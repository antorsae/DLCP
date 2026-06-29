"""Tests for V3.5 SRC4382 USB diagnostics HID cmd 0x45."""

from __future__ import annotations

import json

import pytest

from dlcp_fw.flash import dlcp_src4382_diag as srcdiag
from dlcp_fw.paths import V173_CONTROL_HEX, V35_MAIN_HEX

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain

    _RUST_OK = True
    _RUST_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised only in mismatched local envs
    Chain = object  # type: ignore[assignment,misc]
    _RUST_OK = False
    _RUST_ERROR = exc


pytestmark = pytest.mark.dual_supported

SRC_REG_RX_CONTROL = 0x0D
SRC_REG_PORT_STATUS = 0x08
SRC_REG_PORT_A_CONTROL1 = 0x03
SRC_REG_PORT_A_CONTROL2 = 0x04
SRC_REG_PORT_B_CONTROL1 = 0x05
SRC_REG_PORT_B_CONTROL2 = 0x06
SRC_REG_DIT_CONTROL1 = 0x07
SRC_REG_DIT_CONTROL3 = 0x09
SRC_REG_SRC_DIT_STATUS = 0x0A
SRC_REG_RX_CONTROL2 = 0x0E
SRC_REG_AUDIO_FMT = 0x12
SRC_REG_RX_STATUS = 0x13
SRC_REG_RX_LOCK = 0x14
SRC_REG_RX_ERROR = 0x15
SRC_REG_PC_HIGH = 0x29
SRC_REG_PC_LOW = 0x2A
SRC_REG_PD_HIGH = 0x2B
SRC_REG_PD_LOW = 0x2C
SRC_REG_INT0 = 0x2D
SRC_REG_INT1 = 0x2E
SRC_REG_INT2 = 0x2F
SRC_REG_RATIO_HIGH = 0x32
SRC_REG_RATIO_LOW = 0x33
SRC_REG_PAGE_SELECT = 0x7F

ACTIVE_FLAGS = 0x05E
EVENT_FLAGS = 0x07E
LOGICAL_VOLUME = 0x066
SRC_ROUTE_REQUEST = 0x093
INPUT_SELECT = 0x099
ROUTE_SHADOW = 0x0AB
PRESET_JOB_STATE = 0x2DE
DIAG_I = 0x2E5
DIAG_R = 0x2E9
TAS_REG_VOLUME_COEFF = 0x30

CMD45_REQ_PC_PD = 0x02
CMD45_REQ_RATIO = 0x04
CMD45_FLAG_USEFUL = 0x01
CMD45_FLAG_PARTIAL = 0x02
CMD45_FLAG_PC_PD = 0x04
CMD45_FLAG_RATIO = 0x08
CMD45_FLAG_STALE = 0x10
CMD45_FLAG_PENDING = 0x20
CMD45_FLAG_CLOCK_STATUS = 0x40


def _build_cmd45_response(
    *,
    status: int = 0,
    flags: int = CMD45_FLAG_USEFUL | CMD45_FLAG_CLOCK_STATUS,
    selected_rx: int = 2,
    source_route: int = 3,
    reg0d: int = 0x02,
    reg08: int = 0xA5,
    reg12: int = 0x01,
    reg13: int = 0x02,
    reg14: int = 0x00,
    reg15: int = 0x01,
    reg32: int = 0x18,
    reg33: int = 0x00,
    reg2d: int = 0x10,
    reg2e: int = 0x20,
    reg2f: int = 0x40,
    decoded_lock: int = 0,
    decoded_payload: int = 1,
    decoded_pc_type: int = 0xFF,
    error_bits: int = 0x40,
    extension: tuple[int, int, int, int, int, int, int, int] = (
        0x38,
        0x01,
        0x38,
        0x01,
        0x38,
        0x06,
        0x10,
        0x03,
    ),
    pc_pd: tuple[int, int, int, int] = (0xFF, 0xFF, 0xFF, 0xFF),
    leading_report_id: bool = False,
) -> bytes:
    body = bytearray(64)
    body[0] = 0x45
    body[1] = status
    body[2] = 0x23
    body[3] = 0x01
    body[4] = flags
    body[5] = selected_rx
    body[6] = source_route
    body[7] = reg0d
    body[8] = reg08
    body[9] = reg12
    body[10] = reg13
    body[11] = reg14
    body[12] = reg15
    body[13] = reg32
    body[14] = reg33
    body[15] = reg2d
    body[16] = reg2e
    body[17] = reg2f
    body[18] = decoded_lock
    body[19] = decoded_payload
    body[20] = decoded_pc_type
    body[21] = error_bits
    if flags & CMD45_FLAG_CLOCK_STATUS:
        body[22:30] = bytes(extension)
        body[30:34] = b"\xFF" * 4
    else:
        body[22:34] = b"\xFF" * 12
    body[34:38] = bytes(pc_pd)
    if leading_report_id:
        return b"\x00" + bytes(body)
    return bytes(body)


