from __future__ import annotations

import dataclasses
import json
from types import SimpleNamespace

import pytest

from dlcp_fw.cli import hardware_lcd_probe as lcd
from dlcp_fw.cli import hardware_state_test as hw
from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo
from dlcp_fw.flash.dlcp_main_flash import DeviceSnapshot, RouteEntry, VersionInfo


def _snapshot(*labels: str) -> DeviceSnapshot:
    return DeviceSnapshot(
        mode="app",
        product_string="DLCP",
        manufacturer_string="Hypex BV",
        serial_number="SER",
        version=VersionInfo(flag=0x03, major=0x03, minor=0x01),
        active_config_name="Cfg",
        active_config_raw=b"Cfg",
        active_routes=tuple(
            RouteEntry(channel=index + 1, value=0 if label == "L" else 1, label=label)
            for index, label in enumerate(labels)
        ),
        warnings=(),
    )


def test_classify_role_from_snapshot_detects_left_right_and_mixed() -> None:
    assert hw._classify_role_from_snapshot(_snapshot("L", "L", "L")) == "LEFT"
    assert hw._classify_role_from_snapshot(_snapshot("R", "R", "R")) == "RIGHT"
    assert hw._classify_role_from_snapshot(_snapshot("L", "R", "L")) == "MIXED"


def test_render_ir_command_expands_action_tokens() -> None:
    cmd = hw._render_ir_command(
        "python3 send_ir.py --key {action} --lower {action_lower} --upper {action_upper}",
        action="F2",
    )
    assert cmd == [
        "python3",
        "send_ir.py",
        "--key",
        "F2",
        "--lower",
        "f2",
        "--upper",
        "F2",
    ]


def test_parse_preset_sequence_requires_f1_f2_actions() -> None:
    assert hw._parse_preset_sequence("F1, f2 ,F1") == ["F1", "F2", "F1"]

    with pytest.raises(RuntimeError, match="preset sequence must contain at least one"):
        hw._parse_preset_sequence(" , ")

    with pytest.raises(RuntimeError, match="expected preset action F1 or F2"):
        hw._parse_preset_sequence("F1,MUTE")


def test_parse_delays_ms_parses_numeric_csv() -> None:
    assert hw._parse_delays_ms("50, 100,250") == [50.0, 100.0, 250.0]

    with pytest.raises(RuntimeError, match="delay list must contain at least one"):
        hw._parse_delays_ms(" , ")

    with pytest.raises(RuntimeError, match="invalid delay value"):
        hw._parse_delays_ms("100,banana")


def test_identify_mains_requires_exact_left_right(monkeypatch) -> None:
    left = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="A",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="00",
    )
    right = hw.MainRoleState(
        path="right-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="RIGHT",
        active_preset="A",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="01",
    )
    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: [left, right])

    rc = hw.main(["identify-mains", "--require-left-right"])

    assert rc == 0


def test_identify_mains_fails_when_two_roles_are_not_unique(monkeypatch) -> None:
    left = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="A",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="00",
    )
    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: [left])

    with pytest.raises(RuntimeError, match="expected exactly 2 visible MAIN HID devices"):
        hw.main(["identify-mains", "--require-left-right"])


def test_ir_preset_roundtrip_passes_with_expected_lcd_and_memory(monkeypatch, tmp_path) -> None:
    left_before = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="A",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="00",
    )
    right_before = hw.MainRoleState(
        path="right-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="RIGHT",
        active_preset="A",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="01",
    )
    left_after = dataclasses.replace(left_before, active_preset="B")
    right_after = dataclasses.replace(right_before, active_preset="B")

    states = iter([[left_before, right_before], [left_after, right_after]])
    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: next(states))
    monkeypatch.setattr(
        hw,
        "_probe_lcd",
        lambda **kwargs: {"consensus": {"line1": "Volume", "line2": "Active: B"}},
    )
    monkeypatch.setattr(
        hw,
        "_send_ir",
        lambda template, action: {"command": ["fake-ir", action], "returncode": 0},
    )
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    rc = hw.main(
        [
            "--output-root",
            str(tmp_path),
            "ir-preset-roundtrip",
            "--action",
            "F2",
            "--expected-preset",
            "B",
            "--ir-command-template",
            "fake_ir {action}",
        ]
    )

    assert rc == 0
    result_files = list((tmp_path / "ir_preset_roundtrip").rglob("result.json"))
    assert len(result_files) == 1
    payload = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert payload["after"]["left"]["active_preset"] == "B"
    assert payload["after"]["right"]["active_preset"] == "B"


