"""V3.2 USB filename-transaction gate (option 3 firmware fix).

Pins both source-shape and behavioural contracts of the
``filename_dirty_flags.bit6`` gate that protects the
host-side cmd 0x03 (filename WRITE) -> force_persist sequence
from being raced by a concurrent CONTROL B0/20/x preset
broadcast.

Race the gate is closing
========================

Without the gate, this interleaving silently corrupts the
just-written filename:

  T=0   bit2=B (after USB switch), IDLE, dirty=0
  T=0   USB cmd 0x03 WRITE B's NEW filename:
          RAM[0x2C0..0x2DD] = "B-new", filename_dirty_flags.5 = 1
  T=10  CONTROL B0/20/00 broadcast (CONTROL still thinks A):
          preset_select_handler queues PENDING target=A
  T=11  preset_job_pending runs: dirty=1 -> persist B-new to bit2
          (B)'s slot 0x83 .  dirty cleared.
  T=11  -> HOLDING, 150 ms timer starts.
  T=151 HOLDING expires.  Toggle bit2 -> A.  preset_load_filename
          loads A's stored filename into RAM, clobbering "B-new"
          even though B-new is already on EEPROM.
          (RAM now has A-old, dirty=0.)
  T=200 Flasher's force_persist runs: writes RAM (A-old) to A's
          slot.  No-op (A's slot already had A-old).
  --- final state: B's slot has B-new (good); A's slot unchanged
  ---              (good); but the device is now on A, not B.

The above isn't actually corrupting in this exact trace -- the
saving grace is the dirty-flag persist in preset_job_pending.
The corruption window opens when cmd 0x03 fires DURING the
already-queued HOLDING (after preset_job_pending has run with
dirty=0):

  T=0   bit2=A, queued PENDING target=B (e.g. user-IR press).
  T=1   preset_job_pending runs: dirty=0, no persist.  -> HOLDING.
  T=10  USB cmd 0x03 WRITE: RAM = "B-new", dirty=1.
  T=151 HOLDING expires.  Toggle bit2 -> B.  preset_load_filename
          loads B's STORED filename, clobbering RAM.  RAM=B-old.
          dirty stays 1 (no persist ran here).
  T=200 force_persist: writes RAM (B-old) to B's slot.  B's slot
          stays B-old.  B-new is LOST.

The gate (filename_dirty_flags.bit6) protects this window by
making preset_select_handler DROP the broadcast when bit6 is set
-- target is not recorded and state stays IDLE.  Force_persist
clears bit6 after preset_persist_filename completes; the next
CONTROL full_sync_burst step 6 broadcast (within ~6 sec) retries
the preset switch normally.

Drop-vs-defer rationale
-----------------------

The original sketch deferred broadcasts (recorded target so a
later force_persist could redispatch).  Profiling on
``test_v171_v32_layer5_chain_lcd_renders_mixed_counters`` showed
that adding 4 instructions inside ``preset_select_handler``
shifted the ``cmd21_diag_query_handler`` body just enough to slow
the cmd 0x21 reply chain so the diag-cache slot[4] (R counter)
didn't reach CONTROL within the 400-wiggle test budget.  The drop
form uses 2 instructions (sharing the existing ``movlb 0x0`` at
the handler's top), keeping the shift minimal.  CONTROL's
~6 sec retry cadence makes drop and defer behaviourally
equivalent for any preset switch that's still pending after the
USB xact completes.

Robustness contract
===================

The tests below pin three claims, in both directions:

  1. Forward (gate works): while bit6 is set, preset broadcasts
     do NOT advance the preset_job state machine and do NOT
     update preset_job_target either (drop semantics).

  2. Back (no lockout): force_persist (event_flags.bit0) clears
     bit6 unconditionally as part of clearing bit5, so the device
     never gets stuck in a stale USB transaction.

  3. Resume (retry dispatch): once bit6 clears, the next
     preset_select_handler call (typically the next CONTROL
     full_sync_burst step 6 broadcast within ~6 sec) acts on
     the broadcast normally.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import V171_CONTROL_HEX, V32_MAIN_ASM, V32_MAIN_HEX

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


pytestmark = pytest.mark.dual_supported


# V3.2 RAM map (per src/dlcp_fw/asm/dlcp_main_v32.asm + ram.inc):
_ACTIVE_FLAGS = 0x05E              # bit 2 = preset selector (0=A, 1=B)
_ACTIVE_FLAGS_PRESET_BIT = 0x04
_EVENT_FLAGS = 0x07E               # bit 0 = dirty-service trigger
_EVENT_DIRTY_SERVICE = 0x01
_FILENAME_DIRTY_FLAGS = 0x0BD      # bit 5 = filename RAM dirty
_FILENAME_DIRTY = 0x20             # bit 5
_USB_XACT_PENDING = 0x40           # bit 6  (V3.2 gate, this commit)
_FILENAME_RAM_BASE = 0x2C0
_FILENAME_RAM_LEN = 0x1E           # 30 bytes
_PRESET_JOB_STATE = 0x2DE
_PRESET_JOB_TARGET = 0x2DF
_PRESET_JOB_IDLE = 0


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            f"rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _require_v32_hex(hex_path: Path) -> None:
    if not hex_path.exists():
        pytest.skip(f"missing V3.2 hex: {hex_path}")


def _require_v171_hex(hex_path: Path) -> None:
    if not hex_path.exists():
        pytest.skip(f"missing V1.71 hex: {hex_path}")


# ---------------------------------------------------------------------------
# Tier A: source-shape contract pins
# ---------------------------------------------------------------------------


def test_v32_ram_inc_documents_filename_dirty_flags_bit6_xact_gate() -> None:
    """The new bit6 of filename_dirty_flags must be documented in
    the asm so a future reader doesn't silently re-purpose it."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    # Find the filename_dirty_flags equate block + its trailing
    # comment lines (subsequent lines starting with whitespace + ;).
    m = re.search(
        r"filename_dirty_flags\s+EQU\s+0x0BD\b[^\n]*"
        r"(?:\n\s*;[^\n]*)*",
        text,
    )
    assert m is not None, "filename_dirty_flags equate missing"
    block = m.group(0)
    assert "bit5 = stock filename RAM slot dirty" in block, (
        "bit5 comment missing"
    )
    assert "bit6" in block and (
        "usb_filename_xact_pending" in block
        or "USB filename" in block
        or "xact" in block
    ), (
        "bit6 (USB filename xact gate) must be documented in the "
        "filename_dirty_flags equate block"
    )


