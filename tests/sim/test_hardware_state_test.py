from __future__ import annotations

import dataclasses
import json

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
