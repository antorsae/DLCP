"""Tests for the V3.2 rev 0x37 Tier-1 cmd 0x44 host CLI.

Three tiers:
  * unit -- parse_cmd44_diag_response on synthetic byte buffers
  * unit -- classify_status across the spec's HEALTHY / DEGRADED /
            CRITICAL example shapes
  * integration -- mocked HID device, end-to-end query_diag round-trip
                   verifying both cmd 0x06 (version) and cmd 0x44 are
                   issued and that the JSON report shape matches spec
"""

from __future__ import annotations

from typing import List

import pytest

from dlcp_fw.flash.dlcp_diag import (
    CMD44_EXPECTED_LENGTH_BYTE,
    CMD44_PAYLOAD_OFFSET,
    CMD44_TOTAL_CELLS,
    DiagReport,
    DiagSnapshot,
    RESET_LETTERS,
    RUNTIME_LETTERS,
    SATURATED_VALUE,
    _format_human_report,
    _format_json_report,
    classify_status,
    parse_cmd44_diag_response,
)


# ---------------------------------------------------------------------------
# Helpers: synthesize a 64-byte cmd 0x44 response
# ---------------------------------------------------------------------------


def _build_cmd44_response(
    *,
    counters: tuple[int, int, int, int, int, int, int],
    reset_flags: tuple[int, int, int, int],
    status: int = 0x00,
    length_byte: int = CMD44_EXPECTED_LENGTH_BYTE,
    cmd_echo: int = 0x44,
    leading_zero_report_id: bool = False,
) -> bytes:
    payload = list(counters) + list(reset_flags)
    assert len(payload) == CMD44_TOTAL_CELLS
    body = [cmd_echo, status, length_byte] + payload
    # Pad to 64 bytes with 0xFF (matches the firmware's pad-loop drop:
    # bytes [14..63] are observational only).
    body += [0xFF] * (64 - len(body))
    if leading_zero_report_id:
        body = [0x00] + body[:63]
    return bytes(body)


# ---------------------------------------------------------------------------
# Tier A: parser
# ---------------------------------------------------------------------------


def test_parse_cmd44_all_zero_payload() -> None:
    """All counters + flags zero (impossible in practice but legal
    by length-byte contract)."""
    resp = _build_cmd44_response(counters=(0,) * 7, reset_flags=(0,) * 4)
    snap = parse_cmd44_diag_response(resp)
    assert snap.runtime_counters == (0,) * 7
    assert snap.reset_flags == (0,) * 4
    assert snap.runtime_nonzero_count == 0
    assert snap.active_reset_cause is None


def test_parse_cmd44_clean_por_pattern() -> None:
    """The expected pattern after a clean cold-start: POR=1, S=B=1
    (one standby/bring-up boot cycle), everything else zero."""
    resp = _build_cmd44_response(counters=(0, 0, 1, 1, 0, 0, 0), reset_flags=(1, 0, 0, 0))
    snap = parse_cmd44_diag_response(resp)
    assert snap.diag_s == 1 and snap.diag_b == 1
    assert snap.diag_reset_por == 1
    assert snap.active_reset_cause == "por"


def test_parse_cmd44_saturated_counters_preserved() -> None:
    """Counters reaching 0x0F MUST round-trip through the parser intact
    -- the saturation marker is what the renderer / status classifier
    keys on for CRITICAL escalation."""
    resp = _build_cmd44_response(
        counters=(SATURATED_VALUE, 0, 0, 0, 0, 0, 0),
        reset_flags=(1, 0, 0, 0),
    )
    snap = parse_cmd44_diag_response(resp)
    assert snap.diag_i == SATURATED_VALUE


def test_parse_cmd44_each_reset_cause() -> None:
    """Each of the 4 reset-cause flags maps to its spelled-out label."""
    expected = [
        ((1, 0, 0, 0), "por"),
        ((0, 1, 0, 0), "bor"),
        ((0, 0, 1, 0), "wdt"),
        ((0, 0, 0, 1), "sw"),
    ]
    for flags, label in expected:
        resp = _build_cmd44_response(counters=(0,) * 7, reset_flags=flags)
        snap = parse_cmd44_diag_response(resp)
        assert snap.active_reset_cause == label, f"flags={flags}"


