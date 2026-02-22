#!/usr/bin/env python3
"""
Build a patched DLCP control firmware (v1.6b) with A/B preset support.

Patch summary (top-level Preset screen design):
- Add Preset as a top-level menu screen between Volume and Input.
- Navigation: Volume(0) <-> Preset(1) <-> Input(2) <-> Setup(3) (wrap).
- USBaudio sub-parameter is left untouched (original function preserved).
- Preset screen shows selected preset letter + full 30-byte DSP filename split across both lines.
- Volume screen shows active preset letter (A/B) at column 15.
- Preset change broadcasts route=0xB0 cmd=0x20 data=0|1.
- CONTROL requests generation metadata first with route=0xB1 cmd=0x22 data=((txn4bit)<<3)|preset.
- CONTROL requests filename pages (cmd=0x21) only when generation changed/unknown.
- CONTROL parser accepts MAIN context cmd=0x2F + cmd=0x22 generation + local chunks cmd=0x30..0x37.
- IR F1/F2 shortcuts: RC5 0x38 -> preset A, RC5 0x39 -> preset B.
- Preset state stored in state_flags bit6 (0x01F.6); persisted at EEPROM 0x74.
- Firmware version policy: display/version tuple updated to 1.61b.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import tempfile
from typing import Dict, List, Tuple

from dlcp_fw.paths import PATCHED_CONTROL_HEX_V161B, STOCK_CONTROL_HEX_V16B


class HexParseError(RuntimeError):
    pass


PATCH_ASM = r"""
LIST P=18F2550
#include <p18f2550.inc>

; ============================================================
; Patch 0 - Startup flag init
; ============================================================
; Ensure custom state bits (6/7) start from known values each boot.
; Original: bcf 0x01F,3
org 0x10B2
    clrf 0x01F, ACCESS

; ============================================================
; Patch 1 - Startup preset load hook
; ============================================================
; Original: call function_026
org 0x111C
    call preset_boot_init_wrapper

; Version splash minor/patch component: 6 -> 61 (0x3D)
; Original at 0x1152: movlw 0x06
org 0x1152
    movlw 0x3D

; ============================================================
; Patch 2 - Navigation wrap: 3 screens -> 4 screens
; ============================================================

; RIGHT: wrap limit 2 -> 3
org 0x1216
    movlw 0x03

; LEFT: wrap target 2 -> 3
org 0x123A
    movlw 0x03

; ============================================================
; Patch 3 - String table index fixes
; ============================================================

; function_047 (Setup, now menu_state=3): force string index 2
; Original: movff 0xBF, 0x027 (copies menu_state as index)
org 0x1406
    movlw 0x02
    movwf 0x027, ACCESS

; function_052 (Input, now menu_state=2): force string index 1
; Original: movff 0xBF, 0x027
org 0x191A
    movlw 0x01
    movwf 0x027, ACCESS

; ============================================================
; Patch 4 - Dispatch redirect at label_203 (0x11F0)
; ============================================================
; Original: decfsz 0xBF, W, BANKED / goto label_206
; Replace with goto to new dispatch stub + nop filler
org 0x11F0
    goto new_dispatch_stub
    nop

; ============================================================
; Patch 5 - Volume preset indicator hook
; ============================================================
; Original: call 0x0CB2 (function_035)
org 0x137A
    goto volume_indicator_stub

; ============================================================
; Patch 6 - Full-sync hook (function_028 entry)
; ============================================================
; Original:
;   0x0B36: call function_031
; Replace with stub that emits preset sync (TX-only), then calls
; function_031 and returns to original flow.
org 0x0B36
    goto full_sync_entry_stub

; ============================================================
; Patch 7 - IR dispatch pre-hook
; ============================================================
; Original: 0x0DE6 -> goto label_162 (0x0DEC)
; Route through wrapper to handle RC5 F1/F2 as preset shortcuts.
org 0x0DE6
    goto ir_dispatch_pre_stub

; ============================================================
; Patch 8 - Parser tail hook for filename chunks
; ============================================================
; Original: label_063 starts with "movlw 0x1D".
; Route through wrapper that preserves cmd=0x1D behavior and adds
; cmd=0x30..0x4D LCD filename chunk handling.
org 0x05D0
    goto parser_tail_patch

; ============================================================
; New code in erased flash area (0x7000+)
; ============================================================
org 0x7000

