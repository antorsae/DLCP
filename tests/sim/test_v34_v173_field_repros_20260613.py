"""Focused repro tests for the 2026-06-13 V3.4/V1.73 field findings."""

from __future__ import annotations

import hashlib

import pytest

from dlcp_fw.paths import V173_CONTROL_HEX, V34_MAIN_HEX
from dlcp_fw.sim.dlcp_sim_native import Chain


pytestmark = pytest.mark.slow

CONTROL_FLAGS = 0x01F
CONTROL_CONNECTED_MASK = 0x02
CONTROL_MUTE_MASK = 0x20
CONTROL_PRESET_B_MASK = 0x40
CONTROL_DISPLAY_STATE = 0x0BF
CONTROL_IR_PROFILE_ADDR = 0x020
CONTROL_IR_PROFILE_POWER = 0x021
CONTROL_IR_PROFILE_MUTE = 0x026

STATE_PB1_DIAG = 4
STATE_PB2_DIAG = 5

MAIN_ACTIVE_FLAGS = 0x05E
MAIN_ACTIVE_PRESET_B = 0x04
MAIN_ACTIVE_GATE = 0x08
MAIN_ACTIVE_MUTE = 0x10
MAIN_DSP_FAULT_FLAGS = 0x07F
MAIN_DSP_FAULT_MASK = 0x40
MAIN_DSP_ACKSTAT_MASK = 0x04
MAIN_PRESET_JOB_STATE = 0x2DE
MAIN_PRESET_JOB_INDEX = 0x2E0
MAIN_PRESET_JOB_TARGET = 0x2DF
MAIN_PRESET_JOB_FLAGS = 0x2E2

SRC_NON_PCM = 0x12
SRC_RX_STATUS = 0x13
SRC_UNLOCK = 0x14

TAS_MASTER_VOLUME = 0x30
TAS_BIQUAD_FIRST = 0x37
TAS_BIQUAD_LAST = 0x90

PRESET_A_EEPROM_BASE = 0x60
PRESET_B_EEPROM_BASE = 0x83
FILENAME_LEN = 0x1E
HID_REPORT_LEN = 64
CMD03_FILENAME_WRITE = 0x03
CMD03_FILENAME_READ = 0x04

IR_ADDR_HYPEX = 0x10
IR_CMD_POWER = 0x32
IR_CMD_VOLUME_UP = 0x33
IR_CMD_MUTE = 0x35
IR_CMD_PRESET_A = 0x38
IR_CMD_PRESET_B = 0x39
IR_CMD_STANDBY = 0x3A
IR_CMD_WAKE = 0x3B

MAIN_EVENT_FLAGS = 0x07E
MAIN_EVENT_ROUTE_DIRTY = 0x10
MAIN_REAPPLY_PENDING = 0x80

CORE_MAIN0 = 1
CORE_MAIN1 = 2
PRESET_A_ROW_25 = 0x5978
ROW_25_GOOD_HEADER = bytes([0x01, 0x59, 0x14, 0x00])
ROW_25_BAD_REG = 0x7F

def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def _slot_bytes(text: str) -> bytes:
    raw = text.encode("ascii", errors="replace")[:FILENAME_LEN]
    return raw + bytes([0xFF]) * (FILENAME_LEN - len(raw))


def _seed_filename_slots(
    chain: Chain,
    *,
    a_pb1: str = "",
    b_pb1: str = "",
    a_pb2: str = "",
    b_pb2: str = "",
) -> None:
    for unit, slot_a, slot_b in ((0, a_pb1, b_pb1), (1, a_pb2, b_pb2)):
        for offset, value in enumerate(_slot_bytes(slot_a)):
            chain.write_main_eeprom_byte(unit, PRESET_A_EEPROM_BASE + offset, value)
        for offset, value in enumerate(_slot_bytes(slot_b)):
            chain.write_main_eeprom_byte(unit, PRESET_B_EEPROM_BASE + offset, value)


