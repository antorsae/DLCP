#!/usr/bin/env python3
"""Read V3.2 rev 0x37 Tier-1 diagnostic snapshot via HID cmd 0x44.

Implements the host side of V32_DIAG_TIER1_SPEC.md §"HID protocol
extension -- new cmd 0x44".  Returns a structured :class:`DiagSnapshot`
holding the 7 runtime counters (I D S B R A P) + 4 reset-cause flags
(O V W X) populated by the MAIN cold-init RCON classification cascade.

Round-5 spec note: cmd 0x44 returns an 11-byte payload (length byte at
response[2] = 0x0B) containing only the cell values -- the firmware-
revision trailer was dropped to fit the PIC18F2455 flash budget.
Hosts that need the rev tuple call the existing cmd 0x06 version
probe separately (this module bundles both into :func:`query_diag`).

Status classification (see V32_DIAG_TIER1_SPEC.md §"Status
classification") is advisory; raw counters in the snapshot are
authoritative.
"""

from __future__ import annotations

import dataclasses
import time
from typing import List, Optional, Tuple

from dlcp_fw.flash.dlcp_control_flash import (
    DEFAULT_PID,
    DEFAULT_VID,
    HidDeviceInfo,
    enumerate_devices,
)
from dlcp_fw.flash.dlcp_main_flash import (
    VersionInfo,
    _exchange_report,
    _exchange_report_with_retry,
    _mk_report,
    _open_hid,
    _pick_device,
    _probe_cmd06_version,
)


CMD44_DIAG_SUBCMD = 0x00            # request subcmd byte (reserved future)
CMD44_EXPECTED_LENGTH_BYTE = 0x0B   # response[2] -- 11 cells
CMD44_PAYLOAD_OFFSET = 3            # response[3..13] holds the 11 cells
CMD44_RUNTIME_COUNT = 7             # I D S B R A P
CMD44_RESET_COUNT = 4               # O V W X
CMD44_TOTAL_CELLS = CMD44_RUNTIME_COUNT + CMD44_RESET_COUNT  # 11

RUNTIME_LETTERS = ("I", "D", "S", "B", "R", "A", "P")
RESET_LETTERS = ("O", "V", "W", "X")
RESET_LABELS = {
    "O": "POR -- power-on",
    "V": "BOR -- brown-out",
    "W": "WDT -- watchdog timeout",
    "X": "SW  -- software reset (panic / bootloader hand-off)",
}
RESET_NAMES = {"O": "por", "V": "bor", "W": "wdt", "X": "sw"}

# Tier-1 saturation marker emitted by the diag_inc_sat macro on MAIN.
# Values reach 0x0F when the underlying event class accumulates >= 15
# occurrences in this session.
SATURATED_VALUE = 0x0F


@dataclasses.dataclass(frozen=True)
class DiagSnapshot:
    """One V3.2 rev 0x37 cmd 0x44 response, parsed.

    Order of fields exactly mirrors the on-wire layout so a future
    extension that grows the payload can simply add fields here.
    """

    # 7 runtime counters (each 0..0x0F per the diag_inc_sat saturation cap)
    diag_i: int
    diag_d: int
    diag_s: int
    diag_b: int
    diag_r: int
    diag_a: int
    diag_p: int
    # 4 reset-cause flags (each 0 or 1; exactly one is 1 per session)
    diag_reset_por: int
    diag_reset_bor: int
    diag_reset_wdt: int
    diag_reset_sw: int

    @property
    def runtime_counters(self) -> Tuple[int, ...]:
        return (
            self.diag_i,
            self.diag_d,
            self.diag_s,
            self.diag_b,
            self.diag_r,
            self.diag_a,
            self.diag_p,
        )

    @property
    def reset_flags(self) -> Tuple[int, ...]:
        return (
            self.diag_reset_por,
            self.diag_reset_bor,
            self.diag_reset_wdt,
            self.diag_reset_sw,
        )

    @property
    def runtime_nonzero_count(self) -> int:
        return sum(1 for v in self.runtime_counters if v > 0)

    @property
    def active_reset_cause(self) -> Optional[str]:
        """Spelled-out label for whichever reset flag is set, or None
        if all four are zero (which would indicate a corrupted cold
        init and shouldn't happen in practice).
        """
        for letter, value in zip(RESET_LETTERS, self.reset_flags):
            if value:
                return RESET_NAMES[letter]
        return None


