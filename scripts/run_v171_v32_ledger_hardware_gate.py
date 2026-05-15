#!/usr/bin/env python3
"""Operator runner for the V1.71/V3.2 implementation-bug hardware gate.

The bug ledger in docs/IMPL_V171_V32_BUG_LEDGER.md intentionally requires
live-rig proof for behaviors the simulator cannot fully close: real IR,
physical front-panel controls, USB-visible MAIN identity, and Diagnostics-page
LCD convergence.  This wrapper keeps those checks in one place and prints the
exact pytest command/env for each phase.

Default mode is dry-run.  Use --execute with one or more --phase arguments to
run a concrete live-rig phase after satisfying its manual preconditions.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / "docs" / "IMPL_V171_V32_BUG_LEDGER.md"
TEST_FILE = "tests/hardware/test_live_state_transitions.py"
REPORT_SCHEMA_VERSION = 11
EVIDENCE_FILE_PATHS = {
    "runner": Path(__file__).resolve(),
    "hardware_runbook": REPO_ROOT / "docs" / "HARDWARE_TEST.md",
    "hardware_test": REPO_ROOT / TEST_FILE,
    "hardware_state_cli": REPO_ROOT / "src" / "dlcp_fw" / "cli" / "hardware_state_test.py",
    "hardware_lcd_probe_cli": REPO_ROOT / "src" / "dlcp_fw" / "cli" / "hardware_lcd_probe.py",
    "hardware_flipper_ir_cli": REPO_ROOT / "src" / "dlcp_fw" / "cli" / "hardware_flipper_ir.py",
    "main_flash_module": REPO_ROOT / "src" / "dlcp_fw" / "flash" / "dlcp_main_flash.py",
    "v32_release_flash_module": REPO_ROOT / "src" / "dlcp_fw" / "flash" / "dlcp_v32_release_flash.py",
    "control_flash_module": REPO_ROOT / "src" / "dlcp_fw" / "flash" / "dlcp_control_flash.py",
    "ep0_flash_probe_module": REPO_ROOT / "src" / "dlcp_fw" / "flash" / "dlcp_ep0_flash_probe.py",
    "flash_control_safe_wrapper": REPO_ROOT / "scripts" / "flash_control_safe.sh",
    "main_v32_hex": REPO_ROOT / "firmware" / "patched" / "releases" / "DLCP_Firmware_V3.2.hex",
    "control_v171_hex": REPO_ROOT / "firmware" / "patched" / "releases" / "DLCP_Control_V1.71.hex",
    "control_v16b_hex": REPO_ROOT / "firmware" / "stock" / "control" / "DLCP Control Firmware V1.6b.hex",
}
for import_root in (REPO_ROOT, REPO_ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

HOST_CAMERA_NAME_SUBSTRINGS = (
    "capture screen",
    "continuity camera",
    "desk view",
    "facetime",
    "macbook",
    "screen capture",
)


@dataclass(frozen=True)
class Phase:
    name: str
    description: str
    node: str | None
    env: tuple[tuple[str, str], ...] = ()
    required_env: tuple[str, ...] = ()
    args: tuple[str, ...] = ()
    manual: str = ""
    main_requirement: str = "pair"
    needs_camera: bool = False
    needs_flipper: bool = False

    def command(self, python: str, extra_pytest_args: tuple[str, ...]) -> list[str]:
        cmd = [python, "-m", "pytest", "-q"]
        cmd.extend(self.args)
        if self.node is None:
            cmd.append(TEST_FILE)
        else:
            cmd.append(f"{TEST_FILE}::{self.node}")
        cmd.append("--run-hardware")
        cmd.extend(extra_pytest_args)
        return cmd


PHASES: tuple[Phase, ...] = (
    Phase(
        name="identity",
        description="V3.2 runtime identity, EEPROM revision, A/B filename RAM.",
        node="test_live_v32_release_identity_and_ab_filename_ram",
        env=(("DLCP_HW_RELEASE_IDENTITY_CONFIRM", "1"),),
        manual=(
            "Connect one or both V3.2 MAINs over USB after the release-flash "
            "ceremony. This phase switches visible MAINs A->B->A via EP0 and "
            "restores the starting preset."
        ),
        main_requirement="any",
    ),
    Phase(
        name="settings",
        description="MAIN release flash preserves expected volume/input/profile settings.",
        node="test_live_v32_release_flash_preserves_expected_user_settings",
        env=(("DLCP_HW_RELEASE_SETTINGS_CONFIRM", "1"),),
        required_env=(
            "DLCP_HW_EXPECTED_VOLUME_LOW",
            "DLCP_HW_EXPECTED_INPUT",
            "DLCP_HW_EXPECTED_SETUP_PROFILE",
        ),
        args=("-s",),
        manual=(
            "After flashing V3.2, set DLCP_HW_EXPECTED_VOLUME_LOW and "
            "DLCP_HW_EXPECTED_INPUT to the values recorded before flash "
            "(for example 0xE2 for -30 dB), and set "
            "DLCP_HW_EXPECTED_SETUP_PROFILE to the pre-flash IR profile byte. "
            "This phase reads one or both visible MAINs over EP0 and checks "
            "volume/input/profile RAM."
        ),
        main_requirement="any",
    ),
    Phase(
        name="front-panel-preset-a",
        description="Physical CONTROL preset selection lands on A on both MAINs.",
        node="test_live_manual_front_panel_preset_selection_updates_mains_and_filename_ram",
        env=(
            ("DLCP_HW_FRONT_PANEL_PRESET_CONFIRM", "1"),
            ("DLCP_HW_EXPECTED_PRESET", "A"),
        ),
        manual=(
            "Use the physical CONTROL Preset screen to select A, wait for the "
            "UI to settle on Volume or Preset with row 2 'Active: A', then run."
        ),
        needs_camera=True,
    ),
    Phase(
        name="front-panel-preset-b",
        description="Physical CONTROL preset selection lands on B on both MAINs.",
        node="test_live_manual_front_panel_preset_selection_updates_mains_and_filename_ram",
        env=(
            ("DLCP_HW_FRONT_PANEL_PRESET_CONFIRM", "1"),
            ("DLCP_HW_EXPECTED_PRESET", "B"),
        ),
        manual=(
            "Use the physical CONTROL Preset screen to select B, wait for the "
            "UI to settle on Volume or Preset with row 2 'Active: B', then run."
        ),
        needs_camera=True,
    ),
    Phase(
        name="front-panel-standby-wake",
        description="Physical CONTROL STBY then wake from Volume.",
        node="test_live_manual_front_panel_standby_wake_from_volume",
        env=(("DLCP_HW_FRONT_PANEL_STBY_WAKE_CONFIRM", "1"),),
        args=("-s",),
        manual=(
            "Start on Volume. During the test, press physical STBY when the "
            "prompt appears, then press STBY again when prompted for wake."
        ),
        needs_camera=True,
    ),
    Phase(
        name="preset-convergence",
        description="IR preset request converges on the requested target.",
        node="test_live_preset_convergence_reaches_requested_target",
        manual="Requires Flipper IR and LCD camera access.",
        needs_camera=True,
        needs_flipper=True,
    ),
    Phase(
        name="rapid-toggle",
        description="Rapid IR preset toggles converge on the final target.",
        node="test_live_rapid_toggle_convergence_reaches_final_target",
        manual="Requires Flipper IR and LCD camera access.",
        needs_camera=True,
        needs_flipper=True,
    ),
    Phase(
        name="preset-mute",
        description="IR preset followed by MUTE works across delay sweep.",
        node="test_live_preset_mute_timing_sweep_passes_for_configured_delays",
        manual="Requires Flipper IR and LCD camera access.",
        needs_camera=True,
        needs_flipper=True,
    ),
    Phase(
        name="preset-standby-wake",
        description="IR preset followed by STDBY/WAKE works across delay sweep.",
        node="test_live_preset_standby_wake_timing_sweep_passes_for_configured_delays",
        env=(("DLCP_HW_REQUIRE_STANDBY_LCD_ZZZ", "1"),),
        manual="Requires Flipper IR and LCD camera access.",
        needs_camera=True,
        needs_flipper=True,
    ),
    Phase(
        name="reconnect-soak",
        description="Repeated IR standby/wake reconnect responsiveness soak.",
        node="test_live_reconnect_responsiveness_soak_passes_for_configured_iterations",
        manual="Requires Flipper IR and LCD camera access.",
        needs_camera=True,
        needs_flipper=True,
    ),
    Phase(
        name="ir-receiver-sweep",
        description="Real-IR profile sweep records whether any RC5 action reaches CONTROL.",
        node="test_live_ir_receiver_profile_sweep_records_any_state_change",
        env=(("DLCP_HW_IR_RECEIVER_SWEEP", "1"),),
        manual=(
            "Start from an active/unmuted Volume state. This diagnostic sends "
            "Hypex and standard RC5 volume/preset/mute candidates and writes "
            "MAIN-visible state deltas without requiring LCD OCR. Set "
            "DLCP_HW_IR_SWEEP_ACTIONS to narrow or expand the action list."
        ),
        needs_flipper=True,
    ),
    Phase(
        name="ir-legacy-v16b",
        description="Real-IR legacy stress baseline on stock CONTROL V1.6b.",
        node="test_live_ir_legacy_command_stress_from_volume",
        env=(
            ("DLCP_HW_IR_LEGACY_STRESS", "1"),
            ("DLCP_HW_EXPECTED_CONTROL_VERSION", "V1.6b"),
        ),
        manual=(
            "Put CONTROL in UP+DOWN bootloader: power-cycle while holding "
            "UP+DOWN for at least 6s, do not press SELECT, and retry if the "
            "LCD returns to Volume. Then flash stock CONTROL V1.6b with: "
            "scripts/flash_control_safe.sh --hex "
            "'firmware/stock/control/DLCP Control Firmware V1.6b.hex' "
            "--path '<MAIN path connected to CONTROL>' --live-timeout-s 10. "
            "After it reboots, start from Volume and confirm the rig is "
            "active/unmuted. This phase sends volume, mute, POWER "
            "standby/wake IR commands. Set DLCP_HW_IR_PROFILE=STANDARD "
            "instead of the default HYPEX if the CONTROL setup uses the "
            "standard RC5 profile."
        ),
        needs_camera=True,
        needs_flipper=True,
    ),
    Phase(
        name="ir-legacy-v171",
        description="Real-IR legacy stress on CONTROL V1.71.",
        node="test_live_ir_legacy_command_stress_from_volume",
        env=(
            ("DLCP_HW_IR_LEGACY_STRESS", "1"),
            ("DLCP_HW_EXPECTED_CONTROL_VERSION", "V1.71"),
        ),
        manual=(
            "Put CONTROL in UP+DOWN bootloader: power-cycle while holding "
            "UP+DOWN for at least 6s, do not press SELECT, and retry if the "
            "LCD returns to Volume. Then flash CONTROL V1.71 with: "
            "scripts/flash_control_safe.sh --hex "
            "firmware/patched/releases/DLCP_Control_V1.71.hex --path "
            "'<MAIN path connected to CONTROL>' --live-timeout-s 10. After "
            "it reboots, start from Volume and confirm the rig is "
            "active/unmuted. This should pass the same stress as V1.6b. Set "
            "DLCP_HW_IR_PROFILE=STANDARD instead of the default HYPEX if the "
            "CONTROL setup uses the standard RC5 profile."
        ),
        needs_camera=True,
        needs_flipper=True,
    ),
    Phase(
        name="diag-layout-pb1",
        description="PB1 Diagnostics page renders the V1.71/V3.2 Layer-5 layout.",
        node="test_live_diagnostics_page_renders_pb1_layout",
        env=(("DLCP_HW_LAYER5_AT_DIAG", "1"),),
        manual=(
            "Navigate CONTROL from Volume to PB1 Diag and wait for the display "
            "to settle, then run. This is the broad LCD layout sanity gate."
        ),
        needs_camera=True,
    ),
    Phase(
        name="diag-pb1",
        description="PB1 Diagnostics static wait populates real data, not n/a.",
        node="test_live_diagnostics_pb1_data_lands_on_real_silicon",
        env=(
            ("DLCP_HW_LAYER5_AT_DIAG", "1"),
            ("DLCP_HW_LAYER5_REQUIRE_PB1_DATA", "1"),
        ),
        manual=(
            "Navigate CONTROL from Volume to PB1 Diag, wait about 1 second "
            "without LEFT/RIGHT cycling, then run."
        ),
        needs_camera=True,
    ),
    Phase(
        name="diag-pb2",
        description="PB2 Diagnostics static wait populates real data, not n/a.",
        node="test_live_diagnostics_pb2_data_lands_on_real_silicon",
        env=(
            ("DLCP_HW_LAYER5_AT_DIAG", "1"),
            ("DLCP_HW_LAYER5_REQUIRE_PB2_DATA", "1"),
        ),
        manual=(
            "Navigate CONTROL from Volume to PB2 Diag, wait about 1 second "
            "without LEFT/RIGHT cycling, then run."
        ),
        needs_camera=True,
    ),
    Phase(
        name="diag-buttons-pb1",
        description="PB1 Diagnostics physical LEFT/RIGHT remain responsive.",
        node="test_live_manual_diagnostics_buttons_remain_responsive",
        env=(
            ("DLCP_HW_LAYER5_AT_DIAG", "1"),
            ("DLCP_HW_LAYER5_BUTTON_ACTIONS", "1"),
            ("DLCP_HW_EXPECTED_DIAG_PAGE", "PB1"),
        ),
        args=("-s",),
        manual=(
            "Navigate CONTROL to PB1 Diag and wait about 1 second. "
            "During the test, press physical RIGHT when prompted, navigate "
            "back to PB1 Diag, then press physical LEFT when prompted."
        ),
        needs_camera=True,
    ),
    Phase(
        name="diag-buttons-pb2",
        description="PB2 Diagnostics physical LEFT/RIGHT remain responsive.",
        node="test_live_manual_diagnostics_buttons_remain_responsive",
        env=(
            ("DLCP_HW_LAYER5_AT_DIAG", "1"),
            ("DLCP_HW_LAYER5_BUTTON_ACTIONS", "1"),
            ("DLCP_HW_EXPECTED_DIAG_PAGE", "PB2"),
        ),
        args=("-s",),
        manual=(
            "Navigate CONTROL to PB2 Diag and wait about 1 second. "
            "During the test, press physical RIGHT when prompted, navigate "
            "back to PB2 Diag, then press physical LEFT when prompted."
        ),
        needs_camera=True,
    ),
    Phase(
        name="diag-ir-pb1",
        description="PB1 Diagnostics dispatches IR Vol/Mute/Preset/STDBY/WAKE.",
        node="test_live_diagnostics_page_ir_actions_dispatch_on_real_silicon",
        env=(
            ("DLCP_HW_LAYER5_AT_DIAG", "1"),
            ("DLCP_HW_LAYER5_IR_ACTIONS", "1"),
            ("DLCP_HW_EXPECTED_DIAG_PAGE", "PB1"),
            ("DLCP_HW_IR_PROFILE", "HYPEX"),
        ),
        manual=(
            "Navigate CONTROL to PB1 Diag and wait about 1 second. This "
            "phase sends Hypex-profile real IR volume, mute, preset, standby, "
            "and wake; after wake the UI is expected to return to Volume."
        ),
        needs_camera=True,
        needs_flipper=True,
    ),
    Phase(
        name="diag-ir-pb2",
        description="PB2 Diagnostics dispatches IR Vol/Mute/Preset/STDBY/WAKE.",
        node="test_live_diagnostics_page_ir_actions_dispatch_on_real_silicon",
        env=(
            ("DLCP_HW_LAYER5_AT_DIAG", "1"),
            ("DLCP_HW_LAYER5_IR_ACTIONS", "1"),
            ("DLCP_HW_EXPECTED_DIAG_PAGE", "PB2"),
            ("DLCP_HW_IR_PROFILE", "HYPEX"),
        ),
        manual=(
            "Navigate CONTROL to PB2 Diag and wait about 1 second. This "
            "phase sends Hypex-profile real IR volume, mute, preset, standby, "
            "and wake; after wake the UI is expected to return to Volume."
        ),
        needs_camera=True,
        needs_flipper=True,
    ),
)

PHASE_BY_NAME = {phase.name: phase for phase in PHASES}
PHASE_ALIASES: dict[str, tuple[str, ...]] = {
    "diag-button-actions": ("diag-buttons-pb1", "diag-buttons-pb2"),
    "diag-ir-actions": ("diag-ir-pb1", "diag-ir-pb2"),
}
BUG_PHASES: dict[str, tuple[str, ...]] = {
    "BUG-REV-01": ("identity",),
    "BUG-SETTINGS-01": ("settings", "identity", "ir-receiver-sweep"),
    "BUG-PRESET-01": (
        "identity",
        "front-panel-preset-a",
        "front-panel-preset-b",
    ),
    "BUG-PRESET-02": (
        "rapid-toggle",
        "front-panel-preset-a",
        "front-panel-preset-b",
    ),
    "BUG-PRESET-03": (
        "front-panel-preset-a",
        "front-panel-preset-b",
        "preset-convergence",
        "rapid-toggle",
    ),
    "BUG-STDBY-01": (
        "front-panel-standby-wake",
        "preset-standby-wake",
        "reconnect-soak",
    ),
    "BUG-IR-01": ("ir-receiver-sweep", "ir-legacy-v16b", "ir-legacy-v171"),
    "BUG-IR-02": ("diag-ir-actions", "preset-mute", "preset-standby-wake"),
    "BUG-DIAG-01": ("diag-layout-pb1", "diag-pb1", "diag-pb2"),
    "BUG-DIAG-02": (
        "diag-pb1",
        "diag-pb2",
        "diag-button-actions",
        "diag-ir-actions",
    ),
}


def _resolve_python() -> str:
    here = REPO_ROOT / ".venv_ep0" / "bin" / "python"
    if here.exists():
        return str(here)
    try:
        common = subprocess.check_output(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return sys.executable
    candidate = Path(common).resolve().parent / ".venv_ep0" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def _shell_command(env: tuple[tuple[str, str], ...], cmd: list[str]) -> str:
    env_prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in env)
    rendered_cmd = " ".join(shlex.quote(part) for part in cmd)
    if env_prefix:
        return f"{env_prefix} {rendered_cmd}"
    return rendered_cmd


def _control_hex_identity_for_phase(phase: Phase) -> dict[str, object] | None:
    hex_paths = {
        "ir-legacy-v16b": EVIDENCE_FILE_PATHS["control_v16b_hex"],
        "ir-legacy-v171": EVIDENCE_FILE_PATHS["control_v171_hex"],
    }
    hex_path = hex_paths.get(phase.name)
    if hex_path is None:
        return None

    from dlcp_fw.flash import dlcp_control_flash

    hex_mem = dlcp_control_flash.parse_intel_hex(str(hex_path))
    release = dlcp_control_flash.detect_static_hex_control_release_info(hex_mem)
    preflight = dlcp_control_flash.run_preflight(
        hex_mem=hex_mem,
        bootloader_ref_mem=None,
        require_bootloader_match=False,
    )
    return {
        "path": str(hex_path.relative_to(REPO_ROOT)),
        "release_short": dlcp_control_flash._format_control_release_short(release),
        "payload_len": preflight["payload_len"],
        "payload_crc": preflight["payload_crc"],
        "payload_sha256": preflight["payload_sha256"],
        "app_sha256": preflight["app_sha256"],
        "boot_sha256": preflight["boot_sha256"],
    }


def _phase_payload(
    phase: Phase,
    python: str | None = None,
    extra_pytest_args: tuple[str, ...] = (),
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": phase.name,
        "description": phase.description,
        "node": phase.node,
        "env": dict(phase.env),
        "required_env": list(phase.required_env),
        "args": list(phase.args),
        "manual": phase.manual,
        "main_requirement": phase.main_requirement,
        "needs_camera": phase.needs_camera,
        "needs_flipper": phase.needs_flipper,
    }
    control_hex = _control_hex_identity_for_phase(phase)
    if control_hex is not None:
        payload["expected_control_hex"] = control_hex
    if python is not None:
        cmd = phase.command(python, extra_pytest_args)
        payload["command"] = cmd
        payload["shell_command"] = _shell_command(phase.env, cmd)
    return payload


def _print_phase(
    phase: Phase,
    python: str,
    extra_pytest_args: tuple[str, ...],
) -> None:
    print(f"\n[{phase.name}] {phase.description}")
    if phase.manual:
        print(f"  Manual precondition: {phase.manual}")
    control_hex = _control_hex_identity_for_phase(phase)
    if control_hex is not None:
        print(
            "  Expected CONTROL hex: "
            f"{control_hex['path']} "
            f"({control_hex['release_short']}, "
            f"crc16=0x{control_hex['payload_crc']:04X})"
        )
    if phase.required_env:
        print(f"  Required env: {', '.join(phase.required_env)}")
    print(f"  Command: {_shell_command(phase.env, phase.command(python, extra_pytest_args))}")


def _pytest_junit_counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    suites = [root] if local_name(root.tag) == "testsuite" else [
        node for node in root.iter() if local_name(node.tag) == "testsuite"
    ]
    counts = {"tests": 0, "skipped": 0, "failures": 0, "errors": 0}
    for suite in suites:
        for key in counts:
            counts[key] += int(suite.attrib.get(key, "0") or "0")
    return counts


def _run_phase(
    phase: Phase,
    python: str,
    extra_pytest_args: tuple[str, ...],
    pause: bool,
) -> int:
    _print_phase(phase, python, extra_pytest_args)
    if pause:
        input("  Press Enter to run this phase, or Ctrl-C to stop. ")

    env = os.environ.copy()
    env.update(dict(phase.env))
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"dlcp-{phase.name}-") as tmp_dir:
        junit_path = Path(tmp_dir) / "pytest-junit.xml"
        cmd = phase.command(python, extra_pytest_args) + [
            "--junitxml",
            str(junit_path),
        ]
        cp = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
        junit_error: str | None = None
        try:
            junit_counts = _pytest_junit_counts(junit_path)
        except Exception as exc:
            junit_counts = {"tests": 0, "skipped": 0, "failures": 0, "errors": 0}
            junit_error = str(exc)
    elapsed = time.monotonic() - started
    skipped_without_pass = (
        cp.returncode == 0
        and junit_counts["tests"] > 0
        and junit_counts["skipped"] == junit_counts["tests"]
    )
    unverified_success = cp.returncode == 0 and junit_error is not None
    phase_rc = 1 if skipped_without_pass or unverified_success else cp.returncode
    if phase_rc == 0:
        print(f"  PASS [{phase.name}] in {elapsed:.1f} s", flush=True)
    else:
        if skipped_without_pass:
            print(
                f"  FAIL [{phase.name}] skipped without passing a hardware test",
                file=sys.stderr,
                flush=True,
            )
        if unverified_success:
            print(
                f"  FAIL [{phase.name}] could not verify pytest JUnit results: "
                f"{junit_error}",
                file=sys.stderr,
                flush=True,
            )
        print(
            f"  FAIL [{phase.name}] exit {phase_rc} after {elapsed:.1f} s",
            file=sys.stderr,
            flush=True,
        )
    return phase_rc


def _run_collect(python: str) -> int:
    cmd = [
        python,
        "-m",
        "pytest",
        TEST_FILE,
        "--collect-only",
        "-q",
    ]
    print(f"+ {' '.join(shlex.quote(part) for part in cmd)}", flush=True)
    return subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode


def _looks_like_external_lcd_camera(name: str) -> bool:
    lowered = name.strip().lower()
    if not lowered:
        return False
    return not any(token in lowered for token in HOST_CAMERA_NAME_SUBSTRINGS)


def _required_env_validation_error(name: str, value: str) -> str | None:
    if name not in {
        "DLCP_HW_EXPECTED_VOLUME_LOW",
        "DLCP_HW_EXPECTED_INPUT",
        "DLCP_HW_EXPECTED_SETUP_PROFILE",
    }:
        return None
    try:
        parsed = int(value, 0)
    except ValueError:
        return "must be an integer literal, for example 0xE2"
    if not 0 <= parsed <= 0xFF:
        return f"must be a byte value in 0x00..0xFF, got {value!r}"
    return None


def _preflight_with_report(phases: list[Phase]) -> tuple[int, dict[str, object]]:
    from dlcp_fw.cli import hardware_state_test as hw

    needs_main_pair = any(phase.main_requirement == "pair" for phase in phases)
    needs_any_main = needs_main_pair or any(
        phase.main_requirement == "any" for phase in phases
    )
    needs_camera = any(phase.needs_camera for phase in phases)
    needs_flipper = any(phase.needs_flipper for phase in phases)
    required_env_names = sorted(
        {name for phase in phases for name in phase.required_env}
    )
    failures: list[str] = []
    report: dict[str, object] = {
        "phases": [phase.name for phase in phases],
        "requirements": {
            "main": "pair" if needs_main_pair else ("any" if needs_any_main else "none"),
            "camera": needs_camera,
            "flipper": needs_flipper,
            "env": required_env_names,
        },
        "failures": failures,
    }

    print("Hardware preflight")
    print(f"  phases: {', '.join(phase.name for phase in phases)}")
    if required_env_names:
        env_report: dict[str, object] = {
            name: bool(os.environ.get(name)) for name in required_env_names
        }
        report["env"] = env_report
        print("  required env:")
        for name in required_env_names:
            present = "set" if env_report[name] else "missing"
            validation_error = (
                _required_env_validation_error(name, os.environ[name])
                if env_report[name]
                else None
            )
            if validation_error is not None:
                present = f"invalid ({validation_error})"
            print(f"    {name}: {present}")
            if not env_report[name]:
                failures.append(f"missing required env {name}")
            elif validation_error is not None:
                failures.append(f"invalid required env {name}: {validation_error}")

    if needs_any_main:
        main_error: str | None = None
        try:
            states = hw._collect_main_roles(vid=hw.DEFAULT_VID, pid=hw.DEFAULT_PID)
        except Exception as exc:
            states = []
            main_error = str(exc)
            failures.append(f"MAIN HID probe failed: {exc}")
        print(f"  MAIN HID devices: {len(states)}")
        devices: list[dict[str, object]] = []
        for state in states:
            devices.append(
                {
                    "role": state.role,
                    "mode": state.mode,
                    "version": state.version,
                    "active_preset": state.active_preset,
                    "active_config_name": state.active_config_name,
                    "path": state.path,
                }
            )
            print(
                "    "
                f"{state.role:<7} mode={state.mode or '?':<4} "
                f"version={state.version or '?':<4} "
                f"preset={state.active_preset or '?':<1} "
                f"name={state.active_config_name or '<empty>'!r} "
                f"path={state.path}"
            )
        if not states:
            failures.append("no MAIN HID devices visible")
        elif needs_main_pair:
            try:
                hw._assert_left_right_roles(states)
            except Exception as exc:
                failures.append(f"MAIN pair check failed: {exc}")
        main_report: dict[str, object] = {"count": len(states), "devices": devices}
        if main_error is not None:
            main_report["error"] = main_error
        report["main"] = main_report

    if needs_camera:
        if os.environ.get("DLCP_HW_CAMERA_SELECTOR"):
            report["camera"] = {
                "selector": os.environ["DLCP_HW_CAMERA_SELECTOR"],
                "explicit_selector": True,
            }
            print(
                "  camera: using DLCP_HW_CAMERA_SELECTOR="
                f"{os.environ['DLCP_HW_CAMERA_SELECTOR']!r}"
            )
        else:
            camera_error: str | None = None
            try:
                cameras = hw._load_avfoundation_video_devices()
            except Exception as exc:
                cameras = []
                camera_error = str(exc)
                failures.append(f"camera inventory failed: {exc}")
            print(f"  cameras: {len(cameras)}")
            for camera in cameras:
                print(f"    [{camera.index}] {camera.name}")
            if not cameras:
                failures.append(
                    "no LCD camera visible; set DLCP_HW_CAMERA_SELECTOR or connect the camera"
                )
            else:
                lcd_candidates = [
                    camera
                    for camera in cameras
                    if _looks_like_external_lcd_camera(camera.name)
                ]
                print(f"  external LCD camera candidates: {len(lcd_candidates)}")
                for camera in lcd_candidates:
                    print(f"    [{camera.index}] {camera.name}")
                if not lcd_candidates:
                    failures.append(
                        "no external LCD camera candidate visible; set "
                        "DLCP_HW_CAMERA_SELECTOR if one of the listed cameras "
                        "is intentionally pointed at the DLCP LCD"
                    )
            camera_report: dict[str, object] = {
                "explicit_selector": False,
                "cameras": [
                    {"index": camera.index, "name": camera.name}
                    for camera in cameras
                ],
                "external_lcd_candidates": [
                    {"index": camera.index, "name": camera.name}
                    for camera in (
                        [
                            camera
                            for camera in cameras
                            if _looks_like_external_lcd_camera(camera.name)
                        ]
                        if cameras
                        else []
                    )
                ],
            }
            if camera_error is not None:
                camera_report["error"] = camera_error
            report["camera"] = camera_report

    if needs_flipper:
        if os.environ.get("DLCP_HW_FLIPPER_PORT"):
            report["flipper"] = {
                "selector": os.environ["DLCP_HW_FLIPPER_PORT"],
                "explicit_selector": True,
            }
            print(
                "  Flipper: using DLCP_HW_FLIPPER_PORT="
                f"{os.environ['DLCP_HW_FLIPPER_PORT']!r}"
            )
        else:
            flipper_error: str | None = None
            try:
                ports = hw.hardware_flipper_ir.discover_flipper_serial_ports()
            except Exception as exc:
                ports = []
                flipper_error = str(exc)
                failures.append(f"Flipper serial discovery failed: {exc}")
            print(f"  Flipper serial candidates: {len(ports)}")
            for port in ports:
                print(f"    {port}")
            if not ports:
                failures.append(
                    "no Flipper serial port visible; set DLCP_HW_FLIPPER_PORT or connect Flipper"
                )
            flipper_report: dict[str, object] = {
                "explicit_selector": False,
                "ports": list(ports),
            }
            if flipper_error is not None:
                flipper_report["error"] = flipper_error
            report["flipper"] = flipper_report

    if failures:
        print("\nPreflight FAIL")
        for item in failures:
            print(f"  - {item}")
        report["status"] = "FAIL"
        report["returncode"] = 1
        return 1, report

    print("\nPreflight PASS")
    report["status"] = "PASS"
    report["returncode"] = 0
    return 0, report


def _preflight(phases: list[Phase]) -> int:
    rc, _report = _preflight_with_report(phases)
    return rc


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Report written: {path}")


def _default_report_path(args: argparse.Namespace) -> Path:
    if args.execute:
        mode = "execute"
    elif args.preflight:
        mode = "preflight"
    elif args.audit_completion:
        mode = "audit-completion"
    else:
        mode = "report"
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    selectors = list(args.bug or args.phase or ["all"])
    safe_selector = "_".join(
        "".join(ch if ch.isalnum() else "-" for ch in selector).strip("-").lower()
        for selector in selectors
    )
    if not safe_selector:
        safe_selector = "all"
    return (
        REPO_ROOT
        / "artifacts"
        / "probes"
        / "v171_v32_ledger_gate"
        / f"{stamp}_{mode}_{safe_selector}.json"
    )


def _stable_artifact_summary_report_path() -> Path:
    return (
        REPO_ROOT
        / "artifacts"
        / "probes"
        / "v171_v32_ledger_gate"
        / "artifact_summary_current.json"
    )


def _safe_bug_id(bug_id: str) -> str:
    return bug_id.lower().replace("-", "_")


def _stable_bug_preflight_report_path(bug_id: str) -> Path:
    return (
        Path("artifacts")
        / "probes"
        / "v171_v32_ledger_gate"
        / f"{_safe_bug_id(bug_id)}_preflight_current.json"
    )


def _stable_bug_closure_report_path(bug_id: str) -> Path:
    return (
        Path("artifacts")
        / "probes"
        / "v171_v32_ledger_gate"
        / f"{_safe_bug_id(bug_id)}_closure_current.json"
    )


def _stable_remaining_preflight_report_path() -> Path:
    return (
        Path("artifacts")
        / "probes"
        / "v171_v32_ledger_gate"
        / "remaining_preflight_current.json"
    )


def _stable_remaining_closure_report_path() -> Path:
    return (
        Path("artifacts")
        / "probes"
        / "v171_v32_ledger_gate"
        / "remaining_closure_current.json"
    )


def _append_phase_selector(
    selected: list[Phase],
    seen: set[str],
    name: str,
) -> None:
    phase_names = PHASE_ALIASES.get(name, (name,))
    for phase_name in phase_names:
        if phase_name in seen:
            continue
        selected.append(PHASE_BY_NAME[phase_name])
        seen.add(phase_name)


def _selected_phases(phase_names: list[str], bug_names: list[str]) -> list[Phase]:
    if "all" in phase_names:
        return list(PHASES)
    if not phase_names and not bug_names:
        return list(PHASES)
    selected: list[Phase] = []
    seen: set[str] = set()
    for name in phase_names:
        _append_phase_selector(selected, seen, name)
    for bug_name in bug_names:
        for phase_name in BUG_PHASES[bug_name]:
            _append_phase_selector(selected, seen, phase_name)
    return selected


def _print_list(phases: list[Phase]) -> None:
    print("Phase selectors:")
    for phase in PHASES:
        requirements: list[str] = []
        if phase.main_requirement == "any":
            requirements.append("MAIN")
        elif phase.main_requirement == "pair":
            requirements.append("MAIN pair")
        if phase.needs_camera:
            requirements.append("camera")
        if phase.needs_flipper:
            requirements.append("Flipper")
        if phase.required_env:
            requirements.append(f"env: {', '.join(phase.required_env)}")
        suffix = f" ({', '.join(requirements)})" if requirements else ""
        control_hex = _control_hex_identity_for_phase(phase)
        if control_hex is not None:
            suffix = (
                f"{suffix} [CONTROL {control_hex['release_short']}, "
                f"crc16=0x{control_hex['payload_crc']:04X}]"
            )
        print(f"  {phase.name}: {phase.description}{suffix}")

    print("\nAlias selectors:")
    for alias, phase_names in sorted(PHASE_ALIASES.items()):
        print(f"  {alias}: {', '.join(phase_names)}")

    print("\nBug selectors:")
    for bug_id, selectors in sorted(BUG_PHASES.items()):
        expanded = ", ".join(phase.name for phase in _selected_phases([], [bug_id]))
        print(f"  {bug_id}: {', '.join(selectors)} -> {expanded}")

    print("\nSelected phases:")
    print(f"  {', '.join(phase.name for phase in phases)}")


def _active_ledger_rows() -> dict[str, list[str]]:
    text = LEDGER_PATH.read_text(encoding="utf-8")
    active_table = text.split("## Current Verification Snapshot", 1)[0]
    rows: dict[str, list[str]] = {}
    for line in active_table.splitlines():
        if not line.startswith("| BUG-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        rows[cells[0]] = cells
    return rows


def _active_ledger_statuses() -> dict[str, str]:
    statuses: dict[str, str] = {}
    for bug_id, cells in _active_ledger_rows().items():
        statuses[bug_id] = cells[1]
    return statuses


def _completion_audit_evidence_lines() -> dict[str, str]:
    text = LEDGER_PATH.read_text(encoding="utf-8")
    try:
        audit = text.split("## Completion Audit", 1)[1].split(
            "Additional live hardware gate added",
            1,
        )[0]
    except IndexError:
        return {}
    rows: dict[str, str] = {}
    for line in audit.splitlines():
        if not line.startswith("| BUG-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells:
            rows[cells[0]] = line
    return rows


def _has_strong_done_evidence(evidence_line: str) -> bool:
    if "DONE:" not in evidence_line:
        return False
    lowered = evidence_line.lower()
    has_pass_result = "pass" in lowered
    has_artifact_or_command = "artifacts/probes/" in evidence_line or "->" in evidence_line
    return has_pass_result and has_artifact_or_command


def _remaining_bug_payloads(
    python: str,
    selected_bug_names: list[str],
) -> list[dict[str, object]]:
    statuses = _active_ledger_statuses()
    candidate_bug_ids = selected_bug_names or sorted(statuses)
    bug_ids = [bug_id for bug_id in candidate_bug_ids if statuses[bug_id] != "done"]
    script = str(Path("scripts") / "run_v171_v32_ledger_hardware_gate.py")
    payloads: list[dict[str, object]] = []
    for bug_id in bug_ids:
        status = statuses[bug_id]
        phases = _selected_phases([], [bug_id])
        expected_control_hex = {
            phase.name: control_hex
            for phase in phases
            if (control_hex := _control_hex_identity_for_phase(phase)) is not None
        }
        required_env = sorted({name for phase in phases for name in phase.required_env})
        preflight_report = _stable_bug_preflight_report_path(bug_id)
        closure_report = _stable_bug_closure_report_path(bug_id)
        preflight = [
            python,
            script,
            "--preflight",
            "--bug",
            bug_id,
            "--report-json",
            str(preflight_report),
        ]
        execute = [
            python,
            script,
            "--execute",
            "--keep-going",
            "--bug",
            bug_id,
            "--require-bug-closed",
            bug_id,
            "--report-json",
            str(closure_report),
        ]
        payloads.append(
            {
                "bug": bug_id,
                "status": status,
                "phases": [phase.name for phase in phases],
                "required_env": required_env,
                **(
                    {"expected_control_hex": expected_control_hex}
                    if expected_control_hex
                    else {}
                ),
                "preflight_report": str(preflight_report),
                "closure_report": str(closure_report),
                "preflight": preflight,
                "preflight_shell_command": _shell_command((), preflight),
                "execute": execute,
                "execute_shell_command": _shell_command((), execute),
            }
        )
    return payloads


def _prompt_to_artifact_checklist(
    *,
    statuses: dict[str, str],
    artifact_summary: dict[str, object],
    done_without_evidence: list[str],
    done_with_weak_evidence: list[str],
    evidence_lines: dict[str, str],
) -> dict[str, object]:
    active_rows = _active_ledger_rows()
    artifact_rows = {
        str(row["bug"]): row
        for row in artifact_summary.get("rows", [])
        if isinstance(row, dict) and row.get("bug") is not None
    }
    bugs: list[dict[str, object]] = []
    for bug_id, ledger_status in sorted(statuses.items()):
        artifact_row = artifact_rows.get(bug_id, {})
        hardware_phases = [
            phase.name for phase in _selected_phases([], [bug_id])
        ]
        ledger_cells = active_rows.get(bug_id, [])
        required_sim_evidence = ledger_cells[4] if len(ledger_cells) >= 5 else ""
        blocking_reasons: list[str] = []
        if not required_sim_evidence:
            blocking_reasons.append("missing_required_sim_evidence")
        if not hardware_phases:
            blocking_reasons.append("missing_hardware_phase_mapping")
        if ledger_status == "done":
            if bug_id in done_without_evidence:
                blocking_reasons.append("done_row_missing_done_evidence")
            if bug_id in done_with_weak_evidence:
                blocking_reasons.append("done_row_weak_done_evidence")
            ready_to_mark_done = not blocking_reasons
        else:
            blocking_reasons.append("ledger_status_not_done")
            artifact_status = artifact_row.get("artifact_status")
            if artifact_status != "passed":
                blocking_reasons.append("hardware_artifacts_not_ready")
            ready_to_mark_done = False
        bugs.append(
            {
                "bug": bug_id,
                "ledger_status": ledger_status,
                "done_evidence": (
                    evidence_lines.get(bug_id, "") if ledger_status == "done" else ""
                ),
                "required_sim_evidence": required_sim_evidence,
                "hardware_phases": hardware_phases,
                "preflight_report": artifact_row.get("preflight_report"),
                "closure_report": artifact_row.get("closure_report"),
                "artifact_status": artifact_row.get("artifact_status"),
                "preflight_status": artifact_row.get("preflight_status"),
                "preflight_identity_status": artifact_row.get(
                    "preflight_identity_status"
                ),
                "preflight_missing_required_phases": artifact_row.get(
                    "preflight_missing_required_phases",
                    [],
                ),
                "preflight_failures": artifact_row.get("preflight_failures", []),
                "closure_identity_status": artifact_row.get(
                    "closure_identity_status"
                ),
                "bug_closure_status": artifact_row.get("bug_closure_status"),
                "ready_to_mark_done": ready_to_mark_done,
                "blocking_reasons": blocking_reasons,
            }
        )
    blocking_bugs = [
        {
            "bug": str(item["bug"]),
            "blocking_reasons": list(item["blocking_reasons"]),
        }
        for item in bugs
        if item["blocking_reasons"]
    ]
    return {
        "objective": (
            "each active implementation bug has simulator evidence in the "
            "ledger, current live-hardware preflight and closure artifacts, "
            "and explicit DONE evidence before the ledger is complete"
        ),
        "sim_gate": {
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
        },
        "complete": not blocking_bugs,
        "blocking_bugs": blocking_bugs,
        "bugs": bugs,
    }


def _remaining_plan_payload(
    python: str,
    payloads: list[dict[str, object]],
) -> dict[str, object] | None:
    bug_ids = [str(payload["bug"]) for payload in payloads]
    if not bug_ids:
        return None
    script = str(Path("scripts") / "run_v171_v32_ledger_hardware_gate.py")
    preflight_report = _stable_remaining_preflight_report_path()
    closure_report = _stable_remaining_closure_report_path()
    preflight = [python, script, "--preflight"]
    execute = [python, script, "--execute", "--keep-going"]
    for bug_id in bug_ids:
        preflight.extend(["--bug", bug_id])
        execute.extend(["--bug", bug_id])
    preflight.extend(
        [
            "--mirror-selected-bug-reports",
            "--report-json",
            str(preflight_report),
        ]
    )
    for bug_id in bug_ids:
        execute.extend(["--require-bug-closed", bug_id])
    execute.extend(
        [
            "--mirror-selected-bug-reports",
            "--report-json",
            str(closure_report),
        ]
    )
    phases: list[str] = []
    seen: set[str] = set()
    required_env: set[str] = set()
    expected_control_hex: dict[str, object] = {}
    for payload in payloads:
        required_env.update(str(name) for name in payload.get("required_env", []))
        expected_control_hex.update(
            {
                str(phase): identity
                for phase, identity in (
                    payload.get("expected_control_hex", {}) or {}
                ).items()
            }
        )
        for phase in payload["phases"]:
            phase_name = str(phase)
            if phase_name in seen:
                continue
            seen.add(phase_name)
            phases.append(phase_name)
    return {
        "bugs": bug_ids,
        "phases": phases,
        "required_env": sorted(required_env),
        **(
            {"expected_control_hex": expected_control_hex}
            if expected_control_hex
            else {}
        ),
        "preflight_report": str(preflight_report),
        "closure_report": str(closure_report),
        "preflight": preflight,
        "preflight_shell_command": _shell_command((), preflight),
        "execute": execute,
        "execute_shell_command": _shell_command((), execute),
    }


def _print_remaining_bugs(
    python: str,
    selected_bug_names: list[str],
) -> list[dict[str, object]]:
    payloads = _remaining_bug_payloads(python, selected_bug_names)
    if not payloads:
        print("No remaining non-done ledger bugs.")
        return payloads

    print("Remaining ledger bugs:")
    for payload in payloads:
        phases = ", ".join(str(phase) for phase in payload["phases"])
        print(f"  {payload['bug']} [{payload['status']}]")
        print(f"    phases: {phases}")
        if payload["required_env"]:
            print(f"    required env: {', '.join(str(name) for name in payload['required_env'])}")
        for phase_name, identity in (
            payload.get("expected_control_hex", {}) or {}
        ).items():
            print(
                f"    expected CONTROL {phase_name}: {identity['path']} "
                f"({identity['release_short']}, "
                f"crc16=0x{identity['payload_crc']:04X})"
            )
        print(f"    preflight: {payload['preflight_shell_command']}")
        print(f"    execute: {payload['execute_shell_command']}")
    plan = _remaining_plan_payload(python, payloads)
    if plan is not None:
        print("  combined:")
        print(f"    phases: {', '.join(str(phase) for phase in plan['phases'])}")
        if plan["required_env"]:
            print(f"    required env: {', '.join(str(name) for name in plan['required_env'])}")
        for phase_name, identity in (
            plan.get("expected_control_hex", {}) or {}
        ).items():
            print(
                f"    expected CONTROL {phase_name}: {identity['path']} "
                f"({identity['release_short']}, "
                f"crc16=0x{identity['payload_crc']:04X})"
            )
        print(f"    preflight: {plan['preflight_shell_command']}")
        print(f"    execute: {plan['execute_shell_command']}")
    return payloads


def _completion_audit_payload(python: str) -> dict[str, object]:
    statuses = _active_ledger_statuses()
    remaining = _remaining_bug_payloads(python, selected_bug_names=[])
    done = sorted(bug_id for bug_id, status in statuses.items() if status == "done")
    evidence_lines = _completion_audit_evidence_lines()
    done_without_evidence = [
        bug_id for bug_id in done if "DONE:" not in evidence_lines.get(bug_id, "")
    ]
    done_with_weak_evidence = [
        bug_id
        for bug_id in done
        if "DONE:" in evidence_lines.get(bug_id, "")
        and not _has_strong_done_evidence(evidence_lines.get(bug_id, ""))
    ]
    counts: dict[str, int] = {}
    for status in statuses.values():
        counts[status] = counts.get(status, 0) + 1
    artifact_summary = _artifact_summary_payload(python)
    prompt_to_artifact_checklist = _prompt_to_artifact_checklist(
        statuses=statuses,
        artifact_summary=artifact_summary,
        done_without_evidence=done_without_evidence,
        done_with_weak_evidence=done_with_weak_evidence,
        evidence_lines=evidence_lines,
    )
    checklist = [
        {
            "id": "all_active_bugs_done",
            "passed": not remaining,
            "evidence": (
                "all active ledger rows are done"
                if not remaining
                else f"{len(remaining)} active rows are not done"
            ),
        },
        {
            "id": "done_rows_have_done_evidence",
            "passed": not done_without_evidence and not done_with_weak_evidence,
            "evidence": (
                "every done row has DONE evidence"
                if not done_without_evidence and not done_with_weak_evidence
                else "; ".join(
                    part
                    for part in (
                        (
                            "missing DONE evidence: "
                            + ", ".join(done_without_evidence)
                            if done_without_evidence
                            else ""
                        ),
                        (
                            "weak DONE evidence: "
                            + ", ".join(done_with_weak_evidence)
                            if done_with_weak_evidence
                            else ""
                        ),
                    )
                    if part
                )
            ),
        },
        {
            "id": "hardware_artifacts_ready",
            "passed": not artifact_summary["not_ready_bugs"],
            "evidence": (
                "no hardware artifact readiness gaps"
                if not artifact_summary["not_ready_bugs"]
                else "not ready: "
                + ", ".join(str(bug) for bug in artifact_summary["not_ready_bugs"])
            ),
        },
        {
            "id": "prompt_to_artifact_checklist_ready",
            "passed": bool(prompt_to_artifact_checklist["complete"]),
            "evidence": (
                "no prompt-to-artifact blockers"
                if prompt_to_artifact_checklist["complete"]
                else "blocked: "
                + ", ".join(
                    str(item["bug"])
                    for item in prompt_to_artifact_checklist["blocking_bugs"]
                )
            ),
        },
    ]
    return {
        "complete": all(bool(item["passed"]) for item in checklist),
        "status_counts": counts,
        "done_bugs": done,
        "done_without_evidence": done_without_evidence,
        "done_with_weak_evidence": done_with_weak_evidence,
        "remaining_bugs": remaining,
        "artifact_summary": artifact_summary,
        "completion_checklist": checklist,
        "prompt_to_artifact_checklist": prompt_to_artifact_checklist,
    }


def _print_completion_audit(python: str) -> dict[str, object]:
    payload = _completion_audit_payload(python)
    remaining = payload["remaining_bugs"]
    done = payload["done_bugs"]
    if payload["complete"]:
        print("Completion audit: COMPLETE")
    else:
        print("Completion audit: NOT COMPLETE")
    if done:
        print(f"  done: {', '.join(str(bug_id) for bug_id in done)}")
    done_without_evidence = payload["done_without_evidence"]
    if done_without_evidence:
        print(
            "  done rows missing DONE evidence: "
            f"{', '.join(str(bug_id) for bug_id in done_without_evidence)}"
        )
    done_with_weak_evidence = payload["done_with_weak_evidence"]
    if done_with_weak_evidence:
        print(
            "  done rows with weak DONE evidence: "
            f"{', '.join(str(bug_id) for bug_id in done_with_weak_evidence)}"
        )
    if remaining:
        print("  remaining:")
        for item in remaining:
            print(f"    {item['bug']} [{item['status']}]")
            print(f"      execute: {item['execute_shell_command']}")
        audit_cmd = [
            python,
            str(Path("scripts") / "run_v171_v32_ledger_hardware_gate.py"),
            "--remaining",
        ]
        print(f"  next: run {_shell_command((), audit_cmd)}")
    artifact_summary = payload["artifact_summary"]
    ready = artifact_summary["ready_to_mark_done"]
    not_ready = artifact_summary["not_ready_bugs"]
    print(
        f"  artifact readiness: {len(ready)} ready, {len(not_ready)} not ready"
    )
    print("  checklist:")
    for item in payload["completion_checklist"]:
        mark = "PASS" if item["passed"] else "FAIL"
        print(f"    {mark} {item['id']}: {item['evidence']}")
    prompt_checklist = payload["prompt_to_artifact_checklist"]
    prompt_bugs = prompt_checklist["bugs"]
    prompt_ready = [
        item for item in prompt_bugs if item["ready_to_mark_done"]
    ]
    print(
        "  prompt-to-artifact: "
        f"{len(prompt_ready)} ready, "
        f"{len(prompt_bugs) - len(prompt_ready)} blocked"
    )
    return payload


def _read_report_json(path: Path) -> dict[str, object] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ledger_contract_text() -> str:
    text = LEDGER_PATH.read_text(encoding="utf-8")
    return text.split(
        "Hardware phase map for `scripts/run_v171_v32_ledger_hardware_gate.py --bug`:",
        1,
    )[1].split("## Completion Audit", 1)[0]


def _current_evidence_identity() -> dict[str, object]:
    return {
        "schema": REPORT_SCHEMA_VERSION,
        "ledger_contract": {
            "path": str(LEDGER_PATH.relative_to(REPO_ROOT)),
            "section": "hardware phase map",
            "sha256": hashlib.sha256(
                _ledger_contract_text().encode("utf-8")
            ).hexdigest(),
        },
        "files": {
            name: {
                "path": str(path.relative_to(REPO_ROOT)),
                "sha256": _file_sha256(path),
            }
            for name, path in sorted(EVIDENCE_FILE_PATHS.items())
        },
    }


def _report_identity_status(
    report: dict[str, object] | None,
    current_identity: dict[str, object],
) -> str:
    if report is None:
        return "missing"
    identity = report.get("evidence_identity")
    if not isinstance(identity, dict):
        return "missing"
    return "current" if identity == current_identity else "stale"


def _selected_phase_names_from_report(report: dict[str, object] | None) -> set[str]:
    if report is None:
        return set()
    selected_phases = report.get("selected_phases", [])
    if not isinstance(selected_phases, list):
        return set()
    return {
        str(phase["name"])
        for phase in selected_phases
        if isinstance(phase, dict) and phase.get("name") is not None
    }


def _artifact_summary_payload(python: str) -> dict[str, object]:
    statuses = _active_ledger_statuses()
    current_identity = _current_evidence_identity()
    remaining_by_bug = {
        str(item["bug"]): item
        for item in _remaining_bug_payloads(python, selected_bug_names=[])
    }
    rows: list[dict[str, object]] = []
    ready_to_mark_done: list[str] = []
    for bug_id, ledger_status in sorted(statuses.items()):
        required_phases = [phase.name for phase in _selected_phases([], [bug_id])]
        if ledger_status == "done":
            rows.append(
                {
                    "bug": bug_id,
                    "ledger_status": ledger_status,
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
            )
            continue

        remaining = remaining_by_bug[bug_id]
        preflight_report = str(remaining["preflight_report"])
        preflight = _read_report_json(REPO_ROOT / preflight_report)
        preflight_identity_status = _report_identity_status(
            preflight,
            current_identity,
        )
        preflight_selected = _selected_phase_names_from_report(preflight)
        preflight_missing_required_phases = [
            phase for phase in required_phases if phase not in preflight_selected
        ]
        if preflight is None:
            preflight_status = "missing"
            preflight_failures: list[str] = []
        else:
            preflight_payload = preflight.get("preflight", {})
            if isinstance(preflight_payload, dict):
                preflight_status = str(preflight_payload.get("status", "unknown"))
                failures = preflight_payload.get("failures", [])
                preflight_failures = [
                    str(failure) for failure in failures
                ] if isinstance(failures, list) else []
            else:
                preflight_status = "unknown"
                preflight_failures = []
        closure_report = str(remaining["closure_report"])
        report_path = REPO_ROOT / closure_report
        report = _read_report_json(report_path)
        if report is None:
            rows.append(
                {
                    "bug": bug_id,
                    "ledger_status": ledger_status,
                    "artifact_status": "missing",
                    "preflight_status": preflight_status,
                    "preflight_identity_status": preflight_identity_status,
                    "preflight_missing_required_phases": preflight_missing_required_phases,
                    "preflight_report": preflight_report,
                    "preflight_failures": preflight_failures,
                    "closure_report": closure_report,
                    "closure_identity_status": "missing",
                    "bug_closure_status": None,
                    "final_rc": None,
                }
            )
            continue

        closure_identity_status = _report_identity_status(
            report,
            current_identity,
        )
        closure = report.get("bug_closure", {})
        if not isinstance(closure, dict) or not isinstance(closure.get(bug_id), dict):
            reported_bug_status = None
        else:
            reported_bug_status = str(closure[bug_id].get("status"))
        computed_closure = _bug_closure_report(report).get(bug_id, {})
        bug_status = (
            str(computed_closure.get("status"))
            if isinstance(computed_closure, dict)
            else None
        )
        final_rc = report.get("final_rc")
        if bug_status == "passed":
            if closure_identity_status != "current":
                artifact_status = f"passed_closure_{closure_identity_status}"
            elif preflight_identity_status != "current":
                artifact_status = f"passed_preflight_{preflight_identity_status}"
            elif preflight_missing_required_phases:
                artifact_status = "passed_preflight_missing_required_phases"
            elif preflight_status == "PASS":
                artifact_status = "passed"
                ready_to_mark_done.append(bug_id)
            else:
                artifact_status = f"passed_preflight_{preflight_status.lower()}"
        elif bug_status in {"failed", "missing", "partial", "not_run"}:
            artifact_status = bug_status
        else:
            artifact_status = "unknown"
        rows.append(
            {
                "bug": bug_id,
                "ledger_status": ledger_status,
                "artifact_status": artifact_status,
                "preflight_status": preflight_status,
                "preflight_identity_status": preflight_identity_status,
                "preflight_missing_required_phases": preflight_missing_required_phases,
                "preflight_report": preflight_report,
                "preflight_failures": preflight_failures,
                "closure_report": closure_report,
                "closure_identity_status": closure_identity_status,
                "bug_closure_status": bug_status,
                "reported_bug_closure_status": reported_bug_status,
                "final_rc": final_rc,
            }
        )

    return {
        "rows": rows,
        "ready_to_mark_done": ready_to_mark_done,
        "not_ready_bugs": [
            str(row["bug"])
            for row in rows
            if row["ledger_status"] != "done" and row["artifact_status"] != "passed"
        ],
        "missing_reports": [
            str(row["bug"]) for row in rows if row["artifact_status"] == "missing"
        ],
    }


def _print_artifact_summary(python: str) -> dict[str, object]:
    payload = _artifact_summary_payload(python)
    print("Closure artifact summary:")
    for row in payload["rows"]:
        bug = row["bug"]
        ledger_status = row["ledger_status"]
        artifact_status = row["artifact_status"]
        if artifact_status == "ledger_done":
            print(f"  {bug} [{ledger_status}]: ledger done")
        else:
            print(
                f"  {bug} [{ledger_status}]: {artifact_status} "
                f"(preflight={row['preflight_status']}, "
                f"closure={row['closure_report']})"
            )
    ready = payload["ready_to_mark_done"]
    if ready:
        print(f"  ready to mark done: {', '.join(str(bug) for bug in ready)}")
    not_ready = payload["not_ready_bugs"]
    if not_ready:
        print(f"  not ready: {', '.join(str(bug) for bug in not_ready)}")
    return payload


def _base_report(
    *,
    args: argparse.Namespace,
    phases: list[Phase],
    python: str | None,
    extra_pytest_args: tuple[str, ...],
) -> dict[str, object]:
    bug_phase_map = {
        bug_id: {
            "selectors": list(selectors),
            "expanded_phases": [
                phase.name for phase in _selected_phases([], [bug_id])
            ],
        }
        for bug_id, selectors in sorted(BUG_PHASES.items())
    }
    return {
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "evidence_identity": _current_evidence_identity(),
        "repo_root": str(REPO_ROOT),
        "selectors": {
            "phase": list(args.phase or []),
            "bug": list(args.bug or []),
        },
        "mode": {
            "list": args.list,
            "remaining": args.remaining,
            "audit_completion": args.audit_completion,
            "summarize_artifacts": args.summarize_artifacts,
            "require_all_ready": args.require_all_ready,
            "collect": args.collect,
            "preflight": args.preflight,
            "execute": args.execute,
            "keep_going": args.keep_going,
        },
        "required_bug_closure": list(args.require_bug_closed or []),
        "selected_phases": [
            _phase_payload(phase, python=python, extra_pytest_args=extra_pytest_args)
            for phase in phases
        ],
        "bug_phase_map": bug_phase_map,
    }


def _bug_closure_report(report: dict[str, object]) -> dict[str, object]:
    ledger_statuses = _active_ledger_statuses()
    selected = {
        str(phase["name"])
        for phase in report.get("selected_phases", [])
        if isinstance(phase, dict) and phase.get("name") is not None
    }
    phase_results = {
        str(item["phase"]): int(item["returncode"])
        for item in report.get("phase_results", [])
        if (
            isinstance(item, dict)
            and item.get("phase") is not None
            and item.get("returncode") is not None
        )
    }
    bug_closure: dict[str, object] = {}
    for bug_id in sorted(BUG_PHASES):
        required = [phase.name for phase in _selected_phases([], [bug_id])]
        missing = [phase for phase in required if phase not in selected]
        passed = [phase for phase in required if phase_results.get(phase) == 0]
        failed = [
            phase
            for phase in required
            if phase in phase_results and phase_results[phase] != 0
        ]
        not_run = [phase for phase in required if phase not in phase_results]
        if failed:
            status = "failed"
        elif missing:
            status = "missing"
        elif not phase_results:
            status = "not_run"
        elif not_run:
            status = "partial"
        else:
            status = "passed"
        ledger_status = ledger_statuses.get(bug_id)
        if ledger_status == "done" and not phase_results:
            status = "done"
        bug_closure[bug_id] = {
            "status": status,
            "ledger_status": ledger_status,
            "required_phases": required,
            "selected_required_phases": [
                phase for phase in required if phase in selected
            ],
            "missing_required_phases": missing,
            "passed_required_phases": passed,
            "failed_required_phases": failed,
            "not_run_required_phases": not_run,
        }
    return bug_closure


def _print_bug_closure_summary(report: dict[str, object]) -> None:
    closure = report.get("bug_closure", {})
    if not isinstance(closure, dict):
        return

    rows: list[tuple[str, str, list[str]]] = []
    for bug_id, item in sorted(closure.items()):
        if not isinstance(item, dict):
            continue
        selected = [str(phase) for phase in item.get("selected_required_phases", [])]
        if not selected:
            continue
        rows.append((bug_id, str(item.get("status", "?")), selected))
    if not rows:
        return

    print("\nBug closure status:")
    for bug_id, status, selected in rows:
        print(f"  {bug_id}: {status} ({', '.join(selected)})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Print or run the live V1.71/V3.2 implementation-bug hardware gate."
        )
    )
    choices = ["all", *PHASE_BY_NAME.keys(), *PHASE_ALIASES.keys()]
    parser.add_argument(
        "--phase",
        action="append",
        choices=choices,
        help=(
            "Phase to print/run. May be repeated. Default: all phases. "
            "Use --phase all to be explicit."
        ),
    )
    parser.add_argument(
        "--bug",
        action="append",
        choices=sorted(BUG_PHASES),
        help=(
            "Ledger bug to print/run. May be repeated. Expands to the "
            "hardware phases required by docs/IMPL_V171_V32_BUG_LEDGER.md."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run selected phases. Without this flag the script only prints commands.",
    )
    parser.add_argument(
        "--list",
        "--list-phases",
        action="store_true",
        help="List phase, alias, and bug selectors without probing hardware.",
    )
    parser.add_argument(
        "--remaining",
        action="store_true",
        help=(
            "List non-done ledger bugs with the exact preflight and execute "
            "commands needed to produce closure artifacts. Does not probe hardware."
        ),
    )
    parser.add_argument(
        "--audit-completion",
        action="store_true",
        help=(
            "Fail unless every active ledger row is marked done. Prints the "
            "remaining closure commands and does not probe hardware."
        ),
    )
    parser.add_argument(
        "--summarize-artifacts",
        action="store_true",
        help=(
            "Read stable per-bug closure reports and summarize which bugs have "
            "passed hardware evidence ready to mark done. Does not probe hardware."
        ),
    )
    parser.add_argument(
        "--require-all-ready",
        action="store_true",
        help=(
            "With --summarize-artifacts, exit nonzero unless every non-done "
            "ledger row has passing preflight and closure reports."
        ),
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Run pytest collection for the hardware test file before selected phases.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help=(
            "Run non-destructive rig readiness checks for selected phases "
            "before printing or executing commands."
        ),
    )
    parser.add_argument(
        "--pause",
        action="store_true",
        help=(
            "When executing, prompt before each phase so manual positioning can be done. "
            "Multi-phase --execute runs pause by default unless --no-pause is set."
        ),
    )
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help=(
            "When executing multiple phases, do not auto-pause between phases. "
            "Use only when an external operator/script handles all manual repositioning."
        ),
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue executing later phases after a phase failure.",
    )
    parser.add_argument(
        "--require-bug-closed",
        action="append",
        choices=sorted(BUG_PHASES),
        default=[],
        help=(
            "Require the final report to close this ledger bug. May be repeated. "
            "The command exits nonzero unless each named bug has bug_closure "
            "status 'passed'."
        ),
    )
    parser.add_argument(
        "--mirror-selected-bug-reports",
        action="store_true",
        help=(
            "When running --preflight or --execute with --bug selectors, copy "
            "the final report to each selected bug's stable preflight or "
            "closure report path. This supports deduplicated multi-bug runs "
            "while preserving per-bug artifact-summary inputs."
        ),
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Python interpreter to use. Default resolves .venv_ep0/bin/python.",
    )
    parser.add_argument(
        "--pytest-arg",
        action="append",
        default=[],
        help="Extra argument appended to each pytest invocation. May be repeated.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help=(
            "Write a machine-readable report with selected phases, commands, "
            "preflight inventory, and phase return codes."
        ),
    )
    args = parser.parse_args(argv)
    if args.require_all_ready and not args.summarize_artifacts:
        parser.error("--require-all-ready requires --summarize-artifacts")

    phases = _selected_phases(args.phase or [], args.bug or [])
    python = (
        None
        if (
            args.list
            and not args.remaining
            and not args.audit_completion
            and not args.summarize_artifacts
        )
        else (args.python or _resolve_python())
    )
    extra_pytest_args = tuple(args.pytest_arg)
    report_path = args.report_json
    if report_path is None and args.summarize_artifacts:
        report_path = _stable_artifact_summary_report_path()
    if report_path is None and (args.execute or args.preflight or args.audit_completion):
        report_path = _default_report_path(args)
    report = _base_report(
        args=args,
        phases=phases,
        python=python,
        extra_pytest_args=extra_pytest_args,
    )
    if report_path is not None:
        report["report_path"] = str(report_path)

    def finish(rc: int) -> int:
        report["bug_closure"] = _bug_closure_report(report)
        closure_failures: list[dict[str, str]] = []
        bug_closure = report["bug_closure"]
        for bug_id in args.require_bug_closed:
            status = str(bug_closure[bug_id]["status"])
            if status not in {"done", "passed"}:
                closure_failures.append({"bug": bug_id, "status": status})
        if closure_failures:
            print("\nRequired bug closure failures:", file=sys.stderr)
            for failure in closure_failures:
                print(
                    f"  {failure['bug']}: {failure['status']}",
                    file=sys.stderr,
                )
            report["required_bug_closure_failures"] = closure_failures
            if rc == 0:
                rc = 1
        report["final_rc"] = rc
        report["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if args.execute or args.preflight:
            _print_bug_closure_summary(report)
        if report_path is not None:
            _write_report(report_path, report)
        if args.mirror_selected_bug_reports and args.bug:
            target_bugs = [
                bug_id
                for bug_id in dict.fromkeys(args.bug)
                if _active_ledger_statuses()[bug_id] != "done"
            ]
            if args.preflight:
                for bug_id in target_bugs:
                    _write_report(
                        REPO_ROOT / _stable_bug_preflight_report_path(bug_id),
                        report,
                    )
            if args.execute:
                for bug_id in target_bugs:
                    _write_report(
                        REPO_ROOT / _stable_bug_closure_report_path(bug_id),
                        report,
                    )
        return rc

    if args.list:
        _print_list(phases)
        return finish(0)

    if args.remaining:
        remaining_bugs = _print_remaining_bugs(
            python,
            selected_bug_names=list(args.bug or []),
        )
        report["remaining_bugs"] = remaining_bugs
        report["remaining_plan"] = _remaining_plan_payload(python, remaining_bugs)
        return finish(0)

    if args.audit_completion:
        completion_audit = _print_completion_audit(python)
        report["completion_audit"] = completion_audit
        return finish(0 if completion_audit["complete"] else 1)

    if args.summarize_artifacts:
        artifact_summary = _print_artifact_summary(python)
        report["artifact_summary"] = artifact_summary
        if args.require_all_ready and artifact_summary["not_ready_bugs"]:
            print("\nArtifact readiness failures:", file=sys.stderr)
            for bug_id in artifact_summary["not_ready_bugs"]:
                print(f"  {bug_id}", file=sys.stderr)
            return finish(1)
        return finish(0)

    if args.collect:
        rc = _run_collect(python)
        report["collect"] = {"returncode": rc}
        if rc != 0:
            return finish(rc)

    if args.preflight:
        rc, preflight_report = _preflight_with_report(phases)
        report["preflight"] = preflight_report
        if rc != 0:
            return finish(rc)

    if not args.execute:
        print(
            "Dry run only. Add --execute to run selected phases; add --pause "
            "for manual page/button positioning between phases."
        )
        for phase in phases:
            _print_phase(phase, python, extra_pytest_args)
        return finish(0)

    failures: list[tuple[str, int]] = []
    phase_results: list[dict[str, object]] = []
    report["phase_results"] = phase_results
    pause_each_phase = args.pause or (len(phases) > 1 and not args.no_pause)
    for phase in phases:
        started = time.monotonic()
        rc = _run_phase(phase, python, extra_pytest_args, pause=pause_each_phase)
        phase_results.append(
            {
                "phase": phase.name,
                "returncode": rc,
                "elapsed_s": round(time.monotonic() - started, 3),
            }
        )
        if rc != 0:
            failures.append((phase.name, rc))
            if not args.keep_going:
                break

    if not failures:
        print("\nV1.71/V3.2 hardware gate phases passed.")
        return finish(0)

    print("\nV1.71/V3.2 hardware gate failures:", file=sys.stderr)
    for name, rc in failures:
        print(f"  {name}: exit {rc}", file=sys.stderr)
    report["failures"] = [
        {"phase": name, "returncode": rc}
        for name, rc in failures
    ]
    return finish(1)


if __name__ == "__main__":
    sys.exit(main())
