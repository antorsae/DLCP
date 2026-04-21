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

import dataclasses
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


def test_parse_cmd44_rejects_runtime_counter_above_0x0F() -> None:
    """Spec contract: runtime counters are 0..0x0F (diag_inc_sat
    saturates at 0x0F).  Out-of-range values indicate a misframed
    response or corrupted MAIN diag block; fail fast rather than
    feed garbage into classification.  Codex LOW fix vs dc9647a."""
    resp = bytearray(_build_cmd44_response(counters=(0x10, 0, 0, 0, 0, 0, 0), reset_flags=(1, 0, 0, 0)))
    with pytest.raises(RuntimeError, match=r"runtime counter 'I' out of range"):
        parse_cmd44_diag_response(bytes(resp))


def test_parse_cmd44_rejects_reset_flag_other_than_0_or_1() -> None:
    """Spec contract: reset-cause flags are 0 or 1 (cold-init writes
    exactly one flag per session).  Anything else means corruption."""
    resp = bytearray(_build_cmd44_response(counters=(0,) * 7, reset_flags=(2, 0, 0, 0)))
    with pytest.raises(RuntimeError, match=r"reset-cause flag 'O' out of range"):
        parse_cmd44_diag_response(bytes(resp))


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


def test_classify_lone_s_or_lone_b_is_degraded() -> None:
    """Spec calls for "at most one S+B PAIR" as the HEALTHY runtime
    pattern.  S=1 with B=0 (or vice versa) is a half-completed boot
    cycle, not a healthy boot, and must fall to DEGRADED.  Codex
    MEDIUM fix vs dc9647a -- the earlier `S in (0,1) and B in (0,1)`
    check accepted lone-S and lone-B as HEALTHY."""
    # Lone S (standby dispatch fired, bring-up didn't follow).
    status, alerts = classify_status(_snap(counters=(0, 0, 1, 0, 0, 0, 0)))
    assert status == "DEGRADED"
    assert "standby_dispatches=1" in alerts
    # Lone B (bring-up dispatch fired without preceding standby).
    status, alerts = classify_status(_snap(counters=(0, 0, 0, 1, 0, 0, 0)))
    assert status == "DEGRADED"
    assert "bring_up_dispatches=1" in alerts


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
    # Real V3.2 firmware loads (3, 3, 2) at ram_0x05B/C/D -- see
    # src/dlcp_fw/asm/dlcp_main_v32.asm line ~2870.  The previous mock
    # used (3, 2, 0x37) based on a misreading of the spec sample;
    # codex review 2026-04-21 against the real cmd 0x06 response on
    # hardware showed (3, 3, 2).
    version = VersionInfo(flag=3, major=3, minor=2)
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
    # Format: "V{major}.{minor}".  Real V3.2 firmware reports
    # (flag=3, major=3, minor=2) via cmd 0x06.  The earlier mock used
    # (3, 2, 0x37) -- codex review 2026-04-21 against real hardware
    # showed the correct tuple is (3, 3, 2), so the displayed string
    # is "V3.2".  The "rev 0x37" trailer in the original spec sample
    # is the EEPROM marker, NOT part of the cmd 0x06 response;
    # dropped from the format until/unless we add a separate
    # EEPROM-marker read.
    assert "V3.2" in text
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
    # Real V3.2 firmware reports (flag=3, major=3, minor=2); JSON shape
    # was extended (2026-04-21) to include the EEPROM marker (looked up
    # from the (major, minor) tuple via _rev_marker_for_version) so
    # downstream tooling can distinguish V3.x firmware revisions
    # (V3.1 = 0x36, V3.2 = 0x37, etc.) without a separate EEPROM read.
    assert main_obj["version"] == {
        "flag": 3, "major": 3, "rev": 2, "rev_hex": "0x02",
        "eeprom_marker": "0x37",
    }
    # Channel mapping is operator-supplied via --ch-map; with no map,
    # the channel field is null.
    assert main_obj["channel"] is None
    assert main_obj["counters"] == {
        "i": 3, "d": 2, "s": 1, "b": 1, "r": 0, "a": 0, "p": 0,
    }
    assert main_obj["reset_cause"] == {
        "por": 0, "bor": 1, "wdt": 0, "sw": 0, "active": "bor",
    }
    assert main_obj["status"] == "DEGRADED"
    assert main_obj["nonzero_count"] == 4
    assert "brown_out_reset_this_session" in main_obj["alerts"]