def test_v32_cmd03_write_handler_sets_bit6_alongside_bit5() -> None:
    """cmd 0x03 filename WRITE handler must set BOTH bit5 (dirty) and
    bit6 (xact gate) so the gate is in effect from the moment RAM
    is updated until force_persist clears it."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    # The handler block at flow_hid_command_dispatch_111a:
    m = re.search(
        r"flow_hid_command_dispatch_111a:[^\n]*\n"
        r"(?:[^\n]*\n){0,15}?"
        r"\s*bsf\s+ram_0x0BD,\s*5,\s*BANKED[^\n]*\n"
        r"\s*bsf\s+ram_0x0BD,\s*6,\s*BANKED",
        text,
    )
    assert m is not None, (
        "cmd 0x03 WRITE handler at flow_hid_command_dispatch_111a "
        "must set both ram_0x0BD bit5 (filename dirty) and "
        "immediately bit6 (usb_filename_xact_pending).  Either "
        "bit is missing or they aren't adjacent."
    )


def test_v32_force_persist_clears_bit6_after_preset_persist_filename() -> None:
    """main_core_service_265c (the event_flags.0 dispatcher; the path
    force_persist USB trigger ultimately reaches) must clear bit6
    after `call preset_persist_filename` returns -- otherwise the
    gate stays set forever and the device is stuck."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    m = re.search(
        r"flow_main_core_service_265c_27bc:[^\n]*\n"
        r"\s*btfss\s+ram_0x0BD,\s*5,\s*BANKED[^\n]*\n"
        r"\s*bra\s+flow_main_core_service_265c_27ec[^\n]*\n"
        r"\s*call\s+preset_persist_filename[^\n]*\n"
        r"(?:[^\n]*\n){0,12}?"
        r"\s*bcf\s+ram_0x0BD,\s*6,\s*BANKED",
        text,
    )
    assert m is not None, (
        "main_core_service_265c persist branch must clear bit6 "
        "(usb_filename_xact_pending) after preset_persist_filename "
        "returns.  Without this, the gate never clears and the "
        "device is permanently locked out of preset switches once "
        "a USB cmd 0x03 has fired."
    )


