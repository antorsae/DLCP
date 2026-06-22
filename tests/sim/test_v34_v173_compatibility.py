"""V3.4/V1.73 mixed-version simulator compatibility gates."""

from __future__ import annotations

import pytest

from dlcp_fw.paths import (
    V171_CONTROL_HEX,
    V172_CONTROL_HEX,
    V173_CONTROL_HEX,
    V32_MAIN_HEX,
    V33_MAIN_HEX,
    V34_MAIN_HEX,
)

from tests.sim.test_preset_filename_lcd_spec import (
    CONTROL_FLAGS_PHYS,
    FNAME_FLAGS_PHYS,
    FNAME_PENDING_MASK,
    FNAME_QUERY_WAIT_MASK,
    FNAME_VALID_MASK,
    FNAME_WANT_QUERY_MASK,
    IR_ADDR_HYPEX,
    MAIN_ACTIVE_FLAGS_PHYS,
    MAIN_ACTIVE_GATE_MASK,
    NativePresetFilenameStep,
    PRESET_FILENAME_SLOT_A,
    PRESET_FILENAME_SLOT_B,
    PRESET_BIT_MASK,
    RustChain,
    VOLUME_CACHE_PHYS,
    _bytes_to_frames,
    _drive_and_assert_native_preset_filename,
    _press,
    _require_rust,
    _seed_filename_slots,
    _start_native_filename_chain,
    _wait_for_lcd,
    _preset_filename_windows,
)


pytestmark = pytest.mark.slow

MAIN_ACTIVE_PRESET_MASK = 0x04
MAIN_PRESET_JOB_STATE_PHYS = 0x2DE
MAIN_PRESET_JOB_IDLE = 0
MAIN_LOGICAL_VOLUME_PHYS = 0x066
MAIN_COMPUTED_VOLUME_PHYS = 0x06E
MAIN_SETTING_05F_PHYS = 0x05F
MAIN_SETTING_060_PHYS = 0x060
MAIN_INPUT_SELECT_PHYS = 0x099
MAIN_TRIM_BASE_PHYS = 0x09B
MAIN_SETTING_0C3_PHYS = 0x0C3
MAIN_SETTING_0A5_MIRROR_PHYS = 0x0A5
MAIN_TRIM_MIRROR_BASE_PHYS = 0x0AC
MAIN_INPUT_MIRROR_PHYS = 0x0B3
MAIN_SETTING_0B2_MIRROR_PHYS = 0x0B2

IR_CMD_HYPEX_VOLUME_DOWN = 0x34
IR_CMD_PRESET_B = 0x39

POWER_CYCLE_POLL_TICKS = 1_000_000
POWER_CYCLE_READY_ATTEMPTS = 400
PRESET_SYNC_POLL_TICKS = 50_000_000
PRESET_SYNC_ATTEMPTS = 60
EEPROM_VOLUME_PERSIST_ATTEMPTS = 250
VOLUME_IR_SETTLE_TICKS = 12_000_000


def test_v173_v34_chain_reaches_volume_and_preset_filename() -> None:
    _require_rust()
    chain = _start_native_filename_chain(
        V173_CONTROL_HEX,
        V34_MAIN_HEX,
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
    )
    assert chain.lcd_lines()[0].startswith("Volume")
    _drive_and_assert_native_preset_filename(
        chain,
        NativePresetFilenameStep("RIGHT", "A"),
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
    )


def _main_bytes(
    chain,
    unit: int,
    base: int,
) -> tuple[int, int, int, int]:  # type: ignore[no-untyped-def]
    return tuple(  # type: ignore[return-value]
        chain.read_main_reg(unit, base + i) & 0xFF for i in range(4)
    )


def _main_eeprom_volume(
    chain,
    unit: int,
) -> tuple[int, int, int, int]:  # type: ignore[no-untyped-def]
    return tuple(  # type: ignore[return-value]
        chain.read_main_eeprom_byte(unit, i) & 0xFF for i in range(4)
    )


