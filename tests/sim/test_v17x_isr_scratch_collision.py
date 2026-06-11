"""ISR/foreground scratch sharing around the blocking RC5 decode (task #7).

Final mechanism (docs/V34_FIELD_BUGS_20260610.md Addendum; two earlier
hypotheses were corrected by the probes): the stock V1.6b RC5 decoder runs
BLOCKING inside the ISR (~7-10 ms from the first edge) and clobbers
access-bank scratch shared with the foreground LCD/delay helpers (0x005,
0x008, 0x00C..0x00E, the 0x010..0x013 sample buffer, 0x014/0x015).  The
V1.71 health-suffix patch knew this and GIE-MASKED its own LCD writes --
trading LCD integrity for IR deafness: an RC5 frame landing inside any
masked window latched RBIF but the blocking decoder was entered far too
late to sample the frame, so the press was silently dropped (the original
red state of these tests).  All stock LCD sections stayed unmasked, so an
IR frame mid-draw corrupted the interrupted sequence instead (the historic
LCD-glitch class, and a credible mechanism for the 2026-06-10 field
FIELD-3 row-0 blank, where the wake press arrived by IR remote).

Fix (V1.73): the ISR saves the full shared-scratch set before the decode
and restores it after the result stores; the now-purposeless GIE mask in
the health patch is retired.  IR frames decode regardless of foreground
LCD/delay activity AND the interrupted foreground state survives.  The
decode logic itself is untouched (BUG-IR-01 hardware-validated path).
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

# Whole 01D8 delay routine (staging head + decrement loop): the PC watch
# samples on a ~100-Tcy grid, so the wider window keeps the catch reliable.
DELAY_LOOP_LO = 0x01D8
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

    Pre-fix, the GIE-masked health patch made the catch land deterministically
    inside a masked delay (the deaf window).  Post-fix there is no masked
    window, so the catch retries across redraw injections until the PC lands
    in the (briefly occupied, interruptible) delay loop."""
    for attempt in range(32):
        chain.inject_control_rx_bytes(bytes([0xBF, 0x07, 0x55]))
        pc = chain.step_until_pc_hit(
            0, DELAY_LOOP_LO, DELAY_LOOP_HI, max_tcy=3_000_000
        )
        if DELAY_LOOP_LO <= pc <= DELAY_LOOP_HI:
            return (chain.read_reg(DELAY_CNT_HI) << 8) | chain.read_reg(DELAY_CNT_LO)
        # vary the re-arm phase so consecutive attempts sample different
        # alignments of the redraw against the PC-watch grid
        chain.step_ticks(8_000_000 + attempt * 700_000)
    return None


def test_rc5_decode_works_on_idle_foreground(v173_control_hex: Path) -> None:
    """Baseline pin: the real-RB5 pulse train decodes when no foreground
    delay is in flight.  Keeps the xfails below meaningful."""
    chain = _build_warmed_ir_chain(v173_control_hex)
    _prime_for_rc5_decode(chain)
    _drive_rc5_pulse_train(chain, HYPEX_ADDR, HYPEX_VOL_DOWN)
    chain.step_ticks(4_000_000)
    assert chain.read_reg(IR_DECODED_ADDR_PHYS) == HYPEX_ADDR
    assert chain.read_reg(IR_DECODED_CMD_PHYS) == HYPEX_VOL_DOWN


def test_rc5_decode_survives_foreground_delay_in_flight(
    v173_control_hex: Path,
) -> None:
    chain = _build_warmed_ir_chain(v173_control_hex)
    _prime_for_rc5_decode(chain)
    if _catch_foreground_in_delay_loop(chain) is None:
        pytest.fail("foreground never caught in the delay loop")
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


