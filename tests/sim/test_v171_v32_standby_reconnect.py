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
* The cross-firmware standby/wake contract must stay intact:
  V3.2 answers cmd 0x04 with the sentinel-clearing burst, and V1.71
  sends wake both when leaving `Zzz...` and when reconnect completes.
  The slow gpsim pair harness still hangs intermittently in this path,
  so this file keeps the deterministic source-level integration gate.
"""

from __future__ import annotations

import pytest

from dlcp_fw.paths import V171_CONTROL_ASM, V32_MAIN_ASM


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
