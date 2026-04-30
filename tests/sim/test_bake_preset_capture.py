from __future__ import annotations

import json
from pathlib import Path

from dlcp_fw.patch.bake_preset_capture import main
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex

import pytest

# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.  Mark the
# whole module dual_supported so DLCP_SIM_BACKEND={rust,dual} does
# not auto-skip them.
pytestmark = pytest.mark.dual_supported


def test_bake_capture_patches_flash_and_eeprom(tmp_path: Path) -> None:
    base_hex = tmp_path / "base.hex"
    out_hex = tmp_path / "baked.hex"
    capture = tmp_path / "preset_a.bin"
    capture_meta = tmp_path / "preset_a.json"

    write_intel_hex(base_hex, {0x1000: 0x00})

    table = bytes((i & 0xFF) for i in range(0x0A00))
    capture.write_bytes(table)
    capture_meta.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "A",
                "config_name": "ALPHA-A",
                "config_name_raw_hex": (b"ALPHA-A" + (b"\xFF" * 23)).hex(),
            }
        ),
        encoding="ascii",
    )

    rc = main([
        "--base-hex", str(base_hex),
        "--capture-a", str(capture),
        "--out", str(out_hex),
    ])
    assert rc == 0

    mem = parse_intel_hex(out_hex)
    assert bytes(mem.get(0x5600 + i, 0xFF) for i in range(0x20)) == table[:0x20]
    assert bytes(mem.get(0xF00060 + i, 0xFF) for i in range(7)) == b"ALPHA-A"
