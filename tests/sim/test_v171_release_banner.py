"""V1.71 CONTROL boot-splash release banner tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17


pytestmark = pytest.mark.dual_supported


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_release_banner")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def test_v171_boot_splash_renders_baked_release_revision_and_date(v171_hex: Path) -> None:
    try:
        from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"rust dlcp_sim_native facade not importable -- {exc!r}")

    chain = RustChain.from_v17_control_only(str(v171_hex))
    seen: tuple[str, str] | None = None
    for _ in range(240):
        chain.step_ticks(500_000)
        lines = chain.lcd_lines()
        if lines[0].startswith("Firmware V"):
            seen = lines
            if lines[1].startswith("Rev x"):
                break

    assert seen is not None, "V1.71 boot splash never rendered Firmware row"
    assert seen[0].rstrip() == "Firmware V1.71"
    assert seen[1].startswith("Rev x")
    assert len(seen[1]) == 16
    assert seen[1][4] == "x"
    assert seen[1][7] == " "
    assert seen[1][8:].isdigit()
