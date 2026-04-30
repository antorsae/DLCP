from __future__ import annotations

import json

import pytest

from dlcp_fw.flash.dlcp_hfd_upload import (
    NAME_LEN,
    SLOT_COUNT,
    SLOT_PAYLOAD_SIZE,
    SLOT_SIZE,
    TABLE_SIZE,
    UPLOAD_CMD_FIRST,
    UPLOAD_CMD_LAST,
    _build_upload_reports,
    _resolve_name_slot,
    _transmitted_diff_offset,
    _untransmitted_diff_offset,
    main,
)
from dlcp_fw.flash.dlcp_main_flash import DeviceSnapshot, RouteEntry, VersionInfo


# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.  Mark the
# whole module dual_supported so DLCP_SIM_BACKEND={rust,dual} does
# not auto-skip them.
pytestmark = pytest.mark.dual_supported


def _make_table() -> bytes:
    data = bytearray(TABLE_SIZE)
    for idx in range(SLOT_COUNT):
        base = idx * SLOT_SIZE
        data[base + 0] = 0x01
        data[base + 1] = idx & 0xFF
        data[base + 2] = SLOT_PAYLOAD_SIZE
        data[base + 3] = 0x00
        for off in range(4, SLOT_SIZE):
            data[base + off] = (idx + off) & 0xFF
    for idx in range(SLOT_COUNT * SLOT_SIZE, TABLE_SIZE):
        data[idx] = 0xFF
    return bytes(data)


def test_build_upload_reports_extracts_slot_payloads() -> None:
    table = _make_table()
    reports = _build_upload_reports(table)

    assert len(reports) == SLOT_COUNT
    assert reports[0][0] == UPLOAD_CMD_FIRST
    assert reports[-1][0] == UPLOAD_CMD_LAST
    assert [cmd for cmd, _ in reports[1:6]] == [0x08, 0x09, 0x0A, 0x0B, 0x08]

    for idx, (cmd, report) in enumerate(reports[:6]):
        slot = table[idx * SLOT_SIZE : (idx + 1) * SLOT_SIZE]
        assert len(report) == 64
        assert report[0] == cmd
        assert report[1:4] == b"\x00\x00\x00"
        assert report[4 : 4 + SLOT_PAYLOAD_SIZE] == slot[4:24]


def test_transmitted_diff_ignores_headers_and_tail() -> None:
    expected = bytearray(_make_table())
    got = bytearray(expected)

    got[0] ^= 0xFF
    got[SLOT_SIZE + 3] ^= 0xFF
    got[-1] ^= 0xFF

    assert _transmitted_diff_offset(bytes(got), bytes(expected)) is None
    assert _untransmitted_diff_offset(bytes(got), bytes(expected)) == 0


def test_transmitted_diff_reports_payload_mismatch() -> None:
    expected = bytearray(_make_table())
    got = bytearray(expected)

    got[4] ^= 0xFF

    assert _transmitted_diff_offset(bytes(got), bytes(expected)) == 4


def test_resolve_name_slot_prefers_explicit_name(tmp_path) -> None:
    table_path = tmp_path / "presetA.bin"
    table_path.write_bytes(_make_table())
    json_path = tmp_path / "presetA.json"
    json_path.write_text(
        json.dumps(
            {
                "config_name": "FROMJSON",
                "config_name_raw_hex": ("46" * NAME_LEN),
            }
        ),
        encoding="ascii",
    )

    slot, name = _resolve_name_slot(
        table_path=table_path,
        explicit_name="EXPLICIT",
        explicit_json=json_path,
    )
    assert name == "EXPLICIT"
    assert slot.startswith(b"EXPLICIT")


