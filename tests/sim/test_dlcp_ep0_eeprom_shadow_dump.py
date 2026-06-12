from __future__ import annotations

import json
import plistlib
import subprocess

import pytest

from dlcp_fw.flash import dlcp_ep0_eeprom_shadow_dump as shadow
from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo


# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
pytestmark = pytest.mark.dual_supported


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


def test_macos_location_id_refreshes_stale_hid_cache(monkeypatch) -> None:
    shadow._macos_hid_device_index.cache_clear()
    monkeypatch.setattr(shadow.sys, "platform", "darwin")
    payloads = [
        plistlib.dumps(
            [
                {
                    "IORegistryEntryID": 111,
                    "VendorID": 0x04D8,
                    "ProductID": 0xFF89,
                    "LocationID": 0x01120000,
                }
            ]
        ),
        plistlib.dumps(
            [
                {
                    "IORegistryEntryID": 111,
                    "VendorID": 0x04D8,
                    "ProductID": 0xFF89,
                    "LocationID": 0x01120000,
                },
                {
                    "IORegistryEntryID": 222,
                    "VendorID": 0x04D8,
                    "ProductID": 0xFF89,
                    "LocationID": 0x03112000,
                },
            ]
        ),
    ]

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(_args, 0, stdout=payloads.pop(0), stderr=b"")

    monkeypatch.setattr(shadow.subprocess, "run", fake_run)

    assert (
        shadow._macos_location_id_for_hid_path(
            vid=0x04D8,
            pid=0xFF89,
            path=b"DevSrvsID:111",
        )
        == 0x01120000
    )
    assert (
        shadow._macos_location_id_for_hid_path(
            vid=0x04D8,
            pid=0xFF89,
            path=b"DevSrvsID:222",
        )
        == 0x03112000
    )
    assert payloads == []
    shadow._macos_hid_device_index.cache_clear()


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


# ---------------------------------------------------------------------------
# 2026-06-12 EP0 hardening: bounded ctrl-transfer retries, reopen-on-error,
# re-seek-and-restart reads (run-3 live failure: one Errno-5 EIO instantly
# killed the finalize while the HID side was perfectly healthy).
# ---------------------------------------------------------------------------


class _FakeUSBError(Exception):
    pass


class _FakeUsbCore:
    USBError = _FakeUSBError


def _bare_ep0() -> shadow.DlcpEp0:
    ep0 = shadow.DlcpEp0.__new__(shadow.DlcpEp0)
    ep0._usb_core = _FakeUsbCore
    ep0._pointer = None
    return ep0


def test_ep0_out_poke_retries_transient_usberror(monkeypatch) -> None:
    ep0 = _bare_ep0()
    calls: list[tuple] = []

    class _Dev:
        def ctrl_transfer(self, bm, breq, wval, widx, data_or_len):
            calls.append((bm, breq, wval, widx))
            if len(calls) == 1:
                raise _FakeUSBError("[Errno 5] Input/Output Error")
            return None

    ep0.dev = _Dev()
    reopens: list[bool] = []
    ep0._reopen = lambda: reopens.append(True)  # type: ignore[method-assign]
    monkeypatch.setattr(shadow.time, "sleep", lambda s: None)

    shadow.DlcpEp0._poke(ep0, 0x75, 0x12, in_dir=False)
    assert len(calls) == 2, "transient OUT failure must be re-issued"
    assert reopens == [], "no reopen needed for a single transient"


def test_ep0_out_poke_reopens_once_then_raises_when_persistent(monkeypatch) -> None:
    ep0 = _bare_ep0()
    calls: list[int] = []

    class _Dev:
        def ctrl_transfer(self, bm, breq, wval, widx, data_or_len):
            calls.append(1)
            raise _FakeUSBError("[Errno 5] Input/Output Error")

    ep0.dev = _Dev()
    reopens: list[bool] = []
    ep0._reopen = lambda: reopens.append(True)  # type: ignore[method-assign]
    monkeypatch.setattr(shadow.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="after 3 attempts"):
        shadow.DlcpEp0._poke(ep0, 0x75, 0x12, in_dir=False)
    assert len(calls) == 3, "OUT retry must be bounded"
    assert reopens == [True], "one reopen attempt before the final try"


