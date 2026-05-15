#!/usr/bin/env python3
"""Long-running V1.71 + 2x V3.2 STBY/WAKE liveness soak in rust sim."""

from __future__ import annotations

import argparse
import contextlib
import io
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

import _bootstrap  # noqa: F401

from dlcp_fw.flash import dlcp_main_flash
from dlcp_fw.flash.sim_backend import SimUsbHub, install_sim_hub, make_sim_hub
from dlcp_fw.paths import V171_CONTROL_HEX, V32_MAIN_HEX
from dlcp_fw.sim.dlcp_sim_native import Chain


TICKS_PER_SEC = 48_000_000
MAIN_LATB = 0xF8A
MAIN_LATA = 0xF89
MAIN_ACTIVE_FLAGS = 0x05E
MAIN_RX_RING_RD = 0x0C6
MAIN_RX_RING_WR = 0x0C7
MAIN_DIAG_STANDBY = 0x2E7
MAIN_DIAG_WAKE = 0x2E8
MAIN_DIAG_I2C = 0x2E5
MAIN_DIAG_DSP = 0x2E6
MAIN_DIAG_RCV = 0x2E9
MAIN_DIAG_RESET_BOR = 0x2EE
SSPCON2 = 0xFC5
PORTB = 0xF81
STDBY_FRAME = (0xB0, 0x03, 0x00)
WAKE_FRAME = (0xB0, 0x03, 0x01)
PRESET_A_FRAME = (0xB0, 0x20, 0x00)
PRESET_B_FRAME = (0xB0, 0x20, 0x01)
VOL_DOWN_FRAME = (0xB0, 0x07, 0x30)
MAIN0_CORE_IDX = 1
PC_ADC_BOOT_GATE_LO = 0x2900
PC_ADC_BOOT_GATE_HI = 0x2944
MSSP_TRANSFER_MASK = 0x1F

DEFAULT_FAULTS = (
    "dsp_addr_nack",
    "mssp_sen_stuck",
    "mssp_pen_stuck",
    "scl_held_low",
    "sda_held_low",
    "usb_poll_while_wait",
    "power_rail_bor",
    "uart_burst_wake_gie0",
)


class SoakFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class MainHealth:
    unit: int
    latb: int
    lata: int
    active_flags: int
    diag_standby: int
    diag_wake: int


@dataclass
class FaultStats:
    total: int = 0
    counts: dict[str, int] = field(default_factory=dict)

    def bump(self, name: str) -> None:
        self.total += 1
        self.counts[name] = self.counts.get(name, 0) + 1

    def summary(self) -> str:
        if not self.counts:
            return "none"
        return ",".join(f"{name}:{self.counts[name]}" for name in sorted(self.counts))


@dataclass
class PeriodicBrownout:
    every_ticks: int = 0
    next_tick: int = 0
    injected: int = 0

    @classmethod
    def from_seconds(cls, seconds: float) -> "PeriodicBrownout":
        if seconds <= 0:
            return cls()
        every_ticks = max(1, int(seconds * TICKS_PER_SEC))
        return cls(every_ticks=every_ticks, next_tick=every_ticks)

    @property
    def enabled(self) -> bool:
        return self.every_ticks > 0

    def advance_past(self, elapsed_ticks: int) -> None:
        while self.next_tick <= elapsed_ticks:
            self.next_tick += self.every_ticks


@dataclass
class SimTimeline:
    chain: Chain
    last_tick: int
    elapsed_ticks: int = 0

    @classmethod
    def start(cls, chain: Chain) -> "SimTimeline":
        return cls(chain=chain, last_tick=chain.current_tick())

    def sync(self) -> int:
        now = self.chain.current_tick()
        if now >= self.last_tick:
            self.elapsed_ticks += now - self.last_tick
        else:
            # Whole-chain reset restarts the rust clock.  Callers sync before
            # reset injections, so adding the post-reset tick preserves a
            # monotonic elapsed-time lower bound for soak duration control.
            self.elapsed_ticks += now
        self.last_tick = now
        return self.elapsed_ticks

    def seconds(self) -> float:
        return self.sync() / TICKS_PER_SEC


def _parse_int(value: str) -> int:
    return int(value, 0)


def _parse_faults(value: str) -> tuple[str, ...]:
    raw = value.strip().lower()
    if not raw or raw == "none":
        return ()
    parts = tuple(part.strip() for part in raw.split(",") if part.strip())
    selected: list[str] = []
    for part in parts:
        if part == "all":
            selected.extend(DEFAULT_FAULTS)
        elif part in DEFAULT_FAULTS:
            selected.append(part)
        else:
            valid = ", ".join(("all", "none", *DEFAULT_FAULTS))
            raise argparse.ArgumentTypeError(
                f"unknown fault {part!r}; valid values: {valid}"
            )
    deduped: list[str] = []
    for part in selected:
        if part not in deduped:
            deduped.append(part)
    return tuple(deduped)


