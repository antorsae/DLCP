from __future__ import annotations

import json
from pathlib import Path

import pytest

from dlcp_fw.flash.dlcp_main_flash import (
    ACTIVE_REAPPLY_MASK,
    CMD03_FILENAME_READ_SUBCMD,
    CMD03_FILENAME_WRITE_SUBCMD,
    EVENT_DIRTY_SERVICE_MASK,
    EVENT_FLAGS_ADDR,
    EVENT_ROUTE_APPLY_MASK,
    FILENAME_LEN,
    FILENAME_DIRTY_MASK,
    PRESET_A_FLASH_BASE,
    PRESET_B_FLASH_BASE,
    PRESET_B_FLASH_BASE_V24_TO_V28,
    PRESET_TABLE_SIZE,
    ROUTE_DIRTY_FLAGS_ADDR,
    ROUTE_LEN,
    ROUTE_RAM_BASE,
    ROUTE_SOURCE_RAM_BASE,
    EEPROM_ROUTE_DIRTY_MASK,
    _cmd03_read_filename_slot,
    _cmd03_write_filename_slot,
    _apply_all_channel_mapping,
    _force_active_filename_persist,
    _load_capture_overlay,
    _name_slot_to_cmd03_payload,
    _parse_cmd03_filename_response,
    _switch_active_preset_ep0,
    main,
)
from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo
from dlcp_fw.sim.hexio import write_intel_hex


# All tests in this module are backend-agnostic (static source/hex
# analysis, flash-tool CLI plumbing, semantic-guard regex matchers).
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
pytestmark = pytest.mark.dual_supported


def _write_minimal_main_hex(path: Path, *, major: int, minor: int, flag: int = 0x03) -> None:
    addr = 0x240C
    mem = {
        0x1000: 0x11,
        addr + 0: flag,
        addr + 1: 0x0E,
        addr + 2: 0x01,
        addr + 3: 0x01,
        addr + 4: 0x5B,
        addr + 5: 0x6F,
        addr + 6: major,
        addr + 7: 0x0E,
        addr + 8: 0x5C,
        addr + 9: 0x6F,
        addr + 10: minor,
        addr + 11: 0x0E,
        addr + 12: 0x5D,
        addr + 13: 0x6F,
    }
    write_intel_hex(path, mem)


def test_load_capture_overlay_reads_sidecar_json(tmp_path: Path) -> None:
    capture = tmp_path / "presetA.bin"
    sidecar = tmp_path / "presetA.json"
    table = bytes((i & 0xFF) for i in range(PRESET_TABLE_SIZE))
    name_slot = b"ALPHA-A" + (b"\xFF" * (FILENAME_LEN - 7))

    capture.write_bytes(table)
    sidecar.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "A",
                "config_name": "ALPHA-A",
                "config_name_raw_hex": name_slot.hex(),
            }
        ),
        encoding="ascii",
    )

    overlay = _load_capture_overlay(
        capture_path=capture,
        explicit_meta=None,
        name_override=None,
        preset="A",
    )

    assert overlay.preset == "A"
    assert overlay.table == table
    assert overlay.name_slot == name_slot
    assert overlay.config_name == "ALPHA-A"
    assert overlay.flash_base == PRESET_A_FLASH_BASE


def test_load_capture_overlay_reads_preset_b_sidecar_json(tmp_path: Path) -> None:
    capture = tmp_path / "presetB.bin"
    sidecar = tmp_path / "presetB.json"
    table = bytes(((0x80 + i) & 0xFF) for i in range(PRESET_TABLE_SIZE))
    name_slot = b"BRAVO-B" + (b"\xFF" * (FILENAME_LEN - 7))

    capture.write_bytes(table)
    sidecar.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "B",
                "config_name": "BRAVO-B",
                "config_name_raw_hex": name_slot.hex(),
            }
        ),
        encoding="ascii",
    )

    overlay = _load_capture_overlay(
        capture_path=capture,
        explicit_meta=None,
        name_override=None,
        preset="B",
        flash_base=PRESET_B_FLASH_BASE,
    )

    assert overlay.preset == "B"
    assert overlay.table == table
    assert overlay.name_slot == name_slot
    assert overlay.config_name == "BRAVO-B"
    assert overlay.flash_base == PRESET_B_FLASH_BASE


