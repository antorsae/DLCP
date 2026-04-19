"""V1.71 Layer 2: one-frame-per-call full-sync state machine (BUG C7 fix).

Replaces the V1.6b back-to-back 5-frame burst at ``full_sync_burst`` with
a one-frame-per-call state machine that emits volume / input / mute /
cmd1d_setting / standby_wake / preset across six consecutive trigger
firings.  Spreads chain traffic out so the 31,250-baud link never
saturates, and makes preset value-bearing alongside the other CONTROL-
owned state (closes the V1.61b-era preset desync without adding any
MAIN-side reply protocol).

Three tiers, each independently runnable:

* **Tier A — source-level structural**: ram.inc has the new EQU; the
  function body has the dispatch shape (advance + wrap + 6 dispatch
  arms via tail-call goto); the V1.61b 0x70/0x71 retry block and all
  ``delay_short`` calls are gone; the ``v171_send_preset_frame_txonly``
  helper exists separate from ``v171_send_preset_frame_and_persist``.

* **Tier B — build verification**: v171 still assembles, vector and
  bootloader byte-identity gates hold, all Layer 2 labels resolve.

* **Tier C — behavioral via gpsim**: after enough warmup for the
  full-sync trigger to fire repeatedly, every step (1..6) emits its
  intended frame; in particular the preset frame appears in the TX
  stream from the periodic broadcast (proving Layer 2 closes the
  preset desync without needing the V1.61b retry queue or any MAIN
  reply path).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    STOCK_CONTROL_HEX_V16B,
    V17_CONTROL_RAM_INC,
    V171_CONTROL_ASM,
)
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.v17_symbols import assemble_v17

try:
    from dlcp_fw.sim.control_gpsim import GpsimControlHarness, _read_reg
    _IMPORT_OK = True
except Exception:  # pragma: no cover
    _IMPORT_OK = False


# ---------------------------------------------------------------------------
# Constants pinned by the Layer 2 design (see ram.inc + asm header)
# ---------------------------------------------------------------------------

V171_FULL_SYNC_STEP_EQU = 0x070      # 8-bit BANKED-form operand in firmware (asserted in ram.inc)
V171_FULL_SYNC_STEP_PHYS = 0x170     # physical address (BSR=1 << 8 | 0x70); use this for gpsim reg() reads

ROUTE_BROADCAST = 0xB0
CMD_VOLUME = 0x07              # step 1
CMD_INPUT = 0x06               # step 2
CMD_STDBY_MUTE = 0x03          # steps 3 & 5 BOTH use this cmd; data discriminates
CMD_CMD1D = 0x1D               # step 4
CMD_PRESET = 0x20              # step 6 (V1.71 Layer 2 NEW)

# cmd 0x03 data byte encoding (per V1.6b standby_wake_broadcast / mute_frame_send):
#   0x00 = standby, 0x01 = wake, 0x02 = mute_on, 0x03 = mute_off
DATA_STBY = {0x00, 0x01}        # standby_wake_broadcast (step 5)
DATA_MUTE = {0x02, 0x03}        # mute_frame_send (step 3)

PRESET_FRAME_A = (ROUTE_BROADCAST, CMD_PRESET, 0x00)
PRESET_FRAME_B = (ROUTE_BROADCAST, CMD_PRESET, 0x01)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_layer2")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    if not _IMPORT_OK:
        pytest.skip("control_gpsim harness not importable")


def _equ_address(text: str, name: str) -> int | None:
    m = re.search(rf"^\s*{re.escape(name)}\s+equ\s+(0x[0-9A-Fa-f]+)\s*$", text, re.MULTILINE)
    return int(m.group(1), 16) if m else None


def _full_sync_body(asm_text: str) -> str:
    start = asm_text.find("full_sync_burst:")
    assert start >= 0, "full_sync_burst label missing"
    # Body extends to the next top-level label or the end-of-region marker.
    # Capture a generous window — the dispatch shape is small (~30 instructions).
    return asm_text[start:start + 4000]


# ===========================================================================
# Tier A — source-level structural assertions
# ===========================================================================


def test_ram_inc_defines_v171_full_sync_step_at_0x070() -> None:
    """The step-machine state byte must repurpose the V1.61b preset retry slot.

    Pinning the EQU value (0x070) here documents the repurpose so any
    future change that revives 0x070 with different semantics has to
    update both ram.inc and this test together.  Note: the EQU value
    is the BANKED-form 8-bit operand; the firmware sets BSR=1 before
    every access, so the physical address is 0x170.
    """
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    addr = _equ_address(text, "v171_full_sync_step")
    assert addr == V171_FULL_SYNC_STEP_EQU, (
        f"v171_full_sync_step EQU expected at 0x{V171_FULL_SYNC_STEP_EQU:03X} "
        f"(BANKED-form operand; physical address with BSR=1 is "
        f"0x{V171_FULL_SYNC_STEP_PHYS:03X}); "
        f"ram.inc has {('0x%03X' % addr) if addr is not None else None}"
    )


def test_ram_inc_documents_0x071_deprecation() -> None:
    """0x071 (V1.61b preset_primed_flag) must NOT be re-equated under a
    new symbol — Layer 2 drops the retry queue, so any new use of 0x071
    needs a deliberate review (and a corresponding ram.inc edit)."""
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    # No EQU should resolve to 0x071 (the byte stays unallocated).
    assert _equ_address(text, "v171_preset_primed_flag") is None
    # And the deprecation note should be present so a reader doesn't
    # silently re-introduce a use.
    assert "0x071" in text, (
        "ram.inc must explicitly mention 0x071 deprecation under Layer 2"
    )


def test_full_sync_burst_advances_step_with_incf_and_wraps_at_6() -> None:
    """Body must contain the advance + wrap pattern."""
    body = _full_sync_body(V171_CONTROL_ASM.read_text(encoding="utf-8"))
    assert re.search(r"incf\s+v171_full_sync_step", body), (
        "Layer 2 body must increment v171_full_sync_step on entry"
    )
    assert re.search(r"cpfsgt\s+v171_full_sync_step", body), (
        "Layer 2 body must compare step against the 6-step ceiling"
    )
    # Wrap path stores 0x01 back into v171_full_sync_step.
    assert re.search(r"movlw\s+0x01\s*\n\s*movwf\s+v171_full_sync_step", body), (
        "Layer 2 wrap path must reset step to 0x01"
    )


def test_full_sync_burst_dispatches_all_six_frame_helpers_via_goto() -> None:
    """All 6 step branches must tail-call (goto) the corresponding
    frame_send helper — no further return overhead, no leftover delay_short.
    """
    body = _full_sync_body(V171_CONTROL_ASM.read_text(encoding="utf-8"))
    expected_targets = [
        "volume_frame_send",
        "input_frame_send",
        "mute_frame_send",
        "cmd1d_setting_frame_send",
        "standby_wake_broadcast",
        "v171_send_preset_frame_txonly",
    ]
    for target in expected_targets:
        assert re.search(rf"goto\s+{re.escape(target)}", body), (
            f"Layer 2 dispatch missing goto {target}"
        )


def test_full_sync_burst_has_no_delay_short_calls() -> None:
    """V1.6b's 4 inter-frame ``call delay_short`` calls must be dropped —
    natural iteration spacing replaces them.

    Lingering delay_short calls would mean the back-to-back-burst
    structure has crept back in.
    """
    body = _full_sync_body(V171_CONTROL_ASM.read_text(encoding="utf-8"))
    assert "delay_short" not in body, (
        "Layer 2 must drop all delay_short inter-frame pacing calls"
    )


def test_full_sync_burst_has_no_v161b_retry_counter_block() -> None:
    """The V1.61b 0x70/0x71 retry queue is dead under Layer 2 — preset
    is now value-bearing in step 6.  Body must NOT reference the
    retry-counter labels or directly manipulate 0x70/0x71."""
    body = _full_sync_body(V171_CONTROL_ASM.read_text(encoding="utf-8"))
    # The V1.61b labels:
    for legacy in ("v171_fs_connected", "v171_fs_send_check", "v171_fs_continue"):
        assert legacy not in body, (
            f"Layer 2 must drop V1.61b retry block label {legacy!r}"
        )
    # Direct manipulation of 0x71 (primed flag) — the slot is now dead.
    assert not re.search(r"\b0x71,\s*BANKED", body), (
        "Layer 2 must not touch 0x071 (V1.61b preset_primed_flag, deprecated)"
    )


def test_full_sync_burst_does_not_persist_preset_to_eeprom_on_periodic_emit() -> None:
    """Step 6 must call the *_txonly* helper so periodic broadcast does
    not chew through EEPROM endurance.

    Body window is constrained to the function body up to the first
    blank-line + label boundary so we don't pick up the helper
    definitions (which DO mention _and_persist) below the routine.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("full_sync_burst:")
    # End at the first label that's not a v171_fs_* sub-label of this routine.
    # The dispatch ends with `goto v171_send_preset_frame_txonly`; after that
    # the next thing in the file is the `; ====` header for poll_frame_send.
    end_marker = text.find("\n\n\n; =====", start)
    if end_marker < 0:
        end_marker = start + 4000
    body = text[start:end_marker]
    # Strip line comments before structural matching — the dispatch can
    # mention _and_persist in prose without actually calling it.
    code_only = re.sub(r";[^\n]*", "", body)
    assert re.search(r"\bv171_send_preset_frame_txonly\b", code_only), (
        "Layer 2 dispatch must goto v171_send_preset_frame_txonly"
    )
    assert not re.search(
        r"(call|rcall|goto)\s+v171_send_preset_frame_and_persist", code_only
    ), (
        "Layer 2 periodic dispatch must NOT call/goto v171_send_preset_frame_and_persist "
        "— that helper is reserved for user-initiated state changes"
    )


