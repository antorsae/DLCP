"""Differential parity test for main_core_service_265c.

Runs a purpose-built V3.2 MAIN unit-test firmware under gpsim, then
reads RAM bytes 0x01A0..0x01B4 (EEPROM snapshot written by the harness)
and 0x01FF (completion marker) to verify the 19-record dirty-flag ->
EEPROM mapping is preserved exactly.

Same test must pass BEFORE and AFTER the rewrite of main_core_service_265c
from inlined write blocks to table-driven walker — that's the safety
net the rewrite lands behind.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from dlcp_fw.paths import PROJECT_ROOT
from dlcp_fw.sim.gpsim import gpsim_available, require_gpsim_binary

from tests.asm_unit_tests._unit_test_build import build_unit_test_firmware

HARNESS_ASM = Path(__file__).parent / "harness_main_core_service_265c.asm"
OUT_DIR = PROJECT_ROOT / "artifacts" / "reanalysis" / "asm_unit_tests"

# Expected RAM state at 0x01A0..0x01B4 after the harness drives
# main_core_service_265c with dirty_flags=0x0F and source RAM primed to
# 0xA0..0xB2 (see harness_main_core_service_265c.asm header).
# Expected RAM state for the 19 offsets that main_core_service_265c
# actively writes.  Offsets 0x05 and 0x06 are NOT in the contract (the
# function doesn't touch them); gpsim boots EEPROM to 0x00 and we don't
# snapshot a pre-run baseline, so those two slots are unassertable from
# this harness — intentionally omitted.
EXPECTED_EEPROM_SNAPSHOT = {
    0x1A0: 0xA3,  # EEPROM 0x00: computed_volume_3
    0x1A1: 0xA2,  # EEPROM 0x01: computed_volume_2
    0x1A2: 0xA1,  # EEPROM 0x02: computed_volume_1
    0x1A3: 0xA0,  # EEPROM 0x03: computed_volume
    0x1A4: 0xA4,  # EEPROM 0x04: input_select
    0x1A7: 0xA7,  # EEPROM 0x07: ram_0x060
    0x1A8: 0xA8,
    0x1A9: 0xA9,
    0x1AA: 0xAA,
    0x1AB: 0xAB,
    0x1AC: 0xAC,
    0x1AD: 0xA5,  # EEPROM 0x0D: ram_0x05F
    0x1AE: 0xAE,  # EEPROM 0x0E: ram_0x0B8
    0x1AF: 0xAD,  # EEPROM 0x0F: ram_0x0B4
    0x1B0: 0xAF,  # EEPROM 0x10: ram_0x09B
    0x1B1: 0xB0,
    0x1B2: 0xB1,
    0x1B3: 0xB2,
    0x1B4: 0xA6,  # EEPROM 0x14: ram_0x0C3
}
UT_STATUS_ADDR = 0x1FF
UT_STATUS_READY = 0xA5
GPSIM_CYCLES = 10_000_000  # ~2.5 s sim time at 4 MIPS


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _run_gpsim_unit_test(hex_path: Path, out_dir: Path) -> dict[int, int]:
    """Run the unit-test firmware and return {ram_addr: value} for the
    reporting region (0x1A0..0x1B4 + 0x1FF).
    """
    stc_path = out_dir / "run.stc"
    cli_log = out_dir / "gpsim_cli.txt"

    report_addrs = sorted(
        list(EXPECTED_EEPROM_SNAPSHOT.keys()) + [UT_STATUS_ADDR]
    )

    lines = [
        "processor p18f2455",
        f"load {hex_path}",
        f"break c {GPSIM_CYCLES}",
        "run",
    ]
    # After the break, dump each RAM byte of interest.  gpsim prints
    # `REG<HEX>[0x<addr>] = 0x<val>` for the `x <addr>` command.
    for addr in report_addrs:
        lines.append(f"x 0x{addr:03X}")
    lines.extend(["quit", ""])
    stc_path.write_text("\n".join(lines), encoding="ascii")

    gpsim_bin = require_gpsim_binary()
    cp = subprocess.run(
        [gpsim_bin, "-i", "-c", str(stc_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    cli_text = cp.stdout + cp.stderr
    cli_log.write_text(cli_text, encoding="utf-8")
    if cp.returncode != 0:
        raise RuntimeError(f"gpsim exited with {cp.returncode}: see {cli_log}")

    # gpsim prints: `REG<UPPERHEX>[0x<addr>] = 0x<val>` for `x <addr>`.
    reg_re = re.compile(
        r"REG[0-9A-Fa-f]+\[0x([0-9A-Fa-f]+)\]\s*=\s*0x([0-9A-Fa-f]+)"
    )
    observed: dict[int, int] = {}
    for m in reg_re.finditer(cli_text):
        observed[int(m.group(1), 16)] = int(m.group(2), 16)

    if not observed:
        raise RuntimeError(
            f"gpsim produced no parseable `reg` output; see {cli_log}"
        )
    return observed


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_core_service_265c_eeprom_parity() -> None:
    """Drives main_core_service_265c via a standalone test firmware and
    verifies the 19-record dirty-flag -> EEPROM mapping byte-for-byte.

    Insensitive to the INTERNAL implementation (inlined vs. table-driven
    walker): both must produce the same EEPROM state from the same RAM
    inputs + dirty-flag mask.
    """
    _require_gpsim()
    _, hex_path = build_unit_test_firmware(
        HARNESS_ASM,
        OUT_DIR,
        name="main_core_service_265c",
    )
    observed = _run_gpsim_unit_test(hex_path, OUT_DIR)

    # Sanity check: the harness must have reached the completion marker.
    status = observed.get(UT_STATUS_ADDR)
    status_repr = f"0x{status:02X}" if status is not None else "MISSING"
    assert status == UT_STATUS_READY, (
        f"unit-test harness did not complete within {GPSIM_CYCLES} cycles: "
        f"RAM[0x{UT_STATUS_ADDR:03X}] = {status_repr} "
        f"(expected 0x{UT_STATUS_READY:02X}); see "
        f"{OUT_DIR / 'gpsim_cli.txt'}"
    )

    # Check every expected EEPROM byte.
    mismatches: list[str] = []
    for addr, expected in EXPECTED_EEPROM_SNAPSHOT.items():
        actual = observed.get(addr)
        actual_repr = f"0x{actual:02X}" if actual is not None else "MISSING"
        if actual != expected:
            mismatches.append(
                f"RAM[0x{addr:03X}] (EEPROM 0x{addr - 0x1A0:02X}): "
                f"got {actual_repr}, expected 0x{expected:02X}"
            )
    if mismatches:
        raise AssertionError(
            "EEPROM state after main_core_service_265c differs from "
            "the 19-record contract:\n  " + "\n  ".join(mismatches)
        )
