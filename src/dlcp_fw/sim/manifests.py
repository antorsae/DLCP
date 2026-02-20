"""Built-in simulation-only overlay manifests."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .hexio import parse_intel_hex
from .overlay import OverlayManifest


def control_reset_to_appstart() -> OverlayManifest:
    """
    Redirect reset vector to app start (0x0040) for gpsim-only execution.

    Stock control reset jumps to bootloader 0x7800; gpsim USB bootloader paths
    can stall. This keeps original HEX clean by applying only to temp copies.
    """

    return OverlayManifest(
        name="control_reset_to_appstart",
        preconditions={
            # Require an existing GOTO opcode at reset (low byte may vary by build).
            0x0001: 0xEF,
        },
        byte_patches={
            # PIC18 encoding for: goto 0x0040
            0x0000: 0x20,
            0x0001: 0xEF,
            0x0002: 0x00,
            0x0003: 0xF0,
        },
        postconditions={
            0x0000: 0x20,
            0x0001: 0xEF,
            0x0002: 0x00,
            0x0003: 0xF0,
        },
        description="Simulation-only boot redirect: reset -> 0x0040",
    )


def control_disable_boot_wait() -> OverlayManifest:
    """
    Optional speedup: bypass long startup wait loop in sim.

    This overlay is intentionally conservative and can be omitted from high-fidelity
    runs. It only patches a known long delay call site to NOPs in v1.4.
    """

    return OverlayManifest(
        name="control_disable_boot_wait",
        preconditions={
            # call delay helper at early boot path.
            0x0052: 0xC8,
            0x0053: 0xEC,
            0x0054: 0x00,
            0x0055: 0xF0,
        },
        byte_patches={
            # Replace one CALL instruction with two NOP words.
            0x0052: 0x00,
            0x0053: 0x00,
            0x0054: 0x00,
            0x0055: 0x00,
        },
        postconditions={
            0x0052: 0x00,
            0x0053: 0x00,
            0x0054: 0x00,
            0x0055: 0x00,
        },
        description="Optional sim acceleration by removing one startup delay call.",
    )


def _control_disable_standby_check_manifest(*, jump_addr: int, goto_word_lo: int, name: str) -> OverlayManifest:
    """Build a simulation overlay that NOPs a standby jump site."""
    return OverlayManifest(
        name=name,
        preconditions={
            jump_addr + 0x0: goto_word_lo,
            jump_addr + 0x1: 0xEF,
            jump_addr + 0x2: 0x09,
            jump_addr + 0x3: 0xF0,
        },
        byte_patches={
            # Two NOP words (0x0000 0x0000)
            jump_addr + 0x0: 0x00,
            jump_addr + 0x1: 0x00,
            jump_addr + 0x2: 0x00,
            jump_addr + 0x3: 0x00,
        },
        postconditions={
            jump_addr + 0x0: 0x00,
            jump_addr + 0x1: 0x00,
            jump_addr + 0x2: 0x00,
            jump_addr + 0x3: 0x00,
        },
        description="Simulation-only: NOP standby jump so firmware stays in DISPLAY mode.",
    )


def control_disable_standby_check() -> OverlayManifest:
    """
    Simulation-only: disable the standby/reconnect jump in the main loop.

    Without a real MAIN unit providing continuous serial responses, the
    firmware's idle timeout expires during a single simulation chunk and
    the btfss check at label_205 (0x1226) jumps to the standby handler
    (label_214 at 0x129E).  That handler clears CONNECTED (bit1) and
    displays "Waiting for DLCP", making the harness unable to keep the
    firmware in DISPLAY mode.

    This overlay NOPs the ``goto label_214`` at 0x1228, so the main loop
    always falls through to label_206 (active display) regardless of bit1.
    Label_214 is only reachable via this one goto, so the entire standby/
    reconnect flow becomes dead code.

    v1.4 disassembly:
      001226:  a21f  btfss  0x1F, 1, A    ; label_205 – check CONNECTED
      001228:  ef4f  goto   label_214     ; → standby handler (0x129E)
      00122a:  f009
      00122c:  961f  bcf    0x1F, 3, A    ; label_206 – active display loop
    """

    return _control_disable_standby_check_manifest(
        jump_addr=0x1228,
        goto_word_lo=0x4F,
        name="control_disable_standby_check",
    )


def control_disable_standby_check_v15b() -> OverlayManifest:
    """V1.5b standby-jump variant at 0x121A (goto label_212)."""
    return _control_disable_standby_check_manifest(
        jump_addr=0x121A,
        goto_word_lo=0x48,
        name="control_disable_standby_check_v15b",
    )


def control_disable_standby_check_for_hex(control_hex: Path) -> OverlayManifest:
    """Select the standby-check overlay matching the control firmware layout."""
    mem = parse_intel_hex(control_hex)
    if (
        mem.get(0x1228, 0xFF) == 0x4F
        and mem.get(0x1229, 0xFF) == 0xEF
        and mem.get(0x122A, 0xFF) == 0x09
        and mem.get(0x122B, 0xFF) == 0xF0
    ):
        return control_disable_standby_check()
    if (
        mem.get(0x121A, 0xFF) == 0x48
        and mem.get(0x121B, 0xFF) == 0xEF
        and mem.get(0x121C, 0xFF) == 0x09
        and mem.get(0x121D, 0xFF) == 0xF0
    ):
        return control_disable_standby_check_v15b()
    raise RuntimeError(
        "unsupported control standby-jump layout: expected V1.4 site 0x1228 or V1.5b site 0x121A"
    )


def main_reset_to_appstart() -> OverlayManifest:
    """Redirect main reset + ISR vectors to app region (0x1000+) for gpsim.

    Stock firmware is designed for a USB bootloader that occupies 0x0000-0x0FFF
    and redirects:
      reset  0x0000 -> GOTO 0x1000
      hi ISR 0x0008 -> GOTO 0x1008
      lo ISR 0x0018 -> RETFIE (firmware has data table at 0x1018, not ISR code)

    Without these redirects, any interrupt fires into unprogrammed flash (NOPs)
    and the CPU never returns from the ISR.
    """

    return OverlayManifest(
        name="main_reset_to_appstart",
        byte_patches={
            # Reset vector: GOTO 0x1000
            # PIC18 encoding: EF00 F008 -> k=0x0800, target=k*2=0x1000
            0x0000: 0x00,
            0x0001: 0xEF,
            0x0002: 0x08,
            0x0003: 0xF0,
            # High-priority ISR vector: GOTO 0x1008
            # PIC18 encoding: EF04 F008 -> k=0x0804, target=k*2=0x1008
            0x0008: 0x04,
            0x0009: 0xEF,
            0x000A: 0x08,
            0x000B: 0xF0,
            # Low-priority ISR vector: RETFIE (return immediately)
            # Firmware has a data table at 0x1018, not ISR code.
            # PIC18 RETFIE = 0x0010
            0x0018: 0x10,
            0x0019: 0x00,
        },
        postconditions={
            0x0000: 0x00,
            0x0001: 0xEF,
            0x0002: 0x08,
            0x0003: 0xF0,
            0x0008: 0x04,
            0x0009: 0xEF,
            0x000A: 0x08,
            0x000B: 0xF0,
            0x0018: 0x10,
            0x0019: 0x00,
        },
        description="Simulation-only boot redirect: reset + ISR vectors -> 0x1000+",
    )


_MAIN_SERIAL_MAILBOX_HOOK_ASM = r"""
LIST P=18F2550
#include <p18f2550.inc>

