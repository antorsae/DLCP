#!/usr/bin/env python3
"""Smoke test: verify that RAM-injected button presses work in the TUI simulator.

Runs the co-simulation for 20M cycles (warmup), then injects a SELECT press
(should toggle mute) and an UP press (should change volume), checking 0x9A
and the LCD after each.
"""

import time

import _bootstrap

from gpsim_tui_simulator import (
    CONTROL_FOSC_HZ,
    GpsimControlSession,
    LinkPipe,
    MAIN_FOSC_HZ,
    MainGpsimSession,
    MemSnapshot,
    TxTriplet,
    SELECT,
    UP,
    DOWN,
    _byte_cycles,
)
from dlcp_fw.sim.main_gpsim_timer3 import _read_reg

ROOT = _bootstrap.REPO_ROOT

CONTROL_HEX = ROOT / "firmware" / "stock" / "control" / "DLCP Control Firmware V1.4.hex"
MAIN_HEX = ROOT / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex"

CHUNK = 300_000
WARMUP = 20_000_000
FIFO = 47

ctl_byte_cyc = _byte_cycles(CONTROL_FOSC_HZ)
main_byte_cyc = _byte_cycles(MAIN_FOSC_HZ)

# ---------- helpers ----------

def _control_rc1_level(mem: MemSnapshot) -> int:
    if (mem.trisc & 0x02) == 0:
        return 1 if (mem.latc & 0x02) else 0
    return 1 if (mem.portc & 0x02) else 0

def _fmt_time(cycle: int) -> str:
    return f"{cycle / CONTROL_FOSC_HZ:.3f}s"

# ---------- create sessions ----------

t0 = time.monotonic()

control = GpsimControlSession(
    CONTROL_HEX,
    fast_boot=True,
    chunk_cycles=CHUNK,
    hold_cycles=240_000,
    rx_fifo_limit=FIFO,
)

main0 = MainGpsimSession(
    MAIN_HEX,
    gpasm="gpasm",
    chunk_cycles=CHUNK,
    tag="0",
    standby_mode="hold",
    main_ra0_adc=0x0228,
    rc2_mode="high",
    timer3_mode="shim",
    rx_fifo_limit=FIFO,
)

link_ctl_m0 = LinkPipe("CTL->M0", byte_cycles=ctl_byte_cyc, fifo_depth=FIFO)
link_m0_ctl = LinkPipe("M0->CTL", byte_cycles=main_byte_cyc, fifo_depth=FIFO)

print(f"Sessions created in {time.monotonic()-t0:.1f}s")

# ---------- warmup ----------

_waiting_entered = False
_heartbeat_active = False
_heartbeat_step = 0

print(f"\nWarmup to {WARMUP:,} cycles...")
step_count = 0
while control.current_cycle < WARMUP:
    link_m0_ctl.pump(control.current_cycle, control)

    # Heartbeat
    if _heartbeat_active:
        _heartbeat_step += 1
        cur = _read_reg(control._issue, 0x01F)
        control._issue(f"reg(0x01F)=0x{cur | 0x08:02X}", 5.0)

    lcd_lines, ctl_mem, ctl_tx, ctl_cycle = control.step()
    for t in ctl_tx:
        if (t.route & 0xF0) == 0xB0:
            link_ctl_m0.enqueue(t)

    # BF/03/01 injection (every 5 steps)
    if _heartbeat_active and (_heartbeat_step % 5 == 0):
        if len(link_m0_ctl) < FIFO - 6:
            link_m0_ctl.enqueue(
                TxTriplet(cycle=ctl_cycle, route=0xBF, cmd=0x03, data=0x01)
            )

    # Detect WAITING loop
    if not _heartbeat_active:
        w = (ctl_mem.input_sel, ctl_mem.volume,
             ctl_mem.cmd1d_setting, ctl_mem.unit_count)
        if not _waiting_entered:
            if all(v == 0x80 for v in w):
                _waiting_entered = True
                print(f"  WAITING entered at {_fmt_time(ctl_cycle)}")
        elif all(v != 0x80 for v in w):
            _heartbeat_active = True
            print(f"  Heartbeat activated at {_fmt_time(ctl_cycle)}")

    link_ctl_m0.pump(ctl_cycle, main0)
    main0.set_standby_bus(_control_rc1_level(ctl_mem))
    m0_snap, m0_tx = main0.step()
    for t in m0_tx:
        if t.route == 0xBF:
            link_m0_ctl.enqueue(t)

    step_count += 1

