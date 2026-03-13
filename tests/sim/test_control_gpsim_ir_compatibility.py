"""gpsim stock-vs-patched IR dispatch compatibility tests for CONTROL firmware."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import STOCK_CONTROL_HEX_V14
from dlcp_fw.sim.control_gpsim import GpsimControlHarness, TxTriplet
from dlcp_fw.sim.gpsim import gpsim_available


WARMUP_CYCLES = 25_000_000
IR_STEPS = 3

# Remote profile register layouts (0x020..0x026).
PROFILE_REGS: dict[str, dict[int, int]] = {
    "profile1_hypex": {
        0x020: 0x10,
        0x021: 0x32,  # power
        0x022: 0x33,  # vol+
        0x023: 0x34,  # vol-
        0x024: 0x36,  # input+
        0x025: 0x37,  # input-
        0x026: 0x35,  # mute
    },
    "profile2_standard": {
        0x020: 0x00,
        0x021: 0x0C,  # power
        0x022: 0x10,  # vol+
        0x023: 0x11,  # vol-
        0x024: 0x20,  # input+
        0x025: 0x21,  # input-
        0x026: 0x0D,  # mute
    },
}


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


def _configure_profile(h: GpsimControlHarness, profile_name: str) -> None:
    for addr, value in PROFILE_REGS[profile_name].items():
        h._issue(f"reg(0x{addr:03X})=0x{value:02X}", 5.0)


def _prime_state(h: GpsimControlHarness) -> None:
    # Deterministic baseline so per-command deltas are comparable.
    h._issue("reg(0x0B9)=0x33", 5.0)  # volume midpoint
    h._issue("reg(0x0B7)=0x03", 5.0)  # input index midpoint
    # Normalize low flag bits that affect power/mute behavior:
    # - clear bit1 and bit4 (connected/standby-state path + mute)
    flags = h.read_reg(0x01F) & ~0x12
    h._issue(f"reg(0x01F)=0x{flags:02X}", 5.0)


def _snapshot_state(h: GpsimControlHarness) -> dict[str, int]:
    flags = h.read_reg(0x01F)
    return {
        "volume": h.read_reg(0x0B9),
        "input_idx": h.read_reg(0x0B7),
        "mute": (flags >> 4) & 0x01,
    }


def _s8_delta(before: int, after: int) -> int:
    d = (after - before) & 0xFF
    return d - 256 if d > 127 else d


def _state_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {
        "volume_delta": _s8_delta(before["volume"], after["volume"]),
        "input_delta": _s8_delta(before["input_idx"], after["input_idx"]),
        "mute_delta": _s8_delta(before["mute"], after["mute"]),
    }


def _relevant_frames(frames: list[TxTriplet]) -> list[tuple[int, int, int]]:
    # Focus on legacy behavioral emissions driven by IR actions.
    return [
        (f.route, f.cmd, f.data)
        for f in frames
        if f.route == 0xB0 and f.cmd in (0x03, 0x06, 0x07)
    ]


def _run_ir_case(
    control_hex: Path,
    *,
    profile_name: str,
    decoded_cmd: int,
    decoded_addr: int,
) -> tuple[list[tuple[int, int, int]], dict[str, int]]:
    h = _boot_harness(control_hex)
    try:
        _configure_profile(h, profile_name)
        _prime_state(h)
        before = _snapshot_state(h)
        frames = h.inject_decoded_ir_event(
            cmd=decoded_cmd,
            addr=decoded_addr,
            steps=IR_STEPS,
            clear_debounce=True,
        )
        after = _snapshot_state(h)
        return _relevant_frames(frames), _state_delta(before, after)
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("profile_name", "decoded_addr", "decoded_cmd"),
    [
        # Profile 1 (address 0x10): 0x32..0x37
        pytest.param("profile1_hypex", 0x10, 0x32, id="p1_power_0x32"),
        pytest.param("profile1_hypex", 0x10, 0x33, id="p1_vol_up_0x33"),
        pytest.param("profile1_hypex", 0x10, 0x34, id="p1_vol_down_0x34"),
        pytest.param("profile1_hypex", 0x10, 0x35, id="p1_mute_0x35"),
        pytest.param("profile1_hypex", 0x10, 0x36, id="p1_input_up_0x36"),
        pytest.param("profile1_hypex", 0x10, 0x37, id="p1_input_down_0x37"),
        # Profile 2 (address 0x00): 0x0C,0x10,0x11,0x20,0x21,0x0D
        pytest.param("profile2_standard", 0x00, 0x0C, id="p2_power_0x0c"),
        pytest.param("profile2_standard", 0x00, 0x10, id="p2_vol_up_0x10"),
        pytest.param("profile2_standard", 0x00, 0x11, id="p2_vol_down_0x11"),
        pytest.param("profile2_standard", 0x00, 0x20, id="p2_input_up_0x20"),
        pytest.param("profile2_standard", 0x00, 0x21, id="p2_input_down_0x21"),
        pytest.param("profile2_standard", 0x00, 0x0D, id="p2_mute_0x0d"),
    ],
)
def test_ir_actions_match_stock_dispatch_behavior(
    patched_control_hex: Path,
    profile_name: str,
    decoded_addr: int,
    decoded_cmd: int,
) -> None:
    """Decoded IR events must preserve stock command emission + state deltas."""
    _require_gpsim()
    stock_frames, stock_delta = _run_ir_case(
        STOCK_CONTROL_HEX_V14,
        profile_name=profile_name,
        decoded_cmd=decoded_cmd,
        decoded_addr=decoded_addr,
    )
    patched_frames, patched_delta = _run_ir_case(
        patched_control_hex,
        profile_name=profile_name,
        decoded_cmd=decoded_cmd,
        decoded_addr=decoded_addr,
    )

    assert patched_frames == stock_frames
    assert patched_delta == stock_delta


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("profile_name", "valid_cmd", "wrong_addr"),
    [
        pytest.param("profile1_hypex", 0x33, 0x00, id="wrong_addr_profile1"),
        pytest.param("profile2_standard", 0x10, 0x10, id="wrong_addr_profile2"),
    ],
)
def test_ir_wrong_address_is_ignored(
    patched_control_hex: Path,
    profile_name: str,
    valid_cmd: int,
    wrong_addr: int,
) -> None:
    """Decoded command with non-matching RC5 address must be ignored."""
    _require_gpsim()
    stock_frames, stock_delta = _run_ir_case(
        STOCK_CONTROL_HEX_V14,
        profile_name=profile_name,
        decoded_cmd=valid_cmd,
        decoded_addr=wrong_addr,
    )
    patched_frames, patched_delta = _run_ir_case(
        patched_control_hex,
        profile_name=profile_name,
        decoded_cmd=valid_cmd,
        decoded_addr=wrong_addr,
    )

    assert patched_frames == stock_frames
    assert patched_delta == stock_delta
    assert patched_frames == []
    assert patched_delta == {"volume_delta": 0, "input_delta": 0, "mute_delta": 0}


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("profile_name", "decoded_addr", "unknown_cmd"),
    [
        pytest.param("profile1_hypex", 0x10, 0x3D, id="unknown_cmd_profile1"),
        pytest.param("profile2_standard", 0x00, 0x3D, id="unknown_cmd_profile2"),
    ],
)
def test_ir_unknown_command_is_ignored(
    patched_control_hex: Path,
    profile_name: str,
    decoded_addr: int,
    unknown_cmd: int,
) -> None:
    """Unknown decoded IR command must produce no action."""
    _require_gpsim()
    stock_frames, stock_delta = _run_ir_case(
        STOCK_CONTROL_HEX_V14,
        profile_name=profile_name,
        decoded_cmd=unknown_cmd,
        decoded_addr=decoded_addr,
    )
    patched_frames, patched_delta = _run_ir_case(
        patched_control_hex,
        profile_name=profile_name,
        decoded_cmd=unknown_cmd,
        decoded_addr=decoded_addr,
    )

    assert patched_frames == stock_frames
    assert patched_delta == stock_delta
    assert patched_frames == []
    assert patched_delta == {"volume_delta": 0, "input_delta": 0, "mute_delta": 0}
