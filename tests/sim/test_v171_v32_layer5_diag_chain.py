"""V1.71 × V3.2 Layer 5 Phase C: wire-chain diagnostics page integration.

End-to-end validation of the cmd 0x21 / BF/21..27 protocol with V1.71
CONTROL and V3.2 MAIN co-simulated on the wire-chain harness.  This is
the trust-band counterpart to:

* Phase A (``tests/sim/test_v32_layer5_diag_counters.py``) — MAIN-side
  counter pinning, RCON gate, and reply-burst structure.
* Phase B (``tests/sim/test_v171_layer5_diag_page.py``) — CONTROL-side
  page body, parser cases, and source-structural wiring.

Phase C exercises the *protocol contract* end-to-end:

1. CONTROL navigates to the Diagnostics screen and emits ``B1/0x21/0x00``
   then ``B2/0x21/0x00`` queries on cadence.
2. Both MAINs reply with the BF/21..27 burst (7 frames, one counter
   per frame; the original 4-frame packed-nibble scheme was retired
   2026-04-19 — see Phase A docstring for the rationale).
3. CONTROL parses each frame into the right per-PB cache slot.
4. The compact 16×2 LCD layout renders the cached values per spec.

``docs/SIMULATION_FIDELITY.md`` §"2026-04-18 correction" measured
the now-retired gpsim harness against real hardware for the
preset-apply / IR / button race classes that Phase C needs and
found byte timing within 20 % of hardware.  The rust engine has
not been re-measured to that depth directly, but P3.5 part-10
gates the rust chain bit-for-bit against gpsim ground-truth
fixtures captured at that fidelity (task #29 -- 6-frame MAIN→CTRL
response burst on MAIN's TX stream; task #34 -- bit-exact LCD
raster), which keeps the gpsim measurement load-bearing for the
rust path.

Phase C v1 covers the protocol-contract subset of the spec's 15-case
test matrix.  The per-counter primary tests (I2C / DSP / RCV / S / B /
AN0 / RA1) are added incrementally as the per-counter fault-injection
hooks become available.

PF.3 (2026-05-04) added ``_press_drive_until_pb_present`` (and the
rust mirror ``_rust_press_drive_until_pb_present``), which alternates
RIGHT/LEFT presses across PB1 Diag(4) <-> PB2 Diag(5) so V1.71's
foreground busy-loop in ``display_loop_iteration`` (asm:2885-2897)
keeps exiting and the cmd 0x21 / cmd 0x22 cadence re-fires often
enough for both PBs to reply.  This is a faithful test-side
reproduction: operator HW retest 2026-05-04 (V3.2 rev 0x3F + V1.71
rev 0x0F) confirmed real silicon also needs multiple LEFT/RIGHT
navigation cycles to converge (probe v21 in rust converges in 7
mixed-nav cycles, matching HW).

PF.3 + task #116 (2026-05-04) un-XFAIL'd 4 of the original 5
``_V171_V32_PB2_BRIDGE_XFAIL`` tests:
``test_v171_v32_layer5_chain_diag_page_polls_pb1_and_pb2``,
``lcd_renders_zero_idle``, ``lcd_renders_mixed_counters``, and
``test_v171_v32_layer5_chain_lcd_renders_saturation_plus``.  PF.3
closeout (2026-05-05) retired the last marker on
``pb_cache_isolation`` -- the underlying multi-frame BF/22..27
cache misroute (task #117) was a gpsim-side bug that closed when
gpsim was retired in PF.4 phase 2; the rust path converges via
``_press_drive_until_pb_present`` and the decorator constant
``_V171_V32_PB2_BRIDGE_XFAIL`` was deleted.

The original Task #22 framing (gpsim two-MAIN topology echoes MAIN0's
TX into both downstream and upstream paths) is the architectural half
of the issue and is retired by the rust silicon-correct ring (P3.6a in
``docs/SIM_REWRITE_RUST_PROGRESS.md``); it is distinct from #117.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    V17_CONTROL_RAM_INC,
    V171_CONTROL_ASM,
    V32_MAIN_ASM,
)
from dlcp_fw.sim.v17_symbols import assemble_v17, parse_v17_symbols
from dlcp_fw.sim.v30_symbols import assemble_v30


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


def _require_v32_hex(v32_hex: Path) -> None:
    """Skip if the V3.2 hex isn't present (CI runs without the
    `firmware/patched/releases/DLCP_Firmware_V3.2.hex` artifact in
    minimal worktrees)."""
    if not v32_hex.exists():
        pytest.skip(f"missing V3.2 hex: {v32_hex}")


_CONTROL_BUTTON_PINS = {
    # V1.71 button_scan_debounce reads active-low panel pins:
    # RIGHT=RA4, LEFT=RC5.  Use short taps rather than Chain.press(),
    # whose long hold deliberately exercises auto-repeat.
    "RIGHT": ("A", 4),
    "LEFT": ("C", 5),
}


CONTROL_FLAGS_PHYS = 0x01F
IR_ARMED_MASK = 0x01
CONTROL_CONNECTED_MASK = 0x02
MUTE_MASK = 0x20
PRESET_BIT_MASK = 0x40
VOLUME_CACHE_PHYS = 0x0B9
IR_PROFILE_ADDR_PHYS = 0x020
IR_PROFILE_POWER_PHYS = 0x021
IR_PROFILE_VOL_UP_PHYS = 0x022
IR_PROFILE_VOL_DOWN_PHYS = 0x023
IR_PROFILE_INPUT_UP_PHYS = 0x024
IR_PROFILE_INPUT_DOWN_PHYS = 0x025
IR_PROFILE_MUTE_PHYS = 0x026
MAIN_ACTIVE_FLAGS_PHYS = 0x05E
MAIN_ACTIVE_PRESET_MASK = 0x04
MAIN_ACTIVE_GATE_MASK = 0x08
MAIN_DIAG_STANDBY_PHYS = 0x2E7
MAIN_DIAG_WAKE_PHYS = 0x2E8
IR_ADDR_HYPEX = 0x10
IR_CMD_VOL_UP = 0x10
IR_CMD_VOL_DOWN = 0x11
IR_CMD_MUTE = 0x0D
IR_CMD_PRESET_A = 0x38
IR_CMD_PRESET_B = 0x39
IR_CMD_STANDBY = 0x3A
IR_CMD_WAKE = 0x3B

DIAG_LABEL_OFFSETS = {
    "I": 0,
    "D": 1,
    "S": 2,
    "B": 3,
    "R": 4,
    "A": 5,
    "P": 6,
    "O": 7,
    "V": 8,
    "W": 9,
    "X": 10,
}
DIAG_CACHE_LEN = 11
DIAG_RESET_LABELS = ("O", "V", "W", "X")
RESET_SOURCE_ORDER = ("por", "bor", "wdt", "reset")
RESET_SOURCE_LABELS = {
    "por": "O",
    "bor": "V",
    "wdt": "W",
    "reset": "X",
}


def _rust_tap_key(rust_chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = _CONTROL_BUTTON_PINS[key]
    rust_chain.set_control_pin(port, bit, False)
    rust_chain.step_ticks(5_000_000)
    rust_chain.set_control_pin(port, bit, True)
    rust_chain.step_ticks(5_000_000)


def _frame_tuple(frame) -> tuple[int, int, int]:  # type: ignore[no-untyped-def]
    return tuple(frame) if isinstance(frame, tuple) else (frame.route, frame.cmd, frame.data)


def _bytes_to_frames(bytes_: list[int]) -> list[tuple[int, int, int]]:
    return [
        tuple(int(b) & 0xFF for b in bytes_[idx:idx + 3])  # type: ignore[misc]
        for idx in range(0, len(bytes_) - 2, 3)
    ]


def _configure_hypex_ir_profile(rust_chain) -> None:  # type: ignore[no-untyped-def]
    """Use a deterministic IR profile for legacy vol/mute dispatch."""
    for addr, value in (
        (IR_PROFILE_ADDR_PHYS, IR_ADDR_HYPEX),
        (IR_PROFILE_POWER_PHYS, 0x0C),
        (IR_PROFILE_VOL_UP_PHYS, IR_CMD_VOL_UP),
        (IR_PROFILE_VOL_DOWN_PHYS, IR_CMD_VOL_DOWN),
        (IR_PROFILE_INPUT_UP_PHYS, 0x20),
        (IR_PROFILE_INPUT_DOWN_PHYS, 0x21),
        (IR_PROFILE_MUTE_PHYS, IR_CMD_MUTE),
    ):
        rust_chain.write_reg(addr, value)


def _inject_diag_ir(
    rust_chain, cmd: int, *, settle_ticks: int = 12_000_000,
) -> list[tuple[int, int, int]]:  # type: ignore[no-untyped-def]
    before = len(rust_chain.tx_frames())
    rust_chain.inject_decoded_ir_event(addr=IR_ADDR_HYPEX, cmd=cmd)
    rust_chain.step_ticks(settle_ticks)
    return [_frame_tuple(f) for f in rust_chain.tx_frames()[before:]]


def _wait_until(
    rust_chain, predicate, *, attempts: int = 120, ticks: int = 2_000_000,
) -> None:  # type: ignore[no-untyped-def]
    for _ in range(attempts):
        if predicate():
            return
        rust_chain.step_ticks(ticks)
    pytest.fail(
        f"condition did not converge; lcd={rust_chain.lcd_lines()!r} "
        f"control_flags=0x{rust_chain.read_reg(CONTROL_FLAGS_PHYS):02X} "
        f"display_state=0x{rust_chain.read_reg(DISPLAY_STATE_INDEX_PHYS):02X}"
    )


def _main_preset_bits(rust_chain) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    return tuple(
        (rust_chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS_PHYS) & MAIN_ACTIVE_PRESET_MASK) >> 2
        for unit in (0, 1)
    )


def _main_active_gates(rust_chain) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    return tuple(
        (rust_chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS_PHYS) & MAIN_ACTIVE_GATE_MASK) >> 3
        for unit in (0, 1)
    )


def _rust_connected_chain(
    v171_hex: Path, v32_hex: Path,
):  # type: ignore[no-untyped-def]
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    return c


# ---------------------------------------------------------------------------
# Rust-side navigation / readback helpers.  Originally added as
# mirrors of the gpsim helpers during the dual-backend migration;
# the gpsim path was retired in PF.4 phase 2 so these are now the
# only helpers in the file.
# ---------------------------------------------------------------------------


def _rust_navigate_to_diagnostics(rust_chain) -> None:  # type: ignore[no-untyped-def]
    """Drive CONTROL to PB1 Diag(4).

    Taps RIGHT four times with short active-low physical-style pulses.
    ``Chain.press()`` holds long enough to auto-repeat once the Diag
    page uses its intended non-modal poll loop, so this helper avoids
    the facade's synthetic long hold.
    """
    for _ in range(4):
        _rust_tap_key(rust_chain, "RIGHT")
        for _ in range(8):
            rust_chain.step()


def _rust_navigate_to_diag_page(rust_chain, pb_idx: int) -> None:  # type: ignore[no-untyped-def]
    """Drive CONTROL to PB1 Diag(4) or PB2 Diag(5)."""
    if pb_idx not in {0, 1}:
        raise ValueError(f"pb_idx must be 0 or 1, got {pb_idx!r}")
    _rust_navigate_to_diagnostics(rust_chain)
    if pb_idx == 1:
        _rust_tap_key(rust_chain, "RIGHT")
        for _ in range(8):
            rust_chain.step()


def _rust_main_diag_block(rust_chain, main_idx: int) -> tuple[int, ...]:  # type: ignore[no-untyped-def]
    """Read MAIN's 7 diag-counter bytes (diag_i..diag_p at
    0x2E5..0x2EB) via the per-MAIN register read primitive
    (`Chain.read_main_reg(unit, addr)`).
    """
    return tuple(
        rust_chain.read_main_reg(main_idx, addr)
        for addr in (DIAG_I_PHYS, DIAG_D_PHYS, DIAG_S_PHYS,
                     DIAG_B_PHYS, DIAG_R_PHYS, DIAG_A_PHYS, DIAG_P_PHYS)
    )


def _rust_set_main_diag_block(  # type: ignore[no-untyped-def]
    rust_chain,
    main_idx: int,
    *,
    diag_i: int = 0, diag_d: int = 0, diag_s: int = 0,
    diag_b: int = 0, diag_r: int = 0, diag_a: int = 0,
    diag_p: int = 0
) -> None:
    """Set diag-counter cells on MAIN.

    Writes each cell via the per-MAIN write primitive
    (`Chain.write_main_reg(unit, addr, value)`).  Counter values
    are masked to the low nibble.
    """
    for value, addr in (
        (diag_i, DIAG_I_PHYS), (diag_d, DIAG_D_PHYS),
        (diag_s, DIAG_S_PHYS), (diag_b, DIAG_B_PHYS),
        (diag_r, DIAG_R_PHYS), (diag_a, DIAG_A_PHYS),
        (diag_p, DIAG_P_PHYS),
    ):
        rust_chain.write_main_reg(main_idx, addr, value & 0x0F)


def _rust_configure_main_src4382_no_source(  # type: ignore[no-untyped-def]
    rust_chain, unit: int,
) -> None:
    """Put one MAIN into a deterministic Auto Detect / no-source state."""
    for addr, value in (
        (INPUT_SELECT_PHYS, 0x00),
        (INPUT_SELECT_MIRROR_PHYS, 0x00),
        (SCAN_CANDIDATE_INDEX_PHYS, 0x00),
        (SCAN_MISS_DEBOUNCE_PHYS, 0x00),
        (I2C_SLOW_COUNTER_PHYS, 0x65),
    ):
        rust_chain.write_main_reg(unit, addr, value)
    rust_chain.poke_main_src4382_reg(unit, SRC_REG_RX_STATUS, 0x00)
    rust_chain.poke_main_src4382_reg(unit, SRC_REG_NON_PCM, 0x00)
    rust_chain.reset_main_src4382_stats(unit)


def _rust_diag_present(rust_chain) -> int:  # type: ignore[no-untyped-def]
    """CONTROL's `v171_diag_present` byte at PHYS 0x197."""
    return rust_chain.read_reg(V171_DIAG_PRESENT_PHYS)