def test_v171_send_preset_frame_txonly_helper_exists_and_skips_eeprom() -> None:
    """Helper used by Layer 2 step 6 must exist and must not write EEPROM."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("v171_send_preset_frame_txonly:")
    assert start >= 0, "v171_send_preset_frame_txonly helper missing"
    end = text.find("v171_send_preset_frame_and_persist:", start)
    assert end >= 0, "v171_send_preset_frame_and_persist helper missing"
    txonly = text[start:end]
    assert "eeprom_write_byte" not in txonly, (
        "v171_send_preset_frame_txonly must not call eeprom_write_byte"
    )
    assert "EEADR" not in txonly, (
        "v171_send_preset_frame_txonly must not touch EEADR"
    )


def test_v171_send_preset_frame_and_persist_delegates_to_txonly_then_writes_eeprom() -> None:
    """User-initiated path layers EEPROM persist on top of the TX-only
    helper — change-once, two callers."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("v171_send_preset_frame_and_persist:")
    assert start >= 0
    body = text[start:start + 1200]
    assert "rcall" in body and "v171_send_preset_frame_txonly" in body, (
        "v171_send_preset_frame_and_persist must reuse the txonly helper"
    )
    assert "eeprom_write_byte" in body, (
        "v171_send_preset_frame_and_persist must invoke eeprom_write_byte"
    )


