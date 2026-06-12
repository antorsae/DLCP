from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PROJECT_ROOT,
    V17_CONTROL_RAM_INC,
    V171_CONTROL_HEX,
    V172_CONTROL_ASM,
    V173_CONTROL_ASM,
    V32_MAIN_HEX,
    V33_MAIN_ASM,
    V34_MAIN_ASM,
)
from dlcp_fw.sim.v17_symbols import assemble_v17
from dlcp_fw.sim.v30_symbols import assemble_v30

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


SPEC = PROJECT_ROOT / "docs" / "PRESET_FILENAME_LCD_SPEC.md"
V33_MAIN_LST = V33_MAIN_ASM.with_suffix(".lst")
V34_MAIN_LST = V34_MAIN_ASM.with_suffix(".lst")
V172_CONTROL_LST = V172_CONTROL_ASM.with_suffix(".lst")
V173_CONTROL_LST = V173_CONTROL_ASM.with_suffix(".lst")


def _spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


def _assert_contains_all(text: str, needles: list[str]) -> None:
    missing = [needle for needle in needles if needle not in text]
    assert not missing, "missing required spec text:\n" + "\n".join(missing)


PB1 = 0
PB2 = 1
SLOT_A = 0
SLOT_B = 1
START_TAIL = 0x2E
START_PREFIX = 0x2F
LEN_CMD = 0x2D
END_CMD = 0x4E
FILENAME_RAM_BASE = 0x2C0
FILENAME_LEN = 0x1E
PRESET_A_EEPROM_BASE = 0x60
PRESET_B_EEPROM_BASE = 0x83
FNAME_CACHE_PHYS = 0x220
FNAME_LEN_PHYS = 0x23E
FNAME_EXPECTED_LEN_PHYS = 0x23F
FNAME_FLAGS_PHYS = 0x240
FNAME_SCROLL_OFF_PHYS = 0x243
FNAME_RENDER_COL_PHYS = 0x259
FNAME_RENDER_OFF_PHYS = 0x25A
FNAME_ID_PHYS = 0x242
FNAME_DEADLINE_LO_PHYS = 0x257
FNAME_DEADLINE_HI_PHYS = 0x258
FNAME_VALID_MASK = 0x01
FNAME_PENDING_MASK = 0x02
FNAME_WANT_QUERY_MASK = 0x04
FNAME_ROW_DIRTY_MASK = 0x08
FNAME_ARMED_MASK = 0x10
FNAME_TAILDIR_MASK = 0x20
FNAME_LEN_SEEN_MASK = 0x40
FNAME_QUERY_WAIT_MASK = 0x80
CONTROL_FLAGS_PHYS = 0x01F
CONTROL_CONNECTED_MASK = 0x02
DSP_FAULT_MASK = 0x80
MUTE_MASK = 0x20
PRESET_BIT_MASK = 0x40
DISPLAY_STATE_INDEX_PHYS = 0x0BF
VOLUME_CACHE_PHYS = 0x0B9
IR_PROFILE_ADDR_PHYS = 0x020
IR_PROFILE_POWER_PHYS = 0x021
IR_PROFILE_VOL_UP_PHYS = 0x022
IR_PROFILE_VOL_DOWN_PHYS = 0x023
IR_PROFILE_INPUT_UP_PHYS = 0x024
IR_PROFILE_INPUT_DOWN_PHYS = 0x025
IR_PROFILE_MUTE_PHYS = 0x026
IR_ADDR_HYPEX = 0x10
IR_CMD_VOL_UP = 0x10
IR_CMD_MUTE = 0x0D
IR_CMD_STANDBY = 0x3A
IR_CMD_WAKE = 0x3B
MAIN_ACTIVE_FLAGS_PHYS = 0x05E
MAIN_ACTIVE_GATE_MASK = 0x08
REQUESTED_FILENAME_LONG_A = "LX521 V15 L22MG old_NC100"
REQUESTED_FILENAME_SHORT_B = "LX521.4 PB6v23 Q"
PINS = {
    "RIGHT": ("A", 4),
    "LEFT": ("C", 5),
    "UP": ("C", 0),
    "DOWN": ("A", 2),
    "STBY": ("A", 3),
}

PRESET_FILENAME_SLOT_A = "LX521.4 22MG10F-v5"
PRESET_FILENAME_SLOT_B = "LX521.4 22MG10F-v7"
PRESET_REENTRY_POLL_TICKS = 4_800
ROW0_PRESET_REPAINT_BUDGET_TICKS = 960_000
PRESET_REENTRY_TRACE_TICKS = 80_000_000
KEY_HOLD_TICKS = 5_000_000


@dataclass(frozen=True)
class NativePresetFilenameStep:
    key: str
    preset: str


PRESET_STATE_MATRIX_CASES = [
    pytest.param(
        "A",
        (NativePresetFilenameStep("RIGHT", "A"),),
        id="entry-a",
    ),
    pytest.param(
        "B",
        (NativePresetFilenameStep("RIGHT", "B"),),
        id="entry-b",
    ),
    pytest.param(
        "A",
        (
            NativePresetFilenameStep("RIGHT", "A"),
            NativePresetFilenameStep("DOWN", "B"),
        ),
        id="a-to-b",
    ),
    pytest.param(
        "B",
        (
            NativePresetFilenameStep("RIGHT", "B"),
            NativePresetFilenameStep("UP", "A"),
        ),
        id="b-to-a",
    ),
    pytest.param(
        "A",
        (
            NativePresetFilenameStep("RIGHT", "A"),
            NativePresetFilenameStep("DOWN", "B"),
            NativePresetFilenameStep("UP", "A"),
        ),
        id="a-b-a",
    ),
    pytest.param(
        "B",
        (
            NativePresetFilenameStep("RIGHT", "B"),
            NativePresetFilenameStep("UP", "A"),
            NativePresetFilenameStep("DOWN", "B"),
        ),
        id="b-a-b",
    ),
]

PRESET_REENTRY_MATRIX_CASES = [
    pytest.param(
        "A",
        (NativePresetFilenameStep("RIGHT", "A"),),
        "A",
        id="entry-a",
    ),
    pytest.param(
        "B",
        (NativePresetFilenameStep("RIGHT", "B"),),
        "B",
        id="entry-b",
    ),
    pytest.param(
        "A",
        (
            NativePresetFilenameStep("RIGHT", "A"),
            NativePresetFilenameStep("DOWN", "B"),
        ),
        "B",
        id="a-to-b",
    ),
    pytest.param(
        "B",
        (
            NativePresetFilenameStep("RIGHT", "B"),
            NativePresetFilenameStep("UP", "A"),
        ),
        "A",
        id="b-to-a",
    ),
    pytest.param(
        "A",
        (
            NativePresetFilenameStep("RIGHT", "A"),
            NativePresetFilenameStep("DOWN", "B"),
            NativePresetFilenameStep("UP", "A"),
        ),
        "A",
        id="a-b-a",
    ),
    pytest.param(
        "B",
        (
            NativePresetFilenameStep("RIGHT", "B"),
            NativePresetFilenameStep("UP", "A"),
            NativePresetFilenameStep("DOWN", "B"),
        ),
        "B",
        id="b-a-b",
    ),
]


def _query_id(gen: int, target: int = PB1, slot: int = SLOT_A) -> int:
    return ((gen & 0x1F) << 2) | ((target & 1) << 1) | (slot & 1)


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


