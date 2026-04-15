#!/usr/bin/env python3
"""Real-hardware DLCP state-test helpers for camera, IR, and multi-MAIN mapping."""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import textwrap
import time
from typing import Optional, Sequence

from dlcp_fw.cli import hardware_flipper_ir
from dlcp_fw.cli import hardware_lcd_probe as lcd_probe
from dlcp_fw.flash.dlcp_control_flash import DEFAULT_PID, DEFAULT_VID, enumerate_devices
from dlcp_fw.flash.dlcp_ep0_flash_probe import read_flash_window
from dlcp_fw.flash.dlcp_main_flash import (
    ACTIVE_FLAGS_ADDR,
    ROUTE_LEN,
    ROUTE_RAM_BASE,
    DeviceSnapshot,
    _pick_device,
    _probe_active_preset_ep0,
    _probe_device_snapshot,
)
from dlcp_fw.paths import ARTIFACTS_DIR, SCRIPTS_DIR


DEFAULT_OUTPUT_ROOT = ARTIFACTS_DIR / "probes" / "hardware_state_test"
DEFAULT_MEMORY_SIZE = ROUTE_RAM_BASE + ROUTE_LEN - ACTIVE_FLAGS_ADDR
DEFAULT_MAIN_TIMEOUT_S = 10.0
DEFAULT_MAIN_POLL_S = 0.1
DEFAULT_LCD_TIMEOUT_S = 18.0
DEFAULT_LCD_POLL_S = 0.1
DEFAULT_LCD_PROBE_CAPTURES = 1
DEFAULT_STANDBY_DWELL_S = 1.0
DEFAULT_STANDBY_BLANK_CONSECUTIVE = 2
DEFAULT_WAKE_MAX_ATTEMPTS = 3
DEFAULT_WAKE_RETRY_DELAY_S = 1.0
DEFAULT_WAKE_ROLE_STABLE_POLLS = 3
DEFAULT_WAKE_DIAGNOSTICS_TAIL = 30
DEFAULT_SOAK_ITERATIONS = 5

WAKE_FAILURE_FUNCTIONAL_TIMEOUT = "FUNCTIONAL_WAKE_TIMEOUT"
WAKE_FAILURE_ROLE_DECODE_UNSTABLE = "ROLE_DECODE_UNSTABLE"


@dataclasses.dataclass(frozen=True)
class VideoDevice:
    index: int
    name: str


@dataclasses.dataclass(frozen=True)
class MainRoleState:
    path: str
    serial: str
    product: str
    manufacturer: str
    role: str
    active_preset: str | None
    active_config_name: str | None
    route_labels: list[str]
    route_values: list[int]
    raw_window_hex: str | None
    mode: str = ""
    version: str | None = None
    warnings: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class IrSequenceStep:
    action: str
    sleep_after_s: float = 0.0


class WakeValidationError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        samples: list[dict[str, object]],
        diagnostics_tail: int,
        details: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.samples = samples
        self.diagnostics_tail = diagnostics_tail
        self.details = details or {}
        tail_count = max(1, diagnostics_tail)
        tail = samples[-tail_count:]
        payload = {
            "classification": code,
            "details": self.details,
            "sample_tail_count": len(tail),
            "sample_tail": tail,
        }
        super().__init__(f"{code}: {message}\nWAKE_POLL_DIAGNOSTICS:\n{json.dumps(payload, indent=2, sort_keys=True)}")