def test_cli_info_only_does_not_require_table(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._pick_device",
        lambda vid, pid, path: object(),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._probe_device_snapshot",
        lambda **kwargs: DeviceSnapshot(
            mode="app",
            product_string="DLCP",
            manufacturer_string="Hypex",
            serial_number="123",
            version=VersionInfo(flag=0x03, major=0x03, minor=0x01),
            eeprom_version=None,
            active_config_name="ConfigA",
            active_config_raw=b"ConfigA",
            active_routes=(RouteEntry(channel=1, value=0, label="L"),),
            volume_state=None,
            warnings=(),
        ),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._print_device_snapshot",
        lambda title, snapshot: print(title),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._probe_active_preset",
        lambda **kwargs: "A",
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._path_text",
        lambda path: "fake-path",
    )

    rc = main(["--info-only"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "device info:" in out
    assert "active preset: A" in out


def test_cli_expect_active_mismatch_raises(monkeypatch, tmp_path) -> None:
    table_path = tmp_path / "presetA.bin"
    table_path.write_bytes(_make_table())

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._pick_device",
        lambda vid, pid, path: object(),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._probe_device_snapshot",
        lambda **kwargs: DeviceSnapshot(
            mode="app",
            product_string="DLCP",
            manufacturer_string="Hypex",
            serial_number="123",
            version=VersionInfo(flag=0x03, major=0x03, minor=0x01),
            eeprom_version=None,
            active_config_name="",
            active_config_raw=b"",
            active_routes=(RouteEntry(channel=1, value=0, label="L"),),
            volume_state=None,
            warnings=(),
        ),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._print_device_snapshot",
        lambda title, snapshot: None,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._probe_active_preset",
        lambda **kwargs: "B",
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._path_text",
        lambda path: "fake-path",
    )

    with pytest.raises(RuntimeError, match="active preset mismatch"):
        main(["--table", str(table_path), "--expect-active", "A"])


def test_cli_upload_uses_sidecar_name_and_runs_verify(monkeypatch, tmp_path, capsys) -> None:
    table_path = tmp_path / "presetA.bin"
    table = _make_table()
    table_path.write_bytes(table)
    json_path = tmp_path / "presetA.json"
    slot = b"LX521.4 22MG10F-v5" + (b"\xFF" * (NAME_LEN - len("LX521.4 22MG10F-v5")))
    json_path.write_text(
        json.dumps(
            {
                "config_name": "LX521.4 22MG10F-v5",
                "config_name_raw_hex": slot.hex(),
            }
        ),
        encoding="ascii",
    )

    stream_calls: list[list[int]] = []

    class FakeDev:
        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._pick_device",
        lambda vid, pid, path: HidInfo(path=b"fake"),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._probe_device_snapshot",
        lambda **kwargs: DeviceSnapshot(
            mode="app",
            product_string="DLCP",
            manufacturer_string="Hypex",
            serial_number="123",
            version=VersionInfo(flag=0x03, major=0x03, minor=0x01),
            eeprom_version=None,
            active_config_name="",
            active_config_raw=b"",
            active_routes=(RouteEntry(channel=1, value=0, label="L"),),
            volume_state=None,
            warnings=(),
        ),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._print_device_snapshot",
        lambda title, snapshot: print(title),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._probe_active_preset",
        lambda **kwargs: "A",
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._path_text",
        lambda path: "fake-path",
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._open_hid",
        lambda path: FakeDev(),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._stream_upload",
        lambda dev, **kwargs: stream_calls.append([cmd for cmd, _ in kwargs["reports"]]),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._cmd03_write_filename_slot",
        lambda dev, name_slot: name_slot,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._force_active_filename_persist",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._verify_uploaded_active_bank",
        lambda **kwargs: (True, []),
    )

    rc = main(["--table", str(table_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert stream_calls
    assert stream_calls[0][0] == UPLOAD_CMD_FIRST
    assert stream_calls[0][-1] == UPLOAD_CMD_LAST
    assert "config name: 'LX521.4 22MG10F-v5'" in out
    assert "diag memread transmitted-byte check: passed" in out
    assert "upload complete" in out


def test_cli_forwards_explicit_path_to_ep0_helpers(monkeypatch, tmp_path) -> None:
    table_path = tmp_path / "presetA.bin"
    table_path.write_bytes(_make_table())
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._pick_device",
        lambda vid, pid, path: HidInfo(path=b"hid-main-b"),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._probe_device_snapshot",
        lambda **kwargs: DeviceSnapshot(
            mode="app",
            product_string="DLCP",
            manufacturer_string="Hypex",
            serial_number="123",
            version=VersionInfo(flag=0x03, major=0x03, minor=0x01),
            eeprom_version=None,
            active_config_name="",
            active_config_raw=b"",
            active_routes=(RouteEntry(channel=1, value=0, label="L"),),
            volume_state=None,
            warnings=(),
        ),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._print_device_snapshot",
        lambda title, snapshot: None,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._probe_active_preset",
        lambda **kwargs: seen.__setitem__("probe_path", kwargs.get("path")) or "A",
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._open_hid",
        lambda path: type("FakeDev", (), {"close": lambda self: None})(),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._stream_upload",
        lambda dev, **kwargs: None,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._cmd03_write_filename_slot",
        lambda dev, name_slot: name_slot,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._force_active_filename_persist",
        lambda **kwargs: seen.__setitem__("persist_path", kwargs.get("path")) or True,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_hfd_upload._verify_uploaded_active_bank",
        lambda **kwargs: (True, []),
    )

    rc = main(["--path", "hid-main-b", "--table", str(table_path), "--name", "ConfigB"])

    assert rc == 0
    assert seen["probe_path"] == b"hid-main-b"
    assert seen["persist_path"] == b"hid-main-b"


class HidInfo:
    def __init__(self, path: bytes | None) -> None:
        self.vendor_id = 0x04D8
        self.product_id = 0xFF89
        self.path = path
        self.manufacturer_string = "Hypex"
        self.product_string = "DLCP"
        self.serial_number = "123"
