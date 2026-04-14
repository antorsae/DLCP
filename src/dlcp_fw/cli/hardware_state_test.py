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
        "raw_window_hex": state.raw_window_hex,
        "mode": state.mode,
        "version": state.version,
    }


def _assert_lcd_consensus(
    summary: dict[str, object],
    *,
    expected_line1: str,
    expected_line2: str,
    context: str,
) -> None:
    consensus = summary["consensus"]
    actual_line1 = consensus["line1"]
    actual_line2 = consensus["line2"]
    if actual_line1 != expected_line1 or actual_line2 != expected_line2:
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
    started = time.monotonic()
    deadline = started + max(0.0, timeout_s)
    left_reached_s: float | None = None
    right_reached_s: float | None = None
    both_reached_s: float | None = None
    observations: list[dict[str, object]] = []
    last_left: MainRoleState | None = None
    last_right: MainRoleState | None = None

    while True:
        states = _collect_main_roles(vid=vid, pid=pid)
        left, right = _assert_left_right_roles(states)
        last_left, last_right = left, right
        elapsed = time.monotonic() - started
        observations.append(
            {
                "t_s": elapsed,
                "left": _compact_role_observation(left),
                "right": _compact_role_observation(right),
            }
        )
        if left.active_preset == expected_preset and left_reached_s is None:
            left_reached_s = elapsed
        if right.active_preset == expected_preset and right_reached_s is None:
            right_reached_s = elapsed
        if (
            left.active_preset == expected_preset
            and right.active_preset == expected_preset
            and both_reached_s is None
        ):
            both_reached_s = elapsed
            return {
                "expected_preset": expected_preset,
                "timeout_s": timeout_s,
                "poll_interval_s": poll_interval_s,
                "left_reached_s": left_reached_s,
                "right_reached_s": right_reached_s,
                "both_reached_s": both_reached_s,
                "observations": observations,
                "final": _role_pair_payload(left, right),
            }
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, poll_interval_s))

    raise RuntimeError(
        f"timed out waiting for both MAINs to reach preset {expected_preset}; "
        f"left={None if last_left is None else last_left.active_preset!r} "
        f"right={None if last_right is None else last_right.active_preset!r}"
    )


def _wait_for_lcd_target(
    *,
    expected_line1: str,
    expected_line2: str,
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
        if line1 == expected_line1 and line2 == expected_line2:
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