def _json_dumps(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _path_text(path: bytes | None) -> str:
    if path is None:
        return "<no-path>"
    return path.decode("utf-8", errors="replace")


def _run(
    args: Sequence[str],
    *,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=check,
        capture_output=capture_output,
        text=text,
    )


def _load_avfoundation_video_devices() -> list[VideoDevice]:
    proc = _run(
        ["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        check=False,
    )
    text = proc.stdout + proc.stderr
    out: list[VideoDevice] = []
    in_video = False
    for line in text.splitlines():
        if "AVFoundation video devices:" in line:
            in_video = True
            continue
        if "AVFoundation audio devices:" in line:
            break
        if not in_video:
            continue
        line = line.strip()
        if "] [" not in line:
            continue
        start = line.rfind("[")
        end = line.find("]", start + 1)
        if start < 0 or end < 0:
            continue
        try:
            index = int(line[start + 1 : end])
        except ValueError:
            continue
        name = line[end + 1 :].strip()
        out.append(VideoDevice(index=index, name=name))
    return out


def _camera_inventory() -> list[dict[str, object]]:
    return [dataclasses.asdict(item) for item in _load_avfoundation_video_devices()]


def _flipper_inventory() -> dict[str, object]:
    qflipper = Path("/Applications/qFlipper.app/Contents/MacOS/qFlipper-cli")
    return {
        "qflipper_cli": str(qflipper) if qflipper.exists() else None,
        "serial_candidates": hardware_flipper_ir.discover_flipper_serial_ports(),
    }


def _snapshot_visible_mains(*, vid: int, pid: int) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for dev in enumerate_devices(vid, pid):
        item = dataclasses.asdict(dev)
        item["path"] = _path_text(dev.path)
        out.append(item)
    return out


def _classify_role_from_snapshot(snapshot: DeviceSnapshot) -> str:
    routes = snapshot.active_routes
    if not routes:
        return "UNKNOWN"
    labels = [entry.label for entry in routes]
    unique = sorted(set(labels))
    if unique == ["L"]:
        return "LEFT"
    if unique == ["R"]:
        return "RIGHT"
    return "MIXED"


def _probe_main_role_state(*, vid: int, pid: int, path: bytes) -> MainRoleState:
    info = _pick_device(vid, pid, path)
    snapshot = _probe_device_snapshot(info=info, vid=vid, pid=pid)
    role = _classify_role_from_snapshot(snapshot)
    active_preset: str | None = None
    raw_window_hex: str | None = None
    try:
        active_preset = _probe_active_preset_ep0(vid=vid, pid=pid, path=path)
    except Exception:
        active_preset = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            raw_window = read_flash_window(
                vid=vid,
                pid=pid,
                path=path,
                start=ACTIVE_FLAGS_ADDR,
                size=DEFAULT_MEMORY_SIZE,
                chunk=min(0xFF, DEFAULT_MEMORY_SIZE),
            )
        raw_window_hex = raw_window.hex()
    except Exception:
        raw_window_hex = None

    route_labels = [entry.label for entry in snapshot.active_routes or ()]
    route_values = [entry.value for entry in snapshot.active_routes or ()]
    return MainRoleState(
        path=_path_text(info.path),
        serial=info.serial_number or "",
        product=info.product_string or "",
        manufacturer=info.manufacturer_string or "",
        role=role,
        active_preset=active_preset,
        active_config_name=snapshot.active_config_name,
        route_labels=route_labels,
        route_values=route_values,
        raw_window_hex=raw_window_hex,
        mode=snapshot.mode,
        version=(
            None
            if snapshot.version is None
            else f"{snapshot.version.major}.{snapshot.version.minor}"
        ),
        warnings=list(snapshot.warnings),
    )


def _collect_main_roles(*, vid: int, pid: int) -> list[MainRoleState]:
    states: list[MainRoleState] = []
    for dev in enumerate_devices(vid, pid):
        if dev.path is None:
            continue
        states.append(_probe_main_role_state(vid=vid, pid=pid, path=dev.path))
    return states


def _assert_left_right_roles(states: list[MainRoleState]) -> tuple[MainRoleState, MainRoleState]:
    if len(states) != 2:
        raise RuntimeError(
            f"expected exactly 2 visible MAIN HID devices, found {len(states)}"
        )
    left = [item for item in states if item.role == "LEFT"]
    right = [item for item in states if item.role == "RIGHT"]
    if len(left) != 1 or len(right) != 1:
        payload = [
            {
                "path": item.path,
                "role": item.role,
                "route_labels": item.route_labels,
                "active_config_name": item.active_config_name,
            }
            for item in states
        ]
        raise RuntimeError(
            "expected exactly one LEFT and one RIGHT MAIN from route memory; "
            f"got {payload}"
        )
    return left[0], right[0]


def _render_ir_command(template: str, *, action: str) -> list[str]:
    rendered = template.format(
        action=action,
        action_lower=action.lower(),
        action_upper=action.upper(),
    )
    tokens = shlex.split(rendered)
    if not tokens:
        raise RuntimeError("IR command template rendered to an empty command")
    return tokens


def _send_ir(template: str, *, action: str) -> dict[str, object]:
    cmd = _render_ir_command(template, action=action)
    started = time.time()
    proc = _run(cmd)
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "started_at": started,
        "finished_at": time.time(),
    }


def _default_flipper_ir_command_template(*, port: str | None) -> str:
    script_path = SCRIPTS_DIR / "hardware_flipper_ir.py"
    tokens = [shlex.quote(sys.executable), shlex.quote(str(script_path))]
    if port:
        tokens.extend(["--port", shlex.quote(port)])
    tokens.extend(["--action", "{action}"])
    return " ".join(tokens)


def _normalize_preset_action(action: str) -> str:
    normalized = action.strip().upper()
    if normalized not in {"F1", "F2"}:
        raise RuntimeError(f"expected preset action F1 or F2, got {action!r}")
    return normalized


def _expected_preset_for_action(action: str) -> str:
    normalized = _normalize_preset_action(action)
    return "A" if normalized == "F1" else "B"


def _parse_preset_sequence(sequence: str) -> list[str]:
    actions = [_normalize_preset_action(item) for item in sequence.split(",") if item.strip()]
    if not actions:
        raise RuntimeError("preset sequence must contain at least one F1/F2 action")
    return actions


def _parse_delays_ms(delays_ms: str) -> list[float]:
    delays: list[float] = []
    for item in delays_ms.split(","):
        text = item.strip()
        if not text:
            continue
        try:
            value = float(text)
        except ValueError as exc:
            raise RuntimeError(f"invalid delay value {text!r} in {delays_ms!r}") from exc
        if value < 0:
            raise RuntimeError(f"delay values must be >= 0, got {value!r}")
        delays.append(value)
    if not delays:
        raise RuntimeError("delay list must contain at least one numeric value")
    return delays


def _camera_probe_kwargs_from_args(
    args: argparse.Namespace,
    *,
    output_root: Path,
    skip_configure: bool,
    captures: int | None = None,
) -> dict[str, object]:
    return {
        "camera_selector": args.camera_selector,
        "vendor": args.vendor,
        "product": args.product,
        "address": args.address,
        "zoom": args.zoom,
        "focus": args.focus,
        "exposure": args.exposure,
        "gain": args.gain,
        "sharpness": args.sharpness,
        "captures": args.captures if captures is None else captures,
        "warmup_s": args.warmup_s,
        "skip_configure": skip_configure,
        "output_root": output_root,
    }


def _role_pair_payload(left: MainRoleState, right: MainRoleState) -> dict[str, object]:
    return {
        "left": dataclasses.asdict(left),
        "right": dataclasses.asdict(right),
    }


def _compact_role_observation(state: MainRoleState) -> dict[str, object]:
    return {
        "path": state.path,
        "role": state.role,
        "active_preset": state.active_preset,
        "active_config_name": state.active_config_name,
        "active_flags": _active_flags_value(state),
        "active": _is_active_state(state),
        "muted": _is_muted_state(state),
        "raw_window_hex": state.raw_window_hex,
        "mode": state.mode,
        "version": state.version,
    }


def _active_flags_value(state: MainRoleState) -> int | None:
    if not state.raw_window_hex or len(state.raw_window_hex) < 2:
        return None
    try:
        return int(state.raw_window_hex[:2], 16)
    except ValueError:
        return None


def _is_muted_flags(flags: int) -> bool:
    # On the real rig, mute toggles the first ACTIVE_FLAGS byte from 0x08 to 0x38.
    # The practical user-visible predicate is that either of the mute-intent bits
    # in the 0x10/0x20 range is set.
    return bool(flags & 0x30)


def _is_active_flags(flags: int) -> bool:
    return bool(flags & 0x08)


def _is_muted_state(state: MainRoleState) -> bool | None:
    flags = _active_flags_value(state)
    if flags is None:
        return None
    return _is_muted_flags(flags)


def _is_active_state(state: MainRoleState) -> bool | None:
    flags = _active_flags_value(state)
    if flags is None:
        return None
    return _is_active_flags(flags)


def _read_pair_state(*, vid: int, pid: int) -> tuple[MainRoleState, MainRoleState]:
    states = _collect_main_roles(vid=vid, pid=pid)
    return _assert_left_right_roles(states)


def _current_pair_preset(*, vid: int, pid: int) -> str:
    left, right = _read_pair_state(vid=vid, pid=pid)
    if left.active_preset not in {"A", "B"} or right.active_preset not in {"A", "B"}:
        raise RuntimeError(
            f"unable to determine current pair preset: left={left.active_preset!r} "
            f"right={right.active_preset!r}"
        )
    if left.active_preset != right.active_preset:
        raise RuntimeError(
            f"pair is already split before scenario start: left={left.active_preset!r} "
            f"right={right.active_preset!r}"
        )
    return left.active_preset


def _next_preset_action_from_pair(*, vid: int, pid: int) -> str:
    current = _current_pair_preset(vid=vid, pid=pid)
    return "F2" if current == "A" else "F1"


def _assert_lcd_consensus(
    summary: dict[str, object],
    *,
    expected_line1: str,
    expected_line2: str | None,
    context: str,
) -> None:
    consensus = summary["consensus"]
    actual_line1 = consensus["line1"]
    actual_line2 = consensus["line2"]
    line2_match = expected_line2 is None or actual_line2 == expected_line2
    if actual_line1 != expected_line1 or not line2_match:
        raise RuntimeError(
            f"{context}: unexpected LCD consensus {actual_line1!r} / {actual_line2!r}; "
            f"expected {expected_line1!r} / {expected_line2!r}"
        )


def _assert_expected_role_pair(
    left: MainRoleState,
    right: MainRoleState,
    *,
    expected_preset: str,
    context: str,
) -> None:
    for item in (left, right):
        if item.active_preset != expected_preset:
            raise RuntimeError(
                f"{context}: MAIN role {item.role} did not reach preset {expected_preset}: "
                f"path={item.path} active_preset={item.active_preset!r}"
            )


def _execute_ir_sequence(
    *,
    ir_template: str,
    steps: Sequence[IrSequenceStep],
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for step in steps:
        result = _send_ir(ir_template, action=step.action)
        results.append(
            {
                "action": step.action,
                "sleep_after_s": step.sleep_after_s,
                **result,
            }
        )
        if step.sleep_after_s > 0:
            time.sleep(max(0.0, step.sleep_after_s))
    return results


def _wait_for_main_pair_preset(
    *,
    vid: int,
    pid: int,
    expected_preset: str,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, object]:
    return _wait_for_main_pair_state(
        vid=vid,
        pid=pid,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
        expected_preset=expected_preset,
        muted=None,
        active=None,
    )


def _wait_for_main_pair_state(
    *,
    vid: int,
    pid: int,
    timeout_s: float,
    poll_interval_s: float,
    expected_preset: str | None,
    muted: bool | None,
    active: bool | None,
) -> dict[str, object]:
    started = time.monotonic()
    deadline = started + max(0.0, timeout_s)
    left_reached_s: float | None = None
    right_reached_s: float | None = None
    both_reached_s: float | None = None
    observations: list[dict[str, object]] = []
    last_left: MainRoleState | None = None
    last_right: MainRoleState | None = None
    last_read_error: str | None = None

    def _final_payload_from_unordered_states(states: list[MainRoleState]) -> dict[str, object]:
        ordered = sorted(states, key=lambda item: item.path)
        return {
            "left": dataclasses.asdict(ordered[0]),
            "right": dataclasses.asdict(ordered[1]),
            "role_mapping": "unordered_path",
        }

    while True:
        try:
            left, right = _read_pair_state(vid=vid, pid=pid)
        except Exception as exc:
            elapsed = time.monotonic() - started
            last_read_error = str(exc)
            failure_observation: dict[str, object] = {
                "t_s": elapsed,
                "error": last_read_error,
            }
            try:
                provisional_states = _collect_main_roles(vid=vid, pid=pid)
            except Exception as provisional_exc:
                failure_observation["provisional_error"] = str(provisional_exc)
                provisional_states = []
            if provisional_states:
                failure_observation["provisional_mains"] = [
                    _compact_role_observation(item) for item in provisional_states
                ]
            observations.append(failure_observation)

            if len(provisional_states) == 2:
                provisional_match = all(
                    _state_matches(
                        item,
                        expected_preset=expected_preset,
                        muted=muted,
                        active=active,
                    )
                    for item in provisional_states
                )
                if provisional_match:
                    if left_reached_s is None:
                        left_reached_s = elapsed
                    if right_reached_s is None:
                        right_reached_s = elapsed
                    if both_reached_s is None:
                        both_reached_s = elapsed
                    final_payload = _final_payload_from_unordered_states(provisional_states)
                    return {
                        "expected_preset": expected_preset,
                        "muted": muted,
                        "active": active,
                        "timeout_s": timeout_s,
                        "poll_interval_s": poll_interval_s,
                        "left_reached_s": left_reached_s,
                        "right_reached_s": right_reached_s,
                        "both_reached_s": both_reached_s,
                        "observations": observations,
                        "final": final_payload,
                        "matched_without_roles": True,
                    }
            if time.monotonic() >= deadline:
                break
            time.sleep(max(0.0, poll_interval_s))
            continue

        last_left, last_right = left, right
        elapsed = time.monotonic() - started
        observations.append(
            {
                "t_s": elapsed,
                "left": _compact_role_observation(left),
                "right": _compact_role_observation(right),
            }
        )
        left_match = _state_matches(
            left,
            expected_preset=expected_preset,
            muted=muted,
            active=active,
        )
        right_match = _state_matches(
            right,
            expected_preset=expected_preset,
            muted=muted,
            active=active,
        )
        if left_match and left_reached_s is None:
            left_reached_s = elapsed
        if right_match and right_reached_s is None:
            right_reached_s = elapsed
        if left_match and right_match and both_reached_s is None:
            both_reached_s = elapsed
            return {
                "expected_preset": expected_preset,
                "muted": muted,
                "active": active,
                "timeout_s": timeout_s,
                "poll_interval_s": poll_interval_s,
                "left_reached_s": left_reached_s,
                "right_reached_s": right_reached_s,
                "both_reached_s": both_reached_s,
                "observations": observations,
                "final": _role_pair_payload(left, right),
                "matched_without_roles": False,
            }
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, poll_interval_s))

    raise RuntimeError(
        "timed out waiting for both MAINs to satisfy state "
        f"(preset={expected_preset!r}, muted={muted!r}, active={active!r}); "
        f"last_read_error={last_read_error!r} "
        f"left={None if last_left is None else _compact_role_observation(last_left)!r} "
        f"right={None if last_right is None else _compact_role_observation(last_right)!r}"
    )


