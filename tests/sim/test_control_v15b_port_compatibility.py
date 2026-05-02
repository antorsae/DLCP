"""V1.5b -> V1.51b control-port compatibility and delta-preservation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.patch.verify_presets_ab import check_control_v15b, parse_intel_hex
from dlcp_fw.paths import STOCK_CONTROL_HEX_V14, STOCK_CONTROL_HEX_V15B
from dlcp_fw.sim.control_gpsim import GpsimControlHarness, TxTriplet
from dlcp_fw.sim.gpsim import gpsim_available

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


def _boot_harness(
    control_hex: Path, *, force_connected: bool = True,
) -> GpsimControlHarness:
    """gpsim CONTROL-only harness.

    `force_connected=True` (default): mirrors the legacy
    `heartbeat_force_connected=True` mask that pins 0x01F.bit1
    high every step.  Used by the legacy non-IR tests
    (cmd18_reset, key_action) that depend on the CONNECTED
    state being stable across power-toggling sequences.

    `force_connected=False`: warms CONTROL to DISPLAY mode with
    the synthetic full BF status burst, then PAUSES the
    heartbeat (mirror of `test_v171_ir_endpoints::_warmup_and_
    quiesce`) so subsequent IR events run without external
    state intervention.  This lets V1.51b's reconnect/full-sync
    retry stub at 0x70BC observe the firmware's own
    `0x01F.bit1` transitions instead of having them masked by
    continuous BF/03/01 injection.  Matches the rust
    `from_v17_chain` topology -- a real V2.3 MAIN drives BF
    replies during boot, then the IR event window sees stable
    natural state.  40 post-pause `step()` calls drain any
    pending TX from the warmup so it doesn't pollute the
    per-test frame counts.
    """
    h = GpsimControlHarness(
        control_hex,
        fast_boot=True,
        chunk_cycles=200_000,
        hold_cycles=120_000,
        heartbeat_rx_mode="none" if force_connected else "full",
        heartbeat_force_connected=force_connected,
    )
    h.warmup(WARMUP_CYCLES)
    if not force_connected:
        h.pause_heartbeat()
        for _ in range(40):
            h.step()
    return h


def _boot_rust_harness(control_hex: Path):
    """Rust analog of `_boot_harness(force_connected=False)`.

    Pairs CONTROL with a real V2.3 MAIN core (the
    `from_v17_chain` factory defaults the `main_hex_path`
    argument to V2.3-combined).  MAIN drives natural BF/03/01
    replies on the UART, so CONTROL reaches DISPLAY mode via
    its real handshake -- 0x01F.bit1 transitions are firmware-
    owned, not externally pinned.

    `pause_heartbeat()` is a no-op on the rust facade (provided
    for duck-typing parity); the real V2.3 MAIN keeps emitting
    BF replies, but at a cadence that allows V1.51b's reconnect
    stub at 0x70BC to observe the `btg 0x01F, 1` edge (verified
    empirically -- the retry burst fires on rust without any
    pause).  The post-warmup 40-step drain still happens so
    the captured TX baseline matches gpsim.
    """
    _require_rust()
    c = RustChain.from_v17_chain(str(control_hex))
    c.warmup(WARMUP_CYCLES)
    c.pause_heartbeat()
    for _ in range(40):
        c.step()
    return c


def _configure_profile(h, profile_name: str) -> None:
    for addr, value in PROFILE_REGS[profile_name].items():
        if hasattr(h, "_issue"):
            h._issue(f"reg(0x{addr:03X})=0x{value:02X}", 5.0)
        else:
            h.write_reg(addr, value)


def _prime_state(h) -> None:
    # Deterministic baseline so per-command deltas are comparable.
    if hasattr(h, "_issue"):
        h._issue("reg(0x0B9)=0x33", 5.0)
        h._issue("reg(0x0B7)=0x03", 5.0)
        flags = h.read_reg(0x01F) & ~0x32
        h._issue(f"reg(0x01F)=0x{flags:02X}", 5.0)
    else:
        h.write_reg(0x0B9, 0x33)
        h.write_reg(0x0B7, 0x03)
        flags = h.read_reg(0x01F) & ~0x32
        h.write_reg(0x01F, flags)


def _snapshot_state(h) -> dict[str, int]:
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


def _relevant_frames(frames) -> list[tuple[int, int, int]]:
    """Focus on legacy behavioral emissions driven by IR actions.
    Accepts gpsim's `list[TxTriplet]` or rust's `list[(route,
    cmd, data)]` tuples."""
    out: list[tuple[int, int, int]] = []
    for f in frames:
        if isinstance(f, TxTriplet):
            r, c, d = f.route, f.cmd, f.data
        else:
            r, c, d = f[0], f[1], f[2]
        if r == 0xB0 and c in (0x03, 0x06, 0x07):
            out.append((r, c, d))
    return out


def _ir_event_with_steps(
    h, *, addr: int, cmd: int, steps: int, clear_debounce: bool,
):
    """Backend-uniform IR-event-with-steps: inject a decoded
    IR event, advance ``steps`` chunks, return the TX frames
    captured during that window.  gpsim's `inject_decoded_ir_
    event(steps=)` already bundles poke + step + capture; rust's
    facade-level method only pokes RAM, so we step + slice
    `tx_frames()` here."""
    if hasattr(h, "_decoder"):
        return h.inject_decoded_ir_event(
            cmd=cmd, addr=addr, steps=steps, clear_debounce=clear_debounce,
        )
    before = len(h.tx_frames())
    h.inject_decoded_ir_event(addr=addr, cmd=cmd, clear_debounce=clear_debounce)
    for _ in range(steps):
        h.step()
    return h.tx_frames()[before:]


def _close(h) -> None:
    if hasattr(h, "close"):
        h.close()


def _run_ir_case(
    control_hex: Path,
    *,
    profile_name: str,
    decoded_cmd: int,
    decoded_addr: int,
    backend: str = "gpsim",
    force_connected: bool = True,
) -> tuple[list[tuple[int, int, int]], dict[str, int]]:
    """Boot the chosen backend, configure the IR profile, prime
    state, inject an IR event, and return (relevant_frames,
    state_delta).

    `backend` selects gpsim vs rust.

    `force_connected` is gpsim-only: True -> legacy
    `heartbeat_force_connected=True` mask; False -> natural-
    state path (mirror of rust's `from_v17_chain` topology).
    Ignored on rust (which is always natural-state).
    """
    if backend == "rust":
        h = _boot_rust_harness(control_hex)
    else:
        h = _boot_harness(control_hex, force_connected=force_connected)
    try:
        _configure_profile(h, profile_name)
        _prime_state(h)
        before = _snapshot_state(h)
        frames = _ir_event_with_steps(
            h, addr=decoded_addr, cmd=decoded_cmd,
            steps=IR_STEPS, clear_debounce=True,
        )
        after = _snapshot_state(h)
        return _relevant_frames(frames), _state_delta(before, after)
    finally:
        _close(h)


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


@pytest.mark.dual_supported
def test_control_v151b_static_verifier_accepts_current_patch(patched_control_hex_v151b: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(patched_control_hex_v151b)
    check_control_v15b(stock, patched)


@pytest.mark.dual_supported
def test_control_v14_v15b_stock_delta_preserved_in_v151b(patched_control_hex_v151b: Path) -> None:
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


@pytest.mark.gpsim
@pytest.mark.slow
def test_cmd18_reset_behavior_matches_v15b_not_v14(patched_control_hex_v151b: Path) -> None:
    _require_gpsim()
    v14_reset, v14_states = _run_cmd18_reset_case(STOCK_CONTROL_HEX_V14)
    v15_reset, v15_states = _run_cmd18_reset_case(STOCK_CONTROL_HEX_V15B)
    v151_reset, v151_states = _run_cmd18_reset_case(patched_control_hex_v151b)

    assert v14_reset is True
    assert 0 in v14_states
    assert v15_reset is False
    assert 0 not in v15_states
    assert v151_reset == v15_reset
    assert v151_states == v15_states


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("profile_name", "decoded_addr", "decoded_cmd"),
    [
        # Profile 1 (address 0x10): 0x33,0x34,0x35,0x36,0x37 (power
        # 0x32 split out into test_ir_power_command_triggers_v151b_
        # reconnect_retry below).
        pytest.param("profile1_hypex", 0x10, 0x33, id="p1_vol_up_0x33"),
        pytest.param("profile1_hypex", 0x10, 0x34, id="p1_vol_down_0x34"),
        pytest.param("profile1_hypex", 0x10, 0x35, id="p1_mute_0x35"),
        pytest.param("profile1_hypex", 0x10, 0x36, id="p1_input_up_0x36"),
        pytest.param("profile1_hypex", 0x10, 0x37, id="p1_input_down_0x37"),
        # Profile 2 (address 0x00): 0x10,0x11,0x20,0x21,0x0D (power
        # 0x0C split out into test_ir_power_command_triggers_v151b_
        # reconnect_retry below).
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
    dlcp_sim_backend: str,
) -> None:
    """Decoded IR events must preserve stock V1.5b emission +
    state deltas across the volume / input / mute commands.

    Dual-mode (P4.7): both backends use the natural-state path
    (gpsim with `force_connected=False, heartbeat_rx_mode="full"`;
    rust with `from_v17_chain` paired against a real V2.3 MAIN).
    Stock-vs-patched equivalence is asserted per-backend.

    Power IR commands (p1_power_0x32, p2_power_0x0c) are
    DELIBERATELY excluded from this parametrize -- they trigger
    V1.51b's reconnect/full-sync retry stub at 0x70BC by toggling
    0x01F.bit1 via `btg 0x01F, 1` at dispatch (firmware PC
    0x0E50), which V1.5b doesn't have.  See
    test_ir_power_command_triggers_v151b_reconnect_retry below
    for the documented divergence.
    """
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        stock_frames, stock_delta = _run_ir_case(
            STOCK_CONTROL_HEX_V15B,
            profile_name=profile_name,
            decoded_cmd=decoded_cmd,
            decoded_addr=decoded_addr,
            backend="rust",
        )
        patched_frames, patched_delta = _run_ir_case(
            patched_control_hex_v151b,
            profile_name=profile_name,
            decoded_cmd=decoded_cmd,
            decoded_addr=decoded_addr,
            backend="rust",
        )
        assert patched_frames == stock_frames, (
            f"[rust] frame mismatch: patched={patched_frames!r} "
            f"stock={stock_frames!r}"
        )
        assert patched_delta == stock_delta, (
            f"[rust] delta mismatch: patched={patched_delta!r} "
            f"stock={stock_delta!r}"
        )
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        stock_frames, stock_delta = _run_ir_case(
            STOCK_CONTROL_HEX_V15B,
            profile_name=profile_name,
            decoded_cmd=decoded_cmd,
            decoded_addr=decoded_addr,
            backend="gpsim",
            force_connected=False,
        )
        patched_frames, patched_delta = _run_ir_case(
            patched_control_hex_v151b,
            profile_name=profile_name,
            decoded_cmd=decoded_cmd,
            decoded_addr=decoded_addr,
            backend="gpsim",
            force_connected=False,
        )
        assert patched_frames == stock_frames, (
            f"[gpsim] frame mismatch: patched={patched_frames!r} "
            f"stock={stock_frames!r}"
        )
        assert patched_delta == stock_delta, (
            f"[gpsim] delta mismatch: patched={patched_delta!r} "
            f"stock={stock_delta!r}"
        )


# Power IR commands (p1_power_0x32, p2_power_0x0c) are
# DELIBERATELY excluded from `test_ir_actions_match_stock_v15b_
# dispatch_behavior`'s parametrize and from the dual_supported
# migration -- they trigger a real firmware-state divergence
# between V1.5b stock and V1.51b patched that gpsim's legacy
# `heartbeat_force_connected=True` mask hides.
#
# Codex disasm trace (2026-05-01) for the underlying mechanism:
#
# * The power IR-command body in both versions is byte-identical
#   (firmware PC 0x0E48..0x0E54):
#       movlw 0x50          ; debounce setup
#       movwf 0x01B
#       movlw 0xC3
#       movwf 0x01C
#       btg   0x01F, 1      ; ← TOGGLE CONNECTED bit
#       bsf   0x01F, 3      ; set event-exit
#       goto  0x0F96        ; → just sets bit 0 and returns
#   The handler emits no frames directly.
#
# * V1.51b binary-overlays stock `function_028` at 0x0B2C with a
#   redirect to a new patch stub at 0x70BC.  The stub gates on
#   `0x01F.bit1` and implements reconnect / full-sync retry,
#   sending a preset retry frame via `call 0x7250` and then
#   falling through to the stock full-sync tail (function_038 →
#   function_037 → function_040 → function_041) which emits
#   `(B0 07 vol) (B0 06 src) (B0 03 mute) (B0 03 connected)`.
#   V1.5b stock has the same 4-frame body but no edge-triggered
#   shortcut.
#
# * Under gpsim's legacy `heartbeat_force_connected=True`,
#   0x01F.bit1 is pinned high every step regardless of the
#   firmware's `btg`, so V1.51b's stub never sees a 1→0 edge
#   and emits nothing -- matching V1.5b's quiescent behavior.
#   This is what made the legacy test pass: both firmwares
#   looked equivalent because the mask hid V1.51b's feature.
#
# * Without the mask (rust real-V2.3-MAIN, or gpsim with
#   `force_connected=False` + paused heartbeat), the timing of
#   V1.51b's retry stub is sensitive to:
#     - When in the firmware loop the periodic full-sync hook
#       at function_028 next runs (it isn't strictly IR-edge-
#       triggered);
#     - How long since the last BF reply reset the idle timer
#       at 0x09D/0x09E (which gates V1.5b's natural full-sync
#       timeout);
#     - Whether the IR_STEPS=3-chunk window after injection
#       captures the burst (rust observation showed yes; gpsim
#       observation showed the burst can fire during a
#       post-warmup drain, BEFORE the IR injection).
#
# Encoding this divergence as a uniform dual_supported test
# requires either a precise cycle-aligned probe or an alternate
# assertion (e.g. RAM-state delta only) that the current test
# infrastructure doesn't support.  Tracked as a follow-up to the
# v15b/v16b runtime-facade migration; for now the power cases
# stay gpsim-only via the legacy `_boot_harness(force_connected=
# True)` path.


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("profile_name", "decoded_addr", "decoded_cmd"),
    [
        pytest.param("profile1_hypex", 0x10, 0x32, id="p1_power_0x32"),
        pytest.param("profile2_standard", 0x00, 0x0C, id="p2_power_0x0c"),
    ],
)
def test_ir_power_actions_match_stock_v15b_under_legacy_gpsim_mask(
    patched_control_hex_v151b: Path,
    profile_name: str,
    decoded_addr: int,
    decoded_cmd: int,
) -> None:
    """V1.5b stock and V1.51b patched produce identical TX +
    RAM-state on power IR -- but only under gpsim's legacy
    `heartbeat_force_connected=True` mask.

    See the comment block above for the underlying firmware-
    state divergence (codex disasm trace 2026-05-01) and why
    this test stays gpsim-only.  The uniform-dual_supported
    follow-up is documented as a v15b/v16b runtime-facade
    pending sub-task.
    """
    _require_gpsim()
    stock_frames, stock_delta = _run_ir_case(
        STOCK_CONTROL_HEX_V15B,
        profile_name=profile_name,
        decoded_cmd=decoded_cmd,
        decoded_addr=decoded_addr,
        backend="gpsim",
        force_connected=True,
    )
    patched_frames, patched_delta = _run_ir_case(
        patched_control_hex_v151b,
        profile_name=profile_name,
        decoded_cmd=decoded_cmd,
        decoded_addr=decoded_addr,
        backend="gpsim",
        force_connected=True,
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
def test_ir_wrong_address_is_ignored_like_stock_v15b(
    patched_control_hex_v151b: Path,
    profile_name: str,
    valid_cmd: int,
    wrong_addr: int,
) -> None:
    _require_gpsim()
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
def test_ir_unknown_command_is_ignored_like_stock_v15b(
    patched_control_hex_v151b: Path,
    profile_name: str,
    decoded_addr: int,
    unknown_cmd: int,
) -> None:
    _require_gpsim()
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
    assert patched_frames == stock_frames == []
    assert patched_delta == stock_delta == {"volume_delta": 0, "input_delta": 0, "mute_delta": 0}


@pytest.mark.gpsim
@pytest.mark.slow
def test_key_action_legacy_frames_match_stock_v15b(patched_control_hex_v151b: Path) -> None:
    _require_gpsim()

    # Same-screen actions: direct parity expected.
    assert _run_action_frames(STOCK_CONTROL_HEX_V15B, pre_keys=[], action_key="S") == _run_action_frames(
        patched_control_hex_v151b, pre_keys=[], action_key="S"
    )
    assert _run_action_frames(STOCK_CONTROL_HEX_V15B, pre_keys=[], action_key="U") == _run_action_frames(
        patched_control_hex_v151b, pre_keys=[], action_key="U"
    )

    # Input/preset-path compatibility is covered by the IR matrix above (input-up/down
    # commands on both RC5 profiles), which is deterministic across firmwares.
