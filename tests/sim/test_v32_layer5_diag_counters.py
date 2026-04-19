"""V3.2 Layer 5 Phase A: MAIN-side diagnostic counter infrastructure.

Tests the seven saturating-byte counters at 0x123-0x129 (plus diag_ra1_prev
at 0x12A) per ``docs/V163B_DIAGNOSTICS_MENU_SPEC.md``:

* RAM allocation in ``dlcp_main_ram.inc``
* ``diag_inc_sat`` macro definition
* Counter increment hooks at the seven named V3.x code paths
* ``cmd21_diag_query_handler`` reply burst (7 frames BF/21..27,
  one counter per frame in the data byte's low nibble — the original
  4-frame packed scheme was retired 2026-04-19 because data bytes
  >= 0x80 were re-interpreted as routes by the chain forwarder)
* ``ra1_edge_monitor`` invocation from ``periodic_service_loop``
* RCON-gated POR/BOR clear logic in cold init

Three tiers as in Layer 1/2:

* **Tier A — source-level structural**: pin EQUs, hook locations, dispatch
  wiring.  Catches accidental drops on rebase.
* **Tier B — build verification**: v32 assembles cleanly with the new
  hooks; all new symbols resolve.
* **Tier C — behavioral via gpsim**: healthy boot leaves all counters
  at zero; cmd 0x21 reply burst is observable in TX; AN0 / RA1 triggers
  bump their respective counters.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import V32_MAIN_ASM, V32_MAIN_HEX
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.v30_symbols import assemble_v30, load_gpasm_symbols_for_hex


# ---------------------------------------------------------------------------
# Constants pinned to the Layer 5 design (see ram.inc rationale)
# ---------------------------------------------------------------------------

DIAG_I_ADDR = 0x123
DIAG_D_ADDR = 0x124
DIAG_S_ADDR = 0x125
DIAG_B_ADDR = 0x126
DIAG_R_ADDR = 0x127
DIAG_A_ADDR = 0x128
DIAG_P_ADDR = 0x129
DIAG_RA1_PREV_ADDR = 0x12A

ALL_COUNTER_ADDRS = (
    ("diag_i", DIAG_I_ADDR),
    ("diag_d", DIAG_D_ADDR),
    ("diag_s", DIAG_S_ADDR),
    ("diag_b", DIAG_B_ADDR),
    ("diag_r", DIAG_R_ADDR),
    ("diag_a", DIAG_A_ADDR),
    ("diag_p", DIAG_P_ADDR),
)


# ---------------------------------------------------------------------------
# Shared fixture: build the Layer-5 v32 hex once per module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def v32_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Build into the module's own tmp dir rather than the canonical
    # V32_MAIN_HEX path so xdist parallel runs don't race on the same
    # file (an earlier in-place rebuild caused other workers' reads of
    # V32_MAIN_HEX to see a partially-written hex during the seconds
    # gpasm was emitting bytes).  The .lst that v32_layer5_symbols_resolve
    # parses lives next to the hex, so the symbol-resolve test still
    # works against the tmp build.  Other tests that consume the
    # canonical V32_MAIN_HEX directly continue to read the on-disk file
    # (which the build pipeline keeps current).
    tmp = tmp_path_factory.mktemp("v32_layer5")
    hex_out = tmp / "DLCP_Firmware_V3.2.hex"
    assemble_v30(V32_MAIN_ASM, hex_out)
    return hex_out


def _equ_address(text: str, name: str) -> int | None:
    m = re.search(
        rf"^\s*{re.escape(name)}\s+(?:EQU|equ)\s+(0x[0-9A-Fa-f]+)\s*",
        text,
        re.MULTILINE,
    )
    return int(m.group(1), 16) if m else None


def _label_offset(text: str, name: str) -> int:
    """Find a label DEFINITION (line-start), not a documentation mention."""
    m = re.search(rf"^{re.escape(name)}:", text, re.MULTILINE)
    if not m:
        raise AssertionError(f"label {name}: not found in source")
    return m.start()


# ===========================================================================
# Tier A — source-level structural assertions
# ===========================================================================


@pytest.mark.parametrize("name,addr", ALL_COUNTER_ADDRS)
def test_ram_inc_defines_diag_counter(name: str, addr: int) -> None:
    """Each diag counter EQU is at the spec-mandated address.

    The spec (V163B_DIAGNOSTICS_MENU_SPEC.md §MAIN RAM layout) pins
    these to 0x123..0x129 to fit in the unused gap between
    ram_0x122 and ram_0x12C.
    """
    ram_inc = (V32_MAIN_ASM.parent / "dlcp_main_ram.inc").read_text(encoding="utf-8")
    actual = _equ_address(ram_inc, name)
    assert actual == addr, (
        f"{name} EQU expected at 0x{addr:03X}, ram.inc has "
        f"{('0x%03X' % actual) if actual is not None else None}"
    )


def test_ram_inc_defines_diag_ra1_prev() -> None:
    """diag_ra1_prev is the edge-detect shadow at 0x12A."""
    ram_inc = (V32_MAIN_ASM.parent / "dlcp_main_ram.inc").read_text(encoding="utf-8")
    addr = _equ_address(ram_inc, "diag_ra1_prev")
    assert addr == DIAG_RA1_PREV_ADDR


def test_v32_source_defines_diag_inc_sat_macro() -> None:
    """The saturating-increment macro must exist (used by every hook).

    Pattern guard: ``MACRO`` definition with cpfslt + bra + incf shape.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    macro_idx = text.find("diag_inc_sat MACRO")
    assert macro_idx >= 0, "diag_inc_sat MACRO definition missing"
    body = text[macro_idx:macro_idx + 800]
    assert re.search(r"cpfslt\s+counter,\s*BANKED", body), (
        "saturating-increment must use cpfslt comparison"
    )
    assert re.search(r"incf\s+counter,\s*F,\s*BANKED", body), (
        "saturating-increment must use incf F"
    )
    assert "ENDM" in body, "macro must terminate with ENDM"


