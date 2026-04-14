from __future__ import annotations

import pytest

from dlcp_fw.flash import dlcp_preset
from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo
from dlcp_fw.flash.dlcp_main_flash import DeviceSnapshot, RouteEntry, VersionInfo


def _fake_info(path: bytes = b"test-path") -> HidDeviceInfo:
    return HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=path,
        manufacturer_string="Hypex BV",
        product_string="DLCP",
        serial_number="SER",
    )


def _fake_snapshot() -> DeviceSnapshot:
    return DeviceSnapshot(
        mode="app",
        product_string="DLCP",
        manufacturer_string="Hypex BV",
        serial_number="SER",
        version=VersionInfo(flag=0x03, major=3, minor=1),
        active_config_name="TestConfig",
        active_config_raw=b"TestConfig",
        active_routes=(
            RouteEntry(channel=1, value=0, label="L"),
            RouteEntry(channel=2, value=0, label="L"),
        ),
        warnings=(),
    )


def test_info_only_reports_active_preset(monkeypatch, capsys) -> None:
    monkeypatch.setattr(dlcp_preset, "_pick_device", lambda vid, pid, path: _fake_info())
    monkeypatch.setattr(dlcp_preset, "_probe_device_snapshot", lambda info, vid, pid: _fake_snapshot())
    monkeypatch.setattr(dlcp_preset, "_probe_active_preset_ep0", lambda vid, pid, path=None: "B")

    rc = dlcp_preset.main(["--info-only"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "device info:" in out
    assert "active preset: B" in out


def test_switch_sends_cmd20_and_verifies(monkeypatch, capsys) -> None:
    monkeypatch.setattr(dlcp_preset, "_pick_device", lambda vid, pid, path: _fake_info())
    monkeypatch.setattr(dlcp_preset, "_probe_device_snapshot", lambda info, vid, pid: _fake_snapshot())
    seen: dict[str, object] = {}

    def _fake_switch(*, vid, pid, preset, path=None):
        seen["vid"] = vid
        seen["pid"] = pid
        seen["preset"] = preset
        seen["path"] = path
        return {
            "active_flags_before": 0x08,
            "active_flags_write": 0x8C,
        }

    monkeypatch.setattr(dlcp_preset, "_write_preset_switch_ep0", _fake_switch)
    monkeypatch.setattr(dlcp_preset, "_probe_active_preset_ep0", lambda vid, pid, path=None: "A")
    flags = iter([0x84, 0x04, 0x04])
    monkeypatch.setattr(dlcp_preset, "_read_active_flags_ep0", lambda vid, pid, path=None: next(flags))
    monkeypatch.setattr(dlcp_preset.time, "sleep", lambda _: None)

    rc = dlcp_preset.main(["--preset", "B", "--settle-ms", "0", "--verify-timeout-s", "0.1"])

    assert rc == 0
    assert seen["vid"] == 0x04D8
    assert seen["pid"] == 0xFF89
    assert seen["preset"] == "B"
    assert seen["path"] is None
    out = capsys.readouterr().out
    assert "switched preset: A -> B" in out
    assert "transport: EP0 active_flags toggle + DSP reapply request" in out
    assert "CONTROL will remain out of sync with MAIN preset state" in out
    assert "verification waits for active_flags.7 to clear" in out


def test_switch_errors_if_verify_never_reaches_target(monkeypatch) -> None:
    monkeypatch.setattr(dlcp_preset, "_pick_device", lambda vid, pid, path: _fake_info())
    monkeypatch.setattr(dlcp_preset, "_probe_device_snapshot", lambda info, vid, pid: _fake_snapshot())
    monkeypatch.setattr(
        dlcp_preset,
        "_write_preset_switch_ep0",
        lambda *, vid, pid, preset, path=None: {
            "active_flags_before": 0x08,
            "active_flags_write": 0x8C,
        },
    )
    monkeypatch.setattr(dlcp_preset, "_probe_active_preset_ep0", lambda vid, pid, path=None: "A")
    monkeypatch.setattr(dlcp_preset, "_read_active_flags_ep0", lambda vid, pid, path=None: 0x80)

    ticks = iter([0.0, 1.0, 2.0, 3.0])
    monkeypatch.setattr(dlcp_preset.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(dlcp_preset.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match=r"device reports A \(active_flags=0x80, reapply pending\), expected B with reapply clear"):
        dlcp_preset.main(["--preset", "B", "--settle-ms", "0", "--verify-timeout-s", "0.5"])


def test_switch_reports_low_level_switch_error(monkeypatch) -> None:
    monkeypatch.setattr(dlcp_preset, "_pick_device", lambda vid, pid, path: _fake_info())
    monkeypatch.setattr(dlcp_preset, "_probe_device_snapshot", lambda info, vid, pid: _fake_snapshot())
    monkeypatch.setattr(dlcp_preset, "_probe_active_preset_ep0", lambda vid, pid, path=None: "A")
    monkeypatch.setattr(
        dlcp_preset,
        "_write_preset_switch_ep0",
        lambda *, vid, pid, preset, path=None: (_ for _ in ()).throw(
            RuntimeError("EP0 write failed")
        ),
    )

    with pytest.raises(RuntimeError, match="EP0 write failed"):
        dlcp_preset.main(["--preset", "B", "--settle-ms", "0"])


def test_switch_noops_when_target_already_active(monkeypatch, capsys) -> None:
    monkeypatch.setattr(dlcp_preset, "_pick_device", lambda vid, pid, path: _fake_info())
    monkeypatch.setattr(dlcp_preset, "_probe_device_snapshot", lambda info, vid, pid: _fake_snapshot())
    monkeypatch.setattr(dlcp_preset, "_probe_active_preset_ep0", lambda vid, pid, path=None: "A")

    rc = dlcp_preset.main(["--preset", "A"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "preset already active: A" in out


def test_switch_forwards_explicit_path_to_ep0_helpers(monkeypatch) -> None:
    seen: dict[str, object] = {}

    monkeypatch.setattr(dlcp_preset, "_pick_device", lambda vid, pid, path: _fake_info(path=path))
    monkeypatch.setattr(dlcp_preset, "_probe_device_snapshot", lambda info, vid, pid: _fake_snapshot())
    monkeypatch.setattr(dlcp_preset, "_probe_active_preset_ep0", lambda vid, pid, path=None: "A")

    def _fake_switch(*, vid, pid, preset, path=None):
        seen["switch_path"] = path
        return {
            "active_flags_before": 0x00,
            "active_flags_write": 0x84,
        }

    flags = iter([0x84, 0x04, 0x04])

    monkeypatch.setattr(dlcp_preset, "_write_preset_switch_ep0", _fake_switch)
    def _fake_read(vid, pid, path=None):
        seen["read_path"] = path
        return next(flags)

    monkeypatch.setattr(dlcp_preset, "_read_active_flags_ep0", _fake_read)
    monkeypatch.setattr(dlcp_preset.time, "sleep", lambda _: None)

    rc = dlcp_preset.main(
        ["--path", "hid-main-b", "--preset", "B", "--settle-ms", "0", "--verify-timeout-s", "0.1"]
    )

    assert rc == 0
    assert seen["switch_path"] == b"hid-main-b"
    assert seen["read_path"] == b"hid-main-b"
