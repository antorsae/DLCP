#!/usr/bin/env python3
"""Probe MAIN's UART + OSC + GPIO state via EP0 to diagnose chain-link wedge.

Use case: CONTROL shows "WAITING FOR DLCP" but USB still works on the
MAIN units.  This means MAIN's chain TX or CONTROL's RX is wedged.
Capture this script's output BEFORE power-cycling so we can compare
against a known-healthy baseline.

The EP0 set_pointer / read_exact protocol (cmds 0x75 / 0x76 / 0xE7,
inherited from stock V2.3 MAIN) reaches arbitrary 12-bit data RAM
addresses including the SFR space (0xF60..0xFFF) on the firmware
side via FSR-indirect reads.  Empirically verified 2026-04-21 by
walking known-distinct addresses and observing distinct return
values.

CRITICAL ADDRESS NOTE: V3.2 MAIN is PIC18F2455 (datasheet 39632e).
Earlier drafts of this script (and an earlier draft of the dlcp-sim
rewrite spec) read the F2455 SFR map from the PDF→markdown rendering
of DS39632E Table 5-1 in `firmware/reference/39632e.md` and ended up
using addresses that were uniformly **0x20 too low**.  Those were
the column-header addresses; the table's data rows agree with
`/opt/homebrew/Cellar/gputils/.../p18f2455.inc` and with the V2.3
disassembly opcodes (e.g. stock V2.3's `movwf BAUDCON` at PC 0x455A
disassembles to 6EB8 → 0xFB8, not 0xF98).  See
`scripts/probe_baudcon_mapping.py` (P0.0) and spec §11b for the
empirical resolution.  The 2455 and K20 happen to share the same
top-of-bank-15 layout for the SFRs this probe touches.

  Register   PIC18F2455 (MAIN)   PIC18F25K20 (CONTROL)
  --------   -----------------   ---------------------
  TXSTA      0xFAC               0xFAC
  RCSTA      0xFAB               0xFAB
  SPBRG      0xFAF               0xFAF
  SPBRGH     0xFB0               0xFB0
  BAUDCON    0xFB8               0xFB8
  OSCCON     0xFD3               0xFD3
  TMR0L      0xFD6               0xFD6
  PORTA      0xF80               0xF80
  PORTB      0xF81               0xF81
  PORTC      0xF82               0xF82

This script does NOT diagnose wedges by itself.  V3.x in CHAIN role
runs on INTOSC with adaptive baud detect; the "naive" interpretation
of TXEN=0 / CREN=0 / SCS=INTOSC as a wedge is WRONG -- those are the
healthy idle-state values when the chain is at rest with auto-baud.

Use this script as follows:
  1. Capture output on a HEALTHY system (post-power-cycle, both MAINs
     responsive, CONTROL showing Volume/Preset/etc., NOT WAITING).
     Save as `baseline.txt`.
  2. When the chain wedges (CONTROL shows WAITING but USB still works),
     run again and save as `wedged.txt`.
  3. Diff the two.  Differences in TXSTA / RCSTA / OSCCON / BAUDCON /
     SPBRG / PORTC between the two states isolate which subsystem is
     in an abnormal state.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dlcp_fw.flash.dlcp_control_flash import enumerate_devices
from dlcp_fw.flash.dlcp_ep0_eeprom_shadow_dump import DlcpEp0
from dlcp_fw.flash.dlcp_main_flash import DEFAULT_VID, DEFAULT_PID

# PIC18F2455 SFR addresses (gputils-canonical / data-row reading of
# DS39632E Table 5-1; see header note above and spec §11b).
ADDR_TXSTA   = 0xFAC
ADDR_RCSTA   = 0xFAB
ADDR_TXREG   = 0xFAD
ADDR_RCREG   = 0xFAE
ADDR_SPBRG   = 0xFAF
ADDR_SPBRGH  = 0xFB0
ADDR_BAUDCON = 0xFB8
ADDR_OSCCON  = 0xFD3
ADDR_OSCTUNE = 0xF9B
ADDR_RCON    = 0xFD0
ADDR_TMR0L   = 0xFD6
# PORTs live at 0xF80/0xF81/0xF82.  An earlier draft of this script
# moved them to 0xF60-0xF62 based on the same +0x20-misaligned column
# header in 39632e.md that drove the BAUDCON misreading.  Per gputils'
# p18f2455.inc, 0xF60..0xF65 is `__BADRAM` (no SFR or RAM there) and
# the USB block starts above it: UFRM(L) at 0xF66, UFRMH at 0xF67,
# UIR/UIE/UEIR/UEIE/USTAT/UCON/UADDR/UCFG at 0xF68..0xF6F, and
# UEP0..UEP15 at 0xF70..0xF7F.  Reading 0xF60-0xF62 thinking it was
# GPIO returned `__BADRAM` contents, never PORTA/B/C.  Restored.
ADDR_PORTA   = 0xF80
ADDR_PORTB   = 0xF81
ADDR_PORTC   = 0xF82
ADDR_LATA    = 0xF89
ADDR_LATB    = 0xF8A
ADDR_LATC    = 0xF8B

# V3.2 MAIN RAM addresses (NOT V1.71 CONTROL!).
# Earlier draft used 0x01F (= V1.71 CONTROL's control_flags); that's
# unrelated RAM on V3.2 MAIN.  Correct V3.2 MAIN addresses per
# src/dlcp_fw/asm/dlcp_main_ram.inc:
ADDR_ACTIVE_FLAGS = 0x05E   # bit 3 = chain gate (open=active, clear=standby)
ADDR_EVENT_FLAGS  = 0x07E   # bit 2 = stdby/wake event pending
ADDR_DIAG_I       = 0x2E5   # I2C transport fault counter
ADDR_DIAG_D       = 0x2E6   # DSP fault counter
ADDR_DIAG_S       = 0x2E7   # standby dispatches (S in cmd 0x44)
ADDR_DIAG_B       = 0x2E8   # bring-up dispatches (B in cmd 0x44)
ADDR_DSP_FAULT_FLAGS = 0x07F  # bit 6 = DSP_FAULT sticky (per
                              # src/dlcp_fw/asm/dlcp_main_v32.asm:108)

TXSTA_BITS = [
    (7, "CSRC"),  (6, "TX9"),   (5, "TXEN"),  (4, "SYNC"),
    (3, "SENDB"), (2, "BRGH"),  (1, "TRMT"),  (0, "TX9D"),
]
RCSTA_BITS = [
    (7, "SPEN"),  (6, "RX9"),   (5, "SREN"),  (4, "CREN"),
    (3, "ADDEN"), (2, "FERR"),  (1, "OERR"),  (0, "RX9D"),
]
BAUDCON_BITS = [
    (7, "ABDOVF"), (6, "RCIDL"), (4, "SCKP"),
    (3, "BRG16"),  (1, "WUE"),   (0, "ABDEN"),
]
OSCCON_BITS = [
    (7, "IDLEN"), (6, "IRCF2"), (5, "IRCF1"), (4, "IRCF0"),
    (3, "OSTS"),  (2, "IOFS"),  (1, "SCS1"),  (0, "SCS0"),
]


def fmt_bits(value: int, bits: list[tuple[int, str]]) -> str:
    parts = [name for bit, name in bits if (value >> bit) & 1]
    return " ".join(parts) if parts else "(none)"


def read_block(ep0: DlcpEp0, start: int, size: int) -> bytes:
    ep0.set_pointer(start)
    return ep0.read_exact(size)


def read_byte(ep0: DlcpEp0, addr: int) -> int:
    """Read one byte; on transient EP0 failure return 0xFF and don't
    abort the whole probe.  Codex review of b02c370 noted that bare
    reads would propagate USBError mid-script; this matches the
    graceful-degradation pattern used by dlcp_diag's EP0 path."""
    try:
        return read_block(ep0, addr, 1)[0]
    except (RuntimeError, OSError, ValueError, NotImplementedError) as exc:
        import sys
        print(f"    WARN: read 0x{addr:04X} failed: {exc}", file=sys.stderr)
        return 0xFF


