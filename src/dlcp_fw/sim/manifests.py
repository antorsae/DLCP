"""Built-in simulation-only overlay manifests."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

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


def control_disable_standby_check_v16b() -> OverlayManifest:
    """V1.6b standby-jump variant at 0x11DA (goto label_210)."""
    return _control_disable_standby_check_manifest(
        jump_addr=0x11DA,
        goto_word_lo=0x28,
        name="control_disable_standby_check_v16b",
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
    if (
        mem.get(0x11DA, 0xFF) == 0x28
        and mem.get(0x11DB, 0xFF) == 0xEF
        and mem.get(0x11DC, 0xFF) == 0x09
        and mem.get(0x11DD, 0xFF) == 0xF0
    ):
        return control_disable_standby_check_v16b()
    raise RuntimeError(
        "unsupported control standby-jump layout: expected V1.4 site 0x1228, "
        "V1.5b site 0x121A, or V1.6b site 0x11DA"
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
LIST P=18F2455
#include <p18f2455.inc>

; Hook UART helper routines used by serial parser:
; - function_024: ADC wait/boot sequence helper (avoid ADC hang in gpsim)
; - function_079: Timer3 delay (replaced with software shim for gpsim)
; - function_087: read next RX byte
; - function_109: RX available?
; - function_111: TX byte output
; - function_113: MSSP idle wait (with clearable test-stall flag)
;
; Mailbox RAM:
;   0x7C0 RX_RD
;   0x7C1 RX_WR
;   0x7C2 TX_RD
;   0x7C3 TX_WR
;   0x7C4..0x7C8 hook-local scratch / test fault flags
;   0x7C7 bit0: force UART TX helper stall
;   0x7C7 bit1: force MSSP wait helper stall
;   0x740..0x77F TX circular buffer (64 bytes used)
;   0x780..0x7BF RX circular buffer (64 bytes used)
; TXREG is still written for parity with the firmware under test, but gpsim
; write logs are not used as the transport source of truth.

org 0x45FA
sim_function_087:
    movff BSR, 0x7C5
    clrf 0x004, ACCESS
    call sim_function_109
    iorlw 0x00
    bz sim087_done
    lfsr 0, 0x780
    movlb 0x7
    movf 0x0C0, W, BANKED
    andlw 0x3F
    addwf FSR0L, F, ACCESS
    movf INDF0, W, ACCESS
    movwf 0x004, ACCESS
    incf 0x0C0, F, BANKED
sim087_done:
    movf 0x004, W, ACCESS
    movff 0x7C5, BSR
    return 0x0

org 0x4872
sim_function_109:
    movlb 0x7
    movf 0x0C1, W, BANKED
    clrf PRODL, ACCESS
    cpfseq 0x0C0, BANKED
    incf PRODL, F, ACCESS
    movf PRODL, W, ACCESS
    return 0x0

org 0x4896
    goto sim_function_111
org 0x489A
    nop

org 0x48B6
    goto sim_function_113

; gpsim does not advance TMR3IF for this firmware path reliably.
; Replace Timer3 wait routine with a software-equivalent delay shim.
org 0x447E
sim_function_079:
sim79_outer:
    movf 0x004, W, ACCESS
    iorwf 0x003, W, ACCESS
    bz sim79_done
    decf 0x003, F, ACCESS
    movf 0x003, W, ACCESS
    xorlw 0xFF
    bnz sim79_outer
    decf 0x004, F, ACCESS
    bra sim79_outer

sim79_done:
    return 0x0

org 0x4492
sim_function_113:
    movff BSR, 0x7C6
sim113_poll:
    movlb 0x7
    btfsc 0x0C7, 1, BANKED
    bra sim113_poll
    movf SSPCON2, W, ACCESS
    andlw 0x1F
    bnz sim113_poll
    btfsc SSPSTAT, R, ACCESS
    bra sim113_poll
    movff 0x7C6, BSR
    retlw 0x1F

org 0x2D8C
sim_function_024:
    bcf INTCON, GIE, ACCESS
    bcf LATB, LATB2, ACCESS
    movlb 0x0
    movlw 0x37
    movwf 0x88, BANKED
    movlw 0x02
    movwf 0x89, BANKED
    goto 0x2DC8

org 0x2D9E
sim_function_111:
    movff BSR, 0x7C6
    movwf PRODL, ACCESS
sim111_poll:
    movlb 0x7
    btfsc 0x0C7, 0, BANKED
    bra sim111_poll
    lfsr 0, 0x740
    movf 0x0C3, W, BANKED
    andlw 0x3F
    addwf FSR0L, F, ACCESS
    movf PRODL, W, ACCESS
    movwf INDF0, ACCESS
    incf 0x0C3, F, BANKED
    movff PRODL, TXREG
    movff 0x7C6, BSR
    return 0x0

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
            [gpasm, "-p18f2455", "-o", str(out_hex), str(asm)],
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
        },
        byte_patches=patch_mem,
        postconditions={},
        description="Simulation-only main UART hooks: RAM mailbox RX/TX",
    )


def _build_dynamic_mailbox_asm(symbols: dict[str, int]) -> str:
    """Template the mailbox hook overlay ASM using symbol addresses."""
    rx_ring_read = symbols["rx_ring_read"]
    rx_ring_has_data = symbols["rx_ring_has_data"]
    uart_tx = symbols["uart_tx_byte_blocking"]
    i2c_wait = symbols["i2c_wait_bus_idle"]
    timer3 = symbols["timer3_blocking_delay"]
    adc_gate = symbols["adc_boot_gate"]
    adc_exit = symbols["adc_boot_gate_exit"]
    # sim_function_111 is placed after the 18-byte ADC hook (adc_gate + 0x12)
    tx_body = adc_gate + 0x12
    # sim_function_113 is placed after the 20-byte Timer3 shim (timer3 + 0x14)
    mssp_body = timer3 + 0x14

    return f"""\
