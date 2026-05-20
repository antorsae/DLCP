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

from functools import lru_cache as _lru_cache
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


@_lru_cache(maxsize=None)
def _v32_main_symbol(name: str, fallback: int) -> int:
    """Resolve a canonical V3.2 MAIN symbol from the gpasm listing.

    The PyO3 helper executes firmware subroutines by PC.  Those PCs move when
    V3.2 source changes, so keep the native fallback for old binaries but feed
    current labels from the release listing whenever available.
    """
    try:
        from dlcp_fw.paths import V32_MAIN_HEX
        from dlcp_fw.sim.v30_symbols import load_gpasm_symbols_for_hex

        symbols = load_gpasm_symbols_for_hex(V32_MAIN_HEX)
        if symbols and name in symbols:
            return int(symbols[name])
    except Exception:
        pass
    return int(fallback)


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
    def from_v171_v32(
        cls,
        control_hex_path: str | None = None,
        main_hex_path: str | None = None,
        v23_seed_hex_path: str | None = None,
    ) -> "Chain":
        """Build the canonical V1.71 CONTROL + 2× V3.2 MAIN ring.

        Mirrors the prelude of
        ``crates/dlcp-sim/tests/multicore_parity.rs::three_core_ring_v171_v32_v32_*``
        scenarios:

        - Load V1.71 CONTROL hex (default:
          ``firmware/patched/releases/DLCP_Control_V1.71.hex``;
          override via ``control_hex_path``).
        - Load V3.2 MAIN hex (default: canonical app-only release at
          ``firmware/patched/releases/DLCP_Firmware_V3.2.hex``;
          override via ``main_hex_path``) + V2.3-combined seed
          (default: ``firmware/stock/main/DLCP Firmware V2.3-combined.hex``;
          override via ``v23_seed_hex_path``) and merge to get
          a silicon-correct MAIN flash (V3.2 app on V2.3 boot
          block / preset table / EEPROM seed; per task #36 /
          P3.6 background).
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

        Use the path overrides when the test fixture freshly
        assembles V1.71 / V3.2 hexes from current source into a
        tmp path -- otherwise the rust path tests the canonical
        RELEASE while gpsim/source-based tests test the freshly
        built fixture and the two could diverge on stale-canonical
        skew (codex task #77).

        After return the chain is ready for :meth:`step_ticks`.
        """
        return cls(
            _native.Chain.from_v171_v32(
                control_hex_path,
                main_hex_path,
                v23_seed_hex_path,
            )
        )

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
        MAIN chain.  Uses the canonical V3.1 release hex
        (app-only) merged onto V2.3-combined (silicon-correct
        boot block + EEPROM).
        """
        return cls(_native.Chain.from_v171_v31())

    @classmethod
    def from_v3x_main_only(
        cls,
        v3x_main_hex_path: str,
        v23_seed_hex_path: str | None = None,
    ) -> "Chain":
        """MAIN-only single-core factory.

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

        Boots a single K20 core with an HD44780 LCD slave on the
        LCD-control pins.  Used by V1.7 / V1.71 relocation-safety
        tests that compare stock V1.6b vs rebuilt V1.7 vs shifted
        V1.7 in CONTROL-only mode (no MAIN heartbeats) and assert
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

    def lcd_ddram_write_count(self, addr: int) -> int:
        """Count completed data writes to one raw HD44780 DDRAM address."""
        return int(self._inner.lcd_ddram_write_count(int(addr) & 0x7F))

    def is_connected(self) -> bool:
        """True when CONTROL has marked itself as connected.

        Reads bit 1 of physical RAM 0x01F on the CONTROL
        core (the ``control_flags`` byte)."""
        return bool(self._inner.is_connected())

    def is_waiting(self) -> bool:
        """True when CONTROL's LCD shows the WAITING screen.

        The substring ``"WAITING FOR DLCP"`` (case-insensitive)
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
        """
        return int(self._inner.run_until_waiting(int(limit)))

    def step_many(self, n_chunks: int) -> None:
        """Step ``n_chunks`` chunks of 3.2 M ticks each (no
        early-exit predicate).  Used by the V1.7 blackout/
        wake test to give the firmware time to render the
        standby screen after a STBY press.
        """
        self._inner.step_many(int(n_chunks))

    def set_blackout(self, enabled: bool) -> None:
        """Toggle the chain's UART-blackout flag.  When
        enabled, every completed UART TX byte is dropped
        instead of delivered -- modelling a physical chain
        disconnect (CAT5 unplug, optocoupler fault).  Cores
        keep running and TX history is NOT updated for
        dropped bytes."""
        self._inner.set_blackout(bool(enabled))

    def press(self, key: str) -> None:
        """Inject a panel-button press on CONTROL.  Drives
        the button's active-low PORTx bit LOW, holds ~1 sec
        sim (50 M universal ticks, well past V1.71's 4-poll
        button debounce), releases HIGH, and settles
        another ~1 sec sim. Accepted keys (case-insensitive): SELECT, DOWN,
        STBY, RIGHT, UP, LEFT.  Raises ``ValueError`` for
        any other key.
        """
        self._inner.press(str(key))

    def read_reg(self, addr: int) -> int:
        """Read a single byte of CONTROL's data memory at
        the given physical address. Common addresses: 0x01F (control_flags), 0x0BF
        (display_state_index), 0x0B8 (input_select_cache),
        0x0B9 (volume_cache).
        """
        return int(self._inner.read_reg(int(addr) & 0xFFF))

    def write_reg(self, addr: int, value: int) -> None:
        """Write a single byte of CONTROL's data memory at
        the given physical address.
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

        """
        return int(self._inner.read_main_reg(int(unit), int(addr) & 0xFFF))

    def set_main_pin(
        self,
        unit: int,
        port: str,
        bit: int,
        level: bool,
    ) -> None:
        """Drive an external input pin on one MAIN's PORTx to the
        requested logic level.  Equivalent of gpsim's
        ``MainChainHarness(rc2_mode=...)`` continuous pin-level
        hold (codex task #75).

        ``unit`` selects MAIN0 (0) or MAIN1 (1); ``port`` is "A",
        "B", or "C"; ``bit`` is 0..7; ``level`` is True for HIGH,
        False for LOW.

        **Caveat (gpio.rs::drive_external_pin /
        is_general_input_pin):** the held level is only stored
        when the pin is currently a general input -- TRIS bit
        set, plus on RC4/RC5 the USB peripheral must not be
        overriding the pin (UCON.USBEN clear).  If TRIS is
        cleared (pin is output) at call time, the call is
        silently a no-op.  If firmware later flips TRIS to
        output, LATx takes over and the previously-held external
        level no longer drives the pin.  ANSEL/ANSELH analog
        masking is not modeled for the PIC18F2455 (MAIN) variant
        -- ``analog_digital_off_mask`` returns 0 for non-K20
        cores -- so a stored level always reads back on PORTx
        for MAIN pins regardless of ADCON1 PCFG bits.  This is
        fine for strap pins like RC2 (chain-mode select) that
        firmware never reconfigures, and for steady-state INTx
        / RBIF / RA0-wake stimuli; do not rely on "held level
        survives output" semantics for pins whose TRIS direction
        toggles during the test.
        """
        self._inner.set_main_pin(int(unit), str(port), int(bit), bool(level))

    def set_control_pin(self, port: str, bit: int, level: bool) -> None:
        """CONTROL-side equivalent of ``set_main_pin``: drive an
        external input pin on CONTROL's PORTx to the requested
        logic level.  Same ``gpio.rs::drive_external_pin`` caveats
        apply (pin must currently be a general digital input;
        TRIS-to-output flip releases the held level).

        Used by the RC5 IR pulse-train tests that drive RB5 with
        timed edges to exercise the actual ``ir_rc5_decode``
        decoder rather than poking ``ir_decoded_cmd`` directly.
        """
        self._inner.set_control_pin(str(port), int(bit), bool(level))

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

    def poke_main_src4382_reg(self, unit: int, subaddr: int, value: int) -> None:
        """Seed one MAIN-coupled SRC4382 register.

        This bypasses I2C only for simulator setup.  Firmware still
        exercises its real MSSP read/write path when tests step time.
        """
        self._inner.poke_main_src4382_reg(
            int(unit), int(subaddr) & 0xFF, int(value) & 0xFF
        )

    def read_main_src4382_reg(self, unit: int, subaddr: int) -> int:
        """Read one MAIN-coupled SRC4382 register from the sim model."""
        return int(self._inner.read_main_src4382_reg(
            int(unit), int(subaddr) & 0xFF
        ))

    def reset_main_src4382_stats(self, unit: int) -> None:
        """Clear one MAIN-coupled SRC4382 traffic counters."""
        self._inner.reset_main_src4382_stats(int(unit))

    def read_main_src4382_stats(self, unit: int) -> dict[str, object]:
        """Return one MAIN-coupled SRC4382 traffic snapshot."""
        (
            bytes_acked,
            bytes_nacked,
            tx_bytes_by_subaddr,
            read_bytes_by_subaddr,
            write_transactions,
            read_transactions,
            writes_by_subaddr,
            reads_by_subaddr,
        ) = self._inner.read_main_src4382_stats(int(unit))
        return {
            "bytes_acked": int(bytes_acked),
            "bytes_nacked": int(bytes_nacked),
            "tx_bytes_by_subaddr": list(tx_bytes_by_subaddr),
            "read_bytes_by_subaddr": list(read_bytes_by_subaddr),
            "write_transactions": int(write_transactions),
            "read_transactions": int(read_transactions),
            "writes_by_subaddr": list(writes_by_subaddr),
            "reads_by_subaddr": list(reads_by_subaddr),
        }

    def read_main_src4382_write_values(self, unit: int, subaddr: int) -> list[int]:
        """Return the first data byte for each completed SRC4382 write
        transaction that started at ``subaddr``."""
        return [
            int(v) & 0xFF
            for v in self._inner.read_main_src4382_write_values(
                int(unit), int(subaddr) & 0xFF
            )
        ]

    def inject_main_src4382_address_nack(self, unit: int, count: int) -> None:
        """Inject address-phase NACKs into one MAIN-coupled SRC4382."""
        self._inner.inject_main_src4382_address_nack(int(unit), int(count))

    def inject_main_src4382_data_nack(self, unit: int, count: int) -> None:
        """Inject post-address data-byte NACKs into one MAIN-coupled SRC4382."""
        self._inner.inject_main_src4382_data_nack(int(unit), int(count))

    def firmware_hid_report(
        self,
        unit: int,
        payload: bytes | bytearray | list[int],
        max_steps: int = 20_000,
    ) -> tuple[bytes, int]:
        """Execute one app-mode 64-byte HID report through the
        running V3.2 firmware's EP1 OUT/IN service path.

        This models a configured EP1 transaction at the firmware
        dispatcher boundary rather than emulating command semantics in
        Python: the rust facade stages the EP1 OUT BDT/data buffer,
        invokes ``main_usb_service_3a26`` twice, and returns the EP1 IN
        data buffer.  The second tuple element is the number of observed
        entries into ``hid_command_dispatch``.
        """
        report = [int(b) & 0xFF for b in payload]
        main_usb_service_pc = _v32_main_symbol("main_usb_service_3a26", 0x3436)
        hid_command_dispatch_pc = _v32_main_symbol("hid_command_dispatch", 0x10AC)
        response, dispatch_hits = self._inner.firmware_hid_report(
            int(unit),
            report,
            int(max_steps),
            main_usb_service_pc,
            hid_command_dispatch_pc,
        )
        return bytes(response), int(dispatch_hits)

    def read_core_flash(
        self, core_idx: int, addr: int, length: int
    ) -> bytes:
        """Read a contiguous byte range from a core's program
        flash.
        ``core_idx``: 0=CONTROL, 1=MAIN0, 2=MAIN1.
        ``addr``: byte-addressed program flash address.
        ``length``: number of bytes to read.

        Raises ``ValueError`` for unknown ``core_idx`` or if
        ``addr + length`` extends past the flash end.

        Spec / ledger ref: P4-followup E
        (``docs/SIM_REWRITE_RUST_PROGRESS.md`` "P4 followup
        tracker", task #103) — used by the overlay helpers
        (e.g. :func:`apply_standby_bypass_overlay`) to verify
        manifest preconditions before patching and the
        analogous postconditions afterwards.
        """
        return bytes(
            self._inner.read_core_flash(int(core_idx), int(addr), int(length))
        )

    def patch_core_flash(
        self, core_idx: int, addr: int, payload: bytes
    ) -> None:
        """Patch a contiguous byte range in a core's program
        flash.

        ``core_idx``: 0=CONTROL, 1=MAIN0, 2=MAIN1.
        ``addr``: byte-addressed program flash address.
        ``payload``: bytes to write.

        Raises ``ValueError`` for unknown ``core_idx`` or if
        ``addr + len(payload)`` extends past the flash end.

        Spec / ledger ref: P4-followup E
        (``docs/SIM_REWRITE_RUST_PROGRESS.md`` "P4 followup
        tracker", task #103).  Higher-level helper
        :func:`apply_standby_bypass_overlay` layers the
        gpsim ``control_disable_standby_check_dynamic``
        manifest on top of this primitive.
        """
        self._inner.patch_core_flash(
            int(core_idx), int(addr), bytes(payload)
        )

    @property
    def current_cycle(self) -> int:
        """CONTROL's K20-Tcy cycle counter."""
        return int(self._inner.current_cycle)

    def pause_heartbeat(self) -> None:
        """No-op on the rust backend.  The rust facade has no synthetic-heartbeat
        mode -- the chain runs against a real V2.3-combined
        MAIN that emits actual BF replies -- so there is
        nothing to pause.  Provided for duck-typing parity.
        """
        self._inner.pause_heartbeat()

    def inject_main_frames_fifo(
        self, frames: list[list[int]], fifo_limit: int
    ) -> tuple[int, int]:
        """Inject 3-byte chain frames into MAIN's RX ring.

        Targets the V3.x
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

    def inject_main_uart_rx_bytes(
        self, unit: int, bytes_: list[int] | bytes
    ) -> tuple[int, int]:
        """Inject raw bytes into one MAIN's silicon EUSART RX path.

        Returns ``(accepted, dropped)``.  Unlike
        :meth:`inject_main_frames_fifo`, this exercises the UART
        peripheral gates (`SPEN`, `CREN`, OERR, FIFO capacity, MCLR).
        """
        return tuple(self._inner.inject_main_uart_rx_bytes(
            int(unit), [int(b) & 0xFF for b in bytes_],
        ))

    def write_control_eeprom_byte(self, addr: int, value: int) -> None:
        """Seed CONTROL's EEPROM peripheral at the given
        8-bit address.  Use this immediately after
        ``Chain.from_v17_chain(...)`` and BEFORE the first
        ``step()`` / ``warmup()`` call -- the firmware
        reads EEPROM during early boot.
        """
        self._inner.write_control_eeprom_byte(int(addr) & 0xFF, int(value) & 0xFF)

    def read_main_eeprom_byte(self, unit: int, addr: int) -> int:
        """Read a single byte from one MAIN's EEPROM peripheral
        at the given 8-bit address.  ``unit=0`` selects MAIN0
        (PB1), ``unit=1`` selects MAIN1 (PB2).  Mirrors the
        cmd 0x43 (DIAG_MEMREAD) region=1 path used by the
        V3.2 release flasher to verify post-flash EEPROM
        filename slots; consumed by the SimHidBackend HID
        adapter (``dlcp_fw/flash/sim_backend.py``) when
        routing flasher cmd 0x43 calls through the rust-sim
        chain.
        """
        return int(self._inner.read_main_eeprom_byte(int(unit), int(addr) & 0xFF)) & 0xFF

    def write_main_eeprom_byte(self, unit: int, addr: int, value: int) -> None:
        """Seed one MAIN's EEPROM peripheral at the given
        8-bit address.  ``unit=0`` selects MAIN0 (PB1),
        ``unit=1`` selects MAIN1 (PB2).  Use this
        immediately after ``Chain.from_v171_v32(...)`` and
        BEFORE the first ``step_ticks`` call -- the
        firmware reads EEPROM during early boot for boot
        preset init, route shadow restore, etc.
        """
        self._inner.write_main_eeprom_byte(
            int(unit), int(addr) & 0xFF, int(value) & 0xFF,
        )

    def read_dsp_reg(self, subaddr: int) -> int:
        """Read a single TAS3108 DSP register at ``subaddr``.

        Returns the byte stored in the rust TAS3108 slave's
        in-memory register file (latched as MAIN's MSSP I²C
        burst writes the DSP).  The rust facade reads the
        first DSP slave coupled to MAIN0.
        """
        return int(self._inner.read_dsp_reg(int(subaddr) & 0xFF)) & 0xFF

    def read_main_dsp_reg(self, unit: int, subaddr: int) -> int:
        """Read a TAS3108 DSP register from a SPECIFIC MAIN's
        DSP slave.

        ``unit=0`` selects MAIN0's DSP, ``unit=1`` selects
        MAIN1's DSP.  Used by chain-level preset-sync tests
        that need to compare MAIN0 vs MAIN1 DSP register
        files byte-by-byte (e.g. confirm both audio paths
        converge to identical biquad coefficients after a
        CONTROL preset-switch broadcast).
        """
        return int(
            self._inner.read_main_dsp_reg(int(unit), int(subaddr) & 0xFF)
        ) & 0xFF

    def read_main_dsp_write_payload(self, unit: int, subaddr: int) -> bytes | None:
        """Read the most recent completed TAS3108 write payload that
        started at ``subaddr`` for one MAIN's DSP slave.

        This preserves full preset-entry payloads such as 20-byte
        biquad writes.  The byte register-file snapshot exposed by
        :meth:`read_main_dsp_reg` is intentionally lossy for those
        entries because later bytes land at subsequent subaddresses.
        """
        payload = self._inner.read_main_dsp_write_payload(
            int(unit), int(subaddr) & 0xFF
        )
        if payload is None:
            return None
        return bytes(payload)

    def reset_main_dsp_write_log(self, unit: int) -> None:
        """Clear one MAIN-coupled TAS3108 completed-write log."""
        self._inner.reset_main_dsp_write_log(int(unit))

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
        slave coupled to MAIN0.

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
        TAS3108 slave coupled to MAIN0.
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
        MSSP.
        """
        self._inner.clear_mssp_stop_faults()

    def set_mssp_start_fault(
        self,
        *,
        cycles: int,
        count: int,
    ) -> None:
        """Program MAIN0's MSSP START/SEN fault knobs.

        ``cycles`` extends each selected SEN/RSEN sequence deadline by
        that many Tcy; ``count`` is the number of affected start
        sequences, with ``-1`` meaning indefinite.  Unlike a test-side
        SSPCON2 poke, this leaves the peripheral state machine owning
        the busy bit and completion timing.
        """
        self._inner.set_mssp_start_fault(
            max(0, int(cycles)),
            max(-1, int(count)),
        )

    def clear_mssp_start_faults(self) -> None:
        """Clear MAIN0's MSSP START/SEN fault knobs."""
        self._inner.clear_mssp_start_faults()

    def set_mssp_clock_stretch(
        self,
        *,
        cycles: int,
        count: int,
    ) -> None:
        """Program MAIN0's MSSP clock-stretch injection knobs.

        ``cycles`` extends each selected MSSP sequence deadline by
        that many Tcy; ``count`` is the number of affected sequences,
        with ``-1`` meaning indefinite.  This approximates a held-low
        SCL / clock-stretch condition in sim-only sweeps.
        """
        self._inner.set_mssp_clock_stretch(
            max(0, int(cycles)),
            max(-1, int(count)),
        )

    def clear_mssp_clock_stretch(self) -> None:
        """Clear MAIN0's MSSP clock-stretch injection knobs."""
        self._inner.clear_mssp_clock_stretch()

    def set_mssp_line_hold(
        self,
        *,
        scl_low: bool = False,
        sda_low: bool = False,
    ) -> None:
        """Force MAIN0's MSSP bus lines low at the peripheral boundary.

        While either line is forced low, in-flight MSSP master
        sequences remain busy and their transfer-control bits do not
        auto-clear.  GPIO pin reads are still modelled separately, so
        tests that exercise bitbang bus-clear should also force RB0/RB1
        readback through the existing pin/PORT helpers.
        """
        self._inner.set_mssp_line_hold(bool(scl_low), bool(sda_low))

    def clear_mssp_line_holds(self) -> None:
        """Release MAIN0's forced MSSP bus line holds."""
        self._inner.clear_mssp_line_holds()

    def force_reset_main_mssp(self) -> None:
        """Force-abort any in-flight MSSP transaction on MAIN0
        and clear the SSPCON2 trigger bits.
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

    def apply_main_reset(self, unit: int, source: str) -> None:
        """Apply a reset source to one MAIN core and schedule it to run.

        ``source`` accepts ``por`` / ``poweron``, ``bor`` /
        ``brownout``, ``mclr``, ``wdt``, ``reset``,
        ``stackfull``, or ``stackunderflow``.
        """
        self._inner.apply_main_reset(int(unit), str(source))

    def apply_reset_all(self, source: str) -> None:
        """Apply a reset source to every core and re-bootstrap the chain."""
        self._inner.apply_reset_all(str(source))

    def inject_triplet(self, frame_or_route, cmd=None, data=None) -> bool:  # type: ignore[no-untyped-def]
        """Inject a 3-byte chain frame directly into
        CONTROL's RX ring buffer. Two call shapes (gpsim-compat duck typing):

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
        CONTROL's RX ring buffer. Default route is 0xBF (the parser dispatch tag).
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
        (or chain construction).

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

    def mark_ctl_rx_capture_point(self) -> None:
        """Reset the CTL-side RX capture pointer.  Distinct
        from :meth:`mark_ctl_tx_capture_point` (CONTROL's
        outgoing bytes) and from filtering wire-attempts by
        ``dst_core``: this captures only bytes that the
        destination silicon's FIFO ACCEPTED (passed SPEN+CREN,
        not blocked by OERR, FIFO had room).  See task #94.
        """
        self._inner.mark_ctl_rx_capture_point()

    def ctl_rx_record_since_last_capture(self) -> list[int]:
        """Return CONTROL's RX-accepted bytes since the last
        :meth:`mark_ctl_rx_capture_point` call.  Distinct from
        wire-attempt filtering: this is the byte stream the
        firmware actually saw via RCREG reads.  See task #94.
        """
        return list(self._inner.ctl_rx_record_since_last_capture())

    def mark_main0_rx_capture_point(self) -> None:
        """MAIN0 mirror of :meth:`mark_ctl_rx_capture_point`."""
        self._inner.mark_main0_rx_capture_point()

    def main0_rx_record_since_last_capture(self) -> list[int]:
        """MAIN0 mirror of :meth:`ctl_rx_record_since_last_capture`."""
        return list(self._inner.main0_rx_record_since_last_capture())

    def mark_main1_rx_capture_point(self) -> None:
        """MAIN1 mirror of :meth:`mark_ctl_rx_capture_point`."""
        self._inner.mark_main1_rx_capture_point()

    def main1_rx_record_since_last_capture(self) -> list[int]:
        """MAIN1 mirror of :meth:`ctl_rx_record_since_last_capture`."""
        return list(self._inner.main1_rx_record_since_last_capture())

    def uart_tx_records_full(self) -> list[tuple[int, int, int, int]]:
        """Snapshot the FULL `uart_tx_history` as
        `(tick, src_core, dst_core, byte)` tuples.  No drainage,
        no filter -- caller filters by src/dst and slices by
        tick range.  Used by frame-level timeline probes."""
        return list(self._inner.uart_tx_records_full())

    def uart_rx_records_full(self) -> list[tuple[int, int, int, int]]:
        """Snapshot the FULL `uart_rx_history` (FIFO-accepted
        bytes) as `(tick, src_core, dst_core, byte)` tuples.
        Distinct from `uart_tx_records_full`: only bytes the
        destination's silicon FIFO accepted (passed SPEN+CREN,
        not blocked by OERR, FIFO had room)."""
        return list(self._inner.uart_rx_records_full())

    def set_link_fault(
        self,
        link_name: str,
        *,
        drop: bool | None = None,
        extra_cycles: int | None = None,
    ) -> None:
        """Per-link fault primitive.  Spec / ledger: P4-followup C
        (``docs/SIM_REWRITE_RUST_PROGRESS.md`` "P4 followup
        tracker", task #101).

        ``link_name`` follows the same role-based naming as
        :meth:`bridge_byte_stats` -- e.g. ``ctl_to_m0``,
        ``m0_to_m1``, ``m1_to_ctl`` for the rust 3-core ring.
        Tests that hard-code gpsim's bus-model labels (e.g.
        ``m0_to_ctl``, which doesn't exist on the rust ring)
        raise :class:`KeyError` listing the known links --
        the same exception type as gpsim's analog.  (Codex
        LOW from 4307acc: prior implementation used
        ``ValueError``.)

        ``drop``: ``True`` activates the wire-drop fault;
        every subsequent byte the source TXs is silently
        dropped at the wire layer.  ``False`` clears the
        fault.  ``None`` leaves the drop state unchanged
        (matches gpsim's three-state semantics).

        ``extra_cycles``: NOT supported on the rust silicon
        ring (no bridge-delay model).  Calling with
        ``extra_cycles != None`` raises
        :class:`NotImplementedError`; tests that need
        propagation-delay semantics must be marked
        ``gpsim``-only.  Keyword name matches gpsim's; the
        prior internal name ``extra_ticks`` was renamed for
        gpsim-shape parity (codex LOW from 4307acc).
        """
        self._inner.set_link_fault(
            link_name,
            drop=drop,
            extra_cycles=extra_cycles,
        )

    def bridge_byte_stats(self) -> dict[str, dict[str, int]]:
        """Per-link byte-count snapshot for every UART coupling
        actually wired in the chain.  Mirror-of-shape (NOT
        mirror-of-name) of
        ``WireMultiMainChainHarness.bridge_shift_stats``.

        Each top-level key is a link name; each value has
        ``{'total_edges': int, 'shift_events': int,
        'total_shift_cycles': int, 'max_shift_cycles': int}``.
        Only ``total_edges`` is meaningful for the rust
        silicon ring (number of bytes that crossed the link);
        bit-level counters stay 0 -- gpsim parity placeholders
        so callers don't have to branch on backend just to
        read the dict shape.

        **Topology divergence from gpsim** (codex MEDIUM from
        48a862d): the rust 3-core chain wires a TRUE ring
        (CONTROL -> MAIN0 -> MAIN1 -> CONTROL), so
        ``from_v171_v32`` exposes THREE hops:

           * ``ctl_to_m0``  -- CONTROL TX -> MAIN0 RX
           * ``m0_to_m1``   -- MAIN0 TX  -> MAIN1 RX
           * ``m1_to_ctl``  -- MAIN1 TX  -> CONTROL RX

        gpsim's wire-chain harness reports FOUR hops
        (``ctl_to_m0``, ``m0_to_m1``, ``m1_to_m0``,
        ``m0_to_ctl``) because its bus model simulates both
        directions of the M0-M1 link plus a MAIN0->CONTROL
        forwarder as separate bridges.  Dual-backend tests
        that iterate ``deltas.values()`` work on both shapes;
        tests that hard-code gpsim's four labels will fail on
        rust.

        Spec / ledger: P4-followup A
        (``docs/SIM_REWRITE_RUST_PROGRESS.md`` "P4 followup
        tracker", task #99).
        """
        return {
            link: dict(stats)
            for link, stats in self._inner.bridge_byte_stats().items()
        }

    def current_ctl_pc(self) -> int:
        """CONTROL core's current PC (firmware program counter,
        word-aligned, masked to 21 bits).  Used by tests that align
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
        ``core_idx``: 0=CONTROL, 1=MAIN0, 2=MAIN1.  Mirror of
        gpsim's ``break e <addr>`` + ``run`` primitive.
        (MAIN1 added 2026-05-04 as part of P4-followup B,
        ledger task #100, for 2-MAIN gpsim probe migration.)
        """
        return int(self._inner.step_until_pc_hit(
            int(core_idx),
            int(pc_lo) & 0x001F_FFFF,
            int(pc_hi) & 0x001F_FFFF,
            int(max_tcy),
        ))

    def set_core_pc(self, core_idx: int, pc: int) -> int:
        """Override a core's program counter.  Mirror of
        gpsim's ``pc=0x...`` CLI primitive.  Spec / ledger:
        P4-followup B (``docs/SIM_REWRITE_RUST_PROGRESS.md``
        "P4 followup tracker", task #100) — together with
        :meth:`step_until_pc_hit` this gives Python tests the
        ``pc=X ; break e Y ; run`` pattern that
        ``test_v31_combined_dsp_table_apply.py``,
        ``test_v30_gpsim_equivalence.py``, and parts of
        ``test_v30_relocation.py`` use to drive PIC18 helper
        routines from arbitrary entry points.

        ``core_idx``: 0=CONTROL, 1=MAIN0, 2=MAIN1.
        ``pc``: silicon's word-addressed PC; bit 0 is masked
        to 0 (instruction-aligned).  Returns the masked PC
        actually written so callers can detect the bit-0
        strip without a follow-up read.
        """
        return int(self._inner.set_core_pc(
            int(core_idx),
            int(pc) & 0x001F_FFFF,
        ))

    def read_dsp_address_nack_count_remaining(self) -> int:
        """Remaining address-NACK injection budget on the
        TAS3108 slave coupled to MAIN0.  Used by deafness-chain
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
        Idempotent.
        """
        self._inner.enable_force_connected()

    def inject_control_rx_bytes(self, bytes_: list[int] | bytes) -> bool:
        """Inject 3-byte chain frames into CONTROL's RX ring at
        base 0x066 (depth 48 bytes; rd at 0x098, wr at 0x099).
        Returns False if the ring is too full (>= 0x2C bytes
        pending).
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
        actually advanced.

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

        Used by the ``test_v17_shifted_full_parity`` scenario
        helpers.
        """
        self._inner.step()

    def warmup(self, cycles: int) -> None:
        """Step ``cycles`` K20-Tcy worth of universal
        ticks (each Tcy = 16 universal ticks).  Used by the
        parity-test helpers to advance past the cold-boot
        handshake before driving the scenario.
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


def apply_standby_bypass_overlay(
    chain: Chain,
    *,
    control_hex_path: "str | Path",
) -> int:
    """Patch CONTROL's program flash to NOP the standby-check
    goto at ``post_connect_init+2``, mirroring gpsim's
    ``control_disable_standby_check_dynamic`` overlay manifest.

    Spec / ledger ref: P4-followup E
    (``docs/SIM_REWRITE_RUST_PROGRESS.md`` "P4 followup tracker",
    task #103) — unblocks the rust path of
    ``test_v17_relocation::test_shifted_gpsim_with_dynamic_standby_overlay``
    plus any other rust tests that need the
    ``GpsimControlHarness(disable_standby_check=True)`` shape.

    The overlay resolves the patch site dynamically from the
    sibling ``.lst`` file (gpasm listing) of ``control_hex_path``
    via the ``post_connect_init`` symbol.  This works for both
    the byte-identical V1.7 rebuild and the 0x222-shifted V1.7,
    just like gpsim's
    :func:`dlcp_fw.sim.manifests.control_disable_standby_check_dynamic`.

    The CONTROL core is auto-discovered via :meth:`Chain.ctl`
    (which returns the chain's ``i_ctl`` slot index).  This
    closes a footgun codex flagged on commit 8283fe9 -- the
    prior signature accepted a ``control_core_idx`` parameter
    so a caller could mistakenly patch MAIN's flash instead
    of CONTROL's if the loose 4-byte opcode precondition
    happened to match there too.

    Parameters
    ----------
    chain
        The :class:`Chain` carrying the loaded CONTROL core.
    control_hex_path
        Path to the CONTROL hex used to build the chain.  The
        sibling ``.lst`` (same basename, ``.lst`` extension) is
        read for ``post_connect_init`` symbol lookup.

    Returns
    -------
    int
        The byte-addressed flash address of the patched goto
        (``post_connect_init+2``), so the caller can record it
        for diagnostics or verify the postcondition with
        :meth:`Chain.read_core_flash`.

    Raises
    ------
    KeyError
        If the sibling ``.lst`` is missing or doesn't expose
        ``post_connect_init``.  This mirrors gpsim's failure
        mode for the same overlay.

        **Stock V1.4/V1.5b/V1.6b byte-signature fallback NOT
        migrated** -- the gpsim analog
        (``control_disable_standby_check_for_hex`` lines
        213-227) walks four hard-coded byte signatures at
        addresses 0x1228 / 0x121A / 0x11DA to locate the
        goto site on stock builds.  The targeted test
        (``test_v17_relocation::
        test_shifted_gpsim_with_dynamic_standby_overlay``)
        only exercises V1.7+ which uses the symbol-lookup
        path.  Migrating the byte-signature path is tracked
        as a future P4-followup deferral; the
        :func:`Chain.patch_core_flash` primitive is generic
        enough that the fallback can be layered on top
        without further executor changes.
    AssertionError
        If the precondition fails (the 4 bytes at the patch
        site don't have the documented goto opcode shape).
    """
    from pathlib import Path
    # Local import to avoid a top-of-file cycle: this module is
    # imported from dlcp_fw/sim/__init__.py at import time, but
    # v30_symbols imports paths.py which is fine.
    from .v30_symbols import load_gpasm_symbols_for_hex

    hex_path = Path(control_hex_path)
    symbols = load_gpasm_symbols_for_hex(hex_path)
    if symbols is None or "post_connect_init" not in symbols:
        raise KeyError(
            f"apply_standby_bypass_overlay: cannot resolve "
            f"`post_connect_init` from {hex_path}'s sibling .lst.  "
            f"Either the .lst is missing or this CONTROL build is "
            f"pre-V1.7 (byte-signature path is gpsim-only -- "
            f"see this helper's docstring for the migration deferral)."
        )
    base = symbols["post_connect_init"]
    jump_addr = base + 2
    # Chain.ctl is a property (the Python wrapper), not a
    # method, so no parens.
    control_core_idx = chain.ctl
    # Precondition check: the goto opcode bytes per the gpsim
    # manifest at manifests.py:174-176.  Byte 1 = 0xEF (high
    # byte of `goto`), byte 3 = 0xF0 (continuation opcode).
    pre = chain.read_core_flash(control_core_idx, jump_addr, 4)
    assert pre[1] == 0xEF and pre[3] == 0xF0, (
        f"apply_standby_bypass_overlay: precondition failed at "
        f"0x{jump_addr:04X} on CONTROL core {control_core_idx}; "
        f"expected goto opcode bytes (? 0xEF ? 0xF0), "
        f"got {pre.hex(' ')}"
    )
    chain.patch_core_flash(control_core_idx, jump_addr, b"\x00\x00\x00\x00")
    return jump_addr


__all__ = ["Chain", "__version__", "apply_standby_bypass_overlay"]