; ------------------------------------------------------------
; preset_boot_init_wrapper:
; - preserve stock function_026 behavior
; - load preset from EEPROM[0x74] into state_flags bit6
; ------------------------------------------------------------
preset_boot_init_wrapper:
    call 0x0A46                 ; function_026 (stock settings load)
    movlw 0x74
    call 0x0196                 ; function_010 (EEPROM byte read)
    movwf 0x027, ACCESS
    bcf 0x01F, 6, ACCESS        ; default A unless value == 1
    movlw 0x01
    cpfseq 0x027, ACCESS
    goto preset_boot_init_done
    bsf 0x01F, 6, ACCESS
preset_boot_init_done:
    call init_filename_cache
    return

; ------------------------------------------------------------
; init_filename_cache:
; - initialize display caches for preset A/B filenames:
;   A: 0x180..0x19D (30 bytes), B: 0x19E..0x1BB (30 bytes)
; ------------------------------------------------------------
init_filename_cache:
    lfsr 1, 0x0180
    movlw 0x5A
    movwf 0x028, ACCESS
ifc_loop:
    movlw ' '
    movwf POSTINC1, ACCESS
    decfsz 0x028, F, ACCESS
    bra ifc_loop
    ; filename generation cache A/B + valid mask
    lfsr 1, 0x01DA
    clrf POSTINC1, ACCESS
    clrf POSTINC1, ACCESS
    clrf INDF1, ACCESS
    clrf 0x029, ACCESS
    clrf 0x02E, ACCESS
    return

; ------------------------------------------------------------
; ir_dispatch_pre_stub:
; - adds RC5 F1/F2 preset shortcuts before stock IR dispatch
; - cmd 0x38 (F1) -> preset A
; - cmd 0x39 (F2) -> preset B
; ------------------------------------------------------------
ir_dispatch_pre_stub:
    ; Match configured RC5 address first (same gate as stock dispatch).
    movf 0x01E, W, ACCESS
    cpfseq 0x020, ACCESS
    goto ir_dispatch_passthrough

    ; F1 (0x38) -> preset A
    movf 0x01D, W, ACCESS
    xorlw 0x38
    bz ir_set_preset_a

    ; F2 (0x39) -> preset B
    movf 0x01D, W, ACCESS
    xorlw 0x39
    bz ir_set_preset_b

    goto ir_dispatch_passthrough

ir_set_preset_a:
    ; Idempotent: if already A, do nothing.
    btfss 0x01F, 6, ACCESS
    goto ir_dispatch_done
    bcf 0x01F, 6, ACCESS
    movlb 0x00
    call send_preset_frame
    bsf 0x01F, 3, ACCESS         ; request UI refresh
    goto ir_dispatch_done

ir_set_preset_b:
    ; Idempotent: if already B, do nothing.
    btfsc 0x01F, 6, ACCESS
    goto ir_dispatch_done
    bsf 0x01F, 6, ACCESS
    movlb 0x00
    call send_preset_frame
    bsf 0x01F, 3, ACCESS         ; request UI refresh
    goto ir_dispatch_done

ir_dispatch_done:
    bsf 0x01F, 0, ACCESS         ; re-arm IR path (matches stock tail)
    return

ir_dispatch_passthrough:
    movlb 0x00
    goto 0x0DEC                  ; stock label_162

; ------------------------------------------------------------
; new_dispatch_stub: handle menu states 1, 2, 3
; State 0 (Volume) is handled by original code before this point.
; ------------------------------------------------------------
new_dispatch_stub:
    ; 0xBF = menu_state, known != 0 at this point
    decfsz 0xBF, W, BANKED     ; W = BF-1; skip if was 1 (Preset)
    goto check_state_2
    call preset_screen
    goto 0x120A                 ; label_205 (post-screen nav)

check_state_2:
    movlw 0x02
    cpfseq 0xBF, BANKED        ; skip if BF == 2 (Input)
    goto check_state_3
    call 0x1912                 ; function_044 (Input)
    goto 0x120A                 ; label_205

check_state_3:
    movlw 0x03
    cpfseq 0xBF, BANKED        ; skip if BF == 3 (Setup)
    goto 0x120A                 ; unknown state -> skip
    call 0x13FE                 ; function_040 (Setup)
    goto 0x120A                 ; label_205

