from __future__ import annotations

import pytest

from dlcp_fw.flash.dlcp_main_flash import (
    DeviceSnapshot,
    EepromVersionInfo,
    MAIN_APP_START,
    MAIN_BOOT_END_EXCL,
    MAIN_PROG_END_EXCL,
    PreflightError,
    RouteEntry,
    VersionInfo,
    _looks_like_main_boot_ack,
    bootloader_mismatch_addresses,
    build_main_stream,
    decode_filename_slot,
    decode_route_entries,
    _probe_device_snapshot,
    main,
    parse_intel_hex,
    parse_cmd06_version_response,
    run_preflight,
)
from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo
from dlcp_fw.paths import STOCK_MAIN_COMBINED_HEX
from dlcp_fw.patch.build_v32_release import build_v32_release


def test_build_main_stream_covers_app_window(stock_main_hex) -> None:
    candidate = parse_intel_hex(str(stock_main_hex))
    stream = build_main_stream(candidate)

    assert len(stream) == MAIN_PROG_END_EXCL - MAIN_APP_START
    assert stream[0] == candidate[MAIN_APP_START]
    assert stream[-1] == candidate.get(MAIN_PROG_END_EXCL - 1, 0xFF)


def test_build_main_stream_fills_missing_bytes_with_ff(stock_main_hex) -> None:
    candidate = parse_intel_hex(str(stock_main_hex))
    target = MAIN_APP_START + 0x123
    candidate.pop(target, None)

    stream = build_main_stream(candidate)
    assert stream[target - MAIN_APP_START] == 0xFF


def test_preflight_accepts_app_only_hex_without_bootloader_bytes(stock_main_hex) -> None:
    candidate = parse_intel_hex(str(stock_main_hex))
    reference = parse_intel_hex(str(STOCK_MAIN_COMBINED_HEX))

    preflight = run_preflight(
        hex_mem=candidate,
        bootloader_ref_mem=reference,
        require_bootloader_match=True,
    )
    assert preflight["bootloader_match"] is True
    assert preflight["bootloader_bytes_present"] == 0


def test_preflight_rejects_explicit_bootloader_drift(stock_main_hex) -> None:
    candidate = parse_intel_hex(str(stock_main_hex))
    reference = parse_intel_hex(str(STOCK_MAIN_COMBINED_HEX))
    candidate_mut = dict(candidate)
    candidate_mut[0x0000] = (reference.get(0x0000, 0xFF) ^ 0x01) & 0xFF

    with pytest.raises(PreflightError, match="bootloader bytes differ from reference"):
        run_preflight(
            hex_mem=candidate_mut,
            bootloader_ref_mem=reference,
            require_bootloader_match=True,
        )


def test_bootloader_mismatch_addresses_only_reports_explicit_bytes(stock_main_hex) -> None:
    candidate = parse_intel_hex(str(stock_main_hex))
    reference = parse_intel_hex(str(STOCK_MAIN_COMBINED_HEX))
    target = MAIN_BOOT_END_EXCL - 0x10
    candidate[target] = (reference.get(target, 0xFF) ^ 0x80) & 0xFF

    mismatches = bootloader_mismatch_addresses(candidate, reference)
    assert mismatches == [target]


def test_cli_blocks_unsafe_flags_without_force(stock_main_hex) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--hex", str(stock_main_hex), "--preflight-only", "--no-verify"])
    assert exc.value.code == 2


def test_cli_allows_unsafe_when_explicitly_forced(stock_main_hex) -> None:
    rc = main(["--hex", str(stock_main_hex), "--preflight-only", "--no-verify", "--force-unsafe"])
    assert rc == 0


def test_parse_cmd06_version_response_extracts_fields() -> None:
    version = parse_cmd06_version_response(bytes([0x06, 0x03, 0x03, 0x01]) + bytes(60))
    assert version == VersionInfo(flag=0x03, major=0x03, minor=0x01)


def test_parse_cmd06_version_response_accepts_leading_zero_prefix() -> None:
    version = parse_cmd06_version_response(bytes([0x00, 0x06, 0x03, 0x03, 0x01]) + bytes(59))
    assert version == VersionInfo(flag=0x03, major=0x03, minor=0x01)


