from __future__ import annotations

import pytest

from dlcp_fw.paths import STOCK_MAIN_COMBINED_HEX, V173_CONTROL_HEX, V35_MAIN_HEX
from dlcp_fw.flash.sim_backend import make_sim_ep0
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.main_seed import MAIN_APP_PATCH_LIMIT, MAIN_APP_PATCH_START

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_OK = True
    _RUST_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_OK = False
    _RUST_ERROR = exc


pytestmark = pytest.mark.dual_supported


FILENAME_RAM_BASE = 0x02C0
FILENAME_LEN = 0x1E
PRESET_A_EEPROM_BASE = 0x60
PRESET_B_EEPROM_BASE = 0x83
MAIN_ACTIVE_FLAGS = 0x05E
MAIN_ACTIVE_PRESET_MASK = 0x04
EVENT_FLAGS = 0x07E
EVENT_DIRTY_SERVICE = 0x01
FILENAME_DIRTY_FLAGS = 0x0BD
FILENAME_DIRTY = 0x20
FILENAME_XACT_PENDING = 0x40
BOOT_HIGH_IRQ_VECTOR = 0x0008
APP_IRQ_STUB_TARGET = 0x1008
GOTO_APP_IRQ_STUB = bytes([0x04, 0xEF, 0x08, 0xF0])
MOVFF_FSR2L_TO_ISR_SAVE = bytes([0xD9, 0xCF, 0x01, 0xF0])


def _require_rust() -> None:
    if not _RUST_OK:
        pytest.fail(f"rust facade not importable: {_RUST_ERROR!r}")


def _slot(text: str) -> bytes:
    raw = text.encode("ascii")
    assert len(raw) <= FILENAME_LEN
    return raw + bytes([0xFF]) * (FILENAME_LEN - len(raw))


def _read_main0_eeprom_slot(chain, base: int = PRESET_A_EEPROM_BASE) -> bytes:
    return bytes(chain.read_main_eeprom_byte(0, base + i) for i in range(FILENAME_LEN))


def _read_main_eeprom_slot(chain, unit: int, base: int) -> bytes:
    return bytes(chain.read_main_eeprom_byte(unit, base + i) for i in range(FILENAME_LEN))


def _read_main0_filename_ram(chain) -> bytes:
    return bytes(chain.read_main_reg(0, FILENAME_RAM_BASE + i) for i in range(FILENAME_LEN))


def _stage_main0_filename_ram(chain, slot: bytes, *, main_only: bool) -> None:
    for offset, value in enumerate(slot):
        if main_only:
            chain.write_reg(FILENAME_RAM_BASE + offset, value)
        else:
            chain.write_main_reg(0, FILENAME_RAM_BASE + offset, value)


def _set_main0_active_preset(chain, preset_b: bool) -> None:
    flags = chain.read_main_reg(0, MAIN_ACTIVE_FLAGS)
    if preset_b:
        flags |= MAIN_ACTIVE_PRESET_MASK
    else:
        flags &= ~MAIN_ACTIVE_PRESET_MASK
    chain.write_main_reg(0, MAIN_ACTIVE_FLAGS, flags)


def _force_main0_filename_persist(chain, *, main_only: bool) -> None:
    if main_only:
        chain.write_reg(FILENAME_DIRTY_FLAGS, FILENAME_DIRTY | FILENAME_XACT_PENDING)
        chain.write_reg(
            EVENT_FLAGS,
            chain.read_reg(EVENT_FLAGS) | EVENT_DIRTY_SERVICE,
        )
    else:
        chain.write_main_reg(0, FILENAME_DIRTY_FLAGS, FILENAME_DIRTY | FILENAME_XACT_PENDING)
        ep0 = make_sim_ep0(chain, unit=0)
        ep0._poke(
            EVENT_FLAGS,
            chain.read_main_reg(0, EVENT_FLAGS) | EVENT_DIRTY_SERVICE,
            in_dir=False,
        )
    chain.step_ticks(20_000_000)


def _wait_for_main0_filename_idle(chain) -> None:
    # Let boot or prior HID filename work drain before a targeted persist.
    for _ in range(20):
        if chain.read_main_reg(0, FILENAME_DIRTY_FLAGS) == 0:
            return
        chain.write_main_reg(
            0,
            EVENT_FLAGS,
            chain.read_main_reg(0, EVENT_FLAGS) | EVENT_DIRTY_SERVICE,
        )
        chain.step_ticks(5_000_000)
    assert chain.read_main_reg(0, FILENAME_DIRTY_FLAGS) == 0


def _persist_main0_filename(chain, slot: bytes, *, preset_b: bool) -> None:
    _set_main0_active_preset(chain, preset_b)
    _stage_main0_filename_ram(chain, slot, main_only=False)
    assert _read_main0_filename_ram(chain) == slot
    _force_main0_filename_persist(chain, main_only=False)
    assert _read_main0_filename_ram(chain) == slot
    assert chain.read_main_reg(0, FILENAME_DIRTY_FLAGS) == 0


