from __future__ import annotations

import os
from pathlib import Path

import pytest

from dlcp_fw.cli import hardware_state_test as hw


pytestmark = [pytest.mark.hardware, pytest.mark.slow]


def _common_cli_args() -> list[str]:
    output_root = Path(
        os.environ.get(
            "DLCP_HW_OUTPUT_ROOT",
            str(hw.DEFAULT_OUTPUT_ROOT / "pytest"),
        )
    )
    args = ["--output-root", str(output_root)]

    flipper_port = os.environ.get("DLCP_HW_FLIPPER_PORT")
    if flipper_port:
        args.extend(["--flipper-port", flipper_port])

    camera_selector = os.environ.get("DLCP_HW_CAMERA_SELECTOR")
    if camera_selector:
        args.extend(["--camera-selector", camera_selector])

    camera_address = os.environ.get("DLCP_HW_CAMERA_ADDRESS")
    if camera_address:
        args.extend(["--address", camera_address])

    if os.environ.get("DLCP_HW_SKIP_CONFIGURE") == "1":
        args.append("--skip-configure")

    return args


def _env_float(name: str, default: float) -> str:
    return os.environ.get(name, str(default))


def _env_int(name: str, default: int) -> str:
    return os.environ.get(name, str(default))


def _parse_int_auto(value: str, *, name: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise AssertionError(f"{name} must be an integer literal, got {value!r}") from exc


def _parse_byte_auto(value: str, *, name: str) -> int:
    parsed = _parse_int_auto(value, name=name)
    if not 0 <= parsed <= 0xFF:
        raise AssertionError(
            f"{name} must be a byte value in 0x00..0xFF, got {value!r}"
        )
    return parsed


_SETUP_PROFILE_RAM = 0x0B8


def _current_pair_preset() -> str:
    states = hw._collect_main_roles(vid=hw.DEFAULT_VID, pid=hw.DEFAULT_PID)
    left, right = hw._assert_left_right_roles(states)
    if left.active_preset not in {"A", "B"} or right.active_preset not in {"A", "B"}:
        raise RuntimeError(
            f"unable to determine current pair preset: left={left.active_preset!r} "
            f"right={right.active_preset!r}"
        )
    if left.active_preset != right.active_preset:
        raise RuntimeError(
            f"pair is already split before test start: left={left.active_preset!r} "
            f"right={right.active_preset!r}"
        )
    return left.active_preset


def _require_live_rig_accessible() -> None:
    if not os.environ.get("DLCP_HW_CAMERA_SELECTOR"):
        cameras = hw._load_avfoundation_video_devices()
        if not cameras:
            pytest.skip("no camera devices visible; set DLCP_HW_CAMERA_SELECTOR or connect the LCD camera")

    if not os.environ.get("DLCP_HW_FLIPPER_PORT"):
        ports = hw.hardware_flipper_ir.discover_flipper_serial_ports()
        if not ports:
            pytest.skip("no Flipper serial port visible; set DLCP_HW_FLIPPER_PORT or connect Flipper over USB")

    try:
        _current_pair_preset()
    except OSError as exc:
        pytest.skip(f"MAIN HID devices are visible but not openable: {exc}")
    except RuntimeError as exc:
        pytest.skip(f"live rig preflight failed: {exc}")


def _require_main_pair_and_camera_accessible() -> None:
    if not os.environ.get("DLCP_HW_CAMERA_SELECTOR"):
        cameras = hw._load_avfoundation_video_devices()
        if not cameras:
            pytest.skip("no camera devices visible; set DLCP_HW_CAMERA_SELECTOR or connect the LCD camera")

    try:
        hw._read_pair_state(vid=hw.DEFAULT_VID, pid=hw.DEFAULT_PID)
    except OSError as exc:
        pytest.skip(f"MAIN HID devices are visible but not openable: {exc}")
    except RuntimeError as exc:
        pytest.skip(f"live MAIN pair preflight failed: {exc}")


def _require_main_pair_and_flipper_accessible() -> None:
    if not os.environ.get("DLCP_HW_FLIPPER_PORT"):
        ports = hw.hardware_flipper_ir.discover_flipper_serial_ports()
        if not ports:
            pytest.skip("no Flipper serial port visible; set DLCP_HW_FLIPPER_PORT or connect Flipper over USB")

    try:
        hw._read_pair_state(vid=hw.DEFAULT_VID, pid=hw.DEFAULT_PID)
    except OSError as exc:
        pytest.skip(f"MAIN HID devices are visible but not openable: {exc}")
    except RuntimeError as exc:
        pytest.skip(f"live MAIN pair preflight failed: {exc}")


def _release_capture_name(meta_path: Path) -> str:
    import json

    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    name = payload.get("config_name")
    if not isinstance(name, str) or not name:
        raise RuntimeError(f"release capture sidecar has no config_name: {meta_path}")
    return name


def _active_filename_via_cmd03(path: bytes) -> str:
    from dlcp_fw.flash import dlcp_main_flash as main_flash

    dev = main_flash._open_hid(path)
    try:
        return main_flash.decode_filename_slot(main_flash._cmd03_read_filename_slot(dev))
    finally:
        try:
            dev.close()
        except Exception:
            pass


def _signed_u8(value: int) -> int:
    value &= 0xFF
    return value - 0x100 if value & 0x80 else value


def _running_main_logical_volume_lows() -> dict[str, int]:
    from dlcp_fw.flash import dlcp_main_flash as main_flash

    out: dict[str, int] = {}
    for dev in main_flash.enumerate_devices(hw.DEFAULT_VID, hw.DEFAULT_PID):
        if dev.path is None:
            continue
        snapshot = main_flash._probe_device_snapshot(
            info=dev,
            vid=hw.DEFAULT_VID,
            pid=hw.DEFAULT_PID,
        )
        if snapshot.mode != "app" or snapshot.volume_state is None:
            continue
        path_text = dev.path.decode("utf-8", errors="replace")
        out[path_text] = snapshot.volume_state.logical_low
    return out


def _running_main_user_settings() -> dict[str, dict[str, int]]:
    from dlcp_fw.flash import dlcp_main_flash as main_flash

    out: dict[str, dict[str, int]] = {}
    for dev in main_flash.enumerate_devices(hw.DEFAULT_VID, hw.DEFAULT_PID):
        if dev.path is None:
            continue
        snapshot = main_flash._probe_device_snapshot(
            info=dev,
            vid=hw.DEFAULT_VID,
            pid=hw.DEFAULT_PID,
        )
        if snapshot.mode != "app" or snapshot.volume_state is None:
            continue
        ep0 = main_flash._make_dlcp_ep0(
            vid=hw.DEFAULT_VID,
            pid=hw.DEFAULT_PID,
            path=dev.path,
        )
        path_text = dev.path.decode("utf-8", errors="replace")
        out[path_text] = {
            "logical_low": snapshot.volume_state.logical_low,
            "computed_low": snapshot.volume_state.computed_low,
            "input_select": main_flash._ep0_read_byte(ep0, addr=0x099),
            "input_mirror": main_flash._ep0_read_byte(ep0, addr=0x0B3),
            "setup_profile": main_flash._ep0_read_byte(ep0, addr=_SETUP_PROFILE_RAM),
        }
    return out


def _wait_for_volume_change(
    before: dict[str, int],
    *,
    timeout_s: float = 5.0,
    poll_s: float = 0.1,
) -> dict[str, int]:
    import time

    deadline = time.monotonic() + timeout_s
    while True:
        after = _running_main_logical_volume_lows()
        if after.keys() == before.keys() and after and all(
            after[path] != before[path] for path in before
        ):
            return after
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"volume did not change on every MAIN before timeout: "
                f"before={before!r} after={after!r}"
            )
        time.sleep(max(0.0, poll_s))


def _volume_action_and_restore(before: dict[str, int]) -> tuple[str, str]:
    signed = [_signed_u8(value) for value in before.values()]
    if not signed:
        raise AssertionError("cannot choose volume IR action without MAIN volume readbacks")
    if all(value < 0 for value in signed):
        return "VOL_UP", "VOL_DOWN"
    if all(value > -96 for value in signed):
        return "VOL_DOWN", "VOL_UP"
    raise AssertionError(
        "cannot choose a single volume IR direction that should move every MAIN; "
        f"signed logical volumes={signed!r}"
    )


def _legacy_ir_action(action: str, *, profile: str) -> str:
    normalized = profile.strip().upper()
    if normalized in {"", "HYPEX"}:
        return action
    if normalized in {"STANDARD", "STD", "RC5"}:
        mapping = {
            "POWER": "STD_POWER",
            "MUTE": "STD_MUTE",
            "VOL_UP": "STD_VOL_UP",
            "VOL_DOWN": "STD_VOL_DOWN",
        }
        if action not in mapping:
            raise AssertionError(
                "standard RC5 profile only covers legacy POWER/MUTE/VOL_UP/"
                f"VOL_DOWN actions in this gate; got {action!r}"
            )
        return mapping[action]
    raise AssertionError(
        "DLCP_HW_IR_PROFILE must be HYPEX or STANDARD/RC5; "
        f"got {profile!r}"
    )