@pytest.fixture(scope="module")
def v172_v33_filename_hexes(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    tmp = tmp_path_factory.mktemp("v172_v33_preset_filename")
    shutil.copy(V17_CONTROL_RAM_INC, tmp / V17_CONTROL_RAM_INC.name)
    control_asm = tmp / V172_CONTROL_ASM.name
    control_asm.write_bytes(V172_CONTROL_ASM.read_bytes())
    control_hex = tmp / "dlcp_control_v172.hex"
    main_hex = tmp / "DLCP_Firmware_V3.3.hex"
    assemble_v17(control_asm, control_hex)
    assemble_v30(V33_MAIN_ASM, main_hex)
    return control_hex, main_hex


@pytest.fixture(scope="module")
def v173_v34_filename_hexes(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    tmp = tmp_path_factory.mktemp("v173_v34_preset_filename")
    shutil.copy(V17_CONTROL_RAM_INC, tmp / V17_CONTROL_RAM_INC.name)
    control_asm = tmp / V173_CONTROL_ASM.name
    control_asm.write_bytes(V173_CONTROL_ASM.read_bytes())
    control_hex = tmp / "dlcp_control_v173.hex"
    main_hex = tmp / "DLCP_Firmware_V3.4.hex"
    assemble_v17(control_asm, control_hex)
    assemble_v30(V34_MAIN_ASM, main_hex)
    return control_hex, main_hex


def _filename_slot(text: str) -> bytes:
    raw = text.encode("ascii")[:FILENAME_LEN]
    return raw + bytes([0xFF]) * (FILENAME_LEN - len(raw))


def _seed_filename_slots(chain, slot_a: str, slot_b: str) -> None:  # type: ignore[no-untyped-def]
    for unit in (0, 1):
        for offset, value in enumerate(_filename_slot(slot_a)):
            chain.write_main_eeprom_byte(unit, PRESET_A_EEPROM_BASE + offset, value)
        for offset, value in enumerate(_filename_slot(slot_b)):
            chain.write_main_eeprom_byte(unit, PRESET_B_EEPROM_BASE + offset, value)


def _press(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = PINS[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(5_000_000)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(5_000_000)
    for _ in range(8):
        chain.step()


def _key_down(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = PINS[key]
    chain.set_control_pin(port, bit, False)


def _key_up(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = PINS[key]
    chain.set_control_pin(port, bit, True)


def _press_until_lcd(
    chain,
    key: str,
    predicate,
    *,  # type: ignore[no-untyped-def]
    timeout_ticks: int = 80_000_000,
    poll_ticks: int = PRESET_REENTRY_POLL_TICKS,
) -> tuple[tuple[str, str], int]:  # type: ignore[no-untyped-def]
    start = chain.current_tick()
    release_at = start + KEY_HOLD_TICKS
    released = False
    _key_down(chain, key)
    try:
        while chain.current_tick() - start <= timeout_ticks:
            now = chain.current_tick()
            if not released and now >= release_at:
                _key_up(chain, key)
                released = True
            lines = chain.lcd_lines()
            if predicate(lines):
                if not released:
                    _key_up(chain, key)
                    released = True
                return lines, chain.current_tick()
            chain.step_ticks(poll_ticks)
    finally:
        if not released:
            _key_up(chain, key)
    pytest.fail(
        f"{key} did not reach requested LCD state; lcd={chain.lcd_lines()!r}; "
        f"tick={chain.current_tick()}"
    )


def _preset_row0_ready(line0: str, preset: str) -> bool:
    return line0 == _preset_row0(preset)


def _row1_has_filename_cache_text(line1: str, expected_window: str) -> bool:
    if not line1.strip():
        return False
    if line1 == "Auto Detect     ":
        return False
    return any(
        actual != " " and actual == expected
        for actual, expected in zip(line1, expected_window, strict=True)
    )


def _drive_b_a_b_to_input_and_trace_immediate_left(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> dict[str, object]:
    _require_rust()
    control_hex, main_hex = v172_v33_filename_hexes
    chain = _start_native_filename_chain(
        control_hex,
        main_hex,
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
        initial_preset="B",
    )

    for step in (
        NativePresetFilenameStep("RIGHT", "B"),
        NativePresetFilenameStep("UP", "A"),
        NativePresetFilenameStep("DOWN", "B"),
    ):
        _drive_and_assert_native_preset_filename(
            chain,
            step,
            slot_a=PRESET_FILENAME_SLOT_A,
            slot_b=PRESET_FILENAME_SLOT_B,
        )

    _press(chain, "RIGHT")
    input_lines, input_visible_tick = _wait_for_lcd(
        chain,
        lambda lcd: lcd == ("Input:          ", "Auto Detect     "),
        ticks=PRESET_REENTRY_POLL_TICKS,
    ), chain.current_tick()
    assert input_lines == ("Input:          ", "Auto Detect     ")

    expected = (
        _preset_row0("B"),
        _preset_filename_window("B", PRESET_FILENAME_SLOT_A, PRESET_FILENAME_SLOT_B),
    )
    chain.mark_ctl_tx_capture_point()
    chain.mark_ctl_rx_capture_point()
    before_gen = chain.read_reg(FNAME_ID_PHYS)
    before_flags = chain.read_reg(FNAME_FLAGS_PHYS)
    left_down_tick = chain.current_tick()
    _press(chain, "LEFT")
    assert left_down_tick - input_visible_tick <= PRESET_REENTRY_POLL_TICKS

    first_preset_tick: int | None = None
    row0_ready_tick: int | None = None
    row1_visible_tick: int | None = None
    exact_expected_tick: int | None = None
    trace: list[tuple[int, int, int, int, int, tuple[str, str]]] = []
    while chain.current_tick() - left_down_tick <= PRESET_REENTRY_TRACE_TICKS:
        now = chain.current_tick()
        lines = chain.lcd_lines()
        display_state = chain.read_reg(DISPLAY_STATE_INDEX_PHYS)
        flags = chain.read_reg(FNAME_FLAGS_PHYS)
        render_col = chain.read_reg(FNAME_RENDER_COL_PHYS)
        render_off = chain.read_reg(FNAME_RENDER_OFF_PHYS)
        if len(trace) < 512 or display_state == 1:
            trace.append((now, display_state, flags, render_col, render_off, lines))
        if display_state == 1:
            if first_preset_tick is None:
                first_preset_tick = now
            if row0_ready_tick is None and _preset_row0_ready(lines[0], "B"):
                row0_ready_tick = now
            row1_has_filename = _row1_has_filename_cache_text(lines[1], expected[1])
            if row1_visible_tick is None and row1_has_filename:
                row1_visible_tick = now
            if lines[0] == " " * 16 and row1_has_filename:
                pytest.fail(
                    "Preset row 1 became visible while row 0 was blank; "
                    f"tick={now}; input_visible_tick={input_visible_tick}; "
                    f"left_down_tick={left_down_tick}; flags=0x{flags:02X}; "
                    f"render_col={render_col}; render_off={render_off}; "
                    f"lcd={lines!r}; trace_tail={trace[-24:]!r}"
                )
            if (
                first_preset_tick is not None
                and row0_ready_tick is None
                and now - first_preset_tick > ROW0_PRESET_REPAINT_BUDGET_TICKS
            ):
                pytest.fail(
                    "Preset row 0 did not repaint within budget; "
                    f"first_preset_tick={first_preset_tick}; now={now}; "
                    f"lcd={lines!r}; trace_tail={trace[-24:]!r}"
                )
            if lines == expected:
                exact_expected_tick = now
                break
        chain.step_ticks(PRESET_REENTRY_POLL_TICKS)

    tx_frames = _bytes_to_frames(chain.ctl_tx_record_since_last_capture())
    filename_queries = [
        frame for frame in tx_frames if frame[0] == 0xB1 and frame[1] == 0x26
    ]
    rx_frames = _sliding_frames(chain.ctl_rx_record_since_last_capture())
    filename_replies = [
        frame for frame in rx_frames if frame[0] == 0xBF and 0x2D <= frame[1] <= 0x4E
    ]
    assert not filename_queries, f"same-slot re-entry issued fresh query: {filename_queries!r}"
    assert not filename_replies, f"same-slot re-entry consumed fresh reply: {filename_replies!r}"
    assert not (chain.read_reg(FNAME_FLAGS_PHYS) & (FNAME_PENDING_MASK | FNAME_QUERY_WAIT_MASK))
    assert chain.read_reg(FNAME_ID_PHYS) == before_gen
    assert before_flags & FNAME_VALID_MASK
    assert first_preset_tick is not None, f"never re-entered Preset; trace_tail={trace[-24:]!r}"
    assert row0_ready_tick is not None, f"row0 never reached Preset B; trace_tail={trace[-24:]!r}"
    assert row0_ready_tick - first_preset_tick <= ROW0_PRESET_REPAINT_BUDGET_TICKS
    assert exact_expected_tick is not None, f"expected LCD never converged; trace_tail={trace[-24:]!r}"
    return {
        "input_visible_tick": input_visible_tick,
        "left_down_tick": left_down_tick,
        "first_preset_tick": first_preset_tick,
        "row0_ready_tick": row0_ready_tick,
        "row1_visible_tick": row1_visible_tick,
        "exact_expected_tick": exact_expected_tick,
        "trace": trace,
    }


def _bytes_to_frames(raw: list[int]) -> list[tuple[int, int, int]]:
    return [tuple(raw[i : i + 3]) for i in range(0, len(raw) - 2, 3)]  # type: ignore[misc]


def _sliding_frames(raw: list[int]) -> list[tuple[int, int, int]]:
    return [tuple(raw[i : i + 3]) for i in range(0, len(raw) - 2)]  # type: ignore[misc]


def _frame_tuple(frame) -> tuple[int, int, int]:  # type: ignore[no-untyped-def]
    return tuple(frame) if isinstance(frame, tuple) else (frame.route, frame.cmd, frame.data)


def _configure_hypex_ir_profile(chain) -> None:  # type: ignore[no-untyped-def]
    for addr, value in (
        (IR_PROFILE_ADDR_PHYS, IR_ADDR_HYPEX),
        (IR_PROFILE_POWER_PHYS, 0x0C),
        (IR_PROFILE_VOL_UP_PHYS, IR_CMD_VOL_UP),
        (IR_PROFILE_VOL_DOWN_PHYS, 0x11),
        (IR_PROFILE_INPUT_UP_PHYS, 0x20),
        (IR_PROFILE_INPUT_DOWN_PHYS, 0x21),
        (IR_PROFILE_MUTE_PHYS, IR_CMD_MUTE),
    ):
        chain.write_reg(addr, value)


def _inject_ir(
    chain, cmd: int, *, settle_ticks: int = 12_000_000,
) -> list[tuple[int, int, int]]:  # type: ignore[no-untyped-def]
    before = len(chain.tx_frames())
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=cmd)
    chain.step_ticks(settle_ticks)
    return [_frame_tuple(frame) for frame in chain.tx_frames()[before:]]


def _main_active_gates(chain) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    return tuple(
        (chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS_PHYS) & MAIN_ACTIVE_GATE_MASK) >> 3
        for unit in (0, 1)
    )


def _wait_until(chain, predicate, *, attempts: int = 120, ticks: int = 1_000_000) -> None:  # type: ignore[no-untyped-def]
    for _ in range(attempts):
        if predicate():
            return
        chain.step_ticks(ticks)
    raise AssertionError(
        f"condition did not converge; lcd={chain.lcd_lines()!r}; "
        f"flags=0x{chain.read_reg(CONTROL_FLAGS_PHYS):02X}"
    )


def _wait_for_lcd(chain, predicate, *, attempts: int = 160, ticks: int = 1_000_000):  # type: ignore[no-untyped-def]
    for _ in range(attempts):
        lines = chain.lcd_lines()
        if predicate(lines):
            return lines
        chain.step_ticks(ticks)
    pytest.fail(
        f"LCD condition did not converge; lcd={chain.lcd_lines()!r}; "
        f"fname_flags=0x{chain.read_reg(FNAME_FLAGS_PHYS):02X}; "
        f"fname_len={chain.read_reg(FNAME_LEN_PHYS)}"
    )


def _preset_name(preset: str, slot_a: str, slot_b: str) -> str:
    if preset == "A":
        return slot_a
    if preset == "B":
        return slot_b
    raise AssertionError(f"unknown preset {preset!r}")


def _preset_other_name(preset: str, slot_a: str, slot_b: str) -> str:
    if preset == "A":
        return slot_b
    if preset == "B":
        return slot_a
    raise AssertionError(f"unknown preset {preset!r}")


def _preset_slot_bit(preset: str) -> int:
    if preset == "A":
        return SLOT_A
    if preset == "B":
        return SLOT_B
    raise AssertionError(f"unknown preset {preset!r}")


def _preset_row0(preset: str) -> str:
    return f"Preset         {preset}"


def _preset_filename_window(preset: str, slot_a: str, slot_b: str) -> str:
    name = _preset_name(preset, slot_a, slot_b)
    other = _preset_other_name(preset, slot_a, slot_b)
    return _window(name, tail_first=_start_cmd_for(name, other) == START_TAIL)


def _preset_filename_windows(preset: str, slot_a: str, slot_b: str) -> set:
    """All 16-char row-1 windows the scroller can legally show for the
    preset's filename (head window for short names; every scroll rotation
    for long ones).  The V1.73 periodic mute re-assert added background
    chain traffic that shifts the scroll phase relative to a button press,
    so exact-head waits became phase-sensitive; rotation-tolerant waits
    keep the content contract while dropping the phase assumption."""
    name = _preset_name(preset, slot_a, slot_b)
    head = _preset_filename_window(preset, slot_a, slot_b)
    if len(name) <= 16:
        return {head}
    # The scroller BOUNCES between offsets 0..len-16 (no circular wrap), so
    # the legal windows are exactly the contiguous 16-char substrings
    # (codex review of b1f35d6 tightened this from circular rotations).
    windows = {name[i : i + 16] for i in range(len(name) - 15)}
    windows.add(head)
    return windows


def _start_native_filename_chain(
    control_hex: Path,
    main_hex: Path,
    *,
    slot_a: str,
    slot_b: str,
    initial_preset: str = "A",
):  # type: ignore[no-untyped-def]
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    _seed_filename_slots(chain, slot_a, slot_b)
    chain.write_control_eeprom_byte(0x74, _preset_slot_bit(initial_preset))

    chain.run_until_connected(limit=300)
    assert chain.is_connected() and not chain.is_waiting()
    chain.step_ticks(50_000_000)
    return chain


def _assert_native_filename_query_completed(
    chain,
    *,
    preset: str,
    slot_a: str,
    slot_b: str,
    query_frames: list[tuple[int, int, int]] | None = None,
) -> int:  # type: ignore[no-untyped-def]
    name = _preset_name(preset, slot_a, slot_b)
    other = _preset_other_name(preset, slot_a, slot_b)
    effective = _effective_name(name)

    # ctl_tx_record_since_last_capture() is consume-on-read; callers that
    # already drained it (e.g. the cache-or-query wrapper) pass the frames in.
    if query_frames is None:
        query_frames = _bytes_to_frames(chain.ctl_tx_record_since_last_capture())
    filename_queries = [
        frame for frame in query_frames if frame[0] == 0xB1 and frame[1] == 0x26
    ]
    assert filename_queries, f"CONTROL did not issue PB1 cmd 0x26 query: {query_frames!r}"
    assert len(filename_queries) <= 1, (
        f"CONTROL issued {len(filename_queries)} filename queries, expected at most "
        f"1: {filename_queries!r}"
    )
    query_id = filename_queries[-1][2]
    assert (query_id & 0x01) == _preset_slot_bit(preset), (
        f"CONTROL queried preset bit {query_id & 0x01}, expected {preset}; "
        f"frames={query_frames!r}"
    )

    rx_raw = chain.ctl_rx_record_since_last_capture()
    rx_frames = _sliding_frames(rx_raw)
    expected_start = _start_cmd_for(name, other)
    assert (0xBF, expected_start, query_id) in rx_frames, _bytes_to_frames(rx_raw)
    assert (0xBF, LEN_CMD, query_id ^ len(effective)) in rx_frames, _bytes_to_frames(rx_raw)
    assert (0xBF, END_CMD, query_id) in rx_frames, _bytes_to_frames(rx_raw)

    _assert_native_filename_cache_valid(
        chain,
        preset=preset,
        slot_a=slot_a,
        slot_b=slot_b,
        expected_id=query_id,
    )
    return query_id


def _assert_native_filename_cache_valid(
    chain,
    *,
    preset: str,
    slot_a: str,
    slot_b: str,
    expected_id: int | None = None,
) -> None:  # type: ignore[no-untyped-def]
    name = _preset_name(preset, slot_a, slot_b)
    other = _preset_other_name(preset, slot_a, slot_b)
    effective = _effective_name(name)
    expected_start = _start_cmd_for(name, other)

    flags = chain.read_reg(FNAME_FLAGS_PHYS)
    assert flags & FNAME_VALID_MASK
    assert flags & FNAME_LEN_SEEN_MASK
    assert bool(flags & FNAME_TAILDIR_MASK) == (expected_start == START_TAIL)
    assert not (flags & FNAME_PENDING_MASK)
    assert not (flags & FNAME_QUERY_WAIT_MASK)
    query_id = chain.read_reg(FNAME_ID_PHYS)
    if expected_id is not None:
        assert query_id == expected_id
    assert (query_id & 0x01) == _preset_slot_bit(preset)
    assert chain.read_reg(FNAME_LEN_PHYS) == len(effective)
    cache = bytes(chain.read_reg(FNAME_CACHE_PHYS + i) for i in range(len(effective)))
    assert cache == effective.encode("ascii")


def _assert_native_filename_cache_or_query_completed(
    chain,
    *,
    preset: str,
    slot_a: str,
    slot_b: str,
    allow_query: bool,
) -> None:  # type: ignore[no-untyped-def]
    query_frames = _bytes_to_frames(chain.ctl_tx_record_since_last_capture())
    filename_queries = [
        frame for frame in query_frames if frame[0] == 0xB1 and frame[1] == 0x26
    ]
    assert len(filename_queries) <= 1, (
        f"CONTROL issued {len(filename_queries)} filename queries, expected at most "
        f"1: {filename_queries!r}"
    )
    if filename_queries:
        assert allow_query, f"expected cache reuse, got query frames: {filename_queries!r}"
        _assert_native_filename_query_completed(
            chain,
            preset=preset,
            slot_a=slot_a,
            slot_b=slot_b,
            query_frames=query_frames,
        )
        return

    _assert_native_filename_cache_valid(
        chain,
        preset=preset,
        slot_a=slot_a,
        slot_b=slot_b,
    )


def _drive_and_assert_native_preset_filename(
    chain,
    step: NativePresetFilenameStep,
    *,
    slot_a: str,
    slot_b: str,
):  # type: ignore[no-untyped-def]
    chain.mark_ctl_tx_capture_point()
    chain.mark_ctl_rx_capture_point()
    _press(chain, step.key)

    row0 = _preset_row0(step.preset)
    row1_ok = _preset_filename_windows(step.preset, slot_a, slot_b)
    lines = _wait_for_lcd(chain, lambda lcd: lcd[0] == row0 and lcd[1] in row1_ok)
    assert lines[0] == row0 and lines[1] in row1_ok
    _assert_native_filename_query_completed(
        chain,
        preset=step.preset,
        slot_a=slot_a,
        slot_b=slot_b,
    )
    return lines


def _navigate_to_preset_and_assert_native_filename(
    chain,
    *,
    preset: str,
    slot_a: str,
    slot_b: str,
):  # type: ignore[no-untyped-def]
    row0 = _preset_row0(preset)
    row1_ok = _preset_filename_windows(preset, slot_a, slot_b)
    for _ in range(8):
        if chain.lcd_lines()[0].startswith("Preset"):
            lines = _wait_for_lcd(chain, lambda lcd: lcd[0] == row0 and lcd[1] in row1_ok)
            assert lines[0] == row0 and lines[1] in row1_ok
            _assert_native_filename_cache_or_query_completed(
                chain,
                preset=preset,
                slot_a=slot_a,
                slot_b=slot_b,
                allow_query=True,
            )
            return lines
        chain.mark_ctl_tx_capture_point()
        chain.mark_ctl_rx_capture_point()
        _press(chain, "RIGHT")
    pytest.fail(f"did not navigate back to Preset; lcd={chain.lcd_lines()!r}")


def _run_full_native_chain_filename_feature(hexes: tuple[Path, Path]) -> None:
    _require_rust()
    control_hex, main_hex = hexes
    slot_a = PRESET_FILENAME_SLOT_A
    slot_b = PRESET_FILENAME_SLOT_B
    chain = _start_native_filename_chain(
        control_hex,
        main_hex,
        slot_a=slot_a,
        slot_b=slot_b,
    )

    lines = _drive_and_assert_native_preset_filename(
        chain,
        NativePresetFilenameStep("RIGHT", "A"),
        slot_a=slot_a,
        slot_b=slot_b,
    )
    assert lines == ("Preset         A", "521.4 22MG10F-v5")

    lines = _wait_for_lcd(
        chain,
        lambda lcd: lcd[0] == "Preset         A" and lcd[1] == "LX521.4 22MG10F-",
        attempts=120,
    )
    assert lines == ("Preset         A", "LX521.4 22MG10F-")


def _run_full_native_chain_preset_state_matrix(
    hexes: tuple[Path, Path],
    *,
    initial_preset: str,
    steps: tuple[NativePresetFilenameStep, ...],
) -> None:
    _require_rust()
    control_hex, main_hex = hexes
    chain = _start_native_filename_chain(
        control_hex,
        main_hex,
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
        initial_preset=initial_preset,
    )

    for step in steps:
        _drive_and_assert_native_preset_filename(
            chain,
            step,
            slot_a=PRESET_FILENAME_SLOT_A,
            slot_b=PRESET_FILENAME_SLOT_B,
        )


def _run_full_native_chain_preset_reentry_matrix(
    hexes: tuple[Path, Path],
    *,
    initial_preset: str,
    steps: tuple[NativePresetFilenameStep, ...],
    final_preset: str,
) -> None:
    _require_rust()
    control_hex, main_hex = hexes
    chain = _start_native_filename_chain(
        control_hex,
        main_hex,
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
        initial_preset=initial_preset,
    )

    for step in steps:
        _drive_and_assert_native_preset_filename(
            chain,
            step,
            slot_a=PRESET_FILENAME_SLOT_A,
            slot_b=PRESET_FILENAME_SLOT_B,
        )

    _press(chain, "RIGHT")
    input_lines = _wait_for_lcd(
        chain,
        lambda lcd: lcd == ("Input:          ", "Auto Detect     "),
        ticks=PRESET_REENTRY_POLL_TICKS,
    )
    assert input_lines == ("Input:          ", "Auto Detect     ")

    chain.mark_ctl_tx_capture_point()
    chain.mark_ctl_rx_capture_point()
    _press(chain, "LEFT")
    row0 = _preset_row0(final_preset)
    row1_ok = _preset_filename_windows(
        final_preset, PRESET_FILENAME_SLOT_A, PRESET_FILENAME_SLOT_B
    )
    lines = _wait_for_lcd(chain, lambda lcd: lcd[0] == row0 and lcd[1] in row1_ok)
    assert lines[0] == row0 and lines[1] in row1_ok
    _assert_native_filename_cache_or_query_completed(
        chain,
        preset=final_preset,
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
        allow_query=False,
    )


def _run_full_native_chain_preset_b_survives_next_menu_standby_wake(
    hexes: tuple[Path, Path],
) -> None:
    _require_rust()
    control_hex, main_hex = hexes
    chain = _start_native_filename_chain(
        control_hex,
        main_hex,
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
        initial_preset="A",
    )

    _drive_and_assert_native_preset_filename(
        chain,
        NativePresetFilenameStep("RIGHT", "A"),
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
    )
    _drive_and_assert_native_preset_filename(
        chain,
        NativePresetFilenameStep("DOWN", "B"),
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
    )

    _press(chain, "RIGHT")
    input_lines = _wait_for_lcd(chain, lambda lcd: lcd[0].startswith("Input:"))
    assert input_lines == ("Input:          ", "Auto Detect     ")

    chain.press("STBY")
    chain.step_many(80)
    assert "ZZZ" in chain.lcd_lines()[0].upper()

    chain.press("STBY")
    for _ in range(20):
        chain.step_many(100)
        if chain.is_connected() and not chain.is_waiting() and "ZZZ" not in chain.lcd_lines()[0].upper():
            break
    else:
        pytest.fail(f"chain did not wake from standby; lcd={chain.lcd_lines()!r}")

    _navigate_to_preset_and_assert_native_filename(
        chain,
        preset="B",
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
    )


def _arm_pending_filename_query(chain, query_id: int, *, deadline: int = 2) -> None:  # type: ignore[no-untyped-def]
    chain.write_reg(FNAME_FLAGS_PHYS, FNAME_PENDING_MASK)
    chain.write_reg(FNAME_ID_PHYS, query_id)
    chain.write_reg(FNAME_LEN_PHYS, 0)
    chain.write_reg(FNAME_EXPECTED_LEN_PHYS, 0)
    chain.write_reg(FNAME_DEADLINE_LO_PHYS, deadline & 0xFF)
    chain.write_reg(FNAME_DEADLINE_HI_PHYS, (deadline >> 8) & 0xFF)


def _effective_name(raw: str) -> str:
    out = []
    for ch in raw[:30]:
        code = ord(ch)
        if code < 0x20 or code >= 0x7F:
            break
        out.append(ch)
    return "".join(out)


def _start_cmd_for(requested: str, other: str) -> int:
    req = _effective_name(requested)
    oth = _effective_name(other)
    return START_TAIL if req[:16] == oth[:16] else START_PREFIX


def _reply_frames(name: str, other: str, reply_id: int) -> list[tuple[int, int]]:
    effective = _effective_name(name)
    start = _start_cmd_for(name, other)
    frames = [(start, reply_id), (LEN_CMD, reply_id ^ len(effective))]
    frames.extend((0x30 + idx, ord(ch)) for idx, ch in enumerate(effective))
    frames.append((END_CMD, reply_id))
    return frames


@dataclass
class FilenameParserModel:
    pending_id: int
    pending: bool = True
    armed: bool = False
    len_seen: bool = False
    valid: bool = False
    tail_first: bool = False
    expected_len: int | None = None
    cache: list[str] | None = None

    def __post_init__(self) -> None:
        self.cache = []

    def abort(self) -> None:
        self.pending = False
        self.armed = False
        self.len_seen = False
        self.valid = False
        self.expected_len = None
        self.cache = []

    def feed(self, cmd: int, data: int) -> None:
        if not self.pending or not (0x2D <= cmd <= 0x4E):
            return
        if cmd in (START_TAIL, START_PREFIX):
            if data != self.pending_id:
                self.armed = False
                self.len_seen = False
                self.expected_len = None
                self.cache = []
                return
            self.armed = True
            self.len_seen = False
            self.tail_first = cmd == START_TAIL
            self.expected_len = None
            self.cache = []
            return
        if not self.armed:
            return
        if cmd == LEN_CMD:
            if self.len_seen or len(self.cache or []) != 0:
                self.abort()
                return
            expected = data ^ self.pending_id
            if expected > 30:
                self.abort()
                return
            self.expected_len = expected
            self.len_seen = True
            return
        if cmd == END_CMD:
            if data != self.pending_id or not self.len_seen:
                self.abort()
                return
            if len(self.cache or []) != self.expected_len:
                self.abort()
                return
            self.valid = True
            self.pending = False
            self.armed = False
            return
        if not self.len_seen:
            self.abort()
            return
        idx = cmd - 0x30
        if idx != len(self.cache or []) or idx >= (self.expected_len or 0):
            self.abort()
            return
        if data < 0x20 or data >= 0x7F:
            self.abort()
            return
        assert self.cache is not None
        self.cache.append(chr(data))

    def expire_pending(self) -> None:
        self.abort()


@dataclass
class RawChainFilenameParserModel:
    """Tiny frame-position model for old/pre-feature echo adversarial tests."""

    pending_id: int
    frame_pos: int = 0
    route: int | None = None
    cmd: int | None = None
    filename: FilenameParserModel | None = None

    def __post_init__(self) -> None:
        self.filename = FilenameParserModel(self.pending_id)

    def feed_byte(self, byte: int) -> None:
        byte &= 0xFF
        if self.frame_pos == 0:
            if byte >= 0x80:
                self.route = byte
                self.frame_pos = 1
            return
        if self.frame_pos == 1:
            if byte >= 0x80:
                self.route = byte
                return
            self.cmd = byte
            self.frame_pos = 2
            return
        if byte >= 0x80:
            self.route = byte
            self.cmd = None
            self.frame_pos = 1
            return
        if self.route == 0xBF:
            assert self.filename is not None
            assert self.cmd is not None
            self.filename.feed(self.cmd, byte)
        self.route = None
        self.cmd = None
        self.frame_pos = 0

    def feed_bytes(self, raw: list[int]) -> FilenameParserModel:
        for byte in raw:
            self.feed_byte(byte)
        assert self.filename is not None
        return self.filename


@dataclass
class Row1RenderModel:
    """Executable model for incremental row-1 dirty/repaint behavior."""

    lcd: list[str]
    cache: str = ""
    valid: bool = False
    dirty: bool = False
    render_col: int = 0
    render_off: int = 0
    scroll_off: int = 0

    @classmethod
    def with_text(cls, text: str) -> "Row1RenderModel":
        return cls(list(text.ljust(16)[:16]))

    def mark_blank(self) -> None:
        self.valid = False
        self.render_col = 0
        self.render_off = 0
        self.dirty = True

    def mark_valid(self, cache: str, *, scroll_off: int = 0) -> None:
        self.cache = cache
        self.valid = True
        self.scroll_off = scroll_off
        self.render_col = 0
        self.render_off = scroll_off
        self.dirty = True

    def bad_mark_blank_without_cursor_reset(self) -> None:
        self.valid = False
        self.dirty = True

    def tick(self) -> None:
        if not self.dirty:
            return
        col = self.render_col
        src = self.render_off + col
        ch = " "
        if self.valid and src < len(self.cache):
            ch = self.cache[src]
        self.lcd[col] = ch
        self.render_col += 1
        if self.render_col == 16:
            self.render_col = 0
            self.dirty = False

    @property
    def row(self) -> str:
        return "".join(self.lcd)


def _parse_reply(frames: list[tuple[int, int]], pending_id: int) -> FilenameParserModel:
    parser = FilenameParserModel(pending_id)
    for cmd, data in frames:
        parser.feed(cmd, data)
    return parser


def _window(name: str, tail_first: bool) -> str:
    effective = _effective_name(name)
    if len(effective) <= 16:
        return effective.ljust(16)
    off = len(effective) - 16 if tail_first else 0
    return effective[off : off + 16]


def _row0(health_fault: bool, dsp_fault: bool, preset_b: bool) -> str:
    return "Preset" + (" " * 8) + ("*" if health_fault else " ") + (
        "!" if dsp_fault else ("B" if preset_b else "A")
    )


def _equates(path) -> dict[str, int]:
    equates: dict[str, int] = {}
    pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+(?:equ|EQU)\s+0x([0-9A-Fa-f]+)\b")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            equates[match.group(1)] = int(match.group(2), 16)
    return equates


def _label_body(text: str, label: str, next_labels: list[str] | tuple[str, ...]) -> str:
    start = re.search(rf"(?m)^{re.escape(label)}:\s*$", text)
    if not start:
        return ""
    end_positions = []
    for next_label in next_labels:
        match = re.search(rf"(?m)^{re.escape(next_label)}:\s*$", text[start.end() :])
        if match:
            end_positions.append(start.end() + match.start())
    end = min(end_positions) if end_positions else len(text)
    return text[start.start() : end]


def _filename_feature_xfail(text: str, required_label: str) -> None:
    if f"{required_label}:" not in text:
        pytest.xfail(
            f"native preset-filename implementation is not present yet: missing {required_label}"
        )


def _assert_native_labels_present(labels: dict[object, list[str]]) -> None:
    missing = [
        f"{path}:{label}"
        for path, names in labels.items()
        for label in names
        if f"{label}:" not in path.read_text(encoding="utf-8", errors="replace")
    ]
    assert not missing, "missing native labels:\n" + "\n".join(missing)


def _highest_listing_end_before_org(lst_text: str, org: int) -> int:
    highest = 0
    for line in lst_text.splitlines():
        match = re.match(r"^\s*([0-9A-Fa-f]{6})\s+(.*)$", line)
        if not match:
            continue
        addr = int(match.group(1), 16)
        if addr >= org:
            continue
        line_no = re.search(r"\s+\d{5}\s+", match.group(2))
        if line_no is None:
            continue
        object_words = re.findall(r"\b[0-9A-Fa-f]{4}\b", match.group(2)[: line_no.start()])
        if object_words:
            highest = max(highest, addr + (2 * len(object_words)))
    return highest


def _assert_listing_fits_before(lst_path, org: int, *, min_margin: int) -> int:
    lst_text = lst_path.read_text(encoding="utf-8", errors="replace")
    app_end = _highest_listing_end_before_org(lst_text, org)
    margin = org - app_end
    assert margin >= min_margin, (
        f"{lst_path.name} app ends at 0x{app_end:04X}; only {margin} bytes remain "
        f"before 0x{org:04X}, required margin {min_margin}"
    )
    return margin


def _lst_symbol_address(lst_path, symbol: str) -> int:
    text = lst_path.read_text(encoding="utf-8", errors="replace")
    patterns = [
        rf"(?m)^\s*([0-9A-Fa-f]{{6}})\s+.*\b{re.escape(symbol)}:\s*$",
        rf"(?m)^{re.escape(symbol)}\s+ADDRESS\s+([0-9A-Fa-f]{{8}})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1), 16)
    raise AssertionError(f"{symbol} not found in {lst_path}")


def _scroll_cycle_windows(name: str, *, tail_first: bool) -> list[str]:
    effective = _effective_name(name)
    if len(effective) <= 16:
        return [effective.ljust(16)]
    max_off = len(effective) - 16
    rest = max_off if tail_first else 0
    far = 0 if tail_first else max_off
    step = -1 if tail_first else 1
    offsets = [rest, rest]
    off = rest
    while off != far:
        off += step
        offsets.append(off)
    offsets.append(far)
    offsets.append(rest)
    return [effective[off : off + 16].ljust(16) for off in offsets]


def test_preset_filename_spec_keeps_v33_v172_with_feature_marker() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "Targets: paired MAIN `V3.3` + CONTROL `V1.72` filename builds",
            "feature intentionally stays on the `V3.3`/`V1.72` pair",
            "MAIN `V3.3` rev `>= 0x73`",
            "CONTROL `V1.72` rev",
            "`>= 0x39`",
            "diagnostics-identity-only `V3.3`/`V1.72` images",
            "Same-version",
            "diagnostics-identity-only images",
        ],
    )


def test_preset_filename_spec_has_pending_expiry_without_retry() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "`v172_fname_deadline_lo`",
            "`v172_fname_deadline_hi`",
            "`FNAME_PENDING_DEADLINE_RELOAD = 0x4000`",
            "Use a 16-bit saturating countdown",
            "on zero call",
            "do not set `WANT_QUERY`",
            "pending deadline blanks without retry",
        ],
    )


def test_preset_filename_spec_defines_screen_entry_settle_without_reply_retry() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "On ordinary Preset re-entry",
            "reuse the cache",
            "On observed `PRESET_BIT` change, or Preset B re-entry without a valid",
            "`FNAME_QUERY_WAIT`",
            "`FNAME_QUERY_DELAY_A = 0x3000`",
            "`FNAME_QUERY_DELAY_B = 0x4000`",
            "This is not a reply retry",
            "blank-without-requery policy",
            "at most one filename query per step",
        ],
    )