LIST P=18F2455
#include <p18f2455.inc>

; Dynamic mailbox hook overlay (shifted addresses from V3.0 symbol table)

org 0x{rx_ring_read:04X}
sim_function_087:
    movff BSR, 0x7C5
    clrf 0x004, ACCESS
    call sim_function_109
    iorlw 0x00
    bz sim087_done
    lfsr 0, 0x780
    movlb 0x7
    movf 0x0C0, W, BANKED
    andlw 0x3F
    addwf FSR0L, F, ACCESS
    movf INDF0, W, ACCESS
    movwf 0x004, ACCESS
    incf 0x0C0, F, BANKED
sim087_done:
    movf 0x004, W, ACCESS
    movff 0x7C5, BSR
    return 0x0

org 0x{rx_ring_has_data:04X}
sim_function_109:
    movlb 0x7
    movf 0x0C1, W, BANKED
    clrf PRODL, ACCESS
    cpfseq 0x0C0, BANKED
    incf PRODL, F, ACCESS
    movf PRODL, W, ACCESS
    return 0x0

org 0x{uart_tx:04X}
    goto sim_function_111
org 0x{uart_tx + 4:04X}
    nop

org 0x{i2c_wait:04X}
    goto sim_function_113

org 0x{timer3:04X}
sim_function_079:
sim79_outer:
    movf 0x004, W, ACCESS
    iorwf 0x003, W, ACCESS
    bz sim79_done
    decf 0x003, F, ACCESS
    movf 0x003, W, ACCESS
    xorlw 0xFF
    bnz sim79_outer
    decf 0x004, F, ACCESS
    bra sim79_outer
sim79_done:
    return 0x0

org 0x{mssp_body:04X}
sim_function_113:
    movff BSR, 0x7C6
sim113_poll:
    movlb 0x7
    btfsc 0x0C7, 1, BANKED
    bra sim113_poll
    movf SSPCON2, W, ACCESS
    andlw 0x1F
    bnz sim113_poll
    btfsc SSPSTAT, R, ACCESS
    bra sim113_poll
    movff 0x7C6, BSR
    retlw 0x1F

