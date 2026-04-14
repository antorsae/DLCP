from __future__ import annotations

import pytest

from dlcp_fw.flash import dlcp_ep0_flash_probe as probe


def test_parse_span_start_size_form() -> None:
    start, size = probe.parse_span("0x561C:0x14")
    assert start == 0x561C
    assert size == 0x14


def test_parse_span_inclusive_range_form() -> None:
    start, size = probe.parse_span("0x4C1C..0x4C2F")
    assert start == 0x4C1C
    assert size == 0x14


def test_parse_span_rejects_reversed_range() -> None:
    with pytest.raises(ValueError, match="end must be >= start"):
        probe.parse_span("0x10..0x0F")


def test_format_hexdump_includes_offset_hex_and_ascii() -> None:
    text = probe.format_hexdump(0x561C, b"\x00ABC\xff", width=8)
    assert "0x561C:" in text
    assert "00 41 42 43 FF" in text
    assert "|.ABC.|" in text


def test_read_flash_window_forwards_explicit_path(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeEp0:
        def __init__(self, vid: int, pid: int, path: bytes | None = None) -> None:
            seen["path"] = path
            self.ptr = 0

        def set_pointer(self, addr16: int) -> None:
            self.ptr = addr16

        def read_exact(self, n: int) -> bytes:
            return bytes([0xAA] * n)

    monkeypatch.setattr(probe.ep0, "DlcpEp0", FakeEp0)

    data = probe.read_flash_window(
        vid=0x04D8,
        pid=0xFF89,
        path=b"hid-main-b",
        start=0x561C,
        size=4,
        chunk=2,
    )

    assert data == b"\xAA\xAA\xAA\xAA"
    assert seen["path"] == b"hid-main-b"


def test_cli_list_outputs_matching_devices(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        probe.ep0,
        "list_matching_devices_json",
        lambda vid, pid: [{"path": "hid-main-b", "serial_number": "B"}],
    )

    rc = probe.main(["read", "--list"])

    assert rc == 0
    assert "hid-main-b" in capsys.readouterr().out