def _state_matches(
    state: MainRoleState,
    *,
    expected_preset: str | None,
    muted: bool | None,
    active: bool | None,
) -> bool:
    if expected_preset is not None and state.active_preset != expected_preset:
        return False
    if muted is not None:
        observed_muted = _is_muted_state(state)
        if observed_muted is None or observed_muted != muted:
            return False
    if active is not None:
        observed_active = _is_active_state(state)
        if observed_active is None or observed_active != active:
            return False
    return True


def _capture_sticky_path_roles(*, vid: int, pid: int) -> dict[str, object]:
    path_roles: dict[str, str] = {}
    states_payload: list[dict[str, object]] = []
    capture_error: str | None = None
    try:
        states = _collect_main_roles(vid=vid, pid=pid)
    except Exception as exc:
        states = []
        capture_error = str(exc)

    for state in sorted(states, key=lambda item: item.path):
        states_payload.append(_compact_role_observation(state))
        if state.role in {"LEFT", "RIGHT"}:
            path_roles[state.path] = state.role

    return {
        "path_roles": path_roles,
        "states": states_payload,
        "error": capture_error,
    }


def _collect_wake_poll_sample(
    *,
    vid: int,
    pid: int,
    expected_preset: str,
    sticky_path_roles: dict[str, str],
    elapsed_s: float,
) -> dict[str, object]:
    sample: dict[str, object] = {
        "t_s": elapsed_s,
        "hid_read_ok": False,
        "read_error": None,
        "visible_paths": [],
        "visible_count": 0,
        "mains": [],
        "functional_ready": False,
        "role_decode_ready": False,
        "effective_role_ready": False,
        "sticky_roles_used": False,
    }
    try:
        states = _collect_main_roles(vid=vid, pid=pid)
    except Exception as exc:
        sample["read_error"] = str(exc)
        return sample

    ordered_states = sorted(states, key=lambda item: item.path)
    sample["hid_read_ok"] = True
    sample["visible_count"] = len(ordered_states)
    sample["visible_paths"] = [item.path for item in ordered_states]

    mains_payload: list[dict[str, object]] = []
    functional_matches: list[bool] = []
    raw_left = raw_right = 0
    effective_left = effective_right = 0
    sticky_used = False

    for item in ordered_states:
        raw_role = item.role
        sticky_role = sticky_path_roles.get(item.path)
        effective_role = raw_role
        role_from_sticky = False
        if raw_role not in {"LEFT", "RIGHT"} and sticky_role in {"LEFT", "RIGHT"}:
            effective_role = sticky_role
            role_from_sticky = True
            sticky_used = True
        if raw_role == "LEFT":
            raw_left += 1
        elif raw_role == "RIGHT":
            raw_right += 1
        if effective_role == "LEFT":
            effective_left += 1
        elif effective_role == "RIGHT":
            effective_right += 1

        active_flags = _active_flags_value(item)
        active = _is_active_state(item)
        muted = _is_muted_state(item)
        functional_match = _state_matches(
            item,
            expected_preset=expected_preset,
            muted=False,
            active=True,
        )
        functional_matches.append(functional_match)
        mains_payload.append(
            {
                "path": item.path,
                "role_raw": raw_role,
                "role_effective": effective_role,
                "role_from_sticky": role_from_sticky,
                "active_preset": item.active_preset,
                "active_flags": active_flags,
                "active": active,
                "muted": muted,
                "raw_window_hex": item.raw_window_hex,
                "version": item.version,
                "functional_match": functional_match,
            }
        )

    sample["mains"] = mains_payload
    sample["sticky_roles_used"] = sticky_used
    sample["functional_ready"] = len(ordered_states) == 2 and all(functional_matches)
    sample["role_decode_ready"] = len(ordered_states) == 2 and raw_left == 1 and raw_right == 1
    sample["effective_role_ready"] = len(ordered_states) == 2 and effective_left == 1 and effective_right == 1
    return sample


def _wait_for_wake_two_phase(
    *,
    vid: int,
    pid: int,
    expected_preset: str,
    timeout_s: float,
    poll_interval_s: float,
    wake_phase_a_timeout_s: float | None,
    wake_phase_b_timeout_s: float | None,
    wake_role_stable_polls: int,
    wake_diagnostics_tail: int,
    sticky_path_roles: dict[str, str],
) -> dict[str, object]:
    phase_a_timeout_s = timeout_s if wake_phase_a_timeout_s is None else max(0.0, wake_phase_a_timeout_s)
    phase_b_timeout_s = timeout_s if wake_phase_b_timeout_s is None else max(0.0, wake_phase_b_timeout_s)
    stable_polls_required = max(1, int(wake_role_stable_polls))
    diagnostics_tail = max(1, int(wake_diagnostics_tail))

    started = time.monotonic()
    phase_a_deadline = started + phase_a_timeout_s
    phase_a_passed_at_s: float | None = None
    phase_b_started_mono: float | None = None
    phase_b_deadline: float | None = None
    role_stable_count = 0
    samples: list[dict[str, object]] = []

    while True:
        now = time.monotonic()
        elapsed_s = now - started
        sample = _collect_wake_poll_sample(
            vid=vid,
            pid=pid,
            expected_preset=expected_preset,
            sticky_path_roles=sticky_path_roles,
            elapsed_s=elapsed_s,
        )
        sample["phase"] = "A" if phase_a_passed_at_s is None else "B"

        if phase_a_passed_at_s is None:
            if sample["functional_ready"]:
                phase_a_passed_at_s = elapsed_s
                phase_b_started_mono = now
                phase_b_deadline = phase_b_started_mono + phase_b_timeout_s
                role_stable_count = 1 if sample["role_decode_ready"] else 0
            elif now >= phase_a_deadline:
                sample["role_stable_count"] = role_stable_count
                samples.append(sample)
                raise WakeValidationError(
                    WAKE_FAILURE_FUNCTIONAL_TIMEOUT,
                    "phase A functional wake gate did not converge before timeout",
                    samples=samples,
                    diagnostics_tail=diagnostics_tail,
                    details={
                        "expected_preset": expected_preset,
                        "phase_a_timeout_s": phase_a_timeout_s,
                        "phase_b_timeout_s": phase_b_timeout_s,
                        "role_stable_polls_required": stable_polls_required,
                        "phase_a_passed_at_s": phase_a_passed_at_s,
                    },
                )
        else:
            if sample["role_decode_ready"]:
                role_stable_count += 1
            else:
                role_stable_count = 0
            if phase_b_deadline is not None and now >= phase_b_deadline and role_stable_count < stable_polls_required:
                sample["role_stable_count"] = role_stable_count
                samples.append(sample)
                raise WakeValidationError(
                    WAKE_FAILURE_ROLE_DECODE_UNSTABLE,
                    "phase B role decode did not stabilize before timeout",
                    samples=samples,
                    diagnostics_tail=diagnostics_tail,
                    details={
                        "expected_preset": expected_preset,
                        "phase_a_timeout_s": phase_a_timeout_s,
                        "phase_b_timeout_s": phase_b_timeout_s,
                        "role_stable_polls_required": stable_polls_required,
                        "phase_a_passed_at_s": phase_a_passed_at_s,
                        "phase_b_elapsed_s": (None if phase_b_started_mono is None else now - phase_b_started_mono),
                    },
                )

        sample["role_stable_count"] = role_stable_count
        samples.append(sample)

        if phase_a_passed_at_s is not None and role_stable_count >= stable_polls_required:
            return {
                "expected_preset": expected_preset,
                "phase_a_timeout_s": phase_a_timeout_s,
                "phase_b_timeout_s": phase_b_timeout_s,
                "role_stable_polls_required": stable_polls_required,
                "phase_a_passed_at_s": phase_a_passed_at_s,
                "phase_b_stable_at_s": elapsed_s,
                "samples": samples,
            }

        time.sleep(max(0.0, poll_interval_s))