org 0x{adc_gate:04X}
sim_function_024:
    bcf INTCON, GIE, ACCESS
    bcf LATB, LATB2, ACCESS
    movlb 0x0
    movlw 0x37
    movwf 0x88, BANKED
    movlw 0x02
    movwf 0x89, BANKED
    goto 0x{adc_exit:04X}

org 0x{tx_body:04X}
sim_function_111:
    movff BSR, 0x7C6
    movwf PRODL, ACCESS
sim111_poll:
    movlb 0x7
    btfsc 0x0C7, 0, BANKED
    bra sim111_poll
    lfsr 0, 0x740
    movf 0x0C3, W, BANKED
    andlw 0x3F
    addwf FSR0L, F, ACCESS
    movf PRODL, W, ACCESS
    movwf INDF0, ACCESS
    incf 0x0C3, F, BANKED
    movff PRODL, TXREG
    movff 0x7C6, BSR
    return 0x0

end
"""


def main_serial_mailbox_hooks_dynamic(
    symbols: dict[str, int],
    gpasm: str = "gpasm",
) -> OverlayManifest:
    """Build mailbox hook overlay using addresses from a V3.0 symbol table.

    This is the dynamic variant of :func:`main_serial_mailbox_hooks` that
    accepts shifted symbol addresses instead of hardcoding stock V2.3
    addresses.  Used by the relocation shift test.
    """
    asm_text = _build_dynamic_mailbox_asm(symbols)

    with tempfile.TemporaryDirectory(prefix="main_serial_hook_dyn_") as td:
        td_path = Path(td)
        asm = td_path / "main_serial_hook_dyn.asm"
        out_hex = td_path / "main_serial_hook_dyn.hex"
        asm.write_text(asm_text, encoding="ascii")
        subprocess.run(
            [gpasm, "-p18f2455", "-o", str(out_hex), str(asm)],
            check=True,
            capture_output=True,
            text=True,
        )
        patch_mem = parse_intel_hex(out_hex)

    # Precondition bytes are the same instruction encodings at shifted addrs
    adc = symbols["adc_boot_gate"]
    t3 = symbols["timer3_blocking_delay"]
    rx = symbols["rx_ring_read"]
    rxd = symbols["rx_ring_has_data"]
    return OverlayManifest(
        name="main_serial_mailbox_hooks_dynamic",
        preconditions={
            adc: 0xF2,
            adc + 1: 0x9E,
            t3: 0xA0,
            t3 + 1: 0x92,
            t3 + 2: 0x98,
            t3 + 3: 0x0E,
            rx: 0x04,
            rx + 1: 0x6A,
            rxd: 0x00,
            rxd + 1: 0x01,
        },
        byte_patches=patch_mem,
        postconditions={},
        description="Simulation-only UART hooks (dynamic shifted addresses)",
    )


_MAIN_UART_MAILBOX_ONLY_HOOK_ASM = r"""
LIST P=18F2455
#include <p18f2455.inc>

; Hook UART helper routines used by serial parser:
; - function_087: read next RX byte
; - function_109: RX available?
; - function_111: TX byte output
;
; Mailbox RAM:
;   0x7C0 RX_RD
;   0x7C1 RX_WR
;   0x7C2 TX_RD
;   0x7C3 TX_WR
;   0x7C4..0x7C8 hook-local scratch / test fault flags
;   0x7C7 bit0: force UART TX helper stall
;   0x7C7 bit1: force MSSP wait helper stall
;   0x740..0x77F TX circular buffer (64 bytes used)
;   0x780..0x7BF RX circular buffer (64 bytes used)

org 0x45FA
sim_function_087:
    movff BSR, 0x7C5
    clrf 0x004, ACCESS
    call sim_function_109
    iorlw 0x00
    bz sim087_done
    lfsr 0, 0x780
    movlb 0x7
    movf 0x0C0, W, BANKED
    andlw 0x3F
    addwf FSR0L, F, ACCESS
    movf INDF0, W, ACCESS
    movwf 0x004, ACCESS
    incf 0x0C0, F, BANKED
sim087_done:
    movf 0x004, W, ACCESS
    movff 0x7C5, BSR
    return 0x0

