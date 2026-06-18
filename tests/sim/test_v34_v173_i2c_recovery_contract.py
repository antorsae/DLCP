"""V3.4 MAIN I2C recovery contract tests."""

from __future__ import annotations

import re

from dlcp_fw.paths import V34_MAIN_ASM


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


def test_v34_main_i2c_service_2100_classifies_sen_and_pen_timeouts() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "i2c_apply_channel_route_sync_burst__start_next_dsp_transaction", ["i2c_apply_channel_route_sync_burst__timeout"])

    sen_match = re.search(
        r"bsf\s+SSPCON2,\s+0,\s+ACCESS\s*\n"
        r"\s*call\s+wait_sen_bounded,\s+0x0\s*\n"
        r"\s*bc\s+i2c_apply_channel_route_sync_burst__timeout\b",
        body,
    )
    assert sen_match is not None, "SEN/START timeout must use generic recovery"

    pen_match = re.search(
        r"bsf\s+SSPCON2,\s+2,\s+ACCESS\s*\n"
        r"\s*call\s+wait_pen_bounded,\s+0x0\s*\n"
        r"\s*bc\s+i2c_apply_channel_route_sync_burst__pen_timeout\b",
        body,
    )
    assert pen_match is not None, "PEN/STOP timeout must use PEN-specific recovery"


def test_v34_shared_i2c_start_helper_preserves_carry_timeout_contract() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "i2c_start_after_idle_bounded", ["i2c_secondary_dev_random_read"])
    _assert_ordered(
        helper,
        "rcall       i2c_wait_bus_idle",
        "bsf         SSPCON2, 0, ACCESS",
        "bra         wait_sen_bounded",
    )

    expected = {
        "i2c_secondary_dev_random_read": (
            ["i2c_secondary_dev_random_timeout"],
            "bc          i2c_secondary_dev_random_timeout",
        ),
        "i2c_tas3108_reg1f_write": (["i2c_tas3108_reg1f_write__return_success"], "bc          i2c_reg1f_timeout"),
        "i2c_tas3108_coeff_write": (["i2c_tas3108_coeff_write__return_success"], "bc          coeff_write_timeout"),
    }
    for label, (next_labels, carry_branch) in expected.items():
        body = _label_body(text, label, next_labels)
        _assert_ordered(
            body,
            "rcall       i2c_start_after_idle_bounded",
            carry_branch,
        )


def test_v34_i2c_timeout_recovery_sets_visible_diag_and_carry_contract() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "i2c_timeout_recover_advertise", ["cmd21_diag_query_handler"])
    for needle in (
        "diag_inc_sat diag_i",
        "diag_inc_sat diag_r",
        "bsf         i2c_recover_flags_b2, 0, BANKED",
        "bsf         dsp_fault_flags_b0, 2, BANKED",
        "rcall       send_dsp_fault_status",
        "bsf         STATUS, 0, ACCESS",
        "return      0",
    ):
        assert needle in body


def test_v34_i2c_wait_bus_idle_timeout_returns_error_after_recovery() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "i2c_wait_bus_idle", ["boot_cold_init__run_peripheral_init"])
    assert "rcall       i2c_timeout_recover_advertise" in body
    assert re.search(
        r"rcall\s+i2c_timeout_recover_advertise\s*\n\s*retlw\s+0x1F",
        body,
    ), "idle wait must return with recovery helper's C=1 error contract"


def test_v34_async_apply_timeout_retries_same_entry_after_visible_recovery() -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    apply_body = _label_body(text, "preset_job_apply", ["preset_job_apply_retry"])
    retry_body = _label_body(text, "preset_job_apply_retry", ["preset_job_commit"])
    timeout_body = _label_body(text, "preset_job_apply_i2c_timeout", ["preset_select_handler"])
    helper_body = _label_body(text, "i2c_timeout_recover_advertise", ["cmd21_diag_query_handler"])

    assert "bc          preset_job_apply_retry" in apply_body
    assert "bc          preset_job_apply_retry" in retry_body
    assert "preset_job_apply_i2c_recover:" not in text
    assert "bra         i2c_timeout_recover_advertise" in timeout_body
    assert "bsf         STATUS, 0, ACCESS" in helper_body
    assert "incf        preset_job_index_b2" not in retry_body