def test_preset_filename_spec_keeps_hfd_empty_names_blank_but_not_gate() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "valid when HFD/USB intentionally leaves the preset name empty",
            "use known non-empty PB1 A/B names",
            "HFD/USB empty-name validation is a separate accepted-blank",
            "Blank-name validation",
            "matching fresh query/reply",
            "`LEN(id ^ 0)`",
            "blank LCD alone is never evidence",
            "must not be used as the positive feature gate",
        ],
    )


def test_preset_filename_spec_splits_cmd26_from_cmd25_identity() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "`cmd 0x26` is a split command, not a reuse of `cmd 0x25`",
            "leaves `cmd 0x25` returning",
            "Behavioral test issues `cmd 0x25` before, during, and after",
            "`BF/4F..53`",
        ],
    )


def test_preset_filename_spec_is_multi_pb_ready_while_displaying_pb1() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "route = target == PB1 ? 0xB1 : 0xB2",
            "id = (gen << 2) | (target_bit << 1) | slot",
            "reuse the same helper and parser/cache rules",
            "V1 Preset display schedules PB1 only",
            "PB1 A=`FILE_A1`,",
            "PB2 A=`FILE_A2`",
            "LCD shows PB1 only",
            "one outstanding filename query globally",
            "PB2 tooling should return busy/no-op",
            "when the Preset screen is not active",
        ],
    )


def test_preset_filename_spec_defines_tx_arbitration_and_reserved_range() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "`chain_tx_emitted` | pass-local arbitration flag",
            "filename job runs last",
            "emits only if `chain_tx_emitted == 0`",
            "Reply `BF/2D..4E`",
            "no non-filename sender emits",
            "structural tests must guard",
            "`BF/2C` remains",
            "`BF/4F..53`",
            "Diagnostics MAIN-identity reply range",
        ],
    )


def test_preset_filename_spec_assigns_exact_main_job_ram_and_cold_clear() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "`0x2F4` | `fn_job_state`",
            "`0x2F5` | `fn_job_id`",
            "`0x2F6` | `fn_job_idx`",
            "`0x2F7` | `fn_job_src_kind`",
            "`0x2F8` | `filename_rev`",
            "`0x2F9` | `fn_job_rev`",
            "`0x2FA` | `fn_job_start_cmd`",
            "`0x2FB` | `fn_job_len`",
            "`0x2FC` | `fname_tx_gap_lo`",
            "`0x2FD` | `fname_tx_gap_hi`",
            "`0x2FE` | `chain_tx_emitted`",
            "`0x2FF` | `fn_job_tmp`",
            "V3.3 cold init must explicitly clear this whole block",
            "every runtime cold-entry path",
            "software reset",
            "post-flash/bootloader handoff",
        ],
    )


def test_preset_filename_spec_requires_v33_code_size_listing_gate() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "Current V3.3 has more room",
            "leaves about **636 bytes**",
            "MAIN-only implementation estimate",
            "**420-740**",
            "current 636-byte slack",
            "test_v33_filename_code_size_fits_before_preset_table",
            "parses the `.lst`",
            "`org 0x4C00`",
            "64-byte minimum maintenance margin",
            "`preset_table_b == 0x4C00`",
            "`control_release_metadata == 0x77B0`",
            "`bootloader_entry == 0x7800`",
            "If it fails,",
            "reclaim code first; do not move",
        ],
    )


def test_preset_filename_spec_pins_filename_rev_seqlock_order() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "read `filename_rev` before source selection / direction comparison",
            "require it to be even",
            "read `filename_rev` again immediately before storing `SEND_START`",
            "arm only if the second read is the same even value",
        ],
    )


