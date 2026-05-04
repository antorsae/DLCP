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
# Path 1 strict gates: does PB1 / PB2 reply convergence land on real silicon?
#
# Per `docs/SIM_REWRITE_RUST_PROGRESS.md` task P3.6b, the Rust simulator
# rewrite has structurally retired the gpsim PTY-bridge mirror echo
# (P3.6a).  As of 2026-05-04 the rust sim is empirically WORSE than
# the gpsim PB2-saturation gap the Python xfails describe -- rust
# yields ZERO replies (PB1+PB2 both miss; v171_diag_present stays
# 0x00); see task #94.  The earlier prediction that rust would
# reproduce the same PB1-only saturation came from xfailed tests
# that actually use `run=False` so they never executed empirically.
# No real-hardware test currently distinguishes "V1.71 firmware fails
# PB2 reply on real silicon too" from "both simulators have a shared
# timing/electrical fidelity gap" (gpsim) or a distinct query
# emission/parser gap (rust, task #94).
#
# The two strict gates below answer that question.  Both gates assert
# the operator-navigated PB Diag page (state 4 = PB1, state 5 = PB2)
# is in a layout that proves the corresponding PB has replied:
#   * Degraded / Overflow (`PBn:` colon at row 0 col 3) -> PASS,
#     PB has non-zero counter activity.
#   * Healthy short (row 0 = "PBn", row 1 = "OK") -> PASS, PB
#     replied with all-zero counters.
#   * Absent short (row 0 = "PBn", row 1 = "n/a") -> FAIL, PB has
#     never replied.
#
# Operator runs BOTH gates -- one after navigating to the PB1 Diag
# page, then one after navigating to the PB2 Diag page -- to fill
# in the full PB1 x PB2 decision matrix (per the commit message
# 437a7dd → b581548 lineage):
#
#   PB1 PASS, PB2 PASS  -> Both reply paths work on hardware; both
#                          gpsim and Rust sim have a SHARED
#                          fidelity gap.  P3.6b stays open as
#                          sim-side investigation; do NOT remove
#                          the `_V171_V32_PB2_BRIDGE_XFAIL` markers.
#   PB1 PASS, PB2 FAIL  -> Asymmetric saturation reproduces on
#                          hardware; V1.71 firmware itself fails
#                          PB2 reply.  Close Task #22 as documented
#                          firmware limitation; remove the four
#                          `_V171_V32_PB2_BRIDGE_XFAIL` markers
#                          with a comment referencing this test
#                          run; close P3.6b.
#   PB1 FAIL, PB2 PASS  -> Inverted from sim symptom (very
#                          unexpected).  Hardware/wiring issue
#                          most likely; investigate the rig before
#                          drawing conclusions.
#   PB1 FAIL, PB2 FAIL  -> Whole chain broken; rerun pre-flight
#                          (`scripts/dlcp_diag.py --list`) and
#                          retry.  Does NOT answer the original
#                          sim-vs-firmware question.
#
# Both gates share the same body via `_assert_pb_diag_page_converged`
# below.  Each is OPT-IN behind `DLCP_HW_LAYER5_REQUIRE_PB{1,2}_DATA=1`
# so the routine hardware suite stays green on rigs that saturate at
# PB1 only.
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
            f"{pb_state}); see docs/HARDWARE_TEST.md §Diagnostics page "
            f"for the full walk-through ({nav_presses} RIGHT presses "
            f"from the Volume screen)"
        )
    if os.environ.get(opt_in_env_var) != "1":
        pytest.skip(
            f"this test is opt-in (set {opt_in_env_var}=1).  Path 1 "
            f"strict gate per docs/SIM_REWRITE_RUST_PROGRESS.md P3.6b "
            f"-- only run when explicitly resolving the sim-vs-firmware "
            f"question for Task #22's PB reply convergence"
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
            f"  Layout: Healthy (all 11 {pb_label} cache cells == 0; "
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
        2. Wait >= 10 s on the page so the cadence loop fires
           alternating cmd 0x21 + cmd 0x22 queries against both PBs.
        3. Set DLCP_HW_LAYER5_AT_DIAG=1 and
           DLCP_HW_LAYER5_REQUIRE_PB1_DATA=1.
        4. Run this test.

    Then operator navigates to PB2 Diag page (one more RIGHT) and
    runs `test_live_diagnostics_pb2_data_lands_on_real_silicon` with
    `DLCP_HW_LAYER5_REQUIRE_PB2_DATA=1`.  Combined results fill in
    the PB1 x PB2 decision matrix in the section header above.

    gpsim shows PB1 reply convergence works (`v171_diag_present`
    bit 0 sets reliably).  Rust does NOT (task #94, 2026-05-04
    empirical: zero replies).  This gate's role is the BASELINE
    confirmation that real silicon agrees with the gpsim PB1-works
    side.  If this fails AND the PB2 sibling fails, the rig itself
    is broken (not the firmware / sim question we're trying to
    answer).
    """
    _assert_pb_diag_page_converged(
        pb_num=1,
        opt_in_env_var="DLCP_HW_LAYER5_REQUIRE_PB1_DATA",
        tmp_path=tmp_path,
    )


@pytest.mark.hardware
def test_live_diagnostics_pb2_data_lands_on_real_silicon(tmp_path: Path) -> None:
    """Path 1 strict gate (PB2 leg) -- the leg whose hardware
    behavior decides Task #22's sim-vs-firmware question.

    Operator workflow:
        1. Manually navigate CONTROL from the Volume screen to the
           PB2 Diag page (state 5).  V1.71 Tier-1 6-state menu ring
           is 0=Volume, 1=Preset, 2=Input, 3=Setup, 4=PB1Diag,
           5=PB2Diag (per `dlcp_control_v171.asm:4805+`), so RIGHT
           must be pressed FIVE times from the Volume default to
           reach PB2 Diag.
        2. Wait >= 10 s on the page so the cadence loop fires
           alternating cmd 0x21 + cmd 0x22 queries against both PBs
           (~1 s per cycle, target toggles per BF/27 reception).
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