def _expected_control_hex_identity(expected_control: str) -> dict[str, object]:
    from dlcp_fw.flash import dlcp_control_flash
    from dlcp_fw.paths import STOCK_CONTROL_HEX_V16B, V171_CONTROL_HEX

    hex_paths = {
        "V1.6b": STOCK_CONTROL_HEX_V16B,
        "V1.71": V171_CONTROL_HEX,
    }
    hex_path = hex_paths[expected_control]
    hex_mem = dlcp_control_flash.parse_intel_hex(str(hex_path))
    release = dlcp_control_flash.detect_static_hex_control_release_info(hex_mem)
    preflight = dlcp_control_flash.run_preflight(
        hex_mem=hex_mem,
        bootloader_ref_mem=None,
        require_bootloader_match=False,
    )

    return {
        "expected_control": expected_control,
        "hex_path": str(hex_path),
        "release_short": dlcp_control_flash._format_control_release_short(release),
        "version": None
        if release is None
        else {
            "major": release.major,
            "minor": release.minor,
            "sub": release.sub,
            "sub_ascii": chr(release.sub)
            if 0x20 <= release.sub <= 0x7E
            else None,
            "revision": release.revision,
        },
        "payload_len": preflight["payload_len"],
        "payload_crc": preflight["payload_crc"],
        "payload_sha256": preflight["payload_sha256"],
        "app_sha256": preflight["app_sha256"],
        "boot_sha256": preflight["boot_sha256"],
    }


def _require_hypex_ir_profile_for_hypex_only_gate(gate: str) -> None:
    profile = os.environ.get("DLCP_HW_IR_PROFILE", "HYPEX").strip().upper()
    if profile in {"", "HYPEX"}:
        return
    raise AssertionError(
        f"{gate} sends Hypex-profile IR actions, including F1/F2 preset "
        "shortcuts and V1.71 STANDBY/WAKE endpoints. Run this gate with "
        "DLCP_HW_IR_PROFILE=HYPEX; use the legacy IR stress or receiver "
        "sweep for STANDARD/RC5 profile evidence."
    )


def _wait_for_standby_evidence(
    *,
    timeout_s: float = 8.0,
    poll_s: float = 0.2,
    stable_polls: int = 2,
) -> dict[str, object]:
    import time

    deadline = time.monotonic() + timeout_s
    last: object = None
    consecutive = 0
    last_mode: str | None = None
    samples: list[dict[str, object]] = []
    while True:
        evidence: dict[str, object] | None = None
        try:
            states = hw._collect_main_roles(vid=hw.DEFAULT_VID, pid=hw.DEFAULT_PID)
            last = [state.raw_window_hex for state in states]
            if not states:
                evidence = {"mode": "no_visible_mains"}
            else:
                active_values = [hw._is_active_state(state) for state in states]
                if len(active_values) == 2 and all(value is False for value in active_values):
                    evidence = {
                        "mode": "both_mains_inactive",
                        "active_values": active_values,
                    }
        except Exception as exc:
            last = str(exc)
            evidence = {"mode": "main_probe_error", "error": str(exc)}

        if evidence is None:
            consecutive = 0
            last_mode = None
        else:
            mode = str(evidence["mode"])
            if mode == last_mode:
                consecutive += 1
            else:
                consecutive = 1
                last_mode = mode
            evidence = {**evidence, "consecutive": consecutive}
            samples.append(evidence)
            if consecutive >= max(1, stable_polls):
                return {**evidence, "samples": samples[-max(1, stable_polls) :]}

        if time.monotonic() >= deadline:
            raise AssertionError(
                f"stable standby evidence did not appear before timeout; "
                f"last={last!r} mode={last_mode!r} consecutive={consecutive} "
                f"samples={samples[-5:]!r}"
            )
        time.sleep(max(0.0, poll_s))


def _capture_lcd_consensus(tmp_path: Path, name: str) -> tuple[str, str]:
    import json
    from dlcp_fw.cli import hardware_lcd_probe

    output_root = tmp_path / name
    argv: list[str] = [
        "--captures",
        os.environ.get("DLCP_HW_LAYER5_LCD_CAPTURES", "10"),
        "--output-root",
        str(output_root),
    ]
    selector = os.environ.get("DLCP_HW_CAMERA_SELECTOR")
    if selector:
        argv.extend(["--camera-selector", selector])
    address = os.environ.get("DLCP_HW_CAMERA_ADDRESS")
    if address:
        argv.extend(["--address", address])
    if os.environ.get("DLCP_HW_SKIP_CONFIGURE") == "1":
        argv.append("--skip-configure")

    rc = hardware_lcd_probe.main(argv)
    assert rc == 0, "lcd-probe wrapper failed (camera or OCR)"
    summaries = sorted((output_root / "runs").glob("*/summary.json"))
    assert summaries, f"no LCD summary written under {output_root / 'runs'}"
    summary = json.loads(summaries[-1].read_text(encoding="utf-8"))
    consensus = summary.get("consensus", {})
    return (
        (consensus.get("line1") or "").strip(),
        (consensus.get("line2") or "").strip(),
    )


def _wait_for_lcd_line1(
    tmp_path: Path,
    *,
    name: str,
    expected: str,
    timeout_s: float = 20.0,
    poll_s: float = 0.5,
) -> tuple[str, str]:
    import time

    deadline = time.monotonic() + timeout_s
    last = ("", "")
    index = 0
    while True:
        line1, line2 = _capture_lcd_consensus(tmp_path, f"{name}_{index:02d}")
        last = (line1, line2)
        if line1 == expected:
            return last
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"timed out waiting for LCD line1 {expected!r}; last={last!r}"
            )
        index += 1
        time.sleep(max(0.0, poll_s))


def _wait_for_lcd_line1_match(
    tmp_path: Path,
    *,
    name: str,
    description: str,
    predicate,
    timeout_s: float = 20.0,
    poll_s: float = 0.5,
) -> tuple[str, str]:
    import time

    deadline = time.monotonic() + timeout_s
    last = ("", "")
    index = 0
    while True:
        line1, line2 = _capture_lcd_consensus(tmp_path, f"{name}_{index:02d}")
        last = (line1, line2)
        if predicate(line1):
            return last
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"timed out waiting for LCD line1 {description}; last={last!r}"
            )
        index += 1
        time.sleep(max(0.0, poll_s))


def _assert_lcd_starts_on_diag_page(
    tmp_path: Path,
    *,
    expected_page: str,
    name: str,
) -> tuple[str, str]:
    line1, line2 = _capture_lcd_consensus(tmp_path, name)
    assert line1.startswith(expected_page), (
        f"CONTROL must start this gate on {expected_page} Diag; got "
        f"{line1!r} / {line2!r}"
    )
    return line1, line2


@pytest.mark.hardware
def test_live_v32_release_identity_and_ab_filename_ram() -> None:
    """Opt-in MAIN-only hardware confirmation for BUG-REV-01 and
    BUG-PRESET-01.

    This test intentionally uses only MAIN USB HID/EP0 access, so it
    can be run with one MAIN connected at a time after the release-flash
    ceremony.  It verifies the runtime V3.2 identity and that both A/B
    active filename RAM readbacks match the baked release captures.
    """
    if os.environ.get("DLCP_HW_RELEASE_IDENTITY_CONFIRM") != "1":
        pytest.skip(
            "set DLCP_HW_RELEASE_IDENTITY_CONFIRM=1 after flashing V3.2 "
            "to opt in to MAIN identity/A-B filename confirmation; this "
            "test switches the visible MAIN(s) A->B->A via EP0 and restores "
            "the starting preset"
        )

    from dlcp_fw.flash import dlcp_main_flash as main_flash
    from dlcp_fw.flash import dlcp_v32_release_flash
    from dlcp_fw.paths import V32_MAIN_HEX

    hex_mem = main_flash.parse_intel_hex(str(V32_MAIN_HEX))
    expected_hid = main_flash.detect_static_hex_hid_version(hex_mem)
    expected_eeprom = main_flash.detect_static_hex_eeprom_version(hex_mem)
    assert expected_hid is not None, f"missing HID V3.2 identity in {V32_MAIN_HEX}"
    assert expected_eeprom is not None, f"missing EEPROM V3.2 identity in {V32_MAIN_HEX}"

    expected_names = {
        "A": _release_capture_name(dlcp_v32_release_flash.CAPTURE_A_META),
        "B": _release_capture_name(dlcp_v32_release_flash.CAPTURE_B_META),
    }

    devices = [
        dev
        for dev in main_flash.enumerate_devices(hw.DEFAULT_VID, hw.DEFAULT_PID)
        if dev.path is not None
    ]
    assert devices, "no MAIN HID devices visible"

    tested_paths: list[str] = []
    failures: list[str] = []
    for dev in devices:
        assert dev.path is not None
        path_text = dev.path.decode("utf-8", errors="replace")
        snapshot = main_flash._probe_device_snapshot(
            info=dev,
            vid=hw.DEFAULT_VID,
            pid=hw.DEFAULT_PID,
        )
        if snapshot.mode != "app":
            continue

        role = hw._classify_role_from_snapshot(snapshot)
        if role not in {"LEFT", "RIGHT"}:
            failures.append(
                f"{path_text}: expected all-L or all-R channel mapping after "
                f"release flash, got role={role} routes={snapshot.active_routes!r}"
            )
            continue

        initial_preset = main_flash._probe_active_preset_ep0(
            vid=hw.DEFAULT_VID,
            pid=hw.DEFAULT_PID,
            path=dev.path,
        )
        if initial_preset not in expected_names:
            failures.append(f"{path_text}: unknown initial preset {initial_preset!r}")
            continue

        try:
            if snapshot.version != expected_hid:
                failures.append(
                    f"{path_text}: HID identity {snapshot.version!r} != "
                    f"release {expected_hid!r}"
                )
            if snapshot.eeprom_version != expected_eeprom:
                failures.append(
                    f"{path_text}: EEPROM identity {snapshot.eeprom_version!r} != "
                    f"release {expected_eeprom!r}"
                )

            initial_name = _active_filename_via_cmd03(dev.path)
            if initial_name != expected_names[initial_preset]:
                failures.append(
                    f"{path_text}: initial preset {initial_preset} filename "
                    f"{initial_name!r} != {expected_names[initial_preset]!r}"
                )

            for preset in ("A", "B", "A"):
                main_flash._switch_active_preset_ep0(
                    vid=hw.DEFAULT_VID,
                    pid=hw.DEFAULT_PID,
                    path=dev.path,
                    preset=preset,
                    timeout_s=5.0,
                    settle_s=0.35,
                    stable_reads=3,
                )
                active_name = _active_filename_via_cmd03(dev.path)
                if active_name != expected_names[preset]:
                    failures.append(
                        f"{path_text}: after EP0 switch to preset {preset}, "
                        f"cmd03 filename {active_name!r} != {expected_names[preset]!r}"
                    )

                refreshed = main_flash._probe_device_snapshot(
                    info=main_flash._pick_device(hw.DEFAULT_VID, hw.DEFAULT_PID, dev.path),
                    vid=hw.DEFAULT_VID,
                    pid=hw.DEFAULT_PID,
                )
                if refreshed.active_config_name != expected_names[preset]:
                    failures.append(
                        f"{path_text}: after EP0 switch to preset {preset}, "
                        f"EP0 filename RAM {refreshed.active_config_name!r} != "
                        f"{expected_names[preset]!r}"
                    )
        finally:
            main_flash._switch_active_preset_ep0(
                vid=hw.DEFAULT_VID,
                pid=hw.DEFAULT_PID,
                path=dev.path,
                preset=initial_preset,
                timeout_s=5.0,
                settle_s=0.35,
                stable_reads=3,
            )

        tested_paths.append(path_text)

    assert not failures, "\n".join(failures)
    assert tested_paths, (
        "no running MAIN app devices were testable; visible devices were "
        f"{[dev.product_string for dev in devices]!r}"
    )


