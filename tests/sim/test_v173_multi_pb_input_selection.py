"""V1.73 runtime multi-PB input selection tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    V17_CONTROL_RAM_INC,
    V173_CONTROL_ASM,
    V173_CONTROL_HEX,
    V35_MAIN_HEX,
)
from dlcp_fw.sim.v17_symbols import assemble_v17

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc

BUTTON_PINS = {
    "RIGHT": ("A", 4),
    "LEFT": ("C", 5),
    "UP": ("C", 0),
    "DOWN": ("A", 2),
}

DISPLAY_STATE = 0x0BF
STATE_VOLUME = 0
STATE_PRESET = 1
STATE_INPUT_PB1 = 2
STATE_INPUT_PB2 = 3
STATE_SETUP_SPLIT = 4
STATE_PB1_DIAG_SPLIT = 5
STATE_PB2_DIAG_SPLIT = 6

MENU_OPTION_MAX = 0x0A4
MENU_OPTION_SELECTED = 0x0A5
INPUT_SELECTED_INDEX = 0x0B7
INPUT_SELECT_CACHE = 0x0B8
RAW_STATUS_CACHE = 0x0A1
INPUT_SPLIT_FLAGS = 0x1BA
INPUT_INTENT_PB2 = 0x1BB
INPUT_SPLIT_FLAG_PB2_SEEN = 0
INPUT_SPLIT_FLAG_SYNC_TARGET = 1
INPUT_SPLIT_FLAG_PB2_LINKED = 2
INPUT_SPLIT_FLAG_PB2_PENDING_CONCRETE = 3
INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY = 4
INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE = 5
INPUT_PENDING_PB2 = 0x1BD

IR_ADDR_HYPEX = 0x10
IR_CMD_INPUT_NEXT = 0x44
IR_CMD_INPUT_PREVIOUS = 0x45
IR_INPUT_NEXT_CODE_ADDR = 0x024
IR_INPUT_PREVIOUS_CODE_ADDR = 0x025

FULL_INPUT_ROWS = [
    ("Auto Detect     ", 0x00),
    ("S/PDIF          ", 0x05),
    ("USB Audio       ", 0x06),
    ("AES             ", 0x07),
    ("Optical         ", 0x08),
    ("Analogue 1      ", 0x01),
    ("Analogue 2      ", 0x02),
    ("Analogue 3      ", 0x03),
    ("Analogue 4      ", 0x04),
]

VALID_RAW_STATUS_DOWN_WRAP = {
    0x00: ("Analogue 1      ", 0x01),
    0x01: ("Analogue 2      ", 0x02),
    0x02: ("Analogue 3      ", 0x03),
    0x03: ("Analogue 4      ", 0x04),
}

HEALTH_SEEN_MASK = 0x1B2
HEALTH_AGE_PB2 = 0x1B1
HEALTH_FLAGS = 0x1B3
HEALTH_DISPLAY_DIRTY = 2
HEALTH_STALE_AGE = 0x03
HEALTH_LOST_AGE = 0x0A

CONTROL_RX_RING_BASE = 0x066
CONTROL_RX_RING_RD = 0x098
CONTROL_RX_RING_WR = 0x099
CONTROL_RX_RING_SIZE = 0x30
BF06_INPUT_GATE = 0x032

FULL_SYNC_LO = 0x09F
FULL_SYNC_HI = 0x0A0
FULL_SYNC_STEP = 0x170

CONTROL_DISPLAY_STATE_EEPROM = 0x00
CONTROL_PB2_INPUT_EEPROM = 0x5F
PB2_EEPROM_LINKED = 0xA0
PB2_EEPROM_CONCRETE_BASE = 0xB0

IDLE_TIMEOUT_LO = 0x09D
IDLE_TIMEOUT_HI = 0x09E

V171_DIAG_PRESENT = 0x197
HEALTH_FLAGS_PENDING = 0
HEALTH_FLAGS_TARGET = 1
HEALTH_POLL_TARGET = 0x1B4
HEALTH_TICK_DIV = 0x1B5
HEALTH_PENDING_TICKS = 0x1B6

CONTROL_FLAGS = 0x01F
DSP_FAULT_BIT = 7
BF08_FAULT_BYTE = 0x0AB

MAIN_SRC_ROUTE_STATUS = 0x05F
MAIN_EVENT_FLAGS = 0x07E
MAIN_INPUT_SELECT = 0x099
MAIN_SRC_ROUTE_REQUEST = 0x093
MAIN_ROUTE_SHADOW = 0x0AB
MAIN_INPUT_SELECT_MIRROR = 0x0B3
MAIN_I2C_SLOW_COUNTER = 0x0BB
MAIN_RX_RING_RD = 0x0C6
MAIN_RX_RING_WR = 0x0C7
MAIN_RX_RING_BASE = 0x0200
MAIN_RX_RING_SIZE = 0xC0

SRC_REG_RX_CONTROL = 0x0D
SRC_REG_TX_CONTROL_2 = 0x08
SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
TAS_REG_VOLUME_COEFF = 0x30

ROUTE_AUTO_NONE = 0x00
ROUTE_OPTICAL = 0x04
ROUTE_AES = 0x03
SRC_PAIR_AUTO_NONE = (0x08, 0x30)
SRC_PAIR_OPTICAL = (0x0B, 0xF0)
SRC_PAIR_AES = (0x08, 0x30)

COMMAND_SETTLE_TICKS = 12_000_000


@pytest.fixture(scope="module")
def v173_multi_pb_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v173_multi_pb_input")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V173_CONTROL_ASM.name
    asm.write_bytes(V173_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v173_multi_pb.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _boot_chain(control_hex: Path):  # type: ignore[no-untyped-def]
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(V35_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()
    return chain


def _inject_control_bf08(chain, payload: int) -> None:  # type: ignore[no-untyped-def]
    assert chain.inject_control_rx_bytes(bytes([0xBF, 0x08, payload & 0xFF]))
    for _ in range(30):
        chain.step()


def _new_chain(control_hex: Path):  # type: ignore[no-untyped-def]
    _require_rust()
    return RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(V35_MAIN_HEX),
    )


def _boot_single_main_chain(control_hex: Path):  # type: ignore[no-untyped-def]
    _require_rust()
    chain = RustChain.from_v17_v3x_chain(
        control_hex_path=str(control_hex),
        v3x_main_hex_path=str(V35_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()
    return chain


def _press(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = BUTTON_PINS[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(5_000_000)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(5_000_000)


def _settle_tcy(chain, chunks: int = 50) -> None:  # type: ignore[no-untyped-def]
    for _ in range(chunks):
        chain.step_tcy(1_000)


def _navigate_right(chain, count: int) -> None:  # type: ignore[no-untyped-def]
    for _ in range(count):
        _press(chain, "RIGHT")


def _cmd06_frames(chain, start: int = 0) -> list[tuple[int, int, int]]:  # type: ignore[no-untyped-def]
    return [frame for frame in chain.tx_frames()[start:] if frame[1] == 0x06]


def _ctl_tx_frames_since_mark(chain) -> list[tuple[int, int, int]]:  # type: ignore[no-untyped-def]
    tx = chain.ctl_tx_record_since_last_capture()
    assert len(tx) % 3 == 0, [f"0x{byte:02X}" for byte in tx]
    return [
        (tx[i], tx[i + 1], tx[i + 2])
        for i in range(0, len(tx), 3)
    ]


def _assert_last_cmd06(
    chain,  # type: ignore[no-untyped-def]
    start: int,
    expected_route: int,
    expected_data: int,
) -> None:
    frames = _cmd06_frames(chain, start)
    assert frames
    assert frames[-1] == (expected_route, 0x06, expected_data)


def _wait_for_lcd(chain, expected_row0: str) -> None:  # type: ignore[no-untyped-def]
    for _ in range(80):
        if chain.lcd_lines()[0] == expected_row0:
            return
        chain.step_ticks(1_000_000)
    pytest.fail(f"LCD row 0 did not reach {expected_row0!r}; got {chain.lcd_lines()!r}")


def _latch_split(chain, *, linked: bool = True) -> None:  # type: ignore[no-untyped-def]
    flags = 1 << INPUT_SPLIT_FLAG_PB2_SEEN
    if linked:
        flags |= 1 << INPUT_SPLIT_FLAG_PB2_LINKED
    chain.write_reg(INPUT_SPLIT_FLAGS, flags)
    chain.write_reg(INPUT_INTENT_PB2, chain.read_reg(INPUT_SELECT_CACHE))


def _enter_pb2_same_as_pb1(chain, raw_status: int) -> None:  # type: ignore[no-untyped-def]
    _latch_split(chain, linked=True)
    chain.write_reg(RAW_STATUS_CACHE, raw_status)
    _navigate_right(chain, 3)
    assert chain.lcd_lines() == ("Input PB2:      ", "Same as PB1     ")


def _inject_control_rx_frame(chain, frame: tuple[int, int, int]) -> None:  # type: ignore[no-untyped-def]
    rd = chain.read_reg(CONTROL_RX_RING_RD) % CONTROL_RX_RING_SIZE
    wr = chain.read_reg(CONTROL_RX_RING_WR) % CONTROL_RX_RING_SIZE
    used = (wr + CONTROL_RX_RING_SIZE - rd) % CONTROL_RX_RING_SIZE
    assert CONTROL_RX_RING_SIZE - 1 - used >= len(frame)
    for byte in frame:
        chain.write_reg(CONTROL_RX_RING_BASE + wr, byte & 0xFF)
        wr = (wr + 1) % CONTROL_RX_RING_SIZE
    chain.write_reg(CONTROL_RX_RING_WR, wr)


def _prepare_mains_for_source_status(chain, source_status: int = 0x03) -> None:  # type: ignore[no-untyped-def]
    for unit in (0, 1):
        chain.write_main_reg(unit, MAIN_SRC_ROUTE_STATUS, source_status)
        chain.write_main_reg(unit, MAIN_SRC_ROUTE_REQUEST, 0x00)
        chain.write_main_reg(unit, MAIN_ROUTE_SHADOW, 0x7F)
        chain.write_main_reg(unit, MAIN_INPUT_SELECT, 0x00)
        chain.write_main_reg(unit, MAIN_INPUT_SELECT_MIRROR, 0x00)
        chain.write_main_reg(unit, MAIN_I2C_SLOW_COUNTER, 0x65)
        chain.write_main_reg(unit, MAIN_EVENT_FLAGS, 0x00)
        chain.write_main_reg(
            unit,
            MAIN_RX_RING_RD,
            chain.read_main_reg(unit, MAIN_RX_RING_WR),
        )
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_CONTROL, 0xEE)
        chain.poke_main_src4382_reg(unit, SRC_REG_TX_CONTROL_2, 0xDD)
        chain.reset_main_src4382_stats(unit)
        chain.reset_main_dsp_write_log(unit)


def _inject_main_chain_frame(chain, unit: int, frame: tuple[int, int, int]) -> None:  # type: ignore[no-untyped-def]
    rd = chain.read_main_reg(unit, MAIN_RX_RING_RD) % MAIN_RX_RING_SIZE
    wr = chain.read_main_reg(unit, MAIN_RX_RING_WR) % MAIN_RX_RING_SIZE
    used = (wr + MAIN_RX_RING_SIZE - rd) % MAIN_RX_RING_SIZE
    assert MAIN_RX_RING_SIZE - 1 - used >= len(frame)
    for byte in frame:
        chain.write_main_reg(unit, MAIN_RX_RING_BASE + wr, byte & 0xFF)
        wr = (wr + 1) % MAIN_RX_RING_SIZE
    chain.write_main_reg(unit, MAIN_RX_RING_WR, wr)


def _wait_for_main_input_route(
    chain,  # type: ignore[no-untyped-def]
    unit: int,
    input_select: int,
    route: int,
    src_pair: tuple[int, int],
) -> None:
    expected = (input_select, input_select, route, route, *src_pair)
    got = None
    for _ in range(40):
        got = (
            chain.read_main_reg(unit, MAIN_INPUT_SELECT),
            chain.read_main_reg(unit, MAIN_INPUT_SELECT_MIRROR),
            chain.read_main_reg(unit, MAIN_SRC_ROUTE_REQUEST),
            chain.read_main_reg(unit, MAIN_ROUTE_SHADOW),
            chain.read_main_src4382_reg(unit, SRC_REG_RX_CONTROL),
            chain.read_main_src4382_reg(unit, SRC_REG_TX_CONTROL_2),
        )
        if got == expected:
            assert chain.read_main_dsp_write_payload(unit, TAS_REG_VOLUME_COEFF) is not None
            return
        chain.step_ticks(500_000)
    pytest.fail(f"MAIN{unit} did not reach {expected!r}; got {got!r}")


def _force_full_sync_input_step(chain) -> list[tuple[int, int, int]]:  # type: ignore[no-untyped-def]
    before = len(chain.tx_frames())
    chain.write_reg(FULL_SYNC_STEP, 0x01)
    chain.write_reg(FULL_SYNC_LO, 0x20)
    chain.write_reg(FULL_SYNC_HI, 0x4E)
    chain.step_ticks(4_000_000)
    return _cmd06_frames(chain, before)


def _latch_split_from_health(chain) -> None:  # type: ignore[no-untyped-def]
    chain.write_reg(HEALTH_SEEN_MASK, 0x02)
    chain.step_ticks(2_000_000)
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)


def _rediscover_pb2_with_raw_status(chain, raw_status: int = 0x03) -> None:  # type: ignore[no-untyped-def]
    flags = chain.read_reg(INPUT_SPLIT_FLAGS)
    flags &= ~(
        (1 << INPUT_SPLIT_FLAG_PB2_SEEN)
        | (1 << INPUT_SPLIT_FLAG_PB2_LINKED)
        | (1 << INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE)
    )
    chain.write_reg(INPUT_SPLIT_FLAGS, flags)
    chain.write_reg(RAW_STATUS_CACHE, raw_status & 0xFF)
    chain.write_reg(HEALTH_SEEN_MASK, 0x02)
    chain.step_ticks(2_000_000)
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)


def _force_settings_save(chain) -> None:  # type: ignore[no-untyped-def]
    chain.write_reg(IDLE_TIMEOUT_LO, 0x60)
    chain.write_reg(IDLE_TIMEOUT_HI, 0xEA)
    chain.step_ticks(120_000_000)


def _control_pb2_eeprom_watch() -> dict[str, object]:
    return {
        "role": "CONTROL",
        "space": "Eeprom",
        "start": CONTROL_PB2_INPUT_EEPROM,
        "end": CONTROL_PB2_INPUT_EEPROM,
        "label": "control_pb2_input_persist",
    }


def _decode_pb2_persisted(byte: int) -> tuple[str, int]:
    byte &= 0xFF
    if byte == PB2_EEPROM_LINKED:
        return ("linked", 0)
    if (byte & 0xF0) == PB2_EEPROM_CONCRETE_BASE and (byte & 0x0F) <= 0x08:
        return ("concrete", byte & 0x0F)
    return ("linked", 0)


@pytest.mark.slow
def test_pb2_discovery_inserts_input_pb2_after_pb1_and_defaults_linked(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    if not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)):
        chain.write_reg(HEALTH_SEEN_MASK, 0x02)
        chain.step_ticks(2_000_000)
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED)

    expected = [
        (STATE_PRESET, "Preset"),
        (STATE_INPUT_PB1, "Input PB1:      "),
        (STATE_INPUT_PB2, "Input PB2:      "),
        (STATE_SETUP_SPLIT, "Setup           "),
        (STATE_PB1_DIAG_SPLIT, "PB1 "),
        (STATE_PB2_DIAG_SPLIT, "PB2 "),
        (STATE_VOLUME, "Volume"),
    ]
    for state, row0_prefix in expected:
        _press(chain, "RIGHT")
        assert chain.read_reg(DISPLAY_STATE) == state
        assert chain.lcd_lines()[0].startswith(row0_prefix), chain.lcd_lines()
        if state == STATE_INPUT_PB2:
            assert chain.lcd_lines()[1] == "Same as PB1     "


@pytest.mark.slow
def test_canonical_hex_split_menu_visible_behavior_regression() -> None:
    chain = _boot_chain(V173_CONTROL_HEX)
    chain.write_reg(HEALTH_SEEN_MASK, 0x02)
    chain.step_ticks(2_000_000)

    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED)

    expected = [
        (STATE_PRESET, "Preset"),
        (STATE_INPUT_PB1, "Input PB1:      "),
        (STATE_INPUT_PB2, "Input PB2:      "),
        (STATE_SETUP_SPLIT, "Setup           "),
        (STATE_PB1_DIAG_SPLIT, "PB1 "),
        (STATE_PB2_DIAG_SPLIT, "PB2 "),
        (STATE_VOLUME, "Volume"),
    ]
    for state, row0_prefix in expected:
        _press(chain, "RIGHT")
        assert chain.read_reg(DISPLAY_STATE) == state
        assert chain.lcd_lines()[0].startswith(row0_prefix), chain.lcd_lines()
        if state == STATE_INPUT_PB2:
            assert chain.lcd_lines()[1] == "Same as PB1     "

    chain.write_reg(INPUT_SPLIT_FLAGS, 1 << INPUT_SPLIT_FLAG_PB2_SEEN)
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)  # PB1 Optical
    chain.write_reg(INPUT_INTENT_PB2, 0x07)    # PB2 AES
    _navigate_right(chain, 2)
    assert chain.lcd_lines() == ("Input PB1:      ", "Optical         ")
    _press(chain, "RIGHT")
    assert chain.lcd_lines() == ("Input PB2:      ", "AES             ")
    _navigate_right(chain, 4)
    assert chain.read_reg(DISPLAY_STATE) == STATE_VOLUME
    assert chain.lcd_lines()[1] == "Optical         "


@pytest.mark.slow
def test_pb2_discovery_can_be_latched_from_diag_present(v173_multi_pb_hex: Path) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN))

    chain.write_reg(V171_DIAG_PRESENT, 0x02)
    chain.step_ticks(2_000_000)

    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("start_state", "expected_state"),
    [(2, 2), (3, 4), (4, 5), (5, 6)],
)
def test_pb2_latch_remaps_existing_menu_state_without_page_jump(
    v173_multi_pb_hex: Path,
    start_state: int,
    expected_state: int,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    chain.write_reg(DISPLAY_STATE, start_state)
    chain.write_reg(INPUT_SPLIT_FLAGS, 0x00)
    chain.write_reg(HEALTH_SEEN_MASK, 0x02)
    chain.step_ticks(2_000_000)

    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)
    assert chain.read_reg(DISPLAY_STATE) == expected_state


@pytest.mark.slow
def test_legacy_pb2_unknown_input_page_stays_broadcast_and_six_state(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_single_main_chain(v173_multi_pb_hex)
    assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN))

    _navigate_right(chain, 2)
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB1
    assert chain.lcd_lines() == ("Input:          ", "Auto Detect     ")
    before = len(chain.tx_frames())
    _press(chain, "UP")
    frames = _cmd06_frames(chain, before)
    assert frames and frames[-1][0] == 0xB0

    _navigate_right(chain, 4)
    assert chain.read_reg(DISPLAY_STATE) == STATE_VOLUME
    assert chain.lcd_lines()[0].startswith("Volume")


@pytest.mark.slow
def test_linked_pb1_input_change_broadcasts_to_all_pbs(v173_multi_pb_hex: Path) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=True)

    _navigate_right(chain, 2)
    assert chain.lcd_lines()[0] == "Input PB1:      "
    before = len(chain.tx_frames())
    _press(chain, "UP")
    frames = _cmd06_frames(chain, before)

    assert frames and frames[-1][0] == 0xB0
    assert not any(frame[0] in (0xB1, 0xB2) for frame in frames)
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED)

    _press(chain, "RIGHT")
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2
    assert chain.lcd_lines() == ("Input PB2:      ", "Same as PB1     ")


@pytest.mark.slow
def test_pb2_same_as_pb1_row_restores_linked_broadcast_mode(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=False)
    chain.write_reg(INPUT_INTENT_PB2, 0x07)

    _navigate_right(chain, 3)
    assert chain.lcd_lines()[0] == "Input PB2:      "
    assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED))
    before = len(chain.tx_frames())
    for _ in range(4):  # AES -> USB -> S/PDIF -> Auto Detect -> Same as PB1
        _press(chain, "DOWN")
    frames = _cmd06_frames(chain, before)

    assert chain.lcd_lines() == ("Input PB2:      ", "Same as PB1     ")
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED)
    assert frames and frames[-1][0] == 0xB0


@pytest.mark.slow
def test_independent_pb1_and_pb2_input_pages_emit_addressed_cmd06(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=True)

    _navigate_right(chain, 3)
    before = len(chain.tx_frames())
    _press(chain, "UP")  # Same as PB1 -> Auto Detect, i.e. independent PB2
    pb2_frames = _cmd06_frames(chain, before)
    assert pb2_frames and pb2_frames[-1] == (0xB2, 0x06, 0x00)
    assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED))

    _press(chain, "LEFT")
    assert chain.lcd_lines()[0] == "Input PB1:      "
    before = len(chain.tx_frames())
    _press(chain, "UP")
    pb1_frames = _cmd06_frames(chain, before)
    assert pb1_frames and pb1_frames[-1][0] == 0xB1
    assert not any(frame[0] == 0xB0 for frame in pb1_frames)


@pytest.mark.slow
def test_front_panel_sets_pb1_optical_and_pb2_aes_with_distinct_src_routes(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=True)
    _prepare_mains_for_source_status(chain)

    _navigate_right(chain, 2)
    assert chain.lcd_lines()[0] == "Input PB1:      "
    for _ in range(4):  # Auto -> S/PDIF -> USB -> AES -> Optical
        _press(chain, "UP")
    assert chain.lcd_lines()[1] == "Optical         "

    _press(chain, "RIGHT")
    assert chain.lcd_lines()[0] == "Input PB2:      "
    for _ in range(4):  # Same -> Auto -> S/PDIF -> USB -> AES
        _press(chain, "UP")
    chain.step_ticks(20_000_000)
    assert chain.lcd_lines()[1] == "AES             "

    _wait_for_main_input_route(chain, 0, 0x08, ROUTE_OPTICAL, SRC_PAIR_OPTICAL)
    _wait_for_main_input_route(chain, 1, 0x07, ROUTE_AES, SRC_PAIR_AES)

    _press(chain, "LEFT")
    assert chain.lcd_lines() == ("Input PB1:      ", "Optical         ")
    _press(chain, "RIGHT")
    assert chain.lcd_lines() == ("Input PB2:      ", "AES             ")


@pytest.mark.slow
def test_pb2_autodetect_is_addressed_and_survives_lifecycle(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=False)
    _prepare_mains_for_source_status(chain)
    chain.poke_main_src4382_reg(1, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(1, SRC_REG_NON_PCM, 0x00)
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)  # PB1 fixed Optical.
    chain.write_reg(INPUT_INTENT_PB2, 0x07)    # Start PB2 on fixed AES.

    pb1_frames = _force_full_sync_input_step(chain)
    assert pb1_frames and pb1_frames[-1] == (0xB1, 0x06, 0x08)
    _wait_for_main_input_route(chain, 0, 0x08, ROUTE_OPTICAL, SRC_PAIR_OPTICAL)
    pb2_frames = _force_full_sync_input_step(chain)
    assert pb2_frames and pb2_frames[-1] == (0xB2, 0x06, 0x07)
    _wait_for_main_input_route(chain, 1, 0x07, ROUTE_AES, SRC_PAIR_AES)

    _navigate_right(chain, 3)
    before = len(chain.tx_frames())
    _press(chain, "DOWN")  # AES -> USB
    _press(chain, "DOWN")  # USB -> S/PDIF
    _press(chain, "DOWN")  # S/PDIF -> Auto Detect
    frames = _cmd06_frames(chain, before)

    assert frames and frames[-1] == (0xB2, 0x06, 0x00)
    assert not any(frame[0] in (0xB0, 0xB1) for frame in frames)
    for _ in range(40):
        if (
            chain.read_main_reg(1, MAIN_INPUT_SELECT) == 0x00
            and chain.read_main_reg(1, MAIN_SRC_ROUTE_REQUEST) == ROUTE_AES
            and chain.read_main_reg(1, MAIN_ROUTE_SHADOW) == ROUTE_AES
        ):
            break
        chain.step_ticks(500_000)
    assert chain.read_main_reg(1, MAIN_INPUT_SELECT) == 0x00
    assert chain.read_main_reg(1, MAIN_INPUT_SELECT_MIRROR) == 0x00
    assert chain.read_main_reg(1, MAIN_SRC_ROUTE_REQUEST) == ROUTE_AES
    assert chain.read_main_reg(1, MAIN_ROUTE_SHADOW) == ROUTE_AES

    _navigate_right(chain, 4)
    assert chain.read_reg(DISPLAY_STATE) == STATE_VOLUME
    assert chain.lcd_lines()[1] == "Optical         "
    _navigate_right(chain, 3)
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2
    assert chain.lcd_lines() == ("Input PB2:      ", "Auto Detect     ")

    assert _force_full_sync_input_step(chain)[-1] == (0xB1, 0x06, 0x08)
    assert _force_full_sync_input_step(chain)[-1] == (0xB2, 0x06, 0x00)
    assert chain.read_main_reg(0, MAIN_INPUT_SELECT) == 0x08
    assert chain.read_main_reg(1, MAIN_INPUT_SELECT) == 0x00
    assert chain.read_main_reg(0, MAIN_SRC_ROUTE_REQUEST) == ROUTE_OPTICAL
    assert chain.read_main_reg(1, MAIN_SRC_ROUTE_REQUEST) == ROUTE_AES

    assert chain.inject_host_command(cmd=0x20, data=0x01, route=0xBF)
    chain.step_ticks(80_000_000)
    assert chain.read_main_reg(0, MAIN_INPUT_SELECT) == 0x08
    assert chain.read_main_reg(1, MAIN_INPUT_SELECT) == 0x00
    assert chain.read_main_reg(0, MAIN_SRC_ROUTE_REQUEST) == ROUTE_OPTICAL
    assert chain.read_main_reg(1, MAIN_SRC_ROUTE_REQUEST) == ROUTE_AES

    chain.press("STBY")
    chain.step_ticks(20_000_000)
    assert "ZZZ" in chain.lcd_lines()[0].upper()
    chain.press("SELECT")
    chain.step_ticks(120_000_000)
    assert chain.lcd_lines() == ("Input PB2:      ", "Auto Detect     ")
    assert chain.read_main_reg(0, MAIN_INPUT_SELECT) == 0x08
    assert chain.read_main_reg(1, MAIN_INPUT_SELECT) == 0x00
    assert chain.read_main_reg(0, MAIN_SRC_ROUTE_REQUEST) == ROUTE_OPTICAL
    assert chain.read_main_reg(1, MAIN_SRC_ROUTE_REQUEST) == ROUTE_AES


@pytest.mark.slow
def test_linked_and_independent_full_sync_use_correct_route_style(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=True)
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)
    chain.write_reg(INPUT_INTENT_PB2, 0x03)
    linked = _force_full_sync_input_step(chain)
    assert linked and linked[-1] == (0xB0, 0x06, 0x08)

    chain.write_reg(INPUT_SPLIT_FLAGS, 1 << INPUT_SPLIT_FLAG_PB2_SEEN)
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)
    chain.write_reg(INPUT_INTENT_PB2, 0x03)
    chain.write_reg(FULL_SYNC_STEP, 0x01)
    independent_first = _force_full_sync_input_step(chain)
    independent_second = _force_full_sync_input_step(chain)

    assert independent_first and independent_first[-1] == (0xB1, 0x06, 0x08)
    assert independent_second and independent_second[-1] == (0xB2, 0x06, 0x03)
    assert not any(frame[0] == 0xB0 for frame in independent_first + independent_second)


@pytest.mark.slow
def test_pb2_full_sync_clamps_corrupt_intent_before_send(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    chain.write_reg(
        INPUT_SPLIT_FLAGS,
        (1 << INPUT_SPLIT_FLAG_PB2_SEEN) | (1 << INPUT_SPLIT_FLAG_SYNC_TARGET),
    )
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)
    chain.write_reg(INPUT_INTENT_PB2, 0xFF)

    frames = _force_full_sync_input_step(chain)

    assert frames and frames[-1] == (0xB2, 0x06, 0x00)
    assert chain.read_reg(INPUT_INTENT_PB2) == 0x00


@pytest.mark.slow
@pytest.mark.parametrize("linked", [True, False])
def test_health_only_pb2_discovery_survives_wake_and_health_loss_route_style(
    v173_multi_pb_hex: Path,
    linked: bool,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split_from_health(chain)
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)
    chain.write_reg(INPUT_INTENT_PB2, 0x03)
    if linked:
        chain.write_reg(
            INPUT_SPLIT_FLAGS,
            (1 << INPUT_SPLIT_FLAG_PB2_SEEN) | (1 << INPUT_SPLIT_FLAG_PB2_LINKED),
        )
        assert _force_full_sync_input_step(chain)[-1] == (0xB0, 0x06, 0x08)
    else:
        chain.write_reg(INPUT_SPLIT_FLAGS, 1 << INPUT_SPLIT_FLAG_PB2_SEEN)
        assert _force_full_sync_input_step(chain)[-1] == (0xB1, 0x06, 0x08)
        assert _force_full_sync_input_step(chain)[-1] == (0xB2, 0x06, 0x03)

    _navigate_right(chain, 3)
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2
    chain.write_reg(HEALTH_SEEN_MASK, 0x00)
    chain.step_ticks(2_000_000)
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2

    chain.press("STBY")
    chain.step_ticks(20_000_000)
    assert "ZZZ" in chain.lcd_lines()[0].upper()
    chain.press("SELECT")
    chain.step_ticks(120_000_000)
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2
    if linked:
        assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED)
        assert _force_full_sync_input_step(chain)[-1] == (0xB0, 0x06, 0x08)
    else:
        assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED))
        assert _force_full_sync_input_step(chain)[-1] == (0xB1, 0x06, 0x08)
        assert _force_full_sync_input_step(chain)[-1] == (0xB2, 0x06, 0x03)


@pytest.mark.slow
def test_bf06_echo_updates_linked_mode_but_is_quarantined_when_independent(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=True)
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)
    chain.write_reg(INPUT_INTENT_PB2, 0x03)
    chain.write_reg(BF06_INPUT_GATE, 0x00)

    _inject_control_rx_frame(chain, (0xBF, 0x06, 0x01))
    chain.step_ticks(2_000_000)
    assert chain.read_reg(INPUT_SELECT_CACHE) == 0x01
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED)
    linked_sync = _force_full_sync_input_step(chain)
    assert linked_sync and linked_sync[-1] == (0xB0, 0x06, 0x01)

    chain.write_reg(INPUT_SPLIT_FLAGS, 1 << INPUT_SPLIT_FLAG_PB2_SEEN)
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)
    chain.write_reg(INPUT_INTENT_PB2, 0x03)
    chain.write_reg(BF06_INPUT_GATE, 0x00)
    _inject_control_rx_frame(chain, (0xBF, 0x06, 0x01))
    chain.step_ticks(2_000_000)

    assert chain.read_reg(INPUT_SELECT_CACHE) == 0x08
    assert chain.read_reg(INPUT_INTENT_PB2) == 0x03
    independent_first = _force_full_sync_input_step(chain)
    independent_second = _force_full_sync_input_step(chain)
    assert independent_first and independent_first[-1] == (0xB1, 0x06, 0x08)
    assert independent_second and independent_second[-1] == (0xB2, 0x06, 0x03)
    assert not any(frame[0] == 0xB0 for frame in independent_first + independent_second)


@pytest.mark.slow
def test_volume_row_always_shows_pb1_input_when_pb2_differs(v173_multi_pb_hex: Path) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=False)
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)  # PB1 Optical
    chain.write_reg(INPUT_INTENT_PB2, 0x07)    # PB2 AES

    _navigate_right(chain, 3)
    assert chain.lcd_lines() == ("Input PB2:      ", "AES             ")
    _navigate_right(chain, 4)

    assert chain.read_reg(DISPLAY_STATE) == STATE_VOLUME
    assert chain.lcd_lines()[0].startswith("Volume")
    assert chain.lcd_lines()[1] == "Optical         "


@pytest.mark.slow
@pytest.mark.parametrize(
    ("raw_status", "base_max"),
    [(0x00, 0x05), (0x01, 0x06), (0x02, 0x07), (0x03, 0x08)],
)
def test_pb2_input_raw_status_variants_keep_extra_same_as_pb1_row(
    v173_multi_pb_hex: Path,
    raw_status: int,
    base_max: int,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=True)
    chain.write_reg(RAW_STATUS_CACHE, raw_status)

    _navigate_right(chain, 3)
    assert chain.lcd_lines() == ("Input PB2:      ", "Same as PB1     ")
    assert chain.read_reg(MENU_OPTION_MAX) == base_max + 1
    assert chain.read_reg(INPUT_SELECTED_INDEX) == 0


@pytest.mark.slow
def test_reconnect_clearing_health_seen_mask_does_not_hide_latched_pb2_page(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain)
    chain.write_reg(HEALTH_SEEN_MASK, 0x00)

    _navigate_right(chain, 3)
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2
    assert chain.lcd_lines()[0] == "Input PB2:      "


@pytest.mark.slow
def test_pb2_input_title_tracks_health_old_and_lost(v173_multi_pb_hex: Path) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain)
    _navigate_right(chain, 3)
    _wait_for_lcd(chain, "Input PB2:      ")

    chain.set_blackout(True)
    chain.write_reg(HEALTH_AGE_PB2, HEALTH_STALE_AGE)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _wait_for_lcd(chain, "Input PB2 old   ")

    chain.write_reg(HEALTH_AGE_PB2, HEALTH_LOST_AGE)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _wait_for_lcd(chain, "Input PB2 lost  ")


@pytest.mark.slow
def test_pb2_input_allows_health_aging_but_not_diagnostics_traffic(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain)
    _navigate_right(chain, 3)
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2

    chain.set_blackout(True)
    chain.write_reg(HEALTH_AGE_PB2, 0x00)
    chain.write_reg(
        HEALTH_FLAGS,
        (1 << HEALTH_FLAGS_PENDING) | (1 << HEALTH_FLAGS_TARGET),
    )
    chain.write_reg(HEALTH_PENDING_TICKS, 0x00)
    chain.write_reg(HEALTH_TICK_DIV, 0xFF)
    chain.step_ticks(8_000_000)
    assert chain.read_reg(HEALTH_AGE_PB2) == 0x01

    chain.set_blackout(False)
    chain.write_reg(HEALTH_FLAGS, 0x00)
    chain.write_reg(HEALTH_POLL_TARGET, 0x01)
    chain.write_reg(HEALTH_TICK_DIV, 0xFF)
    chain.mark_ctl_tx_capture_point()
    chain.step_ticks(8_000_000)
    new_frames = _ctl_tx_frames_since_mark(chain)
    assert any(frame[1] == 0x23 for frame in new_frames), new_frames
    assert not any(frame[1] in (0x21, 0x22) for frame in new_frames), new_frames


@pytest.mark.slow
def test_split_setup_keeps_health_service_and_suffix_but_no_diag_poll(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain)
    _navigate_right(chain, 4)
    assert chain.read_reg(DISPLAY_STATE) == STATE_SETUP_SPLIT
    assert chain.lcd_lines()[0] == "Setup           "

    chain.set_blackout(True)
    chain.write_reg(HEALTH_AGE_PB2, HEALTH_STALE_AGE)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _settle_tcy(chain)
    assert chain.lcd_lines()[1] == "BL Timeout    !2", chain.lcd_lines()

    chain.set_blackout(False)
    chain.write_reg(HEALTH_FLAGS, 0x00)
    chain.write_reg(HEALTH_POLL_TARGET, 0x01)
    chain.write_reg(HEALTH_TICK_DIV, 0xFF)
    chain.mark_ctl_tx_capture_point()
    chain.step_ticks(8_000_000)
    new_frames = _ctl_tx_frames_since_mark(chain)
    assert any(frame[1] == 0x23 for frame in new_frames), new_frames
    assert not any(frame[1] in (0x21, 0x22) for frame in new_frames), new_frames


@pytest.mark.slow
@pytest.mark.parametrize("eeprom_display_state", [0x06, 0xFF])
def test_eeprom_display_state_6_or_erased_clamps_to_legacy_input_state(
    v173_multi_pb_hex: Path,
    eeprom_display_state: int,
) -> None:
    chain = _new_chain(v173_multi_pb_hex)
    chain.write_control_eeprom_byte(CONTROL_DISPLAY_STATE_EEPROM, eeprom_display_state)
    chain.run_until_connected(limit=300)

    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB1
    assert chain.lcd_lines()[0] in ("Input:          ", "Input PB1:      ")


@pytest.mark.slow
@pytest.mark.parametrize(
    ("legacy_state", "rediscovered_state", "expected_row0_prefix"),
    [
        (3, STATE_SETUP_SPLIT, "Setup"),
    ],
)
def test_legacy_eeprom_display_state_rediscovery_preserves_visible_page(
    v173_multi_pb_hex: Path,
    legacy_state: int,
    rediscovered_state: int,
    expected_row0_prefix: str,
) -> None:
    chain = _new_chain(v173_multi_pb_hex)
    chain.write_control_eeprom_byte(CONTROL_DISPLAY_STATE_EEPROM, legacy_state)
    chain.run_until_connected(limit=300)

    if not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)):
        assert chain.read_reg(DISPLAY_STATE) == legacy_state
        chain.write_reg(HEALTH_SEEN_MASK, 0x02)
        chain.step_ticks(2_000_000)
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)
    assert chain.read_reg(DISPLAY_STATE) == rediscovered_state
    assert chain.lcd_lines()[0].startswith(expected_row0_prefix), chain.lcd_lines()


@pytest.mark.slow
def test_independent_pb2_intent_is_runtime_only_across_por_reset(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=False)
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)
    chain.write_reg(INPUT_INTENT_PB2, 0x07)
    chain.write_reg(DISPLAY_STATE, STATE_INPUT_PB2)

    chain.apply_reset_all("por")
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()

    assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN))
    assert chain.read_reg(INPUT_INTENT_PB2) == 0x00


@pytest.mark.slow
def test_power_on_reset_clears_runtime_pb2_split_state(v173_multi_pb_hex: Path) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain)
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN)

    chain.apply_reset_all("por")
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()
    assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN))


def test_pb2_persisted_byte_decoder_is_closed_allowlist() -> None:
    valid = {PB2_EEPROM_LINKED} | {
        PB2_EEPROM_CONCRETE_BASE | value for value in range(0x09)
    }
    for byte in range(0x100):
        mode, value = _decode_pb2_persisted(byte)
        if byte == PB2_EEPROM_LINKED:
            assert (mode, value) == ("linked", 0)
        elif byte in valid:
            assert (mode, value) == ("concrete", byte & 0x0F)
        else:
            assert (mode, value) == ("linked", 0)


@pytest.mark.slow
@pytest.mark.parametrize("seed", [0xFF, 0x80, 0x7F, 0x00, 0x07, 0xA1, 0xB9])
def test_pb2_persisted_erased_unknown_and_legacy_bytes_default_to_linked(
    v173_multi_pb_hex: Path,
    seed: int,
) -> None:
    chain = _new_chain(v173_multi_pb_hex)
    chain.write_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM, seed)
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()

    _rediscover_pb2_with_raw_status(chain, 0x03)

    flags = chain.read_reg(INPUT_SPLIT_FLAGS)
    assert flags & (1 << INPUT_SPLIT_FLAG_PB2_LINKED)
    assert not (flags & (1 << INPUT_SPLIT_FLAG_PB2_PENDING_CONCRETE))
    assert not (flags & (1 << INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY))
    assert not (flags & (1 << INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE))
    assert chain.read_reg(INPUT_INTENT_PB2) == chain.read_reg(INPUT_SELECT_CACHE)

    _navigate_right(chain, 3)
    assert chain.lcd_lines() == ("Input PB2:      ", "Same as PB1     ")
    frames = _force_full_sync_input_step(chain)
    assert frames and frames[-1][0] == 0xB0
    assert frames[-1][2] <= 0x08


@pytest.mark.slow
@pytest.mark.parametrize("cmd06", range(0x09))
def test_pb2_persisted_valid_concrete_values_apply_after_pb2_discovery(
    v173_multi_pb_hex: Path,
    cmd06: int,
) -> None:
    chain = _new_chain(v173_multi_pb_hex)
    chain.write_control_eeprom_byte(
        CONTROL_PB2_INPUT_EEPROM,
        PB2_EEPROM_CONCRETE_BASE | cmd06,
    )
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()

    _rediscover_pb2_with_raw_status(chain, 0x03)

    flags = chain.read_reg(INPUT_SPLIT_FLAGS)
    assert not (flags & (1 << INPUT_SPLIT_FLAG_PB2_LINKED))
    assert flags & (1 << INPUT_SPLIT_FLAG_PB2_PENDING_CONCRETE)
    assert not (flags & (1 << INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE))
    assert chain.read_reg(INPUT_PENDING_PB2) == cmd06
    assert chain.read_reg(INPUT_INTENT_PB2) == cmd06

    assert _force_full_sync_input_step(chain)[-1][0] == 0xB1
    assert _force_full_sync_input_step(chain)[-1] == (0xB2, 0x06, cmd06)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("raw_status", "expect_concrete"),
    [
        (0x00, False),
        (0x01, False),
        (0x02, False),
        (0x03, True),
        (0x04, True),
        (0x7F, True),
        (0x80, True),
        (0xFF, True),
    ],
)
def test_pb2_persisted_concrete_source_uses_raw_status_fallback_without_overwrite(
    v173_multi_pb_hex: Path,
    raw_status: int,
    expect_concrete: bool,
) -> None:
    seed = PB2_EEPROM_CONCRETE_BASE | 0x08  # Optical: valid only in full-input class.
    chain = _new_chain(v173_multi_pb_hex)
    chain.write_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM, seed)
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()

    _rediscover_pb2_with_raw_status(chain, raw_status)

    flags = chain.read_reg(INPUT_SPLIT_FLAGS)
    if expect_concrete:
        assert not (flags & (1 << INPUT_SPLIT_FLAG_PB2_LINKED))
        assert not (flags & (1 << INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE))
        assert chain.read_reg(INPUT_INTENT_PB2) == 0x08
    else:
        assert flags & (1 << INPUT_SPLIT_FLAG_PB2_LINKED)
        assert flags & (1 << INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE)
        assert chain.read_reg(INPUT_INTENT_PB2) == chain.read_reg(INPUT_SELECT_CACHE)

    chain.begin_memory_trace([_control_pb2_eeprom_watch()], max_records=200)
    _force_settings_save(chain)
    pb2_commits = [
        record for record in chain.memory_trace_records()
        if record["kind"] == "EepromCommit"
        and record["addr"] == CONTROL_PB2_INPUT_EEPROM
    ]
    assert pb2_commits == []
    assert chain.read_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM) == seed


@pytest.mark.slow
def test_pb2_user_selected_concrete_round_trips_through_eeprom_and_por(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _rediscover_pb2_with_raw_status(chain, 0x03)

    _navigate_right(chain, 3)
    assert chain.lcd_lines() == ("Input PB2:      ", "Same as PB1     ")
    for _ in range(4):  # Same -> Auto -> S/PDIF -> USB -> AES
        _press(chain, "UP")
    assert chain.lcd_lines() == ("Input PB2:      ", "AES             ")
    assert chain.read_reg(INPUT_INTENT_PB2) == 0x07
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY)

    _force_settings_save(chain)
    assert chain.read_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM) == (
        PB2_EEPROM_CONCRETE_BASE | 0x07
    )
    assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY))

    reboot = _new_chain(v173_multi_pb_hex)
    reboot.write_control_eeprom_byte(
        CONTROL_PB2_INPUT_EEPROM,
        PB2_EEPROM_CONCRETE_BASE | 0x07,
    )
    assert reboot.run_until_connected(limit=300) < 300, reboot.lcd_lines()
    _rediscover_pb2_with_raw_status(reboot, 0x03)
    assert not (reboot.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED))
    assert reboot.read_reg(INPUT_INTENT_PB2) == 0x07


@pytest.mark.slow
def test_every_user_selected_concrete_pb2_source_saves_documented_encoding(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _rediscover_pb2_with_raw_status(chain, 0x03)

    _navigate_right(chain, 3)
    assert chain.lcd_lines() == ("Input PB2:      ", "Same as PB1     ")
    for label, cmd06 in FULL_INPUT_ROWS:
        before = len(chain.tx_frames())
        _press(chain, "UP")
        frames = _cmd06_frames(chain, before)

        assert chain.lcd_lines() == ("Input PB2:      ", label)
        assert chain.read_reg(INPUT_INTENT_PB2) == cmd06
        assert frames and frames[-1] == (0xB2, 0x06, cmd06)
        assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY)

        _force_settings_save(chain)
        assert chain.read_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM) == (
            PB2_EEPROM_CONCRETE_BASE | cmd06
        )
        assert not (
            chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY)
        )


@pytest.mark.slow
def test_pb2_same_as_pb1_round_trips_as_linked_encoding(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _new_chain(v173_multi_pb_hex)
    chain.write_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM, PB2_EEPROM_CONCRETE_BASE | 0x07)
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()
    _rediscover_pb2_with_raw_status(chain, 0x03)

    _navigate_right(chain, 3)
    assert chain.lcd_lines() == ("Input PB2:      ", "AES             ")
    for _ in range(4):  # AES -> USB -> S/PDIF -> Auto Detect -> Same as PB1
        _press(chain, "DOWN")
    assert chain.lcd_lines() == ("Input PB2:      ", "Same as PB1     ")

    _press(chain, "RIGHT")
    _force_settings_save(chain)
    assert chain.read_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM) == PB2_EEPROM_LINKED


@pytest.mark.slow
def test_valid_pb2_eeprom_stays_pending_on_single_pb_chain_until_discovery(
    v173_multi_pb_hex: Path,
) -> None:
    _require_rust()
    chain = RustChain.from_v17_v3x_chain(
        control_hex_path=str(v173_multi_pb_hex),
        v3x_main_hex_path=str(V35_MAIN_HEX),
    )
    chain.write_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM, PB2_EEPROM_CONCRETE_BASE | 0x07)
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()

    assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN))
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_PENDING_CONCRETE)
    assert chain.read_reg(INPUT_PENDING_PB2) == 0x07

    _navigate_right(chain, 2)
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB1
    assert chain.lcd_lines()[0] == "Input:          "
    before = len(chain.tx_frames())
    _press(chain, "UP")
    frames = _cmd06_frames(chain, before)
    assert frames and frames[-1][0] == 0xB0
    assert not any(frame[0] == 0xB2 for frame in frames)


@pytest.mark.slow
def test_corrupt_runtime_pb2_intent_saves_linked_default_not_invalid_enum(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _rediscover_pb2_with_raw_status(chain, 0x03)
    _navigate_right(chain, 3)
    _press(chain, "UP")  # normal PB2 user change sets the persistence dirty bit.
    assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY)

    chain.write_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM, PB2_EEPROM_CONCRETE_BASE | 0x07)
    chain.write_reg(INPUT_INTENT_PB2, 0x7F)

    _force_settings_save(chain)

    assert chain.read_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM) == PB2_EEPROM_LINKED
    assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY))


@pytest.mark.slow
@pytest.mark.parametrize(
    ("runtime_state", "saved_state", "rediscovered_state"),
    [
        (STATE_INPUT_PB2, 0x02, STATE_INPUT_PB1),
        (STATE_SETUP_SPLIT, 0x03, STATE_SETUP_SPLIT),
        (STATE_PB1_DIAG_SPLIT, 0x04, STATE_PB1_DIAG_SPLIT),
        (STATE_PB2_DIAG_SPLIT, 0x05, STATE_PB2_DIAG_SPLIT),
    ],
)
def test_split_display_states_save_in_legacy_space_and_restore_after_rediscovery(
    v173_multi_pb_hex: Path,
    runtime_state: int,
    saved_state: int,
    rediscovered_state: int,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _rediscover_pb2_with_raw_status(chain, 0x03)
    chain.write_reg(DISPLAY_STATE, runtime_state)

    _force_settings_save(chain)
    assert chain.read_control_eeprom_byte(CONTROL_DISPLAY_STATE_EEPROM) == saved_state

    reboot = _new_chain(v173_multi_pb_hex)
    reboot.write_control_eeprom_byte(CONTROL_DISPLAY_STATE_EEPROM, saved_state)
    reboot.run_until_connected(limit=300)
    state_after_boot = reboot.read_reg(DISPLAY_STATE)
    assert state_after_boot in {saved_state, rediscovered_state}
    if reboot.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_SEEN):
        assert state_after_boot == rediscovered_state
        return

    assert state_after_boot == saved_state
    if saved_state in (0x02, 0x03):
        _rediscover_pb2_with_raw_status(reboot, 0x03)
        assert reboot.read_reg(DISPLAY_STATE) == rediscovered_state


@pytest.mark.slow
@pytest.mark.parametrize("payload", [0x09, 0x7F, 0x80, 0xFF])
@pytest.mark.parametrize("linked", [True, False])
def test_malformed_bf06_payloads_do_not_change_pb1_or_pb2_intents(
    v173_multi_pb_hex: Path,
    payload: int,
    linked: bool,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=linked)
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)
    chain.write_reg(INPUT_INTENT_PB2, 0x03)
    chain.write_reg(BF06_INPUT_GATE, 0x00)

    _inject_control_rx_frame(chain, (0xBF, 0x06, payload))
    chain.step_ticks(2_000_000)

    assert chain.read_reg(INPUT_SELECT_CACHE) == 0x08
    assert chain.read_reg(INPUT_INTENT_PB2) == 0x03
    flags = chain.read_reg(INPUT_SPLIT_FLAGS)
    assert bool(flags & (1 << INPUT_SPLIT_FLAG_PB2_LINKED)) is linked
    first = _force_full_sync_input_step(chain)
    if linked:
        assert first[-1] == (0xB0, 0x06, 0x08)
    else:
        assert first[-1] == (0xB1, 0x06, 0x08)


@pytest.mark.slow
def test_pb2_persistence_dirty_flag_prevents_repeat_eeprom_commits(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _rediscover_pb2_with_raw_status(chain, 0x03)
    _navigate_right(chain, 3)
    _press(chain, "UP")  # Same as PB1 -> Auto Detect concrete
    _force_settings_save(chain)
    assert chain.read_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM) == PB2_EEPROM_CONCRETE_BASE

    chain.begin_memory_trace([_control_pb2_eeprom_watch()], max_records=200)
    _force_settings_save(chain)
    _force_settings_save(chain)
    assert [
        record for record in chain.memory_trace_records()
        if record["kind"] == "EepromCommit"
        and record["addr"] == CONTROL_PB2_INPUT_EEPROM
    ] == []


@pytest.mark.slow
def test_navigation_full_sync_and_relink_cycles_do_not_write_clean_pb2_eeprom(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _new_chain(v173_multi_pb_hex)
    seed = PB2_EEPROM_CONCRETE_BASE | 0x07
    chain.write_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM, seed)
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()
    _rediscover_pb2_with_raw_status(chain, 0x03)
    assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY))

    chain.begin_memory_trace([_control_pb2_eeprom_watch()], max_records=400)

    _navigate_right(chain, 3)
    assert chain.lcd_lines() == ("Input PB2:      ", "AES             ")
    _navigate_right(chain, 4)
    assert chain.read_reg(DISPLAY_STATE) == STATE_VOLUME
    assert _force_full_sync_input_step(chain)[-1][0] == 0xB1
    assert _force_full_sync_input_step(chain)[-1] == (0xB2, 0x06, 0x07)

    chain.write_reg(HEALTH_SEEN_MASK, 0x00)
    chain.step_ticks(2_000_000)
    _rediscover_pb2_with_raw_status(chain, 0x03)
    _force_settings_save(chain)

    assert [
        record for record in chain.memory_trace_records()
        if record["kind"] == "EepromCommit"
        and record["addr"] == CONTROL_PB2_INPUT_EEPROM
    ] == []
    assert chain.read_control_eeprom_byte(CONTROL_PB2_INPUT_EEPROM) == seed


@pytest.mark.slow
@pytest.mark.parametrize("raw_status", [0x04, 0x7F, 0x80, 0xFF])
def test_bug_v173_pb2_same_as_pb1_down_clamps_unknown_raw_status(
    v173_multi_pb_hex: Path,
    raw_status: int,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _enter_pb2_same_as_pb1(chain, raw_status)

    before = len(chain.tx_frames())
    _press(chain, "DOWN")
    chain.step_ticks(20_000_000)

    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2
    assert chain.read_reg(MENU_OPTION_SELECTED) == 0x09
    assert chain.read_reg(MENU_OPTION_MAX) == 0x09
    assert chain.lcd_lines()[1] == "Analogue 4      "
    assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED))
    assert chain.read_reg(INPUT_INTENT_PB2) == 0x04
    _assert_last_cmd06(chain, before, 0xB2, 0x04)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("raw_status", "expected_label", "expected_data"),
    [
        (raw_status, label, data)
        for raw_status, (label, data) in VALID_RAW_STATUS_DOWN_WRAP.items()
    ],
)
def test_bug_v173_pb2_same_as_pb1_down_preserves_valid_raw_status_limits(
    v173_multi_pb_hex: Path,
    raw_status: int,
    expected_label: str,
    expected_data: int,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _enter_pb2_same_as_pb1(chain, raw_status)

    before = len(chain.tx_frames())
    _press(chain, "DOWN")

    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2
    assert chain.lcd_lines()[1] == expected_label
    assert chain.read_reg(INPUT_INTENT_PB2) == expected_data
    _assert_last_cmd06(chain, before, 0xB2, expected_data)


@pytest.mark.slow
@pytest.mark.parametrize("raw_status", [0x04, 0x7F, 0x80, 0xFF])
def test_bug_v173_unknown_raw_status_pb2_exact_label_to_cmd06_mapping(
    v173_multi_pb_hex: Path,
    raw_status: int,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _enter_pb2_same_as_pb1(chain, raw_status)

    for expected_label, expected_data in FULL_INPUT_ROWS:
        before = len(chain.tx_frames())
        _press(chain, "UP")
        assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2
        assert chain.read_reg(MENU_OPTION_MAX) == 0x09
        assert chain.lcd_lines()[1] == expected_label
        assert chain.read_reg(INPUT_INTENT_PB2) == expected_data
        _assert_last_cmd06(chain, before, 0xB2, expected_data)


@pytest.mark.slow
@pytest.mark.parametrize("raw_status", [0x80, 0xFF])
def test_bug_v173_unknown_raw_status_legacy_pb1_uses_full_input_table(
    v173_multi_pb_hex: Path,
    raw_status: int,
) -> None:
    chain = _boot_single_main_chain(v173_multi_pb_hex)
    chain.write_reg(RAW_STATUS_CACHE, raw_status)
    _navigate_right(chain, 2)
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB1

    for expected_label, expected_data in FULL_INPUT_ROWS[1:] + FULL_INPUT_ROWS[:1]:
        before = len(chain.tx_frames())
        _press(chain, "UP")
        assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB1
        assert chain.read_reg(MENU_OPTION_MAX) == 0x08
        assert chain.lcd_lines()[1].startswith(expected_label.strip())
        assert chain.read_reg(INPUT_SELECT_CACHE) == expected_data
        _assert_last_cmd06(chain, before, 0xB0, expected_data)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("raw_status", "expected_label", "expected_data"),
    [
        (0x00, "Analogue 1      ", 0x01),
        (0x01, "Analogue 2      ", 0x02),
        (0x02, "Analogue 3      ", 0x03),
        (0x03, "Analogue 4      ", 0x04),
        (0x80, "Analogue 4      ", 0x04),
    ],
)
def test_bug_v173_malformed_pb2_state_recovers_to_active_max_commit(
    v173_multi_pb_hex: Path,
    raw_status: int,
    expected_label: str,
    expected_data: int,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _enter_pb2_same_as_pb1(chain, raw_status)
    chain.write_reg(MENU_OPTION_SELECTED, 0x40)
    chain.write_reg(MENU_OPTION_MAX, 0x44)
    chain.write_reg(INPUT_SELECTED_INDEX, 0x40)
    chain.write_reg(INPUT_INTENT_PB2, 0xFF)

    before = len(chain.tx_frames())
    _press(chain, "DOWN")

    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2
    assert chain.read_reg(MENU_OPTION_SELECTED) == chain.read_reg(MENU_OPTION_MAX)
    assert chain.read_reg(MENU_OPTION_MAX) <= 0x09
    assert chain.lcd_lines()[1] == expected_label
    assert chain.read_reg(INPUT_INTENT_PB2) == expected_data
    _assert_last_cmd06(chain, before, 0xB2, expected_data)


@pytest.mark.slow
def test_bug_v173_independent_pb2_corrupt_intent_defaults_to_valid_row(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=False)
    chain.write_reg(RAW_STATUS_CACHE, 0x80)
    chain.write_reg(INPUT_INTENT_PB2, 0xFF)
    chain.write_reg(MENU_OPTION_SELECTED, 0x40)
    chain.write_reg(MENU_OPTION_MAX, 0x44)
    chain.write_reg(INPUT_SELECTED_INDEX, 0x40)

    _navigate_right(chain, 3)
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2
    assert chain.read_reg(RAW_STATUS_CACHE) == 0x80
    assert chain.read_reg(MENU_OPTION_MAX) == 0x09
    assert chain.read_reg(MENU_OPTION_SELECTED) == 0x01
    assert chain.lcd_lines()[1] == "Auto Detect     "

    before = len(chain.tx_frames())
    _press(chain, "UP")
    assert chain.lcd_lines()[1] == "S/PDIF          "
    assert chain.read_reg(INPUT_INTENT_PB2) == 0x05
    assert chain.read_reg(RAW_STATUS_CACHE) == 0x80
    _assert_last_cmd06(chain, before, 0xB2, 0x05)


@pytest.mark.slow
def test_bug_v173_raw_status_sentinel_survives_bf06_and_menu_mapping(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=True)
    chain.write_reg(RAW_STATUS_CACHE, 0x80)
    chain.write_reg(BF06_INPUT_GATE, 0x00)

    _inject_control_rx_frame(chain, (0xBF, 0x06, 0x01))
    chain.step_ticks(2_000_000)
    assert chain.read_reg(RAW_STATUS_CACHE) == 0x80
    assert chain.read_reg(INPUT_SELECT_CACHE) == 0x01

    _latch_split(chain, linked=False)
    chain.write_reg(INPUT_INTENT_PB2, 0xFF)
    _navigate_right(chain, 3)
    assert chain.lcd_lines()[1] == "Auto Detect     "
    assert chain.read_reg(RAW_STATUS_CACHE) == 0x80


@pytest.mark.slow
def test_bug_v173_unknown_raw_status_ir_previous_next_use_full_input_table(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_single_main_chain(v173_multi_pb_hex)
    chain.write_reg(IR_INPUT_NEXT_CODE_ADDR, IR_CMD_INPUT_NEXT)
    chain.write_reg(IR_INPUT_PREVIOUS_CODE_ADDR, IR_CMD_INPUT_PREVIOUS)

    chain.write_reg(RAW_STATUS_CACHE, 0x80)
    chain.write_reg(INPUT_SELECTED_INDEX, 0x00)
    before = len(chain.tx_frames())
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_INPUT_PREVIOUS)
    chain.step_ticks(COMMAND_SETTLE_TICKS)
    assert chain.read_reg(INPUT_SELECT_CACHE) == 0x04
    assert chain.read_reg(RAW_STATUS_CACHE) == 0x80
    _assert_last_cmd06(chain, before, 0xB0, 0x04)

    chain.write_reg(RAW_STATUS_CACHE, 0xFF)
    chain.write_reg(INPUT_SELECTED_INDEX, 0x08)
    before = len(chain.tx_frames())
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_INPUT_NEXT)
    chain.step_ticks(COMMAND_SETTLE_TICKS)
    assert chain.read_reg(INPUT_SELECT_CACHE) == 0x00
    assert chain.read_reg(RAW_STATUS_CACHE) == 0xFF
    _assert_last_cmd06(chain, before, 0xB0, 0x00)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("linked", "expected_route"),
    [(True, 0xB0), (False, 0xB1)],
    ids=["linked-broadcast", "independent-pb1"],
)
@pytest.mark.parametrize(
    ("ir_cmd", "start_index", "expected_input"),
    [
        (IR_CMD_INPUT_PREVIOUS, 0x00, 0x04),
        (IR_CMD_INPUT_NEXT, 0x08, 0x00),
    ],
    ids=["previous-wrap", "next-wrap"],
)
def test_bug_v173_split_ir_previous_next_keep_route_style_and_pb2_intent(
    v173_multi_pb_hex: Path,
    linked: bool,
    expected_route: int,
    ir_cmd: int,
    start_index: int,
    expected_input: int,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)
    _latch_split(chain, linked=linked)
    chain.write_reg(IR_INPUT_NEXT_CODE_ADDR, IR_CMD_INPUT_NEXT)
    chain.write_reg(IR_INPUT_PREVIOUS_CODE_ADDR, IR_CMD_INPUT_PREVIOUS)
    chain.write_reg(RAW_STATUS_CACHE, 0x80)
    chain.write_reg(INPUT_SELECTED_INDEX, start_index)
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)
    chain.write_reg(INPUT_INTENT_PB2, 0x03)

    before = len(chain.tx_frames())
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=ir_cmd)
    chain.step_ticks(COMMAND_SETTLE_TICKS)

    frames = _cmd06_frames(chain, before)
    assert frames and frames[-1] == (expected_route, 0x06, expected_input)
    if linked:
        assert not any(frame[0] in (0xB1, 0xB2) for frame in frames)
        assert chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED)
    else:
        assert not any(frame[0] in (0xB0, 0xB2) for frame in frames)
        assert chain.read_reg(INPUT_INTENT_PB2) == 0x03
        assert not (chain.read_reg(INPUT_SPLIT_FLAGS) & (1 << INPUT_SPLIT_FLAG_PB2_LINKED))
    assert chain.read_reg(INPUT_SELECT_CACHE) == expected_input
    assert chain.read_reg(RAW_STATUS_CACHE) == 0x80


@pytest.mark.slow
@pytest.mark.parametrize("raw_status", [0x03, 0x04, 0x7F, 0x80, 0xFF])
def test_bug_v173_canonical_hex_pb2_same_as_pb1_down_raw_status_regression(
    raw_status: int,
) -> None:
    chain = _boot_chain(V173_CONTROL_HEX)
    _enter_pb2_same_as_pb1(chain, raw_status)

    before = len(chain.tx_frames())
    _press(chain, "DOWN")

    expected_label, expected_data = VALID_RAW_STATUS_DOWN_WRAP[0x03]
    assert chain.read_reg(DISPLAY_STATE) == STATE_INPUT_PB2
    assert chain.lcd_lines()[1] == expected_label
    assert chain.read_reg(INPUT_INTENT_PB2) == expected_data
    _assert_last_cmd06(chain, before, 0xB2, expected_data)


@pytest.mark.slow
def test_bug_v173_canonical_hex_pb2_full_sync_clamps_corrupt_intent() -> None:
    chain = _boot_chain(V173_CONTROL_HEX)
    chain.write_reg(
        INPUT_SPLIT_FLAGS,
        (1 << INPUT_SPLIT_FLAG_PB2_SEEN) | (1 << INPUT_SPLIT_FLAG_SYNC_TARGET),
    )
    chain.write_reg(INPUT_SELECT_CACHE, 0x08)
    chain.write_reg(INPUT_INTENT_PB2, 0xFF)

    frames = _force_full_sync_input_step(chain)

    assert frames and frames[-1] == (0xB2, 0x06, 0x00)
    assert chain.read_reg(INPUT_INTENT_PB2) == 0x00


def test_bug_v173_bf08_ackstat_only_does_not_leave_sticky_lcd_fault(
    v173_multi_pb_hex: Path,
) -> None:
    chain = _boot_chain(v173_multi_pb_hex)

    _inject_control_bf08(chain, 0x04)
    assert chain.read_reg(BF08_FAULT_BYTE) == 0x04
    assert not (chain.read_reg(CONTROL_FLAGS) & (1 << DSP_FAULT_BIT))

    _inject_control_bf08(chain, 0x44)
    assert chain.read_reg(BF08_FAULT_BYTE) == 0x44
    assert chain.read_reg(CONTROL_FLAGS) & (1 << DSP_FAULT_BIT)

    _inject_control_bf08(chain, 0x04)
    assert chain.read_reg(BF08_FAULT_BYTE) == 0x04
    assert not (chain.read_reg(CONTROL_FLAGS) & (1 << DSP_FAULT_BIT))


def test_display_state_save_load_remaps_split_menu_to_legacy_eeprom_space() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8")
    save = text[
        text.index("settings_save_eeprom:"):
        text.index("settings_save_eeprom__write_next_setting_bank:")
    ]
    load = text[
        text.index("settings_load_eeprom:"):
        text.index("settings_load_eeprom__read_next_setting_bank:")
    ]
    assert "INPUT_SPLIT_FLAG_PB2_SEEN" in save
    assert "settings_save_eeprom__split_menu_state_ge3" in save
    assert "decf    tx_data_staging_acc, F, A                      ; split 3..6 -> legacy EEPROM 2..5" in save
    assert "settings_save_eeprom__clamp_runtime_state" in save
    assert "settings_load_eeprom__clamp_display_state" in load
    assert "movlw   0x02                                        ; clamp erased/foreign runtime states to Input" in load


def test_pb2_menu_state_and_malformed_row_are_gated_by_split_flag() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8")
    menu_max = text[
        text.index("input_menu_max_state_to_w:"):
        text.index("volume_screen__draw_current_menu_title:")
    ]
    prepare = text[
        text.index("input_screen_prepare_selected_row:"):
        text.index("input_screen_prepare_option_label:")
    ]
    compute_max = text[
        text.index("input_screen_compute_menu_max:"):
        text.index("input_screen_prepare_selected_row:")
    ]
    render = text[
        text.index("input_screen__render_option_row:"):
        text.index("input_screen__draw_option_and_service:")
    ]
    dispatch = text[
        text.index("v171_menu_ck_state_3:"):
        text.index("display_state_entry__handle_menu_next:")
    ]

    assert "movlw   0x05" in menu_max
    assert "btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED" in menu_max
    assert "movlw   0x06" in menu_max
    assert "input_raw_status_full_fallback_save:" in text
    assert "input_raw_status_restore:" in text
    assert "cpfsgt  raw_status_cache_b0, BANKED" in text
    ram_text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    assert "input_raw_status_full_fallback_save /" in ram_text
    assert "v171_tx_enq_retry          equ  0x02D" in ram_text
    assert "input_raw_status_save_scratch equ 0x028" not in ram_text
    assert "movff   raw_status_cache_b0_phys, v171_tx_enq_retry_acc_phys" in text
    assert "movff   v171_tx_enq_retry_acc_phys, raw_status_cache_b0_phys" in text
    assert "input_screen_compute_menu_max:" in text
    assert "call    input_screen_clamp_staged_row, 0x0" in text
    assert render.index("call    input_screen_compute_menu_max, 0x0") < render.index(
        "call    input_screen_prepare_option_label, 0x0"
    )
    assert render.index("call    input_screen_clamp_staged_row, 0x0") < render.index(
        "call    input_screen_prepare_option_label, 0x0"
    )
    assert "movwf   menu_option_max_index_b0, BANKED" in compute_max
    assert "cpfsgt  rx_ring_staging_b0, BANKED" in compute_max
    assert "INPUT_SPLIT_FLAG_PB2_LINKED" in prepare
    assert "decf    rx_ring_staging_b0, F, BANKED" in prepare
    assert "bc      input_screen__send_option_after_up" in text
    assert "split state 3 -> Input PB2" in dispatch
    assert "split state 4 -> Setup" in dispatch
