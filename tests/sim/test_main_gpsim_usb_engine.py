"""USB HID command dispatch + preset A/B filename tests.

Three tests verify firmware behavior on RAM-write + preset-switch
sequences (filename A/B isolation under cmd 0x20).  These have
been migrated to dual_supported in P4.7.

One test (`test_usb_host_attributes_exist`) verifies gpsim's USB
host SIE attributes -- a gpsim-specific feature with no rust
analog -- and stays gpsim-only.

The gpsim USB SIE engine is validated with smoke tests
(attributes, bus reset).  Full EP1 HID exchange via SIE is
pending EP0 enumeration support -- tracked as future work.
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

# Per-phase MAIN-Tcy advancement (~established native_ring template).
_BOOT_TCY = 4_000_000      # 20 chunks × 200K
_ACTIVATE_TCY = 4_000_000  # 20 chunks × 200K
_FILENAME_WRITE_TCY = 1_000_000  # 5 chunks
_PRESET_SWITCH_TCY = 6_000_000   # 30 chunks (preset switch + EEPROM commit)
_LONG_PRESET_TCY = 12_000_000    # 60 chunks (after first switch on stock A)


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


def _new_harness_gpsim(main_hex: Path) -> MainChainHarness:
    return MainChainHarness(
        main_hex, chunk_cycles=200_000, standby_mode="hold",
        rc2_mode="low", bypass_i2c=False, transport_mode="native_ring",
    )


def _boot_and_activate_gpsim(h: MainChainHarness) -> None:
    for _ in range(_BOOT_TCY // 200_000):
        h.step()
    h.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    for _ in range(_ACTIVATE_TCY // 200_000):
        h.step()


def _write_filename_ram_gpsim(h: MainChainHarness, name: bytes) -> None:
    """Write filename to the active RAM slot and mark dirty."""
    for i in range(_FILENAME_LEN):
        b = name[i] if i < len(name) else 0x00
        h._issue(f"reg(0x{_FILENAME_RAM_BASE + i:03X})=0x{b:02X}", 5.0)
    # Mark filename dirty (bit 5 of ram_0x0BD) so preset switch persists it
    h._issue("reg(0x0BD)=0x20", 5.0)


def _read_filename_ram_gpsim(h: MainChainHarness) -> str:
    raw = bytes(_read_reg(h._issue, _FILENAME_RAM_BASE + i) for i in range(_FILENAME_LEN))
    return raw.rstrip(b"\x00\xFF").decode("ascii", errors="replace")


def _new_chain_rust(main_hex: Path):
    return RustChain.from_v3x_main_only(str(main_hex))


def _boot_and_activate_rust(c) -> None:
    c.step_tcy(_BOOT_TCY)
    c.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    c.step_tcy(_ACTIVATE_TCY)


def _write_filename_ram_rust(c, name: bytes) -> None:
    for i in range(_FILENAME_LEN):
        b = name[i] if i < len(name) else 0x00
        c.write_reg(_FILENAME_RAM_BASE + i, b)
    c.write_reg(0x0BD, 0x20)


def _read_filename_ram_rust(c) -> str:
    raw = bytes(c.read_reg(_FILENAME_RAM_BASE + i) for i in range(_FILENAME_LEN))
    return raw.rstrip(b"\x00\xFF").decode("ascii", errors="replace")


# Backend-uniform protocol: tests pass a `bk` namespace with the
# methods they need.

class _GpsimBackend:
    name = "gpsim"

    def __init__(self, main_hex: Path):
        self._h = _new_harness_gpsim(main_hex)

    def boot_and_activate(self) -> None:
        _boot_and_activate_gpsim(self._h)

    def step_tcy(self, tcy: int) -> None:
        for _ in range(tcy // 200_000):
            self._h.step()

    def write_filename(self, name: bytes) -> None:
        _write_filename_ram_gpsim(self._h, name)

    def read_filename(self) -> str:
        return _read_filename_ram_gpsim(self._h)

    def inject_frame(self, frame: list[int]) -> None:
        self._h.inject_frames_fifo([frame], fifo_limit=47)

    def close(self) -> None:
        self._h.close()


class _RustBackend:
    name = "rust"

    def __init__(self, main_hex: Path):
        self._c = _new_chain_rust(main_hex)

    def boot_and_activate(self) -> None:
        _boot_and_activate_rust(self._c)

    def step_tcy(self, tcy: int) -> None:
        self._c.step_tcy(tcy)

    def write_filename(self, name: bytes) -> None:
        _write_filename_ram_rust(self._c, name)

    def read_filename(self) -> str:
        return _read_filename_ram_rust(self._c)

    def inject_frame(self, frame: list[int]) -> None:
        self._c.inject_main_frames_fifo([frame], fifo_limit=47)

    def close(self) -> None:
        pass


def _make_backend(main_hex: Path, backend: str):
    if backend == "rust":
        return _RustBackend(main_hex)
    return _GpsimBackend(main_hex)


# ===================================================================
# USB SIE smoke tests (gpsim-only)
# ===================================================================


@pytest.mark.gpsim
@pytest.mark.slow
def test_usb_host_attributes_exist() -> None:
    """gpsim USB host-command attributes are registered on PIC18F2455.

    Gpsim-specific: rust has no USB host SIE.  This test verifies the
    gpsim binary registers the `usb_host_cmd` attribute and the NOP
    invocation doesn't crash."""
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX)
    h = _new_harness_gpsim(V31_MAIN_HEX)
    try:
        for _ in range(5):
            h.step()
        h.usb_host_cmd(0)  # NOP — must not crash
    finally:
        h.close()


