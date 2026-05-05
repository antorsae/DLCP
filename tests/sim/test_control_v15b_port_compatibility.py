"""V1.5b -> V1.51b control-port compatibility and delta-preservation tests.

Three rust-facade tests preserve the V1.51b regression surface:

* ``test_control_v151b_static_verifier_accepts_current_patch`` — pure
  binary verifier (delegates to ``check_control_v15b``).
* ``test_control_v14_v15b_stock_delta_preserved_in_v151b`` — pure
  binary scan of stock/patched HEX deltas at config 0x300000,
  EEPROM 0xFE, and the cmd response tail at 0x05C6.
* ``test_ir_actions_match_stock_v15b_dispatch_behavior`` — IR
  vol/input/mute dispatch parity across stock V1.5b vs patched
  V1.51b, parametrized over the two remote profiles (Hypex
  address 0x10 + Standard address 0x00).  Power IR commands are
  excluded — they trigger V1.51b's reconnect/full-sync retry
  stub at 0x70BC by toggling 0x01F.bit1 via ``btg``, which only
  matched stock under gpsim's legacy ``heartbeat_force_connected
  =True`` mask (see deleted tests below).

Five earlier gpsim-only tests were deleted in PF.4 phase 2 batch 7:

* ``test_ir_power_actions_match_stock_v15b_under_legacy_gpsim_mask``:
  GENUINELY mask-dependent.  V1.51b's reconnect/full-sync retry
  stub at 0x70BC observes ``0x01F.bit1`` edges via ``btg``; under
  gpsim's ``heartbeat_force_connected=True`` the bit was pinned
  high so the stub's edge-triggered shortcut never fired,
  matching V1.5b stock.  Natural-state simulators (rust, real
  silicon) see the divergence.  Reviving on rust would prove
  the wrong invariant.

* ``test_cmd18_reset_behavior_matches_v15b_not_v14``,
  ``test_ir_wrong_address_is_ignored_like_stock_v15b``,
  ``test_ir_unknown_command_is_ignored_like_stock_v15b``,
  ``test_key_action_legacy_frames_match_stock_v15b``: NATURAL-STATE
  FRIENDLY but deleted in this batch as a scope decision.  Their
  invariants (no frames on invalid IR, cmd18 reset behaviour,
  front-panel key-action frame parity) do not require the
  legacy mask and could migrate to the rust facade.  Tracked as
  task #131 for revival.

Remaining coverage in this file is the binary-scan verifier
(catches any change in V1.51b's patch stub bytes) and the IR
vol/input/mute dispatch test (most common remote-control paths).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.patch.verify_presets_ab import check_control_v15b, parse_intel_hex
from dlcp_fw.paths import STOCK_CONTROL_HEX_V14, STOCK_CONTROL_HEX_V15B

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
KEY_STEPS = 8

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
    post-warmup TX so the per-test frame counts start clean."""
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
def test_control_v151b_static_verifier_accepts_current_patch(
    patched_control_hex_v151b: Path,
) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(patched_control_hex_v151b)
    check_control_v15b(stock, patched)