def test_human_report_includes_rev_marker_for_known_versions() -> None:
    """V3.2 firmware (cmd 0x06 minor = 2) maps to EEPROM rev 0x37 via
    the static lookup."""
    snap = _snap()
    report = _make_report(snap)  # uses VersionInfo(3, 3, 2) -> V3.2
    text = _format_human_report([report])
    assert "V3.2 rev 0x37" in text, (
        "V3.2 must show 'rev 0x37' from the static lookup"
    )


def test_human_report_v31_rev_marker() -> None:
    """V3.1 firmware (cmd 0x06 (3, 3, 1)) maps to EEPROM rev 0x31.

    Codex review of 6963cfc 2026-04-21 caught the table-vs-firmware
    drift: an earlier version of _REV_MARKER_BY_VERSION had V3.1 ->
    0x36 based on the Phase 2.5 commit message ("EEPROM marker bump
    0x36 -> 0x37"), but 0x36 was a never-shipped intermediate build.
    Committed V3.1 source (src/dlcp_fw/asm/dlcp_main_v31.asm:8384)
    has EEPROM tuple `db 0x03, 0x01, 0x31` -> marker 0x31.  Pin that
    here so a future regression that re-introduces the wrong marker
    fails immediately.
    """
    from dlcp_fw.flash.dlcp_main_flash import VersionInfo
    from dlcp_fw.flash.dlcp_diag import _format_version

    v31 = VersionInfo(flag=3, major=3, minor=1)
    text = _format_version(v31)
    assert text == "V3.1 rev 0x31", (
        f"V3.1 expected 'V3.1 rev 0x31' (per dlcp_main_v31.asm:8384 "
        f"EEPROM tuple); got {text!r}"
    )


def test_human_report_v23_omits_rev_marker() -> None:
    """Stock V2.3 / V3.0 cmd 0x06 reports (3, 2, 3) -- ambiguous tuple
    (we can't distinguish the two firmware variants from cmd 0x06
    alone because V3.0 keeps the stock identifier by design).
    Both display as 'V2.3' with NO rev suffix.  Omitting the suffix
    is a deliberate design choice (see docstring on
    _REV_MARKER_BY_VERSION); pin it so a future change that adds
    a guess for stock V2.3 is forced to update this test.
    """
    from dlcp_fw.flash.dlcp_main_flash import VersionInfo
    from dlcp_fw.flash.dlcp_diag import _format_version

    v23 = VersionInfo(flag=3, major=2, minor=3)
    text = _format_version(v23)
    assert text == "V2.3", (
        f"V2.3/V3.0 expected 'V2.3' with NO rev suffix; got {text!r}"
    )


def test_human_report_auto_derives_channel_from_routes() -> None:
    """When --ch-map is not given, the channel label is auto-derived
    from the EP0 route table:
      * all 6 outputs L  -> "LEFT"
      * all 6 outputs R  -> "RIGHT"
      * mixed             -> "MIX"
    Reuses the existing route helpers from dlcp_main_flash.py so the
    two CLIs (dlcp_diag and dlcp_main_flash --info-only) agree on the
    channel-routing language.
    """
    from dlcp_fw.flash.dlcp_main_flash import RouteEntry

    snap = _snap()
    # Construct a report with routes manually (the live EP0 probe is
    # not exercised in this unit test -- that happens at integration
    # time on hardware).
    base = _make_report(snap)
    routes_left = tuple(
        RouteEntry(channel=i + 1, value=0, label="L") for i in range(6)
    )
    routes_right = tuple(
        RouteEntry(channel=i + 1, value=1, label="R") for i in range(6)
    )
    routes_mixed = (
        RouteEntry(channel=1, value=0, label="L"),
        RouteEntry(channel=2, value=1, label="R"),
        RouteEntry(channel=3, value=0, label="L"),
        RouteEntry(channel=4, value=1, label="R"),
        RouteEntry(channel=5, value=2, label="L+R"),
        RouteEntry(channel=6, value=2, label="L+R"),
    )
    for routes, expected_label in (
        (routes_left, "LEFT"),
        (routes_right, "RIGHT"),
        (routes_mixed, "MIX"),
    ):
        report = dataclasses.replace(base, routes=routes)
        text = _format_human_report([report])
        assert expected_label in text, (
            f"expected auto-derived label {expected_label!r} for routes "
            f"{routes!r}; output: {text!r}"
        )


