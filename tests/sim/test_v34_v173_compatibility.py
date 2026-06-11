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
    FNAME_FLAGS_PHYS,
    FNAME_PENDING_MASK,
    FNAME_QUERY_WAIT_MASK,
    FNAME_VALID_MASK,
    FNAME_WANT_QUERY_MASK,
    NativePresetFilenameStep,
    PRESET_FILENAME_SLOT_A,
    PRESET_FILENAME_SLOT_B,
    RustChain,
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
    _wait_for_lcd(chain, lambda lcd: lcd == ("Input:          ", "Auto Detect     "))
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

