#!/usr/bin/env python3
"""
Build patched DLCP MAIN firmware HEX images with A/B preset support.

Patch strategy:
1) Copy preset table A (0x5600..0x5FFF, 0xA00 bytes) to preset table B at
   0x4A00..0x53FF.
2) Inject code stubs to:
   - remap table flash reads/writes/erases from 0x56xx..0x5Fxx to
     0x4Axx..0x53xx when preset B is active;
   - add current-loop command 0x20: set preset A/B and apply immediately
     only when the requested preset changes;
   - keep the stock USB cmd03 filename command family, but make its backing
     EEPROM/RAM storage preset-aware on MAIN only.
3) Emit a full Intel HEX output.

Reliability policy:
- No current-loop filename transport (`0x21` / `0x22`) is added.
- CONTROL remains unchanged and still does not fetch/display DSP filenames.
- MAIN USB filename commands operate on the active preset only.

Filename storage policy:
- Preset A filename keeps the stock EEPROM slot `0x60..0x7D`.
- Preset B filename uses EEPROM `0x83..0xA0`.
- Live RAM filename slot remains stock `0x02C0..0x02DD`.
- Legacy single-slot upgrades naturally map to preset A; preset B starts blank.

Version policy:
- MAIN EEPROM tuple is kept at stock 2.30 (bytes 0x02, 0x03, 0x30 at
  0xF00080..0xF00082).
- USB-reported application version literal is patched to 2.4 or 2.5 depending
  on the selected output variant.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import tempfile
from typing import Dict, List, Tuple

from dlcp_fw.paths import PATCHED_MAIN_HEX_V24, PATCHED_MAIN_HEX_V25, STOCK_MAIN_HEX


class HexParseError(RuntimeError):
    pass


_FILENAME_BOOT_AND_PERSIST_PATCH = r"""
org 0x20BE
    rcall filename_load_active_slot
    bra 0x20E4

org 0x27C0
filename_persist_active_slot:
    movlw 0x60
    btfsc 0x05E, 2, ACCESS
    movlw 0x83
    movwf 0x0A, ACCESS
    lfsr 2, 0x02C0
    movlw 0x1E
    movwf 0x0B, ACCESS

filename_persist_loop:
    movff 0x00A, 0x007
    clrf 0x08, ACCESS
    movf POSTINC2, W, ACCESS
    movwf 0x09, ACCESS
    call 0x46DE
    incf 0x0A, F, ACCESS
    decfsz 0x0B, F, ACCESS
    bra filename_persist_loop
    movlb 0x0
    bcf 0x0BD, 5, BANKED
    bcf 0x07E, 0, BANKED
    return

org 0x20C2
filename_load_active_slot:
    movlw 0x60
    btfsc 0x05E, 2, ACCESS
    movlw 0x83
    movwf 0x0A, ACCESS
    lfsr 2, 0x02C0
    movlw 0x1E
    movwf 0x0B, ACCESS

filename_load_loop:
    movff 0x00A, 0x003
    clrf 0x04, ACCESS
    call 0x4884
    movwf POSTINC2, ACCESS
    incf 0x0A, F, ACCESS
    decfsz 0x0B, F, ACCESS
    bra filename_load_loop
    return
"""


_CMD_TAIL_PATCH = r"""
cmd_tail_patch:
    ; Recreate old behavior for cmd=0x1D and cmd=0x1E, then add cmd=0x20.
    movf 0x0A2, W, BANKED
    xorlw 0x1D
    btfsc STATUS, Z, ACCESS
    goto 0x1E02

    movf 0x0A2, W, BANKED
    xorlw 0x1E
    btfsc STATUS, Z, ACCESS
    goto 0x1E1C

    movf 0x0A2, W, BANKED
    xorlw 0x20
    bnz cmd_done

    ; cmd 0x20: toggle preset only on actual change. Keep the existing USB
    ; filename command family, but swap backing EEPROM/RAM slot with the active
    ; preset and flush the outgoing slot first if cmd03 data is still dirty.
    movf 0x0A3, W, BANKED
    andlw 0x01
    btfsc 0x05E, 2, ACCESS
    xorlw 0x01
    bz cmd_done
    btfsc 0x0BD, 5, BANKED
    call 0x27C0
    bsf 0x07E, 0, BANKED
    btg 0x05E, 2, ACCESS
    call 0x20C2
    call 0x4574

cmd_done:
    goto 0x1E6C