# ===================================================================
# Preset A/B filename isolation (dual_supported)
# ===================================================================


def _run_filename_isolation_test(bk) -> None:
    bk.boot_and_activate()
    bk.step_tcy(2_000_000)  # 10 chunks settling

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
        f"[{bk.name}] Preset B: {bk.read_filename()!r}"
    )

    # Switch back to A
    bk.inject_frame([0xB0, 0x20, 0x00])
    bk.step_tcy(_PRESET_SWITCH_TCY)

    # Read back on A — must be "ConfigA"
    assert bk.read_filename() == "ConfigA", (
        f"[{bk.name}] Preset A after B->A: {bk.read_filename()!r}"
    )

    # Switch to B again
    bk.inject_frame([0xB0, 0x20, 0x01])
    bk.step_tcy(_PRESET_SWITCH_TCY)

    # Read back on B — must still be "ConfigB"
    assert bk.read_filename() == "ConfigB", (
        f"[{bk.name}] Preset B after A->B->A->B: {bk.read_filename()!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_ab_filename_isolation(dlcp_sim_backend: str) -> None:
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
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        bk = _make_backend(V31_MAIN_HEX, "rust")
        try:
            _run_filename_isolation_test(bk)
        finally:
            bk.close()
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        bk = _make_backend(V31_MAIN_HEX, "gpsim")
        try:
            _run_filename_isolation_test(bk)
        finally:
            bk.close()


def _run_filename_reverse_order_test(bk) -> None:
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
        f"[{bk.name}] Preset A: {bk.read_filename()!r}"
    )

    # Switch to B, verify B
    bk.inject_frame([0xB0, 0x20, 0x01])
    bk.step_tcy(_PRESET_SWITCH_TCY)
    assert bk.read_filename() == "BetaFilter", (
        f"[{bk.name}] Preset B: {bk.read_filename()!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_ab_filename_reverse_order(dlcp_sim_backend: str) -> None:
    """Upload B first, then A -- both names preserved regardless of order."""
    _skip_missing(V31_MAIN_HEX)
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        bk = _make_backend(V31_MAIN_HEX, "rust")
        try:
            _run_filename_reverse_order_test(bk)
        finally:
            bk.close()
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        bk = _make_backend(V31_MAIN_HEX, "gpsim")
        try:
            _run_filename_reverse_order_test(bk)
        finally:
            bk.close()


def _run_filename_stock_test(bk) -> None:
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
        f"[{bk.name}] Stock firmware filename after cmd 0x20: {name!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_ab_filename_works_on_stock(dlcp_sim_backend: str) -> None:
    """Stock V2.3 has no preset B -- cmd 0x20 is ignored, filename unchanged."""
    _skip_missing(STOCK_MAIN_HEX)
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        bk = _make_backend(STOCK_MAIN_HEX, "rust")
        try:
            _run_filename_stock_test(bk)
        finally:
            bk.close()
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        bk = _make_backend(STOCK_MAIN_HEX, "gpsim")
        try:
            _run_filename_stock_test(bk)
        finally:
            bk.close()
