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

    Validates the cmd echo, status, length byte, AND the payload byte
    ranges.  Counters MUST be 0..0x0F (saturated by the diag_inc_sat
    macro); reset flags MUST be 0 or 1 (cold-init writes exactly one
    flag per session).  Out-of-range bytes raise so a misframed response
    or a misbehaving device produces a fail-fast error rather than a
    plausible-looking but wrong report (codex LOW review against dc9647a).

    Trailing bytes (response[14..63]) are NOT zero/0xFF-validated -- the
    firmware explicitly leaves those bytes unspecified in round-5 to save
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
    # Range checks per spec contract (codex LOW fix vs dc9647a).
    for letter, value in zip(RUNTIME_LETTERS, cells[:CMD44_RUNTIME_COUNT]):
        if not 0 <= value <= SATURATED_VALUE:
            raise RuntimeError(
                f"cmd 0x44 runtime counter '{letter}' out of range: "
                f"got 0x{value:02X}, expected 0..0x{SATURATED_VALUE:02X} "
                f"(diag_inc_sat saturates at 0x0F; values above suggest a "
                f"misframed response or a corrupted MAIN diag block)"
            )
    for letter, value in zip(RESET_LETTERS, cells[CMD44_RUNTIME_COUNT:]):
        if value not in (0, 1):
            raise RuntimeError(
                f"cmd 0x44 reset-cause flag '{letter}' out of range: "
                f"got 0x{value:02X}, expected 0 or 1 (cold-init writes "
                f"exactly one flag per session per V32_DIAG_TIER1_SPEC)"
            )
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
    """Combined per-MAIN result: HID device info + version + diag snapshot
    + (optional) live channel-routing snapshot read via EP0.

    The ``routes`` and ``active_config_name`` fields are populated by the
    same EP0 RAM-window probe that ``dlcp_main_flash.py --info-only`` uses
    (``_probe_ep0_app_ram`` in src/dlcp_fw/flash/dlcp_main_flash.py).
    They're optional because:
      * the EP0 probe can fail (permissions, device-busy, bootloader mode);
      * the device might be in bootloader mode and not have the app
        RAM populated yet.
    On expected failure (RuntimeError / OSError / ImportError),
    ``query_diag`` prints a stderr warning and leaves the fields as None.
    Unexpected exception types (typos, signature drift, programming errors)
    are NOT caught and propagate normally so they're visible during
    development.
    """

    info: HidDeviceInfo
    version: Optional[VersionInfo]
    snapshot: DiagSnapshot
    status: str
    alerts: Tuple[str, ...]
    routes: Optional[Tuple[object, ...]] = None  # tuple[RouteEntry, ...]
    active_config_name: Optional[str] = None


# Mapping from a uniform single-route label to the operator-friendly
# channel role.  ONLY pure L and R get aliased to LEFT / RIGHT (the
# common stereo case).  Other route labels (L+R, L-R, R-L) are
# displayed AS-IS to avoid inventing alternative names that conflict
# with existing repo terminology.  HFD v2.12 UI uses "L+R/Mid" and
# "L-R/Side" (see docs/analysis/HFD_v2.12-codex.md:177); rather than
# pick one of those forms, we just echo the raw route label so the
# operator sees the same label dlcp_main_flash --info-only would show.
_ROLE_FOR_UNIFORM_ROUTE: dict[str, str] = {
    "L": "LEFT",
    "R": "RIGHT",
}


def _derive_channel_label(routes: Optional[Tuple[object, ...]]) -> str:
    """Synthesize a short channel label from the per-MAIN route table.

    All 6 outputs the same -> use the role label:
      L  -> "LEFT"  (operator-friendly alias)
      R  -> "RIGHT" (operator-friendly alias)
      others -> echo the raw route label as-is (e.g. "L+R", "L-R",
                "R-L"); avoids conflict with the HFD UI's
                "L+R/Mid"/"L-R/Side" naming.
    Mixed outputs -> "MIX"
    No routes available -> ""
    """
    if not routes:
        return ""
    labels = {r.label for r in routes}
    if len(labels) == 1:
        sole = next(iter(labels))
        return _ROLE_FOR_UNIFORM_ROUTE.get(sole, sole)
    return "MIX"


