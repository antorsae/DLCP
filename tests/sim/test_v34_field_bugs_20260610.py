"""Regressions for the 2026-06-10 live-flash field incident.

Ledger: docs/V34_FIELD_BUGS_20260610.md.  Four field issues, five defects:

- FIELD-1  flasher post-flash reconnect abort (string-less device never
           classified as app; fixed: identity-probe promotion, event-driven
           wait with 60 s ceiling, --finalize-only recovery)
- FIELD-2  IR profile left on standard-RC5 (consequence of FIELD-1 plus the
           unclamped EEPROM[0x0E] write paths)
- FIELD-3  Preset page row 0 blank after STBY/WAKE while parked on the page
- FIELD-4A preset table apply silently skips NACKed coefficient writes and
           COMMITs/unmutes a wrong DSP image with no fault surfaced (SAFETY)
- FIELD-4B COMMIT restores volume while the post-switch route/mixer DSP
           stage is still queued (audio live through a half-reconfigured DSP)

All tests green: the FIELD-3/4A/4B firmware fixes and the FIELD-1 flasher
fixes are implemented; this file pins them.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

import dlcp_fw.flash.dlcp_main_flash as main_flash
from dlcp_fw.paths import V17_CONTROL_RAM_INC, V173_CONTROL_ASM, V34_MAIN_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17
from dlcp_fw.sim.v30_symbols import assemble_v30
from tests.sim.test_v34_mute_refresh_bug import (
    _boot_v34_main,
    _inject_frame,
)

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    RustChain = None  # type: ignore[assignment]
    _RUST_CHAIN_IMPORT_ERROR = exc

PRESET_JOB_STATE = 0x2DE
DIAG_I = 0x2E5
DIAG_R = 0x2E9
DSP_FAULT_FLAGS = 0x07F
EVENT_FLAGS = 0x07E
ACTIVE_FLAGS = 0x05E
STOCK_094 = 0x094
SETUP_PROFILE_RAM = 0x0B8
SETUP_PROFILE_EEPROM = 0x0E
VALID_PROFILE_VALUES = {0x03, 0x04}
FILENAME_RAM_BASE = 0x02C0
RX_RING_WR = 0x0C7

ACTIVE_GATE_MASK = 0x08
ACTIVE_MUTE_MASK = 0x10
ACTIVE_FAULT_MUTE_OWNER_MASK = 0x20
USER_MUTE_LATCH_MASK = 0x20
LATE_BIT1_PENDING_MASK = 0x02
VOLUME_DIRTY_MASK = 0x08
FIELD10_BARRIER_PENDING_MASK = 0x40
DSP_ACKSTAT_MASK = 0x04
DSP_FAULT_MASK = 0x40
STANDBY_SETTLE_TICKS = 12_000_000
WAKE_SETTLE_TICKS = 2_000_000
SRC_NON_PCM_REG = 0x12
SRC_RX_STATUS_REG = 0x13
SRC_UNLOCK_REG = 0x14


# --- shared fixtures ---------------------------------------------------------

@pytest.fixture(scope="module")
def field_main_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v34_field_bugs_main")
    hex_out = tmp / "DLCP_Firmware_V3.4_field.hex"
    assemble_v30(V34_MAIN_ASM, hex_out, output_lst=tmp / "DLCP_Firmware_V3.4_field.lst")
    return hex_out


@pytest.fixture(scope="module")
def field_chain_hexes(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    tmp = tmp_path_factory.mktemp("v34_field_bugs_chain")
    shutil.copy(V17_CONTROL_RAM_INC, tmp / V17_CONTROL_RAM_INC.name)
    control_asm = tmp / V173_CONTROL_ASM.name
    control_asm.write_bytes(V173_CONTROL_ASM.read_bytes())
    control_hex = tmp / "DLCP_Control_V1.73_field.hex"
    assemble_v17(control_asm, control_hex)
    main_hex = tmp / "DLCP_Firmware_V3.4_field.hex"
    assemble_v30(V34_MAIN_ASM, main_hex, output_lst=tmp / "m.lst")
    return control_hex, main_hex


def _biquad_digest(chain, *, unit: int = 0, lo: int = 0x31, hi: int = 0x91) -> str:
    return hashlib.sha256(
        bytes(chain.read_main_dsp_reg(unit, s) for s in range(lo, hi))
    ).hexdigest()[:12]


def _latest_tas30(chain, *, unit: int = 0) -> str | None:
    payloads = chain.read_main_dsp_write_payloads(unit, 0x30)
    return payloads[-1].hex() if payloads else None


def _latest_tas30_bytes(chain, *, unit: int = 0) -> bytes | None:
    payloads = chain.read_main_dsp_write_payloads(unit, 0x30)
    return payloads[-1] if payloads else None


def _coeff_image(chain, *, unit: int = 0) -> bytes:
    return bytes(chain.read_main_dsp_reg(unit, subaddr) for subaddr in range(0x37, 0x91))


def _src_live_pcm(chain, *, unit: int = 0) -> bool:
    return (
        (chain.read_main_src4382_reg(unit, SRC_RX_STATUS_REG) & 0x03) != 0
        and (chain.read_main_src4382_reg(unit, SRC_NON_PCM_REG) & 0x01) == 0
        and chain.read_main_src4382_reg(unit, SRC_UNLOCK_REG) == 0
    )


def _live_wrong_coeff_units(chain, expected: dict[int, bytes]) -> list[dict[str, object]]:
    wrong: list[dict[str, object]] = []
    for unit, expected_image in expected.items():
        active = chain.read_main_reg(unit, ACTIVE_FLAGS)
        faults = chain.read_main_reg(unit, DSP_FAULT_FLAGS)
        tas30 = _latest_tas30_bytes(chain, unit=unit)
        live = (
            bool(active & ACTIVE_GATE_MASK)
            and not bool(active & ACTIVE_MUTE_MASK)
            and chain.read_main_reg(unit, PRESET_JOB_STATE) == 0
            and not (faults & (DSP_FAULT_MASK | DSP_ACKSTAT_MASK))
            and _src_live_pcm(chain, unit=unit)
            and tas30 is not None
            and tas30 != b"\x00" * 4
        )
        observed = _coeff_image(chain, unit=unit)
        if live and observed != expected_image:
            wrong.append(
                {
                    "unit": unit,
                    "active": f"0x{active:02X}",
                    "faults": f"0x{faults:02X}",
                    "tas30": tas30.hex(),
                    "expected": hashlib.sha256(expected_image).hexdigest()[:12],
                    "observed": hashlib.sha256(observed).hexdigest()[:12],
                    "lcd": chain.lcd_lines(),
                }
            )
    return wrong


def _bad_live_volume_payloads(chain, *, unit: int = 0) -> list[bytes]:
    return [
        payload
        for payload in chain.read_main_dsp_write_payloads(unit, 0x30)
        if payload != b"\x00" * 4
    ]


def _switch_preset_and_settle(chain, target: int, *, settle_m: int = 60) -> None:
    _inject_frame(chain, 0x20, target)
    chain.step_ticks(settle_m * 1_000_000)
    assert chain.read_main_reg(0, PRESET_JOB_STATE) == 0


def _connected_field_chain(field_chain_hexes: tuple[Path, Path]):
    if RustChain is None:  # pragma: no cover
        pytest.fail(f"rust facade not importable: {_RUST_CHAIN_IMPORT_ERROR!r}")
    control_hex, main_hex = field_chain_hexes
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()
    return chain


def _set_src4382_nack(chain, *, unit: int, fault_kind: str, count: int) -> None:
    if fault_kind == "address":
        chain.inject_main_src4382_address_nack(unit, count)
    elif fault_kind == "data":
        chain.inject_main_src4382_data_nack(unit, count)
    else:  # pragma: no cover
        raise AssertionError(f"unknown fault kind {fault_kind!r}")


def _inject_unit_broadcast_frame(chain, *, unit: int, cmd: int, data: int) -> None:
    for byte in (0xB0, cmd & 0xFF, data & 0xFF):
        accepted, dropped = chain.inject_main_uart_rx_bytes(unit, bytes([byte]))
        assert (accepted, dropped) == (1, 0)
        chain.step_ticks(16_000)


def _query_cmd44_cells(chain, *, unit: int) -> list[int]:
    response, dispatch_hits = chain.firmware_hid_report(unit, [0x44] + [0x00] * 63)
    assert dispatch_hits >= 1
    assert response[0] == 0x44 and response[1] == 0x00
    assert response[2] == 0x10, f"unexpected cmd-0x44 length 0x{response[2]:02X}"
    return list(response[3:19])


def _drive_standby_then_faulted_wake(chain, *, unit: int, fault_kind: str, count: int) -> None:
    _inject_unit_broadcast_frame(chain, unit=unit, cmd=0x03, data=0x00)
    chain.step_ticks(STANDBY_SETTLE_TICKS)
    _set_src4382_nack(chain, unit=unit, fault_kind=fault_kind, count=count)
    chain.reset_main_src4382_stats(unit)
    chain.reset_main_dsp_write_log(unit)
    _inject_unit_broadcast_frame(chain, unit=unit, cmd=0x03, data=0x01)


def _wait_for_field10_barrier_pending(chain, *, unit: int) -> None:
    for _ in range(120):
        if chain.read_main_reg(unit, STOCK_094) & FIELD10_BARRIER_PENDING_MASK:
            return
        chain.step_ticks(WAKE_SETTLE_TICKS)
    flags = chain.read_main_reg(unit, DSP_FAULT_FLAGS)
    active = chain.read_main_reg(unit, ACTIVE_FLAGS)
    latch = chain.read_main_reg(unit, STOCK_094)
    raise AssertionError(
        f"MAIN{unit} never entered FIELD-10 barrier_pending "
        f"(stock_094=0x{latch:02X}, active=0x{active:02X}, dsp=0x{flags:02X})"
    )


# --- FIELD-4A: NACKed table-apply writes silently skipped (SAFETY) ----------

def test_field4a_preset_apply_with_tas_nacks_must_not_unmute_wrong_image(
    field_main_hex: Path,
) -> None:
    chain = _boot_v34_main(field_main_hex)
    chain.step_ticks(8_000_000)

    # Clean references: full A and B images through the fault-free pipeline.
    _switch_preset_and_settle(chain, 1)
    clean_b = _biquad_digest(chain)
    _switch_preset_and_settle(chain, 0)
    clean_a = _biquad_digest(chain)
    assert clean_a != clean_b, "fixture cannot distinguish preset images"

    # Fault variant: I2C data NACKs at switch time (a real-world glitch at
    # the moment of a preset change).
    chain.inject_main_tas3108_data_nack(0, 60)
    _inject_frame(chain, 0x20, 0x01)
    chain.step_ticks(120_000_000)

    digest = _biquad_digest(chain)
    tas30 = _latest_tas30(chain)
    dsp_fault = chain.read_main_reg(0, DSP_FAULT_FLAGS)
    converged = digest == clean_b
    muted_or_faulted = (tas30 in (None, "00000000")) or bool(dsp_fault & 0x40)
    assert converged or muted_or_faulted, (
        "preset apply under NACKs left audio LIVE on a wrong DSP image with "
        f"no fault: digest={digest} (clean_b={clean_b}, clean_a={clean_a}) "
        f"tas30={tas30} dsp_fault=0x{dsp_fault:02X}"
    )


# --- FIELD-4B: unmute must be the LAST stage of the switch pipeline ---------

def test_field4b_no_dsp_coefficient_writes_after_preset_unmute(
    field_main_hex: Path,
) -> None:
    chain = _boot_v34_main(field_main_hex)
    chain.step_ticks(8_000_000)

    # Learn the fully-settled B image once (fault-free).
    _switch_preset_and_settle(chain, 1)
    settled_b = _biquad_digest(chain)
    _switch_preset_and_settle(chain, 0)

    # Re-run the switch with tight sampling: from the first unmuted sample
    # onward, the DSP image must already be final.
    _inject_frame(chain, 0x20, 0x01)
    violations = []
    for i in range(400):
        chain.step_ticks(250_000)
        tas30 = _latest_tas30(chain)
        if tas30 not in (None, "00000000"):
            digest = _biquad_digest(chain)
            if digest != settled_b:
                violations.append((i, tas30, digest))
        if chain.read_main_reg(0, PRESET_JOB_STATE) == 0 and i > 200:
            break
    assert not violations, (
        "DSP coefficients still changing AFTER volume was restored "
        f"(settled_b={settled_b}): {violations[:5]}"
    )


# --- FIELD-10: wake input-route I2C must wait for post-wake device init -----

@pytest.mark.parametrize("unit", (0, 1))
def test_field10_src4382_not_ready_window_does_not_hit_during_active7_lifecycle(
    field_chain_hexes: tuple[Path, Path],
    unit: int,
) -> None:
    """A realistic short SRC4382 not-ready window must be consumed only after
    the wake lifecycle/preset-reassert phase is over, or else be made visibly
    safe by mute/fault/barrier state.

    This is the discovery-class FIELD-10 guard.  The old rev consumed the two
    address NACKs while ``active_flags.bit7`` was still set, with no mute,
    fault, or barrier ownership visible, yielding the live-hardware-style
    ``I6 R0`` fingerprint.  The test checks the runtime state machine, not the
    source shape.
    """
    chain = _connected_field_chain(field_chain_hexes)
    _drive_standby_then_faulted_wake(
        chain, unit=unit, fault_kind="address", count=2
    )

    observed_nack = False
    unsafe_samples: list[dict[str, object]] = []
    for sample in range(100):
        chain.step_ticks(WAKE_SETTLE_TICKS)
        stats = chain.read_main_src4382_stats(unit)
        consumed = int(stats["address_nacks_consumed"])
        if consumed <= 0:
            continue
        observed_nack = True
        active = chain.read_main_reg(unit, ACTIVE_FLAGS)
        events = chain.read_main_reg(unit, EVENT_FLAGS)
        dsp = chain.read_main_reg(unit, DSP_FAULT_FLAGS)
        latch = chain.read_main_reg(unit, STOCK_094)
        lifecycle_pending = bool(active & 0x80)
        visibly_safe = bool(
            (active & (ACTIVE_MUTE_MASK | ACTIVE_FAULT_MUTE_OWNER_MASK))
            or (latch & FIELD10_BARRIER_PENDING_MASK)
            or (dsp & (DSP_ACKSTAT_MASK | DSP_FAULT_MASK))
        )
        if lifecycle_pending and not visibly_safe:
            unsafe_samples.append(
                {
                    "sample": sample,
                    "consumed": consumed,
                    "remaining": int(stats["address_nack_count_remaining"]),
                    "active": f"0x{active:02X}",
                    "events": f"0x{events:02X}",
                    "dsp": f"0x{dsp:02X}",
                    "stock_094": f"0x{latch:02X}",
                    "diag_i": chain.read_main_reg(unit, DIAG_I),
                    "diag_r": chain.read_main_reg(unit, DIAG_R),
                    "tas30": [
                        p.hex()
                        for p in chain.read_main_dsp_write_payloads(unit, 0x30)[-4:]
                    ],
                }
            )
        if consumed >= 2 and int(stats["address_nack_count_remaining"]) == 0:
            break

    assert observed_nack, f"MAIN{unit} did not exercise the SRC4382 readiness window"
    assert not unsafe_samples, unsafe_samples


@pytest.mark.parametrize("fault_kind", ("address", "data"))
@pytest.mark.parametrize("unit", (0, 1))
def test_field10_faulted_wake_barrier_keeps_main_muted_and_fault_visible(
    field_chain_hexes: tuple[Path, Path],
    unit: int,
    fault_kind: str,
) -> None:
    chain = _connected_field_chain(field_chain_hexes)
    _drive_standby_then_faulted_wake(
        chain, unit=unit, fault_kind=fault_kind, count=1000
    )

    _wait_for_field10_barrier_pending(chain, unit=unit)

    stats = chain.read_main_src4382_stats(unit)
    active = chain.read_main_reg(unit, ACTIVE_FLAGS)
    events = chain.read_main_reg(unit, EVENT_FLAGS)
    dsp = chain.read_main_reg(unit, DSP_FAULT_FLAGS)
    stock_094 = chain.read_main_reg(unit, STOCK_094)
    assert stats[f"{fault_kind}_nacks_consumed"] > 0, stats
    assert stock_094 & FIELD10_BARRIER_PENDING_MASK, (
        f"MAIN{unit} did not preserve barrier_pending: stock_094=0x{stock_094:02X}"
    )
    assert active & ACTIVE_MUTE_MASK, f"MAIN{unit} not forced muted: active=0x{active:02X}"
    assert active & ACTIVE_FAULT_MUTE_OWNER_MASK, (
        f"MAIN{unit} lost fault mute ownership: active=0x{active:02X}"
    )
    assert events & LATE_BIT1_PENDING_MASK, (
        f"MAIN{unit} did not preserve late bit1 retry: events=0x{events:02X}"
    )
    assert not (events & VOLUME_DIRTY_MASK), (
        f"MAIN{unit} left stale volume dirty while barrier failed: events=0x{events:02X}"
    )
    assert dsp & DSP_FAULT_MASK, f"MAIN{unit} did not surface BF/08 fault: dsp=0x{dsp:02X}"
    assert not _bad_live_volume_payloads(chain, unit=unit), (
        f"MAIN{unit} restored live volume while wake barrier was failed: "
        f"{[p.hex() for p in chain.read_main_dsp_write_payloads(unit, 0x30)[-6:]]}"
    )


@pytest.mark.parametrize("unit", (0, 1))
def test_field10_barrier_retry_recovers_and_only_then_restores_volume(
    field_chain_hexes: tuple[Path, Path],
    unit: int,
) -> None:
    chain = _connected_field_chain(field_chain_hexes)
    _drive_standby_then_faulted_wake(chain, unit=unit, fault_kind="address", count=1000)
    _wait_for_field10_barrier_pending(chain, unit=unit)

    chain.inject_main_src4382_address_nack(unit, 0)
    chain.reset_main_dsp_write_log(unit)
    for _ in range(160):
        chain.step_ticks(WAKE_SETTLE_TICKS)
        stock_094 = chain.read_main_reg(unit, STOCK_094)
        dsp = chain.read_main_reg(unit, DSP_FAULT_FLAGS)
        live = _bad_live_volume_payloads(chain, unit=unit)
        if not (stock_094 & FIELD10_BARRIER_PENDING_MASK) and not (dsp & (DSP_FAULT_MASK | DSP_ACKSTAT_MASK)) and live:
            break
    else:
        stock_094 = chain.read_main_reg(unit, STOCK_094)
        active = chain.read_main_reg(unit, ACTIVE_FLAGS)
        events = chain.read_main_reg(unit, EVENT_FLAGS)
        dsp = chain.read_main_reg(unit, DSP_FAULT_FLAGS)
        raise AssertionError(
            f"MAIN{unit} did not recover from FIELD-10 barrier retry: "
            f"stock_094=0x{stock_094:02X} active=0x{active:02X} "
            f"events=0x{events:02X} dsp=0x{dsp:02X} "
            f"tas30={[p.hex() for p in chain.read_main_dsp_write_payloads(unit, 0x30)[-6:]]}"
        )

    active = chain.read_main_reg(unit, ACTIVE_FLAGS)
    stock_094 = chain.read_main_reg(unit, STOCK_094)
    assert not (stock_094 & FIELD10_BARRIER_PENDING_MASK)
    assert not (active & ACTIVE_MUTE_MASK), f"MAIN{unit} stayed fault-muted: 0x{active:02X}"
    assert not (active & ACTIVE_FAULT_MUTE_OWNER_MASK), (
        f"MAIN{unit} kept automatic mute ownership after recovery: 0x{active:02X}"
    )


def test_field10_barrier_retry_preserves_user_mute_until_explicit_unmute(
    field_chain_hexes: tuple[Path, Path],
) -> None:
    unit = 0
    chain = _connected_field_chain(field_chain_hexes)
    _inject_unit_broadcast_frame(chain, unit=unit, cmd=0x03, data=0x02)
    chain.step_ticks(12_000_000)
    assert chain.read_main_reg(unit, STOCK_094) & USER_MUTE_LATCH_MASK

    _drive_standby_then_faulted_wake(chain, unit=unit, fault_kind="address", count=1000)
    _wait_for_field10_barrier_pending(chain, unit=unit)
    chain.inject_main_src4382_address_nack(unit, 0)
    chain.reset_main_dsp_write_log(unit)
    for _ in range(160):
        chain.step_ticks(WAKE_SETTLE_TICKS)
        stock_094 = chain.read_main_reg(unit, STOCK_094)
        dsp = chain.read_main_reg(unit, DSP_FAULT_FLAGS)
        if not (stock_094 & FIELD10_BARRIER_PENDING_MASK) and not (dsp & DSP_ACKSTAT_MASK):
            break
    else:
        raise AssertionError("FIELD-10 barrier did not recover under user mute")

    active = chain.read_main_reg(unit, ACTIVE_FLAGS)
    stock_094 = chain.read_main_reg(unit, STOCK_094)
    assert stock_094 & USER_MUTE_LATCH_MASK
    assert active & ACTIVE_MUTE_MASK
    assert not _bad_live_volume_payloads(chain, unit=unit), (
        "FIELD-10 recovery restored live volume despite user mute"
    )

    _inject_unit_broadcast_frame(chain, unit=unit, cmd=0x03, data=0x03)
    chain.step_ticks(12_000_000)
    assert not (chain.read_main_reg(unit, STOCK_094) & USER_MUTE_LATCH_MASK)
    assert _bad_live_volume_payloads(chain, unit=unit), (
        "explicit user unmute after FIELD-10 recovery did not restore live volume"
    )


def test_field10_active7_zero_mute_nack_does_not_start_live_reapply(
    field_chain_hexes: tuple[Path, Path],
) -> None:
    chain = _connected_field_chain(field_chain_hexes)
    for unit in (0, 1):
        chain.poke_main_src4382_reg(unit, SRC_NON_PCM_REG, 0x00)
        chain.poke_main_src4382_reg(unit, SRC_RX_STATUS_REG, 0x01)
        chain.poke_main_src4382_reg(unit, SRC_UNLOCK_REG, 0x00)
    chain.step_ticks(30_000_000)
    expected = {unit: _coeff_image(chain, unit=unit) for unit in (0, 1)}
    assert _latest_tas30_bytes(chain, unit=0) not in (None, b"\x00" * 4)

    chain.press("RIGHT")
    chain.step_ticks(20_000_000)
    chain.inject_main_tas3108_data_nack(0, 2)
    chain.press("STBY")
    chain.step_ticks(20_000_000)
    chain.press("STBY")

    wrong = []
    for sample in range(120):
        for item in _live_wrong_coeff_units(chain, expected):
            item["sample"] = sample
            wrong.append(item)
        chain.step_ticks(250_000)
    assert not wrong, wrong

    stats = chain.read_main_tas3108_stats(0)
    assert stats["data_nacks_consumed"] >= 2, stats


def test_field10_clean_boot_and_standby_wake_keep_cmd44_i0(
    field_chain_hexes: tuple[Path, Path],
) -> None:
    chain = _connected_field_chain(field_chain_hexes)

    for unit in (0, 1):
        cells = _query_cmd44_cells(chain, unit=unit)
        assert cells[0] == 0 and cells[4] == 0, (unit, cells)
        assert chain.read_main_reg(unit, DIAG_I) == 0
        assert chain.read_main_reg(unit, DIAG_R) == 0

    chain.press("STBY")
    chain.step_ticks(20_000_000)
    chain.press("STBY")
    for _ in range(200):
        if chain.is_connected() and not chain.is_waiting():
            break
        chain.step_ticks(WAKE_SETTLE_TICKS)
    chain.step_ticks(30_000_000)

    for unit in (0, 1):
        cells = _query_cmd44_cells(chain, unit=unit)
        assert cells[0] == 0 and cells[4] == 0, (unit, cells)
        assert cells[2] >= 1 and cells[3] >= 1, (unit, cells)
        assert chain.read_main_reg(unit, DIAG_I) == 0
        assert chain.read_main_reg(unit, DIAG_R) == 0


def test_field10_late_bit1_nack_is_retryable_before_volume_restore(
    field_chain_hexes: tuple[Path, Path],
) -> None:
    unit = 0
    chain = _connected_field_chain(field_chain_hexes)
    chain.step_ticks(20_000_000)

    chain.write_main_reg(unit, EVENT_FLAGS, chain.read_main_reg(unit, EVENT_FLAGS) | LATE_BIT1_PENDING_MASK)
    chain.inject_main_src4382_data_nack(unit, 1000)
    volume_data = (chain.read_main_reg(unit, 0x066) + 0x60) & 0xFF
    _inject_unit_broadcast_frame(chain, unit=unit, cmd=0x07, data=volume_data)
    chain.step_ticks(10_000_000)

    stats = chain.read_main_src4382_stats(unit)
    active = chain.read_main_reg(unit, ACTIVE_FLAGS)
    events = chain.read_main_reg(unit, EVENT_FLAGS)
    dsp = chain.read_main_reg(unit, DSP_FAULT_FLAGS)
    assert stats["data_nacks_consumed"] > 0, stats
    assert active & ACTIVE_MUTE_MASK, f"late bit1 failure did not mute: active=0x{active:02X}"
    assert active & ACTIVE_FAULT_MUTE_OWNER_MASK, (
        f"late bit1 failure lost automatic mute owner: active=0x{active:02X}"
    )
    assert events & LATE_BIT1_PENDING_MASK, f"late bit1 retry not preserved: events=0x{events:02X}"
    assert dsp & DSP_FAULT_MASK, f"late bit1 failure did not surface BF/08: dsp=0x{dsp:02X}"

    chain.inject_main_src4382_data_nack(unit, 0)
    _inject_unit_broadcast_frame(chain, unit=unit, cmd=0x07, data=volume_data)
    for _ in range(120):
        chain.step_ticks(WAKE_SETTLE_TICKS)
        events = chain.read_main_reg(unit, EVENT_FLAGS)
        dsp = chain.read_main_reg(unit, DSP_FAULT_FLAGS)
        if not (events & LATE_BIT1_PENDING_MASK) and not (dsp & (DSP_FAULT_MASK | DSP_ACKSTAT_MASK)):
            break
    else:
        raise AssertionError(
            f"late bit1 retry did not recover: active=0x{chain.read_main_reg(unit, ACTIVE_FLAGS):02X} "
            f"events=0x{events:02X} dsp=0x{dsp:02X}"
        )

    active = chain.read_main_reg(unit, ACTIVE_FLAGS)
    assert not (active & ACTIVE_MUTE_MASK), f"late bit1 recovery stayed muted: active=0x{active:02X}"
    assert _bad_live_volume_payloads(chain, unit=unit), (
        "volume was not restored after late bit1 recovered cleanly"
    )


# --- FIELD-3: Preset page row 0 blank after STBY/WAKE while parked ----------

def test_field3_preset_page_row0_survives_standby_wake_while_parked(
    field_chain_hexes: tuple[Path, Path],
) -> None:
    if RustChain is None:  # pragma: no cover
        pytest.fail(f"rust facade not importable: {_RUST_CHAIN_IMPORT_ERROR!r}")
    control_hex, main_hex = field_chain_hexes
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    assert chain.run_until_connected(limit=300) < 300
    chain.press("RIGHT")
    chain.step_ticks(30_000_000)
    assert chain.lcd_lines()[0].startswith("Preset"), chain.lcd_lines()

    chain.press("STBY")
    assert "ZZZ" in chain.lcd_lines()[0].upper(), chain.lcd_lines()
    chain.press("STBY")
    for _ in range(80):
        if not chain.is_waiting():
            break
        chain.step_ticks(2_000_000)
    chain.step_ticks(30_000_000)

    row0, row1 = chain.lcd_lines()
    assert row0.startswith("Preset"), (
        f"Preset page row 0 lost after standby/wake: {(row0, row1)!r}"
    )
    if row1.strip():
        assert row0.strip(), f"row 1 renders over a blank row 0: {(row0, row1)!r}"


# --- FIELD-2: EEPROM[0x0E] profile byte must never accept garbage -----------

def test_field2_serial_cmd1d_garbage_must_not_corrupt_profile(
    field_main_hex: Path,
) -> None:
    """Green invariant pin: a garbage serial ``B0/1D/0xFF`` must not corrupt
    the profile mirror or its EEPROM[0x0E] backing byte (an out-of-range
    persisted byte becomes 0x03 = standard RC5 at the next boot's clamp,
    killing the Hypex remote).  Sim evidence 2026-06-10: the current V3.4
    serial path already rejects/ignores this vector -- this test guards that
    it stays true.  The HID setup-byte write path
    (``hid_command_dispatch__opcode04_stage_fault_action``, report byte -> RAM 0x0B8 unclamped)
    remains an open hardening item tracked in docs/V34_FIELD_BUGS_20260610.md.
    """
    chain = _boot_v34_main(field_main_hex)
    chain.step_ticks(8_000_000)
    before_ram = chain.read_main_reg(0, SETUP_PROFILE_RAM)
    assert before_ram in VALID_PROFILE_VALUES

    _inject_frame(chain, 0x1D, 0xFF)
    chain.step_ticks(120_000_000)  # let any dirty-service persist run

    ram = chain.read_main_reg(0, SETUP_PROFILE_RAM)
    eeprom = chain.read_main_eeprom_byte(0, SETUP_PROFILE_EEPROM)
    assert ram in VALID_PROFILE_VALUES, f"profile RAM mirror corrupted: 0x{ram:02X}"
    assert eeprom in VALID_PROFILE_VALUES, (
        f"EEPROM[0x0E] corrupted: 0x{eeprom:02X} -- next boot clamps this to RC5"
    )


# --- FIELD-1: flasher reconnect classification + recovery (implemented) -----

class _Dev:
    def __init__(self, path: bytes, product: str, serial: str = "") -> None:
        self.path = path
        self.product_string = product
        self.manufacturer_string = ""
        self.serial_number = serial


def test_field1_wait_for_app_accepts_stringless_device_via_identity_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev = _Dev(b"/dev/hid-stringless", "")
    monkeypatch.setattr(main_flash, "enumerate_devices", lambda vid, pid: [dev])
    monkeypatch.setattr(main_flash, "_probe_path_is_app", lambda path: True)
    got = main_flash._wait_for_app(
        vid=0x04D8, pid=0xFF89, serial_number="", timeout_s=2.0
    )
    assert got is dev, "string-less app device must be accepted via identity probe"


def test_field1_wait_for_app_rejects_stringless_non_app_and_hints_finalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dev = _Dev(b"/dev/hid-stringless", "")
    monkeypatch.setattr(main_flash, "enumerate_devices", lambda vid, pid: [dev])
    monkeypatch.setattr(main_flash, "_probe_path_is_app", lambda path: False)
    with pytest.raises(RuntimeError) as err:
        main_flash._wait_for_app(
            vid=0x04D8, pid=0xFF89, serial_number="", timeout_s=0.5
        )
    assert "finalize-only" in str(err.value)


def test_field1_reconnect_ceilings_are_event_driven_defaults() -> None:
    """The wait exits on first positive identification, so the ceiling is a
    failure bound, not a delay -- default must be generous (>= 60 s), not the
    10 s that aborted both live flashes."""
    ap_actions = {a.dest: a.default for a in main_flash.main.__globals__["argparse"].ArgumentParser()._actions}
    # Parse the real parser defaults via a dry argv run instead:
    args = _parse_flasher_defaults()
    assert args.reconnect_timeout_s >= 60.0
    assert args.post_info_timeout_s >= 60.0


def _parse_flasher_defaults():
    import argparse as _argparse

    captured = {}
    real_parse = _argparse.ArgumentParser.parse_args

    def grab(self, argv=None, namespace=None):
        ns = real_parse(self, argv, namespace)
        captured["ns"] = ns
        return ns

    _argparse.ArgumentParser.parse_args = grab
    try:
        try:
            main_flash.main(["--list", "--vid", "0x04D8", "--pid", "0xFF89"])
        except Exception:
            pass
    finally:
        _argparse.ArgumentParser.parse_args = real_parse
    return captured["ns"]


def test_field1_finalize_only_applies_profile_without_flashing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = _Dev(b"/dev/hid-app", "DLCP")
    applied = {}

    monkeypatch.setattr(main_flash, "_pick_device", lambda *a, **k: dev)
    monkeypatch.setattr(
        main_flash,
        "_apply_ir_profile_ep0",
        lambda *, vid, pid, path, profile_label: applied.update(
            path=path, profile=profile_label
        )
        or (0x03, 0x04),
    )

    def must_not_flash(*a, **k):  # pragma: no cover - failure path
        raise AssertionError("finalize-only must not flash")

    monkeypatch.setattr(main_flash, "flash_main", must_not_flash)
    rc = main_flash.main(["--finalize-only", "--profile", "hypex"])
    assert rc == 0
    assert applied == {"path": b"/dev/hid-app", "profile": "hypex"}
    out = capsys.readouterr().out
    assert "0x03 -> 0x04" in out


def test_field1_wrapper_forwards_profile_on_finalize_only_and_info_only() -> None:
    """codex review of 947ca22: the wrapper's info-only/finalize-only early
    exits dropped an explicit --profile, silently falling back to the main
    flasher's default.  Both modes honor the flag, so it must forward."""
    import argparse

    from dlcp_fw.flash import dlcp_v34_release_flash as wrapper

    parser = argparse.ArgumentParser()
    for mode_flag in ("--finalize-only", "--info-only"):
        argv_in = [mode_flag, "--profile", "rc5"]
        # parse via the wrapper's real parser by reusing release_main's
        # argument wiring through build_forward_argv
        ns = argparse.Namespace(
            vid=0x04D8,
            pid=0xFF89,
            path=None,
            list=False,
            info_only=(mode_flag == "--info-only"),
            finalize_only=(mode_flag == "--finalize-only"),
            preflight_only=False,
            dry_run=False,
            verbose=False,
            left=False,
            right=False,
            all_ch=None,
            profile="rc5",
            reconnect_timeout_s=None,
        )
        argv = wrapper.build_forward_argv(ns, parser)
        assert ["--profile", "rc5"] == argv[-2:], (mode_flag, argv)