def _sim_seconds(chain: Chain, start_tick: int) -> float:
    now = chain.current_tick()
    delta = now - start_tick if now >= start_tick else now
    return delta / TICKS_PER_SEC


def _main_health(chain: Chain, unit: int) -> MainHealth:
    return MainHealth(
        unit=unit,
        latb=chain.read_main_reg(unit, MAIN_LATB) & 0xFF,
        lata=chain.read_main_reg(unit, MAIN_LATA) & 0xFF,
        active_flags=chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) & 0xFF,
        diag_standby=chain.read_main_reg(unit, MAIN_DIAG_STANDBY) & 0xFF,
        diag_wake=chain.read_main_reg(unit, MAIN_DIAG_WAKE) & 0xFF,
    )


def _counter_advanced_or_saturated(before: int, after: int) -> bool:
    return after > before or (before == 0x0F and after == 0x0F)


def _rx_backlog(rd: int, wr: int) -> int:
    return (wr - rd) % 0xC0


def _main_fault_snapshot(chain: Chain, unit: int = 0) -> dict[str, int]:
    rd = chain.read_main_reg(unit, MAIN_RX_RING_RD) & 0xFF
    wr = chain.read_main_reg(unit, MAIN_RX_RING_WR) & 0xFF
    return {
        "unit": unit,
        "active_flags": chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) & 0xFF,
        "diag_i": chain.read_main_reg(unit, MAIN_DIAG_I2C) & 0xFF,
        "diag_d": chain.read_main_reg(unit, MAIN_DIAG_DSP) & 0xFF,
        "diag_r": chain.read_main_reg(unit, MAIN_DIAG_RCV) & 0xFF,
        "diag_standby": chain.read_main_reg(unit, MAIN_DIAG_STANDBY) & 0xFF,
        "diag_wake": chain.read_main_reg(unit, MAIN_DIAG_WAKE) & 0xFF,
        "rx_ring_rd": rd,
        "rx_ring_wr": wr,
        "rx_backlog": _rx_backlog(rd, wr),
        "sspcon2": chain.read_main_reg(unit, SSPCON2) & 0xFF,
    }


def _fail(chain: Chain, start_tick: int, label: str, msg: str) -> None:
    health = [_main_health(chain, unit) for unit in (0, 1)]
    details = {
        "label": label,
        "message": msg,
        "tick": chain.current_tick(),
        "sim_seconds": _sim_seconds(chain, start_tick),
        "lcd": chain.lcd_lines(),
        "connected": chain.is_connected(),
        "waiting": chain.is_waiting(),
        "mains": [asdict(item) for item in health],
        "fault_snapshot": [_main_fault_snapshot(chain, unit) for unit in (0, 1)],
    }
    raise SoakFailure(details)


def _check_awake(chain: Chain, start_tick: int, label: str) -> None:
    problem = _awake_problem(chain)
    if problem is not None:
        _fail(chain, start_tick, label, problem)


def _awake_problem(chain: Chain) -> str | None:
    if not chain.is_connected() or chain.is_waiting():
        return "CONTROL is not connected/ready"
    line0, _ = chain.lcd_lines()
    if "Volume:" not in line0:
        return f"CONTROL LCD is not on Volume: {line0!r}"

    for unit in (0, 1):
        health = _main_health(chain, unit)
        if (health.latb & 0x18) != 0x18:
            return f"MAIN{unit} LATB amp latches are not high"
        if (health.lata & 0x40) != 0x40:
            return f"MAIN{unit} LATA amp latch is not high"
        if (health.active_flags & 0x08) == 0:
            return f"MAIN{unit} active gate is closed"
    return None


def _wait_awake(
    chain: Chain,
    start_tick: int,
    label: str,
    *,
    chunks: int,
) -> int:
    last_problem = "not checked"
    for idx in range(chunks + 1):
        last_problem = _awake_problem(chain) or ""
        if not last_problem:
            return idx
        chain.step_many(1)
    _fail(chain, start_tick, label, last_problem)
    raise AssertionError("unreachable")


def _check_standby(
    chain: Chain,
    start_tick: int,
    label: str,
    before: Sequence[MainHealth],
) -> None:
    line0, _ = chain.lcd_lines()
    if "ZZZ" not in line0.upper():
        _fail(chain, start_tick, label, f"CONTROL LCD did not enter standby: {line0!r}")
    for unit in (0, 1):
        health = _main_health(chain, unit)
        if not _counter_advanced_or_saturated(
            before[unit].diag_standby,
            health.diag_standby,
        ):
            _fail(chain, start_tick, label, f"MAIN{unit} standby counter did not advance")
        if (health.active_flags & 0x08) != 0:
            _fail(chain, start_tick, label, f"MAIN{unit} active gate is still open")