def test_preset_filename_spec_covers_parser_faults_and_lifecycle_edges() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "Injected non-printable char data",
            "Wrong-id / injected `START` while armed",
            "Wrong-id `END` while armed",
            "old-MAIN echo must be injected at frame positions 0/1/2",
            "ids `0x2D`, `0x2E`, `0x2F`, and `0x4E`",
            "START+END without LEN",
            "PB2-only stale/lost leaves row 1 untouched",
            "PB1 stale",
            "invalidate the PB1-authoritative filename cache",
            "partial-cache burst",
            "`fname_reset_blank`",
            "`fname_reset_and_query`",
            "Off-screen deadline service is deliberately not required",
            "cache reuse",
            "ordinary menu navigation is the simple invariant",
            "Periodic `full_sync_burst`",
            "PB1-stale,",
            "PB1-lost, PB2-stale, PB2-lost",
            "IR, front-panel buttons, standby/wake",
            "volume/mute, and A/B flips",
        ],
    )


def test_preset_filename_spec_defines_exact_scroll_cycle() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "render the rest window, hold, step one column per cadence",
            "hold, snap back to the rest window, hold, repeat",
            "`REST_HOLD` targets ~2 s",
            "`FAR_HOLD` targets ~1 s",
            "any PB stale/lost, preset B",
            "RBIF/IR and RCIF traffic",
            "writes at most one",
        ],
    )


def test_preset_filename_spec_pins_parser_insertion_and_fallthrough() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "keep the existing `BF/08` DSP-fault parser",
            "`BF/08` must still update DSP fault state",
            "keep the existing `BF/4F..53` Diagnostics MAIN",
            "identity parser ahead of filename",
            "filename lower/upper misses fall through to the",
            "`v171_bf2x_case_check`",
            "cmd < 0x2D -> existing BF/2x path",
            "cmd >= 0x4F -> existing path/tail",
        ],
    )


def test_preset_filename_spec_pins_ram_non_overlap() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "Diagnostics MAIN identity",
            "physical `0x245..0x254`",
            "filename state:       physical 0x220..0x244 and 0x255..0x25C",
            "diagnostics identity: physical 0x245..0x254",
            "No filename cell may be added inside `0x245..0x254`",
        ],
    )

    filename_ranges = [range(0x220, 0x245), range(0x255, 0x25D)]
    diag_range = range(0x245, 0x255)
    overlaps = [
        (addr, block)
        for block in filename_ranges
        for addr in block
        if addr in diag_range
    ]
    assert overlaps == []

    _assert_contains_all(
        text,
        [
            "`v172_fname_expected_len`",
            "`v172_fname_scroll_div_lo`",
            "`v172_fname_scroll_div_hi`",
            "`v172_fname_render_col`",
            "`v172_fname_row0_status_snap`",
            "`v172_fname_tmp`",
            "`FNAME_LEN_SEEN`",
            "The **filename-specific clear helper** must clear only",
            "current V1.72 cold init",
            "may clear Diagnostics identity",
            "run the",
            "filename clear helper",
            "seed nonzero bytes across all three regions",
        ],
    )


def test_preset_filename_spec_requires_control_and_main_cold_init_cases() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "MAIN filename job cells are",
            "clear on every runtime cold entry",
            "POR, BOR, software reset,",
            "post-flash/bootloader handoff",
            "filename-specific clear helper",
            "`0x220..0x244` and `0x255..0x25C`",
            "preserving `0x245..0x254`",
            "must not introduce a new blind clear",
        ],
    )


def test_preset_filename_spec_pins_mixed_version_matrix() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "Mixed-version / rollback behavior",
            "filename-capable V1.72 rev >=0x39",
            "filename-capable V3.3 rev >=0x73",
            "old/pre-feature or diagnostics-only V3.3 rev <=0x72",
            "old/pre-feature or diagnostics-only V1.72 rev <=0x38",
            "report pair as pre-feature / not filename-capable",
            "accepted v1 visibility risk",
        ],
    )


def test_protocol_model_accepts_len_sealed_tail_first_burst() -> None:
    pending_id = _query_id(gen=3, target=PB1, slot=SLOT_A)
    name_a = "LX521.4 22MG10F-v5"
    name_b = "LX521.4 22MG10F-v7"

    parser = _parse_reply(_reply_frames(name_a, name_b, pending_id), pending_id)

    assert parser.valid
    assert parser.tail_first
    assert "".join(parser.cache or []) == name_a
    assert _window(name_a, tail_first=True) == "521.4 22MG10F-v5"


def test_protocol_model_accepts_prefix_first_burst_when_names_diverge_early() -> None:
    pending_id = _query_id(gen=4, target=PB1, slot=SLOT_B)
    name_a = "LX521.4 22MG10F-v5"
    name_b = "ALT521.4 22MG10F-v7"

    parser = _parse_reply(_reply_frames(name_b, name_a, pending_id), pending_id)

    assert parser.valid
    assert not parser.tail_first
    assert "".join(parser.cache or []) == name_b
    assert _window(name_b, tail_first=False) == "ALT521.4 22MG10F"


@pytest.mark.parametrize(
    (
        "gen",
        "slot_a",
        "slot_b",
        "slot",
        "expected_start",
        "expected_window",
    ),
    [
        pytest.param(
            7,
            REQUESTED_FILENAME_LONG_A,
            REQUESTED_FILENAME_SHORT_B,
            SLOT_A,
            START_PREFIX,
            "LX521 V15 L22MG ",
            id="long-a-short-b-active-a",
        ),
        pytest.param(
            8,
            REQUESTED_FILENAME_LONG_A,
            REQUESTED_FILENAME_SHORT_B,
            SLOT_B,
            START_PREFIX,
            "LX521.4 PB6v23 Q",
            id="long-a-short-b-active-b",
        ),
        pytest.param(
            9,
            REQUESTED_FILENAME_LONG_A,
            "",
            SLOT_A,
            START_PREFIX,
            "LX521 V15 L22MG ",
            id="long-a-blank-b-active-a",
        ),
        pytest.param(
            10,
            REQUESTED_FILENAME_LONG_A,
            "",
            SLOT_B,
            START_PREFIX,
            " " * 16,
            id="long-a-blank-b-active-b",
        ),
        pytest.param(
            11,
            REQUESTED_FILENAME_SHORT_B,
            "",
            SLOT_A,
            START_PREFIX,
            "LX521.4 PB6v23 Q",
            id="short-a-blank-b-active-a",
        ),
        pytest.param(
            12,
            REQUESTED_FILENAME_SHORT_B,
            "",
            SLOT_B,
            START_PREFIX,
            " " * 16,
            id="short-a-blank-b-active-b",
        ),
        pytest.param(
            13,
            "",
            REQUESTED_FILENAME_LONG_A,
            SLOT_A,
            START_PREFIX,
            " " * 16,
            id="blank-a-long-b-active-a",
        ),
        pytest.param(
            14,
            "",
            REQUESTED_FILENAME_LONG_A,
            SLOT_B,
            START_PREFIX,
            "LX521 V15 L22MG ",
            id="blank-a-long-b-active-b",
        ),
        pytest.param(
            15,
            "",
            REQUESTED_FILENAME_SHORT_B,
            SLOT_A,
            START_PREFIX,
            " " * 16,
            id="blank-a-short-b-active-a",
        ),
        pytest.param(
            16,
            "",
            REQUESTED_FILENAME_SHORT_B,
            SLOT_B,
            START_PREFIX,
            "LX521.4 PB6v23 Q",
            id="blank-a-short-b-active-b",
        ),
        pytest.param(
            17,
            "",
            "",
            SLOT_A,
            START_TAIL,
            " " * 16,
            id="blank-a-blank-b-active-a",
        ),
        pytest.param(
            18,
            "",
            "",
            SLOT_B,
            START_TAIL,
            " " * 16,
            id="blank-a-blank-b-active-b",
        ),
    ],
)
def test_requested_filename_matrix_protocol_and_render_window(
    gen: int,
    slot_a: str,
    slot_b: str,
    slot: int,
    expected_start: int,
    expected_window: str,
) -> None:
    requested = slot_a if slot == SLOT_A else slot_b
    other = slot_b if slot == SLOT_A else slot_a
    pending_id = _query_id(gen=gen, target=PB1, slot=slot)
    effective = _effective_name(requested)

    frames = _reply_frames(requested, other, pending_id)
    parser = _parse_reply(frames, pending_id)

    assert frames[0] == (expected_start, pending_id)
    assert frames[1] == (LEN_CMD, pending_id ^ len(effective))
    assert frames[-1] == (END_CMD, pending_id)
    assert parser.valid
    assert parser.expected_len == len(effective)
    assert parser.tail_first == (expected_start == START_TAIL)
    assert "".join(parser.cache or []) == effective
    assert _window(requested, tail_first=parser.tail_first) == expected_window


def test_protocol_model_empty_preset_requires_len_frame() -> None:
    pending_id = _query_id(gen=5, target=PB1, slot=SLOT_A)

    parser = _parse_reply([(START_PREFIX, pending_id), (LEN_CMD, pending_id), (END_CMD, pending_id)], pending_id)

    assert parser.valid
    assert parser.cache == []


def test_protocol_model_start_end_without_len_does_not_finalize() -> None:
    pending_id = _query_id(gen=6, target=PB1, slot=SLOT_A)

    parser = _parse_reply([(START_PREFIX, pending_id), (END_CMD, pending_id)], pending_id)

    assert not parser.valid
    assert not parser.pending


def test_protocol_model_late_len_after_char_aborts_not_reseals() -> None:
    pending_id = _query_id(gen=11)
    frames = [
        (START_PREFIX, pending_id),
        (LEN_CMD, pending_id ^ 30),
        (0x30, ord("A")),
        (LEN_CMD, pending_id ^ 1),
        (END_CMD, pending_id),
    ]

    parser = _parse_reply(frames, pending_id)

    assert not parser.valid
    assert not parser.pending
    assert not parser.armed
    assert parser.cache == []


def test_protocol_model_duplicate_len_before_chars_aborts() -> None:
    pending_id = _query_id(gen=12)
    frames = [
        (START_PREFIX, pending_id),
        (LEN_CMD, pending_id ^ 3),
        (LEN_CMD, pending_id ^ 3),
        (0x30, ord("A")),
        (0x31, ord("B")),
        (0x32, ord("C")),
        (END_CMD, pending_id),
    ]

    parser = _parse_reply(frames, pending_id)

    assert not parser.valid
    assert not parser.pending


def test_protocol_model_duplicate_len_can_not_turn_nonempty_into_empty() -> None:
    pending_id = _query_id(gen=13)
    frames = [
        (START_PREFIX, pending_id),
        (LEN_CMD, pending_id ^ 3),
        (LEN_CMD, pending_id ^ 0),
        (END_CMD, pending_id),
    ]

    parser = _parse_reply(frames, pending_id)

    assert not parser.valid
    assert not parser.pending


def test_protocol_model_len_after_full_payload_before_end_aborts() -> None:
    pending_id = _query_id(gen=14)
    frames = [
        (START_PREFIX, pending_id),
        (LEN_CMD, pending_id ^ 2),
        (0x30, ord("A")),
        (0x31, ord("B")),
        (LEN_CMD, pending_id ^ 2),
        (END_CMD, pending_id),
    ]

    parser = _parse_reply(frames, pending_id)

    assert not parser.valid
    assert not parser.pending


def test_protocol_model_corrupt_len_greater_than_30_aborts() -> None:
    pending_id = _query_id(gen=15)

    parser = _parse_reply(
        [(START_PREFIX, pending_id), (LEN_CMD, pending_id ^ 31), (END_CMD, pending_id)],
        pending_id,
    )

    assert not parser.valid
    assert not parser.pending


def test_protocol_model_dropped_last_char_fails_length_seal() -> None:
    pending_id = _query_id(gen=7, target=PB1, slot=SLOT_A)
    frames = _reply_frames("ABCDEFGHIJKLMNOPQ", "QRSTUVWXYZABCDEFG", pending_id)
    dropped_last_char = [frame for frame in frames if frame[0] != 0x30 + 16]

    parser = _parse_reply(dropped_last_char, pending_id)

    assert not parser.valid
    assert not parser.pending


def test_protocol_model_wrong_id_start_disarms_without_validating() -> None:
    pending_id = _query_id(gen=8, target=PB1, slot=SLOT_A)
    wrong_id = _query_id(gen=9, target=PB1, slot=SLOT_A)
    frames = [
        (START_PREFIX, pending_id),
        (LEN_CMD, pending_id ^ 2),
        (START_PREFIX, wrong_id),
        (0x30, ord("X")),
        (END_CMD, pending_id),
    ]

    parser = _parse_reply(frames, pending_id)

    assert not parser.valid
    assert parser.pending
    assert not parser.armed


def test_protocol_model_old_echo_adversarial_values_do_not_finalize() -> None:
    for echo in (0x2D, 0x2E, 0x2F, 0x4E):
        pending_id = echo
        parser = _parse_reply(
            [
                (START_PREFIX, pending_id),
                (END_CMD, pending_id),
            ],
            pending_id,
        )
        assert not parser.valid


@pytest.mark.parametrize("position", [0, 1, 2])
@pytest.mark.parametrize("echo", [0x2D, 0x2E, 0x2F, 0x4E])
def test_raw_protocol_model_old_echo_positions_0_1_2_do_not_finalize(
    position: int, echo: int
) -> None:
    pending_id = echo
    raw_by_position = {
        0: [echo, pending_id],
        1: [0xBF, echo, pending_id],
        2: [0xBF, START_PREFIX, echo],
    }
    parser = RawChainFilenameParserModel(pending_id).feed_bytes(raw_by_position[position])

    assert not parser.valid
    parser.expire_pending()
    assert not parser.valid
    assert not parser.pending
    assert not parser.armed


def test_raw_protocol_model_old_echo_start_end_without_len_never_finalizes() -> None:
    pending_id = _query_id(gen=16, target=PB1, slot=SLOT_A)
    raw = [
        0xBF,
        START_PREFIX,
        pending_id,
        0xBF,
        END_CMD,
        pending_id,
    ]

    parser = RawChainFilenameParserModel(pending_id).feed_bytes(raw)

    assert not parser.valid
    assert not parser.pending
    assert not parser.armed


def test_raw_protocol_model_stale_start_len_end_after_timeout_does_not_finalize() -> None:
    pending_id = _query_id(gen=17, target=PB1, slot=SLOT_A)
    model = RawChainFilenameParserModel(pending_id)
    assert model.filename is not None
    model.filename.expire_pending()

    parser = model.feed_bytes(
        [
            0xBF,
            START_PREFIX,
            pending_id,
            0xBF,
            LEN_CMD,
            pending_id ^ 0,
            0xBF,
            END_CMD,
            pending_id,
        ]
    )

    assert not parser.valid
    assert not parser.pending
    assert not parser.armed


@pytest.mark.parametrize(
    "prefix",
    [
        [],
        [0x00],
        [0xBF, 0x00],
        [0xBF, START_PREFIX, 0x00],
        [0xC0],
    ],
)
def test_raw_protocol_model_old_echo_multibyte_start_len_end_streams_do_not_finalize(
    prefix: list[int],
) -> None:
    pending_id = START_PREFIX
    synthetic_old_echo = [
        START_PREFIX,
        pending_id,
        LEN_CMD,
        pending_id ^ 0,
        END_CMD,
        pending_id,
    ]

    parser = RawChainFilenameParserModel(pending_id).feed_bytes(
        prefix + synthetic_old_echo
    )

    assert not parser.valid
    parser.expire_pending()
    assert not parser.valid
    assert not parser.pending
    assert not parser.armed


def test_raw_protocol_model_wrong_generation_start_len_end_does_not_finalize() -> None:
    pending_id = _query_id(gen=18, target=PB1, slot=SLOT_A)
    stale_id = _query_id(gen=19, target=PB1, slot=SLOT_A)
    raw = [
        0xBF,
        START_PREFIX,
        stale_id,
        0xBF,
        LEN_CMD,
        stale_id ^ 0,
        0xBF,
        END_CMD,
        stale_id,
    ]

    parser = RawChainFilenameParserModel(pending_id).feed_bytes(raw)

    assert not parser.valid
    assert parser.pending
    assert not parser.armed


