"""Happy-path tests for V3.1 — must also pass on V2.3, V2.4, V2.5, V2.6.

These exercise the normal boot-to-audio flow:
  1. Boot completes and DSP preset registers are loaded
  2. Volume command reaches DSP and changes coefficient register
  3. Multiple volume changes produce different DSP states

If V3.1 fails any of these but stock versions pass, the V3.1 regression
is surfaced.
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
from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available

# ---- Helpers ----

_STATUS_5E = 0x05E


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing: {p.name}")


def _boot_harness(main_hex: Path) -> MainChainHarness:
    """Create a MainChainHarness configured for full boot + I2C."""
    return MainChainHarness(
        main_hex,
        chunk_cycles=200_000,
        standby_mode="hold",
        rc2_mode="low",
        bypass_i2c=False,
        transport_mode="native_ring",
    )


def _boot_and_activate(harness: MainChainHarness) -> None:
    for _ in range(20):
        harness.step()
    harness.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    for _ in range(20):
        harness.step()
    assert _read_reg(harness._issue, _STATUS_5E) & 0x08, "MAIN not active"


def _dsp_snapshot(harness: MainChainHarness) -> dict[int, int]:
    """Read all 256 DSP registers."""
    return {r: harness.read_i2c_regfile("dsp34", r) for r in range(256)}


def _dsp_diff(before: dict[int, int], after: dict[int, int]) -> list:
    return [(r, before[r], after[r]) for r in range(256) if before[r] != after[r]]


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


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _ALL_VERSIONS)
def test_dsp_preset_registers_nonzero_after_boot(main_hex: Path) -> None:
    """After boot + activation, DSP preset registers must have data.

    The firmware loads the DSP preset table (0x5600) into the TAS3108
    via I2C during the boot sequence.  Key DSP registers (0x37-0x45
    for the first filter bank) should be non-zero after boot.

    This catches i2c_byte_tx regressions that silently drop I2C data.
    """
    _require_gpsim()
    _skip_missing(main_hex)

    harness = _boot_harness(main_hex)
    try:
        _boot_and_activate(harness)

        # Allow preset loading to complete (happens after activation)
        for _ in range(30):
            harness.step()

        # Check DSP registers that gpsim's TAS3108 model populates during
        # preset table loading.  Empirically confirmed on stock V2.3:
        # 0x29=0x80, 0x46=0x0F, 0x55=0x0F, 0x6B=0x01, 0x91=0x80, 0xD7=0x01
        preset_regs = [0x29, 0x46, 0x55, 0x6B, 0x91, 0xD7]
        nonzero = {r: harness.read_i2c_regfile("dsp34", r) for r in preset_regs}
        nonzero_count = sum(1 for v in nonzero.values() if v != 0)

        assert nonzero_count >= 4, (
            f"Only {nonzero_count}/6 DSP preset registers non-zero after boot — "
            f"preset table not loaded via I2C. Values: "
            f"{{{', '.join(f'0x{r:02X}:0x{v:02X}' for r,v in nonzero.items())}}}"
        )

    finally:
        harness.close()


# ===================================================================
# Test 2: Volume command changes DSP coefficient register
# ===================================================================


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _ALL_VERSIONS)
def test_volume_command_changes_dsp_registers(main_hex: Path) -> None:
    """A volume command (0xB0/0x07/value) must change DSP registers.

    After boot, sending a volume command should trigger an I2C write
    to the DSP coefficient register.  The DSP register snapshot should
    differ before and after.

    This catches Fix B' (NOP'd volume commit) and i2c_byte_tx issues.
    """
    _require_gpsim()
    _skip_missing(main_hex)

    harness = _boot_harness(main_hex)
    try:
        _boot_and_activate(harness)
        for _ in range(20):
            harness.step()

        # Snapshot DSP state, send volume command, check for changes
        snap_before = _dsp_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(30):
            harness.step()
        snap_after = _dsp_snapshot(harness)

        diff = _dsp_diff(snap_before, snap_after)
        assert len(diff) > 0, (
            "Volume command 0x50 produced zero DSP register changes — "
            "volume I2C path is broken"
        )

    finally:
        harness.close()


# ===================================================================
# Test 3: Two different volume commands produce different DSP states
# ===================================================================


@pytest.mark.gpsim
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
    _require_gpsim()
    _skip_missing(main_hex)

    harness = _boot_harness(main_hex)
    try:
        _boot_and_activate(harness)
        for _ in range(20):
            harness.step()

        # First volume
        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(30):
            harness.step()
        vol1 = tuple(_read_reg(harness._issue, r) for r in (0x06E, 0x06F, 0x070, 0x071))

        # Second volume (different value)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x60]], fifo_limit=47)
        for _ in range(30):
            harness.step()
        vol2 = tuple(_read_reg(harness._issue, r) for r in (0x06E, 0x06F, 0x070, 0x071))

        assert vol1 != vol2, (
            f"Two different volume commands produced same computed_volume: "
            f"vol1={tuple(hex(v) for v in vol1)}, "
            f"vol2={tuple(hex(v) for v in vol2)} — "
            f"volume computation or commit may be broken"
        )

    finally:
        harness.close()


# ===================================================================
# Test 4: Boot volume from EEPROM is applied to DSP
# ===================================================================


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _ALL_VERSIONS)
def test_boot_volume_applied_to_dsp(main_hex: Path) -> None:
    """After boot, the EEPROM-loaded volume should be applied to DSP.

    The firmware loads volume from EEPROM[0x00-0x03] during
    main_core_service_1e88 and applies it via the volume write path.
    The DSP coefficient register (0x30) should reflect this.

    Catches issues where the boot volume isn't applied (Fix B'
    regression, boot timing issues).
    """
    _require_gpsim()
    _skip_missing(main_hex)

    harness = _boot_harness(main_hex)
    try:
        _boot_and_activate(harness)

        # Give boot volume time to be processed
        for _ in range(40):
            harness.step()

        # The EEPROM default volume is 0xA0 (from EEPROM[0x03]).
        # After boot, computed_volume (0x06E) and logical_volume (0x066)
        # should be set.
        computed = _read_reg(harness._issue, 0x06E)
        logical = _read_reg(harness._issue, 0x066)

        # Both should be non-zero (EEPROM default is 0xA0)
        assert computed != 0 or logical != 0, (
            f"Boot volume not loaded: computed=0x{computed:02X}, "
            f"logical=0x{logical:02X} — EEPROM volume init may be broken"
        )

        # Verify volume was actually written to DSP:
        # Send a DIFFERENT volume and check DSP changes
        snap = _dsp_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(30):
            harness.step()
        diff = _dsp_diff(snap, _dsp_snapshot(harness))

        assert len(diff) > 0, (
            "Volume command after boot produced no DSP changes — "
            "DSP I2C path may be broken"
        )

    finally:
        harness.close()
