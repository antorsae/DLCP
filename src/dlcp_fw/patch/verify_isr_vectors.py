#!/usr/bin/env python3
"""Verify ISR vector redirects are applied in the patched hex."""

from dlcp_fw.paths import PATCHED_MAIN_HEX, SIM_ARTIFACTS_DIR
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.manifests import main_reset_to_appstart
from dlcp_fw.sim.overlay import apply_overlays

MAIN_HEX = PATCHED_MAIN_HEX
OUT_HEX = SIM_ARTIFACTS_DIR / "verify_isr.hex"
OUT_HEX.parent.mkdir(parents=True, exist_ok=True)

# Check original hex
mem = parse_intel_hex(MAIN_HEX)
print("Original hex at vector addresses:")
for addr in [0x0000, 0x0001, 0x0002, 0x0003,
             0x0008, 0x0009, 0x000A, 0x000B,
             0x0018, 0x0019]:
    val = mem.get(addr, 0xFF)
    print(f"  0x{addr:04X}: 0x{val:02X}")

# Apply overlays and check
manifests = [main_reset_to_appstart()]
results = apply_overlays(MAIN_HEX, OUT_HEX, manifests)
for r in results:
    print(f"Overlay '{r.manifest_name}': {r.changed_bytes} bytes changed")

# Check patched hex
mem2 = parse_intel_hex(OUT_HEX)
print("\nPatched hex at vector addresses:")
for addr in [0x0000, 0x0001, 0x0002, 0x0003,
             0x0008, 0x0009, 0x000A, 0x000B,
             0x0018, 0x0019]:
    val = mem2.get(addr, 0xFF)
    print(f"  0x{addr:04X}: 0x{val:02X}")

# Decode the instructions
def decode_goto(b0, b1, b2, b3):
    w1 = (b1 << 8) | b0
    w2 = (b3 << 8) | b2
    if (w1 & 0xFF00) == 0xEF00:
        k_lo = w1 & 0xFF
        k_hi = w2 & 0xFFF
        k = (k_hi << 8) | k_lo
        target = k * 2
        return f"GOTO 0x{target:06X}"
    return f"Unknown: {w1:04X} {w2:04X}"

print(f"\n  0x0000: {decode_goto(mem2[0x0000], mem2[0x0001], mem2[0x0002], mem2[0x0003])}")
print(f"  0x0008: {decode_goto(mem2[0x0008], mem2[0x0009], mem2[0x000A], mem2[0x000B])}")
w_18 = (mem2.get(0x0019, 0xFF) << 8) | mem2.get(0x0018, 0xFF)
print(f"  0x0018: 0x{w_18:04X} ({'RETFIE' if w_18 == 0x0010 else 'NOT RETFIE'})")