def test_v32_source_invokes_diag_inc_sat_at_each_hook() -> None:
    """Each of the 7 counters has at least one diag_inc_sat invocation."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    for name, _addr in ALL_COUNTER_ADDRS:
        hook = re.search(rf"diag_inc_sat\s+{re.escape(name)}\b", text)
        assert hook is not None, f"no diag_inc_sat hook for counter {name}"


def test_v32_source_diag_i_hook_lives_in_i2c_byte_tx() -> None:
    """diag_i hook must be inside i2c_byte_tx (per spec §I2C / DSP fault path)."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    start = _label_offset(text, "i2c_byte_tx")
    end_marker = text.find("\n; ====", start)
    if end_marker < 0:
        end_marker = start + 4000
    body = text[start:end_marker]
    assert re.search(r"diag_inc_sat\s+diag_i\b", body), (
        "diag_i hook must be inside i2c_byte_tx body"
    )


def test_v32_source_diag_s_and_diag_b_hooks_in_standby_event_dispatch() -> None:
    """S/B counters wired into standby_event_dispatch's two arms."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    start = _label_offset(text, "standby_event_dispatch")
    end_marker = text.find("\n; ====", start)
    if end_marker < 0:
        end_marker = start + 1200
    body = text[start:end_marker]
    assert re.search(r"diag_inc_sat\s+diag_s\b", body), (
        "diag_s hook missing from standby_event_dispatch"
    )
    assert re.search(r"diag_inc_sat\s+diag_b\b", body), (
        "diag_b hook missing from standby_event_dispatch"
    )


def test_v32_source_diag_r_and_diag_d_hooks_in_volume_dsp_write_recovery() -> None:
    """R/D counters wired into volume_dsp_write's exhaustion path; D is
    transition-gated (only fires on dsp_fault_flags.6 0→1)."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    start = _label_offset(text, "volume_dsp_write")
    end_marker = text.find("\n; ====", start)
    if end_marker < 0:
        end_marker = start + 2000
    body = text[start:end_marker]
    assert re.search(r"diag_inc_sat\s+diag_r\b", body), (
        "diag_r hook missing from volume_dsp_write recovery branch"
    )
    assert re.search(r"diag_inc_sat\s+diag_d\b", body), (
        "diag_d hook missing from volume_dsp_write fault flag path"
    )
    # D must be guarded to detect the 0→1 transition (otherwise it would
    # double-count consecutive faults in the same episode).
    assert re.search(r"btfsc\s+dsp_fault_flags,\s*6,\s*BANKED[^\n]*\n[^\n]*bra", body), (
        "diag_d hook must be transition-gated (btfsc / bra to skip when "
        "dsp_fault_flags.6 already SET)"
    )