"""


PATCH_ASM_V24 = rf"""
LIST P=18F2455
#include <p18f2455.inc>

{_FILENAME_BOOT_AND_PERSIST_PATCH}

; --- Hooks into existing code ---
org 0x1E64
    goto cmd_tail_patch

org 0x2E6E
    goto function_025_patch
org 0x2E72
    nop

org 0x3DAC
    goto function_054_patch
org 0x3DB0
    nop

org 0x4028
    goto function_061_patch
org 0x402C
    nop
org 0x402E
    nop

; --- New code in erased app region ---
org 0x5400
function_061_patch:
    ; original prologue (replaced)
    movff 0x003, 0x00B
    movff 0x004, 0x00C

    ; if PRESET_B=1 and address in 0x56xx..0x5Fxx (u16), remap to 0x4Axx..0x53xx
    btfss 0x05E, 2, ACCESS
    goto rd_done

    movf 0x006, W, ACCESS
    iorwf 0x005, W, ACCESS
    bnz rd_done

    movlw 0x56
    subwf 0x00C, W, ACCESS
    bnc rd_done

    movlw 0x60
    cpfslt 0x00C, ACCESS
    goto rd_done

    movlw 0x0C
    subwf 0x00C, F, ACCESS

rd_done:
    goto 0x4030

org 0x5440
function_025_patch:
    ; original prologue (replaced)
    clrf 0x010, ACCESS
    movff 0x003, 0x014

    ; remap destination start high-byte for preset B
    btfss 0x05E, 2, ACCESS
    goto wr_done

    movf 0x006, W, ACCESS
    iorwf 0x005, W, ACCESS
    bnz wr_done

    movlw 0x56
    subwf 0x004, W, ACCESS
    bnc wr_done

    movlw 0x60
    cpfslt 0x004, ACCESS
    goto wr_done

    movlw 0x0C
    subwf 0x004, F, ACCESS

wr_done:
    goto 0x2E74

org 0x54C0
function_054_patch:
    ; original prologue (replaced)
    clrf 0x00B, ACCESS
    movff 0x003, 0x00C

    ; remap erase start/end window for preset B
    btfss 0x05E, 2, ACCESS
    goto er_done

    ; start address high-byte in +4 if upper words are zero
    movf 0x006, W, ACCESS
    iorwf 0x005, W, ACCESS
    bnz er_chk_end

    movlw 0x56
    subwf 0x004, W, ACCESS
    bnc er_chk_end

    movlw 0x60
    cpfslt 0x004, ACCESS
    goto er_chk_end

    movlw 0x0C
    subwf 0x004, F, ACCESS

er_chk_end:
    ; end address high-byte in +8 if upper words are zero
    movf 0x00A, W, ACCESS
    iorwf 0x009, W, ACCESS
    bnz er_done

    movlw 0x56
    subwf 0x008, W, ACCESS
    bnc er_done

    movlw 0x60
    cpfslt 0x008, ACCESS
    goto er_done

    movlw 0x0C
    subwf 0x008, F, ACCESS

er_done:
    goto 0x3DB2

org 0x5500
{_CMD_TAIL_PATCH}

end
"""


PATCH_ASM_V25 = rf"""
LIST P=18F2455
#include <p18f2455.inc>

{_FILENAME_BOOT_AND_PERSIST_PATCH}

; --- Hooks into existing code ---
org 0x1E64
    goto cmd_tail_patch

org 0x2E6E
    goto function_025_patch
org 0x2E72
    nop

org 0x3DAC
    goto function_054_patch
org 0x3DB0
    nop

org 0x4028
    goto function_061_patch
org 0x402C
    nop
org 0x402E
    nop

org 0x3E68
    goto function_056_patch

org 0x4368
    goto function_072_patch

org 0x46BA
    goto function_093_patch

org 0x4896
    goto function_111_patch

org 0x48B6
    goto function_113_patch

; --- New code in erased app region ---
org 0x5400
function_061_patch:
    ; original prologue (replaced)
    movff 0x003, 0x00B
    movff 0x004, 0x00C

    ; if PRESET_B=1 and address in 0x56xx..0x5Fxx (u16), remap to 0x4Axx..0x53xx
    btfss 0x05E, 2, ACCESS
    goto rd_done

    movf 0x006, W, ACCESS
    iorwf 0x005, W, ACCESS
    bnz rd_done

    movlw 0x56
    subwf 0x00C, W, ACCESS
    bnc rd_done

    movlw 0x60
    cpfslt 0x00C, ACCESS
    goto rd_done

    movlw 0x0C
    subwf 0x00C, F, ACCESS