def test_name_slot_to_cmd03_payload_maps_ff_padding_to_zero() -> None:
    name_slot = b"CONFIG-A" + (b"\xFF" * (FILENAME_LEN - 8))
    payload = _name_slot_to_cmd03_payload(name_slot)

    assert payload[:8] == b"CONFIG-A"
    assert payload[8:] == b"\x00" * (FILENAME_LEN - 8)


def test_parse_cmd03_filename_response_extracts_slot() -> None:
    slot = b"FILE-A" + (b"\xFF" * (FILENAME_LEN - 6))
    resp = bytes([0x03, CMD03_FILENAME_READ_SUBCMD]) + slot + bytes(64 - 2 - FILENAME_LEN)

    assert _parse_cmd03_filename_response(resp, subcmd=CMD03_FILENAME_READ_SUBCMD) == slot


def test_cmd03_read_retries_after_stale_post_flash_reply(monkeypatch) -> None:
    slot = b"FILE-A" + (b"\xFF" * (FILENAME_LEN - 6))
    responses = [
        bytes([0x06, 0x03, 0x03, 0x01]) + bytes(60),
        bytes([0x03, CMD03_FILENAME_READ_SUBCMD]) + slot + bytes(64 - 2 - FILENAME_LEN),
    ]

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._cmd03_exchange_filename",
        lambda *args, **kwargs: responses.pop(0),
    )
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.time.sleep", lambda _: None)

    assert _cmd03_read_filename_slot(object()) == slot
    assert responses == []


def test_cmd03_write_retries_after_stale_post_flash_reply(monkeypatch) -> None:
    slot = b"ALPHA-A" + (b"\xFF" * (FILENAME_LEN - 7))
    responses = [
        bytes([0x06, 0x03, 0x03, 0x01]) + bytes(60),
        bytes([0x03, CMD03_FILENAME_WRITE_SUBCMD]) + slot + bytes(64 - 2 - FILENAME_LEN),
        bytes([0x03, CMD03_FILENAME_READ_SUBCMD]) + slot + bytes(64 - 2 - FILENAME_LEN),
    ]

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._cmd03_exchange_filename",
        lambda *args, **kwargs: responses.pop(0),
    )
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.time.sleep", lambda _: None)

    assert _cmd03_write_filename_slot(object(), name_slot=slot) == slot
    assert responses == []