def _build_cmd45_raw_response(
    reg: int,
    value: int,
    *,
    status: int = 0,
    leading_report_id: bool = False,
) -> bytes:
    body = bytearray(64)
    body[0] = 0x45
    body[1] = status
    body[2] = reg & 0xFF
    body[3] = value & 0xFF
    if leading_report_id:
        return b"\x00" + bytes(body)
    return bytes(body)


def test_parse_cmd45_complete_snapshot_with_ratio() -> None:
    resp = _build_cmd45_response(
        flags=CMD45_FLAG_USEFUL | CMD45_FLAG_RATIO | CMD45_FLAG_CLOCK_STATUS
    )
    snap = srcdiag.parse_cmd45_src4382_response(resp)

    assert snap.status_name == "ok"
    assert snap.payload_len == 0x23
    assert snap.schema == 1
    assert snap.selected_rx == 2
    assert snap.lock_name == "locked"
    assert snap.payload_name == "non_pcm"
    assert snap.rxckr_name == "256fs"
    assert snap.ratio == pytest.approx(3.0)
    assert snap.error_names == ("oslip",)
    assert snap.clock_status_present
    assert (snap.reg03, snap.reg04, snap.reg05, snap.reg06) == (0x38, 0x01, 0x38, 0x01)
    assert (snap.reg07, snap.reg09, snap.reg0a, snap.reg0e) == (0x38, 0x06, 0x10, 0x03)
    assert snap.to_dict()["raw_response_hex"] == resp.hex()
    assert snap.to_dict()["registers"] == {
        "03": 0x38,
        "04": 0x01,
        "05": 0x38,
        "06": 0x01,
        "07": 0x38,
        "0d": 0x02,
        "08": 0xA5,
        "09": 0x06,
        "0a": 0x10,
        "0e": 0x03,
        "12": 0x01,
        "13": 0x02,
        "14": 0x00,
        "15": 0x01,
        "32": 0x18,
        "33": 0x00,
        "2d": 0x10,
        "2e": 0x20,
        "2f": 0x40,
    }


def test_parse_cmd45_tolerates_report_id_prefix_and_pc_pd() -> None:
    resp = _build_cmd45_response(
        flags=CMD45_FLAG_USEFUL | CMD45_FLAG_PC_PD | CMD45_FLAG_CLOCK_STATUS,
        decoded_pc_type=0x0B,
        pc_pd=(0x00, 0x0B, 0x12, 0x34),
        leading_report_id=True,
    )
    snap = srcdiag.parse_cmd45_src4382_response(resp)

    assert snap.pc_pd_present
    assert snap.pc_type_name == "dts_type_i"
    assert (snap.pc_high, snap.pc_low, snap.pd_high, snap.pd_low) == (
        0x00,
        0x0B,
        0x12,
        0x34,
    )


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda b: b.__setitem__(0, 0x44), "unexpected cmd 0x45 echo"),
        (lambda b: b.__setitem__(1, 0x05), "unknown status byte"),
        (lambda b: b.__setitem__(2, 0x22), "payload_len mismatch"),
        (lambda b: b.__setitem__(3, 0x02), "schema mismatch"),
        (lambda b: b.__setitem__(4, b[4] | 0x80), "reserved snapshot flag"),
        (lambda b: b.__setitem__(22, 0xFF), "clock/status extension flag"),
        (lambda b: b.__setitem__(30, 0x00), "extension reserved bytes"),
        (lambda b: b.__setitem__(38, 0x01), "reserved tail bytes"),
        (lambda b: b.__setitem__(5, 0x04), "selected_rx out of range"),
        (lambda b: b.__setitem__(18, 0x03), "decoded_lock out of range"),
        (lambda b: b.__setitem__(19, 0x03), "decoded_payload out of range"),
        (lambda b: b.__setitem__(20, 0x20), "decoded_pc_type out of range"),
    ],
)
def test_parse_cmd45_rejects_invalid_schema_shapes(mutate, match) -> None:
    data = bytearray(_build_cmd45_response())
    mutate(data)
    with pytest.raises(RuntimeError, match=match):
        srcdiag.parse_cmd45_src4382_response(bytes(data))


def test_parse_cmd45_rejects_short_response() -> None:
    with pytest.raises(RuntimeError, match="short cmd 0x45 response"):
        srcdiag.parse_cmd45_src4382_response(_build_cmd45_response()[:20])


def test_parse_cmd45_accepts_legacy_response_without_clock_status_extension() -> None:
    snap = srcdiag.parse_cmd45_src4382_response(
        _build_cmd45_response(flags=CMD45_FLAG_USEFUL)
    )
    assert not snap.clock_status_present
    assert (snap.reg03, snap.reg04, snap.reg05, snap.reg06) == (0xFF, 0xFF, 0xFF, 0xFF)
    assert (snap.reg07, snap.reg09, snap.reg0a, snap.reg0e) == (0xFF, 0xFF, 0xFF, 0xFF)


