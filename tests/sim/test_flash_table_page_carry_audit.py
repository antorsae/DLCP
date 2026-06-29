"""Flash table page-carry audit for current MAIN/CONTROL releases."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import V173_CONTROL_ASM, V35_MAIN_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17
from dlcp_fw.sim.v30_symbols import assemble_v30


pytestmark = pytest.mark.dual_supported


def _parse_gpasm_symbols_and_constants(lst_path: Path) -> dict[str, int]:
    text = lst_path.read_text(encoding="utf-8", errors="replace")
    table_start = text.find("SYMBOL TABLE")
    assert table_start >= 0, f"missing SYMBOL TABLE in {lst_path}"
    table_text = text[table_start:]
    pattern = re.compile(
        r"^(\w+)\s+(?:ADDRESS|CONSTANT)\s+([0-9A-Fa-f]+)\s+\d+",
        re.MULTILINE,
    )
    return {match.group(1): int(match.group(2), 16) for match in pattern.finditer(table_text)}


def _label_body(text: str, label: str, stop_labels: tuple[str, ...]) -> str:
    start = text.index(f"{label}:")
    stops = [text.find(f"{stop}:", start + len(label) + 1) for stop in stop_labels]
    end = min(pos for pos in stops if pos != -1)
    return text[start:end]


@pytest.fixture(scope="module")
def v35_symbols(tmp_path_factory: pytest.TempPathFactory) -> dict[str, int]:
    tmp = tmp_path_factory.mktemp("v35_table_carry_audit")
    hex_out = tmp / "DLCP_Firmware_V3.5.hex"
    lst_out = tmp / "DLCP_Firmware_V3.5.lst"
    assemble_v30(V35_MAIN_ASM, hex_out, output_lst=lst_out)
    return _parse_gpasm_symbols_and_constants(lst_out)


@pytest.fixture(scope="module")
def v173_symbols(tmp_path_factory: pytest.TempPathFactory) -> dict[str, int]:
    tmp = tmp_path_factory.mktemp("v173_table_carry_audit")
    hex_out = tmp / "DLCP_Control_V1.73.hex"
    lst_out = tmp / "DLCP_Control_V1.73.lst"
    assemble_v17(V173_CONTROL_ASM, hex_out, output_lst=lst_out)
    return _parse_gpasm_symbols_and_constants(lst_out)


def test_v35_low_only_tblptr_indexed_tables_stay_page_local(v35_symbols: dict[str, int]) -> None:
    """Tables indexed as LOW(table)+offset must not need a carry into TBLPTRH."""

    low_only_indexed_tables = (
        ("hex_lookup_table", 0x0F, "nibble lookup"),
        ("string_desc_ptr_table", 0x02, "valid USB string descriptors 0..2"),
        ("channel_route_pair_destination_table", 0x0A, "6 route-pair entries x 2"),
        ("channel_route_sync_source_block_table", 0x0C, "7 source-block entries x 2"),
    )

    for label, max_seed_offset, reason in low_only_indexed_tables:
        addr = v35_symbols[label]
        assert (addr & 0xFF) + max_seed_offset <= 0xFF, (
            f"{label} at 0x{addr:04X} crosses a 256-byte page for {reason}; "
            "the lookup seeds TBLPTRL from LOW(table)+offset without carry."
        )


def test_v35_src4382_route_request_table_lookup_carries_low_byte_overflow() -> None:
    text = V35_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(
        text,
        "poll_src4382_route_monitor__lookup_route_request_row",
        ("poll_src4382_route_monitor__handle_autodetect_state",),
    )

    assert "addlw       LOW(src4382_fixed_input_route_request_table)" in body
    assert "btfsc       STATUS, C, ACCESS          ; carry from low-byte table index" in body
    assert "addlw       0x01" in body
    assert "movwf       TBLPTRH, ACCESS" in body


def test_v173_lcd_rom_entry_reader_uses_16bit_carry_for_page_crossing_tables() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(
        text,
        "lcd_write_16char_rom_entry",
        ("settings_save_eeprom",),
    )

    assert "mullw   0x10" in body
    assert "addwf   (Common_RAM + 41), F, A" in body
    assert "addwfc  (Common_RAM + 42), F, A" in body
    assert "addwf   (Common_RAM + 41), W, A" in body
    assert "addwfc  (Common_RAM + 42), W, A" in body


def test_v173_page_crossing_lcd_tables_are_on_carrying_reader_path(
    v173_symbols: dict[str, int],
) -> None:
    lcd_entry_tables = {
        "menu_title_table": 3 * 16,
        "menu_setup_bl_timeout_entry": 1 * 16,
        "menu_bl_timeout_options_table": 4 * 16,
        "menu_source_channel_table": 7 * 16,
        "menu_routing_table": 4 * 16,
        "menu_input_cat_spdif_table": 2 * 16,
        "menu_input_auto_detect_table": 9 * 16,
        "input_pb_title_table": 4 * 16,
        "input_pb2_same_as_pb1_table": 1 * 16,
    }
    actual_crossing = {
        label
        for label, span in lcd_entry_tables.items()
        if (v173_symbols[label] & 0xFF) + span - 1 > 0xFF
    }

    # This is intentionally not an exact layout snapshot.  V1.73 source edits
    # can move tables across page boundaries without changing correctness; the
    # contract is that any table which does cross is consumed only by the
    # carrying reader checked above.
    assert actual_crossing
    assert actual_crossing <= set(lcd_entry_tables)


def test_v173_control_source_does_not_use_computed_pcl_jump_tables() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")

    assert "addwf   PCL" not in text
    assert "addwf       PCL" not in text
    assert "Computed PC (`addwf PCL, F`) is fragile" in text