def test_cli_capture_a_overlays_stream_before_flash(monkeypatch, tmp_path: Path) -> None:
    base_hex = tmp_path / "base.hex"
    capture = tmp_path / "presetA.bin"
    sidecar = tmp_path / "presetA.json"
    table = bytes((0xA0 + i) & 0xFF for i in range(PRESET_TABLE_SIZE))

    _write_minimal_main_hex(base_hex, major=0x02, minor=0x03)
    capture.write_bytes(table)
    sidecar.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "A",
                "config_name": "ALPHA-A",
                "config_name_raw_hex": (b"ALPHA-A" + (b"\xFF" * (FILENAME_LEN - 7))).hex(),
            }
        ),
        encoding="ascii",
    )

    seen: dict[str, object] = {}

    def fake_flash_main(**kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.flash_main", fake_flash_main)

    rc = main(
        [
            "--hex",
            str(base_hex),
            "--capture-a",
            str(capture),
            "--skip-bootloader-check",
            "--force-unsafe",
            "--dry-run",
        ]
    )

    assert rc == 0
    stream = seen["stream"]
    assert isinstance(stream, bytes)
    start = PRESET_A_FLASH_BASE - 0x1000
    assert stream[start : start + 0x20] == table[:0x20]
    assert seen["need_post_app"] is False


def test_cli_capture_a_and_b_overlay_stream_before_flash(monkeypatch, tmp_path: Path) -> None:
    base_hex = tmp_path / "base.hex"
    capture_a = tmp_path / "presetA.bin"
    sidecar_a = tmp_path / "presetA.json"
    capture_b = tmp_path / "presetB.bin"
    sidecar_b = tmp_path / "presetB.json"
    table_a = bytes((0x20 + i) & 0xFF for i in range(PRESET_TABLE_SIZE))
    table_b = bytes((0x40 + i) & 0xFF for i in range(PRESET_TABLE_SIZE))

    _write_minimal_main_hex(base_hex, major=0x03, minor=0x01)
    capture_a.write_bytes(table_a)
    sidecar_a.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "A",
                "config_name": "ALPHA-A",
                "config_name_raw_hex": (b"ALPHA-A" + (b"\xFF" * (FILENAME_LEN - 7))).hex(),
            }
        ),
        encoding="ascii",
    )
    capture_b.write_bytes(table_b)
    sidecar_b.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "B",
                "config_name": "BRAVO-B",
                "config_name_raw_hex": (b"BRAVO-B" + (b"\xFF" * (FILENAME_LEN - 7))).hex(),
            }
        ),
        encoding="ascii",
    )

    seen: dict[str, object] = {}

    def fake_flash_main(**kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.flash_main", fake_flash_main)

    rc = main(
        [
            "--hex",
            str(base_hex),
            "--capture-a",
            str(capture_a),
            "--capture-b",
            str(capture_b),
            "--skip-bootloader-check",
            "--force-unsafe",
            "--dry-run",
        ]
    )

    assert rc == 0
    stream = seen["stream"]
    assert isinstance(stream, bytes)
    start_a = PRESET_A_FLASH_BASE - 0x1000
    start_b = PRESET_B_FLASH_BASE - 0x1000
    assert stream[start_a : start_a + 0x20] == table_a[:0x20]
    assert stream[start_b : start_b + 0x20] == table_b[:0x20]
    assert seen["need_post_app"] is False


def test_cli_capture_b_uses_v24_legacy_flash_base(monkeypatch, tmp_path: Path) -> None:
    base_hex = tmp_path / "base_v24.hex"
    capture_b = tmp_path / "presetB.bin"
    sidecar_b = tmp_path / "presetB.json"
    table_b = bytes((0x40 + i) & 0xFF for i in range(PRESET_TABLE_SIZE))

    _write_minimal_main_hex(base_hex, major=0x02, minor=0x04)
    capture_b.write_bytes(table_b)
    sidecar_b.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "B",
                "config_name": "BRAVO-B",
                "config_name_raw_hex": (b"BRAVO-B" + (b"\xFF" * (FILENAME_LEN - 7))).hex(),
            }
        ),
        encoding="ascii",
    )

    seen: dict[str, object] = {}

    def fake_flash_main(**kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.flash_main", fake_flash_main)

    rc = main(
        [
            "--hex",
            str(base_hex),
            "--capture-b",
            str(capture_b),
            "--skip-bootloader-check",
            "--force-unsafe",
            "--dry-run",
        ]
    )

    assert rc == 0
    stream = seen["stream"]
    assert isinstance(stream, bytes)
    start_b = PRESET_B_FLASH_BASE_V24_TO_V28 - 0x1000
    assert stream[start_b : start_b + 0x20] == table_b[:0x20]


def test_cli_capture_b_rejects_v23_target_hex(monkeypatch, tmp_path: Path) -> None:
    base_hex = tmp_path / "base_v23.hex"
    capture_b = tmp_path / "presetB.bin"
    sidecar_b = tmp_path / "presetB.json"

    _write_minimal_main_hex(base_hex, major=0x02, minor=0x03)
    capture_b.write_bytes(bytes((0x40 + i) & 0xFF for i in range(PRESET_TABLE_SIZE)))
    sidecar_b.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "B",
                "config_name": "BRAVO-B",
                "config_name_raw_hex": (b"BRAVO-B" + (b"\xFF" * (FILENAME_LEN - 7))).hex(),
            }
        ),
        encoding="ascii",
    )

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash.flash_main",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("flash_main must not be called")),
    )

    try:
        main(
            [
                "--hex",
                str(base_hex),
                "--capture-b",
                str(capture_b),
                "--skip-bootloader-check",
                "--force-unsafe",
                "--dry-run",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse rejection for V2.3 preset B overlay")


def test_apply_all_channel_mapping_updates_shadow_live_and_flags(monkeypatch) -> None:
    class FakeEp0:
        def __init__(self, vid: int, pid: int, path: bytes | None = None) -> None:
            self.mem = bytearray(0x1000)
            self.ptr = 0

        def set_pointer(self, addr16: int) -> None:
            self.ptr = addr16

        def read_exact(self, n: int) -> bytes:
            return bytes(self.mem[self.ptr : self.ptr + n])

        def _poke(self, addr: int, value: int, in_dir: bool, read_len: int = 0) -> bytes:
            assert in_dir is False
            self.mem[addr] = value & 0xFF
            return b""

    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.DlcpEp0", FakeEp0)
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.time.sleep", lambda _: None)

    routes = _apply_all_channel_mapping(vid=0x04D8, pid=0xFF89, route_label="R")

    assert all(entry.value == 1 and entry.label == "R" for entry in routes)
    assert len(routes) == ROUTE_LEN

    fake = FakeEp0(0x04D8, 0xFF89)
    # Re-run once so the assertions below inspect a concrete fake instance.
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.DlcpEp0", lambda vid, pid, path=None: fake)
    routes = _apply_all_channel_mapping(vid=0x04D8, pid=0xFF89, route_label="R")

    assert all(entry.value == 1 and entry.label == "R" for entry in routes)
    assert fake.mem[ROUTE_RAM_BASE : ROUTE_RAM_BASE + ROUTE_LEN] == bytes([1] * ROUTE_LEN)
    assert fake.mem[
        ROUTE_SOURCE_RAM_BASE : ROUTE_SOURCE_RAM_BASE + ROUTE_LEN
    ] == bytes([1] * ROUTE_LEN)
    assert fake.mem[EVENT_FLAGS_ADDR] & EVENT_ROUTE_APPLY_MASK
    assert fake.mem[ROUTE_DIRTY_FLAGS_ADDR] & EEPROM_ROUTE_DIRTY_MASK


def test_force_active_filename_persist_sets_event_and_waits_for_dirty_clear(
    monkeypatch,
) -> None:
    class FakeEp0:
        def __init__(self, vid: int, pid: int, path: bytes | None = None) -> None:
            self.mem = bytearray(0x1000)
            self.mem[ROUTE_DIRTY_FLAGS_ADDR] = FILENAME_DIRTY_MASK
            self.ptr = 0
            self.event_pokes = 0

        def set_pointer(self, addr16: int) -> None:
            self.ptr = addr16

        def read_exact(self, n: int) -> bytes:
            return bytes(self.mem[self.ptr : self.ptr + n])

        def _poke(self, addr: int, value: int, in_dir: bool, read_len: int = 0) -> bytes:
            assert in_dir is False
            self.mem[addr] = value & 0xFF
            if addr == EVENT_FLAGS_ADDR and (value & EVENT_DIRTY_SERVICE_MASK):
                self.event_pokes += 1
                self.mem[ROUTE_DIRTY_FLAGS_ADDR] &= (~FILENAME_DIRTY_MASK) & 0xFF
            return b""

    fake = FakeEp0(0x04D8, 0xFF89)
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.DlcpEp0", lambda vid, pid, path=None: fake)
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.time.sleep", lambda _: None)

    changed = _force_active_filename_persist(vid=0x04D8, pid=0xFF89)

    assert changed is True
    assert fake.event_pokes >= 1
    assert fake.mem[EVENT_FLAGS_ADDR] & EVENT_DIRTY_SERVICE_MASK
    assert (fake.mem[ROUTE_DIRTY_FLAGS_ADDR] & FILENAME_DIRTY_MASK) == 0


def test_force_active_filename_persist_returns_false_when_already_clean(monkeypatch) -> None:
    class FakeEp0:
        def __init__(self, vid: int, pid: int, path: bytes | None = None) -> None:
            self.mem = bytearray(0x1000)
            self.ptr = 0

        def set_pointer(self, addr16: int) -> None:
            self.ptr = addr16

        def read_exact(self, n: int) -> bytes:
            return bytes(self.mem[self.ptr : self.ptr + n])

        def _poke(self, addr: int, value: int, in_dir: bool, read_len: int = 0) -> bytes:
            raise AssertionError("no EP0 poke expected when filename dirty bit is clear")

    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.DlcpEp0", FakeEp0)

    changed = _force_active_filename_persist(vid=0x04D8, pid=0xFF89)

    assert changed is False


def test_switch_active_preset_ep0_waits_for_reapply_clear(monkeypatch) -> None:
    seen: list[str] = []
    flags = iter(
        [
            0x00,
            ACTIVE_REAPPLY_MASK | 0x04,
            0x04,
            0x04,
        ]
    )
    ticks = iter([0.0, 0.1, 0.2])

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._request_active_preset_switch_ep0",
        lambda *, vid, pid, preset, path=None: seen.append(preset) or {
            "active_flags_before": 0x00,
            "active_flags_write": ACTIVE_REAPPLY_MASK | 0x04,
        },
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._read_active_flags_ep0",
        lambda *, vid, pid, path=None: next(flags),
    )
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.time.sleep", lambda _: None)
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.time.monotonic", lambda: next(ticks))

    result = _switch_active_preset_ep0(
        vid=0x04D8,
        pid=0xFF89,
        preset="B",
        timeout_s=1.0,
        poll_interval_s=0.0,
        settle_s=0.0,
    )

    assert result == "B"
    assert seen == ["B"]


def test_switch_active_preset_ep0_times_out_when_reapply_stays_pending(monkeypatch) -> None:
    flags = iter(
        [
            0x00,
            ACTIVE_REAPPLY_MASK | 0x04,
            ACTIVE_REAPPLY_MASK | 0x04,
            ACTIVE_REAPPLY_MASK | 0x04,
        ]
    )
    ticks = iter([0.0, 0.4, 0.8, 1.2])

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._request_active_preset_switch_ep0",
        lambda **kwargs: {
            "active_flags_before": 0x00,
            "active_flags_write": ACTIVE_REAPPLY_MASK | 0x04,
        },
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._read_active_flags_ep0",
        lambda *, vid, pid, path=None: next(flags),
    )
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.time.sleep", lambda _: None)
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.time.monotonic", lambda: next(ticks))

    with pytest.raises(
        RuntimeError,
        match=r"device reports B \(active_flags=0x84, reapply pending\), expected B with reapply clear",
    ):
        _switch_active_preset_ep0(
            vid=0x04D8,
            pid=0xFF89,
            preset="B",
            timeout_s=1.0,
            poll_interval_s=0.0,
            settle_s=0.0,
        )


