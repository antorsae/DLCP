"""Wire-chain fault injection tests across CONTROL and MAIN firmware versions.

All three stock CONTROL firmware versions shipped by Hypex contain
identical UART and I2C handling code.  The vendor changed the UI
(menus, display strings, IR dispatch) between releases but NEVER
modified the serial transport, OERR recovery, reconnect logic, or
I2C busy-wait paths.

These tests surface three hidden code issues:

1. **No reconnect timeout (UART)**: a single transient MAIN TX stall
   during the wake handshake causes CONTROL to enter the no-timeout
   reconnect wait loop and stay there forever.  Stock V1.4/V1.5b/V1.6b
   and patched V1.61b are all affected.  Only V1.62b recovers via its
   ``control_uart_soft_recover`` retry mechanism.

2. **No UART soft-recover (link)**: temporary MAIN->CONTROL link loss
   during reconnect strands CONTROL in WAITING.  Stock versions and
   V1.61b lack UART re-priming.  V1.62b's soft-recover (every 8 poll
   iterations) allows recovery.

3. **MAIN I2C STOP busy-wait has no timeout (I2C -> DSP cascade)**: an
   extended MSSP STOP fault on MAIN blocks its main loop.  Serial
   bytes from CONTROL accumulate in the 192-byte RX ring (no overflow
   detection).  CONTROL enters WAITING, DSP command path degrades.
   This is a MAIN-side bug affecting V2.3 stock, V2.4, and V2.5.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_CONTROL_HEX_V161B,
    PATCHED_CONTROL_HEX_V162B,
    PATCHED_MAIN_HEX,
    PATCHED_MAIN_HEX_V24,
    PATCHED_MAIN_HEX_V26,
    STOCK_CONTROL_HEX_V14,
    STOCK_CONTROL_HEX_V15B,
    STOCK_CONTROL_HEX_V16B,
    STOCK_MAIN_HEX,
    V31_MAIN_HEX,
)
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness

# MAIN firmware status register (active gate at bit 3)
_STATUS_5E = 0x05E


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing: {p.name}")


def _new_wire_chain(
    control_hex: Path,
    main_hex: Path,
) -> WireMultiMainChainHarness:
    return WireMultiMainChainHarness(
        control_hex,
        main_hex,
        main_units=1,
        fast_boot=False,
        disable_standby_check=False,
    )


def _enter_standby(chain: WireMultiMainChainHarness) -> None:
    # Settle the display loop before pressing STBY.  Stock CONTROL
    # needs a few display-loop iterations after boot to initialize
    # the button scan state machine.
    chain.step_many(3)
    chain.press("STBY")
    chain.step_many(20)
    assert "ZZZ" in chain.lcd_lines()[0].upper(), (
        f"pair did not enter standby: {chain.lcd_lines()!r}"
    )


# -----------------------------------------------------------------------
# Test 1 — UART: one-shot MAIN TX stall during reconnect
#
# Correct behavior: CONTROL should recover and reconnect.
# xfail: stock V1.4/V1.5b/V1.6b and patched V1.61b lack reconnect
#         timeout → stranded in WAITING permanently.
# pass:  V1.62b has control_uart_soft_recover → recovers.
# -----------------------------------------------------------------------

_TX_STALL_COMBOS = [
    pytest.param(
        STOCK_CONTROL_HEX_V14,
        marks=pytest.mark.xfail(reason="V1.4: no reconnect timeout", strict=True),
        id="stock_v14",
    ),
    pytest.param(
        STOCK_CONTROL_HEX_V15B,
        marks=pytest.mark.xfail(reason="V1.5b: no reconnect timeout", strict=True),
        id="stock_v15b",
    ),
    pytest.param(
        STOCK_CONTROL_HEX_V16B,
        marks=pytest.mark.xfail(reason="V1.6b: no reconnect timeout", strict=True),
        id="stock_v16b",
    ),
    pytest.param(
        PATCHED_CONTROL_HEX_V161B,
        marks=pytest.mark.xfail(reason="V1.61b: retry but no soft-recover", strict=True),
        id="patched_v161b",
    ),
    pytest.param(
        PATCHED_CONTROL_HEX_V162B,
        id="patched_v162b",
    ),
]


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("control_hex", _TX_STALL_COMBOS)
def test_wire_one_shot_tx_stall_reconnect_recovery(
    control_hex: Path,
) -> None:
    """CONTROL must reconnect after a single transient MAIN TX stall.

    Field trigger: standby-exit UART/clock race or current-loop
    driver hiccup delays MAIN's first status reply by ~6ms.

    Bug chain (from STOCK_SYNC_DEADLOCK_ANALYSIS):
      transient TX stall -> MAIN reply delayed past CONTROL's parse
      window -> handshake registers stay 0x80 -> reconnect loop
      iterates forever -> "Waiting for DLCP" permanently.

    Stock V1.4/V1.5b/V1.6b enter the no-timeout reconnect wait loop
    and never exit.  V1.61b adds retry logic but no UART soft-recover.
    V1.62b adds ``control_uart_soft_recover`` every 8 poll iterations,
    allowing recovery.  The vendor shipped three stock releases without
    adding a reconnect timeout.
    """
    _require_gpsim()
    _skip_missing(control_hex, PATCHED_MAIN_HEX)

    chain = _new_wire_chain(control_hex, PATCHED_MAIN_HEX)
    try:
        # Boot to DISPLAY
        first = chain.run_until_connected(limit=60)
        assert first is not None, "pair never reached DISPLAY"
        assert chain.is_connected(), f"pair not connected; lcd={first.lcd!r}"

        # Enter standby
        _enter_standby(chain)

        # Inject one-shot MAIN TX stall (~6ms at 4MHz Tcy = 24,000 cycles)
        chain.set_main_uart_fault(trmt_busy_cycles=24_000, trmt_busy_count=1)

        # Settle Zzz handler before waking.
        chain.step_many(3)

        # Wake: CONTROL exits Zzz, enters reconnect.
        chain.press("STBY")
        held = chain.run_until_waiting(limit=20)
        assert held is not None, "pair produced no steps during wake"
        assert chain.is_waiting(), f"pair never entered WAITING: {held.lcd!r}"

        # Give CONTROL enough time to recover (if it can).
        # V1.62b's soft-recover fires every 8 polls; 120 steps is
        # generous (~30s sim time, many soft-recover cycles).
        recovered = chain.run_until_connected(limit=120)

        # The correct behavior: CONTROL reconnects.
        # xfail versions will fail here.
        assert recovered is not None, "pair produced no steps after TX stall"
        assert chain.is_connected(), (
            f"CONTROL did not reconnect after one-shot TX stall: "
            f"{recovered.lcd!r}"
        )

    finally:
        chain.close()


# -----------------------------------------------------------------------
# Test 2 — UART link: reply drop during reconnect
#
# Correct behavior: CONTROL should reconnect after link is restored.
# xfail: stock V1.4/V1.5b/V1.6b and V1.61b lack UART soft-recover.
# pass:  V1.62b recovers via soft-recover.
# -----------------------------------------------------------------------

_REPLY_DROP_COMBOS = [
    pytest.param(
        STOCK_CONTROL_HEX_V14,
        marks=pytest.mark.xfail(reason="V1.4: no UART soft-recover", strict=True),
        id="stock_v14",
    ),
    pytest.param(
        STOCK_CONTROL_HEX_V16B,
        marks=pytest.mark.xfail(reason="V1.6b: no UART soft-recover", strict=True),
        id="stock_v16b",
    ),
    pytest.param(
        PATCHED_CONTROL_HEX_V161B,
        marks=pytest.mark.xfail(reason="V1.61b: retry but no soft-recover", strict=True),
        id="patched_v161b",
    ),
    pytest.param(
        PATCHED_CONTROL_HEX_V162B,
        id="patched_v162b",
    ),
]


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("control_hex", _REPLY_DROP_COMBOS)
def test_wire_reply_drop_during_wake_reconnect_recovery(
    control_hex: Path,
) -> None:
    """CONTROL must reconnect after temporary MAIN->CONTROL link loss.

    Field trigger: current-loop connector intermittent open during
    standby-exit.  CONTROL exits Zzz, sends wake + reconnect polls,
    but MAIN's responses are lost on the return path for a few
    seconds (connector vibration, EMI burst).

    The link is restored after 3 steps.  CONTROL should re-prime the
    UART and reconnect.  Stock versions and V1.61b lack UART
    soft-recover and stay stranded in WAITING.  V1.62b's
    ``control_uart_soft_recover`` (every 8 poll iterations) re-primes
    the EUSART and allows recovery.

    Hidden issues surfaced:
    - Stock V1.4/V1.5b/V1.6b have no reconnect timeout.
    - V1.61b adds retry counting but no UART re-prime.
    - Once CONTROL's parser desynchronizes during the link drop,
      only V1.62b's explicit CREN toggle can recover it.
    """
    _require_gpsim()
    _skip_missing(control_hex, PATCHED_MAIN_HEX)

    chain = _new_wire_chain(control_hex, PATCHED_MAIN_HEX)
    try:
        # Boot to DISPLAY
        first = chain.run_until_connected(limit=60)
        assert first is not None, "pair never reached DISPLAY"
        assert chain.is_connected(), f"pair not connected; lcd={first.lcd!r}"

        # Enter standby
        _enter_standby(chain)

        # Drop MAIN->CONTROL reply path (simulates connector open)
        chain.set_link_fault("m0_to_ctl", drop=True)

        # Settle Zzz handler before waking.
        chain.step_many(3)

        # Wake: CONTROL exits Zzz, polls MAIN.  MAIN responds but
        # responses are dropped.  CONTROL enters WAITING.
        chain.press("STBY")
        held = chain.run_until_waiting(limit=20)
        assert held is not None, "pair produced no steps during wake"
        assert chain.is_waiting(), f"pair never entered WAITING: {held.lcd!r}"

        # Keep link broken for a few more steps
        chain.step_many(3)
        assert chain.is_waiting(), "CONTROL left WAITING while link still broken"

        # Restore link (connector re-seats)
        chain.clear_link_faults()

        # Give CONTROL time to recover.
        recovered = chain.run_until_connected(limit=120)

        # The correct behavior: CONTROL reconnects.
        # xfail versions will fail here.
        assert recovered is not None, "pair produced no steps after link restore"
        assert chain.is_connected(), (
            f"CONTROL did not reconnect after reply drop + link restore: "
            f"{recovered.lcd!r}"
        )

    finally:
        chain.close()


# -----------------------------------------------------------------------
# Test 3 — I2C cascade: MSSP STOP fault blocks MAIN, degrades DSP path
#
# This is a MAIN-side bug: the I2C busy-wait at SSPSTAT.P has no
# timeout.  Parametrized by MAIN version, not CONTROL version.
# -----------------------------------------------------------------------


def _dsp34_snapshot(main) -> dict[int, int]:
    return {r: main.read_i2c_regfile("dsp34", r) for r in range(256)}


def _dsp34_diff(before: dict[int, int], after: dict[int, int]) -> list:
    return [(r, before[r], after[r]) for r in range(256) if before[r] != after[r]]


# NOTE: V2.6 adds DSP ACKSTAT/commit robustness but does NOT fix the
# MSSP STOP timeout (M2 deadlock chain).  Bus-clear and DSP ping are
# V2.7 scope.  V2.6 is included here to verify it doesn't regress.
_MSSP_MAIN_COMBOS = [
    pytest.param(STOCK_MAIN_HEX, id="main_v23_stock"),
    pytest.param(PATCHED_MAIN_HEX_V24, id="main_v24"),
    pytest.param(PATCHED_MAIN_HEX, id="main_v25"),
    pytest.param(PATCHED_MAIN_HEX_V26, id="main_v26"),
    pytest.param(V31_MAIN_HEX, id="main_v31"),
]


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _MSSP_MAIN_COMBOS)
def test_wire_extended_mssp_stop_fault_degrades_dsp_command_path(
    main_hex: Path,
) -> None:
    """Extended MSSP STOP fault on MAIN blocks main loop, cascading to DSP.

    Field trigger: TAS3108 DSP pulls SCL low (clock stretching) during
    an I2C write, or a bus glitch holds the STOP condition.  MAIN's
    firmware polls SSPSTAT.P in a tight loop with no timeout (the M2
    chain in STOCK_SYNC_DEADLOCK_ANALYSIS).

    While MAIN is blocked on I2C, serial bytes from CONTROL accumulate
    in the 192-byte RX ring buffer at 0x0200.  The ring has NO
    overflow detection -- write_idx wraps silently past read_idx,
    overwriting unread data.  When MAIN resumes, the parser reads
    corrupted frames.

    This is a MAIN-side bug.  All MAIN versions are affected:
    - V2.3 (stock): no I2C timeout, no recovery.
    - V2.4 (patched): A/B preset patch, same I2C path.
    - V2.5 (patched): adds V2.5 timeout hooks, but the MSSP STOP
      busy-wait is in a different code path than the timeout seed.

    CONTROL version is held constant at V1.62b (best-case CONTROL
    with reconnect soft-recover).

    Expected outcome: the MSSP fault causes at least one observable
    degradation — either CONTROL enters WAITING (MAIN can't respond)
    or DSP command path is broken after recovery (volume UP has no
    effect on dsp34 registers).
    """
    _require_gpsim()
    _skip_missing(PATCHED_CONTROL_HEX_V162B, main_hex)

    chain = _new_wire_chain(PATCHED_CONTROL_HEX_V162B, main_hex)
    try:
        # Boot to DISPLAY
        first = chain.run_until_connected(limit=80)
        assert first is not None, "pair never reached DISPLAY"
        assert chain.is_connected(), f"pair not connected; lcd={first.lcd!r}"

        main = chain.mains[0]
        main_issue = main._issue

        # DSP baseline: volume UP must change dsp34 registers
        snap_a = _dsp34_snapshot(main)
        chain.press("UP")
        chain.step_many(5)
        diff_baseline = _dsp34_diff(snap_a, _dsp34_snapshot(main))
        assert len(diff_baseline) > 0, (
            "DSP baseline broken: volume UP did not change registers"
        )

        # Record MAIN's RX ring pointers before fault
        rx_rd_before = _read_reg(main_issue, 0x0C6)
        rx_wr_before = _read_reg(main_issue, 0x0C7)

        # Inject extended MSSP STOP fault: every I2C STOP takes 5M cycles,
        # infinite count.  This blocks MAIN's main loop on every I2C write.
        chain.set_main_mssp_stop_fault(
            stop_busy_cycles=5_000_000,
            stop_busy_count=-1,  # infinite
        )

        # Run many steps.  CONTROL keeps sending display-loop commands
        # (function_035 iterations).  MAIN's main loop is blocked on I2C,
        # so serial bytes accumulate in the RX ring.
        #
        # MAIN's ISR still fires (GIE=1 during I2C poll).  Each RCIF
        # interrupt reads RCREG and stores in the ring.  The ring has
        # NO overflow detection -- write_idx wraps past read_idx silently.
        fault_steps = 30
        chain.step_many(fault_steps)

        # Check ring state
        rx_rd_after = _read_reg(main_issue, 0x0C6)
        rx_wr_after = _read_reg(main_issue, 0x0C7)
        ring_size = 0xC0  # 192 bytes
        used_before = (rx_wr_before - rx_rd_before) % ring_size
        used_after = (rx_wr_after - rx_rd_after) % ring_size

        # Clear the fault
        chain.clear_main_mssp_stop_faults()

        # Let MAIN resume and process whatever is in the ring
        chain.step_many(10)

        # Check if CONTROL entered WAITING (MAIN couldn't respond)
        entered_waiting = chain.is_waiting()

        if entered_waiting:
            # Try to recover (V1.62b has soft-recover)
            recovered = chain.run_until_connected(limit=60)
            if not (recovered is not None and chain.is_connected()):
                # Irrecoverable: MSSP fault cascaded to permanent WAITING
                pytest.fail(
                    f"CONTROL stuck in WAITING after MSSP fault cleared -- "
                    f"ring: rd=0x{rx_rd_after:02X} wr=0x{rx_wr_after:02X} "
                    f"used_before={used_before} used_after={used_after}"
                )

        # DSP integrity check: volume UP after fault recovery
        snap_b = _dsp34_snapshot(main)
        chain.press("UP")
        chain.step_many(5)
        diff_post = _dsp34_diff(snap_b, _dsp34_snapshot(main))

        # Assert the fault DID cause observable degradation:
        # either DSP path broken or CONTROL lost connection.
        dsp_degraded = len(diff_post) == 0
        control_lost = entered_waiting

        assert dsp_degraded or control_lost, (
            f"extended MSSP fault caused no observable degradation: "
            f"DSP still works ({len(diff_post)} changes) and CONTROL "
            f"never entered WAITING -- fault may be too mild"
        )

    finally:
        chain.close()
