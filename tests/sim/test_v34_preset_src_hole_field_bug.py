"""V3.4 field repro: preset switch can commit a mixed DSP image.

Live report 2026-06-13: repeated IR A/B switching eventually produced
dangerously wrong filters/extreme bass while diagnostics still reported
HEALTHY.  Deterministic sim repro: while parked on Auto Detect with a locked
source, create an SRC4382 RXCKR=0 estimator hole with UNLOCK clear, then switch
B->A by IR.  PB2 can report preset A and restore nonzero TAS 0x30 while one
coefficient byte still differs from the clean A image.

The SRC hole is only a trigger/phase shifter.  A phase-only B->A switch with no
SRC register perturbation can reproduce the same missing TAS 0x59 write on PB2.
"""

from __future__ import annotations

import hashlib

import pytest

from dlcp_fw.paths import V173_CONTROL_HEX, V34_MAIN_HEX
from dlcp_fw.sim.dlcp_sim_native import Chain


IR_ADDR_HYPEX = 0x10
IR_CMD_PRESET_A = 0x38
IR_CMD_PRESET_B = 0x39

SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
SRC_REG_RX_LOCK = 0x14

MAIN_ACTIVE_FLAGS = 0x05E
MAIN_ACTIVE_PRESET_B = 0x04
MAIN_ACTIVE_GATE = 0x08
MAIN_ACTIVE_MUTE = 0x10
MAIN_DSP_FAULT_FLAGS = 0x07F
MAIN_DSP_FAULT_MASK = 0x40
MAIN_DSP_ACKSTAT_MASK = 0x04
MAIN_PRESET_JOB_STATE = 0x2DE
MAIN_PRESET_JOB_INDEX = 0x2E0
MAIN_PRESET_JOB_FLAGS = 0x2E2
MAIN_PRESET_JOB_TBL_HI = 0x2E4
TAS_MASTER_VOLUME = 0x30
PRESET_JOB_IDLE = 0x00
PRESET_JOB_APPLY = 0x03

CORE_MAIN0 = 1
CORE_MAIN1 = 2
PRESET_A_ROW_25 = 0x5978
PRESET_B_ROW_25 = 0x4F78
ROW_25_GOOD_HEADER = bytes([0x01, 0x59, 0x14, 0x00])
ROW_25_BAD_REG = 0x7F

ONE_S = 48_000_000
SAMPLE_TICKS = 250_000


pytestmark = pytest.mark.slow


def _new_chain() -> Chain:
    chain = Chain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX),
        main_hex_path=str(V34_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=300) < 300
    _set_src_locked(chain)
    chain.step_ticks(4 * ONE_S)
    return chain


def _set_src_locked(chain: Chain) -> None:
    for unit in (0, 1):
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_STATUS, 0x01)
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_LOCK, 0x00)
        chain.poke_main_src4382_reg(unit, SRC_REG_NON_PCM, 0x00)


def _set_locked_rxckr_hole(chain: Chain) -> None:
    for unit in (0, 1):
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_STATUS, 0x00)
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_LOCK, 0x00)
        chain.poke_main_src4382_reg(unit, SRC_REG_NON_PCM, 0x00)


def _send_ir_preset(chain: Chain, preset_b: bool) -> None:
    chain.inject_decoded_ir_event(
        addr=IR_ADDR_HYPEX,
        cmd=IR_CMD_PRESET_B if preset_b else IR_CMD_PRESET_A,
    )


def _coeff_image(chain: Chain, unit: int) -> bytes:
    return bytes(chain.read_main_dsp_reg(unit, subaddr) for subaddr in range(0x37, 0x91))


def _digest(image: bytes) -> str:
    return hashlib.sha256(image).hexdigest()[:12]


def _latest_tas30(chain: Chain, unit: int) -> bytes:
    payload = chain.read_main_dsp_write_payload(unit, TAS_MASTER_VOLUME)
    return b"" if payload is None else payload


