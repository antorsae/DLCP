"""Auto-Detect cycle volume-excursion regression (2026-06-12 live event).

Live signature: source at -60 dB, set volume -22 dB, parked on Auto Detect
with no input — ~1 s of clearly audible audio, then silence; counters
L +5 / M +2 / T unchanged over 20 minutes.

Sim reproduction (deterministic): during detect loss/re-detect cycles the
volume-dirty pass can sample the IN-FLUX route request 0x093 (walked through
candidate values by the Auto-Detect scan and rewritten by the RC0 stored-route
override) when selecting the per-route volume trim (0x09B..0x09E, HFD-set,
arbitrarily large), writing ANOTHER input's gain to TAS 0x30 until a later
pass corrects it.  Observed: master volume 0x30 <- 00319e3e (+8.8 dB over
the set-volume baseline 00120bdb) on one cycle of five.

Contract: across detect cycles, every TAS 0x30 master-volume write must
carry the settled set-volume coefficient — never a louder transient.  The
fix selects the trim by the APPLIED route shadow 0x0AB (updated only at
reconcile; the route apply re-dirties volume so the trim converges).
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
SRC_LOSS_DEBOUNCE = 0x2F3
SRC_HARD_LOSS_CONFIRM_SAMPLES = 0x14
ONE_S = 48_000_000
DETECT_CYCLES = 5


@pytest.fixture(scope="module")
def cycled_chain():
    chain = Chain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX), main_hex_path=str(V34_MAIN_HEX)
    )
    chain.run_until_connected(limit=240)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, 0x00)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.step_ticks(4 * ONE_S)
    return chain


def _master_volume_writes(chain) -> list[bytes]:
    return chain.read_main_dsp_write_payloads(0, 0x30)


def test_detect_cycles_never_write_louder_master_volume(cycled_chain) -> None:
    chain = cycled_chain
    # settled set-volume coefficient = the most recent completed 0x30 write
    # of the boot/settle era, BEFORE the log reset (keeps the tick schedule
    # exactly aligned with the live-repro probe: the excursion is a race and
    # fires deterministically only on this cadence)
    baseline = chain.read_main_dsp_write_payload(0, 0x30)
    assert baseline is not None, "no settled master volume reference seen"
    baseline_value = int.from_bytes(baseline, "big")
    for u in (0, 1):
        chain.reset_main_dsp_write_log(u)
    chain.step_ticks(2 * ONE_S)
    for w in _master_volume_writes(chain):
        assert w == baseline, (w.hex(), baseline.hex())
    for u in (0, 1):
        chain.reset_main_dsp_write_log(u)

    offenders: list[tuple[int, str]] = []
    for cycle in range(DETECT_CYCLES):
        # This regression is about route-flux volume writes during confirmed
        # loss/reacquire cycles, not about the real-time loss threshold.  The
        # full threshold is exercised in test_v34_src4382_lock_hysteresis.
        chain.write_main_reg(0, SRC_LOSS_DEBOUNCE, SRC_HARD_LOSS_CONFIRM_SAMPLES - 1)
        chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
        chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, UNLOCK_BIT)
        chain.step_ticks(ONE_S)
        chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
        chain.poke_main_src4382_reg(0, SRC_REG_RX_LOCK, 0x00)
        chain.step_ticks(2 * ONE_S)
        for w in _master_volume_writes(chain):
            value = int.from_bytes(w, "big")
            # mute (zero) and the settled set volume are legitimate; any
            # LARGER coefficient is another route's trim leaking into the
            # master volume — the live ~1 s loud-audio burst
            if value > baseline_value:
                offenders.append((cycle + 1, w.hex()))
        for u in (0, 1):
            chain.reset_main_dsp_write_log(u)

    assert not offenders, (
        f"louder-than-set master volume write(s) during detect cycles "
        f"(baseline {baseline.hex()}): {offenders}"
    )