@pytest.mark.hardware
def test_live_v32_release_flash_preserves_expected_user_settings() -> None:
    """Opt-in hardware confirmation for BUG-SETTINGS-01.

    Run this after a release-flash ceremony with expected values captured
    before flashing.  The gate accepts one or both MAINs because the setting
    reset bug is MAIN-local.
    """
    if os.environ.get("DLCP_HW_RELEASE_SETTINGS_CONFIRM") != "1":
        pytest.skip(
            "set DLCP_HW_RELEASE_SETTINGS_CONFIRM=1 after flashing V3.2 and "
            "provide DLCP_HW_EXPECTED_VOLUME_LOW, DLCP_HW_EXPECTED_INPUT, "
            "and DLCP_HW_EXPECTED_SETUP_PROFILE from before flash"
        )
    volume_text = os.environ.get("DLCP_HW_EXPECTED_VOLUME_LOW")
    input_text = os.environ.get("DLCP_HW_EXPECTED_INPUT")
    profile_text = os.environ.get("DLCP_HW_EXPECTED_SETUP_PROFILE")
    if not volume_text or not input_text or not profile_text:
        pytest.fail(
            "set DLCP_HW_EXPECTED_VOLUME_LOW, DLCP_HW_EXPECTED_INPUT, and "
            "DLCP_HW_EXPECTED_SETUP_PROFILE to the pre-flash values, e.g. "
            "0xE2, 0x03, and 0x04"
        )
    expected_volume_low = _parse_byte_auto(
        volume_text, name="DLCP_HW_EXPECTED_VOLUME_LOW"
    )
    expected_input = _parse_byte_auto(input_text, name="DLCP_HW_EXPECTED_INPUT")
    expected_profile = _parse_byte_auto(
        profile_text, name="DLCP_HW_EXPECTED_SETUP_PROFILE"
    )

    settings = _running_main_user_settings()
    assert settings, "no running MAIN app devices with readable volume/input state"

    failures: list[str] = []
    for path, item in settings.items():
        if item["logical_low"] != expected_volume_low:
            failures.append(
                f"{path}: logical volume low=0x{item['logical_low']:02X}, "
                f"expected 0x{expected_volume_low:02X}"
            )
        if item["computed_low"] != expected_volume_low:
            failures.append(
                f"{path}: computed volume low=0x{item['computed_low']:02X}, "
                f"expected 0x{expected_volume_low:02X}"
            )
        if item["input_select"] != expected_input:
            failures.append(
                f"{path}: input_select=0x{item['input_select']:02X}, "
                f"expected 0x{expected_input:02X}"
            )
        if item["input_mirror"] != expected_input:
            failures.append(
                f"{path}: input_select_mirror=0x{item['input_mirror']:02X}, "
                f"expected 0x{expected_input:02X}"
            )
        if item["setup_profile"] != expected_profile:
            failures.append(
                f"{path}: setup/profile byte ram_0x0B8=0x{item['setup_profile']:02X}, "
                f"expected 0x{expected_profile:02X}"
            )

    assert not failures, "\n".join(failures)


@pytest.mark.hardware
def test_live_manual_front_panel_preset_selection_updates_mains_and_filename_ram(
    tmp_path: Path,
) -> None:
    """Opt-in manual front-panel confirmation for BUG-PRESET-01/02.

    Operator workflow:
      1. From CONTROL's Preset screen, select the target preset using
         the physical front-panel UP/DOWN controls.
      2. Wait for the UI to settle on ``Volume`` or ``Preset`` with
         row 2 ``Active: <target>``.
      3. Run this test with DLCP_HW_EXPECTED_PRESET=A or B.

    This intentionally covers the original user-reported path: physical
    CONTROL preset selection, not EP0 switching and not IR F1/F2.
    """
    if os.environ.get("DLCP_HW_FRONT_PANEL_PRESET_CONFIRM") != "1":
        pytest.skip(
            "set DLCP_HW_FRONT_PANEL_PRESET_CONFIRM=1 after manually "
            "selecting A/B from CONTROL's physical Preset screen"
        )
    target = os.environ.get("DLCP_HW_EXPECTED_PRESET", "").strip().upper()
    if target not in {"A", "B"}:
        pytest.fail(
            "set DLCP_HW_EXPECTED_PRESET=A or B to the preset the operator "
            "selected on the physical CONTROL front panel"
        )

    _require_main_pair_and_camera_accessible()

    from dlcp_fw.flash import dlcp_v32_release_flash

    expected_names = {
        "A": _release_capture_name(dlcp_v32_release_flash.CAPTURE_A_META),
        "B": _release_capture_name(dlcp_v32_release_flash.CAPTURE_B_META),
    }

    line1, line2 = _capture_lcd_consensus(tmp_path, f"front_panel_preset_{target}")
    assert line1 in {"Volume", "Preset"}, (
        f"CONTROL should be on Volume or Preset after manual front-panel "
        f"selection; got {line1!r} / {line2!r}"
    )
    assert line2 == f"Active: {target}", (
        f"CONTROL LCD did not show target preset after physical front-panel "
        f"selection; expected row 2 Active: {target!s}, got "
        f"{line1!r} / {line2!r}"
    )

    left, right = hw._read_pair_state(vid=hw.DEFAULT_VID, pid=hw.DEFAULT_PID)
    failures: list[str] = []
    for item in (left, right):
        if item.active_preset != target:
            failures.append(
                f"{item.role} MAIN active_preset={item.active_preset!r}, "
                f"expected {target!r} (path={item.path})"
            )
        if item.active_config_name != expected_names[target]:
            failures.append(
                f"{item.role} MAIN active_config_name={item.active_config_name!r}, "
                f"expected {expected_names[target]!r} for preset {target} "
                f"(path={item.path})"
            )

    assert not failures, "\n".join(failures)


@pytest.mark.hardware
def test_live_manual_front_panel_standby_wake_from_volume(tmp_path: Path) -> None:
    """Opt-in manual front-panel confirmation for BUG-STDBY-01.

    Operator workflow:
      1. Start with CONTROL on the Volume screen.
      2. Run this test with DLCP_HW_FRONT_PANEL_STBY_WAKE_CONFIRM=1.
      3. Press physical STBY within the standby window.
      4. After the test observes standby evidence, press physical STBY again
         within the wake window.

    The test intentionally uses the real front-panel button path. It does not
    use Flipper IR, and it does not synthesize button GPIOs.
    """
    if os.environ.get("DLCP_HW_FRONT_PANEL_STBY_WAKE_CONFIRM") != "1":
        pytest.skip(
            "set DLCP_HW_FRONT_PANEL_STBY_WAKE_CONFIRM=1 and be ready to "
            "press physical STBY, then physical STBY again for wake"
        )

    _require_main_pair_and_camera_accessible()

    expected_preset = _current_pair_preset()
    line1, line2 = _wait_for_lcd_line1(
        tmp_path,
        name="manual_stby_wake_precondition",
        expected="Volume",
        timeout_s=float(os.environ.get("DLCP_HW_LCD_TIMEOUT_S", "25")),
        poll_s=float(os.environ.get("DLCP_HW_LCD_POLL_S", "0.5")),
    )
    assert line2 == f"Active: {expected_preset}", (
        f"manual front-panel STBY/WAKE should start from coherent Volume "
        f"state; got {line1!r} / {line2!r}, expected Active: {expected_preset}"
    )

    print(
        "ACTION REQUIRED: press physical STBY now; waiting for MAIN standby "
        "evidence and Zzz LCD",
        flush=True,
    )
    standby_evidence = _wait_for_standby_evidence(
        timeout_s=float(os.environ.get("DLCP_HW_MANUAL_STBY_WINDOW_S", "20")),
        poll_s=float(os.environ.get("DLCP_HW_MAIN_POLL_S", "0.1")),
        stable_polls=int(os.environ.get("DLCP_HW_STANDBY_STABLE_POLLS", "2")),
    )
    assert standby_evidence["mode"] in {
        "both_mains_inactive",
        "no_visible_mains",
        "main_probe_error",
    }
    line1, line2 = _wait_for_lcd_line1(
        tmp_path,
        name="manual_stby_wake_standby_lcd",
        expected="Zzz...",
        timeout_s=float(os.environ.get("DLCP_HW_LCD_TIMEOUT_S", "25")),
        poll_s=float(os.environ.get("DLCP_HW_LCD_POLL_S", "0.5")),
    )
    assert line1 == "Zzz...", (
        f"manual front-panel STBY must show Zzz LCD before wake prompt; "
        f"got {line1!r} / {line2!r}"
    )

    import time

    time.sleep(float(os.environ.get("DLCP_HW_STBY_DWELL_S", "1.0")))
    print(
        "ACTION REQUIRED: press physical STBY again now to wake; waiting for "
        "both MAINs and Volume LCD",
        flush=True,
    )

    hw._wait_for_main_pair_state(
        vid=hw.DEFAULT_VID,
        pid=hw.DEFAULT_PID,
        timeout_s=float(os.environ.get("DLCP_HW_MANUAL_WAKE_WINDOW_S", "25")),
        poll_interval_s=float(os.environ.get("DLCP_HW_MAIN_POLL_S", "0.1")),
        expected_preset=expected_preset,
        muted=False,
        active=True,
    )

    line1, line2 = _wait_for_lcd_line1(
        tmp_path,
        name="manual_stby_wake_after_wake",
        expected="Volume",
        timeout_s=float(os.environ.get("DLCP_HW_LCD_TIMEOUT_S", "25")),
        poll_s=float(os.environ.get("DLCP_HW_LCD_POLL_S", "0.5")),
    )
    assert line2 == f"Active: {expected_preset}", (
        f"manual front-panel wake returned to Volume but unexpected row 2: "
        f"{line1!r} / {line2!r}; expected Active: {expected_preset}"
    )


