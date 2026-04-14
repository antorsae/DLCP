from __future__ import annotations

import pytest

from dlcp_fw.flash.dlcp_main_flash import (
    DeviceSnapshot,
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

    def _fake_probe_ep0_app_ram(*, vid, pid, path=None):
        seen["path"] = path
        return "ConfigB", (RouteEntry(channel=1, value=1, label="R"),)

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_ep0_app_ram",
        _fake_probe_ep0_app_ram,
    )

    snapshot = _probe_device_snapshot(info=info, vid=0x04D8, pid=0xFF89)

    assert seen["path"] == b"hid-main-b"
    assert snapshot.active_config_name == "ConfigB"
    assert snapshot.active_routes == (RouteEntry(channel=1, value=1, label="R"),)


def test_main_boot_ack_detector_accepts_expected_shapes() -> None:
    assert _looks_like_main_boot_ack(bytes([0x40, 0x00, 0x00]) + bytes(61)) is True
    assert _looks_like_main_boot_ack(bytes([0x00, 0x00, 0x00]) + bytes(61)) is True
    assert _looks_like_main_boot_ack(bytes([0xAA, 0x00, 0x00]) + bytes(61)) is False