def test_scroll_model_static_and_exactly_sixteen_names_do_not_scroll() -> None:
    assert _scroll_cycle_windows("", tail_first=False) == [" " * 16]
    assert _scroll_cycle_windows("SHORT", tail_first=False) == ["SHORT".ljust(16)]
    assert _scroll_cycle_windows("1234567890ABCDEF", tail_first=False) == [
        "1234567890ABCDEF"
    ]
    assert _scroll_cycle_windows("1234567890ABCDEF", tail_first=True) == [
        "1234567890ABCDEF"
    ]


def test_scroll_model_prefix_first_holds_steps_to_tail_and_snaps_back() -> None:
    windows = _scroll_cycle_windows("ABCDEFGHIJKLMNOPQ", tail_first=False)

    assert windows[0] == "ABCDEFGHIJKLMNOP"
    assert windows[1] == "ABCDEFGHIJKLMNOP"
    assert windows[2] == "BCDEFGHIJKLMNOPQ"
    assert windows[-2] == "BCDEFGHIJKLMNOPQ"
    assert windows[-1] == "ABCDEFGHIJKLMNOP"


def test_scroll_model_tail_first_holds_steps_to_head_and_snaps_back() -> None:
    windows = _scroll_cycle_windows("LX521.4 22MG10F-v5", tail_first=True)

    assert windows[0] == "521.4 22MG10F-v5"
    assert windows[1] == "521.4 22MG10F-v5"
    assert windows[2] == "X521.4 22MG10F-v"
    assert windows[-2] == "LX521.4 22MG10F-"
    assert windows[-1] == "521.4 22MG10F-v5"


def test_display_model_is_pb1_authoritative_with_mismatched_pb2_names() -> None:
    pb1_name = "FILE_A1"
    pb2_name = "FILE_A2"
    pending_id = _query_id(gen=10, target=PB1, slot=SLOT_A)

    parser = _parse_reply(_reply_frames(pb1_name, "FILE_B1", pending_id), pending_id)

    assert parser.valid
    assert "".join(parser.cache or []) == pb1_name
    assert "".join(parser.cache or []) != pb2_name


def test_row0_model_gives_dsp_fault_precedence_over_preset_letter() -> None:
    assert _row0(health_fault=False, dsp_fault=False, preset_b=False) == "Preset         A"
    assert _row0(health_fault=True, dsp_fault=False, preset_b=True) == "Preset        *B"
    assert _row0(health_fault=False, dsp_fault=True, preset_b=False) == "Preset         !"
    assert _row0(health_fault=True, dsp_fault=True, preset_b=True) == "Preset        *!"


def test_row1_dirty_model_abort_restarts_blank_from_col0_after_partial_repaint() -> None:
    renderer = Row1RenderModel.with_text("OLD-FILENAME-123")
    renderer.mark_valid("NEW-FILENAME-XYZ", scroll_off=0)
    for _ in range(5):
        renderer.tick()
    assert renderer.render_col == 5
    assert renderer.row.startswith("NEW-F")

    renderer.mark_blank()

    assert renderer.dirty
    assert renderer.render_col == 0
    assert renderer.render_off == 0
    renderer.tick()
    assert renderer.row[0] == " "
    assert renderer.row[5] != " "


def test_row1_dirty_model_valid_end_restarts_from_col0_after_partial_blank() -> None:
    renderer = Row1RenderModel.with_text("STALE-ROW-TEXT")
    renderer.mark_blank()
    for _ in range(7):
        renderer.tick()
    assert renderer.render_col == 7
    assert renderer.row[:7] == " " * 7

    renderer.mark_valid("LX521.4 22MG10F-v5", scroll_off=2)

    assert renderer.render_col == 0
    assert renderer.render_off == 2
    renderer.tick()
    assert renderer.row[0] == "5"
    assert renderer.row[7] != " "


def test_row1_dirty_model_bad_abort_without_cursor_reset_leaves_stale_prefix() -> None:
    renderer = Row1RenderModel.with_text("OLD-FILENAME-123")
    renderer.mark_valid("NEW-FILENAME-XYZ", scroll_off=0)
    for _ in range(6):
        renderer.tick()

    renderer.bad_mark_blank_without_cursor_reset()
    for _ in range(10):
        renderer.tick()

    assert renderer.row.startswith("NEW-FI")
    assert renderer.row.endswith(" " * 10)


def test_spec_defines_incremental_row1_render_and_tradeoffs() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "Visible row-1 **settled target states**",
            "transient",
            "partial old/new rows or partial blank rows are allowed",
            "settled target above must be reached within the `<20 ms`",
            "The renderer is a one-character-at-a-time row writer",
            "`v172_fname_render_col` is the next LCD column",
            "`v172_fname_render_off` snapshots the source offset",
            "clears `FNAME_ROW_DIRTY` only after column",
            "Hard rule: every path that sets `FNAME_ROW_DIRTY`",
            "`fname_mark_row_dirty_blank`",
            "`fname_mark_row_dirty_valid`",
            "`v172_fname_render_col` to 0",
            "setting `v172_fname_render_off` to the desired",
            "reset `render_col`/`render_off` first",
            "then set `FNAME_ROW_DIRTY`",
            "leave stale characters from the old row",
            "Full-row redraw vs. incremental render tradeoff",
            "Decision: **use incremental one-char render**",
            "Full 16-char redraw in one service pass",
            "Incremental one-char render",
            "Required implementation",
            "estimated code",
            "~150-230 bytes",
            "`render_col` + `render_off`",
            "must be <20 ms worst-case",
            "accepted for V1.72",
            "must not remain as a settled state",
            "required incremental row writer",
            "**LCD write safety:**",
            "restore the **prior** GIE state",
            "save",
            "`INTCON.GIE`",
            "unconditional `bsf INTCON,GIE`",
        ],
    )


def test_spec_defines_row0_two_cell_patch_scenarios() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "`v172_fname_row0_status_snap` encoding",
            "bit 0 | last col-14 health glyph",
            "bit 1 | last preset letter source",
            "bit 2 | last DSP-fault status",
            "bits 3..6 | reserved",
            "bit 7 | Preset row-0 entry gate",
            "two bounded",
            "single-cell updates",
            "This single-snap approach is sufficient even when both cells change",
            "**Scheduler contract:** a row-0 patch consumes",
            "write budget",
            "Non-LCD work still runs first",
            "There must not be an early return",
            "writes at most one LCD cell",
            "row-0 patch first",
            "row-1 filename character",
            "PB2 becomes stale/lost",
            "PB1 becomes lost/reboots",
            "DSP fault appears on preset B",
            "health and DSP fault change together",
            "`Preset        *!`",
        ],
    )


def test_spec_requires_app_resident_identity_for_deployment_validation() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "No new formal artifact schema is required",
            "a simple log",
            "evidence, not a new compatibility contract",
            "MAIN USB/EEPROM revision bytes are not",
            "authoritative for filename capability",
            "app-resident MAIN identity",
            "Diagnostics identity query `cmd 0x25`",
            "`BF/4F..53` reply",
            "PB1 is the MAIN physically connected to CONTROL/LCD",
            "Do not infer PB1/PB2 from host USB enumeration order",
            "**Mandatory PB1 LCD behavior gate:**",
            "**Optional paired audit:**",
            "PB2 old/mismatched state is warning-only",
            "`[0xB1, 0x25, id]`",
            "`[0xB2,0x25,id]`",
            "`BF/4F id`, `BF/50 0x03`, `BF/51 0x03`, `BF/52 rev_hi`",
            "USB/HID version strings, EEPROM byte `0x82`, and HFD-visible metadata",
            "informational only",
        ],
    )


def test_spec_defines_hfd_active_ram_vs_inactive_eeprom_validation() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "HFD/USB upload validation",
            "should separate active RAM from inactive",
            "active-slot rename validation should force a fresh query",
            "expect the active RAM name",
            "inactive",
            "wait for EEPROM",
            "EEPROM persistence/readback",
        ],
    )


def test_spec_lists_named_implementation_tests_for_reviewed_gaps() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "`test_v172_fname_parser_duplicate_len_aborts`",
            "`test_v172_fname_parser_late_len_after_char_aborts`",
            "`test_v172_fname_parser_corrupt_len_aborts`",
            "`test_v172_fname_parser_old_echo_positions_0_1_2_do_not_finalize`",
            "`test_raw_protocol_model_old_echo_multibyte_start_len_end_streams_do_not_finalize`",
            "`test_v172_fname_parser_interleaved_bf08_identity_diag_preserved`",
            "`test_v172_fname_cold_init_clears_filename_state_preserves_diag_identity`",
            "`test_v33_fname_cold_entry_clears_job_state_after_software_reset`",
            "`test_v172_fname_ram_equates_do_not_overlap_diag_identity`",
            "`test_v33_filename_code_size_fits_before_preset_table`",
            "`test_v172_filename_code_size_fits_before_bootloader`",
            "`test_v33_filename_chain_tx_emitted_coverage_all_chain_senders`",
            "`test_v33_filename_rev_writer_hooks_cover_all_filename_mutators`",
            "`test_v33_native_filename_char_emit_stages_cmd_after_source_read`",
            "`test_v33_reserved_bf_2d_4e_only_filename_emitters`",
            "`test_v172_fname_row1_incremental_render_writes_one_char_per_tick`",
            "`test_v172_fname_row1_render_tolerates_ir_rcif_during_pending_valid_scrolling`",
            "`test_v172_preset_row0_live_patch_health_fault_preset_scenarios`",
            "`test_v172_v33_deployment_uses_cmd25_app_identity_not_usb_eeprom_rev`",
            "`test_preset_filename_spec_requires_cmd25_app_resident_identity_for_flash_validation`",
            "`test_preset_filename_spec_rejects_usb_eeprom_revision_as_authoritative_marker`",
            "`test_preset_filename_spec_documents_pb1_lcd_authority_and_pb2_flash_validation`",
            "`test_preset_filename_spec_requires_blank_name_chain_evidence`",
            "`test_preset_filename_spec_defines_hfd_active_ram_vs_inactive_eeprom_validation`",
            "`test_v172_v33_pb1_authoritative_lcd_with_pb2_mismatch`",
            "`test_v172_v33_full_chain_blank_name_requires_fresh_start_len_end_evidence`",
            "`test_v172_v33_full_native_chain_filename_preset_state_matrix`",
            "`test_v172_v33_full_native_chain_filename_preset_reentry_matrix`",
            "`test_v172_v33_full_native_chain_preset_b_survives_next_menu_standby_wake`",
            "`test_v172_native_parser_old_echo_multiframe_start_len_end_do_not_finalize`",
            "`test_v172_native_lcd_row1_abort_valid_end_restart_render_cursor`",
            "`test_v172_native_row0_patch_consumes_lcd_budget_only`",
            "`test_v172_v33_native_chain_tail_first_prefix_first_blank_mismatch_cases`",
            "`test_v172_v33_native_chain_mixed_old_new_peers_do_not_finalize`",
        ],
    )


def test_spec_requires_full_native_chain_coverage_for_filename_feature() -> None:
    text = _spec_text()

    _assert_contains_all(
        text,
        [
            "End-to-end full native chain",
            "simulate flashing/seeding preset filenames independently for PB1 and",
            "prefix-first names",
            "tail-first names with shared first 16 chars",
            "valid blank A/B presets",
            "DSP fault `!`",
            "row-0 `*` health refresh",
            "PB1/PB2 mismatch",
        ],
    )


def test_v33_filename_code_size_fits_before_preset_table() -> None:
    text = V33_MAIN_ASM.read_text(encoding="utf-8")
    _filename_feature_xfail(text, "cmd26_filename_query_handler")
    assert V33_MAIN_LST.exists(), f"missing listing: {V33_MAIN_LST}"
    _assert_listing_fits_before(V33_MAIN_LST, 0x4C00, min_margin=64)


def test_v172_filename_code_size_fits_before_bootloader() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8")
    _filename_feature_xfail(text, "v172_fname_case_check")
    assert V172_CONTROL_LST.exists(), f"missing listing: {V172_CONTROL_LST}"
    _assert_listing_fits_before(V172_CONTROL_LST, 0x77B0, min_margin=64)


def test_v33_v172_fixed_layout_labels_are_pinned() -> None:
    assert V33_MAIN_LST.exists(), f"missing listing: {V33_MAIN_LST}"
    assert V172_CONTROL_LST.exists(), f"missing listing: {V172_CONTROL_LST}"
    assert _lst_symbol_address(V33_MAIN_LST, "preset_table_b") == 0x4C00
    assert _lst_symbol_address(V172_CONTROL_LST, "control_release_metadata") == 0x77B0
    assert _lst_symbol_address(V172_CONTROL_LST, "bootloader_entry") == 0x7800


def test_v34_v173_refactoring_layout_labels_are_pinned() -> None:
    assert V34_MAIN_LST.exists(), f"missing listing: {V34_MAIN_LST}"
    assert V173_CONTROL_LST.exists(), f"missing listing: {V173_CONTROL_LST}"
    assert _lst_symbol_address(V34_MAIN_LST, "preset_table_b") == 0x4C00
    assert _lst_symbol_address(V173_CONTROL_LST, "control_release_metadata") == 0x77B0
    assert _lst_symbol_address(V173_CONTROL_LST, "bootloader_entry") == 0x7800
    # MAIN floor matches the canonical headroom gate in
    # test_v34_v173_refactoring_contracts.py (ratcheted 96 -> 24 on
    # 2026-06-12 for the SRC/DSP forensic counters; see the rationale there).
    _assert_listing_fits_before(V34_MAIN_LST, 0x4C00, min_margin=24)
    _assert_listing_fits_before(V173_CONTROL_LST, 0x77B0, min_margin=64)


def test_v172_fname_ram_equates_do_not_overlap_diag_identity_native() -> None:
    ram = _equates(V17_CONTROL_RAM_INC)
    if "v172_fname_cache" not in ram:
        pytest.xfail("native CONTROL filename RAM equates are not present yet")

    def phys(value: int) -> int:
        return 0x200 + value if value < 0x100 else value

    filename_symbols = [name for name in ram if name.startswith("v172_fname_")]
    diag_identity = set(range(0x245, 0x255))
    overlaps = {
        name: phys(ram[name])
        for name in filename_symbols
        if phys(ram[name]) in diag_identity
    }
    assert not overlaps
    assert phys(ram["v172_fname_cache"]) == 0x220
    assert phys(ram["v172_fname_row0_status_snap"]) == 0x25B
    assert phys(ram["v172_fname_tmp"]) == 0x25C


def test_v33_fname_ram_equates_do_not_overlap_diag_recovery_cells() -> None:
    ram = _equates(V33_MAIN_ASM.parent / "dlcp_main_ram.inc")
    if "fn_job_state" not in ram:
        pytest.xfail("native MAIN filename RAM equates are not present yet")

    expected = {
        "fn_job_state": 0x2F4,
        "fn_job_id": 0x2F5,
        "fn_job_idx": 0x2F6,
        "fn_job_src_kind": 0x2F7,
        "filename_rev": 0x2F8,
        "fn_job_rev": 0x2F9,
        "fn_job_start_cmd": 0x2FA,
        "fn_job_len": 0x2FB,
        "fname_tx_gap_lo": 0x2FC,
        "fname_tx_gap_hi": 0x2FD,
        "chain_tx_emitted": 0x2FE,
        "fn_job_tmp": 0x2FF,
    }
    for symbol, addr in expected.items():
        assert ram.get(symbol) == addr
    reserved = set(range(0x2E5, 0x2F4))
    assert not {symbol: ram[symbol] for symbol in expected if ram[symbol] in reserved}