def test_ir_preset_roundtrip_defaults_to_builtin_flipper_sender(monkeypatch, tmp_path) -> None:
    left_before = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="A",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="00",
    )
    right_before = dataclasses.replace(
        left_before,
        path="right-path",
        role="RIGHT",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="01",
    )
    left_after = dataclasses.replace(left_before, active_preset="B")
    right_after = dataclasses.replace(right_before, active_preset="B")

    states = iter([[left_before, right_before], [left_after, right_after]])
    seen_templates: list[str] = []
    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: next(states))
    monkeypatch.setattr(
        hw,
        "_probe_lcd",
        lambda **kwargs: {"consensus": {"line1": "Volume", "line2": "Active: B"}},
    )
    monkeypatch.setattr(
        hw,
        "_send_ir",
        lambda template, action: (
            seen_templates.append(template)
            or {"command": ["builtin-flipper", action], "returncode": 0}
        ),
    )
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    rc = hw.main(
        [
            "--output-root",
            str(tmp_path),
            "ir-preset-roundtrip",
            "--action",
            "F2",
            "--expected-preset",
            "B",
        ]
    )

    assert rc == 0
    assert len(seen_templates) == 1
    assert "hardware_flipper_ir.py" in seen_templates[0]
    assert "{action}" in seen_templates[0]


def test_wait_for_main_pair_preset_tracks_left_right_and_both_times(monkeypatch) -> None:
    left_a = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="A",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="00",
    )
    right_a = dataclasses.replace(
        left_a,
        path="right-path",
        role="RIGHT",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="01",
    )
    left_b = dataclasses.replace(left_a, active_preset="B")
    right_b = dataclasses.replace(right_a, active_preset="B")

    states = iter(
        [
            [left_a, right_a],
            [left_b, right_a],
            [left_b, right_b],
        ]
    )
    ticks = {"value": -0.1}

    def fake_monotonic() -> float:
        ticks["value"] += 0.1
        return ticks["value"]

    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: next(states))
    monkeypatch.setattr(hw.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    payload = hw._wait_for_main_pair_preset(
        vid=0x04D8,
        pid=0xFF89,
        expected_preset="B",
        timeout_s=2.0,
        poll_interval_s=0.0,
    )

    assert payload["expected_preset"] == "B"
    assert payload["left_reached_s"] == pytest.approx(0.3)
    assert payload["right_reached_s"] == pytest.approx(0.5)
    assert payload["both_reached_s"] == pytest.approx(0.5)
    assert payload["final"]["left"]["active_preset"] == "B"
    assert payload["final"]["right"]["active_preset"] == "B"


def test_wait_for_main_pair_preset_tolerates_transient_hid_loss(monkeypatch) -> None:
    left_b = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="B",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="08",
    )
    right_b = dataclasses.replace(
        left_b,
        path="right-path",
        role="RIGHT",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="09",
    )
    states = iter(
        [
            RuntimeError("expected exactly 2 visible MAIN HID devices, found 0"),
            (left_b, right_b),
        ]
    )
    ticks = {"value": -0.1}

    def fake_monotonic() -> float:
        ticks["value"] += 0.1
        return ticks["value"]

    def fake_read_pair_state(*, vid: int, pid: int):
        item = next(states)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(hw, "_read_pair_state", fake_read_pair_state)
    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: [])
    monkeypatch.setattr(hw.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    payload = hw._wait_for_main_pair_preset(
        vid=0x04D8,
        pid=0xFF89,
        expected_preset="B",
        timeout_s=2.0,
        poll_interval_s=0.0,
    )

    assert payload["expected_preset"] == "B"
    assert payload["both_reached_s"] == pytest.approx(0.3)
    assert payload["observations"][0]["error"] == "expected exactly 2 visible MAIN HID devices, found 0"
    assert payload["final"]["left"]["active_preset"] == "B"
    assert payload["final"]["right"]["active_preset"] == "B"


def test_wait_for_main_pair_preset_accepts_unordered_pair_when_roles_unavailable(monkeypatch) -> None:
    main_a = hw.MainRoleState(
        path="path-z",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="UNKNOWN",
        active_preset="A",
        active_config_name=None,
        route_labels=[],
        route_values=[],
        raw_window_hex="08",
    )
    main_b = dataclasses.replace(
        main_a,
        path="path-a",
        active_preset="A",
    )
    ticks = {"value": -0.1}

    def fake_monotonic() -> float:
        ticks["value"] += 0.1
        return ticks["value"]

    monkeypatch.setattr(
        hw,
        "_read_pair_state",
        lambda *, vid, pid: (_ for _ in ()).throw(
            RuntimeError(
                "expected exactly one LEFT and one RIGHT MAIN from route memory; "
                "got [{'path': 'path-z', 'role': 'UNKNOWN'}]"
            )
        ),
    )
    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: [main_a, main_b])
    monkeypatch.setattr(hw.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    payload = hw._wait_for_main_pair_preset(
        vid=0x04D8,
        pid=0xFF89,
        expected_preset="A",
        timeout_s=2.0,
        poll_interval_s=0.0,
    )

    assert payload["matched_without_roles"] is True
    assert payload["both_reached_s"] == pytest.approx(0.1)
    assert payload["final"]["role_mapping"] == "unordered_path"
    assert payload["final"]["left"]["path"] == "path-a"
    assert payload["final"]["right"]["path"] == "path-z"


def test_collect_wake_poll_sample_uses_sticky_path_role_mapping(monkeypatch) -> None:
    main_unknown_a = hw.MainRoleState(
        path="path-left",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="UNKNOWN",
        active_preset="A",
        active_config_name=None,
        route_labels=[],
        route_values=[],
        raw_window_hex="08",
    )
    main_unknown_b = dataclasses.replace(
        main_unknown_a,
        path="path-right",
        raw_window_hex="09",
    )
    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: [main_unknown_a, main_unknown_b])

    sample = hw._collect_wake_poll_sample(
        vid=0x04D8,
        pid=0xFF89,
        expected_preset="A",
        sticky_path_roles={"path-left": "LEFT", "path-right": "RIGHT"},
        elapsed_s=0.2,
    )

    assert sample["functional_ready"] is True
    assert sample["role_decode_ready"] is False
    assert sample["effective_role_ready"] is True
    assert sample["sticky_roles_used"] is True
    assert [item["role_effective"] for item in sample["mains"]] == ["LEFT", "RIGHT"]


