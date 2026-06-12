; ===========================================================================
;                    Hypex DLCP — MAIN firmware V3.4
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
;                     (V3.4: V3.2 Tier-1 diagnostics + V3.3/V3.4
;                      app-resident identity and preset filename protocol)
;
; Build      : gpasm -p18f2455 -o DLCP_Firmware_V3.4.hex dlcp_main_v34.asm
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
;   V3.2   V3.1 + asynchronous preset job state machine, bounded START/STOP
;          waits in apply path, mute/preset coalescing, standby/reconnect
;          cancellation, diagnostics counters, and reset classification.
;   V3.3   V3.2 + app-resident MAIN identity reply for CONTROL diagnostics.
; * V3.4   THIS FILE — V3.3 refactoring branch with explicit runtime
;          lifecycle clears and preset filename LCD/chain lifecycle tests.
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

; Bank-2 recovery latch outside the cmd 0x44 visible diag block.  Bit0 means
; a previous MSSP timeout needs one bus-clear at the next clean I2C entry.
; 0x2F1 is main_rx_frame_gap_timeout; use the reserved upper-bank slot at 0x2F2.
i2c_recover_flags       EQU  0x2F2

; SRC4382 Auto Detect source-loss debounce.  0 = no pending loss sample.
; Counts consecutive RXCKR=0 monitor samples while an Auto Detect route is
; selected; V3.4 rev 0x88 requires SIX consecutive misses (~2-3 s) before
; clearing the route and resuming the scan (RXCKR is a rate classifier
; that transiently reads 0 while audio passes).
src4382_loss_debounce   EQU  0x2F3

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
                                       ; filename_rev (0x2F8 in
                                       ; dlcp_main_ram.inc) is bumped by
                                       ; RAM/EEPROM filename writers so
                                       ; cmd 0x26 never finalizes torn data.
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
; stock_094.bit5 is the V3.4 user-mute latch. active_flags.bit4 is the
; effective mute target and can also be set by SRC status or preset force-mute;
; this latch distinguishes user intent from automatic mute ownership.
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
; Size note (V3.3): the clamp/increment body lives in a shared helper.
; The macro still asserts BSR=2 at each call site (documented side
; effect) and deliberately clobbers FSR0 to point at the target cell.
;
; Usage:    diag_inc_sat   diag_i
diag_inc_sat MACRO counter
    movlb   0x02                        ; V3.2 Layer 5 diag block in BANK 2
    lfsr    FSR0, counter
    rcall   diag_inc_sat_fsr0
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
    bra         flow_app_entry_1014                 ; 0x1000 user reset trampoline
    dw          0xFFFF
    dw          0xFFFF
    movff       FSR2L, isr_save_fsr2l_b0_phys               ; 0x1008 ISR shadow vector entry
    movff       FSR2H, isr_save_fsr2h_b0_phys
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
    movff       WREG, i2c_coeff_2_b0_phys
    lfsr        FSR2, stock_1ED_b1_phys
    lfsr        FSR1, stock_04D_b0_phys
    movlw       0x07
flow_hid_command_dispatch_10ba:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         flow_hid_command_dispatch_10ba
    movf        i2c_coeff_2_acc, W, ACCESS
    xorlw       0x42
    bnz         flow_hid_command_dispatch_10ca
    bra         hid_cmd_xor_dispatch
flow_hid_command_dispatch_10ca:
    movlb       0x0
    clrf        stock_0CB_b0, BANKED
    bra         hid_cmd_xor_dispatch
flow_hid_command_dispatch_10d0:
    movff       stock_11B_b1_phys, stock_097_b0_phys
    movlb       0x0
    movf        stock_097_b0, W, BANKED
    xorlw       0x09
    bnz         flow_hid_command_dispatch_1104
    movlw       0x02
    movwf       i2c_coeff_3_acc, ACCESS
flow_hid_command_dispatch_10e0:
    rcall       main_core_service_15b0
    movf        INDF2, W, ACCESS
    bz          flow_hid_command_dispatch_10fa
    rcall       main_core_service_15b0
    movlw       0xBE
    addwf       i2c_coeff_3_acc, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x02
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         flow_hid_command_dispatch_10fc
flow_hid_command_dispatch_10fa:
    rcall       main_core_service_15be
flow_hid_command_dispatch_10fc:
    incf        i2c_coeff_3_acc, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3_acc, ACCESS
    bra         flow_hid_command_dispatch_10e0
flow_hid_command_dispatch_1104:
    movlb       0x0
    movf        stock_097_b0, W, BANKED
    xorlw       0x0A
    bnz         flow_hid_command_dispatch_111a
    movlw       0x02
    movwf       i2c_coeff_3_acc, ACCESS
flow_hid_command_dispatch_1110:
    rcall       main_core_service_15be
    incf        i2c_coeff_3_acc, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3_acc, ACCESS
    bra         flow_hid_command_dispatch_1110
flow_hid_command_dispatch_111a:
    movlw       0x03
    movlb       0x0
    movwf       stock_0C1_b0, BANKED
    movff       stock_11B_b1_phys, stock_0C2_b0_phys
    movf        stock_097_b0, W, BANKED
    xorlw       0x09
    bz          flow_hid_command_dispatch_111a_dirty
    movf        stock_097_b0, W, BANKED
    xorlw       0x0A
    bnz         flow_hid_command_dispatch_1126
flow_hid_command_dispatch_111a_dirty:
    bsf         filename_dirty_flags_b0, 5, BANKED            ; filename RAM dirty
    bsf         filename_dirty_flags_b0, 6, BANKED            ; V3.2: gate USB filename xact
                                                ; until force_persist clears
                                                ; both bits.  preset_select_
                                                ; handler defers state-machine
                                                ; entry while bit6 set so a
                                                ; concurrent CONTROL B0/20/x
                                                ; broadcast can't race the
                                                ; host's force_persist.
    movlb       0x02
    incf        filename_rev_b2, F, BANKED         ; USB filename write touched RAM
    incf        filename_rev_b2, F, BANKED         ; leave seqlock even/stable
    movlb       0x00
flow_hid_command_dispatch_1126:
    call        main_timer_service_48a6, 0x0
flow_hid_command_dispatch_112a:
    call        main_core_service_492e, 0x0
flow_hid_command_dispatch_112e:
    call        main_core_service_2328, 0x0
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1134:
    movlb       0x1
    decf        stock_11B_b1, W, BANKED
    bnz         flow_hid_command_dispatch_116a
    movff       stock_11C_b1_phys, stock_0B7_b0_phys
    bra         flow_hid_command_dispatch_115c
flow_hid_command_dispatch_1140:
    movlw       0x04
    movwf       stock_0C1_b0, BANKED
    movlw       0x01
    movwf       stock_0C2_b0, BANKED
    bra         flow_hid_command_dispatch_112a
flow_hid_command_dispatch_114a:
    movff       stock_11D_b1_phys, stock_0B8_b0_phys
    movlw       0x04
    movwf       stock_0C1_b0, BANKED
    movlw       0x01
    movwf       stock_0C2_b0, BANKED
    bsf         dsp_fault_flags_b0, 0, BANKED
    bsf         stock_094_b0, 4, BANKED
    bra         flow_hid_command_dispatch_112a
flow_hid_command_dispatch_115c:
    movlb       0x0
    movf        stock_0B7_b0, W, BANKED
    xorlw       0x01
    bz          flow_hid_command_dispatch_1140
    xorlw       0x03
    bz          flow_hid_command_dispatch_114a
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_116a:
    movf        stock_11B_b1, W, BANKED
    xorlw       0x02
    bz          flow_hid_command_dispatch_1172
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1172:
    movff       stock_11E_b1_phys, stock_0B5_b0_phys
    movlw       0x04
    movlb       0x0
    movwf       stock_0C1_b0, BANKED
    movlw       0x02
    movwf       stock_0C2_b0, BANKED
    movf        stock_0B5_b0, W, BANKED
    xorlw       0x06
    bnz         flow_hid_command_dispatch_11c0
    movlw       0x05
    movwf       i2c_coeff_3_acc, ACCESS
flow_hid_command_dispatch_118a:
    rcall       main_core_service_15b0
    movf        INDF2, W, ACCESS
    bz          flow_hid_command_dispatch_11a4
    rcall       main_core_service_15b0
    movlw       0xFB
    addwf       i2c_coeff_3_acc, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x00
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         flow_hid_command_dispatch_11b2
flow_hid_command_dispatch_11a4:
    movlw       0xFB
    addwf       i2c_coeff_3_acc, W, ACCESS
    call        setup_fsr2_page_1, 0x0
    setf        INDF2, ACCESS
flow_hid_command_dispatch_11b2:
    incf        i2c_coeff_3_acc, F, ACCESS
    movlw       0x13
    cpfsgt      i2c_coeff_3_acc, ACCESS
    bra         flow_hid_command_dispatch_118a
    movlb       0x0
    bsf         filename_dirty_flags_b0, 4, BANKED
    bra         flow_hid_command_dispatch_1126
flow_hid_command_dispatch_11c0:
    movf        stock_0B5_b0, W, BANKED
    xorlw       0x05
    bz          flow_hid_command_dispatch_112a
    movf        stock_0B5_b0, W, BANKED
    xorlw       0x07
    bz          flow_hid_command_dispatch_112a
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_11ce:
    movff       stock_11B_b1_phys, input_select_b0_phys
    movff       stock_11F_b1_phys, computed_volume_3_b0_phys
    movff       stock_120_b1_phys, computed_volume_2_b0_phys
    movff       stock_121_b1_phys, computed_volume_1_b0_phys
    movff       stock_122_b1_phys, computed_volume_b0_phys
    movlb       0x1
    btfsc       stock_123_b1, 0, BANKED
    bra         flow_hid_command_dispatch_11ec
    movlb       0x0
    bcf         stock_094_b0, 5, BANKED
    bcf         active_flags_acc, 4, ACCESS
    bra         flow_hid_command_dispatch_11ee
flow_hid_command_dispatch_11ec:
    movlb       0x0
    bsf         stock_094_b0, 5, BANKED
    bsf         active_flags_acc, 4, ACCESS
flow_hid_command_dispatch_11ee:
    movlb       0x1
    btfsc       stock_124_b1, 0, BANKED
    bra         flow_hid_command_dispatch_11fa
    movlb       0x0
    bcf         stock_0A4_b0, 0, BANKED
    bra         flow_hid_command_dispatch_11fe
flow_hid_command_dispatch_11fa:
    movlb       0x0
    bsf         stock_0A4_b0, 0, BANKED
flow_hid_command_dispatch_11fe:
    movlb       0x1
    btfsc       stock_125_b1, 0, BANKED
    bra         flow_hid_command_dispatch_120a
    movlb       0x0
    bcf         stock_0A4_b0, 1, BANKED
    bra         flow_hid_command_dispatch_120e
flow_hid_command_dispatch_120a:
    movlb       0x0
    bsf         stock_0A4_b0, 1, BANKED
flow_hid_command_dispatch_120e:
    movlb       0x1
    btfsc       stock_126_b1, 0, BANKED
    bra         flow_hid_command_dispatch_121a
    movlb       0x0
    bcf         stock_0A4_b0, 2, BANKED
    bra         flow_hid_command_dispatch_121e
flow_hid_command_dispatch_121a:
    movlb       0x0
    bsf         stock_0A4_b0, 2, BANKED
flow_hid_command_dispatch_121e:
    movlb       0x1
    btfsc       stock_128_b1, 0, BANKED
    bra         flow_hid_command_dispatch_122a
    movlb       0x0
    bcf         stock_0A4_b0, 3, BANKED
    bra         flow_hid_command_dispatch_122e
flow_hid_command_dispatch_122a:
    movlb       0x0
    bsf         stock_0A4_b0, 3, BANKED
flow_hid_command_dispatch_122e:
    movlb       0x1
    btfsc       stock_129_b1, 0, BANKED
    bra         flow_hid_command_dispatch_123a
    movlb       0x0
    bcf         stock_0A4_b0, 4, BANKED
    bra         flow_hid_command_dispatch_123e
flow_hid_command_dispatch_123a:
    movlb       0x0
    bsf         stock_0A4_b0, 4, BANKED
flow_hid_command_dispatch_123e:
    movlb       0x1
    btfsc       stock_12A_b1, 0, BANKED
    bra         flow_hid_command_dispatch_124a
    movlb       0x0
    bcf         stock_0A4_b0, 5, BANKED
    bra         flow_hid_command_dispatch_124e
flow_hid_command_dispatch_124a:
    movlb       0x0
    bsf         stock_0A4_b0, 5, BANKED
flow_hid_command_dispatch_124e:
    movff       stock_12C_b1_phys, stock_060_b0_phys
    movff       stock_12D_b1_phys, stock_061_b0_phys
    movff       stock_12E_b1_phys, stock_062_b0_phys
    movff       stock_12F_b1_phys, stock_063_b0_phys
    movff       stock_130_b1_phys, stock_064_b0_phys
    movff       stock_131_b1_phys, stock_065_b0_phys
    movff       stock_132_b1_phys, stock_05F_b0_phys
    movff       stock_133_b1_phys, stock_09B_b0_phys
    movff       stock_134_b1_phys, stock_09C_b0_phys
    movff       stock_135_b1_phys, stock_09D_b0_phys
    movff       stock_136_b1_phys, stock_09E_b0_phys
    movff       stock_138_b1_phys, stock_0B4_b0_phys
    movf        input_select_mirror_b0, W, BANKED
    xorwf       input_select_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         stock_094_b0, 0, BANKED
    movf        logical_volume_3_b0, W, BANKED
    xorwf       computed_volume_3_b0, W, BANKED
    bnz         flow_hid_command_dispatch_129c
    movf        logical_volume_2_b0, W, BANKED
    xorwf       computed_volume_2_b0, W, BANKED
    bnz         flow_hid_command_dispatch_129c
    movf        logical_volume_1_b0, W, BANKED
    xorwf       computed_volume_1_b0, W, BANKED
    bnz         flow_hid_command_dispatch_129c
    movf        logical_volume_b0, W, BANKED
    xorwf       computed_volume_b0, W, BANKED
flow_hid_command_dispatch_129c:
    bz          flow_hid_command_dispatch_12a2
    bsf         event_flags_b0, 3, BANKED
    bsf         stock_094_b0, 1, BANKED
flow_hid_command_dispatch_12a2:
    movf        stock_0AC_b0, W, BANKED
    xorwf       stock_09B_b0, W, BANKED
    bz          flow_hid_command_dispatch_12ac
    bsf         event_flags_b0, 3, BANKED
    bsf         filename_dirty_flags_b0, 3, BANKED
flow_hid_command_dispatch_12ac:
    movf        stock_0AD_b0, W, BANKED
    xorwf       stock_09C_b0, W, BANKED
    bz          flow_hid_command_dispatch_12b6
    bsf         event_flags_b0, 3, BANKED
    bsf         filename_dirty_flags_b0, 3, BANKED
flow_hid_command_dispatch_12b6:
    movf        stock_0AE_b0, W, BANKED
    xorwf       stock_09D_b0, W, BANKED
    bz          flow_hid_command_dispatch_12c0
    bsf         event_flags_b0, 3, BANKED
    bsf         filename_dirty_flags_b0, 3, BANKED
flow_hid_command_dispatch_12c0:
    movf        stock_0AF_b0, W, BANKED
    xorwf       stock_09E_b0, W, BANKED
    bz          flow_hid_command_dispatch_12ca
    bsf         event_flags_b0, 3, BANKED
    bsf         filename_dirty_flags_b0, 3, BANKED
flow_hid_command_dispatch_12ca:
    movlw       0x01
    btfss       active_flags_acc, 4, ACCESS
    movlw       0x00
    movwf       stock_04C_acc, ACCESS
    movlw       0x01
    btfss       active_flags_acc, 5, ACCESS
    movlw       0x00
    xorwf       stock_04C_acc, F, ACCESS
    bz          flow_hid_command_dispatch_12e0
    bsf         event_flags_b0, 5, BANKED
    bsf         stock_094_b0, 3, BANKED
flow_hid_command_dispatch_12e0:
    movf        stock_0B0_b0, W, BANKED
    xorwf       stock_0A4_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags_b0, 6, BANKED
    movf        stock_0B4_b0, W, BANKED
    xorwf       stock_0B1_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         dsp_fault_flags_b0, 1, BANKED
    movf        stock_060_b0, W, BANKED
    cpfseq      stock_0A5_b0, BANKED
    bra         flow_hid_command_dispatch_1324
    movf        stock_0A6_b0, W, BANKED
    lfsr        FSR2, stock_061_b0_phys
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        stock_0A7_b0, W, BANKED
    lfsr        FSR2, stock_062_b0_phys
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        stock_0A8_b0, W, BANKED
    lfsr        FSR2, stock_063_b0_phys
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        stock_0A9_b0, W, BANKED
    lfsr        FSR2, stock_064_b0_phys
    cpfseq      INDF2, ACCESS
    bra         flow_hid_command_dispatch_1324
    movf        stock_065_b0, W, BANKED
    xorwf       stock_0AA_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
flow_hid_command_dispatch_1324:
    bsf         event_flags_b0, 4, BANKED
    movff       input_select_b0_phys, input_select_mirror_b0_phys
    call        copy_computed_volume_to_logical_volume, 0x0
    btfss       active_flags_acc, 4, ACCESS
    bra         flow_hid_command_dispatch_1342
    bsf         active_flags_acc, 5, ACCESS
    bra         flow_hid_command_dispatch_1344
flow_hid_command_dispatch_1342:
    bcf         active_flags_acc, 5, ACCESS
flow_hid_command_dispatch_1344:
    movff       stock_0A4_b0_phys, stock_0B0_b0_phys
    movff       stock_060_b0_phys, stock_0A5_b0_phys
    movff       stock_061_b0_phys, stock_0A6_b0_phys
    movff       stock_062_b0_phys, stock_0A7_b0_phys
    movff       stock_063_b0_phys, stock_0A8_b0_phys
    movff       stock_064_b0_phys, stock_0A9_b0_phys
    movff       stock_065_b0_phys, stock_0AA_b0_phys
    movff       stock_0B4_b0_phys, stock_0B1_b0_phys
    movff       stock_09B_b0_phys, stock_0AC_b0_phys
    movff       stock_09C_b0_phys, stock_0AD_b0_phys
    movff       stock_09D_b0_phys, stock_0AE_b0_phys
    movff       stock_09E_b0_phys, stock_0AF_b0_phys
flow_hid_command_dispatch_1374:
    movlw       0x05
    bra         flow_hid_command_dispatch_1384
flow_hid_command_dispatch_1378:
    movlb       0x1
    decf        stock_11B_b1, W, BANKED
    bnz         flow_hid_command_dispatch_138a
    call        main_core_service_4942, 0x0
    movlw       0x06
flow_hid_command_dispatch_1384:
    movlb       0x0
    movwf       stock_0C1_b0, BANKED
    bra         flow_hid_command_dispatch_112e
flow_hid_command_dispatch_138a:
    movf        stock_11B_b1, W, BANKED
    xorlw       0x02
    bz          flow_hid_command_dispatch_1392
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1392:
    call        main_core_service_4942, 0x0
    bra         flow_hid_command_dispatch_1374
flow_hid_command_dispatch_1398:
    movlb       0x1
    movf        stock_11B_b1, W, BANKED
    xorlw       0x0F
    btfsc       STATUS, 2, ACCESS
    bsf         active_flags_acc, 7, ACCESS
flow_hid_command_dispatch_13a2:
    movf        i2c_coeff_2_acc, W, ACCESS
    xorlw       0x07
    bnz         flow_hid_command_dispatch_13ba
    movlb       0x1
    tstfsz      stock_11B_b1, BANKED
    bra         flow_hid_command_dispatch_13ba
    movlb       0x0
    clrf        stock_0C5_b0, BANKED
    movlw       0x56
    movwf       stock_083_b0, BANKED
    clrf        stock_082_b0, BANKED
flow_hid_command_dispatch_13ba:
    bcf         RCSTA, 4, ACCESS
    bsf         active_flags_acc, 0, ACCESS
    movlb       0x0
    clrf        rx_frame_position_b0, BANKED
    clrf        rx_ring_wr_b0, BANKED
    clrf        rx_ring_rd_b0, BANKED
    call        main_flash_service_2bb8, 0x0
flow_hid_command_dispatch_13ca:
    movff       i2c_coeff_2_b0_phys, stock_0C1_b0_phys
    bra         flow_hid_command_dispatch_112e
flow_hid_command_dispatch_13d0:
    ; BUG-SETTINGS-01: app cmd 0x40 is the firmware-update handoff,
    ; not a factory reset.  Preserve user EEPROM-backed settings and
    ; only set the bootloader-entry marker below.
    clrf        stock_008_acc, ACCESS
    setf        stock_007_acc, ACCESS
    clrf        stock_009_acc, ACCESS
    call        main_flash_service_46de, 0x0
    goto        flash_entry_quiet_shutdown      ; V3.2+: pop-free reset path
    bra         flow_hid_command_dispatch_15aa
fw_update_init_sequence:
    movlb       0x0
    tstfsz      stock_0CB_b0, BANKED
    bra         flow_hid_command_dispatch_14fc
    clrf        stock_07C_b0, BANKED
    clrf        stock_07D_b0, BANKED
    clrf        stock_080_b0, BANKED
    clrf        stock_081_b0, BANKED
    clrf        stock_086_b0, BANKED
    clrf        stock_087_b0, BANKED
    clrf        stock_084_b0, BANKED
    clrf        stock_085_b0, BANKED
    call        prep_bank1_ram004, 0x0
    movlw       0xC7
    movwf       stock_003_acc, ACCESS
    movlw       0x0A
    movwf       stock_005_acc, ACCESS
    call        ram_block_clear, 0x0
    call        prep_bank1_ram004, 0x0
    movlw       0x9A
    movwf       stock_003_acc, ACCESS
    movlw       0x2D
    movwf       stock_005_acc, ACCESS
    call        ram_block_clear, 0x0
    call        prep_bank1_ram004, 0x0
    movlw       0xD1
    movwf       stock_003_acc, ACCESS
    movlw       0x08
    movwf       stock_005_acc, ACCESS
    call        ram_block_clear, 0x0
    call        factory_reset_status_emit, 0x0
    movlw       0x05
    movwf       stock_006_acc, ACCESS
    movlw       0xDC
    movwf       stock_005_acc, ACCESS
    movlb       0x1
    movlw       0x01
    movwf       stock_008_acc, ACCESS
    movlw       0xD1
    movwf       stock_007_acc, ACCESS
    movlw       0x08
    movwf       stock_009_acc, ACCESS
    call        uart_rx_with_framing, 0x0
    movwf       stock_04C_acc, ACCESS
    movlw       0x05
    subwf       stock_04C_acc, W, ACCESS
    bnc         flow_hid_command_dispatch_14fa
    movlw       0x01
    movwf       stock_0CB_b0, BANKED
    clrf        i2c_coeff_3_acc, ACCESS
flow_hid_command_dispatch_14ce:
    movf        i2c_coeff_3_acc, W, ACCESS
    addlw       0x4D
    call        fsr2_page0_read_w, 0x0               ; W04-E03
    movwf       stock_04C_acc, ACCESS
    movlw       0xD1
    addwf       i2c_coeff_3_acc, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    movf        INDF2, W, ACCESS
    xorwf       stock_04C_acc, W, ACCESS
    bz          flow_hid_command_dispatch_14f0
    movlb       0x0
    clrf        stock_0CB_b0, BANKED
flow_hid_command_dispatch_14f0:
    incf        i2c_coeff_3_acc, F, ACCESS
    movlw       0x05
    cpfsgt      i2c_coeff_3_acc, ACCESS
    bra         flow_hid_command_dispatch_14ce
    bra         flow_hid_command_dispatch_14fc
flow_hid_command_dispatch_14fa:
    clrf        stock_0CB_b0, BANKED
flow_hid_command_dispatch_14fc:
    movlb       0x0
    movf        stock_0CB_b0, W, BANKED
    bnz         flow_hid_command_dispatch_1504
    bra         flow_hid_command_dispatch_13ca
flow_hid_command_dispatch_1504:
    rcall       fw_update_relay
    bra         flow_hid_command_dispatch_13ca
flow_hid_command_dispatch_150a:
    movff       stock_11E_b1_phys, i2c_coeff_1_b0_phys
    movff       stock_11F_b1_phys, i2c_coeff_0_b0_phys
    movff       i2c_coeff_2_b0_phys, stock_0C1_b0_phys
    call        main_core_service_2328, 0x0
    movf        stock_07D_b0, W, BANKED
    xorwf       i2c_coeff_1_acc, W, ACCESS
    bnz         flow_hid_command_dispatch_1524
    movf        stock_07C_b0, W, BANKED
    xorwf       i2c_coeff_0_acc, W, ACCESS
flow_hid_command_dispatch_1524:
    bnz         flow_hid_command_dispatch_1532
    call        main_core_service_4672, 0x0
    movlw       0xAA
    movlb       0x1
    movwf       stock_15C_b1, BANKED
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_1532:
    movlw       0x11
    movlb       0x1
    movwf       stock_15B_b1, BANKED
    movlb       0x0
    clrf        stock_084_b0, BANKED
    clrf        stock_085_b0, BANKED
    clrf        stock_080_b0, BANKED
    clrf        stock_081_b0, BANKED
    clrf        stock_086_b0, BANKED
    clrf        stock_087_b0, BANKED
    clrf        stock_07C_b0, BANKED
    clrf        stock_07D_b0, BANKED
    bra         flow_hid_command_dispatch_15aa
flow_hid_command_dispatch_154c:
    movlb       0x1
    clrf        stock_11A_b1, BANKED
    bra         flow_hid_command_dispatch_15aa
hid_cmd_xor_dispatch:
    movf        i2c_coeff_2_acc, W, ACCESS
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
    clrf        stock_11A_b1, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_15b0
; Address : 0x15B0
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_15b0:
    movlw       0x1A
    addwf       i2c_coeff_3_acc, W, ACCESS
    bra         setup_fsr2_page_1_or_2


; ---------------------------------------------------------------------------
; Function: main_core_service_15be
; Address : 0x15BE
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_15be:
    movlw       0xBE
    addwf       i2c_coeff_3_acc, W, ACCESS
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
    lfsr        FSR2, stock_1E5_b1_phys
    lfsr        FSR1, stock_01D_b0_phys
    movlw       0x08
flow_fw_update_relay_15d8:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         flow_fw_update_relay_15d8
    movlw       0x02
    movwf       stock_049_acc, ACCESS
flow_fw_update_relay_15e4:
    movlw       0x1A
    addwf       stock_049_acc, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    movf        INDF2, W, ACCESS
    movwf       stock_04A_acc, ACCESS
    movlw       0xC0
    movlb       0x0
    subwf       stock_084_b0, W, BANKED
    movlw       0x77
    subwfb      stock_085_b0, W, BANKED
    bc          flow_fw_update_relay_1634
    movff       stock_04A_b0_phys, stock_045_b0_phys
    clrf        stock_048_acc, ACCESS
flow_fw_update_relay_1606:
    btfss       stock_07D_b0, 5, BANKED
    bra         flow_fw_update_relay_1610
    movlw       0x01
    movwf       stock_044_acc, ACCESS
    bra         flow_fw_update_relay_1612
flow_fw_update_relay_1610:
    clrf        stock_044_acc, ACCESS
flow_fw_update_relay_1612:
    bcf         STATUS, 0, ACCESS
    rlcf        stock_07C_b0, F, BANKED
    rlcf        stock_07D_b0, F, BANKED
    btfsc       stock_045_acc, 0, ACCESS
    bsf         stock_07C_b0, 0, BANKED
    bcf         STATUS, 0, ACCESS
    rrcf        stock_045_acc, F, ACCESS
    movf        stock_044_acc, W, ACCESS
    bz          flow_fw_update_relay_162c
    movlw       0x02
    xorwf       stock_07C_b0, F, BANKED
    movlw       0x44
    xorwf       stock_07D_b0, F, BANKED
flow_fw_update_relay_162c:
    incf        stock_048_acc, F, ACCESS
    movlw       0x07
    cpfsgt      stock_048_acc, ACCESS
    bra         flow_fw_update_relay_1606
flow_fw_update_relay_1634:
    movlw       0x40
    subwf       stock_084_b0, W, BANKED
    movlw       0x00
    subwfb      stock_085_b0, W, BANKED
    bc          flow_fw_update_relay_1640
    bra         flow_fw_update_relay_18d0
flow_fw_update_relay_1640:
    movlw       0xC0
    subwf       stock_084_b0, W, BANKED
    movlw       0x77
    subwfb      stock_085_b0, W, BANKED
    bnc         flow_fw_update_relay_164c
    bra         flow_fw_update_relay_18d0
flow_fw_update_relay_164c:
    movlw       0x0F
    andwf       stock_084_b0, W, BANKED
    movwf       stock_08A_b0, BANKED
    clrf        stock_08B_b0, BANKED
    iorwf       stock_08B_b0, W, BANKED
    bz          flow_fw_update_relay_165a
    bra         flow_fw_update_relay_182e
flow_fw_update_relay_165a:
    movf        stock_087_b0, W, BANKED
    iorwf       stock_086_b0, W, BANKED
    bnz         flow_fw_update_relay_1662
    bra         flow_fw_update_relay_179c
flow_fw_update_relay_1662:
    movf        stock_086_b0, W, BANKED
    addwf       stock_080_b0, F, BANKED
    movlw       0x00
    addwfc      stock_081_b0, F, BANKED
    movf        stock_087_b0, W, BANKED
    addwf       stock_080_b0, F, BANKED
    movlw       0x00
    addwfc      stock_081_b0, F, BANKED
    comf        stock_080_b0, W, BANKED
    movwf       stock_01B_acc, ACCESS
    comf        stock_081_b0, W, BANKED
    movwf       stock_01C_acc, ACCESS
    movlw       0xF1
    addwf       stock_01B_acc, W, ACCESS
    movwf       stock_080_b0, BANKED
    movlw       0xFF
    addwfc      stock_01C_acc, W, ACCESS
    movwf       stock_081_b0, BANKED
    movf        stock_080_b0, W, BANKED
    call        main_uart_service_43a2, 0x0
    rcall       emit_crlf
    movff       stock_080_b0_phys, stock_01B_b0_phys
    swapf       stock_01B_acc, F, ACCESS
    movlw       0x0F
    andwf       stock_01B_acc, F, ACCESS
    andwf       stock_01B_acc, F, ACCESS
    movf        stock_01B_acc, W, ACCESS
    rcall       hex_lookup_table_ptr                ; indexed TBLPTR -> hex_lookup_table
    movlw       0x9A
    addwf       stock_04B_acc, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    tblrd*
    movff       TABLAT, INDF2
    movff       stock_080_b0_phys, stock_01B_b0_phys
    movlw       0x0F
    andwf       stock_01B_acc, F, ACCESS
    movf        stock_01B_acc, W, ACCESS
    rcall       hex_lookup_table_ptr                ; indexed TBLPTR -> hex_lookup_table
    movlw       0x9B
    addwf       stock_04B_acc, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    tblrd*
    movff       TABLAT, INDF2
    movlw       0x9C
    addwf       stock_04B_acc, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    clrf        INDF2, ACCESS
    movlw       0x02
    addwf       stock_04B_acc, F, ACCESS
    movlb       0x0
    clrf        stock_09F_b0, BANKED
flow_fw_update_relay_16fa:
    clrf        stock_006_acc, ACCESS
    movlw       0x0A
    movwf       stock_005_acc, ACCESS
    movlb       0x1
    movlw       0x01
    movwf       stock_008_acc, ACCESS
    movlw       0xC7
    movwf       stock_007_acc, ACCESS
    movlw       0x0A
    movwf       stock_009_acc, ACCESS
    call        uart_rx_with_framing, 0x0
    movff       stock_1C8_b1_phys, stock_003_b0_phys
    movlb       0x1
    movf        stock_1C7_b1, W, BANKED
    call        intel_hex_checksum_update, 0x0
    movlb       0x0
    xorwf       stock_080_b0, W, BANKED
    bnz         flow_fw_update_relay_172a
    movlw       0x01
    movwf       stock_043_acc, ACCESS
    bra         flow_fw_update_relay_1796
flow_fw_update_relay_172a:
    clrf        stock_043_acc, ACCESS
    clrf        stock_019_acc, ACCESS
    movlw       0x1D
    movwf       stock_018_acc, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    movlb       0x0
    movff       stock_09F_b0_phys, stock_012_b0_phys
    clrf        stock_013_acc, ACCESS
    clrf        stock_015_acc, ACCESS
    movlw       0x0A
    movwf       stock_014_acc, ACCESS
    movlw       0x25
    call        main_core_service_41b6, 0x0
    movwf       stock_01B_acc, ACCESS
    clrf        stock_019_acc, ACCESS
    movff       stock_01B_b0_phys, stock_018_b0_phys
    call        uart_tx_block_from_buffer, 0x0
    movlw       0x21
    call        uart_tx_byte_blocking, 0x0
    call        main_uart_service_4860, 0x0
    rcall       emit_crlf
    movlw       0x19
    movlb       0x0
    subwf       stock_09F_b0, W, BANKED
    bc          flow_fw_update_relay_1792
    incf        stock_09F_b0, F, BANKED
    movlb       0x1
    movlw       0x01
    movwf       stock_019_acc, ACCESS
    movlw       0x9A
    movwf       stock_018_acc, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    rcall       emit_crlf
    bra         flow_fw_update_relay_1796
flow_fw_update_relay_1792:
    incf        stock_09F_b0, F, BANKED
    bra         flow_fw_update_relay_18dc
flow_fw_update_relay_1796:
    movf        stock_043_acc, W, ACCESS
    bnz         flow_fw_update_relay_179e
    bra         flow_fw_update_relay_16fa
flow_fw_update_relay_179c:
    clrf        stock_08E_b0, BANKED
flow_fw_update_relay_179e:
    movlw       0xBF
    movlb       0x0
    subwf       stock_084_b0, W, BANKED
    movlw       0x77
    subwfb      stock_085_b0, W, BANKED
    bc          flow_fw_update_relay_182e
    movlw       0x04
    subwf       stock_08E_b0, W, BANKED
    bc          flow_fw_update_relay_17bc
    incf        stock_08E_b0, F, BANKED
    movlw       0x0A
    call        timer3_blocking_delay_ms_W, 0x0 ; W04-E08 factored (10 ms)
flow_fw_update_relay_17bc:
    movff       stock_084_b0_phys, stock_086_b0_phys
    movff       stock_085_b0_phys, stock_087_b0_phys
    movlw       0x3A
    movlb       0x1
    movwf       stock_19A_b1, BANKED
    movlw       0x31
    movwf       stock_19B_b1, BANKED
    movlw       0x30
    movwf       stock_19C_b1, BANKED
    movff       stock_087_b0_phys, stock_01B_b0_phys
    rcall       nibble_to_hex_ascii_from_01B
    movff       TABLAT, stock_19D_b1_phys
    movff       stock_087_b0_phys, stock_01B_b0_phys
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, stock_19E_b1_phys
    movff       stock_086_b0_phys, stock_01B_b0_phys
    rcall       nibble_to_hex_ascii_from_01B
    movff       TABLAT, stock_19F_b1_phys
    movff       stock_086_b0_phys, stock_01B_b0_phys
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, stock_1A0_b1_phys
    movlw       0x30
    movwf       stock_1A1_b1, BANKED
    movwf       stock_1A2_b1, BANKED
    clrf        stock_1A3_b1, BANKED
    movlw       0x09
    movwf       stock_04B_acc, ACCESS
    call        main_uart_service_4860, 0x0
    movlb       0x1
    movlw       0x01
    movwf       stock_019_acc, ACCESS
    movlw       0x9A
    movwf       stock_018_acc, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    movlb       0x0
    clrf        stock_080_b0, BANKED
    clrf        stock_081_b0, BANKED
flow_fw_update_relay_182e:
    movlw       0xBF
    subwf       stock_084_b0, W, BANKED
    movlw       0x77
    subwfb      stock_085_b0, W, BANKED
    bc          flow_fw_update_relay_18cc
    btfss       stock_084_b0, 0, BANKED
    bra         flow_fw_update_relay_18bc
    movff       stock_046_b0_phys, stock_01B_b0_phys
    rcall       nibble_to_hex_ascii_from_01B
    movff       TABLAT, stock_02F_b0_phys
    movff       stock_046_b0_phys, stock_01B_b0_phys
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, stock_030_b0_phys
    movff       stock_04A_b0_phys, stock_01B_b0_phys
    rcall       nibble_to_hex_ascii_from_01B
    movff       TABLAT, stock_031_b0_phys
    movff       stock_04A_b0_phys, stock_01B_b0_phys
    movlw       0x0F
    rcall       nibble_to_hex_ascii
    movff       TABLAT, stock_032_b0_phys
    clrf        stock_033_acc, ACCESS
    clrf        stock_019_acc, ACCESS
    movlw       0x2F
    movwf       stock_018_acc, ACCESS
    call        uart_tx_block_from_buffer, 0x0
    clrf        stock_047_acc, ACCESS
    bra         flow_fw_update_relay_18a0
flow_fw_update_relay_1884:
    movf        stock_047_acc, W, ACCESS
    addlw       0x2F
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x9A
    addwf       stock_04B_acc, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x01
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    incf        stock_047_acc, F, ACCESS
    incf        stock_04B_acc, F, ACCESS
flow_fw_update_relay_18a0:
    movf        stock_047_acc, W, ACCESS
    addlw       0x2F
    call        fsr2_page0_read_w, 0x0               ; W04-E03
    bnz         flow_fw_update_relay_1884
    movlw       0x9A
    addwf       stock_04B_acc, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    clrf        INDF2, ACCESS
    bra         flow_fw_update_relay_18c0
flow_fw_update_relay_18bc:
    movff       stock_04A_b0_phys, stock_046_b0_phys
flow_fw_update_relay_18c0:
    movf        stock_04A_acc, W, ACCESS
    movlb       0x0
    addwf       stock_080_b0, F, BANKED
    movlw       0x00
    addwfc      stock_081_b0, F, BANKED
    bra         flow_fw_update_relay_18d0
flow_fw_update_relay_18cc:
    clrf        stock_080_b0, BANKED
    clrf        stock_081_b0, BANKED
flow_fw_update_relay_18d0:
    infsnz      stock_084_b0, F, BANKED
    incf        stock_085_b0, F, BANKED
    incf        stock_049_acc, F, ACCESS
    movlw       0x1F
    cpfsgt      stock_049_acc, ACCESS
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
    swapf       stock_01B_acc, F, ACCESS                ; high nibble -> low
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
    andwf       stock_01B_acc, F, ACCESS
    movf        stock_01B_acc, W, ACCESS
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
    movff       WREG, stock_0FD_b0_phys
    btfss       active_flags_acc, 3, ACCESS
    bra         cmd_gate_reject
    btfss       event_flags_b0, 1, BANKED
    bra         flow_cmd_dispatch_gated_19a8
    bsf         event_flags_b0, 3, BANKED
    bra         flow_cmd_dispatch_gated_1970
