#!/usr/bin/env python3
"""
DLCP EP0 RAM + EEPROM-shadow dumper.

This tool uses the same EP0 primitive as the flash dumper, but keeps reads in the
`TBLPTRH <= 0x07` path so data comes from RAM, not program flash.

Important:
- This does NOT provide a guaranteed raw 256-byte EEPROM dump on stock firmware.
- It does provide a safe dump of RAM bytes and a decoded map of EEPROM-backed
  values that stock firmware loads into RAM during boot (`function_007`).

Examples:
  # Capture 0x000..0x1FF RAM and decode known EEPROM shadows
  python3 -m dlcp_fw.flash.dlcp_ep0_eeprom_shadow_dump capture \
    --ram-start 0x000 --ram-size 0x200 \
    --out artifacts/sim/current/eeprom_shadow/ram_000_1ff.bin \
    --json-out artifacts/sim/current/eeprom_shadow/shadow.json

  # Decode from an existing RAM dump file
  python3 -m dlcp_fw.flash.dlcp_ep0_eeprom_shadow_dump decode \
    --in artifacts/sim/current/eeprom_shadow/ram_000_1ff.bin \
    --ram-start 0x000
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
from datetime import datetime, timezone


VID_DEFAULT = 0x04D8
PID_DEFAULT = 0xFF89


def parse_int(s: str) -> int:
    return int(s, 0)


def idx_for_addr(addr: int) -> int:
    if not (0 <= addr <= 0xFF):
        raise ValueError(f"addr out of range: 0x{addr:02X}")
    return (addr - 0xEC) & 0xFF


class DlcpEp0:
    def __init__(self, vid: int, pid: int) -> None:
        try:
            import usb.core  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "pyusb is required. Install with: python3 -m pip install pyusb"
            ) from exc

        self._usb_core = usb.core
        dev = self._usb_core.find(idVendor=vid, idProduct=pid)
        if dev is None:
            raise RuntimeError(f"DLCP not found (VID:PID = {vid:04X}:{pid:04X})")
        self.dev = dev
        self._prepare()

    def _prepare(self) -> None:
        try:
            self.dev.set_configuration()
        except self._usb_core.USBError:
            pass

    def _poke(self, addr: int, value: int, in_dir: bool, read_len: int = 0) -> bytes:
        if not (0 <= value <= 0xFF):
            raise ValueError(f"value out of range: 0x{value:02X}")

        bm = 0x80 if in_dir else 0x00  # standard + device recipient
        b_request = 0x0B
        w_value = value
        w_index = idx_for_addr(addr)
        try:
            if in_dir:
                data = self.dev.ctrl_transfer(bm, b_request, w_value, w_index, read_len)
                return bytes(data)
            self.dev.ctrl_transfer(bm, b_request, w_value, w_index, None)
            return b""
        except self._usb_core.USBError as exc:
            raise RuntimeError(
                f"USB control transfer failed: {exc}\n"
                "Try:\n"
                "  1) quit HFD and any app using DLCP USB\n"
                "  2) replug DLCP\n"
                "  3) run via sudo"
            ) from exc

    def set_pointer(self, addr16: int) -> None:
        lo = addr16 & 0xFF
        hi = (addr16 >> 8) & 0xFF
        self._poke(0x75, lo, in_dir=False)
        self._poke(0x76, hi, in_dir=False)

    def read_exact(self, n: int) -> bytes:
        if n <= 0:
            return b""
        # Keep EEPROM shadow dumps on the stable 0xE7 path as well.
        out = bytearray()
        remaining = n
        while remaining:
            chunk = min(remaining, 0xFF)
            data = self._poke(0xE7, chunk, in_dir=True, read_len=chunk)
            if len(data) != chunk:
                raise RuntimeError(f"short read: expected {chunk}, got {len(data)}")
            out.extend(data)
            remaining -= chunk
        return bytes(out)


def capture_ram(
    *,
    out_path: pathlib.Path,
    vid: int,
    pid: int,
    ram_start: int,
    ram_size: int,
    chunk: int,
) -> bytes:
    if ram_start < 0 or ram_start > 0x7FF:
        raise ValueError("ram_start must be in 0x000..0x7FF")
    if ram_size <= 0:
        raise ValueError("ram_size must be > 0")
    if ram_start + ram_size > 0x800:
        raise ValueError("RAM read window exceeds 0x000..0x7FF")
    if chunk <= 0:
        raise ValueError("chunk must be > 0")

    dev = DlcpEp0(vid=vid, pid=pid)
    dev.set_pointer(ram_start)

    out = bytearray()
    remaining = ram_size
    while remaining:
        n = min(chunk, remaining)
        out.extend(dev.read_exact(n))
        remaining -= n
        done = ram_size - remaining
        print(f"\rread 0x{done:03X}/0x{ram_size:03X}", end="", flush=True)
    print()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out)
    print(f"wrote {len(out)} bytes -> {out_path}")
    return bytes(out)


@dataclasses.dataclass(frozen=True)
class ShadowBinding:
    eeprom_addr: int
    ram_addr: int
    symbol: str


# Known boot-time EEPROM->RAM loads from main firmware function_007 (0x1E88).
SHADOW_BINDINGS: tuple[ShadowBinding, ...] = (
    ShadowBinding(0x00, 0x71, "cfg_00"),
    ShadowBinding(0x01, 0x70, "cfg_01"),
    ShadowBinding(0x02, 0x6F, "cfg_02"),
    ShadowBinding(0x03, 0x6E, "cfg_03"),
    ShadowBinding(0x04, 0x99, "cfg_04"),
    ShadowBinding(0x07, 0x60, "cfg_07"),
    ShadowBinding(0x08, 0x61, "cfg_08"),
    ShadowBinding(0x09, 0x62, "cfg_09"),
    ShadowBinding(0x0A, 0x63, "cfg_0A"),
    ShadowBinding(0x0B, 0x64, "cfg_0B"),
    ShadowBinding(0x0C, 0x65, "cfg_0C"),
    ShadowBinding(0x0D, 0x5F, "cfg_0D"),
    ShadowBinding(0x0E, 0xB8, "cfg_0E"),
    ShadowBinding(0x0F, 0xB4, "cfg_0F"),
    ShadowBinding(0x10, 0x9B, "cfg_10"),
    ShadowBinding(0x11, 0x9C, "cfg_11"),
    ShadowBinding(0x12, 0x9D, "cfg_12"),
    ShadowBinding(0x13, 0x9E, "cfg_13"),
    ShadowBinding(0x14, 0xC3, "cfg_14"),
)


def decode_shadow(ram: bytes, *, ram_start: int) -> list[dict[str, int | str]]:
    out: list[dict[str, int | str]] = []
    for b in SHADOW_BINDINGS:
        off = b.ram_addr - ram_start
        if 0 <= off < len(ram):
            value = ram[off]
            present = True
        else:
            value = -1
            present = False
        out.append(
            {
                "eeprom_addr": b.eeprom_addr,
                "ram_addr": b.ram_addr,
                "symbol": b.symbol,
                "present": int(present),
                "value": value,
            }
        )
    return out


def render_shadow_table(rows: list[dict[str, int | str]]) -> str:
    lines: list[str] = []
    lines.append("EEP  RAM  Value  Symbol")
    lines.append("---  ---  -----  ------")
    for r in rows:
        ee = int(r["eeprom_addr"])
        ra = int(r["ram_addr"])
        sym = str(r["symbol"])
        if int(r["present"]) == 0:
            val_s = "--"
        else:
            val_s = f"{int(r['value']) & 0xFF:02X}"
        lines.append(f"{ee:02X}   {ra:02X}   {val_s:>5}  {sym}")
    return "\n".join(lines)


def _cmd_capture(args: argparse.Namespace) -> int:
    ram = capture_ram(
        out_path=args.out,
        vid=args.vid,
        pid=args.pid,
        ram_start=args.ram_start,
        ram_size=args.ram_size,
        chunk=args.chunk,
    )
    rows = decode_shadow(ram, ram_start=args.ram_start)
    print()
    print(render_shadow_table(rows))

    if args.json_out is not None:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "vid": args.vid,
            "pid": args.pid,
            "ram_start": args.ram_start,
            "ram_size": args.ram_size,
            "ram_dump_path": str(args.out),
            "shadow_rows": rows,
            "note": (
                "Boot-loaded EEPROM shadow only (known function_007 bindings), "
                "not a guaranteed raw full EEPROM dump."
            ),
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="ascii")
        print(f"\nwrote json: {args.json_out}")
    return 0


def _cmd_decode(args: argparse.Namespace) -> int:
    ram = args.in_file.read_bytes()
    rows = decode_shadow(ram, ram_start=args.ram_start)
    print(render_shadow_table(rows))

    if args.json_out is not None:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "ram_start": args.ram_start,
            "ram_size": len(ram),
            "ram_dump_path": str(args.in_file),
            "shadow_rows": rows,
            "note": (
                "Boot-loaded EEPROM shadow only (known function_007 bindings), "
                "not a guaranteed raw full EEPROM dump."
            ),
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="ascii")
        print(f"\nwrote json: {args.json_out}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_cap = sub.add_parser("capture", help="capture RAM via EP0 primitive and decode EEPROM shadow")
    p_cap.add_argument("--vid", type=parse_int, default=VID_DEFAULT)
    p_cap.add_argument("--pid", type=parse_int, default=PID_DEFAULT)
    p_cap.add_argument("--ram-start", type=parse_int, default=0x000)
    p_cap.add_argument("--ram-size", type=parse_int, default=0x200)
    p_cap.add_argument("--chunk", type=parse_int, default=0x100)
    p_cap.add_argument("--out", type=pathlib.Path, required=True)
    p_cap.add_argument("--json-out", type=pathlib.Path, default=None)

    p_dec = sub.add_parser("decode", help="decode EEPROM shadow from existing RAM dump")
    p_dec.add_argument("--in", dest="in_file", type=pathlib.Path, required=True)
    p_dec.add_argument("--ram-start", type=parse_int, default=0x000)
    p_dec.add_argument("--json-out", type=pathlib.Path, default=None)

    return ap


def main() -> int:
    ap = _build_parser()
    args = ap.parse_args()
    if args.cmd == "capture":
        return _cmd_capture(args)
    if args.cmd == "decode":
        return _cmd_decode(args)
    raise SystemExit(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
