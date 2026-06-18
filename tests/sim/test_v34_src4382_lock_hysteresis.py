"""V3.4 SRC4382 Auto Detect lock-vs-rate estimator contract.

SRC4382 register 0x13.RXCKR is a recovered-clock rate classifier; 0 can
mean a transient estimator hole during a valid S/PDIF stream.  Register
0x14.UNLOCK is the formal DIR decoder/PLL lock evidence.  A selected
Auto Detect route must survive RXCKR holes while UNLOCK is clear, and
only sustained RXCKR==0 + UNLOCK may tear the route down.
"""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from dlcp_fw.paths import V173_CONTROL_HEX, V34_MAIN_ASM, V34_MAIN_HEX
from dlcp_fw.sim.dlcp_sim_native import Chain
from dlcp_fw.sim.v30_symbols import assemble_v30


ACTIVE_FLAGS = 0x05E
ACTIVE_USER_MUTE_MASK = 0x10
SRC_ROUTE_REQUEST = 0x093
ROUTE_SHADOW = 0x0AB
SRC_LOSS_DEBOUNCE = 0x2F3
DIAG_SRC_L = 0x3C1
DIAG_SRC_C = 0x3C2

SRC_REG_RX_CONTROL = 0x0D
SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
SRC_REG_RX_LOCK = 0x14
UNLOCK_BIT = 0x04
TAS_REG_VOLUME_COEFF = 0x30

ONE_S = 48_000_000
HARD_LOSS_WINDOW_TICKS = 14 * ONE_S


def _new_chain(main_hex: Path = V34_MAIN_HEX) -> Chain:
    chain = Chain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX),
        main_hex_path=str(main_hex),
    )
    chain.run_until_connected(limit=240)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.step_ticks(2 * ONE_S)
    return chain


def _set_src(chain: Chain, *, rxckr: int, unlock: int = 0x00) -> None:
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, rxckr & 0x03)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, unlock & UNLOCK_BIT)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)


def _detect_locked_source(chain: Chain) -> int:
    _set_src(chain, rxckr=0x01, unlock=0x00)
    chain.step_ticks(4 * ONE_S)
    route = chain.read_main_reg(0, ROUTE_SHADOW)
    assert route != 0, "fixture must converge to a selected Auto Detect route"
    chain.step_ticks(2 * ONE_S)
    assert chain.read_main_reg(0, ROUTE_SHADOW) == route
    return route


def _reset_src_and_dsp_logs(chain: Chain) -> None:
    chain.reset_main_src4382_stats(0)
    chain.reset_main_dsp_write_log(0)


def _assert_no_louder_volume_writes(chain: Chain, baseline: bytes) -> None:
    baseline_value = int.from_bytes(baseline, "big")
    offenders = [
        payload.hex()
        for payload in chain.read_main_dsp_write_payloads(0, TAS_REG_VOLUME_COEFF)
        if int.from_bytes(payload, "big") > baseline_value
    ]
    assert not offenders, (
        f"locked SRC estimator holes must not produce louder TAS volume writes "
        f"(baseline={baseline.hex()}, offenders={offenders})"
    )


def _assert_locked_rxckr_zero_holds_route(main_hex: Path) -> None:
    chain = _new_chain(main_hex)
    route = _detect_locked_source(chain)
    losses_before = chain.read_main_reg(0, DIAG_SRC_L)
    changes_before = chain.read_main_reg(0, DIAG_SRC_C)
    _reset_src_and_dsp_logs(chain)

    _set_src(chain, rxckr=0x00, unlock=0x00)
    chain.step_ticks(HARD_LOSS_WINDOW_TICKS)

    stats = chain.read_main_src4382_stats(0)
    assert chain.read_main_reg(0, ROUTE_SHADOW) == route, (
        "locked RXCKR==0 estimator hole cleared the selected route"
    )
    assert chain.read_main_reg(0, SRC_ROUTE_REQUEST) == route
    assert chain.read_main_reg(0, DIAG_SRC_L) == losses_before
    assert chain.read_main_reg(0, DIAG_SRC_C) == changes_before
    assert chain.read_main_reg(0, SRC_LOSS_DEBOUNCE) == 0x00
    assert stats["writes_by_subaddr"][SRC_REG_RX_CONTROL] == 0, stats
    assert (chain.read_main_reg(0, ACTIVE_FLAGS) & ACTIVE_USER_MUTE_MASK) == 0


def test_spdif_rate_estimator_transitions_hold_selected_route() -> None:
    chain = _new_chain()
    route = _detect_locked_source(chain)
    baseline = chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF)
    assert baseline is not None
    losses_before = chain.read_main_reg(0, DIAG_SRC_L)
    changes_before = chain.read_main_reg(0, DIAG_SRC_C)
    _reset_src_and_dsp_logs(chain)

    for rxckr in (0x01, 0x00, 0x02, 0x00, 0x03):
        _set_src(chain, rxckr=rxckr, unlock=0x00)
        chain.step_ticks(ONE_S)

    assert chain.read_main_reg(0, ROUTE_SHADOW) == route
    assert chain.read_main_reg(0, SRC_ROUTE_REQUEST) == route
    assert chain.read_main_reg(0, DIAG_SRC_L) == losses_before
    assert chain.read_main_reg(0, DIAG_SRC_C) == changes_before
    assert (chain.read_main_reg(0, ACTIVE_FLAGS) & ACTIVE_USER_MUTE_MASK) == 0
    _assert_no_louder_volume_writes(chain, baseline)