def test_parse_cmd44_tolerates_leading_report_id_byte() -> None:
    """Some HID stacks (notably hidapi on Linux) prefix a 0x00 report-id
    byte to the response.  The parser must tolerate both shapes."""
    resp = _build_cmd44_response(
        counters=(0, 0, 1, 1, 0, 0, 0),
        reset_flags=(1, 0, 0, 0),
        leading_zero_report_id=True,
    )
    snap = parse_cmd44_diag_response(resp)
    assert snap.diag_s == 1 and snap.diag_reset_por == 1


def test_parse_cmd44_rejects_wrong_cmd_echo() -> None:
    resp = _build_cmd44_response(counters=(0,) * 7, reset_flags=(1, 0, 0, 0))
    bad = bytearray(resp)
    bad[0] = 0x43          # wrong cmd echo (memread, not diag)
    with pytest.raises(RuntimeError, match="unexpected cmd 0x44 echo"):
        parse_cmd44_diag_response(bytes(bad))


def test_parse_cmd44_rejects_nonzero_status() -> None:
    resp = _build_cmd44_response(counters=(0,) * 7, reset_flags=(1, 0, 0, 0), status=0x01)
    with pytest.raises(RuntimeError, match="status byte non-zero"):
        parse_cmd44_diag_response(resp)


def test_parse_cmd44_rejects_wrong_length_byte() -> None:
    """Pre-rev-0x37 firmware that doesn't implement cmd 0x44 (or a
    future rev with a different payload size) should be detected via
    the length byte at response[2].  The error message names the
    spec rev so operators know to upgrade."""
    resp = _build_cmd44_response(
        counters=(0,) * 7, reset_flags=(1, 0, 0, 0), length_byte=0x0E
    )
    with pytest.raises(RuntimeError, match="length byte mismatch"):
        parse_cmd44_diag_response(resp)


def test_parse_cmd44_rejects_short_response() -> None:
    with pytest.raises(RuntimeError, match="short cmd 0x44 response"):
        parse_cmd44_diag_response(b"\x44\x00\x0B")


# ---------------------------------------------------------------------------
# Tier B: status classification
# ---------------------------------------------------------------------------


def _snap(
    *,
    counters: tuple[int, int, int, int, int, int, int] = (0,) * 7,
    reset_flags: tuple[int, int, int, int] = (1, 0, 0, 0),
) -> DiagSnapshot:
    return DiagSnapshot(
        diag_i=counters[0],
        diag_d=counters[1],
        diag_s=counters[2],
        diag_b=counters[3],
        diag_r=counters[4],
        diag_a=counters[5],
        diag_p=counters[6],
        diag_reset_por=reset_flags[0],
        diag_reset_bor=reset_flags[1],
        diag_reset_wdt=reset_flags[2],
        diag_reset_sw=reset_flags[3],
    )


def test_classify_healthy_clean_boot() -> None:
    """POR=1, S+B both 1, everything else 0 -- the expected boot
    sequence per spec: 'one standby/bring-up cycle is the expected
    boot sequence'."""
    status, alerts = classify_status(_snap(counters=(0, 0, 1, 1, 0, 0, 0)))
    assert status == "HEALTHY"
    assert alerts == ()


def test_classify_healthy_only_por() -> None:
    """Just POR=1, no boot cycles yet (very fresh power-on)."""
    status, alerts = classify_status(_snap())
    assert status == "HEALTHY"
    assert alerts == ()


def test_classify_degraded_brown_out() -> None:
    """BOR firing is degraded -- power supply may be marginal."""
    status, alerts = classify_status(_snap(reset_flags=(0, 1, 0, 0)))
    assert status == "DEGRADED"
    assert "brown_out_reset_this_session" in alerts


def test_classify_degraded_software_reset() -> None:
    status, alerts = classify_status(_snap(reset_flags=(0, 0, 0, 1)))
    assert status == "DEGRADED"
    assert "software_reset_this_session" in alerts


