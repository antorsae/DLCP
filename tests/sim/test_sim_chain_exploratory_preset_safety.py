"""Exploratory preset/DSP safety oracle tests."""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest

from dlcp_fw.paths import SCRIPTS_DIR, V173_CONTROL_HEX, V34_MAIN_HEX


_explore_spec = importlib.util.spec_from_file_location(
    "sim_chain_exploratory", SCRIPTS_DIR / "sim_chain_exploratory.py"
)
_explore = importlib.util.module_from_spec(_explore_spec)
assert _explore_spec.loader is not None
sys.modules.setdefault("sim_chain_exploratory", _explore)
_explore_spec.loader.exec_module(_explore)

_fmt_spec = importlib.util.spec_from_file_location(
    "sim_exploratory_oracle_format", SCRIPTS_DIR / "sim_exploratory_oracle_format.py"
)
_fmt = importlib.util.module_from_spec(_fmt_spec)
assert _fmt_spec.loader is not None
sys.modules.setdefault("sim_exploratory_oracle_format", _fmt)
_fmt_spec.loader.exec_module(_fmt)


def _unit_state(**overrides):
    image = bytes([0x11] * len(_explore.TAS_BIQUAD_SUBADDRS))
    state = {
        "unit": 0,
        "active_flags": _explore.MAIN_ACTIVE_GATE_MASK,
        "active_preset": 0,
        "preset_job_state": 0,
        "preset_job_index": 0,
        "preset_job_target": 0,
        "preset_job_flags": 0,
        "dsp_fault_flags": 0,
        "tas30_last_write": "00000001",
        "tas30_write_count": 1,
        "dsp_biquad_image": image.hex(),
        "src_regs": {"0x12": 0, "0x13": 1, "0x14": 0},
        "src_stats": {},
        "tas_stats": {},
    }
    state.update(overrides)
    return state


def _sample():
    return {"lcd": ["Volume:-17.0dB A", "Auto Detect     "]}


def _golden():
    return {
        0: {
            0: bytes([0x10] * len(_explore.TAS_BIQUAD_SUBADDRS)),
            1: bytes([0x20] * len(_explore.TAS_BIQUAD_SUBADDRS)),
        }
    }


@pytest.mark.slow
def test_golden_image_learner_returns_distinct_stable_a_b_images_per_pb() -> None:
    golden = _explore.learn_preset_golden_images(V173_CONTROL_HEX, V34_MAIN_HEX)

    assert set(golden) == {0, 1}
    for unit in (0, 1):
        assert set(golden[unit]) == {0, 1}
        assert len(golden[unit][0]) == len(_explore.TAS_BIQUAD_SUBADDRS)
        assert len(golden[unit][1]) == len(_explore.TAS_BIQUAD_SUBADDRS)
        assert golden[unit][0] != golden[unit][1]


def test_golden_coeff_oracle_high_for_live_settled_wrong_image() -> None:
    incident = _explore._golden_coeff_incident(
        _sample(),
        _unit_state(),
        _golden(),
        recent_events=[{"action": "ir", "params": {"cmd": 0x38}}],
    )

    assert incident is not None
    assert incident.severity == "HIGH"
    assert incident.oracle == "audio.golden_coeff.live_wrong_image"
    assert incident.observed["reported_preset"] == "A"
    assert incident.observed["diff_count"] == len(_explore.TAS_BIQUAD_SUBADDRS)
    assert incident.observed["recent_stimuli"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"preset_job_state": 3},
        {"active_flags": _explore.MAIN_ACTIVE_MUTE_MASK | _explore.MAIN_ACTIVE_GATE_MASK},
        {"active_flags": 0},
        {"dsp_fault_flags": _explore.DSP_FAULT_MASK},
        {"dsp_fault_flags": _explore.DSP_ACKSTAT_MASK},
        {"tas30_last_write": "00000000"},
        {"src_regs": {"0x12": 0, "0x13": 0, "0x14": 0}},
        {"src_regs": {"0x12": 1, "0x13": 1, "0x14": 0}},
    ],
)
def test_golden_coeff_oracle_ignores_non_live_or_non_healthy_windows(overrides) -> None:
    incident = _explore._golden_coeff_incident(
        _sample(),
        _unit_state(**overrides),
        _golden(),
    )

    assert incident is None


