"""Python facade for the Rust ``dlcp-sim`` engine.

This module is the Python-side mirror of
``crates/dlcp-sim-py/src/lib.rs`` (the PyO3 wrapper).  It
imports the native extension (``dlcp_sim_native.so`` produced
by ``crates/dlcp-sim-py/build.sh``) and re-exports the
Python-friendly surface that test harnesses use to drive
the Rust simulator.

P4.2 lands the **minimum viable Chain API** -- enough to
satisfy the spec's verify command::

    python -c "from dlcp_fw.sim.dlcp_sim_native import Chain; \\
               c = Chain.from_v171_v32(); \\
               c.step_ticks(48_000_000); \\
               print(c.lcd_lines())"

Subsequent migration sub-tasks (P4.3..P4.7) will grow the
API surface with whatever ``chain_gpsim.py`` /
``wire_chain_gpsim.py`` methods the migrated tests actually
need.  Don't bind anything pre-emptively: per spec
non-goals, "not preserving gpsim's CLI / .stc scripts /
PTY interface" -- only the methods the tests use.

Module-import contract:
  * ``import dlcp_sim_native`` (the native PyO3 .so) must
    be resolvable from Python's import path.  In this repo
    the standard incantation is
    ``PYTHONPATH=src .venv_ep0/bin/python ...`` and
    ``crates/dlcp-sim-py/build.sh`` symlinks the cdylib
    into ``src/dlcp_sim_native.so`` so the same
    ``PYTHONPATH=src`` path resolves both this facade
    AND the underlying native module.
  * If you see ``ModuleNotFoundError: No module named
    'dlcp_sim_native'``, run::

        cargo build --release -p dlcp-sim-py
        bash crates/dlcp-sim-py/build.sh

    from the project root and try again.
"""

from __future__ import annotations

# The native extension is built by `cargo build --release
# -p dlcp-sim-py` and symlinked into `src/` by `build.sh`.
# We keep the native module behind a private alias so the
# public API of this facade stays pure-Python and we can
# layer additional Python-side ergonomics (validation,
# parity adapters, etc.) on top of the raw bindings as
# the migration sub-tasks require it.
#
# Bootstrap (P4.8 prep): the .so symlink lives at
# `<repo>/src/dlcp_sim_native.so` (and at
# `<repo>/crates/dlcp-sim-py/dlcp_sim_native.so`) per
# `crates/dlcp-sim-py/build.sh`.  Test invocations that don't
# pre-set `PYTHONPATH=src` (e.g. `pytest tests/sim` from the
# repo root, post-P4.8 default-rust flip) would otherwise fail
# at the import below with `ModuleNotFoundError`.  Add the two
# candidate locations to `sys.path` if they exist; this is a
# no-op when `PYTHONPATH=src` already covered it because Python
# de-dupes path entries on import resolution.
import sys as _sys
from pathlib import Path as _Path

_THIS_FILE = _Path(__file__).resolve()
# src/dlcp_fw/sim/dlcp_sim_native.py -> repo root is parents[3]
_REPO_ROOT = _THIS_FILE.parents[3]
for _candidate in (
    _REPO_ROOT / "src",
    _REPO_ROOT / "crates" / "dlcp-sim-py",
):
    _candidate_str = str(_candidate)
    if _candidate.exists() and _candidate_str not in _sys.path:
        _sys.path.insert(0, _candidate_str)

import dlcp_sim_native as _native

#: Workspace version of the underlying Rust ``dlcp-sim`` /
#: ``dlcp-sim-py`` crates.  Sourced from the native
#: module's ``CARGO_PKG_VERSION``; useful for runtime
#: gating during the migration window
#: (e.g. tests that need a specific bindings version).
__version__: str = _native.__version__