def _wait_for_main_preset(chain, preset_b: bool, *, trigger: str) -> None:  # type: ignore[no-untyped-def]
    target = MAIN_ACTIVE_PRESET_MASK if preset_b else 0
    for _ in range(PRESET_SYNC_ATTEMPTS):
        if all(
            (chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS_PHYS) & MAIN_ACTIVE_PRESET_MASK)
            == target
            and chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE_PHYS)
            == MAIN_PRESET_JOB_IDLE
            for unit in (0, 1)
        ):
            return
        chain.step_ticks(PRESET_SYNC_POLL_TICKS)
    flags = [
        chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS_PHYS) & 0xFF
        for unit in (0, 1)
    ]
    jobs = [
        chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE_PHYS) & 0xFF
        for unit in (0, 1)
    ]
    pytest.fail(
        f"MAINs did not converge on preset {'B' if preset_b else 'A'} after "
        f"{trigger}: flags={[hex(v) for v in flags]} jobs={jobs} "
        f"lcd={chain.lcd_lines()!r}"
    )


def _wait_for_fresh_power_cycle_volume_page(chain):  # type: ignore[no-untyped-def]
    for _ in range(POWER_CYCLE_READY_ATTEMPTS):
        chain.step_ticks(POWER_CYCLE_POLL_TICKS)
        gates_up = all(
            chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS_PHYS) & MAIN_ACTIVE_GATE_MASK
            for unit in (0, 1)
        )
        row0, _ = chain.lcd_lines()
        if chain.is_connected() and gates_up and row0.startswith("Volume:"):
            return chain.lcd_lines()
    pytest.fail(
        "chain did not return to a fresh connected Volume page after POR: "
        f"lcd={chain.lcd_lines()!r}"
    )


def _wait_for_main_eeprom_volume_matches_computed(chain) -> None:  # type: ignore[no-untyped-def]
    for _ in range(EEPROM_VOLUME_PERSIST_ATTEMPTS):
        expected = tuple(reversed(_main_bytes(chain, 0, MAIN_COMPUTED_VOLUME_PHYS)))
        if all(_main_eeprom_volume(chain, unit) == expected for unit in (0, 1)):
            return
        chain.step_ticks(POWER_CYCLE_POLL_TICKS)
    got = [_main_eeprom_volume(chain, unit) for unit in (0, 1)]
    expected = tuple(reversed(_main_bytes(chain, 0, MAIN_COMPUTED_VOLUME_PHYS)))
    pytest.fail(f"MAIN EEPROM volume did not catch computed volume {expected!r}: got={got!r}")


def _drive_preset_b_and_negative_volume(chain):  # type: ignore[no-untyped-def]
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_PRESET_B)
    chain.step_ticks(80_000_000)
    _wait_for_main_preset(chain, True, trigger="IR preset-B selection")

    initial_cache = chain.read_reg(VOLUME_CACHE_PHYS)
    for _ in range(3):
        chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_HYPEX_VOLUME_DOWN)
        chain.step_ticks(VOLUME_IR_SETTLE_TICKS)

    assert chain.read_reg(VOLUME_CACHE_PHYS) == ((initial_cache - 3) & 0xFF)
    _wait_for_main_eeprom_volume_matches_computed(chain)
    return {
        "control_volume": chain.read_reg(VOLUME_CACHE_PHYS),
        "lcd_row0": chain.lcd_lines()[0],
        "main": [
            {
                "logical": _main_bytes(chain, unit, MAIN_LOGICAL_VOLUME_PHYS),
                "computed": _main_bytes(chain, unit, MAIN_COMPUTED_VOLUME_PHYS),
                "eeprom": _main_eeprom_volume(chain, unit),
            }
            for unit in (0, 1)
        ],
    }


def test_v173_v34_user_preset_survives_por_power_cycle() -> None:
    _require_rust()
    chain = _start_native_filename_chain(
        V173_CONTROL_HEX,
        V34_MAIN_HEX,
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
        initial_preset="A",
    )

    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_PRESET_B)
    chain.step_ticks(80_000_000)
    _wait_for_main_preset(chain, True, trigger="pre-POR preset-B selection")

    chain.apply_reset_all("por")
    _wait_for_fresh_power_cycle_volume_page(chain)

    assert chain.read_reg(CONTROL_FLAGS_PHYS) & PRESET_BIT_MASK
    assert chain.lcd_lines()[0].endswith("B"), chain.lcd_lines()
    _wait_for_main_preset(chain, True, trigger="post-POR EEPROM 0x74 boot restore")


