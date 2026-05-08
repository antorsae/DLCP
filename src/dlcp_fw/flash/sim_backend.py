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


# ============================================================================
# SimHidBackend / SimUsbHub: HID feature-report path for cmd 0x03 / 0x06 /
# 0x40 / 0x41 / 0x43.
# ============================================================================
#
# The flasher's HID surface uses 64-byte reports written via ``dev.write(buf)``
# and read via ``dev.read(64, timeout_ms)``.  ``SimHidBackend`` is a duck-type
# drop-in for ``hid.device`` that dispatches each cmd to a chain-backed
# shortcut.  ``SimUsbHub`` aggregates one ``SimHidBackend`` per simulated MAIN
# and provides ``enumerate_devices`` / ``open_hid_path`` etc. that the existing
# flasher modules can be hooked through.
#
# Why direct shortcuts instead of full BDT injection:
#
# * cmd 0x40 (app->bootloader switch + bootloader stream) -- the rust sim does
#   NOT model the PIC18 boot block (0x0000..0x0FFF), so the actual bootloader
#   firmware can't run.  We FAKE the mode switch (flip a per-device flag) and
#   FAKE the stream + CRC verify (capture bytes, compute CRC, return success).
#   The running firmware in the sim is the post-flash V3.2 image already; the
#   stream just exercises the wire protocol shape.
#
# * cmd 0x03 / 0x06 / 0x43 -- mirror the firmware-visible effect via direct
#   chain pokes / reads.  Same pattern as ``test_v32_usb_filename_xact_gate.py``
#   for cmd 0x03's WRITE / ERASE.
# ============================================================================

import contextlib
import dataclasses
import threading
from typing import Callable, Iterable, List, Optional


_HID_REPORT_LEN = 64

# RAM addresses used by V3.2's USB cmd 0x03 filename WRITE/ERASE.  Cross-
# checked against ``src/dlcp_fw/flash/dlcp_main_flash.py`` constants
# (``FILENAME_RAM_BASE``, ``ROUTE_DIRTY_FLAGS_ADDR``, etc) and against the
# V3.2 firmware-side semantics in ``src/dlcp_fw/asm/dlcp_main_v32.asm``.
_FILENAME_RAM_BASE = 0x2C0
_FILENAME_RAM_LEN = 0x1E
_FILENAME_DIRTY_FLAGS_ADDR = 0x0BD
_FILENAME_DIRTY_BIT = 0x20  # bit5: filename region dirty
_USB_XACT_PENDING_BIT = 0x40  # bit6: USB filename transaction in flight

# Subcmds for cmd 0x03 (mirror flasher's CMD03_FILENAME_*_SUBCMD constants).
_CMD03_FILENAME_READ_SUBCMD = 0x08
_CMD03_FILENAME_WRITE_SUBCMD = 0x09
_CMD03_FILENAME_ERASE_SUBCMD = 0x0A

# Subcmd for cmd 0x06 (version probe).
_CMD06_VERSION_SUBCMD = 0x01

# DIAG_MEMREAD constants (mirror real firmware-side handler in
# ``crates/dlcp-sim/src/peripherals/usb.rs::handle_memread``).
_CMD_DIAG_MEMREAD = 0x43
_DIAG_MEMREAD_REGION_FLASH = 0x00
_DIAG_MEMREAD_REGION_EEPROM = 0x01
_DIAG_MEMREAD_MAX_LEN = 0x3D

# Bootloader stream window: app firmware lives at 0x1000..0x5FFF inclusive.
_BOOTLOADER_APP_START = 0x1000
_BOOTLOADER_APP_END_EXCL = 0x6000
_BOOTLOADER_PACKET_PAYLOAD_LEN = 30


def _crc_pic18_stream(data: bytes) -> int:
    """Reuse the real flasher's ``crc_stream`` (bootloader CRC).

    Lazy import so this module's load order is independent of
    ``dlcp_control_flash``.  The real ``crc_stream`` is also what the
    flasher's host-side host-CRC computation uses, so by reusing it we
    guarantee that a sim cmd 0x41 verify accepts whatever CRC the
    flasher's ``flash_main`` would compute on the same stream."""
    from dlcp_fw.flash.dlcp_control_flash import crc_stream
    return crc_stream(data)