def _wait_for_lcd_target(
    *,
    expected_line1: str,
    expected_line2: str | None,
    timeout_s: float,
    poll_interval_s: float,
    probe_captures: int,
    args: argparse.Namespace,
    output_root: Path,
) -> dict[str, object]:
    started = time.monotonic()
    deadline = started + max(0.0, timeout_s)
    probes: list[dict[str, object]] = []
    last_summary: dict[str, object] | None = None

    while True:
        elapsed = time.monotonic() - started
        summary = _probe_lcd(
            **_camera_probe_kwargs_from_args(
                args,
                output_root=output_root,
                skip_configure=True,
                captures=probe_captures,
            )
        )
        last_summary = summary
        line1 = summary["consensus"]["line1"]
        line2 = summary["consensus"]["line2"]
        probes.append(
            {
                "t_s": elapsed,
                "line1": line1,
                "line2": line2,
                "summary_path": summary["summary_path"],
            }
        )
        if line1 == expected_line1 and (expected_line2 is None or line2 == expected_line2):
            return {
                "expected_line1": expected_line1,
                "expected_line2": expected_line2,
                "timeout_s": timeout_s,
                "poll_interval_s": poll_interval_s,
                "probe_captures": probe_captures,
                "matched_at_s": elapsed,
                "probes": probes,
                "last_summary_path": summary["summary_path"],
            }
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, poll_interval_s))

    actual_line1 = None if last_summary is None else last_summary["consensus"]["line1"]
    actual_line2 = None if last_summary is None else last_summary["consensus"]["line2"]
    raise RuntimeError(
        f"timed out waiting for LCD {expected_line1!r} / {expected_line2!r}; "
        f"last consensus was {actual_line1!r} / {actual_line2!r}"
    )


def _active_flags_from_pair_item(pair_item: object) -> int | None:
    if not isinstance(pair_item, dict):
        return None
    raw_window = pair_item.get("raw_window_hex")
    if not isinstance(raw_window, str) or len(raw_window) < 2:
        return None
    try:
        return int(raw_window[:2], 16)
    except ValueError:
        return None


def _standby_blank_support(pair_state: dict[str, object]) -> tuple[bool, str]:
    if not pair_state.get("reachable"):
        return True, "hid_unreachable"

    left_flags = _active_flags_from_pair_item(pair_state.get("left"))
    right_flags = _active_flags_from_pair_item(pair_state.get("right"))
    if left_flags is not None and right_flags is not None:
        if (not _is_active_flags(left_flags)) and (not _is_active_flags(right_flags)):
            return True, "both_mains_inactive"
        return False, "mains_still_active"
    return False, "active_flags_unavailable"


def _wait_for_standby_lcd_entry(
    *,
    timeout_s: float,
    poll_interval_s: float,
    probe_captures: int,
    args: argparse.Namespace,
    output_root: Path,
    pre_standby_lcd_visible: bool,
) -> dict[str, object]:
    started = time.monotonic()
    deadline = started + max(0.0, timeout_s)
    probes: list[dict[str, object]] = []
    last_summary: dict[str, object] | None = None
    consecutive_blank = 0
    allow_blank_fallback = bool(getattr(args, "standby_allow_blank_fallback", True))
    min_blank = max(1, int(getattr(args, "standby_blank_consecutive", DEFAULT_STANDBY_BLANK_CONSECUTIVE)))

    while True:
        elapsed = time.monotonic() - started
        summary = _probe_lcd(
            **_camera_probe_kwargs_from_args(
                args,
                output_root=output_root,
                skip_configure=True,
                captures=probe_captures,
            )
        )
        last_summary = summary
        line1 = summary["consensus"]["line1"]
        line2 = summary["consensus"]["line2"]
        probe_item = {
            "t_s": elapsed,
            "line1": line1,
            "line2": line2,
            "summary_path": summary["summary_path"],
            "blank_consecutive": consecutive_blank,
        }
        if line1 == "Zzz...":
            probes.append(probe_item)
            return {
                "expected_line1": "Zzz...",
                "expected_line2": None,
                "timeout_s": timeout_s,
                "poll_interval_s": poll_interval_s,
                "probe_captures": probe_captures,
                "matched_at_s": elapsed,
                "matched_mode": "lcd_zzz",
                "probes": probes,
                "last_summary_path": summary["summary_path"],
            }

        if line1 is None and line2 is None:
            pair_state = _try_read_pair_state(vid=args.vid, pid=args.pid)
            supported, reason = _standby_blank_support(pair_state)
            probe_item["pair_state"] = pair_state
            probe_item["blank_support_reason"] = reason
            if supported:
                consecutive_blank += 1
                probe_item["blank_consecutive"] = consecutive_blank
                if allow_blank_fallback and pre_standby_lcd_visible and consecutive_blank >= min_blank:
                    probes.append(probe_item)
                    return {
                        "expected_line1": "Zzz...",
                        "expected_line2": None,
                        "timeout_s": timeout_s,
                        "poll_interval_s": poll_interval_s,
                        "probe_captures": probe_captures,
                        "matched_at_s": elapsed,
                        "matched_mode": "blank_fallback",
                        "blank_support_reason": reason,
                        "blank_consecutive_required": min_blank,
                        "pre_standby_lcd_visible": pre_standby_lcd_visible,
                        "probes": probes,
                        "last_summary_path": summary["summary_path"],
                    }
            else:
                consecutive_blank = 0
                probe_item["blank_consecutive"] = consecutive_blank
        else:
            consecutive_blank = 0
            probe_item["blank_consecutive"] = consecutive_blank

        probes.append(probe_item)
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, poll_interval_s))

    actual_line1 = None if last_summary is None else last_summary["consensus"]["line1"]
    actual_line2 = None if last_summary is None else last_summary["consensus"]["line2"]
    raise RuntimeError(
        "timed out waiting for standby LCD entry "
        "('Zzz...' or guarded blank fallback); "
        f"last consensus was {actual_line1!r} / {actual_line2!r}"
    )


def _sleep_ms(delay_ms: float) -> float:
    delay_s = max(0.0, delay_ms / 1000.0)
    if delay_s > 0:
        time.sleep(delay_s)
    return delay_s


def _try_read_pair_state(*, vid: int, pid: int) -> dict[str, object]:
    try:
        left, right = _read_pair_state(vid=vid, pid=pid)
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}
    return {"reachable": True, **_role_pair_payload(left, right)}


def _run_preset_action_and_wait(
    *,
    action: str,
    args: argparse.Namespace,
    output_root: Path,
    context: str,
) -> dict[str, object]:
    expected_preset = _expected_preset_for_action(action)
    ir_template = args.ir_command_template or _default_flipper_ir_command_template(
        port=args.flipper_port
    )
    ir_results = _execute_ir_sequence(
        ir_template=ir_template,
        steps=[IrSequenceStep(action=action)],
    )
    main_wait = _wait_for_main_pair_state(
        vid=args.vid,
        pid=args.pid,
        timeout_s=args.timeout_s,
        poll_interval_s=args.main_poll_s,
        expected_preset=expected_preset,
        muted=None,
        active=True,
    )
    lcd_wait = _wait_for_lcd_target(
        expected_line1="Volume",
        expected_line2=f"Active: {expected_preset}",
        timeout_s=args.lcd_timeout_s,
        poll_interval_s=args.lcd_poll_s,
        probe_captures=args.lcd_probe_captures,
        args=args,
        output_root=output_root / "lcd_wait",
    )
    left, right = _read_pair_state(vid=args.vid, pid=args.pid)
    _assert_expected_role_pair(left, right, expected_preset=expected_preset, context=context)
    return {
        "context": context,
        "expected_preset": expected_preset,
        "ir_command_template": ir_template,
        "ir_results": ir_results,
        "main_wait": main_wait,
        "lcd_wait": lcd_wait,
        "after": _role_pair_payload(left, right),
    }


