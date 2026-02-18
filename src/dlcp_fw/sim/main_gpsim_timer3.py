"""Main gpsim harness with cycle-accurate Timer3 emulation outside firmware patching."""

from __future__ import annotations

import os
import re
import select
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from .main_gpsim import MainGpsimResult, run_main_mailbox_gpsim
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
_CYCLE_PREFIX_RE = re.compile(r"^\s*0x([0-9A-Fa-f]+)\s+p18f2550", re.MULTILINE)
_BP_EXEC_RE = re.compile(r"^\s*(\d+):\s+p18f2550 Execution at .*?\(0x([0-9A-Fa-f]+)\)", re.MULTILINE)
_BP_CYCLE_RE = re.compile(r"^\s*(\d+):\s+cycle\s+0x([0-9A-Fa-f]+)\s+=\s+(\d+)", re.MULTILINE)
_REG_VALUE_RE = re.compile(r"\[0x([0-9A-Fa-f]+)\]\s*=\s*0x([0-9A-Fa-f]+)")
_TXREG_LOG_RE = re.compile(r"Wr(?:ite|ote):\s+0x([0-9A-Fa-f]+)\s+to TXREG\(0x0FAD\)", re.IGNORECASE)


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
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            ["gpsim", "-i"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("failed to open gpsim stdin/stdout")
        self.stdin = self.proc.stdin
        self.stdout = self.proc.stdout
        self.fd = self.stdout.fileno()
        self._buf = b""
        self._read_until_prompt(timeout_s=5.0)

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
            ready, _, _ = select.select([self.fd], [], [], remaining)
            if not ready:
                continue
            data = os.read(self.fd, 4096)
            if not data:
                break
            self._buf += data

        if self.proc.poll() is None:
            raise TimeoutError("gpsim prompt timeout")
        out = self._buf
        self._buf = b""
        return out.decode("utf-8", errors="replace")

    def cmd(self, command: str, *, timeout_s: float = 10.0) -> str:
        if self.proc.poll() is not None:
            raise RuntimeError("gpsim process exited unexpectedly")
        self.stdin.write((command + "\n").encode("ascii"))
        self.stdin.flush()
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


def _add_break_cycle(issue: Callable[[str, float], str], cycle: int) -> int:
    before_map = _list_breakpoints(issue)
    before = set(before_map.keys())
    issue(f"break c {cycle}", 5.0)
    after_map = _list_breakpoints(issue)
    after = set(after_map.keys())
    new_ids = sorted(after - before)
    if new_ids:
        return new_ids[-1]
    for bp_id, meta in after_map.items():
        if meta.get("kind") == 2 and meta.get("value") == cycle:
            return bp_id
    raise RuntimeError(f"failed to allocate cycle breakpoint for {cycle}")


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
        sim_hex = tdp / "main_sim.hex"
        log_path = tdp / "main_gpsim.log"
        cli_path = tdp / "main_gpsim_cli.txt"
        watch_regs = [0x05E, 0x0A1, 0x0A2, 0x0A3, 0x7C0, 0x7C1, 0x7C3]

        apply_overlays(
            main_hex,
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
        session = _GpsimSession()

        def issue(command: str, timeout_s: float) -> str:
            out = session.cmd(command, timeout_s=timeout_s)
            transcript.append(out)
            return out

        try:
            issue("processor p18f2550", 5.0)
            issue(f"load {sim_hex}", 20.0)
            issue(f"log on {log_path}", 5.0)
            issue("log w txreg", 5.0)

            parser_bp = _add_break_exec(issue, parser_break_addr)
            timer_bp = _add_break_exec(issue, timer_clear_break_addr)
            last_overflow_cycles = 4000

            stage1_deadline = time.monotonic() + stage1_timeout_s
            while not parser_break_hit:
                remain = stage1_deadline - time.monotonic()
                if remain <= 0:
                    raise RuntimeError("stage1 timeout before parser breakpoint")
                out = issue("run", max(1.0, remain))
                if _contains_exec_break(out, parser_break_addr):
                    parser_break_hit = True
                    break
                if "Stack overflow" in out:
                    raise RuntimeError("gpsim stack overflow while waiting for parser break")
                if not _contains_exec_break(out, timer_clear_break_addr):
                    # gpsim can emit prompt-only bursts around repeated run commands.
                    # Ignore non-break outputs and continue until a real breakpoint appears.
                    if "Hit a Breakpoint!" not in out:
                        continue
                    raise RuntimeError("unexpected breakpoint while emulating Timer3")

                cycle_now = _parse_cycle(out)
                t3con = _read_reg(issue, 0xFB1)
                tmr3h = _read_reg(issue, 0xFB3)
                tmr3l = _read_reg(issue, 0xFB2)
                preload = ((tmr3h & 0xFF) << 8) | (tmr3l & 0xFF)
                overflow_cycles, prescaler = _timer3_overflow_cycles(t3con, preload)
                if 500 <= overflow_cycles <= 10000:
                    last_overflow_cycles = overflow_cycles
                else:
                    overflow_cycles = last_overflow_cycles
                target_cycle = cycle_now + overflow_cycles

                out_break_c = issue(f"break c {target_cycle}", 5.0)
                if "ignored because cycle" in out_break_c:
                    pir2 = _read_reg(issue, 0xFA1)
                    issue(f"reg(0xFA1)=0x{(pir2 | 0x02) & 0xFF:02X}", 5.0)
                    events.append(
                        Timer3OverflowEvent(
                            cycle_at_clear=cycle_now,
                            tmr3_preload=preload,
                            prescaler=prescaler,
                            overflow_cycles=overflow_cycles,
                            cycle_target=target_cycle,
                        )
                    )
                    continue
                out_cycle = issue("run", max(1.0, remain))
                if "cycle break:" not in out_cycle:
                    issue("clear 3", 5.0)
                    if _contains_exec_break(out_cycle, timer_clear_break_addr) or "Hit a Breakpoint!" in out_cycle:
                        # Our scheduled cycle was too late; inject TMR3IF immediately.
                        pir2 = _read_reg(issue, 0xFA1)
                        issue(f"reg(0xFA1)=0x{(pir2 | 0x02) & 0xFF:02X}", 5.0)
                        events.append(
                            Timer3OverflowEvent(
                                cycle_at_clear=cycle_now,
                                tmr3_preload=preload,
                                prescaler=prescaler,
                                overflow_cycles=overflow_cycles,
                                cycle_target=target_cycle,
                            )
                        )
                        continue
                    if _contains_exec_break(out_cycle, parser_break_addr):
                        parser_break_hit = True
                        break
                    # Prompt-only drift: inject and continue.
                    pir2 = _read_reg(issue, 0xFA1)
                    issue(f"reg(0xFA1)=0x{(pir2 | 0x02) & 0xFF:02X}", 5.0)
                    events.append(
                        Timer3OverflowEvent(
                            cycle_at_clear=cycle_now,
                            tmr3_preload=preload,
                            prescaler=prescaler,
                            overflow_cycles=overflow_cycles,
                            cycle_target=target_cycle,
                        )
                    )
                    continue

                pir2 = _read_reg(issue, 0xFA1)
                issue(f"reg(0xFA1)=0x{(pir2 | 0x02) & 0xFF:02X}", 5.0)
                issue("clear 3", 5.0)

                events.append(
                    Timer3OverflowEvent(
                        cycle_at_clear=cycle_now,
                        tmr3_preload=preload,
                        prescaler=prescaler,
                        overflow_cycles=overflow_cycles,
                        cycle_target=target_cycle,
                    )
                )

            if not parser_break_hit:
                raise RuntimeError("parser breakpoint not reached")

            issue("reg(0x7c0)=0x00", 5.0)
            issue(f"reg(0x7c1)=0x{len(rx_bytes) & 0xFF:02X}", 5.0)
            issue("reg(0x7c2)=0x00", 5.0)
            issue("reg(0x7c3)=0x00", 5.0)
            for i, b in enumerate(rx_bytes):
                issue(f"reg(0x{(0x780 + i):03x})=0x{b & 0xFF:02X}", 5.0)

            consumed = False
            stage2_deadline = time.monotonic() + stage2_timeout_s
            while time.monotonic() < stage2_deadline:
                rx_rd = _read_reg(issue, 0x7C0)
                rx_wr = _read_reg(issue, 0x7C1)
                tx_wr = _read_reg(issue, 0x7C3)
                if rx_rd == rx_wr == (len(rx_bytes) & 0xFF) and tx_wr >= rx_wr:
                    consumed = True
                    break

                remain2 = stage2_deadline - time.monotonic()
                out2 = issue("run", max(1.0, remain2))
                if _contains_exec_break(out2, parser_break_addr):
                    continue
                if _contains_exec_break(out2, timer_clear_break_addr):
                    cycle_now = _parse_cycle(out2)
                    t3con = _read_reg(issue, 0xFB1)
                    tmr3h = _read_reg(issue, 0xFB3)
                    tmr3l = _read_reg(issue, 0xFB2)
                    preload = ((tmr3h & 0xFF) << 8) | (tmr3l & 0xFF)
                    overflow_cycles, prescaler = _timer3_overflow_cycles(t3con, preload)
                    if 500 <= overflow_cycles <= 10000:
                        last_overflow_cycles = overflow_cycles
                    else:
                        overflow_cycles = last_overflow_cycles
                    target_cycle = cycle_now + overflow_cycles
                    out_break_c = issue(f"break c {target_cycle}", 5.0)
                    if "ignored because cycle" not in out_break_c:
                        out_cycle = issue("run", max(1.0, remain2))
                        if "cycle break:" not in out_cycle:
                            issue("clear 3", 5.0)
                    pir2 = _read_reg(issue, 0xFA1)
                    issue(f"reg(0xFA1)=0x{(pir2 | 0x02) & 0xFF:02X}", 5.0)
                    issue("clear 3", 5.0)
                    events.append(
                        Timer3OverflowEvent(
                            cycle_at_clear=cycle_now,
                            tmr3_preload=preload,
                            prescaler=prescaler,
                            overflow_cycles=overflow_cycles,
                            cycle_target=target_cycle,
                        )
                    )
                    continue
                if "cycle break:" in out2:
                    issue("clear 3", 5.0)
                    continue

            if not consumed:
                raise RuntimeError("stage2 timeout before mailbox consumption")

            _clear_break(issue, parser_bp)
            _clear_break(issue, timer_bp)
            issue("clear 3", 5.0)
            issue("log off", 5.0)

            for r in watch_regs:
                regs[r] = _read_reg(issue, r)
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
