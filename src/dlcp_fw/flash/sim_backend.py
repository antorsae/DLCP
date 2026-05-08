"""Sim-backed USB transport for the V3.2 release flasher.

The flasher (``dlcp_main_flash.py``) talks to the live MAIN over two USB
surfaces:

  * **EP0 control transfers** via the ``DlcpEp0`` class
    (pyusb-backed).  Used for byte-level reads / writes of arbitrary
    RAM, SFR, and EEPROM-shadow state -- e.g. ``_ep0_read_byte``,
    ``_ep0_write_byte``, ``_force_active_filename_persist`` (sets
    ``event_flags.0``), ``_switch_active_preset_ep0`` (writes
    ``active_flags`` + polls reapply mask).

  * **HID feature reports / 64-byte interrupt reports** via hidapi.
    Used for ``cmd 0x03`` (filename WRITE / ERASE), ``cmd 0x43``
    (DIAG_MEMREAD), and the ``cmd 0x40``/``0x41`` bootloader stream.

This module supplies sim-backed implementations that route EP0 ops
through the rust simulator's per-MAIN ``read_main_reg`` / ``write_main_reg``
PyO3 facade, so the actual flasher script can run end-to-end against a
``Chain.from_v171_v32`` rust-sim chain (option A from the
flasher-integration menu).

Scope of the current MVP
========================

* ``SimDlcpEp0`` (this module) implements the ``DlcpEp0`` interface
  for the EP0 surface: ``set_pointer``, ``read_exact``, ``_poke``.
  Routes byte-level reads and writes to ``chain.read_main_reg`` /
  ``chain.write_main_reg`` against the per-MAIN ``unit`` index.
  Skips the USB control-transfer state machine entirely; the
  semantic effect on firmware-visible RAM/SFR is the same as the
  real EP0 protocol's ``_poke(addr, value, in_dir=…)`` cycle.

* HID feature reports / 64-byte reports (``send_feature_report`` /
  ``read``) are NOT yet implemented here.  Tests that need them
  should write to firmware staging RAM directly (the existing
  ``test_v32_usb_filename_xact_gate.py`` pattern: poke
  ``filename_dirty_flags`` bits + ``preset_filename_ram_base``
  bytes).  A future commit adds a ``SimHidBackend`` that wraps the
  rust sim's USB BDT injection so cmd 0x03's actual firmware-side
  dispatch runs end-to-end.

Usage
=====

::

    from dlcp_fw.sim.dlcp_sim_native import Chain
    from dlcp_fw.flash.sim_backend import SimDlcpEp0

    chain = Chain.from_v171_v32(control_hex_path=..., main_hex_path=...)
    chain.run_until_connected(limit=400)

    # Construct an EP0 backend that targets MAIN1 (PB2 / right).
    ep0 = SimDlcpEp0(chain=chain, unit=1)

    # Existing flasher helpers accept any ``DlcpEp0``-shaped object;
    # ``ep0.read_exact`` / ``ep0._poke`` route straight through.
    ep0.set_pointer(0x05E)         # active_flags
    flags = ep0.read_exact(1)[0]
    ep0._poke(0x07E, 0x01, False)  # event_flags.0 = 1 (force_persist trigger)
"""

from __future__ import annotations

from typing import Optional


