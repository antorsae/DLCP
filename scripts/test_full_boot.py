#!/usr/bin/env python3
"""Full-boot co-simulation: CONTROL + MAIN, 3-4 seconds of real-time execution.

Runs the unpatched DLCP firmware with fast_boot=False so the LCD shows the
real boot sequence:  "Firmware 1.4" → "Waiting for DLCP" → normal DISPLAY.

Target: ~48 M cycles at 12 MHz FOSC ≈ 4 seconds wall-clock equivalent.

Heartbeat modelling:
  In real hardware, CONTROL periodically toggles RC1 (heartbeat) and MAIN
  detects the toggle (via the current-loop bus) and responds with status
  frames, including BF/03/01 ("I'm active").  Our simulator does not yet
  model the RC1→MAIN feedback loop, so we inject a synthetic BF/03/01
  from MAIN once per CONTROL standby cycle.  This lets function_042 exit
  and CONTROL proceed through RECONNECT → DISPLAY.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gpsim_tui_simulator import (
    CONTROL_FOSC_HZ,
    GpsimControlSession,
    LinkPipe,
    MAIN_FOSC_HZ,
    MainGpsimSession,
    MemSnapshot,
    TxTriplet,
    _byte_cycles,
)
from dlcp_fw.sim.main_gpsim_timer3 import _read_reg

CONTROL_HEX = ROOT / "firmware" / "stock" / "control" / "DLCP Control Firmware V1.4.hex"
MAIN_HEX    = ROOT / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex"

CHUNK       = 300_000        # cycles per step
TARGET      = 48_000_000     # ~4 seconds at 12 MHz
FIFO        = 47

ctl_byte_cyc  = _byte_cycles(CONTROL_FOSC_HZ)
main_byte_cyc = _byte_cycles(MAIN_FOSC_HZ)

# ---------- helpers ----------

def _control_rc1_level(mem: MemSnapshot) -> int:
    if (mem.trisc & 0x02) == 0:
        return 1 if (mem.latc & 0x02) else 0
    return 1 if (mem.portc & 0x02) else 0


def _waiting_vars(ctl) -> tuple[int, int, int, int]:
    """Read the four WAITING-loop sentinel variables."""
    return (
        _read_reg(ctl._issue, 0x0B8),  # input_sel
        _read_reg(ctl._issue, 0x0B9),  # volume
        _read_reg(ctl._issue, 0x0A7),  # bl_timeout
        _read_reg(ctl._issue, 0x0A1),  # unit_count
    )


def _fmt_time(cycle: int) -> str:
    secs = cycle / CONTROL_FOSC_HZ
    return f"{secs:.3f}s"


# ---------- create sessions ----------

print(f"CONTROL HEX: {CONTROL_HEX}")
print(f"MAIN    HEX: {MAIN_HEX}")
print(f"Target cycles: {TARGET:,}  (~{TARGET/CONTROL_FOSC_HZ:.1f}s)")
print()

t0 = time.monotonic()

control = GpsimControlSession(
    CONTROL_HEX,
    fast_boot=False,          # full boot with "Firmware 1.4" visible
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
print()

# ---------- simulation loop ----------

prev_lcd1 = ""
prev_lcd2 = ""
prev_bit1 = -1
firmware_14_seen = False
waiting_seen = False
waiting_exit_cycle = 0
display_entry_cycle = 0
step_num = 0
heartbeat_count = 0                  # how many heartbeat injections so far
HEARTBEAT_INTERVAL = 3               # inject every N steps after WAITING exit
ctl_tx_total = 0
m0_tx_total  = 0
m0_bf_frames = 0

# Milestones for progress reporting
report_interval = 50  # report every N steps

while control.current_cycle < TARGET:
    # --- pump M0→CTL into CONTROL, then step CONTROL ---
    link_m0_ctl.pump(control.current_cycle, control)
    lcd_lines, ctl_mem, ctl_tx, ctl_cycle = control.step()

    # --- route CONTROL TX → M0 ---
    for t in ctl_tx:
        ctl_tx_total += 1
        if (t.route & 0xF0) == 0xB0:
            link_ctl_m0.enqueue(t)

    # --- pump CTL→M0 into MAIN0, then step MAIN0 ---
    link_ctl_m0.pump(ctl_cycle, main0)
    main0.set_standby_bus(_control_rc1_level(ctl_mem))
    m0_snap, m0_tx = main0.step()

    # --- route MAIN0 TX → CTL (single-main: BF only) ---
    for t in m0_tx:
        m0_tx_total += 1
        if t.route == 0xBF:
            m0_bf_frames += 1
            link_m0_ctl.enqueue(t)

    # --- heartbeat model: periodic BF/03/01 + bit3 after WAITING exit ---
    # In real hardware, CONTROL toggles RC1 (heartbeat) every ~30K iterations
    # inside function_042.  MAIN detects the toggle via current-loop ADC,
    # responds with BF/03/01 ("I'm active") plus status frames (BF/06/xx,
    # BF/07/xx) that set bit3 via function_019.  This allows function_042
    # to exit, keeping the DISPLAY and RECONNECT loops alive.
    #
    # Since we don't fully model the RC1→MAIN→response feedback loop,
    # we periodically inject BF/03/01 (for RECONNECT bit1) and set bit3
    # directly (for function_042 exit).
    if waiting_exit_cycle and (step_num % HEARTBEAT_INTERVAL == 0):
        synthetic = TxTriplet(cycle=ctl_cycle, route=0xBF, cmd=0x03, data=0x01)
        link_m0_ctl.enqueue(synthetic)
        # Set bit3 (new-data flag) so function_042 can exit.
        cur_flags = _read_reg(control._issue, 0x01F)
        control._issue(f"reg(0x01F)=0x{cur_flags | 0x08:02X}", 5.0)
        heartbeat_count += 1
        if heartbeat_count <= 5 or heartbeat_count % 20 == 0:
            print(f"[{_fmt_time(ctl_cycle)} step={step_num}] "
                  f"Heartbeat #{heartbeat_count}: injected BF/03/01 + set bit3")

    # --- extract state ---
    lcd1 = lcd_lines[0].rstrip()
    lcd2 = lcd_lines[1].rstrip()
    bit1 = (ctl_mem.flags >> 1) & 1
    flags = ctl_mem.flags

    # --- detect LCD changes ---
    if lcd1 != prev_lcd1 or lcd2 != prev_lcd2:
        secs = _fmt_time(ctl_cycle)
        print(f"[{secs} step={step_num} cyc=0x{ctl_cycle:08X}] LCD changed:")
        print(f"  |{lcd1:16}|")
        print(f"  |{lcd2:16}|")
        print(f"  flags=0x{flags:02X} bit1={bit1} "
              f"q c2m0={len(link_ctl_m0)} m02c={len(link_m0_ctl)} "
              f"ctl_tx={ctl_tx_total} m0_tx={m0_tx_total} m0_bf={m0_bf_frames}")

        if "1.4" in lcd1 or "1.4" in lcd2:
            firmware_14_seen = True
            print("  >>> 'Firmware 1.4' detected!")

        if "waiting" in lcd1.lower() or "waiting" in lcd2.lower():
            waiting_seen = True
            print("  >>> 'Waiting for DLCP' detected!")

        prev_lcd1 = lcd1
        prev_lcd2 = lcd2

    # --- detect bit1 changes ---
    if bit1 != prev_bit1 and prev_bit1 >= 0:
        secs = _fmt_time(ctl_cycle)
        wv = _waiting_vars(control)
        print(f"[{secs} step={step_num}] bit1 {prev_bit1}->{bit1} "
              f"flags=0x{flags:02X} "
              f"waiting=[0x{wv[0]:02X},0x{wv[1]:02X},0x{wv[2]:02X},0x{wv[3]:02X}] "
              f"LCD='{lcd1}/{lcd2}'")

        if bit1 == 1 and prev_bit1 == 0 and not display_entry_cycle:
            display_entry_cycle = ctl_cycle
            print(f"  >>> DISPLAY entry at {_fmt_time(ctl_cycle)}!")

    prev_bit1 = bit1

    # --- detect WAITING loop exit (any WAITING var goes non-0x80) ---
    if waiting_seen and not waiting_exit_cycle:
        wv = _waiting_vars(control)
        if all(v != 0x80 for v in wv):
            waiting_exit_cycle = ctl_cycle
            print(f"[{_fmt_time(ctl_cycle)} step={step_num}] WAITING loop exit! "
                  f"vars=[0x{wv[0]:02X},0x{wv[1]:02X},0x{wv[2]:02X},0x{wv[3]:02X}]")

    # --- periodic progress ---
    if step_num % report_interval == 0:
        secs = _fmt_time(ctl_cycle)
        elapsed = time.monotonic() - t0
        pct = 100.0 * ctl_cycle / TARGET
        ram_9a = _read_reg(control._issue, 0x09A)
        print(f"  progress: {pct:5.1f}% {secs} step={step_num} "
              f"bit1={bit1} 0x9A=0x{ram_9a:02X} "
              f"q c2m0={len(link_ctl_m0)} m02c={len(link_m0_ctl)} "
              f"ctl_tx={ctl_tx_total} m0_tx={m0_tx_total} m0_bf={m0_bf_frames} "
              f"wall={elapsed:.0f}s")

    step_num += 1

# ---------- summary ----------
elapsed = time.monotonic() - t0
lcd1 = prev_lcd1
lcd2 = prev_lcd2

print()
print("=" * 60)
print("SIMULATION SUMMARY")
print("=" * 60)
print(f"Total steps:        {step_num}")
print(f"Final cycle:        0x{control.current_cycle:08X} ({_fmt_time(control.current_cycle)})")
print(f"Wall time:          {elapsed:.1f}s")
print(f"Firmware 1.4 seen:  {firmware_14_seen}")
print(f"Waiting seen:       {waiting_seen}")
if waiting_exit_cycle:
    print(f"Waiting exit:       {_fmt_time(waiting_exit_cycle)}")
else:
    print(f"Waiting exit:       NOT YET")
if display_entry_cycle:
    print(f"Display entry:      {_fmt_time(display_entry_cycle)}")
else:
    print(f"Display entry:      NOT YET (bit1 still 0)")
print(f"Final LCD:")
print(f"  |{lcd1:16}|")
print(f"  |{lcd2:16}|")

wv = _waiting_vars(control)
ram_9a = _read_reg(control._issue, 0x09A)
flags = _read_reg(control._issue, 0x01F)
print(f"Final flags:        0x{flags:02X} (bit1={(flags>>1)&1})")
print(f"Final 0x9A:         0x{ram_9a:02X}")
print(f"Waiting vars:       [0x{wv[0]:02X}, 0x{wv[1]:02X}, 0x{wv[2]:02X}, 0x{wv[3]:02X}]")
print(f"Heartbeats:         {heartbeat_count}")
print(f"Serial frames:      CTL TX={ctl_tx_total} M0 TX={m0_tx_total} M0 BF={m0_bf_frames}")
print(f"Overruns:           CTL->M0={link_ctl_m0.overrun_total} M0->CTL={link_m0_ctl.overrun_total}")

control.close()
main0.close()