@pytest.mark.hardware
def test_live_preset_convergence_reaches_requested_target() -> None:
    _require_live_rig_accessible()
    current = _current_pair_preset()
    action = "F2" if current == "A" else "F1"

    rc = hw.main(
        _common_cli_args()
        + [
            "preset-convergence",
            "--action",
            action,
            "--timeout-s",
            "15",
            "--lcd-timeout-s",
            "25",
        ]
    )

    assert rc == 0


@pytest.mark.hardware
def test_live_rapid_toggle_convergence_reaches_final_target() -> None:
    _require_live_rig_accessible()
    current = _current_pair_preset()
    sequence = "F2,F1,F2" if current == "A" else "F1,F2,F1"

    rc = hw.main(
        _common_cli_args()
        + [
            "rapid-toggle-convergence",
            "--sequence",
            sequence,
            "--inter-press-ms",
            os.environ.get("DLCP_HW_INTER_PRESS_MS", "250"),
            "--timeout-s",
            "15",
            "--lcd-timeout-s",
            "25",
        ]
    )

    assert rc == 0


@pytest.mark.hardware
def test_live_preset_mute_timing_sweep_passes_for_configured_delays() -> None:
    _require_live_rig_accessible()
    rc = hw.main(
        _common_cli_args()
        + [
            "preset-mute-timing-sweep",
            "--delays-ms",
            os.environ.get("DLCP_HW_MUTE_SWEEP_DELAYS_MS", "50,100,250,500,1000"),
            "--timeout-s",
            _env_float("DLCP_HW_TIMEOUT_S", 15.0),
            "--lcd-timeout-s",
            _env_float("DLCP_HW_LCD_TIMEOUT_S", 25.0),
        ]
    )

    assert rc == 0


@pytest.mark.hardware
def test_live_preset_standby_wake_timing_sweep_passes_for_configured_delays() -> None:
    _require_live_rig_accessible()
    argv = _common_cli_args() + [
        "preset-standby-wake-timing-sweep",
        "--delays-ms",
        os.environ.get("DLCP_HW_STBY_SWEEP_DELAYS_MS", "50,100,250,500,1000"),
        "--standby-dwell-s",
        _env_float("DLCP_HW_STBY_DWELL_S", 1.0),
        "--timeout-s",
        _env_float("DLCP_HW_TIMEOUT_S", 15.0),
        "--lcd-timeout-s",
        _env_float("DLCP_HW_LCD_TIMEOUT_S", 25.0),
    ]
    if os.environ.get("DLCP_HW_REQUIRE_STANDBY_LCD_ZZZ") == "1":
        argv.append("--no-standby-blank-fallback")

    rc = hw.main(
        argv
    )

    assert rc == 0


@pytest.mark.hardware
def test_live_reconnect_responsiveness_soak_passes_for_configured_iterations() -> None:
    _require_live_rig_accessible()
    rc = hw.main(
        _common_cli_args()
        + [
            "reconnect-responsiveness-soak",
            "--iterations",
            _env_int("DLCP_HW_SOAK_ITERATIONS", 5),
            "--standby-dwell-s",
            _env_float("DLCP_HW_STBY_DWELL_S", 1.0),
            "--timeout-s",
            _env_float("DLCP_HW_TIMEOUT_S", 15.0),
            "--lcd-timeout-s",
            _env_float("DLCP_HW_LCD_TIMEOUT_S", 25.0),
        ]
    )

    assert rc == 0


@pytest.mark.hardware
def test_live_ir_receiver_profile_sweep_records_any_state_change() -> None:
    """Opt-in BUG-IR-01 diagnostic when the full real-IR stress cannot pass.

    This avoids LCD OCR and sends a small action matrix through the same
    Flipper path, then records MAIN-visible deltas.  It is meant to answer
    whether any Hypex or standard RC5 command reaches CONTROL at all before
    spending time on cross-version V1.6b/V1.71 stress.
    """
    if os.environ.get("DLCP_HW_IR_RECEIVER_SWEEP") != "1":
        pytest.skip(
            "set DLCP_HW_IR_RECEIVER_SWEEP=1 to run the real-IR receiver "
            "profile sweep diagnostic"
        )
    _require_main_pair_and_flipper_accessible()
    rc = hw.main(
        _common_cli_args()
        + [
            "ir-receiver-sweep",
            "--actions",
            os.environ.get(
                "DLCP_HW_IR_SWEEP_ACTIONS",
                "VOL_UP,VOL_DOWN,STD_VOL_UP,STD_VOL_DOWN,F2,F1,MUTE,MUTE,STD_MUTE,STD_MUTE",
            ),
            "--settle-s",
            _env_float("DLCP_HW_IR_SWEEP_SETTLE_S", 1.0),
            "--require-any-change",
        ]
    )

    assert rc == 0