class SimDlcpEp0:
    """``DlcpEp0``-shaped EP0 transport backed by the rust simulator.

    The real ``DlcpEp0`` class (in ``dlcp_ep0_eeprom_shadow_dump.py``)
    wraps pyusb's ``ctrl_transfer`` to send custom DLCP control
    requests with ``bRequest=0x0B``, encoding the target byte address
    via ``idx_for_addr``.  The firmware translates that idx back into
    a physical RAM/SFR/EEPROM-shadow address, services the read or
    write, and ACKs.

    For the simulator we skip the USB layer entirely and route to
    ``chain.read_main_reg(unit, addr)`` / ``chain.write_main_reg
    (unit, addr, value)`` directly.  The semantic effect (firmware
    sees a byte read / write at ``addr``) is identical for every EP0
    op the flasher currently issues.  We do model the
    ``set_pointer`` / ``read_exact(n)`` auto-incrementing pointer
    pattern via Python-side state so multi-byte reads work the same
    way the real EP0 protocol does.

    Parameters
    ----------
    chain
        A ``dlcp_fw.sim.dlcp_sim_native.Chain`` instance.  Must be
        booted to a stable runtime state (typically via
        ``run_until_connected``) before any EP0 op fires.
    unit
        Per-MAIN index: ``0`` for MAIN0 (PB1, ``--left``), ``1`` for
        MAIN1 (PB2, ``--right``).  Maps to ``chain.read_main_reg
        (unit, addr)``.

    Notes
    -----
    * The real EP0 protocol does NOT auto-step the chain after each
      op; the firmware services the control transfer when the host
      polls.  In the sim, the firmware runs concurrently with the
      Python code, so each ``_poke`` / ``read_exact`` call is
      followed by a small ``chain.step_ticks`` so the firmware has
      a chance to observe the change.  Default step is 100 K ticks
      (~ 2 ms sim time at 48 MHz universal clock).  Override via
      ``step_ticks_per_op`` if a test needs different settling.

    * ``_poke`` here mirrors the real ``DlcpEp0._poke`` signature
      (``addr``, ``value``, ``in_dir``, ``read_len``) but ignores
      ``read_len`` for the write path.  In the read path, ``addr``
      is interpreted as the read trigger index; we only handle the
      single-byte read at ``addr=current_pointer`` to support
      ``read_exact``'s ``_poke(0xE7, ...)`` pattern.

    Limitations
    -----------
    * No HID feature report support (cmd 0x03 / 0x43 / 0x40 / 0x41).
      Tests that need cmd 0x03 should poke ``filename_dirty_flags``
      bits + ``preset_filename_ram_base`` directly, the way
      ``test_v32_usb_filename_xact_gate.py`` does.

    * No EP0 stall / NAK simulation.  Every op succeeds.  This is
      semantically correct for the post-flash finalize sequence
      because the real device never NAKs these ops in healthy
      operation; tests that want to stress NAK paths still need
      the real-USB backend.
    """

    # Real EP0 protocol's idx-encoding constants.  We don't actually
    # apply these in the sim path (we use the raw addr instead) but
    # documenting them here helps readers cross-reference.
    _EP0_TBLPTRL_IDX_ADDR = 0x75   # _poke(0x75, lo) → write TBLPTRL
    _EP0_TBLPTRH_IDX_ADDR = 0x76   # _poke(0x76, hi) → write TBLPTRH
    _EP0_READ_TRIGGER_ADDR = 0xE7  # _poke(0xE7, n, in_dir=True, read_len=n)

    def __init__(
        self,
        chain,  # type: ignore[no-untyped-def]
        unit: int = 1,
        *,
        step_ticks_per_op: int = 0,
    ) -> None:
        """``step_ticks_per_op`` defaults to 0: read/write ops do NOT
        advance the chain.  Each EP0 op is therefore atomic w.r.t.
        firmware-side state -- a poke immediately followed by a read
        returns the just-written value regardless of which RAM slot
        is targeted.  Tests that explicitly want firmware to react
        between ops (e.g. force_persist) call ``chain.step_ticks(N)``
        themselves.  Set ``step_ticks_per_op > 0`` only for soak /
        latency-sensitive tests where the goal is to mirror the
        ~1 ms host-poll cadence of real EP0."""
        if unit not in (0, 1):
            raise ValueError(f"unit must be 0 or 1; got {unit}")
        self._chain = chain
        self._unit = unit
        self._step_ticks_per_op = step_ticks_per_op
        self._pointer: int = 0

    @property
    def unit(self) -> int:
        return self._unit

    def set_pointer(self, addr16: int) -> None:
        """Update the firmware-visible read pointer (TBLPTRL:TBLPTRH).

        Real EP0 writes TBLPTRL via ``_poke(0x75, lo)`` and TBLPTRH
        via ``_poke(0x76, hi)``.  In the sim we just store the
        16-bit address Python-side; subsequent ``read_exact`` calls
        read sequential bytes starting from this pointer.
        """
        if not (0 <= addr16 <= 0xFFFF):
            raise ValueError(f"addr16 out of range: 0x{addr16:04X}")
        self._pointer = addr16

    def read_exact(self, n: int) -> bytes:
        """Read ``n`` bytes starting at the current pointer; auto-
        increment the pointer.  Mirrors the real EP0 protocol's
        ``read_exact`` semantics.

        Raises ``ValueError`` if the read would cross the 0x10000
        boundary -- the real firmware's TBLPTRH-driven EP0 path
        switches read regions when the pointer climbs past the
        12-bit data-memory window, which the sim does not model.
        Surfacing the divergence loudly avoids silent wrap-around
        reads that look correct but read from address 0x000+ on
        the second byte (codex LOW vs 83fb65c)."""
        if n <= 0:
            return b""
        if self._pointer + n > 0x10000:
            raise ValueError(
                f"EP0 read would wrap past 0x10000 "
                f"(pointer=0x{self._pointer:04X}, n={n}); "
                f"the simulator does not model the real protocol's "
                f"TBLPTRH-region switch above the 12-bit data-memory "
                f"window."
            )
        out = bytearray(n)
        for i in range(n):
            out[i] = (
                self._chain.read_main_reg(self._unit, self._pointer + i) & 0xFF
            )
        # Step the chain so any firmware-side observers (e.g. a
        # routine polling for activity) can see the read effect.
        # Real EP0 reads complete on host-side polling; firmware
        # only sees a TBLPTR advance, which is benign.
        if self._step_ticks_per_op > 0:
            self._chain.step_ticks(self._step_ticks_per_op)
        # Auto-increment the pointer (the real EP0 protocol uses
        # firmware-side TBLPTR with auto-increment in the read path
        # via ``_poke(0xE7, n, in_dir=True, ...)``).  No mask: a
        # successful read at the upper limit (e.g. ``read_exact(1)``
        # from 0xFFFF) leaves the pointer at 0x10000.  Subsequent
        # reads then trip the wrap check above and raise -- catches
        # CHUNKED crossings (codex LOW vs 805afd2; the previous mask
        # silently wrapped a follow-up read to address 0x000).
        self._pointer = self._pointer + n
        return bytes(out)

    def _poke(
        self,
        addr: int,
        value: int,
        in_dir: bool,
        read_len: int = 0,
    ) -> bytes:
        """Mirror ``DlcpEp0._poke``.  Three call shapes the flasher uses:

        1. ``_poke(0x75, lo, in_dir=False)`` / ``_poke(0x76, hi, ...)``
           -- written by ``set_pointer(addr16)``.  We translate by
           reading the 16-bit pointer state stored Python-side
           (effectively a no-op at the firmware-RAM level since we
           don't model TBLPTR; ``set_pointer`` updates ``self._pointer``
           directly).

        2. ``_poke(addr, value, in_dir=False)`` for arbitrary
           writes -- e.g. ``_ep0_write_byte`` for a single byte poke
           at any 8-bit-encoded address.  We route to
           ``chain.write_main_reg(unit, addr, value)``.  ``addr`` is
           the SHORT 8-bit form the flasher uses; we pass it through
           to ``write_main_reg`` because the test addresses we care
           about (``ACTIVE_FLAGS_ADDR=0x05E``, ``EVENT_FLAGS_ADDR
           =0x07E``) are all in the 0..0xFF range and identical
           between the two encodings.

        3. ``_poke(0xE7, n, in_dir=True, read_len=n)`` -- triggers
           the firmware's TBLPTR-pointed read, returning ``n``
           bytes.  We bypass ``addr=0xE7`` and just read ``read_len``
           bytes from ``self._pointer``, advancing the pointer.
        """
        if not (0 <= value <= 0xFF):
            raise ValueError(f"value out of range: 0x{value:02X}")

        if addr == self._EP0_TBLPTRL_IDX_ADDR and not in_dir:
            self._pointer = (self._pointer & 0xFF00) | (value & 0xFF)
            return b""
        if addr == self._EP0_TBLPTRH_IDX_ADDR and not in_dir:
            self._pointer = ((value & 0xFF) << 8) | (self._pointer & 0x00FF)
            return b""
        if addr == self._EP0_READ_TRIGGER_ADDR and in_dir:
            # ``read_len`` bytes from the TBLPTR-pointed location,
            # auto-incrementing.  Mirrors the real EP0 read path.
            return self.read_exact(read_len)

        if in_dir:
            # Short read at ``addr`` (no TBLPTR involved).  The real
            # protocol returns ``read_len`` bytes; in practice the
            # flasher only uses this for single-byte reads but we
            # honour ``read_len`` directly for parity.  ``read_len=0``
            # is an empty read (matches ``DlcpEp0._poke``'s
            # ``ctrl_transfer(..., 0)`` -> empty bytes return; codex
            # LOW vs 83fb65c).
            if read_len <= 0:
                return b""
            out = bytearray(read_len)
            for i in range(read_len):
                out[i] = (
                    self._chain.read_main_reg(self._unit, (addr + i) & 0xFFFF)
                    & 0xFF
                )
            if self._step_ticks_per_op > 0:
                self._chain.step_ticks(self._step_ticks_per_op)
            return bytes(out)

        # Write path: poke a single byte at ``addr``.
        self._chain.write_main_reg(self._unit, addr & 0xFFFF, value & 0xFF)
        if self._step_ticks_per_op > 0:
            self._chain.step_ticks(self._step_ticks_per_op)
        return b""

    # ---- DlcpEp0 attribute parity --------------------------------------

    @property
    def dev(self):  # type: ignore[no-untyped-def]
        """Stand-in for the pyusb device handle.  Some flasher code
        passes ``ep0.dev`` to other helpers; return ``None`` so any
        access raises a clear ``AttributeError`` if a code path
        actually depends on the underlying USB device.  All usages
        in the post-flash finalize go through ``set_pointer`` /
        ``read_exact`` / ``_poke`` which we DO implement."""
        return None


def make_sim_ep0(
    chain,  # type: ignore[no-untyped-def]
    *,
    unit: int = 1,
    step_ticks_per_op: int = 0,
) -> SimDlcpEp0:
    """Convenience factory for tests / scripts.

    Builds a ``SimDlcpEp0`` against a rust simulator chain.  Mirrors
    the real-USB ``DlcpEp0(vid=..., pid=..., path=...)`` constructor
    pattern but takes a chain handle + per-MAIN unit index instead.
    """
    return SimDlcpEp0(chain, unit=unit, step_ticks_per_op=step_ticks_per_op)
