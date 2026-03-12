"""Main gpsim harness for validating native, unpatched Timer3 behavior."""

from __future__ import annotations

import os
import pty
import re
import select
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from .gpsim import require_gpsim_binary
from .main_gpsim import (
    MAIN_MAILBOX_TX_BASE,
    MAIN_MAILBOX_TX_SIZE,
    MainGpsimResult,
    _mailbox_tx_bytes,
    build_seeded_main_sim_hex,
    run_main_mailbox_gpsim,
)
from .manifests import (
    main_adc_boot_wait_hook,
    main_reset_to_appstart,
    main_serial_mailbox_hooks_uart_only,
)
from .overlay import apply_overlays
from .paths import MAIN_HEX_PATCHED, SIM_ARTIFACTS_DIR
from .protocol import SerialFrame

_PROMPT = b"**gpsim>"
_EXEC_BREAK_RE = re.compile(r"Execution at .*?\(0x([0-9A-Fa-f]+)\)")
_CYCLE_PREFIX_RE = re.compile(r"^\s*0x([0-9A-Fa-f]+)\s+p18f[0-9A-Za-z]+", re.MULTILINE)
_BP_EXEC_RE = re.compile(r"^\s*(\d+):\s+p18f[0-9A-Za-z]+\s+Execution at .*?\(0x([0-9A-Fa-f]+)\)", re.MULTILINE)
_BP_CYCLE_RE = re.compile(r"^\s*(\d+):\s+cycle\s+0x([0-9A-Fa-f]+)\s+=\s+(\d+)", re.MULTILINE)
_REG_VALUE_RE = re.compile(r"\[0x([0-9A-Fa-f]+)\]\s*=\s*0x([0-9A-Fa-f]+)")
_TXREG_LOG_RE = re.compile(r"Wr(?:ite|ote):\s+0x([0-9A-Fa-f]+)\s+to TXREG\(0x0FAD\)", re.IGNORECASE)
MAIN_GPSIM_PROCESSOR = "p18f2455"
MAIN_GPSIM_FOSC_HZ = 16_000_000


@dataclass(frozen=True)
class Timer3OverflowEvent:
    cycle_at_clear: int
    tmr3_preload: int
    prescaler: int
    overflow_cycles: int
    cycle_target: int


@dataclass(frozen=True)
class MainHarnessTimer3Result:
    run: MainGpsimResult
    timer3_events: Tuple[Timer3OverflowEvent, ...]
    mailbox_consumed: bool


@dataclass(frozen=True)
class Timer3ModelComparison:
    semantic: MainGpsimResult
    harness: MainHarnessTimer3Result
    same_reg5e: bool
    same_mailbox_counters: bool