; W05-E07: tail-call merge — 4 callers previously did
;   rcall cmd_dispatch_gated_i2c_pair / bra flow_cmd_dispatch_gated_1990.
; Converted to `bra cmd_dispatch_gated_i2c_pair`; helper tail is
; `bra flow_cmd_dispatch_gated_1990` instead of `return 0`. Saves
; 4 * 2 B by removing the trailing `bra` at each caller; helper tail
; size unchanged (return -> bra, both 1 word).
flow_cmd_dispatch_gated_18fe:
    movlw       0x09
    movwf       stock_006_acc, ACCESS
    movlw       0x70
    bra         cmd_dispatch_gated_i2c_pair
flow_cmd_dispatch_gated_1918:
    movlw       0x0A
    movwf       stock_006_acc, ACCESS
    movlw       0xB0
    bra         cmd_dispatch_gated_i2c_pair
flow_cmd_dispatch_gated_1932:
    movlw       0x08
    movwf       stock_006_acc, ACCESS
    movlw       0x30
    bra         cmd_dispatch_gated_i2c_pair
flow_cmd_dispatch_gated_194c:
    movlw       0x0B
    movwf       stock_006_acc, ACCESS
    movlw       0xF0
cmd_dispatch_gated_i2c_pair:
    movwf       stock_00D_acc, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movf        stock_00D_acc, W, ACCESS
    movwf       stock_006_acc, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    call        main_i2c_service_48e2, 0x0
    bra         flow_cmd_dispatch_gated_1990
flow_cmd_dispatch_gated_1966:
    call        main_core_service_4516, 0x0
    movlw       0x01
    call        i2c_tas3108_reg1f_write, 0x0
    movlw       0x08
    movwf       stock_006_acc, ACCESS
    movlw       0x30
    bra         cmd_dispatch_gated_i2c_pair
flow_cmd_dispatch_gated_1970:
    movf        stock_093_b0, W, BANKED
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
    bcf         event_flags_b0, 1, BANKED
    bsf         filename_dirty_flags_b0, 0, BANKED
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_19a8:
    movlb       0x0
    btfss       event_flags_b0, 3, BANKED
    bra         flow_cmd_dispatch_gated_1a76
    ; V3.4 BUG-MUTE-REFRESH-01: route/SRC/HID/wake refreshes can make
    ; volume_dirty without being user volume movement. While effective mute is
    ; set, route the dirty volume pass through the existing mute service; real
    ; user unmute/volume movement clears active_flags.bit4 before this point.
    btfss       active_flags_acc, 4, ACCESS
    bra         flow_cmd_dispatch_gated_volume_unmuted
    bsf         event_flags_b0, 5, BANKED
    bra         flow_cmd_dispatch_gated_1a76
flow_cmd_dispatch_gated_volume_unmuted:
    bsf         event_flags_b0, 6, BANKED
    clrf        stock_0A4_b0, BANKED
    movff       stock_0A4_b0_phys, stock_0B0_b0_phys
    clrf        stock_09A_b0, BANKED
    bra         flow_cmd_dispatch_gated_19d6
flow_cmd_dispatch_gated_19be:
    movff       stock_09B_b0_phys, stock_09A_b0_phys
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19c4:
    movff       stock_09C_b0_phys, stock_09A_b0_phys
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19ca:
    movff       stock_09D_b0_phys, stock_09A_b0_phys
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19d0:
    movff       stock_09E_b0_phys, stock_09A_b0_phys
    bra         flow_cmd_dispatch_gated_19e6
flow_cmd_dispatch_gated_19d6:
    ; V3.4 SAFETY (2026-06-12 live ~1 s loud-audio burst): select the
    ; per-route volume trim by the APPLIED route shadow 0x0AB, never the
    ; in-flux request 0x093 — the Auto-Detect scan walks 0x093 through
    ; candidate values (and the RC0 stored-route override rewrites it), so
    ; a volume-dirty pass sampling it mid-flux applied ANOTHER input's
    ; HFD trim to the master volume (observed +8.8 dB over set volume)
    ; until a later pass corrected it.  0x0AB changes only at reconcile,
    ; and the route apply re-dirties volume, so the trim converges with
    ; the route the DSP is actually playing.
    ; (tests/sim/test_v34_detect_cycle_volume_excursion.py)
    movf        stock_0AB_b0, W, BANKED
    bz          flow_cmd_dispatch_gated_19be
    xorlw       0x05
    bz          flow_cmd_dispatch_gated_19c4
    xorlw       0x03
    bz          flow_cmd_dispatch_gated_19ca
    xorlw       0x01
    bz          flow_cmd_dispatch_gated_19d0
    ; Routes 1..4 (SRC receivers) carry no digital trim: clear the trim
    ; scratch explicitly rather than relying on ambient 0x09A state.
    ; Empirically load-bearing: the deterministic detect-cycle excursion
    ; (tests/sim/test_v34_detect_cycle_volume_excursion.py) still fired
    ; with the 0x0AB dispatch alone and went green only with this clear —
    ; a trim loaded by an 0x0AB==0/5/6/7 pass otherwise reaches a later
    ; receiver-route volume write through a path the static single-entry
    ; reading (ladder entry pre-clears 0x09A) does not capture.
    clrf        stock_09A_b0, BANKED
flow_cmd_dispatch_gated_19e6:
    movf        stock_09A_b0, W, BANKED
    addwf       computed_volume_b0, W, BANKED
    movwf       stock_00D_acc, ACCESS
    movlw       0x00
    addwfc      computed_volume_1_b0, W, BANKED
    movwf       stock_00E_acc, ACCESS
    movlw       0x00
    addwfc      computed_volume_2_b0, W, BANKED
    movwf       stock_00F_acc, ACCESS
    movlw       0x00
    addwfc      computed_volume_3_b0, W, BANKED
    movwf       stock_010_acc, ACCESS
    call        main_core_service_3e0a, 0x0
    movff       stock_00D_b0_phys, stock_012_b0_phys
    movff       stock_00E_b0_phys, stock_013_b0_phys
    movff       stock_00F_b0_phys, stock_014_b0_phys
    movff       stock_010_b0_phys, stock_015_b0_phys
    movlw       0x47
    movwf       stock_016_acc, ACCESS
    movlw       0xC9
    movwf       stock_017_acc, ACCESS
    movlw       0xEB
    movwf       stock_018_acc, ACCESS
    movlw       0x3D
    movwf       stock_019_acc, ACCESS
    call        main_core_service_2abc, 0x0
    movff       stock_012_b0_phys, stock_0ED_b0_phys
    movff       stock_013_b0_phys, stock_0EE_b0_phys
    movff       stock_014_b0_phys, stock_0EF_b0_phys
    movff       stock_015_b0_phys, stock_0F0_b0_phys
    movff       stock_0ED_b0_phys, stock_02F_b0_phys
    movff       stock_0EE_b0_phys, stock_030_b0_phys
    movff       stock_0EF_b0_phys, stock_031_b0_phys
    movff       stock_0F0_b0_phys, stock_032_b0_phys
    call        main_core_service_297e, 0x0
    movff       stock_02F_b0_phys, i2c_coeff_0_b0_phys
    movff       stock_030_b0_phys, i2c_coeff_1_b0_phys
    movff       stock_031_b0_phys, i2c_coeff_2_b0_phys
    movff       stock_032_b0_phys, i2c_coeff_3_b0_phys
    call        volume_dsp_write, 0x0       ; V3.1 Fix B: verified volume write
flow_cmd_dispatch_gated_volume_done:
    rcall       usb_mailbox_service_05          ; W02-E03: factored 6-line pattern
    movlb       0x0
    bsf         filename_dirty_flags_b0, 0, BANKED
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_1a76:
    btfss       active_flags_acc, 7, ACCESS
    bra         flow_cmd_dispatch_gated_1a9c
    ; V3.2: cancel any active preset job — reconnect does a full table apply
    movlb       0x2
    clrf        preset_job_state_b2, BANKED
    bcf         T3CON, 0, ACCESS
    bcf         PIE2, 1, ACCESS
    bcf         PIR2, 1, ACCESS
    call        clrf_i2c_coeff_0123_and_write, 0x0  ; W03-E02: factored 5-line pattern
    call        main_core_service_4574, 0x0
    movlb       0x0
    ; V3.2 BUG-PRESET-01 hardening: if filename RAM is still dirty or
    ; under a USB filename transaction, do not report EP0 reapply complete.
    ; preset_load_filename would be unsafe to run, but clearing bit7 here
    ; makes the flasher believe the restored preset is coherent while the
    ; visible filename RAM may still belong to the previous preset.
    btfsc       filename_dirty_flags_b0, 5, BANKED
    bra         flow_cmd_dispatch_gated_reapply_wait_name
    btfsc       filename_dirty_flags_b0, 6, BANKED
    bra         flow_cmd_dispatch_gated_reapply_wait_name
    bcf         INTCON, 7, ACCESS
    call        preset_load_filename, 0x0
    bsf         INTCON, 7, ACCESS
flow_cmd_dispatch_gated_reapply_skip_name:
    bsf         RCSTA, 4, ACCESS
    bcf         active_flags_acc, 7, ACCESS
    movlb       0x0
    btfss       event_flags_b0, 5, BANKED
    btfsc       active_flags_acc, 4, ACCESS
    bra         flow_cmd_dispatch_gated_1a9c
    bsf         event_flags_b0, 3, BANKED
    bra         flow_cmd_dispatch_gated_1a9c
flow_cmd_dispatch_gated_reapply_wait_name:
    bsf         RCSTA, 4, ACCESS
flow_cmd_dispatch_gated_1a9c:
    movlb       0x0
    btfss       event_flags_b0, 5, BANKED
    bra         flow_cmd_dispatch_gated_1aca
    btfss       active_flags_acc, 4, ACCESS
    bra         flow_cmd_dispatch_gated_1ab6
    call        clrf_i2c_coeff_0123_and_write, 0x0  ; verified zero write via volume_dsp_write
    bra         flow_cmd_dispatch_gated_1ab8
flow_cmd_dispatch_gated_1ab6:
    bsf         event_flags_b0, 3, BANKED
flow_cmd_dispatch_gated_1ab8:
    rcall       usb_mailbox_service_05          ; W02-E03: factored 6-line pattern
    movlb       0x0
    bcf         event_flags_b0, 5, BANKED
flow_cmd_dispatch_gated_1aca:
    btfss       event_flags_b0, 6, BANKED
    bra         flow_cmd_dispatch_gated_1baa
    movlw       0x5F
    movwf       stock_014_acc, ACCESS
    movlb       0x0
    btfsc       stock_0A4_b0, 0, BANKED
    bra         flow_cmd_dispatch_gated_1ad8
    movlw       0x1C
    bra         flow_cmd_dispatch_gated_1ada
flow_cmd_dispatch_gated_1ad8:
    movlw       0x08
flow_cmd_dispatch_gated_1ada:
    rcall       i2c_381c_with_w_bank0           ; W05-E01: factored 3-line pattern
    btfsc       stock_0A4_b0, 1, BANKED
    bra         flow_cmd_dispatch_gated_1aee
    movlw       0x44
    bra         flow_cmd_dispatch_gated_1af0
flow_cmd_dispatch_gated_1aee:
    movlw       0x30
flow_cmd_dispatch_gated_1af0:
    rcall       i2c_381c_with_w_bank0           ; W05-E01: factored 3-line pattern
    btfsc       stock_0A4_b0, 2, BANKED
    bra         flow_cmd_dispatch_gated_1b04
    movlw       0x6C
    bra         flow_cmd_dispatch_gated_1b06
flow_cmd_dispatch_gated_1b04:
    movlw       0x58
flow_cmd_dispatch_gated_1b06:
    rcall       i2c_381c_with_w_bank0           ; W05-E01: factored 3-line pattern
    btfsc       stock_0A4_b0, 3, BANKED
    bra         flow_cmd_dispatch_gated_1b1a
    movlw       0x94
    bra         flow_cmd_dispatch_gated_1b1c
flow_cmd_dispatch_gated_1b1a:
    movlw       0x80
flow_cmd_dispatch_gated_1b1c:
    rcall       i2c_381c_with_w_bank0           ; W05-E01: factored 3-line pattern
    btfsc       stock_0A4_b0, 4, BANKED
    bra         flow_cmd_dispatch_gated_1b30
    movlw       0xBC
    bra         flow_cmd_dispatch_gated_1b32
flow_cmd_dispatch_gated_1b30:
    movlw       0xA8
flow_cmd_dispatch_gated_1b32:
    rcall       i2c_381c_with_w_bank0           ; W05-E01: factored 3-line pattern
    btfsc       stock_0A4_b0, 5, BANKED
    bra         flow_cmd_dispatch_gated_1b46
    movlw       0xE4
    bra         flow_cmd_dispatch_gated_1b48
flow_cmd_dispatch_gated_1b46:
    movlw       0xD0
flow_cmd_dispatch_gated_1b48:
    movwf       stock_013_acc, ACCESS
    call        main_i2c_service_381c, 0x0
flow_cmd_dispatch_gated_1b8c:
    rcall       usb_mailbox_service_05          ; W02-E03: factored 6-line pattern
    movlb       0x0
    bcf         event_flags_b0, 6, BANKED
flow_cmd_dispatch_gated_1baa:
    btfss       event_flags_b0, 4, BANKED
    bra         flow_cmd_dispatch_gated_1bc8
    rcall       main_i2c_service_2100
    movlb       0x0
    bcf         event_flags_b0, 4, BANKED
    bsf         filename_dirty_flags_b0, 1, BANKED
    movlw       0x05
    movwf       stock_0C1_b0, BANKED
    movf        stock_0FD_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        main_usb_service_45a2, 0x0
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_1bc8:
    movlb       0x0
    btfss       dsp_fault_flags_b0, 0, BANKED
    bra         flow_cmd_dispatch_gated_1bd6
    bcf         dsp_fault_flags_b0, 0, BANKED
    bsf         filename_dirty_flags_b0, 2, BANKED
    call        main_timer_service_48a6, 0x0
flow_cmd_dispatch_gated_1bd6:
    movlb       0x0
    btfss       dsp_fault_flags_b0, 1, BANKED
    bra         cmd_gate_reject
    bcf         dsp_fault_flags_b0, 1, BANKED
    bsf         filename_dirty_flags_b0, 2, BANKED
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
    movwf       stock_0C1_b0, BANKED
    movf        stock_0FD_b0, W, BANKED
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
    movwf       stock_013_acc, ACCESS
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
    clrf        stock_009_acc, ACCESS
    bra         flow_main_uart_service_1be6_1e78
flow_main_uart_service_1be6_1bea:
    call        rx_ring_has_data, 0x0

    bnz         flow_main_uart_service_1be6_1bf4
    bra         flow_main_uart_service_1be6_1e7c
flow_main_uart_service_1be6_1bf4:
    call        rx_ring_read, 0x0
    movwf       stock_00A_acc, ACCESS
    movlw       0x7F
    cpfsgt      stock_00A_acc, ACCESS
    bra         flow_main_uart_service_1be6_1c42
    movf        stock_00A_acc, W, ACCESS
    xorlw       0xB0
    bnz         flow_main_uart_service_1be6_1c0e
    movlw       0x01
    movwf       rx_frame_position_b0, BANKED
    bcf         active_flags_acc, 0, ACCESS
    bra         parser_route_phase_handler
flow_main_uart_service_1be6_1c0e:
    movf        stock_00A_acc, W, ACCESS
    xorlw       0xB1
    bnz         flow_main_uart_service_1be6_1c1c
    movlw       0x01
    movwf       rx_frame_position_b0, BANKED
    bsf         active_flags_acc, 0, ACCESS
    bra         parser_route_phase_handler
flow_main_uart_service_1be6_1c1c:
    clrf        rx_frame_position_b0, BANKED
    bcf         active_flags_acc, 0, ACCESS
    movff       stock_00A_b0_phys, saved_w_b0_phys
    movlw       0xF0
    andwf       stock_005_acc, F, ACCESS
    movf        stock_005_acc, W, ACCESS
    xorlw       0xB0
    bnz         parser_route_phase_handler
    movf        stock_00A_acc, W, ACCESS
    xorlw       0xBF
    btfss       STATUS, 2, ACCESS
    decf        stock_00A_acc, F, ACCESS
; ---------------------------------------------------------------------------
; parser_route_phase_handler
; Receives a route byte (0xB0/0xB1/0xBF/...) and decides whether to forward
; it downstream. PB1 forwards every byte that is NOT addressed to itself
; (active_flags.bit0 == 0); PB2 (last on chain) silently consumes its own
; addressed traffic. This is the chain-link forward path that makes a
; multi-MAIN install behave as one current loop to CONTROL.
; ---------------------------------------------------------------------------
parser_route_phase_handler:
    btfsc       active_flags_acc, 0, ACCESS              ; addressed to us?
    bra         flow_main_uart_service_1be6_1e80     ; yes -> consume locally
    movlb       0x02
    bsf         chain_tx_emitted_b2, 0, BANKED
    movlb       0x00
    movf        stock_00A_acc, W, ACCESS                 ; no  -> echo to next link
    call        uart_tx_byte_blocking, 0x0
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1c42:
    btfsc       active_flags_acc, 0, ACCESS
    bra         flow_main_uart_service_1be6_1c52
    movlw       0x02
    subwf       rx_frame_position_b0, W, BANKED
    bc          flow_main_uart_service_1be6_1c52
    movlb       0x02
    bsf         chain_tx_emitted_b2, 0, BANKED
    movlb       0x00
    movf        stock_00A_acc, W, ACCESS
    call        uart_tx_byte_blocking, 0x0
flow_main_uart_service_1be6_1c52:
    movlb       0x0
    movf        rx_frame_position_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    incf        rx_frame_position_b0, F, BANKED
    movlw       0x02
    subwf       rx_frame_position_b0, W, BANKED
    bc          flow_main_uart_service_1be6_1c62
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1c62:
    movf        rx_frame_position_b0, W, BANKED
    xorlw       0x02
    bnz         flow_main_uart_service_1be6_1c6e
    movff       stock_00A_b0_phys, stock_0A2_b0_phys
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1c6e:
    movff       stock_00A_b0_phys, current_cmd_data_b0_phys
    movff       stock_00A_b0_phys, stock_0BC_b0_phys
    bsf         active_flags_acc, 6, ACCESS
    movlw       0x01
    movwf       rx_frame_position_b0, BANKED
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
    btfsc       active_flags_acc, 3, ACCESS              ; gate already open?
    movlw       0x00                                 ; yes -> ram_0x005 = 0
    movwf       stock_005_acc, ACCESS                    ; ram_0x005 = (gate-was-closed) ? 1 : 0
    rlncf       stock_005_acc, F, ACCESS
    rlncf       stock_005_acc, F, ACCESS                 ; shifted into bit2 mask position
    movf        event_flags_b0, W, BANKED
    xorwf       stock_005_acc, W, ACCESS
    andlw       0xFB                                 ; preserve every bit except bit2
    xorwf       stock_005_acc, W, ACCESS                 ; OR in bit2 if we computed it
    movwf       event_flags_b0, BANKED
    btfsc       event_flags_b0, 2, BANKED               ; event raised?
    bsf         active_flags_acc, 3, ACCESS              ; open the gate
    bra         flow_main_uart_service_1be6_1e6c

; ---------------------------------------------------------------------------
; standby_request_handler                  (cmd=0x03 data=0x00)
; Symmetric inverse of wake: clear active_flags.bit3 (close the gate) and
; raise event_flags.bit2 to schedule hw_standby_shutdown. If the gate was
; already closed, preserve any pending event: CONTROL may emit duplicate
; standby frames before standby_event_dispatch runs, and clearing bit2 there
; would cancel the hardware shutdown while leaving the logical gate closed.
; This is the broadcast that closes EVERY MAIN's gate on the chain — once
; closed, cmd_dispatch_gated drops every command at cmd_gate_reject until a
; wake reopens it.
; ---------------------------------------------------------------------------
standby_request_handler:
    btfss       active_flags_acc, 3, ACCESS              ; gate currently open?
    bra         flow_main_uart_service_1be6_1ca2     ; no  -> just consume the event
    bsf         event_flags_b0, 2, BANKED               ; yes -> raise standby event
    bra         flow_main_uart_service_1be6_1ca6
flow_main_uart_service_1be6_1ca2:
    movlb       0x0
    nop                                             ; duplicate standby: keep pending bit2 intact
flow_main_uart_service_1be6_1ca6:
    btfsc       event_flags_b0, 2, BANKED
    bcf         active_flags_acc, 3, ACCESS              ; close the gate (BROADCAST drops all MAINs)
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
    btfsc       stock_094_b0, 3, BANKED                 ; HID query mode?
    bra         flow_main_uart_service_1be6_1cd6
    bsf         active_flags_acc, 4, ACCESS              ; user mute on
    bsf         stock_094_b0, 5, BANKED                  ; remember user-owned mute
    ; V3.2: if preset job active, record user wants mute
    movlb       0x2
    tstfsz      preset_job_state_b2, BANKED             ; skip if IDLE
    bsf         preset_job_flags_b2, 1, BANKED          ; latch user_mute_desired
    movlb       0x0
    movlw       0x01
    btfss       active_flags_acc, 4, ACCESS
    movlw       0x00
    movwf       stock_005_acc, ACCESS
    btfss       active_flags_acc, 5, ACCESS
    bra         flow_main_uart_service_1be6_1cc2
    movlw       0x01
    bra         flow_main_uart_service_1be6_1cc4
flow_main_uart_service_1be6_1cc2:
    movlw       0x00
flow_main_uart_service_1be6_1cc4:
    xorwf       stock_005_acc, F, ACCESS
    btfss       STATUS, 2, ACCESS
flow_main_uart_service_1be6_1cc8:
    bsf         event_flags_b0, 5, BANKED
flow_main_uart_service_1be6_1cca:
    btfss       active_flags_acc, 4, ACCESS
    bra         flow_main_uart_service_1be6_1cd2
    bsf         active_flags_acc, 5, ACCESS
    bra         flow_main_uart_service_1be6_1cd4
flow_main_uart_service_1be6_1cd2:
    bcf         active_flags_acc, 5, ACCESS
flow_main_uart_service_1be6_1cd4:
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1cd6:
    movlw       0x02
    btfss       active_flags_acc, 4, ACCESS
    movlw       0x03
    movwf       stock_0BC_b0, BANKED
    bcf         stock_094_b0, 3, BANKED
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
    btfsc       stock_094_b0, 3, BANKED                 ; HID query mode?
    bra         flow_main_uart_service_1be6_1cd6
    bcf         stock_094_b0, 5, BANKED                  ; explicit user unmute
    ; V3.2: during a force-muted preset job, suppress the actual mute-off
    ; so the DSP stays muted while the table apply is in progress.
    ; Only record the user's desire for COMMIT to act on later.
    movlb       0x2
    tstfsz      preset_job_state_b2, BANKED             ; skip next if IDLE
    btfss       preset_job_flags_b2, 0, BANKED          ; skip next if force-muted
    bra         cmd03_mute_off_apply
    bcf         preset_job_flags_b2, 1, BANKED          ; record: user wants unmute
    movlb       0x0
    bra         flow_main_uart_service_1be6_1e6c
