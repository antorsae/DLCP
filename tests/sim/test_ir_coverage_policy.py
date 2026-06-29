"""Policy checks for IR receiver-vs-dispatcher coverage.

These tests intentionally do not simulate firmware.  They guard the testing
model that keeps broad decoded-event matrices separate from the smaller set of
real RB5 pulse-train regressions.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


def test_decoded_ir_matrix_declares_dispatcher_only_scope() -> None:
    text = _read("tests/sim/test_v171_ir_command_matrix.py")

    assert "inject_decoded_ir_event" in text
    assert "DISPATCH layer" in text
    assert "without re-validating the bit-bang Manchester decoder" in text
    assert "test_v171_ir_rc5_pulse_train.py" in text


def test_real_rb5_suite_names_current_user_visible_receiver_paths() -> None:
    text = _read("tests/sim/test_v171_ir_rc5_pulse_train.py")

    assert "_drive_rc5_pulse_train" in text
    assert "inject_decoded_ir_event" in text
    for test_name in (
        "test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby",
        "test_v173_real_rc5_receiver_dispatches_volume_mute_preset_and_input_shortcuts",
        "test_v173_real_rc5_receiver_dispatches_standby_and_wake_shortcuts",
        "test_v173_real_rc5_receiver_dispatches_hypex_mute_from_diag_pages",
    ):
        assert test_name in text


def test_test_robustness_docs_record_ir_coverage_model() -> None:
    docs = (
        _read("docs/TEST_ROBUSTNESS_SPEC.md")
        + "\n"
        + _read("docs/TEST_ROBUSTNESS_IMPL.md")
    )

    for required in (
        "receiver-layer",
        "dispatcher-layer",
        "RB5",
        "inject_decoded_ir_event",
    ):
        assert required in docs