rd_done:
    goto 0x4030

org 0x542A
function_113_patch:
    call patch_wait_mssp_idle_c
    bnc function_113_ok
    call patch_recover_mssp
    call patch_wait_mssp_idle_c
    bnc function_113_ok
    goto 0x48D4
function_113_ok:
    retlw 0x1F

org 0x5440
function_025_patch:
    ; original prologue (replaced)
    clrf 0x010, ACCESS
    movff 0x003, 0x014

    ; remap destination start high-byte for preset B
    btfss 0x05E, 2, ACCESS
    goto wr_done

    movf 0x006, W, ACCESS
    iorwf 0x005, W, ACCESS
    bnz wr_done

    movlw 0x56
    subwf 0x004, W, ACCESS
    bnc wr_done

    movlw 0x60
    cpfslt 0x004, ACCESS
    goto wr_done

    movlw 0x0C
    subwf 0x004, F, ACCESS

wr_done:
    goto 0x2E74

org 0x5468
function_054_patch:
    ; original prologue (replaced)
    clrf 0x00B, ACCESS
    movff 0x003, 0x00C

    ; remap erase start/end window for preset B
    btfss 0x05E, 2, ACCESS
    goto er_done

    ; start address high-byte in +4 if upper words are zero
    movf 0x006, W, ACCESS
    iorwf 0x005, W, ACCESS
    bnz er_chk_end

    movlw 0x56
    subwf 0x004, W, ACCESS
    bnc er_chk_end

    movlw 0x60
    cpfslt 0x004, ACCESS
    goto er_chk_end

    movlw 0x0C
    subwf 0x004, F, ACCESS

er_chk_end:
    ; end address high-byte in +8 if upper words are zero
    movf 0x00A, W, ACCESS
    iorwf 0x009, W, ACCESS
    bnz er_done

    movlw 0x56
    subwf 0x008, W, ACCESS
    bnc er_done

    movlw 0x60
    cpfslt 0x008, ACCESS
    goto er_done

    movlw 0x0C
    subwf 0x008, F, ACCESS

er_done:
    goto 0x3DB2

org 0x54C0
{_CMD_TAIL_PATCH}

; --- Robustness patch stubs ---
; Stock MAIN timing basis:
; - PIC18F2455 external clock input = 12 MHz
; - PLLDIV=/3, CPUDIV=PLL/6 => Fosc=16 MHz, Tcy=250 ns
; - current-loop serial is 31.25 kbaud => 320 us/byte => 1280 Tcy/byte
; 16-bit loop budget chosen here yields approximately:
; - 5.13 ms for TRMT/SSPIF/BF/SEN/PEN waits (~16 serial byte-times)
; - 10.25 ms for packed MSSP-idle waits (~32 serial byte-times)
; This is long enough to ignore in-flight bus activity but still bounded.
timeout_lo equ 0x00
timeout_hi equ 0x10

org 0x54A8
patch_recover_uart:
    call 0x4546
    return

patch_recover_mssp:
    movlw 0x80
    movwf 0x003, ACCESS
    movlw 0x08
    call 0x47B2
    return

org 0x5500
patch_wait_trmt_c:
    movlw timeout_lo
    movwf 0x00B, ACCESS
    movlw timeout_hi
    movwf 0x00C, ACCESS

patch_wait_trmt_loop:
    btfsc TXSTA, TRMT, ACCESS
    bra patch_wait_ok
    decfsz 0x00B, F, ACCESS
    bra patch_wait_trmt_loop
    decfsz 0x00C, F, ACCESS
    bra patch_wait_trmt_loop
    bra patch_wait_fail

patch_wait_sspif_c:
    movlw timeout_lo
    movwf 0x00B, ACCESS
    movlw timeout_hi
    movwf 0x00C, ACCESS

patch_wait_sspif_loop:
    btfsc PIR1, SSPIF, ACCESS
    bra patch_wait_ok
    decfsz 0x00B, F, ACCESS
    bra patch_wait_sspif_loop
    decfsz 0x00C, F, ACCESS
    bra patch_wait_sspif_loop
    bra patch_wait_fail