def _tas_writes(chain: Chain, unit: int, subaddr: int) -> list[bytes]:
    return chain.read_main_dsp_write_payloads(unit, subaddr)


def _reset_apply_observability(chain: Chain) -> None:
    for unit in (0, 1):
        chain.reset_main_tas3108_stats(unit)
        chain.reset_main_src4382_stats(unit)
        chain.reset_main_dsp_write_log(unit)


def _consumed_i2c_faults(chain: Chain, unit: int) -> dict[str, int]:
    tas = chain.read_main_tas3108_stats(unit)
    src = chain.read_main_src4382_stats(unit)
    return {
        "tas_address_nacks": int(tas["address_nacks_consumed"]),
        "tas_data_nacks": int(tas["data_nacks_consumed"]),
        "src_address_nacks": int(src["address_nacks_consumed"]),
        "src_data_nacks": int(src["data_nacks_consumed"]),
    }


def _assert_no_consumed_i2c_faults(chain: Chain, unit: int) -> None:
    consumed = _consumed_i2c_faults(chain, unit)
    assert consumed == {
        "tas_address_nacks": 0,
        "tas_data_nacks": 0,
        "src_address_nacks": 0,
        "src_data_nacks": 0,
    }


def _first_diff(expected: bytes, observed: bytes) -> tuple[int, int, int] | None:
    for offset, (a, b) in enumerate(zip(expected, observed)):
        if a != b:
            return 0x37 + offset, a, b
    return None


def _clean_a_images() -> list[bytes]:
    chain = _new_chain()
    _send_ir_preset(chain, True)
    chain.step_ticks(160_000_000)
    _send_ir_preset(chain, False)
    chain.step_ticks(260_000_000)
    assert all(chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE) == 0 for unit in (0, 1))
    return [_coeff_image(chain, unit) for unit in (0, 1)]


def _clean_images_for_preset(preset_b: bool) -> list[bytes]:
    chain = _new_chain()
    if preset_b:
        _send_ir_preset(chain, True)
        chain.step_ticks(260_000_000)
    assert all(chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE) == 0 for unit in (0, 1))
    return [_coeff_image(chain, unit) for unit in (0, 1)]


def _settle_on_preset(chain: Chain, preset_b: bool) -> None:
    _send_ir_preset(chain, preset_b)
    chain.step_ticks(260_000_000)
    for unit in (0, 1):
        active = chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS)
        assert bool(active & MAIN_ACTIVE_PRESET_B) is preset_b, {
            "unit": unit,
            "active": active,
            "lcd": chain.lcd_lines(),
        }
        assert chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE) == PRESET_JOB_IDLE


def _patch_row25_header_reg(chain: Chain, *, core_idx: int, row_addr: int, reg: int) -> bytes:
    original = chain.read_core_flash(core_idx, row_addr, 4)
    assert original == ROW_25_GOOD_HEADER, {
        "core_idx": core_idx,
        "row_addr": hex(row_addr),
        "header": original.hex(),
    }
    chain.patch_core_flash(core_idx, row_addr + 1, bytes([reg & 0xFF]))
    return original


def _restore_row_header(chain: Chain, *, core_idx: int, row_addr: int, header: bytes) -> None:
    chain.patch_core_flash(core_idx, row_addr, header)


def _wait_for_pb2_apply_index(
    chain: Chain,
    index: int,
    *,
    samples: int = 2_000,
) -> None:
    for _ in range(samples):
        chain.step_ticks(50_000)
        state = chain.read_main_reg(1, MAIN_PRESET_JOB_STATE)
        current = chain.read_main_reg(1, MAIN_PRESET_JOB_INDEX)
        if state == PRESET_JOB_APPLY and current == index:
            return
    raise AssertionError(
        {
            "wanted_index": index,
            "state": chain.read_main_reg(1, MAIN_PRESET_JOB_STATE),
            "index": chain.read_main_reg(1, MAIN_PRESET_JOB_INDEX),
            "flags": chain.read_main_reg(1, MAIN_PRESET_JOB_FLAGS),
            "tbl_hi": chain.read_main_reg(1, MAIN_PRESET_JOB_TBL_HI),
            "active": chain.read_main_reg(1, MAIN_ACTIVE_FLAGS),
            "lcd": chain.lcd_lines(),
            "tas7f_writes": len(_tas_writes(chain, 1, ROW_25_BAD_REG)),
            "tas59_writes": len(_tas_writes(chain, 1, 0x59)),
        }
    )


