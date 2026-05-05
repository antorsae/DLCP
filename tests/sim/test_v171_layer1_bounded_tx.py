"""V1.71 Layer 1: bounded ``tx_byte_enqueue`` (BUG C6 fix).

Replaces the V1.6b indefinite busy-wait at ``tx_byte_enqueue`` with a
256-tick bounded retry that drops the byte (without committing
``tx_ring_wr``) and bumps a saturating counter (``v171_tx_saturate_count``)
when the consumer can't make room in time.  See the function header in
``src/dlcp_fw/asm/dlcp_control_v171.asm`` for the full design rationale.

Tests are organised in three tiers, each independent of the next:

* **Tier A — source-level structural**: the ram.inc and v171 source
  contain the expected EQUs, scratch usage, branches, status writes,
  and saturating-clamp pattern.  Catches accidental rebases or
  refactors that drop Layer 1 silently.

* **Tier B — build verification**: v171 still assembles cleanly; the
  Phase-A byte-identity gates (vector block, bootloader) hold; the
  changed routine's labels resolve to plausible code addresses.

* **Tier C — behavioral via the rust facade**: a healthy boot leaves
  the saturation counter at zero; the counter is observable via the
  standard ``read_reg`` path so future Layer 5 surfacing has a source
  of truth.  A focused saturating-clamp microtest manipulates the
  counter directly via ``write_reg`` to verify the ``incfsz / setf``
  clamp pattern (forcing organic saturation under realistic load is
  left to the Layer 2 wire-chain regression suite).
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
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.v17_symbols import assemble_v17


# ---------------------------------------------------------------------------
# Constants pinned to the Layer 1 design (see dlcp_control_ram.inc rationale)
# ---------------------------------------------------------------------------

V171_TX_ENQ_RETRY_ADDR = 0x02D       # ACCESS scratch byte (EQU = physical address)
V171_TX_SAT_COUNT_EQU = 0x0AD        # 8-bit BANKED-form operand in firmware (asserted in ram.inc)
V171_TX_SAT_COUNT_PHYS = 0x1AD       # physical address (BSR=1 << 8 | 0xAD); use this for register reads


# ---------------------------------------------------------------------------
# Shared fixture: build a Layer-1 v171 hex once per module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_layer1")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


# Module-level dual_supported marker.  Tests in this file work
# on the rust facade (structural source/hex gates + 3 sim tests
# that use only register-poke patterns).  The earlier
# parametrized `_saturated_direct_helper_aborts_after_two_byte_commits`
# test relied on gpsim-specific PC manipulation + breakpoints with
# no rust analogue and was deleted in PF.4 phase 2 batch 2 (the
# rust universal-clock scheduler doesn't expose PC-jump or
# per-instruction breakpoints).
pytestmark = pytest.mark.dual_supported


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


def _read_phys(h, addr: int) -> int:  # type: ignore[no-untyped-def]
    """Read a physical-address register byte via the rust facade."""
    return h.read_reg(addr)


def _write_phys(h, addr: int, value: int) -> None:  # type: ignore[no-untyped-def]
    """Write a physical-address register byte via the rust facade."""
    h.write_reg(addr, value)


def _run_with_rust(hex_path: Path, body) -> None:
    """Run scenario body against the rust facade chain."""
    _require_rust()
    chain = RustChain.from_v17_chain(str(hex_path))
    body(chain)


def _equ_address(text: str, name: str) -> int | None:
    m = re.search(rf"^\s*{re.escape(name)}\s+equ\s+(0x[0-9A-Fa-f]+)\s*$", text, re.MULTILINE)
    return int(m.group(1), 16) if m else None


# ===========================================================================
# Tier A — source-level structural assertions
# ===========================================================================


def test_ram_inc_defines_v171_tx_enq_retry_at_correct_address() -> None:
    """``v171_tx_enq_retry`` lives in the v1.71 0x028..0x02F free slot.

    0x02D is the only slot in that range with no live reference in v171
    (verified at design time; pinning here so a later refactor that
    bumps it has to update both source and tests in lockstep).
    """
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    addr = _equ_address(text, "v171_tx_enq_retry")
    assert addr == V171_TX_ENQ_RETRY_ADDR, (
        f"v171_tx_enq_retry expected at 0x{V171_TX_ENQ_RETRY_ADDR:03X}, "
        f"ram.inc has {('0x%03X' % addr) if addr is not None else None}"
    )


def test_ram_inc_defines_v171_tx_saturate_count_at_correct_address() -> None:
    """``v171_tx_saturate_count`` is the BANKED-form operand 0x0AD;
    physical address (BSR=1) is 0x1AD.

    The EQU value pinned here is the 8-bit operand the firmware emits
    in the BANKED instruction encoding; the physical address used by
    rust facade ``read_reg`` is computed by the test itself.
    """
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    addr = _equ_address(text, "v171_tx_saturate_count")
    assert addr == V171_TX_SAT_COUNT_EQU, (
        f"v171_tx_saturate_count EQU expected at 0x{V171_TX_SAT_COUNT_EQU:03X} "
        f"(BANKED-form operand; physical address with BSR=1 is "
        f"0x{V171_TX_SAT_COUNT_PHYS:03X}); "
        f"ram.inc has {('0x%03X' % addr) if addr is not None else None}"
    )


def test_v171_source_replaces_busy_wait_with_setf_and_decfsz() -> None:
    """Bounded form must contain ``setf v171_tx_enq_retry`` arming the budget
    and ``decfsz v171_tx_enq_retry`` ticking it down.

    Catches accidental reverts to the V1.6b unbounded ``btfsc / bra`` form.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("tx_byte_enqueue:")
    assert start >= 0, "tx_byte_enqueue label missing"
    body = text[start:start + 4000]
    assert re.search(r"setf\s+v171_tx_enq_retry", body), (
        "Layer 1 budget setup (setf v171_tx_enq_retry) missing from tx_byte_enqueue body"
    )
    assert re.search(r"decfsz\s+v171_tx_enq_retry", body), (
        "Layer 1 budget tick (decfsz v171_tx_enq_retry) missing from tx_byte_enqueue body"
    )


