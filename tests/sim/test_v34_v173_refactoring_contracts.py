"""V3.4/V1.73 refactoring-release source contracts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import V173_CONTROL_ASM, V34_MAIN_ASM


def _label_body(text: str, label: str, next_labels: list[str] | tuple[str, ...]) -> str:
    start = re.search(rf"(?m)^{re.escape(label)}:\s*$", text)
    assert start is not None, f"missing label: {label}"
    ends: list[int] = []
    for next_label in next_labels:
        match = re.search(rf"(?m)^{re.escape(next_label)}:\s*$", text[start.end() :])
        if match is not None:
            ends.append(start.end() + match.start())
    end = min(ends) if ends else len(text)
    return text[start.start() : end]


def _assert_ordered(body: str, *needles: str) -> None:
    pos = -1
    for needle in needles:
        next_pos = body.find(needle, pos + 1)
        assert next_pos >= 0, f"missing {needle!r} after offset {pos}"
        pos = next_pos


def _main_ram_equates() -> dict[str, int]:
    inc = V34_MAIN_ASM.parent / "dlcp_main_ram.inc"
    equates: dict[str, int] = {}
    for line in inc.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^\s*(\w+)\s+EQU\s+0x([0-9A-Fa-f]+)\b", line)
        if match is not None:
            equates[match.group(1)] = int(match.group(2), 16)
    return equates


def _highest_listing_end_before_org(lst_text: str, org: int) -> int:
    highest = 0
    for line in lst_text.splitlines():
        match = re.match(r"^\s*([0-9A-Fa-f]{6})\s+(.*)$", line)
        if match is None:
            continue
        addr = int(match.group(1), 16)
        if addr >= org:
            continue
        line_no = re.search(r"\s+\d{5}\s+", match.group(2))
        if line_no is None:
            continue
        object_words = re.findall(r"\b[0-9A-Fa-f]{4}\b", match.group(2)[: line_no.start()])
        if object_words:
            highest = max(highest, addr + (2 * len(object_words)))
    return highest


def _assert_listing_fits_before(lst_path, org: int, *, min_margin: int) -> int:
    app_end = _highest_listing_end_before_org(
        lst_path.read_text(encoding="utf-8", errors="replace"),
        org,
    )
    margin = org - app_end
    assert margin >= min_margin, (
        f"{lst_path.name} app ends at 0x{app_end:04X}; only {margin} bytes remain "
        f"before 0x{org:04X}, required margin {min_margin}"
    )
    return margin


def _chain_copy_descriptors(text: str) -> list[list[str]]:
    descriptors: list[list[str]] = []
    for line in text.splitlines():
        if "chain_copy block descriptor" not in line:
            continue
        source = line.split(";", 1)[0]
        match = re.search(r"\bdb\b(.+)$", source)
        assert match is not None, f"descriptor line missing db: {line}"
        descriptors.append([token.strip() for token in match.group(1).split(",")])
    return descriptors


def _db_ints_for_label(text: str, label: str, next_labels: list[str] | tuple[str, ...]) -> list[int]:
    body = _label_body(text, label, next_labels)
    tokens: list[str] = []
    for line in body.splitlines():
        source = line.split(";", 1)[0]
        match = re.search(r"\bdb\b(.+)$", source)
        if match is not None:
            tokens.extend(token.strip() for token in match.group(1).split(","))
    assert tokens, f"missing db table for {label}"
    return [int(token, 16) for token in tokens]


def test_v34_identity_literals_are_v34_owned() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    identity = _label_body(text, "cmd25_identity_query_handler", ["cmd 0x26"])
    eeprom = text[text.index("org 0xF00000") :]

    assert "movlw       0x04                        ; V3.4: minor version = 4" in text
    assert "V3.4_RUNTIME_EEPROM_REV_LO" in text
    assert "movlw       0x04                        ; V3.4 identity minor" in identity
    assert "V3.4_IDENTITY_REV_LO_HI" in identity
    assert "V3.4_IDENTITY_REV_LO_LO" in identity
    assert "V3.4_IDENTITY_REV_HI_HI" in identity
    assert "V3.4_IDENTITY_REV_HI_LO" in identity
    assert re.search(r"\bdb\s+0x03,\s*0x04,\s*0x[0-9A-Fa-f]{2}\b", eeprom)
    assert "db  0x03, 0x03" not in eeprom


def test_v173_identity_literals_are_v173_owned() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    banner = _label_body(text, "control_release_banner_row1", ["control_release_metadata"])
    metadata = _label_body(text, "control_release_metadata", ["bootloader_entry"])

    assert '"Firmware V1.73"' in banner
    assert "build date" in metadata
    assert re.search(r"\bdb\s+0x01,\s*0x07,\s*0x33,\s*0x[0-9A-Fa-f]{2}\b", metadata)
    assert "db      0x01, 0x07, 0x32" not in metadata
    assert "EEPROM 0x72: .3. (V1.73)" in text


def test_v34_v173_listing_size_gates_keep_refactoring_headroom() -> None:
    v34_lst = V34_MAIN_ASM.with_suffix(".lst")
    v173_lst = V173_CONTROL_ASM.with_suffix(".lst")
    assert v34_lst.exists(), f"missing listing: {v34_lst}"
    assert v173_lst.exists(), f"missing listing: {v173_lst}"
    # 2026-06-16 size-reclaim goal raised the MAIN release floor to 2000 bytes
    # of contiguous free space before the fixed Preset-B table at 0x4C00.
    _assert_listing_fits_before(v34_lst, 0x4C00, min_margin=2000)
    _assert_listing_fits_before(v173_lst, 0x77B0, min_margin=128)


def test_v34_src4382_cold_init_table_preserves_exact_ordered_writes() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "main_i2c_service_32f8", ["main_i2c_service_32f8_table"])
    table = _db_ints_for_label(text, "main_i2c_service_32f8_table", ["i2c_secondary_write_rows"])

    assert list(zip(table[0::2], table[1::2])) == [
        (0x3F, 0x01),
        (0x30, 0x03),
        (0x01, 0x04),
        (0x08, 0x05),
        (0x01, 0x06),
        (0x34, 0x07),
        (0x30, 0x08),
        (0x08, 0x0D),
        (0x08, 0x0E),
        (0x22, 0x0F),
        (0x00, 0x10),
        (0x00, 0x11),
        (0x01, 0x1C),
        (0x01, 0x1D),
        (0x02, 0x2D),
        (0x20, 0x2E),
    ]
    _assert_ordered(
        body,
        "call        i2c_wait_bus_idle, 0x0",
        "movlw       LOW(main_i2c_service_32f8_table)",
        "movlw       HIGH(main_i2c_service_32f8_table)",
        "movlw       0x10",
        "bra         i2c_secondary_write_rows",
    )


def test_v34_standby_shutdown_secondary_write_table_preserves_rail_drop_order() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "hw_standby_shutdown", ["flow_hw_standby_shutdown_3c34"])
    table = _db_ints_for_label(text, "hw_standby_shutdown_i2c_table", ["main_core_service_3c82"])

    assert list(zip(table[0::2], table[1::2])) == [
        (0x00, 0x1B),
        (0x00, 0x1C),
        (0x00, 0x1D),
    ]
    _assert_ordered(
        body,
        "movlw       LOW(hw_standby_shutdown_i2c_table)",
        "movlw       HIGH(hw_standby_shutdown_i2c_table)",
        "movlw       0x03",
        "rcall       i2c_secondary_write_rows",
        "btfss       PORTC, 2, ACCESS",
    )


def test_v34_i2c_table_walker_uses_fault_safe_access_counter_and_no_tos_rewrite() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "i2c_secondary_write_rows", ["main_core_service_3398"])

    assert "TOSL" not in body
    assert "TOSH" not in body
    assert "FSR0" not in body
    assert "INDF0" not in body
    _assert_ordered(
        body,
        "clrf        TBLPTRU, ACCESS",
        "movwf       stock_008_acc, ACCESS",
        "tblrd*+",
        "movff       TABLAT, stock_006_b0_phys",
        "tblrd*+",
        "movf        TABLAT, W, ACCESS",
        "rcall       i2c_secondary_dev_write_mid_window",
        "decfsz      stock_008_acc, F, ACCESS",
        "return      0",
    )


def test_v34_boot_marker_check_accepts_0x77_or_0x88_with_single_eeprom_read() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "main_i2c_service_355c", ["flow_main_i2c_service_355c_35bc"])

    assert body.count("call        eeprom_read_byte, 0x0") == 1
    assert "xorlw       0x88" not in body
    _assert_ordered(
        body,
        "clrf        stock_004_acc, ACCESS",
        "setf        stock_003_acc, ACCESS",
        "call        eeprom_read_byte, 0x0",
        "xorlw       0x77",
        "bz          flow_main_i2c_service_355c_35bc",
        "xorlw       0xFF",
        "bz          flow_main_i2c_service_355c_35bc",
    )


def test_v34_main_i2c_service_2100_uses_bank0_clear_wrapper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "ram_block_clear_4_bank0_w", ["main_i2c_service_2100"])
    body = _label_body(text, "main_i2c_service_2100", ["main_i2c_service_2100_dispatch_table"])

    _assert_ordered(
        helper,
        "clrf        stock_004_acc, ACCESS",
        "movlb       0x0",
        "bra         ram_block_clear_4",
    )
    assert body.count("rcall       ram_block_clear_4_bank0_w") == 4
    assert body.count("rcall       prep_bank1_ram004") == 3
    _assert_ordered(
        body,
        "movlw       0xD7",
        "rcall       ram_block_clear_4_bank0_w",
        "movlw       0xDB",
        "rcall       ram_block_clear_4_bank0_w",
        "movlw       0xDF",
        "rcall       ram_block_clear_4_bank0_w",
        "rcall       prep_bank1_ram004",
        "movlw       0xD9",
        "rcall       ram_block_clear_4",
        "movlw       0xE3",
        "rcall       ram_block_clear_4_bank0_w",
        "rcall       prep_bank1_ram004",
        "movlw       0xDD",
        "rcall       ram_block_clear_4",
        "rcall       prep_bank1_ram004",
        "movlw       0xE1",
        "rcall       ram_block_clear_4",
    )


def test_v34_cmd_dispatch_reg1f_route3_reuses_existing_pair_setup() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    route3 = _label_body(text, "flow_cmd_dispatch_gated_1932", ["flow_cmd_dispatch_gated_194c"])
    reg1f = _label_body(text, "flow_cmd_dispatch_gated_1966", ["flow_cmd_dispatch_gated_1970"])

    _assert_ordered(
        route3,
        "movlw       0x08",
        "movwf       stock_006_acc, ACCESS",
        "movlw       0x30",
        "bra         cmd_dispatch_gated_i2c_pair",
    )
    _assert_ordered(
        reg1f,
        "call        main_core_service_4516, 0x0",
        "movlw       0x01",
        "call        i2c_tas3108_reg1f_write, 0x0",
        "bra         flow_cmd_dispatch_gated_1932",
    )
    assert "movwf       stock_006_acc, ACCESS" not in reg1f
    assert "bra         cmd_dispatch_gated_i2c_pair" not in reg1f


def test_v34_zero_peepholes_stay_compact_without_status_sensitive_reuse() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    volume = _label_body(
        text,
        "flow_cmd_dispatch_gated_volume_unmuted",
        ["flow_cmd_dispatch_gated_19d6"],
    )
    adaptive = _label_body(text, "adaptive_baud_select", ["s3_coeff_stage_049"])
    flash = _label_body(text, "main_flash_service_3ce8", ["flow_main_flash_service_3ce8_3d4e"])

    assert "movff       stock_0A4_b0_phys, stock_0B0_b0_phys" not in volume
    assert "bra         flow_cmd_dispatch_gated_19d6" not in volume
    _assert_ordered(
        volume,
        "clrf        stock_0A4_b0, BANKED",
        "clrf        stock_0B0_b0, BANKED",
        "clrf        stock_09A_b0, BANKED",
    )

    assert "movff       stock_093_b0_phys, stock_0AB_b0_phys" not in adaptive
    _assert_ordered(
        adaptive,
        "clrf        stock_093_b0, BANKED",
        "clrf        stock_0AB_b0, BANKED",
        "bcf         INTCON3, 4, ACCESS",
    )

    _assert_ordered(
        flash,
        "movff       stock_00A_b0_phys, POSTDEC2",
        "rcall       fsr2_bank0_from_stock007",
        "btfsc       stock_005_acc, 7, ACCESS",
        "bsf         INDF2, 0, ACCESS",
        "rcall       fsr2_bank0_from_stock007",
    )
    assert "movlw       0x00\n    iorwf       POSTDEC2, F, ACCESS" not in flash
    assert "iorwf       POSTINC2, F, ACCESS" not in flash
    assert "movf        POSTDEC2, F, ACCESS" not in flash


def test_v34_boolean_staging_uses_file_register_increment_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    expected = {
        "flow_hid_command_dispatch_12ca": (
            ["flow_hid_command_dispatch_12e0"],
            "stock_04C_acc",
            "btfsc       active_flags_acc, 4, ACCESS",
        ),
        "wake_request_handler": (
            ["standby_request_handler"],
            "stock_005_acc",
            "btfss       active_flags_acc, 3, ACCESS",
        ),
        "cmd03_stage_mute_refresh_w": (
            ["cmd03_mute_on_handler"],
            "stock_005_acc",
            "btfsc       active_flags_acc, 4, ACCESS",
        ),
        "flow_main_i2c_service_27f0_mute_status": (
            ["flow_main_i2c_service_27f0_295a"],
            "stock_008_acc",
            "btfsc       active_flags_acc, 4, ACCESS",
        ),
        "usb_endpoint_mark_done_fsr0": (
            ["flash_read"],
            "stock_006_acc",
            "btfss       INDF0, 6, ACCESS",
        ),
    }
    for label, (next_labels, scratch, bit_test) in expected.items():
        body = _label_body(text, label, next_labels)
        _assert_ordered(
            body,
            f"clrf        {scratch}, ACCESS",
            bit_test,
            f"incf        {scratch}, F, ACCESS",
        )
        assert f"movwf       {scratch}, ACCESS" not in body
    setup_copy = _label_body(text, "main_core_service_3c82", ["main_flash_service_3ce8"])
    reply_copy = _label_body(text, "main_core_service_3fd0", ["usb_endpoint_mark_done_fsr0"])
    _assert_ordered(
        setup_copy,
        "btfsc       stock_40C_b4, 7, BANKED",
        "return      0",
        "lfsr        FSR0, stock_40C_b4_phys",
        "bra         usb_endpoint_mark_done_fsr0",
    )
    _assert_ordered(
        reply_copy,
        "lfsr        FSR0, stock_410_b4_phys",
    )
    assert "bra         usb_endpoint_mark_done_fsr0" not in reply_copy
    assert "rcall       usb_endpoint_mark_done_fsr0" not in setup_copy
    assert "rcall       usb_endpoint_mark_done_fsr0" not in reply_copy
    cmd03_helper = _label_body(text, "cmd03_stage_mute_refresh_w", ["cmd03_mute_on_handler"])
    _assert_ordered(
        cmd03_helper,
        "clrf        stock_005_acc, ACCESS",
        "btfsc       active_flags_acc, 4, ACCESS",
        "incf        stock_005_acc, F, ACCESS",
        "btfsc       active_flags_acc, 5, ACCESS",
        "retlw       0x01",
        "retlw       0x00",
    )
    for label, next_labels in {
        "cmd03_mute_on_handler": ["flow_main_uart_service_1be6_1cc2"],
        "cmd03_mute_off_apply": ["cmd03_subdispatch"],
    }.items():
        body = _label_body(text, label, next_labels)
        _assert_ordered(
            body,
            "rcall       cmd03_stage_mute_refresh_w",
            "bra         flow_main_uart_service_1be6_1cc4",
        )
        assert "movwf       stock_005_acc, ACCESS" not in body
    mute_off = _label_body(text, "cmd03_mute_off_apply", ["cmd03_subdispatch"])
    _assert_ordered(
        mute_off,
        "bcf         preset_job_flags_b2, 1, BANKED",
        "rcall       cmd03_stage_mute_refresh_w",
        "bra         flow_main_uart_service_1be6_1cc4",
    )
    assert "bnz         flow_main_uart_service_1be6_1cc8" not in mute_off

    flash = _label_body(text, "main_flash_service_3ce8", ["flow_main_flash_service_3ce8_3d4e"])
    assert flash.count("rcall       fsr2_bank0_from_stock007") == 4
    _assert_ordered(
        flash,
        "rcall       fsr2_bank0_from_stock007",
        "clrf        POSTINC2, ACCESS",
        "clrf        POSTDEC2, ACCESS",
        "bra         flow_main_flash_service_3ce8_3d4c",
    )
    fsr2_helper = _label_body(text, "fsr2_bank0_from_stock007", ["flow_main_flash_service_3ce8_3d4e"])
    _assert_ordered(
        fsr2_helper,
        "movf        stock_007_acc, W, ACCESS",
        "movwf       FSR2L, ACCESS",
        "clrf        FSR2H, ACCESS",
        "return      0",
    )
    assert "movlw       0x00\n    movwf       POSTINC2, ACCESS" not in flash


def test_v34_hid_cmd04_staging_uses_shared_ordered_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    clean_body = _label_body(text, "flow_hid_command_dispatch_1140", ["flow_hid_command_dispatch_114a"])
    fault_body = _label_body(text, "flow_hid_command_dispatch_114a", ["flow_hid_command_dispatch_115c"])
    helper = _label_body(text, "hid_stage_0c1_04_0c2_01", ["flow_hid_command_dispatch_1140"])

    assert "rcall       hid_stage_0c1_04_0c2_01" in clean_body
    _assert_ordered(
        clean_body,
        "rcall       hid_stage_0c1_04_0c2_01",
        "bra         flow_hid_command_dispatch_112a",
    )
    _assert_ordered(
        fault_body,
        "movff       stock_11D_b1_phys, stock_0B8_b0_phys",
        "rcall       hid_stage_0c1_04_0c2_01",
        "bsf         dsp_fault_flags_b0, 0, BANKED",
        "bsf         stock_094_b0, 4, BANKED",
    )
    _assert_ordered(
        helper,
        "movlw       0x04",
        "movwf       stock_0C1_b0, BANKED",
        "movlw       0x01",
        "movwf       stock_0C2_b0, BANKED",
        "return      0",
    )


def test_v34_hid_settings_upload_rebuilds_route_bits_with_fsr2() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "flow_hid_command_dispatch_11ce", ["flow_hid_command_dispatch_124e"])

    for old_label in (
        "flow_hid_command_dispatch_11ee:",
        "flow_hid_command_dispatch_11fa:",
        "flow_hid_command_dispatch_11fe:",
        "flow_hid_command_dispatch_120a:",
        "flow_hid_command_dispatch_120e:",
        "flow_hid_command_dispatch_121a:",
        "flow_hid_command_dispatch_121e:",
        "flow_hid_command_dispatch_122a:",
        "flow_hid_command_dispatch_122e:",
        "flow_hid_command_dispatch_123a:",
        "flow_hid_command_dispatch_123e:",
        "flow_hid_command_dispatch_124a:",
    ):
        assert old_label not in text
    assert "btfsc       stock_124_b1, 0, BANKED" not in body
    assert body.count("btfsc       INDF2, 0, ACCESS") == 6
    assert body.count("incf        FSR2L, F, ACCESS") == 6
    _assert_ordered(
        body,
        "movlb       0x0",
        "bcf         stock_094_b0, 5, BANKED",
        "bcf         active_flags_acc, 4, ACCESS",
        "lfsr        FSR2, stock_123_b1_phys",
        "btfss       INDF2, 0, ACCESS",
        "bra         hid_settings_mute_done",
        "bsf         stock_094_b0, 5, BANKED",
        "bsf         active_flags_acc, 4, ACCESS",
        "hid_settings_mute_done:",
        "movf        stock_0A4_b0, W, BANKED",
        "andlw       0xC0",
        "movwf       stock_0A4_b0, BANKED",
        "lfsr        FSR2, stock_124_b1_phys",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         stock_0A4_b0, 0, BANKED",
        "incf        FSR2L, F, ACCESS",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         stock_0A4_b0, 1, BANKED",
        "incf        FSR2L, F, ACCESS",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         stock_0A4_b0, 2, BANKED",
        "incf        FSR2L, F, ACCESS",
        "incf        FSR2L, F, ACCESS",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         stock_0A4_b0, 3, BANKED",
        "incf        FSR2L, F, ACCESS",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         stock_0A4_b0, 4, BANKED",
        "incf        FSR2L, F, ACCESS",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         stock_0A4_b0, 5, BANKED",
    )


def test_v34_rail_adc_thresholds_use_shared_carry_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "rail_adc_cmp_hi02_w", ["hw_standby_shutdown"])
    boot = _label_body(text, "flow_adc_boot_gate_2dbc", ["adc_boot_gate_exit"])
    standby = _label_body(
        text,
        "flow_hw_standby_shutdown_3c3e",
        ["flow_hw_standby_shutdown_3c58"],
    )
    monitor = _label_body(text, "an0_hysteresis_monitor", ["flow_main_adc_service_4124_41ae"])

    _assert_ordered(
        helper,
        "movlb       0x0",
        "subwf       stock_088_b0, W, BANKED",
        "movlw       0x02",
        "subwfb      stock_089_b0, W, BANKED",
        "return      0",
    )
    _assert_ordered(
        boot,
        "movlw       0x36",
        "call        rail_adc_cmp_hi02_w, 0x0",
        "bc          adc_boot_gate_exit",
    )
    _assert_ordered(
        standby,
        "movlw       0x28",
        "rcall       rail_adc_cmp_hi02_w",
        "bc          flow_hw_standby_shutdown_3c78",
    )
    assert monitor.count("rcall       rail_adc_cmp_hi02_w") == 2
    _assert_ordered(
        monitor,
        "movlw       0x29",
        "rcall       rail_adc_cmp_hi02_w",
        "btfsc       STATUS, 0, ACCESS",
        "bsf         stock_094_b0, 2, BANKED",
    )
    _assert_ordered(
        monitor,
        "btfss       stock_094_b0, 2, BANKED",
        "bra         flow_main_adc_service_4124_41ae",
        "movlw       0x28",
        "rcall       rail_adc_cmp_hi02_w",
        "bc          flow_main_adc_service_4124_41ae",
    )


def test_v34_fw_update_addr77_compare_uses_shared_carry_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "fw_update_cmp_addr_77_w", ["fw_update_relay"])
    add_helper = _label_body(text, "fw_update_add_w_to_08081", ["fw_update_relay"])
    body = _label_body(text, "fw_update_relay", ["main_core_service_184a"])
    hex_helper = _label_body(text, "hex_byte_to_postinc2_from_01b", ["hex_lookup_table_ptr"])
    tx_block_helper = _label_body(
        text,
        "fw_update_tx_block0190_from_w",
        ["flow_fw_update_relay_172a"],
    )

    _assert_ordered(
        helper,
        "movlb       0x0",
        "subwf       stock_084_b0, W, BANKED",
        "movlw       0x77",
        "subwfb      stock_085_b0, W, BANKED",
        "return      0",
    )
    assert body.count("rcall       fw_update_cmp_addr_77_w") == 4
    for threshold in ("0xC0", "0xBF"):
        assert f"movlw       {threshold}\n    rcall       fw_update_cmp_addr_77_w" in body
    _assert_ordered(
        add_helper,
        "movlb       0x0",
        "addwf       stock_080_b0, F, BANKED",
        "movlw       0x00",
        "addwfc      stock_081_b0, F, BANKED",
        "return      0",
    )
    assert body.count("rcall       fw_update_add_w_to_08081") == 3
    assert body.count("rcall       fw_update_tx_block0190_from_w") == 3
    _assert_ordered(
        tx_block_helper,
        "clrf        stock_019_acc, ACCESS",
        "movwf       stock_018_acc, ACCESS",
        "goto        uart_tx_block_from_buffer",
    )
    assert (
        "clrf        stock_019_acc, ACCESS\n"
        "    movlw       0x1D\n"
        "    movwf       stock_018_acc, ACCESS\n"
        "    call        uart_tx_block_from_buffer, 0x0"
    ) not in body
    assert (
        "movwf       stock_01B_acc, ACCESS\n"
        "    clrf        stock_019_acc, ACCESS\n"
        "    movff       stock_01B_b0_phys, stock_018_b0_phys\n"
        "    call        uart_tx_block_from_buffer, 0x0"
    ) not in body
    assert (
        "clrf        stock_019_acc, ACCESS\n"
        "    movlw       0x2F\n"
        "    movwf       stock_018_acc, ACCESS\n"
        "    call        uart_tx_block_from_buffer, 0x0"
    ) not in body
    assert (
        "movlw       0x0F\n"
        "    andwf       stock_01B_acc, F, ACCESS\n"
        "    andwf       stock_01B_acc, F, ACCESS"
    ) not in body
    _assert_ordered(
        body,
        "movlw       0x9A",
        "rcall       setup_fsr2_page_1_or_2",
        "movff       stock_080_b0_phys, stock_01B_b0_phys",
        "rcall       hex_byte_to_postinc2_from_01b",
        "clrf        INDF2, ACCESS",
        "movlw       0x02",
        "addwf       stock_04B_acc, F, ACCESS",
    )
    assert "rcall       hex_lookup_table_ptr                ; indexed TBLPTR -> hex_lookup_table" not in body
    _assert_ordered(
        body,
        "lfsr        FSR2, stock_19D_b1_phys",
        "movff       stock_087_b0_phys, stock_01B_b0_phys",
        "rcall       hex_byte_to_postinc2_from_01b",
        "movff       stock_086_b0_phys, stock_01B_b0_phys",
        "rcall       hex_byte_to_postinc2_from_01b",
    )
    _assert_ordered(
        body,
        "lfsr        FSR2, stock_02F_b0_phys",
        "movff       stock_046_b0_phys, stock_01B_b0_phys",
        "rcall       hex_byte_to_postinc2_from_01b",
        "movff       stock_04A_b0_phys, stock_01B_b0_phys",
        "rcall       hex_byte_to_postinc2_from_01b",
    )
    _assert_ordered(
        hex_helper,
        "movff       stock_01B_b0_phys, stock_01C_b0_phys",
        "swapf       stock_01B_acc, F, ACCESS",
        "rcall       hex_01b_low_nibble_to_postinc2",
        "movff       stock_01C_b0_phys, stock_01B_b0_phys",
        "bra         hex_01b_low_nibble_to_postinc2",
        "hex_01b_low_nibble_to_postinc2:",
        "movlw       0x0F",
        "andwf       stock_01B_acc, F, ACCESS",
        "movf        stock_01B_acc, W, ACCESS",
        "rcall       hex_lookup_table_ptr",
        "tblrd*",
        "movff       TABLAT, POSTINC2",
        "return      0",
    )
    assert "nibble_to_hex_ascii_from_01B" not in hex_helper


def test_v34_fw_update_stages_005_and_008_with_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "fw_update_stage_005_w_008_1", ["clear_fw_update_status_accumulators"])
    init = _label_body(text, "fw_update_init_sequence", ["flow_hid_command_dispatch_14fc"])
    relay = _label_body(text, "flow_fw_update_relay_16fa", ["flow_fw_update_relay_172a"])
    clear_helper = _label_body(
        text,
        "fw_update_ram_clear_len_w",
        ["clear_fw_update_status_accumulators"],
    )

    _assert_ordered(
        helper,
        "movwf       stock_005_acc, ACCESS",
        "movlb       0x1",
        "movlw       0x01",
        "movwf       stock_008_acc, ACCESS",
        "return      0",
    )
    _assert_ordered(init, "movlw       0xDC", "rcall       fw_update_stage_005_w_008_1")
    _assert_ordered(
        init,
        "rcall       clear_fw_update_status_accumulators",
        "call        prep_bank1_ram004, 0x0",
        "movlw       0xC7",
        "rcall       fw_update_ram_clear_len_w",
        "movlw       0x9A",
        "rcall       fw_update_ram_clear_len_w",
        "movlw       0xD1",
        "rcall       fw_update_ram_clear_len_w",
    )
    assert init.count("rcall       fw_update_ram_clear_len_w") == 3
    assert "call        ram_block_clear, 0x0" not in init
    _assert_ordered(
        clear_helper,
        "movwf       stock_005_acc, ACCESS",
        "goto        ram_block_clear",
    )
    assert init.count("call        prep_bank1_ram004, 0x0") == 1
    _assert_ordered(relay, "movlw       0x0A", "rcall       fw_update_stage_005_w_008_1")


def test_v34_cmd19_status_bit_fanout_uses_rotate_carry_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(
        text,
        "flow_main_core_service_2328_2380",
        ["flow_main_core_service_2328_240c"],
    )
    helper = _label_body(text, "status_fanout3_from_006_to_fsr2", ["main_core_service_24ac"])

    _assert_ordered(
        body,
        "clrf        stock_163_b1, BANKED",
        "btfsc       active_flags_acc, 4, ACCESS",
        "incf        stock_163_b1, F, BANKED",
        "movff       stock_0A4_b0_phys, stock_006_b0_phys",
        "lfsr        FSR2, stock_164_b1_phys",
        "movlw       0x03",
        "rcall       status_fanout3_from_006_to_fsr2",
        "incf        FSR2L, F, ACCESS",
        "movlw       0x03",
        "rcall       status_fanout3_from_006_to_fsr2",
    )
    _assert_ordered(
        helper,
        "rrcf        stock_006_acc, F, ACCESS",
        "clrf        INDF2, ACCESS",
        "rlcf        POSTINC2, F, ACCESS",
        "decfsz      WREG, F, ACCESS",
        "bra         status_fanout3_from_006_to_fsr2",
        "return      0",
    )
    assert "clrf        stock_164_b1, BANKED" not in body
    assert "clrf        stock_168_b1, BANKED" not in body
    assert "movlb       0x0\n    btfsc       stock_0A4_b0" not in body
    assert "movwf       stock_164_b1, BANKED" not in body


def test_v34_volume_logical_diff_uses_shared_z_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    hid = _label_body(text, "flow_hid_command_dispatch_124e", ["flow_hid_command_dispatch_12a2"])
    uart = _label_body(text, "volume_cmd_handler", ["flow_main_uart_service_1be6_1d80"])
    helper = _label_body(text, "volume_logical_diff_z", ["main_core_service_15b0"])

    _assert_ordered(
        hid,
        "movf        input_select_mirror_b0, W, BANKED",
        "xorwf       input_select_b0, W, BANKED",
        "btfss       STATUS, 2, ACCESS",
        "bsf         stock_094_b0, 0, BANKED",
        "rcall       volume_logical_diff_z",
        "flow_hid_command_dispatch_129c:",
        "bz          flow_hid_command_dispatch_12a2",
    )
    _assert_ordered(
        uart,
        "movwf       computed_volume_2_b0, BANKED",
        "movwf       computed_volume_3_b0, BANKED",
        "rcall       volume_logical_diff_z",
        "flow_main_uart_service_1be6_1d68:",
        "bz          flow_main_uart_service_1be6_1e6c",
    )
    _assert_ordered(
        helper,
        "movlb       0x0",
        "movf        logical_volume_3_b0, W, BANKED",
        "xorwf       computed_volume_3_b0, W, BANKED",
        "bnz         volume_logical_diff_ret",
        "movf        logical_volume_2_b0, W, BANKED",
        "xorwf       computed_volume_2_b0, W, BANKED",
        "bnz         volume_logical_diff_ret",
        "movf        logical_volume_1_b0, W, BANKED",
        "xorwf       computed_volume_1_b0, W, BANKED",
        "bnz         volume_logical_diff_ret",
        "movf        logical_volume_b0, W, BANKED",
        "xorwf       computed_volume_b0, W, BANKED",
        "volume_logical_diff_ret:",
        "return      0",
    )
    assert hid.count("rcall       volume_logical_diff_z") == 1
    assert uart.count("rcall       volume_logical_diff_z") == 1


def test_v34_eeprom_write_gie_snapshot_uses_increment_boolean_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "eeprom_write_blocking", ["main_flash_service_4406"])

    _assert_ordered(
        body,
        "bsf         EECON1, 2, ACCESS",
        "clrf        stock_006_acc, ACCESS",
        "btfsc       INTCON, 7, ACCESS",
        "incf        stock_006_acc, F, ACCESS",
        "bcf         INTCON, 7, ACCESS",
        "rcall       main_flash_service_4406",
    )
    assert "movlw       0x00\n    btfsc       INTCON, 7, ACCESS" not in body
    assert "movwf       stock_006_acc, ACCESS" not in body


def test_v34_flash_page_c0_setup_uses_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "flash_addr_setup_page_c0_0300", ["main_flash_service_2bb8"])
    body = _label_body(text, "main_flash_service_2bb8", ["main_core_service_2ca8"])

    _assert_ordered(
        helper,
        "rcall       flash_addr_setup_from_82_83",
        "clrf        stock_008_acc, ACCESS",
        "movlw       0xC0",
        "movwf       stock_007_acc, ACCESS",
        "movlb       0x3",
        "movlw       0x03",
        "movwf       stock_00A_acc, ACCESS",
        "clrf        stock_009_acc, ACCESS",
        "return      0",
    )
    assert body.count("rcall       flash_addr_setup_page_c0_0300") == 2
    assert (
        "rcall       flash_addr_setup_from_82_83\n"
        "    clrf        stock_008_acc, ACCESS\n"
        "    movlw       0xC0"
    ) not in body


def test_v34_flash_write_reuses_tblptr_stage_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "flash_stage_tblptr_from_014_016", ["flow_flash_write_2eb6"])
    body = _label_body(text, "flow_flash_write_2eb6", ["main_usb_service_2f4e"])

    _assert_ordered(
        helper,
        "movff       stock_016_b0_phys, stock_013_b0_phys",
        "movff       stock_015_b0_phys, stock_012_b0_phys",
        "movff       stock_014_b0_phys, stock_011_b0_phys",
        "return      0",
    )
    assert body.count("rcall       flash_stage_tblptr_from_014_016") == 2
    assert (
        "movff       stock_016_b0_phys, stock_013_b0_phys\n"
        "    movff       stock_015_b0_phys, stock_012_b0_phys\n"
        "    movff       stock_014_b0_phys, stock_011_b0_phys"
    ) not in body


def test_v34_flash_and_core30d8_share_004_006_carry_propagation() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "carry_propagate_004_006", ["flow_flash_write_2eb6"])
    flash = _label_body(text, "flash_write_stock", ["main_usb_service_2f4e"])
    core_30d8 = _label_body(text, "main_core_service_30d8", ["main_core_service_3188"])

    _assert_ordered(
        helper,
        "movlw       0x00",
        "addwfc      stock_004_acc, F, ACCESS",
        "addwfc      stock_005_acc, F, ACCESS",
        "addwfc      stock_006_acc, F, ACCESS",
        "return      0",
    )
    _assert_ordered(
        flash,
        "movlw       0x20",
        "addwf       stock_003_acc, F, ACCESS",
        "rcall       carry_propagate_004_006",
    )
    _assert_ordered(
        core_30d8,
        "incf        stock_003_acc, F, ACCESS",
        "rcall       carry_propagate_004_006",
        "rcall       main_core_service_3188",
    )
    assert text.count("rcall       carry_propagate_004_006") == 2


def test_v34_core30d8_keeps_live_exponent_or_without_scratch_zero_fanout() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "main_core_service_30d8", ["main_core_service_3188"])

    _assert_ordered(
        body,
        "movlw       0xFE",
        "andwf       stock_006_acc, W, ACCESS",
        "bz          flow_main_core_service_30d8_311a",
    )
    _assert_ordered(
        body,
        "movf        stock_006_acc, W, ACCESS",
        "bz          flow_main_core_service_30d8_313c",
    )
    _assert_ordered(
        body,
        "rrcf        stock_007_acc, F, ACCESS",
        "movf        stock_007_acc, W, ACCESS",
        "iorwf       stock_006_acc, F, ACCESS",
        "clrf        stock_009_acc, ACCESS",
        "clrf        stock_00A_acc, ACCESS",
        "clrf        stock_00B_acc, ACCESS",
        "clrf        stock_00C_acc, ACCESS",
        "tstfsz      stock_008_acc, ACCESS",
    )
    for dead in (
        "movwf       stock_00C_acc, ACCESS\n    iorwf       stock_009_acc, W, ACCESS",
        "movwf       stock_00C_acc, ACCESS\n    iorwf       stock_009_acc, W, ACCESS",
        "clrf        stock_009_acc, ACCESS\n    movf        stock_009_acc, W, ACCESS",
        "movf        stock_00C_acc, W, ACCESS\n    iorwf       stock_006_acc, F, ACCESS",
        "movff       stock_007_b0_phys, timeout_hi_b0_phys",
    ):
        assert dead not in body


def test_v34_flash_write_stock_uses_chain_copy_for_address_snapshot() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "flash_write_stock", ["flow_flash_write_2eb6"])

    for old_copy in (
        "movff       stock_003_b0_phys, stock_014_b0_phys",
        "movff       stock_004_b0_phys, stock_015_b0_phys",
        "movff       saved_w_b0_phys, stock_016_b0_phys",
        "movff       stock_006_b0_phys, stock_017_b0_phys",
    ):
        assert old_copy not in body
    _assert_ordered(
        body,
        "clrf        stock_010_acc, ACCESS",
        "rcall       chain_copy",
        "db          0x00, 0x00, stock_003_acc_op, stock_014_acc_op, 0x04, 0xFF",
        "movlw       0x05",
        "movwf       stock_00B_acc, ACCESS",
    )


def test_v34_math_operand_middle_copy_uses_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "math_stage_025_027_to_029_02b", ["main_core_service_297e"])
    early = _label_body(text, "main_core_service_24c2", ["main_core_service_263e"])
    s3 = _label_body(text, "s3_math_stage_029", ["main_core_service_301a"])

    _assert_ordered(
        helper,
        "rcall       chain_copy",
        "db          0x00, 0x00, stock_025_acc_op, stock_029_acc_op, 0x03, 0xFF",
        "return      0",
    )
    _assert_ordered(
        early,
        "movff       stock_024_b0_phys, stock_028_b0_phys",
        "rcall       math_stage_025_027_to_029_02b",
        "rcall       repeat_18_main_core_service_2650",
    )
    _assert_ordered(
        s3,
        "rcall       math_stage_025_027_to_029_02b",
        "movff       stock_028_b0_phys, stock_02C_b0_phys",
        "return      0",
    )
    assert early.count("rcall       math_stage_025_027_to_029_02b") == 1
    assert s3.count("rcall       math_stage_025_027_to_029_02b") == 1


def test_v34_s3_math_and_adc_helpers_use_chain_copy_descriptors() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    math = _label_body(text, "s3_math_stage_025", ["main_core_service_2d80"])
    adc = _label_body(text, "s3_adc_stage_427a", ["flow_main_core_service_34c8_3504"])

    for old_copy in (
        "movff       stock_02F_b0_phys, stock_025_b0_phys",
        "movff       stock_030_b0_phys, stock_026_b0_phys",
        "movff       stock_031_b0_phys, stock_027_b0_phys",
        "movff       stock_032_b0_phys, stock_028_b0_phys",
    ):
        assert old_copy not in math
    for old_copy in (
        "movff       stock_00A_b0_phys, stock_003_b0_phys",
        "movff       timeout_lo_b0_phys, stock_004_b0_phys",
        "movff       timeout_hi_b0_phys, saved_w_b0_phys",
        "movff       stock_00D_b0_phys, stock_006_b0_phys",
    ):
        assert old_copy not in adc

    _assert_ordered(
        math,
        "rcall       chain_copy",
        "db          0x00, 0x00, stock_02F_acc_op, stock_025_acc_op, 0x04, 0xFF",
        "return      0",
    )
    _assert_ordered(
        adc,
        "rcall       chain_copy",
        "db          0x00, 0x00, stock_00A_acc_op, stock_003_acc_op, 0x04, 0xFF",
        "return      0",
    )


def test_v34_adc_division_compare_subtract_is_shared() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "adc_div_compare_subtract_003004_by_005006", ["an0_hysteresis_monitor"])
    adc_div = _label_body(text, "main_adc_service_4124", ["an0_hysteresis_monitor"])
    core_div = _label_body(text, "main_core_service_427a", ["flash_write_with_gie_off"])

    _assert_ordered(
        helper,
        "movf        stock_005_acc, W, ACCESS",
        "subwf       stock_003_acc, W, ACCESS",
        "movf        stock_006_acc, W, ACCESS",
        "subwfb      stock_004_acc, W, ACCESS",
        "bnc         adc_div_compare_subtract_done",
        "movf        stock_005_acc, W, ACCESS",
        "subwf       stock_003_acc, F, ACCESS",
        "movf        stock_006_acc, W, ACCESS",
        "subwfb      stock_004_acc, F, ACCESS",
        "adc_div_compare_subtract_done:",
        "return      0",
    )
    _assert_ordered(
        adc_div,
        "rlcf        stock_008_acc, F, ACCESS",
        "rcall       adc_div_compare_subtract_003004_by_005006",
        "btfsc       STATUS, 0, ACCESS",
        "bsf         stock_007_acc, 0, ACCESS",
    )
    _assert_ordered(
        core_div,
        "btfss       stock_006_acc, 7, ACCESS",
        "rcall       adc_div_compare_subtract_003004_by_005006",
        "bcf         STATUS, 0, ACCESS",
    )


def test_v34_usb_endpoint_clear_uses_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "usb_clear_uep1_7", ["main_usb_service_40d6"])
    reset = _label_body(text, "main_usb_service_40d6", ["main_core_service_41b6"])
    reinit = _label_body(text, "main_usb_service_41fe", ["i2c_secondary_dev_random_read"])

    _assert_ordered(
        helper,
        "clrf        UEP1, ACCESS",
        "clrf        UEP2, ACCESS",
        "clrf        UEP3, ACCESS",
        "clrf        UEP4, ACCESS",
        "clrf        UEP5, ACCESS",
        "clrf        UEP6, ACCESS",
        "clrf        UEP7, ACCESS",
        "return      0",
    )
    _assert_ordered(reset, "clrf        UADDR, ACCESS", "rcall       usb_clear_uep1_7", "movlw       0x16")
    _assert_ordered(reinit, "movwf       stock_0C8_b0, BANKED", "rcall       usb_clear_uep1_7", "clrf        stock_091_b0, BANKED")
    assert reset.count("clrf        UEP1, ACCESS") == 0
    assert reinit.count("clrf        UEP1, ACCESS") == 0


def test_v34_usb_descriptor_tblptr_staging_uses_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "usb_stage_tblptr_from_075_076", ["main_flash_service_365c"])
    setup = _label_body(text, "main_flash_service_365c", ["main_core_service_3672"])
    descriptor = _label_body(text, "main_flash_service_3796", ["main_flash_service_3810"])

    _assert_ordered(
        helper,
        "movff       stock_075_b0_phys, TBLPTRL",
        "movff       stock_076_b0_phys, TBLPTRH",
        "clrf        TBLPTRU, ACCESS",
        "return      0",
    )
    _assert_ordered(
        setup,
        "rcall       usb_stage_tblptr_from_075_076",
        "rcall       fsr2_from_stock072073",
        "retlw       0x07",
    )
    _assert_ordered(
        descriptor,
        "movff       TABLAT, stock_075_b0_phys",
        "movwf       stock_076_b0, BANKED",
        "rcall       usb_stage_tblptr_from_075_076",
        "movlw       0x07",
    )
    assert setup.count("rcall       usb_stage_tblptr_from_075_076") == 1
    assert descriptor.count("rcall       usb_stage_tblptr_from_075_076") == 1


def test_v34_return_value_tails_use_retlw() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    usb_setup = _label_body(text, "main_flash_service_365c", ["main_core_service_3672"])
    signed = _label_body(text, "signed_hi_bias80_compare_prelude", ["main_usb_service_3a26"])

    assert "retlw       0x07" in usb_setup
    assert "movlw       0x07\n    return      0" not in usb_setup
    assert "retlw       0x00" in signed
    assert "movlw       0x00\n    return      0" not in signed


def test_v34_fsr2_from_stock072073_is_shared() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "fsr2_from_stock072073", ["main_core_service_34c8"])
    filter_body = _label_body(text, "main_core_service_3432", ["fsr2_from_stock072073"])
    setup = _label_body(text, "main_flash_service_365c", ["main_core_service_3672"])
    dispatch = _label_body(text, "main_core_service_3710", ["main_flash_service_3796"])
    standby = _label_body(text, "hw_standby_shutdown", ["hw_standby_shutdown_i2c_table"])

    _assert_ordered(
        helper,
        "movff       stock_072_b0_phys, FSR2L",
        "movff       stock_073_b0_phys, FSR2H",
        "return      0",
    )
    assert filter_body.count("rcall       fsr2_from_stock072073") == 4
    assert setup.count("rcall       fsr2_from_stock072073") == 1
    assert dispatch.count("rcall       fsr2_from_stock072073") == 1
    assert "movff       stock_072_b0_phys, FSR2L" not in filter_body
    assert "movff       stock_073_b0_phys, FSR2H" not in filter_body
    _assert_ordered(
        standby,
        "movlw       0x03",
        "rcall       i2c_secondary_write_rows",
        "btfss       PORTC, 2, ACCESS",
    )


def test_v34_usb_descriptor_dirty_return_tail_is_shared() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    lowpage = _label_body(text, "usb_stage_lowpage_descriptor_dirty_w", ["usb_stage_descriptor_dirty_return"])
    helper = _label_body(text, "usb_stage_descriptor_dirty_return", ["usb_service_4080_update_stock096"])
    setup = _label_body(text, "main_core_service_3188", ["usb_service_4080_update_stock096"])
    descriptor = _label_body(text, "main_core_service_3682", ["main_core_service_3710"])

    _assert_ordered(
        lowpage,
        "clrf        stock_076_b0, BANKED",
        "movwf       stock_075_b0, BANKED",
    )
    _assert_ordered(
        helper,
        "bcf         stock_0CE_b0, 1, BANKED",
        "movlw       0x01",
        "movwf       stock_0E7_b0, BANKED",
        "return      0",
    )
    _assert_ordered(
        setup,
        "flow_main_core_service_3188_3200:",
        "movlw       0xEA",
        "bra         usb_stage_lowpage_descriptor_dirty_w",
        "flow_main_core_service_3188_321c:",
        "movlw       0xE9",
        "bra         usb_stage_lowpage_descriptor_dirty_w",
    )
    _assert_ordered(
        descriptor,
        "flow_main_core_service_3682_36a2:",
        "movlw       0xEB",
        "bra         usb_stage_lowpage_descriptor_dirty_w",
        "movff       saved_w_b0_phys, stock_075_b0_phys",
        "bra         usb_stage_descriptor_dirty_return",
    )
    assert "flow_main_core_service_3188_3208:" not in setup
    assert "flow_main_core_service_3682_36ac:" not in descriptor


def test_v34_usb_service_4080_stock096_update_uses_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "usb_service_4080_update_stock096", ["flow_main_core_service_3188_324c"])
    body = _label_body(text, "flow_main_core_service_3188_324c", ["main_i2c_service_32f8"])
    core_4080 = _label_body(text, "main_core_service_4080", ["usb_clear_uep1_7"])

    _assert_ordered(
        helper,
        "decf        stock_096_b0, W, BANKED",
        "bnz         usb_service_4080_update_stock096_nonzero",
        "movlw       0x01",
        "rcall       main_core_service_4080_window",
        "clrf        stock_096_b0, BANKED",
        "return      0",
        "movlw       0x00",
        "rcall       main_core_service_4080_window",
        "movlw       0x01",
        "movwf       stock_096_b0, BANKED",
        "return      0",
    )
    assert body.count("rcall       usb_service_4080_update_stock096") == 2
    assert core_4080.count("movwf       stock_119_b1, BANKED") == 1
    _assert_ordered(
        core_4080,
        "lfsr        FSR0, stock_116_b1_phys",
        "movlw       0x04",
        "call        copy_postinc0_to_postinc2_count_w, 0x0",
        "movlw       0xFC",
        "addwf       FSR2L, F, ACCESS",
        "bsf         INDF2, 7, ACCESS",
    )
    assert "movff       stock_078_b0_phys, FSR2L" not in core_4080
    assert "movff       stock_079_b0_phys, FSR2H" not in core_4080
    assert core_4080.count("movwf       FSR2H, ACCESS") == 1
    assert "tstfsz      stock_003_acc, ACCESS\n    bra         flow_main_core_service_4080_40a8\n    movlw       0x04\n    movwf       stock_119_b1, BANKED" not in core_4080
    assert "bnz         flow_main_core_service_3188_326c" not in body
    assert "bnz         flow_main_core_service_3188_32dc" not in body
    assert "flow_main_core_service_3188_326c:" not in body
    assert "flow_main_core_service_3188_32dc:" not in body


def test_v34_usb_stock116_store_uses_bsr0_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "usb_store_stock116_w_bsr0", ["adaptive_baud_select"])
    service = _label_body(text, "flow_main_core_service_3188_324c", ["main_i2c_service_32f8"])
    reset = _label_body(text, "main_usb_service_40d6", ["main_core_service_41b6"])

    _assert_ordered(
        helper,
        "movlb       0x1",
        "movwf       stock_116_b1, BANKED",
        "movlb       0x0",
        "return      0",
    )
    assert service.count("rcall       usb_store_stock116_w_bsr0") == 4
    assert reset.count("rcall       usb_store_stock116_w_bsr0") == 1
    _assert_ordered(
        service,
        "movlw       0x04",
        "rcall       usb_store_stock116_w_bsr0",
        "rcall       usb_service_4080_update_stock096",
        "movlw       0x48",
        "rcall       usb_store_stock116_w_bsr0",
        "movlw       0x01",
        "rcall       main_core_service_4080_window",
        "movlw       0x04",
        "rcall       usb_store_stock116_w_bsr0",
        "movf        stock_0D6_b0, W, BANKED",
        "movlw       0x48",
        "rcall       usb_store_stock116_w_bsr0",
    )
    _assert_ordered(
        reset,
        "movlw       0x04",
        "rcall       usb_store_stock116_w_bsr0",
        "movlw       0x00",
        "rcall       main_core_service_4080",
    )


def test_v34_usb_offset_ec_paths_share_0c8_0d3_prelude() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "usb_stage_0c8_0d3_offset_ec", ["flow_main_core_service_3682_36c0"])
    body = _label_body(text, "main_core_service_3682", ["main_core_service_3710"])

    _assert_ordered(
        helper,
        "movlw       0x01",
        "movwf       stock_0C8_b0, BANKED",
        "movf        stock_0D3_b0, W, BANKED",
        "addlw       0xEC",
        "return      0",
    )
    _assert_ordered(
        body,
        "flow_main_core_service_3682_36c0:",
        "rcall       usb_stage_0c8_0d3_offset_ec",
        "movwf       stock_005_acc, ACCESS",
        "flow_main_core_service_3682_36d2:",
        "rcall       usb_stage_0c8_0d3_offset_ec",
        "movwf       FSR2L, ACCESS",
    )
    assert body.count("rcall       usb_stage_0c8_0d3_offset_ec") == 2


def test_v34_channel_config_handlers_share_offset_indexed_mirror_dirty_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    dispatch = _label_body(
        text,
        "cmd_dispatch_xor_chain",
        ["flow_main_uart_service_1be6_1e6c"],
    )
    body = _label_body(
        text,
        "uart_channel_config_cache_from_00c",
        ["flow_main_uart_service_1be6_1e02"],
    )
    helper = _label_body(
        text,
        "uart_update_channel_config_cache_w",
        ["flow_main_uart_service_1be6_1e02"],
    )

    assert "movff       current_cmd_data_b0_phys, stock_060_b0_phys" not in body
    assert "xorwf       stock_0A5_b0, W, BANKED" not in body
    _assert_ordered(
        dispatch,
        "movf        stock_0A2_b0, W, BANKED",
        "addlw       0xE9",
        "movwf       stock_00C_acc, ACCESS",
        "sublw       0x05",
        "bc          uart_channel_config_cache_from_00c",
    )
    _assert_ordered(
        body,
        "uart_channel_config_cache_from_00c:",
        "movf        stock_00C_acc, W, ACCESS",
        "uart_update_channel_config_cache_w:",
    )
    assert "bra         uart_update_channel_config_cache_w" not in dispatch
    assert helper.count("cpfseq") == 1
    _assert_ordered(
        helper,
        "addlw       stock_060_b0_op",
        "movwf       FSR0L, ACCESS",
        "clrf        FSR0H, ACCESS",
        "movlw       0x45",
        "addwf       FSR0L, W, ACCESS",
        "movwf       FSR1L, ACCESS",
        "clrf        FSR1H, ACCESS",
        "movlb       0x0",
        "movf        current_cmd_data_b0, W, BANKED",
        "movwf       INDF0, ACCESS",
        "cpfseq      INDF1, ACCESS",
        "bsf         event_flags_b0, 4, BANKED",
        "movwf       INDF1, ACCESS",
        "bra         flow_main_uart_service_1be6_1e6c",
    )


def test_v34_hid_route_cache_compare_uses_shared_z_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    filename = _label_body(
        text,
        "flow_hid_command_dispatch_12a2",
        ["flow_hid_command_dispatch_12e0"],
    )
    body = _label_body(
        text,
        "flow_hid_command_dispatch_12e0",
        ["flow_hid_command_dispatch_1344"],
    )
    helper = _label_body(
        text,
        "ram_pair_diff_z",
        ["main_core_service_15b0"],
    )

    assert "xorwf       stock_09B_b0, W, BANKED" not in filename
    assert filename.count("bsf         filename_dirty_flags_b0, 3, BANKED") == 1
    _assert_ordered(
        filename,
        "lfsr        FSR0, stock_0AC_b0_phys",
        "lfsr        FSR1, stock_09B_b0_phys",
        "movlw       0x04",
        "rcall       ram_pair_diff_z",
        "btfsc       STATUS, 2, ACCESS",
        "bra         flow_hid_command_dispatch_12ca",
        "bsf         event_flags_b0, 3, BANKED",
        "bsf         filename_dirty_flags_b0, 3, BANKED",
    )
    assert "cpfseq      stock_0A5_b0, BANKED" not in body
    assert "lfsr        FSR2, stock_061_b0_phys" not in body
    _assert_ordered(
        body,
        "movf        stock_0B4_b0, W, BANKED",
        "xorwf       stock_0B1_b0, W, BANKED",
        "btfss       STATUS, 2, ACCESS",
        "bsf         dsp_fault_flags_b0, 1, BANKED",
        "lfsr        FSR0, stock_060_b0_phys",
        "lfsr        FSR1, stock_0A5_b0_phys",
        "movlw       0x06",
        "rcall       ram_pair_diff_z",
        "btfss       STATUS, 2, ACCESS",
        "flow_hid_command_dispatch_1324:",
        "bsf         event_flags_b0, 4, BANKED",
    )
    _assert_ordered(
        helper,
        "movwf       stock_04C_acc, ACCESS",
        "ram_pair_diff_loop:",
        "movf        POSTINC0, W, ACCESS",
        "xorwf       POSTINC1, W, ACCESS",
        "bnz         ram_pair_diff_ret",
        "decfsz      stock_04C_acc, F, ACCESS",
        "bra         ram_pair_diff_loop",
        "ram_pair_diff_ret:",
        "return      0",
    )


def test_v34_wreg_access_stores_use_single_word_movwf_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    movff_wreg = re.findall(r"(?m)^\s*movff\s+WREG,\s+([^;\s]+)", text)

    assert movff_wreg == ["stock_0FD_b0_phys"]
    for target in [
        "i2c_coeff_2_acc",
        "stock_011_acc",
        "saved_w_acc",
        "stock_02D_acc",
        "stock_037_acc",
        "stock_003_acc",
        "stock_017_acc",
        "stock_006_acc",
        "stock_01B_acc",
        "stock_007_acc",
        "stock_004_acc",
    ]:
        assert f"movwf       {target}, ACCESS" in text

    for redundant in [
        "movwf       saved_w_acc, ACCESS\n    movff       saved_w_b0_phys, SSPBUF",
        "movwf       stock_02D_acc, ACCESS\n    movf        stock_02D_acc, W, ACCESS",
        "movwf       stock_037_acc, ACCESS\n    movf        stock_037_acc, W, ACCESS",
        "movwf       stock_017_acc, ACCESS\n    movff       stock_017_b0_phys, stock_016_b0_phys",
        "movwf       stock_006_acc, ACCESS\n    movff       stock_006_b0_phys, stock_004_b0_phys",
        "movwf       stock_011_acc, ACCESS\n    movf        stock_011_acc, W, ACCESS",
        "movwf       stock_00C_acc, ACCESS\n    movf        stock_00C_acc, W, ACCESS",
    ]:
        assert redundant not in text


def test_v34_redundant_local_movlb_zero_assertions_stay_removed() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    assert "flow_main_usb_service_2f4e_2f9c:\n    movlb       0x0" not in text
    assert (
        "movff       stock_079_b0_phys, FSR2H\n"
        "    movlb       0x0\n"
        "    bsf         INDF2, 7, ACCESS"
    ) not in text
    assert (
        "bcf         SSPCON1, 6, ACCESS           ; clear SSPOV after aborted rx\n"
        "    movlb       0x0\n"
        "    bsf         dsp_fault_flags_b0, 2, BANKED"
    ) not in text
    assert "cmd03_mute_off_apply:\n    movlb       0x0\n    bcf         active_flags_acc, 4, ACCESS" not in text
    assert (
        "btfsc       active_flags_acc, 7, ACCESS     ; reconnect pending\n"
        "    bra         preset_job_cancel\n\n"
        "    ; Dispatch by state\n"
        "    movlb       0x2"
    ) not in text
    assert (
        "clrf        src4382_loss_debounce_b2, BANKED\n"
        "    movlb       0x0\n"
        "    bra         flow_main_i2c_service_27f0_295c"
    ) not in text
    assert "flow_main_i2c_service_27f0_ad_monitor_timeout:\n    movlb       0x0" not in text


def test_v34_usb_service_endpoint_dispatch_uses_compact_common_tails() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "main_usb_service_2f4e", ["main_core_service_301a"])
    nonzero_ep = _label_body(
        text,
        "flow_main_usb_service_2f4e_2ffe",
        ["flow_main_usb_service_2f4e_300e"],
    )

    assert "flow_main_usb_service_2f4e_2f96:" not in body
    assert "flow_main_usb_service_2f4e_300c:" not in body
    assert body.count("movwf       stock_07B_b0, BANKED") == 1
    _assert_ordered(
        body,
        "movlw       0x04\n"
        "    movwf       stock_07B_b0, BANKED\n"
        "    btfss       USTAT, 1, ACCESS\n"
        "    movlw       0x00\n"
        "flow_main_usb_service_2f4e_2f9c:\n"
        "    movwf       stock_07A_b0, BANKED",
    )
    _assert_ordered(
        nonzero_ep,
        "movf        USTAT, W, ACCESS",
        "xorlw       0x04",
        "bcf         UIR, 3, ACCESS",
        "bnz         flow_main_usb_service_2f4e_300e",
        "call        main_usb_service_4412, 0x0",
    )
    assert nonzero_ep.count("bcf         UIR, 3, ACCESS") == 1


def test_v34_redundant_immediate_fallthrough_branches_stay_removed() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    for redundant in (
        "flow_main_uart_service_1be6_1df0:\n"
        "    movlw       0x05\n"
        "    bra         uart_update_channel_config_cache_w\n"
        "uart_update_channel_config_cache_w:",
        "call        main_usb_service_4412, 0x0\n"
        "    bra         flow_main_usb_service_2f4e_300e\n"
        "flow_main_usb_service_2f4e_300e:",
        "movwf       stock_005_acc, ACCESS\n"
        "    bra         main_core_service_3fd0\n"
        "\n"
        "main_core_service_3fd0:",
        "lfsr        FSR0, stock_410_b4_phys\n"
        "    bra         usb_endpoint_mark_done_fsr0\n"
        "\n"
        "; Shared USB endpoint completion-marker tail",
        "mssp_hard_reset_smp_master:\n"
        "    movlw       0x80\n"
        "    movwf       stock_003_acc, ACCESS\n"
        "    movlw       0x08\n"
        "    bra         mssp_hard_reset\n"
        "\n"
        "mssp_hard_reset:",
    ):
        assert redundant not in text

    _assert_ordered(
        text,
        "uart_channel_config_cache_from_00c:\n"
        "    movf        stock_00C_acc, W, ACCESS\n"
        "uart_update_channel_config_cache_w:",
        "call        main_usb_service_4412, 0x0\n"
        "flow_main_usb_service_2f4e_300e:",
        "movwf       stock_005_acc, ACCESS\n"
        "\n"
        "main_core_service_3fd0:",
        "lfsr        FSR0, stock_410_b4_phys\n"
        "\n"
        "; Shared USB endpoint completion-marker tail",
        "mssp_hard_reset_smp_master:\n"
        "mssp_hard_reset:",
    )


def test_v34_in_range_branch_inversions_stay_collapsed() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    replacements = [
        (
            "bnz         flow_hid_command_dispatch_1504\n"
            "    bra         flow_hid_command_dispatch_13ca\n"
            "flow_hid_command_dispatch_1504:",
            "bz          flow_hid_command_dispatch_13ca\n"
            "flow_hid_command_dispatch_1504:",
        ),
        (
            "bnz         flow_fw_update_relay_1662\n"
            "    bra         flow_fw_update_relay_179c\n"
            "flow_fw_update_relay_1662:",
            "bz          flow_fw_update_relay_179c\n"
            "flow_fw_update_relay_1662:",
        ),
        (
            "bnz         flow_main_uart_service_1be6_1d6c\n"
            "    bra         flow_main_uart_service_1be6_1e6c\n"
            "flow_main_uart_service_1be6_1d6c:",
            "bz          flow_main_uart_service_1be6_1e6c\n"
            "flow_main_uart_service_1be6_1d6c:",
        ),
        (
            "bz          flow_main_uart_service_1be6_1d8a_report\n"
            "    bra         flow_main_uart_service_1be6_1e6c\n"
            "flow_main_uart_service_1be6_1d8a_report:",
            "bnz         flow_main_uart_service_1be6_1e6c\n"
            "flow_main_uart_service_1be6_1d8a_report:",
        ),
        (
            "bnz         flow_main_uart_service_1be6_1e3c\n"
            "    bra         cmd04_status_response\n"
            "flow_main_uart_service_1be6_1e3c:",
            "bz          cmd04_status_response\n"
            "flow_main_uart_service_1be6_1e3c:",
        ),
        (
            "bnz         flow_main_uart_service_1be6_1e42\n"
            "    bra         cmd06_input_select_handler\n"
            "flow_main_uart_service_1be6_1e42:",
            "bz          cmd06_input_select_handler\n"
            "flow_main_uart_service_1be6_1e42:",
        ),
        (
            "bnz         flow_main_uart_service_1be6_1e48\n"
            "    bra         volume_cmd_handler\n"
            "flow_main_uart_service_1be6_1e48:",
            "bz          volume_cmd_handler\n"
            "flow_main_uart_service_1be6_1e48:",
        ),
        (
            "bnz         flow_main_core_service_2328_2482\n"
            "    bra         flow_main_core_service_2328_234a\n"
            "flow_main_core_service_2328_2482:",
            "bz          flow_main_core_service_2328_234a\n"
            "flow_main_core_service_2328_2482:",
        ),
        (
            "bnz         flow_main_core_service_2328_2488\n"
            "    bra         flow_main_core_service_2328_2380\n"
            "flow_main_core_service_2328_2488:",
            "bz          flow_main_core_service_2328_2380\n"
            "flow_main_core_service_2328_2488:",
        ),
        (
            "bnc         flow_main_core_service_3398_33e8\n"
            "    bra         flow_main_core_service_3398_3430\n"
            "flow_main_core_service_3398_33e8:",
            "bc          flow_main_core_service_3398_3430\n"
            "flow_main_core_service_3398_33e8:",
        ),
    ]
    for old, new in replacements:
        assert old not in text
        assert new in text

    fw_update = _label_body(text, "flow_fw_update_relay_1634", ["flow_fw_update_relay_1662"])
    assert (
        "bc          flow_fw_update_relay_1640\n"
        "    bra         flow_fw_update_relay_18d0\n"
        "flow_fw_update_relay_1640:"
    ) not in fw_update
    assert (
        "bnc         flow_fw_update_relay_164c\n"
        "    bra         flow_fw_update_relay_18d0\n"
        "flow_fw_update_relay_164c:"
    ) not in fw_update
    _assert_ordered(
        fw_update,
        "bnc         fw_update_relay_to_18d0",
        "flow_fw_update_relay_1640:",
        "bc          fw_update_relay_to_18d0",
        "flow_fw_update_relay_164c:",
        "bra         flow_fw_update_relay_182e",
        "fw_update_relay_to_18d0:",
        "bra         flow_fw_update_relay_18d0",
        "flow_fw_update_relay_165a:",
    )


def test_v34_volume_dsp_write_keeps_single_post_i2c_bank0_restore() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "volume_dsp_write", ["vol_write_nacked"])

    assert body.count("movlb       0x0") == 2
    _assert_ordered(
        body,
        "movlb       0x0",
        "bcf         dsp_fault_flags_b0, 2, BANKED",
        "rcall       i2c_tas3108_coeff_write",
        "movlb       0x0                          ; helper may leave BSR != 0",
        "btfsc       dsp_fault_flags_b0, 2, BANKED",
        "bra         vol_write_nacked",
        "bcf         event_flags_b0, 3, BANKED",
        "bcf         event_flags_b0, 5, BANKED",
    )
    assert "bra         vol_write_nacked\n    ; Success: DSP responded, clear all fault state\n    movlb" not in body


def test_v34_hid_upload_family_uses_compact_range_dispatch() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(
        text,
        "flow_hid_command_dispatch_1574",
        ["flow_hid_command_dispatch_1598"],
    )

    _assert_ordered(
        body,
        "movf        i2c_coeff_2_acc, W, ACCESS",
        "addlw       0xF9",
        "sublw       0x04",
        "bnc         flow_hid_command_dispatch_157c_not_upload",
        "bra         flow_hid_command_dispatch_13a2",
        "flow_hid_command_dispatch_157c_not_upload:",
        "movf        i2c_coeff_2_acc, W, ACCESS",
        "xorlw       0x0C",
        "bnz         flow_hid_command_dispatch_1598",
        "bra         flow_hid_command_dispatch_1398",
    )
    assert "flow_hid_command_dispatch_157a:" not in text
    assert "flow_hid_command_dispatch_1580:" not in text
    assert "flow_hid_command_dispatch_1586:" not in text
    assert "flow_hid_command_dispatch_158c:" not in text
    assert "flow_hid_command_dispatch_1592:" not in text


def test_v34_uart_terminal_recovery_branches_directly_to_hard_reset() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "uart_tx_timeout", ["main_timer_service_48a6"])

    assert "v31_hard_reset_jump2:" not in text
    assert "bc          hard_reset" in body
    assert "bra         hard_reset" not in body


def test_v34_local_branch_trampolines_stay_collapsed() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    assert "flow_hid_command_dispatch_15a8b:" not in text
    assert "flow_main_core_service_3188_31f4:" not in text
    assert "flow_main_core_service_3188_31fa:" not in text
    assert "bnz         flow_hid_command_dispatch_154c" in text
    assert text.count("bz          flow_main_core_service_3188_324a") >= 2


def test_v34_src_nonpcm_read_uses_random_read_zero_flag_directly() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(
        text,
        "flow_main_i2c_service_27f0_2924",
        ["flow_main_i2c_service_27f0_nonpcm_mute"],
    )

    assert "movwf       stock_0BF_b0, BANKED\n    movf        stock_0BF_b0, W, BANKED" not in body
    assert "movf        stock_0B6_b0, W, BANKED\n    xorlw       0x03" not in body
    _assert_ordered(
        body,
        "flow_main_i2c_service_27f0_2924:",
        "xorlw       0x01",
        "bnz         flow_main_i2c_service_27f0_292e",
        "movlw       0x04",
        "movwf       stock_093_b0, BANKED",
    )
    _assert_ordered(
        body,
        "rcall       i2c_secondary_dev_random_read_window",
        "bc          flow_main_i2c_service_27f0_ad_monitor",
        "movlb       0x0",
        "movwf       stock_0BF_b0, BANKED",
        "bnz         flow_main_i2c_service_27f0_nonpcm_mute",
    )


def test_v34_i2c_timeout_final_actions_are_tail_branches() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    assert "preset_job_apply_i2c_recover:" not in text
    expected = {
        "main_i2c_service_381c_timeout": (
            ["main_i2c_service_381c_pen_timeout"],
            "goto        i2c_timeout_recover_advertise",
        ),
        "main_i2c_service_381c_pen_timeout": (
            ["preset_table_apply_entry_core"],
            "goto        i2c_pen_timeout_recover_advertise",
        ),
        "flow_i2c_byte_tx_timeout": (
            ["chain_copy_mid_window"],
            "goto        i2c_timeout_recover_advertise",
        ),
        "i2c_reg1f_timeout": (
            ["i2c_reg1f_pen_timeout"],
            "bra         i2c_timeout_recover_advertise",
        ),
        "i2c_reg1f_pen_timeout": (
            ["i2c_send_stock006_stop"],
            "bra         i2c_pen_timeout_recover_advertise",
        ),
        "coeff_write_timeout": (
            ["coeff_write_pen_timeout"],
            "bra         i2c_timeout_recover_advertise",
        ),
        "coeff_write_pen_timeout": (
            ["main_core_service_4516"],
            "bra         i2c_pen_timeout_recover_advertise",
        ),
        "i2c_secondary_timeout": (
            ["i2c_secondary_pen_timeout"],
            "bra         i2c_timeout_recover_advertise",
        ),
        "i2c_secondary_pen_timeout": (
            ["main_flash_service_46de"],
            "bra         i2c_pen_timeout_recover_advertise",
        ),
        "preset_job_apply_i2c_timeout": (
            ["preset_select_handler"],
            "bra         i2c_timeout_recover_advertise",
        ),
        "main_i2c_service_464c_timeout": (
            ["main_core_service_4672"],
            "bra         i2c_secondary_dev_random_timeout",
        ),
    }
    for label, (next_labels, branch) in expected.items():
        body = _label_body(text, label, next_labels)
        assert branch in body
        assert "call        i2c_timeout_recover_advertise" not in body
        assert "call        i2c_pen_timeout_recover_advertise" not in body
        assert "rcall       i2c_timeout_recover_advertise" not in body
        assert "rcall       i2c_pen_timeout_recover_advertise" not in body
        assert "return      0" not in body

    reg1f = _label_body(text, "i2c_tas3108_reg1f_write", ["i2c_byte_tx_zero"])
    secondary = _label_body(text, "i2c_secondary_dev_write", ["i2c_secondary_timeout"])
    stop_helper = _label_body(text, "i2c_send_stock006_stop", ["i2c_byte_tx_zero"])
    _assert_ordered(
        stop_helper,
        "movf        stock_006_acc, W, ACCESS",
        "rcall       i2c_byte_tx",
        "bsf         SSPCON2, 2, ACCESS",
        "bra         wait_pen_bounded",
    )
    assert "rcall       wait_pen_bounded" not in stop_helper
    _assert_ordered(reg1f, "rcall       i2c_send_stock006_stop", "bc          i2c_reg1f_pen_timeout")
    _assert_ordered(secondary, "rcall       i2c_send_stock006_stop", "bc          i2c_secondary_pen_timeout")


def test_v34_newly_reachable_far_helpers_use_rcall_only_where_in_range() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    random_read_pen = _label_body(
        text,
        "i2c_secondary_dev_random_pen_timeout",
        ["main_core_service_427a"],
    )
    volume_retry = _label_body(text, "vol_write_nacked", ["vol_diag_d_skip"])

    _assert_ordered(
        random_read_pen,
        "rcall       i2c_pen_timeout_recover_advertise",
        "clrf        WREG, ACCESS",
        "return      0",
    )
    assert "call        i2c_pen_timeout_recover_advertise, 0x0" not in random_read_pen
    _assert_ordered(
        volume_retry,
        "lfsr        FSR0, diag_r_b2_phys",
        "rcall       diag_inc_sat_fsr0",
        "rcall       i2c_bus_clear",
        "rcall       dsp_ping",
        "lfsr        FSR0, diag_d_b2_phys",
        "rcall       diag_inc_sat_fsr0",
    )


def test_v34_usb_filename_compare_and_page1_setup_use_compact_forms() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    filename_tail = _label_body(
        text,
        "flow_hid_command_dispatch_111a",
        ["flow_hid_command_dispatch_1126"],
    )
    filename_subcommand_tail = _label_body(
        text,
        "flow_hid_command_dispatch_11c0",
        ["flow_hid_command_dispatch_11ce"],
    )
    settings_diff = _label_body(
        text,
        "flow_hid_command_dispatch_12ca",
        ["flow_hid_command_dispatch_12e0"],
    )
    preset_erase = _label_body(
        text,
        "flow_hid_command_dispatch_11a4",
        ["flow_hid_command_dispatch_11b2"],
    )

    _assert_ordered(
        filename_tail,
        "movf        stock_097_b0, W, BANKED",
        "xorlw       0x09",
        "bz          flow_hid_command_dispatch_111a_dirty",
        "xorlw       0x03",
        "bnz         flow_hid_command_dispatch_1126",
    )
    assert "movf        stock_097_b0, W, BANKED\n    xorlw       0x0A" not in filename_tail
    _assert_ordered(
        filename_subcommand_tail,
        "movf        stock_0B5_b0, W, BANKED",
        "andlw       0xFD",
        "xorlw       0x05",
        "bz          flow_hid_command_dispatch_112a",
        "bra         flow_hid_command_dispatch_15aa",
    )
    assert "movf        stock_0B5_b0, W, BANKED\n    xorlw       0x07" not in filename_subcommand_tail
    assert "xorlw       0x02" not in filename_subcommand_tail
    _assert_ordered(
        settings_diff,
        "clrf        stock_04C_acc, ACCESS",
        "btfsc       active_flags_acc, 4, ACCESS",
        "incf        stock_04C_acc, F, ACCESS",
        "btfsc       active_flags_acc, 5, ACCESS",
        "btg         stock_04C_acc, 0, ACCESS",
        "movf        stock_04C_acc, F, ACCESS",
    )
    _assert_ordered(
        preset_erase,
        "addwf       i2c_coeff_3_acc, W, ACCESS",
        "rcall       setup_fsr2_page_1",
        "setf        INDF2, ACCESS",
    )
    assert "call        setup_fsr2_page_1, 0x0" not in preset_erase


def test_v34_unconditional_call_return_tails_are_direct_branches() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    expected = {
        "wake_input_failed": (
            ["wake_barrier_retry"],
            "goto        send_dsp_fault_status",
            "call        send_dsp_fault_status",
        ),
        "flow_cmd_dispatch_gated_1990": (
            ["flow_cmd_dispatch_gated_volume_unmuted"],
            "bra         main_timer_service_48a6_low_window",
            "call        main_timer_service_48a6",
        ),
        "cmd_dispatch_route_sync_if_dirty": (
            ["usb_mailbox_service_05"],
            "bra         main_timer_service_48a6_low_window",
            "call        main_timer_service_48a6",
        ),
        "flow_cmd_dispatch_gated_1bd6": (
            ["cmd_dispatch_route_sync_if_dirty"],
            "bra         main_timer_service_48a6_low_window",
            "call        main_timer_service_48a6",
        ),
        "usb_mailbox_service_05": (
            ["setup_fsr2_page_1_or_2"],
            "goto        main_usb_service_45a2",
            "call        main_usb_service_45a2",
        ),
        "main_core_service_4574_final": (
            ["main_usb_service_45a2"],
            "bra         preset_job_apply_i2c_from_job_cursor",
            "rcall       preset_job_apply_i2c_from_job_cursor",
        ),
        "main_usb_service_45a2": (
            ["main_core_service_45ce"],
            "bra         usb_stage_5a40_and_service_3fd0",
            "rcall       usb_stage_5a40_and_service_3fd0",
        ),
        "main_flash_service_46de": (
            ["main_core_service_48fe"],
            "bra         eeprom_write_blocking",
            "rcall       eeprom_write_blocking",
        ),
        "main_core_service_48fe": (
            ["main_timer_service_48a6"],
            "bra         main_usb_service_4624",
            "rcall       main_usb_service_4624",
        ),
        "i2c_send_stock006_stop": (
            ["i2c_byte_tx_zero"],
            "bra         wait_pen_bounded",
            "rcall       wait_pen_bounded",
        ),
    }
    for label, (next_labels, branch, old_call) in expected.items():
        body = _label_body(text, label, next_labels)
        assert branch in body
        assert old_call not in body
        assert not re.search(rf"{re.escape(branch)}\\s*\\n\\s*return\\s+0", body)


def test_v34_branch_only_alias_labels_share_target_addresses() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    aliases = {
        "flow_cmd_dispatch_gated_reapply_wait_name": "flow_cmd_dispatch_gated_1a9c",
        "flow_main_i2c_service_27f0_ad_monitor_timeout": "flow_main_i2c_service_27f0_295c",
        "repeat_w_main_core_service_30cc": "repeat_w_main_core_service_30cc_check",
        "main_usb_service_4812": "flow_main_usb_service_4812_481e",
        "main_uart_service_4860": "flow_main_uart_service_4860_4866",
        "preset_job_commit_rearm": "preset_job_pending_timer",
        "preset_job_commit_idle": "preset_job_cancel_done",
    }
    for alias, target in aliases.items():
        body = _label_body(text, alias, [target])
        assert "bra         " not in body
        assert "goto        " not in body


def test_v34_dead_w_zero_tests_use_tstfsz_skip_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    expected = [
        "tstfsz      input_select_b0, BANKED\n    bsf         event_flags_b0, 3, BANKED",
        "tstfsz      stock_0FD_b0, BANKED\n    goto        main_usb_service_45a2",
        "tstfsz      rx_frame_position_b0, BANKED\n    incf        rx_frame_position_b0, F, BANKED",
        "tstfsz      stock_009_acc, ACCESS\n    return      0",
        "tstfsz      stock_008_acc, ACCESS\n    bsf         stock_006_acc, 7, ACCESS",
        "tstfsz      stock_0FE_b0, BANKED\n    call        flash_write_with_gie_off, 0x0",
        "tstfsz      stock_00B_acc, ACCESS\n    bsf         INTCON, 7, ACCESS",
    ]
    for snippet in expected:
        assert snippet in text

    removed = [
        "movf        input_select_b0, W, BANKED\n    btfss       STATUS, 2, ACCESS",
        "movf        stock_0FD_b0, W, BANKED\n    btfss       STATUS, 2, ACCESS",
        "movf        rx_frame_position_b0, W, BANKED\n    btfss       STATUS, 2, ACCESS",
        "movf        stock_009_acc, W, ACCESS\n    btfss       STATUS, 2, ACCESS",
        "movf        stock_008_acc, W, ACCESS\n    btfss       STATUS, 2, ACCESS",
        "movf        stock_0FE_b0, W, BANKED\n    btfss       STATUS, 2, ACCESS",
        "movf        stock_00B_acc, W, ACCESS\n    btfss       STATUS, 2, ACCESS",
    ]
    for snippet in removed:
        assert snippet not in text


def test_v34_math_result_helpers_share_fsr2_rewind_tail() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    first = _label_body(text, "math_result_fsr2_rewind2", ["main_core_service_3f1e"])
    second = _label_body(text, "main_core_service_3f1e", ["intel_hex_checksum_update"])

    _assert_ordered(
        first,
        "decf        FSR2L, F, ACCESS",
        "decf        FSR2L, F, ACCESS",
        "return      0",
    )
    assert first.count("decf        FSR2L, F, ACCESS") == 2
    _assert_ordered(
        second,
        "lfsr        FSR0, stock_033_b0_phys",
        "rcall       copy4_postinc0_to_postinc2_rewind2",
        "bra         math_result_fsr2_rewind2",
    )
    assert "movff       stock_036_b0_phys, POSTDEC2\n    decf        FSR2L, F, ACCESS" not in second


def test_v34_volume_dsp_path_uses_chain_copy_for_four_byte_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "flow_cmd_dispatch_gated_19e6", ["flow_cmd_dispatch_gated_volume_done"])

    for old_copy in (
        "movff       stock_00D_b0_phys, stock_012_b0_phys",
        "movff       stock_00E_b0_phys, stock_013_b0_phys",
        "movff       stock_00F_b0_phys, stock_014_b0_phys",
        "movff       stock_010_b0_phys, stock_015_b0_phys",
        "movff       stock_02F_b0_phys, i2c_coeff_0_b0_phys",
        "movff       stock_030_b0_phys, i2c_coeff_1_b0_phys",
        "movff       stock_031_b0_phys, i2c_coeff_2_b0_phys",
        "movff       stock_032_b0_phys, i2c_coeff_3_b0_phys",
    ):
        assert old_copy not in body

    _assert_ordered(
        body,
        "call        main_core_service_3e0a, 0x0",
        "rcall       chain_copy_low_window",
        "db          0x00, 0x00, stock_00D_acc_op, stock_012_acc_op, 0x04, 0xFF",
        "movlw       0x47",
        "call        main_core_service_2abc, 0x0",
        "call        chain_copy, 0x0",
        "db          0x00, 0x00, stock_012_acc_op, stock_0ED_b0_op, 0x04, stock_0ED_b0_op, stock_02F_acc_op, 0x04, 0xFF, 0xFF",
        "call        main_core_service_297e, 0x0",
        "rcall       chain_copy_low_window",
        "db          0x00, 0x00, stock_02F_acc_op, i2c_coeff_0_acc_op, 0x04, 0xFF",
        "call        volume_dsp_write, 0x0",
    )


def test_v34_core_38a2_and_volume_mirror_use_chain_copy_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    core = _label_body(text, "main_i2c_service_39a6", ["signed_hi_bias80_compare_prelude"])
    mirror = _label_body(
        text,
        "copy_computed_volume_to_logical_volume",
        ["wait_seed"],
    )

    for old_copy in (
        "movff       stock_02F_b0_phys, stock_03D_b0_phys",
        "movff       stock_030_b0_phys, stock_03E_b0_phys",
        "movff       stock_031_b0_phys, stock_03F_b0_phys",
        "movff       stock_032_b0_phys, stock_040_b0_phys",
        "movff       stock_041_b0_phys, stock_02F_b0_phys",
        "movff       stock_042_b0_phys, stock_030_b0_phys",
        "movff       stock_043_b0_phys, stock_031_b0_phys",
        "movff       stock_044_b0_phys, stock_032_b0_phys",
        "movff       stock_02F_b0_phys, stock_041_b0_phys",
        "movff       stock_030_b0_phys, stock_042_b0_phys",
        "movff       stock_031_b0_phys, stock_043_b0_phys",
        "movff       stock_032_b0_phys, stock_044_b0_phys",
    ):
        assert old_copy not in core
    for old_copy in (
        "movff       computed_volume_b0_phys, logical_volume_b0_phys",
        "movff       computed_volume_1_b0_phys, logical_volume_1_b0_phys",
        "movff       computed_volume_2_b0_phys, logical_volume_2_b0_phys",
        "movff       computed_volume_3_b0_phys, logical_volume_3_b0_phys",
    ):
        assert old_copy not in mirror

    _assert_ordered(
        core,
        "db          0x00, 0x00, stock_041_acc_op, stock_039_acc_op, 0x04, stock_041_acc_op, stock_02F_acc_op, 0x04, 0xFF, 0xFF",
        "rcall       main_core_service_3398",
        "db          0x00, 0x00, stock_02F_acc_op, stock_03D_acc_op, 0x04, 0xFF",
        "call        main_core_service_24c2, 0x0",
        "db          0x00, 0x00, stock_020_acc_op, stock_039_acc_op, 0x04, 0xFF",
        "db          0x00, 0x00, stock_039_acc_op, stock_045_acc_op, 0x04, stock_045_acc_op, stock_02F_acc_op, 0x04, 0xFF, 0xFF",
        "movlw       0x41",
        "rcall       main_core_service_3f1e",
        "db          0x00, 0x00, stock_041_acc_op, stock_02F_acc_op, 0x04, 0xFF",
        "rcall       main_core_service_3398",
        "db          0x00, 0x00, stock_02F_acc_op, stock_041_acc_op, 0x04, 0xFF",
        "bra         i2c_byte_tx",
    )
    _assert_ordered(
        mirror,
        "call        chain_copy, 0x0",
        "db          0x00, 0x00, computed_volume_b0_op, logical_volume_b0_op, 0x04, 0xFF",
        "return      0",
    )


def test_v34_chain_copy_eeprom_mode_keeps_pseudo_page_out_of_fsr0h() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "chain_copy", ["s3_math_stage_025"])

    assert "movf        FSR0H, W, ACCESS" not in body
    assert "movff       chain_copy_srch, FSR0H" not in body
    _assert_ordered(
        body,
        "movf        chain_copy_srch_b3, W, BANKED",
        "xorlw       0xEE",
        "bnz         chain_copy_ram_read",
        "movf        chain_copy_srcl_b3, W, BANKED",
        "call        eeprom_read_byte_W, 0x0",
        "chain_copy_ram_read:",
        "movff       chain_copy_srcl_b3_phys, FSR0L",
        "movff       chain_copy_srch_b3_phys, FSR0H",
    )


def test_v34_chain_copy_descriptors_are_well_formed_and_eeprom_only_where_expected() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    descriptors = _chain_copy_descriptors(text)
    assert descriptors, "missing chain_copy descriptors"

    eeprom_descriptors = []
    for descriptor in descriptors:
        assert len(descriptor) >= 6
        src_page, dst_page = descriptor[:2]
        assert src_page in {"0x00", "0x01", "0xEE"}
        assert dst_page in {"0x00", "0x01"}
        if src_page == "0xEE":
            eeprom_descriptors.append(descriptor)

        cursor = 2
        while cursor < len(descriptor) and descriptor[cursor] != "0xFF":
            assert cursor + 2 < len(descriptor), descriptor
            src_low, _dst_low, count = descriptor[cursor : cursor + 3]
            assert src_low != "0xFF", descriptor
            assert count != "0x00", descriptor
            if src_page == "0xEE":
                assert int(src_low, 16) <= 0x7F
            cursor += 3

        assert cursor < len(descriptor), f"missing descriptor sentinel: {descriptor}"
        assert all(token == "0xFF" for token in descriptor[cursor:])

    assert len(eeprom_descriptors) == 2
    assert any("computed_volume_3_b0_op" in descriptor for descriptor in eeprom_descriptors)
    assert any("stock_09B_b0_op" in descriptor for descriptor in eeprom_descriptors)


def test_v34_chain_copy_windows_use_local_tos_trampolines() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    low_wrapper = _label_body(text, "chain_copy_low_window", ["cmd_dispatch_gated"])
    mid_wrapper = _label_body(text, "chain_copy_mid_window", ["main_core_service_3ec4"])

    _assert_ordered(low_wrapper, "chain_copy_low_window:", "goto        chain_copy")
    _assert_ordered(mid_wrapper, "chain_copy_mid_window:", "goto        chain_copy")

    low_bodies = {
        "flow_hid_command_dispatch_124e": (_label_body(text, "flow_hid_command_dispatch_124e", ["flow_hid_command_dispatch_129c"]), 1),
        "flow_hid_command_dispatch_1344": (_label_body(text, "flow_hid_command_dispatch_1344", ["flow_hid_command_dispatch_1374"]), 1),
        "flow_cmd_dispatch_gated_19e6": (_label_body(text, "flow_cmd_dispatch_gated_19e6", ["flow_cmd_dispatch_gated_volume_done"]), 2),
        "main_core_service_1e88": (_label_body(text, "main_core_service_1e88", ["main_core_service_2328"]), 4),
    }
    for label, (body, expected) in low_bodies.items():
        assert body.count("rcall       chain_copy_low_window") == expected, label
        if label == "flow_cmd_dispatch_gated_19e6":
            assert body.count("call        chain_copy, 0x0") == 1, label
        else:
            assert "call        chain_copy, 0x0" not in body, label

    mid_bodies = {
        "s3_coeff_stage_049": (_label_body(text, "s3_coeff_stage_049", ["main_i2c_service_39a6"]), 1),
        "main_i2c_service_39a6": (_label_body(text, "main_i2c_service_39a6", ["signed_hi_bias80_compare_prelude"]), 11),
        "main_core_service_3e0a": (_label_body(text, "main_core_service_3e0a", ["sspcon1_masked_w"]), 1),
        "main_core_service_3ec4": (_label_body(text, "main_core_service_3ec4", ["main_core_service_3f1e"]), 2),
        "main_core_service_3f1e": (_label_body(text, "main_core_service_3f1e", ["intel_hex_checksum_update"]), 2),
        "main_flash_service_46de": (_label_body(text, "main_flash_service_46de", ["main_core_service_48fe"]), 1),
    }
    for label, (body, expected) in mid_bodies.items():
        assert body.count("rcall       chain_copy_mid_window") == expected, label
        assert "call        chain_copy, 0x0" not in body, label


def test_v34_i2c_service_39a6_uses_chain_copy_for_four_byte_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "main_i2c_service_39a6", ["signed_hi_bias80_compare_prelude"])

    assert "movff       stock_049_b0_phys, stock_012_b0_phys" not in body
    assert "movff       stock_012_b0_phys, stock_041_b0_phys" not in body
    assert "movff       stock_025_b0_phys, stock_051_b0_phys" not in body
    assert "call        chain_copy, 0x0" not in body
    assert body.count("rcall       chain_copy_mid_window") == 11
    _assert_ordered(
        body,
        "movwf       stock_019_acc, ACCESS",
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, stock_049_acc_op, stock_012_acc_op, 0x04, 0xFF",
        "call        main_core_service_2abc, 0x0",
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, stock_012_acc_op, stock_041_acc_op, 0x04, 0xFF",
        "db          0x00, 0x00, stock_041_acc_op, stock_039_acc_op, 0x04, stock_041_acc_op, stock_02F_acc_op, 0x04, 0xFF, 0xFF",
        "rcall       main_core_service_3398",
    )
    _assert_ordered(
        body,
        "call        main_core_service_301a, 0x0",
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, stock_025_acc_op, stock_051_acc_op, 0x04, 0xFF",
        "movf        stock_054_acc, W, ACCESS",
    )


def test_v34_filename_reply_state_machine_keeps_compact_branch_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    query = _label_body(text, "cmd26_filename_query_handler", ["filename_read_source_at_w"])
    reader = _label_body(text, "filename_read_source_at_w", ["filename_reply_job_service"])
    arm = _label_body(text, "cmd26_filename_arm", ["cmd26_filename_compare_prefix16"])
    service = _label_body(text, "filename_reply_job_service", ["diag_send_burst_xx"])

    assert query.count("btfsc       filename_rev_b2, 0, BANKED") == 2
    assert "movf        filename_rev_b2, W, BANKED\n    andlw       0x01\n    bnz         cmd26_filename_query_done" not in query
    _assert_ordered(
        query,
        "movwf       fn_job_src_kind_b2, BANKED",
        "btfsc       active_flags_acc, 2, ACCESS",
        "xorlw       0x01",
        "bz          cmd26_filename_source_ram",
        "movlw       preset_filename_eeprom_a",
        "btfsc       fn_job_src_kind_b2, 0, BANKED",
        "movlw       preset_filename_eeprom_b",
        "movwf       fn_job_src_kind_b2, BANKED",
        "bra         cmd26_filename_len_init",
    )
    _assert_ordered(
        query,
        "cmd26_filename_compare_other_eep:",
        "movlw       preset_filename_eeprom_b",
        "btfsc       active_flags_acc, 2, ACCESS",
        "movlw       preset_filename_eeprom_a",
        "movwf       fn_job_src_kind_b2, BANKED",
        "cmd26_filename_compare_read_other:",
    )
    assert "filename_stage_other_eep_source:" not in query
    assert "rcall       filename_stage_other_eep_source" not in query
    assert "xorlw       0x01\n    bz          filename_read_source_eep_a" not in query
    assert "cmd26_filename_source_set:" not in query
    assert "cmd26_filename_source_eep_a:" not in query
    _assert_ordered(
        query,
        "cmd26_filename_len_loop:",
        "movf        fn_job_len_b2, W, BANKED",
        "xorlw       preset_filename_len",
        "bz          cmd26_filename_arm",
        "rcall       filename_read_source_at_w",
        "addlw       0xE0",
        "bnc         cmd26_filename_arm",
        "sublw       0x5E",
        "bnc         cmd26_filename_arm",
        "incf        fn_job_len_b2, F, BANKED",
    )
    _assert_ordered(
        reader,
        "movwf       fn_job_tmp_b2, BANKED",
        "movf        fn_job_src_kind_b2, W, BANKED",
        "bz          filename_read_source_ram",
    )
    assert "movlw       0x20\n    cpfslt      fn_job_tmp_b2, BANKED" not in query
    _assert_ordered(
        arm,
        "movlw       0x2F",
        "movwf       fn_job_start_cmd_b2, BANKED",
        "movlw       0x10",
        "cpfsgt      fn_job_len_b2, BANKED",
        "bra         cmd26_filename_arm_rev_check",
    )
    assert "movlw       0x11" not in arm
    _assert_ordered(
        service,
        "decf        fname_tx_gap_hi_b2, F, BANKED",
        "filename_reply_dec_gap_lo:",
        "decf        fname_tx_gap_lo_b2, F, BANKED",
        "bra         filename_reply_job_ret",
    )
    send_start = _label_body(service, "filename_reply_send_start", ["filename_reply_send_len"])
    send_len = _label_body(service, "filename_reply_send_len", ["filename_reply_send_char_or_end"])
    _assert_ordered(
        send_start,
        "movf        fn_job_start_cmd_b2, W, BANKED",
        "rcall       filename_emit_id_frame_cmd_w",
        "incf        fn_job_state_b2, F, BANKED",
        "return      0",
    )
    _assert_ordered(
        send_len,
        "movlw       0x2D",
        "rcall       filename_emit_frame",
        "incf        fn_job_state_b2, F, BANKED",
        "return      0",
    )
    _assert_ordered(
        service,
        "filename_reply_send_char_or_end:",
        "cpfseq      fn_job_len_b2, BANKED",
        "bra         filename_reply_send_char",
        "filename_reply_send_end:",
    )
    assert "bra         filename_reply_send_end\nfilename_reply_send_char:" not in service


def test_v34_math_counted_call_loops_use_shared_repeat_helpers() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    for old_label in (
        "flow_main_core_service_24c2_24d6:",
        "flow_main_core_service_24c2_24d8:",
        "flow_main_core_service_24c2_24f4:",
        "flow_main_core_service_24c2_24f6:",
        "flow_main_core_service_2abc_2ad0:",
        "flow_main_core_service_2abc_2ad2:",
        "flow_main_core_service_2abc_2af4:",
        "flow_main_core_service_2abc_2af6:",
        "flow_main_core_service_2ca8_2cbc:",
        "flow_main_core_service_2ca8_2cbe:",
        "flow_main_core_service_2ca8_2ce0:",
        "flow_main_core_service_2ca8_2ce2:",
        "flow_main_core_service_301a_302e:",
        "flow_main_core_service_301a_3030:",
        "flow_main_core_service_301a_305a:",
        "flow_main_core_service_301a_305c:",
    ):
        assert old_label not in text

    fixed_helpers = {
        "repeat_18_main_core_service_2650": (
            "stock_02B_acc",
            "stock_02A_acc",
            "stock_029_acc",
            "stock_028_acc",
        ),
        "repeat_18_main_core_service_2bac": (
            "stock_01D_acc",
            "stock_01C_acc",
            "stock_01B_acc",
            "stock_01A_acc",
        ),
        "repeat_18_main_core_service_2d80": (
            "stock_018_acc",
            "stock_017_acc",
            "stock_016_acc",
            "stock_015_acc",
        ),
    }
    for helper, regs in fixed_helpers.items():
        body = _label_body(text, helper, [f"{helper}_loop"])
        full_body = _label_body(text, helper, ["main_core_service_24c2", "main_core_service_2abc", "main_core_service_2ca8"])
        _assert_ordered(
            full_body,
            "movlw       0x18",
            f"bra         {helper}_check",
            f"{helper}_loop:",
            "bcf         STATUS, 0, ACCESS",
            f"rrcf        {regs[0]}, F, ACCESS",
            f"rrcf        {regs[1]}, F, ACCESS",
            f"rrcf        {regs[2]}, F, ACCESS",
            f"rrcf        {regs[3]}, F, ACCESS",
            f"{helper}_check:",
            "decfsz      WREG, F, ACCESS",
            f"bra         {helper}_loop",
            "return      0",
        )
        assert "movlw       0x18" in body
        assert text.count(f"rcall       {helper}") == 2

    variable_helper = _label_body(text, "repeat_w_main_core_service_30cc", ["main_core_service_301a"])
    variable_loop = _label_body(text, "repeat_w_main_core_service_30cc_loop", ["main_core_service_301a"])
    assert "movlw       0x18" not in variable_helper
    assert "movlw       0x20" not in variable_helper
    assert "bra         repeat_w_main_core_service_30cc_check" not in variable_helper
    _assert_ordered(
        variable_loop,
        "repeat_w_main_core_service_30cc_loop:",
        "bcf         STATUS, 0, ACCESS",
        "rrcf        stock_02C_acc, F, ACCESS",
        "rrcf        stock_02B_acc, F, ACCESS",
        "rrcf        stock_02A_acc, F, ACCESS",
        "rrcf        stock_029_acc, F, ACCESS",
        "repeat_w_main_core_service_30cc:",
        "repeat_w_main_core_service_30cc_check:",
        "decfsz      WREG, F, ACCESS",
        "bra         repeat_w_main_core_service_30cc_loop",
        "return      0",
    )

    caller = _label_body(text, "main_core_service_301a", ["main_core_service_30cc"])
    _assert_ordered(
        caller,
        "movlw       0x18",
        "rcall       repeat_w_main_core_service_30cc",
        "movf        stock_029_acc, W, ACCESS",
        "movlw       0x20",
        "rcall       repeat_w_main_core_service_30cc",
    )
    assert caller.count("rcall       repeat_w_main_core_service_30cc") == 2


def test_v34_math_operand_stage_runs_use_near_chain_copy_descriptors() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    bodies = {
        "main_core_service_24c2": _label_body(text, "main_core_service_24c2", ["main_core_service_263e"]),
        "main_core_service_2abc": _label_body(text, "main_core_service_2abc", ["main_core_service_2b8e"]),
        "main_core_service_2ca8": _label_body(text, "main_core_service_2ca8", ["flash_write_stock"]),
    }

    for old_copy in (
        "movff       stock_020_b0_phys, stock_028_b0_phys",
        "movff       stock_021_b0_phys, stock_029_b0_phys",
        "movff       stock_022_b0_phys, stock_02A_b0_phys",
        "movff       stock_023_b0_phys, stock_02B_b0_phys",
        "movff       stock_024_b0_phys, stock_020_b0_phys",
        "movff       stock_025_b0_phys, stock_021_b0_phys",
        "movff       stock_026_b0_phys, stock_022_b0_phys",
        "movff       stock_027_b0_phys, stock_023_b0_phys",
        "movff       stock_003_b0_phys, stock_020_b0_phys",
        "movff       stock_004_b0_phys, stock_021_b0_phys",
        "movff       saved_w_b0_phys, stock_022_b0_phys",
        "movff       stock_006_b0_phys, stock_023_b0_phys",
    ):
        assert old_copy not in bodies["main_core_service_24c2"]
    for old_copy in (
        "movff       stock_012_b0_phys, stock_01A_b0_phys",
        "movff       stock_013_b0_phys, stock_01B_b0_phys",
        "movff       stock_014_b0_phys, stock_01C_b0_phys",
        "movff       stock_015_b0_phys, stock_01D_b0_phys",
        "movff       stock_016_b0_phys, stock_01A_b0_phys",
        "movff       stock_017_b0_phys, stock_01B_b0_phys",
        "movff       stock_018_b0_phys, stock_01C_b0_phys",
        "movff       stock_019_b0_phys, stock_01D_b0_phys",
    ):
        assert old_copy not in bodies["main_core_service_2abc"]
    for old_copy in (
        "movff       stock_00D_b0_phys, stock_015_b0_phys",
        "movff       stock_00E_b0_phys, stock_016_b0_phys",
        "movff       stock_00F_b0_phys, stock_017_b0_phys",
        "movff       stock_010_b0_phys, stock_018_b0_phys",
        "movff       stock_011_b0_phys, stock_015_b0_phys",
        "movff       stock_012_b0_phys, stock_016_b0_phys",
        "movff       stock_013_b0_phys, stock_017_b0_phys",
        "movff       stock_014_b0_phys, stock_018_b0_phys",
    ):
        assert old_copy not in bodies["main_core_service_2ca8"]

    _assert_ordered(
        bodies["main_core_service_24c2"],
        "db          0x00, 0x00, stock_020_acc_op, stock_028_acc_op, 0x04, 0xFF",
        "rcall       repeat_18_main_core_service_2650",
        "db          0x00, 0x00, stock_024_acc_op, stock_020_acc_op, 0x04, 0xFF",
        "bra         flow_main_core_service_24c2_263c",
        "db          0x00, 0x00, stock_003_acc_op, stock_020_acc_op, 0x04, 0xFF",
        "flow_main_core_service_24c2_263c:",
    )
    helper_24c2 = _label_body(
        bodies["main_core_service_24c2"],
        "main_core_service_24c2_dec_mask_02c",
        ["flow_main_core_service_24c2_2588"],
    )
    assert bodies["main_core_service_24c2"].count("rcall       main_core_service_24c2_dec_mask_02c") == 2
    _assert_ordered(
        helper_24c2,
        "decf        stock_02C_acc, F, ACCESS",
        "movff       stock_02C_b0_phys, stock_028_b0_phys",
        "movlw       0x07",
        "andwf       stock_028_acc, F, ACCESS",
        "return      0",
    )
    _assert_ordered(
        bodies["main_core_service_2abc"],
        "db          0x00, 0x00, stock_012_acc_op, stock_01A_acc_op, 0x04, 0xFF",
        "rcall       repeat_18_main_core_service_2bac",
        "db          0x00, 0x00, stock_016_acc_op, stock_01A_acc_op, 0x04, 0xFF",
        "rcall       repeat_18_main_core_service_2bac",
    )
    _assert_ordered(
        bodies["main_core_service_2ca8"],
        "db          0x00, 0x00, stock_00D_acc_op, stock_015_acc_op, 0x04, 0xFF",
        "rcall       repeat_18_main_core_service_2d80",
        "db          0x00, 0x00, stock_011_acc_op, stock_015_acc_op, 0x04, 0xFF",
        "rcall       repeat_18_main_core_service_2d80",
    )


def test_v34_core_297e_uses_near_chain_copy_for_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "main_core_service_297e", ["flow_main_core_service_2abc_2b52"])

    for old_copy in (
        "movff       stock_02F_b0_phys, stock_00D_b0_phys",
        "movff       stock_030_b0_phys, stock_00E_b0_phys",
        "movff       stock_031_b0_phys, stock_00F_b0_phys",
        "movff       stock_032_b0_phys, stock_010_b0_phys",
        "movff       stock_00D_b0_phys, stock_020_b0_phys",
        "movff       stock_00E_b0_phys, stock_021_b0_phys",
        "movff       stock_00F_b0_phys, stock_022_b0_phys",
        "movff       stock_010_b0_phys, stock_023_b0_phys",
        "movff       stock_020_b0_phys, stock_02F_b0_phys",
        "movff       stock_021_b0_phys, stock_030_b0_phys",
        "movff       stock_022_b0_phys, stock_031_b0_phys",
        "movff       stock_023_b0_phys, stock_032_b0_phys",
    ):
        assert old_copy not in body

    _assert_ordered(
        body,
        "rcall       chain_copy",
        "db          0x00, 0x00, stock_02F_acc_op, stock_00D_acc_op, 0x04, 0xFF",
        "rcall       main_core_service_2ca8",
        "rcall       chain_copy",
        "db          0x00, 0x00, stock_00D_acc_op, stock_020_acc_op, 0x04, 0xFF",
        "rcall       main_core_service_24c2",
        "rcall       chain_copy",
        "db          0x00, 0x00, stock_020_acc_op, stock_02F_acc_op, 0x04, 0xFF",
        "movlw       0x0A",
    )


def test_v34_core_2abc_final_save_uses_chain_copy_descriptor() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "main_core_service_2abc", ["main_core_service_2b8e"])
    volume_caller = _label_body(text, "flow_cmd_dispatch_gated_19e6", ["flow_cmd_dispatch_gated_volume_done"])
    i2c_caller = _label_body(text, "main_i2c_service_39a6", ["signed_hi_bias80_compare_prelude"])
    math_caller = _label_body(text, "main_core_service_3ec4", ["main_core_service_3f1e"])

    for old_copy in (
        "movff       stock_003_b0_phys, stock_012_b0_phys",
        "movff       stock_004_b0_phys, stock_013_b0_phys",
        "movff       saved_w_b0_phys, stock_014_b0_phys",
        "movff       stock_006_b0_phys, stock_015_b0_phys",
    ):
        assert old_copy not in body

    _assert_ordered(
        body,
        "rcall       main_core_service_30d8",
        "rcall       chain_copy",
        "db          0x00, 0x00, stock_003_acc_op, stock_012_acc_op, 0x04, 0xFF",
        "flow_main_core_service_2abc_2b8c:",
        "return      0",
    )
    _assert_ordered(
        volume_caller,
        "call        main_core_service_2abc, 0x0",
        "rcall       chain_copy_low_window",
    )
    _assert_ordered(
        i2c_caller,
        "call        main_core_service_2abc, 0x0",
        "rcall       chain_copy_mid_window",
    )
    _assert_ordered(
        math_caller,
        "call        main_core_service_2abc, 0x0",
        "rcall       chain_copy_mid_window",
    )


def test_v34_math_result_helpers_use_chain_copy_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    core_3ec4 = _label_body(text, "main_core_service_3ec4", ["main_core_service_3f1e"])
    core_3f1e = _label_body(text, "main_core_service_3f1e", ["intel_hex_checksum_update"])
    caller_39a6 = _label_body(text, "main_i2c_service_39a6", ["signed_hi_bias80_compare_prelude"])

    for body, old_copies in (
        (
            core_3ec4,
            (
                "movff       stock_025_b0_phys, stock_016_b0_phys",
                "movff       stock_026_b0_phys, stock_017_b0_phys",
                "movff       stock_027_b0_phys, stock_018_b0_phys",
                "movff       stock_028_b0_phys, stock_019_b0_phys",
                "movff       stock_012_b0_phys, stock_029_b0_phys",
                "movff       stock_013_b0_phys, stock_02A_b0_phys",
                "movff       stock_014_b0_phys, stock_02B_b0_phys",
                "movff       stock_015_b0_phys, stock_02C_b0_phys",
            ),
        ),
        (
            core_3f1e,
            (
                "movff       stock_02F_b0_phys, stock_024_b0_phys",
                "movff       stock_030_b0_phys, stock_025_b0_phys",
                "movff       stock_031_b0_phys, stock_026_b0_phys",
                "movff       stock_032_b0_phys, stock_027_b0_phys",
                "movff       stock_020_b0_phys, stock_033_b0_phys",
                "movff       stock_021_b0_phys, stock_034_b0_phys",
                "movff       stock_022_b0_phys, stock_035_b0_phys",
                "movff       stock_023_b0_phys, stock_036_b0_phys",
            ),
        ),
    ):
        for old_copy in old_copies:
            assert old_copy not in body

    _assert_ordered(
        core_3ec4,
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, stock_025_acc_op, stock_016_acc_op, 0x04, 0xFF",
        "call        main_core_service_2abc, 0x0",
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, stock_012_acc_op, stock_029_acc_op, 0x04, 0xFF",
        "movf        stock_02D_acc, W, ACCESS",
    )
    _assert_ordered(
        core_3f1e,
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, stock_02F_acc_op, stock_024_acc_op, 0x04, 0xFF",
        "call        main_core_service_24c2, 0x0",
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, stock_020_acc_op, stock_033_acc_op, 0x04, 0xFF",
        "movf        stock_037_acc, W, ACCESS",
    )
    assert "main_core_service_432e:" not in text
    assert "call        main_core_service_432e, 0x0" not in text
    _assert_ordered(
        caller_39a6,
        "call        main_core_service_24c2, 0x0",
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, stock_020_acc_op, stock_039_acc_op, 0x04, 0xFF",
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, stock_039_acc_op, stock_045_acc_op, 0x04, stock_045_acc_op, stock_02F_acc_op, 0x04, 0xFF, 0xFF",
    )


def test_v34_settings_load_reuses_clamp_literal_across_adjacent_source_clamps() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "main_core_service_1e88", ["flow_main_core_service_1e88_2088"])
    clamp_body = _label_body(text, "flow_main_core_service_1e88_1f6a", ["flow_main_core_service_1e88_1fbc"])
    trim_clamps = _label_body(text, "flow_main_core_service_1e88_2030", ["flow_main_core_service_1e88_2088"])
    volume_guard = body[
        body.index("movf        computed_volume_3_b0, W, BANKED") :
        body.index("flow_main_core_service_1e88_1f54:")
    ]

    _assert_ordered(
        volume_guard,
        "xorlw       0x80",
        "addlw       0x80",
        "bnz         flow_main_core_service_1e88_1f54",
        "subwf       computed_volume_2_b0, W, BANKED",
        "bnz         flow_main_core_service_1e88_1f54",
        "subwf       computed_volume_1_b0, W, BANKED",
    )
    assert "movlw       0x00" not in volume_guard

    _assert_ordered(
        body,
        "flow_main_core_service_1e88_1f6a:",
        "movlw       0x03",
        "cpfsgt      stock_060_b0, BANKED",
        "flow_main_core_service_1e88_1f72:",
        "lfsr        FSR2, stock_061_b0_phys",
        "cpfsgt      INDF2, ACCESS",
        "flow_main_core_service_1e88_1f7e:",
        "lfsr        FSR2, stock_062_b0_phys",
        "cpfsgt      INDF2, ACCESS",
        "flow_main_core_service_1e88_1f8a:",
        "lfsr        FSR2, stock_063_b0_phys",
        "cpfsgt      INDF2, ACCESS",
        "flow_main_core_service_1e88_1f98:",
        "lfsr        FSR2, stock_064_b0_phys",
        "movlw       0x03",
        "cpfsgt      INDF2, ACCESS",
    )
    assert clamp_body.count("movlw       0x03") == 4
    _assert_ordered(
        trim_clamps,
        "movlw       0x12",
        "cpfsgt      stock_09B_b0, BANKED",
        "flow_main_core_service_1e88_2070:",
        "cpfsgt      stock_09C_b0, BANKED",
        "flow_main_core_service_1e88_2078:",
        "cpfsgt      stock_09D_b0, BANKED",
        "flow_main_core_service_1e88_2080:",
        "cpfsgt      stock_09E_b0, BANKED",
    )
    assert trim_clamps.count("movlw       0x12") == 1


def test_v34_trim_mirrors_and_core_3398_use_chain_copy_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    trims_load = _label_body(text, "flow_main_core_service_1e88_2088", ["flow_main_core_service_1e88_209c"])
    response = _label_body(text, "flow_main_core_service_2328_240c", ["flow_main_core_service_2328_2460"])
    core_3398 = _label_body(text, "main_core_service_3398", ["main_core_service_3432"])

    for body, old_copies in (
        (
            trims_load,
            (
                "movff       stock_09B_b0_phys, stock_0AC_b0_phys",
                "movff       stock_09C_b0_phys, stock_0AD_b0_phys",
                "movff       stock_09D_b0_phys, stock_0AE_b0_phys",
                "movff       stock_09E_b0_phys, stock_0AF_b0_phys",
            ),
        ),
        (
            response,
            (
                "movff       stock_09B_b0_phys, stock_173_b1_phys",
                "movff       stock_09C_b0_phys, stock_174_b1_phys",
                "movff       stock_09D_b0_phys, stock_175_b1_phys",
                "movff       stock_09E_b0_phys, stock_176_b1_phys",
            ),
        ),
        (
            core_3398,
            (
                "movff       stock_02F_b0_phys, stock_003_b0_phys",
                "movff       stock_030_b0_phys, stock_004_b0_phys",
                "movff       stock_031_b0_phys, saved_w_b0_phys",
                "movff       stock_032_b0_phys, stock_006_b0_phys",
                "movff       stock_025_b0_phys, stock_00D_b0_phys",
                "movff       stock_026_b0_phys, stock_00E_b0_phys",
                "movff       stock_027_b0_phys, stock_00F_b0_phys",
                "movff       stock_028_b0_phys, stock_010_b0_phys",
            ),
        ),
    ):
        for old_copy in old_copies:
            assert old_copy not in body

    _assert_ordered(
        trims_load,
        "rcall       chain_copy_low_window",
        "db          0x00, 0x00, stock_09B_b0_op, stock_0AC_b0_op, 0x04, 0xFF",
        "movlw       0x50",
    )
    _assert_ordered(
        response,
        "movlw       0x03",
        "movwf       stock_15B_b1, BANKED",
        "movwf       stock_15C_b1, BANKED",
        "movlw       0x04",
        "movwf       stock_15D_b1, BANKED",
        "rcall       chain_copy",
        "db          0x00, 0x01, stock_09B_b0_op, stock_173_b1_op, 0x04, 0xFF",
        "bra         flow_main_core_service_2328_24a6",
    )
    assert response.count("movlw       0x03") == 1
    _assert_ordered(
        core_3398,
        "main_core_service_3398:",
        "rcall       chain_copy",
        "db          0x00, 0x00, stock_02F_acc_op, stock_003_acc_op, 0x04, 0xFF",
        "movlw       0x37",
        "flow_main_core_service_3398_33e8:",
        "rcall       s3_math_stage_025",
        "rcall       main_core_service_301a",
        "rcall       chain_copy",
        "db          0x00, 0x00, stock_025_acc_op, stock_00D_acc_op, 0x04, 0xFF",
        "call        main_core_service_3e0a, 0x0",
    )


def test_v34_core_3e0a_and_eeprom_writeback_use_chain_copy_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    core_3e0a = _label_body(text, "main_core_service_3e0a", ["i2c_tas3108_reg1f_write"])
    eeprom_writeback = _label_body(text, "main_flash_service_46de", ["main_core_service_48fe"])

    for old_copy in (
        "movff       stock_00D_b0_phys, stock_003_b0_phys",
        "movff       stock_00E_b0_phys, stock_004_b0_phys",
        "movff       stock_00F_b0_phys, saved_w_b0_phys",
        "movff       stock_010_b0_phys, stock_006_b0_phys",
    ):
        assert old_copy not in core_3e0a
    writeback_tail = eeprom_writeback[eeprom_writeback.index("bz          flow_main_flash_service_46de_46fe") :]
    for old_copy in (
        "movff       stock_007_b0_phys, stock_003_b0_phys",
        "movff       stock_008_b0_phys, stock_004_b0_phys",
        "movff       stock_009_b0_phys, saved_w_b0_phys",
    ):
        assert old_copy not in writeback_tail

    _assert_ordered(
        core_3e0a,
        "flow_main_core_service_3e0a_3e3a:",
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, stock_00D_acc_op, stock_003_acc_op, 0x04, 0xFF",
        "movlw       0x96",
        "goto        main_core_service_30d8_with_save",
    )
    _assert_ordered(
        eeprom_writeback,
        "xorwf       stock_009_acc, W, ACCESS",
        "bz          flow_main_flash_service_46de_46fe",
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, stock_007_acc_op, stock_003_acc_op, 0x03, 0xFF",
        "bra         eeprom_write_blocking",
    )


def test_v34_coeff_stage_runs_use_chain_copy_descriptors() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    apply_body = _label_body(text, "flow_main_i2c_service_2100_22de", ["flow_main_i2c_service_2100_22fc"])
    helper = _label_body(text, "s3_coeff_stage_049", ["main_i2c_service_39a6"])

    for old_copy in (
        "movff       stock_00D_b0_phys, i2c_coeff_0_b0_phys",
        "movff       stock_00E_b0_phys, i2c_coeff_1_b0_phys",
        "movff       stock_00F_b0_phys, i2c_coeff_2_b0_phys",
        "movff       stock_010_b0_phys, i2c_coeff_3_b0_phys",
    ):
        assert old_copy not in apply_body
    for old_copy in (
        "movff       i2c_coeff_0_b0_phys, stock_049_b0_phys",
        "movff       i2c_coeff_1_b0_phys, stock_04A_b0_phys",
        "movff       i2c_coeff_2_b0_phys, stock_04B_b0_phys",
        "movff       i2c_coeff_3_b0_phys, stock_04C_b0_phys",
    ):
        assert old_copy not in helper

    _assert_ordered(
        apply_body,
        "call        main_core_service_45ce, 0x0",
        "rcall       chain_copy",
        "db          0x00, 0x00, stock_00D_acc_op, i2c_coeff_0_acc_op, 0x04, 0xFF",
    )
    assert "flow_main_i2c_service_2100_22fc:" not in apply_body
    _assert_ordered(
        helper,
        "rcall       chain_copy_mid_window",
        "db          0x00, 0x00, i2c_coeff_0_acc_op, stock_049_acc_op, 0x04, 0xFF",
        "return      0",
    )


def test_v34_preset_apply_is_transaction_checked_and_physical_source_owned() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    init_cursor = _label_body(
        text,
        "preset_job_init_cursor_from_active",
        ["preset_job_apply_i2c_from_job_cursor"],
    )
    _assert_ordered(
        init_cursor,
        "movlb       0x2",
        "clrf        preset_job_index_b2, BANKED",
        "clrf        preset_job_tbl_lo_b2, BANKED",
        "movlw       0x56",
        "btfsc       active_flags_acc, 2, ACCESS",
        "movlw       0x4C",
        "movwf       preset_job_tbl_hi_b2, BANKED",
        "return      0",
    )

    cursor_entry = _label_body(
        text,
        "preset_job_apply_i2c_from_job_cursor",
        ["preset_job_apply_i2c_entry"],
    )
    _assert_ordered(
        cursor_entry,
        "movff       preset_job_tbl_lo_b2_phys, stock_013_b0_phys",
        "movff       preset_job_tbl_hi_b2_phys, stock_014_b0_phys",
        "bra         preset_job_apply_i2c_entry",
    )
    advance = _label_body(
        text,
        "preset_job_advance_cursor_0x18",
        ["preset_job_apply_i2c_entry"],
    )
    _assert_ordered(
        advance,
        "movlb       0x2",
        "movlw       0x18",
        "addwf       preset_job_tbl_lo_b2, F, BANKED",
        "movlw       0x00",
        "addwfc      preset_job_tbl_hi_b2, F, BANKED",
        "incf        preset_job_index_b2, F, BANKED",
        "return      0",
    )

    i2c_entry = _label_body(
        text,
        "preset_job_apply_i2c_entry",
        ["preset_job_apply_i2c_done", "preset_job_apply_i2c_timeout"],
    )
    _assert_ordered(
        i2c_entry,
        "call        preset_table_apply_entry_core_async, 0x0",
        "bcf         stock_012_acc, 0, ACCESS",
        "bc          preset_job_apply_i2c_timeout",
    )

    holding = _label_body(text, "preset_job_holding", ["preset_job_holding_wait"])
    _assert_ordered(
        holding,
        "btg         active_flags_acc, 2, ACCESS",
        "rcall       preset_job_init_cursor_from_active",
    )

    apply = _label_body(text, "preset_job_apply", ["preset_job_apply_retry"])
    _assert_ordered(
        apply,
        "rcall       preset_target_compare_active_bsr2",
        "bnz         preset_job_commit_rearm",
        "rcall       preset_job_apply_i2c_from_job_cursor",
        "bc          preset_job_apply_retry",
        "bra         preset_job_advance_cursor_0x18",
    )

    final = _label_body(text, "preset_job_apply_final", ["preset_job_commit"])
    assert "movlw       0x5F" not in final
    assert "call        preset_b_remap_start_addr" not in final
    _assert_ordered(
        final,
        "rcall       preset_job_apply_i2c_from_job_cursor",
        "bc          preset_job_apply_retry",
    )

    async_core = _label_body(
        text,
        "preset_table_apply_entry_core_async",
        ["preset_table_stage_header_read"],
    )
    _assert_ordered(
        async_core,
        "bsf         stock_012_acc, 0, ACCESS",
        "rcall       flash_read_stock_fsr2_0017",
        "movff       stock_018_b0_phys, stock_02F_b0_phys",
        "movff       stock_019_b0_phys, stock_031_b0_phys",
        "rcall       preset_table_validate_async_header",
        "bc          preset_table_apply_entry_timeout",
    )
    assert "flash_read_fsr2_0017" not in async_core

    legacy_core = _label_body(
        text,
        "preset_table_apply_entry_core",
        ["preset_table_apply_entry_timeout"],
    )
    _assert_ordered(
        legacy_core,
        "rcall       flash_read_fsr2_0017",
        "rcall       flash_read_stock_fsr2_0017",
        "rcall       flash_read_fsr2_0017",
        "call        wait_sen_bounded, 0x0",
    )

    validator = _label_body(
        text,
        "preset_table_validate_async_header",
        ["preset_table_apply_entry_loop"],
    )
    for token in (
        "xorlw       0x01",
        "movlw       0x60",
        "movlw       0xD4",
        "addlw       0xC8",
        "addwf       stock_016_acc, W, ACCESS",
        "xorlw       0x14",
        "bcf         stock_00D_acc, 0, ACCESS",
        "bsf         STATUS, 0, ACCESS",
    ):
        assert token in validator

    cancel = _label_body(text, "preset_job_cancel", ["preset_job_cancel_done"])
    assert "bcf         active_flags_acc, 4" not in cancel
    assert "bcf         active_flags_acc, 5" not in cancel


def test_v34_preset_target_compare_uses_shared_bsr2_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "preset_target_compare_active_bsr2", ["preset_persist_filename"])

    _assert_ordered(
        helper,
        "movf        preset_job_target_b2, W, BANKED",
        "btfsc       active_flags_acc, 2, ACCESS",
        "xorlw       0x01",
        "return      0",
    )
    expected_calls = {
        "adc_boot_gate_barrier_done": (
            ["adc_boot_gate_no_preset_rearm"],
            "call        preset_target_compare_active_bsr2, 0x0",
        ),
        "preset_select_handler": (
            ["preset_select_handler_done"],
            "rcall       preset_target_compare_active_bsr2",
        ),
        "preset_job_holding": (
            ["preset_job_holding_wait"],
            "rcall       preset_target_compare_active_bsr2",
        ),
        "preset_job_apply": (
            ["preset_job_apply_retry"],
            "rcall       preset_target_compare_active_bsr2",
        ),
        "preset_job_commit": (
            ["preset_job_commit_idle"],
            "rcall       preset_target_compare_active_bsr2",
        ),
    }
    for label, (next_labels, call_shape) in expected_calls.items():
        body = _label_body(text, label, next_labels)
        assert call_shape in body


def test_v34_field6_lifecycle_reassert_uses_validated_writer_and_route_drain() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    main_core = _label_body(text, "main_core_service_4574", ["main_usb_service_45a2"])
    assert "main_i2c_service_381c" not in main_core
    _assert_ordered(
        main_core,
        "rcall       preset_job_init_cursor_from_active",
        "rcall       preset_job_apply_i2c_from_job_cursor",
        "bc          main_core_service_4574_fail",
        "rcall       preset_job_advance_cursor_0x18",
    )
    assert "bra         preset_job_apply_i2c_from_job_cursor" in main_core
    assert main_core.count("rcall       preset_job_apply_i2c_from_job_cursor") == 1
    assert main_core.count("rcall       preset_job_advance_cursor_0x18") == 1

    reconnect = _label_body(
        text,
        "flow_cmd_dispatch_gated_1a76",
        ["flow_cmd_dispatch_gated_1a9c"],
    )
    _assert_ordered(
        reconnect,
        "rcall       clrf_i2c_coeff_0123_and_write_mid_window",
        "rcall       cmd_dispatch_route_sync_if_dirty",
        "bcf         event_flags_b0, 6, BANKED",
        "call        main_core_service_4574",
        "bc          flow_cmd_dispatch_gated_reapply_failed",
    )
    assert "cmd_dispatch_input_route_if_dirty" not in reconnect
    _assert_ordered(
        reconnect,
        "btfss       INTCON, 7, ACCESS",
        "bra         flow_cmd_dispatch_gated_reapply_skip_name",
        "bcf         INTCON, 7, ACCESS",
        "call        preset_load_filename",
        "bsf         INTCON, 7, ACCESS",
    )

    volume_entry = _label_body(
        text,
        "cmd_dispatch_gated",
        ["flow_cmd_dispatch_gated_volume_unmuted"],
    )
    pre_late = volume_entry[: volume_entry.index("cmd_dispatch_late_bit1_entry:")]
    _assert_ordered(
        pre_late,
        "btfsc       active_flags_acc, 7, ACCESS",
        "bra         flow_cmd_dispatch_gated_19a8",
    )
    assert "cmd_dispatch_input_route_if_dirty" not in pre_late
    assert volume_entry.index("cmd_dispatch_late_bit1_entry:") < volume_entry.index(
        "rcall       cmd_dispatch_input_route_if_dirty"
    )
    flow_entry = _label_body(
        text,
        "flow_cmd_dispatch_gated_19a8",
        ["flow_cmd_dispatch_gated_volume_unmuted"],
    )
    _assert_ordered(
        flow_entry,
        "btfsc       active_flags_acc, 7, ACCESS",
        "bra         flow_cmd_dispatch_gated_1a76",
        "btfss       event_flags_b0, 3, BANKED",
    )


def test_v34_channel_route_bit_fanout_uses_addlw_selector_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(
        text,
        "flow_cmd_dispatch_gated_1aca",
        ["flow_cmd_dispatch_gated_1b8c"],
    )
    helper_region = _label_body(
        text,
        "usb_mailbox_service_05",
        ["setup_fsr2_page_1_or_2"],
    )

    for stale_label in [
        "flow_cmd_dispatch_gated_1ad8",
        "flow_cmd_dispatch_gated_1ada",
        "flow_cmd_dispatch_gated_1aee",
        "flow_cmd_dispatch_gated_1af0",
        "flow_cmd_dispatch_gated_1b04",
        "flow_cmd_dispatch_gated_1b06",
        "flow_cmd_dispatch_gated_1b1a",
        "flow_cmd_dispatch_gated_1b1c",
        "flow_cmd_dispatch_gated_1b30",
        "flow_cmd_dispatch_gated_1b32",
        "flow_cmd_dispatch_gated_1b46",
    ]:
        assert stale_label not in body
    assert "i2c_381c_with_w_bank0:" not in helper_region
    assert "rcall       i2c_381c_with_w_bank0" not in body
    assert body.count("addlw       0xEC") == 1
    assert body.count("call        main_i2c_service_381c, 0x0") == 1
    _assert_ordered(
        body,
        "movlw       0x5F",
        "movwf       stock_014_acc, ACCESS",
        "movlw       0x1C",
        "movwf       stock_04B_acc, ACCESS",
        "movff       stock_0A4_b0_phys, stock_04C_b0_phys",
        "flow_cmd_dispatch_gated_route_bit_loop:",
        "rrcf        stock_04C_acc, F, ACCESS",
        "movf        stock_04B_acc, W, ACCESS",
        "btfsc       STATUS, 0, ACCESS",
        "addlw       0xEC",
        "movwf       stock_013_acc, ACCESS",
        "call        main_i2c_service_381c, 0x0",
        "movlw       0x28",
        "addwf       stock_04B_acc, F, ACCESS",
        "bnc         flow_cmd_dispatch_gated_route_bit_loop",
    )


def test_v34_field6_wake_route_sync_precedes_final_reassert() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    wake = _label_body(text, "adc_boot_gate_exit", ["preset_b_remap_start_addr"])

    _assert_ordered(
        wake,
        "rcall       clrf_i2c_coeff_0123_and_write_mid_window",
        "bsf         event_flags_b0, 4, BANKED",
        "bsf         active_flags_acc, 7, ACCESS",
        "call        cmd_dispatch_gated",
        "adc_boot_gate_reassert_ok:",
        "rcall       wake_i2c_barrier_attempt",
        "bc          adc_boot_gate_barrier_pending",
        "bsf         event_flags_b0, 1, BANKED",
        "bsf         event_flags_b0, 3, BANKED",
        "call        cmd_dispatch_gated",
    )
    pre_lifecycle = wake[: wake.index("adc_boot_gate_reassert_ok:")]
    assert "call        main_core_service_4574" not in pre_lifecycle
    assert "call        cmd_dispatch_input_route_if_dirty" not in pre_lifecycle
    assert "call        cmd_dispatch_route_sync_if_dirty" not in pre_lifecycle
    assert "event_flags_b0, 1" not in pre_lifecycle

    barrier = wake[
        wake.index("adc_boot_gate_reassert_ok:") : wake.index("bsf         event_flags_b0, 1, BANKED")
    ]
    assert "call        cmd_dispatch_gated" not in barrier
    assert "event_flags_b0, 3" not in barrier
    assert "stock_094_b0, 7" not in barrier
    assert "bsf         stock_094_b0, 6, BANKED" in wake
    _assert_ordered(
        wake,
        "adc_boot_gate_barrier_pending:",
        "call        field10_mark_fault_mute, 0x0",
        "bsf         stock_094_b0, 6, BANKED",
    )
    fault_mute = _label_body(text, "field10_mark_fault_mute", ["wake_barrier_retry"])
    _assert_ordered(
        fault_mute,
        "bsf         active_flags_acc, 4, ACCESS",
        "bsf         active_flags_acc, 5, ACCESS",
        "bsf         event_flags_b0, 1, BANKED",
        "bcf         event_flags_b0, 3, BANKED",
        "bsf         dsp_fault_flags_b0, 6, BANKED",
        "return      0",
    )

    dispatch = _label_body(text, "cmd_dispatch_late_bit1_entry", ["flow_cmd_dispatch_gated_19a8"])
    _assert_ordered(
        dispatch,
        "bcf         stock_094_b0, 7, BANKED",
        "btfsc       event_flags_b0, 1, BANKED",
        "bsf         stock_094_b0, 7, BANKED",
        "bcf         dsp_fault_flags_b0, 2, BANKED",
        "rcall       cmd_dispatch_input_route_if_dirty",
        "btfsc       dsp_fault_flags_b0, 2, BANKED",
        "bra         wake_input_failed",
    )


def test_v34_field6_route_sync_tail_has_single_code_owner() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    input_helper = _label_body(
        text,
        "cmd_dispatch_input_route_if_dirty",
        ["flow_cmd_dispatch_gated_18fe"],
    )
    helper = _label_body(text, "cmd_dispatch_route_sync_if_dirty", ["usb_mailbox_service_05"])
    normal_tail = _label_body(text, "flow_cmd_dispatch_gated_1baa", ["flow_cmd_dispatch_gated_1bc8"])

    assert "return      0" in input_helper
    assert "event_flags_b0, 3" in input_helper
    assert "call        cmd_dispatch_gated" not in input_helper
    assert len(re.findall(r"(?m)^\s+rcall\s+main_i2c_service_2100\b", text)) == 1
    assert "rcall       main_i2c_service_2100" in helper
    _assert_ordered(
        helper,
        "bsf         filename_dirty_flags_b0, 1, BANKED",
        "rcall       usb_mailbox_service_05",
        "bra         main_timer_service_48a6_low_window",
    )
    assert "call        main_usb_service_45a2, 0x0" not in helper
    assert "rcall       cmd_dispatch_route_sync_if_dirty" in normal_tail
    assert "main_i2c_service_2100" not in normal_tail


def test_v34_field6_repros_are_no_longer_marked_xfail() -> None:
    repro_text = Path(__file__).with_name("test_v34_v173_field_repros_20260613.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    assert "FIELD-6-DSP open repro" not in repro_text


@pytest.mark.xfail(
    strict=True,
    reason=(
        "chain_copy rewrites TOS and still has post-GIE call sites; "
        "this is documented as a failed interrupt-safety proof"
    ),
)
def test_v34_chain_copy_call_sites_are_pre_gie_or_helper_masks_tos_rewrite() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    chain_copy = _label_body(text, "chain_copy", ["s3_math_stage_025"])
    tos_rewrite = chain_copy[
        chain_copy.index("movf        TBLPTRL, W, ACCESS") :
        chain_copy.index("return      0")
    ]
    helper_masks_tos = "bcf         INTCON, 7, ACCESS" in tos_rewrite
    if helper_masks_tos:
        return

    runtime_post_gie_bodies = {
        "flow_hid_command_dispatch_124e": ["flow_hid_command_dispatch_129c"],
        "flow_hid_command_dispatch_1344": ["flow_hid_command_dispatch_1374"],
        "main_core_service_1e88": ["main_core_service_2328"],
        "main_core_service_3398": ["main_core_service_3432"],
        "main_i2c_service_39a6": ["main_core_service_3c82"],
    }
    unsafe = [
        label
        for label, next_labels in runtime_post_gie_bodies.items()
        if (
            "call        chain_copy" in _label_body(text, label, next_labels)
            or "rcall       chain_copy_low_window" in _label_body(text, label, next_labels)
            or "rcall       chain_copy_mid_window" in _label_body(text, label, next_labels)
        )
    ]
    assert not unsafe, "chain_copy call sites reachable after GIE without TOS mask: " + ", ".join(unsafe)


def test_v34_cold_init_clears_all_upper_bank_runtime_lifecycle_cells() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "flow_main_flash_service_3ce8_3d4e", ["diag_rcon_rearm"])
    lifecycle_cells = [
        "preset_job_state_b2",
        "preset_job_target_b2",
        "preset_job_index_b2",
        "preset_job_delay_b2",
        "preset_job_flags_b2",
        "preset_job_tbl_lo_b2",
        "preset_job_tbl_hi_b2",
        "diag_i_b2",
        "diag_d_b2",
        "diag_s_b2",
        "diag_b_b2",
        "diag_r_b2",
        "diag_a_b2",
        "diag_p_b2",
        "diag_ra1_prev_b2",
        "diag_reset_por_b2",
        "diag_reset_bor_b2",
        "diag_reset_wdt_b2",
        "diag_reset_sw_b2",
        "main_rx_frame_gap_timeout_b2",
        "i2c_recover_flags_b2",
        "src4382_loss_debounce_b2",
        "fn_job_state_b2",
        "fn_job_id_b2",
        "fn_job_idx_b2",
        "fn_job_src_kind_b2",
        "filename_rev_b2",
        "fn_job_rev_b2",
        "fn_job_start_cmd_b2",
        "fn_job_len_b2",
        "fname_tx_gap_lo_b2",
        "fname_tx_gap_hi_b2",
        "chain_tx_emitted_b2",
        "fn_job_tmp_b2",
    ]
    equates = _main_ram_equates()
    assert equates["preset_job_state_b2_phys"] == 0x2DE
    assert equates["fn_job_tmp_b2_phys"] == 0x2FF
    out_of_range = [
        symbol
        for symbol in lifecycle_cells
        if not 0x2DE <= equates[f"{symbol}_phys"] <= 0x2FF
    ]
    assert not out_of_range, "runtime cells outside cold-init clear range: " + ", ".join(out_of_range)
    _assert_ordered(
        body,
        "lfsr        FSR0, preset_job_state_b2_phys",
        "movlw       0x22",
        "rcall       clear_postinc0_count_w",
        "btfss       RCON, 1, ACCESS",
    )
    assert body.count("rcall       clear_postinc0_count_w") == 6
    assert "clrf        preset_job_state_b2, BANKED" not in body


def test_v34_parser_forwarded_bytes_mark_chain_tx_emitted_before_uart_tx() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    route_body = _label_body(text, "parser_route_phase_handler", ["flow_main_uart_service_1be6_1c42"])
    data_body = _label_body(text, "flow_main_uart_service_1be6_1c42", ["flow_main_uart_service_1be6_1c52"])
    for body in (route_body, data_body):
        assert "rcall       forward_stock00a_marked" in body
    helper = _label_body(text, "forward_stock00a_marked", ["main_core_service_1e88"])
    _assert_ordered(
        helper,
        "call        mark_chain_tx_emitted_bsr0, 0x0",
        "movf        stock_00A_acc, W, ACCESS",
        "bra         uart_tx_byte_blocking_mid_window",
    )


def test_v34_uart_route_b0_b1_compare_uses_cumulative_xor() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "flow_main_uart_service_1be6_1bf4", ["flow_main_uart_service_1be6_1c1c"])

    _assert_ordered(
        body,
        "movf        stock_00A_acc, W, ACCESS",
        "xorlw       0xB0",
        "bnz         flow_main_uart_service_1be6_1c0e",
        "flow_main_uart_service_1be6_1c0e:",
        "xorlw       0x01",
        "bnz         flow_main_uart_service_1be6_1c1c",
    )
    assert "movf        stock_00A_acc, W, ACCESS\n    xorlw       0xB1" not in body


def test_v34_reply_helpers_participate_in_chain_tx_emitted_contract() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper_body = _label_body(text, "mark_chain_tx_emitted_bsr0", ["send_dsp_fault_status"])
    assert "bsf         chain_tx_emitted_b2, 0, BANKED" in helper_body
    assert "movlb       0x00" in helper_body
    assert "return      0" in helper_body
    bf_header = _label_body(text, "bf_frame_header_tx", ["i2c_pen_timeout_recover_advertise"])
    _assert_ordered(
        bf_header,
        "rcall       mark_chain_tx_emitted_bsr0",
        "bf_byte_tx:",
        "movlw       0xBF",
        "bra         uart_tx_byte_blocking",
    )

    required = {
        "send_status_burst": ["send_status_burst_preamble"],
        "report_cmd29_status": ["cmd21_diag_query_handler"],
        "send_dsp_fault_status": ["cmd21_diag_query_handler"],
        "cmd23_health_query_handler": ["cmd25_identity_query_handler"],
        "cmd25_identity_query_handler": ["cmd 0x26"],
        "filename_emit_frame": ["diag_send_burst_xx"],
        "diag_send_burst_xx": ["Volume DSP Write"],
    }
    missing = []
    for label, next_labels in required.items():
        body = _label_body(text, label, next_labels)
        if (
            "bsf         chain_tx_emitted_b2, 0, BANKED" not in body
            and "rcall       mark_chain_tx_emitted_bsr0" not in body
            and "call        mark_chain_tx_emitted_bsr0, 0x0" not in body
            and "rcall       bf_frame_header_tx" not in body
        ):
            missing.append(label)
    assert not missing


def test_v173_preset_row0_readiness_gates_row1_filename_rendering() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    draw = _label_body(text, "v171_prs_screen_draw_body", ["v171_prs_screen_cache_check"])
    service = _label_body(text, "v172_preset_filename_service", ["v172_fname_query_service"])

    # FIELD-3 factoring (2026-06-11): the row-0 paint (including the
    # readiness bcf) moved into v173_preset_row0_paint so the per-pass
    # filename service can self-heal a blanked row 0; the draw body
    # delegates to it before blanking row 1.
    paint = _label_body(text, "v173_preset_row0_paint", ["v171_preset_screen"])
    assert "FNAME_ROW0_NOT_READY" in paint
    assert "FNAME_ROW0_NOT_READY" in service
    assert "call    v173_preset_row0_paint" in draw
    _assert_ordered(
        paint,
        "call    v172_preset_status_patch_service",
        "bcf     v172_fname_row0_status_snap_b2, FNAME_ROW0_NOT_READY, BANKED",
    )
    _assert_ordered(
        draw,
        "call    v173_preset_row0_paint",
        "v172_preset_blank_row1_entry",
    )
    _assert_ordered(
        service,
        "btfss   v172_fname_row0_status_snap_b2, FNAME_ROW0_NOT_READY, BANKED",
        "v172_preset_filename_service_row0_ready",
        "call    v172_preset_status_patch_service",
        "bc      v172_preset_filename_service_done",
        "call    v172_fname_row1_render_service",
    )


def test_v173_does_not_introduce_preset_row0_full_redraw_recovery_hack() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    assert "v172_preset_row0_full_redraw" not in text
    assert "row0_full_redraw" not in text