def _assert_pb2_stuck_muted_on_corrupt_row(chain: Chain) -> None:
    chain.step_ticks(20_000_000)
    active = chain.read_main_reg(1, MAIN_ACTIVE_FLAGS)
    assert chain.read_main_reg(1, MAIN_PRESET_JOB_STATE) == PRESET_JOB_APPLY
    assert chain.read_main_reg(1, MAIN_PRESET_JOB_INDEX) == 0x25
    assert active & MAIN_ACTIVE_MUTE, {"active": active, "lcd": chain.lcd_lines()}
    assert not _tas_writes(chain, 1, ROW_25_BAD_REG), _tas_writes(chain, 1, ROW_25_BAD_REG)
    assert _latest_tas30(chain, 1) in (b"", b"\x00\x00\x00\x00")
    assert (chain.read_main_reg(1, MAIN_PRESET_JOB_FLAGS) & 0x04) == 0
    assert (chain.read_main_reg(1, 0x00D) & 0x01) == 0


def _assert_final_preset_image(
    chain: Chain,
    *,
    preset_b: bool,
    expected_images: list[bytes],
    expect_lcd_suffix: bool = True,
) -> None:
    chain.step_ticks(260_000_000)
    suffix = "B" if preset_b else "A"
    for unit in (0, 1):
        active = chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS)
        image = _coeff_image(chain, unit)
        assert chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE) == PRESET_JOB_IDLE
        assert bool(active & MAIN_ACTIVE_PRESET_B) is preset_b, {
            "unit": unit,
            "active": active,
            "lcd": chain.lcd_lines(),
        }
        assert image == expected_images[unit], {
            "unit": unit,
            "observed": _digest(image),
            "expected": _digest(expected_images[unit]),
            "first_diff": _first_diff(expected_images[unit], image),
            "lcd": chain.lcd_lines(),
        }
    if expect_lcd_suffix:
        assert chain.lcd_lines()[0].rstrip().endswith(suffix), chain.lcd_lines()


def _unsafe_unmuted_wrong_a_samples(
    chain: Chain,
    expected_a_pb2: bytes,
    *,
    samples: int = 260,
) -> list[dict[str, object]]:
    unsafe = []
    for sample in range(samples):
        chain.step_ticks(SAMPLE_TICKS)
        active = chain.read_main_reg(1, MAIN_ACTIVE_FLAGS)
        job = chain.read_main_reg(1, MAIN_PRESET_JOB_STATE)
        fault_flags = chain.read_main_reg(1, MAIN_DSP_FAULT_FLAGS)
        lcd = chain.lcd_lines()
        active_preset_a = not (active & MAIN_ACTIVE_PRESET_B)
        unmuted = not (active & MAIN_ACTIVE_MUTE)
        volume_live = bool(int.from_bytes(_latest_tas30(chain, 1), "big"))
        committed_healthy = (
            job == 0
            and (fault_flags & (MAIN_DSP_FAULT_MASK | MAIN_DSP_ACKSTAT_MASK)) == 0
            and lcd[0].rstrip().endswith("A")
        )
        image = _coeff_image(chain, 1)
        if (
            committed_healthy
            and active_preset_a
            and unmuted
            and volume_live
            and image != expected_a_pb2
        ):
            unsafe.append(
                {
                    "sample": sample,
                    "active": active,
                    "job": job,
                    "fault_flags": fault_flags,
                    "observed": _digest(image),
                    "expected": _digest(expected_a_pb2),
                    "first_diff": _first_diff(expected_a_pb2, image),
                    "tas30": _latest_tas30(chain, 1).hex(),
                    "tas59_write_count": len(_tas_writes(chain, 1, 0x59)),
                    "consumed_i2c_faults": _consumed_i2c_faults(chain, 1),
                    "lcd": lcd,
                }
            )
    return unsafe