class _GpsimSession:
    def __init__(self, gpsim_bin: str) -> None:
        master_fd, slave_fd = pty.openpty()
        self.proc = subprocess.Popen(
            [gpsim_bin, "-i"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)
        self.fd = master_fd
        self._buf = b""
        self._read_until_prompt(timeout_s=5.0)

    def _read_available(self, timeout_s: float) -> bytes:
        ready, _, _ = select.select([self.fd], [], [], timeout_s)
        if not ready:
            return b""
        return os.read(self.fd, 4096)

    def _sync(self) -> None:
        settle = time.monotonic() + 0.02
        while True:
            timeout_s = max(0.0, settle - time.monotonic())
            data = self._read_available(timeout_s)
            if not data:
                break
            self._buf += data
            settle = time.monotonic() + 0.02
        idx = self._buf.rfind(_PROMPT)
        if idx >= 0:
            self._buf = self._buf[idx + len(_PROMPT):]

    def _read_until_prompt(self, timeout_s: float) -> str:
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            idx = self._buf.find(_PROMPT)
            if idx >= 0:
                # Drain any immediately-following bytes so we consume repeated prompts
                # emitted by gpsim in one burst (e.g. "...**gpsim> run**gpsim>").
                settle_end = time.monotonic() + 0.02
                while time.monotonic() < settle_end:
                    ready, _, _ = select.select([self.fd], [], [], 0.0)
                    if not ready:
                        break
                    data = os.read(self.fd, 4096)
                    if not data:
                        break
                    self._buf += data

                last_idx = self._buf.rfind(_PROMPT)
                cut = last_idx + len(_PROMPT)
                out = self._buf[:cut]
                self._buf = self._buf[cut:]
                return out.decode("utf-8", errors="replace")

            remaining = max(0.01, end - time.monotonic())
            data = self._read_available(remaining)
            if not data:
                continue
            self._buf += data

        if self.proc.poll() is None:
            raise TimeoutError("gpsim prompt timeout")
        out = self._buf
        self._buf = b""
        return out.decode("utf-8", errors="replace")

    def cmd(self, command: str, *, timeout_s: float = 10.0) -> str:
        if self.proc.poll() is not None:
            raise RuntimeError("gpsim process exited unexpectedly")
        self._sync()
        os.write(self.fd, (command + "\n").encode("ascii"))
        return self._read_until_prompt(timeout_s=timeout_s)

    def close(self) -> None:
        if self.proc.poll() is None:
            try:
                self.cmd("quit", timeout_s=2.0)
            except Exception:
                self.proc.terminate()
        try:
            self.proc.wait(timeout=2.0)
        except Exception:
            self.proc.kill()
        try:
            os.close(self.fd)
        except OSError:
            pass


def _frame_bytes(frames: List[SerialFrame]) -> List[int]:
    out: List[int] = []
    for frame in frames:
        n = frame.normalized()
        out.extend([n.route, n.cmd, n.data])
    return out


def _parse_cycle(output: str) -> int:
    m = _CYCLE_PREFIX_RE.search(output)
    if not m:
        raise RuntimeError("unable to parse cycle counter from gpsim output")
    return int(m.group(1), 16)


def _contains_exec_break(output: str, addr: int) -> bool:
    wanted = addr & 0xFFFF
    for m in _EXEC_BREAK_RE.finditer(output):
        if int(m.group(1), 16) & 0xFFFF == wanted:
            return True
    return False


def _parse_breakpoints(output: str) -> Dict[int, Dict[str, int]]:
    out: Dict[int, Dict[str, int]] = {}
    for m in _BP_EXEC_RE.finditer(output):
        out[int(m.group(1))] = {"kind": 1, "value": int(m.group(2), 16)}
    for m in _BP_CYCLE_RE.finditer(output):
        out[int(m.group(1))] = {"kind": 2, "value": int(m.group(3))}
    return out


def _list_breakpoints(issue: Callable[[str, float], str]) -> Dict[int, Dict[str, int]]:
    return _parse_breakpoints(issue("break", 5.0))


def _add_break_exec(issue: Callable[[str, float], str], addr: int) -> int:
    before = set(_list_breakpoints(issue).keys())
    issue(f"break e 0x{addr:04X}", 5.0)
    after = set(_list_breakpoints(issue).keys())
    new_ids = sorted(after - before)
    if len(new_ids) != 1:
        raise RuntimeError(f"failed to allocate execution breakpoint for 0x{addr:04X}")
    return new_ids[0]


def _clear_break(issue: Callable[[str, float], str], bp_id: int) -> None:
    issue(f"clear {bp_id}", 5.0)


def _read_reg(issue: Callable[[str, float], str], addr: int) -> int:
    for _ in range(3):
        out = issue(f"reg(0x{addr:03x})", 5.0)
        for m in _REG_VALUE_RE.finditer(out):
            if int(m.group(1), 16) == addr:
                return int(m.group(2), 16) & 0xFF
        fallback = re.findall(r"=\s*0x([0-9A-Fa-f]+)", out)
        if fallback:
            return int(fallback[-1], 16) & 0xFF
        time.sleep(0.01)
    raise RuntimeError(f"unable to parse register 0x{addr:03X} value")


def _timer3_overflow_cycles(t3con: int, preload: int) -> Tuple[int, int]:
    prescaler = (1, 2, 4, 8)[(t3con >> 4) & 0x3]
    ticks = (0x10000 - (preload & 0xFFFF)) & 0xFFFF
    if ticks == 0:
        ticks = 0x10000
    return ticks * prescaler, prescaler


def _capture_native_timer3_event(
    issue: Callable[[str, float], str],
    *,
    cycle_now: int,
) -> Timer3OverflowEvent:
    t3con = _read_reg(issue, 0xFB1)
    tmr3h = _read_reg(issue, 0xFB3)
    tmr3l = _read_reg(issue, 0xFB2)
    preload = ((tmr3h & 0xFF) << 8) | (tmr3l & 0xFF)
    overflow_cycles, prescaler = _timer3_overflow_cycles(t3con, preload)
    return Timer3OverflowEvent(
        cycle_at_clear=cycle_now,
        tmr3_preload=preload,
        prescaler=prescaler,
        overflow_cycles=overflow_cycles,
        cycle_target=cycle_now + overflow_cycles,
    )


def _parse_tx_bytes(log_path: Path) -> List[int]:
    out: List[int] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _TXREG_LOG_RE.search(line)
        if m:
            out.append(int(m.group(1), 16) & 0xFF)
    return out


def run_main_mailbox_gpsim_harness_timer3(
    frames: List[SerialFrame],
    *,
    main_hex: Path = MAIN_HEX_PATCHED,
    gpasm: str = "gpasm",
    cycles: int = 120_000_000,
    parser_break_addr: int = 0x1BEA,
    timer_clear_break_addr: int = 0x449C,
    stage1_timeout_s: float = 60.0,
    stage2_timeout_s: float = 30.0,
    keep_artifacts: bool = False,
    artifact_dir: Path | None = None,
) -> MainHarnessTimer3Result:
    rx_bytes = _frame_bytes(frames)
    if len(rx_bytes) > 32:
        raise ValueError(f"mailbox supports at most 32 bytes, got {len(rx_bytes)}")

    with tempfile.TemporaryDirectory(prefix="main_mailbox_timer3_harness_") as td:
        tdp = Path(td)
        seeded_hex = tdp / "main_seeded.hex"
        sim_hex = tdp / "main_sim.hex"
        log_path = tdp / "main_gpsim.log"
        cli_path = tdp / "main_gpsim_cli.txt"
        watch_regs = [0x05E, 0x0A1, 0x0A2, 0x0A3, 0x7C0, 0x7C1, 0x7C2, 0x7C3]
        watch_regs.extend(range(MAIN_MAILBOX_TX_BASE, MAIN_MAILBOX_TX_BASE + MAIN_MAILBOX_TX_SIZE))

        build_seeded_main_sim_hex(main_hex, seeded_hex)
        apply_overlays(
            seeded_hex,
            sim_hex,
            manifests=[
                main_reset_to_appstart(),
                main_serial_mailbox_hooks_uart_only(gpasm=gpasm),
                main_adc_boot_wait_hook(gpasm=gpasm),
            ],
        )

        transcript: List[str] = []
        events: List[Timer3OverflowEvent] = []
        regs: Dict[int, int] = {}
        parser_break_hit = False
        session = _GpsimSession(require_gpsim_binary())

        def issue(command: str, timeout_s: float) -> str:
            out = session.cmd(command, timeout_s=timeout_s)
            transcript.append(out)
            return out

        try:
            issue(f"processor {MAIN_GPSIM_PROCESSOR}", 5.0)
            issue(f"load {sim_hex}", 20.0)
            issue(f"frequency {MAIN_GPSIM_FOSC_HZ}", 5.0)
            issue(f"log on {log_path}", 5.0)
            issue("log w txreg", 5.0)

            parser_bp = _add_break_exec(issue, parser_break_addr)
            timer_bp = _add_break_exec(issue, timer_clear_break_addr)
            native_timer_seen = False

            stage1_deadline = time.monotonic() + stage1_timeout_s
            while not parser_break_hit:
                remain = stage1_deadline - time.monotonic()
                if remain <= 0:
                    raise RuntimeError("stage1 timeout before parser breakpoint")
                out = issue("run", max(1.0, remain))
                if "Stack overflow" in out:
                    raise RuntimeError("gpsim stack overflow while waiting for parser break")
                if _contains_exec_break(out, timer_clear_break_addr):
                    event = _capture_native_timer3_event(issue, cycle_now=_parse_cycle(out))
                    issue(f"break c {event.cycle_target}", 5.0)
                    out_overflow = issue("run", max(1.0, remain))
                    if "cycle break:" not in out_overflow:
                        raise RuntimeError("native Timer3 overflow cycle break did not trigger")
                    if (_read_reg(issue, 0xFA1) & 0x02) == 0:
                        raise RuntimeError("native Timer3 did not raise PIR2.TMR3IF at scheduled overflow")
                    issue("clear 3", 5.0)
                    events.append(event)
                    native_timer_seen = True
                    _clear_break(issue, timer_bp)
                    timer_bp = -1
                    continue
                if _contains_exec_break(out, parser_break_addr):
                    parser_break_hit = True
                    break
                if "Hit a Breakpoint!" not in out:
                    continue
                raise RuntimeError("unexpected breakpoint before parser")

            if not parser_break_hit:
                raise RuntimeError("parser breakpoint not reached")
            if not native_timer_seen:
                raise RuntimeError("native Timer3 clear-site was never observed before parser")

            _clear_break(issue, parser_bp)
            parser_bp = -1

            issue("reg(0x7c0)=0x00", 5.0)
            issue(f"reg(0x7c1)=0x{len(rx_bytes) & 0xFF:02X}", 5.0)
            issue("reg(0x7c2)=0x00", 5.0)
            issue("reg(0x7c3)=0x00", 5.0)
            for i, b in enumerate(rx_bytes):
                issue(f"reg(0x{(0x780 + i):03x})=0x{b & 0xFF:02X}", 5.0)

            issue(f"break c {cycles}", 5.0)
            out = issue("run", max(1.0, stage2_timeout_s))
            if "cycle break:" not in out:
                raise RuntimeError("stage2 timeout before cycle break")
            issue("clear 3", 5.0)
            issue("log off", 5.0)

            for r in watch_regs:
                regs[r] = _read_reg(issue, r)
            consumed = (
                regs.get(0x7C0, 0) == regs.get(0x7C1, 0) == (len(rx_bytes) & 0xFF)
                and regs.get(0x7C3, 0) >= regs.get(0x7C1, 0)
            )
            if not consumed:
                raise RuntimeError("stage2 timeout before mailbox consumption")
        except Exception as exc:
            fail_dir = SIM_ARTIFACTS_DIR / "main_mailbox_timer3_harness_failed"
            fail_dir.mkdir(parents=True, exist_ok=True)
            fail_cli = fail_dir / f"main_gpsim_failed_{int(time.time() * 1000)}.txt"
            fail_cli.write_text("".join(transcript), encoding="utf-8")
            raise RuntimeError(f"{exc} (partial transcript: {fail_cli})") from exc
        finally:
            session.close()

        cli_text = "".join(transcript)
        cli_path.write_text(cli_text, encoding="utf-8")
        tx_bytes = _mailbox_tx_bytes(regs)
        if not tx_bytes:
            tx_bytes = _parse_tx_bytes(log_path)

        if keep_artifacts:
            if artifact_dir is None:
                artifact_dir = SIM_ARTIFACTS_DIR / "main_mailbox_timer3_harness_last"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "main_sim.hex").write_bytes(sim_hex.read_bytes())
            (artifact_dir / "main_gpsim.log").write_bytes(log_path.read_bytes())
            (artifact_dir / "main_gpsim_cli.txt").write_text(cli_text, encoding="utf-8")
            run_result = MainGpsimResult(
                sim_hex=artifact_dir / "main_sim.hex",
                log_path=artifact_dir / "main_gpsim.log",
                cli_path=artifact_dir / "main_gpsim_cli.txt",
                tx_bytes=tx_bytes,
                regs=regs,
                cycles=cycles,
                parser_break_hit=parser_break_hit,
            )
        else:
            run_result = MainGpsimResult(
                sim_hex=sim_hex,
                log_path=log_path,
                cli_path=cli_path,
                tx_bytes=tx_bytes,
                regs=regs,
                cycles=cycles,
                parser_break_hit=parser_break_hit,
            )

        return MainHarnessTimer3Result(
            run=run_result,
            timer3_events=tuple(events),
            mailbox_consumed=consumed,
        )


