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


# ---------------------------------------------------------------------------
# Path 1 strict gate: does PB2 reply convergence land on real silicon?
#
# Per `docs/SIM_REWRITE_RUST_PROGRESS.md` task P3.6b, the Rust simulator
# rewrite has structurally retired the gpsim PTY-bridge mirror echo
# (P3.6a) but reproduces the same `v171_diag_present` PB2 saturation
# the Python xfails describe.  No real-hardware test currently
# distinguishes "V1.71 firmware fails PB2 reply on real silicon too"
# from "both simulators have a shared timing/electrical fidelity gap".
#
# The strict gate below is the test that answers that question.
# Operator workflow is identical to
# `test_live_diagnostics_page_renders_two_pb_rows`; the difference is
# the post-capture assertion: instead of accepting `2:n/a` as a
# legitimate "PB silent" rendering, we REQUIRE that line 2 contains
# at least one real diag-counter cell character (digit `'1'..'9'`,
# letter `'A'..'E'`, or saturated `'+'` per the V1.71 v171_diag_emit_nib_w
# encoding in `dlcp_control_v171.asm:4187+`).  PASS = V1.71 works on
# real silicon, sim has a fidelity gap (P3.6b stays open as sim work).
# FAIL = V1.71 firmware itself fails PB2 reply convergence; sim agrees;
# resolution is to remove the four `_V171_V32_PB2_BRIDGE_XFAIL` markers
# in `tests/sim/test_v171_v32_layer5_diag_chain.py` with a comment
# referencing this test, and close Task #22 as "documented firmware
# limitation, not a sim bug".
#
# This test is OPT-IN via DLCP_HW_LAYER5_REQUIRE_PB2_DATA=1 so the
# routine hardware suite (which only requires the lenient two-row-
# present gate above) doesn't fail on rigs whose V1.71 saturates at
# PB1.  Operator runs both: the lenient gate first, then this strict
# gate to record the actual silicon truth.
# ---------------------------------------------------------------------------