def _wait_for_lcd_usable_expected_preset(
    *,
    expected_preset: str,
    args: argparse.Namespace,
    output_root: Path,
) -> dict[str, object]:
    return _wait_for_lcd_target(
        expected_line1="Volume",
        expected_line2=f"Active: {expected_preset}",
        timeout_s=args.lcd_timeout_s,
        poll_interval_s=args.lcd_poll_s,
        probe_captures=args.lcd_probe_captures,
        args=args,
        output_root=output_root,
    )


def _lcd_summary_contains_text(summary: dict[str, object], target: str) -> bool:
    captures = summary.get("captures", [])
    for capture in captures:
        for obs in capture.get("observations", []):
            text = str(obs.get("text", "")).strip()
            if not text:
                continue
            if lcd_probe._looks_like(text, target, max_dist=2):
                return True
    return False


def _wait_for_lcd_text_contains(
    *,
    target: str,
    timeout_s: float,
    poll_interval_s: float,
    probe_captures: int,
    args: argparse.Namespace,
    output_root: Path,
) -> dict[str, object]:
    started = time.monotonic()
    deadline = started + max(0.0, timeout_s)
    probes: list[dict[str, object]] = []
    last_summary: dict[str, object] | None = None

    while True:
        elapsed = time.monotonic() - started
        summary = _probe_lcd(
            **_camera_probe_kwargs_from_args(
                args,
                output_root=output_root,
                skip_configure=True,
                captures=probe_captures,
            )
        )
        last_summary = summary
        found = _lcd_summary_contains_text(summary, target)
        probes.append(
            {
                "t_s": elapsed,
                "found": found,
                "summary_path": summary["summary_path"],
                "line1": summary["consensus"]["line1"],
                "line2": summary["consensus"]["line2"],
            }
        )
        if found:
            return {
                "target": target,
                "timeout_s": timeout_s,
                "poll_interval_s": poll_interval_s,
                "probe_captures": probe_captures,
                "matched_at_s": elapsed,
                "probes": probes,
                "last_summary_path": summary["summary_path"],
            }
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, poll_interval_s))

    raise RuntimeError(
        f"timed out waiting for LCD OCR to contain {target!r}; "
        f"last summary path was {None if last_summary is None else last_summary['summary_path']!r}"
    )


def _resolve_ir_template(args: argparse.Namespace) -> str:
    return args.ir_command_template or _default_flipper_ir_command_template(
        port=args.flipper_port
    )


def _send_single_ir_action(*, args: argparse.Namespace, action: str) -> dict[str, object]:
    return _execute_ir_sequence(
        ir_template=_resolve_ir_template(args),
        steps=[IrSequenceStep(action=action)],
    )[0]


def _ensure_pair_unmuted(
    *,
    args: argparse.Namespace,
    output_root: Path,
    context: str,
) -> dict[str, object]:
    left, right = _read_pair_state(vid=args.vid, pid=args.pid)
    preset = _current_pair_preset(vid=args.vid, pid=args.pid)
    already_unmuted = (_is_muted_state(left) is False) and (_is_muted_state(right) is False)
    if already_unmuted:
        return {
            "context": context,
            "performed": False,
            "expected_preset": preset,
            "before": _role_pair_payload(left, right),
        }

    ir_result = _send_single_ir_action(args=args, action="MUTE")
    main_wait = _wait_for_main_pair_state(
        vid=args.vid,
        pid=args.pid,
        timeout_s=args.timeout_s,
        poll_interval_s=args.main_poll_s,
        expected_preset=preset,
        muted=False,
        active=True,
    )
    lcd_wait = _wait_for_lcd_usable_expected_preset(
        expected_preset=preset,
        args=args,
        output_root=output_root / "lcd_wait",
    )
    left_after, right_after = _read_pair_state(vid=args.vid, pid=args.pid)
    return {
        "context": context,
        "performed": True,
        "expected_preset": preset,
        "ir_result": ir_result,
        "main_wait": main_wait,
        "lcd_wait": lcd_wait,
        "after": _role_pair_payload(left_after, right_after),
    }


def _run_mute_toggle_cycle(
    *,
    expected_preset: str,
    args: argparse.Namespace,
    output_root: Path,
    context: str,
) -> dict[str, object]:
    mute_on_ir = _send_single_ir_action(args=args, action="MUTE")
    mute_on_main = _wait_for_main_pair_state(
        vid=args.vid,
        pid=args.pid,
        timeout_s=args.timeout_s,
        poll_interval_s=args.main_poll_s,
        expected_preset=expected_preset,
        muted=True,
        active=True,
    )
    mute_on_lcd = _wait_for_lcd_text_contains(
        target="Mute",
        timeout_s=args.lcd_timeout_s,
        poll_interval_s=args.lcd_poll_s,
        probe_captures=args.lcd_probe_captures,
        args=args,
        output_root=output_root / "lcd_mute",
    )
    mute_off_ir = _send_single_ir_action(args=args, action="MUTE")
    mute_off_main = _wait_for_main_pair_state(
        vid=args.vid,
        pid=args.pid,
        timeout_s=args.timeout_s,
        poll_interval_s=args.main_poll_s,
        expected_preset=expected_preset,
        muted=False,
        active=True,
    )
    mute_off_lcd = _wait_for_lcd_usable_expected_preset(
        expected_preset=expected_preset,
        args=args,
        output_root=output_root / "lcd_unmute",
    )
    left_after, right_after = _read_pair_state(vid=args.vid, pid=args.pid)
    return {
        "context": context,
        "expected_preset": expected_preset,
        "mute_on_ir": mute_on_ir,
        "mute_on_main": mute_on_main,
        "mute_on_lcd": mute_on_lcd,
        "mute_off_ir": mute_off_ir,
        "mute_off_main": mute_off_main,
        "mute_off_lcd": mute_off_lcd,
        "after": _role_pair_payload(left_after, right_after),
    }


def _run_standby_wake_cycle(
    *,
    expected_preset: str,
    args: argparse.Namespace,
    output_root: Path,
    context: str,
) -> dict[str, object]:
    pre_standby_identity = _capture_sticky_path_roles(vid=args.vid, pid=args.pid)
    sticky_path_roles = dict(pre_standby_identity.get("path_roles", {}))
    standby_ir = _send_single_ir_action(args=args, action="STANDBY")
    standby_lcd = _wait_for_standby_lcd_entry(
        timeout_s=args.lcd_timeout_s,
        poll_interval_s=args.lcd_poll_s,
        probe_captures=args.lcd_probe_captures,
        args=args,
        output_root=output_root / "lcd_standby",
        pre_standby_lcd_visible=True,
    )
    standby_pair = _try_read_pair_state(vid=args.vid, pid=args.pid)
    if args.standby_dwell_s > 0:
        time.sleep(max(0.0, args.standby_dwell_s))
    wake_ir_attempts: list[dict[str, object]] = []
    wake_wait_errors: list[dict[str, object]] = []
    wake_main: dict[str, object] | None = None
    wake_max_attempts = max(1, int(getattr(args, "wake_max_attempts", DEFAULT_WAKE_MAX_ATTEMPTS)))
    wake_retry_delay_s = max(0.0, float(getattr(args, "wake_retry_delay_s", DEFAULT_WAKE_RETRY_DELAY_S)))

    for attempt in range(1, wake_max_attempts + 1):
        wake_ir_attempts.append(_send_single_ir_action(args=args, action="WAKE"))
        try:
            wake_main = _wait_for_wake_two_phase(
                vid=args.vid,
                pid=args.pid,
                timeout_s=args.timeout_s,
                poll_interval_s=args.main_poll_s,
                expected_preset=expected_preset,
                wake_phase_a_timeout_s=args.wake_phase_a_timeout_s,
                wake_phase_b_timeout_s=args.wake_phase_b_timeout_s,
                wake_role_stable_polls=args.wake_role_stable_polls,
                wake_diagnostics_tail=args.wake_diagnostics_tail,
                sticky_path_roles=sticky_path_roles,
            )
            break
        except WakeValidationError as exc:
            wake_wait_errors.append(
                {
                    "attempt": attempt,
                    "code": exc.code,
                    "message": str(exc),
                }
            )
            if exc.code == WAKE_FAILURE_ROLE_DECODE_UNSTABLE:
                raise
            if attempt >= wake_max_attempts:
                raise
            if wake_retry_delay_s > 0:
                time.sleep(wake_retry_delay_s)

    if wake_main is None:
        raise RuntimeError("wake convergence did not complete after WAKE attempts")

    wake_lcd = _wait_for_lcd_usable_expected_preset(
        expected_preset=expected_preset,
        args=args,
        output_root=output_root / "lcd_wake",
    )
    left_after, right_after = _read_pair_state(vid=args.vid, pid=args.pid)
    return {
        "context": context,
        "expected_preset": expected_preset,
        "pre_standby_identity": pre_standby_identity,
        "standby_ir": standby_ir,
        "standby_lcd": standby_lcd,
        "standby_pair": standby_pair,
        "wake_ir": wake_ir_attempts[-1],
        "wake_ir_attempts": wake_ir_attempts,
        "wake_wait_errors": wake_wait_errors,
        "wake_main": wake_main,
        "wake_lcd": wake_lcd,
        "after": _role_pair_payload(left_after, right_after),
    }


