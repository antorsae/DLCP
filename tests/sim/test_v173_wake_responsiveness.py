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
