#!/usr/bin/env python3
"""Query or switch the active DLCP preset over USB.

Important distinction:
  - preset select `cmd 0x20` exists in the MAIN current-loop/UART parser
  - it does NOT exist in the stock MAIN app HID command decoder
  - active preset state is reflected in `active_flags` bit 2 (`0x05E.2`)

Query uses EP0 RAM readback. Switch uses EP0 RAM writes on `active_flags`:
  - bit 2 selects preset A/B
  - bit 7 requests the same DSP re-apply path used after HID coefficient upload

This does not use a stock HID preset command because no such command exists in
the application HID decoder.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Optional

from dlcp_fw.flash.dlcp_control_flash import (
    DEFAULT_PID,
    DEFAULT_VID,
)
from dlcp_fw.flash.dlcp_main_flash import (
    ACTIVE_REAPPLY_MASK,
    DeviceSnapshot,
    _active_preset_from_flags,
    _describe_active_flags,
    _probe_active_preset_ep0,
    _read_active_flags_ep0,
    _list_devices_with_mode,
    _pick_device,
    _print_device_snapshot,
    _probe_device_snapshot,
    _request_active_preset_switch_ep0,
)


def _parse_int_auto(s: str) -> int:
    return int(s, 0)


def _path_text(path: bytes | None) -> str:
    if path is None:
        return "<no-path>"
    return path.decode("utf-8", errors="replace")


def _write_preset_switch_ep0(
    *,
    vid: int,
    pid: int,
    preset: str,
    path: bytes | None = None,
) -> dict[str, int]:
    return _request_active_preset_switch_ep0(vid=vid, pid=pid, preset=preset, path=path)


def _wait_for_active_preset(
    *,
    vid: int,
    pid: int,
    path: bytes | None,
    expected: str,
    timeout_s: float,
    poll_interval_s: float,
    stable_reads: int = 2,
) -> str:
    deadline = time.monotonic() + max(0.0, timeout_s)
    consecutive_ready = 0
    last_flags: Optional[int] = None
    last_exc: Optional[Exception] = None
    while True:
        try:
            flags = _read_active_flags_ep0(vid=vid, pid=pid, path=path)
            last_flags = flags
            current = _active_preset_from_flags(flags)
            ready = current == expected and not (flags & ACTIVE_REAPPLY_MASK)
            if ready:
                consecutive_ready += 1
                if consecutive_ready >= max(1, stable_reads):
                    return current
            else:
                consecutive_ready = 0
        except Exception as exc:  # pragma: no cover - exercised by CLI behavior
            last_exc = exc

        if time.monotonic() >= deadline:
            if last_flags is not None:
                raise RuntimeError(
                    "preset switch verify failed: device reports "
                    f"{_describe_active_flags(last_flags)}, expected {expected} "
                    "with reapply clear"
                )
            if last_exc is not None:
                raise RuntimeError(f"preset switch verify failed: {last_exc}") from last_exc
            raise RuntimeError("preset switch verify failed: timed out")
        time.sleep(max(0.0, poll_interval_s))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vid", type=_parse_int_auto, default=DEFAULT_VID)
    ap.add_argument("--pid", type=_parse_int_auto, default=DEFAULT_PID)
    ap.add_argument("--path", default=None, help="explicit HID path (UTF-8 text)")
    ap.add_argument("--list", action="store_true", help="list matching HID devices and exit")
    ap.add_argument("--info-only", action="store_true", help="print current preset/device info and exit")
    ap.add_argument(
        "--preset",
        choices=("A", "B"),
        default=None,
        help="switch the active preset to A or B by updating active_flags over EP0",
    )
    ap.add_argument(
        "--settle-ms",
        type=int,
        default=250,
        help="delay after EP0 switch request before verification",
    )
    ap.add_argument(
        "--verify-timeout-s",
        type=float,
        default=2.0,
        help="time budget for post-switch EP0 verification",
    )
    ap.add_argument(
        "--poll-interval-s",
        type=float,
        default=0.05,
        help="EP0 verification poll interval",
    )
    ap.add_argument("--verbose", action="store_true", help="print EP0 switch details")
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

    active_preset = _probe_active_preset_ep0(vid=args.vid, pid=args.pid, path=path)
    print(f"  active preset: {active_preset}")

    if args.info_only:
        return 0

    if args.preset is None:
        ap.error("--preset is required unless --info-only is used")

    target = args.preset
    if active_preset == target:
        print("result:")
        print(f"  preset already active: {target}")
        return 0

    print("switch request:")
    print(f"  from: {active_preset}")
    print(f"  to: {target}")
    print("  transport: EP0 active_flags toggle + DSP reapply request")
    print("warning:")
    print("  this is not the stock MAIN preset-switch command path")
    print("  CONTROL will remain out of sync with MAIN preset state until separately updated")
    print("  verification waits for active_flags.7 to clear, which confirms DSP reapply only")
    print("  active config name / filename RAM may remain stale after this EP0-only switch")

    inject = _write_preset_switch_ep0(
        vid=args.vid,
        pid=args.pid,
        preset=target,
        path=path,
    )
    if args.verbose:
        print(
            "active_flags:"
            f" before=0x{inject['active_flags_before']:02X}"
            f" write=0x{inject['active_flags_write']:02X}"
        )

    if args.settle_ms:
        time.sleep(max(0, args.settle_ms) / 1000.0)

    confirmed = _wait_for_active_preset(
        vid=args.vid,
        pid=args.pid,
        path=path,
        expected=target,
        timeout_s=max(0.0, args.verify_timeout_s),
        poll_interval_s=max(0.0, args.poll_interval_s),
    )

    post_info = _pick_device(args.vid, args.pid, path)
    post_snapshot = _probe_device_snapshot(info=post_info, vid=args.vid, pid=args.pid)
    _print_device_snapshot("after switch:", post_snapshot)
    print(f"  active preset: {confirmed}")
    print("  note: CONTROL may still show the old preset until it is explicitly resynchronized")
    print("  note: active config name is RAM-backed and may remain stale after USB-only preset switch")

    print("result:")
    print(f"  switched preset: {active_preset} -> {confirmed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
