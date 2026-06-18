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
    body = _label_body(text, "i2c_secondary_apply_wake_init_table", ["i2c_secondary_wake_init_table"])
    table = _db_ints_for_label(text, "i2c_secondary_wake_init_table", ["i2c_secondary_write_table_rows"])

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
        "movlw       LOW(i2c_secondary_wake_init_table)",
        "movlw       HIGH(i2c_secondary_wake_init_table)",
        "movlw       0x10",
        "bra         i2c_secondary_write_table_rows",
    )


def test_v34_standby_shutdown_secondary_write_table_preserves_rail_drop_order() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "hw_standby_shutdown", ["hw_standby_shutdown__select_master_baud"])
    table = _db_ints_for_label(text, "hw_standby_shutdown_i2c_table", ["usb_ep1_out_copy_packet_if_ready"])

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
        "rcall       i2c_secondary_write_table_rows",
        "btfss       PORTC, 2, ACCESS",
    )


def test_v34_i2c_table_walker_uses_fault_safe_access_counter_and_no_tos_rewrite() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "i2c_secondary_write_table_rows", ["truncate_float32_to_integral_float_in_place"])

    assert "TOSL" not in body
    assert "TOSH" not in body
    assert "FSR0" not in body
    assert "INDF0" not in body
    _assert_ordered(
        body,
        "clrf        TBLPTRU, ACCESS",
        "movwf       flash_end_high_or_loop_mask_scratch_byte, ACCESS",
        "tblrd*+",
        "movff       TABLAT, status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys",
        "tblrd*+",
        "movf        TABLAT, W, ACCESS",
        "rcall       i2c_secondary_dev_write_call_range_trampoline",
        "decfsz      flash_end_high_or_loop_mask_scratch_byte, F, ACCESS",
        "return      0",
    )


def test_v34_boot_marker_check_accepts_0x77_or_0x88_with_single_eeprom_read() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "boot_init_peripherals_and_enter_adc_gate", ["boot_init_peripherals_and_enter_adc_gate__maybe_rewrite_config_bits"])

    assert body.count("call        eeprom_read_byte, 0x0") == 1
    assert "xorlw       0x88" not in body
    _assert_ordered(
        body,
        "clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS",
        "setf        addr_low_counter_or_payload_scratch_byte, ACCESS",
        "call        eeprom_read_byte, 0x0",
        "xorlw       0x77",
        "bz          boot_init_peripherals_and_enter_adc_gate__maybe_rewrite_config_bits",
        "xorlw       0xFF",
        "bz          boot_init_peripherals_and_enter_adc_gate__maybe_rewrite_config_bits",
    )


def test_v34_main_i2c_service_2100_uses_bank0_clear_wrapper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "ram_block_clear_four_bytes_bank0_from_w", ["i2c_apply_channel_route_sync_burst"])
    body = _label_body(text, "i2c_apply_channel_route_sync_burst", ["channel_route_pair_destination_table"])

    _assert_ordered(
        helper,
        "clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS",
        "movlb       0x0",
        "bra         ram_block_clear_four_bytes_from_w",
    )
    assert body.count("rcall       ram_block_clear_four_bytes_bank0_from_w") == 4
    assert body.count("rcall       ram_clear_prepare_page1_address_high") == 3
    _assert_ordered(
        body,
        "movlw       0xD7",
        "rcall       ram_block_clear_four_bytes_bank0_from_w",
        "movlw       0xDB",
        "rcall       ram_block_clear_four_bytes_bank0_from_w",
        "movlw       0xDF",
        "rcall       ram_block_clear_four_bytes_bank0_from_w",
        "rcall       ram_clear_prepare_page1_address_high",
        "movlw       0xD9",
        "rcall       ram_block_clear_four_bytes_from_w",
        "movlw       0xE3",
        "rcall       ram_block_clear_four_bytes_bank0_from_w",
        "rcall       ram_clear_prepare_page1_address_high",
        "movlw       0xDD",
        "rcall       ram_block_clear_four_bytes_from_w",
        "rcall       ram_clear_prepare_page1_address_high",
        "movlw       0xE1",
        "rcall       ram_block_clear_four_bytes_from_w",
    )


def test_v34_cmd_dispatch_reg1f_route3_reuses_existing_pair_setup() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    route3 = _label_body(text, "cmd_dispatch_gated__route_code_3_i2c_pair", ["cmd_dispatch_gated__route_code_4_i2c_pair"])
    reg1f = _label_body(text, "cmd_dispatch_gated__default_route_reg1f_write", ["cmd_dispatch_gated__dispatch_input_route_code"])

    _assert_ordered(
        route3,
        "movlw       0x08",
        "movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS",
        "movlw       0x30",
        "bra         cmd_dispatch_gated_i2c_pair",
    )
    _assert_ordered(
        reg1f,
        "call        drive_audio_route_select_latches, 0x0",
        "movlw       0x01",
        "call        i2c_tas3108_reg1f_write, 0x0",
        "bra         cmd_dispatch_gated__route_code_3_i2c_pair",
    )
    assert "movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS" not in reg1f
    assert "bra         cmd_dispatch_gated_i2c_pair" not in reg1f


def test_v34_zero_peepholes_stay_compact_without_status_sensitive_reuse() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    volume = _label_body(
        text,
        "cmd_dispatch_gated__apply_unmuted_volume_dirty",
        ["cmd_dispatch_gated__select_applied_route_trim"],
    )
    adaptive = _label_body(text, "adaptive_baud_select", ["stage_tas3108_coeff_input_scratch"])
    flash = _label_body(text, "fw_update_signature_status_word_helper", ["boot_cold_init__clear_ram_and_runtime_state"])

    assert "movff       channel_enable_mask_phys, channel_enable_shadow_phys" not in volume
    assert "bra         cmd_dispatch_gated__select_applied_route_trim" not in volume
    _assert_ordered(
        volume,
        "clrf        channel_enable_mask_b0, BANKED",
        "clrf        channel_enable_shadow_b0, BANKED",
        "clrf        route_volume_trim_offset_b0, BANKED",
    )

    assert "movff       pending_route_request_phys, applied_route_shadow_phys" not in adaptive
    _assert_ordered(
        adaptive,
        "clrf        pending_route_request_b0, BANKED",
        "clrf        applied_route_shadow_b0, BANKED",
        "bcf         INTCON3, 4, ACCESS",
    )

    _assert_ordered(
        flash,
        "movff       eeprom_mask_or_flash_src_high_scratch_phys, POSTDEC2",
        "rcall       fw_update_signature_load_fsr2_from_status_ptr",
        "btfsc       length_mask_or_divisor_low_scratch_byte, 7, ACCESS",
        "bsf         INDF2, 0, ACCESS",
        "rcall       fw_update_signature_load_fsr2_from_status_ptr",
    )
    assert "movlw       0x00\n    iorwf       POSTDEC2, F, ACCESS" not in flash
    assert "iorwf       POSTINC2, F, ACCESS" not in flash
    assert "movf        POSTDEC2, F, ACCESS" not in flash


def test_v34_boolean_staging_uses_file_register_increment_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    expected = {
        "hid_command_dispatch__check_mute_state_dirty": (
            ["hid_command_dispatch__check_channel_setup_dirty"],
            "diff_count_update_compare_or_route_mask_scratch_byte",
            "btfsc       active_flags_acc, 4, ACCESS",
        ),
        "wake_request_handler": (
            ["standby_request_handler"],
            "length_mask_or_divisor_low_scratch_byte",
            "btfss       active_flags_acc, 3, ACCESS",
        ),
        "cmd03_stage_mute_refresh_w": (
            ["cmd03_mute_on_handler"],
            "length_mask_or_divisor_low_scratch_byte",
            "btfsc       active_flags_acc, 4, ACCESS",
        ),
        "poll_src4382_route_monitor__sync_nonpcm_mute_state": (
            ["poll_src4382_route_monitor__clear_nonpcm_mute_mirror"],
            "flash_end_high_or_loop_mask_scratch_byte",
            "btfsc       active_flags_acc, 4, ACCESS",
        ),
        "usb_endpoint_mark_state_done": (
            ["flash_read"],
            "status_addr_high_or_i2c_payload_scratch_byte",
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
    setup_copy = _label_body(text, "usb_ep1_out_copy_packet_if_ready", ["fw_update_signature_status_word_helper"])
    reply_copy = _label_body(text, "usb_ep1_in_copy_scratch_buffer_to_bdt", ["usb_endpoint_mark_state_done"])
    _assert_ordered(
        setup_copy,
        "btfsc       usb_ep1_out_bd_status_b4, 7, BANKED",
        "return      0",
        "lfsr        FSR0, usb_ep1_out_bd_status_phys",
        "bra         usb_endpoint_mark_state_done",
    )
    _assert_ordered(
        reply_copy,
        "lfsr        FSR0, usb_ep1_in_bd_status_phys",
    )
    assert "bra         usb_endpoint_mark_state_done" not in reply_copy
    assert "rcall       usb_endpoint_mark_state_done" not in setup_copy
    assert "rcall       usb_endpoint_mark_state_done" not in reply_copy
    cmd03_helper = _label_body(text, "cmd03_stage_mute_refresh_w", ["cmd03_mute_on_handler"])
    _assert_ordered(
        cmd03_helper,
        "clrf        length_mask_or_divisor_low_scratch_byte, ACCESS",
        "btfsc       active_flags_acc, 4, ACCESS",
        "incf        length_mask_or_divisor_low_scratch_byte, F, ACCESS",
        "btfsc       active_flags_acc, 5, ACCESS",
        "retlw       0x01",
        "retlw       0x00",
    )
    for label, next_labels in {
        "cmd03_mute_on_handler": ["uart_link_parser__stage_zero_mute_compare_value"],
        "cmd03_mute_off_apply": ["cmd03_subdispatch"],
    }.items():
        body = _label_body(text, label, next_labels)
        _assert_ordered(
            body,
            "rcall       cmd03_stage_mute_refresh_w",
            "bra         uart_link_parser__mute_dirty_if_user_shadow_differs",
        )
        assert "movwf       length_mask_or_divisor_low_scratch_byte, ACCESS" not in body
    mute_off = _label_body(text, "cmd03_mute_off_apply", ["cmd03_subdispatch"])
    _assert_ordered(
        mute_off,
        "bcf         preset_job_flags_b2, 1, BANKED",
        "rcall       cmd03_stage_mute_refresh_w",
        "bra         uart_link_parser__mute_dirty_if_user_shadow_differs",
    )
    assert "bnz         uart_link_parser__mark_mute_refresh_dirty" not in mute_off

    flash = _label_body(text, "fw_update_signature_status_word_helper", ["boot_cold_init__clear_ram_and_runtime_state"])
    assert flash.count("rcall       fw_update_signature_load_fsr2_from_status_ptr") == 4
    _assert_ordered(
        flash,
        "rcall       fw_update_signature_load_fsr2_from_status_ptr",
        "clrf        POSTINC2, ACCESS",
        "clrf        POSTDEC2, ACCESS",
        "bra         fw_update_signature_status_word_helper__return",
    )
    fsr2_helper = _label_body(text, "fw_update_signature_load_fsr2_from_status_ptr", ["boot_cold_init__clear_ram_and_runtime_state"])
    _assert_ordered(
        fsr2_helper,
        "movf        count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS",
        "movwf       FSR2L, ACCESS",
        "clrf        FSR2H, ACCESS",
        "return      0",
    )
    assert "movlw       0x00\n    movwf       POSTINC2, ACCESS" not in flash


def test_v34_hid_cmd04_staging_uses_shared_ordered_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    clean_body = _label_body(text, "hid_command_dispatch__opcode04_ack_action_one", ["hid_command_dispatch__opcode04_stage_fault_action"])
    fault_body = _label_body(text, "hid_command_dispatch__opcode04_stage_fault_action", ["hid_command_dispatch__dispatch_opcode04_action"])
    helper = _label_body(text, "hid_stage_opcode04_status_one", ["hid_command_dispatch__opcode04_ack_action_one"])

    assert "rcall       hid_stage_opcode04_status_one" in clean_body
    _assert_ordered(
        clean_body,
        "rcall       hid_stage_opcode04_status_one",
        "bra         hid_command_dispatch__delay_before_status_response",
    )
    _assert_ordered(
        fault_body,
        "movff       usb_hid_out_arg2_phys, hid_opcode04_arg2_or_cmd1d_setup_phys",
        "rcall       hid_stage_opcode04_status_one",
        "bsf         dsp_fault_flags_b0, 0, BANKED",
        "bsf         main_runtime_latch_flags_b0, 4, BANKED",
    )
    _assert_ordered(
        helper,
        "movlw       0x04",
        "movwf       usb_hid_ep1_in_report_selector_b0, BANKED",
        "movlw       0x01",
        "movwf       usb_hid_ep1_in_report_selector_arg_b0, BANKED",
        "return      0",
    )


def test_v34_hid_settings_upload_rebuilds_route_bits_with_fsr2() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "hid_command_dispatch__apply_settings_payload", ["hid_command_dispatch__compare_settings_mirrors"])

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
    assert "btfsc       usb_hid_out_arg9_b1, 0, BANKED" not in body
    assert body.count("btfsc       INDF2, 0, ACCESS") == 6
    assert body.count("incf        FSR2L, F, ACCESS") == 6
    _assert_ordered(
        body,
        "movlb       0x0",
        "bcf         main_runtime_latch_flags_b0, 5, BANKED",
        "bcf         active_flags_acc, 4, ACCESS",
        "lfsr        FSR2, usb_hid_out_arg8_phys",
        "btfss       INDF2, 0, ACCESS",
        "bra         hid_command_dispatch__stage_settings_flag_bits",
        "bsf         main_runtime_latch_flags_b0, 5, BANKED",
        "bsf         active_flags_acc, 4, ACCESS",
        "hid_command_dispatch__stage_settings_flag_bits:",
        "movf        channel_enable_mask_b0, W, BANKED",
        "andlw       0xC0",
        "movwf       channel_enable_mask_b0, BANKED",
        "lfsr        FSR2, usb_hid_out_arg9_phys",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         channel_enable_mask_b0, 0, BANKED",
        "incf        FSR2L, F, ACCESS",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         channel_enable_mask_b0, 1, BANKED",
        "incf        FSR2L, F, ACCESS",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         channel_enable_mask_b0, 2, BANKED",
        "incf        FSR2L, F, ACCESS",
        "incf        FSR2L, F, ACCESS",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         channel_enable_mask_b0, 3, BANKED",
        "incf        FSR2L, F, ACCESS",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         channel_enable_mask_b0, 4, BANKED",
        "incf        FSR2L, F, ACCESS",
        "btfsc       INDF2, 0, ACCESS",
        "bsf         channel_enable_mask_b0, 5, BANKED",
    )


def test_v34_rail_adc_thresholds_use_shared_carry_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "compare_adc_rail_sample_to_threshold_w", ["hw_standby_shutdown"])
    boot = _label_body(text, "adc_boot_gate__check_rail_threshold", ["adc_boot_gate__start_dsp_cold_init"])
    standby = _label_body(
        text,
        "hw_standby_shutdown__drop_outputs_after_baud_select",
        ["hw_standby_shutdown__rail_discharge_pulse_loop"],
    )
    monitor = _label_body(text, "an0_hysteresis_monitor", ["an0_hysteresis_monitor__reset_delay_counter"])

    _assert_ordered(
        helper,
        "movlb       0x0",
        "subwf       adc_rail_sample_lo_b0, W, BANKED",
        "movlw       0x02",
        "subwfb      adc_rail_sample_hi_b0, W, BANKED",
        "return      0",
    )
    _assert_ordered(
        boot,
        "movlw       0x36",
        "call        compare_adc_rail_sample_to_threshold_w, 0x0",
        "bc          adc_boot_gate__start_dsp_cold_init",
    )
    _assert_ordered(
        standby,
        "movlw       0x28",
        "rcall       compare_adc_rail_sample_to_threshold_w",
        "bc          hw_standby_shutdown__stop_timer0_and_usb",
    )
    assert monitor.count("rcall       compare_adc_rail_sample_to_threshold_w") == 2
    _assert_ordered(
        monitor,
        "movlw       0x29",
        "rcall       compare_adc_rail_sample_to_threshold_w",
        "btfsc       STATUS, 0, ACCESS",
        "bsf         main_runtime_latch_flags_b0, 2, BANKED",
    )
    _assert_ordered(
        monitor,
        "btfss       main_runtime_latch_flags_b0, 2, BANKED",
        "bra         an0_hysteresis_monitor__reset_delay_counter",
        "movlw       0x28",
        "rcall       compare_adc_rail_sample_to_threshold_w",
        "bc          an0_hysteresis_monitor__reset_delay_counter",
    )


