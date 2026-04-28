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