def test_parse_cmd45_rejects_extension_bytes_without_clock_status_flag() -> None:
    data = bytearray(_build_cmd45_response(flags=CMD45_FLAG_USEFUL))
    data[22] = 0x38
    with pytest.raises(RuntimeError, match="extension bytes present without clock/status flag"):
        srcdiag.parse_cmd45_src4382_response(bytes(data))


def test_parse_cmd45_rejects_pc_pd_bytes_without_flag() -> None:
    data = bytearray(_build_cmd45_response())
    data[34:38] = b"\x00\x01\x02\x03"
    with pytest.raises(RuntimeError, match="PC/PD bytes present without PC/PD flag"):
        srcdiag.parse_cmd45_src4382_response(bytes(data))


def test_make_cmd45_request_is_raw_register_read() -> None:
    report = srcdiag.make_cmd45_request(0x0D)
    assert len(report) == 64
    assert report[:4] == bytes([0x45, 0x0D, 0x00, 0x00])
    assert report[4:] == bytes(60)


def test_parse_cmd45_raw_read_response() -> None:
    read = srcdiag.parse_cmd45_raw_read_response(
        _build_cmd45_raw_response(0x13, 0x02, leading_report_id=True),
        expected_reg=0x13,
    )

    assert read.status == 0
    assert read.register == 0x13
    assert read.value == 0x02

    with pytest.raises(RuntimeError, match="register echo mismatch"):
        srcdiag.parse_cmd45_raw_read_response(
            _build_cmd45_raw_response(0x14, 0x00),
            expected_reg=0x13,
        )


def test_cli_defaults_to_all_with_ratio_and_pc_pd(monkeypatch, capsys) -> None:
    seen: dict[str, object] = {}

    def fake_query_all(**kwargs):
        seen.update(kwargs)
        return [_dummy_report()]

    monkeypatch.setattr(srcdiag, "query_all", fake_query_all)

    assert srcdiag.main([]) == 0

    assert seen["include_ratio"] is True
    assert seen["include_pc_pd"] is True
    assert "SRC4382 selected-source snapshot" in capsys.readouterr().out


def test_cli_can_disable_default_ratio_and_pc_pd_for_explicit_path(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_query_one(**kwargs):
        seen.update(kwargs)
        return _dummy_report()

    monkeypatch.setattr(srcdiag, "query_one", fake_query_one)

    assert srcdiag.main(["--path", "dummy", "--no-include-ratio", "--no-include-pc-pd"]) == 0

    assert seen["path"] == b"dummy"
    assert seen["include_ratio"] is False
    assert seen["include_pc_pd"] is False


def test_cli_rejects_fast_watch_without_force() -> None:
    with pytest.raises(SystemExit) as excinfo:
        srcdiag.main(["--path", "dummy", "--watch", "--interval", "0.1"])
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    ("decoded_lock", "name"),
    [(0x00, "locked"), (0x01, "unlocked"), (0x02, "estimator_hole"), (0xFF, "unknown")],
)
def test_parse_cmd45_decodes_lock_names(decoded_lock: int, name: str) -> None:
    kwargs = (
        {"reg14": 0xFF, "reg13": 0xFF}
        if decoded_lock == 0xFF
        else {}
    )
    snap = srcdiag.parse_cmd45_src4382_response(
        _build_cmd45_response(decoded_lock=decoded_lock, **kwargs)
    )
    assert snap.lock_name == name


@pytest.mark.parametrize(
    ("decoded_payload", "name"),
    [(0x00, "pcm"), (0x01, "non_pcm"), (0x02, "dts"), (0xFF, "unknown")],
)
def test_parse_cmd45_decodes_payload_names(decoded_payload: int, name: str) -> None:
    kwargs = {"reg12": 0xFF} if decoded_payload == 0xFF else {}
    snap = srcdiag.parse_cmd45_src4382_response(
        _build_cmd45_response(decoded_payload=decoded_payload, **kwargs)
    )
    assert snap.payload_name == name


def test_parse_cmd45_derives_summary_fields_from_raw_registers() -> None:
    snap = srcdiag.parse_cmd45_src4382_response(
        _build_cmd45_response(
            selected_rx=0xFF,
            decoded_lock=0xFF,
            decoded_payload=0xFF,
            decoded_pc_type=0xFF,
            error_bits=0xFF,
            reg0d=0x09,
            reg12=0x02,
            reg13=0x03,
            reg14=0xB4,
            reg15=0x01,
            flags=CMD45_FLAG_USEFUL | CMD45_FLAG_PC_PD | CMD45_FLAG_CLOCK_STATUS,
            pc_pd=(0x00, 0x0B, 0x12, 0x34),
        )
    )

    assert snap.selected_rx == 1
    assert snap.lock_name == "unlocked"
    assert snap.payload_name == "dts"
    assert snap.pc_type_name == "dts_type_i"
    assert set(snap.error_names) == {
        "unlock",
        "bipolarity",
        "validity",
        "channel_status_crc",
        "oslip",
    }


