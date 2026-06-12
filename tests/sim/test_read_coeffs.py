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


# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
pytestmark = pytest.mark.dual_supported


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
    """Unrelated reports that arrive after the request (e.g. an async
    notification racing the reply) are skipped until the cmd echo arrives.
    """
    reader = object.__new__(HidMemoryReader)
    reader._timeout_ms = 1000
    reader._dev = object()

    writes: list[bytes] = []
    pending: list[bytes] = []

    def fake_write(dev, payload) -> None:  # noqa: ANN001
        writes.append(payload)
        pending.extend(
            [
                bytes([0x05]) + bytes(63),
                bytes([CMD_DIAG_MEMREAD, 0x00, 0x01, 0xAB]) + bytes(60),
            ]
        )

    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._hid_write64", fake_write)
    monkeypatch.setattr(
        "dlcp_fw.flash.read_coeffs._hid_read64",
        lambda dev, timeout_ms=1000: pending.pop(0) if pending else None,
    )

    report = bytes([CMD_DIAG_MEMREAD]) + bytes(63)
    resp = HidMemoryReader._exchange(reader, report)

    assert writes == [report]
    assert resp[0] == CMD_DIAG_MEMREAD
    assert resp[3] == 0xAB


def test_exchange_reports_ignored_unrelated_commands_on_timeout(monkeypatch) -> None:
    """Unrelated reports arriving AFTER the request still count as 'ignored'
    in the timeout error.  (Unrelated junk sitting in the queue BEFORE the
    request is silently consumed by the pre-write drain instead — covered by
    test_exchange_drains_stale_pending_responses_before_write.)
    """
    reader = object.__new__(HidMemoryReader)
    reader._timeout_ms = 1
    reader._dev = object()

    pending: list[bytes] = []

    def fake_write(dev, payload) -> None:  # noqa: ANN001
        pending.append(bytes([0x05]) + bytes(63))

    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._hid_write64", fake_write)
    monkeypatch.setattr(
        "dlcp_fw.flash.read_coeffs._hid_read64",
        lambda dev, timeout_ms=1000: pending.pop(0) if pending else None,
    )

    with pytest.raises(RuntimeError, match="ignoring 1 unrelated HID report"):
        HidMemoryReader._exchange(reader, bytes([CMD_DIAG_MEMREAD]) + bytes(63))


# ---------------------------------------------------------------------------
# 2026-06-12 live finalize failures: blocking-handle hang + instant-fatal
# transient (RIGHT MAIN rev 0x85 post-flash verify).
# ---------------------------------------------------------------------------


def _bare_reader() -> HidMemoryReader:
    reader = object.__new__(HidMemoryReader)
    reader._timeout_ms = 1000
    reader._dev = object()
    return reader


def _good_resp(length: int, fill: int = 0xA5) -> bytes:
    return bytes([CMD_DIAG_MEMREAD, 0x00, length]) + bytes([fill] * length) + bytes(
        64 - 3 - length
    )


def test_reader_opens_real_hid_nonblocking(monkeypatch) -> None:
    """The deadline poll in _hid_read64 (dev.read(64, 0) + sleep) only honors
    its timeout on a NONBLOCKING handle.  The 2026-06-12 RIGHT-MAIN finalize
    hung forever at `read 0x06AC/0x0A00` because the reader configured the
    device blocking, so one lost report parked dev.read indefinitely.
    """
    calls: list[bool] = []

    class _FakeDev:
        def open_path(self, path) -> None:  # noqa: ANN001
            pass

        def set_nonblocking(self, flag) -> None:  # noqa: ANN001
            calls.append(bool(flag))

    class _FakeHidModule:
        @staticmethod
        def device() -> "_FakeDev":
            return _FakeDev()

    import sys as _sys

    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._OPEN_HID_OVERRIDE", None)
    monkeypatch.setitem(_sys.modules, "hid", _FakeHidModule())
    info = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"fake-path",
        manufacturer_string=None,
        product_string=None,
        serial_number=None,
    )
    HidMemoryReader(info=info, timeout_ms=500)
    assert calls == [True], (
        f"device must be opened nonblocking (got set_nonblocking calls {calls})"
    )


def test_read_chunk_retries_through_transient_bad_status(monkeypatch) -> None:
    """One glitched exchange (device echoes a non-zero status, e.g. the live
    'bad-region' reply mid-window) must be retried, not raised — the window
    verify loop only retried verify MISMATCHES, so a single transient killed
    the whole finalize with a traceback.
    """
    reader = _bare_reader()
    writes: list[bytes] = []
    scripted = [
        bytes([CMD_DIAG_MEMREAD, 0x01]) + bytes(62),   # bad-region status
        _good_resp(4),
    ]
    pending: list[bytes] = []

    def fake_write(dev, payload) -> None:  # noqa: ANN001
        writes.append(payload)
        pending.append(scripted.pop(0))   # device replies only to requests

    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._hid_write64", fake_write)
    monkeypatch.setattr(
        "dlcp_fw.flash.read_coeffs._hid_read64",
        lambda dev, timeout_ms=1000: pending.pop(0) if pending else None,
    )
    monkeypatch.setattr("dlcp_fw.flash.read_coeffs.time.sleep", lambda s: None)

    payload = HidMemoryReader.read_chunk(reader, region=0, addr=0x5600, length=4)
    assert payload == bytes([0xA5] * 4)
    assert len(writes) == 2, "transient bad status must re-send the request"