def test_cli_all_ch_requests_post_flash_finalize(monkeypatch, tmp_path: Path) -> None:
    base_hex = tmp_path / "base.hex"
    _write_minimal_main_hex(base_hex, major=0x02, minor=0x03)

    seen: dict[str, object] = {}

    def fake_flash_main(**kwargs):
        seen["flash_kwargs"] = kwargs
        return HidDeviceInfo(
            vendor_id=0x04D8,
            product_id=0xFF89,
            path=b"/fake/path",
            manufacturer_string="Hypex BV",
            product_string="DLCP",
            serial_number="",
        )

    def fake_apply_all_channel_mapping(**kwargs):
        seen["all_ch_kwargs"] = kwargs
        return tuple()

    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.flash_main", fake_flash_main)
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._apply_all_channel_mapping",
        fake_apply_all_channel_mapping,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._pick_device",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no live unit")),
    )

    rc = main(
        [
            "--hex",
            str(base_hex),
            "--all-ch",
            "R",
            "--skip-bootloader-check",
            "--force-unsafe",
            "--no-info",
        ]
    )

    assert rc == 0
    assert seen["flash_kwargs"]["need_post_app"] is True
    assert seen["all_ch_kwargs"]["route_label"] == "R"


def test_cli_capture_a_warns_when_diag_memread_endpoint_is_missing(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    base_hex = tmp_path / "base.hex"
    capture = tmp_path / "presetA.bin"
    sidecar = tmp_path / "presetA.json"
    table = bytes((0xA0 + i) & 0xFF for i in range(PRESET_TABLE_SIZE))
    name_slot = b"ALPHA-A" + (b"\xFF" * (FILENAME_LEN - 7))

    write_intel_hex(base_hex, {0x1000: 0x11})
    capture.write_bytes(table)
    sidecar.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "A",
                "config_name": "ALPHA-A",
                "config_name_raw_hex": name_slot.hex(),
            }
        ),
        encoding="ascii",
    )

    class FakeDev:
        def close(self) -> None:
            return None

    def fake_flash_main(**kwargs):
        return HidDeviceInfo(
            vendor_id=0x04D8,
            product_id=0xFF89,
            path=b"/fake/path",
            manufacturer_string="Hypex BV",
            product_string="DLCP",
            serial_number="",
        )

    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.flash_main", fake_flash_main)
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash._open_hid", lambda path: FakeDev())
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._cmd03_write_filename_slot",
        lambda dev, name_slot: name_slot,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._force_active_filename_persist",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_active_preset_ep0",
        lambda **kwargs: "A",
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._verify_capture_overlay",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError(
                "unexpected command echo: 0x05 "
                "(expected 0x43; device may not be running the diag memread firmware)"
            )
        ),
    )

    rc = main(
        [
            "--hex",
            str(base_hex),
            "--capture-a",
            str(capture),
            "--skip-bootloader-check",
            "--force-unsafe",
            "--no-info",
        ]
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "wrote preset A active filename: 'ALPHA-A'" in out
    assert "preset A EEPROM persist trigger: OK" in out
    assert "warning: preset A diag memread verify skipped" in out


def test_cli_capture_a_still_fails_on_real_verify_mismatch(monkeypatch, tmp_path: Path) -> None:
    base_hex = tmp_path / "base.hex"
    capture = tmp_path / "presetA.bin"
    sidecar = tmp_path / "presetA.json"
    table = bytes((0xA0 + i) & 0xFF for i in range(PRESET_TABLE_SIZE))
    name_slot = b"ALPHA-A" + (b"\xFF" * (FILENAME_LEN - 7))

    _write_minimal_main_hex(base_hex, major=0x02, minor=0x03)
    capture.write_bytes(table)
    sidecar.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "A",
                "config_name": "ALPHA-A",
                "config_name_raw_hex": name_slot.hex(),
            }
        ),
        encoding="ascii",
    )

    class FakeDev:
        def close(self) -> None:
            return None

    def fake_flash_main(**kwargs):
        return HidDeviceInfo(
            vendor_id=0x04D8,
            product_id=0xFF89,
            path=b"/fake/path",
            manufacturer_string="Hypex BV",
            product_string="DLCP",
            serial_number="",
        )

    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.flash_main", fake_flash_main)
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash._open_hid", lambda path: FakeDev())
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._cmd03_write_filename_slot",
        lambda dev, name_slot: name_slot,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._force_active_filename_persist",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_active_preset_ep0",
        lambda **kwargs: "A",
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._verify_capture_overlay",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("post-flash preset A table verify failed at offset 0x0000")
        ),
    )

    try:
        main(
            [
                "--hex",
                str(base_hex),
                "--capture-a",
                str(capture),
                "--skip-bootloader-check",
                "--force-unsafe",
                "--no-info",
            ]
        )
    except RuntimeError as exc:
        assert "post-flash preset A table verify failed" in str(exc)
    else:
        raise AssertionError("expected verify mismatch to remain fatal")