@pytest.mark.parametrize(
    ("pc_type", "name"),
    [(0x01, "dolby_ac3"), (0x0B, "dts_type_i"), (0x0C, "dts_type_ii"), (0x0D, "dts_type_iii")],
)
def test_parse_cmd45_decodes_pc_type_names(pc_type: int, name: str) -> None:
    snap = srcdiag.parse_cmd45_src4382_response(
        _build_cmd45_response(
            flags=CMD45_FLAG_USEFUL | CMD45_FLAG_PC_PD | CMD45_FLAG_CLOCK_STATUS,
            decoded_pc_type=pc_type,
            pc_pd=(0x00, pc_type, 0x12, 0x34),
        )
    )
    assert snap.pc_type_name == name


@pytest.mark.parametrize(
    ("bit", "name"),
    [
        (0, "unlock"),
        (1, "bipolarity"),
        (2, "parity"),
        (3, "validity"),
        (4, "channel_status_crc"),
        (5, "q_channel_crc"),
        (6, "oslip"),
        (7, "q_channel_change"),
    ],
)
def test_parse_cmd45_decodes_each_error_bit(bit: int, name: str) -> None:
    snap = srcdiag.parse_cmd45_src4382_response(
        _build_cmd45_response(error_bits=1 << bit)
    )
    assert snap.error_names == (name,)


def _dummy_report(snapshot: srcdiag.Src4382Snapshot | None = None) -> srcdiag.Src4382DeviceReport:
    info = srcdiag.HidDeviceInfo(
        vendor_id=srcdiag.DEFAULT_VID,
        product_id=srcdiag.DEFAULT_PID,
        path=b"usb-path-1",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="",
    )
    return srcdiag.Src4382DeviceReport(
        info=info,
        snapshot=snapshot or srcdiag.parse_cmd45_src4382_response(_build_cmd45_response()),
        label="left",
    )


def test_json_report_contains_raw_bytes_and_redacted_path() -> None:
    report = _dummy_report()
    payload = srcdiag._reports_to_json([report], show_path=False)
    device = payload["devices"][0]

    assert device["hid_path"].startswith("<hid:")
    assert device["snapshot"]["raw_response_hex"] == report.snapshot.raw_response.hex()
    assert device["snapshot"]["decoded"]["errors"] == ["oslip"]


def test_human_report_renders_ascii_tables_and_dlcp_native_rate() -> None:
    snap = srcdiag.parse_cmd45_src4382_response(
        _build_cmd45_response(
            flags=CMD45_FLAG_USEFUL | CMD45_FLAG_RATIO | CMD45_FLAG_CLOCK_STATUS,
            selected_rx=0,
            source_route=3,
            reg0d=0x08,
            reg08=0x30,
            reg12=0x00,
            reg13=0x03,
            reg14=0x00,
            reg15=0x00,
            reg32=0x08,
            reg33=0x00,
            reg2d=0x02,
            reg2e=0x00,
            reg2f=0x00,
            decoded_payload=0,
            error_bits=0x00,
        )
    )
    text = srcdiag.format_human_report([_dummy_report(snap)])

    assert "+-" in text
    assert "| Field" in text
    assert "SRC4382 selected-source snapshot" in text
    assert "route=3; AES; check=OK; selected=RX1" in text
    assert "input=93.750 kHz est; nearest=93.75 kHz DLCP native" in text
    assert "ratio=1.000000" in text
    assert "basis=DIT SRC MCLK/256" in text
    assert "Port A SRC MCLK/256=93.750 kHz path" in text
    assert "| 03  | 0x38" in text
    assert "mode=master; out=SRC" in text
    assert "| 0A  | 0x10" in text
    assert "READY irq=on" in text
    assert "| 0D  | 0x08" in text
    assert "RXMUX=RX1; DIR ref=MCLK 24MHz" in text
    assert "| 2D  | 0x02" in text
    assert "input=DIR; ref=MCLK 24MHz; mute=off" in text
    assert "| PC    | n/a   | not requested |" in text
    assert "| Errors     | none" in text


def test_human_report_decodes_non_pcm_pc_pd_and_route_mismatch() -> None:
    snap = srcdiag.parse_cmd45_src4382_response(
        _build_cmd45_response(
            flags=CMD45_FLAG_USEFUL | CMD45_FLAG_PC_PD | CMD45_FLAG_RATIO | CMD45_FLAG_CLOCK_STATUS,
            selected_rx=2,
            source_route=2,
            reg0d=0x08,
            reg08=0x30,
            reg12=0x01,
            reg13=0x01,
            reg14=0x14,
            reg15=0x01,
            reg32=0x04,
            reg33=0x19,
            reg2d=0x12,
            reg2e=0x25,
            reg2f=0xC0,
            extension=(0x38, 0x01, 0x08, 0x05, 0x38, 0x06, 0x10, 0x03),
            decoded_payload=1,
            decoded_lock=1,
            decoded_pc_type=0x0B,
            error_bits=0x43,
            pc_pd=(0x00, 0x8B, 0x12, 0x34),
        )
    )
    text = srcdiag.format_human_report([_dummy_report(snap)])

    assert "route=2; USB Audio; check=MISMATCH expected 0D=0x0A 08=0xB0" in text
    assert "Payload    | IEC61937/non-PCM" in text
    assert "UNLOCK=1; BPERR, UNLOCK" in text
    assert "OSLIP" in text
    assert "type=DTS Type 1; error=on; stream=0" in text
    assert "burst length=4660 bits" in text
    assert "input=48.019 kHz est; nearest=48 kHz" in text