def test_human_report_ch_map_overrides_auto_derived_label() -> None:
    """Operator --ch-map takes precedence over the auto-derived label.

    Use case: a unit physically wired LEFT but with all-R routes (e.g.,
    operator hasn't loaded a preset yet, or the EP0 probe returned stale
    data); --ch-map LEFT=... still labels it LEFT.
    """
    from dlcp_fw.flash.dlcp_main_flash import RouteEntry

    snap = _snap()
    routes_right = tuple(
        RouteEntry(channel=i + 1, value=1, label="R") for i in range(6)
    )
    base = _make_report(snap)
    report = dataclasses.replace(base, routes=routes_right)
    # No ch_map: auto-derived label = "RIGHT".
    text_auto = _format_human_report([report])
    assert "RIGHT" in text_auto
    # ch_map override: label = "LEFT".
    text_manual = _format_human_report(
        [report], ch_map={"DevSrvsID:test": "LEFT"},
    )
    assert "LEFT " in text_manual or "LEFT\n" in text_manual or text_manual.startswith("LEFT")
    # Spot-check that the auto-derived "RIGHT" is NOT in the manual case.
    # Given that "LEFT" replaces the prefix entirely, "RIGHT" should not
    # appear unless it's part of some other content (it's not).
    # However the route line still shows R values; relax to verifying
    # the prefix LINE doesn't contain "RIGHT".
    first_line_with_path = next(
        ln for ln in text_manual.split("\n") if "DevSrvsID:test" in ln
    )
    assert "RIGHT" not in first_line_with_path


def test_human_report_shows_channel_mapping_line() -> None:
    """The new "Channels:" line lists the per-output route mappings
    using format_route_entries from dlcp_main_flash.

    The exact separator format is comma + space (the upstream helper's
    convention; see dlcp_main_flash.format_route_entries).  Pin it
    here so a future change to that helper that breaks consistency
    surfaces in this test rather than only in operator-visible output.
    """
    from dlcp_fw.flash.dlcp_main_flash import RouteEntry

    snap = _snap()
    routes = tuple(
        RouteEntry(channel=i + 1, value=0, label="L") for i in range(6)
    )
    base = _make_report(snap)
    report = dataclasses.replace(base, routes=routes)
    text = _format_human_report([report])
    assert "Channels:" in text
    # All 6 channel slots present.
    for n in range(1, 7):
        assert f"CH{n}=L" in text
    # Pin the comma-separator format from format_route_entries.
    assert "CH1=L, CH2=L, CH3=L, CH4=L, CH5=L, CH6=L" in text


def test_derive_channel_label_echoes_raw_for_non_LR_routes() -> None:
    """Non-L/R uniform routes echo the raw route label as-is to
    match dlcp_main_flash's terminology (and the HFD UI's
    "L+R/Mid"/"L-R/Side" naming convention).  This commit deliberately
    avoids inventing alternative names like MONO/MID/SIDE which
    would conflict with HFD's existing labels.
    """
    from dlcp_fw.flash.dlcp_main_flash import RouteEntry
    from dlcp_fw.flash.dlcp_diag import _derive_channel_label

    for route_label, expected in [
        ("L+R", "L+R"),
        ("L-R", "L-R"),
        ("R-L", "R-L"),
    ]:
        routes = tuple(
            RouteEntry(channel=i + 1, value=2, label=route_label)
            for i in range(6)
        )
        assert _derive_channel_label(routes) == expected, (
            f"non-L/R uniform route {route_label!r} should echo as-is, "
            f"not get aliased; got {_derive_channel_label(routes)!r}"
        )