@pytest.mark.dual_supported
def test_control_v14_v15b_stock_delta_preserved_in_v151b(
    patched_control_hex_v151b: Path,
) -> None:
    v14 = parse_intel_hex(STOCK_CONTROL_HEX_V14)
    v15 = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    v151 = parse_intel_hex(patched_control_hex_v151b)

    # Config delta (V1.5b bootloader-prevention config) must be preserved.
    assert v14.get(0x300000, 0xFF) == 0x00
    assert v15.get(0x300000, 0xFF) == 0xFF
    assert v151.get(0x300000, 0xFF) == 0xFF

    # EEPROM delta at 0xFE between V1.4 and V1.5b must remain V1.5b-like.
    assert v14.get(0xF000FE, 0xFF) == 0x01
    assert v15.get(0xF000FE, 0xFF) == 0xFF
    assert v151.get(0xF000FE, 0xFF) == 0xFF

    # Response cmd tail changed between V1.4 and V1.5b at 0x05C6.
    # V1.4 has movlw 0x18; V1.5b switched to cmd=0x1D handling.
    # The simplified V1.51b design does not touch this parser tail, so the
    # V1.5b bytes must remain intact.
    assert v14.get(0x05C6, 0xFF) == 0x18
    assert v15.get(0x05C6, 0xFF) == 0x1D
    assert [v151.get(0x05C6 + off, 0xFF) for off in range(6)] == [
        v15.get(0x05C6 + off, 0xFF) for off in range(6)
    ]


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize(
    ("profile_name", "decoded_addr", "decoded_cmd"),
    [
        # Profile 1 (address 0x10): vol up/down, mute, input up/down.
        # Power 0x32 excluded -- triggers V1.51b's reconnect/full-sync
        # retry stub (see module docstring).
        pytest.param("profile1_hypex", 0x10, 0x33, id="p1_vol_up_0x33"),
        pytest.param("profile1_hypex", 0x10, 0x34, id="p1_vol_down_0x34"),
        pytest.param("profile1_hypex", 0x10, 0x35, id="p1_mute_0x35"),
        pytest.param("profile1_hypex", 0x10, 0x36, id="p1_input_up_0x36"),
        pytest.param("profile1_hypex", 0x10, 0x37, id="p1_input_down_0x37"),
        # Profile 2 (address 0x00): vol up/down, input up/down, mute.
        # Power 0x0C excluded for the same reason.
        pytest.param("profile2_standard", 0x00, 0x10, id="p2_vol_up_0x10"),
        pytest.param("profile2_standard", 0x00, 0x11, id="p2_vol_down_0x11"),
        pytest.param("profile2_standard", 0x00, 0x20, id="p2_input_up_0x20"),
        pytest.param("profile2_standard", 0x00, 0x21, id="p2_input_down_0x21"),
        pytest.param("profile2_standard", 0x00, 0x0D, id="p2_mute_0x0d"),
    ],
)
def test_ir_actions_match_stock_v15b_dispatch_behavior(
    patched_control_hex_v151b: Path,
    profile_name: str,
    decoded_addr: int,
    decoded_cmd: int,
) -> None:
    """Decoded IR events must preserve stock V1.5b emission +
    state deltas across the volume / input / mute commands."""
    stock_frames, stock_delta = _run_ir_case(
        STOCK_CONTROL_HEX_V15B,
        profile_name=profile_name,
        decoded_cmd=decoded_cmd,
        decoded_addr=decoded_addr,
    )
    patched_frames, patched_delta = _run_ir_case(
        patched_control_hex_v151b,
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


# ---------------------------------------------------------------------------
# Coverage revived from PF.4 phase 2 batch 7 deletion (codex task #131).
# These tests cover natural-state-friendly invariants that don't need the
# legacy gpsim heartbeat-force-connected mask:
#
#   * cmd 0x18 host-command reset behaviour
#   * IR with wrong address -> no frames, no state delta
#   * IR with unknown command -> no frames, no state delta
#   * front-panel key-action frame parity (S=Standby, U=Up)
# ---------------------------------------------------------------------------


def _run_cmd18_reset_case(control_hex: Path) -> tuple[bool, set[int]]:
    """Press R to reach a non-Volume screen, inject host cmd 0x18, then
    poll display_state_index (RAM 0x0BF) and the LCD for evidence of a
    reset traversal back through state 0.  Returns
    ``(seen_reset_text, observed_states)``."""
    c = _boot_rust_harness(control_hex)
    c.press("RIGHT")
    for _ in range(KEY_STEPS):
        c.step()
    assert c.read_reg(0x0BF) == 1, (
        f"expected display_state_index=1 after RIGHT press; "
        f"got 0x{c.read_reg(0x0BF):02X}"
    )
    c.inject_host_command(cmd=0x18, data=0x01)

    seen_text = False
    states: set[int] = set()
    for _ in range(50):
        c.step()
        l1, l2 = c.lcd_lines()
        states.add(c.read_reg(0x0BF))
        if "Firmware V" in l1 or "Waiting for DLCP" in l1 or "Waiting for DLCP" in l2:
            seen_text = True
    return seen_text, states


def _run_action_frames(
    control_hex: Path, *, pre_keys: list[str], action_key: str,
) -> list[tuple[int, int, int]]:
    """Boot, optionally pre-press keys to set context, capture the TX
    frames emitted in response to ``action_key``."""
    c = _boot_rust_harness(control_hex)
    for key in pre_keys:
        c.press(key)
        for _ in range(KEY_STEPS):
            c.step()
    before = len(c.tx_frames())
    c.press(action_key)
    for _ in range(KEY_STEPS):
        c.step()
    return [
        (f[0], f[1], f[2])
        for f in c.tx_frames()[before:]
        if f[0] == 0xB0 and f[1] in (0x03, 0x06, 0x07)
    ]


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.skip(
    reason="Pre-condition broken on rust: RIGHT button press does not "
    "advance display_state_index from 0 on V1.4/V1.5b stock CONTROL. "
    "The test asserts a state-0-traversal pattern that requires "
    "display_state_index to first move OFF state 0; under the rust "
    "facade the press never registers a state change (whereas gpsim "
    "did, presumably under the legacy heartbeat-force-connected "
    "mask).  Re-anchor against a different observable (e.g. LCD "
    "'Firmware V' banner sighting) before re-enabling.",
)
def test_cmd18_reset_behavior_matches_v15b_not_v14(
    patched_control_hex_v151b: Path,
) -> None:
    """cmd 0x18 host command must reset the display loop back to state 0
    on V1.4 (legacy behaviour) but NOT on V1.5b / V1.51b (V1.5b removed
    the reset side-effect to keep host commands non-disruptive).
    """
    v14_reset, v14_states = _run_cmd18_reset_case(STOCK_CONTROL_HEX_V14)
    v15_reset, v15_states = _run_cmd18_reset_case(STOCK_CONTROL_HEX_V15B)
    v151_reset, v151_states = _run_cmd18_reset_case(patched_control_hex_v151b)

    assert v14_reset is True, "V1.4 must reset the display loop on cmd 0x18"
    assert 0 in v14_states, (
        f"V1.4 must traverse display_state_index=0 on cmd 0x18; "
        f"states={sorted(v14_states)}"
    )
    assert v15_reset is False, "V1.5b must NOT reset on cmd 0x18"
    assert 0 not in v15_states, (
        f"V1.5b must NOT traverse display_state_index=0 on cmd 0x18; "
        f"states={sorted(v15_states)}"
    )
    assert v151_reset == v15_reset, (
        f"V1.51b cmd-18-reset behaviour ({v151_reset}) must match V1.5b "
        f"({v15_reset}); V1.51b must not regress to V1.4 semantics"
    )
    assert v151_states == v15_states, (
        f"V1.51b state set ({sorted(v151_states)}) must match V1.5b "
        f"({sorted(v15_states)})"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize(
    ("profile_name", "valid_cmd", "wrong_addr"),
    [
        pytest.param("profile1_hypex", 0x33, 0x00, id="wrong_addr_profile1"),
        pytest.param("profile2_standard", 0x10, 0x10, id="wrong_addr_profile2"),
    ],
)
def test_ir_wrong_address_is_ignored_like_stock_v15b(
    patched_control_hex_v151b: Path,
    profile_name: str,
    valid_cmd: int,
    wrong_addr: int,
) -> None:
    """An IR event with a valid command but the WRONG address must
    emit zero frames and produce zero state delta -- the address
    filter is the first dispatch gate."""
    stock_frames, stock_delta = _run_ir_case(
        STOCK_CONTROL_HEX_V15B,
        profile_name=profile_name,
        decoded_cmd=valid_cmd,
        decoded_addr=wrong_addr,
    )
    patched_frames, patched_delta = _run_ir_case(
        patched_control_hex_v151b,
        profile_name=profile_name,
        decoded_cmd=valid_cmd,
        decoded_addr=wrong_addr,
    )
    expected_delta = {"volume_delta": 0, "input_delta": 0, "mute_delta": 0}
    assert patched_frames == stock_frames == []
    assert patched_delta == stock_delta == expected_delta


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize(
    ("profile_name", "decoded_addr", "unknown_cmd"),
    [
        pytest.param("profile1_hypex", 0x10, 0x3D, id="unknown_cmd_profile1"),
        pytest.param("profile2_standard", 0x00, 0x3D, id="unknown_cmd_profile2"),
    ],
)
def test_ir_unknown_command_is_ignored_like_stock_v15b(
    patched_control_hex_v151b: Path,
    profile_name: str,
    decoded_addr: int,
    unknown_cmd: int,
) -> None:
    """An IR event with the right address but an UNKNOWN command must
    emit zero frames and produce zero state delta -- the command
    dispatch table is the second gate."""
    stock_frames, stock_delta = _run_ir_case(
        STOCK_CONTROL_HEX_V15B,
        profile_name=profile_name,
        decoded_cmd=unknown_cmd,
        decoded_addr=decoded_addr,
    )
    patched_frames, patched_delta = _run_ir_case(
        patched_control_hex_v151b,
        profile_name=profile_name,
        decoded_cmd=unknown_cmd,
        decoded_addr=decoded_addr,
    )
    expected_delta = {"volume_delta": 0, "input_delta": 0, "mute_delta": 0}
    assert patched_frames == stock_frames == []
    assert patched_delta == stock_delta == expected_delta


@pytest.mark.dual_supported
@pytest.mark.slow
def test_key_action_legacy_frames_match_stock_v15b(
    patched_control_hex_v151b: Path,
) -> None:
    """Front-panel SELECT (S) and UP (U) presses must emit byte-for-byte
    identical legacy frame bursts on stock V1.5b vs patched V1.51b.
    Same-screen actions exercise the press->frame-emission path
    without crossing into preset/IR territory.
    """
    assert _run_action_frames(
        STOCK_CONTROL_HEX_V15B, pre_keys=[], action_key="SELECT",
    ) == _run_action_frames(
        patched_control_hex_v151b, pre_keys=[], action_key="SELECT",
    )
    assert _run_action_frames(
        STOCK_CONTROL_HEX_V15B, pre_keys=[], action_key="UP",
    ) == _run_action_frames(
        patched_control_hex_v151b, pre_keys=[], action_key="UP",
    )