def test_human_report_allows_output_rate_override_and_disable() -> None:
    snap = srcdiag.parse_cmd45_src4382_response(
        _build_cmd45_response(
            flags=CMD45_FLAG_USEFUL | CMD45_FLAG_RATIO | CMD45_FLAG_CLOCK_STATUS,
            reg32=0x08,
            reg33=0x00,
        )
    )

    override = srcdiag.format_human_report([_dummy_report(snap)], output_rate_hz=48_000.0)
    disabled = srcdiag.format_human_report([_dummy_report(snap)], output_clock_hz=None)

    assert "input=48.000 kHz est; nearest=48 kHz" in override
    assert "basis=caller-supplied output rate 48.000 kHz" in override
    assert "ratio=1.000000; no proven MCLK output-rate basis" in disabled


def test_human_report_estimates_input_rate_when_ready_irq_is_masked() -> None:
    snap = srcdiag.parse_cmd45_src4382_response(
        _build_cmd45_response(
            flags=CMD45_FLAG_USEFUL | CMD45_FLAG_RATIO | CMD45_FLAG_CLOCK_STATUS,
            reg13=0x03,
            reg32=0x03,
            reg33=0xC3,
            extension=(0x30, 0x01, 0x08, 0x01, 0x34, 0x00, 0x00, 0x08),
            error_bits=0x00,
        )
    )

    text = srcdiag.format_human_report([_dummy_report(snap)])

    assert "input=44.083 kHz est; nearest=44.1 kHz" in text
    assert "ratio=0.470215" in text
    assert "basis=DIT DIR MCLK/256" in text
    assert "READY irq=off/masked" in text
    assert "READY irq=off" in text


