"""USB HID command dispatch + preset A/B filename tests.

Three tests verify firmware behavior on RAM-write + preset-switch
sequences (filename A/B isolation under cmd 0x20).

A fourth gpsim-only test (`test_usb_host_attributes_exist`)
verified gpsim's USB host SIE attributes -- no rust analogue, so
that test was deleted in PF.4 phase 2 batch 5.  The full EP1 HID
exchange via SIE remains future work tracked separately.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    STOCK_MAIN_HEX,
    V31_MAIN_HEX,
)

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


_FILENAME_RAM_BASE = 0x2C0
_FILENAME_LEN = 0x1E

# Per-phase MAIN-Tcy advancement.
_BOOT_TCY = 4_000_000
_ACTIVATE_TCY = 4_000_000
_FILENAME_WRITE_TCY = 1_000_000
_PRESET_SWITCH_TCY = 6_000_000
_LONG_PRESET_TCY = 12_000_000


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing: {p.name}")


class _RustBackend:
    """Thin rust adapter exposing the helper surface used in this file."""

    def __init__(self, main_hex: Path):
        self._c = RustChain.from_v3x_main_only(str(main_hex))

    def boot_and_activate(self) -> None:
        self._c.step_tcy(_BOOT_TCY)
        self._c.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
        self._c.step_tcy(_ACTIVATE_TCY)

    def step_tcy(self, tcy: int) -> None:
        self._c.step_tcy(tcy)

    def write_filename(self, name: bytes) -> None:
        for i in range(_FILENAME_LEN):
            b = name[i] if i < len(name) else 0x00
            self._c.write_reg(_FILENAME_RAM_BASE + i, b)
        # Mark filename dirty (bit 5 of ram_0x0BD) so preset switch
        # persists it.
        self._c.write_reg(0x0BD, 0x20)

    def read_filename(self) -> str:
        raw = bytes(
            self._c.read_reg(_FILENAME_RAM_BASE + i)
            for i in range(_FILENAME_LEN)
        )
        return raw.rstrip(b"\x00\xFF").decode("ascii", errors="replace")

    def inject_frame(self, frame: list[int]) -> None:
        self._c.inject_main_frames_fifo([frame], fifo_limit=47)


def _make_backend(main_hex: Path) -> _RustBackend:
    _require_rust()
    return _RustBackend(main_hex)


# ===================================================================
# Preset A/B filename isolation
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
def test_preset_ab_filename_isolation() -> None:
    """Write ConfigA on preset A, ConfigB on preset B -- both preserved.

    1. Boot on preset A (default)
    2. Write "ConfigA" filename
    3. Switch to B (cmd 0x20 data=1)
    4. Write "ConfigB" filename
    5. Read back -> "ConfigB"
    6. Switch to A (cmd 0x20 data=0)
    7. Read back -> "ConfigA" (restored from EEPROM 0x60)
    8. Switch to B
    9. Read back -> "ConfigB" (restored from EEPROM 0x83)
    """
    _skip_missing(V31_MAIN_HEX)
    bk = _make_backend(V31_MAIN_HEX)
    bk.boot_and_activate()
    bk.step_tcy(2_000_000)

    # Write "ConfigA" on preset A
    bk.write_filename(b"ConfigA")
    bk.step_tcy(_FILENAME_WRITE_TCY)

    # Switch to preset B
    bk.inject_frame([0xB0, 0x20, 0x01])
    bk.step_tcy(_PRESET_SWITCH_TCY)

    # Write "ConfigB" on preset B
    bk.write_filename(b"ConfigB")
    bk.step_tcy(_FILENAME_WRITE_TCY)

    # Read back on B
    assert bk.read_filename() == "ConfigB", (
        f"Preset B: {bk.read_filename()!r}"
    )

    # Switch back to A
    bk.inject_frame([0xB0, 0x20, 0x00])
    bk.step_tcy(_PRESET_SWITCH_TCY)

    # Read back on A — must be "ConfigA"
    assert bk.read_filename() == "ConfigA", (
        f"Preset A after B->A: {bk.read_filename()!r}"
    )

    # Switch to B again
    bk.inject_frame([0xB0, 0x20, 0x01])
    bk.step_tcy(_PRESET_SWITCH_TCY)

    # Read back on B — must still be "ConfigB"
    assert bk.read_filename() == "ConfigB", (
        f"Preset B after A->B->A->B: {bk.read_filename()!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_preset_ab_filename_reverse_order() -> None:
    """Upload B first, then A -- both names preserved regardless of order."""
    _skip_missing(V31_MAIN_HEX)
    bk = _make_backend(V31_MAIN_HEX)
    bk.boot_and_activate()
    bk.step_tcy(2_000_000)

    # Switch to B FIRST
    bk.inject_frame([0xB0, 0x20, 0x01])
    bk.step_tcy(_PRESET_SWITCH_TCY)

    # Write "BetaFilter" on B
    bk.write_filename(b"BetaFilter")
    bk.step_tcy(4_000_000)

    # Switch to A (persists B's filename to EEPROM 0x83)
    bk.inject_frame([0xB0, 0x20, 0x00])
    bk.step_tcy(_LONG_PRESET_TCY)

    # Write "AlphaFilter" on A
    bk.write_filename(b"AlphaFilter")
    bk.step_tcy(4_000_000)

    # Verify A
    assert bk.read_filename() == "AlphaFilter", (
        f"Preset A: {bk.read_filename()!r}"
    )

    # Switch to B, verify B
    bk.inject_frame([0xB0, 0x20, 0x01])
    bk.step_tcy(_PRESET_SWITCH_TCY)
    assert bk.read_filename() == "BetaFilter", (
        f"Preset B: {bk.read_filename()!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_preset_ab_filename_works_on_stock() -> None:
    """Stock V2.3 has no preset B -- cmd 0x20 is ignored, filename unchanged."""
    _skip_missing(STOCK_MAIN_HEX)
    bk = _make_backend(STOCK_MAIN_HEX)
    bk.boot_and_activate()
    bk.step_tcy(2_000_000)

    # Write filename on preset A
    bk.write_filename(b"StockFilter")
    bk.step_tcy(_FILENAME_WRITE_TCY)

    # Try to switch to B (stock ignores cmd 0x20)
    bk.inject_frame([0xB0, 0x20, 0x01])
    bk.step_tcy(_PRESET_SWITCH_TCY)

    # Filename should still be "StockFilter" (no B slot)
    name = bk.read_filename()
    assert name == "StockFilter", (
        f"Stock firmware filename after cmd 0x20: {name!r}"
    )
