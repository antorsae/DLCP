#!/usr/bin/env python3
"""Capture an early-boot V1.71 ground-truth snapshot for the
P1.8d Rust ISA-parity gate.

Runs gpsim with the canonical V1.71 CONTROL release loaded, no
overlays applied, breaks at a fixed Tcy target, then dumps:

  - RAM bank 0  (0x000-0x0FF, 256 bytes) -- saved as
    early_boot_v171_<cycles>.ram.bin
  - SFR window  (0xF60-0xFFF, 160 bytes) -- saved as
    early_boot_v171_<cycles>.sfr.json (hex-keyed dict)
  - Cycle target -- saved as
    early_boot_v171_<cycles>.meta.json

Output goes to artifacts/ground_truth/v171_early_boot_parity/.

The cycle target needs to be small enough that the V1.71
firmware hasn't yet exercised peripherals that the Phase-1 Rust
executor doesn't model (timers, UART, ADC, USB, I2C).  100k Tcy
is the spec's recommended starting point per
docs/SIM_REWRITE_RUST_SPEC.md §5.

This script does NOT use the harness machinery
(GpsimControlHarness applies overlays for fast-boot which alter
the firmware footprint; for ISA parity we want a clean POR boot
with the unmodified release hex).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dlcp_fw.paths import V171_CONTROL_HEX  # noqa: E402
from dlcp_fw.sim.gpsim import require_gpsim_binary  # noqa: E402


def _parse_reg_response(output: str, addr: int) -> int:
    """Extract `reg(0xXXX) = 0xYY` from gpsim's interactive output."""
    pattern = re.compile(
        rf"reg\(0x{addr:03X}\)\s*=\s*0x([0-9A-Fa-f]{{1,8}})",
    )
    m = pattern.search(output)
    if m:
        return int(m.group(1), 16) & 0xFF
    # Fallback: gpsim sometimes prints just `= 0xYY`.
    pattern2 = re.compile(r"=\s*0x([0-9A-Fa-f]{1,8})")
    matches = pattern2.findall(output)
    if matches:
        return int(matches[-1], 16) & 0xFF
    raise RuntimeError(f"could not parse reg(0x{addr:03X}) from: {output[:200]!r}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture early-boot V1.71 parity snapshot."
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=100_000,
        help="gpsim Tcy target (default: 100000 per spec §5)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "artifacts/ground_truth/v171_early_boot_parity",
    )
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    gpsim_bin = require_gpsim_binary()
    hex_path = V171_CONTROL_HEX
    if not hex_path.exists():
        print(f"V1.71 hex not found at {hex_path}", file=sys.stderr)
        return 1

    # Build a gpsim batch script that runs to break, dumps every
    # register we care about, then quits.  reg(addr) prints the
    # current value as a side effect of the CLI.
    addrs: list[int] = list(range(0x000, 0x100)) + list(range(0xF60, 0x1000))
    stc = out_dir / "capture.stc"
    log = out_dir / "gpsim.log"
    lines: list[str] = [
        "processor p18f25k20",
        f"load {hex_path}",
        f"log on {log}",
        f"break c {args.cycles}",
        "run",
    ]
    for addr in addrs:
        lines.append(f"reg(0x{addr:03X})")
    lines.extend(["log off", "quit", ""])
    stc.write_text("\n".join(lines), encoding="ascii")

    print(f"running gpsim with {args.cycles} Tcy target ...", file=sys.stderr)
    cp = subprocess.run(
        [gpsim_bin, "-i", "-c", str(stc)],
        text=True,
        capture_output=True,
        check=False,
    )
    cli_text = cp.stdout + cp.stderr
    cli_path = out_dir / "gpsim_cli.txt"
    cli_path.write_text(cli_text, encoding="utf-8")
    if cp.returncode != 0:
        print(f"gpsim failed (rc={cp.returncode}); see {cli_path}", file=sys.stderr)
        return 1
    if "cycle break:" not in cli_text:
        print(f"gpsim did not hit cycle break; see {cli_path}", file=sys.stderr)
        return 1

    # Parse register dumps.  gpsim prints `REGNAME[0xADDR] =
    # 0xVALUE` lines, where REGNAME varies (REG0FE, BSR, STATUS,
    # ...).  We trust the bracketed hex address.
    ram = bytearray(256)
    ram_addrs_seen: set[int] = set()
    sfr: dict[int, int] = {}
    rg = re.compile(r"\b\w+\[0x([0-9a-fA-F]+)\]\s*=\s*0x([0-9a-fA-F]+)")
    for match in rg.finditer(cli_text):
        addr = int(match.group(1), 16)
        value = int(match.group(2), 16) & 0xFF
        if 0x000 <= addr <= 0x0FF:
            ram[addr] = value
            ram_addrs_seen.add(addr)
        elif 0xF60 <= addr <= 0xFFF:
            sfr[addr] = value

    expected_sfr = len(range(0xF60, 0x1000))
    if len(sfr) != expected_sfr:
        print(
            f"error: SFR dump incomplete ({len(sfr)} of "
            f"{expected_sfr} entries); see {cli_path}",
            file=sys.stderr,
        )
        return 1
    expected_ram = 0x100
    if len(ram_addrs_seen) != expected_ram:
        print(
            f"error: RAM dump incomplete ({len(ram_addrs_seen)} of "
            f"{expected_ram} distinct addresses parsed); see {cli_path}",
            file=sys.stderr,
        )
        return 1

    stem = f"early_boot_v171_{args.cycles}"
    ram_path = out_dir / f"{stem}.ram.bin"
    sfr_path = out_dir / f"{stem}.sfr.json"
    meta_path = out_dir / f"{stem}.meta.json"

    ram_path.write_bytes(bytes(ram))
    sfr_path.write_text(
        json.dumps(
            {f"0x{addr:03X}": v for addr, v in sorted(sfr.items())},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    meta_path.write_text(
        json.dumps({"cycle": args.cycles, "hex_path": str(hex_path.relative_to(REPO_ROOT))}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    print(f"captured early-boot snapshot at {args.cycles} Tcy:", file=sys.stderr)
    print(f"  {ram_path}", file=sys.stderr)
    print(f"  {sfr_path}", file=sys.stderr)
    print(f"  {meta_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