def parse_cmd44_diag_response(resp: bytes) -> DiagSnapshot:
    """Parse a 64-byte HID IN response from cmd 0x44 into a snapshot.

    Validates the cmd echo, status, and length byte.  Trailing bytes
    (response[14..63]) are NOT zero/0xFF-validated -- the firmware
    explicitly leaves those bytes unspecified in round-5 to save
    flash; the host MUST stop reading at byte 13 per the length byte.
    """
    if len(resp) < CMD44_PAYLOAD_OFFSET + CMD44_TOTAL_CELLS:
        raise RuntimeError(
            f"short cmd 0x44 response: {len(resp)} bytes "
            f"(need >= {CMD44_PAYLOAD_OFFSET + CMD44_TOTAL_CELLS})"
        )
    # Some HID stacks prefix a leading 0x00 report-id byte; tolerate.
    base = 0
    if resp[0] == 0x00 and len(resp) >= 4 and resp[1] == 0x44:
        base = 1
    elif resp[0] != 0x44:
        raise RuntimeError(f"unexpected cmd 0x44 echo: 0x{resp[0]:02X}")
    status = resp[base + 1]
    if status != 0x00:
        raise RuntimeError(f"cmd 0x44 status byte non-zero: 0x{status:02X}")
    length_byte = resp[base + 2]
    if length_byte != CMD44_EXPECTED_LENGTH_BYTE:
        raise RuntimeError(
            f"cmd 0x44 length byte mismatch: got 0x{length_byte:02X}, "
            f"expected 0x{CMD44_EXPECTED_LENGTH_BYTE:02X} -- the firmware "
            f"may be a pre-rev-0x37 build that doesn't implement cmd 0x44 "
            f"per V32_DIAG_TIER1_SPEC.md"
        )
    payload_start = base + CMD44_PAYLOAD_OFFSET
    cells = resp[payload_start : payload_start + CMD44_TOTAL_CELLS]
    if len(cells) < CMD44_TOTAL_CELLS:
        raise RuntimeError(f"cmd 0x44 payload truncated: {len(cells)} cells")
    return DiagSnapshot(
        diag_i=cells[0],
        diag_d=cells[1],
        diag_s=cells[2],
        diag_b=cells[3],
        diag_r=cells[4],
        diag_a=cells[5],
        diag_p=cells[6],
        diag_reset_por=cells[7],
        diag_reset_bor=cells[8],
        diag_reset_wdt=cells[9],
        diag_reset_sw=cells[10],
    )


def _probe_cmd44_diag(
    dev,
    *,
    timeout_ms: int = 1000,
    attempts: int = 3,
    retry_delay_s: float = 0.05,
) -> DiagSnapshot:
    """Send cmd 0x44 via the open HID device and parse the response."""
    report = _mk_report(0x44)
    report[1] = CMD44_DIAG_SUBCMD
    last_exc: Optional[RuntimeError] = None
    for attempt in range(max(1, attempts)):
        try:
            resp = _exchange_report(dev, bytes(report), timeout_ms=timeout_ms)
            return parse_cmd44_diag_response(resp)
        except RuntimeError as exc:
            last_exc = exc
            if attempt + 1 >= max(1, attempts):
                raise
            time.sleep(retry_delay_s)
    assert last_exc is not None
    raise last_exc