def test_cli_watch_json_emits_ndjson(monkeypatch, capsys) -> None:
    monkeypatch.setattr(srcdiag, "_query_from_args", lambda _args: [_dummy_report()])

    def stop_after_first_sleep(_interval: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(srcdiag.time, "sleep", stop_after_first_sleep)
    assert srcdiag.main(["--path", "dummy", "--json", "--watch"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["cmd"] == "0x45"


def test_probe_cmd45_sends_one_raw_register_read(monkeypatch) -> None:
    seen: list[tuple[bytes, int]] = []

    def fake_exchange(_dev, report: bytes, *, timeout_ms: int) -> bytes:
        seen.append((report, timeout_ms))
        return _build_cmd45_raw_response(0x13, 0x02)

    monkeypatch.setattr(srcdiag, "_exchange_report", fake_exchange)
    read = srcdiag._probe_cmd45_reg(object(), 0x13, timeout_ms=123)

    assert read.status == 0
    assert read.register == 0x13
    assert read.value == 0x02
    assert len(seen) == 1
    report, timeout_ms = seen[0]
    assert report[:4] == bytes([0x45, 0x13, 0x00, 0x00])
    assert timeout_ms == 123


def test_query_src4382_snapshot_assembles_raw_reads(monkeypatch) -> None:
    values = {
        SRC_REG_PORT_A_CONTROL1: 0x38,
        SRC_REG_PORT_A_CONTROL2: 0x01,
        SRC_REG_PORT_B_CONTROL1: 0x38,
        SRC_REG_PORT_B_CONTROL2: 0x01,
        SRC_REG_DIT_CONTROL1: 0x38,
        SRC_REG_DIT_CONTROL3: 0x06,
        SRC_REG_SRC_DIT_STATUS: 0x00,
        SRC_REG_RX_CONTROL2: 0x03,
        SRC_REG_RX_CONTROL: 0x08,
        SRC_REG_PORT_STATUS: 0x30,
        SRC_REG_AUDIO_FMT: 0x02,
        SRC_REG_RX_STATUS: 0x03,
        SRC_REG_RX_LOCK: 0x00,
        SRC_REG_RX_ERROR: 0x01,
        SRC_REG_INT0: 0x10,
        SRC_REG_INT1: 0x20,
        SRC_REG_INT2: 0x40,
        SRC_REG_RATIO_HIGH: 0x08,
        SRC_REG_RATIO_LOW: 0x00,
        SRC_REG_PC_HIGH: 0x00,
        SRC_REG_PC_LOW: 0x0B,
        SRC_REG_PD_HIGH: 0x12,
        SRC_REG_PD_LOW: 0x34,
    }
    seen: list[int] = []

    def fake_probe(_dev, reg: int, *, timeout_ms: int):
        assert timeout_ms == 123
        seen.append(reg)
        return srcdiag.Cmd45RawRead(
            status=0,
            register=reg,
            value=values[reg],
            raw_response=_build_cmd45_raw_response(reg, values[reg]),
        )

    monkeypatch.setattr(srcdiag, "_probe_cmd45_reg", fake_probe)
    snap = srcdiag.query_src4382_snapshot(object(), timeout_ms=123)

    assert seen == list(srcdiag.CMD45_RAW_READ_REGS) + list(srcdiag.CMD45_RAW_RATIO_REGS) + list(srcdiag.CMD45_RAW_PC_PD_REGS)
    assert snap.status_name == "ok"
    assert snap.source_route == 3
    assert snap.selected_rx == 0
    assert snap.lock_name == "locked"
    assert snap.payload_name == "dts"
    assert snap.pc_type_name == "dts_type_i"
    assert snap.ratio == pytest.approx(1.0)


def test_query_all_rejects_no_matching_devices(monkeypatch) -> None:
    monkeypatch.setattr(srcdiag, "enumerate_devices", lambda _vid, _pid: [])
    with pytest.raises(RuntimeError, match="no matching DLCP HID devices"):
        srcdiag.query_all()


def test_query_one_propagates_explicit_path_failures(monkeypatch) -> None:
    def fail_pick(_vid: int, _pid: int, _path: bytes | None):
        raise RuntimeError("explicit path missing")

    monkeypatch.setattr(srcdiag, "_pick_device", fail_pick)
    with pytest.raises(RuntimeError, match="explicit path missing"):
        srcdiag.query_one(path=b"missing")


def test_cli_diag_status_exit_policy(monkeypatch) -> None:
    partial = srcdiag.parse_cmd45_src4382_response(
        _build_cmd45_response(status=4, flags=CMD45_FLAG_PARTIAL)
    )
    monkeypatch.setattr(srcdiag, "_query_from_args", lambda _args: [_dummy_report(partial)])

    assert srcdiag.main(["--path", "dummy", "--json"]) == 0
    assert srcdiag.main(["--path", "dummy", "--json", "--fail-on-diag-status"]) == 2


def _boot_v35_chain() -> Chain:
    if not _RUST_OK:
        pytest.skip(f"rust facade not importable: {_RUST_ERROR!r}")
    if not V35_MAIN_HEX.exists() or not V173_CONTROL_HEX.exists():
        pytest.skip("missing canonical V3.5/V1.73 release artifacts")
    chain = Chain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX),
        main_hex_path=str(V35_MAIN_HEX),
    )
    chain.run_until_connected(limit=400)
    assert chain.is_connected() and not chain.is_waiting()
    chain.step_ticks(50_000_000)
    return chain


def _cmd45(reg: int) -> bytes:
    report = bytearray(64)
    report[0] = 0x45
    report[1] = reg & 0xFF
    return bytes(report)


def _firmware_cmd45(chain: Chain, reg: int) -> bytes:
    resp, dispatch_hits = chain.firmware_hid_report(0, _cmd45(reg), max_steps=120_000)
    assert dispatch_hits >= 1
    assert len(resp) == 64
    return resp


def _complete_cmd45_snapshot(chain: Chain, flags: int = 0) -> srcdiag.Src4382Snapshot:
    regs = list(srcdiag.CMD45_RAW_READ_REGS)
    include_ratio = bool(flags & CMD45_REQ_RATIO)
    include_pc_pd = bool(flags & CMD45_REQ_PC_PD)
    if include_ratio:
        regs.extend(srcdiag.CMD45_RAW_RATIO_REGS)
    if include_pc_pd:
        regs.extend(srcdiag.CMD45_RAW_PC_PD_REGS)
    reads = {
        reg: srcdiag.parse_cmd45_raw_read_response(_firmware_cmd45(chain, reg), expected_reg=reg)
        for reg in regs
    }
    return srcdiag._raw_read_values_to_snapshot(
        reads,
        include_ratio=include_ratio,
        include_pc_pd=include_pc_pd,
    )


def _prime_src_regs(chain: Chain) -> None:
    chain.poke_main_src4382_reg(0, SRC_REG_PORT_A_CONTROL1, 0x38)
    chain.poke_main_src4382_reg(0, SRC_REG_PORT_A_CONTROL2, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_PORT_B_CONTROL1, 0x38)
    chain.poke_main_src4382_reg(0, SRC_REG_PORT_B_CONTROL2, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_DIT_CONTROL1, 0x38)
    chain.poke_main_src4382_reg(0, SRC_REG_DIT_CONTROL3, 0x06)
    chain.poke_main_src4382_reg(0, SRC_REG_SRC_DIT_STATUS, 0x10)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_CONTROL2, 0x03)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_CONTROL, 0x02)
    chain.poke_main_src4382_reg(0, SRC_REG_PORT_STATUS, 0xA5)
    chain.poke_main_src4382_reg(0, SRC_REG_AUDIO_FMT, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x02)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_ERROR, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_INT0, 0x10)
    chain.poke_main_src4382_reg(0, SRC_REG_INT1, 0x20)
    chain.poke_main_src4382_reg(0, SRC_REG_INT2, 0x40)
    chain.poke_main_src4382_reg(0, SRC_REG_RATIO_HIGH, 0x18)
    chain.poke_main_src4382_reg(0, SRC_REG_RATIO_LOW, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_PC_HIGH, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_PC_LOW, 0x0B)
    chain.poke_main_src4382_reg(0, SRC_REG_PD_HIGH, 0x12)
    chain.poke_main_src4382_reg(0, SRC_REG_PD_LOW, 0x34)


