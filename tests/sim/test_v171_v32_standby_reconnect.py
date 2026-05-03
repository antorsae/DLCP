"""V1.71 CONTROL × V3.2 MAIN standby/wake reconnect regression.

The field failure for the current recommended pair was:

1. Reach the normal Volume screen.
2. Enter standby with `STBY`.
3. Press `STBY` again to wake.
4. CONTROL falls into `WAITING FOR DLCP` instead of returning to display.

This file pins the MAIN-side hardening that fixes that path:

* `adc_boot_gate` must quiesce the UART before the long wake delays,
  then re-run the cold-boot UART init before resuming traffic.
* MAIN's OERR recovery must drain the 2-byte hardware FIFO before
  re-enabling CREN.
* `adc_boot_gate_exit` must re-emit the `B0/03/01` WAKE broadcast post-gate
  so a downstream MAIN that received only the truncated `B0/03` from this
  MAIN's pre-gate forward (because `uart_quiesce_for_wake` killed TX before
  byte 3 hit the wire) gets a complete frame and can dispatch
  `wake_request_handler`.  This is the Bug #45 H2 firmware mitigation.
* The cross-firmware standby/wake contract must stay intact:
  V3.2 answers cmd 0x04 with the sentinel-clearing burst, and V1.71
  sends wake both when leaving `Zzz...` and when reconnect completes.
  The slow gpsim pair harness still hangs intermittently in this path,
  so this file keeps the deterministic source-level integration gate.
"""

from __future__ import annotations

import pytest

from dlcp_fw.paths import V171_CONTROL_ASM, V32_MAIN_ASM

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_OK = True
    _RUST_ERR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_OK = False
    _RUST_ERR = exc


# Pure source / hex integrity gates -- no sim backend needed.
# See `test_v171_atomic_3byte_frame.py` for the full rationale.
pytestmark = pytest.mark.dual_supported


def test_v32_source_hardens_wake_uart_path() -> None:
    text = V32_MAIN_ASM.read_text(encoding="utf-8")

    adc_start = text.find("adc_boot_gate:")
    adc_end = text.find("flash_write:", adc_start)
    assert adc_start != -1 and adc_end > adc_start, "adc_boot_gate body not found"
    adc_body = text[adc_start:adc_end]
    for token in (
        "call        uart_quiesce_for_wake, 0x0",
        "call        main_uart_tx_only_service, 0x0",
        "call        cmd_dispatch_gated, 0x0",
        "call        send_status_burst, 0x0",
        "call        main_uart_service_4938, 0x0",
        "bsf         PIE1, 5, ACCESS",
    ):
        assert token in adc_body, f"adc_boot_gate missing {token!r}"
    assert adc_body.index("call        main_uart_tx_only_service, 0x0") < adc_body.index(
        "call        cmd_dispatch_gated, 0x0"
    ), "wake TX-only rearm must happen before cmd_dispatch_gated can emit BF/08"
    assert adc_body.index("call        cmd_dispatch_gated, 0x0") < adc_body.index(
        "call        send_status_burst, 0x0"
    ), "wake-time state reconciliation must finish before MAIN advertises sentinel-clearing status"
    assert adc_body.index("call        send_status_burst, 0x0") < adc_body.index(
        "call        main_uart_service_4938, 0x0"
    ), "full UART RX rearm must happen after the post-wake sentinel burst"