; ------------------------------------------------------------
; volume_indicator_stub: show A/B at line 1 col 15, then
; call function_035 (the original call we replaced).
; ------------------------------------------------------------
volume_indicator_stub:
    ; One-time boot resync: emit current preset once after startup so
    ; mains can follow EEPROM-restored state after a full power cycle.
    ; Reuse flags bit7 as "preset sync sent" latch. In V1.6b, bit5 is live stock state.
    btfsc 0x01F, 7, ACCESS
    goto vol_draw
    bsf 0x01F, 7, ACCESS
    call send_preset_frame_txonly

vol_draw:
    movlw 0x80
    movwf 0x001, ACCESS         ; LCD output target
    movlw 0x8F                  ; cursor: line 1, column 15
    call 0x0066                 ; LCD command routine
    movlw 'A'
    btfsc 0x01F, 6, ACCESS      ; preset bit6: 0=A, 1=B
    movlw 'B'
    call 0x00EC                 ; LCD char output
    call 0x0CB2                 ; function_035 (original)
    goto 0x137E                 ; return to post-function_035

; ------------------------------------------------------------
; full_sync_entry_stub: emit periodic preset sync alongside the
; existing full-sync block (function_028) without EEPROM writes.
; ------------------------------------------------------------
full_sync_entry_stub:
    call send_preset_frame_txonly
    call 0x0C40                 ; function_031 (original)
    goto 0x0B3A                 ; continue original function_028 flow

; ------------------------------------------------------------
; preset_screen: render + event loop
; Line 1: "<filename[0..13]> <preset>" (16 chars total)
; Line 2: "<filename[14..29]>" (16 chars)
; ------------------------------------------------------------
preset_screen:
    call start_filename_fetch

prs_screen_draw:
    ; --- Line 1 ---
    movlw 0x80
    movwf 0x001, ACCESS         ; LCD output target
    movlw 0x80                  ; cursor: line 1, column 0
    call 0x0066

    lfsr 1, 0x0180              ; preset A filename cache
    btfsc 0x01F, 6, ACCESS
    lfsr 1, 0x019E              ; preset B filename cache

    ; Emit first 14 filename chars on line1.
    movlw 0x0E
    movwf 0x028, ACCESS
prs_line1_name_loop:
    movf POSTINC1, W, ACCESS
    call 0x00EC
    decfsz 0x028, F, ACCESS
    bra prs_line1_name_loop
    movlw ' '
    call 0x00EC
    movlw 'A'
    btfsc 0x01F, 6, ACCESS
    movlw 'B'
    call 0x00EC

    ; --- Line 2 ---
    movlw 0xC0
    call 0x0066
    movlw 0x10
    movwf 0x028, ACCESS
prs_line2_name_loop:
    movf POSTINC1, W, ACCESS
    call 0x00EC
    decfsz 0x028, F, ACCESS
    bra prs_line2_name_loop
    clrf 0x028, ACCESS

    ; Shadow rendered preset in scratch byte 0x02D for out-of-band
    ; change detection (avoids reusing stock state_flags bits).
    clrf 0x02D, ACCESS
    btfsc 0x01F, 6, ACCESS
    incf 0x02D, F, ACCESS
    bcf 0x02E, 7, ACCESS

; --- Event loop ---
preset_loop:
    call 0x0CB2                 ; function_035 (wait for event)
    ; Parser chunk update pending -> redraw.
    btfss 0x02E, 7, ACCESS
    goto prs_check_shadow
    bcf 0x02E, 7, ACCESS
    goto prs_screen_draw

prs_check_shadow:
    ; If preset changed out-of-band (e.g. IR F1/F2), request and redraw.
    clrf WREG, ACCESS
    btfsc 0x01F, 6, ACCESS
    movlw 0x01
    xorwf 0x02D, W, ACCESS
    bz prs_shadow_ok
    call start_filename_fetch
    goto prs_screen_draw
prs_shadow_ok:

    ; Check UP (0x9A bit1) -> set preset A
    btfss 0x09A, 1, BANKED
    goto prs_check_down
    btfss 0x01F, 6, ACCESS      ; already A -> no-op
    goto preset_loop
    bcf 0x01F, 6, ACCESS
    call send_preset_frame
    call start_filename_fetch
    goto prs_screen_draw         ; full re-render