; Hook UART helper routines used by serial parser:
; - function_087: read next RX byte
; - function_109: RX available?
; - function_111: TX byte output
; - function_079: Timer3 delay (replaced with software shim for gpsim)
; - function_024: ADC wait/boot sequence helper (avoid ADC hang in gpsim)
;
; Mailbox RAM:
;   0x7C0 RX_RD
;   0x7C1 RX_WR
;   0x7C2 TX_RD (reserved)
;   0x7C3 TX_WR
;   0x7C4..0x7C6 saved BSR scratch (hook-local)
;   0x780..0x7BF RX circular buffer (64 bytes used)
;   0x7E0..0x7FF TX circular buffer (32 bytes used)

org 0x45FA
    goto sim_function_087
org 0x45FE
    nop

org 0x4872
    goto sim_function_109
org 0x4876
    nop

org 0x4896
    goto sim_function_111
org 0x489A
    nop

; gpsim does not advance TMR3IF for this firmware path reliably.
; Replace Timer3 wait routine with a software-equivalent delay shim.
org 0x447E
    goto sim_function_079
org 0x4482
    nop

org 0x2D8C
    goto sim_function_024
org 0x2D90
    nop

org 0x7000
sim_function_109:
    movff BSR, 0x7C4
    movlb 0x7
    movf 0x0C1, W, BANKED
    xorwf 0x0C0, W, BANKED
    bnz sim109_has_data
    clrw
    movff 0x7C4, BSR
    return 0x0
sim109_has_data:
    movlw 0x01
    movff 0x7C4, BSR
    return 0x0

