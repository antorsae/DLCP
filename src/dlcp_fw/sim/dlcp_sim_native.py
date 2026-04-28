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
    def from_v17_chain(
        cls,
        control_hex_path: str,
        main_hex_path: str | None = None,
    ) -> "Chain":
        """Generic V1.7-family single-MAIN factory.

        Accepts any K20 CONTROL hex (V1.6b stock, V1.7
        byte-identical rebuild, V1.7 shifted +0x222, V1.71)
        paired with any 2455 MAIN hex (defaults to
        V2.3-combined when ``main_hex_path`` is ``None``).
        Used by the dual-mode migration of
        ``tests/sim/test_v17_chain.py`` to drive the rust
        engine with the same hex files the gpsim
        ``v17_chain_images`` fixture builds.
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
        """Index of MAIN0 in the chain."""
        return self._inner.main0

    @property
    def main1(self) -> int:
        """Index of MAIN1 in the chain."""
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


__all__ = ["Chain", "__version__"]