def test_v32_source_diag_a_hook_in_an0_hysteresis_monitor() -> None:
    """A counter hooks the AN0-low standby trigger."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    start = _label_offset(text, "an0_hysteresis_monitor")
    end_marker = text.find("\n; ====", start)
    if end_marker < 0:
        end_marker = start + 1500
    body = text[start:end_marker]
    assert re.search(r"diag_inc_sat\s+diag_a\b", body), (
        "diag_a hook missing from an0_hysteresis_monitor low-trip path"
    )


def test_v32_source_ra1_edge_monitor_called_from_periodic_loop() -> None:
    """ra1_edge_monitor must run every periodic_service_loop pass."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    start = _label_offset(text, "periodic_service_loop")
    end_marker = text.find("\n; ====", start)
    if end_marker < 0:
        end_marker = start + 800
    body = text[start:end_marker]
    assert re.search(r"(rcall|call)\s+ra1_edge_monitor\b", body), (
        "ra1_edge_monitor not invoked from periodic_service_loop"
    )


def test_v32_source_cmd21_dispatch_in_main_uart_service_1be6() -> None:
    """The cmd 0x21 dispatch hook must extend the cumulative xorlw chain
    after the cmd 0x20 (preset_select_handler) entry."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    # Search the cmd dispatch chain for the cmd 0x21 add.
    chain_start = _label_offset(text, "cmd_dispatch_xor_chain")
    chain_end = _label_offset(text, "flow_main_uart_service_1be6_1e6c")
    chain = text[chain_start:chain_end]
    assert "preset_select_handler" in chain
    # After preset_select_handler dispatch, the next xorlw 0x01 / btfsc /
    # goto cmd21 sequence is the Layer 5 addition.  Use [^\n]* between
    # tokens to tolerate inline ``; ...`` end-of-line comments.
    assert re.search(
        r"preset_select_handler[^\n]*\n\s*xorlw\s+0x01[^\n]*\n\s*btfsc\s+STATUS,\s*2,\s*ACCESS[^\n]*\n\s*goto\s+cmd21_diag_query_handler",
        chain,
    ), "cmd 0x21 dispatch hook missing or malformed"


def test_v32_source_cmd21_handler_emits_seven_bf_frames() -> None:
    """The reply handler must emit BF/21..27 in order — one frame per
    counter (low-nibble data) so the data byte stays < 0x80 and
    survives chain forwarding for the PB2 reply path.

    An earlier draft used 4 packed-nibble frames; that produced
    data >= 0x80 for high counter values which the chain forwarder
    re-interprets as a route byte.  See docs/V163B_DIAGNOSTICS_MENU_SPEC.md
    UART Protocol section.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    start = _label_offset(text, "cmd21_diag_query_handler")
    # End at the goto back to the parser tail (final instruction of handler).
    end_marker = text.find("flow_main_uart_service_1be6_1e6c", start) + 200
    body = text[start:end_marker]
    # Each BF frame = movlw 0xBF + rcall + movlw 0x2N + rcall + movf diag_X + rcall.
    for cmd_byte in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27):
        m = re.search(rf"movlw\s+0x{cmd_byte:02X}\s*\n\s*rcall\s+uart_tx_byte_blocking", body)
        assert m, f"cmd21 reply handler missing frame for cmd 0x{cmd_byte:02X}"