def test_v32_preset_select_handler_gates_state_machine_on_bit6() -> None:
    """preset_select_handler must check filename_dirty_flags.bit6
    EARLY (before storing target) and bra to
    preset_select_handler_done if set, dropping the broadcast
    entirely.  CONTROL's ~6 sec full_sync_burst step 6 cadence
    will retry once the gate clears."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    m = re.search(
        r"preset_select_handler:[^\n]*\n"
        r"\s*movlb\s+0x0[^\n]*\n"
        r"(?:[^\n]*\n){0,8}?"
        r"\s*btfsc\s+filename_dirty_flags,\s*6,\s*BANKED[^\n]*\n"
        r"\s*bra\s+preset_select_handler_done",
        text,
    )
    assert m is not None, (
        "preset_select_handler must, after the entry "
        "``movlb 0x0`` and before storing target / advancing "
        "state, check filename_dirty_flags.bit6 and bra to "
        "preset_select_handler_done if set.  Otherwise the state "
        "machine advances to PENDING during a USB filename xact "
        "and racy preset_load_filename clobbers the host's RAM."
    )
    # The gate MUST land BEFORE the target store -- otherwise we
    # are deferring not dropping, which conflicts with the docstring
    # contract and re-introduces the code-shift timing risk that
    # broke layer5_diag_chain.
    bra_idx = m.end()
    target_store_idx = text.find("preset_job_target, BANKED", bra_idx)
    assert target_store_idx > 0, (
        "preset_job_target must still be stored later in the handler"
    )
    # Sanity: the gate match must be inside preset_select_handler
    # and the target store must be downstream of it.
    handler_start = text.find("preset_select_handler:")
    assert handler_start <= m.start() < target_store_idx, (
        "gate placement lookups misaligned"
    )


# ---------------------------------------------------------------------------
# Tier B: behavioural contract pins (rust sim chain)
# ---------------------------------------------------------------------------


def _open_chain():
    """Open a V1.71 + 2x V3.2 chain, run it to CONNECTED steady-state,
    settle the boot-time preset job, and return.  Behavioural tests
    operate on MAIN0 specifically; the second MAIN is along for the
    chain semantics so V3.2 reaches a fully-booted, fully-awake state
    where preset_select_handler actually parses and the preset_job
    state machine can advance (preset_job_service gates on
    active_flags.bit3 -- without a chain peer the MAIN stays in
    standby and broadcasts are silently cancelled).
    """
    _require_v171_hex(V171_CONTROL_HEX)
    chain = RustChain.from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(V32_MAIN_HEX),
    )
    chain.run_until_connected(limit=400)
    assert chain.is_connected() and not chain.is_waiting(), (
        f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
    )
    # Allow boot-time preset-load to complete.
    chain.step_ticks(50_000_000)
    pjs = chain.read_main_reg(0, _PRESET_JOB_STATE)
    assert pjs == _PRESET_JOB_IDLE, (
        f"chain failed to reach IDLE post-boot (pjs={pjs})"
    )
    return chain


def _set_filename_xact(chain) -> None:
    """Simulate a USB cmd 0x03 WRITE-sized side-effect on RAM:
    set the dirty flag AND the xact gate bit, mimicking what the
    cmd 0x03 WRITE handler does at asm:flow_hid_command_dispatch_111a.

    Reading the flag back via read_main_reg verifies the bits are
    set as expected before the test proceeds."""
    flags = chain.read_main_reg(0, _FILENAME_DIRTY_FLAGS)
    chain.write_main_reg(
        0,
        _FILENAME_DIRTY_FLAGS,
        flags | _FILENAME_DIRTY | _USB_XACT_PENDING,
    )
    after = chain.read_main_reg(0, _FILENAME_DIRTY_FLAGS)
    assert after & _USB_XACT_PENDING, (
        f"setup: usb_filename_xact_pending bit (0x40) did not stick "
        f"after write; got 0x{after:02X}"
    )
    assert after & _FILENAME_DIRTY, (
        f"setup: filename dirty bit (0x20) did not stick after write; "
        f"got 0x{after:02X}"
    )


def test_v32_xact_gate_blocks_preset_broadcast_state_machine_entry() -> None:
    """While filename_dirty_flags.bit6 is set, an incoming B0/20/x
    broadcast must NOT advance preset_job_state past IDLE.  Drop
    semantics: target is NOT recorded either (CONTROL retries
    every full_sync_burst step 6 cycle so a later broadcast after
    the gate clears resumes normal operation)."""
    _require_rust()
    _require_v32_hex(V32_MAIN_HEX)
    chain = _open_chain()

    # Capture initial state.
    initial_af = chain.read_main_reg(0, _ACTIVE_FLAGS)
    initial_bit2 = (initial_af & _ACTIVE_FLAGS_PRESET_BIT) >> 2
    initial_pjt = chain.read_main_reg(0, _PRESET_JOB_TARGET)

    # Enter a synthetic USB filename xact.
    _set_filename_xact(chain)

    # Inject the OPPOSITE preset target (so a normal switch would
    # fire if the gate weren't holding).
    target = 1 - initial_bit2
    chain.inject_main_frames_fifo([[0xB0, 0x20, target]], fifo_limit=47)

    # Step a healthy budget.  preset_select_handler should run as
    # MAIN parses the frame and bra to ``preset_select_handler_done``
    # without storing target or advancing state.
    chain.step_ticks(100_000_000)

    pjs = chain.read_main_reg(0, _PRESET_JOB_STATE)
    pjt = chain.read_main_reg(0, _PRESET_JOB_TARGET)
    af = chain.read_main_reg(0, _ACTIVE_FLAGS)
    flags = chain.read_main_reg(0, _FILENAME_DIRTY_FLAGS)

    assert pjs == _PRESET_JOB_IDLE, (
        f"preset_job_state must stay IDLE while gate is held; "
        f"got pjs={pjs} (gate={'held' if flags & _USB_XACT_PENDING else 'cleared'})"
    )
    assert pjt == initial_pjt, (
        f"preset_job_target must NOT update when the gate is held "
        f"(drop semantics); initial={initial_pjt}, got={pjt}, "
        f"injected_target={target}.  CONTROL's full_sync_burst step 6 "
        f"will retry once the gate clears."
    )
    af_bit2 = (af & _ACTIVE_FLAGS_PRESET_BIT) >> 2
    assert af_bit2 == initial_bit2, (
        f"active_flags.bit2 must NOT have toggled (gate held); "
        f"initial={initial_bit2}, got={af_bit2}"
    )
    assert flags & _USB_XACT_PENDING, (
        f"gate bit (0x40) must remain set; got 0x{flags:02X}"
    )


def test_v32_force_persist_clears_xact_gate_robust_no_lockout() -> None:
    """Triggering force_persist (event_flags.bit0=1) must clear
    BOTH bit5 (filename dirty) AND bit6 (xact gate) once
    preset_persist_filename completes.  This is the no-lockout
    guarantee: a host that crashes mid-transaction will, on the
    NEXT successful force_persist (which the next flasher run will
    issue), unstick the gate and re-enable preset broadcasts."""
    _require_rust()
    _require_v32_hex(V32_MAIN_HEX)
    chain = _open_chain()

    _set_filename_xact(chain)

    # Trigger main_core_service_265c via event_flags.bit0.
    ev = chain.read_main_reg(0, _EVENT_FLAGS)
    chain.write_main_reg(0, _EVENT_FLAGS, ev | _EVENT_DIRTY_SERVICE)

    # Step enough for main_core_service_265c to dispatch.  The
    # block walker + filename persist takes a few main loop passes
    # plus the 30-byte EEPROM write loop (~30 ms in real time).
    chain.step_ticks(200_000_000)

    flags = chain.read_main_reg(0, _FILENAME_DIRTY_FLAGS)
    assert (flags & _FILENAME_DIRTY) == 0, (
        f"filename dirty bit must clear after force_persist; "
        f"got 0x{flags:02X}"
    )
    assert (flags & _USB_XACT_PENDING) == 0, (
        f"xact gate (bit6) must clear after force_persist; "
        f"got 0x{flags:02X}.  This is the no-lockout guarantee -- "
        f"if this fails, the device is permanently stuck."
    )


def test_v32_post_gate_broadcast_dispatches_normally() -> None:
    """After force_persist clears the gate, a subsequent broadcast
    must advance the preset_job state machine as if the gate had
    never been set.  This is the resume guarantee."""
    _require_rust()
    _require_v32_hex(V32_MAIN_HEX)
    chain = _open_chain()

    initial_af = chain.read_main_reg(0, _ACTIVE_FLAGS)
    initial_bit2 = (initial_af & _ACTIVE_FLAGS_PRESET_BIT) >> 2
    target = 1 - initial_bit2

    # Set gate, broadcast (deferred), force_persist (clears gate).
    _set_filename_xact(chain)
    chain.inject_main_frames_fifo([[0xB0, 0x20, target]], fifo_limit=47)
    chain.step_ticks(50_000_000)
    ev = chain.read_main_reg(0, _EVENT_FLAGS)
    chain.write_main_reg(0, _EVENT_FLAGS, ev | _EVENT_DIRTY_SERVICE)
    chain.step_ticks(200_000_000)
    flags = chain.read_main_reg(0, _FILENAME_DIRTY_FLAGS)
    assert (flags & _USB_XACT_PENDING) == 0, "setup: gate did not clear"

    # NOW broadcast again — this time the state machine should
    # advance.  Inject the SAME target as before; it's still
    # different from the current bit2 (we never actually toggled).
    chain.inject_main_frames_fifo([[0xB0, 0x20, target]], fifo_limit=47)
    # Step enough for HOLDING (~150 ms = ~7 M ticks) + APPLY/COMMIT
    # (96 I²C entries, slow on rust sim).  Use the same generous
    # budget as the dual-MAIN sync tests.
    for _ in range(60):
        chain.step_ticks(50_000_000)
        af = chain.read_main_reg(0, _ACTIVE_FLAGS)
        pjs = chain.read_main_reg(0, _PRESET_JOB_STATE)
        bit2 = (af & _ACTIVE_FLAGS_PRESET_BIT) >> 2
        if bit2 == target and pjs == _PRESET_JOB_IDLE:
            break

    af = chain.read_main_reg(0, _ACTIVE_FLAGS)
    bit2 = (af & _ACTIVE_FLAGS_PRESET_BIT) >> 2
    pjs = chain.read_main_reg(0, _PRESET_JOB_STATE)
    assert bit2 == target, (
        f"post-gate broadcast must drive bit2 to target ({target}); "
        f"got bit2={bit2}.  Resume guarantee broken."
    )
    assert pjs == _PRESET_JOB_IDLE, (
        f"post-gate broadcast must complete (pjs=IDLE); got pjs={pjs}"
    )


def test_v32_no_gate_broadcast_unaffected_by_fix() -> None:
    """Sanity: when no USB xact is in flight (bit6 clear), preset
    broadcasts behave exactly like they did before this commit --
    the gate is invisible to the unimpeded path.  This protects
    against a future regression that accidentally inverts the
    btfsc / btfss polarity in preset_select_handler."""
    _require_rust()
    _require_v32_hex(V32_MAIN_HEX)
    chain = _open_chain()

    initial_af = chain.read_main_reg(0, _ACTIVE_FLAGS)
    initial_bit2 = (initial_af & _ACTIVE_FLAGS_PRESET_BIT) >> 2
    target = 1 - initial_bit2

    # Confirm gate is clear at baseline.
    flags = chain.read_main_reg(0, _FILENAME_DIRTY_FLAGS)
    assert (flags & _USB_XACT_PENDING) == 0, (
        f"baseline: gate must be clear; got 0x{flags:02X}"
    )

    # Broadcast and wait for convergence.
    chain.inject_main_frames_fifo([[0xB0, 0x20, target]], fifo_limit=47)
    for _ in range(60):
        chain.step_ticks(50_000_000)
        af = chain.read_main_reg(0, _ACTIVE_FLAGS)
        pjs = chain.read_main_reg(0, _PRESET_JOB_STATE)
        bit2 = (af & _ACTIVE_FLAGS_PRESET_BIT) >> 2
        if bit2 == target and pjs == _PRESET_JOB_IDLE:
            break

    af = chain.read_main_reg(0, _ACTIVE_FLAGS)
    bit2 = (af & _ACTIVE_FLAGS_PRESET_BIT) >> 2
    assert bit2 == target, (
        f"baseline broadcast (no gate) must drive bit2 to target "
        f"({target}); got bit2={bit2}.  Possible polarity inversion "
        f"in the gate check -- preset_select_handler may now skip "
        f"normal broadcasts too."
    )