prs_check_down:
    ; Check DOWN (0x9A bit2) -> set preset B
    btfss 0x09A, 2, BANKED
    goto preset_exit_check
    btfsc 0x01F, 6, ACCESS      ; already B -> no-op
    goto preset_loop
    bsf 0x01F, 6, ACCESS
    call send_preset_frame
    call start_filename_fetch
    goto prs_screen_draw         ; full re-render

; --- Exit check (same pattern as function_046 at 0x1402) ---
preset_exit_check:
    bcf 0x01F, 3, ACCESS        ; clear refresh flag
    clrf WREG, ACCESS            ; W = 0
    btfsc 0x09A, 5, BANKED      ; RIGHT pressed?
    movlw 0x01
    movwf 0x018, ACCESS
    clrf WREG, ACCESS
    btfsc 0x09A, 4, BANKED      ; LEFT pressed?
    movlw 0x01
    iorwf 0x018, F, ACCESS
    movlw 0x01
    btfsc 0x01F, 1, ACCESS      ; still connected?
    clrf WREG, ACCESS            ; connected -> W=0
    iorwf 0x018, F, ACCESS
    btfsc STATUS, Z, ACCESS      ; skip if nonzero (exit)
    bra preset_loop              ; zero -> stay in screen
    return

; ------------------------------------------------------------
; parser_tail_patch:
; - preserve stock cmd=0x1D behavior
; - add cmd=0x2F context + cmd=0x30..0x37 local chunk ingest
; ------------------------------------------------------------
parser_tail_patch:
    movlw 0x1D
    cpfseq 0x02F, ACCESS
    goto prs_parser_check_ctx
    movf 0x0A7, W, BANKED
    subwf 0x030, W, ACCESS
    skpnz
    goto prs_parser_done
    movff 0x030, 0x0A7
    call 0x0F54                 ; function_037
    goto prs_parser_done

prs_parser_check_ctx:
    movlw 0x2F
    cpfseq 0x02F, ACCESS
    goto prs_parser_check_gen
    movf 0x030, W, ACCESS
    xorwf 0x029, W, ACCESS
    btfss STATUS, Z, ACCESS
    goto prs_parser_done
    ; Context matched request txn/page/preset: arm chunk ingest.
    movf 0x02E, W, ACCESS
    andlw 0x90
    movwf 0x02E, ACCESS
    btfss 0x029, 0, ACCESS
    bcf 0x02E, 5, ACCESS
    btfsc 0x029, 0, ACCESS
    bsf 0x02E, 5, ACCESS
    bsf 0x02E, 6, ACCESS
    goto prs_parser_done

prs_parser_check_gen:
    movlw 0x22
    cpfseq 0x02F, ACCESS
    goto prs_parser_check_chunks

    ; Generation response is accepted only after matching context and while
    ; generation mode is active (0x02E.4).
    btfss 0x02E, 6, ACCESS
    goto prs_parser_done
    btfss 0x02E, 4, ACCESS
    goto prs_parser_done

    ; Generation is carried as 7-bit data (<0x80) to stay framing-safe.
    movf 0x030, W, ACCESS
    andlw 0x7F
    movwf 0x028, ACCESS

    ; Select generation cache byte + valid-bit mask by target preset.
    lfsr 0, 0x01DC              ; valid mask (bit0=A, bit1=B)
    lfsr 1, 0x01DA              ; gen cache A
    movlw 0x01
    movwf 0x02A, ACCESS
    btfss 0x02E, 5, ACCESS
    goto prs_parser_gen_target_ready
    lfsr 1, 0x01DB              ; gen cache B
    movlw 0x02
    movwf 0x02A, ACCESS
prs_parser_gen_target_ready:
    movf INDF0, W, ACCESS
    andwf 0x02A, W, ACCESS
    bz prs_parser_gen_miss
    movf INDF1, W, ACCESS
    xorwf 0x028, W, ACCESS
    bz prs_parser_gen_hit

prs_parser_gen_miss:
    ; Generation changed/unknown: stage it and start paged cmd=0x21 fetch.
    ; Cache/valid are committed only after full page3 completion.
    movf 0x028, W, ACCESS
    movwf 0x02C, ACCESS
    movf 0x02E, W, ACCESS
    andlw 0x80
    movwf 0x02E, ACCESS
    call send_filename_request_current
    goto prs_parser_done