def _set_src_locked(chain: Chain) -> None:
    for unit in (0, 1):
        chain.poke_main_src4382_reg(unit, SRC_NON_PCM, 0x00)
        chain.poke_main_src4382_reg(unit, SRC_RX_STATUS, 0x01)
        chain.poke_main_src4382_reg(unit, SRC_UNLOCK, 0x00)


def _set_src_flap_fixture(chain: Chain) -> None:
    """Pin the session-15 ``src_initial=flap`` fixture explicitly.

    The exploratory runner left the SRC registers at their post-BOR defaults
    for this mode.  The repro depends on that lost-estimator state, so encode
    it instead of relying on simulator constructor defaults.
    """
    for unit in (0, 1):
        chain.poke_main_src4382_reg(unit, SRC_NON_PCM, 0x00)
        chain.poke_main_src4382_reg(unit, SRC_RX_STATUS, 0x00)
        chain.poke_main_src4382_reg(unit, SRC_UNLOCK, 0x00)


def _assert_src_flap_fixture(chain: Chain) -> None:
    for unit in (0, 1):
        assert chain.read_main_src4382_reg(unit, SRC_NON_PCM) == 0x00
        assert chain.read_main_src4382_reg(unit, SRC_RX_STATUS) == 0x00
        assert chain.read_main_src4382_reg(unit, SRC_UNLOCK) == 0x00


def _new_chain(
    *,
    seed_session5_names: bool = False,
    reset_source: str = "por",
    src_initial: str = "locked",
) -> Chain:
    chain = Chain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX),
        main_hex_path=str(V34_MAIN_HEX),
    )
    if seed_session5_names:
        _seed_filename_slots(
            chain,
            a_pb1="bad\x01name",
            b_pb1="LX521.4 PB6v23 Q",
            a_pb2="",
            b_pb2="",
        )
    if reset_source != "por":
        chain.apply_reset_all(reset_source)
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()
    assert chain.is_connected() and not chain.is_waiting(), chain.lcd_lines()
    if src_initial == "locked":
        _set_src_locked(chain)
    elif src_initial == "flap":
        _set_src_flap_fixture(chain)
    else:
        raise AssertionError(f"unhandled src_initial fixture: {src_initial!r}")
    assert chain.read_reg(CONTROL_IR_PROFILE_ADDR) == IR_ADDR_HYPEX
    assert chain.read_reg(CONTROL_IR_PROFILE_POWER) == IR_CMD_POWER
    assert chain.read_reg(CONTROL_IR_PROFILE_MUTE) == IR_CMD_MUTE
    return chain


def _send_ir(chain: Chain, cmd: int, *, settle_ticks: int = 8_000_000) -> None:
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=cmd)
    chain.step_ticks(settle_ticks)


def _cmd03_filename_payload(text: str) -> bytes:
    raw = text.encode("ascii", errors="replace")[:FILENAME_LEN]
    return raw + bytes([0xFF]) * (FILENAME_LEN - len(raw))


def _firmware_filename_write(chain: Chain, unit: int, name: str) -> None:
    report = bytearray(HID_REPORT_LEN)
    report[0] = 0x03
    report[1] = CMD03_FILENAME_WRITE
    payload = _cmd03_filename_payload(name)
    report[2 : 2 + len(payload)] = payload
    chain.firmware_hid_report(unit, report, max_steps=60_000)
    chain.step_ticks(4_000_000)


def _firmware_filename_read(chain: Chain, unit: int) -> None:
    report = bytearray(HID_REPORT_LEN)
    report[0] = 0x03
    report[1] = CMD03_FILENAME_READ
    chain.firmware_hid_report(unit, report, max_steps=60_000)
    chain.step_ticks(2_000_000)


def _coeff_image(chain: Chain, unit: int) -> bytes:
    return bytes(
        chain.read_main_dsp_reg(unit, subaddr)
        for subaddr in range(TAS_BIQUAD_FIRST, TAS_BIQUAD_LAST + 1)
    )