@dataclasses.dataclass
class SimUsbDevice:
    """Per-simulated-MAIN USB device record.

    Tracks the device's mode (app vs bootloader), its synthetic identity
    strings, and -- when in bootloader mode -- the captured firmware
    stream + the host-supplied CRC for verify.

    The real DLCP MAIN's product_string contains "DLCP" in app mode and
    "bootl" in bootloader mode (the flasher's ``_device_mode`` checks for
    ``BOOTLOADER_PRODUCT_TOKEN = "bootl"`` substring).
    """

    unit: int  # 0 = MAIN0 / PB1 / left, 1 = MAIN1 / PB2 / right
    path: bytes
    serial_number: str
    app_product_string: str = "DLCP V3.2 sim"
    bootloader_product_string: str = "DLCP bootloader sim"
    manufacturer_string: str = "Hypex sim"
    mode: str = "app"  # "app" or "bootloader"
    bootloader_stream: bytearray = dataclasses.field(default_factory=bytearray)

    @property
    def product_string(self) -> str:
        if self.mode == "bootloader":
            return self.bootloader_product_string
        return self.app_product_string


class SimHidBackend:
    """``hid.device``-shaped HID transport backed by the rust simulator.

    Implements the minimal interface the flasher's HID helpers consume:

      * ``write(buf)``:   ``buf`` is 65 bytes (1 report id + 64 payload);
                          returns the number of bytes written.
      * ``read(size, timeout_ms)``: returns up to ``size`` bytes.  We always
                          return a 64-byte response; the caller's
                          ``_hid_read64`` strips any leading 0x00 if present.
      * ``close()``:      no-op on the sim path.
      * ``set_nonblocking(flag)``: no-op (sim is always synchronous).

    Dispatches on the cmd byte (payload[0]) to chain-backed shortcuts.  Each
    response is queued onto ``self._read_queue``; the next ``read`` pops the
    head.  Out-of-band reports (e.g. unrelated to the just-issued write)
    aren't simulated -- the flasher never relies on them in healthy
    operation.

    Construction is via ``SimUsbHub.open_hid_path(path)``; do not instantiate
    directly.
    """

    def __init__(
        self,
        hub: "SimUsbHub",
        device: SimUsbDevice,
        *,
        step_ticks_per_op: Optional[int] = None,
    ) -> None:
        self._hub = hub
        self._device = device
        self._read_queue: list[bytes] = []
        self._closed = False
        self._lock = threading.Lock()
        # Inherit from hub if not explicitly overridden so
        # ``cmd 0x43 verify`` (~70 reads in a row) accumulates sim time
        # the same way EP0 polling does.  Without this, a long verify
        # phase advances 0 sim time and the subsequent preset-switch
        # via EP0 sees a stale firmware state (active_flags.7 still set
        # because no chain frame has fired since the EP0 write).
        if step_ticks_per_op is None:
            self._step_ticks_per_op = hub.default_step_ticks_per_hid_op
        else:
            self._step_ticks_per_op = max(0, int(step_ticks_per_op))

    # ---- hid.device duck-type API --------------------------------------

    def write(self, buf) -> int:  # type: ignore[no-untyped-def]
        """Process a HID write.  ``buf`` is 65 bytes: a leading 0x00 report
        id followed by the 64-byte payload."""
        if self._closed:
            raise RuntimeError("write to closed SimHidBackend")
        b = bytes(buf)
        if len(b) != _HID_REPORT_LEN + 1:
            raise ValueError(
                f"SimHidBackend.write expected {_HID_REPORT_LEN + 1} bytes "
                f"(1 report id + {_HID_REPORT_LEN} payload); got {len(b)}"
            )
        if b[0] != 0x00:
            raise ValueError(
                f"SimHidBackend.write expected leading 0x00 report id; "
                f"got 0x{b[0]:02X}"
            )
        payload = b[1:]
        response = self._dispatch(payload)
        if response is not None:
            with self._lock:
                self._read_queue.append(response)
        # Step the chain so the firmware can react between HID ops.
        # Critical for cmd 0x43 verify (~70 reads in a row) -- without
        # stepping, sim time stalls during the verify phase and the
        # subsequent EP0 preset-switch sees a stale active_flags.7
        # (no chain frame fired between EP0 write and EP0 poll).
        if self._step_ticks_per_op > 0:
            self._hub._chain.step_ticks(self._step_ticks_per_op)
        return len(b)

    def read(self, size: int, timeout_ms: int = 0) -> list[int]:
        """Pop the next queued response.  ``size`` is ignored beyond
        ensuring it >= 64; we always return a full 64-byte response.
        Real hidapi returns ``list[int]`` so we mirror that shape."""
        if self._closed:
            raise RuntimeError("read from closed SimHidBackend")
        if size < _HID_REPORT_LEN:
            raise ValueError(
                f"SimHidBackend.read expected size >= {_HID_REPORT_LEN}; "
                f"got {size}"
            )
        with self._lock:
            if not self._read_queue:
                # No pending response -> "timeout" (return empty list, like
                # hidapi does).  The caller's ``_hid_read64`` treats empty as
                # ``None``.
                return []
            head = self._read_queue.pop(0)
        return list(head)

    def close(self) -> None:
        self._closed = True

    def set_nonblocking(self, flag: bool) -> None:
        pass

    # ---- Cmd dispatch --------------------------------------------------

    def _dispatch(self, payload: bytes) -> Optional[bytes]:
        if len(payload) != _HID_REPORT_LEN:
            raise ValueError(
                f"_dispatch: expected {_HID_REPORT_LEN}-byte payload; got "
                f"{len(payload)}"
            )
        cmd = payload[0]

        # Bootloader mode only services 0x40 (stream) and 0x41 (verify).
        # Any other cmd in bootloader mode is left unanswered -- mirrors
        # the silent NAK behaviour of the real bootloader (which doesn't
        # even know the app's cmd codes).
        if self._device.mode == "bootloader":
            if cmd == 0x40:
                return self._handle_bootloader_stream(payload)
            if cmd == 0x41:
                return self._handle_bootloader_verify(payload)
            return self._echo_with_status(cmd, status=0xFE)

        # App mode dispatch.
        if cmd == 0x06:
            return self._handle_cmd06_version(payload)
        if cmd == 0x03:
            return self._handle_cmd03_filename(payload)
        if cmd == 0x40:
            return self._handle_app_to_bootloader_switch(payload)
        if cmd == _CMD_DIAG_MEMREAD:
            return self._handle_cmd43_memread(payload)
        # Unknown cmd in app mode: echo + NAK so the flasher's parser
        # surfaces a clear error rather than silently hanging.
        return self._echo_with_status(cmd, status=0xFE)

    def _echo_with_status(self, cmd: int, *, status: int) -> bytes:
        resp = bytearray(_HID_REPORT_LEN)
        resp[0] = cmd & 0xFF
        resp[1] = status & 0xFF
        return bytes(resp)

    # ---- cmd 0x06 (version probe) -------------------------------------

    def _handle_cmd06_version(self, payload: bytes) -> bytes:
        """Return a cmd 0x06 response in the shape ``parse_cmd06_version_
        response`` accepts: ``[0x06, flag, major, minor, ...]``.

        The flag/major/minor are static literals embedded in the V3.2
        firmware's HID dispatch.  We extract them by scanning the
        flash for the ``detect_static_hex_hid_version`` pattern -- same
        signature the flasher itself uses to compute ``target_hex_version``
        from the parsed hex.

        ``payload[1]`` is the subcmd byte; only ``0x01`` (version) is
        recognised.  Other subcmds return a NAK echo.
        """
        if payload[1] != _CMD06_VERSION_SUBCMD:
            return self._echo_with_status(0x06, status=0xFE)
        version = self._scan_hid_version_literals()
        resp = bytearray(_HID_REPORT_LEN)
        resp[0] = 0x06
        if version is None:
            # Couldn't find the pattern -- NAK so the flasher's caller
            # surfaces a clear error.
            resp[1] = 0xFF
            return bytes(resp)
        resp[1] = version[0] & 0xFF  # flag
        resp[2] = version[1] & 0xFF  # major
        resp[3] = version[2] & 0xFF  # minor
        return bytes(resp)

    def _scan_hid_version_literals(self) -> Optional[tuple[int, int, int]]:
        """Scan MAIN flash for the cmd 0x06 version literals.  Mirror of
        ``dlcp_main_flash.detect_static_hex_hid_version`` operating on the
        live chain's flash."""
        core_idx = 1 + self._device.unit  # 1=MAIN0, 2=MAIN1
        # The version-pattern check spans 14 bytes; bound the scan to the
        # app window (0x1000..0x5FFF) so we don't probe boot block + preset
        # tables.  Mirror the flasher's range exactly.
        scan_start = _BOOTLOADER_APP_START
        scan_end = 0x5600  # PRESET_A_FLASH_BASE
        flash = self._hub._chain.read_core_flash(
            core_idx, scan_start, scan_end - scan_start
        )
        for off in range(0, len(flash) - 14, 2):
            if (
                flash[off + 1] == 0x0E
                and flash[off + 2] == 0x01
                and flash[off + 3] == 0x01
                and flash[off + 4] == 0x5B
                and flash[off + 5] == 0x6F
                and flash[off + 7] == 0x0E
                and flash[off + 8] == 0x5C
                and flash[off + 9] == 0x6F
                and flash[off + 11] == 0x0E
                and flash[off + 12] == 0x5D
                and flash[off + 13] == 0x6F
            ):
                return (flash[off], flash[off + 6], flash[off + 10])
        return None

    # ---- cmd 0x03 (filename WRITE / ERASE / READ) --------------------

    def _handle_cmd03_filename(self, payload: bytes) -> bytes:
        """Mirror the V3.2 firmware-side cmd 0x03 filename handler effect
        directly via chain pokes (no firmware-side dispatch).

        Subcmd semantics (cross-checked against
        ``src/dlcp_fw/asm/dlcp_main_v32.asm`` cmd 0x03 handlers + tests):

          * 0x08 READ: respond with the current 0x2C0..0x2DD slot.
          * 0x09 WRITE: payload[2..0x20] -> RAM 0x2C0..0x2DD; set
            filename_dirty_flags bits 5+6 (dirty + USB xact pending).
          * 0x0A ERASE: 0xFF -> RAM 0x2C0..0x2DD; set bits 5+6.
        """
        subcmd = payload[1]
        chain = self._hub._chain
        unit = self._device.unit

        if subcmd == _CMD03_FILENAME_WRITE_SUBCMD:
            # WRITE bytes 2..2+0x1E into RAM 0x2C0..0x2DD.  Critical:
            # the V3.2 firmware-side WRITE handler (asm lines 355-374,
            # main_core_service_15b0/15be) MAPS payload byte 0x00 to RAM
            # 0xFF -- it's how the host signals "end of filename
            # padding" without needing a length field.  The flasher's
            # ``_name_slot_to_cmd03_payload`` mirrors this by converting
            # both 0x00 AND 0xFF in the source name slot to 0x00 in the
            # payload, expecting the firmware to convert back to 0xFF
            # in RAM.  We must match that conversion here, or sim RAM
            # ends up with 0x00 padding while real hardware would have
            # 0xFF -- post-flash EEPROM persists then carry 0x00 bytes
            # and break ``_verify_capture_overlay`` parity (codex MEDIUM
            # vs 7d16ff9).
            for i in range(_FILENAME_RAM_LEN):
                src = payload[2 + i] & 0xFF
                dst = 0xFF if src == 0x00 else src
                chain.write_main_reg(
                    unit,
                    _FILENAME_RAM_BASE + i,
                    dst,
                )
            self._set_filename_dirty_bits(unit)
        elif subcmd == _CMD03_FILENAME_ERASE_SUBCMD:
            for i in range(_FILENAME_RAM_LEN):
                chain.write_main_reg(unit, _FILENAME_RAM_BASE + i, 0xFF)
            self._set_filename_dirty_bits(unit)
        elif subcmd != _CMD03_FILENAME_READ_SUBCMD:
            return self._echo_with_status(0x03, status=0xFE)

        # All three subcmds respond with a READ snapshot of the slot.
        resp = bytearray(_HID_REPORT_LEN)
        resp[0] = 0x03
        resp[1] = subcmd & 0xFF
        for i in range(_FILENAME_RAM_LEN):
            resp[2 + i] = (
                chain.read_main_reg(unit, _FILENAME_RAM_BASE + i) & 0xFF
            )
        return bytes(resp)

    def _set_filename_dirty_bits(self, unit: int) -> None:
        """Set filename_dirty_flags bits 5 (dirty) + 6 (USB xact pending).

        Matches the firmware's cmd 0x03 WRITE/ERASE handler (see V3.2 asm
        line ~393, ``bsf ram_0x0BD, 5/6, BANKED``).  Bit 6 is the gate
        added in ``test_v32_usb_filename_xact_gate.py`` work; clearing
        it requires firmware-side service via the
        ``main_core_service_265c`` join after persist completes."""
        chain = self._hub._chain
        current = chain.read_main_reg(unit, _FILENAME_DIRTY_FLAGS_ADDR) & 0xFF
        chain.write_main_reg(
            unit,
            _FILENAME_DIRTY_FLAGS_ADDR,
            current | _FILENAME_DIRTY_BIT | _USB_XACT_PENDING_BIT,
        )

    # ---- cmd 0x40 (app->bootloader) + cmd 0x40 stream + cmd 0x41 verify

    def _handle_app_to_bootloader_switch(self, payload: bytes) -> bytes:
        """Switch the simulated device to bootloader mode.

        The real DLCP MAIN's app cmd 0x40 writes ``EEPROM[0xFF] = 0`` and
        resets into bootloader mode.  In the sim we don't simulate the
        bootloader firmware, so we just flip the device's mode flag --
        the next ``enumerate_devices`` call will see the bootloader-mode
        product string and the flasher's ``_wait_for_bootloader`` will
        accept it.

        Returns no response (the real device replies later via the
        bootloader stream's first packet).  Returning ``None`` skips
        adding to the read queue; the host's read after this write
        returns empty and the host moves on to the reconnect wait.
        """
        self._device.mode = "bootloader"
        self._device.bootloader_stream = bytearray()
        return None

    def _handle_bootloader_stream(self, payload: bytes) -> bytes:
        """Bootloader stream packet.  Captures bytes 2..32 (30 bytes of
        app firmware payload).  Returns an ACK with the cmd echo.

        The real bootloader writes the bytes into program flash starting
        at the next cursor position and ACKs.  In the sim we capture the
        bytes into ``device.bootloader_stream`` so cmd 0x41 verify can
        compute their CRC against the host's expectation.

        Critical constraint (codex MEDIUM vs 7d16ff9): we do NOT patch
        the running firmware's flash with the streamed bytes -- patching
        flash mid-execution would corrupt the running V3.2 image's
        state (the firmware executes from 0x1000..0x5FFF, the same
        window the cmd 0x40 stream targets).  Instead the integration
        test fixture MUST construct ``Chain.from_v171_v32`` with a
        pre-overlaid hex (preset A/B captures already applied via
        ``_apply_capture_overlay`` into a temp hex file before chain
        construction) so the post-flash finalize's ``_verify_capture_
        overlay`` reads the correct preset bytes from
        ``chain.read_core_flash``.  See
        ``tests/sim/test_v32_release_flash_sim.py`` for the canonical
        pre-overlay pattern."""
        chunk = bytes(payload[2 : 2 + _BOOTLOADER_PACKET_PAYLOAD_LEN])
        self._device.bootloader_stream.extend(chunk)
        # Real bootloader's ACK: response[0] = 0x40 (cmd echo) is enough
        # for the flasher's ``_looks_like_main_boot_ack`` check.
        resp = bytearray(_HID_REPORT_LEN)
        resp[0] = 0x40
        return bytes(resp)

    def _handle_bootloader_verify(self, payload: bytes) -> bytes:
        """Bootloader CRC verify.  Compares ``payload[4]:payload[5]``
        (hi:lo) against the CRC of the captured stream.  Responds with
        ``0xAA`` at resp[2] on success, anything else on failure.

        On success, also flips the device back to app mode -- mirrors
        the real bootloader's "verify -> jump to app" flow."""
        expected_hi = payload[4]
        expected_lo = payload[5]
        # Strip trailing pad bytes that the flasher inserts to round the
        # last packet up to 30 bytes (``chunk + bytes([0xFF]) *
        # (30 - len(chunk))``).  The real bootloader CRCs the FULL stream
        # window (0x1000..0x5FFF inclusive), so the sim must too.
        stream = bytes(self._device.bootloader_stream)
        # Truncate to expected app-window length (0x5000 bytes); the
        # flasher always streams exactly that many.
        expected_len = _BOOTLOADER_APP_END_EXCL - _BOOTLOADER_APP_START
        if len(stream) > expected_len:
            stream = stream[:expected_len]
        elif len(stream) < expected_len:
            stream = stream + bytes(
                [0xFF] * (expected_len - len(stream))
            )
        actual_crc = _crc_pic18_stream(stream)
        actual_hi = (actual_crc >> 8) & 0xFF
        actual_lo = actual_crc & 0xFF

        resp = bytearray(_HID_REPORT_LEN)
        resp[0] = 0x41
        if actual_hi == expected_hi and actual_lo == expected_lo:
            resp[2] = 0xAA  # success token
            # On verify-OK, real bootloader jumps back to app.  In the sim
            # we just flip the mode flag; ``_wait_for_app`` will then see
            # the device back in app mode.
            self._device.mode = "app"
            self._device.bootloader_stream = bytearray()
        else:
            resp[2] = 0x55  # arbitrary non-AA = failure
        return bytes(resp)

    # ---- cmd 0x43 (DIAG_MEMREAD) ---------------------------------------

    def _handle_cmd43_memread(self, payload: bytes) -> bytes:
        """Mirror the V3.2 firmware-side cmd 0x43 (DIAG_MEMREAD) handler.

        Cross-checked against ``crates/dlcp-sim/src/peripherals/usb.rs::
        handle_memread`` (the rust shortcut for the firmware path) and
        the live V3.2 firmware's ``hid_cmd_diag_memread`` handler.

        Request layout: ``[0x43, region, addr_lo, addr_hi, length, ...]``
        Response layout: ``[0x43, status, length, data...]``
          * status=0x00 ok
          * status=0x01 bad-region
          * status=0x02 bad-length / out-of-range
        """
        region = payload[1]
        addr = payload[2] | (payload[3] << 8)
        length = payload[4]

        resp = bytearray(_HID_REPORT_LEN)
        resp[0] = _CMD_DIAG_MEMREAD

        if length == 0 or length > _DIAG_MEMREAD_MAX_LEN:
            resp[1] = 0x02  # bad-length
            return bytes(resp)
        resp[2] = length & 0xFF

        chain = self._hub._chain
        unit = self._device.unit

        if region == _DIAG_MEMREAD_REGION_FLASH:
            core_idx = 1 + unit
            try:
                data = chain.read_core_flash(core_idx, addr, length)
            except (ValueError, OSError) as exc:
                resp[1] = 0x02
                return bytes(resp)
            if len(data) != length:
                resp[1] = 0x02
                return bytes(resp)
            for i in range(length):
                resp[3 + i] = data[i] & 0xFF
            resp[1] = 0x00
            return bytes(resp)

        if region == _DIAG_MEMREAD_REGION_EEPROM:
            if addr + length > 0x100:
                resp[1] = 0x02  # EEPROM is 256 bytes
                return bytes(resp)
            for i in range(length):
                resp[3 + i] = chain.read_main_eeprom_byte(unit, addr + i) & 0xFF
            resp[1] = 0x00
            return bytes(resp)

        resp[1] = 0x01  # bad-region
        return bytes(resp)