def test_locked_rxckr_zero_longer_than_threshold_does_not_confirm_loss() -> None:
    _assert_locked_rxckr_zero_holds_route(V34_MAIN_HEX)


def test_short_unlock_flap_does_not_confirm_loss() -> None:
    chain = _new_chain()
    route = _detect_locked_source(chain)
    losses_before = chain.read_main_reg(0, DIAG_SRC_L)

    _set_src(chain, rxckr=0x00, unlock=UNLOCK_BIT)
    chain.step_ticks(2 * ONE_S)
    _set_src(chain, rxckr=0x01, unlock=0x00)
    chain.step_ticks(2 * ONE_S)

    assert chain.read_main_reg(0, ROUTE_SHADOW) == route
    assert chain.read_main_reg(0, DIAG_SRC_L) == losses_before
    assert chain.read_main_reg(0, SRC_LOSS_DEBOUNCE) == 0x00


def test_sustained_unlock_confirms_once_and_rescans() -> None:
    chain = _new_chain()
    _detect_locked_source(chain)
    losses_before = chain.read_main_reg(0, DIAG_SRC_L)

    _set_src(chain, rxckr=0x00, unlock=UNLOCK_BIT)
    chain.step_ticks(HARD_LOSS_WINDOW_TICKS)

    assert chain.read_main_reg(0, DIAG_SRC_L) == losses_before + 1
    assert chain.read_main_reg(0, ROUTE_SHADOW) == 0x00
    assert chain.read_main_reg(0, SRC_ROUTE_REQUEST) == 0x00

    _set_src(chain, rxckr=0x01, unlock=0x00)
    chain.step_ticks(4 * ONE_S)
    assert chain.read_main_reg(0, ROUTE_SHADOW) != 0x00


def test_unlocked_rxckr_nonzero_candidate_does_not_apply_route() -> None:
    chain = _new_chain()
    changes_before = chain.read_main_reg(0, DIAG_SRC_C)
    _reset_src_and_dsp_logs(chain)

    _set_src(chain, rxckr=0x01, unlock=UNLOCK_BIT)
    chain.step_ticks(4 * ONE_S)

    assert chain.read_main_reg(0, ROUTE_SHADOW) == 0x00
    assert chain.read_main_reg(0, SRC_ROUTE_REQUEST) == 0x00
    assert chain.read_main_reg(0, DIAG_SRC_C) == changes_before
    assert chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF) is None


def test_locked_rxckr_nonzero_candidate_still_applies_route_quickly() -> None:
    chain = _new_chain()
    baseline = chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF)
    assert baseline is not None
    changes_before = chain.read_main_reg(0, DIAG_SRC_C)
    _reset_src_and_dsp_logs(chain)

    _set_src(chain, rxckr=0x01, unlock=0x00)
    chain.step_ticks(4 * ONE_S)

    assert chain.read_main_reg(0, ROUTE_SHADOW) != 0x00
    assert chain.read_main_reg(0, DIAG_SRC_C) >= changes_before + 1
    _assert_no_louder_volume_writes(chain, baseline)


def test_rxckr_only_loss_mutation_is_rejected(tmp_path: Path) -> None:
    text = V34_MAIN_ASM.read_text(encoding="utf-8")
    old = (
        "    andlw       SRC4382_UNLOCK_MASK\n"
        "    bz          poll_src4382_route_monitor__clear_loss_debounce_for_soft_hold\n"
        "poll_src4382_route_monitor__sample_hard_route_loss:\n"
    )
    new = (
        "    andlw       SRC4382_UNLOCK_MASK\n"
        "    bra         poll_src4382_route_monitor__sample_hard_route_loss ; mutation: RXCKR-only loss\n"
        "poll_src4382_route_monitor__sample_hard_route_loss:\n"
    )
    assert old in text, "RXCKR-only mutation anchor drifted"

    asm_path = tmp_path / "dlcp_main_v34_rxckr_only_loss.asm"
    hex_path = tmp_path / "DLCP_Firmware_V3.4_rxckr_only_loss.hex"
    shutil.copy2(V34_MAIN_ASM.parent / "dlcp_main_ram.inc", tmp_path / "dlcp_main_ram.inc")
    asm_path.write_text(text.replace(old, new, 1), encoding="utf-8")
    assemble_v30(asm_path, hex_path)

    with pytest.raises(AssertionError, match="locked RXCKR==0 estimator hole"):
        _assert_locked_rxckr_zero_holds_route(hex_path)