def _first_diff(expected: bytes, observed: bytes) -> tuple[int, int, int] | None:
    for offset, (want, got) in enumerate(zip(expected, observed, strict=True)):
        if want != got:
            return TAS_BIQUAD_FIRST + offset, want, got
    return None


def _tas_volume_regs(chain: Chain, unit: int) -> bytes:
    return bytes(
        chain.read_main_dsp_reg(unit, TAS_MASTER_VOLUME + offset)
        for offset in range(4)
    )


def _tas30_write_payload(chain: Chain, unit: int) -> bytes:
    return chain.read_main_dsp_write_payload(unit, TAS_MASTER_VOLUME) or b""


def _tas30(chain: Chain, unit: int) -> bytes:
    return _tas_volume_regs(chain, unit)


def _src_effectively_live(chain: Chain, unit: int) -> bool:
    # RXCKR=0 with UNLOCK=0 is a locked estimator hole, not hard loss.
    return (
        chain.read_main_src4382_reg(unit, SRC_NON_PCM) == 0
        and chain.read_main_src4382_reg(unit, SRC_UNLOCK) == 0
    )


def _learn_clean_images() -> dict[bool, list[bytes]]:
    chain = _new_chain()
    _send_ir(chain, IR_CMD_PRESET_B)
    chain.step_ticks(260_000_000)
    assert all(chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE) == 0 for unit in (0, 1))
    clean_b = [_coeff_image(chain, unit) for unit in (0, 1)]
    _send_ir(chain, IR_CMD_PRESET_A)
    chain.step_ticks(260_000_000)
    assert all(chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE) == 0 for unit in (0, 1))
    clean_a = [_coeff_image(chain, unit) for unit in (0, 1)]
    return {False: clean_a, True: clean_b}


def _learn_clean_a_images() -> list[bytes]:
    return _learn_clean_images()[False]


def _live_wrong_coeff_units(
    chain: Chain,
    expected_images: dict[bool, list[bytes]],
) -> list[dict[str, object]]:
    wrong: list[dict[str, object]] = []
    for unit in (0, 1):
        active = chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS)
        preset_b = bool(active & MAIN_ACTIVE_PRESET_B)
        expected = expected_images[preset_b][unit]
        src_live = (
            chain.read_main_src4382_reg(unit, SRC_NON_PCM) == 0
            and chain.read_main_src4382_reg(unit, SRC_RX_STATUS) != 0
            and chain.read_main_src4382_reg(unit, SRC_UNLOCK) == 0
        )
        fault_flags = chain.read_main_reg(unit, MAIN_DSP_FAULT_FLAGS)
        image = _coeff_image(chain, unit)
        live_committed = (
            (active & MAIN_ACTIVE_GATE)
            and not (active & MAIN_ACTIVE_MUTE)
            and chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE) == 0
            and (fault_flags & (MAIN_DSP_FAULT_MASK | MAIN_DSP_ACKSTAT_MASK)) == 0
            and bool(int.from_bytes(_tas_volume_regs(chain, unit), "big"))
            and src_live
        )
        if live_committed and image != expected:
            wrong.append(
                {
                    "unit": unit,
                    "preset": "B" if preset_b else "A",
                    "active": active,
                    "job_index": chain.read_main_reg(unit, MAIN_PRESET_JOB_INDEX),
                    "job_target": chain.read_main_reg(unit, MAIN_PRESET_JOB_TARGET),
                    "job_flags": chain.read_main_reg(unit, MAIN_PRESET_JOB_FLAGS),
                    "tas30_regs": _tas_volume_regs(chain, unit).hex(),
                    "tas30_write": _tas30_write_payload(chain, unit).hex(),
                    "expected": _digest(expected),
                    "observed": _digest(image),
                    "first_diff": _first_diff(expected, image),
                    "lcd": chain.lcd_lines(),
                }
            )
    return wrong