def _run_preset_sequence_scenario(
    *,
    scenario_name: str,
    steps: Sequence[IrSequenceStep],
    expected_preset: str,
    args: argparse.Namespace,
) -> Path:
    run_root = args.output_root / scenario_name / time.strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

    states_before = _collect_main_roles(vid=args.vid, pid=args.pid)
    left_before, right_before = _assert_left_right_roles(states_before)
    baseline_lcd = _probe_lcd(
        **_camera_probe_kwargs_from_args(
            args,
            output_root=run_root / "baseline",
            skip_configure=args.skip_configure,
        )
    )

    ir_template = args.ir_command_template or _default_flipper_ir_command_template(
        port=args.flipper_port
    )
    ir_results = _execute_ir_sequence(ir_template=ir_template, steps=steps)
    main_wait = _wait_for_main_pair_preset(
        vid=args.vid,
        pid=args.pid,
        expected_preset=expected_preset,
        timeout_s=args.timeout_s,
        poll_interval_s=args.main_poll_s,
    )
    expected_line2 = f"Active: {expected_preset}"
    lcd_wait = _wait_for_lcd_target(
        expected_line1="Volume",
        expected_line2=expected_line2,
        timeout_s=args.lcd_timeout_s,
        poll_interval_s=args.lcd_poll_s,
        probe_captures=args.lcd_probe_captures,
        args=args,
        output_root=run_root / "lcd_wait",
    )
    after_lcd = _probe_lcd(
        **_camera_probe_kwargs_from_args(
            args,
            output_root=run_root / "after",
            skip_configure=True,
        )
    )
    states_after = _collect_main_roles(vid=args.vid, pid=args.pid)
    left_after, right_after = _assert_left_right_roles(states_after)

    _assert_expected_role_pair(
        left_after,
        right_after,
        expected_preset=expected_preset,
        context=scenario_name,
    )
    _assert_lcd_consensus(
        after_lcd,
        expected_line1="Volume",
        expected_line2=expected_line2,
        context=scenario_name,
    )

    payload = {
        "scenario": scenario_name,
        "run_root": str(run_root),
        "expected_preset": expected_preset,
        "baseline_lcd": baseline_lcd,
        "ir_command_template": ir_template,
        "sequence": [dataclasses.asdict(step) for step in steps],
        "ir_results": ir_results,
        "main_wait": main_wait,
        "lcd_wait": lcd_wait,
        "after_lcd": after_lcd,
        "before": _role_pair_payload(left_before, right_before),
        "after": _role_pair_payload(left_after, right_after),
    }
    out_path = run_root / "result.json"
    out_path.write_text(_json_dumps(payload), encoding="utf-8")
    return out_path