elapsed = time.monotonic() - t0
lcd1 = lcd_lines[0].rstrip()
lcd2 = lcd_lines[1].rstrip()
flags = ctl_mem.flags
bit1 = (flags >> 1) & 1
ram_9a = _read_reg(control._issue, 0x09A)
ram_be = _read_reg(control._issue, 0x0BE)
ram_bd = _read_reg(control._issue, 0x0BD)
ram_bb = _read_reg(control._issue, 0x0BB)
print(f"\nWarmup done in {elapsed:.1f}s ({step_count} steps)")
print(f"  LCD: '{lcd1}' / '{lcd2}'")
print(f"  flags=0x{flags:02X} bit1={bit1} 0x9A=0x{ram_9a:02X}")
print(f"  debounce: 0xBB=0x{ram_bb:02X} 0xBD=0x{ram_bd:02X} 0xBE=0x{ram_be:02X}")
print(f"  overruns: c2m0={link_ctl_m0.overrun_total} m02c={link_m0_ctl.overrun_total}")

# ---------- run a few more steps to stabilize ----------

for i in range(5):
    link_m0_ctl.pump(control.current_cycle, control)
    if _heartbeat_active:
        _heartbeat_step += 1
        cur = _read_reg(control._issue, 0x01F)
        control._issue(f"reg(0x01F)=0x{cur | 0x08:02X}", 5.0)
    lcd_lines, ctl_mem, ctl_tx, ctl_cycle = control.step()
    for t in ctl_tx:
        if (t.route & 0xF0) == 0xB0:
            link_ctl_m0.enqueue(t)
    if _heartbeat_active and (_heartbeat_step % 5 == 0):
        if len(link_m0_ctl) < FIFO - 6:
            link_m0_ctl.enqueue(
                TxTriplet(cycle=ctl_cycle, route=0xBF, cmd=0x03, data=0x01)
            )
    link_ctl_m0.pump(ctl_cycle, main0)
    main0.set_standby_bus(_control_rc1_level(ctl_mem))
    m0_snap, m0_tx = main0.step()
    for t in m0_tx:
        if t.route == 0xBF:
            link_m0_ctl.enqueue(t)

lcd1 = lcd_lines[0].rstrip()
lcd2 = lcd_lines[1].rstrip()
print(f"\nStabilized LCD: '{lcd1}' / '{lcd2}'")

# ---------- test: press SELECT (mute toggle) ----------

print("\n=== TEST: Press SELECT (should toggle mute) ===")

# Simulate control.press(SELECT)
control.press(SELECT)
print(f"  Pressed SELECT at cycle {control.current_cycle}")

# Read debounce state BEFORE step
ram_be_pre = _read_reg(control._issue, 0x0BE)
ram_bd_pre = _read_reg(control._issue, 0x0BD)
ram_bb_pre = _read_reg(control._issue, 0x0BB)
print(f"  Pre-step debounce: 0xBE=0x{ram_be_pre:02X} 0xBD=0x{ram_bd_pre:02X} 0xBB=0x{ram_bb_pre:02X}")

# Step with heartbeat
link_m0_ctl.pump(control.current_cycle, control)
if _heartbeat_active:
    _heartbeat_step += 1
    cur = _read_reg(control._issue, 0x01F)
    control._issue(f"reg(0x01F)=0x{cur | 0x08:02X}", 5.0)
lcd_lines, ctl_mem, ctl_tx, ctl_cycle = control.step()  # _apply_key_levels runs here
for t in ctl_tx:
    if (t.route & 0xF0) == 0xB0:
        link_ctl_m0.enqueue(t)
