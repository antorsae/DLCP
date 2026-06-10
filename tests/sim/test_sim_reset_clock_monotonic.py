"""The universal clock must be monotonic across mid-run resets.

`apply_reset_all` used to re-bootstrap every core at tick zero, rewinding
`current_tick` mid-session.  The exploratory runner logs `tick` with every
observation and the card formatter merges stimuli and observations by tick, so
each rewind interleaved clock epochs and manufactured phantom regressions
(cumulative I2C counters going negative, DSP digests "oscillating" between two
fixed values) in the 2026-06-09 post-fix corpus — which the oracle then
confirmed as firmware findings.  A device reset must not rewind wall-clock
time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V34_MAIN_HEX

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    RustChain = None  # type: ignore[assignment]
    _RUST_CHAIN_IMPORT_ERROR = exc

ACTIVE_FLAGS = 0x05E
ACTIVE_GATE_MASK = 0x08
BOOT_TCY = 16_000_000
TAS_VOLUME_SUBADDR = 0x30


def _require_rust() -> None:
    if RustChain is None:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


@pytest.fixture(scope="module")
def booted_main_chain():  # type: ignore[no-untyped-def]
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(V34_MAIN_HEX))
    chain.step_tcy(BOOT_TCY)
    assert chain.read_main_reg(0, ACTIVE_FLAGS) & ACTIVE_GATE_MASK
    return chain


def test_apply_reset_all_keeps_universal_clock_monotonic(booted_main_chain) -> None:  # type: ignore[no-untyped-def]
    chain = booted_main_chain
    before = chain.current_tick()
    assert before > 0

    chain.apply_reset_all("mclr")
    after_reset = chain.current_tick()
    assert after_reset >= before, (
        f"apply_reset_all rewound the universal clock: {before} -> {after_reset}"
    )

    chain.step_ticks(1_000_000)
    assert chain.current_tick() == after_reset + 1_000_000


def test_main_reboots_and_observables_stay_monotonic_across_reset_all(
    booted_main_chain,
) -> None:  # type: ignore[no-untyped-def]
    chain = booted_main_chain
    n_before = len(chain.read_main_dsp_write_payloads(0, TAS_VOLUME_SUBADDR))
    tick_before = chain.current_tick()

    chain.apply_reset_all("mclr")
    # Epoch pin: the re-bootstrap events must be scheduled at the CURRENT
    # tick, so the reboot unfolds across simulated time exactly like a cold
    # boot.  A regression that queued boot events at tick 0 (while merely
    # restoring current_tick) would let the entire boot race ahead "in the
    # past" and the gate would already be up here.
    chain.step_tcy(BOOT_TCY // 16)
    assert not (chain.read_main_reg(0, ACTIVE_FLAGS) & ACTIVE_GATE_MASK), (
        "post-reset boot collapsed into a burst: gate already up after a "
        "fraction of the boot time (re-bootstrap events not at the current epoch)"
    )
    chain.step_tcy(BOOT_TCY)

    assert chain.read_main_reg(0, ACTIVE_FLAGS) & ACTIVE_GATE_MASK, (
        "MAIN did not reach active app state after a mid-run reset_all"
    )
    assert chain.current_tick() > tick_before
    # The facade's TAS write log is a cumulative observation artifact: a
    # reset reboots the firmware (which re-writes the DSP) but must never
    # shrink the log the exploratory observer derives counters from.
    n_after = len(chain.read_main_dsp_write_payloads(0, TAS_VOLUME_SUBADDR))
    assert n_after >= n_before, f"TAS write log shrank across reset: {n_before} -> {n_after}"
    assert n_after > n_before, "reboot should have re-written the TAS volume coefficient"
