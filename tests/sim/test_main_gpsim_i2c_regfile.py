from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from dlcp_fw.sim.gpsim import gpsim_available, require_gpsim_binary
from dlcp_fw.sim.main_gpsim import (
    MAIN_GPSIM_PROCESSOR,
    MainI2CRegFileDevice,
    build_seeded_main_sim_hex,
    write_main_an0_bootstrap_stc,
    write_main_i2c_regfile_stc,
)
from dlcp_fw.sim.manifests import main_reset_to_appstart
from dlcp_fw.sim.overlay import apply_overlays

_BREAK_RE = re.compile(r"line_([0-9a-f]{4})\(0x([0-9a-f]{4})\)", re.IGNORECASE)
_SFR_RE = re.compile(r"\[0x([0-9A-Fa-f]+)\]\s*=\s*0x([0-9A-Fa-f]+)")
_REGFILE_RE = re.compile(r"(?:[A-Za-z0-9_]+\.)?reg([0-9A-Fa-f]{2})\s*=\s*(?:\$|0x)([0-9A-Fa-f]+)", re.IGNORECASE)


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _did_hit_break(cli_text: str, addr: int) -> bool:
    wanted = addr & 0xFFFF
    for match in _BREAK_RE.finditer(cli_text):
        if int(match.group(2), 16) == wanted:
            return True
    return False


def _read_sfr(cli_text: str, addr: int) -> int:
    for match in _SFR_RE.finditer(cli_text):
        if int(match.group(1), 16) == addr:
            return int(match.group(2), 16) & 0xFF
    raise AssertionError(f"missing SFR readback for 0x{addr:03X}")


def _read_regfile(cli_text: str, addr: int) -> int:
    wanted_addr = addr & 0xFF
    for match in _REGFILE_RE.finditer(cli_text):
        if int(match.group(1), 16) != wanted_addr:
            continue
        return int(match.group(2), 16) & 0xFF
    raise AssertionError(f"missing regfile readback for reg{wanted_addr:02x}")


def _run_main_i2c_regfile_probe(main_hex: Path, *, lines: list[str]) -> str:
    with tempfile.TemporaryDirectory(prefix="main_i2c_regfile_probe_") as td:
        tdp = Path(td)
        seeded_hex = tdp / "main_seeded.hex"
        sim_hex = tdp / "main_sim.hex"
        boot_stc = tdp / "main_an0_bootstrap.stc"
        i2c_stc = tdp / "main_i2c_bus.stc"
        run_stc = tdp / "main_i2c_probe.stc"

        build_seeded_main_sim_hex(main_hex, seeded_hex)
        apply_overlays(seeded_hex, sim_hex, manifests=[main_reset_to_appstart()])
        write_main_an0_bootstrap_stc(boot_stc, processor=MAIN_GPSIM_PROCESSOR)
        write_main_i2c_regfile_stc(
            i2c_stc,
            devices=[
                MainI2CRegFileDevice("cfg71", 0x71, registers={0x12: 0x34}),
                MainI2CRegFileDevice("dsp34", 0x34),
            ],
            processor=MAIN_GPSIM_PROCESSOR,
        )

        stc_lines = [
            f"processor {MAIN_GPSIM_PROCESSOR}",
            f"load {sim_hex}",
            "frequency 16000000",
            f"load {boot_stc}",
            f"load {i2c_stc}",
            "break e 0x1BEA",
            "run",
            "clear 0",
            *lines,
            "quit",
            "",
        ]
        run_stc.write_text("\n".join(stc_lines), encoding="ascii")
        cp = subprocess.run(
            [require_gpsim_binary(), "-i", "-c", str(run_stc)],
            text=True,
            capture_output=True,
            check=False,
            timeout=180.0,
        )
        cli_text = cp.stdout + cp.stderr
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim probe failed ({cp.returncode}):\n{cli_text}")
        if not _did_hit_break(cli_text, 0x1BEA):
            raise RuntimeError(f"gpsim probe never reached parser loop:\n{cli_text}")
        return cli_text


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_shadow_i2c_regfile_read_write_without_external_bypass(stock_main_hex: Path) -> None:
    _require_gpsim()

    cli_text = _run_main_i2c_regfile_probe(
        stock_main_hex,
        lines=[
            # Stock caller at 0x18FE performs two writes via function_093:
            #   0x0D <- 0x09
            #   0x08 <- 0x70
            "pc=0x18FE",
            "break e 0x1990",
            "run",
            "cfg71.reg0d",
            "cfg71.reg08",
            # Stock caller at 0x292E performs a random-read via function_067
            # and returns with the byte in WREG at 0x2934.
            "pc=0x292E",
            "break e 0x2934",
            "run",
            "reg(0xFE8)",
        ],
    )

    assert _did_hit_break(cli_text, 0x1990)
    assert _did_hit_break(cli_text, 0x2934)
    assert _read_regfile(cli_text, 0x0D) == 0x09
    assert _read_regfile(cli_text, 0x08) == 0x70
    assert _read_sfr(cli_text, 0xFE8) == 0x34


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_dsp_i2c_regfile_captures_stock_multi_byte_write(stock_main_hex: Path) -> None:
    _require_gpsim()

    cli_text = _run_main_i2c_regfile_probe(
        stock_main_hex,
        lines=[
            # Stock caller at 0x48E2 invokes function_072, which writes:
            #   DSP reg 0x1F <- 0x00 0x00 0x00 0x02
            "pc=0x48E2",
            "break e 0x48E8",
            "run",
            "dsp34.reg1f",
            "dsp34.reg20",
            "dsp34.reg21",
            "dsp34.reg22",
        ],
    )

    assert _did_hit_break(cli_text, 0x48E8)
    assert _read_regfile(cli_text, 0x1F) == 0x00
    assert _read_regfile(cli_text, 0x20) == 0x00
    assert _read_regfile(cli_text, 0x21) == 0x00
    assert _read_regfile(cli_text, 0x22) == 0x02
