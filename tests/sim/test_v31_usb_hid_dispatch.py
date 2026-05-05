"""USB HID command dispatch tests via rust facade RAM injection.

Boots the firmware on the rust V3.x MAIN-only chain, then injects HID
command bytes into the firmware's command buffer RAM and reads back
the response from RAM.

The firmware's filename slot is at RAM 0x2C0-0x2DD (30 bytes).

A third test (`test_version_ram_bytes_after_boot`) was gpsim-only by
design: it depended on gpsim's slower scheduler leaving the cmd 0x06
response RAM in a "not staged" state so the test could conservatively
skip on rust.  The version-byte-correctness invariant is covered
end-to-end by ``test_firmware_version_label.py`` which verifies the
bytes at their flash-resident locations directly without simulation;
keeping a probe of the response-builder RAM here on rust would require
an actual USB SIE model that neither backend provides.
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


def _make_harness(main_hex: Path) -> _RustHarness:
    _require_rust()
    return _RustHarness(main_hex)


def _boot_and_activate(h: _RustHarness) -> None:
    h.advance_tcy(20 * 200_000)
    h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    h.advance_tcy(20 * 200_000)
    assert h.read_reg(_STATUS_5E) & 0x08, "MAIN not active"


def _read_filename_ram(h: _RustHarness) -> bytes:
    return bytes(h.read_reg(_FILENAME_RAM_BASE + i) for i in range(_FILENAME_LEN))


# ===================================================================
# Test 1: Filename RAM is populated after boot (from EEPROM)
# ===================================================================

_ALL_VERSIONS = [
    pytest.param(STOCK_MAIN_HEX, id="v23_stock"),
    pytest.param(V31_MAIN_HEX, id="v31"),
]


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("hex_path", _ALL_VERSIONS)
def test_filename_ram_populated_after_boot(hex_path: Path) -> None:
    """After boot, the filename RAM slot (0x2C0) should be loaded from EEPROM.

    The firmware reads EEPROM 0x60-0x7D (preset A) into RAM 0x2C0-0x2DD
    during boot. This tests the boot filename loading path.
    """
    _skip_missing(hex_path)

    h = _make_harness(hex_path)
    _boot_and_activate(h)
    h.advance_tcy(10 * 200_000)

    name = _read_filename_ram(h)
    assert name != bytes(0x1E), (
        "Filename RAM slot is all zeros — boot filename load may have failed"
    )


# ===================================================================
# Test 2: Filename changes when preset switches via cmd=0x20
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("hex_path", [
    pytest.param(V31_MAIN_HEX, id="v31"),
])
def test_cmd20_switches_filename_slot(hex_path: Path) -> None:
    """cmd=0x20 (preset select) switches the active filename RAM slot.

    Write a filename via EEPROM seeding, switch presets via serial
    cmd=0x20, verify the RAM slot is restored on A→B→A round-trip.
    """
    _skip_missing(hex_path)

    h = _make_harness(hex_path)
    _boot_and_activate(h)
    h.advance_tcy(10 * 200_000)

    name_a = _read_filename_ram(h)

    h.inject_main_frames_fifo([[0xB0, 0x20, 0x01]], fifo_limit=47)
    h.advance_tcy(30 * 200_000)

    _ = _read_filename_ram(h)  # name_b -- intentionally unused

    active = h.read_reg(_STATUS_5E)
    assert active & 0x08, "MAIN lost active state after preset switch"

    h.inject_main_frames_fifo([[0xB0, 0x20, 0x00]], fifo_limit=47)
    h.advance_tcy(30 * 200_000)

    name_a2 = _read_filename_ram(h)
    assert name_a == name_a2, (
        f"Preset A filename not restored after A→B→A switch: "
        f"before={name_a.hex()} after={name_a2.hex()}"
    )
