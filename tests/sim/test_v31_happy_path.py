"""Happy-path tests for V3.1 — must also pass on V2.3, V2.4, V2.5, V2.6.

These exercise the normal boot-to-audio flow:
  1. Boot completes and DSP preset registers are loaded (I²C path)
  2. EEPROM-init populates volume RAM at boot
  3. Two different volume commands produce different computed_volume
     (volume computation path)

If V3.1 fails any of these but stock versions pass, the V3.1 regression
is surfaced.

Two earlier tests (`test_volume_command_changes_dsp_registers` and
the second-half DSP-diff assertion of `test_boot_volume_applied_to_dsp`)
were gpsim-only by design: they relied on gpsim's slower scheduler
keeping the preset-table I²C burst in flight when the post-volume
snapshot was taken.  The rust engine finishes preset loading earlier,
so the snapshot diff would be empty on the rust path.  Volume-cmd →
DSP-register-change observable coverage is therefore left to
`test_v31_dsp_boot_equivalence.py` (full 256-reg snapshot vs stock).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_MAIN_HEX_V24,
    PATCHED_MAIN_HEX_V26,
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


_STATUS_5E = 0x05E


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


class _RustHarness:
    """Thin rust adapter exposing the helper surface used in this file
    (advance_tcy / inject_main_frames_fifo / read_reg / read_dsp_reg)."""

    def __init__(self, main_hex: Path) -> None:
        self._c = RustChain.from_v3x_main_only(str(main_hex))

    def advance_tcy(self, tcy: int) -> None:
        self._c.step_tcy(tcy)

    def inject_main_frames_fifo(
        self, frames: list[list[int]], fifo_limit: int
    ) -> tuple[int, int]:
        return self._c.inject_main_frames_fifo(frames, fifo_limit)

    def read_reg(self, addr: int) -> int:
        return self._c.read_reg(addr)

    def read_dsp_reg(self, subaddr: int) -> int:
        return self._c.read_dsp_reg(subaddr)


def _make_harness(main_hex: Path) -> _RustHarness:
    _require_rust()
    return _RustHarness(main_hex)


def _boot_and_activate(h: _RustHarness) -> None:
    h.advance_tcy(20 * 200_000)
    h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    h.advance_tcy(20 * 200_000)
    assert h.read_reg(_STATUS_5E) & 0x08, "MAIN not active"


# ---- Firmware versions under test ----
# All happy-path tests run on STOCK + every patched version + V3.1.

_ALL_VERSIONS = [
    pytest.param(STOCK_MAIN_HEX, id="v23_stock"),
    pytest.param(PATCHED_MAIN_HEX_V24, id="v24"),
    pytest.param(PATCHED_MAIN_HEX_V26, id="v26"),
    pytest.param(V31_MAIN_HEX, id="v31"),
]


# ===================================================================
# Test 1: DSP preset registers loaded after boot
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _ALL_VERSIONS)
def test_dsp_preset_registers_nonzero_after_boot(main_hex: Path) -> None:
    """After boot + activation, DSP preset registers must have data.

    The firmware loads the DSP preset table (0x5600) into the TAS3108
    via I2C during the boot sequence.  Key DSP registers (0x37-0x45
    for the first filter bank) should be non-zero after boot.

    This catches i2c_byte_tx regressions that silently drop I2C data.
    """
    _skip_missing(main_hex)

    h = _make_harness(main_hex)
    _boot_and_activate(h)
    h.advance_tcy(30 * 200_000)

    preset_regs = [0x29, 0x46, 0x55, 0x6B, 0x91, 0xD7]
    nonzero = {r: h.read_dsp_reg(r) for r in preset_regs}
    nonzero_count = sum(1 for v in nonzero.values() if v != 0)

    assert nonzero_count >= 4, (
        f"Only {nonzero_count}/6 DSP preset registers non-zero after boot — "
        f"preset table not loaded via I2C. Values: "
        f"{{{', '.join(f'0x{r:02X}:0x{v:02X}' for r,v in nonzero.items())}}}"
    )


# ===================================================================
# Test 2: EEPROM-init populates volume RAM at boot
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _ALL_VERSIONS)
def test_boot_volume_applied_to_ram(main_hex: Path) -> None:
    """After boot, the EEPROM-loaded volume must be applied to RAM.

    The firmware loads volume from EEPROM[0x00-0x03] during
    main_core_service_1e88 and applies it via the volume write path.
    Either ``computed_volume`` (0x06E) or ``logical_volume`` (0x066)
    must be non-zero post-boot.

    Catches issues where the boot volume isn't applied (Fix B'
    regression, boot timing issues).
    """
    _skip_missing(main_hex)

    h = _make_harness(main_hex)
    _boot_and_activate(h)
    h.advance_tcy(40 * 200_000)

    computed = h.read_reg(0x06E)
    logical = h.read_reg(0x066)

    assert computed != 0 or logical != 0, (
        f"Boot volume not loaded: computed=0x{computed:02X}, "
        f"logical=0x{logical:02X} — EEPROM volume init may be broken"
    )


# ===================================================================
# Test 3: Two different volume commands produce different computed_volume
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _ALL_VERSIONS)
def test_two_volumes_produce_different_computed_volume(main_hex: Path) -> None:
    """Two different volume commands must produce different computed_volume.

    The firmware's volume computation converts serial data byte to a
    32-bit coefficient stored in computed_volume (0x06E-0x071).
    Different input values must produce different computed values.

    Note: The 8-bit DSP regfile snapshot may not distinguish two
    volume coefficients (the MSB might be the same).  So we check
    the 32-bit computed_volume in MAIN RAM instead.
    """
    _skip_missing(main_hex)

    h = _make_harness(main_hex)
    _boot_and_activate(h)
    h.advance_tcy(20 * 200_000)

    h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
    h.advance_tcy(30 * 200_000)
    vol1 = tuple(h.read_reg(r) for r in (0x06E, 0x06F, 0x070, 0x071))

    h.inject_main_frames_fifo([[0xB0, 0x07, 0x60]], fifo_limit=47)
    h.advance_tcy(30 * 200_000)
    vol2 = tuple(h.read_reg(r) for r in (0x06E, 0x06F, 0x070, 0x071))

    assert vol1 != vol2, (
        f"Two different volume commands produced same computed_volume: "
        f"vol1={tuple(hex(v) for v in vol1)}, "
        f"vol2={tuple(hex(v) for v in vol2)} — "
        f"volume computation or commit may be broken"
    )