def _drive_b_to_a_after_phase_delay(
    chain: Chain,
    *,
    delay_ticks: int,
    use_src_hole: bool,
) -> None:
    _send_ir_preset(chain, True)
    chain.step_ticks(160_000_000)
    _reset_apply_observability(chain)

    if use_src_hole:
        _set_locked_rxckr_hole(chain)
    chain.step_ticks(delay_ticks)
    _send_ir_preset(chain, False)
    if use_src_hole:
        _set_src_locked(chain)
    chain.step_ticks(1_000_000)


def _assert_b_to_a_apply_never_commits_mixed_pb2_image(
    *,
    delay_ticks: int,
    use_src_hole: bool,
) -> None:
    expected_a = _clean_a_images()

    chain = _new_chain()
    _drive_b_to_a_after_phase_delay(
        chain,
        delay_ticks=delay_ticks,
        use_src_hole=use_src_hole,
    )

    unsafe = _unsafe_unmuted_wrong_a_samples(chain, expected_a[1])
    chain.step_ticks(2 * ONE_S)
    final_pb2 = _coeff_image(chain, 1)
    tas59_writes = _tas_writes(chain, 1, 0x59)
    fault_flags = chain.read_main_reg(1, MAIN_DSP_FAULT_FLAGS)

    assert not unsafe, unsafe[:3]
    _assert_no_consumed_i2c_faults(chain, 1)
    assert (fault_flags & (MAIN_DSP_FAULT_MASK | MAIN_DSP_ACKSTAT_MASK)) == 0, {
        "fault_flags": fault_flags,
        "consumed_i2c_faults": _consumed_i2c_faults(chain, 1),
    }
    assert chain.lcd_lines()[0].rstrip().endswith("A"), chain.lcd_lines()
    assert tas59_writes, {
        "missing": "PB2 never emitted the TAS 0x59 preset burst during B->A",
        "tas58_last": (chain.read_main_dsp_write_payload(1, 0x58) or b"").hex(),
        "tas5a_last": (chain.read_main_dsp_write_payload(1, 0x5A) or b"").hex(),
        "fault_flags": fault_flags,
        "consumed_i2c_faults": _consumed_i2c_faults(chain, 1),
        "final_digest": _digest(final_pb2),
        "expected": _digest(expected_a[1]),
        "first_diff": _first_diff(expected_a[1], final_pb2),
        "lcd": chain.lcd_lines(),
    }
    assert final_pb2 == expected_a[1], {
        "observed": _digest(final_pb2),
        "expected": _digest(expected_a[1]),
        "first_diff": _first_diff(expected_a[1], final_pb2),
        "tas59_write_count": len(tas59_writes),
        "lcd": chain.lcd_lines(),
    }


def test_ir_b_to_a_under_locked_rxckr_hole_never_unmutes_wrong_pb2_coefficients() -> None:
    _assert_b_to_a_apply_never_commits_mixed_pb2_image(
        delay_ticks=2_000_000,
        use_src_hole=True,
    )


def test_ir_b_to_a_phase_hit_without_src_hole_never_omits_pb2_tas59_write() -> None:
    _assert_b_to_a_apply_never_commits_mixed_pb2_image(
        delay_ticks=2_000_000,
        use_src_hole=False,
    )


