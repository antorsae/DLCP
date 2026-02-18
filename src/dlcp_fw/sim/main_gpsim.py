"""Instruction-level main firmware simulation with mailbox RX/TX probes."""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from .manifests import main_reset_to_appstart, main_serial_mailbox_hooks
from .overlay import apply_overlays
from .paths import MAIN_HEX_PATCHED, SIM_ARTIFACTS_DIR
from .protocol import SerialFrame


@dataclass(frozen=True)
class MainGpsimResult:
    sim_hex: Path
    log_path: Path
    cli_path: Path
    tx_bytes: List[int]
    regs: Dict[int, int]
    cycles: int
    parser_break_hit: bool = False


def _build_frame_bytes(frames: Sequence[SerialFrame]) -> List[int]:
    out: List[int] = []
    for f in frames:
        n = f.normalized()
        out.extend([n.route, n.cmd, n.data])
    return out


def _build_script(
    sim_hex: Path,
    log_path: Path,
    cycles: int,
    parser_break_addr: int,
    rx_bytes: Sequence[int],
    cli_path: Path,
    watch_regs: Iterable[int],
) -> str:
    lines = [
        "processor p18f2550",
        f"load {sim_hex}",
        f"log on {log_path}",
        "log w txreg",
        # Stage 1: run boot/init until parser loop entry (0x1BEA).
        f"break e 0x{parser_break_addr:04X}",
        "run",
        # Stage 2: inject mailbox after RAM init is complete.
        "reg(0x7c0)=0x00",  # rx_rd
        f"reg(0x7c1)=0x{len(rx_bytes) & 0xFF:02X}",  # rx_wr
        "reg(0x7c2)=0x00",  # tx_rd (reserved)
        "reg(0x7c3)=0x00",  # tx_wr
    ]
    for i, b in enumerate(rx_bytes):
        lines.append(f"reg(0x{(0x780 + i):03x})=0x{b & 0xFF:02X}")
    lines.extend(
        [
            "clear 0",
            "clear 1",
            f"break c {cycles}",
            "run",
            "log off",
        ]
    )
    for r in watch_regs:
        lines.append(f"reg(0x{r:03x})")
    lines.append("quit")
    text = "\n".join(lines) + "\n"
    cli_path.with_suffix(".stc").write_text(text, encoding="ascii")
    return text


def _parse_tx_bytes(log_path: Path) -> List[int]:
    # gpsim log style includes lines like:
    # Write: 0xBF to TXREG(0x0FAD)
    # Wrote: 0x00BF to txreg(0x0fad)
    p = re.compile(r"Wr(?:ite|ote):\s+0x([0-9A-Fa-f]+)\s+to TXREG\(0x0FAD\)", re.IGNORECASE)
    out: List[int] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = p.search(line)
        if m:
            out.append(int(m.group(1), 16) & 0xFF)
    return out


def _parse_regs(cli_text: str) -> Dict[int, int]:
    # Example:
    # REG05E[0x5e] = 0x04 was 0x00
    p = re.compile(r"REG([0-9A-Fa-f]{3})\[0x([0-9A-Fa-f]+)\]\s*=\s*0x([0-9A-Fa-f]+)")
    out: Dict[int, int] = {}
    for line in cli_text.splitlines():
        m = p.search(line)
        if m:
            addr = int(m.group(2), 16)
            val = int(m.group(3), 16)
            out[addr] = val
    return out


