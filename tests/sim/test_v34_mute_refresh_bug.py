"""V3.4 MAIN mute must survive automated route/input volume refreshes."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V173_CONTROL_HEX, V34_MAIN_ASM
from dlcp_fw.sim.v30_symbols import assemble_v30


ACTIVE_FLAGS = 0x05E
EVENT_FLAGS = 0x07E
LOGICAL_VOLUME = 0x066
USER_MUTE_LATCH = 0x094
INPUT_SELECT = 0x099
ROUTE_SHADOW = 0x0AB
INPUT_SELECT_MIRROR = 0x0B3
SCAN_CANDIDATE_INDEX = 0x0B6
SCAN_MISS_DEBOUNCE = 0x0BA
I2C_SLOW_COUNTER = 0x0BB
SRC_NON_PCM_SHADOW = 0x0BF
PRESET_JOB_STATE = 0x2DE
DIAG_D = 0x2E4
DIAG_R = 0x2E9
CONTROL_FULL_SYNC_STEP = 0x170
CONTROL_FULL_SYNC_LO = 0x09F
CONTROL_FULL_SYNC_HI = 0x0A0

ACTIVE_GATE_MASK = 0x08
ACTIVE_MUTE_MASK = 0x10
ACTIVE_MUTE_SHADOW_MASK = 0x20
USER_MUTE_LATCH_MASK = 0x20

SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
TAS_REG_VOLUME_COEFF = 0x30

BOOT_TCY = 16_000_000
COMMAND_SETTLE_TICKS = 12_000_000
INPUT_REFRESH_SETTLE_TICKS = 24_000_000
STANDBY_SETTLE_TICKS = 10_000_000
ONE_SECOND_TICKS = 4_000_000

IR_ADDR_HYPEX = 0x10
IR_CMD_HYPEX_MUTE = 0x35


try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    RustChain = None  # type: ignore[assignment]
    _RUST_CHAIN_IMPORT_ERROR = exc


def _require_rust() -> None:
    if RustChain is None:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


@pytest.fixture(scope="module")
def v34_mute_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v34_mute_refresh_bug")
    hex_out = tmp / "DLCP_Firmware_V3.4_mute_refresh.hex"
    lst_out = tmp / "DLCP_Firmware_V3.4_mute_refresh.lst"
    assemble_v30(V34_MAIN_ASM, hex_out, output_lst=lst_out)
    return hex_out


def _inject_frame(chain, cmd: int, data: int, *, unit: int = 0) -> None:  # type: ignore[no-untyped-def]
    if unit == 0:
        delivered, overruns = chain.inject_main_frames_fifo([[0xB0, cmd, data]], fifo_limit=47)
    else:
        delivered, overruns = chain.inject_main1_frames_fifo([[0xB0, cmd, data]], fifo_limit=47)
    assert delivered == 3 and overruns == 0


def _boot_v34_main(v34_mute_hex: Path):  # type: ignore[no-untyped-def]
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(v34_mute_hex))
    chain.step_tcy(BOOT_TCY)
    assert chain.read_main_reg(0, ACTIVE_FLAGS) & ACTIVE_GATE_MASK, (
        "MAIN did not reach active app state"
    )
    return chain


def _boot_v173_v34_chain(v34_mute_hex: Path):  # type: ignore[no-untyped-def]
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX),
        main_hex_path=str(v34_mute_hex),
    )
    assert chain.run_until_connected(limit=300) < 300
    assert chain.is_connected() and not chain.is_waiting(), chain.lcd_lines()
    return chain


def _volume_payloads(chain, *, unit: int = 0) -> list[bytes]:  # type: ignore[no-untyped-def]
    return chain.read_main_dsp_write_payloads(unit, TAS_REG_VOLUME_COEFF)


def _bad_unmuted_payloads(chain, *, unit: int = 0) -> list[bytes]:  # type: ignore[no-untyped-def]
    return [payload for payload in _volume_payloads(chain, unit=unit) if payload != b"\x00" * 4]


def _latest_volume_payload(chain, *, unit: int = 0) -> bytes | None:  # type: ignore[no-untyped-def]
    payloads = _volume_payloads(chain, unit=unit)
    return payloads[-1] if payloads else None


def _assert_no_unmuted_volume_write(chain, *, unit: int = 0) -> None:  # type: ignore[no-untyped-def]
    bad = _bad_unmuted_payloads(chain, unit=unit)
    assert not bad, (
        f"muted refresh wrote non-zero TAS3108 volume payload(s): "
        f"{[payload.hex() for payload in bad]}"
    )


def _assert_user_mute_flags(chain, *, unit: int = 0) -> None:  # type: ignore[no-untyped-def]
    active = chain.read_main_reg(unit, ACTIVE_FLAGS) & 0xFF
    events = chain.read_main_reg(unit, EVENT_FLAGS) & 0xFF
    latch = chain.read_main_reg(unit, USER_MUTE_LATCH) & 0xFF
    latest = _latest_volume_payload(chain, unit=unit)
    assert active & ACTIVE_MUTE_MASK, (
        f"effective mute bit cleared: active=0x{active:02X}, "
        f"events=0x{events:02X}, latch=0x{latch:02X}, "
        f"dsp30={None if latest is None else latest.hex()}"
    )
    assert active & ACTIVE_MUTE_SHADOW_MASK, (
        f"mute shadow bit cleared: active=0x{active:02X}, "
        f"events=0x{events:02X}, latch=0x{latch:02X}, "
        f"dsp30={None if latest is None else latest.hex()}"
    )
    assert latch & USER_MUTE_LATCH_MASK, (
        f"user mute latch cleared: active=0x{active:02X}, "
        f"events=0x{events:02X}, latch=0x{latch:02X}"
    )


def _assert_user_muted_with_zero_volume_coeff(chain, *, unit: int = 0) -> None:  # type: ignore[no-untyped-def]
    latest = _latest_volume_payload(chain, unit=unit)
    _assert_user_mute_flags(chain, unit=unit)
    assert latest == b"\x00" * 4
    _assert_no_unmuted_volume_write(chain, unit=unit)


def _assert_unmuted_with_nonzero_volume_coeff(chain, *, unit: int = 0) -> None:  # type: ignore[no-untyped-def]
    active = chain.read_main_reg(unit, ACTIVE_FLAGS) & 0xFF
    latch = chain.read_main_reg(unit, USER_MUTE_LATCH) & 0xFF
    latest = _latest_volume_payload(chain, unit=unit)
    assert not (active & ACTIVE_MUTE_MASK), f"mute bit still set: active=0x{active:02X}"
    assert not (active & ACTIVE_MUTE_SHADOW_MASK), (
        f"mute shadow still set: active=0x{active:02X}"
    )
    assert not (latch & USER_MUTE_LATCH_MASK), (
        f"user mute latch still set: latch=0x{latch:02X}"
    )
    assert latest is not None and latest != b"\x00" * 4


def _mute_main(chain, *, unit: int = 0) -> None:  # type: ignore[no-untyped-def]
    chain.reset_main_dsp_write_log(unit)
    _inject_frame(chain, 0x03, 0x02, unit=unit)
    chain.step_ticks(COMMAND_SETTLE_TICKS)
    _assert_user_muted_with_zero_volume_coeff(chain, unit=unit)


def _configure_autodetect_source_present(chain, *, unit: int = 0, non_pcm: int = 0) -> None:  # type: ignore[no-untyped-def]
    chain.write_main_reg(unit, INPUT_SELECT, 0x00)
    chain.write_main_reg(unit, INPUT_SELECT_MIRROR, 0x00)
    chain.write_main_reg(unit, SCAN_CANDIDATE_INDEX, 0x00)
    chain.write_main_reg(unit, SCAN_MISS_DEBOUNCE, 0x00)
    chain.write_main_reg(unit, I2C_SLOW_COUNTER, 0x65)
    chain.poke_main_src4382_reg(unit, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(unit, SRC_REG_NON_PCM, non_pcm)


def _send_hid_settings(chain, *, mute: bool, volume_data: int = 0x40, input_select: int = 0) -> bytes:  # type: ignore[no-untyped-def]
    report = bytearray(64)
    report[0] = 0x05
    report[1] = input_select & 0xFF
    computed = (volume_data - 0x60) & 0xFFFFFFFF
    report[5] = (computed >> 24) & 0xFF
    report[6] = (computed >> 16) & 0xFF
    report[7] = (computed >> 8) & 0xFF
    report[8] = computed & 0xFF
    report[9] = 1 if mute else 0
    response, dispatch_hits = chain.firmware_hid_report(0, bytes(report), max_steps=120_000)
    assert dispatch_hits > 0
    chain.step_ticks(COMMAND_SETTLE_TICKS)
    return response


def test_v34_mute_on_writes_zero_volume_coeff(v34_mute_hex: Path) -> None:
    chain = _boot_v34_main(v34_mute_hex)
    _mute_main(chain)


@pytest.mark.parametrize("input_data", [0x00, 0x01, 0x02, 0x05])
def test_v34_user_mute_survives_input_route_refresh(
    v34_mute_hex: Path,
    input_data: int,
) -> None:
    chain = _boot_v34_main(v34_mute_hex)
    _mute_main(chain)

    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x06, input_data)
    chain.step_ticks(INPUT_REFRESH_SETTLE_TICKS)

    _assert_user_muted_with_zero_volume_coeff(chain)


def test_v34_unchanged_full_sync_volume_while_muted_does_not_unmute(
    v34_mute_hex: Path,
) -> None:
    chain = _boot_v34_main(v34_mute_hex)
    _mute_main(chain)

    volume_data = (chain.read_main_reg(0, LOGICAL_VOLUME) + 0x60) & 0xFF
    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x07, volume_data)
    chain.step_ticks(COMMAND_SETTLE_TICKS)

    assert _volume_payloads(chain) == []
    _assert_user_mute_flags(chain)
    _assert_no_unmuted_volume_write(chain)


def test_v34_explicit_user_volume_change_unmutes_for_v173_compatibility(
    v34_mute_hex: Path,
) -> None:
    chain = _boot_v34_main(v34_mute_hex)
    _mute_main(chain)

    current = (chain.read_main_reg(0, LOGICAL_VOLUME) + 0x60) & 0xFF
    changed = (current + 4) & 0x7F
    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x07, changed)
    chain.step_ticks(COMMAND_SETTLE_TICKS)

    _assert_unmuted_with_nonzero_volume_coeff(chain)


def test_v34_explicit_mute_off_unmutes_even_after_refreshes(v34_mute_hex: Path) -> None:
    chain = _boot_v34_main(v34_mute_hex)
    _mute_main(chain)
    _inject_frame(chain, 0x06, 0x00)
    chain.step_ticks(INPUT_REFRESH_SETTLE_TICKS)

    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x03, 0x03)
    chain.step_ticks(COMMAND_SETTLE_TICKS)

    _assert_unmuted_with_nonzero_volume_coeff(chain)


def test_v34_standby_wake_reapply_keeps_user_mute_zeroed(v34_mute_hex: Path) -> None:
    chain = _boot_v34_main(v34_mute_hex)
    _mute_main(chain)

    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x03, 0x00)
    chain.step_ticks(STANDBY_SETTLE_TICKS)
    _inject_frame(chain, 0x03, 0x01)
    chain.step_ticks(INPUT_REFRESH_SETTLE_TICKS)

    _assert_user_mute_flags(chain)
    _assert_no_unmuted_volume_write(chain)


def test_v34_user_mute_survives_src4382_source_present_refresh(
    v34_mute_hex: Path,
) -> None:
    chain = _boot_v34_main(v34_mute_hex)
    _mute_main(chain)
    _configure_autodetect_source_present(chain, non_pcm=0)

    chain.reset_main_dsp_write_log(0)
    chain.step_ticks(ONE_SECOND_TICKS * 2)

    assert chain.read_main_reg(0, ROUTE_SHADOW) != 0xFF
    _assert_user_muted_with_zero_volume_coeff(chain)


def test_v34_src4382_non_pcm_auto_mute_releases_but_user_mute_does_not(
    v34_mute_hex: Path,
) -> None:
    chain = _boot_v34_main(v34_mute_hex)
    _configure_autodetect_source_present(chain, non_pcm=1)
    chain.reset_main_dsp_write_log(0)
    chain.step_ticks(ONE_SECOND_TICKS * 2)

    assert chain.read_main_reg(0, SRC_NON_PCM_SHADOW) != 0
    assert chain.read_main_reg(0, ACTIVE_FLAGS) & ACTIVE_MUTE_MASK
    assert _latest_volume_payload(chain) == b"\x00" * 4

    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0)
    chain.reset_main_dsp_write_log(0)
    chain.step_ticks(ONE_SECOND_TICKS * 2)
    assert not (chain.read_main_reg(0, ACTIVE_FLAGS) & ACTIVE_MUTE_MASK)
    assert _latest_volume_payload(chain) is not None

    _mute_main(chain)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 1)
    chain.step_ticks(ONE_SECOND_TICKS * 2)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0)
    chain.reset_main_dsp_write_log(0)
    chain.step_ticks(ONE_SECOND_TICKS * 2)

    _assert_user_mute_flags(chain)
    _assert_no_unmuted_volume_write(chain)


def test_v34_hid_settings_import_tracks_user_mute_latch(v34_mute_hex: Path) -> None:
    chain = _boot_v34_main(v34_mute_hex)

    chain.reset_main_dsp_write_log(0)
    _send_hid_settings(chain, mute=True, volume_data=0x42, input_select=0x01)
    _assert_user_muted_with_zero_volume_coeff(chain)

    chain.reset_main_dsp_write_log(0)
    _send_hid_settings(chain, mute=False, volume_data=0x43, input_select=0x02)
    _assert_unmuted_with_nonzero_volume_coeff(chain)


@pytest.mark.parametrize("fault_kind", ["address", "data"])
def test_v34_muted_zero_write_uses_volume_retry_contract(
    v34_mute_hex: Path,
    fault_kind: str,
) -> None:
    chain = _boot_v34_main(v34_mute_hex)
    _mute_main(chain)

    before_d = chain.read_main_reg(0, DIAG_D)
    before_r = chain.read_main_reg(0, DIAG_R)
    if fault_kind == "address":
        chain.inject_main_tas3108_address_nack(0, 2)
    else:
        chain.inject_main_tas3108_data_nack(0, 2)
    chain.reset_main_tas3108_stats(0)
    chain.reset_main_dsp_write_log(0)

    _inject_frame(chain, 0x06, 0x00)
    chain.step_ticks(INPUT_REFRESH_SETTLE_TICKS)

    stats = chain.read_main_tas3108_stats(0)
    assert stats[f"{fault_kind}_nacks_consumed"] > 0
    assert chain.read_main_reg(0, DIAG_R) >= before_r
    assert chain.read_main_reg(0, DIAG_D) >= before_d
    _assert_user_muted_with_zero_volume_coeff(chain)


def test_v173_v34_chain_mute_survives_periodic_full_sync_refresh(
    v34_mute_hex: Path,
) -> None:
    chain = _boot_v173_v34_chain(v34_mute_hex)

    for unit in (0, 1):
        chain.reset_main_dsp_write_log(unit)
    chain.mark_ctl_tx_capture_point()
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_HYPEX_MUTE)
    chain.step_ticks(COMMAND_SETTLE_TICKS)
    for unit in (0, 1):
        _assert_user_muted_with_zero_volume_coeff(chain, unit=unit)

    chain.write_reg(CONTROL_FULL_SYNC_STEP, 0x01)
    chain.write_reg(CONTROL_FULL_SYNC_LO, 0x20)
    chain.write_reg(CONTROL_FULL_SYNC_HI, 0x4E)
    for unit in (0, 1):
        chain.reset_main_dsp_write_log(unit)
    chain.mark_ctl_tx_capture_point()
    chain.step_ticks(ONE_SECOND_TICKS)

    frames = [
        tuple(chunk)
        for chunk in zip(*[iter(chain.ctl_tx_record_since_last_capture())] * 3)
    ]
    assert any(frame[0] == 0xB0 and frame[1] == 0x06 for frame in frames), frames
    assert not any(frame == (0xB0, 0x03, 0x03) for frame in frames), frames
    for unit in (0, 1):
        assert chain.read_main_reg(unit, PRESET_JOB_STATE) == 0
        _assert_user_muted_with_zero_volume_coeff(chain, unit=unit)


def test_bug_mute_refresh_has_no_stale_strict_xfail() -> None:
    bug_token = "BUG-MUTE-REFRESH-01"
    xfail_token = ".".join(("pytest", "mark", "xfail"))
    for path in Path("tests").rglob("test_*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        assert bug_token not in text or xfail_token not in text