@dataclasses.dataclass(frozen=True)
class DiagReport:
    """Combined per-MAIN result: HID device info + version + diag snapshot."""

    info: HidDeviceInfo
    version: Optional[VersionInfo]
    snapshot: DiagSnapshot
    status: str
    alerts: Tuple[str, ...]


def query_diag(
    *,
    vid: int = DEFAULT_VID,
    pid: int = DEFAULT_PID,
    path: Optional[bytes] = None,
    timeout_ms: int = 1000,
) -> DiagReport:
    """Open one HID device, query cmd 0x06 (version) + cmd 0x44 (diag),
    and return a combined :class:`DiagReport`.

    If multiple HID devices match VID:PID, ``path`` must be specified.
    """
    info = _pick_device(vid, pid, path)
    dev = _open_hid(info.path)
    try:
        try:
            version = _probe_cmd06_version(dev, timeout_ms=timeout_ms)
        except RuntimeError:
            version = None
        snapshot = _probe_cmd44_diag(dev, timeout_ms=timeout_ms)
    finally:
        try:
            dev.close()
        except Exception:
            pass
    status, alerts = classify_status(snapshot)
    return DiagReport(info=info, version=version, snapshot=snapshot, status=status, alerts=alerts)


def query_all_diags(
    *,
    vid: int = DEFAULT_VID,
    pid: int = DEFAULT_PID,
    timeout_ms: int = 1000,
) -> List[DiagReport]:
    """Enumerate every matching HID device and query each.

    Per-device errors are surfaced by raising; the caller can wrap
    individual ``query_diag`` calls if it wants partial results.
    """
    devices = enumerate_devices(vid, pid)
    return [
        query_diag(vid=vid, pid=pid, path=dev.path, timeout_ms=timeout_ms)
        for dev in devices
    ]


def classify_status(snapshot: DiagSnapshot) -> Tuple[str, Tuple[str, ...]]:
    """Return ``(status, alerts)`` per V32_DIAG_TIER1_SPEC.md
    §"Status classification".

    * HEALTHY  -- only POR=1 and at most one S+B pair (one standby /
                  bring-up cycle is the expected boot sequence).
    * DEGRADED -- any runtime counter at non-zero, or any unexpected
                  reset flag (V/W/X) set.
    * CRITICAL -- any counter saturated to 0x0F (15+ occurrences),
                  or W (WDT) > 0.
    """
    alerts: List[str] = []

    # CRITICAL conditions take precedence.
    if snapshot.diag_reset_wdt > 0:
        alerts.append("watchdog_reset_this_session")
    saturated = [
        f"{letter}_saturated"
        for letter, value in zip(RUNTIME_LETTERS, snapshot.runtime_counters)
        if value >= SATURATED_VALUE
    ]
    alerts.extend(saturated)
    if alerts:
        # Add full nonzero details for context even on CRITICAL.
        alerts.extend(_runtime_nonzero_alerts(snapshot))
        return ("CRITICAL", tuple(_dedup_preserving_order(alerts)))

    # DEGRADED: any runtime > 0 (other than the expected one S + one B
    # boot pair) OR any unexpected reset flag (BOR or SW-reset).
    expected_only = (
        snapshot.diag_reset_por == 1
        and snapshot.diag_reset_bor == 0
        and snapshot.diag_reset_wdt == 0
        and snapshot.diag_reset_sw == 0
        and snapshot.diag_i == 0
        and snapshot.diag_d == 0
        and snapshot.diag_s in (0, 1)
        and snapshot.diag_b in (0, 1)
        and snapshot.diag_r == 0
        and snapshot.diag_a == 0
        and snapshot.diag_p == 0
    )
    if expected_only:
        return ("HEALTHY", ())

    if snapshot.diag_reset_bor > 0:
        alerts.append("brown_out_reset_this_session")
    if snapshot.diag_reset_sw > 0:
        alerts.append("software_reset_this_session")
    alerts.extend(_runtime_nonzero_alerts(snapshot))
    if alerts:
        return ("DEGRADED", tuple(_dedup_preserving_order(alerts)))

    # Unexpected: no runtime counters, no unexpected resets, but also
    # not the expected POR-only pattern (e.g. all reset flags clear).
    # Surface as DEGRADED with an explicit "unknown" alert.
    return ("DEGRADED", ("no_reset_cause_flag_set",))