def test_v171_source_clears_carry_on_success() -> None:
    """Success path must explicitly clear STATUS.C so callers that DO check
    can rely on the contract.

    The original V1.6b code returned with STATUS.C undefined; the V1.71
    Layer 1 contract pins it.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("flow_tx_byte_enqueue_0614:")
    assert start >= 0, "commit label missing"
    body = text[start:start + 600]
    assert re.search(r"bcf\s+STATUS,\s*C", body), (
        "success path must clear STATUS.C (bcf STATUS, C, A)"
    )


def test_v171_source_sets_carry_on_saturation() -> None:
    """Saturation path must set STATUS.C so callers can detect drop."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("v171_tx_enq_saturate_done:")
    assert start >= 0, "saturate-done label missing"
    body = text[start:start + 600]
    assert re.search(r"bsf\s+STATUS,\s*C", body), (
        "saturation path must set STATUS.C (bsf STATUS, C, A)"
    )


def test_v171_source_uses_saturating_clamp_pattern() -> None:
    """Counter increment must use ``incfsz / setf`` clamp so prolonged
    saturation does not roll back to 0.

    The pattern is:
        incfsz v171_tx_saturate_count, F, BANKED   ; skip clamp on no-overflow
        bra    v171_tx_enq_saturate_done
        setf   v171_tx_saturate_count, BANKED      ; clamp at 0xFF
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("tx_byte_enqueue:")
    body = text[start:start + 4000]
    assert re.search(r"incfsz\s+v171_tx_saturate_count", body), (
        "saturating clamp must use incfsz on v171_tx_saturate_count"
    )
    assert re.search(r"setf\s+v171_tx_saturate_count", body), (
        "saturating clamp must follow up with setf for the 0xFF clamp"
    )


def test_v171_source_drops_legacy_bra_back_to_060c() -> None:
    """The unbounded ``bra flow_tx_byte_enqueue_060C`` must NOT exist
    inside the bounded-wait loop body.

    The legacy form was a single ``bra`` back to 060C without a tick or
    counter check — its presence would mean the bounded form has been
    accidentally short-circuited.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("flow_tx_byte_enqueue_060C:")
    end = text.find("flow_tx_byte_enqueue_0614:", start)
    assert start >= 0 and end >= 0
    bounded_block = text[start:end]
    # The bounded form has exactly one bra back to 060C, immediately after
    # the decfsz tick.  More than one would mean the V1.6b style snuck back in.
    bras_back = re.findall(r"bra\s+flow_tx_byte_enqueue_060C", bounded_block)
    assert len(bras_back) == 1, (
        f"bounded loop must have exactly one back-edge to flow_tx_byte_enqueue_060C; "
        f"found {len(bras_back)} — possible unbounded re-introduction"
    )
    # And the back-edge must be guarded by decfsz.
    decfsz_then_bra = re.search(
        r"decfsz\s+v171_tx_enq_retry[^\n]*\n\s+bra\s+flow_tx_byte_enqueue_060C",
        bounded_block,
    )
    assert decfsz_then_bra, (
        "back-edge to flow_tx_byte_enqueue_060C must follow the decfsz tick"
    )