if _heartbeat_active and (_heartbeat_step % 5 == 0):
    if len(link_m0_ctl) < FIFO - 6:
        link_m0_ctl.enqueue(
            TxTriplet(cycle=ctl_cycle, route=0xBF, cmd=0x03, data=0x01)
        )
link_ctl_m0.pump(ctl_cycle, main0)
main0.set_standby_bus(_control_rc1_level(ctl_mem))
m0_snap, m0_tx = main0.step()
for t in m0_tx:
    if t.route == 0xBF:
        link_m0_ctl.enqueue(t)

lcd1 = lcd_lines[0].rstrip()
lcd2 = lcd_lines[1].rstrip()
ram_9a = _read_reg(control._issue, 0x09A)
ram_be = _read_reg(control._issue, 0x0BE)
ram_bd = _read_reg(control._issue, 0x0BD)
ram_bb = _read_reg(control._issue, 0x0BB)
flags = ctl_mem.flags
bit4_mute = (flags >> 4) & 1
print("  Post-SELECT step:")
print(f"    LCD: '{lcd1}' / '{lcd2}'")
print(f"    flags=0x{flags:02X} bit4(mute)={bit4_mute} 0x9A=0x{ram_9a:02X}")
print(f"    debounce: 0xBE=0x{ram_be:02X} 0xBD=0x{ram_bd:02X} 0xBB=0x{ram_bb:02X}")

# Run a few more steps to see the LCD update
for i in range(3):
    link_m0_ctl.pump(control.current_cycle, control)
    if _heartbeat_active:
        _heartbeat_step += 1
        cur = _read_reg(control._issue, 0x01F)
        control._issue(f"reg(0x01F)=0x{cur | 0x08:02X}", 5.0)
    lcd_lines, ctl_mem, ctl_tx, ctl_cycle = control.step()
    for t in ctl_tx:
        if (t.route & 0xF0) == 0xB0:
            link_ctl_m0.enqueue(t)
    if _heartbeat_active and (_heartbeat_step % 5 == 0):
        if len(link_m0_ctl) < FIFO - 6:
            link_m0_ctl.enqueue(
                TxTriplet(cycle=ctl_cycle, route=0xBF, cmd=0x03, data=0x01)
            )
    link_ctl_m0.pump(ctl_cycle, main0)
    main0.set_standby_bus(_control_rc1_level(ctl_mem))
    m0_snap, m0_tx = main0.step()
    for t in m0_tx:
        if t.route == 0xBF:
            link_m0_ctl.enqueue(t)

lcd1 = lcd_lines[0].rstrip()
lcd2 = lcd_lines[1].rstrip()
flags = ctl_mem.flags
print(f"  After 3 more steps: LCD='{lcd1}' / '{lcd2}' flags=0x{flags:02X}")

# ---------- test: press UP (volume up) ----------

print("\n=== TEST: Press UP (should change volume) ===")

control.press(UP)
print(f"  Pressed UP at cycle {control.current_cycle}")

link_m0_ctl.pump(control.current_cycle, control)
if _heartbeat_active:
    _heartbeat_step += 1
    cur = _read_reg(control._issue, 0x01F)
    control._issue(f"reg(0x01F)=0x{cur | 0x08:02X}", 5.0)
lcd_lines, ctl_mem, ctl_tx, ctl_cycle = control.step()
for t in ctl_tx:
    if (t.route & 0xF0) == 0xB0:
        link_ctl_m0.enqueue(t)
if _heartbeat_active and (_heartbeat_step % 5 == 0):
    if len(link_m0_ctl) < FIFO - 6:
        link_m0_ctl.enqueue(
            TxTriplet(cycle=ctl_cycle, route=0xBF, cmd=0x03, data=0x01)
        )
link_ctl_m0.pump(ctl_cycle, main0)
main0.set_standby_bus(_control_rc1_level(ctl_mem))
m0_snap, m0_tx = main0.step()
for t in m0_tx:
    if t.route == 0xBF:
        link_m0_ctl.enqueue(t)

lcd1 = lcd_lines[0].rstrip()
lcd2 = lcd_lines[1].rstrip()
ram_9a = _read_reg(control._issue, 0x09A)
flags = ctl_mem.flags
print("  Post-UP step:")
print(f"    LCD: '{lcd1}' / '{lcd2}'")
print(f"    flags=0x{flags:02X} 0x9A=0x{ram_9a:02X}")