def _probe_usb_snapshots(
    chain: Chain,
    *,
    allow_warnings: bool,
) -> list[dict[str, object]]:
    hub = make_sim_hub(chain)
    out: list[dict[str, object]] = []
    with install_sim_hub(hub):
        infos = hub.enumerate_devices(SimUsbHub.DEFAULT_VID, SimUsbHub.DEFAULT_PID)
        if len(infos) != 2:
            raise SoakFailure({"message": f"expected 2 simulated MAIN HID devices, got {len(infos)}"})
        for info in infos:
            with contextlib.redirect_stdout(io.StringIO()):
                snap = dlcp_main_flash._probe_device_snapshot(
                    info=info,
                    vid=SimUsbHub.DEFAULT_VID,
                    pid=SimUsbHub.DEFAULT_PID,
                )
            if snap.mode != "app":
                raise SoakFailure({"message": f"{info.path!r} mode is {snap.mode!r}, expected app"})
            if snap.version is None or (snap.version.major, snap.version.minor) != (3, 2):
                raise SoakFailure({"message": f"{info.path!r} version probe failed: {snap.version!r}"})
            if snap.eeprom_version is None:
                raise SoakFailure({"message": f"{info.path!r} EEPROM identity probe failed"})
            if snap.warnings and not allow_warnings:
                raise SoakFailure({"message": f"{info.path!r} USB snapshot warnings: {snap.warnings!r}"})
            out.append(
                {
                    "path": info.path.decode("utf-8", errors="replace") if info.path else None,
                    "serial": info.serial_number,
                    "version": f"{snap.version.major}.{snap.version.minor}",
                    "revision": snap.eeprom_version.revision,
                    "config": snap.active_config_name,
                    "warnings": list(snap.warnings),
                }
            )
    return out


def _chunk_frames(raw: Sequence[int]) -> list[tuple[int, int, int]]:
    return [
        (raw[i] & 0xFF, raw[i + 1] & 0xFF, raw[i + 2] & 0xFF)
        for i in range(0, len(raw) - 2, 3)
    ]


def _fmt_frame(frame: tuple[int, int, int]) -> str:
    return f"{frame[0]:02X}/{frame[1]:02X}/{frame[2]:02X}"


def _summarize_bytes(raw: Sequence[int], expected: tuple[int, int, int]) -> dict[str, object]:
    frames = _chunk_frames(raw)
    return {
        "bytes": len(raw),
        "frames": len(frames),
        "expected": sum(1 for frame in frames if frame == expected),
        "tail": [_fmt_frame(frame) for frame in frames[-3:]],
    }


def _capture_mark_all(chain: Chain) -> None:
    chain.mark_ctl_tx_capture_point()
    chain.mark_tx_capture_point()
    chain.mark_main1_tx_capture_point()
    chain.mark_main0_rx_capture_point()
    chain.mark_main1_rx_capture_point()
    chain.mark_ctl_rx_capture_point()


def _capture_uart_summary(
    chain: Chain,
    expected: tuple[int, int, int],
) -> dict[str, dict[str, object]]:
    return {
        "ctl_tx": _summarize_bytes(chain.ctl_tx_record_since_last_capture(), expected),
        "main0_rx": _summarize_bytes(chain.main0_rx_record_since_last_capture(), expected),
        "main0_tx": _summarize_bytes(chain.tx_record_since_last_capture(), expected),
        "main1_rx": _summarize_bytes(chain.main1_rx_record_since_last_capture(), expected),
        "main1_tx": _summarize_bytes(chain.main1_tx_record_since_last_capture(), expected),
        "ctl_rx": _summarize_bytes(chain.ctl_rx_record_since_last_capture(), expected),
    }


def _format_uart_summary(summary: dict[str, dict[str, object]]) -> str:
    parts = []
    for name in ("ctl_tx", "main0_rx", "main0_tx", "main1_rx", "main1_tx", "ctl_rx"):
        item = summary[name]
        parts.append(
            f"{name}=b{item['bytes']}/f{item['frames']}/hit{item['expected']}"
        )
    return " ".join(parts)


def _assert_expected_seen(
    chain: Chain,
    start_tick: int,
    *,
    label: str,
    summary: dict[str, dict[str, object]],
    required_paths: Sequence[str],
) -> None:
    missing = [
        name for name in required_paths
        if int(summary[name]["expected"]) <= 0
    ]
    if missing:
        _fail(
            chain,
            start_tick,
            label,
            "expected UART frame missing on "
            + ", ".join(missing)
            + "; "
            + _format_uart_summary(summary),
        )


def _step_fault_window(chain: Chain, args: argparse.Namespace, maintain=None) -> None:
    for _ in range(args.fault_chunks):
        if maintain is not None:
            maintain(chain)
        chain.step_tcy(args.fault_chunk_tcy)
        if maintain is not None:
            maintain(chain)


def _clear_main0_i2c_faults(chain: Chain) -> None:
    chain.clear_i2c_faults()
    chain.clear_mssp_start_faults()
    chain.clear_mssp_stop_faults()
    chain.clear_mssp_clock_stretch()
    chain.clear_mssp_line_holds()
    chain.set_main_pin(0, "B", 0, True)
    chain.set_main_pin(0, "B", 1, True)
    chain.write_main_reg(0, PORTB, chain.read_main_reg(0, PORTB) | 0x03)
    chain.force_reset_main_mssp()