def test_query_diag_handles_ep0_failure_gracefully(monkeypatch, capsys) -> None:
    """When the EP0 probe raises RuntimeError / OSError, query_diag
    must:
      * print a stderr warning so the operator notices,
      * leave routes / active_config_name as None,
      * still return a valid DiagReport with the cmd 0x44 snapshot
        (the diag pipeline is independent of the EP0 channel probe).

    Codex review of 90af763 caught that the original `except Exception:
    pass` was too broad and silent; this test exercises the now-narrowed
    exception handling path.
    """
    from dlcp_fw.flash import dlcp_diag

    # Stub the HID lookup + cmd 0x06 + cmd 0x44 path so the test runs
    # without real hardware.
    from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo
    from dlcp_fw.flash.dlcp_main_flash import VersionInfo

    info = HidDeviceInfo(
        vendor_id=0x04D8, product_id=0xFF89, path=b"DevSrvsID:test",
        manufacturer_string="Hypex BV", product_string="DLCP",
        serial_number="",
    )

    class _StubDev:
        def write(self, *a, **kw): return 65
        def read(self, *a, **kw): return [0] * 65
        def close(self): pass

    monkeypatch.setattr(dlcp_diag, "_pick_device", lambda *a, **kw: info)
    monkeypatch.setattr(dlcp_diag, "_open_hid", lambda *a, **kw: _StubDev())
    monkeypatch.setattr(
        dlcp_diag, "_probe_cmd06_version",
        lambda dev, **kw: VersionInfo(flag=3, major=3, minor=2),
    )
    monkeypatch.setattr(
        dlcp_diag, "_probe_cmd44_diag",
        lambda dev, **kw: DiagSnapshot(
            diag_i=0, diag_d=0, diag_s=0, diag_b=0, diag_r=0, diag_a=0, diag_p=0,
            diag_reset_por=1, diag_reset_bor=0, diag_reset_wdt=0, diag_reset_sw=0,
        ),
    )

    # Make the EP0 probe raise a RuntimeError (one of the expected
    # failure types).
    def _failing_probe(**kw):
        raise RuntimeError("simulated EP0 failure (libusb refused)")

    from dlcp_fw.flash import dlcp_main_flash
    monkeypatch.setattr(dlcp_main_flash, "_probe_ep0_app_ram", _failing_probe)

    report = dlcp_diag.query_diag(probe_routes=True)

    # Report still valid -- snapshot present, status classified.
    assert report.snapshot is not None
    assert report.status in {"HEALTHY", "DEGRADED", "CRITICAL"}
    # Routes / config null because EP0 failed.
    assert report.routes is None
    assert report.active_config_name is None
    # Stderr carries the warning (operator can correlate).
    captured = capsys.readouterr()
    assert "EP0 routes probe failed" in captured.err
    assert "simulated EP0 failure" in captured.err


def test_query_diag_handles_pyusb_no_backend_gracefully(monkeypatch, capsys) -> None:
    """PyUSB raises NoBackendError(ValueError) when no libusb backend
    is loadable -- a common failure on stripped/minimal hosts.  Codex
    review of 25d6780 caught that ValueError was NOT in the original
    narrowed catch list (RuntimeError, OSError, ImportError), so a
    libusb-less host would crash query_diag instead of degrading.

    This test injects a ValueError from `_probe_ep0_app_ram` and
    verifies the same graceful degradation as the RuntimeError test.
    """
    from dlcp_fw.flash import dlcp_diag
    from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo
    from dlcp_fw.flash.dlcp_main_flash import VersionInfo

    info = HidDeviceInfo(
        vendor_id=0x04D8, product_id=0xFF89, path=b"DevSrvsID:test",
        manufacturer_string="Hypex BV", product_string="DLCP",
        serial_number="",
    )

    class _StubDev:
        def write(self, *a, **kw): return 65
        def read(self, *a, **kw): return [0] * 65
        def close(self): pass

    monkeypatch.setattr(dlcp_diag, "_pick_device", lambda *a, **kw: info)
    monkeypatch.setattr(dlcp_diag, "_open_hid", lambda *a, **kw: _StubDev())
    monkeypatch.setattr(
        dlcp_diag, "_probe_cmd06_version",
        lambda dev, **kw: VersionInfo(flag=3, major=3, minor=2),
    )
    monkeypatch.setattr(
        dlcp_diag, "_probe_cmd44_diag",
        lambda dev, **kw: DiagSnapshot(
            diag_i=0, diag_d=0, diag_s=0, diag_b=0, diag_r=0, diag_a=0, diag_p=0,
            diag_reset_por=1, diag_reset_bor=0, diag_reset_wdt=0, diag_reset_sw=0,
        ),
    )

    # Simulate PyUSB's NoBackendError (subclass of ValueError).
    def _no_backend(**kw):
        raise ValueError("No backend available")

    from dlcp_fw.flash import dlcp_main_flash
    monkeypatch.setattr(dlcp_main_flash, "_probe_ep0_app_ram", _no_backend)

    report = dlcp_diag.query_diag(probe_routes=True)

    # Graceful degradation: report still valid, no routes.
    assert report.snapshot is not None
    assert report.routes is None
    captured = capsys.readouterr()
    assert "EP0 routes probe failed" in captured.err
    assert "No backend available" in captured.err