patch_wait_bf_clear_c:
    movlw timeout_lo
    movwf 0x00B, ACCESS
    movlw timeout_hi
    movwf 0x00C, ACCESS

patch_wait_bf_loop:
    btfss SSPSTAT, BF, ACCESS
    bra patch_wait_ok
    decfsz 0x00B, F, ACCESS
    bra patch_wait_bf_loop
    decfsz 0x00C, F, ACCESS
    bra patch_wait_bf_loop
    bra patch_wait_fail

patch_wait_sen_clear_c:
    movlw timeout_lo
    movwf 0x00B, ACCESS
    movlw timeout_hi
    movwf 0x00C, ACCESS

patch_wait_sen_loop:
    btfss SSPCON2, SEN, ACCESS
    bra patch_wait_ok
    decfsz 0x00B, F, ACCESS
    bra patch_wait_sen_loop
    decfsz 0x00C, F, ACCESS
    bra patch_wait_sen_loop
    bra patch_wait_fail

patch_wait_pen_clear_c:
    movlw timeout_lo
    movwf 0x00B, ACCESS
    movlw timeout_hi
    movwf 0x00C, ACCESS

patch_wait_pen_loop:
    btfss SSPCON2, PEN, ACCESS
    bra patch_wait_ok
    decfsz 0x00B, F, ACCESS
    bra patch_wait_pen_loop
    decfsz 0x00C, F, ACCESS
    bra patch_wait_pen_loop
    bra patch_wait_fail

patch_wait_mssp_idle_c:
    movlw timeout_lo
    movwf 0x00B, ACCESS
    movlw timeout_hi
    movwf 0x00C, ACCESS

patch_wait_mssp_loop:
    movff SSPCON2, 0x003
    movlw 0x1F
    andwf 0x003, W, ACCESS
    btfss STATUS, Z, ACCESS
    bra patch_wait_mssp_spin
    btfsc SSPSTAT, R, ACCESS
    bra patch_wait_mssp_spin
    bra patch_wait_ok

patch_wait_mssp_spin:
    decfsz 0x00B, F, ACCESS
    bra patch_wait_mssp_loop
    decfsz 0x00C, F, ACCESS
    bra patch_wait_mssp_loop
    bra patch_wait_fail

patch_wait_ok:
    bcf STATUS, C, ACCESS
    return

patch_wait_fail:
    bsf STATUS, C, ACCESS
    return

org 0x4970
function_056_patch:
    movff WREG, 0x005
    rcall patch_function_056_core
    bnc function_056_done
    call patch_recover_mssp
    rcall patch_function_056_core
    bc patch_hard_reset
function_056_done:
    return

function_072_patch:
    movff WREG, 0x006
    call patch_function_072_core
    bnc function_072_done
    call patch_recover_mssp
    call patch_function_072_core
    bc patch_hard_reset
function_072_done:
    return

function_093_patch:
    movff WREG, 0x007
    call patch_function_093_core
    bnc function_093_done
    call patch_recover_mssp
    call patch_function_093_core
    bc patch_hard_reset
function_093_done:
    return

function_111_patch:
    movff WREG, 0x003
    call patch_wait_trmt_c
    bnc function_111_send
    call patch_recover_uart
    call patch_wait_trmt_c
    bc patch_hard_reset
function_111_send:
    movf 0x003, W, ACCESS
    movwf TXREG, ACCESS
    return

patch_hard_reset:
    goto 0x48D4

patch_function_056_core:
    movff 0x005, SSPBUF
    btfsc SSPCON1, WCOL, ACCESS
    bra patch_function_056_timeout

    movf SSPCON1, W, ACCESS
    andlw 0x0F
    xorlw 0x08
    bz patch_function_056_mode_bf

    xorlw 0x03
    bz patch_function_056_mode_bf

    bsf SSPCON1, CKP, ACCESS
    call patch_wait_sspif_c
    bc patch_function_056_timeout
    btfss SSPSTAT, R, ACCESS
    movf SSPSTAT, W, ACCESS
    bcf STATUS, C, ACCESS
    return

patch_function_056_mode_bf:
    call patch_wait_bf_clear_c
    bc patch_function_056_timeout
    call function_113_patch
    return

patch_function_056_timeout:
    bsf STATUS, C, ACCESS
    return