def _sample_live_wrong_coeff_units(
    chain: Chain,
    expected_images: dict[bool, list[bytes]],
    *,
    samples: int = 240,
    ticks: int = 250_000,
) -> list[dict[str, object]]:
    wrong: list[dict[str, object]] = []
    for sample in range(samples):
        for item in _live_wrong_coeff_units(chain, expected_images):
            item["sample"] = sample
            wrong.append(item)
        chain.step_ticks(ticks)
    return wrong


def _inject_lifecycle_reassert_fault(chain: Chain, fault_kind: str) -> list[tuple[int, bytes]]:
    patched_headers: list[tuple[int, bytes]] = []
    for unit, core_idx in ((0, CORE_MAIN0), (1, CORE_MAIN1)):
        if fault_kind == "address-nack":
            chain.inject_main_tas3108_address_nack(unit, 60_000)
        elif fault_kind == "data-nack":
            chain.inject_main_tas3108_data_nack(unit, 60_000)
        elif fault_kind == "header-mismatch":
            original = chain.read_core_flash(core_idx, PRESET_A_ROW_25, 4)
            assert original == ROW_25_GOOD_HEADER, {
                "unit": unit,
                "core_idx": core_idx,
                "header": original.hex(),
            }
            chain.patch_core_flash(core_idx, PRESET_A_ROW_25 + 1, bytes([ROW_25_BAD_REG]))
            patched_headers.append((core_idx, original))
        elif fault_kind == "stop-timeout":
            chain.set_main_mssp_stop_fault(
                unit,
                stop_busy_cycles=5_000_000,
                stop_busy_count=-1,
            )
        else:
            raise AssertionError(f"unhandled fault kind: {fault_kind}")
    return patched_headers


def _clear_lifecycle_reassert_fault(
    chain: Chain,
    fault_kind: str,
    patched_headers: list[tuple[int, bytes]],
) -> None:
    for core_idx, original in patched_headers:
        chain.patch_core_flash(core_idx, PRESET_A_ROW_25, original)
    for unit in (0, 1):
        chain.inject_main_tas3108_address_nack(unit, 0)
        chain.inject_main_tas3108_data_nack(unit, 0)
        chain.clear_main_mssp_stop_faults(unit)
        chain.force_reset_main_mssp_unit(unit)


def test_session5_power_toggle_never_restores_live_audio_on_wrong_a_coefficients() -> None:
    expected = _learn_clean_images()
    chain = _new_chain(seed_session5_names=True, reset_source="mclr")

    chain.press("STBY")
    chain.step_ticks(7_999_364)
    chain.press("STBY")
    _send_ir(chain, IR_CMD_POWER)
    chain.step_ticks(1_581_503)
    _send_ir(chain, IR_CMD_POWER)

    wrong = _sample_live_wrong_coeff_units(chain, expected, samples=120)
    _send_ir(chain, IR_CMD_VOLUME_UP, settle_ticks=20_000_000)
    wrong.extend(_sample_live_wrong_coeff_units(chain, expected, samples=80))
    assert not wrong, wrong


def test_reconnect_reassert_never_restores_live_audio_on_wrong_coefficients() -> None:
    expected = _learn_clean_images()
    chain = _new_chain(seed_session5_names=True, reset_source="mclr")

    for unit in (0, 1):
        chain.write_main_reg(
            unit,
            MAIN_EVENT_FLAGS,
            chain.read_main_reg(unit, MAIN_EVENT_FLAGS) | MAIN_EVENT_ROUTE_DIRTY,
        )
        chain.write_main_reg(
            unit,
            MAIN_ACTIVE_FLAGS,
            chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) | MAIN_REAPPLY_PENDING,
        )

    wrong = _sample_live_wrong_coeff_units(chain, expected, samples=360, ticks=1_000_000)
    _send_ir(chain, IR_CMD_VOLUME_UP, settle_ticks=20_000_000)
    wrong.extend(_sample_live_wrong_coeff_units(chain, expected, samples=80))
    assert not wrong, wrong


