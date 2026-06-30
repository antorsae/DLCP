from __future__ import annotations

from pathlib import Path
import shutil
import sys
import types

import pytest

from dlcp_fw.paths import (
    STOCK_CONTROL_HEX_V14,
    V171_CONTROL_HEX,
    V172_CONTROL_HEX,
    V173_CONTROL_ASM,
    V173_CONTROL_HEX,
    V35_MAIN_ASM,
    V35_MAIN_HEX,
)
from dlcp_fw.flash.dlcp_control_flash import (
    CONTROL_BOOT_START,
    CONTROL_EEPROM_BASE,
    CONTROL_PROG_END_EXCL,
    CONTROL_RELEASE_MAGIC,
    CONTROL_RELEASE_METADATA_ADDR,
    ControlRelayNotArmedError,
    HidDeviceInfo,
    PreflightError,
    _pick_device,
    build_control_stream,
    bootloader_mismatch_addresses,
    crc_stream,
    detect_static_hex_control_release_info,
    flash_control,
    main,
    parse_intel_hex,
    run_preflight,
)
from dlcp_fw.patch.build_v171_release import build_v171_release, bump_v171_release_revision
from dlcp_fw.patch.build_v173_release import build_v173_release
from dlcp_fw.sim.v30_symbols import assemble_v30


# All tests in this module are backend-agnostic (static source/hex
# analysis, flash-tool CLI plumbing, semantic-guard regex matchers).
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
pytestmark = pytest.mark.dual_supported

_RELAY_HANDSHAKE_MAX_TICKS = 500_000_000


def _stock_control_v14() -> Path:
    return STOCK_CONTROL_HEX_V14


def _mk_report(cmd: int) -> bytearray:
    report = bytearray(64)
    report[0] = cmd & 0xFF
    return report


def _first_control_stream_report(stream: bytes) -> bytes:
    report = _mk_report(0x42)
    report[2 : 2 + 30] = stream[:30]
    return bytes(report)


def _copy_main_include(tmp_path: Path) -> None:
    shutil.copy2(V35_MAIN_ASM.parent / "dlcp_main_ram.inc", tmp_path / "dlcp_main_ram.inc")


def _assemble_temp_v35(tmp_path: Path, text: str, *, stem: str = "dlcp_main_v35") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    _copy_main_include(tmp_path)
    asm_path = tmp_path / f"{stem}.asm"
    hex_path = tmp_path / f"{stem}.hex"
    asm_path.write_text(text, encoding="utf-8")
    assemble_v30(asm_path, hex_path, output_lst=hex_path.with_suffix(".lst"))
    assert hex_path.with_suffix(".lst").exists()
    return hex_path


def _chain(control_hex: Path, main_hex: Path):
    native = pytest.importorskip("dlcp_fw.sim.dlcp_sim_native")
    return native.Chain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )


def _connected_chain(control_hex: Path, main_hex: Path):
    chain = _chain(control_hex, main_hex)
    assert chain.run_until_connected(300) < 300, chain.lcd_lines()
    return chain


def _single_main_chain(control_hex: Path, main_hex: Path):
    native = pytest.importorskip("dlcp_fw.sim.dlcp_sim_native")
    return native.Chain.from_v17_v3x_chain(
        control_hex_path=str(control_hex),
        v3x_main_hex_path=str(main_hex),
    )


def _connected_single_main_chain(control_hex: Path, main_hex: Path):
    chain = _single_main_chain(control_hex, main_hex)
    assert chain.run_until_connected(300) < 300, chain.lcd_lines()
    return chain


def _assert_flash_release_metadata(readback: bytes, expected: bytes) -> tuple[int, int, int, int]:
    offset = CONTROL_RELEASE_METADATA_ADDR
    actual_meta = readback[offset : offset + 16]
    expected_meta = expected[offset : offset + 16]
    assert actual_meta == expected_meta
    assert actual_meta[: len(CONTROL_RELEASE_MAGIC)] == CONTROL_RELEASE_MAGIC
    return actual_meta[8], actual_meta[9], actual_meta[10], actual_meta[11]


