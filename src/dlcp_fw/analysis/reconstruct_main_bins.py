#!/usr/bin/env python3
"""
Reconstruct the main DLCP analysis binaries from the Intel HEX file.

This answers "how was firmware.bin generated?" concretely:
  - Parse `firmware/stock/main/DLCP Firmware V2.3.hex`
  - Emit:
      * code_only.bin  : bytes [0x1000..0x5FFF] (0x5000 bytes)
      * eeprom.bin     : bytes [0xF00000..0xF000FF] (256 bytes)
      * firmware.bin   : flat image from 0x1000 up to 0xF000FF inclusive
                        (size 0xEFF100 = 15,724,800 bytes), gaps filled 0xFF
    Note: firmware.bin is *not* a physical flash dump; it includes large padding.
"""

from __future__ import annotations

import argparse
import pathlib

from dlcp_fw.paths import FIRMWARE_DUMPS_DIR, STOCK_MAIN_HEX


class HexParseError(RuntimeError):
    pass


def parse_intel_hex(path: pathlib.Path) -> dict[int, int]:
    mem: dict[int, int] = {}
    upper = 0

    def b(h: str) -> int:
        try:
            return int(h, 16)
        except ValueError as e:
            raise HexParseError(f"bad hex byte {h!r} in {path}") from e

    with path.open("r", encoding="ascii", errors="strict") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise HexParseError(f"{path}:{lineno}: missing ':'")
            ll = b(line[1:3])
            aaaa = int(line[3:7], 16)
            rtype = b(line[7:9])
            data_hex = line[9 : 9 + ll * 2]
            cc = b(line[9 + ll * 2 : 11 + ll * 2])

            total = ll + ((aaaa >> 8) & 0xFF) + (aaaa & 0xFF) + rtype
            data: list[int] = []
            for i in range(0, len(data_hex), 2):
                bb = b(data_hex[i : i + 2])
                data.append(bb)
                total += bb
            total &= 0xFF
            calc = (~total + 1) & 0xFF
            if calc != cc:
                raise HexParseError(
                    f"{path}:{lineno}: checksum mismatch (got 0x{cc:02x}, want 0x{calc:02x})"
                )

            if rtype == 0x00:
                base = (upper << 16) | aaaa
                for i, bb in enumerate(data):
                    mem[base + i] = bb & 0xFF
            elif rtype == 0x01:
                break
            elif rtype == 0x04:
                if ll != 2:
                    raise HexParseError(f"{path}:{lineno}: type 04 with ll={ll}")
                upper = (data[0] << 8) | data[1]
            else:
                # ignore other record types
                continue

    return mem


def write_region(
    mem: dict[int, int],
    out_path: pathlib.Path,
    start: int,
    length: int,
    fill: int = 0xFF,
) -> None:
    buf = bytearray([fill & 0xFF] * length)
    end_excl = start + length
    for addr, val in mem.items():
        if start <= addr < end_excl:
            buf[addr - start] = val & 0xFF
    out_path.write_bytes(bytes(buf))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hex",
        type=pathlib.Path,
        default=STOCK_MAIN_HEX,
        help=f"path to main firmware Intel HEX (default: {STOCK_MAIN_HEX})",
    )
    ap.add_argument(
        "--out-dir",
        type=pathlib.Path,
        default=FIRMWARE_DUMPS_DIR,
        help=f"output directory (default: {FIRMWARE_DUMPS_DIR})",
    )
    args = ap.parse_args()

    hex_path = args.hex.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    mem = parse_intel_hex(hex_path)

    # code_only.bin: 0x1000..0x5FFF inclusive => length 0x5000
    write_region(mem, out_dir / "code_only.bin", 0x1000, 0x5000, fill=0xFF)

    # eeprom.bin: 0xF00000..0xF000FF
    write_region(mem, out_dir / "eeprom.bin", 0xF00000, 0x100, fill=0xFF)

    # firmware.bin: flat from 0x1000 up to 0xF000FF inclusive.
    #
    # Historical note: the existing repo artifact is a "nulled" sparse image
    # (padding filled with 0x00), not an "erased flash" image (0xFF).
    fw_len = (0xF00000 - 0x1000) + 0x100
    write_region(mem, out_dir / "firmware.bin", 0x1000, fw_len, fill=0x00)

    print("wrote:", out_dir / "code_only.bin")
    print("wrote:", out_dir / "eeprom.bin")
    print("wrote:", out_dir / "firmware.bin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