class SimUsbHub:
    """Aggregates one ``SimHidBackend`` per simulated MAIN.

    Used as the install target for the flasher's transport hooks.  The
    test fixture builds a ``SimUsbHub`` against a rust chain, calls
    ``install_sim_hub(hub)`` to redirect the flasher's enumerate /
    open_hid / DlcpEp0 / HidMemoryReader call sites at this hub, runs
    the flasher unmodified, and verifies post-flash state via direct
    chain reads.

    Two-MAIN convention: ``unit=0`` is MAIN0 (PB1, ``--left``);
    ``unit=1`` is MAIN1 (PB2, ``--right``).
    """

    DEFAULT_VID = 0x04D8
    DEFAULT_PID = 0xFF89

    # Default ticks-per-EP0-op for ``make_dlcp_ep0`` (see HIGH from codex
    # review of 7d16ff9).  The unmodified flasher uses ``time.sleep`` between
    # EP0 polls, expecting the firmware to be running concurrently on real
    # hardware.  In the sim, ``time.sleep`` is wall-clock only and the
    # firmware is paused until ``chain.step_ticks`` is called.  Stepping
    # ~100k ticks (~ 2 ms sim time at 48 MHz universal clock) per EP0 op
    # gives the firmware enough run time to service event_flags writes
    # (force-persist trigger, route apply, etc.) within the flasher's
    # 1.5 s default timeout.
    #
    # Tests that need atomic EP0 ops (poke immediately followed by read,
    # no firmware-side reaction in between) construct ``SimDlcpEp0``
    # directly with ``step_ticks_per_op=0`` -- the existing
    # ``test_v32_flasher_sim_backend_ep0.py`` pattern.
    # 2 M ticks (~ 42 ms sim time @ 48 MHz) per EP0 op gives the
    # unmodified flasher's polling loops (40 polls over a 2 s timeout,
    # 0.05 s wall-clock spacing) ~ 1.68 s of cumulative sim time.  That
    # is enough to catch at least one V1.71 CONTROL chain frame
    # broadcast (~1 s spacing at idle, ~6 s for full_sync_burst step 6),
    # which is the only path that fires ``cmd_dispatch_gated`` and
    # clears ``active_flags.7`` after the host's reapply request.
    # Smaller values (100 k) starve the firmware -- the polling loop
    # times out before a chain frame can fire.
    DEFAULT_STEP_TICKS_PER_EP0_OP = 2_000_000

    # Default step-ticks-per-HID-op (1 M ticks ~= 21 ms sim time @ 48 MHz).
    # Larger than the EP0 default because a typical flasher session does
    # ~70 cmd 0x43 reads in a row during ``_verify_capture_overlay`` --
    # they'd accumulate ~1.5 s of sim time, which gives chain frames
    # (V1.71 CONTROL's ~6 s full_sync_burst step 6) and asynchronous
    # firmware paths (preset_job_service, active_flags.7 reapply
    # cleared by cmd_dispatch_gated) plenty of opportunity to converge
    # before the next EP0 polling phase fires.
    DEFAULT_STEP_TICKS_PER_HID_OP = 1_000_000

    def __init__(
        self,
        chain,  # type: ignore[no-untyped-def]
        *,
        units: Iterable[int] = (0, 1),
        vid: int = DEFAULT_VID,
        pid: int = DEFAULT_PID,
        default_step_ticks_per_ep0_op: int = DEFAULT_STEP_TICKS_PER_EP0_OP,
        default_step_ticks_per_hid_op: int = DEFAULT_STEP_TICKS_PER_HID_OP,
    ) -> None:
        self._chain = chain
        self._vid = vid
        self._pid = pid
        self._default_step_ticks_per_ep0_op = max(
            0, int(default_step_ticks_per_ep0_op)
        )
        self._default_step_ticks_per_hid_op = max(
            0, int(default_step_ticks_per_hid_op)
        )
        self._devices: dict[bytes, SimUsbDevice] = {}
        for unit in units:
            if unit not in (0, 1):
                raise ValueError(f"unit must be 0 or 1; got {unit}")
            path = f"sim:main{unit}".encode("utf-8")
            self._devices[path] = SimUsbDevice(
                unit=unit,
                path=path,
                serial_number=f"SIM-MAIN{unit}",
            )

    def device_for_unit(self, unit: int) -> SimUsbDevice:
        for dev in self._devices.values():
            if dev.unit == unit:
                return dev
        raise KeyError(f"no sim device for unit {unit}")

    def device_for_path(self, path: bytes) -> SimUsbDevice:
        return self._devices[path]

    @property
    def chain(self):  # type: ignore[no-untyped-def]
        return self._chain

    @property
    def default_step_ticks_per_hid_op(self) -> int:
        return self._default_step_ticks_per_hid_op

    # ---- Hooks consumed by the flasher modules ------------------------

    def enumerate_devices(self, vid: int, pid: int):
        """Drop-in replacement for
        ``dlcp_control_flash.enumerate_devices``.

        Returns one ``HidDeviceInfo`` per simulated MAIN device whose
        (vid, pid) matches the caller's filter.  Uses the device's
        current mode-dependent product_string."""
        # Lazy import to avoid module-load cycles.
        from dlcp_fw.flash.dlcp_control_flash import HidDeviceInfo

        out = []
        for dev in self._devices.values():
            if vid is not None and vid != self._vid:
                continue
            if pid is not None and pid != self._pid:
                continue
            out.append(
                HidDeviceInfo(
                    vendor_id=self._vid,
                    product_id=self._pid,
                    path=dev.path,
                    manufacturer_string=dev.manufacturer_string,
                    product_string=dev.product_string,
                    serial_number=dev.serial_number,
                )
            )
        return out

    def open_hid_path(self, path: bytes):
        """Drop-in replacement for ``dlcp_main_flash._open_hid``.

        Returns a ``SimHidBackend`` bound to the device with the given
        path."""
        if path not in self._devices:
            raise RuntimeError(
                f"requested HID path was not found among simulated devices: "
                f"{path!r}"
            )
        return SimHidBackend(self, self._devices[path])

    def make_dlcp_ep0(
        self,
        *,
        vid: int,
        pid: int,
        path: Optional[bytes] = None,
        hid_info=None,  # type: ignore[no-untyped-def]
        step_ticks_per_op: Optional[int] = None,
    ) -> SimDlcpEp0:
        """Drop-in replacement for ``DlcpEp0(vid=, pid=, path=)``.

        Returns a ``SimDlcpEp0`` bound to the matching simulated MAIN.

        ``step_ticks_per_op`` defaults to the hub's
        ``default_step_ticks_per_ep0_op`` so polling loops in the
        unmodified flasher (e.g. ``_force_active_filename_persist``,
        ``_switch_active_preset_ep0``) can observe firmware-side state
        changes.  Pass ``0`` explicitly to opt out of stepping (atomic
        ops, used by unit tests that step the chain manually)."""
        target_path: Optional[bytes] = path
        if target_path is None and hid_info is not None:
            target_path = getattr(hid_info, "path", None)
        if target_path is None:
            # No explicit path; if the hub has exactly one device, target
            # that.  Otherwise raise -- mirrors the real DlcpEp0's
            # multiple-device error.
            unique = list(self._devices.values())
            if len(unique) != 1:
                raise RuntimeError(
                    f"multiple HID devices match {vid:04X}:{pid:04X}; "
                    f"use --list and pass --path"
                )
            target_dev = unique[0]
        else:
            target_dev = self._devices[target_path]
        effective_step = (
            self._default_step_ticks_per_ep0_op
            if step_ticks_per_op is None
            else int(step_ticks_per_op)
        )
        return SimDlcpEp0(
            self._chain,
            unit=target_dev.unit,
            step_ticks_per_op=effective_step,
        )