def test_wait_for_wake_two_phase_allows_transient_unknown_roles(monkeypatch) -> None:
    unknown_left = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="UNKNOWN",
        active_preset="B",
        active_config_name=None,
        route_labels=[],
        route_values=[],
        raw_window_hex="08",
    )
    unknown_right = dataclasses.replace(
        unknown_left,
        path="right-path",
        raw_window_hex="09",
    )
    decoded_left = dataclasses.replace(unknown_left, role="LEFT")
    decoded_right = dataclasses.replace(unknown_right, role="RIGHT")
    states = iter([[unknown_left, unknown_right], [decoded_left, decoded_right]])
    ticks = {"value": -0.1}

    def fake_monotonic() -> float:
        ticks["value"] += 0.1
        return ticks["value"]

    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: next(states))
    monkeypatch.setattr(hw.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    payload = hw._wait_for_wake_two_phase(
        vid=0x04D8,
        pid=0xFF89,
        expected_preset="B",
        timeout_s=5.0,
        poll_interval_s=0.0,
        wake_phase_a_timeout_s=1.0,
        wake_phase_b_timeout_s=1.0,
        wake_role_stable_polls=1,
        wake_diagnostics_tail=10,
        sticky_path_roles={"left-path": "LEFT", "right-path": "RIGHT"},
    )

    assert payload["phase_a_passed_at_s"] == pytest.approx(0.1)
    assert payload["samples"][0]["functional_ready"] is True
    assert payload["samples"][0]["role_decode_ready"] is False
    assert payload["samples"][1]["role_decode_ready"] is True


def test_wait_for_wake_two_phase_fails_with_role_decode_unstable(monkeypatch) -> None:
    unknown_left = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="UNKNOWN",
        active_preset="A",
        active_config_name=None,
        route_labels=[],
        route_values=[],
        raw_window_hex="08",
    )
    unknown_right = dataclasses.replace(
        unknown_left,
        path="right-path",
        raw_window_hex="09",
    )
    ticks = {"value": -0.1}

    def fake_monotonic() -> float:
        ticks["value"] += 0.1
        return ticks["value"]

    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: [unknown_left, unknown_right])
    monkeypatch.setattr(hw.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    with pytest.raises(hw.WakeValidationError) as exc:
        hw._wait_for_wake_two_phase(
            vid=0x04D8,
            pid=0xFF89,
            expected_preset="A",
            timeout_s=5.0,
            poll_interval_s=0.0,
            wake_phase_a_timeout_s=1.0,
            wake_phase_b_timeout_s=0.25,
            wake_role_stable_polls=2,
            wake_diagnostics_tail=10,
            sticky_path_roles={"left-path": "LEFT", "right-path": "RIGHT"},
        )

    assert exc.value.code == hw.WAKE_FAILURE_ROLE_DECODE_UNSTABLE
    assert "WAKE_POLL_DIAGNOSTICS" in str(exc.value)


def test_wait_for_wake_two_phase_tolerates_transient_hid_read_error(monkeypatch) -> None:
    decoded_left = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="A",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="08",
    )
    decoded_right = dataclasses.replace(
        decoded_left,
        path="right-path",
        role="RIGHT",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="09",
    )
    calls = {"count": 0}
    ticks = {"value": -0.1}

    def fake_monotonic() -> float:
        ticks["value"] += 0.1
        return ticks["value"]

    def fake_collect_main_roles(*, vid: int, pid: int):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("expected exactly 2 visible MAIN HID devices, found 0")
        return [decoded_left, decoded_right]

    monkeypatch.setattr(hw, "_collect_main_roles", fake_collect_main_roles)
    monkeypatch.setattr(hw.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    payload = hw._wait_for_wake_two_phase(
        vid=0x04D8,
        pid=0xFF89,
        expected_preset="A",
        timeout_s=5.0,
        poll_interval_s=0.0,
        wake_phase_a_timeout_s=1.0,
        wake_phase_b_timeout_s=1.0,
        wake_role_stable_polls=1,
        wake_diagnostics_tail=10,
        sticky_path_roles={},
    )

    assert payload["samples"][0]["hid_read_ok"] is False
    assert "found 0" in payload["samples"][0]["read_error"]
    assert payload["samples"][1]["functional_ready"] is True


def test_wait_for_wake_two_phase_failure_contains_sample_tail(monkeypatch) -> None:
    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: [])
    ticks = {"value": -0.1}

    def fake_monotonic() -> float:
        ticks["value"] += 0.1
        return ticks["value"]

    monkeypatch.setattr(hw.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    with pytest.raises(hw.WakeValidationError) as exc:
        hw._wait_for_wake_two_phase(
            vid=0x04D8,
            pid=0xFF89,
            expected_preset="A",
            timeout_s=5.0,
            poll_interval_s=0.0,
            wake_phase_a_timeout_s=0.25,
            wake_phase_b_timeout_s=1.0,
            wake_role_stable_polls=1,
            wake_diagnostics_tail=3,
            sticky_path_roles={},
        )

    text = str(exc.value)
    assert exc.value.code == hw.WAKE_FAILURE_FUNCTIONAL_TIMEOUT
    assert "WAKE_POLL_DIAGNOSTICS" in text
    assert "\"sample_tail_count\"" in text


def test_preset_convergence_command_writes_result(monkeypatch, tmp_path) -> None:
    left_before = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="A",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="00",
    )
    right_before = dataclasses.replace(
        left_before,
        path="right-path",
        role="RIGHT",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="01",
    )
    left_after = dataclasses.replace(left_before, active_preset="B")
    right_after = dataclasses.replace(right_before, active_preset="B")

    states = iter([[left_before, right_before], [left_after, right_after]])
    monkeypatch.setattr(hw, "_collect_main_roles", lambda *, vid, pid: next(states))
    monkeypatch.setattr(
        hw,
        "_probe_lcd",
        lambda **kwargs: {"consensus": {"line1": "Volume", "line2": "Active: B"}},
    )
    monkeypatch.setattr(
        hw,
        "_execute_ir_sequence",
        lambda **kwargs: [{"action": "F2", "command": ["fake-ir", "F2"], "returncode": 0}],
    )
    monkeypatch.setattr(
        hw,
        "_wait_for_main_pair_preset",
        lambda **kwargs: {
            "expected_preset": "B",
            "left_reached_s": 0.2,
            "right_reached_s": 0.2,
            "both_reached_s": 0.2,
            "observations": [],
            "final": {
                "left": dataclasses.asdict(left_after),
                "right": dataclasses.asdict(right_after),
            },
        },
    )
    monkeypatch.setattr(
        hw,
        "_wait_for_lcd_target",
        lambda **kwargs: {"matched_at_s": 0.3, "probes": [], "last_summary_path": "fake"},
    )

    rc = hw.main(
        [
            "--output-root",
            str(tmp_path),
            "preset-convergence",
            "--action",
            "F2",
        ]
    )

    assert rc == 0
    result_files = list((tmp_path / "preset_convergence").rglob("result.json"))
    assert len(result_files) == 1
    payload = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert payload["expected_preset"] == "B"
    assert payload["after"]["left"]["active_preset"] == "B"
    assert payload["sequence"] == [{"action": "F2", "sleep_after_s": 0.0}]


