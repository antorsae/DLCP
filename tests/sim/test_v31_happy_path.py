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

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc

# ---- Helpers ----

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


# ---- Backend-uniform helpers ----
# Each test body uses these helpers + the per-backend factory below
# so the test logic can stay backend-agnostic. The rust/gpsim split
# lives entirely inside `_make_harness` and the `read_main_reg` /
# `read_dsp_reg` helpers.


_GPSIM_CHUNK_TCY = 200_000


class _GpsimHarness:
    """Thin gpsim adapter mirroring the rust Chain interface used
    in this file (read_reg / read_dsp_reg / advance_tcy / inject /
    close)."""

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
        # gpsim's single-process scheduler can't advance more
        # than `chunk_cycles` between core swaps; loop the
        # required number of chunked steps.
        for _ in range(tcy // _GPSIM_CHUNK_TCY):
            self._h.step()

    def inject_main_frames_fifo(
        self, frames: list[list[int]], fifo_limit: int
    ) -> tuple[int, int]:
        return self._h.inject_frames_fifo(frames, fifo_limit=fifo_limit)

    def read_reg(self, addr: int) -> int:
        return _read_reg(self._h._issue, addr)

    def read_dsp_reg(self, subaddr: int) -> int:
        return self._h.read_i2c_regfile("dsp34", subaddr)

    def close(self) -> None:
        self._h.close()


class _RustHarness:
    """Thin rust adapter mirroring the same surface.  Advances
    time in single `step_tcy` calls -- no chunk granularity, so
    no for-loops in the test body."""

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

    def close(self) -> None:  # rust chain has no resource to release
        pass


def _make_harness(main_hex: Path, backend: str):
    if backend == "rust":
        return _RustHarness(main_hex)
    return _GpsimHarness(main_hex)


def _boot_and_activate(h) -> None:
    h.advance_tcy(20 * 200_000)
    h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    h.advance_tcy(20 * 200_000)
    assert h.read_reg(_STATUS_5E) & 0x08, "MAIN not active"


def _dsp_snapshot(h) -> dict[int, int]:
    return {r: h.read_dsp_reg(r) for r in range(256)}


def _dsp_diff(before: dict[int, int], after: dict[int, int]) -> list:
    return [(r, before[r], after[r]) for r in range(256) if before[r] != after[r]]


def _enabled_backends(dlcp_sim_backend: str) -> list[str]:
    backends: list[str] = []
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        backends.append("rust")
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        backends.append("gpsim")
    return backends


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
@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _ALL_VERSIONS)
def test_dsp_preset_registers_nonzero_after_boot(
    main_hex: Path, dlcp_sim_backend: str,
) -> None:
    """After boot + activation, DSP preset registers must have data.

    The firmware loads the DSP preset table (0x5600) into the TAS3108
    via I2C during the boot sequence.  Key DSP registers (0x37-0x45
    for the first filter bank) should be non-zero after boot.

    This catches i2c_byte_tx regressions that silently drop I2C data.
    """
    _skip_missing(main_hex)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_harness(main_hex, backend)
        try:
            _boot_and_activate(h)
            h.advance_tcy(30 * 200_000)

            preset_regs = [0x29, 0x46, 0x55, 0x6B, 0x91, 0xD7]
            nonzero = {r: h.read_dsp_reg(r) for r in preset_regs}
            nonzero_count = sum(1 for v in nonzero.values() if v != 0)

            assert nonzero_count >= 4, (
                f"[{backend}] Only {nonzero_count}/6 DSP preset registers "
                f"non-zero after boot — preset table not loaded via I2C. "
                f"Values: "
                f"{{{', '.join(f'0x{r:02X}:0x{v:02X}' for r,v in nonzero.items())}}}"
            )
        finally:
            h.close()


