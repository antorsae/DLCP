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
    assert "V3.4_RUNTIME_EEPROM_REV" in text
    assert "movlw       0x04                        ; V3.4 identity minor" in identity
    assert "V3.4_IDENTITY_REV_HI" in identity
    assert "V3.4_IDENTITY_REV_LO" in identity
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
    # MAIN floor lowered 128 -> 96 bytes on 2026-06-11: the FIELD-4A
    # ACK-verified preset table apply and the FIELD-4B volume-family row
    # skip (docs/V34_FIELD_BUGS_20260610.md) spent ~20 bytes of reserve on
    # a safety fix (live audio through a wrong/half-applied DSP image).
    # Floor lowered 96 -> 24 on 2026-06-12 for the SRC/DSP forensic counters
    # (N/L/C/T/M + cmd 0x44 extension) during the live spontaneous-filter
    # incident, then RAISED 24 -> 200 the same day: the size-reclaim
    # S-series (chain_copy S1/S2/S4 + S3 dedup,
    # docs/V34_SIZE_OPTIMIZATION_FINDINGS.md) rebuilt the reserve to
    # 250 bytes (gate measure).  2026-06-13 FIELD-5 override: user explicitly
    # relaxed the MAIN reserve floor to 10 bytes so the safety fix can fit;
    # reclaim candidates remain inventoried in the findings doc.
    _assert_listing_fits_before(v34_lst, 0x4C00, min_margin=10)
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
        "call        i2c_secondary_write_rows, 0x0",
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
        "call        i2c_secondary_dev_write, 0x0",
        "decfsz      stock_008_acc, F, ACCESS",
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


def test_v34_preset_apply_is_transaction_checked_and_physical_source_owned() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

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
        "clrf        preset_job_index_b2, BANKED",
        "clrf        preset_job_tbl_lo_b2, BANKED",
        "movlw       0x56",
        "btfsc       active_flags_acc, 2, ACCESS",
        "movlw       0x4C",
        "movwf       preset_job_tbl_hi_b2, BANKED",
    )

    apply = _label_body(text, "preset_job_apply", ["preset_job_apply_retry"])
    _assert_ordered(
        apply,
        "movf        preset_job_target_b2, W, BANKED",
        "btfsc       active_flags_acc, 2, ACCESS",
        "xorlw       0x01",
        "bnz         preset_job_commit_rearm",
        "movff       preset_job_tbl_lo_b2_phys, stock_013_b0_phys",
        "movff       preset_job_tbl_hi_b2_phys, stock_014_b0_phys",
    )

    final = _label_body(text, "preset_job_apply_final", ["preset_job_commit"])
    assert "movlw       0x5F" not in final
    assert "call        preset_b_remap_start_addr" not in final
    _assert_ordered(
        final,
        "movff       preset_job_tbl_lo_b2_phys, stock_013_b0_phys",
        "movff       preset_job_tbl_hi_b2_phys, stock_014_b0_phys",
        "rcall       preset_job_apply_i2c_entry",
    )

    async_core = _label_body(
        text,
        "preset_table_apply_entry_core_async",
        ["preset_table_stage_header_read"],
    )
    _assert_ordered(
        async_core,
        "bsf         stock_012_acc, 0, ACCESS",
        "call        flash_read_stock_fsr2_0017, 0x0",
        "movff       stock_018_b0_phys, stock_02F_b0_phys",
        "movff       stock_019_b0_phys, stock_031_b0_phys",
        "rcall       preset_table_validate_async_header",
        "bc          preset_table_apply_entry_timeout",
    )
    assert "flash_read_fsr2_0017" not in async_core

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


def test_v34_field6_lifecycle_reassert_uses_validated_writer_and_route_drain() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    main_core = _label_body(text, "main_core_service_4574", ["main_usb_service_45a2"])
    assert "main_i2c_service_381c" not in main_core
    _assert_ordered(
        main_core,
        "clrf        preset_job_index_b2, BANKED",
        "clrf        preset_job_tbl_lo_b2, BANKED",
        "movlw       0x56",
        "btfsc       active_flags_acc, 2, ACCESS",
        "movlw       0x4C",
        "movwf       preset_job_tbl_hi_b2, BANKED",
        "rcall       preset_job_apply_i2c_entry",
        "bc          main_core_service_4574_fail",
    )

    reconnect = _label_body(
        text,
        "flow_cmd_dispatch_gated_1a76",
        ["flow_cmd_dispatch_gated_1a9c"],
    )
    _assert_ordered(
        reconnect,
        "call        clrf_i2c_coeff_0123_and_write",
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


def test_v34_field6_wake_route_sync_precedes_final_reassert() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    wake = _label_body(text, "adc_boot_gate_exit", ["preset_b_remap_start_addr"])

    _assert_ordered(
        wake,
        "call        clrf_i2c_coeff_0123_and_write",
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
        "main_core_service_38a2": ["adaptive_baud_select"],
        "main_i2c_service_39a6": ["main_core_service_3c82"],
        "main_core_service_432e": ["i2c_tas3108_reg1f_write"],
    }
    unsafe = [
        label
        for label, next_labels in runtime_post_gie_bodies.items()
        if "call        chain_copy" in _label_body(text, label, next_labels)
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
        "v34_runtime_bank2_clear_loop:",
        "clrf        POSTINC0, ACCESS",
        "decf        WREG, F, ACCESS",
        "bnz         v34_runtime_bank2_clear_loop",
        "btfss       RCON, 1, ACCESS",
    )
    assert "clrf        preset_job_state_b2, BANKED" not in body


def test_v34_parser_forwarded_bytes_mark_chain_tx_emitted_before_uart_tx() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    route_body = _label_body(text, "parser_route_phase_handler", ["flow_main_uart_service_1be6_1c42"])
    data_body = _label_body(text, "flow_main_uart_service_1be6_1c42", ["flow_main_uart_service_1be6_1c52"])
    for body in (route_body, data_body):
        mark = (
            "bsf         chain_tx_emitted_b2, 0, BANKED"
            if "bsf         chain_tx_emitted_b2, 0, BANKED" in body
            else "call        mark_chain_tx_emitted_bsr0, 0x0"
        )
        _assert_ordered(
            body,
            mark,
            "call        uart_tx_byte_blocking, 0x0",
        )


def test_v34_reply_helpers_participate_in_chain_tx_emitted_contract() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper_body = _label_body(text, "mark_chain_tx_emitted_bsr0", ["send_dsp_fault_status"])
    assert "bsf         chain_tx_emitted_b2, 0, BANKED" in helper_body
    assert "movlb       0x00" in helper_body
    assert "return      0" in helper_body

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