def _triage_observation(*, golden_match: bool) -> dict:
    def main(unit: int) -> dict:
        return {
            "unit": unit,
            "active_gate": 1,
            "active_preset": 0,
            "preset_job_state": 0,
            "preset_job_target": 0,
            "diag": {},
            "reset": {},
            "filename_ram": "",
            "tas_stats": {},
            "src_stats": {},
            "mute_latch": 4,
            "event_flags": 0,
            "dsp_fault_flags": 0,
            "logical_volume": 0xEF,
            "computed_volume": 0xEF,
            "input_select": 0,
            "input_mirror": 0,
            "tas30_last_write": "00000001",
            "tas30_write_count": 1,
            "tas30_writes_since": [],
            "tas30_nonzero_since": False,
            "dsp_biquad_digest": "bad" if unit == 0 else "ok",
            "dsp_full_digest": "full",
            "golden_coeff_live_checked": True,
            "golden_coeff_match": golden_match if unit == 0 else True,
            "golden_coeff_digest": "gold",
        }

    return {
        "session_id": 1,
        "tick": 1,
        "lcd": ["Volume:-17.0dB A", "Auto Detect     "],
        "is_connected": True,
        "is_waiting": False,
        "control": {
            "flags": 0x02,
            "display_state": 0,
            "volume": 0xEF,
            "input": 0,
            "diag_present": 0,
            "diag_pb1": [],
            "diag_pb2": [],
            "fname": {
                "flags": 0,
                "len": 0,
                "expected_len": 0,
                "id": 0,
                "cache": "",
            },
        },
        "main": [main(0), main(1)],
    }


def test_src_rxckr_churn_is_realistic_when_live_wrong_coeff_is_present() -> None:
    events = [
        {"session_id": 1, "event_id": 1, "action": "init", "params": {"campaign": "preset-phase-sweep", "seed": 1}},
        {"session_id": 1, "event_id": 2, "action": "run_until_connected", "params": {}, "result": {"connected": True}},
        {"session_id": 1, "event_id": 3, "action": "src_rxckr_hole", "params": {"units": [0, 1]}, "result": {"tick": 1}},
    ]
    rows = _fmt._triage_session(
        Path("."),
        1,
        events=events,
        observations=[_triage_observation(golden_match=False)],
    )

    assert rows["signals"]["live_wrong_coeff_obs"] == 1
    assert rows["signals"]["final_live_wrong_coeff"] is True
    assert rows["synthetic_fault_load"] == 0
    assert rows["realistic_score"] >= 100


def test_preset_phase_sweep_plan_is_deterministic_and_logs_phase_delay() -> None:
    plan_a = _explore.build_preset_phase_sweep_plan(random.Random(1234), cycles=3, sample_count=2)
    plan_b = _explore.build_preset_phase_sweep_plan(random.Random(1234), cycles=3, sample_count=2)

    assert plan_a == plan_b
    assert any(
        action == "step" and params.get("purpose") == "phase_delay_before_second"
        for action, params in plan_a
    )
    assert any(action == "phase_sample_window" and params["samples"] == 2 for action, params in plan_a)
    assert any(params.get("purpose") == "phase_origin_primer" for _, params in plan_a)
    setup_actions = [
        params
        for _, params in plan_a
        if str(params.get("purpose", "")).startswith("phase_origin")
        or params.get("purpose") == "phase_target"
    ]
    assert setup_actions
    assert all(params.get("observe") is False for params in setup_actions)