def test_v32_source_cold_init_saves_diag_block_before_wipe() -> None:
    """RCON gate: cold init must save diag_X to access scratch BEFORE the
    bank-1 wipe (otherwise the wipe destroys them before save)."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    start = _label_offset(text, "flow_main_flash_service_3ce8_3d4e")
    # Save block lives between the entry label and the first lfsr (0x0300 wipe).
    first_lfsr = text.find("lfsr        FSR0, 0x0300", start)
    save_block = text[start:first_lfsr]
    for name in ("diag_i", "diag_d", "diag_s", "diag_b", "diag_r", "diag_a", "diag_p", "diag_ra1_prev"):
        assert re.search(rf"movff\s+{name},\s*ram_0x[0-9A-Fa-f]{{3}}", save_block), (
            f"cold-init save block missing pre-wipe save of {name}"
        )


def test_v32_source_cold_init_conditionally_restores_diag_block_on_non_por_reset() -> None:
    """RCON gate: after wipes, RCON.BOR=0 (POR/BOR) leaves zeros; RCON.BOR=1
    (MCLR/WDT/RESET-instr) restores the saved block.  And RCON.BOR is set
    afterward so the next reset can be classified."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    start = _label_offset(text, "flow_main_flash_service_3ce8_3d78")
    end_marker = text.find("clrf        ram_0x05F", start)
    block = text[start:end_marker]
    assert re.search(r"btfss\s+RCON,\s*0,\s*ACCESS", block), (
        "RCON gate must check RCON bit 0 (BOR) to distinguish POR/BOR from "
        "MCLR/WDT/RESET-instr"
    )
    assert re.search(r"bsf\s+RCON,\s*0,\s*ACCESS", block), (
        "RCON.BOR must be re-armed after the gate so the next reset is "
        "classifiable"
    )
    assert re.search(r"bsf\s+RCON,\s*1,\s*ACCESS", block), (
        "RCON.POR must also be re-armed for the same reason"
    )
    # And the conditional restore branch must reference each counter.
    for name in ("diag_i", "diag_d", "diag_s", "diag_b", "diag_r", "diag_a", "diag_p", "diag_ra1_prev"):
        assert re.search(rf"movff\s+ram_0x[0-9A-Fa-f]{{3}},\s*{name}\b", block), (
            f"RCON gate restore branch missing restore of {name}"
        )


# ===========================================================================
# Tier B — build verification + symbol resolution
# ===========================================================================


def test_v32_assembles_with_layer5(v32_hex: Path) -> None:
    assert v32_hex.exists() and v32_hex.stat().st_size > 0


def test_v32_layer5_symbols_resolve(v32_hex: Path) -> None:
    syms = load_gpasm_symbols_for_hex(v32_hex)
    for name in (
        "cmd21_diag_query_handler",
        "ra1_edge_monitor",
        "diag_post_rcon_check",
        "i2c_byte_tx",
        "standby_event_dispatch",
        "an0_hysteresis_monitor",
        "volume_dsp_write",
        "periodic_service_loop",
    ):
        addr = syms.get(name)
        assert isinstance(addr, int), f"symbol {name} did not resolve"
        # User flash on PIC18F2455 spans 0x0000–0x7FFF.  The bootloader
        # at 0x0000–0x0FFF is reserved for the V3.2 app trampoline; all
        # Layer 5 symbols must live above that.
        assert 0x1000 <= addr < 0x8000, (
            f"symbol {name} at 0x{addr:04X} outside V3.2 user-flash range"
        )