def test_field1_info_only_warns_on_rc5_profile(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dev = _Dev(b"/dev/hid-app", "DLCP")

    class _Input:
        setup_profile = 0x03

    class _Snap:
        input_state = _Input()

    monkeypatch.setattr(main_flash, "_pick_device", lambda *a, **k: dev)
    monkeypatch.setattr(main_flash, "_probe_device_snapshot", lambda **k: _Snap())
    monkeypatch.setattr(main_flash, "_print_device_snapshot", lambda *a, **k: None)
    rc = main_flash.main(["--info-only"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "WARNING" in out and "0x03" in out and "finalize-only" in out


# ---------------------------------------------------------------------------
# Task #8 resolution (2026-06-11): the session-49 "parser loss" mechanism.
# Single-instruction tracing on the run-era binary showed the V3.2 parser
# stall watchdog (periodic_service_loop__check_rx_frame_gap) firing MID-FRAME inside a
# normal inter-byte gap: the stock parser idles at fpos=1 after every
# dispatched frame, so the watchdog's 8-bit counter accumulates through
# every inter-frame idle and is never reset when a real frame starts.
# When the carried count is within one inter-byte gap of wrapping, it
# expires between a frame's bytes, resets the frame phase, and the
# remaining bytes are discarded as invalid routes -- the frame silently
# vanishes (session 49 lost a B0/03/02 mute this way).
# ---------------------------------------------------------------------------

RX_FRAME_GAP_TIMEOUT = 0x2F1  # main_rx_frame_gap_timeout (bank2)


def test_v34_frame_dispatches_with_preaccumulated_gap_watchdog(
    field_main_hex: Path,
) -> None:
    """Contract: a frame whose bytes arrive with normal UART spacing must
    dispatch even when the gap-watchdog counter carries a near-wrap value
    from prior inter-frame idle accumulation."""
    chain = _boot_v34_main(field_main_hex)
    chain.step_ticks(8_000_000)
    latch_before = chain.read_main_reg(0, 0x094)
    assert not (latch_before & 0x20)

    # Pre-accumulate the watchdog to the brink, exactly as a long idle does.
    chain.write_main_reg(0, RX_FRAME_GAP_TIMEOUT, 0xFE)
    # Deliver a mute frame with realistic inter-byte spacing (~320 us per
    # byte at 31250 baud ~= 15.4k ticks) so the watchdog polls between bytes.
    chain.inject_main_uart_rx_bytes(0, bytes([0xB0]))
    chain.step_ticks(16_000)
    chain.inject_main_uart_rx_bytes(0, bytes([0x03]))
    chain.step_ticks(16_000)
    chain.inject_main_uart_rx_bytes(0, bytes([0x02]))
    chain.step_ticks(8_000_000)

    latch = chain.read_main_reg(0, 0x094)
    assert latch & 0x20, (
        "mute frame silently discarded: the parser gap watchdog fired "
        f"mid-frame on a pre-accumulated counter (latch=0x{latch:02X})"
    )


def test_v34_invalid_rx_ring_wr_is_clamped_before_uart_indirect_write(
    field_chain_hexes: tuple[Path, Path],
) -> None:
    """Regression for the 2026-06-14 live `...10F BF v7` readback.

    Before the ISR clamp, `wr=0xCF` mapped exactly to filename RAM offset
    15 (`0x02CF`), where the expected '-' in `LX521.4 22MG10F-v7` was
    observed as `0xBF`.  The ISR must heal the bad pointer before the
    indirect RCREG store, so the byte lands at ring[0] instead.
    """
    if RustChain is None:
        pytest.skip(f"rust sim unavailable: {_RUST_CHAIN_IMPORT_ERROR}")
    control_hex, main_hex = field_chain_hexes
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()

    slot = b"LX521.4 22MG10F-v7" + (b"\xFF" * (30 - 18))
    for offset, value in enumerate(slot):
        chain.write_main_reg(0, FILENAME_RAM_BASE + offset, value)
    assert chain.read_main_reg(0, FILENAME_RAM_BASE + 15) == 0x2D

    chain.write_main_reg(0, RX_RING_WR, 0xCF)
    accepted, dropped = chain.inject_main_uart_rx_bytes(0, bytes([0xBF]))
    assert (accepted, dropped) == (1, 0)
    chain.step_ticks(1_000)

    assert chain.read_main_reg(0, FILENAME_RAM_BASE + 15) == 0x2D
    assert chain.read_main_reg(0, 0x0200) == 0xBF
    assert chain.read_main_reg(0, RX_RING_WR) == 0x01


def test_field1b_preflash_mode_inference_uses_identity_probe(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """2026-06-11 field incident #2: the PRE-flash mode inference still
    dead-ended on string-less enumeration ("unable to infer app vs
    bootloader mode from HID product string") even though the cmd 0x06
    identity probe answered in the same run.  A successful probe must be
    accepted as app mode and proceed to the bootloader switch."""
    dev = _Dev(b"/dev/hid-stringless", "")
    switched = {}

    monkeypatch.setattr(main_flash, "_pick_device", lambda *a, **k: dev)
    monkeypatch.setattr(main_flash, "enumerate_devices", lambda vid, pid: [dev])
    monkeypatch.setattr(main_flash, "_probe_path_is_app", lambda path: True)

    def fake_switch(**kwargs):
        switched["info"] = kwargs["info"]
        raise RuntimeError("stop-after-switch")  # cut the flow after the decision

    monkeypatch.setattr(main_flash, "_switch_to_bootloader", fake_switch)
    stream = bytes(main_flash.MAIN_PROG_END_EXCL - main_flash.MAIN_APP_START)
    with pytest.raises(RuntimeError, match="stop-after-switch"):
        main_flash.flash_main(
            vid=0x04D8,
            pid=0xFF89,
            path=dev.path,
            route_label=None,
            stream=stream,
            pace_ms=0,
            reconnect_timeout_s=1.0,
            reconnect_settle_ms=0,
            verify=False,
            skip_switch=False,
            dry_run=False,
            report_info=False,
            need_post_app=False,
            post_info_timeout_s=1.0,
            target_hex_version=None,
            target_hex_eeprom_version=None,
            verbose=False,
        )
    assert switched["info"] is dev
    assert "identity probe" in capsys.readouterr().out


def test_field1b_bootloader_wait_accepts_stringless_non_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After the app->bootloader switch, a string-less device that does NOT
    answer the app identity probe must be accepted as the bootloader --
    once the commanded app's enumeration has been seen to drop."""
    dev = _Dev(b"/dev/hid-stringless-boot", "")
    monkeypatch.setattr(main_flash, "enumerate_devices", lambda vid, pid: [dev])
    monkeypatch.setattr(main_flash, "_probe_path_is_app", lambda path: False)
    got = main_flash._wait_for_bootloader(
        vid=0x04D8,
        pid=0xFF89,
        serial_number="",
        timeout_s=2.0,
        switched_app_path=b"/dev/hid-old-app-path",   # absent => drop observed
    )
    assert got is dev


def test_field1b_bootloader_wait_rejects_wedged_app_on_same_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """codex review of 83bf29f (MEDIUM): a WEDGED app -- string-less, no
    longer answering cmd 0x06, still enumerated on its original path --
    must NOT be accepted as the bootloader and streamed at."""
    dev = _Dev(b"/dev/hid-wedged-app", "")
    monkeypatch.setattr(main_flash, "enumerate_devices", lambda vid, pid: [dev])
    monkeypatch.setattr(main_flash, "_probe_path_is_app", lambda path: False)
    with pytest.raises(RuntimeError, match="bootloader did not reconnect"):
        main_flash._wait_for_bootloader(
            vid=0x04D8,
            pid=0xFF89,
            serial_number="",
            timeout_s=1.0,
            switched_app_path=dev.path,   # same path, never seen absent
        )


def test_field1c_post_flash_wait_identifies_app_by_exclusion(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """2026-06-11 field incident #3: with string-less enumeration the
    post-flash wait's precise branches are ALL disabled at once (the app
    re-enumerates on a new path, previous_app_paths is empty because
    pre-flash apps classified "unknown", and the serial is blank) -- a
    probe-confirmed app sat unreturnable for the full 60 s while
    --info-only found it instantly.  On a two-MAIN rig the unflashed unit
    keeps its pre-flash path, so excluding the other devices' known paths
    identifies the flashed unit uniquely."""
    flashed = _Dev(b"/dev/hid-new-path", "")
    other = _Dev(b"/dev/hid-other-main", "")
    monkeypatch.setattr(
        main_flash, "enumerate_devices", lambda vid, pid: [flashed, other]
    )
    monkeypatch.setattr(main_flash, "_probe_path_is_app", lambda path: True)
    # 2026-06-12 live LEFT flash: the device EEPROM keeps the legacy 3.3
    # major/minor while the hex declares 3.4 -- only the REVISION byte is
    # comparable.  The stub returns the mismatching-minor tuple to pin
    # revision-only matching.
    device_id = main_flash.EepromVersionInfo(major=3, minor=3, revision=0x83)
    target_id = main_flash.EepromVersionInfo(major=3, minor=4, revision=0x83)
    monkeypatch.setattr(
        main_flash, "_probe_device_eeprom_version", lambda *, info, **k: device_id
    )
    got = main_flash._wait_for_app(
        vid=0x04D8,
        pid=0xFF89,
        serial_number="",
        path=b"/dev/hid-stale-bootloader-path",
        previous_app_paths=set(),
        excluded_paths={other.path},
        expected_eeprom_version=target_id,
        timeout_s=2.0,
    )
    assert got is flashed
    assert "identified by exclusion" in capsys.readouterr().out


def test_field1c_exclusion_fallback_refuses_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If more than one probe-confirmed app sits outside the excluded set,
    the wait must keep timing out rather than guess."""
    a = _Dev(b"/dev/hid-new-a", "")
    b = _Dev(b"/dev/hid-new-b", "")
    monkeypatch.setattr(main_flash, "enumerate_devices", lambda vid, pid: [a, b])
    monkeypatch.setattr(main_flash, "_probe_path_is_app", lambda path: True)
    with pytest.raises(RuntimeError, match="did not reconnect"):
        main_flash._wait_for_app(
            vid=0x04D8,
            pid=0xFF89,
            serial_number="",
            path=b"/dev/hid-stale",
            previous_app_paths=set(),
            excluded_paths=set(),
            timeout_s=1.0,
        )


def test_field1c_exclusion_rejects_wrong_unit_by_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """codex review of e5003a6 (HIGH): if the UNFLASHED MAIN re-enumerates
    onto a fresh path mid-wait, topology exclusion alone would bless it.
    The identity gate must reject a candidate whose EEPROM version tuple
    does not match the target hex, leaving the wait to time out rather
    than restore/finalize against the wrong unit."""
    wrong_unit = _Dev(b"/dev/hid-other-main-new-path", "")
    monkeypatch.setattr(
        main_flash, "enumerate_devices", lambda vid, pid: [wrong_unit]
    )
    monkeypatch.setattr(main_flash, "_probe_path_is_app", lambda path: True)
    monkeypatch.setattr(
        main_flash,
        "_probe_device_eeprom_version",
        lambda *, info, **k: main_flash.EepromVersionInfo(
            major=3, minor=3, revision=0x81   # the OLD image (legacy minor)
        ),
    )
    with pytest.raises(RuntimeError, match="did not reconnect"):
        main_flash._wait_for_app(
            vid=0x04D8,
            pid=0xFF89,
            serial_number="",
            path=b"/dev/hid-stale",
            previous_app_paths=set(),
            excluded_paths={b"/dev/hid-other-main-old-path"},
            expected_eeprom_version=main_flash.EepromVersionInfo(
                major=3, minor=4, revision=0x83
            ),
            timeout_s=1.0,
        )


# ---------------------------------------------------------------------------
# 2026-06-12 field incident #4: the EP0 profile finalize verified 0x04 and
# reverted to 0x03 within seconds -- a connected CONTROL's periodic full-sync
# re-broadcasts its CACHED B0/1D/<old> and the MAIN's cmd-0x1D handler stores
# it back.  The fix arms the firmware's stock_094.4 cmd-1D query-echo (the
# next incoming cmd-1D is consumed as a query and the BF/1D reply carries the
# new value back, which CONTROL adopts) and waits for the round-trip.
# Live-validated on the rig 2026-06-12: profile held through multiple
# CONTROL sync cycles after adoption.
# ---------------------------------------------------------------------------


def _sync_ep0_stub(monkeypatch, reads, *, rx_advances: bool = True):
    """Install EP0 factory/_ep0 stubs; `reads` yields (arm_byte, profile_byte).
    ``rx_advances`` models chain traffic (CONTROL polls advancing the RX
    ring write index); False models a bench MAIN with no CONTROL."""
    seq = iter(reads)
    state = {"current": None, "ors": [], "rx": 0}

    monkeypatch.setattr(
        main_flash, "_make_dlcp_ep0", lambda **kwargs: object()
    )
    monkeypatch.setattr(
        main_flash,
        "_ep0_or_byte",
        lambda ep0, *, addr, mask: state["ors"].append((addr, mask)) or 0,
    )

    def read_byte(ep0, *, addr):
        if addr == main_flash.RX_RING_WR_ADDR:
            if rx_advances:
                state["rx"] = (state["rx"] + 1) & 0xFF
            return state["rx"]
        if state["current"] is None:
            state["current"] = next(seq)
        arm, value = state["current"]
        if addr == main_flash.CMD1D_ECHO_ARM_ADDR:
            return arm
        if addr == main_flash.SETUP_PROFILE_RAM:
            state["current"] = None
            return value
        raise AssertionError(f"unexpected read 0x{addr:03X}")

    monkeypatch.setattr(main_flash, "_ep0_read_byte", read_byte)
    monkeypatch.setattr(main_flash.time, "sleep", lambda s: None)
    return state


def test_field1d_profile_sync_arms_echo_and_confirms_adoption(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state = _sync_ep0_stub(
        monkeypatch,
        [(0x10, 0x04), (0x10, 0x04), (0x00, 0x04)],  # armed, armed, consumed
    )
    main_flash._sync_profile_to_chain_control(
        vid=0x04D8, pid=0xFF89, path=b"/dev/x", profile_value=0x04,
        budget_s=10.0, poll_s=0.0,
    )
    assert (main_flash.CMD1D_ECHO_ARM_ADDR, main_flash.CMD1D_ECHO_ARM_MASK) in state["ors"]
    assert "adopted the new IR profile" in capsys.readouterr().out


def test_field1d_profile_sync_detects_reversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sync_ep0_stub(monkeypatch, [(0x10, 0x04), (0x10, 0x03)])  # reverted
    with pytest.raises(RuntimeError, match="reverted"):
        main_flash._sync_profile_to_chain_control(
            vid=0x04D8, pid=0xFF89, path=b"/dev/x", profile_value=0x04,
            budget_s=10.0, poll_s=0.0,
        )


def test_field1d_profile_sync_bails_early_on_bench_main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """codex review of aceca1f (MEDIUM): a bench MAIN without a CONTROL must
    not sit out the full budget -- no chain traffic (RX ring write index
    static) means nothing will contest the profile; bail early."""
    import itertools

    times = itertools.count(start=0.0, step=3.0)
    monkeypatch.setattr(main_flash.time, "monotonic", lambda: next(times))
    _sync_ep0_stub(
        monkeypatch, itertools.repeat((0x10, 0x04)), rx_advances=False
    )
    main_flash._sync_profile_to_chain_control(
        vid=0x04D8, pid=0xFF89, path=b"/dev/x", profile_value=0x04,
        budget_s=90.0, poll_s=0.0,
    )
    out = capsys.readouterr().out
    assert "no chain traffic observed" in out
