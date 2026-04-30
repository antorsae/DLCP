from __future__ import annotations

from dlcp_fw.analysis.word_dump_to_ihex import (
    combine_v23_main_exports_to_ihex,
    parse_addressed_byte_table,
    parse_byte_page_dump,
    parse_decoded_config_report,
    parse_tabular_word_dump,
)
from dlcp_fw.paths import (
    STOCK_MAIN_COMBINED_HEX,
    STOCK_MAIN_CONFIG_BITS_EXPORT,
    STOCK_MAIN_EE_DATA_EXPORT,
    STOCK_MAIN_HEX,
    STOCK_MAIN_PROGRAM_MEMORY_EXPORT,
    STOCK_MAIN_USER_ID_EXPORT,
)
from dlcp_fw.sim.hexio import parse_intel_hex

import pytest

# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.  Mark the
# whole module dual_supported so DLCP_SIM_BACKEND={rust,dual} does
# not auto-skip them.
pytestmark = pytest.mark.dual_supported


def test_parse_tabular_word_dump_sample(tmp_path) -> None:
    sample = "\n".join(
        [
            "   Address      00     02     04     06               ASCII",
            "1000         EF0A   F008   FFFF   1234               ........",
            "1008         CFD9   F001   CFDA   F002               ........",
            "",
        ]
    )

    tmp = tmp_path / "sample_dump.txt"
    tmp.write_text(sample, encoding="ascii")
    mem, summary = parse_tabular_word_dump(tmp)

    assert summary.format_name == "word_dump"
    assert summary.row_count == 2
    assert summary.byte_count == 16
    assert summary.min_addr == 0x1000
    assert summary.max_addr == 0x100F
    assert mem[0x1000] == 0x0A
    assert mem[0x1001] == 0xEF
    assert mem[0x1006] == 0x34
    assert mem[0x1007] == 0x12


def test_parse_byte_page_dump_sample(tmp_path) -> None:
    sample = "\n".join(
        [
            "Address 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F",
            "00 FF EE DD CC BB AA 99 88 77 66 55 44 33 22 11 00",
            "10 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F",
        ]
    )

    tmp = tmp_path / "byte_page.txt"
    tmp.write_text(sample, encoding="ascii")
    mem, summary = parse_byte_page_dump(tmp, base_addr=0xF00000)

    assert summary.format_name == "byte_page"
    assert summary.base_addr == 0xF00000
    assert summary.byte_count == 32
    assert summary.min_addr == 0xF00000
    assert summary.max_addr == 0xF0001F
    assert mem[0xF00000] == 0xFF
    assert mem[0xF0000F] == 0x00
    assert mem[0xF00010] == 0x00
    assert mem[0xF0001F] == 0x0F


def test_parse_addressed_byte_table_sample(tmp_path) -> None:
    sample = "\n".join(
        [
            "Address User ID",
            "200000 0xFF",
            "200001 0x11",
            "200002 0x22",
        ]
    )

    tmp = tmp_path / "addressed.txt"
    tmp.write_text(sample, encoding="ascii")
    mem, summary = parse_addressed_byte_table(tmp)

    assert summary.format_name == "addressed_bytes"
    assert summary.row_count == 3
    assert summary.byte_count == 3
    assert summary.min_addr == 0x200000
    assert summary.max_addr == 0x200002
    assert mem[0x200001] == 0x11


def test_parse_decoded_config_report_with_reference() -> None:
    reference = parse_intel_hex(STOCK_MAIN_HEX)
    mem, summary = parse_decoded_config_report(
        STOCK_MAIN_CONFIG_BITS_EXPORT,
        reference_bytes=reference,
    )

    assert summary.format_name == "decoded_config_report"
    assert summary.row_count == 11
    assert summary.byte_count == 14
    assert summary.min_addr == 0x300000
    assert summary.max_addr == 0x30000D
    assert mem[0x300000] == 0x3A
    assert mem[0x300001] == 0x46
    assert mem[0x300008] == 0x0F
    assert mem[0x30000A] == 0x0F
    assert mem[0x30000C] == 0x0F


def test_combine_real_v23_exports(tmp_path) -> None:
    out_hex = tmp_path / "v23_combined.hex"
    summary = combine_v23_main_exports_to_ihex(out_hex)

    combined = parse_intel_hex(out_hex)
    stock = parse_intel_hex(STOCK_MAIN_HEX)

    assert summary.byte_count == 0x6000 + 0x100 + 0x8 + 0x0E
    assert summary.min_addr == 0x0000
    assert summary.max_addr == 0xF000FF

    # Program-memory export is byte-identical to the repaired readback.
    for addr in range(0x0000, 0x6000):
        assert addr in combined
    assert combined[0x0000] == 0xC7
    assert combined[0x0001] == 0xEF
    assert combined[0x561C] == 0x0F
    assert combined[0x561D] == 0xE7

    # User ID tables merge cleanly.
    for addr in range(0x200000, 0x200008):
        assert combined[addr] == stock.get(addr, 0xFF) == 0xFF

    # Config report is normalized to raw config bytes using the stock HEX.
    assert combined[0x300000] == 0x3A
    assert combined[0x300001] == 0x46
    assert combined[0x300008] == 0x0F
    assert combined[0x30000D] == 0x40

    # The 256-byte addressless export is mapped to EEPROM space at 0xF00000.
    assert combined[0xF00000] == 0xFF
    assert combined[0xF00003] == 0xEF
    assert combined[0xF00060] == 0x4C
    assert combined[0xF00061] == 0x58
    assert combined[0xF000FD] == 0x00
    assert combined[0xF000FE] == 0x02
    assert combined[0xF000FF] == 0x02

    # The live program-memory export matches stock app code but includes boot block and a populated DSP table.
    for addr in range(0x1000, 0x5600):
        assert combined[addr] == stock[addr]
    for addr in range(0x5F00, 0x6000):
        assert combined[addr] == stock[addr]
    assert 0x0000 not in stock
    assert combined[0x561C] != stock[0x561C]


def test_stock_main_export_constants_exist() -> None:
    for path in [
        STOCK_MAIN_PROGRAM_MEMORY_EXPORT,
        STOCK_MAIN_CONFIG_BITS_EXPORT,
        STOCK_MAIN_EE_DATA_EXPORT,
        STOCK_MAIN_USER_ID_EXPORT,
    ]:
        assert path.exists()
    assert STOCK_MAIN_COMBINED_HEX.name == "DLCP Firmware V2.3-combined.hex"