def test_v34_fw_update_addr77_compare_uses_shared_carry_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "fw_update_compare_relay_addr_limit_w", ["fw_update_relay"])
    add_helper = _label_body(text, "fw_update_add_byte_to_relay_checksum", ["fw_update_relay"])
    body = _label_body(text, "fw_update_relay", ["main_core_service_184a"])
    hex_helper = _label_body(text, "hex_store_ascii_byte_to_postinc2", ["hex_lookup_table_ptr"])
    tx_block_helper = _label_body(
        text,
        "fw_update_tx_text_block_from_w",
        ["fw_update_relay__handle_status_checksum_mismatch"],
    )

    _assert_ordered(
        helper,
        "movlb       0x0",
        "subwf       fw_update_relay_addr_lo_b0, W, BANKED",
        "movlw       0x77",
        "subwfb      fw_update_relay_addr_hi_b0, W, BANKED",
        "return      0",
    )
    assert body.count("rcall       fw_update_compare_relay_addr_limit_w") == 4
    for threshold in ("0xC0", "0xBF"):
        assert f"movlw       {threshold}\n    rcall       fw_update_compare_relay_addr_limit_w" in body
    _assert_ordered(
        add_helper,
        "movlb       0x0",
        "addwf       fw_update_relay_checksum_accum_lo_b0, F, BANKED",
        "movlw       0x00",
        "addwfc      fw_update_relay_checksum_accum_hi_b0, F, BANKED",
        "return      0",
    )
    assert body.count("rcall       fw_update_add_byte_to_relay_checksum") == 3
    assert body.count("rcall       fw_update_tx_text_block_from_w") == 3
    _assert_ordered(
        tx_block_helper,
        "clrf        float32_product_or_uart_base_high_scratch_byte, ACCESS",
        "movwf       float32_product_or_uart_base_scratch_byte, ACCESS",
        "goto        uart_tx_block_from_buffer",
    )
    assert (
        "clrf        float32_product_or_uart_base_high_scratch_byte, ACCESS\n"
        "    movlw       0x1D\n"
        "    movwf       float32_product_or_uart_base_scratch_byte, ACCESS\n"
        "    call        uart_tx_block_from_buffer, 0x0"
    ) not in body
    assert (
        "movwf       fw_update_hex_or_float32_quotient_or_uart_block_scratch, ACCESS\n"
        "    clrf        float32_product_or_uart_base_high_scratch_byte, ACCESS\n"
        "    movff       fw_update_hex_byte_or_uart_block_base_low_scratch_phys, preset_header_tas_reg_or_uart_block_base_low_scratch_phys\n"
        "    call        uart_tx_block_from_buffer, 0x0"
    ) not in body
    assert (
        "clrf        float32_product_or_uart_base_high_scratch_byte, ACCESS\n"
        "    movlw       0x2F\n"
        "    movwf       float32_product_or_uart_base_scratch_byte, ACCESS\n"
        "    call        uart_tx_block_from_buffer, 0x0"
    ) not in body
    assert (
        "movlw       0x0F\n"
        "    andwf       fw_update_hex_or_float32_quotient_or_uart_block_scratch, F, ACCESS\n"
        "    andwf       fw_update_hex_or_float32_quotient_or_uart_block_scratch, F, ACCESS"
    ) not in body
    _assert_ordered(
        body,
        "movlw       0x9A",
        "rcall       setup_fsr2_page1_or_page2_from_w_carry",
        "movff       fw_update_relay_checksum_accum_lo_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys",
        "rcall       hex_store_ascii_byte_to_postinc2",
        "clrf        INDF2, ACCESS",
        "movlw       0x02",
        "addwf       fw_update_offset_or_channel_enable_row_base_scratch, F, ACCESS",
    )
    assert "rcall       hex_lookup_table_ptr                ; indexed TBLPTR -> hex_lookup_table" not in body
    _assert_ordered(
        body,
        "lfsr        FSR2, fw_update_intel_hex_record_addr_hi_high_nibble_phys",
        "movff       fw_update_relay_saved_addr_hi_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys",
        "rcall       hex_store_ascii_byte_to_postinc2",
        "movff       fw_update_relay_saved_addr_lo_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys",
        "rcall       hex_store_ascii_byte_to_postinc2",
    )
    _assert_ordered(
        body,
        "lfsr        FSR2, float32_preset_fw_update_scratch_byte0_b0_phys",
        "movff       fw_update_even_addr_pending_byte_b0_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys",
        "rcall       hex_store_ascii_byte_to_postinc2",
        "movff       fw_update_relay_current_byte_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys",
        "rcall       hex_store_ascii_byte_to_postinc2",
    )
    _assert_ordered(
        hex_helper,
        "movff       fw_update_hex_byte_or_uart_block_base_low_scratch_phys, hex_byte_save_or_uart_status_block_buffer_phys",
        "swapf       fw_update_hex_or_float32_quotient_or_uart_block_scratch, F, ACCESS",
        "rcall       hex_store_ascii_low_nibble_to_postinc2",
        "movff       hex_byte_save_or_uart_status_block_buffer_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys",
        "bra         hex_store_ascii_low_nibble_to_postinc2",
        "hex_store_ascii_low_nibble_to_postinc2:",
        "movlw       0x0F",
        "andwf       fw_update_hex_or_float32_quotient_or_uart_block_scratch, F, ACCESS",
        "movf        fw_update_hex_or_float32_quotient_or_uart_block_scratch, W, ACCESS",
        "rcall       hex_lookup_table_ptr",
        "tblrd*",
        "movff       TABLAT, POSTINC2",
        "return      0",
    )
    assert "nibble_to_hex_ascii_from_01B" not in hex_helper


def test_v34_fw_update_stages_005_and_008_with_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "fw_update_stage_uart_rx_window", ["fw_update_clear_relay_status_accumulators"])
    init = _label_body(text, "fw_update_start_relay_handshake", ["fw_update_init_sequence__gate_relay_session"])
    relay = _label_body(text, "fw_update_relay__poll_status_response", ["fw_update_relay__handle_status_checksum_mismatch"])
    clear_helper = _label_body(
        text,
        "fw_update_clear_buffer_from_003_len_w",
        ["fw_update_clear_relay_status_accumulators"],
    )

    _assert_ordered(
        helper,
        "movwf       length_mask_or_divisor_low_scratch_byte, ACCESS",
        "movlb       0x1",
        "movlw       0x01",
        "movwf       flash_end_high_or_loop_mask_scratch_byte, ACCESS",
        "return      0",
    )
    _assert_ordered(init, "movlw       0xDC", "rcall       fw_update_stage_uart_rx_window")
    _assert_ordered(
        init,
        "rcall       fw_update_clear_relay_status_accumulators",
        "call        ram_clear_prepare_page1_address_high, 0x0",
        "movlw       0xC7",
        "rcall       fw_update_clear_buffer_from_003_len_w",
        "movlw       0x9A",
        "rcall       fw_update_clear_buffer_from_003_len_w",
        "movlw       0xD1",
        "rcall       fw_update_clear_buffer_from_003_len_w",
    )
    assert init.count("rcall       fw_update_clear_buffer_from_003_len_w") == 3
    assert "call        clear_ram_span_from_staged_addr_count, 0x0" not in init
    _assert_ordered(
        clear_helper,
        "movwf       length_mask_or_divisor_low_scratch_byte, ACCESS",
        "goto        clear_ram_span_from_staged_addr_count",
    )
    assert init.count("call        ram_clear_prepare_page1_address_high, 0x0") == 1
    _assert_ordered(relay, "movlw       0x0A", "rcall       fw_update_stage_uart_rx_window")


def test_v34_cmd19_status_bit_fanout_uses_rotate_carry_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(
        text,
        "stage_hid_ep1_in_report_from_selector__stage_selector5_status_snapshot",
        ["stage_hid_ep1_in_report_from_selector__stage_selector6_version_setup"],
    )
    helper = _label_body(text, "fanout_channel_enable_bits_to_usb_report_bytes", ["copy_indexed_fsr2_byte_to_hid_ep1_in"])

    _assert_ordered(
        body,
        "clrf        usb_hid_ep1_in_report_payload_byte6_b1, BANKED",
        "btfsc       active_flags_acc, 4, ACCESS",
        "incf        usb_hid_ep1_in_report_payload_byte6_b1, F, BANKED",
        "movff       channel_enable_mask_phys, status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys",
        "lfsr        FSR2, usb_hid_ep1_in_report_payload_byte7_phys",
        "movlw       0x03",
        "rcall       fanout_channel_enable_bits_to_usb_report_bytes",
        "incf        FSR2L, F, ACCESS",
        "movlw       0x03",
        "rcall       fanout_channel_enable_bits_to_usb_report_bytes",
    )
    _assert_ordered(
        helper,
        "rrcf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS",
        "clrf        INDF2, ACCESS",
        "rlcf        POSTINC2, F, ACCESS",
        "decfsz      WREG, F, ACCESS",
        "bra         fanout_channel_enable_bits_to_usb_report_bytes",
        "return      0",
    )
    assert "clrf        usb_hid_ep1_in_report_payload_byte7_b1, BANKED" not in body
    assert "clrf        usb_hid_ep1_in_report_payload_byte11_b1, BANKED" not in body
    assert "movlb       0x0\n    btfsc       channel_enable_mask_b0" not in body
    assert "movwf       usb_hid_ep1_in_report_payload_byte7_b1, BANKED" not in body


def test_v34_volume_logical_diff_uses_shared_z_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    hid = _label_body(text, "hid_command_dispatch__compare_settings_mirrors", ["hid_command_dispatch__check_route_trim_dirty"])
    uart = _label_body(text, "volume_cmd_handler", ["uart_link_parser__volume_query_reply"])
    helper = _label_body(text, "volume_logical_diff_z", ["hid_out_payload_index_to_fsr2"])

    _assert_ordered(
        hid,
        "movf        input_select_mirror_b0, W, BANKED",
        "xorwf       input_select_b0, W, BANKED",
        "btfss       STATUS, 2, ACCESS",
        "bsf         main_runtime_latch_flags_b0, 0, BANKED",
        "rcall       volume_logical_diff_z",
        "hid_command_dispatch__mark_volume_dirty_if_changed:",
        "bz          hid_command_dispatch__check_route_trim_dirty",
    )
    _assert_ordered(
        uart,
        "movwf       computed_volume_2_b0, BANKED",
        "movwf       computed_volume_3_b0, BANKED",
        "rcall       volume_logical_diff_z",
        "uart_link_parser__volume_return_if_unchanged:",
        "bz          uart_link_parser__handler_return_tail",
    )
    _assert_ordered(
        helper,
        "movlb       0x0",
        "movf        logical_volume_3_b0, W, BANKED",
        "xorwf       computed_volume_3_b0, W, BANKED",
        "bnz         volume_logical_diff_z__return",
        "movf        logical_volume_2_b0, W, BANKED",
        "xorwf       computed_volume_2_b0, W, BANKED",
        "bnz         volume_logical_diff_z__return",
        "movf        logical_volume_1_b0, W, BANKED",
        "xorwf       computed_volume_1_b0, W, BANKED",
        "bnz         volume_logical_diff_z__return",
        "movf        logical_volume_b0, W, BANKED",
        "xorwf       computed_volume_b0, W, BANKED",
        "volume_logical_diff_z__return:",
        "return      0",
    )
    assert hid.count("rcall       volume_logical_diff_z") == 1
    assert uart.count("rcall       volume_logical_diff_z") == 1


def test_v34_eeprom_write_gie_snapshot_uses_increment_boolean_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "eeprom_write_blocking", ["nvm_unlock_and_set_wr"])

    _assert_ordered(
        body,
        "bsf         EECON1, 2, ACCESS",
        "clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS",
        "btfsc       INTCON, 7, ACCESS",
        "incf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS",
        "bcf         INTCON, 7, ACCESS",
        "rcall       nvm_unlock_and_set_wr",
    )
    assert "movlw       0x00\n    btfsc       INTCON, 7, ACCESS" not in body
    assert "movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS" not in body


def test_v34_flash_page_c0_setup_uses_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "fw_update_stage_flash_page_window", ["fw_update_commit_hid_payload_page"])
    body = _label_body(text, "fw_update_commit_hid_payload_page", ["float32_divide_primary_by_secondary_in_place"])

    _assert_ordered(
        helper,
        "rcall       fw_update_stage_flash_addr_from_cursor",
        "clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS",
        "movlw       0xC0",
        "movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS",
        "movlb       0x3",
        "movlw       0x03",
        "movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS",
        "clrf        flash_src_low_or_rx_length_scratch_byte, ACCESS",
        "return      0",
    )
    assert body.count("rcall       fw_update_stage_flash_page_window") == 2
    assert (
        "rcall       fw_update_stage_flash_addr_from_cursor\n"
        "    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS\n"
        "    movlw       0xC0"
    ) not in body


def test_v34_flash_write_reuses_tblptr_stage_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "flash_write_stage_block_cursor_shadow", ["flash_write__start_next_block"])
    body = _label_body(text, "flash_write__start_next_block", ["usb_sie_endpoint_pump"])

    _assert_ordered(
        helper,
        "movff       flash_addr_shadow_upper_or_preset_job_index_or_init_copy_end_phys, eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys",
        "movff       float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys, fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys",
        "movff       flash_addr_shadow_low_or_preset_table_addr_hi_phys, flash_addr_low_or_float32_scale_or_flash_read_tblptru_save_phys",
        "return      0",
    )
    assert body.count("rcall       flash_write_stage_block_cursor_shadow") == 2
    assert (
        "movff       flash_addr_shadow_upper_or_preset_job_index_or_init_copy_end_phys, eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys\n"
        "    movff       float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys, fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys\n"
        "    movff       flash_addr_shadow_low_or_preset_table_addr_hi_phys, flash_addr_low_or_float32_scale_or_flash_read_tblptru_save_phys"
    ) not in body


def test_v34_flash_and_core30d8_share_004_006_carry_propagation() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "propagate_carry_to_u32_scratch_high24", ["flash_write__start_next_block"])
    flash = _label_body(text, "flash_write_without_preset_remap", ["usb_sie_endpoint_pump"])
    core_30d8 = _label_body(text, "float32_pack_mantissa_exponent_sign", ["shift_003_006_right_clear_c"])

    _assert_ordered(
        helper,
        "movlw       0x00",
        "addwfc      addr_high_table_row_or_checksum_scratch_byte, F, ACCESS",
        "addwfc      length_mask_or_divisor_low_scratch_byte, F, ACCESS",
        "addwfc      status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS",
        "return      0",
    )
    _assert_ordered(
        flash,
        "movlw       0x20",
        "addwf       addr_low_counter_or_payload_scratch_byte, F, ACCESS",
        "rcall       propagate_carry_to_u32_scratch_high24",
    )
    _assert_ordered(
        core_30d8,
        "incf        addr_low_counter_or_payload_scratch_byte, F, ACCESS",
        "rcall       propagate_carry_to_u32_scratch_high24",
        "rcall       shift_003_006_right_clear_c",
    )
    assert text.count("rcall       propagate_carry_to_u32_scratch_high24") == 2


def test_v34_core30d8_keeps_live_exponent_or_without_scratch_zero_fanout() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "float32_pack_mantissa_exponent_sign", ["shift_003_006_right_clear_c"])

    _assert_ordered(
        body,
        "movlw       0xFE",
        "andwf       status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS",
        "bz          float32_pack_mantissa_exponent_sign__check_guard_byte",
    )
    _assert_ordered(
        body,
        "movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS",
        "bz          float32_pack_mantissa_exponent_sign__normalize_left_to_mantissa_msb",
    )
    _assert_ordered(
        body,
        "rrcf        count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS",
        "movf        count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS",
        "iorwf       status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS",
        "clrf        flash_src_low_or_rx_length_scratch_byte, ACCESS",
        "clrf        eeprom_mask_or_flash_src_high_scratch_byte, ACCESS",
        "clrf        eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, ACCESS",
        "clrf        uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, ACCESS",
        "tstfsz      flash_end_high_or_loop_mask_scratch_byte, ACCESS",
    )
    for dead in (
        "movwf       uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, ACCESS\n    iorwf       flash_src_low_or_rx_length_scratch_byte, W, ACCESS",
        "movwf       uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, ACCESS\n    iorwf       flash_src_low_or_rx_length_scratch_byte, W, ACCESS",
        "clrf        flash_src_low_or_rx_length_scratch_byte, ACCESS\n    movf        flash_src_low_or_rx_length_scratch_byte, W, ACCESS",
        "movf        uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, W, ACCESS\n    iorwf       status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS",
        "movff       computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys, timeout_hi_b0_phys",
    ):
        assert dead not in body


