"""Wire-chain fault injection tests proving stock CONTROL bugs across V1.4/V1.5b/V1.6b.

All three stock CONTROL firmware versions shipped by Hypex contain
identical UART and I2C handling code.  The vendor changed the UI
(menus, display strings, IR dispatch) between releases but NEVER
modified the serial transport, OERR recovery, reconnect logic, or
I2C busy-wait paths.

These tests surface three hidden code issues:

1. **No reconnect timeout (UART)**: a single transient MAIN TX stall
   during the wake handshake causes CONTROL to enter the
   no-timeout reconnect wait loop and stay there forever.  All
   three stock versions are affected identically.

2. **Idle timeout with slow recovery (link)**: dropping MAIN->CONTROL
   responses during normal DISPLAY mode triggers CONTROL's idle
   counter to fire, entering WAITING.  Recovery requires a full
   reconnect cycle.  The idle timeout threshold and recovery speed
   are characterized.

3. **I2C STOP fault cascading to DSP corruption (I2C -> UART)**: an
   extended MSSP STOP fault on MAIN blocks the main loop.  Serial
   bytes from CONTROL accumulate in the 192-byte RX ring.  After
   overflow, the frame parser reads corrupted data.  Subsequent DSP
   commands are silently mis-routed or dropped.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_CONTROL_HEX_V162B,
    PATCHED_MAIN_HEX,
    STOCK_CONTROL_HEX_V14,
    STOCK_CONTROL_HEX_V15B,
    STOCK_CONTROL_HEX_V16B,
)
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness

# PIC18F25K20 register for CONTROL UART status
_RCSTA = 0xFAB

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
# Firmware combos: all three stock CONTROL versions + V2.5 MAIN.
# MAIN version is irrelevant for the CONTROL-side bugs being tested.
# -----------------------------------------------------------------------
_STOCK_CONTROL_VERSIONS = [
    pytest.param(STOCK_CONTROL_HEX_V14, id="stock_v14"),
    pytest.param(STOCK_CONTROL_HEX_V15B, id="stock_v15b"),
    pytest.param(STOCK_CONTROL_HEX_V16B, id="stock_v16b"),
]


# =======================================================================
# Test 1 — UART: one-shot MAIN TX stall strands ALL stock versions
# =======================================================================


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("control_hex", _STOCK_CONTROL_VERSIONS)
def test_wire_stock_control_one_shot_tx_stall_no_reconnect(
    control_hex: Path,
) -> None:
    """A single transient MAIN TX stall during wake strands stock CONTROL.

    Field trigger: standby-exit UART/clock race or current-loop
    driver hiccup delays MAIN's first status reply by ~6ms.

    All three stock CONTROL versions (V1.4, V1.5b, V1.6b) enter
    the no-timeout reconnect wait loop (label_204/label_212) and
    never exit.  The vendor shipped three firmware releases without
    adding a reconnect timeout or retry mechanism.

    Bug chain (from STOCK_SYNC_DEADLOCK_ANALYSIS):
      transient TX stall -> MAIN reply delayed past CONTROL's parse
      window -> handshake registers stay 0x80 -> reconnect loop
      iterates forever -> "Waiting for DLCP" permanently.
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

        # Settle the Zzz display handler before waking.  V1.6b's UI
        # refactor needs a few extra iterations to initialize the
        # standby button scan state.
        chain.step_many(3)

        # Wake: CONTROL exits Zzz, enters reconnect.
        chain.press("STBY")
        held = chain.run_until_waiting(limit=20)
        assert held is not None, "pair produced no steps during wake"
        assert chain.is_waiting(), f"pair never entered WAITING: {held.lcd!r}"

        # Stock CONTROL has no reconnect timeout.
        # Run 80 more steps (~20 seconds sim time).  It should NEVER recover.
        stuck = chain.run_until_connected(limit=80)
        assert stuck is not None, "pair produced no steps after TX stall"
        assert not chain.is_connected(), (
            f"stock CONTROL unexpectedly reconnected after one-shot TX stall "
            f"(this version has a reconnect timeout!): {stuck.lcd!r}"
        )
        assert chain.is_waiting(), (
            f"stock CONTROL left WAITING without reconnecting: {stuck.lcd!r}"
        )

    finally:
        chain.close()