# ===================================================================
# Test 2: Volume command changes DSP coefficient register
# ===================================================================
#
# NOTE: NOT marked `dual_supported`.  This test passes on gpsim only
# because gpsim's preset-table I²C burst is still in flight when the
# pre-volume snapshot is taken, so the post-volume snapshot diff
# captures preset bytes finishing as well as the volume write.  The
# rust engine completes preset loading earlier (faster scheduler),
# so by the snapshot window only the volume write is in flight --
# and a single volume command on V3.x writes 0 or 1 DSP subaddresses
# (verified by probing both backends with an extra 50-chunk
# settle: gpsim shows 1 reg change for 0x07/0x50 then 0 for the
# next volume cmd).  The test as written documents a gpsim timing
# coincidence, not a real invariant about the volume-to-DSP path.
# Test #3 (`test_two_volumes_produce_different_computed_volume`)
# already covers the volume-computation path via MAIN RAM
# (0x06E-0x071) and is dual-mode-validated.


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

    h = _GpsimHarness(main_hex)
    try:
        _boot_and_activate(h)
        h.advance_tcy(20 * 200_000)

        snap_before = _dsp_snapshot(h)
        h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        h.advance_tcy(30 * 200_000)
        snap_after = _dsp_snapshot(h)

        diff = _dsp_diff(snap_before, snap_after)
        assert len(diff) > 0, (
            "Volume command 0x50 produced zero DSP register changes — "
            "volume I2C path is broken"
        )
    finally:
        h.close()


# ===================================================================
# Test 3: Two different volume commands produce different DSP states
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _ALL_VERSIONS)
def test_two_volumes_produce_different_computed_volume(
    main_hex: Path, dlcp_sim_backend: str,
) -> None:
    """Two different volume commands must produce different computed_volume.

    The firmware's volume computation converts serial data byte to a
    32-bit coefficient stored in computed_volume (0x06E-0x071).
    Different input values must produce different computed values.

    Note: The 8-bit DSP regfile snapshot may not distinguish two
    volume coefficients (the MSB might be the same).  So we check
    the 32-bit computed_volume in MAIN RAM instead.
    """
    _skip_missing(main_hex)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_harness(main_hex, backend)
        try:
            _boot_and_activate(h)
            h.advance_tcy(20 * 200_000)

            h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
            h.advance_tcy(30 * 200_000)
            vol1 = tuple(h.read_reg(r) for r in (0x06E, 0x06F, 0x070, 0x071))

            h.inject_main_frames_fifo([[0xB0, 0x07, 0x60]], fifo_limit=47)
            h.advance_tcy(30 * 200_000)
            vol2 = tuple(h.read_reg(r) for r in (0x06E, 0x06F, 0x070, 0x071))

            assert vol1 != vol2, (
                f"[{backend}] Two different volume commands produced same "
                f"computed_volume: vol1={tuple(hex(v) for v in vol1)}, "
                f"vol2={tuple(hex(v) for v in vol2)} — "
                f"volume computation or commit may be broken"
            )
        finally:
            h.close()


# ===================================================================
# Test 4: Boot volume from EEPROM is applied to DSP
# ===================================================================
#
# NOTE: NOT marked `dual_supported`.  The SECOND assertion in this
# test ("volume cmd produces DSP changes") relies on preset loading
# still being in flight on gpsim's slower scheduler -- same
# timing-coincidence rationale as test 2 above.
#
# The FIRST assertion ("computed_volume or logical_volume non-zero
# after boot") is robust on both backends and exercises the
# EEPROM-boot-volume-applied-to-RAM init path that no other test in
# this file covers (test 1 checks DSP preset regs, test 3 checks
# that two POST-boot injected volumes differ in RAM but doesn't
# establish that EEPROM boot init populated RAM).  A future P4.6
# follow-up could split this test so the EEPROM-init assertion
# becomes a standalone dual_supported function and only the
# DSP-diff assertion stays gpsim-only; for now the whole function
# stays gpsim-only to keep the migration scope tight.


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

    h = _GpsimHarness(main_hex)
    try:
        _boot_and_activate(h)
        h.advance_tcy(40 * 200_000)

        computed = h.read_reg(0x06E)
        logical = h.read_reg(0x066)

        assert computed != 0 or logical != 0, (
            f"Boot volume not loaded: computed=0x{computed:02X}, "
            f"logical=0x{logical:02X} — EEPROM volume init may be broken"
        )

        snap = _dsp_snapshot(h)
        h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        h.advance_tcy(30 * 200_000)
        diff = _dsp_diff(snap, _dsp_snapshot(h))

        assert len(diff) > 0, (
            "Volume command after boot produced no DSP changes — "
            "DSP I2C path may be broken"
        )
    finally:
        h.close()