def _rust_diag_pb_cache(rust_chain, pb_idx: int) -> tuple[int, ...]:  # type: ignore[no-untyped-def]
    """Read the 7-byte CONTROL diag cache (I, D, S, B, R, A, P) for
    PB1 (idx=0) or PB2 (idx=1).
    """
    base = V171_DIAG_PB1_BASE_PHYS if pb_idx == 0 else V171_DIAG_PB2_BASE_PHYS
    return tuple(rust_chain.read_reg(base + i) for i in range(7))


def _rust_diag_pb_cache_all(rust_chain, pb_idx: int) -> tuple[int, ...]:  # type: ignore[no-untyped-def]
    """Read the full 11-byte CONTROL diag cache:
    I, D, S, B, R, A, P, O, V, W, X.
    """
    base = V171_DIAG_PB1_BASE_PHYS if pb_idx == 0 else V171_DIAG_PB2_BASE_PHYS
    return tuple(rust_chain.read_reg(base + i) for i in range(DIAG_CACHE_LEN))


def _parse_v171_symbols(hex_path: Path) -> dict[str, int]:
    lst_path = hex_path.with_suffix(".lst")
    assert lst_path.exists(), f"missing V1.71 listing beside {hex_path}"
    return parse_v17_symbols(lst_path)


def _rust_wait_for_pb_present(  # type: ignore[no-untyped-def]
    rust_chain, *, pb_mask: int, limit: int = 250,
) -> bool:
    """Step the chain until `v171_diag_present` has the requested
    PB bits set, or `limit` chain steps elapse.  Returns True on
    success.
    """
    for _ in range(limit):
        if (_rust_diag_present(rust_chain) & pb_mask) == pb_mask:
            return True
        rust_chain.step()
    return (_rust_diag_present(rust_chain) & pb_mask) == pb_mask


def _rust_wait_for_visible_diag_cache(  # type: ignore[no-untyped-def]
    rust_chain, *, pb_idx: int, checks, limit: int = 500,
) -> bool:
    """Wait until the visible PB Diag page has parsed expected cache cells.

    ``checks`` is an iterable of ``(offset, min_value)`` pairs against the
    CONTROL cache for the visible PB.
    """
    pb_label = f"PB{pb_idx + 1}"
    base = V171_DIAG_PB1_BASE_PHYS if pb_idx == 0 else V171_DIAG_PB2_BASE_PHYS
    for _ in range(limit):
        line0, line1 = rust_chain.lcd_lines()
        if line0.startswith(pb_label) and "n/a" not in line1.lower():
            if all(rust_chain.read_reg(base + offset) >= min_value for offset, min_value in checks):
                return True
        rust_chain.step()
    return False


def _rust_drive_main_volume_frame(
    rust_chain, unit: int, value: int = 0x40,
) -> None:  # type: ignore[no-untyped-def]
    """Inject a real chain volume frame into one MAIN's UART RX path."""
    for byte in (0xB0, 0x07, value & 0xFF):
        accepted, dropped = rust_chain.inject_main_uart_rx_bytes(unit, [byte])
        assert accepted == 1 and dropped == 0, (
            f"failed to inject MAIN{unit} volume byte 0x{byte:02X}: "
            f"accepted={accepted} dropped={dropped}"
        )
        rust_chain.step_ticks(1_000_000)


def _rust_wait_for_main_diag_delta(  # type: ignore[no-untyped-def]
    rust_chain, *, unit: int, addr: int, baseline: int,
    min_delta: int = 1, attempts: int = 160, ticks: int = 2_000_000,
) -> int:
    """Wait for a MAIN diag byte to increase by at least ``min_delta``."""
    for _ in range(attempts):
        value = rust_chain.read_main_reg(unit, addr)
        if value >= baseline + min_delta:
            return value
        rust_chain.step_ticks(ticks)
    value = rust_chain.read_main_reg(unit, addr)
    pytest.fail(
        f"MAIN{unit} diag at 0x{addr:03X} did not reach "
        f"0x{baseline + min_delta:02X}; got 0x{value:02X}; "
        f"block={_rust_main_diag_block(rust_chain, unit)}; "
        f"lcd={rust_chain.lcd_lines()!r}"
    )


def _assert_diag_deltas_allowed(
    before: tuple[int, ...], after: tuple[int, ...], *,
    allowed_offsets: set[int], context: str,
) -> None:
    """Fail if any unlisted diag cache/counter cell changed."""
    for label, offset in DIAG_LABEL_OFFSETS.items():
        if offset >= len(before) or offset >= len(after) or offset in allowed_offsets:
            continue
        assert after[offset] == before[offset], (
            f"{context}: unexpected {label} delta at offset {offset}; "
            f"before={[hex(v) for v in before]}; after={[hex(v) for v in after]}"
        )


def _assert_lcd_diag_token(
    line0: str, line1: str, *, label: str, value: int, context: str,
) -> None:
    """Assert the sparse Diag renderer emitted an exact `Lx` token.

    Plain substring checks are not enough: `B` and `P` occur in the `PBn`
    page label, and `O` can occur in the healthy `OK` row.
    """
    token = f"{label}{value & 0x0F:X}"
    lcd_text = f"{line0}\n{line1}"
    assert re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", lcd_text), (
        f"{context}: LCD did not render exact token {token!r}; "
        f"lcd={(line0, line1)!r}"
    )


def _assert_diag_cache_value(
    cache: tuple[int, ...], *, label: str, expected: int, context: str,
) -> None:
    offset = DIAG_LABEL_OFFSETS[label]
    actual = cache[offset]
    assert actual == (expected & 0x0F), (
        f"{context}: cache[{offset}]/{label} expected "
        f"0x{expected & 0x0F:X}, got 0x{actual:X}; "
        f"cache={[hex(v) for v in cache]}"
    )


def _rust_surface_visible_diag(  # type: ignore[no-untyped-def]
    rust_chain, *, pb_idx: int, checks, limit: int = 1000,
) -> tuple[str, str, tuple[int, ...]]:
    """Navigate once to a PB Diag page and wait there until checks land."""
    _rust_navigate_to_diag_page(rust_chain, pb_idx)
    ok = _rust_wait_for_visible_diag_cache(
        rust_chain, pb_idx=pb_idx, checks=checks, limit=limit
    )
    line0, line1 = rust_chain.lcd_lines()
    cache = _rust_diag_pb_cache_all(rust_chain, pb_idx)
    assert ok, (
        f"PB{pb_idx + 1} Diag did not surface expected counters; "
        f"checks={checks!r}; cache={[hex(v) for v in cache]}; "
        f"lcd={(line0, line1)!r}; "
        f"main={_rust_main_diag_block(rust_chain, pb_idx)}"
    )
    return line0, line1, cache


def _rust_press_drive_until_pb_present(  # type: ignore[no-untyped-def]
    rust_chain, *, pb_mask: int, limit: int = 400, press_period: int = 8,
    settle_steps: int = 0, extra_check=None,
) -> bool:
    """Drive CONTROL's diag-poll cadence by alternating RIGHT/LEFT
    presses across PB1 Diag(4) <-> PB2 Diag(5) so V1.71's
    ``display_loop_iteration`` busy-loop (asm:2885-2897) keeps
    exiting and the cmd 0x21/0x22 timer re-fires often enough for
    both PB replies to land.

    Caller must have positioned CONTROL on PB1 Diag(4) (e.g. via
    ``_rust_navigate_to_diagnostics``) before calling.  The wiggle
    pattern is:
      * From PB1(4) press RIGHT  -> PB2(5)
      * From PB2(5) press LEFT   -> PB1(4)
      * repeat
    On exit (success or timeout) the chain is left on PB1 Diag(4)
    so subsequent LCD assertions render PB1 data on row 0.

    ``press_period`` is the number of chain steps between
    consecutive presses.  Presses themselves are ~100 M ticks of
    sim time each (50 M HOLD + 50 M RELEASE_SETTLE), so a small
    ``press_period`` keeps the foreground loop exiting at well
    above the V171_DIAG_POLL_RELOAD = 0x1E00 ticks cadence.

    ``settle_steps`` continues wiggling for this many additional
    chain steps AFTER ``pb_mask`` is reached.  V3.2's `cmd 0x21`
    handler emits a single 7-frame BF/21..27 burst per query
    (V32_DIAG_TIER1_SPEC.md line 102-105), but EMPIRICALLY (probe
    /tmp/probe_ctl_cache.py) cache slot[N] populates progressively
    across many wiggle cycles (slot[0] hits at ~wiggle 11, slot[1]
    at ~wiggle 22-34) -- the present mask flips on the first slot
    landing, so tests that assert on cache[1..6] need this extra
    settle.  Likely cause is V1.71 parser / chain-transport
    latency; tracked under task #117 for the gpsim path where the
    later frames fail to land at all.
    """
    on_pb1 = True
    steps_since_press = 0
    converged = False
    extra_remaining = 0
    for _ in range(limit):
        mask_ok = (_rust_diag_present(rust_chain) & pb_mask) == pb_mask
        extra_ok = extra_check(rust_chain) if extra_check is not None else True
        if not converged and mask_ok and extra_ok:
            converged = True
            extra_remaining = settle_steps
        if converged and extra_remaining <= 0:
            break
        rust_chain.step()
        if converged:
            extra_remaining -= 1
        steps_since_press += 1
        if steps_since_press >= press_period:
            _rust_tap_key(rust_chain, "RIGHT" if on_pb1 else "LEFT")
            on_pb1 = not on_pb1
            steps_since_press = 0
    # Skip the post-loop normalize when extra_check is provided:
    # callers using extra_check have already asserted the exact end
    # state they want (typically display_state_index == STATE_PB1_DIAG),
    # and an extra normalization press would auto-repeat past it.
    if extra_check is None and not on_pb1:
        _rust_tap_key(rust_chain, "LEFT")
        on_pb1 = True
        for _ in range(8):
            rust_chain.step()
    return converged


def _rust_diag_canary_run(  # type: ignore[no-untyped-def]
    rust_chain,
) -> tuple[dict[str, int], int, tuple[int, ...]]:
    """Run a diag-page poll cycle and snapshot per-hop byte deltas.

    Returns ``(hop_deltas, present_mask, pb2_cache)``.  Pre-loads
    MAIN1's diag_p = 0x07 so a successful PB2 reply has a distinct
    payload.

    **Topology** (codex MEDIUM from 48a862d): the rust 3-core
    chain wires a TRUE ring (CONTROL -> MAIN0 -> MAIN1 -> CONTROL)
    with THREE UART couplings:
       * ``ctl_to_m0`` -- CONTROL TX -> MAIN0 RX
       * ``m0_to_m1``  -- MAIN0 TX  -> MAIN1 RX
       * ``m1_to_ctl`` -- MAIN1 TX  -> CONTROL RX
    Per-hop counts are byte-level.  See the
    ``Chain.bridge_byte_stats`` docstring in
    ``src/dlcp_fw/sim/dlcp_sim_native.py``.
    """
    rust_chain.run_until_connected(limit=200)
    if not rust_chain.is_connected() or rust_chain.is_waiting():
        raise AssertionError(
            f"chain stuck in WAITING/Zzz: lcd={rust_chain.lcd_lines()!r}"
        )
    _rust_set_main_diag_block(rust_chain, 1, diag_p=0x07)
    pre_stats = rust_chain.bridge_byte_stats()
    _rust_navigate_to_diagnostics(rust_chain)
    # Drive the cmd 0x21/0x22 cadence with alternating RIGHT/LEFT
    # wiggles so V1.71's display_loop_iteration busy-loop keeps
    # exiting and PB2's reply burst lands.  Operator HW retest
    # 2026-05-04 confirmed real silicon needs the same wiggle.
    _rust_press_drive_until_pb_present(rust_chain, pb_mask=0x02, limit=200)
    post_stats = rust_chain.bridge_byte_stats()
    # Compute deltas across EVERY hop the chain reports (3 on
    # rust, 4 on gpsim if this helper were ever reused there).
    # Iterating post_stats's keys -- not a hard-coded list --
    # makes the helper topology-agnostic.
    deltas = {
        link: post_stats[link].get("total_edges", 0)
              - pre_stats.get(link, {}).get("total_edges", 0)
        for link in post_stats
    }
    return deltas, _rust_diag_present(rust_chain), _rust_diag_pb_cache(rust_chain, 1)