sim_function_087:
    movff BSR, 0x7C5
    clrf 0x004, ACCESS
    movlb 0x7
    movf 0x0C1, W, BANKED
    xorwf 0x0C0, W, BANKED
    bz sim087_done

    lfsr 0, 0x780
    movlb 0x7
    movf 0x0C0, W, BANKED
    andlw 0x3F
    addwf FSR0L, F, ACCESS
    movf INDF0, W, ACCESS
    movwf 0x004, ACCESS

    movlb 0x7
    incf 0x0C0, F, BANKED

sim087_done:
    movf 0x004, W, ACCESS
    movff 0x7C5, BSR
    return 0x0

sim_function_111:
    movff BSR, 0x7C6
    movwf 0x003, ACCESS

    lfsr 0, 0x7E0
    movlb 0x7
    movf 0x0C3, W, BANKED
    andlw 0x1F
    addwf FSR0L, F, ACCESS
    movf 0x003, W, ACCESS
    movwf INDF0, ACCESS

    movlb 0x7
    incf 0x0C3, F, BANKED

    movff 0x003, TXREG
    movf 0x003, W, ACCESS
    movff 0x7C6, BSR
    return 0x0

org 0x7100
sim_function_079:
    bcf PIE2, TMR3IE, ACCESS
    movlw 0x98
    movwf T3CON, ACCESS
    bsf T3CON, TMR3ON, ACCESS

sim79_outer:
    movf 0x004, W, ACCESS
    iorwf 0x003, W, ACCESS
    bz sim79_done

    ; Emulate one Timer3 overflow event per outer iteration.
    bcf PIR2, TMR3IF, ACCESS
    bsf PIR2, TMR3IF, ACCESS

    decf 0x003, F, ACCESS
    movf 0x003, W, ACCESS
    xorlw 0xFF
    bnz sim79_outer
    decf 0x004, F, ACCESS
    bra sim79_outer

sim79_done:
    bcf T3CON, TMR3ON, ACCESS
    return 0x0

org 0x7140
sim_function_024:
    bcf INTCON, GIE, ACCESS
    bcf LATB, LATB2, ACCESS
    movlb 0x0
    movlw 0x37
    movwf 0x88, BANKED
    movlw 0x02
    movwf 0x89, BANKED
    goto 0x2DC8

end
"""


def main_serial_mailbox_hooks(gpasm: str = "gpasm") -> OverlayManifest:
    """Build mailbox hook overlay for main UART helper functions."""

    with tempfile.TemporaryDirectory(prefix="main_serial_hook_") as td:
        td_path = Path(td)
        asm = td_path / "main_serial_hook.asm"
        out_hex = td_path / "main_serial_hook.hex"
        asm.write_text(_MAIN_SERIAL_MAILBOX_HOOK_ASM, encoding="ascii")
        subprocess.run(
            [gpasm, "-p18f2550", "-o", str(out_hex), str(asm)],
            check=True,
            capture_output=True,
            text=True,
        )
        patch_mem = parse_intel_hex(out_hex)

    return OverlayManifest(
        name="main_serial_mailbox_hooks",
        preconditions={
            0x2D8C: 0xF2,  # function_024 prologue bytes: F2 9E ...
            0x2D8D: 0x9E,
            0x447E: 0xA0,  # function_079 prologue bytes: A0 92 98 0E
            0x447F: 0x92,
            0x4480: 0x98,
            0x4481: 0x0E,
            0x45FA: 0x04,  # function_087 prologue bytes: 04 6A ...
            0x45FB: 0x6A,
            0x4872: 0x00,  # function_109 prologue bytes: 00 01 ...
            0x4873: 0x01,
            0x4896: 0xE8,  # function_111 prologue bytes: E8 CF ...
            0x4897: 0xCF,
        },
        byte_patches=patch_mem,
        postconditions={
            0x2D8D: 0xEF,
            0x447F: 0xEF,
            # PIC18 GOTO second byte signature.
            0x45FB: 0xEF,
            0x4873: 0xEF,
            0x4897: 0xEF,
        },
        description="Simulation-only main UART hooks: RAM mailbox RX/TX",
    )


_MAIN_UART_MAILBOX_ONLY_HOOK_ASM = r"""
LIST P=18F2550
#include <p18f2550.inc>