def test_v173_v34_user_volume_and_preset_survive_por_power_cycle() -> None:
    _require_rust()
    chain = _start_native_filename_chain(
        V173_CONTROL_HEX,
        V34_MAIN_HEX,
        slot_a=PRESET_FILENAME_SLOT_A,
        slot_b=PRESET_FILENAME_SLOT_B,
        initial_preset="A",
    )
    before_reset = _drive_preset_b_and_negative_volume(chain)

    chain.apply_reset_all("por")
    _wait_for_fresh_power_cycle_volume_page(chain)

    assert chain.read_reg(CONTROL_FLAGS_PHYS) & PRESET_BIT_MASK
    assert chain.read_reg(VOLUME_CACHE_PHYS) == before_reset["control_volume"]
    assert chain.lcd_lines()[0] == before_reset["lcd_row0"]
    for unit in (0, 1):
        expected = before_reset["main"][unit]
        assert _main_bytes(chain, unit, MAIN_LOGICAL_VOLUME_PHYS) == expected["logical"]
        assert _main_bytes(chain, unit, MAIN_COMPUTED_VOLUME_PHYS) == expected["computed"]
        assert _main_eeprom_volume(chain, unit) == expected["eeprom"]
    _wait_for_main_preset(chain, True, trigger="post-POR combined restore")


def test_v34_main_boot_restores_seeded_eeprom_settings_exactly() -> None:
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(V34_MAIN_HEX))
    seed = {
        0x00: 0xFF,
        0x01: 0xFF,
        0x02: 0xFF,
        0x03: 0xFD,
        0x04: 0x04,
        0x07: 0x02,
        0x08: 0x03,
        0x09: 0x01,
        0x0A: 0x02,
        0x0B: 0x03,
        0x0C: 0x01,
        0x0D: 0x02,
        0x10: 0x05,
        0x11: 0x06,
        0x12: 0x07,
        0x13: 0x08,
        0x14: 0x04,
    }
    for addr, value in seed.items():
        chain.write_main_eeprom_byte(0, addr, value)

    chain.step_tcy(16_000_000)
    chain.step_ticks(40_000_000)
    assert chain.read_main_reg(0, MAIN_ACTIVE_FLAGS_PHYS) & MAIN_ACTIVE_GATE_MASK

    assert _main_bytes(chain, 0, MAIN_COMPUTED_VOLUME_PHYS) == (
        0xFD,
        0xFF,
        0xFF,
        0xFF,
    )
    assert _main_bytes(chain, 0, MAIN_LOGICAL_VOLUME_PHYS) == (
        0xFD,
        0xFF,
        0xFF,
        0xFF,
    )
    assert chain.read_main_reg(0, MAIN_INPUT_SELECT_PHYS) == 0x04
    assert chain.read_main_reg(0, MAIN_INPUT_MIRROR_PHYS) == 0x04
    assert [
        chain.read_main_reg(0, MAIN_SETTING_060_PHYS + offset) & 0xFF
        for offset in range(6)
    ] == [0x02, 0x03, 0x01, 0x02, 0x03, 0x01]
    assert [
        chain.read_main_reg(0, MAIN_SETTING_0A5_MIRROR_PHYS + offset) & 0xFF
        for offset in range(6)
    ] == [0x02, 0x03, 0x01, 0x02, 0x03, 0x01]
    assert chain.read_main_reg(0, MAIN_SETTING_05F_PHYS) == 0x02
    assert chain.read_main_reg(0, MAIN_SETTING_0C3_PHYS) == 0x04
    assert chain.read_main_reg(0, MAIN_SETTING_0B2_MIRROR_PHYS) == 0x04
    assert [
        chain.read_main_reg(0, MAIN_TRIM_BASE_PHYS + offset) & 0xFF
        for offset in range(4)
    ] == [0x05, 0x06, 0x07, 0x08]
    assert [
        chain.read_main_reg(0, MAIN_TRIM_MIRROR_BASE_PHYS + offset) & 0xFF
        for offset in range(4)
    ] == [0x05, 0x06, 0x07, 0x08]


