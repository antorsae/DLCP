from __future__ import annotations

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


def test_dlcp_ep0_large_read_uses_repeated_e7_reads() -> None:
    dev = shadow.DlcpEp0.__new__(shadow.DlcpEp0)
    calls: list[tuple[int, int, bool, int]] = []

    def fake_poke(addr: int, value: int, in_dir: bool, read_len: int = 0) -> bytes:
        calls.append((addr, value, in_dir, read_len))
        return bytes([len(calls)]) * read_len

    dev._poke = fake_poke  # type: ignore[method-assign]

    data = shadow.DlcpEp0.read_exact(dev, 0x210)

    assert len(data) == 0x210
    assert data[:0xFF] == bytes([1]) * 0xFF
    assert data[0xFF : 0x1FE] == bytes([2]) * 0xFF
    assert data[0x1FE :] == bytes([3]) * 0x12
    assert calls == [
        (0xE7, 0xFF, True, 0xFF),
        (0xE7, 0xFF, True, 0xFF),
        (0xE7, 0x12, True, 0x12),
    ]