def _assert_lifecycle_fault_keeps_audio_safe(chain: Chain, expected: dict[bool, list[bytes]]) -> None:
    wrong = _sample_live_wrong_coeff_units(chain, expected, samples=160, ticks=1_000_000)
    assert not wrong, wrong
    for unit in (0, 1):
        active = chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS)
        faults = chain.read_main_reg(unit, MAIN_DSP_FAULT_FLAGS)
        assert (
            (active & MAIN_ACTIVE_MUTE)
            or (faults & (MAIN_DSP_FAULT_MASK | MAIN_DSP_ACKSTAT_MASK))
            or not int.from_bytes(_tas_volume_regs(chain, unit), "big")
        ), {
            "unit": unit,
            "active": active,
            "faults": faults,
            "tas30_regs": _tas_volume_regs(chain, unit).hex(),
            "tas30_write": _tas30_write_payload(chain, unit).hex(),
            "lcd": chain.lcd_lines(),
        }


@pytest.mark.parametrize(
    "fault_kind",
    [
        "address-nack",
        "data-nack",
        "header-mismatch",
        "stop-timeout",
    ],
)
def test_wake_lifecycle_reassert_failure_keeps_audio_muted_until_validated_reapply(
    fault_kind: str,
) -> None:
    expected = _learn_clean_images()
    chain = _new_chain(seed_session5_names=True, reset_source="mclr")
    patched_headers = _inject_lifecycle_reassert_fault(chain, fault_kind)

    chain.press("STBY")
    chain.step_ticks(20_000_000)
    chain.press("STBY")
    _assert_lifecycle_fault_keeps_audio_safe(chain, expected)

    _clear_lifecycle_reassert_fault(chain, fault_kind, patched_headers)
    _send_ir(chain, IR_CMD_VOLUME_UP, settle_ticks=40_000_000)
    assert not _live_wrong_coeff_units(chain, expected)


@pytest.mark.parametrize(
    "fault_kind",
    [
        "address-nack",
        "data-nack",
        "header-mismatch",
        "stop-timeout",
    ],
)
def test_reconnect_lifecycle_reassert_failure_keeps_audio_muted_until_validated_reapply(
    fault_kind: str,
) -> None:
    expected = _learn_clean_images()
    chain = _new_chain(seed_session5_names=True, reset_source="mclr")
    patched_headers = _inject_lifecycle_reassert_fault(chain, fault_kind)
    for unit in (0, 1):
        chain.write_main_reg(
            unit,
            MAIN_EVENT_FLAGS,
            chain.read_main_reg(unit, MAIN_EVENT_FLAGS) | MAIN_EVENT_ROUTE_DIRTY,
        )
        chain.write_main_reg(
            unit,
            MAIN_ACTIVE_FLAGS,
            chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) | MAIN_REAPPLY_PENDING,
        )

    _assert_lifecycle_fault_keeps_audio_safe(chain, expected)

    _clear_lifecycle_reassert_fault(chain, fault_kind, patched_headers)
    _send_ir(chain, IR_CMD_VOLUME_UP, settle_ticks=40_000_000)
    assert not _live_wrong_coeff_units(chain, expected)


def test_field7_preset_phase_sweep_never_leaves_live_audio_on_wrong_coefficients() -> None:
    expected = _learn_clean_images()
    chain = _new_chain(reset_source="por")

    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_PRESET_B)
    chain.step_ticks(160_000_000)
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_PRESET_A)
    chain.step_ticks(160_000_000)
    chain.step_ticks(12_174_408)

    wrong = _sample_live_wrong_coeff_units(chain, expected, samples=80, ticks=250_000)
    assert not wrong, wrong


def _main_visible_fault_or_lost(chain: Chain, unit: int) -> bool:
    active = chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS)
    fault_flags = chain.read_main_reg(unit, MAIN_DSP_FAULT_FLAGS)
    lcd = " ".join(chain.lcd_lines()).upper()
    visible = (
        chain.is_waiting()
        or "WAITING" in lcd
        or "ZZZ" in lcd
        or "FAULT" in lcd
        or "LOST" in lcd
        or "OLD" in lcd
        or "N/A" in lcd
    )
    return (
        visible
        and (
            not chain.is_connected()
            or not (active & MAIN_ACTIVE_GATE)
            or bool(fault_flags & (MAIN_DSP_FAULT_MASK | MAIN_DSP_ACKSTAT_MASK))
        )
    )