org 0x4872
sim_function_109:
    movlb 0x7
    movf 0x0C1, W, BANKED
    clrf PRODL, ACCESS
    cpfseq 0x0C0, BANKED
    incf PRODL, F, ACCESS
    movf PRODL, W, ACCESS
    return 0x0

org 0x4896
    goto sim_function_111
org 0x489A
    nop

; Requires main_adc_boot_wait_hook in the same overlay stack. That companion
; patch redirects function_024 before execution reaches this helper area.
org 0x2D9E
sim_function_111:
    movff BSR, 0x7C6
    movwf PRODL, ACCESS
sim111_poll:
    movlb 0x7
    btfsc 0x0C7, 0, BANKED
    bra sim111_poll
    lfsr 0, 0x740
    movf 0x0C3, W, BANKED
    andlw 0x3F
    addwf FSR0L, F, ACCESS
    movf PRODL, W, ACCESS
    movwf INDF0, ACCESS
    incf 0x0C3, F, BANKED
    movff PRODL, TXREG
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
            [gpasm, "-p18f2455", "-o", str(out_hex), str(asm)],
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
        },
        byte_patches=patch_mem,
        postconditions={},
        description="Simulation-only UART hooks: mailbox-backed RX/TX probes",
    )


_MAIN_V25_TIMEOUT_TEST_HOOK_ASM = r"""
LIST P=18F2455
#include <p18f2455.inc>

; V2.5 MAIN simulation-only timeout test hook.
;
; Access-bank bytes 0x04E / 0x04F hold the timeout high-byte seed used by the
; intercepted helpers:
;   0x04E: UART wait helper (patch_wait_trmt_c)
;   0x04F: MSSP wait helper (patch_wait_mssp_idle_c)
; Tests write 0x10 for the normal V2.5 budget or 0x00 to force an immediate
; timeout on the next helper call.
;
; The high-level V2.5 wrapper/recovery/reset code remains untouched.
; Only the low-level wait helper entries are intercepted so tests can trigger
; the real timeout/recovery paths on demand without overwriting the V2.5 patch
; bodies that already live at 0x5500 and 0x556E.  Helper stubs must stay within
; the valid 24 KiB PIC18F2455 flash range (< 0x6000).

org 0x5500
    clrf 0x0B, ACCESS
    goto sim_patch_wait_trmt_entry

org 0x556E
    clrf 0x0B, ACCESS
    goto sim_patch_wait_mssp_entry

org 0x53F8
sim_patch_wait_trmt_entry:
    movf 0x04E, W, ACCESS
    goto 0x5506

org 0x54BA
sim_patch_wait_mssp_entry:
    movf 0x04F, W, ACCESS
    goto 0x5574

end
"""


_MAIN_V24_STALL_TEST_HOOK_ASM = r"""
LIST P=18F2455
#include <p18f2455.inc>

; V2.4/stock MAIN simulation-only helper stall hook.
;
; Access-bank bytes 0x04E / 0x04F act as clearable helper gates:
;   0x04E: UART wait helper (function_111)
;   0x04F: MSSP wait helper (function_113)
;
; Non-zero = run the displaced stock helper prologue and continue.
; Zero     = stay inside the helper until the seed byte is restored.
;
; This does not add any recovery logic. It only creates a clearable native-ring
; stall so tests can compare stock/V2.4 behavior against the real V2.5 timeout
; wrappers under the same control-side scenario.

org 0x4896
    goto sim_v24_uart_entry

org 0x48B6
    goto sim_v24_mssp_entry

org 0x53F8
sim_v24_uart_entry:
    movwf 0x0B, ACCESS
sim_v24_uart_wait:
    movf 0x04E, W, ACCESS
    bnz sim_v24_uart_continue
    bra sim_v24_uart_wait
sim_v24_uart_continue:
    movf 0x0B, W, ACCESS
    movff WREG, 0x003
    goto 0x489A

org 0x54BA
sim_v24_mssp_entry:
sim_v24_mssp_wait:
    movf 0x04F, W, ACCESS
    bnz sim_v24_mssp_continue
    bra sim_v24_mssp_wait
sim_v24_mssp_continue:
    movff SSPCON2, 0x003
    goto 0x48BA

end
"""