def query_diag(
    *,
    vid: int = DEFAULT_VID,
    pid: int = DEFAULT_PID,
    path: Optional[bytes] = None,
    timeout_ms: int = 1000,
    probe_routes: bool = True,
) -> DiagReport:
    """Open one HID device, query cmd 0x06 (version) + cmd 0x44 (diag),
    and (optionally) probe the channel-routing RAM window via EP0.
    Returns a combined :class:`DiagReport`.

    If multiple HID devices match VID:PID, ``path`` must be specified.

    Setting ``probe_routes=False`` skips the EP0 probe (used by tests
    that don't want to require the EP0 helper to be importable / by
    callers that just want the cmd 0x44 snapshot).
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

    routes: Optional[Tuple[object, ...]] = None
    active_config_name: Optional[str] = None
    if probe_routes:
        # Reuse the EP0 RAM-window probe shipped by dlcp_main_flash.py
        # so dlcp_diag and dlcp_main_flash speak the same channel-routing
        # language.  Failures are non-fatal in the operator-facing flow
        # (a device in bootloader mode or one that refuses EP0 access
        # still produces a usable diag report -- just without the
        # channel info), but we narrow the exception types caught so
        # that real bugs (typos, signature drift, programming errors)
        # surface as crashes rather than silent no-ops.  Non-fatal
        # categories:
        #   * RuntimeError -- the helper's own error class for unexpected
        #                     EP0 transfer states.
        #   * OSError      -- USB I/O / device-busy.  PyUSB's USBError
        #                     subclasses IOError/OSError so it lands here.
        #   * ImportError  -- missing libusb / pyusb in stripped envs.
        #   * ValueError   -- pyusb raises NoBackendError(ValueError)
        #                     when no libusb backend is loadable; codex
        #                     review of 25d6780 caught this gap.
        from dlcp_fw.flash.dlcp_main_flash import _probe_ep0_app_ram

        try:
            active_config_name, routes = _probe_ep0_app_ram(
                vid=vid, pid=pid, path=info.path,
            )
        except (RuntimeError, OSError, ImportError, ValueError) as exc:
            # Surface to stderr so the operator can correlate a missing
            # channel column with a real failure (e.g., libusb perms).
            # Don't kill the diag report -- the cmd 0x44 path is
            # independent and the rest of the snapshot is still useful.
            import sys
            print(
                f"WARNING: EP0 routes probe failed for "
                f"{info.path!r}: {exc}",
                file=sys.stderr,
            )

    status, alerts = classify_status(snapshot)
    return DiagReport(
        info=info,
        version=version,
        snapshot=snapshot,
        status=status,
        alerts=alerts,
        routes=routes,
        active_config_name=active_config_name,
    )


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
    #
    # Spec contract (codex MEDIUM fix vs dc9647a): "at most one S+B
    # PAIR" means S and B fire together as part of one boot cycle.
    # A lone S (S=1, B=0) or lone B (S=0, B=1) is a half-completed
    # boot, not a healthy boot, and should fall to DEGRADED.  Pin the
    # equality `S == B` so the only HEALTHY runtime patterns are
    # all-zero or both-one.
    expected_only = (
        snapshot.diag_reset_por == 1
        and snapshot.diag_reset_bor == 0
        and snapshot.diag_reset_wdt == 0
        and snapshot.diag_reset_sw == 0
        and snapshot.diag_i == 0
        and snapshot.diag_d == 0
        and snapshot.diag_s == snapshot.diag_b
        and snapshot.diag_s <= 1
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


# Mapping from cmd 0x06 (flag, major, minor) tuple to the EEPROM rev
# marker (third byte of the EEPROM tuple at offset 0x80..0x82).  Keep
# this in sync with the `org 0xF00000 / eeprom_data` block of each MAIN
# source file -- VERIFIED against the committed sources 2026-04-21:
#   * src/dlcp_fw/asm/dlcp_main_v30.asm:7246  -> EEPROM (0x02, 0x03, 0x30)
#     V3.0 stock-equivalent rewrite.  cmd 0x06 reports (3, 2, 3) -- the
#     SAME tuple stock V2.3 reports, by design (V3.0 keeps the stock
#     identifier so existing tools see no change).  Omitted from this
#     lookup because the cmd 0x06 tuple is ambiguous: we can't tell
#     stock V2.3 (no Tier-1, no Tier-1 spec rev) from V3.0 (no Tier-1
#     either, but a different EEPROM marker).  Both display as "V2.3"
#     without a rev suffix.
#   * src/dlcp_fw/asm/dlcp_main_v31.asm:8384  -> EEPROM (0x03, 0x01, 0x31)
#     V3.1 source rewrite.  cmd 0x43 memread; no Tier-1.
#   * src/dlcp_fw/asm/dlcp_main_v32.asm:9958  -> EEPROM (0x03, 0x02, 0x37)
#     V3.2 Phase 2.5 Tier-1 (cmd 0x22 + cmd 0x44).
#
# An earlier draft of this table mapped V3.1 -> 0x36 based on the
# Phase 2.5 commit message ("EEPROM marker bump 0x36 -> 0x37"), but
# 0x36 was an intermediate V3.x build that never shipped the V3.1
# source rewrite -- the committed V3.1 EEPROM uses 0x31.  Codex
# review of 6963cfc 2026-04-21 caught the drift; fixed in this commit.
#
# Older / unknown versions return None and the rev string is omitted.
_REV_MARKER_BY_VERSION: dict[tuple[int, int, int], int] = {
    (3, 3, 1): 0x31,   # V3.1 source rewrite
    (3, 3, 2): 0x37,   # V3.2 Tier-1 (cmd 0x22 + cmd 0x44)
}


def _rev_marker_for_version(version: Optional[VersionInfo]) -> Optional[int]:
    """Look up the EEPROM rev marker for a given cmd 0x06 version tuple.

    The EEPROM marker (e.g. 0x37 for V3.2) is NOT in the cmd 0x06 response;
    it lives at EEPROM offset 0x82 in the MAIN's EEPROM block.  Reading it
    requires either a separate EEPROM-shadow query (cmd 0x43 memread or
    similar) or static lookup from the cmd 0x06 (major, minor) tuple.
    For brevity and to avoid a second HID round-trip, this function uses
    the static lookup -- adequate as long as the lookup table stays in
    sync with the MAIN source EEPROM blocks.
    """
    if version is None:
        return None
    key = (version.flag, version.major, version.minor)
    return _REV_MARKER_BY_VERSION.get(key)


def _format_version(version: Optional[VersionInfo]) -> str:
    """Render a VersionInfo as "V{major}.{minor}" or with rev marker
    appended when available: "V{major}.{minor} rev 0xNN".

    cmd 0x06 returns 3 bytes that the firmware encodes as:
      * byte[1] = flag   (0x03 = "valid version block" marker)
      * byte[2] = major  (0x02 for V2.x family, 0x03 for V3.x family)
      * byte[3] = minor

    Examples (verified against firmware source):
      * stock V2.3:                      (3, 2, 3) -> "V2.3"
      * V3.0 (byte-equivalent rewrite):  (3, 2, 3) -> "V2.3"  -- intentional;
                                                                V3.0 keeps the
                                                                stock identifier
                                                                so existing tools
                                                                see no change.
      * V3.1 source rewrite:             (3, 3, 1) -> "V3.1"
      * V3.2 source rewrite:             (3, 3, 2) -> "V3.2"

    A previous version of this function rendered as
    `f"V{flag}.{major} rev 0x{rev:02X}"` which produced "V3.3 rev 0x02"
    for V3.2 firmware -- the format treated the major-byte as a minor
    and the minor-byte as a "rev" when those bytes are actually
    (major, minor) of the same version.

    Note: the EEPROM marker (e.g. 0x37 for V3.2) is a SEPARATE byte
    that lives in EEPROM, not in the cmd 0x06 response.  The
    "rev 0x37" string in V32_DIAG_TIER1_SPEC.md sample output was
    misleading and isn't reproducible from cmd 0x06 alone.  Drop it
    from the format until/unless we add a separate EEPROM-marker read.
    """
    if version is None:
        return "<unknown>"
    flag = version.flag
    major = version.major
    minor = version.minor
    if flag == 3 and major in (2, 3):
        rev = _rev_marker_for_version(version)
        if rev is not None:
            return f"V{major}.{minor} rev 0x{rev:02X}"
        return f"V{major}.{minor}"
    return f"flag=0x{flag:02X} major=0x{major:02X} minor=0x{minor:02X}"


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


def _resolve_channel_label(
    path_text: str,
    ch_map: Optional[dict[str, str]],
) -> str:
    """Resolve the channel label (LEFT / RIGHT / etc.) for a HID path
    from the operator-supplied ``ch_map`` dict.

    Match strategy: a map key matches if it is contained as a SUBSTRING
    of the HID path.  This lets the operator pass just the DevSrvsID
    suffix (e.g. ``LEFT=4296563925``) instead of the full path
    (``DevSrvsID:4296563925``) -- ergonomic on macOS where the path
    prefix is always identical across devices.

    Returns the label if matched, or the empty string if no match.
    Multiple matches resolve to the FIRST hit in the map (operator
    insertion order = argparse list order).  A path that doesn't match
    any key returns "" (printed as a placeholder by the caller).
    """
    if not ch_map:
        return ""
    for key, label in ch_map.items():
        if key in path_text:
            return label
    return ""


def _format_human_report(
    reports: List["DiagReport"],
    *,
    ts: Optional[str] = None,
    ch_map: Optional[dict[str, str]] = None,
) -> str:
    if ts is None:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines: List[str] = []
    lines.append(f"DLCP Diagnostics  ({ts})")
    lines.append("=" * 40)
    lines.append("")
    if not reports:
        lines.append("No DLCP HID devices detected.")
        return "\n".join(lines)
    # Channel label resolution priority:
    #   1. Operator override via --ch-map (manual; matches by HID-path
    #      substring).
    #   2. Auto-derive from EP0 route table via
    #      _derive_channel_label(report.routes): LEFT (all-L), RIGHT
    #      (all-R), the raw route label echoed (all uniform L+R / L-R /
    #      R-L), or MIX (non-uniform).
    #   3. "" (no prefix column) when neither is available.
    # If ANY device gets a label (manual or auto), left-align all labels
    # in a fixed-width column so the report stays visually consistent.
    auto_labels = [_derive_channel_label(r.routes) for r in reports]
    manual_labels = [
        _resolve_channel_label(
            r.info.path.decode("utf-8", errors="replace")
            if r.info.path is not None else "",
            ch_map,
        )
        for r in reports
    ]
    have_any_label = bool(ch_map) or any(auto_labels)
    label_width = max(
        (len(lbl) for lbl in (auto_labels + manual_labels) if lbl),
        default=5,
    )
    for report, auto_lbl, manual_lbl in zip(reports, auto_labels, manual_labels):
        path_text = (
            report.info.path.decode("utf-8", errors="replace")
            if report.info.path is not None
            else "<no-path>"
        )
        # Manual label wins over auto-derived (operator override).  When
        # neither is available but ch_map was given, show "?" so the
        # operator notices to extend the map.
        label = manual_lbl or auto_lbl
        if not label and ch_map:
            label = "?"
        prefix = f"{label:<{label_width}} " if have_any_label else ""
        lines.append(
            f"{prefix}HID {path_text}  {_format_version(report.version)}"
        )
        if report.routes:
            from dlcp_fw.flash.dlcp_main_flash import format_route_entries
            lines.append("  Channels:  " + format_route_entries(report.routes))
        if report.active_config_name:
            lines.append(f"  Config:    {report.active_config_name!r}")
        lines.append("  " + _format_runtime_line(report.snapshot))
        lines.append("  " + _format_reset_line(report.snapshot))
        lines.append("  " + _format_status_line(report))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_json_report(
    reports: List["DiagReport"],
    *,
    ts: Optional[str] = None,
    ch_map: Optional[dict[str, str]] = None,
) -> str:
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
            rev_marker = _rev_marker_for_version(report.version)
            version_obj = {
                "flag": report.version.flag,
                "major": report.version.major,
                "rev": report.version.minor,
                "rev_hex": f"0x{report.version.minor:02X}",
                "eeprom_marker": (
                    f"0x{rev_marker:02X}" if rev_marker is not None else None
                ),
            }
        path_text = (
            report.info.path.decode("utf-8", errors="replace")
            if report.info.path is not None
            else None
        )
        manual_channel = (
            _resolve_channel_label(path_text, ch_map) or None
            if path_text is not None
            else None
        )
        auto_channel = _derive_channel_label(report.routes) or None
        # Manual override wins; auto-derived as fallback.
        channel = manual_channel or auto_channel
        routes_obj: Optional[List[dict[str, object]]] = None
        if report.routes:
            routes_obj = [
                {"channel": r.channel, "value": r.value, "label": r.label}
                for r in report.routes
            ]
        out["mains"].append(
            {
                "channel": channel,
                "channel_source": (
                    "ch_map" if manual_channel else
                    ("ep0_routes" if auto_channel else None)
                ),
                "routes": routes_obj,
                "active_config_name": report.active_config_name,
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
    ap.add_argument(
        "--ch-map",
        action="append",
        default=[],
        metavar="LABEL=PATH_SUBSTRING",
        help=(
            "Operator-supplied channel mapping (repeatable).  Each value "
            "is `LABEL=PATH_SUBSTRING` -- if PATH_SUBSTRING is contained "
            "in a HID device path, the device is labeled LABEL in the "
            "report.  Example: `--ch-map LEFT=4296563925 --ch-map "
            "RIGHT=4296563940`.  Firmware doesn't carry the channel "
            "identity over HID (the round-5 cmd 0x44 trailer drop "
            "removed it), so the operator provides it externally; "
            "mapping is by HID path substring rather than full path "
            "to keep the CLI usable with macOS DevSrvsID-style paths."
        ),
    )
    args = ap.parse_args(argv)

    # Parse --ch-map values into an ordered dict.  Reject malformed entries
    # loudly rather than silently dropping them -- a typo in the mapping
    # would be hard to diagnose otherwise.
    ch_map: dict[str, str] = {}
    for spec in args.ch_map:
        if "=" not in spec:
            ap.error(
                f"--ch-map value must be in the form LABEL=PATH_SUBSTRING "
                f"(got: {spec!r})"
            )
        label, path_sub = spec.split("=", 1)
        label = label.strip()
        path_sub = path_sub.strip()
        if not label or not path_sub:
            ap.error(
                f"--ch-map value must have non-empty LABEL and "
                f"PATH_SUBSTRING (got: {spec!r})"
            )
        ch_map[path_sub] = label

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
            print(_format_json_report(reports, ch_map=ch_map), end="")
        else:
            print(_format_human_report(reports, ch_map=ch_map), end="")

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