def _seeded_main_bytes() -> dict[int, int]:
    merged = dict(parse_intel_hex(STOCK_MAIN_COMBINED_HEX))
    for addr, value in parse_intel_hex(V35_MAIN_HEX).items():
        if MAIN_APP_PATCH_START <= addr < MAIN_APP_PATCH_LIMIT:
            merged[addr] = value
    return merged


def test_v35_seeded_boot_irq_vector_targets_fsr2l_save_word() -> None:
    """Static root-cause guard for the full-chain EEPROM repro.

    The stock bootloader high interrupt vector preserved in seeded V3.x
    images jumps to byte address 0x1008. That address must start the
    ``movff FSR2L,isr_save_fsr2l`` instruction, otherwise UART RX interrupts
    restore a stale low byte after using FSR2 for the RX ring.
    """
    image = _seeded_main_bytes()
    assert bytes(image.get(BOOT_HIGH_IRQ_VECTOR + i, 0xFF) for i in range(4)) == (
        GOTO_APP_IRQ_STUB
    )
    assert bytes(image.get(APP_IRQ_STUB_TARGET + i, 0xFF) for i in range(4)) == (
        MOVFF_FSR2L_TO_ISR_SAVE
    )


def test_v35_main_only_filename_force_persist_is_byte_exact() -> None:
    """Control case: without CONTROL chain traffic, forced filename persist
    writes the staged 0x02C0..0x02DD RAM slot byte-exactly to EEPROM.
    """
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(V35_MAIN_HEX))
    chain.step_ticks(2_000_000_000)
    expected = _slot("LX521.4 22MG10F-v5")

    _stage_main0_filename_ram(chain, expected, main_only=True)
    _force_main0_filename_persist(chain, main_only=True)

    assert _read_main0_eeprom_slot(chain) == expected
    assert chain.read_reg(FILENAME_DIRTY_FLAGS) == 0


def test_v35_full_chain_filename_force_persist_is_byte_exact() -> None:
    """Regression repro for the live NUL symptom.

    The staged filename RAM must remain correct and EEPROM A must persist the
    same bytes after the dirty-service persist runs in the full CONTROL+MAIN
    chain.
    """
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX),
        main_hex_path=str(V35_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=400) < 400
    chain.step_ticks(50_000_000)
    expected = _slot("LX521.4 22MG10F-v5")

    # Let boot-time settings dirty work finish, then stage only filename work.
    for _ in range(20):
        if chain.read_main_reg(0, FILENAME_DIRTY_FLAGS) == 0:
            break
        chain.write_main_reg(
            0,
            EVENT_FLAGS,
            chain.read_main_reg(0, EVENT_FLAGS) | EVENT_DIRTY_SERVICE,
        )
        chain.step_ticks(5_000_000)
    assert chain.read_main_reg(0, FILENAME_DIRTY_FLAGS) == 0

    _stage_main0_filename_ram(chain, expected, main_only=False)
    assert _read_main0_filename_ram(chain) == expected
    _force_main0_filename_persist(chain, main_only=False)

    assert _read_main0_filename_ram(chain) == expected
    observed = _read_main0_eeprom_slot(chain)
    assert observed == expected, (
        "EEPROM A filename changed during full-chain force persist:\n"
        f"  observed={observed.hex()} {observed!r}\n"
        f"  expected={expected.hex()} {expected!r}"
    )
    assert chain.read_main_reg(0, FILENAME_DIRTY_FLAGS) == 0


def test_v35_full_chain_filename_eeprom_a_b_survive_churn_and_power_cycle() -> None:
    """Persistent-state invariant for the missed bug category.

    A release finalize or HID filename write must preserve both preset filename
    EEPROM slots byte-for-byte through A/B updates, menu churn, and reset. This
    is intentionally persistent-state-first; LCD correctness alone missed the
    field failure.
    """
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX),
        main_hex_path=str(V35_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=400) < 400
    chain.step_ticks(50_000_000)
    _wait_for_main0_filename_idle(chain)

    slot_a = _slot("LX521.4 22MG10F-v5")
    slot_b = _slot("LX521.4 22MG10F-v7")
    _persist_main0_filename(chain, slot_a, preset_b=False)
    assert _read_main_eeprom_slot(chain, 0, PRESET_A_EEPROM_BASE) == slot_a

    _persist_main0_filename(chain, slot_b, preset_b=True)
    assert _read_main_eeprom_slot(chain, 0, PRESET_B_EEPROM_BASE) == slot_b

    for key in ("RIGHT", "RIGHT", "LEFT", "RIGHT", "LEFT"):
        chain.press(key)
        chain.step_ticks(8_000_000)
    chain.step_ticks(80_000_000)
    assert _read_main_eeprom_slot(chain, 0, PRESET_A_EEPROM_BASE) == slot_a
    assert _read_main_eeprom_slot(chain, 0, PRESET_B_EEPROM_BASE) == slot_b

    chain.apply_reset_all("por")
    assert chain.run_until_connected(limit=400) < 400
    chain.step_ticks(50_000_000)
    assert _read_main_eeprom_slot(chain, 0, PRESET_A_EEPROM_BASE) == slot_a
    assert _read_main_eeprom_slot(chain, 0, PRESET_B_EEPROM_BASE) == slot_b
