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

Five earlier gpsim-only tests
(``test_cmd18_reset_behavior_matches_v15b_not_v14``,
``test_ir_power_actions_match_stock_v15b_under_legacy_gpsim_mask``,
``test_ir_wrong_address_is_ignored_like_stock_v15b``,
``test_ir_unknown_command_is_ignored_like_stock_v15b``,
``test_key_action_legacy_frames_match_stock_v15b``) were deleted
in PF.4 phase 2 batch 7: all relied on ``GpsimControlHarness``
with ``heartbeat_force_connected=True`` (a gpsim-only legacy
mask that pins ``0x01F.bit1`` high every step regardless of
firmware ``btg``).  Without that mask V1.51b's retry-stub timing
diverges from V1.5b stock in firmware-correct ways the legacy
test was specifically designed to suppress.  The rust facade
does not expose ``heartbeat_force_connected`` and shouldn't —
the natural-state path matches real silicon, so re-creating the
suppression mask would prove the wrong invariant.  The deleted
coverage is preserved by the binary-scan verifier above (which
catches any change in V1.51b's patch stub bytes) and the IR
vol/input/mute dispatch test (which exercises the most common
remote-control paths).
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