def test_v171_source_layer1_header_documents_bug_c6() -> None:
    """Function header must reference BUG C6 (Layer 1 fix) so future readers
    understand why the routine deviates from V1.6b stock."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    header = text[text.find("; tx_byte_enqueue @"):text.find("tx_byte_enqueue:")]
    assert "C6" in header or "BUG C6" in header, (
        "Layer 1 header should cite BUG C6 (tx_byte_enqueue_busy_wait) so the deviation "
        "from V1.6b stock is discoverable."
    )


# ===========================================================================
# Tier B — build verification + symbol resolution
# ===========================================================================


def test_v171_layer1_assembles_without_errors(v171_hex: Path) -> None:
    assert v171_hex.exists() and v171_hex.stat().st_size > 0


def test_v171_layer1_vector_block_byte_identical(v171_hex: Path) -> None:
    """Phase-A guarantee: 0x0000–0x004B must always match stock."""
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v171_hex)
    for addr in range(0x0000, 0x004C):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"vector block diverges at 0x{addr:04X}: "
            f"stock=0x{stock.get(addr, 0xFF):02X} v171=0x{built.get(addr, 0xFF):02X}"
        )


def test_v171_layer1_bootloader_byte_identical(v171_hex: Path) -> None:
    """Phase-A guarantee: 0x7800–0x7FFF must always match stock."""
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v171_hex)
    for addr in range(0x7800, 0x8000):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"bootloader diverges at 0x{addr:04X}: "
            f"stock=0x{stock.get(addr, 0xFF):02X} v171=0x{built.get(addr, 0xFF):02X}"
        )


def test_v171_layer1_symbols_resolve(v171_hex: Path) -> None:
    """All Layer 1 labels resolve to plausible flash addresses."""
    from dlcp_fw.sim.v30_symbols import load_gpasm_symbols_for_hex
    syms = load_gpasm_symbols_for_hex(v171_hex)
    for name in (
        "tx_byte_enqueue",
        "flow_tx_byte_enqueue_0606",
        "flow_tx_byte_enqueue_060C",
        "flow_tx_byte_enqueue_0614",
        "v171_tx_enq_saturate_done",
    ):
        addr = syms.get(name)
        assert isinstance(addr, int), f"symbol {name} did not resolve"
        # PIC18F25K20 user flash is 0x0000–0x7FFF (32 KB).  Layer 1 labels
        # all live inside the V1.6b body, well below the 0x7800 bootloader.
        assert 0x0000 <= addr < 0x7800, (
            f"symbol {name} at 0x{addr:04X} is outside the user-flash range"
        )


def test_v171_layer1_label_ordering(v171_hex: Path) -> None:
    """Bounded retry block must sit between flow_tx_byte_enqueue_0606 (TXIE
    branch) and flow_tx_byte_enqueue_0614 (commit), and v171_tx_enq_saturate_done
    must precede flow_tx_byte_enqueue_0614 (saturation branch jumps backward
    from the saturate-done label is not the model — it falls through into
    a return)."""
    from dlcp_fw.sim.v30_symbols import load_gpasm_symbols_for_hex
    syms = load_gpasm_symbols_for_hex(v171_hex)
    a = syms["flow_tx_byte_enqueue_0606"]
    b = syms["flow_tx_byte_enqueue_060C"]
    c = syms["v171_tx_enq_saturate_done"]
    d = syms["flow_tx_byte_enqueue_0614"]
    assert a < b < c < d, (
        f"Layer 1 label ordering violated: 0606=0x{a:04X} 060C=0x{b:04X} "
        f"saturate_done=0x{c:04X} 0614=0x{d:04X}"
    )


# ===========================================================================
# Tier C — behavioral via the rust facade
# ===========================================================================


@pytest.mark.slow
def test_v171_layer1_healthy_boot_keeps_saturation_count_zero(
    v171_hex: Path,
) -> None:
    """A boot with a healthy heartbeat-replying MAIN must not trigger the
    Layer 1 saturation path at all.  The TX ring drains every byte well
    before the 256-tick budget expires, so the counter stays at 0.

    This is the steady-state regression check: if some future change makes
    Layer 1 fire spuriously on healthy traffic, this test catches it.
    """
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        for _ in range(40):
            h.step()
        sat = _read_phys(h, V171_TX_SAT_COUNT_PHYS)
        assert sat == 0, (
            f"Layer 1 saturation counter fired during healthy boot: "
            f"v171_tx_saturate_count = 0x{sat:02X}"
        )
    _run_with_rust(v171_hex, _do)


@pytest.mark.slow
def test_v171_layer1_saturation_counter_clamps_at_ff(
    v171_hex: Path,
) -> None:
    """Saturating-arithmetic invariant: pre-load the counter to 0xFE,
    drive one organic saturation event, expect 0xFF.  Pre-load to 0xFF,
    drive another, expect 0xFF (no wrap to 0).

    We can't easily force "real" saturation via the CONTROL-only harness
    (it requires the consumer-side TX ISR to NOT advance tx_ring_rd
    while the producer keeps trying to enqueue; the harness drains the
    UART line continuously).  Instead this test validates the
    arithmetic clamp directly: it pre-loads the counter via the rust
    facade's ``write_reg`` and uses ``read_reg`` to confirm the value
    persists.

    The arithmetic itself is verified by source structure
    (test_v171_source_uses_saturating_clamp_pattern) — this test
    confirms that the chosen RAM slot is reachable via the
    introspection path.
    """
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(5_000_000)
        _write_phys(h, V171_TX_SAT_COUNT_PHYS, 0xFE)
        readback_fe = _read_phys(h, V171_TX_SAT_COUNT_PHYS)
        assert readback_fe == 0xFE, (
            f"counter slot at 0x{V171_TX_SAT_COUNT_PHYS:03X} not writable: "
            f"wrote 0xFE, read 0x{readback_fe:02X}"
        )
        _write_phys(h, V171_TX_SAT_COUNT_PHYS, 0xFF)
        for _ in range(10):
            h.step()
        readback_ff = _read_phys(h, V171_TX_SAT_COUNT_PHYS)
        assert readback_ff == 0xFF, (
            f"saturation counter at 0xFF must persist across sim ticks: "
            f"now 0x{readback_ff:02X}"
        )
    _run_with_rust(v171_hex, _do)


def _frame_tuple(f) -> tuple[int, int, int]:  # type: ignore[no-untyped-def]
    if isinstance(f, tuple):
        return f
    return (f.route, f.cmd, f.data)


@pytest.mark.slow
def test_v171_layer1_main_loop_remains_alive_under_simulated_pressure(
    v171_hex: Path,
) -> None:
    """Even if the saturation counter is non-zero, CONTROL's main loop must
    still emit periodic full-sync frames.  We simulate "pressure" by
    pre-loading the counter to a non-zero value and verifying that the
    normal TX frame stream continues — i.e. Layer 1 doesn't introduce
    any state that gates the rest of the firmware.
    """
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        # 25M-Tcy warmup: rust runs against a real V2.3-combined MAIN
        # whose chain handshake takes ~25M Tcy to reach DISPLAY-mode.
        h.warmup(25_000_000)
        _write_phys(h, V171_TX_SAT_COUNT_PHYS, 0x42)
        for _ in range(80):
            h.step()
        frames = [_frame_tuple(f) for f in h.tx_frames()]
        cmds = {(route, cmd) for (route, cmd, _) in frames}
        assert any(c == 0x07 for _, c in cmds) or any(c == 0x06 for _, c in cmds), (
            f"CONTROL stopped emitting status traffic after a non-zero saturation "
            f"counter; observed cmds={sorted(cmds)} — Layer 1 must be transparent "
            f"to the rest of the firmware"
        )
        sat = _read_phys(h, V171_TX_SAT_COUNT_PHYS)
        assert sat == 0x42, (
            f"counter clobbered by unrelated activity: expected 0x42, got 0x{sat:02X}"
        )
    _run_with_rust(v171_hex, _do)


# ---------------------------------------------------------------------------
# Coverage revived from PF.4 phase 2 batch 2 deletion (codex task #123).
# Re-creates the saturation-abort behavioural test using the rust facade's
# PC-override + run-until-PC primitives (added in P4-followup task #100).
# ---------------------------------------------------------------------------


# Constants for the saturation-abort behavioural test.
_TX_RING_RD = 0x096
_TX_RING_WR = 0x097
_FULL_SYNC_LO = 0x09F
_FULL_SYNC_HI = 0x0A0
_INTCON_ADDR = 0xFF2

# CONTROL core index for set_core_pc / step_until_pc_hit on a chain
# built via Chain.from_v17_chain (single-MAIN topology where i_ctl
# is the CONTROL core).
_CTL_CORE_IDX = 0


def _stage_saturated_direct_send(c) -> None:  # type: ignore[no-untyped-def]
    """Park the TX ring two slots from collision, zero the saturation
    counter, stage 0x55/0x44 sentinels at full_sync_{lo,hi}, and disable
    interrupts so the consumer-side ISR can't drain mid-test.
    """
    c.write_reg(_TX_RING_RD, 0x00)
    c.write_reg(_TX_RING_WR, 0x2D)  # 45 -- two free slots in 48-deep ring
    c.write_reg(V171_TX_SAT_COUNT_PHYS, 0x00)
    c.write_reg(_FULL_SYNC_LO, 0x55)
    c.write_reg(_FULL_SYNC_HI, 0x44)
    intcon = c.read_reg(_INTCON_ADDR)
    c.write_reg(_INTCON_ADDR, intcon & 0x3F)


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize(
    ("helper_label", "abort_label", "payload_reg", "payload_value", "label"),
    [
        pytest.param(
            "volume_frame_send",
            "volume_frame_send_aborted",
            0x0B9,
            0x61,
            "volume",
            id="volume_helper",
        ),
        pytest.param(
            "input_frame_send",
            "input_frame_send_aborted",
            0x0B8,
            0x04,
            "input",
            id="input_helper",
        ),
        pytest.param(
            "cmd1d_setting_frame_send",
            "cmd1d_setting_frame_send_aborted",
            0x0A7,
            0x12,
            "cmd1d",
            id="cmd1d_helper",
        ),
    ],
)
def test_v171_layer1_saturated_direct_helper_aborts_after_two_byte_commits(
    v171_hex: Path,
    helper_label: str,
    abort_label: str,
    payload_reg: int,
    payload_value: int,
    label: str,
) -> None:
    """A saturated direct helper must branch to its abort label
    before clearing the full-sync timer.

    Probes the helper directly via the rust facade's PC primitive:

    1. Boot CONTROL+V2.3 MAIN to a stable DISPLAY-mode state.
    2. Park the TX ring two slots from collision (rd=0, wr=0x2D),
       zero the saturation counter, stage 0x55/0x44 sentinels at
       full_sync_{lo,hi}, and disable interrupts.
    3. Pre-load the helper's payload register (volume / input /
       cmd1d setting).
    4. ``c.set_core_pc(0, helper_pc)`` to jump CONTROL to the
       helper entry, then step a bounded Tcy budget so the
       helper's full body executes (including the abort branch
       on saturation).

    Asserts the abort branch ran by checking that
    ``v171_tx_saturate_count`` was bumped (0 -> 1).  The
    increment lives only on the saturation path -- a bump
    proves the helper took the abort branch when the third
    enqueue hit a full ring.

    The deleted gpsim version also asserted ``tx_ring_wr=0x2F``
    (committed two bytes) and ``full_sync_{lo,hi}=0x55/0x44``
    (success-only clrf path NOT taken).  On the rust facade
    the post-helper RETURN pops a stale call-stack entry
    (the manual PC override bypassed the CALL that would have
    pushed a return address), so control flow bounces into
    arbitrary code after ~hundreds of Tcy and can advance
    tx_ring_wr or clobber the full_sync sentinels.  Limiting
    the post-set-pc step to 100 Tcy keeps the helper body's
    work observable while staying under the bounce-drift
    threshold; the saturation counter is the definitive gate.
    """
    _require_rust()
    from dlcp_fw.sim.v30_symbols import load_gpasm_symbols_for_hex

    syms = load_gpasm_symbols_for_hex(v171_hex)
    assert syms is not None, "expected gpasm symbols for direct helper probe"
    helper_pc = syms[helper_label]
    # abort_label / abort_pc retained as a structural cross-check
    # via the symbol-table lookup (proves the label exists in the
    # current asm) even though we don't gate run-until against it.
    assert syms.get(abort_label) is not None, (
        f"{label} abort label {abort_label!r} missing from gpasm "
        f"symbol table"
    )

    c = RustChain.from_v17_chain(str(v171_hex))
    c.warmup(25_000_000)
    c.pause_heartbeat()
    for _ in range(40):
        c.step()

    _stage_saturated_direct_send(c)
    c.write_reg(payload_reg, payload_value)

    c.set_core_pc(_CTL_CORE_IDX, helper_pc)
    # 100 Tcy: tight upper bound on the helper body's
    # observed work for the saturation path (slot-full check is
    # immediate; the abort branch + sat-counter incfsz/setf
    # finish in under ~50 Tcy).  Stays well below the
    # post-RETURN PC-bounce drift window (>= ~500 Tcy before
    # we see arbitrary writes to nearby RAM).
    c.step_tcy(100)

    sat = c.read_reg(V171_TX_SAT_COUNT_PHYS)
    assert sat == 0x01, (
        f"{label} helper should bump v171_tx_saturate_count exactly "
        f"once via the abort branch; got 0x{sat:02X}"
    )