@pytest.mark.hardware
def test_live_ir_legacy_command_stress_from_volume(tmp_path: Path) -> None:
    """Opt-in real-IR stress gate for BUG-IR-01.

    This intentionally uses legacy CONTROL commands that should work on both
    stock V1.6b and V1.71: volume up/down, mute toggle, and POWER
    standby/wake toggle.  Run it once on stock V1.6b CONTROL to establish the
    baseline and again with V1.71 CONTROL; both runs must pass.
    """
    if os.environ.get("DLCP_HW_IR_LEGACY_STRESS") != "1":
        pytest.skip(
            "set DLCP_HW_IR_LEGACY_STRESS=1 to run the destructive real-IR "
            "legacy command stress gate; run once on V1.6b and once on V1.71"
        )
    expected_control = os.environ.get("DLCP_HW_EXPECTED_CONTROL_VERSION", "").strip()
    if expected_control not in {"V1.6b", "V1.71"}:
        pytest.fail(
            "set DLCP_HW_EXPECTED_CONTROL_VERSION=V1.6b or V1.71 so the "
            "legacy real-IR evidence is tied to the CONTROL firmware under test"
        )
    expected_control_hex = _expected_control_hex_identity(expected_control)
    _require_live_rig_accessible()

    import time

    output_root = Path(
        os.environ.get(
            "DLCP_HW_OUTPUT_ROOT",
            str(hw.DEFAULT_OUTPUT_ROOT / "pytest"),
        )
    )
    run_root = output_root / "legacy_ir_stress" / time.strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)
    result_path = run_root / "result.json"

    current_preset = _current_pair_preset()
    line1, line2 = _capture_lcd_consensus(tmp_path, "ir_legacy_start")
    assert line1 == "Volume", (
        f"CONTROL {expected_control} must start this test on Volume; "
        f"got {line1!r} / {line2!r}"
    )

    ir_template = hw._default_flipper_ir_command_template(
        port=os.environ.get("DLCP_HW_FLIPPER_PORT")
    )
    ir_profile = os.environ.get("DLCP_HW_IR_PROFILE", "HYPEX")
    timeout_s = float(os.environ.get("DLCP_HW_TIMEOUT_S", "15"))
    poll_s = float(os.environ.get("DLCP_HW_MAIN_POLL_S", "0.1"))
    repeats = max(1, int(os.environ.get("DLCP_HW_IR_STRESS_REPEATS", "3")))
    ir_results: list[dict[str, object]] = []
    last_before_volume: dict[str, int] | None = None
    last_after_volume: dict[str, int] | None = None

    def send_legacy_ir(action: str) -> dict[str, object]:
        actual = _legacy_ir_action(action, profile=ir_profile)
        result = hw._send_ir(ir_template, action=actual)
        result = {
            **result,
            "logical_action": action,
            "actual_action": actual,
            "ir_profile": ir_profile,
        }
        ir_results.append(result)
        return result

    def write_result(status: str, error: BaseException | None = None) -> None:
        try:
            final_volume = _running_main_logical_volume_lows()
        except Exception as exc:  # pragma: no cover - hardware diagnostic path
            final_volume = {"collect_error": str(exc)}  # type: ignore[assignment]
        payload: dict[str, object] = {
            "status": status,
            "scenario": "legacy_ir_stress",
            "run_root": str(run_root),
            "expected_control": expected_control,
            "expected_control_hex": expected_control_hex,
            "ir_profile": ir_profile,
            "current_preset": current_preset,
            "start_lcd": {"line1": line1, "line2": line2},
            "ir_command_template": ir_template,
            "ir_results": ir_results,
            "last_before_volume": last_before_volume,
            "last_after_volume": last_after_volume,
            "final_volume": final_volume,
        }
        if error is not None:
            payload["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        result_path.write_text(hw._json_dumps(payload), encoding="utf-8")

    try:
        left, right = hw._read_pair_state(vid=hw.DEFAULT_VID, pid=hw.DEFAULT_PID)
        if hw._is_muted_state(left) or hw._is_muted_state(right):
            send_legacy_ir("MUTE")
            hw._wait_for_main_pair_state(
                vid=hw.DEFAULT_VID,
                pid=hw.DEFAULT_PID,
                timeout_s=timeout_s,
                poll_interval_s=poll_s,
                expected_preset=current_preset,
                muted=False,
                active=True,
            )

        for repeat in range(repeats):
            last_before_volume = _running_main_logical_volume_lows()
            assert last_before_volume, "could not read MAIN logical volume before legacy IR stress"
            volume_action, volume_restore = _volume_action_and_restore(last_before_volume)
            send_legacy_ir(volume_action)
            last_after_volume = _wait_for_volume_change(
                last_before_volume,
                timeout_s=timeout_s,
                poll_s=poll_s,
            )
            send_legacy_ir(volume_restore)
            _wait_for_volume_change(last_after_volume, timeout_s=timeout_s, poll_s=poll_s)

            send_legacy_ir("MUTE")
            hw._wait_for_main_pair_state(
                vid=hw.DEFAULT_VID,
                pid=hw.DEFAULT_PID,
                timeout_s=timeout_s,
                poll_interval_s=poll_s,
                expected_preset=current_preset,
                muted=True,
                active=True,
            )
            send_legacy_ir("MUTE")
            hw._wait_for_main_pair_state(
                vid=hw.DEFAULT_VID,
                pid=hw.DEFAULT_PID,
                timeout_s=timeout_s,
                poll_interval_s=poll_s,
                expected_preset=current_preset,
                muted=False,
                active=True,
            )

            send_legacy_ir("POWER")
            _wait_for_standby_evidence(
                timeout_s=timeout_s,
                poll_s=poll_s,
                stable_polls=int(os.environ.get("DLCP_HW_STANDBY_STABLE_POLLS", "2")),
            )
            time.sleep(float(os.environ.get("DLCP_HW_STBY_DWELL_S", "1.0")))
            send_legacy_ir("POWER")
            hw._wait_for_main_pair_state(
                vid=hw.DEFAULT_VID,
                pid=hw.DEFAULT_PID,
                timeout_s=timeout_s,
                poll_interval_s=poll_s,
                expected_preset=current_preset,
                muted=False,
                active=True,
            )
            line1, line2 = _wait_for_lcd_line1(
                tmp_path,
                name=f"ir_legacy_after_power_{repeat}",
                expected="Volume",
                timeout_s=float(os.environ.get("DLCP_HW_LCD_TIMEOUT_S", "25")),
                poll_s=float(os.environ.get("DLCP_HW_LCD_POLL_S", "0.5")),
            )
            assert line2 == f"Active: {current_preset}", (
                f"POWER wake returned to Volume with unexpected row 2: "
                f"{line1!r} / {line2!r}; expected Active: {current_preset}"
            )
    except Exception as exc:
        write_result("FAIL", exc)
        raise

    write_result("PASS")


# ---------------------------------------------------------------------------
# Layer 5 Diagnostics page (V1.71 + V3.2)
#
# Menu navigation to Diagnostics is driven by the CONTROL's PHYSICAL
# RIGHT/LEFT buttons (the IR vocabulary in hardware_flipper_ir.py
# intentionally does not include menu-navigation actions).  This test
# therefore requires the operator to manually navigate before running:
#
#   1. From Volume, press the RIGHT physical button on CONTROL FOUR
#      times to walk Volume(0) → Preset(1) → Input(2) → Setup(3) →
#      PB1Diag(4).  V1.71 Tier-1 menu ring is documented at
#      `dlcp_control_v171.asm:4805+` -- 6 states with PB1 Diag at
#      state 4 (a separate page from PB2 Diag at state 5).
#   2. Set DLCP_HW_LAYER5_AT_DIAG=1 in the environment
#   3. Run this test
#
# See docs/HARDWARE_TEST.md §"Diagnostics page" for the full operator
# walk-through.  Post BUG-DIAG-01/02 firmware must update the PB rows
# from a static wait; LEFT/RIGHT cycling is no longer an accepted
# workaround for persistent `PBn` / `n/a`.
# ---------------------------------------------------------------------------


@pytest.mark.hardware
def test_live_diagnostics_page_renders_pb1_layout(tmp_path: Path) -> None:
    """Layer 5 live-rig validation: confirm CONTROL's PB1 Diag page
    (V1.71 Tier-1 menu state 4) renders the spec'd ``PB1`` /
    ``n/a|OK|PB1:...`` layout when the operator has navigated to it.

    This validates that V1.71 CONTROL's Tier-1 per-PB Diag layout
    renders correctly on real silicon: row 0 begins with the literal
    ``PB1`` prefix per `dlcp_control_v171.asm:3603+`, regardless of
    whether the BF/2N reply burst has converged the cache yet.  This
    test checks layout rendering only (the `PB1` prefix), not counter
    convergence.  Strict convergence is covered by the opt-in PB1/PB2
    data gates below.  This test fails only if
    V1.71 Tier-1 layout rendering is broken or the operator did
    not navigate to state 4.

    Pre-2026-05-04 (and pre-Tier-1) versions of this test asserted
    ``line1.startswith("1:")`` / ``line2.startswith("2:")`` against
    the legacy Diagnostics(2) layout.  V1.71 Tier-1 (state 4 PB1 +
    state 5 PB2 split-page model per
    `dlcp_control_v171.asm:3484+,4805+`) replaced that two-row
    single-page layout, so the legacy assertions have been removed.
    Task #94 (briefly framed as a rust-specific Timer3/Timer1
    fidelity bug) closed 2026-05-04 -- rust matches HW.
    """
    if os.environ.get("DLCP_HW_LAYER5_AT_DIAG") != "1":
        pytest.skip(
            "set DLCP_HW_LAYER5_AT_DIAG=1 once operator has manually "
            "navigated CONTROL to PB1 Diag (V1.71 Tier-1 state 4) via "
            "FOUR physical RIGHT button presses from Volume; see "
            "docs/HARDWARE_TEST.md §Diagnostics page for the full "
            "walk-through"
        )
    _require_live_rig_accessible()

    import json
    from dlcp_fw.cli import hardware_lcd_probe

    captures = int(os.environ.get("DLCP_HW_LAYER5_LCD_CAPTURES", "10"))
    output_root = tmp_path / "layer5_lcd"
    argv: list[str] = [
        "--captures", str(captures),
        "--output-root", str(output_root),
    ]
    selector = os.environ.get("DLCP_HW_CAMERA_SELECTOR")
    if selector:
        argv.extend(["--camera-selector", selector])
    address = os.environ.get("DLCP_HW_CAMERA_ADDRESS")
    if address:
        argv.extend(["--address", address])
    if os.environ.get("DLCP_HW_SKIP_CONFIGURE") == "1":
        argv.append("--skip-configure")

    rc = hardware_lcd_probe.main(argv)
    assert rc == 0, "lcd-probe wrapper failed (camera or OCR)"

    runs_dir = output_root / "runs"
    summaries = sorted(runs_dir.glob("*/summary.json"))
    assert summaries, f"no LCD summary written under {runs_dir}"
    summary = json.loads(summaries[-1].read_text(encoding="utf-8"))
    line1 = (summary.get("consensus", {}).get("line1") or "").strip()

    # Pass criterion: row 0 starts with "PB1" per V1.71 Tier-1 layout
    # (`dlcp_control_v171.asm:3603+` writes 'P','B','1' at row 0
    # cols 0..2).  Counter content (or `n/a`/`OK`) varies with
    # convergence state and is not asserted here.
    assert line1.startswith("PB1"), (
        f"line1 must start with 'PB1' on the PB1 Diag page; got "
        f"{line1!r}.  Either the operator did not navigate to PB1 Diag "
        f"(state 4 -- press RIGHT FOUR times from Volume) before "
        f"setting DLCP_HW_LAYER5_AT_DIAG=1, or V1.71 CONTROL is not "
        f"flashed correctly."
    )


# ---------------------------------------------------------------------------
# Path 1 strict gates: does PB1 / PB2 reply convergence land on real silicon?
#
# Post BUG-DIAG-01/02, Diagnostics pages are expected to update from a
# static wait.  The old LEFT/RIGHT-cycling workaround is no longer a pass
# criterion: after the operator navigates to PB1 or PB2 Diag and waits a
# couple of seconds, each present MAIN must render either `OK` or concrete
# counter cells.  Persistent `PBn` / `n/a` is a real failure unless that PB is
# physically absent.
#
# The two gates below are live-rig sanity checks that the operator-navigated
# PB Diag page (state 4 = PB1, state 5 = PB2) converges to a layout proving
# the corresponding PB has replied:
#   * Degraded / Overflow (`PBn:` colon at row 0 col 3) -> PASS,
#     PB has non-zero counter activity.
#   * Healthy short (row 0 = "PBn", row 1 = "OK") -> PASS, PB
#     replied with all-zero counters.
#   * Absent short (row 0 = "PBn", row 1 = "n/a") -> FAIL after the
#     static wait, unless that PB is genuinely absent.
#
# Operator runs BOTH gates -- one after navigating to the PB1 Diag
# page and waiting about 1 second, then one after navigating to
# the PB2 Diag page and waiting about 1 second -- to fill in the
# full PB1 x PB2 decision matrix:
#
#   PB1 PASS, PB2 PASS  -> Both reply paths work on hardware as
#                          expected under static diagnostics cadence.
#                          No firmware bug.
#   PB1 PASS, PB2 FAIL  -> Persistent asymmetric `n/a`: V1.71
#                          parser-target bug, V3.2 PB2 reply-path bug,
#                          or real PB2 absence/wiring issue.
#                          Investigate at the firmware level.
#   PB1 FAIL, PB2 PASS  -> Inverted from the typical PB1-first
#                          convergence ordering -- very unexpected.
#                          Hardware/wiring issue most likely;
#                          investigate the rig before drawing
#                          conclusions.
#   PB1 FAIL, PB2 FAIL  -> Whole chain broken; rerun pre-flight
#                          (`scripts/dlcp_diag.py --list`) and
#                          retry.  Likely bad flash or rig wiring.
#
# Both gates share the same body via `_assert_pb_diag_page_converged`
# below.  Each is OPT-IN behind `DLCP_HW_LAYER5_REQUIRE_PB{1,2}_DATA=1`
# so the routine hardware suite stays green unless an operator has placed
# CONTROL on the requested Diagnostics page and waited for the static cadence.
# ---------------------------------------------------------------------------


def _assert_pb_diag_page_converged(
    pb_num: int, opt_in_env_var: str, tmp_path: Path
) -> None:
    """Shared body for the strict PB1 / PB2 reply-convergence gates.

    Captures the LCD via `hardware_lcd_probe` and asserts the
    operator-navigated page is in one of the documented PASS layouts
    (Degraded/Overflow with cell entries, or Healthy short with
    `OK`).  Routes the Absent (`n/a`) layout to a FAIL pointing at
    the PB1 x PB2 decision matrix in the section header above
    (each PB's failure cannot be acted on in isolation -- the
    actions depend on the OTHER PB's result, so per-message
    action items would mislead).

    `pb_num` selects the page to validate (1 or 2).  The literal
    page-title prefix is `"PB1"` or `"PB2"` per the V1.71 Tier-1
    layout (`dlcp_control_v171.asm:3603+` writes `'P', 'B', '1'/'2'`
    at row 0 cols 0..2).
    """
    if pb_num not in (1, 2):
        raise ValueError(f"pb_num must be 1 or 2, got {pb_num!r}")
    pb_label = f"PB{pb_num}"
    pb_state = 4 if pb_num == 1 else 5
    nav_presses = 4 if pb_num == 1 else 5

    if os.environ.get("DLCP_HW_LAYER5_AT_DIAG") != "1":
        pytest.skip(
            f"set DLCP_HW_LAYER5_AT_DIAG=1 once operator has manually "
            f"navigated CONTROL to the {pb_label} Diag page (state "
            f"{pb_state}) and waited about 1 second; see "
            f"docs/HARDWARE_TEST.md §Diagnostics page for the full "
            f"walk-through ({nav_presses} RIGHT presses from the "
            f"Volume screen)"
        )
    if os.environ.get(opt_in_env_var) != "1":
        pytest.skip(
            f"this test is opt-in (set {opt_in_env_var}=1).  Path 1 "
            f"strict gate for BUG-DIAG-01/02 -- only run after the "
            f"operator has navigated to the {pb_label} Diag page and "
            f"waited about 1 second for the static diagnostics "
            f"cadence to update"
        )
    _require_live_rig_accessible()

    import json
    from dlcp_fw.cli import hardware_lcd_probe

    captures = int(os.environ.get("DLCP_HW_LAYER5_LCD_CAPTURES", "10"))
    output_root = tmp_path / f"layer5_lcd_{pb_label.lower()}_strict"
    argv: list[str] = [
        "--captures", str(captures),
        "--output-root", str(output_root),
    ]
    selector = os.environ.get("DLCP_HW_CAMERA_SELECTOR")
    if selector:
        argv.extend(["--camera-selector", selector])
    address = os.environ.get("DLCP_HW_CAMERA_ADDRESS")
    if address:
        argv.extend(["--address", address])
    if os.environ.get("DLCP_HW_SKIP_CONFIGURE") == "1":
        argv.append("--skip-configure")

    rc = hardware_lcd_probe.main(argv)
    assert rc == 0, "lcd-probe wrapper failed (camera or OCR)"

    runs_dir = output_root / "runs"
    summaries = sorted(runs_dir.glob("*/summary.json"))
    assert summaries, f"no LCD summary written under {runs_dir}"
    summary = json.loads(summaries[-1].read_text(encoding="utf-8"))
    line1_raw = summary.get("consensus", {}).get("line1") or ""
    line2_raw = summary.get("consensus", {}).get("line2") or ""
    line1 = line1_raw.rstrip()
    line2 = line2_raw.rstrip()

    pb_colon_prefix = f"{pb_label}:"

    # Pre-flight: confirm the operator actually navigated to the
    # right Diag page.  V1.71 Tier-1 puts the page title at row 0
    # cols 0..2 = "PBn".
    assert line1.startswith(pb_label), (
        f"line1 must start with {pb_label!r} on the {pb_label} Diag "
        f"page; got {line1!r}.  Operator must navigate CONTROL to "
        f"state {pb_state} ({pb_label} Diag) -- press RIGHT "
        f"{nav_presses} times from the Volume screen.  Anything else "
        f"means the wrong screen is captured.  V1.71 Tier-1 6-state "
        f"menu ring is documented at `dlcp_control_v171.asm:4805+`."
    )

    pb_row1 = line2

    if line1.startswith(pb_colon_prefix):
        # Degraded or Overflow layout.  Row 0 has cell entries =>
        # at least one non-zero counter or reset-cause flag for
        # this PB.  PASS.
        print(
            f"\n  {pb_label} reply CONVERGED on real silicon.\n"
            f"  line1 ({pb_label} page row 0) = {line1_raw!r}\n"
            f"  line2 ({pb_label} page row 1) = {line2_raw!r}\n"
            f"  Layout: Degraded / Overflow ({pb_colon_prefix!r} colon "
            f"at col 3 + cell entries on row 0).\n"
            f"  -> V1.71 firmware delivers {pb_label} reply convergence "
            f"with non-zero counter activity on hardware.\n"
        )
        return

    if line1 != pb_label:
        pytest.fail(
            f"\n  Row 0 starts with {pb_label!r} but is not exactly "
            f"{pb_label!r} (short layout) and not "
            f"{pb_colon_prefix!r} (degraded/overflow):\n"
            f"  line1 = {line1_raw!r}\n"
            f"  line2 = {line2_raw!r}\n"
            f"\n  V1.71 Tier-1 spec ('docs/V32_DIAG_TIER1_SPEC.md' "
            f"§'Phase 3.4 implementation notes') prescribes only\n"
            f"  these four layouts for the {pb_label} page:\n"
            f"    Absent:   row 0 = {pb_label!r}    row 1 = 'n/a'\n"
            f"    Healthy:  row 0 = {pb_label!r}    row 1 = 'OK'\n"
            f"    Degraded: row 0 = {pb_colon_prefix!r} + entries  row 1 = (entries|empty)\n"
            f"    Overflow: row 0 = {pb_colon_prefix!r} + 4 entries  row 1 = entries + '..'\n"
            f"  Anything else is most likely OCR garbage / partial render.  Disambiguate by:\n"
            f"    (a) re-capturing with more cycles via "
            f"DLCP_HW_LAYER5_LCD_CAPTURES (default 10),\n"
            f"    (b) confirming the rig is visually on the "
            f"{pb_label} Diag page (state {pb_state}).\n"
        )

    if pb_row1 == "n/a":
        pytest.fail(
            f"\n  {pb_label} row 1 is the 'n/a' (absent) layout -- "
            f"CONTROL has NEVER registered a {pb_label} reply on "
            f"real silicon.\n"
            f"  Reply chain fails at HOP E or earlier (CONTROL "
            f"parser does not dispatch BF/27 through the BF/2N\n"
            f"  last-frame path; v171_diag_present "
            f"bit {pb_num - 1} stays clear; renderer falls back to "
            f"the absent layout per\n"
            f"  `docs/V32_DIAG_TIER1_SPEC.md` §'Phase 3.4 "
            f"implementation notes').\n"
            f"  Cross-reference per-MAIN cmd 0x44 snapshots from "
            f"`scripts/dlcp_diag.py` to confirm the corresponding\n"
            f"  MAIN itself has counter data, isolating the failure "
            f"to the CONTROL parser path.\n"
            f"  See docs/SIM_REWRITE_RUST_PROGRESS.md P3.6b for "
            f"PB1/PB2 decision matrix and resulting actions.\n"
            f"\n  Captured LCD lines:\n"
            f"    line1 = {line1_raw!r}\n"
            f"    line2 = {line2_raw!r}\n"
        )

    if pb_row1 == "OK":
        print(
            f"\n  {pb_label} reply CONVERGED on real silicon.\n"
            f"  line1 ({pb_label} page row 0) = {line1_raw!r}\n"
            f"  line2 ({pb_label} page row 1) = {line2_raw!r}\n"
            f"  Layout: Healthy (all 7 runtime counters + abnormal "
            f"reset flags V/W/X are zero; the POR `O` flag may be 1 "
            f"on normal cold boot per V32_DIAG_TIER1_SPEC.md; "
            f"{pb_label} IS replying with clean state).\n"
            f"  -> V1.71 firmware delivers {pb_label} reply convergence "
            f"on hardware.\n"
        )
        return

    pytest.fail(
        f"\n  {pb_label} page is the SHORT layout (row 0 = "
        f"{pb_label!r} with no trailing colon) but row 1 is "
        f"neither 'n/a' nor 'OK':\n"
        f"  Captured LCD lines:\n"
        f"    line1 = {line1_raw!r}\n"
        f"    line2 = {line2_raw!r}\n"
        f"\n  V1.71 Tier-1 spec ('docs/V32_DIAG_TIER1_SPEC.md' "
        f"§'Phase 3.4 implementation notes') prescribes only 'n/a' "
        f"or 'OK' for row 1 of the short layout.\n"
        f"  Anything else is most likely OCR garbage / partial "
        f"render.  Disambiguate by:\n"
        f"    (a) re-capturing with more cycles via "
        f"DLCP_HW_LAYER5_LCD_CAPTURES (default 10),\n"
        f"    (b) cross-referencing per-MAIN cmd 0x44 snapshots from "
        f"`scripts/dlcp_diag.py`,\n"
        f"    (c) confirming the rig is visually on the "
        f"{pb_label} Diag page (state {pb_state}) and not "
        f"transitioning between pages.\n"
    )


@pytest.mark.hardware
def test_live_diagnostics_pb1_data_lands_on_real_silicon(tmp_path: Path) -> None:
    """Path 1 strict gate (PB1 leg) -- baseline sanity for the PB1 x
    PB2 decision matrix.

    Operator workflow:
        1. Manually navigate CONTROL from the Volume screen to the
           PB1 Diag page (state 4).  V1.71 Tier-1 6-state menu ring
           is 0=Volume, 1=Preset, 2=Input, 3=Setup, 4=PB1Diag,
           5=PB2Diag (per `dlcp_control_v171.asm:4805+`), so RIGHT
           must be pressed FOUR times from the Volume default to
           reach PB1 Diag.
        2. Wait about 1 second on the PB1 Diag page.  Post
           BUG-DIAG-01/02, static wait is the required pass condition;
           LEFT/RIGHT cycling must not be necessary to populate the
           BF/2N reply cache.
        3. Set DLCP_HW_LAYER5_AT_DIAG=1 and
           DLCP_HW_LAYER5_REQUIRE_PB1_DATA=1.
        4. Run this test.

    Then operator navigates to PB2 Diag page (one more RIGHT), waits
    about 1 second, and runs
    `test_live_diagnostics_pb2_data_lands_on_real_silicon` with
    `DLCP_HW_LAYER5_REQUIRE_PB2_DATA=1`.  Combined results fill in
    the PB1 x PB2 decision matrix in the section header above.
    """
    _assert_pb_diag_page_converged(
        pb_num=1,
        opt_in_env_var="DLCP_HW_LAYER5_REQUIRE_PB1_DATA",
        tmp_path=tmp_path,
    )


@pytest.mark.hardware
def test_live_diagnostics_pb2_data_lands_on_real_silicon(tmp_path: Path) -> None:
    """Path 1 strict gate (PB2 leg) -- live-rig confirmation that
    the PB2 reply-convergence path lands on real silicon after a
    static diagnostics wait.

    Operator workflow:
        1. Manually navigate CONTROL from the Volume screen to the
           PB2 Diag page (state 5).  V1.71 Tier-1 6-state menu ring
           is 0=Volume, 1=Preset, 2=Input, 3=Setup, 4=PB1Diag,
           5=PB2Diag (per `dlcp_control_v171.asm:4805+`), so RIGHT
           must be pressed FIVE times from the Volume default to
           reach PB2 Diag.
        2. Wait about 1 second on the PB2 Diag page.  Post
           BUG-DIAG-01/02, static wait is the required pass condition;
           LEFT/RIGHT cycling must not be necessary to populate the
           BF/2N reply cache.
        3. (Optional) Run `scripts/dlcp_diag.py` to record per-MAIN
           cmd 0x44 snapshots.
        4. Set DLCP_HW_LAYER5_AT_DIAG=1 and
           DLCP_HW_LAYER5_REQUIRE_PB2_DATA=1.
        5. Run this test.

    Operator should ALSO run the PB1 sibling
    `test_live_diagnostics_pb1_data_lands_on_real_silicon` (after
    navigating to state 4) to fill in the PB1 x PB2 decision
    matrix.  See section header comment above for the matrix and
    actions per outcome.

    V1.71 Tier-1 LCD layout reference (per
    `docs/V32_DIAG_TIER1_SPEC.md` §"Phase 3.4 implementation notes"
    and `dlcp_control_v171.asm:3484+`):

        Page = state 4 (PB1) or state 5 (PB2).  Both 16x2 LCD rows
        belong to the SAME PB.  Layout dispatch by health:

          Absent   (PB has never replied):
              row 0 = "PBn"               (+ 13 spaces)
              row 1 = "n/a"               (+ 13 spaces)
          Healthy  (7 runtime counters I/D/S/B/R/A/P + V/W/X
                    abnormal reset flags all 0; POR `O` flag may
                    be 1 on a normal cold boot and is masked out):
              row 0 = "PBn"               (+ 13 spaces)
              row 1 = "OK"                (+ 14 spaces)
          Degraded (1..9 non-zero cells):
              row 0 = "PBn:" + ` X#`*<=4 entries
              row 1 = `X#` + ` X#`*<=4 entries
          Overflow (10..11 non-zero cells):
              row 0 = "PBn:" + 4 entries (full)
              row 1 = 5 entries + ".."   overflow indicator

        Cells are letter-value pairs.  Letter = column label
        I/D/S/B/R/A/P/O/V/W/X.  Value = ' ' (counter == 0), '1'..'9',
        'A'..'E', or '+' (saturated) per
        `v171_diag_emit_nib_w` (`dlcp_control_v171.asm:4187+`).

    Why pattern-match against literal layouts (n/a, OK, cell entries)
    rather than per-char class checks?  Because static column-label
    letters (I/D/S/B/R/A/P/O/V/W/X) ARE in the cell-pair format, and
    several of them ('A', 'B', 'D') overlap with the value-letter
    set 'A'..'E' from the encoding.  A naive "is this char in
    [0-9A-E+]" check would treat the static label 'D' as a value
    char and pass the convergence gate even when every counter is
    zero -- false-positive risk codex flagged in 437a7dd review.
    """
    _assert_pb_diag_page_converged(
        pb_num=2,
        opt_in_env_var="DLCP_HW_LAYER5_REQUIRE_PB2_DATA",
        tmp_path=tmp_path,
    )


@pytest.mark.hardware
def test_live_manual_diagnostics_buttons_remain_responsive(tmp_path: Path) -> None:
    """Opt-in manual physical-button responsiveness gate for BUG-DIAG-02.

    The operator manually positions CONTROL on PB1 or PB2 Diagnostics.  The
    test then prompts for one physical RIGHT press and one physical LEFT press,
    with an explicit re-positioning prompt between them.  It proves the real
    touch-button path remains responsive while the Diagnostics cadence is
    active, instead of relying only on IR dispatch from those pages.
    """
    if os.environ.get("DLCP_HW_LAYER5_AT_DIAG") != "1":
        pytest.skip(
            "set DLCP_HW_LAYER5_AT_DIAG=1 once operator has manually "
            "navigated CONTROL to PB1 or PB2 Diag and waited at least "
            "1 second"
        )
    if os.environ.get("DLCP_HW_LAYER5_BUTTON_ACTIONS") != "1":
        pytest.skip(
            "set DLCP_HW_LAYER5_BUTTON_ACTIONS=1 to opt in; this test "
            "prompts the operator to press physical RIGHT and LEFT while "
            "CONTROL is on a Diagnostics page"
        )
    expected_page = os.environ.get("DLCP_HW_EXPECTED_DIAG_PAGE", "").strip().upper()
    if expected_page not in {"PB1", "PB2"}:
        pytest.fail(
            "set DLCP_HW_EXPECTED_DIAG_PAGE=PB1 or PB2 for the manual "
            "Diagnostics button responsiveness gate"
        )

    _require_main_pair_and_camera_accessible()
    _assert_lcd_starts_on_diag_page(
        tmp_path,
        expected_page=expected_page,
        name="diag_buttons_start",
    )

    right_target = "PB2" if expected_page == "PB1" else "Volume"
    right_predicate = (
        (lambda line1: line1.startswith("PB2"))
        if right_target == "PB2"
        else (lambda line1: line1 == right_target)
    )
    print(
        f"ACTION REQUIRED: press physical RIGHT now from {expected_page}; "
        f"waiting for LCD line1 {right_target!r}",
        flush=True,
    )
    line1, line2 = _wait_for_lcd_line1_match(
        tmp_path,
        name="diag_buttons_after_right",
        description=f"{right_target!r}",
        predicate=right_predicate,
        timeout_s=float(os.environ.get("DLCP_HW_MANUAL_BUTTON_WINDOW_S", "15")),
        poll_s=float(os.environ.get("DLCP_HW_LCD_POLL_S", "0.5")),
    )
    assert right_predicate(line1), (
        f"RIGHT from {expected_page} did not reach {right_target}; "
        f"got {line1!r} / {line2!r}"
    )

    input(
        f"ACTION REQUIRED: navigate CONTROL back to {expected_page} Diag, "
        "wait about 1 second on the page, then press Enter here. "
    )
    _assert_lcd_starts_on_diag_page(
        tmp_path,
        expected_page=expected_page,
        name="diag_buttons_repositioned",
    )

    left_target = "Setup" if expected_page == "PB1" else "PB1"
    left_predicate = (
        (lambda line1: line1.startswith("PB1"))
        if left_target == "PB1"
        else (lambda line1: line1 == left_target)
    )
    print(
        f"ACTION REQUIRED: press physical LEFT now from {expected_page}; "
        f"waiting for LCD line1 {left_target!r}",
        flush=True,
    )
    line1, line2 = _wait_for_lcd_line1_match(
        tmp_path,
        name="diag_buttons_after_left",
        description=f"{left_target!r}",
        predicate=left_predicate,
        timeout_s=float(os.environ.get("DLCP_HW_MANUAL_BUTTON_WINDOW_S", "15")),
        poll_s=float(os.environ.get("DLCP_HW_LCD_POLL_S", "0.5")),
    )
    assert left_predicate(line1), (
        f"LEFT from {expected_page} did not reach {left_target}; "
        f"got {line1!r} / {line2!r}"
    )


@pytest.mark.hardware
def test_live_diagnostics_page_ir_actions_dispatch_on_real_silicon(tmp_path: Path) -> None:
    """Opt-in live gate for BUG-DIAG-02 and BUG-IR-01/02.

    The operator manually positions CONTROL on either PB1 or PB2 Diagnostics,
    then this test sends real Flipper IR actions from that page.  It proves
    Diagnostics foreground polling does not starve decoded IR dispatch for
    volume, mute, preset, standby, or wake.

    Set DLCP_HW_EXPECTED_DIAG_PAGE=PB1 or PB2 when running this as a
    per-page gate.  Leaving it unset preserves the older "either page"
    behavior for ad-hoc checks.
    """
    if os.environ.get("DLCP_HW_LAYER5_AT_DIAG") != "1":
        pytest.skip(
            "set DLCP_HW_LAYER5_AT_DIAG=1 once operator has manually "
            "navigated CONTROL to PB1 or PB2 Diag and waited at least "
            "1 second"
        )
    if os.environ.get("DLCP_HW_LAYER5_IR_ACTIONS") != "1":
        pytest.skip(
            "set DLCP_HW_LAYER5_IR_ACTIONS=1 to opt in; this test sends "
            "real IR volume, mute, preset, standby, and wake actions while "
            "CONTROL is on a Diagnostics page"
        )
    _require_live_rig_accessible()
    _require_hypex_ir_profile_for_hypex_only_gate("Diagnostics-page IR gate")

    import time

    line1, line2 = _capture_lcd_consensus(tmp_path, "diag_ir_start")
    assert line1.startswith(("PB1", "PB2")), (
        f"CONTROL must start this test on PB1/PB2 Diag; got {line1!r} / {line2!r}"
    )
    expected_page = os.environ.get("DLCP_HW_EXPECTED_DIAG_PAGE", "").strip().upper()
    if expected_page:
        assert expected_page in {"PB1", "PB2"}, (
            "DLCP_HW_EXPECTED_DIAG_PAGE must be PB1 or PB2 when set; "
            f"got {expected_page!r}"
        )
        assert line1.startswith(expected_page), (
            f"CONTROL must start this per-page Diagnostics IR gate on "
            f"{expected_page}; got {line1!r} / {line2!r}"
        )

    ir_template = hw._default_flipper_ir_command_template(
        port=os.environ.get("DLCP_HW_FLIPPER_PORT")
    )
    current_preset = _current_pair_preset()

    left, right = hw._read_pair_state(vid=hw.DEFAULT_VID, pid=hw.DEFAULT_PID)
    if hw._is_muted_state(left) or hw._is_muted_state(right):
        hw._send_ir(ir_template, action="MUTE")
        hw._wait_for_main_pair_state(
            vid=hw.DEFAULT_VID,
            pid=hw.DEFAULT_PID,
            timeout_s=float(os.environ.get("DLCP_HW_TIMEOUT_S", "15")),
            poll_interval_s=float(os.environ.get("DLCP_HW_MAIN_POLL_S", "0.1")),
            expected_preset=current_preset,
            muted=False,
            active=True,
        )

    before_volume = _running_main_logical_volume_lows()
    assert before_volume, "could not read MAIN logical volume before diagnostics IR volume test"
    volume_action, volume_restore = _volume_action_and_restore(before_volume)
    hw._send_ir(ir_template, action=volume_action)
    after_volume = _wait_for_volume_change(before_volume)
    hw._send_ir(ir_template, action=volume_restore)
    _wait_for_volume_change(after_volume)

    line1, line2 = _capture_lcd_consensus(tmp_path, "diag_ir_after_volume")
    assert line1.startswith(("PB1", "PB2")), (
        f"IR volume should not wedge or navigate away from Diagnostics; "
        f"got {line1!r} / {line2!r}"
    )
    if expected_page:
        assert line1.startswith(expected_page), (
            f"IR volume should keep CONTROL on {expected_page}; "
            f"got {line1!r} / {line2!r}"
        )

    hw._send_ir(ir_template, action="MUTE")
    hw._wait_for_main_pair_state(
        vid=hw.DEFAULT_VID,
        pid=hw.DEFAULT_PID,
        timeout_s=float(os.environ.get("DLCP_HW_TIMEOUT_S", "15")),
        poll_interval_s=float(os.environ.get("DLCP_HW_MAIN_POLL_S", "0.1")),
        expected_preset=current_preset,
        muted=True,
        active=True,
    )
    hw._send_ir(ir_template, action="MUTE")
    hw._wait_for_main_pair_state(
        vid=hw.DEFAULT_VID,
        pid=hw.DEFAULT_PID,
        timeout_s=float(os.environ.get("DLCP_HW_TIMEOUT_S", "15")),
        poll_interval_s=float(os.environ.get("DLCP_HW_MAIN_POLL_S", "0.1")),
        expected_preset=current_preset,
        muted=False,
        active=True,
    )

    preset_action = "F2" if current_preset == "A" else "F1"
    expected_preset = "B" if preset_action == "F2" else "A"
    hw._send_ir(ir_template, action=preset_action)
    hw._wait_for_main_pair_state(
        vid=hw.DEFAULT_VID,
        pid=hw.DEFAULT_PID,
        timeout_s=float(os.environ.get("DLCP_HW_TIMEOUT_S", "15")),
        poll_interval_s=float(os.environ.get("DLCP_HW_MAIN_POLL_S", "0.1")),
        expected_preset=expected_preset,
        muted=False,
        active=True,
    )

    line1, line2 = _capture_lcd_consensus(tmp_path, "diag_ir_after_preset")
    assert line1.startswith(("PB1", "PB2")), (
        f"IR preset should not wedge or navigate away from Diagnostics; "
        f"got {line1!r} / {line2!r}"
    )
    if expected_page:
        assert line1.startswith(expected_page), (
            f"IR preset should keep CONTROL on {expected_page}; "
            f"got {line1!r} / {line2!r}"
        )

    hw._send_ir(ir_template, action="STANDBY")
    standby_evidence = _wait_for_standby_evidence(
        timeout_s=float(os.environ.get("DLCP_HW_TIMEOUT_S", "15")),
        poll_s=float(os.environ.get("DLCP_HW_MAIN_POLL_S", "0.1")),
        stable_polls=int(os.environ.get("DLCP_HW_STANDBY_STABLE_POLLS", "2")),
    )
    assert standby_evidence["mode"] in {
        "both_mains_inactive",
        "no_visible_mains",
        "main_probe_error",
    }
    line1, line2 = _wait_for_lcd_line1(
        tmp_path,
        name="diag_ir_after_standby",
        expected="Zzz...",
        timeout_s=float(os.environ.get("DLCP_HW_LCD_TIMEOUT_S", "25")),
        poll_s=float(os.environ.get("DLCP_HW_LCD_POLL_S", "0.5")),
    )
    assert line1 == "Zzz...", (
        f"IR STANDBY from Diagnostics must show Zzz LCD before WAKE; "
        f"got {line1!r} / {line2!r}"
    )
    time.sleep(float(os.environ.get("DLCP_HW_STBY_DWELL_S", "1.0")))

    errors: list[str] = []
    for _ in range(int(os.environ.get("DLCP_HW_WAKE_MAX_ATTEMPTS", "3"))):
        hw._send_ir(ir_template, action="WAKE")
        try:
            hw._wait_for_main_pair_state(
                vid=hw.DEFAULT_VID,
                pid=hw.DEFAULT_PID,
                timeout_s=float(os.environ.get("DLCP_HW_TIMEOUT_S", "15")),
                poll_interval_s=float(os.environ.get("DLCP_HW_MAIN_POLL_S", "0.1")),
                expected_preset=expected_preset,
                muted=False,
                active=True,
            )
            break
        except Exception as exc:
            errors.append(str(exc))
            time.sleep(float(os.environ.get("DLCP_HW_WAKE_RETRY_DELAY_S", "1.0")))
    else:
        raise AssertionError(f"WAKE from Diagnostics did not restore MAIN pair: {errors!r}")

    line1, line2 = _wait_for_lcd_line1(
        tmp_path,
        name="diag_ir_after_wake",
        expected="Volume",
        timeout_s=float(os.environ.get("DLCP_HW_LCD_TIMEOUT_S", "25")),
        poll_s=float(os.environ.get("DLCP_HW_LCD_POLL_S", "0.5")),
    )
    assert line2 == f"Active: {expected_preset}", (
        f"WAKE from Diagnostics returned to Volume but with unexpected row 2: "
        f"{line1!r} / {line2!r}"
    )