@pytest.mark.parametrize(
    ("control_hex", "main_hex", "case_id"),
    [
        pytest.param(V173_CONTROL_HEX, V33_MAIN_HEX, "v173-v33", id="v173-v33"),
        pytest.param(V172_CONTROL_HEX, V34_MAIN_HEX, "v172-v34", id="v172-v34"),
    ],
)
def test_mixed_new_old_filename_pairs_preserve_query_cache_and_reentry(
    control_hex, main_hex, case_id: str
) -> None:
    _require_rust()
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
    input_title = "Input PB1:      " if case_id == "v173-v33" else "Input:          "
    _wait_for_lcd(chain, lambda lcd: lcd == (input_title, "Auto Detect     "))
    chain.mark_ctl_tx_capture_point()
    _press(chain, "LEFT")
    # Rotation-tolerant: background chain traffic (e.g. the V1.73 periodic
    # mute re-assert) shifts the scroll phase, so pin the content (any
    # legal scroll window of slot B) rather than one exact rotation.
    row1_ok = _preset_filename_windows("B", PRESET_FILENAME_SLOT_A, PRESET_FILENAME_SLOT_B)
    _wait_for_lcd(
        chain,
        lambda lcd: lcd[0] == "Preset         B" and lcd[1] in row1_ok,
    )
    frames = _bytes_to_frames(chain.ctl_tx_record_since_last_capture())
    assert not any(frame[0] == 0xB1 and frame[1] == 0x26 for frame in frames), case_id


def test_v173_v32_old_main_filename_query_times_out_blank() -> None:
    """V1.73 + old V3.2 MAIN (no cmd 0x26 support): the filename query times
    out blank.  BUG-V34V173-4 makes the timeout schedule a *bounded* delayed
    retry (FNAME_RETRY_MAX total attempts), so the FSM is briefly re-armed
    after each expiry and then settles terminally quiet -- it must not retry
    forever against a MAIN that will never answer.
    """
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX),
        main_hex_path=str(V32_MAIN_HEX),
    )
    _seed_filename_slots(chain, PRESET_FILENAME_SLOT_A, PRESET_FILENAME_SLOT_B)
    assert chain.run_until_connected(limit=300) < 300
    chain.mark_ctl_tx_capture_point()
    _press(chain, "RIGHT")

    _wait_for_lcd(chain, lambda lcd: lcd == ("Preset         A", "                "))
    busy_mask = FNAME_PENDING_MASK | FNAME_WANT_QUERY_MASK | FNAME_QUERY_WAIT_MASK
    for _ in range(600):
        chain.step_ticks(1_000_000)
        if not (chain.read_reg(FNAME_FLAGS_PHYS) & busy_mask):
            break

    flags = chain.read_reg(FNAME_FLAGS_PHYS)
    assert not (flags & FNAME_VALID_MASK)
    assert not (flags & busy_mask), (
        "filename FSM still armed after the bounded retry budget expired: "
        f"flags=0x{flags:02X}"
    )
    assert chain.lcd_lines() == ("Preset         A", "                ")
    queries = [
        frame
        for frame in _bytes_to_frames(chain.ctl_tx_record_since_last_capture())
        if frame[0] == 0xB1 and frame[1] == 0x26
    ]
    # FNAME_RETRY_MAX = 3: the initial query plus exactly two bounded retries.
    assert len(queries) == 3, queries


def test_v171_v34_old_control_never_sends_filename_query() -> None:
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(V34_MAIN_HEX),
    )
    _seed_filename_slots(chain, PRESET_FILENAME_SLOT_A, PRESET_FILENAME_SLOT_B)
    assert chain.run_until_connected(limit=300) < 300
    chain.mark_ctl_tx_capture_point()
    _press(chain, "RIGHT")
    _wait_for_lcd(chain, lambda lcd: lcd == ("Preset          ", "Active: A       "))
    chain.step_ticks(20_000_000)

    frames = _bytes_to_frames(chain.ctl_tx_record_since_last_capture())
    assert not any(frame[1] == 0x26 for frame in frames)
    assert chain.lcd_lines() == ("Preset          ", "Active: A       ")
