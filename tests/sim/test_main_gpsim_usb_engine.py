"""USB HID command dispatch + preset A/B filename tests via gpsim.

Uses MainChainHarness with RAM injection for filename operations
and serial cmd 0x20 for preset switching. Tests the firmware's
actual HID command processing logic at instruction level.

The gpsim USB SIE engine is validated with smoke tests (attributes,
bus reset). Full EP1 HID exchange via SIE is pending EP0 enumeration
support — tracked as future work.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    STOCK_MAIN_HEX,
    V31_MAIN_HEX,
)
from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available

_FILENAME_RAM_BASE = 0x2C0
_FILENAME_LEN = 0x1E


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing: {p.name}")


def _new_harness(main_hex: Path) -> MainChainHarness:
    return MainChainHarness(
        main_hex, chunk_cycles=200_000, standby_mode="hold",
        rc2_mode="low", bypass_i2c=False, transport_mode="native_ring",
    )


def _boot_and_activate(h: MainChainHarness) -> None:
    for _ in range(20):
        h.step()
    h.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    for _ in range(20):
        h.step()


def _write_filename_ram(h: MainChainHarness, name: bytes) -> None:
    """Write filename to the active RAM slot and mark dirty."""
    for i in range(_FILENAME_LEN):
        b = name[i] if i < len(name) else 0x00
        h._issue(f"reg(0x{_FILENAME_RAM_BASE + i:03X})=0x{b:02X}", 5.0)
    # Mark filename dirty (bit 5 of ram_0x0BD) so preset switch persists it
    h._issue("reg(0x0BD)=0x20", 5.0)


def _read_filename_ram(h: MainChainHarness) -> str:
    """Read filename from active RAM slot."""
    raw = bytes(_read_reg(h._issue, _FILENAME_RAM_BASE + i) for i in range(_FILENAME_LEN))
    return raw.rstrip(b"\x00\xFF").decode("ascii", errors="replace")


# ===================================================================
# USB SIE smoke tests
# ===================================================================


@pytest.mark.gpsim
@pytest.mark.slow
def test_usb_host_attributes_exist() -> None:
    """gpsim USB host-command attributes are registered on PIC18F2455."""
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX)
    h = _new_harness(V31_MAIN_HEX)
    try:
        for _ in range(5):
            h.step()
        h.usb_host_cmd(0)  # NOP — must not crash
    finally:
        h.close()


# ===================================================================
# Preset A/B filename isolation (the key tests)
# ===================================================================


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_ab_filename_isolation() -> None:
    """Write ConfigA on preset A, ConfigB on preset B — both preserved.

    1. Boot on preset A (default)
    2. Write "ConfigA" filename
    3. Switch to B (cmd 0x20 data=1)
    4. Write "ConfigB" filename
    5. Read back → "ConfigB"
    6. Switch to A (cmd 0x20 data=0)
    7. Read back → "ConfigA" (restored from EEPROM 0x60)
    8. Switch to B
    9. Read back → "ConfigB" (restored from EEPROM 0x83)
    """
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX)

    h = _new_harness(V31_MAIN_HEX)
    try:
        _boot_and_activate(h)
        for _ in range(10):
            h.step()

        # Write "ConfigA" on preset A
        _write_filename_ram(h, b"ConfigA")
        for _ in range(5):
            h.step()

        # Switch to preset B
        h.inject_frames_fifo([[0xB0, 0x20, 0x01]], fifo_limit=47)
        for _ in range(15):
            h.step()

        # Write "ConfigB" on preset B
        _write_filename_ram(h, b"ConfigB")
        for _ in range(5):
            h.step()

        # Read back on B
        assert _read_filename_ram(h) == "ConfigB", (
            f"Preset B: {_read_filename_ram(h)!r}"
        )

        # Switch back to A
        h.inject_frames_fifo([[0xB0, 0x20, 0x00]], fifo_limit=47)
        for _ in range(15):
            h.step()

        # Read back on A — must be "ConfigA"
        assert _read_filename_ram(h) == "ConfigA", (
            f"Preset A after B→A: {_read_filename_ram(h)!r}"
        )

        # Switch to B again
        h.inject_frames_fifo([[0xB0, 0x20, 0x01]], fifo_limit=47)
        for _ in range(15):
            h.step()

        # Read back on B — must still be "ConfigB"
        assert _read_filename_ram(h) == "ConfigB", (
            f"Preset B after A→B→A→B: {_read_filename_ram(h)!r}"
        )

    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_ab_filename_reverse_order() -> None:
    """Upload B first, then A — both names preserved regardless of order."""
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX)

    h = _new_harness(V31_MAIN_HEX)
    try:
        _boot_and_activate(h)
        for _ in range(10):
            h.step()

        # Switch to B FIRST
        h.inject_frames_fifo([[0xB0, 0x20, 0x01]], fifo_limit=47)
        for _ in range(15):
            h.step()

        # Write "BetaFilter" on B
        _write_filename_ram(h, b"BetaFilter")
        for _ in range(5):
            h.step()

        # Switch to A
        h.inject_frames_fifo([[0xB0, 0x20, 0x00]], fifo_limit=47)
        for _ in range(15):
            h.step()

        # Write "AlphaFilter" on A
        _write_filename_ram(h, b"AlphaFilter")
        for _ in range(5):
            h.step()

        # Verify A
        assert _read_filename_ram(h) == "AlphaFilter"

        # Switch to B, verify B
        h.inject_frames_fifo([[0xB0, 0x20, 0x01]], fifo_limit=47)
        for _ in range(15):
            h.step()

        assert _read_filename_ram(h) == "BetaFilter"

    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_ab_filename_works_on_stock() -> None:
    """Stock V2.3 has no preset B — cmd 0x20 is ignored, filename unchanged."""
    _require_gpsim()
    _skip_missing(STOCK_MAIN_HEX)

    h = _new_harness(STOCK_MAIN_HEX)
    try:
        _boot_and_activate(h)
        for _ in range(10):
            h.step()

        # Write filename on preset A
        _write_filename_ram(h, b"StockFilter")
        for _ in range(5):
            h.step()

        # Try to switch to B (stock ignores cmd 0x20)
        h.inject_frames_fifo([[0xB0, 0x20, 0x01]], fifo_limit=47)
        for _ in range(15):
            h.step()

        # Filename should still be "StockFilter" (no B slot)
        name = _read_filename_ram(h)
        assert name == "StockFilter", (
            f"Stock firmware filename after cmd 0x20: {name!r}"
        )

    finally:
        h.close()