def _assert_main0_recovered(
    chain: Chain,
    start_tick: int,
    label: str,
    *,
    max_backlog: int = 0,
    mssp_quiesce_tcy: int,
    mssp_quiesce_step_tcy: int,
) -> None:
    snap, observed = _wait_main0_mssp_quiescent(
        chain,
        timeout_tcy=mssp_quiesce_tcy,
        step_tcy=mssp_quiesce_step_tcy,
    )
    if snap is None:
        last = _main_fault_snapshot(chain, 0)
        _fail(
            chain,
            start_tick,
            label,
            "MAIN0 MSSP control bits did not quiesce: "
            f"observed={[f'0x{value:02X}' for value in observed]} last={last!r}",
        )
    assert snap is not None
    if snap["rx_backlog"] > max_backlog:
        _fail(chain, start_tick, label, f"MAIN0 RX backlog after fault: {snap!r}")
    _check_awake(chain, start_tick, label)


def _wait_main0_mssp_quiescent(
    chain: Chain,
    *,
    timeout_tcy: int,
    step_tcy: int,
) -> tuple[dict[str, int] | None, list[int]]:
    if timeout_tcy < 0:
        raise ValueError("timeout_tcy must be >= 0")
    if step_tcy <= 0:
        raise ValueError("step_tcy must be > 0")

    elapsed = 0
    observed: list[int] = []
    while True:
        snap = _main_fault_snapshot(chain, 0)
        sspcon2 = int(snap["sspcon2"])
        observed.append(sspcon2)
        if (sspcon2 & MSSP_TRANSFER_MASK) == 0:
            return snap, observed
        if elapsed >= timeout_tcy:
            return None, observed
        step = min(step_tcy, timeout_tcy - elapsed)
        if step <= 0:
            return None, observed
        chain.step_tcy(step)
        elapsed += step


def _exercise_main0_i2c_fault(
    chain: Chain,
    start_tick: int,
    args: argparse.Namespace,
    *,
    name: str,
    cycle: int,
    arm,
    maintain=None,
) -> dict[str, object]:
    label = f"cycle {cycle} fault {name}"
    before = _main_fault_snapshot(chain, 0)
    target = PRESET_B_FRAME if cycle % 2 else PRESET_A_FRAME
    arm(chain)
    delivered = overrun = 0
    try:
        delivered, overrun = chain.inject_main_frames_fifo([target], fifo_limit=47)
        if delivered != 3 or overrun:
            _fail(
                chain,
                start_tick,
                label,
                f"failed to inject preset frame under fault: delivered={delivered} overrun={overrun}",
            )
        _step_fault_window(chain, args, maintain=maintain)
    finally:
        _clear_main0_i2c_faults(chain)
    chain.step_tcy(args.fault_recovery_tcy)
    after = _main_fault_snapshot(chain, 0)
    _assert_main0_recovered(
        chain,
        start_tick,
        label,
        mssp_quiesce_tcy=args.mssp_quiesce_tcy,
        mssp_quiesce_step_tcy=args.mssp_quiesce_step_tcy,
    )
    return {
        "name": name,
        "target": _fmt_frame(target),
        "delivered": delivered,
        "overrun": overrun,
        "before": before,
        "after": after,
    }


def _exercise_usb_poll_while_wait(
    chain: Chain,
    start_tick: int,
    args: argparse.Namespace,
    *,
    cycle: int,
) -> dict[str, object]:
    label = f"cycle {cycle} fault usb_poll_while_wait"
    before = _main_fault_snapshot(chain, 0)
    payload = bytearray(64)
    payload[0] = 0x43
    payload[1] = 0x01
    payload[2] = 0x80
    payload[3] = 0x00
    payload[4] = 0x03
    responses: list[dict[str, int]] = []
    try:
        for idx in range(args.usb_wait_polls):
            chain.write_main_reg(0, SSPCON2, chain.read_main_reg(0, SSPCON2) | 0x01)
            response, dispatch_hits = chain.firmware_hid_report(
                0,
                payload,
                max_steps=args.usb_hid_max_steps,
            )
            item = {
                "poll": idx + 1,
                "cmd": response[0] if response else -1,
                "status": response[1] if len(response) > 1 else -1,
                "length": response[2] if len(response) > 2 else -1,
                "dispatch_hits": dispatch_hits,
            }
            responses.append(item)
            if item["cmd"] != 0x43 or item["status"] != 0 or dispatch_hits <= 0:
                _fail(chain, start_tick, label, f"firmware HID poll failed: {item!r}")
            chain.step_tcy(args.fault_chunk_tcy)
    finally:
        _clear_main0_i2c_faults(chain)
    chain.step_tcy(args.fault_recovery_tcy)
    after = _main_fault_snapshot(chain, 0)
    _assert_main0_recovered(
        chain,
        start_tick,
        label,
        mssp_quiesce_tcy=args.mssp_quiesce_tcy,
        mssp_quiesce_step_tcy=args.mssp_quiesce_step_tcy,
    )
    return {"name": "usb_poll_while_wait", "before": before, "after": after, "responses": responses}