def _main_state(chain: Chain) -> tuple[int, ...]:
    return tuple(
        chain.read_main_reg(0, addr)
        for addr in (
            ACTIVE_FLAGS,
            EVENT_FLAGS,
            LOGICAL_VOLUME,
            LOGICAL_VOLUME + 1,
            LOGICAL_VOLUME + 2,
            LOGICAL_VOLUME + 3,
            SRC_ROUTE_REQUEST,
            INPUT_SELECT,
            ROUTE_SHADOW,
            PRESET_JOB_STATE,
            DIAG_I,
            DIAG_R,
        )
    )


def test_firmware_cmd45_raw_reads_assemble_snapshot() -> None:
    chain = _boot_v35_chain()
    _prime_src_regs(chain)

    raw = srcdiag.parse_cmd45_raw_read_response(
        _firmware_cmd45(chain, SRC_REG_RX_STATUS),
        expected_reg=SRC_REG_RX_STATUS,
    )
    assert raw.status == 0
    assert raw.value == 0x02

    snap = _complete_cmd45_snapshot(chain)
    assert snap.status_name == "ok"
    assert snap.useful
    assert snap.clock_status_present
    assert not snap.partial
    assert not snap.stale
    assert not snap.job_pending
    assert (snap.reg03, snap.reg04, snap.reg05, snap.reg06) == (
        0x38,
        0x01,
        0x38,
        0x01,
    )
    assert (snap.reg07, snap.reg09, snap.reg0a, snap.reg0e) == (
        0x38,
        0x06,
        0x10,
        0x03,
    )
    assert snap.reg12 == 0x01
    assert snap.reg13 == 0x02
    assert snap.reg14 == 0x00
    assert snap.reg15 == 0x01
    assert snap.lock_name == "locked"
    assert snap.payload_name == "non_pcm"
    assert not snap.ratio_present
    assert not snap.pc_pd_present
    assert snap.reg32 == 0xFF and snap.reg33 == 0xFF
    assert (snap.pc_high, snap.pc_low, snap.pd_high, snap.pd_low) == (
        0xFF,
        0xFF,
        0xFF,
        0xFF,
    )


def test_firmware_cmd45_optional_ratio_and_pc_pd() -> None:
    chain = _boot_v35_chain()
    _prime_src_regs(chain)
    flags = CMD45_REQ_PC_PD | CMD45_REQ_RATIO
    chain.reset_main_src4382_stats(0)

    snap = _complete_cmd45_snapshot(chain, flags)

    assert snap.status_name == "ok"
    assert snap.ratio_present
    assert snap.pc_pd_present
    assert snap.ratio == pytest.approx(3.0)
    assert (snap.pc_high, snap.pc_low, snap.pd_high, snap.pd_low) == (
        0x00,
        0x0B,
        0x12,
        0x34,
    )
    assert snap.pc_type_name == "dts_type_i"
    stats = chain.read_main_src4382_stats(0)
    for reg in (
        SRC_REG_PORT_A_CONTROL1,
        SRC_REG_PORT_A_CONTROL2,
        SRC_REG_PORT_B_CONTROL1,
        SRC_REG_PORT_B_CONTROL2,
        SRC_REG_DIT_CONTROL1,
        SRC_REG_DIT_CONTROL3,
        SRC_REG_SRC_DIT_STATUS,
        SRC_REG_RX_CONTROL2,
    ):
        assert stats["reads_by_subaddr"][reg] >= 1, stats
    assert stats["reads_by_subaddr"][SRC_REG_RATIO_HIGH] >= 1, stats
    assert stats["reads_by_subaddr"][SRC_REG_RATIO_LOW] >= 1, stats


def test_firmware_cmd45_has_no_request_whitelist_or_padding_validation() -> None:
    chain = _boot_v35_chain()
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x03)
    chain.reset_main_src4382_stats(0)
    report = bytearray(64)
    report[0] = 0x45
    report[1] = SRC_REG_RX_STATUS
    report[2] = 0x08
    report[63] = 0x01

    resp, dispatch_hits = chain.firmware_hid_report(0, report, max_steps=120_000)
    assert dispatch_hits >= 1
    read = srcdiag.parse_cmd45_raw_read_response(resp, expected_reg=SRC_REG_RX_STATUS)

    assert read.status == 0
    assert read.value == 0x03
    stats = chain.read_main_src4382_stats(0)
    assert stats["reads_by_subaddr"][SRC_REG_RX_STATUS] >= 1
    assert stats["write_transactions"] == 0