# Run a few more steps
for i in range(3):
    link_m0_ctl.pump(control.current_cycle, control)
    if _heartbeat_active:
        _heartbeat_step += 1
        cur = _read_reg(control._issue, 0x01F)
        control._issue(f"reg(0x01F)=0x{cur | 0x08:02X}", 5.0)
    lcd_lines, ctl_mem, ctl_tx, ctl_cycle = control.step()
    for t in ctl_tx:
        if (t.route & 0xF0) == 0xB0:
            link_ctl_m0.enqueue(t)
    if _heartbeat_active and (_heartbeat_step % 5 == 0):
        if len(link_m0_ctl) < FIFO - 6:
            link_m0_ctl.enqueue(
                TxTriplet(cycle=ctl_cycle, route=0xBF, cmd=0x03, data=0x01)
            )
    link_ctl_m0.pump(ctl_cycle, main0)
    main0.set_standby_bus(_control_rc1_level(ctl_mem))
    m0_snap, m0_tx = main0.step()
    for t in m0_tx:
        if t.route == 0xBF:
            link_m0_ctl.enqueue(t)

lcd1 = lcd_lines[0].rstrip()
lcd2 = lcd_lines[1].rstrip()
print(f"  After 3 more steps: LCD='{lcd1}' / '{lcd2}'")

# ---------- test: press DOWN ----------

print("\n=== TEST: Press DOWN ===")

control.press(DOWN)
link_m0_ctl.pump(control.current_cycle, control)
if _heartbeat_active:
    _heartbeat_step += 1
    cur = _read_reg(control._issue, 0x01F)
    control._issue(f"reg(0x01F)=0x{cur | 0x08:02X}", 5.0)
lcd_lines, ctl_mem, ctl_tx, ctl_cycle = control.step()
for t in ctl_tx:
    if (t.route & 0xF0) == 0xB0:
        link_ctl_m0.enqueue(t)
if _heartbeat_active and (_heartbeat_step % 5 == 0):
    if len(link_m0_ctl) < FIFO - 6:
        link_m0_ctl.enqueue(
            TxTriplet(cycle=ctl_cycle, route=0xBF, cmd=0x03, data=0x01)
        )
link_ctl_m0.pump(ctl_cycle, main0)
main0.set_standby_bus(_control_rc1_level(ctl_mem))
m0_snap, m0_tx = main0.step()
for t in m0_tx:
    if t.route == 0xBF:
        link_m0_ctl.enqueue(t)

for i in range(3):
    link_m0_ctl.pump(control.current_cycle, control)
    if _heartbeat_active:
        _heartbeat_step += 1
        cur = _read_reg(control._issue, 0x01F)
        control._issue(f"reg(0x01F)=0x{cur | 0x08:02X}", 5.0)
    lcd_lines, ctl_mem, ctl_tx, ctl_cycle = control.step()
    for t in ctl_tx:
        if (t.route & 0xF0) == 0xB0:
            link_ctl_m0.enqueue(t)
    if _heartbeat_active and (_heartbeat_step % 5 == 0):
        if len(link_m0_ctl) < FIFO - 6:
            link_m0_ctl.enqueue(
                TxTriplet(cycle=ctl_cycle, route=0xBF, cmd=0x03, data=0x01)
            )
    link_ctl_m0.pump(ctl_cycle, main0)
    main0.set_standby_bus(_control_rc1_level(ctl_mem))
    m0_snap, m0_tx = main0.step()
    for t in m0_tx:
        if t.route == 0xBF:
            link_m0_ctl.enqueue(t)

lcd1 = lcd_lines[0].rstrip()
lcd2 = lcd_lines[1].rstrip()
print(f"  After DOWN + 3 steps: LCD='{lcd1}' / '{lcd2}'")

print(f"\nFinal overruns: c2m0={link_ctl_m0.overrun_total} m02c={link_m0_ctl.overrun_total}")

control.close()
main0.close()
print("\nDone.")