def test_read_chunk_retries_through_transient_length_echo_mismatch(monkeypatch) -> None:
    reader = _bare_reader()
    writes: list[bytes] = []
    scripted = [
        _good_resp(2),   # stale/short echo for a 4-byte request
        _good_resp(4),
    ]
    pending: list[bytes] = []

    def fake_write(dev, payload) -> None:  # noqa: ANN001
        writes.append(payload)
        pending.append(scripted.pop(0))

    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._hid_write64", fake_write)
    monkeypatch.setattr(
        "dlcp_fw.flash.read_coeffs._hid_read64",
        lambda dev, timeout_ms=1000: pending.pop(0) if pending else None,
    )
    monkeypatch.setattr("dlcp_fw.flash.read_coeffs.time.sleep", lambda s: None)

    payload = HidMemoryReader.read_chunk(reader, region=0, addr=0x5600, length=4)
    assert payload == bytes([0xA5] * 4)
    assert len(writes) == 2


def test_read_chunk_raises_after_persistent_bad_status(monkeypatch) -> None:
    reader = _bare_reader()
    writes: list[bytes] = []

    monkeypatch.setattr(
        "dlcp_fw.flash.read_coeffs._hid_write64",
        lambda dev, payload: writes.append(payload),
    )
    monkeypatch.setattr(
        "dlcp_fw.flash.read_coeffs._hid_read64",
        lambda dev, timeout_ms=1000: bytes([CMD_DIAG_MEMREAD, 0x01]) + bytes(62),
    )
    monkeypatch.setattr("dlcp_fw.flash.read_coeffs.time.sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="after 3 attempts.*bad-region"):
        HidMemoryReader.read_chunk(reader, region=0, addr=0x5600, length=4)
    assert len(writes) == 3, "retry must be bounded"


def test_exchange_drains_stale_pending_responses_before_write(monkeypatch) -> None:
    """A Ctrl-C'd predecessor can leave its response sitting in the IN queue;
    accepting it for the NEXT request shifts every later exchange off by one
    (the live bad-region reply at 0x066F).  _exchange must drain pending
    reports BEFORE writing the new request.
    """
    reader = _bare_reader()
    events: list[str] = []
    stale = _good_resp(2, fill=0x11)
    real = _good_resp(4, fill=0x22)
    queue = [stale]

    def fake_write(dev, payload) -> None:  # noqa: ANN001
        events.append("write")
        queue.append(real)

    def fake_read(dev, timeout_ms=1000):  # noqa: ANN001
        events.append(f"read(t={timeout_ms})")
        return queue.pop(0) if queue else None

    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._hid_write64", fake_write)
    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._hid_read64", fake_read)

    resp = HidMemoryReader._exchange(
        reader, bytes([CMD_DIAG_MEMREAD]) + bytes(63)
    )
    assert resp == real, "stale pre-write response must be drained, not returned"
    assert events[0].startswith("read"), "drain must happen before the write"


def test_exchange_deadline_holds_under_continuous_unrelated_chatter(monkeypatch) -> None:
    """A device chattering unrelated reports must not livelock _exchange:
    the deadline is enforced against the wall clock even though every read
    returns data (codex MEDIUM vs 540dc76 — the old max(1, ...) clamp made
    the timeout branch unreachable).
    """
    reader = object.__new__(HidMemoryReader)
    reader._timeout_ms = 30
    reader._dev = object()
    wrote = False

    def fake_write(dev, payload) -> None:  # noqa: ANN001
        nonlocal wrote
        wrote = True

    def fake_read(dev, timeout_ms=1000):  # noqa: ANN001
        # pre-write drain sees an empty queue; post-write the device
        # chatters unrelated reports forever
        return bytes([0x05]) + bytes(63) if wrote else None

    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._hid_write64", fake_write)
    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._hid_read64", fake_read)

    with pytest.raises(RuntimeError, match="unrelated HID report"):
        HidMemoryReader._exchange(reader, bytes([CMD_DIAG_MEMREAD]) + bytes(63))


def test_drain_pending_is_bounded(monkeypatch) -> None:
    """_drain_pending must stop at its bound even against a queue that never
    empties, and read_chunk must still converge afterwards via the normal
    exchange/retry semantics.
    """
    reader = _bare_reader()
    stale = [_good_resp(2, fill=0x11)] * 12   # more stale junk than the bound
    pending: list[bytes] = list(stale)
    writes: list[bytes] = []

    def fake_write(dev, payload) -> None:  # noqa: ANN001
        writes.append(payload)
        pending.append(_good_resp(4, fill=0x22))

    def fake_read(dev, timeout_ms=1000):  # noqa: ANN001
        return pending.pop(0) if pending else None

    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._hid_write64", fake_write)
    monkeypatch.setattr("dlcp_fw.flash.read_coeffs._hid_read64", fake_read)
    monkeypatch.setattr("dlcp_fw.flash.read_coeffs.time.sleep", lambda s: None)

    drained = HidMemoryReader._drain_pending(reader)
    assert drained == 8, "drain must stop at its bound"

    # 4 stale reports remain; the exchange path must still converge: the
    # next read_chunk drains what it can, skips/errors through the rest,
    # and the bounded retry lands on the real response.
    payload = HidMemoryReader.read_chunk(reader, region=0, addr=0x5600, length=4)
    assert payload == bytes([0x22] * 4)


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