def test_rapid_toggle_command_expands_sequence_and_expected_target(monkeypatch, tmp_path) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        hw,
        "_run_preset_sequence_scenario",
        lambda **kwargs: seen.setdefault("call", kwargs) or (tmp_path / "result.json"),
    )

    rc = hw.main(
        [
            "--output-root",
            str(tmp_path),
            "rapid-toggle-convergence",
            "--sequence",
            "F1,F2,F1",
            "--inter-press-ms",
            "250",
        ]
    )

    assert rc == 0
    call = seen["call"]
    assert call["scenario_name"] == "rapid_toggle_convergence"
    assert call["expected_preset"] == "A"
    assert [step.action for step in call["steps"]] == ["F1", "F2", "F1"]
    assert [step.sleep_after_s for step in call["steps"]] == [0.25, 0.25, 0.0]


def test_lcd_summary_contains_text_matches_observations() -> None:
    summary = {
        "captures": [
            {
                "observations": [
                    {"text": "Volume:Mute    A"},
                    {"text": "Auto Detect"},
                ]
            }
        ]
    }

    assert hw._lcd_summary_contains_text(summary, "Mute") is True
    assert hw._lcd_summary_contains_text(summary, "Zzz") is False


def test_preset_mute_timing_sweep_command_writes_result(monkeypatch, tmp_path) -> None:
    left_before = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="A",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="08",
    )
    right_before = dataclasses.replace(
        left_before,
        path="right-path",
        role="RIGHT",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="09",
    )
    left_after = dataclasses.replace(left_before, active_preset="B")
    right_after = dataclasses.replace(right_before, active_preset="B")

    states = iter([(left_before, right_before), (left_after, right_after)])
    actions = iter(["F2", "F1"])
    monkeypatch.setattr(hw, "_read_pair_state", lambda *, vid, pid: next(states))
    monkeypatch.setattr(
        hw,
        "_probe_lcd",
        lambda **kwargs: {"consensus": {"line1": "Volume", "line2": "Active: B"}},
    )
    monkeypatch.setattr(
        hw,
        "_ensure_pair_unmuted",
        lambda **kwargs: {"performed": False},
    )
    monkeypatch.setattr(
        hw,
        "_next_preset_action_from_pair",
        lambda *, vid, pid: next(actions),
    )
    monkeypatch.setattr(
        hw,
        "_run_preset_action_and_wait",
        lambda **kwargs: {"expected_preset": "B"},
    )
    monkeypatch.setattr(
        hw,
        "_run_mute_toggle_cycle",
        lambda **kwargs: {"after": {"left": {"active_preset": "B"}, "right": {"active_preset": "B"}}},
    )
    monkeypatch.setattr(hw, "_sleep_ms", lambda delay_ms: delay_ms / 1000.0)

    rc = hw.main(
        [
            "--output-root",
            str(tmp_path),
            "preset-mute-timing-sweep",
            "--delays-ms",
            "100,250",
        ]
    )

    assert rc == 0
    result_files = list((tmp_path / "preset_mute_timing_sweep").rglob("result.json"))
    assert len(result_files) == 1
    payload = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert payload["delays_ms"] == [100.0, 250.0]
    assert len(payload["iterations"]) == 2