def test_ep0_read_exact_reseeks_and_restarts_after_transfer_failure(monkeypatch) -> None:
    """A failed IN transfer leaves the device-side autoincrement pointer in an
    unknown state; blindly re-reading would misalign the stream.  read_exact
    must re-seek to the stored window start and restart the whole read.
    """
    ep0 = _bare_ep0()
    outs: list[tuple[int, int]] = []
    in_calls: list[int] = []

    class _Dev:
        def ctrl_transfer(self, bm, breq, wval, widx, data_or_len):
            if bm == 0x00:
                outs.append((widx, wval))
                return None
            in_calls.append(1)
            if len(in_calls) == 1:
                raise _FakeUSBError("[Errno 5] Input/Output Error")
            return bytes([0xAB]) * data_or_len

    ep0.dev = _Dev()
    ep0._reopen = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(shadow.time, "sleep", lambda s: None)

    shadow.DlcpEp0.set_pointer(ep0, 0x0123)
    seek_count_after_first = len(outs)
    data = shadow.DlcpEp0.read_exact(ep0, 4)
    assert data == bytes([0xAB]) * 4
    assert len(in_calls) == 2
    assert len(outs) == seek_count_after_first * 2, (
        "recovery must re-seek the window start before re-reading"
    )
    # the re-seek must target the SAME address (lo, hi pair repeated)
    assert outs[:seek_count_after_first] == outs[seek_count_after_first:]


def test_ep0_read_exact_without_pointer_does_not_blind_retry(monkeypatch) -> None:
    ep0 = _bare_ep0()
    in_calls: list[int] = []

    class _Dev:
        def ctrl_transfer(self, bm, breq, wval, widx, data_or_len):
            in_calls.append(1)
            raise _FakeUSBError("[Errno 5] Input/Output Error")

    ep0.dev = _Dev()
    ep0._reopen = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(shadow.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError):
        shadow.DlcpEp0.read_exact(ep0, 4)
    assert len(in_calls) == 1, (
        "without a stored window start there is no safe re-seek; "
        "a blind re-read could return misaligned data"
    )


def test_ep0_read_recovery_reseeks_current_window_not_stale_start(monkeypatch) -> None:
    """Streaming callers seek ONCE then loop read_exact(); recovery must
    re-seek the CURRENT window's start (advanced by prior successful reads),
    not the original set_pointer address — re-reading window 1's bytes for
    window 2 would be silent duplicate-data corruption (codex HIGH vs
    75cae7a).
    """
    ep0 = _bare_ep0()
    device_ptr = {"value": 0}
    fail_once = {"armed": False}

    class _Dev:
        def ctrl_transfer(self, bm, breq, wval, widx, data_or_len):
            if bm == 0x00:
                if widx == shadow.idx_for_addr(0x75):
                    device_ptr["value"] = (device_ptr["value"] & 0xFF00) | wval
                elif widx == shadow.idx_for_addr(0x76):
                    device_ptr["value"] = (device_ptr["value"] & 0x00FF) | (wval << 8)
                return None
            if fail_once["armed"]:
                fail_once["armed"] = False
                raise _FakeUSBError("[Errno 5] Input/Output Error")
            start = device_ptr["value"]
            data = bytes((start + i) & 0xFF for i in range(data_or_len))
            device_ptr["value"] = start + data_or_len
            return data

    ep0.dev = _Dev()
    ep0._reopen = lambda: None  # type: ignore[method-assign]
    monkeypatch.setattr(shadow.time, "sleep", lambda s: None)

    shadow.DlcpEp0.set_pointer(ep0, 0x0100)
    first = shadow.DlcpEp0.read_exact(ep0, 4)
    assert first == bytes([0x00, 0x01, 0x02, 0x03])

    fail_once["armed"] = True
    second = shadow.DlcpEp0.read_exact(ep0, 4)
    assert second == bytes([0x04, 0x05, 0x06, 0x07]), (
        "recovery must resume at the CURRENT stream position; duplicated "
        f"window-1 bytes would be silent corruption (got {second.hex()})"
    )


def test_ep0_reopen_failure_keeps_transport_classification(monkeypatch) -> None:
    """If the recovery reopen itself fails (device mid-re-enumeration:
    _resolve_usb_device raises plain RuntimeError), the surfaced error must
    STAY an Ep0TransferError so the finalize fallback still degrades to the
    HID verification (codex MEDIUM vs 75cae7a), with the reopen failure
    chained for visibility.
    """
    ep0 = _bare_ep0()

    class _Dev:
        def ctrl_transfer(self, bm, breq, wval, widx, data_or_len):
            raise _FakeUSBError("[Errno 5] Input/Output Error")

    ep0.dev = _Dev()

    def _reopen_fails() -> None:
        raise RuntimeError("DLCP not found (VID:PID = 04D8:FF89)")

    ep0._reopen = _reopen_fails  # type: ignore[method-assign]
    monkeypatch.setattr(shadow.time, "sleep", lambda s: None)

    with pytest.raises(shadow.Ep0TransferError, match="reopen"):
        shadow.DlcpEp0._poke(ep0, 0x75, 0x12, in_dir=False)
