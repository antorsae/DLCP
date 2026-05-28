"""Preset-page LCD stability under V1.71 health suffix updates.

The field symptom was row 2 changing from ``Active: A`` to ``    ve: A``.
That exact shape means four spaces landed at DDRAM 0x40..0x43 while the
Preset page was visible.  The health suffix updater is allowed to patch only
the row-2 tail (DDRAM 0x4C..0x4F), so these tests pin that invariant with a
real V1.71/V3.2 chain and structural guards around the suffix helper.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM, V32_MAIN_HEX
from dlcp_fw.sim.v17_symbols import assemble_v17, parse_v17_symbols


pytestmark = pytest.mark.dual_supported


try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


CONTROL_FLAGS = 0x01F
HEALTH_AGE_PB1 = 0x1B0
HEALTH_AGE_PB2 = 0x1B1
HEALTH_SEEN_MASK = 0x1B2
HEALTH_FLAGS = 0x1B3
HEALTH_DISPLAY_DIRTY = 2
HEALTH_STALE_AGE = 0x03
INTCON = 0xFF2
LCD_COMMAND_STAGE = 0x017

MAIN_DIAG_I = 0x2E5
MAIN_DIAG_R = 0x2E9

PINS = {
    "STBY": ("A", 3),
    "UP": ("C", 0),
    "DOWN": ("A", 2),
    "SELECT": ("A", 1),
    "RIGHT": ("A", 4),
    "LEFT": ("C", 5),
}


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_preset_lcd_health_suffix")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _press(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = PINS[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(5_000_000)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(5_000_000)
    for _ in range(8):
        chain.step()


def _navigate_to_preset(chain) -> None:  # type: ignore[no-untyped-def]
    for _ in range(8):
        if chain.lcd_lines()[0].rstrip() == "Preset":
            return
        _press(chain, "RIGHT")
    pytest.fail(f"did not reach Preset page; lcd={chain.lcd_lines()!r}")


def _step_until_control_pc(chain, target_pc: int, *, max_tcy: int = 1_000_000) -> None:  # type: ignore[no-untyped-def]
    for _ in range(max_tcy):
        if chain.current_ctl_pc() == target_pc:
            return
        chain.step_tcy(1)
    pytest.fail(
        f"CONTROL PC did not reach 0x{target_pc:04X}; "
        f"last=0x{chain.current_ctl_pc():04X}, lcd={chain.lcd_lines()!r}"
    )


def _force_health_suffix(
    chain, *, age_pb1: int, age_pb2: int, inject_ir_edge: bool = False
) -> None:  # type: ignore[no-untyped-def]
    chain.write_reg(HEALTH_AGE_PB1, age_pb1)
    chain.write_reg(HEALTH_AGE_PB2, age_pb2)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    if inject_ir_edge:
        chain.write_reg(CONTROL_FLAGS, chain.read_reg(CONTROL_FLAGS) | 0x01)
        chain.set_control_pin("B", 5, False)
        chain.step_tcy(2_000)
        chain.set_control_pin("B", 5, True)

    for _ in range(2_000):
        if not (chain.read_reg(HEALTH_FLAGS) & (1 << HEALTH_DISPLAY_DIRTY)):
            return
        chain.step_tcy(1_000)
    pytest.fail(f"health suffix dirty bit did not clear; lcd={chain.lcd_lines()!r}")


def test_preset_health_suffix_updates_never_touch_active_prefix(v171_hex: Path) -> None:
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(V32_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=300) < 300

    # Realistic non-clean context matching the field report: both MAINs have
    # non-zero I/R diagnostics, while CONTROL stays on the Preset UI.
    for unit in (0, 1):
        chain.write_main_reg(unit, MAIN_DIAG_I, 2)
        chain.write_main_reg(unit, MAIN_DIAG_R, 2)

    _navigate_to_preset(chain)
    assert chain.lcd_lines() == ("Preset          ", "Active: A       ")
    chain.set_blackout(True)

    prefix_before = [chain.lcd_ddram_write_count(0x40 + i) for i in range(4)]
    tail_before = [chain.lcd_ddram_write_count(0x4C + i) for i in range(4)]

    _force_health_suffix(chain, age_pb1=HEALTH_STALE_AGE, age_pb2=0)
    assert chain.lcd_lines()[1].startswith("Active: A")
    _force_health_suffix(chain, age_pb1=0, age_pb2=0, inject_ir_edge=True)
    assert chain.lcd_lines()[1] == "Active: A       "

    _force_health_suffix(chain, age_pb1=0, age_pb2=HEALTH_STALE_AGE)
    assert chain.lcd_lines()[1].startswith("Active: A")
    _force_health_suffix(chain, age_pb1=0, age_pb2=0, inject_ir_edge=True)
    assert chain.lcd_lines()[1] == "Active: A       "

    prefix_after = [chain.lcd_ddram_write_count(0x40 + i) for i in range(4)]
    tail_after = [chain.lcd_ddram_write_count(0x4C + i) for i in range(4)]

    assert prefix_after == prefix_before, (
        "health suffix updates on Preset must not rewrite row-2 cols 0..3; "
        f"before={prefix_before}, after={prefix_after}, lcd={chain.lcd_lines()!r}"
    )
    assert any(after > before for before, after in zip(tail_before, tail_after)), (
        "test did not exercise the row-2 tail suffix patch"
    )
    assert not chain.lcd_lines()[1].startswith("    ve")


def test_preset_health_suffix_mid_patch_ir_irq_keeps_cursor_at_tail(
    v171_hex: Path,
) -> None:
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(V32_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=300) < 300
    _navigate_to_preset(chain)
    assert chain.lcd_lines() == ("Preset          ", "Active: A       ")

    chain.set_blackout(True)
    chain.write_reg(HEALTH_AGE_PB1, HEALTH_STALE_AGE)
    chain.write_reg(HEALTH_AGE_PB2, 0)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    chain.write_reg(CONTROL_FLAGS, chain.read_reg(CONTROL_FLAGS) | 0x01)

    symbols = parse_v17_symbols(v171_hex.with_suffix(".lst"))
    # +4 lands after the suffix-mask calculation, immediately before the
    # LCD cursor command.  Pre-fix firmware still has GIE enabled here and an
    # RBIF/IR interrupt can corrupt access-bank LCD/scratch state; fixed
    # firmware has already masked GIE for the five-byte suffix patch.
    _step_until_control_pc(chain, symbols["v171_health_patch_have_mask"] + 4)

    chain.set_control_pin("B", 5, False)
    for _ in range(2_000_000):
        if not (chain.read_reg(HEALTH_FLAGS) & (1 << HEALTH_DISPLAY_DIRTY)):
            break
        chain.step_tcy(1)
    else:
        pytest.fail(f"health suffix dirty bit did not clear; lcd={chain.lcd_lines()!r}")
    chain.set_control_pin("B", 5, True)
    chain.step_tcy(500_000)

    assert chain.lcd_lines()[1] == "Active: A     !1"
    assert not chain.lcd_lines()[1].startswith("    ve")


def test_preset_health_suffix_clear_masks_lcd_stage_fault(
    v171_hex: Path,
) -> None:
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(V32_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=300) < 300
    _navigate_to_preset(chain)
    assert chain.lcd_lines() == ("Preset          ", "Active: A       ")

    chain.set_blackout(True)
    chain.write_reg(HEALTH_AGE_PB1, 0)
    chain.write_reg(HEALTH_AGE_PB2, 0)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    chain.write_reg(CONTROL_FLAGS, chain.read_reg(CONTROL_FLAGS) | 0x01)

    symbols = parse_v17_symbols(v171_hex.with_suffix(".lst"))
    _step_until_control_pc(chain, symbols["v171_health_patch_have_mask"] + 4)
    _step_until_control_pc(chain, symbols["lcd_command"] + 6)

    assert chain.read_reg(LCD_COMMAND_STAGE) == 0xCC
    if chain.read_reg(INTCON) & 0x80:
        # Pre-fix this patch ran with GIE enabled.  Model the interrupt/scratch
        # race implied by the field symptom: the staged LCD cursor command
        # changes from 0xCC (row-2 tail) to 0xC0 (row-2 col 0).  The following
        # four-space clear then produces exactly "    ve: A".
        chain.write_reg(LCD_COMMAND_STAGE, 0xC0)

    for _ in range(2_000_000):
        if not (chain.read_reg(HEALTH_FLAGS) & (1 << HEALTH_DISPLAY_DIRTY)):
            break
        chain.step_tcy(1)
    else:
        pytest.fail(f"health suffix dirty bit did not clear; lcd={chain.lcd_lines()!r}")
    chain.step_tcy(500_000)

    assert chain.lcd_lines()[1] == "Active: A       "


def test_health_suffix_helper_does_not_use_isr_save_scratch_or_irq_window() -> None:
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    body = text[
        text.index("v171_health_patch_suffix:") :
        text.index("; v171_health_diag_check_stale --")
    ]

    assert "v171_health_suffix_mask" in body
    assert "(Common_RAM + 4)" not in body, (
        "Common_RAM+4 is the ISR FSR0H save byte; suffix rendering must not "
        "use it as scratch across LCD calls"
    )
    assert re.search(
        r"bcf\s+INTCON,\s*GIE,\s*A.*?movlw\s+0xCC.*?call\s+lcd_command"
        r".*?bsf\s+INTCON,\s*GIE,\s*A",
        body,
        re.S,
    ), "suffix LCD cursor command + four-byte patch must run with GIE masked"