def _exercise_power_rail_bor(
    chain: Chain,
    start_tick: int,
    args: argparse.Namespace,
    *,
    cycle: int,
) -> dict[str, object]:
    label = f"cycle {cycle} fault power_rail_bor"
    before_lcd = chain.lcd_lines()
    before = [_main_fault_snapshot(chain, unit) for unit in (0, 1)]
    chain.set_main_an0_sample(0, args.rail_sag_an0)
    chain.set_main_an0_sample(1, args.rail_sag_an0)
    chain.apply_reset_all("bor")
    _step_fault_window(chain, args)
    chain.set_main_an0_sample(0, args.rail_restore_an0)
    chain.set_main_an0_sample(1, args.rail_restore_an0)
    reconnect_chunks = chain.run_until_connected(limit=args.bor_reconnect_limit)
    settle_chunks = _wait_awake(
        chain,
        start_tick,
        label,
        chunks=args.bor_awake_settle_chunks,
    )
    bor_flags = [
        chain.read_main_reg(unit, MAIN_DIAG_RESET_BOR) & 0xFF
        for unit in (0, 1)
    ]
    if bor_flags != [1, 1]:
        _fail(chain, start_tick, label, f"BOR diag flags did not latch: {bor_flags!r}")
    return {
        "name": "power_rail_bor",
        "before_lcd": before_lcd,
        "after_lcd": chain.lcd_lines(),
        "before": before,
        "after": [_main_fault_snapshot(chain, unit) for unit in (0, 1)],
        "bor_flags": bor_flags,
        "reconnect_chunks": reconnect_chunks,
        "settle_chunks": settle_chunks,
    }


def _exercise_uart_burst_wake_gie0(
    chain: Chain,
    start_tick: int,
    args: argparse.Namespace,
    *,
    cycle: int,
) -> dict[str, object]:
    label = f"cycle {cycle} fault uart_burst_wake_gie0"
    before_standby = [_main_health(chain, unit) for unit in (0, 1)]
    chain.press("STBY")
    chain.step_many(args.standby_entry_chunks)
    _check_standby(chain, start_tick, f"{label} standby precondition", before_standby)

    chain.set_main_an0_sample(0, args.rail_sag_an0)
    chain.set_main_an0_sample(1, args.rail_sag_an0)
    native_wake_delivered, native_wake_overrun = chain.inject_main_frames_fifo(
        [WAKE_FRAME],
        fifo_limit=47,
    )
    adc_gate_pc = chain.step_until_pc_hit(
        MAIN0_CORE_IDX,
        PC_ADC_BOOT_GATE_LO,
        PC_ADC_BOOT_GATE_HI,
        args.fault_chunk_tcy * 10,
    )
    burst = bytes(VOL_DOWN_FRAME * args.uart_burst_frames)
    accepted, dropped = chain.inject_main_uart_rx_bytes(0, burst)
    _step_fault_window(chain, args)
    chain.set_main_an0_sample(0, args.rail_restore_an0)
    chain.set_main_an0_sample(1, args.rail_restore_an0)

    # CONTROL is still logically on the standby screen because the native
    # wake above targeted MAIN0.  Use the real front-panel wake path to
    # restore the full product state before the outer soak loop continues.
    chain.press("STBY")
    chain.run_until_connected(limit=args.wake_limit)
    _check_awake(chain, start_tick, label)
    return {
        "name": "uart_burst_wake_gie0",
        "native_wake": {
            "delivered": native_wake_delivered,
            "overrun": native_wake_overrun,
        },
        "adc_gate_pc": adc_gate_pc,
        "adc_gate_hit": PC_ADC_BOOT_GATE_LO <= adc_gate_pc <= PC_ADC_BOOT_GATE_HI,
        "burst": {
            "frames": args.uart_burst_frames,
            "accepted": accepted,
            "dropped": dropped,
        },
        "after": [_main_fault_snapshot(chain, unit) for unit in (0, 1)],
    }


