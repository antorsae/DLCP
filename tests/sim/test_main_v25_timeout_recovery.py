from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from dlcp_fw.sim.gpsim import gpsim_available, require_gpsim_binary

def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _did_hit_break(cli_text: str, addr: int) -> bool:
    pat = rf"line_{addr:04x}\(0x{addr:04x}\)"
    return bool(re.search(pat, cli_text, flags=re.IGNORECASE))


def _run_probe(
    main_hex: Path,
    lines: list[str],
    *,
    timeout_s: float = 20.0,
) -> str:
    with tempfile.TemporaryDirectory(prefix="main_v25_timeout_probe_") as td:
        tdp = Path(td)
        cli_path = tdp / "probe_cli.txt"
        stc_path = tdp / "probe.stc"
        stc_lines = [
            "processor p18f2455",
            f"load {main_hex}",
            *lines,
            "quit",
            "",
        ]
        stc_path.write_text("\n".join(stc_lines), encoding="ascii")
        gpsim_bin = require_gpsim_binary()
        cp = subprocess.run(
            [gpsim_bin, "-i", "-c", str(stc_path)],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
        cli_text = cp.stdout + cp.stderr
        cli_path.write_text(cli_text, encoding="utf-8")
        if cp.returncode != 0:
            raise RuntimeError(f"gpsim probe exited {cp.returncode}; inspect {cli_path}")
        return cli_text


@pytest.mark.gpsim
@pytest.mark.slow
def test_v25_i2c_write_collision_path_hits_local_mssp_recover_first(patched_main_hex: Path) -> None:
    _require_gpsim()

    cli_text = _run_probe(
        patched_main_hex,
        [
            "reg(0xFC6)=0x80",
            "reg(0xFE8)=0x68",
            "pc=0x3E68",
            "break e 0x54AE",
            "run",
        ],
    )

    assert _did_hit_break(cli_text, 0x54AE)
