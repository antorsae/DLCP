; ===========================================================================
;                    Hypex DLCP — MAIN firmware V3.2
; ===========================================================================
; Target MCU : Microchip PIC18F2455 @ 16 MHz (4 MIPS), USB-FS HID device
; USB IDs    : VID 0x04D8, PID 0xFF89  (string "DLCP" / "Hypex BV")
; Peripherals: MSSP (I2C master to TAS3108 DSP @ 0x68 + secondary dev @ 0x71),
;              EUSART (current-loop RS-485-style, 31,250 baud, 3-byte frames),
;              Timer0 (heartbeat / debounce), Timer3 (DSP ping + preset hold),
;              ADC AN0 (rail standby sense — threshold ~0x0228 / 0x0236),
;              GPIOs RA3-RA5 (source select), RA6/RB3-RB6 (relays/aux).
;
; Image map (post-build, gpasm output -p18f2455):
;   0x1000 .. 0x10AB  USB descriptors + ASCII hex lookup table (read-only data)
;   0x10AC .. 0x4C00  Application code  (HID dispatch, parser, ISR, services)
;   0x4C00 .. 0x55FE  DSP preset table B (slot used in V2.4+ A/B patch path)
;   0x5600 .. 0x57FE  DSP preset table A (stock-aligned, pinned to flash top)
;   0xF00000+         EEPROM data — config bytes, version marker
;                     (V3.2 Tier-1: + reset-cause classification
;                      + cmd 0x22 reset-flags burst + HID cmd 0x44
;                      diag snapshot = 03/02/37)
;
; Build      : gpasm -p18f2455 -o DLCP_Firmware_V3.2.hex dlcp_main_v32.asm
;              (from src/dlcp_fw/sim/v30_symbols.py::assemble_v30)
;
; ---------------------------------------------------------------------------
; Position in the V2.x/V3.x release line
; ---------------------------------------------------------------------------
;   V2.3   Stock Hypex MAIN binary (reference baseline).
;   V2.4   First A/B preset binary patch on stock V2.3.
;   V2.5   V2.4 + I2C/MSSP timeout recovery (stock-bus-clear + DSP ping).
;   V2.6   + DSP NACK-aware volume retry (Fix B / Fix B').
;   V2.7   + bus-clear/ping/PEN integration (pairs with CONTROL V1.63b).
;   V2.8   + delayed-switch synchronous helper (BLOCKING — caused desync bug).
;   V3.0   Source-equivalent rewrite of V2.3 (zero functional change).
;   V3.1   V3.0 + all robustness features inline (recommended deployment).
; * V3.2   THIS FILE — V3.1 + asynchronous preset job state machine,
;          bounded START/STOP waits in apply path, mute/preset coalescing,
;          standby/reconnect cancellation, EEPROM marker bumped to 03/02/32.
;
; The V3.2 work targets the field failure pattern documented in
; docs/V32_MAIN_HANG_HARDENING_PLAN.md and docs/V28_DELAYED_SWITCH_REMEDIATION_PLAN.md
; (CONTROL keeps sending 0x03 commands but one or both MAINs stop reacting after
; rapid preset toggles or interleaved standby/mute traffic).
;
; ---------------------------------------------------------------------------
; Serial protocol over the current loop (31,250 baud, 3-byte frame)
; ---------------------------------------------------------------------------
;   route byte : 0xB0 = broadcast (MAIN0 + MAIN1)        ← active_flags.0 = 0
;                0xB1 = addressed unit only              ← active_flags.0 = 1
;                0xBF = MAIN-to-CONTROL response prefix
;   cmd byte   : 0x03=stdby/wake/mute, 0x04=status_poll, 0x06=input_select,
;                0x07=volume, 0x17..0x1C=channel cfg, 0x1D=shared setup byte,
;                0x1E=link addr, 0x20=preset_select (V2.4+).
;   data byte  : depends on cmd. cmd=0x03/data: 0=standby, 1=wake,
;                2=mute_on, 3=mute_off.
;
; CONTROL gates ALL command processing on the active gate
; (active_flags.bit3). cmd=0x03/data=0 broadcasts close every gate
; system-wide. The wake frame (cmd=0x03/data=1) reopens them. Failure to
; emit the wake frame is the V1.62b reconnect bug — see
; docs/analysis/V162B_RECONNECT_WAKE_BUG.md.
;
; ---------------------------------------------------------------------------
; Top-level service architecture (main loop = main_processing_loop @ 0x48C6)
; ---------------------------------------------------------------------------
;   periodic_service_loop:
;     1. main_usb_service_3a26   — USB SIE / HID OUT processing
;     2. main_uart_service_1be6  — RX ring drain + 3-byte parser + forward
;     3. preset_job_service      — V3.2 async preset state machine (NEW)
;     4. main_i2c_service_27f0   — DSP refresh / dirty bit drain
;     5. standby_event_dispatch  — react to event_flags.bit2 (stdby/wake)
;     6. main_core_service_265c  — assorted housekeeping
;     7. an0_hysteresis_monitor  — rail-rise / rail-fall classification
;
; All paths are non-blocking by V3.2 convention except the legacy
; main_i2c_service_381c sites that V3.2 hardening has not yet boundified.
;
; ---------------------------------------------------------------------------
; Known long-standing bugs (cross-refs to docs/analysis/SEMANTIC_FUNCTION_MAP.md)
; ---------------------------------------------------------------------------
;   M1  i2c_busywait_no_timeout       — i2c_wait_bus_idle (still stock/raw)
;   M2  uart_tx_trmt_busywait         — addressed by wait_trmt_bounded (V3.1+)
;   M3  eeprom_write_disables_gie     — eeprom_write_blocking, ~4 ms GIE-off
;   M4  oerr_no_fifo_drain            — addressed by full FIFO drain + parser resync
;   M5  timer3_blocking_delay         — replaced by ISR-tick HOLDING in V3.2
;   M6  rx_ring_no_overflow_detect    — silent overwrite at 0x0200 ring
;   M7  flash_write_gie_leak          — flash_write_with_gie_off
;   M8  no_clrwdt_main_loop           — only usb_disconnect_handler clears WDT
;   M9  adc_boot_gate_no_timeout      — adc_boot_gate (waits AN0 ≥ 0x0236)
;
; ===========================================================================

    LIST P=18F2455
    #include <p18f2455.inc>
    #include "dlcp_main_ram.inc"

; ---------------------------------------------------------------------------
; V3.2 named RAM aliases (multi-purpose / state-machine slots)
; ---------------------------------------------------------------------------
; dsp_fault_flags packs:
;   bit2 (mask 0x04) : ACKSTAT latch — set by i2c_tas3108_coeff_write/reg1f
;                      when SSPCON2.ACKSTAT was 1 (NACK) on the last byte.
;                      Drives volume_dsp_write retry/escalation.
;   bit6 (mask 0x40) : DSP_FAULT — set by dsp_ping NACK or after retries
;                      exhausted. Forwarded to CONTROL via BF/08 frame.
;   bits[5:3] (mask 0x38) : retry counter for volume_dsp_write (0..5×0x08).
; Note: bits 0/1/7 are reserved for periodic_service handshake plumbing.
dsp_fault_flags         EQU  0x07F

; Shared 16-bit timeout countdown used by every wait_*_bounded helper.
; Seeded to ~0x1000 (see wait_seed). Each wait_tick decrements; carry set on 0.
; Caveat: helpers share the slot — only one bounded wait may be active at a
; time. All call sites are call-then-poll, so this is safe.
timeout_lo              EQU  0x00B
timeout_hi              EQU  0x00C

; saved_w is the cooperative WREG-spill slot used by i2c_byte_tx so callers
; can supply the byte in W and recover it post-write without using a SCRATCH
; that ISR/preset-apply also touches.
saved_w                 EQU  0x005

; Stock A/B preset plumbing that V3.2 still relies on.
; The live HID-visible filename always sits in the stock RAM slot at 0x02C0
; and is backed by EEPROM 0x60..0x7D (preset A) or 0x83..0xA0 (preset B).
preset_filename_ram_base EQU  0x02C0
preset_filename_len      EQU  0x1E
preset_filename_eeprom_a EQU  0x60
preset_filename_eeprom_b EQU  0x83
current_cmd_data         EQU  0x0A3   ; parser-staged data byte (route/cmd live in nearby bank-0 slots)
filename_dirty_flags     EQU  0x0BD   ; bit5 = stock filename RAM slot dirty
                                       ; bit6 = usb_filename_xact_pending
                                       ;        (V3.2 cleanup: gates
                                       ;        preset_select_handler from
                                       ;        running the state machine
                                       ;        while a USB cmd 0x03 filename
                                       ;        write is in flight, so a
                                       ;        concurrent CONTROL B0/20/x
                                       ;        broadcast can't race the
                                       ;        host's force_persist and
                                       ;        clobber RAM via
                                       ;        preset_load_filename mid-
                                       ;        HOLDING)
preset_hold_timer_lo     EQU  0x08C   ; Timer3 ISR countdown low byte used by HOLDING
preset_hold_timer_hi     EQU  0x08D   ; Timer3 ISR countdown high byte used by HOLDING

; ---------------------------------------------------------------------------
; V3.2 preset job state machine — placed in BSR=2 immediately after the
; filename staging buffer at 0x2C0..0x2DD. 7 bytes total.
; The state machine is advanced ONCE per main-loop pass from
; periodic_service_loop, so each transition is observable in well under the
; UART byte time and command latency stays bounded.
; ---------------------------------------------------------------------------
preset_job_state        EQU  0x2DE   ; 0=IDLE,1=PENDING,2=HOLDING,3=APPLY,4=COMMIT
preset_job_target       EQU  0x2DF   ; requested preset (0=A, 1=B). May be re-armed
                                     ; mid-job to coalesce rapid CONTROL F1/F2 toggles.
preset_job_index        EQU  0x2E0   ; APPLY: table entry counter, 0..0x60.
                                     ; index 0x60 redirects to the final LOGICAL entry @ 0x5F00
                                     ; (flash_read remaps that to 0x5500 when preset B is active).
preset_job_delay        EQU  0x2E1   ; HOLDING: ms remaining (reserved — ISR path uses
                                     ; preset_hold_timer_lo/hi Timer3 countdown instead).
preset_job_flags        EQU  0x2E2   ; bit0=we_force_muted (preset_force_mute did the mute),
                                     ; bit1=user_mute_desired (latched user intent during job).
                                     ; Drives whether COMMIT/CANCEL restores volume or stays muted.
preset_job_tbl_lo       EQU  0x2E3   ; APPLY: logical TBLPTR seed inside the stock-aligned
preset_job_tbl_hi       EQU  0x2E4   ; preset window 0x5600..0x5FFF. flash_read remaps that
                                     ; window to 0x4C00..0x55FF whenever active_flags.bit2
                                     ; says preset B is active. Pre-incremented by 0x18 per entry.


; ---------------------------------------------------------------------------
; Configuration Bits
; ---------------------------------------------------------------------------
    __CONFIG  _CONFIG1L, 0x3A
    __CONFIG  _CONFIG1H, 0x46
    __CONFIG  _CONFIG2L, 0x3E
    __CONFIG  _CONFIG2H, 0x1E
    __CONFIG  _CONFIG3H, 0x00
    __CONFIG  _CONFIG4L, 0x80
    __CONFIG  _CONFIG5L, 0x0F
    __CONFIG  _CONFIG5H, 0xC0
    __CONFIG  _CONFIG6L, 0x0F
    __CONFIG  _CONFIG6H, 0xA0
    __CONFIG  _CONFIG7L, 0x0F
    __CONFIG  _CONFIG7H, 0x40

; ---------------------------------------------------------------------------
; V3.2 Layer 5 — saturating diagnostic counter increment macro
; ---------------------------------------------------------------------------
; Used by the diag_i / diag_d / diag_s / diag_b / diag_r / diag_a / diag_p
; instrumentation hooks placed at the named V3.x code paths per
; docs/V163B_DIAGNOSTICS_MENU_SPEC.md.  Each counter is one byte at
; 0x2E5..0x2EB (bank 2, see dlcp_main_ram.inc).  The counters saturate at
; 0x0F so the rev 0x37 cmd 0x21 / cmd 0x22 reply burst (one frame per
; counter / reset-cause flag, low nibble carries the value, high nibble
; forced to 0 by the shared diag_send_burst_xx mask) stays inside the
; chain-forwarder's < 0x80 data-byte invariant.
;
; Side effects: clobbers BSR (caller must re-establish if it cares).
; Most hook sites are at routine returns / tail-calls where BSR is reset
; on the next instruction anyway — see hook annotations.
;
; Self-healing upper bound (V3.2 hardening): if a counter cell holds a
; value > 0x0F (e.g. RAM corruption from FSR overrun, uninitialized boot
; on a non-BOR reset, or a stray write into the diag block), the original
; macro would `cpfslt < 0x0F`, fail to skip, fall through to `bra $+4`,
; and leave the corrupt value untouched.  cmd 0x21 then transmitted the
; corrupt low nibble verbatim and the operator's Diag-page cell stuck at
; whatever glyph the corrupt value rendered to, forever.  The defense is
; layered: the diag_send_burst_xx helper masks the wire byte with
; `andlw 0x0F` (see the mask instruction at the burst-loop body — search
; for `chain-forwarder safe` in this file), AND this macro now self-
; clamps any counter > 0x0F back to 0x0F on the next increment so the
; in-RAM cell heals too.
;
; Branch shape:
;   counter > 0x0F  →  movwf counter (W=0x0F)  →  done    (clamp)
;   counter == 0x0F →  done                              (saturate)
;   counter <  0x0F →  incf counter                      (increment)
;
; LOCAL labels are required so each macro expansion gets unique label
; names; the previous `bra $+4` style is replaced because the new shape
; has two forward branches and a hand-counted offset is brittle.
;
; Usage:    diag_inc_sat   diag_i
diag_inc_sat MACRO counter
    LOCAL   _check_low, _done
    movlb   0x02                        ; V3.2 Layer 5 diag block in BANK 2
    movlw   0x0F
    cpfsgt  counter, BANKED             ; skip if counter > 0x0F
    bra     _check_low
    movwf   counter, BANKED             ; counter > 0x0F: clamp to 0x0F (W=0x0F)
    bra     _done
_check_low:
    cpfslt  counter, BANKED             ; skip if counter < 0x0F
    bra     _done                       ; counter == 0x0F: saturate (no inc)
    incf    counter, F, BANKED          ; counter < 0x0F: increment
_done:
    ENDM

; ---------------------------------------------------------------------------
; App Entry / Interrupt Vector Stub (0x1000)
; ---------------------------------------------------------------------------
; Hypex MAIN images live above the bootloader at 0x1000. The bootloader's
; reset vector at 0x0000 jumps here; the bootloader's HW interrupt vector at
; 0x0008 jumps to 0x1008 below, hence the FSR2 spill + ISR call sequence
; that occupies words 0x1008..0x1012. flow_app_entry_1014 then jumps to the
; cold-init path (flow_main_flash_service_3ce8_3d4e).
; ---------------------------------------------------------------------------
    org 0x1000
    goto        flow_app_entry_1014                 ; 0x1000 user reset trampoline
    dw          0xFFFF
    dw          0xFFFF
    movff       FSR2L, isr_save_fsr2l               ; 0x1008 ISR shadow vector entry
    movff       FSR2H, isr_save_fsr2h
    call        main_isr_dispatch, 0x1              ; FAST=1: shadow STATUS/W/BSR
flow_app_entry_1014:
    goto        flow_main_flash_service_3ce8_3d4e   ; cold init / boot

; ---------------------------------------------------------------------------
; USB Descriptors and Data Tables (0x1018-0x10AB)
; ---------------------------------------------------------------------------
; All USB descriptors are read via TBLRD from the descriptor pull engine in
; main_usb_service_*. Bytes are word-packed little-endian; sub-labels below
; are byte offsets used directly as TBLPTR values. nibble_to_hex_ascii uses
; hex_lookup_table to convert a low nibble to its ASCII representation
; (0..9 → '0'..'9', 0xA..0xF → 'A'..'F').
; ---------------------------------------------------------------------------
hex_lookup_sentinel:  ; NUL byte at hex_lookup_table-1 terminates string scans
    dw  0x3000, 0x3231, 0x3433, 0x3635, 0x3837, 0x4139, 0x4342, 0x4544
    dw  0xA646, 0x9A72                                   ; padding + descriptor ptr table seed

usb_config_descriptor:  ; USB Configuration Descriptor (1 cfg, 1 if, bus-powered, 100 mA)
    dw  0x0209, 0x0029, 0x0101, 0x8000, 0x0932, 0x0004, 0x0200, 0x0003
    dw  0x0000

usb_hid_descriptor:  ; USB HID Descriptor (HID 1.11, country=0, 1 report)
    dw  0x2109, 0x0111, 0x0100, 0x1D22, 0x0700, 0x8105, 0x4003, 0x0100

usb_ep1_out_descriptor:  ; Endpoint 1 OUT (interrupt, 64 B); HID report descriptor follows
    dw  0x0507, 0x0301, 0x0040, 0x0601, 0xFF00, 0x0109, 0x01A1, 0x0119
    dw  0x4029, 0x0015, 0xFF26, 0x7500, 0x9508, 0x8140, 0x1900, 0x2901
    dw  0x9140, 0xC000

usb_string_desc_1:  ; "Hypex BV"  (UTF-16LE, vendor name)
    dw  0x0316, 0x0048, 0x0079, 0x0070, 0x0065, 0x0078, 0x0020, 0x0042
    dw  0x0056, 0x0000, 0x0000

usb_device_descriptor:  ; USB Device Descriptor — VID=0x04D8 PID=0xFF89 (Hypex/DLCP)
    dw  0x0112, 0x0200, 0x0000, 0x0800, 0x04D8, 0xFF89, 0x0001, 0x0201
    dw  0x0100

usb_string_desc_2:  ; "DLCP"  (UTF-16LE, product name)
    dw  0x030C, 0x0044, 0x004C, 0x0043, 0x0050, 0x0000

usb_string_desc_0:  ; LANGID descriptor — 0x0409 (English-US)
    dw  0x0304, 0x0409

usb_data_pad:  ; padding word so first instruction lands on a code boundary
    dw  0x0000

; Sub-labels at odd byte addresses (EQU offsets — used directly as TBLPTR seeds)
hex_lookup_table          EQU  hex_lookup_sentinel + 0x1   ; ASCII '0'..'F' table base
string_desc_ptr_table     EQU  hex_lookup_sentinel + 0x11  ; index→string-desc offset table
usb_interface_descriptor  EQU  usb_config_descriptor + 0x9 ; USB Interface Descriptor (HID class)
usb_ep1_in_descriptor     EQU  usb_hid_descriptor + 0x9    ; Endpoint 1 IN (interrupt, 64 B)
usb_hid_report_descriptor EQU  usb_ep1_out_descriptor + 0x7; HID report (vendor-defined, 64 B in/out)

; ---------------------------------------------------------------------------
; Application Code
; ---------------------------------------------------------------------------


; ---------------------------------------------------------------------------
; Function: hid_command_dispatch          (USB HID OUT report decoder)
; Address : 0x10AC
; ---------------------------------------------------------------------------
; Decodes the 8-byte HID OUT report staged at 0x01ED and routes by report
; opcode in W (loaded from byte 0). The first 7 bytes are mirrored into the
; staging area at 0x004D so handlers can both work on a stable copy and emit
; the response from the same buffer.
;
; XOR cmp 0x42 ('B'): branch to the legacy XOR-trampoline (hid_cmd_xor_dispatch);
; otherwise fall through to the per-opcode XOR chain. Opcodes covered include
; configuration upload (0x09/0x0A), preset bake helpers (0x06/0x07), HID-driven
; firmware-update entry (the fw_update_relay path), and the V3.1 diagnostic
; flash/EEPROM memread (0x43, see hid_cmd_diag_memread). Each handler ends by
; jumping into flow_hid_command_dispatch_15aa to commit the response and
; signal completion to the SIE.
; ---------------------------------------------------------------------------
hid_command_dispatch:
    movff       WREG, i2c_coeff_2
    lfsr        FSR2, 0x01ED
    lfsr        FSR1, 0x004D
    movlw       0x07
flow_hid_command_dispatch_10ba:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         flow_hid_command_dispatch_10ba
    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x42
    bnz         flow_hid_command_dispatch_10ca
    bra         hid_cmd_xor_dispatch
flow_hid_command_dispatch_10ca:
    movlb       0x0
    clrf        ram_0x0CB, BANKED
    bra         hid_cmd_xor_dispatch
flow_hid_command_dispatch_10d0:
    movff       ram_0x11B, ram_0x097
    movlb       0x0
    movf        ram_0x097, W, BANKED
    xorlw       0x09
    bnz         flow_hid_command_dispatch_1104
    movlw       0x02
    movwf       i2c_coeff_3, ACCESS
flow_hid_command_dispatch_10e0:
    rcall       main_core_service_15b0
    movf        INDF2, W, ACCESS
    bz          flow_hid_command_dispatch_10fa
    rcall       main_core_service_15b0
    movlw       0xBE
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x02
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         flow_hid_command_dispatch_10fc
flow_hid_command_dispatch_10fa:
    rcall       main_core_service_15be
flow_hid_command_dispatch_10fc:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_10e0
flow_hid_command_dispatch_1104:
    movlb       0x0
    movf        ram_0x097, W, BANKED
    xorlw       0x0A
    bnz         flow_hid_command_dispatch_111a
    movlw       0x02
    movwf       i2c_coeff_3, ACCESS
flow_hid_command_dispatch_1110:
    rcall       main_core_service_15be
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_1110
flow_hid_command_dispatch_111a:
    movlw       0x03
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movff       ram_0x11B, ram_0x0C2
    bsf         ram_0x0BD, 5, BANKED            ; filename RAM dirty
    bsf         ram_0x0BD, 6, BANKED            ; V3.2: gate USB filename xact
                                                ; until force_persist clears
                                                ; both bits.  preset_select_
                                                ; handler defers state-machine
                                                ; entry while bit6 set so a
                                                ; concurrent CONTROL B0/20/x
                                                ; broadcast can't race the
                                                ; host's force_persist.
flow_hid_command_dispatch_1126:
    call        main_timer_service_48a6, 0x0
flow_hid_command_dispatch_112a:
    call        main_core_service_492e, 0x0
flow_hid_command_dispatch_112e:
    call        main_core_service_2328, 0x0
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1134:
    movlb       0x1
    decf        ram_0x01B, W, BANKED
    bnz         flow_hid_command_dispatch_116a
    movff       ram_0x11C, ram_0x0B7
    bra         flow_hid_command_dispatch_115c
flow_hid_command_dispatch_1140:
    movlw       0x04
    movwf       ram_0x0C1, BANKED
    movlw       0x01
    movwf       ram_0x0C2, BANKED
    bra         flow_hid_command_dispatch_112a
flow_hid_command_dispatch_114a:
    movff       ram_0x11D, ram_0x0B8
    movlw       0x04
    movwf       ram_0x0C1, BANKED
    movlw       0x01
    movwf       ram_0x0C2, BANKED
    bsf         ram_0x07F, 0, BANKED
    bsf         ram_0x094, 4, BANKED
    bra         flow_hid_command_dispatch_112a
flow_hid_command_dispatch_115c:
    movlb       0x0
    movf        ram_0x0B7, W, BANKED
    xorlw       0x01
    bz          flow_hid_command_dispatch_1140
    xorlw       0x03
    bz          flow_hid_command_dispatch_114a
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_116a:
    movf        ram_0x01B, W, BANKED
    xorlw       0x02
    bz          flow_hid_command_dispatch_1172
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1172:
    movff       ram_0x11E, ram_0x0B5
    movlw       0x04
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movlw       0x02
    movwf       ram_0x0C2, BANKED
    movf        ram_0x0B5, W, BANKED
    xorlw       0x06
    bnz         flow_hid_command_dispatch_11c0
    movlw       0x05
    movwf       i2c_coeff_3, ACCESS
flow_hid_command_dispatch_118a:
    rcall       main_core_service_15b0
    movf        INDF2, W, ACCESS
    bz          flow_hid_command_dispatch_11a4
    rcall       main_core_service_15b0
    movlw       0xFB
    addwf       i2c_coeff_3, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x00
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         flow_hid_command_dispatch_11b2
flow_hid_command_dispatch_11a4:
    movlw       0xFB
    addwf       i2c_coeff_3, W, ACCESS
    call        setup_fsr2_page_1, 0x0
    setf        INDF2, ACCESS
flow_hid_command_dispatch_11b2:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x13
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_118a
    movlb       0x0
    bsf         ram_0x0BD, 4, BANKED
    bra         flow_hid_command_dispatch_1126
flow_hid_command_dispatch_11c0:
    movf        ram_0x0B5, W, BANKED
    xorlw       0x05
    bz          flow_hid_command_dispatch_112a
    movf        ram_0x0B5, W, BANKED
    xorlw       0x07
    bz          flow_hid_command_dispatch_112a
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_11ce:
    movff       ram_0x11B, input_select
    movff       ram_0x11F, computed_volume_3
    movff       ram_0x120, computed_volume_2
    movff       ram_0x121, computed_volume_1
    movff       ram_0x122, computed_volume
    movlb       0x1
    btfsc       ram_0x023, 0, BANKED
    bra         flow_hid_command_dispatch_11ec
    bcf         active_flags, 4, ACCESS
    bra         flow_hid_command_dispatch_11ee
flow_hid_command_dispatch_11ec:
    bsf         active_flags, 4, ACCESS
flow_hid_command_dispatch_11ee:
    movlb       0x1
    btfsc       ram_0x024, 0, BANKED
    bra         flow_hid_command_dispatch_11fa
    movlb       0x0
    bcf         ram_0x0A4, 0, BANKED
    bra         flow_hid_command_dispatch_11fe
flow_hid_command_dispatch_11fa:
    movlb       0x0
    bsf         ram_0x0A4, 0, BANKED
flow_hid_command_dispatch_11fe:
    movlb       0x1
    btfsc       ram_0x025, 0, BANKED
    bra         flow_hid_command_dispatch_120a
    movlb       0x0
    bcf         ram_0x0A4, 1, BANKED
    bra         flow_hid_command_dispatch_120e
flow_hid_command_dispatch_120a:
    movlb       0x0
    bsf         ram_0x0A4, 1, BANKED
flow_hid_command_dispatch_120e:
    movlb       0x1
    btfsc       ram_0x026, 0, BANKED
    bra         flow_hid_command_dispatch_121a
    movlb       0x0
    bcf         ram_0x0A4, 2, BANKED
    bra         flow_hid_command_dispatch_121e
flow_hid_command_dispatch_121a:
    movlb       0x0
    bsf         ram_0x0A4, 2, BANKED
flow_hid_command_dispatch_121e:
    movlb       0x1
    btfsc       ram_0x028, 0, BANKED
    bra         flow_hid_command_dispatch_122a
    movlb       0x0
    bcf         ram_0x0A4, 3, BANKED
    bra         flow_hid_command_dispatch_122e
flow_hid_command_dispatch_122a:
    movlb       0x0
    bsf         ram_0x0A4, 3, BANKED
flow_hid_command_dispatch_122e:
    movlb       0x1
    btfsc       ram_0x029, 0, BANKED
    bra         flow_hid_command_dispatch_123a
    movlb       0x0
    bcf         ram_0x0A4, 4, BANKED
    bra         flow_hid_command_dispatch_123e
flow_hid_command_dispatch_123a:
    movlb       0x0
    bsf         ram_0x0A4, 4, BANKED
flow_hid_command_dispatch_123e:
    movlb       0x1
    btfsc       ram_0x02A, 0, BANKED
    bra         flow_hid_command_dispatch_124a
    movlb       0x0
    bcf         ram_0x0A4, 5, BANKED
    bra         flow_hid_command_dispatch_124e
flow_hid_command_dispatch_124a:
    movlb       0x0
    bsf         ram_0x0A4, 5, BANKED
flow_hid_command_dispatch_124e:
    movff       ram_0x12C, ram_0x060
    movff       ram_0x12D, ram_0x061
    movff       ram_0x12E, ram_0x062
    movff       ram_0x12F, ram_0x063
    movff       ram_0x130, ram_0x064
    movff       ram_0x131, ram_0x065
    movff       ram_0x132, ram_0x05F
    movff       ram_0x133, ram_0x09B
    movff       ram_0x134, ram_0x09C
    movff       ram_0x135, ram_0x09D
    movff       ram_0x136, ram_0x09E
    movff       ram_0x138, ram_0x0B4
    movf        input_select_mirror, W, BANKED
    xorwf       input_select, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         ram_0x094, 0, BANKED
    movf        logical_volume_3, W, BANKED
    xorwf       computed_volume_3, W, BANKED
    bnz         flow_hid_command_dispatch_129c
    movf        logical_volume_2, W, BANKED
    xorwf       computed_volume_2, W, BANKED
    bnz         flow_hid_command_dispatch_129c
    movf        logical_volume_1, W, BANKED
    xorwf       computed_volume_1, W, BANKED
    bnz         flow_hid_command_dispatch_129c
    movf        logical_volume, W, BANKED
    xorwf       computed_volume, W, BANKED
flow_hid_command_dispatch_129c:
    bz          flow_hid_command_dispatch_12a2
    bsf         event_flags, 3, BANKED
    bsf         ram_0x094, 1, BANKED
flow_hid_command_dispatch_12a2:
    movf        ram_0x0AC, W, BANKED
    xorwf       ram_0x09B, W, BANKED
    bz          flow_hid_command_dispatch_12ac
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
flow_hid_command_dispatch_12ac:
    movf        ram_0x0AD, W, BANKED
    xorwf       ram_0x09C, W, BANKED
    bz          flow_hid_command_dispatch_12b6
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
flow_hid_command_dispatch_12b6:
    movf        ram_0x0AE, W, BANKED
    xorwf       ram_0x09D, W, BANKED
    bz          flow_hid_command_dispatch_12c0
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
flow_hid_command_dispatch_12c0:
    movf        ram_0x0AF, W, BANKED
    xorwf       ram_0x09E, W, BANKED
    bz          flow_hid_command_dispatch_12ca
    bsf         event_flags, 3, BANKED
    bsf         ram_0x0BD, 3, BANKED
flow_hid_command_dispatch_12ca:
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x04C, ACCESS
    movlw       0x01
    btfss       active_flags, 5, ACCESS
    movlw       0x00
    xorwf       ram_0x04C, F, ACCESS
    bz          flow_hid_command_dispatch_12e0
    bsf         event_flags, 5, BANKED
    bsf         ram_0x094, 3, BANKED
flow_hid_command_dispatch_12e0:
    movf        ram_0x0B0, W, BANKED
    xorwf       ram_0x0A4, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 6, BANKED
    movf        ram_0x0B4, W, BANKED
    xorwf       ram_0x0B1, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         ram_0x07F, 1, BANKED
    movf        ram_0x060, W, BANKED
    cpfseq      ram_0x0A5, BANKED
    bra         flow_hid_command_dispatch_1324
    movf        ram_0x0A6, W, BANKED
    lfsr        FSR2, 0x0061
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        ram_0x0A7, W, BANKED
    lfsr        FSR2, 0x0062
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        ram_0x0A8, W, BANKED
    lfsr        FSR2, 0x0063
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        ram_0x0A9, W, BANKED
    lfsr        FSR2, 0x0064
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        ram_0x065, W, BANKED
    xorwf       ram_0x0AA, W, BANKED
    btfss       STATUS, 2, ACCESS
flow_hid_command_dispatch_1324:
    bsf         event_flags, 4, BANKED
    movff       input_select, input_select_mirror
    call        copy_computed_volume_to_logical_volume, 0x0
    btfss       active_flags, 4, ACCESS
    bra         flow_hid_command_dispatch_1342
    bsf         active_flags, 5, ACCESS
    bra         flow_hid_command_dispatch_1344
flow_hid_command_dispatch_1342:
    bcf         active_flags, 5, ACCESS
flow_hid_command_dispatch_1344:
    movff       ram_0x0A4, ram_0x0B0
    movff       ram_0x060, ram_0x0A5
    movff       ram_0x061, ram_0x0A6
    movff       ram_0x062, ram_0x0A7
    movff       ram_0x063, ram_0x0A8
    movff       ram_0x064, ram_0x0A9
    movff       ram_0x065, ram_0x0AA
    movff       ram_0x0B4, ram_0x0B1
    movff       ram_0x09B, ram_0x0AC
    movff       ram_0x09C, ram_0x0AD
    movff       ram_0x09D, ram_0x0AE
    movff       ram_0x09E, ram_0x0AF
flow_hid_command_dispatch_1374:
    movlw       0x05
    bra         flow_hid_command_dispatch_1384
flow_hid_command_dispatch_1378:
    movlb       0x1
    decf        ram_0x01B, W, BANKED
    bnz         flow_hid_command_dispatch_138a
    call        main_core_service_4942, 0x0
    movlw       0x06
flow_hid_command_dispatch_1384:
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    bra         flow_hid_command_dispatch_112e
flow_hid_command_dispatch_138a:
    movf        ram_0x01B, W, BANKED
    xorlw       0x02
    bz          flow_hid_command_dispatch_1392
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1392:
    call        main_core_service_4942, 0x0
    bra         flow_hid_command_dispatch_1374
flow_hid_command_dispatch_1398:
    movlb       0x1
    movf        ram_0x01B, W, BANKED
    xorlw       0x0F
    btfsc       STATUS, 2, ACCESS
    bsf         active_flags, 7, ACCESS
flow_hid_command_dispatch_13a2:
    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x07
    bnz         flow_hid_command_dispatch_13ba
    movlb       0x1
    tstfsz      ram_0x01B, BANKED
    bra         flow_hid_command_dispatch_13ba
    movlb       0x0
    clrf        ram_0x0C5, BANKED
    movlw       0x56
    movwf       ram_0x083, BANKED
    clrf        ram_0x082, BANKED
flow_hid_command_dispatch_13ba:
    bcf         RCSTA, 4, ACCESS
    bsf         active_flags, 0, ACCESS
    movlb       0x0
    clrf        rx_frame_position, BANKED
    clrf        rx_ring_wr, BANKED
    clrf        rx_ring_rd, BANKED
    call        main_flash_service_2bb8, 0x0
flow_hid_command_dispatch_13ca:
    movff       i2c_coeff_2, ram_0x0C1
    bra         flow_hid_command_dispatch_112e
flow_hid_command_dispatch_13d0:
    movlw       0xA0
    movlb       0x0
    movwf       computed_volume, BANKED
    setf        computed_volume_1, BANKED
    setf        computed_volume_2, BANKED
    setf        computed_volume_3, BANKED
    movlw       0x01
    movwf       input_select, BANKED
    movlw       0x03
    movwf       ram_0x05F, ACCESS
    clrf        ram_0x060, BANKED
    clrf        ram_0x061, BANKED
    clrf        ram_0x062, BANKED
    movlw       0x01
    movwf       ram_0x063, BANKED
    movwf       ram_0x064, BANKED
    movwf       ram_0x065, BANKED
    movwf       ram_0x0B4, BANKED
    movlw       0x04
    movwf       ram_0x0B8, BANKED
    clrf        ram_0x09B, BANKED
    clrf        ram_0x09C, BANKED
    clrf        ram_0x09D, BANKED
    clrf        ram_0x09E, BANKED
    clrf        i2c_coeff_3, ACCESS
flow_hid_command_dispatch_1402:
    movlw       0xC0
    addwf       i2c_coeff_3, W, ACCESS
    call        fsr2_page2_from_W, 0x0       ; W05-E02: FSR2=0x0200|W (helper clobbers W with 0x02; setf uses no W)
    setf        INDF2, ACCESS
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x1D
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_1402
    clrf        i2c_coeff_3, ACCESS
flow_hid_command_dispatch_141a:
    movlw       0x00
    addwf       i2c_coeff_3, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    setf        INDF2, ACCESS
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x0E
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_141a
    movlb       0x0
    bsf         ram_0x0BD, 0, BANKED
    bsf         ram_0x0BD, 5, BANKED
    bsf         ram_0x0BD, 4, BANKED
    bsf         ram_0x0BD, 1, BANKED
    bsf         ram_0x0BD, 2, BANKED
    bsf         ram_0x0BD, 3, BANKED
    bsf         event_flags, 0, BANKED
    call        main_core_service_265c, 0x0
    clrf        ram_0x008, ACCESS
    setf        ram_0x007, ACCESS
    clrf        ram_0x009, ACCESS
    call        main_flash_service_46de, 0x0
    goto        flash_entry_quiet_shutdown      ; V3.2+: pop-free reset path
    bra         flow_hid_command_dispatch_15aa
fw_update_init_sequence:
    movlb       0x0
    tstfsz      ram_0x0CB, BANKED
    bra         flow_hid_command_dispatch_14fc
    clrf        ram_0x07C, BANKED
    clrf        ram_0x07D, BANKED
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
    clrf        ram_0x086, BANKED
    clrf        ram_0x087, BANKED
    clrf        ram_0x084, BANKED
    clrf        ram_0x085, BANKED
    call        prep_bank1_ram004, 0x0
    movlw       0xC7
    movwf       ram_0x003, ACCESS
    movlw       0x0A
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    call        prep_bank1_ram004, 0x0
    movlw       0x9A
    movwf       ram_0x003, ACCESS
    movlw       0x2D
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    call        prep_bank1_ram004, 0x0
    movlw       0xD1
    movwf       ram_0x003, ACCESS
    movlw       0x08
    movwf       ram_0x005, ACCESS
    call        ram_block_clear, 0x0
    call        factory_reset_status_emit, 0x0
    movlw       0x05
    movwf       ram_0x006, ACCESS
    movlw       0xDC
    movwf       ram_0x005, ACCESS
    movlb       0x1
    movlw       0x01
    movwf       ram_0x008, ACCESS
    movlw       0xD1
    movwf       ram_0x007, ACCESS
    movlw       0x08
    movwf       ram_0x009, ACCESS
    call        uart_rx_with_framing, 0x0
    movwf       ram_0x04C, ACCESS
    movlw       0x05
    subwf       ram_0x04C, W, ACCESS
    bnc         flow_hid_command_dispatch_14fa
    movlw       0x01
    movwf       ram_0x0CB, BANKED
    clrf        i2c_coeff_3, ACCESS
flow_hid_command_dispatch_14ce:
    movf        i2c_coeff_3, W, ACCESS
    addlw       0x4D
    call        fsr2_page0_read_w, 0x0               ; W04-E03
    movwf       ram_0x04C, ACCESS
    movlw       0xD1
    addwf       i2c_coeff_3, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    movf        INDF2, W, ACCESS
    xorwf       ram_0x04C, W, ACCESS
    bz          flow_hid_command_dispatch_14f0
    movlb       0x0
    clrf        ram_0x0CB, BANKED
flow_hid_command_dispatch_14f0:
    incf        i2c_coeff_3, F, ACCESS
    movlw       0x05
    cpfsgt      i2c_coeff_3, ACCESS
    bra         flow_hid_command_dispatch_14ce
    bra         flow_hid_command_dispatch_14fc
flow_hid_command_dispatch_14fa:
    clrf        ram_0x0CB, BANKED
flow_hid_command_dispatch_14fc:
    movlb       0x0
    movf        ram_0x0CB, W, BANKED
    bnz         flow_hid_command_dispatch_1504
    bra         flow_hid_command_dispatch_13ca
flow_hid_command_dispatch_1504:
    rcall       fw_update_relay
    bra         flow_hid_command_dispatch_13ca
flow_hid_command_dispatch_150a:
    movff       ram_0x11E, i2c_coeff_1
    movff       ram_0x11F, i2c_coeff_0
    movff       i2c_coeff_2, ram_0x0C1
    call        main_core_service_2328, 0x0
    movf        ram_0x07D, W, BANKED
    xorwf       i2c_coeff_1, W, ACCESS
    bnz         flow_hid_command_dispatch_1524
    movf        ram_0x07C, W, BANKED
    xorwf       i2c_coeff_0, W, ACCESS
flow_hid_command_dispatch_1524:
    bnz         flow_hid_command_dispatch_1532
    call        main_core_service_4672, 0x0
    movlw       0xAA
    movlb       0x1
    movwf       ram_0x05C, BANKED
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1532:
    movlw       0x11
    movlb       0x1
    movwf       ram_0x05B, BANKED
    movlb       0x0
    clrf        ram_0x084, BANKED
    clrf        ram_0x085, BANKED
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
    clrf        ram_0x086, BANKED
    clrf        ram_0x087, BANKED
    clrf        ram_0x07C, BANKED
    clrf        ram_0x07D, BANKED
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_154c:
    movlb       0x1
    clrf        ram_0x01A, BANKED
    bra         flow_hid_command_dispatch_15aa
hid_cmd_xor_dispatch:
    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x01
    bz          flow_hid_command_dispatch_15aa
    xorlw       0x03
    bz          flow_hid_command_dispatch_15aa
    xorlw       0x01
    bnz         flow_hid_command_dispatch_1562
    bra         flow_hid_command_dispatch_10d0
flow_hid_command_dispatch_1562:
    xorlw       0x07
    bnz         flow_hid_command_dispatch_1568
    bra         flow_hid_command_dispatch_1134
flow_hid_command_dispatch_1568:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_156e
    bra         flow_hid_command_dispatch_11ce
flow_hid_command_dispatch_156e:
    xorlw       0x03
    bnz         flow_hid_command_dispatch_1574
    bra         flow_hid_command_dispatch_1378
flow_hid_command_dispatch_1574:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_157a
    bra         flow_hid_command_dispatch_13a2
flow_hid_command_dispatch_157a:
    xorlw       0x0F
    bnz         flow_hid_command_dispatch_1580
    bra         flow_hid_command_dispatch_13a2
flow_hid_command_dispatch_1580:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_1586
    bra         flow_hid_command_dispatch_13a2
flow_hid_command_dispatch_1586:
    xorlw       0x03
    bnz         flow_hid_command_dispatch_158c
    bra         flow_hid_command_dispatch_13a2
flow_hid_command_dispatch_158c:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_1592
    bra         flow_hid_command_dispatch_13a2
flow_hid_command_dispatch_1592:
    xorlw       0x07
    bnz         flow_hid_command_dispatch_1598
    bra         flow_hid_command_dispatch_1398
flow_hid_command_dispatch_1598:
    xorlw       0x4C
    bnz         flow_hid_command_dispatch_159e
    bra         flow_hid_command_dispatch_13d0
flow_hid_command_dispatch_159e:
    xorlw       0x01
    bz          flow_hid_command_dispatch_150a
    xorlw       0x03
    bnz         hid_cmd_diag_memread_probe
    bra         fw_update_init_sequence
hid_cmd_diag_memread_probe:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_15a8
    goto        hid_cmd_diag_memread
flow_hid_command_dispatch_15a8:
    xorlw       0x07                            ; V3.2 Tier-1: cumulative 0x43 ^ 0x07 = 0x44
    bnz         flow_hid_command_dispatch_15a8b ; not 0x44 either -> fall through
    goto        hid_cmd_diag_snapshot           ; cmd 0x44 (V3.2 Tier-1 diag snapshot)
flow_hid_command_dispatch_15a8b:
    bra         flow_hid_command_dispatch_154c
flow_hid_command_dispatch_15aa:
    movlb       0x1
    clrf        ram_0x01A, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_15b0
; Address : 0x15B0
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_15b0:
    movlw       0x1A
    addwf       i2c_coeff_3, W, ACCESS
    bra         setup_fsr2_page_1_or_2


; ---------------------------------------------------------------------------
; Function: main_core_service_15be
; Address : 0x15BE
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_15be:
    movlw       0xBE
    addwf       i2c_coeff_3, W, ACCESS
    call        fsr2_page2_from_W, 0x0       ; W05-E02: FSR2=0x0200|W (helper clobbers W with 0x02; setf uses no W)
    setf        INDF2, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: fw_update_relay                (USB-HID -> UART firmware update bridge)
; Address : 0x15CE
; ---------------------------------------------------------------------------
; Bridges firmware-update payload between the USB host and the downstream
; PB on the current loop. Once the host sends the FW-update HID command,
; this routine:
;   1. Stages the 8-byte HID OUT report at FSR2=0x01E5 and copies it into
;      the working buffer at FSR1=0x001D.
;   2. Forwards each Intel HEX record to the downstream UART through
;      main_uart_service_43a2 (which uses tblrd_lookup + uart_tx_byte_blocking
;      to emit the ASCII hex pair).
;   3. Reads the response back via uart_rx_with_framing and returns it
;      through the USB IN endpoint.
; This routine ONLY runs in firmware-update mode (entered by HID opcode);
; it has no role in normal command flow. The protocol is essentially
; "USB HID = full-duplex Intel HEX over UART" so PB1 can flash both itself
; and the downstream PB2 from a single host connection.
; ---------------------------------------------------------------------------
fw_update_relay:
    lfsr        FSR2, 0x01E5
    lfsr        FSR1, 0x001D
    movlw       0x08
flow_fw_update_relay_15d8:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         flow_fw_update_relay_15d8
    movlw       0x02
    movwf       ram_0x049, ACCESS
flow_fw_update_relay_15e4:
    movlw       0x1A
    addwf       ram_0x049, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    movf        INDF2, W, ACCESS
    movwf       ram_0x04A, ACCESS
    movlw       0xC0
    movlb       0x0
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bc          flow_fw_update_relay_1634
    movff       ram_0x04A, ram_0x045
    clrf        ram_0x048, ACCESS
flow_fw_update_relay_1606:
    btfss       ram_0x07D, 5, BANKED
    bra         flow_fw_update_relay_1610
    movlw       0x01
    movwf       ram_0x044, ACCESS
    bra         flow_fw_update_relay_1612
flow_fw_update_relay_1610:
    clrf        ram_0x044, ACCESS
flow_fw_update_relay_1612:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x07C, F, BANKED
    rlcf        ram_0x07D, F, BANKED
    btfsc       ram_0x045, 0, ACCESS
    bsf         ram_0x07C, 0, BANKED
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x045, F, ACCESS
    movf        ram_0x044, W, ACCESS
    bz          flow_fw_update_relay_162c
    movlw       0x02
    xorwf       ram_0x07C, F, BANKED
    movlw       0x44
    xorwf       ram_0x07D, F, BANKED
flow_fw_update_relay_162c:
    incf        ram_0x048, F, ACCESS
    movlw       0x07
    cpfsgt      ram_0x048, ACCESS
    bra         flow_fw_update_relay_1606
flow_fw_update_relay_1634:
    movlw       0x40
    subwf       ram_0x084, W, BANKED
    movlw       0x00
    subwfb      ram_0x085, W, BANKED
    bc          flow_fw_update_relay_1640
    bra         flow_fw_update_relay_18d0
flow_fw_update_relay_1640:
    movlw       0xC0
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bnc         flow_fw_update_relay_164c
    bra         flow_fw_update_relay_18d0
flow_fw_update_relay_164c:
    movlw       0x0F
    andwf       ram_0x084, W, BANKED
    movwf       ram_0x08A, BANKED
    clrf        ram_0x08B, BANKED
    iorwf       ram_0x08B, W, BANKED
    bz          flow_fw_update_relay_165a
    bra         flow_fw_update_relay_182e
flow_fw_update_relay_165a:
    movf        ram_0x087, W, BANKED
    iorwf       ram_0x086, W, BANKED
    bnz         flow_fw_update_relay_1662
    bra         flow_fw_update_relay_179c
flow_fw_update_relay_1662:
    movf        ram_0x086, W, BANKED
    addwf       ram_0x080, F, BANKED
    movlw       0x00
    addwfc      ram_0x081, F, BANKED
    movf        ram_0x087, W, BANKED
    addwf       ram_0x080, F, BANKED
    movlw       0x00
    addwfc      ram_0x081, F, BANKED
    comf        ram_0x080, W, BANKED
    movwf       ram_0x01B, ACCESS
    comf        ram_0x081, W, BANKED
    movwf       ram_0x01C, ACCESS
    movlw       0xF1
    addwf       ram_0x01B, W, ACCESS
    movwf       ram_0x080, BANKED
    movlw       0xFF
    addwfc      ram_0x01C, W, ACCESS
    movwf       ram_0x081, BANKED
    movf        ram_0x080, W, BANKED
    call        main_uart_service_43a2, 0x0
    rcall       emit_crlf
    movff       ram_0x080, ram_0x01B
    swapf       ram_0x01B, F, ACCESS
    movlw       0x0F
    andwf       ram_0x01B, F, ACCESS
    andwf       ram_0x01B, F, ACCESS
    movf        ram_0x01B, W, ACCESS
    rcall       hex_lookup_table_ptr                ; indexed TBLPTR -> hex_lookup_table
    movlw       0x9A
    addwf       ram_0x04B, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    tblrd*
    movff       TABLAT, INDF2
    movff       ram_0x080, ram_0x01B
    movlw       0x0F
    andwf       ram_0x01B, F, ACCESS
    movf        ram_0x01B, W, ACCESS
    rcall       hex_lookup_table_ptr                ; indexed TBLPTR -> hex_lookup_table
    movlw       0x9B
    addwf       ram_0x04B, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    tblrd*
    movff       TABLAT, INDF2
    movlw       0x9C
    addwf       ram_0x04B, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    clrf        INDF2, ACCESS
    movlw       0x02
    addwf       ram_0x04B, F, ACCESS
    movlb       0x0
    clrf        ram_0x09F, BANKED
flow_fw_update_relay_16fa:
    clrf        ram_0x006, ACCESS
    movlw       0x0A
    movwf       ram_0x005, ACCESS
    movlb       0x1
    movlw       0x01
    movwf       ram_0x008, ACCESS
    movlw       0xC7
    movwf       ram_0x007, ACCESS
    movlw       0x0A
    movwf       ram_0x009, ACCESS
    call        uart_rx_with_framing, 0x0
    movff       ram_0x1C8, ram_0x003
    movlb       0x1
    movf        rx_ring_wr, W, BANKED
    call        intel_hex_checksum_update, 0x0
    movlb       0x0
    xorwf       ram_0x080, W, BANKED
    bnz         flow_fw_update_relay_172a
    movlw       0x01
    movwf       ram_0x043, ACCESS
    bra         flow_fw_update_relay_1796
flow_fw_update_relay_172a:
    clrf        ram_0x043, ACCESS
    clrf        ram_0x019, ACCESS
    movlw       0x1D
    movwf       ram_0x018, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    movlb       0x0
    movff       ram_0x09F, ram_0x012
    clrf        ram_0x013, ACCESS
    clrf        ram_0x015, ACCESS
    movlw       0x0A
    movwf       ram_0x014, ACCESS
    movlw       0x25
    call        main_core_service_41b6, 0x0
    movwf       ram_0x01B, ACCESS
    clrf        ram_0x019, ACCESS
    movff       ram_0x01B, ram_0x018
    call        uart_tx_block_from_buffer, 0x0
    movlw       0x21
    call        uart_tx_byte_blocking, 0x0
    call        main_uart_service_4860, 0x0
    rcall       emit_crlf
    movlw       0x19
    movlb       0x0
    subwf       ram_0x09F, W, BANKED
    bc          flow_fw_update_relay_1792
    incf        ram_0x09F, F, BANKED
    movlb       0x1
    movlw       0x01
    movwf       ram_0x019, ACCESS
    movlw       0x9A
    movwf       ram_0x018, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    rcall       emit_crlf
    bra         flow_fw_update_relay_1796
flow_fw_update_relay_1792:
    incf        ram_0x09F, F, BANKED
    bra         flow_fw_update_relay_18dc
flow_fw_update_relay_1796:
    movf        ram_0x043, W, ACCESS
    bnz         flow_fw_update_relay_179e
    bra         flow_fw_update_relay_16fa
flow_fw_update_relay_179c:
    clrf        ram_0x08E, BANKED
flow_fw_update_relay_179e:
    movlw       0xBF
    movlb       0x0
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bc          flow_fw_update_relay_182e
    movlw       0x04
    subwf       ram_0x08E, W, BANKED
    bc          flow_fw_update_relay_17bc
    incf        ram_0x08E, F, BANKED
    movlw       0x0A
    call        timer3_blocking_delay_ms_W, 0x0 ; W04-E08 factored (10 ms)
flow_fw_update_relay_17bc:
    movff       ram_0x084, ram_0x086
    movff       ram_0x085, ram_0x087
    movlw       0x3A
    movlb       0x1
    movwf       ram_0x09A, BANKED
    movlw       0x31
    movwf       ram_0x09B, BANKED
    movlw       0x30
    movwf       ram_0x09C, BANKED
    movff       ram_0x087, ram_0x01B
    rcall       nibble_to_hex_ascii_from_01B
    movff       TABLAT, ram_0x19D
    movff       ram_0x087, ram_0x01B
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x19E
    movff       ram_0x086, ram_0x01B
    rcall       nibble_to_hex_ascii_from_01B
    movff       TABLAT, ram_0x19F
    movff       ram_0x086, ram_0x01B
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x1A0
    movlw       0x30
    movwf       ram_0x0A1, BANKED
    movwf       ram_0x0A2, BANKED
    clrf        ram_0x0A3, BANKED
    movlw       0x09
    movwf       ram_0x04B, ACCESS
    call        main_uart_service_4860, 0x0
    movlb       0x1
    movlw       0x01
    movwf       ram_0x019, ACCESS
    movlw       0x9A
    movwf       ram_0x018, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    movlb       0x0
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
flow_fw_update_relay_182e:
    movlw       0xBF
    subwf       ram_0x084, W, BANKED
    movlw       0x77
    subwfb      ram_0x085, W, BANKED
    bc          flow_fw_update_relay_18cc
    btfss       ram_0x084, 0, BANKED
    bra         flow_fw_update_relay_18bc
    movff       ram_0x046, ram_0x01B
    rcall       nibble_to_hex_ascii_from_01B
    movff       TABLAT, ram_0x02F
    movff       ram_0x046, ram_0x01B
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x030
    movff       ram_0x04A, ram_0x01B
    rcall       nibble_to_hex_ascii_from_01B
    movff       TABLAT, ram_0x031
    movff       ram_0x04A, ram_0x01B
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, ram_0x032
    clrf        ram_0x033, ACCESS
    clrf        ram_0x019, ACCESS
    movlw       0x2F
    movwf       ram_0x018, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    clrf        ram_0x047, ACCESS
    bra         flow_fw_update_relay_18a0
flow_fw_update_relay_1884:
    movf        ram_0x047, W, ACCESS
    addlw       0x2F
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x9A
    addwf       ram_0x04B, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x01
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    incf        ram_0x047, F, ACCESS
    incf        ram_0x04B, F, ACCESS
flow_fw_update_relay_18a0:
    movf        ram_0x047, W, ACCESS
    addlw       0x2F
    call        fsr2_page0_read_w, 0x0               ; W04-E03
    bnz         flow_fw_update_relay_1884
    movlw       0x9A
    addwf       ram_0x04B, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    clrf        INDF2, ACCESS
    bra         flow_fw_update_relay_18c0
flow_fw_update_relay_18bc:
    movff       ram_0x04A, ram_0x046
flow_fw_update_relay_18c0:
    movf        ram_0x04A, W, ACCESS
    movlb       0x0
    addwf       ram_0x080, F, BANKED
    movlw       0x00
    addwfc      ram_0x081, F, BANKED
    bra         flow_fw_update_relay_18d0
flow_fw_update_relay_18cc:
    clrf        ram_0x080, BANKED
    clrf        ram_0x081, BANKED
flow_fw_update_relay_18d0:
    infsnz      ram_0x084, F, BANKED
    incf        ram_0x085, F, BANKED
    incf        ram_0x049, F, ACCESS
    movlw       0x1F
    cpfsgt      ram_0x049, ACCESS
    bra         flow_fw_update_relay_15e4
flow_fw_update_relay_18dc:
    return      0

; ---------------------------------------------------------------------------
; Helper: emit_crlf                       (W03-E06 size-opt wrapper)
; ---------------------------------------------------------------------------
; Factored CR+LF emitter for the 3 sites in fw_update_relay that bracket
; Intel-HEX echo lines. Per site this collapses 12 B (two inline CR/LF
; emit pairs of movlw+call) down to 2 B (rcall emit_crlf). uart_tx_byte_blocking
; lives at 0x45F2, which is outside the ±1024-word rcall window from this
; placement, so the final LF uses `goto` as a tail-call — the outer
; uart_tx_byte_blocking `return` unwinds straight to the emit_crlf caller.
;
; Register/flag contract:
;   • W returns = 0x0A (clobbered by design — all 3 callers overwrite W
;     before reading it; audited at lines ~1086-1089, 1163-1166, 1178-1181).
;   • STATUS / BSR are not inspected after the CRLF pair at any call site.
;   • Stack depth grows by 1 (rcall emit_crlf) + 1 (call uart_tx_byte_blocking)
;     transiently; the second emit uses goto so no extra stack frame.
; ---------------------------------------------------------------------------
emit_crlf:
    movlw       0x0D                                ; CR
    call        uart_tx_byte_blocking, 0x0
    movlw       0x0A                                ; LF (tail-call, goto preserves caller's return)
    goto        uart_tx_byte_blocking


; ---------------------------------------------------------------------------
; Helper: nibble_to_hex_ascii_from_01B      (high-nibble preamble + fall-through)
; ---------------------------------------------------------------------------
; Factors the 4-instruction "swapf + movlw 0x0F + andwf" preamble emitted by
; the fw_update_relay hex-format emitter before each high-nibble
; rcall nibble_to_hex_ascii. Fall-through into nibble_to_hex_ascii reuses the
; shared `andwf ram_0x01B, F` first instruction (W=0x0F is already loaded
; here), so this helper is only 2 instructions (4 B). Net savings per site:
; 8 B preamble -> 2 B rcall, minus 4 B helper = 20 B across the 4 sites at
; lines ~1218, 1228, 1262, 1272. STATUS flags on return are identical to the
; inlined version (same `andwf` sequence). W holds 0x0F on entry to
; nibble_to_hex_ascii in both layouts.
; ---------------------------------------------------------------------------
nibble_to_hex_ascii_from_01B:
    swapf       ram_0x01B, F, ACCESS                ; high nibble -> low
    movlw       0x0F                                ; mask, consumed by shared andwf below

; ---------------------------------------------------------------------------
; Function: nibble_to_hex_ascii            (low nibble -> ASCII '0'..'F')
; Address : 0x18DE
; ---------------------------------------------------------------------------
; Caller stages the nibble in ram_0x01B; W is the AND mask (typically 0x0F)
; that selects which nibble to consume. Returns the ASCII byte in TABLAT
; via tblrd of hex_lookup_table[ram_0x01B]. Mirror of tblrd_lookup which
; uses ram_0x004 for the firmware-update path.
; ---------------------------------------------------------------------------
nibble_to_hex_ascii:
    andwf       ram_0x01B, F, ACCESS
    movf        ram_0x01B, W, ACCESS
    rcall       hex_lookup_table_ptr                ; W=nibble -> TBLPTR -> hex_lookup_table[nibble]
    tblrd*
    return      0

; ---------------------------------------------------------------------------
; Helper: hex_lookup_table_ptr
; ---------------------------------------------------------------------------
; W holds the low nibble (caller has already ANDed with 0x0F). Adds the LOW
; byte of hex_lookup_table to W, loads TBLPTRL/TBLPTRH. W is clobbered by the
; final movlw of HIGH(hex_lookup_table). Callers typically follow with tblrd*.
; Shared by nibble_to_hex_ascii, tblrd_lookup, and the two inline nibble
; emitters in main_uart_service_43a2's feeder. Near callers use rcall (2 B);
; distant callers (tblrd_lookup at ~0x424C) use call (4 B).
; ---------------------------------------------------------------------------
hex_lookup_table_ptr:
    addlw       LOW(hex_lookup_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(hex_lookup_table)
    movwf       TBLPTRH, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: cmd_dispatch_gated            (gated post-parse command dispatcher)
; Address : 0x18EE
; ---------------------------------------------------------------------------
; Called by every incoming serial command after main_uart_service_1be6 has
; staged route/cmd/data. The first instruction tests active_flags.bit3 — the
; "active gate" — and silently drops the command at cmd_gate_reject when it
; is clear.  This single gate is what made the V1.62b CONTROL reconnect bug
; visible: a missed wake frame leaves every command discarded here.
;
; Below the gate, this routine fans out the per-cmd work:
;   • input-channel I2C pair updates (dispatch by ram_0x093 = parsed cmd_low)
;   • DSP volume/mute/preset apply through volume_dsp_write (Fix B/B') —
;     the only V3.1+ verified-write path
;   • V3.2 reconnect (active_flags.bit7) cancels any in-flight preset job,
;     mutes the DSP, and replays the preset table from main_core_service_4574
;
; Calls: i2c_secondary_dev_write, main_i2c_service_48e2, main_core_service_4516,
;        volume_dsp_write, i2c_tas3108_coeff_write, main_i2c_service_381c,
;        main_i2c_service_2100, main_usb_service_45a2, main_timer_service_48a6.
; ---------------------------------------------------------------------------
cmd_dispatch_gated:
    movff       WREG, ram_0x0FD
    btfss       active_flags, 3, ACCESS
    bra         cmd_gate_reject
    btfss       event_flags, 1, BANKED
    bra         flow_cmd_dispatch_gated_19a8
    bsf         event_flags, 3, BANKED
    bra         flow_cmd_dispatch_gated_1970
; W05-E07: tail-call merge — 4 callers previously did
;   rcall cmd_dispatch_gated_i2c_pair / bra flow_cmd_dispatch_gated_1990.
; Converted to `bra cmd_dispatch_gated_i2c_pair`; helper tail is
; `bra flow_cmd_dispatch_gated_1990` instead of `return 0`. Saves
; 4 * 2 B by removing the trailing `bra` at each caller; helper tail
; size unchanged (return -> bra, both 1 word).
flow_cmd_dispatch_gated_18fe:
    movlw       0x09
    movwf       ram_0x006, ACCESS
    movlw       0x70
    bra         cmd_dispatch_gated_i2c_pair
flow_cmd_dispatch_gated_1918:
    movlw       0x0A
    movwf       ram_0x006, ACCESS
    movlw       0xB0
    bra         cmd_dispatch_gated_i2c_pair
flow_cmd_dispatch_gated_1932:
    movlw       0x08
    movwf       ram_0x006, ACCESS
    movlw       0x30
    bra         cmd_dispatch_gated_i2c_pair
flow_cmd_dispatch_gated_194c:
    movlw       0x0B
    movwf       ram_0x006, ACCESS
    movlw       0xF0
    bra         cmd_dispatch_gated_i2c_pair
cmd_dispatch_gated_i2c_pair:
    movwf       ram_0x00D, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movf        ram_0x00D, W, ACCESS
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        main_i2c_service_48e2, 0x0
    bra         flow_cmd_dispatch_gated_1990
flow_cmd_dispatch_gated_1966:
    call        main_core_service_4516, 0x0
    movlw       0x01
    call        i2c_tas3108_reg1f_write, 0x0
    bra         flow_cmd_dispatch_gated_1990
flow_cmd_dispatch_gated_1970:
    movf        ram_0x093, W, BANKED
    bz          flow_cmd_dispatch_gated_1966
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_18fe
    xorlw       0x03
    bz          flow_cmd_dispatch_gated_1918
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_1932
    xorlw       0x07
    bz          flow_cmd_dispatch_gated_194c
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_1966
    xorlw       0x03
    bz          flow_cmd_dispatch_gated_1966
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_1966
flow_cmd_dispatch_gated_1990:
    rcall       usb_mailbox_service_05          ; W02-E03: factored 6-line pattern
    movlb       0x0
    bcf         event_flags, 1, BANKED
    bsf         ram_0x0BD, 0, BANKED
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_19a8:
    movlb       0x0
    btfss       event_flags, 3, BANKED
    bra         flow_cmd_dispatch_gated_1a76
    ; V3.2: skip unmute if a user cmd 0x03 mute arrived this pass.
    ; event_flags.5 is only set by cmd 0x03 mute/unmute handlers;
    ; preset_force_mute clears it, so a set bit here means user intent.
    btfss       event_flags, 5, BANKED
    bcf         active_flags, 4, ACCESS
    ; Leave event_flags.5 for the mute handler at 1a9c to process.
    bsf         event_flags, 6, BANKED
    clrf        ram_0x0A4, BANKED
    movff       ram_0x0A4, ram_0x0B0
    clrf        ram_0x09A, BANKED
    bra         flow_cmd_dispatch_gated_19d6
flow_cmd_dispatch_gated_19be:
    movff       ram_0x09B, ram_0x09A
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19c4:
    movff       ram_0x09C, ram_0x09A
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19ca:
    movff       ram_0x09D, ram_0x09A
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19d0:
    movff       ram_0x09E, ram_0x09A
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19d6:
    movf        ram_0x093, W, BANKED
    bz          flow_cmd_dispatch_gated_19be
    xorlw       0x05
    bz          flow_cmd_dispatch_gated_19c4
    xorlw       0x03
    bz          flow_cmd_dispatch_gated_19ca
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_19d0
flow_cmd_dispatch_gated_19e6:
    movf        ram_0x09A, W, BANKED
    addwf       computed_volume, W, BANKED
    movwf       ram_0x00D, ACCESS
    movlw       0x00
    addwfc      computed_volume_1, W, BANKED
    movwf       ram_0x00E, ACCESS
    movlw       0x00
    addwfc      computed_volume_2, W, BANKED
    movwf       ram_0x00F, ACCESS
    movlw       0x00
    addwfc      computed_volume_3, W, BANKED
    movwf       ram_0x010, ACCESS
    call        main_core_service_3e0a, 0x0
    movff       ram_0x00D, ram_0x012
    movff       ram_0x00E, ram_0x013
    movff       ram_0x00F, ram_0x014
    movff       ram_0x010, ram_0x015
    movlw       0x47
    movwf       ram_0x016, ACCESS
    movlw       0xC9
    movwf       ram_0x017, ACCESS
    movlw       0xEB
    movwf       ram_0x018, ACCESS
    movlw       0x3D
    movwf       ram_0x019, ACCESS
    call        main_core_service_2abc, 0x0
    movff       ram_0x012, ram_0x0ED
    movff       ram_0x013, ram_0x0EE
    movff       ram_0x014, ram_0x0EF
    movff       ram_0x015, ram_0x0F0
    movff       ram_0x0ED, ram_0x02F
    movff       ram_0x0EE, ram_0x030
    movff       ram_0x0EF, ram_0x031
    movff       ram_0x0F0, ram_0x032
    call        main_core_service_297e, 0x0
    movff       ram_0x02F, i2c_coeff_0
    movff       ram_0x030, i2c_coeff_1
    movff       ram_0x031, i2c_coeff_2
    movff       ram_0x032, i2c_coeff_3
    call        volume_dsp_write, 0x0       ; V3.1 Fix B: verified volume write
    rcall       usb_mailbox_service_05          ; W02-E03: factored 6-line pattern
    movlb       0x0
    bsf         ram_0x0BD, 0, BANKED
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_1a76:
    btfss       active_flags, 7, ACCESS
    bra         flow_cmd_dispatch_gated_1a9c
    ; V3.2: cancel any active preset job — reconnect does a full table apply
    movlb       0x2
    clrf        preset_job_state, BANKED
    bcf         T3CON, 0, ACCESS
    bcf         PIE2, 1, ACCESS
    bcf         PIR2, 1, ACCESS
    call        clrf_i2c_coeff_0123_and_write, 0x0  ; W03-E02: factored 5-line pattern
    call        main_core_service_4574, 0x0
    bsf         RCSTA, 4, ACCESS
    bcf         active_flags, 7, ACCESS
    movlb       0x0
    btfss       event_flags, 5, BANKED
    btfsc       active_flags, 4, ACCESS
    bra         flow_cmd_dispatch_gated_1a9c
    bsf         event_flags, 3, BANKED
flow_cmd_dispatch_gated_1a9c:
    movlb       0x0
    btfss       event_flags, 5, BANKED
    bra         flow_cmd_dispatch_gated_1aca
    btfss       active_flags, 4, ACCESS
    bra         flow_cmd_dispatch_gated_1ab6
    call        clrf_i2c_coeff_0123_and_write, 0x0  ; W03-E02: factored 5-line pattern
    bra         flow_cmd_dispatch_gated_1ab8
flow_cmd_dispatch_gated_1ab6:
    bsf         event_flags, 3, BANKED
flow_cmd_dispatch_gated_1ab8:
    rcall       usb_mailbox_service_05          ; W02-E03: factored 6-line pattern
    movlb       0x0
    bcf         event_flags, 5, BANKED
flow_cmd_dispatch_gated_1aca:
    btfss       event_flags, 6, BANKED
    bra         flow_cmd_dispatch_gated_1baa
    movlw       0x5F
    movwf       ram_0x014, ACCESS
    movlb       0x0
    btfsc       ram_0x0A4, 0, BANKED
    bra         flow_cmd_dispatch_gated_1ad8
    movlw       0x1C
    bra         flow_cmd_dispatch_gated_1ada
flow_cmd_dispatch_gated_1ad8:
    movlw       0x08
flow_cmd_dispatch_gated_1ada:
    rcall       i2c_381c_with_w_bank0           ; W05-E01: factored 3-line pattern
    btfsc       ram_0x0A4, 1, BANKED
    bra         flow_cmd_dispatch_gated_1aee
    movlw       0x44
    bra         flow_cmd_dispatch_gated_1af0
flow_cmd_dispatch_gated_1aee:
    movlw       0x30
flow_cmd_dispatch_gated_1af0:
    rcall       i2c_381c_with_w_bank0           ; W05-E01: factored 3-line pattern
    btfsc       ram_0x0A4, 2, BANKED
    bra         flow_cmd_dispatch_gated_1b04
    movlw       0x6C
    bra         flow_cmd_dispatch_gated_1b06
flow_cmd_dispatch_gated_1b04:
    movlw       0x58
flow_cmd_dispatch_gated_1b06:
    rcall       i2c_381c_with_w_bank0           ; W05-E01: factored 3-line pattern
    btfsc       ram_0x0A4, 3, BANKED
    bra         flow_cmd_dispatch_gated_1b1a
    movlw       0x94
    bra         flow_cmd_dispatch_gated_1b1c
flow_cmd_dispatch_gated_1b1a:
    movlw       0x80
flow_cmd_dispatch_gated_1b1c:
    rcall       i2c_381c_with_w_bank0           ; W05-E01: factored 3-line pattern
    btfsc       ram_0x0A4, 4, BANKED
    bra         flow_cmd_dispatch_gated_1b30
    movlw       0xBC
    bra         flow_cmd_dispatch_gated_1b32
flow_cmd_dispatch_gated_1b30:
    movlw       0xA8
flow_cmd_dispatch_gated_1b32:
    rcall       i2c_381c_with_w_bank0           ; W05-E01: factored 3-line pattern
    btfsc       ram_0x0A4, 5, BANKED
    bra         flow_cmd_dispatch_gated_1b46
    movlw       0xE4
    bra         flow_cmd_dispatch_gated_1b48
flow_cmd_dispatch_gated_1b46:
    movlw       0xD0
flow_cmd_dispatch_gated_1b48:
    movwf       ram_0x013, ACCESS
    call        main_i2c_service_381c, 0x0
    bra         flow_cmd_dispatch_gated_1b8c
flow_cmd_dispatch_gated_1b8c:
    rcall       usb_mailbox_service_05          ; W02-E03: factored 6-line pattern
    movlb       0x0
    bcf         event_flags, 6, BANKED
flow_cmd_dispatch_gated_1baa:
    btfss       event_flags, 4, BANKED
    bra         flow_cmd_dispatch_gated_1bc8
    rcall       main_i2c_service_2100
    movlb       0x0
    bcf         event_flags, 4, BANKED
    bsf         ram_0x0BD, 1, BANKED
    movlw       0x05
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        main_usb_service_45a2, 0x0
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_1bc8:
    movlb       0x0
    btfss       ram_0x07F, 0, BANKED
    bra         flow_cmd_dispatch_gated_1bd6
    bcf         ram_0x07F, 0, BANKED
    bsf         ram_0x0BD, 2, BANKED
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_1bd6:
    movlb       0x0
    btfss       ram_0x07F, 1, BANKED
    bra         cmd_gate_reject
    bcf         ram_0x07F, 1, BANKED
    bsf         ram_0x0BD, 2, BANKED
    call        main_timer_service_48a6, 0x0
cmd_gate_reject:
    return      0


; ---------------------------------------------------------------------------
; Helper : usb_mailbox_service_05          (W02-E03: factored 4-site pattern)
; ---------------------------------------------------------------------------
; Loads 0x05 into ram_0x0C1 (USB mailbox counter) with BSR=0x0, then runs the
; USB service routine at 0x45A2 if ram_0x0FD != 0 (btfss skips call when Z=1).
;
; BSR: enters any, exits at 0x0 (from movlb inside) or whatever main_usb_
;      service_45a2 leaves — all 4 callers immediately re-issue movlb 0x0,
;      so helper does not need to post-restore BSR.
; STATUS.Z: btfss consumes Z from the movf; post-return Z is
;           indeterminate. All 4 callers only execute bcf/bsf/call after,
;           none branch on Z.
; Savings : 4 sites × (14 B → 2 B) − 16 B helper = 32 B.
; ---------------------------------------------------------------------------
usb_mailbox_service_05:
    movlw       0x05
    movlb       0x0
    movwf       ram_0x0C1, BANKED
    movf        ram_0x0FD, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        main_usb_service_45a2, 0x0
    return      0


; ---------------------------------------------------------------------------
; Helper: i2c_381c_with_w_bank0                      (W05-E01 size-opt helper)
; ---------------------------------------------------------------------------
; Shared factor for the 3-instruction "stage W into ram_0x013, call
; main_i2c_service_381c, restore BSR=0" pattern used 5 times in the
; flow_cmd_dispatch_gated_1ada..1b32 chain.  Each caller has just loaded
; W via `movlw <imm>`, so W carries the I2C register-byte argument.
;
; Semantics preserved: the helper stores W into ram_0x013 (access),
; invokes main_i2c_service_381c, and forces BSR to 0 on return.  All 5
; callers follow with `btfsc ram_0x0A4, N, BANKED`, which requires BSR=0.
;
; Savings : 5 sites × (8 B → 2 B rcall) − 10 B helper = 20 B.
; ---------------------------------------------------------------------------
i2c_381c_with_w_bank0:
    movwf       ram_0x013, ACCESS
    call        main_i2c_service_381c, 0x0
    movlb       0x0
    return      0


; ---------------------------------------------------------------------------
; Helper: setup_fsr2_page_1_or_2                     (W02-E05 size-opt helper)
; ---------------------------------------------------------------------------
; Shared factor for the 4-instruction FSR2 "page 1 or 2" setup sequence. The
; caller must have just executed "addwf <reg>, W, ACCESS" (or equivalent that
; sets C on carry-out) with the low byte in W. On entry: W = FSR2L target,
; C = carry-out from the prior addwf. Helper sets:
;   FSR2L = W
;   FSR2H = 0x01 + C   (i.e. page 1 if no carry, page 2 if carry)
; Side effects: W is left at 0x01 (as in the inlined original pattern),
; C/DC/N/OV/Z reflect addwfc FSR2H + 0x01 + C. Callers of the original
; inline sequence did not rely on post-pattern flags; see W02-E05 audit.
; ---------------------------------------------------------------------------
setup_fsr2_page_1_or_2:
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Helper: setup_fsr2_page_1                           (W03-E04 size-opt helper)
; ---------------------------------------------------------------------------
; Shared factor for the 4-instruction FSR2 "page 1" setup sequence where the
; caller has just executed "addwf <reg>, W, ACCESS" with a constant bias such
; that the carry-out is provably always 1 for the reachable input range (see
; W03-E04 audit at lines ~419, ~2420, ~3284). In each original pattern the
; inline sequence was:
;     movwf       FSR2L, ACCESS
;     clrf        FSR2H, ACCESS
;     movlw       0x00
;     addwfc      FSR2H, F, ACCESS
; which, with C=1 guaranteed, always lands at FSR2H = 1. This helper collapses
; the sequence to an unconditional page-1 selection.
;   FSR2L = W
;   FSR2H = 0x01
; Side effects: W ends at 0x01 (vs 0x00 in the original post-pattern); no
; caller relies on W after the pattern (next insn at each site either calls
; into a helper that returns W, or reloads W via movlw/movf). C/DC/N/OV/Z are
; not preserved; no caller inspected them.
; ---------------------------------------------------------------------------
setup_fsr2_page_1:
    movwf       FSR2L, ACCESS
    movlw       0x01
    movwf       FSR2H, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_uart_service_1be6        (UART parser + downstream forwarder)
; Address : 0x1BE6
; ---------------------------------------------------------------------------
; Drains the native RX ring (0x0200, indices rx_ring_rd/rx_ring_wr) one byte
; per pass, runs a 3-byte frame parser keyed on rx_frame_position (0=route,
; 1=cmd, 2=data), and forwards every non-addressed byte downstream as the
; PB1->PB2 chain link.
;
; Frame discrimination by route byte:
;   0xB0 -> broadcast: clear active_flags.bit0 (rx_route_is_b1=0)
;   0xB1 -> addressed: set active_flags.bit0
;   else  -> non-route data, force-pass through; if a stray BF/04 status,
;            drop the cmd byte by one (pre-V3.1 protocol artefact).
;
; Once cmd+data are latched into ram_0x0A2/ram_0x0A3, control falls into
; cmd_dispatch_xor_chain which routes by cmd byte to one of:
;     cmd03_subdispatch (standby/wake/mute on/off)
;     cmd04_status_response, cmd06_input_select_handler, volume_cmd_handler,
;     channel-config and preset_select_handler (V3.2: queues only).
;
; V3.2 invariant: every handler returns through flow_main_uart_service_1be6_1e6c
; in bounded time.  No handler may block the parser; long-running work is
; deferred to preset_job_service.
;
; Calls: rx_ring_has_data, rx_ring_read, uart_tx_byte_blocking,
;        send_status_burst, volume_dsp_write, preset_select_handler.
; ---------------------------------------------------------------------------
main_uart_service_1be6:
    clrf        ram_0x009, ACCESS
    bra         flow_main_uart_service_1be6_1e78
flow_main_uart_service_1be6_1bea:
    call        rx_ring_has_data, 0x0

    bnz         flow_main_uart_service_1be6_1bf4
    bra         flow_main_uart_service_1be6_1e7c
flow_main_uart_service_1be6_1bf4:
    call        rx_ring_read, 0x0
    movwf       ram_0x00A, ACCESS
    movlw       0x7F
    cpfsgt      ram_0x00A, ACCESS
    bra         flow_main_uart_service_1be6_1c42
    movf        ram_0x00A, W, ACCESS
    xorlw       0xB0
    bnz         flow_main_uart_service_1be6_1c0e
    movlw       0x01
    movwf       rx_frame_position, BANKED
    bcf         active_flags, 0, ACCESS
    bra         parser_route_phase_handler
flow_main_uart_service_1be6_1c0e:
    movf        ram_0x00A, W, ACCESS
    xorlw       0xB1
    bnz         flow_main_uart_service_1be6_1c1c
    movlw       0x01
    movwf       rx_frame_position, BANKED
    bsf         active_flags, 0, ACCESS
    bra         parser_route_phase_handler
flow_main_uart_service_1be6_1c1c:
    clrf        rx_frame_position, BANKED
    bcf         active_flags, 0, ACCESS
    movff       ram_0x00A, ram_0x005
    movlw       0xF0
    andwf       ram_0x005, F, ACCESS
    movf        ram_0x005, W, ACCESS
    xorlw       0xB0
    bnz         parser_route_phase_handler
    movf        ram_0x00A, W, ACCESS
    xorlw       0xBF
    btfss       STATUS, 2, ACCESS
    decf        ram_0x00A, F, ACCESS
; ---------------------------------------------------------------------------
; parser_route_phase_handler
; Receives a route byte (0xB0/0xB1/0xBF/...) and decides whether to forward
; it downstream. PB1 forwards every byte that is NOT addressed to itself
; (active_flags.bit0 == 0); PB2 (last on chain) silently consumes its own
; addressed traffic. This is the chain-link forward path that makes a
; multi-MAIN install behave as one current loop to CONTROL.
; ---------------------------------------------------------------------------
parser_route_phase_handler:
    btfsc       active_flags, 0, ACCESS              ; addressed to us?
    bra         flow_main_uart_service_1be6_1e80     ; yes -> consume locally
    movf        ram_0x00A, W, ACCESS                 ; no  -> echo to next link
    call        uart_tx_byte_blocking, 0x0
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1c42:
    btfsc       active_flags, 0, ACCESS
    bra         flow_main_uart_service_1be6_1c52
    movlw       0x02
    subwf       rx_frame_position, W, BANKED
    bc          flow_main_uart_service_1be6_1c52
    movf        ram_0x00A, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
flow_main_uart_service_1be6_1c52:
    movlb       0x0
    movf        rx_frame_position, W, BANKED
    btfss       STATUS, 2, ACCESS
    incf        rx_frame_position, F, BANKED
    movlw       0x02
    subwf       rx_frame_position, W, BANKED
    bc          flow_main_uart_service_1be6_1c62
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1c62:
    movf        rx_frame_position, W, BANKED
    xorlw       0x02
    bnz         flow_main_uart_service_1be6_1c6e
    movff       ram_0x00A, ram_0x0A2
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1c6e:
    movff       ram_0x00A, ram_0x0A3
    movff       ram_0x00A, ram_0x0BC
    bsf         active_flags, 6, ACCESS
    movlw       0x01
    movwf       rx_frame_position, BANKED
    bra         cmd_dispatch_xor_chain
; ---------------------------------------------------------------------------
; wake_request_handler                     (cmd=0x03 data=0x01)
; Sets active_flags.bit3 (open the gate) and raises event_flags.bit2 only if
; the gate was previously closed (so a wake against an already-open gate
; doesn't re-trigger adc_boot_gate). The XOR-then-AND-then-XOR dance is the
; stock idiom for "set bit3 unconditionally, set bit2 only if was clear".
; This is the wake frame that V1.62b CONTROL was failing to send after
; reconnect — see V162B_RECONNECT_WAKE_BUG.md.
; ---------------------------------------------------------------------------
wake_request_handler:
    movlw       0x01
    btfsc       active_flags, 3, ACCESS              ; gate already open?
    movlw       0x00                                 ; yes -> ram_0x005 = 0
    movwf       ram_0x005, ACCESS                    ; ram_0x005 = (gate-was-closed) ? 1 : 0
    rlncf       ram_0x005, F, ACCESS
    rlncf       ram_0x005, F, ACCESS                 ; shifted into bit2 mask position
    movf        event_flags, W, BANKED
    xorwf       ram_0x005, W, ACCESS
    andlw       0xFB                                 ; preserve every bit except bit2
    xorwf       ram_0x005, W, ACCESS                 ; OR in bit2 if we computed it
    movwf       event_flags, BANKED
    btfsc       event_flags, 2, BANKED               ; event raised?
    bsf         active_flags, 3, ACCESS              ; open the gate
    bra         flow_main_uart_service_1be6_1e6c

; ---------------------------------------------------------------------------
; standby_request_handler                  (cmd=0x03 data=0x00)
; Symmetric inverse of wake: clear active_flags.bit3 (close the gate) and
; raise event_flags.bit2 to schedule hw_standby_shutdown. If the gate was
; already closed, just clear event_flags.bit2 (no further action). This is
; the broadcast that closes EVERY MAIN's gate on the chain — once closed,
; cmd_dispatch_gated drops every command at cmd_gate_reject until a wake
; reopens it.
; ---------------------------------------------------------------------------
standby_request_handler:
    btfss       active_flags, 3, ACCESS              ; gate currently open?
    bra         flow_main_uart_service_1be6_1ca2     ; no  -> just consume the event
    bsf         event_flags, 2, BANKED               ; yes -> raise standby event
    bra         flow_main_uart_service_1be6_1ca6
flow_main_uart_service_1be6_1ca2:
    movlb       0x0
    bcf         event_flags, 2, BANKED               ; gate was already closed
flow_main_uart_service_1be6_1ca6:
    btfsc       event_flags, 2, BANKED
    bcf         active_flags, 3, ACCESS              ; close the gate (BROADCAST drops all MAINs)
    bra         flow_main_uart_service_1be6_1e6c
; ---------------------------------------------------------------------------
; cmd03_mute_on_handler                    (cmd=0x03 data=0x02 — mute on)
; Sets the user mute (active_flags.bit4). If a preset job is in flight,
; latches user-mute-desired in preset_job_flags.bit1 so COMMIT/CANCEL stays
; muted instead of restoring the previous state. The xor/and dance below
; computes whether a DSP refresh is needed (event_flags.bit5 set) by
; comparing user-mute (bit4) against the shadow forced-mute (bit5).
; ---------------------------------------------------------------------------
cmd03_mute_on_handler:
    btfsc       ram_0x094, 3, BANKED                 ; HID query mode?
    bra         flow_main_uart_service_1be6_1cd6
    bsf         active_flags, 4, ACCESS              ; user mute on
    ; V3.2: if preset job active, record user wants mute
    movlb       0x2
    tstfsz      preset_job_state, BANKED             ; skip if IDLE
    bsf         preset_job_flags, 1, BANKED          ; latch user_mute_desired
    movlb       0x0
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x005, ACCESS
    btfss       active_flags, 5, ACCESS
    bra         flow_main_uart_service_1be6_1cc2
    movlw       0x01
    bra         flow_main_uart_service_1be6_1cc4
flow_main_uart_service_1be6_1cc2:
    movlw       0x00
flow_main_uart_service_1be6_1cc4:
    xorwf       ram_0x005, F, ACCESS
    btfss       STATUS, 2, ACCESS
flow_main_uart_service_1be6_1cc8:
    bsf         event_flags, 5, BANKED
flow_main_uart_service_1be6_1cca:
    btfss       active_flags, 4, ACCESS
    bra         flow_main_uart_service_1be6_1cd2
    bsf         active_flags, 5, ACCESS
    bra         flow_main_uart_service_1be6_1cd4
flow_main_uart_service_1be6_1cd2:
    bcf         active_flags, 5, ACCESS
flow_main_uart_service_1be6_1cd4:
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1cd6:
    movlw       0x02
    btfss       active_flags, 4, ACCESS
    movlw       0x03
    movwf       ram_0x0BC, BANKED
    bcf         ram_0x094, 3, BANKED
    bra         flow_main_uart_service_1be6_1e6c
; ---------------------------------------------------------------------------
; cmd03_mute_off_handler                   (cmd=0x03 data=0x03 — mute off)
; If we are currently force-muted by an in-flight preset job
; (preset_job_flags.bit0 set), the cmd is RECORDED but NOT executed —
; preset_job COMMIT or CANCEL will release the mute when the table apply
; completes. Otherwise we drop the user mute (active_flags.bit4) and run
; the same DSP-refresh logic as cmd03_mute_on (event_flags.bit5 dirtying).
; This guard is the V3.2 fix for "preset switch goes silent" — without it,
; a user who pressed unmute during the 150 ms preset hold would get a
; brief loud burst because the table wasn't fully applied yet.
; ---------------------------------------------------------------------------
cmd03_mute_off_handler:
    btfsc       ram_0x094, 3, BANKED                 ; HID query mode?
    bra         flow_main_uart_service_1be6_1cd6
    ; V3.2: during a force-muted preset job, suppress the actual mute-off
    ; so the DSP stays muted while the table apply is in progress.
    ; Only record the user's desire for COMMIT to act on later.
    movlb       0x2
    tstfsz      preset_job_state, BANKED             ; skip next if IDLE
    btfss       preset_job_flags, 0, BANKED          ; skip next if force-muted
    bra         cmd03_mute_off_apply
    bcf         preset_job_flags, 1, BANKED          ; record: user wants unmute
    movlb       0x0
    bra         flow_main_uart_service_1be6_1e6c
cmd03_mute_off_apply:
    movlb       0x0
    bcf         active_flags, 4, ACCESS
    ; V3.2: if preset job active (non-force-muted), record user wants unmute
    movlb       0x2
    tstfsz      preset_job_state, BANKED
    bcf         preset_job_flags, 1, BANKED
    movlb       0x0
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x005, ACCESS
    btfss       active_flags, 5, ACCESS
    bra         flow_main_uart_service_1be6_1cc2
    movlw       0x01
    xorwf       ram_0x005, F, ACCESS
    bnz         flow_main_uart_service_1be6_1cc8
    bra         flow_main_uart_service_1be6_1cca
; ---------------------------------------------------------------------------
; cmd03_subdispatch                        (cmd=0x03 data → handler)
; Routes cmd=0x03 by data byte to one of four handlers. The XOR-chain idiom
; saves one cycle per case vs. independent compares; cumulative XOR values
; must add up to the data byte exactly when the case matches.
;   data=0x00 → standby_request_handler
;   data=0x01 → wake_request_handler
;   data=0x02 → cmd03_mute_on_handler
;   data=0x03 → cmd03_mute_off_handler
; Any other data falls through to "no-op consume" (1e6c).
; ---------------------------------------------------------------------------
cmd03_subdispatch:
    movf        ram_0x0A3, W, BANKED
    bz          standby_request_handler              ; data=0x00
    xorlw       0x01
    bz          wake_request_handler                 ; data=0x01
    xorlw       0x03                                 ; cumulative XOR == data ?
    bz          cmd03_mute_on_handler                ; data=0x02
    xorlw       0x01
    bz          cmd03_mute_off_handler               ; data=0x03
    bra         flow_main_uart_service_1be6_1e6c

; ---------------------------------------------------------------------------
; cmd04_status_response                    (cmd=0x04 data=0x00 — status_poll)
; Bypasses the active gate: CONTROL can poll for status even from standby.
; Emits the BF/05, BF/07, BF/03, BF/06, BF/1D burst from cached RAM via
; send_status_burst. There is no BF/04 reply frame.
; ---------------------------------------------------------------------------
cmd04_status_response:
    call        send_status_burst, 0x0
    bra         flow_main_uart_service_1be6_1e6c

; ---------------------------------------------------------------------------
; cmd06_input_select_handler               (cmd=0x06 — input source)
; Updates input_select (0x099) and its mirror (0x0B3). When ram_0x094.bit0
; is set (HID-driven query mode), the routine instead RETURNS the current
; value via ram_0x0BC and clears the bit, so the caller's status burst
; carries it back.
; ---------------------------------------------------------------------------
cmd06_input_select_handler:
    btfsc       ram_0x094, 0, BANKED                 ; HID query mode?
    bra         flow_main_uart_service_1be6_1d22
    movff       ram_0x0A3, input_select              ; commit new input
    movff       input_select, input_select_mirror
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d22:
    movff       input_select, ram_0x0BC
    bcf         ram_0x094, 0, BANKED
    bra         flow_main_uart_service_1be6_1e6c
; ---------------------------------------------------------------------------
; volume_cmd_handler                       (cmd=0x07 — volume set)
; Computes new 32-bit volume from data byte: data is sent biased by 0x60
; (0x60 = 0 dB), so the routine adds 0xFFA0 (i.e. -0x60) and sign-extends
; to 32 bits in computed_volume[0..3]. If the new value differs from the
; cached logical_volume[0..3], event_flags.bit3 (volume_dirty) is set so
; the next periodic_service_loop pass calls volume_dsp_write to push the
; coefficient into the DSP.
;
; V3.1 Fix B': the helper deliberately does NOT copy computed→logical
; here. The copy happens inside volume_dsp_write only after a verified
; successful I2C write (ACKSTAT==0). The old behavior unconditionally
; cleared the dirty bit, so a NACK was silent (DSP2 bug).
; ---------------------------------------------------------------------------
volume_cmd_handler:
    btfsc       ram_0x094, 1, BANKED                 ; HID query mode?
    bra         flow_main_uart_service_1be6_1d80
    movlw       0xA0                                 ; -0x60 low byte (two's complement)
    movwf       ram_0x005, ACCESS
    setf        ram_0x006, ACCESS                    ; 0xFFFF... high byte
    movf        ram_0x0A3, W, BANKED                 ; data byte
    movwf       ram_0x007, ACCESS
    clrf        ram_0x008, ACCESS
    movf        ram_0x005, W, ACCESS
    addwf       ram_0x007, F, ACCESS                 ; data + 0xA0 (8-bit)
    movf        ram_0x006, W, ACCESS
    addwfc      ram_0x008, F, ACCESS                 ; carry → upper byte
    movff       ram_0x007, computed_volume
    movff       ram_0x008, computed_volume_1
    movlw       0x00
    btfsc       computed_volume_1, 7, BANKED         ; sign-extend to 32 bits
    movlw       0xFF
    movwf       computed_volume_2, BANKED
    movwf       computed_volume_3, BANKED
    xorwf       logical_volume_3, W, BANKED
    bnz         flow_main_uart_service_1be6_1d68
    movf        logical_volume_2, W, BANKED
    xorwf       computed_volume_2, W, BANKED
    bnz         flow_main_uart_service_1be6_1d68
    movf        logical_volume_1, W, BANKED
    xorwf       computed_volume_1, W, BANKED
    bnz         flow_main_uart_service_1be6_1d68
    movf        logical_volume, W, BANKED
    xorwf       computed_volume, W, BANKED
flow_main_uart_service_1be6_1d68:
    bnz         flow_main_uart_service_1be6_1d6c
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d6c:
    bsf         event_flags, 3, BANKED
    ; V3.1 Fix B': do NOT copy computed->logical here (deferred to volume_dsp_write)
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d80:
    movf        computed_volume, W, BANKED
    addlw       0x60
    movwf       ram_0x0BC, BANKED
    bcf         ram_0x094, 1, BANKED
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d8a:
    movf        ram_0x0A3, W, BANKED
    xorlw       0x29
    bnz         flow_main_uart_service_1be6_1e6c
    call        report_cmd29_status, 0x0
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d96:
    movff       ram_0x0A3, ram_0x060
    movf        ram_0x0A5, W, BANKED
    xorwf       ram_0x060, W, BANKED
    bz          flow_main_uart_service_1be6_1e6c
    bsf         event_flags, 4, BANKED
    movff       ram_0x060, ram_0x0A5
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1da8:
    movff       ram_0x0A3, ram_0x061
    movf        ram_0x061, W, BANKED
    xorwf       ram_0x0A6, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x061, ram_0x0A6
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1dba:
    movff       ram_0x0A3, ram_0x062
    movf        ram_0x062, W, BANKED
    xorwf       ram_0x0A7, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x062, ram_0x0A7
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1dcc:
    movff       ram_0x0A3, ram_0x063
    movf        ram_0x063, W, BANKED
    xorwf       ram_0x0A8, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x063, ram_0x0A8
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1dde:
    movff       ram_0x0A3, ram_0x064
    movf        ram_0x064, W, BANKED
    xorwf       ram_0x0A9, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x064, ram_0x0A9
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1df0:
    movff       ram_0x0A3, ram_0x065
    movf        ram_0x065, W, BANKED
    xorwf       ram_0x0AA, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 4, BANKED
    movff       ram_0x065, ram_0x0AA
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1e02:
    btfsc       ram_0x094, 4, BANKED
    bra         flow_main_uart_service_1be6_1e14
    movf        ram_0x0B8, W, BANKED
    xorwf       ram_0x0A3, W, BANKED
    bz          flow_main_uart_service_1be6_1e6c
    movff       ram_0x0A3, ram_0x0B8
    bsf         ram_0x07F, 0, BANKED
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1e14:
    movff       ram_0x0B8, ram_0x0BC
    bcf         ram_0x094, 4, BANKED
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1e1c:
    movff       ram_0x0A3, ram_0x0C3
    movf        ram_0x0B2, W, BANKED
    xorwf       ram_0x0C3, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         ram_0x0BD, 0, BANKED
    movff       ram_0x0C3, ram_0x0B2
    bra         flow_main_uart_service_1be6_1e6c
cmd_dispatch_xor_chain:
    movf        ram_0x0A2, W, BANKED
    xorlw       0x03
    bnz         flow_main_uart_service_1be6_1e36
    bra         cmd03_subdispatch
flow_main_uart_service_1be6_1e36:
    xorlw       0x07
    bnz         flow_main_uart_service_1be6_1e3c
    bra         cmd04_status_response
flow_main_uart_service_1be6_1e3c:
    xorlw       0x02
    bnz         flow_main_uart_service_1be6_1e42
    bra         cmd06_input_select_handler
flow_main_uart_service_1be6_1e42:
    xorlw       0x01
    bnz         flow_main_uart_service_1be6_1e48
    bra         volume_cmd_handler
flow_main_uart_service_1be6_1e48:
    xorlw       0x17
    bz          flow_main_uart_service_1be6_1d8a
    xorlw       0x07
    bz          flow_main_uart_service_1be6_1d96
    xorlw       0x0F
    bz          flow_main_uart_service_1be6_1da8
    xorlw       0x01
    bz          flow_main_uart_service_1be6_1dba
    xorlw       0x03
    bz          flow_main_uart_service_1be6_1dcc
    xorlw       0x01
    bz          flow_main_uart_service_1be6_1dde
    xorlw       0x07
    bz          flow_main_uart_service_1be6_1df0
    xorlw       0x01
    bz          flow_main_uart_service_1be6_1e02
    xorlw       0x03
    bz          flow_main_uart_service_1be6_1e1c
    xorlw       0x3E                            ; V3.1: cumulative 0x1E ^ 0x3E = 0x20
    btfsc       STATUS, 2, ACCESS               ; Z = cmd 0x20
    goto        preset_select_handler
    xorlw       0x01                            ; V3.2 Layer 5: cumulative 0x20 ^ 0x01 = 0x21
    btfsc       STATUS, 2, ACCESS               ; Z = cmd 0x21 (diagnostics query)
    goto        cmd21_diag_query_handler
    xorlw       0x03                            ; V3.2 Tier-1: cumulative 0x21 ^ 0x03 = 0x22
    btfsc       STATUS, 2, ACCESS               ; Z = cmd 0x22 (reset-cause flags query)
    goto        cmd22_reset_flags_query_handler
flow_main_uart_service_1be6_1e6c:
    btfss       active_flags, 6, ACCESS
    bra         flow_main_uart_service_1be6_1e80
    movlb       0x0
    movf        ram_0x0BC, W, BANKED
    call        uart_tx_byte_blocking, 0x0
flow_main_uart_service_1be6_1e78:
    bcf         active_flags, 6, ACCESS
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1e7c:
    movlw       0x01
    movwf       ram_0x009, ACCESS
flow_main_uart_service_1be6_1e80:
    movf        ram_0x009, W, ACCESS
    btfss       STATUS, 2, ACCESS
    return      0
    bra         flow_main_uart_service_1be6_1bea


; ---------------------------------------------------------------------------
; Function: main_core_service_1e88
; Address : 0x1E88
; Notes   : Inferred core helper routine. Calls: eeprom_read_byte, main_flash_service_46de.
; ---------------------------------------------------------------------------
main_core_service_1e88:
    clrf        ram_0x004, ACCESS
    clrf        ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       computed_volume_3, BANKED
    movlw       0x01
    rcall       eeprom_read_byte_W
    movwf       computed_volume_2, BANKED
    movlw       0x02
    rcall       eeprom_read_byte_W
    movwf       computed_volume_1, BANKED
    movlw       0x03
    rcall       eeprom_read_byte_W
    movwf       computed_volume, BANKED
    movlw       0x04
    rcall       eeprom_read_byte_W
    movwf       input_select, BANKED
    movlw       0x07
    rcall       eeprom_read_byte_W
    movwf       ram_0x060, BANKED
    movlw       0x08
    rcall       eeprom_read_byte_W
    movwf       ram_0x061, BANKED
    movlw       0x09
    rcall       eeprom_read_byte_W
    movwf       ram_0x062, BANKED
    movlw       0x0A
    rcall       eeprom_read_byte_W
    movwf       ram_0x063, BANKED
    movlw       0x0B
    rcall       eeprom_read_byte_W
    movwf       ram_0x064, BANKED
    movlw       0x0C
    rcall       eeprom_read_byte_W
    movwf       ram_0x065, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0x0D
    movwf       ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    movwf       ram_0x05F, ACCESS
    movlw       0x14
    rcall       eeprom_read_byte_W
    movwf       ram_0x0C3, BANKED
    movf        computed_volume_3, W, BANKED
    xorlw       0x80
    addlw       0x80
    bnz         flow_main_core_service_1e88_1f54
    movlw       0x00
    subwf       computed_volume_2, W, BANKED
    bnz         flow_main_core_service_1e88_1f54
    movlw       0x00
    subwf       computed_volume_1, W, BANKED
    bnz         flow_main_core_service_1e88_1f54
    movlw       0x13
    subwf       computed_volume, W, BANKED
flow_main_core_service_1e88_1f54:
    bnc         flow_main_core_service_1e88_1f60
    movlw       0xA0
    movwf       computed_volume, BANKED
    setf        computed_volume_1, BANKED
    setf        computed_volume_2, BANKED
    setf        computed_volume_3, BANKED
flow_main_core_service_1e88_1f60:
    movlw       0x08
    cpfsgt      input_select, BANKED
    bra         flow_main_core_service_1e88_1f6a
    movlw       0x01
    movwf       input_select, BANKED
flow_main_core_service_1e88_1f6a:
    movlw       0x03
    cpfsgt      ram_0x060, BANKED
    bra         flow_main_core_service_1e88_1f72
    clrf        ram_0x060, BANKED
flow_main_core_service_1e88_1f72:
    lfsr        FSR2, 0x0061
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1f7e
    clrf        ram_0x061, BANKED
flow_main_core_service_1e88_1f7e:
    lfsr        FSR2, 0x0062
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1f8a
    clrf        ram_0x062, BANKED
flow_main_core_service_1e88_1f8a:
    lfsr        FSR2, 0x0063
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1f98
    movlw       0x01
    movwf       ram_0x063, BANKED
flow_main_core_service_1e88_1f98:
    lfsr        FSR2, 0x0064
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1fa6
    movlw       0x01
    movwf       ram_0x064, BANKED
flow_main_core_service_1e88_1fa6:
    lfsr        FSR2, 0x0065
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1fb4
    movlw       0x01
    movwf       ram_0x064, BANKED
flow_main_core_service_1e88_1fb4:
    movlw       0x03
    cpfsgt      ram_0x05F, ACCESS
    bra         flow_main_core_service_1e88_1fbc
    movwf       ram_0x05F, ACCESS
flow_main_core_service_1e88_1fbc:
    movlw       0x04
    cpfsgt      ram_0x0C3, BANKED
    bra         flow_main_core_service_1e88_1fc6
    movlw       0x01
    movwf       ram_0x0C3, BANKED
flow_main_core_service_1e88_1fc6:
    call        copy_computed_volume_to_logical_volume, 0x0
    movff       input_select, input_select_mirror
    movff       ram_0x060, ram_0x0A5
    movff       ram_0x061, ram_0x0A6
    movff       ram_0x062, ram_0x0A7
    movff       ram_0x063, ram_0x0A8
    movff       ram_0x064, ram_0x0A9
    movff       ram_0x065, ram_0x0AA
    movff       ram_0x0C3, ram_0x0B2
    movlw       0x0F
    rcall       eeprom_read_byte_W
    movwf       ram_0x0B4, BANKED
    incf        ram_0x0B4, W, BANKED
    btfsc       STATUS, 2, ACCESS
    bcf         ram_0x0B4, 0, BANKED
    movff       ram_0x0B4, ram_0x0B1
    movlw       0x0E
    rcall       eeprom_read_byte_W
    movwf       ram_0x0B8, BANKED
    movlw       0x03
    subwf       ram_0x0B8, W, BANKED
    bc          flow_main_core_service_1e88_2026
    movlw       0x03
    movwf       ram_0x0B8, BANKED
flow_main_core_service_1e88_2026:
    movlw       0x04
    cpfsgt      ram_0x0B8, BANKED
    bra         flow_main_core_service_1e88_2030
    movlw       0x03
    movwf       ram_0x0B8, BANKED
flow_main_core_service_1e88_2030:
    movlw       0x10
    rcall       eeprom_read_byte_W
    movwf       ram_0x09B, BANKED
    movlw       0x11
    rcall       eeprom_read_byte_W
    movwf       ram_0x09C, BANKED
    movlw       0x12
    rcall       eeprom_read_byte_W
    movwf       ram_0x09D, BANKED
    movlw       0x13
    rcall       eeprom_read_byte_W
    movwf       ram_0x09E, BANKED
    movlw       0x12
    cpfsgt      ram_0x09B, BANKED
    bra         flow_main_core_service_1e88_2070
    clrf        ram_0x09B, BANKED
flow_main_core_service_1e88_2070:
    movlw       0x12
    cpfsgt      ram_0x09C, BANKED
    bra         flow_main_core_service_1e88_2078
    clrf        ram_0x09C, BANKED
flow_main_core_service_1e88_2078:
    movlw       0x12
    cpfsgt      ram_0x09D, BANKED
    bra         flow_main_core_service_1e88_2080
    clrf        ram_0x09D, BANKED
flow_main_core_service_1e88_2080:
    movlw       0x12
    cpfsgt      ram_0x09E, BANKED
    bra         flow_main_core_service_1e88_2088
    clrf        ram_0x09E, BANKED
flow_main_core_service_1e88_2088:
    movff       ram_0x09B, ram_0x0AC
    movff       ram_0x09C, ram_0x0AD
    movff       ram_0x09D, ram_0x0AE
    movff       ram_0x09E, ram_0x0AF
    movlw       0x50
    movwf       ram_0x00A, ACCESS
flow_main_core_service_1e88_209c:
    movlb       0x1
    movlw       0xB0
    addwf       ram_0x00A, W, ACCESS
    rcall       setup_fsr2_page_1
    movff       ram_0x00A, ram_0x003
    clrf        ram_0x004, ACCESS
    call        eeprom_read_byte, 0x0
    movwf       INDF2, ACCESS
    incf        ram_0x00A, F, ACCESS
    movlw       0x5E
    cpfsgt      ram_0x00A, ACCESS
    bra         flow_main_core_service_1e88_209c
    movlw       0x60
    movwf       ram_0x00A, ACCESS
flow_main_core_service_1e88_20c2:
    movlb       0x2
    movlw       0x60
    addwf       ram_0x00A, W, ACCESS
    call        fsr2_page2_from_W, 0x0       ; W05-E02: FSR2=0x0200|W (helper clobbers W; eeprom_read_byte takes input via ram_0x003)
    movff       ram_0x00A, ram_0x003
    clrf        ram_0x004, ACCESS
    call        eeprom_read_byte, 0x0
    movwf       INDF2, ACCESS
    incf        ram_0x00A, F, ACCESS
    movlw       0x7D
    cpfsgt      ram_0x00A, ACCESS
    bra         flow_main_core_service_1e88_20c2
    clrf        ram_0x008, ACCESS
    movlw       0x80
    movwf       ram_0x007, ACCESS
    movlw       0x02
    movwf       ram_0x009, ACCESS
    call        main_flash_service_46de, 0x0
    clrf        ram_0x008, ACCESS
    movlw       0x81
    movwf       ram_0x007, ACCESS
    movlw       0x03
    movwf       ram_0x009, ACCESS
    goto        main_flash_service_46de


; ---------------------------------------------------------------------------
; eeprom_read_byte_W  — rcall-reachable wrapper that reads one EEPROM byte.
; Arguments: W = EEPROM address (low byte); ram_0x004 cleared by helper.
; Returns  : W = byte read; BSR = 0 on return.
; W02-E01 size optimization: collapses 17 × 5-instruction preambles in
; main_core_service_1e88 into 17 × 2-instruction sequences.
; ---------------------------------------------------------------------------
eeprom_read_byte_W:
    movwf       ram_0x003, ACCESS   ; ram_0x003 = address low byte
    clrf        ram_0x004, ACCESS   ; high byte always 0 in this call site set
    call        eeprom_read_byte, 0x0
    movlb       0x0
    return      0



; ---------------------------------------------------------------------------
; Helper: prep_bank1_ram004 (W04-E02 size-opt helper)
; Sets BSR=1 and ram_0x004 (addr_high scratch) = 0x01.  W is clobbered to
; 0x01.  Shared by 9 `ram_block_clear` / `ram_block_clear_4` callers that
; set up a bank-1 page-1 address window before calling into the clear
; helpers.
; ---------------------------------------------------------------------------
prep_bank1_ram004:
    movlb       0x1
    movlw       0x01
    movwf       ram_0x004, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Helper: ram_block_clear_4 (W02-E02 size-opt helper)
; ---------------------------------------------------------------------------
; Wraps the uniform 4-instruction setup used at 7 sites inside
; main_i2c_service_2100. Caller loads W with the starting ram_0x003 address
; (low byte); ram_0x004 (high byte) must already be set by the caller.
; The helper fixes the block length at 0x04 and dispatches to
; ram_block_clear. Saves 30 B vs inlined setup at 7 sites.
; ---------------------------------------------------------------------------
ram_block_clear_4:
    movwf       ram_0x003, ACCESS
    movlw       0x04
    movwf       ram_0x005, ACCESS
    goto        ram_block_clear


; ---------------------------------------------------------------------------
; Function: main_i2c_service_2100          (DSP/secondary device sync burst)
; Address : 0x2100
; ---------------------------------------------------------------------------
; Long composite I2C-update routine triggered from cmd_dispatch_gated when
; event_flags.bit4 (input/route dirty) is set. Clears the working RAM at
; 0x04D7 area, then re-runs the channel-config / DSP-sync sequence (touches
; the secondary device 0x71 for amp routing AND the TAS3108 for the
; coefficient block). Used during initial wake and after channel config
; changes; not part of the volume-only fast path.
; ---------------------------------------------------------------------------
main_i2c_service_2100:
    clrf        ram_0x004, ACCESS
    movlw       0xD7
    rcall       ram_block_clear_4
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xDB
    rcall       ram_block_clear_4
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xDF
    rcall       ram_block_clear_4
    rcall       prep_bank1_ram004
    movlw       0xD9
    rcall       ram_block_clear_4
    clrf        ram_0x004, ACCESS
    movlb       0x0
    movlw       0xE3
    rcall       ram_block_clear_4
    rcall       prep_bank1_ram004
    movlw       0xDD
    rcall       ram_block_clear_4
    rcall       prep_bank1_ram004
    movlw       0xE1
    rcall       ram_block_clear_4
    call        i2c_wait_bus_idle, 0x0

    ; --- Part 2: dispatch six (ram_0x0A0, ram_0x0B9) writes via FSR1
    ; -------------------------------------------------------------------
    ; Replaces a 6-way xorlw chain + 6 switch targets (~94 B) with a
    ; table-driven loop that pulls the 12-bit destination out of the
    ; packed `main_i2c_service_2100_dispatch_table`.  TBLPTR is re-seeded
    ; every iteration from counter*2 so the `tblrd*+` sequence always
    ; starts at the current entry; callees are not audited to preserve
    ; TBLPTR.
    ; -------------------------------------------------------------------
    clrf        ram_0x059, ACCESS
flow_main_i2c_service_2100_217a:
    rlncf       ram_0x059, W, ACCESS                ; W = counter * 2
    addlw       LOW(main_i2c_service_2100_dispatch_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(main_i2c_service_2100_dispatch_table)
    movwf       TBLPTRH, ACCESS
    clrf        TBLPTRU, ACCESS
    tblrd*+
    movff       TABLAT, FSR1L
    tblrd*+
    movff       TABLAT, FSR1H
    movf        ram_0x059, W, ACCESS
    movlb       0x0
    addlw       0x60
    call        fsr2_page0_read_w, 0x0               ; W04-E03
    call        main_core_service_4448, 0x0
    movff       ram_0x0A0, POSTINC1
    movff       ram_0x0B9, INDF1
    incf        ram_0x059, F, ACCESS
    movlw       0x05
    cpfsgt      ram_0x059, ACCESS
    bra         flow_main_i2c_service_2100_217a

    ; --- Part 3: 7 I2C transactions with source-table indexed copy ------
    ; Replaces a 7-way xorlw chain + 7 switch targets (~154 B) with a
    ; table lookup into `main_i2c_service_2100_source_table` plus a
    ; 4-byte movff copy through FSR1.  The I2C transaction body below is
    ; unchanged from the pre-rewrite function.
    ; -------------------------------------------------------------------
    clrf        ram_0x05A, ACCESS
flow_main_i2c_service_2100_226a:
    rlncf       ram_0x05A, W, ACCESS                ; W = counter * 2
    addlw       LOW(main_i2c_service_2100_source_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(main_i2c_service_2100_source_table)
    movwf       TBLPTRH, ACCESS
    clrf        TBLPTRU, ACCESS
    tblrd*+
    movff       TABLAT, FSR1L
    tblrd*+
    movff       TABLAT, FSR1H
    movff       POSTINC1, ram_0x06A
    movff       POSTINC1, ram_0x06B
    movff       POSTINC1, ram_0x06C
    movff       INDF1, ram_0x06D
flow_main_i2c_service_2100_2286:
    bsf         SSPCON2, 0, ACCESS
flow_main_i2c_service_2100_2288:
    btfsc       SSPCON2, 0, ACCESS
    bra         flow_main_i2c_service_2100_2288
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlb       0x1
    movlw       0x0F
    addwf       ram_0x05A, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    movf        INDF2, W, ACCESS
    call        i2c_byte_tx, 0x0
    clrf        ram_0x05B, ACCESS
flow_main_i2c_service_2100_22a8:
    movf        ram_0x05B, W, ACCESS
    movlb       0x0
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    cpfseq      INDF2, ACCESS
    bra         flow_main_i2c_service_2100_22c2
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    movlw       0x3F
    bra         flow_main_i2c_service_2100_22da
flow_main_i2c_service_2100_22c2:
    movf        ram_0x05B, W, ACCESS
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x03
    cpfseq      INDF2, ACCESS
    bra         flow_main_i2c_service_2100_22de
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    movlw       0x80
    movwf       i2c_coeff_2, ACCESS
    movlw       0xBF
flow_main_i2c_service_2100_22da:
    movwf       i2c_coeff_3, ACCESS
    bra         flow_main_i2c_service_2100_22fc
flow_main_i2c_service_2100_22de:
    movf        ram_0x05B, W, ACCESS
    addlw       0x6A
    call        fsr2_page0_read_w, 0x0               ; W04-E03
    call        main_core_service_45ce, 0x0
    movff       ram_0x00D, i2c_coeff_0
    movff       ram_0x00E, i2c_coeff_1
    movff       ram_0x00F, i2c_coeff_2
    movff       ram_0x010, i2c_coeff_3
flow_main_i2c_service_2100_22fc:
    movff       i2c_coeff_0, ram_0x049
    movff       i2c_coeff_1, ram_0x04A
    movff       i2c_coeff_2, ram_0x04B
    movff       i2c_coeff_3, ram_0x04C
    call        main_i2c_service_39a6, 0x0
    incf        ram_0x05B, F, ACCESS
    movlw       0x03
    cpfsgt      ram_0x05B, ACCESS
    bra         flow_main_i2c_service_2100_22a8
    bsf         SSPCON2, 2, ACCESS
flow_main_i2c_service_2100_231a:
    btfsc       SSPCON2, 2, ACCESS
    bra         flow_main_i2c_service_2100_231a
    incf        ram_0x05A, F, ACCESS
    movlw       0x06
    cpfsgt      ram_0x05A, ACCESS
    bra         flow_main_i2c_service_2100_226a
    retlw       0x06


; ---------------------------------------------------------------------------
; Data: main_i2c_service_2100_dispatch_table  (part 2, 6 entries × 2 B)
; ---------------------------------------------------------------------------
; Each entry is (FSR1L, FSR1H) for the destination pair written by part 2
; of main_i2c_service_2100.  Counter 0..5 selects the entry; writes
; (ram_0x0A0, ram_0x0B9) at (dest, dest+1).  Matches the old 6-way xorlw
; switch byte-for-byte:
;   counter 0 -> ram_0x0D7/0x0D8  (bank 0)
;   counter 1 -> ram_0x0DB/0x0DC  (bank 0)
;   counter 2 -> ram_0x0DF/0x0E0  (bank 0)
;   counter 3 -> ram_0x1D9/0x1DA  (bank 1)
;   counter 4 -> ram_0x0E4/0x0E5  (bank 0)
;   counter 5 -> ram_0x1E0/0x1E1  (bank 1)
; ---------------------------------------------------------------------------
main_i2c_service_2100_dispatch_table:
    db  0xD7, 0x00, 0xDB, 0x00, 0xDF, 0x00, 0xD9, 0x01, 0xE4, 0x00, 0xE0, 0x01


; ---------------------------------------------------------------------------
; Data: main_i2c_service_2100_source_table  (part 3, 7 entries × 2 B)
; ---------------------------------------------------------------------------
; Each entry is (FSR1L, FSR1H) for the 4-byte source block that part 3
; copies into ram_0x06A..0x06D before the DSP write transaction.  Matches
; the old 7-way xorlw switch byte-for-byte:
;   counter 0 -> ram_0x0D7..0x0DA  (bank 0)
;   counter 1 -> ram_0x0DB..0x0DE  (bank 0)
;   counter 2 -> ram_0x0DF..0x0E2  (bank 0)
;   counter 3 -> ram_0x1D9..0x1DC  (bank 1)
;   counter 4 -> ram_0x0E3..0x0E6  (bank 0)
;   counter 5 -> ram_0x1DD..0x1E0  (bank 1)
;   counter 6 -> ram_0x1E1..0x1E4  (bank 1)
; ---------------------------------------------------------------------------
main_i2c_service_2100_source_table:
    db  0xD7, 0x00, 0xDB, 0x00, 0xDF, 0x00, 0xD9, 0x01, 0xE3, 0x00, 0xDD, 0x01, 0xE1, 0x01


; ---------------------------------------------------------------------------
; Function: main_core_service_2328
; Address : 0x2328
; Notes   : Inferred core helper routine. Calls: main_core_service_24ac.
; ---------------------------------------------------------------------------
main_core_service_2328:
    movff       ram_0x0C1, ram_0x15A
    bra         flow_main_core_service_2328_2472
flow_main_core_service_2328_232e:
    movff       ram_0x0C2, ram_0x15B
    movlw       0x02
    movwf       ram_0x003, ACCESS
flow_main_core_service_2328_2336:
    movlw       0xBE
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    rcall       main_core_service_24ac
    movlw       0x1F
    cpfsgt      ram_0x003, ACCESS
    bra         flow_main_core_service_2328_2336
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_234a:
    movff       ram_0x0C2, ram_0x15B
    decf        ram_0x0C2, W, BANKED
    bnz         flow_main_core_service_2328_235c
    movff       ram_0x0B7, ram_0x15C
    movff       ram_0x0B8, ram_0x15D
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_235c:
    movf        ram_0x0C2, W, BANKED
    xorlw       0x02
    bz          flow_main_core_service_2328_2364
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2364:
    movff       ram_0x0B5, ram_0x15E
    movlw       0x05
    movwf       ram_0x003, ACCESS
flow_main_core_service_2328_236c:
    movlw       0xFB
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    rcall       main_core_service_24ac
    movlw       0x13
    cpfsgt      ram_0x003, ACCESS
    bra         flow_main_core_service_2328_236c
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2380:
    movff       ram_0x093, ram_0x15B
    movff       input_select, ram_0x15C
    movlb       0x1
    clrf        ram_0x05D, BANKED
    clrf        active_flags, BANKED
    movff       computed_volume_3, ram_0x15F
    movff       computed_volume_2, ram_0x160
    movff       computed_volume_1, ram_0x161
    movff       computed_volume, ram_0x162
    movlw       0x00
    btfsc       active_flags, 4, ACCESS
    movlw       0x01
    movwf       ram_0x063, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 0, BANKED
    movlw       0x01
    movlb       0x1
    movwf       ram_0x064, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 1, BANKED
    movlw       0x01
    movlb       0x1
    movwf       ram_0x065, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 2, BANKED
    movlw       0x01
    movlb       0x1
    movwf       logical_volume, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 3, BANKED
    movlw       0x01
    movlb       0x1
    movwf       logical_volume_2, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 4, BANKED
    movlw       0x01
    movlb       0x1
    movwf       logical_volume_3, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       ram_0x0A4, 5, BANKED
    movlw       0x01
    movlb       0x1
    movwf       ram_0x06A, BANKED
    movff       ram_0x060, ram_0x16C
    movff       ram_0x061, ram_0x16D
    movff       ram_0x062, ram_0x16E
    movff       ram_0x063, ram_0x16F
    movff       ram_0x064, ram_0x170
    movff       ram_0x065, ram_0x171
    movff       ram_0x0B4, ram_0x178
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_240c:
    movlw       0x03
    movlb       0x1
    movwf       ram_0x05B, BANKED
    movlw       0x03                        ; V3.2: major version = 3
    movwf       ram_0x05C, BANKED
    movlw       0x02                        ; V3.2: minor version = 2
    movwf       ram_0x05D, BANKED
    movff       input_select, ram_0x15E
    clrf        ram_0x05F, BANKED
    clrf        ram_0x060, BANKED
    clrf        ram_0x061, BANKED
    movff       ram_0x05F, ram_0x163
    movlw       0x06
    movwf       ram_0x064, BANKED
    movlw       0x0F
    movwf       ram_0x065, BANKED
    movwf       logical_volume, BANKED
    movwf       logical_volume_1, BANKED
    movwf       logical_volume_2, BANKED
    movwf       logical_volume_3, BANKED
    movwf       ram_0x06A, BANKED
    movlw       0x0A
    movwf       ram_0x06B, BANKED
    movwf       ram_0x06C, BANKED
    movwf       ram_0x06D, BANKED
    movwf       computed_volume, BANKED
    movwf       computed_volume_1, BANKED
    movwf       computed_volume_2, BANKED
    movlw       0x01
    movwf       computed_volume_3, BANKED
    movwf       ram_0x072, BANKED
    movff       ram_0x09B, ram_0x173
    movff       ram_0x09C, ram_0x174
    movff       ram_0x09D, ram_0x175
    movff       ram_0x09E, ram_0x176
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2460:
    movff       ram_0x11B, ram_0x15B
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2466:
    movlb       0x1
    clrf        ram_0x05B, BANKED
    clrf        ram_0x05C, BANKED
    clrf        ram_0x05D, BANKED
    clrf        active_flags, BANKED
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2472:
    movlb       0x0
    movf        ram_0x0C1, W, BANKED
    xorlw       0x03
    bnz         flow_main_core_service_2328_247c
    bra         flow_main_core_service_2328_232e
flow_main_core_service_2328_247c:
    xorlw       0x07
    bnz         flow_main_core_service_2328_2482
    bra         flow_main_core_service_2328_234a
flow_main_core_service_2328_2482:
    xorlw       0x01
    bnz         flow_main_core_service_2328_2488
    bra         flow_main_core_service_2328_2380
flow_main_core_service_2328_2488:
    xorlw       0x03
    bz          flow_main_core_service_2328_240c
    xorlw       0x01
    bz          flow_main_core_service_2328_2460
    xorlw       0x0F
    bz          flow_main_core_service_2328_2460
    xorlw       0x01
    bz          flow_main_core_service_2328_2460
    xorlw       0x03
    bz          flow_main_core_service_2328_2460
    xorlw       0x01
    bz          flow_main_core_service_2328_2460
    xorlw       0x07
    bz          flow_main_core_service_2328_2460
    bra         flow_main_core_service_2328_2466
flow_main_core_service_2328_24a6:
    movlb       0x0
    clrf        ram_0x0C1, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_24ac
; Address : 0x24AC
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_24ac:
    addwfc      FSR2H, F, ACCESS
    movlw       0x5A
    addwf       ram_0x003, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x01
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    incf        ram_0x003, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_24c2
; Address : 0x24C2
; Notes   : Inferred core helper routine. Calls: main_core_service_2650, main_core_service_263e, main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_24c2:
    movff       ram_0x020, ram_0x028
    movff       ram_0x021, ram_0x029
    movff       ram_0x022, ram_0x02A
    movff       ram_0x023, ram_0x02B
    movlw       0x18
    bra         flow_main_core_service_24c2_24d8
flow_main_core_service_24c2_24d6:
    rcall       main_core_service_2650
flow_main_core_service_24c2_24d8:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_24c2_24d6
    movf        ram_0x028, W, ACCESS
    movwf       ram_0x02E, ACCESS
    movff       ram_0x024, ram_0x028
    movff       ram_0x025, ram_0x029
    movff       ram_0x026, ram_0x02A
    movff       ram_0x027, ram_0x02B
    movlw       0x18
    bra         flow_main_core_service_24c2_24f6
flow_main_core_service_24c2_24f4:
    rcall       main_core_service_2650
flow_main_core_service_24c2_24f6:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_24c2_24f4
    movf        ram_0x028, W, ACCESS
    movwf       ram_0x02D, ACCESS
    movf        ram_0x02E, W, ACCESS
    bz          flow_main_core_service_24c2_2514
    movf        ram_0x02D, W, ACCESS
    subwf       ram_0x02E, W, ACCESS
    bc          flow_main_core_service_24c2_2526
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    movwf       ram_0x028, ACCESS
    movlw       0x21
    subwf       ram_0x028, W, ACCESS
    bnc         flow_main_core_service_24c2_2526
flow_main_core_service_24c2_2514:
    movff       ram_0x024, ram_0x020
    movff       ram_0x025, ram_0x021
    movff       ram_0x026, ram_0x022
    movff       ram_0x027, ram_0x023
    bra         flow_main_core_service_24c2_263c
flow_main_core_service_24c2_2526:
    movf        ram_0x02D, W, ACCESS
    bz          flow_main_core_service_24c2_253c
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    bc          flow_main_core_service_24c2_254e
    movf        ram_0x02D, W, ACCESS
    subwf       ram_0x02E, W, ACCESS
    movwf       ram_0x028, ACCESS
    movlw       0x21
    subwf       ram_0x028, W, ACCESS
    bnc         flow_main_core_service_24c2_254e
flow_main_core_service_24c2_253c:
    bra         flow_main_core_service_24c2_263c
flow_main_core_service_24c2_254e:
    movlw       0x06
    movwf       ram_0x02C, ACCESS
    btfsc       ram_0x023, 7, ACCESS
    bsf         ram_0x02C, 7, ACCESS
    btfsc       ram_0x027, 7, ACCESS
    bsf         ram_0x02C, 6, ACCESS
    bsf         ram_0x022, 7, ACCESS
    clrf        ram_0x023, ACCESS
    bsf         ram_0x026, 7, ACCESS
    clrf        ram_0x027, ACCESS
    movf        ram_0x02D, W, ACCESS
    subwf       ram_0x02E, W, ACCESS
    bc          flow_main_core_service_24c2_259c
flow_main_core_service_24c2_2568:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x024, F, ACCESS
    rlcf        ram_0x025, F, ACCESS
    rlcf        ram_0x026, F, ACCESS
    rlcf        ram_0x027, F, ACCESS
    decf        ram_0x02D, F, ACCESS
    movf        ram_0x02D, W, ACCESS
    xorwf       ram_0x02E, W, ACCESS
    bz          flow_main_core_service_24c2_2594
    decf        ram_0x02C, F, ACCESS
    movff       ram_0x02C, ram_0x028
    movlw       0x07
    andwf       ram_0x028, F, ACCESS
    bz          flow_main_core_service_24c2_2594
    bra         flow_main_core_service_24c2_2568
flow_main_core_service_24c2_2588:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x023, F, ACCESS
    rrcf        ram_0x022, F, ACCESS
    rrcf        ram_0x021, F, ACCESS
    rrcf        ram_0x020, F, ACCESS
    incf        ram_0x02E, F, ACCESS
flow_main_core_service_24c2_2594:
    movf        ram_0x02D, W, ACCESS
    cpfseq      ram_0x02E, ACCESS
    bra         flow_main_core_service_24c2_2588
    bra         flow_main_core_service_24c2_25d4
flow_main_core_service_24c2_259c:
    movf        ram_0x02E, W, ACCESS
    subwf       ram_0x02D, W, ACCESS
    bc          flow_main_core_service_24c2_25d4
flow_main_core_service_24c2_25a2:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x020, F, ACCESS
    rlcf        ram_0x021, F, ACCESS
    rlcf        ram_0x022, F, ACCESS
    rlcf        ram_0x023, F, ACCESS
    decf        ram_0x02E, F, ACCESS
    movf        ram_0x02D, W, ACCESS
    xorwf       ram_0x02E, W, ACCESS
    bz          flow_main_core_service_24c2_25ce
    decf        ram_0x02C, F, ACCESS
    movff       ram_0x02C, ram_0x028
    movlw       0x07
    andwf       ram_0x028, F, ACCESS
    bz          flow_main_core_service_24c2_25ce
    bra         flow_main_core_service_24c2_25a2
flow_main_core_service_24c2_25c2:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x027, F, ACCESS
    rrcf        ram_0x026, F, ACCESS
    rrcf        ram_0x025, F, ACCESS
    rrcf        ram_0x024, F, ACCESS
    incf        ram_0x02D, F, ACCESS
flow_main_core_service_24c2_25ce:
    movf        ram_0x02D, W, ACCESS
    cpfseq      ram_0x02E, ACCESS
    bra         flow_main_core_service_24c2_25c2
flow_main_core_service_24c2_25d4:
    btfss       ram_0x02C, 7, ACCESS
    bra         flow_main_core_service_24c2_25ea
    comf        ram_0x020, F, ACCESS
    comf        ram_0x021, F, ACCESS
    comf        ram_0x022, F, ACCESS
    comf        ram_0x023, F, ACCESS
    incf        ram_0x020, F, ACCESS
    movlw       0x00
    addwfc      ram_0x021, F, ACCESS
    addwfc      ram_0x022, F, ACCESS
    addwfc      ram_0x023, F, ACCESS
flow_main_core_service_24c2_25ea:
    btfss       ram_0x02C, 6, ACCESS
    bra         flow_main_core_service_24c2_25f2
    comf        ram_0x024, F, ACCESS
    rcall       main_core_service_263e
flow_main_core_service_24c2_25f2:
    clrf        ram_0x02C, ACCESS
    movf        ram_0x020, W, ACCESS
    addwf       ram_0x024, F, ACCESS
    movf        ram_0x021, W, ACCESS
    addwfc      ram_0x025, F, ACCESS
    movf        ram_0x022, W, ACCESS
    addwfc      ram_0x026, F, ACCESS
    movf        ram_0x023, W, ACCESS
    addwfc      ram_0x027, F, ACCESS
    btfss       ram_0x027, 7, ACCESS
    bra         flow_main_core_service_24c2_2610
    comf        ram_0x024, F, ACCESS
    rcall       main_core_service_263e
    movlw       0x01
    movwf       ram_0x02C, ACCESS
flow_main_core_service_24c2_2610:
    movff       ram_0x024, ram_0x003
    movff       ram_0x025, ram_0x004
    movff       ram_0x026, ram_0x005
    movff       ram_0x027, ram_0x006
    movff       ram_0x02E, ram_0x007
    movff       ram_0x02C, ram_0x008
    call        main_core_service_30d8, 0x0
    movff       ram_0x003, ram_0x020
    movff       ram_0x004, ram_0x021
    movff       ram_0x005, ram_0x022
    movff       ram_0x006, ram_0x023
flow_main_core_service_24c2_263c:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_263e
; Address : 0x263E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_263e:
    comf        ram_0x025, F, ACCESS
    comf        ram_0x026, F, ACCESS
    comf        ram_0x027, F, ACCESS
    incf        ram_0x024, F, ACCESS
    movlw       0x00
    addwfc      ram_0x025, F, ACCESS
    addwfc      ram_0x026, F, ACCESS
    addwfc      ram_0x027, F, ACCESS
    retlw       0x00


; ---------------------------------------------------------------------------
; Function: main_core_service_2650
; Address : 0x2650
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2650:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x02B, F, ACCESS
    rrcf        ram_0x02A, F, ACCESS
    rrcf        ram_0x029, F, ACCESS
    rrcf        ram_0x028, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_265c        (EEPROM persistence service, V3.2)
; Address : (renumbered by size-opt; see .lst)
; ---------------------------------------------------------------------------
; Dirty-flag-driven flush of volume / input / route / filter / filename
; state bytes to internal EEPROM via main_flash_service_46de (read-then-
; write-if-differ).  Gated on event_flags.bit0; for each set bit of
; ram_0x0BD (bits 0..3 for the four static blocks + bits 4/5 for the
; 0x50..0x5E loop and filename-persist call), emits a known set of
; (eeprom_offset, ram_source) records.
;
; The 19 static records (blocks 0..3) live as a packed TBLRD-readable
; table at `eeprom_persist_static_records` and are driven by the generic
; `eeprom_persist_block_walker` helper below.  Block 4 (the 0x50..0x5E
; filter window) and block 5 (the filename-persist tail) are already
; structurally minimal and remain inline.
; ---------------------------------------------------------------------------
main_core_service_265c:
    movlb       0x0
    btfss       event_flags, 0, BANKED
    return      0
    ; Seed TBLPTR at the packed records table so the block walker can
    ; consume it sequentially across all four static blocks.
    movlw       LOW(eeprom_persist_static_records)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(eeprom_persist_static_records)
    movwf       TBLPTRH, ACCESS
    clrf        TBLPTRU, ACCESS
    movlw       0x01
    rcall       eeprom_persist_block_walker      ; block 0 (7 records)
    movlw       0x02
    rcall       eeprom_persist_block_walker      ; block 1 (6 records)
    movlw       0x04
    rcall       eeprom_persist_block_walker      ; block 2 (2 records)
    movlw       0x08
    rcall       eeprom_persist_block_walker      ; block 3 (4 records)
flow_main_core_service_265c_278c:
    btfss       ram_0x0BD, 4, BANKED
    bra         flow_main_core_service_265c_27bc
    movlw       0x50
    movwf       ram_0x00A, ACCESS
flow_main_core_service_265c_2794:
    movff       ram_0x00A, ram_0x007
    clrf        ram_0x008, ACCESS
    movlb       0x1
    movlw       0xB0
    addwf       ram_0x00A, W, ACCESS
    call        setup_fsr2_page_1, 0x0
    movf        INDF2, W, ACCESS
    movwf       ram_0x009, ACCESS
    call        main_flash_service_46de, 0x0
    incf        ram_0x00A, F, ACCESS
    movlw       0x5E
    cpfsgt      ram_0x00A, ACCESS
    bra         flow_main_core_service_265c_2794
    movlb       0x0
    bcf         ram_0x0BD, 4, BANKED
flow_main_core_service_265c_27bc:
    btfss       ram_0x0BD, 5, BANKED
    bra         flow_main_core_service_265c_27ec
    call        preset_persist_filename, 0x0
    ; V3.2 USB-xact gate: clear bit6 once the EEPROM persist has
    ; completed.  Whether the dirty bit was set by a USB cmd 0x03 or
    ; by a separate path, the gate is cleared here so deferred preset
    ; broadcasts can resume.  preset_persist_filename is foreground-
    ; atomic (its outgoing-slot decision is made at entry; see
    ; asm:preset_persist_filename header), so by the time we reach
    ; this bcf the wire-state for the active preset is fully on
    ; EEPROM and a queued preset switch is now safe to proceed.  Explicit
    ; movlb 0x0 because preset_persist_filename's loop calls
    ; main_flash_service_46de which may leave BSR in a different bank.
    movlb       0x0
    bcf         ram_0x0BD, 6, BANKED
flow_main_core_service_265c_27ec:
    bcf         event_flags, 0, BANKED
flow_main_core_service_265c_27ee:
    return      0


; ---------------------------------------------------------------------------
; Helper: eeprom_persist_block_walker      (rewrite of main_core_service_265c)
; ---------------------------------------------------------------------------
; Processes one static-block's worth of (eeprom_offset, ram_src) records
; from the packed table at `eeprom_persist_static_records`.
;
; Entry : W       = bit mask for this block (e.g. 0x01 for ram_0x0BD.bit0).
;         TBLPTR  = points at the count byte for this block in the table.
;                   Caller seeds TBLPTR once at the start of the table; the
;                   walker advances it past the count byte and all records
;                   so a subsequent call consumes the next block.
; Effect: Reads the count byte.  Consumes `count` (offset, src_lo) pairs
;         from TBLPTR.  If the mask bit is set in ram_0x0BD, each pair
;         triggers a call to main_flash_service_46de with
;             ram_0x008 = 0 (addr_hi),
;             ram_0x007 = offset,
;             ram_0x009 = *(bank 0 RAM at src_lo).
;         The matching bit in ram_0x0BD is cleared iff the walk fired.
;         BSR = 0 on exit (same contract as the inline version).
; Scratch: ram_0x00A (mask save), ram_0x00B (gate), ram_0x013 (loop count),
;          ram_0x003/4/7/8/9 (main_flash_service_46de I/O), FSR0.
; ---------------------------------------------------------------------------
eeprom_persist_block_walker:
    movwf       ram_0x00A, ACCESS                ; save the bit mask
    tblrd*+                                      ; fetch record count
    movff       TABLAT, ram_0x013
    movf        ram_0x0BD, W, BANKED             ; BSR = 0 on entry
    andwf       ram_0x00A, W, ACCESS
    movwf       ram_0x00B, ACCESS                ; non-zero => do the work
eeprom_persist_record_loop:
    tblrd*+                                      ; fetch EEPROM offset
    movff       TABLAT, ram_0x007
    tblrd*+                                      ; fetch bank-0 src_lo
    movff       TABLAT, FSR0L
    clrf        FSR0H, ACCESS                    ; all source RAM in bank 0
    movf        ram_0x00B, F, ACCESS             ; is the gate still set?
    btfsc       STATUS, 2, ACCESS                ; Z => bit was clear
    bra         eeprom_persist_record_next
    clrf        ram_0x008, ACCESS
    movff       INDF0, ram_0x009
    call        main_flash_service_46de, 0x0
eeprom_persist_record_next:
    decfsz      ram_0x013, F, ACCESS
    bra         eeprom_persist_record_loop
    movf        ram_0x00B, F, ACCESS
    btfsc       STATUS, 2, ACCESS                ; gate was clear: no bit to clear
    return      0
    movlb       0x0
    comf        ram_0x00A, W, ACCESS             ; W = ~mask
    andwf       ram_0x0BD, F, BANKED             ; drop only this block's bit
    return      0


; ---------------------------------------------------------------------------
; Data: eeprom_persist_static_records
; ---------------------------------------------------------------------------
; Packed TBLRD-addressable table consumed by `eeprom_persist_block_walker`,
; one record per pair of `(eeprom_offset, src_ram_lo)`.  Each block starts
; with a 1-byte count header.  Block order mirrors the pre-rewrite
; `btfss ram_0x0BD,N` sequence so the walker is driven by the same 4
; calls in main_core_service_265c.
;
; All 42 bytes are emitted in a single `db` statement so gpasm packs them
; into consecutive program-memory bytes with no inter-block 0x00 padding
; (a separate `db <odd-length>` for each block would add one byte of
; padding per block, which TBLRD*+ would misread as a zero offset/src).
;
; Layout (byte offset from table start):
;   [ 0]  0x07                    ; block 0 count = 7 records
;   [ 1]  0x03, 0x6E              ; rec 0: EEPROM[0x03] <- computed_volume   (0x06E)
;   [ 3]  0x02, 0x6F              ; rec 1: EEPROM[0x02] <- computed_volume_1 (0x06F)
;   [ 5]  0x01, 0x70              ; rec 2: EEPROM[0x01] <- computed_volume_2 (0x070)
;   [ 7]  0x00, 0x71              ; rec 3: EEPROM[0x00] <- computed_volume_3 (0x071)
;   [ 9]  0x04, 0x99              ; rec 4: EEPROM[0x04] <- input_select      (0x099)
;   [11]  0x0D, 0x5F              ; rec 5: EEPROM[0x0D] <- ram_0x05F
;   [13]  0x14, 0xC3              ; rec 6: EEPROM[0x14] <- ram_0x0C3
;   [15]  0x06                    ; block 1 count = 6 records
;   [16]  0x07, 0x60              ; rec 0: EEPROM[0x07] <- ram_0x060
;   [18]  0x08, 0x61              ; rec 1: EEPROM[0x08] <- ram_0x061
;   [20]  0x09, 0x62              ; rec 2
;   [22]  0x0A, 0x63              ; rec 3
;   [24]  0x0B, 0x64              ; rec 4
;   [26]  0x0C, 0x65              ; rec 5
;   [28]  0x02                    ; block 2 count = 2 records
;   [29]  0x0F, 0xB4              ; rec 0: EEPROM[0x0F] <- ram_0x0B4
;   [31]  0x0E, 0xB8              ; rec 1: EEPROM[0x0E] <- ram_0x0B8
;   [33]  0x04                    ; block 3 count = 4 records
;   [34]  0x10, 0x9B              ; rec 0: EEPROM[0x10] <- ram_0x09B
;   [36]  0x11, 0x9C              ; rec 1
;   [38]  0x12, 0x9D              ; rec 2
;   [40]  0x13, 0x9E              ; rec 3 — table ends at byte 42
; ---------------------------------------------------------------------------
eeprom_persist_static_records:
    ; 42 bytes total, emitted in one `db` statement so gpasm doesn't
    ; pad any inter-block or end-of-statement byte to word alignment.
    db  0x07, 0x03, 0x6E, 0x02, 0x6F, 0x01, 0x70, 0x00, 0x71, 0x04, 0x99, 0x0D, 0x5F, 0x14, 0xC3, 0x06, 0x07, 0x60, 0x08, 0x61, 0x09, 0x62, 0x0A, 0x63, 0x0B, 0x64, 0x0C, 0x65, 0x02, 0x0F, 0xB4, 0x0E, 0xB8, 0x04, 0x10, 0x9B, 0x11, 0x9C, 0x12, 0x9D, 0x13, 0x9E


; ---------------------------------------------------------------------------
; Function: main_i2c_service_27f0          (periodic DSP/secondary refresh)
; Address : 0x27F0
; ---------------------------------------------------------------------------
; Periodic-loop slot 4 (called from periodic_service_loop). Active gate
; (active_flags.bit3) gated. Performs:
;   • ram_0x0BB watchdog increment (cleared elsewhere on activity); when it
;     exceeds 0x64 (~100 service ticks), dispatches a refresh of the
;     secondary device (0x71) state via i2c_secondary_dev_write.
;   • Reads current ram_0x05F status from secondary via
;     i2c_secondary_dev_random_read.
;   • Compares against expected and queues channel/source-select fixups
;     into ram_0x093 for the next cmd_dispatch_gated pass.
; This is the slow-housekeeping I2C path; the fast volume/preset paths go
; through volume_dsp_write and preset_job_apply_i2c_entry respectively.
; ---------------------------------------------------------------------------
main_i2c_service_27f0:
    btfss       active_flags, 3, ACCESS
    bra         flow_main_i2c_service_27f0_297c
    movlw       0x64
    movlb       0x0
    cpfsgt      ram_0x0BB, BANKED
    bra         flow_main_i2c_service_27f0_297a
    clrf        ram_0x0BB, BANKED
    bra         flow_main_i2c_service_27f0_28aa
flow_main_i2c_service_27f0_2800:
    movf        ram_0x0B6, W, BANKED
    addlw       0x08
    movwf       ram_0x0BE, BANKED
    bra         flow_main_i2c_service_27f0_28ce
flow_main_i2c_service_27f0_2808:
    clrf        ram_0x093, BANKED
    bra         flow_main_i2c_service_27f0_28ce
flow_main_i2c_service_27f0_280c:
    movlw       0x01
    movwf       ram_0x093, BANKED
    movf        ram_0x05F, W, ACCESS
    bz          flow_main_i2c_service_27f0_28ce
    movlw       0x05
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_2818:
    movlw       0x02
    movwf       ram_0x093, BANKED
    decf        ram_0x05F, W, ACCESS
    bnz         flow_main_i2c_service_27f0_2824
    movlw       0x01
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2824:
    movlw       0x01
    cpfsgt      ram_0x05F, ACCESS
    bra         flow_main_i2c_service_27f0_28ce
    movlw       0x06
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_282e:
    movlw       0x03
    movwf       ram_0x093, BANKED
    decf        ram_0x05F, W, ACCESS
    bnz         flow_main_i2c_service_27f0_283a
    movlw       0x02
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_283a:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         flow_main_i2c_service_27f0_2844
    movlw       0x01
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2844:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         flow_main_i2c_service_27f0_28ce
    movlw       0x07
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_284e:
    movlw       0x04
    movwf       ram_0x093, BANKED
    decf        ram_0x05F, W, ACCESS
    bnz         flow_main_i2c_service_27f0_285a
    movlw       0x03
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_285a:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         flow_main_i2c_service_27f0_2864
    movlw       0x02
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2864:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         flow_main_i2c_service_27f0_28ce
    movlw       0x01
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_286e:
    decf        ram_0x05F, W, ACCESS
    bnz         flow_main_i2c_service_27f0_2876
    movlw       0x04
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2876:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         flow_main_i2c_service_27f0_2880
    movlw       0x03
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2880:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         flow_main_i2c_service_27f0_28ce
    movlw       0x02
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_288a:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x02
    bnz         flow_main_i2c_service_27f0_2894
    movlw       0x04
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2894:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         flow_main_i2c_service_27f0_28ce
    movlw       0x03
    bra         flow_main_i2c_service_27f0_28a6
flow_main_i2c_service_27f0_289e:
    movf        ram_0x05F, W, ACCESS
    xorlw       0x03
    bnz         flow_main_i2c_service_27f0_28ce
    movlw       0x04
flow_main_i2c_service_27f0_28a6:
    movwf       ram_0x093, BANKED
    bra         flow_main_i2c_service_27f0_28ce
flow_main_i2c_service_27f0_28aa:
    movf        input_select, W, BANKED
    bz          flow_main_i2c_service_27f0_2800
    xorlw       0x01
    bz          flow_main_i2c_service_27f0_2808
    xorlw       0x03
    bz          flow_main_i2c_service_27f0_280c
    xorlw       0x01
    bz          flow_main_i2c_service_27f0_2818
    xorlw       0x07
    bz          flow_main_i2c_service_27f0_282e
    xorlw       0x01
    bz          flow_main_i2c_service_27f0_284e
    xorlw       0x03
    bz          flow_main_i2c_service_27f0_286e
    xorlw       0x01
    bz          flow_main_i2c_service_27f0_288a
    xorlw       0x0F
    bz          flow_main_i2c_service_27f0_289e
flow_main_i2c_service_27f0_28ce:
    tstfsz      input_select, BANKED
    bra         flow_main_i2c_service_27f0_2902
    movff       ram_0x0BE, ram_0x006
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x13
    call        i2c_secondary_dev_random_read, 0x0
    movlb       0x0
    movwf       ram_0x0BE, BANKED
    tstfsz      ram_0x0BE, BANKED
    bra         flow_main_i2c_service_27f0_290a
    clrf        ram_0x093, BANKED
    movlw       0x0A
    cpfsgt      ram_0x0BA, BANKED
    bra         flow_main_i2c_service_27f0_2906
    clrf        ram_0x0BA, BANKED
    movlw       0x04
    subwf       ram_0x0B6, W, BANKED
    btfss       STATUS, 0, ACCESS
    incf        ram_0x0B6, F, BANKED
    movf        ram_0x0B6, W, BANKED
    xorlw       0x04
    bnz         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_2902:
    clrf        ram_0x0B6, BANKED
    bra         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_2906:
    incf        ram_0x0BA, F, BANKED
    bra         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_290a:
    tstfsz      ram_0x0B6, BANKED
    bra         flow_main_i2c_service_27f0_2912
    movlw       0x03
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2912:
    decf        ram_0x0B6, W, BANKED
    bnz         flow_main_i2c_service_27f0_291a
    movlw       0x01
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_291a:
    movf        ram_0x0B6, W, BANKED
    xorlw       0x02
    bnz         flow_main_i2c_service_27f0_2924
    movlw       0x02
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_2924:
    movf        ram_0x0B6, W, BANKED
    xorlw       0x03
    bnz         flow_main_i2c_service_27f0_292e
    movlw       0x04
    movwf       ram_0x093, BANKED
flow_main_i2c_service_27f0_292e:
    movlw       0x12
    call        i2c_secondary_dev_random_read, 0x0
    movlb       0x0
    movwf       ram_0x0BF, BANKED
    movf        ram_0x0BF, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         active_flags, 4, ACCESS
    movlw       0x01
    btfss       active_flags, 4, ACCESS
    movlw       0x00
    movwf       ram_0x008, ACCESS
    movlw       0x01
    btfss       active_flags, 5, ACCESS
    movlw       0x00
    xorwf       ram_0x008, F, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 5, BANKED
    btfss       active_flags, 4, ACCESS
    bra         flow_main_i2c_service_27f0_295a
    bsf         active_flags, 5, ACCESS
    bra         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_295a:
    bcf         active_flags, 5, ACCESS
flow_main_i2c_service_27f0_295c:
    movlb       0x0
    movf        ram_0x093, W, BANKED
    xorlw       0x02
    btfsc       STATUS, 2, ACCESS
    btfsc       PORTC, 0, ACCESS
    bra         flow_main_i2c_service_27f0_296c
    movff       ram_0x0C3, ram_0x093
flow_main_i2c_service_27f0_296c:
    movf        ram_0x0AB, W, BANKED
    xorwf       ram_0x093, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags, 1, BANKED
    movff       ram_0x093, ram_0x0AB
    bra         flow_main_i2c_service_27f0_297c
flow_main_i2c_service_27f0_297a:
    incf        ram_0x0BB, F, BANKED
flow_main_i2c_service_27f0_297c:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_297e
; Address : 0x297E
; Notes   : Inferred core helper routine. Calls: main_core_service_2ca8, main_core_service_24c2, main_core_service_3ec4.
; ---------------------------------------------------------------------------
main_core_service_297e:
    clrf        ram_0x011, ACCESS
    clrf        ram_0x012, ACCESS
    movlw       0x80
    movwf       ram_0x013, ACCESS
    movlw       0x44
    movwf       ram_0x014, ACCESS
    movff       ram_0x02F, ram_0x00D
    movff       ram_0x030, ram_0x00E
    movff       ram_0x031, ram_0x00F
    movff       ram_0x032, ram_0x010
    rcall       main_core_service_2ca8
    movff       ram_0x00D, ram_0x020
    movff       ram_0x00E, ram_0x021
    movff       ram_0x00F, ram_0x022
    movff       ram_0x010, ram_0x023
    clrf        ram_0x024, ACCESS
    clrf        ram_0x025, ACCESS
    movlw       0x80
    movwf       ram_0x026, ACCESS
    movlw       0x3F
    movwf       ram_0x027, ACCESS
    rcall       main_core_service_24c2
    movff       ram_0x020, ram_0x02F
    movff       ram_0x021, ram_0x030
    movff       ram_0x022, ram_0x031
    movff       ram_0x023, ram_0x032
    movlw       0x0A
    movwf       ram_0x011, ACCESS
flow_main_core_service_297e_apply_loop:
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    decfsz      ram_0x011, F, ACCESS
    bra         flow_main_core_service_297e_apply_loop
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2abc
; Address : 0x2ABC
; Notes   : Inferred core helper routine. Calls: main_core_service_2bac, main_core_service_2b8e, main_core_service_2b9e.
; ---------------------------------------------------------------------------
main_core_service_2abc:
    movff       ram_0x012, ram_0x01A
    movff       ram_0x013, ram_0x01B
    movff       ram_0x014, ram_0x01C
    movff       ram_0x015, ram_0x01D
    movlw       0x18
    bra         flow_main_core_service_2abc_2ad2
flow_main_core_service_2abc_2ad0:
    rcall       main_core_service_2bac
flow_main_core_service_2abc_2ad2:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2abc_2ad0
    movf        ram_0x01A, W, ACCESS
    movwf       ram_0x01E, ACCESS
    tstfsz      ram_0x01E, ACCESS
    bra         flow_main_core_service_2abc_2ae0
    bra         flow_main_core_service_2abc_2b02
flow_main_core_service_2abc_2ae0:
    movff       ram_0x016, ram_0x01A
    movff       ram_0x017, ram_0x01B
    movff       ram_0x018, ram_0x01C
    movff       ram_0x019, ram_0x01D
    movlw       0x18
    bra         flow_main_core_service_2abc_2af6
flow_main_core_service_2abc_2af4:
    rcall       main_core_service_2bac
flow_main_core_service_2abc_2af6:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2abc_2af4
    movf        ram_0x01A, W, ACCESS
    movwf       ram_0x024, ACCESS
    tstfsz      ram_0x024, ACCESS
    bra         flow_main_core_service_2abc_2b0c
flow_main_core_service_2abc_2b02:
    clrf        ram_0x012, ACCESS
    clrf        ram_0x013, ACCESS
    clrf        ram_0x014, ACCESS
    clrf        ram_0x015, ACCESS
    bra         flow_main_core_service_2abc_2b8c
flow_main_core_service_2abc_2b0c:
    movf        ram_0x024, W, ACCESS
    addlw       0x7B
    addwf       ram_0x01E, F, ACCESS
    movff       ram_0x015, ram_0x024
    movf        ram_0x019, W, ACCESS
    xorwf       ram_0x024, F, ACCESS
    movlw       0x80
    andwf       ram_0x024, F, ACCESS
    bsf         ram_0x014, 7, ACCESS
    bsf         ram_0x018, 7, ACCESS
    clrf        ram_0x019, ACCESS
    clrf        ram_0x01F, ACCESS
    clrf        ram_0x020, ACCESS
    clrf        ram_0x021, ACCESS
    clrf        ram_0x022, ACCESS
    movlw       0x07
    movwf       ram_0x023, ACCESS
flow_main_core_service_2abc_2b30:
    btfss       ram_0x012, 0, ACCESS
    bra         flow_main_core_service_2abc_2b38
    movf        ram_0x016, W, ACCESS
    rcall       main_core_service_2b8e
flow_main_core_service_2abc_2b38:
    rcall       main_core_service_2b9e
    rlcf        ram_0x016, F, ACCESS
    rlcf        ram_0x017, F, ACCESS
    rlcf        ram_0x018, F, ACCESS
    rlcf        ram_0x019, F, ACCESS
    decfsz      ram_0x023, F, ACCESS
    bra         flow_main_core_service_2abc_2b30
    movlw       0x11
    movwf       ram_0x023, ACCESS
flow_main_core_service_2abc_2b4a:
    btfss       ram_0x012, 0, ACCESS
    bra         flow_main_core_service_2abc_2b52
    movf        ram_0x016, W, ACCESS
    rcall       main_core_service_2b8e
flow_main_core_service_2abc_2b52:
    rcall       main_core_service_2b9e
    rrcf        ram_0x022, F, ACCESS
    rrcf        ram_0x021, F, ACCESS
    rrcf        ram_0x020, F, ACCESS
    rrcf        ram_0x01F, F, ACCESS
    decfsz      ram_0x023, F, ACCESS
    bra         flow_main_core_service_2abc_2b4a
    movff       ram_0x01F, ram_0x003
    movff       ram_0x020, ram_0x004
    movff       ram_0x021, ram_0x005
    movff       ram_0x022, ram_0x006
    movff       ram_0x01E, ram_0x007
    movff       ram_0x024, ram_0x008
    rcall       main_core_service_30d8
    movff       ram_0x003, ram_0x012
    movff       ram_0x004, ram_0x013
    movff       ram_0x005, ram_0x014
    movff       ram_0x006, ram_0x015
flow_main_core_service_2abc_2b8c:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2b8e
; Address : 0x2B8E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2b8e:
    addwf       ram_0x01F, F, ACCESS
    movf        ram_0x017, W, ACCESS
    addwfc      ram_0x020, F, ACCESS
    movf        ram_0x018, W, ACCESS
    addwfc      ram_0x021, F, ACCESS
    movf        ram_0x019, W, ACCESS
    addwfc      ram_0x022, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2b9e
; Address : 0x2B9E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2b9e:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x015, F, ACCESS
    rrcf        ram_0x014, F, ACCESS
    rrcf        ram_0x013, F, ACCESS
    rrcf        ram_0x012, F, ACCESS
    bcf         STATUS, 0, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2bac
; Address : 0x2BAC
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2bac:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x01D, F, ACCESS
    rrcf        ram_0x01C, F, ACCESS
    rrcf        ram_0x01B, F, ACCESS
    rrcf        ram_0x01A, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Helper: flash_addr_setup_from_82_83 (W04-E04)
; Copies the caller-selected flash address held at ram_0x082:ram_0x083
; (little-endian) into ram_0x003:ram_0x004, and zeros ram_0x005:ram_0x006.
; Used as the common address preamble for flash_read / flash_erase /
; flash_write paths inside main_flash_service_2bb8.
; Uses only ACCESS-bank + movff, so BSR is preserved across the call.
; ---------------------------------------------------------------------------
flash_addr_setup_from_82_83:
    movff       ram_0x082, ram_0x003
    movff       ram_0x083, ram_0x004
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_2bb8
; Address : 0x2BB8
; Notes   : Inferred flash helper routine. Calls: flash_read, flash_erase, flash_write.
; ---------------------------------------------------------------------------
main_flash_service_2bb8:
    tstfsz      ram_0x0C5, BANKED
    bra         flow_main_flash_service_2bb8_2bdc
    rcall       flash_addr_setup_from_82_83
    clrf        ram_0x008, ACCESS
    movlw       0xC0
    movwf       ram_0x007, ACCESS
    movlb       0x3
    movlw       0x03
    movwf       ram_0x00A, ACCESS
    clrf        ram_0x009, ACCESS
    call        flash_read, 0x0
flow_main_flash_service_2bb8_2bdc:
    movlb       0x1
    movf        ram_0x01B, W, BANKED
    bz          flow_main_flash_service_2bb8_2bea
    clrf        ram_0x01D, ACCESS
    movlw       0x02
    movwf       ram_0x01C, ACCESS
    bra         flow_main_flash_service_2bb8_2bee
flow_main_flash_service_2bb8_2bea:
    clrf        ram_0x01C, ACCESS
    clrf        ram_0x01D, ACCESS
flow_main_flash_service_2bb8_2bee:
    movff       ram_0x01C, ram_0x01E
    movlw       0x04
    movwf       ram_0x01F, ACCESS
flow_main_flash_service_2bb8_2bf6:
    movlw       0x1A
    movwf       ram_0x018, ACCESS
    movlw       0x01
    movwf       ram_0x019, ACCESS
    movf        ram_0x01F, W, ACCESS
    addwf       ram_0x018, F, ACCESS
    movlw       0x00
    addwfc      ram_0x019, F, ACCESS
    movf        ram_0x01E, W, ACCESS
    subwf       ram_0x018, W, ACCESS
    movwf       FSR2L, ACCESS
    movf        ram_0x019, W, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x019, W, ACCESS
    movwf       FSR2H, ACCESS
    clrf        ram_0x01A, ACCESS
    movlw       0x03
    movwf       ram_0x01B, ACCESS
    movlb       0x0
    movf        ram_0x0C5, W, BANKED
    addwf       ram_0x01A, F, ACCESS
    movlw       0x00
    addwfc      ram_0x01B, F, ACCESS
    movf        ram_0x01F, W, ACCESS
    addwf       ram_0x01A, W, ACCESS
    movwf       FSR1L, ACCESS
    movlw       0x00
    addwfc      ram_0x01B, W, ACCESS
    movwf       FSR1H, ACCESS
    movff       INDF2, INDF1
    incf        ram_0x01F, F, ACCESS
    movlw       0x17
    cpfsgt      ram_0x01F, ACCESS
    bra         flow_main_flash_service_2bb8_2bf6
    movlw       0x18
    addwf       ram_0x0C5, F, BANKED
    movlw       0xBF
    cpfsgt      ram_0x0C5, BANKED
    bra         flow_main_flash_service_2bb8_2ca6
    clrf        ram_0x0C5, BANKED
    movlw       0x3F
    subwf       ram_0x082, W, BANKED
    movlw       0x5F
    subwfb      ram_0x083, W, BANKED
    bc          flow_main_flash_service_2bb8_2ca6
    rcall       flash_addr_setup_from_82_83
    movlw       0xBF
    addwf       ram_0x082, W, BANKED
    movwf       ram_0x018, ACCESS
    movlw       0x00
    addwfc      ram_0x083, W, BANKED
    movwf       ram_0x019, ACCESS
    movff       ram_0x018, ram_0x007
    movff       ram_0x019, ram_0x008
    clrf        ram_0x009, ACCESS
    clrf        ram_0x00A, ACCESS
    call        flash_erase, 0x0
    rcall       flash_addr_setup_from_82_83
    clrf        ram_0x008, ACCESS
    movlw       0xC0
    movwf       ram_0x007, ACCESS
    movlb       0x3
    movlw       0x03
    movwf       ram_0x00A, ACCESS
    clrf        ram_0x009, ACCESS
    rcall       flash_write
    movlw       0xC0
    movlb       0x0
    addwf       ram_0x082, F, BANKED
    movlw       0x00
    addwfc      ram_0x083, F, BANKED
flow_main_flash_service_2bb8_2ca6:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2ca8
; Address : 0x2CA8
; Notes   : Inferred core helper routine. Calls: main_core_service_2d80, main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_2ca8:
    movff       ram_0x00D, ram_0x015
    movff       ram_0x00E, ram_0x016
    movff       ram_0x00F, ram_0x017
    movff       ram_0x010, ram_0x018
    movlw       0x18
    bra         flow_main_core_service_2ca8_2cbe
flow_main_core_service_2ca8_2cbc:
    rcall       main_core_service_2d80
flow_main_core_service_2ca8_2cbe:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2ca8_2cbc
    movf        ram_0x015, W, ACCESS
    movwf       ram_0x01E, ACCESS
    tstfsz      ram_0x01E, ACCESS
    bra         flow_main_core_service_2ca8_2ccc
    bra         flow_main_core_service_2ca8_2cee
flow_main_core_service_2ca8_2ccc:
    movff       ram_0x011, ram_0x015
    movff       ram_0x012, ram_0x016
    movff       ram_0x013, ram_0x017
    movff       ram_0x014, ram_0x018
    movlw       0x18
    bra         flow_main_core_service_2ca8_2ce2
flow_main_core_service_2ca8_2ce0:
    rcall       main_core_service_2d80
flow_main_core_service_2ca8_2ce2:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2ca8_2ce0
    movf        ram_0x015, W, ACCESS
    movwf       ram_0x01F, ACCESS
    tstfsz      ram_0x01F, ACCESS
    bra         flow_main_core_service_2ca8_2cf8
flow_main_core_service_2ca8_2cee:
    clrf        ram_0x00D, ACCESS
    clrf        ram_0x00E, ACCESS
    clrf        ram_0x00F, ACCESS
    clrf        ram_0x010, ACCESS
    bra         flow_main_core_service_2ca8_2d7e
flow_main_core_service_2ca8_2cf8:
    movf        ram_0x01F, W, ACCESS
    addlw       0x89
    subwf       ram_0x01E, F, ACCESS
    movff       ram_0x010, ram_0x01F
    movf        ram_0x014, W, ACCESS
    xorwf       ram_0x01F, F, ACCESS
    movlw       0x80
    andwf       ram_0x01F, F, ACCESS
    bsf         ram_0x00F, 7, ACCESS
    clrf        ram_0x010, ACCESS
    bsf         ram_0x013, 7, ACCESS
    clrf        ram_0x014, ACCESS
    movlw       0x20
    movwf       ram_0x01D, ACCESS
flow_main_core_service_2ca8_2d16:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x019, F, ACCESS
    rlcf        ram_0x01A, F, ACCESS
    rlcf        ram_0x01B, F, ACCESS
    rlcf        ram_0x01C, F, ACCESS
    movf        ram_0x011, W, ACCESS
    subwf       ram_0x00D, W, ACCESS
    movf        ram_0x012, W, ACCESS
    subwfb      ram_0x00E, W, ACCESS
    movf        ram_0x013, W, ACCESS
    subwfb      ram_0x00F, W, ACCESS
    movf        ram_0x014, W, ACCESS
    subwfb      ram_0x010, W, ACCESS
    bnc         flow_main_core_service_2ca8_2d44
    movf        ram_0x011, W, ACCESS
    subwf       ram_0x00D, F, ACCESS
    movf        ram_0x012, W, ACCESS
    subwfb      ram_0x00E, F, ACCESS
    movf        ram_0x013, W, ACCESS
    subwfb      ram_0x00F, F, ACCESS
    movf        ram_0x014, W, ACCESS
    subwfb      ram_0x010, F, ACCESS
    bsf         ram_0x019, 0, ACCESS
flow_main_core_service_2ca8_2d44:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x00D, F, ACCESS
    rlcf        ram_0x00E, F, ACCESS
    rlcf        ram_0x00F, F, ACCESS
    rlcf        ram_0x010, F, ACCESS
    decfsz      ram_0x01D, F, ACCESS
    bra         flow_main_core_service_2ca8_2d16
    movff       ram_0x019, ram_0x003
    movff       ram_0x01A, ram_0x004
    movff       ram_0x01B, ram_0x005
    movff       ram_0x01C, ram_0x006
    movff       ram_0x01E, ram_0x007
    movff       ram_0x01F, ram_0x008
    ; W04-E01: factor rcall+4 movff tail into main_core_service_30d8_with_save
    bra         main_core_service_30d8_with_save
flow_main_core_service_2ca8_2d7e:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2d80
; Address : 0x2D80
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2d80:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x018, F, ACCESS
    rrcf        ram_0x017, F, ACCESS
    rrcf        ram_0x016, F, ACCESS
    rrcf        ram_0x015, F, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: adc_boot_gate                  (rail-rise wait + DSP cold init)
; Address : 0x2D8C
; ---------------------------------------------------------------------------
; Phase A — RAIL WAIT (BUG M9: unbounded). With INTCON.GIE=0, samples AN0
;   (12-bit ADC) every 10 ms and stores ram_0x088:089. Loop exits when
;   ram_0x088:089 ≥ 0x0236 (i.e. supply rail is up). There is no timeout: a
;   stuck rail blocks here forever. The V3.2 hardening plan workstream 5
;   would gate this with a watchdog.
;
; Phase B — DSP COLD BRING-UP. Once the rail is good:
;   • Quiesce the EUSART first so reconnect polls cannot accumulate into OERR
;     while GIE stays masked across the long wake delays.
;   • 70 ms timer3 settle
;   • OSCCON.SCS1 = 0 (HS oscillator selected), SPBRG = 0x7F (31,250 baud)
;   • Drop LATB.bit4, LATA.bit6 (amp enable lines), drop LATB.bit3
;   • SSPCON1.SSPEN = 0, tristate RB0/RB1 (release SDA/SCL)
;   • 100 ms idle, then a 1500 ms (5 * 256 + 0xDC) settle while LATB.bit4
;     is asserted (PSU stable indicator)
;   • mssp_hard_reset with W=0x08 (SSPM master) and ram_0x003=0x80 (SMP=1)
;   • Re-arm I2C and write zero coefficient to TAS3108 (mute the DSP),
;     then run main_core_service_4574 (preset table apply)
;   • Bring LATB.bit3 back up (amp enable), re-arm the UART in TX-only mode
;     so wake-time BF/08 fault-clear traffic cannot trip the bounded TRMT
;     panic path, then set the housekeeping event flags so cmd_dispatch_gated
;     does the volume/mute/preset reconciliation.
;   • Finally re-run the cold-boot UART bring-up with RX enabled, re-arm Timer0
;     (TMR0=0xA471, ~50 ms) and INTCON.T0IE.  Wake exits through the same UART
;     state as cold boot; CONTROL reconnect then relies on its normal poll
;     loop instead of whatever stale bytes survived the blind wake window.
;
; This is the routine called from standby_event_dispatch when the gate is
; reopened — i.e. when CONTROL sends a wake B0/03/01 frame after standby.
; ---------------------------------------------------------------------------
adc_boot_gate:
    bcf         INTCON, 7, ACCESS
    call        uart_quiesce_for_wake, 0x0
    bcf         LATB, 2, ACCESS
    movlb       0x0
    clrf        ram_0x088, BANKED
    clrf        ram_0x089, BANKED
    bsf         ADCON0, 1, ACCESS
    ; Bug #45 §C: bound the rail-rise wait at ~50 iters * 10 ms = ~500 ms so a
    ; depressed AN0 (e.g. asymmetric shared-rail coupling on a two-MAIN chain)
    ; cannot pin this MAIN inside the polling loop indefinitely.  ram_0x008 is
    ; ACCESS BANK scratch -- safe for the gate scope: the only call inside the
    ; loop is timer3_blocking_delay_ms_W which uses ram_0x003/0x004 for its
    ; own countdown.
    movlw       0x32
    movwf       ram_0x008, ACCESS
adc_boot_gate_loop:
    movlw       0x0A
    call        timer3_blocking_delay_ms_W, 0x0 ; W04-E08 factored (10 ms poll)
    btfsc       ADCON0, 1, ACCESS
    bra         flow_adc_boot_gate_2dbc
    movf        ADRESH, W, ACCESS
    movwf       ram_0x05D, ACCESS
    clrf        ram_0x05C, ACCESS
    movf        ADRESL, W, ACCESS
    addwf       ram_0x05C, W, ACCESS
    movlb       0x0
    movwf       ram_0x088, BANKED
    movlw       0x00
    addwfc      ram_0x05D, W, ACCESS
    movwf       ram_0x089, BANKED
    bsf         ADCON0, 1, ACCESS
flow_adc_boot_gate_2dbc:
    movlw       0x36
    movlb       0x0
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    bc          adc_boot_gate_exit
    decfsz      ram_0x008, F, ACCESS
    bra         adc_boot_gate_loop
    ; Counter exhausted -- proceed with bring-up despite low rail.  If the
    ; rail is still genuinely bad, downstream supplies will collapse and BOR
    ; will fire a fresh cold boot; either is preferable to wedging silently
    ; inside the loop with no CPU activity visible to the chain.
adc_boot_gate_exit:
    movlw       0x46
    call        timer3_blocking_delay_ms_W, 0x0 ; W04-E08 factored (~70 ms)
    call        uart_baud_31250_prefix, 0x0
    bcf         LATB, 4, ACCESS
    bcf         LATA, 6, ACCESS
    bcf         LATB, 3, ACCESS
    bcf         SSPCON1, 5, ACCESS
    bsf         TRISB, 1, ACCESS
    bsf         TRISB, 0, ACCESS
    movlw       0x64
    call        timer3_blocking_delay_ms_W, 0x0 ; W04-E08 factored (100 ms)
    bsf         LATB, 4, ACCESS
    movlw       0x05
    movwf       ram_0x004, ACCESS
    movlw       0xDC
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    bsf         TRISB, 1, ACCESS
    bsf         TRISB, 0, ACCESS
    movlw       0x01
    call        timer3_blocking_delay_ms_W, 0x0 ; W04-E08 factored (1 ms)
    movlw       0x80
    movwf       ram_0x003, ACCESS
    movlw       0x08
    call        mssp_hard_reset, 0x0
    bsf         LATA, 6, ACCESS
    call        clrf_i2c_coeff_0123_and_write, 0x0  ; W03-E02: factored 5-line pattern
    call        main_core_service_4574, 0x0
    bsf         LATB, 3, ACCESS
    call        main_core_service_4942, 0x0
    rcall       main_i2c_service_32f8
    call        main_core_service_4942, 0x0
    call        main_uart_tx_only_service, 0x0
    ; Bug #45 H2: re-emit B0/03/01 broadcast post-gate.  The parser's
    ; chain-echo at _1e6c forwards the WAKE data byte BEFORE this MAIN
    ; enters adc_boot_gate, but the call to uart_quiesce_for_wake at
    ; gate entry (asm:4043) clears CREN/TXEN/SPEN -- if the third byte
    ; of the broadcast was still in the TX path (sw ring, TXREG, or
    ; TSR shift register) when quiesce hit, it never makes it onto the
    ; wire.  MAIN1 then sees only `B0 03 ...` (incomplete frame) and
    ; never wakes, producing the field-bug observable: CONTROL stuck
    ; in `Waiting for DLCP` because MAIN1 never sends its
    ; sentinel-clearing BF/04 status burst.  Re-emit unconditionally
    ; here -- on cold boot a downstream MAIN is also booting, so a
    ; spurious WAKE broadcast is consumed harmlessly (gate-already-open
    ; path); CONTROL handles unsolicited broadcast bytes idempotently.
    movlw       0xB0
    call        uart_tx_byte_blocking, 0x0
    movlw       0x03
    call        uart_tx_byte_blocking, 0x0
    movlw       0x01
    call        uart_tx_byte_blocking, 0x0
    movlb       0x0
    bsf         event_flags, 1, BANKED
    bsf         event_flags, 3, BANKED
    bsf         event_flags, 4, BANKED
    bsf         ram_0x07F, 0, BANKED
    bsf         ram_0x07F, 1, BANKED
    movlw       0x00
    call        cmd_dispatch_gated, 0x0
    call        send_status_burst, 0x0
    movlw       0x01
    movwf       ram_0x006, ACCESS
    movlw       0x1B
    call        i2c_secondary_dev_write, 0x0
    bcf         INTCON, 5, ACCESS
    bcf         T0CON, 7, ACCESS
    movlw       0xA4
    movwf       TMR0H, ACCESS
    movlw       0x71
    movwf       TMR0L, ACCESS
    movlb       0x0
    clrf        ram_0x0A1, BANKED
    bcf         ram_0x094, 2, BANKED
    call        main_uart_service_4938, 0x0
    bsf         PIE1, 5, ACCESS
    bsf         INTCON, 7, ACCESS
    goto        flow_main_usb_service_490c_4918

; ---------------------------------------------------------------------------
; Function: flash_write                    (program-memory write w/ A/B remap)
; Address : 0x2E6E
; ---------------------------------------------------------------------------
; Stock body (flash_write_stock) is the original Hypex 64-byte tblwt loop:
;   • input: ram_0x003..006 = byte-address (24-bit + zero MSB)
;            ram_0x007:008  = byte-length (16-bit countdown)
;            FSR2 (ram_0x009:00A) = source byte pointer
;   • aligns the start to a 32-byte block (right-shift 5, add 0x20, recover),
;     then for each block copies up to 32 bytes via TBLWT*, sets EECON1 for
;     program memory write (EEPGD=1, CFGS=0, WREN=1), runs the
;     unlock-then-WR sequence in main_flash_service_4406, and reloads the
;     next 32-byte block. INTCON.GIE is preserved across the unlock.
;
; V3.1+ prologue: when active_flags.bit2 (preset B) is set AND the target
; falls in the 0x56xx-0x5FFF flash window, the address ram_0x004 byte is
; pulled down by 0x0A so writes land in the alternate preset table at
; 0x4Cxx-0x55FF (the "preset B" slot built into V2.4+/V3.x images). This
; remap is the binary-patched A/B preset machinery preserved at source level.
;
; BUG M7 (flash_write_with_gie_off): GIE is intentionally cleared during
; writes; the leak is in the wrapper which can return without restoring GIE
; on certain control-flow paths.
; ---------------------------------------------------------------------------
flash_write:
    btfss       active_flags, 2, ACCESS     ; preset B active?
    bra         flash_write_stock
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bnz         flash_write_stock
    movlw       0x56
    subwf       ram_0x004, W, ACCESS
    bnc         flash_write_stock
    movlw       0x60
    subwf       ram_0x004, W, ACCESS
    bc          flash_write_stock
    movlw       0x0A
    subwf       ram_0x004, F, ACCESS
flash_write_stock:
    clrf        ram_0x010, ACCESS
    movff       ram_0x003, ram_0x014
    movff       ram_0x004, ram_0x015
    movff       ram_0x005, ram_0x016
    movff       ram_0x006, ram_0x017
    movlw       0x05
    movwf       ram_0x00B, ACCESS
flow_flash_write_2e84:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    rrcf        ram_0x004, F, ACCESS
    rrcf        ram_0x003, F, ACCESS
    decfsz      ram_0x00B, F, ACCESS
    bra         flow_flash_write_2e84
    movlw       0x05
flow_flash_write_2e94:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x003, F, ACCESS
    rlcf        ram_0x004, F, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    decfsz      WREG, F, ACCESS
    bra         flow_flash_write_2e94
    movlw       0x20
    addwf       ram_0x003, F, ACCESS
    movlw       0x00
    addwfc      ram_0x004, F, ACCESS
    addwfc      ram_0x005, F, ACCESS
    addwfc      ram_0x006, F, ACCESS
    movf        ram_0x014, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movwf       ram_0x00F, ACCESS
    bra         flow_flash_write_2f44
flow_flash_write_2eb6:
    movff       ram_0x016, ram_0x013
    movff       ram_0x015, ram_0x012
    movff       ram_0x014, ram_0x011
    bra         flow_flash_write_2ef6
flow_flash_write_2ec4:
    movff       ram_0x009, FSR2L
    movff       ram_0x00A, FSR2H
    movf        INDF2, W, ACCESS
    movff       ram_0x011, TBLPTRL
    movff       ram_0x012, TBLPTRH
    movff       ram_0x013, TBLPTRU
    movwf       TABLAT, ACCESS
    tblwt*
    infsnz      ram_0x009, F, ACCESS
    incf        ram_0x00A, F, ACCESS
    incf        ram_0x011, F, ACCESS
    movlw       0x00
    addwfc      ram_0x012, F, ACCESS
    addwfc      ram_0x013, F, ACCESS
    decf        ram_0x007, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x008, F, ACCESS
    movf        ram_0x008, W, ACCESS
    iorwf       ram_0x007, W, ACCESS
    bz          flow_flash_write_2efc
flow_flash_write_2ef6:
    decf        ram_0x00F, F, ACCESS
    incf        ram_0x00F, W, ACCESS
    bnz         flow_flash_write_2ec4
flow_flash_write_2efc:
    movff       ram_0x013, ram_0x00E
    movff       ram_0x012, ram_0x00D
    movff       ram_0x011, ram_0x00C
    movff       ram_0x016, ram_0x013
    movff       ram_0x015, ram_0x012
    movff       ram_0x014, ram_0x011
    bsf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    btfss       INTCON, 7, ACCESS
    bra         flow_flash_write_2f24
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       ram_0x010, ACCESS
flow_flash_write_2f24:
    call        main_flash_service_4406, 0x0
    bcf         EECON1, 2, ACCESS
    movf        ram_0x010, W, ACCESS
    bz          flow_flash_write_2f32
    bsf         INTCON, 7, ACCESS
    clrf        ram_0x010, ACCESS
flow_flash_write_2f32:
    movlw       0x20
    movwf       ram_0x00F, ACCESS
    movf        ram_0x00C, W, ACCESS
    movwf       ram_0x014, ACCESS
    movf        ram_0x00D, W, ACCESS
    movwf       ram_0x015, ACCESS
    movf        ram_0x00E, W, ACCESS
    movwf       ram_0x016, ACCESS
    clrf        ram_0x017, ACCESS
flow_flash_write_2f44:
    movf        ram_0x008, W, ACCESS
    iorwf       ram_0x007, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         flow_flash_write_2eb6


; ---------------------------------------------------------------------------
; Function: main_usb_service_2f4e
; Address : 0x2F4E
; Notes   : Inferred usb helper; touches usb. Calls: main_usb_service_475c, main_usb_service_483c, main_usb_service_40d6.
; ---------------------------------------------------------------------------
main_usb_service_2f4e:
    call        main_usb_service_475c, 0x0
    tstfsz      ram_0x0CD, BANKED
    bra         flow_main_usb_service_2f4e_2f58
    bra         flow_main_usb_service_2f4e_3018
flow_main_usb_service_2f4e_2f58:
    btfsc       UIR, 2, ACCESS
    call        main_usb_service_483c, 0x0
    btfsc       UCON, 1, ACCESS
    bra         flow_main_usb_service_2f4e_3018
    btfsc       UIR, 0, ACCESS
    call        main_usb_service_40d6, 0x0
    btfsc       UIR, 4, ACCESS
    call        main_usb_service_4720, 0x0
    movlw       0x03
    movlb       0x0
    subwf       ram_0x0CD, W, BANKED
    bnc         flow_main_usb_service_2f4e_3018
    clrf        ram_0x0C4, BANKED
flow_main_usb_service_2f4e_2f78:
    btfss       UIR, 3, ACCESS
    bra         flow_main_usb_service_2f4e_3018
    movf        USTAT, W, ACCESS
    movff       USTAT, ram_0x006
    movlw       0x7C
    andwf       ram_0x006, F, ACCESS
    bnz         flow_main_usb_service_2f4e_2ffe
    btfsc       USTAT, 1, ACCESS
    bra         flow_main_usb_service_2f4e_2f96
    movlw       0x04
    movlb       0x0
    movwf       ram_0x07B, BANKED
    movlw       0x00
    bra         flow_main_usb_service_2f4e_2f9c
flow_main_usb_service_2f4e_2f96:
    movlw       0x04
    movlb       0x0
    movwf       ram_0x07B, BANKED
flow_main_usb_service_2f4e_2f9c:
    movlb       0x0
    movwf       ram_0x07A, BANKED
    bcf         UIR, 3, ACCESS
    movff       ram_0x07A, FSR2L
    movff       ram_0x07B, FSR2H
    rrcf        INDF2, W, ACCESS
    rrcf        WREG, F, ACCESS
    andlw       0x0F
    xorlw       0x0D
    bnz         flow_main_usb_service_2f4e_300e
    clrf        ram_0x090, BANKED
flow_main_usb_service_2f4e_2fb6:
    lfsr        FSR2, 0x0002
    movf        ram_0x07A, W, BANKED
    addwf       FSR2L, F, ACCESS
    movf        ram_0x07B, W, BANKED
    addwfc      FSR2H, F, ACCESS
    movff       POSTINC2, ram_0x006
    movff       POSTDEC2, ram_0x007
    movff       ram_0x006, FSR2L
    movff       ram_0x007, FSR2H
    movf        ram_0x090, W, BANKED
    addlw       0xCF
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movff       INDF2, INDF1
    lfsr        FSR2, 0x0002
    movf        ram_0x07A, W, BANKED
    addwf       FSR2L, F, ACCESS
    movf        ram_0x07B, W, BANKED
    addwfc      FSR2H, F, ACCESS
    incf        POSTINC2, F, ACCESS
    movlw       0x00
    addwfc      POSTDEC2, F, ACCESS
    incf        ram_0x090, F, BANKED
    movlw       0x07
    cpfsgt      ram_0x090, BANKED
    bra         flow_main_usb_service_2f4e_2fb6
    call        main_usb_service_42f4, 0x0
    bra         flow_main_usb_service_2f4e_300e
flow_main_usb_service_2f4e_2ffe:
    movf        USTAT, W, ACCESS
    xorlw       0x04
    bnz         flow_main_usb_service_2f4e_300c
    bcf         UIR, 3, ACCESS
    call        main_usb_service_4412, 0x0
    bra         flow_main_usb_service_2f4e_300e
flow_main_usb_service_2f4e_300c:
    bcf         UIR, 3, ACCESS
flow_main_usb_service_2f4e_300e:
    movlb       0x0
    incf        ram_0x0C4, F, BANKED
    movlw       0x03
    cpfsgt      ram_0x0C4, BANKED
    bra         flow_main_usb_service_2f4e_2f78
flow_main_usb_service_2f4e_3018:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_301a
; Address : 0x301A
; Notes   : Inferred core helper routine. Calls: main_core_service_30cc.
; ---------------------------------------------------------------------------
main_core_service_301a:
    movff       ram_0x025, ram_0x029
    movff       ram_0x026, ram_0x02A
    movff       ram_0x027, ram_0x02B
    movff       ram_0x028, ram_0x02C
    movlw       0x18
    bra         flow_main_core_service_301a_3030
flow_main_core_service_301a_302e:
    rcall       main_core_service_30cc
flow_main_core_service_301a_3030:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_301a_302e
    movf        ram_0x029, W, ACCESS
    movwf       ram_0x02E, ACCESS
    tstfsz      ram_0x02E, ACCESS
    bra         flow_main_core_service_301a_3046
flow_main_core_service_301a_303c:
    clrf        ram_0x025, ACCESS
    clrf        ram_0x026, ACCESS
    clrf        ram_0x027, ACCESS
    clrf        ram_0x028, ACCESS
    bra         flow_main_core_service_301a_30ca
flow_main_core_service_301a_3046:
    movff       ram_0x025, ram_0x029
    movff       ram_0x026, ram_0x02A
    movff       ram_0x027, ram_0x02B
    movff       ram_0x028, ram_0x02C
    movlw       0x20
    bra         flow_main_core_service_301a_305c
flow_main_core_service_301a_305a:
    rcall       main_core_service_30cc
flow_main_core_service_301a_305c:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_301a_305a
    movf        ram_0x029, W, ACCESS
    movwf       ram_0x02D, ACCESS
    bsf         ram_0x027, 7, ACCESS
    clrf        ram_0x028, ACCESS
    movlw       0x96
    subwf       ram_0x02E, F, ACCESS
    btfss       ram_0x02E, 7, ACCESS
    bra         flow_main_core_service_301a_308e
    movf        ram_0x02E, W, ACCESS
    xorlw       0x80
    movwf       ram_0x029, ACCESS
    movlw       0xE9
    xorlw       0x80
    subwf       ram_0x029, W, ACCESS
    bnc         flow_main_core_service_301a_303c
flow_main_core_service_301a_307e:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x028, F, ACCESS
    rrcf        ram_0x027, F, ACCESS
    rrcf        ram_0x026, F, ACCESS
    rrcf        ram_0x025, F, ACCESS
    incfsz      ram_0x02E, F, ACCESS
    bra         flow_main_core_service_301a_307e
    bra         flow_main_core_service_301a_30a6
flow_main_core_service_301a_308e:
    movlw       0x1F
    cpfsgt      ram_0x02E, ACCESS
    bra         flow_main_core_service_301a_30a2
    bra         flow_main_core_service_301a_303c
flow_main_core_service_301a_3096:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x025, F, ACCESS
    rlcf        ram_0x026, F, ACCESS
    rlcf        ram_0x027, F, ACCESS
    rlcf        ram_0x028, F, ACCESS
    decf        ram_0x02E, F, ACCESS
flow_main_core_service_301a_30a2:
    tstfsz      ram_0x02E, ACCESS
    bra         flow_main_core_service_301a_3096
flow_main_core_service_301a_30a6:
    movf        ram_0x02D, W, ACCESS
    bz          flow_main_core_service_301a_30ba
    comf        ram_0x028, F, ACCESS
    comf        ram_0x027, F, ACCESS
    comf        ram_0x026, F, ACCESS
    negf        ram_0x025, ACCESS
    movlw       0x00
    addwfc      ram_0x026, F, ACCESS
    addwfc      ram_0x027, F, ACCESS
    addwfc      ram_0x028, F, ACCESS
flow_main_core_service_301a_30ba:
flow_main_core_service_301a_30ca:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_30cc
; Address : 0x30CC
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_30cc:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x02C, F, ACCESS
    rrcf        ram_0x02B, F, ACCESS
    rrcf        ram_0x02A, F, ACCESS
    rrcf        ram_0x029, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_30d8
; Address : 0x30D8
; Notes   : Inferred core helper routine. Calls: main_core_service_3188.
; ---------------------------------------------------------------------------
main_core_service_30d8:
    movf        ram_0x007, W, ACCESS
    bz          flow_main_core_service_30d8_30e6
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    iorwf       ram_0x004, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bnz         flow_main_core_service_30d8_30f4
flow_main_core_service_30d8_30e6:
    clrf        ram_0x003, ACCESS
    clrf        ram_0x004, ACCESS
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    bra         flow_main_core_service_30d8_3186
flow_main_core_service_30d8_30f0:
    incf        ram_0x007, F, ACCESS
    rcall       main_core_service_3188
flow_main_core_service_30d8_30f4:
    clrf        ram_0x009, ACCESS
    clrf        ram_0x00A, ACCESS
    clrf        ram_0x00B, ACCESS
    movlw       0xFE
    andwf       ram_0x006, W, ACCESS
    movwf       ram_0x00C, ACCESS
    movf        ram_0x00C, W, ACCESS
    iorwf       ram_0x009, W, ACCESS
    iorwf       ram_0x00A, W, ACCESS
    iorwf       ram_0x00B, W, ACCESS
    bz          flow_main_core_service_30d8_311a
    bra         flow_main_core_service_30d8_30f0
flow_main_core_service_30d8_310c:
    incf        ram_0x007, F, ACCESS
    incf        ram_0x003, F, ACCESS
    movlw       0x00
    addwfc      ram_0x004, F, ACCESS
    addwfc      ram_0x005, F, ACCESS
    addwfc      ram_0x006, F, ACCESS
    rcall       main_core_service_3188
flow_main_core_service_30d8_311a:
    clrf        ram_0x009, ACCESS
    clrf        ram_0x00A, ACCESS
    clrf        ram_0x00B, ACCESS
    movf        ram_0x006, W, ACCESS
    movwf       ram_0x00C, ACCESS
    movf        ram_0x00C, W, ACCESS
    iorwf       ram_0x009, W, ACCESS
    iorwf       ram_0x00A, W, ACCESS
    iorwf       ram_0x00B, W, ACCESS
    bz          flow_main_core_service_30d8_313c
    bra         flow_main_core_service_30d8_310c
flow_main_core_service_30d8_3130:
    decf        ram_0x007, F, ACCESS
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x003, F, ACCESS
    rlcf        ram_0x004, F, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
flow_main_core_service_30d8_313c:
    btfss       ram_0x005, 7, ACCESS
    bra         flow_main_core_service_30d8_3130
    btfsc       ram_0x007, 0, ACCESS
    bra         flow_main_core_service_30d8_3148
    movlw       0x7F
    andwf       ram_0x005, F, ACCESS
flow_main_core_service_30d8_3148:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x007, F, ACCESS
    movff       ram_0x007, ram_0x009
    clrf        ram_0x00A, ACCESS
    clrf        ram_0x00B, ACCESS
    clrf        ram_0x00C, ACCESS
    movff       ram_0x009, ram_0x00C
    clrf        ram_0x00B, ACCESS
    clrf        ram_0x00A, ACCESS
    clrf        ram_0x009, ACCESS
    movf        ram_0x009, W, ACCESS
    iorwf       ram_0x003, F, ACCESS
    movf        ram_0x00A, W, ACCESS
    iorwf       ram_0x004, F, ACCESS
    movf        ram_0x00B, W, ACCESS
    iorwf       ram_0x005, F, ACCESS
    movf        ram_0x00C, W, ACCESS
    iorwf       ram_0x006, F, ACCESS
    movf        ram_0x008, W, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         ram_0x006, 7, ACCESS
flow_main_core_service_30d8_3186:
    return      0


; ---------------------------------------------------------------------------
; Helper: main_core_service_30d8_with_save          (W04-E01)
;
; Factor of the rcall/call main_core_service_30d8 + 4-movff save tail that
; appeared inline at three sites. Callers bra/goto here to avoid duplicating
; the 18-byte cleanup sequence.
; ---------------------------------------------------------------------------
main_core_service_30d8_with_save:
    rcall       main_core_service_30d8
    movff       ram_0x003, ram_0x00D
    movff       ram_0x004, ram_0x00E
    movff       ram_0x005, ram_0x00F
    movff       ram_0x006, ram_0x010
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3188
; Address : 0x3188
; Notes   : Inferred core helper routine. Calls: main_core_service_496c, main_core_service_4080.
; ---------------------------------------------------------------------------
main_core_service_3188:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    rrcf        ram_0x004, F, ACCESS
    rrcf        ram_0x003, F, ACCESS
    return      0
flow_main_core_service_3188_3194:
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    movwf       ram_0x003, ACCESS
    decf        ram_0x003, W, ACCESS
    bnz         flow_main_core_service_3188_324a
    movf        ram_0x0D3, W, BANKED
    bnz         flow_main_core_service_3188_324a
    movf        ram_0x0D0, W, BANKED
    xorlw       0x06
    bz          flow_main_core_service_3188_31d8
    bra         flow_main_core_service_3188_31e6
flow_main_core_service_3188_31aa:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x3E
    movwf       ram_0x075, BANKED
    clrf        ram_0x0E8, BANKED
    movlw       0x09
    bra         flow_main_core_service_3188_31d4
flow_main_core_service_3188_31bc:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    decf        ram_0x0EB, W, BANKED
    bnz         flow_main_core_service_3188_31cc
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x55
    movwf       ram_0x075, BANKED
flow_main_core_service_3188_31cc:
    decf        ram_0x0EB, W, BANKED
    bnz         flow_main_core_service_3188_31e4
    clrf        ram_0x0E8, BANKED
    movlw       0x1D
flow_main_core_service_3188_31d4:
    movwf       ram_0x0E7, BANKED
    bra         flow_main_core_service_3188_31e4
flow_main_core_service_3188_31d8:
    movf        ram_0x0D2, W, BANKED
    xorlw       0x21
    bz          flow_main_core_service_3188_31aa
    xorlw       0x03
    bz          flow_main_core_service_3188_31bc
    xorlw       0x01
flow_main_core_service_3188_31e4:
    bsf         ram_0x0CE, 1, BANKED
flow_main_core_service_3188_31e6:
    swapf       ram_0x0CF, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    movwf       ram_0x003, ACCESS
    decf        ram_0x003, W, ACCESS
    bnz         flow_main_core_service_3188_324a
    bra         flow_main_core_service_3188_3230
flow_main_core_service_3188_31f4:
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_31fa:
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_3200:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xEA
flow_main_core_service_3188_3208:
    movwf       ram_0x075, BANKED
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x01
    movwf       ram_0x0E7, BANKED
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_3212:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movff       ram_0x0D2, ram_0x0EA
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_321c:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xE9
    bra         flow_main_core_service_3188_3208
flow_main_core_service_3188_3226:
    movlw       0x02
    movwf       ram_0x0C8, BANKED
    movff       ram_0x0D1, ram_0x0E9
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_3230:
    movf        ram_0x0D0, W, BANKED
    xorlw       0x01
    bz          flow_main_core_service_3188_31f4
    xorlw       0x03
    bz          flow_main_core_service_3188_3200
    xorlw       0x01
    bz          flow_main_core_service_3188_321c
    xorlw       0x0A
    bz          flow_main_core_service_3188_31fa
    xorlw       0x03
    bz          flow_main_core_service_3188_3212
    xorlw       0x01
    bz          flow_main_core_service_3188_3226
flow_main_core_service_3188_324a:
    return      0
flow_main_core_service_3188_324c:
    tstfsz      ram_0x0C8, BANKED
    bra         flow_main_core_service_3188_3278
    movlw       0x04
    movlb       0x4
    movwf       ram_0x008, BANKED
    bsf         ram_0x008, 7, BANKED
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlb       0x0
    decf        ram_0x096, W, BANKED
    bnz         flow_main_core_service_3188_326c
    movlw       0x01
    call        main_core_service_4080, 0x0
    clrf        ram_0x096, BANKED
    bra         flow_main_core_service_3188_32f6
flow_main_core_service_3188_326c:
    movlw       0x00
    call        main_core_service_4080, 0x0
    movlw       0x01
    movwf       ram_0x096, BANKED
    bra         flow_main_core_service_3188_32f6
flow_main_core_service_3188_3278:
    btfss       ram_0x0CF, 7, BANKED
    bra         flow_main_core_service_3188_32b4
    movlw       0x01
    movwf       ram_0x0C9, BANKED
    movf        ram_0x0E7, W, BANKED
    subwf       ram_0x0D5, W, BANKED
    movf        ram_0x0E8, W, BANKED
    subwfb      ram_0x0D6, W, BANKED
    bc          flow_main_core_service_3188_3292
    movff       ram_0x0D5, ram_0x0E7
    movff       ram_0x0D6, ram_0x0E8
flow_main_core_service_3188_3292:
    rcall       main_flash_service_35f0
    movlw       0x48
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlw       0x01
    call        main_core_service_4080, 0x0
    movlw       0x00
    call        main_core_service_4080, 0x0
    movlb       0x4
    movlw       0x04
    movwf       ram_0x00B, BANKED
    movlw       0x24
    movwf       ram_0x00A, BANKED
    bra         flow_main_core_service_3188_32f0
flow_main_core_service_3188_32b4:
    movlw       0x02
    movwf       ram_0x0C9, BANKED
    movlw       0x04
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlb       0x0
    movf        ram_0x0D6, W, BANKED
    iorwf       ram_0x0D5, W, BANKED
    bnz         flow_main_core_service_3188_32cc
    movlw       0x48
    movlb       0x1
    movwf       ram_0x016, BANKED
flow_main_core_service_3188_32cc:
    movlb       0x0
    decf        ram_0x096, W, BANKED
    bnz         flow_main_core_service_3188_32dc
    movlw       0x01
    call        main_core_service_4080, 0x0
    clrf        ram_0x096, BANKED
    bra         flow_main_core_service_3188_32e6
flow_main_core_service_3188_32dc:
    movlw       0x00
    call        main_core_service_4080, 0x0
    movlw       0x01
    movwf       ram_0x096, BANKED
flow_main_core_service_3188_32e6:
    movf        ram_0x0D6, W, BANKED
    iorwf       ram_0x0D5, W, BANKED
    bnz         flow_main_core_service_3188_32f6
    movlb       0x4
    clrf        ram_0x009, BANKED
flow_main_core_service_3188_32f0:
    movlw       0x48
    movwf       ram_0x008, BANKED
    bsf         ram_0x008, 7, BANKED
flow_main_core_service_3188_32f6:
    return      0


; ---------------------------------------------------------------------------
; Function: main_i2c_service_32f8
; Address : 0x32F8
; Notes   : Inferred i2c helper routine. Calls: i2c_wait_bus_idle, i2c_secondary_dev_write.
; ---------------------------------------------------------------------------
main_i2c_service_32f8:
    call        i2c_wait_bus_idle, 0x0
    movlw       0x3F
    movwf       ram_0x006, ACCESS
    movlw       0x01
    call        i2c_secondary_dev_write, 0x0
    movlw       0x30
    movwf       ram_0x006, ACCESS
    movlw       0x03
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       ram_0x006, ACCESS
    movlw       0x04
    call        i2c_secondary_dev_write, 0x0
    movlw       0x08
    movwf       ram_0x006, ACCESS
    movlw       0x05
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       ram_0x006, ACCESS
    movlw       0x06
    call        i2c_secondary_dev_write, 0x0
    movlw       0x34
    movwf       ram_0x006, ACCESS
    movlw       0x07
    call        i2c_secondary_dev_write, 0x0
    movlw       0x30
    movwf       ram_0x006, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    movlw       0x08
    movwf       ram_0x006, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x08
    movwf       ram_0x006, ACCESS
    movlw       0x0E
    call        i2c_secondary_dev_write, 0x0
    movlw       0x22
    movwf       ram_0x006, ACCESS
    movlw       0x0F
    call        i2c_secondary_dev_write, 0x0
    clrf        ram_0x006, ACCESS
    movlw       0x10
    call        i2c_secondary_dev_write, 0x0
    clrf        ram_0x006, ACCESS
    movlw       0x11
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       ram_0x006, ACCESS
    movlw       0x1C
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       ram_0x006, ACCESS
    movlw       0x1D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x02
    movwf       ram_0x006, ACCESS
    movlw       0x2D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x20
    movwf       ram_0x006, ACCESS
    movlw       0x2E
    goto        i2c_secondary_dev_write


; ---------------------------------------------------------------------------
; Function: main_core_service_3398
; Address : 0x3398
; Notes   : Inferred core helper routine. Calls: main_flash_service_3ce8, main_core_service_301a, main_core_service_3e0a.
; ---------------------------------------------------------------------------
main_core_service_3398:
    movff       ram_0x02F, ram_0x003
    movff       ram_0x030, ram_0x004
    movff       ram_0x031, ram_0x005
    movff       ram_0x032, ram_0x006
    movlw       0x37
    movwf       ram_0x007, ACCESS
    call        main_flash_service_3ce8, 0x0
    movf        ram_0x038, W, ACCESS
    xorlw       0x80
    movwf       PRODL, ACCESS
    movlw       0x80
    subwf       PRODL, W, ACCESS
    movlw       0x00
    btfsc       STATUS, 2, ACCESS
    subwf       ram_0x037, W, ACCESS
    bc          flow_main_core_service_3398_33cc
    clrf        ram_0x02F, ACCESS
    clrf        ram_0x030, ACCESS
    clrf        ram_0x031, ACCESS
    clrf        ram_0x032, ACCESS
    bra         flow_main_core_service_3398_3430
flow_main_core_service_3398_33cc:
    movlw       0x1D
    subwf       ram_0x037, W, ACCESS
    movlw       0x00
    subwfb      ram_0x038, W, ACCESS
    bnc         flow_main_core_service_3398_33e8
    bra         flow_main_core_service_3398_3430
flow_main_core_service_3398_33e8:
    movff       ram_0x02F, ram_0x025
    movff       ram_0x030, ram_0x026
    movff       ram_0x031, ram_0x027
    movff       ram_0x032, ram_0x028
    rcall       main_core_service_301a
    movff       ram_0x025, ram_0x00D
    movff       ram_0x026, ram_0x00E
    movff       ram_0x027, ram_0x00F
    movff       ram_0x028, ram_0x010
    call        main_core_service_3e0a, 0x0
    movff       ram_0x00D, ram_0x033
    movff       ram_0x00E, ram_0x034
    movff       ram_0x00F, ram_0x035
    movff       ram_0x010, ram_0x036
    movff       ram_0x033, ram_0x02F
    movff       ram_0x034, ram_0x030
    movff       ram_0x035, ram_0x031
    movff       ram_0x036, ram_0x032
flow_main_core_service_3398_3430:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3432
; Address : 0x3432
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3432:
    decf        ram_0x0D1, W, BANKED
    bnz         flow_main_core_service_3432_344c
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    bnz         flow_main_core_service_3432_344c
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D0, W, BANKED
    xorlw       0x03
    bnz         flow_main_core_service_3432_344a
    bsf         ram_0x0CE, 0, BANKED
    bra         flow_main_core_service_3432_344c
flow_main_core_service_3432_344a:
    bcf         ram_0x0CE, 0, BANKED
flow_main_core_service_3432_344c:
    tstfsz      ram_0x0D1, BANKED
    bra         flow_main_core_service_3432_34c6
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    xorlw       0x02
    bnz         flow_main_core_service_3432_34c6
    movf        ram_0x0D3, W, BANKED
    andlw       0x0F
    bz          flow_main_core_service_3432_34c6
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    rcall       core_filter_addr_from_0x0D3        ; W05-E06 factored
    movf        ram_0x0D0, W, BANKED
    xorlw       0x03
    bnz         flow_main_core_service_3432_349c
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x04
    bra         flow_main_core_service_3432_34b8
flow_main_core_service_3432_349c:
    btfss       ram_0x0D3, 7, BANKED
    bra         flow_main_core_service_3432_34ae
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x40
    movwf       INDF2, ACCESS
    bra         flow_main_core_service_3432_34c6
flow_main_core_service_3432_34ae:
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x08
flow_main_core_service_3432_34b8:
    movwf       INDF2, ACCESS
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x00
    bsf         PLUSW2, 7, ACCESS
flow_main_core_service_3432_34c6:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_34c8
; Address : 0x34C8
; Notes   : Inferred core helper routine. Calls: main_adc_service_4124, main_core_service_427a.
; ---------------------------------------------------------------------------
main_core_service_34c8:
    movff       WREG, ram_0x011
    movff       ram_0x00A, ram_0x00E
    movff       ram_0x00B, ram_0x00F
flow_main_core_service_34c8_34d4:
    movff       ram_0x00E, ram_0x003
    movff       ram_0x00F, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        main_adc_service_4124, 0x0
    movff       ram_0x003, ram_0x00E
    movff       ram_0x004, ram_0x00F
    incf        ram_0x011, F, ACCESS
    movf        ram_0x00F, W, ACCESS
    iorwf       ram_0x00E, W, ACCESS
    bnz         flow_main_core_service_34c8_34d4
    movf        ram_0x011, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    clrf        INDF2, ACCESS
    decf        ram_0x011, F, ACCESS
flow_main_core_service_34c8_3504:
    movff       ram_0x00A, ram_0x003
    movff       ram_0x00B, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        main_core_service_427a, 0x0
    movf        ram_0x003, W, ACCESS
    movwf       ram_0x010, ACCESS
    movff       ram_0x00A, ram_0x003
    movff       ram_0x00B, ram_0x004
    movff       ram_0x00C, ram_0x005
    movff       ram_0x00D, ram_0x006
    call        main_adc_service_4124, 0x0
    movff       ram_0x003, ram_0x00A
    movff       ram_0x004, ram_0x00B
    movlw       0x09
    cpfsgt      ram_0x010, ACCESS
    bra         flow_main_core_service_34c8_3542
    movlw       0x07
    addwf       ram_0x010, F, ACCESS
flow_main_core_service_34c8_3542:
    movlw       0x30
    addwf       ram_0x010, F, ACCESS
    movf        ram_0x011, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x010, INDF2
    decf        ram_0x011, F, ACCESS
    movf        ram_0x00B, W, ACCESS
    iorwf       ram_0x00A, W, ACCESS
    bnz         flow_main_core_service_34c8_3504
    incf        ram_0x011, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_i2c_service_355c
; Address : 0x355C
; Notes   : Inferred i2c helper; touches adc,i2c,timer. Calls: eeprom_read_byte, flash_write_with_gie_off, main_flash_service_46de.
; ---------------------------------------------------------------------------
main_i2c_service_355c:
    clrf        INTCON, ACCESS
    clrf        PIE1, ACCESS
    clrf        PIE2, ACCESS
    clrf        PIR1, ACCESS
    clrf        PIR2, ACCESS
    clrf        PORTA, ACCESS
    clrf        PORTB, ACCESS
    clrf        PORTC, ACCESS
    movlw       0x07
    movwf       TRISA, ACCESS
    clrf        TRISB, ACCESS
    movlw       0x87
    movwf       TRISC, ACCESS
    movlw       0x70
    movwf       OSCCON, ACCESS
    movlw       0x38
    movwf       SSPCON1, ACCESS
    movlw       0x01
    movwf       ADCON0, ACCESS
    movlw       0x0C
    movwf       ADCON1, ACCESS
    movlw       0xB5
    movwf       ADCON2, ACCESS
    movlw       0x07
    movwf       T0CON, ACCESS
    movlw       0x80
    movwf       T1CON, ACCESS
    movlw       0x77
    movwf       SSPADD, ACCESS
    movlw       0x01
    movlb       0x0
    movwf       ram_0x0FE, BANKED
    clrf        ram_0x004, ACCESS
    movlw       0xFF
    setf        ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    xorlw       0x77
    bz          flow_main_i2c_service_355c_35bc
    clrf        ram_0x004, ACCESS
    movlw       0xFF
    setf        ram_0x003, ACCESS
    call        eeprom_read_byte, 0x0
    xorlw       0x88
    bz          flow_main_i2c_service_355c_35bc
    movlb       0x0
    clrf        ram_0x0FE, BANKED
flow_main_i2c_service_355c_35bc:
    movlb       0x0
    movf        ram_0x0FE, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        flash_write_with_gie_off, 0x0
    clrf        ram_0x008, ACCESS
    setf        ram_0x007, ACCESS
    movlw       0x02
    movwf       ram_0x009, ACCESS
    call        main_flash_service_46de, 0x0
    bsf         PORTB, 6, ACCESS
    rcall       adaptive_baud_select
    movlw       0x03
    movwf       ram_0x004, ACCESS
    movlw       0xE8
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    call        main_core_service_1e88, 0x0
    bsf         PIE1, 5, ACCESS
    bsf         active_flags, 3, ACCESS
    movlb       0x0
    bsf         event_flags, 7, BANKED      ; V3.1: boot complete — enable bounded PEN waits
    goto        adc_boot_gate


; ---------------------------------------------------------------------------
; Function: main_flash_service_35f0
; Address : 0x35F0
; Notes   : Inferred flash helper; touches flash. Calls: main_flash_service_365c, main_flash_service_3810, main_core_service_3672.
; ---------------------------------------------------------------------------
main_flash_service_35f0:
    movlw       0x08
    movwf       ram_0x08F, BANKED
    subwf       ram_0x0E7, W, BANKED
    movlw       0x00
    subwfb      ram_0x0E8, W, BANKED
    bc          flow_main_flash_service_35f0_3610
    movff       ram_0x0E7, ram_0x08F
    tstfsz      ram_0x0CC, BANKED
    bra         flow_main_flash_service_35f0_3608
    movlw       0x01
    bra         flow_main_flash_service_35f0_360e
flow_main_flash_service_35f0_3608:
    decf        ram_0x0CC, W, BANKED
    bnz         flow_main_flash_service_35f0_3610
    movlw       0x02
flow_main_flash_service_35f0_360e:
    movwf       ram_0x0CC, BANKED
flow_main_flash_service_35f0_3610:
    movff       ram_0x08F, ram_0x409
    movf        ram_0x08F, W, BANKED
    subwf       ram_0x0E7, F, BANKED
    movlw       0x00
    subwfb      ram_0x0E8, F, BANKED
    movlw       0x04
    movlb       0x0
    movwf       ram_0x073, BANKED
    movlw       0x24
    movwf       ram_0x072, BANKED
    btfsc       ram_0x0CE, 1, BANKED
    bra         flow_main_flash_service_35f0_363e
    bra         flow_main_flash_service_35f0_3656
flow_main_flash_service_35f0_362c:
    rcall       main_flash_service_365c
    cpfsgt      TBLPTRH, ACCESS
    bra         flow_main_flash_service_35f0_3638
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         flow_main_flash_service_35f0_363c
flow_main_flash_service_35f0_3638:
    rcall       main_flash_service_3810
flow_main_flash_service_35f0_363c:
    rcall       main_core_service_3672
flow_main_flash_service_35f0_363e:
    tstfsz      ram_0x08F, BANKED
    bra         flow_main_flash_service_35f0_362c
    bra         flow_main_flash_service_35f0_365a
flow_main_flash_service_35f0_3644:
    rcall       main_flash_service_365c
    cpfsgt      TBLPTRH, ACCESS
    bra         flow_main_flash_service_35f0_3650
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         flow_main_flash_service_35f0_3654
flow_main_flash_service_35f0_3650:
    rcall       main_flash_service_3810
flow_main_flash_service_35f0_3654:
    rcall       main_core_service_3672
flow_main_flash_service_35f0_3656:
    tstfsz      ram_0x08F, BANKED
    bra         flow_main_flash_service_35f0_3644
flow_main_flash_service_35f0_365a:
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_365c
; Address : 0x365C
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
main_flash_service_365c:
    movff       ram_0x075, TBLPTRL
    movff       ram_0x076, TBLPTRH
    clrf        TBLPTRU, ACCESS
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movlw       0x07
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3672
; Address : 0x3672
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3672:
    movwf       INDF2, ACCESS
    movlb       0x0
    infsnz      ram_0x072, F, BANKED
    incf        ram_0x073, F, BANKED
    infsnz      ram_0x075, F, BANKED
    incf        ram_0x076, F, BANKED
    decf        ram_0x08F, F, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3682
; Address : 0x3682
; Notes   : Inferred core helper routine. Calls: main_flash_service_3796, main_usb_service_41fe, main_core_service_3710.
; ---------------------------------------------------------------------------
main_core_service_3682:
    swapf       ram_0x0CF, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    bnz         flow_main_core_service_3682_370e
    bra         flow_main_core_service_3682_36e4
flow_main_core_service_3682_368c:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x04
    movwf       ram_0x0CD, BANKED
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_3696:
    rcall       main_flash_service_3796
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_369c:
    call        main_usb_service_41fe, 0x0
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36a2:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    clrf        ram_0x076, BANKED
    movlw       0xEB
    movwf       ram_0x075, BANKED
flow_main_core_service_3682_36ac:
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x01
    movwf       ram_0x0E7, BANKED
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36b4:
    rcall       main_core_service_3710
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36ba:
    rcall       main_core_service_3432
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36c0:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D3, W, BANKED
    addlw       0xEC
    movwf       ram_0x005, ACCESS
    clrf        ram_0x076, BANKED
    movff       ram_0x005, ram_0x075
    bra         flow_main_core_service_3682_36ac
flow_main_core_service_3682_36d2:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D3, W, BANKED
    addlw       0xEC
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x0D1, INDF2
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36e4:
    movf        ram_0x0D0, W, BANKED
    bz          flow_main_core_service_3682_36b4
    xorlw       0x01
    bz          flow_main_core_service_3682_36ba
    xorlw       0x02
    bz          flow_main_core_service_3682_36ba
    xorlw       0x06
    bz          flow_main_core_service_3682_368c
    xorlw       0x03
    bz          flow_main_core_service_3682_3696
    xorlw       0x01
    bz          flow_main_core_service_3682_370e
    xorlw       0x0F
    bz          flow_main_core_service_3682_36a2
    xorlw       0x01
    bz          flow_main_core_service_3682_369c
    xorlw       0x03
    bz          flow_main_core_service_3682_36c0
    xorlw       0x01
    bz          flow_main_core_service_3682_36d2
    xorlw       0x07
flow_main_core_service_3682_370e:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3710
; Address : 0x3710
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3710:
    movlb       0x4
    clrf        ram_0x024, BANKED
    clrf        ram_0x025, BANKED
    bra         flow_main_core_service_3710_3770
flow_main_core_service_3710_3718:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    btfss       ram_0x0CE, 0, BANKED
    bra         flow_main_core_service_3710_3780
    movlb       0x4
    bsf         ram_0x024, 1, BANKED
    bra         flow_main_core_service_3710_3780
flow_main_core_service_3710_3726:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    bra         flow_main_core_service_3710_3780
flow_main_core_service_3710_372c:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    rcall       core_filter_addr_from_0x0D3        ; W05-E06 factored
    movff       ram_0x072, FSR2L
    movff       ram_0x073, FSR2H
    movf        INDF2, W, ACCESS
    movwf       ram_0x003, ACCESS
    btfss       ram_0x003, 2, ACCESS
    bra         flow_main_core_service_3710_3780
    movlw       0x01
    movlb       0x4
    movwf       ram_0x024, BANKED
    bra         flow_main_core_service_3710_3780
; ---------------------------------------------------------------------------
; core_filter_addr_from_0x0D3 (W05-E06 factored helper, 2 sites)
;   Input : ram_0x0D3 (BANKED) — selected filter/slot index (4-bit lo) + bit7
;   Output:
;     ram_0x003:ram_0x004 = base + mul_lo  (main_core_service_3432 site uses
;                                           this as the working filter addr)
;     ram_0x072:ram_0x073 = ram_0x003:004 +/- mul_hi adjustment per bit7
;   Factors an identical 20-instruction block shared by
;     main_core_service_3432 (L4961 in v32) and
;     main_core_service_3710 (L5339 in v32).
;   Uses rcall (within range from both callers).  BSR left unchanged; callers
;   continue to expect BANKED access to bank 0 (ram_0x0D0..ram_0x0D3 live
;   in bank 0).
; ---------------------------------------------------------------------------
core_filter_addr_from_0x0D3:
    movf        ram_0x0D3, W, BANKED
    andlw       0x0F
    mullw       0x08
    movlw       0x04
    movwf       ram_0x003, ACCESS
    movwf       ram_0x004, ACCESS
    movf        PRODL, W, ACCESS
    addwf       ram_0x003, F, ACCESS
    movf        PRODH, W, ACCESS
    addwfc      ram_0x004, F, ACCESS
    movlw       0x01
    btfss       ram_0x0D3, 7, BANKED
    movlw       0x00
    mullw       0x04
    movf        PRODL, W, ACCESS
    addwf       ram_0x003, W, ACCESS
    movwf       ram_0x072, BANKED
    movf        PRODH, W, ACCESS
    addwfc      ram_0x004, W, ACCESS
    movwf       ram_0x073, BANKED
    return      0
flow_main_core_service_3710_3770:
    movlb       0x0
    movf        ram_0x0CF, W, BANKED
    andlw       0x1F
    bz          flow_main_core_service_3710_3718
    xorlw       0x01
    bz          flow_main_core_service_3710_3726
    xorlw       0x03
    bz          flow_main_core_service_3710_372c
flow_main_core_service_3710_3780:
    movlb       0x0
    decf        ram_0x0C8, W, BANKED
    bnz         flow_main_core_service_3710_3794
    movlw       0x04
    movwf       ram_0x076, BANKED
    movlw       0x24
    movwf       ram_0x075, BANKED
    bcf         ram_0x0CE, 1, BANKED
    movlw       0x02
    movwf       ram_0x0E7, BANKED
flow_main_core_service_3710_3794:
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_3796
; Address : 0x3796
; Notes   : Inferred flash helper; touches flash. Calls: main_flash_service_3810.
; ---------------------------------------------------------------------------
main_flash_service_3796:
    movf        ram_0x0CF, W, BANKED
    xorlw       0x80
    bz          flow_main_flash_service_3796_37fe
    bra         flow_main_flash_service_3796_380e
flow_main_flash_service_3796_379e:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x88
    movwf       ram_0x075, BANKED
    movlw       0x12
    bra         flow_main_flash_service_3796_37c4
flow_main_flash_service_3796_37ae:
    tstfsz      ram_0x0D1, BANKED
    bra         flow_main_flash_service_3796_380c
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movlw       0x10
    movwf       ram_0x076, BANKED
    movlw       0x2C
    movwf       ram_0x075, BANKED
    clrf        ram_0x0E8, BANKED
    movlw       0x29
flow_main_flash_service_3796_37c4:
    movwf       ram_0x0E7, BANKED
    bra         flow_main_flash_service_3796_380c
flow_main_flash_service_3796_37c8:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    movf        ram_0x0D1, W, BANKED
    addlw       LOW(string_desc_ptr_table)          ; indexed TBLPTR -> string_desc_ptr_table
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(string_desc_ptr_table)
    movwf       TBLPTRH, ACCESS
    tblrd*+
    movff       TABLAT, ram_0x075
    movwf       ram_0x076, BANKED
    movff       ram_0x075, TBLPTRL
    movff       ram_0x076, TBLPTRH
    clrf        TBLPTRU, ACCESS
    movlw       0x07
    cpfsgt      TBLPTRH, ACCESS
    bra         flow_main_flash_service_3796_37f4
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         flow_main_flash_service_3796_37f6
flow_main_flash_service_3796_37f4:
    rcall       main_flash_service_3810
flow_main_flash_service_3796_37f6:
    movlb       0x0
    movwf       ram_0x0E7, BANKED
    clrf        ram_0x0E8, BANKED
    bra         flow_main_flash_service_3796_380c
flow_main_flash_service_3796_37fe:
    movf        ram_0x0D2, W, BANKED
    xorlw       0x01
    bz          flow_main_flash_service_3796_379e
    xorlw       0x03
    bz          flow_main_flash_service_3796_37ae
    xorlw       0x01
    bz          flow_main_flash_service_3796_37c8
flow_main_flash_service_3796_380c:
    bsf         ram_0x0CE, 1, BANKED
flow_main_flash_service_3796_380e:
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_3810
; Address : 0x3810
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
main_flash_service_3810:
    movff       TBLPTRL, FSR1L
    movff       TBLPTRH, FSR1H
    movf        INDF1, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_i2c_service_381c          (legacy preset table-entry I2C apply)
; Address : 0x381C
; ---------------------------------------------------------------------------
; This is the synchronous, UNBOUNDED preset apply path inherited from V2.x.
; It reads one preset table entry from flash (24 bytes, ram_0x013:014 ->
; flash, count 0x17 to ram_0x02F), then issues a single I2C burst to the
; TAS3108 DSP at write addr 0x68 with up to 24 data bytes.
;
; CRITICAL HAZARDS (V3.2 hardening targets — workstream 1 deferred):
;   • SSPCON2.SEN poll at flow_main_i2c_service_381c_3870 has NO timeout
;     (legacy stock pattern — this is a fixed-iteration pulse on healthy
;     hardware, but a stuck START condition will hang here forever).
;   • SSPCON2.PEN poll at flow_main_i2c_service_381c_389c has NO timeout
;     (same hazard, on STOP).
;   • i2c_byte_tx is V3.1+ bounded inside, but a SEN/PEN hang upstream
;     leaves any half-applied table entry uncommitted.
;
; The V3.2 async path (preset_job_apply_i2c_entry) is a near-clone of this
; routine that wraps the same flash_read + I2C burst pattern with the
; bounded wait_sen/pen_bounded helpers and the
; preset_job_apply_i2c_recover bus-clear/ping path. Field-debugged callers
; (delayed-switch path) MUST use that copy — this stock body is preserved
; only for the few non-preset call sites that have not yet been migrated.
;
; W1 ATTEMPT NOTE (2026-04-17): a bounded-wait + recover wrapper here
; broke test_v32_main_bus_clear_recovers_after_mssp_stop_fault and
; test_v32_main_pen_timeout_recovers in test_v31_v163b_robustness.py.
; Root cause: the recover path returns `0` to the caller, which signals
; "table entry applied" to main_core_service_4574 and cmd_dispatch_gated.
; During a multi-loop fault window the caller advances past entries that
; were never written, losing dirty state. A future M1 needs either
; (a) a return-value contract change so callers honor a "retry" signal,
; or (b) per-call internal retry with a bounded counter. Until then the
; legacy unbounded behavior is the only one that satisfies both
; robustness tests and the V3.2 wire-chain convergence gates.
;
; Called from: main_i2c_service_27f0 (DSP I2C refresh), cmd_dispatch_gated
;              (channel sync), some legacy reconnect/wake paths.
; ---------------------------------------------------------------------------
main_i2c_service_381c:
    movff       ram_0x013, ram_0x003                ; copy 16-bit flash addr (caller staged)
    movff       ram_0x014, ram_0x004
    clrf        ram_0x005, ACCESS                   ; high byte and TBLPTRU = 0
    clrf        ram_0x006, ACCESS
    clrf        ram_0x008, ACCESS
    movlw       0x04                                ; first read: 4-byte header (TAS reg + len)
    movwf       ram_0x007, ACCESS
    rcall       flash_read_fsr2_0017                ; W05-E04: FSR2 dest=0x0017 helper (in rcall reach)
    movff       ram_0x018, ram_0x02F                ; ram_0x02F = TAS reg byte
    movff       ram_0x019, ram_0x031                ; ram_0x031 = byte count
    movlw       0x19                                ; >= 25 -> end-of-table sentinel
    subwf       ram_0x031, W, ACCESS
    bc          flow_main_i2c_service_381c_38a0
    movlw       0x04                                ; advance past header
    addwf       ram_0x013, W, ACCESS
    movwf       ram_0x015, ACCESS
    movlw       0x00
    addwfc      ram_0x014, W, ACCESS
    movwf       ram_0x016, ACCESS
    movff       ram_0x015, ram_0x003
    movff       ram_0x016, ram_0x004
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    movff       ram_0x031, ram_0x007                ; second read = data block
    clrf        ram_0x008, ACCESS
    clrf        ram_0x00A, ACCESS
    movlw       0x17                                ; FSR2 dest = 0x0017 (overlay)
    movwf       ram_0x009, ACCESS
    rcall       flash_read                          ; W02-E07: back in range after W01-R01 compaction
    bsf         SSPCON2, 0, ACCESS                  ; SEN — START
flow_main_i2c_service_381c_3870:
    btfsc       SSPCON2, 0, ACCESS                  ; <-- M1 unbounded SEN poll (W1 deferred)
    bra         flow_main_i2c_service_381c_3870
    movlw       0x68                                ; TAS3108 write address
    rcall       i2c_byte_tx
    movf        ram_0x02F, W, ACCESS                ; reg byte
    rcall       i2c_byte_tx
    clrf        ram_0x030, ACCESS
    bra         flow_main_i2c_service_381c_3894
flow_main_i2c_service_381c_3884:
    movf        ram_0x030, W, ACCESS
    addlw       0x17                                ; data buffer at 0x0017+i
    call        fsr2_page0_read_w, 0x0               ; W04-E03
    rcall       i2c_byte_tx
    incf        ram_0x030, F, ACCESS
flow_main_i2c_service_381c_3894:
    movf        ram_0x031, W, ACCESS
    subwf       ram_0x030, W, ACCESS
    bnc         flow_main_i2c_service_381c_3884
    bsf         SSPCON2, 2, ACCESS                  ; PEN — STOP
flow_main_i2c_service_381c_389c:
    btfsc       SSPCON2, 2, ACCESS                  ; <-- M1 unbounded PEN poll (W1 deferred)
    bra         flow_main_i2c_service_381c_389c
flow_main_i2c_service_381c_38a0:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_38a2
; Address : 0x38A2
; Notes   : Inferred core helper routine. Calls: main_core_service_3398, main_core_service_432e, main_core_service_3f1e.
; ---------------------------------------------------------------------------
main_core_service_38a2:
    movff       ram_0x041, ram_0x039
    movff       ram_0x042, ram_0x03A
    movff       ram_0x043, ram_0x03B
    movff       ram_0x044, ram_0x03C
    movff       ram_0x041, ram_0x02F
    movff       ram_0x042, ram_0x030
    movff       ram_0x043, ram_0x031
    movff       ram_0x044, ram_0x032
    rcall       main_core_service_3398
    movff       ram_0x02F, ram_0x03D
    movff       ram_0x030, ram_0x03E
    movff       ram_0x031, ram_0x03F
    movff       ram_0x032, ram_0x040
    call        main_core_service_432e, 0x0
    movff       ram_0x039, ram_0x045
    movff       ram_0x03A, ram_0x046
    movff       ram_0x03B, ram_0x047
    movff       ram_0x03C, ram_0x048
    movff       ram_0x045, ram_0x02F
    movff       ram_0x046, ram_0x030
    movff       ram_0x047, ram_0x031
    movff       ram_0x048, ram_0x032
    movlw       0x41
    rcall       main_core_service_3f1e
    movff       ram_0x041, ram_0x02F
    movff       ram_0x042, ram_0x030
    movff       ram_0x043, ram_0x031
    movff       ram_0x044, ram_0x032
    rcall       main_core_service_3398
    movff       ram_0x02F, ram_0x041
    movff       ram_0x030, ram_0x042
    movff       ram_0x031, ram_0x043
    movff       ram_0x032, ram_0x044
    return      0

; ---------------------------------------------------------------------------
; Function: adaptive_baud_select           (chain-role strap → UART/oscillator)
; Address : 0x3926
; ---------------------------------------------------------------------------
; Reads PORTC.bit2 (the chain-role strap, see PIN_SEMANTICS RC2) and selects
; the UART baud + oscillator path:
;   PORTC.RC2 = 1 (chain role): SPBRG=0x3F  (62,500 baud), OSCCON.SCS1=1
;                               (slow internal osc), LATB.bit2 high (chain
;                               status indicator).
;   PORTC.RC2 = 0 (master role): SPBRG=0x7F (31,250 baud, the protocol baud),
;                               OSCCON.SCS1=0 (HS osc), LATB.bit2 low.
; Then drives every output low (LATB.{2..7}, LATA.{3..6}), runs
; main_uart_service_4938 to bring up the EUSART, enables GIE/PEIE, clears
; the parser/event/active flag bytes (event_flags, active_flags, ram_0x07F,
; ram_0x0BD, ram_0x0BB, etc.), and pre-seeds the bank-1 register pointer
; cache (ram_0x00F..0x015 = 0x20..0x28) used by the I2C secondary writes.
; This is the post-cold-reset peripheral configuration path; do NOT confuse
; it with hw_standby_shutdown (which performs the inverse OSCCON change).
; ---------------------------------------------------------------------------
adaptive_baud_select:
    btfss       PORTC, 2, ACCESS
    bra         flow_adaptive_baud_select_3936
    bsf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x3F
    movwf       SPBRG, ACCESS
    bsf         OSCCON, 1, ACCESS
    bra         flow_adaptive_baud_select_3940
flow_adaptive_baud_select_3936:
    bcf         LATB, 2, ACCESS
    rcall       uart_baud_31250_prefix
flow_adaptive_baud_select_3940:
    bcf         LATB, 4, ACCESS
    bcf         LATB, 5, ACCESS
    bcf         LATB, 3, ACCESS
    bcf         LATA, 6, ACCESS
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    bcf         LATB, 7, ACCESS
    call        main_uart_service_4938, 0x0
    bsf         INTCON, 7, ACCESS
    bsf         INTCON, 6, ACCESS
    clrf        ram_0x093, BANKED
    movff       ram_0x093, ram_0x0AB
    bcf         INTCON3, 4, ACCESS
    bcf         INTCON3, 1, ACCESS
    bcf         INTCON, 2, ACCESS
    bcf         T0CON, 7, ACCESS
    bcf         INTCON, 5, ACCESS
    clrf        ram_0x0A4, BANKED
    clrf        ram_0x0B0, BANKED
    clrf        ram_0x0B6, BANKED
    clrf        ram_0x0BA, BANKED
    clrf        event_flags, BANKED
    clrf        ram_0x07F, BANKED
    clrf        ram_0x0BD, BANKED
    clrf        active_flags, ACCESS
    clrf        ram_0x0BB, BANKED
    clrf        ram_0x0BC, BANKED
    clrf        ram_0x0A1, BANKED
    clrf        ram_0x088, BANKED
    clrf        ram_0x089, BANKED
    bcf         ADCON0, 1, ACCESS
    clrf        ram_0x094, BANKED
    movlw       0x20
    movlb       0x1
    movwf       ram_0x00F, BANKED
    movlw       0x21
    movwf       ram_0x010, BANKED
    movlw       0x22
    movwf       ram_0x011, BANKED
    movlw       0x23
    movwf       ram_0x012, BANKED
    movlw       0x25
    movwf       ram_0x013, BANKED
    movlw       0x27
    movwf       ram_0x014, BANKED
    movlw       0x28
    movwf       ram_0x015, BANKED
    retlw       0x28


; ---------------------------------------------------------------------------
; Function: main_i2c_service_39a6
; Address : 0x39A6
; Notes   : Inferred i2c helper routine. Calls: main_core_service_2abc, main_core_service_38a2, main_core_service_301a.
; ---------------------------------------------------------------------------
main_i2c_service_39a6:
    clrf        ram_0x016, ACCESS
    clrf        ram_0x017, ACCESS
    clrf        ram_0x018, ACCESS
    movlw       0x4B
    movwf       ram_0x019, ACCESS
    movff       ram_0x049, ram_0x012
    movff       ram_0x04A, ram_0x013
    movff       ram_0x04B, ram_0x014
    movff       ram_0x04C, ram_0x015
    call        main_core_service_2abc, 0x0
    movff       ram_0x012, ram_0x041
    movff       ram_0x013, ram_0x042
    movff       ram_0x014, ram_0x043
    movff       ram_0x015, ram_0x044
    rcall       main_core_service_38a2
    movff       ram_0x041, ram_0x04D
    movff       ram_0x042, ram_0x04E
    movff       ram_0x043, ram_0x04F
    movff       ram_0x044, ram_0x050
    movff       ram_0x04D, ram_0x025
    movff       ram_0x04E, ram_0x026
    movff       ram_0x04F, ram_0x027
    movff       ram_0x050, ram_0x028
    call        main_core_service_301a, 0x0
    movff       ram_0x025, ram_0x051
    movff       ram_0x026, ram_0x052
    movff       ram_0x027, ram_0x053
    movff       ram_0x028, ram_0x054
    movf        ram_0x054, W, ACCESS
    andlw       0x0F
    rcall       i2c_byte_tx
    movf        ram_0x053, W, ACCESS
    rcall       i2c_byte_tx
    movf        ram_0x052, W, ACCESS
    rcall       i2c_byte_tx
    movf        ram_0x051, W, ACCESS
    bra         i2c_byte_tx


; ---------------------------------------------------------------------------
; Function: main_usb_service_3a26          (HID OUT consume / dispatch arbiter)
; Address : 0x3A26
; ---------------------------------------------------------------------------
; Top-of-loop slot in periodic_service_loop. Decides whether the device is
; in "USB attached + active gate open + sense pin reading 1" state and only
; in that state will pull a complete HID OUT report and call
; hid_command_dispatch.
;
; Path summary:
;   • If USB is suspended (UCON.SUSPND=1) OR active gate is closed (no host
;     allowed to drive the device) OR PORTC.bit0 is low (current-loop RX
;     line idle), force CREN=1 (re-prime UART RX) and return without
;     touching USB.
;   • Otherwise inspect ram_0x0C0 (HID-staging "owned by us" flag): if
;     clear, run main_core_service_3c82 to copy the SETUP into the working
;     buffer at 0x015A and then zero the response buffer at bank 1 offsets
;     0x5A..0x99.
;   • If HID-staging is set (a complete OUT report has been latched), call
;     hid_command_dispatch with the opcode in W; on completion, copy 0x40
;     bytes back to bank 1 offset 0x5A as the IN reply via
;     main_core_service_3fd0.
; ---------------------------------------------------------------------------
main_usb_service_3a26:
    movlb       0x0
    movf        ram_0x0CD, W, BANKED
    xorlw       0x06
    btfsc       STATUS, 2, ACCESS
    btfsc       UCON, 1, ACCESS
    bra         flow_main_usb_service_3a26_3a3a
    btfss       active_flags, 3, ACCESS
    bra         flow_main_usb_service_3a26_3a3a
    btfsc       PORTC, 0, ACCESS
    bra         flow_main_usb_service_3a26_3a40
flow_main_usb_service_3a26_3a3a:
    bsf         RCSTA, 4, ACCESS
    bra         flow_main_usb_service_3a26_3aa2
flow_main_usb_service_3a26_3a40:
    tstfsz      ram_0x0C0, BANKED
    bra         flow_main_usb_service_3a26_3a7e
    movlb       0x4
    btfsc       ram_0x00C, 7, BANKED
    bra         flow_main_usb_service_3a26_3aa2
    call        prep_bank1_ram004, 0x0
    movlw       0x1A
    movwf       ram_0x003, ACCESS
    movlw       0x40
    movwf       ram_0x005, ACCESS
    rcall       main_core_service_3c82
    movlw       0x01
    movlb       0x0
    movwf       ram_0x0C0, BANKED
    clrf        ram_0x059, ACCESS
flow_main_usb_service_3a26_3a64:
    movlb       0x1
    movlw       0x5A
    addwf       ram_0x059, W, ACCESS
    call        setup_fsr2_page_1_or_2, 0x0
    clrf        INDF2, ACCESS
    incf        ram_0x059, F, ACCESS
    movlw       0x3F
    cpfsgt      ram_0x059, ACCESS
    bra         flow_main_usb_service_3a26_3a64
    bra         flow_main_usb_service_3a26_3aa2
flow_main_usb_service_3a26_3a7e:
    movlb       0x1
    movf        ram_0x01A, W, BANKED
    call        hid_command_dispatch, 0x0
    movlb       0x4
    btfsc       ram_0x010, 7, BANKED
    bra         flow_main_usb_service_3a26_3aa2
    call        prep_bank1_ram004, 0x0
    movlw       0x5A
    movwf       ram_0x003, ACCESS
    movlw       0x40
    movwf       ram_0x005, ACCESS
    rcall       main_core_service_3fd0
    movlb       0x0
    clrf        ram_0x0C0, BANKED
flow_main_usb_service_3a26_3aa2:
    return      0

; ---------------------------------------------------------------------------
; Function: uart_rx_with_framing           (Intel-HEX framing for FW-update)
; Address : 0x3AA4
; ---------------------------------------------------------------------------
; Synchronous receive loop used during firmware-update mode. Waits for a
; ':' lead-in via the RX ring, then collects an Intel HEX record of the
; declared length, terminated by CR/LF. Used by fw_update_relay (USB-HID →
; UART firmware update relay) so a host can flash both MAINs in a chain.
;
; Note: this path is only entered after the host issues the FW-update HID
; command; it is NOT part of normal runtime serial parsing (which goes
; through main_uart_service_1be6).
; ---------------------------------------------------------------------------
uart_rx_with_framing:
    clrf        ram_0x00E, ACCESS
    clrf        ram_0x00D, ACCESS
    clrf        ram_0x00F, ACCESS
    clrf        ram_0x00B, ACCESS
    movff       ram_0x005, ram_0x003
    movff       ram_0x006, ram_0x004
    call        main_timer_service_477a, 0x0
flow_uart_rx_with_framing_3ab8:
    call        rx_ring_has_data, 0x0

    bz          flow_uart_rx_with_framing_3b06
    movff       ram_0x00F, ram_0x00A
    call        rx_ring_read, 0x0
    movwf       ram_0x00F, ACCESS
    movf        ram_0x00D, W, ACCESS
    bz          flow_uart_rx_with_framing_3ae2
    movf        ram_0x00E, W, ACCESS
    addwf       ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x008, W, ACCESS
    movwf       FSR2H, ACCESS
    movff       ram_0x00F, INDF2
    incf        ram_0x00E, F, ACCESS
    bra         flow_uart_rx_with_framing_3aec
flow_uart_rx_with_framing_3ae2:
    movf        ram_0x00F, W, ACCESS
    xorlw       0x3A
    bnz         flow_uart_rx_with_framing_3aec
    movlw       0x01
    movwf       ram_0x00D, ACCESS
flow_uart_rx_with_framing_3aec:
    clrf        ram_0x00C, ACCESS
    movf        ram_0x00D, W, ACCESS
    bz          flow_uart_rx_with_framing_3b02
    movf        ram_0x00A, W, ACCESS
    xorlw       0x0D
    bnz         flow_uart_rx_with_framing_3b02
    movf        ram_0x00F, W, ACCESS
    xorlw       0x0A
    bnz         flow_uart_rx_with_framing_3b02
    movlw       0x01
    movwf       ram_0x00C, ACCESS
flow_uart_rx_with_framing_3b02:
    movff       ram_0x00C, ram_0x00B
flow_uart_rx_with_framing_3b06:
    call        main_usb_service_490c, 0x0
    bc          flow_uart_rx_with_framing_3b16
    movf        ram_0x009, W, ACCESS
    subwf       ram_0x00E, W, ACCESS
    bc          flow_uart_rx_with_framing_3b16
    movf        ram_0x00B, W, ACCESS
    bz          flow_uart_rx_with_framing_3ab8
flow_uart_rx_with_framing_3b16:
    call        main_timer_service_494c, 0x0
    movf        ram_0x00E, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: main_isr_dispatch              (single high-priority ISR)
; Address : 0x3B1E
; ---------------------------------------------------------------------------
; Reached from the bootloader's IV at 0x0008 -> the FSR2 spill stub at 0x1008.
; FAST=1 was used on the call so STATUS/W/BSR are already shadowed; FSR2L/H
; were spilled into isr_save_fsr2l/h (restored before retfie 1).
;
; Sources serviced (in priority/poll order):
;   1. T0IF  : Timer0 1-second tick — sets event_flags.bit0; clears T0IE/TMR0ON
;              so the main loop must re-arm.
;   2. TMR3IF: Timer3 reload (preset HOLDING countdown clock). Pre-loads
;              0xF830 for ~10 ms tick. Decrements 16-bit ram_0x08C/0x08D;
;              when it reaches zero, disables T3 + PIE2 so HOLDING in
;              preset_job_service sees the zero and advances to APPLY.
;   3. RCIF  : UART RX byte. Stores RCREG into ring at 0x0200+rx_ring_wr,
;              wraps at 0xC0 (192-byte ring). BUG M6: no overflow detection
;              if rx_ring_wr catches up to rx_ring_rd; oldest byte is silently
;              overwritten. The V3.2 hardening plan workstream 2 calls for a
;              full/overflow flag here.
;   4. OERR  : RCSTA.OERR set → full soft-recover: CREN=0, drain RCREG twice,
;              CREN=1, then reset the ring / staged parser bytes so the next
;              byte is consumed as a fresh route byte.
; ---------------------------------------------------------------------------
main_isr_dispatch:
    pop                                              ; discard call-frame return (FAST=1)
    btfss       PIR2, 5, ACCESS                      ; Timer1? (event-out, unused)
    bra         timer0_irq_handler
    bcf         PIR2, 5, ACCESS
    bcf         PIE2, 5, ACCESS
timer0_irq_handler:
    btfss       INTCON, 2, ACCESS                    ; T0IF — Timer0 overflow?
    bra         timer3_irq_handler
    movlb       0x0
    bsf         event_flags, 0, BANKED               ; raise t0_tick for main loop
    bcf         INTCON, 2, ACCESS                    ; clear T0IF
    bcf         INTCON, 5, ACCESS                    ; mask T0IE (re-armed by main loop)
    bcf         T0CON, 7, ACCESS                     ; stop Timer0 (re-armed by main loop)
timer3_irq_handler:
    btfss       PIR2, 1, ACCESS                      ; TMR3IF — preset HOLDING tick?
    bra         uart_rx_irq_enqueue
    bcf         T3CON, 0, ACCESS                     ; pause Timer3 during reload
    movlw       0xF8                                 ; reload 0xF830 → ~10 ms @ Fosc/4
    movwf       TMR3H, ACCESS
    movlw       0x30
    movwf       TMR3L, ACCESS
    bsf         T3CON, 0, ACCESS
    bcf         PIR2, 1, ACCESS                      ; clear TMR3IF
    movlb       0x0
    movf        ram_0x08D, W, BANKED                 ; HOLDING countdown {hi,lo}
    iorwf       ram_0x08C, W, BANKED
    bz          flow_main_isr_dispatch_3b58          ; reached zero -> stop Timer3
    decf        ram_0x08C, F, BANKED                 ; 16-bit countdown decrement
    btfss       STATUS, 0, ACCESS                    ; borrow into hi byte?
    decf        ram_0x08D, F, BANKED
    bra         uart_rx_irq_enqueue
flow_main_isr_dispatch_3b58:
    bcf         T3CON, 0, ACCESS                     ; HOLDING expired: T3 off
    bcf         PIE2, 1, ACCESS                      ; mask Timer3 IE until next job
uart_rx_irq_enqueue:
    btfss       PIR1, 5, ACCESS                      ; RCIF — UART byte arrived?
    bra         flow_main_isr_dispatch_3b8c
    movlb       0x0
    movf        rx_ring_wr, W, BANKED                ; FSR2 = 0x0200 + rx_ring_wr
    call        fsr2_page2_from_W, 0x0               ; W05-E02: FSR2=0x0200|W (movff uses no W)
    movff       RCREG, INDF2                         ; copy RX byte into ring
    incf        rx_ring_wr, F, BANKED
    movlw       0xBF                                 ; ring size = 0xC0 (192 bytes)
    cpfsgt      rx_ring_wr, BANKED                   ; wr > 0xBF -> wrap
    bra         uart_oerr_recover
    clrf        rx_ring_wr, BANKED                   ; wrap to 0
uart_oerr_recover:
    btfss       RCSTA, 1, ACCESS                     ; OERR? (RX overrun)
    bra         flow_main_isr_dispatch_3b8c
    call        uart_soft_recover_full, 0x0
flow_main_isr_dispatch_3b8c:
    movff       isr_save_fsr2h, FSR2H                ; restore FSR2 spilled at vector entry
    movff       isr_save_fsr2l, FSR2L
    retfie      1                                    ; FAST=1: pop shadow STATUS/W/BSR

; ---------------------------------------------------------------------------
; Function: send_status_burst              (CONTROL status burst — cmd 0x04)
; Address : 0x3B96
; ---------------------------------------------------------------------------
; Emits five BF/<cmd>/<data> frames in fixed order:
;   BF/05/<ram_0x05F>           cmd=0x05 status byte (raw)
;   BF/07/<computed_volume+0x60> cmd=0x07 current volume (with 0x60 offset)
;   BF/03/<active_gate>         cmd=0x03 current standby state (1=active)
;   BF/06/<input_select>        cmd=0x06 current input
;   BF/1D/<ram_0x0B8>           cmd=0x1D current shared setup/timeout byte
;
; Each frame is 3 bytes; preamble emits the 0xBF prefix and cmd byte through
; uart_tx_byte_blocking (V3.1: bounded TRMT wait), and postamble emits the
; data byte then runs main_core_service_492e to insert a Timer3 1 ms inter-
; frame delay so the receiver's 3-byte parser does not re-sync.
;
; Cross-ref: docs/analysis/SEMANTIC_FUNCTION_MAP.md — note that BF/29 is sent
; separately by report_cmd29_status, NOT here.
; ---------------------------------------------------------------------------
send_status_burst:
    movlw       0x05
    rcall       send_status_burst_preamble
    movf        ram_0x05F, W, ACCESS
    rcall       send_status_burst_postamble
    movlw       0x07
    rcall       send_status_burst_preamble
    movlb       0x0
    movf        computed_volume, W, BANKED
    addlw       0x60
    rcall       send_status_burst_postamble
    movlw       0x03
    rcall       send_status_burst_preamble
    movlw       0x01
    btfss       active_flags, 3, ACCESS
    movlw       0x00
    rcall       send_status_burst_postamble
    movlw       0x06
    rcall       send_status_burst_preamble
    movlb       0x0
    movf        input_select, W, BANKED
    rcall       send_status_burst_postamble
    movlw       0x1D
    rcall       send_status_burst_preamble
    movlb       0x0
    movf        ram_0x0B8, W, BANKED
    goto        uart_tx_byte_blocking

send_status_burst_preamble:
    movwf       ram_0x00D, ACCESS
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movf        ram_0x00D, W, ACCESS
    goto        uart_tx_byte_blocking

send_status_burst_postamble:
    call        uart_tx_byte_blocking, 0x0
    goto        main_core_service_492e


; ---------------------------------------------------------------------------
; Helper: uart_baud_31250_prefix (W04-E05 size-opt helper)
; SPBRG/SPBRGH program for 31,250 baud on the 8 MHz INTOSC post-prescaler,
; then drop OSCCON bit 1 (select low-power oscillator group for the UART
; pre-timer gate).  Shared prefix of the wake / adaptive-baud / standby-
; shutdown paths.
; ---------------------------------------------------------------------------
uart_baud_31250_prefix:
    clrf        SPBRGH, ACCESS
    movlw       0x7F
    movwf       SPBRG, ACCESS
    bcf         OSCCON, 1, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: hw_standby_shutdown            (full hardware standby sequence)
; Address : 0x3C0C
; ---------------------------------------------------------------------------
; Reached from standby_event_dispatch when active_flags.bit3 has been cleared
; by a cmd=0x03 standby broadcast (or USB-driven path). Performs, in order:
;   1. Three I2C writes to secondary device 0x71 (regs 0x1B/0x1C/0x1D=0):
;      drops audio rails / clears amp enable. These use function_093 not the
;      DSP path, so a DSP I2C glitch CANNOT mask the standby (the V1.62b
;      "PBs don't power down" field bug was caused by these writes failing).
;   2. Branches on PORTC.bit2 (chain-role strap) to set the OSCCON.SCS1
;      bit, SPBRG (baud) and chain LATB.bit2 indicator into the role-correct
;      low-power oscillator setting.
;   3. Drops LATB.bit4, LATA.bit6, RA3/RA4/RA5 (relay/source select bits).
;   4. Compares ram_0x088:089 against 0x0228 (rail trip threshold). If still
;      above threshold, runs a 4-iteration toggle loop that pulses the 0x1C
;      register on the secondary device with a 250 ms timer3 delay between
;      pulses (this is the controlled rail discharge to suppress pop).
;   5. Drops LATB.bit3, stops Timer0 (T0CON.bit7=0), masks T0IE, then tail
;      calls usb_shutdown which clears UCON and sets usb_reinit_pending=1.
; The active_gate stays cleared — wake comes from a B0/03/01 frame being
; received while standby_event_dispatch's adc_boot_gate path runs after the
; AN0 rail comes back up.
; ---------------------------------------------------------------------------
hw_standby_shutdown:
    clrf        ram_0x006, ACCESS
    movlw       0x1B
    call        i2c_secondary_dev_write, 0x0
    clrf        ram_0x006, ACCESS
    movlw       0x1C
    call        i2c_secondary_dev_write, 0x0
    clrf        ram_0x006, ACCESS
    movlw       0x1D
    call        i2c_secondary_dev_write, 0x0
    btfss       PORTC, 2, ACCESS
    bra         flow_hw_standby_shutdown_3c34
    bsf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x3F
    movwf       SPBRG, ACCESS
    bsf         OSCCON, 1, ACCESS
    bra         flow_hw_standby_shutdown_3c3e
flow_hw_standby_shutdown_3c34:
    bcf         LATB, 2, ACCESS
    rcall       uart_baud_31250_prefix
flow_hw_standby_shutdown_3c3e:
    bcf         LATB, 4, ACCESS
    bcf         LATA, 6, ACCESS
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    movlw       0x28
    movlb       0x0
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    bc          flow_hw_standby_shutdown_3c78
    clrf        ram_0x008, ACCESS
    clrf        ram_0x009, ACCESS
flow_hw_standby_shutdown_3c58:
    movff       ram_0x008, ram_0x006
    movlw       0x1C
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    xorwf       ram_0x008, F, ACCESS
    movlw       0xFA
    call        timer3_blocking_delay_ms_W, 0x0 ; W04-E08 factored (250 ms pulse)
    incf        ram_0x009, F, ACCESS
    movlw       0x04
    cpfsgt      ram_0x009, ACCESS
    bra         flow_hw_standby_shutdown_3c58
flow_hw_standby_shutdown_3c78:
    bcf         LATB, 3, ACCESS
    bcf         T0CON, 7, ACCESS
    bcf         INTCON, 5, ACCESS
    goto        usb_shutdown


; ---------------------------------------------------------------------------
; Function: main_core_service_3c82
; Address : 0x3C82
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3c82:
    movlb       0x0
    clrf        ram_0x0CA, BANKED
    movlb       0x4
    btfsc       ram_0x00C, 7, BANKED
    bra         flow_main_core_service_3c82_3ce6
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x00D, W, BANKED
    btfss       STATUS, 0, ACCESS
    movff       ram_0x40D, ram_0x005
    movlb       0x0
    clrf        ram_0x0CA, BANKED
    bra         flow_main_core_service_3c82_3cbc
flow_main_core_service_3c82_3c9c:
    movlw       0x2C
    movlb       0x0
    addwf       ram_0x0CA, W, BANKED
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x04
    addwfc      FSR2H, F, ACCESS
    movf        ram_0x0CA, W, BANKED
    addwf       ram_0x003, W, ACCESS
    movwf       FSR1L, ACCESS
    movlw       0x00
    addwfc      ram_0x004, W, ACCESS
    movwf       FSR1H, ACCESS
    movff       INDF2, INDF1
    incf        ram_0x0CA, F, BANKED
flow_main_core_service_3c82_3cbc:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x0CA, W, BANKED
    bnc         flow_main_core_service_3c82_3c9c
    movlw       0x40
    movlb       0x4
    movwf       ram_0x00D, BANKED
    andwf       ram_0x00C, F, BANKED
    movlw       0x01
    btfsc       ram_0x00C, 6, BANKED
    movlw       0x00
    movwf       ram_0x006, ACCESS
    swapf       ram_0x006, F, ACCESS
    rlncf       ram_0x006, F, ACCESS
    rlncf       ram_0x006, F, ACCESS
    movf        ram_0x00C, W, BANKED
    xorwf       ram_0x006, W, ACCESS
    andlw       0xBF
    xorwf       ram_0x006, W, ACCESS
    movwf       ram_0x00C, BANKED
    bsf         ram_0x00C, 3, BANKED
    bsf         ram_0x00C, 7, BANKED
flow_main_core_service_3c82_3ce6:
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_3ce8        (cold init / RAM zero / boot trampoline)
; Address : 0x3CE8
; ---------------------------------------------------------------------------
; Two distinct entry points share the address window:
;
;   main_flash_service_3ce8 (helper):
;     Filter on a 4-byte signature loaded by the caller via FSR2 starting at
;     RAM 0x0003. If all four bytes are zero, write a zero pair into RAM at
;     ram_0x007 and return. Otherwise unpack ram_0x005/0x006 into a
;     {ram_0x009,0x00A} 16-bit word, OR a status bit (ram_0x005.bit7) into
;     it, then add 0xFF82 (i.e. -0x7E) to commit the result back to FSR2.
;     This is the tiny helper used during EEPROM/flash signature checks
;     (called from the firmware-update path).
;
;   flow_main_flash_service_3ce8_3d4e (cold-boot entry — actual reset target):
;     The branch target stored at 0x1014 jumps here. It clears all of
;     {0x0300, 0x0200, 0x0100, 0x0060} RAM blocks (the entire usable RAM
;     bank set), then continues into peripheral init: TBLPTR seeded for
;     inline_data_table_47E6 (the FW-update string), TRISA/B/C set per
;     PIN_SEMANTICS.md (TRISA=0x07, TRISB=0x00, TRISC=0x87), ADCON0/1
;     configured (AN0 analog), MSSP and EUSART (31,250 baud) brought up,
;     then drops into main_processing_loop.
; ---------------------------------------------------------------------------
main_flash_service_3ce8:
    lfsr        FSR2, 0x0003
    movf        POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    bnz         flow_main_flash_service_3ce8_3d04
    movf        ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    movwf       POSTINC2, ACCESS
    movwf       POSTDEC2, ACCESS
    bra         flow_main_flash_service_3ce8_3d4c
flow_main_flash_service_3ce8_3d04:
    movf        ram_0x006, W, ACCESS
    andlw       0x7F
    movwf       ram_0x008, ACCESS
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x008, W, ACCESS
    movwf       ram_0x009, ACCESS
    clrf        ram_0x00A, ACCESS
    rlcf        ram_0x00A, F, ACCESS
    movf        ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x009, POSTINC2
    movff       ram_0x00A, POSTDEC2
    movf        ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    btfss       ram_0x005, 7, ACCESS
    movlw       0x00
    iorwf       POSTINC2, F, ACCESS
    movlw       0x00
    iorwf       POSTDEC2, F, ACCESS
    movf        ram_0x007, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x82
    addwf       POSTINC2, F, ACCESS
    movlw       0xFF
    addwfc      POSTDEC2, F, ACCESS
    movf        ram_0x006, W, ACCESS
    andlw       0x80
    iorlw       0x3F
    movwf       ram_0x006, ACCESS
    bcf         ram_0x005, 7, ACCESS
flow_main_flash_service_3ce8_3d4c:
    return      0
flow_main_flash_service_3ce8_3d4e:
    lfsr        FSR0, 0x0300
    movlw       0xC0
flow_main_flash_service_3ce8_3d54:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         flow_main_flash_service_3ce8_3d54
    lfsr        FSR0, 0x0200
    movlw       0xDE
flow_main_flash_service_3ce8_3d60:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         flow_main_flash_service_3ce8_3d60
    lfsr        FSR0, 0x0100
    movlw       0xE5
flow_main_flash_service_3ce8_3d6c:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         flow_main_flash_service_3ce8_3d6c
    lfsr        FSR0, 0x0060
    movlw       0x8D
flow_main_flash_service_3ce8_3d78:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         flow_main_flash_service_3ce8_3d78

    ; --- V3.2 Layer 5: unconditional diag block clear at cold init ---
    ; The diag block (0x2E5..0x2EC) is unconditionally zeroed on EVERY
    ; cold-init pass, regardless of reset cause.  This is a deliberate
    ; design change from the original "RCON-gated preserve on software
    ; reset" approach (revised 2026-04-20 per operator request).
    ;
    ; Rationale:
    ;   * The PIC18 `reset` instruction (used by the bootloader to launch
    ;     the new app after FW update) is a SOFTWARE reset.  Software
    ;     reset does NOT clear RCON.POR or RCON.BOR — it preserves them.
    ;     So after FW update, RCON.BOR=1 and the original gate would
    ;     SKIP the clrf, leaving the diag cells holding whatever bytes
    ;     the previous firmware (or factory-fresh undefined RAM) had.
    ;   * Operators flashing a new image expect a CLEAN counter slate,
    ;     not stale-RAM values from a previous session.
    ;   * The "fault evidence survives recovery" feature was theoretical
    ;     — if you really want long-lived fault counters, they belong
    ;     in EEPROM, not RAM.  RAM counters that reset on every reset
    ;     match standard / least-surprising behavior.
    ;   * On real HW, brief power-button presses might not hold long
    ;     enough for BOR to fire (PIC18F2455 BOR has a minimum off-time
    ;     before re-arming).  Without unconditional clear, the operator
    ;     sees stale-RAM-looking counters on every brief power blip.
    ;
    ; The diag block lives in the wipe-protected BANK 2 upper region
    ; (the wipe loops above stop at 0x2DD), so the explicit clrf below
    ; is the ONLY thing that ever zeroes the cells.  The RCON.BOR/POR
    ; arming below is still done so future code that wants reset-cause
    ; classification can read RCON before re-arming.
    movlb       0x02
    clrf        diag_i, BANKED
    clrf        diag_d, BANKED
    clrf        diag_s, BANKED
    clrf        diag_b, BANKED
    clrf        diag_r, BANKED
    clrf        diag_a, BANKED
    clrf        diag_p, BANKED
    clrf        diag_ra1_prev, BANKED

    ; --- V3.2 rev 0x37 Tier-1: zero reset-cause flag cells too ---
    ; Cold-init zeroes all four flags before classification picks one
    ; (V32_DIAG_TIER1_SPEC.md §"RAM layout").  The classification cascade
    ; below then writes 1 to whichever flag matches the cleared RCON bit.
    clrf        diag_reset_por, BANKED
    clrf        diag_reset_bor, BANKED
    clrf        diag_reset_wdt, BANKED
    clrf        diag_reset_sw, BANKED

    ; --- V3.2 rev 0x37 Tier-1: reset-cause classification cascade ---
    ; Silicon clears the corresponding RCON bit on each reset cause
    ; (PIC18F2455 datasheet 39632e §4.4 + V32_DIAG_TIER1_SPEC.md
    ; §"Reset-cause classification").  Read RCON BEFORE the re-arm
    ; bsfs below so classification sees the as-reported state.
    ;
    ;   RCON.POR (bit 1) clear -> POR fired
    ;   RCON.BOR (bit 0) clear -> BOR fired (with POR still set)
    ;   RCON.TO  (bit 3) clear -> WDT timeout fired
    ;   RCON.RI  (bit 4) clear -> software reset (`reset` instruction) fired
    ;   else                    -> map to SW bucket (MCLR is physically
    ;                              disabled on this hardware via
    ;                              _CONFIG3H = 0x00, so this is the
    ;                              catch-all for glitches / unexpected
    ;                              corner cases)
    ; Hoist W = 0x01 once; each classify branch just stores W to its
    ; cell and falls through to the rearm block.  Catch-all (no
    ; recognized cause cleared) lands on diag_classify_sw — same
    ; outcome as the explicit btfss-RI miss path, which keeps MCLR
    ; (physically disabled by _CONFIG3H = 0x00) folded into the SW
    ; bucket as documented in the spec.
    movlw       0x01
    btfss       RCON, 1, ACCESS                    ; POR cleared?
    bra         diag_classify_por
    btfss       RCON, 0, ACCESS                    ; BOR cleared?
    bra         diag_classify_bor
    btfss       RCON, 3, ACCESS                    ; TO  cleared (WDT)?
    bra         diag_classify_wdt
    ; RI cleared OR no recognized bit cleared -> SW bucket (catch-all).
diag_classify_sw:
    movwf       diag_reset_sw, BANKED
    bra         diag_rcon_rearm
diag_classify_por:
    movwf       diag_reset_por, BANKED
    bra         diag_rcon_rearm
diag_classify_bor:
    movwf       diag_reset_bor, BANKED
    bra         diag_rcon_rearm
diag_classify_wdt:
    movwf       diag_reset_wdt, BANKED
    ; fall through
diag_rcon_rearm:
    bsf         RCON, 0, ACCESS                    ; arm BOR detection for next reset
    bsf         RCON, 1, ACCESS                    ; arm POR detection for next reset
    bsf         RCON, 3, ACCESS                    ; arm TO  (WDT)  for next reset
    bsf         RCON, 4, ACCESS                    ; arm RI  (SW)   for next reset

    clrf        ram_0x05F, ACCESS
    clrf        active_flags, ACCESS
    movlw       LOW(inline_data_table_47E6)         ; TBLPTR -> inline_data_table_47E6
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(inline_data_table_47E6)
    movwf       TBLPTRH, ACCESS
    movlw       UPPER(inline_data_table_47E6)
    movwf       TBLPTRU, ACCESS
    lfsr        FSR0, 0x01E5
    lfsr        FSR1, 0x0016
flow_main_flash_service_3ce8_3d96:
    tblrd*+
    movff       TABLAT, POSTINC0
    movf        POSTDEC1, W, ACCESS
    movf        FSR1L, W, ACCESS
    bnz         flow_main_flash_service_3ce8_3d96
    movlw       UPPER(0x0000)                       ; clear TBLPTRU to program space
    movwf       TBLPTRU, ACCESS
    movlb       0x0
    goto        flow_i2c_wait_bus_idle_48c6

; ---------------------------------------------------------------------------
; Function: flash_erase                    (64-byte block erase w/ A/B remap)
; Address : 0x3DAC
; ---------------------------------------------------------------------------
; Erases program memory in 64-byte blocks from start ram_0x003:006 to end
; ram_0x007:00A (inclusive). EECON1 EEPGD=1, CFGS=0, FREE=1, WREN=1 with
; the standard PIC18 unlock sequence handed off to main_flash_service_4406.
; INTCON.GIE state is preserved across each unlock.
;
; A/B remap prologue mirrors flash_write/flash_read: when active_flags.bit2
; (preset B) is set AND a start/end address falls in 0x56xx-0x5FFF (the
; preset A table window), the corresponding TBLPTRH (ram_0x004 / ram_0x008)
; is pulled down by 0x0A so the erase lands in 0x4Cxx-0x55FF (preset B
; table). Both endpoints are checked independently so cross-window erases
; keep block alignment.
; ---------------------------------------------------------------------------
flash_erase:
    btfss       active_flags, 2, ACCESS     ; preset B active?
    bra         flash_erase_stock
    ; Remap start address (ram_0x004 = TBLPTRH)
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bnz         flash_erase_remap_end
    movlw       0x56
    subwf       ram_0x004, W, ACCESS
    bnc         flash_erase_remap_end
    movlw       0x60
    subwf       ram_0x004, W, ACCESS
    bc          flash_erase_remap_end
    movlw       0x0A
    subwf       ram_0x004, F, ACCESS
flash_erase_remap_end:
    ; Remap end address (ram_0x008 = end TBLPTRH)
    movf        ram_0x00A, W, ACCESS
    iorwf       ram_0x009, W, ACCESS
    bnz         flash_erase_stock
    movlw       0x56
    subwf       ram_0x008, W, ACCESS
    bnc         flash_erase_stock
    movlw       0x60
    subwf       ram_0x008, W, ACCESS
    bc          flash_erase_stock
    movlw       0x0A
    subwf       ram_0x008, F, ACCESS
flash_erase_stock:
    clrf        ram_0x00B, ACCESS
    movff       ram_0x003, ram_0x00C
    movff       ram_0x004, ram_0x00D
    movff       ram_0x005, ram_0x00E
    movff       ram_0x006, ram_0x00F
    bra         flow_flash_erase_3df4
flow_flash_erase_3dc0:
    movff       ram_0x00E, TBLPTRU
    movff       ram_0x00D, TBLPTRH
    movff       ram_0x00C, TBLPTRL
    bsf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    bsf         EECON1, 4, ACCESS
    btfss       INTCON, 7, ACCESS
    bra         flow_flash_erase_3dde
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       ram_0x00B, ACCESS
flow_flash_erase_3dde:
    rcall       main_flash_service_4406
    movf        ram_0x00B, W, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         INTCON, 7, ACCESS
    movlw       0x40
    addwf       ram_0x00C, F, ACCESS
    movlw       0x00
    addwfc      ram_0x00D, F, ACCESS
    addwfc      ram_0x00E, F, ACCESS
    addwfc      ram_0x00F, F, ACCESS
flow_flash_erase_3df4:
    movf        ram_0x007, W, ACCESS
    subwf       ram_0x00C, W, ACCESS
    movf        ram_0x008, W, ACCESS
    subwfb      ram_0x00D, W, ACCESS
    movf        ram_0x009, W, ACCESS
    subwfb      ram_0x00E, W, ACCESS
    movf        ram_0x00A, W, ACCESS
    subwfb      ram_0x00F, W, ACCESS
    btfsc       STATUS, 0, ACCESS
    return      0
    bra         flow_flash_erase_3dc0


; ---------------------------------------------------------------------------
; Function: main_core_service_3e0a
; Address : 0x3E0A
; Notes   : Inferred core helper routine. Calls: main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_3e0a:
    clrf        ram_0x011, ACCESS
    movf        ram_0x010, W, ACCESS
    xorlw       0x80
    addlw       0x80
    bnz         flow_main_core_service_3e0a_3e24
    movlw       0x00
    subwf       ram_0x00F, W, ACCESS
    bnz         flow_main_core_service_3e0a_3e24
    movlw       0x00
    subwf       ram_0x00E, W, ACCESS
    bnz         flow_main_core_service_3e0a_3e24
    movlw       0x00
    subwf       ram_0x00D, W, ACCESS
flow_main_core_service_3e0a_3e24:
    bc          flow_main_core_service_3e0a_3e3a
    comf        ram_0x010, F, ACCESS
    comf        ram_0x00F, F, ACCESS
    comf        ram_0x00E, F, ACCESS
    negf        ram_0x00D, ACCESS
    movlw       0x00
    addwfc      ram_0x00E, F, ACCESS
    addwfc      ram_0x00F, F, ACCESS
    addwfc      ram_0x010, F, ACCESS
    movlw       0x01
    movwf       ram_0x011, ACCESS
flow_main_core_service_3e0a_3e3a:
    movff       ram_0x00D, ram_0x003
    movff       ram_0x00E, ram_0x004
    movff       ram_0x00F, ram_0x005
    movff       ram_0x010, ram_0x006
    movlw       0x96
    movwf       ram_0x007, ACCESS
    movff       ram_0x011, ram_0x008
    ; W04-E01: factor call+4 movff tail into main_core_service_30d8_with_save
    goto        main_core_service_30d8_with_save

; ---------------------------------------------------------------------------
; Function: i2c_byte_tx                    (single I2C byte transmit, V3.1+)
; Address : 0x3EB8
; ---------------------------------------------------------------------------
; Helper: sspcon1_masked_w
; Reads SSPCON1, masks to the low 4 bits (SSPM mode nibble) via ram_0x004
; scratch, returns result in W. Factored from four in-line copies of the
; stock mode-check preamble inside i2c_byte_tx. ram_0x004 is scratched
; unconditionally at each original call site, so factoring preserves
; semantics. No other registers are touched; BSR/STATUS flags reflect the
; final movf into W (Z set iff masked value == 0, same as the in-line form).
; ---------------------------------------------------------------------------
sspcon1_masked_w:
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Stock contract: caller stages the byte in W, calls; the routine writes
; SSPBUF, checks WCOL, and waits for SSPIF or BF. The stock did NOT check
; ACKSTAT — bug DSP1 — making the entire DSP communication path silently
; tolerate every NACK from the TAS3108.
;
; V3.1 changes (preserve byte-equivalence at every other I2C call site):
;   • The previously-unbounded SSPSTAT.BF poll is replaced by
;     wait_bf_clear_bounded (carries on timeout).
;   • Fix A — ACKSTAT (SSPCON2.bit6) is sampled on every successful master
;     TX and latched into dsp_fault_flags.bit2 with caller's BSR preserved.
;     volume_dsp_write reads that latch to drive its 5-attempt retry.
;
; Calling convention preserved:
;   in : W = byte to send
;   out: SSPSTAT in W if BF wait failed (stock), 0 otherwise
;   touches: ram_0x004 (mode shadow), ram_0x005 (saved_w), ram_0x00E
;            (BSR spill); leaves BSR == caller's value on return.
; ---------------------------------------------------------------------------
i2c_byte_tx:
    movff       WREG, ram_0x005
    movff       ram_0x005, SSPBUF
    btfsc       SSPCON1, 7, ACCESS
    bra         flow_i2c_byte_tx_exit
    rcall       sspcon1_masked_w
    xorlw       0x08
    bz          flow_i2c_byte_tx_master
    rcall       sspcon1_masked_w
    xorlw       0x0B
    bz          flow_i2c_byte_tx_master
    bsf         SSPCON1, 4, ACCESS
flow_i2c_byte_tx_sspif:
    btfss       PIR1, 3, ACCESS
    bra         flow_i2c_byte_tx_sspif
    btfss       SSPSTAT, 2, ACCESS
    movf        SSPSTAT, W, ACCESS
    bra         flow_i2c_byte_tx_exit
flow_i2c_byte_tx_master:
    ; Re-check mode (stock pattern preserved)
    rcall       sspcon1_masked_w
    xorlw       0x08
    bz          flow_i2c_byte_tx_bf
    rcall       sspcon1_masked_w
    xorlw       0x0B
    bnz         flow_i2c_byte_tx_exit
flow_i2c_byte_tx_bf:
    ; V3.1: bounded BF wait (stock was unbounded loop)
    call        wait_bf_clear_bounded, 0x0
    bc          flow_i2c_byte_tx_exit
    call        i2c_wait_bus_idle, 0x0
    ; V3.1 Fix A: ACKSTAT check after successful master TX
    ; Save/restore BSR — callers may have any bank selected and stock
    ; i2c_byte_tx never touched BSR.
    movff       BSR, ram_0x00E              ; save caller's BSR
    movlb       0x0
    btfss       SSPCON2, 6, ACCESS          ; skip if NACK (ACKSTAT=1)
    bra         flow_i2c_byte_tx_was_ack
    bsf         dsp_fault_flags, 2, BANKED  ; latch ACKSTAT fault
    diag_inc_sat diag_i                      ; V3.2 Layer 5: count I2C transport fault
flow_i2c_byte_tx_was_ack:
    movff       ram_0x00E, BSR              ; restore caller's BSR (also undoes any macro BSR clobber)
    movf        SSPCON2, W, ACCESS
flow_i2c_byte_tx_exit:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3ec4
; Address : 0x3EC4
; Notes   : Inferred core helper routine. Calls: main_core_service_2abc.
; ---------------------------------------------------------------------------
main_core_service_3ec4:
    movff       WREG, ram_0x02D
    movf        ram_0x02D, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       POSTINC2, ram_0x012
    movff       POSTINC2, ram_0x013
    movff       POSTINC2, ram_0x014
    movff       POSTINC2, ram_0x015
    movff       ram_0x025, ram_0x016
    movff       ram_0x026, ram_0x017
    movff       ram_0x027, ram_0x018
    movff       ram_0x028, ram_0x019
    call        main_core_service_2abc, 0x0
    movff       ram_0x012, ram_0x029
    movff       ram_0x013, ram_0x02A
    movff       ram_0x014, ram_0x02B
    movff       ram_0x015, ram_0x02C
    movf        ram_0x02D, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x029, POSTINC2
    movff       ram_0x02A, POSTINC2
    movff       ram_0x02B, POSTINC2
    movff       ram_0x02C, POSTDEC2
    decf        FSR2L, F, ACCESS
    decf        FSR2L, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3f1e
; Address : 0x3F1E
; Notes   : Inferred core helper routine. Calls: main_core_service_24c2.
; ---------------------------------------------------------------------------
main_core_service_3f1e:
    movff       WREG, ram_0x037
    movf        ram_0x037, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       POSTINC2, ram_0x020
    movff       POSTINC2, ram_0x021
    movff       POSTINC2, ram_0x022
    movff       POSTINC2, ram_0x023
    movff       ram_0x02F, ram_0x024
    movff       ram_0x030, ram_0x025
    movff       ram_0x031, ram_0x026
    movff       ram_0x032, ram_0x027
    call        main_core_service_24c2, 0x0
    movff       ram_0x020, ram_0x033
    movff       ram_0x021, ram_0x034
    movff       ram_0x022, ram_0x035
    movff       ram_0x023, ram_0x036
    movf        ram_0x037, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       ram_0x033, POSTINC2
    movff       ram_0x034, POSTINC2
    movff       ram_0x035, POSTINC2
    movff       ram_0x036, POSTDEC2
    decf        FSR2L, F, ACCESS
    decf        FSR2L, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: intel_hex_checksum_update      (ASCII hex char -> nibble + accum)
; Address : 0x3F78
; ---------------------------------------------------------------------------
; Caller stages an ASCII hex character in W. Returns the corresponding
; 4-bit value in W (0x00-0x0F), and accumulates it into the running
; checksum at ram_0x004. Handles three ASCII ranges:
;   '0'..'9' (0x30-0x39): subtract 0x30
;   'A'..'F' (0x41-0x46): subtract 0x37
;   'a'..'f' (0x61-0x66): subtract 0x57
; Used by the FW-update path (uart_rx_with_framing) to decode each
; received Intel HEX record while keeping the running checksum.
; ---------------------------------------------------------------------------
intel_hex_checksum_update:
    movff       WREG, ram_0x005
    clrf        ram_0x004, ACCESS
    movlw       0x2F
    cpfsgt      ram_0x005, ACCESS
    bra         flow_intel_hex_checksum_updat_3f90
    movlw       0x3A
    subwf       ram_0x005, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3f90
    movf        ram_0x005, W, ACCESS
    addlw       0xD0
    bra         flow_intel_hex_checksum_updat_3fa0
flow_intel_hex_checksum_updat_3f90:
    movlw       0x40
    cpfsgt      ram_0x005, ACCESS
    bra         flow_intel_hex_checksum_updat_3fa2
    movlw       0x47
    subwf       ram_0x005, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3fa2
    movf        ram_0x005, W, ACCESS
    addlw       0xC9
flow_intel_hex_checksum_updat_3fa0:
    movwf       ram_0x004, ACCESS
flow_intel_hex_checksum_updat_3fa2:
    swapf       ram_0x004, F, ACCESS
    movlw       0xF0
    andwf       ram_0x004, F, ACCESS
    movlw       0x2F
    cpfsgt      ram_0x003, ACCESS
    bra         flow_intel_hex_checksum_updat_3fba
    movlw       0x3A
    subwf       ram_0x003, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3fba
    movf        ram_0x003, W, ACCESS
    addlw       0xD0
    bra         flow_intel_hex_checksum_updat_3fca
flow_intel_hex_checksum_updat_3fba:
    movlw       0x40
    cpfsgt      ram_0x003, ACCESS
    bra         flow_intel_hex_checksum_updat_3fcc
    movlw       0x47
    subwf       ram_0x003, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3fcc
    movf        ram_0x003, W, ACCESS
    addlw       0xC9
flow_intel_hex_checksum_updat_3fca:
    addwf       ram_0x004, F, ACCESS
flow_intel_hex_checksum_updat_3fcc:
    movf        ram_0x004, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3fd0
; Address : 0x3FD0
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3fd0:
    movlw       0x40
    cpfsgt      ram_0x005, ACCESS
    bra         flow_main_core_service_3fd0_3fd8
    movwf       ram_0x005, ACCESS
flow_main_core_service_3fd0_3fd8:
    clrf        ram_0x007, ACCESS
    bra         flow_main_core_service_3fd0_3ffa
flow_main_core_service_3fd0_3fdc:
    movf        ram_0x007, W, ACCESS
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x004, W, ACCESS
    movwf       FSR2H, ACCESS
    movlw       0x6C
    addwf       ram_0x007, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x04
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    incf        ram_0x007, F, ACCESS
flow_main_core_service_3fd0_3ffa:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x007, W, ACCESS
    bnc         flow_main_core_service_3fd0_3fdc
    movff       ram_0x005, ram_0x411
    movlw       0x40
    movlb       0x4
    andwf       ram_0x010, F, BANKED
    movlw       0x01
    btfsc       ram_0x010, 6, BANKED
    movlw       0x00
    movwf       ram_0x006, ACCESS
    swapf       ram_0x006, F, ACCESS
    rlncf       ram_0x006, F, ACCESS
    rlncf       ram_0x006, F, ACCESS
    movf        ram_0x010, W, BANKED
    xorwf       ram_0x006, W, ACCESS
    andlw       0xBF
    xorwf       ram_0x006, W, ACCESS
    movwf       ram_0x010, BANKED
    bsf         ram_0x010, 3, BANKED
    bsf         ram_0x010, 7, BANKED
    return      0

; ---------------------------------------------------------------------------
; Function: flash_read                     (program-memory read w/ A/B remap)
; Address : 0x4028
; ---------------------------------------------------------------------------
; Reads ram_0x007:008 bytes from program memory at ram_0x003:006 (24-bit
; addr + zero MSB) into FSR2 = ram_0x009:00A using the TBLRD*+ engine.
; Caller's TBLPTR is preserved (saved/restored via ram_0x00F..0x011).
;
; V3.1+ prologue (preserved from binary patch path): when active_flags.bit2
; (preset B) is set AND target lies in the 0x56xx-0x5FFF window, ram_0x004
; is pre-decremented by 0x0A so the read lands in the alternate preset
; table at 0x4Cxx-0x55FF.  This makes preset_table_a/preset_table_b
; transparent to all callers.
;
; Used by: preset apply (main_i2c_service_381c, preset_job_apply_i2c_entry),
; HID memread, EEPROM-writeback signature paths, flash_erase auto-arm.
; ---------------------------------------------------------------------------

; ---------------------------------------------------------------------------
; Helper: flash_read_fsr2_0017 (W05-E04 size-opt helper)
; Shared preamble used by 3 callers that want FSR2 dest = 0x0017 (RAM
; scratch) for the next flash_read.  Clears the dest-high byte
; (ram_0x00A) and loads 0x17 into dest-low (ram_0x009), then falls
; through to flash_read so the stacked return goes directly back to the
; original caller.  No explicit branch needed -- the helper body is
; immediately above flash_read's entry point.
; ---------------------------------------------------------------------------
flash_read_fsr2_0017:
    clrf        ram_0x00A, ACCESS
    movlw       0x17
    movwf       ram_0x009, ACCESS
    ; fall through into flash_read
flash_read:
    btfss       active_flags, 2, ACCESS     ; preset B active?
    bra         flash_read_stock
    movf        ram_0x006, W, ACCESS        ; check TBLPTRU = 0
    iorwf       ram_0x005, W, ACCESS
    bnz         flash_read_stock
    movlw       0x56
    subwf       ram_0x004, W, ACCESS        ; TBLPTRH >= 0x56?
    bnc         flash_read_stock
    movlw       0x60
    subwf       ram_0x004, W, ACCESS        ; TBLPTRH < 0x60?
    bc          flash_read_stock
    movlw       0x0A
    subwf       ram_0x004, F, ACCESS        ; remap: 0x56->0x4C etc.
flash_read_stock:
    movff       ram_0x003, ram_0x00B
    movff       ram_0x004, ram_0x00C
    movff       ram_0x005, ram_0x00D
    movff       ram_0x006, ram_0x00E
    movff       TBLPTRU, ram_0x011
    movff       TBLPTRH, ram_0x010
    movff       TBLPTRL, ram_0x00F
    movff       ram_0x00D, TBLPTRU
    movff       ram_0x00C, TBLPTRH
    movff       ram_0x00B, TBLPTRL
    bra         flow_flash_read_4064
flow_flash_read_4052:
    tblrd*+
    movff       ram_0x009, FSR2L
    movff       ram_0x00A, FSR2H
    movff       TABLAT, INDF2
    infsnz      ram_0x009, F, ACCESS
    incf        ram_0x00A, F, ACCESS
flow_flash_read_4064:
    decf        ram_0x007, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x008, F, ACCESS
    incf        ram_0x007, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    incf        ram_0x008, W, ACCESS
    bnz         flow_flash_read_4052
    movff       ram_0x011, TBLPTRU
    movff       ram_0x010, TBLPTRH
    movff       ram_0x00F, TBLPTRL
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4080
; Address : 0x4080
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4080:
    movff       WREG, ram_0x003
    movlw       0x08
    movlb       0x1
    movwf       ram_0x017, BANKED
    movlw       0x04
    movwf       ram_0x019, BANKED
    movlw       0x1C
    movwf       ram_0x018, BANKED
    tstfsz      ram_0x003, ACCESS
    bra         flow_main_core_service_4080_40a8
    movlw       0x04
    movwf       ram_0x019, BANKED
    movlw       0x14
    movwf       ram_0x018, BANKED
    movlw       0x04
    movlb       0x0
    movwf       ram_0x079, BANKED
    movlw       0x00
    bra         flow_main_core_service_4080_40ae
flow_main_core_service_4080_40a8:
    movlw       0x04
    movlb       0x0
    movwf       ram_0x079, BANKED
flow_main_core_service_4080_40ae:
    movwf       ram_0x078, BANKED
    movff       ram_0x078, FSR2L
    movff       ram_0x079, FSR2H
    movff       ram_0x116, POSTINC2
    movff       ram_0x117, POSTINC2
    movff       ram_0x118, POSTINC2
    movff       ram_0x119, POSTINC2
    movff       ram_0x078, FSR2L
    movff       ram_0x079, FSR2H
    movlb       0x0
    bsf         INDF2, 7, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_40d6
; Address : 0x40D6
; Notes   : Inferred usb helper; touches usb. Calls: usb_disconnect_handler, main_core_service_4080.
; ---------------------------------------------------------------------------
main_usb_service_40d6:
    movlw       0x03
    movlb       0x0
    movwf       ram_0x0CD, BANKED
    clrf        UEIE, ACCESS
    clrf        UIR, ACCESS
    movlw       0x7B
    movwf       UIE, ACCESS
    clrf        UADDR, ACCESS
    clrf        UEP1, ACCESS
    clrf        UEP2, ACCESS
    clrf        UEP3, ACCESS
    clrf        UEP4, ACCESS
    clrf        UEP5, ACCESS
    clrf        UEP6, ACCESS
    clrf        UEP7, ACCESS
    movlw       0x16
    movwf       UEP0, ACCESS
    bsf         UCON, 6, ACCESS
    bra         flow_main_usb_service_40d6_4102
flow_main_usb_service_40d6_40fc:
    bcf         UIR, 3, ACCESS
    clrwdt
flow_main_usb_service_40d6_4102:
    btfsc       UIR, 3, ACCESS
    bra         flow_main_usb_service_40d6_40fc
    bcf         UCON, 6, ACCESS
    bcf         UCON, 4, ACCESS
    movlw       0x04
    movlb       0x1
    movwf       ram_0x016, BANKED
    movlw       0x00
    rcall       main_core_service_4080
    movlw       0x01
    movwf       ram_0x096, BANKED
    clrf        ram_0x0CE, BANKED
    clrf        ram_0x0EB, BANKED
    movlw       0x00
    goto        main_core_service_48fe


; ---------------------------------------------------------------------------
; Function: main_adc_service_4124
; Address : 0x4124
; Notes   : Inferred adc helper; touches adc.
; ---------------------------------------------------------------------------
main_adc_service_4124:
    clrf        ram_0x007, ACCESS
    clrf        ram_0x008, ACCESS
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bz          flow_main_adc_service_4124_4164
    movlw       0x01
    movwf       ram_0x009, ACCESS
    bra         flow_main_adc_service_4124_413c
flow_main_adc_service_4124_4134:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    incf        ram_0x009, F, ACCESS
flow_main_adc_service_4124_413c:
    btfss       ram_0x006, 7, ACCESS
    bra         flow_main_adc_service_4124_4134
flow_main_adc_service_4124_4140:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x007, F, ACCESS
    rlcf        ram_0x008, F, ACCESS
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, W, ACCESS
    bnc         flow_main_adc_service_4124_415a
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, F, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, F, ACCESS
    bsf         ram_0x007, 0, ACCESS
flow_main_adc_service_4124_415a:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    decfsz      ram_0x009, F, ACCESS
    bra         flow_main_adc_service_4124_4140
flow_main_adc_service_4124_4164:
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    return      0
an0_hysteresis_monitor:
    btfss       active_flags, 3, ACCESS
    bra         flow_main_adc_service_4124_41b4
    movf        ram_0x0A1, W, BANKED
    xorlw       0x64
    bnz         flow_main_adc_service_4124_41b2
    btfsc       ADCON0, 1, ACCESS
    bra         flow_main_adc_service_4124_41ae
    movf        ADRESH, W, ACCESS
    movwf       ram_0x004, ACCESS
    clrf        ram_0x003, ACCESS
    movf        ADRESL, W, ACCESS
    addwf       ram_0x003, W, ACCESS
    movwf       ram_0x088, BANKED
    movlw       0x00
    addwfc      ram_0x004, W, ACCESS
    movwf       ram_0x089, BANKED
    movlw       0x29
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    btfsc       STATUS, 0, ACCESS
    bsf         ram_0x094, 2, BANKED
    bsf         ADCON0, 1, ACCESS
    btfss       ram_0x094, 2, BANKED
    bra         flow_main_adc_service_4124_41ae
    movlw       0x28
    subwf       ram_0x088, W, BANKED
    movlw       0x02
    subwfb      ram_0x089, W, BANKED
    bc          flow_main_adc_service_4124_41ae
    bcf         active_flags, 3, ACCESS
    bsf         event_flags, 2, BANKED
    diag_inc_sat diag_a                              ; V3.2 Layer 5: count AN0-triggered standby
    movlb       0x0                                  ; macro clobbers BSR; restore for the bra below
flow_main_adc_service_4124_41ae:
    clrf        ram_0x0A1, BANKED
    bra         flow_main_adc_service_4124_41b4
flow_main_adc_service_4124_41b2:
    incf        ram_0x0A1, F, BANKED
flow_main_adc_service_4124_41b4:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_41b6
; Address : 0x41B6
; Notes   : Inferred core helper routine. Calls: main_core_service_34c8.
; ---------------------------------------------------------------------------
main_core_service_41b6:
    movff       WREG, ram_0x017
    movff       ram_0x017, ram_0x016
    movf        ram_0x013, W, ACCESS
    xorlw       0x80
    movwf       PRODL, ACCESS
    movlw       0x80
    subwf       PRODL, W, ACCESS
    movlw       0x00
    btfsc       STATUS, 2, ACCESS
    subwf       ram_0x012, W, ACCESS
    bc          flow_main_core_service_41b6_41e4
    movf        ram_0x017, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x2D
    movwf       INDF2, ACCESS
    incf        ram_0x017, F, ACCESS
    negf        ram_0x012, ACCESS
    comf        ram_0x013, F, ACCESS
    btfsc       STATUS, 0, ACCESS
    incf        ram_0x013, F, ACCESS
flow_main_core_service_41b6_41e4:
    movff       ram_0x012, ram_0x00A
    movff       ram_0x013, ram_0x00B
    movff       ram_0x014, ram_0x00C
    movff       ram_0x015, ram_0x00D
    movf        ram_0x017, W, ACCESS
    call        main_core_service_34c8, 0x0
    movf        ram_0x016, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_41fe
; Address : 0x41FE
; Notes   : Inferred usb helper; touches usb. Calls: main_core_service_48fe.
; ---------------------------------------------------------------------------
main_usb_service_41fe:
    movlw       0x01
    movwf       ram_0x0C8, BANKED
    clrf        UEP1, ACCESS
    clrf        UEP2, ACCESS
    clrf        UEP3, ACCESS
    clrf        UEP4, ACCESS
    clrf        UEP5, ACCESS
    clrf        UEP6, ACCESS
    clrf        UEP7, ACCESS
    clrf        ram_0x091, BANKED
flow_main_usb_service_41fe_4212:
    movf        ram_0x091, W, BANKED
    addlw       0xEC
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    clrf        INDF2, ACCESS
    incf        ram_0x091, F, BANKED
    movf        ram_0x091, W, BANKED
    bz          flow_main_usb_service_41fe_4212
    movff       ram_0x0D1, ram_0x0EB
    movf        ram_0x0EB, W, BANKED
    rcall       main_core_service_48fe
    movlb       0x0
    tstfsz      ram_0x0D1, BANKED
    bra         flow_main_usb_service_41fe_4236
    movlw       0x05
    bra         flow_main_usb_service_41fe_4238
flow_main_usb_service_41fe_4236:
    movlw       0x06
flow_main_usb_service_41fe_4238:
    movwf       ram_0x0CD, BANKED
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_secondary_dev_random_read  (1-byte read from device 0x71)
; Address : 0x423C
; ---------------------------------------------------------------------------
; PIC18 master: random read from secondary device (8-bit write addr 0xE2,
; read addr 0xE3 — i.e. 7-bit dev addr 0x71). The secondary is the per-PB
; configuration / amp-control device, NOT the TAS3108.
;
; Sequence: WAIT_IDLE -> START -> 0xE2 -> reg(W) -> RSTART -> 0xE3 ->
;           recv -> NACK -> STOP. Read byte returned in W.
; All START/STOP polls are stock-style (unbounded); callers are not
; reachable on hot/parser paths so the V3.2 hardening plan does not
; require boundification here yet. See workstream 1 for the migration plan.
; ---------------------------------------------------------------------------
i2c_secondary_dev_random_read:
    movff       WREG, ram_0x006
    rcall       i2c_wait_bus_idle
    bsf         SSPCON2, 0, ACCESS
flow_i2c_secondary_dev_random_4246:
    btfsc       SSPCON2, 0, ACCESS
    bra         flow_i2c_secondary_dev_random_4246
    movlw       0xE2
    rcall       i2c_byte_tx
    movf        ram_0x006, W, ACCESS
    rcall       i2c_byte_tx
    bsf         SSPCON2, 1, ACCESS
flow_i2c_secondary_dev_random_4258:
    btfsc       SSPCON2, 1, ACCESS
    bra         flow_i2c_secondary_dev_random_4258
    movlw       0xE3
    rcall       i2c_byte_tx
    rcall       main_i2c_service_464c
    movwf       ram_0x007, ACCESS
    bsf         SSPCON2, 5, ACCESS
    bsf         SSPCON2, 4, ACCESS
flow_i2c_secondary_dev_random_426c:
    btfsc       SSPCON2, 4, ACCESS
    bra         flow_i2c_secondary_dev_random_426c
    bsf         SSPCON2, 2, ACCESS
flow_i2c_secondary_dev_random_4272:
    btfsc       SSPCON2, 2, ACCESS
    bra         flow_i2c_secondary_dev_random_4272
    movf        ram_0x007, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_427a
; Address : 0x427A
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_427a:
    movf        ram_0x006, W, ACCESS
    iorwf       ram_0x005, W, ACCESS
    bz          flow_main_core_service_427a_42ae
    movlw       0x01
    movwf       ram_0x007, ACCESS
    bra         flow_main_core_service_427a_428e
flow_main_core_service_427a_4286:
    bcf         STATUS, 0, ACCESS
    rlcf        ram_0x005, F, ACCESS
    rlcf        ram_0x006, F, ACCESS
    incf        ram_0x007, F, ACCESS
flow_main_core_service_427a_428e:
    btfss       ram_0x006, 7, ACCESS
    bra         flow_main_core_service_427a_4286
flow_main_core_service_427a_4292:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, W, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, W, ACCESS
    bnc         flow_main_core_service_427a_42a4
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x003, F, ACCESS
    movf        ram_0x006, W, ACCESS
    subwfb      ram_0x004, F, ACCESS
flow_main_core_service_427a_42a4:
    bcf         STATUS, 0, ACCESS
    rrcf        ram_0x006, F, ACCESS
    rrcf        ram_0x005, F, ACCESS
    decfsz      ram_0x007, F, ACCESS
    bra         flow_main_core_service_427a_4292
flow_main_core_service_427a_42ae:
    return      0

; ---------------------------------------------------------------------------
; Function: flash_write_with_gie_off       (CONFIG-bit rewrite — boot path)
; Address : 0x42B8
; ---------------------------------------------------------------------------
; Special-purpose flash write that targets the device CONFIG bytes (CFGS=1
; via EECON1=0xC4). Used during firmware-update finalize to commit the new
; CONFIG6H = 0xA0 (bootloader/app boot vector) and CONFIG1L = 0x3A.
;
; Caveat — BUG M7 (flash_write_gie_leak): GIE is intentionally disabled at
; entry, but the routine's RETURN doesn't restore the prior GIE state on
; every path. Callers must arrange to bsf INTCON,GIE themselves on return.
; The wrapper this lives in (firmware-update commit) does the restore;
; future re-use elsewhere has to be careful.
; ---------------------------------------------------------------------------
flash_write_with_gie_off:
    bcf         INTCON, 7, ACCESS
    movlw       UPPER(_CONFIG6H)
    movwf       TBLPTRU, ACCESS
    clrf        TBLPTRH, ACCESS
    movlw       LOW(_CONFIG6H)                      ; TBLPTR -> _CONFIG6H
    movwf       TBLPTRL, ACCESS
    movlw       0xA0
    movwf       TABLAT, ACCESS
    tblwt*
    movlw       0xC4
    movwf       EECON1, ACCESS
    rcall       main_flash_service_4406
flow_flash_write_with_gie_off_42d2:
    btfsc       EECON1, 1, ACCESS
    bra         flow_flash_write_with_gie_off_42d2
    movlw       UPPER(_CONFIG1L)
    movwf       TBLPTRU, ACCESS
    clrf        TBLPTRH, ACCESS
    clrf        TBLPTRL, ACCESS
    movlw       0x3A
    movwf       TABLAT, ACCESS
    tblwt*
    movlw       0xC4
    movwf       EECON1, ACCESS
    rcall       main_flash_service_4406
flow_flash_write_with_gie_off_42ec:
    btfsc       EECON1, 1, ACCESS
    bra         flow_flash_write_with_gie_off_42ec
    bcf         EECON1, 2, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_42f4
; Address : 0x42F4
; Notes   : Inferred usb helper; touches usb. Calls: main_core_service_3682, flow_main_core_service_3188_3194.
; ---------------------------------------------------------------------------
main_usb_service_42f4:
    movlb       0x4
    clrf        ram_0x008, BANKED
    movlb       0x0
    clrf        ram_0x0CC, BANKED
    movlb       0x4
    btfss       ram_0x000, 7, BANKED
    bra         flow_main_usb_service_42f4_4308
    clrf        ram_0x000, BANKED
    movlb       0x0
    clrf        ram_0x096, BANKED
flow_main_usb_service_42f4_4308:
    movlb       0x4
    btfss       ram_0x004, 7, BANKED
    bra         flow_main_usb_service_42f4_4316
    clrf        ram_0x004, BANKED
    movlw       0x01
    movlb       0x0
    movwf       ram_0x096, BANKED
flow_main_usb_service_42f4_4316:
    movlb       0x0
    clrf        ram_0x0C9, BANKED
    clrf        ram_0x0C8, BANKED
    clrf        ram_0x0E7, BANKED
    clrf        ram_0x0E8, BANKED
    bcf         UCON, 4, ACCESS
    call        main_core_service_3682, 0x0
    call        flow_main_core_service_3188_3194, 0x0
    goto        flow_main_core_service_3188_324c


; ---------------------------------------------------------------------------
; Function: main_core_service_432e
; Address : 0x432E
; Notes   : Inferred core helper routine. Calls: main_core_service_24c2.
; ---------------------------------------------------------------------------
main_core_service_432e:
    movlw       0x80
    xorwf       ram_0x040, F, ACCESS
    movff       ram_0x039, ram_0x020
    movff       ram_0x03A, ram_0x021
    movff       ram_0x03B, ram_0x022
    movff       ram_0x03C, ram_0x023
    movff       ram_0x03D, ram_0x024
    movff       ram_0x03E, ram_0x025
    movff       ram_0x03F, ram_0x026
    movff       ram_0x040, ram_0x027
    call        main_core_service_24c2, 0x0
    movff       ram_0x020, ram_0x039
    movff       ram_0x021, ram_0x03A
    movff       ram_0x022, ram_0x03B
    movff       ram_0x023, ram_0x03C
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_tas3108_reg1f_write        (DSP register 0x1F write, V3.1+)
; Address : 0x4368
; ---------------------------------------------------------------------------
; Writes a single byte to TAS3108 register 0x1F (the master-mode / mute
; control register). Used by the standby paths to stage the DSP's mute
; before the rail drops, and by adc_boot_gate during the wake sequence.
;
; Wire format on the bus:
;   START | 0x68 (DSP write) | 0x1F (reg) | 00 | 00 | 00 | <data> | STOP
; The three zero bytes are the upper 3 bytes of the 32-bit register address
; field (TAS3108 register protocol uses 32-bit addr + N bytes data).
;
; V3.1 hardening: SEN/PEN waits go through wait_sen_bounded / wait_pen_bounded
; and short-circuit to i2c_reg1f_done on timeout. i2c_byte_tx (V3.1+) latches
; ACKSTAT in dsp_fault_flags.bit2 — but this routine does not act on it; it
; is the volume_dsp_write path that drives the retry/escalation.
; ---------------------------------------------------------------------------
i2c_tas3108_reg1f_write:
    movff       WREG, ram_0x006
    rcall       i2c_wait_bus_idle
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    rcall       wait_sen_bounded
    bc          i2c_reg1f_done
    movlw       0x68
    rcall       i2c_byte_tx
    movlw       0x1F
    rcall       i2c_byte_tx
    movlw       0x00
    rcall       i2c_byte_tx
    movlw       0x00
    rcall       i2c_byte_tx
    movlw       0x00
    rcall       i2c_byte_tx
    movf        ram_0x006, W, ACCESS
    rcall       i2c_byte_tx
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    rcall       wait_pen_bounded
i2c_reg1f_done:
    return      0


; ---------------------------------------------------------------------------
; Function: main_uart_service_43a2
; Address : 0x43A2
; Notes   : Inferred uart helper routine. Calls: tblrd_lookup, uart_tx_byte_blocking.
; ---------------------------------------------------------------------------
main_uart_service_43a2:
    movff       WREG, ram_0x006
    movff       ram_0x006, ram_0x004
    swapf       ram_0x004, F, ACCESS
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    rcall       tblrd_lookup
    rcall       uart_tx_byte_blocking
    movwf       ram_0x005, ACCESS
    movff       ram_0x006, ram_0x004
    movlw       0x0F
    rcall       tblrd_lookup
    rcall       uart_tx_byte_blocking
    xorwf       ram_0x005, F, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: tblrd_lookup                   (ASCII hex digit lookup)
; Address : 0x43C8
; ---------------------------------------------------------------------------
; Loads ram_0x004 with W (low nibble), then TBLRDs hex_lookup_table[nibble]
; to convert 0..F into ASCII. Twin of nibble_to_hex_ascii (which converts
; ram_0x01B); they exist as two copies because the firmware-update relay
; path needs the conversion in a different scratch register without
; clobbering the main parser's ram_0x01B accumulator.
; ---------------------------------------------------------------------------
tblrd_lookup:
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    call        hex_lookup_table_ptr, 0x0           ; far call: helper lives near nibble_to_hex_ascii
    tblrd*
    movf        TABLAT, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: eeprom_write_blocking          (single-byte EEPROM write, 4 ms)
; Address : 0x43EA
; ---------------------------------------------------------------------------
; Writes one byte: EEADR=ram_0x003, EEDATA=ram_0x005. Drives the standard
; PIC18 EEPROM unlock (0x55, 0xAA, WR) via main_flash_service_4406, then
; spins on EECON1.WR until completion (~4 ms typical).
;
; BUG M3 (eeprom_write_disables_gie): GIE is forcibly cleared at entry and
; restored at exit only if it was set on entry (snapshot in ram_0x006.bit0).
; During the ~4 ms write window the UART RX cannot service interrupts —
; this is the documented cause of OERR latching during EEPROM-heavy paths
; (preset persist, settings save). Mitigation work is in
; docs/V32_MAIN_HANG_HARDENING_PLAN workstream 2.
; ---------------------------------------------------------------------------
eeprom_write_blocking:
    movff       ram_0x003, EEADR
    movff       ram_0x005, EEDATA
    bcf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    movlw       0x00
    btfsc       INTCON, 7, ACCESS
    movlw       0x01
    movwf       ram_0x006, ACCESS
    bcf         INTCON, 7, ACCESS
    rcall       main_flash_service_4406
flow_eeprom_write_blocking_43f4:
    btfsc       EECON1, 1, ACCESS
    bra         flow_eeprom_write_blocking_43f4
    btfsc       ram_0x006, 0, ACCESS
    bra         flow_eeprom_write_blocking_4400
    bcf         INTCON, 7, ACCESS
    bra         flow_eeprom_write_blocking_4402
flow_eeprom_write_blocking_4400:
    bsf         INTCON, 7, ACCESS
flow_eeprom_write_blocking_4402:
    bcf         EECON1, 2, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_4406
; Address : 0x4406
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
main_flash_service_4406:
    movlw       0x55
    movwf       EECON2, ACCESS
    movlw       0xAA
    movwf       EECON2, ACCESS
    bsf         EECON1, 1, ACCESS
    retlw       0xAA


; ---------------------------------------------------------------------------
; Function: main_usb_service_4412
; Address : 0x4412
; Notes   : Inferred usb helper; touches usb. Calls: main_flash_service_35f0.
; ---------------------------------------------------------------------------
main_usb_service_4412:
    movf        ram_0x0CD, W, BANKED
    xorlw       0x04
    bnz         flow_main_usb_service_4412_4426
    movff       ram_0x0D1, UADDR
    movf        UADDR, W, ACCESS
    movlw       0x05
    btfsc       STATUS, 2, ACCESS
    movlw       0x03
    movwf       ram_0x0CD, BANKED
flow_main_usb_service_4412_4426:
    decf        ram_0x0C9, W, BANKED
    bnz         flow_main_usb_service_4412_4446
    call        main_flash_service_35f0, 0x0
    movf        ram_0x0CC, W, BANKED
    xorlw       0x02
    bnz         flow_main_usb_service_4412_443a
    movlw       0x04
    movlb       0x4
    bra         flow_main_usb_service_4412_4442
flow_main_usb_service_4412_443a:
    movlb       0x4
    movlw       0x48
    btfsc       ram_0x008, 6, BANKED
    movlw       0x08
flow_main_usb_service_4412_4442:
    movwf       ram_0x008, BANKED
    bsf         ram_0x008, 7, BANKED
flow_main_usb_service_4412_4446:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4448
; Address : 0x4448
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4448:
    movff       WREG, ram_0x003
    bra         flow_main_core_service_4448_446c
flow_main_core_service_4448_444e:
    movlw       0x01
    movwf       ram_0x0A0, BANKED
    clrf        ram_0x0B9, BANKED
    bra         flow_main_core_service_4448_447c
flow_main_core_service_4448_4456:
    clrf        ram_0x0A0, BANKED
    movlw       0x01
    bra         flow_main_core_service_4448_4468
flow_main_core_service_4448_445c:
    movlw       0x02
    movwf       ram_0x0A0, BANKED
    bra         flow_main_core_service_4448_4468
flow_main_core_service_4448_4462:
    movlw       0x01
    movwf       ram_0x0A0, BANKED
    movlw       0x03
flow_main_core_service_4448_4468:
    movwf       ram_0x0B9, BANKED
    bra         flow_main_core_service_4448_447c
flow_main_core_service_4448_446c:
    movf        ram_0x003, W, ACCESS
    bz          flow_main_core_service_4448_444e
    xorlw       0x01
    bz          flow_main_core_service_4448_4456
    xorlw       0x03
    bz          flow_main_core_service_4448_445c
    xorlw       0x01
    bz          flow_main_core_service_4448_4462
flow_main_core_service_4448_447c:
    return      0

; ---------------------------------------------------------------------------
; Function: timer3_blocking_delay          (busy-wait Timer3 ms delay)
; Address : 0x449E (was 0x447E)
; ---------------------------------------------------------------------------
; Counts ram_0x003:004 timer3 reload-overflow ticks. Each tick is ~1 ms in
; HS-osc mode; ~0.4 ms in low-power mode (OSCCON.SCS1=1).  Reload constants
; differ per oscillator path: 0xFC18 (low-pow) vs 0xF830 (HS).
;
; BUG M5 (timer3_blocking_delay): no caller-visible timeout; if Timer3 IF
; never sets (HW glitch), this hangs. The V3.2 preset job state machine
; intentionally avoids this routine and uses the ISR-driven 16-bit
; ram_0x08C/0x08D countdown for HOLDING — the loop just polls the
; countdown's zero state once per main-loop pass.
;
; Used by hw_standby_shutdown (250 ms pulse loop), adc_boot_gate (settle
; delays), and various fw-update path delays.
; ---------------------------------------------------------------------------
; Helper: timer3_blocking_delay_ms_W (W04-E08)
; Loads the 16-bit timer counter as (ram_0x004=0, ram_0x003=W) and falls
; through into timer3_blocking_delay. Used by wake / cold-boot paths that
; always zero the high byte. Saves 4 B per call site (7 sites factored).
; Reorder is safe: timer3_blocking_delay does not read ram_0x003/ram_0x004
; until after its own setup; the two stores to W-relative scratch bytes do
; not depend on order.
; ---------------------------------------------------------------------------
timer3_blocking_delay_ms_W:
    movwf       ram_0x003, ACCESS
    clrf        ram_0x004, ACCESS
    ; fall through into timer3_blocking_delay
timer3_blocking_delay:
    bcf         PIE2, 1, ACCESS
    movlw       0x98
    movwf       T3CON, ACCESS
    bsf         T3CON, 0, ACCESS
    bra         flow_timer3_blocking_delay_44a8
flow_timer3_blocking_delay_4488:
    btfss       OSCCON, 1, ACCESS
    bra         flow_timer3_blocking_delay_4494
    movlw       0xFC
    movwf       TMR3H, ACCESS
    movlw       0x18
    bra         flow_timer3_blocking_delay_449a
flow_timer3_blocking_delay_4494:
    movlw       0xF8
    movwf       TMR3H, ACCESS
    movlw       0x30
flow_timer3_blocking_delay_449a:
    movwf       TMR3L, ACCESS
    bcf         PIR2, 1, ACCESS
flow_timer3_blocking_delay_449e:
    btfss       PIR2, 1, ACCESS
    bra         flow_timer3_blocking_delay_449e
    decf        ram_0x003, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x004, F, ACCESS
flow_timer3_blocking_delay_44a8:
    movf        ram_0x004, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    bnz         flow_timer3_blocking_delay_4488
    bcf         T3CON, 0, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_uart_service_44b2
; Address : 0x44B2
; Notes   : Inferred uart helper routine. Calls: uart_tx_byte_blocking, uart_tx_block_from_buffer.
; ---------------------------------------------------------------------------
main_uart_service_44b2:
    movff       WREG, ram_0x01B
    movlw       0x0D
    rcall       uart_tx_byte_blocking
    movlw       0x0A
    rcall       uart_tx_byte_blocking
    movlw       0x0C
    rcall       uart_tx_byte_blocking
    movlw       0x3A
    rcall       uart_tx_byte_blocking
    clrf        ram_0x019, ACCESS
    movff       ram_0x01B, ram_0x018
    rcall       uart_tx_block_from_buffer
    movlw       0x0D
    rcall       uart_tx_byte_blocking
    movlw       0x0A
    bra         uart_tx_byte_blocking

; ---------------------------------------------------------------------------
; Helper: clrf_i2c_coeff_0123_and_write        (W03-E02 size-opt helper)
; ---------------------------------------------------------------------------
; Shared factor for the "clear i2c_coeff_0..3 then write a zero coefficient
; block to the DSP" pattern. Clears the 4-byte i2c_coeff_0..i2c_coeff_3 RAM
; block (0x055..0x058, ACCESS) and then FALLS THROUGH into
; i2c_tas3108_coeff_write — the helper is positioned immediately before
; that function so no branch is required on exit.
;
; Callers:
;   - flow_cmd_dispatch entry clear + write  (was 5 inline lines)
;   - flow_cmd_dispatch_gated post-gate write (was 5 inline lines)
;   - mssp_hard_reset post-reset clear + write (was 5 inline lines)
;   - preset_force_mute  (tail-call via `bra`; helper fall-through chains
;                         i2c_tas3108_coeff_write's `return` back to the
;                         caller of preset_force_mute)
;
; BSR/Z/W: helper only executes `clrf` on ACCESS registers and falls
; through; BSR unchanged, STATUS.Z = 1 (last clrf), W unchanged. All four
; callers immediately return/branch without relying on post-pattern flags.
;
; Savings : (sites 1-3) 3 × (12 B -> 4 B) + (site 4) 1 × (12 B -> 2 B)
;           − 8 B helper = 24 + 10 − 8 = 26 B.
; ---------------------------------------------------------------------------
clrf_i2c_coeff_0123_and_write:
    clrf        i2c_coeff_0, ACCESS
    clrf        i2c_coeff_1, ACCESS
    clrf        i2c_coeff_2, ACCESS
    clrf        i2c_coeff_3, ACCESS
    ; fall through into i2c_tas3108_coeff_write

; ---------------------------------------------------------------------------
; Function: i2c_tas3108_coeff_write        (DSP volume coefficient write)
; Address : 0x44E4
; ---------------------------------------------------------------------------
; Writes a 4-byte coefficient block to TAS3108 reg 0x30 (the volume
; coefficient register) from i2c_coeff_0..i2c_coeff_3 (RAM 0x055..0x058).
; Stock wire format:
;   START | 0x68 (DSP write) | 0x30 | i2c_coeff_0..3 | STOP
;
; HARDWARE-VERIFIED REGRESSION NOTE:
;   V3.1 development tried to replace the START/STOP waits with the new
;   wait_sen/pen_bounded helpers (matching i2c_tas3108_reg1f_write). On
;   simulation that path was equivalent and tests passed; on real hardware
;   the bounded poll cadence interacted badly with the TAS3108 internal
;   I2C state machine and DSP coefficient writes silently dropped at
;   long-running soak. The committed V3.1+ path therefore keeps the stock
;   START/STOP busy-waits HERE, while every OTHER MSSP user is bounded.
;
; This is the canonical site that ACKSTAT (set by i2c_byte_tx into
; dsp_fault_flags.bit2 — V3.1 Fix A) is observed and acted on by
; volume_dsp_write's retry/escalation. dsp_fault_flags.bit2 is the only
; signal that lets us distinguish "DSP responding but coefficient ignored"
; (Fix B/B' retries) from the silent NACK pattern that DSP1 originally
; tolerated.
; ---------------------------------------------------------------------------
i2c_tas3108_coeff_write:
    rcall       i2c_wait_bus_idle
    bsf         SSPCON2, 0, ACCESS          ; stock START wait
coeff_write_wait_sen_stock:
    btfsc       SSPCON2, 0, ACCESS
    bra         coeff_write_wait_sen_stock
    movlw       0x68
    rcall       i2c_byte_tx
    movlw       0x30
    rcall       i2c_byte_tx
    movff       i2c_coeff_0, ram_0x049
    movff       i2c_coeff_1, ram_0x04A
    movff       i2c_coeff_2, ram_0x04B
    movff       i2c_coeff_3, ram_0x04C
    call        main_i2c_service_39a6, 0x0
    bsf         SSPCON2, 2, ACCESS          ; stock STOP wait
coeff_write_pen_stock:
    btfss       SSPCON2, 2, ACCESS
    bra         coeff_write_pen_done
    bra         coeff_write_pen_stock
coeff_write_pen_timeout:
coeff_write_pen_done:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4516
; Address : 0x4516
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4516:
    tstfsz      ram_0x05F, ACCESS
    bra         flow_main_core_service_4516_4534
flow_main_core_service_4516_451a:
    bcf         LATA, 3, ACCESS
    bra         flow_main_core_service_4516_4520
flow_main_core_service_4516_451e:
    bsf         LATA, 3, ACCESS
flow_main_core_service_4516_4520:
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    bra         flow_main_core_service_4516_4544
flow_main_core_service_4516_4526:
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bra         flow_main_core_service_4516_4530
flow_main_core_service_4516_452c:
    bcf         LATA, 3, ACCESS
    bsf         LATA, 4, ACCESS
flow_main_core_service_4516_4530:
    bsf         LATA, 5, ACCESS
    bra         flow_main_core_service_4516_4544
flow_main_core_service_4516_4534:
    movf        ram_0x093, W, BANKED
    bz          flow_main_core_service_4516_451a
    xorlw       0x05
    bz          flow_main_core_service_4516_451e
    xorlw       0x03
    bz          flow_main_core_service_4516_4526
    xorlw       0x01
    bz          flow_main_core_service_4516_452c
flow_main_core_service_4516_4544:
    return      0

; ---------------------------------------------------------------------------
; Function: uart_fifo_drain_2              (drain both hardware RX FIFO slots)
; Address : 0x4546
; ---------------------------------------------------------------------------
; PIC18F2455 EUSART RX is 2 deep. CONTROL's reconnect poll is 3 bytes, so a
; wake-time blind window can leave two stale bytes in RCREG plus an OERR latch
; on the third. This helper deliberately performs two reads with no RCIF test
; so OERR/FERR recovery consumes the whole FIFO depth exactly like the hardened
; CONTROL v1.71 path.
; ---------------------------------------------------------------------------
uart_fifo_drain_2:
    movf        RCREG, W, ACCESS
    movf        RCREG, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: uart_quiesce_for_wake          (disable EUSART before wake delays)
; Address : 0x455E
; ---------------------------------------------------------------------------
; Wake holds INTCON.GIE low across ~1.7 s of rail / DSP settle time. If RX
; stays enabled during that window, CONTROL's reconnect polls can overflow the
; 2-byte hardware FIFO before the ISR runs. This helper masks UART IRQs,
; drains any partial frame, disables TX/RX/SPEN, and drops the software parser
; to a known-empty state so wake exits through a full re-init instead of a
; partially wedged link.
; ---------------------------------------------------------------------------
uart_quiesce_for_wake:
    bcf         PIE1, 5, ACCESS
    bcf         PIR1, 5, ACCESS
    bcf         PIE1, 4, ACCESS
    bcf         PIR1, 4, ACCESS
    bcf         RCSTA, 4, ACCESS
    rcall       uart_fifo_drain_2
    bcf         TXSTA, 5, ACCESS
    bcf         RCSTA, 7, ACCESS
    bra         uart_parser_resync


; ---------------------------------------------------------------------------
; Function: uart_soft_recover_full         (OERR FIFO drain + parser reset)
; Address : 0x4570
; ---------------------------------------------------------------------------
; MAIN now matches CONTROL v1.71's OERR recovery contract: clear CREN, drain
; both FIFO slots, re-enable CREN, then reset the staged frame / ring state.
; Falls through into uart_parser_resync (W04-E07 reorder: saves 2 B by
; eliminating the terminal bra).
; ---------------------------------------------------------------------------
uart_soft_recover_full:
    bcf         RCSTA, 4, ACCESS
    rcall       uart_fifo_drain_2
    bsf         RCSTA, 4, ACCESS
    ; fall through to uart_parser_resync


; ---------------------------------------------------------------------------
; Function: uart_parser_resync             (drop staged frame + ring state)
; Address : 0x454C
; ---------------------------------------------------------------------------
; Shared by wake-time UART quiesce, OERR soft-recover, and the cold-boot
; bring-up helper. Clears both software ring indices and the parser staging
; bytes so the next received byte is always interpreted as a fresh route byte,
; and suppresses any pending cmd-XOR ACK echo.
; ---------------------------------------------------------------------------
uart_parser_resync:
    movlb       0x0
    clrf        rx_ring_rd, BANKED
    clrf        rx_ring_wr, BANKED
    clrf        rx_frame_position, BANKED
    clrf        ram_0x0A2, BANKED
    clrf        current_cmd_data, BANKED
    clrf        ram_0x0BC, BANKED
    bcf         active_flags, 0, ACCESS
    bcf         active_flags, 6, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_service_rx_frame_gap      (parser stall watchdog, V3.2)
; ---------------------------------------------------------------------------
; Polled once per `periodic_service_loop` pass, right after
; `main_uart_service_1be6` drains whatever bytes are in the native RX
; ring.  Closes the V32_MAIN_HANG_HARDENING_PLAN §2 "parser must not
; wait forever" gap — previously the 3-byte frame assembler could be
; left staged (route byte received, cmd/data bytes never arrived) and
; the parser would accept an arbitrarily late continuation as part of
; that stale frame.
;
; Semantics:
;   * If `rx_frame_position == 0` (parser idle), clear the timeout and
;     return — nothing to guard against.
;   * If the RX ring still has bytes pending, the parser is about to
;     make progress on the next pass; clear the timeout.
;   * Otherwise the parser is stalled mid-frame.  Increment the
;     timeout; when it wraps 0xFF → 0x00 (~256 periodic_service_loop
;     passes), reset `rx_frame_position` and `active_flags.0` so the
;     next byte is interpreted as a fresh route byte, then clear the
;     timeout.
; ---------------------------------------------------------------------------
main_service_rx_frame_gap:
    movlb       0x0
    movf        rx_frame_position, F, BANKED
    btfsc       STATUS, 2, ACCESS               ; Z = parser idle
    bra         main_rx_frame_gap_idle
    movf        rx_ring_wr, W, BANKED
    cpfseq      rx_ring_rd, BANKED               ; ring has data? parser about to progress
    bra         main_rx_frame_gap_idle
    movlb       0x2
    infsnz      main_rx_frame_gap_timeout, F, BANKED
    bra         main_rx_frame_gap_expired
    return      0
main_rx_frame_gap_expired:
    movlb       0x0
    clrf        rx_frame_position, BANKED
    bcf         active_flags, 0, ACCESS
    ; fall through to idle — clears the timeout after reset
main_rx_frame_gap_idle:
    movlb       0x2
    clrf        main_rx_frame_gap_timeout, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: uart_config                    (EUSART bring-up — 31,250 baud)
; Address : 0x4576
; ---------------------------------------------------------------------------
; Brings up the EUSART for the 31,250-baud current-loop chain protocol:
;   • TXSTA = 0x06  (BRGH=1, asynchronous, 8-bit, TX disabled until later)
;   • RCSTA = 0x80  (SPEN, asynchronous, 8-bit, CREN off until SPBRG set)
;   • BAUDCON = 0x48 (BRG16=1 in bit 3; bit 6 RCIDL is read-only and the
;     write to it is ignored by hardware — the byte's effective payload
;     is just BRG16=1, all other writable bits 0)
;   • TRISC.6/7 inputs (peripheral takes them over)
;   • SPBRGH=0, SPBRG=0x7F. With BRGH=1 + BRG16=1 (16-bit BRG, hi-speed)
;     the formula is Fosc/(4*(SPBRGH:SPBRG + 1)) =
;     16 MHz / (4 * 128) = 31,250 baud — matches stock V2.3 and the
;     wire baud documented in PIN_SEMANTICS.md.
;   • TXEN=1, CREN=1 — TX/RX enabled.
; Also clears rx_ring_rd/wr so the RX ring at 0x0200 starts fresh.
; Returns 0x7F in W (the SPBRG byte) — used by callers that want to
; double-check the configured baud later.
; ---------------------------------------------------------------------------
uart_config:
    bcf         RCSTA, 7, ACCESS
    bcf         RCON, 7, ACCESS
    movlb       0x0
    clrf        rx_ring_rd, BANKED
    clrf        rx_ring_wr, BANKED
    movlw       0x06
    movwf       TXSTA, ACCESS
    movlw       0x80
    movwf       RCSTA, ACCESS
    movlw       0x48
    movwf       BAUDCON, ACCESS
    bsf         TRISC, 7, ACCESS
    bsf         TRISC, 6, ACCESS
    bcf         PIE1, 4, ACCESS
    bcf         PIR1, 4, ACCESS
    bcf         PIR1, 5, ACCESS
    bcf         PIE1, 5, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x7F
    movwf       SPBRG, ACCESS
    bsf         TXSTA, 5, ACCESS
    bsf         RCSTA, 4, ACCESS
    retlw       0x7F


; ---------------------------------------------------------------------------
; Function: main_core_service_4574
; Address : 0x4574
; Notes   : Inferred core helper routine. Calls: main_i2c_service_381c.
; ---------------------------------------------------------------------------
main_core_service_4574:
    movlw       0x56
    movwf       ram_0x033, ACCESS
    clrf        ram_0x032, ACCESS
    clrf        ram_0x034, ACCESS
flow_main_core_service_4574_457e:
    movff       ram_0x032, ram_0x013
    movff       ram_0x033, ram_0x014
    call        main_i2c_service_381c, 0x0
    movlw       0x18
    addwf       ram_0x032, F, ACCESS
    movlw       0x00
    addwfc      ram_0x033, F, ACCESS
    incf        ram_0x034, F, ACCESS
    movlw       0x5F
    cpfsgt      ram_0x034, ACCESS
    bra         flow_main_core_service_4574_457e
    movwf       ram_0x014, ACCESS
    clrf        ram_0x013, ACCESS
    goto        main_i2c_service_381c


; ---------------------------------------------------------------------------
; Function: main_usb_service_45a2
; Address : 0x45A2
; Notes   : Inferred usb helper; touches usb. Calls: main_core_service_2328, main_core_service_3fd0.
; ---------------------------------------------------------------------------
main_usb_service_45a2:
    call        main_core_service_2328, 0x0
    movf        ram_0x0CD, W, BANKED
    xorlw       0x06
    btfsc       STATUS, 2, ACCESS
    btfsc       UCON, 1, ACCESS
    bra         flow_main_usb_service_45a2_45cc
    btfss       PORTC, 0, ACCESS
    bra         flow_main_usb_service_45a2_45cc
    movlb       0x4
    btfsc       ram_0x010, 7, BANKED
    bra         flow_main_usb_service_45a2_45cc
    call        prep_bank1_ram004, 0x0
    movlw       0x5A
    movwf       ram_0x003, ACCESS
    movlw       0x40
    movwf       ram_0x005, ACCESS
    rcall       main_core_service_3fd0
flow_main_usb_service_45a2_45cc:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_45ce
; Address : 0x45CE
; Notes   : Inferred core helper routine. Calls: main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_45ce:
    movff       WREG, ram_0x011
    movf        ram_0x011, W, ACCESS
    movwf       ram_0x003, ACCESS
    clrf        ram_0x004, ACCESS
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    movlw       0x96
    movwf       ram_0x007, ACCESS
    clrf        ram_0x008, ACCESS
    ; W04-E01: factor call+4 movff tail into main_core_service_30d8_with_save
    goto        main_core_service_30d8_with_save

; ---------------------------------------------------------------------------
; Function: rx_ring_read                   (UART RX ring dequeue, returns W)
; Address : 0x45FA
; ---------------------------------------------------------------------------
; Returns one byte from the native RX ring at 0x0200..0x02BF (192 bytes,
; rx_ring_rd is the head index; rx_ring_wr is updated by the ISR).
;
; Contract:
;   in : none
;   out: W = byte (or 0 if empty); STATUS.Z indicates empty (via test of
;        the local zero scratch ram_0x004 before/after).
;   side: rx_ring_rd advances and wraps at 0xC0.
;
; Used by main_uart_service_1be6 and uart_rx_with_framing. There is no
; locking — the ISR (uart_rx_irq_enqueue) writes the same backing buffer
; and increments rx_ring_wr; correctness relies on the head/tail pair being
; updated by a single side at a time (cooperative). BUG M6 (rx_ring_no_
; overflow_detect): no full check — the ISR can overwrite the byte that
; this routine is about to read. V3.2 hardening plan workstream 2.
; ---------------------------------------------------------------------------
rx_ring_read:
    clrf        ram_0x004, ACCESS
    rcall       rx_ring_has_data

    bz          flow_rx_ring_read_4620
    movlb       0x0
    movf        rx_ring_rd, W, BANKED
    rcall       fsr2_page2_from_W                    ; W05-E02: FSR2=0x0200|W (movf INDF2 overwrites W)
    movf        INDF2, W, ACCESS
    movwf       ram_0x004, ACCESS
    incf        rx_ring_rd, F, BANKED
    movlw       0xBF
    cpfsgt      rx_ring_rd, BANKED
    bra         flow_rx_ring_read_4620
    clrf        rx_ring_rd, BANKED
flow_rx_ring_read_4620:
    movf        ram_0x004, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_4624
; Address : 0x4624
; Notes   : Inferred usb helper; touches usb.
; ---------------------------------------------------------------------------
main_usb_service_4624:
    clrf        ram_0x0CA, BANKED
    movlw       0x1E
    movwf       UEP1, ACCESS
    movlw       0x40
    movlb       0x4
    movwf       ram_0x00D, BANKED
    movlw       0x04
    movwf       ram_0x00F, BANKED
    movlw       0x2C
    movwf       ram_0x00E, BANKED
    movlw       0x08
    movwf       ram_0x00C, BANKED
    bsf         ram_0x00C, 7, BANKED
    movlw       0x04
    movwf       ram_0x013, BANKED
    movlw       0x6C
    movwf       ram_0x012, BANKED
    movlw       0x40
    movwf       ram_0x010, BANKED
    retlw       0x40


; ---------------------------------------------------------------------------
; Function: main_i2c_service_464c
; Address : 0x464C
; Notes   : Inferred i2c helper; touches i2c.
; ---------------------------------------------------------------------------
main_i2c_service_464c:
    movf        SSPCON1, W, ACCESS
    andlw       0x0F
    xorlw       0x08
    bz          flow_main_i2c_service_464c_4668
    xorlw       0x0B
    btfsc       STATUS, 2, ACCESS
flow_main_i2c_service_464c_4668:
    bsf         SSPCON2, 3, ACCESS
flow_main_i2c_service_464c_466a:
    btfss       SSPSTAT, 0, ACCESS
    bra         flow_main_i2c_service_464c_466a
    movf        SSPBUF, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4672
; Address : 0x4672
; Notes   : Inferred core helper routine. Calls: main_uart_service_44b2.
; ---------------------------------------------------------------------------
main_core_service_4672:
    lfsr        FSR2, 0x01F4
    lfsr        FSR1, 0x001C
    movlw       0x07
flow_main_core_service_4672_467c:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_4672_467c
    movlw       0x1C
    rcall       main_uart_service_44b2
    movlw       0x1C
    rcall       main_uart_service_44b2
    movlw       0x1C
    bra         main_uart_service_44b2


; ---------------------------------------------------------------------------
; Function: uart_tx_block_from_buffer
; Address : 0x4696
; Notes   : Transmits a buffered UART block one byte at a time.
; ---------------------------------------------------------------------------
uart_tx_block_from_buffer:
    clrf        ram_0x01A, ACCESS
    bra         flow_uart_tx_block_from_buffe_46a2
flow_uart_tx_block_from_buffe_469a:
    rcall       main_core_service_46aa
    rcall       uart_tx_byte_blocking
    incf        ram_0x01A, F, ACCESS
flow_uart_tx_block_from_buffe_46a2:
    rcall       main_core_service_46aa
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         flow_uart_tx_block_from_buffe_469a


; ---------------------------------------------------------------------------
; Function: main_core_service_46aa
; Address : 0x46AA
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_46aa:
    movf        ram_0x01A, W, ACCESS
    addwf       ram_0x018, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x019, W, ACCESS
    movwf       FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_secondary_dev_write        (1-byte write to device 0x71, V3.1+)
; Address : 0x46C0
; ---------------------------------------------------------------------------
; Writes one register on the secondary device at 7-bit addr 0x71 (write
; addr 0xE2). Caller stages the register address byte in W and the data
; byte in ram_0x006. Wire format:
;   START | 0xE2 | reg(W) | data(ram_0x006) | STOP
;
; V3.1 hardening: SEN/PEN polls go through wait_sen_bounded /
; wait_pen_bounded; on bounded timeout the routine short-circuits to
; i2c_secondary_done leaving the bus best-effort recovered (caller is
; expected to detect failure via dsp_fault_flags or downstream symptoms).
;
; This is the device touched by hw_standby_shutdown's three-write rail
; sequence — an unbounded wait HERE used to be the V1.62b "PBs don't power
; down" signature; bounding it was part of V3.1.
; ---------------------------------------------------------------------------
i2c_secondary_dev_write:
    movff       WREG, ram_0x007
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    rcall       wait_sen_bounded
    bc          i2c_secondary_done
    movlw       0xE2
    call        i2c_byte_tx, 0x0
    movf        ram_0x007, W, ACCESS
    call        i2c_byte_tx, 0x0
    movf        ram_0x006, W, ACCESS
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    rcall       wait_pen_bounded
i2c_secondary_done:
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_46de
; Address : 0x46DE
; Notes   : Inferred flash helper routine. Calls: eeprom_read_byte, eeprom_write_blocking.
; ---------------------------------------------------------------------------
main_flash_service_46de:
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    rcall       eeprom_read_byte
    xorwf       ram_0x009, W, ACCESS
    bz          flow_main_flash_service_46de_46fe
    movff       ram_0x007, ram_0x003
    movff       ram_0x008, ram_0x004
    movff       ram_0x009, ram_0x005
    rcall       eeprom_write_blocking
flow_main_flash_service_46de_46fe:
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_4700
; Address : 0x4700
; Notes   : Inferred usb helper; touches usb. Calls: main_usb_service_4828, main_usb_service_40d6.
; ---------------------------------------------------------------------------
main_usb_service_4700:
    decf        usb_reinit_pending, W, BANKED
    btfsc       STATUS, 2, ACCESS
    rcall       main_usb_service_4828
    clrf        UCON, ACCESS
    movlw       0x15
    movwf       UCFG, ACCESS
    clrf        UIE, ACCESS
    bsf         UCON, 3, ACCESS
    rcall       main_usb_service_40d6
    movlw       0x01
    movlb       0x0
    movwf       ram_0x0CD, BANKED
    clrf        usb_reinit_pending, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_4720
; Address : 0x4720
; Notes   : Inferred usb helper; touches timer,usb.
; ---------------------------------------------------------------------------
main_usb_service_4720:
    movff       UIE, ram_0x092
    movlw       0x04
    movwf       UIE, ACCESS
    bcf         UIR, 4, ACCESS
    bsf         UCON, 1, ACCESS
    bcf         PIR2, 5, ACCESS
    bsf         PIE2, 5, ACCESS
    bcf         PIE2, 5, ACCESS
    movlb       0x0
    movf        ram_0x092, W, BANKED
    iorwf       UIE, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Helper: fsr2_page0_read_w                           (W04-E03 size-opt helper)
; ---------------------------------------------------------------------------
; Shared factor for the 3-instruction "read mem[page0 + W] via FSR2" pattern:
;     movwf FSR2L, ACCESS
;     clrf  FSR2H, ACCESS
;     movf  INDF2, W, ACCESS
; On entry: W = page-0 byte address (0x00..0xFF).
; On exit:  W = mem[0x0000 + addr]; FSR2L/FSR2H point at that address;
;           Z/N set by the final movf so callers using bz/bnz on the loaded
;           value remain correct (return 0 does not restore STATUS).
; Side effects: ACCESS-bank only; BSR unchanged.
; ---------------------------------------------------------------------------
fsr2_page0_read_w:
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movf        INDF2, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Helper: fsr2_page2_from_W                            (W05-E02 size-opt helper)
; ---------------------------------------------------------------------------
; Shared factor for the 3-instruction "set FSR2 = 0x0200 | W" pattern:
;     movwf FSR2L, ACCESS
;     movlw 0x02
;     movwf FSR2H, ACCESS
; On entry: W = page-2 byte address (0x00..0xFF).
; On exit:  FSR2L/FSR2H point at 0x0200 + W; W = 0x02 (side effect).
; Side effects: ACCESS-bank only; BSR unchanged.  Caller does its own
; indirect access via INDF2 after the call.  Callers that are known to
; not consume W before the next write-to-W are eligible.
; ---------------------------------------------------------------------------
fsr2_page2_from_W:
    movwf       FSR2L, ACCESS
    movlw       0x02
    movwf       FSR2H, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: ram_block_clear
; Address : 0x473E
; Notes   : Clears a RAM span from an FSR2 pointer and byte count.
; ---------------------------------------------------------------------------
ram_block_clear:
    clrf        ram_0x006, ACCESS
    bra         flow_ram_block_clear_4752
flow_ram_block_clear_4742:
    movf        ram_0x006, W, ACCESS
    addwf       ram_0x003, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      ram_0x004, W, ACCESS
    movwf       FSR2H, ACCESS
    clrf        INDF2, ACCESS
    incf        ram_0x006, F, ACCESS
flow_ram_block_clear_4752:
    movf        ram_0x005, W, ACCESS
    subwf       ram_0x006, W, ACCESS
    btfsc       STATUS, 0, ACCESS
    return      0
    bra         flow_ram_block_clear_4742


; ---------------------------------------------------------------------------
; Function: main_usb_service_475c
; Address : 0x475C
; Notes   : Inferred usb helper; touches usb. Calls: main_usb_service_4700, usb_shutdown.
; ---------------------------------------------------------------------------
main_usb_service_475c:
    movlb       0x0
    decf        usb_reinit_pending, W, BANKED
    bz          flow_main_usb_service_475c_4778
    btfss       PORTC, 0, ACCESS
    bra         flow_main_usb_service_475c_476e
    btfss       UCON, 3, ACCESS
    rcall       main_usb_service_4700
    bra         flow_main_usb_service_475c_4778
flow_main_usb_service_475c_476e:
    btfss       UCON, 3, ACCESS
    bra         flow_main_usb_service_475c_4778
    rcall       usb_shutdown
    clrf        usb_reinit_pending, BANKED
flow_main_usb_service_475c_4778:
    return      0


; ---------------------------------------------------------------------------
; Function: main_timer_service_477a
; Address : 0x477A
; Notes   : Inferred timer helper; touches timer.
; ---------------------------------------------------------------------------
main_timer_service_477a:
    movlw       0x98
    movwf       T3CON, ACCESS
    movlw       0xF8
    movwf       TMR3H, ACCESS
    movlw       0x30
    movwf       TMR3L, ACCESS
    movff       ram_0x003, ram_0x08C
    movff       ram_0x004, ram_0x08D
    bcf         PIR2, 1, ACCESS
    bsf         T3CON, 0, ACCESS
    bsf         PIE2, 1, ACCESS
    retlw       0x30

; ---------------------------------------------------------------------------
; Function: standby_event_dispatch        (rail-rise/fall reaction core)
; Address : 0x4796
; ---------------------------------------------------------------------------
; Drains a pending standby event (event_flags.bit2 set by label_154/155 in
; the cmd_03 sub-dispatch) and reacts based on the current active gate
; (active_flags.bit3):
;   gate set    -> adc_boot_gate          (waits AN0 ≥ 0x0236; bug M9: unbounded)
;   gate clear  -> hw_standby_shutdown    (I2C DSP shutdown, T0 disable, OSCCON
;                                          switch, USB disable; sets
;                                          usb_reinit_pending=0x01)
;
; After dispatch the bit is cleared and control falls into cmd_dispatch_gated
; with W=0x01 so the input/volume/mute reconciliation pass runs immediately.
; On a real STDBY broadcast the active gate has already been cleared at
; standby_request_handler, so this routine takes the shutdown path.
;
; V3.2 interaction: preset_job_service detects active_flags.bit3 == 0 and
; cancels the in-flight preset job *before* this routine performs the shutdown,
; so a partially-applied preset never gets "committed" into a hardware-off
; state.
; ---------------------------------------------------------------------------
standby_event_dispatch:
    movlb       0x0
    btfss       event_flags, 2, BANKED              ; pending stdby/wake event?
    bra         flow_standby_event_dispatch_47ac    ; no -> tail-call gate dispatch
    btfss       active_flags, 3, ACCESS             ; gate currently open?
    bra         flow_standby_event_dispatch_47a6    ;   no -> shutdown path
    diag_inc_sat diag_b                              ; V3.2 Layer 5: count bring-up dispatch
    call        adc_boot_gate, 0x0                  ; gate open -> rail-rise wait
    bra         flow_standby_event_dispatch_47aa
flow_standby_event_dispatch_47a6:
    diag_inc_sat diag_s                              ; V3.2 Layer 5: count standby dispatch
    call        hw_standby_shutdown, 0x0            ; I2C DSP shutdown / OSC switch
flow_standby_event_dispatch_47aa:
    bcf         event_flags, 2, BANKED              ; consume the event
flow_standby_event_dispatch_47ac:
    movlw       0x01                                ; W=1 forces post-event reconciliation
    goto        cmd_dispatch_gated

; ---------------------------------------------------------------------------
; Function: mssp_hard_reset                (MSSP soft reset / pin re-arm)
; Address : 0x47B2
; ---------------------------------------------------------------------------
; Bus-recovery primitive used by volume_dsp_write and the V3.2 preset apply
; helper after a SEN/PEN timeout. Caller stages the desired SSPCON1 SSPM
; bits in W (e.g. 0x08 master) and the SSPSTAT SMP bits in ram_0x003 (0x80
; for the stock high-speed setting). The routine:
;   1. clears SSPSTAT[5:0] (preserving SMP/CKE),
;   2. zeroes SSPCON1 / SSPCON2 (forces idle, drops STOP/START in flight),
;   3. re-applies the staged SSPM bits and SSPSTAT mode,
;   4. tristates SDA/SCL (RB0/RB1), then re-enables SSPEN.
; The bus is now ready for i2c_bus_clear (clock 9 + manual STOP) followed by
; dsp_ping. Note SSPEN re-enable comes BEFORE i2c_bus_clear flips back
; (i2c_bus_clear drops SSPEN itself before bit-banging).
; ---------------------------------------------------------------------------
mssp_hard_reset:
    movff       WREG, ram_0x004
    movlw       0x3F
    andwf       SSPSTAT, F, ACCESS
    clrf        SSPCON1, ACCESS
    clrf        SSPCON2, ACCESS
    movf        ram_0x004, W, ACCESS
    iorwf       SSPCON1, F, ACCESS
    movf        ram_0x003, W, ACCESS
    iorwf       SSPSTAT, F, ACCESS
    bsf         TRISB, 1, ACCESS
    bsf         TRISB, 0, ACCESS
    bsf         SSPCON1, 5, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: periodic_service_loop          (one main-loop pass — service slot)
; Address : 0x47CE
; ---------------------------------------------------------------------------
; Single iteration of the cooperative main loop. main_processing_loop tail-
; calls this between USB SIE polls. Order matters:
;   1. main_usb_service_3a26   USB SIE / endpoint pump (must run frequently)
;   2. main_uart_service_1be6  drain native RX ring + parse + forward
;   3. preset_job_service      V3.2: ONE step of the async preset state machine
;                              (see notes near preset_job_service for invariants)
;   4. main_i2c_service_27f0   refresh DSP I2C state (volume dirty drain etc.)
;   5. standby_event_dispatch  stdby/wake reaction if event_flags.bit2 pending
;   6. main_core_service_265c  housekeeping (Timer3 reload, ping fault relay)
;   7. an0_hysteresis_monitor  AN0 ADC threshold tracking (rail rise/fall)
;
; Total worst-case path is dominated by the legacy main_i2c_service_381c sites
; reachable from main_i2c_service_27f0 — those are the V3.2 hardening targets
; documented in docs/V32_MAIN_HANG_HARDENING_PLAN.md workstream 1.
; ---------------------------------------------------------------------------
periodic_service_loop:
    call        main_usb_service_3a26, 0x0
    call        main_uart_service_1be6, 0x0
    rcall       main_service_rx_frame_gap           ; V3.2 §2: parser stall watchdog
    rcall       preset_job_service                  ; V3.2: async preset state machine
    call        main_i2c_service_27f0, 0x0
    rcall       standby_event_dispatch
    call        main_core_service_265c, 0x0
    rcall       ra1_edge_monitor                    ; V3.2 Layer 5: diag_p edge counter
    bra         an0_hysteresis_monitor

; ---------------------------------------------------------------------------
; ra1_edge_monitor — V3.2 Layer 5 RA1 edge counter (diag_p)
; ---------------------------------------------------------------------------
; Polled once per periodic_service_loop pass (= main_processing_loop tick,
; tens of µs).  Compares PORTA bit 1 against diag_ra1_prev shadow byte;
; on either edge (0→1 or 1→0) bumps diag_p (saturating at 0x0F).  Tested
; via gpsim by toggling RA1 in the harness; no real-hardware function is
; assigned to RA1 in V3.2, so this is pure observability infrastructure
; per docs/V163B_DIAGNOSTICS_MENU_SPEC.md "RA1-trigger path" section.
; ---------------------------------------------------------------------------
ra1_edge_monitor:
    movff       BSR, ram_0x00E                  ; save caller BSR
    movlb       0x02                            ; V3.2 Layer 5 diag block in BANK 2
    movf        PORTA, W, ACCESS                ; W = PORTA snapshot
    andlw       0x02                            ; isolate RA1
    xorwf       diag_ra1_prev, W, BANKED        ; W = current ^ prev (bit 1 only)
    btfsc       STATUS, 2, ACCESS               ; if Z (no edge), skip increment
    bra         ra1_no_edge
    ; Edge detected — refresh shadow and bump counter.
    movf        PORTA, W, ACCESS
    andlw       0x02
    movwf       diag_ra1_prev, BANKED
    diag_inc_sat diag_p                          ; macro re-asserts movlb 0x02
ra1_no_edge:
    movff       ram_0x00E, BSR                  ; restore caller BSR
    return      0

; ---------------------------------------------------------------------------
; Inline Data Table (0x47E6-0x47FB)
; ---------------------------------------------------------------------------
inline_data_table_47E6:  ; UART status strings for FW update
    dw  0x202D, 0x4146, 0x4C49, 0x0020, 0x5746, 0x555F, 0x6470, 0x3000
    dw  0x3030, 0x3030, 0x0030

; ---------------------------------------------------------------------------
; Remaining Code (0x47FC-0x496F)
; ---------------------------------------------------------------------------

; ---------------------------------------------------------------------------
; Function: report_cmd29_status
; Address : 0x47FC
; Notes   : Inferred uart helper routine. Calls: uart_tx_byte_blocking.
; ---------------------------------------------------------------------------
report_cmd29_status:
    movlw       0xBF
    rcall       uart_tx_byte_blocking
    movlw       0x29
    rcall       uart_tx_byte_blocking
    movlw       0x01
    btfss       active_flags, 1, ACCESS
    movlw       0x00
    bra         uart_tx_byte_blocking


; ---------------------------------------------------------------------------
; Function: main_usb_service_4812          (16-bit countdown busy-wait + WDT clr)
; Address : 0x4812
; ---------------------------------------------------------------------------
; Decrements the 16-bit pair {ram_0x004,ram_0x003} to zero, calling CLRWDT
; on every iteration. This is the ONLY routine in MAIN that ever clears the
; WDT (BUG M8: no_clrwdt_main_loop). Called from main_usb_service_4828
; during USB-disconnect / sleep transitions, where it acts as the
; soft-reset backstop while UCON is being torn down.
; ---------------------------------------------------------------------------
main_usb_service_4812:
    bra         flow_main_usb_service_4812_481e
flow_main_usb_service_4812_4814:
    clrwdt
    decf        ram_0x003, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        ram_0x004, F, ACCESS
flow_main_usb_service_4812_481e:
    movf        ram_0x004, W, ACCESS
    iorwf       ram_0x003, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         flow_main_usb_service_4812_4814


; ---------------------------------------------------------------------------
; Function: main_usb_service_4828
; Address : 0x4828
; Notes   : Inferred usb helper; touches usb. Calls: main_usb_service_4812.
; ---------------------------------------------------------------------------
main_usb_service_4828:
    bcf         UCON, 1, ACCESS
    clrf        UCON, ACCESS
    movlw       0xFF
    setf        ram_0x004, ACCESS
    setf        ram_0x003, ACCESS
    rcall       main_usb_service_4812
    movlb       0x0
    clrf        ram_0x0CD, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_483c
; Address : 0x483C
; Notes   : Inferred usb helper; touches usb. Calls: main_core_service_4924.
; ---------------------------------------------------------------------------
main_usb_service_483c:
    rcall       main_core_service_4924
    bcf         UCON, 1, ACCESS
    bcf         UIE, 2, ACCESS
    bra         flow_main_usb_service_483c_4848
flow_main_usb_service_483c_4846:
    bcf         UIR, 2, ACCESS
flow_main_usb_service_483c_4848:
    btfss       UIR, 2, ACCESS
    return      0
    bra         flow_main_usb_service_483c_4846


; ---------------------------------------------------------------------------
; Function: factory_reset_status_emit
; Address : 0x484E
; Notes   : Emits BF/18/01 factory-reset status frame over UART.
; ---------------------------------------------------------------------------
factory_reset_status_emit:
    movlw       0xBF
    rcall       uart_tx_byte_blocking
    movlw       0x18
    rcall       uart_tx_byte_blocking
    movlw       0x01
    bra         uart_tx_byte_blocking


; ---------------------------------------------------------------------------
; Function: main_uart_service_4860         (drain RX ring to completion)
; Address : 0x4860
; ---------------------------------------------------------------------------
; Tight loop: while rx_ring has data, dequeue one byte (W is discarded).
; This is the "throw away everything pending" primitive used to clear the
; ring before entering firmware-update relay or after a parser desync —
; NOT used on the hot parsing path (which dequeues and dispatches inline).
; ---------------------------------------------------------------------------
main_uart_service_4860:
    bra         flow_main_uart_service_4860_4866
flow_main_uart_service_4860_4862:
    rcall       rx_ring_read
flow_main_uart_service_4860_4866:
    rcall       rx_ring_has_data

    btfsc       STATUS, 2, ACCESS
    return      0
    bra         flow_main_uart_service_4860_4862


; ---------------------------------------------------------------------------
; Function: rx_ring_has_data               (UART RX ring head!=tail predicate)
; Address : 0x4872
; ---------------------------------------------------------------------------
; Returns STATUS.Z=1 when rx_ring_rd == rx_ring_wr (empty), Z=0 when the
; ring has data. W is set to (wr XOR rd) which carries no useful value
; beyond the Z flag; callers consume only Z.
; ---------------------------------------------------------------------------
rx_ring_has_data:
    movlb       0x0
    movf        rx_ring_wr, W, BANKED
    xorwf       rx_ring_rd, W, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: eeprom_read_byte               (single-byte EEPROM read)
; Address : 0x4884
; ---------------------------------------------------------------------------
; Caller stages address in ram_0x003. Returns byte in W. EEPGD=0, CFGS=0,
; RD=1; the two `dw 0xF000` words are NOPs satisfying the EEPROM read
; latency on PIC18 (one cycle for the read setup, one cycle for the data
; latch). Used heavily by the preset-filename load path
; (preset_load_filename) and settings_load.
; ---------------------------------------------------------------------------
eeprom_read_byte:
    movff       ram_0x003, EEADR
    bcf         EECON1, 6, ACCESS
    bcf         EECON1, 7, ACCESS
    bsf         EECON1, 0, ACCESS
    dw          0xF000
    dw          0xF000
    movf        EEDATA, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: uart_tx_byte_blocking          (single byte TX, V3.1+ bounded)
; Address : 0x4896
; ---------------------------------------------------------------------------
; Stock contract: caller stages byte in W, helper waits TXSTA.TRMT then
; writes TXREG. Returns the byte in W on success.
;
; V3.1 hardening (BUG M2 fix — uart_tx_trmt_busywait):
;   • TRMT poll runs through wait_trmt_bounded (~39 ms timeout). On C=1
;     it falls to uart_tx_timeout, which:
;       - re-runs uart_config (full EUSART re-init)
;       - retries wait_trmt_bounded once
;       - on a second timeout: goto hard_reset (panic)
;   • Original stock body had an unbounded `btfss TXSTA, TRMT` spin at
;     label_605, the entire bus would lock if a hardware UART glitch left
;     TRMT clear forever. The V3.1 escalation matches the volume_dsp_write
;     pattern (retry, then escalate, then panic).
; ---------------------------------------------------------------------------
uart_tx_byte_blocking:
    movff       WREG, ram_0x003
    rcall       wait_trmt_bounded
    bc          uart_tx_timeout
    movff       ram_0x003, TXREG
    movf        ram_0x003, W, ACCESS
    return      0
uart_tx_timeout:
    rcall       uart_config
    rcall       wait_trmt_bounded
    bc          v31_hard_reset_jump2
    movff       ram_0x003, TXREG
    movf        ram_0x003, W, ACCESS
    return      0
v31_hard_reset_jump2:
    bra         hard_reset


; ---------------------------------------------------------------------------
; Function: main_timer_service_48a6        (Timer0 re-arm — ~50 ms heartbeat)
; Address : 0x48A6
; ---------------------------------------------------------------------------
; Re-arms Timer0 with TMR0=0xA471 → ~50 ms overflow @ 16 MHz / 4 / 1024
; prescaler. Called whenever the main service loop wants to schedule a
; "wake me later" tick (post-cmd reconciliation, post-USB-state-change,
; rail wait pre-roll). Returns retlw 0x71 (TMR0L low byte) to keep callers
; consistent with the earlier stock behavior.
; ---------------------------------------------------------------------------
main_timer_service_48a6:
    movlw       0xA4                                ; TMR0H = 0xA4 — high byte of preload
    movwf       TMR0H, ACCESS
    movlw       0x71                                ; TMR0L = 0x71
    movwf       TMR0L, ACCESS
    bcf         INTCON, 2, ACCESS                   ; clear T0IF
    bsf         INTCON, 5, ACCESS                   ; T0IE on
    bsf         T0CON, 7, ACCESS                    ; TMR0ON on
    retlw       0x71

; ---------------------------------------------------------------------------
; Function: i2c_wait_bus_idle              (M1: STOCK unbounded MSSP-idle spin)
; Address : 0x48B6
; ---------------------------------------------------------------------------
; Spin until the MSSP module reports idle: SSPCON2[4:0] (SEN, RSEN, PEN,
; RCEN, ACKEN) == 0 AND SSPSTAT.R_nW (bit 2) == 0.
;
; BUG M1 (i2c_busywait_no_timeout): no timeout. This is the canonical
; example of the unbounded-wait pattern that the V3.2 hardening plan
; targets. The V3.1+ wait_*_bounded helpers cover SEN/PEN/BF/TRMT but the
; "is the controller idle at all" question still uses this stock primitive.
;
; Used by i2c_tas3108_reg1f_write, i2c_tas3108_coeff_write,
; i2c_secondary_dev_random_read at the start of each transaction (so a
; previous incomplete transaction must finish before the next can begin).
;
; Note: flow_i2c_wait_bus_idle_48c6 is NOT part of i2c_wait_bus_idle —
; it is the tail entry of an unrelated routine landing here by branch
; alias; main_processing_loop is also defined right after, sharing this
; address window because the assembler packs sequentially.
; ---------------------------------------------------------------------------
i2c_wait_bus_idle:
    movff       SSPCON2, ram_0x003
    movlw       0x1F
    andwf       ram_0x003, F, ACCESS                ; mask SEN/RSEN/PEN/RCEN/ACKEN
    btfsc       STATUS, 2, ACCESS                   ; if any of those set, keep spinning
    btfsc       SSPSTAT, 2, ACCESS                  ; AND while R_nW (master in receive)
    bra         i2c_wait_bus_idle
    retlw       0x1F
flow_i2c_wait_bus_idle_48c6:
    call        main_i2c_service_355c, 0x0
; ---------------------------------------------------------------------------
; main_processing_loop                     (top-level idle/service loop)
; Address : 0x48CA
; ---------------------------------------------------------------------------
; Cooperative super-loop: USB SIE pump, then periodic_service_loop. Tight
; loop because periodic_service_loop must run as often as possible to keep
; UART RX latency below 1 byte time at 31,250 baud (~320 µs/byte) — any
; slower and the rx_ring overflow hazard (M6) becomes likely.
; ---------------------------------------------------------------------------
main_processing_loop:
    call        main_usb_service_2f4e, 0x0          ; USB SIE / endpoint pump
    rcall       periodic_service_loop               ; one main-loop pass
    bra         main_processing_loop

; ---------------------------------------------------------------------------
; Function: hard_reset                     (PIC reset instruction — panic exit)
; Address : 0x48D4
; ---------------------------------------------------------------------------
; Top-of-app panic endpoint. Disables all interrupts (clrf INTCON), pads
; with two NOP-equivalent words, executes the PIC18 RESET instruction,
; then pads again. Reached from uart_tx_byte_blocking when even the
; reconfigured EUSART cannot drain TRMT (two strikes), and from the V3.1
; volume_dsp_write final-escalation path when retries + bus-clear + ping
; all fail.
;
; On reset, PC -> 0x0000 (bootloader), which jumps back to 0x1000 unless
; the bootloader-entry combo (UP+DOWN+!SELECT for ~5 s) is held on
; CONTROL — in that case the bootloader takes over for FW update.
; ---------------------------------------------------------------------------
hard_reset:
    clrf        INTCON, ACCESS
    dw          0xF000
    dw          0xF000
    reset
    dw          0xF000
    dw          0xF000
    return      0


; ---------------------------------------------------------------------------
; Function: main_i2c_service_48e2
; Address : 0x48E2
; Notes   : Inferred i2c helper routine. Calls: i2c_tas3108_reg1f_write.
; ---------------------------------------------------------------------------
main_i2c_service_48e2:
    movlw       0x02
    rcall       i2c_tas3108_reg1f_write
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: usb_shutdown                   (USB PHY drop + reinit-pending flag)
; Address : 0x48F0
; ---------------------------------------------------------------------------
; Drops UCON.SUSPND, zeroes UCON entirely, clears ram_0x0CD (USB endpoint
; state machine slot), then sets usb_reinit_pending = 0x01 so the main
; loop's main_usb_service_475c will route through main_usb_service_4700
; (full UCON re-arm) on the next pass once PORTC.RC0 indicates host
; presence again.
;
; Returns 0x01 in W (the reinit-pending flag value) so callers can chain
; checks without re-reading the BANKED RAM.
; ---------------------------------------------------------------------------
usb_shutdown:
    bcf         UCON, 1, ACCESS
    clrf        UCON, ACCESS
    movlb       0x0
    clrf        ram_0x0CD, BANKED
    movlw       0x01
    movwf       usb_reinit_pending, BANKED
    retlw       0x01


; ---------------------------------------------------------------------------
; Function: flash_entry_quiet_shutdown      (V3.2+ pop-free flash entry)
; ---------------------------------------------------------------------------
; Called ONLY from the flash-trigger handler in flow_hid_command_dispatch_13d0
; after EEPROM[0xFF]=0 has been committed. Drives the same sequence that
; hw_standby_shutdown uses to land the amp inputs at a known quiescent point
; BEFORE the PIC18 RESET instruction tristates every pin.
;
; Deliberately OMITS the parts of hw_standby_shutdown that would break flash
; entry: no OSCCON.SCS1 change (USB needs HS osc until RESET), no SPBRG/UCON
; change (RESET disconnects USB cleanly), no T0/INTCON teardown (Timer3
; settle still needs the tick source), no 4 x 250 ms rail-bleed loop.
;
; Falls into hard_reset; never returns on normal completion. Bounded-wait
; failures inside i2c_secondary_dev_write / i2c_tas3108_coeff_write still
; reach the goto hard_reset at the bottom — worst case is a single click,
; never a hang.
; ---------------------------------------------------------------------------
flash_entry_quiet_shutdown:
    rcall       preset_force_mute               ; (1) DSP coefficients = 0
    clrf        ram_0x006, ACCESS               ; (2) drop audio rails via 0x71
    movlw       0x1B
    rcall       i2c_secondary_dev_write
    clrf        ram_0x006, ACCESS
    movlw       0x1C
    rcall       i2c_secondary_dev_write
    clrf        ram_0x006, ACCESS
    movlw       0x1D
    rcall       i2c_secondary_dev_write
    bcf         LATB, 4, ACCESS                 ; (3) amp enable - graceful
    bcf         LATA, 6, ACCESS                 ;     drop to LOW while pins
    bcf         LATA, 3, ACCESS                 ;     are still being driven
    bcf         LATA, 4, ACCESS                 ;     (RESET would tristate
    bcf         LATA, 5, ACCESS                 ;     them in one Tcy)
    movlw       0x64                            ; (4) 100 ms timer3 settle
    rcall       timer3_blocking_delay_ms_W      ;     (W04-E08 factored)
    bcf         LATB, 3, ACCESS                 ; (5) final amp gate down
    bra         hard_reset                      ; (6) now do the RESET


; ---------------------------------------------------------------------------
; Function: main_core_service_48fe
; Address : 0x48FE
; Notes   : Inferred core helper routine. Calls: main_usb_service_4624.
; ---------------------------------------------------------------------------
main_core_service_48fe:
    movff       WREG, ram_0x003
    decf        ram_0x003, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    rcall       main_usb_service_4624
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_490c
; Address : 0x490C
; Notes   : Inferred usb helper; touches timer,usb. Calls: main_usb_service_4828.
; ---------------------------------------------------------------------------
main_usb_service_490c:
    btfss       T3CON, 0, ACCESS
    bra         flow_main_usb_service_490c_4914
    bcf         STATUS, 0, ACCESS
    bra         flow_main_usb_service_490c_4916
flow_main_usb_service_490c_4914:
    bsf         STATUS, 0, ACCESS
flow_main_usb_service_490c_4916:
    return      0
flow_main_usb_service_490c_4918:
    btfsc       UCON, 3, ACCESS
    rcall       main_usb_service_4828
    clrf        usb_reinit_pending, BANKED
    bra         main_usb_service_475c


; ---------------------------------------------------------------------------
; Function: main_core_service_4924
; Address : 0x4924
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4924:
    movlw       0x03
    movwf       ram_0x004, ACCESS
    clrf        ram_0x003, ACCESS
    bra         flow_main_usb_service_4812_481e


; ---------------------------------------------------------------------------
; Function: main_core_service_492e
; Address : 0x492E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_492e:
    clrf        ram_0x004, ACCESS
    movlw       0x01
    movwf       ram_0x003, ACCESS
    bra         timer3_blocking_delay


; ---------------------------------------------------------------------------
; Function: main_uart_tx_only_service      (wake-time TX re-arm, RX still off)
; Address : 0x4938
; ---------------------------------------------------------------------------
; Wake-time cmd_dispatch_gated can emit BF/08 over the serial link before the
; reconnect window fully re-opens.  Reuse uart_config to restore baud/SPEN/TXEN,
; then immediately clear CREN so CONTROL polls cannot accumulate into RCREG
; while GIE is still masked across the remaining wake-time housekeeping.
; ---------------------------------------------------------------------------
main_uart_tx_only_service:
    rcall       uart_config
    bcf         RCSTA, 4, ACCESS
    bra         uart_parser_resync


; ---------------------------------------------------------------------------
; Function: main_uart_service_4938
; Address : 0x4938
; Notes   : Inferred uart helper routine. Calls: uart_config, uart_parser_resync.
; ---------------------------------------------------------------------------
main_uart_service_4938:
    rcall       uart_config
    bra         uart_parser_resync


; ---------------------------------------------------------------------------
; Function: main_core_service_4942
; Address : 0x4942
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4942:
    clrf        ram_0x004, ACCESS
    movlw       0x02
    movwf       ram_0x003, ACCESS
    bra         timer3_blocking_delay


; ---------------------------------------------------------------------------
; Function: main_timer_service_494c
; Address : 0x494C
; Notes   : Inferred timer helper; touches timer.
; ---------------------------------------------------------------------------
main_timer_service_494c:
    bcf         T3CON, 0, ACCESS
    bcf         PIR2, 1, ACCESS
    bcf         PIE2, 1, ACCESS
    return      0


copy_computed_volume_to_logical_volume:
    movff       computed_volume, logical_volume
    movff       computed_volume_1, logical_volume_1
    movff       computed_volume_2, logical_volume_2
    movff       computed_volume_3, logical_volume_3
    return      0


; ===========================================================================
; V3.1 New Functions (after last stock function, before preset tables)
; ===========================================================================

; ---------------------------------------------------------------------------
; Bounded Wait Helpers (shared 16-bit timeout infrastructure)
; ---------------------------------------------------------------------------
wait_seed:
    clrf        timeout_lo, ACCESS
    movlw       0x10
    movwf       timeout_hi, ACCESS
    bcf         STATUS, 0, ACCESS           ; clear C
    return      0

wait_tick:
    decfsz      timeout_lo, F, ACCESS
    return      0
    decfsz      timeout_hi, F, ACCESS
    return      0
    bsf         STATUS, 0, ACCESS           ; C=1: timeout
    return      0

wait_trmt_bounded:
    rcall       wait_seed
wait_trmt_loop:
    btfsc       TXSTA, 1, ACCESS            ; TRMT?
    bra         wait_wait_done
    rcall       wait_tick
    bnc         wait_trmt_loop
    return      0

wait_sen_bounded:
    rcall       wait_seed
wait_sen_loop:
    btfss       SSPCON2, 0, ACCESS          ; SEN clear?
    bra         wait_wait_done
    rcall       wait_tick
    bnc         wait_sen_loop
    return      0

wait_pen_bounded:
    rcall       wait_seed
wait_pen_loop:
    btfss       SSPCON2, 2, ACCESS          ; PEN clear?
    bra         wait_wait_done
    rcall       wait_tick
    bnc         wait_pen_loop
    return      0

wait_bf_clear_bounded:
    rcall       wait_seed
wait_bf_clear_loop:
    btfss       SSPSTAT, 0, ACCESS          ; BF set?
    bra         wait_wait_done              ; BF=0: buffer empty, done
    rcall       wait_tick
    bnc         wait_bf_clear_loop
    return      0                           ; C=1: timed out
wait_wait_done:
    bcf         STATUS, 0, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Recovery Helpers
; ---------------------------------------------------------------------------
; ---------------------------------------------------------------------------
; I2C Bus Clear (Fix C) — 9 SCL clocks + manual STOP
; ---------------------------------------------------------------------------
i2c_bus_clear:
    bcf         SSPCON1, 5, ACCESS          ; SSPEN off — release pins
    bsf         TRISB, 1, ACCESS            ; RB1 (SCL) input (pulled high)
    bsf         TRISB, 0, ACCESS            ; RB0 (SDA) input (pulled high)
    movlw       0x09
    movwf       timeout_lo, ACCESS
i2c_bus_clear_clk:
    bcf         TRISB, 1, ACCESS            ; SCL low
    bcf         LATB, 1, ACCESS
    nop
    nop
    bsf         TRISB, 1, ACCESS            ; SCL high
    nop
    nop
    btfsc       PORTB, 0, ACCESS            ; SDA released?
    bra         i2c_bus_clear_stop
    decfsz      timeout_lo, F, ACCESS
    bra         i2c_bus_clear_clk
i2c_bus_clear_stop:
    bcf         TRISB, 0, ACCESS            ; SDA output
    bcf         LATB, 0, ACCESS             ; SDA low
    nop
    bsf         TRISB, 1, ACCESS            ; SCL high
    nop
    nop
    bsf         TRISB, 0, ACCESS            ; SDA high = STOP
    movlw       0x28                        ; I2C master + SSPEN
    movwf       SSPCON1, ACCESS
    return      0

; ---------------------------------------------------------------------------
; DSP Ping (Fix D) — TAS3108 address probe
; ---------------------------------------------------------------------------
; BSR contract: self-asserts BSR=0 at entry so the BANKED writes to
; ``dsp_fault_flags`` (0x07F, bank 0) hit the right cell regardless of
; the caller's incoming BSR.  Required because at least one caller --
; the volume_dsp_write retry-exhausted recovery branch at
; ``vol_exhausted_skip_i2c`` predecessor (asm:9370+) -- invokes
; ``diag_inc_sat diag_r`` (which sets BSR=2) immediately before the
; ``rcall dsp_ping``, so without this self-assertion the BANKED writes
; would land at 0x27F (bank 2) instead of 0x07F.  The intermediate
; helpers ``wait_sen_bounded``, ``wait_pen_bounded`` are ACCESS-only
; (BSR-neutral) and ``i2c_byte_tx`` save/restores caller's BSR
; (asm:6696/6703), so the entry assertion alone is sufficient.
; ---------------------------------------------------------------------------
dsp_ping:
    movlb       0x0                          ; assert bank 0 for dsp_fault_flags
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    rcall       wait_sen_bounded
    bc          dsp_ping_nack
    movlw       0x68                        ; TAS3108 write addr
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    rcall       wait_pen_bounded
    btfss       SSPCON2, 6, ACCESS          ; ACKSTAT?
    bcf         dsp_fault_flags, 6, BANKED  ; ACK: clear fault
    btfsc       SSPCON2, 6, ACCESS
    bra         dsp_ping_nack
    return      0
dsp_ping_nack:
    bsf         dsp_fault_flags, 6, BANKED  ; NACK: set fault
    return      0

; ---------------------------------------------------------------------------
; Send DSP Fault Status (Fix E) — BF/08 frame to CONTROL
; ---------------------------------------------------------------------------
send_dsp_fault_status:
    movlb       0x00
    movf        dsp_fault_flags, W, BANKED
    andlw       0x44                        ; bits 6 + 2
    movwf       ram_0x00D, ACCESS           ; save in ram_0x00D (uart_tx clobbers ram_0x003)
    movlw       0xBF
    rcall       uart_tx_byte_blocking
    movlw       0x08
    rcall       uart_tx_byte_blocking
    movf        ram_0x00D, W, ACCESS
    bra         uart_tx_byte_blocking

; ---------------------------------------------------------------------------
; cmd 0x21 — Diagnostics counter reply burst (V3.2 Layer 5)
; ---------------------------------------------------------------------------
; Reached from main_uart_service_1be6 dispatch when CONTROL sends
; [B0/B1/B2, 0x21, 0x00].  Emits SEVEN BF/2N reply frames, one counter
; per frame in the data byte's LOW nibble (high nibble forced to 0):
;
;   BF/21 = diag_i  (I2C transport faults)
;   BF/22 = diag_d  (DSP-fault episodes)
;   BF/23 = diag_s  (standby/shutdown dispatches)
;   BF/24 = diag_b  (bring-up / wake dispatches)
;   BF/25 = diag_r  (recovery branch entries)
;   BF/26 = diag_a  (AN0-triggered standby)
;   BF/27 = diag_p  (RA1 edge events; LAST FRAME — CONTROL clears
;                    its PENDING flag and toggles next-target here)
;
; Each counter byte saturates at 0x0F so it fits in one nibble.  The
; original 4-frame packed-nibble scheme (pack(I,D), pack(S,B),
; pack(R,A), pack(0,P)) was retired 2026-04-19 because data bytes
; >= 0x80 were re-interpreted as routes by the chain forwarder.  See
; docs/V163B_DIAGNOSTICS_MENU_SPEC.md for the full contract and the
; CONTROL-side rendering rules.
;
; Caller convention:
;   in : nothing — body sets FSR0 to diag_i (0x2E5) and tail-calls
;        diag_send_burst_xx, which walks the 7 counters via POSTINC0.
;   out: returns via flow_main_uart_service_1be6_1e6c (the parser tail
;        used by every cmd handler), so dispatch+forwarding to PB2 stays
;        consistent with stock cmd handlers.
;   side: FSR0-based reads are bank-agnostic; the body never asserts a
;         specific bank.  uart_tx_byte_blocking's timeout fallback does
;         an unconditional `movlb 0x0`, so a wedged-and-recovered TX
;         path can leave BSR at 0 on exit.  Callers that depend on a
;         specific bank must reset BSR themselves.  uart_tx_byte_blocking
;         is bounded so a wedged TX path cannot hang here.
; ---------------------------------------------------------------------------
cmd21_diag_query_handler:
    ; ---------------------------------------------------------------
    ; V3.2 Layer 5 Phase B revision: 7 single-counter frames
    ; ---------------------------------------------------------------
    ; The original packed-nibble design (4 frames carrying pack(I,D),
    ; pack(S,B), pack(R,A), pack(0,P)) hit a chain-protocol invariant:
    ; data bytes >= 0x80 get re-interpreted as routes by the K20
    ; CONTROL parser AND by MAIN's chain forwarder for PB2 traffic.
    ; Counter values where the "high nibble" counter exceeds 7 would
    ; produce data bytes >= 0x80 (e.g. diag_i=12, diag_d=2 → 0xC2)
    ; which the forwarder treats as a route byte, dropping the data
    ; and corrupting the parser frame state.
    ;
    ; Fix: emit 7 frames, one per counter, with the counter value in
    ; the LOW nibble of the data byte (high nibble forced to 0).
    ; Data is then always 0..0x0F < 0x80 — passes through chain
    ; forwarders intact regardless of which PB sourced the reply.
    ;
    ; Frame schedule:
    ;   BF/21 = diag_i  (low nibble; high nibble = 0)
    ;   BF/22 = diag_d
    ;   BF/23 = diag_s
    ;   BF/24 = diag_b
    ;   BF/25 = diag_r
    ;   BF/26 = diag_a
    ;   BF/27 = diag_p  (last frame; CONTROL uses this to mark PB
    ;                    present and toggle next-target)
    ; Implementation: rev 0x37 (Tier-1) loop refactor.  Driven by an
    ; FSR0 walk and the shared diag_send_burst_xx helper (cmd 0x22 reuses
    ; it).  Frees ~100 bytes of flash for the new cmd 0x22 + HID cmd 0x44
    ; handlers vs the rev 0x35 unrolled body, but stays structurally
    ; identical from the wire's perspective: same 7 frames, same
    ; `andlw 0x0F` mask, same ACK-echo suppression.
    ;
    ; BSR safety: FSR0 indirect addressing (POSTINC0) is bank-agnostic.
    ; The body never asserts a specific BSR; uart_tx_byte_blocking's
    ; timeout-fallback path (uart_tx_timeout → uart_config does an
    ; unconditional `movlb 0x0`) cannot affect a POSTINC0 read, so the
    ; per-frame BSR re-assertion the rev 0x35 unrolled body needed is
    ; not necessary here.  The diag block was relocated 0x123..0x12A
    ; -> 0x2E5..0x2EC on 2026-04-19 to escape the USB EP1 OUT buffer
    ; (HID OUT) at 0x11A..0x159 — the original placement caused HID
    ; payload byte 14 corruption on every filename / route HID write.
    ; See dlcp_main_ram.inc.
    movlw       0x28                        ; sentinel: stop AFTER BF/27 sent
    movwf       ram_0x004, ACCESS
    movlw       0x21                        ; first sub-cmd byte
    movwf       i2c_coeff_3, ACCESS
    lfsr        FSR0, diag_i                ; 0x2E5 — first diag counter
    bra         diag_send_burst_xx

; ---------------------------------------------------------------------------
; cmd 0x22 — Reset-cause flags reply burst (V3.2 rev 0x37 Tier-1)
; ---------------------------------------------------------------------------
; Reached from main_uart_service_1be6 dispatch when CONTROL sends
; [B0/B1/B2, 0x22, 0x00].  Emits FOUR BF/2N reply frames carrying the
; 4 reset-cause FLAGS in the low nibble (each value is 0 or 1; cold-init
; sets exactly one flag per session per V32_DIAG_TIER1_SPEC.md):
;
;   BF/28 = diag_reset_por  (O — Power-On Reset)
;   BF/29 = diag_reset_bor  (V — Brown-Out Reset)
;   BF/2A = diag_reset_wdt  (W — WDT timeout)
;   BF/2B = diag_reset_sw   (X — software reset; LAST FRAME — CONTROL
;                            uses this to clear RESET_PENDING and refresh
;                            the per-PB reset-cause cache)
;
; CONTROL fires this ONCE per Diag-page entry (the flag value never
; changes within a session — cold-init is the only thing that mutates
; the cells), so cmd 0x22 is NOT on the cadence rotation alongside
; cmd 0x21.  This decouples runtime-cadence traffic from reset-cause
; traffic and keeps `cmd 0x21` at its fixed 7-frame contract for
; backward compatibility with V3.2 ≤ rev 0x36 MAINs.
;
; Older MAINs (≤ rev 0x36) have NO handler for cmd 0x22.  The cmd-XOR-
; chain dispatch path still fires for them, emitting ONE stray byte
; upstream as the cmd-XOR ACK echo (data byte 0x00 → echoed 0x00).
; CONTROL drops the stray byte at parser frame_position == 0; reset
; cells stay at 0 in cache; LCD shows runtime counters only.  The new
; rev 0x37 handler MUST suppress the cmd-XOR ACK echo (`bcf
; active_flags, 6, ACCESS` before the parser-tail goto) so the chain
; stays clean even when both sides know about Tier-1 — exactly mirrors
; the rev 0x35 fix on cmd 0x21.
;
; Caller convention:
;   in : nothing — body sets FSR0 to diag_reset_por (0x2ED) and tail-
;        calls diag_send_burst_xx, which walks the 4 reset-cause flag
;        cells via POSTINC0.
;   out: returns via flow_main_uart_service_1be6_1e6c (the parser tail
;        used by every cmd handler), so dispatch + forwarding to PB2
;        stays consistent with stock cmd handlers.
;   side: FSR0-based reads are bank-agnostic; the body never asserts a
;         specific bank.  uart_tx_byte_blocking's timeout fallback does
;         an unconditional `movlb 0x0`, so a wedged-and-recovered TX
;         path can leave BSR at 0 on exit.  Callers that depend on a
;         specific bank must reset BSR themselves.  Same shape as
;         cmd21_diag_query_handler; both share diag_send_burst_xx.
; ---------------------------------------------------------------------------
cmd22_reset_flags_query_handler:
    ; Reuses diag_send_burst_xx (defined immediately below) — exactly
    ; the same wire shape as cmd 0x21 but with a different FSR0 base
    ; (reset-cause flag cells) and different sub-cmd range (0x28..0x2B).
    movlw       0x2C                        ; sentinel: stop AFTER BF/2B sent
    movwf       ram_0x004, ACCESS
    movlw       0x28                        ; first sub-cmd byte
    movwf       i2c_coeff_3, ACCESS
    lfsr        FSR0, diag_reset_por        ; 0x2ED — first reset-flag cell
    bra         diag_send_burst_xx

; ---------------------------------------------------------------------------
; diag_send_burst_xx — shared helper for cmd 0x21 + cmd 0x22 reply burst
; ---------------------------------------------------------------------------
; Caller convention:
;   ram_0x004    = sentinel (one greater than the LAST sub-cmd byte to send;
;                  e.g. 0x28 for cmd 0x21, 0x2C for cmd 0x22)
;   i2c_coeff_3  = first sub-cmd byte (e.g. 0x21 for cmd 0x21, 0x28 for 0x22)
;   FSR0         = pointer to first counter / flag cell to read
; Each iteration emits one BF/2N frame and advances both the sub-cmd byte
; and FSR0.  Loop ends when i2c_coeff_3 == ram_0x004 (sentinel).  Suppresses
; the cmd-XOR-chain ACK echo on exit (mirrors the rev 0x35 fix on cmd 0x21)
; and joins the parser tail used by every cmd handler.
;
; Without ACK suppression, the trailing cumulative-XOR byte (often non-
; route, often non-low-nibble) gets parsed by V1.71 CONTROL as data for
; the next frame, drifting the parser state.  Combined with sustained
; Diag-page cadence this drives chain heartbeat loss → reconnect-OERR
; storm → unit hang.
; ---------------------------------------------------------------------------
diag_send_burst_xx:
    movlw       0xBF
    rcall       uart_tx_byte_blocking
    movf        i2c_coeff_3, W, ACCESS
    rcall       uart_tx_byte_blocking
    movf        POSTINC0, W, ACCESS
    andlw       0x0F                        ; chain-forwarder safe (data < 0x80)
    rcall       uart_tx_byte_blocking
    incf        i2c_coeff_3, F, ACCESS
    movf        ram_0x004, W, ACCESS
    cpfseq      i2c_coeff_3, ACCESS
    bra         diag_send_burst_xx
    bcf         active_flags, 6, ACCESS     ; suppress cmd-XOR ACK echo
    goto        flow_main_uart_service_1be6_1e6c

; ---------------------------------------------------------------------------
; Volume DSP Write (Fix B + B' + recovery)
; ---------------------------------------------------------------------------
volume_dsp_write:
    movlb       0x0
    bcf         dsp_fault_flags, 2, BANKED  ; clear ACKSTAT latch
    rcall       i2c_tas3108_coeff_write
    btfsc       dsp_fault_flags, 2, BANKED  ; NACKed?
    bra         vol_write_nacked
    ; Success: DSP responded, clear all fault state
    movlb       0x0
    bcf         event_flags, 3, BANKED      ; clear volume dirty
    bsf         event_flags, 7, BANKED      ; boot-complete gate
    rcall       copy_computed_volume_to_logical_volume  ; W02-E07: in range after W01-R01
    bcf         dsp_fault_flags, 6, BANKED  ; clear DSP fault (write worked)
    movlw       0xC7
    andwf       dsp_fault_flags, F, BANKED  ; clear retry counter, preserve bits 7,6
    bra         send_dsp_fault_status
vol_write_nacked:
    movlw       0x08
    addwf       dsp_fault_flags, F, BANKED  ; bump retry [5:3]
    movf        dsp_fault_flags, W, BANKED
    andlw       0x38
    sublw       0x28                        ; 5 retries?
    bc          vol_retry_ok
    ; Exhausted: bus-clear + ping only if bus is idle (PEN not pending).
    ; If PEN stuck from fault model, skip I2C recovery to avoid corruption.
    btfsc       SSPCON2, 2, ACCESS          ; PEN pending?
    bra         vol_exhausted_skip_i2c
    diag_inc_sat diag_r                      ; V3.2 Layer 5: count recovery branch entry
    rcall       i2c_bus_clear
    rcall       dsp_ping
vol_exhausted_skip_i2c:
    movlb       0x0                          ; macro / dsp_ping may leave BSR != 0
    btfsc       dsp_fault_flags, 6, BANKED  ; V3.2 Layer 5: skip diag_d if already SET (no transition)
    bra         vol_diag_d_skip
    diag_inc_sat diag_d                      ; (executed only on 0→1 transition)
vol_diag_d_skip:
    movlb       0x0                          ; restore BSR for the existing bsf line
    bsf         dsp_fault_flags, 6, BANKED  ; flag DSP fault
    rcall       send_dsp_fault_status
    movlb       0x0
    bcf         event_flags, 3, BANKED
    movlw       0xC7
    andwf       dsp_fault_flags, F, BANKED  ; clear retry, preserve bit6 (DSP fault)
    return      0
vol_retry_ok:
    return      0                           ; dirty bit stays: main loop retries

; ---------------------------------------------------------------------------
; Async Preset APPLY Helpers (V3.2 only)
; Notes   : Keep legacy main_i2c_service_381c contract untouched.
;           Return with C=0 on success, C=1 on bounded START/STOP timeout.
; ---------------------------------------------------------------------------
preset_job_apply_i2c_recover:
    movlw       0x80                        ; restore stock SSPSTAT SMP state
    movwf       ram_0x003, ACCESS
    movlw       0x08                        ; SSPM master bits (SSPEN re-set in helper)
    rcall       mssp_hard_reset
    rcall       i2c_bus_clear
    movlb       0x0                         ; dsp_ping touches BANKED fault flags
    rcall       dsp_ping
    bsf         STATUS, 0, ACCESS           ; C=1: caller retries same table entry
    return      0

preset_job_apply_i2c_entry:
    movff       ram_0x013, ram_0x003
    movff       ram_0x014, ram_0x004
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    clrf        ram_0x008, ACCESS
    movlw       0x04
    movwf       ram_0x007, ACCESS
    call        flash_read_fsr2_0017, 0x0   ; W05-E04: shared preamble helper
    movff       ram_0x018, ram_0x02F
    movff       ram_0x019, ram_0x031
    movlw       0x19
    subwf       ram_0x031, W, ACCESS
    bc          preset_job_apply_i2c_done
    movlw       0x04
    addwf       ram_0x013, W, ACCESS
    movwf       ram_0x015, ACCESS
    movlw       0x00
    addwfc      ram_0x014, W, ACCESS
    movwf       ram_0x016, ACCESS
    movff       ram_0x015, ram_0x003
    movff       ram_0x016, ram_0x004
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    movff       ram_0x031, ram_0x007
    clrf        ram_0x008, ACCESS
    call        flash_read_fsr2_0017, 0x0   ; W05-E04: shared preamble helper
    bsf         SSPCON2, 0, ACCESS
    rcall       wait_sen_bounded
    bc          preset_job_apply_i2c_timeout
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movf        ram_0x02F, W, ACCESS
    call        i2c_byte_tx, 0x0
    clrf        ram_0x030, ACCESS
    bra         preset_job_apply_i2c_loop_check
preset_job_apply_i2c_loop:
    movf        ram_0x030, W, ACCESS
    addlw       0x17
    rcall       fsr2_page0_read_w                    ; W04-E03
    call        i2c_byte_tx, 0x0
    incf        ram_0x030, F, ACCESS
preset_job_apply_i2c_loop_check:
    movf        ram_0x031, W, ACCESS
    subwf       ram_0x030, W, ACCESS
    bnc         preset_job_apply_i2c_loop
    bsf         SSPCON2, 2, ACCESS
    rcall       wait_pen_bounded
    bc          preset_job_apply_i2c_timeout
preset_job_apply_i2c_done:
    bcf         STATUS, 0, ACCESS           ; C=0: success / benign no-op
    return      0
preset_job_apply_i2c_timeout:
    bra         preset_job_apply_i2c_recover

; ---------------------------------------------------------------------------
; Preset Select Handler (V3.2 non-blocking — cmd=0x20)
; Parser entry: record target preset and start/coalesce the async preset job.
; Actual work is done by preset_job_service from the main loop.
;
; USB filename-xact gate (V3.2 cleanup): when filename_dirty_flags.bit6 is
; set, a USB cmd 0x03 filename WRITE has already updated RAM at
; preset_filename_ram_base but the host's force_persist has not yet
; flushed RAM to EEPROM.  In that window, advancing the state machine
; would have the HOLDING -> APPLY transition call preset_load_filename,
; which OVERWRITES the host's just-written RAM with the incoming
; preset's stored filename -- silently dropping the host's data.  Gate
; the state-machine entry on bit6 so the target is recorded but no
; switch fires until main_core_service_265c clears bit6 after persist.
; The next CONTROL broadcast (or any subsequent preset_select_handler
; entry) past the cleared gate will pick up the deferred target.
; ---------------------------------------------------------------------------
preset_select_handler:
    movlb       0x0
    ; V3.2 USB-xact gate: drop broadcast entirely while host's filename
    ; write is in flight (bit6 set).  Target NOT stored -- the next
    ; CONTROL full_sync_burst step 6 broadcast (within ~6 sec) will
    ; retry once the gate clears.  2-instruction gate; we share the
    ; ``movlb 0x0`` already at the top of the handler.
    btfsc       filename_dirty_flags, 6, BANKED
    bra         preset_select_handler_done
    movf        current_cmd_data, W, BANKED ; data byte: 0=A, 1=B
    andlw       0x01
    movlb       0x2
    movwf       preset_job_target, BANKED   ; store requested preset
    ; If a job is already active, the target update is enough (coalesce)
    movf        preset_job_state, W, BANKED
    bnz         preset_select_handler_done
    ; Compare target with current preset
    movf        preset_job_target, W, BANKED
    btfsc       active_flags, 2, ACCESS     ; current preset B?
    xorlw       0x01                        ; invert for comparison
    bz          preset_select_handler_done  ; no change needed
    ; Start new job
    movlw       0x01                        ; PENDING state
    movwf       preset_job_state, BANKED
    clrf        preset_job_flags, BANKED
    btfsc       active_flags, 4, ACCESS     ; user already muted?
    bsf         preset_job_flags, 1, BANKED ; remember user mute desire
preset_select_handler_done:
    goto        flow_main_uart_service_1be6_1e6c

; --- Persist dirty filename to EEPROM (outgoing preset slot) ---
preset_persist_filename:
    movlw       preset_filename_eeprom_a
    btfsc       active_flags, 2, ACCESS
    movlw       preset_filename_eeprom_b
    movwf       ram_0x007, ACCESS
    clrf        ram_0x008, ACCESS
    lfsr        FSR2, preset_filename_ram_base
    movlw       preset_filename_len
    movwf       ram_0x00A, ACCESS
preset_pf_lp:
    movff       POSTINC2, ram_0x009
    rcall       main_flash_service_46de
    incf        ram_0x007, F, ACCESS
    decfsz      ram_0x00A, F, ACCESS
    bra         preset_pf_lp
    bcf         filename_dirty_flags, 5, BANKED
    return      0

; --- Load filename from EEPROM (incoming preset slot) ---
preset_load_filename:
    movlw       preset_filename_eeprom_a
    btfsc       active_flags, 2, ACCESS
    movlw       preset_filename_eeprom_b
    movwf       ram_0x003, ACCESS
    clrf        ram_0x004, ACCESS
    lfsr        FSR2, preset_filename_ram_base
    movlw       preset_filename_len
    movwf       ram_0x00A, ACCESS
preset_lf_lp:
    rcall       eeprom_read_byte
    movwf       POSTINC2
    incf        ram_0x003, F, ACCESS
    decfsz      ram_0x00A, F, ACCESS
    bra         preset_lf_lp
    return      0

; --- Force-mute DSP output ---
preset_force_mute:
    movlb       0x0
    bsf         active_flags, 4, ACCESS
    bsf         active_flags, 5, ACCESS
    bcf         event_flags, 5, BANKED
    bra         clrf_i2c_coeff_0123_and_write   ; W03-E02: tail-call (helper falls through to i2c_tas3108_coeff_write whose return chains back to caller of preset_force_mute)

; ---------------------------------------------------------------------------
; Preset Job State Machine (V3.2: async delayed preset switching)
; Called once per main-loop pass from periodic_service_loop.
; States: 0=IDLE, 1=PENDING, 2=HOLDING, 3=APPLY, 4=COMMIT
; ---------------------------------------------------------------------------
preset_job_service:
    movlb       0x2
    movf        preset_job_state, W, BANKED
    bz          preset_job_ret              ; IDLE — nothing to do

    ; Cancel on standby shutdown or reconnect
    btfss       active_flags, 3, ACCESS     ; active flag clear → standby
    bra         preset_job_cancel
    btfsc       active_flags, 7, ACCESS     ; reconnect pending
    bra         preset_job_cancel

    ; Dispatch by state
    movlb       0x2
    movf        preset_job_state, W, BANKED
    xorlw       0x01
    bz          preset_job_pending          ; state 1
    xorlw       0x03                        ; cumulative 0x02
    bz          preset_job_holding          ; state 2
    xorlw       0x01                        ; cumulative 0x03
    bz          preset_job_apply            ; state 3
    xorlw       0x07                        ; cumulative 0x04
    bz          preset_job_commit           ; state 4
    bra         preset_job_cancel           ; unknown → cancel

preset_job_ret:
    return      0

; --- PENDING (1): persist filename, force mute, configure hold timer ---
preset_job_pending:
    ; Persist dirty filename for outgoing preset
    movlb       0x0
    btfsc       filename_dirty_flags, 5, BANKED
    rcall       preset_persist_filename

    ; Force mute if user is not already muted
    movlb       0x2
    btfsc       active_flags, 4, ACCESS     ; already muted?
    bra         preset_job_pending_no_mute
    bsf         preset_job_flags, 0, BANKED ; flag: we forced mute
    rcall       preset_force_mute
    bra         preset_job_pending_timer

preset_job_pending_no_mute:
    bcf         preset_job_flags, 0, BANKED ; we did not force mute

preset_job_pending_timer:
    ; Start ISR-based Timer3 countdown (150 ticks, ~150 ms)
    ; The Timer3 ISR decrements ram_0x08C:08D on each overflow;
    ; HOLDING polls that pair for zero.
    clrf        ram_0x004, ACCESS
    movlw       0x96                        ; 150 decimal
    movwf       ram_0x003, ACCESS
    rcall       main_timer_service_477a

    ; Advance to HOLDING
    movlb       0x2
    movlw       0x02
    movwf       preset_job_state, BANKED
    return      0

; --- HOLDING (2): non-blocking timer countdown, coalescing window ---
preset_job_holding:
    ; Check if the ISR-driven Timer3 countdown has reached zero
    movlb       0x0
    movf        preset_hold_timer_hi, W, BANKED
    iorwf       preset_hold_timer_lo, W, BANKED
    bnz         preset_job_holding_wait     ; still counting

    ; After coalescing, check if target still differs from current
    movlb       0x2
    movf        preset_job_target, W, BANKED
    btfsc       active_flags, 2, ACCESS     ; current preset B?
    xorlw       0x01
    bz          preset_job_cancel_unmute    ; coalesced back → cancel

    ; Toggle preset bit
    btg         active_flags, 2, ACCESS
    ; Load incoming preset filename from EEPROM
    rcall       preset_load_filename
    ; Set cmd03 dirty flag for I2C parameter refresh
    movlb       0x0
    bsf         event_flags, 0, BANKED

    ; Initialize table-apply state
    ; Always seed the STOCK-aligned logical preset window at 0x5600.
    ; flash_read remaps that window to 0x4C00..0x55FF automatically when
    ; active_flags.bit2 says preset B is now active, so callers never seed
    ; a physical 0x4Cxx base directly.
    movlb       0x2
    clrf        preset_job_index, BANKED
    clrf        preset_job_tbl_lo, BANKED
    movlw       0x56
    movwf       preset_job_tbl_hi, BANKED

    ; Advance to APPLY
    movlw       0x03
    movwf       preset_job_state, BANKED
    return      0

preset_job_holding_wait:
    return      0

; --- APPLY (3): one I2C preset-table entry per main-loop pass ---
preset_job_apply:
    movlb       0x2
    movlw       0x60                        ; 96 regular entries
    cpfslt      preset_job_index, BANKED    ; skip if index < 96
    bra         preset_job_apply_final      ; index >= 96 → final entry

    ; Apply regular entry from tracked address
    movff       preset_job_tbl_lo, ram_0x013
    movff       preset_job_tbl_hi, ram_0x014
    rcall       preset_job_apply_i2c_entry
    bc          preset_job_apply_retry      ; timeout: retry same entry next pass

    ; Advance address by 0x18 and increment index
    movlb       0x2
    movlw       0x18
    addwf       preset_job_tbl_lo, F, BANKED
    movlw       0x00
    addwfc      preset_job_tbl_hi, F, BANKED
    incf        preset_job_index, F, BANKED
    return      0

preset_job_apply_retry:
    movlb       0x2
    return      0

preset_job_apply_final:
    ; Final logical entry at 0x5F00 (flash_read remaps to 0x5500 for preset B).
    clrf        ram_0x013, ACCESS
    movlw       0x5F
    movwf       ram_0x014, ACCESS
    rcall       preset_job_apply_i2c_entry
    bc          preset_job_apply_retry      ; timeout: stay in APPLY, keep final entry pending

    ; Advance to COMMIT
    movlb       0x2
    movlw       0x04
    movwf       preset_job_state, BANKED
    return      0

; --- COMMIT (4): finalize preset switch, restore volume if appropriate ---
preset_job_commit:
    movlb       0x2
    btfss       preset_job_flags, 0, BANKED ; did we force mute?
    bra         preset_job_commit_idle      ; no → leave mute as user had it
    btfsc       preset_job_flags, 1, BANKED ; user wants mute?
    bra         preset_job_commit_idle      ; yes → stay muted
    ; Unmute and schedule volume restore
    bcf         active_flags, 4, ACCESS
    bcf         active_flags, 5, ACCESS
    movlb       0x0
    bsf         event_flags, 3, BANKED      ; restore volume on next pass

preset_job_commit_idle:
    bra         preset_job_cancel_done      ; shared tail: state=IDLE+return

; --- Cancel with unmute (coalesced back to same preset) ---
preset_job_cancel_unmute:
    bcf         T3CON, 0, ACCESS            ; stop Timer3
    bcf         PIE2, 1, ACCESS             ; disable Timer3 interrupt
    bcf         PIR2, 1, ACCESS             ; clear TMR3IF
    movlb       0x2
    btfss       preset_job_flags, 0, BANKED ; did we force mute?
    bra         preset_job_cancel_done
    btfsc       preset_job_flags, 1, BANKED ; user wants mute?
    bra         preset_job_cancel_done
    bcf         active_flags, 4, ACCESS
    bcf         active_flags, 5, ACCESS
    movlb       0x0
    bsf         event_flags, 3, BANKED      ; restore volume
    bra         preset_job_cancel_done

; --- Cancel (standby/reconnect): clear state, don't touch mute ---
preset_job_cancel:
    bcf         T3CON, 0, ACCESS            ; stop Timer3
    bcf         PIE2, 1, ACCESS             ; disable Timer3 interrupt
    bcf         PIR2, 1, ACCESS             ; clear TMR3IF
    ; Clear forced-mute flags so reconnect/standby path is not confused
    movlb       0x2
    btfss       preset_job_flags, 0, BANKED ; did we force mute?
    bra         preset_job_cancel_done
    bcf         active_flags, 5, ACCESS     ; clear forced-mute shadow
    btfsc       preset_job_flags, 1, BANKED ; user wanted mute?
    bra         preset_job_cancel_done      ; yes → leave bit4
    bcf         active_flags, 4, ACCESS     ; clear our force-mute in bit4

preset_job_cancel_done:
    movlb       0x2
    clrf        preset_job_state, BANKED
    return      0

; ---------------------------------------------------------------------------
; HID Diagnostic Memory Read (cmd=0x43)
; Request : ram_0x11B=region (0=flash,1=eeprom), 0x11C/0x11D=addr, 0x11E=len
; Response: 0x15A=cmd, 0x15B=status, 0x15C=len, 0x15D..=data (max 61 bytes)
; ---------------------------------------------------------------------------
hid_cmd_diag_memread:
    movlb       0x1
    lfsr        FSR2, 0x015A
    movlw       0x43
    movwf       POSTINC2, ACCESS
    clrf        POSTINC2, ACCESS
    movf        ram_0x11E, W, BANKED
    movwf       POSTINC2, ACCESS
    bz          hid_cmd_diag_memread_bad_len
    movlw       0x3D
    cpfsgt      ram_0x11E, BANKED
    bra         hid_cmd_diag_memread_len_ok
hid_cmd_diag_memread_bad_len:
    movlw       0x02
    bra         hid_cmd_diag_memread_fail
hid_cmd_diag_memread_len_ok:
    movf        ram_0x11B, W, BANKED
    bz          hid_cmd_diag_memread_flash
    xorlw       0x01
    bz          hid_cmd_diag_memread_eeprom
    movlw       0x01
    bra         hid_cmd_diag_memread_fail
hid_cmd_diag_memread_flash:
    movff       ram_0x11C, ram_0x003
    movff       ram_0x11D, ram_0x004
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    movff       ram_0x11E, ram_0x007
    clrf        ram_0x008, ACCESS
    movlw       0x5D
    movwf       ram_0x009, ACCESS
    movlw       0x01
    movwf       ram_0x00A, ACCESS
    call        flash_read, 0x0
    goto        flow_hid_command_dispatch_15aa
hid_cmd_diag_memread_eeprom:
    movf        ram_0x11C, W, BANKED
    movwf       ram_0x003, ACCESS
    clrf        ram_0x004, ACCESS
    movf        ram_0x11E, W, BANKED
    movwf       ram_0x00A, ACCESS
    lfsr        FSR2, 0x015D
hid_cmd_diag_memread_eeprom_lp:
    rcall       eeprom_read_byte
    movwf       POSTINC2, ACCESS
    incf        ram_0x003, F, ACCESS
    decfsz      ram_0x00A, F, ACCESS
    bra         hid_cmd_diag_memread_eeprom_lp
    goto        flow_hid_command_dispatch_15aa
hid_cmd_diag_memread_fail:
    movwf       ram_0x05B, BANKED
    goto        flow_hid_command_dispatch_15aa

; ---------------------------------------------------------------------------
; HID Diagnostic Snapshot (cmd=0x44, V3.2 rev 0x37 Tier-1)
; ---------------------------------------------------------------------------
; Returns a structured 64-byte HID IN report carrying the full diag block
; (7 runtime counters + 4 reset-cause flags) plus a fixed trailer.  Read-
; only and idempotent: no chain traffic, no side effects, no counter
; mutation.  The host can poll this freely without disturbing the chain
; cadence or LCD rendering.
;
; Request layout (64-byte HID OUT, staged at 0x011A onward):
;   [0]    = 0x44   cmd byte
;   [1]    = 0x00   subcmd reserved (ignored — handler does not check)
;   [2..63]= 0x00   unused
;
; Response layout (64-byte HID IN at 0x015A; offsets relative to FSR2 base):
;   [0]    = 0x44   cmd echo
;   [1]    = 0x00   status (always OK for this read-only snapshot)
;   [2]    = 0x0E   payload length = 14 bytes (11 cells + 3 trailer)
;   [3..9] = 7 runtime counters: I, D, S, B, R, A, P (raw byte; saturates 0..0x0F)
;   [10..13] = 4 reset-cause flags: O, V, W, X (each 0 or 1; exactly one = 1)
;   [14]   = 0x03   firmware flag (V3.x)
;   [15]   = 0x37   firmware revision (this spec defines rev 0x37)
;   [16]   = 0xFF   role (LEFT/RIGHT/unknown — host derives from HID path)
;   [17..63] = 0xFF padding
;
; The role byte is a placeholder (0xFF = unknown) in this firmware
; because MAIN does not have a hardware-discoverable side identity;
; both LEFT and RIGHT MAINs run the identical hex.  The host CLI
; (scripts/dlcp_diag.py) maps HID device path -> role using its own
; configuration.  Future firmware revs could populate this byte from
; an EEPROM-stored side marker if site automation needs in-firmware
; identity.
;
; See V32_DIAG_TIER1_SPEC.md §"HID protocol extension — new cmd 0x44".
; ---------------------------------------------------------------------------
hid_cmd_diag_snapshot:
    lfsr        FSR2, 0x015A                ; HID IN buffer base
    movlw       0x44                        ; [0] cmd echo
    movwf       POSTINC2, ACCESS
    clrf        POSTINC2, ACCESS            ; [1] status = OK
    movlw       0x0B                        ; [2] payload length = 11 cells
    movwf       POSTINC2, ACCESS
    ; [3..9] = 7 runtime counters from diag_i..diag_p (0x2E5..0x2EB).
    ; FSR0 walks the diag block; FSR2 walks the HID IN buffer.
    lfsr        FSR0, diag_i                ; 0x2E5
    movlw       0x07
    movwf       i2c_coeff_3, ACCESS
hid_diag_snap_cnt:
    movf        POSTINC0, W, ACCESS
    movwf       POSTINC2, ACCESS
    decfsz      i2c_coeff_3, F, ACCESS
    bra         hid_diag_snap_cnt
    ; FSR0 now sits on diag_ra1_prev (0x2EC); skip past it to the
    ; reset-cause flag block at 0x2ED.
    incf        FSR0L, F, ACCESS
    ; [10..13] = 4 reset-cause flags from diag_reset_por..diag_reset_sw.
    movlw       0x04
    movwf       i2c_coeff_3, ACCESS
hid_diag_snap_flag:
    movf        POSTINC0, W, ACCESS
    movwf       POSTINC2, ACCESS
    decfsz      i2c_coeff_3, F, ACCESS
    bra         hid_diag_snap_flag
    ; [14..63] = padding — host sees length byte at [2]=0x0B so it
    ; stops parsing at offset 13.  Firmware version metadata is
    ; available via the existing cmd 0x06 probe (see hid_dispatch);
    ; cmd 0x44 stays focused on the diag block to keep the handler
    ; small enough to fit before the DSP preset tables at 0x4C00.
    goto        flow_hid_command_dispatch_15aa

; ---------------------------------------------------------------------------
; DSP Preset Table B (clone of Preset A)
; ---------------------------------------------------------------------------
    org 0x4C00
preset_table_b:
    dw  0xC801, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3701, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3801, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3901, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3A01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3B01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3C01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3D01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3E01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3F01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4001, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4101, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4201, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4301, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4401, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4501, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xC901, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4601, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4701, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4801, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4901, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4A01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4B01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4C01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4D01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4E01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4F01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5001, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5101, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5201, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5301, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5401, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCA01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5501, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5601, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5701, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5801, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5901, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5A01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5B01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5C01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5D01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5E01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5F01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6001, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6101, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6201, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6301, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCB01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6401, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6501, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6601, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6701, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6801, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6901, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6A01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6B01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6C01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6D01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6E01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6F01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7001, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7101, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7201, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCC01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7301, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7401, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7501, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7601, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7701, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7801, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7901, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7A01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7B01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7C01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7D01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7E01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7F01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8001, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8101, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCD01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8201, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8301, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8401, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8501, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8601, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8701, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8801, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8901, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8A01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8B01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8C01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8D01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8E01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8F01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x9001, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xD401, 0x0004, 0x0000, 0x0100, 0x3101, 0x0010, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x3101, 0x0010
    dw  0x8000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3201, 0x0010, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x3201, 0x0010, 0x8000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3301, 0x0010, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x3301, 0x0010
    dw  0x8000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3401, 0x0010, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x3401, 0x0010, 0x8000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3501, 0x0010, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x3501, 0x0010
    dw  0x8000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3601, 0x0010, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x3601, 0x0010, 0x8000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF

; ---------------------------------------------------------------------------
; Erased Flash Padding to Preset A
; ---------------------------------------------------------------------------
    fill 0xFFFF, (0x5600 - $) / 2

; ---------------------------------------------------------------------------
; DSP Preset Table A (stock, pinned to flash ceiling)
; ---------------------------------------------------------------------------
    org 0x5600
preset_table_a:
    dw  0xC801, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3701, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3801, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3901, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3A01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3B01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3C01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3D01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3E01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3F01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4001, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4101, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4201, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4301, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4401, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4501, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xC901, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4601, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4701, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4801, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4901, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4A01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4B01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4C01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4D01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x4E01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x4F01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5001, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5101, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5201, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5301, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5401, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCA01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5501, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5601, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5701, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5801, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5901, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5A01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5B01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5C01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5D01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x5E01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x5F01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6001, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6101, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6201, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6301, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCB01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6401, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6501, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6601, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6701, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6801, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6901, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6A01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6B01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6C01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6D01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x6E01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x6F01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7001, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7101, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7201, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCC01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7301, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7401, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7501, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7601, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7701, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7801, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7901, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7A01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7B01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7C01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7D01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x7E01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x7F01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8001, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8101, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xCD01, 0x0004, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8201, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8301, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8401, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8501, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8601, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8701, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8801, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8901, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8A01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8B01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8C01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8D01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x8E01, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x8F01, 0x0014, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x9001, 0x0014, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0xD401, 0x0004, 0x0000, 0x0100, 0x3101, 0x0010, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x3101, 0x0010
    dw  0x8000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3201, 0x0010, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x3201, 0x0010, 0x8000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3301, 0x0010, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x3301, 0x0010
    dw  0x8000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3401, 0x0010, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x3401, 0x0010, 0x8000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x3501, 0x0010, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x3501, 0x0010
    dw  0x8000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x3601, 0x0010, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x3601, 0x0010, 0x8000, 0x0000, 0x0000, 0x0000
    dw  0x0000, 0x0000, 0x0000, 0x0000, 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF

; ---------------------------------------------------------------------------
; EEPROM Data (V3.2: version updated at offset 0x82)
; ---------------------------------------------------------------------------
    org 0xF00000
eeprom_data:
    db  0xFF, 0xFF, 0xFF, 0xA0, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 0x01, 0x03, 0x04, 0x01  ; ................
    db  0x00, 0x00, 0x00, 0x00, 0x01, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0x03, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0x03, 0x02, 0x4D, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; V3.2 Tier-1 lineage: no-pop + reset-cause classification + cmd 0x22 reset-flags burst + HID cmd 0x44 diag snapshot; third byte is the monotonic release revision
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x02  ; ................

    END