def _exercise_fault(
    chain: Chain,
    start_tick: int,
    args: argparse.Namespace,
    *,
    cycle: int,
    name: str,
) -> dict[str, object]:
    if name == "dsp_addr_nack":
        return _exercise_main0_i2c_fault(
            chain,
            start_tick,
            args,
            name=name,
            cycle=cycle,
            arm=lambda c: c.set_i2c_fault("dsp34", address_nack_count=args.dsp_nack_count),
        )
    if name == "mssp_sen_stuck":
        return _exercise_main0_i2c_fault(
            chain,
            start_tick,
            args,
            name=name,
            cycle=cycle,
            arm=lambda c: c.set_mssp_start_fault(cycles=args.mssp_stuck_cycles, count=1),
        )
    if name == "mssp_pen_stuck":
        return _exercise_main0_i2c_fault(
            chain,
            start_tick,
            args,
            name=name,
            cycle=cycle,
            arm=lambda c: c.set_mssp_stop_fault(
                stop_busy_cycles=args.mssp_stuck_cycles,
                stop_busy_count=1,
            ),
        )
    if name == "scl_held_low":
        return _exercise_main0_i2c_fault(
            chain,
            start_tick,
            args,
            name=name,
            cycle=cycle,
            arm=lambda c: (
                c.set_mssp_line_hold(scl_low=True, sda_low=False),
                c.set_main_pin(0, "B", 1, False),
                c.write_main_reg(0, PORTB, c.read_main_reg(0, PORTB) & ~0x02),
            ),
            maintain=lambda c: (
                c.set_main_pin(0, "B", 1, False),
                c.write_main_reg(0, PORTB, c.read_main_reg(0, PORTB) & ~0x02),
            ),
        )
    if name == "sda_held_low":
        return _exercise_main0_i2c_fault(
            chain,
            start_tick,
            args,
            name=name,
            cycle=cycle,
            arm=lambda c: (
                c.set_mssp_line_hold(scl_low=False, sda_low=True),
                c.set_main_pin(0, "B", 0, False),
                c.write_main_reg(0, PORTB, c.read_main_reg(0, PORTB) & ~0x01),
            ),
            maintain=lambda c: (
                c.set_main_pin(0, "B", 0, False),
                c.write_main_reg(0, PORTB, c.read_main_reg(0, PORTB) & ~0x01),
            ),
        )
    if name == "usb_poll_while_wait":
        return _exercise_usb_poll_while_wait(chain, start_tick, args, cycle=cycle)
    if name == "power_rail_bor":
        return _exercise_power_rail_bor(chain, start_tick, args, cycle=cycle)
    if name == "uart_burst_wake_gie0":
        return _exercise_uart_burst_wake_gie0(chain, start_tick, args, cycle=cycle)
    raise AssertionError(f"unhandled fault name: {name}")


def _format_fault_result(result: dict[str, object]) -> str:
    name = str(result["name"])
    if name == "uart_burst_wake_gie0":
        burst = result.get("burst", {})
        return f"{name} burst={burst}"
    if name == "usb_poll_while_wait":
        return f"{name} polls={len(result.get('responses', []))}"
    if name == "power_rail_bor":
        return f"{name} reconnect_chunks={result.get('reconnect_chunks')}"
    after = result.get("after", {})
    if isinstance(after, dict):
        return (
            f"{name} diag_i={after.get('diag_i')} diag_d={after.get('diag_d')} "
            f"diag_r={after.get('diag_r')}"
        )
    return name


def _step_awake_idle_with_periodic_brownouts(
    chain: Chain,
    timeline: SimTimeline,
    start_tick: int,
    args: argparse.Namespace,
    *,
    idle_ticks: int,
    brownout: PeriodicBrownout,
    fault_stats: FaultStats,
    cycle: int,
) -> None:
    """Step an awake idle window, injecting BOR at simulated-time cadence.

    Brownouts are intentionally injected only during awake idle windows.  A BOR
    during the explicit standby dwell would turn the device back on underneath
    the STBY/WAKE cycle contract and make the next panel STBY press ambiguous.
    """
    end_tick = timeline.sync() + idle_ticks
    while timeline.sync() < end_tick:
        now = timeline.sync()
        if not brownout.enabled or brownout.next_tick > end_tick:
            chain.step_ticks(end_tick - now)
            timeline.sync()
            return

        if brownout.next_tick > now:
            chain.step_ticks(brownout.next_tick - now)
            timeline.sync()

        result = _exercise_power_rail_bor(
            chain,
            start_tick,
            args,
            cycle=cycle,
        )
        timeline.sync()
        brownout.injected += 1
        fault_stats.bump("power_rail_bor")
        if args.fault_log_every and fault_stats.total % args.fault_log_every == 0:
            print(
                f"cycle={cycle} INJECT_OK periodic_brownout "
                f"{_format_fault_result(result)}",
                flush=True,
            )
        brownout.advance_past(timeline.sync())


