"""LCD refresh-budget regressions for CONTROL V1.73."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V173_CONTROL_ASM, V35_MAIN_HEX
from dlcp_fw.sim.v17_symbols import assemble_v17

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


ONE_SECOND_TICKS = 48_000_000
LCD_REFRESH_SOFT_LIMIT_WRITES_PER_SEC = 20.0
SETTLE_TICKS = ONE_SECOND_TICKS
MEASURE_TICKS = 10 * ONE_SECOND_TICKS
SAMPLE_TICKS = ONE_SECOND_TICKS
BUTTON_HOLD_TICKS = 5_000_000
BUTTON_SETTLE_TICKS = 5_000_000

ROW0_ADDRS = tuple(range(0x00, 0x10))
ROW1_ADDRS = tuple(range(0x40, 0x50))
VISIBLE_ADDRS = ROW0_ADDRS + ROW1_ADDRS

DISPLAY_STATE = 0x0BF
STATE_VOLUME = 0
STATE_PRESET = 1
STATE_INPUT_PB1 = 2
STATE_INPUT_PB2 = 3
STATE_SETUP_SPLIT = 4
STATE_PB1_DIAG_SPLIT = 5
STATE_PB2_DIAG_SPLIT = 6

CONTROL_FLAGS = 0x01F
PRESET_BIT = 6
DSP_FAULT_BIT = 7
FNAME_FLAGS = 0x240
FNAME_ROW_DIRTY = 0x08
FNAME_ROW0_STATUS_SNAP = 0x25B
FNAME_ROW0_NOT_READY = 0x80
FNAME_RENDER_COL = 0x259
FNAME_RENDER_OFF = 0x25A
FNAME_SCROLL_OFF = 0x243

HEALTH_AGE_PB1 = 0x1B0
HEALTH_AGE_PB2 = 0x1B1
HEALTH_SEEN_MASK = 0x1B2
HEALTH_FLAGS = 0x1B3
HEALTH_DISPLAY_DIRTY = 2
HEALTH_STALE_AGE = 0x03
HEALTH_LOST_AGE = 0x0A

INPUT_SPLIT_FLAGS = 0x1BA
INPUT_SPLIT_FLAG_PB2_SEEN = 0
INPUT_SPLIT_FLAG_PB2_LINKED = 2
INPUT_INTENT_PB2 = 0x1BB
INPUT_SELECT_CACHE = 0x0B8
INPUT_OPTION_ROW_CACHE = 0x25F
RAW_STATUS_CACHE = 0x0A1

PRESET_A_EEPROM_BASE = 0x60
PRESET_B_EEPROM_BASE = 0x83
FILENAME_LEN = 0x1E
LONG_PRESET_A = "LX521 V15 L22MG old_NC100"
LONG_PRESET_B = "LX521 V15 R22MG new_NC200"

IR_ADDR_HYPEX = 0x10
IR_CMD_PRESET_A = 0x38
IR_CMD_PRESET_B = 0x39

PINS = {
    "RIGHT": ("A", 4),
    "LEFT": ("C", 5),
    "UP": ("C", 0),
    "DOWN": ("A", 2),
    "SELECT": ("A", 1),
    "STBY": ("A", 3),
}


@dataclass(frozen=True)
class LcdWriteMeasurement:
    label: str
    row0: int
    row1: int
    total: int
    row0_col15: int
    row1_col15: int
    reset_cells: tuple[int, ...]
    start_lcd: tuple[str, str]
    end_lcd: tuple[str, str]
    variants: tuple[tuple[str, str], ...]

    @property
    def total_rate(self) -> float:
        return self.total / (MEASURE_TICKS / ONE_SECOND_TICKS)

    def failure_context(self) -> str:
        return (
            f"{self.label}: total={self.total_rate:.2f}/s "
            f"row0={self.row0 / 10:.2f}/s row1={self.row1 / 10:.2f}/s "
            f"row0_col15={self.row0_col15 / 10:.2f}/s "
            f"row1_col15={self.row1_col15 / 10:.2f}/s "
            f"reset_cells={[hex(addr) for addr in self.reset_cells]} "
            f"start={self.start_lcd!r} end={self.end_lcd!r} "
            f"variants={self.variants!r}"
        )


@pytest.fixture(scope="module")
def v173_lcd_refresh_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v173_lcd_refresh")
    shutil.copy(V17_CONTROL_RAM_INC, tmp / V17_CONTROL_RAM_INC.name)
    asm = tmp / V173_CONTROL_ASM.name
    asm.write_bytes(V173_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v173_lcd_refresh.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _filename_slot(text: str) -> bytes:
    raw = text.encode("ascii")[:FILENAME_LEN]
    return raw + bytes([0xFF]) * (FILENAME_LEN - len(raw))


def _seed_filename_slots(chain) -> None:  # type: ignore[no-untyped-def]
    for unit in (0, 1):
        for offset, value in enumerate(_filename_slot(LONG_PRESET_A)):
            chain.write_main_eeprom_byte(unit, PRESET_A_EEPROM_BASE + offset, value)
        for offset, value in enumerate(_filename_slot(LONG_PRESET_B)):
            chain.write_main_eeprom_byte(unit, PRESET_B_EEPROM_BASE + offset, value)


def _new_chain(control_hex: Path, *, long_names: bool = False):  # type: ignore[no-untyped-def]
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(V35_MAIN_HEX),
    )
    if long_names:
        _seed_filename_slots(chain)
    return chain


def _boot_chain(control_hex: Path, *, long_names: bool = False):  # type: ignore[no-untyped-def]
    chain = _new_chain(control_hex, long_names=long_names)
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()
    return chain


def _press(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = PINS[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(BUTTON_HOLD_TICKS)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(BUTTON_SETTLE_TICKS)


def _wait_for_title(
    chain, title: str, *, attempts: int = 120, ticks: int = 1_000_000
) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    for _ in range(attempts):
        lcd = chain.lcd_lines()
        if lcd[0].startswith(title):
            return lcd
        chain.step_ticks(ticks)
    pytest.fail(f"LCD did not reach title {title!r}; lcd={chain.lcd_lines()!r}")


def _try_wait_for_title(chain, title: str) -> bool:  # type: ignore[no-untyped-def]
    for _ in range(4):
        if chain.lcd_lines()[0].startswith(title):
            return True
        chain.step_ticks(500_000)
    return False


def _navigate_to_title(chain, title: str, *, max_presses: int = 8) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    if _try_wait_for_title(chain, title):
        return
    for _ in range(max_presses):
        _press(chain, "RIGHT")
        if _try_wait_for_title(chain, title):
            return
    pytest.fail(f"could not navigate to {title!r}; lcd={chain.lcd_lines()!r}")


def _latch_pb2(chain) -> None:  # type: ignore[no-untyped-def]
    chain.write_reg(HEALTH_SEEN_MASK, 0x02)
    chain.step_ticks(2_000_000)
    flags = chain.read_reg(INPUT_SPLIT_FLAGS)
    flags |= 1 << INPUT_SPLIT_FLAG_PB2_SEEN
    flags |= 1 << INPUT_SPLIT_FLAG_PB2_LINKED
    chain.write_reg(INPUT_SPLIT_FLAGS, flags)
    chain.write_reg(INPUT_INTENT_PB2, chain.read_reg(INPUT_SELECT_CACHE))


def _wait_for_row1(chain, expected: str) -> None:  # type: ignore[no-untyped-def]
    for _ in range(80):
        if chain.lcd_lines()[1] == expected:
            return
        chain.step_ticks(500_000)
    pytest.fail(f"row1 did not reach {expected!r}; lcd={chain.lcd_lines()!r}")


def _set_field_inputs_pb1_spdif_pb2_aes(chain) -> None:  # type: ignore[no-untyped-def]
    flags = chain.read_reg(INPUT_SPLIT_FLAGS)
    flags |= 1 << INPUT_SPLIT_FLAG_PB2_SEEN
    flags &= ~(1 << INPUT_SPLIT_FLAG_PB2_LINKED)
    chain.write_reg(INPUT_SPLIT_FLAGS, flags)
    chain.write_reg(INPUT_SELECT_CACHE, 0x05)
    chain.write_reg(INPUT_INTENT_PB2, 0x07)
    chain.write_reg(INPUT_OPTION_ROW_CACHE, 0xFF)
    chain.step_ticks(2_000_000)

    _navigate_to_title(chain, "Input PB1")
    _wait_for_row1(chain, "S/PDIF          ")

    _navigate_to_title(chain, "Input PB2")
    _wait_for_row1(chain, "AES             ")


def _visible_counts(chain) -> dict[int, int]:  # type: ignore[no-untyped-def]
    return {addr: chain.lcd_ddram_write_count(addr) for addr in VISIBLE_ADDRS}


def _measure_visible_writes(chain, label: str) -> LcdWriteMeasurement:  # type: ignore[no-untyped-def]
    chain.step_ticks(SETTLE_TICKS)
    start_lcd = chain.lcd_lines()
    start = _visible_counts(chain)
    variants = {start_lcd}
    elapsed = 0
    while elapsed < MEASURE_TICKS:
        step = min(SAMPLE_TICKS, MEASURE_TICKS - elapsed)
        chain.step_ticks(step)
        elapsed += step
        variants.add(chain.lcd_lines())
    end = _visible_counts(chain)
    reset_cells = tuple(addr for addr in VISIBLE_ADDRS if end[addr] < start[addr])
    delta = {
        addr: max(0, end[addr] - start[addr])
        for addr in VISIBLE_ADDRS
    }
    return LcdWriteMeasurement(
        label=label,
        row0=sum(delta[addr] for addr in ROW0_ADDRS),
        row1=sum(delta[addr] for addr in ROW1_ADDRS),
        total=sum(delta.values()),
        row0_col15=delta[0x0F],
        row1_col15=delta[0x4F],
        reset_cells=reset_cells,
        start_lcd=start_lcd,
        end_lcd=chain.lcd_lines(),
        variants=tuple(sorted(variants)),
    )


def _assert_under_budget(measurement: LcdWriteMeasurement) -> None:
    assert not measurement.reset_cells, measurement.failure_context()
    assert measurement.total_rate < LCD_REFRESH_SOFT_LIMIT_WRITES_PER_SEC, (
        measurement.failure_context()
    )


def _enter_bl_timeout_editor(chain) -> None:  # type: ignore[no-untyped-def]
    _navigate_to_title(chain, "Setup")
    _press(chain, "SELECT")
    assert chain.lcd_lines()[0].startswith(("Setup", "BL Timeout")), chain.lcd_lines()


@pytest.mark.slow
def test_v173_lcd_refresh_budget_default_pages(v173_lcd_refresh_hex: Path) -> None:
    chain = _boot_chain(v173_lcd_refresh_hex)
    _latch_pb2(chain)

    pages = [
        ("Volume", "Volume"),
        ("Preset", "Preset"),
        ("Input PB1", "Input PB1"),
        ("Input PB2", "Input PB2"),
        ("Setup", "Setup"),
        ("PB1 Diag", "PB1"),
        ("PB2 Diag", "PB2"),
    ]
    measurements: list[LcdWriteMeasurement] = []
    for label, title in pages:
        _navigate_to_title(chain, title)
        measurements.append(_measure_visible_writes(chain, label))

    _enter_bl_timeout_editor(chain)
    measurements.append(_measure_visible_writes(chain, "BL Timeout editor"))

    failures = [
        m.failure_context()
        for m in measurements
        if m.reset_cells or m.total_rate >= LCD_REFRESH_SOFT_LIMIT_WRITES_PER_SEC
    ]
    assert not failures, "\n".join(failures)


@pytest.mark.slow
def test_v173_lcd_refresh_budget_field_pb1_spdif_pb2_aes(
    v173_lcd_refresh_hex: Path,
) -> None:
    chain = _boot_chain(v173_lcd_refresh_hex)
    _set_field_inputs_pb1_spdif_pb2_aes(chain)

    measurements: list[LcdWriteMeasurement] = []
    for label, title in [
        ("Volume PB1 S/PDIF", "Volume"),
        ("Preset PB1 S/PDIF PB2 AES", "Preset"),
        ("Input PB1 S/PDIF", "Input PB1"),
        ("Input PB2 AES", "Input PB2"),
        ("Setup PB1 S/PDIF PB2 AES", "Setup"),
    ]:
        _navigate_to_title(chain, title)
        measurements.append(_measure_visible_writes(chain, label))
    _enter_bl_timeout_editor(chain)
    measurements.append(_measure_visible_writes(chain, "BL Timeout editor field inputs"))

    failures = [
        m.failure_context()
        for m in measurements
        if m.reset_cells or m.total_rate >= LCD_REFRESH_SOFT_LIMIT_WRITES_PER_SEC
    ]
    assert not failures, "\n".join(failures)


@pytest.mark.slow
def test_v173_preset_long_filename_scroll_budget(v173_lcd_refresh_hex: Path) -> None:
    chain = _boot_chain(v173_lcd_refresh_hex, long_names=True)
    _navigate_to_title(chain, "Preset")
    _wait_for_title(chain, "Preset")
    for _ in range(160):
        if chain.lcd_lines()[1].strip():
            break
        chain.step_ticks(1_000_000)
    assert chain.lcd_lines()[1].strip(), chain.lcd_lines()

    measurement = _measure_visible_writes(chain, "Preset active moving filename scroll")
    _assert_under_budget(measurement)


def test_v173_lcd_refresh_structural_guards() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    preset_service = _label_body(
        text, "v172_preset_filename_service", ["v172_fname_query_service"]
    )
    row0_paint = _label_body(text, "v173_preset_row0_paint", ["v171_preset_screen"])
    health_suffix = _label_body(
        text, "v171_health_patch_suffix", ["v171_health_diag_check_stale"]
    )
    volume_loop = _label_body(
        text, "volume_screen__loop_or_return", ["menu_setup_bl_timeout_entry"]
    )
    setup_loop = _label_body(
        text, "setup_screen__loop_or_return", ["backlight_timeout_load_threshold"]
    )
    diag_entry = _label_body(text, "v171_diag_pb_screen", ["v171_diag_screen"])
    diag_reset_last = _label_body(
        text, "v171_bf2x_check_reset_last", ["v171_health_bf2c_reply"]
    )
    ram_inc = V17_CONTROL_RAM_INC.read_text(encoding="utf-8", errors="replace")

    assert "v173_row0_reassert_div" not in preset_service
    assert "btfss   v173_row0_reassert_div" not in preset_service
    assert "call    v172_preset_status_patch_service" in row0_paint
    assert row0_paint.count("call    v172_preset_status_patch_service") >= 2
    assert "movlw   0x8E" not in row0_paint.split("call    v172_preset_status_patch_service")[0]
    assert "cpfseq  v171_health_suffix_mask_b1" in health_suffix
    assert "v173_volume_value_snapshot" in ram_inc
    assert "v173_volume_input_snapshot" in ram_inc
    assert "v173_volume_status_snapshot" in ram_inc
    assert "call    v173_volume_snapshot_visible_state" in text
    assert "call    v173_volume_visible_state_changed" in volume_loop
    assert "bra     volume_screen__service_loop" in volume_loop
    assert "bra     setup_screen__service_loop" in setup_loop
    assert "v173_diag_active_page" in ram_inc
    assert "cpfseq  v173_diag_active_page_b2" in diag_entry
    assert "bra     v171_diag_loop" in diag_entry
    assert "bsf     v171_diag_flags_b1, V171_DIAG_FLAG_DIRTY" not in diag_reset_last
    assert "V171_DIAG_POLL_RELOAD_HI   equ  0x5A" in ram_inc
    assert "V171_DIAG_POLL_RELOAD_LO   equ  0x00" in ram_inc


def test_v173_preset_suffix_no_blank_lifecycle(v173_lcd_refresh_hex: Path) -> None:
    chain = _boot_chain(v173_lcd_refresh_hex, long_names=True)
    _navigate_to_title(chain, "Preset")

    def assert_coherent(label: str) -> None:
        for _ in range(60):
            lcd0, _lcd1 = chain.lcd_lines()
            if lcd0.startswith("Preset"):
                assert lcd0[15] in {"A", "B", "!"}, (label, chain.lcd_lines())
            chain.step_ticks(100_000)

    assert_coherent("entry")
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_PRESET_B)
    assert_coherent("ir-b")
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_PRESET_A)
    assert_coherent("ir-a")
    _press(chain, "LEFT")
    _navigate_to_title(chain, "Preset")
    assert_coherent("reentry")
    chain.write_reg(
        FNAME_ROW0_STATUS_SNAP,
        chain.read_reg(FNAME_ROW0_STATUS_SNAP) | FNAME_ROW0_NOT_READY,
    )
    assert_coherent("self-heal")
    _press(chain, "STBY")
    for _ in range(60):
        if "ZZZ" in chain.lcd_lines()[0].upper():
            break
        chain.step_ticks(1_000_000)
    _press(chain, "STBY")
    _wait_for_title(chain, "Preset", attempts=240)
    assert_coherent("standby-wake")


def test_v173_preset_host_and_fault_status_updates_without_periodic_repaint(
    v173_lcd_refresh_hex: Path,
) -> None:
    chain = _boot_chain(v173_lcd_refresh_hex)
    _navigate_to_title(chain, "Preset")
    _wait_for_title(chain, "Preset")

    assert chain.inject_host_command(cmd=0x20, data=0x01, route=0xBF)
    _wait_for_preset_suffix(chain, "B")
    assert chain.inject_host_command(cmd=0x20, data=0x00, route=0xBF)
    _wait_for_preset_suffix(chain, "A")

    assert chain.inject_control_rx_bytes(bytes([0xBF, 0x08, 0x40]))
    _wait_for_preset_suffix(chain, "!")
    assert chain.inject_control_rx_bytes(bytes([0xBF, 0x08, 0x00]))
    _wait_for_preset_suffix(chain, "A")


def _wait_for_preset_suffix(chain, suffix: str) -> None:  # type: ignore[no-untyped-def]
    for _ in range(80):
        lcd0 = chain.lcd_lines()[0]
        if lcd0.startswith("Preset") and lcd0[15] == suffix:
            return
        chain.step_ticks(500_000)
    pytest.fail(f"Preset suffix did not reach {suffix!r}; lcd={chain.lcd_lines()!r}")


def test_v173_health_suffix_and_input_pb2_dirty_paths_are_cached(
    v173_lcd_refresh_hex: Path,
) -> None:
    chain = _boot_chain(v173_lcd_refresh_hex)
    _latch_pb2(chain)

    _wait_for_suffix(chain, "    ")
    chain.set_blackout(True)
    chain.write_reg(HEALTH_AGE_PB1, HEALTH_STALE_AGE)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _wait_for_suffix(chain, "  !1")
    chain.write_reg(HEALTH_AGE_PB2, HEALTH_STALE_AGE)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _wait_for_suffix(chain, "!1 2")
    chain.write_reg(HEALTH_AGE_PB1, 0)
    chain.write_reg(HEALTH_AGE_PB2, 0)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _wait_for_suffix(chain, "    ")
    chain.set_blackout(False)
    chain.step_ticks(2_000_000)

    _navigate_to_title(chain, "Input PB2")
    assert chain.lcd_lines()[0] == "Input PB2:      "
    row1_before = {addr: chain.lcd_ddram_write_count(addr) for addr in ROW1_ADDRS}
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    chain.step_ticks(4_000_000)
    row1_after = {addr: chain.lcd_ddram_write_count(addr) for addr in ROW1_ADDRS}
    assert row1_after == row1_before, (
        f"unchanged PB2 title health dirty rewrote row1; lcd={chain.lcd_lines()!r}"
    )

    chain.set_blackout(True)
    chain.write_reg(HEALTH_AGE_PB2, HEALTH_STALE_AGE)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _wait_for_title(chain, "Input PB2 old")
    chain.write_reg(HEALTH_AGE_PB2, HEALTH_LOST_AGE)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _wait_for_title(chain, "Input PB2 lost")
    chain.write_reg(HEALTH_AGE_PB2, 0)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _wait_for_title(chain, "Input PB2:")


def _wait_for_suffix(chain, suffix: str) -> None:  # type: ignore[no-untyped-def]
    _navigate_to_title(chain, "Volume")
    for _ in range(120):
        if chain.lcd_lines()[1][-4:] == suffix:
            return
        chain.step_ticks(500_000)
    pytest.fail(f"suffix did not reach {suffix!r}; lcd={chain.lcd_lines()!r}")


def _label_body(text: str, label: str, next_labels: list[str]) -> str:
    start = text.index(f"{label}:")
    end = len(text)
    for next_label in next_labels:
        marker = f"{next_label}:"
        idx = text.find(marker, start + len(label) + 1)
        if idx != -1:
            end = min(end, idx)
    return text[start:end]