def test_parse_cmd06_version_response_rejects_wrong_echo() -> None:
    with pytest.raises(RuntimeError, match="unexpected cmd 0x06 echo"):
        parse_cmd06_version_response(bytes([0x00, 0x03, 0x03, 0x01]) + bytes(60))


def test_decode_filename_slot_strips_padding() -> None:
    assert decode_filename_slot(b"ConfigA\x00\xff\xff") == "ConfigA"
    assert decode_filename_slot(b"\xff" * 8) == ""


def test_decode_route_entries_labels_known_and_unknown() -> None:
    routes = decode_route_entries(bytes([0, 1, 2, 3, 4, 0xAA]))
    assert routes == (
        RouteEntry(channel=1, value=0, label="L"),
        RouteEntry(channel=2, value=1, label="R"),
        RouteEntry(channel=3, value=2, label="L+R"),
        RouteEntry(channel=4, value=3, label="L-R"),
        RouteEntry(channel=5, value=4, label="R-L"),
        RouteEntry(channel=6, value=0xAA, label="0xAA"),
    )


def test_cli_info_only_does_not_require_hex(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._pick_device",
        lambda vid, pid, path: object(),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_device_snapshot",
        lambda **kwargs: DeviceSnapshot(
            mode="app",
            product_string="DLCP",
            manufacturer_string="Hypex",
            serial_number="123",
            version=VersionInfo(flag=0x03, major=0x03, minor=0x01),
            eeprom_version=EepromVersionInfo(major=0x03, minor=0x01, revision=0x31),
            active_config_name="ConfigA",
            active_config_raw=b"ConfigA",
            active_routes=(RouteEntry(channel=1, value=0, label="L"),),
            warnings=(),
        ),
    )

    rc = main(["--info-only"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "device info:" in out
    assert "version: 3.1" in out
    assert "active config: 'ConfigA'" in out


def test_probe_device_snapshot_forwards_selected_path_to_ep0(monkeypatch) -> None:
    info = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"hid-main-b",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="SER-B",
    )
    seen: dict[str, object] = {}

    class FakeDev:
        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._open_hid",
        lambda path: FakeDev(),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_cmd06_version",
        lambda dev: VersionInfo(flag=0x03, major=0x03, minor=0x01),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_device_eeprom_version",
        lambda **kwargs: EepromVersionInfo(major=0x03, minor=0x01, revision=0x31),
    )

    def _fake_probe_ep0_app_ram(*, vid, pid, path=None):
        seen["path"] = path
        return "ConfigB", (RouteEntry(channel=1, value=1, label="R"),)

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_ep0_app_ram",
        _fake_probe_ep0_app_ram,
    )

    snapshot = _probe_device_snapshot(info=info, vid=0x04D8, pid=0xFF89)

    assert seen["path"] == b"hid-main-b"
    assert snapshot.eeprom_version == EepromVersionInfo(major=0x03, minor=0x01, revision=0x31)
    assert snapshot.active_config_name == "ConfigB"
    assert snapshot.active_routes == (RouteEntry(channel=1, value=1, label="R"),)


def test_probe_device_snapshot_includes_eeprom_revision(monkeypatch) -> None:
    info = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"hid-main-a",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="SER-A",
    )

    class FakeDev:
        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._open_hid",
        lambda path: FakeDev(),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_cmd06_version",
        lambda dev: VersionInfo(flag=0x03, major=0x03, minor=0x02),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_device_eeprom_version",
        lambda **kwargs: EepromVersionInfo(major=0x03, minor=0x02, revision=0x38),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_ep0_app_ram",
        lambda **kwargs: ("ConfigA", (RouteEntry(channel=1, value=0, label="L"),)),
    )

    snapshot = _probe_device_snapshot(info=info, vid=0x04D8, pid=0xFF89)

    assert snapshot.eeprom_version == EepromVersionInfo(major=0x03, minor=0x02, revision=0x38)


