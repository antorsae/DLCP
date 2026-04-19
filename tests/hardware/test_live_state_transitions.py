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
    rc = hw.main(
        _common_cli_args()
        + [
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


# ---------------------------------------------------------------------------
# Layer 5 Diagnostics page (V1.71 + V3.2)
#
# Menu navigation to Diagnostics is driven by the CONTROL's PHYSICAL
# RIGHT/LEFT buttons (the IR vocabulary in hardware_flipper_ir.py
# intentionally does not include menu-navigation actions).  This test
# therefore requires the operator to manually navigate before running:
#
#   1. From Volume, press RIGHT physical button on CONTROL → Preset(1)
#   2. Press RIGHT again → Diagnostics(2)
#   3. Set DLCP_HW_LAYER5_AT_DIAG=1 in the environment
#   4. Run this test
#
# See docs/HARDWARE_TEST.md §"Diagnostics page" for the full operator
# walk-through and resolves-which-Task #22-question matrix.
# ---------------------------------------------------------------------------


@pytest.mark.hardware
def test_live_diagnostics_page_renders_two_pb_rows(tmp_path: Path) -> None:
    """Layer 5 live-rig validation: confirm CONTROL's Diagnostics page
    renders the spec'd ``1:...`` / ``2:...`` two-row layout when the
    operator has manually navigated to the page.

    This is the test that distinguishes Task #22 (gpsim two-MAIN echo
    loop, currently quarantined under ``_V171_V32_PB2_BRIDGE_XFAIL``)
    from a real V1.71 / V3.2 firmware bug.  If both rows render here,
    the sim quarantine is harness-only and the firmware is sound.
    """
    if os.environ.get("DLCP_HW_LAYER5_AT_DIAG") != "1":
        pytest.skip(
            "set DLCP_HW_LAYER5_AT_DIAG=1 once operator has manually "
            "navigated CONTROL to the Diagnostics screen via physical "
            "RIGHT, RIGHT button presses; see docs/HARDWARE_TEST.md "
            "§Diagnostics page for the full walk-through"
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
    line2 = (summary.get("consensus", {}).get("line2") or "").strip()

    # Pass criteria: row 0 starts with "1:" and row 1 starts with "2:".
    # The counter chars (or `n/a` for a silent / unsupported PB) follow.
    # We do NOT assert the exact counter content here — that varies by
    # rig state; basic two-row presence is sufficient to disprove the
    # gpsim Task #22 quarantine hypothesis on real hardware.
    assert line1.startswith("1:"), (
        f"line1 must start with '1:' on the Diagnostics page; got {line1!r}.  "
        f"Either the operator did not navigate to Diagnostics before "
        f"setting DLCP_HW_LAYER5_AT_DIAG=1, or V1.71 CONTROL is not flashed."
    )
    assert line2.startswith("2:"), (
        f"line2 must start with '2:' on the Diagnostics page; got {line2!r}.  "
        f"V1.71 CONTROL renders both rows even when PB2 is silent (as `2:n/a`); "
        f"absence of the '2:' prefix means CONTROL exited the page or the "
        f"render path is broken."
    )