def test_v34_flash_write_stock_uses_chain_copy_for_address_snapshot() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "flash_write_without_preset_remap", ["flash_write__start_next_block"])

    for old_copy in (
        "movff       addr_low_counter_or_payload_scratch_phys, flash_addr_shadow_low_or_preset_table_addr_hi_phys",
        "movff       addr_high_table_row_or_checksum_scratch_phys, float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys",
        "movff       saved_w_b0_phys, flash_addr_shadow_upper_or_preset_job_index_or_init_copy_end_phys",
        "movff       status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys, float_product_or_output_index_scratch_bank0_phys",
    ):
        assert old_copy not in body
    _assert_ordered(
        body,
        "clrf        flash_gie_or_float_sign_scratch_byte, ACCESS",
        "rcall       chain_copy",
        "db          0x00, 0x00, addr_low_counter_or_payload_scratch_operand, flash_write_start_addr_shadow_dword_op, 0x04, 0xFF",
        "movlw       0x05",
        "movwf       eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, ACCESS",
    )


def test_v34_math_operand_middle_copy_uses_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "copy_math_operand_low24_to_secondary", ["float32_exp_limit1024_in_place"])
    early = _label_body(text, "float32_add_secondary_to_primary_in_place", ["twos_complement_024_027_after_low_byte_complement"])
    s3 = _label_body(text, "copy_math_operand_to_secondary_shadow", ["float32_to_int32_in_place"])

    _assert_ordered(
        helper,
        "rcall       chain_copy",
        "db          0x00, 0x00, float32_math_operand_byte0_op, float32_secondary_work_byte0_op, 0x03, 0xFF",
        "return      0",
    )
    _assert_ordered(
        early,
        "movff       float32_aux_work_byte0_b0_phys, float32_math_operand_byte3_b0_phys",
        "rcall       copy_math_operand_low24_to_secondary",
        "rcall       shift_028_02b_right_23_clear_c",
    )
    _assert_ordered(
        s3,
        "rcall       copy_math_operand_low24_to_secondary",
        "movff       float32_math_operand_byte3_b0_phys, float32_secondary_work_byte3_b0_phys",
        "return      0",
    )
    assert early.count("rcall       copy_math_operand_low24_to_secondary") == 1
    assert s3.count("rcall       copy_math_operand_low24_to_secondary") == 1


def test_v34_s3_math_and_adc_helpers_use_chain_copy_descriptors() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    math = _label_body(text, "copy_transform_shadow_to_math_operand", ["main_core_service_2d80"])
    adc = _label_body(text, "adc_stage_division_operands_from_sample_window", ["format_uint16_radix_ascii_to_w_pointer__emit_next_digit"])

    for old_copy in (
        "movff       float32_preset_fw_update_scratch_byte0_b0_phys, float32_math_operand_byte0_b0_phys",
        "movff       preset_payload_index_or_float32_shadow_byte1_b0_phys, float32_math_operand_byte1_b0_phys",
        "movff       preset_table_row_len_phys, float32_math_operand_byte2_b0_phys",
        "movff       float32_transform_shadow_byte3_b0_phys, float32_math_operand_byte3_b0_phys",
    ):
        assert old_copy not in math
    for old_copy in (
        "movff       eeprom_mask_or_flash_src_high_scratch_phys, addr_low_counter_or_payload_scratch_phys",
        "movff       timeout_lo_b0_phys, addr_high_table_row_or_checksum_scratch_phys",
        "movff       timeout_hi_b0_phys, saved_w_b0_phys",
        "movff       flash_saved_tblptrh_phys, status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys",
    ):
        assert old_copy not in adc

    _assert_ordered(
        math,
        "rcall       chain_copy",
        "db          0x00, 0x00, float32_transform_shadow_dword_op, float32_math_operand_byte0_op, 0x04, 0xFF",
        "return      0",
    )
    _assert_ordered(
        adc,
        "rcall       chain_copy",
        "db          0x00, 0x00, numeric_format_value_dword_op, addr_low_counter_or_payload_scratch_operand, 0x04, 0xFF",
        "return      0",
    )


def test_v34_adc_division_compare_subtract_is_shared() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "adc_div_compare_subtract_staged_words", ["an0_hysteresis_monitor"])
    adc_div = _label_body(text, "adc_divide_staged_words", ["an0_hysteresis_monitor"])
    core_div = _label_body(text, "adc_remainder_staged_words", ["flash_write_with_gie_off"])

    _assert_ordered(
        helper,
        "movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS",
        "subwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS",
        "movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS",
        "subwfb      addr_high_table_row_or_checksum_scratch_byte, W, ACCESS",
        "bnc         adc_div_compare_subtract_staged_words__return",
        "movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS",
        "subwf       addr_low_counter_or_payload_scratch_byte, F, ACCESS",
        "movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS",
        "subwfb      addr_high_table_row_or_checksum_scratch_byte, F, ACCESS",
        "adc_div_compare_subtract_staged_words__return:",
        "return      0",
    )
    _assert_ordered(
        adc_div,
        "rlcf        flash_end_high_or_loop_mask_scratch_byte, F, ACCESS",
        "rcall       adc_div_compare_subtract_staged_words",
        "btfsc       STATUS, 0, ACCESS",
        "bsf         count_flash_page_or_i2c_payload_scratch_byte, 0, ACCESS",
    )
    _assert_ordered(
        core_div,
        "btfss       status_addr_high_or_i2c_payload_scratch_byte, 7, ACCESS",
        "rcall       adc_div_compare_subtract_staged_words",
        "bcf         STATUS, 0, ACCESS",
    )


def test_v34_usb_endpoint_clear_uses_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "usb_clear_uep1_7", ["usb_bus_reset_reinitialize"])
    reset = _label_body(text, "usb_bus_reset_reinitialize", ["format_int16_decimal_ascii_to_w_pointer"])
    reinit = _label_body(text, "usb_apply_set_configuration", ["i2c_secondary_dev_random_read"])

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
    _assert_ordered(reinit, "movwf       usb_ep0_control_response_mode_b0, BANKED", "rcall       usb_clear_uep1_7", "clrf        usb_reset_lowram_clear_index_b0, BANKED")
    assert reset.count("clrf        UEP1, ACCESS") == 0
    assert reinit.count("clrf        UEP1, ACCESS") == 0


def test_v34_usb_descriptor_tblptr_staging_uses_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "usb_stage_tblptr_from_flash_ptr_cache", ["usb_ep0_prepare_in_data_copy_pointers"])
    setup = _label_body(text, "usb_ep0_prepare_in_data_copy_pointers", ["usb_ep0_store_in_data_byte_and_advance"])
    descriptor = _label_body(text, "usb_ep0_select_get_descriptor_payload", ["read_low_memory_byte_at_tblptr"])

    _assert_ordered(
        helper,
        "movff       usb_ep0_in_source_ptr_lo_phys, TBLPTRL",
        "movff       usb_ep0_in_source_ptr_hi_phys, TBLPTRH",
        "clrf        TBLPTRU, ACCESS",
        "return      0",
    )
    _assert_ordered(
        setup,
        "rcall       usb_stage_tblptr_from_flash_ptr_cache",
        "rcall       load_fsr2_from_target_ptr",
        "retlw       0x07",
    )
    _assert_ordered(
        descriptor,
        "movff       TABLAT, usb_ep0_in_source_ptr_lo_phys",
        "movwf       usb_ep0_in_source_ptr_hi_b0, BANKED",
        "rcall       usb_stage_tblptr_from_flash_ptr_cache",
        "movlw       0x07",
    )
    assert setup.count("rcall       usb_stage_tblptr_from_flash_ptr_cache") == 1
    assert descriptor.count("rcall       usb_stage_tblptr_from_flash_ptr_cache") == 1


def test_v34_return_value_tails_use_retlw() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    usb_setup = _label_body(text, "usb_ep0_prepare_in_data_copy_pointers", ["usb_ep0_store_in_data_byte_and_advance"])
    signed = _label_body(text, "signed_hi_bias80_compare_prelude", ["usb_hid_dispatch_out_report_if_ready"])

    assert "retlw       0x07" in usb_setup
    assert "movlw       0x07\n    return      0" not in usb_setup
    assert "retlw       0x00" in signed
    assert "movlw       0x00\n    return      0" not in signed


def test_v34_fsr2_from_stock072073_is_shared() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "load_fsr2_from_target_ptr", ["format_uint16_radix_ascii_to_w_pointer"])
    filter_body = _label_body(text, "usb_ep0_apply_clear_set_feature_request", ["load_fsr2_from_target_ptr"])
    setup = _label_body(text, "usb_ep0_prepare_in_data_copy_pointers", ["usb_ep0_store_in_data_byte_and_advance"])
    dispatch = _label_body(text, "usb_ep0_prepare_get_status_reply", ["usb_ep0_select_get_descriptor_payload"])
    standby = _label_body(text, "hw_standby_shutdown", ["hw_standby_shutdown_i2c_table"])

    _assert_ordered(
        helper,
        "movff       fsr2_target_ptr_lo_phys, FSR2L",
        "movff       fsr2_target_ptr_hi_phys, FSR2H",
        "return      0",
    )
    assert filter_body.count("rcall       load_fsr2_from_target_ptr") == 4
    assert setup.count("rcall       load_fsr2_from_target_ptr") == 1
    assert dispatch.count("rcall       load_fsr2_from_target_ptr") == 1
    assert "movff       fsr2_target_ptr_lo_phys, FSR2L" not in filter_body
    assert "movff       fsr2_target_ptr_hi_phys, FSR2H" not in filter_body
    _assert_ordered(
        standby,
        "movlw       0x03",
        "rcall       i2c_secondary_write_table_rows",
        "btfss       PORTC, 2, ACCESS",
    )


def test_v34_usb_descriptor_dirty_return_tail_is_shared() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    lowpage = _label_body(text, "usb_ep0_stage_one_byte_lowpage_in_data_pointer", ["usb_ep0_mark_one_byte_lowpage_in_data_ready"])
    helper = _label_body(text, "usb_ep0_mark_one_byte_lowpage_in_data_ready", ["usb_ep0_arm_next_out_pingpong_bd"])
    setup = _label_body(text, "shift_003_006_right_clear_c", ["usb_ep0_arm_next_out_pingpong_bd"])
    descriptor = _label_body(text, "usb_ep0_dispatch_standard_setup_request", ["usb_ep0_prepare_get_status_reply"])

    _assert_ordered(
        lowpage,
        "clrf        usb_ep0_in_source_ptr_hi_b0, BANKED",
        "movwf       usb_ep0_in_source_ptr_lo_b0, BANKED",
    )
    _assert_ordered(
        helper,
        "bcf         usb_ep0_control_flags_b0, 1, BANKED",
        "movlw       0x01",
        "movwf       usb_ep0_transfer_remaining_lo_b0, BANKED",
        "return      0",
    )
    _assert_ordered(
        setup,
        "usb_ep0_dispatch_hid_setup_request__stage_get_idle_reply:",
        "movlw       0xEA",
        "bra         usb_ep0_stage_one_byte_lowpage_in_data_pointer",
        "usb_ep0_dispatch_hid_setup_request__stage_get_protocol_reply:",
        "movlw       0xE9",
        "bra         usb_ep0_stage_one_byte_lowpage_in_data_pointer",
    )
    _assert_ordered(
        descriptor,
        "usb_ep0_dispatch_standard_setup_request__get_configuration:",
        "movlw       0xEB",
        "bra         usb_ep0_stage_one_byte_lowpage_in_data_pointer",
        "movff       saved_w_b0_phys, usb_ep0_in_source_ptr_lo_phys",
        "bra         usb_ep0_mark_one_byte_lowpage_in_data_ready",
    )
    assert "flow_main_core_service_3188_3208:" not in setup
    assert "flow_main_core_service_3682_36ac:" not in descriptor


def test_v34_usb_service_4080_stock096_update_uses_shared_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "usb_ep0_arm_next_out_pingpong_bd", ["usb_ep0_arm_control_transfer_response"])
    body = _label_body(text, "usb_ep0_arm_control_transfer_response", ["i2c_secondary_apply_wake_init_table"])
    core_4080 = _label_body(text, "usb_ep0_arm_out_pingpong_bd", ["usb_clear_uep1_7"])

    _assert_ordered(
        helper,
        "decf        usb_ep0_out_next_bd_toggle_b0, W, BANKED",
        "bnz         usb_ep0_arm_next_out_pingpong_bd__arm_even_bd",
        "movlw       0x01",
        "rcall       usb_ep0_arm_out_pingpong_bd_window",
        "clrf        usb_ep0_out_next_bd_toggle_b0, BANKED",
        "return      0",
        "movlw       0x00",
        "rcall       usb_ep0_arm_out_pingpong_bd_window",
        "movlw       0x01",
        "movwf       usb_ep0_out_next_bd_toggle_b0, BANKED",
        "return      0",
    )
    assert body.count("rcall       usb_ep0_arm_next_out_pingpong_bd") == 2
    assert core_4080.count("movwf       usb_bdt_template_addr_hi_b1, BANKED") == 1
    _assert_ordered(
        core_4080,
        "lfsr        FSR0, usb_bdt_template_status_phys",
        "movlw       0x04",
        "call        hid_diag_snapshot_copy_block_count_w, 0x0",
        "movlw       0xFC",
        "addwf       FSR2L, F, ACCESS",
        "bsf         INDF2, 7, ACCESS",
    )
    assert "movff       stock_078_b0_phys, FSR2L" not in core_4080
    assert "movff       stock_079_b0_phys, FSR2H" not in core_4080
    assert core_4080.count("movwf       FSR2H, ACCESS") == 1
    assert "tstfsz      addr_low_counter_or_payload_scratch_byte, ACCESS\n    bra         usb_ep0_arm_out_pingpong_bd__select_odd_bd\n    movlw       0x04\n    movwf       usb_bdt_template_addr_hi_b1, BANKED" not in core_4080
    assert "bnz         flow_main_core_service_3188_326c" not in body
    assert "bnz         flow_main_core_service_3188_32dc" not in body
    assert "flow_main_core_service_3188_326c:" not in body
    assert "flow_main_core_service_3188_32dc:" not in body


def test_v34_usb_stock116_store_uses_bsr0_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "usb_stage_bdt_template_status_w", ["adaptive_baud_select"])
    service = _label_body(text, "usb_ep0_arm_control_transfer_response", ["i2c_secondary_apply_wake_init_table"])
    reset = _label_body(text, "usb_bus_reset_reinitialize", ["format_int16_decimal_ascii_to_w_pointer"])

    _assert_ordered(
        helper,
        "movlb       0x1",
        "movwf       usb_bdt_template_status_b1, BANKED",
        "movlb       0x0",
        "return      0",
    )
    assert service.count("rcall       usb_stage_bdt_template_status_w") == 4
    assert reset.count("rcall       usb_stage_bdt_template_status_w") == 1
    _assert_ordered(
        service,
        "movlw       0x04",
        "rcall       usb_stage_bdt_template_status_w",
        "rcall       usb_ep0_arm_next_out_pingpong_bd",
        "movlw       0x48",
        "rcall       usb_stage_bdt_template_status_w",
        "movlw       0x01",
        "rcall       usb_ep0_arm_out_pingpong_bd_window",
        "movlw       0x04",
        "rcall       usb_stage_bdt_template_status_w",
        "movf        usb_setup_w_length_hi_b0, W, BANKED",
        "movlw       0x48",
        "rcall       usb_stage_bdt_template_status_w",
    )
    _assert_ordered(
        reset,
        "movlw       0x04",
        "rcall       usb_stage_bdt_template_status_w",
        "movlw       0x00",
        "rcall       usb_ep0_arm_out_pingpong_bd",
    )


def test_v34_usb_offset_ec_paths_share_0c8_0d3_prelude() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "usb_ep0_stage_interface_alt_setting_offset", ["usb_ep0_dispatch_standard_setup_request__get_interface"])
    body = _label_body(text, "usb_ep0_dispatch_standard_setup_request", ["usb_ep0_prepare_get_status_reply"])

    _assert_ordered(
        helper,
        "movlw       0x01",
        "movwf       usb_ep0_control_response_mode_b0, BANKED",
        "movf        usb_setup_w_index_lo_b0, W, BANKED",
        "addlw       0xEC",
        "return      0",
    )
    _assert_ordered(
        body,
        "usb_ep0_dispatch_standard_setup_request__get_interface:",
        "rcall       usb_ep0_stage_interface_alt_setting_offset",
        "movwf       length_mask_or_divisor_low_scratch_byte, ACCESS",
        "usb_ep0_dispatch_standard_setup_request__set_interface:",
        "rcall       usb_ep0_stage_interface_alt_setting_offset",
        "movwf       FSR2L, ACCESS",
    )
    assert body.count("rcall       usb_ep0_stage_interface_alt_setting_offset") == 2


