"""Stock-latent ISR/foreground scratch collision on 0x00C/0x00D (task #7).

Found during the FIELD-3 forensics (docs/V34_FIELD_BUGS_20260610.md
Addendum): the in-ISR RC5 decoder uses ``Common_RAM+12/13`` (0x00C/0x00D)
as its per-edge timing scratch (and, after the timing phase, as the
address/command accumulators), while every foreground delay
(``control_core_service_01D8``) decrements the very same cells in place.
When an IR edge interrupts a foreground delay loop the two writers
interleave, deterministically reproduced in sim:

- Direction 2 (user-visible): the in-flight foreground count corrupts the
  decoder's edge timing and the frame FAILS TO DECODE -- the remote press
  is silently dropped.  On an idle foreground the same train decodes fine,
  which is why the field symptom is "remote is flaky while the display is
  busy".
- Direction 1: the decoder's residue corrupts the interrupted delay's
  remaining count (observed 0x0019 -> 0x0205, a ~20x inflation), i.e. LCD
  timing distortion on real hardware.

Present in stock V1.6b and carried into V1.7x by the byte-faithful
rewrite.  The strict xfails below define the fix contract (save/restore
the shared scratch around the ISR decode, or give the decoder dedicated
cells) without touching the hardware-validated decode logic assertions:
the baseline test pins that the decoder itself still works.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V173_CONTROL_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17
from tests.sim.test_v171_ir_rc5_pulse_train import (
    IR_DECODED_ADDR_PHYS,
    IR_DECODED_CMD_PHYS,
    _build_warmed_ir_chain,
    _drive_rc5_pulse_train,
    _prime_for_rc5_decode,
)

HYPEX_ADDR = 0x10
# Distinct from the address byte so an addr/cmd swap or mirror cannot
# satisfy the decode assertions by accident (codex review of 6aef4da).
HYPEX_VOL_DOWN = 0x11

DELAY_LOOP_LO = 0x01E2
DELAY_LOOP_HI = 0x01EE
DELAY_CNT_LO = 0x00C
DELAY_CNT_HI = 0x00D


@pytest.fixture(scope="module")
def v173_control_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v17x_isr_scratch")
    shutil.copy(V17_CONTROL_RAM_INC, tmp / V17_CONTROL_RAM_INC.name)
    asm = tmp / V173_CONTROL_ASM.name
    asm.write_bytes(V173_CONTROL_ASM.read_bytes())
    hex_out = tmp / "DLCP_Control_V1.73_isr_scratch.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _catch_foreground_in_delay_loop(chain) -> int:
    """Trigger a real LCD update (BF/07 volume echo -> digit redraw) and
    stop with the foreground PC inside the 01D8 decrement loop.  Returns
    the 16-bit remaining delay count at the stop point.

    A first full redraw runs and settles beforehand: the collision is
    phase-dependent (which delay site / how much count remains when the
    first IR edge lands), and this warm-up pins the deterministic phase
    that reproduces the 2026-06-11 probe (caught at remaining count
    0x0019, decode dropped, residue 0x0205)."""
    chain.inject_control_rx_bytes(bytes([0xBF, 0x07, 0x55]))
    chain.step_ticks(8_000_000)
    chain.inject_control_rx_bytes(bytes([0xBF, 0x07, 0x55]))
    pc = chain.step_until_pc_hit(0, DELAY_LOOP_LO, DELAY_LOOP_HI, max_tcy=3_000_000)
    assert DELAY_LOOP_LO <= pc <= DELAY_LOOP_HI, (
        f"foreground not caught in the delay loop (pc={pc:#06x}); "
        "fixture assumption broken"
    )
    return (chain.read_reg(DELAY_CNT_HI) << 8) | chain.read_reg(DELAY_CNT_LO)


def test_rc5_decode_works_on_idle_foreground(v173_control_hex: Path) -> None:
    """Baseline pin: the real-RB5 pulse train decodes when no foreground
    delay is in flight.  Keeps the xfails below meaningful."""
    chain = _build_warmed_ir_chain(v173_control_hex)
    _prime_for_rc5_decode(chain)
    _drive_rc5_pulse_train(chain, HYPEX_ADDR, HYPEX_VOL_DOWN)
    chain.step_ticks(4_000_000)
    assert chain.read_reg(IR_DECODED_ADDR_PHYS) == HYPEX_ADDR
    assert chain.read_reg(IR_DECODED_CMD_PHYS) == HYPEX_VOL_DOWN


@pytest.mark.xfail(
    reason=(
        "stock-latent 0x00C/0x00D scratch collision: an RC5 frame arriving "
        "while the foreground sits in a 01D8 delay loop fails to decode "
        "(the in-flight delay count corrupts the decoder's edge timing) -- "
        "the remote press is silently dropped"
    ),
    strict=True,
)
def test_rc5_decode_survives_foreground_delay_in_flight(
    v173_control_hex: Path,
) -> None:
    chain = _build_warmed_ir_chain(v173_control_hex)
    _prime_for_rc5_decode(chain)
    _catch_foreground_in_delay_loop(chain)
    _drive_rc5_pulse_train(chain, HYPEX_ADDR, HYPEX_VOL_DOWN)
    chain.step_ticks(4_000_000)
    got = (
        chain.read_reg(IR_DECODED_ADDR_PHYS),
        chain.read_reg(IR_DECODED_CMD_PHYS),
    )
    assert got == (HYPEX_ADDR, HYPEX_VOL_DOWN), (
        "IR frame dropped while the foreground was mid-delay: "
        f"decoded addr/cmd = 0x{got[0]:02X}/0x{got[1]:02X}"
    )


@pytest.mark.xfail(
    reason=(
        "stock-latent 0x00C/0x00D scratch collision: the ISR decoder's "
        "residue rewrites the interrupted foreground delay's remaining "
        "count (observed 0x0019 -> 0x0205, ~20x inflation) -- LCD timing "
        "distortion on real hardware"
    ),
    strict=True,
)
def test_foreground_delay_count_never_inflated_by_ir_isr(
    v173_control_hex: Path,
) -> None:
    chain = _build_warmed_ir_chain(v173_control_hex)
    _prime_for_rc5_decode(chain)
    count_before = _catch_foreground_in_delay_loop(chain)
    _drive_rc5_pulse_train(chain, HYPEX_ADDR, HYPEX_VOL_DOWN)
    count_after = (chain.read_reg(DELAY_CNT_HI) << 8) | chain.read_reg(DELAY_CNT_LO)
    pc = chain.current_ctl_pc()
    if not (DELAY_LOOP_LO <= pc <= DELAY_LOOP_HI):
        # The delay legitimately finished during the ~25 ms train; a
        # completed delay cannot have been inflated.
        return
    assert count_after <= count_before, (
        "interrupted foreground delay count INCREASED across the IR frame "
        f"(0x{count_before:04X} -> 0x{count_after:04X}): ISR scratch residue"
    )