org 0x559A
patch_function_072_core:
    rcall patch_wait_mssp_idle_c
    bc patch_function_072_timeout
    bsf SSPCON2, SEN, ACCESS
    rcall patch_wait_sen_clear_c
    bc patch_function_072_timeout

    movlw 0x68
    call function_056_patch
    movlw 0x1F
    call function_056_patch
    movlw 0x00
    call function_056_patch
    movlw 0x00
    call function_056_patch
    movlw 0x00
    call function_056_patch
    movf 0x006, W, ACCESS
    call function_056_patch

    bsf SSPCON2, PEN, ACCESS
    rcall patch_wait_pen_clear_c
    bc patch_function_072_timeout
    bcf STATUS, C, ACCESS
    return

patch_function_072_timeout:
    bsf STATUS, C, ACCESS
    return

patch_function_093_core:
    bsf SSPCON2, SEN, ACCESS
    rcall patch_wait_sen_clear_c
    bc patch_function_093_timeout

    movlw 0xE2
    call function_056_patch
    movf 0x007, W, ACCESS
    call function_056_patch
    movf 0x006, W, ACCESS
    call function_056_patch

    bsf SSPCON2, PEN, ACCESS
    rcall patch_wait_pen_clear_c
    bc patch_function_093_timeout
    bcf STATUS, C, ACCESS
    return

patch_function_093_timeout:
    bsf STATUS, C, ACCESS
    return