def test_cli_warns_when_device_revision_is_same_or_newer(monkeypatch, stock_main_hex, capsys) -> None:
    initial = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"hid-main-a",
        manufacturer_string="Hypex",
        product_string="bootl",
        serial_number="SER-A",
    )

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._pick_device",
        lambda vid, pid, path, route_label=None: initial,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_device_snapshot",
        lambda **kwargs: DeviceSnapshot(
            mode="bootloader",
            product_string="bootl",
            manufacturer_string="Hypex",
            serial_number="SER-A",
            version=VersionInfo(flag=0x03, major=0x03, minor=0x02),
            eeprom_version=EepromVersionInfo(major=0x03, minor=0x02, revision=0xFF),
            active_config_name=None,
            active_config_raw=None,
            active_routes=None,
            warnings=(),
        ),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._open_hid",
        lambda path: type("FakeDev", (), {"close": lambda self: None})(),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._hid_write64",
        lambda dev, report: None,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._hid_read64",
        lambda dev, timeout_ms=0: bytes([0x40, 0x00, 0x00]) + bytes(61),
    )

    rc = main(
        [
            "--hex",
            str(stock_main_hex),
            "--no-info",
            "--skip-switch",
            "--no-verify",
            "--force-unsafe",
            "--pace-ms",
            "0",
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "WARNING: device firmware is the same or newer than the target hex" in out


def test_pick_device_auto_resolves_uniform_left_route(monkeypatch) -> None:
    left = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"left",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="LEFT",
    )
    right = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"right",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="RIGHT",
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash.enumerate_devices",
        lambda vid, pid: [left, right],
    )

    def _fake_probe(*, vid, pid, path=None):
        label = "L" if path == b"left" else "R"
        return "Cfg", tuple(
            RouteEntry(channel=index + 1, value=0 if label == "L" else 1, label=label)
            for index in range(6)
        )

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_ep0_app_ram",
        _fake_probe,
    )

    from dlcp_fw.flash.dlcp_main_flash import _pick_device

    assert _pick_device(0x04D8, 0xFF89, None, route_label="L") == left


def test_pick_device_auto_resolve_requires_unambiguous_match(monkeypatch) -> None:
    left_a = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"left-a",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="LEFT-A",
    )
    left_b = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"left-b",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="LEFT-B",
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash.enumerate_devices",
        lambda vid, pid: [left_a, left_b],
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_ep0_app_ram",
        lambda **kwargs: (
            "Cfg",
            tuple(RouteEntry(channel=index + 1, value=0, label="L") for index in range(6)),
        ),
    )

    from dlcp_fw.flash.dlcp_main_flash import _pick_device

    with pytest.raises(RuntimeError, match="2 devices report all channels L"):
        _pick_device(0x04D8, 0xFF89, None, route_label="L")


def test_main_boot_ack_detector_accepts_expected_shapes() -> None:
    assert _looks_like_main_boot_ack(bytes([0x40, 0x00, 0x00]) + bytes(61)) is True
    assert _looks_like_main_boot_ack(bytes([0x00, 0x00, 0x00]) + bytes(61)) is True
    assert _looks_like_main_boot_ack(bytes([0xAA, 0x00, 0x00]) + bytes(61)) is False


def test_build_v32_release_rolls_back_source_and_hex_on_assemble_failure(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_main_v32.asm"
    original_text = (
        "org 0xF00000\n"
        "        db      0x03, 0x02, 0x38\n"
    )
    asm_path.write_text(original_text, encoding="utf-8")
    output_hex = tmp_path / "DLCP_Firmware_V3.2.hex"
    output_hex.write_text(":00000001FF\n", encoding="ascii")

    def _boom(*args, **kwargs):
        raise RuntimeError("gpasm boom")

    monkeypatch.setattr("dlcp_fw.patch.build_v32_release.assemble_v30", _boom)

    with pytest.raises(RuntimeError, match="gpasm boom"):
        build_v32_release(asm_path=asm_path, output_hex=output_hex)

    assert asm_path.read_text(encoding="utf-8") == original_text
    assert output_hex.read_text(encoding="ascii") == ":00000001FF\n"
