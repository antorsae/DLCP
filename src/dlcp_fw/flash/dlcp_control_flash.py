#!/usr/bin/env python3
"""
Flash DLCP Control firmware *through the main DLCP USB HID* using the main
firmware's command 0x42 relay (binary -> Intel HEX -> current-loop UART).

Reverse-engineered from main firmware disassembly:
  - cmd 0x42: init/update + stream data (30 bytes per HID report at offsets 2..31)
  - cmd 0x41: CRC verify (expected CRC bytes at offsets 4..5: [hi, lo])
  - end-of-file: send one 0x42 report with all-zero payload (0x000000.. record)

This tool intentionally only touches CONTROL application flash (0x0040..0x77BF).

Tested environment expectations (macOS):
  - python-hidapi (module name: hid)
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional

from dlcp_fw.paths import STOCK_CONTROL_HEX_V14


DEFAULT_VID = 0x04D8
DEFAULT_PID = 0xFF89  # main DLCP USB device

# CONTROL bootloader write window (per control bootloader disasm)
CONTROL_PROG_END_EXCL = 0x77C0  # last writable byte is 0x77BF
CONTROL_BOOT_START = 0x7800
CONTROL_BOOT_END_EXCL = 0x8000  # inclusive last byte: 0x7FFF
DEFAULT_BOOTLOADER_REF = STOCK_CONTROL_HEX_V14


class HexParseError(RuntimeError):
    pass


class PreflightError(RuntimeError):
    pass


def _parse_int_auto(s: str) -> int:
    s = s.strip().lower()
    if s.startswith("0x"):
        return int(s, 16)
    return int(s, 10)


def parse_intel_hex(path: str) -> Dict[int, int]:
    """
    Minimal Intel HEX parser.

    Returns a dict: absolute_byte_address -> value(0..255)
    Supports record types 00 (data), 01 (EOF), 04 (extended linear address).
    """
    mem: Dict[int, int] = {}
    upper = 0

    def parse_byte(h: str) -> int:
        try:
            return int(h, 16)
        except ValueError as e:
            raise HexParseError(f"bad hex byte {h!r} in {path}") from e

    with open(path, "r", encoding="ascii", errors="strict") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise HexParseError(f"{path}:{lineno}: missing ':'")
            if len(line) < 11:
                raise HexParseError(f"{path}:{lineno}: line too short")

            # :LLAAAATT[DD..]CC
            ll = parse_byte(line[1:3])
            aaaa = int(line[3:7], 16)
            rtype = parse_byte(line[7:9])
            data_hex = line[9 : 9 + ll * 2]
            cc = parse_byte(line[9 + ll * 2 : 11 + ll * 2])

            # Verify checksum (optional but cheap)
            total = ll + ((aaaa >> 8) & 0xFF) + (aaaa & 0xFF) + rtype
            data: List[int] = []
            for i in range(0, len(data_hex), 2):
                b = parse_byte(data_hex[i : i + 2])
                data.append(b)
                total += b
            total &= 0xFF
            calc = (~total + 1) & 0xFF
            if calc != cc:
                raise HexParseError(
                    f"{path}:{lineno}: checksum mismatch (got 0x{cc:02x}, want 0x{calc:02x})"
                )

            if rtype == 0x00:
                base = (upper << 16) | aaaa
                for i, b in enumerate(data):
                    mem[base + i] = b
            elif rtype == 0x01:
                break
            elif rtype == 0x04:
                if ll != 2:
                    raise HexParseError(f"{path}:{lineno}: type 04 with ll={ll}")
                upper = (data[0] << 8) | data[1]
            else:
                # Ignore other record types (02/03/05 etc)
                continue

    return mem


def build_control_stream(hex_mem: Dict[int, int], length: int = CONTROL_PROG_END_EXCL) -> bytes:
    """
    Build the byte stream that the main firmware's 0x42 relay expects:
      - sequential bytes from address 0x0000 up to 0x77BF inclusive
      - fill gaps with 0xFF
      - ignore non-program regions (config words, EEPROM, etc)
    """
    out = bytearray([0xFF] * length)
    for addr, b in hex_mem.items():
        # Program memory is upper == 0, addr < 0x8000 for control
        if 0 <= addr < length:
            out[addr] = b & 0xFF
    return bytes(out)


def _region_bytes(mem: Dict[int, int], start: int, end_excl: int) -> bytes:
    out = bytearray(end_excl - start)
    for addr in range(start, end_excl):
        out[addr - start] = mem.get(addr, 0xFF) & 0xFF
    return bytes(out)


def bootloader_mismatch_addresses(candidate_mem: Dict[int, int], reference_mem: Dict[int, int]) -> List[int]:
    mismatches: List[int] = []
    for addr in range(CONTROL_BOOT_START, CONTROL_BOOT_END_EXCL):
        if (candidate_mem.get(addr, 0xFF) & 0xFF) != (reference_mem.get(addr, 0xFF) & 0xFF):
            mismatches.append(addr)
    return mismatches


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_preflight(
    *,
    hex_mem: Dict[int, int],
    bootloader_ref_mem: Optional[Dict[int, int]],
    require_bootloader_match: bool,
) -> Dict[str, object]:
    control_window = _region_bytes(hex_mem, 0x0000, CONTROL_PROG_END_EXCL)
    app_window = _region_bytes(hex_mem, 0x0040, CONTROL_PROG_END_EXCL)
    boot_window = _region_bytes(hex_mem, CONTROL_BOOT_START, CONTROL_BOOT_END_EXCL)

    result: Dict[str, object] = {
        "payload_len": len(control_window),
        "payload_crc": crc_stream(control_window),
        "payload_sha256": _sha256_hex(control_window),
        "app_sha256": _sha256_hex(app_window),
        "boot_sha256": _sha256_hex(boot_window),
    }

    if require_bootloader_match:
        if bootloader_ref_mem is None:
            raise PreflightError("bootloader check requested but no reference HEX was provided")
        mismatches = bootloader_mismatch_addresses(hex_mem, bootloader_ref_mem)
        if mismatches:
            preview = ", ".join(
                f"0x{a:04X}(got=0x{hex_mem.get(a, 0xFF):02X},ref=0x{bootloader_ref_mem.get(a, 0xFF):02X})"
                for a in mismatches[:8]
            )
            raise PreflightError(
                "bootloader bytes differ from reference in "
                f"{len(mismatches)} locations within 0x{CONTROL_BOOT_START:04X}..0x{CONTROL_BOOT_END_EXCL-1:04X}; "
                f"first diffs: {preview}"
            )
        result["bootloader_match"] = True

    return result


def crc_update_pic18_style(crc: int, b: int) -> int:
    """
    Reproduce the main firmware's update CRC as implemented in function_003.

    State:
      crc is 16-bit (0x7D:0x7C), init 0x0000
    Per data byte:
      - process 8 times:
        * feedback = bit5 of crc_high (overall bit13) BEFORE shift
        * shift crc left by 1
        * shift in data bit0 into crc bit0 (LSB), then shift data right by 1
        * if feedback: crc ^= 0x4402
    """
    crc &= 0xFFFF
    b &= 0xFF
    for _ in range(8):
        crc_high = (crc >> 8) & 0xFF
        feedback = 1 if (crc_high & 0x20) else 0  # bit5 of high byte
        # shift crc left by 1
        crc = ((crc << 1) & 0xFFFF)
        # shift in next data bit (LSB-first)
        if b & 0x01:
            crc |= 0x0001
        b >>= 1
        if feedback:
            crc ^= 0x4402
    return crc & 0xFFFF


def crc_stream(data: bytes) -> int:
    crc = 0
    for b in data:
        crc = crc_update_pic18_style(crc, b)
    return crc


def _find_default_device_path(vid: int, pid: int) -> Optional[bytes]:
    import hid

    for d in hid.enumerate():
        if d.get("vendor_id") == vid and d.get("product_id") == pid:
            # Prefer an interface that looks like HID (some platforms expose multiple)
            p = d.get("path")
            if p is not None:
                return p
    return None


@dataclasses.dataclass(frozen=True)
class HidDeviceInfo:
    vendor_id: int
    product_id: int
    path: Optional[bytes]
    manufacturer_string: str
    product_string: str
    serial_number: str


def enumerate_devices(vid: int, pid: int) -> List[HidDeviceInfo]:
    import hid

    out: List[HidDeviceInfo] = []
    for d in hid.enumerate():
        if vid is not None and d.get("vendor_id") != vid:
            continue
        if pid is not None and d.get("product_id") != pid:
            continue
        out.append(
            HidDeviceInfo(
                vendor_id=d.get("vendor_id") or 0,
                product_id=d.get("product_id") or 0,
                path=d.get("path"),
                manufacturer_string=d.get("manufacturer_string") or "",
                product_string=d.get("product_string") or "",
                serial_number=d.get("serial_number") or "",
            )
        )
    return out


def _hid_write64(dev, payload64: bytes) -> None:
    if len(payload64) != 64:
        raise ValueError("payload must be exactly 64 bytes")
    # hidapi expects report id prefix (0x00) on macOS even when no report IDs exist.
    buf = bytes([0x00]) + payload64
    n = dev.write(buf)
    if n != len(buf):
        raise RuntimeError(f"hid write short: wrote {n} bytes (expected {len(buf)})")


def _hid_read64(dev, timeout_ms: int = 1000) -> Optional[bytes]:
    data = dev.read(64, timeout_ms)
    if not data:
        return None
    b = bytes(data)
    # Some stacks include report ID, some don't.
    if len(b) == 65 and b[0] == 0x00:
        return b[1:]
    if len(b) == 64:
        return b
    # Best effort: trim/pad
    if len(b) > 64:
        return b[-64:]
    return b.ljust(64, b"\x00")


def _mk_report(cmd: int) -> bytearray:
    r = bytearray(64)
    r[0] = cmd & 0xFF
    return r


def flash_control(
    *,
    vid: int,
    pid: int,
    path: Optional[bytes],
    stream: bytes,
    pace_ms: int,
    init_delay_ms: int,
    verify: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    if len(stream) != CONTROL_PROG_END_EXCL:
        raise ValueError(f"stream must be {CONTROL_PROG_END_EXCL} bytes, got {len(stream)}")

    expected_crc = crc_stream(stream)
    exp_hi = (expected_crc >> 8) & 0xFF
    exp_lo = expected_crc & 0xFF

    if verbose or dry_run:
        print(f"control stream: {len(stream)} bytes (0x0000..0x{CONTROL_PROG_END_EXCL-1:04X})")
        print(f"expected CRC: 0x{expected_crc:04X} (report[4]=0x{exp_hi:02X}, report[5]=0x{exp_lo:02X})")

    if dry_run:
        return

    import hid

    dev = hid.device()
    if path is None:
        path = _find_default_device_path(vid, pid)
        if path is None:
            raise RuntimeError(f"no HID device found for VID:PID {vid:04x}:{pid:04x}")
    dev.open_path(path)
    dev.set_nonblocking(False)

    try:
        # 1) init update mode
        if verbose:
            print("sending init (0x42)...")
        r = _mk_report(0x42)
        _hid_write64(dev, bytes(r))
        time.sleep(init_delay_ms / 1000.0)

        # 2) stream bytes (30 per report at offsets 2..31)
        total = len(stream)
        pos = 0
        report_i = 0
        last_print = time.time()

        while pos < total:
            chunk = stream[pos : pos + 30]
            if len(chunk) < 30:
                chunk = chunk + bytes([0xFF]) * (30 - len(chunk))

            r = _mk_report(0x42)
            r[2 : 2 + 30] = chunk
            _hid_write64(dev, bytes(r))

            pos += 30
            report_i += 1

            if pace_ms:
                time.sleep(pace_ms / 1000.0)

            if verbose and (time.time() - last_print) > 0.5:
                pct = min(100.0, (pos / total) * 100.0)
                print(f"streaming: report={report_i} pos=0x{pos:04X}/{total:04X} ({pct:5.1f}%)")
                last_print = time.time()

        # 3) CRC verify (recommended before EOF/reset)
        if verify:
            if verbose:
                print("sending CRC verify (0x41)...")
            r = _mk_report(0x41)
            r[4] = exp_hi
            r[5] = exp_lo
            _hid_write64(dev, bytes(r))

            resp = _hid_read64(dev, timeout_ms=2000)
            if resp is None:
                raise RuntimeError("no response to CRC verify (0x41)")

            # Main firmware sets response byte at 0x15C to 0xAA on success.
            # 0x15A is response[0], so 0x15C is response[2].
            ok = resp[2] == 0xAA
            if verbose:
                print("verify resp[0..7] =", " ".join(f"{x:02x}" for x in resp[:8]))
            if not ok:
                raise RuntimeError(f"CRC verify failed (resp[2]=0x{resp[2]:02X}, expected 0xAA)")

            if verbose:
                print("CRC verify OK.")

        # 4) EOF record trigger: one 0x42 report with all-zero payload.
        # This should make the main send an Intel HEX ":00000001FF" to the CONTROL bootloader.
        if verbose:
            print("sending EOF trigger (0x42 all-zero payload)...")
        r = _mk_report(0x42)
        _hid_write64(dev, bytes(r))
        time.sleep(0.5)
    finally:
        try:
            dev.close()
        except Exception:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vid", type=_parse_int_auto, default=DEFAULT_VID, help="USB VID (default: 0x04D8)")
    ap.add_argument("--pid", type=_parse_int_auto, default=DEFAULT_PID, help="USB PID (default: 0xFF89)")
    ap.add_argument("--path", type=str, default="", help="hidapi path (advanced; leave empty to auto-pick)")
    ap.add_argument("--list", action="store_true", help="list matching HID devices and exit")
    ap.add_argument("--hex", type=str, default="", help="control firmware .hex (Intel HEX)")
    ap.add_argument(
        "--bootloader-ref",
        type=str,
        default=str(DEFAULT_BOOTLOADER_REF),
        help="trusted reference HEX used for bootloader integrity check (default: stock V1.4)",
    )
    ap.add_argument(
        "--skip-bootloader-check",
        action="store_true",
        help="unsafe: skip bootloader integrity preflight",
    )
    ap.add_argument(
        "--preflight-only",
        action="store_true",
        help="run safety checks and print checksums/CRC; do not write over USB",
    )
    ap.add_argument("--pace-ms", type=int, default=75, help="sleep after each 0x42 report (default: 75ms)")
    ap.add_argument("--init-delay-ms", type=int, default=1500, help="wait after init 0x42 (default: 1500ms)")
    ap.add_argument("--no-verify", action="store_true", help="unsafe: skip CRC verify command (0x41)")
    ap.add_argument(
        "--force-unsafe",
        action="store_true",
        help="required to use unsafe flags (--no-verify and/or --skip-bootloader-check)",
    )
    ap.add_argument("--dry-run", action="store_true", help="parse/prepare only, no USB writes")
    ap.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    args = ap.parse_args(argv)

    if args.list:
        devs = enumerate_devices(args.vid, args.pid)
        print(json.dumps([dataclasses.asdict(d) for d in devs], indent=2, default=str))
        return 0

    if not args.hex:
        ap.error("--hex is required (control firmware Intel HEX)")
    if (args.no_verify or args.skip_bootloader_check) and not args.force_unsafe:
        ap.error("--no-verify and --skip-bootloader-check require --force-unsafe")

    hex_mem = parse_intel_hex(args.hex)
    ref_mem: Optional[Dict[int, int]] = None
    if not args.skip_bootloader_check:
        ref_path = Path(args.bootloader_ref)
        if not ref_path.exists():
            ap.error(f"bootloader reference HEX not found: {ref_path}")
        ref_mem = parse_intel_hex(str(ref_path))

    preflight = run_preflight(
        hex_mem=hex_mem,
        bootloader_ref_mem=ref_mem,
        require_bootloader_match=not args.skip_bootloader_check,
    )
    if args.verbose or args.preflight_only or args.dry_run:
        print("preflight: OK")
        print(
            "  payload window: 0x0000..0x"
            f"{CONTROL_PROG_END_EXCL - 1:04X} ({preflight['payload_len']} bytes)"
        )
        print(f"  payload crc16: 0x{preflight['payload_crc']:04X}")
        print(f"  payload sha256: {preflight['payload_sha256']}")
        print(f"  app sha256:     {preflight['app_sha256']}")
        print(f"  boot sha256:    {preflight['boot_sha256']}")
        if not args.skip_bootloader_check:
            print(
                "  bootloader match:"
                f" 0x{CONTROL_BOOT_START:04X}..0x{CONTROL_BOOT_END_EXCL - 1:04X} == {args.bootloader_ref}"
            )

    stream = build_control_stream(hex_mem)

    path: Optional[bytes] = None
    if args.path:
        # Allow either raw bytes escaped (not practical) or a hex string.
        # Most users should just omit --path.
        path = args.path.encode("utf-8")

    flash_control(
        vid=args.vid,
        pid=args.pid,
        path=path,
        stream=stream,
        pace_ms=max(0, args.pace_ms),
        init_delay_ms=max(0, args.init_delay_ms),
        verify=not args.no_verify,
        dry_run=args.dry_run or args.preflight_only,
        verbose=args.verbose,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
