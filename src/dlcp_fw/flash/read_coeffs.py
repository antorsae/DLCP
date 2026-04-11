#!/usr/bin/env python3
"""Read V3.1 diagnostic preset tables and EEPROM filenames over USB HID."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import time

from dlcp_fw.flash.dlcp_control_flash import (
    DEFAULT_PID as PID_DEFAULT,
    DEFAULT_VID as VID_DEFAULT,
    HidDeviceInfo,
    _hid_read64,
    _hid_write64,
    enumerate_devices,
)
from dlcp_fw.flash.dlcp_main_flash import (
    _device_mode,
    _print_device_snapshot,
    _probe_device_snapshot,
)


CMD_DIAG_MEMREAD = 0x43
REGION_FLASH = 0x00
REGION_EEPROM = 0x01

TABLE_SIZE = 0x0A00
NAME_LEN = 0x1E
MAX_CHUNK = 0x3D

PRESET_FLASH_BASE = {
    "A": 0x5600,
    "B": 0x4C00,
}
PRESET_NAME_EEPROM_BASE = {
    "A": 0x60,
    "B": 0x83,
}


def _parse_int_auto(s: str) -> int:
    return int(s, 0)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path_text(path: bytes | None) -> str:
    if path is None:
        return "<no-path>"
    return path.decode("utf-8", errors="replace")


def _status_name(status: int) -> str:
    return {
        0x00: "ok",
        0x01: "bad-region",
        0x02: "bad-length",
    }.get(status & 0xFF, f"0x{status & 0xFF:02X}")


def _sanitize_stem(name: str, preset: str) -> str:
    out: list[str] = []
    for ch in name.strip():
        if ch.isalnum() or ch in "._-":
            out.append(ch)
        elif ch == " ":
            out.append("_")
    stem = "".join(out).strip("._-")
    if stem:
        return stem
    return f"preset_{preset.lower()}"


def decode_config_name(raw: bytes) -> str:
    seen_pad = False
    chars: list[int] = []
    for idx, b in enumerate(raw):
        bb = b & 0xFF
        if bb in (0x00, 0xFF):
            seen_pad = True
            continue
        if not (0x20 <= bb <= 0x7E):
            raise ValueError(f"non-ASCII EEPROM byte at offset {idx}: 0x{bb:02X}")
        if seen_pad:
            raise ValueError(
                f"non-padding byte after EEPROM padding at offset {idx}: 0x{bb:02X}"
            )
        chars.append(bb)
    return bytes(chars).decode("ascii")


def encode_name_slot(name: str) -> bytes:
    raw = name.encode("ascii", errors="strict")[:NAME_LEN]
    return raw + (b"\xFF" * (NAME_LEN - len(raw)))


@dataclasses.dataclass(frozen=True)
class CaptureResult:
    preset: str
    table: bytes
    flash_base: int
    eeprom_base: int
    name_slot: bytes
    config_name: str

    @property
    def table_sha256(self) -> str:
        return _sha256_hex(self.table)


def _list_devices_with_mode(vid: int, pid: int) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for dev in enumerate_devices(vid, pid):
        out.append(
            {
                "vendor_id": dev.vendor_id,
                "product_id": dev.product_id,
                "path": _path_text(dev.path),
                "manufacturer_string": dev.manufacturer_string,
                "product_string": dev.product_string,
                "serial_number": dev.serial_number,
                "mode": _device_mode(dev),
            }
        )
    return out


def _pick_device(vid: int, pid: int, path: bytes | None) -> HidDeviceInfo:
    devs = enumerate_devices(vid, pid)
    if path is not None:
        for dev in devs:
            if dev.path == path:
                return dev
        raise RuntimeError("requested HID path was not found among matching devices")
    if not devs:
        raise RuntimeError(f"no HID device found for VID:PID {vid:04X}:{pid:04X}")
    if len(devs) > 1:
        raise RuntimeError(
            f"multiple HID devices match {vid:04X}:{pid:04X}; use --list and pass --path"
        )
    return devs[0]


def _parse_diag_memread_response(resp: bytes, *, length: int) -> bytes:
    if len(resp) != 64:
        raise RuntimeError(f"short HID response: {len(resp)} bytes")
    if resp[0] != CMD_DIAG_MEMREAD:
        raise RuntimeError(
            f"unexpected command echo: 0x{resp[0]:02X} "
            "(expected 0x43; device may not be running the diag memread firmware)"
        )
    status = resp[1]
    if status != 0:
        raise RuntimeError(f"device returned {_status_name(status)} for read request")
    if resp[2] != length:
        raise RuntimeError(f"device echoed length {resp[2]}, expected {length}")
    return bytes(resp[3 : 3 + length])


class HidMemoryReader:
    def __init__(
        self,
        *,
        info: HidDeviceInfo,
        timeout_ms: int,
    ) -> None:
        self._timeout_ms = timeout_ms
        self.info = info
        try:
            import hid
        except ImportError as exc:
            raise RuntimeError(
                "python-hidapi is required. Install with: python3 -m pip install hidapi"
            ) from exc
        self._hid = hid
        self._dev = hid.device()
        if info.path is None:
            raise RuntimeError("selected HID device has no path")
        self._dev.open_path(info.path)
        self._dev.set_nonblocking(False)

    @property
    def path_text(self) -> str:
        return _path_text(self.info.path)

    def close(self) -> None:
        self._dev.close()

    def __enter__(self) -> "HidMemoryReader":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _exchange(self, report: bytes) -> bytes:
        if len(report) != 64:
            raise ValueError("report must be exactly 64 bytes")
        _hid_write64(self._dev, report)
        deadline = time.monotonic() + (max(1, self._timeout_ms) / 1000.0)
        ignored: list[int] = []
        while True:
            remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
            if remaining_ms <= 0:
                if ignored:
                    ignored_text = ", ".join(f"0x{x:02X}" for x in ignored[:8])
                    raise RuntimeError(
                        "timed out waiting for diag memread response after ignoring "
                        f"{len(ignored)} unrelated HID report(s): {ignored_text}"
                    )
                raise RuntimeError("timed out waiting for HID response")
            resp = _hid_read64(self._dev, timeout_ms=remaining_ms)
            if resp is None:
                if ignored:
                    ignored_text = ", ".join(f"0x{x:02X}" for x in ignored[:8])
                    raise RuntimeError(
                        "timed out waiting for diag memread response after ignoring "
                        f"{len(ignored)} unrelated HID report(s): {ignored_text}"
                    )
                raise RuntimeError("timed out waiting for HID response")
            if len(resp) == 64 and resp[0] == CMD_DIAG_MEMREAD:
                return resp
            first = resp[0] if resp else -1
            ignored.append(first & 0xFF)

    def read_chunk(self, *, region: int, addr: int, length: int) -> bytes:
        if not (0 <= region <= 1):
            raise ValueError("region must be 0 (flash) or 1 (EEPROM)")
        if not (0 <= addr <= 0xFFFF):
            raise ValueError("addr must be in 0..0xFFFF")
        if not (1 <= length <= MAX_CHUNK):
            raise ValueError(f"length must be in 1..{MAX_CHUNK}")

        report = bytearray(64)
        report[0] = CMD_DIAG_MEMREAD
        report[1] = region & 0xFF
        report[2] = addr & 0xFF
        report[3] = (addr >> 8) & 0xFF
        report[4] = length & 0xFF

        resp = self._exchange(bytes(report))
        return _parse_diag_memread_response(resp, length=length)

    def read_window_verified(
        self,
        *,
        region: int,
        addr: int,
        size: int,
        verify_reads: int,
        retries: int,
        delay_s: float,
    ) -> bytes:
        out = bytearray()
        remaining = size
        cursor = addr
        done = 0
        while remaining:
            chunk = min(MAX_CHUNK, remaining)
            stable: bytes | None = None
            for attempt in range(retries):
                reads = [
                    self.read_chunk(region=region, addr=cursor, length=chunk)
                    for _ in range(max(1, verify_reads))
                ]
                first = reads[0]
                if all(candidate == first for candidate in reads[1:]):
                    stable = first
                    break
                time.sleep(delay_s)
            if stable is None:
                raise RuntimeError(
                    f"unable to stabilize chunk at 0x{cursor:04X} after {retries} retries"
                )
            out.extend(stable)
            cursor += chunk
            remaining -= chunk
            done += chunk
            print(f"\rread 0x{done:04X}/0x{size:04X}", end="", flush=True)
        print()
        return bytes(out)


def capture_preset(
    *,
    reader: HidMemoryReader,
    preset: str,
    verify_reads: int,
    retries: int,
    delay_s: float,
) -> CaptureResult:
    flash_base = PRESET_FLASH_BASE[preset]
    eeprom_base = PRESET_NAME_EEPROM_BASE[preset]
    table = reader.read_window_verified(
        region=REGION_FLASH,
        addr=flash_base,
        size=TABLE_SIZE,
        verify_reads=verify_reads,
        retries=retries,
        delay_s=delay_s,
    )
    name_slot = reader.read_window_verified(
        region=REGION_EEPROM,
        addr=eeprom_base,
        size=NAME_LEN,
        verify_reads=verify_reads,
        retries=retries,
        delay_s=delay_s,
    )
    return CaptureResult(
        preset=preset,
        table=table,
        flash_base=flash_base,
        eeprom_base=eeprom_base,
        name_slot=name_slot,
        config_name=decode_config_name(name_slot),
    )


def _metadata_path_for(bin_path: Path) -> Path:
    return bin_path.with_suffix(".json")


def _write_capture(bin_path: Path, result: CaptureResult) -> Path:
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.write_bytes(result.table)
    meta = {
        "format": "dlcp_preset_capture_v1",
        "preset": result.preset,
        "flash_base": result.flash_base,
        "eeprom_base": result.eeprom_base,
        "table_size": len(result.table),
        "table_sha256": result.table_sha256,
        "config_name": result.config_name,
        "config_name_raw_hex": result.name_slot.hex(),
    }
    meta_path = _metadata_path_for(bin_path)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="ascii")
    return meta_path


def _default_output_path(result: CaptureResult) -> Path:
    stem = _sanitize_stem(result.config_name, result.preset)
    return Path(f"{stem}.bin")


def _cmd_capture(args: argparse.Namespace) -> int:
    preset = args.preset.upper()
    info = _pick_device(args.vid, args.pid, args.path)
    if not args.no_banner:
        _print_device_snapshot(
            "device info:",
            _probe_device_snapshot(info=info, vid=args.vid, pid=args.pid),
        )
        print(f"  hid path: {_path_text(info.path)}")
        print(f"capture preset {preset}:")
        print(f"  flash base: 0x{PRESET_FLASH_BASE[preset]:04X}")
        print(f"  eeprom base: 0x{PRESET_NAME_EEPROM_BASE[preset]:02X}")

    with HidMemoryReader(info=info, timeout_ms=args.timeout_ms) as reader:
        result = capture_preset(
            reader=reader,
            preset=preset,
            verify_reads=args.verify_reads,
            retries=args.retries,
            delay_s=args.retry_delay_ms / 1000.0,
        )

    if args.check is not None:
        want = args.check.read_bytes()
        if len(want) != TABLE_SIZE:
            raise RuntimeError(f"{args.check} has {len(want)} bytes, expected {TABLE_SIZE}")
        if want != result.table:
            for idx, (got, exp) in enumerate(zip(result.table, want)):
                if got != exp:
                    raise RuntimeError(
                        f"check failed at offset 0x{idx:04X}: got 0x{got:02X}, expected 0x{exp:02X}"
                    )
            raise RuntimeError("check failed: table bytes differ")
        print(f"check passed: {args.check}")
        print(f"config name: {result.config_name!r}")
        print(f"table sha256: {result.table_sha256}")
        return 0

    out_path = args.out if args.out is not None else _default_output_path(result)
    meta_path = _write_capture(out_path, result)
    print(f"wrote table: {out_path}")
    print(f"wrote metadata: {meta_path}")
    print(f"config name: {result.config_name!r}")
    print(f"table sha256: {result.table_sha256}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read preset DSP tables and EEPROM config names from the V3.1 "
            "diagnostic HID memory-read command."
        )
    )
    parser.add_argument("--preset", required=False, choices=("A", "B", "a", "b"))
    parser.add_argument("--list", action="store_true", help="list matching HID devices and exit")
    parser.add_argument("--out", type=Path, default=None, help="raw table output path")
    parser.add_argument("--check", type=Path, default=None, help="compare current read against this raw table")
    parser.add_argument("--verify-reads", type=int, default=2, help="reads per chunk before accepting data")
    parser.add_argument("--retries", type=int, default=5, help="retry attempts per chunk")
    parser.add_argument("--retry-delay-ms", type=int, default=25, help="delay between unstable chunk retries")
    parser.add_argument("--timeout-ms", type=int, default=1000, help="HID read timeout per report")
    parser.add_argument("--vid", type=_parse_int_auto, default=VID_DEFAULT)
    parser.add_argument("--pid", type=_parse_int_auto, default=PID_DEFAULT)
    parser.add_argument(
        "--path",
        type=lambda s: s.encode("utf-8"),
        default=None,
        help="optional hidapi path string",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="skip default device info banner and selected HID path reporting",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        print(json.dumps(_list_devices_with_mode(args.vid, args.pid), indent=2))
        return 0
    if not args.preset:
        raise SystemExit("--preset is required unless --list is used")
    return _cmd_capture(args)


if __name__ == "__main__":
    raise SystemExit(main())
