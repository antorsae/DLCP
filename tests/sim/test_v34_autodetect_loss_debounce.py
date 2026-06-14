"""Auto-Detect lock-loss debounce hardening (V3.4).

The source-present oracle is SRC4382 0x13.RXCKR[1:0] — a recovered-clock
rate CLASSIFIER, transiently 0 on re-measure windows, jitter, rate
boundaries, and source-side re-clocking even while audio passes.  V3.4
therefore confirms loss only when RXCKR==0 is paired with SRC4382
0x14.UNLOCK.

Contract: a short detect blip (~1 s) must NOT confirm a loss (route held,
L counter unchanged); sustained hard unlock must still confirm within a
bounded window and resume scanning.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from dlcp_fw.paths import V173_CONTROL_HEX, V34_MAIN_HEX  # noqa: E402
from dlcp_fw.sim.dlcp_sim_native import Chain  # noqa: E402

SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
SRC_REG_RX_LOCK = 0x14
UNLOCK_BIT = 0x04
DIAG_SRC_L = 0x3C1
ONE_S = 48_000_000
HARD_LOSS_WINDOW_TICKS = 14 * ONE_S


@pytest.fixture(scope="module")
def detected_chain():
    chain = Chain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX), main_hex_path=str(V34_MAIN_HEX)
    )
    chain.run_until_connected(limit=240)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.step_ticks(4 * ONE_S)
    return chain


def test_short_detect_blip_survives_without_route_loss(detected_chain) -> None:
    chain = detected_chain
    route_before = chain.read_main_reg(0, 0x0AB)
    assert route_before != 0, "fixture must start with a detected route"
    losses_before = chain.read_main_reg(0, DIAG_SRC_L)

    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, 0x00)
    chain.step_ticks(ONE_S)            # ~2-3 monitor samples: a status blip
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, 0x00)
    chain.step_ticks(2 * ONE_S)

    assert chain.read_main_reg(0, DIAG_SRC_L) == losses_before, (
        "a ~1 s status blip must not confirm an Auto-Detect source loss"
    )
    assert chain.read_main_reg(0, 0x0AB) == route_before, (
        "the held route must survive a short status blip"
    )


def test_sustained_loss_still_confirms_and_rescans(detected_chain) -> None:
    chain = detected_chain
    losses_before = chain.read_main_reg(0, DIAG_SRC_L)

    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, UNLOCK_BIT)
    chain.step_ticks(HARD_LOSS_WINDOW_TICKS)
    assert chain.read_main_reg(0, DIAG_SRC_L) >= losses_before + 1, (
        "sustained hard unlock must still confirm a loss within a bounded window"
    )

    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, 0x00)
    chain.step_ticks(4 * ONE_S)
    assert chain.read_main_reg(0, 0x0AB) != 0, "re-detect must re-apply a route"