def test_classify_degraded_runtime_counter_nonzero() -> None:
    """Any I2C transport fault -> degraded."""
    status, alerts = classify_status(_snap(counters=(3, 0, 0, 0, 0, 0, 0)))
    assert status == "DEGRADED"
    assert "i2c_transport_faults=3" in alerts


def test_classify_critical_wdt() -> None:
    """WDT firing is always CRITICAL -- main loop hung means a code
    bug, not an environmental issue."""
    status, alerts = classify_status(_snap(reset_flags=(0, 0, 1, 0)))
    assert status == "CRITICAL"
    assert "watchdog_reset_this_session" in alerts


def test_classify_critical_saturated_counter() -> None:
    """Any counter reaching 0x0F (15+ events this session) is
    CRITICAL.  Spec rationale: 15+ events per session of any class
    is far above any plausible real fault rate; suggests RAM
    corruption or protocol cascade."""
    status, alerts = classify_status(_snap(counters=(SATURATED_VALUE, 0, 0, 0, 0, 0, 0)))
    assert status == "CRITICAL"
    assert "I_saturated" in alerts


def test_classify_unknown_no_reset_flag() -> None:
    """All four reset-cause flags clear -- shouldn't happen in
    practice but the classifier surfaces it as DEGRADED with an
    explicit alert so the operator can investigate."""
    status, alerts = classify_status(_snap(reset_flags=(0, 0, 0, 0)))
    assert status == "DEGRADED"
    assert "no_reset_cause_flag_set" in alerts


# ---------------------------------------------------------------------------
# Tier B: report formatters (no HID required)
# ---------------------------------------------------------------------------


def _make_report(
    snapshot: DiagSnapshot,
    *,
    path: bytes = b"DevSrvsID:test",
) -> DiagReport:
    from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo
    from dlcp_fw.flash.dlcp_main_flash import VersionInfo

    info = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=path,
        manufacturer_string="Hypex BV",
        product_string="DLCP",
        serial_number="",
    )
    version = VersionInfo(flag=3, major=2, minor=0x37)
    status, alerts = classify_status(snapshot)
    return DiagReport(info=info, version=version, snapshot=snapshot, status=status, alerts=alerts)


def test_human_report_shape_clean_boot() -> None:
    """Spec sample shape: title + per-MAIN block with Runtime / Reset /
    Status lines.  All 7 letters present in Runtime; all 4 in Reset."""
    snap = _snap(counters=(0, 0, 1, 1, 0, 0, 0))
    report = _make_report(snap)
    text = _format_human_report([report], ts="2026-04-20T15:23:00Z")
    assert "DLCP Diagnostics  (2026-04-20T15:23:00Z)" in text
    assert "DevSrvsID:test" in text
    assert "V3.x.2 rev 0x37" in text
    # All 7 runtime letters present in Runtime line.
    for letter in RUNTIME_LETTERS:
        assert f"{letter}" in text, f"missing runtime letter {letter}"
    # All 4 reset letters present.
    for letter in RESET_LETTERS:
        assert f"{letter}" in text, f"missing reset letter {letter}"
    assert "Status:    HEALTHY" in text


def test_human_report_with_alerts() -> None:
    snap = _snap(counters=(3, 2, 1, 1, 0, 0, 0), reset_flags=(0, 1, 0, 0))
    report = _make_report(snap)
    text = _format_human_report([report])
    assert "DEGRADED" in text
    assert "brown_out_reset_this_session" in text
    assert "i2c_transport_faults=3" in text


