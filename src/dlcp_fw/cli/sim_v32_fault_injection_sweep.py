"""Configurable V3.2 sim-only fault-injection sweep.

This is intentionally a labelled-stimulus harness, not a new firmware
release.  The stimuli are named so report artifacts can be tied back to
the requested injections without minting throwaway V3.2 hex names.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from dlcp_fw.flash.sim_backend import SimUsbHub, make_sim_hub
from dlcp_fw.paths import ARTIFACTS_DIR
from dlcp_fw.sim.dlcp_sim_native import Chain


TICKS_PER_SEC = 48_000_000

ACTIVE_FLAGS = 0x05E
EVENT_FLAGS = 0x07E
RX_RING_RD = 0x0C6
RX_RING_WR = 0x0C7
PRESET_JOB_STATE = 0x2DE
PRESET_JOB_TARGET = 0x2DF
PRESET_JOB_INDEX = 0x2E0
DIAG_STANDBY = 0x2E7
DIAG_WAKE = 0x2E8

MAIN0_CORE_IDX = 1
PC_ADC_BOOT_GATE_LO = 0x2900
PC_ADC_BOOT_GATE_HI = 0x2944
PC_UART_REENABLE_LO = 0x44DC
PC_UART_REENABLE_HI = 0x4514

SSPCON2 = 0xFC5
RCSTA = 0xFAB
RCON = 0xFD0
PORTB = 0xF81
LATB = 0xF8A
LATA = 0xF89
TRISB = 0xF93

FRAME_WAKE = [0xB0, 0x03, 0x01]
FRAME_PRESET_A = [0xB0, 0x20, 0x00]
FRAME_PRESET_B = [0xB0, 0x20, 0x01]
FRAME_VOL_DOWN = [0xB0, 0x07, 0x30]

DEFAULT_REPORT_JSON = (
    ARTIFACTS_DIR / "probes" / "v32_fault_injection_sweep" / "current.json"
)
DEFAULT_REPORT_MD = (
    ARTIFACTS_DIR / "probes" / "v32_fault_injection_sweep" / "current.md"
)


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    label: str
    requested_injection: str
    topology: str
    model: str


SCENARIOS: dict[str, ScenarioDefinition] = {
    "mssp_sen_stuck": ScenarioDefinition(
        scenario_id="mssp_sen_stuck",
        label="V32-SIM-INJECT-MSSP-SEN-STUCK",
        requested_injection="permanent MSSP SEN stuck",
        topology="V3.2 MAIN-only",
        model="rust MSSP START-fault hook with start_busy_count=-1",
    ),
    "mssp_pen_stuck": ScenarioDefinition(
        scenario_id="mssp_pen_stuck",
        label="V32-SIM-INJECT-MSSP-PEN-STUCK",
        requested_injection="permanent MSSP PEN stuck",
        topology="V3.2 MAIN-only",
        model="rust MSSP STOP-fault hook with stop_busy_count=-1",
    ),
    "scl_held_low": ScenarioDefinition(
        scenario_id="scl_held_low",
        label="V32-SIM-INJECT-I2C-SCL-LOW",
        requested_injection="SCL held low",
        topology="V3.2 MAIN-only",
        model="rust MSSP physical SCL-low hold plus RB1 low readback hold",
    ),
    "sda_held_low": ScenarioDefinition(
        scenario_id="sda_held_low",
        label="V32-SIM-INJECT-I2C-SDA-LOW",
        requested_injection="SDA held low",
        topology="V3.2 MAIN-only",
        model="rust MSSP physical SDA-low hold plus RB0 low readback hold",
    ),
    "power_rail_bor": ScenarioDefinition(
        scenario_id="power_rail_bor",
        label="V32-SIM-INJECT-POWER-RAIL-BOR",
        requested_injection="power-rail/BOR events",
        topology="V1.71 CONTROL + 2x V3.2 MAIN",
        model="AN0 rail sag, whole-chain BrownOut reboot, rail restore, firmware reconnect",
    ),
    "usb_poll_while_wait": ScenarioDefinition(
        scenario_id="usb_poll_while_wait",
        label="V32-SIM-INJECT-USB-POLL-WHILE-WAIT",
        requested_injection="USB host polling while MAIN is stuck inside a firmware wait",
        topology="V1.71 CONTROL + 2x V3.2 MAIN",
        model="MAIN0 forced into SEN wait while SimHidBackend polls cmd 0x43",
    ),
    "uart_burst_wake_gie0": ScenarioDefinition(
        scenario_id="uart_burst_wake_gie0",
        label="V32-SIM-INJECT-UART-BURST-WAKE-GIE0",
        requested_injection="high-rate UART bursts during the wake GIE=0 window",
        topology="V1.71 CONTROL + 2x V3.2 MAIN",
        model="native wake frame starts adc_boot_gate; PC-aligned raw MAIN0 EUSART burst follows",
    ),
}


@dataclass(frozen=True)
class SweepConfig:
    chunk_tcy: int
    sweep_chunks: tuple[int, ...]
    mssp_stuck_cycles: int
    uart_burst_frames: int
    usb_polls: int


def _parse_int(value: str) -> int:
    return int(value, 0)


def _parse_sweep_chunks(value: str) -> tuple[int, ...]:
    chunks = tuple(int(part.strip(), 0) for part in value.split(",") if part.strip())
    if not chunks:
        raise argparse.ArgumentTypeError("at least one sweep chunk count is required")
    if any(v <= 0 for v in chunks):
        raise argparse.ArgumentTypeError("sweep chunk counts must be positive")
    return chunks


def _rx_backlog(rd: int, wr: int) -> int:
    return (wr - rd) % 0xC0


def _boot_main_active(chunk_tcy: int) -> Chain:
    c = Chain.from_v32_main_only()
    c.step_tcy(20 * chunk_tcy)
    c.inject_main_frames_fifo([FRAME_WAKE], fifo_limit=47)
    c.step_tcy(60 * chunk_tcy)
    return c


def _main_snapshot(c: Chain, *, unit: int = 0, main_only: bool = True) -> dict[str, int]:
    read = c.read_reg if main_only else (lambda addr: c.read_main_reg(unit, addr))
    rd = read(RX_RING_RD) & 0xFF
    wr = read(RX_RING_WR) & 0xFF
    return {
        "active_flags": read(ACTIVE_FLAGS) & 0xFF,
        "event_flags": read(EVENT_FLAGS) & 0xFF,
        "preset_job_state": read(PRESET_JOB_STATE) & 0xFF,
        "preset_job_target": read(PRESET_JOB_TARGET) & 0xFF,
        "preset_job_index": read(PRESET_JOB_INDEX) & 0xFF,
        "rx_ring_rd": rd,
        "rx_ring_wr": wr,
        "rx_backlog": _rx_backlog(rd, wr),
        "sspcon2": read(SSPCON2) & 0xFF,
        "rcsta": read(RCSTA) & 0xFF,
        "rcon": read(RCON) & 0xFF,
        "portb": read(PORTB) & 0xFF,
        "latb": read(LATB) & 0xFF,
        "lata": read(LATA) & 0xFF,
        "trisb": read(TRISB) & 0xFF,
        "pc": c.current_main_pc() & 0x1F_FFFF,
    }


def _sampled(samples: list[dict[str, int]], chunks: int) -> list[dict[str, int]]:
    if not samples:
        return []
    keep = {0, len(samples) - 1, max(0, chunks // 2 - 1), max(0, chunks // 2)}
    return [sample for idx, sample in enumerate(samples) if idx in keep]


def _run_main_wait_scenario(
    definition: ScenarioDefinition,
    cfg: SweepConfig,
    chunks: int,
    arm: Callable[[Chain], None],
    per_chunk: Callable[[Chain], None] | None = None,
    model_limitations: list[str] | None = None,
) -> dict[str, object]:
    c = _boot_main_active(cfg.chunk_tcy)
    before = _main_snapshot(c)
    arm(c)
    c.inject_main_frames_fifo([FRAME_PRESET_B], fifo_limit=47)
    samples: list[dict[str, int]] = []
    followup_chunk = max(1, chunks // 2)
    followup_injected = False
    for idx in range(chunks):
        if idx == followup_chunk:
            c.inject_main_frames_fifo([FRAME_PRESET_A], fifo_limit=47)
            followup_injected = True
        if per_chunk is not None:
            per_chunk(c)
        c.step_tcy(cfg.chunk_tcy)
        if per_chunk is not None:
            per_chunk(c)
        snap = _main_snapshot(c)
        snap["chunk"] = idx + 1
        samples.append(snap)

    final = samples[-1]
    stuck = bool(final["rx_backlog"] and final["preset_job_target"] == 0x01)
    completed = final["preset_job_state"] == 0 and final["preset_job_index"] >= 0x60
    if stuck:
        verdict = "firmware_wait_stalled"
    elif completed:
        verdict = "completed_despite_injection"
    else:
        verdict = "partial_progress_or_bounded_retry"

    return {
        "scenario_id": definition.scenario_id,
        "label": definition.label,
        "requested_injection": definition.requested_injection,
        "topology": definition.topology,
        "model": definition.model,
        "sweep_chunks": chunks,
        "sim_seconds": round((chunks * cfg.chunk_tcy) / TICKS_PER_SEC, 6),
        "followup_preset_a_injected": followup_injected,
        "verdict": verdict,
        "before": before,
        "samples": _sampled(samples, chunks),
        "final": final,
        "observations": {
            "stuck_with_rx_backlog": stuck,
            "preset_job_completed": completed,
            "followup_consumed": final["rx_backlog"] == 0 or final["preset_job_target"] == 0x00,
        },
        "model_limitations": model_limitations or [],
    }


def run_mssp_sen_stuck(cfg: SweepConfig, chunks: int) -> dict[str, object]:
    definition = SCENARIOS["mssp_sen_stuck"]

    def arm(c: Chain) -> None:
        c.set_mssp_start_fault(cycles=cfg.mssp_stuck_cycles, count=-1)

    return _run_main_wait_scenario(definition, cfg, chunks, arm=arm)


def run_mssp_pen_stuck(cfg: SweepConfig, chunks: int) -> dict[str, object]:
    definition = SCENARIOS["mssp_pen_stuck"]

    def arm(c: Chain) -> None:
        c.set_mssp_stop_fault(
            stop_busy_cycles=cfg.mssp_stuck_cycles,
            stop_busy_count=-1,
        )

    return _run_main_wait_scenario(definition, cfg, chunks, arm=arm)


def run_scl_held_low(cfg: SweepConfig, chunks: int) -> dict[str, object]:
    definition = SCENARIOS["scl_held_low"]

    def arm(c: Chain) -> None:
        c.set_mssp_line_hold(scl_low=True, sda_low=False)
        c.set_main_pin(0, "B", 1, False)
        c.write_reg(PORTB, c.read_reg(PORTB) & ~0x02)

    def per_chunk(c: Chain) -> None:
        c.set_main_pin(0, "B", 1, False)
        c.write_reg(PORTB, c.read_reg(PORTB) & ~0x02)

    return _run_main_wait_scenario(definition, cfg, chunks, arm=arm, per_chunk=per_chunk)


def run_sda_held_low(cfg: SweepConfig, chunks: int) -> dict[str, object]:
    definition = SCENARIOS["sda_held_low"]

    def arm(c: Chain) -> None:
        c.set_mssp_line_hold(scl_low=False, sda_low=True)
        c.set_main_pin(0, "B", 0, False)
        c.write_reg(PORTB, c.read_reg(PORTB) & ~0x01)

    def per_chunk(c: Chain) -> None:
        c.set_main_pin(0, "B", 0, False)
        c.write_reg(PORTB, c.read_reg(PORTB) & ~0x01)

    return _run_main_wait_scenario(
        definition,
        cfg,
        chunks,
        arm=arm,
        per_chunk=per_chunk,
    )


def run_power_rail_bor(cfg: SweepConfig, chunks: int) -> dict[str, object]:
    definition = SCENARIOS["power_rail_bor"]
    c = Chain.from_v171_v32()
    boot_chunks = c.run_until_connected(limit=300)
    before = _main_snapshot(c, unit=0, main_only=False)
    before_lcd = c.lcd_lines()
    c.set_main_an0_sample(0, 0x0100)
    c.set_main_an0_sample(1, 0x0100)
    c.apply_reset_all("bor")
    samples: list[dict[str, int]] = []
    for idx in range(chunks):
        c.step_tcy(cfg.chunk_tcy)
        snap = _main_snapshot(c, unit=0, main_only=False)
        snap["chunk"] = idx + 1
        samples.append(snap)
    sag_final = samples[-1]
    c.set_main_an0_sample(0, 0x0300)
    c.set_main_an0_sample(1, 0x0300)
    c.step_tcy(min(cfg.chunk_tcy * 4, cfg.chunk_tcy * chunks))
    reconnect_chunks = c.run_until_connected(limit=300)
    c.step_ticks(5_000_000)
    restored = _main_snapshot(c, unit=0, main_only=False)
    restored_lcd = c.lcd_lines()
    control_reconnected = c.is_connected() and not c.is_waiting()
    bor_flag = c.read_main_reg(0, 0x2EE) & 0xFF
    rcon_bor_observed = any((sample["rcon"] & 0x01) == 0 for sample in samples)
    return {
        "scenario_id": definition.scenario_id,
        "label": definition.label,
        "requested_injection": definition.requested_injection,
        "topology": definition.topology,
        "model": definition.model,
        "sweep_chunks": chunks,
        "sim_seconds": round((chunks * cfg.chunk_tcy) / TICKS_PER_SEC, 6),
        "verdict": "bor_reboot_reconnect_ok" if rcon_bor_observed and control_reconnected and bor_flag == 1 else "bor_reboot_reconnect_failed",
        "boot_chunks_to_volume": boot_chunks,
        "reconnect_chunks_to_volume": reconnect_chunks,
        "before": before,
        "before_lcd": before_lcd,
        "samples": _sampled(samples, chunks),
        "final": sag_final,
        "after_rail_restore": restored,
        "after_rail_restore_lcd": restored_lcd,
        "observations": {
            "rcon_bor_bit_cleared": rcon_bor_observed,
            "diag_reset_bor_flag": bor_flag,
            "control_reconnected": control_reconnected,
            "lcd_volume_after_reconnect": "Volume:" in restored_lcd[0],
            "rail_sag_an0": 0x0100,
            "rail_restore_an0": 0x0300,
        },
        "model_limitations": [
            "The analog threshold crossing is represented by a BrownOut reset "
            "event at the sag boundary; after that, the full CONTROL+dual-MAIN "
            "firmware reboot and reconnect ceremony runs in the chain."
        ],
    }


def _hid_cmd43_eeprom(dev, addr: int, length: int) -> bytes:  # type: ignore[no-untyped-def]
    payload = bytearray(64)
    payload[0] = 0x43
    payload[1] = 0x01
    payload[2] = addr & 0xFF
    payload[3] = (addr >> 8) & 0xFF
    payload[4] = length & 0xFF
    written = dev.write(bytes([0x00]) + bytes(payload))
    if written != 65:
        raise RuntimeError(f"HID write returned {written}, expected 65")
    resp = bytes(dev.read(64, 100))
    return resp


def run_usb_poll_while_wait(cfg: SweepConfig, chunks: int) -> dict[str, object]:
    definition = SCENARIOS["usb_poll_while_wait"]
    c = Chain.from_v171_v32()
    boot_chunks = c.run_until_connected(limit=300)
    before = _main_snapshot(c, unit=0, main_only=False)
    hub = make_sim_hub(
        c,
        default_step_ticks_per_hid_op=0,
        default_step_ticks_per_ep0_op=0,
    )
    dev = hub.open_hid_path(hub.device_for_unit(0).path)
    c.write_main_reg(0, SSPCON2, c.read_main_reg(0, SSPCON2) | 0x01)
    c.inject_main_frames_fifo([FRAME_PRESET_B], fifo_limit=47)

    responses: list[dict[str, int]] = []
    samples: list[dict[str, int]] = []
    for idx in range(max(chunks, cfg.usb_polls)):
        c.write_main_reg(0, SSPCON2, c.read_main_reg(0, SSPCON2) | 0x01)
        if idx < cfg.usb_polls:
            resp = _hid_cmd43_eeprom(dev, 0x80, 3)
            responses.append({
                "poll": idx + 1,
                "cmd": resp[0] if resp else -1,
                "status": resp[1] if len(resp) > 1 else -1,
                "length": resp[2] if len(resp) > 2 else -1,
            })
        c.step_tcy(cfg.chunk_tcy)
        c.write_main_reg(0, SSPCON2, c.read_main_reg(0, SSPCON2) | 0x01)
        snap = _main_snapshot(c, unit=0, main_only=False)
        snap["chunk"] = idx + 1
        samples.append(snap)

    final = samples[-1]
    all_ok = bool(responses) and all(r["cmd"] == 0x43 and r["status"] == 0 for r in responses)
    wait_stuck = bool(final["sspcon2"] & 0x01)
    return {
        "scenario_id": definition.scenario_id,
        "label": definition.label,
        "requested_injection": definition.requested_injection,
        "topology": definition.topology,
        "model": definition.model,
        "sweep_chunks": chunks,
        "sim_seconds": round((chunks * cfg.chunk_tcy) / TICKS_PER_SEC, 6),
        "verdict": "firmware_hid_polls_ok_while_main_wait_stuck" if all_ok and wait_stuck else "unexpected_usb_or_wait_result",
        "boot_chunks_to_volume": boot_chunks,
        "before": before,
        "samples": _sampled(samples, chunks),
        "final": final,
        "usb_polls": responses,
        "observations": {
            "all_usb_polls_status_ok": all_ok,
            "main_wait_still_forced": wait_stuck,
        },
        "model_limitations": [
            "SimHidBackend now stages a configured EP1 report and executes the "
            "V3.2 firmware HID dispatcher; it still injects at the dispatcher "
            "boundary rather than modeling full USB SIE interrupt preemption "
            "while the application PC is pinned in the MSSP wait."
        ],
    }


def run_uart_burst_wake_gie0(cfg: SweepConfig, chunks: int) -> dict[str, object]:
    definition = SCENARIOS["uart_burst_wake_gie0"]
    c = Chain.from_v171_v32()
    boot_chunks = c.run_until_connected(limit=300)
    c.press("STBY")
    c.step_many(20)
    before = _main_snapshot(c, unit=0, main_only=False)
    c.set_main_an0_sample(0, 0x0100)
    c.set_main_an0_sample(1, 0x0100)
    native_wake_delivered, native_wake_overrun = c.inject_main_frames_fifo(
        [FRAME_WAKE],
        fifo_limit=47,
    )
    adc_gate_pc = c.step_until_pc_hit(
        MAIN0_CORE_IDX,
        PC_ADC_BOOT_GATE_LO,
        PC_ADC_BOOT_GATE_HI,
        cfg.chunk_tcy * 10,
    )
    adc_gate_hit = PC_ADC_BOOT_GATE_LO <= adc_gate_pc <= PC_ADC_BOOT_GATE_HI
    if not adc_gate_hit:
        for _ in range(4):
            c.step_tcy(cfg.chunk_tcy)
    pre_burst = _main_snapshot(c, unit=0, main_only=False)
    burst = bytes(FRAME_VOL_DOWN * cfg.uart_burst_frames)
    accepted, dropped = c.inject_main_uart_rx_bytes(0, burst)
    samples: list[dict[str, int]] = []
    for idx in range(chunks):
        c.step_tcy(cfg.chunk_tcy)
        snap = _main_snapshot(c, unit=0, main_only=False)
        snap["chunk"] = idx + 1
        samples.append(snap)
    c.set_main_an0_sample(0, 0x0300)
    c.set_main_an0_sample(1, 0x0300)
    uart_reenable_pc = c.step_until_pc_hit(
        MAIN0_CORE_IDX,
        PC_UART_REENABLE_LO,
        PC_UART_REENABLE_HI,
        cfg.chunk_tcy * 50,
    )
    uart_reenable_hit = PC_UART_REENABLE_LO <= uart_reenable_pc <= PC_UART_REENABLE_HI
    c.step_many(20)
    after_restore = _main_snapshot(c, unit=0, main_only=False)
    return {
        "scenario_id": definition.scenario_id,
        "label": definition.label,
        "requested_injection": definition.requested_injection,
        "topology": definition.topology,
        "model": definition.model,
        "sweep_chunks": chunks,
        "sim_seconds": round((chunks * cfg.chunk_tcy) / TICKS_PER_SEC, 6),
        "verdict": "burst_dropped_while_uart_quiesced" if dropped > 0 and accepted == 0 else "burst_partly_accepted",
        "boot_chunks_to_volume": boot_chunks,
        "before": before,
        "native_wake": {
            "delivered": native_wake_delivered,
            "overrun": native_wake_overrun,
        },
        "pc_alignment": {
            "adc_boot_gate_range": [PC_ADC_BOOT_GATE_LO, PC_ADC_BOOT_GATE_HI],
            "adc_boot_gate_pc": adc_gate_pc,
            "adc_boot_gate_hit": adc_gate_hit,
            "uart_reenable_range": [PC_UART_REENABLE_LO, PC_UART_REENABLE_HI],
            "uart_reenable_pc": uart_reenable_pc,
            "uart_reenable_hit": uart_reenable_hit,
        },
        "pre_burst": pre_burst,
        "burst": {
            "frames": cfg.uart_burst_frames,
            "bytes": len(burst),
            "accepted": accepted,
            "dropped": dropped,
        },
        "samples": _sampled(samples, chunks),
        "final": samples[-1],
        "after_rail_restore": after_restore,
        "observations": {
            "adc_boot_gate_pc_hit": adc_gate_hit,
            "rcsta_at_burst": pre_burst["rcsta"],
            "uart_rx_enabled_at_burst": (pre_burst["rcsta"] & 0x90) == 0x90,
            "uart_reenable_pc_hit": uart_reenable_hit,
            "rcsta_after_restore": after_restore["rcsta"],
            "event_flags_final": samples[-1]["event_flags"],
            "main0_diag_wake_counter": c.read_main_reg(0, DIAG_WAKE) & 0xFF,
            "main0_diag_standby_counter": c.read_main_reg(0, DIAG_STANDBY) & 0xFF,
        },
        "model_limitations": [
            "The wake trigger is injected into V3.2's native RX ring; the burst "
            "is PC-aligned to adc_boot_gate and uses the silicon EUSART RX gate "
            "to record accepted vs dropped bytes."
        ],
    }


RUNNERS: dict[str, Callable[[SweepConfig, int], dict[str, object]]] = {
    "mssp_sen_stuck": run_mssp_sen_stuck,
    "mssp_pen_stuck": run_mssp_pen_stuck,
    "scl_held_low": run_scl_held_low,
    "sda_held_low": run_sda_held_low,
    "power_rail_bor": run_power_rail_bor,
    "usb_poll_while_wait": run_usb_poll_while_wait,
    "uart_burst_wake_gie0": run_uart_burst_wake_gie0,
}


def selected_scenarios(value: str) -> list[str]:
    if value.strip().lower() == "all":
        return list(SCENARIOS)
    names = [part.strip() for part in value.split(",") if part.strip()]
    unknown = sorted(set(names) - set(SCENARIOS))
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown scenario(s): {', '.join(unknown)}")
    return names


def build_report(
    *,
    cfg: SweepConfig,
    scenario_names: Sequence[str],
) -> dict[str, object]:
    started = time.time()
    results: list[dict[str, object]] = []
    for name in scenario_names:
        runner = RUNNERS[name]
        for chunks in cfg.sweep_chunks:
            results.append(runner(cfg, chunks))
    elapsed = time.time() - started
    return {
        "schema": 1,
        "kind": "v32_sim_fault_injection_sweep",
        "firmware_label": "DLCP_Firmware_V3.2 canonical release, labelled stimuli",
        "generated_at_epoch": started,
        "elapsed_wall_seconds": round(elapsed, 3),
        "config": {
            "chunk_tcy": cfg.chunk_tcy,
            "sweep_chunks": list(cfg.sweep_chunks),
            "mssp_stuck_cycles": cfg.mssp_stuck_cycles,
            "uart_burst_frames": cfg.uart_burst_frames,
            "usb_polls": cfg.usb_polls,
        },
        "scenario_definitions": {
            name: SCENARIOS[name].__dict__ for name in scenario_names
        },
        "results": results,
    }


def write_markdown_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    results = report["results"]
    assert isinstance(results, list)
    lines = [
        "# V3.2 Sim Fault-Injection Sweep",
        "",
        f"Firmware/stimulus label: `{report['firmware_label']}`",
        "",
        "| Scenario | Verdict | Key observation | Limitation |",
        "|---|---|---|---|",
    ]
    for item in results:
        assert isinstance(item, dict)
        obs = item.get("observations", {})
        if isinstance(obs, dict):
            key_obs = ", ".join(f"{k}={v}" for k, v in obs.items())
        else:
            key_obs = ""
        limitations = item.get("model_limitations", [])
        limitation = " ".join(str(v) for v in limitations) if isinstance(limitations, list) else ""
        lines.append(
            f"| `{item['label']}` ({item['sweep_chunks']} chunks) "
            f"| `{item['verdict']}` | {key_obs} | {limitation} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        default="all",
        type=selected_scenarios,
        help="comma-separated scenario IDs, or all",
    )
    parser.add_argument(
        "--sweep-chunks",
        default="8,24",
        type=_parse_sweep_chunks,
        help="comma-separated chunk counts to sweep; each chunk is --chunk-tcy",
    )
    parser.add_argument("--chunk-tcy", type=_parse_int, default=200_000)
    parser.add_argument("--mssp-stuck-cycles", type=_parse_int, default=1_000_000_000)
    parser.add_argument("--uart-burst-frames", type=_parse_int, default=20)
    parser.add_argument("--usb-polls", type=_parse_int, default=4)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD)
    parser.add_argument("--no-markdown", action="store_true")
    args = parser.parse_args(argv)

    cfg = SweepConfig(
        chunk_tcy=max(1, args.chunk_tcy),
        sweep_chunks=args.sweep_chunks,
        mssp_stuck_cycles=max(0, args.mssp_stuck_cycles),
        uart_burst_frames=max(1, args.uart_burst_frames),
        usb_polls=max(1, args.usb_polls),
    )
    report = build_report(cfg=cfg, scenario_names=args.scenario)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not args.no_markdown:
        write_markdown_report(report, args.report_md)
    print(f"wrote {args.report_json}")
    if not args.no_markdown:
        print(f"wrote {args.report_md}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
