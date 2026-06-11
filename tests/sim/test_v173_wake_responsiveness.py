"""Wake-to-responsive bound for the V1.73+V3.4 chain.

Root cause pinned in docs/analysis/CONNECTED_WAITING_WAKE_DELAY_2026-06-10.md:
the stock V1.6b WAITING entries block in open-loop banner delays (wake path
``0x1388`` ~= 14 s, cold path ``0x0FA0`` ~= 11 s) before entering the
closed-loop WAITING loops, leaving the foreground dead (no polls, no parser,
no buttons, no IR re-arm) while the LCD shows ``Waiting for DLCP`` with the
conn bit set.  With the delays removed, the evidence-driven loops own the
wait, so wake-to-responsive is bounded by the MAIN wake bring-up (~8 s of
``adc_boot_gate`` rail settle + blocking DSP table apply) instead of the
~14 s banner delay.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    V17_CONTROL_RAM_INC,
    V173_CONTROL_ASM,
    V34_MAIN_ASM,
)
from dlcp_fw.sim.v17_symbols import assemble_v17
from dlcp_fw.sim.v30_symbols import assemble_v30

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    RustChain = None  # type: ignore[assignment]
    _RUST_CHAIN_IMPORT_ERROR = exc

VOLUME_CACHE = 0x0B9
IR_ADDR_HYPEX = 0x10
IR_CMD_HYPEX_VOLUME_UP = 0x33

# Wake-to-responsive ceiling.  Pre-fix the wake banner delay alone holds the
# foreground for ~223M ticks (~14 s); post-fix the bound is the MAIN wake
# bring-up (~115M ticks observed) plus one reconnect poll round-trip.
WAKE_RESPONSIVE_BOUND_TICKS = 160_000_000  # 10 s
PROBE_SLICE_TICKS = 2_000_000
PROBE_SLICES = 140  # 280M-tick hard stop so a regression fails, not hangs
COMMAND_SETTLE_TICKS = 12_000_000


def _require_rust() -> None:
    if RustChain is None:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


@pytest.fixture(scope="module")
def wake_chain_hexes(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    tmp = tmp_path_factory.mktemp("v173_wake_responsiveness")
    shutil.copy(V17_CONTROL_RAM_INC, tmp / V17_CONTROL_RAM_INC.name)
    control_asm = tmp / V173_CONTROL_ASM.name
    control_asm.write_bytes(V173_CONTROL_ASM.read_bytes())
    control_hex = tmp / "DLCP_Control_V1.73_wake.hex"
    assemble_v17(control_asm, control_hex)
    main_hex = tmp / "DLCP_Firmware_V3.4_wake.hex"
    assemble_v30(V34_MAIN_ASM, main_hex, output_lst=tmp / "DLCP_Firmware_V3.4_wake.lst")
    return control_hex, main_hex


def test_v173_v34_wake_to_responsive_under_bound(
    wake_chain_hexes: tuple[Path, Path],
) -> None:
    _require_rust()
    control_hex, main_hex = wake_chain_hexes
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    assert chain.run_until_connected(limit=300) < 300
    assert chain.is_connected() and not chain.is_waiting()

    chain.press("STBY")
    assert "ZZZ" in chain.lcd_lines()[0].upper(), chain.lcd_lines()

    wake_start = chain.current_tick()
    chain.press("STBY")
    for _ in range(PROBE_SLICES):
        if not chain.is_waiting() and chain.lcd_lines()[0].startswith("Volume"):
            break
        chain.step_ticks(PROBE_SLICE_TICKS)
    elapsed = chain.current_tick() - wake_start

    assert not chain.is_waiting(), (
        f"chain still WAITING {elapsed:,} ticks after wake; lcd={chain.lcd_lines()!r}"
    )
    assert chain.lcd_lines()[0].startswith("Volume"), chain.lcd_lines()
    assert elapsed <= WAKE_RESPONSIVE_BOUND_TICKS, (
        f"wake-to-responsive took {elapsed:,} ticks "
        f"(bound {WAKE_RESPONSIVE_BOUND_TICKS:,}); the WAITING-entry banner "
        "delay is blocking the foreground again"
    )

    # End-to-end responsiveness: the first IR key after recovery must work
    # (the WAITING window must leave IR_ARMED usable).
    vol_before = chain.read_reg(VOLUME_CACHE)
    chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=IR_CMD_HYPEX_VOLUME_UP)
    chain.step_ticks(COMMAND_SETTLE_TICKS)
    assert chain.read_reg(VOLUME_CACHE) == ((vol_before + 1) & 0xFF), (
        "IR volume key dead after wake recovery"
    )


MAIN_ACTIVE_FLAGS = 0x05E
MAIN_GATE_MASK = 0x08
# Measured 2026-06-11 on the canonical pair, edge-anchored and sampled
# THROUGH the press hold: the LOGICAL gates open within a few M ticks of
# the press edge (the wake handler sets them long before the MAINs are
# actually ready), so "after gates" is effectively the whole wake
# bring-up -- the blocking DSP cold-init plus the reconnect fresh-status
# handshake, measured ~115M ticks.  Both bounds therefore sit at the
# established 160M wake-to-responsive budget; the contract's value is
# that WAITING can never outlive that budget while both gates are up.
WAITING_EXIT_AFTER_GATES_BOUND_TICKS = 160_000_000
WAKE_TO_WAITING_EXIT_BOUND_TICKS = 160_000_000


def test_v173_connected_waiting_exit_bound_after_wake(
    wake_chain_hexes: tuple[Path, Path],
) -> None:
    """Exit-bound contract for the exploratory "connected WAITING" class:
    once both MAIN gates are up during a wake-triggered WAITING, CONTROL
    must exit WAITING within a fixed small bound -- WAITING may only ever
    be as long as the slowest MAIN's bring-up, never an open-ended UI
    state.  This converts the seed-dependent exploratory observation
    counts (86/23 in run 20260611_100415) into a deterministic pass/fail
    contract, exercised across two consecutive standby/wake cycles."""
    _require_rust()
    control_hex, main_hex = wake_chain_hexes
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex),
        main_hex_path=str(main_hex),
    )
    assert chain.run_until_connected(limit=300) < 300
    chain.step_ticks(30_000_000)

    for cycle in range(2):
        chain.press("STBY")
        # Drive the wake press at the PIN level so wake_tick anchors the
        # actual press edge: chain.press() advances ~100M ticks internally
        # (hold+settle), which would hide any WAITING window that starts
        # and clears inside the helper (codex review of f88fb95).
        chain.set_control_pin("A", 3, False)
        wake_tick = chain.current_tick()
        gates_up_tick = None
        exit_tick = None
        # Sample THROUGH the 50M-tick hold (codex review of ce67fa8: the
        # gates can come up during the hold, so sampling only after the
        # release would inflate gates_up_tick by up to the hold duration).
        for step in range(200):
            if step == 50:
                chain.set_control_pin("A", 3, True)
            chain.step_ticks(1_000_000)
            gates_up = all(
                chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) & MAIN_GATE_MASK
                for unit in (0, 1)
            )
            if gates_up and gates_up_tick is None:
                gates_up_tick = chain.current_tick()
            if gates_up_tick is not None and not chain.is_waiting():
                exit_tick = chain.current_tick()
                break
        assert gates_up_tick is not None, f"cycle {cycle}: MAIN gates never opened"
        assert exit_tick is not None, (
            f"cycle {cycle}: WAITING never exited after both gates were up "
            f"(gates_up at +{(gates_up_tick - wake_tick) / 1e6:.0f}M)"
        )
        after_gates = exit_tick - gates_up_tick
        total = exit_tick - wake_tick
        assert after_gates <= WAITING_EXIT_AFTER_GATES_BOUND_TICKS, (
            f"cycle {cycle}: WAITING lingered {after_gates / 1e6:.0f}M ticks "
            f"after both gates were up (bound "
            f"{WAITING_EXIT_AFTER_GATES_BOUND_TICKS / 1e6:.0f}M)"
        )
        assert total <= WAKE_TO_WAITING_EXIT_BOUND_TICKS, (
            f"cycle {cycle}: wake->WAITING-exit took {total / 1e6:.0f}M ticks "
            f"(bound {WAKE_TO_WAITING_EXIT_BOUND_TICKS / 1e6:.0f}M)"
        )
        chain.step_ticks(40_000_000)   # settle before the next cycle


def test_v173_waiting_entries_have_no_blocking_banner_delay() -> None:
    """Structural pin: the two WAITING entries must not re-grow an open-loop
    `control_core_service_01BE` banner delay; the loops own the wait."""
    text = V173_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")

    def window_before(label: str, span: int = 1200) -> str:
        idx = text.index(f"\n{label}:")
        return text[max(0, idx - span) : idx]

    cold_entry = window_before("flow_ccs_0FA0_118C")
    wake_entry = window_before("reconnect_wait_loop")
    for name, body in {"cold": cold_entry, "wake": wake_entry}.items():
        assert "call    control_core_service_01BE" not in body, (
            f"{name} WAITING entry re-introduced a blocking banner delay"
        )
