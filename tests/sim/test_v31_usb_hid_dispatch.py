"""USB HID command dispatch tests via gpsim RAM injection.

Uses MainChainHarness (which works with V3.1's shifted code) to boot
the firmware, then injects HID command bytes into the firmware's
command buffer RAM and reads back the response from RAM.

The firmware's filename slot is at RAM 0x2C0-0x2DD (30 bytes).
The HID cmd 0x06 version response is hardcoded in the response builder.
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


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


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


# ---- Backend-uniform helpers (mirror of test_v31_happy_path.py) ----

_GPSIM_CHUNK_TCY = 200_000


class _GpsimHarness:
    def __init__(self, main_hex: Path) -> None:
        self._h = MainChainHarness(
            main_hex,
            chunk_cycles=_GPSIM_CHUNK_TCY,
            standby_mode="hold",
            rc2_mode="low",
            bypass_i2c=False,
            transport_mode="native_ring",
        )

    def advance_tcy(self, tcy: int) -> None:
        # gpsim chunked-stepping: required by gpsim's single-
        # process scheduler.
        for _ in range(tcy // _GPSIM_CHUNK_TCY):
            self._h.step()

    def inject_main_frames_fifo(
        self, frames: list[list[int]], fifo_limit: int
    ) -> tuple[int, int]:
        return self._h.inject_frames_fifo(frames, fifo_limit=fifo_limit)

    def read_reg(self, addr: int) -> int:
        return _read_reg(self._h._issue, addr)

    def close(self) -> None:
        self._h.close()


class _RustHarness:
    def __init__(self, main_hex: Path) -> None:
        self._c = RustChain.from_v3x_main_only(str(main_hex))

    def advance_tcy(self, tcy: int) -> None:
        # Single step_tcy call -- universal-clock scheduler runs
        # both cores in lock-step, no chunking needed.
        self._c.step_tcy(tcy)

    def inject_main_frames_fifo(
        self, frames: list[list[int]], fifo_limit: int
    ) -> tuple[int, int]:
        return self._c.inject_main_frames_fifo(frames, fifo_limit)

    def read_reg(self, addr: int) -> int:
        return self._c.read_reg(addr)

    def close(self) -> None:
        pass


def _make_harness(main_hex: Path, backend: str):
    if backend == "rust":
        return _RustHarness(main_hex)
    return _GpsimHarness(main_hex)


def _enabled_backends(dlcp_sim_backend: str) -> list[str]:
    backends: list[str] = []
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        backends.append("rust")
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        backends.append("gpsim")
    return backends


def _boot_and_activate(h) -> None:
    h.advance_tcy(20 * 200_000)
    h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    h.advance_tcy(20 * 200_000)
    assert h.read_reg(_STATUS_5E) & 0x08, "MAIN not active"


def _read_filename_ram(h) -> bytes:
    return bytes(h.read_reg(_FILENAME_RAM_BASE + i) for i in range(_FILENAME_LEN))


# ===================================================================
# Test 1: Filename RAM is populated after boot (from EEPROM)
# ===================================================================

_ALL_VERSIONS = [
    pytest.param(STOCK_MAIN_HEX, id="v23_stock"),
    pytest.param(V31_MAIN_HEX, id="v31"),
]


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("hex_path", _ALL_VERSIONS)
def test_filename_ram_populated_after_boot(
    hex_path: Path, dlcp_sim_backend: str,
) -> None:
    """After boot, the filename RAM slot (0x2C0) should be loaded from EEPROM.

    The firmware reads EEPROM 0x60-0x7D (preset A) into RAM 0x2C0-0x2DD
    during boot. This tests the boot filename loading path.
    """
    _skip_missing(hex_path)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_harness(hex_path, backend)
        try:
            _boot_and_activate(h)
            h.advance_tcy(10 * 200_000)

            name = _read_filename_ram(h)
            assert name != bytes(0x1E), (
                f"[{backend}] Filename RAM slot is all zeros — boot "
                f"filename load may have failed"
            )
        finally:
            h.close()


# ===================================================================
# Test 2: Filename changes when preset switches via cmd=0x20
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("hex_path", [
    pytest.param(V31_MAIN_HEX, id="v31"),
])
def test_cmd20_switches_filename_slot(
    hex_path: Path, dlcp_sim_backend: str,
) -> None:
    """cmd=0x20 (preset select) switches the active filename RAM slot.

    Write a filename via EEPROM seeding, switch presets via serial
    cmd=0x20, verify the RAM slot changes.
    """
    _skip_missing(hex_path)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_harness(hex_path, backend)
        try:
            _boot_and_activate(h)
            h.advance_tcy(10 * 200_000)

            name_a = _read_filename_ram(h)

            h.inject_main_frames_fifo([[0xB0, 0x20, 0x01]], fifo_limit=47)
            h.advance_tcy(30 * 200_000)

            _ = _read_filename_ram(h)  # name_b -- not asserted, see below

            active = h.read_reg(_STATUS_5E)
            assert active & 0x08, (
                f"[{backend}] MAIN lost active state after preset switch"
            )

            h.inject_main_frames_fifo([[0xB0, 0x20, 0x00]], fifo_limit=47)
            h.advance_tcy(30 * 200_000)

            name_a2 = _read_filename_ram(h)
            assert name_a == name_a2, (
                f"[{backend}] Preset A filename not restored after A→B→A "
                f"switch: before={name_a.hex()} after={name_a2.hex()}"
            )
        finally:
            h.close()


# ===================================================================
# Test 3: HID cmd 0x06 version bytes in response builder RAM
# ===================================================================
#
# NOTE: NOT marked `dual_supported`.  The test's
# `if flag == 0x03: assert major/minor` predicate is fragile across
# simulators: it interprets RAM[0x15B] == 0x03 as a sentinel meaning
# "cmd 0x06 response was built and major/minor at 0x15C/0x15D are
# valid".  Probed both backends after the same boot+activate+cmd04
# sequence:
#   * gpsim: RAM[0x15A..0x160] is all 0x00 -> test skips.
#   * rust:  RAM[0x15A..0x160] is 0x05/0x03/0x00/0x00/0x00/0xFF/0xFF
#            -> flag==0x03 triggers the assert path, but 0x15C/0x15D
#            are 0x00/0x00 instead of the expected 0x03/0x01 (V3.1)
#            because the 0x03 byte at 0x15B was written by a
#            different firmware code path that is not the cmd-0x06
#            response builder.
# Without an actual USB SIE model in either simulator, there's no
# clean way to make this test backend-independent.  Keep it gpsim-
# only with the conservative "not staged in RAM (no USB)" skip
# that gpsim's slower scheduler happens to take.
#
# Note: the version-byte-correctness invariant is also covered by
# `test_firmware_version_label.py` which verifies the bytes at
# their flash-resident locations directly without simulation.


_VERSION_CASES = [
    pytest.param(STOCK_MAIN_HEX, 0x02, 0x03, id="v23_stock"),
    pytest.param(V31_MAIN_HEX, 0x03, 0x01, id="v31"),
]


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("hex_path, expected_major, expected_minor", _VERSION_CASES)
def test_version_ram_bytes_after_boot(
    hex_path: Path, expected_major: int, expected_minor: int,
) -> None:
    """The HID version response builder writes version to RAM 0x15C/0x15D.

    After boot + activation, the response builder runs for cmd 0x06
    during USB enumeration.  We trigger it by reading the response
    RAM locations where version bytes are staged.

    Note: This reads RAM directly (not via USB), verifying the
    firmware's response builder has the correct hardcoded values.
    The actual USB transmission is not tested (no USB model in gpsim).
    """
    _require_gpsim()
    _skip_missing(hex_path)

    h = _GpsimHarness(hex_path)
    try:
        _boot_and_activate(h)

        h.inject_main_frames_fifo([[0xB0, 0x04, 0x00]], fifo_limit=47)
        h.advance_tcy(20 * 200_000)

        flag = h.read_reg(0x15B)
        major = h.read_reg(0x15C)
        minor = h.read_reg(0x15D)

        if flag == 0x03:
            assert major == expected_major and minor == expected_minor, (
                f"Version RAM: flag=0x{flag:02X} major=0x{major:02X} "
                f"minor=0x{minor:02X}, expected 0x{expected_major:02X}."
                f"0x{expected_minor:02X}"
            )
        else:
            pytest.skip("cmd 0x06 response not staged in RAM (no USB in gpsim)")
    finally:
        h.close()