def test_cli_capture_a_warns_when_eeprom_name_has_not_persisted_yet(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    base_hex = tmp_path / "base.hex"
    capture = tmp_path / "presetA.bin"
    sidecar = tmp_path / "presetA.json"
    table = bytes((0xA0 + i) & 0xFF for i in range(PRESET_TABLE_SIZE))
    name_slot = b"ALPHA-A" + (b"\xFF" * (FILENAME_LEN - 7))

    _write_minimal_main_hex(base_hex, major=0x02, minor=0x03)
    capture.write_bytes(table)
    sidecar.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "A",
                "config_name": "ALPHA-A",
                "config_name_raw_hex": name_slot.hex(),
            }
        ),
        encoding="ascii",
    )

    class FakeDev:
        def close(self) -> None:
            return None

    def fake_flash_main(**kwargs):
        return HidDeviceInfo(
            vendor_id=0x04D8,
            product_id=0xFF89,
            path=b"/fake/path",
            manufacturer_string="Hypex BV",
            product_string="DLCP",
            serial_number="",
        )

    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash.flash_main", fake_flash_main)
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash._open_hid", lambda path: FakeDev())
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._cmd03_write_filename_slot",
        lambda dev, name_slot: name_slot,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._force_active_filename_persist",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_active_preset_ep0",
        lambda **kwargs: "A",
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._verify_capture_overlay",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError(
                "post-flash preset A EEPROM name verify failed: "
                "got ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff, "
                "expected 414c5048412d41ffffffffffffffffffffffffffffffffffffffffff"
            )
        ),
    )

    rc = main(
        [
            "--hex",
            str(base_hex),
            "--capture-a",
            str(capture),
            "--skip-bootloader-check",
            "--force-unsafe",
            "--no-info",
        ]
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "wrote preset A active filename: 'ALPHA-A'" in out
    assert "preset A EEPROM persist trigger: already clean" in out
    assert "preset A flash table verify: OK" in out
    assert "warning: preset A EEPROM filename not yet persisted" in out


def test_cli_capture_a_and_b_finalize_switches_b_and_restores_a(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    base_hex = tmp_path / "base.hex"
    capture_a = tmp_path / "presetA.bin"
    sidecar_a = tmp_path / "presetA.json"
    capture_b = tmp_path / "presetB.bin"
    sidecar_b = tmp_path / "presetB.json"
    table_a = bytes((0x20 + i) & 0xFF for i in range(PRESET_TABLE_SIZE))
    table_b = bytes((0x40 + i) & 0xFF for i in range(PRESET_TABLE_SIZE))
    name_a = b"ALPHA-A" + (b"\xFF" * (FILENAME_LEN - 7))
    name_b = b"BRAVO-B" + (b"\xFF" * (FILENAME_LEN - 7))

    _write_minimal_main_hex(base_hex, major=0x03, minor=0x01)
    capture_a.write_bytes(table_a)
    sidecar_a.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "A",
                "config_name": "ALPHA-A",
                "config_name_raw_hex": name_a.hex(),
            }
        ),
        encoding="ascii",
    )
    capture_b.write_bytes(table_b)
    sidecar_b.write_text(
        json.dumps(
            {
                "format": "dlcp_preset_capture_v1",
                "preset": "B",
                "config_name": "BRAVO-B",
                "config_name_raw_hex": name_b.hex(),
            }
        ),
        encoding="ascii",
    )

    class FakeDev:
        def close(self) -> None:
            return None

    writes: list[bytes] = []
    switches: list[str] = []

    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash.flash_main",
        lambda **kwargs: HidDeviceInfo(
            vendor_id=0x04D8,
            product_id=0xFF89,
            path=b"/fake/path",
            manufacturer_string="Hypex BV",
            product_string="DLCP",
            serial_number="",
        ),
    )
    monkeypatch.setattr("dlcp_fw.flash.dlcp_main_flash._open_hid", lambda path: FakeDev())
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._cmd03_write_filename_slot",
        lambda dev, name_slot: writes.append(name_slot) or name_slot,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._force_active_filename_persist",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._verify_capture_overlay",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._probe_active_preset_ep0",
        lambda **kwargs: "A",
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.dlcp_main_flash._switch_active_preset_ep0",
        lambda *, preset, **kwargs: switches.append(preset) or preset,
    )

    rc = main(
        [
            "--hex",
            str(base_hex),
            "--capture-a",
            str(capture_a),
            "--capture-b",
            str(capture_b),
            "--skip-bootloader-check",
            "--force-unsafe",
            "--no-info",
        ]
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert writes == [name_a, name_b]
    assert switches == ["B", "A"]
    assert "wrote preset A active filename: 'ALPHA-A'" in out
    assert "wrote preset B active filename: 'BRAVO-B'" in out
    assert "restored active preset: A" in out