def _preset_mismatches(chain: Chain) -> list[dict[str, object]]:
    control_b = bool(chain.read_reg(CONTROL_FLAGS) & CONTROL_PRESET_B_MASK)
    mismatches: list[dict[str, object]] = []
    for unit in (0, 1):
        active = chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS)
        main_b = bool(active & MAIN_ACTIVE_PRESET_B)
        if main_b != control_b and not _main_visible_fault_or_lost(chain, unit):
            mismatches.append(
                {
                    "unit": unit,
                    "control_preset": "B" if control_b else "A",
                    "main_preset": "B" if main_b else "A",
                    "active": active,
                    "job_state": chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE),
                    "job_target": chain.read_main_reg(unit, MAIN_PRESET_JOB_TARGET),
                    "digest": _digest(_coeff_image(chain, unit)),
                    "lcd": chain.lcd_lines(),
                }
            )
    return mismatches


def _mute_mismatches(chain: Chain) -> list[dict[str, object]]:
    control_muted = bool(chain.read_reg(CONTROL_FLAGS) & CONTROL_MUTE_MASK)
    mismatches: list[dict[str, object]] = []
    for unit in (0, 1):
        active = chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS)
        main_muted = bool(active & MAIN_ACTIVE_MUTE)
        tas30 = _tas30(chain, unit)
        audio_safe_when_muted = (
            not (active & MAIN_ACTIVE_GATE)
            or not _src_effectively_live(chain, unit)
            or not int.from_bytes(tas30, "big")
        )
        mismatch = (
            (main_muted != control_muted)
            or (control_muted and not audio_safe_when_muted)
        )
        if mismatch and not _main_visible_fault_or_lost(chain, unit):
            mismatches.append(
                {
                    "unit": unit,
                    "control_muted": control_muted,
                    "main_muted": main_muted,
                    "active": active,
                    "job_state": chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE),
                    "job_target": chain.read_main_reg(unit, MAIN_PRESET_JOB_TARGET),
                    "tas30": tas30.hex(),
                    "src_effectively_live": _src_effectively_live(chain, unit),
                    "digest": _digest(_coeff_image(chain, unit)),
                    "lcd": chain.lcd_lines(),
                }
            )
    return mismatches


def _field8_value_mismatches(chain: Chain) -> list[dict[str, object]]:
    return [
        {"kind": "preset", **item}
        for item in _preset_mismatches(chain)
    ] + [
        {"kind": "mute", **item}
        for item in _mute_mismatches(chain)
    ]


def _unresolved_field8_mismatches_over_bound(
    chain: Chain,
    mismatch_fn,
    *,
    attempts: int = 20,
    ticks: int = 1_000_000,
) -> list[dict[str, object]]:  # type: ignore[no-untyped-def]
    mismatches: list[dict[str, object]] = []
    for sample in range(attempts + 1):
        mismatches = mismatch_fn(chain)
        if not mismatches:
            return []
        for item in mismatches:
            item["sample"] = sample
        chain.step_ticks(ticks)
    return mismatches


