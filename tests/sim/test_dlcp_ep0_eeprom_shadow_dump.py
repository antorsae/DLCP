from __future__ import annotations

import json

import pytest

from dlcp_fw.flash import dlcp_ep0_eeprom_shadow_dump as shadow
from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo


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


def test_decode_macos_location_id_extracts_bus_and_ports() -> None:
    assert shadow._decode_macos_location_id(0x01120000) == (0x01, (1, 2))
    assert shadow._decode_macos_location_id(0x03112000) == (0x03, (1, 1, 2))


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


def test_capture_ram_forwards_explicit_path(monkeypatch, tmp_path) -> None:
    seen: dict[str, object] = {}

    class FakeEp0:
        def __init__(self, vid: int, pid: int, path: bytes | None = None) -> None:
            seen["path"] = path
            self.ptr = 0

        def set_pointer(self, addr16: int) -> None:
            self.ptr = addr16

        def read_exact(self, n: int) -> bytes:
            return bytes([0x5A] * n)

    monkeypatch.setattr(shadow, "DlcpEp0", FakeEp0)

    out_path = tmp_path / "ram.bin"
    data = shadow.capture_ram(
        out_path=out_path,
        vid=0x04D8,
        pid=0xFF89,
        path=b"hid-main-b",
        ram_start=0x000,
        ram_size=4,
        chunk=2,
    )

    assert data == b"\x5A\x5A\x5A\x5A"
    assert out_path.read_bytes() == data
    assert seen["path"] == b"hid-main-b"


def test_capture_list_outputs_matching_devices(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        shadow,
        "list_matching_devices_json",
        lambda vid, pid: [{"path": "hid-main-b", "serial_number": "B"}],
    )

    rc = shadow.main(["capture", "--list"])

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == [{"path": "hid-main-b", "serial_number": "B"}]


def test_resolve_usb_device_matches_selected_hid_serial(monkeypatch) -> None:
    dev_a = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"path-a",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="SER-A",
    )
    dev_b = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"path-b",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="SER-B",
    )

    class FakeUsbDev:
        def __init__(self, serial_number: str) -> None:
            self.serial_number = serial_number

    usb_a = FakeUsbDev("SER-A")
    usb_b = FakeUsbDev("SER-B")

    class FakeUsbCore:
        @staticmethod
        def find(*, find_all: bool, idVendor: int, idProduct: int):
            assert find_all is True
            return [usb_a, usb_b]

    monkeypatch.setattr(shadow, "enumerate_devices", lambda vid, pid: [dev_a, dev_b])

    result = shadow._resolve_usb_device(
        usb_core=FakeUsbCore(),
        vid=0x04D8,
        pid=0xFF89,
        path=b"path-b",
        hid_info=None,
    )

    assert result is usb_b


def test_resolve_usb_device_accepts_single_usb_match_without_hid_lookup(monkeypatch) -> None:
    usb_dev = object()

    class FakeUsbCore:
        @staticmethod
        def find(*, find_all: bool, idVendor: int, idProduct: int):
            assert find_all is True
            return [usb_dev]

    monkeypatch.setattr(
        shadow,
        "_pick_hid_device_info",
        lambda vid, pid, path: (_ for _ in ()).throw(AssertionError("HID lookup should not run")),
    )

    result = shadow._resolve_usb_device(
        usb_core=FakeUsbCore(),
        vid=0x04D8,
        pid=0xFF89,
        path=None,
        hid_info=None,
    )

    assert result is usb_dev


def test_resolve_usb_device_rejects_ambiguous_serialless_multi_device(monkeypatch) -> None:
    dev_a = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"path-a",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="",
    )
    dev_b = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"path-b",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="",
    )

    class FakeUsbCore:
        @staticmethod
        def find(*, find_all: bool, idVendor: int, idProduct: int):
            assert find_all is True
            return [object(), object()]

    monkeypatch.setattr(shadow, "enumerate_devices", lambda vid, pid: [dev_a, dev_b])

    with pytest.raises(RuntimeError, match="does not expose a usable serial number"):
        shadow._resolve_usb_device(
            usb_core=FakeUsbCore(),
            vid=0x04D8,
            pid=0xFF89,
            path=b"path-b",
            hid_info=None,
        )


def test_resolve_usb_device_matches_selected_hid_topology_when_serial_missing(monkeypatch) -> None:
    dev_a = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"DevSrvsID:111",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="",
    )
    dev_b = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"DevSrvsID:222",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="",
    )

    class FakeUsbDev:
        def __init__(self, bus: int, port_numbers: tuple[int, ...]) -> None:
            self.bus = bus
            self.port_numbers = port_numbers
            self.serial_number = None

    usb_a = FakeUsbDev(1, (1, 2))
    usb_b = FakeUsbDev(3, (1, 1, 2))

    class FakeUsbCore:
        @staticmethod
        def find(*, find_all: bool, idVendor: int, idProduct: int):
            assert find_all is True
            return [usb_a, usb_b]

    monkeypatch.setattr(shadow, "enumerate_devices", lambda vid, pid: [dev_a, dev_b])
    monkeypatch.setattr(
        shadow,
        "_macos_location_id_for_hid_path",
        lambda *, vid, pid, path: 0x03112000 if path == b"DevSrvsID:222" else 0x01120000,
    )

    result = shadow._resolve_usb_device(
        usb_core=FakeUsbCore(),
        vid=0x04D8,
        pid=0xFF89,
        path=b"DevSrvsID:222",
        hid_info=None,
    )

    assert result is usb_b