def test_corrupt_pb2_a_row_header_retries_muted_and_recovers_after_repair() -> None:
    expected_a = _clean_a_images()
    chain = _new_chain()
    _settle_on_preset(chain, True)
    _reset_apply_observability(chain)
    original = _patch_row25_header_reg(
        chain,
        core_idx=CORE_MAIN1,
        row_addr=PRESET_A_ROW_25,
        reg=ROW_25_BAD_REG,
    )

    _send_ir_preset(chain, False)
    _wait_for_pb2_apply_index(chain, 0x25)
    _assert_pb2_stuck_muted_on_corrupt_row(chain)

    _restore_row_header(
        chain,
        core_idx=CORE_MAIN1,
        row_addr=PRESET_A_ROW_25,
        header=original,
    )
    _assert_final_preset_image(
        chain,
        preset_b=False,
        expected_images=expected_a,
        expect_lcd_suffix=False,
    )
    assert _tas_writes(chain, 1, 0x59), "PB2 must emit TAS 0x59 after header repair"


@pytest.mark.parametrize("cancel_mode", ["standby", "reconnect"])
def test_corrupt_pb2_header_retry_cancels_without_unmuting_partial_image(
    cancel_mode: str,
) -> None:
    chain = _new_chain()
    _settle_on_preset(chain, True)
    _reset_apply_observability(chain)
    _patch_row25_header_reg(
        chain,
        core_idx=CORE_MAIN1,
        row_addr=PRESET_A_ROW_25,
        reg=ROW_25_BAD_REG,
    )

    _send_ir_preset(chain, False)
    _wait_for_pb2_apply_index(chain, 0x25)
    _assert_pb2_stuck_muted_on_corrupt_row(chain)

    if cancel_mode == "standby":
        chain.press("STBY")
    else:
        active = chain.read_main_reg(1, MAIN_ACTIVE_FLAGS)
        chain.write_main_reg(1, MAIN_ACTIVE_FLAGS, active | 0x80)
    chain.step_ticks(30_000_000)

    active = chain.read_main_reg(1, MAIN_ACTIVE_FLAGS)
    assert chain.read_main_reg(1, MAIN_PRESET_JOB_STATE) == PRESET_JOB_IDLE
    assert (active & MAIN_ACTIVE_MUTE) or not (active & MAIN_ACTIVE_GATE), {
        "cancel_mode": cancel_mode,
        "active": active,
        "lcd": chain.lcd_lines(),
    }
    assert (chain.read_main_reg(1, MAIN_PRESET_JOB_FLAGS) & 0x04) == 0
    assert _latest_tas30(chain, 1) in (b"", b"\x00\x00\x00\x00")


@pytest.mark.parametrize(
    ("first_b", "second_b"),
    [
        (True, False),
        (False, True),
    ],
)
def test_coalesced_target_during_apply_restarts_from_row0_correct_source(
    first_b: bool,
    second_b: bool,
) -> None:
    expected = _clean_images_for_preset(True) if second_b else _clean_a_images()
    chain = _new_chain()
    if not first_b:
        _settle_on_preset(chain, True)
    _reset_apply_observability(chain)

    _send_ir_preset(chain, first_b)
    _wait_for_pb2_apply_index(chain, 0x10)
    active_during_first = chain.read_main_reg(1, MAIN_ACTIVE_FLAGS)
    assert bool(active_during_first & MAIN_ACTIVE_PRESET_B) is first_b
    assert active_during_first & MAIN_ACTIVE_MUTE

    _send_ir_preset(chain, second_b)
    _assert_final_preset_image(chain, preset_b=second_b, expected_images=expected)


def test_coalesced_target_during_validation_retry_restarts_from_row0_correct_source() -> None:
    expected_a = _clean_a_images()
    chain = _new_chain()
    _reset_apply_observability(chain)
    _patch_row25_header_reg(
        chain,
        core_idx=CORE_MAIN1,
        row_addr=PRESET_B_ROW_25,
        reg=ROW_25_BAD_REG,
    )

    _send_ir_preset(chain, True)
    _wait_for_pb2_apply_index(chain, 0x25)
    _assert_pb2_stuck_muted_on_corrupt_row(chain)

    _send_ir_preset(chain, False)
    _assert_final_preset_image(
        chain,
        preset_b=False,
        expected_images=expected_a,
        expect_lcd_suffix=False,
    )