def test_json_report_shape() -> None:
    """JSON report MUST have the spec'd fields so downstream tooling
    (CI dashboards, soak-test analyzers) can rely on field positions."""
    import json

    snap = _snap(counters=(3, 2, 1, 1, 0, 0, 0), reset_flags=(0, 1, 0, 0))
    report = _make_report(snap)
    text = _format_json_report([report], ts="2026-04-20T15:23:00Z")
    obj = json.loads(text)
    assert obj["ts"] == "2026-04-20T15:23:00Z"
    assert obj["spec_rev"] == "V32_DIAG_TIER1"
    assert isinstance(obj["mains"], list) and len(obj["mains"]) == 1
    main_obj = obj["mains"][0]
    # Spec'd field names.
    assert main_obj["hid_path"] == "DevSrvsID:test"
    assert main_obj["version"] == {"flag": 3, "major": 2, "rev": 0x37, "rev_hex": "0x37"}
    assert main_obj["counters"] == {
        "i": 3, "d": 2, "s": 1, "b": 1, "r": 0, "a": 0, "p": 0,
    }
    assert main_obj["reset_cause"] == {
        "por": 0, "bor": 1, "wdt": 0, "sw": 0, "active": "bor",
    }
    assert main_obj["status"] == "DEGRADED"
    assert main_obj["nonzero_count"] == 4
    assert "brown_out_reset_this_session" in main_obj["alerts"]


def test_json_report_empty_when_no_devices() -> None:
    text = _format_json_report([], ts="2026-04-20T00:00:00Z")
    import json

    obj = json.loads(text)
    assert obj["mains"] == []


# ---------------------------------------------------------------------------
# Tier C: mocked-HID end-to-end (no live hardware)
# ---------------------------------------------------------------------------


class _MockHidDevice:
    """In-memory fake hidapi device.  Records writes; replies to cmd
    0x06 + cmd 0x44 with canned responses."""

    def __init__(self, version: tuple[int, int, int], cmd44_payload: bytes):
        self.version = version
        self.cmd44_payload = cmd44_payload
        self._pending_response: bytes | None = None
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, buf: bytes) -> int:
        # hidapi prepends a 0-byte report id; strip it.
        if len(buf) == 65 and buf[0] == 0x00:
            payload = bytes(buf[1:])
        else:
            payload = bytes(buf)
        self.writes.append(payload)
        cmd = payload[0]
        if cmd == 0x06:
            flag, major, minor = self.version
            self._pending_response = bytes([0x06, flag, major, minor]) + b"\xFF" * 60
        elif cmd == 0x44:
            self._pending_response = self.cmd44_payload
        else:
            self._pending_response = None
        return len(buf)

    def read(self, size: int, timeout_ms: int) -> list[int]:
        if self._pending_response is None:
            return []
        out = self._pending_response[:size]
        self._pending_response = None
        return list(out)

    def set_nonblocking(self, _val: bool) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def test_query_diag_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: mocked HID, query_diag issues cmd 0x06 + cmd 0x44,
    parses both, classifies status, returns a DiagReport.  This is
    the behavioral contract the CLI relies on."""
    from dlcp_fw.flash import dlcp_diag
    from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo

    cmd44_payload = _build_cmd44_response(
        counters=(0, 0, 1, 1, 0, 0, 0),
        reset_flags=(1, 0, 0, 0),
    )
    fake = _MockHidDevice(version=(3, 2, 0x37), cmd44_payload=cmd44_payload)

    fake_info = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"DevSrvsID:fake",
        manufacturer_string="Hypex BV",
        product_string="DLCP",
        serial_number="",
    )
    monkeypatch.setattr(dlcp_diag, "_pick_device", lambda vid, pid, path: fake_info)
    monkeypatch.setattr(dlcp_diag, "_open_hid", lambda path: fake)

    report = dlcp_diag.query_diag()
    # Both queries hit the wire.
    cmds_seen = [w[0] for w in fake.writes]
    assert 0x06 in cmds_seen, "cmd 0x06 (version) must be issued"
    assert 0x44 in cmds_seen, "cmd 0x44 (diag) must be issued"
    # Parsed shape.
    assert report.snapshot.diag_s == 1
    assert report.snapshot.diag_b == 1
    assert report.snapshot.active_reset_cause == "por"
    assert report.version is not None
    assert (report.version.flag, report.version.major, report.version.minor) == (3, 2, 0x37)
    assert report.status == "HEALTHY"
    # HID device closed cleanly.
    assert fake.closed