prs_parser_gen_hit:
    ; Cache already up-to-date: stop without cmd=0x21 fetch.
    movf 0x02E, W, ACCESS
    andlw 0x80
    movwf 0x02E, ACCESS
    goto prs_parser_done

prs_parser_check_chunks:
    ; Accept only local chunk commands 0x30..0x37.
    movf 0x02F, W, ACCESS
    andlw 0xF8
    xorlw 0x30
    bnz prs_parser_done

    ; Ignore chunks unless matching context was accepted.
    btfss 0x02E, 6, ACCESS
    goto prs_parser_done
    btfsc 0x02E, 4, ACCESS
    goto prs_parser_done

    movf 0x02F, W, ACCESS
    andlw 0x07
    movwf 0x02A, ACCESS

    ; Enforce in-page order (expected local idx in 0x02E bits0..2).
    movf 0x02E, W, ACCESS
    andlw 0x07
    xorwf 0x02A, W, ACCESS
    bnz prs_parser_done

    ; Page3 has only idx 0..5 (abs 24..29).
    movf 0x029, W, ACCESS
    andlw 0x06
    xorlw 0x06
    bnz prs_parser_idx_ok
    movf 0x02A, W, ACCESS
    sublw 0x05
    bnc prs_parser_done
prs_parser_idx_ok:
    ; abs_idx = ((page_bits<<2)) + local_idx.
    movf 0x029, W, ACCESS
    andlw 0x06
    movwf 0x028, ACCESS
    movf 0x028, W, ACCESS
    addwf 0x028, F, ACCESS
    movf 0x028, W, ACCESS
    addwf 0x028, F, ACCESS

    ; Stage incoming byte into 30-byte staging buffer (0x01BC..0x01D9).
    lfsr 1, 0x01BC
    movf 0x02A, W, ACCESS
    addwf 0x028, W, ACCESS
    addwf FSR1L, F, ACCESS

    movf 0x030, W, ACCESS
    bz prs_parser_space
    xorlw 0xFF
    bz prs_parser_space
    movf 0x030, W, ACCESS
    bra prs_parser_store
prs_parser_space:
    movlw ' '
prs_parser_store:
    movwf INDF1, ACCESS

prs_parser_advance:
    ; Page transition/termination driven by expected local idx.
    movf 0x029, W, ACCESS
    andlw 0x06
    xorlw 0x06
    bz prs_parser_page3

    movf 0x02A, W, ACCESS
    xorlw 0x07                  ; page0..2 end
    bz prs_parser_page_commit_next
    incf 0x02E, F, ACCESS       ; next local idx
    goto prs_parser_done

prs_parser_page3:
    movf 0x02A, W, ACCESS
    xorlw 0x05                  ; page3 end (idx 5)
    bz prs_parser_page_commit_done
    incf 0x02E, F, ACCESS
    goto prs_parser_done
prs_parser_page_commit_next:
    ; Commit this completed 8-byte page, then request next page.
    call prs_parser_commit_page
    movlw 0x02                  ; next page
    addwf 0x029, F, ACCESS
    movf 0x02E, W, ACCESS
    andlw 0x80
    movwf 0x02E, ACCESS         ; clear armed + expected idx
    call send_filename_request_current
    goto prs_parser_done

prs_parser_page_commit_done:
    ; Final page (idx 0..5): commit tail and complete transfer.
    call prs_parser_commit_page
    ; Commit staged generation only after full transfer commit.
    lfsr 0, 0x01DC              ; valid mask (bit0=A, bit1=B)
    lfsr 1, 0x01DA              ; gen cache A
    movlw 0x01
    movwf 0x02A, ACCESS
    btfss 0x02E, 5, ACCESS
    goto prs_parser_gen_commit_target
    lfsr 1, 0x01DB              ; gen cache B
    movlw 0x02
    movwf 0x02A, ACCESS
prs_parser_gen_commit_target:
    movf 0x02C, W, ACCESS
    movwf INDF1, ACCESS
    movf INDF0, W, ACCESS
    iorwf 0x02A, W, ACCESS
    movwf INDF0, ACCESS
    bcf 0x02E, 6, ACCESS        ; disarm context
    goto prs_parser_done