def test_preset_standby_wake_timing_sweep_command_writes_result(monkeypatch, tmp_path) -> None:
    left_before = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="A",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="08",
    )
    right_before = dataclasses.replace(
        left_before,
        path="right-path",
        role="RIGHT",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="09",
    )

    monkeypatch.setattr(hw, "_read_pair_state", lambda *, vid, pid: (left_before, right_before))
    monkeypatch.setattr(
        hw,
        "_probe_lcd",
        lambda **kwargs: {"consensus": {"line1": "Volume", "line2": "Active: A"}},
    )
    monkeypatch.setattr(hw, "_ensure_pair_unmuted", lambda **kwargs: {"performed": False})
    monkeypatch.setattr(hw, "_next_preset_action_from_pair", lambda *, vid, pid: "F2")
    monkeypatch.setattr(hw, "_run_preset_action_and_wait", lambda **kwargs: {"expected_preset": "B"})
    monkeypatch.setattr(hw, "_run_standby_wake_cycle", lambda **kwargs: {"after": {}})
    monkeypatch.setattr(hw, "_sleep_ms", lambda delay_ms: delay_ms / 1000.0)

    rc = hw.main(
        [
            "--output-root",
            str(tmp_path),
            "preset-standby-wake-timing-sweep",
            "--delays-ms",
            "250",
        ]
    )

    assert rc == 0
    result_files = list((tmp_path / "preset_standby_wake_timing_sweep").rglob("result.json"))
    assert len(result_files) == 1
    payload = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert payload["delays_ms"] == [250.0]
    assert len(payload["iterations"]) == 1


