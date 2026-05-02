#!/usr/bin/env python3
"""Reproduce real-hardware field bug #44 in the rust simulator (Python facade).

Real-HW symptom (2026-04-27, V1.71 CONTROL + V3.2 MAIN0 + V3.2 MAIN1):
  - cmd 0x44 (USB diag readout from MAIN-side RAM): all-zero counters
    Runtime: I0 D0 S0 B0 R0 A0 P0
  - LCD on PB1 Diag screen (CONTROL-side cache rendering):
    PB1: I+ D1 SE B4   <- substantial Overflow content, NOT all-zero!

Hypothesis (per `docs/analysis/HW_2026-04-27_DIAG_AND_STDBY_FINDINGS.md` §4):
  CONTROL POR cache cells (`v171_diag_pb1_*`, 0x180+) start at random RAM
  at cold boot.  BF/2N replies of zero data don't fully overwrite the
  garbage when some BF/2N frames are dropped by the parser-stall
  watchdog.  Therefore the LCD reflects garbage + partial overwrites,
  while cmd 0x44's direct read-out from MAIN's diag_i..diag_p (0x2E5+)
  reflects MAIN-side counters which legitimately ARE zero on a healthy
  idle rig.

Rust sim cannot spontaneously reproduce the random-POR garbage (rust's
POR clears RAM to known values), but a SEEDED probe reproduces the
exact symptom by manually injecting "garbage" matching the HW capture.

Full analysis + bugfix proposal:
  docs/analysis/TASK_44_LCD_VS_CMD44_DIVERGENCE.md

Usage:
  PYTHONPATH=src .venv_ep0/bin/python scripts/reproduce_bug44_lcd_vs_cmd44.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain  # noqa: E402


def main() -> int:
    print("=" * 70)
    print("Field bug #44 reproduction in rust simulator (Python facade)")
    print("V1.71 CONTROL + V3.2 MAIN0 + V3.2 MAIN1")
    print("=" * 70)

    # Build chain, boot to Volume display.
    c = RustChain.from_v171_v32()
    used = c.run_until_connected(limit=200)
    print(f"\n[STEP 1] Chain booted in {used} chunks (~{used * 200_000} K20 Tcy)")
    print(f"         LCD: {c.lcd_lines()!r}")
    if not (c.is_connected() and not c.is_waiting()):
        print("FAILURE: chain did not reach Volume display")
        return 1

    # Seed CONTROL's PB1 cache with the EXACT real-HW values.
    # Encoding (V1.71 Tier-1): ' '=0, '1'..'9'=1..9, 'A'..'E'=10..14, '+'=15
    PB1_BASE = 0x180
    pb1_seed = [
        (0x0F, "I+"),  # diag_pb1_i = saturated
        (0x01, "D1"),
        (0x0E, "SE"),
        (0x04, "B4"),
        (0x0A, "RA"),
        (0x03, "A3"),
        (0x08, "P8"),
    ]

    print(f"\n[STEP 2] Seed CONTROL PB1 cache (0x180..0x186) with real-HW values:")
    for i, (val, label) in enumerate(pb1_seed):
        addr = PB1_BASE + i
        c.write_reg(addr, val)
        print(f"           0x{addr:03X} = 0x{val:02X}  ({label})")

    # Set diag_present.bit_0 to mark PB1 as having replied.
    c.write_reg(0x197, 0x01)
    print(f"         0x197 = 0x01 (v171_diag_present, bit_0 = PB1 has replied)")

    # Navigate Volume(0) -> ... -> PB1 Diag (state 4) via 4 RIGHT presses.
    # Direct PORTA manipulation (5M-tick hold) instead of facade's press()
    # which holds 50M ticks and causes button-repeat past PB1 Diag(4)
    # into PB2 Diag(5).
    RA4_MASK = 0x10
    PORTA = 0xF80
    print(f"\n[STEP 3] Navigate to PB1 Diag (state 4) via 4 short RIGHT presses")
    c.step_tcy(5_000_000 // 16)
    for press in range(4):
        porta = c.read_reg(PORTA)
        c.write_reg(PORTA, porta & ~RA4_MASK)
        c.step_tcy(5_000_000 // 16)
        c.write_reg(PORTA, porta | RA4_MASK)
        c.step_tcy(5_000_000 // 16)
        state = c.read_reg(0x0BF)
        print(f"          RIGHT #{press + 1}: menu_state = {state}")

    # Step the chain so the redraw cadence fires.
    print(f"\n[STEP 4] Step chain to trigger LCD redraw")
    redraw_chunk = -1
    for chunk in range(20):
        c.step_tcy(1_000_000)
        line0, line1 = c.lcd_lines()
        if line0.startswith("PB1:"):
            redraw_chunk = chunk
            print(f"          redraw fired at chunk {chunk}: line0={line0!r}, line1={line1!r}")
            break

    line0, line1 = c.lcd_lines()
    print(f"\n[STEP 5] Final LCD reads:")
    print(f"          line0 = {line0!r}")
    print(f"          line1 = {line1!r}")

    print(f"\n[STEP 6] CONTROL PB1 cache after LCD render:")
    all_match = True
    for i, (expected, label) in enumerate(pb1_seed):
        actual = c.read_reg(PB1_BASE + i)
        match = (actual == expected)
        all_match = all_match and match
        flag = "OK" if match else "DIFFER"
        print(f"          0x{PB1_BASE + i:03X} = 0x{actual:02X} (seeded 0x{expected:02X}) {flag}")

    # Strict reproduction gate: LCD MUST equal the seeded-cache pattern
    # exactly so the persisted script doesn't false-pass on partial
    # convergence (e.g. line0 starting with "PB1:" but holding
    # "PB1: I0 D0 ..." because the cache got cleared between seed and
    # render).
    EXPECTED_LINE0 = "PB1: I+ D1 SE B4"
    EXPECTED_LINE1 = "RA A3 P8        "

    line0_match = (line0 == EXPECTED_LINE0)
    line1_match = (line1 == EXPECTED_LINE1)
    redraw_ok = (redraw_chunk >= 0)

    print()
    print("=" * 70)
    print("BUG #44 REPRODUCTION VERDICT:")
    if line0_match and line1_match and all_match and redraw_ok:
        print("  - LCD shows substantial cell content sourced from CONTROL cache")
        print(f"  - line0 == {EXPECTED_LINE0!r}  OK")
        print(f"  - line1 == {EXPECTED_LINE1!r}  OK")
        print("  - LCD content matches real-HW PB1 capture pattern exactly")
        print("  - Cache values are independent RAM from MAIN0 runtime counters")
        print("  - CONTROL render-from-cache architecture allows LCD to desync")
        print("    from MAIN runtime cells when cache holds non-MAIN values")
        print()
        print("  BUG #44 SYMPTOM REPRODUCED in rust simulator.")
        print()
        print("  Suggested fix: see docs/analysis/TASK_44_LCD_VS_CMD44_DIVERGENCE.md")
        print("=" * 70)
        return 0

    print(
        f"  Reproduction did not converge:"
        f"\n    line0 = {line0!r}  (expected {EXPECTED_LINE0!r}, match={line0_match})"
        f"\n    line1 = {line1!r}  (expected {EXPECTED_LINE1!r}, match={line1_match})"
        f"\n    cache_match={all_match}; redraw_chunk={redraw_chunk}"
    )
    print("=" * 70)
    return 1


if __name__ == "__main__":
    sys.exit(main())