def test_json_report_includes_routes_and_channel_source() -> None:
    """JSON gains `routes`, `channel_source`, and `active_config_name`
    when EP0 probe succeeded."""
    import json
    from dlcp_fw.flash.dlcp_main_flash import RouteEntry

    snap = _snap()
    routes = tuple(
        RouteEntry(channel=i + 1, value=0, label="L") for i in range(6)
    )
    base = _make_report(snap)
    report = dataclasses.replace(
        base, routes=routes, active_config_name="ConfigName",
    )
    text = _format_json_report([report])
    obj = json.loads(text)
    main_obj = obj["mains"][0]
    # Auto-derived channel.
    assert main_obj["channel"] == "LEFT"
    assert main_obj["channel_source"] == "ep0_routes"
    # routes shape.
    assert main_obj["routes"] is not None
    assert len(main_obj["routes"]) == 6
    assert main_obj["routes"][0] == {"channel": 1, "value": 0, "label": "L"}
    assert main_obj["active_config_name"] == "ConfigName"


def test_json_report_channel_source_indicates_ch_map_override() -> None:
    """When --ch-map overrides the auto-derived label, JSON
    channel_source = "ch_map" so downstream tooling can distinguish
    operator-supplied labels from auto-derived ones."""
    import json
    from dlcp_fw.flash.dlcp_main_flash import RouteEntry

    snap = _snap()
    routes = tuple(
        RouteEntry(channel=i + 1, value=1, label="R") for i in range(6)
    )
    base = _make_report(snap)
    report = dataclasses.replace(base, routes=routes)
    text = _format_json_report(
        [report], ch_map={"DevSrvsID:test": "LEFT"},
    )
    obj = json.loads(text)
    assert obj["mains"][0]["channel"] == "LEFT"
    assert obj["mains"][0]["channel_source"] == "ch_map"


def test_json_report_eeprom_marker_null_for_unknown_version() -> None:
    """Unknown firmware tuples (not in _REV_MARKER_BY_VERSION) get
    `eeprom_marker: null` in the JSON.  Verifies the lookup returns
    None gracefully rather than raising or producing a garbage hex
    string."""
    import json
    from dlcp_fw.flash.dlcp_main_flash import VersionInfo

    snap = _snap()
    report = _make_report(snap)
    # Substitute a tuple that's NOT in the lookup table.
    object.__setattr__(report, "version", VersionInfo(flag=3, major=2, minor=3))
    text = _format_json_report([report])
    obj = json.loads(text)
    assert obj["mains"][0]["version"]["eeprom_marker"] is None, (
        "unknown firmware tuple must produce eeprom_marker=null"
    )


def test_human_report_with_ch_map_labels_devices() -> None:
    """`--ch-map LEFT=DevSrvsID:test` should label that device LEFT
    in the report; unmatched devices show '?' as the placeholder."""
    snap = _snap()
    report = _make_report(snap, path=b"DevSrvsID:test")
    text = _format_human_report([report], ch_map={"DevSrvsID:test": "LEFT"})
    assert "LEFT" in text
    # Substring matching: the operator can pass just the suffix.
    text2 = _format_human_report([report], ch_map={"test": "RIGHT"})
    assert "RIGHT" in text2


def test_human_report_unmapped_channel_shows_placeholder() -> None:
    """When --ch-map is given but a device doesn't match any key,
    the report shows '?' as the placeholder instead of leaving the
    column blank -- so the operator notices to extend the map."""
    snap = _snap()
    report = _make_report(snap, path=b"DevSrvsID:unmapped")
    text = _format_human_report(
        [report], ch_map={"DevSrvsID:other": "LEFT"},
    )
    assert "?" in text


def test_json_report_includes_channel_when_mapped() -> None:
    """JSON report carries the channel label so downstream consumers
    can attribute counters to specific units."""
    import json

    snap = _snap()
    report = _make_report(snap, path=b"DevSrvsID:test")
    text = _format_json_report(
        [report], ch_map={"DevSrvsID:test": "LEFT"},
    )
    obj = json.loads(text)
    assert obj["mains"][0]["channel"] == "LEFT"


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
