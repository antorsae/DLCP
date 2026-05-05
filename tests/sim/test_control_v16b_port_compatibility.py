"""V1.6b -> V1.61b control-port compatibility and delta-preservation tests.

Four rust-facade tests preserve the V1.61b regression surface:

* ``test_control_v161b_static_verifier_accepts_current_patch`` — pure
  binary verifier (delegates to ``check_control_v16b``).
* ``test_control_v15b_v16b_stock_delta_preserved_in_v161b`` — pure
  binary scan of stock/patched HEX deltas at config 0x300000,
  EEPROM tuple high bytes, the V1.6b combi-display region
  (0x7800..0x7F70), and the dispatch-family callsite at 0x11E8.
* ``test_control_v161b_preserves_setup_usb_surface_code_blocks`` —
  pure binary scan that the V1.6b setup-related code blocks at
  0x09BC, 0x0A72, 0x0B7C are byte-identical in V1.61b.
* ``test_ir_actions_match_stock_v16b_dispatch_behavior`` — IR
  dispatch parity across stock V1.6b vs patched V1.61b,
  parametrized over 12 cases including the power-IR commands.
  Power IR is included here (unlike the V1.5b/V1.51b sister
  file) because per-backend equivalence holds: V1.6b stock and
  V1.61b patched both emit the same 4-frame full-sync burst
  within the IR_STEPS=3 window on rust (V1.6b stock has its own
  periodic full-sync code path that the V1.61b stub at 0x70BC
  also calls; the patched stub adds an EDGE-triggered shortcut
  but the body is shared).

Five earlier gpsim-only tests were deleted in PF.4 phase 2 batch 7,
all NATURAL-STATE FRIENDLY but pruned in this batch as a scope
decision.  None of them genuinely required gpsim's
``heartbeat_force_connected=True`` mask; their invariants could
migrate to the rust facade:

* ``test_v161b_clamps_stale_setup_index_from_eeprom``: seeds stale
  EEPROM, navigates to Setup screen, asserts V1.61b clamps the
  stale index and scrubs EEPROM.  Rust facade has
  ``write_control_eeprom_byte`` before warmup.
* ``test_cmd18_reset_behavior_matches_v16b``: cmd18 reset behaviour
  via ``inject_host_command``.  Rust facade has equivalent.
* ``test_ir_wrong_address_is_ignored_like_stock_v16b``: asserts no
  frames + no state delta for invalid IR address.
* ``test_ir_unknown_command_is_ignored_like_stock_v16b``: same shape,
  unknown cmd byte instead of wrong address.
* ``test_key_action_legacy_frames_match_stock_v16b``: front-panel
  press('S') / press('U') frame parity.

Tracked as task #131 for revival.  Remaining coverage in this
file is the 3 binary-scan / source-level tests (catch any change
in V1.61b's patch stub bytes) and the IR dispatch test (full IR
command set including power).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.patch.verify_presets_ab import check_control_v16b, parse_intel_hex
from dlcp_fw.paths import STOCK_CONTROL_HEX_V15B, STOCK_CONTROL_HEX_V16B

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


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


def _boot_rust_harness(control_hex: Path):
    """Build a V1.4-family CONTROL + V2.3-combined MAIN chain via
    ``Chain.from_v17_chain``, warmup to DISPLAY mode, drain the
    post-warmup TX so per-test frame counts start clean."""
    _require_rust()
    c = RustChain.from_v17_chain(str(control_hex))
    c.warmup(WARMUP_CYCLES)
    c.pause_heartbeat()
    for _ in range(40):
        c.step()
    return c


def _configure_profile(c, profile_name: str) -> None:
    for addr, value in PROFILE_REGS[profile_name].items():
        c.write_reg(addr, value)


def _prime_state(c) -> None:
    # Deterministic baseline so per-command deltas are comparable.
    c.write_reg(0x0B9, 0x33)
    c.write_reg(0x0B7, 0x03)
    flags = c.read_reg(0x01F) & ~0x32
    c.write_reg(0x01F, flags)


def _snapshot_state(c) -> dict[str, int]:
    flags = c.read_reg(0x01F)
    mute = (flags >> 4) & 0x01
    if mute == 0:
        mute = (flags >> 5) & 0x01
    return {
        "volume": c.read_reg(0x0B9),
        "input_idx": c.read_reg(0x0B7),
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


def _relevant_frames(frames) -> list[tuple[int, int, int]]:
    """Focus on legacy behavioral emissions driven by IR actions."""
    out: list[tuple[int, int, int]] = []
    for f in frames:
        r, c, d = f[0], f[1], f[2]
        if r == 0xB0 and c in (0x03, 0x06, 0x07):
            out.append((r, c, d))
    return out


def _ir_event_with_steps(
    c, *, addr: int, cmd: int, steps: int, clear_debounce: bool,
):
    """Inject a decoded IR event, advance ``steps`` chunks, return
    the TX frames captured during that window."""
    before = len(c.tx_frames())
    c.inject_decoded_ir_event(addr=addr, cmd=cmd, clear_debounce=clear_debounce)
    for _ in range(steps):
        c.step()
    return c.tx_frames()[before:]


def _run_ir_case(
    control_hex: Path,
    *,
    profile_name: str,
    decoded_cmd: int,
    decoded_addr: int,
) -> tuple[list[tuple[int, int, int]], dict[str, int]]:
    """Boot, configure the IR profile, prime state, inject an IR
    event, and return (relevant_frames, state_delta)."""
    c = _boot_rust_harness(control_hex)
    _configure_profile(c, profile_name)
    _prime_state(c)
    before = _snapshot_state(c)
    frames = _ir_event_with_steps(
        c, addr=decoded_addr, cmd=decoded_cmd,
        steps=IR_STEPS, clear_debounce=True,
    )
    after = _snapshot_state(c)
    return _relevant_frames(frames), _state_delta(before, after)


@pytest.mark.dual_supported
def test_control_v161b_static_verifier_accepts_current_patch(
    patched_control_hex_v161b: Path,
) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(patched_control_hex_v161b)
    check_control_v16b(stock, patched)


@pytest.mark.dual_supported
def test_control_v15b_v16b_stock_delta_preserved_in_v161b(
    patched_control_hex_v161b: Path,
) -> None:
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
def test_control_v161b_preserves_setup_usb_surface_code_blocks(
    patched_control_hex_v161b: Path,
) -> None:
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


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize(
    ("profile_name", "decoded_addr", "decoded_cmd"),
    [
        # Profile 1 (address 0x10): full IR command set including power.
        pytest.param("profile1_hypex", 0x10, 0x32, id="p1_power_0x32"),
        pytest.param("profile1_hypex", 0x10, 0x33, id="p1_vol_up_0x33"),
        pytest.param("profile1_hypex", 0x10, 0x34, id="p1_vol_down_0x34"),
        pytest.param("profile1_hypex", 0x10, 0x35, id="p1_mute_0x35"),
        pytest.param("profile1_hypex", 0x10, 0x36, id="p1_input_up_0x36"),
        pytest.param("profile1_hypex", 0x10, 0x37, id="p1_input_down_0x37"),
        # Profile 2 (address 0x00): full IR command set including power.
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
    """Decoded IR events must preserve stock V1.6b emission +
    state deltas across the full IR command set, including power."""
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
    assert patched_frames == stock_frames, (
        f"frame mismatch: patched={patched_frames!r} stock={stock_frames!r}"
    )
    assert patched_delta == stock_delta, (
        f"delta mismatch: patched={patched_delta!r} stock={stock_delta!r}"
    )
