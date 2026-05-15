from __future__ import annotations

import json

import pytest

from dlcp_fw.cli import sim_v32_fault_injection_sweep as sweep
from dlcp_fw.sim.dlcp_sim_native import Chain


def test_v32_fault_sweep_definitions_cover_requested_injections() -> None:
    requested = {
        item.requested_injection for item in sweep.SCENARIOS.values()
    }
    assert requested == {
        "permanent MSSP SEN stuck",
        "permanent MSSP PEN stuck",
        "SDA held low",
        "SCL held low",
        "power-rail/BOR events",
        "USB host polling while MAIN is stuck inside a firmware wait",
        "high-rate UART bursts during the wake GIE=0 window",
    }
    assert all(item.label.startswith("V32-SIM-INJECT-") for item in sweep.SCENARIOS.values())


def test_v32_fault_sweep_native_hooks_are_available() -> None:
    chain = Chain.from_v32_main_only()
    chain.set_mssp_start_fault(cycles=1, count=1)
    chain.clear_mssp_start_faults()
    chain.set_mssp_clock_stretch(cycles=1, count=1)
    chain.clear_mssp_clock_stretch()
    chain.set_mssp_line_hold(scl_low=True, sda_low=False)
    chain.clear_mssp_line_holds()
    chain.apply_main_reset(0, "bor")
    chain.apply_reset_all("bor")
    accepted, dropped = chain.inject_main_uart_rx_bytes(0, [0xB0])
    assert accepted + dropped == 1


@pytest.mark.slow
def test_v32_fault_sweep_smoke_executes_every_requested_injection() -> None:
    cfg = sweep.SweepConfig(
        chunk_tcy=200_000,
        sweep_chunks=(2,),
        mssp_stuck_cycles=1_000_000_000,
        uart_burst_frames=2,
        usb_polls=1,
    )
    report = sweep.build_report(cfg=cfg, scenario_names=list(sweep.SCENARIOS))
    assert report["schema"] == 1
    results = {
        item["scenario_id"]: item
        for item in report["results"]
    }
    assert set(results) == set(sweep.SCENARIOS)

    for scenario_id in (
        "mssp_sen_stuck",
        "mssp_pen_stuck",
        "scl_held_low",
        "sda_held_low",
    ):
        result = results[scenario_id]
        assert result["verdict"] == "partial_progress_or_bounded_retry"
        assert result["observations"]["followup_consumed"] is True
        assert result["observations"]["stuck_with_rx_backlog"] is False

    bor = results["power_rail_bor"]
    assert bor["verdict"] == "bor_reboot_reconnect_ok"
    assert bor["observations"]["rcon_bor_bit_cleared"] is True
    assert bor["observations"]["diag_reset_bor_flag"] == 1
    assert bor["observations"]["control_reconnected"] is True
    assert bor["observations"]["lcd_volume_after_reconnect"] is True

    usb = results["usb_poll_while_wait"]
    assert usb["verdict"] == "firmware_hid_polls_ok_while_main_wait_stuck"
    assert usb["observations"]["all_usb_polls_status_ok"] is True
    assert usb["observations"]["main_wait_still_forced"] is True
    assert usb["model_limitations"], "USB dispatcher-boundary limitation must be explicit"

    uart = results["uart_burst_wake_gie0"]
    assert uart["burst"]["dropped"] > 0
    assert uart["pc_alignment"]["adc_boot_gate_hit"] is True
    assert uart["model_limitations"], "wake-window trigger limitation must be explicit"


def test_v32_fault_sweep_cli_writes_json_and_markdown(tmp_path) -> None:
    out_json = tmp_path / "sweep.json"
    out_md = tmp_path / "sweep.md"
    rc = sweep.main([
        "--scenario",
        "mssp_sen_stuck",
        "--sweep-chunks",
        "2",
        "--report-json",
        str(out_json),
        "--report-md",
        str(out_md),
    ])
    assert rc == 0
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["kind"] == "v32_sim_fault_injection_sweep"
    assert data["results"][0]["label"] == "V32-SIM-INJECT-MSSP-SEN-STUCK"
    assert "V3.2 Sim Fault-Injection Sweep" in out_md.read_text(encoding="utf-8")
