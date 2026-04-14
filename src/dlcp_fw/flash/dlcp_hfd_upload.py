#!/usr/bin/env python3
"""Upload a DLCP preset table through the stock MAIN USB HID upload family.

This tool uses the stock MAIN application HID coefficient-upload command family
(`0x07..0x0C`) rather than the bootloader flash protocol. The upload targets the
currently active preset bank only; the USB reports themselves do not encode an
explicit preset selector.

Important behavior:
- The uploaded table payload is interpreted as the raw `0x5600..0x5FFF` flash
  window captured by `dlcp_read_coeffs.py`.
- Only the 20-byte payload portion of each 24-byte table slot is transmitted,
  matching the stock upload flow. Slot headers and the trailing 16-byte tail are
  not rewritten by this command family.
- `--expect-active A|B` is a safety guard only. It checks the live preset state
  before upload and aborts on mismatch.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Iterable, Optional

from dlcp_fw.flash.dlcp_control_flash import (
    DEFAULT_PID,
    DEFAULT_VID,
    HidDeviceInfo,
    _hid_read64,
    _hid_write64,
    _mk_report,
)
from dlcp_fw.flash.dlcp_ep0_eeprom_shadow_dump import DlcpEp0
from dlcp_fw.flash.dlcp_main_flash import (
    DeviceSnapshot,
    _cmd03_write_filename_slot,
    _device_mode,
    _force_active_filename_persist,
    _is_diag_memread_unavailable_error,
    _list_devices_with_mode,
    _open_hid,
    _pick_device,
    _print_device_snapshot,
    _probe_device_snapshot,
    decode_filename_slot,
)
from dlcp_fw.flash.read_coeffs import (
    CaptureResult,
    HidMemoryReader,
    capture_preset,
)


TABLE_SIZE = 0x0A00
SLOT_SIZE = 0x18
SLOT_PAYLOAD_SIZE = 0x14
SLOT_COUNT = TABLE_SIZE // SLOT_SIZE
TAIL_SIZE = TABLE_SIZE - (SLOT_COUNT * SLOT_SIZE)

UPLOAD_CMD_FIRST = 0x07
UPLOAD_CMD_MIDDLE = (0x08, 0x09, 0x0A, 0x0B)
UPLOAD_CMD_LAST = 0x0C

ACTIVE_FLAGS_ADDR = 0x05E
ACTIVE_PRESET_MASK = 0x04
NAME_LEN = 0x1E


def _parse_int_auto(s: str) -> int:
    return int(s, 0)


def _path_text(path: bytes | None) -> str:
    if path is None:
        return "<no-path>"
    return path.decode("utf-8", errors="replace")


def _slot_headers(table: bytes) -> list[bytes]:
    headers: list[bytes] = []
    for idx in range(SLOT_COUNT):
        start = idx * SLOT_SIZE
        headers.append(table[start : start + 4])
    return headers


def _slot_payloads(table: bytes) -> list[bytes]:
    payloads: list[bytes] = []
    for idx in range(SLOT_COUNT):
        start = idx * SLOT_SIZE
        slot = table[start : start + SLOT_SIZE]
        if len(slot) != SLOT_SIZE:
            raise RuntimeError(f"short slot {idx}: got {len(slot)} bytes")
        payloads.append(slot[4:24])
    return payloads


def _build_upload_reports(table: bytes) -> list[tuple[int, bytes]]:
    if len(table) != TABLE_SIZE:
        raise RuntimeError(f"table has {len(table)} bytes, expected {TABLE_SIZE}")

    reports: list[tuple[int, bytes]] = []
    payloads = _slot_payloads(table)
    for idx, payload in enumerate(payloads):
        if idx == 0:
            cmd = UPLOAD_CMD_FIRST
        elif idx == len(payloads) - 1:
            cmd = UPLOAD_CMD_LAST
        else:
            cmd = UPLOAD_CMD_MIDDLE[(idx - 1) % len(UPLOAD_CMD_MIDDLE)]
        report = _mk_report(cmd)
        report[1] = 0x00
        report[2] = 0x00
        report[3] = 0x00
        report[4 : 4 + SLOT_PAYLOAD_SIZE] = payload
        reports.append((cmd, bytes(report)))
    return reports


def _load_table(path: Path) -> bytes:
    table = path.read_bytes()
    if len(table) != TABLE_SIZE:
        raise RuntimeError(f"{path} has {len(table)} bytes, expected {TABLE_SIZE}")
    return table


def _load_name_slot_from_json(path: Path) -> tuple[bytes, str]:
    meta = json.loads(path.read_text(encoding="utf-8"))
    raw_hex = str(meta.get("config_name_raw_hex", ""))
    config_name = str(meta.get("config_name", ""))
    if len(raw_hex) != NAME_LEN * 2:
        raise RuntimeError(f"{path} has invalid config_name_raw_hex length")
    slot = bytes.fromhex(raw_hex)
    if len(slot) != NAME_LEN:
        raise RuntimeError(f"{path} has invalid config_name_raw_hex payload")
    return slot, config_name


def _encode_name_slot(name: str) -> bytes:
    raw = name.encode("ascii", errors="strict")[:NAME_LEN]
    return raw + (b"\xFF" * (NAME_LEN - len(raw)))


def _resolve_name_slot(
    *,
    table_path: Path,
    explicit_name: str | None,
    explicit_json: Path | None,
) -> tuple[bytes, str] | None:
    if explicit_name is not None:
        slot = _encode_name_slot(explicit_name)
        return slot, explicit_name

    json_path = explicit_json if explicit_json is not None else table_path.with_suffix(".json")
    if json_path.exists():
        return _load_name_slot_from_json(json_path)
    return None


def _warn_non_transmitted_bytes(table: bytes) -> list[str]:
    warnings: list[str] = []
    tail = table[SLOT_COUNT * SLOT_SIZE :]
    if len(tail) != TAIL_SIZE:
        warnings.append(
            f"unexpected table tail size {len(tail)} (expected {TAIL_SIZE})"
        )
    elif any(b not in (0x00, 0xFF) for b in tail):
        warnings.append(
            "table tail contains non-padding bytes; stock HID upload does not "
            "rewrite the trailing 16-byte region"
        )
    return warnings


def _transmitted_diff_offset(got: bytes, expected: bytes) -> Optional[int]:
    if len(got) != len(expected):
        raise ValueError("length mismatch")
    for slot_idx in range(SLOT_COUNT):
        base = slot_idx * SLOT_SIZE
        for off in range(4, SLOT_SIZE):
            idx = base + off
            if got[idx] != expected[idx]:
                return idx
    return None


def _untransmitted_diff_offset(got: bytes, expected: bytes) -> Optional[int]:
    if len(got) != len(expected):
        raise ValueError("length mismatch")
    for slot_idx in range(SLOT_COUNT):
        base = slot_idx * SLOT_SIZE
        for off in range(0, 4):
            idx = base + off
            if got[idx] != expected[idx]:
                return idx
    for idx in range(SLOT_COUNT * SLOT_SIZE, len(expected)):
        if got[idx] != expected[idx]:
            return idx
    return None


def _probe_active_preset(*, vid: int, pid: int, path: bytes | None = None) -> str:
    ep0 = DlcpEp0(vid=vid, pid=pid, path=path)
    ep0.set_pointer(ACTIVE_FLAGS_ADDR)
    data = ep0.read_exact(1)
    if len(data) != 1:
        raise RuntimeError(f"short EP0 read at 0x{ACTIVE_FLAGS_ADDR:04X}")
    return "B" if (data[0] & ACTIVE_PRESET_MASK) else "A"


def _looks_like_upload_ack(resp: bytes, *, expected_cmd: int) -> bool:
    if len(resp) != 64:
        return False
    if resp[0] == (expected_cmd & 0xFF):
        return True
    if resp[0] == 0x00 and len(resp) >= 2 and resp[1] in (0x00, expected_cmd & 0xFF):
        return True
    return False


def _exchange_upload_report(
    dev,
    *,
    cmd: int,
    report: bytes,
    timeout_ms: int,
) -> bytes:
    _hid_write64(dev, report)
    deadline = time.monotonic() + (max(1, timeout_ms) / 1000.0)
    ignored: list[int] = []
    while True:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        if remaining_ms <= 0:
            if ignored:
                ignored_text = ", ".join(f"0x{x:02X}" for x in ignored[:8])
                raise RuntimeError(
                    "timed out waiting for upload ack after ignoring "
                    f"{len(ignored)} unrelated HID report(s): {ignored_text}"
                )
            raise RuntimeError("timed out waiting for upload ack")
        resp = _hid_read64(dev, timeout_ms=remaining_ms)
        if resp is None:
            if ignored:
                ignored_text = ", ".join(f"0x{x:02X}" for x in ignored[:8])
                raise RuntimeError(
                    "timed out waiting for upload ack after ignoring "
                    f"{len(ignored)} unrelated HID report(s): {ignored_text}"
                )
            raise RuntimeError("timed out waiting for upload ack")
        if _looks_like_upload_ack(resp, expected_cmd=cmd):
            return resp
        first = resp[0] if resp else -1
        ignored.append(first & 0xFF)


def _stream_upload(
    dev,
    *,
    reports: Iterable[tuple[int, bytes]],
    timeout_ms: int,
    verbose: bool,
) -> None:
    reports_list = list(reports)
    total = len(reports_list)
    for idx, (cmd, report) in enumerate(reports_list, start=1):
        _exchange_upload_report(dev, cmd=cmd, report=report, timeout_ms=timeout_ms)
        if verbose or idx == 1 or idx == total or (idx % 8) == 0:
            print(f"  slot {idx:03d}/{total:03d} cmd=0x{cmd:02X}")


def _verify_uploaded_active_bank(
    *,
    info: HidDeviceInfo,
    active_preset: str,
    expected_table: bytes,
    expected_name_slot: bytes | None,
    timeout_ms: int,
    verify_reads: int,
    retries: int,
    delay_s: float,
) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    try:
        with HidMemoryReader(info=info, timeout_ms=timeout_ms) as reader:
            result: CaptureResult = capture_preset(
                reader=reader,
                preset=active_preset,
                verify_reads=verify_reads,
                retries=retries,
                delay_s=delay_s,
            )
    except Exception as exc:
        if _is_diag_memread_unavailable_error(exc):
            warnings.append(f"diag memread verify skipped; {exc}")
            return False, warnings
        raise

    diff = _transmitted_diff_offset(result.table, expected_table)
    if diff is not None:
        raise RuntimeError(
            "post-upload transmitted-byte verify failed at "
            f"offset 0x{diff:04X}: got 0x{result.table[diff]:02X}, "
            f"expected 0x{expected_table[diff]:02X}"
        )

    non_tx_diff = _untransmitted_diff_offset(result.table, expected_table)
    if non_tx_diff is not None:
        warnings.append(
            "live flash differs outside the transmitted-byte subset at "
            f"offset 0x{non_tx_diff:04X}; headers/tail are not rewritten by the "
            "stock HID upload family"
        )

    if expected_name_slot is not None and result.name_slot != expected_name_slot:
        raise RuntimeError(
            "post-upload EEPROM name verify failed: "
            f"got {result.name_slot.hex()}, expected {expected_name_slot.hex()}"
        )
    return True, warnings


def _print_upload_summary(
    *,
    table_path: Path,
    table: bytes,
    active_preset: str | None,
    name_slot_info: tuple[bytes, str] | None,
) -> None:
    print("upload request:")
    if active_preset is None:
        print("  active preset: unavailable")
    else:
        print(f"  active preset: {active_preset}")
    print(f"  table: {table_path}")
    print(f"  bytes: 0x{len(table):04X}")
    print(f"  slots: {SLOT_COUNT}")
    print(f"  trailing bytes not directly rewritten: {TAIL_SIZE}")
    if name_slot_info is None:
        print("  config name: <unchanged>")
    else:
        print(f"  config name: {name_slot_info[1]!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Upload a preset table using the stock MAIN HID coefficient-upload "
            "command family. Upload always targets the currently active bank."
        )
    )
    ap.add_argument("--vid", type=_parse_int_auto, default=DEFAULT_VID)
    ap.add_argument("--pid", type=_parse_int_auto, default=DEFAULT_PID)
    ap.add_argument("--path", default=None, help="explicit HID path (UTF-8 text)")
    ap.add_argument("--list", action="store_true", help="list matching HID devices and exit")
    ap.add_argument("--info-only", action="store_true", help="print current device info and exit")
    ap.add_argument("--table", type=Path, default=None, help="raw 0x0A00-byte preset table to upload")
    ap.add_argument("--name", default=None, help="ASCII config name to write to the active slot after upload")
    ap.add_argument(
        "--name-from-json",
        type=Path,
        default=None,
        help="JSON sidecar with config_name/config_name_raw_hex (defaults to TABLE.json if present)",
    )
    ap.add_argument(
        "--expect-active",
        choices=("A", "B"),
        default=None,
        help="safety check only: abort unless the current active preset matches",
    )
    ap.add_argument("--timeout-ms", type=int, default=1000, help="HID timeout per upload report")
    ap.add_argument("--verify-reads", type=int, default=2, help="diag memread verify count when available")
    ap.add_argument("--retries", type=int, default=2, help="diag memread retries when available")
    ap.add_argument("--delay-s", type=float, default=0.025, help="inter-read delay for diag memread verification")
    ap.add_argument("--verbose", action="store_true", help="print per-slot upload progress")
    args = ap.parse_args(argv)

    if args.list:
        print(json.dumps(_list_devices_with_mode(args.vid, args.pid), indent=2, default=str))
        return 0

    path = args.path.encode("utf-8") if args.path is not None else None
    info = _pick_device(args.vid, args.pid, path)
    snapshot: DeviceSnapshot = _probe_device_snapshot(info=info, vid=args.vid, pid=args.pid)
    _print_device_snapshot("device info:", snapshot)
    info_path = getattr(info, "path", None)
    print(f"  hid path: {_path_text(info_path)}")

    active_preset: str | None = None
    try:
        active_preset = _probe_active_preset(vid=args.vid, pid=args.pid, path=path)
        print(f"  active preset: {active_preset}")
    except Exception as exc:
        print(f"  warning: active preset probe failed: {exc}")

    if args.info_only:
        return 0

    if args.table is None:
        ap.error("--table is required unless --info-only is used")

    table = _load_table(args.table)
    name_slot_info = _resolve_name_slot(
        table_path=args.table,
        explicit_name=args.name,
        explicit_json=args.name_from_json,
    )
    _print_upload_summary(
        table_path=args.table,
        table=table,
        active_preset=active_preset,
        name_slot_info=name_slot_info,
    )
    for warning in _warn_non_transmitted_bytes(table):
        print(f"  warning: {warning}")

    if args.expect_active is not None:
        if active_preset is None:
            raise RuntimeError(
                f"--expect-active {args.expect_active} requested but active preset could not be probed"
            )
        if active_preset != args.expect_active:
            raise RuntimeError(
                f"active preset mismatch: device reports {active_preset}, "
                f"expected {args.expect_active}"
            )

    if info_path is None:
        raise RuntimeError("selected HID device has no path")

    reports = _build_upload_reports(table)
    dev = _open_hid(info_path)
    try:
        print("streaming coeffs via stock HID upload...")
        _stream_upload(dev, reports=reports, timeout_ms=args.timeout_ms, verbose=args.verbose)

        if name_slot_info is not None:
            print("filename finalize:")
            live_slot = _cmd03_write_filename_slot(dev, name_slot=name_slot_info[0])
            print(f"  wrote active filename RAM slot: {decode_filename_slot(live_slot)!r}")
            try:
                changed = _force_active_filename_persist(
                    vid=args.vid,
                    pid=args.pid,
                    path=info_path,
                )
            except Exception as exc:
                print(f"  warning: active filename EEPROM persist trigger failed: {exc}")
            else:
                if changed:
                    print("  forced EEPROM persist: OK")
                else:
                    print("  forced EEPROM persist: already clean")
    finally:
        try:
            dev.close()
        except Exception:
            pass

    post_info = _pick_device(args.vid, args.pid, path)
    post_snapshot = _probe_device_snapshot(info=post_info, vid=args.vid, pid=args.pid)
    post_active_preset: str | None = None
    try:
        post_active_preset = _probe_active_preset(
            vid=args.vid,
            pid=args.pid,
            path=post_info.path,
        )
    except Exception:
        post_active_preset = active_preset

    print("post-upload verify:")
    if post_active_preset is None:
        print("  active preset: unavailable")
    else:
        print(f"  active preset: {post_active_preset}")

    verified, verify_warnings = _verify_uploaded_active_bank(
        info=post_info,
        active_preset=post_active_preset or "A",
        expected_table=table,
        expected_name_slot=name_slot_info[0] if name_slot_info is not None else None,
        timeout_ms=args.timeout_ms,
        verify_reads=args.verify_reads,
        retries=args.retries,
        delay_s=args.delay_s,
    )
    if verified:
        print("  diag memread transmitted-byte check: passed")
        if name_slot_info is not None:
            print("  diag memread EEPROM name check: passed")
    for warning in verify_warnings:
        print(f"  warning: {warning}")

    print("result:")
    print("  upload complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