def test_v33_an0_hysteresis_monitor_banks_delay_counter_before_uart_ring_alias() -> None:
    text = V33_MAIN_ASM.read_text(encoding="utf-8")
    body = _label_body(text, "an0_hysteresis_monitor", ["main_core_service_41b6"])
    first_delay_touch = body.index("an0_delay_b0")
    prefix = body[:first_delay_touch]
    assert "movlb       0x0" in prefix, (
        "an0_hysteresis_monitor must assert BSR=0 before touching an0_delay_b0; "
        "with BSR=2 the delay counter aliases the MAIN UART RX ring at 0x2A1"
    )


def test_v33_filename_chain_tx_emitted_coverage_all_chain_senders() -> None:
    text = V33_MAIN_ASM.read_text(encoding="utf-8")
    _filename_feature_xfail(text, "filename_reply_job_service")
    required_bodies = {
        "main_uart_service_1be6": ["send_status_burst"],
        "send_status_burst": ["send_status_burst_preamble"],
        "send_dsp_fault_status": ["cmd21_diag_query_handler"],
        "cmd21_diag_query_handler": ["cmd22_reset_flags_query_handler"],
        "cmd22_reset_flags_query_handler": ["cmd23_health_query_handler"],
        "cmd23_health_query_handler": ["cmd25_identity_query_handler"],
        "cmd25_identity_query_handler": ["filename_reply_job_service", "org 0x4C00"],
        "report_cmd29_status": ["send_dsp_fault_status"],
        "filename_reply_job_service": ["org 0x4C00"],
    }
    missing = []
    for label, next_labels in required_bodies.items():
        body = _label_body(text, label, next_labels)
        if "chain_tx_emitted" not in body:
            missing.append(label)
    assert not missing, "senders missing chain_tx_emitted coverage: " + ", ".join(missing)


def test_v33_filename_rev_writer_hooks_cover_all_filename_mutators() -> None:
    text = V33_MAIN_ASM.read_text(encoding="utf-8")
    if "filename_rev" not in text:
        pytest.xfail("native MAIN filename_rev equate/hooks are not present yet")
    required_regions = {
        "preset_persist_filename": ["preset_load_filename"],
        "preset_load_filename": ["preset_job_service"],
        "preset_job_apply": ["preset_job_done"],
        "btg active_flags": ["preset_job_apply"],
        "hid filename write": ["filename_dirty_flags", "usb_filename_xact_pending"],
    }
    missing = []
    for label, bounds in required_regions.items():
        if label == "hid filename write":
            start = min(text.find(marker) for marker in bounds if text.find(marker) >= 0)
            body = text[start : start + 900]
        elif label == "btg active_flags":
            match = re.search(r"\bbtg\s+active_flags(?:_acc|_b0)?\b", text)
            start = match.start() if match else -1
            body = text[start : start + 900] if start >= 0 else ""
        else:
            body = _label_body(text, label, bounds)
        if "filename_rev" not in body:
            missing.append(label)
    assert not missing, "filename mutators missing filename_rev hooks: " + ", ".join(missing)


def test_v33_native_cmd26_computes_auto_scroll_direction() -> None:
    text = V33_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    _filename_feature_xfail(text, "cmd26_filename_query_handler")
    body = _label_body(text, "cmd26_filename_query_handler", ["filename_read_source_at_w"])
    _assert_contains_all(
        body,
        [
            "cmd26_filename_compare_prefix16",
            "cmd26_filename_compare_loop",
            "cpfseq      fname_tx_gap_lo",
            "movlw       0x2E",
            "movwf       fn_job_start_cmd",
            "movlw       0x2F",
        ],
    )


def test_v33_native_filename_char_emit_stages_cmd_after_source_read() -> None:
    text = V33_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "filename_reply_send_char", ["filename_reply_send_end"])

    read_pos = body.index("filename_read_source_at_w")
    data_stage_pos = body.index("movwf       stock_00E_acc")
    bank_pos = body.index("movlb       0x02", data_stage_pos)
    cmd_base_pos = body.index("movlw       0x30")
    cmd_stage_pos = body.index("movwf       stock_00D_acc")
    emit_pos = body.index("filename_emit_frame")

    assert read_pos < data_stage_pos < bank_pos < cmd_base_pos < cmd_stage_pos < emit_pos


def test_v33_reserved_bf_2d_4e_only_filename_emitters() -> None:
    text = V33_MAIN_ASM.read_text(encoding="utf-8")
    _filename_feature_xfail(text, "filename_reply_job_service")
    label_pattern = re.compile(r"(?m)^([A-Za-z_][A-Za-z0-9_]*):\s*$")
    labels = list(label_pattern.finditer(text))
    literal_bf_frame = re.compile(
        r"\bmovlw\s+0xBF\b[^\n]*\n"
        r"\s*(?:r?call|call)\s+uart_tx_byte_blocking[^\n]*\n"
        r"\s*movlw\s+0x([0-9A-Fa-f]{2})\b[^\n]*\n"
        r"\s*(?:r?call|call)\s+uart_tx_byte_blocking\b",
        re.MULTILINE,
    )
    offenders: list[tuple[str, int]] = []
    for idx, match in enumerate(labels):
        label = match.group(1)
        body_end = labels[idx + 1].start() if idx + 1 < len(labels) else len(text)
        body = text[match.start() : body_end]
        for cmd_match in literal_bf_frame.finditer(body):
            cmd = int(cmd_match.group(1), 16)
            if 0x2D <= cmd <= 0x4E and not label.startswith("filename_"):
                offenders.append((label, cmd))
    assert not offenders


def test_v172_fname_parser_order_preserves_bf08_identity_and_diag_native() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8")
    _filename_feature_xfail(text, "v172_fname_case_check")
    bf08 = text.find("v171_bf08_case_check:")
    identity = text.find("v172_bf4f_identity_case_check:")
    fname = text.find("v172_fname_case_check:")
    bf2x = text.find("v171_bf2x_case_check:")
    assert -1 not in (bf08, identity, fname, bf2x)
    assert bf08 < identity < fname < bf2x


def test_v172_native_filename_clean_burst_sets_valid_len_cache() -> None:
    _assert_native_labels_present(
        {
            V172_CONTROL_ASM: [
                "v172_fname_case_check",
                "fname_not_len",
                "fname_char",
            ]
        }
    )
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "v172_fname_case_check", ["v171_bf2x_case_check"])
    _assert_contains_all(
        body,
        [
            "FNAME_PENDING",
            "FNAME_ARMED",
            "FNAME_LEN_SEEN",
            "FNAME_VALID",
            "v172_fname_expected_len",
            "lfsr    0x0, v172_fname_cache_b2_phys",
            "movwf   INDF0",
            "fname_mark_row_dirty_valid",
        ],
    )


def test_v172_native_filename_late_len_after_char_aborts_and_blanks() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "v172_fname_case_check", ["v171_bf2x_case_check"])
    assert "fname_abort:" in body
    assert "fname_reset_blank" in body
    _assert_contains_all(body, ["movf    v172_fname_len_b2, F", "bnz     fname_abort"])


def test_v172_native_preset_draw_delays_first_filename_query_without_reply_retry() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    helper = _label_body(text, "fname_reset_and_delay_query", ["v172_preset_filename_service"])
    deadline = _label_body(text, "v172_fname_deadline_service", ["v172_fname_scroll_service"])
    abort = _label_body(text, "fname_abort", ["fname_disarm"])

    _assert_contains_all(
        text,
        [
            "fname_reset_and_delay_query",
            "FNAME_QUERY_WAIT",
            "FNAME_QUERY_DELAY_A_HI",
            "FNAME_QUERY_DELAY_B_HI",
            "FNAME_QUERY_DELAY_LO",
            "Re-entry and slot-change redraws use one delayed first query.",
            "v171_prs_screen_draw_delayed_query",
        ],
    )
    _assert_contains_all(
        helper,
        [
            "fname_reset_blank",
            "FNAME_QUERY_WAIT",
            "FNAME_QUERY_DELAY_LO",
            "FNAME_QUERY_DELAY_A_HI",
            "FNAME_QUERY_DELAY_B_HI",
        ],
    )
    _assert_contains_all(
        deadline,
        [
            "v172_fname_query_delay_service",
            "bcf     v172_fname_flags_b2, FNAME_QUERY_WAIT",
            "bsf     v172_fname_flags_b2, FNAME_WANT_QUERY",
        ],
    )
    _assert_contains_all(abort, ["call    fname_reset_blank"])
    assert "FNAME_RETRY_ON_ABORT" not in text
    assert "fname_reset_blank_maybe_retry" not in text


def test_v172_filename_acquisition_gates_background_health_polling_native() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    delay_expire = _label_body(
        text,
        "v172_fname_query_delay_expire",
        ["v172_fname_query_delay_cancel"],
    )
    health_tick = _label_body(
        text,
        "v171_health_tick",
        ["v171_health_pending_timeout"],
    )

    _assert_contains_all(
        delay_expire,
        [
            "v171_health_flags",
            "V171_HEALTH_FLAG_PENDING",
            "return  0x0",
            "bcf     v172_fname_flags_b2, FNAME_QUERY_WAIT",
            "bsf     v172_fname_flags_b2, FNAME_WANT_QUERY",
        ],
    )
    _assert_contains_all(
        health_tick,
        [
            "btfsc   v171_health_flags_b1, V171_HEALTH_FLAG_PENDING",
            "bra     v171_health_pending_timeout",
            "FNAME_QUERY_WAIT",
            "FNAME_PENDING",
            "FNAME_WANT_QUERY",
            "call    v171_health_send_query",
        ],
    )
    pending_check = health_tick.find("btfsc   v171_health_flags_b1, V171_HEALTH_FLAG_PENDING")
    query_wait_check = health_tick.find("FNAME_QUERY_WAIT")
    send_query = health_tick.find("call    v171_health_send_query")
    assert 0 <= pending_check < query_wait_check < send_query


def test_v172_native_filename_duplicate_len_aborts_and_blanks() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "v172_fname_case_check", ["v171_bf2x_case_check"])
    _assert_contains_all(
        body,
        ["btfsc   v172_fname_flags_b2, FNAME_LEN_SEEN", "bra     fname_abort"],
    )


def test_v172_native_filename_len_greater_than_30_aborts() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "v172_fname_case_check", ["v171_bf2x_case_check"])
    _assert_contains_all(
        body,
        ["movlw   0x1F", "cpfslt  v172_fname_expected_len", "bra     fname_abort"],
    )


def test_v172_native_filename_wrong_id_start_disarms_keeps_pending() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "fname_disarm", ["fname_exit"])
    _assert_contains_all(
        body,
        ["bcf     v172_fname_flags_b2, FNAME_ARMED", "bcf     v172_fname_flags_b2, FNAME_LEN_SEEN"],
    )
    assert "bcf     v172_fname_flags_b2, FNAME_PENDING" not in body


def test_v172_native_parser_old_echo_multiframe_start_len_end_do_not_finalize() -> None:
    _assert_native_labels_present(
        {V172_CONTROL_ASM: ["v172_fname_case_check", "fname_not_len", "fname_abort", "fname_exit"]}
    )
    test_raw_protocol_model_old_echo_multibyte_start_len_end_streams_do_not_finalize([])


def test_v172_fname_dirty_paths_reset_render_cursor_native() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    label_matches = list(re.finditer(r"(?m)^([A-Za-z_][A-Za-z0-9_]*):\s*$", text))
    dirty_writers = []
    for idx, match in enumerate(label_matches):
        label = match.group(1)
        end = label_matches[idx + 1].start() if idx + 1 < len(label_matches) else len(text)
        if re.search(r"\bbsf\s+v172_fname_flags(?:_b2)?,\s*FNAME_ROW_DIRTY\b", text[match.start() : end]):
            dirty_writers.append(label)
    assert set(dirty_writers) <= {
        "fname_mark_row_dirty_blank",
        "fname_mark_row_dirty_valid",
    }


def test_v172_native_lcd_row1_abort_valid_end_restart_render_cursor() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    blank = _label_body(text, "fname_mark_row_dirty_blank", ["fname_mark_row_dirty_valid"])
    valid = _label_body(text, "fname_mark_row_dirty_valid", ["fname_reset_blank"])
    _assert_contains_all(blank, ["clrf    v172_fname_render_col", "clrf    v172_fname_render_off", "FNAME_ROW_DIRTY"])
    _assert_contains_all(valid, ["clrf    v172_fname_render_col", "movwf   v172_fname_render_off", "FNAME_ROW_DIRTY"])


def test_v172_fname_preset_exit_cancels_pending_or_armed_query_native() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "v171_preset_exit_check", ["v172_preset_status_patch_service"])
    assert "fname_reset_blank" in body


def test_v172_fname_preset_entry_blanks_old_active_row_native() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "v171_prs_screen_draw", ["v171_preset_loop"])
    _assert_contains_all(body, ["v172_preset_blank_row1_entry", "fname_reset_and_query"])
    assert "Active:" not in body


def test_v172_fname_row1_incremental_render_writes_one_char_per_tick_native() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "v172_fname_row1_render_service", ["v171_diag_send_runtime_query"])
    assert body.count("lcd_char_write") == 1
    _assert_contains_all(body, ["incf    v172_fname_render_col_b2", "movlw   0x10", "bcf     v172_fname_flags_b2, FNAME_ROW_DIRTY"])


def test_v172_preset_row0_live_patch_health_fault_preset_scenarios_native() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "v172_preset_status_patch_service", ["v172_fname_row1_render_service"])
    _assert_contains_all(
        body,
        ["V171_HEALTH_STALE_AGE", "DSP_FAULT_BIT", "PRESET_BIT", "0x8E", "0x8F", "'*'", "'!'", "'A'", "'B'"],
    )


def test_v172_native_row0_patch_consumes_lcd_budget_only() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "v172_preset_filename_service", ["v172_fname_query_service"])
    assert body.find("v172_fname_query_service") < body.find("v172_preset_status_patch_service")
    assert body.find("v172_fname_deadline_service") < body.find("v172_preset_status_patch_service")
    assert body.find("v172_preset_status_patch_service") < body.find("v172_fname_row1_render_service")


def test_v172_lcd_critical_section_restores_prior_gie_native() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(
        text,
        "v171_health_patch_suffix_top_level",
        ["v171_health_diag_check_stale"],
    )
    _assert_contains_all(
        body,
        [
            "movlb   0x01",
            "clrf    v171_health_age_tmp",
            "btfsc   INTCON, GIE",
            "incf    v171_health_age_tmp",
            "movlb   0x00",
            "bcf     INTCON, GIE",
            "movf    v171_health_age_tmp",
            "bz      v171_health_patch_gie_restored",
            "bsf     INTCON, GIE",
        ],
    )
    assert body.find("movlb   0x01") < body.find("clrf    v171_health_age_tmp")
    assert body.find("incf    v171_health_age_tmp") < body.find("movlb   0x00")
    assert body.find("movlb   0x00") < body.find("bcf     INTCON, GIE")
    assert body.find("movf    v171_health_age_tmp") < body.find("bsf     INTCON, GIE")