cmd03_mute_off_apply:
    movlb       0x0
    bcf         active_flags_acc, 4, ACCESS
    ; V3.2: if preset job active (non-force-muted), record user wants unmute
    movlb       0x2
    tstfsz      preset_job_state_b2, BANKED
    bcf         preset_job_flags_b2, 1, BANKED
    movlb       0x0
    movlw       0x01
    btfss       active_flags_acc, 4, ACCESS
    movlw       0x00
    movwf       stock_005_acc, ACCESS
    btfss       active_flags_acc, 5, ACCESS
    bra         flow_main_uart_service_1be6_1cc2
    movlw       0x01
    xorwf       stock_005_acc, F, ACCESS
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
    movf        current_cmd_data_b0, W, BANKED
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
    btfsc       stock_094_b0, 0, BANKED                 ; HID query mode?
    bra         flow_main_uart_service_1be6_1d22
    movff       current_cmd_data_b0_phys, input_select_b0_phys              ; commit new input
    movff       input_select_b0_phys, input_select_mirror_b0_phys
    movlb       0x0
    setf        stock_0AB_b0, BANKED                    ; force route re-evaluation
    movlw       0x65
    movwf       stock_0BB_b0, BANKED                    ; run slow I2C service immediately
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d22:
    movff       input_select_b0_phys, stock_0BC_b0_phys
    bcf         stock_094_b0, 0, BANKED
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
    btfsc       stock_094_b0, 1, BANKED                 ; HID query mode?
    bra         flow_main_uart_service_1be6_1d80
    movlw       0xA0                                 ; -0x60 low byte (two's complement)
    movwf       stock_005_acc, ACCESS
    setf        stock_006_acc, ACCESS                    ; 0xFFFF... high byte
    movf        current_cmd_data_b0, W, BANKED                 ; data byte
    movwf       stock_007_acc, ACCESS
    clrf        stock_008_acc, ACCESS
    movf        stock_005_acc, W, ACCESS
    addwf       stock_007_acc, F, ACCESS                 ; data + 0xA0 (8-bit)
    movf        stock_006_acc, W, ACCESS
    addwfc      stock_008_acc, F, ACCESS                 ; carry → upper byte
    movff       stock_007_b0_phys, computed_volume_b0_phys
    movff       stock_008_b0_phys, computed_volume_1_b0_phys
    movlw       0x00
    btfsc       computed_volume_1_b0, 7, BANKED         ; sign-extend to 32 bits
    movlw       0xFF
    movwf       computed_volume_2_b0, BANKED
    movwf       computed_volume_3_b0, BANKED
    xorwf       logical_volume_3_b0, W, BANKED
    bnz         flow_main_uart_service_1be6_1d68
    movf        logical_volume_2_b0, W, BANKED
    xorwf       computed_volume_2_b0, W, BANKED
    bnz         flow_main_uart_service_1be6_1d68
    movf        logical_volume_1_b0, W, BANKED
    xorwf       computed_volume_1_b0, W, BANKED
    bnz         flow_main_uart_service_1be6_1d68
    movf        logical_volume_b0, W, BANKED
    xorwf       computed_volume_b0, W, BANKED
flow_main_uart_service_1be6_1d68:
    bnz         flow_main_uart_service_1be6_1d6c
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d6c:
    bsf         event_flags_b0, 3, BANKED
    ; V3.4 BUG-V34V173-1: a volume frame updates the latent volume only.
    ; Mute is owned EXCLUSIVELY by cmd 0x03.  A real user volume key while
    ; muted is unmuted by the B0/03/03 that V1.73 CONTROL emits after
    ; clearing its local mute; host/full-sync volume frames carry no such
    ; provenance and must not clear mute.  While active_flags.bit4 is set
    ; the volume-dirty drain routes through the verified mute-zero path.
    ; V3.1 Fix B': do NOT copy computed->logical here (deferred to volume_dsp_write)
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d80:
    movf        computed_volume_b0, W, BANKED
    addlw       0x60
    movwf       stock_0BC_b0, BANKED
    bcf         stock_094_b0, 1, BANKED
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d8a:
    movf        current_cmd_data_b0, W, BANKED
    xorlw       0x29
    bz          flow_main_uart_service_1be6_1d8a_report
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d8a_report:
    call        report_cmd29_status, 0x0
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1d96:
    movff       current_cmd_data_b0_phys, stock_060_b0_phys
    movf        stock_0A5_b0, W, BANKED
    xorwf       stock_060_b0, W, BANKED
    bz          flow_main_uart_service_1be6_1e6c
    bsf         event_flags_b0, 4, BANKED
    movff       stock_060_b0_phys, stock_0A5_b0_phys
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1da8:
    movff       current_cmd_data_b0_phys, stock_061_b0_phys
    movf        stock_061_b0, W, BANKED
    xorwf       stock_0A6_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags_b0, 4, BANKED
    movff       stock_061_b0_phys, stock_0A6_b0_phys
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1dba:
    movff       current_cmd_data_b0_phys, stock_062_b0_phys
    movf        stock_062_b0, W, BANKED
    xorwf       stock_0A7_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags_b0, 4, BANKED
    movff       stock_062_b0_phys, stock_0A7_b0_phys
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1dcc:
    movff       current_cmd_data_b0_phys, stock_063_b0_phys
    movf        stock_063_b0, W, BANKED
    xorwf       stock_0A8_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags_b0, 4, BANKED
    movff       stock_063_b0_phys, stock_0A8_b0_phys
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1dde:
    movff       current_cmd_data_b0_phys, stock_064_b0_phys
    movf        stock_064_b0, W, BANKED
    xorwf       stock_0A9_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags_b0, 4, BANKED
    movff       stock_064_b0_phys, stock_0A9_b0_phys
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1df0:
    movff       current_cmd_data_b0_phys, stock_065_b0_phys
    movf        stock_065_b0, W, BANKED
    xorwf       stock_0AA_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags_b0, 4, BANKED
    movff       stock_065_b0_phys, stock_0AA_b0_phys
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1e02:
    btfsc       stock_094_b0, 4, BANKED
    bra         flow_main_uart_service_1be6_1e14
    movf        stock_0B8_b0, W, BANKED
    xorwf       current_cmd_data_b0, W, BANKED
    bz          flow_main_uart_service_1be6_1e6c
    movff       current_cmd_data_b0_phys, stock_0B8_b0_phys
    bsf         dsp_fault_flags_b0, 0, BANKED
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1e14:
    movff       stock_0B8_b0_phys, stock_0BC_b0_phys
    bcf         stock_094_b0, 4, BANKED
    bra         flow_main_uart_service_1be6_1e6c
flow_main_uart_service_1be6_1e1c:
    movff       current_cmd_data_b0_phys, stock_0C3_b0_phys
    movf        stock_0B2_b0, W, BANKED
    xorwf       stock_0C3_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         filename_dirty_flags_b0, 0, BANKED
    movff       stock_0C3_b0_phys, stock_0B2_b0_phys
    bra         flow_main_uart_service_1be6_1e6c
cmd_dispatch_xor_chain:
    movf        stock_0A2_b0, W, BANKED
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
    xorlw       0x01                            ; V3.2 link health: cumulative 0x22 ^ 0x01 = 0x23
    btfsc       STATUS, 2, ACCESS               ; Z = cmd 0x23 (one-frame health ping)
    goto        cmd23_health_query_handler
    xorlw       0x06                            ; V3.4 identity: cumulative 0x23 ^ 0x06 = 0x25
    btfsc       STATUS, 2, ACCESS               ; Z = cmd 0x25 (MAIN identity query)
    goto        cmd25_identity_query_handler
    xorlw       0x03                            ; V3.4 filename: cumulative 0x25 ^ 0x03 = 0x26
    btfsc       STATUS, 2, ACCESS               ; Z = cmd 0x26 (preset filename query)
    goto        cmd26_filename_query_handler
flow_main_uart_service_1be6_1e6c:
    btfss       active_flags_acc, 6, ACCESS
    bra         flow_main_uart_service_1be6_1e80
    movlb       0x02
    bsf         chain_tx_emitted_b2, 0, BANKED
    movlb       0x0
    movf        stock_0BC_b0, W, BANKED
    call        uart_tx_byte_blocking, 0x0
flow_main_uart_service_1be6_1e78:
    bcf         active_flags_acc, 6, ACCESS
    bra         flow_main_uart_service_1be6_1e80
flow_main_uart_service_1be6_1e7c:
    movlw       0x01
    movwf       stock_009_acc, ACCESS
flow_main_uart_service_1be6_1e80:
    movf        stock_009_acc, W, ACCESS
    btfss       STATUS, 2, ACCESS
    return      0
    bra         flow_main_uart_service_1be6_1bea


; ---------------------------------------------------------------------------
; Function: main_core_service_1e88
; Address : 0x1E88
; Notes   : Inferred core helper routine. Calls: eeprom_read_byte, main_flash_service_46de.
; ---------------------------------------------------------------------------
main_core_service_1e88:
    clrf        stock_004_acc, ACCESS
    clrf        stock_003_acc, ACCESS
    call        eeprom_read_byte, 0x0
    movlb       0x0
    movwf       computed_volume_3_b0, BANKED
    movlw       0x01
    rcall       eeprom_read_byte_W
    movwf       computed_volume_2_b0, BANKED
    movlw       0x02
    rcall       eeprom_read_byte_W
    movwf       computed_volume_1_b0, BANKED
    movlw       0x03
    rcall       eeprom_read_byte_W
    movwf       computed_volume_b0, BANKED
    movlw       0x04
    rcall       eeprom_read_byte_W
    movwf       input_select_b0, BANKED
    movlw       0x07
    rcall       eeprom_read_byte_W
    movwf       stock_060_b0, BANKED
    movlw       0x08
    rcall       eeprom_read_byte_W
    movwf       stock_061_b0, BANKED
    movlw       0x09
    rcall       eeprom_read_byte_W
    movwf       stock_062_b0, BANKED
    movlw       0x0A
    rcall       eeprom_read_byte_W
    movwf       stock_063_b0, BANKED
    movlw       0x0B
    rcall       eeprom_read_byte_W
    movwf       stock_064_b0, BANKED
    movlw       0x0C
    rcall       eeprom_read_byte_W
    movwf       stock_065_b0, BANKED
    clrf        stock_004_acc, ACCESS
    movlw       0x0D
    movwf       stock_003_acc, ACCESS
    call        eeprom_read_byte, 0x0
    movwf       stock_05F_acc, ACCESS
    movlw       0x14
    rcall       eeprom_read_byte_W
    movwf       stock_0C3_b0, BANKED
    movf        computed_volume_3_b0, W, BANKED
    xorlw       0x80
    addlw       0x80
    bnz         flow_main_core_service_1e88_1f54
    movlw       0x00
    subwf       computed_volume_2_b0, W, BANKED
    bnz         flow_main_core_service_1e88_1f54
    movlw       0x00
    subwf       computed_volume_1_b0, W, BANKED
    bnz         flow_main_core_service_1e88_1f54
    movlw       0x13
    subwf       computed_volume_b0, W, BANKED
flow_main_core_service_1e88_1f54:
    bnc         flow_main_core_service_1e88_1f60
    movlw       0xA0
    movwf       computed_volume_b0, BANKED
    setf        computed_volume_1_b0, BANKED
    setf        computed_volume_2_b0, BANKED
    setf        computed_volume_3_b0, BANKED
flow_main_core_service_1e88_1f60:
    movlw       0x08
    cpfsgt      input_select_b0, BANKED
    bra         flow_main_core_service_1e88_1f6a
    movlw       0x01
    movwf       input_select_b0, BANKED
flow_main_core_service_1e88_1f6a:
    movlw       0x03
    cpfsgt      stock_060_b0, BANKED
    bra         flow_main_core_service_1e88_1f72
    clrf        stock_060_b0, BANKED
flow_main_core_service_1e88_1f72:
    lfsr        FSR2, stock_061_b0_phys
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1f7e
    clrf        stock_061_b0, BANKED
flow_main_core_service_1e88_1f7e:
    lfsr        FSR2, stock_062_b0_phys
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1f8a
    clrf        stock_062_b0, BANKED
flow_main_core_service_1e88_1f8a:
    lfsr        FSR2, stock_063_b0_phys
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1f98
    movlw       0x01
    movwf       stock_063_b0, BANKED
flow_main_core_service_1e88_1f98:
    lfsr        FSR2, stock_064_b0_phys
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1fa6
    movlw       0x01
    movwf       stock_064_b0, BANKED
flow_main_core_service_1e88_1fa6:
    lfsr        FSR2, stock_065_b0_phys
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         flow_main_core_service_1e88_1fb4
    movlw       0x01
    movwf       stock_064_b0, BANKED
flow_main_core_service_1e88_1fb4:
    movlw       0x03
    cpfsgt      stock_05F_acc, ACCESS
    bra         flow_main_core_service_1e88_1fbc
    movwf       stock_05F_acc, ACCESS
flow_main_core_service_1e88_1fbc:
    movlw       0x04
    cpfsgt      stock_0C3_b0, BANKED
    bra         flow_main_core_service_1e88_1fc6
    movlw       0x01
    movwf       stock_0C3_b0, BANKED
flow_main_core_service_1e88_1fc6:
    call        copy_computed_volume_to_logical_volume, 0x0
    movff       input_select_b0_phys, input_select_mirror_b0_phys
    movff       stock_060_b0_phys, stock_0A5_b0_phys
    movff       stock_061_b0_phys, stock_0A6_b0_phys
    movff       stock_062_b0_phys, stock_0A7_b0_phys
    movff       stock_063_b0_phys, stock_0A8_b0_phys
    movff       stock_064_b0_phys, stock_0A9_b0_phys
    movff       stock_065_b0_phys, stock_0AA_b0_phys
    movff       stock_0C3_b0_phys, stock_0B2_b0_phys
    movlw       0x0F
    rcall       eeprom_read_byte_W
    movwf       stock_0B4_b0, BANKED
    incf        stock_0B4_b0, W, BANKED
    btfsc       STATUS, 2, ACCESS
    bcf         stock_0B4_b0, 0, BANKED
    movff       stock_0B4_b0_phys, stock_0B1_b0_phys
    movlw       0x0E
    rcall       eeprom_read_byte_W
    movwf       stock_0B8_b0, BANKED
    movlw       0x03
    subwf       stock_0B8_b0, W, BANKED
    bc          flow_main_core_service_1e88_2026
    movlw       0x03
    movwf       stock_0B8_b0, BANKED
flow_main_core_service_1e88_2026:
    movlw       0x04
    cpfsgt      stock_0B8_b0, BANKED
    bra         flow_main_core_service_1e88_2030
    movlw       0x03
    movwf       stock_0B8_b0, BANKED
flow_main_core_service_1e88_2030:
    movlw       0x10
    rcall       eeprom_read_byte_W
    movwf       stock_09B_b0, BANKED
    movlw       0x11
    rcall       eeprom_read_byte_W
    movwf       stock_09C_b0, BANKED
    movlw       0x12
    rcall       eeprom_read_byte_W
    movwf       stock_09D_b0, BANKED
    movlw       0x13
    rcall       eeprom_read_byte_W
    movwf       stock_09E_b0, BANKED
    movlw       0x12
    cpfsgt      stock_09B_b0, BANKED
    bra         flow_main_core_service_1e88_2070
    clrf        stock_09B_b0, BANKED
flow_main_core_service_1e88_2070:
    movlw       0x12
    cpfsgt      stock_09C_b0, BANKED
    bra         flow_main_core_service_1e88_2078
    clrf        stock_09C_b0, BANKED
flow_main_core_service_1e88_2078:
    movlw       0x12
    cpfsgt      stock_09D_b0, BANKED
    bra         flow_main_core_service_1e88_2080
    clrf        stock_09D_b0, BANKED
flow_main_core_service_1e88_2080:
    movlw       0x12
    cpfsgt      stock_09E_b0, BANKED
    bra         flow_main_core_service_1e88_2088
    clrf        stock_09E_b0, BANKED
flow_main_core_service_1e88_2088:
    movff       stock_09B_b0_phys, stock_0AC_b0_phys
    movff       stock_09C_b0_phys, stock_0AD_b0_phys
    movff       stock_09D_b0_phys, stock_0AE_b0_phys
    movff       stock_09E_b0_phys, stock_0AF_b0_phys
    movlw       0x50
    movwf       stock_00A_acc, ACCESS
flow_main_core_service_1e88_209c:
    movlb       0x1
    movlw       0xB0
    addwf       stock_00A_acc, W, ACCESS
    rcall       setup_fsr2_page_1
    movff       stock_00A_b0_phys, stock_003_b0_phys
    clrf        stock_004_acc, ACCESS
    call        eeprom_read_byte, 0x0
    movwf       INDF2, ACCESS
    incf        stock_00A_acc, F, ACCESS
    movlw       0x5E
    cpfsgt      stock_00A_acc, ACCESS
    bra         flow_main_core_service_1e88_209c
    movlw       0x60
    movwf       stock_00A_acc, ACCESS
flow_main_core_service_1e88_20c2:
    movlb       0x2
    movlw       0x60
    addwf       stock_00A_acc, W, ACCESS
    call        fsr2_page2_from_W, 0x0       ; W05-E02: FSR2=0x0200|W (helper clobbers W; eeprom_read_byte takes input via ram_0x003)
    movff       stock_00A_b0_phys, stock_003_b0_phys
    clrf        stock_004_acc, ACCESS
    call        eeprom_read_byte, 0x0
    movwf       INDF2, ACCESS
    incf        stock_00A_acc, F, ACCESS
    movlw       0x7D
    cpfsgt      stock_00A_acc, ACCESS
    bra         flow_main_core_service_1e88_20c2
    clrf        stock_008_acc, ACCESS
    movlw       0x80
    movwf       stock_007_acc, ACCESS
    movlw       0x03
    movwf       stock_009_acc, ACCESS
    call        main_flash_service_46de, 0x0
    clrf        stock_008_acc, ACCESS
    movlw       0x81
    movwf       stock_007_acc, ACCESS
    movlw       0x03
    movwf       stock_009_acc, ACCESS
    call        main_flash_service_46de, 0x0
    clrf        stock_008_acc, ACCESS
    movlw       0x82
    movwf       stock_007_acc, ACCESS
    movlw       0x8A                            ; V3.4_RUNTIME_EEPROM_REV
    movwf       stock_009_acc, ACCESS
    goto        main_flash_service_46de


; ---------------------------------------------------------------------------
; eeprom_read_byte_W  — rcall-reachable wrapper that reads one EEPROM byte.
; Arguments: W = EEPROM address (low byte); ram_0x004 cleared by helper.
; Returns  : W = byte read; BSR = 0 on return.
; W02-E01 size optimization: collapses 17 × 5-instruction preambles in
; main_core_service_1e88 into 17 × 2-instruction sequences.
; ---------------------------------------------------------------------------
eeprom_read_byte_W:
    movwf       stock_003_acc, ACCESS   ; ram_0x003 = address low byte
    clrf        stock_004_acc, ACCESS   ; high byte always 0 in this call site set
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
    movwf       stock_004_acc, ACCESS
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
    movwf       stock_003_acc, ACCESS
    movlw       0x04
    movwf       stock_005_acc, ACCESS
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
    clrf        stock_004_acc, ACCESS
    movlw       0xD7
    rcall       ram_block_clear_4
    clrf        stock_004_acc, ACCESS
    movlb       0x0
    movlw       0xDB
    rcall       ram_block_clear_4
    clrf        stock_004_acc, ACCESS
    movlb       0x0
    movlw       0xDF
    rcall       ram_block_clear_4
    rcall       prep_bank1_ram004
    movlw       0xD9
    rcall       ram_block_clear_4
    clrf        stock_004_acc, ACCESS
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
    clrf        stock_059_acc, ACCESS
flow_main_i2c_service_2100_217a:
    rlncf       stock_059_acc, W, ACCESS                ; W = counter * 2
    addlw       LOW(main_i2c_service_2100_dispatch_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(main_i2c_service_2100_dispatch_table)
    movwf       TBLPTRH, ACCESS
    clrf        TBLPTRU, ACCESS
    tblrd*+
    movff       TABLAT, FSR1L
    tblrd*+
    movff       TABLAT, FSR1H
    movf        stock_059_acc, W, ACCESS
    movlb       0x0
    addlw       0x60
    call        fsr2_page0_read_w, 0x0               ; W04-E03
    call        main_core_service_4448, 0x0
    movff       stock_0A0_b0_phys, POSTINC1
    movff       stock_0B9_b0_phys, INDF1
    incf        stock_059_acc, F, ACCESS
    movlw       0x05
    cpfsgt      stock_059_acc, ACCESS
    bra         flow_main_i2c_service_2100_217a

    ; --- Part 3: 7 I2C transactions with source-table indexed copy ------
    ; Replaces a 7-way xorlw chain + 7 switch targets (~154 B) with a
    ; table lookup into `main_i2c_service_2100_source_table` plus a
    ; 4-byte movff copy through FSR1.  The I2C transaction body below is
    ; unchanged from the pre-rewrite function.
    ; -------------------------------------------------------------------
    clrf        stock_05A_acc, ACCESS
flow_main_i2c_service_2100_226a:
    rlncf       stock_05A_acc, W, ACCESS                ; W = counter * 2
    addlw       LOW(main_i2c_service_2100_source_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(main_i2c_service_2100_source_table)
    movwf       TBLPTRH, ACCESS
    clrf        TBLPTRU, ACCESS
    tblrd*+
    movff       TABLAT, FSR1L
    tblrd*+
    movff       TABLAT, FSR1H
    movff       POSTINC1, stock_06A_b0_phys
    movff       POSTINC1, stock_06B_b0_phys
    movff       POSTINC1, stock_06C_b0_phys
    movff       INDF1, stock_06D_b0_phys
flow_main_i2c_service_2100_2286:
    bsf         SSPCON2, 0, ACCESS
    call        wait_sen_bounded, 0x0
    bc          main_i2c_service_2100_timeout
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlb       0x1
    movlw       0x0F
    addwf       stock_05A_acc, W, ACCESS
    rcall       setup_fsr2_page_1_or_2
    movf        INDF2, W, ACCESS
    call        i2c_byte_tx, 0x0
    clrf        stock_05B_acc, ACCESS
flow_main_i2c_service_2100_22a8:
    movf        stock_05B_acc, W, ACCESS
    movlb       0x0
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    cpfseq      INDF2, ACCESS
    bra         flow_main_i2c_service_2100_22c2
    clrf        i2c_coeff_0_acc, ACCESS
    clrf        i2c_coeff_1_acc, ACCESS
    clrf        i2c_coeff_2_acc, ACCESS
    movlw       0x3F
    bra         flow_main_i2c_service_2100_22da
flow_main_i2c_service_2100_22c2:
    movf        stock_05B_acc, W, ACCESS
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x03
    cpfseq      INDF2, ACCESS
    bra         flow_main_i2c_service_2100_22de
    clrf        i2c_coeff_0_acc, ACCESS
    clrf        i2c_coeff_1_acc, ACCESS
    movlw       0x80
    movwf       i2c_coeff_2_acc, ACCESS
    movlw       0xBF
flow_main_i2c_service_2100_22da:
    movwf       i2c_coeff_3_acc, ACCESS
    bra         flow_main_i2c_service_2100_22fc
flow_main_i2c_service_2100_22de:
    movf        stock_05B_acc, W, ACCESS
    addlw       0x6A
    call        fsr2_page0_read_w, 0x0               ; W04-E03
    call        main_core_service_45ce, 0x0
    movff       stock_00D_b0_phys, i2c_coeff_0_b0_phys
    movff       stock_00E_b0_phys, i2c_coeff_1_b0_phys
    movff       stock_00F_b0_phys, i2c_coeff_2_b0_phys
    movff       stock_010_b0_phys, i2c_coeff_3_b0_phys
flow_main_i2c_service_2100_22fc:
    movff       i2c_coeff_0_b0_phys, stock_049_b0_phys
    movff       i2c_coeff_1_b0_phys, stock_04A_b0_phys
    movff       i2c_coeff_2_b0_phys, stock_04B_b0_phys
    movff       i2c_coeff_3_b0_phys, stock_04C_b0_phys
    call        main_i2c_service_39a6, 0x0
    incf        stock_05B_acc, F, ACCESS
    movlw       0x03
    cpfsgt      stock_05B_acc, ACCESS
    bra         flow_main_i2c_service_2100_22a8
    bsf         SSPCON2, 2, ACCESS
    call        wait_pen_bounded, 0x0
    bc          main_i2c_service_2100_pen_timeout
    incf        stock_05A_acc, F, ACCESS
    movlw       0x06
    cpfsgt      stock_05A_acc, ACCESS
    bra         flow_main_i2c_service_2100_226a
    retlw       0x06
main_i2c_service_2100_timeout:
    call        i2c_timeout_recover_advertise, 0x0
    retlw       0x06
main_i2c_service_2100_pen_timeout:
    call        i2c_pen_timeout_recover_advertise, 0x0
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
    movff       stock_0C1_b0_phys, stock_15A_b1_phys
    bra         flow_main_core_service_2328_2472
flow_main_core_service_2328_232e:
    movff       stock_0C2_b0_phys, stock_15B_b1_phys
    movlw       0x02
    movwf       stock_003_acc, ACCESS
flow_main_core_service_2328_2336:
    movlw       0xBE
    addwf       stock_003_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    rcall       main_core_service_24ac
    movlw       0x1F
    cpfsgt      stock_003_acc, ACCESS
    bra         flow_main_core_service_2328_2336
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_234a:
    movff       stock_0C2_b0_phys, stock_15B_b1_phys
    decf        stock_0C2_b0, W, BANKED
    bnz         flow_main_core_service_2328_235c
    movff       stock_0B7_b0_phys, stock_15C_b1_phys
    movff       stock_0B8_b0_phys, stock_15D_b1_phys
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_235c:
    movf        stock_0C2_b0, W, BANKED
    xorlw       0x02
    bz          flow_main_core_service_2328_2364
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2364:
    movff       stock_0B5_b0_phys, stock_15E_b1_phys
    movlw       0x05
    movwf       stock_003_acc, ACCESS
flow_main_core_service_2328_236c:
    movlw       0xFB
    addwf       stock_003_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    rcall       main_core_service_24ac
    movlw       0x13
    cpfsgt      stock_003_acc, ACCESS
    bra         flow_main_core_service_2328_236c
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2380:
    movff       stock_093_b0_phys, stock_15B_b1_phys
    movff       input_select_b0_phys, stock_15C_b1_phys
    movlb       0x1
    clrf        stock_15D_b1, BANKED
    clrf        stock_15E_b1, BANKED
    movff       computed_volume_3_b0_phys, stock_15F_b1_phys
    movff       computed_volume_2_b0_phys, stock_160_b1_phys
    movff       computed_volume_1_b0_phys, stock_161_b1_phys
    movff       computed_volume_b0_phys, stock_162_b1_phys
    movlw       0x00
    btfsc       active_flags_acc, 4, ACCESS
    movlw       0x01
    movwf       stock_163_b1, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       stock_0A4_b0, 0, BANKED
    movlw       0x01
    movlb       0x1
    movwf       stock_164_b1, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       stock_0A4_b0, 1, BANKED
    movlw       0x01
    movlb       0x1
    movwf       stock_165_b1, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       stock_0A4_b0, 2, BANKED
    movlw       0x01
    movlb       0x1
    movwf       stock_166_b1, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       stock_0A4_b0, 3, BANKED
    movlw       0x01
    movlb       0x1
    movwf       stock_168_b1, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       stock_0A4_b0, 4, BANKED
    movlw       0x01
    movlb       0x1
    movwf       stock_169_b1, BANKED
    movlw       0x00
    movlb       0x0
    btfsc       stock_0A4_b0, 5, BANKED
    movlw       0x01
    movlb       0x1
    movwf       stock_16A_b1, BANKED
    movff       stock_060_b0_phys, stock_16C_b1_phys
    movff       stock_061_b0_phys, stock_16D_b1_phys
    movff       stock_062_b0_phys, stock_16E_b1_phys
    movff       stock_063_b0_phys, stock_16F_b1_phys
    movff       stock_064_b0_phys, stock_170_b1_phys
    movff       stock_065_b0_phys, stock_171_b1_phys
    movff       stock_0B4_b0_phys, stock_178_b1_phys
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_240c:
    movlw       0x03
    movlb       0x1
    movwf       stock_15B_b1, BANKED
    movlw       0x03                        ; V3.4: major version = 3
    movwf       stock_15C_b1, BANKED
    movlw       0x04                        ; V3.4: minor version = 4
    movwf       stock_15D_b1, BANKED
    movff       input_select_b0_phys, stock_15E_b1_phys
    clrf        stock_15F_b1, BANKED
    clrf        stock_160_b1, BANKED
    clrf        stock_161_b1, BANKED
    movff       stock_05F_b0_phys, stock_163_b1_phys
    movlw       0x06
    movwf       stock_164_b1, BANKED
    movlw       0x0F
    movwf       stock_165_b1, BANKED
    movwf       stock_166_b1, BANKED
    movwf       stock_167_b1, BANKED
    movwf       stock_168_b1, BANKED
    movwf       stock_169_b1, BANKED
    movwf       stock_16A_b1, BANKED
    movlw       0x0A
    movwf       stock_16B_b1, BANKED
    movwf       stock_16C_b1, BANKED
    movwf       stock_16D_b1, BANKED
    movwf       stock_16E_b1, BANKED
    movwf       stock_16F_b1, BANKED
    movwf       stock_170_b1, BANKED
    movlw       0x01
    movwf       stock_171_b1, BANKED
    movwf       stock_172_b1, BANKED
    movff       stock_09B_b0_phys, stock_173_b1_phys
    movff       stock_09C_b0_phys, stock_174_b1_phys
    movff       stock_09D_b0_phys, stock_175_b1_phys
    movff       stock_09E_b0_phys, stock_176_b1_phys
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2460:
    movff       stock_11B_b1_phys, stock_15B_b1_phys
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2466:
    movlb       0x1
    clrf        stock_15B_b1, BANKED
    clrf        stock_15C_b1, BANKED
    clrf        stock_15D_b1, BANKED
    clrf        stock_15E_b1, BANKED
    bra         flow_main_core_service_2328_24a6
flow_main_core_service_2328_2472:
    movlb       0x0
    movf        stock_0C1_b0, W, BANKED
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
    clrf        stock_0C1_b0, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_24ac
; Address : 0x24AC
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_24ac:
    addwfc      FSR2H, F, ACCESS
    movlw       0x5A
    addwf       stock_003_acc, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x01
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    incf        stock_003_acc, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_24c2
; Address : 0x24C2
; Notes   : Inferred core helper routine. Calls: main_core_service_2650, main_core_service_263e, main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_24c2:
    movff       stock_020_b0_phys, stock_028_b0_phys
    movff       stock_021_b0_phys, stock_029_b0_phys
    movff       stock_022_b0_phys, stock_02A_b0_phys
    movff       stock_023_b0_phys, stock_02B_b0_phys
    movlw       0x18
    bra         flow_main_core_service_24c2_24d8
flow_main_core_service_24c2_24d6:
    rcall       main_core_service_2650
flow_main_core_service_24c2_24d8:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_24c2_24d6
    movf        stock_028_acc, W, ACCESS
    movwf       stock_02E_acc, ACCESS
    movff       stock_024_b0_phys, stock_028_b0_phys
    movff       stock_025_b0_phys, stock_029_b0_phys
    movff       stock_026_b0_phys, stock_02A_b0_phys
    movff       stock_027_b0_phys, stock_02B_b0_phys
    movlw       0x18
    bra         flow_main_core_service_24c2_24f6
flow_main_core_service_24c2_24f4:
    rcall       main_core_service_2650
flow_main_core_service_24c2_24f6:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_24c2_24f4
    movf        stock_028_acc, W, ACCESS
    movwf       stock_02D_acc, ACCESS
    movf        stock_02E_acc, W, ACCESS
    bz          flow_main_core_service_24c2_2514
    movf        stock_02D_acc, W, ACCESS
    subwf       stock_02E_acc, W, ACCESS
    bc          flow_main_core_service_24c2_2526
    movf        stock_02E_acc, W, ACCESS
    subwf       stock_02D_acc, W, ACCESS
    movwf       stock_028_acc, ACCESS
    movlw       0x21
    subwf       stock_028_acc, W, ACCESS
    bnc         flow_main_core_service_24c2_2526
flow_main_core_service_24c2_2514:
    movff       stock_024_b0_phys, stock_020_b0_phys
    movff       stock_025_b0_phys, stock_021_b0_phys
    movff       stock_026_b0_phys, stock_022_b0_phys
    movff       stock_027_b0_phys, stock_023_b0_phys
    bra         flow_main_core_service_24c2_263c
flow_main_core_service_24c2_2526:
    movf        stock_02D_acc, W, ACCESS
    bz          flow_main_core_service_24c2_253c
    movf        stock_02E_acc, W, ACCESS
    subwf       stock_02D_acc, W, ACCESS
    bc          flow_main_core_service_24c2_254e
    movf        stock_02D_acc, W, ACCESS
    subwf       stock_02E_acc, W, ACCESS
    movwf       stock_028_acc, ACCESS
    movlw       0x21
    subwf       stock_028_acc, W, ACCESS
    bnc         flow_main_core_service_24c2_254e
flow_main_core_service_24c2_253c:
    bra         flow_main_core_service_24c2_263c
flow_main_core_service_24c2_254e:
    movlw       0x06
    movwf       stock_02C_acc, ACCESS
    btfsc       stock_023_acc, 7, ACCESS
    bsf         stock_02C_acc, 7, ACCESS
    btfsc       stock_027_acc, 7, ACCESS
    bsf         stock_02C_acc, 6, ACCESS
    bsf         stock_022_acc, 7, ACCESS
    clrf        stock_023_acc, ACCESS
    bsf         stock_026_acc, 7, ACCESS
    clrf        stock_027_acc, ACCESS
    movf        stock_02D_acc, W, ACCESS
    subwf       stock_02E_acc, W, ACCESS
    bc          flow_main_core_service_24c2_259c
flow_main_core_service_24c2_2568:
    bcf         STATUS, 0, ACCESS
    rlcf        stock_024_acc, F, ACCESS
    rlcf        stock_025_acc, F, ACCESS
    rlcf        stock_026_acc, F, ACCESS
    rlcf        stock_027_acc, F, ACCESS
    decf        stock_02D_acc, F, ACCESS
    movf        stock_02D_acc, W, ACCESS
    xorwf       stock_02E_acc, W, ACCESS
    bz          flow_main_core_service_24c2_2594
    decf        stock_02C_acc, F, ACCESS
    movff       stock_02C_b0_phys, stock_028_b0_phys
    movlw       0x07
    andwf       stock_028_acc, F, ACCESS
    bz          flow_main_core_service_24c2_2594
    bra         flow_main_core_service_24c2_2568
flow_main_core_service_24c2_2588:
    bcf         STATUS, 0, ACCESS
    rrcf        stock_023_acc, F, ACCESS
    rrcf        stock_022_acc, F, ACCESS
    rrcf        stock_021_acc, F, ACCESS
    rrcf        stock_020_acc, F, ACCESS
    incf        stock_02E_acc, F, ACCESS
flow_main_core_service_24c2_2594:
    movf        stock_02D_acc, W, ACCESS
    cpfseq      stock_02E_acc, ACCESS
    bra         flow_main_core_service_24c2_2588
    bra         flow_main_core_service_24c2_25d4
flow_main_core_service_24c2_259c:
    movf        stock_02E_acc, W, ACCESS
    subwf       stock_02D_acc, W, ACCESS
    bc          flow_main_core_service_24c2_25d4
flow_main_core_service_24c2_25a2:
    bcf         STATUS, 0, ACCESS
    rlcf        stock_020_acc, F, ACCESS
    rlcf        stock_021_acc, F, ACCESS
    rlcf        stock_022_acc, F, ACCESS
    rlcf        stock_023_acc, F, ACCESS
    decf        stock_02E_acc, F, ACCESS
    movf        stock_02D_acc, W, ACCESS
    xorwf       stock_02E_acc, W, ACCESS
    bz          flow_main_core_service_24c2_25ce
    decf        stock_02C_acc, F, ACCESS
    movff       stock_02C_b0_phys, stock_028_b0_phys
    movlw       0x07
    andwf       stock_028_acc, F, ACCESS
    bz          flow_main_core_service_24c2_25ce
    bra         flow_main_core_service_24c2_25a2
flow_main_core_service_24c2_25c2:
    bcf         STATUS, 0, ACCESS
    rrcf        stock_027_acc, F, ACCESS
    rrcf        stock_026_acc, F, ACCESS
    rrcf        stock_025_acc, F, ACCESS
    rrcf        stock_024_acc, F, ACCESS
    incf        stock_02D_acc, F, ACCESS
flow_main_core_service_24c2_25ce:
    movf        stock_02D_acc, W, ACCESS
    cpfseq      stock_02E_acc, ACCESS
    bra         flow_main_core_service_24c2_25c2
flow_main_core_service_24c2_25d4:
    btfss       stock_02C_acc, 7, ACCESS
    bra         flow_main_core_service_24c2_25ea
    comf        stock_020_acc, F, ACCESS
    comf        stock_021_acc, F, ACCESS
    comf        stock_022_acc, F, ACCESS
    comf        stock_023_acc, F, ACCESS
    incf        stock_020_acc, F, ACCESS
    movlw       0x00
    addwfc      stock_021_acc, F, ACCESS
    addwfc      stock_022_acc, F, ACCESS
    addwfc      stock_023_acc, F, ACCESS
flow_main_core_service_24c2_25ea:
    btfss       stock_02C_acc, 6, ACCESS
    bra         flow_main_core_service_24c2_25f2
    comf        stock_024_acc, F, ACCESS
    rcall       main_core_service_263e
flow_main_core_service_24c2_25f2:
    clrf        stock_02C_acc, ACCESS
    movf        stock_020_acc, W, ACCESS
    addwf       stock_024_acc, F, ACCESS
    movf        stock_021_acc, W, ACCESS
    addwfc      stock_025_acc, F, ACCESS
    movf        stock_022_acc, W, ACCESS
    addwfc      stock_026_acc, F, ACCESS
    movf        stock_023_acc, W, ACCESS
    addwfc      stock_027_acc, F, ACCESS
    btfss       stock_027_acc, 7, ACCESS
    bra         flow_main_core_service_24c2_2610
    comf        stock_024_acc, F, ACCESS
    rcall       main_core_service_263e
    movlw       0x01
    movwf       stock_02C_acc, ACCESS
flow_main_core_service_24c2_2610:
    movff       stock_024_b0_phys, stock_003_b0_phys
    movff       stock_025_b0_phys, stock_004_b0_phys
    movff       stock_026_b0_phys, saved_w_b0_phys
    movff       stock_027_b0_phys, stock_006_b0_phys
    movff       stock_02E_b0_phys, stock_007_b0_phys
    movff       stock_02C_b0_phys, stock_008_b0_phys
    call        main_core_service_30d8, 0x0
    movff       stock_003_b0_phys, stock_020_b0_phys
    movff       stock_004_b0_phys, stock_021_b0_phys
    movff       saved_w_b0_phys, stock_022_b0_phys
    movff       stock_006_b0_phys, stock_023_b0_phys
flow_main_core_service_24c2_263c:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_263e
; Address : 0x263E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_263e:
    comf        stock_025_acc, F, ACCESS
    comf        stock_026_acc, F, ACCESS
    comf        stock_027_acc, F, ACCESS
    incf        stock_024_acc, F, ACCESS
    movlw       0x00
    addwfc      stock_025_acc, F, ACCESS
    addwfc      stock_026_acc, F, ACCESS
    addwfc      stock_027_acc, F, ACCESS
    retlw       0x00


; ---------------------------------------------------------------------------
; Function: main_core_service_2650
; Address : 0x2650
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2650:
    bcf         STATUS, 0, ACCESS
    rrcf        stock_02B_acc, F, ACCESS
    rrcf        stock_02A_acc, F, ACCESS
    rrcf        stock_029_acc, F, ACCESS
    rrcf        stock_028_acc, F, ACCESS
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
    btfss       event_flags_b0, 0, BANKED
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
    btfss       filename_dirty_flags_b0, 4, BANKED
    bra         flow_main_core_service_265c_27bc
    movlw       0x50
    movwf       stock_00A_acc, ACCESS
flow_main_core_service_265c_2794:
    movff       stock_00A_b0_phys, stock_007_b0_phys
    clrf        stock_008_acc, ACCESS
    movlb       0x1
    movlw       0xB0
    addwf       stock_00A_acc, W, ACCESS
    call        setup_fsr2_page_1, 0x0
    movf        INDF2, W, ACCESS
    movwf       stock_009_acc, ACCESS
    call        main_flash_service_46de, 0x0
    incf        stock_00A_acc, F, ACCESS
    movlw       0x5E
    cpfsgt      stock_00A_acc, ACCESS
    bra         flow_main_core_service_265c_2794
    movlb       0x0
    bcf         filename_dirty_flags_b0, 4, BANKED
flow_main_core_service_265c_27bc:
    btfss       filename_dirty_flags_b0, 5, BANKED
    bra         flow_main_core_service_265c_27ec
    call        preset_persist_filename, 0x0
flow_main_core_service_265c_27ec:
    ; V3.2 USB-xact gate: ALWAYS clear bit6 when the host triggers
    ; the dirty-service path (event_flags.0 = 1), regardless of
    ; whether bit5 was set when this dispatcher ran.  bit5 may have
    ; ALREADY been cleared by preset_job_pending's persist branch
    ; (asm:9568) before main_core_service_265c got to it -- if so,
    ; the bit5 test above branches over the persist call and bit6
    ; would stay set forever, locking the gate (codex MEDIUM vs
    ; f3b25d6).  Putting the bit6 clear AFTER the bit5 branch
    ; closes ensures both paths converge here.  Explicit movlb 0x0
    ; because preset_persist_filename (when it runs) calls
    ; main_flash_service_46de which may leave BSR in a different
    ; bank.
    movlb       0x0
    bcf         filename_dirty_flags_b0, 6, BANKED
    bcf         event_flags_b0, 0, BANKED
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
    movwf       stock_00A_acc, ACCESS                ; save the bit mask
    tblrd*+                                      ; fetch record count
    movff       TABLAT, stock_013_b0_phys
    movf        filename_dirty_flags_b0, W, BANKED             ; BSR = 0 on entry
    andwf       stock_00A_acc, W, ACCESS
    movwf       stock_00B_acc, ACCESS                ; non-zero => do the work
eeprom_persist_record_loop:
    tblrd*+                                      ; fetch EEPROM offset
    movff       TABLAT, stock_007_b0_phys
    tblrd*+                                      ; fetch bank-0 src_lo
    movff       TABLAT, FSR0L
    clrf        FSR0H, ACCESS                    ; all source RAM in bank 0
    movf        stock_00B_acc, F, ACCESS             ; is the gate still set?
    btfsc       STATUS, 2, ACCESS                ; Z => bit was clear
    bra         eeprom_persist_record_next
    clrf        stock_008_acc, ACCESS
    movff       INDF0, stock_009_b0_phys
    call        main_flash_service_46de, 0x0
eeprom_persist_record_next:
    decfsz      stock_013_acc, F, ACCESS
    bra         eeprom_persist_record_loop
    movf        stock_00B_acc, F, ACCESS
    btfsc       STATUS, 2, ACCESS                ; gate was clear: no bit to clear
    return      0
    movlb       0x0
    comf        stock_00A_acc, W, ACCESS             ; W = ~mask
    andwf       filename_dirty_flags_b0, F, BANKED             ; drop only this block's bit
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
    btfss       active_flags_acc, 3, ACCESS
    bra         flow_main_i2c_service_27f0_297c
    movlw       0x64
    movlb       0x0
    cpfsgt      stock_0BB_b0, BANKED
    bra         flow_main_i2c_service_27f0_297a
    clrf        stock_0BB_b0, BANKED
    bra         flow_main_i2c_service_27f0_28aa
flow_main_i2c_service_27f0_2800:
    movf        stock_0B6_b0, W, BANKED
    addlw       0x08
    movwf       stock_0BE_b0, BANKED
    bra         flow_main_i2c_service_27f0_28ce
flow_main_i2c_service_27f0_28aa:
    movf        input_select_b0, W, BANKED
    bz          flow_main_i2c_service_27f0_2800
    movlw       0x09
    cpfslt      input_select_b0, BANKED       ; valid fixed inputs are 1..8
    bra         flow_main_i2c_service_27f0_28ce
    movf        input_select_b0, W, BANKED
    addlw       0xFF                       ; W = input_select - 1
    movwf       stock_003_acc, ACCESS          ; table column
    movlw       0x03
    cpfsgt      stock_05F_acc, ACCESS          ; status > 3 uses overflow row
    bra         flow_main_i2c_service_27f0_route_status_ok
    movlw       0x04
    bra         flow_main_i2c_service_27f0_route_status_ready
flow_main_i2c_service_27f0_route_status_ok:
    movf        stock_05F_acc, W, ACCESS
flow_main_i2c_service_27f0_route_status_ready:
    movwf       stock_004_acc, ACCESS
    rlncf       stock_004_acc, F, ACCESS
    rlncf       stock_004_acc, F, ACCESS
    rlncf       stock_004_acc, W, ACCESS       ; W = row * 8
    addwf       stock_003_acc, W, ACCESS       ; W = row * 8 + column
    addlw       LOW(main_i2c_service_27f0_route_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(main_i2c_service_27f0_route_table)
    btfsc       STATUS, C, ACCESS          ; carry from low-byte table index
    addlw       0x01
    movwf       TBLPTRH, ACCESS
    clrf        TBLPTRU, ACCESS
    tblrd*
    movff       TABLAT, stock_093_b0_phys
flow_main_i2c_service_27f0_28ce:
    tstfsz      input_select_b0, BANKED
    bra         flow_main_i2c_service_27f0_2902
    tstfsz      stock_0BA_b0, BANKED
    bra         flow_main_i2c_service_27f0_ad_wait
    movff       stock_0BE_b0_phys, stock_006_b0_phys
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlb       0x0
    movlw       0x12                            ; candidate settle countdown
    movwf       stock_0BA_b0, BANKED
    bra         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_ad_wait:
    decfsz      stock_0BA_b0, F, BANKED
    bra         flow_main_i2c_service_27f0_295c
    movlw       0x13
    call        i2c_secondary_dev_random_read, 0x0
    bc          flow_main_i2c_service_27f0_ad_monitor_timeout
    movlb       0x0
    movwf       stock_0BE_b0, BANKED
    tstfsz      stock_0BE_b0, BANKED
    bra         flow_main_i2c_service_27f0_290a
    movf        stock_0AB_b0, W, BANKED
    bz          flow_main_i2c_service_27f0_ad_scan_miss
    ; V3.4 rev 0x88 hardening: 0x13.RXCKR is a recovered-clock rate
    ; CLASSIFIER that reads 0 transiently (re-measure windows, jitter,
    ; rate boundaries, source-side re-clocking) while audio passes.  The
    ; stock-lineage 2-consecutive-miss confirm tore the route down on
    ; sub-second status bursts (live 2026-06-12: L+5 in 20 min on a
    ; continuous -60 dB source).  Require 6 consecutive misses (~2-3 s);
    ; the held route stays applied through the confirmation window.
    movlb       0x02
    incf        src4382_loss_debounce_b2, F, BANKED
    movlw       0x06
    cpfslt      src4382_loss_debounce_b2, BANKED
    bra         flow_main_i2c_service_27f0_ad_loss_confirmed
    movlb       0x0
    movff       stock_0AB_b0_phys, stock_093_b0_phys
    bra         flow_main_i2c_service_27f0_ad_monitor
flow_main_i2c_service_27f0_ad_loss_confirmed:
    clrf        src4382_loss_debounce_b2, BANKED
    ; V3.4 forensic L: one count per debounce-confirmed Auto-Detect loss.
    movlw       0x01                        ; index 1 = L
    call        diag_src_inc_w, 0x0
    movlb       0x0
flow_main_i2c_service_27f0_ad_scan_miss:
    clrf        stock_093_b0, BANKED
    incf        stock_0B6_b0, F, BANKED
    movf        stock_0B6_b0, W, BANKED
    xorlw       0x04
    bnz         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_2902:
    clrf        stock_0B6_b0, BANKED
    clrf        stock_0BA_b0, BANKED
    movlb       0x02
    clrf        src4382_loss_debounce_b2, BANKED
    movlb       0x0
    bra         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_ad_monitor_timeout:
    movlb       0x0
    bra         flow_main_i2c_service_27f0_295c
flow_main_i2c_service_27f0_290a:
    movlb       0x02
    clrf        src4382_loss_debounce_b2, BANKED
    movlb       0x0
    tstfsz      stock_0B6_b0, BANKED
    bra         flow_main_i2c_service_27f0_2912
    movlw       0x03
    movwf       stock_093_b0, BANKED
flow_main_i2c_service_27f0_2912:
    decf        stock_0B6_b0, W, BANKED
    bnz         flow_main_i2c_service_27f0_291a
    movlw       0x01
    movwf       stock_093_b0, BANKED
flow_main_i2c_service_27f0_291a:
    movf        stock_0B6_b0, W, BANKED
    xorlw       0x02
    bnz         flow_main_i2c_service_27f0_2924
    movlw       0x02
    movwf       stock_093_b0, BANKED
flow_main_i2c_service_27f0_2924:
    movf        stock_0B6_b0, W, BANKED
    xorlw       0x03
    bnz         flow_main_i2c_service_27f0_292e
    movlw       0x04
    movwf       stock_093_b0, BANKED
flow_main_i2c_service_27f0_292e:
    movlw       0x12
    call        i2c_secondary_dev_random_read, 0x0
    bc          flow_main_i2c_service_27f0_ad_monitor
    movlb       0x0
    movwf       stock_0BF_b0, BANKED
    movf        stock_0BF_b0, W, BANKED
    bnz         flow_main_i2c_service_27f0_nonpcm_mute
    btfsc       stock_094_b0, 5, BANKED
    bra         flow_main_i2c_service_27f0_mute_status
    movlb       0x2
    movf        preset_job_state_b2, F, BANKED
    movlb       0x0
    btfsc       STATUS, 2, ACCESS
    bcf         active_flags_acc, 4, ACCESS
    bra         flow_main_i2c_service_27f0_mute_status
flow_main_i2c_service_27f0_nonpcm_mute:
    ; V3.4 forensic N: count mute EPISODES (active_flags.4 0->1 edges), not
    ; monitor passes — the monitor re-runs this branch every poll while
    ; reg 0x12 stays non-PCM.
    btfsc       active_flags_acc, 4, ACCESS
    bra         flow_main_i2c_service_27f0_nonpcm_set
    movlw       0x00                        ; index 0 = N
    call        diag_src_inc_w, 0x0
flow_main_i2c_service_27f0_nonpcm_set:
    bsf         active_flags_acc, 4, ACCESS
flow_main_i2c_service_27f0_mute_status:
    movlw       0x01
    btfss       active_flags_acc, 4, ACCESS
    movlw       0x00
    movwf       stock_008_acc, ACCESS
    movlw       0x01
    btfss       active_flags_acc, 5, ACCESS
    movlw       0x00
    xorwf       stock_008_acc, F, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         event_flags_b0, 5, BANKED
    btfss       active_flags_acc, 4, ACCESS
    bra         flow_main_i2c_service_27f0_295a
    bsf         active_flags_acc, 5, ACCESS
    bra         flow_main_i2c_service_27f0_ad_monitor
flow_main_i2c_service_27f0_295a:
    bcf         active_flags_acc, 5, ACCESS
flow_main_i2c_service_27f0_ad_monitor:
    movlw       0x28                            ; source-present monitor countdown
    movlb       0x0
    movwf       stock_0BA_b0, BANKED
flow_main_i2c_service_27f0_295c:
    movlb       0x0
    movf        stock_093_b0, W, BANKED
    xorlw       0x02
    btfsc       STATUS, 2, ACCESS
    btfsc       PORTC, 0, ACCESS
    bra         flow_main_i2c_service_27f0_296c
    movff       stock_0C3_b0_phys, stock_093_b0_phys
flow_main_i2c_service_27f0_296c:
    movf        stock_0AB_b0, W, BANKED
    xorwf       stock_093_b0, W, BANKED
    bz          flow_main_i2c_service_27f0_route_same
    bsf         event_flags_b0, 1, BANKED
    ; V3.4 forensic C: each applied route change (incl. ->no-route on loss).
    movlw       0x02                        ; index 2 = C
    call        diag_src_inc_w, 0x0
flow_main_i2c_service_27f0_route_same:
    movff       stock_093_b0_phys, stock_0AB_b0_phys
    bra         flow_main_i2c_service_27f0_297c
flow_main_i2c_service_27f0_297a:
    incf        stock_0BB_b0, F, BANKED
flow_main_i2c_service_27f0_297c:
    return      0


; ---------------------------------------------------------------------------
; Data: main_i2c_service_27f0_route_table  (status row × input column)
; ---------------------------------------------------------------------------
; Rows are SRC status 0..3 plus an overflow row for impossible status bytes.
; Columns are fixed input_select 1..8. Values are the same intermediate
; ram_0x093 route requests produced by the old branch ladder before the
; existing PORTC.0 route-2 fallback below `flow_..._295c` runs.
; ---------------------------------------------------------------------------
main_i2c_service_27f0_route_table:
    db  0x00, 0x01, 0x02, 0x03, 0x04, 0x00, 0x00, 0x00
    db  0x00, 0x05, 0x01, 0x02, 0x03, 0x04, 0x00, 0x00
    db  0x00, 0x05, 0x06, 0x01, 0x02, 0x03, 0x04, 0x00
    db  0x00, 0x05, 0x06, 0x07, 0x01, 0x02, 0x03, 0x04
    db  0x00, 0x05, 0x06, 0x03, 0x04, 0x00, 0x00, 0x00


; ---------------------------------------------------------------------------
; Function: main_core_service_297e
; Address : 0x297E
; Notes   : Inferred core helper routine. Calls: main_core_service_2ca8, main_core_service_24c2, main_core_service_3ec4.
; ---------------------------------------------------------------------------
main_core_service_297e:
    clrf        stock_011_acc, ACCESS
    clrf        stock_012_acc, ACCESS
    movlw       0x80
    movwf       stock_013_acc, ACCESS
    movlw       0x44
    movwf       stock_014_acc, ACCESS
    movff       stock_02F_b0_phys, stock_00D_b0_phys
    movff       stock_030_b0_phys, stock_00E_b0_phys
    movff       stock_031_b0_phys, stock_00F_b0_phys
    movff       stock_032_b0_phys, stock_010_b0_phys
    rcall       main_core_service_2ca8
    movff       stock_00D_b0_phys, stock_020_b0_phys
    movff       stock_00E_b0_phys, stock_021_b0_phys
    movff       stock_00F_b0_phys, stock_022_b0_phys
    movff       stock_010_b0_phys, stock_023_b0_phys
    clrf        stock_024_acc, ACCESS
    clrf        stock_025_acc, ACCESS
    movlw       0x80
    movwf       stock_026_acc, ACCESS
    movlw       0x3F
    movwf       stock_027_acc, ACCESS
    rcall       main_core_service_24c2
    movff       stock_020_b0_phys, stock_02F_b0_phys
    movff       stock_021_b0_phys, stock_030_b0_phys
    movff       stock_022_b0_phys, stock_031_b0_phys
    movff       stock_023_b0_phys, stock_032_b0_phys
    movlw       0x0A
    movwf       stock_011_acc, ACCESS
flow_main_core_service_297e_apply_loop:
    movff       stock_02F_b0_phys, stock_025_b0_phys
    movff       stock_030_b0_phys, stock_026_b0_phys
    movff       stock_031_b0_phys, stock_027_b0_phys
    movff       stock_032_b0_phys, stock_028_b0_phys
    movlw       0x2F
    call        main_core_service_3ec4, 0x0
    decfsz      stock_011_acc, F, ACCESS
    bra         flow_main_core_service_297e_apply_loop
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2abc
; Address : 0x2ABC
; Notes   : Inferred core helper routine. Calls: main_core_service_2bac, main_core_service_2b8e, main_core_service_2b9e.
; ---------------------------------------------------------------------------
main_core_service_2abc:
    movff       stock_012_b0_phys, stock_01A_b0_phys
    movff       stock_013_b0_phys, stock_01B_b0_phys
    movff       stock_014_b0_phys, stock_01C_b0_phys
    movff       stock_015_b0_phys, stock_01D_b0_phys
    movlw       0x18
    bra         flow_main_core_service_2abc_2ad2
flow_main_core_service_2abc_2ad0:
    rcall       main_core_service_2bac
flow_main_core_service_2abc_2ad2:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2abc_2ad0
    movf        stock_01A_acc, W, ACCESS
    movwf       stock_01E_acc, ACCESS
    tstfsz      stock_01E_acc, ACCESS
    bra         flow_main_core_service_2abc_2ae0
    bra         flow_main_core_service_2abc_2b02
flow_main_core_service_2abc_2ae0:
    movff       stock_016_b0_phys, stock_01A_b0_phys
    movff       stock_017_b0_phys, stock_01B_b0_phys
    movff       stock_018_b0_phys, stock_01C_b0_phys
    movff       stock_019_b0_phys, stock_01D_b0_phys
    movlw       0x18
    bra         flow_main_core_service_2abc_2af6
flow_main_core_service_2abc_2af4:
    rcall       main_core_service_2bac
flow_main_core_service_2abc_2af6:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2abc_2af4
    movf        stock_01A_acc, W, ACCESS
    movwf       stock_024_acc, ACCESS
    tstfsz      stock_024_acc, ACCESS
    bra         flow_main_core_service_2abc_2b0c
flow_main_core_service_2abc_2b02:
    clrf        stock_012_acc, ACCESS
    clrf        stock_013_acc, ACCESS
    clrf        stock_014_acc, ACCESS
    clrf        stock_015_acc, ACCESS
    bra         flow_main_core_service_2abc_2b8c
flow_main_core_service_2abc_2b0c:
    movf        stock_024_acc, W, ACCESS
    addlw       0x7B
    addwf       stock_01E_acc, F, ACCESS
    movff       stock_015_b0_phys, stock_024_b0_phys
    movf        stock_019_acc, W, ACCESS
    xorwf       stock_024_acc, F, ACCESS
    movlw       0x80
    andwf       stock_024_acc, F, ACCESS
    bsf         stock_014_acc, 7, ACCESS
    bsf         stock_018_acc, 7, ACCESS
    clrf        stock_019_acc, ACCESS
    clrf        stock_01F_acc, ACCESS
    clrf        stock_020_acc, ACCESS
    clrf        stock_021_acc, ACCESS
    clrf        stock_022_acc, ACCESS
    movlw       0x07
    movwf       stock_023_acc, ACCESS
flow_main_core_service_2abc_2b30:
    btfss       stock_012_acc, 0, ACCESS
    bra         flow_main_core_service_2abc_2b38
    movf        stock_016_acc, W, ACCESS
    rcall       main_core_service_2b8e
flow_main_core_service_2abc_2b38:
    rcall       main_core_service_2b9e
    rlcf        stock_016_acc, F, ACCESS
    rlcf        stock_017_acc, F, ACCESS
    rlcf        stock_018_acc, F, ACCESS
    rlcf        stock_019_acc, F, ACCESS
    decfsz      stock_023_acc, F, ACCESS
    bra         flow_main_core_service_2abc_2b30
    movlw       0x11
    movwf       stock_023_acc, ACCESS
flow_main_core_service_2abc_2b4a:
    btfss       stock_012_acc, 0, ACCESS
    bra         flow_main_core_service_2abc_2b52
    movf        stock_016_acc, W, ACCESS
    rcall       main_core_service_2b8e
flow_main_core_service_2abc_2b52:
    rcall       main_core_service_2b9e
    rrcf        stock_022_acc, F, ACCESS
    rrcf        stock_021_acc, F, ACCESS
    rrcf        stock_020_acc, F, ACCESS
    rrcf        stock_01F_acc, F, ACCESS
    decfsz      stock_023_acc, F, ACCESS
    bra         flow_main_core_service_2abc_2b4a
    movff       stock_01F_b0_phys, stock_003_b0_phys
    movff       stock_020_b0_phys, stock_004_b0_phys
    movff       stock_021_b0_phys, saved_w_b0_phys
    movff       stock_022_b0_phys, stock_006_b0_phys
    movff       stock_01E_b0_phys, stock_007_b0_phys
    movff       stock_024_b0_phys, stock_008_b0_phys
    rcall       main_core_service_30d8
    movff       stock_003_b0_phys, stock_012_b0_phys
    movff       stock_004_b0_phys, stock_013_b0_phys
    movff       saved_w_b0_phys, stock_014_b0_phys
    movff       stock_006_b0_phys, stock_015_b0_phys
flow_main_core_service_2abc_2b8c:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2b8e
; Address : 0x2B8E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2b8e:
    addwf       stock_01F_acc, F, ACCESS
    movf        stock_017_acc, W, ACCESS
    addwfc      stock_020_acc, F, ACCESS
    movf        stock_018_acc, W, ACCESS
    addwfc      stock_021_acc, F, ACCESS
    movf        stock_019_acc, W, ACCESS
    addwfc      stock_022_acc, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2b9e
; Address : 0x2B9E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2b9e:
    bcf         STATUS, 0, ACCESS
    rrcf        stock_015_acc, F, ACCESS
    rrcf        stock_014_acc, F, ACCESS
    rrcf        stock_013_acc, F, ACCESS
    rrcf        stock_012_acc, F, ACCESS
    bcf         STATUS, 0, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2bac
; Address : 0x2BAC
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_2bac:
    bcf         STATUS, 0, ACCESS
    rrcf        stock_01D_acc, F, ACCESS
    rrcf        stock_01C_acc, F, ACCESS
    rrcf        stock_01B_acc, F, ACCESS
    rrcf        stock_01A_acc, F, ACCESS
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
    movff       stock_082_b0_phys, stock_003_b0_phys
    movff       stock_083_b0_phys, stock_004_b0_phys
    clrf        stock_005_acc, ACCESS
    clrf        stock_006_acc, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_2bb8
; Address : 0x2BB8
; Notes   : Inferred flash helper routine. Calls: flash_read, flash_erase, flash_write.
; ---------------------------------------------------------------------------
main_flash_service_2bb8:
    tstfsz      stock_0C5_b0, BANKED
    bra         flow_main_flash_service_2bb8_2bdc
    rcall       flash_addr_setup_from_82_83
    clrf        stock_008_acc, ACCESS
    movlw       0xC0
    movwf       stock_007_acc, ACCESS
    movlb       0x3
    movlw       0x03
    movwf       stock_00A_acc, ACCESS
    clrf        stock_009_acc, ACCESS
    call        flash_read, 0x0
flow_main_flash_service_2bb8_2bdc:
    movlb       0x1
    movf        stock_11B_b1, W, BANKED
    bz          flow_main_flash_service_2bb8_2bea
    clrf        stock_01D_acc, ACCESS
    movlw       0x02
    movwf       stock_01C_acc, ACCESS
    bra         flow_main_flash_service_2bb8_2bee
flow_main_flash_service_2bb8_2bea:
    clrf        stock_01C_acc, ACCESS
    clrf        stock_01D_acc, ACCESS
flow_main_flash_service_2bb8_2bee:
    movff       stock_01C_b0_phys, stock_01E_b0_phys
    movlw       0x04
    movwf       stock_01F_acc, ACCESS
flow_main_flash_service_2bb8_2bf6:
    movlw       0x1A
    movwf       stock_018_acc, ACCESS
    movlw       0x01
    movwf       stock_019_acc, ACCESS
    movf        stock_01F_acc, W, ACCESS
    addwf       stock_018_acc, F, ACCESS
    movlw       0x00
    addwfc      stock_019_acc, F, ACCESS
    movf        stock_01E_acc, W, ACCESS
    subwf       stock_018_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    movf        stock_019_acc, W, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        stock_019_acc, W, ACCESS
    movwf       FSR2H, ACCESS
    clrf        stock_01A_acc, ACCESS
    movlw       0x03
    movwf       stock_01B_acc, ACCESS
    movlb       0x0
    movf        stock_0C5_b0, W, BANKED
    addwf       stock_01A_acc, F, ACCESS
    movlw       0x00
    addwfc      stock_01B_acc, F, ACCESS
    movf        stock_01F_acc, W, ACCESS
    addwf       stock_01A_acc, W, ACCESS
    movwf       FSR1L, ACCESS
    movlw       0x00
    addwfc      stock_01B_acc, W, ACCESS
    movwf       FSR1H, ACCESS
    movff       INDF2, INDF1
    incf        stock_01F_acc, F, ACCESS
    movlw       0x17
    cpfsgt      stock_01F_acc, ACCESS
    bra         flow_main_flash_service_2bb8_2bf6
    movlw       0x18
    addwf       stock_0C5_b0, F, BANKED
    movlw       0xBF
    cpfsgt      stock_0C5_b0, BANKED
    bra         flow_main_flash_service_2bb8_2ca6
    clrf        stock_0C5_b0, BANKED
    movlw       0x3F
    subwf       stock_082_b0, W, BANKED
    movlw       0x5F
    subwfb      stock_083_b0, W, BANKED
    bc          flow_main_flash_service_2bb8_2ca6
    rcall       flash_addr_setup_from_82_83
    movlw       0xBF
    addwf       stock_082_b0, W, BANKED
    movwf       stock_018_acc, ACCESS
    movlw       0x00
    addwfc      stock_083_b0, W, BANKED
    movwf       stock_019_acc, ACCESS
    movff       stock_018_b0_phys, stock_007_b0_phys
    movff       stock_019_b0_phys, stock_008_b0_phys
    clrf        stock_009_acc, ACCESS
    clrf        stock_00A_acc, ACCESS
    call        flash_erase, 0x0
    rcall       flash_addr_setup_from_82_83
    clrf        stock_008_acc, ACCESS
    movlw       0xC0
    movwf       stock_007_acc, ACCESS
    movlb       0x3
    movlw       0x03
    movwf       stock_00A_acc, ACCESS
    clrf        stock_009_acc, ACCESS
    rcall       flash_write
    movlw       0xC0
    movlb       0x0
    addwf       stock_082_b0, F, BANKED
    movlw       0x00
    addwfc      stock_083_b0, F, BANKED
flow_main_flash_service_2bb8_2ca6:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_2ca8
; Address : 0x2CA8
; Notes   : Inferred core helper routine. Calls: main_core_service_2d80, main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_2ca8:
    movff       stock_00D_b0_phys, stock_015_b0_phys
    movff       stock_00E_b0_phys, stock_016_b0_phys
    movff       stock_00F_b0_phys, stock_017_b0_phys
    movff       stock_010_b0_phys, stock_018_b0_phys
    movlw       0x18
    bra         flow_main_core_service_2ca8_2cbe
flow_main_core_service_2ca8_2cbc:
    rcall       main_core_service_2d80
flow_main_core_service_2ca8_2cbe:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2ca8_2cbc
    movf        stock_015_acc, W, ACCESS
    movwf       stock_01E_acc, ACCESS
    tstfsz      stock_01E_acc, ACCESS
    bra         flow_main_core_service_2ca8_2ccc
    bra         flow_main_core_service_2ca8_2cee
flow_main_core_service_2ca8_2ccc:
    movff       stock_011_b0_phys, stock_015_b0_phys
    movff       stock_012_b0_phys, stock_016_b0_phys
    movff       stock_013_b0_phys, stock_017_b0_phys
    movff       stock_014_b0_phys, stock_018_b0_phys
    movlw       0x18
    bra         flow_main_core_service_2ca8_2ce2
flow_main_core_service_2ca8_2ce0:
    rcall       main_core_service_2d80
flow_main_core_service_2ca8_2ce2:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_2ca8_2ce0
    movf        stock_015_acc, W, ACCESS
    movwf       stock_01F_acc, ACCESS
    tstfsz      stock_01F_acc, ACCESS
    bra         flow_main_core_service_2ca8_2cf8
flow_main_core_service_2ca8_2cee:
    clrf        stock_00D_acc, ACCESS
    clrf        stock_00E_acc, ACCESS
    clrf        stock_00F_acc, ACCESS
    clrf        stock_010_acc, ACCESS
    bra         flow_main_core_service_2ca8_2d7e
flow_main_core_service_2ca8_2cf8:
    movf        stock_01F_acc, W, ACCESS
    addlw       0x89
    subwf       stock_01E_acc, F, ACCESS
    movff       stock_010_b0_phys, stock_01F_b0_phys
    movf        stock_014_acc, W, ACCESS
    xorwf       stock_01F_acc, F, ACCESS
    movlw       0x80
    andwf       stock_01F_acc, F, ACCESS
    bsf         stock_00F_acc, 7, ACCESS
    clrf        stock_010_acc, ACCESS
    bsf         stock_013_acc, 7, ACCESS
    clrf        stock_014_acc, ACCESS
    movlw       0x20
    movwf       stock_01D_acc, ACCESS
flow_main_core_service_2ca8_2d16:
    bcf         STATUS, 0, ACCESS
    rlcf        stock_019_acc, F, ACCESS
    rlcf        stock_01A_acc, F, ACCESS
    rlcf        stock_01B_acc, F, ACCESS
    rlcf        stock_01C_acc, F, ACCESS
    movf        stock_011_acc, W, ACCESS
    subwf       stock_00D_acc, W, ACCESS
    movf        stock_012_acc, W, ACCESS
    subwfb      stock_00E_acc, W, ACCESS
    movf        stock_013_acc, W, ACCESS
    subwfb      stock_00F_acc, W, ACCESS
    movf        stock_014_acc, W, ACCESS
    subwfb      stock_010_acc, W, ACCESS
    bnc         flow_main_core_service_2ca8_2d44
    movf        stock_011_acc, W, ACCESS
    subwf       stock_00D_acc, F, ACCESS
    movf        stock_012_acc, W, ACCESS
    subwfb      stock_00E_acc, F, ACCESS
    movf        stock_013_acc, W, ACCESS
    subwfb      stock_00F_acc, F, ACCESS
    movf        stock_014_acc, W, ACCESS
    subwfb      stock_010_acc, F, ACCESS
    bsf         stock_019_acc, 0, ACCESS
flow_main_core_service_2ca8_2d44:
    bcf         STATUS, 0, ACCESS
    rlcf        stock_00D_acc, F, ACCESS
    rlcf        stock_00E_acc, F, ACCESS
    rlcf        stock_00F_acc, F, ACCESS
    rlcf        stock_010_acc, F, ACCESS
    decfsz      stock_01D_acc, F, ACCESS
    bra         flow_main_core_service_2ca8_2d16
    movff       stock_019_b0_phys, stock_003_b0_phys
    movff       stock_01A_b0_phys, stock_004_b0_phys
    movff       stock_01B_b0_phys, saved_w_b0_phys
    movff       stock_01C_b0_phys, stock_006_b0_phys
    movff       stock_01E_b0_phys, stock_007_b0_phys
    movff       stock_01F_b0_phys, stock_008_b0_phys
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
    rrcf        stock_018_acc, F, ACCESS
    rrcf        stock_017_acc, F, ACCESS
    rrcf        stock_016_acc, F, ACCESS
    rrcf        stock_015_acc, F, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Helper: wake_rebroadcast_downstream      (blocking B0/03/01 emit)
; ---------------------------------------------------------------------------
; Shared by adc_boot_gate's entry (round-2 parallel wake: downstream MAIN
; gates concurrently with ours) and exit (Bug #45 H2 backstop).  Blocking,
; ~1 ms for 3 bytes at 31,250 baud; callers run with the UART still
; configured (entry: pre-quiesce; exit: post TX-only re-arm).
; ---------------------------------------------------------------------------
wake_rebroadcast_downstream:
    movlw       0xB0
    call        uart_tx_byte_blocking, 0x0
    movlw       0x03
    call        uart_tx_byte_blocking, 0x0
    movlw       0x01
    goto        uart_tx_byte_blocking           ; tail-call return

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
    ; V3.4 round-2 (docs/analysis/CONNECTED_WAITING_WAKE_DELAY_2026-06-10):
    ; re-broadcast WAKE downstream BEFORE quiescing the UART, so the next
    ; MAIN in the ring starts its own (deaf, blocking) wake gate in PARALLEL
    ; with ours.  Previously the parser's chain-echo forward could be killed
    ; mid-frame by the quiesce below (Bug #45 H2), and even a clean forward
    ; only reached the downstream MAIN through OUR deaf window -- so a
    ; two-MAIN chain woke SEQUENTIALLY (~2x the single-gate latency, the
    ; dominant term in CONTROL's wake-to-responsive time).  The exit-time
    ; re-emit stays as the H2 robustness backstop; a duplicate wake is
    ; consumed idempotently by an already-awake MAIN.
    rcall       wake_rebroadcast_downstream
    call        uart_quiesce_for_wake, 0x0
    bcf         LATB, 2, ACCESS
    movlb       0x0
    clrf        stock_088_b0, BANKED
    clrf        stock_089_b0, BANKED
    bsf         ADCON0, 1, ACCESS
    ; Bug #45 §C: bound the rail-rise wait at ~50 iters * 10 ms = ~500 ms so a
    ; depressed AN0 (e.g. asymmetric shared-rail coupling on a two-MAIN chain)
    ; cannot pin this MAIN inside the polling loop indefinitely.  ram_0x008 is
    ; ACCESS BANK scratch -- safe for the gate scope: the only call inside the
    ; loop is timer3_blocking_delay_ms_W which uses ram_0x003/0x004 for its
    ; own countdown.
    movlw       0x32
    movwf       stock_008_acc, ACCESS
adc_boot_gate_loop:
    movlw       0x0A
    call        timer3_blocking_delay_ms_W, 0x0 ; W04-E08 factored (10 ms poll)
    btfsc       ADCON0, 1, ACCESS
    bra         flow_adc_boot_gate_2dbc
    movf        ADRESH, W, ACCESS
    movwf       stock_05D_acc, ACCESS
    clrf        stock_05C_acc, ACCESS
    movf        ADRESL, W, ACCESS
    addwf       stock_05C_acc, W, ACCESS
    movlb       0x0
    movwf       stock_088_b0, BANKED
    movlw       0x00
    addwfc      stock_05D_acc, W, ACCESS
    movwf       stock_089_b0, BANKED
    bsf         ADCON0, 1, ACCESS
flow_adc_boot_gate_2dbc:
    movlw       0x36
    movlb       0x0
    subwf       stock_088_b0, W, BANKED
    movlw       0x02
    subwfb      stock_089_b0, W, BANKED
    bc          adc_boot_gate_exit
    decfsz      stock_008_acc, F, ACCESS
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
    movwf       stock_004_acc, ACCESS
    movlw       0xDC
    movwf       stock_003_acc, ACCESS
    call        timer3_blocking_delay, 0x0
    bsf         TRISB, 1, ACCESS
    bsf         TRISB, 0, ACCESS
    movlw       0x01
    call        timer3_blocking_delay_ms_W, 0x0 ; W04-E08 factored (1 ms)
    movlw       0x80
    movwf       stock_003_acc, ACCESS
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
    ; (Round-2: the entry-time wake_rebroadcast_downstream is the primary
    ; parallel-wake path; this exit emit remains the H2 backstop.)
    rcall       wake_rebroadcast_downstream
    movlb       0x0
    bsf         event_flags_b0, 1, BANKED
    bsf         event_flags_b0, 3, BANKED
    bsf         event_flags_b0, 4, BANKED
    bsf         dsp_fault_flags_b0, 0, BANKED
    bsf         dsp_fault_flags_b0, 1, BANKED
    movlw       0x00
    call        cmd_dispatch_gated, 0x0
    call        send_status_burst, 0x0
    movlw       0x01
    movwf       stock_006_acc, ACCESS
    movlw       0x1B
    call        i2c_secondary_dev_write, 0x0
    bcf         INTCON, 5, ACCESS
    bcf         T0CON, 7, ACCESS
    movlw       0xA4
    movwf       TMR0H, ACCESS
    movlw       0x71
    movwf       TMR0L, ACCESS
    movlb       0x0
    clrf        an0_delay_b0, BANKED
    bcf         stock_094_b0, 2, BANKED
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
;
; Helper: preset_b_remap_start_addr (W05)
; Shared preset-B start-address remap for flash_read / flash_write /
; flash_erase.  When active_flags.bit2 is set and ram_0x003:006 points
; into logical preset-A flash 0x56xx..0x5Fxx, subtract 0x0A from
; ram_0x004 so the operation lands in the physical preset-B table at
; 0x4Cxx..0x55xx.  The _if_b entry is for callers that have already tested
; active_flags.bit2 and still need to continue into a second endpoint check.
; ---------------------------------------------------------------------------
preset_b_remap_start_addr:
    btfss       active_flags_acc, 2, ACCESS
    return      0
preset_b_remap_start_addr_if_b:
    movf        stock_006_acc, W, ACCESS
    iorwf       stock_005_acc, W, ACCESS
    bnz         preset_b_remap_start_addr_return
    movlw       0x56
    subwf       stock_004_acc, W, ACCESS
    bnc         preset_b_remap_start_addr_return
    movlw       0x60
    subwf       stock_004_acc, W, ACCESS
    bc          preset_b_remap_start_addr_return
    movlw       0x0A
    subwf       stock_004_acc, F, ACCESS
preset_b_remap_start_addr_return:
    return      0

flash_write:
    rcall       preset_b_remap_start_addr
flash_write_stock:
    clrf        stock_010_acc, ACCESS
    movff       stock_003_b0_phys, stock_014_b0_phys
    movff       stock_004_b0_phys, stock_015_b0_phys
    movff       saved_w_b0_phys, stock_016_b0_phys
    movff       stock_006_b0_phys, stock_017_b0_phys
    movlw       0x05
    movwf       stock_00B_acc, ACCESS
flow_flash_write_2e84:
    bcf         STATUS, 0, ACCESS
    rrcf        stock_006_acc, F, ACCESS
    rrcf        stock_005_acc, F, ACCESS
    rrcf        stock_004_acc, F, ACCESS
    rrcf        stock_003_acc, F, ACCESS
    decfsz      stock_00B_acc, F, ACCESS
    bra         flow_flash_write_2e84
    movlw       0x05
flow_flash_write_2e94:
    bcf         STATUS, 0, ACCESS
    rlcf        stock_003_acc, F, ACCESS
    rlcf        stock_004_acc, F, ACCESS
    rlcf        stock_005_acc, F, ACCESS
    rlcf        stock_006_acc, F, ACCESS
    decfsz      WREG, F, ACCESS
    bra         flow_flash_write_2e94
    movlw       0x20
    addwf       stock_003_acc, F, ACCESS
    movlw       0x00
    addwfc      stock_004_acc, F, ACCESS
    addwfc      stock_005_acc, F, ACCESS
    addwfc      stock_006_acc, F, ACCESS
    movf        stock_014_acc, W, ACCESS
    subwf       stock_003_acc, W, ACCESS
    movwf       stock_00F_acc, ACCESS
    bra         flow_flash_write_2f44
flow_flash_write_2eb6:
    movff       stock_016_b0_phys, stock_013_b0_phys
    movff       stock_015_b0_phys, stock_012_b0_phys
    movff       stock_014_b0_phys, stock_011_b0_phys
    bra         flow_flash_write_2ef6
flow_flash_write_2ec4:
    movff       stock_009_b0_phys, FSR2L
    movff       stock_00A_b0_phys, FSR2H
    movf        INDF2, W, ACCESS
    movff       stock_011_b0_phys, TBLPTRL
    movff       stock_012_b0_phys, TBLPTRH
    movff       stock_013_b0_phys, TBLPTRU
    movwf       TABLAT, ACCESS
    tblwt*
    infsnz      stock_009_acc, F, ACCESS
    incf        stock_00A_acc, F, ACCESS
    incf        stock_011_acc, F, ACCESS
    movlw       0x00
    addwfc      stock_012_acc, F, ACCESS
    addwfc      stock_013_acc, F, ACCESS
    decf        stock_007_acc, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        stock_008_acc, F, ACCESS
    movf        stock_008_acc, W, ACCESS
    iorwf       stock_007_acc, W, ACCESS
    bz          flow_flash_write_2efc
flow_flash_write_2ef6:
    decf        stock_00F_acc, F, ACCESS
    incf        stock_00F_acc, W, ACCESS
    bnz         flow_flash_write_2ec4
flow_flash_write_2efc:
    movff       stock_013_b0_phys, stock_00E_b0_phys
    movff       stock_012_b0_phys, stock_00D_b0_phys
    movff       stock_011_b0_phys, timeout_hi_b0_phys
    movff       stock_016_b0_phys, stock_013_b0_phys
    movff       stock_015_b0_phys, stock_012_b0_phys
    movff       stock_014_b0_phys, stock_011_b0_phys
    bsf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    btfss       INTCON, 7, ACCESS
    bra         flow_flash_write_2f24
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       stock_010_acc, ACCESS
flow_flash_write_2f24:
    call        main_flash_service_4406, 0x0
    bcf         EECON1, 2, ACCESS
    movf        stock_010_acc, W, ACCESS
    bz          flow_flash_write_2f32
    bsf         INTCON, 7, ACCESS
    clrf        stock_010_acc, ACCESS
flow_flash_write_2f32:
    movlw       0x20
    movwf       stock_00F_acc, ACCESS
    movf        stock_00C_acc, W, ACCESS
    movwf       stock_014_acc, ACCESS
    movf        stock_00D_acc, W, ACCESS
    movwf       stock_015_acc, ACCESS
    movf        stock_00E_acc, W, ACCESS
    movwf       stock_016_acc, ACCESS
    clrf        stock_017_acc, ACCESS
flow_flash_write_2f44:
    movf        stock_008_acc, W, ACCESS
    iorwf       stock_007_acc, W, ACCESS
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
    tstfsz      stock_0CD_b0, BANKED
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
    subwf       stock_0CD_b0, W, BANKED
    bnc         flow_main_usb_service_2f4e_3018
    clrf        stock_0C4_b0, BANKED
flow_main_usb_service_2f4e_2f78:
    btfss       UIR, 3, ACCESS
    bra         flow_main_usb_service_2f4e_3018
    movf        USTAT, W, ACCESS
    movff       USTAT, stock_006_b0_phys
    movlw       0x7C
    andwf       stock_006_acc, F, ACCESS
    bnz         flow_main_usb_service_2f4e_2ffe
    btfsc       USTAT, 1, ACCESS
    bra         flow_main_usb_service_2f4e_2f96
    movlw       0x04
    movlb       0x0
    movwf       stock_07B_b0, BANKED
    movlw       0x00
    bra         flow_main_usb_service_2f4e_2f9c
flow_main_usb_service_2f4e_2f96:
    movlw       0x04
    movlb       0x0
    movwf       stock_07B_b0, BANKED
flow_main_usb_service_2f4e_2f9c:
    movlb       0x0
    movwf       stock_07A_b0, BANKED
    bcf         UIR, 3, ACCESS
    movff       stock_07A_b0_phys, FSR2L
    movff       stock_07B_b0_phys, FSR2H
    rrcf        INDF2, W, ACCESS
    rrcf        WREG, F, ACCESS
    andlw       0x0F
    xorlw       0x0D
    bnz         flow_main_usb_service_2f4e_300e
    clrf        stock_090_b0, BANKED
flow_main_usb_service_2f4e_2fb6:
    lfsr        FSR2, isr_save_fsr2h_b0_phys
    movf        stock_07A_b0, W, BANKED
    addwf       FSR2L, F, ACCESS
    movf        stock_07B_b0, W, BANKED
    addwfc      FSR2H, F, ACCESS
    movff       POSTINC2, stock_006_b0_phys
    movff       POSTDEC2, stock_007_b0_phys
    movff       stock_006_b0_phys, FSR2L
    movff       stock_007_b0_phys, FSR2H
    movf        stock_090_b0, W, BANKED
    addlw       0xCF
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movff       INDF2, INDF1
    lfsr        FSR2, isr_save_fsr2h_b0_phys
    movf        stock_07A_b0, W, BANKED
    addwf       FSR2L, F, ACCESS
    movf        stock_07B_b0, W, BANKED
    addwfc      FSR2H, F, ACCESS
    incf        POSTINC2, F, ACCESS
    movlw       0x00
    addwfc      POSTDEC2, F, ACCESS
    incf        stock_090_b0, F, BANKED
    movlw       0x07
    cpfsgt      stock_090_b0, BANKED
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
    incf        stock_0C4_b0, F, BANKED
    movlw       0x03
    cpfsgt      stock_0C4_b0, BANKED
    bra         flow_main_usb_service_2f4e_2f78
flow_main_usb_service_2f4e_3018:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_301a
; Address : 0x301A
; Notes   : Inferred core helper routine. Calls: main_core_service_30cc.
; ---------------------------------------------------------------------------
main_core_service_301a:
    movff       stock_025_b0_phys, stock_029_b0_phys
    movff       stock_026_b0_phys, stock_02A_b0_phys
    movff       stock_027_b0_phys, stock_02B_b0_phys
    movff       stock_028_b0_phys, stock_02C_b0_phys
    movlw       0x18
    bra         flow_main_core_service_301a_3030
flow_main_core_service_301a_302e:
    rcall       main_core_service_30cc
flow_main_core_service_301a_3030:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_301a_302e
    movf        stock_029_acc, W, ACCESS
    movwf       stock_02E_acc, ACCESS
    tstfsz      stock_02E_acc, ACCESS
    bra         flow_main_core_service_301a_3046
flow_main_core_service_301a_303c:
    clrf        stock_025_acc, ACCESS
    clrf        stock_026_acc, ACCESS
    clrf        stock_027_acc, ACCESS
    clrf        stock_028_acc, ACCESS
    bra         flow_main_core_service_301a_30ca
flow_main_core_service_301a_3046:
    movff       stock_025_b0_phys, stock_029_b0_phys
    movff       stock_026_b0_phys, stock_02A_b0_phys
    movff       stock_027_b0_phys, stock_02B_b0_phys
    movff       stock_028_b0_phys, stock_02C_b0_phys
    movlw       0x20
    bra         flow_main_core_service_301a_305c
flow_main_core_service_301a_305a:
    rcall       main_core_service_30cc
flow_main_core_service_301a_305c:
    decfsz      WREG, F, ACCESS
    bra         flow_main_core_service_301a_305a
    movf        stock_029_acc, W, ACCESS
    movwf       stock_02D_acc, ACCESS
    bsf         stock_027_acc, 7, ACCESS
    clrf        stock_028_acc, ACCESS
    movlw       0x96
    subwf       stock_02E_acc, F, ACCESS
    btfss       stock_02E_acc, 7, ACCESS
    bra         flow_main_core_service_301a_308e
    movf        stock_02E_acc, W, ACCESS
    xorlw       0x80
    movwf       stock_029_acc, ACCESS
    movlw       0xE9
    xorlw       0x80
    subwf       stock_029_acc, W, ACCESS
    bnc         flow_main_core_service_301a_303c
flow_main_core_service_301a_307e:
    bcf         STATUS, 0, ACCESS
    rrcf        stock_028_acc, F, ACCESS
    rrcf        stock_027_acc, F, ACCESS
    rrcf        stock_026_acc, F, ACCESS
    rrcf        stock_025_acc, F, ACCESS
    incfsz      stock_02E_acc, F, ACCESS
    bra         flow_main_core_service_301a_307e
    bra         flow_main_core_service_301a_30a6
flow_main_core_service_301a_308e:
    movlw       0x1F
    cpfsgt      stock_02E_acc, ACCESS
    bra         flow_main_core_service_301a_30a2
    bra         flow_main_core_service_301a_303c
flow_main_core_service_301a_3096:
    bcf         STATUS, 0, ACCESS
    rlcf        stock_025_acc, F, ACCESS
    rlcf        stock_026_acc, F, ACCESS
    rlcf        stock_027_acc, F, ACCESS
    rlcf        stock_028_acc, F, ACCESS
    decf        stock_02E_acc, F, ACCESS
flow_main_core_service_301a_30a2:
    tstfsz      stock_02E_acc, ACCESS
    bra         flow_main_core_service_301a_3096
flow_main_core_service_301a_30a6:
    movf        stock_02D_acc, W, ACCESS
    bz          flow_main_core_service_301a_30ba
    comf        stock_028_acc, F, ACCESS
    comf        stock_027_acc, F, ACCESS
    comf        stock_026_acc, F, ACCESS
    negf        stock_025_acc, ACCESS
    movlw       0x00
    addwfc      stock_026_acc, F, ACCESS
    addwfc      stock_027_acc, F, ACCESS
    addwfc      stock_028_acc, F, ACCESS
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
    rrcf        stock_02C_acc, F, ACCESS
    rrcf        stock_02B_acc, F, ACCESS
    rrcf        stock_02A_acc, F, ACCESS
    rrcf        stock_029_acc, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_30d8
; Address : 0x30D8
; Notes   : Inferred core helper routine. Calls: main_core_service_3188.
; ---------------------------------------------------------------------------
main_core_service_30d8:
    movf        stock_007_acc, W, ACCESS
    bz          flow_main_core_service_30d8_30e6
    movf        stock_006_acc, W, ACCESS
    iorwf       stock_003_acc, W, ACCESS
    iorwf       stock_004_acc, W, ACCESS
    iorwf       stock_005_acc, W, ACCESS
    bnz         flow_main_core_service_30d8_30f4
flow_main_core_service_30d8_30e6:
    clrf        stock_003_acc, ACCESS
    clrf        stock_004_acc, ACCESS
    clrf        stock_005_acc, ACCESS
    clrf        stock_006_acc, ACCESS
    bra         flow_main_core_service_30d8_3186
flow_main_core_service_30d8_30f0:
    incf        stock_007_acc, F, ACCESS
    rcall       main_core_service_3188
flow_main_core_service_30d8_30f4:
    clrf        stock_009_acc, ACCESS
    clrf        stock_00A_acc, ACCESS
    clrf        stock_00B_acc, ACCESS
    movlw       0xFE
    andwf       stock_006_acc, W, ACCESS
    movwf       stock_00C_acc, ACCESS
    movf        stock_00C_acc, W, ACCESS
    iorwf       stock_009_acc, W, ACCESS
    iorwf       stock_00A_acc, W, ACCESS
    iorwf       stock_00B_acc, W, ACCESS
    bz          flow_main_core_service_30d8_311a
    bra         flow_main_core_service_30d8_30f0
flow_main_core_service_30d8_310c:
    incf        stock_007_acc, F, ACCESS
    incf        stock_003_acc, F, ACCESS
    movlw       0x00
    addwfc      stock_004_acc, F, ACCESS
    addwfc      stock_005_acc, F, ACCESS
    addwfc      stock_006_acc, F, ACCESS
    rcall       main_core_service_3188
flow_main_core_service_30d8_311a:
    clrf        stock_009_acc, ACCESS
    clrf        stock_00A_acc, ACCESS
    clrf        stock_00B_acc, ACCESS
    movf        stock_006_acc, W, ACCESS
    movwf       stock_00C_acc, ACCESS
    movf        stock_00C_acc, W, ACCESS
    iorwf       stock_009_acc, W, ACCESS
    iorwf       stock_00A_acc, W, ACCESS
    iorwf       stock_00B_acc, W, ACCESS
    bz          flow_main_core_service_30d8_313c
    bra         flow_main_core_service_30d8_310c
flow_main_core_service_30d8_3130:
    decf        stock_007_acc, F, ACCESS
    bcf         STATUS, 0, ACCESS
    rlcf        stock_003_acc, F, ACCESS
    rlcf        stock_004_acc, F, ACCESS
    rlcf        stock_005_acc, F, ACCESS
    rlcf        stock_006_acc, F, ACCESS
flow_main_core_service_30d8_313c:
    btfss       stock_005_acc, 7, ACCESS
    bra         flow_main_core_service_30d8_3130
    btfsc       stock_007_acc, 0, ACCESS
    bra         flow_main_core_service_30d8_3148
    movlw       0x7F
    andwf       stock_005_acc, F, ACCESS
flow_main_core_service_30d8_3148:
    bcf         STATUS, 0, ACCESS
    rrcf        stock_007_acc, F, ACCESS
    movff       stock_007_b0_phys, stock_009_b0_phys
    clrf        stock_00A_acc, ACCESS
    clrf        stock_00B_acc, ACCESS
    clrf        stock_00C_acc, ACCESS
    movff       stock_009_b0_phys, timeout_hi_b0_phys
    clrf        stock_00B_acc, ACCESS
    clrf        stock_00A_acc, ACCESS
    clrf        stock_009_acc, ACCESS
    movf        stock_009_acc, W, ACCESS
    iorwf       stock_003_acc, F, ACCESS
    movf        stock_00A_acc, W, ACCESS
    iorwf       stock_004_acc, F, ACCESS
    movf        stock_00B_acc, W, ACCESS
    iorwf       stock_005_acc, F, ACCESS
    movf        stock_00C_acc, W, ACCESS
    iorwf       stock_006_acc, F, ACCESS
    movf        stock_008_acc, W, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         stock_006_acc, 7, ACCESS
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
    movff       stock_003_b0_phys, stock_00D_b0_phys
    movff       stock_004_b0_phys, stock_00E_b0_phys
    movff       saved_w_b0_phys, stock_00F_b0_phys
    movff       stock_006_b0_phys, stock_010_b0_phys
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3188
; Address : 0x3188
; Notes   : Inferred core helper routine. Calls: main_core_service_496c, main_core_service_4080.
; ---------------------------------------------------------------------------
main_core_service_3188:
    bcf         STATUS, 0, ACCESS
    rrcf        stock_006_acc, F, ACCESS
    rrcf        stock_005_acc, F, ACCESS
    rrcf        stock_004_acc, F, ACCESS
    rrcf        stock_003_acc, F, ACCESS
    return      0
flow_main_core_service_3188_3194:
    movf        stock_0CF_b0, W, BANKED
    andlw       0x1F
    movwf       stock_003_acc, ACCESS
    decf        stock_003_acc, W, ACCESS
    bnz         flow_main_core_service_3188_324a
    movf        stock_0D3_b0, W, BANKED
    bnz         flow_main_core_service_3188_324a
    movf        stock_0D0_b0, W, BANKED
    xorlw       0x06
    bz          flow_main_core_service_3188_31d8
    bra         flow_main_core_service_3188_31e6
flow_main_core_service_3188_31aa:
    movlw       0x02
    movwf       stock_0C8_b0, BANKED
    movlw       HIGH(usb_hid_descriptor)
    movwf       stock_076_b0, BANKED
    movlw       LOW(usb_hid_descriptor)
    movwf       stock_075_b0, BANKED
    clrf        stock_0E8_b0, BANKED
    movlw       0x09
    bra         flow_main_core_service_3188_31d4
flow_main_core_service_3188_31bc:
    movlw       0x02
    movwf       stock_0C8_b0, BANKED
    decf        stock_0EB_b0, W, BANKED
    bnz         flow_main_core_service_3188_31cc
    movlw       HIGH(usb_hid_report_descriptor)
    movwf       stock_076_b0, BANKED
    movlw       LOW(usb_hid_report_descriptor)
    movwf       stock_075_b0, BANKED
flow_main_core_service_3188_31cc:
    decf        stock_0EB_b0, W, BANKED
    bnz         flow_main_core_service_3188_31e4
    clrf        stock_0E8_b0, BANKED
    movlw       0x1D
flow_main_core_service_3188_31d4:
    movwf       stock_0E7_b0, BANKED
    bra         flow_main_core_service_3188_31e4
flow_main_core_service_3188_31d8:
    movf        stock_0D2_b0, W, BANKED
    xorlw       0x21
    bz          flow_main_core_service_3188_31aa
    xorlw       0x03
    bz          flow_main_core_service_3188_31bc
    xorlw       0x01
flow_main_core_service_3188_31e4:
    bsf         stock_0CE_b0, 1, BANKED
flow_main_core_service_3188_31e6:
    swapf       stock_0CF_b0, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    movwf       stock_003_acc, ACCESS
    decf        stock_003_acc, W, ACCESS
    bnz         flow_main_core_service_3188_324a
    bra         flow_main_core_service_3188_3230
flow_main_core_service_3188_31f4:
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_31fa:
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_3200:
    movlw       0x02
    movwf       stock_0C8_b0, BANKED
    clrf        stock_076_b0, BANKED
    movlw       0xEA
flow_main_core_service_3188_3208:
    movwf       stock_075_b0, BANKED
    bcf         stock_0CE_b0, 1, BANKED
    movlw       0x01
    movwf       stock_0E7_b0, BANKED
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_3212:
    movlw       0x02
    movwf       stock_0C8_b0, BANKED
    movff       stock_0D2_b0_phys, stock_0EA_b0_phys
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_321c:
    movlw       0x02
    movwf       stock_0C8_b0, BANKED
    clrf        stock_076_b0, BANKED
    movlw       0xE9
    bra         flow_main_core_service_3188_3208
flow_main_core_service_3188_3226:
    movlw       0x02
    movwf       stock_0C8_b0, BANKED
    movff       stock_0D1_b0_phys, stock_0E9_b0_phys
    bra         flow_main_core_service_3188_324a
flow_main_core_service_3188_3230:
    movf        stock_0D0_b0, W, BANKED
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
    tstfsz      stock_0C8_b0, BANKED
    bra         flow_main_core_service_3188_3278
    movlw       0x04
    movlb       0x4
    movwf       stock_408_b4, BANKED
    bsf         stock_408_b4, 7, BANKED
    movlb       0x1
    movwf       stock_116_b1, BANKED
    movlb       0x0
    decf        stock_096_b0, W, BANKED
    bnz         flow_main_core_service_3188_326c
    movlw       0x01
    call        main_core_service_4080, 0x0
    clrf        stock_096_b0, BANKED
    bra         flow_main_core_service_3188_32f6
flow_main_core_service_3188_326c:
    movlw       0x00
    call        main_core_service_4080, 0x0
    movlw       0x01
    movwf       stock_096_b0, BANKED
    bra         flow_main_core_service_3188_32f6
flow_main_core_service_3188_3278:
    btfss       stock_0CF_b0, 7, BANKED
    bra         flow_main_core_service_3188_32b4
    movlw       0x01
    movwf       stock_0C9_b0, BANKED
    movf        stock_0E7_b0, W, BANKED
    subwf       stock_0D5_b0, W, BANKED
    movf        stock_0E8_b0, W, BANKED
    subwfb      stock_0D6_b0, W, BANKED
    bc          flow_main_core_service_3188_3292
    movff       stock_0D5_b0_phys, stock_0E7_b0_phys
    movff       stock_0D6_b0_phys, stock_0E8_b0_phys
flow_main_core_service_3188_3292:
    rcall       main_flash_service_35f0
    movlw       0x48
    movlb       0x1
    movwf       stock_116_b1, BANKED
    movlw       0x01
    call        main_core_service_4080, 0x0
    movlw       0x00
    call        main_core_service_4080, 0x0
    movlb       0x4
    movlw       0x04
    movwf       stock_40B_b4, BANKED
    movlw       0x24
    movwf       stock_40A_b4, BANKED
    bra         flow_main_core_service_3188_32f0
flow_main_core_service_3188_32b4:
    movlw       0x02
    movwf       stock_0C9_b0, BANKED
    movlw       0x04
    movlb       0x1
    movwf       stock_116_b1, BANKED
    movlb       0x0
    movf        stock_0D6_b0, W, BANKED
    iorwf       stock_0D5_b0, W, BANKED
    bnz         flow_main_core_service_3188_32cc
    movlw       0x48
    movlb       0x1
    movwf       stock_116_b1, BANKED
flow_main_core_service_3188_32cc:
    movlb       0x0
    decf        stock_096_b0, W, BANKED
    bnz         flow_main_core_service_3188_32dc
    movlw       0x01
    call        main_core_service_4080, 0x0
    clrf        stock_096_b0, BANKED
    bra         flow_main_core_service_3188_32e6
flow_main_core_service_3188_32dc:
    movlw       0x00
    call        main_core_service_4080, 0x0
    movlw       0x01
    movwf       stock_096_b0, BANKED
flow_main_core_service_3188_32e6:
    movf        stock_0D6_b0, W, BANKED
    iorwf       stock_0D5_b0, W, BANKED
    bnz         flow_main_core_service_3188_32f6
    movlb       0x4
    clrf        stock_409_b4, BANKED
flow_main_core_service_3188_32f0:
    movlw       0x48
    movwf       stock_408_b4, BANKED
    bsf         stock_408_b4, 7, BANKED
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
    movwf       stock_006_acc, ACCESS
    movlw       0x01
    call        i2c_secondary_dev_write, 0x0
    movlw       0x30
    movwf       stock_006_acc, ACCESS
    movlw       0x03
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       stock_006_acc, ACCESS
    movlw       0x04
    call        i2c_secondary_dev_write, 0x0
    movlw       0x08
    movwf       stock_006_acc, ACCESS
    movlw       0x05
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       stock_006_acc, ACCESS
    movlw       0x06
    call        i2c_secondary_dev_write, 0x0
    movlw       0x34
    movwf       stock_006_acc, ACCESS
    movlw       0x07
    call        i2c_secondary_dev_write, 0x0
    movlw       0x30
    movwf       stock_006_acc, ACCESS
    movlw       0x08
    call        i2c_secondary_dev_write, 0x0
    movlw       0x08
    movwf       stock_006_acc, ACCESS
    movlw       0x0D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x08
    movwf       stock_006_acc, ACCESS
    movlw       0x0E
    call        i2c_secondary_dev_write, 0x0
    movlw       0x22
    movwf       stock_006_acc, ACCESS
    movlw       0x0F
    call        i2c_secondary_dev_write, 0x0
    clrf        stock_006_acc, ACCESS
    movlw       0x10
    call        i2c_secondary_dev_write, 0x0
    clrf        stock_006_acc, ACCESS
    movlw       0x11
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       stock_006_acc, ACCESS
    movlw       0x1C
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    movwf       stock_006_acc, ACCESS
    movlw       0x1D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x02
    movwf       stock_006_acc, ACCESS
    movlw       0x2D
    call        i2c_secondary_dev_write, 0x0
    movlw       0x20
    movwf       stock_006_acc, ACCESS
    movlw       0x2E
    goto        i2c_secondary_dev_write


; ---------------------------------------------------------------------------
; Function: main_core_service_3398
; Address : 0x3398
; Notes   : Inferred core helper routine. Calls: main_flash_service_3ce8, main_core_service_301a, main_core_service_3e0a.
; ---------------------------------------------------------------------------
main_core_service_3398:
    movff       stock_02F_b0_phys, stock_003_b0_phys
    movff       stock_030_b0_phys, stock_004_b0_phys
    movff       stock_031_b0_phys, saved_w_b0_phys
    movff       stock_032_b0_phys, stock_006_b0_phys
    movlw       0x37
    movwf       stock_007_acc, ACCESS
    call        main_flash_service_3ce8, 0x0
    movf        stock_038_acc, W, ACCESS
    xorlw       0x80
    movwf       PRODL, ACCESS
    movlw       0x80
    subwf       PRODL, W, ACCESS
    movlw       0x00
    btfsc       STATUS, 2, ACCESS
    subwf       stock_037_acc, W, ACCESS
    bc          flow_main_core_service_3398_33cc
    clrf        stock_02F_acc, ACCESS
    clrf        stock_030_acc, ACCESS
    clrf        stock_031_acc, ACCESS
    clrf        stock_032_acc, ACCESS
    bra         flow_main_core_service_3398_3430
flow_main_core_service_3398_33cc:
    movlw       0x1D
    subwf       stock_037_acc, W, ACCESS
    movlw       0x00
    subwfb      stock_038_acc, W, ACCESS
    bnc         flow_main_core_service_3398_33e8
    bra         flow_main_core_service_3398_3430
flow_main_core_service_3398_33e8:
    movff       stock_02F_b0_phys, stock_025_b0_phys
    movff       stock_030_b0_phys, stock_026_b0_phys
    movff       stock_031_b0_phys, stock_027_b0_phys
    movff       stock_032_b0_phys, stock_028_b0_phys
    rcall       main_core_service_301a
    movff       stock_025_b0_phys, stock_00D_b0_phys
    movff       stock_026_b0_phys, stock_00E_b0_phys
    movff       stock_027_b0_phys, stock_00F_b0_phys
    movff       stock_028_b0_phys, stock_010_b0_phys
    call        main_core_service_3e0a, 0x0
    movff       stock_00D_b0_phys, stock_033_b0_phys
    movff       stock_00E_b0_phys, stock_034_b0_phys
    movff       stock_00F_b0_phys, stock_035_b0_phys
    movff       stock_010_b0_phys, stock_036_b0_phys
    movff       stock_033_b0_phys, stock_02F_b0_phys
    movff       stock_034_b0_phys, stock_030_b0_phys
    movff       stock_035_b0_phys, stock_031_b0_phys
    movff       stock_036_b0_phys, stock_032_b0_phys
flow_main_core_service_3398_3430:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3432
; Address : 0x3432
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3432:
    decf        stock_0D1_b0, W, BANKED
    bnz         flow_main_core_service_3432_344c
    movf        stock_0CF_b0, W, BANKED
    andlw       0x1F
    bnz         flow_main_core_service_3432_344c
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    movf        stock_0D0_b0, W, BANKED
    xorlw       0x03
    bnz         flow_main_core_service_3432_344a
    bsf         stock_0CE_b0, 0, BANKED
    bra         flow_main_core_service_3432_344c
flow_main_core_service_3432_344a:
    bcf         stock_0CE_b0, 0, BANKED
flow_main_core_service_3432_344c:
    tstfsz      stock_0D1_b0, BANKED
    bra         flow_main_core_service_3432_34c6
    movf        stock_0CF_b0, W, BANKED
    andlw       0x1F
    xorlw       0x02
    bnz         flow_main_core_service_3432_34c6
    movf        stock_0D3_b0, W, BANKED
    andlw       0x0F
    bz          flow_main_core_service_3432_34c6
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    rcall       core_filter_addr_from_0x0D3        ; W05-E06 factored
    movf        stock_0D0_b0, W, BANKED
    xorlw       0x03
    bnz         flow_main_core_service_3432_349c
    movff       stock_072_b0_phys, FSR2L
    movff       stock_073_b0_phys, FSR2H
    movlw       0x04
    bra         flow_main_core_service_3432_34b8
flow_main_core_service_3432_349c:
    btfss       stock_0D3_b0, 7, BANKED
    bra         flow_main_core_service_3432_34ae
    movff       stock_072_b0_phys, FSR2L
    movff       stock_073_b0_phys, FSR2H
    movlw       0x40
    movwf       INDF2, ACCESS
    bra         flow_main_core_service_3432_34c6
flow_main_core_service_3432_34ae:
    movff       stock_072_b0_phys, FSR2L
    movff       stock_073_b0_phys, FSR2H
    movlw       0x08
flow_main_core_service_3432_34b8:
    movwf       INDF2, ACCESS
    movff       stock_072_b0_phys, FSR2L
    movff       stock_073_b0_phys, FSR2H
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
    movff       WREG, stock_011_b0_phys
    movff       stock_00A_b0_phys, stock_00E_b0_phys
    movff       timeout_lo_b0_phys, stock_00F_b0_phys
flow_main_core_service_34c8_34d4:
    movff       stock_00E_b0_phys, stock_003_b0_phys
    movff       stock_00F_b0_phys, stock_004_b0_phys
    movff       timeout_hi_b0_phys, saved_w_b0_phys
    movff       stock_00D_b0_phys, stock_006_b0_phys
    call        main_adc_service_4124, 0x0
    movff       stock_003_b0_phys, stock_00E_b0_phys
    movff       stock_004_b0_phys, stock_00F_b0_phys
    incf        stock_011_acc, F, ACCESS
    movf        stock_00F_acc, W, ACCESS
    iorwf       stock_00E_acc, W, ACCESS
    bnz         flow_main_core_service_34c8_34d4
    movf        stock_011_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    clrf        INDF2, ACCESS
    decf        stock_011_acc, F, ACCESS
flow_main_core_service_34c8_3504:
    movff       stock_00A_b0_phys, stock_003_b0_phys
    movff       timeout_lo_b0_phys, stock_004_b0_phys
    movff       timeout_hi_b0_phys, saved_w_b0_phys
    movff       stock_00D_b0_phys, stock_006_b0_phys
    call        main_core_service_427a, 0x0
    movf        stock_003_acc, W, ACCESS
    movwf       stock_010_acc, ACCESS
    movff       stock_00A_b0_phys, stock_003_b0_phys
    movff       timeout_lo_b0_phys, stock_004_b0_phys
    movff       timeout_hi_b0_phys, saved_w_b0_phys
    movff       stock_00D_b0_phys, stock_006_b0_phys
    call        main_adc_service_4124, 0x0
    movff       stock_003_b0_phys, stock_00A_b0_phys
    movff       stock_004_b0_phys, timeout_lo_b0_phys
    movlw       0x09
    cpfsgt      stock_010_acc, ACCESS
    bra         flow_main_core_service_34c8_3542
    movlw       0x07
    addwf       stock_010_acc, F, ACCESS
flow_main_core_service_34c8_3542:
    movlw       0x30
    addwf       stock_010_acc, F, ACCESS
    movf        stock_011_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       stock_010_b0_phys, INDF2
    decf        stock_011_acc, F, ACCESS
    movf        stock_00B_acc, W, ACCESS
    iorwf       stock_00A_acc, W, ACCESS
    bnz         flow_main_core_service_34c8_3504
    incf        stock_011_acc, F, ACCESS
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
    movwf       stock_0FE_b0, BANKED
    clrf        stock_004_acc, ACCESS
    movlw       0xFF
    setf        stock_003_acc, ACCESS
    call        eeprom_read_byte, 0x0
    xorlw       0x77
    bz          flow_main_i2c_service_355c_35bc
    clrf        stock_004_acc, ACCESS
    movlw       0xFF
    setf        stock_003_acc, ACCESS
    call        eeprom_read_byte, 0x0
    xorlw       0x88
    bz          flow_main_i2c_service_355c_35bc
    movlb       0x0
    clrf        stock_0FE_b0, BANKED
flow_main_i2c_service_355c_35bc:
    movlb       0x0
    movf        stock_0FE_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    call        flash_write_with_gie_off, 0x0
    clrf        stock_008_acc, ACCESS
    setf        stock_007_acc, ACCESS
    movlw       0x02
    movwf       stock_009_acc, ACCESS
    call        main_flash_service_46de, 0x0
    bsf         PORTB, 6, ACCESS
    rcall       adaptive_baud_select
    movlw       0x03
    movwf       stock_004_acc, ACCESS
    movlw       0xE8
    movwf       stock_003_acc, ACCESS
    call        timer3_blocking_delay, 0x0
    call        main_core_service_1e88, 0x0
    bsf         PIE1, 5, ACCESS
    bsf         active_flags_acc, 3, ACCESS
    movlb       0x0
    bsf         event_flags_b0, 7, BANKED      ; V3.1: boot complete — enable bounded PEN waits
    goto        adc_boot_gate


; ---------------------------------------------------------------------------
; Function: main_flash_service_35f0
; Address : 0x35F0
; Notes   : Inferred flash helper; touches flash. Calls: main_flash_service_365c, main_flash_service_3810, main_core_service_3672.
; ---------------------------------------------------------------------------
main_flash_service_35f0:
    movlw       0x08
    movwf       stock_08F_b0, BANKED
    subwf       stock_0E7_b0, W, BANKED
    movlw       0x00
    subwfb      stock_0E8_b0, W, BANKED
    bc          flow_main_flash_service_35f0_3610
    movff       stock_0E7_b0_phys, stock_08F_b0_phys
    tstfsz      stock_0CC_b0, BANKED
    bra         flow_main_flash_service_35f0_3608
    movlw       0x01
    bra         flow_main_flash_service_35f0_360e
flow_main_flash_service_35f0_3608:
    decf        stock_0CC_b0, W, BANKED
    bnz         flow_main_flash_service_35f0_3610
    movlw       0x02
flow_main_flash_service_35f0_360e:
    movwf       stock_0CC_b0, BANKED
flow_main_flash_service_35f0_3610:
    movff       stock_08F_b0_phys, stock_409_b4_phys
    movf        stock_08F_b0, W, BANKED
    subwf       stock_0E7_b0, F, BANKED
    movlw       0x00
    subwfb      stock_0E8_b0, F, BANKED
    movlw       0x04
    movlb       0x0
    movwf       stock_073_b0, BANKED
    movlw       0x24
    movwf       stock_072_b0, BANKED
    btfsc       stock_0CE_b0, 1, BANKED
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
    tstfsz      stock_08F_b0, BANKED
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
    tstfsz      stock_08F_b0, BANKED
    bra         flow_main_flash_service_35f0_3644
flow_main_flash_service_35f0_365a:
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_365c
; Address : 0x365C
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
main_flash_service_365c:
    movff       stock_075_b0_phys, TBLPTRL
    movff       stock_076_b0_phys, TBLPTRH
    clrf        TBLPTRU, ACCESS
    movff       stock_072_b0_phys, FSR2L
    movff       stock_073_b0_phys, FSR2H
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
    infsnz      stock_072_b0, F, BANKED
    incf        stock_073_b0, F, BANKED
    infsnz      stock_075_b0, F, BANKED
    incf        stock_076_b0, F, BANKED
    decf        stock_08F_b0, F, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3682
; Address : 0x3682
; Notes   : Inferred core helper routine. Calls: main_flash_service_3796, main_usb_service_41fe, main_core_service_3710.
; ---------------------------------------------------------------------------
main_core_service_3682:
    swapf       stock_0CF_b0, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    bnz         flow_main_core_service_3682_370e
    bra         flow_main_core_service_3682_36e4
flow_main_core_service_3682_368c:
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    movlw       0x04
    movwf       stock_0CD_b0, BANKED
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_3696:
    rcall       main_flash_service_3796
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_369c:
    call        main_usb_service_41fe, 0x0
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36a2:
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    clrf        stock_076_b0, BANKED
    movlw       0xEB
    movwf       stock_075_b0, BANKED
flow_main_core_service_3682_36ac:
    bcf         stock_0CE_b0, 1, BANKED
    movlw       0x01
    movwf       stock_0E7_b0, BANKED
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36b4:
    rcall       main_core_service_3710
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36ba:
    rcall       main_core_service_3432
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36c0:
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    movf        stock_0D3_b0, W, BANKED
    addlw       0xEC
    movwf       stock_005_acc, ACCESS
    clrf        stock_076_b0, BANKED
    movff       saved_w_b0_phys, stock_075_b0_phys
    bra         flow_main_core_service_3682_36ac
flow_main_core_service_3682_36d2:
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    movf        stock_0D3_b0, W, BANKED
    addlw       0xEC
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       stock_0D1_b0_phys, INDF2
    bra         flow_main_core_service_3682_370e
flow_main_core_service_3682_36e4:
    movf        stock_0D0_b0, W, BANKED
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
    clrf        stock_424_b4, BANKED
    clrf        stock_425_b4, BANKED
    bra         flow_main_core_service_3710_3770
flow_main_core_service_3710_3718:
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    btfss       stock_0CE_b0, 0, BANKED
    bra         flow_main_core_service_3710_3780
    movlb       0x4
    bsf         stock_424_b4, 1, BANKED
    bra         flow_main_core_service_3710_3780
flow_main_core_service_3710_3726:
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    bra         flow_main_core_service_3710_3780
flow_main_core_service_3710_372c:
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    rcall       core_filter_addr_from_0x0D3        ; W05-E06 factored
    movff       stock_072_b0_phys, FSR2L
    movff       stock_073_b0_phys, FSR2H
    movf        INDF2, W, ACCESS
    movwf       stock_003_acc, ACCESS
    btfss       stock_003_acc, 2, ACCESS
    bra         flow_main_core_service_3710_3780
    movlw       0x01
    movlb       0x4
    movwf       stock_424_b4, BANKED
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
    movf        stock_0D3_b0, W, BANKED
    andlw       0x0F
    mullw       0x08
    movlw       0x04
    movwf       stock_003_acc, ACCESS
    movwf       stock_004_acc, ACCESS
    movf        PRODL, W, ACCESS
    addwf       stock_003_acc, F, ACCESS
    movf        PRODH, W, ACCESS
    addwfc      stock_004_acc, F, ACCESS
    movlw       0x01
    btfss       stock_0D3_b0, 7, BANKED
    movlw       0x00
    mullw       0x04
    movf        PRODL, W, ACCESS
    addwf       stock_003_acc, W, ACCESS
    movwf       stock_072_b0, BANKED
    movf        PRODH, W, ACCESS
    addwfc      stock_004_acc, W, ACCESS
    movwf       stock_073_b0, BANKED
    return      0
flow_main_core_service_3710_3770:
    movlb       0x0
    movf        stock_0CF_b0, W, BANKED
    andlw       0x1F
    bz          flow_main_core_service_3710_3718
    xorlw       0x01
    bz          flow_main_core_service_3710_3726
    xorlw       0x03
    bz          flow_main_core_service_3710_372c
flow_main_core_service_3710_3780:
    movlb       0x0
    decf        stock_0C8_b0, W, BANKED
    bnz         flow_main_core_service_3710_3794
    movlw       0x04
    movwf       stock_076_b0, BANKED
    movlw       0x24
    movwf       stock_075_b0, BANKED
    bcf         stock_0CE_b0, 1, BANKED
    movlw       0x02
    movwf       stock_0E7_b0, BANKED
flow_main_core_service_3710_3794:
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_3796
; Address : 0x3796
; Notes   : Inferred flash helper; touches flash. Calls: main_flash_service_3810.
; ---------------------------------------------------------------------------
main_flash_service_3796:
    movf        stock_0CF_b0, W, BANKED
    xorlw       0x80
    bz          flow_main_flash_service_3796_37fe
    bra         flow_main_flash_service_3796_380e
flow_main_flash_service_3796_379e:
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    movlw       HIGH(usb_device_descriptor)
    movwf       stock_076_b0, BANKED
    movlw       LOW(usb_device_descriptor)
    movwf       stock_075_b0, BANKED
    movlw       0x12
    bra         flow_main_flash_service_3796_37c4
flow_main_flash_service_3796_37ae:
    tstfsz      stock_0D1_b0, BANKED
    bra         flow_main_flash_service_3796_380c
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    movlw       HIGH(usb_config_descriptor)
    movwf       stock_076_b0, BANKED
    movlw       LOW(usb_config_descriptor)
    movwf       stock_075_b0, BANKED
    clrf        stock_0E8_b0, BANKED
    movlw       0x29
flow_main_flash_service_3796_37c4:
    movwf       stock_0E7_b0, BANKED
    bra         flow_main_flash_service_3796_380c
flow_main_flash_service_3796_37c8:
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    movf        stock_0D1_b0, W, BANKED
    addlw       LOW(string_desc_ptr_table)          ; indexed TBLPTR -> string_desc_ptr_table
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(string_desc_ptr_table)
    movwf       TBLPTRH, ACCESS
    tblrd*+
    movff       TABLAT, stock_075_b0_phys
    movwf       stock_076_b0, BANKED
    movff       stock_075_b0_phys, TBLPTRL
    movff       stock_076_b0_phys, TBLPTRH
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
    movwf       stock_0E7_b0, BANKED
    clrf        stock_0E8_b0, BANKED
    bra         flow_main_flash_service_3796_380c
flow_main_flash_service_3796_37fe:
    movf        stock_0D2_b0, W, BANKED
    xorlw       0x01
    bz          flow_main_flash_service_3796_379e
    xorlw       0x03
    bz          flow_main_flash_service_3796_37ae
    xorlw       0x01
    bz          flow_main_flash_service_3796_37c8
flow_main_flash_service_3796_380c:
    bsf         stock_0CE_b0, 1, BANKED
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
; This is the synchronous preset-table apply path inherited from V2.x.
; It reads one preset table entry from flash (24 bytes, ram_0x013:014 ->
; flash, count 0x17 to ram_0x02F), then issues a single I2C burst to the
; TAS3108 DSP at write addr 0x68 with up to 24 data bytes.
;
; V3.2 hang-hardening: every SEN/PEN wait in this legacy body is bounded.
; Timeout routes through i2c_timeout_recover_advertise, which increments
; diagnostics, resets/clears the MSSP bus, pings the DSP, emits BF/08, and
; returns to the caller instead of stranding the cooperative main loop.
;
; Called from: main_i2c_service_27f0 (DSP I2C refresh), cmd_dispatch_gated
;              (channel sync), some legacy reconnect/wake paths.
; ---------------------------------------------------------------------------
main_i2c_service_381c:
    rcall       preset_table_apply_entry_core
    bnc         flow_main_i2c_service_381c_38a0
    btfsc       stock_00D_acc, 0, ACCESS
    bra         main_i2c_service_381c_pen_timeout
    bra         main_i2c_service_381c_timeout
flow_main_i2c_service_381c_38a0:
    return      0
main_i2c_service_381c_timeout:
    call        i2c_timeout_recover_advertise, 0x0
    return      0
main_i2c_service_381c_pen_timeout:
    call        i2c_pen_timeout_recover_advertise, 0x0
    return      0

; Shared core for legacy blocking applies and the V3.2 async preset job.
; in : ram_0x013/014 = table-entry flash address.
; out: C=0 success or sentinel no-op; C=1 bounded wait timeout.
;      ram_0x00D.bit0 set only for PEN timeout so legacy callers can keep
;      their separate PEN recovery path.
preset_table_apply_entry_core:
    clrf        stock_00D_acc, ACCESS
    movff       stock_013_b0_phys, stock_003_b0_phys                ; copy 16-bit flash addr (caller staged)
    movff       stock_014_b0_phys, stock_004_b0_phys
    clrf        stock_005_acc, ACCESS                   ; high byte and TBLPTRU = 0
    clrf        stock_006_acc, ACCESS
    clrf        stock_008_acc, ACCESS
    movlw       0x04                                ; first read: 4-byte header (TAS reg + len)
    movwf       stock_007_acc, ACCESS
    rcall       flash_read_fsr2_0017                ; W05-E04 helper; now in relative range
    movff       stock_018_b0_phys, stock_02F_b0_phys                ; ram_0x02F = TAS reg byte
    movff       stock_019_b0_phys, stock_031_b0_phys                ; ram_0x031 = byte count
    movlw       0x19                                ; >= 25 -> end-of-table sentinel
    subwf       stock_031_acc, W, ACCESS
    bc          preset_table_apply_entry_done
    ; FIELD-4B: skip volume-family rows (TAS 0x30-0x36).  The volume engine
    ; owns master + per-channel volumes and re-derives them right after
    ; every switch anyway, so the capture-baked values were only ever a
    ; transient overwrite -- but they played LIVE between the master-volume
    ; restore and the engine's per-channel re-walk (2026-06-10 field
    ; incident: loud bass on preset B), persistently if that walk stalled.
    ; Skipping them keeps the user's channel volumes correct end-to-end.
    movlw       0x30
    subwf       stock_02F_acc, W, ACCESS            ; C=1 if reg >= 0x30
    bnc         preset_table_apply_entry_not_vol
    movlw       0x37
    subwf       stock_02F_acc, W, ACCESS            ; C=1 if reg >= 0x37
    bnc         preset_table_apply_entry_done       ; 0x30..0x36 -> benign skip
preset_table_apply_entry_not_vol:
    movlw       0x04                                ; advance past header
    addwf       stock_013_acc, W, ACCESS
    movwf       stock_015_acc, ACCESS
    movlw       0x00
    addwfc      stock_014_acc, W, ACCESS
    movwf       stock_016_acc, ACCESS
    movff       stock_015_b0_phys, stock_003_b0_phys
    movff       stock_016_b0_phys, stock_004_b0_phys
    clrf        stock_005_acc, ACCESS
    clrf        stock_006_acc, ACCESS
    movff       stock_031_b0_phys, stock_007_b0_phys                ; second read = data block
    clrf        stock_008_acc, ACCESS
    rcall       flash_read_fsr2_0017
    bsf         SSPCON2, 0, ACCESS                  ; SEN — START
    call        wait_sen_bounded, 0x0
    bc          preset_table_apply_entry_timeout
    movlw       0x68                                ; TAS3108 write address
    rcall       i2c_byte_tx
    movf        stock_02F_acc, W, ACCESS                ; reg byte
    rcall       i2c_byte_tx
    clrf        stock_030_acc, ACCESS
    bra         preset_table_apply_entry_loop_check
preset_table_apply_entry_loop:
    movf        stock_030_acc, W, ACCESS
    addlw       0x17                                ; data buffer at 0x0017+i
    call        fsr2_page0_read_w, 0x0               ; W04-E03
    rcall       i2c_byte_tx
    incf        stock_030_acc, F, ACCESS
preset_table_apply_entry_loop_check:
    movf        stock_031_acc, W, ACCESS
    subwf       stock_030_acc, W, ACCESS
    bnc         preset_table_apply_entry_loop
    bsf         SSPCON2, 2, ACCESS                  ; PEN — STOP
    call        wait_pen_bounded, 0x0
    bc          preset_table_apply_entry_pen_timeout
preset_table_apply_entry_done:
    bcf         STATUS, 0, ACCESS
    return      0
preset_table_apply_entry_timeout:
    bsf         STATUS, 0, ACCESS
    return      0
preset_table_apply_entry_pen_timeout:
    bsf         stock_00D_acc, 0, ACCESS
    bsf         STATUS, 0, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_38a2
; Address : 0x38A2
; Notes   : Inferred core helper routine. Calls: main_core_service_3398, main_core_service_432e, main_core_service_3f1e.
; ---------------------------------------------------------------------------
main_core_service_38a2:
    movff       stock_041_b0_phys, stock_039_b0_phys
    movff       stock_042_b0_phys, stock_03A_b0_phys
    movff       stock_043_b0_phys, stock_03B_b0_phys
    movff       stock_044_b0_phys, stock_03C_b0_phys
    movff       stock_041_b0_phys, stock_02F_b0_phys
    movff       stock_042_b0_phys, stock_030_b0_phys
    movff       stock_043_b0_phys, stock_031_b0_phys
    movff       stock_044_b0_phys, stock_032_b0_phys
    rcall       main_core_service_3398
    movff       stock_02F_b0_phys, stock_03D_b0_phys
    movff       stock_030_b0_phys, stock_03E_b0_phys
    movff       stock_031_b0_phys, stock_03F_b0_phys
    movff       stock_032_b0_phys, stock_040_b0_phys
    call        main_core_service_432e, 0x0
    movff       stock_039_b0_phys, stock_045_b0_phys
    movff       stock_03A_b0_phys, stock_046_b0_phys
    movff       stock_03B_b0_phys, stock_047_b0_phys
    movff       stock_03C_b0_phys, stock_048_b0_phys
    movff       stock_045_b0_phys, stock_02F_b0_phys
    movff       stock_046_b0_phys, stock_030_b0_phys
    movff       stock_047_b0_phys, stock_031_b0_phys
    movff       stock_048_b0_phys, stock_032_b0_phys
    movlw       0x41
    rcall       main_core_service_3f1e
    movff       stock_041_b0_phys, stock_02F_b0_phys
    movff       stock_042_b0_phys, stock_030_b0_phys
    movff       stock_043_b0_phys, stock_031_b0_phys
    movff       stock_044_b0_phys, stock_032_b0_phys
    rcall       main_core_service_3398
    movff       stock_02F_b0_phys, stock_041_b0_phys
    movff       stock_030_b0_phys, stock_042_b0_phys
    movff       stock_031_b0_phys, stock_043_b0_phys
    movff       stock_032_b0_phys, stock_044_b0_phys
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
    clrf        stock_093_b0, BANKED
    movff       stock_093_b0_phys, stock_0AB_b0_phys
    bcf         INTCON3, 4, ACCESS
    bcf         INTCON3, 1, ACCESS
    bcf         INTCON, 2, ACCESS
    bcf         T0CON, 7, ACCESS
    bcf         INTCON, 5, ACCESS
    clrf        stock_0A4_b0, BANKED
    clrf        stock_0B0_b0, BANKED
    clrf        stock_0B6_b0, BANKED
    clrf        stock_0BA_b0, BANKED
    clrf        event_flags_b0, BANKED
    clrf        dsp_fault_flags_b0, BANKED
    clrf        filename_dirty_flags_b0, BANKED
    clrf        active_flags_acc, ACCESS
    clrf        stock_0BB_b0, BANKED
    clrf        stock_0BC_b0, BANKED
    clrf        an0_delay_b0, BANKED
    clrf        stock_088_b0, BANKED
    clrf        stock_089_b0, BANKED
    bcf         ADCON0, 1, ACCESS
    clrf        stock_094_b0, BANKED
    movlw       0x20
    movlb       0x1
    movwf       stock_10F_b1, BANKED
    movlw       0x21
    movwf       stock_110_b1, BANKED
    movlw       0x22
    movwf       stock_111_b1, BANKED
    movlw       0x23
    movwf       stock_112_b1, BANKED
    movlw       0x25
    movwf       stock_113_b1, BANKED
    movlw       0x27
    movwf       stock_114_b1, BANKED
    movlw       0x28
    movwf       stock_115_b1, BANKED
    retlw       0x28


; ---------------------------------------------------------------------------
; Function: main_i2c_service_39a6
; Address : 0x39A6
; Notes   : Inferred i2c helper routine. Calls: main_core_service_2abc, main_core_service_38a2, main_core_service_301a.
; ---------------------------------------------------------------------------
main_i2c_service_39a6:
    clrf        stock_016_acc, ACCESS
    clrf        stock_017_acc, ACCESS
    clrf        stock_018_acc, ACCESS
    movlw       0x4B
    movwf       stock_019_acc, ACCESS
    movff       stock_049_b0_phys, stock_012_b0_phys
    movff       stock_04A_b0_phys, stock_013_b0_phys
    movff       stock_04B_b0_phys, stock_014_b0_phys
    movff       stock_04C_b0_phys, stock_015_b0_phys
    call        main_core_service_2abc, 0x0
    movff       stock_012_b0_phys, stock_041_b0_phys
    movff       stock_013_b0_phys, stock_042_b0_phys
    movff       stock_014_b0_phys, stock_043_b0_phys
    movff       stock_015_b0_phys, stock_044_b0_phys
    rcall       main_core_service_38a2
    movff       stock_041_b0_phys, stock_04D_b0_phys
    movff       stock_042_b0_phys, stock_04E_b0_phys
    movff       stock_043_b0_phys, stock_04F_b0_phys
    movff       stock_044_b0_phys, stock_050_b0_phys
    movff       stock_04D_b0_phys, stock_025_b0_phys
    movff       stock_04E_b0_phys, stock_026_b0_phys
    movff       stock_04F_b0_phys, stock_027_b0_phys
    movff       stock_050_b0_phys, stock_028_b0_phys
    call        main_core_service_301a, 0x0
    movff       stock_025_b0_phys, stock_051_b0_phys
    movff       stock_026_b0_phys, stock_052_b0_phys
    movff       stock_027_b0_phys, stock_053_b0_phys
    movff       stock_028_b0_phys, stock_054_b0_phys
    movf        stock_054_acc, W, ACCESS
    andlw       0x0F
    rcall       i2c_byte_tx
    movf        stock_053_acc, W, ACCESS
    rcall       i2c_byte_tx
    movf        stock_052_acc, W, ACCESS
    rcall       i2c_byte_tx
    movf        stock_051_acc, W, ACCESS
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
    movf        stock_0CD_b0, W, BANKED
    xorlw       0x06
    btfsc       STATUS, 2, ACCESS
    btfsc       UCON, 1, ACCESS
    bra         flow_main_usb_service_3a26_3a3a
    btfss       active_flags_acc, 3, ACCESS
    bra         flow_main_usb_service_3a26_3a3a
    btfsc       PORTC, 0, ACCESS
    bra         flow_main_usb_service_3a26_3a40
flow_main_usb_service_3a26_3a3a:
    bsf         RCSTA, 4, ACCESS
    bra         flow_main_usb_service_3a26_3aa2
flow_main_usb_service_3a26_3a40:
    tstfsz      stock_0C0_b0, BANKED
    bra         flow_main_usb_service_3a26_3a7e
    movlb       0x4
    btfsc       stock_40C_b4, 7, BANKED
    bra         flow_main_usb_service_3a26_3aa2
    call        prep_bank1_ram004, 0x0
    movlw       0x1A
    movwf       stock_003_acc, ACCESS
    movlw       0x40
    movwf       stock_005_acc, ACCESS
    rcall       main_core_service_3c82
    movlw       0x01
    movlb       0x0
    movwf       stock_0C0_b0, BANKED
    clrf        stock_059_acc, ACCESS
flow_main_usb_service_3a26_3a64:
    movlb       0x1
    movlw       0x5A
    addwf       stock_059_acc, W, ACCESS
    call        setup_fsr2_page_1_or_2, 0x0
    clrf        INDF2, ACCESS
    incf        stock_059_acc, F, ACCESS
    movlw       0x3F
    cpfsgt      stock_059_acc, ACCESS
    bra         flow_main_usb_service_3a26_3a64
    bra         flow_main_usb_service_3a26_3aa2
flow_main_usb_service_3a26_3a7e:
    movlb       0x1
    movf        stock_11A_b1, W, BANKED
    call        hid_command_dispatch, 0x0
    movlb       0x4
    btfsc       stock_410_b4, 7, BANKED
    bra         flow_main_usb_service_3a26_3aa2
    call        prep_bank1_ram004, 0x0
    movlw       0x5A
    movwf       stock_003_acc, ACCESS
    movlw       0x40
    movwf       stock_005_acc, ACCESS
    rcall       main_core_service_3fd0
    movlb       0x0
    clrf        stock_0C0_b0, BANKED
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
    clrf        stock_00E_acc, ACCESS
    clrf        stock_00D_acc, ACCESS
    clrf        stock_00F_acc, ACCESS
    clrf        stock_00B_acc, ACCESS
    movff       saved_w_b0_phys, stock_003_b0_phys
    movff       stock_006_b0_phys, stock_004_b0_phys
    call        main_timer_service_477a, 0x0
flow_uart_rx_with_framing_3ab8:
    call        rx_ring_has_data, 0x0

    bz          flow_uart_rx_with_framing_3b06
    movff       stock_00F_b0_phys, stock_00A_b0_phys
    call        rx_ring_read, 0x0
    movwf       stock_00F_acc, ACCESS
    movf        stock_00D_acc, W, ACCESS
    bz          flow_uart_rx_with_framing_3ae2
    movf        stock_00E_acc, W, ACCESS
    addwf       stock_007_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      stock_008_acc, W, ACCESS
    movwf       FSR2H, ACCESS
    movff       stock_00F_b0_phys, INDF2
    incf        stock_00E_acc, F, ACCESS
    bra         flow_uart_rx_with_framing_3aec
flow_uart_rx_with_framing_3ae2:
    movf        stock_00F_acc, W, ACCESS
    xorlw       0x3A
    bnz         flow_uart_rx_with_framing_3aec
    movlw       0x01
    movwf       stock_00D_acc, ACCESS
flow_uart_rx_with_framing_3aec:
    clrf        stock_00C_acc, ACCESS
    movf        stock_00D_acc, W, ACCESS
    bz          flow_uart_rx_with_framing_3b02
    movf        stock_00A_acc, W, ACCESS
    xorlw       0x0D
    bnz         flow_uart_rx_with_framing_3b02
    movf        stock_00F_acc, W, ACCESS
    xorlw       0x0A
    bnz         flow_uart_rx_with_framing_3b02
    movlw       0x01
    movwf       stock_00C_acc, ACCESS
flow_uart_rx_with_framing_3b02:
    movff       timeout_hi_b0_phys, timeout_lo_b0_phys
flow_uart_rx_with_framing_3b06:
    call        main_usb_service_490c, 0x0
    bc          flow_uart_rx_with_framing_3b16
    movf        stock_009_acc, W, ACCESS
    subwf       stock_00E_acc, W, ACCESS
    bc          flow_uart_rx_with_framing_3b16
    movf        stock_00B_acc, W, ACCESS
    bz          flow_uart_rx_with_framing_3ab8
flow_uart_rx_with_framing_3b16:
    call        main_timer_service_494c, 0x0
    movf        stock_00E_acc, W, ACCESS
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
    bsf         event_flags_b0, 0, BANKED               ; raise t0_tick for main loop
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
    movf        preset_hold_timer_hi_b0, W, BANKED                 ; HOLDING countdown {hi,lo}
    iorwf       preset_hold_timer_lo_b0, W, BANKED
    bz          flow_main_isr_dispatch_3b58          ; reached zero -> stop Timer3
    decf        preset_hold_timer_lo_b0, F, BANKED                 ; 16-bit countdown decrement
    btfss       STATUS, 0, ACCESS                    ; borrow into hi byte?
    decf        preset_hold_timer_hi_b0, F, BANKED
    bra         uart_rx_irq_enqueue
flow_main_isr_dispatch_3b58:
    bcf         T3CON, 0, ACCESS                     ; HOLDING expired: T3 off
    bcf         PIE2, 1, ACCESS                      ; mask Timer3 IE until next job
uart_rx_irq_enqueue:
    btfss       PIR1, 5, ACCESS                      ; RCIF — UART byte arrived?
    bra         flow_main_isr_dispatch_3b8c
    movlb       0x0
    movf        rx_ring_wr_b0, W, BANKED                ; FSR2 = 0x0200 + rx_ring_wr
    call        fsr2_page2_from_W, 0x0               ; W05-E02: FSR2=0x0200|W (movff uses no W)
    movff       RCREG, INDF2                         ; copy RX byte into ring
    incf        rx_ring_wr_b0, F, BANKED
    movlw       0xBF                                 ; ring size = 0xC0 (192 bytes)
    cpfsgt      rx_ring_wr_b0, BANKED                   ; wr > 0xBF -> wrap
    bra         uart_oerr_recover
    clrf        rx_ring_wr_b0, BANKED                   ; wrap to 0
uart_oerr_recover:
    btfss       RCSTA, 1, ACCESS                     ; OERR? (RX overrun)
    bra         flow_main_isr_dispatch_3b8c
    call        uart_soft_recover_full, 0x0
flow_main_isr_dispatch_3b8c:
    movff       isr_save_fsr2h_b0_phys, FSR2H                ; restore FSR2 spilled at vector entry
    movff       isr_save_fsr2l_b0_phys, FSR2L
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
    movlb       0x02
    bsf         chain_tx_emitted_b2, 0, BANKED
    movlb       0x00
    movlw       0x05
    rcall       send_status_burst_preamble
    movf        stock_05F_acc, W, ACCESS
    rcall       send_status_burst_postamble
    movlw       0x07
    rcall       send_status_burst_preamble
    movlb       0x0
    movf        computed_volume_b0, W, BANKED
    addlw       0x60
    rcall       send_status_burst_postamble
    movlw       0x03
    rcall       send_status_burst_preamble
    movlw       0x01
    btfss       active_flags_acc, 3, ACCESS
    movlw       0x00
    rcall       send_status_burst_postamble
    movlw       0x06
    rcall       send_status_burst_preamble
    movlb       0x0
    movf        input_select_b0, W, BANKED
    rcall       send_status_burst_postamble
    movlw       0x1D
    rcall       send_status_burst_preamble
    movlb       0x0
    movf        stock_0B8_b0, W, BANKED
    goto        uart_tx_byte_blocking

send_status_burst_preamble:
    movwf       stock_00D_acc, ACCESS
    movlw       0xBF
    call        uart_tx_byte_blocking, 0x0
    movf        stock_00D_acc, W, ACCESS
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
    clrf        stock_006_acc, ACCESS
    movlw       0x1B
    call        i2c_secondary_dev_write, 0x0
    clrf        stock_006_acc, ACCESS
    movlw       0x1C
    call        i2c_secondary_dev_write, 0x0
    clrf        stock_006_acc, ACCESS
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
    subwf       stock_088_b0, W, BANKED
    movlw       0x02
    subwfb      stock_089_b0, W, BANKED
    bc          flow_hw_standby_shutdown_3c78
    clrf        stock_008_acc, ACCESS
    clrf        stock_009_acc, ACCESS
flow_hw_standby_shutdown_3c58:
    movff       stock_008_b0_phys, stock_006_b0_phys
    movlw       0x1C
    call        i2c_secondary_dev_write, 0x0
    movlw       0x01
    xorwf       stock_008_acc, F, ACCESS
    movlw       0xFA
    call        timer3_blocking_delay_ms_W, 0x0 ; W04-E08 factored (250 ms pulse)
    incf        stock_009_acc, F, ACCESS
    movlw       0x04
    cpfsgt      stock_009_acc, ACCESS
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
    clrf        stock_0CA_b0, BANKED
    movlb       0x4
    btfsc       stock_40C_b4, 7, BANKED
    bra         flow_main_core_service_3c82_3ce6
    movf        stock_005_acc, W, ACCESS
    subwf       stock_40D_b4, W, BANKED
    btfss       STATUS, 0, ACCESS
    movff       stock_40D_b4_phys, saved_w_b0_phys
    movlb       0x0
    clrf        stock_0CA_b0, BANKED
    bra         flow_main_core_service_3c82_3cbc
flow_main_core_service_3c82_3c9c:
    movlw       0x2C
    movlb       0x0
    addwf       stock_0CA_b0, W, BANKED
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x04
    addwfc      FSR2H, F, ACCESS
    movf        stock_0CA_b0, W, BANKED
    addwf       stock_003_acc, W, ACCESS
    movwf       FSR1L, ACCESS
    movlw       0x00
    addwfc      stock_004_acc, W, ACCESS
    movwf       FSR1H, ACCESS
    movff       INDF2, INDF1
    incf        stock_0CA_b0, F, BANKED
flow_main_core_service_3c82_3cbc:
    movf        stock_005_acc, W, ACCESS
    subwf       stock_0CA_b0, W, BANKED
    bnc         flow_main_core_service_3c82_3c9c
    movlw       0x40
    movlb       0x4
    movwf       stock_40D_b4, BANKED
    andwf       stock_40C_b4, F, BANKED
    movlw       0x01
    btfsc       stock_40C_b4, 6, BANKED
    movlw       0x00
    movwf       stock_006_acc, ACCESS
    swapf       stock_006_acc, F, ACCESS
    rlncf       stock_006_acc, F, ACCESS
    rlncf       stock_006_acc, F, ACCESS
    movf        stock_40C_b4, W, BANKED
    xorwf       stock_006_acc, W, ACCESS
    andlw       0xBF
    xorwf       stock_006_acc, W, ACCESS
    movwf       stock_40C_b4, BANKED
    bsf         stock_40C_b4, 3, BANKED
    bsf         stock_40C_b4, 7, BANKED
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
    lfsr        FSR2, stock_003_b0_phys
    movf        POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    bnz         flow_main_flash_service_3ce8_3d04
    movf        stock_007_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    movwf       POSTINC2, ACCESS
    movwf       POSTDEC2, ACCESS
    bra         flow_main_flash_service_3ce8_3d4c
flow_main_flash_service_3ce8_3d04:
    movf        stock_006_acc, W, ACCESS
    andlw       0x7F
    movwf       stock_008_acc, ACCESS
    bcf         STATUS, 0, ACCESS
    rlcf        stock_008_acc, W, ACCESS
    movwf       stock_009_acc, ACCESS
    clrf        stock_00A_acc, ACCESS
    rlcf        stock_00A_acc, F, ACCESS
    movf        stock_007_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       stock_009_b0_phys, POSTINC2
    movff       stock_00A_b0_phys, POSTDEC2
    movf        stock_007_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    btfss       stock_005_acc, 7, ACCESS
    movlw       0x00
    iorwf       POSTINC2, F, ACCESS
    movlw       0x00
    iorwf       POSTDEC2, F, ACCESS
    movf        stock_007_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x82
    addwf       POSTINC2, F, ACCESS
    movlw       0xFF
    addwfc      POSTDEC2, F, ACCESS
    movf        stock_006_acc, W, ACCESS
    andlw       0x80
    iorlw       0x3F
    movwf       stock_006_acc, ACCESS
    bcf         stock_005_acc, 7, ACCESS
flow_main_flash_service_3ce8_3d4c:
    return      0
flow_main_flash_service_3ce8_3d4e:
    lfsr        FSR0, stock_300_b3_phys
    movlw       0xC0
flow_main_flash_service_3ce8_3d54:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         flow_main_flash_service_3ce8_3d54
    lfsr        FSR0, stock_200_b2_phys
    movlw       0xDE
flow_main_flash_service_3ce8_3d60:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         flow_main_flash_service_3ce8_3d60
    lfsr        FSR0, stock_100_b1_phys
    movlw       0xE5
flow_main_flash_service_3ce8_3d6c:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         flow_main_flash_service_3ce8_3d6c
    lfsr        FSR0, stock_060_b0_phys
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
    ; (the wipe loops above stop before 0x2DE), so the range clear below
    ; is the ONLY thing that ever zeroes the cells.  The RCON.BOR/POR
    ; arming below is still done so future code that wants reset-cause
    ; classification can read RCON before re-arming.
    ; --- V3.4 runtime lifecycle clear for wipe-protected BANK 2 cells ---
    ; The broad BANK 2 wipe above clears 0x200..0x2DD.  Everything from
    ; 0x2DE upward is runtime state and is cleared as one contiguous range so
    ; stale async preset, parser-gap, recovery, diagnostics, or filename jobs
    ; cannot resume after reset/reconnect.
    movlb       0x02
    lfsr        FSR0, preset_job_state_b2_phys
    movlw       0x22
v34_runtime_bank2_clear_loop:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         v34_runtime_bank2_clear_loop

    ; --- V3.4 SRC/DSP forensic counter clear (BANK 3 upper block) ---
    ; diag_src_n..diag_src_m (0x3C0..0x3C4) live in wipe-protected BANK 3
    ; upper, so this range clear is the only thing that ever zeroes them —
    ; same unconditional-clear rationale as the BANK 2 diag block above.
    lfsr        FSR0, diag_src_n
    movlw       0x05
v34_src_diag_clear_loop:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         v34_src_diag_clear_loop

    ; --- V3.2 rev 0x37 Tier-1: zero reset-cause flag cells too ---
    ; Cold-init zeroes all four flags before classification picks one
    ; (V32_DIAG_TIER1_SPEC.md §"RAM layout").  The classification cascade
    ; below then writes 1 to whichever flag matches the cleared RCON bit.

    ; --- V3.2 rev 0x37 Tier-1: reset-cause classification cascade ---
    ; Silicon clears the corresponding RCON bit on each reset cause
    ; (PIC18F2455 datasheet 39632e §4.4 + V32_DIAG_TIER1_SPEC.md
    ; §"Reset-cause classification").  Read RCON BEFORE the re-arm
    ; bsfs below so classification sees the as-reported state.
    ;
    ;   RCON.POR (bit 1) clear -> POR fired
    ;   RCON.BOR (bit 0) clear -> BOR fired (with POR still set)
    ;   RCON.TO  (bit 3) clear -> W bucket (normally unreachable while
    ;                              WDT is disabled in V3.2 config/policy)
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
    btfss       RCON, 3, ACCESS                    ; TO cleared (W bucket)?
    bra         diag_classify_wdt
    ; RI cleared OR no recognized bit cleared -> SW bucket (catch-all).
diag_classify_sw:
    movwf       diag_reset_sw_b2, BANKED
    bra         diag_rcon_rearm
diag_classify_por:
    movwf       diag_reset_por_b2, BANKED
    bra         diag_rcon_rearm
diag_classify_bor:
    movwf       diag_reset_bor_b2, BANKED
    bra         diag_rcon_rearm
diag_classify_wdt:
    movwf       diag_reset_wdt_b2, BANKED
    ; fall through
diag_rcon_rearm:
    bsf         RCON, 0, ACCESS                    ; arm BOR detection for next reset
    bsf         RCON, 1, ACCESS                    ; arm POR detection for next reset
    bsf         RCON, 3, ACCESS                    ; arm TO latch for next reset
    bsf         RCON, 4, ACCESS                    ; arm RI  (SW)   for next reset

    clrf        stock_05F_acc, ACCESS
    clrf        active_flags_acc, ACCESS
    movlw       LOW(inline_data_table_47E6)         ; TBLPTR -> inline_data_table_47E6
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(inline_data_table_47E6)
    movwf       TBLPTRH, ACCESS
    movlw       UPPER(inline_data_table_47E6)
    movwf       TBLPTRU, ACCESS
    lfsr        FSR0, stock_1E5_b1_phys
    lfsr        FSR1, stock_016_b0_phys
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
    btfss       active_flags_acc, 2, ACCESS     ; preset B active?
    bra         flash_erase_stock
    ; Remap start address (ram_0x004 = TBLPTRH)
    call        preset_b_remap_start_addr_if_b, 0x0
flash_erase_remap_end:
    ; Remap end address (ram_0x008 = end TBLPTRH)
    movf        stock_00A_acc, W, ACCESS
    iorwf       stock_009_acc, W, ACCESS
    bnz         flash_erase_stock
    movlw       0x56
    subwf       stock_008_acc, W, ACCESS
    bnc         flash_erase_stock
    movlw       0x60
    subwf       stock_008_acc, W, ACCESS
    bc          flash_erase_stock
    movlw       0x0A
    subwf       stock_008_acc, F, ACCESS
flash_erase_stock:
    clrf        stock_00B_acc, ACCESS
    movff       stock_003_b0_phys, timeout_hi_b0_phys
    movff       stock_004_b0_phys, stock_00D_b0_phys
    movff       saved_w_b0_phys, stock_00E_b0_phys
    movff       stock_006_b0_phys, stock_00F_b0_phys
    bra         flow_flash_erase_3df4
flow_flash_erase_3dc0:
    movff       stock_00E_b0_phys, TBLPTRU
    movff       stock_00D_b0_phys, TBLPTRH
    movff       timeout_hi_b0_phys, TBLPTRL
    bsf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    bsf         EECON1, 4, ACCESS
    btfss       INTCON, 7, ACCESS
    bra         flow_flash_erase_3dde
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       stock_00B_acc, ACCESS
flow_flash_erase_3dde:
    rcall       main_flash_service_4406
    movf        stock_00B_acc, W, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         INTCON, 7, ACCESS
    movlw       0x40
    addwf       stock_00C_acc, F, ACCESS
    movlw       0x00
    addwfc      stock_00D_acc, F, ACCESS
    addwfc      stock_00E_acc, F, ACCESS
    addwfc      stock_00F_acc, F, ACCESS
flow_flash_erase_3df4:
    movf        stock_007_acc, W, ACCESS
    subwf       stock_00C_acc, W, ACCESS
    movf        stock_008_acc, W, ACCESS
    subwfb      stock_00D_acc, W, ACCESS
    movf        stock_009_acc, W, ACCESS
    subwfb      stock_00E_acc, W, ACCESS
    movf        stock_00A_acc, W, ACCESS
    subwfb      stock_00F_acc, W, ACCESS
    btfsc       STATUS, 0, ACCESS
    return      0
    bra         flow_flash_erase_3dc0


; ---------------------------------------------------------------------------
; Function: main_core_service_3e0a
; Address : 0x3E0A
; Notes   : Inferred core helper routine. Calls: main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_3e0a:
    clrf        stock_011_acc, ACCESS
    movf        stock_010_acc, W, ACCESS
    xorlw       0x80
    addlw       0x80
    bnz         flow_main_core_service_3e0a_3e24
    movlw       0x00
    subwf       stock_00F_acc, W, ACCESS
    bnz         flow_main_core_service_3e0a_3e24
    movlw       0x00
    subwf       stock_00E_acc, W, ACCESS
    bnz         flow_main_core_service_3e0a_3e24
    movlw       0x00
    subwf       stock_00D_acc, W, ACCESS
flow_main_core_service_3e0a_3e24:
    bc          flow_main_core_service_3e0a_3e3a
    comf        stock_010_acc, F, ACCESS
    comf        stock_00F_acc, F, ACCESS
    comf        stock_00E_acc, F, ACCESS
    negf        stock_00D_acc, ACCESS
    movlw       0x00
    addwfc      stock_00E_acc, F, ACCESS
    addwfc      stock_00F_acc, F, ACCESS
    addwfc      stock_010_acc, F, ACCESS
    movlw       0x01
    movwf       stock_011_acc, ACCESS
flow_main_core_service_3e0a_3e3a:
    movff       stock_00D_b0_phys, stock_003_b0_phys
    movff       stock_00E_b0_phys, stock_004_b0_phys
    movff       stock_00F_b0_phys, saved_w_b0_phys
    movff       stock_010_b0_phys, stock_006_b0_phys
    movlw       0x96
    movwf       stock_007_acc, ACCESS
    movff       stock_011_b0_phys, stock_008_b0_phys
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
    movff       SSPCON1, stock_004_b0_phys
    movlw       0x0F
    andwf       stock_004_acc, F, ACCESS
    movf        stock_004_acc, W, ACCESS
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
    movff       WREG, saved_w_b0_phys
    movff       saved_w_b0_phys, SSPBUF
    btfsc       SSPCON1, 7, ACCESS
    bra         flow_i2c_byte_tx_timeout
    rcall       sspcon1_masked_w
    xorlw       0x08
    bz          flow_i2c_byte_tx_master
    rcall       sspcon1_masked_w
    xorlw       0x0B
    bz          flow_i2c_byte_tx_master
    bsf         SSPCON1, 4, ACCESS
flow_i2c_byte_tx_sspif:
    call        wait_sspif_bounded, 0x0
    bc          flow_i2c_byte_tx_timeout
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
    movff       BSR, stock_00E_b0_phys              ; save caller's BSR
    movlb       0x0
    btfss       SSPCON2, 6, ACCESS          ; skip if NACK (ACKSTAT=1)
    bra         flow_i2c_byte_tx_was_ack
    bsf         dsp_fault_flags_b0, 2, BANKED  ; latch ACKSTAT fault
    diag_inc_sat diag_i                      ; V3.2 Layer 5: count I2C transport fault
flow_i2c_byte_tx_was_ack:
    movff       stock_00E_b0_phys, BSR              ; restore caller's BSR (also undoes any macro BSR clobber)
    movf        SSPCON2, W, ACCESS
flow_i2c_byte_tx_exit:
    return      0
flow_i2c_byte_tx_timeout:
    call        i2c_timeout_recover_advertise, 0x0
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3ec4
; Address : 0x3EC4
; Notes   : Inferred core helper routine. Calls: main_core_service_2abc.
; ---------------------------------------------------------------------------
main_core_service_3ec4:
    movff       WREG, stock_02D_b0_phys
    movf        stock_02D_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       POSTINC2, stock_012_b0_phys
    movff       POSTINC2, stock_013_b0_phys
    movff       POSTINC2, stock_014_b0_phys
    movff       POSTINC2, stock_015_b0_phys
    movff       stock_025_b0_phys, stock_016_b0_phys
    movff       stock_026_b0_phys, stock_017_b0_phys
    movff       stock_027_b0_phys, stock_018_b0_phys
    movff       stock_028_b0_phys, stock_019_b0_phys
    call        main_core_service_2abc, 0x0
    movff       stock_012_b0_phys, stock_029_b0_phys
    movff       stock_013_b0_phys, stock_02A_b0_phys
    movff       stock_014_b0_phys, stock_02B_b0_phys
    movff       stock_015_b0_phys, stock_02C_b0_phys
    movf        stock_02D_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       stock_029_b0_phys, POSTINC2
    movff       stock_02A_b0_phys, POSTINC2
    movff       stock_02B_b0_phys, POSTINC2
    movff       stock_02C_b0_phys, POSTDEC2
    decf        FSR2L, F, ACCESS
    decf        FSR2L, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3f1e
; Address : 0x3F1E
; Notes   : Inferred core helper routine. Calls: main_core_service_24c2.
; ---------------------------------------------------------------------------
main_core_service_3f1e:
    movff       WREG, stock_037_b0_phys
    movf        stock_037_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       POSTINC2, stock_020_b0_phys
    movff       POSTINC2, stock_021_b0_phys
    movff       POSTINC2, stock_022_b0_phys
    movff       POSTINC2, stock_023_b0_phys
    movff       stock_02F_b0_phys, stock_024_b0_phys
    movff       stock_030_b0_phys, stock_025_b0_phys
    movff       stock_031_b0_phys, stock_026_b0_phys
    movff       stock_032_b0_phys, stock_027_b0_phys
    call        main_core_service_24c2, 0x0
    movff       stock_020_b0_phys, stock_033_b0_phys
    movff       stock_021_b0_phys, stock_034_b0_phys
    movff       stock_022_b0_phys, stock_035_b0_phys
    movff       stock_023_b0_phys, stock_036_b0_phys
    movf        stock_037_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       stock_033_b0_phys, POSTINC2
    movff       stock_034_b0_phys, POSTINC2
    movff       stock_035_b0_phys, POSTINC2
    movff       stock_036_b0_phys, POSTDEC2
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
    movff       WREG, saved_w_b0_phys
    clrf        stock_004_acc, ACCESS
    movlw       0x2F
    cpfsgt      stock_005_acc, ACCESS
    bra         flow_intel_hex_checksum_updat_3f90
    movlw       0x3A
    subwf       stock_005_acc, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3f90
    movf        stock_005_acc, W, ACCESS
    addlw       0xD0
    bra         flow_intel_hex_checksum_updat_3fa0
flow_intel_hex_checksum_updat_3f90:
    movlw       0x40
    cpfsgt      stock_005_acc, ACCESS
    bra         flow_intel_hex_checksum_updat_3fa2
    movlw       0x47
    subwf       stock_005_acc, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3fa2
    movf        stock_005_acc, W, ACCESS
    addlw       0xC9
flow_intel_hex_checksum_updat_3fa0:
    movwf       stock_004_acc, ACCESS
flow_intel_hex_checksum_updat_3fa2:
    swapf       stock_004_acc, F, ACCESS
    movlw       0xF0
    andwf       stock_004_acc, F, ACCESS
    movlw       0x2F
    cpfsgt      stock_003_acc, ACCESS
    bra         flow_intel_hex_checksum_updat_3fba
    movlw       0x3A
    subwf       stock_003_acc, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3fba
    movf        stock_003_acc, W, ACCESS
    addlw       0xD0
    bra         flow_intel_hex_checksum_updat_3fca
flow_intel_hex_checksum_updat_3fba:
    movlw       0x40
    cpfsgt      stock_003_acc, ACCESS
    bra         flow_intel_hex_checksum_updat_3fcc
    movlw       0x47
    subwf       stock_003_acc, W, ACCESS
    bc          flow_intel_hex_checksum_updat_3fcc
    movf        stock_003_acc, W, ACCESS
    addlw       0xC9
flow_intel_hex_checksum_updat_3fca:
    addwf       stock_004_acc, F, ACCESS
flow_intel_hex_checksum_updat_3fcc:
    movf        stock_004_acc, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_3fd0
; Address : 0x3FD0
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_3fd0:
    movlw       0x40
    cpfsgt      stock_005_acc, ACCESS
    bra         flow_main_core_service_3fd0_3fd8
    movwf       stock_005_acc, ACCESS
flow_main_core_service_3fd0_3fd8:
    clrf        stock_007_acc, ACCESS
    bra         flow_main_core_service_3fd0_3ffa
flow_main_core_service_3fd0_3fdc:
    movf        stock_007_acc, W, ACCESS
    addwf       stock_003_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      stock_004_acc, W, ACCESS
    movwf       FSR2H, ACCESS
    movlw       0x6C
    addwf       stock_007_acc, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x04
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    incf        stock_007_acc, F, ACCESS
flow_main_core_service_3fd0_3ffa:
    movf        stock_005_acc, W, ACCESS
    subwf       stock_007_acc, W, ACCESS
    bnc         flow_main_core_service_3fd0_3fdc
    movff       saved_w_b0_phys, stock_411_b4_phys
    movlw       0x40
    movlb       0x4
    andwf       stock_410_b4, F, BANKED
    movlw       0x01
    btfsc       stock_410_b4, 6, BANKED
    movlw       0x00
    movwf       stock_006_acc, ACCESS
    swapf       stock_006_acc, F, ACCESS
    rlncf       stock_006_acc, F, ACCESS
    rlncf       stock_006_acc, F, ACCESS
    movf        stock_410_b4, W, BANKED
    xorwf       stock_006_acc, W, ACCESS
    andlw       0xBF
    xorwf       stock_006_acc, W, ACCESS
    movwf       stock_410_b4, BANKED
    bsf         stock_410_b4, 3, BANKED
    bsf         stock_410_b4, 7, BANKED
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
    clrf        stock_00A_acc, ACCESS
    movlw       0x17
    movwf       stock_009_acc, ACCESS
    ; fall through into flash_read
flash_read:
    call        preset_b_remap_start_addr, 0x0
flash_read_stock:
    movff       stock_003_b0_phys, timeout_lo_b0_phys
    movff       stock_004_b0_phys, timeout_hi_b0_phys
    movff       saved_w_b0_phys, stock_00D_b0_phys
    movff       stock_006_b0_phys, stock_00E_b0_phys
    movff       TBLPTRU, stock_011_b0_phys
    movff       TBLPTRH, stock_010_b0_phys
    movff       TBLPTRL, stock_00F_b0_phys
    movff       stock_00D_b0_phys, TBLPTRU
    movff       timeout_hi_b0_phys, TBLPTRH
    movff       timeout_lo_b0_phys, TBLPTRL
    bra         flow_flash_read_4064
flow_flash_read_4052:
    tblrd*+
    movff       stock_009_b0_phys, FSR2L
    movff       stock_00A_b0_phys, FSR2H
    movff       TABLAT, INDF2
    infsnz      stock_009_acc, F, ACCESS
    incf        stock_00A_acc, F, ACCESS
flow_flash_read_4064:
    decf        stock_007_acc, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        stock_008_acc, F, ACCESS
    incf        stock_007_acc, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    incf        stock_008_acc, W, ACCESS
    bnz         flow_flash_read_4052
    movff       stock_011_b0_phys, TBLPTRU
    movff       stock_010_b0_phys, TBLPTRH
    movff       stock_00F_b0_phys, TBLPTRL
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4080
; Address : 0x4080
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4080:
    movff       WREG, stock_003_b0_phys
    movlw       0x08
    movlb       0x1
    movwf       stock_117_b1, BANKED
    movlw       0x04
    movwf       stock_119_b1, BANKED
    movlw       0x1C
    movwf       stock_118_b1, BANKED
    tstfsz      stock_003_acc, ACCESS
    bra         flow_main_core_service_4080_40a8
    movlw       0x04
    movwf       stock_119_b1, BANKED
    movlw       0x14
    movwf       stock_118_b1, BANKED
    movlw       0x04
    movlb       0x0
    movwf       stock_079_b0, BANKED
    movlw       0x00
    bra         flow_main_core_service_4080_40ae
flow_main_core_service_4080_40a8:
    movlw       0x04
    movlb       0x0
    movwf       stock_079_b0, BANKED
flow_main_core_service_4080_40ae:
    movwf       stock_078_b0, BANKED
    movff       stock_078_b0_phys, FSR2L
    movff       stock_079_b0_phys, FSR2H
    movff       stock_116_b1_phys, POSTINC2
    movff       stock_117_b1_phys, POSTINC2
    movff       stock_118_b1_phys, POSTINC2
    movff       stock_119_b1_phys, POSTINC2
    movff       stock_078_b0_phys, FSR2L
    movff       stock_079_b0_phys, FSR2H
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
    movwf       stock_0CD_b0, BANKED
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
    movwf       stock_116_b1, BANKED
    movlw       0x00
    rcall       main_core_service_4080
    movlw       0x01
    movwf       stock_096_b0, BANKED
    clrf        stock_0CE_b0, BANKED
    clrf        stock_0EB_b0, BANKED
    movlw       0x00
    goto        main_core_service_48fe


; ---------------------------------------------------------------------------
; Function: main_adc_service_4124
; Address : 0x4124
; Notes   : Inferred adc helper; touches adc.
; ---------------------------------------------------------------------------
main_adc_service_4124:
    clrf        stock_007_acc, ACCESS
    clrf        stock_008_acc, ACCESS
    movf        stock_006_acc, W, ACCESS
    iorwf       stock_005_acc, W, ACCESS
    bz          flow_main_adc_service_4124_4164
    movlw       0x01
    movwf       stock_009_acc, ACCESS
    bra         flow_main_adc_service_4124_413c
flow_main_adc_service_4124_4134:
    bcf         STATUS, 0, ACCESS
    rlcf        stock_005_acc, F, ACCESS
    rlcf        stock_006_acc, F, ACCESS
    incf        stock_009_acc, F, ACCESS
flow_main_adc_service_4124_413c:
    btfss       stock_006_acc, 7, ACCESS
    bra         flow_main_adc_service_4124_4134
flow_main_adc_service_4124_4140:
    bcf         STATUS, 0, ACCESS
    rlcf        stock_007_acc, F, ACCESS
    rlcf        stock_008_acc, F, ACCESS
    movf        stock_005_acc, W, ACCESS
    subwf       stock_003_acc, W, ACCESS
    movf        stock_006_acc, W, ACCESS
    subwfb      stock_004_acc, W, ACCESS
    bnc         flow_main_adc_service_4124_415a
    movf        stock_005_acc, W, ACCESS
    subwf       stock_003_acc, F, ACCESS
    movf        stock_006_acc, W, ACCESS
    subwfb      stock_004_acc, F, ACCESS
    bsf         stock_007_acc, 0, ACCESS
flow_main_adc_service_4124_415a:
    bcf         STATUS, 0, ACCESS
    rrcf        stock_006_acc, F, ACCESS
    rrcf        stock_005_acc, F, ACCESS
    decfsz      stock_009_acc, F, ACCESS
    bra         flow_main_adc_service_4124_4140
flow_main_adc_service_4124_4164:
    movff       stock_007_b0_phys, stock_003_b0_phys
    movff       stock_008_b0_phys, stock_004_b0_phys
    return      0
an0_hysteresis_monitor:
    movlb       0x0                                  ; callers may leave BSR=2; ram_0x0A1 is bank 0
    btfss       active_flags_acc, 3, ACCESS
    bra         flow_main_adc_service_4124_41b4
    movf        an0_delay_b0, W, BANKED
    xorlw       0x64
    bnz         flow_main_adc_service_4124_41b2
    btfsc       ADCON0, 1, ACCESS
    bra         flow_main_adc_service_4124_41ae
    movf        ADRESH, W, ACCESS
    movwf       stock_004_acc, ACCESS
    clrf        stock_003_acc, ACCESS
    movf        ADRESL, W, ACCESS
    addwf       stock_003_acc, W, ACCESS
    movwf       stock_088_b0, BANKED
    movlw       0x00
    addwfc      stock_004_acc, W, ACCESS
    movwf       stock_089_b0, BANKED
    movlw       0x29
    subwf       stock_088_b0, W, BANKED
    movlw       0x02
    subwfb      stock_089_b0, W, BANKED
    btfsc       STATUS, 0, ACCESS
    bsf         stock_094_b0, 2, BANKED
    bsf         ADCON0, 1, ACCESS
    btfss       stock_094_b0, 2, BANKED
    bra         flow_main_adc_service_4124_41ae
    movlw       0x28
    subwf       stock_088_b0, W, BANKED
    movlw       0x02
    subwfb      stock_089_b0, W, BANKED
    bc          flow_main_adc_service_4124_41ae
    bcf         active_flags_acc, 3, ACCESS
    bsf         event_flags_b0, 2, BANKED
    diag_inc_sat diag_a                              ; V3.2 Layer 5: count AN0-triggered standby
    movlb       0x0                                  ; macro clobbers BSR; restore for the bra below
flow_main_adc_service_4124_41ae:
    clrf        an0_delay_b0, BANKED
    bra         flow_main_adc_service_4124_41b4
flow_main_adc_service_4124_41b2:
    incf        an0_delay_b0, F, BANKED
flow_main_adc_service_4124_41b4:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_41b6
; Address : 0x41B6
; Notes   : Inferred core helper routine. Calls: main_core_service_34c8.
; ---------------------------------------------------------------------------
main_core_service_41b6:
    movff       WREG, stock_017_b0_phys
    movff       stock_017_b0_phys, stock_016_b0_phys
    movf        stock_013_acc, W, ACCESS
    xorlw       0x80
    movwf       PRODL, ACCESS
    movlw       0x80
    subwf       PRODL, W, ACCESS
    movlw       0x00
    btfsc       STATUS, 2, ACCESS
    subwf       stock_012_acc, W, ACCESS
    bc          flow_main_core_service_41b6_41e4
    movf        stock_017_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x2D
    movwf       INDF2, ACCESS
    incf        stock_017_acc, F, ACCESS
    negf        stock_012_acc, ACCESS
    comf        stock_013_acc, F, ACCESS
    btfsc       STATUS, 0, ACCESS
    incf        stock_013_acc, F, ACCESS
flow_main_core_service_41b6_41e4:
    movff       stock_012_b0_phys, stock_00A_b0_phys
    movff       stock_013_b0_phys, timeout_lo_b0_phys
    movff       stock_014_b0_phys, timeout_hi_b0_phys
    movff       stock_015_b0_phys, stock_00D_b0_phys
    movf        stock_017_acc, W, ACCESS
    call        main_core_service_34c8, 0x0
    movf        stock_016_acc, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_41fe
; Address : 0x41FE
; Notes   : Inferred usb helper; touches usb. Calls: main_core_service_48fe.
; ---------------------------------------------------------------------------
main_usb_service_41fe:
    movlw       0x01
    movwf       stock_0C8_b0, BANKED
    clrf        UEP1, ACCESS
    clrf        UEP2, ACCESS
    clrf        UEP3, ACCESS
    clrf        UEP4, ACCESS
    clrf        UEP5, ACCESS
    clrf        UEP6, ACCESS
    clrf        UEP7, ACCESS
    clrf        stock_091_b0, BANKED
flow_main_usb_service_41fe_4212:
    movf        stock_091_b0, W, BANKED
    addlw       0xEC
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    clrf        INDF2, ACCESS
    incf        stock_091_b0, F, BANKED
    movf        stock_091_b0, W, BANKED
    bz          flow_main_usb_service_41fe_4212
    movff       stock_0D1_b0_phys, stock_0EB_b0_phys
    movf        stock_0EB_b0, W, BANKED
    rcall       main_core_service_48fe
    movlb       0x0
    tstfsz      stock_0D1_b0, BANKED
    bra         flow_main_usb_service_41fe_4236
    movlw       0x05
    bra         flow_main_usb_service_41fe_4238
flow_main_usb_service_41fe_4236:
    movlw       0x06
flow_main_usb_service_41fe_4238:
    movwf       stock_0CD_b0, BANKED
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
    movff       WREG, stock_006_b0_phys
    rcall       i2c_wait_bus_idle
    bsf         SSPCON2, 0, ACCESS
    rcall       wait_sen_bounded
    bc          i2c_secondary_dev_random_timeout
    movlw       0xE2
    rcall       i2c_byte_tx
    movf        stock_006_acc, W, ACCESS
    rcall       i2c_byte_tx
    bsf         SSPCON2, 1, ACCESS
    rcall       wait_rsen_bounded
    bc          i2c_secondary_dev_random_timeout
    movlw       0xE3
    rcall       i2c_byte_tx
    rcall       main_i2c_service_464c
    movwf       stock_007_acc, ACCESS
    bsf         SSPCON2, 5, ACCESS
    bsf         SSPCON2, 4, ACCESS
    rcall       wait_acken_bounded
    bc          i2c_secondary_dev_random_timeout
    bsf         SSPCON2, 2, ACCESS
    rcall       wait_pen_bounded
    bc          i2c_secondary_dev_random_pen_timeout
    movf        stock_007_acc, W, ACCESS
    bcf         STATUS, 0, ACCESS
    return      0
i2c_secondary_dev_random_timeout:
    call        i2c_timeout_recover_advertise, 0x0
    clrf        WREG, ACCESS
    return      0
i2c_secondary_dev_random_pen_timeout:
    call        i2c_pen_timeout_recover_advertise, 0x0
    clrf        WREG, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_427a
; Address : 0x427A
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_427a:
    movf        stock_006_acc, W, ACCESS
    iorwf       stock_005_acc, W, ACCESS
    bz          flow_main_core_service_427a_42ae
    movlw       0x01
    movwf       stock_007_acc, ACCESS
    bra         flow_main_core_service_427a_428e
flow_main_core_service_427a_4286:
    bcf         STATUS, 0, ACCESS
    rlcf        stock_005_acc, F, ACCESS
    rlcf        stock_006_acc, F, ACCESS
    incf        stock_007_acc, F, ACCESS
flow_main_core_service_427a_428e:
    btfss       stock_006_acc, 7, ACCESS
    bra         flow_main_core_service_427a_4286
flow_main_core_service_427a_4292:
    movf        stock_005_acc, W, ACCESS
    subwf       stock_003_acc, W, ACCESS
    movf        stock_006_acc, W, ACCESS
    subwfb      stock_004_acc, W, ACCESS
    bnc         flow_main_core_service_427a_42a4
    movf        stock_005_acc, W, ACCESS
    subwf       stock_003_acc, F, ACCESS
    movf        stock_006_acc, W, ACCESS
    subwfb      stock_004_acc, F, ACCESS
flow_main_core_service_427a_42a4:
    bcf         STATUS, 0, ACCESS
    rrcf        stock_006_acc, F, ACCESS
    rrcf        stock_005_acc, F, ACCESS
    decfsz      stock_007_acc, F, ACCESS
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
    clrf        stock_408_b4, BANKED
    movlb       0x0
    clrf        stock_0CC_b0, BANKED
    movlb       0x4
    btfss       stock_400_b4, 7, BANKED
    bra         flow_main_usb_service_42f4_4308
    clrf        stock_400_b4, BANKED
    movlb       0x0
    clrf        stock_096_b0, BANKED
flow_main_usb_service_42f4_4308:
    movlb       0x4
    btfss       stock_404_b4, 7, BANKED
    bra         flow_main_usb_service_42f4_4316
    clrf        stock_404_b4, BANKED
    movlw       0x01
    movlb       0x0
    movwf       stock_096_b0, BANKED
flow_main_usb_service_42f4_4316:
    movlb       0x0
    clrf        stock_0C9_b0, BANKED
    clrf        stock_0C8_b0, BANKED
    clrf        stock_0E7_b0, BANKED
    clrf        stock_0E8_b0, BANKED
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
    xorwf       stock_040_acc, F, ACCESS
    movff       stock_039_b0_phys, stock_020_b0_phys
    movff       stock_03A_b0_phys, stock_021_b0_phys
    movff       stock_03B_b0_phys, stock_022_b0_phys
    movff       stock_03C_b0_phys, stock_023_b0_phys
    movff       stock_03D_b0_phys, stock_024_b0_phys
    movff       stock_03E_b0_phys, stock_025_b0_phys
    movff       stock_03F_b0_phys, stock_026_b0_phys
    movff       stock_040_b0_phys, stock_027_b0_phys
    call        main_core_service_24c2, 0x0
    movff       stock_020_b0_phys, stock_039_b0_phys
    movff       stock_021_b0_phys, stock_03A_b0_phys
    movff       stock_022_b0_phys, stock_03B_b0_phys
    movff       stock_023_b0_phys, stock_03C_b0_phys
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
    movff       WREG, stock_006_b0_phys
    rcall       i2c_wait_bus_idle
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    rcall       wait_sen_bounded
    bc          i2c_reg1f_timeout
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
    movf        stock_006_acc, W, ACCESS
    rcall       i2c_byte_tx
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    rcall       wait_pen_bounded
    bc          i2c_reg1f_pen_timeout
i2c_reg1f_done:
    return      0
i2c_reg1f_timeout:
    rcall       i2c_timeout_recover_advertise
    return      0
i2c_reg1f_pen_timeout:
    rcall       i2c_pen_timeout_recover_advertise
    return      0


; ---------------------------------------------------------------------------
; Function: main_uart_service_43a2
; Address : 0x43A2
; Notes   : Inferred uart helper routine. Calls: tblrd_lookup, uart_tx_byte_blocking.
; ---------------------------------------------------------------------------
main_uart_service_43a2:
    movff       WREG, stock_006_b0_phys
    movff       stock_006_b0_phys, stock_004_b0_phys
    swapf       stock_004_acc, F, ACCESS
    movlw       0x0F
    andwf       stock_004_acc, F, ACCESS
    rcall       tblrd_lookup
    rcall       uart_tx_byte_blocking
    movwf       stock_005_acc, ACCESS
    movff       stock_006_b0_phys, stock_004_b0_phys
    movlw       0x0F
    rcall       tblrd_lookup
    rcall       uart_tx_byte_blocking
    xorwf       stock_005_acc, F, ACCESS
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
    andwf       stock_004_acc, F, ACCESS
    movf        stock_004_acc, W, ACCESS
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
    movff       stock_003_b0_phys, EEADR
    movff       saved_w_b0_phys, EEDATA
    bcf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    movlw       0x00
    btfsc       INTCON, 7, ACCESS
    movlw       0x01
    movwf       stock_006_acc, ACCESS
    bcf         INTCON, 7, ACCESS
    rcall       main_flash_service_4406
flow_eeprom_write_blocking_43f4:
    btfsc       EECON1, 1, ACCESS
    bra         flow_eeprom_write_blocking_43f4
    btfsc       stock_006_acc, 0, ACCESS
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
    movf        stock_0CD_b0, W, BANKED
    xorlw       0x04
    bnz         flow_main_usb_service_4412_4426
    movff       stock_0D1_b0_phys, UADDR
    movf        UADDR, W, ACCESS
    movlw       0x05
    btfsc       STATUS, 2, ACCESS
    movlw       0x03
    movwf       stock_0CD_b0, BANKED
flow_main_usb_service_4412_4426:
    decf        stock_0C9_b0, W, BANKED
    bnz         flow_main_usb_service_4412_4446
    call        main_flash_service_35f0, 0x0
    movf        stock_0CC_b0, W, BANKED
    xorlw       0x02
    bnz         flow_main_usb_service_4412_443a
    movlw       0x04
    movlb       0x4
    bra         flow_main_usb_service_4412_4442
flow_main_usb_service_4412_443a:
    movlb       0x4
    movlw       0x48
    btfsc       stock_408_b4, 6, BANKED
    movlw       0x08
flow_main_usb_service_4412_4442:
    movwf       stock_408_b4, BANKED
    bsf         stock_408_b4, 7, BANKED
flow_main_usb_service_4412_4446:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4448
; Address : 0x4448
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4448:
    movff       WREG, stock_003_b0_phys
    bra         flow_main_core_service_4448_446c
flow_main_core_service_4448_444e:
    movlw       0x01
    movwf       stock_0A0_b0, BANKED
    clrf        stock_0B9_b0, BANKED
    bra         flow_main_core_service_4448_447c
flow_main_core_service_4448_4456:
    clrf        stock_0A0_b0, BANKED
    movlw       0x01
    bra         flow_main_core_service_4448_4468
flow_main_core_service_4448_445c:
    movlw       0x02
    movwf       stock_0A0_b0, BANKED
    bra         flow_main_core_service_4448_4468
flow_main_core_service_4448_4462:
    movlw       0x01
    movwf       stock_0A0_b0, BANKED
    movlw       0x03
flow_main_core_service_4448_4468:
    movwf       stock_0B9_b0, BANKED
    bra         flow_main_core_service_4448_447c
flow_main_core_service_4448_446c:
    movf        stock_003_acc, W, ACCESS
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
    movwf       stock_003_acc, ACCESS
    clrf        stock_004_acc, ACCESS
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
    decf        stock_003_acc, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        stock_004_acc, F, ACCESS
flow_timer3_blocking_delay_44a8:
    movf        stock_004_acc, W, ACCESS
    iorwf       stock_003_acc, W, ACCESS
    bnz         flow_timer3_blocking_delay_4488
    bcf         T3CON, 0, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_uart_service_44b2
; Address : 0x44B2
; Notes   : Inferred uart helper routine. Calls: uart_tx_byte_blocking, uart_tx_block_from_buffer.
; ---------------------------------------------------------------------------
main_uart_service_44b2:
    movff       WREG, stock_01B_b0_phys
    movlw       0x0D
    rcall       uart_tx_byte_blocking
    movlw       0x0A
    rcall       uart_tx_byte_blocking
    movlw       0x0C
    rcall       uart_tx_byte_blocking
    movlw       0x3A
    rcall       uart_tx_byte_blocking
    clrf        stock_019_acc, ACCESS
    movff       stock_01B_b0_phys, stock_018_b0_phys
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
; block (0x055..0x058, ACCESS) and then jumps into volume_dsp_write so the
; muted zero write uses the same ACK/NACK retry and BF/08 fault contract as
; normal volume writes.
;
; Callers:
;   - flow_cmd_dispatch entry clear + write  (was 5 inline lines)
;   - flow_cmd_dispatch_gated post-gate write (was 5 inline lines)
;   - mssp_hard_reset post-reset clear + write (was 5 inline lines)
;   - preset_force_mute  (tail-call via `bra`; helper chains through
;                         volume_dsp_write's `return` back to the caller of
;                         preset_force_mute)
;
; BSR/Z/W: BSR unchanged at entry to volume_dsp_write, STATUS.Z = 1 (last
; clrf).  V3.4 forensic M sets W=0x0F and clobbers FSR0 via diag_inc_sat_fsr0
; before the clrf pattern; all four callers immediately return/branch without
; relying on W, FSR0, or post-pattern flags.
;
; Savings : (sites 1-3) 3 × (12 B -> 4 B) + (site 4) 1 × (12 B -> 2 B)
;           − 8 B helper = 24 + 10 − 8 = 26 B.
; ---------------------------------------------------------------------------
clrf_i2c_coeff_0123_and_write:
    ; V3.4 forensic M: every DSP mute write (TAS 0x30 <- 0) passes here.
    movlw       0x04                        ; index 4 = M
    rcall       diag_src_inc_w
    clrf        i2c_coeff_0_acc, ACCESS
    clrf        i2c_coeff_1_acc, ACCESS
    clrf        i2c_coeff_2_acc, ACCESS
    clrf        i2c_coeff_3_acc, ACCESS
    goto        volume_dsp_write

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
    rcall       wait_sen_bounded
    bc          coeff_write_timeout
    movlw       0x68
    rcall       i2c_byte_tx
    movlw       0x30
    rcall       i2c_byte_tx
    movff       i2c_coeff_0_b0_phys, stock_049_b0_phys
    movff       i2c_coeff_1_b0_phys, stock_04A_b0_phys
    movff       i2c_coeff_2_b0_phys, stock_04B_b0_phys
    movff       i2c_coeff_3_b0_phys, stock_04C_b0_phys
    call        main_i2c_service_39a6, 0x0
    bsf         SSPCON2, 2, ACCESS          ; stock STOP wait
    rcall       wait_pen_bounded
    bc          coeff_write_pen_timeout
coeff_write_pen_done:
    return      0
coeff_write_timeout:
    rcall       i2c_timeout_recover_advertise
    return      0
coeff_write_pen_timeout:
    rcall       i2c_pen_timeout_recover_advertise
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4516
; Address : 0x4516
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4516:
    tstfsz      stock_05F_acc, ACCESS
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
    movf        stock_093_b0, W, BANKED
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
; diag_inc_sat_fsr0 — shared Layer 5 saturating counter increment
; ---------------------------------------------------------------------------
; in : FSR0 points at one byte in the diag counter block; BSR already 2
; out: W=0x0F, BSR unchanged, target clamped/saturated/incremented:
;      >0x0F -> 0x0F, ==0x0F unchanged, <0x0F incremented.
; note: uses INDF0/ACCESS so the target is bank-agnostic after FSR0 setup.
; ---------------------------------------------------------------------------
diag_inc_sat_fsr0:
    movlw       0x0F
    cpfsgt      INDF0, ACCESS             ; skip if counter > 0x0F
    bra         diag_inc_sat_check_low
    movwf       INDF0, ACCESS             ; counter > 0x0F: clamp to 0x0F
    return      0
diag_inc_sat_check_low:
    cpfslt      INDF0, ACCESS             ; skip if counter < 0x0F
    return      0                         ; counter == 0x0F: saturate
    incf        INDF0, F, ACCESS          ; counter < 0x0F: increment
    return      0

; ---------------------------------------------------------------------------
; diag_src_inc_w — V3.4 SRC/DSP forensic counter increment by index
; ---------------------------------------------------------------------------
; in : W = counter index 0..4 (N L C T M order, diag_src_n..diag_src_m)
; out: same contract as diag_inc_sat_fsr0 (W=0x0F, FSR0 -> cell, BSR
;      unchanged).  The five cells are contiguous in BANK 3 upper
;      (0x3C0..0x3C4) so the FSR0L add never carries into FSR0H.
; Shared indexed entry instead of per-site lfsr pairs: each call site is
; movlw+call (3 words) / movlw+rcall (2 words) — the flash margin before
; the 0x4C00 preset tables is the binding constraint for V3.4.
; ---------------------------------------------------------------------------
diag_src_inc_w:
    lfsr        FSR0, diag_src_n
    addwf       FSR0L, F, ACCESS
    bra         diag_inc_sat_fsr0

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
    clrf        rx_ring_rd_b0, BANKED
    clrf        rx_ring_wr_b0, BANKED
    clrf        rx_frame_position_b0, BANKED
    clrf        stock_0A2_b0, BANKED
    clrf        current_cmd_data_b0, BANKED
    clrf        stock_0BC_b0, BANKED
    bcf         active_flags_acc, 0, ACCESS
    bcf         active_flags_acc, 6, ACCESS
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
    movf        rx_frame_position_b0, F, BANKED
    btfsc       STATUS, 2, ACCESS               ; Z = parser idle
    bra         main_rx_frame_gap_idle
    movf        rx_ring_wr_b0, W, BANKED
    cpfseq      rx_ring_rd_b0, BANKED               ; ring has data? parser about to progress
    bra         main_rx_frame_gap_idle
    movlb       0x2
    infsnz      main_rx_frame_gap_timeout_b2, F, BANKED
    bra         main_rx_frame_gap_expired
    return      0
main_rx_frame_gap_expired:
    movlb       0x0
    clrf        rx_frame_position_b0, BANKED
    bcf         active_flags_acc, 0, ACCESS
    ; fall through to idle — clears the timeout after reset
main_rx_frame_gap_idle:
    movlb       0x2
    clrf        main_rx_frame_gap_timeout_b2, BANKED
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
    clrf        rx_ring_rd_b0, BANKED
    clrf        rx_ring_wr_b0, BANKED
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
    ; V3.4 forensic T: every full blocking preset-table walk (cold init,
    ; wake bring-up, EP0/reconnect reapply) enters here.
    movlw       0x03                        ; index 3 = T
    rcall       diag_src_inc_w
    movlw       0x56
    movwf       stock_033_acc, ACCESS
    clrf        stock_032_acc, ACCESS
    clrf        stock_034_acc, ACCESS
flow_main_core_service_4574_457e:
    movff       stock_032_b0_phys, stock_013_b0_phys
    movff       stock_033_b0_phys, stock_014_b0_phys
    call        main_i2c_service_381c, 0x0
    movlw       0x18
    addwf       stock_032_acc, F, ACCESS
    movlw       0x00
    addwfc      stock_033_acc, F, ACCESS
    incf        stock_034_acc, F, ACCESS
    movlw       0x5F
    cpfsgt      stock_034_acc, ACCESS
    bra         flow_main_core_service_4574_457e
    movwf       stock_014_acc, ACCESS
    clrf        stock_013_acc, ACCESS
    goto        main_i2c_service_381c


; ---------------------------------------------------------------------------
; Function: main_usb_service_45a2
; Address : 0x45A2
; Notes   : Inferred usb helper; touches usb. Calls: main_core_service_2328, main_core_service_3fd0.
; ---------------------------------------------------------------------------
main_usb_service_45a2:
    call        main_core_service_2328, 0x0
    movf        stock_0CD_b0, W, BANKED
    xorlw       0x06
    btfsc       STATUS, 2, ACCESS
    btfsc       UCON, 1, ACCESS
    bra         flow_main_usb_service_45a2_45cc
    btfss       PORTC, 0, ACCESS
    bra         flow_main_usb_service_45a2_45cc
    movlb       0x4
    btfsc       stock_410_b4, 7, BANKED
    bra         flow_main_usb_service_45a2_45cc
    call        prep_bank1_ram004, 0x0
    movlw       0x5A
    movwf       stock_003_acc, ACCESS
    movlw       0x40
    movwf       stock_005_acc, ACCESS
    rcall       main_core_service_3fd0
flow_main_usb_service_45a2_45cc:
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_45ce
; Address : 0x45CE
; Notes   : Inferred core helper routine. Calls: main_core_service_30d8.
; ---------------------------------------------------------------------------
main_core_service_45ce:
    movff       WREG, stock_011_b0_phys
    movf        stock_011_acc, W, ACCESS
    movwf       stock_003_acc, ACCESS
    clrf        stock_004_acc, ACCESS
    clrf        stock_005_acc, ACCESS
    clrf        stock_006_acc, ACCESS
    movlw       0x96
    movwf       stock_007_acc, ACCESS
    clrf        stock_008_acc, ACCESS
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
    clrf        stock_004_acc, ACCESS
    rcall       rx_ring_has_data

    bz          flow_rx_ring_read_4620
    ; Task #8 (session-49 lost mute frame): every consumed byte is parser
    ; PROGRESS, so it must reset the mid-frame stall watchdog.  The stock
    ; parser idles at fpos=1 after each dispatched frame, letting the
    ; watchdog counter accumulate across inter-frame idle; un-reset, a
    ; near-wrap carry could expire INSIDE a frame's normal 320 us
    ; inter-byte gap and silently discard the frame.
    movlb       0x2
    clrf        main_rx_frame_gap_timeout_b2, BANKED
    movlb       0x0
    movf        rx_ring_rd_b0, W, BANKED
    rcall       fsr2_page2_from_W                    ; W05-E02: FSR2=0x0200|W (movf INDF2 overwrites W)
    movf        INDF2, W, ACCESS
    movwf       stock_004_acc, ACCESS
    incf        rx_ring_rd_b0, F, BANKED
    movlw       0xBF
    cpfsgt      rx_ring_rd_b0, BANKED
    bra         flow_rx_ring_read_4620
    clrf        rx_ring_rd_b0, BANKED
flow_rx_ring_read_4620:
    movf        stock_004_acc, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_4624
; Address : 0x4624
; Notes   : Inferred usb helper; touches usb.
; ---------------------------------------------------------------------------
main_usb_service_4624:
    clrf        stock_0CA_b0, BANKED
    movlw       0x1E
    movwf       UEP1, ACCESS
    movlw       0x40
    movlb       0x4
    movwf       stock_40D_b4, BANKED
    movlw       0x04
    movwf       stock_40F_b4, BANKED
    movlw       0x2C
    movwf       stock_40E_b4, BANKED
    movlw       0x08
    movwf       stock_40C_b4, BANKED
    bsf         stock_40C_b4, 7, BANKED
    movlw       0x04
    movwf       stock_413_b4, BANKED
    movlw       0x6C
    movwf       stock_412_b4, BANKED
    movlw       0x40
    movwf       stock_410_b4, BANKED
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
    rcall       wait_bf_set_bounded
    bc          main_i2c_service_464c_timeout
    movf        SSPBUF, W, ACCESS
    return      0
main_i2c_service_464c_timeout:
    rcall       i2c_timeout_recover_advertise
    clrf        WREG, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: main_core_service_4672
; Address : 0x4672
; Notes   : Inferred core helper routine. Calls: main_uart_service_44b2.
; ---------------------------------------------------------------------------
main_core_service_4672:
    lfsr        FSR2, stock_1F4_b1_phys
    lfsr        FSR1, stock_01C_b0_phys
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
    clrf        stock_01A_acc, ACCESS
    bra         flow_uart_tx_block_from_buffe_46a2
flow_uart_tx_block_from_buffe_469a:
    rcall       main_core_service_46aa
    rcall       uart_tx_byte_blocking
    incf        stock_01A_acc, F, ACCESS
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
    movf        stock_01A_acc, W, ACCESS
    addwf       stock_018_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      stock_019_acc, W, ACCESS
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
    movff       WREG, stock_007_b0_phys
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    rcall       wait_sen_bounded
    bc          i2c_secondary_timeout
    movlw       0xE2
    call        i2c_byte_tx, 0x0
    movf        stock_007_acc, W, ACCESS
    call        i2c_byte_tx, 0x0
    movf        stock_006_acc, W, ACCESS
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    rcall       wait_pen_bounded
    bc          i2c_secondary_pen_timeout
i2c_secondary_done:
    return      0
i2c_secondary_timeout:
    rcall       i2c_timeout_recover_advertise
    return      0
i2c_secondary_pen_timeout:
    rcall       i2c_pen_timeout_recover_advertise
    return      0


; ---------------------------------------------------------------------------
; Function: main_flash_service_46de
; Address : 0x46DE
; Notes   : Inferred flash helper routine. Calls: eeprom_read_byte, eeprom_write_blocking.
; ---------------------------------------------------------------------------
main_flash_service_46de:
    movff       stock_007_b0_phys, stock_003_b0_phys
    movff       stock_008_b0_phys, stock_004_b0_phys
    rcall       eeprom_read_byte
    xorwf       stock_009_acc, W, ACCESS
    bz          flow_main_flash_service_46de_46fe
    movff       stock_007_b0_phys, stock_003_b0_phys
    movff       stock_008_b0_phys, stock_004_b0_phys
    movff       stock_009_b0_phys, saved_w_b0_phys
    rcall       eeprom_write_blocking
flow_main_flash_service_46de_46fe:
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_4700
; Address : 0x4700
; Notes   : Inferred usb helper; touches usb. Calls: main_usb_service_4828, main_usb_service_40d6.
; ---------------------------------------------------------------------------
main_usb_service_4700:
    decf        usb_reinit_pending_b0, W, BANKED
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
    movwf       stock_0CD_b0, BANKED
    clrf        usb_reinit_pending_b0, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: main_usb_service_4720
; Address : 0x4720
; Notes   : Inferred usb helper; touches timer,usb.
; ---------------------------------------------------------------------------
main_usb_service_4720:
    movff       UIE, stock_092_b0_phys
    movlw       0x04
    movwf       UIE, ACCESS
    bcf         UIR, 4, ACCESS
    bsf         UCON, 1, ACCESS
    bcf         PIR2, 5, ACCESS
    bsf         PIE2, 5, ACCESS
    bcf         PIE2, 5, ACCESS
    movlb       0x0
    movf        stock_092_b0, W, BANKED
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
    clrf        stock_006_acc, ACCESS
    bra         flow_ram_block_clear_4752
flow_ram_block_clear_4742:
    movf        stock_006_acc, W, ACCESS
    addwf       stock_003_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      stock_004_acc, W, ACCESS
    movwf       FSR2H, ACCESS
    clrf        INDF2, ACCESS
    incf        stock_006_acc, F, ACCESS
flow_ram_block_clear_4752:
    movf        stock_005_acc, W, ACCESS
    subwf       stock_006_acc, W, ACCESS
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
    decf        usb_reinit_pending_b0, W, BANKED
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
    clrf        usb_reinit_pending_b0, BANKED
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
    movff       stock_003_b0_phys, preset_hold_timer_lo_b0_phys
    movff       stock_004_b0_phys, preset_hold_timer_hi_b0_phys
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
    btfss       event_flags_b0, 2, BANKED              ; pending stdby/wake event?
    bra         flow_standby_event_dispatch_47ac    ; no -> tail-call gate dispatch
    btfss       active_flags_acc, 3, ACCESS             ; gate currently open?
    bra         flow_standby_event_dispatch_47a6    ;   no -> shutdown path
    diag_inc_sat diag_b                              ; V3.2 Layer 5: count bring-up dispatch
    call        adc_boot_gate, 0x0                  ; gate open -> rail-rise wait
    bra         flow_standby_event_dispatch_47aa
flow_standby_event_dispatch_47a6:
    diag_inc_sat diag_s                              ; V3.2 Layer 5: count standby dispatch
    call        hw_standby_shutdown, 0x0            ; I2C DSP shutdown / OSC switch
flow_standby_event_dispatch_47aa:
    bcf         event_flags_b0, 2, BANKED              ; consume the event
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
    movff       WREG, stock_004_b0_phys
    movlw       0xC0
    andwf       SSPSTAT, F, ACCESS
    clrf        SSPCON1, ACCESS
    clrf        SSPCON2, ACCESS
    bcf         SSPCON1, 7, ACCESS
    bcf         SSPCON1, 6, ACCESS
    bcf         PIR2, 3, ACCESS
    movf        stock_004_acc, W, ACCESS
    iorwf       SSPCON1, F, ACCESS
    movf        stock_003_acc, W, ACCESS
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
    movlb       0x02
    clrf        chain_tx_emitted_b2, BANKED
    movlb       0x00
    call        main_usb_service_3a26, 0x0
    call        main_uart_service_1be6, 0x0
    rcall       main_service_rx_frame_gap           ; V3.2 §2: parser stall watchdog
    rcall       preset_job_service                  ; V3.2: async preset state machine
    call        main_i2c_service_27f0, 0x0
    rcall       standby_event_dispatch
    call        main_core_service_265c, 0x0
    rcall       filename_reply_job_service          ; V3.3: lowest-priority filename burst
    rcall       ra1_edge_monitor                    ; V3.2 Layer 5: diag_p edge counter
    bra         an0_hysteresis_monitor

; ---------------------------------------------------------------------------
; ra1_edge_monitor — V3.2 Layer 5 RA1 edge counter (diag_p)
; ---------------------------------------------------------------------------
; Polled once per periodic_service_loop pass (= main_processing_loop tick,
; tens of µs).  Compares PORTA bit 1 against diag_ra1_prev shadow byte;
; on either edge (0→1 or 1→0) bumps diag_p (saturating at 0x0F).  Tested
; via the simulator by toggling RA1 in the harness; no real-hardware function is
; assigned to RA1 in V3.2, so this is pure observability infrastructure
; per docs/V163B_DIAGNOSTICS_MENU_SPEC.md "RA1-trigger path" section.
; ---------------------------------------------------------------------------
ra1_edge_monitor:
    movff       BSR, stock_00E_b0_phys                  ; save caller BSR
    movlb       0x02                            ; V3.2 Layer 5 diag block in BANK 2
    movf        PORTA, W, ACCESS                ; W = PORTA snapshot
    andlw       0x02                            ; isolate RA1
    xorwf       diag_ra1_prev_b2, W, BANKED        ; W = current ^ prev (bit 1 only)
    btfsc       STATUS, 2, ACCESS               ; if Z (no edge), skip increment
    bra         ra1_no_edge
    ; Edge detected — refresh shadow and bump counter.
    movf        PORTA, W, ACCESS
    andlw       0x02
    movwf       diag_ra1_prev_b2, BANKED
    diag_inc_sat diag_p                          ; macro re-asserts movlb 0x02
ra1_no_edge:
    movff       stock_00E_b0_phys, BSR                  ; restore caller BSR
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
    movlb       0x02
    bsf         chain_tx_emitted_b2, 0, BANKED
    movlb       0x00
    movlw       0xBF
    rcall       uart_tx_byte_blocking
    movlw       0x29
    rcall       uart_tx_byte_blocking
    movlw       0x01
    btfss       active_flags_acc, 1, ACCESS
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
    decf        stock_003_acc, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        stock_004_acc, F, ACCESS
flow_main_usb_service_4812_481e:
    movf        stock_004_acc, W, ACCESS
    iorwf       stock_003_acc, W, ACCESS
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
    setf        stock_004_acc, ACCESS
    setf        stock_003_acc, ACCESS
    rcall       main_usb_service_4812
    movlb       0x0
    clrf        stock_0CD_b0, BANKED
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
    movf        rx_ring_wr_b0, W, BANKED
    xorwf       rx_ring_rd_b0, W, BANKED
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
    movff       stock_003_b0_phys, EEADR
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
;     TRMT clear forever. UART's terminal recovery is deliberately a panic
;     reset; volume_dsp_write now stays in its bounded DSP-fault path.
; ---------------------------------------------------------------------------
uart_tx_byte_blocking:
    movff       WREG, stock_003_b0_phys
    rcall       wait_trmt_bounded
    bc          uart_tx_timeout
    movff       stock_003_b0_phys, TXREG
    movf        stock_003_acc, W, ACCESS
    return      0
uart_tx_timeout:
    rcall       uart_config
    rcall       wait_trmt_bounded
    bc          v31_hard_reset_jump2
    movff       stock_003_b0_phys, TXREG
    movf        stock_003_acc, W, ACCESS
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
; Function: i2c_wait_bus_idle              (bounded MSSP idle wait)
; Address : 0x48B6
; ---------------------------------------------------------------------------
; Spin until the MSSP module reports idle: SSPCON2[4:0] (SEN, RSEN, PEN,
; RCEN, ACKEN) == 0 AND SSPSTAT.R_nW (bit 2) == 0.
;
; V3.2 hang-hardening: timeout routes through the same centralized
; MSSP-recovery and BF/08 advertisement helper used by direct SEN/PEN waits.
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
    movlb       0x2
    btfss       i2c_recover_flags_b2, 0, BANKED
    bra         i2c_wait_bus_idle_seed
    btfsc       SSPCON2, 2, ACCESS
    bra         i2c_wait_bus_idle_seed
    bcf         i2c_recover_flags_b2, 0, BANKED
    rcall       i2c_bus_clear
i2c_wait_bus_idle_seed:
    rcall       wait_seed
i2c_wait_bus_idle_loop:
    movff       SSPCON2, stock_003_b0_phys
    movlw       0x1F
    andwf       stock_003_acc, F, ACCESS                ; mask SEN/RSEN/PEN/RCEN/ACKEN
    btfsc       STATUS, 2, ACCESS                   ; if any of those set, keep spinning
    btfsc       SSPSTAT, 2, ACCESS                  ; AND while R_nW (master in receive)
    bra         i2c_wait_bus_idle_busy
    bcf         STATUS, 0, ACCESS
    retlw       0x1F
i2c_wait_bus_idle_busy:
    rcall       wait_tick
    bnc         i2c_wait_bus_idle_loop
    rcall       i2c_timeout_recover_advertise
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
; reconfigured EUSART cannot drain TRMT (two strikes), and from the
; flash-entry quiet-shutdown terminator after the EEPROM bootloader marker
; is committed and the outputs have been muted/gated down.
;
; V3.2 volume_dsp_write does not enter hard_reset.  Its retry-exhaustion
; path performs bounded bus-clear/ping recovery, raises BF/08 DSP fault
; telemetry, clears the dirty bit, and returns to the foreground loop.
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
    clrf        stock_0CD_b0, BANKED
    movlw       0x01
    movwf       usb_reinit_pending_b0, BANKED
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
    clrf        stock_006_acc, ACCESS               ; (2) drop audio rails via 0x71
    movlw       0x1B
    rcall       i2c_secondary_dev_write
    clrf        stock_006_acc, ACCESS
    movlw       0x1C
    rcall       i2c_secondary_dev_write
    clrf        stock_006_acc, ACCESS
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
    movff       WREG, stock_003_b0_phys
    decf        stock_003_acc, W, ACCESS
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
    clrf        usb_reinit_pending_b0, BANKED
    bra         main_usb_service_475c


; ---------------------------------------------------------------------------
; Function: main_core_service_4924
; Address : 0x4924
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_4924:
    movlw       0x03
    movwf       stock_004_acc, ACCESS
    clrf        stock_003_acc, ACCESS
    bra         flow_main_usb_service_4812_481e


; ---------------------------------------------------------------------------
; Function: main_core_service_492e
; Address : 0x492E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
main_core_service_492e:
    clrf        stock_004_acc, ACCESS
    movlw       0x01
    movwf       stock_003_acc, ACCESS
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
    clrf        stock_004_acc, ACCESS
    movlw       0x02
    movwf       stock_003_acc, ACCESS
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
    movff       computed_volume_b0_phys, logical_volume_b0_phys
    movff       computed_volume_1_b0_phys, logical_volume_1_b0_phys
    movff       computed_volume_2_b0_phys, logical_volume_2_b0_phys
    movff       computed_volume_3_b0_phys, logical_volume_3_b0_phys
    return      0


; ===========================================================================
; V3.1 New Functions (after last stock function, before preset tables)
; ===========================================================================

; ---------------------------------------------------------------------------
; Bounded Wait Helpers (shared 16-bit timeout infrastructure)
; ---------------------------------------------------------------------------
wait_seed:
    clrf        timeout_lo_acc, ACCESS
    movlw       0x10
    movwf       timeout_hi_acc, ACCESS
    bcf         STATUS, 0, ACCESS           ; clear C
    return      0

wait_tick:
    decfsz      timeout_lo_acc, F, ACCESS
    return      0
    decfsz      timeout_hi_acc, F, ACCESS
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

wait_rsen_bounded:
    rcall       wait_seed
wait_rsen_loop:
    btfss       SSPCON2, 1, ACCESS          ; RSEN clear?
    bra         wait_wait_done
    rcall       wait_tick
    bnc         wait_rsen_loop
    return      0

wait_pen_bounded:
    rcall       wait_seed
wait_pen_loop:
    btfss       SSPCON2, 2, ACCESS          ; PEN clear?
    bra         wait_wait_done
    rcall       wait_tick
    bnc         wait_pen_loop
    return      0

wait_acken_bounded:
    rcall       wait_seed
wait_acken_loop:
    btfss       SSPCON2, 4, ACCESS          ; ACKEN clear?
    bra         wait_wait_done
    rcall       wait_tick
    bnc         wait_acken_loop
    return      0

wait_bf_clear_bounded:
    rcall       wait_seed
wait_bf_clear_loop:
    btfss       SSPSTAT, 0, ACCESS          ; BF set?
    bra         wait_wait_done              ; BF=0: buffer empty, done
    rcall       wait_tick
    bnc         wait_bf_clear_loop
    return      0                           ; C=1: timed out

wait_bf_set_bounded:
    rcall       wait_seed
wait_bf_set_loop:
    btfsc       SSPSTAT, 0, ACCESS          ; BF set?
    bra         wait_wait_done
    rcall       wait_tick
    bnc         wait_bf_set_loop
    return      0                           ; C=1: timed out

wait_sspif_bounded:
    rcall       wait_seed
wait_sspif_loop:
    btfsc       PIR1, 3, ACCESS             ; SSPIF set?
    bra         wait_wait_done
    rcall       wait_tick
    bnc         wait_sspif_loop
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
    movwf       timeout_lo_acc, ACCESS
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
    decfsz      timeout_lo_acc, F, ACCESS
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
;@routine dsp_ping entry_bsr=unknown exit_bsr=0
dsp_ping:
    movlb       0x0                          ; assert bank 0 for dsp_fault_flags
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    rcall       wait_sen_bounded
    bc          dsp_ping_nack_reset
    movlw       0x68                        ; TAS3108 write addr
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    rcall       wait_pen_bounded
    bc          dsp_ping_nack_reset
    movlb       0x0
    btfss       SSPCON2, 6, ACCESS          ; ACKSTAT?
    bcf         dsp_fault_flags_b0, 6, BANKED  ; ACK: clear fault
    btfsc       SSPCON2, 6, ACCESS
    bra         dsp_ping_nack
    return      0
dsp_ping_nack_reset:
    movlw       0x80
    movwf       stock_003_acc, ACCESS
    movlw       0x08
    rcall       mssp_hard_reset
    movlb       0x0
dsp_ping_nack:
    bsf         dsp_fault_flags_b0, 6, BANKED  ; NACK: set fault
    return      0

; ---------------------------------------------------------------------------
; Send DSP Fault Status (Fix E) — BF/08 frame to CONTROL
; ---------------------------------------------------------------------------
mark_chain_tx_emitted_bsr0:
    movlb       0x02
    bsf         chain_tx_emitted_b2, 0, BANKED
    movlb       0x00
    return      0

send_dsp_fault_status:
    rcall       mark_chain_tx_emitted_bsr0
    movf        dsp_fault_flags_b0, W, BANKED
    andlw       0x44                        ; bits 6 + 2
    movwf       stock_00D_acc, ACCESS           ; save in ram_0x00D (uart_tx clobbers ram_0x003)
    movlw       0xBF
    rcall       uart_tx_byte_blocking
    movlw       0x08
    rcall       uart_tx_byte_blocking
    movf        stock_00D_acc, W, ACCESS
    bra         uart_tx_byte_blocking

; ---------------------------------------------------------------------------
; Centralized I2C/MSSP timeout recovery + observability.
; ---------------------------------------------------------------------------
; Contract:
;   in : timeout already detected by a bounded wait helper
;   out: C=1, dsp_fault_flags.bit2 set, BF/08 emitted with a non-zero
;        transport/fault payload.  The caller must return to the main loop
;        or retry from a bounded state-machine path.
;   touches: timeout scratch, BSR, W, UART TX.
; ---------------------------------------------------------------------------
i2c_pen_timeout_recover_advertise:
    clrf        stock_00D_acc, ACCESS
    bsf         stock_00D_acc, 0, ACCESS
    bra         i2c_timeout_recover_common

;@routine i2c_timeout_recover_advertise entry_bsr=unknown exit_bsr=0
i2c_timeout_recover_advertise:
    clrf        stock_00D_acc, ACCESS
    btfsc       SSPCON2, 2, ACCESS
    bsf         stock_00D_acc, 0, ACCESS         ; remember PEN-pending timeout
i2c_timeout_recover_common:
    diag_inc_sat diag_i                      ; I: I2C/MSSP transport timeout
    diag_inc_sat diag_r                      ; R: recovery branch entered
    movlb       0x2
    bsf         i2c_recover_flags_b2, 0, BANKED ; next clean I2C entry bus-clears
    movlw       0x80
    movwf       stock_003_acc, ACCESS            ; stock SSPSTAT SMP state
    movlw       0x08                         ; MSSP master mode bits
    rcall       mssp_hard_reset
    btfsc       stock_00D_acc, 0, ACCESS
    bra         i2c_timeout_skip_bus_probe
    rcall       i2c_bus_clear
    rcall       dsp_ping                     ; updates bit6 if DSP still NACKs
i2c_timeout_skip_bus_probe:
    movlb       0x0
    bcf         SSPCON1, 7, ACCESS           ; clear WCOL after aborted tx
    bcf         SSPCON1, 6, ACCESS           ; clear SSPOV after aborted rx
    movlb       0x0
    bsf         dsp_fault_flags_b0, 2, BANKED   ; keep timeout visible after ACK ping
    rcall       send_dsp_fault_status
    bsf         STATUS, 0, ACCESS
    return      0

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
    ; chain_tx_emitted is set by shared diag_send_burst_xx.
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
    movwf       stock_004_acc, ACCESS
    movlw       0x21                        ; first sub-cmd byte
    movwf       i2c_coeff_3_acc, ACCESS
    lfsr        FSR0, diag_i_b2_phys                ; 0x2E5 — first diag counter
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
;   BF/2A = diag_reset_wdt  (W - RCON.TO-cleared bucket; WDT disabled by policy)
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
    ; chain_tx_emitted is set by shared diag_send_burst_xx.
    ; Reuses diag_send_burst_xx (defined immediately below) — exactly
    ; the same wire shape as cmd 0x21 but with a different FSR0 base
    ; (reset-cause flag cells) and different sub-cmd range (0x28..0x2B).
    movlw       0x2C                        ; sentinel: stop AFTER BF/2B sent
    movwf       stock_004_acc, ACCESS
    movlw       0x28                        ; first sub-cmd byte
    movwf       i2c_coeff_3_acc, ACCESS
    lfsr        FSR0, diag_reset_por_b2_phys        ; 0x2ED — first reset-flag cell
    bra         diag_send_burst_xx

; ---------------------------------------------------------------------------
; cmd 0x23 — Link-health ping reply (V1.71/V3.2 freshness MVP)
; ---------------------------------------------------------------------------
; Reached from main_uart_service_1be6 dispatch when CONTROL sends
; [B1/B2, 0x23, 0x00].  Emits exactly one chain-safe reply:
;
;   BF/2C/00
;
; The data byte is intentionally constant for the MVP.  CONTROL owns
; freshness and only needs a complete addressed reply; MAIN-local
; sequence/counter telemetry can be added later if it proves useful.
;
; Like cmd 0x21 / 0x22, suppress the cmd-XOR ACK echo before returning
; through the normal parser tail.
; ---------------------------------------------------------------------------
cmd23_health_query_handler:
    rcall       mark_chain_tx_emitted_bsr0
    movlw       0xBF
    rcall       uart_tx_byte_blocking
    movlw       0x2C
    rcall       uart_tx_byte_blocking
    movlw       0x00
    rcall       uart_tx_byte_blocking
    bcf         active_flags_acc, 6, ACCESS     ; suppress cmd-XOR ACK echo
    goto        flow_main_uart_service_1be6_1e6c

; ---------------------------------------------------------------------------
; cmd 0x25 — MAIN identity reply (V1.73/V3.4 diagnostics title)
; ---------------------------------------------------------------------------
; Reached when CONTROL sends [B1/B2, 0x25, id].  Emits five chain-safe
; frames:
;   BF/4F/id, BF/50/major, BF/51/minor, BF/52/rev_hi, BF/53/rev_lo
; All payload bytes are masked below 0x80; the release revision is split
; into nibbles so future revs above 0x7F cannot look like route bytes.
; ---------------------------------------------------------------------------
cmd25_identity_query_handler:
    rcall       mark_chain_tx_emitted_bsr0
    ; START carries the full 6-bit route-safe query id; the remaining
    ; four payloads are low nibbles and can reuse diag_send_burst_xx.
    movlw       0xBF
    rcall       uart_tx_byte_blocking
    movlw       0x4F
    rcall       uart_tx_byte_blocking
    movf        current_cmd_data_b0, W, BANKED        ; query id
    andlw       0x3F
    rcall       uart_tx_byte_blocking

    movlw       0x03                        ; V3.4 identity major
    movwf       stock_005_acc, ACCESS
    movlw       0x04                        ; V3.4 identity minor
    movwf       stock_006_acc, ACCESS
    movlw       0x08                        ; V3.4_IDENTITY_REV_HI
    movwf       stock_007_acc, ACCESS
    movlw       0x0A                        ; V3.4_IDENTITY_REV_LO
    movwf       stock_008_acc, ACCESS
    movlw       0x54                        ; sentinel: stop AFTER BF/53 sent
    movwf       stock_004_acc, ACCESS
    movlw       0x50                        ; first identity payload sub-cmd
    movwf       i2c_coeff_3_acc, ACCESS
    lfsr        FSR0, saved_w_b0_phys                ; major/minor/rev_hi/rev_lo staging
    bra         diag_send_burst_xx

; ---------------------------------------------------------------------------
; cmd 0x26 — preset filename query (V3.4/V1.73 Preset LCD)
; ---------------------------------------------------------------------------
; Reached when CONTROL sends [B1/B2, 0x26, id].  The id format is
; (generation<<2)|(target_bit<<1)|slot.  V1 display uses PB1, but MAIN just
; echoes the id it receives so the same protocol is PB2-ready.
;
; The handler arms a tiny foreground job and returns through the normal parser
; tail.  filename_reply_job_service later emits one BF frame per main-loop pass
; after all other chain senders had a chance to set chain_tx_emitted.
; ---------------------------------------------------------------------------
cmd26_filename_query_handler:
    movlb       0x02
    movf        filename_rev_b2, W, BANKED
    andlw       0x01
    bnz         cmd26_filename_query_done
    movf        filename_rev_b2, W, BANKED
    movwf       fn_job_rev_b2, BANKED

    movlb       0x00
    movf        current_cmd_data_b0, W, BANKED
    andlw       0x7F
    movlb       0x02
    movwf       fn_job_id_b2, BANKED
    andlw       0x01
    movwf       fn_job_src_kind_b2, BANKED      ; temporary: requested slot
    btfsc       active_flags_acc, 2, ACCESS      ; active preset B?
    xorlw       0x01
    bz          cmd26_filename_source_ram
    movf        fn_job_src_kind_b2, W, BANKED
    bz          cmd26_filename_source_eep_a
    movlw       0x02                         ; requested B while A active
    bra         cmd26_filename_source_set
cmd26_filename_source_eep_a:
    movlw       0x01                         ; requested A while B active
    bra         cmd26_filename_source_set
cmd26_filename_source_ram:
    clrf        fn_job_src_kind_b2, BANKED       ; requested slot == active RAM
    bra         cmd26_filename_len_init
cmd26_filename_source_set:
    movwf       fn_job_src_kind_b2, BANKED

cmd26_filename_len_init:
    clrf        fn_job_len_b2, BANKED
cmd26_filename_len_loop:
    movf        fn_job_len_b2, W, BANKED
    xorlw       preset_filename_len
    bz          cmd26_filename_arm
    movf        fn_job_len_b2, W, BANKED
    rcall       filename_read_source_at_w
    movlb       0x02
    movwf       fn_job_tmp_b2, BANKED
    movlw       0x20
    cpfslt      fn_job_tmp_b2, BANKED
    bra         cmd26_filename_len_high
    bra         cmd26_filename_arm
cmd26_filename_len_high:
    movlw       0x7F
    cpfslt      fn_job_tmp_b2, BANKED
    bra         cmd26_filename_arm
    incf        fn_job_len_b2, F, BANKED
    bra         cmd26_filename_len_loop

cmd26_filename_arm:
    movlw       0x2F                         ; prefix-first default
    movwf       fn_job_start_cmd_b2, BANKED
    movlw       0x11
    cpfslt      fn_job_len_b2, BANKED           ; len < 17?
    bra         cmd26_filename_compare_prefix16
    bra         cmd26_filename_arm_rev_check

cmd26_filename_compare_prefix16:
    movf        fn_job_src_kind_b2, W, BANKED
    movwf       fname_tx_gap_hi_b2, BANKED      ; save requested source kind
    clrf        fn_job_idx_b2, BANKED
cmd26_filename_compare_loop:
    movf        fname_tx_gap_hi_b2, W, BANKED
    movwf       fn_job_src_kind_b2, BANKED
    movf        fn_job_idx_b2, W, BANKED
    rcall       filename_read_source_at_w
    movlb       0x02
    movwf       fname_tx_gap_lo_b2, BANKED      ; requested char
    movf        fname_tx_gap_hi_b2, W, BANKED
    bz          cmd26_filename_compare_other_eep
    clrf        fn_job_src_kind_b2, BANKED       ; requested EEPROM -> other active RAM
    bra         cmd26_filename_compare_read_other
cmd26_filename_compare_other_eep:
    movlw       0x01                         ; active B -> other EEPROM A
    btfss       active_flags_acc, 2, ACCESS
    movlw       0x02                         ; active A -> other EEPROM B
    movwf       fn_job_src_kind_b2, BANKED
cmd26_filename_compare_read_other:
    movf        fn_job_idx_b2, W, BANKED
    rcall       filename_read_source_at_w
    movlb       0x02
    cpfseq      fname_tx_gap_lo_b2, BANKED
    bra         cmd26_filename_compare_done
    incf        fn_job_idx_b2, F, BANKED
    movlw       0x10
    cpfseq      fn_job_idx_b2, BANKED
    bra         cmd26_filename_compare_loop
    movlw       0x2E                         ; first 16 match: rest on tail
    movwf       fn_job_start_cmd_b2, BANKED
cmd26_filename_compare_done:
    movf        fname_tx_gap_hi_b2, W, BANKED
    movwf       fn_job_src_kind_b2, BANKED

cmd26_filename_arm_rev_check:
    movf        filename_rev_b2, W, BANKED
    andlw       0x01
    bnz         cmd26_filename_query_done
    movf        filename_rev_b2, W, BANKED
    cpfseq      fn_job_rev_b2, BANKED
    bra         cmd26_filename_query_done
    clrf        fn_job_idx_b2, BANKED
    clrf        fname_tx_gap_lo_b2, BANKED
    clrf        fname_tx_gap_hi_b2, BANKED
    movlw       0x01
    movwf       fn_job_state_b2, BANKED
cmd26_filename_query_done:
    bcf         active_flags_acc, 6, ACCESS      ; suppress cmd-XOR ACK echo
    goto        flow_main_uart_service_1be6_1e6c

filename_read_source_at_w:
    movwf       fn_job_tmp_b2, BANKED
    movf        fn_job_src_kind_b2, W, BANKED
    bz          filename_read_source_ram
    xorlw       0x01
    bz          filename_read_source_eep_a
    movlw       preset_filename_eeprom_b
    bra         filename_read_source_eep
filename_read_source_eep_a:
    movlw       preset_filename_eeprom_a
filename_read_source_eep:
    addwf       fn_job_tmp_b2, W, BANKED
    movwf       stock_003_acc, ACCESS
    clrf        stock_004_acc, ACCESS
    rcall       eeprom_read_byte
    return      0
filename_read_source_ram:
    lfsr        FSR2, preset_filename_ram_base
    movf        fn_job_tmp_b2, W, BANKED
    addwf       FSR2L, F, ACCESS
    movf        INDF2, W, ACCESS
    return      0

filename_reply_job_service:
    movlb       0x02
    movf        fn_job_state_b2, W, BANKED
    bz          filename_reply_job_ret
    btfss       chain_tx_emitted_b2, 0, BANKED
    bra         filename_reply_check_gap
    clrf        fname_tx_gap_lo_b2, BANKED
    movlw       0x01
    movwf       fname_tx_gap_hi_b2, BANKED
    bra         filename_reply_job_ret
filename_reply_check_gap:
    movf        fname_tx_gap_lo_b2, F, BANKED
    bnz         filename_reply_dec_gap_lo
    movf        fname_tx_gap_hi_b2, F, BANKED
    bz          filename_reply_ready
    decf        fname_tx_gap_hi_b2, F, BANKED
    decf        fname_tx_gap_lo_b2, F, BANKED
    bra         filename_reply_job_ret
filename_reply_dec_gap_lo:
    decf        fname_tx_gap_lo_b2, F, BANKED
    bra         filename_reply_job_ret
filename_reply_ready:
    movf        filename_rev_b2, W, BANKED
    andlw       0x01
    bnz         filename_reply_job_abort
    movf        filename_rev_b2, W, BANKED
    cpfseq      fn_job_rev_b2, BANKED
    bra         filename_reply_job_abort
    movf        fn_job_state_b2, W, BANKED
    xorlw       0x01
    bz          filename_reply_send_start
    xorlw       0x03
    bz          filename_reply_send_len
    xorlw       0x01
    bz          filename_reply_send_char_or_end
    xorlw       0x07
    bz          filename_reply_send_end
filename_reply_job_abort:
    clrf        fn_job_state_b2, BANKED
filename_reply_job_ret:
    return      0

filename_reply_send_start:
    movf        fn_job_start_cmd_b2, W, BANKED
    movwf       stock_00D_acc, ACCESS
    movf        fn_job_id_b2, W, BANKED
    movwf       stock_00E_acc, ACCESS
    rcall       filename_emit_frame
    movlb       0x02
    movlw       0x02
    movwf       fn_job_state_b2, BANKED
    return      0

filename_reply_send_len:
    movlw       0x2D
    movwf       stock_00D_acc, ACCESS
    movf        fn_job_id_b2, W, BANKED
    xorwf       fn_job_len_b2, W, BANKED
    movwf       stock_00E_acc, ACCESS
    rcall       filename_emit_frame
    movlb       0x02
    movlw       0x03
    movwf       fn_job_state_b2, BANKED
    return      0

filename_reply_send_char_or_end:
    movf        fn_job_idx_b2, W, BANKED
    cpfseq      fn_job_len_b2, BANKED
    bra         filename_reply_send_char
    bra         filename_reply_send_end
filename_reply_send_char:
    movf        fn_job_idx_b2, W, BANKED
    rcall       filename_read_source_at_w
    movwf       stock_00E_acc, ACCESS
    movlb       0x02
    movlw       0x30
    addwf       fn_job_idx_b2, W, BANKED
    movwf       stock_00D_acc, ACCESS
    rcall       filename_emit_frame
    movlb       0x02
    incf        fn_job_idx_b2, F, BANKED
    return      0

filename_reply_send_end:
    movlw       0x4E
    movwf       stock_00D_acc, ACCESS
    movf        fn_job_id_b2, W, BANKED
    movwf       stock_00E_acc, ACCESS
    rcall       filename_emit_frame
    movlb       0x02
    clrf        fn_job_state_b2, BANKED
    return      0

filename_emit_frame:
    movlb       0x02
    bsf         chain_tx_emitted_b2, 0, BANKED
    clrf        fname_tx_gap_lo_b2, BANKED
    movlw       0x01
    movwf       fname_tx_gap_hi_b2, BANKED
    movlb       0x00
    movlw       0xBF
    rcall       uart_tx_byte_blocking
    movf        stock_00D_acc, W, ACCESS
    rcall       uart_tx_byte_blocking
    movf        stock_00E_acc, W, ACCESS
    bra         uart_tx_byte_blocking

; ---------------------------------------------------------------------------
; diag_send_burst_xx — shared helper for cmd 0x21/0x22 and cmd 0x25 tail
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
    rcall       mark_chain_tx_emitted_bsr0
    movlw       0xBF
    rcall       uart_tx_byte_blocking
    movf        i2c_coeff_3_acc, W, ACCESS
    rcall       uart_tx_byte_blocking
    movf        POSTINC0, W, ACCESS
    andlw       0x0F                        ; chain-forwarder safe (data < 0x80)
    rcall       uart_tx_byte_blocking
    incf        i2c_coeff_3_acc, F, ACCESS
    movf        stock_004_acc, W, ACCESS
    cpfseq      i2c_coeff_3_acc, ACCESS
    bra         diag_send_burst_xx
    bcf         active_flags_acc, 6, ACCESS     ; suppress cmd-XOR ACK echo
    goto        flow_main_uart_service_1be6_1e6c

; ---------------------------------------------------------------------------
; Volume DSP Write (Fix B + B' + recovery)
; ---------------------------------------------------------------------------
volume_dsp_write:
    movlb       0x0
    bcf         dsp_fault_flags_b0, 2, BANKED  ; clear ACKSTAT latch
    call        i2c_tas3108_coeff_write, 0x0
    movlb       0x0                          ; helper may leave BSR != 0
    btfsc       dsp_fault_flags_b0, 2, BANKED  ; NACKed?
    bra         vol_write_nacked
    ; Success: DSP responded, clear all fault state
    movlb       0x0
    bcf         event_flags_b0, 3, BANKED      ; clear volume dirty
    bsf         event_flags_b0, 7, BANKED      ; boot-complete gate
    rcall       copy_computed_volume_to_logical_volume  ; W02-E07: in range after W01-R01
    movlw       0xC7
    andwf       dsp_fault_flags_b0, F, BANKED  ; clear retry counter, preserve bits 7,6
    btfss       dsp_fault_flags_b0, 6, BANKED  ; only report a real fault-clear transition
    return      0
    bcf         dsp_fault_flags_b0, 6, BANKED  ; clear DSP fault (write worked)
    bra         send_dsp_fault_status
vol_write_nacked:
    movlw       0x08
    addwf       dsp_fault_flags_b0, F, BANKED  ; bump retry [5:3]
    movf        dsp_fault_flags_b0, W, BANKED
    andlw       0x38
    sublw       0x28                        ; 5 retries?
    bc          vol_retry_ok
    ; Exhausted: bus-clear + ping only if bus is idle (PEN not pending).
    ; If PEN stuck from fault model, skip I2C recovery to avoid corruption.
    btfsc       SSPCON2, 2, ACCESS          ; PEN pending?
    bra         vol_exhausted_skip_i2c
    movlb       0x02
    lfsr        FSR0, diag_r_b2_phys                 ; V3.2 Layer 5: count recovery branch entry
    call        diag_inc_sat_fsr0, 0x0
    rcall       i2c_bus_clear
    rcall       dsp_ping
vol_exhausted_skip_i2c:
    movlb       0x0                          ; macro / dsp_ping may leave BSR != 0
    btfsc       dsp_fault_flags_b0, 6, BANKED  ; V3.2 Layer 5: skip diag_d if already SET (no transition)
    bra         vol_diag_d_skip
    movlb       0x02
    lfsr        FSR0, diag_d_b2_phys                 ; executed only on 0→1 transition
    call        diag_inc_sat_fsr0, 0x0
vol_diag_d_skip:
    movlb       0x0                          ; restore BSR for the existing bsf line
    bsf         dsp_fault_flags_b0, 6, BANKED  ; flag DSP fault
    rcall       send_dsp_fault_status
    movlb       0x0
    bcf         event_flags_b0, 3, BANKED
    movlw       0xC7
    andwf       dsp_fault_flags_b0, F, BANKED  ; clear retry, preserve bit6 (DSP fault)
    return      0
vol_retry_ok:
    return      0                           ; dirty bit stays: main loop retries

; ---------------------------------------------------------------------------
; Async Preset APPLY Helpers (V3.2 only)
; Notes   : Keep legacy main_i2c_service_381c contract untouched.
;           Return with C=0 on success, C=1 on bounded START/STOP timeout.
; ---------------------------------------------------------------------------
preset_job_apply_i2c_recover:
    rcall       i2c_timeout_recover_advertise
    return      0

preset_job_apply_i2c_entry:
    ; FIELD-4A: the shared i2c_byte_tx engine latches dsp_fault_flags.2 on
    ; any master-TX NACK.  Clear the latch before the entry and treat a
    ; latched NACK exactly like a bounded timeout: C=1 -> the caller retries
    ; THIS entry (recover/advertise runs in between).  Without this check a
    ; NACKed coefficient write was silently skipped and the job COMMITted /
    ; unmuted a wrong DSP image (2026-06-10 field incident: loud bass on
    ; preset B -- wrong crossover at full volume).
    movlb       0x0
    bcf         dsp_fault_flags_b0, 2, BANKED
    call        preset_table_apply_entry_core, 0x0
    bc          preset_job_apply_i2c_timeout
    movlb       0x0
    btfss       dsp_fault_flags_b0, 2, BANKED
    bra         preset_job_apply_i2c_done
    bsf         STATUS, 0, ACCESS           ; NACKed entry -> C=1, retry it
    bra         preset_job_apply_i2c_timeout
preset_job_apply_i2c_done:
    bcf         STATUS, 0, ACCESS           ; C=0: success / benign no-op
    return      0
preset_job_apply_i2c_timeout:
    bra         preset_job_apply_i2c_recover

; ---------------------------------------------------------------------------
; Preset Select Handler (V3.2 non-blocking — cmd=0x20)
; Parser entry: ALWAYS record the target preset and start/coalesce the async
; preset job.  Actual work is done by preset_job_service from the main loop.
;
; V3.4 BUG-V34V173-5: the handler no longer gates on the USB filename-write
; bit (filename_dirty_flags.bit6).  The old parser-entry gate dropped the
; broadcast without storing the target, so a preset change coinciding with a
; host filename write was lost on this unit until the ~6 s full-sync
; re-broadcast (cross-PB preset/coeff desync).  The deferral the gate wanted
; lives in the layer that owns the hazard: preset_job_pending parks un-muted
; while bit6 is set, and the HOLDING -> APPLY transition keeps its bit6
; backstop immediately before preset_load_filename (the only call that can
; clobber the host's just-written filename RAM).  main_core_service_265c
; clears bit6 after the host's force_persist and the parked job proceeds on
; the next main-loop pass.
; ---------------------------------------------------------------------------
preset_select_handler:
    movlb       0x0
    movf        current_cmd_data_b0, W, BANKED ; data byte: 0=A, 1=B
    andlw       0x01
    movlb       0x2
    movwf       preset_job_target_b2, BANKED   ; store requested preset
    ; If a job is already active, the target update is enough (coalesce)
    movf        preset_job_state_b2, W, BANKED
    bnz         preset_select_handler_done
    ; Compare target with current preset
    movf        preset_job_target_b2, W, BANKED
    btfsc       active_flags_acc, 2, ACCESS     ; current preset B?
    xorlw       0x01                        ; invert for comparison
    bz          preset_select_handler_done  ; no change needed
    ; Start new job
    movlw       0x01                        ; PENDING state
    movwf       preset_job_state_b2, BANKED
    clrf        preset_job_flags_b2, BANKED
    btfsc       active_flags_acc, 4, ACCESS     ; user already muted?
    bsf         preset_job_flags_b2, 1, BANKED ; remember user mute desire
preset_select_handler_done:
    goto        flow_main_uart_service_1be6_1e6c

; --- Persist dirty filename to EEPROM (outgoing preset slot) ---
preset_persist_filename:
    movlb       0x02
    incf        filename_rev_b2, F, BANKED     ; seqlock odd: backing store mutating
    movlb       0x00
    movlw       preset_filename_eeprom_a
    btfsc       active_flags_acc, 2, ACCESS
    movlw       preset_filename_eeprom_b
    movwf       stock_007_acc, ACCESS
    clrf        stock_008_acc, ACCESS
    lfsr        FSR2, preset_filename_ram_base
    movlw       preset_filename_len
    movwf       stock_00A_acc, ACCESS
preset_pf_lp:
    movff       POSTINC2, stock_009_b0_phys
    rcall       main_flash_service_46de
    incf        stock_007_acc, F, ACCESS
    decfsz      stock_00A_acc, F, ACCESS
    bra         preset_pf_lp
    movlb       0x02
    incf        filename_rev_b2, F, BANKED     ; seqlock even: stable again
    movlb       0x00
    bcf         filename_dirty_flags_b0, 5, BANKED
    return      0

; --- Load filename from EEPROM (incoming preset slot) ---
preset_load_filename:
    movlb       0x02
    incf        filename_rev_b2, F, BANKED     ; seqlock odd: RAM slot mutating
    movlb       0x00
    movlw       preset_filename_eeprom_a
    btfsc       active_flags_acc, 2, ACCESS
    movlw       preset_filename_eeprom_b
    movwf       stock_003_acc, ACCESS
    clrf        stock_004_acc, ACCESS
    lfsr        FSR2, preset_filename_ram_base
    movlw       preset_filename_len
    movwf       stock_00A_acc, ACCESS
preset_lf_lp:
    rcall       eeprom_read_byte
    movwf       POSTINC2
    incf        stock_003_acc, F, ACCESS
    decfsz      stock_00A_acc, F, ACCESS
    bra         preset_lf_lp
    movlb       0x02
    incf        filename_rev_b2, F, BANKED     ; seqlock even: stable again
    movlb       0x00
    return      0

; --- Force-mute DSP output ---
preset_force_mute:
    movlb       0x0
    bsf         active_flags_acc, 4, ACCESS
    bsf         active_flags_acc, 5, ACCESS
    bcf         event_flags_b0, 5, BANKED
    goto        clrf_i2c_coeff_0123_and_write   ; tail-call; far-safe after M1 growth

; ---------------------------------------------------------------------------
; Preset Job State Machine (V3.2: async delayed preset switching)
; Called once per main-loop pass from periodic_service_loop.
; States: 0=IDLE, 1=PENDING, 2=HOLDING, 3=APPLY, 4=COMMIT
; ---------------------------------------------------------------------------
preset_job_service:
    movlb       0x2
    movf        preset_job_state_b2, W, BANKED
    bz          preset_job_ret              ; IDLE — nothing to do

    ; Cancel on standby shutdown or reconnect
    btfss       active_flags_acc, 3, ACCESS     ; active flag clear → standby
    bra         preset_job_cancel
    btfsc       active_flags_acc, 7, ACCESS     ; reconnect pending
    bra         preset_job_cancel

    ; Dispatch by state
    movlb       0x2
    movf        preset_job_state_b2, W, BANKED
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
    movlb       0x0
    ; V3.4 BUG-V34V173-5: while a USB cmd 0x03 filename WRITE is in flight
    ; (bit6 set), park un-muted in PENDING.  The target stays recorded and
    ; coalescable; main_core_service_265c clears bit6 after the host's
    ; force_persist and the next pass proceeds (persist/mute/hold/apply).
    ; Parking before the bit5 persist also defers that persist to
    ; main_core_service_265c, its canonical owner.
    btfsc       filename_dirty_flags_b0, 6, BANKED
    return      0
    ; Persist dirty filename for outgoing preset
    btfsc       filename_dirty_flags_b0, 5, BANKED
    rcall       preset_persist_filename

    ; Force mute if user is not already muted
    movlb       0x2
    btfsc       active_flags_acc, 4, ACCESS     ; already muted?
    bra         preset_job_pending_no_mute
    bsf         preset_job_flags_b2, 0, BANKED ; flag: we forced mute
    rcall       preset_force_mute
    bra         preset_job_pending_timer

preset_job_pending_no_mute:
    bcf         preset_job_flags_b2, 0, BANKED ; we did not force mute

preset_job_pending_timer:
    ; Start ISR-based Timer3 countdown (150 ticks, ~150 ms)
    ; The Timer3 ISR decrements ram_0x08C:08D on each overflow;
    ; HOLDING polls that pair for zero.
    clrf        stock_004_acc, ACCESS
    movlw       0x96                        ; 150 decimal
    movwf       stock_003_acc, ACCESS
    rcall       main_timer_service_477a

    ; Advance to HOLDING
    movlb       0x2
    movlw       0x02
    movwf       preset_job_state_b2, BANKED
    return      0

; --- HOLDING (2): non-blocking timer countdown, coalescing window ---
preset_job_holding:
    ; Check if the ISR-driven Timer3 countdown has reached zero
    movlb       0x0
    movf        preset_hold_timer_hi_b0, W, BANKED
    iorwf       preset_hold_timer_lo_b0, W, BANKED
    bnz         preset_job_holding_wait     ; still counting

    ; V3.2 USB-xact gate (codex MEDIUM vs entry-only gate at
    ; preset_select_handler): if a USB cmd 0x03 fired DURING this
    ; HOLDING window, bit6 is set and the host's RAM at
    ; preset_filename_ram_base has new data not yet persisted.
    ; Toggling active_flags.bit2 here would call preset_load_filename
    ; and CLOBBER that RAM with the incoming preset's stored
    ; filename.  Defer the toggle until force_persist clears bit6.
    ; (BSR is 0 from the earlier movlb above, so the BANKED check
    ; targets ram_0x0BD bit6 directly without an extra movlb.)
    btfsc       filename_dirty_flags_b0, 6, BANKED
    return      0

    ; After coalescing, check if target still differs from current
    movlb       0x2
    movf        preset_job_target_b2, W, BANKED
    btfsc       active_flags_acc, 2, ACCESS     ; current preset B?
    xorlw       0x01
    bz          preset_job_cancel_unmute    ; coalesced back → cancel

    ; Toggle preset bit
    btg         active_flags_acc, 2, ACCESS
    ; Load incoming preset filename from EEPROM
    ; filename_rev is bumped inside preset_load_filename so any active
    ; cmd 0x26 filename burst aborts rather than finalizing mixed data.
    bcf         INTCON, 7, ACCESS
    rcall       preset_load_filename
    bsf         INTCON, 7, ACCESS
    ; Set cmd03 dirty flag for I2C parameter refresh
    movlb       0x0
    bsf         event_flags_b0, 0, BANKED

    ; Initialize table-apply state
    ; Always seed the STOCK-aligned logical preset window at 0x5600.
    ; flash_read remaps that window to 0x4C00..0x55FF automatically when
    ; active_flags.bit2 says preset B is now active, so callers never seed
    ; a physical 0x4Cxx base directly.
    movlb       0x2
    clrf        preset_job_index_b2, BANKED
    clrf        preset_job_tbl_lo_b2, BANKED
    movlw       0x56
    movwf       preset_job_tbl_hi_b2, BANKED

    ; Advance to APPLY
    movlw       0x03
    movwf       preset_job_state_b2, BANKED
    return      0

preset_job_holding_wait:
    return      0

; --- APPLY (3): one I2C preset-table entry per main-loop pass ---
preset_job_apply:
    ; filename_rev is not modified here; the preset flip path bumps it in
    ; preset_load_filename before APPLY starts.
    movlb       0x2
    movlw       0x60                        ; 96 regular entries
    cpfslt      preset_job_index_b2, BANKED    ; skip if index < 96
    bra         preset_job_apply_final      ; index >= 96 → final entry

    ; Apply regular entry from tracked address
    movff       preset_job_tbl_lo_b2_phys, stock_013_b0_phys
    movff       preset_job_tbl_hi_b2_phys, stock_014_b0_phys
    rcall       preset_job_apply_i2c_entry
    bc          preset_job_apply_retry      ; timeout: retry same entry next pass

    ; Advance address by 0x18 and increment index
    movlb       0x2
    movlw       0x18
    addwf       preset_job_tbl_lo_b2, F, BANKED
    movlw       0x00
    addwfc      preset_job_tbl_hi_b2, F, BANKED
    incf        preset_job_index_b2, F, BANKED
    return      0

preset_job_apply_retry:
    movlb       0x2
    return      0

preset_job_apply_final:
    ; Final logical entry at 0x5F00 (flash_read remaps to 0x5500 for preset B).
    clrf        stock_013_acc, ACCESS
    movlw       0x5F
    movwf       stock_014_acc, ACCESS
    rcall       preset_job_apply_i2c_entry
    bc          preset_job_apply_retry      ; timeout: stay in APPLY, keep final entry pending

    ; V3.4 forensic T: async table walk completed (advancing to COMMIT).
    movlw       0x03                        ; index 3 = T
    call        diag_src_inc_w, 0x0

    ; Advance to COMMIT
    movlb       0x2
    movlw       0x04
    movwf       preset_job_state_b2, BANKED
    return      0

; --- COMMIT (4): finalize preset switch, restore volume if appropriate ---
preset_job_commit:
    movlb       0x2
    ; If CONTROL changed target during APPLY, keep the forced-mute context
    ; and immediately run another coalesced switch instead of going idle on
    ; the older target.
    movf        preset_job_target_b2, W, BANKED
    btfsc       active_flags_acc, 2, ACCESS     ; current preset B?
    xorlw       0x01
    bnz         preset_job_commit_rearm
    btfss       preset_job_flags_b2, 0, BANKED ; did we force mute?
    bra         preset_job_commit_idle      ; no → leave mute as user had it
    btfsc       preset_job_flags_b2, 1, BANKED ; user wants mute?
    bra         preset_job_commit_idle      ; yes → stay muted
    ; Unmute and schedule volume restore
    bcf         active_flags_acc, 4, ACCESS
    bcf         active_flags_acc, 5, ACCESS
    movlb       0x0
    bsf         event_flags_b0, 3, BANKED      ; restore volume on next pass

preset_job_commit_idle:
    bra         preset_job_cancel_done      ; shared tail: state=IDLE+return

preset_job_commit_rearm:
    bra         preset_job_pending_timer

; --- Cancel with unmute (coalesced back to same preset) ---
preset_job_cancel_unmute:
    bcf         T3CON, 0, ACCESS            ; stop Timer3
    bcf         PIE2, 1, ACCESS             ; disable Timer3 interrupt
    bcf         PIR2, 1, ACCESS             ; clear TMR3IF
    movlb       0x2
    btfss       preset_job_flags_b2, 0, BANKED ; did we force mute?
    bra         preset_job_cancel_done
    btfsc       preset_job_flags_b2, 1, BANKED ; user wants mute?
    bra         preset_job_cancel_done
    bcf         active_flags_acc, 4, ACCESS
    bcf         active_flags_acc, 5, ACCESS
    movlb       0x0
    bsf         event_flags_b0, 3, BANKED      ; restore volume
    bra         preset_job_cancel_done

; --- Cancel (standby/reconnect): clear state, don't touch mute ---
preset_job_cancel:
    bcf         T3CON, 0, ACCESS            ; stop Timer3
    bcf         PIE2, 1, ACCESS             ; disable Timer3 interrupt
    bcf         PIR2, 1, ACCESS             ; clear TMR3IF
    ; Clear forced-mute flags so reconnect/standby path is not confused
    movlb       0x2
    btfss       preset_job_flags_b2, 0, BANKED ; did we force mute?
    bra         preset_job_cancel_done
    bcf         active_flags_acc, 5, ACCESS     ; clear forced-mute shadow
    btfsc       preset_job_flags_b2, 1, BANKED ; user wanted mute?
    bra         preset_job_cancel_done      ; yes → leave bit4
    bcf         active_flags_acc, 4, ACCESS     ; clear our force-mute in bit4

preset_job_cancel_done:
    movlb       0x2
    clrf        preset_job_state_b2, BANKED
    return      0

; ---------------------------------------------------------------------------
; HID Diagnostic Memory Read (cmd=0x43)
; Request : ram_0x11B=region (0=flash,1=eeprom), 0x11C/0x11D=addr, 0x11E=len
; Response: 0x15A=cmd, 0x15B=status, 0x15C=len, 0x15D..=data (max 61 bytes)
; ---------------------------------------------------------------------------
hid_cmd_diag_memread:
    movlb       0x1
    lfsr        FSR2, stock_15A_b1_phys
    movlw       0x43
    movwf       POSTINC2, ACCESS
    clrf        POSTINC2, ACCESS
    movf        stock_11E_b1, W, BANKED
    movwf       POSTINC2, ACCESS
    bz          hid_cmd_diag_memread_bad_len
    movlw       0x3D
    cpfsgt      stock_11E_b1, BANKED
    bra         hid_cmd_diag_memread_len_ok
hid_cmd_diag_memread_bad_len:
    movlw       0x02
    bra         hid_cmd_diag_memread_fail
hid_cmd_diag_memread_len_ok:
    movf        stock_11B_b1, W, BANKED
    bz          hid_cmd_diag_memread_flash
    xorlw       0x01
    bz          hid_cmd_diag_memread_eeprom
    movlw       0x01
    bra         hid_cmd_diag_memread_fail
hid_cmd_diag_memread_flash:
    movff       stock_11C_b1_phys, stock_003_b0_phys
    movff       stock_11D_b1_phys, stock_004_b0_phys
    clrf        stock_005_acc, ACCESS
    clrf        stock_006_acc, ACCESS
    movff       stock_11E_b1_phys, stock_007_b0_phys
    clrf        stock_008_acc, ACCESS
    movlw       0x5D
    movwf       stock_009_acc, ACCESS
    movlw       0x01
    movwf       stock_00A_acc, ACCESS
    call        flash_read, 0x0
    goto        flow_hid_command_dispatch_15aa
hid_cmd_diag_memread_eeprom:
    movf        stock_11C_b1, W, BANKED
    movwf       stock_003_acc, ACCESS
    clrf        stock_004_acc, ACCESS
    movf        stock_11E_b1, W, BANKED
    movwf       stock_00A_acc, ACCESS
    lfsr        FSR2, stock_15D_b1_phys
hid_cmd_diag_memread_eeprom_lp:
    rcall       eeprom_read_byte
    movwf       POSTINC2, ACCESS
    incf        stock_003_acc, F, ACCESS
    decfsz      stock_00A_acc, F, ACCESS
    bra         hid_cmd_diag_memread_eeprom_lp
    goto        flow_hid_command_dispatch_15aa
hid_cmd_diag_memread_fail:
    movwf       stock_15B_b1, BANKED
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
    lfsr        FSR2, stock_15A_b1_phys                ; HID IN buffer base
    movlw       0x44                        ; [0] cmd echo
    movwf       POSTINC2, ACCESS
    clrf        POSTINC2, ACCESS            ; [1] status = OK
    movlw       0x10                        ; [2] payload length = 16 cells
                                            ; (V3.4 SRC/DSP forensic ext)
    movwf       POSTINC2, ACCESS
    ; [3..9] = 7 runtime counters from diag_i..diag_p (0x2E5..0x2EB).
    ; FSR0 walks the diag block; FSR2 walks the HID IN buffer.
    lfsr        FSR0, diag_i_b2_phys                ; 0x2E5
    movlw       0x07
    movwf       i2c_coeff_3_acc, ACCESS
hid_diag_snap_cnt:
    movf        POSTINC0, W, ACCESS
    movwf       POSTINC2, ACCESS
    decfsz      i2c_coeff_3_acc, F, ACCESS
    bra         hid_diag_snap_cnt
    ; FSR0 now sits on diag_ra1_prev (0x2EC); skip past it to the
    ; reset-cause flag block at 0x2ED.
    incf        FSR0L, F, ACCESS
    ; [10..13] = 4 reset-cause flags from diag_reset_por..diag_reset_sw.
    movlw       0x04
    movwf       i2c_coeff_3_acc, ACCESS
hid_diag_snap_flag:
    movf        POSTINC0, W, ACCESS
    movwf       POSTINC2, ACCESS
    decfsz      i2c_coeff_3_acc, F, ACCESS
    bra         hid_diag_snap_flag
    ; [14..18] = 5 V3.4 SRC/DSP forensic counters (N L C T M) from
    ; diag_src_n..diag_src_m (0x3C0..0x3C4, BANK 3 upper) — appended
    ; AFTER the reset flags so the legacy 11-cell offsets stay stable
    ; for older hosts.
    lfsr        FSR0, diag_src_n
    movlw       0x05
    movwf       i2c_coeff_3_acc, ACCESS
hid_diag_snap_src:
    movf        POSTINC0, W, ACCESS
    movwf       POSTINC2, ACCESS
    decfsz      i2c_coeff_3_acc, F, ACCESS
    bra         hid_diag_snap_src
    ; [19..63] = padding — host sees length byte at [2]=0x10 so it
    ; stops parsing at offset 18.  Firmware version metadata is
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
; EEPROM Data (V3.4: version updated at offset 0x82)
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
    db  0x03, 0x04, 0x8A, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; V3.4 lineage: V3.2 diagnostics plus cmd 0x25 MAIN identity reply; third byte is the monotonic release revision
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x02  ; ................

    END