def test_v34_channel_config_handlers_share_offset_indexed_mirror_dirty_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    dispatch = _label_body(
        text,
        "cmd_dispatch_xor_chain",
        ["uart_link_parser__handler_return_tail"],
    )
    body = _label_body(
        text,
        "uart_update_channel_config_cache_from_cmd_index",
        ["uart_link_parser__cmd1d_update_setup_timeout"],
    )
    helper = _label_body(
        text,
        "uart_update_channel_config_cache_from_w_index",
        ["uart_link_parser__cmd1d_update_setup_timeout"],
    )

    assert "movff       current_cmd_data_b0_phys, channel_1_source_config_phys" not in body
    assert "xorwf       channel_1_source_config_shadow_b0, W, BANKED" not in body
    _assert_ordered(
        dispatch,
        "movf        uart_current_cmd_code_b0, W, BANKED",
        "addlw       0xE9",
        "movwf       uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, ACCESS",
        "sublw       0x05",
        "bc          uart_update_channel_config_cache_from_cmd_index",
    )
    _assert_ordered(
        body,
        "uart_update_channel_config_cache_from_cmd_index:",
        "movf        uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, W, ACCESS",
        "uart_update_channel_config_cache_from_w_index:",
    )
    assert "bra         uart_update_channel_config_cache_from_w_index" not in dispatch
    assert helper.count("cpfseq") == 1
    _assert_ordered(
        helper,
        "addlw       channel_1_source_config_op",
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
        "bra         uart_link_parser__handler_return_tail",
    )


def test_v34_hid_route_cache_compare_uses_shared_z_helper() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    filename = _label_body(
        text,
        "hid_command_dispatch__check_route_trim_dirty",
        ["hid_command_dispatch__check_channel_setup_dirty"],
    )
    body = _label_body(
        text,
        "hid_command_dispatch__check_channel_setup_dirty",
        ["hid_command_dispatch__snapshot_settings_mirrors"],
    )
    helper = _label_body(
        text,
        "compare_fsr0_fsr1_bytes_z",
        ["hid_out_payload_index_to_fsr2"],
    )

    assert "xorwf       route_0_volume_trim_b0, W, BANKED" not in filename
    assert filename.count("bsf         filename_dirty_flags_b0, 3, BANKED") == 1
    _assert_ordered(
        filename,
        "lfsr        FSR0, route_0_volume_trim_shadow_phys",
        "lfsr        FSR1, route_0_volume_trim_phys",
        "movlw       0x04",
        "rcall       compare_fsr0_fsr1_bytes_z",
        "btfsc       STATUS, 2, ACCESS",
        "bra         hid_command_dispatch__check_mute_state_dirty",
        "bsf         event_flags_b0, 3, BANKED",
        "bsf         filename_dirty_flags_b0, 3, BANKED",
    )
    assert "cpfseq      channel_1_source_config_shadow_b0, BANKED" not in body
    assert "lfsr        FSR2, channel_2_source_config_phys" not in body
    _assert_ordered(
        body,
        "movf        setup_profile_setting_b0, W, BANKED",
        "xorwf       setup_profile_shadow_b0, W, BANKED",
        "btfss       STATUS, 2, ACCESS",
        "bsf         dsp_fault_flags_b0, 1, BANKED",
        "lfsr        FSR0, channel_1_source_config_phys",
        "lfsr        FSR1, channel_1_source_config_shadow_phys",
        "movlw       0x06",
        "rcall       compare_fsr0_fsr1_bytes_z",
        "btfss       STATUS, 2, ACCESS",
        "hid_command_dispatch__mark_channel_source_dirty:",
        "bsf         event_flags_b0, 4, BANKED",
    )
    _assert_ordered(
        helper,
        "movwf       diff_count_update_compare_or_route_mask_scratch_byte, ACCESS",
        "ram_pair_diff_z__compare_next_byte:",
        "movf        POSTINC0, W, ACCESS",
        "xorwf       POSTINC1, W, ACCESS",
        "bnz         ram_pair_diff_z__return",
        "decfsz      diff_count_update_compare_or_route_mask_scratch_byte, F, ACCESS",
        "bra         ram_pair_diff_z__compare_next_byte",
        "ram_pair_diff_z__return:",
        "return      0",
    )


def test_v34_wreg_access_stores_use_single_word_movwf_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    movff_wreg = re.findall(r"(?m)^\s*movff\s+WREG,\s+([^;\s]+)", text)

    assert movff_wreg == ["cmd_dispatch_hid_mailbox_enable_phys"]
    for target in [
        "i2c_coeff_2_acc",
        "float_loop_or_tblptr_low_scratch_byte",
        "saved_w_acc",
        "float32_sign_exponent_offset_scratch_acc",
        "float32_exponent_lo_or_target_offset_scratch_acc",
        "addr_low_counter_or_payload_scratch_byte",
        "float_product_or_output_index_scratch_byte",
        "status_addr_high_or_i2c_payload_scratch_byte",
        "fw_update_hex_or_float32_quotient_or_uart_block_scratch",
        "count_flash_page_or_i2c_payload_scratch_byte",
        "addr_high_table_row_or_checksum_scratch_byte",
    ]:
        assert f"movwf       {target}, ACCESS" in text

    for redundant in [
        "movwf       saved_w_acc, ACCESS\n    movff       saved_w_b0_phys, SSPBUF",
        "movwf       float32_sign_exponent_offset_scratch_acc, ACCESS\n    movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS",
        "movwf       float32_exponent_lo_or_target_offset_scratch_acc, ACCESS\n    movf        float32_exponent_lo_or_target_offset_scratch_acc, W, ACCESS",
        "movwf       float_product_or_output_index_scratch_byte, ACCESS\n    movff       float_product_or_output_index_scratch_bank0_phys, flash_addr_shadow_upper_or_preset_job_index_or_init_copy_end_phys",
        "movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS\n    movff       status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys, addr_high_table_row_or_checksum_scratch_phys",
        "movwf       float_loop_or_tblptr_low_scratch_byte, ACCESS\n    movf        float_loop_or_tblptr_low_scratch_byte, W, ACCESS",
        "movwf       uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, ACCESS\n    movf        uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, W, ACCESS",
    ]:
        assert redundant not in text


def test_v34_redundant_local_movlb_zero_assertions_stay_removed() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    assert "usb_sie_endpoint_pump__select_ep0_out_bd:\n    movlb       0x0" not in text
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
        "    bra         poll_src4382_route_monitor__finalize_pending_route"
    ) not in text
    assert "poll_src4382_route_monitor__join_after_monitor_or_timeout:\n    movlb       0x0" not in text


def test_v34_usb_service_endpoint_dispatch_uses_compact_common_tails() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "usb_sie_endpoint_pump", ["float32_to_int32_in_place"])
    nonzero_ep = _label_body(
        text,
        "usb_sie_endpoint_pump__service_ep0_in_token_if_selected",
        ["usb_sie_endpoint_pump__advance_transaction_scan"],
    )

    assert "flow_main_usb_service_2f4e_2f96:" not in body
    assert "flow_main_usb_service_2f4e_300c:" not in body
    assert body.count("movwf       usb_selected_bdt_entry_ptr_hi_b0, BANKED") == 1
    _assert_ordered(
        body,
        "movlw       0x04\n"
        "    movwf       usb_selected_bdt_entry_ptr_hi_b0, BANKED\n"
        "    btfss       USTAT, 1, ACCESS\n"
        "    movlw       0x00\n"
        "usb_sie_endpoint_pump__select_ep0_out_bd:\n"
        "    movwf       usb_selected_bdt_entry_ptr_lo_b0, BANKED",
    )
    _assert_ordered(
        nonzero_ep,
        "movf        USTAT, W, ACCESS",
        "xorlw       0x04",
        "bcf         UIR, 3, ACCESS",
        "bnz         usb_sie_endpoint_pump__advance_transaction_scan",
        "call        usb_ep0_service_in_transaction, 0x0",
    )
    assert nonzero_ep.count("bcf         UIR, 3, ACCESS") == 1


def test_v34_redundant_immediate_fallthrough_branches_stay_removed() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    for redundant in (
        "flow_main_uart_service_1be6_1df0:\n"
        "    movlw       0x05\n"
        "    bra         uart_update_channel_config_cache_from_w_index\n"
        "uart_update_channel_config_cache_from_w_index:",
        "call        usb_ep0_service_in_transaction, 0x0\n"
        "    bra         usb_sie_endpoint_pump__advance_transaction_scan\n"
        "usb_sie_endpoint_pump__advance_transaction_scan:",
        "movwf       length_mask_or_divisor_low_scratch_byte, ACCESS\n"
        "    bra         usb_ep1_in_copy_scratch_buffer_to_bdt\n"
        "\n"
        "usb_ep1_in_copy_scratch_buffer_to_bdt:",
        "lfsr        FSR0, usb_ep1_in_bd_status_phys\n"
        "    bra         usb_endpoint_mark_state_done\n"
        "\n"
        "; Shared USB endpoint completion-marker tail",
        "mssp_hard_reset_smp_master:\n"
        "    movlw       0x80\n"
        "    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS\n"
        "    movlw       0x08\n"
        "    bra         mssp_hard_reset\n"
        "\n"
        "mssp_hard_reset:",
    ):
        assert redundant not in text

    _assert_ordered(
        text,
        "uart_update_channel_config_cache_from_cmd_index:\n"
        "    movf        uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, W, ACCESS\n"
        "uart_update_channel_config_cache_from_w_index:",
        "call        usb_ep0_service_in_transaction, 0x0\n"
        "usb_sie_endpoint_pump__advance_transaction_scan:",
        "movwf       length_mask_or_divisor_low_scratch_byte, ACCESS\n"
        "\n"
        "usb_ep1_in_copy_scratch_buffer_to_bdt:",
        "lfsr        FSR0, usb_ep1_in_bd_status_phys\n"
        "\n"
        "; Shared USB endpoint completion-marker tail",
        "mssp_hard_reset_smp_master:\n"
        "mssp_hard_reset:",
    )


def test_v34_in_range_branch_inversions_stay_collapsed() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    replacements = [
        (
            "bnz         fw_update_init_sequence__run_relay_session\n"
            "    bra         hid_command_dispatch__emit_opcode_status\n"
            "fw_update_init_sequence__run_relay_session:",
            "bz          hid_command_dispatch__emit_opcode_status\n"
            "fw_update_init_sequence__run_relay_session:",
        ),
        (
            "bnz         fw_update_relay__emit_saved_addr_checksum\n"
            "    bra         fw_update_relay__clear_retry_delay_counter\n"
            "fw_update_relay__emit_saved_addr_checksum:",
            "bz          fw_update_relay__clear_retry_delay_counter\n"
            "fw_update_relay__emit_saved_addr_checksum:",
        ),
        (
            "bnz         uart_link_parser__volume_mark_dirty\n"
            "    bra         uart_link_parser__handler_return_tail\n"
            "uart_link_parser__volume_mark_dirty:",
            "bz          uart_link_parser__handler_return_tail\n"
            "uart_link_parser__volume_mark_dirty:",
        ),
        (
            "bz          uart_link_parser__cmd10_emit_cmd29_status\n"
            "    bra         uart_link_parser__handler_return_tail\n"
            "uart_link_parser__cmd10_emit_cmd29_status:",
            "bnz         uart_link_parser__handler_return_tail\n"
            "uart_link_parser__cmd10_emit_cmd29_status:",
        ),
        (
            "bnz         uart_link_parser__dispatch_check_cmd06_input_select\n"
            "    bra         cmd04_status_response\n"
            "uart_link_parser__dispatch_check_cmd06_input_select:",
            "bz          cmd04_status_response\n"
            "uart_link_parser__dispatch_check_cmd06_input_select:",
        ),
        (
            "bnz         uart_link_parser__dispatch_check_cmd07_volume\n"
            "    bra         cmd06_input_select_handler\n"
            "uart_link_parser__dispatch_check_cmd07_volume:",
            "bz          cmd06_input_select_handler\n"
            "uart_link_parser__dispatch_check_cmd07_volume:",
        ),
        (
            "bnz         uart_link_parser__dispatch_check_cmd10_and_extended\n"
            "    bra         volume_cmd_handler\n"
            "uart_link_parser__dispatch_check_cmd10_and_extended:",
            "bz          volume_cmd_handler\n"
            "uart_link_parser__dispatch_check_cmd10_and_extended:",
        ),
        (
            "bnz         stage_hid_ep1_in_report_from_selector__check_selector5\n"
            "    bra         stage_hid_ep1_in_report_from_selector__stage_selector4_opcode04_reply\n"
            "stage_hid_ep1_in_report_from_selector__check_selector5:",
            "bz          stage_hid_ep1_in_report_from_selector__stage_selector4_opcode04_reply\n"
            "stage_hid_ep1_in_report_from_selector__check_selector5:",
        ),
        (
            "bnz         stage_hid_ep1_in_report_from_selector__check_selector6_or_echo_range\n"
            "    bra         stage_hid_ep1_in_report_from_selector__stage_selector5_status_snapshot\n"
            "stage_hid_ep1_in_report_from_selector__check_selector6_or_echo_range:",
            "bz          stage_hid_ep1_in_report_from_selector__stage_selector5_status_snapshot\n"
            "stage_hid_ep1_in_report_from_selector__check_selector6_or_echo_range:",
        ),
        (
            "bnc         truncate_float32_to_integral_float_in_place__convert_through_int32\n"
            "    bra         truncate_float32_to_integral_float_in_place__return\n"
            "truncate_float32_to_integral_float_in_place__convert_through_int32:",
            "bc          truncate_float32_to_integral_float_in_place__return\n"
            "truncate_float32_to_integral_float_in_place__convert_through_int32:",
        ),
    ]
    for old, new in replacements:
        assert old not in text
        assert new in text

    fw_update = _label_body(text, "fw_update_relay__check_minimum_flash_addr", ["fw_update_relay__emit_saved_addr_checksum"])
    assert (
        "bc          fw_update_relay__check_crc_region_limit\n"
        "    bra         fw_update_relay__advance_payload_cursor\n"
        "fw_update_relay__check_crc_region_limit:"
    ) not in fw_update
    assert (
        "bnc         fw_update_relay__check_address_alignment\n"
        "    bra         fw_update_relay__advance_payload_cursor\n"
        "fw_update_relay__check_address_alignment:"
    ) not in fw_update
    _assert_ordered(
        fw_update,
        "bnc         fw_update_relay__advance_cursor_trampoline",
        "fw_update_relay__check_crc_region_limit:",
        "bc          fw_update_relay__advance_cursor_trampoline",
        "fw_update_relay__check_address_alignment:",
        "bra         fw_update_relay__forward_payload_byte",
        "fw_update_relay__advance_cursor_trampoline:",
        "bra         fw_update_relay__advance_payload_cursor",
        "fw_update_relay__check_saved_status_addr:",
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
        "hid_command_dispatch__probe_upload_opcode_range",
        ["hid_command_dispatch__probe_fw_boot_opcode_40"],
    )

    _assert_ordered(
        body,
        "movf        i2c_coeff_2_acc, W, ACCESS",
        "addlw       0xF9",
        "sublw       0x04",
        "bnc         hid_command_dispatch__probe_opcode_0c",
        "bra         hid_command_dispatch__stage_upload_payload",
        "hid_command_dispatch__probe_opcode_0c:",
        "movf        i2c_coeff_2_acc, W, ACCESS",
        "xorlw       0x0C",
        "bnz         hid_command_dispatch__probe_fw_boot_opcode_40",
        "bra         hid_command_dispatch__handle_opcode_0c",
    )
    assert "flow_hid_command_dispatch_157a:" not in text
    assert "flow_hid_command_dispatch_1580:" not in text
    assert "flow_hid_command_dispatch_1586:" not in text
    assert "flow_hid_command_dispatch_158c:" not in text
    assert "flow_hid_command_dispatch_1592:" not in text


def test_v34_uart_terminal_recovery_branches_directly_to_hard_reset() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "uart_tx_timeout", ["timer0_rearm_50ms_heartbeat"])

    assert "v31_hard_reset_jump2:" not in text
    assert "bc          hard_reset" in body
    assert "bra         hard_reset" not in body


def test_v34_local_branch_trampolines_stay_collapsed() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    assert "flow_hid_command_dispatch_15a8b:" not in text
    assert "flow_main_core_service_3188_31f4:" not in text
    assert "flow_main_core_service_3188_31fa:" not in text
    assert "bnz         hid_command_dispatch__unsupported_opcode" in text
    assert text.count("bz          usb_ep0_dispatch_hid_setup_request__return") >= 2


