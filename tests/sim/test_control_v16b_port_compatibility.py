"""V1.6b -> V1.61b control-port compatibility and delta-preservation tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dlcp_fw.patch.verify_presets_ab import check_control_v16b, parse_intel_hex
from dlcp_fw.paths import STOCK_CONTROL_HEX_V15B, STOCK_CONTROL_HEX_V16B
from dlcp_fw.sim.control_gpsim import GpsimControlHarness, TxTriplet
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.hexio import write_intel_hex


WARMUP_CYCLES = 25_000_000
IR_STEPS = 3
KEY_STEPS = 12

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


def _boot_harness(control_hex: Path, *, eeprom_file: Path | None = None) -> GpsimControlHarness:
    h = GpsimControlHarness(
        control_hex,
        fast_boot=True,
        eeprom_file=eeprom_file,
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
    # - clear bit1 and bit4/bit5 toggles used by firmware variants.
    flags = h.read_reg(0x01F) & ~0x32
    h._issue(f"reg(0x01F)=0x{flags:02X}", 5.0)


def _snapshot_state(h: GpsimControlHarness) -> dict[str, int]:
    flags = h.read_reg(0x01F)
    mute = (flags >> 4) & 0x01
    if mute == 0:
        mute = (flags >> 5) & 0x01
    return {
        "volume": h.read_reg(0x0B9),
        "input_idx": h.read_reg(0x0B7),
        "mute": mute,
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


def _run_cmd18_reset_case(control_hex: Path) -> tuple[bool, set[int]]:
    h = _boot_harness(control_hex)
    try:
        h.press("R")
        for _ in range(KEY_STEPS):
            h.step()
        assert h.read_reg(0x0BF) == 1
        h.inject_host_command(cmd=0x18, data=0x01, steps=0)

        seen_text = False
        states: set[int] = set()
        for _ in range(50):
            h.step()
            l1, l2 = h.lcd_lines()
            states.add(h.read_reg(0x0BF))
            if ("Firmware V" in l1) or ("Waiting for DLCP" in l1) or ("Waiting for DLCP" in l2):
                seen_text = True
        return seen_text, states
    finally:
        h.close()


def _run_action_frames(control_hex: Path, *, pre_keys: list[str], action_key: str) -> list[tuple[int, int, int]]:
    h = _boot_harness(control_hex)
    try:
        for key in pre_keys:
            h.press(key)
            for _ in range(KEY_STEPS):
                h.step()
        before = len(h.tx_frames())
        h.press(action_key)
        for _ in range(KEY_STEPS):
            h.step()
        return [
            (f.route, f.cmd, f.data)
            for f in h.tx_frames()[before:]
            if f.route == 0xB0 and f.cmd in (0x03, 0x06, 0x07)
        ]
    finally:
        h.close()


def _seed_stale_v16_setup_index(path: Path, *, setup_idx: int) -> None:
    mem = {addr: 0x00 for addr in range(256)}
    mem[0x01] = setup_idx & 0xFF
    mem[0x73] = 0xFF
    mem[0x74] = 0xFF
    write_intel_hex(path, mem)


def _enter_setup_screen(h: GpsimControlHarness, *, max_moves: int = 8) -> tuple[str, str]:
    for _ in range(max_moves):
        lines = h.lcd_lines()
        if lines[0].startswith("Setup"):
            return lines
        h.press("R")
        for _ in range(KEY_STEPS):
            h.step()
    raise AssertionError(f"failed to reach Setup screen: lcd={h.lcd_lines()} state=0x{h.read_reg(0x0BF):02X}")


@pytest.mark.dual_supported
def test_control_v161b_static_verifier_accepts_current_patch(patched_control_hex_v161b: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(patched_control_hex_v161b)
    check_control_v16b(stock, patched)


@pytest.mark.dual_supported
def test_control_v15b_v16b_stock_delta_preserved_in_v161b(patched_control_hex_v161b: Path) -> None:
    v15 = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    v16 = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    v161 = parse_intel_hex(patched_control_hex_v161b)

    # Bootloader-prevention config remains enabled through the port.
    assert v15.get(0x300000, 0xFF) == 0xFF
    assert v16.get(0x300000, 0xFF) == 0xFF
    assert v161.get(0x300000, 0xFF) == 0xFF

    # Preserve V1.6b branch identity in tuple high bytes while updating patch digit.
    assert [v15.get(0xF00070, 0xFF), v15.get(0xF00071, 0xFF), v15.get(0xF00072, 0xFF)] == [0x01, 0x04, 0x30]
    assert [v16.get(0xF00070, 0xFF), v16.get(0xF00071, 0xFF), v16.get(0xF00072, 0xFF)] == [0x01, 0x06, 0x30]
    assert [v161.get(0xF00070, 0xFF), v161.get(0xF00071, 0xFF), v161.get(0xF00072, 0xFF)] == [0x01, 0x06, 0x31]

    # V1.6b "combi display" high-page region must remain byte-identical.
    for addr in range(0x7800, 0x7F70):
        assert v161.get(addr, 0xFF) == v16.get(addr, 0xFF)

    # Keep V1.6b dispatch-family callsite bytes (outside patch hooks).
    assert v16.get(0x11E8, 0xFF) == 0x68
    assert v161.get(0x11E8, 0xFF) == 0x68


@pytest.mark.dual_supported
def test_control_v161b_preserves_setup_usb_surface_code_blocks(patched_control_hex_v161b: Path) -> None:
    """Keep V1.6b setup-related blocks byte-identical.

    V1.6b removed front-panel setup navigation, but setup-equivalent values are
    still represented in control RAM blocks and command helper routines. Keep the
    stock V1.6b code for those paths intact in V1.61b.
    """
    v16 = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    v161 = parse_intel_hex(patched_control_hex_v161b)

    protected_ranges = [
        # EEPROM save path for setup parameter blocks.
        (0x09BC, 0x0A30, "setup_save_cluster"),
        # EEPROM load/restore path for setup parameter blocks.
        (0x0A72, 0x0AF8, "setup_load_cluster"),
        # Legacy helper routines that emit route/cmd/data for 0x17..0x1E.
        (0x0B7C, 0x0C22, "setup_tx_helper_cluster"),
    ]

    for start, end, label in protected_ranges:
        diffs = [addr for addr in range(start, end) if v161.get(addr, 0xFF) != v16.get(addr, 0xFF)]
        assert not diffs, (
            f"{label} drifted in V1.61b; first diff=0x{diffs[0]:04X} "
            f"(stock=0x{v16.get(diffs[0], 0xFF):02X}, patched=0x{v161.get(diffs[0], 0xFF):02X})"
        )


@pytest.mark.gpsim
@pytest.mark.slow
def test_v161b_clamps_stale_setup_index_from_eeprom(patched_control_hex_v161b: Path) -> None:
    _require_gpsim()

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        stale = tmp / "stale_setup.hex"
        scrubbed = tmp / "scrubbed.hex"
        _seed_stale_v16_setup_index(stale, setup_idx=0x01)

        stock = _boot_harness(STOCK_CONTROL_HEX_V16B, eeprom_file=stale)
        try:
            stock_setup = _enter_setup_screen(stock)
            assert stock_setup[0] == "Setup           "
            assert stock_setup[1] != "BL Timeout      "
            stock.press("S")
            for _ in range(KEY_STEPS):
                stock.step()
            stock_editor = stock.lcd_lines()
            assert stock_editor[0] != "BL Timeout      "
            assert stock_editor[1] == "30 sec          "
        finally:
            stock.close()

        patched = _boot_harness(patched_control_hex_v161b, eeprom_file=stale)
        try:
            patched.dump_eeprom(scrubbed)
            scrubbed_mem = parse_intel_hex(scrubbed)
            assert scrubbed_mem.get(0x01, 0xFF) == 0x00

            patched_setup = _enter_setup_screen(patched)
            assert patched_setup == ("Setup           ", "BL Timeout      ")
            patched.press("S")
            for _ in range(KEY_STEPS):
                patched.step()
            assert patched.lcd_lines() == ("BL Timeout      ", "30 sec          ")
        finally:
            patched.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_cmd18_reset_behavior_matches_v16b(patched_control_hex_v161b: Path) -> None:
    _require_gpsim()
    v16_reset, v16_states = _run_cmd18_reset_case(STOCK_CONTROL_HEX_V16B)
    v161_reset, v161_states = _run_cmd18_reset_case(patched_control_hex_v161b)

    assert v161_reset == v16_reset
    assert v161_states == v16_states


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
def test_ir_actions_match_stock_v16b_dispatch_behavior(
    patched_control_hex_v161b: Path,
    profile_name: str,
    decoded_addr: int,
    decoded_cmd: int,
) -> None:
    """Decoded IR events must preserve stock V1.6b emission + state deltas."""
    _require_gpsim()
    stock_frames, stock_delta = _run_ir_case(
        STOCK_CONTROL_HEX_V16B,
        profile_name=profile_name,
        decoded_cmd=decoded_cmd,
        decoded_addr=decoded_addr,
    )
    patched_frames, patched_delta = _run_ir_case(
        patched_control_hex_v161b,
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
def test_ir_wrong_address_is_ignored_like_stock_v16b(
    patched_control_hex_v161b: Path,
    profile_name: str,
    valid_cmd: int,
    wrong_addr: int,
) -> None:
    _require_gpsim()
    stock_frames, stock_delta = _run_ir_case(
        STOCK_CONTROL_HEX_V16B,
        profile_name=profile_name,
        decoded_cmd=valid_cmd,
        decoded_addr=wrong_addr,
    )
    patched_frames, patched_delta = _run_ir_case(
        patched_control_hex_v161b,
        profile_name=profile_name,
        decoded_cmd=valid_cmd,
        decoded_addr=wrong_addr,
    )
    assert patched_frames == stock_frames == []
    assert patched_delta == stock_delta == {"volume_delta": 0, "input_delta": 0, "mute_delta": 0}


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("profile_name", "decoded_addr", "unknown_cmd"),
    [
        pytest.param("profile1_hypex", 0x10, 0x3D, id="unknown_cmd_profile1"),
        pytest.param("profile2_standard", 0x00, 0x3D, id="unknown_cmd_profile2"),
    ],
)
def test_ir_unknown_command_is_ignored_like_stock_v16b(
    patched_control_hex_v161b: Path,
    profile_name: str,
    decoded_addr: int,
    unknown_cmd: int,
) -> None:
    _require_gpsim()
    stock_frames, stock_delta = _run_ir_case(
        STOCK_CONTROL_HEX_V16B,
        profile_name=profile_name,
        decoded_cmd=unknown_cmd,
        decoded_addr=decoded_addr,
    )
    patched_frames, patched_delta = _run_ir_case(
        patched_control_hex_v161b,
        profile_name=profile_name,
        decoded_cmd=unknown_cmd,
        decoded_addr=decoded_addr,
    )
    assert patched_frames == stock_frames == []
    assert patched_delta == stock_delta == {"volume_delta": 0, "input_delta": 0, "mute_delta": 0}


@pytest.mark.gpsim
@pytest.mark.slow
def test_key_action_legacy_frames_match_stock_v16b(patched_control_hex_v161b: Path) -> None:
    _require_gpsim()

    # Same-screen actions: direct parity expected.
    assert _run_action_frames(STOCK_CONTROL_HEX_V16B, pre_keys=[], action_key="S") == _run_action_frames(
        patched_control_hex_v161b, pre_keys=[], action_key="S"
    )
    assert _run_action_frames(STOCK_CONTROL_HEX_V16B, pre_keys=[], action_key="U") == _run_action_frames(
        patched_control_hex_v161b, pre_keys=[], action_key="U"
    )

    # Input/preset-path compatibility is covered by the IR matrix above (input-up/down
    # commands on both RC5 profiles), which is deterministic across firmwares.