def _probe_lcd(
    *,
    camera_selector: str,
    vendor: int,
    product: int,
    address: int,
    zoom: int,
    focus: int,
    exposure: int,
    gain: int,
    sharpness: int,
    captures: int,
    warmup_s: float,
    skip_configure: bool,
    output_root: Path,
) -> dict[str, object]:
    run_root = output_root / "lcd" / time.strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="dlcp_hw_state_lcd_") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        capture_swift = tmpdir / "capture.swift"
        ocr_swift = tmpdir / "ocr.swift"
        capture_swift.write_text(textwrap.dedent(lcd_probe._CAPTURE_SWIFT), encoding="utf-8")
        ocr_swift.write_text(textwrap.dedent(lcd_probe._OCR_SWIFT), encoding="utf-8")

        config = None
        if not skip_configure:
            config = lcd_probe._configure_camera(
                argparse.Namespace(
                    camera_selector=camera_selector,
                    vendor=vendor,
                    product=product,
                    address=address,
                    zoom=zoom,
                    focus=focus,
                    exposure=exposure,
                    gain=gain,
                    sharpness=sharpness,
                )
            )

        captures_out = []
        line1_values: list[str | None] = []
        line2_values: list[str | None] = []
        for index in range(captures):
            image_path = run_root / f"capture_{index + 1}.jpg"
            lcd_probe._capture_frame(capture_swift, camera_selector, image_path, warmup_s)
            observations = lcd_probe._ocr_frame(ocr_swift, image_path)
            line1, line2 = lcd_probe._pick_lines(observations)
            line1_values.append(line1)
            line2_values.append(line2)
            captures_out.append(
                {
                    "image_path": str(image_path),
                    "line1": line1,
                    "line2": line2,
                    "observations": [dataclasses.asdict(item) for item in observations],
                }
            )

    summary = {
        "run_root": str(run_root),
        "camera_selector": camera_selector,
        "configured": config,
        "captures": captures_out,
        "consensus": {
            "line1": lcd_probe._consensus(line1_values),
            "line2": lcd_probe._consensus_active(line2_values),
        },
    }
    summary_path = run_root / "summary.json"
    summary_path.write_text(_json_dumps(summary), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def _cmd_detect(args: argparse.Namespace) -> int:
    payload = {
        "cameras": _camera_inventory(),
        "flipper": _flipper_inventory(),
        "hid_devices": _snapshot_visible_mains(vid=args.vid, pid=args.pid),
    }
    print(_json_dumps(payload))
    return 0


def _cmd_identify_mains(args: argparse.Namespace) -> int:
    states = _collect_main_roles(vid=args.vid, pid=args.pid)
    payload = {
        "mains": [dataclasses.asdict(item) for item in states],
    }
    if args.require_left_right:
        left, right = _assert_left_right_roles(states)
        payload["left"] = dataclasses.asdict(left)
        payload["right"] = dataclasses.asdict(right)
    print(_json_dumps(payload))
    return 0


def _cmd_preset_convergence(args: argparse.Namespace) -> int:
    action = _normalize_preset_action(args.action)
    out_path = _run_preset_sequence_scenario(
        scenario_name="preset_convergence",
        steps=[IrSequenceStep(action=action)],
        expected_preset=_expected_preset_for_action(action),
        args=args,
    )
    print(_json_dumps({"result_path": str(out_path), "status": "PASS"}))
    return 0


def _cmd_rapid_toggle_convergence(args: argparse.Namespace) -> int:
    actions = _parse_preset_sequence(args.sequence)
    inter_press_s = max(0.0, args.inter_press_ms / 1000.0)
    steps = [
        IrSequenceStep(
            action=action,
            sleep_after_s=(inter_press_s if index + 1 < len(actions) else 0.0),
        )
        for index, action in enumerate(actions)
    ]
    out_path = _run_preset_sequence_scenario(
        scenario_name="rapid_toggle_convergence",
        steps=steps,
        expected_preset=_expected_preset_for_action(actions[-1]),
        args=args,
    )
    print(_json_dumps({"result_path": str(out_path), "status": "PASS"}))
    return 0


def _cmd_preset_mute_timing_sweep(args: argparse.Namespace) -> int:
    delays_ms = _parse_delays_ms(args.delays_ms)
    run_root = args.output_root / "preset_mute_timing_sweep" / time.strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

    baseline_pair = _read_pair_state(vid=args.vid, pid=args.pid)
    baseline_lcd = _probe_lcd(
        **_camera_probe_kwargs_from_args(
            args,
            output_root=run_root / "baseline",
            skip_configure=args.skip_configure,
        )
    )
    unmute_sync = _ensure_pair_unmuted(
        args=args,
        output_root=run_root / "ensure_unmuted",
        context="preset_mute_timing_sweep.ensure_unmuted",
    )

    iterations: list[dict[str, object]] = []
    for index, delay_ms in enumerate(delays_ms, start=1):
        iteration_root = run_root / f"delay_{int(round(delay_ms)):04d}ms"
        action = _next_preset_action_from_pair(vid=args.vid, pid=args.pid)
        preset_phase = _run_preset_action_and_wait(
            action=action,
            args=args,
            output_root=iteration_root / "preset",
            context=f"preset_mute_timing_sweep.iteration_{index}.preset",
        )
        delay_s = _sleep_ms(delay_ms)
        mute_phase = _run_mute_toggle_cycle(
            expected_preset=preset_phase["expected_preset"],
            args=args,
            output_root=iteration_root / "mute_cycle",
            context=f"preset_mute_timing_sweep.iteration_{index}.mute_cycle",
        )
        iterations.append(
            {
                "index": index,
                "delay_ms": delay_ms,
                "delay_s": delay_s,
                "preset_phase": preset_phase,
                "mute_cycle": mute_phase,
            }
        )

    left_after, right_after = _read_pair_state(vid=args.vid, pid=args.pid)
    final_lcd = _probe_lcd(
        **_camera_probe_kwargs_from_args(
            args,
            output_root=run_root / "final",
            skip_configure=True,
        )
    )
    payload = {
        "scenario": "preset_mute_timing_sweep",
        "run_root": str(run_root),
        "delays_ms": delays_ms,
        "before": _role_pair_payload(*baseline_pair),
        "baseline_lcd": baseline_lcd,
        "ensure_unmuted": unmute_sync,
        "iterations": iterations,
        "after": _role_pair_payload(left_after, right_after),
        "final_lcd": final_lcd,
    }
    out_path = run_root / "result.json"
    out_path.write_text(_json_dumps(payload), encoding="utf-8")
    print(_json_dumps({"result_path": str(out_path), "status": "PASS"}))
    return 0


def _cmd_preset_standby_wake_timing_sweep(args: argparse.Namespace) -> int:
    delays_ms = _parse_delays_ms(args.delays_ms)
    run_root = args.output_root / "preset_standby_wake_timing_sweep" / time.strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

    baseline_pair = _read_pair_state(vid=args.vid, pid=args.pid)
    baseline_lcd = _probe_lcd(
        **_camera_probe_kwargs_from_args(
            args,
            output_root=run_root / "baseline",
            skip_configure=args.skip_configure,
        )
    )
    unmute_sync = _ensure_pair_unmuted(
        args=args,
        output_root=run_root / "ensure_unmuted",
        context="preset_standby_wake_timing_sweep.ensure_unmuted",
    )

    iterations: list[dict[str, object]] = []
    for index, delay_ms in enumerate(delays_ms, start=1):
        iteration_root = run_root / f"delay_{int(round(delay_ms)):04d}ms"
        action = _next_preset_action_from_pair(vid=args.vid, pid=args.pid)
        preset_phase = _run_preset_action_and_wait(
            action=action,
            args=args,
            output_root=iteration_root / "preset",
            context=f"preset_standby_wake_timing_sweep.iteration_{index}.preset",
        )
        delay_s = _sleep_ms(delay_ms)
        standby_phase = _run_standby_wake_cycle(
            expected_preset=preset_phase["expected_preset"],
            args=args,
            output_root=iteration_root / "standby_wake",
            context=f"preset_standby_wake_timing_sweep.iteration_{index}.standby_wake",
        )
        iterations.append(
            {
                "index": index,
                "delay_ms": delay_ms,
                "delay_s": delay_s,
                "preset_phase": preset_phase,
                "standby_wake": standby_phase,
            }
        )

    left_after, right_after = _read_pair_state(vid=args.vid, pid=args.pid)
    final_lcd = _probe_lcd(
        **_camera_probe_kwargs_from_args(
            args,
            output_root=run_root / "final",
            skip_configure=True,
        )
    )
    payload = {
        "scenario": "preset_standby_wake_timing_sweep",
        "run_root": str(run_root),
        "delays_ms": delays_ms,
        "before": _role_pair_payload(*baseline_pair),
        "baseline_lcd": baseline_lcd,
        "ensure_unmuted": unmute_sync,
        "iterations": iterations,
        "after": _role_pair_payload(left_after, right_after),
        "final_lcd": final_lcd,
    }
    out_path = run_root / "result.json"
    out_path.write_text(_json_dumps(payload), encoding="utf-8")
    print(_json_dumps({"result_path": str(out_path), "status": "PASS"}))
    return 0


def _cmd_reconnect_responsiveness_soak(args: argparse.Namespace) -> int:
    run_root = args.output_root / "reconnect_responsiveness_soak" / time.strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

    baseline_pair = _read_pair_state(vid=args.vid, pid=args.pid)
    baseline_lcd = _probe_lcd(
        **_camera_probe_kwargs_from_args(
            args,
            output_root=run_root / "baseline",
            skip_configure=args.skip_configure,
        )
    )
    unmute_sync = _ensure_pair_unmuted(
        args=args,
        output_root=run_root / "ensure_unmuted",
        context="reconnect_responsiveness_soak.ensure_unmuted",
    )

    iterations: list[dict[str, object]] = []
    for index in range(1, args.iterations + 1):
        iteration_root = run_root / f"iteration_{index:03d}"
        action = _next_preset_action_from_pair(vid=args.vid, pid=args.pid)
        preset_phase = _run_preset_action_and_wait(
            action=action,
            args=args,
            output_root=iteration_root / "preset",
            context=f"reconnect_responsiveness_soak.iteration_{index}.preset",
        )
        standby_phase = _run_standby_wake_cycle(
            expected_preset=preset_phase["expected_preset"],
            args=args,
            output_root=iteration_root / "standby_wake",
            context=f"reconnect_responsiveness_soak.iteration_{index}.standby_wake",
        )
        mute_phase = _run_mute_toggle_cycle(
            expected_preset=preset_phase["expected_preset"],
            args=args,
            output_root=iteration_root / "mute_cycle",
            context=f"reconnect_responsiveness_soak.iteration_{index}.mute_cycle",
        )
        iterations.append(
            {
                "index": index,
                "preset_phase": preset_phase,
                "standby_wake": standby_phase,
                "mute_cycle": mute_phase,
            }
        )

    left_after, right_after = _read_pair_state(vid=args.vid, pid=args.pid)
    final_lcd = _probe_lcd(
        **_camera_probe_kwargs_from_args(
            args,
            output_root=run_root / "final",
            skip_configure=True,
        )
    )
    payload = {
        "scenario": "reconnect_responsiveness_soak",
        "run_root": str(run_root),
        "iterations_requested": args.iterations,
        "before": _role_pair_payload(*baseline_pair),
        "baseline_lcd": baseline_lcd,
        "ensure_unmuted": unmute_sync,
        "iterations": iterations,
        "after": _role_pair_payload(left_after, right_after),
        "final_lcd": final_lcd,
    }
    out_path = run_root / "result.json"
    out_path.write_text(_json_dumps(payload), encoding="utf-8")
    print(_json_dumps({"result_path": str(out_path), "status": "PASS"}))
    return 0


def _cmd_ir_preset_roundtrip(args: argparse.Namespace) -> int:
    run_root = args.output_root / "ir_preset_roundtrip" / time.strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

    states_before = _collect_main_roles(vid=args.vid, pid=args.pid)
    left_before, right_before = _assert_left_right_roles(states_before)
    baseline_lcd = _probe_lcd(
        camera_selector=args.camera_selector,
        vendor=args.vendor,
        product=args.product,
        address=args.address,
        zoom=args.zoom,
        focus=args.focus,
        exposure=args.exposure,
        gain=args.gain,
        sharpness=args.sharpness,
        captures=args.captures,
        warmup_s=args.warmup_s,
        skip_configure=args.skip_configure,
        output_root=run_root / "baseline",
    )

    ir_template = args.ir_command_template or _default_flipper_ir_command_template(
        port=args.flipper_port
    )
    ir_result = _send_ir(ir_template, action=args.action)
    time.sleep(max(0.0, args.settle_s))

    lcd_after = _probe_lcd(
        camera_selector=args.camera_selector,
        vendor=args.vendor,
        product=args.product,
        address=args.address,
        zoom=args.zoom,
        focus=args.focus,
        exposure=args.exposure,
        gain=args.gain,
        sharpness=args.sharpness,
        captures=args.captures,
        warmup_s=args.warmup_s,
        # Reuse the baseline camera state to avoid injecting a second UVC control
        # step into the timing window being validated.
        skip_configure=True,
        output_root=run_root / "after",
    )

    states_after = _collect_main_roles(vid=args.vid, pid=args.pid)
    left_after, right_after = _assert_left_right_roles(states_after)

    expected_line2 = f"Active: {args.expected_preset}"
    lcd_line1 = lcd_after["consensus"]["line1"]
    lcd_line2 = lcd_after["consensus"]["line2"]
    if lcd_line1 != "Volume":
        raise RuntimeError(
            f"unexpected LCD line1 after {args.action}: got {lcd_line1!r}, expected 'Volume'"
        )
    if lcd_line2 != expected_line2:
        raise RuntimeError(
            f"unexpected LCD line2 after {args.action}: got {lcd_line2!r}, expected {expected_line2!r}"
        )
    for item in (left_after, right_after):
        if item.active_preset != args.expected_preset:
            raise RuntimeError(
                f"MAIN role {item.role} did not reach preset {args.expected_preset}: "
                f"path={item.path} active_preset={item.active_preset!r}"
            )

    payload = {
        "run_root": str(run_root),
        "baseline_lcd": baseline_lcd,
        "ir_command_template": ir_template,
        "ir": ir_result,
        "after_lcd": lcd_after,
        "before": {
            "left": dataclasses.asdict(left_before),
            "right": dataclasses.asdict(right_before),
        },
        "after": {
            "left": dataclasses.asdict(left_after),
            "right": dataclasses.asdict(right_after),
        },
    }
    out_path = run_root / "result.json"
    out_path.write_text(_json_dumps(payload), encoding="utf-8")
    print(_json_dumps({"result_path": str(out_path), "status": "PASS"}))
    return 0


def _add_camera_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--camera-selector", default=lcd_probe.DEFAULT_CAMERA_NAME)
    parser.add_argument("--vendor", type=int, default=lcd_probe.DEFAULT_CAMERA_VENDOR)
    parser.add_argument("--product", type=int, default=lcd_probe.DEFAULT_CAMERA_PRODUCT)
    parser.add_argument("--address", type=int, default=lcd_probe.DEFAULT_CAMERA_ADDRESS)
    parser.add_argument("--zoom", type=int, default=lcd_probe.DEFAULT_CAMERA_ZOOM)
    parser.add_argument("--focus", type=int, default=lcd_probe.DEFAULT_CAMERA_FOCUS)
    parser.add_argument("--exposure", type=int, default=lcd_probe.DEFAULT_CAMERA_EXPOSURE)
    parser.add_argument("--gain", type=int, default=lcd_probe.DEFAULT_CAMERA_GAIN)
    parser.add_argument("--sharpness", type=int, default=lcd_probe.DEFAULT_CAMERA_SHARPNESS)
    parser.add_argument("--captures", type=int, default=lcd_probe.DEFAULT_CAPTURE_COUNT)
    parser.add_argument("--warmup-s", type=float, default=lcd_probe.DEFAULT_WARMUP_S)
    parser.add_argument("--skip-configure", action="store_true")


def _add_ir_transport_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ir-command-template",
        help="optional command template used to send IR; supports {action}, {action_lower}, {action_upper}",
    )
    parser.add_argument("--flipper-port", help="optional Flipper serial port for the built-in sender")