def compare_timer3_models(
    frames: List[SerialFrame],
    *,
    main_hex: Path = MAIN_HEX_PATCHED,
    gpasm: str = "gpasm",
    cycles: int = 120_000_000,
    stage1_timeout_s: float = 60.0,
) -> Timer3ModelComparison:
    semantic = run_main_mailbox_gpsim(
        frames=frames,
        main_hex=main_hex,
        gpasm=gpasm,
        cycles=cycles,
        stage1_timeout_s=stage1_timeout_s,
    )
    harness = run_main_mailbox_gpsim_harness_timer3(
        frames=frames,
        main_hex=main_hex,
        gpasm=gpasm,
        cycles=cycles,
        stage1_timeout_s=stage1_timeout_s,
    )
    same_reg5e = semantic.regs.get(0x5E, 0) == harness.run.regs.get(0x5E, 0)
    same_mailbox = (
        harness.mailbox_consumed
        and semantic.regs.get(0x7C1, 0) == harness.run.regs.get(0x7C1, 0)
        and semantic.regs.get(0x7C3, 0) == harness.run.regs.get(0x7C3, 0)
    )
    return Timer3ModelComparison(
        semantic=semantic,
        harness=harness,
        same_reg5e=same_reg5e,
        same_mailbox_counters=same_mailbox,
    )
