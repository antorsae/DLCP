"""V3.2 SRC4382 Auto Detect cadence/liveness regression tests.

These tests keep the route/DSP liveness checks and pin a balanced candidate
shape: receiver select is written once per candidate, status is read after a
bounded settle, source-present monitoring is slow enough to reduce I2C
exposure, and source discovery is not slowed beyond the user-visible budget.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil

import pytest

from dlcp_fw.paths import V171_CONTROL_HEX, V32_MAIN_ASM
from dlcp_fw.sim.v30_symbols import assemble_v30


ACTIVE_FLAGS = 0x05E
EVENT_FLAGS = 0x07E
LOGICAL_VOLUME = 0x066
COMPUTED_VOLUME = 0x06E
SRC_ROUTE_REQUEST = 0x093
SRC_ROUTE_STATUS = 0x05F
INPUT_SELECT = 0x099
ROUTE_SHADOW = 0x0AB
INPUT_SELECT_MIRROR = 0x0B3
SCAN_CANDIDATE_INDEX = 0x0B6
SCAN_MISS_DEBOUNCE = 0x0BA
I2C_SLOW_COUNTER = 0x0BB
NON_PCM_STATUS_SHADOW = 0x0BF
RX_RING_RD = 0x0C6
RX_RING_WR = 0x0C7
DIAG_I = 0x2E5
DIAG_R = 0x2E9
SRC_LOSS_DEBOUNCE = 0x2F3
PRESET_JOB_STATE = 0x2DE
PRESET_JOB_TARGET = 0x2DF
SSPCON1 = 0xFC6

ACTIVE_PRESET_MASK = 0x04
ACTIVE_GATE_MASK = 0x08
ACTIVE_USER_MUTE_MASK = 0x10
ACTIVE_MUTE_SHADOW_MASK = 0x20
PRESET_JOB_IDLE = 0x00

SRC_REG_RX_CONTROL = 0x0D
SRC_REG_TX_CONTROL_2 = 0x08
SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
TAS_REG_VOLUME_COEFF = 0x30

CONTROL_INPUT_INDEX = 0x0B7
CONTROL_INPUT_SELECT_CACHE = 0x0B8
CONTROL_DISPLAY_STATE = 0x0BF
CONTROL_RAW_STATUS_CACHE = 0x0A1
CONTROL_BUTTON_PINS = {
    "RIGHT": ("A", 4),
    "UP": ("C", 0),
}

BOOT_TCY = 16_000_000
ONE_SECOND_TCY = 4_000_000
SHORT_DWELL_TCY = 500_000
WORST_POSITION_DETECT_TCY = 2_000_000
POLL_STEP_TCY = 10_000
COMMAND_SETTLE_TCY = 4_000_000
STANDBY_SETTLE_TCY = 8_000_000
PRESET_SETTLE_TCY = 50_000_000
CHAIN_NO_SOURCE_TICKS = 48_000_000
CHAIN_SOURCE_SETTLE_TICKS = 10_000_000
CHAIN_COMMAND_SETTLE_TICKS = 20_000_000


def _equ_address(text: str, name: str) -> int | None:
    m = re.search(
        rf"^\s*{re.escape(name)}\s+(?:EQU|equ)\s+(0x[0-9A-Fa-f]+)\s*",
        text,
        re.MULTILINE,
    )
    return int(m.group(1), 16) if m else None


@pytest.fixture(scope="module")
def v32_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v32_src4382_autodetect_polling")
    hex_out = tmp / "DLCP_Firmware_V3.2.hex"
    assemble_v30(V32_MAIN_ASM, hex_out)
    return hex_out


def _rust_chain():
    try:
        from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"rust dlcp_sim_native facade not importable -- {exc!r}")
    return RustChain


def _boot_autodetect_main(v32_hex: Path):  # type: ignore[no-untyped-def]
    chain = _rust_chain().from_v3x_main_only(str(v32_hex))
    chain.step_tcy(BOOT_TCY)
    assert chain.read_reg(ACTIVE_FLAGS) & 0x08, "MAIN did not reach active app state"
    chain.write_reg(INPUT_SELECT, 0x00)
    chain.write_reg(INPUT_SELECT_MIRROR, 0x00)
    chain.write_reg(SCAN_CANDIDATE_INDEX, 0x00)
    chain.write_reg(SCAN_MISS_DEBOUNCE, 0x00)
    chain.write_reg(I2C_SLOW_COUNTER, 0x65)
    return chain


def _configure_main_autodetect(chain, unit: int) -> None:  # type: ignore[no-untyped-def]
    chain.write_main_reg(unit, INPUT_SELECT, 0x00)
    chain.write_main_reg(unit, INPUT_SELECT_MIRROR, 0x00)
    chain.write_main_reg(unit, SCAN_CANDIDATE_INDEX, 0x00)
    chain.write_main_reg(unit, SCAN_MISS_DEBOUNCE, 0x00)
    chain.write_main_reg(unit, I2C_SLOW_COUNTER, 0x65)
    chain.poke_main_src4382_reg(unit, SRC_REG_RX_STATUS, 0x00)
    chain.poke_main_src4382_reg(unit, SRC_REG_NON_PCM, 0x00)
    chain.reset_main_src4382_stats(unit)
    chain.reset_main_dsp_write_log(unit)


def _boot_autodetect_dual_chain(v32_hex: Path):  # type: ignore[no-untyped-def]
    chain = _rust_chain().from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(v32_hex),
    )
    chain.run_until_connected(limit=200)
    assert chain.is_connected() and not chain.is_waiting(), chain.lcd_lines()
    for unit in (0, 1):
        _configure_main_autodetect(chain, unit)
    return chain


def _inject_frame(chain, cmd: int, data: int) -> None:  # type: ignore[no-untyped-def]
    delivered, overruns = chain.inject_main_frames_fifo([[0xB0, cmd, data]], fifo_limit=47)
    assert delivered == 3 and overruns == 0


def _assert_rx_ring_drained(chain) -> None:  # type: ignore[no-untyped-def]
    assert chain.read_reg(RX_RING_RD) == chain.read_reg(RX_RING_WR)


def _assert_main_rx_ring_drained(chain, unit: int) -> None:  # type: ignore[no-untyped-def]
    assert chain.read_main_reg(unit, RX_RING_RD) == chain.read_main_reg(unit, RX_RING_WR)


def _tap_control_key(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = CONTROL_BUTTON_PINS[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(5_000_000)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(5_000_000)


def _force_mains_to_autodetect_prior_route(chain, route: int, rx: int, tx: int) -> None:  # type: ignore[no-untyped-def]
    for unit in (0, 1):
        chain.write_main_reg(unit, INPUT_SELECT, 0x00)
        chain.write_main_reg(unit, INPUT_SELECT_MIRROR, 0x00)
        chain.write_main_reg(unit, SRC_ROUTE_REQUEST, route)
        chain.write_main_reg(unit, ROUTE_SHADOW, route)
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_CONTROL, rx)
        chain.poke_main_src4382_reg(unit, SRC_REG_TX_CONTROL_2, tx)
        chain.reset_main_src4382_stats(unit)
        chain.reset_main_dsp_write_log(unit)


def _assert_no_source_cadence_is_reduced(v32_hex: Path) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.reset_main_src4382_stats(0)

    chain.step_tcy(ONE_SECOND_TCY)

    stats = chain.read_main_src4382_stats(0)
    assert stats["bytes_acked"] <= 150, stats


def _assert_source_present_cadence_is_reduced(v32_hex: Path) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.reset_main_src4382_stats(0)

    chain.step_tcy(ONE_SECOND_TCY)

    stats = chain.read_main_src4382_stats(0)
    assert stats["bytes_acked"] <= 160, stats


def _assert_worst_position_source_detects_within_500ms(v32_hex: Path) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.reset_main_src4382_stats(0)
    chain.reset_main_dsp_write_log(0)

    saw_rx4_at: int | None = None
    tas_refreshed_at: int | None = None
    elapsed = 0
    while elapsed < WORST_POSITION_DETECT_TCY:
        chain.step_tcy(POLL_STEP_TCY)
        elapsed += POLL_STEP_TCY
        rx_values = chain.read_main_src4382_write_values(0, SRC_REG_RX_CONTROL)
        if saw_rx4_at is None and 0x0B in rx_values:
            saw_rx4_at = elapsed
            chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
        if (
            saw_rx4_at is not None
            and 0xF0 in chain.read_main_src4382_write_values(0, SRC_REG_TX_CONTROL_2)
            and chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF) is not None
        ):
            tas_refreshed_at = elapsed
            break

    assert saw_rx4_at is not None, "Auto Detect never scanned RX4 / 0x0B"
    assert tas_refreshed_at is not None, (
        "Worst-position source did not converge through SRC route and TAS refresh "
        f"within {WORST_POSITION_DETECT_TCY} TCY"
    )


def test_v32_src4382_loss_debounce_ram_slot_is_reserved_and_safe() -> None:
    asm = V32_MAIN_ASM.read_text(encoding="utf-8")
    ram_inc = (V32_MAIN_ASM.parent / "dlcp_main_ram.inc").read_text(encoding="utf-8")
    combined = asm + "\n" + ram_inc

    addr = _equ_address(asm, "src4382_loss_debounce")
    assert addr == SRC_LOSS_DEBOUNCE == 0x2F3
    assert "0x2F3 reserved by V3.2 SRC4382 Auto Detect source-loss debounce" in ram_inc

    forbidden_ranges = (
        (0x11A, 0x159, "EP1 OUT (HID OUT)"),
        (0x15A, 0x199, "EP1 IN (HID IN)"),
        (0x1ED, 0x1F4, "EP0 SETUP"),
        (0x400, 0x4FF, "USB BDT"),
        (0x2C0, 0x2DD, "preset filename RAM"),
        (0x2DE, 0x2E4, "async preset-job state"),
        (0x2E5, 0x2F0, "Layer 5 diag/reset visible block"),
        (0x2F1, 0x2F2, "main rx-frame gap / MSSP recovery latches"),
    )
    for lo, hi, label in forbidden_ranges:
        assert not (lo <= addr <= hi), (
            f"src4382_loss_debounce=0x{addr:03X} collides with {label} "
            f"(0x{lo:03X}..0x{hi:03X})"
        )

    assert 0x2DE <= addr < 0x300, (
        "SRC4382 source-loss debounce must stay in the wipe-protected BANK 2 "
        "upper window documented in dlcp_main_ram.inc"
    )
    for other in (
        "preset_job_state",
        "preset_job_target",
        "preset_job_index",
        "preset_job_delay",
        "preset_job_flags",
        "preset_job_tbl_lo",
        "preset_job_tbl_hi",
        "diag_i",
        "diag_d",
        "diag_s",
        "diag_b",
        "diag_r",
        "diag_a",
        "diag_p",
        "diag_ra1_prev",
        "diag_reset_por",
        "diag_reset_bor",
        "diag_reset_wdt",
        "diag_reset_sw",
        "main_rx_frame_gap_timeout",
        "i2c_recover_flags",
    ):
        assert _equ_address(combined, other) != addr, (
            f"src4382_loss_debounce aliases existing RAM symbol {other}"
        )


def test_v32_src4382_autodetect_no_source_cadence_is_reduced(
    v32_hex: Path,
) -> None:
    _assert_no_source_cadence_is_reduced(v32_hex)


def test_v32_cadence_guard_rejects_unthrottled_receiver_select_mutation(
    tmp_path: Path,
) -> None:
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    old = (
        "    movlw       0x12                            ; candidate settle countdown\n"
        "    movwf       ram_0x0BA, BANKED\n"
    )
    new = (
        "    movlw       0x01                            ; mutation: near-unthrottled cadence\n"
        "    movwf       ram_0x0BA, BANKED\n"
    )
    assert old in text, "cadence mutation anchor drifted"

    asm_path = tmp_path / "dlcp_main_v32_unthrottled_src4382.asm"
    hex_path = tmp_path / "DLCP_Firmware_V3.2_unthrottled_src4382.hex"
    shutil.copy2(V32_MAIN_ASM.parent / "dlcp_main_ram.inc", tmp_path / "dlcp_main_ram.inc")
    asm_path.write_text(text.replace(old, new, 1), encoding="utf-8")
    assemble_v30(asm_path, hex_path)

    with pytest.raises(AssertionError, match="bytes_acked"):
        _assert_no_source_cadence_is_reduced(hex_path)


def test_v32_src4382_autodetect_source_present_cadence_is_reduced(
    v32_hex: Path,
) -> None:
    _assert_source_present_cadence_is_reduced(v32_hex)


def test_v32_source_present_cadence_guard_rejects_unthrottled_monitor_mutation(
    tmp_path: Path,
) -> None:
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    old = (
        "    movlw       0x28                            ; source-present monitor countdown\n"
        "    movwf       ram_0x0BA, BANKED\n"
    )
    new = (
        "    movlw       0x01                            ; mutation: near-unthrottled source-present monitor\n"
        "    movwf       ram_0x0BA, BANKED\n"
    )
    assert old in text, "source-present cadence mutation anchor drifted"

    asm_path = tmp_path / "dlcp_main_v32_unthrottled_src4382_monitor.asm"
    hex_path = tmp_path / "DLCP_Firmware_V3.2_unthrottled_src4382_monitor.hex"
    shutil.copy2(V32_MAIN_ASM.parent / "dlcp_main_ram.inc", tmp_path / "dlcp_main_ram.inc")
    asm_path.write_text(text.replace(old, new, 1), encoding="utf-8")
    assemble_v30(asm_path, hex_path)

    with pytest.raises(AssertionError, match="bytes_acked"):
        _assert_source_present_cadence_is_reduced(hex_path)


def test_v32_src4382_no_source_scan_does_not_read_non_pcm_status(
    v32_hex: Path,
) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0xA5)
    chain.reset_main_src4382_stats(0)

    chain.step_tcy(ONE_SECOND_TCY)

    stats = chain.read_main_src4382_stats(0)
    assert stats["reads_by_subaddr"][SRC_REG_RX_STATUS] > 0, stats
    assert stats["reads_by_subaddr"][SRC_REG_NON_PCM] == 0, stats
    assert chain.read_reg(SRC_ROUTE_REQUEST) == 0x00
    assert chain.read_reg(ROUTE_SHADOW) == 0x00


def test_v32_src4382_source_present_latches_non_pcm_status(
    v32_hex: Path,
) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0xA5)
    chain.write_reg(NON_PCM_STATUS_SHADOW, 0x00)
    chain.reset_main_src4382_stats(0)

    chain.step_tcy(ONE_SECOND_TCY)

    stats = chain.read_main_src4382_stats(0)
    assert stats["reads_by_subaddr"][SRC_REG_RX_STATUS] > 0, stats
    assert stats["reads_by_subaddr"][SRC_REG_NON_PCM] > 0, stats
    assert chain.read_reg(NON_PCM_STATUS_SHADOW) == 0xA5
    assert chain.read_reg(SRC_ROUTE_REQUEST) in ROUTE_TO_SRC_PAIR
    assert chain.read_reg(ROUTE_SHADOW) == chain.read_reg(SRC_ROUTE_REQUEST)


ROUTE_TO_SRC_PAIR = {
    0x01: (0x09, 0x70),
    0x02: (0x0A, 0xB0),
    0x03: (0x08, 0x30),
    0x04: (0x0B, 0xF0),
}


def _converge_autodetect_source(chain) -> int:  # type: ignore[no-untyped-def]
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.reset_main_src4382_stats(0)
    chain.reset_main_dsp_write_log(0)

    chain.step_tcy(ONE_SECOND_TCY)

    route = chain.read_reg(SRC_ROUTE_REQUEST)
    assert route in ROUTE_TO_SRC_PAIR
    assert chain.read_reg(ROUTE_SHADOW) == route
    assert chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF) is not None
    return route


def test_v32_src4382_single_source_loss_sample_does_not_flap_route(
    v32_hex: Path,
) -> None:
    chain = _boot_autodetect_main(v32_hex)
    route = _converge_autodetect_source(chain)

    chain.reset_main_src4382_stats(0)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)

    elapsed = 0
    while elapsed < ONE_SECOND_TCY:
        chain.step_tcy(POLL_STEP_TCY)
        elapsed += POLL_STEP_TCY
        stats = chain.read_main_src4382_stats(0)
        if stats["reads_by_subaddr"][SRC_REG_RX_STATUS] >= 1:
            break
    else:
        pytest.fail("Auto Detect source-present monitor did not sample 0x13")

    assert chain.read_reg(SRC_LOSS_DEBOUNCE) == 0x01
    assert chain.read_reg(SRC_ROUTE_REQUEST) == route
    assert chain.read_reg(ROUTE_SHADOW) == route

    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.step_tcy(ONE_SECOND_TCY)

    assert chain.read_reg(SRC_LOSS_DEBOUNCE) == 0x00
    assert chain.read_reg(SRC_ROUTE_REQUEST) == route
    assert chain.read_reg(ROUTE_SHADOW) == route


def test_v32_src4382_sustained_source_loss_resumes_scan_within_1s(
    v32_hex: Path,
) -> None:
    chain = _boot_autodetect_main(v32_hex)
    route = _converge_autodetect_source(chain)

    chain.reset_main_src4382_stats(0)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)

    cleared_at: int | None = None
    elapsed = 0
    while elapsed < ONE_SECOND_TCY:
        chain.step_tcy(POLL_STEP_TCY)
        elapsed += POLL_STEP_TCY
        if chain.read_reg(ROUTE_SHADOW) == 0x00:
            cleared_at = elapsed
            break

    assert cleared_at is not None, (
        f"Auto Detect route 0x{route:02X} did not clear after sustained source loss"
    )
    stats = chain.read_main_src4382_stats(0)
    assert stats["reads_by_subaddr"][SRC_REG_RX_STATUS] >= 2, stats
    assert chain.read_reg(SRC_LOSS_DEBOUNCE) == 0x00
    assert chain.read_reg(SRC_ROUTE_REQUEST) == 0x00
    assert chain.read_reg(ROUTE_SHADOW) == 0x00


def test_v32_src4382_status_read_timeout_does_not_clear_good_route(
    v32_hex: Path,
) -> None:
    """An MSSP timeout while reading SRC4382 reg 0x13 is transport loss,
    not proof that the selected audio source disappeared.

    Pre-fix, `i2c_secondary_dev_random_read` returned W=0 on timeout and
    Auto Detect treated two such samples as sustained source loss, clearing
    a good route.  Fixed firmware preserves the last route and counts I/R.
    """
    chain = _boot_autodetect_main(v32_hex)
    route = _converge_autodetect_source(chain)
    before_i = chain.read_reg(DIAG_I)
    before_r = chain.read_reg(DIAG_R)

    chain.set_mssp_start_fault(cycles=5_000_000, count=4)
    chain.step_tcy(2 * ONE_SECOND_TCY)

    assert chain.read_reg(DIAG_I) > before_i, "timeout did not increment diag_i"
    assert chain.read_reg(DIAG_R) > before_r, "timeout recovery did not increment diag_r"
    assert chain.read_reg(SRC_ROUTE_REQUEST) == route
    assert chain.read_reg(ROUTE_SHADOW) == route
    assert chain.read_reg(SRC_LOSS_DEBOUNCE) == 0x00


def test_v32_i2c_byte_tx_wcol_enters_recovery_and_clears_latch(
    v32_hex: Path,
) -> None:
    """A write collision must use the same visible recovery path as a
    bounded MSSP timeout.

    Pre-fix, `i2c_byte_tx` branched directly to return when SSPCON1.WCOL was
    set.  That left WCOL latched forever, every later write returned early,
    and no diagnostic counter recorded the fault.
    """
    chain = _boot_autodetect_main(v32_hex)
    before_i = chain.read_reg(DIAG_I)
    before_r = chain.read_reg(DIAG_R)
    chain.write_reg(SSPCON1, chain.read_reg(SSPCON1) | 0x80)

    _inject_frame(chain, 0x07, 0x40)
    chain.step_tcy(COMMAND_SETTLE_TCY)

    assert not (chain.read_reg(SSPCON1) & 0x80), "SSPCON1.WCOL stayed latched"
    assert chain.read_reg(DIAG_I) > before_i, "WCOL did not increment diag_i"
    assert chain.read_reg(DIAG_R) > before_r, "WCOL did not enter recovery"
    assert chain.read_reg(LOGICAL_VOLUME) == 0xE0


def test_v32_mssp_hard_reset_clears_bclif_source_flag() -> None:
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    start = text.index("mssp_hard_reset:")
    end = text.index("; ---------------------------------------------------------------------------", start + 1)
    body = text[start:end]
    assert re.search(r"bcf\s+PIR2,\s*3,\s*ACCESS", body), (
        "mssp_hard_reset should clear PIR2.BCLIF so a bus-collision latch "
        "does not survive transport recovery"
    )


def test_v32_src4382_writes_0d_only_when_candidate_changes(v32_hex: Path) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.reset_main_src4382_stats(0)

    chain.step_tcy(ONE_SECOND_TCY)

    stats = chain.read_main_src4382_stats(0)
    values = chain.read_main_src4382_write_values(0, SRC_REG_RX_CONTROL)
    assert stats["writes_by_subaddr"][SRC_REG_RX_CONTROL] <= 16, stats
    assert values[:4] == [0x08, 0x09, 0x0A, 0x0B], values
    assert all(left != right for left, right in zip(values, values[1:])), values


def test_v32_src4382_full_scan_detects_worst_position_source_within_500ms(
    v32_hex: Path,
) -> None:
    _assert_worst_position_source_detects_within_500ms(v32_hex)


def test_v32_discovery_guard_rejects_overly_slow_candidate_settle_mutation(
    tmp_path: Path,
) -> None:
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    old = (
        "    movlw       0x12                            ; candidate settle countdown\n"
        "    movwf       ram_0x0BA, BANKED\n"
    )
    new = (
        "    movlw       0x24                            ; mutation: too-slow source discovery\n"
        "    movwf       ram_0x0BA, BANKED\n"
    )
    assert old in text, "discovery mutation anchor drifted"

    asm_path = tmp_path / "dlcp_main_v32_too_slow_src4382_scan.asm"
    hex_path = tmp_path / "DLCP_Firmware_V3.2_too_slow_src4382_scan.hex"
    shutil.copy2(V32_MAIN_ASM.parent / "dlcp_main_ram.inc", tmp_path / "dlcp_main_ram.inc")
    asm_path.write_text(text.replace(old, new, 1), encoding="utf-8")
    assemble_v30(asm_path, hex_path)

    with pytest.raises(AssertionError, match="Auto Detect never scanned|within"):
        _assert_worst_position_source_detects_within_500ms(hex_path)


def test_v32_src4382_explicit_input_preempts_autodetect_and_converges_route(
    v32_hex: Path,
) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.step_tcy(SHORT_DWELL_TCY)
    chain.reset_main_src4382_stats(0)
    chain.reset_main_dsp_write_log(0)

    _inject_frame(chain, 0x06, 0x05)
    chain.step_tcy(COMMAND_SETTLE_TCY)

    assert chain.read_reg(INPUT_SELECT) == 0x05
    assert chain.read_reg(INPUT_SELECT_MIRROR) == 0x05
    assert chain.read_reg(SCAN_CANDIDATE_INDEX) == 0x00
    assert chain.read_reg(SRC_ROUTE_REQUEST) == 0x01
    assert chain.read_reg(ROUTE_SHADOW) == 0x01
    assert 0x09 in chain.read_main_src4382_write_values(0, SRC_REG_RX_CONTROL)
    assert 0x70 in chain.read_main_src4382_write_values(0, SRC_REG_TX_CONTROL_2)
    assert chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF) is not None
    _assert_rx_ring_drained(chain)


@pytest.mark.parametrize(
    ("input_select", "route_request"),
    [
        (0x01, 0x00),  # legacy external-mux route 0
        (0x02, 0x05),  # legacy external-mux route 5
        (0x03, 0x06),  # legacy external-mux route 6
        (0x04, 0x07),  # legacy external-mux route 7
    ],
)
def test_v32_src4382_external_mux_input_primes_default_receiver_route(
    v32_hex: Path,
    input_select: int,
    route_request: int,
) -> None:
    chain = _boot_autodetect_main(v32_hex)

    # Model the stock external-mux branches after Auto Detect had been scanning.
    # The 0/5/6/7 route requests drive the external mux pins; they must also
    # restore the SRC4382 receiver/transmitter pair from any Auto Detect scan
    # position so the selected mux input actually reaches the DSP. Displayed
    # front-panel fixed digital inputs are covered by the CONTROL S/PDIF test.
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.write_reg(SRC_ROUTE_STATUS, 0x03)
    chain.write_reg(SRC_ROUTE_REQUEST, 0x00)
    chain.write_reg(ROUTE_SHADOW, 0x00)
    chain.write_reg(I2C_SLOW_COUNTER, 0x65)
    chain.reset_main_src4382_stats(0)
    chain.reset_main_dsp_write_log(0)

    _inject_frame(chain, 0x06, input_select)
    chain.step_tcy(COMMAND_SETTLE_TCY)

    assert chain.read_reg(INPUT_SELECT) == input_select
    assert chain.read_reg(INPUT_SELECT_MIRROR) == input_select
    assert chain.read_reg(SRC_ROUTE_REQUEST) == route_request
    assert chain.read_reg(ROUTE_SHADOW) == route_request
    assert 0x08 in chain.read_main_src4382_write_values(0, SRC_REG_RX_CONTROL)
    assert 0x30 in chain.read_main_src4382_write_values(0, SRC_REG_TX_CONTROL_2)
    assert chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF) is not None
    _assert_rx_ring_drained(chain)


def test_v171_v32_control_spdif_menu_selects_route_after_autodetect(
    v32_hex: Path,
) -> None:
    chain = _boot_autodetect_dual_chain(v32_hex)

    # Front-panel path: Volume -> Preset -> Input, then first UP selects the
    # displayed S/PDIF item. This is the user-observed RCA S/PDIF path; it is
    # not the older direct-injection assumption that UI value 0x01 means S/PDIF.
    _tap_control_key(chain, "RIGHT")
    _tap_control_key(chain, "RIGHT")
    assert chain.lcd_lines() == ("Input:          ", "Auto Detect     ")
    assert chain.read_reg(CONTROL_DISPLAY_STATE) == 0x02
    assert chain.read_reg(CONTROL_RAW_STATUS_CACHE) == 0x03

    # Model the bug report's transition: Auto Detect had already been active
    # and left the SRC parked on another route before the operator selected the
    # fixed S/PDIF menu item.
    _force_mains_to_autodetect_prior_route(chain, route=0x03, rx=0x08, tx=0x30)
    before_frames = len(chain.tx_frames())

    _tap_control_key(chain, "UP")
    chain.step_ticks(CHAIN_COMMAND_SETTLE_TICKS)

    new_frames = chain.tx_frames()[before_frames:]
    assert (0xB0, 0x06, 0x05) in new_frames, new_frames
    assert chain.lcd_lines() == ("Input:          ", "S/PDIF          ")
    assert chain.read_reg(CONTROL_INPUT_INDEX) == 0x01
    assert chain.read_reg(CONTROL_INPUT_SELECT_CACHE) == 0x05

    for unit in (0, 1):
        assert chain.read_main_reg(unit, INPUT_SELECT) == 0x05
        assert chain.read_main_reg(unit, INPUT_SELECT_MIRROR) == 0x05
        assert chain.read_main_reg(unit, SRC_ROUTE_REQUEST) == 0x01
        assert chain.read_main_reg(unit, ROUTE_SHADOW) == 0x01
        assert 0x09 in chain.read_main_src4382_write_values(unit, SRC_REG_RX_CONTROL)
        assert 0x70 in chain.read_main_src4382_write_values(unit, SRC_REG_TX_CONTROL_2)
        assert chain.read_main_dsp_write_payload(unit, TAS_REG_VOLUME_COEFF) is not None
        _assert_main_rx_ring_drained(chain, unit)


def test_v32_src4382_fixed_input_goes_quiet_after_route_converges(
    v32_hex: Path,
) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)

    _inject_frame(chain, 0x06, 0x05)
    chain.step_tcy(COMMAND_SETTLE_TCY)
    assert chain.read_reg(INPUT_SELECT) == 0x05
    assert chain.read_reg(SRC_ROUTE_REQUEST) == 0x01
    assert chain.read_reg(ROUTE_SHADOW) == 0x01

    chain.reset_main_src4382_stats(0)
    chain.step_tcy(ONE_SECOND_TCY)

    stats = chain.read_main_src4382_stats(0)
    assert stats["bytes_acked"] == 0, stats
    assert stats["writes_by_subaddr"][SRC_REG_RX_CONTROL] == 0, stats
    assert stats["reads_by_subaddr"][SRC_REG_RX_STATUS] == 0, stats
    assert stats["reads_by_subaddr"][SRC_REG_NON_PCM] == 0, stats
    assert chain.read_reg(SCAN_CANDIDATE_INDEX) == 0x00
    assert chain.read_reg(SCAN_MISS_DEBOUNCE) == 0x00


def test_v32_src4382_autodetect_mute_unmute_remain_responsive(
    v32_hex: Path,
) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.step_tcy(SHORT_DWELL_TCY)

    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x03, 0x02)
    chain.step_tcy(COMMAND_SETTLE_TCY)

    active = chain.read_reg(ACTIVE_FLAGS)
    assert active & ACTIVE_USER_MUTE_MASK
    assert active & ACTIVE_MUTE_SHADOW_MASK
    assert chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF) == b"\x00\x00\x00\x00"
    _assert_rx_ring_drained(chain)

    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x03, 0x03)
    chain.step_tcy(COMMAND_SETTLE_TCY)

    active = chain.read_reg(ACTIVE_FLAGS)
    assert not (active & ACTIVE_USER_MUTE_MASK)
    assert not (active & ACTIVE_MUTE_SHADOW_MASK)
    assert chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF) is not None
    _assert_rx_ring_drained(chain)


def test_v32_src4382_autodetect_standby_wake_remain_responsive(
    v32_hex: Path,
) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.step_tcy(SHORT_DWELL_TCY)

    _inject_frame(chain, 0x03, 0x00)
    chain.step_tcy(STANDBY_SETTLE_TCY)

    assert not (chain.read_reg(ACTIVE_FLAGS) & ACTIVE_GATE_MASK)
    _assert_rx_ring_drained(chain)

    _inject_frame(chain, 0x03, 0x01)
    chain.step_tcy(COMMAND_SETTLE_TCY)

    assert chain.read_reg(ACTIVE_FLAGS) & ACTIVE_GATE_MASK
    _assert_rx_ring_drained(chain)


def test_v32_src4382_autodetect_preset_change_remains_responsive(
    v32_hex: Path,
) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.step_tcy(SHORT_DWELL_TCY)

    initial_target = (chain.read_reg(ACTIVE_FLAGS) & ACTIVE_PRESET_MASK) >> 2
    target = 1 - initial_target

    _inject_frame(chain, 0x20, target)
    chain.step_tcy(PRESET_SETTLE_TCY)

    active_target = (chain.read_reg(ACTIVE_FLAGS) & ACTIVE_PRESET_MASK) >> 2
    assert active_target == target
    assert chain.read_reg(PRESET_JOB_TARGET) == target
    assert chain.read_reg(PRESET_JOB_STATE) == PRESET_JOB_IDLE
    _assert_rx_ring_drained(chain)


@pytest.mark.parametrize("fault_kind", ("address", "data"))
def test_v32_src4382_nack_does_not_block_volume_command(
    v32_hex: Path,
    fault_kind: str,
) -> None:
    chain = _boot_autodetect_main(v32_hex)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    if fault_kind == "address":
        chain.inject_main_src4382_address_nack(0, 1000)
    else:
        chain.inject_main_src4382_data_nack(0, 1000)
    chain.reset_main_src4382_stats(0)

    _inject_frame(chain, 0x07, 0x40)
    chain.step_tcy(COMMAND_SETTLE_TCY)

    stats = chain.read_main_src4382_stats(0)
    assert stats["bytes_nacked"] > 0
    assert stats["bytes_nacked"] <= 1600
    assert chain.read_reg(DIAG_I) > 0
    assert chain.read_reg(LOGICAL_VOLUME) == 0xE0
    assert chain.read_reg(COMPUTED_VOLUME) == 0xE0
    assert chain.read_reg(RX_RING_RD) == chain.read_reg(RX_RING_WR)


def test_v171_v32_src4382_autodetect_dual_main_chain_soak_stays_responsive(
    v32_hex: Path,
) -> None:
    chain = _boot_autodetect_dual_chain(v32_hex)

    chain.step_ticks(CHAIN_NO_SOURCE_TICKS)

    assert chain.is_connected() and not chain.is_waiting(), chain.lcd_lines()
    for unit in (0, 1):
        stats = chain.read_main_src4382_stats(unit)
        assert stats["bytes_acked"] <= 150, (unit, stats)
        assert chain.read_main_reg(unit, SRC_ROUTE_REQUEST) == 0x00
        assert chain.read_main_reg(unit, ROUTE_SHADOW) == 0x00

    for unit in (0, 1):
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_STATUS, 0x01)
        chain.poke_main_src4382_reg(unit, SRC_REG_NON_PCM, 0x00)
        chain.reset_main_src4382_stats(unit)
        chain.reset_main_dsp_write_log(unit)

    chain.step_ticks(CHAIN_SOURCE_SETTLE_TICKS)

    assert chain.is_connected() and not chain.is_waiting(), chain.lcd_lines()
    for unit in (0, 1):
        route = chain.read_main_reg(unit, SRC_ROUTE_REQUEST)
        assert route in ROUTE_TO_SRC_PAIR, (unit, route)
        assert chain.read_main_reg(unit, ROUTE_SHADOW) == route
        rx_control, tx_control_2 = ROUTE_TO_SRC_PAIR[route]
        assert rx_control in chain.read_main_src4382_write_values(unit, SRC_REG_RX_CONTROL)
        assert tx_control_2 in chain.read_main_src4382_write_values(unit, SRC_REG_TX_CONTROL_2)
        assert chain.read_main_dsp_write_payload(unit, TAS_REG_VOLUME_COEFF) is not None

    for unit in (0, 1):
        chain.reset_main_dsp_write_log(unit)

    _inject_frame(chain, 0x07, 0x40)
    chain.step_ticks(CHAIN_COMMAND_SETTLE_TICKS)

    assert chain.is_connected() and not chain.is_waiting(), chain.lcd_lines()
    for unit in (0, 1):
        assert chain.read_main_reg(unit, LOGICAL_VOLUME) == 0xE0
        assert chain.read_main_reg(unit, COMPUTED_VOLUME) == 0xE0
        assert chain.read_main_dsp_write_payload(unit, TAS_REG_VOLUME_COEFF) is not None
        _assert_main_rx_ring_drained(chain, unit)

    for unit in (0, 1):
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_STATUS, 0x00)
        chain.reset_main_src4382_stats(unit)

    chain.step_ticks(CHAIN_NO_SOURCE_TICKS)

    assert chain.is_connected() and not chain.is_waiting(), chain.lcd_lines()
    for unit in (0, 1):
        stats = chain.read_main_src4382_stats(unit)
        assert stats["bytes_acked"] <= 150, (unit, stats)