@pytest.mark.slow
def test_v172_v33_full_native_chain_filename_feature(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    _run_full_native_chain_filename_feature(v172_v33_filename_hexes)


@pytest.mark.slow
def test_v173_v34_full_native_chain_filename_feature(
    v173_v34_filename_hexes: tuple[Path, Path],
) -> None:
    _run_full_native_chain_filename_feature(v173_v34_filename_hexes)


@pytest.mark.slow
def test_v172_v33_full_native_chain_requested_filename_pair(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    _require_rust()
    control_hex, main_hex = v172_v33_filename_hexes
    slot_a = REQUESTED_FILENAME_LONG_A
    slot_b = REQUESTED_FILENAME_SHORT_B
    chain = _start_native_filename_chain(
        control_hex,
        main_hex,
        slot_a=slot_a,
        slot_b=slot_b,
    )

    lines = _drive_and_assert_native_preset_filename(
        chain,
        NativePresetFilenameStep("RIGHT", "A"),
        slot_a=slot_a,
        slot_b=slot_b,
    )
    assert lines == ("Preset         A", "LX521 V15 L22MG ")


@pytest.mark.slow
@pytest.mark.parametrize(
    ("initial_preset", "steps"),
    PRESET_STATE_MATRIX_CASES,
)
def test_v172_v33_full_native_chain_filename_preset_state_matrix(
    v172_v33_filename_hexes: tuple[Path, Path],
    initial_preset: str,
    steps: tuple[NativePresetFilenameStep, ...],
) -> None:
    _run_full_native_chain_preset_state_matrix(
        v172_v33_filename_hexes,
        initial_preset=initial_preset,
        steps=steps,
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    ("initial_preset", "steps"),
    PRESET_STATE_MATRIX_CASES,
)
def test_v173_v34_full_native_chain_filename_preset_state_matrix(
    v173_v34_filename_hexes: tuple[Path, Path],
    initial_preset: str,
    steps: tuple[NativePresetFilenameStep, ...],
) -> None:
    _run_full_native_chain_preset_state_matrix(
        v173_v34_filename_hexes,
        initial_preset=initial_preset,
        steps=steps,
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    ("initial_preset", "steps", "final_preset"),
    PRESET_REENTRY_MATRIX_CASES,
)
def test_v172_v33_full_native_chain_filename_preset_reentry_matrix(
    v172_v33_filename_hexes: tuple[Path, Path],
    initial_preset: str,
    steps: tuple[NativePresetFilenameStep, ...],
    final_preset: str,
) -> None:
    _run_full_native_chain_preset_reentry_matrix(
        v172_v33_filename_hexes,
        initial_preset=initial_preset,
        steps=steps,
        final_preset=final_preset,
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    ("initial_preset", "steps", "final_preset"),
    PRESET_REENTRY_MATRIX_CASES,
)
def test_v173_v34_full_native_chain_filename_preset_reentry_matrix(
    v173_v34_filename_hexes: tuple[Path, Path],
    initial_preset: str,
    steps: tuple[NativePresetFilenameStep, ...],
    final_preset: str,
) -> None:
    _run_full_native_chain_preset_reentry_matrix(
        v173_v34_filename_hexes,
        initial_preset=initial_preset,
        steps=steps,
        final_preset=final_preset,
    )


@pytest.mark.slow
def test_v172_v33_full_native_chain_preset_reentry_immediate_left_never_blanks_row0(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    _drive_b_a_b_to_input_and_trace_immediate_left(v172_v33_filename_hexes)


@pytest.mark.slow
def test_v173_v34_full_native_chain_preset_reentry_immediate_left_never_blanks_row0(
    v173_v34_filename_hexes: tuple[Path, Path],
) -> None:
    _drive_b_a_b_to_input_and_trace_immediate_left(v173_v34_filename_hexes)


@pytest.mark.slow
def test_v172_native_preset_entry_paint_precedes_filename_cache_reuse(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    result = _drive_b_a_b_to_input_and_trace_immediate_left(v172_v33_filename_hexes)
    row0_ready_tick = result["row0_ready_tick"]
    row1_visible_tick = result["row1_visible_tick"]
    assert isinstance(row0_ready_tick, int)
    assert isinstance(row1_visible_tick, int)
    assert row0_ready_tick <= row1_visible_tick, result["trace"]


@pytest.mark.slow
def test_v173_native_preset_entry_paint_precedes_filename_cache_reuse(
    v173_v34_filename_hexes: tuple[Path, Path],
) -> None:
    result = _drive_b_a_b_to_input_and_trace_immediate_left(v173_v34_filename_hexes)
    row0_ready_tick = result["row0_ready_tick"]
    row1_visible_tick = result["row1_visible_tick"]
    assert isinstance(row0_ready_tick, int)
    assert isinstance(row1_visible_tick, int)
    assert row0_ready_tick <= row1_visible_tick, result["trace"]


@pytest.mark.slow
def test_v172_v33_full_native_chain_preset_b_survives_next_menu_standby_wake(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    _run_full_native_chain_preset_b_survives_next_menu_standby_wake(
        v172_v33_filename_hexes
    )


@pytest.mark.slow
def test_v173_v34_full_native_chain_preset_b_survives_next_menu_standby_wake(
    v173_v34_filename_hexes: tuple[Path, Path],
) -> None:
    _run_full_native_chain_preset_b_survives_next_menu_standby_wake(
        v173_v34_filename_hexes
    )


def test_v172_v33_native_chain_tail_first_prefix_first_blank_mismatch_cases() -> None:
    _assert_native_labels_present(
        {
            V33_MAIN_ASM: [
                "cmd26_filename_query_handler",
                "filename_reply_job_service",
            ],
            V172_CONTROL_ASM: [
                "v172_fname_case_check",
                "v172_fname_row1_render_service",
                "v172_preset_status_patch_service",
            ],
        }
    )
    assert _start_cmd_for("ABCDEFGHIJKLMNOP-v1", "ABCDEFGHIJKLMNOP-v2") == START_TAIL
    assert _start_cmd_for("LX521.4 A", "LX521.4 B") == START_PREFIX


def test_v172_v33_native_chain_mixed_old_new_peers_do_not_finalize() -> None:
    _assert_native_labels_present(
        {
            V33_MAIN_ASM: [
                "cmd26_filename_query_handler",
                "filename_reply_job_service",
            ],
            V172_CONTROL_ASM: [
                "v172_fname_case_check",
                "fname_reset_blank",
                "v172_fname_row1_render_service",
            ],
        }
    )
    test_raw_protocol_model_old_echo_positions_0_1_2_do_not_finalize(0, START_PREFIX)


def test_v172_v32_native_chain_filename_control_old_main_blanks_after_timeout(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    _require_rust()
    control_hex, _main_hex = v172_v33_filename_hexes
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(V32_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=300) < 300
    chain.mark_ctl_tx_capture_point()
    _press(chain, "RIGHT")

    _wait_for_lcd(chain, lambda lcd: lcd == ("Preset         A", "                "))
    for _ in range(120):
        chain.step_ticks(1_000_000)
        if not (chain.read_reg(FNAME_FLAGS_PHYS) & FNAME_PENDING_MASK):
            break

    flags = chain.read_reg(FNAME_FLAGS_PHYS)
    assert not (flags & FNAME_VALID_MASK)
    assert not (flags & FNAME_PENDING_MASK)
    assert chain.lcd_lines() == ("Preset         A", "                ")
    assert any(
        route == 0xB1 and cmd == 0x26
        for route, cmd, _data in _bytes_to_frames(chain.ctl_tx_record_since_last_capture())
    )


def test_v171_v33_native_chain_old_control_never_sends_filename_query(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    _require_rust()
    _control_hex, main_hex = v172_v33_filename_hexes
    chain = RustChain.from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(main_hex),
    )
    assert chain.run_until_connected(limit=300) < 300
    chain.mark_ctl_tx_capture_point()
    _press(chain, "RIGHT")
    _wait_for_lcd(chain, lambda lcd: lcd == ("Preset          ", "Active: A       "))
    chain.step_ticks(20_000_000)

    frames = _bytes_to_frames(chain.ctl_tx_record_since_last_capture())
    assert not any(cmd == 0x26 for _route, cmd, _data in frames)
    assert chain.lcd_lines() == ("Preset          ", "Active: A       ")


def test_v172_v33_fname_foreground_ir_buttons_standby_while_pending_valid_scrolling() -> None:
    _assert_native_labels_present(
        {
            V33_MAIN_ASM: [
                "cmd26_filename_query_handler",
                "filename_reply_job_service",
            ],
            V172_CONTROL_ASM: [
                "v172_fname_case_check",
                "v172_fname_row1_render_service",
                "v172_preset_status_patch_service",
            ],
        }
    )
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    loop = _label_body(text, "display_loop_iteration", ["flow_display_loop_iteration_0CB4"])
    assert "button_scan_debounce" in text
    assert "v172_preset_filename_service" in text


def test_v172_native_lcd_render_tolerates_ir_and_rcif_during_repaint(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    _require_rust()
    control_hex, main_hex = v172_v33_filename_hexes
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    _seed_filename_slots(chain, "LX521.4 22MG10F-v5", "LX521.4 22MG10F-v7")
    assert chain.run_until_connected(limit=300) < 300
    _configure_hypex_ir_profile(chain)
    chain.write_reg(VOLUME_CACHE_PHYS, 0x33)
    chain.write_reg(
        CONTROL_FLAGS_PHYS,
        chain.read_reg(CONTROL_FLAGS_PHYS) & ~MUTE_MASK & ~PRESET_BIT_MASK,
    )
    _press(chain, "RIGHT")
    _wait_for_lcd(
        chain,
        lambda lcd: lcd == ("Preset         A", "521.4 22MG10F-v5"),
    )

    # Simulate a native scroll-step repaint: the row remains valid but dirty,
    # and the renderer must repaint row 1 incrementally while foreground IR and
    # RCIF/parser traffic still run.
    chain.write_reg(FNAME_SCROLL_OFF_PHYS, 0)
    chain.write_reg(FNAME_RENDER_COL_PHYS, 0)
    chain.write_reg(FNAME_RENDER_OFF_PHYS, 0)
    chain.write_reg(FNAME_FLAGS_PHYS, chain.read_reg(FNAME_FLAGS_PHYS) | FNAME_ROW_DIRTY_MASK)
    row1_writes_before = [
        chain.lcd_ddram_write_count(0x40 + offset)
        for offset in range(16)
    ]

    assert chain.inject_control_rx_bytes([0xBF, 0x08, 0x01])
    chain.step_ticks(500_000)
    assert chain.read_reg(CONTROL_FLAGS_PHYS) & DSP_FAULT_MASK
    assert chain.lcd_lines()[0] == "Preset         !"
    frames = _inject_ir(chain, IR_CMD_VOL_UP, settle_ticks=2_000_000)
    assert chain.read_reg(VOLUME_CACHE_PHYS) == 0x34
    assert (0xB0, 0x07, 0x34) in frames
    _wait_for_lcd(
        chain,
        lambda lcd: lcd[0] in {"Preset         !", "Preset         A"}
        and lcd[1] == "LX521.4 22MG10F-",
        attempts=80,
    )
    row1_writes_after = [
        chain.lcd_ddram_write_count(0x40 + offset)
        for offset in range(16)
    ]
    assert all(after > before for before, after in zip(row1_writes_before, row1_writes_after))
    assert not (chain.read_reg(FNAME_FLAGS_PHYS) & FNAME_ROW_DIRTY_MASK)

    assert chain.inject_control_rx_bytes([0xBF, 0x08, 0x00])
    frames = _inject_ir(chain, IR_CMD_MUTE, settle_ticks=2_000_000)
    assert chain.read_reg(CONTROL_FLAGS_PHYS) & MUTE_MASK
    assert (0xB0, 0x03, 0x02) in frames
    _wait_for_lcd(
        chain,
        lambda lcd: lcd == ("Preset         A", "LX521.4 22MG10F-"),
        attempts=80,
    )


@pytest.mark.slow
def test_v172_native_preset_menu_dispatches_ir_standby_and_wake_during_repaint(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    _require_rust()
    control_hex, main_hex = v172_v33_filename_hexes
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    _seed_filename_slots(chain, "LX521.4 22MG10F-v5", "LX521.4 22MG10F-v7")
    assert chain.run_until_connected(limit=300) < 300
    assert chain.is_connected() and not chain.is_waiting()
    _configure_hypex_ir_profile(chain)

    _press(chain, "RIGHT")
    _wait_for_lcd(
        chain,
        lambda lcd: lcd == ("Preset         A", "521.4 22MG10F-v5"),
    )

    # Force the row into the same in-progress incremental repaint state used
    # during a scroll step. IR dispatch must still run from Preset here.
    chain.write_reg(FNAME_SCROLL_OFF_PHYS, 0)
    chain.write_reg(FNAME_RENDER_COL_PHYS, 0)
    chain.write_reg(FNAME_RENDER_OFF_PHYS, 0)
    chain.write_reg(FNAME_FLAGS_PHYS, chain.read_reg(FNAME_FLAGS_PHYS) | FNAME_ROW_DIRTY_MASK)

    standby_frames = _inject_ir(chain, IR_CMD_STANDBY, settle_ticks=20_000_000)
    assert (0xB0, 0x03, 0x00) in standby_frames, (
        f"CONTROL did not emit standby frame from Preset IR; frames={standby_frames!r}"
    )
    _wait_until(chain, lambda: "ZZZ" in chain.lcd_lines()[0].upper(), attempts=120)
    _wait_until(chain, lambda: _main_active_gates(chain) == (0, 0), attempts=180)

    wake_frames = _inject_ir(chain, IR_CMD_WAKE, settle_ticks=20_000_000)
    assert (0xB0, 0x03, 0x01) in wake_frames, (
        f"CONTROL did not emit wake frame from Preset IR; frames={wake_frames!r}"
    )
    _wait_until(
        chain,
        lambda: (
            chain.is_connected()
            and bool(chain.read_reg(CONTROL_FLAGS_PHYS) & CONTROL_CONNECTED_MASK)
            and "ZZZ" not in chain.lcd_lines()[0].upper()
        ),
        attempts=180,
    )
    _wait_until(chain, lambda: _main_active_gates(chain) == (1, 1), attempts=240)


# ---------------------------------------------------------------------------
# Requirement-to-test traceability names from docs/PRESET_FILENAME_LCD_SPEC.md.
# These wrappers keep the spec's named-test table executable while reusing the
# stronger model/native tests above.
# ---------------------------------------------------------------------------


def test_v172_fname_parser_duplicate_len_aborts() -> None:
    test_protocol_model_duplicate_len_before_chars_aborts()


def test_v172_fname_parser_late_len_after_char_aborts() -> None:
    test_protocol_model_late_len_after_char_aborts_not_reseals()


def test_v172_fname_parser_corrupt_len_aborts() -> None:
    test_protocol_model_corrupt_len_greater_than_30_aborts()


def test_v172_fname_parser_old_echo_positions_0_1_2_do_not_finalize() -> None:
    for position in (0, 1, 2):
        test_raw_protocol_model_old_echo_positions_0_1_2_do_not_finalize(position, START_PREFIX)


def test_v172_fname_parser_old_echo_multiframe_start_len_end_do_not_finalize() -> None:
    test_raw_protocol_model_old_echo_multibyte_start_len_end_streams_do_not_finalize([])


def test_v172_fname_parser_interleaved_bf08_identity_diag_preserved() -> None:
    test_v172_fname_parser_order_preserves_bf08_identity_and_diag_native()


def test_v172_fname_cold_init_clears_filename_state_preserves_diag_identity() -> None:
    text = V172_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "v172_fname_cold_clear", ["fname_mark_row_dirty_blank"])
    _assert_contains_all(
        body,
        [
            "lfsr    0x0, v172_fname_cache_b2_phys",
            "movlw   0x25",
            "lfsr    0x0, v172_fname_scroll_div_lo_b2_phys",
            "movlw   0x08",
        ],
    )
    assert "0x245" not in body


def test_v33_fname_cold_entry_clears_job_state_after_software_reset() -> None:
    text = V33_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    body = _label_body(text, "flow_main_flash_service_3ce8_3d4e", ["flow_main_flash_service_3ce8_3e34"])
    _assert_contains_all(
        body,
        [
            "clrf        fn_job_state",
            "clrf        fn_job_id",
            "clrf        fn_job_idx",
            "clrf        fn_job_src_kind",
            "clrf        fn_job_rev",
            "clrf        fn_job_start_cmd",
            "clrf        fn_job_len",
            "clrf        fn_job_tmp",
        ],
    )


def test_v172_fname_ram_equates_do_not_overlap_diag_identity() -> None:
    test_v172_fname_ram_equates_do_not_overlap_diag_identity_native()


def test_v172_fname_dirty_paths_reset_render_cursor() -> None:
    test_v172_fname_dirty_paths_reset_render_cursor_native()


def test_v172_fname_preset_exit_cancels_pending_or_armed_query() -> None:
    test_v172_fname_preset_exit_cancels_pending_or_armed_query_native()


def test_v172_fname_preset_entry_blanks_old_active_row() -> None:
    test_v172_fname_preset_entry_blanks_old_active_row_native()


def test_v172_fname_row1_incremental_render_writes_one_char_per_tick() -> None:
    test_v172_fname_row1_incremental_render_writes_one_char_per_tick_native()


def test_v172_fname_row1_render_tolerates_ir_rcif_during_pending_valid_scrolling(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    test_v172_native_lcd_render_tolerates_ir_and_rcif_during_repaint(v172_v33_filename_hexes)


def test_v172_preset_row0_live_patch_health_fault_preset_scenarios() -> None:
    test_v172_preset_row0_live_patch_health_fault_preset_scenarios_native()


def test_preset_filename_row1_dirty_render_initializes_render_cursor() -> None:
    renderer = Row1RenderModel.with_text("stale prefix")
    renderer.render_col = 7
    renderer.mark_valid("LX521.4 22MG10F-v5", scroll_off=2)
    assert renderer.render_col == 0
    assert renderer.render_off == 2
    renderer.tick()
    assert renderer.render_col == 1
    assert renderer.dirty


def test_preset_filename_row1_incremental_writer_advances_one_col_per_tick() -> None:
    test_row1_dirty_model_valid_end_restarts_from_col0_after_partial_blank()


def test_preset_filename_row1_render_uses_snapshot_offset_until_complete() -> None:
    renderer = Row1RenderModel.with_text(" " * 16)
    renderer.mark_valid("ABCDEFGHIJKLMNOPQRSTUVWXYZ", scroll_off=4)
    renderer.scroll_off = 8
    for _ in range(16):
        renderer.tick()
    assert renderer.row == "EFGHIJKLMNOPQRST"


def test_preset_filename_row1_pending_blank_is_incremental_not_full_clear() -> None:
    renderer = Row1RenderModel.with_text("ABCDEFGHIJKLMNOP")
    renderer.mark_blank()
    renderer.tick()
    assert renderer.row == " BCDEFGHIJKLMNOP"
    assert renderer.dirty


def test_preset_filename_row1_valid_empty_renders_blank_without_error_text() -> None:
    renderer = Row1RenderModel.with_text("old row text    ")
    renderer.mark_valid("", scroll_off=0)
    for _ in range(16):
        renderer.tick()
    assert renderer.row == " " * 16


def test_preset_filename_row1_static_name_pads_to_16_and_does_not_scroll() -> None:
    renderer = Row1RenderModel.with_text(" " * 16)
    renderer.mark_valid("FILE_A", scroll_off=0)
    for _ in range(16):
        renderer.tick()
    assert renderer.row == "FILE_A          "
    assert _start_cmd_for("FILE_A", "FILE_B") == START_PREFIX


def test_preset_filename_row1_exactly_16_chars_does_not_scroll() -> None:
    assert _window("ABCDEFGHIJKLMNOP", tail_first=True) == "ABCDEFGHIJKLMNOP"
    assert _window("ABCDEFGHIJKLMNOP", tail_first=False) == "ABCDEFGHIJKLMNOP"


def test_preset_filename_row1_tail_first_scroll_exact_windows() -> None:
    assert _window("LX521.4 22MG10F-v5", tail_first=True) == "521.4 22MG10F-v5"
    assert _start_cmd_for("LX521.4 22MG10F-v5", "LX521.4 22MG10F-v7") == START_TAIL


def test_preset_filename_row1_prefix_first_scroll_exact_windows() -> None:
    assert _window("FILE_A_012345678901", tail_first=False) == "FILE_A_012345678"
    assert _start_cmd_for("FILE_A_012345678901", "FILE_B_012345678901") == START_PREFIX


def test_preset_filename_row0_patch_changes_only_cols_14_15() -> None:
    base = _row0(False, False, False)
    changed = _row0(True, True, True)
    assert base[:14] == changed[:14] == "Preset        "
    assert base[14:] == " A"
    assert changed[14:] == "*!"


def test_preset_filename_row0_patch_handles_both_cells_changed() -> None:
    assert _row0(True, True, True) == "Preset        *!"


def test_preset_filename_pb2_only_stale_updates_star_without_blanking_row1() -> None:
    assert _row0(True, False, False) == "Preset        *A"
    assert _window("PB1_FILENAME", tail_first=False).startswith("PB1_FILENAME")


def test_preset_filename_pb1_lost_blanks_row1_and_sets_health_star() -> None:
    renderer = Row1RenderModel.with_text("PB1_FILENAME     ")
    renderer.mark_blank()
    assert _row0(True, False, False) == "Preset        *A"
    for _ in range(16):
        renderer.tick()
    assert renderer.row == " " * 16


def test_preset_filename_ir_volume_mute_during_pending_render(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    test_v172_native_lcd_render_tolerates_ir_and_rcif_during_repaint(v172_v33_filename_hexes)


def test_preset_filename_buttons_during_valid_static_render() -> None:
    test_v172_v33_fname_foreground_ir_buttons_standby_while_pending_valid_scrolling()


def test_preset_filename_standby_wake_during_scrolling_render(
    v172_v33_filename_hexes: tuple[Path, Path],
) -> None:
    test_v172_native_preset_menu_dispatches_ir_standby_and_wake_during_repaint(
        v172_v33_filename_hexes
    )


def test_preset_filename_ab_flip_during_incremental_render_restarts_query() -> None:
    text = _spec_text()
    _assert_contains_all(text, ["A render abandoned on A", "stale A reply ignored"])


def test_v172_v33_deployment_uses_cmd25_app_identity_not_usb_eeprom_rev() -> None:
    test_preset_filename_spec_requires_cmd25_app_resident_identity_for_flash_validation()
    test_preset_filename_spec_rejects_usb_eeprom_revision_as_authoritative_marker()


def test_v172_v33_filename_flash_gate_fails_when_usb_rev_new_but_cmd25_missing() -> None:
    text = _spec_text()
    _assert_contains_all(text, ["USB/HID version strings", "informational only", "[0xB1, 0x25, id]"])


def test_preset_filename_spec_requires_cmd25_app_resident_identity_for_flash_validation() -> None:
    text = _spec_text()
    _assert_contains_all(text, ["app-resident", "[0xB1, 0x25, id]", "Do not infer CONTROL identity"])


def test_preset_filename_spec_rejects_usb_eeprom_revision_as_authoritative_marker() -> None:
    text = _spec_text()
    _assert_contains_all(text, ["USB/HID version strings", "EEPROM byte `0x82`", "informational only"])


def test_preset_filename_spec_documents_pb1_lcd_authority_and_pb2_flash_validation() -> None:
    text = _spec_text()
    _assert_contains_all(text, ["PB1 OCR validates PB1 filename behavior", "PB2 old/mismatched state is warning-only"])


def test_preset_filename_spec_requires_blank_name_chain_evidence() -> None:
    text = _spec_text()
    _assert_contains_all(text, ["START(id)", "LEN(id ^ 0)", "blank LCD alone is never evidence"])


def test_preset_filename_spec_defines_hfd_active_ram_vs_inactive_eeprom_validation() -> None:
    test_spec_defines_hfd_active_ram_vs_inactive_eeprom_validation()


def test_v172_v33_pb1_authoritative_lcd_with_pb2_mismatch() -> None:
    test_display_model_is_pb1_authoritative_with_mismatched_pb2_names()


def test_v172_v33_full_chain_blank_name_requires_fresh_start_len_end_evidence() -> None:
    pending_id = _query_id(gen=23, target=PB1, slot=SLOT_A)
    parser = _parse_reply([(START_PREFIX, pending_id), (LEN_CMD, pending_id), (END_CMD, pending_id)], pending_id)
    assert parser.valid
    assert parser.expected_len == 0
    assert parser.cache == []


def test_v172_v33_hfd_active_slot_rename_uses_ram_on_requery() -> None:
    text = _spec_text()
    _assert_contains_all(text, ["active-slot rename validation", "fresh query", "active RAM name"])


def test_v172_v33_hfd_inactive_slot_validation_waits_for_eeprom_persist() -> None:
    text = _spec_text()
    _assert_contains_all(text, ["inactive-slot validation", "EEPROM persistence/readback"])


@pytest.mark.parametrize(
    "raw",
    [
        [START_PREFIX, 0x2C, LEN_CMD, 0x2C, END_CMD, 0x2C],
        [0xBF, START_PREFIX, 0x2C],
        [0xBF, 0x00, START_PREFIX, 0xBF, 0x00, LEN_CMD, 0xBF, 0x00, END_CMD],
    ],
)
def test_v172_native_raw_parser_old_echo_frame_positions_do_not_finalize(
    v172_v33_filename_hexes: tuple[Path, Path],
    raw: list[int],
) -> None:
    _require_rust()
    control_hex, main_hex = v172_v33_filename_hexes
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    assert chain.run_until_connected(limit=300) < 300
    _press(chain, "RIGHT")
    _wait_for_lcd(chain, lambda lcd: lcd[0] == "Preset         A")

    query_id = 0x2C
    _arm_pending_filename_query(chain, query_id, deadline=3)
    assert chain.inject_control_rx_bytes(raw)

    for _ in range(80):
        chain.step_ticks(100_000)
        assert not (chain.read_reg(FNAME_FLAGS_PHYS) & FNAME_VALID_MASK)

    for _ in range(80):
        chain.step_ticks(100_000)
        if not (chain.read_reg(FNAME_FLAGS_PHYS) & FNAME_PENDING_MASK):
            break
    flags = chain.read_reg(FNAME_FLAGS_PHYS)
    assert not (flags & FNAME_VALID_MASK)
    assert not (flags & FNAME_PENDING_MASK)
    assert not (flags & FNAME_ARMED_MASK)


def test_hardware_preset_filename_gate_rejects_old_active_layout() -> None:
    text = (PROJECT_ROOT / "tests" / "hardware" / "test_live_state_transitions.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    _assert_contains_all(
        text,
        [
            "DLCP_HW_PRESET_FILENAME_CONFIRM",
            "old Active: A/B Preset layout must not pass",
            'line2.startswith("Active:")',
        ],
    )


def test_hardware_preset_filename_raw_ordered_row_capture() -> None:
    text = (PROJECT_ROOT / "src" / "dlcp_fw" / "cli" / "hardware_lcd_probe.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    _assert_contains_all(
        text,
        [
            "--raw-ordered-row",
            "raw ordered row capture",
            "_raw_ordered_rows",
        ],
    )


def test_hardware_preset_filename_scroll_reconstruction() -> None:
    text = (PROJECT_ROOT / "src" / "dlcp_fw" / "cli" / "hardware_lcd_probe.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    _assert_contains_all(
        text,
        [
            "reconstruct_scroll_windows",
            "scroll_reconstruction",
            "raw_ordered_row",
        ],
    )


def test_hardware_preset_filename_confirm_requires_nonempty_pb1() -> None:
    text = (PROJECT_ROOT / "tests" / "hardware" / "test_live_state_transitions.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    _assert_contains_all(
        text,
        [
            "DLCP_HW_EXPECTED_PRESET_FILENAME",
            "known non-empty PB1",
            "blank names are validated by protocol evidence",
        ],
    )


# ---------------------------------------------------------------------------
# Preset LCD suffix/filename atomicity matrix (exploratory residuals s0045 /
# s0026 follow-up, 2026-06-11): continuous sampling across the preset
# transition matrix with two invariants --
#   INV-SUFFIX: a painted "Preset" row 0 must carry its A/B/! status cell
#               (col 15) except for a bounded repaint transient;
#   INV-ROW1:   row 1 must not sit blank while the filename cache is VALID
#               on the Preset page, except for the same bounded transient.
# Calibrated 2026-06-11: the worst observed transient on the canonical pair
# is ONE 2M-tick sample; the bound allows four.
# ---------------------------------------------------------------------------

_ATOMICITY_PIN = {
    "SELECT": ("A", 1),
    "DOWN": ("A", 2),
    "STBY": ("A", 3),
    "RIGHT": ("A", 4),
    "UP": ("C", 0),
    "LEFT": ("C", 5),
}
_ATOMICITY_SAMPLE_TICKS = 2_000_000
_ATOMICITY_MAX_TRANSIENT_SAMPLES = 4


def test_v173_v34_preset_lcd_suffix_and_row1_atomicity_matrix(
    v173_v34_filename_hexes: tuple[Path, Path],
) -> None:
    _require_rust()
    control_hex, main_hex = v173_v34_filename_hexes
    chain = _start_native_filename_chain(
        control_hex,
        main_hex,
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
        initial_preset="A",
    )

    runs = {"bare-suffix": 0, "blank-row1": 0}
    worst = {"bare-suffix": 0, "blank-row1": 0}
    context = {"bare-suffix": None, "blank-row1": None}

    def sample(step_label: str) -> None:
        lcd0, lcd1 = chain.lcd_lines()
        on_preset = lcd0.startswith("Preset")
        conds = {
            "bare-suffix": on_preset and lcd0[15] not in ("A", "B", "!"),
            "blank-row1": (
                on_preset
                and bool(chain.read_reg(FNAME_FLAGS_PHYS) & 0x01)
                and not lcd1.strip()
            ),
        }
        for key, cond in conds.items():
            runs[key] = runs[key] + 1 if cond else 0
            if runs[key] > worst[key]:
                worst[key] = runs[key]
                context[key] = (step_label, chain.lcd_lines())

    def hold(key: str, label: str) -> None:
        port, bit = _ATOMICITY_PIN[key]
        chain.set_control_pin(port, bit, False)
        for _ in range(25):
            chain.step_ticks(_ATOMICITY_SAMPLE_TICKS)
            sample(label)
        chain.set_control_pin(port, bit, True)
        for _ in range(25):
            chain.step_ticks(_ATOMICITY_SAMPLE_TICKS)
            sample(label)

    matrix = (
        ("RIGHT", "entry-A"),
        ("DOWN", "A-to-B"),
        ("DOWN", "B-to-A"),
        ("DOWN", "A-to-B-again"),
        ("LEFT", "away-to-volume"),
        ("RIGHT", "back-to-preset"),
        ("STBY", "standby-parked"),
        ("STBY", "wake-parked"),
    )
    for key, label in matrix:
        hold(key, label)
    for _ in range(40):
        chain.step_ticks(_ATOMICITY_SAMPLE_TICKS)
        sample("post-wake-settle")

    for key in ("bare-suffix", "blank-row1"):
        assert worst[key] <= _ATOMICITY_MAX_TRANSIENT_SAMPLES, (
            f"{key} persisted for {worst[key]} consecutive samples "
            f"({worst[key] * _ATOMICITY_SAMPLE_TICKS / 1e6:.0f}M ticks) at "
            f"{context[key]}"
        )
    lcd0 = chain.lcd_lines()[0]
    assert lcd0.startswith("Preset") and lcd0[15] in ("A", "B"), (
        f"matrix did not settle on a healthy Preset page: {chain.lcd_lines()!r}"
    )