def _runtime_nonzero_alerts(snapshot: DiagSnapshot) -> List[str]:
    out: List[str] = []
    name_map = {
        "I": "i2c_transport_faults",
        "D": "dsp_fault",
        "S": "standby_dispatches",
        "B": "bring_up_dispatches",
        "R": "recovery_branch_entries",
        "A": "an0_standby_triggers",
        "P": "ra1_edge_events",
    }
    for letter, value in zip(RUNTIME_LETTERS, snapshot.runtime_counters):
        if value > 0:
            out.append(f"{name_map[letter]}={value}")
    return out


def _dedup_preserving_order(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


# ===========================================================================
# CLI
# ===========================================================================


def _format_version(version: Optional[VersionInfo]) -> str:
    if version is None:
        return "<unknown>"
    flag = version.flag
    major = version.major
    rev = version.minor
    family = "V3.x" if flag == 3 else f"flag=0x{flag:02X}"
    return f"{family}.{major} rev 0x{rev:02X}"


def _format_runtime_line(snapshot: DiagSnapshot) -> str:
    parts = [f"{letter}{value}" for letter, value in zip(RUNTIME_LETTERS, snapshot.runtime_counters)]
    return "Runtime:   " + " ".join(parts)


def _format_reset_line(snapshot: DiagSnapshot) -> str:
    parts = [f"{letter}{value}" for letter, value in zip(RESET_LETTERS, snapshot.reset_flags)]
    active = snapshot.active_reset_cause
    if active is None:
        tail = "(no flag set -- corrupted cold-init?)"
    else:
        active_letter = next(L for L in RESET_LETTERS if RESET_NAMES[L] == active)
        tail = f"({RESET_LABELS[active_letter]})"
    return "Reset:     " + " ".join(parts) + "     " + tail


def _format_status_line(report: "DiagReport") -> str:
    if not report.alerts:
        return f"Status:    {report.status}"
    return f"Status:    {report.status} (" + ", ".join(report.alerts) + ")"


def _format_human_report(reports: List["DiagReport"], *, ts: Optional[str] = None) -> str:
    if ts is None:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines: List[str] = []
    lines.append(f"DLCP Diagnostics  ({ts})")
    lines.append("=" * 40)
    lines.append("")
    if not reports:
        lines.append("No DLCP HID devices detected.")
        return "\n".join(lines)
    for report in reports:
        path_text = (
            report.info.path.decode("utf-8", errors="replace")
            if report.info.path is not None
            else "<no-path>"
        )
        # Role is operator-derived from HID path mapping; we don't infer
        # a side identity from the firmware (rev 0x37 cmd 0x44 omits
        # the role byte in the round-5 trailer-drop; cmd 0x06 doesn't
        # carry it either).
        lines.append(f"HID {path_text}  {_format_version(report.version)}")
        lines.append("  " + _format_runtime_line(report.snapshot))
        lines.append("  " + _format_reset_line(report.snapshot))
        lines.append("  " + _format_status_line(report))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_json_report(reports: List["DiagReport"], *, ts: Optional[str] = None) -> str:
    import json

    if ts is None:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out = {
        "ts": ts,
        "spec_rev": "V32_DIAG_TIER1",
        "mains": [],
    }
    for report in reports:
        snap = report.snapshot
        version_obj: dict[str, object] | None = None
        if report.version is not None:
            version_obj = {
                "flag": report.version.flag,
                "major": report.version.major,
                "rev": report.version.minor,
                "rev_hex": f"0x{report.version.minor:02X}",
            }
        path_text = (
            report.info.path.decode("utf-8", errors="replace")
            if report.info.path is not None
            else None
        )
        out["mains"].append(
            {
                "hid_path": path_text,
                "product_string": report.info.product_string,
                "serial_number": report.info.serial_number,
                "version": version_obj,
                "counters": {
                    "i": snap.diag_i,
                    "d": snap.diag_d,
                    "s": snap.diag_s,
                    "b": snap.diag_b,
                    "r": snap.diag_r,
                    "a": snap.diag_a,
                    "p": snap.diag_p,
                },
                "reset_cause": {
                    "por": snap.diag_reset_por,
                    "bor": snap.diag_reset_bor,
                    "wdt": snap.diag_reset_wdt,
                    "sw": snap.diag_reset_sw,
                    "active": snap.active_reset_cause,
                },
                "status": report.status,
                "nonzero_count": snap.runtime_nonzero_count,
                "alerts": list(report.alerts),
            }
        )
    return json.dumps(out, indent=2) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    """Operator CLI -- enumerate all DLCP MAINs and print their cmd 0x44
    diagnostic snapshots.

    Default output is human-readable; ``--json`` switches to a structured
    report suitable for CI / scripting / time-series logging.
    """
    import argparse

    def _parse_int_auto(s: str) -> int:
        return int(s, 0)

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vid", type=_parse_int_auto, default=DEFAULT_VID, help="USB VID (default: 0x04D8)")
    ap.add_argument("--pid", type=_parse_int_auto, default=DEFAULT_PID, help="USB PID (default: 0xFF89)")
    ap.add_argument(
        "--path",
        default=None,
        help="explicit HID device path (UTF-8); query just this MAIN",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="emit a JSON report instead of human-readable text",
    )
    ap.add_argument(
        "--watch",
        action="store_true",
        help="loop and re-query every --interval seconds (Ctrl-C to exit)",
    )
    ap.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="poll interval in seconds when --watch is set (default: 5.0)",
    )
    ap.add_argument(
        "--timeout-ms",
        type=int,
        default=1000,
        help="HID exchange timeout per cmd 0x06 / cmd 0x44 query (default: 1000)",
    )
    args = ap.parse_args(argv)

    path_bytes = args.path.encode("utf-8") if args.path is not None else None

    def _collect_one_pass() -> List[DiagReport]:
        if path_bytes is not None:
            return [
                query_diag(
                    vid=args.vid,
                    pid=args.pid,
                    path=path_bytes,
                    timeout_ms=args.timeout_ms,
                )
            ]
        # Per-device errors: print the failure inline so a single bad
        # MAIN doesn't kill enumeration of the rest.
        results: List[DiagReport] = []
        for dev in enumerate_devices(args.vid, args.pid):
            try:
                results.append(
                    query_diag(
                        vid=args.vid,
                        pid=args.pid,
                        path=dev.path,
                        timeout_ms=args.timeout_ms,
                    )
                )
            except RuntimeError as exc:
                # Surface to stderr; continue with remaining devices.
                import sys

                path_text = (
                    dev.path.decode("utf-8", errors="replace")
                    if dev.path is not None
                    else "<no-path>"
                )
                print(
                    f"WARNING: cmd 0x44 query failed for {path_text}: {exc}",
                    file=sys.stderr,
                )
        return results

    def _emit(reports: List[DiagReport]) -> None:
        if args.json:
            print(_format_json_report(reports), end="")
        else:
            print(_format_human_report(reports), end="")

    if not args.watch:
        _emit(_collect_one_pass())
        return 0

    # Watch mode.  Print a separator between iterations so the operator
    # can tell where one snapshot ends and the next begins.
    while True:
        try:
            _emit(_collect_one_pass())
        except KeyboardInterrupt:
            return 0
        if not args.json:
            print("--- next pass in {:.1f}s ---".format(args.interval))
        try:
            time.sleep(max(0.0, args.interval))
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