def _manual_bootloader_chain(control_hex: Path, main_hex: Path):
    chain = _chain(control_hex, main_hex)
    chain.write_control_eeprom_byte(0xFF, 0x00)
    for _ in range(80):
        tx = bytes(
            byte for _tick, src, dst, byte in chain.uart_tx_records_full()
            if src == 0 and dst == 1
        )
        if b"FW_Upd" in tx:
            return chain
        chain.step_ticks(1_000_000)
    pytest.fail(
        f"CONTROL bootloader prompt not observed; lcd={chain.lcd_lines()!r}, "
        f"tx_len={len(chain.uart_tx_records_full())}"
    )


def _flash_stream_through_main_relay(
    chain,
    stream: bytes,
    *,
    control_bootloader_reset_after_ticks: int | None = None,
) -> tuple[bytes, int]:  # type: ignore[no-untyped-def]
    total_ticks = 0
    pos = 0
    report_i = 0
    while pos < len(stream):
        chunk = stream[pos : pos + 30]
        if len(chunk) < 30:
            chunk = chunk + bytes([0xFF]) * (30 - len(chunk))
        report = _mk_report(0x42)
        report[2 : 2 + 30] = chunk
        resp, dispatch_hits, ticks = chain.firmware_hid_report_full_chain(
            0,
            bytes(report),
            max_ticks=500_000_000,
            control_bootloader_reset_after_ticks=(
                control_bootloader_reset_after_ticks if report_i == 0 else None
            ),
        )
        total_ticks += ticks
        assert dispatch_hits >= 1
        assert resp[0] == 0x42
        assert resp[1] == 0x00, {
            "report": report_i + 1,
            "pos": pos,
            "resp": resp[:8],
        }
        pos += 30
        report_i += 1

    expected_crc = crc_stream(stream)
    report = _mk_report(0x41)
    report[4] = (expected_crc >> 8) & 0xFF
    report[5] = expected_crc & 0xFF
    resp, dispatch_hits, ticks = chain.firmware_hid_report_full_chain(
        0,
        bytes(report),
        max_ticks=500_000_000,
    )
    total_ticks += ticks
    assert dispatch_hits >= 1
    return resp, total_ticks


def test_preflight_bootloader_match(patched_control_hex: Path) -> None:
    candidate = parse_intel_hex(str(patched_control_hex))
    reference = parse_intel_hex(str(_stock_control_v14()))
    preflight = run_preflight(
        hex_mem=candidate,
        bootloader_ref_mem=reference,
        require_bootloader_match=True,
    )
    assert preflight["bootloader_match"] is True


def test_preflight_rejects_bootloader_drift(patched_control_hex: Path) -> None:
    candidate = parse_intel_hex(str(patched_control_hex))
    reference = parse_intel_hex(str(_stock_control_v14()))
    candidate_mut = dict(candidate)
    candidate_mut[CONTROL_BOOT_START] = (candidate_mut.get(CONTROL_BOOT_START, 0xFF) ^ 0x01) & 0xFF

    with pytest.raises(PreflightError, match="bootloader bytes differ from reference"):
        run_preflight(
            hex_mem=candidate_mut,
            bootloader_ref_mem=reference,
            require_bootloader_match=True,
        )


def test_bootloader_mismatch_addresses_reports_exact_site(patched_control_hex: Path) -> None:
    candidate = parse_intel_hex(str(patched_control_hex))
    reference = parse_intel_hex(str(_stock_control_v14()))
    candidate_mut = dict(candidate)
    target = CONTROL_BOOT_START + 0x37
    candidate_mut[target] = (candidate_mut.get(target, 0xFF) ^ 0x80) & 0xFF

    mismatches = bootloader_mismatch_addresses(candidate_mut, reference)
    assert target in mismatches


def test_preflight_without_bootloader_check_allows_no_reference(patched_control_hex: Path) -> None:
    candidate = parse_intel_hex(str(patched_control_hex))
    preflight = run_preflight(
        hex_mem=candidate,
        bootloader_ref_mem=None,
        require_bootloader_match=False,
    )
    assert preflight["payload_len"] > 0