prs_parser_commit_page:
    ; page_off = (page_bits<<2) = page*8
    movf 0x029, W, ACCESS
    andlw 0x06
    movwf 0x028, ACCESS
    movf 0x028, W, ACCESS
    addwf 0x028, F, ACCESS
    movf 0x028, W, ACCESS
    addwf 0x028, F, ACCESS

    lfsr 0, 0x01BC              ; staging base
    lfsr 1, 0x0180              ; preset A cache
    btfsc 0x02E, 5, ACCESS
    lfsr 1, 0x019E              ; preset B cache
    movf 0x028, W, ACCESS
    addwf FSR0L, F, ACCESS
    addwf FSR1L, F, ACCESS

    movlw 0x08                  ; default page copy width
    movwf 0x02A, ACCESS
    movf 0x029, W, ACCESS
    andlw 0x06
    xorlw 0x06
    bnz prs_parser_commit_loop
    movlw 0x06                  ; page3 tail width
    movwf 0x02A, ACCESS
prs_parser_commit_loop:
    movf POSTINC0, W, ACCESS
    movwf POSTINC1, ACCESS
    decfsz 0x02A, F, ACCESS
    bra prs_parser_commit_loop

    ; Mark redraw only when preset screen is active.
    movlw 0x01
    cpfseq 0x0BF, BANKED
    return
    bsf 0x02E, 7, ACCESS
    return

prs_parser_done:
    goto 0x05EA

; ------------------------------------------------------------
; send_preset_frame: transmit route=0xB0 cmd=0x20 data=preset
; ------------------------------------------------------------
send_preset_frame_txonly:
    movlw 0xB0                  ; route = broadcast
    movwf 0x027, ACCESS
    call 0x05EC                 ; function_020 (serial TX byte)
    movlw 0x20                  ; cmd = set preset
    movwf 0x027, ACCESS
    call 0x05EC
    clrf WREG, ACCESS
    btfsc 0x01F, 6, ACCESS
    movlw 0x01                  ; data = preset value (0 or 1)
    movwf 0x027, ACCESS
    call 0x05EC
    return

start_filename_fetch:
    ; Build new request token: bump txn (bits6..3), page0, preset bit.
    ; Keep bit7 clear so reply data is never mis-framed as a route byte.
    movf 0x029, W, ACCESS
    addlw 0x08
    andlw 0x78
    movwf 0x029, ACCESS
    btfsc 0x01F, 6, ACCESS
    incf 0x029, F, ACCESS
    clrf 0x02E, ACCESS
    bsf 0x02E, 4, ACCESS        ; generation mode (expect cmd=0x22 after context)
    call send_filename_generation_request
    return

send_filename_generation_request:
    movlw 0xB1                  ; route = first MAIN only
    movwf 0x027, ACCESS
    call 0x05EC                 ; function_020 (serial TX byte)
    movlw 0x22                  ; cmd = filename generation request
    movwf 0x027, ACCESS
    call 0x05EC
    movf 0x029, W, ACCESS
    movwf 0x027, ACCESS
    call 0x05EC
    return

send_filename_request_current:
    movlw 0xB1                  ; route = first MAIN only
    movwf 0x027, ACCESS
    call 0x05EC                 ; function_020 (serial TX byte)
    movlw 0x21                  ; cmd = filename display request
    movwf 0x027, ACCESS
    call 0x05EC
    movf 0x029, W, ACCESS
    movwf 0x027, ACCESS
    call 0x05EC
    return

send_preset_frame:
    call send_preset_frame_txonly
    ; EEPROM persist: write preset to EEPROM[0x74]
    movlw 0x74
    movwf EEADR, ACCESS
    clrf WREG, ACCESS
    btfsc 0x01F, 6, ACCESS
    movlw 0x01
    call 0x01A2                 ; function_011 (EEPROM byte write)
    return