def test_v34_src_nonpcm_read_uses_random_read_zero_flag_directly() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(
        text,
        "poll_src4382_route_monitor__check_scan_index3",
        ["poll_src4382_route_monitor__assert_nonpcm_mute"],
    )

    assert "movwf       src4382_audio_format_latch_b0, BANKED\n    movf        src4382_audio_format_latch_b0, W, BANKED" not in body
    assert "movf        src4382_autodetect_scan_index_b0, W, BANKED\n    xorlw       0x03" not in body
    _assert_ordered(
        body,
        "poll_src4382_route_monitor__check_scan_index3:",
        "xorlw       0x01",
        "bnz         poll_src4382_route_monitor__read_audio_format",
        "movlw       0x04",
        "movwf       pending_route_request_b0, BANKED",
    )
    _assert_ordered(
        body,
        "rcall       i2c_secondary_dev_random_read_call_range_trampoline",
        "bc          poll_src4382_route_monitor__reload_source_monitor_countdown",
        "movlb       0x0",
        "movwf       src4382_audio_format_latch_b0, BANKED",
        "bnz         poll_src4382_route_monitor__assert_nonpcm_mute",
    )


def test_v34_i2c_timeout_final_actions_are_tail_branches() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    assert "preset_job_apply_i2c_recover:" not in text
    expected = {
        "preset_table_apply_entry_legacy__timeout_recover": (
            ["preset_table_apply_entry_legacy__pen_timeout_recover"],
            "goto        i2c_timeout_recover_advertise",
        ),
        "preset_table_apply_entry_legacy__pen_timeout_recover": (
            ["preset_table_apply_entry_core"],
            "goto        i2c_pen_timeout_recover_advertise",
        ),
        "i2c_byte_tx__timeout_recover": (
            ["chain_copy_call_range_trampoline_mid"],
            "goto        i2c_timeout_recover_advertise",
        ),
        "i2c_reg1f_timeout": (
            ["i2c_reg1f_pen_timeout"],
            "bra         i2c_timeout_recover_advertise",
        ),
        "i2c_reg1f_pen_timeout": (
            ["i2c_send_staged_data_byte_and_stop"],
            "bra         i2c_pen_timeout_recover_advertise",
        ),
        "coeff_write_timeout": (
            ["coeff_write_pen_timeout"],
            "bra         i2c_timeout_recover_advertise",
        ),
        "coeff_write_pen_timeout": (
            ["drive_audio_route_select_latches"],
            "bra         i2c_pen_timeout_recover_advertise",
        ),
        "i2c_secondary_timeout": (
            ["i2c_secondary_pen_timeout"],
            "bra         i2c_timeout_recover_advertise",
        ),
        "i2c_secondary_pen_timeout": (
            ["eeprom_write_byte_if_changed"],
            "bra         i2c_pen_timeout_recover_advertise",
        ),
        "preset_job_apply_i2c_timeout": (
            ["preset_select_handler"],
            "bra         i2c_timeout_recover_advertise",
        ),
        "i2c_receive_sspbuf_bounded__timeout": (
            ["fw_update_emit_zero_status_lines"],
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
    stop_helper = _label_body(text, "i2c_send_staged_data_byte_and_stop", ["i2c_byte_tx_zero"])
    _assert_ordered(
        stop_helper,
        "movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS",
        "rcall       i2c_byte_tx",
        "bsf         SSPCON2, 2, ACCESS",
        "bra         wait_pen_bounded",
    )
    assert "rcall       wait_pen_bounded" not in stop_helper
    _assert_ordered(reg1f, "rcall       i2c_send_staged_data_byte_and_stop", "bc          i2c_reg1f_pen_timeout")
    _assert_ordered(secondary, "rcall       i2c_send_staged_data_byte_and_stop", "bc          i2c_secondary_pen_timeout")


def test_v34_newly_reachable_far_helpers_use_rcall_only_where_in_range() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    random_read_pen = _label_body(
        text,
        "i2c_secondary_dev_random_pen_timeout",
        ["adc_remainder_staged_words"],
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
        "hid_command_dispatch__stage_opcode03_status",
        ["hid_command_dispatch__arm_timer0_after_update"],
    )
    filename_subcommand_tail = _label_body(
        text,
        "hid_command_dispatch__check_opcode04_quick_status_modes",
        ["hid_command_dispatch__apply_settings_payload"],
    )
    settings_diff = _label_body(
        text,
        "hid_command_dispatch__check_mute_state_dirty",
        ["hid_command_dispatch__check_channel_setup_dirty"],
    )
    preset_erase = _label_body(
        text,
        "hid_command_dispatch__fill_opcode04_payload_byte_ff",
        ["hid_command_dispatch__advance_opcode04_payload_index"],
    )

    _assert_ordered(
        filename_tail,
        "movf        hid_opcode03_subcommand_b0, W, BANKED",
        "xorlw       0x09",
        "bz          hid_command_dispatch__mark_filename_ram_dirty",
        "xorlw       0x03",
        "bnz         hid_command_dispatch__arm_timer0_after_update",
    )
    assert "movf        hid_opcode03_subcommand_b0, W, BANKED\n    xorlw       0x0A" not in filename_tail
    _assert_ordered(
        filename_subcommand_tail,
        "movf        hid_opcode04_payload_mode_b0, W, BANKED",
        "andlw       0xFD",
        "xorlw       0x05",
        "bz          hid_command_dispatch__delay_before_status_response",
        "bra         hid_command_dispatch__clear_opcode_and_return",
    )
    assert "movf        hid_opcode04_payload_mode_b0, W, BANKED\n    xorlw       0x07" not in filename_subcommand_tail
    assert "xorlw       0x02" not in filename_subcommand_tail
    _assert_ordered(
        settings_diff,
        "clrf        diff_count_update_compare_or_route_mask_scratch_byte, ACCESS",
        "btfsc       active_flags_acc, 4, ACCESS",
        "incf        diff_count_update_compare_or_route_mask_scratch_byte, F, ACCESS",
        "btfsc       active_flags_acc, 5, ACCESS",
        "btg         diff_count_update_compare_or_route_mask_scratch_byte, 0, ACCESS",
        "movf        diff_count_update_compare_or_route_mask_scratch_byte, F, ACCESS",
    )
    _assert_ordered(
        preset_erase,
        "addwf       i2c_coeff_3_acc, W, ACCESS",
        "rcall       setup_fsr2_page1_from_w",
        "setf        INDF2, ACCESS",
    )
    assert "call        setup_fsr2_page1_from_w, 0x0" not in preset_erase


def test_v34_unconditional_call_return_tails_are_direct_branches() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    expected = {
        "wake_input_failed": (
            ["wake_barrier_retry"],
            "goto        send_dsp_fault_status",
            "call        send_dsp_fault_status",
        ),
        "cmd_dispatch_gated__input_route_write_complete": (
            ["cmd_dispatch_gated__apply_unmuted_volume_dirty"],
            "bra         timer0_rearm_50ms_low_window_trampoline",
            "call        timer0_rearm_50ms_heartbeat",
        ),
        "cmd_dispatch_route_sync_if_dirty": (
            ["usb_hid_mailbox_stage_selector5_if_enabled"],
            "bra         timer0_rearm_50ms_low_window_trampoline",
            "call        timer0_rearm_50ms_heartbeat",
        ),
        "cmd_dispatch_gated__check_setup_profile_eeprom_dirty": (
            ["cmd_dispatch_route_sync_if_dirty"],
            "bra         timer0_rearm_50ms_low_window_trampoline",
            "call        timer0_rearm_50ms_heartbeat",
        ),
        "usb_hid_mailbox_stage_selector5_if_enabled": (
            ["setup_fsr2_page1_or_page2_from_w_carry"],
            "goto        usb_hid_mailbox_send_reply_if_ready",
            "call        usb_hid_mailbox_send_reply_if_ready",
        ),
        "preset_replay_selected_table_blocking__apply_final_entry": (
            ["usb_hid_mailbox_send_reply_if_ready"],
            "bra         preset_job_apply_i2c_from_job_cursor",
            "rcall       preset_job_apply_i2c_from_job_cursor",
        ),
        "usb_hid_mailbox_send_reply_if_ready": (
            ["uint8_to_float32_and_save"],
            "bra         usb_ep1_in_send_hid_reply_buffer",
            "rcall       usb_ep1_in_send_hid_reply_buffer",
        ),
        "eeprom_write_byte_if_changed": (
            ["usb_ep1_configure_if_enabled"],
            "bra         eeprom_write_blocking",
            "rcall       eeprom_write_blocking",
        ),
        "usb_ep1_configure_if_enabled": (
            ["timer0_rearm_50ms_heartbeat"],
            "bra         usb_ep1_configure_hid_buffers",
            "rcall       usb_ep1_configure_hid_buffers",
        ),
        "i2c_send_staged_data_byte_and_stop": (
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
        "cmd_dispatch_gated__defer_reapply_until_filename_ready": "cmd_dispatch_gated__check_mute_dirty",
        "poll_src4382_route_monitor__join_after_monitor_or_timeout": "poll_src4382_route_monitor__finalize_pending_route",
        "shift_029_02c_right_w_minus_one": "shift_029_02c_right_w_minus_one__check_remaining",
        "usb_delay_countdown_with_clrwdt": "usb_delay_countdown_with_clrwdt__check_remaining",
        "uart_rx_ring_drain_all": "uart_rx_ring_drain_all__check_more",
        "preset_job_commit_rearm": "preset_job_pending_timer",
        "preset_job_commit_idle": "preset_job_service__clear_state_and_return",
    }
    for alias, target in aliases.items():
        body = _label_body(text, alias, [target])
        assert "bra         " not in body
        assert "goto        " not in body


def test_v34_dead_w_zero_tests_use_tstfsz_skip_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    expected = [
        "tstfsz      input_select_b0, BANKED\n    bsf         event_flags_b0, 3, BANKED",
        "tstfsz      cmd_dispatch_hid_mailbox_enable_b0, BANKED\n    goto        usb_hid_mailbox_send_reply_if_ready",
        "tstfsz      rx_frame_position_b0, BANKED\n    incf        rx_frame_position_b0, F, BANKED",
        "tstfsz      flash_src_low_or_rx_length_scratch_byte, ACCESS\n    return      0",
        "tstfsz      flash_end_high_or_loop_mask_scratch_byte, ACCESS\n    bsf         status_addr_high_or_i2c_payload_scratch_byte, 7, ACCESS",
        "tstfsz      boot_config_marker_valid_b0, BANKED\n    call        flash_write_with_gie_off, 0x0",
        "tstfsz      eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, ACCESS\n    bsf         INTCON, 7, ACCESS",
    ]
    for snippet in expected:
        assert snippet in text

    removed = [
        "movf        input_select_b0, W, BANKED\n    btfss       STATUS, 2, ACCESS",
        "movf        cmd_dispatch_hid_mailbox_enable_b0, W, BANKED\n    btfss       STATUS, 2, ACCESS",
        "movf        rx_frame_position_b0, W, BANKED\n    btfss       STATUS, 2, ACCESS",
        "movf        flash_src_low_or_rx_length_scratch_byte, W, ACCESS\n    btfss       STATUS, 2, ACCESS",
        "movf        flash_end_high_or_loop_mask_scratch_byte, W, ACCESS\n    btfss       STATUS, 2, ACCESS",
        "movf        boot_config_marker_valid_b0, W, BANKED\n    btfss       STATUS, 2, ACCESS",
        "movf        eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, W, ACCESS\n    btfss       STATUS, 2, ACCESS",
    ]
    for snippet in removed:
        assert snippet not in text


def test_v34_math_result_helpers_share_fsr2_rewind_tail() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    first = _label_body(text, "rewind_fsr2_after_four_byte_math_result_store", ["float32_add_staged_operand_to_ram_window_in_place"])
    second = _label_body(text, "float32_add_staged_operand_to_ram_window_in_place", ["intel_hex_checksum_update"])

    _assert_ordered(
        first,
        "decf        FSR2L, F, ACCESS",
        "decf        FSR2L, F, ACCESS",
        "return      0",
    )
    assert first.count("decf        FSR2L, F, ACCESS") == 2
    _assert_ordered(
        second,
        "lfsr        FSR0, math_temp_result_buffer_phys",
        "rcall       copy_four_bytes_fsr0_to_fsr2_rewind2",
        "bra         rewind_fsr2_after_four_byte_math_result_store",
    )
    assert "movff       math_temp_result_byte3_b0_phys, POSTDEC2\n    decf        FSR2L, F, ACCESS" not in second


def test_v34_volume_dsp_path_uses_chain_copy_for_four_byte_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "cmd_dispatch_gated__stage_volume_coefficients", ["cmd_dispatch_gated__volume_write_complete"])

    for old_copy in (
        "movff       flash_saved_tblptrh_phys, fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys",
        "movff       flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys, eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys",
        "movff       adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys, flash_addr_shadow_low_or_preset_table_addr_hi_phys",
        "movff       float32_sign_or_uart_digit_or_flash_read_tblptrh_save_phys, float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys",
        "movff       float32_preset_fw_update_scratch_byte0_b0_phys, i2c_coeff_0_b0_phys",
        "movff       preset_payload_index_or_float32_shadow_byte1_b0_phys, i2c_coeff_1_b0_phys",
        "movff       preset_table_row_len_phys, i2c_coeff_2_b0_phys",
        "movff       float32_transform_shadow_byte3_b0_phys, i2c_coeff_3_b0_phys",
    ):
        assert old_copy not in body

    _assert_ordered(
        body,
        "call        int32_to_float32_and_save, 0x0",
        "rcall       chain_copy_call_range_trampoline_low",
        "db          0x00, 0x00, float32_coeff_or_volume_work_operand_op, float32_i2c_coeff_or_volume_work_operand_op, 0x04, 0xFF",
        "movlw       0x47",
        "call        float32_multiply_primary_by_secondary_in_place, 0x0",
        "call        chain_copy, 0x0",
        "db          0x00, 0x00, float32_i2c_coeff_or_volume_work_operand_op, volume_dsp_coeff_input_shadow_byte0_op, 0x04, volume_dsp_coeff_input_shadow_byte0_op, float32_transform_shadow_dword_op, 0x04, 0xFF, 0xFF",
        "call        float32_exp_limit1024_in_place, 0x0",
        "rcall       chain_copy_call_range_trampoline_low",
        "db          0x00, 0x00, float32_transform_shadow_dword_op, i2c_coeff_0_acc_op, 0x04, 0xFF",
        "call        volume_dsp_write, 0x0",
    )


def test_v34_core_38a2_and_volume_mirror_use_chain_copy_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    core = _label_body(text, "i2c_emit_tas3108_coeff_from_staged_float", ["signed_hi_bias80_compare_prelude"])
    mirror = _label_body(
        text,
        "copy_computed_volume_to_logical_volume",
        ["wait_seed"],
    )

    for old_copy in (
        "movff       float32_preset_fw_update_scratch_byte0_b0_phys, tas3108_coeff_result_byte0_b0_phys",
        "movff       preset_payload_index_or_float32_shadow_byte1_b0_phys, tas3108_coeff_result_byte1_b0_phys",
        "movff       preset_table_row_len_phys, tas3108_coeff_result_byte2_b0_phys",
        "movff       float32_transform_shadow_byte3_b0_phys, tas3108_coeff_result_sign_byte_b0_phys",
        "movff       tas3108_coeff_transform_work_byte0_b0_phys, float32_preset_fw_update_scratch_byte0_b0_phys",
        "movff       tas3108_coeff_transform_work_byte1_b0_phys, preset_payload_index_or_float32_shadow_byte1_b0_phys",
        "movff       fw_update_line_checksum_ok_b0_phys, preset_table_row_len_phys",
        "movff       fw_update_crc_feedback_scratch_b0_phys, float32_transform_shadow_byte3_b0_phys",
        "movff       float32_preset_fw_update_scratch_byte0_b0_phys, tas3108_coeff_transform_work_byte0_b0_phys",
        "movff       preset_payload_index_or_float32_shadow_byte1_b0_phys, tas3108_coeff_transform_work_byte1_b0_phys",
        "movff       preset_table_row_len_phys, fw_update_line_checksum_ok_b0_phys",
        "movff       float32_transform_shadow_byte3_b0_phys, fw_update_crc_feedback_scratch_b0_phys",
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
        "db          0x00, 0x00, tas3108_coeff_transform_work_dword_op, tas3108_coeff_work_accum_dword_op, 0x04, tas3108_coeff_transform_work_dword_op, float32_transform_shadow_dword_op, 0x04, 0xFF, 0xFF",
        "rcall       truncate_float32_to_integral_float_in_place",
        "db          0x00, 0x00, float32_transform_shadow_dword_op, tas3108_coeff_result_dword_op, 0x04, 0xFF",
        "call        float32_add_secondary_to_primary_in_place, 0x0",
        "db          0x00, 0x00, float32_accum_work_byte0_op, tas3108_coeff_work_accum_dword_op, 0x04, 0xFF",
        "db          0x00, 0x00, tas3108_coeff_work_accum_dword_op, tas3108_coeff_secondary_work_dword_op, 0x04, tas3108_coeff_secondary_work_dword_op, float32_transform_shadow_dword_op, 0x04, 0xFF, 0xFF",
        "movlw       0x41",
        "rcall       float32_add_staged_operand_to_ram_window_in_place",
        "db          0x00, 0x00, tas3108_coeff_transform_work_dword_op, float32_transform_shadow_dword_op, 0x04, 0xFF",
        "rcall       truncate_float32_to_integral_float_in_place",
        "db          0x00, 0x00, float32_transform_shadow_dword_op, tas3108_coeff_transform_work_dword_op, 0x04, 0xFF",
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
    body = _label_body(text, "chain_copy", ["copy_transform_shadow_to_math_operand"])

    assert "movf        FSR0H, W, ACCESS" not in body
    assert "movff       chain_copy_srch, FSR0H" not in body
    _assert_ordered(
        body,
        "movf        chain_copy_srch_b3, W, BANKED",
        "xorlw       0xEE",
        "bnz         chain_copy__read_ram_source_byte",
        "movf        chain_copy_srcl_b3, W, BANKED",
        "call        eeprom_read_byte_at_w, 0x0",
        "chain_copy__read_ram_source_byte:",
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
    assert any("route_0_volume_trim_op" in descriptor for descriptor in eeprom_descriptors)


def test_v34_chain_copy_windows_use_local_tos_trampolines() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    low_wrapper = _label_body(text, "chain_copy_call_range_trampoline_low", ["cmd_dispatch_gated"])
    mid_wrapper = _label_body(text, "chain_copy_call_range_trampoline_mid", ["float32_multiply_ram_window_by_staged_operand_in_place"])

    _assert_ordered(low_wrapper, "chain_copy_call_range_trampoline_low:", "goto        chain_copy")
    _assert_ordered(mid_wrapper, "chain_copy_call_range_trampoline_mid:", "goto        chain_copy")

    low_bodies = {
        "hid_command_dispatch__compare_settings_mirrors": (_label_body(text, "hid_command_dispatch__compare_settings_mirrors", ["hid_command_dispatch__mark_volume_dirty_if_changed"]), 1),
        "hid_command_dispatch__snapshot_settings_mirrors": (_label_body(text, "hid_command_dispatch__snapshot_settings_mirrors", ["hid_command_dispatch__stage_status_05"]), 1),
        "cmd_dispatch_gated__stage_volume_coefficients": (_label_body(text, "cmd_dispatch_gated__stage_volume_coefficients", ["cmd_dispatch_gated__volume_write_complete"]), 2),
        "restore_eeprom_settings_on_boot": (_label_body(text, "restore_eeprom_settings_on_boot", ["stage_hid_ep1_in_report_from_selector"]), 4),
    }
    for label, (body, expected) in low_bodies.items():
        assert body.count("rcall       chain_copy_call_range_trampoline_low") == expected, label
        if label == "cmd_dispatch_gated__stage_volume_coefficients":
            assert body.count("call        chain_copy, 0x0") == 1, label
        else:
            assert "call        chain_copy, 0x0" not in body, label

    mid_bodies = {
        "stage_tas3108_coeff_input_scratch": (_label_body(text, "stage_tas3108_coeff_input_scratch", ["i2c_emit_tas3108_coeff_from_staged_float"]), 1),
        "i2c_emit_tas3108_coeff_from_staged_float": (_label_body(text, "i2c_emit_tas3108_coeff_from_staged_float", ["signed_hi_bias80_compare_prelude"]), 11),
        "int32_to_float32_and_save": (_label_body(text, "int32_to_float32_and_save", ["sspcon1_masked_w"]), 1),
        "float32_multiply_ram_window_by_staged_operand_in_place": (_label_body(text, "float32_multiply_ram_window_by_staged_operand_in_place", ["float32_add_staged_operand_to_ram_window_in_place"]), 2),
        "float32_add_staged_operand_to_ram_window_in_place": (_label_body(text, "float32_add_staged_operand_to_ram_window_in_place", ["intel_hex_checksum_update"]), 2),
        "eeprom_write_byte_if_changed": (_label_body(text, "eeprom_write_byte_if_changed", ["usb_ep1_configure_if_enabled"]), 1),
    }
    for label, (body, expected) in mid_bodies.items():
        assert body.count("rcall       chain_copy_call_range_trampoline_mid") == expected, label
        assert "call        chain_copy, 0x0" not in body, label


def test_v34_i2c_service_39a6_uses_chain_copy_for_four_byte_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "i2c_emit_tas3108_coeff_from_staged_float", ["signed_hi_bias80_compare_prelude"])

    assert "movff       fw_update_relay_page_index_bank0_phys, fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys" not in body
    assert "movff       fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys, tas3108_coeff_transform_work_byte0_b0_phys" not in body
    assert "movff       float32_math_operand_byte0_b0_phys, tas3108_coeff_tx_byte3_b0_phys" not in body
    assert "call        chain_copy, 0x0" not in body
    assert body.count("rcall       chain_copy_call_range_trampoline_mid") == 11
    _assert_ordered(
        body,
        "movwf       float32_product_or_uart_base_high_scratch_byte, ACCESS",
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, tas3108_coeff_staged_input_dword_op, float32_i2c_coeff_or_volume_work_operand_op, 0x04, 0xFF",
        "call        float32_multiply_primary_by_secondary_in_place, 0x0",
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, float32_i2c_coeff_or_volume_work_operand_op, tas3108_coeff_transform_work_dword_op, 0x04, 0xFF",
        "db          0x00, 0x00, tas3108_coeff_transform_work_dword_op, tas3108_coeff_work_accum_dword_op, 0x04, tas3108_coeff_transform_work_dword_op, float32_transform_shadow_dword_op, 0x04, 0xFF, 0xFF",
        "rcall       truncate_float32_to_integral_float_in_place",
    )
    _assert_ordered(
        body,
        "call        float32_to_int32_in_place, 0x0",
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, float32_math_operand_byte0_op, tas3108_coeff_tx_byte3_op, 0x04, 0xFF",
        "movf        tas3108_coeff_tx_byte0_acc, W, ACCESS",
    )


def test_v34_filename_reply_state_machine_keeps_compact_branch_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    query = _label_body(text, "cmd26_filename_query_handler", ["filename_read_source_at_w"])
    reader = _label_body(text, "filename_read_source_at_w", ["filename_reply_emit_next_frame_if_ready"])
    arm = _label_body(text, "cmd26_filename_arm", ["cmd26_filename_compare_prefix16"])
    service = _label_body(text, "filename_reply_emit_next_frame_if_ready", ["diag_low_nibble_reply_burst"])

    assert query.count("btfsc       filename_rev_b2, 0, BANKED") == 2
    assert "movf        filename_rev_b2, W, BANKED\n    andlw       0x01\n    bnz         cmd26_filename_query_handler__suppress_ack_and_return" not in query
    _assert_ordered(
        query,
        "movwf       fn_job_src_kind_b2, BANKED",
        "btfsc       active_flags_acc, 2, ACCESS",
        "xorlw       0x01",
        "bz          cmd26_filename_query_handler__select_active_ram_source",
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
        "cmd26_filename_query_handler__scan_printable_length:",
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
        "bz          filename_read_source_at_w__read_active_ram_slot",
    )
    assert "movlw       0x20\n    cpfslt      fn_job_tmp_b2, BANKED" not in query
    _assert_ordered(
        arm,
        "movlw       0x2F",
        "movwf       fn_job_start_cmd_b2, BANKED",
        "movlw       0x10",
        "cpfsgt      fn_job_len_b2, BANKED",
        "bra         cmd26_filename_query_handler__verify_rev_and_arm_job",
    )
    assert "movlw       0x11" not in arm
    _assert_ordered(
        service,
        "decf        fname_tx_gap_hi_b2, F, BANKED",
        "filename_reply_job_service__decrement_gap_low:",
        "decf        fname_tx_gap_lo_b2, F, BANKED",
        "bra         filename_reply_job_service__return",
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
        "shift_028_02b_right_23_clear_c": (
            "float32_secondary_work_byte2_acc",
            "float32_secondary_work_byte1_acc",
            "float32_secondary_work_byte0_acc",
            "float32_math_operand_byte3_acc",
        ),
        "shift_01a_01d_right_23_clear_c": (
            "float32_extract_or_divide_counter_acc",
            "fw_update_checksum_or_float32_quotient_top_scratch",
            "fw_update_hex_or_float32_quotient_or_uart_block_scratch",
            "float32_extract_or_quotient_or_preset_uart_index",
        ),
        "shift_015_018_right_23_clear_c": (
            "float32_product_or_uart_base_scratch_byte",
            "float_product_or_output_index_scratch_byte",
            "float_product_flash_addr_or_preset_index_scratch_byte",
            "float_shift_flash_addr_or_preset_index_scratch_byte",
        ),
    }
    for helper, regs in fixed_helpers.items():
        loop_label = f"{helper}__rotate_next_bit"
        check_label = f"{helper}__check_remaining"
        body = _label_body(text, helper, [loop_label])
        full_body = _label_body(text, helper, ["float32_add_secondary_to_primary_in_place", "float32_multiply_primary_by_secondary_in_place", "float32_divide_primary_by_secondary_in_place"])
        _assert_ordered(
            full_body,
            "movlw       0x18",
            f"bra         {check_label}",
            f"{loop_label}:",
            "bcf         STATUS, 0, ACCESS",
            f"rrcf        {regs[0]}, F, ACCESS",
            f"rrcf        {regs[1]}, F, ACCESS",
            f"rrcf        {regs[2]}, F, ACCESS",
            f"rrcf        {regs[3]}, F, ACCESS",
            f"{check_label}:",
            "decfsz      WREG, F, ACCESS",
            f"bra         {loop_label}",
            "return      0",
        )
        assert "movlw       0x18" in body
        assert text.count(f"rcall       {helper}") == 2

    variable_helper = _label_body(text, "shift_029_02c_right_w_minus_one", ["float32_to_int32_in_place"])
    variable_loop = _label_body(text, "shift_029_02c_right_w_minus_one__rotate_next_bit", ["float32_to_int32_in_place"])
    assert "movlw       0x18" not in variable_helper
    assert "movlw       0x20" not in variable_helper
    assert "bra         shift_029_02c_right_w_minus_one__check_remaining" not in variable_helper
    _assert_ordered(
        variable_loop,
        "shift_029_02c_right_w_minus_one__rotate_next_bit:",
        "bcf         STATUS, 0, ACCESS",
        "rrcf        float32_secondary_work_byte3_acc, F, ACCESS",
        "rrcf        float32_secondary_work_byte2_acc, F, ACCESS",
        "rrcf        float32_secondary_work_byte1_acc, F, ACCESS",
        "rrcf        float32_secondary_work_byte0_acc, F, ACCESS",
        "shift_029_02c_right_w_minus_one:",
        "shift_029_02c_right_w_minus_one__check_remaining:",
        "decfsz      WREG, F, ACCESS",
        "bra         shift_029_02c_right_w_minus_one__rotate_next_bit",
        "return      0",
    )

    caller = _label_body(text, "float32_to_int32_in_place", ["main_core_service_30cc"])
    _assert_ordered(
        caller,
        "movlw       0x18",
        "rcall       shift_029_02c_right_w_minus_one",
        "movf        float32_secondary_work_byte0_acc, W, ACCESS",
        "movlw       0x20",
        "rcall       shift_029_02c_right_w_minus_one",
    )
    assert caller.count("rcall       shift_029_02c_right_w_minus_one") == 2


def test_v34_math_operand_stage_runs_use_near_chain_copy_descriptors() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    bodies = {
        "float32_add_secondary_to_primary_in_place": _label_body(text, "float32_add_secondary_to_primary_in_place", ["twos_complement_024_027_after_low_byte_complement"]),
        "float32_multiply_primary_by_secondary_in_place": _label_body(text, "float32_multiply_primary_by_secondary_in_place", ["add_shifted_multiplicand_to_product_accumulator"]),
        "float32_divide_primary_by_secondary_in_place": _label_body(text, "float32_divide_primary_by_secondary_in_place", ["flash_write_without_preset_remap"]),
    }

    for old_copy in (
        "movff       float32_accum_work_byte0_b0_phys, float32_math_operand_byte3_b0_phys",
        "movff       float32_accum_work_byte1_b0_phys, float32_secondary_work_byte0_b0_phys",
        "movff       float32_accum_work_byte2_b0_phys, float32_secondary_work_byte1_b0_phys",
        "movff       float32_accum_work_byte3_b0_phys, float32_secondary_work_byte2_b0_phys",
        "movff       float32_aux_work_byte0_b0_phys, float32_accum_work_byte0_b0_phys",
        "movff       float32_math_operand_byte0_b0_phys, float32_accum_work_byte1_b0_phys",
        "movff       float32_math_operand_byte1_b0_phys, float32_accum_work_byte2_b0_phys",
        "movff       float32_math_operand_byte2_b0_phys, float32_accum_work_byte3_b0_phys",
        "movff       addr_low_counter_or_payload_scratch_phys, float32_accum_work_byte0_b0_phys",
        "movff       addr_high_table_row_or_checksum_scratch_phys, float32_accum_work_byte1_b0_phys",
        "movff       saved_w_b0_phys, float32_accum_work_byte2_b0_phys",
        "movff       status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys, float32_accum_work_byte3_b0_phys",
    ):
        assert old_copy not in bodies["float32_add_secondary_to_primary_in_place"]
    for old_copy in (
        "movff       fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys, float32_extract_or_quotient_or_preset_uart_index_bank0_phys",
        "movff       eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys",
        "movff       flash_addr_shadow_low_or_preset_table_addr_hi_phys, hex_byte_save_or_uart_status_block_buffer_phys",
        "movff       float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys, fw_update_relay_header_buffer_phys",
        "movff       flash_addr_shadow_upper_or_preset_job_index_or_init_copy_end_phys, float32_extract_or_quotient_or_preset_uart_index_bank0_phys",
        "movff       float_product_or_output_index_scratch_bank0_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys",
        "movff       preset_header_tas_reg_or_uart_block_base_low_scratch_phys, hex_byte_save_or_uart_status_block_buffer_phys",
        "movff       preset_table_header_len_source_phys, fw_update_relay_header_buffer_phys",
    ):
        assert old_copy not in bodies["float32_multiply_primary_by_secondary_in_place"]
    for old_copy in (
        "movff       flash_saved_tblptrh_phys, float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys",
        "movff       flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys, flash_addr_shadow_upper_or_preset_job_index_or_init_copy_end_phys",
        "movff       adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys, float_product_or_output_index_scratch_bank0_phys",
        "movff       float32_sign_or_uart_digit_or_flash_read_tblptrh_save_phys, preset_header_tas_reg_or_uart_block_base_low_scratch_phys",
        "movff       flash_addr_low_or_float32_scale_or_flash_read_tblptru_save_phys, float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys",
        "movff       fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys, flash_addr_shadow_upper_or_preset_job_index_or_init_copy_end_phys",
        "movff       eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys, float_product_or_output_index_scratch_bank0_phys",
        "movff       flash_addr_shadow_low_or_preset_table_addr_hi_phys, preset_header_tas_reg_or_uart_block_base_low_scratch_phys",
    ):
        assert old_copy not in bodies["float32_divide_primary_by_secondary_in_place"]

    _assert_ordered(
        bodies["float32_add_secondary_to_primary_in_place"],
        "db          0x00, 0x00, float32_accum_work_byte0_op, float32_math_operand_byte3_op, 0x04, 0xFF",
        "rcall       shift_028_02b_right_23_clear_c",
        "db          0x00, 0x00, float32_aux_work_byte0_op, float32_accum_work_byte0_op, 0x04, 0xFF",
        "bra         float32_add_secondary_to_primary_in_place__return",
        "db          0x00, 0x00, addr_low_counter_or_payload_scratch_operand, float32_accum_work_byte0_op, 0x04, 0xFF",
        "float32_add_secondary_to_primary_in_place__return:",
    )
    helper_24c2 = _label_body(
        bodies["float32_add_secondary_to_primary_in_place"],
        "float32_add_secondary_to_primary_in_place__decrement_alignment_guard_mod8",
        ["float32_add_secondary_to_primary_in_place__right_shift_primary_to_match_secondary"],
    )
    assert bodies["float32_add_secondary_to_primary_in_place"].count("rcall       float32_add_secondary_to_primary_in_place__decrement_alignment_guard_mod8") == 2
    _assert_ordered(
        helper_24c2,
        "decf        float32_secondary_work_byte3_acc, F, ACCESS",
        "movff       float32_secondary_work_byte3_b0_phys, float32_math_operand_byte3_b0_phys",
        "movlw       0x07",
        "andwf       float32_math_operand_byte3_acc, F, ACCESS",
        "return      0",
    )
    _assert_ordered(
        bodies["float32_multiply_primary_by_secondary_in_place"],
        "db          0x00, 0x00, float32_i2c_coeff_or_volume_work_operand_op, float32_multiply_extract_window_dword_op, 0x04, 0xFF",
        "rcall       shift_01a_01d_right_23_clear_c",
        "db          0x00, 0x00, float32_multiply_secondary_operand_dword_op, float32_multiply_extract_window_dword_op, 0x04, 0xFF",
        "rcall       shift_01a_01d_right_23_clear_c",
    )
    _assert_ordered(
        bodies["float32_divide_primary_by_secondary_in_place"],
        "db          0x00, 0x00, float32_coeff_or_volume_work_operand_op, float32_divide_extract_window_dword_op, 0x04, 0xFF",
        "rcall       shift_015_018_right_23_clear_c",
        "db          0x00, 0x00, float32_divide_divisor_dword_op, float32_divide_extract_window_dword_op, 0x04, 0xFF",
        "rcall       shift_015_018_right_23_clear_c",
    )


def test_v34_core_297e_uses_near_chain_copy_for_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "float32_exp_limit1024_in_place", ["float32_multiply_primary_by_secondary_in_place__shift_multiplier_and_product"])

    for old_copy in (
        "movff       float32_preset_fw_update_scratch_byte0_b0_phys, flash_saved_tblptrh_phys",
        "movff       preset_payload_index_or_float32_shadow_byte1_b0_phys, flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys",
        "movff       preset_table_row_len_phys, adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys",
        "movff       float32_transform_shadow_byte3_b0_phys, float32_sign_or_uart_digit_or_flash_read_tblptrh_save_phys",
        "movff       flash_saved_tblptrh_phys, float32_accum_work_byte0_b0_phys",
        "movff       flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys, float32_accum_work_byte1_b0_phys",
        "movff       adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys, float32_accum_work_byte2_b0_phys",
        "movff       float32_sign_or_uart_digit_or_flash_read_tblptrh_save_phys, float32_accum_work_byte3_b0_phys",
        "movff       float32_accum_work_byte0_b0_phys, float32_preset_fw_update_scratch_byte0_b0_phys",
        "movff       float32_accum_work_byte1_b0_phys, preset_payload_index_or_float32_shadow_byte1_b0_phys",
        "movff       float32_accum_work_byte2_b0_phys, preset_table_row_len_phys",
        "movff       float32_accum_work_byte3_b0_phys, float32_transform_shadow_byte3_b0_phys",
    ):
        assert old_copy not in body

    _assert_ordered(
        body,
        "rcall       chain_copy",
        "db          0x00, 0x00, float32_transform_shadow_dword_op, float32_coeff_or_volume_work_operand_op, 0x04, 0xFF",
        "rcall       float32_divide_primary_by_secondary_in_place",
        "rcall       chain_copy",
        "db          0x00, 0x00, float32_coeff_or_volume_work_operand_op, float32_accum_work_byte0_op, 0x04, 0xFF",
        "rcall       float32_add_secondary_to_primary_in_place",
        "rcall       chain_copy",
        "db          0x00, 0x00, float32_accum_work_byte0_op, float32_transform_shadow_dword_op, 0x04, 0xFF",
        "movlw       0x0A",
    )


def test_v34_core_2abc_final_save_uses_chain_copy_descriptor() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "float32_multiply_primary_by_secondary_in_place", ["add_shifted_multiplicand_to_product_accumulator"])
    volume_caller = _label_body(text, "cmd_dispatch_gated__stage_volume_coefficients", ["cmd_dispatch_gated__volume_write_complete"])
    i2c_caller = _label_body(text, "i2c_emit_tas3108_coeff_from_staged_float", ["signed_hi_bias80_compare_prelude"])
    math_caller = _label_body(text, "float32_multiply_ram_window_by_staged_operand_in_place", ["float32_add_staged_operand_to_ram_window_in_place"])

    for old_copy in (
        "movff       addr_low_counter_or_payload_scratch_phys, fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys",
        "movff       addr_high_table_row_or_checksum_scratch_phys, eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys",
        "movff       saved_w_b0_phys, flash_addr_shadow_low_or_preset_table_addr_hi_phys",
        "movff       status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys, float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys",
    ):
        assert old_copy not in body

    _assert_ordered(
        body,
        "rcall       float32_pack_mantissa_exponent_sign",
        "rcall       chain_copy",
        "db          0x00, 0x00, addr_low_counter_or_payload_scratch_operand, float32_i2c_coeff_or_volume_work_operand_op, 0x04, 0xFF",
        "float32_multiply_primary_by_secondary_in_place__return:",
        "return      0",
    )
    _assert_ordered(
        volume_caller,
        "call        float32_multiply_primary_by_secondary_in_place, 0x0",
        "rcall       chain_copy_call_range_trampoline_low",
    )
    _assert_ordered(
        i2c_caller,
        "call        float32_multiply_primary_by_secondary_in_place, 0x0",
        "rcall       chain_copy_call_range_trampoline_mid",
    )
    _assert_ordered(
        math_caller,
        "call        float32_multiply_primary_by_secondary_in_place, 0x0",
        "rcall       chain_copy_call_range_trampoline_mid",
    )


def test_v34_math_result_helpers_use_chain_copy_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    core_3ec4 = _label_body(text, "float32_multiply_ram_window_by_staged_operand_in_place", ["float32_add_staged_operand_to_ram_window_in_place"])
    core_3f1e = _label_body(text, "float32_add_staged_operand_to_ram_window_in_place", ["intel_hex_checksum_update"])
    caller_39a6 = _label_body(text, "i2c_emit_tas3108_coeff_from_staged_float", ["signed_hi_bias80_compare_prelude"])

    for body, old_copies in (
        (
            core_3ec4,
            (
                "movff       float32_math_operand_byte0_b0_phys, flash_addr_shadow_upper_or_preset_job_index_or_init_copy_end_phys",
                "movff       float32_math_operand_byte1_b0_phys, float_product_or_output_index_scratch_bank0_phys",
                "movff       float32_math_operand_byte2_b0_phys, preset_header_tas_reg_or_uart_block_base_low_scratch_phys",
                "movff       float32_math_operand_byte3_b0_phys, preset_table_header_len_source_phys",
                "movff       fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys, float32_secondary_work_byte0_b0_phys",
                "movff       eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys, float32_secondary_work_byte1_b0_phys",
                "movff       flash_addr_shadow_low_or_preset_table_addr_hi_phys, float32_secondary_work_byte2_b0_phys",
                "movff       float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys, float32_secondary_work_byte3_b0_phys",
            ),
        ),
        (
            core_3f1e,
            (
                "movff       float32_preset_fw_update_scratch_byte0_b0_phys, float32_aux_work_byte0_b0_phys",
                "movff       preset_payload_index_or_float32_shadow_byte1_b0_phys, float32_math_operand_byte0_b0_phys",
                "movff       preset_table_row_len_phys, float32_math_operand_byte1_b0_phys",
                "movff       float32_transform_shadow_byte3_b0_phys, float32_math_operand_byte2_b0_phys",
                "movff       float32_accum_work_byte0_b0_phys, math_temp_result_buffer_phys",
                "movff       float32_accum_work_byte1_b0_phys, math_temp_result_byte1_b0_phys",
                "movff       float32_accum_work_byte2_b0_phys, math_temp_result_byte2_b0_phys",
                "movff       float32_accum_work_byte3_b0_phys, math_temp_result_byte3_b0_phys",
            ),
        ),
    ):
        for old_copy in old_copies:
            assert old_copy not in body

    _assert_ordered(
        core_3ec4,
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, float32_math_operand_byte0_op, float32_multiply_secondary_operand_dword_op, 0x04, 0xFF",
        "call        float32_multiply_primary_by_secondary_in_place, 0x0",
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, float32_i2c_coeff_or_volume_work_operand_op, float32_secondary_work_byte0_op, 0x04, 0xFF",
        "movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS",
    )
    _assert_ordered(
        core_3f1e,
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, float32_transform_shadow_dword_op, float32_aux_work_byte0_op, 0x04, 0xFF",
        "call        float32_add_secondary_to_primary_in_place, 0x0",
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, float32_accum_work_byte0_op, math_temp_result_dword_op, 0x04, 0xFF",
        "movf        float32_exponent_lo_or_target_offset_scratch_acc, W, ACCESS",
    )
    assert "main_core_service_432e:" not in text
    assert "call        main_core_service_432e, 0x0" not in text
    _assert_ordered(
        caller_39a6,
        "call        float32_add_secondary_to_primary_in_place, 0x0",
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, float32_accum_work_byte0_op, tas3108_coeff_work_accum_dword_op, 0x04, 0xFF",
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, tas3108_coeff_work_accum_dword_op, tas3108_coeff_secondary_work_dword_op, 0x04, tas3108_coeff_secondary_work_dword_op, float32_transform_shadow_dword_op, 0x04, 0xFF, 0xFF",
    )


def test_v34_settings_load_reuses_clamp_literal_across_adjacent_source_clamps() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "restore_eeprom_settings_on_boot", ["restore_eeprom_settings_on_boot__mirror_route_trim_shadows"])
    clamp_body = _label_body(text, "restore_eeprom_settings_on_boot__validate_channel1_source", ["restore_eeprom_settings_on_boot__validate_link_address"])
    trim_clamps = _label_body(text, "restore_eeprom_settings_on_boot__read_route_trim_eeprom", ["restore_eeprom_settings_on_boot__mirror_route_trim_shadows"])
    volume_guard = body[
        body.index("movf        computed_volume_3_b0, W, BANKED") :
        body.index("restore_eeprom_settings_on_boot__clamp_volume_minimum:")
    ]

    _assert_ordered(
        volume_guard,
        "xorlw       0x80",
        "addlw       0x80",
        "bnz         restore_eeprom_settings_on_boot__clamp_volume_minimum",
        "subwf       computed_volume_2_b0, W, BANKED",
        "bnz         restore_eeprom_settings_on_boot__clamp_volume_minimum",
        "subwf       computed_volume_1_b0, W, BANKED",
    )
    assert "movlw       0x00" not in volume_guard

    _assert_ordered(
        body,
        "restore_eeprom_settings_on_boot__validate_channel1_source:",
        "movlw       0x03",
        "cpfsgt      channel_1_source_config_b0, BANKED",
        "restore_eeprom_settings_on_boot__validate_channel2_source:",
        "lfsr        FSR2, channel_2_source_config_phys",
        "cpfsgt      INDF2, ACCESS",
        "restore_eeprom_settings_on_boot__validate_channel3_source:",
        "lfsr        FSR2, channel_3_source_config_phys",
        "cpfsgt      INDF2, ACCESS",
        "restore_eeprom_settings_on_boot__validate_channel4_source:",
        "lfsr        FSR2, channel_4_source_config_phys",
        "cpfsgt      INDF2, ACCESS",
        "restore_eeprom_settings_on_boot__validate_channel5_source:",
        "lfsr        FSR2, channel_5_source_config_phys",
        "movlw       0x03",
        "cpfsgt      INDF2, ACCESS",
    )
    assert clamp_body.count("movlw       0x03") == 4
    _assert_ordered(
        trim_clamps,
        "movlw       0x12",
        "cpfsgt      route_0_volume_trim_b0, BANKED",
        "restore_eeprom_settings_on_boot__validate_route5_trim:",
        "cpfsgt      route_5_volume_trim_b0, BANKED",
        "restore_eeprom_settings_on_boot__validate_route6_trim:",
        "cpfsgt      route_6_volume_trim_b0, BANKED",
        "restore_eeprom_settings_on_boot__validate_route7_trim:",
        "cpfsgt      route_7_volume_trim_b0, BANKED",
    )
    assert trim_clamps.count("movlw       0x12") == 1