def test_v32_source_re_emits_wake_broadcast_post_gate() -> None:
    """Bug #45 H2 source-contract: adc_boot_gate_exit must re-emit
    `B0/03/01` AFTER `main_uart_tx_only_service` re-arms TX and BEFORE
    `cmd_dispatch_gated` runs.  Without this, a downstream MAIN that
    only received the truncated `B0/03` from this MAIN's pre-gate
    forward (because uart_quiesce_for_wake at gate entry killed the TX
    path before byte 3 hit the wire) never sees the complete WAKE
    broadcast and stays standby."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    exit_start = text.find("adc_boot_gate_exit:")
    exit_end = text.find("flash_write:", exit_start)
    assert exit_start != -1 and exit_end > exit_start, "adc_boot_gate_exit body not found"
    body = text[exit_start:exit_end]
    rearm_idx = body.index("call        main_uart_tx_only_service, 0x0")
    dispatch_idx = body.index("call        cmd_dispatch_gated, 0x0")
    rebroadcast = body[rearm_idx:dispatch_idx]
    # Three uart_tx_byte_blocking calls in sequence carrying B0, 03, 01.
    for token in (
        "movlw       0xB0",
        "movlw       0x03",
        "movlw       0x01",
        "call        uart_tx_byte_blocking, 0x0",
    ):
        assert token in rebroadcast, (
            f"post-gate WAKE re-emit missing {token!r}; required between "
            f"main_uart_tx_only_service and cmd_dispatch_gated"
        )
    assert rebroadcast.index("movlw       0xB0") < rebroadcast.index("movlw       0x03"), (
        "Bug #45 H2 re-emit must order route-byte 0xB0 before cmd-byte 0x03"
    )
    assert rebroadcast.index("movlw       0x03") < rebroadcast.index("movlw       0x01"), (
        "Bug #45 H2 re-emit must order cmd-byte 0x03 before data-byte 0x01"
    )
    assert rebroadcast.count("call        uart_tx_byte_blocking, 0x0") >= 3, (
        "Bug #45 H2 re-emit must call uart_tx_byte_blocking three times "
        "(once per byte); each call is the bounded TRMT-wait + TXREG store"
    )


@pytest.mark.dual_supported
def test_v171_v32_v32_panel_wake_brings_up_main1_via_h2_re_emit(
    dlcp_sim_backend: str,
) -> None:
    """Bug #45 H2 dynamic regression: panel-press WAKE on the V1.71+V3.2+V3.2
    canonical pair must wake MAIN1 (not just MAIN0).

    Pre-fix observable: only MAIN0 woke (LATB.bit3/bit4 + LATA.bit6 high);
    MAIN1 stayed in standby (latches=0, db=0) because MAIN0's pre-gate
    forward of CONTROL's WAKE broadcast was truncated to `B0 03 ...`
    when uart_quiesce_for_wake disabled TX before byte 3 hit the wire.
    Without a complete `B0/03/01` frame MAIN1's parser never dispatched
    wake_request_handler.

    Post-fix observable (asserted): both MAINs latch all three amp-enable
    pins HIGH (LATB.bit4 = asm:4098, LATA.bit6 = asm:4112, LATB.bit3 =
    asm:4115) within bounded sim time.  The CONTROL-side WAITING-stick
    (CONTROL fails to recognize the woken MAINs as connected) is a
    SEPARATE issue per V32_MAIN_HANG_HARDENING_PLAN §3b CONTROL-side
    reconnect fragility -- intentionally NOT asserted here.

    Stays rust-only: the gpsim multi-MAIN harness has documented
    flakiness in this exact path.
    """
    if dlcp_sim_backend == "gpsim":
        pytest.skip("rust-only: gpsim multi-MAIN harness is documented-flaky on STBY/WAKE")
    if not _RUST_OK:
        pytest.fail(f"rust facade not importable: {_RUST_ERR!r}")

    c = RustChain.from_v171_v32()
    n = c.run_until_connected(limit=300)
    assert n < 300, f"chain did not boot to Volume display within 300 chunks; lcd={c.lcd_lines()!r}"
    assert "Volume:" in c.lcd_lines()[0], f"boot lcd unexpected: {c.lcd_lines()!r}"

    c.press("STBY")
    c.step_many(80)
    assert "ZZZ" in c.lcd_lines()[0].upper(), f"STBY press did not enter Zzz: {c.lcd_lines()!r}"
    # Both MAINs should be in standby (diag_s incremented).
    for unit in (0, 1):
        ds = c.read_main_reg(unit, 0x2E7)
        assert ds >= 1, f"MAIN{unit}.diag_s should be >=1 after STBY broadcast; got {ds}"

    c.press("STBY")  # WAKE

    # Step until both MAINs raise all three amp-enable latches OR budget
    # expires.  Per the H2 fix, this should converge within a few hundred
    # chunks (boot-gate ~500ms + post-gate timer settles + i2c work).
    for _ in range(20):
        c.step_many(100)
        m0_ok = (
            (c.read_main_reg(0, 0xF8A) & 0x18) == 0x18
            and (c.read_main_reg(0, 0xF89) & 0x40) == 0x40
            and c.read_main_reg(0, 0x2E8) >= 1
        )
        m1_ok = (
            (c.read_main_reg(1, 0xF8A) & 0x18) == 0x18
            and (c.read_main_reg(1, 0xF89) & 0x40) == 0x40
            and c.read_main_reg(1, 0x2E8) >= 1
        )
        if m0_ok and m1_ok:
            break

    for unit, label in ((0, "MAIN0"), (1, "MAIN1")):
        latb = c.read_main_reg(unit, 0xF8A)
        lata = c.read_main_reg(unit, 0xF89)
        db = c.read_main_reg(unit, 0x2E8)
        assert (latb & 0x18) == 0x18, (
            f"{label}: LATB.bit3+bit4 must both be HIGH (post-gate amp-enable); "
            f"got latB=0x{latb:02X}.  Pre-H2-fix this was the asymmetric-wake "
            f"failure mode for MAIN1."
        )
        assert (lata & 0x40) == 0x40, (
            f"{label}: LATA.bit6 must be HIGH (pre-DSP-coeff amp-enable); "
            f"got latA=0x{lata:02X}"
        )
        assert db >= 1, (
            f"{label}: diag_b must be >=1 after WAKE (standby_event_dispatch "
            f"bring-up branch); got {db}"
        )


def test_v32_source_oerr_recover_uses_full_fifo_drain() -> None:
    """V3.2 OERR recovery must use the full FIFO-drain helper.  This was
    the ISR-side check originally bundled into
    `test_v32_source_hardens_wake_uart_path` but split out when the
    Bug #45 H2 source-contract + dynamic regression tests were added."""
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    isr_start = text.find("uart_oerr_recover:")
    isr_end = text.find("flow_main_isr_dispatch_3b8c:", isr_start)
    assert isr_start != -1 and isr_end > isr_start, "uart_oerr_recover body not found"
    isr_body = text[isr_start:isr_end]
    assert "call        uart_soft_recover_full, 0x0" in isr_body, (
        "MAIN OERR path must use the full FIFO-drain soft recover helper"
    )