def run_main_mailbox_gpsim(
    frames: Sequence[SerialFrame],
    *,
    main_hex: Path = MAIN_HEX_PATCHED,
    gpasm: str = "gpasm",
    cycles: int = 120_000_000,
    parser_break_addr: int = 0x1BEA,
    stage1_timeout_s: float = 20.0,
    keep_artifacts: bool = False,
    artifact_dir: Path | None = None,
) -> MainGpsimResult:
    rx_bytes = _build_frame_bytes(frames)
    if len(rx_bytes) > 32:
        raise ValueError(f"mailbox supports at most 32 bytes, got {len(rx_bytes)}")
    # Include legacy command side-effect registers used by compatibility tests.
    watch_regs = [
        0x05E,
        0x066,  # volume signed 32-bit cache (low)
        0x067,
        0x068,
        0x069,  # volume signed 32-bit cache (high)
        0x06E,  # latest computed volume signed value (low)
        0x06F,
        0x070,
        0x071,  # latest computed volume signed value (high)
        0x07E,  # dirty flags for DSP updates
        0x07F,  # timeout/display dirty flags
        0x094,  # main state bitfield used in command handlers
        0x099,  # source config shadow
        0x0A1,
        0x0A2,
        0x0A3,
        0x0A5,  # ch1 source
        0x0A6,  # ch2 source
        0x0A7,  # ch3 source / timeout
        0x0A8,  # ch4 source
        0x0A9,  # ch5 source
        0x0AA,  # ch6 source
        0x0B2,  # link address (cmd 0x1E)
        0x0B3,  # source config mirror (cmd 0x06)
        0x0B8,  # display/backlight timeout (cmd 0x1D)
        0x0BC,  # command response byte staging
        0x0C3,  # mirrored link address (cmd 0x1E)
        0x7C0,
        0x7C1,
        0x7C3,
    ]

    with tempfile.TemporaryDirectory(prefix="main_mailbox_sim_") as td:
        tdp = Path(td)
        sim_hex = tdp / "main_sim.hex"
        log_path = tdp / "main_gpsim.log"
        cli_path = tdp / "main_gpsim_cli.txt"

        apply_overlays(
            main_hex,
            sim_hex,
            manifests=[main_reset_to_appstart(), main_serial_mailbox_hooks(gpasm=gpasm)],
        )

        stc_path = cli_path.with_suffix(".stc")
        script_text = _build_script(
            sim_hex=sim_hex,
            log_path=log_path,
            cycles=cycles,
            parser_break_addr=parser_break_addr,
            rx_bytes=rx_bytes,
            cli_path=cli_path,
            watch_regs=watch_regs,
        )
        try:
            cp = subprocess.run(
                ["gpsim", "-i", "-c", str(stc_path)],
                text=True,
                capture_output=True,
                check=False,
                timeout=stage1_timeout_s + 20.0,
            )
        except subprocess.TimeoutExpired as exc:
            cli_path.write_text((exc.stdout or "") + (exc.stderr or ""), encoding="utf-8")
            raise RuntimeError(f"gpsim timed out after {exc.timeout}s; inspect {cli_path}") from exc
        cli_text = cp.stdout + cp.stderr
        cli_path.write_text(cli_text, encoding="utf-8")
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim exited {cp.returncode}; inspect {cli_path}")
        parser_break_hit = bool(
            re.search(rf"\b0x{parser_break_addr:04x}\b", cli_text, flags=re.IGNORECASE)
        )
        if not parser_break_hit:
            raise RuntimeError(
                f"gpsim did not reach parser break 0x{parser_break_addr:04X}; inspect {cli_path}"
            )
        if "cycle break:" not in cli_text:
            raise RuntimeError(f"gpsim did not hit cycle break; inspect {cli_path}")

        tx_bytes = _parse_tx_bytes(log_path)
        regs = _parse_regs(cli_text)

        if keep_artifacts:
            if artifact_dir is None:
                artifact_dir = SIM_ARTIFACTS_DIR / "main_mailbox_last"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "main_sim.hex").write_bytes(sim_hex.read_bytes())
            (artifact_dir / "main_gpsim.log").write_bytes(log_path.read_bytes())
            (artifact_dir / "main_gpsim_cli.txt").write_text(cli_text, encoding="utf-8")
            (artifact_dir / "main_gpsim.stc").write_text(script_text, encoding="ascii")
            return MainGpsimResult(
                sim_hex=artifact_dir / "main_sim.hex",
                log_path=artifact_dir / "main_gpsim.log",
                cli_path=artifact_dir / "main_gpsim_cli.txt",
                tx_bytes=tx_bytes,
                regs=regs,
                cycles=cycles,
                parser_break_hit=parser_break_hit,
            )

        return MainGpsimResult(
            sim_hex=sim_hex,
            log_path=log_path,
            cli_path=cli_path,
            tx_bytes=tx_bytes,
            regs=regs,
            cycles=cycles,
            parser_break_hit=parser_break_hit,
        )