def test_v34_trim_mirrors_and_core_3398_use_chain_copy_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    trims_load = _label_body(text, "restore_eeprom_settings_on_boot__mirror_route_trim_shadows", ["restore_eeprom_settings_on_boot__read_filter_window"])
    response = _label_body(text, "stage_hid_ep1_in_report_from_selector__stage_selector6_version_setup", ["stage_hid_ep1_in_report_from_selector__stage_selector7_to_12_echo"])
    core_3398 = _label_body(text, "truncate_float32_to_integral_float_in_place", ["usb_ep0_apply_clear_set_feature_request"])

    for body, old_copies in (
        (
            trims_load,
            (
                "movff       route_0_volume_trim_phys, route_0_volume_trim_shadow_phys",
                "movff       route_5_volume_trim_phys, route_5_volume_trim_shadow_phys",
                "movff       route_6_volume_trim_phys, route_6_volume_trim_shadow_phys",
                "movff       route_7_volume_trim_phys, route_7_volume_trim_shadow_phys",
            ),
        ),
        (
            response,
            (
                "movff       route_0_volume_trim_phys, usb_hid_ep1_in_report_payload_byte22_phys",
                "movff       route_5_volume_trim_phys, usb_hid_ep1_in_report_payload_byte23_phys",
                "movff       route_6_volume_trim_phys, usb_hid_ep1_in_report_payload_byte24_phys",
                "movff       route_7_volume_trim_phys, usb_hid_ep1_in_report_payload_byte25_phys",
            ),
        ),
        (
            core_3398,
            (
                "movff       float32_preset_fw_update_scratch_byte0_b0_phys, addr_low_counter_or_payload_scratch_phys",
                "movff       preset_payload_index_or_float32_shadow_byte1_b0_phys, addr_high_table_row_or_checksum_scratch_phys",
                "movff       preset_table_row_len_phys, saved_w_b0_phys",
                "movff       float32_transform_shadow_byte3_b0_phys, status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys",
                "movff       float32_math_operand_byte0_b0_phys, flash_saved_tblptrh_phys",
                "movff       float32_math_operand_byte1_b0_phys, flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys",
                "movff       float32_math_operand_byte2_b0_phys, adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys",
                "movff       float32_math_operand_byte3_b0_phys, float32_sign_or_uart_digit_or_flash_read_tblptrh_save_phys",
            ),
        ),
    ):
        for old_copy in old_copies:
            assert old_copy not in body

    _assert_ordered(
        trims_load,
        "rcall       chain_copy_call_range_trampoline_low",
        "db          0x00, 0x00, route_0_volume_trim_op, route_0_volume_trim_shadow_op, 0x04, 0xFF",
        "movlw       0x50",
    )
    _assert_ordered(
        response,
        "movlw       0x03",
        "movwf       usb_hid_ep1_in_report_byte1_b1, BANKED",
        "movwf       usb_hid_ep1_in_report_byte2_b1, BANKED",
        "movlw       0x04",
        "movwf       usb_hid_ep1_in_report_byte3_b1, BANKED",
        "rcall       chain_copy",
        "db          0x00, 0x01, route_0_volume_trim_op, usb_hid_ep1_in_report_payload_byte22_op, 0x04, 0xFF",
        "bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return",
    )
    assert response.count("movlw       0x03") == 1
    _assert_ordered(
        core_3398,
        "truncate_float32_to_integral_float_in_place:",
        "rcall       chain_copy",
        "db          0x00, 0x00, float32_transform_shadow_dword_op, addr_low_counter_or_payload_scratch_operand, 0x04, 0xFF",
        "movlw       0x37",
        "truncate_float32_to_integral_float_in_place__convert_through_int32:",
        "rcall       copy_transform_shadow_to_math_operand",
        "rcall       float32_to_int32_in_place",
        "rcall       chain_copy",
        "db          0x00, 0x00, float32_math_operand_byte0_op, float32_coeff_or_volume_work_operand_op, 0x04, 0xFF",
        "call        int32_to_float32_and_save, 0x0",
    )