def test_foreground_delay_count_survives_blocking_isr_decode(
    v173_control_hex: Path,
) -> None:
    """Catch the foreground inside a delay with a healthy remaining count,
    fire an RB5 edge IMMEDIATELY (the blocking decode then runs in ISR
    context while the foreground is frozen), and step past the decode's
    worst-case duration.  The ISR must hand the foreground its delay count
    back intact: pre-fix the decoder's residue replaced it (observed
    0x000E -> 0x020C); post-fix the saved/restored count resumes within a
    few loop iterations of the catch value."""
    chain = _build_warmed_ir_chain(v173_control_hex)
    _prime_for_rc5_decode(chain)
    count_before = None
    for _ in range(6):
        count_before = _catch_foreground_in_delay_loop(chain)
        if count_before is not None and count_before >= 0x100:
            break
        chain.step_ticks(8_000_000)
    if count_before is None or count_before < 0x100:
        pytest.skip(
            "could not establish an in-delay catch with a long-lived count "
            "on this build's phase; the wrap itself is pinned structurally "
            "by test_isr_decode_wrap_saves_and_restores_foreground_scratch"
        )
    chain.set_control_pin("B", 5, False)   # falling edge: trap NOW
    chain.step_tcy(250_000)                # > worst-case blocking decode
    chain.set_control_pin("B", 5, True)
    count_after = (chain.read_reg(DELAY_CNT_HI) << 8) | chain.read_reg(DELAY_CNT_LO)
    pc = chain.current_ctl_pc()
    if not (DELAY_LOOP_LO <= pc <= DELAY_LOOP_HI):
        # The (restored) delay ran to completion after the decode; a
        # finished delay cannot show residue.
        return
    assert count_before - 0x80 <= count_after <= count_before, (
        "foreground delay count did not survive the blocking ISR decode "
        f"(0x{count_before:04X} -> 0x{count_after:04X})"
    )


def test_isr_decode_wrap_saves_and_restores_foreground_scratch() -> None:
    """Structural pin for the fix: the ISR must save the full foreground
    scratch set before `rcall ir_rc5_decode` and restore it after the
    result stores; the health-suffix patch must no longer mask GIE."""
    text = V173_CONTROL_ASM.read_text(encoding="utf-8", errors="replace")
    isr_idx = text.index("rcall   ir_rc5_decode")
    before = text[isr_idx - 1600 : isr_idx]
    after = text[isr_idx : isr_idx + 1600]
    for off in (5, 8, 12, 13, 14, 16, 17, 18, 19, 20, 21):
        assert f"movff   (Common_RAM + {off}), " in before, (
            f"missing ISR save of Common_RAM+{off} before the decode"
        )
        assert f" (Common_RAM + {off})" in after.split("bcf     control_flags_acc")[0], (
            f"missing ISR restore of Common_RAM+{off} after the result stores"
        )
    assert after.index("movff   (Common_RAM + 13), ir_decoded_addr") < after.index(
        "movff   v173_isr_decode_save_b2_phys + 0"
    ), "restores must run AFTER the decoded-address store (it reads 0x00D)"
    # the GIE mask in the health patch is retired
    patch_idx = text.index("v171_health_patch_have_mask")
    patch_body = text[patch_idx : patch_idx + 2400]
    assert "bcf     INTCON, GIE" not in patch_body, (
        "health-suffix patch still masks GIE (IR-deaf window)"
    )
    # codex review of 00f654b: the text pin above cannot catch a wrong or
    # overlapping save-area allocation, and the behavioral count check may
    # skip.  Verify the RESOLVED alias range and its uniqueness directly.
    import re

    inc = V17_CONTROL_RAM_INC.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r"^v173_isr_decode_save_b2_phys\s+EQU\s+0x([0-9A-Fa-f]+)", inc, re.M
    )
    assert m, "missing generated v173_isr_decode_save_b2_phys alias"
    base = int(m.group(1), 16)
    assert base == 0x260, f"save area moved: 0x{base:04X}"
    save_range = set(range(base, base + 11))
    for em in re.finditer(r"^(\w+)\s+EQU\s+0x([0-9A-Fa-f]+)", inc, re.M):
        name, value = em.group(1), int(em.group(2), 16)
        if name.startswith("v173_isr_decode_save"):
            continue
        if not name.endswith(("_b2", "_b2_phys")):
            continue
        assert value not in save_range, (
            f"{name} (0x{value:04X}) overlaps the ISR decode save area "
            f"0x{base:04X}..0x{base + 10:04X}"
        )
