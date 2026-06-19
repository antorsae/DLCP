"""Focused regressions for the V3.4/V1.73 exploratory bugs.

Authored red-first as strict xfails against the unfixed sources (see
``docs/V34_V173_EXPLORATORY_BUGS.md``); now they pin the fixed contracts from
``docs/IMPL_V34_V173_EXPLORATORY_BUGS.md`` and must stay green.

BUG-5's structural test pins the amended contract (record target independent
of the USB-filename gate; deferral lives in the preset job machinery and stays
muted while filename RAM is protected), per the ledger's "before (or
independent of)" expected behavior.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V173_CONTROL_ASM, V34_MAIN_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17
from dlcp_fw.sim.v30_symbols import assemble_v30
from tests.sim.test_v34_mute_refresh_bug import (
    COMMAND_SETTLE_TICKS,
    INPUT_REFRESH_SETTLE_TICKS,
    LOGICAL_VOLUME,
    _assert_user_muted_with_zero_volume_coeff,
    _boot_v34_main,
    _inject_frame,
    _mute_main,
)

ACTIVE_FLAGS = 0x05E
ACTIVE_PRESET_B_MASK = 0x04
ACTIVE_MUTE_MASK = 0x10
FILENAME_DIRTY_FLAGS = 0x0BD
USB_FILENAME_GATE_MASK = 0x40
PRESET_JOB_STATE = 0x2DE
PRESET_JOB_TARGET = 0x2DF
PRESET_JOB_STATE_PENDING = 0x01
PRESET_JOB_STATE_HOLDING = 0x02


def _label_body(text: str, label: str, next_labels: list[str] | tuple[str, ...]) -> str:
    # Labels may carry a trailing "; address: 0x..." comment, so match the
    # label at column 0 and allow anything after the colon.
    start = re.search(rf"(?m)^{re.escape(label)}:[^\n]*$", text)
    if not start:
        raise AssertionError(f"label not found: {label}")
    end_positions: list[int] = []
    for next_label in next_labels:
        match = re.search(rf"(?m)^{re.escape(next_label)}:[^\n]*$", text[start.end() :])
        if match:
            end_positions.append(start.end() + match.start())
    end = min(end_positions) if end_positions else len(text)
    return text[start.start() : end]


@pytest.fixture(scope="module")
def v34_bug_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v34_v173_exploratory_bugs")
    hex_out = tmp / "DLCP_Firmware_V3.4_exploratory_bug_regressions.hex"
    lst_out = tmp / "DLCP_Firmware_V3.4_exploratory_bug_regressions.lst"
    assemble_v30(V34_MAIN_ASM, hex_out, output_lst=lst_out)
    return hex_out


@pytest.fixture(scope="module")
def v173_bug_asm(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v173_exploratory_bug_regressions")
    shutil.copy(V17_CONTROL_RAM_INC, tmp / V17_CONTROL_RAM_INC.name)
    control_asm = tmp / V173_CONTROL_ASM.name
    control_asm.write_bytes(V173_CONTROL_ASM.read_bytes())
    control_hex = tmp / "DLCP_Control_V1.73_exploratory_bug_regressions.hex"
    assemble_v17(control_asm, control_hex)
    return control_asm


def test_bug_v34v173_1_changed_volume_frame_must_not_clear_user_mute(
    v34_bug_hex: Path,
) -> None:
    chain = _boot_v34_main(v34_bug_hex)
    _mute_main(chain)

    current = (chain.read_main_reg(0, LOGICAL_VOLUME) + 0x60) & 0xFF
    changed = (current + 4) & 0x7F
    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x07, changed)
    chain.step_ticks(COMMAND_SETTLE_TICKS)

    _assert_user_muted_with_zero_volume_coeff(chain)


def test_bug_v34v173_2_waiting_loops_must_service_ir_and_fresh_status(
    v173_bug_asm: Path,
) -> None:
    text = v173_bug_asm.read_text(encoding="utf-8", errors="replace")
    cold_wait = _label_body(text, "boot_waiting_for_dlcp_loop", ["post_connect_init"])
    reconnect_wait = _label_body(text, "v171_reconnect_wait_body", ["v171_reconnect_wait_done"])

    ir_service_call = re.compile(
        r"\bcall\s+(?:display_loop_iteration|ir_dispatch_configured_or_fixed_shortcuts|v173_waiting_ir_service)\b"
    )
    for name, body in {
        "cold WAITING": cold_wait,
        "reconnect WAITING": reconnect_wait,
    }.items():
        assert ir_service_call.search(body), f"{name} does not dispatch/re-arm IR"

    assert "v173_reconnect_fresh_status_mask" in text
    assert "raw_status_cache_b0" not in reconnect_wait


def test_bug_v34v173_3_lcd_lifecycle_must_invalidate_preset_row0_before_waiting(
    v173_bug_asm: Path,
) -> None:
    text = v173_bug_asm.read_text(encoding="utf-8", errors="replace")
    cold_wait_entry = _label_body(text, "boot_waiting_for_dlcp_loop", ["post_connect_init"])
    standby_wait_entry = _label_body(
        text,
        "display_state_entry__enter_standby_waiting",
        ["display_state_entry__standby_wait_loop"],
    )
    reconnect_wait_entry = _label_body(text, "reconnect_wait_loop", ["v171_reconnect_wait_body"])

    invalidation = re.compile(r"(FNAME_ROW0_NOT_READY|fname_reset_blank|v173_preset_lcd_invalidate)")
    for name, body in {
        "cold WAITING entry": cold_wait_entry,
        "standby/WAITING entry": standby_wait_entry,
        "reconnect WAITING entry": reconnect_wait_entry,
    }.items():
        assert invalidation.search(body), f"{name} leaves Preset LCD row0 marked ready"


def test_bug_v34v173_4_filename_abort_or_timeout_must_schedule_bounded_retry(
    v173_bug_asm: Path,
) -> None:
    text = v173_bug_asm.read_text(encoding="utf-8", errors="replace")
    abort = _label_body(text, "fname_abort", ["fname_disarm"])
    deadline_expire = _label_body(text, "v172_fname_deadline_expire", ["v172_fname_query_delay_service"])

    retry_tokens = ("FNAME_QUERY_WAIT", "FNAME_WANT_QUERY", "fname_reset_blank_maybe_retry")
    for name, body in {
        "parser abort": abort,
        "pending deadline expiry": deadline_expire,
    }.items():
        assert any(token in body for token in retry_tokens), (
            f"{name} can leave invalid filename state with no recovery query"
        )


def test_bug_v34v173_5_preset_select_must_record_target_independent_of_usb_gate() -> None:
    """Pin the BUG-5 contract at its real layers.

    The parser must always record the broadcast target (no drop gate); the
    deferral while a USB cmd 0x03 filename WRITE is in flight belongs to the
    preset job machinery: PENDING skips filename persistence but force-mutes,
    and the HOLDING bit6
    backstop before ``preset_load_filename`` (the actual hazard) must stay.
    """
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    handler = _label_body(text, "preset_select_handler", ["preset_select_handler__return_to_parser"])
    assert re.search(r"movwf\s+preset_job_target_b2", handler), (
        "preset_job_target store not found in preset_select_handler"
    )
    assert not re.search(r"btfsc\s+filename_dirty_flags_b0,\s*6", handler), (
        "parser-entry gate reintroduced: a preset broadcast arriving during a "
        "USB filename write would be dropped (not deferred) again"
    )
    pending = _label_body(text, "preset_job_pending", ["preset_job_pending_no_mute"])
    assert re.search(
        r"btfsc\s+filename_dirty_flags_b0,\s*6,\s*BANKED[^\n]*\n"
        r"\s*bra\s+preset_job_pending_force_mute",
        pending,
    ), (
        "PENDING must skip filename persistence but still force-mute while "
        "a USB filename write is open"
    )
    holding = _label_body(text, "preset_job_holding", ["preset_job_holding_wait"])
    assert re.search(r"btfsc\s+filename_dirty_flags_b0,\s*6", holding), (
        "HOLDING bit6 backstop before preset_load_filename must stay"
    )


def test_bug_v34v173_5_preset_broadcast_defers_until_usb_gate_clears(
    v34_bug_hex: Path,
) -> None:
    """Behavioral proof: a preset broadcast landing mid-USB-filename-write is
    recorded and parked, then applied as soon as the gate clears.

    Previously the broadcast was silently dropped (target not stored) and the
    unit only re-converged via the ~6 s CONTROL full-sync re-broadcast.
    """
    chain = _boot_v34_main(v34_bug_hex)
    assert not (chain.read_main_reg(0, ACTIVE_FLAGS) & ACTIVE_PRESET_B_MASK), (
        "expected to boot on preset A"
    )

    flags = chain.read_main_reg(0, FILENAME_DIRTY_FLAGS)
    chain.write_main_reg(0, FILENAME_DIRTY_FLAGS, flags | USB_FILENAME_GATE_MASK)
    _inject_frame(chain, 0x20, 0x01)
    chain.step_ticks(COMMAND_SETTLE_TICKS)

    assert chain.read_main_reg(0, PRESET_JOB_TARGET) == 0x01, (
        "broadcast target was not recorded while the USB filename gate is set"
    )
    assert chain.read_main_reg(0, PRESET_JOB_STATE) == PRESET_JOB_STATE_HOLDING, (
        "job must advance to HOLDING, muted, while the USB filename gate is set"
    )
    active = chain.read_main_reg(0, ACTIVE_FLAGS)
    assert not (active & ACTIVE_PRESET_B_MASK), "preset must not switch while parked"
    assert active & ACTIVE_MUTE_MASK, (
        "deferred preset switch must force-mute instead of playing the old preset"
    )

    flags = chain.read_main_reg(0, FILENAME_DIRTY_FLAGS)
    chain.write_main_reg(0, FILENAME_DIRTY_FLAGS, flags & ~USB_FILENAME_GATE_MASK)
    chain.step_ticks(COMMAND_SETTLE_TICKS)

    assert chain.read_main_reg(0, ACTIVE_FLAGS) & ACTIVE_PRESET_B_MASK, (
        "deferred preset target was not applied after the gate cleared"
    )
    # The APPLY/COMMIT table walk takes ~10 s of sim time against the
    # un-baked from-source preset region; poll until the job goes idle.
    for _ in range(5):
        if chain.read_main_reg(0, PRESET_JOB_STATE) == 0:
            break
        chain.step_ticks(INPUT_REFRESH_SETTLE_TICKS)
    assert chain.read_main_reg(0, PRESET_JOB_STATE) == 0
    assert chain.read_main_reg(0, ACTIVE_FLAGS) & ACTIVE_PRESET_B_MASK