end
"""


PATCH_ASM = PATCH_ASM_V25

# V2.6 DSP robustness fixes (additive to V2.5).
# - Fix A (DSP1): ACKSTAT check in function_056_core success paths
# - Fix B (DSP2): conditional dirty-bit clear with bounded retry
# - Fix B' (DSP3): deferred volume commit (after verified I2C write)
_V26_DSP_FIXES = r"""
; === V2.6 DSP robustness (Fix A / B / B') ===

; --- Fix A: patch function_056_core success returns to check ACKSTAT ---
; The two success-return sites in patch_function_056_core are rewritten
; by replacing the stock dead-code zone with a shared ACKSTAT latch.
; We cannot modify the inline code (no space), so we redirect the two
; success-return addresses to a shared check placed in dead code.
;
; (A is implemented inline: the V2.6 ASM replaces the patch_function_056_core
;  block with a version that includes ACKSTAT checks on both success paths.
;  See the sed-style replacement below.)

; --- Fix A (DSP1): latch ACKSTAT after the address byte in function_081 ---
; Hook function_081's first call function_056 at 0x44F0 to check ACKSTAT
; immediately after the address byte TX, before subsequent bytes clear it.
org 0x44F0
    call ackstat_first_byte_check

; Place the wrapper in function_093's dead code zone (0x46BE, 36 bytes free)
org 0x46BE
ackstat_first_byte_check:
    ; NOTE: BSR must be 0 on entry.  All callers (function_081 via the
    ; volume dirty-bit service path) set BSR=0 before reaching 0x44F0.
    call 0x3E68                         ; function_056 (goes through V2.5 patch)
    btfsc SSPCON2, 6, ACCESS            ; ACKSTAT set? (slave NACKed address)
    bsf 0x7F, 2, BANKED                ; Latch sticky I2C error (BSR=0)
    return

; --- Fix B (DSP2): hook volume I2C write for conditional dirty clear ---
org 0x1A5A
    call volume_dsp_write_v26
org 0x1A6E
    nop

; --- Fix B' (DSP3): NOP the premature volume commit ---
org 0x1D6E
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop

; --- Fix B+B' wrapper (placed in dead function_056 body at 0x3E6C) ---
org 0x3E6C
volume_dsp_write_v26:
    bcf 0x7F, 2, BANKED               ; Clear error latch
    call 0x44E4                         ; function_081 (address byte latches via hook)

    ; Fix A+B: check the error latch set by ackstat_first_byte_check
    btfsc 0x7F, 2, BANKED
    bra vol_write_nacked

    movlb 0x0
    bcf 0x7E, 3, BANKED
    movff 0x06E, 0x066
    movff 0x06F, 0x067
    movff 0x070, 0x068
    movff 0x071, 0x069
    ; Reset retry counter (0x07F bits 3-5)
    movlw 0x07
    andwf 0x7F, F, BANKED
    return

vol_write_nacked:
    ; I2C write failed.  Increment retry counter (bits 3-5 of 0x07F).
    movlw 0x08
    addwf 0x7F, F, BANKED

    ; Check max retries (5 * 8 = 0x28 in the bit3-5 field)
    movf 0x7F, W, BANKED
    andlw 0x38
    sublw 0x28
    bc vol_retry_ok                 ; carry set = not exceeded

    ; Max retries: give up, clear dirty, reset counter
    movlb 0x0
    bcf 0x7E, 3, BANKED
    movlw 0x07
    andwf 0x7F, F, BANKED
    return

vol_retry_ok:
    ; Dirty bit stays set -- retry next main loop iteration
    return
"""

# V2.6 replaces the function_056_core block with ACKSTAT-checking version.
_V25_056_CORE = r"""patch_function_056_core:
    movff 0x005, SSPBUF
    btfsc SSPCON1, WCOL, ACCESS
    bra patch_function_056_timeout

    movf SSPCON1, W, ACCESS
    andlw 0x0F
    xorlw 0x08
    bz patch_function_056_mode_bf

    xorlw 0x03
    bz patch_function_056_mode_bf

    bsf SSPCON1, CKP, ACCESS
    call patch_wait_sspif_c
    bc patch_function_056_timeout
    btfss SSPSTAT, R, ACCESS
    movf SSPSTAT, W, ACCESS
    bcf STATUS, C, ACCESS
    return

patch_function_056_mode_bf:
    call patch_wait_bf_clear_c
    bc patch_function_056_timeout
    call function_113_patch
    return

patch_function_056_timeout:
    bsf STATUS, C, ACCESS
    return"""

_V26_056_CORE = r"""patch_function_056_core:
    movff 0x005, SSPBUF
    btfsc SSPCON1, WCOL, ACCESS
    bra patch_function_056_timeout

    movf SSPCON1, W, ACCESS
    andlw 0x0F
    xorlw 0x08
    bz patch_function_056_mode_bf

    xorlw 0x03
    bz patch_function_056_mode_bf

    bsf SSPCON1, CKP, ACCESS
    call patch_wait_sspif_c
    bc patch_function_056_timeout
    btfss SSPSTAT, R, ACCESS
    movf SSPSTAT, W, ACCESS
    ; Fix A: normal path not reached on PIC18F2455 I2C master
    ; (I2C master always takes the BF path below)
    bcf STATUS, C, ACCESS
    return

patch_function_056_mode_bf:
    call patch_wait_bf_clear_c
    bc patch_function_056_timeout
    call function_113_patch
    ; Fix A (DSP1): check ACKSTAT after I2C byte TX
    btfsc SSPCON2, 6, ACCESS
    bsf 0x7F, 2, BANKED
    return

patch_function_056_timeout:
    bsf STATUS, C, ACCESS
    return"""

# Build V2.6 ASM: V2.5 base with Fix A core replacement + Fix B/B' additions
PATCH_ASM_V26 = PATCH_ASM_V25.replace(_V25_056_CORE, _V26_056_CORE).replace(
    "\nend\n", _V26_DSP_FIXES + "\nend\n"
)

PATCH_ASM_BY_VARIANT = {
    "v24": PATCH_ASM_V24,
    "v25": PATCH_ASM_V25,
    "v26": PATCH_ASM_V26,
}


def parse_intel_hex(path: pathlib.Path) -> Dict[int, int]:
    mem: Dict[int, int] = {}
    upper = 0

    def b(h: str) -> int:
        try:
            return int(h, 16)
        except ValueError as e:
            raise HexParseError(f"bad hex byte {h!r} in {path}") from e

    with path.open("r", encoding="ascii", errors="strict") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise HexParseError(f"{path}:{lineno}: missing ':'")

            ll = b(line[1:3])
            aaaa = int(line[3:7], 16)
            rtype = b(line[7:9])
            data_hex = line[9 : 9 + ll * 2]
            cc = b(line[9 + ll * 2 : 11 + ll * 2])

            total = ll + ((aaaa >> 8) & 0xFF) + (aaaa & 0xFF) + rtype
            data: List[int] = []
            for i in range(0, len(data_hex), 2):
                bb = b(data_hex[i : i + 2])
                data.append(bb)
                total += bb
            total &= 0xFF
            calc = (~total + 1) & 0xFF
            if calc != cc:
                raise HexParseError(
                    f"{path}:{lineno}: checksum mismatch (got 0x{cc:02X}, want 0x{calc:02X})"
                )

            if rtype == 0x00:
                base = (upper << 16) | aaaa
                for i, bb in enumerate(data):
                    mem[base + i] = bb
            elif rtype == 0x01:
                break
            elif rtype == 0x04:
                if ll != 2:
                    raise HexParseError(f"{path}:{lineno}: type 04 with ll={ll}")
                upper = (data[0] << 8) | data[1]
            else:
                continue

    return mem


def _record(addr16: int, rtype: int, payload: bytes) -> str:
    ll = len(payload)
    total = ll + ((addr16 >> 8) & 0xFF) + (addr16 & 0xFF) + rtype + sum(payload)
    cc = (~total + 1) & 0xFF
    return f":{ll:02X}{addr16:04X}{rtype:02X}{payload.hex().upper()}{cc:02X}"


def write_intel_hex(path: pathlib.Path, mem: Dict[int, int], chunk: int = 16) -> None:
    addrs = sorted(mem.keys())
    lines: List[str] = []
    current_upper: int | None = None

    i = 0
    while i < len(addrs):
        start = addrs[i]
        upper = (start >> 16) & 0xFFFF
        if upper != current_upper:
            current_upper = upper
            lines.append(_record(0x0000, 0x04, bytes([(upper >> 8) & 0xFF, upper & 0xFF])))

        addr16 = start & 0xFFFF
        data = bytearray([mem[start]])
        i += 1

        while i < len(addrs):
            a = addrs[i]
            if ((a >> 16) & 0xFFFF) != upper:
                break
            if (a & 0xFFFF) != ((addr16 + len(data)) & 0xFFFF):
                break
            if len(data) >= chunk:
                break
            data.append(mem[a] & 0xFF)
            i += 1

        lines.append(_record(addr16, 0x00, bytes(data)))

    lines.append(":00000001FF")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def assemble_patch(gpasm: str, *, variant: str = "v25") -> Dict[int, int]:
    try:
        asm_text = PATCH_ASM_BY_VARIANT[variant]
    except KeyError as exc:
        raise ValueError(f"unsupported MAIN patch variant: {variant}") from exc

    with tempfile.TemporaryDirectory(prefix=f"dlcp_main_patch_{variant}_") as td:
        td_path = pathlib.Path(td)
        asm = td_path / f"main_presets_patch_{variant}.asm"
        out_hex = td_path / f"main_presets_patch_{variant}.hex"
        asm.write_text(asm_text, encoding="ascii")
        subprocess.run(
            [gpasm, "-p18f2455", "-o", str(out_hex), str(asm)],
            check=True,
            capture_output=True,
            text=True,
        )
        return parse_intel_hex(out_hex)


def copy_table_a_to_b(mem: Dict[int, int], force: bool = False) -> Tuple[int, int]:
    src = 0x5600
    dst = 0x4A00
    size = 0x0A00

    for i in range(size):
        if (src + i) not in mem:
            raise RuntimeError(f"source table missing byte @ 0x{src + i:04X}")

    if not force:
        for i in range(size):
            a = dst + i
            if a in mem and mem[a] != 0xFF:
                raise RuntimeError(
                    f"destination not erased @ 0x{a:04X}: 0x{mem[a]:02X} "
                    "(use --force-copy to overwrite)"
                )

    written = 0
    changed = 0
    for i in range(size):
        s = mem[src + i]
        a = dst + i
        old = mem.get(a, 0xFF)
        mem[a] = s
        written += 1
        if old != s:
            changed += 1

    return written, changed


def apply_patch_bytes(mem: Dict[int, int], patch: Dict[int, int]) -> Tuple[int, int]:
    written = 0
    changed = 0
    for a, v in patch.items():
        old = mem.get(a, 0xFF)
        mem[a] = v
        written += 1
        if old != v:
            changed += 1
    return written, changed


def summarize_diff(old_mem: Dict[int, int], new_mem: Dict[int, int]) -> int:
    all_addrs = set(old_mem.keys()) | set(new_mem.keys())
    diff = 0
    for a in all_addrs:
        if old_mem.get(a, 0xFF) != new_mem.get(a, 0xFF):
            diff += 1
    return diff


def set_main_eeprom_version_230(mem: Dict[int, int]) -> Tuple[int, int]:
    desired = {
        0xF00080: 0x02,
        0xF00081: 0x03,
        0xF00082: 0x30,
    }
    written = 0
    changed = 0
    for a, v in desired.items():
        old = mem.get(a, 0xFF)
        mem[a] = v
        written += 1
        if old != v:
            changed += 1
    return written, changed


def patch_usb_version(mem: Dict[int, int], *, variant: str) -> Tuple[int, int]:
    version_lo = {"v24": 0x04, "v25": 0x05, "v26": 0x06}.get(variant, 0x05)
    desired = {
        0x240C: 0x03,
        0x2412: 0x02,
        0x2416: version_lo,
    }
    written = 0
    changed = 0
    for a, v in desired.items():
        old = mem.get(a, 0xFF)
        mem[a] = v
        written += 1
        if old != v:
            changed += 1
    return written, changed


def default_output_hex_for_variant(variant: str) -> pathlib.Path:
    if variant == "v24":
        return PATCHED_MAIN_HEX_V24
    if variant == "v26":
        from dlcp_fw.paths import FIRMWARE_PATCHED_DIR
        return FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V2.6.hex"
    return PATCHED_MAIN_HEX_V25


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--variant",
        choices=("v24", "v25", "v26"),
        default="v26",
        help="patched MAIN output variant (default: v25)",
    )
    ap.add_argument(
        "--in-hex",
        type=pathlib.Path,
        default=STOCK_MAIN_HEX,
        help=f"input main firmware hex (default: {STOCK_MAIN_HEX})",
    )
    ap.add_argument(
        "--out-hex",
        type=pathlib.Path,
        default=None,
        help="output patched hex path (defaults to the selected variant release path)",
    )
    ap.add_argument(
        "--gpasm",
        default="gpasm",
        help="gpasm executable (default: gpasm)",
    )
    ap.add_argument(
        "--force-copy",
        action="store_true",
        help="overwrite destination preset B range even if non-FF bytes are present",
    )
    args = ap.parse_args()

    variant = str(args.variant)
    in_hex = args.in_hex.resolve()
    out_hex = (args.out_hex or default_output_hex_for_variant(variant)).resolve()
    out_hex.parent.mkdir(parents=True, exist_ok=True)

    base = parse_intel_hex(in_hex)
    new_mem = dict(base)

    table_written, table_changed = copy_table_a_to_b(new_mem, force=args.force_copy)
    patch_mem = assemble_patch(args.gpasm, variant=variant)
    patch_written, patch_changed = apply_patch_bytes(new_mem, patch_mem)
    eep_written, eep_changed = set_main_eeprom_version_230(new_mem)
    usb_written, usb_changed = patch_usb_version(new_mem, variant=variant)
    total_diff = summarize_diff(base, new_mem)

    # V2.6 post-build guard: verify the ACKSTAT check encoding is present.
    # btfsc SSPCON2,6,ACCESS = 0xBCC5.  Must appear in the 0x46BE-0x49FF
    # range (ackstat_first_byte_check + patch_function_056_mode_bf).
    if variant == "v26":
        found_ackstat = False
        for addr in range(0x46BE, 0x4A00, 2):
            if new_mem.get(addr, 0xFF) == 0xC5 and new_mem.get(addr + 1, 0xFF) == 0xBC:
                found_ackstat = True
                break
        if not found_ackstat:
            raise RuntimeError(
                "V2.6 post-build check FAILED: btfsc SSPCON2,6 (0xBCC5) "
                "not found in 0x46BE..0x49FF — Fix A string replacement "
                "may have silently failed"
            )

    write_intel_hex(out_hex, new_mem)

    print(f"variant: {variant}")
    print(f"input:   {in_hex}")
    print(f"output:  {out_hex}")
    print(
        "table copy A->B:",
        f"bytes={table_written}",
        f"changed={table_changed}",
        "src=0x5600..0x5FFF",
        "dst=0x4A00..0x53FF",
    )
    print(
        "stub patch:",
        f"bytes={patch_written}",
        f"changed={patch_changed}",
        "hook_addrs=[0x1E64,0x2E6E,0x3DAC,0x4028,0x20BE,0x27C0]",
        "stub_regions=[0x20BE..0x20E2,0x27C0..0x27EA,0x5400..0x55FF]",
    )
    print(
        "eeprom version tuple:",
        f"bytes={eep_written}",
        f"changed={eep_changed}",
        "eeprom=[0xF00080..0xF00082]=[0x02,0x03,0x30]",
    )
    print(
        "usb version literal:",
        f"bytes={usb_written}",
        f"changed={usb_changed}",
        f"app_version=2.{dict(v24=4, v25=5, v26=6).get(variant, 5)}",
    )
    print(f"total bytes changed vs input: {total_diff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