def test_v34_core_3e0a_and_eeprom_writeback_use_chain_copy_stage_runs() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    core_3e0a = _label_body(text, "int32_to_float32_and_save", ["i2c_tas3108_reg1f_write"])
    eeprom_writeback = _label_body(text, "eeprom_write_byte_if_changed", ["usb_ep1_configure_if_enabled"])

    for old_copy in (
        "movff       flash_saved_tblptrh_phys, addr_low_counter_or_payload_scratch_phys",
        "movff       flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys, addr_high_table_row_or_checksum_scratch_phys",
        "movff       adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys, saved_w_b0_phys",
        "movff       float32_sign_or_uart_digit_or_flash_read_tblptrh_save_phys, status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys",
    ):
        assert old_copy not in core_3e0a
    writeback_tail = eeprom_writeback[eeprom_writeback.index("bz          eeprom_write_byte_if_changed__return_unchanged") :]
    for old_copy in (
        "movff       computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys, addr_low_counter_or_payload_scratch_phys",
        "movff       computed_volume_or_i2c_payload_or_float32_scale_or_adc_eeprom_hi_phys, addr_high_table_row_or_checksum_scratch_phys",
        "movff       eeprom_or_filename_data_or_flash_buffer_ptr_low_or_signature_low_phys, saved_w_b0_phys",
    ):
        assert old_copy not in writeback_tail

    _assert_ordered(
        core_3e0a,
        "int32_to_float32_and_save__pack_result:",
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, float32_coeff_or_volume_work_operand_op, addr_low_counter_or_payload_scratch_operand, 0x04, 0xFF",
        "movlw       0x96",
        "goto        float32_pack_mantissa_exponent_sign_and_save",
    )
    _assert_ordered(
        eeprom_writeback,
        "xorwf       flash_src_low_or_rx_length_scratch_byte, W, ACCESS",
        "bz          eeprom_write_byte_if_changed__return_unchanged",
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, eeprom_addr_or_float32_pack_tail_operand_op, addr_low_counter_or_payload_scratch_operand, 0x03, 0xFF",
        "bra         eeprom_write_blocking",
    )


