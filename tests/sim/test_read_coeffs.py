from __future__ import annotations

import json

import pytest

from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo
from dlcp_fw.flash.dlcp_main_flash import DeviceSnapshot, RouteEntry, VersionInfo
from dlcp_fw.flash.read_coeffs import (
    CMD_DIAG_MEMREAD,
    HidMemoryReader,
    TABLE_SIZE,
    CaptureResult,
    _parse_diag_memread_response,
    _pick_device,
    decode_config_name,
    main,
)


def test_decode_config_name_accepts_ascii_with_padding() -> None:
    assert decode_config_name(b"Preset A\x00\xFF\xFF") == "Preset A"


def test_decode_config_name_rejects_non_padding_after_padding() -> None:
    with pytest.raises(ValueError, match="non-padding byte after EEPROM padding"):
        decode_config_name(b"Preset\xFFA")


def test_parse_diag_memread_response_extracts_payload() -> None:
    resp = bytes([CMD_DIAG_MEMREAD, 0x00, 0x03, 0x11, 0x22, 0x33]) + bytes(58)
    assert _parse_diag_memread_response(resp, length=3) == b"\x11\x22\x33"


def test_parse_diag_memread_response_rejects_wrong_echo_with_diag_hint() -> None:
    resp = bytes([0x41, 0x00, 0x01, 0x55]) + bytes(60)
    with pytest.raises(RuntimeError, match="device may not be running the diag memread firmware"):
        _parse_diag_memread_response(resp, length=1)


def test_exchange_skips_unrelated_queued_reports(monkeypatch) -> None:
    reader = object.__new__(HidMemoryReader)
    reader._timeout_ms = 1000
    reader._dev = object()

    writes: list[bytes] = []
    responses = [
        bytes([0x05]) + bytes(63),
        bytes([CMD_DIAG_MEMREAD, 0x00, 0x01, 0xAB]) + bytes(60),
    ]

    monkeypatch.setattr(
        "dlcp_fw.flash.read_coeffs._hid_write64",
        lambda dev, payload: writes.append(payload),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.read_coeffs._hid_read64",
        lambda dev, timeout_ms=1000: responses.pop(0) if responses else None,
    )

    report = bytes([CMD_DIAG_MEMREAD]) + bytes(63)
    resp = HidMemoryReader._exchange(reader, report)

    assert writes == [report]
    assert resp[0] == CMD_DIAG_MEMREAD
    assert resp[3] == 0xAB


def test_exchange_reports_ignored_unrelated_commands_on_timeout(monkeypatch) -> None:
    reader = object.__new__(HidMemoryReader)
    reader._timeout_ms = 1
    reader._dev = object()

    responses = [bytes([0x05]) + bytes(63), None]

    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._hid_write64", lambda dev, payload: None)
    monkeypatch.setattr(
        "dlcp_fw.flash.read_coeffs._hid_read64",
        lambda dev, timeout_ms=1000: responses.pop(0) if responses else None,
    )

    with pytest.raises(RuntimeError, match="ignoring 1 unrelated HID report"):
        HidMemoryReader._exchange(reader, bytes([CMD_DIAG_MEMREAD]) + bytes(63))


def test_pick_device_requires_path_when_multiple_match(monkeypatch) -> None:
    dev_a = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"path-a",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="A",
    )
    dev_b = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"path-b",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="B",
    )
    monkeypatch.setattr("dlcp_fw.flash.read_coeffs.enumerate_devices", lambda vid, pid: [dev_a, dev_b])

    with pytest.raises(RuntimeError, match="multiple HID devices match"):
        _pick_device(0x04D8, 0xFF89, None)

    assert _pick_device(0x04D8, 0xFF89, b"path-b") == dev_b


def test_main_list_does_not_require_preset(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "dlcp_fw.flash.read_coeffs._list_devices_with_mode",
        lambda vid, pid: [{"path": "hid0", "mode": "app"}],
    )

    rc = main(["--list"])
    out = capsys.readouterr().out

    assert rc == 0
    assert json.loads(out) == [{"path": "hid0", "mode": "app"}]


def test_main_requires_preset_unless_list() -> None:
    with pytest.raises(SystemExit, match="--preset is required unless --list is used"):
        main([])


def test_main_capture_prints_banner_and_selected_path(monkeypatch, tmp_path, capsys) -> None:
    info = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"hid-main-1",
        manufacturer_string="Hypex BV",
        product_string="DLCP",
        serial_number="abc123",
    )
    snapshot = DeviceSnapshot(
        mode="app",
        product_string="DLCP",
        manufacturer_string="Hypex BV",
        serial_number="abc123",
        version=VersionInfo(flag=0x03, major=0x03, minor=0x01),
        eeprom_version=None,
        active_config_name="ConfigA",
        active_config_raw=b"ConfigA",
        active_routes=(RouteEntry(channel=1, value=0, label="L"),),
        volume_state=None,
        warnings=(),
    )
    result = CaptureResult(
        preset="A",
        table=b"\x5A" * TABLE_SIZE,
        flash_base=0x5600,
        eeprom_base=0x60,
        name_slot=b"ConfigA" + (b"\xFF" * 23),
        config_name="ConfigA",
    )

    class DummyReader:
        def __init__(self, *, info: HidDeviceInfo, timeout_ms: int) -> None:
            assert info == test_info
            assert timeout_ms == 1000

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    test_info = info
    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._pick_device", lambda vid, pid, path: test_info)
    monkeypatch.setattr(
        "dlcp_fw.flash.read_coeffs._probe_device_snapshot",
        lambda **kwargs: snapshot,
    )
    monkeypatch.setattr("dlcp_fw.flash.read_coeffs.HidMemoryReader", DummyReader)
    monkeypatch.setattr("dlcp_fw.flash.read_coeffs.capture_preset", lambda **kwargs: result)

    out_path = tmp_path / "presetA.bin"
    rc = main(["--preset", "A", "--out", str(out_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "device info:" in out
    assert "version: 3.1" in out
    assert "active config: 'ConfigA'" in out
    assert "hid path: hid-main-1" in out
    assert "capture preset A:" in out
    assert "flash base: 0x5600" in out
    assert "eeprom base: 0x60" in out
    assert "wrote table:" in out
    assert out_path.read_bytes() == b"\x5A" * TABLE_SIZE