; Hook UART helper routines used by serial parser:
; - function_087: read next RX byte
; - function_109: RX available?
; - function_111: TX byte output
;
; Mailbox RAM:
;   0x7C0 RX_RD
;   0x7C1 RX_WR
;   0x7C2 TX_RD (reserved)
;   0x7C3 TX_WR
;   0x7C4..0x7C6 saved BSR scratch (hook-local)
;   0x780..0x7BF RX circular buffer (64 bytes used)
;   0x7E0..0x7FF TX circular buffer (32 bytes used)

org 0x45FA
    goto sim_function_087
org 0x45FE
    nop

org 0x4872
    goto sim_function_109
org 0x4876
    nop

org 0x4896
    goto sim_function_111
org 0x489A
    nop

org 0x7000
sim_function_109:
    movff BSR, 0x7C4
    movlb 0x7
    movf 0x0C1, W, BANKED
    xorwf 0x0C0, W, BANKED
    bnz sim109_has_data
    clrw
    movff 0x7C4, BSR
    return 0x0
sim109_has_data:
    movlw 0x01
    movff 0x7C4, BSR
    return 0x0

sim_function_087:
    movff BSR, 0x7C5
    clrf 0x004, ACCESS
    movlb 0x7
    movf 0x0C1, W, BANKED
    xorwf 0x0C0, W, BANKED
    bz sim087_done

    lfsr 0, 0x780
    movlb 0x7
    movf 0x0C0, W, BANKED
    andlw 0x3F
    addwf FSR0L, F, ACCESS
    movf INDF0, W, ACCESS
    movwf 0x004, ACCESS

    movlb 0x7
    incf 0x0C0, F, BANKED

sim087_done:
    movf 0x004, W, ACCESS
    movff 0x7C5, BSR
    return 0x0

sim_function_111:
    movff BSR, 0x7C6
    movwf 0x003, ACCESS

    lfsr 0, 0x7E0
    movlb 0x7
    movf 0x0C3, W, BANKED
    andlw 0x1F
    addwf FSR0L, F, ACCESS
    movf 0x003, W, ACCESS
    movwf INDF0, ACCESS

    movlb 0x7
    incf 0x0C3, F, BANKED

    movff 0x003, TXREG
    movf 0x003, W, ACCESS
    movff 0x7C6, BSR
    return 0x0

end
"""


def main_serial_mailbox_hooks_uart_only(gpasm: str = "gpasm") -> OverlayManifest:
    """Build mailbox hook overlay for main UART helper functions only."""

    with tempfile.TemporaryDirectory(prefix="main_uart_hook_") as td:
        td_path = Path(td)
        asm = td_path / "main_uart_hook.asm"
        out_hex = td_path / "main_uart_hook.hex"
        asm.write_text(_MAIN_UART_MAILBOX_ONLY_HOOK_ASM, encoding="ascii")
        subprocess.run(
            [gpasm, "-p18f2550", "-o", str(out_hex), str(asm)],
            check=True,
            capture_output=True,
            text=True,
        )
        patch_mem = parse_intel_hex(out_hex)

    return OverlayManifest(
        name="main_serial_mailbox_hooks_uart_only",
        preconditions={
            0x45FA: 0x04,  # function_087 prologue bytes: 04 6A ...
            0x45FB: 0x6A,
            0x4872: 0x00,  # function_109 prologue bytes: 00 01 ...
            0x4873: 0x01,
            0x4896: 0xE8,  # function_111 prologue bytes: E8 CF ...
            0x4897: 0xCF,
        },
        byte_patches=patch_mem,
        postconditions={
            0x45FB: 0xEF,
            0x4873: 0xEF,
            0x4897: 0xEF,
        },
        description="Simulation-only UART hooks: mailbox-backed RX/TX probes",
    )


_MAIN_ADC_BOOT_WAIT_HOOK_ASM = r"""
LIST P=18F2550
#include <p18f2550.inc>

; gpsim does not resolve ADCON0.GO completion for this firmware boot path.
; Hook function_024 to bypass ADC wait loops while preserving side effects.

org 0x2D8C
    goto sim_function_024
org 0x2D90
    nop

org 0x7090
sim_function_024:
    bcf INTCON, GIE, ACCESS
    bcf LATB, LATB2, ACCESS
    movlb 0x0
    movlw 0x37
    movwf 0x88, BANKED
    movlw 0x02
    movwf 0x89, BANKED
    goto 0x2DC8