def _setup_field8_session15_prefix() -> Chain:
    chain = Chain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX),
        main_hex_path=str(V34_MAIN_HEX),
    )
    _seed_filename_slots(
        chain,
        a_pb1="bad\x01name",
        b_pb1="LX521 V15 L22MG old_NC100",
        a_pb2="",
        b_pb2="",
    )
    chain.apply_reset_all("bor")
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()
    _set_src_flap_fixture(chain)
    _assert_src_flap_fixture(chain)
    assert chain.read_reg(CONTROL_IR_PROFILE_ADDR) == IR_ADDR_HYPEX
    assert chain.read_reg(CONTROL_IR_PROFILE_POWER) == IR_CMD_POWER
    assert chain.read_reg(CONTROL_IR_PROFILE_MUTE) == IR_CMD_MUTE

    chain.press("RIGHT")
    chain.press("UP")
    chain.step_ticks(1_550_321)
    _firmware_filename_write(chain, 1, "")
    chain.step_ticks(10_385_641)
    _firmware_filename_read(chain, 0)
    chain.step_ticks(5_873_614)
    _send_ir(chain, IR_CMD_PRESET_A)
    chain.step_ticks(5_446_938)
    _firmware_filename_write(chain, 0, "")
    chain.step_ticks(10_294_382)
    _firmware_filename_read(chain, 1)
    _firmware_filename_write(chain, 0, "Long preset name scroll tail first")
    chain.step_ticks(6_850_541)
    return chain


def test_field8_ir_mute_converges_control_and_both_mains_under_filename_churn() -> None:
    chain = _setup_field8_session15_prefix()

    _send_ir(chain, IR_CMD_MUTE)
    chain.step_ticks(3_202_824)

    mismatches = _unresolved_field8_mismatches_over_bound(chain, _mute_mismatches)
    assert not mismatches, mismatches


def test_field8_preset_down_converges_control_and_both_mains_under_filename_churn() -> None:
    chain = _setup_field8_session15_prefix()

    _send_ir(chain, IR_CMD_MUTE)
    chain.step_ticks(3_202_824)
    chain.press("DOWN")
    chain.step_ticks(4_813_848)

    mismatches = _unresolved_field8_mismatches_over_bound(
        chain,
        _field8_value_mismatches,
    )
    assert not mismatches, mismatches


def test_field8_asleep_preset_b_host_traffic_converges_after_wake() -> None:
    chain = _new_chain(reset_source="mclr")

    chain.press("STBY")
    chain.step_ticks(20_000_000)
    _send_ir(chain, IR_CMD_PRESET_B)
    assert chain.read_reg(CONTROL_FLAGS) & CONTROL_PRESET_B_MASK
    for unit in (0, 1):
        assert not (chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) & MAIN_ACTIVE_GATE)
        assert chain.read_main_reg(unit, MAIN_PRESET_JOB_TARGET) == 1

    assert chain.inject_host_command(cmd=0x20, data=0x00, route=0xBF)
    chain.step_ticks(6_000_000)
    chain.press("SELECT")
    chain.step_ticks(120_000_000)

    mismatches = _unresolved_field8_mismatches_over_bound(
        chain,
        _preset_mismatches,
        attempts=20,
        ticks=1_000_000,
    )
    assert not mismatches, mismatches


def _tap_key(chain: Chain, key: str) -> None:
    pins = {
        "RIGHT": ("A", 4),
        "STBY": ("A", 3),
    }
    port, bit = pins[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(5_000_000)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(5_000_000)


def _navigate_to_diag_page(chain: Chain, pb_idx: int) -> None:
    for _ in range(4 + pb_idx):
        _tap_key(chain, "RIGHT")
    target = STATE_PB1_DIAG if pb_idx == 0 else STATE_PB2_DIAG
    _wait_until(
        chain,
        lambda: chain.read_reg(CONTROL_DISPLAY_STATE) == target
        and chain.lcd_lines()[0].startswith(f"PB{pb_idx + 1}"),
        attempts=700,
        ticks=2_000_000,
    )


def _wait_until(chain: Chain, predicate, *, attempts: int, ticks: int) -> None:  # type: ignore[no-untyped-def]
    for _ in range(attempts):
        if predicate():
            return
        chain.step_ticks(ticks)
    pytest.fail(
        f"condition did not converge; lcd={chain.lcd_lines()!r} "
        f"flags=0x{chain.read_reg(CONTROL_FLAGS):02X} "
        f"display_state=0x{chain.read_reg(CONTROL_DISPLAY_STATE):02X} "
        f"gates={_main_gates(chain)}"
    )


def _main_gates(chain: Chain) -> tuple[int, int]:
    return tuple(
        1 if chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) & MAIN_ACTIVE_GATE else 0
        for unit in (0, 1)
    )