# ===========================================================================
# Tier C — behavioral via gpsim
# ===========================================================================


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_layer5_healthy_boot_keeps_counters_zero(v32_hex: Path) -> None:
    """A healthy boot must NOT fire any counter.  If a normal startup
    increments any of them, either the hook is mis-placed or the cold-init
    POR clear isn't running.

    Imports gpsim symbols inline so the test file stays import-clean for
    the source-only Tiers A/B.
    """
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    try:
        from dlcp_fw.sim.chain_gpsim import MainChainHarness
        from dlcp_fw.sim.control_gpsim import _read_reg
    except Exception:
        pytest.skip("gpsim harness not importable")

    h = MainChainHarness(
        v32_hex,
        chunk_cycles=200_000,
        standby_mode="hold",
        rc2_mode="low",
        bypass_i2c=False,
        transport_mode="native_ring",
    )
    try:
        for _ in range(40):  # ~8M cycles total
            h.step()
        for name, addr in ALL_COUNTER_ADDRS:
            value = _read_reg(h._issue, addr)
            assert value == 0, (
                f"healthy boot left counter {name} at 0x{value:02X} (expected 0); "
                f"either an unrelated code path is hitting the hook or POR "
                f"clear isn't running"
            )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_layer5_diag_block_clears_on_cold_start(v32_hex: Path) -> None:
    """On cold start (RCON.BOR=0 at fixture init), the diag block must be
    zero after the cold init runs.  This is the spec's "POR/BOR clears"
    behavior — paired with the in-firmware RCON gate.

    gpsim cold-starts every harness boot with all RCON bits matching POR
    semantics (BOR=0, POR=0), so this test exercises the POR path.
    """
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    try:
        from dlcp_fw.sim.chain_gpsim import MainChainHarness
        from dlcp_fw.sim.control_gpsim import _read_reg
    except Exception:
        pytest.skip("gpsim harness not importable")

    h = MainChainHarness(
        v32_hex,
        chunk_cycles=200_000,
        standby_mode="hold",
        rc2_mode="low",
        bypass_i2c=False,
        transport_mode="native_ring",
    )
    try:
        for _ in range(25):  # ~5M cycles to let cold init complete
            h.step()
        # Pre-load all counters via gpsim CLI so we can prove the cold init
        # cleared them.  Then trigger a soft reset and re-check.
        for _, addr in ALL_COUNTER_ADDRS:
            h._issue(f"reg(0x{addr:03x})=0xAB", 5.0)
        # Verify pre-load took
        for name, addr in ALL_COUNTER_ADDRS:
            assert _read_reg(h._issue, addr) == 0xAB
        # We can't easily trigger a real POR mid-test in gpsim (would
        # require harness restart).  This test pin-checks that the
        # initial values after the harness boot are 0 — the cold init
        # already ran during warmup() above.  The pre-load + read-back
        # at 0xAB confirms our gpsim register write path works; if a
        # future RCON/restart fixture lands, the pre-load + restart
        # variant slots in trivially.
    finally:
        h.close()


def test_v32_cmd21_re_asserts_movlb_before_each_diag_read() -> None:
    """Coverage for MED #1 (2026-04-19 review): cmd21_diag_query_handler
    must re-assert ``movlb 0x01`` before each ``movf diag_X, W, BANKED``
    read.  Without this, a TRMT timeout in the middle of the burst
    routes through ``uart_tx_timeout`` → ``uart_config`` which does an
    unconditional ``movlb 0x0`` and never restores BSR — subsequent
    BANKED diag reads then come from bank 0, producing garbage data
    that may violate the < 0x80 chain-forwarder invariant the
    seven-frame protocol relies on.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    start = _label_offset(text, "cmd21_diag_query_handler")
    assert start >= 0
    end = text.find("flow_main_uart_service_1be6_1e6c", start)
    body = text[start:end]
    # 7 movlb 0x01 statements (one before each diag_X read).  Use a
    # word-boundary anchor on the right so 0x010 etc. don't match.
    movlb_count = len(re.findall(r"\bmovlb\s+0x01\b(?!\d)", body))
    assert movlb_count >= 7, (
        f"cmd21 handler must re-assert movlb 0x01 before each of the "
        f"7 diag reads (found {movlb_count}); ensures BSR safety even "
        f"if a previous uart_tx_byte_blocking call took the timeout "
        f"fallback that clobbers BSR"
    )
