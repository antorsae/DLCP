from __future__ import annotations

import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dlcp_fw.flash import dlcp_ep0_eeprom_shadow_dump as shadow


def test_decode_shadow_with_zero_ram_start() -> None:
    ram = bytearray([0x00] * 0x200)
    ram[0x71] = 0xAA
    ram[0x70] = 0xBB
    ram[0x99] = 0xCC

    rows = shadow.decode_shadow(bytes(ram), ram_start=0x000)
    by_ee = {int(r["eeprom_addr"]): r for r in rows}

    assert int(by_ee[0x00]["present"]) == 1
    assert int(by_ee[0x00]["value"]) == 0xAA

    assert int(by_ee[0x01]["present"]) == 1
    assert int(by_ee[0x01]["value"]) == 0xBB

    assert int(by_ee[0x04]["present"]) == 1
    assert int(by_ee[0x04]["value"]) == 0xCC


def test_decode_shadow_marks_missing_when_out_of_window() -> None:
    # Window 0x100..0x13F excludes all known shadow RAM addresses.
    ram = bytes([0x11] * 0x40)
    rows = shadow.decode_shadow(ram, ram_start=0x100)
    assert all(int(r["present"]) == 0 for r in rows)


def test_render_shadow_table_contains_headers() -> None:
    rows = [
        {
            "eeprom_addr": 0x00,
            "ram_addr": 0x71,
            "symbol": "cfg_00",
            "present": 1,
            "value": 0x5A,
        }
    ]
    text = shadow.render_shadow_table(rows)
    assert "EEP  RAM  Value  Symbol" in text
    assert "00   71" in text
    assert "5A" in text