def main_v24_stall_test_hooks(gpasm: str = "gpasm") -> OverlayManifest:
    """Build simulation-only runtime stall hooks for stock/V2.4 MAIN wait helpers."""

    with tempfile.TemporaryDirectory(prefix="main_v24_stall_hook_") as td:
        td_path = Path(td)
        asm = td_path / "main_v24_stall_hook.asm"
        out_hex = td_path / "main_v24_stall_hook.hex"
        asm.write_text(_MAIN_V24_STALL_TEST_HOOK_ASM, encoding="ascii")
        subprocess.run(
            [gpasm, "-p18f2455", "-o", str(out_hex), str(asm)],
            check=True,
            capture_output=True,
            text=True,
        )
        patch_mem = parse_intel_hex(out_hex)

    return OverlayManifest(
        name="main_v24_stall_test_hooks",
        preconditions={
            0x4896: 0xE8,
            0x4897: 0xCF,
            0x4898: 0x03,
            0x4899: 0xF0,
            0x48B6: 0xC5,
            0x48B7: 0xCF,
            0x48B8: 0x03,
            0x48B9: 0xF0,
            0x53F8: 0xFF,
            0x53F9: 0xFF,
            0x53FA: 0xFF,
            0x53FB: 0xFF,
            0x53FC: 0xFF,
            0x53FD: 0xFF,
            0x53FE: 0xFF,
            0x53FF: 0xFF,
            0x54BA: 0xFF,
            0x54BB: 0xFF,
            0x54BC: 0xFF,
            0x54BD: 0xFF,
            0x54BE: 0xFF,
            0x54BF: 0xFF,
        },
        byte_patches=patch_mem,
        postconditions={},
        description="Simulation-only MAIN V2.4 stall hook via access-bank seed bytes at 0x04E/0x04F",
    )


def main_v25_timeout_test_hooks(gpasm: str = "gpasm") -> OverlayManifest:
    """Build simulation-only runtime timeout hooks for MAIN V2.5 wait helpers."""

    with tempfile.TemporaryDirectory(prefix="main_v25_timeout_hook_") as td:
        td_path = Path(td)
        asm = td_path / "main_v25_timeout_hook.asm"
        out_hex = td_path / "main_v25_timeout_hook.hex"
        asm.write_text(_MAIN_V25_TIMEOUT_TEST_HOOK_ASM, encoding="ascii")
        subprocess.run(
            [gpasm, "-p18f2455", "-o", str(out_hex), str(asm)],
            check=True,
            capture_output=True,
            text=True,
        )
        patch_mem = parse_intel_hex(out_hex)

    return OverlayManifest(
        name="main_v25_timeout_test_hooks",
        preconditions={
            0x5500: 0x00,
            0x5501: 0x0E,
            0x5502: 0x0B,
            0x5503: 0x6E,
            0x5504: 0x10,
            0x5505: 0x0E,
            0x5506: 0x0C,
            0x5507: 0x6E,
            0x556E: 0x00,
            0x556F: 0x0E,
            0x5570: 0x0B,
            0x5571: 0x6E,
            0x5572: 0x10,
            0x5573: 0x0E,
            0x5574: 0x0C,
            0x5575: 0x6E,
            0x53F8: 0xFF,
            0x53F9: 0xFF,
            0x53FA: 0xFF,
            0x53FB: 0xFF,
            0x53FC: 0xFF,
            0x53FD: 0xFF,
            0x53FE: 0xFF,
            0x53FF: 0xFF,
            0x54BA: 0xFF,
            0x54BB: 0xFF,
            0x54BC: 0xFF,
            0x54BD: 0xFF,
            0x54BE: 0xFF,
            0x54BF: 0xFF,
        },
        byte_patches=patch_mem,
        postconditions={},
        description="Simulation-only MAIN V2.5 timeout trigger hook via access-bank seed bytes at 0x04E/0x04F",
    )