# ============================================================================
# install_sim_hub: context manager that redirects the flasher's transport
# hooks at the sim hub.
# ============================================================================
#
# Each flasher module exposes a single override hook (a callable or class).
# The context manager swaps them at entry and restores at exit -- the same
# pattern pytest's monkeypatch fixture uses, but kept self-contained so the
# install/uninstall is explicit in the test fixture.
# ============================================================================


@contextlib.contextmanager
def install_sim_hub(hub: SimUsbHub):
    """Redirect the flasher's transport entry points at ``hub``.

    Modules patched:

      * ``dlcp_fw.flash.dlcp_control_flash._ENUMERATE_DEVICES_OVERRIDE``
      * ``dlcp_fw.flash.dlcp_main_flash._OPEN_HID_OVERRIDE``
      * ``dlcp_fw.flash.dlcp_main_flash._DLCP_EP0_FACTORY_OVERRIDE``
      * ``dlcp_fw.flash.read_coeffs._OPEN_HID_OVERRIDE``

    Restores all four on exit (even if the body raises).

    Usage::

        with install_sim_hub(hub):
            from dlcp_fw.flash.dlcp_v32_release_flash import main
            assert main(["--right", "--all-ch", "R", ...]) == 0
    """
    from dlcp_fw.flash import (  # noqa: WPS433 -- intentional inline import
        dlcp_control_flash,
        dlcp_main_flash,
        read_coeffs,
    )

    saved = {
        ("dlcp_control_flash", "_ENUMERATE_DEVICES_OVERRIDE"): getattr(
            dlcp_control_flash, "_ENUMERATE_DEVICES_OVERRIDE", None
        ),
        ("dlcp_main_flash", "_OPEN_HID_OVERRIDE"): getattr(
            dlcp_main_flash, "_OPEN_HID_OVERRIDE", None
        ),
        ("dlcp_main_flash", "_DLCP_EP0_FACTORY_OVERRIDE"): getattr(
            dlcp_main_flash, "_DLCP_EP0_FACTORY_OVERRIDE", None
        ),
        ("read_coeffs", "_OPEN_HID_OVERRIDE"): getattr(
            read_coeffs, "_OPEN_HID_OVERRIDE", None
        ),
    }
    dlcp_control_flash._ENUMERATE_DEVICES_OVERRIDE = hub.enumerate_devices
    dlcp_main_flash._OPEN_HID_OVERRIDE = hub.open_hid_path
    dlcp_main_flash._DLCP_EP0_FACTORY_OVERRIDE = (
        lambda *, vid, pid, path=None, hid_info=None: hub.make_dlcp_ep0(
            vid=vid, pid=pid, path=path, hid_info=hid_info,
        )
    )
    read_coeffs._OPEN_HID_OVERRIDE = hub.open_hid_path
    try:
        yield hub
    finally:
        dlcp_control_flash._ENUMERATE_DEVICES_OVERRIDE = saved[
            ("dlcp_control_flash", "_ENUMERATE_DEVICES_OVERRIDE")
        ]
        dlcp_main_flash._OPEN_HID_OVERRIDE = saved[
            ("dlcp_main_flash", "_OPEN_HID_OVERRIDE")
        ]
        dlcp_main_flash._DLCP_EP0_FACTORY_OVERRIDE = saved[
            ("dlcp_main_flash", "_DLCP_EP0_FACTORY_OVERRIDE")
        ]
        read_coeffs._OPEN_HID_OVERRIDE = saved[
            ("read_coeffs", "_OPEN_HID_OVERRIDE")
        ]


def make_sim_hub(
    chain,  # type: ignore[no-untyped-def]
    *,
    units: Iterable[int] = (0, 1),
    vid: int = SimUsbHub.DEFAULT_VID,
    pid: int = SimUsbHub.DEFAULT_PID,
    default_step_ticks_per_ep0_op: int = SimUsbHub.DEFAULT_STEP_TICKS_PER_EP0_OP,
    default_step_ticks_per_hid_op: int = SimUsbHub.DEFAULT_STEP_TICKS_PER_HID_OP,
) -> SimUsbHub:
    """Convenience factory mirroring ``make_sim_ep0``."""
    return SimUsbHub(
        chain,
        units=units,
        vid=vid,
        pid=pid,
        default_step_ticks_per_ep0_op=default_step_ticks_per_ep0_op,
        default_step_ticks_per_hid_op=default_step_ticks_per_hid_op,
    )
