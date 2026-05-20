from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace

import pytest

from dlcp_fw.paths import PROJECT_ROOT


pytestmark = pytest.mark.dual_supported


def _load_runner() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "run_v171_v32_ledger_hardware_gate.py"
    spec = importlib.util.spec_from_file_location("run_v171_v32_ledger_hardware_gate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_src4382_evidence_validator() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "validate_src4382_manual_evidence.py"
    spec = importlib.util.spec_from_file_location("validate_src4382_manual_evidence", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _src4382_identity_lines() -> tuple[str, str, str]:
    validator = _load_src4382_evidence_validator()
    identities = validator.current_release_identities()
    control = identities["CONTROL"].display
    main = identities["MAIN"].display
    return (
        f"CONTROL: {control}",
        f"MAIN PB1: {main}",
        f"MAIN PB2: {main}",
    )


def _src4382_expected_firmware_payload() -> dict[str, str]:
    validator = _load_src4382_evidence_validator()
    identities = validator.current_release_identities()
    hashes = validator.current_release_hashes()
    return {
        "CONTROL": identities["CONTROL"].display,
        "CONTROL SHA256": hashes["CONTROL"],
        "MAIN PB1": identities["MAIN"].display,
        "MAIN PB1 SHA256": hashes["MAIN"],
        "MAIN PB2": identities["MAIN"].display,
        "MAIN PB2 SHA256": hashes["MAIN"],
    }


def _runner_control_identity(runner: ModuleType, phase_name: str) -> dict[str, object]:
    phase = next(phase for phase in runner.PHASES if phase.name == phase_name)
    identity = runner._control_hex_identity_for_phase(phase)
    assert identity is not None
    return identity


def _hardware_test_nodes() -> set[str]:
    path = PROJECT_ROOT / "tests" / "hardware" / "test_live_state_transitions.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def _hardware_test_sources() -> dict[str, str]:
    path = PROJECT_ROOT / "tests" / "hardware" / "test_live_state_transitions.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    lines = text.splitlines()
    sources: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        start = node.lineno - 1
        end = node.end_lineno or node.lineno
        sources[node.name] = "\n".join(lines[start:end])
    return sources


def _sim_test_sources() -> dict[str, tuple[Path, str]]:
    tests: dict[str, tuple[Path, str]] = {}
    for path in (PROJECT_ROOT / "tests" / "sim").glob("test_*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        lines = text.splitlines()
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            tests[node.name] = (path, "\n".join(lines[start:end]))
    return tests


def _ledger_text() -> str:
    return (PROJECT_ROOT / "docs" / "IMPL_V171_V32_BUG_LEDGER.md").read_text(
        encoding="utf-8"
    )


def test_src4382_manual_evidence_template_is_tracked_and_referenced() -> None:
    template_path = PROJECT_ROOT / "docs" / "SRC4382_AD_MANUAL_EVIDENCE_TEMPLATE.md"
    template = template_path.read_text(encoding="utf-8")
    hardware_runbook = (PROJECT_ROOT / "docs" / "HARDWARE_TEST.md").read_text(
        encoding="utf-8"
    )
    impl_spec = (
        PROJECT_ROOT / "docs" / "IMPL_SRC4382_AUTODETECT_POLLING_SPEC.md"
    ).read_text(encoding="utf-8")
    ledger = _ledger_text()
    validator = (PROJECT_ROOT / "scripts" / "validate_src4382_manual_evidence.py").read_text(
        encoding="utf-8"
    )
    validator_module = _load_src4382_evidence_validator()
    identities = validator_module.current_release_identities()
    hashes = validator_module.current_release_hashes()

    artifact_path = (
        "artifacts/probes/v171_v32_ledger_gate/"
        "bug_src4382_ad_01_manual_evidence.md"
    )
    required_fields = (
        "CONTROL: V1.71",
        "CONTROL SHA256:",
        "CONTROL flashed/running V1.71? yes/no:",
        "MAIN PB1: V3.2",
        "MAIN PB1 SHA256:",
        "MAIN PB1 visible/running V3.2? yes/no:",
        "MAIN PB2: V3.2",
        "MAIN PB2 SHA256:",
        "MAIN PB2 visible/running V3.2? yes/no:",
        "Normal low-band output? yes/no",
        "Fixed digital sources tested after Auto Detect (S/PDIF, USB Audio, AES, Optical as available):",
        "Any fixed digital source silent? yes/no:",
        "Selected same source? yes/no",
        "Volume responsive? yes/no",
        "Mute/unmute responsive? yes/no",
        "Preset A/B responsive and audio correct after switch? yes/no",
        "Standby/wake responsive and both MAINs recover? yes/no",
        "Explicit input selection responsive? yes/no",
        "Auto Detect no-source duration >= 30 min? yes/no, duration:",
        "Fixed-input playback duration >= 1 h? yes/no, duration:",
        "UI stalls observed? yes/no:",
        "Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details:",
        "Unexplained I/R growth observed? yes/no:",
        "PB1 before/after diag I/R:",
        "PB2 before/after diag I/R:",
        "I/R growth explanation if any:",
        "Pass/fail:",
    )

    assert "BUG-SRC4382-AD-01" in template
    assert identities["CONTROL"].display in template
    assert identities["MAIN"].display in template
    assert hashes["CONTROL"] in template
    assert hashes["MAIN"] in template
    assert artifact_path in template
    for field in required_fields:
        assert field in template, f"missing SRC4382 manual evidence field: {field}"
    for text in (hardware_runbook, impl_spec, ledger):
        assert "docs/SRC4382_AD_MANUAL_EVIDENCE_TEMPLATE.md" in text
        assert artifact_path in text
        assert "scripts/validate_src4382_manual_evidence.py" in text
    assert artifact_path in validator


def test_src4382_manual_evidence_artifact_is_prefilled_with_current_release_identity() -> None:
    validator = _load_src4382_evidence_validator()
    identities = validator.current_release_identities()
    hashes = validator.current_release_hashes()
    artifact_path = validator.DEFAULT_EVIDENCE_PATH
    artifact = artifact_path.read_text(encoding="utf-8")

    assert identities["CONTROL"].display in artifact
    assert identities["MAIN"].display in artifact
    assert hashes["CONTROL"] in artifact
    assert hashes["MAIN"] in artifact

    errors = validator.validate_path(artifact_path)
    assert errors
    assert not any(error.startswith("firmware field must include current") for error in errors)
    assert not any(error.startswith("firmware hash field must include current") for error in errors)
    assert "section needs concrete entry: Date/Time" in errors
    assert (
        "field must start with yes or no: Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details: -> ''"
        in errors
    )


def _passing_src4382_manual_evidence() -> str:
    control_line, main_pb1_line, main_pb2_line = _src4382_identity_lines()
    validator = _load_src4382_evidence_validator()
    hashes = validator.current_release_hashes()
    return f"""# SRC4382 Auto Detect Manual Evidence

BUG-SRC4382-AD-01

## Date/Time

2026-05-19 22:30

## Firmware

{control_line}

CONTROL SHA256: {hashes["CONTROL"]}

CONTROL flashed/running V1.71? yes/no: yes

{main_pb1_line}

MAIN PB1 SHA256: {hashes["MAIN"]}

MAIN PB1 visible/running V3.2? yes/no: yes

{main_pb2_line}

MAIN PB2 SHA256: {hashes["MAIN"]}

MAIN PB2 visible/running V3.2? yes/no: yes

## Test Setup

Source/input: SPDIF 1

Preset: A

Volume: -30 dB

Audio material or measurement used for low-band check: sweep + music

## Fixed-Input Playback

Normal low-band output? yes/no: yes

Fixed digital sources tested after Auto Detect (S/PDIF, USB Audio, AES, Optical as available): S/PDIF, USB Audio, AES, Optical

Any fixed digital source silent? yes/no: no

Notes: baseline sounds normal

## Auto Detect Playback

Selected same source? yes/no: yes

Normal low-band output? yes/no: yes

Notes: Auto Detect sounds normal

## User Actions While Playing

Volume responsive? yes/no: yes

Mute/unmute responsive? yes/no: yes

Preset A/B responsive and audio correct after switch? yes/no: yes

Standby/wake responsive and both MAINs recover? yes/no: yes

Explicit input selection responsive? yes/no: yes

## Soak

Auto Detect no-source duration >= 30 min? yes/no, duration: yes, 35 min

Fixed-input playback duration >= 1 h? yes/no, duration: yes, 1 h 5 min

UI stalls observed? yes/no: no

Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details: no

Unexplained I/R growth observed? yes/no: no

PB1 before/after diag I/R: I0/R0 -> I0/R0

PB2 before/after diag I/R: I0/R0 -> I0/R0

I/R growth explanation if any: none

## Optional Captures

Audio capture / SPL / RTA: n/a

SCL/SDA capture: n/a

Probe logs: n/a

## Verdict

Pass/fail: pass

Remaining concerns: none
"""


def test_src4382_manual_evidence_validator_accepts_complete_pass() -> None:
    validator = _load_src4382_evidence_validator()
    assert validator.validate_text(_passing_src4382_manual_evidence()) == []


def test_src4382_manual_evidence_validator_rejects_template_and_short_soak() -> None:
    validator = _load_src4382_evidence_validator()
    template = (
        PROJECT_ROOT / "docs" / "SRC4382_AD_MANUAL_EVIDENCE_TEMPLATE.md"
    ).read_text(encoding="utf-8")
    template_errors = validator.validate_text(template)
    assert template_errors
    assert any(
        error == "field must be yes: Normal low-band output? yes/no: -> ''"
        for error in template_errors
    )

    short_soak = _passing_src4382_manual_evidence().replace(
        "yes, 35 min", "yes, 15 min"
    )
    errors = validator.validate_text(short_soak)
    assert any("duration too short" in error for error in errors)


def test_src4382_manual_evidence_validator_requires_concrete_run_metadata() -> None:
    validator = _load_src4382_evidence_validator()
    missing_metadata = (
        _passing_src4382_manual_evidence()
        .replace("2026-05-19 22:30", "-")
        .replace("Source/input: SPDIF 1", "Source/input:")
        .replace("Preset: A", "Preset:")
        .replace("Volume: -30 dB", "Volume:")
        .replace(
            "Audio material or measurement used for low-band check: sweep + music",
            "Audio material or measurement used for low-band check:",
        )
    )

    errors = validator.validate_text(missing_metadata)

    assert "section needs concrete entry: Date/Time" in errors
    for label in (
        "Source/input:",
        "Preset:",
        "Volume:",
        "Audio material or measurement used for low-band check:",
    ):
        assert f"field needs concrete value: {label} -> ''" in errors


def test_src4382_manual_evidence_validator_requires_release_pair_confirmation() -> None:
    validator = _load_src4382_evidence_validator()
    missing_confirmations = (
        _passing_src4382_manual_evidence()
        .replace("CONTROL flashed/running V1.71? yes/no: yes", "CONTROL flashed/running V1.71? yes/no:")
        .replace("MAIN PB1 visible/running V3.2? yes/no: yes", "MAIN PB1 visible/running V3.2? yes/no: no")
        .replace("MAIN PB2 visible/running V3.2? yes/no: yes", "MAIN PB2 visible/running V3.2? yes/no:")
    )

    errors = validator.validate_text(missing_confirmations)

    assert (
        "field must be yes: CONTROL flashed/running V1.71? yes/no: -> ''"
        in errors
    )
    assert (
        "field must be yes: MAIN PB1 visible/running V3.2? yes/no: -> 'no'"
        in errors
    )
    assert (
        "field must be yes: MAIN PB2 visible/running V3.2? yes/no: -> ''"
        in errors
    )


def test_src4382_manual_evidence_validator_rejects_stale_release_revisions() -> None:
    validator = _load_src4382_evidence_validator()
    identities = validator.current_release_identities()
    control = identities["CONTROL"]
    main = identities["MAIN"]
    stale_control_rev = "0x00" if control.rev_hex != "0x00" else "0xFF"
    stale_main_rev = "0x00" if main.rev_hex != "0x00" else "0xFF"
    stale_revisions = (
        _passing_src4382_manual_evidence()
        .replace(control.display, f"{control.version} / rev {stale_control_rev}")
        .replace(main.display, f"{main.version} / rev {stale_main_rev}")
    )

    errors = validator.validate_text(stale_revisions)

    assert (
        f"firmware field must include current {control.display}: "
        f"CONTROL: -> '{control.version} / rev {stale_control_rev}'"
    ) in errors
    assert (
        f"firmware field must include current {main.display}: "
        f"MAIN PB1: -> '{main.version} / rev {stale_main_rev}'"
    ) in errors
    assert (
        f"firmware field must include current {main.display}: "
        f"MAIN PB2: -> '{main.version} / rev {stale_main_rev}'"
    ) in errors


def test_src4382_manual_evidence_validator_rejects_stale_release_hashes() -> None:
    validator = _load_src4382_evidence_validator()
    hashes = validator.current_release_hashes()
    stale_control_hash = "0" * 64 if hashes["CONTROL"] != "0" * 64 else "f" * 64
    stale_main_hash = "0" * 64 if hashes["MAIN"] != "0" * 64 else "f" * 64
    stale_hashes = (
        _passing_src4382_manual_evidence()
        .replace(hashes["CONTROL"], stale_control_hash)
        .replace(hashes["MAIN"], stale_main_hash)
    )

    errors = validator.validate_text(stale_hashes)

    assert (
        "firmware hash field must include current SHA256 "
        f"{hashes['CONTROL']}: CONTROL SHA256: -> '{stale_control_hash}'"
    ) in errors
    assert (
        "firmware hash field must include current SHA256 "
        f"{hashes['MAIN']}: MAIN PB1 SHA256: -> '{stale_main_hash}'"
    ) in errors
    assert (
        "firmware hash field must include current SHA256 "
        f"{hashes['MAIN']}: MAIN PB2 SHA256: -> '{stale_main_hash}'"
    ) in errors


def test_src4382_manual_evidence_validator_requires_ir_snapshots() -> None:
    validator = _load_src4382_evidence_validator()
    missing_snapshot = _passing_src4382_manual_evidence().replace(
        "PB1 before/after diag I/R: I0/R0 -> I0/R0",
        "PB1 before/after diag I/R:",
    )
    invalid_snapshot = _passing_src4382_manual_evidence().replace(
        "PB2 before/after diag I/R: I0/R0 -> I0/R0",
        "PB2 before/after diag I/R: unchanged",
    )

    missing_errors = validator.validate_text(missing_snapshot)
    invalid_errors = validator.validate_text(invalid_snapshot)

    assert (
        "field needs concrete value: PB1 before/after diag I/R: -> ''"
        in missing_errors
    )
    assert (
        "field needs I/R before-after value like I0/R0 -> I0/R0: "
        "PB2 before/after diag I/R: -> 'unchanged'"
    ) in invalid_errors


def test_src4382_manual_evidence_validator_requires_badge_observation() -> None:
    validator = _load_src4382_evidence_validator()
    missing_badge_field = _passing_src4382_manual_evidence().replace(
        "Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details: no\n\n",
        "",
    )
    blank_badge_value = _passing_src4382_manual_evidence().replace(
        "Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details: no",
        "Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details:",
    )
    malformed_badge_value = _passing_src4382_manual_evidence().replace(
        "Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details: no",
        "Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details: pulsing observed",
    )

    assert (
        "missing field: Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details:"
        in validator.validate_text(missing_badge_field)
    )
    assert (
        "field must start with yes or no: Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details: -> ''"
        in validator.validate_text(blank_badge_value)
    )
    assert (
        "field must start with yes or no: Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details: -> 'pulsing observed'"
        in validator.validate_text(malformed_badge_value)
    )


def test_src4382_manual_evidence_validator_requires_ir_growth_explanation() -> None:
    validator = _load_src4382_evidence_validator()
    growth_without_explanation = _passing_src4382_manual_evidence().replace(
        "PB1 before/after diag I/R: I0/R0 -> I0/R0",
        "PB1 before/after diag I/R: I0/R0 -> I1/R0",
    )
    growth_with_explanation = growth_without_explanation.replace(
        "I/R growth explanation if any: none",
        "I/R growth explanation if any: expected I increment from injected SRC4382 NACK",
    )

    errors = validator.validate_text(growth_without_explanation)

    assert (
        "field needs concrete growth explanation: "
        "I/R growth explanation if any: -> 'none'"
    ) in errors
    assert validator.validate_text(growth_with_explanation) == []


def test_src4382_manual_evidence_validator_rejects_prefix_words_as_yes_no() -> None:
    validator = _load_src4382_evidence_validator()
    prefix_words = (
        _passing_src4382_manual_evidence()
        .replace(
            "CONTROL flashed/running V1.71? yes/no: yes",
            "CONTROL flashed/running V1.71? yes/no: yesterday",
        )
        .replace(
            "UI stalls observed? yes/no: no",
            "UI stalls observed? yes/no: none",
        )
        .replace("Pass/fail: pass", "Pass/fail: passive")
    )

    errors = validator.validate_text(prefix_words)

    assert (
        "field must be yes: CONTROL flashed/running V1.71? yes/no: "
        "-> 'yesterday'"
    ) in errors
    assert "field must be no: UI stalls observed? yes/no: -> 'none'" in errors
    assert "verdict must be pass: 'passive'" in errors


def test_src4382_manual_evidence_validator_requires_dated_timestamp() -> None:
    validator = _load_src4382_evidence_validator()

    missing_time = _passing_src4382_manual_evidence().replace(
        "2026-05-19 22:30", "2026-05-19"
    )
    assert validator.validate_text(missing_time) == [
        "section needs time-like value: Date/Time -> '2026-05-19'"
    ]

    missing_date = _passing_src4382_manual_evidence().replace(
        "2026-05-19 22:30", "22:30 hardware run"
    )
    assert validator.validate_text(missing_date) == [
        "section needs date-like value: Date/Time -> '22:30 hardware run'"
    ]


def test_src4382_manual_evidence_validator_cli_returns_nonzero_for_failure(
    tmp_path: Path,
) -> None:
    validator = _load_src4382_evidence_validator()
    evidence = tmp_path / "evidence.md"
    evidence.write_text(_passing_src4382_manual_evidence(), encoding="utf-8")
    assert validator.main([str(evidence)]) == 0

    evidence.write_text(
        _passing_src4382_manual_evidence().replace("Pass/fail: pass", "Pass/fail: fail"),
        encoding="utf-8",
    )
    assert validator.main([str(evidence)]) == 1


def _active_ledger_bug_ids(ledger: str) -> set[str]:
    active_table = ledger.split("## Current Verification Snapshot", 1)[0]
    return set(re.findall(r"\|\s*(BUG-[A-Z0-9-]+)\s*\|", active_table))


def _active_ledger_rows(ledger: str) -> dict[str, list[str]]:
    active_table = ledger.split("## Current Verification Snapshot", 1)[0]
    rows: dict[str, list[str]] = {}
    for line in active_table.splitlines():
        if not line.startswith("| BUG-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 5, f"unexpected active bug row shape: {line!r}"
        rows[cells[0]] = cells
    return rows


def _completion_audit_lines(ledger: str) -> dict[str, str]:
    audit = ledger.split("## Completion Audit", 1)[1].split(
        "Additional live hardware gate added",
        1,
    )[0]
    rows: dict[str, str] = {}
    for line in audit.splitlines():
        match = re.match(r"^\|\s*(BUG-[A-Z0-9-]+)\s*\|", line)
        if match:
            rows[match.group(1)] = line
    return rows


def _test_names_from_required_cell(cell: str) -> set[str]:
    names: set[str] = set()
    for code in re.findall(r"`([^`]+)`", cell):
        if "::" in code:
            node = code.rsplit("::", 1)[1]
            if node.startswith("{") and node.endswith("}"):
                names.update(
                    part.strip()
                    for part in node.strip("{}").split(",")
                    if part.strip().startswith("test_")
                )
            elif node.startswith("test_"):
                names.add(node)
            continue
        if code.startswith("test_") and "." not in code and "/" not in code:
            names.add(code)
    return names


def _required_sim_evidence_tests_by_bug() -> dict[str, tuple[str, ...]]:
    return {
        "BUG-DIAG-01": (
            "test_v171_v32_layer5_chain_diag_static_wait_updates_pb1_and_pb2",
            "test_v171_v32_layer5_diag_visible_page_refreshes_on_next_cadence",
        ),
        "BUG-DIAG-02": (
            "test_diag_loop_uses_non_modal_foreground_services",
            "test_v171_v32_layer5_chain_sustained_diag_page_keeps_control_responsive",
            "test_v171_v32_layer5_chain_diag_page_left_button_exits_promptly",
            "test_v171_v32_layer5_diag_page_dispatches_ir_volume_mute_and_preset",
            "test_v171_v32_layer5_diag_page_dispatches_ir_standby_and_wake",
        ),
        "BUG-IR-01": (
            "test_v16b_and_v171_rc5_pulse_train_decode_same_command_stress",
            "test_v171_ir_decode_uses_hardware_validated_stock_isr_path",
            "test_v171_profile_ir_actions_match_stock_v16b_dispatch_behavior",
        ),
        "BUG-IR-02": (
            "test_explicit_ir_standby_updates_control_lcd_state",
            "test_explicit_ir_wake_returns_control_lcd_to_volume",
            "test_v171_v32_layer5_diag_page_dispatches_ir_standby_and_wake",
        ),
        "BUG-STDBY-01": (
            "test_v32_duplicate_standby_preserves_pending_shutdown_event",
            "test_v171_v32_v32_panel_wake_brings_up_main1_via_h2_re_emit",
        ),
        "BUG-PRESET-01": (
            "test_v32_ep0_reapply_reload_filename_ram_for_restored_preset",
            "test_v32_release_flash_sim_full_main_post_flash_state",
        ),
        "BUG-PRESET-02": (
            "test_rapid_preset_reversal_during_apply_finishes_on_latest_target",
        ),
        "BUG-PRESET-03": (
            "test_ir_preset_b_tx_saturation_does_not_change_local_preset_state",
        ),
        "BUG-REV-01": (
            "test_v32_runtime_eeprom_identity_matches_release_hex_without_seed",
            "test_build_v32_release_bumps_runtime_eeprom_revision_marker",
        ),
        "BUG-SETTINGS-01": (
            "test_v32_cmd40_bootloader_entry_preserves_saved_settings_in_source",
            "test_sim_hid_cmd40_preserves_user_volume_and_input_settings",
            "test_v32_release_flash_sim_full_main_post_flash_state",
        ),
        "BUG-SRC4382-AD-01": (
            "test_v32_autodetect_source_present_drives_route_event_and_dsp_refresh",
            "test_v32_audio_path_safety_guard_rejects_missing_route_event_mutation",
            "test_v32_audio_path_safety_guard_rejects_missing_tas_refresh_mutation",
            "test_v32_src4382_autodetect_no_source_cadence_is_reduced",
            "test_v32_cadence_guard_rejects_unthrottled_receiver_select_mutation",
            "test_v32_src4382_autodetect_source_present_cadence_is_reduced",
            "test_v32_source_present_cadence_guard_rejects_unthrottled_monitor_mutation",
            "test_v32_src4382_no_source_scan_does_not_read_non_pcm_status",
            "test_v32_src4382_source_present_latches_non_pcm_status",
            "test_v32_src4382_single_source_loss_sample_does_not_flap_route",
            "test_v32_src4382_sustained_source_loss_resumes_scan_within_1s",
            "test_v32_src4382_writes_0d_only_when_candidate_changes",
            "test_v32_src4382_full_scan_detects_worst_position_source_within_500ms",
            "test_v32_discovery_guard_rejects_overly_slow_candidate_settle_mutation",
            "test_v32_src4382_explicit_input_preempts_autodetect_and_converges_route",
            "test_v32_src4382_manual_digital_input_primes_default_receiver_route",
            "test_v32_src4382_fixed_input_goes_quiet_after_route_converges",
            "test_v32_src4382_autodetect_mute_unmute_remain_responsive",
            "test_v32_src4382_autodetect_standby_wake_remain_responsive",
            "test_v32_src4382_autodetect_preset_change_remains_responsive",
            "test_v32_src4382_nack_does_not_block_volume_command",
            "test_v171_v32_src4382_autodetect_dual_main_chain_soak_stays_responsive",
            "test_v32_lx521_a_b_payloads_reach_each_main_tas3108",
        ),
    }


def _selected_phase_payloads(runner: ModuleType, bug_ids: list[str]) -> list[dict[str, str]]:
    return [{"name": phase.name} for phase in runner._selected_phases([], bug_ids)]


def _phase_results_for_bugs(
    runner: ModuleType,
    bug_ids: list[str],
    *,
    failed_phases: set[str] | None = None,
) -> list[dict[str, int | str]]:
    failed = failed_phases or set()
    return [
        {"phase": phase.name, "returncode": 1 if phase.name in failed else 0}
        for phase in runner._selected_phases([], bug_ids)
    ]


def test_bug_phase_map_covers_all_ledger_bug_ids() -> None:
    runner = _load_runner()
    bug_ids = _active_ledger_bug_ids(_ledger_text())

    assert bug_ids == set(runner.BUG_PHASES), (
        "hardware runner --bug selector must cover every active ledger bug "
        f"without extras; ledger={sorted(bug_ids)!r} runner={sorted(runner.BUG_PHASES)!r}"
    )


def test_bug_phase_map_references_known_phases_or_aliases() -> None:
    runner = _load_runner()
    known = set(runner.PHASE_BY_NAME) | set(runner.PHASE_ALIASES)

    failures: list[str] = []
    for bug_id, phase_names in runner.BUG_PHASES.items():
        for phase_name in phase_names:
            if phase_name not in known:
                failures.append(f"{bug_id}: unknown phase selector {phase_name!r}")

    assert not failures, "\n".join(failures)


def test_every_live_phase_is_required_by_a_ledger_bug() -> None:
    runner = _load_runner()
    required_phases = {
        phase.name
        for bug_id in runner.BUG_PHASES
        for phase in runner._selected_phases([], [bug_id])
    }

    assert [phase.name for phase in runner.PHASES if phase.name not in required_phases] == []


def test_phase_env_contract_covers_live_hardware_opt_in_gates() -> None:
    runner = _load_runner()
    phase_contract = {
        phase.name: {
            "env": dict(phase.env),
            "required_env": set(phase.required_env),
        }
        for phase in runner.PHASES
    }

    assert phase_contract["identity"]["env"]["DLCP_HW_RELEASE_IDENTITY_CONFIRM"] == "1"
    assert phase_contract["settings"]["env"]["DLCP_HW_RELEASE_SETTINGS_CONFIRM"] == "1"
    assert phase_contract["settings"]["required_env"] == {
        "DLCP_HW_EXPECTED_VOLUME_LOW",
        "DLCP_HW_EXPECTED_INPUT",
        "DLCP_HW_EXPECTED_SETUP_PROFILE",
    }
    assert phase_contract["src4382-ad-acoustic"]["env"] == {
        "DLCP_HW_SRC4382_AD_ACOUSTIC_CONFIRM": "1"
    }
    assert phase_contract["src4382-ad-acoustic"]["required_env"] == {
        "DLCP_HW_SRC4382_FIXED_INPUT_AUDIO_OK",
        "DLCP_HW_SRC4382_AUTODETECT_AUDIO_OK",
        "DLCP_HW_SRC4382_USER_ACTIONS_OK",
        "DLCP_HW_SRC4382_SOAK_OK",
    }
    assert phase_contract["front-panel-preset-a"]["env"] == {
        "DLCP_HW_FRONT_PANEL_PRESET_CONFIRM": "1",
        "DLCP_HW_EXPECTED_PRESET": "A",
    }
    assert phase_contract["front-panel-preset-b"]["env"] == {
        "DLCP_HW_FRONT_PANEL_PRESET_CONFIRM": "1",
        "DLCP_HW_EXPECTED_PRESET": "B",
    }
    assert phase_contract["front-panel-standby-wake"]["env"] == {
        "DLCP_HW_FRONT_PANEL_STBY_WAKE_CONFIRM": "1"
    }
    assert phase_contract["preset-standby-wake"]["env"] == {
        "DLCP_HW_REQUIRE_STANDBY_LCD_ZZZ": "1"
    }
    assert phase_contract["ir-receiver-sweep"]["env"] == {
        "DLCP_HW_IR_RECEIVER_SWEEP": "1"
    }
    assert phase_contract["ir-legacy-v16b"]["env"] == {
        "DLCP_HW_IR_LEGACY_STRESS": "1",
        "DLCP_HW_EXPECTED_CONTROL_VERSION": "V1.6b",
    }
    assert phase_contract["ir-legacy-v171"]["env"] == {
        "DLCP_HW_IR_LEGACY_STRESS": "1",
        "DLCP_HW_EXPECTED_CONTROL_VERSION": "V1.71",
    }
    for phase_name in ("diag-layout-pb1", "diag-pb1", "diag-pb2"):
        assert phase_contract[phase_name]["env"]["DLCP_HW_LAYER5_AT_DIAG"] == "1"
    assert phase_contract["diag-pb1"]["env"]["DLCP_HW_LAYER5_REQUIRE_PB1_DATA"] == "1"
    assert phase_contract["diag-pb2"]["env"]["DLCP_HW_LAYER5_REQUIRE_PB2_DATA"] == "1"
    for phase_name, page in (
        ("diag-buttons-pb1", "PB1"),
        ("diag-buttons-pb2", "PB2"),
        ("diag-ir-pb1", "PB1"),
        ("diag-ir-pb2", "PB2"),
    ):
        assert phase_contract[phase_name]["env"]["DLCP_HW_LAYER5_AT_DIAG"] == "1"
        assert phase_contract[phase_name]["env"]["DLCP_HW_EXPECTED_DIAG_PAGE"] == page
    for phase_name in ("diag-buttons-pb1", "diag-buttons-pb2"):
        assert phase_contract[phase_name]["env"]["DLCP_HW_LAYER5_BUTTON_ACTIONS"] == "1"
    for phase_name in ("diag-ir-pb1", "diag-ir-pb2"):
        assert phase_contract[phase_name]["env"]["DLCP_HW_LAYER5_IR_ACTIONS"] == "1"
        assert phase_contract[phase_name]["env"]["DLCP_HW_IR_PROFILE"] == "HYPEX"


def test_diagnostics_live_gates_document_one_second_static_cadence() -> None:
    """BUG-DIAG-01/02: hardware prompts must not relax to a 2 s settle.

    The product requirement is user-visible Diag data within the active
    page's roughly 1 s poll cadence.  A 2 s operator wait can mask a
    PB1/PB2 alternating-poll regression, so keep the runner, hardware
    pytest guidance, runbook, and ledger on the 1 s contract.
    """
    runner = _load_runner()
    for phase_name in (
        "diag-pb1",
        "diag-pb2",
        "diag-buttons-pb1",
        "diag-buttons-pb2",
        "diag-ir-pb1",
        "diag-ir-pb2",
    ):
        manual = runner.PHASE_BY_NAME[phase_name].manual
        assert "1 second" in manual, f"{phase_name} manual text: {manual!r}"
        assert "2 seconds" not in manual, f"{phase_name} manual text: {manual!r}"

    hardware_source = (
        PROJECT_ROOT / "tests" / "hardware" / "test_live_state_transitions.py"
    ).read_text(encoding="utf-8")
    runbook = (PROJECT_ROOT / "docs" / "HARDWARE_TEST.md").read_text(encoding="utf-8")
    v171_release = (PROJECT_ROOT / "docs" / "V171_RELEASE.md").read_text(encoding="utf-8")
    ledger = _ledger_text()

    for text, label in (
        (hardware_source, "hardware live test"),
        (runbook, "hardware runbook"),
        (v171_release, "V1.71 release runbook"),
        (ledger, "bug ledger"),
    ):
        assert "1 second" in text, label
        assert "wait at least 2 seconds" not in text, label
        assert "waited at least 2 seconds" not in text, label
        assert "within about 2 seconds" not in text, label


def test_phase_resource_contract_covers_live_hardware_requirements() -> None:
    runner = _load_runner()
    expected = {
        "identity": ("any", False, False),
        "settings": ("any", False, False),
        "src4382-ad-acoustic": ("pair", False, False),
        "front-panel-preset-a": ("pair", True, False),
        "front-panel-preset-b": ("pair", True, False),
        "front-panel-standby-wake": ("pair", True, False),
        "preset-convergence": ("pair", True, True),
        "rapid-toggle": ("pair", True, True),
        "preset-mute": ("pair", True, True),
        "preset-standby-wake": ("pair", True, True),
        "reconnect-soak": ("pair", True, True),
        "ir-receiver-sweep": ("pair", False, True),
        "ir-legacy-v16b": ("pair", True, True),
        "ir-legacy-v171": ("pair", True, True),
        "diag-layout-pb1": ("pair", True, False),
        "diag-pb1": ("pair", True, False),
        "diag-pb2": ("pair", True, False),
        "diag-buttons-pb1": ("pair", True, False),
        "diag-buttons-pb2": ("pair", True, False),
        "diag-ir-pb1": ("pair", True, True),
        "diag-ir-pb2": ("pair", True, True),
    }

    actual = {
        phase.name: (phase.main_requirement, phase.needs_camera, phase.needs_flipper)
        for phase in runner.PHASES
    }
    assert actual == expected


def test_ir_legacy_stress_cannot_pass_without_real_ir_iteration() -> None:
    source = _hardware_test_sources()[
        "test_live_ir_legacy_command_stress_from_volume"
    ]

    assert 'os.environ.get("DLCP_HW_IR_STRESS_REPEATS", "3")' in source
    assert "repeats = max(1, int(" in source
    assert "for repeat in range(repeats):" in source
    assert 'send_legacy_ir("MUTE")' in source
    assert 'send_legacy_ir("POWER")' in source
    assert 'line2 == f"Active: {current_preset}"' in source


def test_preset_standby_wake_phase_requires_literal_zzz_lcd_evidence() -> None:
    source = _hardware_test_sources()[
        "test_live_preset_standby_wake_timing_sweep_passes_for_configured_delays"
    ]

    assert "DLCP_HW_REQUIRE_STANDBY_LCD_ZZZ" in source
    assert '"--no-standby-blank-fallback"' in source


def test_front_panel_standby_wake_gate_requires_literal_zzz_lcd_evidence() -> None:
    source = _hardware_test_sources()[
        "test_live_manual_front_panel_standby_wake_from_volume"
    ]

    assert "manual_stby_wake_standby_lcd" in source
    assert 'expected="Zzz..."' in source
    assert "manual front-panel STBY must show Zzz LCD" in source


def test_diagnostics_ir_gate_requires_literal_zzz_lcd_evidence() -> None:
    source = _hardware_test_sources()[
        "test_live_diagnostics_page_ir_actions_dispatch_on_real_silicon"
    ]

    assert "diag_ir_after_standby" in source
    assert 'expected="Zzz..."' in source
    assert "IR STANDBY from Diagnostics must show Zzz LCD" in source


def test_ir_legacy_artifact_records_expected_control_hex_identity() -> None:
    hardware_source = (
        PROJECT_ROOT / "tests" / "hardware" / "test_live_state_transitions.py"
    ).read_text(encoding="utf-8")
    source = _hardware_test_sources()[
        "test_live_ir_legacy_command_stress_from_volume"
    ]

    assert "def _expected_control_hex_identity" in hardware_source
    assert "STOCK_CONTROL_HEX_V16B" in hardware_source
    assert "V171_CONTROL_HEX" in hardware_source
    assert "detect_static_hex_control_release_info" in hardware_source
    assert "run_preflight(" in hardware_source
    assert "expected_control_hex = _expected_control_hex_identity(expected_control)" in source
    assert '"expected_control_hex": expected_control_hex' in source
    assert '"payload_crc": preflight["payload_crc"]' in hardware_source
    assert '"payload_sha256": preflight["payload_sha256"]' in hardware_source


def test_runner_dry_run_prints_ir_legacy_control_hex_identity(capsys) -> None:
    runner = _load_runner()

    rc = runner.main(
        [
            "--python",
            "PY",
            "--phase",
            "ir-legacy-v16b",
            "--phase",
            "ir-legacy-v171",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Expected CONTROL hex:" in captured.out
    assert "firmware/stock/control/DLCP Control Firmware V1.6b.hex" in captured.out
    assert "firmware/patched/releases/DLCP_Control_V1.71.hex" in captured.out
    assert "V1.60 / rev <unknown>, crc16=0x2199" in captured.out
    v171_identity = _runner_control_identity(runner, "ir-legacy-v171")
    assert (
        f"{v171_identity['release_short']}, "
        f"crc16=0x{v171_identity['payload_crc']:04X}"
    ) in captured.out

    phase_payloads = {
        phase.name: runner._phase_payload(phase)
        for phase in runner._selected_phases(
            ["ir-legacy-v16b", "ir-legacy-v171"], []
        )
    }
    assert phase_payloads["ir-legacy-v16b"]["expected_control_hex"]["payload_crc"] == 0x2199
    assert (
        phase_payloads["ir-legacy-v171"]["expected_control_hex"]["payload_crc"]
        == v171_identity["payload_crc"]
    )


def test_settings_live_gate_rejects_out_of_range_expected_bytes() -> None:
    hardware_source = (
        PROJECT_ROOT / "tests" / "hardware" / "test_live_state_transitions.py"
    ).read_text(encoding="utf-8")
    source = _hardware_test_sources()[
        "test_live_v32_release_flash_preserves_expected_user_settings"
    ]

    assert "def _parse_byte_auto" in hardware_source
    assert "must be a byte value in 0x00..0xFF" in hardware_source
    assert "_parse_byte_auto(" in source
    assert "& 0xFF" not in source


def test_execute_phase_treats_pytest_skip_as_failure(monkeypatch, capsys) -> None:
    runner = _load_runner()

    def fake_subprocess_run(cmd, cwd, env):  # noqa: ANN001
        assert cmd[:3] == ["PY", "-m", "pytest"]
        assert cwd == str(runner.REPO_ROOT)
        assert env["DLCP_HW_RELEASE_IDENTITY_CONFIRM"] == "1"
        junit_path = Path(cmd[cmd.index("--junitxml") + 1])
        junit_path.write_text(
            '<testsuites><testsuite tests="1" skipped="1" failures="0" errors="0" /></testsuites>',
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(runner, "_print_phase", lambda *args, **kwargs: None)

    rc = runner._run_phase(
        runner.PHASE_BY_NAME["identity"],
        "PY",
        (),
        pause=False,
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "skipped without passing a hardware test" in captured.err


def test_ledger_hardware_phase_table_matches_runner_bug_map() -> None:
    runner = _load_runner()
    ledger = _ledger_text()
    section = ledger.split(
        "Hardware phase map for `scripts/run_v171_v32_ledger_hardware_gate.py --bug`:",
        1,
    )[1].split("## Completion Audit", 1)[0]

    documented: dict[str, tuple[str, ...]] = {}
    for line in section.splitlines():
        if not line.startswith("| BUG-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 2, f"unexpected phase-map row shape: {line!r}"
        bug_ids = re.findall(r"BUG-[A-Z0-9-]+", cells[0])
        phase_names = tuple(re.findall(r"`([^`]+)`", cells[1]))
        assert bug_ids, f"phase-map row has no bug id: {line!r}"
        assert phase_names, f"phase-map row has no backtick phase selector: {line!r}"
        for bug_id in bug_ids:
            assert bug_id not in documented, f"duplicate phase-map row for {bug_id}"
            documented[bug_id] = phase_names

    assert documented == runner.BUG_PHASES


def test_ledger_completion_audit_covers_active_bug_ids() -> None:
    ledger = _ledger_text()
    bug_ids = _active_ledger_bug_ids(ledger)
    audit_ids = set(_completion_audit_lines(ledger))

    assert audit_ids == bug_ids
    for bug_id in bug_ids:
        assert f"## {bug_id}:" in ledger, f"missing detail section for {bug_id}"


def test_ledger_active_statuses_use_documented_vocabulary() -> None:
    rows = _active_ledger_rows(_ledger_text())
    allowed = {
        "pending-red",
        "red",
        "fixing",
        "green",
        "done",
        "blocked",
    }

    for bug_id, cells in rows.items():
        assert cells[1] in allowed, f"{bug_id}: unknown status {cells[1]!r}"


def test_ledger_completion_criteria_documents_artifacts_and_stop_condition() -> None:
    ledger = _ledger_text()
    section = ledger.split("Completion criteria for this ledger:", 1)[1].split(
        "## Active Bugs",
        1,
    )[0]

    assert ".venv_ep0/bin/python -m pytest tests/sim -n 16 -q" in section
    assert "artifacts/probes/v171_v32_ledger_gate/preflight_current.json" in section
    assert "bug_..._closure_current.json" in section
    assert (
        ".venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --remaining"
        in section
    )
    assert "artifacts/probes/v171_v32_ledger_gate/artifact_summary_current.json" in section
    assert "no missing, failed, or stale per-bug preflight reports" in section
    assert "no missing or stale" in section
    assert (
        ".venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py "
        "--summarize-artifacts --require-all-ready"
    ) in section
    assert "ready_to_mark_done" in section
    assert (
        ".venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py "
        "--audit-completion --report-json "
        "artifacts/probes/v171_v32_ledger_gate/completion_audit_current.json"
    ) in section
    assert "exits `0`" in section
    assert "completion_checklist" in section
    assert "all_active_bugs_done" in section
    assert "done_rows_have_done_evidence" in section
    assert "hardware_artifacts_ready" in section
    assert "prompt_to_artifact_checklist_ready" in section
    assert "simulator evidence cell" in section
    assert "no blocking reasons" in section


def test_ledger_tracking_rules_document_xfail_and_hardware_transitions() -> None:
    ledger = _ledger_text()
    section = ledger.split("## Tracking Rules", 1)[1]

    assert "Every xfail introduced for this ledger must include the bug ID" in section
    assert "cannot move to `green` while its required test is still xfailed" in section
    assert "cannot move to `done` without the listed hardware confirmation" in section
    assert "source of truth" in section


def test_ledger_documents_runner_stop_condition() -> None:
    ledger = _ledger_text()

    assert (
        ".venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py "
        "--preflight --phase all --report-json "
        "artifacts/probes/v171_v32_ledger_gate/preflight_current.json"
    ) in ledger
    assert "artifacts/probes/v171_v32_ledger_gate/preflight_current.json" in ledger
    assert (
        ".venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py "
        "--audit-completion --report-json "
        "artifacts/probes/v171_v32_ledger_gate/completion_audit_current.json"
    ) in ledger
    assert (
        "FAIL with `BUG-REV-01` done, nine rows still `green`, and\n"
        "`BUG-SRC4382-AD-01` still `blocked`"
    ) in ledger
    assert "artifacts/probes/v171_v32_ledger_gate/completion_audit_current.json" in ledger
    assert (
        ".venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py "
        "--summarize-artifacts --require-all-ready"
    ) in ledger
    assert "artifacts/probes/v171_v32_ledger_gate/artifact_summary_current.json" in ledger


def test_ledger_top_level_dates_stay_in_sync() -> None:
    ledger = _ledger_text()
    last_updated = re.search(r"^Last updated: (\d{4}-\d{2}-\d{2})$", ledger, re.MULTILINE)
    audit_date = re.search(r"^Audit date: (\d{4}-\d{2}-\d{2})$", ledger, re.MULTILINE)
    verification_date = re.search(
        r"^Green simulator runs through (\d{4}-\d{2}-\d{2}):$",
        ledger,
        re.MULTILINE,
    )

    assert last_updated is not None
    assert audit_date is not None
    assert verification_date is not None
    assert last_updated.group(1) == audit_date.group(1) == verification_date.group(1)


def test_ledger_done_status_matches_completion_audit_evidence() -> None:
    ledger = _ledger_text()
    active = _active_ledger_rows(ledger)
    audit = _completion_audit_lines(ledger)

    for bug_id, cells in active.items():
        status = cells[1]
        has_done_evidence = "DONE:" in audit[bug_id]
        if status == "done":
            assert has_done_evidence, (
                f"{bug_id} is marked done but its completion-audit row lacks "
                "explicit DONE hardware evidence"
            )
        else:
            assert not has_done_evidence, (
                f"{bug_id} has DONE hardware evidence but active-table status is {status!r}"
            )


def test_ledger_sim_evidence_tests_exist_and_are_not_xfailed() -> None:
    ledger = _ledger_text()
    bug_ids = _active_ledger_bug_ids(ledger)
    required = _required_sim_evidence_tests_by_bug()
    assert set(required) == bug_ids

    sim_tests = _sim_test_sources()
    failures: list[str] = []
    for bug_id, test_names in required.items():
        for test_name in test_names:
            record = sim_tests.get(test_name)
            if record is None:
                failures.append(f"{bug_id}: missing sim test {test_name}")
                continue
            path, source = record
            if "xfail" in source:
                failures.append(f"{bug_id}: sim test {test_name} is xfailed in {path}")

    assert not failures, "\n".join(failures)


def test_active_table_lists_all_required_sim_evidence_tests() -> None:
    rows = _active_ledger_rows(_ledger_text())
    failures: list[str] = []

    for bug_id, required_tests in _required_sim_evidence_tests_by_bug().items():
        listed = _test_names_from_required_cell(rows[bug_id][4])
        missing = [test for test in required_tests if test not in listed]
        if missing:
            failures.append(
                f"{bug_id}: active-table Required red test cell misses {missing!r}"
            )

    assert not failures, "\n".join(failures)


def test_ledger_active_table_required_red_tests_resolve() -> None:
    ledger = _ledger_text()
    rows = _active_ledger_rows(ledger)
    sim_tests = _sim_test_sources()
    failures: list[str] = []

    for bug_id, cells in rows.items():
        required_cell = cells[4]
        names = sorted(_test_names_from_required_cell(required_cell))
        if not names:
            failures.append(f"{bug_id}: required red test cell names no concrete test")
            continue
        for name in names:
            record = sim_tests.get(name)
            if record is None:
                failures.append(f"{bug_id}: required red test {name} is missing")
                continue
            path, source = record
            if "xfail" in source:
                failures.append(f"{bug_id}: required red test {name} is xfailed in {path}")

    assert not failures, "\n".join(failures)


def test_each_bug_detail_section_documents_red_test_target() -> None:
    ledger = _ledger_text()
    active_bug_ids = _active_ledger_bug_ids(ledger)
    bug_ids = [
        match.group(1)
        for match in re.finditer(r"^## (BUG-[A-Z0-9-]+):", ledger, re.MULTILINE)
    ]
    failures: list[str] = []

    assert set(bug_ids) == active_bug_ids
    for index, bug_id in enumerate(bug_ids):
        start = ledger.index(f"## {bug_id}:")
        if index + 1 < len(bug_ids):
            end = ledger.index(f"## {bug_ids[index + 1]}:", start + 1)
        else:
            end = ledger.index("## Tracking Rules", start + 1)
        section = ledger[start:end]
        if "Red test target:" not in section:
            failures.append(f"{bug_id}: detail section lacks Red test target")

    assert not failures, "\n".join(failures)


def test_runner_phase_nodes_match_live_hardware_test_file() -> None:
    runner = _load_runner()
    hardware_nodes = _hardware_test_nodes()
    runner_nodes = {phase.node for phase in runner.PHASES if phase.node is not None}

    assert runner_nodes <= hardware_nodes, (
        "runner phase references missing hardware tests: "
        f"{sorted(runner_nodes - hardware_nodes)!r}"
    )
    assert hardware_nodes <= runner_nodes, (
        "hardware tests are not reachable from the ledger runner: "
        f"{sorted(hardware_nodes - runner_nodes)!r}"
    )


def test_bug_selector_expands_aliases_and_deduplicates() -> None:
    runner = _load_runner()

    diag = runner._selected_phases([], ["BUG-DIAG-02"])
    assert [phase.name for phase in diag] == [
        "diag-pb1",
        "diag-pb2",
        "diag-buttons-pb1",
        "diag-buttons-pb2",
        "diag-ir-pb1",
        "diag-ir-pb2",
    ]

    preset_and_rev = runner._selected_phases([], ["BUG-PRESET-01", "BUG-REV-01"])
    assert [phase.name for phase in preset_and_rev] == [
        "identity",
        "front-panel-preset-a",
        "front-panel-preset-b",
    ]


def test_dry_run_bug_selector_prints_per_page_diag_ir_commands(capsys) -> None:
    runner = _load_runner()

    rc = runner.main(["--python", "PY", "--bug", "BUG-DIAG-02"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "[diag-pb1]" in captured.out
    assert "[diag-pb2]" in captured.out
    assert "[diag-buttons-pb1]" in captured.out
    assert "[diag-buttons-pb2]" in captured.out
    assert "[diag-ir-pb1]" in captured.out
    assert "[diag-ir-pb2]" in captured.out
    assert "DLCP_HW_LAYER5_BUTTON_ACTIONS=1" in captured.out
    assert "DLCP_HW_IR_PROFILE=HYPEX" in captured.out
    assert "DLCP_HW_EXPECTED_DIAG_PAGE=PB1" in captured.out
    assert "DLCP_HW_EXPECTED_DIAG_PAGE=PB2" in captured.out


def test_list_mode_prints_bug_phase_selection_without_hardware(capsys) -> None:
    runner = _load_runner()

    rc = runner.main(["--list-phases", "--bug", "BUG-IR-01"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Phase selectors:" in captured.out
    assert "Alias selectors:" in captured.out
    assert "Bug selectors:" in captured.out
    assert "ir-legacy-v16b: Real-IR legacy stress baseline on stock CONTROL V1.6b." in captured.out
    assert "[CONTROL V1.60 / rev <unknown>, crc16=0x2199]" in captured.out
    v171_identity = _runner_control_identity(runner, "ir-legacy-v171")
    assert (
        f"[CONTROL {v171_identity['release_short']}, "
        f"crc16=0x{v171_identity['payload_crc']:04X}]"
    ) in captured.out
    assert "BUG-IR-01: ir-receiver-sweep, ir-legacy-v16b, ir-legacy-v171" in captured.out
    assert "Selected phases:" in captured.out
    assert "ir-receiver-sweep, ir-legacy-v16b, ir-legacy-v171" in captured.out


def test_list_mode_prints_settings_env_requirements_without_hardware(capsys) -> None:
    runner = _load_runner()

    rc = runner.main(["--list-phases", "--bug", "BUG-SETTINGS-01"])

    captured = capsys.readouterr()
    assert rc == 0
    assert (
        "settings: MAIN release flash preserves expected volume/input/profile "
        "settings. (MAIN, env: DLCP_HW_EXPECTED_VOLUME_LOW, "
        "DLCP_HW_EXPECTED_INPUT, DLCP_HW_EXPECTED_SETUP_PROFILE)"
        in captured.out
    )
    assert "BUG-SETTINGS-01: settings, identity, ir-receiver-sweep" in captured.out
    assert "settings, identity, ir-receiver-sweep" in captured.out


def test_remaining_mode_prints_non_done_bug_closure_commands(capsys) -> None:
    runner = _load_runner()

    rc = runner.main(["--remaining", "--python", "PY"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Remaining ledger bugs:" in captured.out
    for bug_id, cells in _active_ledger_rows(_ledger_text()).items():
        if cells[1] == "done":
            assert bug_id not in captured.out
            continue
        safe_bug = bug_id.lower().replace("-", "_")
        assert f"{bug_id} [{cells[1]}]" in captured.out
        assert f"{safe_bug}_preflight_current.json" in captured.out
        assert f"{safe_bug}_closure_current.json" in captured.out
    assert "--preflight --bug BUG-DIAG-01" in captured.out
    assert "bug_diag_01_preflight_current.json" in captured.out
    assert (
        "PY scripts/run_v171_v32_ledger_hardware_gate.py --execute --keep-going "
        "--bug BUG-DIAG-01 --require-bug-closed BUG-DIAG-01"
    ) in captured.out
    assert "bug_diag_01_closure_current.json" in captured.out
    assert "combined:" in captured.out
    assert "remaining_preflight_current.json" in captured.out
    assert "remaining_closure_current.json" in captured.out
    assert "--mirror-selected-bug-reports" in captured.out
    assert "manual evidence:" in captured.out
    assert "expected firmware:" in captured.out
    for label, value in _src4382_expected_firmware_payload().items():
        assert f"{label}: {value}" in captured.out
    assert "PY scripts/run_v171_v32_ledger_hardware_gate.py --src4382-manual-evidence" in captured.out
    assert (
        "artifacts/probes/v171_v32_ledger_gate/"
        "bug_src4382_ad_01_manual_evidence.md"
    ) in captured.out
    assert (
        "PY scripts/validate_src4382_manual_evidence.py "
        "artifacts/probes/v171_v32_ledger_gate/"
        "bug_src4382_ad_01_manual_evidence.md"
    ) in captured.out
    assert (
        "expected CONTROL ir-legacy-v16b: "
        "firmware/stock/control/DLCP Control Firmware V1.6b.hex "
        "(V1.60 / rev <unknown>, crc16=0x2199)"
    ) in captured.out
    runner = _load_runner()
    v171_identity = _runner_control_identity(runner, "ir-legacy-v171")
    assert (
        "expected CONTROL ir-legacy-v171: "
        "firmware/patched/releases/DLCP_Control_V1.71.hex "
        f"({v171_identity['release_short']}, "
        f"crc16=0x{v171_identity['payload_crc']:04X})"
    ) in captured.out


def test_remaining_mode_filters_explicit_done_bug(capsys) -> None:
    runner = _load_runner()

    rc = runner.main(["--remaining", "--bug", "BUG-REV-01", "--python", "PY"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "No remaining non-done ledger bugs." in captured.out
    assert "BUG-REV-01" not in captured.out


def test_remaining_mode_report_json_records_commands(tmp_path) -> None:
    runner = _load_runner()
    report_path = tmp_path / "remaining-report.json"

    rc = runner.main(
        [
            "--remaining",
            "--bug",
            "BUG-DIAG-01",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )

    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"]["remaining"] is True
    assert report["remaining_plan"]["bugs"] == ["BUG-DIAG-01"]
    assert report["remaining_plan"]["phases"] == [
        "diag-layout-pb1",
        "diag-pb1",
        "diag-pb2",
    ]
    assert report["remaining_plan"]["required_env"] == []
    assert (
        "remaining_preflight_current.json"
        in report["remaining_plan"]["preflight_shell_command"]
    )
    assert (
        "remaining_closure_current.json"
        in report["remaining_plan"]["execute_shell_command"]
    )
    assert "--mirror-selected-bug-reports" in report["remaining_plan"][
        "execute_shell_command"
    ]
    assert report["remaining_bugs"] == [
        {
            "bug": "BUG-DIAG-01",
            "status": "green",
            "phases": ["diag-layout-pb1", "diag-pb1", "diag-pb2"],
            "required_env": [],
            "preflight_report": (
                "artifacts/probes/v171_v32_ledger_gate/"
                "bug_diag_01_preflight_current.json"
            ),
            "closure_report": (
                "artifacts/probes/v171_v32_ledger_gate/"
                "bug_diag_01_closure_current.json"
            ),
            "preflight": [
                "PY",
                "scripts/run_v171_v32_ledger_hardware_gate.py",
                "--preflight",
                "--bug",
                "BUG-DIAG-01",
                "--report-json",
                "artifacts/probes/v171_v32_ledger_gate/"
                "bug_diag_01_preflight_current.json",
            ],
            "preflight_shell_command": (
                "PY scripts/run_v171_v32_ledger_hardware_gate.py "
                "--preflight --bug BUG-DIAG-01 --report-json "
                "artifacts/probes/v171_v32_ledger_gate/"
                "bug_diag_01_preflight_current.json"
            ),
            "execute": [
                "PY",
                "scripts/run_v171_v32_ledger_hardware_gate.py",
                "--execute",
                "--keep-going",
                "--bug",
                "BUG-DIAG-01",
                "--require-bug-closed",
                "BUG-DIAG-01",
                "--report-json",
                "artifacts/probes/v171_v32_ledger_gate/"
                "bug_diag_01_closure_current.json",
            ],
            "execute_shell_command": (
                "PY scripts/run_v171_v32_ledger_hardware_gate.py "
                "--execute --keep-going --bug BUG-DIAG-01 "
                "--require-bug-closed BUG-DIAG-01 --report-json "
                "artifacts/probes/v171_v32_ledger_gate/"
                "bug_diag_01_closure_current.json"
            ),
        }
    ]


def test_src4382_manual_evidence_mode_prints_artifact_and_commands(
    monkeypatch,
    capsys,
) -> None:
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "_src4382_manual_evidence_status",
        lambda: (
            "manual_evidence_missing",
            ["evidence file does not exist: test SRC4382 evidence"],
        ),
    )

    rc = runner.main(["--src4382-manual-evidence", "--python", "PY"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "SRC4382 Auto Detect manual evidence:" in captured.out
    assert "BUG-SRC4382-AD-01" in captured.out
    assert "src4382-ad-acoustic" in captured.out
    assert "two visible V3.2 MAIN HID devices (left + right)" in captured.out
    assert "CONTROL V1.71:" in captured.out
    assert (
        "scripts/flash_control_safe.sh --hex "
        "firmware/patched/releases/DLCP_Control_V1.71.hex --preflight-only"
        in captured.out
    )
    assert (
        "scripts/flash_control_safe.sh --hex "
        "firmware/patched/releases/DLCP_Control_V1.71.hex"
        in captured.out
    )
    assert "MAIN V3.2:" in captured.out
    assert "PY scripts/dlcp_v32_release_flash.py --left" in captured.out
    assert "PY scripts/dlcp_v32_release_flash.py --right" in captured.out
    assert "docs/SRC4382_AD_MANUAL_EVIDENCE_TEMPLATE.md" in captured.out
    assert (
        "artifacts/probes/v171_v32_ledger_gate/"
        "bug_src4382_ad_01_manual_evidence.md"
    ) in captured.out
    assert "expected firmware fields:" in captured.out
    for label, value in _src4382_expected_firmware_payload().items():
        assert f"{label}: {value}" in captured.out
    assert "current evidence status: manual_evidence_missing" in captured.out
    assert "current evidence errors:" in captured.out
    assert "evidence file does not exist: test SRC4382 evidence" in captured.out
    assert (
        "PY scripts/validate_src4382_manual_evidence.py "
        "artifacts/probes/v171_v32_ledger_gate/"
        "bug_src4382_ad_01_manual_evidence.md"
    ) in captured.out
    assert "DLCP_HW_SRC4382_AD_ACOUSTIC_CONFIRM=1" in captured.out
    assert "DLCP_HW_SRC4382_FIXED_INPUT_AUDIO_OK=1" in captured.out
    assert "DLCP_HW_SRC4382_AUTODETECT_AUDIO_OK=1" in captured.out
    assert "DLCP_HW_SRC4382_USER_ACTIONS_OK=1" in captured.out
    assert "DLCP_HW_SRC4382_SOAK_OK=1" in captured.out
    assert (
        "PY scripts/run_v171_v32_ledger_hardware_gate.py --preflight "
        "--bug BUG-SRC4382-AD-01"
    ) in captured.out
    assert (
        "PY scripts/run_v171_v32_ledger_hardware_gate.py --execute --keep-going "
        "--bug BUG-SRC4382-AD-01 --require-bug-closed BUG-SRC4382-AD-01"
    ) in captured.out
    assert "--summarize-artifacts" in captured.out
    assert "--audit-completion" in captured.out


def test_src4382_manual_evidence_mode_report_json_records_payload(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "_src4382_manual_evidence_status",
        lambda: (
            "manual_evidence_missing",
            ["evidence file does not exist: test SRC4382 evidence"],
        ),
    )
    report_path = tmp_path / "src4382-manual-evidence-report.json"

    rc = runner.main(
        [
            "--src4382-manual-evidence",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )

    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"]["src4382_manual_evidence"] is True
    payload = report["src4382_manual_evidence"]
    assert payload["bug"] == "BUG-SRC4382-AD-01"
    assert payload["phase"] == "src4382-ad-acoustic"
    assert payload["main_requirement"] == "pair"
    assert payload["template"] == "docs/SRC4382_AD_MANUAL_EVIDENCE_TEMPLATE.md"
    assert (
        payload["manual_evidence"]
        == "artifacts/probes/v171_v32_ledger_gate/"
        "bug_src4382_ad_01_manual_evidence.md"
    )
    assert payload["manual_evidence_status"] == "manual_evidence_missing"
    assert payload["manual_evidence_errors"] == [
        "evidence file does not exist: test SRC4382 evidence"
    ]
    assert payload["expected_firmware"] == _src4382_expected_firmware_payload()
    assert payload["required_env"] == [
        "DLCP_HW_SRC4382_FIXED_INPUT_AUDIO_OK",
        "DLCP_HW_SRC4382_AUTODETECT_AUDIO_OK",
        "DLCP_HW_SRC4382_USER_ACTIONS_OK",
        "DLCP_HW_SRC4382_SOAK_OK",
    ]
    assert (
        "DLCP_HW_SRC4382_AD_ACOUSTIC_CONFIRM=1"
        in payload["execute_shell_command"]
    )
    assert (
        "--require-bug-closed BUG-SRC4382-AD-01"
        in payload["execute_shell_command"]
    )
    assert payload["control_flash"] == [
        [
            "scripts/flash_control_safe.sh",
            "--hex",
            "firmware/patched/releases/DLCP_Control_V1.71.hex",
            "--preflight-only",
        ],
        [
            "scripts/flash_control_safe.sh",
            "--hex",
            "firmware/patched/releases/DLCP_Control_V1.71.hex",
        ],
    ]
    assert payload["control_flash_shell_commands"] == [
        (
            "scripts/flash_control_safe.sh --hex "
            "firmware/patched/releases/DLCP_Control_V1.71.hex --preflight-only"
        ),
        (
            "scripts/flash_control_safe.sh --hex "
            "firmware/patched/releases/DLCP_Control_V1.71.hex"
        ),
    ]
    assert payload["flash"] == [
        ["PY", "scripts/dlcp_v32_release_flash.py", "--left"],
        ["PY", "scripts/dlcp_v32_release_flash.py", "--right"],
    ]
    assert payload["flash_shell_commands"] == [
        "PY scripts/dlcp_v32_release_flash.py --left",
        "PY scripts/dlcp_v32_release_flash.py --right",
    ]
    assert payload["validator"] == [
        "PY",
        "scripts/validate_src4382_manual_evidence.py",
        "artifacts/probes/v171_v32_ledger_gate/"
        "bug_src4382_ad_01_manual_evidence.md",
    ]


def test_remaining_combined_plan_keeps_v16b_baseline_next_to_v171_restore(
    tmp_path,
) -> None:
    runner = _load_runner()
    report_path = tmp_path / "remaining-combined-report.json"

    rc = runner.main(
        [
            "--remaining",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )

    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    plan = report["remaining_plan"]
    assert plan["bugs"] == [
        "BUG-DIAG-01",
        "BUG-DIAG-02",
        "BUG-IR-01",
        "BUG-IR-02",
        "BUG-PRESET-01",
        "BUG-PRESET-02",
        "BUG-PRESET-03",
        "BUG-SETTINGS-01",
        "BUG-SRC4382-AD-01",
        "BUG-STDBY-01",
    ]
    assert plan["phases"] == [
        "diag-layout-pb1",
        "diag-pb1",
        "diag-pb2",
        "diag-buttons-pb1",
        "diag-buttons-pb2",
        "diag-ir-pb1",
        "diag-ir-pb2",
        "ir-receiver-sweep",
        "ir-legacy-v16b",
        "ir-legacy-v171",
        "preset-mute",
        "preset-standby-wake",
        "identity",
        "front-panel-preset-a",
        "front-panel-preset-b",
        "rapid-toggle",
        "preset-convergence",
        "settings",
        "src4382-ad-acoustic",
        "front-panel-standby-wake",
        "reconnect-soak",
    ]
    assert (
        plan["phases"].index("ir-legacy-v171")
        == plan["phases"].index("ir-legacy-v16b") + 1
    )
    assert plan["required_env"] == [
        "DLCP_HW_EXPECTED_INPUT",
        "DLCP_HW_EXPECTED_SETUP_PROFILE",
        "DLCP_HW_EXPECTED_VOLUME_LOW",
        "DLCP_HW_SRC4382_AUTODETECT_AUDIO_OK",
        "DLCP_HW_SRC4382_FIXED_INPUT_AUDIO_OK",
        "DLCP_HW_SRC4382_SOAK_OK",
        "DLCP_HW_SRC4382_USER_ACTIONS_OK",
    ]
    assert plan["expected_control_hex"]["ir-legacy-v16b"]["payload_crc"] == 0x2199
    v171_identity = _runner_control_identity(runner, "ir-legacy-v171")
    assert (
        plan["expected_control_hex"]["ir-legacy-v171"]["payload_crc"]
        == v171_identity["payload_crc"]
    )
    ir_bug = next(item for item in report["remaining_bugs"] if item["bug"] == "BUG-IR-01")
    assert ir_bug["expected_control_hex"]["ir-legacy-v16b"]["payload_crc"] == 0x2199
    assert (
        ir_bug["expected_control_hex"]["ir-legacy-v171"]["payload_crc"]
        == v171_identity["payload_crc"]
    )
    settings_bug = next(
        item for item in report["remaining_bugs"] if item["bug"] == "BUG-SETTINGS-01"
    )
    assert settings_bug["required_env"] == [
        "DLCP_HW_EXPECTED_INPUT",
        "DLCP_HW_EXPECTED_SETUP_PROFILE",
        "DLCP_HW_EXPECTED_VOLUME_LOW",
    ]
    src4382_bug = next(
        item for item in report["remaining_bugs"] if item["bug"] == "BUG-SRC4382-AD-01"
    )
    assert src4382_bug["required_env"] == [
        "DLCP_HW_SRC4382_AUTODETECT_AUDIO_OK",
        "DLCP_HW_SRC4382_FIXED_INPUT_AUDIO_OK",
        "DLCP_HW_SRC4382_SOAK_OK",
        "DLCP_HW_SRC4382_USER_ACTIONS_OK",
    ]
    assert src4382_bug["manual_evidence"] == {
        "template": "docs/SRC4382_AD_MANUAL_EVIDENCE_TEMPLATE.md",
        "manual_evidence": (
            "artifacts/probes/v171_v32_ledger_gate/"
            "bug_src4382_ad_01_manual_evidence.md"
        ),
        "expected_firmware": _src4382_expected_firmware_payload(),
        "helper": [
            "PY",
            "scripts/run_v171_v32_ledger_hardware_gate.py",
            "--src4382-manual-evidence",
        ],
        "helper_shell_command": (
            "PY scripts/run_v171_v32_ledger_hardware_gate.py "
            "--src4382-manual-evidence"
        ),
        "validator": [
            "PY",
            "scripts/validate_src4382_manual_evidence.py",
            "artifacts/probes/v171_v32_ledger_gate/"
            "bug_src4382_ad_01_manual_evidence.md",
        ],
        "validator_shell_command": (
            "PY scripts/validate_src4382_manual_evidence.py "
            "artifacts/probes/v171_v32_ledger_gate/"
            "bug_src4382_ad_01_manual_evidence.md"
        ),
    }
    assert "--mirror-selected-bug-reports" in plan["execute_shell_command"]
    assert "--require-bug-closed BUG-STDBY-01" in plan["execute_shell_command"]


def test_mirror_selected_bug_reports_writes_stable_preflight_and_closure_reports(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_runner()
    main_preflight = tmp_path / "preflight-main.json"
    mirror_preflight = tmp_path / "bug_diag_01_preflight_current.json"
    main_closure = tmp_path / "closure-main.json"
    mirror_closure = tmp_path / "bug_diag_01_closure_current.json"
    monkeypatch.setattr(
        runner,
        "_stable_bug_preflight_report_path",
        lambda bug_id: mirror_preflight,
    )
    monkeypatch.setattr(
        runner,
        "_stable_bug_closure_report_path",
        lambda bug_id: mirror_closure,
    )
    monkeypatch.setattr(
        runner,
        "_preflight_with_report",
        lambda phases: (0, {"status": "PASS", "failures": []}),
    )
    monkeypatch.setattr(runner, "_run_phase", lambda *args, **kwargs: 0)

    preflight_rc = runner.main(
        [
            "--preflight",
            "--bug",
            "BUG-DIAG-01",
            "--mirror-selected-bug-reports",
            "--python",
            "PY",
            "--report-json",
            str(main_preflight),
        ]
    )
    closure_rc = runner.main(
        [
            "--execute",
            "--no-pause",
            "--bug",
            "BUG-DIAG-01",
            "--require-bug-closed",
            "BUG-DIAG-01",
            "--mirror-selected-bug-reports",
            "--python",
            "PY",
            "--report-json",
            str(main_closure),
        ]
    )

    assert preflight_rc == 0
    assert closure_rc == 0
    assert json.loads(main_preflight.read_text(encoding="utf-8")) == json.loads(
        mirror_preflight.read_text(encoding="utf-8")
    )
    mirrored_closure = json.loads(mirror_closure.read_text(encoding="utf-8"))
    assert mirrored_closure == json.loads(main_closure.read_text(encoding="utf-8"))
    assert mirrored_closure["bug_closure"]["BUG-DIAG-01"]["status"] == "passed"


def test_combined_mirrored_reports_make_multiple_bug_rows_ready(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_runner()
    evidence_identity = {"schema": 2, "test": "current"}
    preflight_paths = {
        bug_id: tmp_path / f"{bug_id.lower().replace('-', '_')}_preflight_current.json"
        for bug_id in ("BUG-DIAG-01", "BUG-DIAG-02")
    }
    closure_paths = {
        bug_id: tmp_path / f"{bug_id.lower().replace('-', '_')}_closure_current.json"
        for bug_id in ("BUG-DIAG-01", "BUG-DIAG-02")
    }
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-REV-01": "done", "BUG-DIAG-01": "green", "BUG-DIAG-02": "green"},
    )
    monkeypatch.setattr(
        runner,
        "_current_evidence_identity",
        lambda: evidence_identity,
    )
    monkeypatch.setattr(
        runner,
        "_stable_bug_preflight_report_path",
        lambda bug_id: preflight_paths[bug_id],
    )
    monkeypatch.setattr(
        runner,
        "_stable_bug_closure_report_path",
        lambda bug_id: closure_paths[bug_id],
    )
    monkeypatch.setattr(
        runner,
        "_preflight_with_report",
        lambda phases: (0, {"status": "PASS", "failures": []}),
    )
    monkeypatch.setattr(runner, "_run_phase", lambda *args, **kwargs: 0)

    preflight_rc = runner.main(
        [
            "--preflight",
            "--bug",
            "BUG-DIAG-01",
            "--bug",
            "BUG-DIAG-02",
            "--mirror-selected-bug-reports",
            "--python",
            "PY",
            "--report-json",
            str(tmp_path / "remaining_preflight_current.json"),
        ]
    )
    closure_rc = runner.main(
        [
            "--execute",
            "--no-pause",
            "--bug",
            "BUG-DIAG-01",
            "--bug",
            "BUG-DIAG-02",
            "--require-bug-closed",
            "BUG-DIAG-01",
            "--require-bug-closed",
            "BUG-DIAG-02",
            "--mirror-selected-bug-reports",
            "--python",
            "PY",
            "--report-json",
            str(tmp_path / "remaining_closure_current.json"),
        ]
    )

    assert preflight_rc == 0
    assert closure_rc == 0
    summary = runner._artifact_summary_payload("PY")
    assert summary["ready_to_mark_done"] == ["BUG-DIAG-01", "BUG-DIAG-02"]
    assert summary["not_ready_bugs"] == []
    rows = {row["bug"]: row for row in summary["rows"]}
    assert rows["BUG-DIAG-01"]["artifact_status"] == "passed"
    assert rows["BUG-DIAG-02"]["artifact_status"] == "passed"
    assert rows["BUG-DIAG-01"]["closure_report"] == str(closure_paths["BUG-DIAG-01"])
    assert rows["BUG-DIAG-02"]["closure_report"] == str(closure_paths["BUG-DIAG-02"])


def test_combined_report_can_make_unaffected_bug_ready_when_another_bug_fails(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_runner()
    evidence_identity = {"schema": 2, "test": "current"}
    closure = tmp_path / "combined_closure.json"
    preflight = tmp_path / "combined_preflight.json"
    selected_phase_payloads = _selected_phase_payloads(
        runner,
        ["BUG-DIAG-01", "BUG-DIAG-02"],
    )
    failed_diag_02_phases = {"diag-buttons-pb1"}
    preflight.write_text(
        json.dumps(
            {
                "evidence_identity": evidence_identity,
                "selected_phases": selected_phase_payloads,
                "preflight": {"status": "PASS", "failures": []},
            }
        ),
        encoding="utf-8",
    )
    closure.write_text(
        json.dumps(
            {
                "evidence_identity": evidence_identity,
                "final_rc": 1,
                "selected_phases": selected_phase_payloads,
                "phase_results": _phase_results_for_bugs(
                    runner,
                    ["BUG-DIAG-01", "BUG-DIAG-02"],
                    failed_phases=failed_diag_02_phases,
                ),
                "bug_closure": {
                    "BUG-DIAG-01": {"status": "passed"},
                    "BUG-DIAG-02": {"status": "failed"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-REV-01": "done", "BUG-DIAG-01": "green", "BUG-DIAG-02": "green"},
    )
    monkeypatch.setattr(
        runner,
        "_current_evidence_identity",
        lambda: evidence_identity,
    )
    monkeypatch.setattr(
        runner,
        "_remaining_bug_payloads",
        lambda python, selected_bug_names: [
            {
                "bug": "BUG-DIAG-01",
                "status": "green",
                "preflight_report": str(preflight),
                "closure_report": str(closure),
            },
            {
                "bug": "BUG-DIAG-02",
                "status": "green",
                "preflight_report": str(preflight),
                "closure_report": str(closure),
            },
        ],
    )

    summary = runner._artifact_summary_payload("PY")

    assert summary["ready_to_mark_done"] == ["BUG-DIAG-01"]
    assert summary["not_ready_bugs"] == ["BUG-DIAG-02"]
    rows = {row["bug"]: row for row in summary["rows"]}
    assert rows["BUG-DIAG-01"]["artifact_status"] == "passed"
    assert rows["BUG-DIAG-01"]["final_rc"] == 1
    assert rows["BUG-DIAG-02"]["artifact_status"] == "failed"


def test_audit_completion_fails_until_every_ledger_bug_is_done(tmp_path, capsys) -> None:
    runner = _load_runner()
    report_path = tmp_path / "completion-audit.json"

    rc = runner.main(
        [
            "--audit-completion",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )

    captured = capsys.readouterr()
    assert "Completion audit: NOT COMPLETE" in captured.out
    assert "done: BUG-REV-01" in captured.out
    assert "BUG-DIAG-01 [green]" in captured.out
    assert "artifact readiness:" in captured.out
    assert "FAIL all_active_bugs_done" in captured.out
    assert "PASS done_rows_have_done_evidence" in captured.out
    assert "FAIL hardware_artifacts_ready" in captured.out
    assert "PY scripts/run_v171_v32_ledger_hardware_gate.py --remaining" in captured.out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    audit = report["completion_audit"]
    assert report["mode"]["audit_completion"] is True
    assert audit["complete"] is False
    assert audit["status_counts"] == {"blocked": 1, "done": 1, "green": 9}
    assert audit["done_bugs"] == ["BUG-REV-01"]
    assert audit["done_without_evidence"] == []
    assert audit["done_with_weak_evidence"] == []
    assert audit["completion_checklist"] == [
        {
            "id": "all_active_bugs_done",
            "passed": False,
            "evidence": "10 active rows are not done",
        },
        {
            "id": "done_rows_have_done_evidence",
            "passed": True,
            "evidence": "every done row has DONE evidence",
        },
        {
            "id": "hardware_artifacts_ready",
            "passed": False,
            "evidence": (
                "not ready: BUG-DIAG-01, BUG-DIAG-02, BUG-IR-01, BUG-IR-02, "
                "BUG-PRESET-01, BUG-PRESET-02, BUG-PRESET-03, "
                "BUG-SETTINGS-01, BUG-SRC4382-AD-01, BUG-STDBY-01"
            ),
        },
        {
            "id": "prompt_to_artifact_checklist_ready",
            "passed": False,
            "evidence": (
                "blocked: BUG-DIAG-01, BUG-DIAG-02, BUG-IR-01, BUG-IR-02, "
                "BUG-PRESET-01, BUG-PRESET-02, BUG-PRESET-03, "
                "BUG-SETTINGS-01, BUG-SRC4382-AD-01, BUG-STDBY-01"
            ),
        },
    ]
    prompt_checklist = audit["prompt_to_artifact_checklist"]
    assert prompt_checklist["complete"] is False
    assert prompt_checklist["objective"].startswith(
        "each active implementation bug has simulator evidence"
    )
    assert prompt_checklist["sim_gate"] == {
        "command": ".venv_ep0/bin/python -m pytest tests/sim -n 16 -q",
        "guards": [
            (
                "tests/sim/test_v171_v32_ledger_hardware_gate.py::"
                "test_active_table_lists_all_required_sim_evidence_tests"
            ),
            (
                "tests/sim/test_v171_v32_ledger_hardware_gate.py::"
                "test_every_live_phase_is_required_by_a_ledger_bug"
            ),
        ],
    }
    active_rows = _active_ledger_rows(_ledger_text())
    prompt_bugs = {
        item["bug"]: item for item in prompt_checklist["bugs"]
    }
    assert set(prompt_bugs) == set(active_rows)
    assert prompt_bugs["BUG-REV-01"]["ready_to_mark_done"] is True
    assert prompt_bugs["BUG-REV-01"]["blocking_reasons"] == []
    assert "DONE:" in prompt_bugs["BUG-REV-01"]["done_evidence"]
    assert prompt_checklist["blocking_bugs"] == [
        {
            "bug": bug_id,
            "blocking_reasons": [
                "ledger_status_not_done",
                "hardware_artifacts_not_ready",
            ],
        }
        for bug_id in sorted(active_rows)
        if bug_id != "BUG-REV-01"
    ]
    assert prompt_bugs["BUG-IR-02"]["hardware_phases"] == [
        "diag-ir-pb1",
        "diag-ir-pb2",
        "preset-mute",
        "preset-standby-wake",
    ]
    for bug_id, cells in active_rows.items():
        bug_prompt = prompt_bugs[bug_id]
        assert bug_prompt["ledger_status"] == cells[1]
        assert bug_prompt["required_sim_evidence"] == cells[4]
        if bug_id == "BUG-REV-01":
            continue
        assert bug_prompt["ready_to_mark_done"] is False
        assert bug_prompt["blocking_reasons"] == [
            "ledger_status_not_done",
            "hardware_artifacts_not_ready",
        ]
    assert "artifact_summary" in audit
    assert {
        row["bug"] for row in audit["artifact_summary"]["rows"]
    } == set(active_rows)
    remaining_bug_ids = {item["bug"] for item in audit["remaining_bugs"]}
    assert remaining_bug_ids == {
        bug_id for bug_id, cells in active_rows.items() if cells[1] != "done"
    }
    assert {item["status"] for item in audit["remaining_bugs"]} == {
        "blocked",
        "green",
    }
    for item in audit["remaining_bugs"]:
        safe_bug = item["bug"].lower().replace("-", "_")
        assert item["preflight_report"] == (
            "artifacts/probes/v171_v32_ledger_gate/"
            f"{safe_bug}_preflight_current.json"
        )
        assert item["closure_report"] == (
            "artifacts/probes/v171_v32_ledger_gate/"
            f"{safe_bug}_closure_current.json"
        )
        assert f"--report-json {item['preflight_report']}" in item[
            "preflight_shell_command"
        ]
        assert f"--report-json {item['closure_report']}" in item[
            "execute_shell_command"
        ]
        assert f"--bug {item['bug']} --require-bug-closed {item['bug']}" in item[
            "execute_shell_command"
        ]


def test_audit_completion_passes_when_all_ledger_bugs_are_done(
    monkeypatch,
    capsys,
) -> None:
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {bug_id: "done" for bug_id in runner.BUG_PHASES},
    )
    monkeypatch.setattr(
        runner,
        "_completion_audit_evidence_lines",
        lambda: {
            bug_id: "DONE: `hardware-command` -> `1 passed`"
            for bug_id in runner.BUG_PHASES
        },
    )
    monkeypatch.setattr(
        runner,
        "_src4382_manual_evidence_status",
        lambda: ("passed", []),
    )

    rc = runner.main(["--audit-completion", "--python", "PY"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Completion audit: COMPLETE" in captured.out
    assert "done: " in captured.out
    assert "remaining:" not in captured.out
    assert "PASS all_active_bugs_done" in captured.out
    assert "PASS done_rows_have_done_evidence" in captured.out
    assert "PASS hardware_artifacts_ready" in captured.out
    assert "PASS prompt_to_artifact_checklist_ready" in captured.out


def test_audit_completion_fails_if_src4382_done_row_lacks_valid_manual_evidence(
    monkeypatch,
    capsys,
) -> None:
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-SRC4382-AD-01": "done"},
    )
    monkeypatch.setattr(
        runner,
        "_completion_audit_evidence_lines",
        lambda: {
            "BUG-SRC4382-AD-01": (
                "DONE: `artifacts/probes/v171_v32_ledger_gate/"
                "bug_src4382_ad_01_manual_evidence.md` -> `pass`"
            )
        },
    )
    monkeypatch.setattr(
        runner,
        "_src4382_manual_evidence_status",
        lambda: (
            "manual_evidence_missing",
            ["evidence file does not exist: manual SRC4382 evidence"],
        ),
    )

    rc = runner.main(["--audit-completion", "--python", "PY"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Completion audit: NOT COMPLETE" in captured.out
    assert (
        "done rows with invalid manual evidence: BUG-SRC4382-AD-01"
        in captured.out
    )
    assert "FAIL done_rows_have_done_evidence" in captured.out
    assert "invalid manual evidence: BUG-SRC4382-AD-01" in captured.out
    audit = runner._completion_audit_payload("PY")
    assert audit["done_with_invalid_manual_evidence"] == ["BUG-SRC4382-AD-01"]
    assert audit["done_manual_evidence_errors"] == {
        "BUG-SRC4382-AD-01": [
            "evidence file does not exist: manual SRC4382 evidence"
        ]
    }
    src4382_prompt = audit["prompt_to_artifact_checklist"]["bugs"][0]
    assert src4382_prompt["bug"] == "BUG-SRC4382-AD-01"
    assert src4382_prompt["ready_to_mark_done"] is False
    assert src4382_prompt["blocking_reasons"] == [
        "done_row_invalid_manual_evidence"
    ]


def test_audit_completion_fails_if_prompt_to_artifact_checklist_blocks(
    monkeypatch,
) -> None:
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-REV-01": "done"},
    )
    monkeypatch.setattr(
        runner,
        "_active_ledger_rows",
        lambda: {"BUG-REV-01": ["BUG-REV-01", "done", "MAIN", "symptom"]},
    )
    monkeypatch.setattr(
        runner,
        "_completion_audit_evidence_lines",
        lambda: {"BUG-REV-01": "DONE: `hardware-command` -> `1 passed`"},
    )

    audit = runner._completion_audit_payload("PY")

    assert audit["complete"] is False
    assert audit["remaining_bugs"] == []
    assert audit["done_without_evidence"] == []
    assert audit["done_with_weak_evidence"] == []
    assert audit["artifact_summary"]["not_ready_bugs"] == []
    assert audit["completion_checklist"] == [
        {
            "id": "all_active_bugs_done",
            "passed": True,
            "evidence": "all active ledger rows are done",
        },
        {
            "id": "done_rows_have_done_evidence",
            "passed": True,
            "evidence": "every done row has DONE evidence",
        },
        {
            "id": "hardware_artifacts_ready",
            "passed": True,
            "evidence": "no hardware artifact readiness gaps",
        },
        {
            "id": "prompt_to_artifact_checklist_ready",
            "passed": False,
            "evidence": "blocked: BUG-REV-01",
        },
    ]
    assert audit["prompt_to_artifact_checklist"]["complete"] is False
    assert audit["prompt_to_artifact_checklist"]["blocking_bugs"] == [
        {
            "bug": "BUG-REV-01",
            "blocking_reasons": ["missing_required_sim_evidence"],
        }
    ]
    rev_prompt = audit["prompt_to_artifact_checklist"]["bugs"][0]
    assert rev_prompt["done_evidence"] == "DONE: `hardware-command` -> `1 passed`"


def test_audit_completion_fails_if_done_rows_have_weak_done_evidence(
    monkeypatch,
    capsys,
) -> None:
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-REV-01": "done"},
    )
    monkeypatch.setattr(
        runner,
        "_completion_audit_evidence_lines",
        lambda: {"BUG-REV-01": "DONE:"},
    )
    monkeypatch.setattr(
        runner,
        "_src4382_manual_evidence_status",
        lambda: ("passed", []),
    )

    rc = runner.main(["--audit-completion", "--python", "PY"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Completion audit: NOT COMPLETE" in captured.out
    assert "done rows with weak DONE evidence: BUG-REV-01" in captured.out
    assert "FAIL done_rows_have_done_evidence" in captured.out
    assert "weak DONE evidence: BUG-REV-01" in captured.out


def test_audit_completion_fails_if_done_rows_lack_done_evidence(
    monkeypatch,
    capsys,
) -> None:
    runner = _load_runner()
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {bug_id: "done" for bug_id in runner.BUG_PHASES},
    )
    monkeypatch.setattr(
        runner,
        "_completion_audit_evidence_lines",
        lambda: {"BUG-REV-01": "DONE:"},
    )

    rc = runner.main(["--audit-completion", "--python", "PY"])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Completion audit: NOT COMPLETE" in captured.out
    assert "done rows missing DONE evidence:" in captured.out
    assert "FAIL done_rows_have_done_evidence" in captured.out
    assert "BUG-DIAG-01" in captured.out


def test_summarize_artifacts_reports_missing_and_passed_closure_reports(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    runner = _load_runner()
    evidence_identity = {"schema": 2, "test": "current"}
    monkeypatch.setattr(
        runner,
        "_current_evidence_identity",
        lambda: evidence_identity,
    )
    selected_passed_phases = _selected_phase_payloads(
        runner,
        ["BUG-DIAG-01", "BUG-IR-01"],
    )
    selected_failed_preflight_phases = _selected_phase_payloads(runner, ["BUG-DIAG-02"])
    passed_report = tmp_path / "bug_diag_01_closure_current.json"
    passed_report.write_text(
        json.dumps(
            {
                "evidence_identity": evidence_identity,
                "final_rc": 0,
                "selected_phases": selected_passed_phases,
                "phase_results": _phase_results_for_bugs(
                    runner,
                    ["BUG-DIAG-01", "BUG-IR-01"],
                ),
                "bug_closure": {
                    "BUG-DIAG-01": {"status": "passed"},
                    "BUG-IR-01": {"status": "passed"},
                },
            }
        ),
        encoding="utf-8",
    )
    passed_preflight = tmp_path / "bug_diag_01_preflight_current.json"
    passed_preflight.write_text(
        json.dumps(
            {
                "evidence_identity": evidence_identity,
                "selected_phases": selected_passed_phases,
                "preflight": {"status": "PASS", "failures": []},
            }
        ),
        encoding="utf-8",
    )
    failed_preflight = tmp_path / "bug_diag_02_preflight_current.json"
    failed_preflight.write_text(
        json.dumps(
            {
                "evidence_identity": evidence_identity,
                "selected_phases": selected_failed_preflight_phases,
                "preflight": {
                    "status": "FAIL",
                    "failures": ["no MAIN HID devices visible"],
                }
            }
        ),
        encoding="utf-8",
    )
    summary_report = tmp_path / "artifact-summary.json"

    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {
            "BUG-REV-01": "done",
            "BUG-DIAG-01": "green",
            "BUG-DIAG-02": "green",
            "BUG-IR-01": "green",
        },
    )
    monkeypatch.setattr(
        runner,
        "_remaining_bug_payloads",
        lambda python, selected_bug_names: [
            {
                "bug": "BUG-DIAG-01",
                "status": "green",
                "preflight_report": str(passed_preflight),
                "closure_report": str(passed_report),
            },
            {
                "bug": "BUG-DIAG-02",
                "status": "green",
                "preflight_report": str(failed_preflight),
                "closure_report": str(tmp_path / "missing.json"),
            },
            {
                "bug": "BUG-IR-01",
                "status": "green",
                "preflight_report": str(tmp_path / "missing_preflight.json"),
                "closure_report": str(passed_report),
            },
        ],
    )

    rc = runner.main(
        [
            "--summarize-artifacts",
            "--require-all-ready",
            "--python",
            "PY",
            "--report-json",
            str(summary_report),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "Closure artifact summary:" in captured.out
    assert "BUG-REV-01 [done]: ledger done" in captured.out
    assert "BUG-DIAG-01 [green]: passed (preflight=PASS" in captured.out
    assert "BUG-DIAG-02 [green]: missing (preflight=FAIL" in captured.out
    assert "BUG-IR-01 [green]: passed_preflight_missing" in captured.out
    assert "Artifact readiness failures:" in captured.err
    report = json.loads(summary_report.read_text(encoding="utf-8"))
    summary = report["artifact_summary"]
    assert report["final_rc"] == 1
    assert report["mode"]["require_all_ready"] is True
    assert summary["ready_to_mark_done"] == ["BUG-DIAG-01"]
    assert summary["not_ready_bugs"] == ["BUG-DIAG-02", "BUG-IR-01"]
    assert summary["missing_reports"] == ["BUG-DIAG-02"]
    rows = {row["bug"]: row for row in summary["rows"]}
    assert rows["BUG-DIAG-01"]["preflight_status"] == "PASS"
    assert rows["BUG-DIAG-01"]["preflight_identity_status"] == "current"
    assert rows["BUG-DIAG-01"]["closure_identity_status"] == "current"
    assert rows["BUG-DIAG-02"]["preflight_status"] == "FAIL"
    assert rows["BUG-DIAG-02"]["preflight_failures"] == [
        "no MAIN HID devices visible"
    ]
    assert rows["BUG-IR-01"]["artifact_status"] == "passed_preflight_missing"
    assert rows["BUG-IR-01"]["preflight_status"] == "missing"


def test_summarize_artifacts_require_all_ready_passes_when_all_green_rows_ready(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_runner()
    evidence_identity = {"schema": 2, "test": "current"}
    monkeypatch.setattr(
        runner,
        "_current_evidence_identity",
        lambda: evidence_identity,
    )
    preflight = tmp_path / "bug_diag_01_preflight_current.json"
    closure = tmp_path / "bug_diag_01_closure_current.json"
    report_path = tmp_path / "artifact-summary-ready.json"
    selected_phases = _selected_phase_payloads(runner, ["BUG-DIAG-01"])
    preflight.write_text(
        json.dumps(
            {
                "evidence_identity": evidence_identity,
                "selected_phases": selected_phases,
                "preflight": {"status": "PASS", "failures": []},
            }
        ),
        encoding="utf-8",
    )
    closure.write_text(
        json.dumps(
            {
                "evidence_identity": evidence_identity,
                "final_rc": 0,
                "selected_phases": selected_phases,
                "phase_results": _phase_results_for_bugs(runner, ["BUG-DIAG-01"]),
                "bug_closure": {"BUG-DIAG-01": {"status": "passed"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-REV-01": "done", "BUG-DIAG-01": "green"},
    )
    monkeypatch.setattr(
        runner,
        "_remaining_bug_payloads",
        lambda python, selected_bug_names: [
            {
                "bug": "BUG-DIAG-01",
                "status": "green",
                "preflight_report": str(preflight),
                "closure_report": str(closure),
            },
        ],
    )

    rc = runner.main(
        [
            "--summarize-artifacts",
            "--require-all-ready",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )

    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = report["artifact_summary"]
    assert summary["ready_to_mark_done"] == ["BUG-DIAG-01"]
    assert summary["not_ready_bugs"] == []


def test_summarize_artifacts_requires_valid_src4382_manual_evidence(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_runner()
    evidence_identity = {"schema": 2, "test": "current"}
    monkeypatch.setattr(
        runner,
        "_current_evidence_identity",
        lambda: evidence_identity,
    )
    evidence = tmp_path / "bug_src4382_ad_01_manual_evidence.md"
    monkeypatch.setattr(
        runner,
        "SRC4382_MANUAL_EVIDENCE_RELATIVE_PATH",
        str(evidence),
    )
    preflight = tmp_path / "bug_src4382_ad_01_preflight_current.json"
    closure = tmp_path / "bug_src4382_ad_01_closure_current.json"
    report_path = tmp_path / "artifact-summary-src4382.json"
    selected_phases = _selected_phase_payloads(runner, ["BUG-SRC4382-AD-01"])
    preflight.write_text(
        json.dumps(
            {
                "evidence_identity": evidence_identity,
                "selected_phases": selected_phases,
                "preflight": {"status": "PASS", "failures": []},
            }
        ),
        encoding="utf-8",
    )
    closure.write_text(
        json.dumps(
            {
                "evidence_identity": evidence_identity,
                "final_rc": 0,
                "selected_phases": selected_phases,
                "phase_results": _phase_results_for_bugs(
                    runner,
                    ["BUG-SRC4382-AD-01"],
                ),
                "bug_closure": {"BUG-SRC4382-AD-01": {"status": "passed"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-SRC4382-AD-01": "green"},
    )
    monkeypatch.setattr(
        runner,
        "_remaining_bug_payloads",
        lambda python, selected_bug_names: [
            {
                "bug": "BUG-SRC4382-AD-01",
                "status": "green",
                "preflight_report": str(preflight),
                "closure_report": str(closure),
            },
        ],
    )

    rc = runner.main(
        [
            "--summarize-artifacts",
            "--require-all-ready",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )
    assert rc == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    row = report["artifact_summary"]["rows"][0]
    assert row["artifact_status"] == "manual_evidence_missing"
    assert row["bug_closure_status"] == "passed"
    assert row["manual_evidence_status"] == "manual_evidence_missing"
    assert row["manual_evidence_errors"]
    assert report["artifact_summary"]["ready_to_mark_done"] == []
    assert report["artifact_summary"]["not_ready_bugs"] == ["BUG-SRC4382-AD-01"]

    evidence.write_text(_passing_src4382_manual_evidence(), encoding="utf-8")
    report_path = tmp_path / "artifact-summary-src4382-ready.json"
    rc = runner.main(
        [
            "--summarize-artifacts",
            "--require-all-ready",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )
    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    row = report["artifact_summary"]["rows"][0]
    assert row["artifact_status"] == "passed"
    assert row["manual_evidence_status"] == "passed"
    assert row["manual_evidence_errors"] == []
    assert report["artifact_summary"]["ready_to_mark_done"] == [
        "BUG-SRC4382-AD-01"
    ]
    assert report["artifact_summary"]["not_ready_bugs"] == []


def test_summarize_artifacts_accepts_src4382_manual_evidence_without_live_report(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_runner()
    evidence = tmp_path / "bug_src4382_ad_01_manual_evidence.md"
    evidence.write_text(_passing_src4382_manual_evidence(), encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "SRC4382_MANUAL_EVIDENCE_RELATIVE_PATH",
        str(evidence),
    )
    preflight = tmp_path / "missing_preflight.json"
    closure = tmp_path / "missing_closure.json"
    report_path = tmp_path / "artifact-summary-src4382-manual-only.json"
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-SRC4382-AD-01": "green"},
    )
    monkeypatch.setattr(
        runner,
        "_remaining_bug_payloads",
        lambda python, selected_bug_names: [
            {
                "bug": "BUG-SRC4382-AD-01",
                "status": "green",
                "preflight_report": str(preflight),
                "closure_report": str(closure),
            },
        ],
    )

    rc = runner.main(
        [
            "--summarize-artifacts",
            "--require-all-ready",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )

    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    row = report["artifact_summary"]["rows"][0]
    assert row["artifact_status"] == "passed"
    assert row["preflight_status"] == "missing"
    assert row["closure_identity_status"] == "manual_evidence"
    assert row["bug_closure_status"] == "manual_evidence"
    assert row["manual_evidence_status"] == "passed"
    assert row["manual_evidence_errors"] == []
    assert report["artifact_summary"]["ready_to_mark_done"] == [
        "BUG-SRC4382-AD-01"
    ]
    assert report["artifact_summary"]["not_ready_bugs"] == []
    assert report["artifact_summary"]["missing_reports"] == []


def test_summarize_artifacts_reports_invalid_src4382_manual_evidence_without_live_report(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    runner = _load_runner()
    evidence = tmp_path / "bug_src4382_ad_01_manual_evidence.md"
    evidence.write_text(
        _passing_src4382_manual_evidence().replace("Pass/fail: pass", "Pass/fail: fail"),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "SRC4382_MANUAL_EVIDENCE_RELATIVE_PATH",
        str(evidence),
    )
    preflight = tmp_path / "missing_preflight.json"
    closure = tmp_path / "missing_closure.json"
    report_path = tmp_path / "artifact-summary-src4382-invalid-manual.json"
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-SRC4382-AD-01": "green"},
    )
    monkeypatch.setattr(
        runner,
        "_remaining_bug_payloads",
        lambda python, selected_bug_names: [
            {
                "bug": "BUG-SRC4382-AD-01",
                "status": "green",
                "preflight_report": str(preflight),
                "closure_report": str(closure),
            },
        ],
    )

    rc = runner.main(
        [
            "--summarize-artifacts",
            "--require-all-ready",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "BUG-SRC4382-AD-01 [green]: manual_evidence_failed" in captured.out
    assert "manual evidence: verdict must be pass: 'fail'" in captured.out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    row = report["artifact_summary"]["rows"][0]
    assert row["artifact_status"] == "manual_evidence_failed"
    assert row["preflight_status"] == "missing"
    assert row["closure_identity_status"] == "missing"
    assert row["bug_closure_status"] is None
    assert row["manual_evidence_status"] == "manual_evidence_failed"
    assert row["manual_evidence_errors"] == ["verdict must be pass: 'fail'"]
    assert report["artifact_summary"]["ready_to_mark_done"] == []
    assert report["artifact_summary"]["not_ready_bugs"] == ["BUG-SRC4382-AD-01"]
    assert report["artifact_summary"]["missing_reports"] == []


def test_summarize_artifacts_rejects_stale_passed_reports(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_runner()
    current_identity = {"schema": 2, "test": "current"}
    stale_identity = {"schema": 2, "test": "old"}
    monkeypatch.setattr(
        runner,
        "_current_evidence_identity",
        lambda: current_identity,
    )
    preflight = tmp_path / "bug_diag_01_preflight_current.json"
    closure = tmp_path / "bug_diag_01_closure_current.json"
    report_path = tmp_path / "artifact-summary-stale.json"
    selected_phases = _selected_phase_payloads(runner, ["BUG-DIAG-01"])
    preflight.write_text(
        json.dumps(
            {
                "evidence_identity": stale_identity,
                "selected_phases": selected_phases,
                "preflight": {"status": "PASS", "failures": []},
            }
        ),
        encoding="utf-8",
    )
    closure.write_text(
        json.dumps(
            {
                "evidence_identity": stale_identity,
                "final_rc": 0,
                "selected_phases": selected_phases,
                "phase_results": _phase_results_for_bugs(runner, ["BUG-DIAG-01"]),
                "bug_closure": {"BUG-DIAG-01": {"status": "passed"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-REV-01": "done", "BUG-DIAG-01": "green"},
    )
    monkeypatch.setattr(
        runner,
        "_remaining_bug_payloads",
        lambda python, selected_bug_names: [
            {
                "bug": "BUG-DIAG-01",
                "status": "green",
                "preflight_report": str(preflight),
                "closure_report": str(closure),
            },
        ],
    )

    rc = runner.main(
        [
            "--summarize-artifacts",
            "--require-all-ready",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )

    assert rc == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = report["artifact_summary"]
    assert summary["ready_to_mark_done"] == []
    assert summary["not_ready_bugs"] == ["BUG-DIAG-01"]
    row = summary["rows"][0]
    assert row["artifact_status"] == "passed_closure_stale"
    assert row["preflight_status"] == "PASS"
    assert row["preflight_identity_status"] == "stale"
    assert row["closure_identity_status"] == "stale"


def test_summarize_artifacts_rejects_passed_preflight_for_wrong_phase_set(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_runner()
    evidence_identity = {"schema": 2, "test": "current"}
    monkeypatch.setattr(
        runner,
        "_current_evidence_identity",
        lambda: evidence_identity,
    )
    preflight = tmp_path / "bug_diag_01_preflight_current.json"
    closure = tmp_path / "bug_diag_01_closure_current.json"
    report_path = tmp_path / "artifact-summary-mismatched-preflight.json"
    required_diag_01 = [
        phase.name for phase in runner._selected_phases([], ["BUG-DIAG-01"])
    ]
    preflight.write_text(
        json.dumps(
            {
                "evidence_identity": evidence_identity,
                "selected_phases": [{"name": "identity"}],
                "preflight": {"status": "PASS", "failures": []},
            }
        ),
        encoding="utf-8",
    )
    closure.write_text(
        json.dumps(
            {
                "evidence_identity": evidence_identity,
                "final_rc": 0,
                "selected_phases": _selected_phase_payloads(runner, ["BUG-DIAG-01"]),
                "phase_results": _phase_results_for_bugs(runner, ["BUG-DIAG-01"]),
                "bug_closure": {"BUG-DIAG-01": {"status": "passed"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-REV-01": "done", "BUG-DIAG-01": "green"},
    )
    monkeypatch.setattr(
        runner,
        "_remaining_bug_payloads",
        lambda python, selected_bug_names: [
            {
                "bug": "BUG-DIAG-01",
                "status": "green",
                "preflight_report": str(preflight),
                "closure_report": str(closure),
            },
        ],
    )

    rc = runner.main(
        [
            "--summarize-artifacts",
            "--require-all-ready",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )

    assert rc == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    summary = report["artifact_summary"]
    assert summary["ready_to_mark_done"] == []
    assert summary["not_ready_bugs"] == ["BUG-DIAG-01"]
    row = summary["rows"][0]
    assert row["artifact_status"] == "passed_preflight_missing_required_phases"
    assert row["preflight_status"] == "PASS"
    assert row["preflight_missing_required_phases"] == required_diag_01
    assert row["bug_closure_status"] == "passed"
    assert row["reported_bug_closure_status"] == "passed"


def test_summarize_artifacts_writes_stable_default_report(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_runner()
    report_path = tmp_path / "artifact_summary_current.json"
    monkeypatch.setattr(
        runner,
        "_stable_artifact_summary_report_path",
        lambda: report_path,
    )
    monkeypatch.setattr(
        runner,
        "_active_ledger_statuses",
        lambda: {"BUG-REV-01": "done"},
    )

    rc = runner.main(["--summarize-artifacts", "--python", "PY"])

    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["report_path"] == str(report_path)
    assert report["mode"]["summarize_artifacts"] is True
    assert report["artifact_summary"]["rows"] == [
        {
            "bug": "BUG-REV-01",
            "ledger_status": "done",
            "artifact_status": "ledger_done",
            "preflight_status": "ledger_done",
            "preflight_identity_status": "ledger_done",
            "preflight_missing_required_phases": [],
            "preflight_report": None,
            "preflight_failures": [],
            "closure_report": None,
            "closure_identity_status": "ledger_done",
            "bug_closure_status": "done",
            "final_rc": None,
        }
    ]


def test_evidence_identity_covers_ledger_runner_tests_and_release_hexes() -> None:
    runner = _load_runner()

    identity = runner._current_evidence_identity()

    assert runner.REPORT_SCHEMA_VERSION == 13
    assert identity["schema"] == runner.REPORT_SCHEMA_VERSION
    ledger = _ledger_text()
    assert f"current report schema is `{runner.REPORT_SCHEMA_VERSION}`" in ledger
    assert f"schema-{runner.REPORT_SCHEMA_VERSION} evidence-identity" in ledger
    assert f"schema-{runner.REPORT_SCHEMA_VERSION} bump" in ledger
    assert identity["ledger_contract"] == {
        "path": "docs/IMPL_V171_V32_BUG_LEDGER.md",
        "section": "hardware phase map",
        "sha256": identity["ledger_contract"]["sha256"],
    }
    assert len(identity["ledger_contract"]["sha256"]) == 64
    files = identity["files"]
    assert set(files) == {
        "control_flash_module",
        "control_v16b_hex",
        "control_v171_hex",
        "ep0_flash_probe_module",
        "flash_control_safe_wrapper",
        "hardware_flipper_ir_cli",
        "hardware_lcd_probe_cli",
        "hardware_runbook",
        "hardware_state_cli",
        "hardware_test",
        "main_flash_module",
        "main_v32_hex",
        "runner",
        "src4382_manual_evidence_template",
        "src4382_manual_evidence_validator",
        "v32_release_flash_module",
    }
    for item in files.values():
        assert len(item["sha256"]) == 64
        assert not item["path"].startswith("/")


def test_evidence_identity_ignores_mutable_ledger_status_text(monkeypatch) -> None:
    runner = _load_runner()

    class FakeLedgerPath:
        def __init__(self, text: str) -> None:
            self.text = text

        def read_text(self, encoding: str) -> str:
            return self.text

        def relative_to(self, root: Path) -> Path:
            return Path("docs/IMPL_V171_V32_BUG_LEDGER.md")

    base = (
        "prefix with | BUG-DIAG-01 | green | mutable status\n"
        "Hardware phase map for `scripts/run_v171_v32_ledger_hardware_gate.py --bug`:\n"
        "| Bug(s) | Required phase(s) |\n"
        "| BUG-DIAG-01 | `diag-pb1` |\n"
        "## Completion Audit\n"
        "| BUG-DIAG-01 | sim | required |\n"
    )
    changed = base.replace(
        "| BUG-DIAG-01 | green | mutable status",
        "| BUG-DIAG-01 | done | mutable status",
    ).replace(
        "| BUG-DIAG-01 | sim | required |",
        "| BUG-DIAG-01 | sim | DONE: later evidence |",
    )
    fake_ledger = FakeLedgerPath(base)
    monkeypatch.setattr(runner, "LEDGER_PATH", fake_ledger)
    before = runner._current_evidence_identity()["ledger_contract"]["sha256"]
    fake_ledger.text = changed
    after = runner._current_evidence_identity()["ledger_contract"]["sha256"]

    assert before == after


def test_ir_bug_dry_run_prints_control_flash_commands(capsys) -> None:
    runner = _load_runner()

    rc = runner.main(["--python", "PY", "--bug", "BUG-IR-01"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "[ir-receiver-sweep]" in captured.out
    assert "DLCP Control Firmware V1.6b.hex" in captured.out
    assert "DLCP_Control_V1.71.hex" in captured.out
    assert "--live-timeout-s 10" in captured.out
    assert "DLCP_HW_EXPECTED_CONTROL_VERSION=V1.6b" in captured.out
    assert "DLCP_HW_EXPECTED_CONTROL_VERSION=V1.71" in captured.out


def test_settings_dry_run_prints_required_env(capsys) -> None:
    runner = _load_runner()

    rc = runner.main(["--python", "PY", "--bug", "BUG-SETTINGS-01"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "[settings]" in captured.out
    assert (
        "Required env: DLCP_HW_EXPECTED_VOLUME_LOW, DLCP_HW_EXPECTED_INPUT, "
        "DLCP_HW_EXPECTED_SETUP_PROFILE"
    ) in captured.out


def _fake_main_role(role: str) -> SimpleNamespace:
    return SimpleNamespace(
        role=role,
        mode="app",
        version="3.2",
        active_preset="A",
        active_config_name="LX521.4 22MG10F-v5",
        path=f"fake-{role.lower()}",
    )


def test_preflight_rejects_host_only_cameras(monkeypatch, capsys) -> None:
    runner = _load_runner()

    from dlcp_fw.cli import hardware_state_test as hw

    monkeypatch.delenv("DLCP_HW_CAMERA_SELECTOR", raising=False)
    monkeypatch.setattr(
        hw,
        "_collect_main_roles",
        lambda *, vid, pid: [_fake_main_role("LEFT"), _fake_main_role("RIGHT")],
    )
    monkeypatch.setattr(hw, "_assert_left_right_roles", lambda states: None)
    monkeypatch.setattr(
        hw,
        "_load_avfoundation_video_devices",
        lambda: [
            hw.VideoDevice(index=0, name="MacBook Pro Camera"),
            hw.VideoDevice(index=1, name="MacBook Pro Desk View Camera"),
            hw.VideoDevice(index=2, name="Capture screen 0"),
        ],
    )

    rc = runner._preflight([runner.PHASE_BY_NAME["diag-layout-pb1"]])

    captured = capsys.readouterr()
    assert rc == 1
    assert "external LCD camera candidates: 0" in captured.out
    assert "no external LCD camera candidate visible" in captured.out


def test_report_json_records_preflight_failures(monkeypatch, tmp_path) -> None:
    runner = _load_runner()

    from dlcp_fw.cli import hardware_state_test as hw

    monkeypatch.delenv("DLCP_HW_CAMERA_SELECTOR", raising=False)
    monkeypatch.setattr(
        hw,
        "_collect_main_roles",
        lambda *, vid, pid: [_fake_main_role("LEFT"), _fake_main_role("RIGHT")],
    )
    monkeypatch.setattr(hw, "_assert_left_right_roles", lambda states: None)
    monkeypatch.setattr(
        hw,
        "_load_avfoundation_video_devices",
        lambda: [hw.VideoDevice(index=0, name="MacBook Pro Camera")],
    )
    report_path = tmp_path / "gate-report.json"

    rc = runner.main(
        [
            "--preflight",
            "--phase",
            "diag-layout-pb1",
            "--report-json",
            str(report_path),
        ]
    )

    assert rc == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["final_rc"] == 1
    assert report["selectors"]["phase"] == ["diag-layout-pb1"]
    assert report["selected_phases"][0]["name"] == "diag-layout-pb1"
    assert report["preflight"]["status"] == "FAIL"
    assert report["preflight"]["camera"]["external_lcd_candidates"] == []
    assert any(
        "no external LCD camera candidate visible" in failure
        for failure in report["preflight"]["failures"]
    )


def test_settings_preflight_requires_expected_user_setting_env(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    runner = _load_runner()

    from dlcp_fw.cli import hardware_state_test as hw

    monkeypatch.delenv("DLCP_HW_EXPECTED_VOLUME_LOW", raising=False)
    monkeypatch.delenv("DLCP_HW_EXPECTED_INPUT", raising=False)
    monkeypatch.delenv("DLCP_HW_EXPECTED_SETUP_PROFILE", raising=False)
    monkeypatch.setattr(
        hw,
        "_collect_main_roles",
        lambda *, vid, pid: [_fake_main_role("LEFT")],
    )
    report_path = tmp_path / "settings-preflight-report.json"

    rc = runner.main(
        [
            "--preflight",
            "--phase",
            "settings",
            "--report-json",
            str(report_path),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "DLCP_HW_EXPECTED_VOLUME_LOW: missing" in captured.out
    assert "DLCP_HW_EXPECTED_INPUT: missing" in captured.out
    assert "DLCP_HW_EXPECTED_SETUP_PROFILE: missing" in captured.out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["preflight"]["requirements"]["env"] == [
        "DLCP_HW_EXPECTED_INPUT",
        "DLCP_HW_EXPECTED_SETUP_PROFILE",
        "DLCP_HW_EXPECTED_VOLUME_LOW",
    ]
    assert report["preflight"]["env"] == {
        "DLCP_HW_EXPECTED_INPUT": False,
        "DLCP_HW_EXPECTED_SETUP_PROFILE": False,
        "DLCP_HW_EXPECTED_VOLUME_LOW": False,
    }
    assert "missing required env DLCP_HW_EXPECTED_INPUT" in report["preflight"][
        "failures"
    ]
    assert "missing required env DLCP_HW_EXPECTED_VOLUME_LOW" in report[
        "preflight"
    ]["failures"]
    assert "missing required env DLCP_HW_EXPECTED_SETUP_PROFILE" in report[
        "preflight"
    ]["failures"]


def test_settings_preflight_passes_when_expected_user_setting_env_is_present(
    monkeypatch,
    tmp_path,
) -> None:
    runner = _load_runner()

    from dlcp_fw.cli import hardware_state_test as hw

    monkeypatch.setenv("DLCP_HW_EXPECTED_VOLUME_LOW", "0xE2")
    monkeypatch.setenv("DLCP_HW_EXPECTED_INPUT", "0x03")
    monkeypatch.setenv("DLCP_HW_EXPECTED_SETUP_PROFILE", "0x04")
    monkeypatch.setattr(
        hw,
        "_collect_main_roles",
        lambda *, vid, pid: [_fake_main_role("LEFT")],
    )
    report_path = tmp_path / "settings-preflight-pass-report.json"

    rc = runner.main(
        [
            "--preflight",
            "--phase",
            "settings",
            "--report-json",
            str(report_path),
        ]
    )

    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["preflight"]["status"] == "PASS"
    assert report["preflight"]["env"] == {
        "DLCP_HW_EXPECTED_INPUT": True,
        "DLCP_HW_EXPECTED_SETUP_PROFILE": True,
        "DLCP_HW_EXPECTED_VOLUME_LOW": True,
    }


def test_settings_preflight_rejects_invalid_expected_user_setting_env(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    runner = _load_runner()

    from dlcp_fw.cli import hardware_state_test as hw

    monkeypatch.setenv("DLCP_HW_EXPECTED_VOLUME_LOW", "not-a-byte")
    monkeypatch.setenv("DLCP_HW_EXPECTED_INPUT", "0x100")
    monkeypatch.setenv("DLCP_HW_EXPECTED_SETUP_PROFILE", "-1")
    monkeypatch.setattr(
        hw,
        "_collect_main_roles",
        lambda *, vid, pid: [_fake_main_role("LEFT")],
    )
    report_path = tmp_path / "settings-preflight-invalid-report.json"

    rc = runner.main(
        [
            "--preflight",
            "--phase",
            "settings",
            "--report-json",
            str(report_path),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "DLCP_HW_EXPECTED_VOLUME_LOW: invalid" in captured.out
    assert "DLCP_HW_EXPECTED_INPUT: invalid" in captured.out
    assert "DLCP_HW_EXPECTED_SETUP_PROFILE: invalid" in captured.out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["preflight"]["env"] == {
        "DLCP_HW_EXPECTED_INPUT": True,
        "DLCP_HW_EXPECTED_SETUP_PROFILE": True,
        "DLCP_HW_EXPECTED_VOLUME_LOW": True,
    }
    failures = report["preflight"]["failures"]
    assert any(
        failure.startswith("invalid required env DLCP_HW_EXPECTED_VOLUME_LOW")
        for failure in failures
    )
    assert any(
        failure.startswith("invalid required env DLCP_HW_EXPECTED_INPUT")
        for failure in failures
    )
    assert any(
        failure.startswith("invalid required env DLCP_HW_EXPECTED_SETUP_PROFILE")
        for failure in failures
    )


def test_live_modes_write_default_report_json(monkeypatch, tmp_path, capsys) -> None:
    runner = _load_runner()

    from dlcp_fw.cli import hardware_state_test as hw

    report_path = tmp_path / "default-preflight-report.json"
    monkeypatch.setattr(runner, "_default_report_path", lambda args: report_path)
    monkeypatch.setattr(
        hw,
        "_collect_main_roles",
        lambda *, vid, pid: [_fake_main_role("LEFT")],
    )

    rc = runner.main(["--preflight", "--phase", "identity"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Bug closure status:" in captured.out
    assert "BUG-REV-01: done (identity)" in captured.out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["report_path"] == str(report_path)
    assert report["preflight"]["status"] == "PASS"
    assert report["bug_closure"]["BUG-REV-01"]["status"] == "done"
    assert report["bug_closure"]["BUG-REV-01"]["ledger_status"] == "done"


def test_report_json_contains_bug_phase_closure_map(tmp_path) -> None:
    runner = _load_runner()
    report_path = tmp_path / "list-report.json"

    rc = runner.main(
        [
            "--list",
            "--bug",
            "BUG-IR-02",
            "--report-json",
            str(report_path),
        ]
    )

    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert set(report["bug_phase_map"]) == set(runner.BUG_PHASES)
    assert report["bug_phase_map"]["BUG-IR-02"] == {
        "selectors": ["diag-ir-actions", "preset-mute", "preset-standby-wake"],
        "expanded_phases": [
            "diag-ir-pb1",
            "diag-ir-pb2",
            "preset-mute",
            "preset-standby-wake",
        ],
    }
    assert [phase["name"] for phase in report["selected_phases"]] == [
        "diag-ir-pb1",
        "diag-ir-pb2",
        "preset-mute",
        "preset-standby-wake",
    ]
    assert report["bug_closure"]["BUG-IR-02"] == {
        "status": "not_run",
        "ledger_status": "green",
        "required_phases": [
            "diag-ir-pb1",
            "diag-ir-pb2",
            "preset-mute",
            "preset-standby-wake",
        ],
        "selected_required_phases": [
            "diag-ir-pb1",
            "diag-ir-pb2",
            "preset-mute",
            "preset-standby-wake",
        ],
        "missing_required_phases": [],
        "passed_required_phases": [],
        "failed_required_phases": [],
        "not_run_required_phases": [
            "diag-ir-pb1",
            "diag-ir-pb2",
            "preset-mute",
            "preset-standby-wake",
        ],
    }
    assert report["bug_closure"]["BUG-DIAG-01"]["status"] == "missing"


def test_preflight_report_preserves_inventory_errors(monkeypatch) -> None:
    runner = _load_runner()

    from dlcp_fw.cli import hardware_state_test as hw

    def raise_main(*, vid, pid):  # noqa: ANN001
        raise RuntimeError("hid access denied")

    def raise_camera() -> list[object]:
        raise RuntimeError("camera inventory denied")

    def raise_flipper() -> list[str]:
        raise RuntimeError("flipper inventory denied")

    monkeypatch.delenv("DLCP_HW_CAMERA_SELECTOR", raising=False)
    monkeypatch.delenv("DLCP_HW_FLIPPER_PORT", raising=False)
    monkeypatch.setattr(hw, "_collect_main_roles", raise_main)
    monkeypatch.setattr(hw, "_load_avfoundation_video_devices", raise_camera)
    monkeypatch.setattr(
        hw.hardware_flipper_ir,
        "discover_flipper_serial_ports",
        raise_flipper,
    )

    rc, report = runner._preflight_with_report([runner.PHASE_BY_NAME["diag-ir-pb1"]])

    assert rc == 1
    assert report["main"]["error"] == "hid access denied"
    assert report["camera"]["error"] == "camera inventory denied"
    assert report["flipper"]["error"] == "flipper inventory denied"


def test_preflight_allows_explicit_camera_selector(monkeypatch, capsys) -> None:
    runner = _load_runner()

    from dlcp_fw.cli import hardware_state_test as hw

    monkeypatch.setenv("DLCP_HW_CAMERA_SELECTOR", "MacBook Pro Camera")
    monkeypatch.setattr(
        hw,
        "_collect_main_roles",
        lambda *, vid, pid: [_fake_main_role("LEFT"), _fake_main_role("RIGHT")],
    )
    monkeypatch.setattr(hw, "_assert_left_right_roles", lambda states: None)

    rc = runner._preflight([runner.PHASE_BY_NAME["diag-layout-pb1"]])

    captured = capsys.readouterr()
    assert rc == 0
    assert "using DLCP_HW_CAMERA_SELECTOR='MacBook Pro Camera'" in captured.out


def test_report_json_records_execute_phase_results(monkeypatch, tmp_path) -> None:
    runner = _load_runner()
    report_path = tmp_path / "execute-report.json"

    def fake_run_phase(phase, python, extra_pytest_args, pause):  # noqa: ANN001
        assert not pause
        return 7 if phase.name == "settings" else 0

    monkeypatch.setattr(runner, "_run_phase", fake_run_phase)

    rc = runner.main(
        [
            "--execute",
            "--keep-going",
            "--no-pause",
            "--phase",
            "identity",
            "--phase",
            "settings",
            "--python",
            "PY",
            "--report-json",
            str(report_path),
        ]
    )

    assert rc == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["final_rc"] == 1
    assert [item["name"] for item in report["selected_phases"]] == [
        "identity",
        "settings",
    ]
    assert [
        {key: item[key] for key in ("phase", "returncode")}
        for item in report["phase_results"]
    ] == [
        {"phase": "identity", "returncode": 0},
        {"phase": "settings", "returncode": 7},
    ]
    assert report["phase_results"][0]["elapsed_s"] == pytest.approx(0.0, abs=1.0)
    assert report["phase_results"][1]["elapsed_s"] == pytest.approx(0.0, abs=1.0)
    assert report["failures"] == [{"phase": "settings", "returncode": 7}]
    assert report["bug_closure"]["BUG-REV-01"] == {
        "status": "passed",
        "ledger_status": "done",
        "required_phases": ["identity"],
        "selected_required_phases": ["identity"],
        "missing_required_phases": [],
        "passed_required_phases": ["identity"],
        "failed_required_phases": [],
        "not_run_required_phases": [],
    }
    assert report["bug_closure"]["BUG-SETTINGS-01"] == {
        "status": "failed",
        "ledger_status": "green",
        "required_phases": ["settings", "identity", "ir-receiver-sweep"],
        "selected_required_phases": ["settings", "identity"],
        "missing_required_phases": ["ir-receiver-sweep"],
        "passed_required_phases": ["identity"],
        "failed_required_phases": ["settings"],
        "not_run_required_phases": ["ir-receiver-sweep"],
    }


def test_execute_writes_default_report_json(monkeypatch, tmp_path, capsys) -> None:
    runner = _load_runner()
    report_path = tmp_path / "default-execute-report.json"

    monkeypatch.setattr(runner, "_default_report_path", lambda args: report_path)
    monkeypatch.setattr(
        runner,
        "_run_phase",
        lambda phase, python, extra_pytest_args, pause: 0,
    )

    rc = runner.main(
        ["--execute", "--no-pause", "--python", "PY", "--phase", "identity"]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "Bug closure status:" in captured.out
    assert "BUG-REV-01: passed (identity)" in captured.out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["report_path"] == str(report_path)
    assert report["bug_closure"]["BUG-REV-01"]["status"] == "passed"


def test_require_bug_closed_enforces_bug_closure_status(monkeypatch, tmp_path, capsys) -> None:
    runner = _load_runner()
    report_path = tmp_path / "required-closure-report.json"

    monkeypatch.setattr(
        runner,
        "_run_phase",
        lambda phase, python, extra_pytest_args, pause: 0,
    )

    rc = runner.main(
        [
            "--execute",
            "--no-pause",
            "--python",
            "PY",
            "--phase",
            "identity",
            "--require-bug-closed",
            "BUG-REV-01",
            "--require-bug-closed",
            "BUG-SETTINGS-01",
            "--report-json",
            str(report_path),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "BUG-REV-01: passed (identity)" in captured.out
    assert "Required bug closure failures:" in captured.err
    assert "BUG-SETTINGS-01: missing" in captured.err
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["final_rc"] == 1
    assert report["required_bug_closure"] == ["BUG-REV-01", "BUG-SETTINGS-01"]
    assert report["required_bug_closure_failures"] == [
        {"bug": "BUG-SETTINGS-01", "status": "missing"}
    ]


def test_execute_multi_phase_defaults_to_pause(monkeypatch) -> None:
    runner = _load_runner()
    pauses: list[bool] = []

    def fake_run_phase(phase, python, extra_pytest_args, pause):  # noqa: ANN001
        pauses.append(pause)
        return 0

    monkeypatch.setattr(runner, "_run_phase", fake_run_phase)

    rc = runner.main(["--execute", "--python", "PY", "--phase", "diag-ir-actions"])

    assert rc == 0
    assert pauses == [True, True]


def test_execute_multi_phase_no_pause_override(monkeypatch) -> None:
    runner = _load_runner()
    pauses: list[bool] = []

    def fake_run_phase(phase, python, extra_pytest_args, pause):  # noqa: ANN001
        pauses.append(pause)
        return 0

    monkeypatch.setattr(runner, "_run_phase", fake_run_phase)

    rc = runner.main(
        ["--execute", "--no-pause", "--python", "PY", "--phase", "diag-ir-actions"]
    )

    assert rc == 0
    assert pauses == [False, False]