end
"""


def main_adc_boot_wait_hook(gpasm: str = "gpasm") -> OverlayManifest:
    """Hook ADC wait path in function_024 for gpsim runs."""

    with tempfile.TemporaryDirectory(prefix="main_adc_hook_") as td:
        td_path = Path(td)
        asm = td_path / "main_adc_hook.asm"
        out_hex = td_path / "main_adc_hook.hex"
        asm.write_text(_MAIN_ADC_BOOT_WAIT_HOOK_ASM, encoding="ascii")
        subprocess.run(
            [gpasm, "-p18f2550", "-o", str(out_hex), str(asm)],
            check=True,
            capture_output=True,
            text=True,
        )
        patch_mem = parse_intel_hex(out_hex)

    return OverlayManifest(
        name="main_adc_boot_wait_hook",
        preconditions={
            0x2D8C: 0xF2,  # function_024 prologue bytes: F2 9E ...
            0x2D8D: 0x9E,
        },
        byte_patches=patch_mem,
        postconditions={
            0x2D8D: 0xEF,
        },
        description="Simulation-only ADC boot-wait bypass hook",
    )


def main_i2c_bypass() -> OverlayManifest:
    """
    Bypass ALL I2C/MSSP and EEPROM polling loops in the MAIN firmware.

    gpsim does not emulate I2C peripherals or EEPROM write timing, so the
    firmware hangs in tight polling loops.  Each btfsc/btfss + bra pair is
    patched to bcf/bsf (satisfy the flag) + nop (skip the branch).

    Covers:
      - SSPCON2 bits SEN/PEN/RSEN/ACKEN (I2C start/stop/restart/ack)
      - PIR1.SSPIF (I2C operation complete)
      - SSPSTAT.BF (I2C buffer full/empty)
      - EECON1.WR (EEPROM write complete)
    """
    # All tight polling loops: (addr, current_hi_byte, patched_hi_byte)
    # btfsc XX -> bcf XX:  0xBx -> 0x9x  (subtract 0x20)
    # btfss XX -> bsf XX:  0xAx -> 0x8x  (subtract 0x20)
    loops = [
        # SSPCON2.SEN (bit 0) polling
        (0x2288, 0xB0, 0x90),
        (0x3870, 0xB0, 0x90),
        (0x4246, 0xB0, 0x90),
        (0x4372, 0xB0, 0x90),
        (0x44EA, 0xB0, 0x90),
        (0x46C0, 0xB0, 0x90),
        # SSPCON2.RSEN (bit 1) polling
        (0x4258, 0xB2, 0x92),
        # SSPCON2.PEN (bit 2) polling
        (0x231A, 0xB4, 0x94),
        (0x389C, 0xB4, 0x94),
        (0x4272, 0xB4, 0x94),
        # SSPCON2.ACKEN (bit 4) polling
        (0x426C, 0xB8, 0x98),
        # PIR1.SSPIF (bit 3) polling — btfss
        (0x3E92, 0xA6, 0x86),
        # SSPSTAT.BF (bit 0) polling — btfsc at 0x3EB8, btfss at 0x466A
        (0x3EB8, 0xB0, 0x90),
        (0x466A, 0xA0, 0x80),
        # EECON1.WR (bit 1) polling
        (0x42D2, 0xB2, 0x92),
        (0x42EC, 0xB2, 0x92),
        (0x43F4, 0xB2, 0x92),
    ]

    # 3-instruction loops: btfss REG,bit / return / bra
    # Pattern: btfss skips return if bit set → loops; if clear → returns.
    # Patch btfss→bcf to force bit clear, then fall through to return.
    # bra becomes dead code but NOP it for safety.
    loops_3instr = [
        # SSPCON2.PEN (bit 2) — btfss/return/bra pattern
        (0x439C, 0xA4, 0x94),  # btfss → bcf; bra at addr+4
        (0x4510, 0xA4, 0x94),
        (0x46D8, 0xA4, 0x94),
    ]

    preconditions = {}
    byte_patches = {}

    # 2-instruction loops: btfsc/btfss + bra
    for addr, old_hi, new_hi in loops:
        preconditions[addr + 1] = old_hi
        preconditions[addr + 3] = 0xD7
        byte_patches[addr + 1] = new_hi
        byte_patches[addr + 2] = 0x00
        byte_patches[addr + 3] = 0x00

    # 3-instruction loops: btfss + return + bra
    for addr, old_hi, new_hi in loops_3instr:
        preconditions[addr + 1] = old_hi
        preconditions[addr + 5] = 0xD7
        byte_patches[addr + 1] = new_hi
        byte_patches[addr + 4] = 0x00
        byte_patches[addr + 5] = 0x00

    return OverlayManifest(
        name="main_i2c_bypass",
        preconditions=preconditions,
        byte_patches=byte_patches,
        description="Simulation-only bypass: all I2C/MSSP/EEPROM polling loops",
    )
