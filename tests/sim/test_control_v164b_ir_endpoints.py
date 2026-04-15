"""V1.64b CONTROL IR endpoint semantics tests.

Validate that decoded IR commands expose deterministic standby/wake endpoints
instead of only POWER toggle behavior.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness
from dlcp_fw.sim.gpsim import gpsim_available


WARMUP_CYCLES = 25_000_000


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _boot_harness(control_hex: Path) -> GpsimControlHarness:
    h = GpsimControlHarness(
        control_hex,
        fast_boot=True,
        chunk_cycles=200_000,
        hold_cycles=120_000,
        heartbeat_rx_mode="none",
        heartbeat_force_connected=True,
    )
    h.warmup(WARMUP_CYCLES)
    return h


def _configure_profile1_hypex(h: GpsimControlHarness) -> None:
    for addr, value in {
        0x020: 0x10,
        0x021: 0x32,
        0x022: 0x33,
        0x023: 0x34,
        0x024: 0x36,
        0x025: 0x37,
        0x026: 0x35,
    }.items():
        h._issue(f"reg(0x{addr:03X})=0x{value:02X}", 5.0)


def _set_standby_flag(h: GpsimControlHarness, *, enabled: bool) -> None:
    flags = h.read_reg(0x01F)
    if enabled:
        flags |= 0x02
    else:
        flags &= 0xFD
    h._issue(f"reg(0x01F)=0x{flags:02X}", 5.0)


@pytest.mark.gpsim
@pytest.mark.slow
def test_v164b_ir_standby_endpoint_forces_bit1_low(patched_control_hex_v164b: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex_v164b)
    try:
        _configure_profile1_hypex(h)
        _set_standby_flag(h, enabled=True)

        h.inject_decoded_ir_event(cmd=0x3A, addr=0x10, steps=1, clear_debounce=True)

        flags = h.read_reg(0x01F)
        assert (flags & 0x02) == 0x00
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v164b_ir_wake_endpoint_forces_bit1_high(patched_control_hex_v164b: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex_v164b)
    try:
        _configure_profile1_hypex(h)
        _set_standby_flag(h, enabled=False)

        h.inject_decoded_ir_event(cmd=0x3B, addr=0x10, steps=1, clear_debounce=True)

        flags = h.read_reg(0x01F)
        assert (flags & 0x02) == 0x02
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v164b_ir_power_code_remains_toggle_compatible(patched_control_hex_v164b: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex_v164b)
    try:
        _configure_profile1_hypex(h)

        _set_standby_flag(h, enabled=True)
        h.inject_decoded_ir_event(cmd=0x32, addr=0x10, steps=1, clear_debounce=True)
        after_first = h.read_reg(0x01F)
        assert (after_first & 0x02) == 0x00

        _set_standby_flag(h, enabled=False)
        h.inject_decoded_ir_event(cmd=0x32, addr=0x10, steps=2, clear_debounce=True)
        after_second = h.read_reg(0x01F)
        assert (after_second & 0x02) == 0x02
    finally:
        h.close()