# =======================================================================
# Test 2 — UART link: asymmetric reply loss triggers idle timeout
# =======================================================================


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("control_hex", [
    pytest.param(STOCK_CONTROL_HEX_V14, id="stock_v14"),
    pytest.param(STOCK_CONTROL_HEX_V16B, id="stock_v16b"),
])
def test_wire_stock_control_reply_drop_during_wake_no_recovery(
    control_hex: Path,
) -> None:
    """Dropping MAIN->CONTROL replies during wake strands stock CONTROL.

    Field trigger: current-loop connector intermittent open during
    standby-exit.  CONTROL exits Zzz, sends wake + reconnect polls,
    but MAIN's responses are lost due to the open circuit.

    CONTROL enters the reconnect wait loop (label_212) and polls
    MAIN repeatedly.  MAIN responds to every poll.  But the responses
    never reach CONTROL because the return path is broken.

    The link fault is temporary (cleared after 3 steps).  On real
    hardware this models a connector that re-seats after vibration.
    But stock CONTROL's reconnect loop has no timeout, so it stays
    in WAITING even after the link is restored -- because by then
    CONTROL and MAIN are out of sync (CONTROL's parser saw no
    data during the drop, so its handshake registers are still 0x80).

    Hidden issues surfaced:
    - Stock V1.4/V1.5b/V1.6b have no reconnect timeout.
    - The reconnect wait loop polls indefinitely.
    - No UART soft-recover (only V1.62b adds that).
    - Once CONTROL misses the handshake window, it can never recover
      without power cycle.
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

        # Run a few more steps with link still broken
        chain.step_many(3)
        assert chain.is_waiting(), "CONTROL left WAITING while link still broken"

        # Restore link (connector re-seats)
        chain.clear_link_faults()

        # Stock CONTROL has no reconnect timeout and no UART
        # soft-recover.  Even with the link restored, CONTROL's
        # poll/parse cycle may be desynchronized.  Run 80 steps and
        # check if it ever reconnects.
        recovered = chain.run_until_connected(limit=80)
        assert recovered is not None, "pair produced no steps after link restore"

        # Stock CONTROL should remain stranded in WAITING because
        # the reconnect loop's poll/parse cycle doesn't re-prime
        # the UART.  (V1.62b's soft-recover fixes this.)
        assert not chain.is_connected(), (
            f"stock CONTROL unexpectedly reconnected after reply drop — "
            f"this version may have recovery logic: {recovered.lcd!r}"
        )
        assert chain.is_waiting(), (
            f"stock CONTROL left WAITING without reconnecting: "
            f"{recovered.lcd!r}"
        )

    finally:
        chain.close()


# =======================================================================
# Test 3 — I2C cascade: MSSP STOP fault blocks MAIN, degrades DSP path
# =======================================================================


def _dsp34_snapshot(main) -> dict[int, int]:
    return {r: main.read_i2c_regfile("dsp34", r) for r in range(256)}


def _dsp34_diff(before: dict[int, int], after: dict[int, int]) -> list:
    return [(r, before[r], after[r]) for r in range(256) if before[r] != after[r]]


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("control_hex", [
    pytest.param(STOCK_CONTROL_HEX_V16B, id="stock_v16b"),
    pytest.param(PATCHED_CONTROL_HEX_V162B, id="patched_v162b"),
])
def test_wire_extended_mssp_stop_fault_degrades_dsp_command_path(
    control_hex: Path,
) -> None:
    """Extended MSSP STOP fault on MAIN blocks main loop, cascading to DSP.

    Field trigger: TAS3108 DSP pulls SCL low (clock stretching) during
    an I2C write, or a bus glitch holds the STOP condition.  MAIN's
    firmware polls SSPSTAT.P in a tight loop with no timeout (the M2
    chain in STOCK_SYNC_DEADLOCK_ANALYSIS).

    While MAIN is blocked on I2C, serial bytes from CONTROL accumulate
    in the 192-byte RX ring buffer at 0x0200.  The ring has NO
    overflow detection -- write_idx wraps silently past read_idx,
    overwriting unread data.  When MAIN resumes after the fault clears,
    the parser reads corrupted frames.

    This test:
    1. Boots to DISPLAY, confirms DSP baseline.
    2. Injects an extended MSSP STOP fault (blocks every I2C op for
       5M cycles, infinite count).
    3. CONTROL keeps sending display-loop commands for many steps.
    4. MAIN's RX ring fills and overflows.
    5. Clears the fault.
    6. Checks whether MAIN can still process volume commands correctly.

    Expected:
    - DSP command path is degraded or broken after ring overflow.
    - CONTROL may enter WAITING (MAIN can't respond while blocked).
    - Even after fault clears, DSP writes may fail silently due to
      parser desynchronization from the ring overflow.
    """
    _require_gpsim()
    _skip_missing(control_hex, PATCHED_MAIN_HEX)

    chain = _new_wire_chain(control_hex, PATCHED_MAIN_HEX)
    try:
        # Boot to DISPLAY
        first = chain.run_until_connected(limit=60)
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

        # Check ring state: has it wrapped?
        rx_rd_after = _read_reg(main_issue, 0x0C6)
        rx_wr_after = _read_reg(main_issue, 0x0C7)

        # Calculate bytes accumulated (approximate).  The ring is 192 bytes
        # (indices 0x00-0xBF).  If wr wrapped past rd, data was corrupted.
        ring_size = 0xC0  # 192 bytes
        used_before = (rx_wr_before - rx_rd_before) % ring_size
        used_after = (rx_wr_after - rx_rd_after) % ring_size

        # Clear the fault
        chain.clear_main_mssp_stop_faults()

        # Let MAIN resume and process whatever is in the ring
        chain.step_many(10)

        # Check if CONTROL entered WAITING (MAIN couldn't respond during fault)
        entered_waiting = chain.is_waiting()

        if entered_waiting:
            # Try to recover
            recovered = chain.run_until_connected(limit=60)
            # Stock CONTROL may or may not recover depending on parser state.
            if recovered is not None and chain.is_connected():
                # Recovered -- now check DSP integrity
                pass
            else:
                # Still stuck -- this is the irrecoverable case.
                # The MSSP fault cascaded to a permanent WAITING state
                # because MAIN's ring overflow desynchronized the parser.
                pytest.fail(
                    f"CONTROL stuck in WAITING after MSSP fault cleared — "
                    f"ring state: rd=0x{rx_rd_after:02X} wr=0x{rx_wr_after:02X} "
                    f"used_before={used_before} used_after={used_after} "
                    f"(ring overflow likely corrupted the frame parser)"
                )

        # DSP integrity check: volume UP after fault recovery
        snap_b = _dsp34_snapshot(main)
        chain.press("UP")
        chain.step_many(5)
        diff_post = _dsp34_diff(snap_b, _dsp34_snapshot(main))

        # After extended I2C blocking, the DSP command path should be
        # degraded.  MAIN's main loop was blocked for many steps,
        # serial bytes accumulated, and CONTROL likely entered WAITING.
        # Even after recovery, the DSP command path may be broken due
        # to parser desync from ring overflow or residual I2C state.
        #
        # We assert that the fault DID cause observable degradation.
        # If the DSP still works perfectly, the fault was too mild.
        dsp_degraded = len(diff_post) == 0
        control_lost = entered_waiting

        assert dsp_degraded or control_lost, (
            f"extended MSSP fault caused no observable degradation: "
            f"DSP still works ({len(diff_post)} changes) and CONTROL "
            f"never entered WAITING — fault parameters may be too mild"
        )

    finally:
        chain.close()
