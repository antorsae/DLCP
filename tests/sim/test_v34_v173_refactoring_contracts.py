"""V3.4/V1.73 refactoring-release source contracts."""

from __future__ import annotations

import re

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
    # 252 bytes.  The 200 floor pins the user-mandated working reserve —
    # do not lower it casually; reclaim candidates are inventoried in the
    # findings doc.
    _assert_listing_fits_before(v34_lst, 0x4C00, min_margin=200)
    _assert_listing_fits_before(v173_lst, 0x77B0, min_margin=128)


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
        _assert_ordered(
            body,
            "bsf         chain_tx_emitted_b2, 0, BANKED",
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
