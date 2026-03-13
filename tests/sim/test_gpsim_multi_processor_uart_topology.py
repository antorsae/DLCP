from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from dlcp_fw.paths import GPSIM_XTC_BINARY, STOCK_CONTROL_HEX_V14, STOCK_MAIN_HEX


def _link_or_copy(src: Path, dst: Path) -> None:
    try:
        dst.symlink_to(src.resolve())
    except OSError:
        shutil.copyfile(src, dst)


def test_local_gpsim_build_loads_ctl_m0_m1_and_attaches_uart_hops(tmp_path: Path) -> None:
    if not GPSIM_XTC_BINARY.exists():
        pytest.skip("local gpsim wrapper missing")

    control_hex = tmp_path / "control.hex"
    main_hex = tmp_path / "main.hex"
    _link_or_copy(STOCK_CONTROL_HEX_V14, control_hex)
    _link_or_copy(STOCK_MAIN_HEX, main_hex)

    stc_path = tmp_path / "multi_uart_chain.stc"
    stc_path.write_text(
        "\n".join(
            [
                "processor p18f25k20",
                f"load {control_hex} ctl",
                "processor p18f2455",
                f"load {main_hex} m0",
                f"load {main_hex} m1",
                'processor "ctl"',
                "frequency 12000000",
                "frequency",
                'processor "m0"',
                "frequency 16000000",
                "frequency",
                'processor "m1"',
                "frequency 16000000",
                "frequency",
                "processor",
                "node c2m0 m0c m0m1 m1m0",
                "attach c2m0 ctl.portc6 m0.portc7",
                "attach m0c m0.portc6 ctl.portc7",
                "attach m0m1 m0.portc6 m1.portc7",
                "attach m1m0 m1.portc6 m0.portc7",
                "node",
                "quit",
                "",
            ]
        ),
        encoding="ascii",
    )

    cp = subprocess.run(
        [str(GPSIM_XTC_BINARY), "-i", "-c", str(stc_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    cli = cp.stdout + cp.stderr
    assert cp.returncode == 0, cli
    assert "***ERROR" not in cli, cli

    lines = [line.strip() for line in cli.splitlines()]
    idx = lines.index("Processor List")
    assert lines[idx + 1 : idx + 4] == ["ctl", "m0", "m1"], cli
    assert cli.count("Clock frequency: 16 MHz.") >= 2, cli
    assert "Clock frequency: 12 MHz." in cli, cli

    for node_name in ("c2m0", "m0c", "m0m1", "m1m0"):
        assert f"{node_name} voltage" in cli, cli
    assert cli.count("\tportc6") >= 3, cli
    assert cli.count("\tportc7") >= 3, cli