def _add_convergence_wait_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_MAIN_TIMEOUT_S)
    parser.add_argument("--main-poll-s", type=float, default=DEFAULT_MAIN_POLL_S)
    parser.add_argument("--lcd-timeout-s", type=float, default=DEFAULT_LCD_TIMEOUT_S)
    parser.add_argument("--lcd-poll-s", type=float, default=DEFAULT_LCD_POLL_S)
    parser.add_argument("--lcd-probe-captures", type=int, default=DEFAULT_LCD_PROBE_CAPTURES)


def _add_delay_sweep_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--delays-ms",
        default="50,100,250,500,1000",
        help="comma-separated delays in milliseconds",
    )


def _add_standby_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--standby-dwell-s", type=float, default=DEFAULT_STANDBY_DWELL_S)
    parser.add_argument(
        "--standby-blank-consecutive",
        type=int,
        default=DEFAULT_STANDBY_BLANK_CONSECUTIVE,
        help=(
            "number of consecutive None/None LCD probes required for guarded standby fallback "
            "when backlight is too dim for OCR"
        ),
    )
    parser.add_argument(
        "--no-standby-blank-fallback",
        action="store_false",
        dest="standby_allow_blank_fallback",
        help="require literal 'Zzz...' OCR for standby entry",
    )
    parser.add_argument(
        "--wake-max-attempts",
        type=int,
        default=DEFAULT_WAKE_MAX_ATTEMPTS,
        help="maximum WAKE endpoint retries before failing convergence",
    )
    parser.add_argument(
        "--wake-retry-delay-s",
        type=float,
        default=DEFAULT_WAKE_RETRY_DELAY_S,
        help="delay between WAKE retry attempts",
    )
    parser.add_argument(
        "--wake-phase-a-timeout-s",
        type=float,
        default=None,
        help="phase A timeout: functional wake gate (visible+active+preset converged); defaults to --timeout-s",
    )
    parser.add_argument(
        "--wake-phase-b-timeout-s",
        type=float,
        default=None,
        help="phase B timeout: LEFT/RIGHT role decode stabilization gate; defaults to --timeout-s",
    )
    parser.add_argument(
        "--wake-role-stable-polls",
        type=int,
        default=DEFAULT_WAKE_ROLE_STABLE_POLLS,
        help="consecutive polls with decoded LEFT/RIGHT required to pass wake phase B",
    )
    parser.add_argument(
        "--wake-diagnostics-tail",
        type=int,
        default=DEFAULT_WAKE_DIAGNOSTICS_TAIL,
        help="number of recent wake poll samples included in wake timeout diagnostics",
    )
    parser.set_defaults(standby_allow_blank_fallback=True)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vid", type=int, default=DEFAULT_VID)
    ap.add_argument("--pid", type=int, default=DEFAULT_PID)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)

    sub = ap.add_subparsers(dest="cmd", required=True)

    p_detect = sub.add_parser("detect", help="inventory visible cameras, Flipper helpers, and DLCP HID devices")
    p_detect.set_defaults(func=_cmd_detect)

    p_roles = sub.add_parser("identify-mains", help="read each visible MAIN and classify LEFT/RIGHT from route memory")
    p_roles.add_argument("--require-left-right", action="store_true", help="fail unless exactly one LEFT and one RIGHT are visible")
    p_roles.set_defaults(func=_cmd_identify_mains)

    p_conv = sub.add_parser(
        "preset-convergence",
        help="send one real IR preset action and wait for both MAINs and the LCD to converge",
    )
    p_conv.add_argument("--action", required=True, help="preset IR action: F1 or F2")
    _add_ir_transport_args(p_conv)
    _add_convergence_wait_args(p_conv)
    _add_camera_args(p_conv)
    p_conv.set_defaults(func=_cmd_preset_convergence)

    p_rapid = sub.add_parser(
        "rapid-toggle-convergence",
        help="send a timed F1/F2 sequence and verify final convergence on both MAINs and the LCD",
    )
    p_rapid.add_argument(
        "--sequence",
        required=True,
        help="comma-separated preset IR actions, e.g. F1,F2,F1,F2",
    )
    p_rapid.add_argument("--inter-press-ms", type=float, default=250.0)
    _add_ir_transport_args(p_rapid)
    _add_convergence_wait_args(p_rapid)
    _add_camera_args(p_rapid)
    p_rapid.set_defaults(func=_cmd_rapid_toggle_convergence)

    p_mute = sub.add_parser(
        "preset-mute-timing-sweep",
        help="for each delay, switch preset, then verify MUTE and MUTE-off preserve pair convergence",
    )
    _add_ir_transport_args(p_mute)
    _add_delay_sweep_args(p_mute)
    _add_convergence_wait_args(p_mute)
    _add_camera_args(p_mute)
    p_mute.set_defaults(func=_cmd_preset_mute_timing_sweep)

    p_stby = sub.add_parser(
        "preset-standby-wake-timing-sweep",
        help="for each delay, switch preset, enter standby, then verify wake/reconnect preserves convergence",
    )
    _add_ir_transport_args(p_stby)
    _add_delay_sweep_args(p_stby)
    _add_standby_args(p_stby)
    _add_convergence_wait_args(p_stby)
    _add_camera_args(p_stby)
    p_stby.set_defaults(func=_cmd_preset_standby_wake_timing_sweep)

    p_soak = sub.add_parser(
        "reconnect-responsiveness-soak",
        help="repeat preset switch, standby/wake, and mute cycles to catch liveness regressions",
    )
    _add_ir_transport_args(p_soak)
    p_soak.add_argument("--iterations", type=int, default=DEFAULT_SOAK_ITERATIONS)
    _add_standby_args(p_soak)
    _add_convergence_wait_args(p_soak)
    _add_camera_args(p_soak)
    p_soak.set_defaults(func=_cmd_reconnect_responsiveness_soak)

    p_ir = sub.add_parser(
        "ir-preset-roundtrip",
        help="send one preset-select IR action, then verify LCD and both MAIN memories",
    )
    p_ir.add_argument("--action", required=True, help="logical IR action name, e.g. F1 or F2")
    p_ir.add_argument("--expected-preset", choices=("A", "B"), required=True)
    _add_ir_transport_args(p_ir)
    p_ir.add_argument("--settle-s", type=float, default=1.0)
    _add_camera_args(p_ir)
    p_ir.set_defaults(func=_cmd_ir_preset_roundtrip)

    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