def test_full_sync_burst_header_documents_layer2_and_bug_c7() -> None:
    """Header should reference both the BUG C7 root cause and the Layer 2 fix."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    header_start = text.find("; full_sync_burst @")
    body_start = text.find("full_sync_burst:", header_start)
    header = text[header_start:body_start]
    assert "C7" in header
    assert "Layer 2" in header
    assert "value-bearing" in header.lower(), (
        "header should explain that preset is now value-bearing (architectural rationale)"
    )


# ===========================================================================
# Tier B — build verification + symbol resolution
# ===========================================================================


def test_v171_layer2_assembles_without_errors(v171_hex: Path) -> None:
    assert v171_hex.exists() and v171_hex.stat().st_size > 0


def test_v171_layer2_vector_block_byte_identical(v171_hex: Path) -> None:
    """Phase-A guarantee: 0x0000–0x004B must always match stock."""
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v171_hex)
    for addr in range(0x0000, 0x004C):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"vector block diverges at 0x{addr:04X}"
        )


def test_v171_layer2_bootloader_byte_identical(v171_hex: Path) -> None:
    """Phase-A guarantee: 0x7800–0x7FFF must always match stock."""
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v171_hex)
    for addr in range(0x7800, 0x8000):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"bootloader diverges at 0x{addr:04X}"
        )


def test_v171_layer2_dispatch_labels_resolve(v171_hex: Path) -> None:
    from dlcp_fw.sim.v30_symbols import load_gpasm_symbols_for_hex
    syms = load_gpasm_symbols_for_hex(v171_hex)
    expected = [
        "full_sync_burst",
        "v171_fs_step_in_range",
        "v171_fs_try_step_2",
        "v171_fs_try_step_3",
        "v171_fs_try_step_4",
        "v171_fs_try_step_5",
        "v171_fs_try_step_6",
        "v171_send_preset_frame_txonly",
        "v171_send_preset_frame_and_persist",
    ]
    for name in expected:
        addr = syms.get(name)
        assert isinstance(addr, int), f"symbol {name} did not resolve"
        assert 0x0000 <= addr < 0x7800, (
            f"symbol {name} at 0x{addr:04X} is outside the user-flash range"
        )


# ===========================================================================
# Tier C — behavioral via gpsim
# ===========================================================================


def _boot(hex_path: Path) -> "GpsimControlHarness":
    return GpsimControlHarness(
        hex_path,
        fast_boot=False,
        chunk_cycles=600_000,
        heartbeat_rx_mode="full",
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_layer2_step_advances_through_full_cycle(v171_hex: Path) -> None:
    """After enough warmup for the periodic full-sync trigger to fire
    several times, ``v171_full_sync_step`` should land in the 1..6
    range — proving the state machine is being driven and the wrap
    is keeping the value bounded."""
    _require_gpsim()
    h = _boot(v171_hex)
    try:
        h.warmup(40_000_000)
        for _ in range(80):
            h.step()
        step = _read_reg(h._issue, V171_FULL_SYNC_STEP_PHYS)
        assert 1 <= step <= 6, (
            f"v171_full_sync_step out of range after warmup: 0x{step:02X} "
            f"(expected 1..6, value 0 means trigger never fired, value > 6 "
            f"means wrap is broken)"
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_layer2_emits_all_six_step_frame_types_after_warmup(v171_hex: Path) -> None:
    """After enough trigger cycles for every step to fire at least once,
    all six step destinations must appear in the TX stream.

    Note that cmd 0x03 is shared between mute_frame_send (step 3, data
    in {0x02, 0x03}) and standby_wake_broadcast (step 5, data in
    {0x00, 0x01}), so to prove both steps fired we need to inspect
    (cmd, data) pairs for cmd 0x03 — not just the cmd byte alone.
    """
    _require_gpsim()
    h = _boot(v171_hex)
    try:
        # Need ≥6 full-sync triggers for every step to fire.  At
        # ~80,000 main-loop iterations per trigger, ≥480k iters total.
        # Extra warmup margin to be robust against startup variance.
        h.warmup(80_000_000)
        for _ in range(160):
            h.step()
        frames = h.tx_frames()
        cmds_seen = {f.cmd for f in frames}
        cmd03_data = {f.data for f in frames if f.cmd == CMD_STDBY_MUTE}
        # Single-cmd steps: each must have at least one frame in the stream.
        for cmd, name in (
            (CMD_VOLUME, "step 1 volume"),
            (CMD_INPUT, "step 2 input"),
            (CMD_CMD1D, "step 4 cmd1d_setting"),
            (CMD_PRESET, "step 6 preset (Layer 2 NEW)"),
        ):
            assert cmd in cmds_seen, (
                f"Layer 2 dispatch did not fire {name}; "
                f"observed cmds={sorted(hex(c) for c in cmds_seen)}"
            )
        # Shared-cmd steps: cmd 0x03 must show BOTH a mute-data byte
        # AND a standby-data byte to prove steps 3 and 5 both fired.
        assert cmd03_data & DATA_STBY, (
            f"step 5 (standby_wake_broadcast) did not fire — cmd 0x03 stream "
            f"contains no standby/wake data byte; observed cmd03 data={sorted(hex(d) for d in cmd03_data)}"
        )
        assert cmd03_data & DATA_MUTE, (
            f"step 3 (mute_frame_send) did not fire — cmd 0x03 stream "
            f"contains no mute data byte; observed cmd03 data={sorted(hex(d) for d in cmd03_data)}"
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_layer2_preset_frame_appears_without_v161b_retry_arm(v171_hex: Path) -> None:
    """The Layer-2 design replaces the V1.61b reconnect-edge retry queue
    (0x70/0x71) with periodic value-bearing emit.  This test verifies
    the preset frame appears in the TX stream EVEN THOUGH 0x70 is
    repurposed and the V1.61b "primed" handshake is gone — i.e. the
    new dispatch path is the actual driver, not residual state.
    """
    _require_gpsim()
    h = _boot(v171_hex)
    try:
        h.warmup(80_000_000)
        for _ in range(160):
            h.step()
        tx = {(f.route, f.cmd, f.data) for f in h.tx_frames()}
        assert PRESET_FRAME_A in tx or PRESET_FRAME_B in tx, (
            f"no preset frame in TX after warmup; got {sorted(tx)}"
        )
        # Also confirm 0x70 holds a Layer-2 step value (1..6), not a
        # legacy V1.61b retry counter (which would be 0..3).
        step = _read_reg(h._issue, V171_FULL_SYNC_STEP_PHYS)
        assert 1 <= step <= 6, (
            f"0x070 holds 0x{step:02X}, outside the Layer-2 step range — "
            f"is the V1.61b retry counter still alive?"
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_layer2_no_dual_preset_frames_per_trigger(v171_hex: Path) -> None:
    """Sanity check: each full-sync trigger emits AT MOST one preset
    frame.  If both the legacy V1.61b retry block and the Layer-2 step
    machine were active, we'd see ≥2 preset frames per trigger window
    (the legacy block emits when 0x70 > 0, the new step 6 emits every
    cycle).  With the legacy block fully removed, each trigger window
    contributes exactly one frame of each step type.
    """
    _require_gpsim()
    h = _boot(v171_hex)
    try:
        h.warmup(40_000_000)
        for _ in range(60):
            h.step()
        baseline = sum(1 for f in h.tx_frames() if f.cmd == CMD_PRESET)
        # One more trigger window worth of steps.
        for _ in range(60):
            h.step()
        followup = sum(1 for f in h.tx_frames() if f.cmd == CMD_PRESET)
        delta = followup - baseline
        # In one window of ~60 chunk-steps, the Layer-2 dispatch can
        # emit at most a couple of preset frames (each requires step
        # to land on 6, which happens ~once per 6 triggers).  Anything
        # ≥6 in a single 60-step window strongly suggests the legacy
        # retry block is also firing.
        assert delta < 6, (
            f"too many preset frames in a single 60-step window ({delta}); "
            f"suspect the V1.61b retry block is still active alongside Layer 2"
        )
    finally:
        h.close()