def _main_mutes(chain: Chain) -> tuple[int, int]:
    return tuple(
        1 if chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) & MAIN_ACTIVE_MUTE else 0
        for unit in (0, 1)
    )


@pytest.mark.xfail(
    strict=True,
    reason="DIAG-STBY open repro: Diagnostics pages ignore front-panel STBY",
)
@pytest.mark.parametrize("pb_idx", [0, 1], ids=["pb1-diag", "pb2-diag"])
def test_diag_page_front_panel_stby_enters_standby_and_closes_both_main_gates(
    pb_idx: int,
) -> None:
    chain = _new_chain()
    _navigate_to_diag_page(chain, pb_idx)

    chain.press("STBY")

    _wait_until(
        chain,
        lambda: "ZZZ" in chain.lcd_lines()[0].upper(),
        attempts=120,
        ticks=2_000_000,
    )
    _wait_until(chain, lambda: _main_gates(chain) == (0, 0), attempts=180, ticks=2_000_000)


@pytest.mark.parametrize("pb_idx", [0, 1], ids=["pb1-diag", "pb2-diag"])
def test_diag_page_ir_standby_wake_closes_and_reopens_both_main_gates(
    pb_idx: int,
) -> None:
    chain = _new_chain()
    _navigate_to_diag_page(chain, pb_idx)

    before = len(chain.tx_frames())
    _send_ir(chain, IR_CMD_STANDBY, settle_ticks=20_000_000)
    frames = [tuple(frame) for frame in chain.tx_frames()[before:]]

    assert (0xB0, 0x03, 0x00) in frames
    _wait_until(
        chain,
        lambda: "ZZZ" in chain.lcd_lines()[0].upper(),
        attempts=120,
        ticks=2_000_000,
    )
    _wait_until(chain, lambda: _main_gates(chain) == (0, 0), attempts=180, ticks=2_000_000)

    before = len(chain.tx_frames())
    _send_ir(chain, IR_CMD_WAKE, settle_ticks=20_000_000)
    frames = [tuple(frame) for frame in chain.tx_frames()[before:]]

    assert (0xB0, 0x03, 0x01) in frames
    _wait_until(
        chain,
        lambda: (
            chain.is_connected()
            and bool(chain.read_reg(CONTROL_FLAGS) & CONTROL_CONNECTED_MASK)
            and "ZZZ" not in chain.lcd_lines()[0].upper()
        ),
        attempts=180,
        ticks=2_000_000,
    )
    _wait_until(chain, lambda: _main_gates(chain) == (1, 1), attempts=240, ticks=2_000_000)


@pytest.mark.parametrize("pb_idx", [0, 1], ids=["pb1-diag", "pb2-diag"])
def test_diag_page_ir_mute_mutes_control_and_both_mains(pb_idx: int) -> None:
    chain = _new_chain()
    _navigate_to_diag_page(chain, pb_idx)

    before = len(chain.tx_frames())
    _send_ir(chain, IR_CMD_MUTE, settle_ticks=20_000_000)
    frames = [tuple(frame) for frame in chain.tx_frames()[before:]]

    assert (0xB0, 0x03, 0x02) in frames
    assert chain.read_reg(CONTROL_FLAGS) & CONTROL_MUTE_MASK
    _wait_until(chain, lambda: _main_mutes(chain) == (1, 1), attempts=120, ticks=2_000_000)
    for unit in (0, 1):
        assert _tas30(chain, unit) in (b"", b"\x00\x00\x00\x00"), {
            "unit": unit,
            "tas30": _tas30(chain, unit).hex(),
            "lcd": chain.lcd_lines(),
        }
    assert chain.lcd_lines()[0].startswith(f"PB{pb_idx + 1}"), chain.lcd_lines()