def test_cli_blocks_unsafe_flags_without_force(patched_control_hex: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--hex", str(patched_control_hex), "--preflight-only", "--no-verify"])
    assert exc.value.code == 2


def test_cli_allows_unsafe_when_explicitly_forced(patched_control_hex: Path) -> None:
    rc = main(["--hex", str(patched_control_hex), "--preflight-only", "--no-verify", "--force-unsafe"])
    assert rc == 0


def test_detect_static_hex_control_release_info_v171() -> None:
    release = detect_static_hex_control_release_info(parse_intel_hex(str(V171_CONTROL_HEX)))
    assert release is not None
    assert (release.major, release.minor, release.sub) == (0x01, 0x07, 0x31)
    assert release.revision is not None
    assert release.revision >= 0x01


def test_detect_static_hex_control_release_info_v172() -> None:
    release = detect_static_hex_control_release_info(parse_intel_hex(str(V172_CONTROL_HEX)))
    assert release is not None
    assert (release.major, release.minor, release.sub) == (0x01, 0x07, 0x32)
    assert release.revision is not None
    assert release.revision >= 0x01
    assert release.build_date is not None


def test_detect_static_hex_control_release_info_v173() -> None:
    if not V173_CONTROL_HEX.exists():
        pytest.skip(f"missing: {V173_CONTROL_HEX.name}")
    release = detect_static_hex_control_release_info(parse_intel_hex(str(V173_CONTROL_HEX)))
    assert release is not None
    assert (release.major, release.minor, release.sub) == (0x01, 0x07, 0x33)
    assert release.revision is not None
    assert release.revision >= 0x01
    assert release.build_date is not None


def test_v171_release_metadata_is_within_flashable_app_window() -> None:
    assert CONTROL_RELEASE_METADATA_ADDR >= 0x0040
    assert CONTROL_RELEASE_METADATA_ADDR + 12 <= CONTROL_PROG_END_EXCL


def test_build_control_stream_preserves_release_metadata_bytes() -> None:
    candidate = parse_intel_hex(str(V171_CONTROL_HEX))
    stream = build_control_stream(candidate)
    offset = CONTROL_RELEASE_METADATA_ADDR
    assert stream[offset : offset + len(CONTROL_RELEASE_MAGIC)] == CONTROL_RELEASE_MAGIC
    assert stream[offset + 8 : offset + 11] == bytes([0x01, 0x07, 0x31])


def test_build_control_stream_ignores_pb1_pb2_input_eeprom_records() -> None:
    candidate = {
        0x0000: 0x12,
        CONTROL_EEPROM_BASE + 0x5E: 0xC5,
        CONTROL_EEPROM_BASE + 0x5F: 0xB7,
    }

    stream = build_control_stream(candidate)

    assert stream[0x0000] == 0x12
    assert stream[0x5E] == 0xFF
    assert stream[0x5F] == 0xFF


def test_hfd_v212_control_update_disassembly_contract_is_documented() -> None:
    pc_dir = Path("firmware/disasm/PC/HFD_v2.12")
    builder = (pc_dir / "disasm_packet_builder_554590_554980.asm").read_text(encoding="utf-8")
    parser = (pc_dir / "disasm_response_parser_553910_554520.asm").read_text(encoding="utf-8")
    txlogic = (pc_dir / "disasm_cmd3_txlogic_554c00_554ed0.asm").read_text(encoding="utf-8")

    # HFD command 0x42 is the CONTROL firmware byte stream.  The builder
    # starts at internal report offset 3, because offset 0 is HID report ID,
    # offset 1 is command 0x42, and offset 2 remains zero.  That maps to
    # device payload offsets 2..31 after hidapi's report-ID byte is stripped.
    assert "5548f0: be 03 00 00 00" in builder
    assert "554900: 8b 15 80 94 56 00" in builder
    assert "554908: 88 44 32 25" in builder
    assert "554919: e8 86 05 00 00" in builder

    # HFD command 0x41 sends the rolling CRC through the big-endian dword
    # helper at offset 3.  The high/low CRC bytes therefore land at device
    # payload offsets 4 and 5, matching dlcp_control_flash.py.
    assert "55492a: 0f b7 0d 6c b3 57 00" in builder
    assert "554931: b2 03" in builder
    assert "554935: e8 36 05 00 00" in builder
    assert "554e70: 53" in txlogic
    assert "554e7f: 88 5c 30 25" in txlogic

    # The checked-in slice stops at 0x554ECC, before the final xor literal
    # at 0x554ED7.  These instructions still pin the same LSB-first bit-13
    # CRC helper entry and data-bit injection used by MAIN's relay.
    assert "554eb2: c1 e9 0d" in txlogic
    assert "554ebb: 66 d1 26" in txlogic
    assert "554ec9: 66 01 1e" in txlogic

    # Responses are ACK-paced: HFD handles 0x42 responses, advances its report
    # counter, and either sends another 0x42 or finalizes with 0x41.  The 0x41
    # response handler treats byte 0xAA as firmware-update success.
    assert "554266: a1 04 92 56 00" in parser
    assert "554317: b2 42" in parser
    assert "554302: b2 41" in parser
    assert "554333: 80 7f 07 aa" in parser


def test_flash_control_starts_with_first_hfd_data_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeHidDevice:
        def __init__(self) -> None:
            self.writes: list[bytes] = []
            self.reads: list[int] = []

        def open_path(self, path: bytes) -> None:
            assert path == b"pb1"

        def set_nonblocking(self, value: bool) -> None:
            assert value is True

        def write(self, payload: bytes) -> int:
            self.writes.append(payload)
            return len(payload)

        def read(self, size: int, timeout_ms: int):
            self.reads.append(timeout_ms)
            report = self.writes[-1][1:]
            resp = bytearray(64)
            resp[0] = report[0]
            if report[0] == 0x41:
                resp[2] = 0xAA
            return list(resp)

        def close(self) -> None:
            pass

    fake = FakeHidDevice()
    monkeypatch.setitem(
        sys.modules,
        "hid",
        types.SimpleNamespace(device=lambda: fake),
    )

    stream = bytes(i & 0xFF for i in range(CONTROL_PROG_END_EXCL))
    flash_control(
        vid=0x04D8,
        pid=0xFF89,
        path=b"pb1",
        stream=stream,
        pace_ms=0,
        init_delay_ms=0,
        verify=True,
        dry_run=False,
        verbose=False,
    )

    stream_reports = (CONTROL_PROG_END_EXCL + 29) // 30
    assert len(fake.writes) == stream_reports + 1
    assert len(fake.reads) == stream_reports + 1

    # HFD's first 0x42 packet is not a separate FW_Upd init. It already
    # carries firmware bytes 0..29 at device-report offsets 2..31.
    assert fake.writes[0][1] == 0x42
    assert fake.writes[0][2] == 0x00
    assert fake.writes[0][3 : 3 + 30] == stream[:30]

    assert fake.writes[-1][1] == 0x41
    expected_crc = crc_stream(stream)
    assert fake.writes[-1][5] == (expected_crc >> 8) & 0xFF
    assert fake.writes[-1][6] == expected_crc & 0xFF


def test_flash_control_first_report_times_out_when_ack_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeHidDevice:
        def __init__(self) -> None:
            self.writes: list[bytes] = []
            self.closed = False
            self.nonblocking: bool | None = None

        def open_path(self, path: bytes) -> None:
            assert path == b"pb1"

        def set_nonblocking(self, value: bool) -> None:
            self.nonblocking = value

        def write(self, payload: bytes) -> int:
            self.writes.append(payload)
            return len(payload)

        def read(self, size: int, timeout_ms: int):
            return []

        def close(self) -> None:
            self.closed = True

    fake = FakeHidDevice()
    monkeypatch.setitem(
        sys.modules,
        "hid",
        types.SimpleNamespace(device=lambda: fake),
    )

    with pytest.raises(RuntimeError, match="no response after control stream report 1"):
        flash_control(
            vid=0x04D8,
            pid=0xFF89,
            path=b"pb1",
            stream=bytes([0xFF]) * CONTROL_PROG_END_EXCL,
            pace_ms=0,
            init_delay_ms=0,
            verify=True,
            dry_run=False,
            verbose=False,
            report_timeout_ms=1,
        )

    assert fake.nonblocking is True
    assert fake.closed is True
    assert len(fake.writes) == 1
    assert fake.writes[0][1] == 0x42


def test_flash_control_aborts_when_main_reports_relay_not_armed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeHidDevice:
        def __init__(self) -> None:
            self.writes: list[bytes] = []
            self.closed = False

        def open_path(self, path: bytes) -> None:
            assert path == b"pb1"

        def set_nonblocking(self, value: bool) -> None:
            assert value is True

        def write(self, payload: bytes) -> int:
            self.writes.append(payload)
            return len(payload)

        def read(self, size: int, timeout_ms: int):
            resp = bytearray(64)
            resp[0] = 0x42
            resp[1] = 0x12
            return list(resp)

        def close(self) -> None:
            self.closed = True

    fake = FakeHidDevice()
    monkeypatch.setitem(
        sys.modules,
        "hid",
        types.SimpleNamespace(device=lambda: fake),
    )

    with pytest.raises(ControlRelayNotArmedError, match="UP\\+DOWN"):
        flash_control(
            vid=0x04D8,
            pid=0xFF89,
            path=b"pb1",
            stream=bytes([0xFF]) * CONTROL_PROG_END_EXCL,
            pace_ms=0,
            init_delay_ms=0,
            verify=True,
            dry_run=False,
            verbose=False,
        )

    assert fake.closed is True
    assert len(fake.writes) == 1
    assert fake.writes[0][1] == 0x42


def test_cli_reports_relay_not_armed_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeHidDevice:
        def open_path(self, path: bytes) -> None:
            assert path == b"pb1"

        def set_nonblocking(self, value: bool) -> None:
            assert value is True

        def write(self, payload: bytes) -> int:
            return len(payload)

        def read(self, size: int, timeout_ms: int):
            resp = bytearray(64)
            resp[0] = 0x42
            resp[1] = 0x12
            return list(resp)

        def close(self) -> None:
            pass

    monkeypatch.setitem(
        sys.modules,
        "hid",
        types.SimpleNamespace(device=lambda: FakeHidDevice()),
    )

    rc = main(
        [
            "--hex",
            str(V173_CONTROL_HEX),
            "--path",
            "pb1",
            "--report-timeout-ms",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "MAIN returned cmd 0x42 status 0x12" in captured.err
    assert "UP+DOWN" in captured.err
    assert "Traceback" not in captured.err


def test_source_assembled_v35_unarmed_relay_rejects_first_42_report(tmp_path: Path) -> None:
    main_hex = _assemble_temp_v35(tmp_path, V35_MAIN_ASM.read_text(encoding="utf-8"))
    stream = build_control_stream(parse_intel_hex(str(V173_CONTROL_HEX)))
    chain = _connected_single_main_chain(V173_CONTROL_HEX, main_hex)

    resp, dispatch_hits, _ticks = chain.firmware_hid_report_full_chain(
        0,
        _first_control_stream_report(stream),
        max_ticks=_RELAY_HANDSHAKE_MAX_TICKS,
    )

    assert dispatch_hits >= 1
    assert resp[:4] == bytes([0x42, 0x12, 0x00, 0x00])
    assert chain.read_main_reg(0, 0x0CB) == 0x00
    assert chain.read_main_reg(0, 0x07C) == 0x00
    assert chain.read_main_reg(0, 0x07D) == 0x00


def test_canonical_v35_unarmed_relay_rejects_first_42_report_after_release_build() -> None:
    stream = build_control_stream(parse_intel_hex(str(V173_CONTROL_HEX)))
    chain = _connected_chain(V173_CONTROL_HEX, V35_MAIN_HEX)

    resp, dispatch_hits, _ticks = chain.firmware_hid_report_full_chain(
        0,
        _first_control_stream_report(stream),
        max_ticks=_RELAY_HANDSHAKE_MAX_TICKS,
    )

    assert dispatch_hits >= 1
    assert resp[:4] == bytes([0x42, 0x12, 0x00, 0x00])


def test_old_relay_false_ack_behavior_reproduces_with_temp_mutation(tmp_path: Path) -> None:
    fixed_text = V35_MAIN_ASM.read_text(encoding="utf-8")
    assert "bz          fw_update_init_sequence__reject_unarmed_relay" in fixed_text
    old_text = fixed_text.replace(
        "bz          fw_update_init_sequence__reject_unarmed_relay",
        "bz          hid_command_dispatch__emit_opcode_status",
        1,
    )
    old_hex = _assemble_temp_v35(tmp_path, old_text, stem="dlcp_main_v35_old_relay")
    stream = build_control_stream(parse_intel_hex(str(V173_CONTROL_HEX)))
    chain = _connected_chain(V173_CONTROL_HEX, old_hex)

    resp, dispatch_hits, _ticks = chain.firmware_hid_report_full_chain(
        0,
        _first_control_stream_report(stream),
        max_ticks=_RELAY_HANDSHAKE_MAX_TICKS,
    )

    assert dispatch_hits >= 1
    assert resp[:4] == bytes([0x42, 0x00, 0x00, 0x00])
    assert chain.read_main_reg(0, 0x0CB) == 0x00

    verify = _mk_report(0x41)
    expected_crc = crc_stream(stream)
    verify[4] = (expected_crc >> 8) & 0xFF
    verify[5] = expected_crc & 0xFF
    resp, dispatch_hits, _ticks = chain.firmware_hid_report_full_chain(
        0,
        bytes(verify),
        max_ticks=_RELAY_HANDSHAKE_MAX_TICKS,
    )

    assert dispatch_hits >= 1
    assert resp[:4] == bytes([0x41, 0x11, 0x00, 0x00])


@pytest.mark.slow
def test_full_chain_fixed_main_flashes_control_v173_through_real_bootloader(
    tmp_path: Path,
) -> None:
    main_hex = _assemble_temp_v35(tmp_path, V35_MAIN_ASM.read_text(encoding="utf-8"))
    stream = build_control_stream(parse_intel_hex(str(V173_CONTROL_HEX)))
    chain = _connected_single_main_chain(V173_CONTROL_HEX, main_hex)

    resp, total_ticks = _flash_stream_through_main_relay(
        chain,
        stream,
        control_bootloader_reset_after_ticks=200_000,
    )

    assert resp[:4] == bytes([0x41, 0x00, 0xAA, 0x00])
    readback = chain.read_core_flash(0, 0x0000, CONTROL_PROG_END_EXCL)
    assert readback[0x0040:] == stream[0x0040:]
    assert _assert_flash_release_metadata(readback, stream)[:3] == (0x01, 0x07, 0x33)
    tx = bytes(byte for _tick, src, dst, byte in chain.uart_tx_records_full() if src == 0 and dst == 1)
    assert b"FW_Upd" in tx
    assert total_ticks > 0


@pytest.mark.slow
def test_full_chain_fixed_main_flashes_newer_v173_through_real_bootloader(
    tmp_path: Path,
) -> None:
    main_hex = _assemble_temp_v35(tmp_path / "main", V35_MAIN_ASM.read_text(encoding="utf-8"))
    control_dir = tmp_path / "control"
    control_dir.mkdir()
    shutil.copy2(V173_CONTROL_ASM.parent / "dlcp_control_ram.inc", control_dir / "dlcp_control_ram.inc")
    temp_control_asm = control_dir / V173_CONTROL_ASM.name
    temp_control_asm.write_text(V173_CONTROL_ASM.read_text(encoding="utf-8"), encoding="utf-8")
    newer_control_hex = control_dir / "DLCP_Control_V1.73_newer.hex"
    _old_rev, new_rev, _built_hex = build_v173_release(
        asm_path=temp_control_asm,
        output_hex=newer_control_hex,
        build_date="20260701",
    )
    stream = build_control_stream(parse_intel_hex(str(newer_control_hex)))
    chain = _connected_chain(V173_CONTROL_HEX, main_hex)

    resp, total_ticks = _flash_stream_through_main_relay(
        chain,
        stream,
        control_bootloader_reset_after_ticks=200_000,
    )

    assert resp[:4] == bytes([0x41, 0x00, 0xAA, 0x00])
    readback = chain.read_core_flash(0, 0x0000, CONTROL_PROG_END_EXCL)
    assert readback[0x0040:] == stream[0x0040:]
    major, minor, sub, revision = _assert_flash_release_metadata(readback, stream)
    assert (major, minor, sub) == (0x01, 0x07, 0x33)
    assert revision == new_rev
    assert readback[CONTROL_RELEASE_METADATA_ADDR + 12 : CONTROL_RELEASE_METADATA_ADDR + 16] == bytes(
        [0x20, 0x26, 0x07, 0x01]
    )
    assert total_ticks > 0


def test_preflight_reports_target_release_and_compare_limitation(capsys) -> None:
    rc = main(["--hex", str(V171_CONTROL_HEX), "--preflight-only"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "target release: V1.71 / rev 0x" in out
    assert " / build " in out
    assert "live CONTROL version/revision probe is unavailable" in out


def test_preflight_reports_v172_target_release(capsys) -> None:
    rc = main(["--hex", str(V172_CONTROL_HEX), "--preflight-only"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "target release: V1.72 / rev 0x" in out
    assert " / build " in out


def test_preflight_reports_v173_target_release(capsys) -> None:
    if not V173_CONTROL_HEX.exists():
        pytest.skip(f"missing: {V173_CONTROL_HEX.name}")
    rc = main(["--hex", str(V173_CONTROL_HEX), "--preflight-only"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "target release: V1.73 / rev 0x" in out
    assert " / build " in out


def test_safe_control_wrapper_defaults_to_v173_release() -> None:
    text = Path("scripts/flash_control_safe.sh").read_text(encoding="utf-8")
    assert 'DEFAULT_HEX="${ROOT_DIR}/firmware/patched/releases/DLCP_Control_V1.73.hex"' in text
    assert 'DEFAULT_HEX="${ROOT_DIR}/firmware/patched/releases/DLCP_Control_V1.72.hex"' not in text
    assert 'DEFAULT_HEX="${ROOT_DIR}/firmware/patched/releases/DLCP_Control_V1.71.hex"' not in text


def test_safe_control_wrapper_auto_picks_single_main_but_requires_path_for_multiple() -> None:
    text = Path("scripts/flash_control_safe.sh").read_text(encoding="utf-8")
    assert "auto-selected only visible MAIN HID path" in text
    assert "live control flash saw" in text
    assert "pass --path with the relay MAIN HID path" in text
    assert 'PREFLIGHT_ONLY} -ne 1 && -z "${HID_PATH}"' in text


def test_safe_control_wrapper_does_not_own_main_ir_profile_restore() -> None:
    text = Path("scripts/flash_control_safe.sh").read_text(encoding="utf-8")
    assert "--profile hypex|rc5" not in text
    assert "persisting MAIN IR profile" not in text


def test_static_control_release_info_includes_build_date() -> None:
    mem = parse_intel_hex(str(V171_CONTROL_HEX))
    info = detect_static_hex_control_release_info(mem)

    assert info is not None
    assert (info.major, info.minor, info.sub) == (0x01, 0x07, 0x31)
    assert info.revision is not None
    assert info.build_date is not None
    assert len(info.build_date) == 8 and info.build_date.isdigit()


def test_safe_wrapper_timeout_guidance_mentions_manual_bootloader_hold() -> None:
    text = Path("scripts/flash_control_safe.sh").read_text(encoding="utf-8")
    assert "live control flash timed out" in text
    assert "power-cycle while holding UP+DOWN for at least 6s" in text
    assert "do not press " in text
    assert "SELECT; retry if the LCD returns to Volume" in text


def test_build_v171_release_rolls_back_source_and_hex_on_assemble_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_control_v171.asm"
    original_text = (
        "control_release_banner_row2:\n"
        "        db      0x52, 0x65, 0x76, 0x20, 0x78, 0x30, 0x32, 0x20, 0x32, 0x30, 0x32, 0x36, 0x30, 0x35, 0x32, 0x31, 0x00 ; \"Rev x02 20260521\"\n"
        "control_release_metadata:\n"
        "        db      0x01, 0x07, 0x31, 0x02\n"
        "        db      0x20, 0x26, 0x05, 0x21                    ; build date 20260521 (BCD YYYYMMDD)\n"
    )
    asm_path.write_text(original_text, encoding="utf-8")
    output_hex = tmp_path / "DLCP_Control_V1.71.hex"
    output_hex.write_text(":00000001FF\n", encoding="ascii")

    def _boom(*args, **kwargs):
        raise RuntimeError("gpasm boom")

    monkeypatch.setattr("dlcp_fw.patch.build_v171_release.assemble_v17", _boom)

    with pytest.raises(RuntimeError, match="gpasm boom"):
        build_v171_release(asm_path=asm_path, output_hex=output_hex)

    assert asm_path.read_text(encoding="utf-8") == original_text
    assert output_hex.read_text(encoding="ascii") == ":00000001FF\n"


def test_build_v171_release_updates_revision_date_and_banner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asm_path = tmp_path / "dlcp_control_v171.asm"
    asm_path.write_text(
        "control_release_banner_row2:\n"
        "        db      0x52, 0x65, 0x76, 0x20, 0x78, 0x30, 0x32, 0x20, 0x32, 0x30, 0x32, 0x36, 0x30, 0x35, 0x32, 0x31, 0x00 ; \"Rev x02 20260521\"\n"
        "control_release_metadata:\n"
        "        db      0x01, 0x07, 0x31, 0x02\n"
        "        db      0x20, 0x26, 0x05, 0x21                    ; build date 20260521 (BCD YYYYMMDD)\n",
        encoding="utf-8",
    )
    output_hex = tmp_path / "DLCP_Control_V1.71.hex"

    def _fake_assemble(_asm_path: Path, hex_out: Path, **_kwargs) -> None:
        hex_out.write_text(":00000001FF\n", encoding="ascii")

    monkeypatch.setattr("dlcp_fw.patch.build_v171_release.assemble_v17", _fake_assemble)

    old_rev, new_rev, built_hex = build_v171_release(
        asm_path=asm_path,
        output_hex=output_hex,
        build_date="20260523",
    )

    text = asm_path.read_text(encoding="utf-8")
    assert (old_rev, new_rev, built_hex) == (0x02, 0x03, output_hex)
    assert "db      0x01, 0x07, 0x31, 0x03" in text
    assert "db      0x20, 0x26, 0x05, 0x23" in text
    assert '"Rev x03 20260523"' in text
    assert (
        "0x52, 0x65, 0x76, 0x20, 0x78, 0x30, 0x33, 0x20, "
        "0x32, 0x30, 0x32, 0x36, 0x30, 0x35, 0x32, 0x33, 0x00"
    ) in text
    assert output_hex.read_text(encoding="ascii") == ":00000001FF\n"


def test_bump_v171_release_revision_keeps_banner_and_date_in_sync(tmp_path: Path) -> None:
    asm_path = tmp_path / "dlcp_control_v171.asm"
    asm_path.write_text(
        "control_release_banner_row2:\n"
        "        db      0x52, 0x65, 0x76, 0x20, 0x78, 0x30, 0x32, 0x20, 0x32, 0x30, 0x32, 0x36, 0x30, 0x35, 0x32, 0x31, 0x00 ; \"Rev x02 20260521\"\n"
        "control_release_metadata:\n"
        "        db      0x01, 0x07, 0x31, 0x02\n"
        "        db      0x20, 0x26, 0x05, 0x21                    ; build date 20260521 (BCD YYYYMMDD)\n",
        encoding="utf-8",
    )

    old_rev, new_rev = bump_v171_release_revision(
        asm_path=asm_path,
        build_date="20260523",
    )

    text = asm_path.read_text(encoding="utf-8")
    assert (old_rev, new_rev) == (0x02, 0x03)
    assert "db      0x01, 0x07, 0x31, 0x03" in text
    assert "db      0x20, 0x26, 0x05, 0x23" in text
    assert '"Rev x03 20260523"' in text


def test_pick_device_rejects_ambiguous_auto_select(monkeypatch) -> None:
    dev_a = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"path-a",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="A",
    )
    dev_b = HidDeviceInfo(
        vendor_id=0x04D8,
        product_id=0xFF89,
        path=b"path-b",
        manufacturer_string="Hypex",
        product_string="DLCP",
        serial_number="B",
    )
    monkeypatch.setattr("dlcp_fw.flash.dlcp_control_flash.enumerate_devices", lambda vid, pid: [dev_a, dev_b])

    with pytest.raises(RuntimeError, match="multiple HID devices match"):
        _pick_device(0x04D8, 0xFF89, None)

    assert _pick_device(0x04D8, 0xFF89, b"path-b") == dev_b