def test_run_standby_wake_cycle_uses_endpoint_actions(monkeypatch, tmp_path) -> None:
    actions: list[str] = []

    left_after = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="B",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="08",
    )
    right_after = dataclasses.replace(
        left_after,
        path="right-path",
        role="RIGHT",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="09",
    )

    monkeypatch.setattr(
        hw,
        "_send_single_ir_action",
        lambda *, args, action: (actions.append(action) or {"action": action}),
    )
    monkeypatch.setattr(hw, "_capture_sticky_path_roles", lambda **kwargs: {"path_roles": {}, "states": [], "error": None})
    monkeypatch.setattr(hw, "_wait_for_standby_lcd_entry", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(hw, "_try_read_pair_state", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(hw, "_wait_for_wake_two_phase", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(hw, "_wait_for_lcd_usable_expected_preset", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(hw, "_read_pair_state", lambda *, vid, pid: (left_after, right_after))
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    args = SimpleNamespace(
        vid=0x04D8,
        pid=0xFF89,
        timeout_s=5.0,
        main_poll_s=0.1,
        lcd_timeout_s=5.0,
        lcd_poll_s=0.1,
        lcd_probe_captures=3,
        standby_dwell_s=0.0,
        wake_phase_a_timeout_s=None,
        wake_phase_b_timeout_s=None,
        wake_role_stable_polls=2,
        wake_diagnostics_tail=30,
        wake_max_attempts=2,
        wake_retry_delay_s=0.0,
    )

    payload = hw._run_standby_wake_cycle(
        expected_preset="B",
        args=args,
        output_root=tmp_path,
        context="unit_test",
    )

    assert actions == ["STANDBY", "WAKE"]
    assert payload["after"]["left"]["active_preset"] == "B"
    assert payload["after"]["right"]["active_preset"] == "B"


def test_run_standby_wake_cycle_retries_wake_on_main_timeout(monkeypatch, tmp_path) -> None:
    actions: list[str] = []
    wait_calls = {"count": 0}

    left_after = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="A",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="08",
    )
    right_after = dataclasses.replace(
        left_after,
        path="right-path",
        role="RIGHT",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="09",
    )

    monkeypatch.setattr(
        hw,
        "_send_single_ir_action",
        lambda *, args, action: (actions.append(action) or {"action": action}),
    )
    monkeypatch.setattr(hw, "_capture_sticky_path_roles", lambda **kwargs: {"path_roles": {}, "states": [], "error": None})
    monkeypatch.setattr(hw, "_wait_for_standby_lcd_entry", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(hw, "_try_read_pair_state", lambda **kwargs: {"ok": True})

    def fake_wait_for_wake_two_phase(**kwargs):
        wait_calls["count"] += 1
        if wait_calls["count"] == 1:
            raise hw.WakeValidationError(
                hw.WAKE_FAILURE_FUNCTIONAL_TIMEOUT,
                "phase A functional wake gate did not converge before timeout",
                samples=[{"t_s": 0.1, "read_error": "found 0"}],
                diagnostics_tail=5,
            )
        return {"ok": True}

    monkeypatch.setattr(hw, "_wait_for_wake_two_phase", fake_wait_for_wake_two_phase)
    monkeypatch.setattr(hw, "_wait_for_lcd_usable_expected_preset", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(hw, "_read_pair_state", lambda *, vid, pid: (left_after, right_after))
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    args = SimpleNamespace(
        vid=0x04D8,
        pid=0xFF89,
        timeout_s=5.0,
        main_poll_s=0.1,
        lcd_timeout_s=5.0,
        lcd_poll_s=0.1,
        lcd_probe_captures=3,
        standby_dwell_s=0.0,
        wake_max_attempts=3,
        wake_retry_delay_s=0.0,
        wake_phase_a_timeout_s=None,
        wake_phase_b_timeout_s=None,
        wake_role_stable_polls=2,
        wake_diagnostics_tail=30,
    )

    payload = hw._run_standby_wake_cycle(
        expected_preset="A",
        args=args,
        output_root=tmp_path,
        context="unit_test",
    )

    assert actions == ["STANDBY", "WAKE", "WAKE"]
    assert payload["wake_wait_errors"][0]["code"] == hw.WAKE_FAILURE_FUNCTIONAL_TIMEOUT
    assert payload["after"]["left"]["active_preset"] == "A"
    assert payload["after"]["right"]["active_preset"] == "A"


def test_wait_for_standby_lcd_entry_allows_guarded_blank_fallback(monkeypatch, tmp_path) -> None:
    summaries = iter(
        [
            {
                "consensus": {"line1": None, "line2": None},
                "summary_path": str(tmp_path / "probe_1.json"),
            },
            {
                "consensus": {"line1": None, "line2": None},
                "summary_path": str(tmp_path / "probe_2.json"),
            },
        ]
    )
    ticks = {"value": -0.1}

    def fake_monotonic() -> float:
        ticks["value"] += 0.1
        return ticks["value"]

    monkeypatch.setattr(hw, "_probe_lcd", lambda **kwargs: next(summaries))
    monkeypatch.setattr(hw, "_try_read_pair_state", lambda **kwargs: {"reachable": False, "error": "hid closed"})
    monkeypatch.setattr(hw.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(hw.time, "sleep", lambda _: None)

    args = SimpleNamespace(
        vid=0x04D8,
        pid=0xFF89,
        camera_selector="cam",
        vendor=1133,
        product=2194,
        address=5,
        zoom=500,
        focus=140,
        exposure=156,
        gain=80,
        sharpness=200,
        captures=1,
        warmup_s=0.0,
        standby_allow_blank_fallback=True,
        standby_blank_consecutive=2,
    )

    payload = hw._wait_for_standby_lcd_entry(
        timeout_s=2.0,
        poll_interval_s=0.0,
        probe_captures=1,
        args=args,
        output_root=tmp_path,
        pre_standby_lcd_visible=True,
    )

    assert payload["matched_mode"] == "blank_fallback"
    assert payload["blank_support_reason"] == "hid_unreachable"
    assert payload["matched_at_s"] == pytest.approx(0.3)


def test_reconnect_responsiveness_soak_command_writes_result(monkeypatch, tmp_path) -> None:
    left_before = hw.MainRoleState(
        path="left-path",
        serial="",
        product="DLCP",
        manufacturer="Hypex BV",
        role="LEFT",
        active_preset="A",
        active_config_name="CfgL",
        route_labels=["L"] * 6,
        route_values=[0] * 6,
        raw_window_hex="08",
    )
    right_before = dataclasses.replace(
        left_before,
        path="right-path",
        role="RIGHT",
        active_config_name="CfgR",
        route_labels=["R"] * 6,
        route_values=[1] * 6,
        raw_window_hex="09",
    )

    monkeypatch.setattr(hw, "_read_pair_state", lambda *, vid, pid: (left_before, right_before))
    monkeypatch.setattr(
        hw,
        "_probe_lcd",
        lambda **kwargs: {"consensus": {"line1": "Volume", "line2": "Active: A"}},
    )
    monkeypatch.setattr(hw, "_ensure_pair_unmuted", lambda **kwargs: {"performed": False})
    monkeypatch.setattr(hw, "_next_preset_action_from_pair", lambda *, vid, pid: "F2")
    monkeypatch.setattr(hw, "_run_preset_action_and_wait", lambda **kwargs: {"expected_preset": "B"})
    monkeypatch.setattr(hw, "_run_standby_wake_cycle", lambda **kwargs: {"after": {}})
    monkeypatch.setattr(hw, "_run_mute_toggle_cycle", lambda **kwargs: {"after": {}})

    rc = hw.main(
        [
            "--output-root",
            str(tmp_path),
            "reconnect-responsiveness-soak",
            "--iterations",
            "3",
        ]
    )

    assert rc == 0
    result_files = list((tmp_path / "reconnect_responsiveness_soak").rglob("result.json"))
    assert len(result_files) == 1
    payload = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert payload["iterations_requested"] == 3
    assert len(payload["iterations"]) == 3


def test_probe_main_role_state_reads_snapshot_and_memory(monkeypatch) -> None:
    info = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"hid-left",
        manufacturer_string="Hypex BV",
        product_string="DLCP",
        serial_number="",
    )
    monkeypatch.setattr(hw, "_pick_device", lambda vid, pid, path: info)
    monkeypatch.setattr(hw, "_probe_device_snapshot", lambda info, vid, pid: _snapshot("L", "L", "L", "L", "L", "L"))
    monkeypatch.setattr(hw, "_probe_active_preset_ep0", lambda vid, pid, path=None: "A")
    monkeypatch.setattr(
        hw,
        "read_flash_window",
        lambda **kwargs: bytes([0x01, 0x02, 0x03]),
    )

    state = hw._probe_main_role_state(vid=0x04D8, pid=0xFF89, path=b"hid-left")

    assert state.role == "LEFT"
    assert state.active_preset == "A"
    assert state.raw_window_hex == "010203"


def test_probe_main_role_state_suppresses_memory_read_progress(monkeypatch, capsys) -> None:
    info = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"hid-left",
        manufacturer_string="Hypex BV",
        product_string="DLCP",
        serial_number="",
    )
    monkeypatch.setattr(hw, "_pick_device", lambda vid, pid, path: info)
    monkeypatch.setattr(hw, "_probe_device_snapshot", lambda info, vid, pid: _snapshot("L"))
    monkeypatch.setattr(hw, "_probe_active_preset_ep0", lambda vid, pid, path=None: "A")

    def fake_read_flash_window(**kwargs):
        print("read 0x0008/0x0008")
        return bytes([0xAA])

    monkeypatch.setattr(hw, "read_flash_window", fake_read_flash_window)

    state = hw._probe_main_role_state(vid=0x04D8, pid=0xFF89, path=b"hid-left")

    assert state.raw_window_hex == "aa"
    captured = capsys.readouterr()
    assert captured.out == ""


def test_flipper_inventory_only_reports_flipper_named_serial_devices(monkeypatch) -> None:
    monkeypatch.setattr(
        hw.Path,
        "glob",
        lambda self, pattern: [
            hw.Path("/dev/cu.NicksLugs"),
            hw.Path("/dev/cu.debug-console"),
            hw.Path("/dev/cu.FlipperZero"),
            hw.Path("/dev/cu.usbmodemflip_Ovarlide1"),
        ],
    )
    monkeypatch.setattr(hw.Path, "exists", lambda self: False)

    inventory = hw._flipper_inventory()

    assert inventory["qflipper_cli"] is None
    assert inventory["serial_candidates"] == [
        "/dev/cu.FlipperZero",
        "/dev/cu.usbmodemflip_Ovarlide1",
    ]


def test_lcd_pick_lines_extracts_active_letter_from_volume_line() -> None:
    observations = [
        lcd.OcrObservation(text="Auto Detect", confidence=0.99, x=0.10, y=0.30, w=0.20, h=0.10),
        lcd.OcrObservation(text="Volume:-15.0dB A", confidence=0.99, x=0.10, y=0.80, w=0.30, h=0.10),
    ]

    line1, line2 = lcd._pick_lines(observations)

    assert line1 == "Volume"
    assert line2 == "Active: A"


def test_lcd_pick_lines_prefers_explicit_active_line_when_present() -> None:
    observations = [
        lcd.OcrObservation(text="Active B", confidence=0.98, x=0.10, y=0.30, w=0.20, h=0.10),
        lcd.OcrObservation(text="Volume:-20.0dB", confidence=0.99, x=0.10, y=0.80, w=0.30, h=0.10),
    ]

    line1, line2 = lcd._pick_lines(observations)

    assert line1 == "Volume"
    assert line2 == "Active: B"


def test_lcd_resolve_uvcc_address_returns_selector_match_when_default_is_wrong(monkeypatch) -> None:
    monkeypatch.setattr(
        lcd,
        "_list_uvcc_devices",
        lambda: [
            {"vendor": 1133, "product": 2194, "address": 5, "name": "HD Pro Webcam C920"},
            {"vendor": 1452, "product": 34065, "address": 1, "name": "MacBook Pro Camera"},
        ],
    )

    address = lcd._resolve_uvcc_address(
        vendor=1133,
        product=2194,
        preferred_address=1,
        selector="HD Pro Webcam C920",
    )

    assert address == 5


def test_lcd_resolve_uvcc_address_requires_explicit_address_when_multiple_match(monkeypatch) -> None:
    monkeypatch.setattr(
        lcd,
        "_list_uvcc_devices",
        lambda: [
            {"vendor": 1133, "product": 2194, "address": 5, "name": "HD Pro Webcam C920"},
            {"vendor": 1133, "product": 2194, "address": 6, "name": "HD Pro Webcam C920"},
        ],
    )

    with pytest.raises(RuntimeError, match="pass --address explicitly"):
        lcd._resolve_uvcc_address(
            vendor=1133,
            product=2194,
            preferred_address=1,
            selector="HD Pro Webcam C920",
        )


def test_probe_lcd_passes_camera_selector_to_configure(monkeypatch, tmp_path) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        hw.lcd_probe,
        "_configure_camera",
        lambda args: seen.setdefault("camera_selector", args.camera_selector) or {},
    )
    monkeypatch.setattr(hw.lcd_probe, "_capture_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(hw.lcd_probe, "_ocr_frame", lambda *args, **kwargs: [])
    monkeypatch.setattr(hw.lcd_probe, "_pick_lines", lambda observations: ("Volume", "Active: A"))
    monkeypatch.setattr(hw.lcd_probe, "_consensus", lambda values: "Volume")
    monkeypatch.setattr(hw.lcd_probe, "_consensus_active", lambda values: "Active: A")

    summary = hw._probe_lcd(
        camera_selector="HD Pro Webcam C920",
        vendor=1133,
        product=2194,
        address=5,
        zoom=500,
        focus=140,
        exposure=156,
        gain=80,
        sharpness=200,
        captures=1,
        warmup_s=0.1,
        skip_configure=False,
        output_root=tmp_path,
    )

    assert seen["camera_selector"] == "HD Pro Webcam C920"
    assert summary["consensus"]["line2"] == "Active: A"
