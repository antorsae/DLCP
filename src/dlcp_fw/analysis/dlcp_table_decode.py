#!/usr/bin/env python3
"""
Decode the persisted DSP/config table used by DLCP main firmware.

Main firmware stores a 0xA00-byte table in program flash at 0x5600..0x5FFF.
Entries are 24 bytes:
  word0 = (subaddr << 8) | op
  word1 = data_size (bytes)
  payload = 20 bytes (padded)

This script prints a compact view so we can reason about "what is in a preset"
and how much space each preset needs.
"""

from __future__ import annotations

import argparse
import pathlib


def u16le(b: bytes) -> int:
    return b[0] | (b[1] << 8)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--firmware-bin",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parent.parent / "firmware.bin",
        help="path to analysis/firmware.bin (default: analysis/firmware.bin)",
    )
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0x5600, help="table base address")
    ap.add_argument("--size", type=lambda s: int(s, 0), default=0xA00, help="table size in bytes")
    args = ap.parse_args()

    fw = args.firmware_bin.read_bytes()

    # firmware.bin is a flat image starting at 0x1000.
    if args.base < 0x1000:
        raise SystemExit("base must be >= 0x1000 for this firmware.bin layout")
    off = args.base - 0x1000
    table = fw[off : off + args.size]
    if len(table) != args.size:
        raise SystemExit("table slice out of range")

    n_full = args.size // 24
    rem = args.size % 24
    print(f"table @ 0x{args.base:04X} size=0x{args.size:X} full_entries={n_full} rem_bytes={rem}")
    print("idx  flash    op sub  len  payload[0:8]")

    op_counts = {}
    len_counts = {}
    sub_counts = {}

    for i in range(0, len(table) - rem, 24):
        idx = i // 24
        entry = table[i : i + 24]
        w0 = u16le(entry[0:2])
        w1 = u16le(entry[2:4])
        op = w0 & 0xFF
        sub = (w0 >> 8) & 0xFF
        payload = entry[4:24]

        op_counts[op] = op_counts.get(op, 0) + 1
        len_counts[w1] = len_counts.get(w1, 0) + 1
        sub_counts[sub] = sub_counts.get(sub, 0) + 1

        if op == 0x01:
            pfx = payload[:8].hex()
            print(f"{idx:3d}  0x{args.base + i:04X}  {op:02X} {sub:02X} 0x{w1:04X}  {pfx}")

    print()
    print("op counts:", {f"0x{k:02X}": v for k, v in sorted(op_counts.items())})
    print("len counts:", {f"0x{k:04X}": v for k, v in sorted(len_counts.items())})

    # show a few subaddr frequencies (useful sanity)
    top = sorted(sub_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:16]
    print("top subaddrs:", [(f"0x{k:02X}", v) for k, v in top])

    if rem:
        tail = table[-rem:]
        print(f"tail @ 0x{args.base + args.size - rem:04X} ({rem} bytes): {tail.hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
