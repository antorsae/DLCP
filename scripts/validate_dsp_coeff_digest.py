#!/usr/bin/env python3
"""Sanity-check the DSP preset-coefficient digest oracle.

Boots the V1.73 CONTROL + 2x V3.5 MAIN chain, drives a preset A->B->A sequence
via the real IR path, and snapshots each MAIN's TAS3108 biquad coefficient image
(0x37..0x90).  Proves the oracle CAN see actual coefficient state by confirming
the nominal contract:

  * preset A coeffs != preset B coeffs   (a switch really rewrites the DSP)
  * PB1 image == PB2 image on each preset (no cross-unit coeff desync)

If those hold, a divergence found during exploration is meaningful.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dlcp_fw.paths import V173_CONTROL_HEX, V35_MAIN_HEX  # noqa: E402
from dlcp_fw.sim.dlcp_sim_native import Chain  # noqa: E402

IR_ADDR = 0x10
IR_PRESET_A = 0x38
IR_PRESET_B = 0x39
BIQUAD = range(0x37, 0x91)  # 0x37..0x90 inclusive (per dual_main_preset_sync)


def biquad_image(chain: Chain, unit: int) -> bytes:
    return bytes(chain.read_main_dsp_reg(unit, s) for s in BIQUAD)


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def snapshot(chain: Chain, label: str) -> tuple[str, str]:
    img0, img1 = biquad_image(chain, 0), biquad_image(chain, 1)
    p0 = chain.read_main_reg(0, 0x05E) & 0x04
    p1 = chain.read_main_reg(1, 0x05E) & 0x04
    d0, d1 = digest(img0), digest(img1)
    print(f"[{label}] PB1 preset_bit={p0>>2} biquad={d0}  |  "
          f"PB2 preset_bit={p1>>2} biquad={d1}  |  PB1==PB2: {d0 == d1}")
    return d0, d1


def main() -> int:
    chain = Chain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX), main_hex_path=str(V35_MAIN_HEX)
    )
    chain.run_until_connected(limit=240)
    print(f"booted; lcd={chain.lcd_lines()}")

    chain.inject_decoded_ir_event(addr=IR_ADDR, cmd=IR_PRESET_A)
    chain.step_ticks(160_000_000)
    a0, a1 = snapshot(chain, "preset A")

    chain.inject_decoded_ir_event(addr=IR_ADDR, cmd=IR_PRESET_B)
    chain.step_ticks(160_000_000)
    b0, b1 = snapshot(chain, "preset B")

    chain.inject_decoded_ir_event(addr=IR_ADDR, cmd=IR_PRESET_A)
    chain.step_ticks(160_000_000)
    a0b, a1b = snapshot(chain, "preset A (return)")

    print("\n--- contract checks ---")
    ok = True
    if a0 == b0 or a1 == b1:
        print("FAIL: preset A and B biquad images are identical -> switch did NOT "
              "rewrite coeffs (silent no-op). Oracle would have NOTHING to compare.")
        ok = False
    else:
        print("PASS: preset A coeffs differ from preset B coeffs (switch rewrites DSP).")
    if a0 != a1 or b0 != b1:
        print("NOTE: PB1 != PB2 on a preset in this nominal run -> would be flagged "
              "as cross-PB coeff desync (investigate timing/settle).")
    else:
        print("PASS: PB1 and PB2 hold byte-identical coeffs on each preset.")
    if a0b != a0:
        print("NOTE: returning to preset A produced a different image than the first "
              "preset-A snapshot -> preset->coeff mapping is not stable.")
    else:
        print("PASS: returning to preset A reproduced the same coeff image (stable mapping).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