def test_v171_v32_standby_wake_pair_contracts_line_up() -> None:
    main_text = V32_MAIN_ASM.read_text(encoding="utf-8")
    control_text = V171_CONTROL_ASM.read_text(encoding="utf-8")

    cmd04_start = main_text.find("cmd04_status_response:")
    cmd04_end = main_text.find("cmd06_input_select_handler", cmd04_start)
    assert cmd04_start >= 0 and cmd04_end > cmd04_start, "MAIN cmd04_status_response body not found"
    cmd04_body = main_text[cmd04_start:cmd04_end]
    assert "call        send_status_burst, 0x0" in cmd04_body, (
        "V3.2 must answer CONTROL cmd 0x04 polls with the sentinel-clearing burst"
    )

    cold_wait_start = control_text.find("flow_ccs_0FA0_118C:")
    cold_wait_end = control_text.find("post_connect_init", cold_wait_start)
    assert cold_wait_start >= 0 and cold_wait_end > cold_wait_start, "CONTROL cold WAITING loop not found"
    cold_wait_body = control_text[cold_wait_start:cold_wait_end]
    assert "call    rx_parser_entry, 0x0" in cold_wait_body
    # Post-838cebf: BSR reset after `rx_parser_entry` is provided by the
    # new parser-stall watchdog call `v171_service_rx_frame_gap`
    # (first instruction is `movlb 0x00`).  Asserting its presence
    # covers both the liveness hardening and the BSR contract.
    assert "call    v171_service_rx_frame_gap, 0x0" in cold_wait_body, (
        "cold WAITING loop must call v171_service_rx_frame_gap after "
        "rx_parser_entry (parser stall watchdog + BSR reset)"
    )

    standby_start = control_text.find("flow_display_state_entry_126E:")
    standby_end = control_text.find("reconnect_wait_loop:", standby_start)
    assert standby_start >= 0 and standby_end > standby_start, "CONTROL standby-exit path not found"
    standby_body = control_text[standby_start:standby_end]
    for token in (
        "bsf     control_flags, 0x1, A",
        "call    standby_wake_broadcast, 0x0",
        "lcd_str_waiting_for_dlcp_alt",
        "bcf     control_flags, 0x1, A",
    ):
        assert token in standby_body, f"CONTROL standby-exit path missing {token!r}"
    assert standby_body.index("bsf     control_flags, 0x1, A") < standby_body.index(
        "call    standby_wake_broadcast, 0x0"
    ), "CONTROL must broadcast wake before entering reconnect WAITING"

    reconnect_start = control_text.find("reconnect_wait_loop:")
    reconnect_end = control_text.find("control_core_service_12D0:", reconnect_start)
    assert reconnect_start >= 0 and reconnect_end > reconnect_start, "CONTROL reconnect loop body not found"
    reconnect_body = control_text[reconnect_start:reconnect_end]
    for token in (
        "subwf   input_select_cache, W, B",
        "subwf   volume_cache, W, B",
        "subwf   cmd1d_setting_cache, W, B",
        "subwf   raw_status_cache, W, B",
        # Post-838cebf: the reconnect WAITING loop uses
        # `v171_service_rx_frame_gap` after `rx_parser_entry` both for
        # parser-stall watchdog and as the BSR=0 reset the BANKED
        # sentinel compares depend on (helper entry = `movlb 0x00`).
        "call    v171_service_rx_frame_gap, 0x0",
        "v171_reconnect_wait_done:",
        "call    standby_wake_broadcast, 0x0",
    ):
        assert token in reconnect_body, f"CONTROL reconnect path missing {token!r}"