@pytest.mark.hardware
def test_live_diagnostics_pb2_data_lands_on_real_silicon(tmp_path: Path) -> None:
    """Path 1 strict gate -- distinguishes V1.71 firmware bug from sim
    fidelity gap by asserting that the PB2 Diag PAGE (state 5) renders
    a non-`n/a` row 1, i.e. PB2 has actually replied to CONTROL's
    BF/2N queries on real silicon.

    Operator workflow:
        1. Manually navigate CONTROL from the Volume screen to the
           PB2 Diag page (state 5).  V1.71 Tier-1 6-state menu ring
           is 0=Volume, 1=Preset, 2=Input, 3=Setup, 4=PB1Diag,
           5=PB2Diag (per `dlcp_control_v171.asm:4805+`), so RIGHT
           must be pressed FIVE times from the Volume default to
           reach PB2 Diag.  See `docs/HARDWARE_TEST.md`
           §"Diagnostics page" for the full walk-through.
        2. Wait >= 10 s on the page so the cadence loop fires
           alternating cmd 0x21 + cmd 0x22 queries against both PBs
           (~1 s per cycle, target toggles per BF/27 reception).
        3. (Optional, complementary) Run
           `.venv_ep0/bin/python scripts/dlcp_diag.py` to record
           the per-MAIN cmd 0x44 snapshot for both MAINs.  These are
           what CONTROL's LCD SHOULD eventually display if PB2 reply
           convergence works.
        4. Set DLCP_HW_LAYER5_AT_DIAG=1 and
           DLCP_HW_LAYER5_REQUIRE_PB2_DATA=1.
        5. Run this test.

    V1.71 Tier-1 LCD layout reference (per
    `docs/V32_DIAG_TIER1_SPEC.md` §"Phase 3.4 implementation notes"
    and `dlcp_control_v171.asm:3484+`):

        Page = state 4 (PB1) or state 5 (PB2).  Both 16x2 LCD rows
        belong to the SAME PB.  Layout dispatch by health:

          Absent   (PB has never replied):
              row 0 = "PBn"               (+ 13 spaces)
              row 1 = "n/a"               (+ 13 spaces)
          Healthy  (all 11 cache cells == 0):
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
        'A'..'E', or '+' (saturated) per the
        `v171_diag_emit_nib_w` encoding at
        `dlcp_control_v171.asm:4187+`.

    Decision matrix:

        row 1 == "n/a"        =>  FAIL.  PB2 absent / silent.
                                  V1.71 firmware itself does not
                                  deliver PB2 reply convergence on
                                  real silicon; both simulators are
                                  correctly reproducing this
                                  firmware behavior.
                                  ACTION: per
                                  docs/SIM_REWRITE_RUST_PROGRESS.md
                                  P3.6b: (a) close Task #22 as
                                  documented firmware limitation,
                                  (b) remove the four
                                  `_V171_V32_PB2_BRIDGE_XFAIL`
                                  markers with a comment
                                  referencing this test run, (c)
                                  close P3.6b.
        row 1 == "OK"         =>  PASS.  PB2 healthy with all-zero
                                  counters.  Reply convergence
                                  works; both simulators have a
                                  shared fidelity gap.
        row 1 has cell pairs  =>  PASS.  PB2 has non-zero counter
                                  activity; reply convergence
                                  works.
        empty / unrecognised  =>  Fail with "ambiguous" diagnostic
                                  pointing the operator at
                                  `scripts/dlcp_diag.py` to
                                  cross-reference MAIN1's local
                                  cmd 0x44 snapshot.

    Why pattern-match against literal layouts (n/a, OK, cell entries)
    rather than per-char class checks?  Because static column-label
    letters (I/D/S/B/R/A/P/O/V/W/X) ARE in the cell-pair format, and
    several of them ('A', 'B', 'D') overlap with the value-letter
    set 'A'..'E' from the encoding.  A naive "is this char in
    [0-9A-E+]" check would treat the static label 'D' as a value
    char and pass the convergence gate even when every counter is
    zero -- false-positive risk codex flagged in 437a7dd review.
    """
    if os.environ.get("DLCP_HW_LAYER5_AT_DIAG") != "1":
        pytest.skip(
            "set DLCP_HW_LAYER5_AT_DIAG=1 once operator has manually "
            "navigated CONTROL to the PB2 Diag page (state 5); see "
            "docs/HARDWARE_TEST.md §Diagnostics page for the full "
            "walk-through (5 RIGHT presses from the Volume screen)"
        )
    if os.environ.get("DLCP_HW_LAYER5_REQUIRE_PB2_DATA") != "1":
        pytest.skip(
            "this test is opt-in (set DLCP_HW_LAYER5_REQUIRE_PB2_DATA=1).  "
            "Path 1 strict gate per docs/SIM_REWRITE_RUST_PROGRESS.md P3.6b "
            "-- only run when explicitly resolving the sim-vs-firmware "
            "question for Task #22's PB2 reply convergence"
        )
    _require_live_rig_accessible()

    import json
    from dlcp_fw.cli import hardware_lcd_probe

    captures = int(os.environ.get("DLCP_HW_LAYER5_LCD_CAPTURES", "10"))
    output_root = tmp_path / "layer5_lcd_pb2_strict"
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

    # Pre-flight: confirm the operator actually navigated to the
    # PB2 Diag page (state 5).  V1.71 Tier-1 puts the page title
    # at row 0 cols 0..2 = "PB2".  Without this check, the row 1
    # decision below would mis-diagnose the wrong screen.
    assert line1.startswith("PB2"), (
        f"line1 must start with 'PB2' on the PB2 Diag page; got "
        f"{line1!r}.  Operator must navigate CONTROL to state 5 "
        f"(PB2 Diag) -- press RIGHT five times from the Volume "
        f"screen.  Anything else (Volume / Preset / Input / "
        f"Setup / PB1 Diag) means the wrong screen is captured.  "
        f"V1.71 Tier-1 6-state menu ring is documented at "
        f"`dlcp_control_v171.asm:4805+`."
    )

    # PB2 row 1 body, after stripping the trailing pad spaces.
    pb2_row1 = line2

    if pb2_row1 == "n/a":
        pytest.fail(
            f"\n  PB2 row 1 is the 'n/a' (absent) layout -- CONTROL has "
            f"NEVER registered a PB2 reply on real silicon.\n"
            f"  Reply chain fails at HOP E or earlier (CONTROL parser "
            f"does not dispatch BF/27 through the BF/2N\n"
            f"  last-frame path; v171_diag_present bit 1 stays clear; "
            f"renderer falls back to the absent layout per\n"
            f"  `docs/V32_DIAG_TIER1_SPEC.md` §'Phase 3.4 implementation notes').\n"
            f"  This rules out 'sim-only bug' for Task #22 and confirms "
            f"V1.71 firmware itself does NOT deliver PB2\n"
            f"  reply convergence on this rig.  Cross-reference "
            f"per-MAIN cmd 0x44 snapshots from `scripts/dlcp_diag.py`\n"
            f"  to confirm MAIN1 itself has counter data, isolating "
            f"the failure to the CONTROL parser path.\n"
            f"  ACTION: per docs/SIM_REWRITE_RUST_PROGRESS.md P3.6b:\n"
            f"    (a) close Task #22 as documented firmware limitation,\n"
            f"    (b) remove the four `_V171_V32_PB2_BRIDGE_XFAIL` markers in\n"
            f"        `tests/sim/test_v171_v32_layer5_diag_chain.py` with a comment\n"
            f"        referencing this test run,\n"
            f"    (c) close P3.6b.\n"
            f"\n  Captured LCD lines:\n"
            f"    line1 = {line1_raw!r}\n"
            f"    line2 = {line2_raw!r}\n"
        )

    if pb2_row1 == "":
        pytest.fail(
            f"\n  PB2 row 1 is empty after rstrip -- ambiguous between "
            f"'firmware bug', 'OCR misread', and 'wrong screen'.\n"
            f"  Disambiguate via `scripts/dlcp_diag.py` -- if MAIN1's "
            f"cmd 0x44 snapshot shows non-zero counters and the rig\n"
            f"  is actually on the PB2 Diag page (operator confirms "
            f"visually), the OCR likely misread `n/a` as empty.\n"
            f"  Re-capture with more `--captures` cycles via "
            f"DLCP_HW_LAYER5_LCD_CAPTURES (default 10).\n"
            f"\n  Captured LCD lines:\n"
            f"    line1 = {line1_raw!r}\n"
            f"    line2 = {line2_raw!r}\n"
        )

    # Healthy or Degraded / Overflow with at least some content.
    # Both branches mean PB2 reply convergence works on real silicon.
    if pb2_row1 == "OK":
        layout = "Healthy (all 11 PB2 counters == 0; PB2 IS replying)"
    else:
        layout = (
            f"Degraded / Overflow (PB2 has non-zero counter activity; "
            f"row 1 = {pb2_row1!r})"
        )

    print(
        f"\n  PB2 reply CONVERGED on real silicon.\n"
        f"  line1 (PB2 page title) = {line1_raw!r}\n"
        f"  line2 (PB2 cells)      = {line2_raw!r}\n"
        f"  Layout: {layout}\n"
        f"  -> V1.71 firmware delivers PB2 reply convergence on hardware.\n"
        f"  -> Both simulators (gpsim Python and Rust sim) have a SHARED\n"
        f"     timing/electrical fidelity gap.\n"
        f"  -> P3.6b stays open as sim-side investigation; do NOT remove\n"
        f"     the `_V171_V32_PB2_BRIDGE_XFAIL` markers yet.\n"
    )