def test_v34_coeff_stage_runs_use_chain_copy_descriptors() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    apply_body = _label_body(text, "i2c_apply_channel_route_sync_burst__compute_source_coefficients", ["i2c_apply_channel_route_sync_burst__write_staged_coefficients"])
    helper = _label_body(text, "stage_tas3108_coeff_input_scratch", ["i2c_emit_tas3108_coeff_from_staged_float"])

    for old_copy in (
        "movff       flash_saved_tblptrh_phys, i2c_coeff_0_b0_phys",
        "movff       flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys, i2c_coeff_1_b0_phys",
        "movff       adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys, i2c_coeff_2_b0_phys",
        "movff       float32_sign_or_uart_digit_or_flash_read_tblptrh_save_phys, i2c_coeff_3_b0_phys",
    ):
        assert old_copy not in apply_body
    for old_copy in (
        "movff       i2c_coeff_0_b0_phys, fw_update_relay_page_index_bank0_phys",
        "movff       i2c_coeff_1_b0_phys, fw_update_relay_current_byte_phys",
        "movff       i2c_coeff_2_b0_phys, fw_update_offset_or_channel_enable_row_base_scratch_bank0_phys",
        "movff       i2c_coeff_3_b0_phys, channel_enable_route_shift_mask_phys",
    ):
        assert old_copy not in helper

    _assert_ordered(
        apply_body,
        "call        uint8_to_float32_and_save, 0x0",
        "rcall       chain_copy",
        "db          0x00, 0x00, float32_coeff_or_volume_work_operand_op, i2c_coeff_0_acc_op, 0x04, 0xFF",
    )
    assert "i2c_apply_channel_route_sync_burst__write_staged_coefficients:" not in apply_body
    _assert_ordered(
        helper,
        "rcall       chain_copy_call_range_trampoline_mid",
        "db          0x00, 0x00, i2c_coeff_0_acc_op, tas3108_coeff_staged_input_dword_op, 0x04, 0xFF",
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
        "movff       preset_job_tbl_lo_b2_phys, eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys",
        "movff       preset_job_tbl_hi_b2_phys, flash_addr_shadow_low_or_preset_table_addr_hi_phys",
        "bra         preset_job_apply_i2c_entry",
    )
    advance = _label_body(
        text,
        "preset_job_advance_cursor_to_next_table_row",
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
        ["preset_job_apply_i2c_entry__return_success", "preset_job_apply_i2c_timeout"],
    )
    _assert_ordered(
        i2c_entry,
        "call        preset_table_apply_entry_core_async, 0x0",
        "bcf         float_divisor_or_preset_flag_scratch_byte, 0, ACCESS",
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
        "bra         preset_job_advance_cursor_to_next_table_row",
    )

    final = _label_body(text, "preset_job_apply_final", ["preset_job_commit"])
    assert "movlw       0x5F" not in final
    assert "call        flash_remap_preset_b_start_address_if_active" not in final
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
        "bsf         float_divisor_or_preset_flag_scratch_byte, 0, ACCESS",
        "rcall       flash_read_without_preset_remap_to_scratch_buffer",
        "movff       preset_header_tas_reg_or_uart_block_base_low_scratch_phys, float32_preset_fw_update_scratch_byte0_b0_phys",
        "movff       preset_table_header_len_source_phys, preset_table_row_len_phys",
        "rcall       preset_table_validate_async_header",
        "bc          preset_table_apply_entry_timeout",
    )
    assert "flash_read_to_scratch_buffer" not in async_core

    legacy_core = _label_body(
        text,
        "preset_table_apply_entry_core",
        ["preset_table_apply_entry_timeout"],
    )
    _assert_ordered(
        legacy_core,
        "rcall       flash_read_to_scratch_buffer",
        "rcall       flash_read_without_preset_remap_to_scratch_buffer",
        "rcall       flash_read_to_scratch_buffer",
        "call        wait_sen_bounded, 0x0",
    )

    validator = _label_body(
        text,
        "preset_table_validate_async_header",
        ["preset_table_apply_entry_core__send_payload_byte_loop"],
    )
    for token in (
        "xorlw       0x01",
        "movlw       0x60",
        "movlw       0xD4",
        "addlw       0xC8",
        "addwf       float_product_flash_addr_or_preset_index_scratch_byte, W, ACCESS",
        "xorlw       0x14",
        "bcf         i2c_flag_or_flash_math_uart_cmd_scratch_byte, 0, ACCESS",
        "bsf         STATUS, 0, ACCESS",
    ):
        assert token in validator

    cancel = _label_body(text, "preset_job_cancel", ["preset_job_service__clear_state_and_return"])
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
        "adc_boot_gate__resume_uart_and_rebroadcast_wake": (
            ["adc_boot_gate__skip_pending_preset_rearm"],
            "call        preset_target_compare_active_bsr2, 0x0",
        ),
        "preset_select_handler": (
            ["preset_select_handler__return_to_parser"],
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

    main_core = _label_body(text, "preset_replay_selected_table_blocking", ["usb_hid_mailbox_send_reply_if_ready"])
    assert "preset_table_apply_entry_legacy_blocking" not in main_core
    _assert_ordered(
        main_core,
        "rcall       preset_job_init_cursor_from_active",
        "rcall       preset_job_apply_i2c_from_job_cursor",
        "bc          preset_replay_selected_table_blocking__return_failure",
        "rcall       preset_job_advance_cursor_to_next_table_row",
    )
    assert "bra         preset_job_apply_i2c_from_job_cursor" in main_core
    assert main_core.count("rcall       preset_job_apply_i2c_from_job_cursor") == 1
    assert main_core.count("rcall       preset_job_advance_cursor_to_next_table_row") == 1

    reconnect = _label_body(
        text,
        "cmd_dispatch_gated__check_reconnect_reapply",
        ["cmd_dispatch_gated__check_mute_dirty"],
    )
    _assert_ordered(
        reconnect,
        "rcall       tas3108_write_zero_volume_coeff_mid_window",
        "rcall       cmd_dispatch_route_sync_if_dirty",
        "bcf         event_flags_b0, 6, BANKED",
        "call        preset_replay_selected_table_blocking",
        "bc          cmd_dispatch_gated__reapply_failed_fault_mute",
    )
    assert "cmd_dispatch_input_route_if_dirty" not in reconnect
    _assert_ordered(
        reconnect,
        "btfss       INTCON, 7, ACCESS",
        "bra         cmd_dispatch_gated__finish_reapply_without_filename_reload",
        "bcf         INTCON, 7, ACCESS",
        "call        preset_load_filename",
        "bsf         INTCON, 7, ACCESS",
    )

    volume_entry = _label_body(
        text,
        "cmd_dispatch_gated",
        ["cmd_dispatch_gated__apply_unmuted_volume_dirty"],
    )
    pre_late = volume_entry[: volume_entry.index("cmd_dispatch_late_bit1_entry:")]
    _assert_ordered(
        pre_late,
        "btfsc       active_flags_acc, 7, ACCESS",
        "bra         cmd_dispatch_gated__check_reconnect_and_volume_dirty",
    )
    assert "cmd_dispatch_input_route_if_dirty" not in pre_late
    assert volume_entry.index("cmd_dispatch_late_bit1_entry:") < volume_entry.index(
        "rcall       cmd_dispatch_input_route_if_dirty"
    )
    flow_entry = _label_body(
        text,
        "cmd_dispatch_gated__check_reconnect_and_volume_dirty",
        ["cmd_dispatch_gated__apply_unmuted_volume_dirty"],
    )
    _assert_ordered(
        flow_entry,
        "btfsc       active_flags_acc, 7, ACCESS",
        "bra         cmd_dispatch_gated__check_reconnect_reapply",
        "btfss       event_flags_b0, 3, BANKED",
    )


def test_v34_channel_route_bit_fanout_uses_addlw_selector_shape() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(
        text,
        "cmd_dispatch_gated__check_channel_enable_dirty",
        ["cmd_dispatch_gated__channel_enable_write_complete"],
    )
    helper_region = _label_body(
        text,
        "usb_hid_mailbox_stage_selector5_if_enabled",
        ["setup_fsr2_page1_or_page2_from_w_carry"],
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
    assert body.count("call        preset_table_apply_entry_legacy_blocking, 0x0") == 1
    _assert_ordered(
        body,
        "movlw       0x5F",
        "movwf       route_base_or_flash_addr_low_scratch_byte, ACCESS",
        "movlw       0x1C",
        "movwf       fw_update_offset_or_channel_enable_row_base_scratch, ACCESS",
        "movff       channel_enable_mask_phys, channel_enable_route_shift_mask_phys",
        "cmd_dispatch_gated__write_next_channel_enable_bit:",
        "rrcf        diff_count_update_compare_or_route_mask_scratch_byte, F, ACCESS",
        "movf        fw_update_offset_or_channel_enable_row_base_scratch, W, ACCESS",
        "btfsc       STATUS, 0, ACCESS",
        "addlw       0xEC",
        "movwf       route_bit_or_tblptr_upper_scratch_byte, ACCESS",
        "call        preset_table_apply_entry_legacy_blocking, 0x0",
        "movlw       0x28",
        "addwf       fw_update_offset_or_channel_enable_row_base_scratch, F, ACCESS",
        "bnc         cmd_dispatch_gated__write_next_channel_enable_bit",
    )


def test_v34_field6_wake_route_sync_precedes_final_reassert() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    wake = _label_body(text, "adc_boot_gate__start_dsp_cold_init", ["flash_remap_preset_b_start_address_if_active"])

    _assert_ordered(
        wake,
        "rcall       tas3108_write_zero_volume_coeff_mid_window",
        "bsf         event_flags_b0, 4, BANKED",
        "bsf         active_flags_acc, 7, ACCESS",
        "call        cmd_dispatch_gated",
        "adc_boot_gate__enable_amp_and_probe_i2c:",
        "rcall       wake_i2c_barrier_attempt",
        "bc          adc_boot_gate__mark_i2c_barrier_pending",
        "bsf         event_flags_b0, 1, BANKED",
        "bsf         event_flags_b0, 3, BANKED",
        "call        cmd_dispatch_gated",
    )
    pre_lifecycle = wake[: wake.index("adc_boot_gate__enable_amp_and_probe_i2c:")]
    assert "call        preset_replay_selected_table_blocking" not in pre_lifecycle
    assert "call        cmd_dispatch_input_route_if_dirty" not in pre_lifecycle
    assert "call        cmd_dispatch_route_sync_if_dirty" not in pre_lifecycle
    assert "event_flags_b0, 1" not in pre_lifecycle

    barrier = wake[
        wake.index("adc_boot_gate__enable_amp_and_probe_i2c:") : wake.index("bsf         event_flags_b0, 1, BANKED")
    ]
    assert "call        cmd_dispatch_gated" not in barrier
    assert "event_flags_b0, 3" not in barrier
    assert "main_runtime_latch_flags_b0, 7" not in barrier
    assert "bsf         main_runtime_latch_flags_b0, 6, BANKED" in wake
    _assert_ordered(
        wake,
        "adc_boot_gate__mark_i2c_barrier_pending:",
        "call        field10_mark_fault_mute, 0x0",
        "bsf         main_runtime_latch_flags_b0, 6, BANKED",
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

    dispatch = _label_body(text, "cmd_dispatch_late_bit1_entry", ["cmd_dispatch_gated__check_reconnect_and_volume_dirty"])
    _assert_ordered(
        dispatch,
        "bcf         main_runtime_latch_flags_b0, 7, BANKED",
        "btfsc       event_flags_b0, 1, BANKED",
        "bsf         main_runtime_latch_flags_b0, 7, BANKED",
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
        ["cmd_dispatch_gated__route_code_1_i2c_pair"],
    )
    helper = _label_body(text, "cmd_dispatch_route_sync_if_dirty", ["usb_hid_mailbox_stage_selector5_if_enabled"])
    normal_tail = _label_body(text, "cmd_dispatch_gated__check_route_sync_dirty", ["cmd_dispatch_gated__check_shared_setup_eeprom_dirty"])

    assert "return      0" in input_helper
    assert "event_flags_b0, 3" in input_helper
    assert "call        cmd_dispatch_gated" not in input_helper
    assert len(re.findall(r"(?m)^\s+rcall\s+i2c_apply_channel_route_sync_burst\b", text)) == 1
    assert "rcall       i2c_apply_channel_route_sync_burst" in helper
    _assert_ordered(
        helper,
        "bsf         filename_dirty_flags_b0, 1, BANKED",
        "rcall       usb_hid_mailbox_stage_selector5_if_enabled",
        "bra         timer0_rearm_50ms_low_window_trampoline",
    )
    assert "call        usb_hid_mailbox_send_reply_if_ready, 0x0" not in helper
    assert "rcall       cmd_dispatch_route_sync_if_dirty" in normal_tail
    assert "i2c_apply_channel_route_sync_burst" not in normal_tail


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
    chain_copy = _label_body(text, "chain_copy", ["copy_transform_shadow_to_math_operand"])
    tos_rewrite = chain_copy[
        chain_copy.index("movf        TBLPTRL, W, ACCESS") :
        chain_copy.index("return      0")
    ]
    helper_masks_tos = "bcf         INTCON, 7, ACCESS" in tos_rewrite
    if helper_masks_tos:
        return

    runtime_post_gie_bodies = {
        "hid_command_dispatch__compare_settings_mirrors": ["hid_command_dispatch__mark_volume_dirty_if_changed"],
        "hid_command_dispatch__snapshot_settings_mirrors": ["hid_command_dispatch__stage_status_05"],
        "restore_eeprom_settings_on_boot": ["stage_hid_ep1_in_report_from_selector"],
        "truncate_float32_to_integral_float_in_place": ["usb_ep0_apply_clear_set_feature_request"],
        "i2c_emit_tas3108_coeff_from_staged_float": ["usb_ep1_out_copy_packet_if_ready"],
    }
    unsafe = [
        label
        for label, next_labels in runtime_post_gie_bodies.items()
        if (
            "call        chain_copy" in _label_body(text, label, next_labels)
            or "rcall       chain_copy_call_range_trampoline_low" in _label_body(text, label, next_labels)
            or "rcall       chain_copy_call_range_trampoline_mid" in _label_body(text, label, next_labels)
        )
    ]
    assert not unsafe, "chain_copy call sites reachable after GIE without TOS mask: " + ", ".join(unsafe)


def test_v34_cold_init_clears_all_upper_bank_runtime_lifecycle_cells() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "boot_cold_init__clear_ram_and_runtime_state", ["diag_rcon_rearm"])
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
    route_body = _label_body(text, "parser_route_phase_handler", ["uart_link_parser__payload_forward_gate"])
    data_body = _label_body(text, "uart_link_parser__payload_forward_gate", ["uart_link_parser__advance_payload_position"])
    for body in (route_body, data_body):
        assert "rcall       uart_link_forward_parser_byte_and_mark_tx" in body
    helper = _label_body(text, "uart_link_forward_parser_byte_and_mark_tx", ["restore_eeprom_settings_on_boot"])
    _assert_ordered(
        helper,
        "call        mark_chain_tx_emitted_bsr0, 0x0",
        "movf        eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS",
        "bra         uart_tx_byte_blocking_call_range_trampoline",
    )


def test_v34_uart_route_b0_b1_compare_uses_cumulative_xor() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "uart_link_parser__read_next_byte", ["uart_link_parser__handle_route_or_status_byte"])

    _assert_ordered(
        body,
        "movf        eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS",
        "xorlw       0xB0",
        "bnz         uart_link_parser__check_b1_address_route",
        "uart_link_parser__check_b1_address_route:",
        "xorlw       0x01",
        "bnz         uart_link_parser__handle_route_or_status_byte",
    )
    assert "movf        eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS\n    xorlw       0xB1" not in body


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
        "filename_emit_frame": ["diag_low_nibble_reply_burst"],
        "diag_low_nibble_reply_burst": ["Volume DSP Write"],
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