_MAIN_ADC_BOOT_WAIT_HOOK_ASM = r"""
LIST P=18F2455
#include <p18f2455.inc>

; gpsim does not resolve ADCON0.GO completion for this firmware boot path.
; Hook function_024 to bypass ADC wait loops while preserving side effects.

org 0x2D8C
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
            [gpasm, "-p18f2455", "-o", str(out_hex), str(asm)],
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
        postconditions={},
        description="Simulation-only ADC boot-wait bypass hook",
    )


def _build_main_poll_bypass(
    *,
    name: str,
    description: str,
    loops: Sequence[tuple[int, int, int]],
    loops_3instr: Sequence[tuple[int, int, int]] = (),
) -> OverlayManifest:
    preconditions: dict[int, int] = {}
    byte_patches: dict[int, int] = {}

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
        name=name,
        preconditions=preconditions,
        byte_patches=byte_patches,
        description=description,
    )


def main_external_i2c_bypass() -> OverlayManifest:
    """
    Bypass only external MSSP/I2C polling loops in the MAIN firmware.

    This is a simulator workaround for runs that do not attach a real external
    I2C bus/slave model. It intentionally does not touch internal PIC EEPROM
    write-complete polling (`EECON1.WR`).
    """
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
    ]
    loops_3instr = [
        # SSPCON2.PEN (bit 2) — btfss/return/bra pattern
        (0x439C, 0xA4, 0x94),
        (0x4510, 0xA4, 0x94),
        (0x46D8, 0xA4, 0x94),
    ]
    return _build_main_poll_bypass(
        name="main_external_i2c_bypass",
        description="Simulation-only bypass: external MSSP/I2C polling loops",
        loops=loops,
        loops_3instr=loops_3instr,
    )


def main_internal_eeprom_bypass() -> OverlayManifest:
    """
    Bypass only internal PIC EEPROM/flash write-complete polling loops.

    This exists as a temporary compatibility overlay. gpsim now handles the
    normal `EECON1.WR` completion path used by MAIN tests, so new fidelity
    tests should avoid this overlay.
    """
    loops = [
        (0x42D2, 0xB2, 0x92),
        (0x42EC, 0xB2, 0x92),
        (0x43F4, 0xB2, 0x92),
    ]
    return _build_main_poll_bypass(
        name="main_internal_eeprom_bypass",
        description="Simulation-only bypass: internal EEPROM/flash write polling loops",
        loops=loops,
    )


def main_i2c_bypass() -> OverlayManifest:
    """
    Legacy compatibility overlay for the old blanket MAIN I2C bypass.

    Prefer `main_external_i2c_bypass()` for external-bus gaps and avoid
    bypassing `EECON1.WR` unless a targeted regression proves it is required.
    """
    combined = _build_main_poll_bypass(
        name="main_i2c_bypass",
        description="Simulation-only bypass: all I2C/MSSP/EEPROM polling loops",
        loops=[
            # External MSSP/I2C
            (0x2288, 0xB0, 0x90),
            (0x3870, 0xB0, 0x90),
            (0x4246, 0xB0, 0x90),
            (0x4372, 0xB0, 0x90),
            (0x44EA, 0xB0, 0x90),
            (0x46C0, 0xB0, 0x90),
            (0x4258, 0xB2, 0x92),
            (0x231A, 0xB4, 0x94),
            (0x389C, 0xB4, 0x94),
            (0x4272, 0xB4, 0x94),
            (0x426C, 0xB8, 0x98),
            (0x3E92, 0xA6, 0x86),
            (0x3EB8, 0xB0, 0x90),
            (0x466A, 0xA0, 0x80),
            # Internal EEPROM/flash write-complete polling
            (0x42D2, 0xB2, 0x92),
            (0x42EC, 0xB2, 0x92),
            (0x43F4, 0xB2, 0x92),
        ],
        loops_3instr=[
            (0x439C, 0xA4, 0x94),
            (0x4510, 0xA4, 0x94),
            (0x46D8, 0xA4, 0x94),
        ],
    )
    return combined