def probe_one(path: bytes) -> None:
    path_str = path.decode("utf-8", errors="replace")
    print(f"\n=== {path_str} ===")
    try:
        ep0 = DlcpEp0(vid=DEFAULT_VID, pid=DEFAULT_PID, path=path)
    except Exception as exc:
        print(f"  ERROR opening EP0: {exc}")
        return

    # Liveness check: read TMR0L twice.  If Timer 0 is running, the value
    # advances.  Also confirms SFR access works.
    t0a = read_byte(ep0, ADDR_TMR0L)
    t0b = read_byte(ep0, ADDR_TMR0L)
    if t0a != t0b:
        print(f"  TMR0L liveness:  0x{t0a:02X} -> 0x{t0b:02X}    "
              f"diff={(t0b - t0a) & 0xFF}  (Timer 0 IS running, SFR access OK)")
    else:
        print(f"  TMR0L liveness:  0x{t0a:02X} (same)             "
              f"(Timer 0 not running OR SFR address miss)")

    # V3.2 MAIN state flags + diag-cell live snapshot.
    af = read_byte(ep0, ADDR_ACTIVE_FLAGS)
    ef = read_byte(ep0, ADDR_EVENT_FLAGS)
    di = read_byte(ep0, ADDR_DIAG_I)
    dd = read_byte(ep0, ADDR_DIAG_D)
    ds = read_byte(ep0, ADDR_DIAG_S)
    db = read_byte(ep0, ADDR_DIAG_B)
    dsp_fault = read_byte(ep0, ADDR_DSP_FAULT_FLAGS)
    print(f"  active_flags  (0x05E) = 0x{af:02X}    "
          f"rx_route_is_b1(bit0)={af & 1}  "
          f"chain_gate_open(bit3)={(af >> 3) & 1}")
    print(f"  event_flags   (0x07E) = 0x{ef:02X}    "
          f"stdby_wake_pending(bit2)={(ef >> 2) & 1}")
    print(f"  dsp_fault_flg (0x07F) = 0x{dsp_fault:02X}    "
          f"DSP_FAULT(bit6)={(dsp_fault >> 6) & 1}")
    print(f"  diag cells    I={di} D={dd} S={ds} B={db}  (live RAM vs "
          f"cmd 0x44 snapshot)")

    # UART block.
    txsta   = read_byte(ep0, ADDR_TXSTA)
    rcsta   = read_byte(ep0, ADDR_RCSTA)
    spbrg   = read_byte(ep0, ADDR_SPBRG)
    spbrgh  = read_byte(ep0, ADDR_SPBRGH)
    baudcon = read_byte(ep0, ADDR_BAUDCON)
    print(f"  TXSTA   (0xFAC) = 0x{txsta:02X}    {fmt_bits(txsta, TXSTA_BITS)}")
    print(f"  RCSTA   (0xFAB) = 0x{rcsta:02X}    {fmt_bits(rcsta, RCSTA_BITS)}")
    print(f"  SPBRG   (0xFAF) = 0x{spbrg:02X} ({spbrg})")
    print(f"  SPBRGH  (0xFB0) = 0x{spbrgh:02X}")
    print(f"  BAUDCON (0xFB8) = 0x{baudcon:02X}    {fmt_bits(baudcon, BAUDCON_BITS)}")

    # OSC.
    osccon = read_byte(ep0, ADDR_OSCCON)
    osctune = read_byte(ep0, ADDR_OSCTUNE)
    scs_bits = osccon & 0x03
    scs_name = {0: "PRIMARY", 1: "T1OSC", 2: "INTOSC", 3: "INTOSC"}[scs_bits]
    ircf_bits = (osccon >> 4) & 0x07
    ircf_freq = {0: "31kHz", 1: "125kHz", 2: "250kHz", 3: "500kHz",
                 4: "1MHz",  5: "2MHz",   6: "4MHz",   7: "8MHz"}[ircf_bits]
    print(f"  OSCTUNE (0xF9B) = 0x{osctune:02X}    PLLEN={(osctune >> 6) & 1}")
    print(f"  OSCCON  (0xFD3) = 0x{osccon:02X}    {fmt_bits(osccon, OSCCON_BITS)}")
    print(f"    -> SCS={scs_bits} ({scs_name})  "
          f"IRCF={ircf_bits} ({ircf_freq})  "
          f"OSTS={(osccon >> 3) & 1}")

    # GPIO.
    porta = read_byte(ep0, ADDR_PORTA)
    portc = read_byte(ep0, ADDR_PORTC)
    print(f"  PORTA   (0xF80) = 0x{porta:02X}    "
          f"AN0(bit0)={porta & 1}  RA1(bit1)={(porta >> 1) & 1}")
    print(f"  PORTC   (0xF82) = 0x{portc:02X}    "
          f"RC2={(portc >> 2) & 1} ({'CHAIN' if (portc >> 2) & 1 else 'MASTER'})  "
          f"RC6_TX={(portc >> 6) & 1}  "
          f"RC7_RX={(portc >> 7) & 1}")

    # 8 quick samples of TXREG/RCREG/RCSTA flags to catch transient
    # transmit activity or receive errors that single reads miss.
    print(f"  TXSTA samples (8 quick reads): " +
          " ".join(f"0x{read_byte(ep0, ADDR_TXSTA):02X}" for _ in range(8)))
    print(f"  RCSTA samples (8 quick reads): " +
          " ".join(f"0x{read_byte(ep0, ADDR_RCSTA):02X}" for _ in range(8)))


def main() -> int:
    devs = enumerate_devices(DEFAULT_VID, DEFAULT_PID)
    if not devs:
        print("No DLCP HID devices detected.")
        return 1
    for d in devs:
        probe_one(d.path)
    print()
    print("INTERPRETATION NOTES")
    print("-" * 40)
    print("Capture this output BOTH at idle (baseline) AND when CONTROL")
    print("shows WAITING FOR DLCP.  Diff the two.  V3.x in CHAIN role")
    print("normally has SCS=INTOSC with ABDEN=1 (auto-baud detect),")
    print("and TXEN/CREN may toggle on demand -- so any single value")
    print("alone is not a wedge signature.  Real wedges show as STABLE")
    print("differences across the 8 quick-read samples.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