class Chain:
    """Python-friendly facade over the Rust ``Chain``.

    A `Chain` is the top-level simulation object: it owns
    one or more PIC18 cores (CONTROL + MAIN0 + MAIN1 in
    the canonical DLCP topology), the inter-core UART/I²C
    couplings, and slave peripherals like the HD44780 LCD
    and TAS3108 DSP.

    P4.2 minimum API:
      * :meth:`from_v171_v32` -- factory: build the canonical
        3-core ring (V1.71 CONTROL + 2× V3.2 MAIN) with
        UART ring, DSP slaves, LCD slave, POR-reset and
        initial-step schedule applied.
      * :meth:`step_ticks` -- advance the universal-clock
        scheduler by N ticks (48 MHz time base).
      * :meth:`current_tick` -- current scheduler tick.
      * :meth:`lcd_lines` -- ``(line1, line2)`` snapshot of
        the HD44780 DDRAM rows.
      * Index getters: :attr:`ctl`, :attr:`main0`,
        :attr:`main1` -- core indices the chain assigned;
        used by future P4.x methods like ``read_ram``,
        ``set_pin_*``.

    Construction:
        Don't instantiate ``Chain()`` directly.  Use
        :meth:`from_v171_v32` (or future factory methods
        for other firmware combos).  Direct construction
        would require building / wiring cores manually
        from Python, which is the API surface we're
        trying to keep minimal during the migration
        window.
    """

    __slots__ = ("_inner",)

    def __init__(self, _inner: "_native.Chain") -> None:
        # Private constructor -- factory methods only.
        # The leading underscore on the parameter is the
        # convention this codebase uses to mark "not for
        # direct external callers".  Tests that need a
        # bare Chain for low-level wiring should add a
        # method to this facade instead of bypassing
        # :meth:`from_v171_v32`.
        self._inner = _inner

    @classmethod
    def from_v171_v32(cls) -> "Chain":
        """Build the canonical V1.71 CONTROL + 2× V3.2 MAIN ring.

        Mirrors the prelude of
        ``crates/dlcp-sim/tests/multicore_parity.rs::three_core_ring_v171_v32_v32_*``
        scenarios:

        - Load V1.71 CONTROL hex
          (``firmware/patched/releases/DLCP_Control_V1.71.hex``).
        - Load V3.2 MAIN hex (canonical app-only release at
          ``firmware/patched/releases/DLCP_Firmware_V3.2.hex``)
          + V2.3-combined seed
          (``firmware/stock/main/DLCP Firmware V2.3-combined.hex``)
          and merge to get a silicon-correct MAIN flash
          (V3.2 app on V2.3 boot block / preset table /
          EEPROM seed; per task #36 / P3.6 background).
        - Build CONTROL core (K20) from V1.71.
        - Build 2× MAIN cores (2455) each with the merged
          flash + V2.3 EEPROM seed + AN0=0x0300 (steady-
          state standby-gate sample).
        - Wire UART ring CONTROL.TX → MAIN0.RX,
          MAIN0.TX → MAIN1.RX, MAIN1.TX → CONTROL.RX.
        - Couple a TAS3108 DSP slave to each MAIN over I²C.
        - Couple an HD44780 LCD slave to CONTROL.
        - Apply POR reset to all cores; schedule initial
          steps (cores wake at universal-tick 0).

        After return the chain is ready for :meth:`step_ticks`.
        """
        return cls(_native.Chain.from_v171_v32())

    @classmethod
    def from_v16b_v23(cls) -> "Chain":
        """Convenience: stock V1.6b CONTROL + stock V2.3 MAIN single-MAIN chain.

        Mirror of the gpsim baseline
        ``tests/sim/test_v17_chain.py::test_v17_stock_v16b_chain_reaches_display``.
        Uses the canonical stock V1.6b CONTROL hex
        (``firmware/stock/control/DLCP Control Firmware V1.6b.hex``)
        and the V2.3-combined silicon image (full boot block
        + V2.3 app + EEPROM + preset tables).
        """
        return cls(_native.Chain.from_v16b_v23())

    @classmethod
    def from_v171_v31(cls) -> "Chain":
        """Convenience: V1.71 CONTROL + V3.1 MAIN single-
        MAIN chain.  Mirror of
        ``tests/sim/test_v171_v31_chain.py::_new_pair``.
        Uses the canonical V3.1 release hex (app-only)
        merged onto V2.3-combined (silicon-correct boot
        block + EEPROM).
        """
        return cls(_native.Chain.from_v171_v31())

    @classmethod
    def from_v3x_main_only(
        cls,
        v3x_main_hex_path: str,
        v23_seed_hex_path: str | None = None,
    ) -> "Chain":
        """MAIN-only single-core factory.

        Mirror of gpsim's
        ``MainChainHarness(main_hex, transport_mode="native_ring")``.
        Builds a single 2455 core with V3.x app + V2.3-combined
        seed merge, TAS3108 DSP slave on MSSP I²C, AN0 ADC =
        0x0300, no CONTROL.  All Chain methods (read_reg,
        write_reg, step, ...) target the MAIN core because
        internally ``i_ctl == i_main`` for MAIN-only chains.
        Use :meth:`inject_main_frames_fifo` to inject synthetic
        chain frames into MAIN's RX ring (V3.x native_ring
        layout: rd at 0x0C6, wr at 0x0C7, ring at 0x0200).
        """
        return cls(_native.Chain.from_v3x_main_only(
            v3x_main_hex_path, v23_seed_hex_path,
        ))

    @classmethod
    def from_v31_main_only(cls) -> "Chain":
        """Convenience: V3.1 MAIN-only chain."""
        return cls(_native.Chain.from_v31_main_only())

    @classmethod
    def from_v32_main_only(cls) -> "Chain":
        """Convenience: V3.2 MAIN-only chain."""
        return cls(_native.Chain.from_v32_main_only())

    @classmethod
    def from_v17_v3x_chain(
        cls,
        control_hex_path: str,
        v3x_main_hex_path: str,
        v23_seed_hex_path: str | None = None,
    ) -> "Chain":
        """Generic V1.7-family CONTROL + V3.x MAIN single-
        MAIN factory.

        Accepts any K20 CONTROL hex (V1.71, V1.7-shifted,
        etc.) paired with a V3.x app-only MAIN hex (V3.1,
        V3.2 release, V3.x diagnostic build).  The V3.x app
        is merged onto a V2.3-combined seed
        (defaults to ``firmware/stock/main/DLCP Firmware
        V2.3-combined.hex`` when ``v23_seed_hex_path`` is
        ``None``) for silicon-correct boot.
        """
        return cls(_native.Chain.from_v17_v3x_chain(
            control_hex_path, v3x_main_hex_path, v23_seed_hex_path,
        ))

    @classmethod
    def from_v17_chain(
        cls,
        control_hex_path: str,
        main_hex_path: str | None = None,
    ) -> "Chain":
        """Generic V1.7-family single-MAIN factory.

        Accepts any K20 CONTROL hex (V1.6b stock, V1.7
        byte-identical rebuild, V1.7 shifted +0x222, V1.71)
        paired with a FULL-SILICON 2455 MAIN hex (defaults
        to V2.3-combined when ``main_hex_path`` is ``None``).
        Used by the dual-mode migration of
        ``tests/sim/test_v17_chain.py`` to drive the rust
        engine with the same hex files the gpsim
        ``v17_chain_images`` fixture builds.

        ``main_hex_path`` must be a complete silicon image
        (boot block + app + EEPROM); the builder does NOT
        merge an app-only V3.x release onto a V2.3 seed.
        Passing a V3.x app-only hex won't fault outright --
        the executor walks the erased ``[0x0000, 0x1000)``
        bootloader window as NOPs (``0xFFFF`` decodes as
        NopContinuation) and re-enters app code from the
        wrong path (skipping the V3.x user-IRQ handler at
        0x1008).  See the rust pyclass docstring for the
        full rationale and task #30 for the original V3.x
        chain-probe finding.  For V3.x main use a 3-core
        factory like :meth:`from_v171_v32`.
        """
        return cls(_native.Chain.from_v17_chain(control_hex_path, main_hex_path))

    @classmethod
    def from_v17_control_only(cls, control_hex_path: str) -> "Chain":
        """CONTROL-only single-K20 chain (no MAIN, no UART couplings).

        Mirror of gpsim's ``GpsimControlHarness(hex,
        fast_boot=False)`` invocation without a synthetic-
        heartbeat pump.  Boots a single K20 core with an
        HD44780 LCD slave on the LCD-control pins.  Used by
        V1.7 / V1.71 relocation-safety tests that compare
        stock V1.6b vs rebuilt V1.7 vs shifted V1.7 in
        CONTROL-only mode (no MAIN heartbeats) and assert
        that all three advance identical Tcy and emit
        identical UART TX byte sequences.

        :attr:`current_cycle` and :meth:`tx_frames` work
        without changes -- TX bytes are captured via the
        ``Chain::drain_completed_tx_bytes`` loopback-sentinel
        branch (the same mechanism that makes MAIN-only
        chains observable when no UART coupling exists).

        Methods that require a MAIN core
        (:meth:`inject_main_frames_fifo`, :meth:`read_dsp_reg`,
        :meth:`set_dsp_i2c_fault`, etc.) are NOT meaningful
        in this topology -- callers must avoid them.
        """
        return cls(_native.Chain.from_v17_control_only(control_hex_path))

    def step_ticks(self, n_ticks: int) -> None:
        """Advance the chain's universal scheduler by ``n_ticks``.

        ``n_ticks`` is in 48 MHz universal ticks: e.g.
        ``48_000_000`` advances 1 simulated second; the
        K20 runs at 16 ticks/Tcy so 1 sim sec ≈ 3 M K20
        instructions.
        """
        self._inner.step_ticks(int(n_ticks))

    def current_tick(self) -> int:
        """Current universal-clock tick (48 MHz time base)."""
        return self._inner.current_tick()

    @property
    def ctl(self) -> int:
        """Index of the CONTROL core in the chain."""
        return self._inner.ctl

    @property
    def main0(self) -> int:
        """Index of MAIN0 in the chain.

        For single-MAIN topologies (``from_v16b_v23``,
        ``from_v17_chain``) this returns the same index as
        :attr:`main1`; the two getters collapse to the only
        MAIN core's index.  See the rust pyclass docstring
        for rationale.
        """
        return self._inner.main0

    @property
    def main1(self) -> int:
        """Index of MAIN1 in the chain.

        For single-MAIN topologies (``from_v16b_v23``,
        ``from_v17_chain``) this returns the same index as
        :attr:`main0` (the topology has no second MAIN to
        distinguish).  Callers that constructed the chain
        themselves should branch on the factory used; generic
        helpers handed an already-built ``Chain`` may inspect
        ``main0 == main1`` as the only object-local
        topology signal exposed today (a future
        ``main_count`` accessor could replace this idiom --
        track it as a P4.x backlog item if/when a generic
        helper hits the limitation).
        """
        return self._inner.main1

    def lcd_lines(self) -> tuple[str, str]:
        """``(line1, line2)`` snapshot of the HD44780 DDRAM.

        Returns the EMPTY-DDRAM default (16 spaces each)
        on a freshly-reset chain before CONTROL has
        rendered any text.  Trailing whitespace is
        preserved so callers can decide whether to trim;
        compare with ``rstrip()`` if you only care about
        the visible characters.
        """
        return tuple(self._inner.lcd_lines())  # type: ignore[return-value]

    def is_connected(self) -> bool:
        """True when CONTROL has marked itself as connected.

        Reads bit 1 of physical RAM 0x01F on the CONTROL
        core (the ``control_flags`` byte).  Mirror of
        ``chain_gpsim.py::SingleMainChainHarness.is_connected``.
        """
        return bool(self._inner.is_connected())

    def is_waiting(self) -> bool:
        """True when CONTROL's LCD shows the WAITING screen.

        Mirror of ``chain_gpsim.py::_is_waiting_lcd``: the
        substring ``"WAITING FOR DLCP"`` (case-insensitive)
        appears on either of the two LCD rows.
        """
        return bool(self._inner.is_waiting())

    def run_until_connected(self, limit: int) -> int:
        """Step in 200K-Tcy chunks (3.2M universal ticks each)
        up to ``limit`` chunks, returning early as soon as the
        chain has reached the steady-state CONNECTED Volume
        display.  Returns the number of chunks actually
        consumed (== ``limit`` if the predicate never fired).

        Predicate: ``is_connected() AND not is_waiting() AND
        "Volume:" in lcd_lines()[0]``.  This is STRICTER than
        ``chain_gpsim.py::SingleMainChainHarness.run_until_connected``,
        which uses just ``is_connected AND not is_waiting``.
        See the rust-side comment on
        ``Chain::run_until_connected`` for why the Rust facade
        adds the LCD check (briefly: the Rust chain advances
        cores within the same universal-tick scheduler rather
        than gpsim's alternating per-MAIN / per-CONTROL chunks,
        so ``control_flags.CONNECTED`` can transiently flip
        True before the LCD has rendered the Volume screen --
        the LCD check rejects those transients).
        """
        return int(self._inner.run_until_connected(int(limit)))

    def run_until_waiting(self, limit: int) -> int:
        """Step in 3.2 M-tick chunks up to ``limit`` chunks,
        returning early as soon as ``is_waiting()`` is True
        (LCD shows ``"WAITING FOR DLCP"`` on either row).
        Mirror of
        ``chain_gpsim.py::SingleMainChainHarness.run_until_waiting``.
        """
        return int(self._inner.run_until_waiting(int(limit)))

    def step_many(self, n_chunks: int) -> None:
        """Step ``n_chunks`` chunks of 3.2 M ticks each (no
        early-exit predicate).  Mirror of
        ``chain_gpsim.py::SingleMainChainHarness.step_many``.
        Used by the V1.7 blackout/wake test to give the
        firmware time to render the standby screen after
        a STBY press.
        """
        self._inner.step_many(int(n_chunks))

    def set_blackout(self, enabled: bool) -> None:
        """Toggle the chain's UART-blackout flag.  When
        enabled, every completed UART TX byte is dropped
        instead of delivered -- modelling a physical chain
        disconnect (CAT5 unplug, optocoupler fault).  Cores
        keep running and TX history is NOT updated for
        dropped bytes.  Mirror of
        ``chain_gpsim.py::SingleMainChainHarness.set_blackout``
        (modulo gpsim's `LinkPipe.clear` step -- the rust
        engine's destination-side RCREG residual is bounded
        by the firmware's read latency).
        """
        self._inner.set_blackout(bool(enabled))

    def press(self, key: str) -> None:
        """Inject a panel-button press on CONTROL.  Drives
        the button's active-low PORTx bit LOW, holds ~1 sec
        sim (50 M universal ticks, well past V1.71's 4-poll
        button debounce), releases HIGH, and settles
        another ~1 sec sim.  Mirror of
        ``chain_gpsim.py::SingleMainChainHarness.press``.

        Accepted keys (case-insensitive): SELECT, DOWN,
        STBY, RIGHT, UP, LEFT.  Raises ``ValueError`` for
        any other key.
        """
        self._inner.press(str(key))

    def read_reg(self, addr: int) -> int:
        """Read a single byte of CONTROL's data memory at
        the given physical address.  Mirror of
        ``control_gpsim.py::GpsimControlHarness.read_reg``.
        Common addresses: 0x01F (control_flags), 0x0BF
        (display_state_index), 0x0B8 (input_select_cache),
        0x0B9 (volume_cache).
        """
        return int(self._inner.read_reg(int(addr) & 0xFFF))

    def write_reg(self, addr: int, value: int) -> None:
        """Write a single byte of CONTROL's data memory at
        the given physical address.  Mirror of gpsim's
        ``_issue(f"reg(0xADDR)=0xVAL")`` register-poke
        command, used by V1.71 tests that drive specific
        firmware paths via direct RAM writes.
        """
        self._inner.write_reg(int(addr) & 0xFFF, int(value) & 0xFF)

    def read_main_reg(self, unit: int, addr: int) -> int:
        """Read a single byte of one MAIN's data memory at
        the given physical address.

        ``unit`` selects which MAIN core: ``0`` for MAIN0, ``1``
        for MAIN1.  Values 2..=255 raise ``ValueError``;
        negatives and values >255 raise ``OverflowError`` from
        the underlying PyO3 ``u8`` conversion.  On MAIN-only /
        single-MAIN chain topologies (where i_main0 == i_main1)
        both unit indices target the same core.

        Mirror of gpsim's per-MAIN register read in the
        wire-chain harnesses (used by V1.71+V3.2 layer-5
        diag-chain tests, V2.8 wire-chain delayed-switch
        repros, etc.).
        """
        return int(self._inner.read_main_reg(int(unit), int(addr) & 0xFFF))

    def write_main_reg(self, unit: int, addr: int, value: int) -> None:
        """Write a single byte of one MAIN's data memory at
        the given physical address.

        ``unit`` selects which MAIN core: ``0`` for MAIN0, ``1``
        for MAIN1.  Values 2..=255 raise ``ValueError``;
        negatives and values >255 raise ``OverflowError`` from
        the underlying PyO3 ``u8`` conversion.  Mirror of
        gpsim's per-MAIN register poke (used to seed diag
        counters, force standby state, etc.).
        """
        self._inner.write_main_reg(
            int(unit), int(addr) & 0xFFF, int(value) & 0xFF
        )

    @property
    def current_cycle(self) -> int:
        """CONTROL's K20-Tcy cycle counter (mirror of
        ``control_gpsim.py::GpsimControlHarness.current_cycle``).
        """
        return int(self._inner.current_cycle)

    def pause_heartbeat(self) -> None:
        """No-op on the rust backend.  Mirror of
        ``control_gpsim.py::GpsimControlHarness.pause_heartbeat``,
        which suppresses gpsim's synthetic heartbeat-RX
        pump.  The rust facade has no synthetic-heartbeat
        mode -- the chain runs against a real V2.3-combined
        MAIN that emits actual BF replies -- so there is
        nothing to pause.  Provided for duck-typing parity.
        """
        self._inner.pause_heartbeat()

    def inject_main_frames_fifo(
        self, frames: list[list[int]], fifo_limit: int
    ) -> tuple[int, int]:
        """Inject 3-byte chain frames into MAIN's RX ring.

        Mirror of gpsim's
        ``MainChainHarness.inject_frames_fifo`` for
        ``transport_mode="native_ring"``.  Targets the V3.x
        firmware's RX ring at physical 0x0200..0x02BF, with rd
        index at 0x0C6 and wr index at 0x0C7.  Frame-aligned
        overrun semantics: each 3-byte frame is either fully
        delivered or fully dropped.  Returns
        ``(delivered_bytes, overrun_bytes)``.

        ``frames`` is a list of 3-element byte sequences
        (route, cmd, data).  ``fifo_limit`` is capped at 191;
        gpsim tests typically pass ``fifo_limit=47``.
        """
        py_frames = [[int(b) & 0xFF for b in f] for f in frames]
        return tuple(self._inner.inject_main_frames_fifo(
            py_frames, int(fifo_limit),
        ))

    def write_control_eeprom_byte(self, addr: int, value: int) -> None:
        """Seed CONTROL's EEPROM peripheral at the given
        8-bit address.  Mirror of gpsim's
        ``GpsimControlHarness(eeprom_file=...)`` constructor
        argument that pre-loads CONTROL's EEPROM HEX before
        simulation starts.  Use this immediately after
        ``Chain.from_v17_chain(...)`` and BEFORE the first
        ``step()`` / ``warmup()`` call -- the firmware
        reads EEPROM during early boot.
        """
        self._inner.write_control_eeprom_byte(int(addr) & 0xFF, int(value) & 0xFF)

    def read_dsp_reg(self, subaddr: int) -> int:
        """Read a single TAS3108 DSP register at ``subaddr``.

        Mirror of gpsim's
        ``MainChainHarness.read_i2c_regfile("dsp34", subaddr)``.
        Returns the byte stored in the rust TAS3108 slave's
        in-memory register file (latched as MAIN's MSSP I²C
        burst writes the DSP).  The rust facade reads the
        first DSP slave coupled to MAIN0.
        """
        return int(self._inner.read_dsp_reg(int(subaddr) & 0xFF)) & 0xFF

    def set_i2c_fault(
        self,
        device_name: str,
        *,
        address_nack_count: int | None = None,
        address_stretch_scl_cycles: int | None = None,
        address_stretch_count: int | None = None,
        data_nack_count: int | None = None,
        data_stuck_sda_cycles: int | None = None,
        data_stuck_sda_count: int | None = None,
        hold_scl_low: bool | None = None,
        stretch_scl_cycles: int | None = None,
    ) -> None:
        """Program I²C fault-injection on the rust TAS3108
        slave coupled to MAIN0.  Mirror of gpsim's
        ``MainChainHarness.set_i2c_fault`` (chain_gpsim.py:471).

        Today only ``address_nack_count`` is implemented in the
        rust slave model.  The other knobs (address_stretch_*,
        data_nack_count, data_stuck_sda_*, stretch_scl_cycles,
        hold_scl_low) raise ``NotImplementedError`` so callers
        get a clear failure rather than a silent no-op.

        ``device_name`` is required for gpsim signature parity
        but not used by the rust path -- the rust chain has at
        most one DSP slave coupled to MAIN0, so the device name
        is implicit.  We still validate it equals ``"dsp34"``
        (the only DSP device gpsim's MainChainHarness exposes)
        to surface typos before they get tunnelled past the
        facade.
        """
        if device_name != "dsp34":
            raise ValueError(
                f"set_i2c_fault: rust facade only supports device "
                f"\"dsp34\" (got {device_name!r})"
            )
        unsupported: list[str] = []
        if address_stretch_scl_cycles is not None:
            unsupported.append("address_stretch_scl_cycles")
        if address_stretch_count is not None:
            unsupported.append("address_stretch_count")
        if data_nack_count is not None:
            unsupported.append("data_nack_count")
        if data_stuck_sda_cycles is not None:
            unsupported.append("data_stuck_sda_cycles")
        if data_stuck_sda_count is not None:
            unsupported.append("data_stuck_sda_count")
        if hold_scl_low is not None:
            unsupported.append("hold_scl_low")
        if stretch_scl_cycles is not None:
            unsupported.append("stretch_scl_cycles")
        if unsupported:
            raise NotImplementedError(
                f"rust TAS3108 slave does not yet model the "
                f"following I²C fault-injection knobs: "
                f"{', '.join(unsupported)}"
            )
        if address_nack_count is not None:
            self._inner.set_dsp_i2c_fault(max(0, int(address_nack_count)))

    def clear_i2c_faults(self, device_name: str = "dsp34") -> None:
        """Clear all I²C fault-injection counters on the rust
        TAS3108 slave coupled to MAIN0.  Mirror of gpsim's
        ``MainChainHarness.clear_i2c_faults`` (chain_gpsim.py:526).
        """
        if device_name != "dsp34":
            raise ValueError(
                f"clear_i2c_faults: rust facade only supports device "
                f"\"dsp34\" (got {device_name!r})"
            )
        self._inner.clear_dsp_i2c_faults()

    def set_mssp_stop_fault(
        self,
        *,
        stop_busy_cycles: int | None = None,
        stop_busy_count: int | None = None,
    ) -> None:
        """Program the MSSP STOP-fault knobs on MAIN0's MSSP.
        Mirror of gpsim's
        ``MainChainHarness.set_mssp_stop_fault`` (chain_gpsim.py:451).

        While ``stop_busy_count != 0`` and the firmware
        schedules a PEN-driven STOP, the MSSP keeps PEN=1 for
        ``stop_busy_cycles`` Tcy beyond the normal SCL-period
        deadline.  Used to simulate the field-observed
        "stuck PEN" condition that V3.1's bounded
        i2c_wait_bus_idle is designed to recover from.

        Both kwargs MUST be passed together: the rust facade
        doesn't expose getters for the current MSSP fault
        state, so accepting a partial update would conceal an
        ambiguous "keep the other" semantics that gpsim's
        ``MainI2CHarness.set_mssp_stop_fault`` only handles
        because gpsim's CLI lets you address each attribute
        independently.  Tests that need to update one knob
        without disturbing the other should call
        ``clear_mssp_stop_faults()`` first and then pass both.

        Both args are clamped as gpsim does
        (``max(0, int(...))`` for cycles,
        ``max(-1, int(...))`` for count) so the
        signature is gpsim-compatible.

        Calling with both args ``None`` is a no-op (matches
        gpsim's behaviour when its corresponding `if x is not
        None` chain finds nothing to forward).
        """
        if stop_busy_cycles is None and stop_busy_count is None:
            return
        if stop_busy_cycles is None or stop_busy_count is None:
            raise ValueError(
                "set_mssp_stop_fault: rust facade requires both "
                "stop_busy_cycles AND stop_busy_count to be passed "
                "together (no partial-update helper exists today; "
                "call clear_mssp_stop_faults() first if you only "
                "want to update one knob)."
            )
        self._inner.set_mssp_stop_fault(
            max(0, int(stop_busy_cycles)),
            max(-1, int(stop_busy_count)),
        )

    def clear_mssp_stop_faults(self) -> None:
        """Clear all MSSP fault-injection knobs on MAIN0's
        MSSP.  Mirror of gpsim's
        ``MainChainHarness.clear_mssp_stop_faults``
        (chain_gpsim.py:468).
        """
        self._inner.clear_mssp_stop_faults()

    def force_reset_main_mssp(self) -> None:
        """Force-abort any in-flight MSSP transaction on MAIN0
        and clear the SSPCON2 trigger bits.  Mirror of gpsim's
        ``harness._issue("p18f2455.sspcon2 = 0")`` privileged-
        register-write workaround used by V3.1/V3.2 PEN-timeout
        recovery tests.
        """
        self._inner.force_reset_main_mssp()

    def set_main_an0_sample(self, unit: int, value: int) -> None:
        """Set the AN0 (rail-sense ADC ch 0) sample for one MAIN.

        ``unit`` selects which MAIN core: ``0`` for MAIN0, ``1``
        for MAIN1.  Other values raise ``ValueError``.  On
        MAIN-only / single-MAIN chain topologies (where i_main0
        == i_main1) both unit indices target the same core.

        ``value`` is a 10-bit ADC sample in ``[0x0000, 0x03FF]``
        (the PIC18F2455 ADC is 10-bit per DS39632E §21).  Values
        outside that range raise ``ValueError`` rather than
        silently masking, so a caller that passes a "12-bit-
        looking" word like ``0x0500`` gets a clear error instead
        of an unexpected sub-threshold sample.

        V3.x's ``adc_boot_gate`` (`asm:4041`) busy-waits until
        AN0 crosses ``>= 0x0236`` (runtime hysteresis
        ``0x0229/0x0228``).  Default factory seed is ``0x0300``
        (well above threshold) for both MAINs.

        Bug #45 H1 use case: the H1 firmware-OBSERVABLE
        reproduction needs MAIN1 to run wake_request_handler
        (asm:1894 sets ``active_flags.bit3``) BEFORE the AN0
        droop applies.  Setting MAIN1's AN0 below threshold
        while MAIN1 is still in the post-STDBY standby loop
        prevents wake-byte dispatch in the rust sim and
        produces the H2 observable from #81 instead.  Use AT
        or AFTER the wake byte's parser dispatch is observable:
        trigger on ``MAIN1.active_flags.bit3 == 1`` (RAM 0x05E
        bit 3) and then drop AN0 to ``0x0100`` -- the path from
        wake_request_handler exit through the main loop and
        standby_event_dispatch to the gate's first ADC
        conversion (asm:4048) traverses many MAIN-Tcy, leaving
        ample slack for the droop to land before the conversion
        latch.  See ``crates/dlcp-sim/tests/multicore_parity.rs``
        for the fully-worked example.
        """
        v = int(value)
        if not (0 <= v <= 0x3FF):
            raise ValueError(
                "set_main_an0_sample: value must fit in 10 bits "
                f"(0x0000..=0x03FF); got 0x{v:04X}. "
                "The PIC18F2455 ADC is 10-bit per DS39632E §21."
            )
        self._inner.set_main_an0_sample(int(unit), v)

    def inject_triplet(self, frame_or_route, cmd=None, data=None) -> bool:  # type: ignore[no-untyped-def]
        """Inject a 3-byte chain frame directly into
        CONTROL's RX ring buffer.  Mirror of
        ``control_gpsim.py::GpsimControlHarness.inject_triplet``.

        Two call shapes (gpsim-compat duck typing):

          * Single object with ``.route`` / ``.cmd`` /
            ``.data`` attributes (e.g. an ``RxTriplet`` /
            ``TxTriplet`` from ``control_gpsim.py``); same
            shape gpsim's ``inject_triplet`` accepts.
          * Three positional ints: ``inject_triplet(route,
            cmd, data)``.

        Returns True on success, False if the ring buffer
        was too full.
        """
        if cmd is None and data is None:
            # Object-with-attrs form (gpsim-compat).
            triplet = frame_or_route
            route_val = triplet.route
            cmd_val = triplet.cmd
            data_val = triplet.data
        else:
            route_val = frame_or_route
            cmd_val = cmd
            data_val = data
        return bool(self._inner.inject_triplet(
            int(route_val) & 0xFF,
            int(cmd_val) & 0xFF,
            int(data_val) & 0xFF,
        ))

    def inject_host_command(
        self, *, cmd: int, data: int, route: int = 0xBF
    ) -> bool:
        """Inject a host command (HFD-over-BF) into
        CONTROL's RX ring buffer.  Mirror of
        ``control_gpsim.py::GpsimControlHarness.inject_host_command``.
        Default route is 0xBF (the parser dispatch tag).
        Returns True on success, False if the ring buffer
        was too full.
        """
        return bool(self._inner.inject_host_command(
            int(cmd) & 0xFF, int(data) & 0xFF, int(route) & 0xFF
        ))

    def inject_decoded_ir_event(
        self, *, addr: int, cmd: int, clear_debounce: bool = True
    ) -> None:
        """Inject a decoded IR event through the ISR
        handoff cells (0x01D = decoded cmd, 0x01E = decoded
        addr) and clear ``control_flags.IR_ARMED``.  Mirror
        of
        ``control_gpsim.py::GpsimControlHarness.inject_decoded_ir_event``.
        Bypasses RB5 IR-waveform decoding.
        """
        self._inner.inject_decoded_ir_event(
            int(addr) & 0xFF,
            int(cmd) & 0xFF,
            bool(clear_debounce),
        )

    def tx_frames(self) -> list[tuple[int, int, int]]:
        """Snapshot CONTROL's TX byte history as a list of
        3-byte ``(route, cmd, data)`` tuples (frame-
        aligned; trailing partial frame truncated).  Mirror
        of
        ``control_gpsim.py::GpsimControlHarness.tx_frames``.
        """
        return [tuple(t) for t in self._inner.tx_frames()]  # type: ignore[misc]

    def tx_record_since_last_capture(self) -> list[int]:
        """Return MAIN0's TX bytes since the previous call
        (or chain construction).  Mirror of gpsim's
        ``MainChainHarness.decoder.tx_record_since_last_capture()``
        used by ``test_v32_layer5_diag_counters`` for
        byte-level inspection of cmd-0x21 diag responses.

        On MAIN-only chains (no UART couplings), the rust
        ``Chain::drain_completed_tx_bytes`` path records each
        completed TX byte to ``uart_tx_history`` even without
        a peer, so MAIN's USART output is observable
        independent of any coupling.
        """
        return list(self._inner.tx_record_since_last_capture())

    def mark_tx_capture_point(self) -> None:
        """Reset the TX capture pointer to the current end
        of MAIN0's recorded TX history.  Subsequent
        ``tx_record_since_last_capture`` calls only return
        bytes pushed AFTER this call.  Use to drop
        pre-stimulus bytes (boot-time TX, prior responses)
        before injecting the next stimulus.
        """
        self._inner.mark_tx_capture_point()

    def mark_ctl_tx_capture_point(self) -> None:
        """CONTROL-side analog of :meth:`mark_tx_capture_point`.
        Snapshots the count of CONTROL TX records for use with
        :meth:`ctl_tx_record_since_last_capture`.  Equivalent
        to gpsim's
        ``len(GpsimControlHarness.tx_frames())`` snapshot before
        injecting a stimulus that the test wants to bound the
        TX observation around.
        """
        self._inner.mark_ctl_tx_capture_point()

    def ctl_tx_record_since_last_capture(self) -> list[int]:
        """Return CONTROL's TX bytes pushed since the last
        :meth:`mark_ctl_tx_capture_point` call (or chain
        construction).  Bytes are returned as a flat list of
        u8s; the caller chunks into 3-byte ``(route, cmd,
        data)`` frames.  Equivalent to slicing
        ``GpsimControlHarness.tx_frames()[before:]`` after the
        baseline mark.
        """
        return list(self._inner.ctl_tx_record_since_last_capture())

    def mark_main1_tx_capture_point(self) -> None:
        """MAIN1 mirror of :meth:`mark_tx_capture_point` for
        3-core wire-chain probes.  In the V1.71+V3.2+V3.2 ring
        topology (CTL.tx -> MAIN0.rx -> MAIN1.rx -> CTL.rx),
        MAIN0's BF/2N reply burst flows through MAIN1's
        forwarder before reaching CONTROL.  Comparing MAIN0 TX,
        MAIN1 TX, and CONTROL RX accept counts localizes which
        hop drops bytes.  Single-MAIN chains alias
        ``i_main1 == i_main0``, so this returns the same stream
        as :meth:`mark_tx_capture_point` and offers no new
        information.  See task #94.
        """
        self._inner.mark_main1_tx_capture_point()

    def main1_tx_record_since_last_capture(self) -> list[int]:
        """MAIN1 mirror of :meth:`tx_record_since_last_capture`.
        Returns MAIN1's TX bytes recorded since the last
        :meth:`mark_main1_tx_capture_point` call (or chain
        construction).  Bytes are returned as a flat list of
        u8s.  See task #94.
        """
        return list(self._inner.main1_tx_record_since_last_capture())

    def current_ctl_pc(self) -> int:
        """CONTROL core's current PC (firmware program counter,
        word-aligned, masked to 21 bits).  Mirror of gpsim's
        ``pc()`` register read.  Used by tests that align
        observation windows to firmware-loop-head events.
        """
        return int(self._inner.current_ctl_pc())

    def current_main_pc(self) -> int:
        """MAIN0 core's current PC.  See :meth:`current_ctl_pc`."""
        return int(self._inner.current_main_pc())

    def step_until_pc_hit(
        self,
        core_idx: int,
        pc_lo: int,
        pc_hi: int,
        max_tcy: int = 1_000_000,
    ) -> int:
        """Step the chain until ``core_idx``'s PC enters
        ``[pc_lo, pc_hi]`` (inclusive) or ``max_tcy`` Tcy
        elapse.  Returns the actual PC at exit (which may be
        outside the range if the budget was exhausted).
        ``core_idx``: 0=CONTROL, 1=MAIN0.  Mirror of gpsim's
        ``break e <addr>`` + ``run`` primitive.
        """
        return int(self._inner.step_until_pc_hit(
            int(core_idx),
            int(pc_lo) & 0x001F_FFFF,
            int(pc_hi) & 0x001F_FFFF,
            int(max_tcy),
        ))

    def read_dsp_address_nack_count_remaining(self) -> int:
        """Remaining address-NACK injection budget on the
        TAS3108 slave coupled to MAIN0.  Mirror of gpsim's
        ``MainChainHarness.read_i2c_attribute("dsp34",
        "Address_Nack_Count")``.  Used by deafness-chain
        regression tests to prove firmware-driven I²C bursts
        consumed part of the budget set by
        :meth:`set_i2c_fault`.
        """
        return int(self._inner.read_dsp_address_nack_count_remaining())

    def enable_force_connected(self) -> None:
        """Enable the per-step "force CONNECTED" hook on
        CONTROL.  After this call, every subsequent
        :meth:`step` ORs 0x0A into 0x01F (CONNECTED + event-
        exit) and resets the idle timer at 0x09D/0x09E.
        Mirror of gpsim's
        ``GpsimControlHarness(heartbeat_force_connected=True)``.
        Idempotent.
        """
        self._inner.enable_force_connected()

    def inject_control_rx_bytes(self, bytes_: list[int] | bytes) -> bool:
        """Inject 3-byte chain frames into CONTROL's RX ring at
        base 0x066 (depth 48 bytes; rd at 0x098, wr at 0x099).
        Returns False if the ring is too full (>= 0x2C bytes
        pending).  Mirror of gpsim's
        ``_CliSession::_inject_rx_bytes``.
        """
        return bool(self._inner.inject_control_rx_bytes(list(bytes_)))

    def warmup_force_connected(self, cycles: int) -> None:
        """Run a CONTROL-only chain through cold-boot ->
        WAITING -> DISPLAY transition by feeding synthetic
        BF status replies until the firmware reaches DISPLAY
        mode, then continues stepping with the force-connected
        hook applied each chunk.  Implicitly enables
        :meth:`enable_force_connected` so post-warmup
        :meth:`step` keeps the hook active.  Mirror of
        ``GpsimControlHarness.warmup`` with
        ``heartbeat_rx_mode="full"`` +
        ``heartbeat_force_connected=True``.
        """
        self._inner.warmup_force_connected(int(cycles))

    def step_until_tx_quiescent(
        self,
        *,
        quiescent_tcy: int = 10_000,
        max_tcy: int = 5_000_000,
        require_tx_activity: bool = True,
    ) -> int:
        """Advance simulation until MAIN0 stops emitting TX
        bytes for ``quiescent_tcy`` consecutive Tcy, or up
        to ``max_tcy`` total.  Returns the number of Tcy
        actually advanced.  Mirror of gpsim's
        ``chain.step_until_tx_quiescent()``.

        ``require_tx_activity`` (default True): wait for at
        least one TX byte to appear before applying the
        quiescence check, so the function doesn't return
        immediately on the first quiescence chunk if the
        firmware hasn't yet started responding.  Pass False
        if the test wants the bare "no activity for one
        chunk" semantic (e.g. asserting NO response is
        generated under some condition).

        Defaults: 10_000 Tcy quiescence window (~2.5 ms at
        4 MIPS, comfortably longer than a 31_250-baud frame
        at ~320 us/byte); 5_000_000 Tcy upper bound (~1.25 s
        sim time, long enough for a multi-frame burst
        response).
        """
        return int(self._inner.step_until_tx_quiescent(
            int(quiescent_tcy),
            int(max_tcy),
            bool(require_tx_activity),
        ))

    def step(self) -> None:
        """Step a single 200K-Tcy / 3.2 M-tick chunk.
        Mirror of gpsim's ``step()`` cadence.  Used by the
        ``test_v17_shifted_full_parity`` scenario helpers.
        """
        self._inner.step()

    def warmup(self, cycles: int) -> None:
        """Step ``cycles`` K20-Tcy worth of universal
        ticks (each Tcy = 16 universal ticks).  Mirror of
        ``control_gpsim.py::GpsimControlHarness.warmup``.
        Used by the parity-test helpers to advance past
        the cold-boot handshake before driving the
        scenario.
        """
        self._inner.warmup(int(cycles))

    def step_tcy(self, tcy: int) -> None:
        """Advance the universal clock by ``tcy`` K20
        instruction cycles.  Each Tcy = 16 universal ticks
        on the K20.

        Use this when a test needs a specific amount of
        simulated time -- e.g. parity tests that previously
        used gpsim's per-harness ``chunk_cycles`` config
        should call ``chain.step_tcy(600_000)`` explicitly.
        The rust simulator's universal-clock scheduler
        runs both cores in lock-step at instruction-level
        granularity; gpsim's chunked-alternating execution
        is a serialization artifact we deliberately do NOT
        replicate, so there is no per-instance chunk_cycles
        knob to tune.
        """
        self._inner.step_tcy(int(tcy))


__all__ = ["Chain", "__version__"]
