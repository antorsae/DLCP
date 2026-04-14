#!/usr/bin/env python3
"""
Targeted DLCP MAIN flash reader via the stock EP0 memory leak primitive.

This uses the same request path already exercised by the filename A/B probe,
but exposes a direct CLI for small flash windows so hardware checks do not
require a full dump workflow.
"""

from __future__ import annotations

import argparse
import json
import pathlib

from dlcp_fw.flash import dsp_filename_ab_probe as ep0


VID_DEFAULT = ep0.VID_DEFAULT
PID_DEFAULT = ep0.PID_DEFAULT


def parse_int(text: str) -> int:
    return ep0.parse_int(text)


def parse_span(text: str) -> tuple[int, int]:
    if ":" in text:
        start_s, size_s = text.split(":", 1)
        start = parse_int(start_s)
        size = parse_int(size_s)
        if size <= 0:
            raise ValueError("size must be > 0")
        return start, size

    if ".." in text:
        start_s, end_s = text.split("..", 1)
        start = parse_int(start_s)
        end = parse_int(end_s)
        if end < start:
            raise ValueError("end must be >= start")
        return start, (end - start) + 1

    raise ValueError("span must be START:SIZE or START..END")


def _validate_window(*, start: int, size: int, chunk: int) -> None:
    if start < 0 or start > 0xFFFF:
        raise ValueError("start must be in 0..0xFFFF")
    if size <= 0:
        raise ValueError("size must be > 0")
    end_excl = start + size
    if end_excl > 0x10000:
        raise ValueError("flash read exceeds 16-bit EP0 address window")
    if chunk <= 0:
        raise ValueError("chunk must be > 0")


def read_flash_window(
    *,
    vid: int,
    pid: int,
    path: bytes | None,
    start: int,
    size: int,
    chunk: int,
) -> bytes:
    _validate_window(start=start, size=size, chunk=chunk)

    dev = ep0.DlcpEp0(vid=vid, pid=pid, path=path)
    dev.set_pointer(start)

    out = bytearray()
    remaining = size
    while remaining:
        n = min(chunk, remaining)
        out.extend(dev.read_exact(n))
        remaining -= n
        done = size - remaining
        print(f"\rread 0x{done:04X}/0x{size:04X}", end="", flush=True)
    print()
    return bytes(out)


def _ascii(chunk: bytes) -> str:
    chars: list[str] = []
    for b in chunk:
        if 0x20 <= b <= 0x7E:
            chars.append(chr(b))
        else:
            chars.append(".")
    return "".join(chars)


def format_hexdump(start: int, data: bytes, *, width: int = 16) -> str:
    if width <= 0:
        raise ValueError("width must be > 0")
    lines: list[str] = []
    for off in range(0, len(data), width):
        chunk = data[off : off + width]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        lines.append(f"0x{start + off:04X}: {hex_part:<{width * 3 - 1}}  |{_ascii(chunk)}|")
    return "\n".join(lines)


def _cmd_read(args: argparse.Namespace) -> int:
    if args.list:
        print(json.dumps(ep0.list_matching_devices_json(args.vid, args.pid), indent=2))
        return 0
    if args.span is not None:
        start, size = parse_span(args.span)
    else:
        start = args.start
        size = args.size

    data = read_flash_window(
        vid=args.vid,
        pid=args.pid,
        path=args.path.encode("utf-8") if args.path is not None else None,
        start=start,
        size=size,
        chunk=args.chunk,
    )

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(data)
        print(f"wrote {len(data)} bytes -> {args.out}")

    print(format_hexdump(start, data, width=args.width))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read MAIN flash/RAM windows through the stock DLCP USB EP0 leak "
            "primitive. This targets the MAIN MCU application path, not the "
            "control bootloader."
        )
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    read_p = sub.add_parser("read", help="read and hexdump a flash window")
    read_p.add_argument(
        "--span",
        help="window as START:SIZE or START..END, e.g. 0x561C:0x14 or 0x561C..0x562F",
    )
    read_p.add_argument("--start", type=parse_int, help="start address (hex or decimal)")
    read_p.add_argument("--size", type=parse_int, help="size in bytes (hex or decimal)")
    read_p.add_argument("--out", type=pathlib.Path, help="optional raw output path")
    read_p.add_argument("--chunk", type=parse_int, default=0xFF, help="read chunk size")
    read_p.add_argument("--width", type=int, default=16, help="hexdump bytes per line")
    read_p.add_argument("--vid", type=parse_int, default=VID_DEFAULT, help="USB vendor ID")
    read_p.add_argument("--pid", type=parse_int, default=PID_DEFAULT, help="USB product ID")
    read_p.add_argument("--path", default=None, help="explicit HID path (UTF-8 text)")
    read_p.add_argument("--list", action="store_true", help="list matching HID devices and exit")
    read_p.set_defaults(func=_cmd_read)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "read" and args.span is None and not args.list:
        if args.start is None or args.size is None:
            parser.error("read requires either --span or both --start and --size")

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
