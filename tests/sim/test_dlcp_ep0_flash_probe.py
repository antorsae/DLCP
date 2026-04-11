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
