#!/usr/bin/env python3
"""
Flash DLCP MAIN application firmware through the recovered MAIN USB HID
bootloader protocol used by HFD.

Recovered behavior:
  - Running app command 0x40 writes EEPROM[0xFF] = 0 and resets into bootloader.
  - Bootloader accepts 0x40 stream packets carrying 30 raw app bytes at offsets 2..31.
  - Bootloader app write window is 0x1000..0x5FFF inclusive.
  - Bootloader finalizes with 0x41, comparing payload[4:6] against its CRC and
    returning status 0xAA on success.

This tool intentionally only streams MAIN application flash. Boot block, config,
EEPROM, and User ID bytes present in Intel HEX input are ignored by the device.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import time
from typing import Dict, List, Optional

from dlcp_fw.flash.dlcp_control_flash import (
    DEFAULT_PID,
    DEFAULT_VID,
    HidDeviceInfo,
    PreflightError,
    _hid_read64,
    _hid_write64,
    _mk_report,
    crc_stream,
    enumerate_devices,
    parse_intel_hex,
)
from dlcp_fw.flash.dlcp_ep0_eeprom_shadow_dump import DlcpEp0
from dlcp_fw.paths import STOCK_MAIN_COMBINED_HEX


MAIN_BOOT_END_EXCL = 0x1000
MAIN_APP_START = 0x1000
MAIN_PROG_END_EXCL = 0x6000
DEFAULT_BOOTLOADER_REF = STOCK_MAIN_COMBINED_HEX
BOOTLOADER_PRODUCT_TOKEN = "bootl"
CMD06_VERSION_SUBCMD = 0x01
CMD03_FILENAME_READ_SUBCMD = 0x08
CMD03_FILENAME_WRITE_SUBCMD = 0x09
CMD03_FILENAME_ERASE_SUBCMD = 0x0A
FILENAME_RAM_BASE = 0x2C0
FILENAME_LEN = 0x1E
PRESET_A_FLASH_BASE = 0x5600
PRESET_B_FLASH_BASE = 0x4C00
PRESET_B_FLASH_BASE_V24_TO_V28 = 0x4A00
PRESET_B_FLASH_BASE_V31_PLUS = PRESET_B_FLASH_BASE
PRESET_TABLE_SIZE = 0x0A00
ROUTE_RAM_BASE = 0x60
ROUTE_LEN = 0x06
ROUTE_SOURCE_RAM_BASE = 0x0A5
EVENT_FLAGS_ADDR = 0x07E
ROUTE_DIRTY_FLAGS_ADDR = 0x0BD
ACTIVE_FLAGS_ADDR = 0x05E
ACTIVE_PRESET_MASK = 0x04
ACTIVE_REAPPLY_MASK = 0x80
EVENT_DIRTY_SERVICE_MASK = 0x01
EVENT_ROUTE_APPLY_MASK = 0x10
EEPROM_ROUTE_DIRTY_MASK = 0x02
FILENAME_DIRTY_MASK = 0x20
PRESET_FLASH_BASES = {
    "A": PRESET_A_FLASH_BASE,
}
ROUTE_LABELS = {
    0: "L",
    1: "R",
    2: "L+R",
    3: "L-R",
    4: "R-L",
}
ALL_CH_ROUTE_VALUES = {
    "L": 0,
    "R": 1,
}


def _parse_int_auto(s: str) -> int:
    return int(s, 0)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _encode_name_slot(name: str) -> bytes:
    raw = name.encode("ascii", errors="strict")[:FILENAME_LEN]
    return raw + (b"\xFF" * (FILENAME_LEN - len(raw)))


def _region_bytes(mem: Dict[int, int], start: int, end_excl: int) -> bytes:
    out = bytearray(end_excl - start)
    for addr in range(start, end_excl):
        out[addr - start] = mem.get(addr, 0xFF) & 0xFF
    return bytes(out)


def _count_explicit(mem: Dict[int, int], start: int, end_excl: int) -> int:
    return sum(1 for addr in mem if start <= addr < end_excl)


@dataclasses.dataclass(frozen=True)
class VersionInfo:
    flag: int
    major: int
    minor: int


@dataclasses.dataclass(frozen=True)
class RouteEntry:
    channel: int
    value: int
    label: str


@dataclasses.dataclass(frozen=True)
class DeviceSnapshot:
    mode: str
    product_string: str
    manufacturer_string: str
    serial_number: str
    version: Optional[VersionInfo]
    active_config_name: Optional[str]
    active_config_raw: Optional[bytes]
    active_routes: Optional[tuple[RouteEntry, ...]]
    warnings: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class CaptureOverlay:
    preset: str
    table: bytes
    name_slot: bytes
    config_name: str
    flash_base: int


def detect_static_hex_hid_version(hex_mem: Dict[int, int]) -> Optional[VersionInfo]:
    for addr in range(MAIN_APP_START, PRESET_A_FLASH_BASE, 2):
        if (
            hex_mem.get(addr + 1, 0xFF) == 0x0E
            and hex_mem.get(addr + 2, 0xFF) == 0x01
            and hex_mem.get(addr + 3, 0xFF) == 0x01
            and hex_mem.get(addr + 4, 0xFF) == 0x5B
            and hex_mem.get(addr + 5, 0xFF) == 0x6F
            and hex_mem.get(addr + 7, 0xFF) == 0x0E
            and hex_mem.get(addr + 8, 0xFF) == 0x5C
            and hex_mem.get(addr + 9, 0xFF) == 0x6F
            and hex_mem.get(addr + 11, 0xFF) == 0x0E
            and hex_mem.get(addr + 12, 0xFF) == 0x5D
            and hex_mem.get(addr + 13, 0xFF) == 0x6F
        ):
            return VersionInfo(
                flag=hex_mem.get(addr, 0xFF) & 0xFF,
                major=hex_mem.get(addr + 6, 0xFF) & 0xFF,
                minor=hex_mem.get(addr + 10, 0xFF) & 0xFF,
            )
    return None


def detect_static_hex_version(hex_mem: Dict[int, int]) -> Optional[VersionInfo]:
    return detect_static_hex_hid_version(hex_mem)


def _format_version_short(version: Optional[VersionInfo]) -> str:
    if version is None:
        return "<unknown>"
    return f"{version.major}.{version.minor}"


def resolve_capture_flash_base(
    *,
    preset: str,
    target_version: Optional[VersionInfo],
) -> int:
    if preset == "A":
        return PRESET_A_FLASH_BASE
    if preset != "B":
        raise RuntimeError(f"unsupported preset overlay {preset!r}")
    if target_version is None:
        raise RuntimeError(
            "--capture-b requires a target MAIN image with a statically detectable "
            "firmware version; supported preset-B layouts are V2.4-V2.8 (0x4A00) "
            "and V3.1+ (0x4C00)"
        )
    if target_version.major == 2 and 4 <= target_version.minor <= 8:
        return PRESET_B_FLASH_BASE_V24_TO_V28
    if target_version.major >= 3:
        return PRESET_B_FLASH_BASE_V31_PLUS
    raise RuntimeError(
        f"--capture-b is unsupported for target MAIN image version "
        f"{_format_version_short(target_version)}; supported preset-B layouts are "
        "V2.4-V2.8 (0x4A00) and V3.1+ (0x4C00)"
    )


def _load_capture_overlay(
    *,
    capture_path: Path,
    explicit_meta: Optional[Path],
    name_override: Optional[str],
    preset: str,
    flash_base: Optional[int] = None,
) -> CaptureOverlay:
    if preset not in {"A", "B"}:
        raise RuntimeError(f"unsupported preset overlay {preset!r}")
    if flash_base is None:
        if preset == "A":
            flash_base = PRESET_A_FLASH_BASE
        else:
            raise RuntimeError(
                "preset B flash base must be resolved from the target MAIN image version"
            )

    table = capture_path.read_bytes()
    if len(table) != PRESET_TABLE_SIZE:
        raise RuntimeError(
            f"{capture_path} has {len(table)} bytes, expected {PRESET_TABLE_SIZE}"
        )

    meta_path = explicit_meta if explicit_meta is not None else capture_path.with_suffix(".json")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raw_hex = str(meta.get("config_name_raw_hex", ""))
        config_name = str(meta.get("config_name", ""))
        if len(raw_hex) != FILENAME_LEN * 2:
            raise RuntimeError(f"{meta_path} has invalid config_name_raw_hex length")
        name_slot = bytes.fromhex(raw_hex)
    else:
        if name_override is None:
            raise RuntimeError(
                f"missing metadata sidecar for {capture_path}; "
                f"provide --name-{preset.lower()} or --meta-{preset.lower()}"
            )
        name_slot = _encode_name_slot(name_override)
        config_name = name_override

    return CaptureOverlay(
        preset=preset,
        table=table,
        name_slot=name_slot,
        config_name=config_name,
        flash_base=flash_base,
    )


def _apply_capture_overlay(hex_mem: Dict[int, int], overlay: CaptureOverlay) -> None:
    for idx, value in enumerate(overlay.table):
        hex_mem[overlay.flash_base + idx] = value & 0xFF


def build_main_stream(hex_mem: Dict[int, int]) -> bytes:
    """
    Build the byte stream expected by the MAIN bootloader:
      - sequential bytes from 0x1000 up to 0x5FFF inclusive
      - fill gaps with 0xFF
      - ignore bootloader/config/EEPROM/User ID regions
    """
    return _region_bytes(hex_mem, MAIN_APP_START, MAIN_PROG_END_EXCL)


def bootloader_mismatch_addresses(candidate_mem: Dict[int, int], reference_mem: Dict[int, int]) -> List[int]:
    """
    Return boot-block addresses where the candidate explicitly carries a byte that
    differs from the trusted combined-image reference.

    App-only MAIN HEX files normally omit 0x0000..0x0FFF entirely, so missing
    candidate bytes are treated as "not attempting to change bootloader" rather
    than mismatches.
    """
    mismatches: List[int] = []
    for addr, value in candidate_mem.items():
        if 0 <= addr < MAIN_BOOT_END_EXCL:
            if (value & 0xFF) != (reference_mem.get(addr, 0xFF) & 0xFF):
                mismatches.append(addr)
    mismatches.sort()
    return mismatches


def run_preflight(
    *,
    hex_mem: Dict[int, int],
    bootloader_ref_mem: Optional[Dict[int, int]],
    require_bootloader_match: bool,
) -> Dict[str, object]:
    app_window = build_main_stream(hex_mem)
    result: Dict[str, object] = {
        "payload_len": len(app_window),
        "payload_crc": crc_stream(app_window),
        "payload_sha256": _sha256_hex(app_window),
        "bootloader_bytes_present": _count_explicit(hex_mem, 0x0000, MAIN_BOOT_END_EXCL),
        "app_bytes_present": _count_explicit(hex_mem, MAIN_APP_START, MAIN_PROG_END_EXCL),
        "non_app_explicit_count": sum(
            1 for addr in hex_mem if not (MAIN_APP_START <= addr < MAIN_PROG_END_EXCL)
        ),
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
                f"{len(mismatches)} explicit locations within 0x0000..0x{MAIN_BOOT_END_EXCL - 1:04X}; "
                f"first diffs: {preview}"
            )
        result["bootloader_match"] = True

    return result


def _device_mode(info: HidDeviceInfo) -> str:
    product = info.product_string.strip().lower()
    if BOOTLOADER_PRODUCT_TOKEN in product:
        return "bootloader"
    if product:
        return "app"
    return "unknown"


def _list_devices_with_mode(vid: int, pid: int) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for dev in enumerate_devices(vid, pid):
        item = dataclasses.asdict(dev)
        item["mode"] = _device_mode(dev)
        out.append(item)
    return out


def _pick_device(vid: int, pid: int, path: Optional[bytes]) -> HidDeviceInfo:
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


def _open_hid(path: bytes):
    try:
        import hid
    except ImportError as exc:
        raise RuntimeError(
            "python-hidapi is required. Install with: python3 -m pip install hidapi"
        ) from exc
    dev = hid.device()
    dev.open_path(path)
    dev.set_nonblocking(False)
    return dev


def parse_cmd06_version_response(resp: bytes) -> VersionInfo:
    if len(resp) < 4:
        raise RuntimeError(f"short cmd 0x06 response: {len(resp)} bytes")
    base = 0
    if resp[0] == 0x00 and len(resp) >= 5 and resp[1] == 0x06:
        base = 1
    elif resp[0] != 0x06:
        raise RuntimeError(f"unexpected cmd 0x06 echo: 0x{resp[0]:02X}")
    return VersionInfo(flag=resp[base + 1], major=resp[base + 2], minor=resp[base + 3])


def decode_filename_slot(raw: bytes) -> str:
    trimmed = raw.rstrip(b"\x00\xFF")
    if not trimmed:
        return ""
    try:
        return trimmed.decode("ascii")
    except UnicodeDecodeError:
        return f"<non-ascii:{trimmed.hex()}>"


def route_value_label(value: int) -> str:
    return ROUTE_LABELS.get(value & 0xFF, f"0x{value & 0xFF:02X}")


def decode_route_entries(raw: bytes) -> tuple[RouteEntry, ...]:
    return tuple(
        RouteEntry(channel=idx + 1, value=b & 0xFF, label=route_value_label(b))
        for idx, b in enumerate(raw)
    )


def format_route_entries(entries: tuple[RouteEntry, ...]) -> str:
    return ", ".join(f"CH{entry.channel}={entry.label}" for entry in entries)


def _name_slot_to_cmd03_payload(name_slot: bytes) -> bytes:
    if len(name_slot) != FILENAME_LEN:
        raise ValueError(f"name slot must be {FILENAME_LEN} bytes")
    payload = bytearray(FILENAME_LEN)
    for idx, value in enumerate(name_slot):
        vv = value & 0xFF
        payload[idx] = 0x00 if vv in (0x00, 0xFF) else vv
    return bytes(payload)


def _parse_cmd03_filename_response(resp: bytes, *, subcmd: int) -> bytes:
    if len(resp) != 64:
        raise RuntimeError(f"short HID response: {len(resp)} bytes")
    if resp[0] != 0x03 or resp[1] != (subcmd & 0xFF):
        raise RuntimeError(
            "unexpected cmd 0x03 response: "
            f"got [0]=0x{resp[0]:02X} [1]=0x{resp[1]:02X}, "
            f"expected [0]=0x03 [1]=0x{subcmd & 0xFF:02X}"
        )
    return bytes(resp[2 : 2 + FILENAME_LEN])


def _exchange_report(dev, report: bytes, *, timeout_ms: int = 1000) -> bytes:
    if len(report) != 64:
        raise ValueError("report must be exactly 64 bytes")
    _hid_write64(dev, report)
    resp = _hid_read64(dev, timeout_ms=timeout_ms)
    if resp is None:
        raise RuntimeError("timed out waiting for HID response")
    if len(resp) != 64:
        raise RuntimeError(f"short HID response: {len(resp)} bytes")
    return resp


def _exchange_report_with_retry(
    dev,
    report: bytes,
    *,
    timeout_ms: int = 1000,
    attempts: int = 3,
    retry_delay_s: float = 0.05,
) -> bytes:
    last_exc: Optional[RuntimeError] = None
    for attempt in range(max(1, attempts)):
        try:
            return _exchange_report(dev, report, timeout_ms=timeout_ms)
        except RuntimeError as exc:
            last_exc = exc
            if attempt + 1 >= max(1, attempts):
                raise
            time.sleep(retry_delay_s)
    assert last_exc is not None
    raise last_exc


def _probe_cmd06_version(
    dev,
    *,
    timeout_ms: int = 1000,
    attempts: int = 3,
    retry_delay_s: float = 0.05,
) -> VersionInfo:
    report = _mk_report(0x06)
    report[1] = CMD06_VERSION_SUBCMD
    last_exc: Optional[RuntimeError] = None
    for attempt in range(max(1, attempts)):
        try:
            resp = _exchange_report(dev, bytes(report), timeout_ms=timeout_ms)
            return parse_cmd06_version_response(resp)
        except RuntimeError as exc:
            last_exc = exc
            if attempt + 1 >= max(1, attempts):
                raise
            time.sleep(retry_delay_s)
    assert last_exc is not None
    raise last_exc


def _cmd03_exchange_filename(dev, *, subcmd: int, payload: bytes = b"", timeout_ms: int = 1000) -> bytes:
    if len(payload) > FILENAME_LEN:
        raise ValueError(f"payload must be at most {FILENAME_LEN} bytes")
    report = _mk_report(0x03)
    report[1] = subcmd & 0xFF
    report[2 : 2 + len(payload)] = payload
    return _exchange_report(dev, bytes(report), timeout_ms=timeout_ms)


def _cmd03_exchange_filename_checked(
    dev,
    *,
    subcmd: int,
    payload: bytes = b"",
    timeout_ms: int = 1000,
    attempts: int = 3,
    retry_delay_s: float = 0.05,
) -> bytes:
    last_exc: Optional[RuntimeError] = None
    for attempt in range(max(1, attempts)):
        try:
            resp = _cmd03_exchange_filename(
                dev,
                subcmd=subcmd,
                payload=payload,
                timeout_ms=timeout_ms,
            )
            return _parse_cmd03_filename_response(resp, subcmd=subcmd)
        except RuntimeError as exc:
            last_exc = exc
            if attempt + 1 >= max(1, attempts):
                raise
            time.sleep(retry_delay_s)
    assert last_exc is not None
    raise last_exc


def _cmd03_read_filename_slot(
    dev,
    *,
    timeout_ms: int = 1000,
    attempts: int = 3,
    retry_delay_s: float = 0.05,
) -> bytes:
    return _cmd03_exchange_filename_checked(
        dev,
        subcmd=CMD03_FILENAME_READ_SUBCMD,
        timeout_ms=timeout_ms,
        attempts=attempts,
        retry_delay_s=retry_delay_s,
    )


def _cmd03_write_filename_slot(
    dev,
    *,
    name_slot: bytes,
    timeout_ms: int = 1000,
    attempts: int = 3,
    retry_delay_s: float = 0.05,
) -> bytes:
    if all((b & 0xFF) == 0xFF for b in name_slot):
        _cmd03_exchange_filename_checked(
            dev,
            subcmd=CMD03_FILENAME_ERASE_SUBCMD,
            timeout_ms=timeout_ms,
            attempts=attempts,
            retry_delay_s=retry_delay_s,
        )
        return _cmd03_read_filename_slot(
            dev,
            timeout_ms=timeout_ms,
            attempts=attempts,
            retry_delay_s=retry_delay_s,
        )

    _cmd03_exchange_filename_checked(
        dev,
        subcmd=CMD03_FILENAME_WRITE_SUBCMD,
        payload=_name_slot_to_cmd03_payload(name_slot),
        timeout_ms=timeout_ms,
        attempts=attempts,
        retry_delay_s=retry_delay_s,
    )
    return _cmd03_read_filename_slot(
        dev,
        timeout_ms=timeout_ms,
        attempts=attempts,
        retry_delay_s=retry_delay_s,
    )


def _first_byte_diff(got: bytes, expected: bytes) -> Optional[int]:
    for idx, (got_b, exp_b) in enumerate(zip(got, expected)):
        if got_b != exp_b:
            return idx
    if len(got) != len(expected):
        return min(len(got), len(expected))
    return None


def _verify_capture_overlay(
    *,
    info: HidDeviceInfo,
    overlay: CaptureOverlay,
    timeout_ms: int,
    verify_reads: int,
    retries: int,
    delay_s: float,
) -> None:
    from dlcp_fw.flash.read_coeffs import HidMemoryReader, capture_preset

    with HidMemoryReader(info=info, timeout_ms=timeout_ms) as reader:
        result = capture_preset(
            reader=reader,
            preset=overlay.preset,
            verify_reads=verify_reads,
            retries=retries,
            delay_s=delay_s,
        )

    if result.table != overlay.table:
        diff = _first_byte_diff(result.table, overlay.table)
        assert diff is not None
        raise RuntimeError(
            f"post-flash preset {overlay.preset} table verify failed at "
            f"offset 0x{diff:04X}: got 0x{result.table[diff]:02X}, "
            f"expected 0x{overlay.table[diff]:02X}"
        )
    if result.name_slot != overlay.name_slot:
        raise RuntimeError(
            f"post-flash preset {overlay.preset} EEPROM name verify failed: "
            f"got {result.name_slot.hex()}, expected {overlay.name_slot.hex()}"
        )


def _is_diag_memread_unavailable_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    if "device may not be running the diag memread firmware" in text:
        return True
    if "unexpected command echo" in text and "expected 0x43" in text:
        return True
    if "timed out waiting for diag memread response" in text:
        return True
    if "timed out waiting for hid response" in text:
        return True
    return False


def _is_preset_eeprom_name_verify_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "post-flash preset " in text and " eeprom name verify failed" in text


def _looks_like_main_boot_ack(resp: bytes) -> bool:
    if len(resp) < 3:
        return False
    # The MAIN bootloader returns a response after each streamed 0x40 packet.
    # On real hardware we only need that pacing signal; the parser can be loose.
    if resp[0] in (0x40, 0x00):
        return True
    return False


def _read_ep0_window(ep0: DlcpEp0, *, start: int, size: int) -> bytes:
    ep0.set_pointer(start)
    return ep0.read_exact(size)


def _ep0_read_byte(ep0: DlcpEp0, *, addr: int) -> int:
    data = _read_ep0_window(ep0, start=addr, size=1)
    if len(data) != 1:
        raise RuntimeError(f"short EP0 byte read at 0x{addr:04X}: got {len(data)} bytes")
    return data[0]


def _ep0_write_byte(ep0: DlcpEp0, *, addr: int, value: int) -> None:
    ep0._poke(addr, value & 0xFF, in_dir=False)


def _ep0_or_byte(ep0: DlcpEp0, *, addr: int, mask: int) -> int:
    current = _ep0_read_byte(ep0, addr=addr)
    updated = current | (mask & 0xFF)
    if updated != current:
        _ep0_write_byte(ep0, addr=addr, value=updated)
    return updated


def _active_preset_from_flags(flags: int) -> str:
    return "B" if (flags & ACTIVE_PRESET_MASK) else "A"


def _describe_active_flags(flags: int) -> str:
    preset = _active_preset_from_flags(flags)
    reapply = "pending" if (flags & ACTIVE_REAPPLY_MASK) else "clear"
    return f"{preset} (active_flags=0x{flags:02X}, reapply {reapply})"


def _read_active_flags_ep0(*, vid: int, pid: int, path: bytes | None = None) -> int:
    ep0 = DlcpEp0(vid=vid, pid=pid, path=path)
    return _ep0_read_byte(ep0, addr=ACTIVE_FLAGS_ADDR)


def _probe_active_preset_ep0(*, vid: int, pid: int, path: bytes | None = None) -> str:
    return _active_preset_from_flags(_read_active_flags_ep0(vid=vid, pid=pid, path=path))


def _request_active_preset_switch_ep0(
    *,
    vid: int,
    pid: int,
    preset: str,
    path: bytes | None = None,
) -> dict[str, int]:
    if preset not in {"A", "B"}:
        raise ValueError(f"unsupported preset {preset!r}")
    ep0 = DlcpEp0(vid=vid, pid=pid, path=path)
    before = _ep0_read_byte(ep0, addr=ACTIVE_FLAGS_ADDR)
    target = before & (~ACTIVE_PRESET_MASK & 0xFF)
    if preset == "B":
        target |= ACTIVE_PRESET_MASK
    write_value = target | ACTIVE_REAPPLY_MASK
    _ep0_write_byte(ep0, addr=ACTIVE_FLAGS_ADDR, value=write_value)
    return {
        "active_flags_before": before,
        "active_flags_write": write_value,
    }


def _switch_active_preset_ep0(
    *,
    vid: int,
    pid: int,
    preset: str,
    path: bytes | None = None,
    timeout_s: float = 2.0,
    poll_interval_s: float = 0.05,
    settle_s: float = 0.25,
    stable_reads: int = 2,
) -> str:
    current_flags = _read_active_flags_ep0(vid=vid, pid=pid, path=path)
    current = _active_preset_from_flags(current_flags)
    if current == preset and not (current_flags & ACTIVE_REAPPLY_MASK):
        return current
    _request_active_preset_switch_ep0(vid=vid, pid=pid, preset=preset, path=path)
    if settle_s > 0:
        time.sleep(settle_s)
    deadline = time.monotonic() + max(0.0, timeout_s)
    last_flags = current_flags
    consecutive_ready = 0
    while True:
        last_flags = _read_active_flags_ep0(vid=vid, pid=pid, path=path)
        ready = (
            _active_preset_from_flags(last_flags) == preset
            and not (last_flags & ACTIVE_REAPPLY_MASK)
        )
        if ready:
            consecutive_ready += 1
            if consecutive_ready >= max(1, stable_reads):
                return preset
        else:
            consecutive_ready = 0
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "preset switch verify failed: device reports "
                f"{_describe_active_flags(last_flags)}, expected {preset} "
                "with reapply clear"
            )
        time.sleep(max(0.0, poll_interval_s))


def _apply_all_channel_mapping(
    *,
    vid: int,
    pid: int,
    path: bytes | None = None,
    route_label: str,
    settle_s: float = 0.15,
) -> tuple[RouteEntry, ...]:
    route_value = ALL_CH_ROUTE_VALUES.get(route_label)
    if route_value is None:
        raise ValueError(f"unsupported --all-ch value: {route_label!r}")

    expected = bytes([route_value] * ROUTE_LEN)
    ep0 = DlcpEp0(vid=vid, pid=pid, path=path)

    for offset in range(ROUTE_LEN):
        _ep0_write_byte(ep0, addr=ROUTE_RAM_BASE + offset, value=route_value)
        _ep0_write_byte(ep0, addr=ROUTE_SOURCE_RAM_BASE + offset, value=route_value)

    # Route shadow bytes drive persistence, while live source bytes drive the
    # active DSP selector matrix. Setting both avoids relying on a later copy.
    _ep0_or_byte(ep0, addr=EVENT_FLAGS_ADDR, mask=EVENT_ROUTE_APPLY_MASK)
    _ep0_or_byte(ep0, addr=ROUTE_DIRTY_FLAGS_ADDR, mask=EEPROM_ROUTE_DIRTY_MASK)

    if settle_s > 0:
        time.sleep(settle_s)

    route_raw = _read_ep0_window(ep0, start=ROUTE_RAM_BASE, size=ROUTE_LEN)
    source_raw = _read_ep0_window(ep0, start=ROUTE_SOURCE_RAM_BASE, size=ROUTE_LEN)
    if route_raw != expected:
        raise RuntimeError(
            "route shadow verify failed after --all-ch: "
            f"got {route_raw.hex()}, expected {expected.hex()}"
        )
    if source_raw != expected:
        raise RuntimeError(
            "live source verify failed after --all-ch: "
            f"got {source_raw.hex()}, expected {expected.hex()}"
        )
    return decode_route_entries(route_raw)


def _force_active_filename_persist(
    *,
    vid: int,
    pid: int,
    path: bytes | None = None,
    timeout_s: float = 1.5,
    poll_s: float = 0.02,
) -> bool:
    if timeout_s <= 0:
        raise ValueError("timeout_s must be > 0")
    if poll_s <= 0:
        raise ValueError("poll_s must be > 0")

    ep0 = DlcpEp0(vid=vid, pid=pid, path=path)
    dirty = _ep0_read_byte(ep0, addr=ROUTE_DIRTY_FLAGS_ADDR)
    if (dirty & FILENAME_DIRTY_MASK) == 0:
        return False

    deadline = time.monotonic() + timeout_s
    while True:
        _ep0_or_byte(ep0, addr=EVENT_FLAGS_ADDR, mask=EVENT_DIRTY_SERVICE_MASK)
        time.sleep(poll_s)
        dirty = _ep0_read_byte(ep0, addr=ROUTE_DIRTY_FLAGS_ADDR)
        if (dirty & FILENAME_DIRTY_MASK) == 0:
            return True
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "filename dirty flag did not clear after EP0 persist trigger "
                f"(dirty=0x{dirty:02X})"
            )


def _probe_ep0_app_ram(
    *,
    vid: int,
    pid: int,
    path: bytes | None = None,
) -> tuple[str, tuple[RouteEntry, ...]]:
    ep0 = DlcpEp0(vid=vid, pid=pid, path=path)
    route_raw = _read_ep0_window(ep0, start=ROUTE_RAM_BASE, size=ROUTE_LEN)
    filename_raw = _read_ep0_window(ep0, start=FILENAME_RAM_BASE, size=FILENAME_LEN)
    return decode_filename_slot(filename_raw), decode_route_entries(route_raw)


def _probe_device_snapshot(*, info: HidDeviceInfo, vid: int, pid: int) -> DeviceSnapshot:
    warnings: List[str] = []
    mode = _device_mode(info)
    version: Optional[VersionInfo] = None
    active_config_name: Optional[str] = None
    active_config_raw: Optional[bytes] = None
    active_routes: Optional[tuple[RouteEntry, ...]] = None

    if info.path is not None:
        dev = _open_hid(info.path)
        try:
            version = _probe_cmd06_version(dev)
        except Exception as exc:
            warnings.append(f"version probe failed: {exc}")
        finally:
            try:
                dev.close()
            except Exception:
                pass

    if mode != "bootloader":
        try:
            active_config_name, active_routes = _probe_ep0_app_ram(
                vid=vid,
                pid=pid,
                path=info.path,
            )
            active_config_raw = active_config_name.encode("ascii", errors="ignore")
        except Exception as exc:
            warnings.append(f"EP0 RAM probe failed: {exc}")

    return DeviceSnapshot(
        mode=mode,
        product_string=info.product_string,
        manufacturer_string=info.manufacturer_string,
        serial_number=info.serial_number,
        version=version,
        active_config_name=active_config_name,
        active_config_raw=active_config_raw,
        active_routes=active_routes,
        warnings=tuple(warnings),
    )


def _print_device_snapshot(title: str, snapshot: DeviceSnapshot) -> None:
    print(title)
    print(f"  mode: {snapshot.mode}")
    print(f"  product: {snapshot.product_string or '<no-product>'}")
    print(f"  manufacturer: {snapshot.manufacturer_string or '<no-mfg>'}")
    print(f"  serial: {snapshot.serial_number or '<no-serial>'}")
    if snapshot.version is None:
        print("  version: unavailable")
    else:
        print(
            "  version:"
            f" {snapshot.version.major}.{snapshot.version.minor}"
            f" (flag=0x{snapshot.version.flag:02X})"
        )
    if snapshot.active_config_name is None:
        print("  active config: unavailable")
    elif snapshot.active_config_name:
        print(f"  active config: {snapshot.active_config_name!r}")
    else:
        print("  active config: <empty>")
    if snapshot.active_routes is None:
        print("  channel mappings: unavailable")
    else:
        print(f"  channel mappings: {format_route_entries(snapshot.active_routes)}")
    for warning in snapshot.warnings:
        print(f"  warning: {warning}")


def _wait_for_bootloader(
    *,
    vid: int,
    pid: int,
    serial_number: str,
    timeout_s: float,
) -> HidDeviceInfo:
    deadline = time.time() + timeout_s
    last_modes: List[str] = []
    while time.time() < deadline:
        devs = enumerate_devices(vid, pid)
        boot_devs = [dev for dev in devs if _device_mode(dev) == "bootloader"]
        if serial_number:
            serial_matches = [dev for dev in boot_devs if dev.serial_number == serial_number]
            if len(serial_matches) == 1:
                return serial_matches[0]
        if len(boot_devs) == 1:
            return boot_devs[0]
        last_modes = [f"{dev.product_string or '<no-product>'}:{_device_mode(dev)}" for dev in devs]
        time.sleep(0.2)
    mode_text = ", ".join(last_modes) if last_modes else "<none>"
    raise RuntimeError(
        f"bootloader did not reconnect within {timeout_s:.1f}s; last seen devices: {mode_text}"
    )


def _wait_for_app(
    *,
    vid: int,
    pid: int,
    serial_number: str,
    timeout_s: float,
) -> HidDeviceInfo:
    deadline = time.time() + timeout_s
    last_modes: List[str] = []
    while time.time() < deadline:
        devs = enumerate_devices(vid, pid)
        app_devs = [dev for dev in devs if _device_mode(dev) == "app"]
        if serial_number:
            serial_matches = [dev for dev in app_devs if dev.serial_number == serial_number]
            if len(serial_matches) == 1:
                return serial_matches[0]
        if len(app_devs) == 1:
            return app_devs[0]
        last_modes = [f"{dev.product_string or '<no-product>'}:{_device_mode(dev)}" for dev in devs]
        time.sleep(0.2)
    mode_text = ", ".join(last_modes) if last_modes else "<none>"
    raise RuntimeError(
        f"app did not reconnect within {timeout_s:.1f}s; last seen devices: {mode_text}"
    )


def _switch_to_bootloader(
    *,
    info: HidDeviceInfo,
    vid: int,
    pid: int,
    reconnect_timeout_s: float,
    reconnect_settle_ms: int,
    verbose: bool,
) -> HidDeviceInfo:
    if info.path is None:
        raise RuntimeError("selected HID device has no path")
    if verbose:
        print(
            "switching to bootloader via app 0x40 "
            f"({info.product_string or '<no-product>'})..."
        )
    dev = _open_hid(info.path)
    try:
        _hid_write64(dev, bytes(_mk_report(0x40)))
    finally:
        try:
            dev.close()
        except Exception:
            pass
    time.sleep(max(0, reconnect_settle_ms) / 1000.0)
    return _wait_for_bootloader(
        vid=vid,
        pid=pid,
        serial_number=info.serial_number,
        timeout_s=reconnect_timeout_s,
    )


def flash_main(
    *,
    vid: int,
    pid: int,
    path: Optional[bytes],
    stream: bytes,
    pace_ms: int,
    reconnect_timeout_s: float,
    reconnect_settle_ms: int,
    verify: bool,
    skip_switch: bool,
    dry_run: bool,
    report_info: bool,
    need_post_app: bool,
    post_info_timeout_s: float,
    verbose: bool,
) -> Optional[HidDeviceInfo]:
    expected_len = MAIN_PROG_END_EXCL - MAIN_APP_START
    if len(stream) != expected_len:
        raise ValueError(f"stream must be {expected_len} bytes, got {len(stream)}")

    expected_crc = crc_stream(stream)
    exp_hi = (expected_crc >> 8) & 0xFF
    exp_lo = expected_crc & 0xFF

    if verbose or dry_run:
        print(
            f"main stream: {len(stream)} bytes "
            f"(0x{MAIN_APP_START:04X}..0x{MAIN_PROG_END_EXCL - 1:04X})"
        )
        print(
            f"expected CRC: 0x{expected_crc:04X} "
            f"(report[4]=0x{exp_hi:02X}, report[5]=0x{exp_lo:02X})"
        )

    if dry_run:
        return None

    initial = _pick_device(vid, pid, path)
    initial_mode = _device_mode(initial)
    if verbose:
        print(
            "selected device:"
            f" product={initial.product_string or '<no-product>'}"
            f" manufacturer={initial.manufacturer_string or '<no-mfg>'}"
            f" serial={initial.serial_number or '<no-serial>'}"
            f" mode={initial_mode}"
        )
    if report_info:
        _print_device_snapshot(
            "before flash:",
            _probe_device_snapshot(info=initial, vid=vid, pid=pid),
        )

    if skip_switch:
        if initial_mode == "app":
            raise RuntimeError("--skip-switch requested but selected device looks like app mode")
        if initial_mode == "unknown":
            raise RuntimeError(
                "--skip-switch requires a device that enumerates as bootloader mode"
            )
        boot_dev = initial
    elif initial_mode == "bootloader":
        boot_dev = initial
    elif initial_mode == "app":
        boot_dev = _switch_to_bootloader(
            info=initial,
            vid=vid,
            pid=pid,
            reconnect_timeout_s=reconnect_timeout_s,
            reconnect_settle_ms=reconnect_settle_ms,
            verbose=verbose,
        )
    else:
        raise RuntimeError(
            "unable to infer app vs bootloader mode from HID product string; "
            "use --list and reconnect in a clearer state"
        )

    if boot_dev.path is None:
        raise RuntimeError("bootloader device has no HID path")
    if verbose:
        print(
            "bootloader device:"
            f" product={boot_dev.product_string or '<no-product>'}"
            f" manufacturer={boot_dev.manufacturer_string or '<no-mfg>'}"
            f" serial={boot_dev.serial_number or '<no-serial>'}"
        )

    dev = _open_hid(boot_dev.path)
    try:
        total = len(stream)
        pos = 0
        report_i = 0
        last_print = time.time()

        while pos < total:
            chunk = stream[pos : pos + 30]
            if len(chunk) < 30:
                chunk = chunk + bytes([0xFF]) * (30 - len(chunk))
            report = _mk_report(0x40)
            report[2 : 2 + 30] = chunk
            _hid_write64(dev, bytes(report))
            ack = _hid_read64(dev, timeout_ms=2000)
            if ack is None:
                raise RuntimeError("no response after stream packet (0x40)")
            if not _looks_like_main_boot_ack(ack):
                raise RuntimeError(
                    "unexpected stream ack after 0x40: "
                    + " ".join(f"{x:02x}" for x in ack[:8])
                )

            pos += 30
            report_i += 1

            if pace_ms:
                time.sleep(pace_ms / 1000.0)

            if verbose and (time.time() - last_print) > 0.5:
                pct = min(100.0, (pos / total) * 100.0)
                print(f"streaming: report={report_i} pos=0x{pos:04X}/{total:04X} ({pct:5.1f}%)")
                print("stream ack[0..7] =", " ".join(f"{x:02x}" for x in ack[:8]))
                last_print = time.time()

        if verify:
            if verbose:
                print("sending CRC verify (0x41)...")
            report = _mk_report(0x41)
            report[4] = exp_hi
            report[5] = exp_lo
            _hid_write64(dev, bytes(report))
            resp = _hid_read64(dev, timeout_ms=2000)
            if resp is None:
                raise RuntimeError("no response to CRC verify (0x41)")
            ok = len(resp) >= 3 and resp[2] == 0xAA
            if verbose:
                print("verify resp[0..7] =", " ".join(f"{x:02x}" for x in resp[:8]))
            if not ok:
                got = resp[2] if len(resp) >= 3 else -1
                raise RuntimeError(f"CRC verify failed (resp[2]=0x{got & 0xFF:02X}, expected 0xAA)")
            if verbose:
                print("CRC verify OK.")
    finally:
        try:
            dev.close()
        except Exception:
            pass

    post_dev: Optional[HidDeviceInfo] = None
    if report_info or need_post_app:
        try:
            post_dev = _wait_for_app(
                vid=vid,
                pid=pid,
                serial_number=boot_dev.serial_number,
                timeout_s=post_info_timeout_s,
            )
            if report_info:
                _print_device_snapshot(
                    "after flash:",
                    _probe_device_snapshot(info=post_dev, vid=vid, pid=pid),
                )
        except Exception as exc:
            if report_info:
                print(f"after flash:\n  warning: post-flash info probe failed: {exc}")
            else:
                raise

    return post_dev


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vid", type=_parse_int_auto, default=DEFAULT_VID, help="USB VID (default: 0x04D8)")
    ap.add_argument("--pid", type=_parse_int_auto, default=DEFAULT_PID, help="USB PID (default: 0xFF89)")
    ap.add_argument("--path", type=str, default="", help="hidapi path (advanced; leave empty to auto-pick)")
    ap.add_argument("--list", action="store_true", help="list matching HID devices and exit")
    ap.add_argument("--hex", type=str, default="", help="main firmware .hex (Intel HEX)")
    ap.add_argument("--capture-a", type=Path, default=None, help="preset A capture .bin to overlay into flash before streaming")
    ap.add_argument(
        "--capture-b",
        type=Path,
        default=None,
        help=(
            "preset B capture .bin to overlay into flash before streaming; "
            "target HEX must be V2.4-V2.8 or V3.1+"
        ),
    )
    ap.add_argument("--meta-a", type=Path, default=None, help="explicit sidecar JSON for --capture-a")
    ap.add_argument("--meta-b", type=Path, default=None, help="explicit sidecar JSON for --capture-b")
    ap.add_argument("--name-a", default=None, help="ASCII config name fallback if --capture-a sidecar JSON is missing")
    ap.add_argument("--name-b", default=None, help="ASCII config name fallback if --capture-b sidecar JSON is missing")
    ap.add_argument(
        "--all-ch",
        type=str.upper,
        choices=sorted(ALL_CH_ROUTE_VALUES),
        default=None,
        help="after flashing, set all channel mappings to this source (currently: L or R)",
    )
    ap.add_argument(
        "--info-only",
        action="store_true",
        help="probe current device info and exit (no flashing)",
    )
    ap.add_argument(
        "--no-info",
        action="store_true",
        help="skip default pre/post flash device info reporting",
    )
    ap.add_argument(
        "--bootloader-ref",
        type=str,
        default=str(DEFAULT_BOOTLOADER_REF),
        help="trusted reference HEX for explicit boot-block bytes (default: stock V2.3 combined HEX)",
    )
    ap.add_argument(
        "--skip-bootloader-check",
        action="store_true",
        help="unsafe: skip explicit boot-block byte check against reference",
    )
    ap.add_argument(
        "--skip-switch",
        action="store_true",
        help="unsafe: do not auto-switch app mode into bootloader; require bootloader to already be active",
    )
    ap.add_argument(
        "--preflight-only",
        action="store_true",
        help="run safety checks and print checksums/CRC; do not write over USB",
    )
    ap.add_argument("--pace-ms", type=int, default=20, help="sleep after each 0x40 report (default: 20ms)")
    ap.add_argument(
        "--reconnect-timeout-s",
        type=float,
        default=10.0,
        help="wait for bootloader reconnect after app 0x40 (default: 10s)",
    )
    ap.add_argument(
        "--reconnect-settle-ms",
        type=int,
        default=500,
        help="sleep after app 0x40 before polling for bootloader (default: 500ms)",
    )
    ap.add_argument(
        "--post-info-timeout-s",
        type=float,
        default=10.0,
        help="wait for app reconnect before post-flash info probe (default: 10s)",
    )
    ap.add_argument("--no-verify", action="store_true", help="unsafe: skip CRC verify command (0x41)")
    ap.add_argument(
        "--force-unsafe",
        action="store_true",
        help="required to use unsafe flags (--no-verify, --skip-bootloader-check, --skip-switch)",
    )
    ap.add_argument("--dry-run", action="store_true", help="parse/prepare only, no USB writes")
    ap.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    args = ap.parse_args(argv)

    if args.list:
        print(json.dumps(_list_devices_with_mode(args.vid, args.pid), indent=2, default=str))
        return 0

    if args.info_only:
        info = _pick_device(args.vid, args.pid, args.path.encode("utf-8") if args.path else None)
        _print_device_snapshot(
            "device info:",
            _probe_device_snapshot(info=info, vid=args.vid, pid=args.pid),
        )
        return 0

    if not args.hex:
        ap.error("--hex is required (main firmware Intel HEX)")
    if (args.no_verify or args.skip_bootloader_check or args.skip_switch) and not args.force_unsafe:
        ap.error("--no-verify, --skip-bootloader-check, and --skip-switch require --force-unsafe")

    hex_mem = parse_intel_hex(args.hex)
    overlays: list[CaptureOverlay] = []
    overlay_a: Optional[CaptureOverlay] = None
    target_hex_version = detect_static_hex_version(hex_mem)
    if args.capture_a is not None:
        overlay_a = _load_capture_overlay(
            capture_path=args.capture_a,
            explicit_meta=args.meta_a,
            name_override=args.name_a,
            preset="A",
            flash_base=resolve_capture_flash_base(
                preset="A",
                target_version=target_hex_version,
            ),
        )
        _apply_capture_overlay(hex_mem, overlay_a)
        overlays.append(overlay_a)
    if args.capture_b is not None:
        try:
            overlay_b = _load_capture_overlay(
                capture_path=args.capture_b,
                explicit_meta=args.meta_b,
                name_override=args.name_b,
                preset="B",
                flash_base=resolve_capture_flash_base(
                    preset="B",
                    target_version=target_hex_version,
                ),
            )
        except RuntimeError as exc:
            ap.error(str(exc))
        _apply_capture_overlay(hex_mem, overlay_b)
        overlays.append(overlay_b)

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
            "  payload window: 0x"
            f"{MAIN_APP_START:04X}..0x{MAIN_PROG_END_EXCL - 1:04X} ({preflight['payload_len']} bytes)"
        )
        print(f"  payload crc16: 0x{preflight['payload_crc']:04X}")
        print(f"  payload sha256: {preflight['payload_sha256']}")
        print(f"  explicit app bytes: {preflight['app_bytes_present']}")
        print(f"  explicit bootloader bytes: {preflight['bootloader_bytes_present']}")
        print(f"  explicit non-app bytes ignored by device: {preflight['non_app_explicit_count']}")
        if not args.skip_bootloader_check:
            print(f"  explicit bootloader bytes match: {args.bootloader_ref}")
        for overlay in overlays:
            capture_path = args.capture_a if overlay.preset == "A" else args.capture_b
            print(f"  capture {overlay.preset} overlay: {capture_path}")
            print(f"  capture {overlay.preset} name: {overlay.config_name!r}")
            print(f"  capture {overlay.preset} flash base: 0x{overlay.flash_base:04X}")
            print(f"  capture {overlay.preset} table sha256: {_sha256_hex(overlay.table)}")
        if args.all_ch is not None:
            print(f"  post-flash all-ch mapping: {args.all_ch}")

    stream = build_main_stream(hex_mem)

    path: Optional[bytes] = args.path.encode("utf-8") if args.path else None

    post_dev = flash_main(
        vid=args.vid,
        pid=args.pid,
        path=path,
        stream=stream,
        pace_ms=max(0, args.pace_ms),
        reconnect_timeout_s=max(0.1, float(args.reconnect_timeout_s)),
        reconnect_settle_ms=max(0, args.reconnect_settle_ms),
        verify=not args.no_verify,
        skip_switch=args.skip_switch,
        dry_run=args.dry_run or args.preflight_only,
        report_info=not args.no_info and not (args.dry_run or args.preflight_only),
        need_post_app=(
            (bool(overlays) or args.all_ch is not None)
            and not (args.dry_run or args.preflight_only)
        ),
        post_info_timeout_s=max(0.1, float(args.post_info_timeout_s)),
        verbose=args.verbose,
    )

    if (bool(overlays) or args.all_ch is not None) and not (
        args.dry_run or args.preflight_only
    ):
        if post_dev is None:
            raise RuntimeError(
                "post-flash app reconnect is required for post-flash finalize/verify"
            )
        if post_dev.path is None:
            raise RuntimeError("post-flash app device has no HID path")

        if overlays:
            initial_preset = _probe_active_preset_ep0(
                vid=args.vid,
                pid=args.pid,
                path=post_dev.path,
            )
            current_preset = initial_preset
            for overlay in overlays:
                print(f"post-flash preset {overlay.preset} finalize:")
                if current_preset != overlay.preset:
                    confirmed = _switch_active_preset_ep0(
                        vid=args.vid,
                        pid=args.pid,
                        preset=overlay.preset,
                        path=post_dev.path,
                    )
                    current_preset = confirmed
                    print(f"  switched active preset for filename finalize: {confirmed}")

                dev = _open_hid(post_dev.path)
                try:
                    live_slot = _cmd03_write_filename_slot(dev, name_slot=overlay.name_slot)
                finally:
                    dev.close()

                print(
                    f"  wrote preset {overlay.preset} active filename: "
                    f"{decode_filename_slot(live_slot)!r}"
                )
                print(f"  forcing preset {overlay.preset} filename EEPROM persist...")
                try:
                    forced = _force_active_filename_persist(
                        vid=args.vid,
                        pid=args.pid,
                        path=post_dev.path,
                    )
                except RuntimeError as exc:
                    print(
                        f"  warning: preset {overlay.preset} EEPROM persist trigger failed ({exc})"
                    )
                else:
                    if forced:
                        print(f"  preset {overlay.preset} EEPROM persist trigger: OK")
                    else:
                        print(
                            f"  preset {overlay.preset} EEPROM persist trigger: already clean"
                        )
                print(
                    f"  verifying preset {overlay.preset} flash + EEPROM via diag memread..."
                )
                try:
                    _verify_capture_overlay(
                        info=post_dev,
                        overlay=overlay,
                        timeout_ms=1000,
                        verify_reads=2,
                        retries=5,
                        delay_s=0.025,
                    )
                except RuntimeError as exc:
                    if _is_diag_memread_unavailable_error(exc):
                        print(
                            f"  warning: preset {overlay.preset} diag memread verify skipped; "
                            f"USB memread endpoint unavailable ({exc})"
                        )
                    elif _is_preset_eeprom_name_verify_error(exc):
                        print(f"  preset {overlay.preset} flash table verify: OK")
                        print(
                            f"  warning: preset {overlay.preset} EEPROM filename not yet persisted; "
                            f"RAM slot is correct but raw EEPROM still differs ({exc})"
                        )
                    else:
                        raise
                else:
                    print(f"  preset {overlay.preset} verify: OK")

            if current_preset != initial_preset:
                restored = _switch_active_preset_ep0(
                    vid=args.vid,
                    pid=args.pid,
                    preset=initial_preset,
                    path=post_dev.path,
                )
                print(f"post-flash preset restore:\n  restored active preset: {restored}")

        if args.all_ch is not None:
            print("post-flash channel mapping finalize:")
            routes = _apply_all_channel_mapping(
                vid=args.vid,
                pid=args.pid,
                path=post_dev.path,
                route_label=args.all_ch,
            )
            print(f"  requested all channels: {args.all_ch}")
            print(f"  verified mappings: {format_route_entries(routes)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
