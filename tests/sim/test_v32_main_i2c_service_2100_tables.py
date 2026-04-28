"""V3.2 main_i2c_service_2100 table-shape guard.

Pins the packed dispatch/source tables introduced when
``main_i2c_service_2100`` was rewritten from two inline xorlw-chain
switches into two table-driven loops.  A corruption of either table
silently redirects RAM writes to the wrong per-channel block, which
would corrupt the DSP sync state without any visible parser-level
symptom until the next channel config change.

Behavioral equivalence is enforced by the integration gate
(``test_v31_dsp_boot_equivalence.py``, ``test_v31_command_matrix.py``,
``test_main_gpsim_i2c_regfile.py``).  This file is the cheap,
millisecond-scale guard that catches the most likely breakage
(accidentally flipping a table byte during an unrelated edit).
"""

from __future__ import annotations

import pytest
from intelhex import IntelHex

from dlcp_fw.paths import V32_MAIN_ASM
from dlcp_fw.sim.v30_symbols import (
    assemble_v30,
    load_gpasm_symbols_for_hex,
)


# Pure source / hex tests -- no sim backend needed.
pytestmark = pytest.mark.dual_supported


# Counter -> (FSR1L, FSR1H) pairs that the old xorlw chains dispatched to.
# See docs/V32_SIZE_OPTIMIZATION_PROGRESS.md and the body comments on
# ``main_i2c_service_2100_dispatch_table`` / ``_source_table``.
DISPATCH_TABLE_EXPECTED = [
    (0xD7, 0x00),  # 0 -> ram_0x0D7/0x0D8  (bank 0)
    (0xDB, 0x00),  # 1 -> ram_0x0DB/0x0DC  (bank 0)
    (0xDF, 0x00),  # 2 -> ram_0x0DF/0x0E0  (bank 0)
    (0xD9, 0x01),  # 3 -> ram_0x1D9/0x1DA  (bank 1)
    (0xE4, 0x00),  # 4 -> ram_0x0E4/0x0E5  (bank 0)
    (0xE0, 0x01),  # 5 -> ram_0x1E0/0x1E1  (bank 1)
]

SOURCE_TABLE_EXPECTED = [
    (0xD7, 0x00),  # 0 -> ram_0x0D7..0x0DA  (bank 0)
    (0xDB, 0x00),  # 1 -> ram_0x0DB..0x0DE  (bank 0)
    (0xDF, 0x00),  # 2 -> ram_0x0DF..0x0E2  (bank 0)
    (0xD9, 0x01),  # 3 -> ram_0x1D9..0x1DC  (bank 1)
    (0xE3, 0x00),  # 4 -> ram_0x0E3..0x0E6  (bank 0)
    (0xDD, 0x01),  # 5 -> ram_0x1DD..0x1E0  (bank 1)
    (0xE1, 0x01),  # 6 -> ram_0x1E1..0x1E4  (bank 1)
]


@pytest.fixture(scope="module")
def v32_symbols_and_hex(tmp_path_factory: pytest.TempPathFactory):
    # Per-worker tmp build to avoid xdist races on the canonical release
    # hex (see tests/sim/test_v32_no_pop_flash_entry.py:71 for the same
    # pattern).  Explicit output_lst so the sibling listing lives next
    # to the tmp hex; `load_gpasm_symbols_for_hex` will then resolve
    # symbols from that tmp `.lst` directly.
    tmp = tmp_path_factory.mktemp("v32_i2c_2100_tables")
    hex_out = tmp / "DLCP_Firmware_V3.2.hex"
    lst_out = tmp / "DLCP_Firmware_V3.2.lst"
    assemble_v30(V32_MAIN_ASM, hex_out, output_lst=lst_out)
    symbols = load_gpasm_symbols_for_hex(hex_out)
    assert symbols is not None, "gpasm listing missing — cannot resolve table addresses"
    ih = IntelHex(str(hex_out))
    return symbols, ih


def _table_bytes(ih: IntelHex, byte_addr: int, count: int) -> list[int]:
    return [ih[byte_addr + i] for i in range(count)]


def test_dispatch_table_bytes_match_expected(v32_symbols_and_hex):
    symbols, ih = v32_symbols_and_hex
    byte_addr = symbols["main_i2c_service_2100_dispatch_table"]
    expected = [b for pair in DISPATCH_TABLE_EXPECTED for b in pair]
    actual = _table_bytes(ih, byte_addr, len(expected))
    assert actual == expected, (
        f"dispatch_table bytes diverged: expected {expected}, got {actual}"
    )


def test_source_table_bytes_match_expected(v32_symbols_and_hex):
    symbols, ih = v32_symbols_and_hex
    byte_addr = symbols["main_i2c_service_2100_source_table"]
    expected = [b for pair in SOURCE_TABLE_EXPECTED for b in pair]
    actual = _table_bytes(ih, byte_addr, len(expected))
    assert actual == expected, (
        f"source_table bytes diverged: expected {expected}, got {actual}"
    )


def test_tables_do_not_cross_256_byte_page(v32_symbols_and_hex):
    # The Part 2/3 loops compute TBLPTRL as `LOW(table) + 2*counter` without
    # propagating carry into TBLPTRH. That only stays correct while the
    # whole table lives within a single 256-byte page.
    symbols, _ = v32_symbols_and_hex
    for label, span_bytes in (
        ("main_i2c_service_2100_dispatch_table", len(DISPATCH_TABLE_EXPECTED) * 2),
        ("main_i2c_service_2100_source_table", len(SOURCE_TABLE_EXPECTED) * 2),
    ):
        byte_addr = symbols[label]
        low_start = byte_addr & 0xFF
        low_end = (byte_addr + span_bytes - 1) & 0xFF
        assert low_end >= low_start, (
            f"{label} at 0x{byte_addr:04X} crosses a 256-byte page "
            f"(low start={low_start:#04x}, end={low_end:#04x}). "
            "The Part 2/3 loops compute TBLPTRL without carry into TBLPTRH — "
            "relocate the tables or re-seed TBLPTR differently."
        )