def run(args: argparse.Namespace) -> int:
    if args.seconds <= 0:
        raise SystemExit("--seconds must be > 0")
    if args.idle_min_s < 0 or args.idle_max_s < args.idle_min_s:
        raise SystemExit("--idle-max-s must be >= --idle-min-s >= 0")
    if args.dwell_min_s < 0 or args.dwell_max_s < args.dwell_min_s:
        raise SystemExit("--dwell-max-s must be >= --dwell-min-s >= 0")
    if args.fault_every_cycles < 0:
        raise SystemExit("--fault-every-cycles must be >= 0")
    if args.fault_chunks <= 0:
        raise SystemExit("--fault-chunks must be > 0")
    if args.fault_chunk_tcy <= 0 or args.fault_recovery_tcy < 0:
        raise SystemExit("--fault-chunk-tcy must be > 0 and --fault-recovery-tcy must be >= 0")
    if args.mssp_quiesce_tcy < 0 or args.mssp_quiesce_step_tcy <= 0:
        raise SystemExit("--mssp-quiesce-tcy must be >= 0 and --mssp-quiesce-step-tcy must be > 0")
    if args.brownout_every_s < 0:
        raise SystemExit("--brownout-every-s must be >= 0")

    rng = random.Random(args.seed)
    chain = Chain.from_v171_v32(
        control_hex_path=str(args.control_hex),
        main_hex_path=str(args.main_hex),
    )
    chain.run_until_connected(limit=args.boot_limit)

    start_tick = chain.current_tick()
    timeline = SimTimeline.start(chain)
    total_ticks = int(args.seconds * TICKS_PER_SEC)
    wall_start = time.monotonic()
    cycle = 0
    fault_stats = FaultStats()
    brownout = PeriodicBrownout.from_seconds(args.brownout_every_s)

    _check_awake(chain, start_tick, "boot")
    if args.usb_probe_every:
        _probe_usb_snapshots(chain, allow_warnings=args.allow_usb_warnings)

    print(
        "start "
        f"seconds={args.seconds:g} seed=0x{args.seed:X} "
        f"idle=[{args.idle_min_s:g},{args.idle_max_s:g}] "
        f"dwell=[{args.dwell_min_s:g},{args.dwell_max_s:g}] "
        f"faults={','.join(args.faults) if args.faults else 'none'} "
        f"fault_every={args.fault_every_cycles} "
        f"brownout_every={args.brownout_every_s:g}s "
        f"lcd={chain.lcd_lines()!r}",
        flush=True,
    )

    try:
        while timeline.sync() < total_ticks:
            idle_s = rng.randint(int(args.idle_min_s), int(args.idle_max_s))
            dwell_s = rng.randint(int(args.dwell_min_s), int(args.dwell_max_s))
            remaining = total_ticks - timeline.sync()
            idle_ticks = idle_s * TICKS_PER_SEC
            if idle_ticks >= remaining:
                _step_awake_idle_with_periodic_brownouts(
                    chain,
                    timeline,
                    start_tick,
                    args,
                    idle_ticks=remaining,
                    brownout=brownout,
                    fault_stats=fault_stats,
                    cycle=cycle,
                )
                timeline.sync()
                break

            cycle += 1
            _step_awake_idle_with_periodic_brownouts(
                chain,
                timeline,
                start_tick,
                args,
                idle_ticks=idle_ticks,
                brownout=brownout,
                fault_stats=fault_stats,
                cycle=cycle,
            )
            timeline.sync()
            _check_awake(chain, start_tick, f"cycle {cycle} before standby")
            before_standby = [_main_health(chain, unit) for unit in (0, 1)]

            _capture_mark_all(chain)
            chain.press("STBY")
            chain.step_many(args.standby_entry_chunks)
            timeline.sync()
            standby_uart = _capture_uart_summary(chain, STDBY_FRAME)
            _check_standby(chain, start_tick, f"cycle {cycle} standby", before_standby)
            _assert_expected_seen(
                chain,
                start_tick,
                label=f"cycle {cycle} standby UART",
                summary=standby_uart,
                required_paths=("ctl_tx", "main0_rx", "main0_tx", "main1_rx"),
            )
            if args.uart_log_every and cycle % args.uart_log_every == 0:
                print(
                    f"cycle={cycle} STDBY uart {_format_uart_summary(standby_uart)}",
                    flush=True,
                )

            chain.step_ticks(dwell_s * TICKS_PER_SEC)
            timeline.sync()

            _capture_mark_all(chain)
            chain.press("STBY")
            chain.run_until_connected(limit=args.wake_limit)
            timeline.sync()
            wake_uart = _capture_uart_summary(chain, WAKE_FRAME)
            _check_awake(chain, start_tick, f"cycle {cycle} after wake")
            _assert_expected_seen(
                chain,
                start_tick,
                label=f"cycle {cycle} wake UART",
                summary=wake_uart,
                required_paths=("ctl_tx", "main0_rx", "main0_tx", "main1_rx"),
            )
            if args.uart_log_every and cycle % args.uart_log_every == 0:
                print(
                    f"cycle={cycle} WAKE  uart {_format_uart_summary(wake_uart)}",
                    flush=True,
                )
            if args.usb_probe_every and cycle % args.usb_probe_every == 0:
                _probe_usb_snapshots(chain, allow_warnings=args.allow_usb_warnings)

            if (
                args.faults
                and args.fault_every_cycles
                and cycle % args.fault_every_cycles == 0
            ):
                timeline.sync()
                fault_index = (cycle // args.fault_every_cycles - 1) % len(args.faults)
                fault_name = args.faults[fault_index]
                result = _exercise_fault(
                    chain,
                    start_tick,
                    args,
                    cycle=cycle,
                    name=fault_name,
                )
                timeline.sync()
                fault_stats.bump(fault_name)
                if args.fault_log_every and fault_stats.total % args.fault_log_every == 0:
                    print(
                        f"cycle={cycle} INJECT_OK {_format_fault_result(result)}",
                        flush=True,
                    )

            if args.progress_every and cycle % args.progress_every == 0:
                wall_s = time.monotonic() - wall_start
                sim_s = timeline.seconds()
                print(
                    f"cycle={cycle} sim_s={sim_s:.1f} wall_s={wall_s:.1f} "
                    f"speedup={sim_s / wall_s:.1f}x faults={fault_stats.summary()} "
                    f"lcd={chain.lcd_lines()!r}",
                    flush=True,
                )
    except SoakFailure as exc:
        print(f"FAIL {exc}", flush=True)
        return 1

    wall_s = time.monotonic() - wall_start
    sim_s = timeline.seconds()
    print(
        f"PASS cycles={cycle} sim_s={sim_s:.1f} wall_s={wall_s:.1f} "
        f"speedup={sim_s / wall_s:.1f}x faults={fault_stats.summary()} "
        f"lcd={chain.lcd_lines()!r}",
        flush=True,
    )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Simulate V1.71 CONTROL + two V3.2 MAINs left running, with "
            "random STBY/WAKE cycles over a requested simulated duration."
        )
    )
    parser.add_argument(
        "--seconds",
        type=float,
        required=True,
        help="simulated duration to run, in seconds; 86400 = 24 hours",
    )
    parser.add_argument("--seed", type=_parse_int, default=0x17132)
    parser.add_argument("--idle-min-s", type=float, default=60.0)
    parser.add_argument("--idle-max-s", type=float, default=600.0)
    parser.add_argument("--dwell-min-s", type=float, default=1.0)
    parser.add_argument("--dwell-max-s", type=float, default=60.0)
    parser.add_argument("--boot-limit", type=int, default=400)
    parser.add_argument("--wake-limit", type=int, default=300)
    parser.add_argument("--standby-entry-chunks", type=int, default=80)
    parser.add_argument(
        "--usb-probe-every",
        type=int,
        default=1,
        help="probe both simulated MAINs through the HID/EP0 snapshot path every N cycles; 0 disables",
    )
    parser.add_argument("--allow-usb-warnings", action="store_true")
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument(
        "--uart-log-every",
        type=int,
        default=1,
        help="print UART summary every N cycles; 0 disables summary logging",
    )
    parser.add_argument(
        "--faults",
        type=_parse_faults,
        default=DEFAULT_FAULTS,
        metavar="LIST",
        help=(
            "recoverable fault exercises to interleave with the soak; "
            "comma-separated IDs, all, or none. Default: all. IDs: "
            + ",".join(DEFAULT_FAULTS)
        ),
    )
    parser.add_argument(
        "--no-faults",
        dest="faults",
        action="store_const",
        const=(),
        help="disable interleaved fault exercises",
    )
    parser.add_argument(
        "--fault-every-cycles",
        type=int,
        default=1,
        help="inject one selected fault every N STBY/WAKE cycles; 0 disables",
    )
    parser.add_argument(
        "--fault-log-every",
        type=int,
        default=1,
        help="print a compact fault result every N injected faults; 0 disables",
    )
    parser.add_argument(
        "--fault-chunks",
        type=int,
        default=12,
        help="number of --fault-chunk-tcy windows to hold each transient fault",
    )
    parser.add_argument("--fault-chunk-tcy", type=_parse_int, default=200_000)
    parser.add_argument("--fault-recovery-tcy", type=_parse_int, default=1_000_000)
    parser.add_argument(
        "--brownout-every-s",
        type=float,
        default=0.0,
        help=(
            "inject an additional whole-chain power_rail_bor during awake idle "
            "every N simulated seconds; 0 disables the time-based BOR cadence"
        ),
    )
    parser.add_argument(
        "--mssp-quiesce-tcy",
        type=_parse_int,
        default=5_000_000,
        help=(
            "after clearing a transient I2C/MSSP fault, wait up to this many "
            "Tcy for MAIN0 SSPCON2 transfer bits to quiesce before declaring "
            "the MSSP stuck"
        ),
    )
    parser.add_argument(
        "--mssp-quiesce-step-tcy",
        type=_parse_int,
        default=25_000,
        help="sampling step for --mssp-quiesce-tcy",
    )
    parser.add_argument("--mssp-stuck-cycles", type=_parse_int, default=1_000_000_000)
    parser.add_argument("--dsp-nack-count", type=_parse_int, default=64)
    parser.add_argument("--usb-wait-polls", type=_parse_int, default=4)
    parser.add_argument("--usb-hid-max-steps", type=_parse_int, default=20_000)
    parser.add_argument("--rail-sag-an0", type=_parse_int, default=0x0100)
    parser.add_argument("--rail-restore-an0", type=_parse_int, default=0x0300)
    parser.add_argument("--bor-reconnect-limit", type=int, default=500)
    parser.add_argument("--bor-awake-settle-chunks", type=int, default=80)
    parser.add_argument("--uart-burst-frames", type=_parse_int, default=20)
    parser.add_argument("--control-hex", type=Path, default=V171_CONTROL_HEX)
    parser.add_argument("--main-hex", type=Path, default=V32_MAIN_HEX)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