end
"""


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


def assemble_patch(gpasm: str) -> Dict[int, int]:
    with tempfile.TemporaryDirectory(prefix="dlcp_control_patch_") as td:
        td_path = pathlib.Path(td)
        asm = td_path / "control_presets_patch.asm"
        out_hex = td_path / "control_presets_patch.hex"
        asm.write_text(PATCH_ASM, encoding="ascii")
        result = subprocess.run(
            [gpasm, "-p18f2550", "-o", str(out_hex), str(asm)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"gpasm failed (rc={result.returncode}):\n{result.stderr}\n{result.stdout}"
            )
        return parse_intel_hex(out_hex)


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


def validate_expected(mem: Dict[int, int]) -> None:
    """Validate original V1.6b firmware bytes at all patch points."""
    expected = {
        # Patch 0: startup flag init hook (original bcf 0x01F,3)
        0x10B2: 0x1F,
        0x10B3: 0x96,
        # Patch 1: startup preset hook (original call function_026)
        0x111C: 0x23,
        0x111D: 0xEC,
        0x111E: 0x05,
        0x111F: 0xF0,
        # Patch 1b: version literal (movlw 0x06)
        0x1152: 0x06,
        0x1153: 0x0E,
        # Patch 2: nav wrap literals (movlw 0x02)
        0x1216: 0x02,
        0x1217: 0x0E,
        0x123A: 0x02,
        0x123B: 0x0E,
        # Patch 3: string table index (movff 0xBF, 0x027)
        0x1406: 0xBF,
        0x1407: 0xC0,
        0x191A: 0xBF,
        0x191B: 0xC0,
        # Patch 4: dispatch hook (decfsz 0xBF, W, BANKED)
        0x11F0: 0xBF,
        0x11F1: 0x2D,
        # Patch 5: volume indicator hook (call function_035 = call 0x0CB2)
        0x137A: 0x59,
        0x137B: 0xEC,
        0x137C: 0x06,
        0x137D: 0xF0,
        # Patch 6: full-sync entry hook (call function_031 = call 0x0C40)
        0x0B36: 0x20,
        0x0B37: 0xEC,
        0x0B38: 0x06,
        0x0B39: 0xF0,
        # Patch 7: IR dispatch pre-hook (original goto label_162)
        0x0DE6: 0xF6,
        0x0DE7: 0xEF,
        0x0DE8: 0x06,
        0x0DE9: 0xF0,
        # Patch 8: parser-tail hook site (original label_063: movlw 0x1D)
        0x05D0: 0x1D,
        0x05D1: 0x0E,
    }
    for a, want in expected.items():
        got = mem.get(a, 0xFF)
        if got != want:
            raise RuntimeError(
                f"input firmware mismatch at 0x{a:04X}: got 0x{got:02X}, expected 0x{want:02X}"
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--in-hex",
        type=pathlib.Path,
        default=STOCK_CONTROL_HEX_V16B,
        help="input control v1.6b hex",
    )
    ap.add_argument(
        "--out-hex",
        type=pathlib.Path,
        default=PATCHED_CONTROL_HEX_V161B,
        help="output patched control hex",
    )
    ap.add_argument("--gpasm", default="gpasm", help="gpasm executable (default: gpasm)")
    args = ap.parse_args()

    in_hex = args.in_hex.resolve()
    out_hex = args.out_hex.resolve()
    out_hex.parent.mkdir(parents=True, exist_ok=True)

    base = parse_intel_hex(in_hex)
    validate_expected(base)
    new_mem = dict(base)

    # No text patches — USBaudio labels and Volume header are preserved.
    # Preset text is rendered at runtime by the preset_screen stub.

    patch_mem = assemble_patch(args.gpasm)
    patch_written, patch_changed = apply_patch_bytes(new_mem, patch_mem)

    # Keep CONTROL version tuple at 1.61 in EEPROM defaults.
    version_bytes = {
        0xF00070: 0x01,
        0xF00071: 0x06,
        0xF00072: 0x31,
    }
    ver_written = 0
    ver_changed = 0
    for a, v in version_bytes.items():
        old = new_mem.get(a, 0xFF)
        new_mem[a] = v
        ver_written += 1
        if old != v:
            ver_changed += 1

    total_diff = summarize_diff(base, new_mem)

    write_intel_hex(out_hex, new_mem)

    print(f"input:  {in_hex}")
    print(f"output: {out_hex}")
    print(
        "code patch:",
        f"bytes={patch_written}",
        f"changed={patch_changed}",
        "hooks=[0x10B2,0x111C,0x1152,0x0B36,0x0DE6,0x05D0,0x1216,0x123A,0x1406,0x191A,0x11F0,0x137A]",
        "stub_range=0x7000+",
    )
    print(
        "version patch:",
        f"bytes={ver_written}",
        f"changed={ver_changed}",
        "eeprom=[0xF00070..0xF00072]=[0x01,0x06,0x31]",
    )
    print(f"total bytes changed vs input: {total_diff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
