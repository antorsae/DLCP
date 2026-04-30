"""Static version-label checks for CONTROL V1.64b."""

from __future__ import annotations

from pathlib import Path

from intelhex import IntelHex

from dlcp_fw.paths import PATCHED_CONTROL_HEX_V164B

import pytest

# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.  Mark the
# whole module dual_supported so DLCP_SIM_BACKEND={rust,dual} does
# not auto-skip them.
pytestmark = pytest.mark.dual_supported


def _read_eeprom_version(hex_path: Path) -> tuple[int, int, int]:
    ih = IntelHex(str(hex_path))
    return (ih[0xF00070], ih[0xF00071], ih[0xF00072])


def test_v164b_control_eeprom_version_tuple() -> None:
    assert PATCHED_CONTROL_HEX_V164B.exists(), f"missing: {PATCHED_CONTROL_HEX_V164B.name}"
    assert _read_eeprom_version(PATCHED_CONTROL_HEX_V164B) == (0x01, 0x06, 0x34)


def test_v164b_control_display_version_literal() -> None:
    assert PATCHED_CONTROL_HEX_V164B.exists(), f"missing: {PATCHED_CONTROL_HEX_V164B.name}"
    ih = IntelHex(str(PATCHED_CONTROL_HEX_V164B))
    # At 0x1152 we patch `movlw 0x3F` for the V1.64b display tuple.
    assert ih[0x1152] == 0x3F and ih[0x1153] == 0x0E