def test_firmware_cmd45_can_read_page_select_but_never_writes_page() -> None:
    chain = _boot_v35_chain()
    chain.poke_main_src4382_reg(0, SRC_REG_PAGE_SELECT, 0xAA)
    chain.reset_main_src4382_stats(0)

    read = srcdiag.parse_cmd45_raw_read_response(
        _firmware_cmd45(chain, SRC_REG_PAGE_SELECT),
        expected_reg=SRC_REG_PAGE_SELECT,
    )
    assert read.status == 0
    assert read.value == 0xAA

    cmd46 = bytearray(64)
    cmd46[0] = 0x46
    resp46, dispatch_hits46 = chain.firmware_hid_report(0, cmd46, max_steps=120_000)
    assert dispatch_hits46 >= 1
    assert resp46[0] != 0x46

    stats = chain.read_main_src4382_stats(0)
    assert stats["reads_by_subaddr"][SRC_REG_PAGE_SELECT] >= 1
    assert stats["write_transactions"] == 0
    assert chain.read_main_src4382_reg(0, SRC_REG_PAGE_SELECT) == 0xAA
    assert stats["writes_by_subaddr"][SRC_REG_PAGE_SELECT] == 0


def test_firmware_cmd45_i2c_address_nack_is_reflected_in_raw_status() -> None:
    chain = _boot_v35_chain()
    chain.reset_main_src4382_stats(0)
    chain.inject_main_src4382_address_nack(0, 1000)

    failed = srcdiag.parse_cmd45_raw_read_response(
        _firmware_cmd45(chain, SRC_REG_RX_STATUS),
        expected_reg=SRC_REG_RX_STATUS,
    )

    assert failed.status != 0
    stats = chain.read_main_src4382_stats(0)
    assert stats["address_nacks_consumed"] >= 1


def test_firmware_cmd45_i2c_data_nack_is_consumed_without_cache_state() -> None:
    chain = _boot_v35_chain()
    chain.reset_main_src4382_stats(0)
    chain.inject_main_src4382_data_nack(0, 1)

    read = srcdiag.parse_cmd45_raw_read_response(
        _firmware_cmd45(chain, SRC_REG_RX_STATUS),
        expected_reg=SRC_REG_RX_STATUS,
    )

    assert read.register == SRC_REG_RX_STATUS
    assert chain.read_main_src4382_stats(0)["data_nacks_consumed"] >= 1


def test_firmware_cmd45_failed_raw_read_does_not_preserve_stale_cache() -> None:
    chain = _boot_v35_chain()
    _prime_src_regs(chain)
    assert _complete_cmd45_snapshot(chain).status_name == "ok"

    chain.inject_main_src4382_address_nack(0, 1000)
    failed = srcdiag.parse_cmd45_raw_read_response(
        _firmware_cmd45(chain, SRC_REG_RX_CONTROL),
        expected_reg=SRC_REG_RX_CONTROL,
    )

    assert failed.status != 0
    assert failed.value == 0xFF


def test_firmware_cmd45_lock_heuristic_variants() -> None:
    chain = _boot_v35_chain()
    _prime_src_regs(chain)
    cases = [
        (0x04, 0x02, "unlocked"),
        (0x00, 0x00, "estimator_hole"),
        (0x00, 0x03, "locked"),
    ]
    for reg14, reg13, expected in cases:
        chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, reg14)
        chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, reg13)
        snap = _complete_cmd45_snapshot(chain)
        assert snap.lock_name == expected


def test_firmware_cmd45_payload_and_pc_type_decode_variants() -> None:
    chain = _boot_v35_chain()
    _prime_src_regs(chain)

    chain.poke_main_src4382_reg(0, SRC_REG_AUDIO_FMT, 0x00)
    assert _complete_cmd45_snapshot(chain).payload_name == "pcm"

    chain.poke_main_src4382_reg(0, SRC_REG_AUDIO_FMT, 0x02)
    chain.poke_main_src4382_reg(0, SRC_REG_PC_LOW, 0x01)
    snap = _complete_cmd45_snapshot(chain, CMD45_REQ_PC_PD)
    assert snap.payload_name == "dts"
    assert snap.pc_type_name == "dolby_ac3"


def test_firmware_cmd45_repeated_polling_is_read_only_for_main_audio_state() -> None:
    chain = _boot_v35_chain()
    _prime_src_regs(chain)
    chain.poke_main_src4382_reg(0, SRC_REG_AUDIO_FMT, 0x00)
    chain.step_ticks(50_000_000)
    assert _complete_cmd45_snapshot(chain, CMD45_REQ_RATIO).status_name == "ok"
    before = _main_state(chain)
    chain.reset_main_src4382_stats(0)
    chain.reset_main_dsp_write_log(0)
    chain.reset_main_tas3108_stats(0)

    for _ in range(3):
        snap = _complete_cmd45_snapshot(chain, CMD45_REQ_RATIO)
        assert snap.status_name == "ok"

    assert _main_state(chain) == before
    src_stats = chain.read_main_src4382_stats(0)
    assert src_stats["writes_by_subaddr"][SRC_REG_PAGE_SELECT] == 0
    assert chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF) is None