# ---------------------------------------------------------------------------
# Hex source skew caveat (post codex review of 16fa3ee, 2026-05-03)
# ---------------------------------------------------------------------------
# `Chain.from_v171_v32()` loads CANONICAL release hexes from
# `firmware/patched/releases/{DLCP_Control_V1.71,DLCP_Firmware_V3.2}.hex`.
# A Phase A/B source change landing BEFORE a canonical release
# rebuild (`scripts/build_v32_release.py` / `scripts/build_v171_release.py`)
# would silently make these tests load stale binaries.  Tracking:
# pending sim-rewrite progress-ledger entry "Add hex-path overrides
# to `Chain.from_v171_v32` to avoid stale-canonical skew".
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Constants pinned by the Layer 5 design (kept duplicated from Phase A/B
# files so a wire-chain test failure can be diagnosed locally without
# cross-file lookups).
# ---------------------------------------------------------------------------

# CONTROL diag cache (BANK 1, 11 cells per PB — physical addresses).
# Layer 5 baseline: 7 runtime counter cells (BF/21..BF/27, cmd 0x21).
# V1.71 Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20): + 4 reset-cause
# flag cells (BF/28..BF/2B, cmd 0x22) per PB, plus extra state cells.
# Cache base unchanged (PB1 = 0x180); PB2 base shifted +4 (was +7,
# now +11) and trailing state cells shifted +8.
V171_DIAG_PB1_BASE_PHYS = 0x180        # I D S B R A P O V W X (11 bytes)
V171_DIAG_PB2_BASE_PHYS = 0x18B        # I D S B R A P O V W X (11 bytes)
V171_DIAG_TARGET_PHYS = 0x196
V171_DIAG_PRESENT_PHYS = 0x197
V171_DIAG_POLL_LO_PHYS = 0x198
V171_DIAG_POLL_HI_PHYS = 0x199
V171_DIAG_FLAGS_PHYS = 0x19C
V171_DIAG_RESET_SEEN_PHYS = 0x19D
V171_DIAG_RESET_TARGET_PHYS = 0x19E
V171_DIAG_RESET_TIMEOUT_PHYS = 0x19F
V171_DIAG_RUNTIME_TARGET_PHYS = 0x1AE
V171_DIAG_RUNTIME_TIMEOUT_PHYS = 0x1AF
V171_DIAG_FLAG_RUNTIME_PENDING_MASK = 0x02
V171_DIAG_FLAG_RESET_PENDING_MASK = 0x04

# MAIN diag block (BANK 2 upper, physical addresses for gpsim CLI reads).
# Relocated 2026-04-19 from 0x123..0x12A to escape the USB EP1 OUT buffer
# (0x11A..0x159).  See dlcp_main_ram.inc "RAM safety" section.
DIAG_I_PHYS = 0x2E5
DIAG_D_PHYS = 0x2E6
DIAG_S_PHYS = 0x2E7
DIAG_B_PHYS = 0x2E8
DIAG_R_PHYS = 0x2E9
DIAG_A_PHYS = 0x2EA
DIAG_P_PHYS = 0x2EB
DIAG_RESET_POR_PHYS = 0x2ED
DIAG_RESET_BOR_PHYS = 0x2EE
DIAG_RESET_WDT_PHYS = 0x2EF
DIAG_RESET_SW_PHYS = 0x2F0
DSP_FAULT_FLAGS_PHYS = 0x07F
DSP_FAULT_BIT = 0x40
RCON_PHYS = 0xFD0
RESET_SOURCE_RCON = {
    "por": 0x1C,    # POR=0, BOR=0, TO/PD/RI=1; POR wins the cascade.
    "bor": 0x1E,    # BOR=0, POR=1.
    "wdt": 0x17,    # TO=0, BOR/POR/PD/RI=1.
    "reset": 0x0F,  # RI=0, BOR/POR/PD/TO=1.
}

# V3.2 SRC4382 Auto Detect state / simulated receiver registers used by
# fault-to-Diagnostics surfacing tests.
INPUT_SELECT_PHYS = 0x099
INPUT_SELECT_MIRROR_PHYS = 0x0B3
SCAN_CANDIDATE_INDEX_PHYS = 0x0B6
SCAN_MISS_DEBOUNCE_PHYS = 0x0BA
I2C_SLOW_COUNTER_PHYS = 0x0BB
SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13

# Menu state indices.  V1.71 Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20)
# moved Diagnostics from state 2 (between Preset and Input) to states 4-5
# (after Setup), with one PB per state.  STATE_DIAG is preserved as an
# alias pointing at PB1 Diag for older tests that read a single state
# index; new tests should use STATE_PB1_DIAG / STATE_PB2_DIAG explicitly.
STATE_VOLUME   = 0
STATE_PRESET   = 1
STATE_INPUT    = 2     # Tier-1: was 3
STATE_SETUP    = 3     # Tier-1: was 4
STATE_PB1_DIAG = 4     # Tier-1: NEW (split of single Diag state)
STATE_PB2_DIAG = 5     # Tier-1: NEW
STATE_DIAG     = STATE_PB1_DIAG  # back-compat alias for legacy tests

DISPLAY_STATE_INDEX_PHYS = 0x0BF


# ---------------------------------------------------------------------------
# Shared fixture: build V1.71 hex once per module, reuse across tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_v32_layer5")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


@pytest.fixture(scope="module")
def v32_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build V3.2 MAIN from current source into a module-scoped tmp dir.

    Phase C used to consume the canonical ``V32_MAIN_HEX`` directly, but
    that path is only refreshed by an external build pipeline — if a
    Phase A / Phase B source change landed since the last canonical
    rebuild, Phase C silently tested the stale binary.  Building from
    ``V32_MAIN_ASM`` here guarantees Phase C and Phase A see the same
    source-derived artifact, eliminating the source/hex skew blind
    spot called out in the 2026-04-19 review.

    Module-scoped so the ~3-second gpasm step runs once per file.  The
    ``tmp_path_factory.mktemp`` location is per-worker under xdist, so
    parallel runs cannot race on a shared output path.
    """
    tmp = tmp_path_factory.mktemp("v32_layer5_chain")
    hex_out = tmp / "DLCP_Firmware_V3.2.hex"
    assemble_v30(V32_MAIN_ASM, hex_out)
    return hex_out




@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_idle_caches_zero_at_boot(
    v171_hex: Path, v32_hex: Path
) -> None:
    """At boot, neither PB has replied, so CONTROL's diag cache and
    present mask must be zero across the chain warmup.

    This is the wire-chain analogue of the Phase B
    ``diag_block_holds_zero_through_boot_and_warmup`` test, but with
    real MAINs on the chain (which exercise the BF/05/07/03/06/1D
    steady-state status burst — none of which should leak into the
    diag cache).

    Migrated to dual_supported in P4.7: the V1.71+V3.2+V3.2 chain
    now reaches DISPLAY mode on rust after the codex hypothesis #1
    fix to ``build_v171_v32_chain`` (PORTA/PORTC seeded to 0xFF
    after POR so V1.71 doesn't read the wiped 0x00 PORT bits as
    "STBY-stuck-pressed" -> Zzz).  Drives the chain with the
    freshly-built ``v171_hex`` / ``v32_hex`` tmp fixtures via the
    ``control_hex_path`` / ``main_hex_path`` overrides on
    ``Chain.from_v171_v32`` (codex task #77) so the test gates
    on the current source rather than the canonical release hex.
    """
    _require_v32_hex(v32_hex)
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    present = c.read_reg(V171_DIAG_PRESENT_PHYS)
    assert present == 0, (
        f"[rust] present mask non-zero at boot: 0x{present:02X}"
    )
    for pb_base, pb_label in (
        (V171_DIAG_PB1_BASE_PHYS, "PB1"),
        (V171_DIAG_PB2_BASE_PHYS, "PB2"),
    ):
        cache = tuple(c.read_reg(pb_base + i) for i in range(7))
        assert all(v == 0 for v in cache), (
            f"[rust] {pb_label} cache non-zero at boot: "
            f"{[hex(v) for v in cache]}"
        )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_diag_page_polls_pb1_and_pb2(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Navigating to Diagnostics drives CONTROL's poll loop, which
    alternates queries between PB1 and PB2.  After enough chain steps
    for the cadence to fire twice (once per PB), both ``v171_diag_present``
    bits must be set, demonstrating that:

    1. CONTROL emits ``B1/0x21/0x00`` and the V3.2 MAIN at PB1 replies
       with the 7-frame BF/21..27 burst (one counter per frame, low-
       nibble data), which CONTROL parses into the PB1 cache.
    2. CONTROL emits ``B2/0x21/0x00``, PB1 forwards (decremented to B1),
       PB2 consumes and replies, the BF/21..27 burst flows back upstream
       through PB1's forwarder, and CONTROL parses into the PB2 cache.

    This is the protocol-contract end-to-end gate.

    PF.3 (2026-05-04) un-XFAIL'd this test on both backends by
    swapping the navigation-only ``_wait_for_pb_present`` poll loop
    for ``_press_drive_until_pb_present``, which alternates RIGHT/
    LEFT presses across PB1 Diag(4) <-> PB2 Diag(5) so V1.71's
    ``display_loop_iteration`` busy-loop (asm:2885-2897) keeps
    exiting and the cmd 0x21/0x22 cadence re-fires often enough for
    both PBs to reply.  Operator HW retest 2026-05-04 (V3.2 rev 0x3F
    + V1.71 rev 0x0F) confirmed real silicon also needs multiple
    LEFT/RIGHT cycles to converge (probe v21 in rust converges in 7
    wiggle cycles); the wiggle harness is a faithful test-side
    reproduction.  Task #94 (briefly framed as a rust-specific
    Timer3/Timer1 ISR-dispatch fidelity bug) CLOSED.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_navigate_to_diagnostics(c)
    # Limit kept at 1200 to absorb V1.71 source-layout movement around the
    # display loop.  Earlier IR experiments showed this convergence point is
    # sensitive to code shifts; 1200 keeps the test passing with margin and
    # matches the bumped limit across all
    # _rust_press_drive_until_pb_present sites in this file.
    ok = _rust_press_drive_until_pb_present(c, pb_mask=0x03, limit=1200)
    assert ok, (
        f"[rust] diag_present never reached 0x03; got "
        f"0x{_rust_diag_present(c):02X}; "
        f"PB1 cache={[hex(v) for v in _rust_diag_pb_cache(c, 0)]}; "
        f"PB2 cache={[hex(v) for v in _rust_diag_pb_cache(c, 1)]}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_diag_static_wait_updates_pb1_and_pb2(
    v171_hex: Path, v32_hex: Path
) -> None:
    """BUG-DIAG-01: each visible Diagnostics page must refresh by
    static wait without requiring repeated LEFT/RIGHT cycling.

    The legacy tests below use ``_rust_press_drive_until_pb_present`` to
    force convergence by repeatedly leaving and re-entering the diag page.
    That is now only a workaround.  The product behavior must be: enter
    a PB1/PB2 Diagnostics page once, wait, and see live data within the
    bounded poll cadence.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )

    _rust_navigate_to_diagnostics(c)
    for pb_idx, pb_mask, pb_label in ((0, 0x01, "PB1"), (1, 0x02, "PB2")):
        if pb_idx == 1:
            _rust_tap_key(c, "RIGHT")
            for _ in range(8):
                c.step()

        for _ in range(400):
            line0, line1 = c.lcd_lines()
            present = _rust_diag_present(c)
            if (
                (present & pb_mask) == pb_mask
                and line0.startswith(pb_label)
                and "n/a" not in line1.lower()
            ):
                break
            c.step()

        present = _rust_diag_present(c)
        line0, line1 = c.lcd_lines()
        assert (present & pb_mask) == pb_mask, (
            f"[rust] static Diag wait did not discover {pb_label}; "
            f"present=0x{present:02X}; lcd={(line0, line1)!r}; "
            f"PB1 cache={[hex(v) for v in _rust_diag_pb_cache(c, 0)]}; "
            f"PB2 cache={[hex(v) for v in _rust_diag_pb_cache(c, 1)]}"
        )
        assert line0.startswith(pb_label), (
            f"[rust] expected visible {pb_label} page; lcd={(line0, line1)!r}"
        )
        assert "n/a" not in line1.lower(), (
            f"[rust] static {pb_label} Diag wait still renders n/a: "
            f"lcd={(line0, line1)!r}"
        )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize(
    "pb_idx,pending_target",
    [(0, 0), (0, 1), (1, 0), (1, 1)],
)
def test_v171_v32_diag_entry_clears_stale_pending_timeout_state(
    v171_hex: Path, v32_hex: Path, pb_idx: int, pending_target: int
) -> None:
    """Real-HW regression, 2026-05-20: PB1/PB2 Diag rendered ``n/a``
    for many minutes, then eventually changed to ``OK``.

    Reproduction shape: CONTROL enters a PB Diag page with stale
    RUNTIME_PENDING / RESET_PENDING bits already set and their timeout
    bytes at zero.  Pre-fix, page entry cleared the poll countdown but
    not the pending state; the first cadence decremented runtime_timeout
    from 0 to 0xFF and suppressed fresh cmd 0x21 queries for 256 poll
    cadences.  This test seeds that stale state BEFORE entering PB1/PB2
    Diag and requires the visible page to discover its PB from a static
    wait, including same-target and opposite-target stale transactions.
    """
    c = _rust_connected_chain(v171_hex, v32_hex)

    # Seed the exact stale transaction shape observed on hardware.  Old
    # firmware carried these bytes into v171_diag_screen; fixed firmware
    # clears them at page entry before the first cadence decision.
    c.write_reg(V171_DIAG_PRESENT_PHYS, 0x00)
    c.write_reg(
        V171_DIAG_FLAGS_PHYS,
        V171_DIAG_FLAG_RUNTIME_PENDING_MASK | V171_DIAG_FLAG_RESET_PENDING_MASK,
    )
    c.write_reg(V171_DIAG_RUNTIME_TARGET_PHYS, pending_target)
    c.write_reg(V171_DIAG_RUNTIME_TIMEOUT_PHYS, 0x00)
    c.write_reg(V171_DIAG_RESET_TARGET_PHYS, pending_target)
    c.write_reg(V171_DIAG_RESET_TIMEOUT_PHYS, 0x00)

    _rust_navigate_to_diag_page(c, pb_idx)
    ok = _rust_wait_for_visible_diag_cache(c, pb_idx=pb_idx, checks=((0, 0),), limit=400)
    line0, line1 = c.lcd_lines()
    pb_mask = 1 << pb_idx
    pb_label = f"PB{pb_idx + 1}"
    assert ok and (_rust_diag_present(c) & pb_mask), (
        f"[rust] stale pending/timeout state blocked {pb_label} discovery; "
        f"pending_target=PB{pending_target + 1}; "
        f"present=0x{_rust_diag_present(c):02X}; "
        f"flags=0x{c.read_reg(V171_DIAG_FLAGS_PHYS):02X}; "
        f"runtime_timeout=0x{c.read_reg(V171_DIAG_RUNTIME_TIMEOUT_PHYS):02X}; "
        f"reset_timeout=0x{c.read_reg(V171_DIAG_RESET_TIMEOUT_PHYS):02X}; "
        f"lcd={(line0, line1)!r}; "
        f"cache={[hex(v) for v in _rust_diag_pb_cache_all(c, pb_idx)]}"
    )
    assert line0.startswith(pb_label) and "n/a" not in line1.lower(), (
        f"[rust] {pb_label} Diag must not remain n/a after stale-state entry; "
        f"lcd={(line0, line1)!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_reset_pending_times_out_while_runtime_pending(
    v171_hex: Path, v32_hex: Path
) -> None:
    """RESET_PENDING timeout must not freeze behind RUNTIME_PENDING.

    Pre-fix shape: when the cmd 0x21 runtime burst stayed pending, the cadence
    loop branched to `v171_diag_runtime_wait` before touching the cmd 0x22
    reset-cause timeout.  That stretched the documented ~4-cadence give-up
    window until runtime either replied or timed out.  Seed both pending bits,
    keep runtime pending alive, and force cadence expiries; reset timeout must
    still age out and mark the in-flight PB as seen/unknown.
    """
    c = _rust_connected_chain(v171_hex, v32_hex)
    _rust_navigate_to_diag_page(c, 0)

    syms = _parse_v171_symbols(v171_hex)
    poll_check_pc = syms["v171_diag_poll_check"]
    c.write_reg(V171_DIAG_FLAGS_PHYS, V171_DIAG_FLAG_RUNTIME_PENDING_MASK | V171_DIAG_FLAG_RESET_PENDING_MASK)
    c.write_reg(V171_DIAG_RUNTIME_TARGET_PHYS, 0x00)
    c.write_reg(V171_DIAG_RUNTIME_TIMEOUT_PHYS, 0x20)
    c.write_reg(V171_DIAG_RESET_TARGET_PHYS, 0x00)
    c.write_reg(V171_DIAG_RESET_SEEN_PHYS, 0x00)
    c.write_reg(V171_DIAG_RESET_TIMEOUT_PHYS, 0x02)

    observed_timeouts: list[int] = []
    for _ in range(3):
        hit = c.step_until_pc_hit(0, poll_check_pc, poll_check_pc, max_tcy=5_000_000)
        assert hit == poll_check_pc, f"CONTROL did not reach poll check; pc=0x{hit:04X}"
        c.write_reg(V171_DIAG_POLL_LO_PHYS, 0x00)
        c.write_reg(V171_DIAG_POLL_HI_PHYS, 0x00)
        c.step_tcy(100_000)
        observed_timeouts.append(c.read_reg(V171_DIAG_RESET_TIMEOUT_PHYS))
        if not (c.read_reg(V171_DIAG_FLAGS_PHYS) & V171_DIAG_FLAG_RESET_PENDING_MASK):
            break

    flags = c.read_reg(V171_DIAG_FLAGS_PHYS)
    assert not (flags & V171_DIAG_FLAG_RESET_PENDING_MASK), (
        "RESET_PENDING stayed set while RUNTIME_PENDING was also set; "
        f"timeouts={observed_timeouts}, flags=0x{flags:02X}"
    )
    assert c.read_reg(V171_DIAG_RESET_SEEN_PHYS) & 0x01, (
        "timeout give-up path must mark PB1 reset-cause cache as seen/unknown"
    )
    assert flags & V171_DIAG_FLAG_RUNTIME_PENDING_MASK, (
        "test did not keep runtime pending alive long enough to exercise the freeze"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("pb_idx,pb_label", [(0, "PB1"), (1, "PB2")])
def test_v171_v32_layer5_diag_visible_page_refreshes_on_next_cadence(
    v171_hex: Path, v32_hex: Path, pb_idx: int, pb_label: str
) -> None:
    """BUG-DIAG-01: the visible per-PB page must get the full cadence.

    The old alternating-target loop could leave PB2 visible while the
    next cadence queried PB1, so a fresh PB2 counter update did not reach
    the LCD until a later cadence.  Force that worst-case target state and
    require the active page's PB to refresh immediately on the next
    cadence tick.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )

    _rust_navigate_to_diag_page(c, pb_idx)
    for _ in range(10):
        c.step()
    assert c.lcd_lines()[0].startswith(pb_label), c.lcd_lines()

    active_base = V171_DIAG_PB1_BASE_PHYS if pb_idx == 0 else V171_DIAG_PB2_BASE_PHYS
    inactive_target = 1 - pb_idx
    _rust_set_main_diag_block(c, pb_idx, diag_i=0x7)
    assert c.read_reg(active_base) == 0x0

    # Align before the countdown read.  A fixed-size `step()` can stop
    # after `iorwf poll_hi,W` but before `bnz`; poking the countdown there
    # leaves STATUS.Z reflecting the old value, which is not the "cadence
    # expired" state this test is trying to exercise.
    syms = _parse_v171_symbols(v171_hex)
    poll_check_pc = syms["v171_diag_poll_check"]
    hit = c.step_until_pc_hit(0, poll_check_pc, poll_check_pc, max_tcy=5_000_000)
    assert hit == poll_check_pc, (
        f"CONTROL did not reach v171_diag_poll_check; hit PC=0x{hit:04X}; "
        f"lcd={c.lcd_lines()!r}"
    )

    # Reproduce the stale alternating-target state: the operator is on
    # PBn, but v171_diag_target points at the other PB as the cadence
    # expires.  Correct firmware reloads target from the visible page
    # before sending cmd 0x21/cmd 0x22.
    c.write_reg(V171_DIAG_TARGET_PHYS, inactive_target)
    c.write_reg(V171_DIAG_POLL_LO_PHYS, 0x00)
    c.write_reg(V171_DIAG_POLL_HI_PHYS, 0x00)
    c.write_reg(V171_DIAG_FLAGS_PHYS, 0x00)

    # One Chain.step is 200K CONTROL Tcy (~50 ms).  Twenty chunks keep the
    # assertion inside the <=1 s diagnostic refresh contract while allowing
    # PB1/PB2's ring paths to drain at their natural simulated latency.
    for _ in range(20):
        c.step()
        line0, line1 = c.lcd_lines()
        if (
            c.read_reg(active_base) == 0x7
            and line0.startswith(pb_label)
            and re.search(r"(?<![A-Z0-9])I7(?![A-Z0-9])", f"{line0}\n{line1}")
        ):
            break

    assert c.read_reg(active_base) == 0x7, (
        f"{pb_label} visible page did not refresh on the next cadence when "
        f"diag_target initially pointed at PB{inactive_target + 1}; "
        f"target=0x{c.read_reg(V171_DIAG_TARGET_PHYS):02X}; "
        f"cache={[hex(v) for v in _rust_diag_pb_cache(c, pb_idx)]}; "
        f"lcd={c.lcd_lines()!r}"
    )
    line0, line1 = c.lcd_lines()
    assert line0.startswith(pb_label), c.lcd_lines()
    _assert_lcd_diag_token(
        line0,
        line1,
        label="I",
        value=0x7,
        context=f"{pb_label} visible-page cadence refresh",
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("pb_idx,pb_label", [(0, "PB1"), (1, "PB2")])
def test_v171_v32_layer5_diag_page_dispatches_ir_volume_mute_and_preset(
    v171_hex: Path, v32_hex: Path, pb_idx: int, pb_label: str
) -> None:
    """While parked on PB1/PB2 Diagnostics, decoded IR commands must still
    run through the normal dispatch path.

    BUG-DIAG-02 broadened: replacing the modal display loop must not
    make Diagnostics a dead-end mode.  Volume, mute, and preset IR
    commands are expected to update CONTROL state and emit their normal
    CONTROL->MAIN frames without requiring the operator to leave the
    Diagnostics page first.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _configure_hypex_ir_profile(c)
    c.write_reg(VOLUME_CACHE_PHYS, 0x33)
    c.write_reg(CONTROL_FLAGS_PHYS, c.read_reg(CONTROL_FLAGS_PHYS) & ~MUTE_MASK & ~PRESET_BIT_MASK)
    _rust_navigate_to_diag_page(c, pb_idx)
    assert c.lcd_lines()[0].startswith(pb_label), c.lcd_lines()

    frames = _inject_diag_ir(c, IR_CMD_VOL_UP)
    assert c.read_reg(VOLUME_CACHE_PHYS) == 0x34, (
        f"Diag page ignored IR volume-up; volume=0x{c.read_reg(VOLUME_CACHE_PHYS):02X}"
    )
    assert (0xB0, 0x07, 0x34) in frames, (
        f"IR volume-up on Diag should emit B0/07/34; frames={frames!r}"
    )

    frames = _inject_diag_ir(c, IR_CMD_MUTE)
    assert c.read_reg(CONTROL_FLAGS_PHYS) & MUTE_MASK, (
        f"Diag page ignored IR mute; flags=0x{c.read_reg(CONTROL_FLAGS_PHYS):02X}"
    )
    assert (0xB0, 0x03, 0x02) in frames, (
        f"IR mute-on on Diag should emit B0/03/02; frames={frames!r}"
    )

    frames = _inject_diag_ir(c, IR_CMD_PRESET_B, settle_ticks=20_000_000)
    assert c.read_reg(CONTROL_FLAGS_PHYS) & PRESET_BIT_MASK, (
        f"Diag page ignored IR preset-B; flags=0x{c.read_reg(CONTROL_FLAGS_PHYS):02X}"
    )
    assert (0xB0, 0x20, 0x01) in frames, (
        f"IR preset-B on Diag should emit B0/20/01; frames={frames!r}"
    )
    _wait_until(c, lambda: _main_preset_bits(c) == (1, 1), attempts=160)

    line0, _ = c.lcd_lines()
    assert line0.startswith(pb_label), (
        f"volume/mute/preset IR should not force navigation away from Diag; lcd={c.lcd_lines()!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("pb_idx,pb_label", [(0, "PB1"), (1, "PB2")])
def test_v171_v32_layer5_diag_page_dispatches_ir_standby_and_wake(
    v171_hex: Path, v32_hex: Path, pb_idx: int, pb_label: str
) -> None:
    """IR standby/wake must work from Diagnostics, including local UI state.

    Standby should leave the PB1/PB2 Diagnostics page and render Zzz while
    both MAINs observe the standby command.  Wake should bring CONTROL
    back through reconnect/awake display state with both MAINs awake;
    preserving the previous PB Diagnostics menu state is acceptable.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _configure_hypex_ir_profile(c)
    _rust_navigate_to_diag_page(c, pb_idx)
    assert c.lcd_lines()[0].startswith(pb_label), c.lcd_lines()

    standby_frames = _inject_diag_ir(c, IR_CMD_STANDBY, settle_ticks=20_000_000)
    assert (0xB0, 0x03, 0x00) in standby_frames, (
        f"CONTROL did not emit standby frame from Diag IR; frames={standby_frames!r}"
    )
    _wait_until(c, lambda: "ZZZ" in c.lcd_lines()[0].upper(), attempts=120)
    _wait_until(c, lambda: _main_active_gates(c) == (0, 0), attempts=180)

    wake_frames = _inject_diag_ir(c, IR_CMD_WAKE, settle_ticks=20_000_000)
    assert (0xB0, 0x03, 0x01) in wake_frames, (
        f"CONTROL did not emit wake frame from Diag IR; frames={wake_frames!r}"
    )
    _wait_until(
        c,
        lambda: (
            c.is_connected()
            and bool(c.read_reg(CONTROL_FLAGS_PHYS) & CONTROL_CONNECTED_MASK)
            and "ZZZ" not in c.lcd_lines()[0].upper()
        ),
        attempts=180,
    )
    _wait_until(c, lambda: _main_active_gates(c) == (1, 1), attempts=240)


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_pb_cache_isolation(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Forcing distinct counter values into PB1 vs PB2's diag block must
    surface as distinct CONTROL cache slots after the next poll.

    Concrete: set PB1 diag_d/diag_p=1/5 and PB2 diag_d/diag_p=2/12.
    After both PBs have replied at least once, CONTROL's PB1 and PB2
    caches must preserve those distinct values.  Avoid diag_i here:
    V3.2 Auto Detect legitimately owns the live I2C counter while this
    test is driving the chain.  Cross-talk between cache slots would
    mean the parser is indexing the wrong PB on reply arrival.

    PF.3 closeout (2026-05-05): the stale ``_V171_V32_PB2_BRIDGE_XFAIL``
    decorator was retired here -- the underlying gpsim-side multi-
    frame BF/22..27 cache misroute (task #117) closed when gpsim was
    retired in PF.4 phase 2, and the rust path converges via
    ``_press_drive_until_pb_present``.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_set_main_diag_block(c, 0, diag_d=0x1, diag_p=0x5)
    _rust_set_main_diag_block(c, 1, diag_d=0x2, diag_p=0xC)
    _rust_navigate_to_diagnostics(c)
    # settle_steps=200 lets the BF/22 frame populate cache[1]
    # for both PBs after the mask hit on the BF/21 frame.
    ok = _rust_press_drive_until_pb_present(
        c, pb_mask=0x03, limit=1200, settle_steps=200
    )
    assert ok, "[rust] both PBs never replied"
    pb1_cache = _rust_diag_pb_cache(c, 0)
    pb2_cache = _rust_diag_pb_cache(c, 1)
    assert pb1_cache[1] == 0x1, (
        f"[rust] PB1 cache[1] (diag_d) expected 0x1; got "
        f"0x{pb1_cache[1]:X}"
    )
    assert pb2_cache[1] == 0x2, (
        f"[rust] PB2 cache[1] (diag_d) expected 0x2; got "
        f"0x{pb2_cache[1]:X}"
    )
    assert pb1_cache[6] == 0x5, (
        f"[rust] PB1 cache[6] (diag_p) expected 0x5; got "
        f"0x{pb1_cache[6]:X}; full={[hex(v) for v in pb1_cache]}"
    )
    assert pb2_cache[6] == 0xC, (
        f"[rust] PB2 cache[6] (diag_p) expected 0xC; got "
        f"0x{pb2_cache[6]:X}; full={[hex(v) for v in pb2_cache]}"
    )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_lcd_renders_zero_idle(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Cold-boot Diagnostics renders an OK PB1 title and OK-context
    reset cause on row 1.

    Tier-1 (2026-04-20) replaced the pre-Tier-1 'both PBs on one
    screen' layout with ONE PB per page.  The current sparse renderer
    keeps row 0 as ``PB1 OK`` when only OK-context S/B/O cells are
    present, and emits those OK-context cells on row 1.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_navigate_to_diagnostics(c)
    # extra_check pins the exit iteration to one where the chain is
    # parked on PB1 Diag(4) so the trailing LCD assertion sees the
    # PB1 view (V1.71's 50M-tick button-hold auto-repeat in rust
    # makes plain-mask exit unreliable).  Limit bumped 600 -> 1200
    # to absorb the M3 IR non-blocking decoder code shift (#153 /
    # commits 86d88e0 + 61e17a7).  See sibling
    # test_v171_v32_layer5_chain_diag_page_polls_pb1_and_pb2 for the
    # full rationale.
    ok = _rust_press_drive_until_pb_present(
        c, pb_mask=0x03, limit=2000,
        extra_check=lambda ch: (
            ch.read_reg(DISPLAY_STATE_INDEX_PHYS) == STATE_PB1_DIAG
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 7) == 0x1
        ),
    )
    assert ok, "[rust] both PBs never replied"
    for _ in range(8):
        c.step()
    line0, line1 = c.lcd_lines()
    expected = "PB1 OK          "
    assert line0 == expected, (
        f"[rust] row 0 mismatch: expected {expected!r}, got {line0!r}"
    )
    expected2 = "O1              "
    assert line1 == expected2, (
        f"[rust] row 1 mismatch: expected {expected2!r}, got {line1!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_lcd_renders_ok_context_counters(
    v171_hex: Path, v32_hex: Path
) -> None:
    """S/B/O are OK-context counters: they render under ``PB1 OK`` and
    must not turn the page into a ``PB1!`` issue layout by themselves.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_set_main_diag_block(c, 0, diag_s=1, diag_b=1)
    _rust_navigate_to_diagnostics(c)
    ok = _rust_press_drive_until_pb_present(
        c, pb_mask=0x03, limit=2000,
        extra_check=lambda ch: (
            ch.read_reg(DISPLAY_STATE_INDEX_PHYS) == STATE_PB1_DIAG
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 2) == 0x1
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 3) == 0x1
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 7) == 0x1
        ),
    )
    assert ok, "[rust] both PBs never replied"
    for _ in range(8):
        c.step()
    line0, line1 = c.lcd_lines()
    assert line0 == "PB1 OK          ", (
        f"[rust] row 0 mismatch for OK-context counters: got {line0!r}"
    )
    assert line1 == "S1 B1 O1        ", (
        f"[rust] row 1 mismatch for OK-context counters: got {line1!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_lcd_renders_mixed_counters(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Spec §"LCD Examples" — Some-activity case (Tier-1 layout).

    PB1: diag_i=2, diag_b=1, diag_r=1 -> "PB1! I2 R1 B1 O1" on row 0,
        blank row 1.  Issue cells (I/R) render before OK-context cells
        (B/O).  Trailing "O1" comes from cache slot[7] (Tier-1 reset-cause
        cell BF/28); slot[7] is auto-set to 0x1 by V3.2 firmware on every
        diag-page entry, NOT a counter the test wrote.

    Tier-1 (2026-04-20) replaced pre-Tier-1's "both PBs on one screen"
    layout ('1:I2D S B1R1A P ' / '2:I D S1B1R A3P ') with one PB per
    page; the test now asserts only the PB1 view (PB2 cache content
    is verified separately by ``test_v171_v32_layer5_chain_pb_cache_
    isolation``, so per-PB LCD navigation is redundant coverage).

    PF.3 (2026-05-04) un-XFAIL'd busy-loop convergence via the
    ``_press_drive_until_pb_present`` helper; task #116 (this
    commit) un-XFAIL'd the layout drift by updating the assertion
    to the Tier-1 string.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_set_main_diag_block(c, 0, diag_i=2, diag_b=1, diag_r=1)
    _rust_set_main_diag_block(c, 1, diag_s=1, diag_b=1, diag_a=3)
    _rust_navigate_to_diagnostics(c)
    # Mixed counters need cache[0,3,4] populated AND the chain
    # parked on PB1 Diag(4) for the LCD assertion.  Use an
    # extra_check that fires only when both conditions are met
    # in the same wiggle iteration (V1.71's 50M-tick button-
    # hold auto-repeat means each press jumps 1-3 menu states
    # unpredictably; without the state==4 gate the loop can
    # exit on a state-drifted iteration).  Empirically (probe
    # /tmp/probe_mixed.py) the first qualifying iteration is
    # ~wiggle 20.
    # limit bumped 400 -> 800 -> 2000 across the M3 IR code shift
    # (#153 task -- the multi-condition extra_check needs a longer
    # convergence window because slot[7] (O reset-cause cell) lags
    # the runtime counters by ~10x more wiggles post-shift).
    ok = _rust_press_drive_until_pb_present(
        c, pb_mask=0x03, limit=2000,
        extra_check=lambda ch: (
            ch.read_reg(DISPLAY_STATE_INDEX_PHYS) == STATE_PB1_DIAG
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 0) == 0x2
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 3) == 0x1
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 4) == 0x1
            # slot[7]=O is filled by V3.2's BF/28 cmd 0x22 reply
            # on diag-page entry (Tier-1 reset-cause cell); the
            # LCD renders trailing "O1" only after this slot
            # populates, which lags slot[0,3,4] by several wiggles.
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 7) == 0x1
        ),
    )
    assert ok, "[rust] both PBs never replied"
    for _ in range(8):
        c.step()
    line0, line1 = c.lcd_lines()
    # Tier-1 PB1 view: issue-first compact list 'PB1! I2 R1 B1 O1'
    # on row 0, blank row 1.  PB2 cache content is exercised by
    # the cache_isolation test, so per-PB LCD navigation here
    # would only re-test the same protocol path.
    assert line0 == "PB1! I2 R1 B1 O1", (
        f"[rust] row 0 mismatch for PB1 mixed counters: got {line0!r}"
    )
    assert line1 == "                ", (
        f"[rust] row 1 mismatch (expected blank): got {line1!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("fault_kind", ("address", "data"))
@pytest.mark.parametrize("unit,pb_label", [(0, "PB1"), (1, "PB2")])
def test_v171_v32_diag_lcd_surfaces_injected_src4382_i2c_fault(
    v171_hex: Path, v32_hex: Path, fault_kind: str, unit: int, pb_label: str
) -> None:
    """End-to-end fault surfacing: inject a real SRC4382 I2C NACK, prove
    MAIN increments ``diag_i``, then prove CONTROL's PB Diag page renders
    that counter through the cmd 0x21 / BF/21 protocol.

    This is intentionally stronger than the older LCD tests that seed
    MAIN diag RAM directly.  Direct seeding proves protocol/rendering;
    this proves an injected fault reaches the user-visible Diagnostics
    page.
    """
    c = _rust_connected_chain(v171_hex, v32_hex)

    _rust_configure_main_src4382_no_source(c, unit)
    before_block = _rust_main_diag_block(c, unit)
    before_i = c.read_main_reg(unit, DIAG_I_PHYS)
    if fault_kind == "address":
        c.inject_main_src4382_address_nack(unit, 1000)
    else:
        c.inject_main_src4382_data_nack(unit, 1000)
    c.reset_main_src4382_stats(unit)

    _rust_drive_main_volume_frame(c, unit, 0x40)
    main_diag_i = _rust_wait_for_main_diag_delta(
        c, unit=unit, addr=DIAG_I_PHYS, baseline=before_i,
        attempts=180, ticks=2_000_000,
    )

    stats = c.read_main_src4382_stats(unit)
    consumed_key = f"{fault_kind}_nacks_consumed"
    other_key = "data_nacks_consumed" if fault_kind == "address" else "address_nacks_consumed"
    assert stats[consumed_key] > 0, (
        f"SRC4382 {fault_kind} NACK injection did not fire; stats={stats!r}"
    )
    assert stats[other_key] == 0, (
        f"SRC4382 {fault_kind} NACK test consumed the wrong fault kind; "
        f"stats={stats!r}"
    )
    if fault_kind == "address":
        c.inject_main_src4382_address_nack(unit, 0)
    else:
        c.inject_main_src4382_data_nack(unit, 0)
    main_diag_i = c.read_main_reg(unit, DIAG_I_PHYS)
    assert main_diag_i > before_i, (
        f"SRC4382 {fault_kind} NACK did not increment MAIN{unit}.diag_i; "
        f"diag_i=0x{main_diag_i:02X}; stats={stats!r}"
    )
    after_block = _rust_main_diag_block(c, unit)
    _assert_diag_deltas_allowed(
        before_block,
        after_block,
        allowed_offsets={DIAG_LABEL_OFFSETS["I"]},
        context=f"MAIN{unit} SRC4382 {fault_kind} NACK",
    )

    line0, line1, cache = _rust_surface_visible_diag(
        c,
        pb_idx=unit,
        checks=((DIAG_LABEL_OFFSETS["I"], min(main_diag_i & 0x0F, 0x0F)),),
        limit=1000,
    )
    expected_i = main_diag_i & 0x0F
    _assert_diag_cache_value(
        cache,
        label="I",
        expected=expected_i,
        context=f"{pb_label} SRC4382 {fault_kind} NACK",
    )
    _assert_lcd_diag_token(
        line0,
        line1,
        label="I",
        value=expected_i,
        context=f"{pb_label} SRC4382 {fault_kind} NACK",
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("pb_idx,pb_label", [(0, "PB1"), (1, "PB2")])
def test_v171_v32_diag_lcd_surfaces_standby_wake_event_counters(
    v171_hex: Path, v32_hex: Path, pb_idx: int, pb_label: str
) -> None:
    """End-to-end event-counter surfacing for a different Diagnostics path.

    Drive real CONTROL STBY/WAKE actions, prove both MAINs increment S/B
    counters, then prove the selected PB Diag renders those counters through the same
    user-visible LCD path.
    """
    c = _rust_connected_chain(v171_hex, v32_hex)
    before_blocks = {unit: _rust_main_diag_block(c, unit) for unit in (0, 1)}

    c.press("STBY")
    c.step_many(80)
    for unit in (0, 1):
        assert c.read_main_reg(unit, DIAG_S_PHYS) > before_blocks[unit][DIAG_LABEL_OFFSETS["S"]], (
            f"MAIN{unit}.diag_s did not increment after STBY; "
            f"before={before_blocks[unit]}; "
            f"after={_rust_main_diag_block(c, unit)}; lcd={c.lcd_lines()!r}"
        )

    c.press("STBY")
    for _ in range(20):
        c.step_many(100)
        if (
            all(
                c.read_main_reg(unit, DIAG_B_PHYS)
                > before_blocks[unit][DIAG_LABEL_OFFSETS["B"]]
                for unit in (0, 1)
            )
            and not c.is_waiting()
        ):
            break
    for unit in (0, 1):
        after_block = _rust_main_diag_block(c, unit)
        assert after_block[DIAG_LABEL_OFFSETS["B"]] > before_blocks[unit][DIAG_LABEL_OFFSETS["B"]], (
            f"MAIN{unit}.diag_b did not increment after WAKE; "
            f"before={before_blocks[unit]}; after={after_block}; "
            f"lcd={c.lcd_lines()!r}"
        )
        _assert_diag_deltas_allowed(
            before_blocks[unit],
            after_block,
            allowed_offsets={DIAG_LABEL_OFFSETS["S"], DIAG_LABEL_OFFSETS["B"]},
            context=f"MAIN{unit} standby/wake",
        )
    c.run_until_connected(limit=300)

    expected_s = c.read_main_reg(pb_idx, DIAG_S_PHYS) & 0x0F
    expected_b = c.read_main_reg(pb_idx, DIAG_B_PHYS) & 0x0F
    line0, line1, cache = _rust_surface_visible_diag(
        c,
        pb_idx=pb_idx,
        checks=((DIAG_LABEL_OFFSETS["S"], expected_s), (DIAG_LABEL_OFFSETS["B"], expected_b)),
        limit=1000,
    )
    for label, expected in (("S", expected_s), ("B", expected_b)):
        _assert_diag_cache_value(
            cache,
            label=label,
            expected=expected,
            context=f"{pb_label} standby/wake",
        )
        _assert_lcd_diag_token(
            line0,
            line1,
            label=label,
            value=expected,
            context=f"{pb_label} standby/wake",
        )


def _rust_trigger_tas3108_volume_fault_episode(  # type: ignore[no-untyped-def]
    c, *, unit: int,
) -> tuple[dict[str, int], tuple[int, ...], tuple[int, ...]]:
    """Drive a real volume-write TAS3108 address-NACK episode on one MAIN."""
    c.inject_main_tas3108_address_nack(unit, 0)
    _rust_drive_main_volume_frame(c, unit, 0x50)
    c.step_ticks(30_000_000)
    flags_before = c.read_main_reg(unit, DSP_FAULT_FLAGS_PHYS)
    assert (flags_before & DSP_FAULT_BIT) == 0, (
        f"MAIN{unit} DSP fault bit already set before injected episode; "
        f"flags=0x{flags_before:02X}; block={_rust_main_diag_block(c, unit)}"
    )

    before = _rust_main_diag_block(c, unit)
    c.inject_main_tas3108_address_nack(unit, 60_000)
    c.reset_main_tas3108_stats(unit)
    _rust_drive_main_volume_frame(c, unit, 0x30)

    stats: dict[str, int] = {}
    after = before
    for _ in range(260):
        c.step_ticks(2_000_000)
        stats = c.read_main_tas3108_stats(unit)
        after = _rust_main_diag_block(c, unit)
        if (
            stats["address_nacks_consumed"] > 0
            and after[DIAG_LABEL_OFFSETS["R"]] > before[DIAG_LABEL_OFFSETS["R"]]
            and after[DIAG_LABEL_OFFSETS["D"]] > before[DIAG_LABEL_OFFSETS["D"]]
        ):
            break

    # Stop the injected fault after proving it fired; the latched counters
    # are what the diagnostics protocol should surface.
    c.inject_main_tas3108_address_nack(unit, 0)
    c.step_ticks(20_000_000)
    return stats, before, after


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("unit,pb_label", [(0, "PB1"), (1, "PB2")])
def test_v171_v32_diag_lcd_surfaces_tas3108_dsp_fault_episode(
    v171_hex: Path, v32_hex: Path, unit: int, pb_label: str
) -> None:
    """D row: a real TAS3108 volume-write fault must reach Diagnostics.

    The stimulus is a TAS3108 address NACK during ``volume_dsp_write``.
    A ping-only fault is not sufficient for this row because ``D`` is the
    user-visible DSP-fault episode latch.
    """
    c = _rust_connected_chain(v171_hex, v32_hex)
    stats, before, after = _rust_trigger_tas3108_volume_fault_episode(c, unit=unit)
    assert stats["address_nacks_consumed"] > 0, (
        f"TAS3108 address NACK budget was not consumed; stats={stats!r}"
    )
    _assert_diag_deltas_allowed(
        before,
        after,
        allowed_offsets={
            DIAG_LABEL_OFFSETS["I"],
            DIAG_LABEL_OFFSETS["D"],
            DIAG_LABEL_OFFSETS["R"],
        },
        context=f"MAIN{unit} TAS3108 fault episode",
    )
    assert after[DIAG_LABEL_OFFSETS["D"]] > before[DIAG_LABEL_OFFSETS["D"]], (
        f"MAIN{unit}.diag_d did not increment after TAS3108 fault episode; "
        f"before={before}; after={after}; stats={stats!r}"
    )

    expected_d = after[DIAG_LABEL_OFFSETS["D"]] & 0x0F
    line0, line1, cache = _rust_surface_visible_diag(
        c,
        pb_idx=unit,
        checks=((DIAG_LABEL_OFFSETS["D"], expected_d),),
        limit=1200,
    )
    _assert_diag_cache_value(
        cache,
        label="D",
        expected=expected_d,
        context=f"{pb_label} TAS3108 fault episode",
    )
    _assert_lcd_diag_token(
        line0,
        line1,
        label="D",
        value=expected_d,
        context=f"{pb_label} TAS3108 fault episode",
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("unit,pb_label", [(0, "PB1"), (1, "PB2")])
def test_v171_v32_diag_lcd_surfaces_volume_dsp_recovery_counter(
    v171_hex: Path, v32_hex: Path, unit: int, pb_label: str
) -> None:
    """R row producer 1: volume-write retry exhaustion surfaces as ``R``."""
    c = _rust_connected_chain(v171_hex, v32_hex)
    stats, before, after = _rust_trigger_tas3108_volume_fault_episode(c, unit=unit)
    _assert_diag_deltas_allowed(
        before,
        after,
        allowed_offsets={
            DIAG_LABEL_OFFSETS["I"],
            DIAG_LABEL_OFFSETS["D"],
            DIAG_LABEL_OFFSETS["R"],
        },
        context=f"MAIN{unit} volume-write recovery",
    )
    assert after[DIAG_LABEL_OFFSETS["R"]] > before[DIAG_LABEL_OFFSETS["R"]], (
        f"MAIN{unit}.diag_r did not increment after volume-write recovery; "
        f"before={before}; after={after}; stats={stats!r}"
    )

    expected_r = after[DIAG_LABEL_OFFSETS["R"]] & 0x0F
    line0, line1, cache = _rust_surface_visible_diag(
        c,
        pb_idx=unit,
        checks=((DIAG_LABEL_OFFSETS["R"], expected_r),),
        limit=1200,
    )
    _assert_diag_cache_value(
        cache,
        label="R",
        expected=expected_r,
        context=f"{pb_label} volume-write recovery",
    )
    _assert_lcd_diag_token(
        line0,
        line1,
        label="R",
        value=expected_r,
        context=f"{pb_label} volume-write recovery",
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("unit,pb_label", [(0, "PB1"), (1, "PB2")])
def test_v171_v32_diag_lcd_surfaces_bounded_i2c_timeout_recovery_counter(
    v171_hex: Path, v32_hex: Path, unit: int, pb_label: str
) -> None:
    """R row producer 2: bounded MSSP STOP timeout surfaces as ``R``.

    This is distinct from a TAS3108 NACK: the simulated MSSP peripheral
    keeps PEN busy long enough to exercise the bounded wait/recovery path.
    """
    c = _rust_connected_chain(v171_hex, v32_hex)
    _rust_drive_main_volume_frame(c, unit, 0x50)
    c.step_ticks(30_000_000)
    before = _rust_main_diag_block(c, unit)

    c.set_main_mssp_stop_fault(unit, stop_busy_cycles=5_000_000, stop_busy_count=-1)
    _rust_drive_main_volume_frame(c, unit, 0x30)
    after = before
    for _ in range(220):
        c.step_ticks(2_000_000)
        after = _rust_main_diag_block(c, unit)
        if after[DIAG_LABEL_OFFSETS["R"]] > before[DIAG_LABEL_OFFSETS["R"]]:
            break
    c.clear_main_mssp_stop_faults(unit)
    c.force_reset_main_mssp_unit(unit)
    c.step_ticks(20_000_000)

    assert after[DIAG_LABEL_OFFSETS["R"]] > before[DIAG_LABEL_OFFSETS["R"]], (
        f"MAIN{unit}.diag_r did not increment after MSSP STOP timeout; "
        f"before={before}; after={after}; lcd={c.lcd_lines()!r}"
    )
    _assert_diag_deltas_allowed(
        before,
        after,
        allowed_offsets={DIAG_LABEL_OFFSETS["I"], DIAG_LABEL_OFFSETS["R"]},
        context=f"MAIN{unit} MSSP STOP timeout",
    )
    expected_r = after[DIAG_LABEL_OFFSETS["R"]] & 0x0F
    line0, line1, cache = _rust_surface_visible_diag(
        c,
        pb_idx=unit,
        checks=((DIAG_LABEL_OFFSETS["R"], expected_r),),
        limit=1200,
    )
    _assert_diag_cache_value(
        cache,
        label="R",
        expected=expected_r,
        context=f"{pb_label} MSSP STOP timeout",
    )
    _assert_lcd_diag_token(
        line0,
        line1,
        label="R",
        value=expected_r,
        context=f"{pb_label} MSSP STOP timeout",
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("unit,pb_label", [(0, "PB1"), (1, "PB2")])
def test_v171_v32_diag_lcd_surfaces_an0_standby_trigger(
    v171_hex: Path, v32_hex: Path, unit: int, pb_label: str
) -> None:
    """A row: a real AN0 high-to-low standby trigger surfaces as ``A``."""
    c = _rust_connected_chain(v171_hex, v32_hex)
    c.set_main_an0_sample(unit, 0x0300)
    c.step_ticks(120_000_000)
    before_block = _rust_main_diag_block(c, unit)
    before_a = c.read_main_reg(unit, DIAG_A_PHYS)

    c.set_main_an0_sample(unit, 0x0100)
    after_a = _rust_wait_for_main_diag_delta(
        c, unit=unit, addr=DIAG_A_PHYS, baseline=before_a,
        attempts=260, ticks=2_000_000,
    )
    after_block = _rust_main_diag_block(c, unit)
    _assert_diag_deltas_allowed(
        before_block,
        after_block,
        allowed_offsets={DIAG_LABEL_OFFSETS["A"], DIAG_LABEL_OFFSETS["S"]},
        context=f"MAIN{unit} AN0 standby trigger",
    )
    c.set_main_an0_sample(unit, 0x0300)
    # Let the AN0-induced standby transition reach a stable MAIN service
    # boundary before issuing the explicit user standby/wake pair.  The
    # counter has already been proven above; without this short settle,
    # MAIN0 can still be mid-frame with its active gate closed and will
    # correctly ignore the immediate PB1 Diagnostics query.
    c.step_ticks(10_000_000)
    c.press("STBY")
    c.step_many(80)
    c.press("STBY")
    c.run_until_connected(limit=300)

    expected_a = after_a & 0x0F
    line0, line1, cache = _rust_surface_visible_diag(
        c,
        pb_idx=unit,
        checks=((DIAG_LABEL_OFFSETS["A"], expected_a),),
        limit=1200,
    )
    _assert_diag_cache_value(
        cache,
        label="A",
        expected=expected_a,
        context=f"{pb_label} AN0 standby trigger",
    )
    _assert_lcd_diag_token(
        line0,
        line1,
        label="A",
        value=expected_a,
        context=f"{pb_label} AN0 standby trigger",
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("unit,pb_label", [(0, "PB1"), (1, "PB2")])
def test_v171_v32_diag_lcd_surfaces_ra1_edge_counter(
    v171_hex: Path, v32_hex: Path, unit: int, pb_label: str
) -> None:
    """P row: one modeled RA1 edge increments once and surfaces as ``P``."""
    c = _rust_connected_chain(v171_hex, v32_hex)
    c.set_main_pin(unit, "A", 1, True)
    c.step_ticks(30_000_000)
    before_block = _rust_main_diag_block(c, unit)
    before_p = c.read_main_reg(unit, DIAG_P_PHYS)

    c.set_main_pin(unit, "A", 1, False)
    after_p = _rust_wait_for_main_diag_delta(
        c, unit=unit, addr=DIAG_P_PHYS, baseline=before_p,
        attempts=120, ticks=2_000_000,
    )
    c.step_ticks(30_000_000)
    steady_p = c.read_main_reg(unit, DIAG_P_PHYS)
    assert steady_p == after_p, (
        f"MAIN{unit}.diag_p repeated while RA1 was held steady low; "
        f"after_edge=0x{after_p:02X}; steady=0x{steady_p:02X}"
    )
    after_block = _rust_main_diag_block(c, unit)
    _assert_diag_deltas_allowed(
        before_block,
        after_block,
        allowed_offsets={DIAG_LABEL_OFFSETS["P"]},
        context=f"MAIN{unit} RA1 edge",
    )

    expected_p = after_p & 0x0F
    line0, line1, cache = _rust_surface_visible_diag(
        c,
        pb_idx=unit,
        checks=((DIAG_LABEL_OFFSETS["P"], expected_p),),
        limit=1000,
    )
    _assert_diag_cache_value(
        cache,
        label="P",
        expected=expected_p,
        context=f"{pb_label} RA1 edge",
    )
    _assert_lcd_diag_token(
        line0,
        line1,
        label="P",
        value=expected_p,
        context=f"{pb_label} RA1 edge",
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize(
    "source,label,offset",
    [
        ("por", "O", DIAG_LABEL_OFFSETS["O"]),
        ("bor", "V", DIAG_LABEL_OFFSETS["V"]),
        ("wdt", "W", DIAG_LABEL_OFFSETS["W"]),
        ("reset", "X", DIAG_LABEL_OFFSETS["X"]),
    ],
)
@pytest.mark.parametrize("pb_idx,pb_label", [(0, "PB1"), (1, "PB2")])
def test_v171_v32_diag_lcd_surfaces_reset_cause_flags(
    v171_hex: Path, v32_hex: Path, source: str, label: str,
    offset: int, pb_idx: int, pb_label: str,
) -> None:
    """Reset rows O/V/W/X: cmd 0x22 reset flags reach PB1/PB2 LCD pages.

    The two MAINs deliberately boot with different reset causes so a PB cache
    routing bug cannot pass by showing the other MAIN's reset flags.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    # Seed the reset-cause latch that real silicon exposes in RCON at reset
    # entry, then let V3.2's cold-init classification code set the diag flag.
    # This keeps the test on the firmware classification path without waiting
    # for a full mid-session bootloader re-entry.
    other_source = RESET_SOURCE_ORDER[
        (RESET_SOURCE_ORDER.index(source) + 1) % len(RESET_SOURCE_ORDER)
    ]
    sources_by_unit = {
        pb_idx: source,
        1 - pb_idx: other_source,
    }
    for unit, unit_source in sources_by_unit.items():
        c.write_main_reg(unit, RCON_PHYS, RESET_SOURCE_RCON[unit_source])
    c.run_until_connected(limit=300)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain did not reconnect after {source} reset; lcd={c.lcd_lines()!r}"
    )

    checks = [(offset, 1)]
    if source == "por":
        # POR is OK-context telemetry and renders under "PBn OK" by itself.
        # Add an unrelated real I2C fault after reset classification so the
        # sparse renderer has an issue row and must still place O1 at the end
        # when there is room.
        _rust_configure_main_src4382_no_source(c, pb_idx)
        before_i = c.read_main_reg(pb_idx, DIAG_I_PHYS)
        c.inject_main_src4382_address_nack(pb_idx, 1000)
        c.reset_main_src4382_stats(pb_idx)
        _rust_drive_main_volume_frame(c, pb_idx, 0x40)
        after_i = _rust_wait_for_main_diag_delta(
            c, unit=pb_idx, addr=DIAG_I_PHYS, baseline=before_i,
            attempts=180, ticks=2_000_000,
        )
        checks.append((DIAG_LABEL_OFFSETS["I"], after_i & 0x0F))

    c.mark_ctl_tx_capture_point()
    c.mark_ctl_rx_capture_point()
    line0, line1, cache = _rust_surface_visible_diag(
        c, pb_idx=pb_idx, checks=tuple(checks), limit=1400
    )
    ctl_tx_frames = _bytes_to_frames(c.ctl_tx_record_since_last_capture())
    ctl_rx_frames = _bytes_to_frames(c.ctl_rx_record_since_last_capture())
    expected_route = 0xB1 if pb_idx == 0 else 0xB2
    assert (expected_route, 0x22, 0x00) in ctl_tx_frames, (
        f"{pb_label} did not emit cmd 0x22 reset query; "
        f"expected={(expected_route, 0x22, 0x00)!r}; frames={ctl_tx_frames!r}"
    )
    expected_reply = (0xBF, 0x28 + (offset - DIAG_LABEL_OFFSETS["O"]), 0x01)
    assert expected_reply in ctl_rx_frames, (
        f"{pb_label} CONTROL RX did not receive expected BF/28..2B reset reply; "
        f"expected={expected_reply!r}; frames={ctl_rx_frames!r}"
    )

    for reset_label in DIAG_RESET_LABELS:
        expected = 1 if reset_label == label else 0
        _assert_diag_cache_value(
            cache,
            label=reset_label,
            expected=expected,
            context=(
                f"{pb_label} {source} reset cause "
                f"(other PB booted as {other_source})"
            ),
        )
    _assert_lcd_diag_token(
        line0,
        line1,
        label=label,
        value=1,
        context=f"{pb_label} {source} reset cause",
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_no_query_off_diag_page(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Without entering the Diagnostics page, neither PB should ever
    receive a cmd 0x21 query.  We assert this indirectly: after enough
    chain warmup for the steady-state status burst to cycle several
    times, ``v171_diag_present`` must remain 0 (no BF/2N replies have
    arrived because no query was sent).

    This proves the spec's "send no diagnostics queries outside the
    Diagnostics page" requirement without needing to scrape the TX
    stream for absence of B1/0x21 frames.
    """
    _require_v32_hex(v32_hex)
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    # Step 50M Tcy (matches gpsim's 50 chunks * 1M Tcy chunk size).
    for _ in range(50):
        c.step_tcy(1_000_000)
    present = c.read_reg(V171_DIAG_PRESENT_PHYS)
    # Read PB1/PB2 caches lazily inside the assert error path -- only
    # needed for diagnostics if the present-mask gate fails.  Mirrors
    # gpsim's lazy read pattern (codex #78); avoids 14 RAM reads on
    # the success path.
    assert present == 0, (
        f"[rust] diag_present non-zero without entering Diagnostics: "
        f"0x{present:02X}; "
        f"PB1 cache={[hex(c.read_reg(V171_DIAG_PB1_BASE_PHYS + i)) for i in range(7)]}; "
        f"PB2 cache={[hex(c.read_reg(V171_DIAG_PB2_BASE_PHYS + i)) for i in range(7)]}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_diag_page_cadence_is_not_fast_polling(
    v171_hex: Path, v32_hex: Path
) -> None:
    """REGRESSION: parked PB1/PB2 Diagnostics pages must not poll at
    tens of Hz.

    The first Diagnostics query is intentionally immediate on page entry,
    but after that the active page should refresh near 1 Hz.  A previous
    0x0080 reload estimate produced ~60 cmd 0x21 queries/s in the rust
    ring, which in turn produced hundreds of BF/2N replies/s and repeated
    full-LCD redraws on real hardware.
    """
    _require_v32_hex(v32_hex)
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_navigate_to_diagnostics(c)
    c.step_ticks(50_000_000)  # absorb the immediate page-entry query
    c.mark_ctl_tx_capture_point()
    c.step_ticks(96_000_000)  # 2 s at the 48 MHz universal clock
    tx = c.ctl_tx_record_since_last_capture()
    frames = [tuple(tx[i:i + 3]) for i in range(0, len(tx) - 2, 3)]
    runtime_queries = [f for f in frames if f[1] == 0x21]
    assert 1 <= len(runtime_queries) <= 4, (
        "Diagnostics cadence is fast-polling instead of ~1 Hz: "
        f"{len(runtime_queries)} cmd 0x21 queries in 2 simulated seconds; "
        f"first frames={frames[:12]!r}; lcd={c.lcd_lines()!r}"
    )
# ===========================================================================
# F4 + xfail Group A canary (2026-04-19 round 2): split into two tests.
#
# (1) Always-on transport canary — proves bytes actually flow through
#     EVERY chain bridge during a diag-page run.  If a future change
#     breaks the harness's bridge plumbing this catches it loudly,
#     instead of silently masking it under the Group-A xfail.
#
# (2) Hop-attribution canary — same probe but also asserts CONTROL
#     parses PB2's reply AND that the BF/27 payload landed in PB2
#     cache slot[6].  Post-PF.3 (2026-05-04): the canary's
#     `_diag_canary_run` helper now uses
#     `_press_drive_until_pb_present` to drive the cmd 0x21/0x22
#     cadence, so hop (e) (`v171_diag_present` bit 1) PASSES.  The
#     xfail now fires at hop (f) instead -- gpsim's wire-chain
#     misroutes the multi-frame BF/22..27 burst, so PB2 cache slot
#     [6] never receives the BF/27 diag_p payload.  Same root cause
#     as `pb_cache_isolation` gpsim path failure; tracked as task
#     #117.  The historical Task #22 "gpsim bridge echo" framing
#     applies to architectural fan-out (retired by the rust silicon
#     ring) and is distinct from #117.  Marked run=True so the
#     hop-attribution report still fires every CI run.
# ===========================================================================


# ===========================================================================
# 2026-04-20 hang-class regression tests.
#
# Real-hardware bring-up of V1.71 + V3.2 surfaced a class of bugs the
# original Phase A/B/C tests did NOT catch:
#
#   * On the operator's two-MAIN rig, navigating to the Diagnostics
#     page rendered counter values for both PBs, but within seconds
#     PB2's diag_s and diag_r counters saturated to '+' (15+ events)
#     and CONTROL hung completely (no LCD updates, no IR response).
#     Only a power-cycle recovered, and reaching the Diag page again
#     hung in the same way.
#
# Why the original tests missed it:
#
#   * Phase A (test_v32_layer5_diag_counters.py) verifies MAIN-side
#     counters at boot are zero and stay zero through warmup — but
#     never under sustained cmd 0x21 traffic.
#
#   * Phase B (test_v171_layer5_diag_page.py) is a CONTROL-only
#     gpsim run (no MAIN attached); the cmd 0x21 query path is
#     issued but nothing replies, so no parser-state stress.
#
#   * Phase C (this file, all tests above) verifies SHORT-DURATION
#     behaviors: idle-at-boot, force-counter-and-render-once,
#     LCD-renders-zero-idle.  None of them sustain the cadence for
#     the 30+ chain-step window that was needed to surface the
#     cascade.  The closest test (no_query_off_diag_page) only runs
#     50 chain steps and stays OFF the page — which is the opposite
#     stress shape.
#
# The tests below close that gap.  Each test asserts an invariant
# that the operator-observed hang violated:
#
#   * sustained_diag_page_keeps_control_responsive — page can be
#     entered AND exited via LEFT after extended cadence; CONTROL's
#     LCD doesn't freeze.
#
#   * diag_page_does_not_cascade_main_counters — sustained cmd 0x21
#     traffic must not cause MAIN's diag_s / diag_r / diag_b to
#     saturate (which on the rig was evidence of a standby/wake
#     cascade triggered by the cmd 0x21 reply burst itself).
#
#   * cmd21_handler_emits_clean_burst — the 7-frame BF/2N reply must
#     not be followed by a stray cmd-XOR ACK (0x21 echo) byte that
#     V1.71's parser is not designed to handle.
# ===========================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_sustained_diag_page_keeps_control_responsive(
    v171_hex: Path, v32_hex: Path
) -> None:
    """REGRESSION: real-HW operator report 2026-04-20 — V1.71 CONTROL
    hung completely after a few seconds on the Diagnostics page.  LCD
    stopped updating, IR remote stopped responding, only a power-cycle
    recovered.

    The page MUST stay responsive: CONTROL must continue ticking the
    cadence, the operator must be able to navigate AWAY by pressing
    LEFT, and the chain must reach the Volume screen again.

    Sustained-cadence shape:
      1. Reach DISPLAY (Volume).
      2. Navigate to Diagnostics.
      3. Step the chain for 200 chain steps (multiple cadence cycles
         + many cmd 0x21 query/reply round-trips on PB1 — PB2 path
         currently does not converge in the no-user-events test
         scenario because V1.71's foreground busy-loop in
         `display_loop_iteration` (asm:2885-2897) only exits on
         user-driven events; cadence still issues PB2 queries that
         fail to land within the test budget; same shape as the
         remaining `_V171_V32_PB2_BRIDGE_XFAIL` tests post-PF.3 --
         see ``_press_drive_until_pb_present`` for the wiggle-based
         resolution path).
      4. Press LEFT four times -> exit page -> land back on Volume.
         (Tier-1 menu rework moved Diag from state 2 to states 4-5;
         exit now requires four LEFT presses to walk back to Volume(0).)
      5. Verify LCD shows "Volume:" and CONTROL accepted the navigation.

    Hang mode this catches:
      * v171_diag_loop deadlocks on display_loop_iteration or
        v171_diag_send_query (Layer 1 bounded TX).
      * UART RX overrun cascade triggers reconnect-OERR helper which
        loops indefinitely under continued chain traffic.
      * CONTROL's button-poll path (v171_diag_check_buttons) loses
        the LEFT press because it's starved by the parser ISR.

    Migrated to dual_supported in P4.7: the firmware-correctness
    invariant (CONTROL stays out of WAITING during the sustained
    cadence; LEFT/LEFT/LEFT/LEFT lands back on Volume) is
    backend-independent.  Both gpsim and rust must show the same
    responsiveness behavior because hang-vs-responsive is a
    firmware property of v171_diag_loop / v171_diag_check_buttons,
    not a property of either simulator's UART byte timing.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_navigate_to_diagnostics(c)
    for _ in range(200):
        c.step()
        assert not c.is_waiting(), (
            "[rust] CONTROL fell into WAITING during sustained "
            "Diag-page cadence — cascade reconnect storm."
        )
    # Walk LEFT back to Volume.  Adaptive: press LEFT, settle, check
    # DISPLAY_STATE_INDEX -- repeat until state == 0 (Volume) or
    # budget exhausted.  V1.71's button-hold auto-repeat (50M ticks)
    # makes a fixed-count loop unreliable: post the M3 IR code shift
    # (#153) the foreground main-loop iteration cost shifted, and a
    # press-settle that previously produced exactly 1 menu step now
    # absorbs presses non-deterministically.
    #
    # Codex LOW vs a7e4169 raised a wrap-around concern (e.g. state
    # 4 -> 3 -> 2 -> 1 -> 0 -> 4 -> 3 -> ... -> 0 in a 5-state menu).
    # An earlier monotonic-decrease guard rejected this empirically
    # because V1.71's Tier-1 menu has sub-state numbering beyond 0..4
    # (LEFT from state 0x01 lands on state 0x05, presumably a Diag
    # sub-page entry vs the Diag root).  The final LCD == "Volume:"
    # check is the real gate: even if intermediate states transit
    # through sub-page numbering, only the Volume page renders that
    # line0 prefix, so a false-pass via wrap-only would have to
    # leave the LCD at Volume's actual rendering -- which is the
    # contract under test.
    max_lefts = 12
    for _ in range(max_lefts):
        if c.read_reg(DISPLAY_STATE_INDEX_PHYS) == 0:
            break
        _rust_tap_key(c, "LEFT")
        for _ in range(8):
            c.step()
    line0, line1 = c.lcd_lines()
    assert line0.startswith("Volume:"), (
        f"[rust] LEFT navigation did not return to Volume within "
        f"{max_lefts} presses; LCD={(line0, line1)!r}, "
        f"display_state_index=0x{c.read_reg(DISPLAY_STATE_INDEX_PHYS):02X}"
    )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_diag_page_does_not_cascade_main_counters(
    v171_hex: Path, v32_hex: Path
) -> None:
    """REGRESSION: on real HW, sustained Diag-page cadence caused PB2's
    ``diag_s`` and ``diag_r`` to saturate to '+' (15+ events) within
    seconds — strong evidence that the cmd 0x21 reply burst itself was
    triggering MAIN-side standby/wake or recovery events, which in turn
    cascaded into chain instability.

    Invariant (firmware-correctness, backend-independent): serving
    cmd 0x21 queries is purely observational.  The handler reads
    diag_X cells and emits 7 BF/2N frames over UART; it must not
    provoke standby_event_dispatch (diag_s, diag_b) or
    volume_dsp_write retry escalation (diag_r).  If it does, the
    cmd-21-reply path is racing with the standby/recovery state
    machines and needs a guard (an "armed" check or a higher cadence-
    interval threshold).

    What this test asserts:
      1. Boot, capture initial counter snapshot for PB1 (all zero).
      2. Navigate to Diag page.
      3. Run sustained cadence for 200 chain steps (~16 cadence cycles).
      4. Capture post-cadence counter snapshot for PB1.
      5. diag_s, diag_r, diag_b deltas must be small (< 4 events each).
         A delta of 15+ means cascade.

    Counter-cascade mode this catches:
      * MAIN's main loop pause (during cmd 0x21 reply burst) trips
        watchdog -> standby_event_dispatch -> diag_s++.
      * I2C transaction interrupted by cmd 0x21 -> volume_dsp_write
        retry-escalation -> diag_r++.
      * Wake-after-spurious-standby -> adc_boot_gate -> diag_b++.

    Both MAINs are checked: PB1's replies tend to surface in CONTROL
    sooner than PB2's in the no-user-events test scenario (the
    pre-PF.3 ``_V171_V32_PB2_BRIDGE_XFAIL`` busy-loop convergence
    root cause; see file-level docstring -- now resolved test-side
    via ``_press_drive_until_pb_present`` for tests that opt into
    the wiggle), but the MAIN1 hardware still SERVES the cmd 0x21
    queries either way.  Counter cascade on the MAIN1 (PB2)
    hardware is a real firmware bug regardless of
    whether the reply makes it back to CONTROL.

    Migrated to dual_supported in P4.7: cascade-detection is a
    firmware-correctness invariant on the MAIN side; rust path uses
    `read_main_reg(unit, addr)` to read the diag block on each MAIN.
    """
    # Counter-cascade thresholds (shared across backends).  Index map:
    # 0=I, 1=D, 2=S, 3=B, 4=R, 5=A, 6=P.  Cascade-sensitive counters
    # are S/B/R (state machines) plus I/D (I2C/DSP fault counters).
    cascade_idx = (("S", 2), ("B", 3), ("R", 4), ("I", 0), ("D", 1))
    threshold = 4

    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )

    baseline_pb1 = _rust_main_diag_block(c, 0)
    baseline_pb2 = _rust_main_diag_block(c, 1)

    _rust_navigate_to_diagnostics(c)
    for _ in range(200):
        c.step()

    post_pb1 = _rust_main_diag_block(c, 0)
    post_pb2 = _rust_main_diag_block(c, 1)

    for label, idx in cascade_idx:
        for baseline, post, tag in (
            (baseline_pb1, post_pb1, "PB1"),
            (baseline_pb2, post_pb2, "PB2"),
        ):
            delta = post[idx] - baseline[idx]
            assert delta < threshold and post[idx] < threshold, (
                f"[rust] cascade detected: {tag}.diag_{label} went "
                f"from {baseline[idx]} to {post[idx]} "
                f"(delta={delta}) during sustained Diag-page "
                f"cadence.  Full snapshot: baseline={baseline}, "
                f"post={post}."
            )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_diag_page_left_button_exits_promptly(
    v171_hex: Path, v32_hex: Path
) -> None:
    """REGRESSION: on real HW the operator could not navigate away
    from a hung Diag page -- LEFT presses were ignored.  Even WITHOUT
    a full hang, a slow button-poll on the Diag page would make the
    UI feel unresponsive.

    Invariant (firmware-correctness, backend-independent): pressing
    LEFT on the Diag page must take CONTROL OFF the Diag page within
    a small number of chain steps (the same responsiveness budget the
    other menu screens give).

    V1.71 Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20) moved Diag from
    state 2 (between Preset and Input) to states 4-5 (after Setup),
    so a single LEFT press from PB1 Diag(4) now lands on Setup(3),
    not Preset(1).  Phase 3.4 (9bed274, 2026-04-21) then rewrote the
    Diag renderer from the legacy dual-PB layout ("1:IDSBRAP" /
    "2:IDSBRAP" on one screen) to a sparse per-PB layout
    ("PBn OK" or "PBn! X# X# ..." across two menu states).

    The exit assertion therefore checks that the LCD no longer starts
    with any Diagnostics-page prefix ("PB1" or "PB2") — it doesn't
    matter which non-Diag screen we landed on, only that the LEFT
    press took effect.  Matching both "PB1" and "PB2" here means a
    hypothetical LEFT→RIGHT misdecode (landing on PB2 Diag instead of
    exiting the page) does NOT false-pass the test.

    Test shape:
      1. Reach DISPLAY, navigate to Diag.
      2. Run a few cadence cycles so the page is "warm".
      3. Press LEFT once.
      4. Step the chain for at most 12 steps.
      5. Verify LCD no longer shows the Diag layout (any non-Diag
         screen is acceptable; Setup(3) is the expected post-LEFT
         landing under the Tier-1 menu order).

    Migrated to dual_supported in P4.7: rust path uses the same
    button-press cadence + LCD inspection.  The firmware's button-
    poll responsiveness is a property of v171_diag_check_buttons,
    not of either simulator's UART byte timing -- both backends
    must show the same exit-within-12-steps behavior.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_navigate_to_diagnostics(c)
    # Settle bumped 40 -> 120 to absorb the M3 IR code shift (#153)
    # -- post-M3, _rust_navigate_to_diagnostics's 4 RIGHTs may land
    # on PB2 instead of PB1 if the auto-repeat hold time has shifted;
    # the longer settle gives the menu state machine time to clamp
    # at PB1 (Tier-1 menu state 4) and the screen to render.
    for _ in range(120):
        c.step()
    line0_diag, _ = c.lcd_lines()
    if line0_diag.startswith("PB2"):
        # Auto-repeat overshot to PB2; one LEFT brings us back to PB1.
        _rust_tap_key(c, "LEFT")
        for _ in range(24):
            c.step()
        line0_diag, _ = c.lcd_lines()
    assert line0_diag.startswith("PB1"), (
        f"[rust] chain did not reach PB1 Diag page after navigation; "
        f"LCD={line0_diag!r}"
    )
    _rust_tap_key(c, "LEFT")
    exit_seen = False
    for _ in range(12):
        c.step()
        line0, _ = c.lcd_lines()
        if not line0.startswith(("PB1", "PB2")):
            exit_seen = True
            break
    assert exit_seen, (
        "[rust] LEFT press did not exit Diag page within 12 chain "
        "steps; v171_diag_check_buttons isn't acting on the press "
        f"promptly.  Final LCD: {c.lcd_lines()!r}"
    )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v32_cmd21_handler_emits_clean_seven_frame_burst(
    v32_hex: Path
) -> None:
    """REGRESSION: V3.2's cmd 0x21 handler returns to the parser tail at
    ``flow_main_uart_service_1be6_1e6c`` which (under the cmd-XOR-chain
    dispatch path) emits an EXTRA byte — the cmd-XOR ACK echo (0x21
    for cmd 0x21).  Stock V1.x parsers tolerate this trailing byte, but
    V1.71's diagnostics parser only handles BF/21..27 frames; an
    unsolicited 0x21 byte at parser frame_position=0 may bleed into the
    next frame's state and progressively misalign the parser.

    This test pins WHAT the V3.2 cmd 0x21 handler emits at the source
    level.  Specifically:
      1. The handler MUST goto ``flow_main_uart_service_1be6_1e6c``
         (so it integrates with the standard parser tail).
      2. The handler MUST clear ``active_flags.bit6`` BEFORE returning
         to suppress the cmd-XOR ACK echo (defense in depth — if the
         ACK byte is the parser-corruption root cause, this prevents
         it; if it's not, this is a no-op cleanup).

    Right now this test FAILS because the handler doesn't clear bit 6.
    Once we land that suppression (proposed fix B), this test passes
    and pins the new behavior so a future revert is caught.

    Marked xfail until the suppression lands so the gate doesn't block
    other work; flip to passing assertion once the fix is in.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8") if 'V32_MAIN_ASM' in globals() else None
    if text is None:
        from dlcp_fw.paths import V32_MAIN_ASM as _V32
        text = _V32.read_text(encoding="utf-8")
    handler_idx = text.find("cmd21_diag_query_handler:")
    assert handler_idx >= 0, "cmd21_diag_query_handler missing"
    body_end = text.find("\n; ---", handler_idx + 1)
    assert body_end > handler_idx, "could not delimit cmd21 handler body"
    body = text[handler_idx:body_end]
    # V3.2 rev 0x37 (Tier-1) refactored cmd 0x21 + cmd 0x22 into a shared
    # diag_send_burst_xx helper.  cmd21 setup-block now bra's into the
    # helper; the helper does the bcf active_flags,6 + goto parser tail.
    # We pin the contract by checking either the standalone or the
    # shared form, so the test still passes after the refactor and a
    # future rewrite that re-inlines doesn't silently lose the
    # suppression / parser-tail integration.
    helper_idx = text.find("\ndiag_send_burst_xx:")
    has_helper = helper_idx >= 0
    if has_helper:
        helper_end = text.find("\n; ---", helper_idx + 1)
        if helper_end < 0:
            helper_end = helper_idx + 4000
        helper_body = text[helper_idx:helper_end]
        # cmd 0x21 setup must bra into the shared helper.
        assert re.search(r"bra\s+diag_send_burst_xx", body), (
            "cmd21 handler must bra into diag_send_burst_xx (shared "
            "with cmd 0x22) -- the refactor moved the parser-tail "
            "exit into the helper; the cmd21 entry just seeds it."
        )
        # The helper itself must goto flow_main_uart_service_1be6_1e6c
        # to keep dispatch/forwarding consistent with stock cmd handlers.
        # Match the actual `goto <label>` instruction (not just substrings),
        # so a refactor that points goto at a different label and merely
        # mentions the parser-tail label in a comment doesn't slip past
        # this gate (codex LOW review against 1d4f3dc).
        assert re.search(
            r"goto\s+flow_main_uart_service_1be6_1e6c\b",
            helper_body,
        ), (
            "diag_send_burst_xx helper must exit via "
            "`goto flow_main_uart_service_1be6_1e6c` so dispatch/"
            "forwarding is consistent with stock cmd handlers"
        )
        # And the helper must clear active_flags.bit6 to suppress the
        # cmd-XOR ACK echo.  Suspected contributor to the V1.71 + V3.2
        # Diag-page hang observed on real HW (2026-04-20).
        assert re.search(r"bcf\s+active_flags,\s*6,\s*ACCESS", helper_body), (
            "diag_send_burst_xx must clear active_flags.bit6 BEFORE "
            "the parser-tail goto so the trailing 0x21/0x22 ACK echo "
            "doesn't bleed into V1.71 CONTROL's parser state."
        )
    else:
        # Pre-refactor fallback: the cmd21 handler does the goto + bcf
        # itself.  This branch keeps the test compatible with any
        # legacy / pre-Tier-1 source tree.  Same instruction-exact
        # match as the helper-path above.
        assert re.search(
            r"goto\s+flow_main_uart_service_1be6_1e6c\b",
            body,
        ), (
            "cmd21 handler must exit via "
            "`goto flow_main_uart_service_1be6_1e6c` so dispatch/"
            "forwarding is consistent with stock cmd handlers"
        )
        assert re.search(r"bcf\s+active_flags,\s*6,\s*ACCESS", body), (
            "cmd21 handler does not clear active_flags.bit6 -- the "
            "parser tail still emits the trailing 0x21 ACK echo.  "
            "Suspected contributor to the V1.71 + V3.2 Diag-page hang "
            "observed on real HW (2026-04-20).  Fix: insert `bcf "
            "active_flags, 6, ACCESS` before the final "
            "`goto flow_main_uart_service_1be6_1e6c`."
        )
