; ===========================================================================
;                    Hypex DLCP — MAIN firmware V3.5
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
;                     (V3.5: V3.2 Tier-1 diagnostics + V3.3/V3.4
;                      app-resident identity and preset filename protocol)
;
; Build      : gpasm -p18f2455 -o DLCP_Firmware_V3.5.hex dlcp_main_v35.asm
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
; * V3.5   THIS FILE — V3.4 refactoring branch with explicit runtime
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
; Top-level service architecture (main loop = run_main_foreground_loop @ 0x48C6)
; ---------------------------------------------------------------------------
;   run_main_service_pass:
;     1. usb_hid_dispatch_out_report_if_ready   — USB SIE / HID OUT processing
;     2. uart_link_parser_drain_rx_and_forward  — RX ring drain + 3-byte parser + forward
;     3. advance_preset_job_state_machine      — V3.2 async preset state machine (NEW)
;     4. poll_src4382_route_monitor   — DSP refresh / dirty bit drain
;     5. standby_event_dispatch  — react to event_flags.bit2 (stdby/wake)
;     6. persist_dirty_runtime_state_to_eeprom  — assorted housekeeping
;     7. an0_hysteresis_monitor  — rail-rise / rail-fall classification
;
; All paths are non-blocking by V3.2 convention except the legacy
; preset_table_apply_entry_legacy_blocking sites that V3.2 hardening has not yet boundified.
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
;   M9  adc_boot_gate_no_timeout      — run_wake_rail_gate_and_dsp_cold_init (waits AN0 ≥ 0x0236)
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
; RXCKR (0x13) is only a recovered-clock rate classifier; selected-route
; teardown requires sustained RXCKR=0 plus formal DIR/PLL unlock (0x14 bit2).
src4382_loss_debounce   EQU  0x2F3
SRC4382_REG_RX_STATUS   EQU  0x13
SRC4382_REG_RX_LOCK     EQU  0x14
SRC4382_UNLOCK_MASK     EQU  0x04
SRC4382_HARD_LOSS_CONFIRM_SAMPLES EQU 0x14

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
; stock_094.bit5 is the V3.4 user-mute latch. stock_094.bit6 is the compact
; FIELD-10 barrier_pending state and stock_094.bit7 is the per-dispatch
; bit1-attempt marker; event_flags.bit1 is the late_bit1_pending retry token
; after that barrier clears. active_flags.bit5 is the existing automatic mute
; owner and carries FIELD-10 fault_mute_owned while bit4 keeps the effective
; mute target asserted.
preset_hold_timer_lo     EQU  0x08C   ; Timer3 ISR countdown low byte used by HOLDING
preset_hold_timer_hi     EQU  0x08D   ; Timer3 ISR countdown high byte used by HOLDING

; ---------------------------------------------------------------------------
; V3.2 preset job state machine — placed in BSR=2 immediately after the
; filename staging buffer at 0x2C0..0x2DD. 7 bytes total.
; The state machine is advanced ONCE per main-loop pass from
; run_main_service_pass, so each transition is observable in well under the
; UART byte time and command latency stays bounded.
; ---------------------------------------------------------------------------
preset_job_state        EQU  0x2DE   ; 0=IDLE,1=PENDING,2=HOLDING,3=APPLY,4=COMMIT
preset_job_target       EQU  0x2DF   ; requested preset (0=A, 1=B). May be re-armed
                                     ; mid-job to coalesce rapid CONTROL F1/F2 toggles.
preset_job_index        EQU  0x2E0   ; APPLY: table entry counter, 0..0x60.
                                     ; index 0x60 is the final row at the job-owned
                                     ; physical cursor (A=0x5F00, B=0x5500).
preset_job_delay        EQU  0x2E1   ; HOLDING: ms remaining (reserved — ISR path uses
                                     ; preset_hold_timer_lo/hi Timer3 countdown instead).
preset_job_flags        EQU  0x2E2   ; bit0=we_force_muted (preset_force_mute did the mute),
                                     ; bit1=user_mute_desired (latched user intent during job).
                                     ; Drives whether COMMIT/CANCEL restores volume or stays muted.
preset_job_tbl_lo       EQU  0x2E3   ; APPLY: job-owned physical TBLPTR cursor:
preset_job_tbl_hi       EQU  0x2E4   ; A starts at 0x5600/final 0x5F00; B starts at
                                     ; 0x4C00/final 0x5500. Pre-incremented by 0x18 per entry.


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
; forced to 0 by the shared diag_low_nibble_reply_burst mask) stays inside the
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
; layered: the diag_low_nibble_reply_burst helper masks the wire byte with
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
; that occupies words 0x1008..0x1012. app_entry__jump_to_cold_init then jumps to the
; cold-init path (boot_cold_init__clear_ram_and_runtime_state).
; ---------------------------------------------------------------------------
    org 0x1000
    bra         app_entry__jump_to_cold_init                 ; 0x1000 user reset trampoline
    dw          0xFFFF
    dw          0xFFFF
    movff       FSR2L, isr_save_fsr2l_b0_phys               ; 0x1008 ISR shadow vector entry
    movff       FSR2H, isr_save_fsr2h_b0_phys
    call        isr_high_priority_dispatch, 0x1              ; FAST=1: shadow STATUS/W/BSR
app_entry__jump_to_cold_init:
    goto        boot_cold_init__clear_ram_and_runtime_state   ; cold init / boot

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
; XOR cmp 0x42 ('B'): branch to the legacy XOR-trampoline (hid_command_dispatch__decode_opcode_xor_chain);
; otherwise fall through to the per-opcode XOR chain. Opcodes covered include
; configuration upload (0x09/0x0A), preset bake helpers (0x06/0x07), HID-driven
; firmware-update entry (the fw_update_relay path), and the V3.1 diagnostic
; flash/EEPROM memread (0x43, see hid_diag_memread_dispatch). Each handler ends by
; jumping into hid_command_dispatch__clear_opcode_and_return to commit the response and
; signal completion to the SIE.
; ---------------------------------------------------------------------------
hid_command_dispatch:
    movwf       i2c_coeff_2_acc, ACCESS
    lfsr        FSR2, usb_ep0_setup_packet_base_phys
    lfsr        FSR1, hid_out_coeff_scratch_byte0_b0_phys
    movlw       0x07
    call        copy_w_bytes_fsr2_to_fsr1, 0x0
    movf        i2c_coeff_2_acc, W, ACCESS
    xorlw       0x42
    bnz         hid_command_dispatch__clear_relay_session_before_decode
    bra         hid_command_dispatch__decode_opcode_xor_chain
hid_command_dispatch__clear_relay_session_before_decode:
    movlb       0x0
    clrf        fw_update_relay_session_active_b0, BANKED
    bra         hid_command_dispatch__decode_opcode_xor_chain
hid_command_dispatch__handle_opcode_03:
    movff       usb_hid_out_arg0_phys, hid_opcode03_subcommand_phys
    movlb       0x0
    movf        hid_opcode03_subcommand_b0, W, BANKED
    xorlw       0x09
    bnz         hid_command_dispatch__probe_config_clear_subcommand
    movlw       0x02
    movwf       i2c_coeff_3_acc, ACCESS
hid_command_dispatch__copy_sparse_config_byte_loop:
    rcall       hid_out_payload_index_to_fsr2
    movf        INDF2, W, ACCESS
    bz          hid_command_dispatch__fill_sparse_config_byte_ff
    rcall       hid_out_payload_index_to_fsr2
    movlw       0xBE
    addwf       i2c_coeff_3_acc, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x02
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         hid_command_dispatch__advance_sparse_config_index
hid_command_dispatch__fill_sparse_config_byte_ff:
    rcall       hid_config_fill_ff_at_index
hid_command_dispatch__advance_sparse_config_index:
    incf        i2c_coeff_3_acc, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3_acc, ACCESS
    bra         hid_command_dispatch__copy_sparse_config_byte_loop
hid_command_dispatch__probe_config_clear_subcommand:
    xorlw       0x03
    bnz         hid_command_dispatch__stage_opcode03_status
    movlw       0x02
    movwf       i2c_coeff_3_acc, ACCESS
hid_command_dispatch__fill_config_range_ff:
    rcall       hid_config_fill_ff_at_index
    incf        i2c_coeff_3_acc, F, ACCESS
    movlw       0x1F
    cpfsgt      i2c_coeff_3_acc, ACCESS
    bra         hid_command_dispatch__fill_config_range_ff
hid_command_dispatch__stage_opcode03_status:
    movlw       0x03
    movlb       0x0
    movwf       usb_hid_ep1_in_report_selector_b0, BANKED
    movff       usb_hid_out_arg0_phys, usb_hid_ep1_in_report_selector_arg_phys
    movf        hid_opcode03_subcommand_b0, W, BANKED
    xorlw       0x09
    bz          hid_command_dispatch__mark_filename_ram_dirty
    xorlw       0x03
    bnz         hid_command_dispatch__arm_timer0_after_update
hid_command_dispatch__mark_filename_ram_dirty:
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
hid_command_dispatch__arm_timer0_after_update:
    rcall       timer0_rearm_50ms_low_window_trampoline
hid_command_dispatch__delay_before_status_response:
    call        timer3_blocking_delay_1ms, 0x0
hid_command_dispatch__emit_status_response:
    call        stage_hid_ep1_in_report_from_selector, 0x0
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__handle_opcode_04:
    movlb       0x1
    decf        usb_hid_out_arg0_b1, W, BANKED
    bnz         hid_command_dispatch__probe_opcode04_payload_mode
    movff       usb_hid_out_arg1_phys, hid_opcode04_action_phys
    bra         hid_command_dispatch__dispatch_opcode04_action
hid_stage_opcode04_status_one:
    movlw       0x04
    movwf       usb_hid_ep1_in_report_selector_b0, BANKED
    movlw       0x01
    movwf       usb_hid_ep1_in_report_selector_arg_b0, BANKED
    return      0
hid_command_dispatch__opcode04_ack_action_one:
    rcall       hid_stage_opcode04_status_one
    bra         hid_command_dispatch__delay_before_status_response
hid_command_dispatch__opcode04_stage_fault_action:
    movff       usb_hid_out_arg2_phys, hid_opcode04_arg2_or_cmd1d_setup_phys
    rcall       hid_stage_opcode04_status_one
    bsf         dsp_fault_flags_b0, 0, BANKED
    bsf         main_runtime_latch_flags_b0, 4, BANKED
    bra         hid_command_dispatch__delay_before_status_response
hid_command_dispatch__dispatch_opcode04_action:
    movlb       0x0
    movf        hid_opcode04_action_b0, W, BANKED
    xorlw       0x01
    bz          hid_command_dispatch__opcode04_ack_action_one
    xorlw       0x03
    bz          hid_command_dispatch__opcode04_stage_fault_action
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__probe_opcode04_payload_mode:
    movf        usb_hid_out_arg0_b1, W, BANKED
    xorlw       0x02
    bz          hid_command_dispatch__handle_opcode04_payload_mode
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__handle_opcode04_payload_mode:
    movff       usb_hid_out_arg3_phys, hid_opcode04_payload_mode_phys
    movlw       0x04
    movlb       0x0
    movwf       usb_hid_ep1_in_report_selector_b0, BANKED
    movlw       0x02
    movwf       usb_hid_ep1_in_report_selector_arg_b0, BANKED
    movf        hid_opcode04_payload_mode_b0, W, BANKED
    xorlw       0x06
    bnz         hid_command_dispatch__check_opcode04_quick_status_modes
    movlw       0x05
    movwf       i2c_coeff_3_acc, ACCESS
hid_command_dispatch__copy_opcode04_payload_loop:
    rcall       hid_out_payload_index_to_fsr2
    movf        INDF2, W, ACCESS
    bz          hid_command_dispatch__fill_opcode04_payload_byte_ff
    rcall       hid_out_payload_index_to_fsr2
    movlw       0xFB
    addwf       i2c_coeff_3_acc, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x00
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    bra         hid_command_dispatch__advance_opcode04_payload_index
hid_command_dispatch__fill_opcode04_payload_byte_ff:
    movlw       0xFB
    addwf       i2c_coeff_3_acc, W, ACCESS
    rcall       setup_fsr2_page1_from_w
    setf        INDF2, ACCESS
hid_command_dispatch__advance_opcode04_payload_index:
    incf        i2c_coeff_3_acc, F, ACCESS
    movlw       0x13
    cpfsgt      i2c_coeff_3_acc, ACCESS
    bra         hid_command_dispatch__copy_opcode04_payload_loop
    movlb       0x0
    bsf         filename_dirty_flags_b0, 4, BANKED
    bra         hid_command_dispatch__arm_timer0_after_update
hid_command_dispatch__check_opcode04_quick_status_modes:
    movf        hid_opcode04_payload_mode_b0, W, BANKED
    andlw       0xFD
    xorlw       0x05
    bz          hid_command_dispatch__delay_before_status_response
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__apply_settings_payload:
    rcall       chain_copy_call_range_trampoline_low ; size T149: HID settings input+volume staging
    db          0x01, 0x00, 0x1B, input_select_b0_op, 0x01, 0x1F, computed_volume_3_b0_op, 0x04, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movlb       0x0
    bcf         main_runtime_latch_flags_b0, 5, BANKED
    bcf         active_flags_acc, 4, ACCESS
    lfsr        FSR2, usb_hid_out_arg8_phys
    btfss       INDF2, 0, ACCESS
    bra         hid_command_dispatch__stage_settings_flag_bits
    bsf         main_runtime_latch_flags_b0, 5, BANKED
    bsf         active_flags_acc, 4, ACCESS
hid_command_dispatch__stage_settings_flag_bits:
    movf        channel_enable_mask_b0, W, BANKED
    andlw       0xC0
    movwf       channel_enable_mask_b0, BANKED
    lfsr        FSR2, usb_hid_out_arg9_phys
    btfsc       INDF2, 0, ACCESS
    bsf         channel_enable_mask_b0, 0, BANKED
    incf        FSR2L, F, ACCESS
    btfsc       INDF2, 0, ACCESS
    bsf         channel_enable_mask_b0, 1, BANKED
    incf        FSR2L, F, ACCESS
    btfsc       INDF2, 0, ACCESS
    bsf         channel_enable_mask_b0, 2, BANKED
    incf        FSR2L, F, ACCESS
    incf        FSR2L, F, ACCESS
    btfsc       INDF2, 0, ACCESS
    bsf         channel_enable_mask_b0, 3, BANKED
    incf        FSR2L, F, ACCESS
    btfsc       INDF2, 0, ACCESS
    bsf         channel_enable_mask_b0, 4, BANKED
    incf        FSR2L, F, ACCESS
    btfsc       INDF2, 0, ACCESS
    bsf         channel_enable_mask_b0, 5, BANKED
hid_command_dispatch__compare_settings_mirrors:
    rcall       chain_copy_call_range_trampoline_low ; size T122: local trampoline keeps descriptor TOS shape
    db          0x01, 0x00, 0x2C, channel_1_source_config_op, 0x06, 0x32, src_route_status_code_acc_op, 0x01, 0x33, route_0_volume_trim_op, 0x04, 0x38, setup_profile_setting_op, 0x01, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movf        input_select_mirror_b0, W, BANKED
    xorwf       input_select_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         main_runtime_latch_flags_b0, 0, BANKED
    rcall       volume_logical_diff_z
hid_command_dispatch__mark_volume_dirty_if_changed:
    bz          hid_command_dispatch__check_route_trim_dirty
    bsf         event_flags_b0, 3, BANKED
    bsf         main_runtime_latch_flags_b0, 1, BANKED
hid_command_dispatch__check_route_trim_dirty:
    lfsr        FSR0, route_0_volume_trim_shadow_phys
    lfsr        FSR1, route_0_volume_trim_phys
    movlw       0x04
    rcall       compare_fsr0_fsr1_bytes_z
    btfsc       STATUS, 2, ACCESS
    bra         hid_command_dispatch__check_mute_state_dirty
    bsf         event_flags_b0, 3, BANKED
    bsf         filename_dirty_flags_b0, 3, BANKED
hid_command_dispatch__check_mute_state_dirty:
    clrf        diff_count_update_compare_or_route_mask_scratch_byte, ACCESS
    btfsc       active_flags_acc, 4, ACCESS
    incf        diff_count_update_compare_or_route_mask_scratch_byte, F, ACCESS
    btfsc       active_flags_acc, 5, ACCESS
    btg         diff_count_update_compare_or_route_mask_scratch_byte, 0, ACCESS
    movf        diff_count_update_compare_or_route_mask_scratch_byte, F, ACCESS
    bz          hid_command_dispatch__check_channel_setup_dirty
    bsf         event_flags_b0, 5, BANKED
    bsf         main_runtime_latch_flags_b0, 3, BANKED
hid_command_dispatch__check_channel_setup_dirty:
    movf        channel_enable_shadow_b0, W, BANKED
    xorwf       channel_enable_mask_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         event_flags_b0, 6, BANKED
    movf        setup_profile_setting_b0, W, BANKED
    xorwf       setup_profile_shadow_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         dsp_fault_flags_b0, 1, BANKED
    lfsr        FSR0, channel_1_source_config_phys
    lfsr        FSR1, channel_1_source_config_shadow_phys
    movlw       0x06
    rcall       compare_fsr0_fsr1_bytes_z
    btfss       STATUS, 2, ACCESS
hid_command_dispatch__mark_channel_source_dirty:
    bsf         event_flags_b0, 4, BANKED
    movff       input_select_b0_phys, input_select_mirror_b0_phys
    call        copy_computed_volume_to_logical_volume, 0x0
    btfss       active_flags_acc, 4, ACCESS
    bra         hid_command_dispatch__clear_mute_shadow
    bsf         active_flags_acc, 5, ACCESS
    bra         hid_command_dispatch__snapshot_settings_mirrors
hid_command_dispatch__clear_mute_shadow:
    bcf         active_flags_acc, 5, ACCESS
hid_command_dispatch__snapshot_settings_mirrors:
    rcall       chain_copy_call_range_trampoline_low ; size T122: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, channel_enable_mask_op, channel_enable_shadow_op, 0x01, channel_1_source_config_op, channel_1_source_config_shadow_op, 0x06, setup_profile_setting_op, setup_profile_shadow_op, 0x01, route_0_volume_trim_op, route_0_volume_trim_shadow_op, 0x04, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
hid_command_dispatch__stage_status_05:
    movlw       0x05
    bra         hid_command_dispatch__emit_selected_status
hid_command_dispatch__handle_opcode_06:
    movlb       0x1
    decf        usb_hid_out_arg0_b1, W, BANKED
    bnz         hid_command_dispatch__probe_opcode06_alt_status
    call        timer3_blocking_delay_2ms, 0x0
    movlw       0x06
hid_command_dispatch__emit_selected_status:
    movlb       0x0
    movwf       usb_hid_ep1_in_report_selector_b0, BANKED
    bra         hid_command_dispatch__emit_status_response
hid_command_dispatch__probe_opcode06_alt_status:
    movf        usb_hid_out_arg0_b1, W, BANKED
    xorlw       0x02
    bz          hid_command_dispatch__delay_before_status_05
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__delay_before_status_05:
    call        timer3_blocking_delay_2ms, 0x0
    bra         hid_command_dispatch__stage_status_05
hid_command_dispatch__handle_opcode_0c:
    movlb       0x1
    movf        usb_hid_out_arg0_b1, W, BANKED
    xorlw       0x0F
    btfsc       STATUS, 2, ACCESS
    bsf         active_flags_acc, 7, ACCESS
hid_command_dispatch__stage_upload_payload:
    movf        i2c_coeff_2_acc, W, ACCESS
    xorlw       0x07
    bnz         hid_command_dispatch__commit_upload_payload
    movlb       0x1
    tstfsz      usb_hid_out_arg0_b1, BANKED
    bra         hid_command_dispatch__commit_upload_payload
    movlb       0x0
    clrf        fw_update_page_buffer_offset_b0, BANKED
    movlw       0x56
    movwf       fw_update_flash_cursor_hi_b0, BANKED
    clrf        fw_update_flash_cursor_lo_b0, BANKED
hid_command_dispatch__commit_upload_payload:
    bcf         RCSTA, 4, ACCESS
    bsf         active_flags_acc, 0, ACCESS
    movlb       0x0
    clrf        rx_frame_position_b0, BANKED
    clrf        rx_ring_wr_b0, BANKED
    clrf        rx_ring_rd_b0, BANKED
    call        fw_update_commit_hid_payload_page, 0x0
hid_command_dispatch__emit_opcode_status:
    movff       i2c_coeff_2_b0_phys, usb_hid_ep1_in_report_selector_phys
    bra         hid_command_dispatch__emit_status_response
hid_command_dispatch__enter_fw_update_boot_marker:
    ; BUG-SETTINGS-01: app cmd 0x40 is the firmware-update handoff,
    ; not a factory reset.  Preserve user EEPROM-backed settings and
    ; only set the bootloader-entry marker below.
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    setf        count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    clrf        flash_src_low_or_rx_length_scratch_byte, ACCESS
    rcall       eeprom_write_byte_if_changed_rcall_trampoline
    goto        flash_entry_mute_and_reset      ; V3.2+: pop-free reset path
fw_update_start_relay_handshake:
    movlb       0x0
    tstfsz      fw_update_relay_session_active_b0, BANKED
    bra         fw_update_init_sequence__gate_relay_session
    rcall       fw_update_clear_relay_status_accumulators
    call        ram_clear_prepare_page1_address_high, 0x0
    movlw       0xC7
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    movlw       0x0A
    rcall       fw_update_clear_buffer_from_003_len_w
    movlw       0x9A
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    movlw       0x2D
    rcall       fw_update_clear_buffer_from_003_len_w
    movlw       0xD1
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    movlw       0x08
    rcall       fw_update_clear_buffer_from_003_len_w
    call        fw_update_emit_bf18_status, 0x0
    movlw       0x05
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0xDC
    rcall       fw_update_stage_uart_rx_window
    movlw       0xD1
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x08
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    call        uart_rx_with_framing, 0x0
    movwf       diff_count_update_compare_or_route_mask_scratch_byte, ACCESS
    movlw       0x05
    subwf       diff_count_update_compare_or_route_mask_scratch_byte, W, ACCESS
    bnc         fw_update_init_sequence__clear_failed_session
    movlw       0x01
    movwf       fw_update_relay_session_active_b0, BANKED
    clrf        i2c_coeff_3_acc, ACCESS
fw_update_init_sequence__compare_echo_buffer_byte:
    movf        i2c_coeff_3_acc, W, ACCESS
    addlw       0x4D
    rcall       fsr2_page0_read_w_call_range_trampoline         ; W04-E03
    movwf       diff_count_update_compare_or_route_mask_scratch_byte, ACCESS
    movlw       0xD1
    addwf       i2c_coeff_3_acc, W, ACCESS
    rcall       setup_fsr2_page1_or_page2_from_w_carry
    movf        INDF2, W, ACCESS
    xorwf       diff_count_update_compare_or_route_mask_scratch_byte, W, ACCESS
    bz          fw_update_init_sequence__advance_echo_compare
    movlb       0x0
    clrf        fw_update_relay_session_active_b0, BANKED
fw_update_init_sequence__advance_echo_compare:
    incf        i2c_coeff_3_acc, F, ACCESS
    movlw       0x05
    cpfsgt      i2c_coeff_3_acc, ACCESS
    bra         fw_update_init_sequence__compare_echo_buffer_byte
    bra         fw_update_init_sequence__gate_relay_session
fw_update_init_sequence__clear_failed_session:
    clrf        fw_update_relay_session_active_b0, BANKED
fw_update_init_sequence__gate_relay_session:
    movlb       0x0
    movf        fw_update_relay_session_active_b0, W, BANKED
    bz          hid_command_dispatch__emit_opcode_status
fw_update_init_sequence__run_relay_session:
    rcall       fw_update_relay
    bra         hid_command_dispatch__emit_opcode_status
hid_command_dispatch__validate_fw_update_signature:
    movff       usb_hid_out_arg3_phys, i2c_coeff_1_b0_phys
    movff       usb_hid_out_arg4_phys, i2c_coeff_0_b0_phys
    movff       i2c_coeff_2_b0_phys, usb_hid_ep1_in_report_selector_phys
    call        stage_hid_ep1_in_report_from_selector, 0x0
    movf        fw_update_relay_signature_accum_hi_b0, W, BANKED
    xorwf       i2c_coeff_1_acc, W, ACCESS
    bnz         hid_command_dispatch__check_fw_update_signature_result
    movf        fw_update_relay_signature_accum_lo_b0, W, BANKED
    xorwf       i2c_coeff_0_acc, W, ACCESS
hid_command_dispatch__check_fw_update_signature_result:
    bnz         hid_command_dispatch__reject_fw_update_signature
    call        fw_update_emit_zero_status_lines, 0x0
    movlw       0xAA
    movlb       0x1
    movwf       usb_hid_ep1_in_report_byte2_b1, BANKED
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__reject_fw_update_signature:
    movlw       0x11
    movlb       0x1
    movwf       usb_hid_ep1_in_report_byte1_b1, BANKED
    movlb       0x0
    rcall       fw_update_clear_relay_status_accumulators
    bra         hid_command_dispatch__clear_opcode_and_return
hid_command_dispatch__unsupported_opcode:
    movlb       0x1
    clrf        usb_hid_out_opcode_b1, BANKED
    bra         hid_command_dispatch__clear_opcode_and_return

fw_update_stage_uart_rx_window:
    movwf       length_mask_or_divisor_low_scratch_byte, ACCESS
    movlb       0x1
    movlw       0x01
    movwf       flash_end_high_or_loop_mask_scratch_byte, ACCESS
    return      0

fw_update_clear_buffer_from_003_len_w:
    movwf       length_mask_or_divisor_low_scratch_byte, ACCESS
    goto        clear_ram_span_from_staged_addr_count

fw_update_clear_relay_status_accumulators:
    clrf        fw_update_relay_signature_accum_lo_b0, BANKED
    clrf        fw_update_relay_signature_accum_hi_b0, BANKED
    clrf        fw_update_relay_checksum_accum_lo_b0, BANKED
    clrf        fw_update_relay_checksum_accum_hi_b0, BANKED
    clrf        fw_update_relay_saved_addr_lo_b0, BANKED
    clrf        fw_update_relay_saved_addr_hi_b0, BANKED
    clrf        fw_update_relay_addr_lo_b0, BANKED
    clrf        fw_update_relay_addr_hi_b0, BANKED
    return      0

hid_command_dispatch__decode_opcode_xor_chain:
    movf        i2c_coeff_2_acc, W, ACCESS
    xorlw       0x01
    bz          hid_command_dispatch__clear_opcode_and_return
    xorlw       0x03
    bz          hid_command_dispatch__clear_opcode_and_return
    xorlw       0x01
    bnz         hid_command_dispatch__probe_opcode_04
    bra         hid_command_dispatch__handle_opcode_03
hid_command_dispatch__probe_opcode_04:
    xorlw       0x07
    bnz         hid_command_dispatch__probe_opcode_05
    bra         hid_command_dispatch__handle_opcode_04
hid_command_dispatch__probe_opcode_05:
    xorlw       0x01
    bnz         hid_command_dispatch__probe_opcode_06
    bra         hid_command_dispatch__apply_settings_payload
hid_command_dispatch__probe_opcode_06:
    xorlw       0x03
    bnz         hid_command_dispatch__probe_upload_opcode_range
    bra         hid_command_dispatch__handle_opcode_06
hid_command_dispatch__probe_upload_opcode_range:
    movf        i2c_coeff_2_acc, W, ACCESS
    addlw       0xF9                            ; cmd - 0x07
    sublw       0x04                            ; C=1 for cmd 0x07..0x0B
    bnc         hid_command_dispatch__probe_opcode_0c
    bra         hid_command_dispatch__stage_upload_payload
hid_command_dispatch__probe_opcode_0c:
    movf        i2c_coeff_2_acc, W, ACCESS
    xorlw       0x0C
    bnz         hid_command_dispatch__probe_fw_boot_opcode_40
    bra         hid_command_dispatch__handle_opcode_0c
hid_command_dispatch__probe_fw_boot_opcode_40:
    xorlw       0x4C
    bnz         hid_command_dispatch__probe_fw_update_opcodes
    bra         hid_command_dispatch__enter_fw_update_boot_marker
hid_command_dispatch__probe_fw_update_opcodes:
    xorlw       0x01
    bz          hid_command_dispatch__validate_fw_update_signature
    xorlw       0x03
    bnz         hid_command_dispatch__probe_diag_memread_opcode
    bra         fw_update_start_relay_handshake
hid_command_dispatch__probe_diag_memread_opcode:
    xorlw       0x01
    bnz         hid_cmd_diag_snapshot_probe
    goto        hid_diag_memread_dispatch
hid_cmd_diag_snapshot_probe:
    xorlw       0x07                            ; V3.2 Tier-1: cumulative 0x43 ^ 0x07 = 0x44
    bnz         hid_command_dispatch__unsupported_opcode  ; not 0x44 either -> fall through
    goto        hid_diag_snapshot_emit           ; cmd 0x44 (V3.2 Tier-1 diag snapshot)
hid_command_dispatch__clear_opcode_and_return:
    movlb       0x1
    clrf        usb_hid_out_opcode_b1, BANKED
    return      0

volume_logical_diff_z:
    movlb       0x0
    movf        logical_volume_3_b0, W, BANKED
    xorwf       computed_volume_3_b0, W, BANKED
    bnz         volume_logical_diff_z__return
    movf        logical_volume_2_b0, W, BANKED
    xorwf       computed_volume_2_b0, W, BANKED
    bnz         volume_logical_diff_z__return
    movf        logical_volume_1_b0, W, BANKED
    xorwf       computed_volume_1_b0, W, BANKED
    bnz         volume_logical_diff_z__return
    movf        logical_volume_b0, W, BANKED
    xorwf       computed_volume_b0, W, BANKED
volume_logical_diff_z__return:
    return      0

compare_fsr0_fsr1_bytes_z:
    movwf       diff_count_update_compare_or_route_mask_scratch_byte, ACCESS
ram_pair_diff_z__compare_next_byte:
    movf        POSTINC0, W, ACCESS
    xorwf       POSTINC1, W, ACCESS
    bnz         ram_pair_diff_z__return
    decfsz      diff_count_update_compare_or_route_mask_scratch_byte, F, ACCESS
    bra         ram_pair_diff_z__compare_next_byte
ram_pair_diff_z__return:
    return      0


; ---------------------------------------------------------------------------
; Function: hid_out_payload_index_to_fsr2
; Address : 0x15B0
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
hid_out_payload_index_to_fsr2:
    movlw       0x1A
    addwf       i2c_coeff_3_acc, W, ACCESS
    bra         setup_fsr2_page1_or_page2_from_w_carry


; ---------------------------------------------------------------------------
; Function: hid_config_fill_ff_at_index
; Address : 0x15BE
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
hid_config_fill_ff_at_index:
    movlw       0xBE
    addwf       i2c_coeff_3_acc, W, ACCESS
    call        setup_fsr2_page2_from_w, 0x0       ; W05-E02: FSR2=0x0200|W (helper clobbers W with 0x02; setf uses no W)
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
;      uart_tx_ascii_hex_byte (which uses hex_scratch_nibble_to_ascii + uart_tx_byte_blocking
;      to emit the ASCII hex pair).
;   3. Reads the response back via uart_rx_with_framing and returns it
;      through the USB IN endpoint.
; This routine ONLY runs in firmware-update mode (entered by HID opcode);
; it has no role in normal command flow. The protocol is essentially
; "USB HID = full-duplex Intel HEX over UART" so PB1 can flash both itself
; and the downstream PB2 from a single host connection.
; ---------------------------------------------------------------------------
fw_update_compare_relay_addr_limit_w:
    movlb       0x0
    subwf       fw_update_relay_addr_lo_b0, W, BANKED
    movlw       0x77
    subwfb      fw_update_relay_addr_hi_b0, W, BANKED
    return      0

fw_update_add_byte_to_relay_checksum:
    movlb       0x0
    addwf       fw_update_relay_checksum_accum_lo_b0, F, BANKED
    movlw       0x00
    addwfc      fw_update_relay_checksum_accum_hi_b0, F, BANKED
    return      0

fw_update_relay:
    lfsr        FSR2, fw_update_fail_status_text_phys
    lfsr        FSR1, fw_update_relay_header_buffer_phys
    movlw       0x08
    call        copy_w_bytes_fsr2_to_fsr1, 0x0
    movlw       0x02
    movwf       fw_update_relay_page_index, ACCESS
fw_update_relay__process_next_hid_payload_byte:
    movlw       0x1A
    addwf       fw_update_relay_page_index, W, ACCESS
    rcall       setup_fsr2_page1_or_page2_from_w_carry
    movf        INDF2, W, ACCESS
    movwf       fw_update_relay_current_byte, ACCESS
    movlw       0xC0
    rcall       fw_update_compare_relay_addr_limit_w
    bc          fw_update_relay__check_minimum_flash_addr
    movff       fw_update_relay_current_byte_phys, fw_update_relay_shift_byte_phys
    clrf        fw_update_crc_bit_index_acc, ACCESS
fw_update_relay__update_signature_bit_loop:
    btfss       fw_update_relay_signature_accum_hi_b0, 5, BANKED
    bra         fw_update_relay__clear_signature_feedback_flag
    movlw       0x01
    movwf       fw_update_crc_feedback_scratch_acc, ACCESS
    bra         fw_update_relay__shift_signature_with_payload_bit
fw_update_relay__clear_signature_feedback_flag:
    clrf        fw_update_crc_feedback_scratch_acc, ACCESS
fw_update_relay__shift_signature_with_payload_bit:
    bcf         STATUS, 0, ACCESS
    rlcf        fw_update_relay_signature_accum_lo_b0, F, BANKED
    rlcf        fw_update_relay_signature_accum_hi_b0, F, BANKED
    btfsc       fw_update_relay_shift_byte, 0, ACCESS
    bsf         fw_update_relay_signature_accum_lo_b0, 0, BANKED
    bcf         STATUS, 0, ACCESS
    rrcf        fw_update_relay_shift_byte, F, ACCESS
    movf        fw_update_crc_feedback_scratch_acc, W, ACCESS
    bz          fw_update_relay__advance_signature_bit_count
    movlw       0x02
    xorwf       fw_update_relay_signature_accum_lo_b0, F, BANKED
    movlw       0x44
    xorwf       fw_update_relay_signature_accum_hi_b0, F, BANKED
fw_update_relay__advance_signature_bit_count:
    incf        fw_update_crc_bit_index_acc, F, ACCESS
    movlw       0x07
    cpfsgt      fw_update_crc_bit_index_acc, ACCESS
    bra         fw_update_relay__update_signature_bit_loop
fw_update_relay__check_minimum_flash_addr:
    movlw       0x40
    subwf       fw_update_relay_addr_lo_b0, W, BANKED
    movlw       0x00
    subwfb      fw_update_relay_addr_hi_b0, W, BANKED
    bnc         fw_update_relay__advance_cursor_trampoline
fw_update_relay__check_crc_region_limit:
    movlw       0xC0
    rcall       fw_update_compare_relay_addr_limit_w
    bc          fw_update_relay__advance_cursor_trampoline
fw_update_relay__check_address_alignment:
    movlw       0x0F
    andwf       fw_update_relay_addr_lo_b0, W, BANKED
    movwf       fw_update_relay_alignment_remainder_lo_b0, BANKED
    clrf        fw_update_relay_alignment_remainder_hi_b0, BANKED
    iorwf       fw_update_relay_alignment_remainder_hi_b0, W, BANKED
    bz          fw_update_relay__check_saved_status_addr
    bra         fw_update_relay__forward_payload_byte
fw_update_relay__advance_cursor_trampoline:
    bra         fw_update_relay__advance_payload_cursor
fw_update_relay__check_saved_status_addr:
    movf        fw_update_relay_saved_addr_hi_b0, W, BANKED
    iorwf       fw_update_relay_saved_addr_lo_b0, W, BANKED
    bz          fw_update_relay__clear_retry_delay_counter
fw_update_relay__emit_saved_addr_checksum:
    movf        fw_update_relay_saved_addr_lo_b0, W, BANKED
    rcall       fw_update_add_byte_to_relay_checksum
    movf        fw_update_relay_saved_addr_hi_b0, W, BANKED
    rcall       fw_update_add_byte_to_relay_checksum
    comf        fw_update_relay_checksum_accum_lo_b0, W, BANKED
    movwf       fw_update_hex_or_float32_quotient_or_uart_block_scratch, ACCESS
    comf        fw_update_relay_checksum_accum_hi_b0, W, BANKED
    movwf       fw_update_checksum_or_float32_quotient_top_scratch, ACCESS
    movlw       0xF1
    addwf       fw_update_hex_or_float32_quotient_or_uart_block_scratch, W, ACCESS
    movwf       fw_update_relay_checksum_accum_lo_b0, BANKED
    movlw       0xFF
    addwfc      fw_update_checksum_or_float32_quotient_top_scratch, W, ACCESS
    movwf       fw_update_relay_checksum_accum_hi_b0, BANKED
    movf        fw_update_relay_checksum_accum_lo_b0, W, BANKED
    call        uart_tx_ascii_hex_byte, 0x0
    rcall       emit_crlf
    movlw       0x9A
    addwf       fw_update_offset_or_channel_enable_row_base_scratch, W, ACCESS
    rcall       setup_fsr2_page1_or_page2_from_w_carry
    movff       fw_update_relay_checksum_accum_lo_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys
    rcall       hex_store_ascii_byte_to_postinc2
    clrf        INDF2, ACCESS
    movlw       0x02
    addwf       fw_update_offset_or_channel_enable_row_base_scratch, F, ACCESS
    movlb       0x0
    clrf        fw_update_relay_response_retry_count_b0, BANKED
fw_update_relay__poll_status_response:
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x0A
    rcall       fw_update_stage_uart_rx_window
    movlw       0xC7
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x0A
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    call        uart_rx_with_framing, 0x0
    movff       fw_update_uart_record_byte1_phys, addr_low_counter_or_payload_scratch_phys
    movlb       0x1
    movf        fw_update_uart_record_byte0_b1, W, BANKED
    call        intel_hex_checksum_update, 0x0
    movlb       0x0
    xorwf       fw_update_relay_checksum_accum_lo_b0, W, BANKED
    bnz         fw_update_relay__handle_status_checksum_mismatch
    movlw       0x01
    movwf       fw_update_line_checksum_ok_acc, ACCESS
    bra         fw_update_relay__retry_until_response_matches

fw_update_tx_status_text_transmit:
    movlb       0x1
    movlw       0x01
    movwf       float32_product_or_uart_base_high_scratch_byte, ACCESS
    movlw       0x9A
    movwf       float32_product_or_uart_base_scratch_byte, ACCESS
    goto        uart_tx_block_from_buffer

fw_update_tx_text_block_from_w:
    clrf        float32_product_or_uart_base_high_scratch_byte, ACCESS
    movwf       float32_product_or_uart_base_scratch_byte, ACCESS
    goto        uart_tx_block_from_buffer

fw_update_relay__handle_status_checksum_mismatch:
    clrf        fw_update_line_checksum_ok_acc, ACCESS
    movlw       0x1D
    rcall       fw_update_tx_text_block_from_w
    movlb       0x0
    movff       fw_update_relay_response_retry_count_phys, fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys
    clrf        route_bit_or_tblptr_upper_scratch_byte, ACCESS
    clrf        float_shift_flash_addr_or_preset_index_scratch_byte, ACCESS
    movlw       0x0A
    movwf       route_base_or_flash_addr_low_scratch_byte, ACCESS
    movlw       0x25
    call        format_int16_decimal_ascii_to_w_pointer, 0x0
    rcall       fw_update_tx_text_block_from_w
    movlw       0x21
    rcall       uart_tx_byte_blocking_fw_update_trampoline
    call        uart_rx_ring_drain_all, 0x0
    rcall       emit_crlf
    movlw       0x19
    movlb       0x0
    subwf       fw_update_relay_response_retry_count_b0, W, BANKED
    bc          fw_update_relay__return_after_retry_exhausted
    incf        fw_update_relay_response_retry_count_b0, F, BANKED
    rcall       fw_update_tx_status_text_transmit
    rcall       emit_crlf
    bra         fw_update_relay__retry_until_response_matches
fw_update_relay__return_after_retry_exhausted:
    incf        fw_update_relay_response_retry_count_b0, F, BANKED
    return      0
fw_update_relay__retry_until_response_matches:
    movf        fw_update_line_checksum_ok_acc, W, ACCESS
    bnz         fw_update_relay__maybe_delay_before_status_emit
    bra         fw_update_relay__poll_status_response
fw_update_relay__clear_retry_delay_counter:
    clrf        fw_update_relay_retry_delay_count_b0, BANKED
fw_update_relay__maybe_delay_before_status_emit:
    movlw       0xBF
    rcall       fw_update_compare_relay_addr_limit_w
    bc          fw_update_relay__forward_payload_byte
    movlw       0x04
    subwf       fw_update_relay_retry_delay_count_b0, W, BANKED
    bc          fw_update_relay__emit_active_addr_status_line
    incf        fw_update_relay_retry_delay_count_b0, F, BANKED
    movlw       0x0A
    call        timer3_blocking_delay_ms_from_w, 0x0 ; W04-E08 factored (10 ms)
fw_update_relay__emit_active_addr_status_line:
    movff       fw_update_relay_addr_lo_phys, fw_update_relay_saved_addr_lo_phys
    movff       fw_update_relay_addr_hi_phys, fw_update_relay_saved_addr_hi_phys
    movlw       0x3A
    movlb       0x1
    movwf       fw_update_intel_hex_record_colon_b1, BANKED
    movlw       0x31
    movwf       fw_update_intel_hex_record_length_hi_b1, BANKED
    movlw       0x30
    movwf       fw_update_intel_hex_record_length_lo_b1, BANKED
    lfsr        FSR2, fw_update_intel_hex_record_addr_hi_high_nibble_phys
    movff       fw_update_relay_saved_addr_hi_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys
    rcall       hex_store_ascii_byte_to_postinc2
    movff       fw_update_relay_saved_addr_lo_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys
    rcall       hex_store_ascii_byte_to_postinc2
    movlw       0x30
    movwf       fw_update_intel_hex_record_type_hi_b1, BANKED
    movwf       fw_update_intel_hex_record_type_lo_b1, BANKED
    clrf        fw_update_intel_hex_record_tail_start_b1, BANKED
    movlw       0x09
    movwf       fw_update_offset_or_channel_enable_row_base_scratch, ACCESS
    call        uart_rx_ring_drain_all, 0x0
    rcall       fw_update_tx_status_text_transmit
    movlb       0x0
    clrf        fw_update_relay_checksum_accum_lo_b0, BANKED
    clrf        fw_update_relay_checksum_accum_hi_b0, BANKED
fw_update_relay__forward_payload_byte:
    movlw       0xBF
    rcall       fw_update_compare_relay_addr_limit_w
    bc          fw_update_relay__clear_checksum_after_range
    btfss       fw_update_relay_addr_lo_b0, 0, BANKED
    bra         fw_update_relay__stage_odd_payload_byte
    lfsr        FSR2, float32_preset_fw_update_scratch_byte0_b0_phys
    movff       fw_update_even_addr_pending_byte_b0_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys
    rcall       hex_store_ascii_byte_to_postinc2
    movff       fw_update_relay_current_byte_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys
    rcall       hex_store_ascii_byte_to_postinc2
    clrf        fw_update_hex_line_nul_terminator, ACCESS
    movlw       0x2F
    rcall       fw_update_tx_text_block_from_w
    clrf        fw_update_reply_copy_index_acc, ACCESS
    bra         fw_update_relay__copy_payload_text_until_nul
fw_update_relay__copy_payload_text_byte:
    movf        fw_update_reply_copy_index_acc, W, ACCESS
    addlw       0x2F
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x9A
    addwf       fw_update_offset_or_channel_enable_row_base_scratch, W, ACCESS
    rcall       copy_indf2_to_page1_w
    incf        fw_update_reply_copy_index_acc, F, ACCESS
    incf        fw_update_offset_or_channel_enable_row_base_scratch, F, ACCESS
fw_update_relay__copy_payload_text_until_nul:
    movf        fw_update_reply_copy_index_acc, W, ACCESS
    addlw       0x2F
    rcall       fsr2_page0_read_w_call_range_trampoline         ; W04-E03
    bnz         fw_update_relay__copy_payload_text_byte
    movlw       0x9A
    addwf       fw_update_offset_or_channel_enable_row_base_scratch, W, ACCESS
    rcall       setup_fsr2_page1_or_page2_from_w_carry
    clrf        INDF2, ACCESS
    bra         fw_update_relay__accumulate_payload_checksum
fw_update_relay__stage_odd_payload_byte:
    movff       fw_update_relay_current_byte_phys, fw_update_even_addr_pending_byte_b0_phys
fw_update_relay__accumulate_payload_checksum:
    movf        fw_update_relay_current_byte, W, ACCESS
    rcall       fw_update_add_byte_to_relay_checksum
    bra         fw_update_relay__advance_payload_cursor
fw_update_relay__clear_checksum_after_range:
    clrf        fw_update_relay_checksum_accum_lo_b0, BANKED
    clrf        fw_update_relay_checksum_accum_hi_b0, BANKED
fw_update_relay__advance_payload_cursor:
    infsnz      fw_update_relay_addr_lo_b0, F, BANKED
    incf        fw_update_relay_addr_hi_b0, F, BANKED
    incf        fw_update_relay_page_index, F, ACCESS
    movlw       0x1F
    cpfsgt      fw_update_relay_page_index, ACCESS
    bra         fw_update_relay__process_next_hid_payload_byte

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
    rcall       uart_tx_byte_blocking_fw_update_trampoline
    movlw       0x0A                                ; LF (tail-call, goto preserves caller's return)
    bra         uart_tx_byte_blocking_fw_update_trampoline

uart_tx_byte_blocking_fw_update_trampoline:
    goto        uart_tx_byte_blocking


hex_store_ascii_byte_to_postinc2:
    movff       fw_update_hex_byte_or_uart_block_base_low_scratch_phys, hex_byte_save_or_uart_status_block_buffer_phys
    swapf       fw_update_hex_or_float32_quotient_or_uart_block_scratch, F, ACCESS                ; high nibble -> low
    rcall       hex_store_ascii_low_nibble_to_postinc2
    movff       hex_byte_save_or_uart_status_block_buffer_phys, fw_update_hex_byte_or_uart_block_base_low_scratch_phys
    bra         hex_store_ascii_low_nibble_to_postinc2

hex_store_ascii_low_nibble_to_postinc2:
    movlw       0x0F
    andwf       fw_update_hex_or_float32_quotient_or_uart_block_scratch, F, ACCESS
    movf        fw_update_hex_or_float32_quotient_or_uart_block_scratch, W, ACCESS
    rcall       hex_lookup_table_ptr                ; W=nibble -> TBLPTR -> hex_lookup_table[nibble]
    tblrd*
    movff       TABLAT, POSTINC2
    return      0

; ---------------------------------------------------------------------------
; Helper: hex_lookup_table_ptr
; ---------------------------------------------------------------------------
; W holds the low nibble (caller has already ANDed with 0x0F). Adds the LOW
; byte of hex_lookup_table to W, loads TBLPTRL/TBLPTRH. W is clobbered by the
; final movlw of HIGH(hex_lookup_table). Callers typically follow with tblrd*.
; Shared by nibble_to_hex_ascii, hex_scratch_nibble_to_ascii, and the two inline nibble
; emitters in uart_tx_ascii_hex_byte's feeder. Near callers use rcall (2 B);
; distant callers (hex_scratch_nibble_to_ascii at ~0x424C) use call (4 B).
; ---------------------------------------------------------------------------
hex_lookup_table_ptr:
    addlw       LOW(hex_lookup_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(hex_lookup_table)
    movwf       TBLPTRH, ACCESS
    return      0

chain_copy_call_range_trampoline_low:
    goto        chain_copy

fsr2_page0_read_w_call_range_trampoline:
    goto        fsr2_page0_read_w

; ---------------------------------------------------------------------------
; Function: cmd_dispatch_gated            (gated post-parse command dispatcher)
; Address : 0x18EE
; ---------------------------------------------------------------------------
; Called by every incoming serial command after uart_link_parser_drain_rx_and_forward has
; staged route/cmd/data. The first instruction tests active_flags.bit3 — the
; "active gate" — and silently returns without dispatch when it
; is clear.  This single gate is what made the V1.62b CONTROL reconnect bug
; visible: a missed wake frame leaves every command discarded here.
;
; Below the gate, this routine fans out the per-cmd work:
;   • input-channel I2C pair updates (dispatch by ram_0x093 = parsed cmd_low)
;   • DSP volume/mute/preset apply through volume_dsp_write (Fix B/B') —
;     the only V3.1+ verified-write path
;   • V3.2 reconnect (active_flags.bit7) cancels any in-flight preset job,
;     mutes the DSP, and replays the preset table from preset_replay_selected_table_blocking
;
; Calls: i2c_secondary_dev_write, i2c_tas3108_reg1f_02_clear_source_pins, drive_audio_route_select_latches,
;        volume_dsp_write, i2c_tas3108_coeff_write, preset_table_apply_entry_legacy_blocking,
;        i2c_apply_channel_route_sync_burst, usb_hid_mailbox_send_reply_if_ready, timer0_rearm_50ms_heartbeat.
; ---------------------------------------------------------------------------
cmd_dispatch_gated:
    movff       WREG, cmd_dispatch_hid_mailbox_enable_phys
    btfss       active_flags_acc, 3, ACCESS
    return      0
    movlb       0x0
    btfsc       main_runtime_latch_flags_b0, 6, BANKED       ; FIELD-10 barrier_pending
    bra         wake_barrier_retry
    btfsc       active_flags_acc, 7, ACCESS
    bra         cmd_dispatch_gated__check_reconnect_and_volume_dirty
cmd_dispatch_late_bit1_entry:
    bcf         main_runtime_latch_flags_b0, 7, BANKED       ; FIELD-10 bit1-attempt marker
    btfsc       event_flags_b0, 1, BANKED
    bsf         main_runtime_latch_flags_b0, 7, BANKED
    bcf         dsp_fault_flags_b0, 2, BANKED
cmd_dispatch_input_normal:
    rcall       cmd_dispatch_input_route_if_dirty
    movlb       0x0
    btfss       main_runtime_latch_flags_b0, 7, BANKED
    bra         cmd_dispatch_gated__check_reconnect_and_volume_dirty
    bcf         main_runtime_latch_flags_b0, 7, BANKED
    btfsc       dsp_fault_flags_b0, 2, BANKED
    bra         wake_input_failed
    btfss       dsp_fault_flags_b0, 6, BANKED
    bra         cmd_dispatch_gated__check_reconnect_and_volume_dirty
    btfsc       main_runtime_latch_flags_b0, 5, BANKED
    bra         cmd_dispatch_gated__check_reconnect_and_volume_dirty
    bcf         active_flags_acc, 4, ACCESS
    bcf         active_flags_acc, 5, ACCESS
    bra         cmd_dispatch_gated__check_reconnect_and_volume_dirty
wake_input_failed:
    rcall       field10_mark_fault_mute
    goto        send_dsp_fault_status
field10_mark_fault_mute:
    bsf         active_flags_acc, 4, ACCESS
    bsf         active_flags_acc, 5, ACCESS
    bsf         event_flags_b0, 1, BANKED
    bcf         event_flags_b0, 3, BANKED
    bsf         dsp_fault_flags_b0, 6, BANKED
    return      0
wake_barrier_retry:
    call        wake_i2c_barrier_attempt, 0x0
    bc          wake_barrier_failed
    bcf         main_runtime_latch_flags_b0, 6, BANKED
    bsf         event_flags_b0, 1, BANKED
    bra         cmd_dispatch_late_bit1_entry
wake_barrier_failed:
    bsf         main_runtime_latch_flags_b0, 6, BANKED
    bra         wake_input_failed
cmd_dispatch_gated__check_reconnect_and_volume_dirty:
    movlb       0x0
    btfsc       active_flags_acc, 7, ACCESS
    bra         cmd_dispatch_gated__check_reconnect_reapply
    btfss       event_flags_b0, 3, BANKED
    bra         cmd_dispatch_gated__check_reconnect_reapply
    ; V3.4 BUG-MUTE-REFRESH-01: route/SRC/HID/wake refreshes can make
    ; volume_dirty without being user volume movement. While effective mute is
    ; set, route the dirty volume pass through the existing mute service; real
    ; user unmute/volume movement clears active_flags.bit4 before this point.
    btfss       active_flags_acc, 4, ACCESS
    bra         cmd_dispatch_gated__apply_unmuted_volume_dirty
    bsf         event_flags_b0, 5, BANKED
    bra         cmd_dispatch_gated__check_reconnect_reapply


; ---------------------------------------------------------------------------
; Helper : cmd_dispatch_input_route_if_dirty
; ---------------------------------------------------------------------------
; Single owner for event_flags.bit1 input/route side effects.  It may mark
; volume dirty for later fixed-input/mute convergence, but it never services
; bit3/bit6 itself.  FIELD-10 keeps this helper out of active7 lifecycle work;
; wake reaches it only after the 32f8 device-init barrier has succeeded.
; ---------------------------------------------------------------------------
cmd_dispatch_input_route_if_dirty:
    movlb       0x0
    btfss       event_flags_b0, 1, BANKED
    return      0
    ; Auto Detect route churn must not dirty master volume by itself while
    ; unmuted.  If user/effective mute is active, keep the dirty path so the
    ; existing mute service rewrites TAS 0x30 with zero.  Fixed-input route
    ; changes still get per-input trim convergence.
    btfsc       active_flags_acc, 4, ACCESS
    bsf         event_flags_b0, 3, BANKED
    tstfsz      input_select_b0, BANKED
    bsf         event_flags_b0, 3, BANKED
    bra         cmd_dispatch_gated__dispatch_input_route_code
; W05-E07: tail-call merge — 4 callers previously did
;   rcall cmd_dispatch_gated_i2c_pair / bra cmd_dispatch_gated__input_route_write_complete.
; Converted to `bra cmd_dispatch_gated_i2c_pair`; helper tail is
; `bra cmd_dispatch_gated__input_route_write_complete` instead of `return 0`. Saves
; 4 * 2 B by removing the trailing `bra` at each caller; helper tail
; size unchanged (return -> bra, both 1 word).
cmd_dispatch_gated__route_code_1_i2c_pair:
    movlw       0x09
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x70
    bra         cmd_dispatch_gated_i2c_pair
cmd_dispatch_gated__route_code_2_i2c_pair:
    movlw       0x0A
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0xB0
    bra         cmd_dispatch_gated_i2c_pair
cmd_dispatch_gated__route_code_3_i2c_pair:
    movlw       0x08
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x30
    bra         cmd_dispatch_gated_i2c_pair
cmd_dispatch_gated__route_code_4_i2c_pair:
    movlw       0x0B
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0xF0
cmd_dispatch_gated_i2c_pair:
    movwf       i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    movlw       0x0D
    rcall       i2c_secondary_dev_write_low_call_range_trampoline
    movf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, W, ACCESS
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x08
    rcall       i2c_secondary_dev_write_low_call_range_trampoline
    call        i2c_tas3108_reg1f_02_clear_source_pins, 0x0
    bra         cmd_dispatch_gated__input_route_write_complete
cmd_dispatch_gated__default_route_reg1f_write:
    call        drive_audio_route_select_latches, 0x0
    movlw       0x01
    call        i2c_tas3108_reg1f_write, 0x0
    bra         cmd_dispatch_gated__route_code_3_i2c_pair
cmd_dispatch_gated__dispatch_input_route_code:
    movf        pending_route_request_b0, W, BANKED
    bz          cmd_dispatch_gated__default_route_reg1f_write
    xorlw       0x01
    bz          cmd_dispatch_gated__route_code_1_i2c_pair
    xorlw       0x03
    bz          cmd_dispatch_gated__route_code_2_i2c_pair
    xorlw       0x01
    bz          cmd_dispatch_gated__route_code_3_i2c_pair
    xorlw       0x07
    bz          cmd_dispatch_gated__route_code_4_i2c_pair
    movf        pending_route_request_b0, W, BANKED
    addlw       0xFB                            ; routes 5..7 use default reg1f path
    sublw       0x02
    bc          cmd_dispatch_gated__default_route_reg1f_write
cmd_dispatch_gated__input_route_write_complete:
    rcall       usb_hid_mailbox_stage_selector5_if_enabled          ; W02-E03: factored 6-line pattern
    movlb       0x0
    bcf         event_flags_b0, 1, BANKED
    bsf         filename_dirty_flags_b0, 0, BANKED
    bra         timer0_rearm_50ms_low_window_trampoline
cmd_dispatch_gated__apply_unmuted_volume_dirty:
    bsf         event_flags_b0, 6, BANKED
    clrf        channel_enable_mask_b0, BANKED
    clrf        channel_enable_shadow_b0, BANKED
    clrf        route_volume_trim_offset_b0, BANKED
cmd_dispatch_gated__select_applied_route_trim:
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
    movf        applied_route_shadow_b0, W, BANKED
    andlw       0xF8
    bnz         cmd_dispatch_gated__stage_volume_coefficients
    movf        applied_route_shadow_b0, W, BANKED
    bz          cmd_dispatch_gated__load_applied_route_volume_trim
    addlw       0xFB
    bnc         cmd_dispatch_gated__stage_volume_coefficients
    addlw       0x01
cmd_dispatch_gated__load_applied_route_volume_trim:
    lfsr        FSR2, route_0_volume_trim_phys
    movff       PLUSW2, route_volume_trim_offset_phys
    ; Routes 1..4 (SRC receivers) carry no digital trim: clear the trim
    ; scratch explicitly rather than relying on ambient 0x09A state.
    ; Empirically load-bearing: the deterministic detect-cycle excursion
    ; (tests/sim/test_v34_detect_cycle_volume_excursion.py) still fired
    ; with the 0x0AB dispatch alone and went green only with this clear —
    ; a trim loaded by an 0x0AB==0/5/6/7 pass otherwise reaches a later
    ; receiver-route volume write through a path the static single-entry
    ; reading (ladder entry pre-clears 0x09A) does not capture.
cmd_dispatch_gated__stage_volume_coefficients:
    movf        route_volume_trim_offset_b0, W, BANKED
    addwf       computed_volume_b0, W, BANKED
    movwf       i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    movlw       0x00
    addwfc      computed_volume_1_b0, W, BANKED
    movwf       flash_upper_or_uart_count_scratch_byte, ACCESS
    movlw       0x00
    addwfc      computed_volume_2_b0, W, BANKED
    movwf       flash_block_or_uart_byte_scratch_byte, ACCESS
    movlw       0x00
    addwfc      computed_volume_3_b0, W, BANKED
    movwf       flash_gie_or_float_sign_scratch_byte, ACCESS
    call        int32_to_float32_and_save, 0x0
    rcall       chain_copy_call_range_trampoline_low ; size T122: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, float32_coeff_or_volume_work_operand_op, float32_i2c_coeff_or_volume_work_operand_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movlw       0x47
    movwf       float_product_flash_addr_or_preset_index_scratch_byte, ACCESS
    movlw       0xC9
    movwf       float_product_or_output_index_scratch_byte, ACCESS
    movlw       0xEB
    movwf       float32_product_or_uart_base_scratch_byte, ACCESS
    movlw       0x3D
    movwf       float32_product_or_uart_base_high_scratch_byte, ACCESS
    call        float32_multiply_primary_by_secondary_in_place, 0x0
    call        chain_copy, 0x0     ; size S1: table-driven copy run
    db          0x00, 0x00, float32_i2c_coeff_or_volume_work_operand_op, volume_dsp_coeff_input_shadow_byte0_op, 0x04, volume_dsp_coeff_input_shadow_byte0_op, float32_transform_shadow_dword_op, 0x04, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    call        float32_exp_limit1024_in_place, 0x0
    rcall       chain_copy_call_range_trampoline_low ; size T122: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, float32_transform_shadow_dword_op, i2c_coeff_0_acc_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    call        volume_dsp_write, 0x0       ; V3.1 Fix B: verified volume write
cmd_dispatch_gated__volume_write_complete:
    rcall       usb_hid_mailbox_stage_selector5_if_enabled          ; W02-E03: factored 6-line pattern
    movlb       0x0
    bsf         filename_dirty_flags_b0, 0, BANKED
    rcall       timer0_rearm_50ms_low_window_trampoline
cmd_dispatch_gated__check_reconnect_reapply:
    btfss       active_flags_acc, 7, ACCESS
    bra         cmd_dispatch_gated__check_mute_dirty
    ; V3.2: cancel any active preset job — reconnect does a full table apply
    movlb       0x2
    clrf        preset_job_state_b2, BANKED
    call        timer3_stop_interrupt_countdown, 0x0
    rcall       tas3108_write_zero_volume_coeff_mid_window  ; W03-E02: factored 5-line pattern
    rcall       cmd_dispatch_route_sync_if_dirty
    movlb       0x0
    bcf         event_flags_b0, 6, BANKED
    call        preset_replay_selected_table_blocking, 0x0
    bc          cmd_dispatch_gated__reapply_failed_fault_mute
    movlb       0x0
    ; V3.2 BUG-PRESET-01 hardening: if filename RAM is still dirty or
    ; under a USB filename transaction, do not report EP0 reapply complete.
    ; preset_load_filename would be unsafe to run, but clearing bit7 here
    ; makes the flasher believe the restored preset is coherent while the
    ; visible filename RAM may still belong to the previous preset.
    movf        filename_dirty_flags_b0, W, BANKED
    andlw       0x60
    bnz         cmd_dispatch_gated__defer_reapply_until_filename_ready
    btfss       INTCON, 7, ACCESS
    bra         cmd_dispatch_gated__finish_reapply_without_filename_reload
    bcf         INTCON, 7, ACCESS
    call        preset_load_filename, 0x0
    bsf         INTCON, 7, ACCESS
cmd_dispatch_gated__finish_reapply_without_filename_reload:
    bcf         active_flags_acc, 7, ACCESS
    movlb       0x0
    btfss       event_flags_b0, 5, BANKED
    btfsc       active_flags_acc, 4, ACCESS
    bra         cmd_dispatch_gated__check_mute_dirty
    bsf         event_flags_b0, 3, BANKED
    bra         cmd_dispatch_gated__check_mute_dirty
cmd_dispatch_gated__reapply_failed_fault_mute:
    bsf         active_flags_acc, 4, ACCESS
    bsf         dsp_fault_flags_b0, 6, BANKED
    bsf         RCSTA, 4, ACCESS
    return      0
cmd_dispatch_gated__defer_reapply_until_filename_ready:
cmd_dispatch_gated__check_mute_dirty:
    bsf         RCSTA, 4, ACCESS
    bsf         PIE1, 5, ACCESS
    movlb       0x0
    btfss       event_flags_b0, 5, BANKED
    bra         cmd_dispatch_gated__check_channel_enable_dirty
    btfss       active_flags_acc, 4, ACCESS
    bra         cmd_dispatch_gated__mute_dirty_unmuted
    rcall       tas3108_write_zero_volume_coeff_mid_window  ; verified zero write via volume_dsp_write
    bra         cmd_dispatch_gated__mute_dirty_complete
cmd_dispatch_gated__mute_dirty_unmuted:
    bsf         event_flags_b0, 3, BANKED
cmd_dispatch_gated__mute_dirty_complete:
    rcall       usb_hid_mailbox_stage_selector5_if_enabled          ; W02-E03: factored 6-line pattern
    movlb       0x0
cmd_dispatch_gated__check_channel_enable_dirty:
    btfss       event_flags_b0, 6, BANKED
    bra         cmd_dispatch_gated__check_route_sync_dirty
    movlw       0x5F
    movwf       route_base_or_flash_addr_low_scratch_byte, ACCESS
    movlw       0x1C
    movwf       fw_update_offset_or_channel_enable_row_base_scratch, ACCESS
    movff       channel_enable_mask_phys, channel_enable_route_shift_mask_phys
cmd_dispatch_gated__write_next_channel_enable_bit:
    rrcf        diff_count_update_compare_or_route_mask_scratch_byte, F, ACCESS
    movf        fw_update_offset_or_channel_enable_row_base_scratch, W, ACCESS
    btfsc       STATUS, 0, ACCESS
    addlw       0xEC
    movwf       route_bit_or_tblptr_upper_scratch_byte, ACCESS
    call        preset_table_apply_entry_legacy_blocking, 0x0
    movlw       0x28
    addwf       fw_update_offset_or_channel_enable_row_base_scratch, F, ACCESS
    bnc         cmd_dispatch_gated__write_next_channel_enable_bit
cmd_dispatch_gated__channel_enable_write_complete:
    rcall       usb_hid_mailbox_stage_selector5_if_enabled          ; W02-E03: factored 6-line pattern
    movlb       0x0
    bcf         event_flags_b0, 6, BANKED
cmd_dispatch_gated__check_route_sync_dirty:
    rcall       cmd_dispatch_route_sync_if_dirty
cmd_dispatch_gated__check_shared_setup_eeprom_dirty:
    movlb       0x0
    btfss       dsp_fault_flags_b0, 0, BANKED
    bra         cmd_dispatch_gated__check_setup_profile_eeprom_dirty
    bcf         dsp_fault_flags_b0, 0, BANKED
    bsf         filename_dirty_flags_b0, 2, BANKED
    rcall       timer0_rearm_50ms_low_window_trampoline
cmd_dispatch_gated__check_setup_profile_eeprom_dirty:
    movlb       0x0
    btfss       dsp_fault_flags_b0, 1, BANKED
    return      0
    bcf         dsp_fault_flags_b0, 1, BANKED
    bsf         filename_dirty_flags_b0, 2, BANKED
    bra         timer0_rearm_50ms_low_window_trampoline

timer0_rearm_50ms_low_window_trampoline:
    goto        timer0_rearm_50ms_heartbeat


; ---------------------------------------------------------------------------
; Helper : cmd_dispatch_route_sync_if_dirty
; ---------------------------------------------------------------------------
; Single owner for event_flags.bit4 route/channel sync side effects.  Normal
; dispatch and FIELD-6-DSP wake/reconnect lifecycle drains use this same tail
; so route sync can run while muted before the final validated preset reassert.
; ---------------------------------------------------------------------------
cmd_dispatch_route_sync_if_dirty:
    movlb       0x0
    btfss       event_flags_b0, 4, BANKED
    return      0
    rcall       i2c_apply_channel_route_sync_burst
    movlb       0x0
    bcf         event_flags_b0, 4, BANKED
    bsf         filename_dirty_flags_b0, 1, BANKED
    rcall       usb_hid_mailbox_stage_selector5_if_enabled
    bra         timer0_rearm_50ms_low_window_trampoline


; ---------------------------------------------------------------------------
; Helper : usb_hid_mailbox_stage_selector5_if_enabled          (W02-E03: factored 4-site pattern)
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
usb_hid_mailbox_stage_selector5_if_enabled:
    movlw       0x05
    movlb       0x0
    movwf       usb_hid_ep1_in_report_selector_b0, BANKED
    tstfsz      cmd_dispatch_hid_mailbox_enable_b0, BANKED
    goto        usb_hid_mailbox_send_reply_if_ready
    return      0


; ---------------------------------------------------------------------------
; Helper: setup_fsr2_page1_or_page2_from_w_carry                     (W02-E05 size-opt helper)
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
setup_fsr2_page1_or_page2_from_w_carry:
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x01
    addwfc      FSR2H, F, ACCESS
    return      0

setup_fsr2_page1_settings_shadow_from_eeprom_index:
    movlb       0x1
    movlw       0xB0
    addwf       eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS
    bra         setup_fsr2_page1_from_w


; ---------------------------------------------------------------------------
; Helper: setup_fsr2_page1_from_w                           (W03-E04 size-opt helper)
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
setup_fsr2_page1_from_w:
    movwf       FSR2L, ACCESS
    movlw       0x01
    movwf       FSR2H, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: uart_link_parser_drain_rx_and_forward        (UART parser + downstream forwarder)
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
; V3.2 invariant: every handler returns through uart_link_parser__handler_return_tail
; in bounded time.  No handler may block the parser; long-running work is
; deferred to advance_preset_job_state_machine.
;
; Calls: rx_ring_has_data, rx_ring_read, uart_tx_byte_blocking,
;        send_status_burst, volume_dsp_write, preset_select_handler.
; ---------------------------------------------------------------------------
uart_link_parser_drain_rx_and_forward:
    clrf        flash_src_low_or_rx_length_scratch_byte, ACCESS
    bra         uart_link_parser__clear_pending_echo
uart_link_parser__poll_rx_ring:
    call        rx_ring_has_data, 0x0

    bnz         uart_link_parser__read_next_byte
    bra         uart_link_parser__mark_no_rx_data_return
uart_link_parser__read_next_byte:
    call        rx_ring_read, 0x0
    movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    movlw       0x7F
    cpfsgt      eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    bra         uart_link_parser__payload_forward_gate
    movf        eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS
    xorlw       0xB0
    bnz         uart_link_parser__check_b1_address_route
    movlw       0x01
    movwf       rx_frame_position_b0, BANKED
    bcf         active_flags_acc, 0, ACCESS
    bra         parser_route_phase_handler
uart_link_parser__check_b1_address_route:
    xorlw       0x01
    bnz         uart_link_parser__handle_route_or_status_byte
    movlw       0x01
    movwf       rx_frame_position_b0, BANKED
    bsf         active_flags_acc, 0, ACCESS
    bra         parser_route_phase_handler
uart_link_parser__handle_route_or_status_byte:
    clrf        rx_frame_position_b0, BANKED
    bcf         active_flags_acc, 0, ACCESS
    movff       eeprom_mask_or_flash_src_high_scratch_phys, saved_w_b0_phys
    movlw       0xF0
    andwf       length_mask_or_divisor_low_scratch_byte, F, ACCESS
    movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS
    xorlw       0xB0
    bnz         parser_route_phase_handler
    movf        eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS
    xorlw       0xBF
    btfss       STATUS, 2, ACCESS
    decf        eeprom_mask_or_flash_src_high_scratch_byte, F, ACCESS
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
    bra         uart_link_parser__return_if_idle_else_poll     ; yes -> consume locally
    rcall       uart_link_forward_parser_byte_and_mark_tx                 ; no -> echo to next link
    bra         uart_link_parser__return_if_idle_else_poll
uart_link_parser__payload_forward_gate:
    btfsc       active_flags_acc, 0, ACCESS
    bra         uart_link_parser__advance_payload_position
    movlw       0x02
    subwf       rx_frame_position_b0, W, BANKED
    bc          uart_link_parser__advance_payload_position
    rcall       uart_link_forward_parser_byte_and_mark_tx
uart_link_parser__advance_payload_position:
    movlb       0x0
    tstfsz      rx_frame_position_b0, BANKED
    incf        rx_frame_position_b0, F, BANKED
    movlw       0x02
    subwf       rx_frame_position_b0, W, BANKED
    bc          uart_link_parser__latch_command_or_data
    bra         uart_link_parser__return_if_idle_else_poll
uart_link_parser__latch_command_or_data:
    movf        rx_frame_position_b0, W, BANKED
    xorlw       0x02
    bnz         uart_link_parser__latch_data_and_dispatch_command
    movff       eeprom_mask_or_flash_src_high_scratch_phys, uart_current_cmd_code_phys
    bra         uart_link_parser__return_if_idle_else_poll
uart_link_parser__latch_data_and_dispatch_command:
    movff       eeprom_mask_or_flash_src_high_scratch_phys, current_cmd_data_b0_phys
    movff       eeprom_mask_or_flash_src_high_scratch_phys, uart_cmd_reply_data_phys
    bsf         active_flags_acc, 6, ACCESS
    movlw       0x01
    movwf       rx_frame_position_b0, BANKED
    bra         cmd_dispatch_xor_chain
; ---------------------------------------------------------------------------
; wake_request_handler                     (cmd=0x03 data=0x01)
; Sets active_flags.bit3 (open the gate) and raises event_flags.bit2 only if
; the gate was previously closed (so a wake against an already-open gate
; doesn't re-trigger run_wake_rail_gate_and_dsp_cold_init). The XOR-then-AND-then-XOR dance is the
; stock idiom for "set bit3 unconditionally, set bit2 only if was clear".
; This is the wake frame that V1.62b CONTROL was failing to send after
; reconnect — see V162B_RECONNECT_WAKE_BUG.md.
; ---------------------------------------------------------------------------
wake_request_handler:
    clrf        length_mask_or_divisor_low_scratch_byte, ACCESS                    ; ram_0x005 = (gate-was-closed) ? 1 : 0
    btfss       active_flags_acc, 3, ACCESS              ; gate already open?
    incf        length_mask_or_divisor_low_scratch_byte, F, ACCESS
    rlncf       length_mask_or_divisor_low_scratch_byte, F, ACCESS
    rlncf       length_mask_or_divisor_low_scratch_byte, F, ACCESS                 ; shifted into bit2 mask position
    movf        event_flags_b0, W, BANKED
    xorwf       length_mask_or_divisor_low_scratch_byte, W, ACCESS
    andlw       0xFB                                 ; preserve every bit except bit2
    xorwf       length_mask_or_divisor_low_scratch_byte, W, ACCESS                 ; OR in bit2 if we computed it
    movwf       event_flags_b0, BANKED
    btfsc       event_flags_b0, 2, BANKED               ; event raised?
    bsf         active_flags_acc, 3, ACCESS              ; open the gate
    bra         uart_link_parser__handler_return_tail

; ---------------------------------------------------------------------------
; standby_request_handler                  (cmd=0x03 data=0x00)
; Symmetric inverse of wake: clear active_flags.bit3 (close the gate) and
; raise event_flags.bit2 to schedule hw_standby_shutdown. If the gate was
; already closed, preserve any pending event: CONTROL may emit duplicate
; standby frames before standby_event_dispatch runs, and clearing bit2 there
; would cancel the hardware shutdown while leaving the logical gate closed.
; This is the broadcast that closes EVERY MAIN's gate on the chain — once
; closed, cmd_dispatch_gated drops every command until a
; wake reopens it.
; ---------------------------------------------------------------------------
standby_request_handler:
    btfss       active_flags_acc, 3, ACCESS              ; gate currently open?
    bra         uart_link_parser__standby_duplicate_preserve_pending_event     ; no  -> just consume the event
    bsf         event_flags_b0, 2, BANKED               ; yes -> raise standby event
    bra         uart_link_parser__standby_close_gate_if_event_pending
uart_link_parser__standby_duplicate_preserve_pending_event:
    movlb       0x0
    nop                                             ; duplicate standby: keep pending bit2 intact
uart_link_parser__standby_close_gate_if_event_pending:
    btfsc       event_flags_b0, 2, BANKED
    bcf         active_flags_acc, 3, ACCESS              ; close the gate (BROADCAST drops all MAINs)
    bra         uart_link_parser__handler_return_tail
; ---------------------------------------------------------------------------
cmd03_stage_mute_refresh_w:
    movlb       0x0
    clrf        length_mask_or_divisor_low_scratch_byte, ACCESS
    btfsc       active_flags_acc, 4, ACCESS
    incf        length_mask_or_divisor_low_scratch_byte, F, ACCESS
    btfsc       active_flags_acc, 5, ACCESS
    retlw       0x01
    retlw       0x00

; ---------------------------------------------------------------------------
; cmd03_mute_on_handler                    (cmd=0x03 data=0x02 — mute on)
; Sets the user mute (active_flags.bit4). If a preset job is in flight,
; latches user-mute-desired in preset_job_flags.bit1 so COMMIT/CANCEL stays
; muted instead of restoring the previous state. The xor/and dance below
; computes whether a DSP refresh is needed (event_flags.bit5 set) by
; comparing user-mute (bit4) against the shadow forced-mute (bit5).
; ---------------------------------------------------------------------------
cmd03_mute_on_handler:
    btfsc       main_runtime_latch_flags_b0, 3, BANKED                 ; HID query mode?
    bra         uart_link_parser__mute_query_reply
    bsf         active_flags_acc, 4, ACCESS              ; user mute on
    bsf         main_runtime_latch_flags_b0, 5, BANKED                  ; remember user-owned mute
    ; V3.2: if preset job active, record user wants mute
    movlb       0x2
    tstfsz      preset_job_state_b2, BANKED             ; skip if IDLE
    bsf         preset_job_flags_b2, 1, BANKED          ; latch user_mute_desired
    rcall       cmd03_stage_mute_refresh_w
    bra         uart_link_parser__mute_dirty_if_user_shadow_differs
uart_link_parser__stage_zero_mute_compare_value:
    movlw       0x00
uart_link_parser__mute_dirty_if_user_shadow_differs:
    xorwf       length_mask_or_divisor_low_scratch_byte, F, ACCESS
    btfss       STATUS, 2, ACCESS
uart_link_parser__mark_mute_refresh_dirty:
    bsf         event_flags_b0, 5, BANKED
uart_link_parser__sync_mute_shadow:
    btfss       active_flags_acc, 4, ACCESS
    bra         uart_link_parser__mute_clear_shadow_bit
    bsf         active_flags_acc, 5, ACCESS
    bra         uart_link_parser__mute_return_after_shadow_update
uart_link_parser__mute_clear_shadow_bit:
    bcf         active_flags_acc, 5, ACCESS
uart_link_parser__mute_return_after_shadow_update:
    bra         uart_link_parser__handler_return_tail
uart_link_parser__mute_query_reply:
    movlw       0x02
    btfss       active_flags_acc, 4, ACCESS
    movlw       0x03
    movwf       uart_cmd_reply_data_b0, BANKED
    bcf         main_runtime_latch_flags_b0, 3, BANKED
    bra         uart_link_parser__handler_return_tail
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
    btfsc       main_runtime_latch_flags_b0, 3, BANKED                 ; HID query mode?
    bra         uart_link_parser__mute_query_reply
    bcf         main_runtime_latch_flags_b0, 5, BANKED                  ; explicit user unmute
    ; V3.2: during a force-muted preset job, suppress the actual mute-off
    ; so the DSP stays muted while the table apply is in progress.
    ; Only record the user's desire for COMMIT to act on later.
    movlb       0x2
    tstfsz      preset_job_state_b2, BANKED             ; skip next if IDLE
    btfss       preset_job_flags_b2, 0, BANKED          ; skip next if force-muted
    bra         cmd03_mute_off_apply
    bcf         preset_job_flags_b2, 1, BANKED          ; record: user wants unmute
    movlb       0x0
    bra         uart_link_parser__handler_return_tail
cmd03_mute_off_apply:
    bcf         active_flags_acc, 4, ACCESS
    ; V3.2: if preset job active (non-force-muted), record user wants unmute
    movlb       0x2
    tstfsz      preset_job_state_b2, BANKED
    bcf         preset_job_flags_b2, 1, BANKED
    rcall       cmd03_stage_mute_refresh_w
    bra         uart_link_parser__mute_dirty_if_user_shadow_differs
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
    bra         uart_link_parser__handler_return_tail

eeprom_write_byte_if_changed_rcall_trampoline:
    goto        eeprom_write_byte_if_changed

i2c_secondary_dev_write_low_call_range_trampoline:
    goto        i2c_secondary_dev_write

; ---------------------------------------------------------------------------
; cmd04_status_response                    (cmd=0x04 data=0x00 — status_poll)
; Bypasses the active gate: CONTROL can poll for status even from standby.
; Emits the BF/05, BF/07, BF/03, BF/06, BF/1D burst from cached RAM via
; send_status_burst. There is no BF/04 reply frame.
; ---------------------------------------------------------------------------
cmd04_status_response:
    call        send_status_burst, 0x0
    bra         uart_link_parser__handler_return_tail

; ---------------------------------------------------------------------------
; cmd06_input_select_handler               (cmd=0x06 — input source)
; Updates input_select (0x099) and its mirror (0x0B3). When ram_0x094.bit0
; is set (HID-driven query mode), the routine instead RETURNS the current
; value via ram_0x0BC and clears the bit, so the caller's status burst
; carries it back.
; ---------------------------------------------------------------------------
cmd06_input_select_handler:
    btfsc       main_runtime_latch_flags_b0, 0, BANKED                 ; HID query mode?
    bra         uart_link_parser__input_select_query_reply
    ; Repeated CONTROL cmd06/data=0 means "stay in Auto Detect".  Do not
    ; force 0x0AB to 0xFF and re-apply the same SRC route during unmuted,
    ; locked playback.  When muted, keep the refresh path so BUG-MUTE-
    ; REFRESH-01 still rewrites the zero coefficient through the retry path.
    btfss       active_flags_acc, 4, ACCESS
    bra         cmd06_input_select_check_noop
    bsf         event_flags_b0, 3, BANKED
    bra         cmd06_input_select_commit
cmd06_input_select_check_noop:
    movf        current_cmd_data_b0, W, BANKED
    iorwf       input_select_b0, W, BANKED
    bnz         cmd06_input_select_commit
    bra         uart_link_parser__handler_return_tail
cmd06_input_select_commit:
    movf        current_cmd_data_b0, W, BANKED              ; commit new input
    movwf       input_select_b0, BANKED
    movwf       input_select_mirror_b0, BANKED
    setf        applied_route_shadow_b0, BANKED                    ; force route re-evaluation
    movlw       0x65
    movwf       src4382_route_refresh_watchdog_b0, BANKED                    ; run slow I2C service immediately
    bra         uart_link_parser__handler_return_tail
uart_link_parser__input_select_query_reply:
    movff       input_select_b0_phys, uart_cmd_reply_data_phys
    bcf         main_runtime_latch_flags_b0, 0, BANKED
    bra         uart_link_parser__handler_return_tail
; ---------------------------------------------------------------------------
; volume_cmd_handler                       (cmd=0x07 — volume set)
; Computes new 32-bit volume from data byte: data is sent biased by 0x60
; (0x60 = 0 dB), so the routine adds 0xFFA0 (i.e. -0x60) and sign-extends
; to 32 bits in computed_volume[0..3]. If the new value differs from the
; cached logical_volume[0..3], event_flags.bit3 (volume_dirty) is set so
; the next run_main_service_pass pass calls volume_dsp_write to push the
; coefficient into the DSP.
;
; V3.1 Fix B': the helper deliberately does NOT copy computed→logical
; here. The copy happens inside volume_dsp_write only after a verified
; successful I2C write (ACKSTAT==0). The old behavior unconditionally
; cleared the dirty bit, so a NACK was silent (DSP2 bug).
; ---------------------------------------------------------------------------
volume_cmd_handler:
    btfsc       main_runtime_latch_flags_b0, 1, BANKED                 ; HID query mode?
    bra         uart_link_parser__volume_query_reply
    movlw       0xA0                                 ; -0x60 low byte (two's complement)
    movwf       length_mask_or_divisor_low_scratch_byte, ACCESS
    setf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS                    ; 0xFFFF... high byte
    movf        current_cmd_data_b0, W, BANKED                 ; data byte
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS
    addwf       count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS                 ; data + 0xA0 (8-bit)
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    addwfc      flash_end_high_or_loop_mask_scratch_byte, F, ACCESS                 ; carry → upper byte
    movff       computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys, computed_volume_b0_phys
    movff       computed_volume_or_i2c_payload_or_float32_scale_or_adc_eeprom_hi_phys, computed_volume_1_b0_phys
    movlw       0x00
    btfsc       computed_volume_1_b0, 7, BANKED         ; sign-extend to 32 bits
    movlw       0xFF
    movwf       computed_volume_2_b0, BANKED
    movwf       computed_volume_3_b0, BANKED
    rcall       volume_logical_diff_z
uart_link_parser__volume_return_if_unchanged:
    bz          uart_link_parser__handler_return_tail
uart_link_parser__volume_mark_dirty:
    bsf         event_flags_b0, 3, BANKED
    ; V3.4 BUG-V34V173-1: a volume frame updates the latent volume only.
    ; Mute is owned EXCLUSIVELY by cmd 0x03.  A real user volume key while
    ; muted is unmuted by the B0/03/03 that V1.73 CONTROL emits after
    ; clearing its local mute; host/full-sync volume frames carry no such
    ; provenance and must not clear mute.  While active_flags.bit4 is set
    ; the volume-dirty drain routes through the verified mute-zero path.
    ; V3.1 Fix B': do NOT copy computed->logical here (deferred to volume_dsp_write)
    bra         uart_link_parser__handler_return_tail
uart_link_parser__volume_query_reply:
    movf        computed_volume_b0, W, BANKED
    addlw       0x60
    movwf       uart_cmd_reply_data_b0, BANKED
    bcf         main_runtime_latch_flags_b0, 1, BANKED
    bra         uart_link_parser__handler_return_tail
uart_link_parser__cmd10_require_data_29:
    movf        current_cmd_data_b0, W, BANKED
    xorlw       0x29
    bnz         uart_link_parser__handler_return_tail
uart_link_parser__cmd10_emit_cmd29_status:
    call        report_cmd29_status, 0x0
    bra         uart_link_parser__handler_return_tail
uart_update_channel_config_cache_from_cmd_index:
    movf        uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, W, ACCESS
uart_update_channel_config_cache_from_w_index:
    addlw       channel_1_source_config_op
    movwf       FSR0L, ACCESS
    clrf        FSR0H, ACCESS
    movlw       0x45
    addwf       FSR0L, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlb       0x0
    movf        current_cmd_data_b0, W, BANKED
    movwf       INDF0, ACCESS
    cpfseq      INDF1, ACCESS
    bsf         event_flags_b0, 4, BANKED
    movwf       INDF1, ACCESS
    bra         uart_link_parser__handler_return_tail
uart_link_parser__cmd1d_update_setup_timeout:
    btfsc       main_runtime_latch_flags_b0, 4, BANKED
    bra         uart_link_parser__cmd1d_query_reply
    movf        hid_opcode04_arg2_or_cmd1d_setup_b0, W, BANKED
    xorwf       current_cmd_data_b0, W, BANKED
    bz          uart_link_parser__handler_return_tail
    movff       current_cmd_data_b0_phys, hid_opcode04_arg2_or_cmd1d_setup_phys
    bsf         dsp_fault_flags_b0, 0, BANKED
    bra         uart_link_parser__handler_return_tail
uart_link_parser__cmd1d_query_reply:
    movff       hid_opcode04_arg2_or_cmd1d_setup_phys, uart_cmd_reply_data_phys
    bcf         main_runtime_latch_flags_b0, 4, BANKED
    bra         uart_link_parser__handler_return_tail
uart_link_parser__cmd1e_update_link_address:
    movff       current_cmd_data_b0_phys, link_address_setting_phys
    movf        link_address_shadow_b0, W, BANKED
    xorwf       link_address_setting_b0, W, BANKED
    btfss       STATUS, 2, ACCESS
    bsf         filename_dirty_flags_b0, 0, BANKED
    movff       link_address_setting_phys, link_address_shadow_phys
    bra         uart_link_parser__handler_return_tail
cmd_dispatch_xor_chain:
    movf        uart_current_cmd_code_b0, W, BANKED
    xorlw       0x03
    bnz         uart_link_parser__dispatch_check_cmd04_status_poll
    bra         cmd03_subdispatch
uart_link_parser__dispatch_check_cmd04_status_poll:
    xorlw       0x07
    bz          cmd04_status_response
uart_link_parser__dispatch_check_cmd06_input_select:
    xorlw       0x02
    bz          cmd06_input_select_handler
uart_link_parser__dispatch_check_cmd07_volume:
    xorlw       0x01
    bz          volume_cmd_handler
uart_link_parser__dispatch_check_cmd10_and_extended:
    xorlw       0x17
    bz          uart_link_parser__cmd10_require_data_29
    movf        uart_current_cmd_code_b0, W, BANKED
    addlw       0xE9                            ; cmd 0x17..0x1C -> index 0..5
    movwf       uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, ACCESS
    sublw       0x05
    bc          uart_update_channel_config_cache_from_cmd_index
    movf        uart_current_cmd_code_b0, W, BANKED
    xorlw       0x1D
    bz          uart_link_parser__cmd1d_update_setup_timeout
    xorlw       0x03
    bz          uart_link_parser__cmd1e_update_link_address
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
    xorlw       0x06                            ; V3.5 identity: cumulative 0x23 ^ 0x06 = 0x25
    btfsc       STATUS, 2, ACCESS               ; Z = cmd 0x25 (MAIN identity query)
    goto        cmd25_identity_query_handler
    xorlw       0x03                            ; V3.5 filename: cumulative 0x25 ^ 0x03 = 0x26
    btfsc       STATUS, 2, ACCESS               ; Z = cmd 0x26 (preset filename query)
    goto        cmd26_filename_query_handler
uart_link_parser__handler_return_tail:
    btfss       active_flags_acc, 6, ACCESS
    bra         uart_link_parser__return_if_idle_else_poll
    call        mark_chain_tx_emitted_bsr0, 0x0
    movf        uart_cmd_reply_data_b0, W, BANKED
    rcall       uart_tx_byte_blocking_call_range_trampoline
uart_link_parser__clear_pending_echo:
    bcf         active_flags_acc, 6, ACCESS
    bra         uart_link_parser__return_if_idle_else_poll
uart_link_parser__mark_no_rx_data_return:
    movlw       0x01
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
uart_link_parser__return_if_idle_else_poll:
    tstfsz      flash_src_low_or_rx_length_scratch_byte, ACCESS
    return      0
    bra         uart_link_parser__poll_rx_ring

uart_link_forward_parser_byte_and_mark_tx:
    call        mark_chain_tx_emitted_bsr0, 0x0
    movf        eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS
    bra         uart_tx_byte_blocking_call_range_trampoline


; ---------------------------------------------------------------------------
; Function: restore_eeprom_settings_on_boot
; Address : 0x1E88
; Notes   : Inferred core helper routine. Calls: eeprom_read_byte, eeprom_write_byte_if_changed.
; ---------------------------------------------------------------------------
restore_eeprom_settings_on_boot:
    rcall       chain_copy_call_range_trampoline_low ; size T122: local trampoline keeps descriptor TOS shape
    db          0xEE, 0x00, 0x00, computed_volume_3_b0_op, 0x01, 0x01, computed_volume_2_b0_op, 0x01, 0x02, computed_volume_1_b0_op, 0x01, 0x03, computed_volume_b0_op, 0x01, 0x04, input_select_b0_op, 0x01, 0x07, channel_1_source_config_op, 0x06, 0x0D, src_route_status_code_acc_op, 0x01, 0x14, link_address_setting_op, 0x01, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movf        computed_volume_3_b0, W, BANKED
    xorlw       0x80
    addlw       0x80
    bnz         restore_eeprom_settings_on_boot__clamp_volume_minimum
    subwf       computed_volume_2_b0, W, BANKED
    bnz         restore_eeprom_settings_on_boot__clamp_volume_minimum
    subwf       computed_volume_1_b0, W, BANKED
    bnz         restore_eeprom_settings_on_boot__clamp_volume_minimum
    movlw       0x13
    subwf       computed_volume_b0, W, BANKED
restore_eeprom_settings_on_boot__clamp_volume_minimum:
    bnc         restore_eeprom_settings_on_boot__validate_input_select
    movlw       0xA0
    movwf       computed_volume_b0, BANKED
    setf        computed_volume_1_b0, BANKED
    setf        computed_volume_2_b0, BANKED
    setf        computed_volume_3_b0, BANKED
restore_eeprom_settings_on_boot__validate_input_select:
    movlw       0x08
    cpfsgt      input_select_b0, BANKED
    bra         restore_eeprom_settings_on_boot__validate_channel1_source
    movlw       0x01
    movwf       input_select_b0, BANKED
restore_eeprom_settings_on_boot__validate_channel1_source:
    movlw       0x03
    cpfsgt      channel_1_source_config_b0, BANKED
    bra         restore_eeprom_settings_on_boot__validate_channel2_source
    clrf        channel_1_source_config_b0, BANKED
restore_eeprom_settings_on_boot__validate_channel2_source:
    lfsr        FSR2, channel_2_source_config_phys
    cpfsgt      INDF2, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_channel3_source
    clrf        channel_2_source_config_b0, BANKED
restore_eeprom_settings_on_boot__validate_channel3_source:
    lfsr        FSR2, channel_3_source_config_phys
    cpfsgt      INDF2, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_channel4_source
    clrf        channel_3_source_config_b0, BANKED
restore_eeprom_settings_on_boot__validate_channel4_source:
    lfsr        FSR2, channel_4_source_config_phys
    cpfsgt      INDF2, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_channel5_source
    movlw       0x01
    movwf       channel_4_source_config_b0, BANKED
restore_eeprom_settings_on_boot__validate_channel5_source:
    lfsr        FSR2, channel_5_source_config_phys
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_channel6_source
    movlw       0x01
    movwf       channel_5_source_config_b0, BANKED
restore_eeprom_settings_on_boot__validate_channel6_source:
    lfsr        FSR2, channel_6_source_config_phys
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_src_route_status
    movlw       0x01
    movwf       channel_5_source_config_b0, BANKED
restore_eeprom_settings_on_boot__validate_src_route_status:
    movlw       0x03
    cpfsgt      src_route_status_code_acc, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_link_address
    movwf       src_route_status_code_acc, ACCESS
restore_eeprom_settings_on_boot__validate_link_address:
    movlw       0x04
    cpfsgt      link_address_setting_b0, BANKED
    bra         restore_eeprom_settings_on_boot__mirror_runtime_settings
    movlw       0x01
    movwf       link_address_setting_b0, BANKED
restore_eeprom_settings_on_boot__mirror_runtime_settings:
    call        copy_computed_volume_to_logical_volume, 0x0
    rcall       chain_copy_call_range_trampoline_low ; size T122: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, input_select_b0_op, input_select_mirror_b0_op, 0x01, channel_1_source_config_op, channel_1_source_config_shadow_op, 0x06, link_address_setting_op, link_address_shadow_op, 0x01, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movlw       0x0F
    rcall       eeprom_read_byte_at_w
    movwf       setup_profile_setting_b0, BANKED
    incf        setup_profile_setting_b0, W, BANKED
    btfsc       STATUS, 2, ACCESS
    bcf         setup_profile_setting_b0, 0, BANKED
    movff       setup_profile_setting_phys, setup_profile_shadow_phys
    movlw       0x0E
    rcall       eeprom_read_byte_at_w
    movwf       hid_opcode04_arg2_or_cmd1d_setup_b0, BANKED
    movlw       0x03
    subwf       hid_opcode04_arg2_or_cmd1d_setup_b0, W, BANKED
    bc          restore_eeprom_settings_on_boot__clamp_shared_setup_maximum
    movlw       0x03
    movwf       hid_opcode04_arg2_or_cmd1d_setup_b0, BANKED
restore_eeprom_settings_on_boot__clamp_shared_setup_maximum:
    movlw       0x04
    cpfsgt      hid_opcode04_arg2_or_cmd1d_setup_b0, BANKED
    bra         restore_eeprom_settings_on_boot__read_route_trim_eeprom
    movlw       0x03
    movwf       hid_opcode04_arg2_or_cmd1d_setup_b0, BANKED
restore_eeprom_settings_on_boot__read_route_trim_eeprom:
    rcall       chain_copy_call_range_trampoline_low ; size T122: local trampoline keeps descriptor TOS shape
    db          0xEE, 0x00, 0x10, route_0_volume_trim_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movlw       0x12
    cpfsgt      route_0_volume_trim_b0, BANKED
    bra         restore_eeprom_settings_on_boot__validate_route5_trim
    clrf        route_0_volume_trim_b0, BANKED
restore_eeprom_settings_on_boot__validate_route5_trim:
    cpfsgt      route_5_volume_trim_b0, BANKED
    bra         restore_eeprom_settings_on_boot__validate_route6_trim
    clrf        route_5_volume_trim_b0, BANKED
restore_eeprom_settings_on_boot__validate_route6_trim:
    cpfsgt      route_6_volume_trim_b0, BANKED
    bra         restore_eeprom_settings_on_boot__validate_route7_trim
    clrf        route_6_volume_trim_b0, BANKED
restore_eeprom_settings_on_boot__validate_route7_trim:
    cpfsgt      route_7_volume_trim_b0, BANKED
    bra         restore_eeprom_settings_on_boot__mirror_route_trim_shadows
    clrf        route_7_volume_trim_b0, BANKED
restore_eeprom_settings_on_boot__mirror_route_trim_shadows:
    rcall       chain_copy_call_range_trampoline_low ; size T122: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, route_0_volume_trim_op, route_0_volume_trim_shadow_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movlw       0x50
    movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
restore_eeprom_settings_on_boot__read_filter_window:
    rcall       setup_fsr2_page1_settings_shadow_from_eeprom_index
    rcall       eeprom_read_indexed_byte_to_postinc2
    movlw       0x5E
    cpfsgt      eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    bra         restore_eeprom_settings_on_boot__read_filter_window
    movlw       0x60
    movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
restore_eeprom_settings_on_boot__read_preset_a_filename:
    movlb       0x2
    movlw       0x60
    addwf       eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS
    call        setup_fsr2_page2_from_w, 0x0       ; W05-E02: FSR2=0x0200|W (helper clobbers W; eeprom_read_byte takes input via ram_0x003)
    rcall       eeprom_read_indexed_byte_to_postinc2
    movlw       0x7D
    cpfsgt      eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    bra         restore_eeprom_settings_on_boot__read_preset_a_filename
    movlw       0x80
    rcall       eeprom_write_runtime_version_byte_at_w
    movlw       0x81
    rcall       eeprom_write_runtime_version_byte_at_w
    movlw       0x82
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x84                            ; V3.5_RUNTIME_EEPROM_REV_LO
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    bra         eeprom_write_byte_if_changed_rcall_trampoline

eeprom_read_indexed_byte_to_postinc2:
    movf        eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS
    rcall       eeprom_read_byte_at_w
    movwf       INDF2, ACCESS
    incf        eeprom_mask_or_flash_src_high_scratch_byte, F, ACCESS
    return      0

eeprom_write_runtime_version_byte_at_w:
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    rlncf       count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    addlw       0x02
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    rcall       eeprom_write_byte_if_changed_rcall_trampoline
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    return      0


; ---------------------------------------------------------------------------
; eeprom_read_byte_at_w  — rcall-reachable wrapper that reads one EEPROM byte.
; Arguments: W = EEPROM address (low byte); ram_0x004 cleared by helper.
; Returns  : W = byte read; BSR = 0 on return.
; W02-E01 size optimization: collapses 19 EEPROM-address preambles in
; restore_eeprom_settings_on_boot into compact W-address wrapper calls.
; ---------------------------------------------------------------------------
eeprom_read_byte_at_w:
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS   ; ram_0x003 = address low byte
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS   ; high byte always 0 in this call site set
    call        eeprom_read_byte, 0x0
    movlb       0x0
    return      0



; ---------------------------------------------------------------------------
; Helper: ram_clear_prepare_page1_address_high (W04-E02 size-opt helper)
; Sets BSR=1 and ram_0x004 (addr_high scratch) = 0x01.  W is clobbered to
; 0x01.  Shared by 9 `clear_ram_span_from_staged_addr_count` / `ram_block_clear_four_bytes_from_w` callers that
; set up a bank-1 page-1 address window before calling into the clear
; helpers.
; ---------------------------------------------------------------------------
copy_indf2_to_page1_w:
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x01
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    return      0

ram_clear_prepare_page1_address_high:
    movlb       0x1
    movlw       0x01
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Helper: ram_block_clear_four_bytes_from_w (W02-E02 size-opt helper)
; ---------------------------------------------------------------------------
; Wraps the uniform 4-instruction setup used at 7 sites inside
; i2c_apply_channel_route_sync_burst. Caller loads W with the starting ram_0x003 address
; (low byte); ram_0x004 (high byte) must already be set by the caller.
; The helper fixes the block length at 0x04 and dispatches to
; clear_ram_span_from_staged_addr_count. Saves 30 B vs inlined setup at 7 sites.
; ---------------------------------------------------------------------------
ram_block_clear_four_bytes_from_w:
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    movlw       0x04
    movwf       length_mask_or_divisor_low_scratch_byte, ACCESS
    goto        clear_ram_span_from_staged_addr_count

ram_block_clear_four_bytes_bank0_from_w:
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movlb       0x0
    bra         ram_block_clear_four_bytes_from_w


; ---------------------------------------------------------------------------
; Function: i2c_apply_channel_route_sync_burst          (DSP/secondary device sync burst)
; Address : 0x2100
; ---------------------------------------------------------------------------
; Long composite I2C-update routine triggered from cmd_dispatch_gated when
; event_flags.bit4 (input/route dirty) is set. Clears the working RAM at
; 0x04D7 area, then re-runs the channel-config / DSP-sync sequence (touches
; the secondary device 0x71 for amp routing AND the TAS3108 for the
; coefficient block). Used during initial wake and after channel config
; changes; not part of the volume-only fast path.
; ---------------------------------------------------------------------------
tblrd_load_fsr1_pair_from_table_page_w:
    movwf       TBLPTRH, ACCESS
    clrf        TBLPTRU, ACCESS
    tblrd*+
    movff       TABLAT, FSR1L
    tblrd*+
    movff       TABLAT, FSR1H
    return      0

i2c_apply_channel_route_sync_burst:
    movlw       0xD7
    rcall       ram_block_clear_four_bytes_bank0_from_w
    movlw       0xDB
    rcall       ram_block_clear_four_bytes_bank0_from_w
    movlw       0xDF
    rcall       ram_block_clear_four_bytes_bank0_from_w
    rcall       ram_clear_prepare_page1_address_high
    movlw       0xD9
    rcall       ram_block_clear_four_bytes_from_w
    movlw       0xE3
    rcall       ram_block_clear_four_bytes_bank0_from_w
    rcall       ram_clear_prepare_page1_address_high
    movlw       0xDD
    rcall       ram_block_clear_four_bytes_from_w
    rcall       ram_clear_prepare_page1_address_high
    movlw       0xE1
    rcall       ram_block_clear_four_bytes_from_w
    call        i2c_wait_bus_idle, 0x0

    ; --- Part 2: dispatch six (ram_0x0A0, ram_0x0B9) writes via FSR1
    ; -------------------------------------------------------------------
    ; Replaces a 6-way xorlw chain + 6 switch targets (~94 B) with a
    ; table-driven loop that pulls the 12-bit destination out of the
    ; packed `channel_route_pair_destination_table`.  TBLPTR is re-seeded
    ; every iteration from counter*2 so the `tblrd*+` sequence always
    ; starts at the current entry; callees are not audited to preserve
    ; TBLPTR.
    ; -------------------------------------------------------------------
    clrf        scratch_loop_counter_acc, ACCESS
i2c_apply_channel_route_sync_burst__map_next_channel_route_pair:
    rlncf       scratch_loop_counter_acc, W, ACCESS                ; W = counter * 2
    addlw       LOW(channel_route_pair_destination_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(channel_route_pair_destination_table)
    rcall       tblrd_load_fsr1_pair_from_table_page_w
    movf        scratch_loop_counter_acc, W, ACCESS
    movlb       0x0
    addlw       0x60
    rcall       fsr2_page0_read_w_call_range_trampoline         ; W04-E03
    call        map_audio_source_selector_to_route_pair, 0x0
    movff       audio_route_pair_byte0_phys, POSTINC1
    movff       audio_route_pair_byte1_phys, INDF1
    incf        scratch_loop_counter_acc, F, ACCESS
    movlw       0x05
    cpfsgt      scratch_loop_counter_acc, ACCESS
    bra         i2c_apply_channel_route_sync_burst__map_next_channel_route_pair

    ; --- Part 3: 7 I2C transactions with source-table indexed copy ------
    ; Replaces a 7-way xorlw chain + 7 switch targets (~154 B) with a
    ; table lookup into `channel_route_sync_source_block_table` plus a
    ; 4-byte movff copy through FSR1.  The I2C transaction body below is
    ; unchanged from the pre-rewrite function.
    ; -------------------------------------------------------------------
    clrf        channel_route_sync_source_block_index_acc, ACCESS
i2c_apply_channel_route_sync_burst__stage_next_dsp_source_block:
    rlncf       channel_route_sync_source_block_index_acc, W, ACCESS                ; W = counter * 2
    addlw       LOW(channel_route_sync_source_block_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(channel_route_sync_source_block_table)
    rcall       tblrd_load_fsr1_pair_from_table_page_w
    movff       POSTINC1, channel_route_sync_selected_source_byte0_phys
    movff       POSTINC1, channel_route_sync_selected_source_byte1_phys
    movff       POSTINC1, channel_route_sync_selected_source_byte2_phys
    movff       INDF1, channel_route_sync_selected_source_byte3_phys
i2c_apply_channel_route_sync_burst__start_next_dsp_transaction:
    bsf         SSPCON2, 0, ACCESS
    call        wait_sen_bounded, 0x0
    bc          i2c_apply_channel_route_sync_burst__timeout
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlb       0x1
    movlw       0x0F
    addwf       channel_route_sync_source_block_index_acc, W, ACCESS
    rcall       setup_fsr2_page1_or_page2_from_w_carry
    movf        INDF2, W, ACCESS
    call        i2c_byte_tx, 0x0
    clrf        channel_route_sync_selected_source_byte_index_acc, ACCESS
i2c_apply_channel_route_sync_burst__write_next_channel_coefficient:
    movf        channel_route_sync_selected_source_byte_index_acc, W, ACCESS
    movlb       0x0
    addlw       0x6A
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    cpfseq      INDF2, ACCESS
    bra         i2c_apply_channel_route_sync_burst__check_source_code_three
    clrf        i2c_coeff_0_acc, ACCESS
    clrf        i2c_coeff_1_acc, ACCESS
    clrf        i2c_coeff_2_acc, ACCESS
    movlw       0x3F
    bra         i2c_apply_channel_route_sync_burst__stage_forced_source_coefficients
i2c_apply_channel_route_sync_burst__check_source_code_three:
    movlw       0x03
    cpfseq      INDF2, ACCESS
    bra         i2c_apply_channel_route_sync_burst__compute_source_coefficients
    clrf        i2c_coeff_0_acc, ACCESS
    clrf        i2c_coeff_1_acc, ACCESS
    movlw       0x80
    movwf       i2c_coeff_2_acc, ACCESS
    movlw       0xBF
i2c_apply_channel_route_sync_burst__stage_forced_source_coefficients:
    movwf       i2c_coeff_3_acc, ACCESS
    bra         i2c_apply_channel_route_sync_burst__write_staged_coefficients
i2c_apply_channel_route_sync_burst__compute_source_coefficients:
    movf        INDF2, W, ACCESS
    call        uint8_to_float32_and_save, 0x0
    rcall       chain_copy          ; size T100/T91: now in relative range
    db          0x00, 0x00, float32_coeff_or_volume_work_operand_op, i2c_coeff_0_acc_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
i2c_apply_channel_route_sync_burst__write_staged_coefficients:
    call        stage_tas3108_coeff_input_scratch, 0x0  ; size S3 (out of rcall reach)
    call        i2c_emit_tas3108_coeff_from_staged_float, 0x0
    incf        channel_route_sync_selected_source_byte_index_acc, F, ACCESS
    movlw       0x03
    cpfsgt      channel_route_sync_selected_source_byte_index_acc, ACCESS
    bra         i2c_apply_channel_route_sync_burst__write_next_channel_coefficient
    bsf         SSPCON2, 2, ACCESS
    call        wait_pen_bounded, 0x0
    bc          i2c_apply_channel_route_sync_burst__pen_timeout
    incf        channel_route_sync_source_block_index_acc, F, ACCESS
    movlw       0x06
    cpfsgt      channel_route_sync_source_block_index_acc, ACCESS
    bra         i2c_apply_channel_route_sync_burst__stage_next_dsp_source_block
    retlw       0x06
i2c_apply_channel_route_sync_burst__timeout:
    call        i2c_timeout_recover_advertise, 0x0
    retlw       0x06
i2c_apply_channel_route_sync_burst__pen_timeout:
    call        i2c_pen_timeout_recover_advertise, 0x0
    retlw       0x06


; ---------------------------------------------------------------------------
; Data: channel_route_pair_destination_table  (part 2, 6 entries × 2 B)
; ---------------------------------------------------------------------------
; Each entry is (FSR1L, FSR1H) for the destination pair written by part 2
; of i2c_apply_channel_route_sync_burst.  Counter 0..5 selects the entry; writes
; (ram_0x0A0, ram_0x0B9) at (dest, dest+1).  Matches the old 6-way xorlw
; switch byte-for-byte:
;   counter 0 -> ram_0x0D7/0x0D8  (bank 0)
;   counter 1 -> ram_0x0DB/0x0DC  (bank 0)
;   counter 2 -> ram_0x0DF/0x0E0  (bank 0)
;   counter 3 -> ram_0x1D9/0x1DA  (bank 1)
;   counter 4 -> ram_0x0E4/0x0E5  (bank 0)
;   counter 5 -> ram_0x1E0/0x1E1  (bank 1)
; ---------------------------------------------------------------------------
channel_route_pair_destination_table:
    db  0xD7, 0x00, 0xDB, 0x00, 0xDF, 0x00, 0xD9, 0x01, 0xE4, 0x00, 0xE0, 0x01


; ---------------------------------------------------------------------------
; Data: channel_route_sync_source_block_table  (part 3, 7 entries × 2 B)
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
channel_route_sync_source_block_table:
    db  0xD7, 0x00, 0xDB, 0x00, 0xDF, 0x00, 0xD9, 0x01, 0xE3, 0x00, 0xDD, 0x01, 0xE1, 0x01


; ---------------------------------------------------------------------------
; Function: stage_hid_ep1_in_report_from_selector
; Address : 0x2328
; Notes   : Inferred core helper routine. Calls: copy_indexed_fsr2_byte_to_hid_ep1_in.
; ---------------------------------------------------------------------------
stage_hid_ep1_in_report_from_selector:
    movff       usb_hid_ep1_in_report_selector_phys, usb_hid_ep1_in_report_cmd_selector_phys
    bra         stage_hid_ep1_in_report_from_selector__dispatch_selector
stage_hid_ep1_in_report_from_selector__stage_selector3_page2_block:
    movff       usb_hid_ep1_in_report_selector_arg_phys, usb_hid_ep1_in_report_byte1_phys
    movlw       0x02
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
stage_hid_ep1_in_report_from_selector__copy_selector3_payload_byte:
    movlw       0xBE
    addwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x02
    rcall       copy_indexed_fsr2_byte_to_hid_ep1_in
    movlw       0x1F
    cpfsgt      addr_low_counter_or_payload_scratch_byte, ACCESS
    bra         stage_hid_ep1_in_report_from_selector__copy_selector3_payload_byte
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_selector4_opcode04_reply:
    movff       usb_hid_ep1_in_report_selector_arg_phys, usb_hid_ep1_in_report_byte1_phys
    decf        usb_hid_ep1_in_report_selector_arg_b0, W, BANKED
    bnz         stage_hid_ep1_in_report_from_selector__check_selector4_mode2
    movff       hid_opcode04_action_phys, usb_hid_ep1_in_report_byte2_phys
    movff       hid_opcode04_arg2_or_cmd1d_setup_phys, usb_hid_ep1_in_report_byte3_phys
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__check_selector4_mode2:
    movf        usb_hid_ep1_in_report_selector_arg_b0, W, BANKED
    xorlw       0x02
    bz          stage_hid_ep1_in_report_from_selector__stage_selector4_mode2_payload
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_selector4_mode2_payload:
    movff       hid_opcode04_payload_mode_phys, usb_hid_ep1_in_report_payload_byte1_phys
    movlw       0x05
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
stage_hid_ep1_in_report_from_selector__copy_selector4_page1_payload_byte:
    movlw       0xFB
    addwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x00
    rcall       copy_indexed_fsr2_byte_to_hid_ep1_in
    movlw       0x13
    cpfsgt      addr_low_counter_or_payload_scratch_byte, ACCESS
    bra         stage_hid_ep1_in_report_from_selector__copy_selector4_page1_payload_byte
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_selector5_status_snapshot:
    movff       pending_route_request_phys, usb_hid_ep1_in_report_byte1_phys
    movff       input_select_b0_phys, usb_hid_ep1_in_report_byte2_phys
    movlb       0x1
    clrf        usb_hid_ep1_in_report_byte3_b1, BANKED
    clrf        usb_hid_ep1_in_report_payload_byte1_b1, BANKED
    movff       computed_volume_3_b0_phys, usb_hid_ep1_in_report_payload_byte2_phys
    movff       computed_volume_2_b0_phys, usb_hid_ep1_in_report_payload_byte3_phys
    movff       computed_volume_1_b0_phys, usb_hid_ep1_in_report_payload_byte4_phys
    movff       computed_volume_b0_phys, usb_hid_ep1_in_report_payload_byte5_phys
    clrf        usb_hid_ep1_in_report_payload_byte6_b1, BANKED
    btfsc       active_flags_acc, 4, ACCESS
    incf        usb_hid_ep1_in_report_payload_byte6_b1, F, BANKED
    movff       channel_enable_mask_phys, status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys
    lfsr        FSR2, usb_hid_ep1_in_report_payload_byte7_phys
    movlw       0x03
    rcall       fanout_channel_enable_bits_to_usb_report_bytes
    incf        FSR2L, F, ACCESS            ; skip usb_hid_ep1_in_report_payload_byte10_b1
    movlw       0x03
    rcall       fanout_channel_enable_bits_to_usb_report_bytes
    rcall       chain_copy          ; size S1: table-driven copy run
    db          0x00, 0x01, channel_1_source_config_op, 0x6C, 0x06, setup_profile_setting_op, 0x78, 0x01, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_selector6_version_setup:
    movlw       0x03
    movlb       0x1
    movwf       usb_hid_ep1_in_report_byte1_b1, BANKED
    movwf       usb_hid_ep1_in_report_byte2_b1, BANKED
    movlw       0x05                        ; V3.5: minor version = 5
    movwf       usb_hid_ep1_in_report_byte3_b1, BANKED
    movff       input_select_b0_phys, usb_hid_ep1_in_report_payload_byte1_phys
    clrf        usb_hid_ep1_in_report_payload_byte2_b1, BANKED
    clrf        usb_hid_ep1_in_report_payload_byte3_b1, BANKED
    clrf        usb_hid_ep1_in_report_payload_byte4_b1, BANKED
    movff       src_route_status_code_b0_phys, usb_hid_ep1_in_report_payload_byte6_phys
    movlw       0x06
    movwf       usb_hid_ep1_in_report_payload_byte7_b1, BANKED
    movlw       0x0F
    movwf       usb_hid_ep1_in_report_payload_byte8_b1, BANKED
    movwf       usb_hid_ep1_in_report_payload_byte9_b1, BANKED
    movwf       usb_hid_ep1_in_report_payload_byte10_b1, BANKED
    movwf       usb_hid_ep1_in_report_payload_byte11_b1, BANKED
    movwf       usb_hid_ep1_in_report_payload_byte12_b1, BANKED
    movwf       usb_hid_ep1_in_report_payload_byte13_b1, BANKED
    movlw       0x0A
    movwf       usb_hid_ep1_in_report_payload_byte14_b1, BANKED
    movwf       usb_hid_ep1_in_report_payload_byte15_b1, BANKED
    movwf       usb_hid_ep1_in_report_payload_byte16_b1, BANKED
    movwf       usb_hid_ep1_in_report_payload_byte17_b1, BANKED
    movwf       usb_hid_ep1_in_report_payload_byte18_b1, BANKED
    movwf       usb_hid_ep1_in_report_payload_byte19_b1, BANKED
    movlw       0x01
    movwf       usb_hid_ep1_in_report_payload_byte20_b1, BANKED
    movwf       usb_hid_ep1_in_report_payload_byte21_b1, BANKED
    rcall       chain_copy          ; size T95: table-driven copy run
    db          0x00, 0x01, route_0_volume_trim_op, usb_hid_ep1_in_report_payload_byte22_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_selector7_to_12_echo:
    movff       usb_hid_out_arg0_phys, usb_hid_ep1_in_report_byte1_phys
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__stage_empty_reply:
    movlb       0x1
    clrf        usb_hid_ep1_in_report_byte1_b1, BANKED
    clrf        usb_hid_ep1_in_report_byte2_b1, BANKED
    clrf        usb_hid_ep1_in_report_byte3_b1, BANKED
    clrf        usb_hid_ep1_in_report_payload_byte1_b1, BANKED
    bra         stage_hid_ep1_in_report_from_selector__clear_selector_and_return
stage_hid_ep1_in_report_from_selector__dispatch_selector:
    movlb       0x0
    movf        usb_hid_ep1_in_report_selector_b0, W, BANKED
    xorlw       0x03
    bnz         stage_hid_ep1_in_report_from_selector__check_selector4
    bra         stage_hid_ep1_in_report_from_selector__stage_selector3_page2_block
stage_hid_ep1_in_report_from_selector__check_selector4:
    xorlw       0x07
    bz          stage_hid_ep1_in_report_from_selector__stage_selector4_opcode04_reply
stage_hid_ep1_in_report_from_selector__check_selector5:
    xorlw       0x01
    bz          stage_hid_ep1_in_report_from_selector__stage_selector5_status_snapshot
stage_hid_ep1_in_report_from_selector__check_selector6_or_echo_range:
    xorlw       0x03
    bz          stage_hid_ep1_in_report_from_selector__stage_selector6_version_setup
    movf        usb_hid_ep1_in_report_selector_b0, W, BANKED
    addlw       0xF9                            ; selectors 7..12 echo stock_11B
    sublw       0x05
    bc          stage_hid_ep1_in_report_from_selector__stage_selector7_to_12_echo
    bra         stage_hid_ep1_in_report_from_selector__stage_empty_reply
stage_hid_ep1_in_report_from_selector__clear_selector_and_return:
    movlb       0x0
    clrf        usb_hid_ep1_in_report_selector_b0, BANKED
    return      0

tas3108_write_zero_volume_coeff_mid_window:
    goto        tas3108_write_zero_volume_coeff

uart_tx_byte_blocking_call_range_trampoline:
    goto        uart_tx_byte_blocking

fanout_channel_enable_bits_to_usb_report_bytes:
    rrcf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    clrf        INDF2, ACCESS
    rlcf        POSTINC2, F, ACCESS
    decfsz      WREG, F, ACCESS
    bra         fanout_channel_enable_bits_to_usb_report_bytes
    return      0

; ---------------------------------------------------------------------------
; Function: copy_indexed_fsr2_byte_to_hid_ep1_in
; Address : 0x24AC
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
copy_indexed_fsr2_byte_to_hid_ep1_in:
    addwfc      FSR2H, F, ACCESS
    movlw       0x5A
    addwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    rcall       copy_indf2_to_page1_w
    incf        addr_low_counter_or_payload_scratch_byte, F, ACCESS
    return      0

shift_028_02b_right_23_clear_c:
    movlw       0x18
    bra         shift_028_02b_right_23_clear_c__check_remaining
shift_028_02b_right_23_clear_c__rotate_next_bit:
    bcf         STATUS, 0, ACCESS
    rrcf        float32_secondary_work_byte2_acc, F, ACCESS
    rrcf        float32_secondary_work_byte1_acc, F, ACCESS
    rrcf        float32_secondary_work_byte0_acc, F, ACCESS
    rrcf        float32_math_operand_byte3_acc, F, ACCESS
shift_028_02b_right_23_clear_c__check_remaining:
    decfsz      WREG, F, ACCESS
    bra         shift_028_02b_right_23_clear_c__rotate_next_bit
    return      0


; ---------------------------------------------------------------------------
; Function: float32_add_secondary_to_primary_in_place
; Address : 0x24C2
; Notes   : Inferred core helper routine. Calls: main_core_service_2650, twos_complement_024_027_after_low_byte_complement, float32_pack_mantissa_exponent_sign.
; ---------------------------------------------------------------------------
float32_add_secondary_to_primary_in_place:
    rcall       chain_copy          ; size T90: table-driven copy run
    db          0x00, 0x00, float32_accum_work_byte0_op, float32_math_operand_byte3_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       shift_028_02b_right_23_clear_c
    movf        float32_math_operand_byte3_acc, W, ACCESS
    movwf       float32_exponent_work_acc, ACCESS
    movff       float32_aux_work_byte0_b0_phys, float32_math_operand_byte3_b0_phys
    rcall       copy_math_operand_low24_to_secondary
    rcall       shift_028_02b_right_23_clear_c
    movf        float32_math_operand_byte3_acc, W, ACCESS
    movwf       float32_sign_exponent_offset_scratch_acc, ACCESS
    movf        float32_exponent_work_acc, W, ACCESS
    bz          float32_add_secondary_to_primary_in_place__return_secondary_as_dominant_operand
    movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS
    subwf       float32_exponent_work_acc, W, ACCESS
    bc          float32_add_secondary_to_primary_in_place__check_primary_dominant_or_zero_secondary
    movf        float32_exponent_work_acc, W, ACCESS
    subwf       float32_sign_exponent_offset_scratch_acc, W, ACCESS
    movwf       float32_math_operand_byte3_acc, ACCESS
    movlw       0x21
    subwf       float32_math_operand_byte3_acc, W, ACCESS
    bnc         float32_add_secondary_to_primary_in_place__check_primary_dominant_or_zero_secondary
float32_add_secondary_to_primary_in_place__return_secondary_as_dominant_operand:
    rcall       chain_copy          ; size T90: table-driven copy run
    db          0x00, 0x00, float32_aux_work_byte0_op, float32_accum_work_byte0_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    bra         float32_add_secondary_to_primary_in_place__return
float32_add_secondary_to_primary_in_place__check_primary_dominant_or_zero_secondary:
    movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS
    bz          float32_add_secondary_to_primary_in_place__return_primary_as_dominant_operand
    movf        float32_exponent_work_acc, W, ACCESS
    subwf       float32_sign_exponent_offset_scratch_acc, W, ACCESS
    bc          float32_add_secondary_to_primary_in_place__prepare_signed_mantissas_for_aligned_add
    movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS
    subwf       float32_exponent_work_acc, W, ACCESS
    movwf       float32_math_operand_byte3_acc, ACCESS
    movlw       0x21
    subwf       float32_math_operand_byte3_acc, W, ACCESS
    bnc         float32_add_secondary_to_primary_in_place__prepare_signed_mantissas_for_aligned_add
float32_add_secondary_to_primary_in_place__return_primary_as_dominant_operand:
    bra         float32_add_secondary_to_primary_in_place__return
float32_add_secondary_to_primary_in_place__prepare_signed_mantissas_for_aligned_add:
    movlw       0x06
    movwf       float32_secondary_work_byte3_acc, ACCESS
    btfsc       float32_accum_work_byte3_acc, 7, ACCESS
    bsf         float32_secondary_work_byte3_acc, 7, ACCESS
    btfsc       float32_math_operand_byte2_acc, 7, ACCESS
    bsf         float32_secondary_work_byte3_acc, 6, ACCESS
    bsf         float32_accum_work_byte2_acc, 7, ACCESS
    clrf        float32_accum_work_byte3_acc, ACCESS
    bsf         float32_math_operand_byte1_acc, 7, ACCESS
    clrf        float32_math_operand_byte2_acc, ACCESS
    movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS
    subwf       float32_exponent_work_acc, W, ACCESS
    bc          float32_add_secondary_to_primary_in_place__check_primary_higher_alignment_needed
float32_add_secondary_to_primary_in_place__left_shift_secondary_toward_primary_exponent:
    bcf         STATUS, 0, ACCESS
    rlcf        float32_aux_work_byte0_acc, F, ACCESS
    rlcf        float32_math_operand_byte0_acc, F, ACCESS
    rlcf        float32_math_operand_byte1_acc, F, ACCESS
    rlcf        float32_math_operand_byte2_acc, F, ACCESS
    decf        float32_sign_exponent_offset_scratch_acc, F, ACCESS
    movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS
    xorwf       float32_exponent_work_acc, W, ACCESS
    bz          float32_add_secondary_to_primary_in_place__finish_secondary_higher_alignment
    rcall       float32_add_secondary_to_primary_in_place__decrement_alignment_guard_mod8
    bz          float32_add_secondary_to_primary_in_place__finish_secondary_higher_alignment
    bra         float32_add_secondary_to_primary_in_place__left_shift_secondary_toward_primary_exponent
float32_add_secondary_to_primary_in_place__decrement_alignment_guard_mod8:
    decf        float32_secondary_work_byte3_acc, F, ACCESS
    movff       float32_secondary_work_byte3_b0_phys, float32_math_operand_byte3_b0_phys
    movlw       0x07
    andwf       float32_math_operand_byte3_acc, F, ACCESS
    return      0
float32_add_secondary_to_primary_in_place__right_shift_primary_to_match_secondary:
    bcf         STATUS, 0, ACCESS
    rrcf        float32_accum_work_byte3_acc, F, ACCESS
    rrcf        float32_accum_work_byte2_acc, F, ACCESS
    rrcf        float32_accum_work_byte1_acc, F, ACCESS
    rrcf        float32_accum_work_byte0_acc, F, ACCESS
    incf        float32_exponent_work_acc, F, ACCESS
float32_add_secondary_to_primary_in_place__finish_secondary_higher_alignment:
    movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS
    cpfseq      float32_exponent_work_acc, ACCESS
    bra         float32_add_secondary_to_primary_in_place__right_shift_primary_to_match_secondary
    bra         float32_add_secondary_to_primary_in_place__apply_primary_sign_if_needed
float32_add_secondary_to_primary_in_place__check_primary_higher_alignment_needed:
    movf        float32_exponent_work_acc, W, ACCESS
    subwf       float32_sign_exponent_offset_scratch_acc, W, ACCESS
    bc          float32_add_secondary_to_primary_in_place__apply_primary_sign_if_needed
float32_add_secondary_to_primary_in_place__left_shift_primary_toward_secondary_exponent:
    bcf         STATUS, 0, ACCESS
    rlcf        float32_accum_work_byte0_acc, F, ACCESS
    rlcf        float32_accum_work_byte1_acc, F, ACCESS
    rlcf        float32_accum_work_byte2_acc, F, ACCESS
    rlcf        float32_accum_work_byte3_acc, F, ACCESS
    decf        float32_exponent_work_acc, F, ACCESS
    movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS
    xorwf       float32_exponent_work_acc, W, ACCESS
    bz          float32_add_secondary_to_primary_in_place__finish_primary_higher_alignment
    rcall       float32_add_secondary_to_primary_in_place__decrement_alignment_guard_mod8
    bz          float32_add_secondary_to_primary_in_place__finish_primary_higher_alignment
    bra         float32_add_secondary_to_primary_in_place__left_shift_primary_toward_secondary_exponent
float32_add_secondary_to_primary_in_place__right_shift_secondary_to_match_primary:
    bcf         STATUS, 0, ACCESS
    rrcf        float32_math_operand_byte2_acc, F, ACCESS
    rrcf        float32_math_operand_byte1_acc, F, ACCESS
    rrcf        float32_math_operand_byte0_acc, F, ACCESS
    rrcf        float32_aux_work_byte0_acc, F, ACCESS
    incf        float32_sign_exponent_offset_scratch_acc, F, ACCESS
float32_add_secondary_to_primary_in_place__finish_primary_higher_alignment:
    movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS
    cpfseq      float32_exponent_work_acc, ACCESS
    bra         float32_add_secondary_to_primary_in_place__right_shift_secondary_to_match_primary
float32_add_secondary_to_primary_in_place__apply_primary_sign_if_needed:
    btfss       float32_secondary_work_byte3_acc, 7, ACCESS
    bra         float32_add_secondary_to_primary_in_place__apply_secondary_sign_if_needed
    comf        float32_accum_work_byte0_acc, F, ACCESS
    comf        float32_accum_work_byte1_acc, F, ACCESS
    comf        float32_accum_work_byte2_acc, F, ACCESS
    comf        float32_accum_work_byte3_acc, F, ACCESS
    incf        float32_accum_work_byte0_acc, F, ACCESS
    movlw       0x00
    addwfc      float32_accum_work_byte1_acc, F, ACCESS
    addwfc      float32_accum_work_byte2_acc, F, ACCESS
    addwfc      float32_accum_work_byte3_acc, F, ACCESS
float32_add_secondary_to_primary_in_place__apply_secondary_sign_if_needed:
    btfss       float32_secondary_work_byte3_acc, 6, ACCESS
    bra         float32_add_secondary_to_primary_in_place__add_aligned_signed_mantissas
    comf        float32_aux_work_byte0_acc, F, ACCESS
    rcall       twos_complement_024_027_after_low_byte_complement
float32_add_secondary_to_primary_in_place__add_aligned_signed_mantissas:
    clrf        float32_secondary_work_byte3_acc, ACCESS
    movf        float32_accum_work_byte0_acc, W, ACCESS
    addwf       float32_aux_work_byte0_acc, F, ACCESS
    movf        float32_accum_work_byte1_acc, W, ACCESS
    addwfc      float32_math_operand_byte0_acc, F, ACCESS
    movf        float32_accum_work_byte2_acc, W, ACCESS
    addwfc      float32_math_operand_byte1_acc, F, ACCESS
    movf        float32_accum_work_byte3_acc, W, ACCESS
    addwfc      float32_math_operand_byte2_acc, F, ACCESS
    btfss       float32_math_operand_byte2_acc, 7, ACCESS
    bra         float32_add_secondary_to_primary_in_place__pack_sum_result
    comf        float32_aux_work_byte0_acc, F, ACCESS
    rcall       twos_complement_024_027_after_low_byte_complement
    movlw       0x01
    movwf       float32_secondary_work_byte3_acc, ACCESS
float32_add_secondary_to_primary_in_place__pack_sum_result:
    rcall       chain_copy          ; size S1: table-driven copy run
    db          0x00, 0x00, float32_aux_work_byte0_op, addr_low_counter_or_payload_scratch_operand, 0x04, float32_add_result_exponent_op, eeprom_addr_or_float32_pack_tail_operand_op, 0x01, float32_secondary_work_byte3_op, float32_packer_sign_flag_op, 0x01, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    call        float32_pack_mantissa_exponent_sign, 0x0
    rcall       chain_copy          ; size T90: table-driven copy run
    db          0x00, 0x00, addr_low_counter_or_payload_scratch_operand, float32_accum_work_byte0_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
float32_add_secondary_to_primary_in_place__return:
    return      0


; ---------------------------------------------------------------------------
; Function: twos_complement_024_027_after_low_byte_complement
; Address : 0x263E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
twos_complement_024_027_after_low_byte_complement:
    comf        float32_math_operand_byte0_acc, F, ACCESS
    comf        float32_math_operand_byte1_acc, F, ACCESS
    comf        float32_math_operand_byte2_acc, F, ACCESS
    incf        float32_aux_work_byte0_acc, F, ACCESS
    movlw       0x00
    addwfc      float32_math_operand_byte0_acc, F, ACCESS
    addwfc      float32_math_operand_byte1_acc, F, ACCESS
    addwfc      float32_math_operand_byte2_acc, F, ACCESS
    retlw       0x00


; ---------------------------------------------------------------------------
; Function: persist_dirty_runtime_state_to_eeprom        (EEPROM persistence service, V3.2)
; Address : (renumbered by size-opt; see .lst)
; ---------------------------------------------------------------------------
; Dirty-flag-driven flush of volume / input / route / filter / filename
; state bytes to internal EEPROM via eeprom_write_byte_if_changed (read-then-
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
persist_dirty_runtime_state_to_eeprom:
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
persist_dirty_runtime_state_to_eeprom__check_filter_window_dirty:
    btfss       filename_dirty_flags_b0, 4, BANKED
    bra         persist_dirty_runtime_state_to_eeprom__check_filename_dirty
    movlw       0x50
    movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
persist_dirty_runtime_state_to_eeprom__persist_filter_window_byte:
    movff       eeprom_mask_or_flash_src_high_scratch_phys, computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    rcall       setup_fsr2_page1_settings_shadow_from_eeprom_index
    movf        INDF2, W, ACCESS
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    rcall       eeprom_write_byte_if_changed_rcall_trampoline
    incf        eeprom_mask_or_flash_src_high_scratch_byte, F, ACCESS
    movlw       0x5E
    cpfsgt      eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    bra         persist_dirty_runtime_state_to_eeprom__persist_filter_window_byte
    movlb       0x0
    bcf         filename_dirty_flags_b0, 4, BANKED
persist_dirty_runtime_state_to_eeprom__check_filename_dirty:
    btfss       filename_dirty_flags_b0, 5, BANKED
    bra         persist_dirty_runtime_state_to_eeprom__clear_filename_usb_transaction_gate
    call        preset_persist_filename, 0x0
persist_dirty_runtime_state_to_eeprom__clear_filename_usb_transaction_gate:
    ; V3.2 USB-xact gate: ALWAYS clear bit6 when the host triggers
    ; the dirty-service path (event_flags.0 = 1), regardless of
    ; whether bit5 was set when this dispatcher ran.  bit5 may have
    ; ALREADY been cleared by preset_job_pending's persist branch
    ; (asm:9568) before persist_dirty_runtime_state_to_eeprom got to it -- if so,
    ; the bit5 test above branches over the persist call and bit6
    ; would stay set forever, locking the gate (codex MEDIUM vs
    ; f3b25d6).  Putting the bit6 clear AFTER the bit5 branch
    ; closes ensures both paths converge here.  Explicit movlb 0x0
    ; because preset_persist_filename (when it runs) calls
    ; eeprom_write_byte_if_changed which may leave BSR in a different
    ; bank.
    movlb       0x0
    bcf         filename_dirty_flags_b0, 6, BANKED
    bcf         event_flags_b0, 0, BANKED
persist_dirty_runtime_state_to_eeprom__return:
    return      0


; ---------------------------------------------------------------------------
; Helper: eeprom_persist_block_walker      (rewrite of persist_dirty_runtime_state_to_eeprom)
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
;         triggers a call to eeprom_write_byte_if_changed with
;             ram_0x008 = 0 (addr_hi),
;             ram_0x007 = offset,
;             ram_0x009 = *(bank 0 RAM at src_lo).
;         The matching bit in ram_0x0BD is cleared iff the walk fired.
;         BSR = 0 on exit (same contract as the inline version).
; Scratch: ram_0x00A (mask save), ram_0x00B (gate), ram_0x013 (loop count),
;          ram_0x003/4/7/8/9 (eeprom_write_byte_if_changed I/O), FSR0.
; ---------------------------------------------------------------------------
eeprom_persist_block_walker:
    movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS                ; save the bit mask
    tblrd*+                                      ; fetch record count
    movff       TABLAT, eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys
    movf        filename_dirty_flags_b0, W, BANKED             ; BSR = 0 on entry
    andwf       eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS
    movwf       eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, ACCESS                ; non-zero => do the work
eeprom_persist_block_walker__process_next_record:
    tblrd*+                                      ; fetch EEPROM offset
    movff       TABLAT, computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys
    tblrd*+                                      ; fetch bank-0 src_lo
    movff       TABLAT, FSR0L
    clrf        FSR0H, ACCESS                    ; all source RAM in bank 0
    movf        eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, F, ACCESS             ; is the gate still set?
    btfsc       STATUS, 2, ACCESS                ; Z => bit was clear
    bra         eeprom_persist_record_next
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    movff       INDF0, eeprom_or_filename_data_or_flash_buffer_ptr_low_or_signature_low_phys
    rcall       eeprom_write_byte_if_changed_rcall_trampoline
eeprom_persist_record_next:
    decfsz      route_bit_or_tblptr_upper_scratch_byte, F, ACCESS
    bra         eeprom_persist_block_walker__process_next_record
    movf        eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, F, ACCESS
    btfsc       STATUS, 2, ACCESS                ; gate was clear: no bit to clear
    return      0
    movlb       0x0
    comf        eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS             ; W = ~mask
    andwf       filename_dirty_flags_b0, F, BANKED             ; drop only this block's bit
    return      0


; ---------------------------------------------------------------------------
; Data: eeprom_persist_static_records
; ---------------------------------------------------------------------------
; Packed TBLRD-addressable table consumed by `eeprom_persist_block_walker`,
; one record per pair of `(eeprom_offset, src_ram_lo)`.  Each block starts
; with a 1-byte count header.  Block order mirrors the pre-rewrite
; `btfss ram_0x0BD,N` sequence so the walker is driven by the same 4
; calls in persist_dirty_runtime_state_to_eeprom.
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
; Function: poll_src4382_route_monitor          (periodic DSP/secondary refresh)
; Address : 0x27F0
; ---------------------------------------------------------------------------
; Periodic-loop slot 4 (called from run_main_service_pass). Active gate
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
poll_src4382_route_monitor:
    btfss       active_flags_acc, 3, ACCESS
    bra         poll_src4382_route_monitor__return
    movlw       0x64
    movlb       0x0
    cpfsgt      src4382_route_refresh_watchdog_b0, BANKED
    bra         poll_src4382_route_monitor__increment_refresh_watchdog
    clrf        src4382_route_refresh_watchdog_b0, BANKED
    bra         poll_src4382_route_monitor__compute_route_request
poll_src4382_route_monitor__stage_next_autodetect_candidate:
    movf        src4382_autodetect_scan_index_b0, W, BANKED
    addlw       0x08
    movwf       src4382_autodetect_scratch_b0, BANKED
    bra         poll_src4382_route_monitor__handle_autodetect_state
poll_src4382_route_monitor__compute_route_request:
    movf        input_select_b0, W, BANKED
    bz          poll_src4382_route_monitor__stage_next_autodetect_candidate
    movlw       0x09
    cpfslt      input_select_b0, BANKED       ; valid fixed inputs are 1..8
    bra         poll_src4382_route_monitor__handle_autodetect_state
    movf        input_select_b0, W, BANKED
    addlw       0xFF                       ; W = input_select - 1
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS          ; table column
    movlw       0x03
    cpfsgt      src_route_status_code_acc, ACCESS          ; status > 3 uses overflow row
    bra         poll_src4382_route_monitor__use_current_route_status_row
    movlw       0x04
    bra         poll_src4382_route_monitor__lookup_route_request_row
poll_src4382_route_monitor__use_current_route_status_row:
    movf        src_route_status_code_acc, W, ACCESS
poll_src4382_route_monitor__lookup_route_request_row:
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    rlncf       addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    rlncf       addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    rlncf       addr_high_table_row_or_checksum_scratch_byte, W, ACCESS       ; W = row * 8
    addwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS       ; W = row * 8 + column
    addlw       LOW(src4382_fixed_input_route_request_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(src4382_fixed_input_route_request_table)
    btfsc       STATUS, C, ACCESS          ; carry from low-byte table index
    addlw       0x01
    movwf       TBLPTRH, ACCESS
    clrf        TBLPTRU, ACCESS
    tblrd*
    movff       TABLAT, pending_route_request_phys
poll_src4382_route_monitor__handle_autodetect_state:
    tstfsz      input_select_b0, BANKED
    bra         poll_src4382_route_monitor__reset_autodetect_scan
    tstfsz      src4382_autodetect_countdown_b0, BANKED
    bra         poll_src4382_route_monitor__wait_autodetect_candidate_settle
    movf        applied_route_shadow_b0, W, BANKED
    bnz         poll_src4382_route_monitor__read_rx_status
    movff       src4382_autodetect_scratch_phys, status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys
    movlw       0x0D
    rcall       i2c_secondary_dev_write_low_call_range_trampoline
    movlb       0x0
    movlw       0x12                            ; candidate settle countdown
    movwf       src4382_autodetect_countdown_b0, BANKED
    bra         poll_src4382_route_monitor__finalize_pending_route
poll_src4382_route_monitor__wait_autodetect_candidate_settle:
    decfsz      src4382_autodetect_countdown_b0, F, BANKED
    bra         poll_src4382_route_monitor__finalize_pending_route
poll_src4382_route_monitor__read_rx_status:
    movlw       SRC4382_REG_RX_STATUS
    rcall       i2c_secondary_dev_random_read_call_range_trampoline
    bc          poll_src4382_route_monitor__join_after_monitor_or_timeout
    movlb       0x0
    movwf       src4382_autodetect_scratch_b0, BANKED
    tstfsz      src4382_autodetect_scratch_b0, BANKED
    bra         poll_src4382_route_monitor__handle_rx_status_present
    movf        applied_route_shadow_b0, W, BANKED
    bz          poll_src4382_route_monitor__advance_scan_after_miss
    ; RXCKR=0 while a route is selected is ambiguous: estimator hole or
    ; real loss.  Only count hard loss when the SRC4382 formal lock bit says
    ; the DIR decoder/PLL are unlocked.
    movlw       SRC4382_REG_RX_LOCK
    rcall       i2c_secondary_dev_random_read_call_range_trampoline
    bc          poll_src4382_route_monitor__join_after_monitor_or_timeout
    movlb       0x02
    andlw       SRC4382_UNLOCK_MASK
    bz          poll_src4382_route_monitor__clear_loss_debounce_for_soft_hold
poll_src4382_route_monitor__sample_hard_route_loss:
    incf        src4382_loss_debounce_b2, F, BANKED
    movlw       SRC4382_HARD_LOSS_CONFIRM_SAMPLES
    cpfslt      src4382_loss_debounce_b2, BANKED
    bra         poll_src4382_route_monitor__confirm_route_loss
    bra         poll_src4382_route_monitor__hold_current_route
poll_src4382_route_monitor__clear_loss_debounce_for_soft_hold:
    clrf        src4382_loss_debounce_b2, BANKED
poll_src4382_route_monitor__hold_current_route:
    movlb       0x0
    movff       applied_route_shadow_phys, pending_route_request_phys
    bra         poll_src4382_route_monitor__reload_source_monitor_countdown
poll_src4382_route_monitor__confirm_route_loss:
    clrf        src4382_loss_debounce_b2, BANKED
    ; V3.4 forensic L: one count per debounce-confirmed Auto-Detect loss.
    movlw       0x01                        ; index 1 = L
    rcall       diag_src_inc_w_call_range_trampoline
    movlb       0x0
poll_src4382_route_monitor__advance_scan_after_miss:
    clrf        pending_route_request_b0, BANKED
    incf        src4382_autodetect_scan_index_b0, F, BANKED
    movf        src4382_autodetect_scan_index_b0, W, BANKED
    xorlw       0x04
    bnz         poll_src4382_route_monitor__finalize_pending_route
poll_src4382_route_monitor__reset_autodetect_scan:
    clrf        src4382_autodetect_scan_index_b0, BANKED
    clrf        src4382_autodetect_countdown_b0, BANKED
    movlb       0x02
    clrf        src4382_loss_debounce_b2, BANKED
    bra         poll_src4382_route_monitor__finalize_pending_route
poll_src4382_route_monitor__handle_rx_status_present:
    movlb       0x02
    clrf        src4382_loss_debounce_b2, BANKED
    movlb       0x0
    movf        applied_route_shadow_b0, W, BANKED
    bnz         poll_src4382_route_monitor__map_rx_present_candidate_route
    movlw       SRC4382_REG_RX_LOCK
    rcall       i2c_secondary_dev_random_read_call_range_trampoline
    bc          poll_src4382_route_monitor__join_after_monitor_or_timeout
    movlb       0x0
    andlw       SRC4382_UNLOCK_MASK
    bnz         poll_src4382_route_monitor__advance_scan_after_miss
poll_src4382_route_monitor__map_rx_present_candidate_route:
    tstfsz      src4382_autodetect_scan_index_b0, BANKED
    bra         poll_src4382_route_monitor__check_scan_index1
    movlw       0x03
    movwf       pending_route_request_b0, BANKED
poll_src4382_route_monitor__check_scan_index1:
    decf        src4382_autodetect_scan_index_b0, W, BANKED
    bnz         poll_src4382_route_monitor__check_scan_index2
    movlw       0x01
    movwf       pending_route_request_b0, BANKED
poll_src4382_route_monitor__check_scan_index2:
    movf        src4382_autodetect_scan_index_b0, W, BANKED
    xorlw       0x02
    bnz         poll_src4382_route_monitor__check_scan_index3
    movlw       0x02
    movwf       pending_route_request_b0, BANKED
poll_src4382_route_monitor__check_scan_index3:
    xorlw       0x01
    bnz         poll_src4382_route_monitor__read_audio_format
    movlw       0x04
    movwf       pending_route_request_b0, BANKED
poll_src4382_route_monitor__read_audio_format:
    movlw       0x12
    rcall       i2c_secondary_dev_random_read_call_range_trampoline
    bc          poll_src4382_route_monitor__reload_source_monitor_countdown
    movlb       0x0
    movwf       src4382_audio_format_latch_b0, BANKED
    bnz         poll_src4382_route_monitor__assert_nonpcm_mute
    btfsc       main_runtime_latch_flags_b0, 5, BANKED
    bra         poll_src4382_route_monitor__sync_nonpcm_mute_state
    movlb       0x2
    movf        preset_job_state_b2, F, BANKED
    movlb       0x0
    btfsc       STATUS, 2, ACCESS
    bcf         active_flags_acc, 4, ACCESS
    bra         poll_src4382_route_monitor__sync_nonpcm_mute_state
poll_src4382_route_monitor__assert_nonpcm_mute:
    ; V3.4 forensic N: count mute EPISODES (active_flags.4 0->1 edges), not
    ; monitor passes — the monitor re-runs this branch every poll while
    ; reg 0x12 stays non-PCM.
    btfsc       active_flags_acc, 4, ACCESS
    bra         poll_src4382_route_monitor__set_nonpcm_mute_latch
    movlw       0x00                        ; index 0 = N
    rcall       diag_src_inc_w_call_range_trampoline
poll_src4382_route_monitor__set_nonpcm_mute_latch:
    bsf         active_flags_acc, 4, ACCESS
poll_src4382_route_monitor__sync_nonpcm_mute_state:
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    btfsc       active_flags_acc, 4, ACCESS
    incf        flash_end_high_or_loop_mask_scratch_byte, F, ACCESS
    movlw       0x01
    btfss       active_flags_acc, 5, ACCESS
    movlw       0x00
    xorwf       flash_end_high_or_loop_mask_scratch_byte, F, ACCESS
    btfss       STATUS, 2, ACCESS
    bsf         event_flags_b0, 5, BANKED
    btfss       active_flags_acc, 4, ACCESS
    bra         poll_src4382_route_monitor__clear_nonpcm_mute_mirror
    bsf         active_flags_acc, 5, ACCESS
    bra         poll_src4382_route_monitor__reload_source_monitor_countdown
poll_src4382_route_monitor__clear_nonpcm_mute_mirror:
    bcf         active_flags_acc, 5, ACCESS
poll_src4382_route_monitor__reload_source_monitor_countdown:
    movlw       0x28                            ; source-present monitor countdown
    movlb       0x0
    movwf       src4382_autodetect_countdown_b0, BANKED
poll_src4382_route_monitor__join_after_monitor_or_timeout:
poll_src4382_route_monitor__finalize_pending_route:
    movlb       0x0
    movf        pending_route_request_b0, W, BANKED
    xorlw       0x02
    btfsc       STATUS, 2, ACCESS
    btfsc       PORTC, 0, ACCESS
    bra         poll_src4382_route_monitor__compare_pending_route
    movff       link_address_setting_phys, pending_route_request_phys
poll_src4382_route_monitor__compare_pending_route:
    movf        applied_route_shadow_b0, W, BANKED
    xorwf       pending_route_request_b0, W, BANKED
    bz          poll_src4382_route_monitor__commit_pending_route
    bsf         event_flags_b0, 1, BANKED
    ; V3.4 forensic C: each applied route change (incl. ->no-route on loss).
    movlw       0x02                        ; index 2 = C
    rcall       diag_src_inc_w_call_range_trampoline
poll_src4382_route_monitor__commit_pending_route:
    movff       pending_route_request_phys, applied_route_shadow_phys
    bra         poll_src4382_route_monitor__return
poll_src4382_route_monitor__increment_refresh_watchdog:
    incf        src4382_route_refresh_watchdog_b0, F, BANKED
poll_src4382_route_monitor__return:
    return      0


; ---------------------------------------------------------------------------
; Data: src4382_fixed_input_route_request_table  (status row × input column)
; ---------------------------------------------------------------------------
; Rows are SRC status 0..3 plus an overflow row for impossible status bytes.
; Columns are fixed input_select 1..8. Values are the same intermediate
; ram_0x093 route requests produced by the old branch ladder before the
; existing PORTC.0 route-2 fallback below `flow_..._295c` runs.
; ---------------------------------------------------------------------------
src4382_fixed_input_route_request_table:
    db  0x00, 0x01, 0x02, 0x03, 0x04, 0x00, 0x00, 0x00
    db  0x00, 0x05, 0x01, 0x02, 0x03, 0x04, 0x00, 0x00
    db  0x00, 0x05, 0x06, 0x01, 0x02, 0x03, 0x04, 0x00
    db  0x00, 0x05, 0x06, 0x07, 0x01, 0x02, 0x03, 0x04
    db  0x00, 0x05, 0x06, 0x03, 0x04, 0x00, 0x00, 0x00

i2c_secondary_dev_random_read_call_range_trampoline:
    goto        i2c_secondary_dev_random_read

diag_src_inc_w_call_range_trampoline:
    goto        diag_src_inc_w

copy_math_operand_low24_to_secondary:
    rcall       chain_copy          ; size T94: table-driven copy run
    db          0x00, 0x00, float32_math_operand_byte0_op, float32_secondary_work_byte0_op, 0x03, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    return      0


; ---------------------------------------------------------------------------
; Function: float32_exp_limit1024_in_place
; Address : 0x297E
; Notes   : Inferred core helper routine. Calls: float32_divide_primary_by_secondary_in_place, float32_add_secondary_to_primary_in_place, float32_multiply_ram_window_by_staged_operand_in_place.
; ---------------------------------------------------------------------------
float32_exp_limit1024_in_place:
    clrf        float_loop_or_tblptr_low_scratch_byte, ACCESS
    clrf        float_divisor_or_preset_flag_scratch_byte, ACCESS
    movlw       0x80
    movwf       route_bit_or_tblptr_upper_scratch_byte, ACCESS
    movlw       0x44
    movwf       route_base_or_flash_addr_low_scratch_byte, ACCESS
    rcall       chain_copy          ; size T92: table-driven copy run
    db          0x00, 0x00, float32_transform_shadow_dword_op, float32_coeff_or_volume_work_operand_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       float32_divide_primary_by_secondary_in_place
    rcall       chain_copy          ; size T92: table-driven copy run
    db          0x00, 0x00, float32_coeff_or_volume_work_operand_op, float32_accum_work_byte0_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    clrf        float32_aux_work_byte0_acc, ACCESS
    clrf        float32_math_operand_byte0_acc, ACCESS
    movlw       0x80
    movwf       float32_math_operand_byte1_acc, ACCESS
    movlw       0x3F
    movwf       float32_math_operand_byte2_acc, ACCESS
    rcall       float32_add_secondary_to_primary_in_place
    rcall       chain_copy          ; size T92: table-driven copy run
    db          0x00, 0x00, float32_accum_work_byte0_op, float32_transform_shadow_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movlw       0x0A
    movwf       float_loop_or_tblptr_low_scratch_byte, ACCESS
float32_exp_limit1024_in_place__square_accumulator_next_pass:
    rcall       copy_transform_shadow_to_math_operand           ; size S3
    movlw       0x2F
    call        float32_multiply_ram_window_by_staged_operand_in_place, 0x0
    decfsz      float_loop_or_tblptr_low_scratch_byte, F, ACCESS
    bra         float32_exp_limit1024_in_place__square_accumulator_next_pass
    return      0


; ---------------------------------------------------------------------------
; Function: float32_multiply_primary_by_secondary_in_place
; Address : 0x2ABC
; Notes   : Inferred core helper routine. Calls: main_core_service_2bac, add_shifted_multiplicand_to_product_accumulator, shift_multiplier_mantissa_right_clear_c.
; ---------------------------------------------------------------------------
shift_01a_01d_right_23_clear_c:
    movlw       0x18
    bra         shift_01a_01d_right_23_clear_c__check_remaining
shift_01a_01d_right_23_clear_c__rotate_next_bit:
    bcf         STATUS, 0, ACCESS
    rrcf        float32_extract_or_divide_counter_acc, F, ACCESS
    rrcf        fw_update_checksum_or_float32_quotient_top_scratch, F, ACCESS
    rrcf        fw_update_hex_or_float32_quotient_or_uart_block_scratch, F, ACCESS
    rrcf        float32_extract_or_quotient_or_preset_uart_index, F, ACCESS
shift_01a_01d_right_23_clear_c__check_remaining:
    decfsz      WREG, F, ACCESS
    bra         shift_01a_01d_right_23_clear_c__rotate_next_bit
    return      0

float32_multiply_primary_by_secondary_in_place:
    rcall       chain_copy          ; size T90: table-driven copy run
    db          0x00, 0x00, float32_i2c_coeff_or_volume_work_operand_op, float32_multiply_extract_window_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       shift_01a_01d_right_23_clear_c
    movf        float32_extract_or_quotient_or_preset_uart_index, W, ACCESS
    movwf       float32_muldiv_result_exponent_acc, ACCESS
    tstfsz      float32_muldiv_result_exponent_acc, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__unpack_secondary_top_byte
    bra         float32_multiply_primary_by_secondary_in_place__clear_zero_result
float32_multiply_primary_by_secondary_in_place__unpack_secondary_top_byte:
    rcall       chain_copy          ; size T90: table-driven copy run
    db          0x00, 0x00, float32_multiply_secondary_operand_dword_op, float32_multiply_extract_window_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       shift_01a_01d_right_23_clear_c
    movf        float32_extract_or_quotient_or_preset_uart_index, W, ACCESS
    movwf       float32_aux_work_byte0_acc, ACCESS
    tstfsz      float32_aux_work_byte0_acc, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__prepare_sign_exponent_and_mantissas
float32_multiply_primary_by_secondary_in_place__clear_zero_result:
    clrf        float_divisor_or_preset_flag_scratch_byte, ACCESS
    clrf        route_bit_or_tblptr_upper_scratch_byte, ACCESS
    clrf        route_base_or_flash_addr_low_scratch_byte, ACCESS
    clrf        float_shift_flash_addr_or_preset_index_scratch_byte, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__return
float32_multiply_primary_by_secondary_in_place__prepare_sign_exponent_and_mantissas:
    movf        float32_aux_work_byte0_acc, W, ACCESS
    addlw       0x7B
    addwf       float32_muldiv_result_exponent_acc, F, ACCESS
    movff       float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys, float32_aux_work_byte0_b0_phys
    movf        float32_product_or_uart_base_high_scratch_byte, W, ACCESS
    xorwf       float32_aux_work_byte0_acc, F, ACCESS
    movlw       0x80
    andwf       float32_aux_work_byte0_acc, F, ACCESS
    bsf         route_base_or_flash_addr_low_scratch_byte, 7, ACCESS
    bsf         float32_product_or_uart_base_scratch_byte, 7, ACCESS
    clrf        float32_product_or_uart_base_high_scratch_byte, ACCESS
    clrf        float32_muldiv_product_sign_scratch_acc, ACCESS
    clrf        float32_accum_work_byte0_acc, ACCESS
    clrf        float32_accum_work_byte1_acc, ACCESS
    clrf        float32_accum_work_byte2_acc, ACCESS
    movlw       0x07
    movwf       float32_accum_work_byte3_acc, ACCESS
float32_multiply_primary_by_secondary_in_place__multiply_low_mantissa_bits:
    btfss       float_divisor_or_preset_flag_scratch_byte, 0, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__shift_multiplier_and_multiplicand
    movf        float_product_flash_addr_or_preset_index_scratch_byte, W, ACCESS
    rcall       add_shifted_multiplicand_to_product_accumulator
float32_multiply_primary_by_secondary_in_place__shift_multiplier_and_multiplicand:
    rcall       shift_multiplier_mantissa_right_clear_c
    rlcf        float_product_flash_addr_or_preset_index_scratch_byte, F, ACCESS
    rlcf        float_product_or_output_index_scratch_byte, F, ACCESS
    rlcf        float32_product_or_uart_base_scratch_byte, F, ACCESS
    rlcf        float32_product_or_uart_base_high_scratch_byte, F, ACCESS
    decfsz      float32_accum_work_byte3_acc, F, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__multiply_low_mantissa_bits
    movlw       0x11
    movwf       float32_accum_work_byte3_acc, ACCESS
float32_multiply_primary_by_secondary_in_place__multiply_high_mantissa_bits:
    btfss       float_divisor_or_preset_flag_scratch_byte, 0, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__shift_multiplier_and_product
    movf        float_product_flash_addr_or_preset_index_scratch_byte, W, ACCESS
    rcall       add_shifted_multiplicand_to_product_accumulator
float32_multiply_primary_by_secondary_in_place__shift_multiplier_and_product:
    rcall       shift_multiplier_mantissa_right_clear_c
    rrcf        float32_accum_work_byte2_acc, F, ACCESS
    rrcf        float32_accum_work_byte1_acc, F, ACCESS
    rrcf        float32_accum_work_byte0_acc, F, ACCESS
    rrcf        float32_muldiv_product_sign_scratch_acc, F, ACCESS
    decfsz      float32_accum_work_byte3_acc, F, ACCESS
    bra         float32_multiply_primary_by_secondary_in_place__multiply_high_mantissa_bits
    rcall       chain_copy          ; size S1: table-driven copy run
    db          0x00, 0x00, float32_multiply_product_mantissa_dword_op, addr_low_counter_or_payload_scratch_operand, 0x04, float32_muldiv_result_exponent_op, eeprom_addr_or_float32_pack_tail_operand_op, 0x01, float32_aux_work_byte0_op, float32_packer_sign_flag_op, 0x01, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       float32_pack_mantissa_exponent_sign
    rcall       chain_copy          ; size T97: table-driven copy run
    db          0x00, 0x00, addr_low_counter_or_payload_scratch_operand, float32_i2c_coeff_or_volume_work_operand_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
float32_multiply_primary_by_secondary_in_place__return:
    return      0


; ---------------------------------------------------------------------------
; Function: add_shifted_multiplicand_to_product_accumulator
; Address : 0x2B8E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
add_shifted_multiplicand_to_product_accumulator:
    addwf       float32_muldiv_product_sign_scratch_acc, F, ACCESS
    movf        float_product_or_output_index_scratch_byte, W, ACCESS
    addwfc      float32_accum_work_byte0_acc, F, ACCESS
    movf        float32_product_or_uart_base_scratch_byte, W, ACCESS
    addwfc      float32_accum_work_byte1_acc, F, ACCESS
    movf        float32_product_or_uart_base_high_scratch_byte, W, ACCESS
    addwfc      float32_accum_work_byte2_acc, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: shift_multiplier_mantissa_right_clear_c
; Address : 0x2B9E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
shift_multiplier_mantissa_right_clear_c:
    bcf         STATUS, 0, ACCESS
    rrcf        float_shift_flash_addr_or_preset_index_scratch_byte, F, ACCESS
    rrcf        route_base_or_flash_addr_low_scratch_byte, F, ACCESS
    rrcf        route_bit_or_tblptr_upper_scratch_byte, F, ACCESS
    rrcf        float_divisor_or_preset_flag_scratch_byte, F, ACCESS
    bcf         STATUS, 0, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Helper: fw_update_stage_flash_addr_from_cursor (W04-E04)
; Copies the caller-selected flash address held at ram_0x082:ram_0x083
; (little-endian) into ram_0x003:ram_0x004, and zeros ram_0x005:ram_0x006.
; Used as the common address preamble for flash_read / flash_erase /
; flash_write paths inside fw_update_commit_hid_payload_page.
; Uses only ACCESS-bank + movff, so BSR is preserved across the call.
; ---------------------------------------------------------------------------
fw_update_stage_flash_addr_from_cursor:
    movff       fw_update_flash_cursor_lo_phys, addr_low_counter_or_payload_scratch_phys
    movff       fw_update_flash_cursor_hi_phys, addr_high_table_row_or_checksum_scratch_phys
    clrf        length_mask_or_divisor_low_scratch_byte, ACCESS
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    return      0

fw_update_stage_flash_page_window:
    rcall       fw_update_stage_flash_addr_from_cursor
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    movlw       0xC0
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    movlb       0x3
    movlw       0x03
    movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    clrf        flash_src_low_or_rx_length_scratch_byte, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: fw_update_commit_hid_payload_page
; Address : 0x2BB8
; Notes   : Inferred flash helper routine. Calls: flash_read, flash_erase, flash_write.
; ---------------------------------------------------------------------------
fw_update_commit_hid_payload_page:
    tstfsz      fw_update_page_buffer_offset_b0, BANKED
    bra         fw_update_commit_hid_payload_page__copy_staged_payload
    rcall       fw_update_stage_flash_page_window
    call        flash_read, 0x0
fw_update_commit_hid_payload_page__copy_staged_payload:
    ; Copy 20 staged HID/programming payload bytes into the flash page buffer.
    ; stock_11B selects the stock-compatible source skew: 0x011E or 0x011C.
    lfsr        FSR2, usb_hid_out_arg3_phys
    movlb       0x1
    movf        usb_hid_out_arg0_b1, W, BANKED
    bz          fw_update_commit_hid_payload_page__payload_source_ready
    movlw       0x02
    subwf       FSR2L, F, ACCESS
fw_update_commit_hid_payload_page__payload_source_ready:
    movlw       0x04
    movlb       0x0
    addwf       fw_update_page_buffer_offset_b0, W, BANKED
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x03
    addwfc      FSR1H, F, ACCESS
    movlw       0x14
    call        copy_w_bytes_fsr2_to_fsr1, 0x0
    movlw       0x18
    addwf       fw_update_page_buffer_offset_b0, F, BANKED
    movlw       0xBF
    cpfsgt      fw_update_page_buffer_offset_b0, BANKED
    bra         fw_update_commit_hid_payload_page__return
    clrf        fw_update_page_buffer_offset_b0, BANKED
    movlw       0x3F
    subwf       fw_update_flash_cursor_lo_b0, W, BANKED
    movlw       0x5F
    subwfb      fw_update_flash_cursor_hi_b0, W, BANKED
    bc          fw_update_commit_hid_payload_page__return
    rcall       fw_update_stage_flash_addr_from_cursor
    movlw       0xBF
    addwf       fw_update_flash_cursor_lo_b0, W, BANKED
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x00
    addwfc      fw_update_flash_cursor_hi_b0, W, BANKED
    movwf       flash_end_high_or_loop_mask_scratch_byte, ACCESS
    clrf        flash_src_low_or_rx_length_scratch_byte, ACCESS
    clrf        eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    call        flash_erase, 0x0
    rcall       fw_update_stage_flash_page_window
    rcall       flash_write
    movlw       0xC0
    movlb       0x0
    addwf       fw_update_flash_cursor_lo_b0, F, BANKED
    movlw       0x00
    addwfc      fw_update_flash_cursor_hi_b0, F, BANKED
fw_update_commit_hid_payload_page__return:
    return      0


; ---------------------------------------------------------------------------
; Function: float32_divide_primary_by_secondary_in_place
; Address : 0x2CA8
; Notes   : Inferred core helper routine. Calls: main_core_service_2d80, float32_pack_mantissa_exponent_sign.
; ---------------------------------------------------------------------------
shift_015_018_right_23_clear_c:
    movlw       0x18
    bra         shift_015_018_right_23_clear_c__check_remaining
shift_015_018_right_23_clear_c__rotate_next_bit:
    bcf         STATUS, 0, ACCESS
    rrcf        float32_product_or_uart_base_scratch_byte, F, ACCESS
    rrcf        float_product_or_output_index_scratch_byte, F, ACCESS
    rrcf        float_product_flash_addr_or_preset_index_scratch_byte, F, ACCESS
    rrcf        float_shift_flash_addr_or_preset_index_scratch_byte, F, ACCESS
shift_015_018_right_23_clear_c__check_remaining:
    decfsz      WREG, F, ACCESS
    bra         shift_015_018_right_23_clear_c__rotate_next_bit
    return      0

float32_divide_primary_by_secondary_in_place:
    rcall       chain_copy          ; size T90: table-driven copy run
    db          0x00, 0x00, float32_coeff_or_volume_work_operand_op, float32_divide_extract_window_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       shift_015_018_right_23_clear_c
    movf        float_shift_flash_addr_or_preset_index_scratch_byte, W, ACCESS
    movwf       float32_muldiv_result_exponent_acc, ACCESS
    tstfsz      float32_muldiv_result_exponent_acc, ACCESS
    bra         float32_divide_primary_by_secondary_in_place__unpack_divisor_top_byte
    bra         float32_divide_primary_by_secondary_in_place__clear_zero_result
float32_divide_primary_by_secondary_in_place__unpack_divisor_top_byte:
    rcall       chain_copy          ; size T90: table-driven copy run
    db          0x00, 0x00, float32_divide_divisor_dword_op, float32_divide_extract_window_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       shift_015_018_right_23_clear_c
    movf        float_shift_flash_addr_or_preset_index_scratch_byte, W, ACCESS
    movwf       float32_muldiv_product_sign_scratch_acc, ACCESS
    tstfsz      float32_muldiv_product_sign_scratch_acc, ACCESS
    bra         float32_divide_primary_by_secondary_in_place__prepare_sign_exponent_and_mantissas
float32_divide_primary_by_secondary_in_place__clear_zero_result:
    clrf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    clrf        flash_upper_or_uart_count_scratch_byte, ACCESS
    clrf        flash_block_or_uart_byte_scratch_byte, ACCESS
    clrf        flash_gie_or_float_sign_scratch_byte, ACCESS
    return      0
float32_divide_primary_by_secondary_in_place__prepare_sign_exponent_and_mantissas:
    movf        float32_muldiv_product_sign_scratch_acc, W, ACCESS
    addlw       0x89
    subwf       float32_muldiv_result_exponent_acc, F, ACCESS
    movff       float32_sign_or_uart_digit_or_flash_read_tblptrh_save_phys, float32_divide_sign_scratch_phys
    movf        route_base_or_flash_addr_low_scratch_byte, W, ACCESS
    xorwf       float32_muldiv_product_sign_scratch_acc, F, ACCESS
    movlw       0x80
    andwf       float32_muldiv_product_sign_scratch_acc, F, ACCESS
    bsf         flash_block_or_uart_byte_scratch_byte, 7, ACCESS
    clrf        flash_gie_or_float_sign_scratch_byte, ACCESS
    bsf         route_bit_or_tblptr_upper_scratch_byte, 7, ACCESS
    clrf        route_base_or_flash_addr_low_scratch_byte, ACCESS
    movlw       0x20
    movwf       float32_extract_or_divide_counter_acc, ACCESS
float32_divide_primary_by_secondary_in_place__division_step_compare_subtract:
    bcf         STATUS, 0, ACCESS
    rlcf        float32_product_or_uart_base_high_scratch_byte, F, ACCESS
    rlcf        float32_extract_or_quotient_or_preset_uart_index, F, ACCESS
    rlcf        fw_update_hex_or_float32_quotient_or_uart_block_scratch, F, ACCESS
    rlcf        fw_update_checksum_or_float32_quotient_top_scratch, F, ACCESS
    movf        float_loop_or_tblptr_low_scratch_byte, W, ACCESS
    subwf       i2c_flag_or_flash_math_uart_cmd_scratch_byte, W, ACCESS
    movf        float_divisor_or_preset_flag_scratch_byte, W, ACCESS
    subwfb      flash_upper_or_uart_count_scratch_byte, W, ACCESS
    movf        route_bit_or_tblptr_upper_scratch_byte, W, ACCESS
    subwfb      flash_block_or_uart_byte_scratch_byte, W, ACCESS
    movf        route_base_or_flash_addr_low_scratch_byte, W, ACCESS
    subwfb      flash_gie_or_float_sign_scratch_byte, W, ACCESS
    bnc         float32_divide_primary_by_secondary_in_place__advance_remainder_next_bit
    movf        float_loop_or_tblptr_low_scratch_byte, W, ACCESS
    subwf       i2c_flag_or_flash_math_uart_cmd_scratch_byte, F, ACCESS
    movf        float_divisor_or_preset_flag_scratch_byte, W, ACCESS
    subwfb      flash_upper_or_uart_count_scratch_byte, F, ACCESS
    movf        route_bit_or_tblptr_upper_scratch_byte, W, ACCESS
    subwfb      flash_block_or_uart_byte_scratch_byte, F, ACCESS
    movf        route_base_or_flash_addr_low_scratch_byte, W, ACCESS
    subwfb      flash_gie_or_float_sign_scratch_byte, F, ACCESS
    bsf         float32_product_or_uart_base_high_scratch_byte, 0, ACCESS
float32_divide_primary_by_secondary_in_place__advance_remainder_next_bit:
    bcf         STATUS, 0, ACCESS
    rlcf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, F, ACCESS
    rlcf        flash_upper_or_uart_count_scratch_byte, F, ACCESS
    rlcf        flash_block_or_uart_byte_scratch_byte, F, ACCESS
    rlcf        flash_gie_or_float_sign_scratch_byte, F, ACCESS
    decfsz      float32_extract_or_divide_counter_acc, F, ACCESS
    bra         float32_divide_primary_by_secondary_in_place__division_step_compare_subtract
    rcall       chain_copy          ; size S1: table-driven copy run
    db          0x00, 0x00, float32_divide_quotient_dword_op, addr_low_counter_or_payload_scratch_operand, 0x04, float32_muldiv_result_exponent_op, eeprom_addr_or_float32_pack_tail_operand_op, 0x02, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    ; W04-E01: factor rcall+4 movff tail into float32_pack_mantissa_exponent_sign_and_save
    bra         float32_pack_mantissa_exponent_sign_and_save


; ---------------------------------------------------------------------------
; Function: main_core_service_2d80
; Address : 0x2D80
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
; ---------------------------------------------------------------------------
; chain_copy — table-driven replacement for straight movff copy runs (size S1)
; ---------------------------------------------------------------------------
; Call shape (ONE db directive — gpasm pads each db to word alignment, so a
; multi-line descriptor would gain phantom zeros that desync this parser):
;     call        chain_copy, 0x0
;     db          srcPage, dstPage, s0,d0,c0 [, s1,d1,c1 ...], 0xFF [, 0xFF]
; header = phys high bytes (bank numbers); each (srcL, dstL, count) row
; copies `count` consecutive bytes (srcPage:srcL+k -> dstPage:dstL+k);
; 0xFF terminates.  Total descriptor length must be EVEN — append the
; optional second 0xFF when header+rows+sentinel is odd; the exit path
; consumes one pad byte iff the resume address is odd (btfsc TBLPTRL,0)
; and rewrites TOS from TBLPTR so execution resumes word-aligned after
; the descriptor.
;
; EEPROM-source mode (size S2): srcPage == 0xEE is descriptor metadata
; only.  Never load that pseudo-page into FSR0H: PIC18 FSRnH preserves
; only a 4-bit data-memory page.  Each row's first byte is an EEPROM
; address instead of a RAM low byte; the value is fetched through
; eeprom_read_byte_at_w (clobbers ram_0x003/004, leaves BSR=0 like the inline
; rcall form it replaces).  0xEE cannot collide with a RAM page (GPR banks
; end at 3) and EE addresses stay <= 0x7F, far from the 0xFF sentinel.
;
; Clobbers: W, FSR0, TBLPTR (callers may not hold TBLPTR live — audited:
; converted sites are core-service shuffles, not flash readers),
; chain_copy_srch/dsth (BANK 3 page scratch, movff-only — PROD was REJECTED
; here: it is live across the 19e6 volume chain's 2abc->297e math hand-off,
; the session-0 runtime failure; the ISR touches none of these); EE mode
; additionally clobbers ram_0x003/004 and forces BSR=0, matching the
; eeprom_read_byte_at_w call runs it replaces.
; STATUS is NOT preserved (unlike raw movff runs) — every converted site was
; audited: no following instruction consumes pre-chain flags.
; 0xFF is a safe sentinel: no converted descriptor copies cell 0xXFF.
; ---------------------------------------------------------------------------
chain_copy:
    movff       TOSL, TBLPTRL
    movff       TOSH, TBLPTRH
    clrf        TBLPTRU, ACCESS             ; all callers live below 0x4C00
    tblrd*+
    movff       TABLAT, chain_copy_srch_b3_phys ; src page (bank3 via movff)
    tblrd*+
    movff       TABLAT, chain_copy_dsth_b3_phys ; dst page
    movlb       0x03                        ; block counters live in bank 3
chain_copy__read_next_block_or_finish:
    tblrd*+
    incfsz      TABLAT, W, ACCESS           ; srcL == 0xFF -> done
    bra         chain_copy__load_block_header
    btfsc       TBLPTRL, 0, ACCESS          ; odd resume PC -> consume the pad
    tblrd*+
    movlb       0x00                        ; uniform exit contract: BSR = 0
    movf        TBLPTRL, W, ACCESS          ; movff may not target TOSx
    movwf       TOSL, ACCESS
    movf        TBLPTRH, W, ACCESS
    movwf       TOSH, ACCESS
    return      0
chain_copy__load_block_header:
    movff       TABLAT, chain_copy_srcl_b3_phys ; block source low byte
    tblrd*+
    movff       TABLAT, chain_copy_dstl_b3_phys ; block destination low byte
    tblrd*+
    movff       TABLAT, chain_copy_cnt_b3_phys  ; block length (>= 1)
chain_copy__copy_next_byte:
    movf        chain_copy_srch_b3, W, BANKED
    xorlw       0xEE                        ; EEPROM-source descriptor?
    bnz         chain_copy__read_ram_source_byte
    movf        chain_copy_srcl_b3, W, BANKED ; W = EEPROM address
    call        eeprom_read_byte_at_w, 0x0     ; W = value; BSR = 0 on return
    movlb       0x03                        ; back to the counter bank
    bra         chain_copy__store_byte_and_advance
chain_copy__read_ram_source_byte:
    movff       chain_copy_srcl_b3_phys, FSR0L
    movff       chain_copy_srch_b3_phys, FSR0H
    movf        INDF0, W, ACCESS
chain_copy__store_byte_and_advance:
    movff       chain_copy_dstl_b3_phys, FSR0L
    movff       chain_copy_dsth_b3_phys, FSR0H
    movwf       INDF0, ACCESS
    incf        chain_copy_srcl_b3, F, BANKED
    incf        chain_copy_dstl_b3, F, BANKED
    decfsz      chain_copy_cnt_b3, F, BANKED
    bra         chain_copy__copy_next_byte
    bra         chain_copy__read_next_block_or_finish

; copy_transform_shadow_to_math_operand — shared stock_02F..032 -> stock_025..028 operand staging
; (size S3 dedup; W/STATUS-dead at both callers, audited).
copy_transform_shadow_to_math_operand:
    rcall       chain_copy          ; size T94: table-driven copy run
    db          0x00, 0x00, float32_transform_shadow_dword_op, float32_math_operand_byte0_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    return      0

; ---------------------------------------------------------------------------
; Helper: wake_rebroadcast_downstream      (blocking B0/03/01 emit)
; ---------------------------------------------------------------------------
; Shared by run_wake_rail_gate_and_dsp_cold_init's entry (round-2 parallel wake: downstream MAIN
; gates concurrently with ours) and exit (Bug #45 H2 backstop).  Blocking,
; ~1 ms for 3 bytes at 31,250 baud; callers run with the UART still
; configured (entry: pre-quiesce; exit: post TX-only re-arm).
; ---------------------------------------------------------------------------
wake_rebroadcast_downstream:
    movlw       0xB0
    rcall       uart_tx_byte_blocking_call_range_trampoline
    movlw       0x03
    rcall       uart_tx_byte_blocking_call_range_trampoline
    movlw       0x01
    bra         uart_tx_byte_blocking_call_range_trampoline ; tail-call return

; ---------------------------------------------------------------------------
; Function: run_wake_rail_gate_and_dsp_cold_init                  (rail-rise wait + DSP cold init)
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
;     then run preset_replay_selected_table_blocking (preset table apply)
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
run_wake_rail_gate_and_dsp_cold_init:
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
    clrf        adc_rail_sample_lo_b0, BANKED
    clrf        adc_rail_sample_hi_b0, BANKED
    bsf         ADCON0, 1, ACCESS
    ; Bug #45 §C: bound the rail-rise wait at ~50 iters * 10 ms = ~500 ms so a
    ; depressed AN0 (e.g. asymmetric shared-rail coupling on a two-MAIN chain)
    ; cannot pin this MAIN inside the polling loop indefinitely.  ram_0x008 is
    ; ACCESS BANK scratch -- safe for the gate scope: the only call inside the
    ; loop is timer3_blocking_delay_ms_from_w which uses ram_0x003/0x004 for its
    ; own countdown.
    movlw       0x32
    movwf       flash_end_high_or_loop_mask_scratch_byte, ACCESS
adc_boot_gate__poll_an0_rail_ready:
    movlw       0x0A
    rcall       timer3_blocking_delay_ms_from_w_trampoline ; W04-E08 factored (10 ms poll)
    btfsc       ADCON0, 1, ACCESS
    bra         adc_boot_gate__check_rail_threshold
    movf        ADRESH, W, ACCESS
    movwf       adc_boot_gate_sample_hi_acc, ACCESS
    clrf        adc_boot_gate_sample_lo_acc, ACCESS
    movf        ADRESL, W, ACCESS
    addwf       adc_boot_gate_sample_lo_acc, W, ACCESS
    movlb       0x0
    movwf       adc_rail_sample_lo_b0, BANKED
    movlw       0x00
    addwfc      adc_boot_gate_sample_hi_acc, W, ACCESS
    movwf       adc_rail_sample_hi_b0, BANKED
    bsf         ADCON0, 1, ACCESS
adc_boot_gate__check_rail_threshold:
    movlw       0x36
    call        compare_adc_rail_sample_to_threshold_w, 0x0
    bc          adc_boot_gate__start_dsp_cold_init
    decfsz      flash_end_high_or_loop_mask_scratch_byte, F, ACCESS
    bra         adc_boot_gate__poll_an0_rail_ready
    ; Counter exhausted -- proceed with bring-up despite low rail.  If the
    ; rail is still genuinely bad, downstream supplies will collapse and BOR
    ; will fire a fresh cold boot; either is preferable to wedging silently
    ; inside the loop with no CPU activity visible to the chain.
adc_boot_gate__start_dsp_cold_init:
    movlw       0x46
    rcall       timer3_blocking_delay_ms_from_w_trampoline ; W04-E08 factored (~70 ms)
    call        program_uart_31250_baud_common, 0x0
    bcf         LATB, 4, ACCESS
    bcf         LATA, 6, ACCESS
    bcf         LATB, 3, ACCESS
    bcf         SSPCON1, 5, ACCESS
    bsf         TRISB, 1, ACCESS
    bsf         TRISB, 0, ACCESS
    movlw       0x64
    rcall       timer3_blocking_delay_ms_from_w_trampoline ; W04-E08 factored (100 ms)
    bsf         LATB, 4, ACCESS
    movlw       0x05
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movlw       0xDC
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    call        timer3_blocking_delay, 0x0
    bsf         TRISB, 1, ACCESS
    bsf         TRISB, 0, ACCESS
    movlw       0x01
    rcall       timer3_blocking_delay_ms_from_w_trampoline ; W04-E08 factored (1 ms)
    call        mssp_hard_reset_smp_master, 0x0
    bsf         LATA, 6, ACCESS
    rcall       tas3108_write_zero_volume_coeff_mid_window  ; W03-E02: factored 5-line pattern
    movlb       0x0
    bsf         event_flags_b0, 4, BANKED
    bsf         active_flags_acc, 7, ACCESS
    movlw       0x00
    call        cmd_dispatch_gated, 0x0
adc_boot_gate__enable_amp_and_probe_i2c:
    bsf         LATB, 3, ACCESS
    call        timer3_blocking_delay_2ms, 0x0
    rcall       wake_i2c_barrier_attempt
    bc          adc_boot_gate__mark_i2c_barrier_pending
    bsf         event_flags_b0, 1, BANKED
    bra         adc_boot_gate__resume_uart_and_rebroadcast_wake
adc_boot_gate__mark_i2c_barrier_pending:
    call        field10_mark_fault_mute, 0x0
    bsf         main_runtime_latch_flags_b0, 6, BANKED       ; FIELD-10 barrier_pending
adc_boot_gate__resume_uart_and_rebroadcast_wake:
    call        timer3_blocking_delay_2ms, 0x0
    call        uart_wake_reconfigure_tx_only_and_resync_parser, 0x0
    ; Bug #45 H2: re-emit B0/03/01 broadcast post-gate.  The parser's
    ; chain-echo at _1e6c forwards the WAKE data byte BEFORE this MAIN
    ; enters run_wake_rail_gate_and_dsp_cold_init, but the call to uart_quiesce_for_wake at
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
    ; FIELD-8: a preset request accepted while asleep parks only
    ; preset_job_target; standby cancellation has cleared the job state.
    ; Re-arm after wake hardware is back, before status/volume refresh.
    movlb       0x2
    call        preset_target_compare_active_bsr2, 0x0
    bz          adc_boot_gate__skip_pending_preset_rearm
    movlw       0x01
    movwf       preset_job_state_b2, BANKED
adc_boot_gate__skip_pending_preset_rearm:
    movlb       0x0
    bsf         event_flags_b0, 3, BANKED
    bsf         dsp_fault_flags_b0, 0, BANKED
    bsf         dsp_fault_flags_b0, 1, BANKED
    movlw       0x00
    call        cmd_dispatch_gated, 0x0
    call        send_status_burst, 0x0
    bcf         INTCON, 5, ACCESS
    bcf         T0CON, 7, ACCESS
    movlw       0xA4
    movwf       TMR0H, ACCESS
    movlw       0x71
    movwf       TMR0L, ACCESS
    movlb       0x0
    clrf        an0_delay_b0, BANKED
    bcf         main_runtime_latch_flags_b0, 2, BANKED
    call        uart_reconfigure_and_resync_parser, 0x0
    bsf         PIE1, 5, ACCESS
    bsf         INTCON, 7, ACCESS
    goto        usb_reinit_after_wake__clear_pending_and_poll_host

timer3_blocking_delay_ms_from_w_trampoline:
    goto        timer3_blocking_delay_ms_from_w

; ---------------------------------------------------------------------------
; Function: flash_write                    (program-memory write w/ A/B remap)
; Address : 0x2E6E
; ---------------------------------------------------------------------------
; Stock body (flash_write_without_preset_remap) is the original Hypex 64-byte tblwt loop:
;   • input: ram_0x003..006 = byte-address (24-bit + zero MSB)
;            ram_0x007:008  = byte-length (16-bit countdown)
;            FSR2 (ram_0x009:00A) = source byte pointer
;   • aligns the start to a 32-byte block (right-shift 5, add 0x20, recover),
;     then for each block copies up to 32 bytes via TBLWT*, sets EECON1 for
;     program memory write (EEPGD=1, CFGS=0, WREN=1), runs the
;     unlock-then-WR sequence in nvm_unlock_and_set_wr, and reloads the
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
; Helper: flash_remap_preset_b_start_address_if_active (W05)
; Shared preset-B start-address remap for flash_read / flash_write /
; flash_erase.  When active_flags.bit2 is set and ram_0x003:006 points
; into logical preset-A flash 0x56xx..0x5Fxx, subtract 0x0A from
; ram_0x004 so the operation lands in the physical preset-B table at
; 0x4Cxx..0x55xx.  The _if_b entry is for callers that have already tested
; active_flags.bit2 and still need to continue into a second endpoint check.
; ---------------------------------------------------------------------------
flash_remap_preset_b_start_address_if_active:
    btfss       active_flags_acc, 2, ACCESS
    return      0
flash_remap_preset_b_start_address:
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    iorwf       length_mask_or_divisor_low_scratch_byte, W, ACCESS
    bnz         flash_remap_preset_b_start_address__return
    movlw       0x56
    subwf       addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    bnc         flash_remap_preset_b_start_address__return
    movlw       0x60
    subwf       addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    bc          flash_remap_preset_b_start_address__return
    movlw       0x0A
    subwf       addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
flash_remap_preset_b_start_address__return:
    return      0

flash_write:
    rcall       flash_remap_preset_b_start_address_if_active
flash_write_without_preset_remap:
    clrf        flash_gie_or_float_sign_scratch_byte, ACCESS
    rcall       chain_copy          ; size T96: table-driven copy run
    db          0x00, 0x00, addr_low_counter_or_payload_scratch_operand, flash_write_start_addr_shadow_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movlw       0x05
    movwf       eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, ACCESS
flash_write__shift_start_addr_to_block_index:
    rcall       shift_003_006_right_clear_c
    decfsz      eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, F, ACCESS
    bra         flash_write__shift_start_addr_to_block_index
    movlw       0x05
flash_write__restore_block_base_from_index:
    rcall       shift_scratch32_left_clear_carry
    decfsz      WREG, F, ACCESS
    bra         flash_write__restore_block_base_from_index
    movlw       0x20
    addwf       addr_low_counter_or_payload_scratch_byte, F, ACCESS
    rcall       propagate_carry_to_u32_scratch_high24
    movf        route_base_or_flash_addr_low_scratch_byte, W, ACCESS
    subwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    movwf       flash_block_or_uart_byte_scratch_byte, ACCESS
    bra         flash_write__check_remaining_byte_count
flash_write_stage_block_cursor_shadow:
    movff       flash_addr_shadow_upper_or_preset_job_index_or_init_copy_end_phys, eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys
    movff       float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys, fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys
    movff       flash_addr_shadow_low_or_preset_table_addr_hi_phys, flash_addr_low_or_float32_scale_or_flash_read_tblptru_save_phys
    return      0

shift_scratch32_left_clear_carry:
    bcf         STATUS, 0, ACCESS
    rlcf        addr_low_counter_or_payload_scratch_byte, F, ACCESS
    rlcf        addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    rlcf        length_mask_or_divisor_low_scratch_byte, F, ACCESS
    rlcf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    return      0

propagate_carry_to_u32_scratch_high24:
    movlw       0x00
    addwfc      addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    addwfc      length_mask_or_divisor_low_scratch_byte, F, ACCESS
    addwfc      status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    return      0
flash_write__start_next_block:
    rcall       flash_write_stage_block_cursor_shadow
    bra         flash_write__test_block_bytes_remaining
flash_write__copy_next_source_byte:
    movff       eeprom_or_filename_data_or_flash_buffer_ptr_low_or_signature_low_phys, FSR2L
    movff       eeprom_mask_or_flash_src_high_scratch_phys, FSR2H
    movf        INDF2, W, ACCESS
    movff       flash_addr_low_or_float32_scale_or_flash_read_tblptru_save_phys, TBLPTRL
    movff       fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys, TBLPTRH
    movff       eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys, TBLPTRU
    movwf       TABLAT, ACCESS
    tblwt*
    infsnz      flash_src_low_or_rx_length_scratch_byte, F, ACCESS
    incf        eeprom_mask_or_flash_src_high_scratch_byte, F, ACCESS
    incf        float_loop_or_tblptr_low_scratch_byte, F, ACCESS
    movlw       0x00
    addwfc      float_divisor_or_preset_flag_scratch_byte, F, ACCESS
    addwfc      route_bit_or_tblptr_upper_scratch_byte, F, ACCESS
    decf        count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        flash_end_high_or_loop_mask_scratch_byte, F, ACCESS
    movf        flash_end_high_or_loop_mask_scratch_byte, W, ACCESS
    iorwf       count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    bz          flash_write__prepare_block_commit
flash_write__test_block_bytes_remaining:
    decf        flash_block_or_uart_byte_scratch_byte, F, ACCESS
    incf        flash_block_or_uart_byte_scratch_byte, W, ACCESS
    bnz         flash_write__copy_next_source_byte
flash_write__prepare_block_commit:
    movff       eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys, flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys
    movff       fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys, flash_saved_tblptrh_phys
    movff       flash_addr_low_or_float32_scale_or_flash_read_tblptru_save_phys, timeout_hi_b0_phys
    rcall       flash_write_stage_block_cursor_shadow
    bsf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    btfss       INTCON, 7, ACCESS
    bra         flash_write__unlock_and_clear_wren
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       flash_gie_or_float_sign_scratch_byte, ACCESS
flash_write__unlock_and_clear_wren:
    call        nvm_unlock_and_set_wr, 0x0
    bcf         EECON1, 2, ACCESS
    movf        flash_gie_or_float_sign_scratch_byte, W, ACCESS
    bz          flash_write__reload_next_block_cursor
    bsf         INTCON, 7, ACCESS
    clrf        flash_gie_or_float_sign_scratch_byte, ACCESS
flash_write__reload_next_block_cursor:
    movlw       0x20
    movwf       flash_block_or_uart_byte_scratch_byte, ACCESS
    movf        uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, W, ACCESS
    movwf       route_base_or_flash_addr_low_scratch_byte, ACCESS
    movf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, W, ACCESS
    movwf       float_shift_flash_addr_or_preset_index_scratch_byte, ACCESS
    movf        flash_upper_or_uart_count_scratch_byte, W, ACCESS
    movwf       float_product_flash_addr_or_preset_index_scratch_byte, ACCESS
    clrf        float_product_or_output_index_scratch_byte, ACCESS
flash_write__check_remaining_byte_count:
    movf        flash_end_high_or_loop_mask_scratch_byte, W, ACCESS
    iorwf       count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         flash_write__start_next_block


; ---------------------------------------------------------------------------
; Function: usb_sie_endpoint_pump
; Address : 0x2F4E
; Notes   : Inferred usb helper; touches usb. Calls: usb_poll_host_presence_reinit_or_shutdown, usb_clear_activity_interrupt_after_settle, usb_bus_reset_reinitialize.
; ---------------------------------------------------------------------------
usb_sie_endpoint_pump:
    call        usb_poll_host_presence_reinit_or_shutdown, 0x0
    tstfsz      usb_device_state_b0, BANKED
    bra         usb_sie_endpoint_pump__service_enabled_state
    bra         usb_sie_endpoint_pump__return
usb_sie_endpoint_pump__service_enabled_state:
    btfsc       UIR, 2, ACCESS
    call        usb_clear_activity_interrupt_after_settle, 0x0
    btfsc       UCON, 1, ACCESS
    bra         usb_sie_endpoint_pump__return
    btfsc       UIR, 0, ACCESS
    call        usb_bus_reset_reinitialize, 0x0
    btfss       UIR, 4, ACCESS
    bra         usb_sie_endpoint_pump__idle_interrupt_done
    movff       UIE, usb_uie_saved_mask_phys
    movlw       0x04
    movwf       UIE, ACCESS
    bcf         UIR, 4, ACCESS
    bsf         UCON, 1, ACCESS
    bcf         PIR2, 5, ACCESS
    bsf         PIE2, 5, ACCESS
    bcf         PIE2, 5, ACCESS
    movlb       0x0
    movf        usb_uie_saved_mask_b0, W, BANKED
    iorwf       UIE, F, ACCESS
usb_sie_endpoint_pump__idle_interrupt_done:
    movlw       0x03
    movlb       0x0
    subwf       usb_device_state_b0, W, BANKED
    bnc         usb_sie_endpoint_pump__return
    clrf        usb_transaction_service_pass_count_b0, BANKED
usb_sie_endpoint_pump__poll_transaction_flag:
    btfss       UIR, 3, ACCESS
    bra         usb_sie_endpoint_pump__return
    movf        USTAT, W, ACCESS
    movff       USTAT, status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys
    movlw       0x7C
    andwf       status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    bnz         usb_sie_endpoint_pump__service_ep0_in_token_if_selected
    movlw       0x04
    movwf       usb_selected_bdt_entry_ptr_hi_b0, BANKED
    btfss       USTAT, 1, ACCESS
    movlw       0x00
usb_sie_endpoint_pump__select_ep0_out_bd:
    movwf       usb_selected_bdt_entry_ptr_lo_b0, BANKED
    bcf         UIR, 3, ACCESS
    movff       usb_selected_bdt_entry_ptr_lo_phys, FSR2L
    movff       usb_selected_bdt_entry_ptr_hi_phys, FSR2H
    rrcf        INDF2, W, ACCESS
    rrcf        WREG, F, ACCESS
    andlw       0x0F
    xorlw       0x0D
    bnz         usb_sie_endpoint_pump__advance_transaction_scan
    clrf        usb_setup_copy_index_b0, BANKED
usb_sie_endpoint_pump__copy_setup_packet_byte:
    rcall       usb_setup_fsr2_from_selected_bdt_entry_ptr
    movff       POSTINC2, status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys
    movff       POSTDEC2, computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys
    movff       status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys, FSR2L
    movff       computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys, FSR2H
    movf        usb_setup_copy_index_b0, W, BANKED
    addlw       0xCF
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movff       INDF2, INDF1
    rcall       usb_setup_fsr2_from_selected_bdt_entry_ptr
    incf        POSTINC2, F, ACCESS
    movlw       0x00
    addwfc      POSTDEC2, F, ACCESS
    incf        usb_setup_copy_index_b0, F, BANKED
    movlw       0x07
    cpfsgt      usb_setup_copy_index_b0, BANKED
    bra         usb_sie_endpoint_pump__copy_setup_packet_byte
    call        usb_ep0_service_setup_transaction, 0x0
    bra         usb_sie_endpoint_pump__advance_transaction_scan
usb_setup_fsr2_from_selected_bdt_entry_ptr:
    lfsr        FSR2, isr_save_fsr2h_b0_phys
    movf        usb_selected_bdt_entry_ptr_lo_b0, W, BANKED
    addwf       FSR2L, F, ACCESS
    movf        usb_selected_bdt_entry_ptr_hi_b0, W, BANKED
    addwfc      FSR2H, F, ACCESS
    return      0
usb_sie_endpoint_pump__service_ep0_in_token_if_selected:
    movf        USTAT, W, ACCESS
    xorlw       0x04
    bcf         UIR, 3, ACCESS
    bnz         usb_sie_endpoint_pump__advance_transaction_scan
    call        usb_ep0_service_in_transaction, 0x0
usb_sie_endpoint_pump__advance_transaction_scan:
    movlb       0x0
    incf        usb_transaction_service_pass_count_b0, F, BANKED
    movlw       0x03
    cpfsgt      usb_transaction_service_pass_count_b0, BANKED
    bra         usb_sie_endpoint_pump__poll_transaction_flag
usb_sie_endpoint_pump__return:
    return      0


; ---------------------------------------------------------------------------
; Function: float32_to_int32_in_place
; Address : 0x301A
; Notes   : Inferred core helper routine. Calls: main_core_service_30cc.
; ---------------------------------------------------------------------------
; copy_math_operand_to_secondary_shadow — shared stock_025..028 -> stock_029..02C operand copy
; (size S3 dedup; W/STATUS-dead at both callers, audited).
copy_math_operand_to_secondary_shadow:
    rcall       copy_math_operand_low24_to_secondary
    movff       float32_math_operand_byte3_b0_phys, float32_secondary_work_byte3_b0_phys
    return      0

shift_029_02c_right_w_minus_one__rotate_next_bit:
    bcf         STATUS, 0, ACCESS
    rrcf        float32_secondary_work_byte3_acc, F, ACCESS
    rrcf        float32_secondary_work_byte2_acc, F, ACCESS
    rrcf        float32_secondary_work_byte1_acc, F, ACCESS
    rrcf        float32_secondary_work_byte0_acc, F, ACCESS
shift_029_02c_right_w_minus_one:
shift_029_02c_right_w_minus_one__check_remaining:
    decfsz      WREG, F, ACCESS
    bra         shift_029_02c_right_w_minus_one__rotate_next_bit
    return      0

float32_to_int32_in_place:
    rcall       copy_math_operand_to_secondary_shadow           ; size S3
    movlw       0x18
    rcall       shift_029_02c_right_w_minus_one
    movf        float32_secondary_work_byte0_acc, W, ACCESS
    movwf       float32_exponent_work_acc, ACCESS
    tstfsz      float32_exponent_work_acc, ACCESS
    bra         float32_to_int32_in_place__unpack_sign_and_mantissa
float32_to_int32_in_place__clear_zero_or_out_of_range:
    clrf        float32_math_operand_byte0_acc, ACCESS
    clrf        float32_math_operand_byte1_acc, ACCESS
    clrf        float32_math_operand_byte2_acc, ACCESS
    clrf        float32_math_operand_byte3_acc, ACCESS
    bra         float32_to_int32_in_place__return
float32_to_int32_in_place__unpack_sign_and_mantissa:
    rcall       copy_math_operand_to_secondary_shadow           ; size S3
    movlw       0x20
    rcall       shift_029_02c_right_w_minus_one
    movf        float32_secondary_work_byte0_acc, W, ACCESS
    movwf       float32_sign_exponent_offset_scratch_acc, ACCESS
    bsf         float32_math_operand_byte2_acc, 7, ACCESS
    clrf        float32_math_operand_byte3_acc, ACCESS
    movlw       0x96
    subwf       float32_exponent_work_acc, F, ACCESS
    btfss       float32_exponent_work_acc, 7, ACCESS
    bra         float32_to_int32_in_place__check_left_shift_range
    movf        float32_exponent_work_acc, W, ACCESS
    xorlw       0x80
    movwf       float32_secondary_work_byte0_acc, ACCESS
    movlw       0xE9
    xorlw       0x80
    subwf       float32_secondary_work_byte0_acc, W, ACCESS
    bnc         float32_to_int32_in_place__clear_zero_or_out_of_range
float32_to_int32_in_place__shift_right_until_exponent_zero:
    bcf         STATUS, 0, ACCESS
    rrcf        float32_math_operand_byte3_acc, F, ACCESS
    rrcf        float32_math_operand_byte2_acc, F, ACCESS
    rrcf        float32_math_operand_byte1_acc, F, ACCESS
    rrcf        float32_math_operand_byte0_acc, F, ACCESS
    incfsz      float32_exponent_work_acc, F, ACCESS
    bra         float32_to_int32_in_place__shift_right_until_exponent_zero
    bra         float32_to_int32_in_place__apply_sign_if_needed
float32_to_int32_in_place__check_left_shift_range:
    movlw       0x1F
    cpfsgt      float32_exponent_work_acc, ACCESS
    bra         float32_to_int32_in_place__shift_left_until_exponent_zero
    bra         float32_to_int32_in_place__clear_zero_or_out_of_range
float32_to_int32_in_place__shift_left_next_bit:
    bcf         STATUS, 0, ACCESS
    rlcf        float32_math_operand_byte0_acc, F, ACCESS
    rlcf        float32_math_operand_byte1_acc, F, ACCESS
    rlcf        float32_math_operand_byte2_acc, F, ACCESS
    rlcf        float32_math_operand_byte3_acc, F, ACCESS
    decf        float32_exponent_work_acc, F, ACCESS
float32_to_int32_in_place__shift_left_until_exponent_zero:
    tstfsz      float32_exponent_work_acc, ACCESS
    bra         float32_to_int32_in_place__shift_left_next_bit
float32_to_int32_in_place__apply_sign_if_needed:
    movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS
    bz          float32_to_int32_in_place__positive_result_ready
    comf        float32_math_operand_byte3_acc, F, ACCESS
    comf        float32_math_operand_byte2_acc, F, ACCESS
    comf        float32_math_operand_byte1_acc, F, ACCESS
    negf        float32_math_operand_byte0_acc, ACCESS
    movlw       0x00
    addwfc      float32_math_operand_byte1_acc, F, ACCESS
    addwfc      float32_math_operand_byte2_acc, F, ACCESS
    addwfc      float32_math_operand_byte3_acc, F, ACCESS
float32_to_int32_in_place__positive_result_ready:
float32_to_int32_in_place__return:
    return      0


; ---------------------------------------------------------------------------
; Function: float32_pack_mantissa_exponent_sign
; Address : 0x30D8
; Notes   : Inferred core helper routine. Calls: shift_003_006_right_clear_c.
; ---------------------------------------------------------------------------
float32_pack_mantissa_exponent_sign:
    movf        count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    bz          float32_pack_mantissa_exponent_sign__clear_zero_result
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    iorwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    iorwf       addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    iorwf       length_mask_or_divisor_low_scratch_byte, W, ACCESS
    bnz         float32_pack_mantissa_exponent_sign__trim_high_guard_bits
float32_pack_mantissa_exponent_sign__clear_zero_result:
    clrf        addr_low_counter_or_payload_scratch_byte, ACCESS
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    clrf        length_mask_or_divisor_low_scratch_byte, ACCESS
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    bra         float32_pack_mantissa_exponent_sign__return
float32_pack_mantissa_exponent_sign__shift_right_increment_exponent:
    incf        count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS
    rcall       shift_003_006_right_clear_c
float32_pack_mantissa_exponent_sign__trim_high_guard_bits:
    movlw       0xFE
    andwf       status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    bz          float32_pack_mantissa_exponent_sign__check_guard_byte
    bra         float32_pack_mantissa_exponent_sign__shift_right_increment_exponent
float32_pack_mantissa_exponent_sign__round_guard_and_shift_right:
    incf        count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS
    incf        addr_low_counter_or_payload_scratch_byte, F, ACCESS
    rcall       propagate_carry_to_u32_scratch_high24
    rcall       shift_003_006_right_clear_c
float32_pack_mantissa_exponent_sign__check_guard_byte:
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    bz          float32_pack_mantissa_exponent_sign__normalize_left_to_mantissa_msb
    bra         float32_pack_mantissa_exponent_sign__round_guard_and_shift_right
float32_pack_mantissa_exponent_sign__shift_left_decrement_exponent:
    decf        count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS
    rcall       shift_scratch32_left_clear_carry
float32_pack_mantissa_exponent_sign__normalize_left_to_mantissa_msb:
    btfss       length_mask_or_divisor_low_scratch_byte, 7, ACCESS
    bra         float32_pack_mantissa_exponent_sign__shift_left_decrement_exponent
    btfsc       count_flash_page_or_i2c_payload_scratch_byte, 0, ACCESS
    bra         float32_pack_mantissa_exponent_sign__merge_exponent_and_sign_bits
    movlw       0x7F
    andwf       length_mask_or_divisor_low_scratch_byte, F, ACCESS
float32_pack_mantissa_exponent_sign__merge_exponent_and_sign_bits:
    bcf         STATUS, 0, ACCESS
    rrcf        count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS
    movf        count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    iorwf       status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    clrf        flash_src_low_or_rx_length_scratch_byte, ACCESS
    clrf        eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    clrf        eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, ACCESS
    clrf        uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, ACCESS
    tstfsz      flash_end_high_or_loop_mask_scratch_byte, ACCESS
    bsf         status_addr_high_or_i2c_payload_scratch_byte, 7, ACCESS
float32_pack_mantissa_exponent_sign__return:
    return      0

; ---------------------------------------------------------------------------
; Helper: float32_pack_mantissa_exponent_sign_and_save          (W04-E01)
;
; Factor of the rcall/call float32_pack_mantissa_exponent_sign + 4-movff save tail that
; appeared inline at three sites. Callers bra/goto here to avoid duplicating
; the 18-byte cleanup sequence.
; ---------------------------------------------------------------------------
float32_pack_mantissa_exponent_sign_and_save:
    rcall       float32_pack_mantissa_exponent_sign
    rcall       chain_copy          ; size T150: 30d8 result save tail
    db          0x00, 0x00, addr_low_counter_or_payload_scratch_operand, float32_coeff_or_volume_work_operand_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    return      0


; ---------------------------------------------------------------------------
; Function: shift_003_006_right_clear_c
; Address : 0x3188
; Notes   : Inferred core helper routine. Calls: main_core_service_496c, usb_ep0_arm_out_pingpong_bd.
; ---------------------------------------------------------------------------
shift_003_006_right_clear_c:
    bcf         STATUS, 0, ACCESS
    rrcf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    rrcf        length_mask_or_divisor_low_scratch_byte, F, ACCESS
    rrcf        addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    rrcf        addr_low_counter_or_payload_scratch_byte, F, ACCESS
    return      0
usb_ep0_dispatch_hid_setup_request:
    movf        usb_setup_bm_request_type_b0, W, BANKED
    andlw       0x1F
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    decf        addr_low_counter_or_payload_scratch_byte, W, ACCESS
    bnz         usb_ep0_dispatch_hid_setup_request__return
    movf        usb_setup_w_index_lo_b0, W, BANKED
    bnz         usb_ep0_dispatch_hid_setup_request__return
    movf        usb_setup_b_request_b0, W, BANKED
    xorlw       0x06
    bz          usb_ep0_dispatch_hid_setup_request__decode_get_descriptor_type
    bra         usb_ep0_dispatch_hid_setup_request__decode_class_request_type
usb_ep0_dispatch_hid_setup_request__stage_hid_descriptor:
    movlw       0x02
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movlw       HIGH(usb_hid_descriptor)
    movwf       usb_ep0_in_source_ptr_hi_b0, BANKED
    movlw       LOW(usb_hid_descriptor)
    movwf       usb_ep0_in_source_ptr_lo_b0, BANKED
    clrf        usb_ep0_transfer_remaining_hi_b0, BANKED
    movlw       0x09
    bra         usb_ep0_dispatch_hid_setup_request__store_descriptor_length
usb_ep0_dispatch_hid_setup_request__handle_report_descriptor_request:
    movlw       0x02
    movwf       usb_ep0_control_response_mode_b0, BANKED
    decf        usb_current_configuration_b0, W, BANKED
    bnz         usb_ep0_dispatch_hid_setup_request__maybe_set_report_descriptor_length
    movlw       HIGH(usb_hid_report_descriptor)
    movwf       usb_ep0_in_source_ptr_hi_b0, BANKED
    movlw       LOW(usb_hid_report_descriptor)
    movwf       usb_ep0_in_source_ptr_lo_b0, BANKED
usb_ep0_dispatch_hid_setup_request__maybe_set_report_descriptor_length:
    decf        usb_current_configuration_b0, W, BANKED
    bnz         usb_ep0_dispatch_hid_setup_request__set_table_source_flag
    clrf        usb_ep0_transfer_remaining_hi_b0, BANKED
    movlw       0x1D
usb_ep0_dispatch_hid_setup_request__store_descriptor_length:
    movwf       usb_ep0_transfer_remaining_lo_b0, BANKED
    bra         usb_ep0_dispatch_hid_setup_request__set_table_source_flag
usb_ep0_dispatch_hid_setup_request__decode_get_descriptor_type:
    movf        usb_setup_w_value_hi_b0, W, BANKED
    xorlw       0x21
    bz          usb_ep0_dispatch_hid_setup_request__stage_hid_descriptor
    xorlw       0x03
    bz          usb_ep0_dispatch_hid_setup_request__handle_report_descriptor_request
    xorlw       0x01
usb_ep0_dispatch_hid_setup_request__set_table_source_flag:
    bsf         usb_ep0_control_flags_b0, 1, BANKED
usb_ep0_dispatch_hid_setup_request__decode_class_request_type:
    swapf       usb_setup_bm_request_type_b0, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    decf        addr_low_counter_or_payload_scratch_byte, W, ACCESS
    bnz         usb_ep0_dispatch_hid_setup_request__return
    bra         usb_ep0_dispatch_hid_setup_request__decode_class_request_code
usb_ep0_dispatch_hid_setup_request__stage_get_idle_reply:
    movlw       0x02
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movlw       0xEA
    bra         usb_ep0_stage_one_byte_lowpage_in_data_pointer
usb_ep0_dispatch_hid_setup_request__store_set_idle_duration:
    movlw       0x02
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movff       usb_setup_w_value_hi_phys, usb_hid_idle_duration_phys
    bra         usb_ep0_dispatch_hid_setup_request__return
usb_ep0_dispatch_hid_setup_request__stage_get_protocol_reply:
    movlw       0x02
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movlw       0xE9
    bra         usb_ep0_stage_one_byte_lowpage_in_data_pointer
usb_ep0_dispatch_hid_setup_request__store_set_protocol_value:
    movlw       0x02
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movff       usb_setup_w_value_lo_phys, usb_hid_protocol_setting_phys
    bra         usb_ep0_dispatch_hid_setup_request__return
usb_ep0_dispatch_hid_setup_request__decode_class_request_code:
    movf        usb_setup_b_request_b0, W, BANKED
    xorlw       0x01
    bz          usb_ep0_dispatch_hid_setup_request__return
    xorlw       0x03
    bz          usb_ep0_dispatch_hid_setup_request__stage_get_idle_reply
    xorlw       0x01
    bz          usb_ep0_dispatch_hid_setup_request__stage_get_protocol_reply
    xorlw       0x0A
    bz          usb_ep0_dispatch_hid_setup_request__return
    xorlw       0x03
    bz          usb_ep0_dispatch_hid_setup_request__store_set_idle_duration
    xorlw       0x01
    bz          usb_ep0_dispatch_hid_setup_request__store_set_protocol_value
usb_ep0_dispatch_hid_setup_request__return:
    return      0
usb_ep0_stage_one_byte_lowpage_in_data_pointer:
    clrf        usb_ep0_in_source_ptr_hi_b0, BANKED
    movwf       usb_ep0_in_source_ptr_lo_b0, BANKED
usb_ep0_mark_one_byte_lowpage_in_data_ready:
    bcf         usb_ep0_control_flags_b0, 1, BANKED
    movlw       0x01
    movwf       usb_ep0_transfer_remaining_lo_b0, BANKED
    return      0
usb_ep0_arm_next_out_pingpong_bd:
    decf        usb_ep0_out_next_bd_toggle_b0, W, BANKED
    bnz         usb_ep0_arm_next_out_pingpong_bd__arm_even_bd
    movlw       0x01
    rcall       usb_ep0_arm_out_pingpong_bd_window
    clrf        usb_ep0_out_next_bd_toggle_b0, BANKED
    return      0
usb_ep0_arm_next_out_pingpong_bd__arm_even_bd:
    movlw       0x00
    rcall       usb_ep0_arm_out_pingpong_bd_window
    movlw       0x01
    movwf       usb_ep0_out_next_bd_toggle_b0, BANKED
    return      0

usb_ep0_arm_out_pingpong_bd_window:
    goto        usb_ep0_arm_out_pingpong_bd

usb_ep0_arm_control_transfer_response:
    tstfsz      usb_ep0_control_response_mode_b0, BANKED
    bra         usb_ep0_arm_control_transfer_response__dispatch_by_direction
    movlw       0x04
    movlb       0x4
    movwf       usb_ep0_in_bd_status_b4, BANKED
    bsf         usb_ep0_in_bd_status_b4, 7, BANKED
    rcall       usb_stage_bdt_template_status_w
    rcall       usb_ep0_arm_next_out_pingpong_bd
    bra         usb_ep0_arm_control_transfer_response__return
usb_ep0_arm_control_transfer_response__dispatch_by_direction:
    btfss       usb_setup_bm_request_type_b0, 7, BANKED
    bra         usb_ep0_arm_control_transfer_response__handle_host_to_device_stage
    movlw       0x01
    movwf       usb_ep0_control_transfer_phase_b0, BANKED
    movf        usb_ep0_transfer_remaining_lo_b0, W, BANKED
    subwf       usb_setup_w_length_lo_b0, W, BANKED
    movf        usb_ep0_transfer_remaining_hi_b0, W, BANKED
    subwfb      usb_setup_w_length_hi_b0, W, BANKED
    bc          usb_ep0_arm_control_transfer_response__stage_in_data_packet
    movff       usb_setup_w_length_lo_phys, usb_ep0_transfer_remaining_lo_phys
    movff       usb_setup_w_length_hi_phys, usb_ep0_transfer_remaining_hi_phys
usb_ep0_arm_control_transfer_response__stage_in_data_packet:
    rcall       usb_ep0_stage_in_data_packet
    movlw       0x48
    rcall       usb_stage_bdt_template_status_w
    movlw       0x01
    rcall       usb_ep0_arm_out_pingpong_bd_window
    movlw       0x00
    rcall       usb_ep0_arm_out_pingpong_bd_window
    movlb       0x4
    movlw       0x04
    movwf       usb_ep0_in_bd_addr_hi_b4, BANKED
    movlw       0x24
    movwf       usb_ep0_in_bd_addr_lo_b4, BANKED
    bra         usb_ep0_arm_control_transfer_response__arm_in_bd
usb_ep0_arm_control_transfer_response__handle_host_to_device_stage:
    movlw       0x02
    movwf       usb_ep0_control_transfer_phase_b0, BANKED
    movlw       0x04
    rcall       usb_stage_bdt_template_status_w
    movf        usb_setup_w_length_hi_b0, W, BANKED
    iorwf       usb_setup_w_length_lo_b0, W, BANKED
    bnz         usb_ep0_arm_control_transfer_response__arm_next_out_stage
    movlw       0x48
    rcall       usb_stage_bdt_template_status_w
usb_ep0_arm_control_transfer_response__arm_next_out_stage:
    movlb       0x0
    rcall       usb_ep0_arm_next_out_pingpong_bd
usb_ep0_arm_control_transfer_response__maybe_arm_zero_length_in_status:
    movf        usb_setup_w_length_hi_b0, W, BANKED
    iorwf       usb_setup_w_length_lo_b0, W, BANKED
    bnz         usb_ep0_arm_control_transfer_response__return
    movlb       0x4
    clrf        usb_ep0_in_bd_count_b4, BANKED
usb_ep0_arm_control_transfer_response__arm_in_bd:
    movlw       0x48
    movwf       usb_ep0_in_bd_status_b4, BANKED
    bsf         usb_ep0_in_bd_status_b4, 7, BANKED
usb_ep0_arm_control_transfer_response__return:
    return      0


; ---------------------------------------------------------------------------
; Function: i2c_secondary_apply_wake_init_table
; Address : 0x32F8
; Notes   : Inferred i2c helper routine. Calls: i2c_wait_bus_idle, i2c_secondary_dev_write.
; ---------------------------------------------------------------------------
i2c_secondary_apply_wake_init_table:
    call        i2c_wait_bus_idle, 0x0
    movlw       LOW(i2c_secondary_wake_init_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(i2c_secondary_wake_init_table)
    movwf       TBLPTRH, ACCESS
    movlw       0x10
    bra         i2c_secondary_write_table_rows

i2c_secondary_wake_init_table:
    db          0x3F,0x01, 0x30,0x03, 0x01,0x04, 0x08,0x05, 0x01,0x06, 0x34,0x07, 0x30,0x08, 0x08,0x0D, 0x08,0x0E, 0x22,0x0F, 0x00,0x10, 0x00,0x11, 0x01,0x1C, 0x01,0x1D, 0x02,0x2D, 0x20,0x2E

i2c_secondary_write_table_rows:
    clrf        TBLPTRU, ACCESS
    movwf       flash_end_high_or_loop_mask_scratch_byte, ACCESS
i2c_secondary_write_table_rows__write_next_row:
    tblrd*+
    movff       TABLAT, status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys
    tblrd*+
    movf        TABLAT, W, ACCESS
    rcall       i2c_secondary_dev_write_call_range_trampoline
    decfsz      flash_end_high_or_loop_mask_scratch_byte, F, ACCESS
    bra         i2c_secondary_write_table_rows__write_next_row
    return      0

; FIELD-10 wake device-init barrier.  This is the only post-wake owner for
; i2c_secondary_apply_wake_init_table and the wake-tail secondary 0x1B write.  Carry set
; means the phase observed ACKSTAT/DSP fault and volume must stay suppressed.
wake_i2c_barrier_attempt:
    movlb       0x0
    bcf         dsp_fault_flags_b0, 2, BANKED
    rcall       i2c_secondary_apply_wake_init_table
    movlw       0x01
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x1B
    rcall       i2c_secondary_dev_write_call_range_trampoline
    movlb       0x0
    bcf         STATUS, 0, ACCESS
    btfsc       dsp_fault_flags_b0, 2, BANKED
    bsf         STATUS, 0, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: truncate_float32_to_integral_float_in_place
; Address : 0x3398
; Notes   : Inferred core helper routine. Calls: fw_update_signature_status_word_helper, float32_to_int32_in_place, int32_to_float32_and_save.
; ---------------------------------------------------------------------------
truncate_float32_to_integral_float_in_place:
    rcall       chain_copy          ; size T95: table-driven copy run
    db          0x00, 0x00, float32_transform_shadow_dword_op, addr_low_counter_or_payload_scratch_operand, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movlw       0x37
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    call        fw_update_signature_status_word_helper, 0x0
    movf        float32_trunc_exponent_hi_acc, W, ACCESS
    rcall       signed_hi_bias80_compare_prelude
    btfsc       STATUS, 2, ACCESS
    subwf       float32_exponent_lo_or_target_offset_scratch_acc, W, ACCESS
    bc          truncate_float32_to_integral_float_in_place__check_already_integral_range
    clrf        float32_preset_fw_update_scratch_byte0_acc, ACCESS
    clrf        preset_payload_index_or_float32_shadow_byte1_acc, ACCESS
    clrf        preset_row_len_or_float32_shadow_byte2_acc, ACCESS
    clrf        float32_transform_shadow_byte3_acc, ACCESS
    bra         truncate_float32_to_integral_float_in_place__return
truncate_float32_to_integral_float_in_place__check_already_integral_range:
    movlw       0x1D
    subwf       float32_exponent_lo_or_target_offset_scratch_acc, W, ACCESS
    movlw       0x00
    subwfb      float32_trunc_exponent_hi_acc, W, ACCESS
    bc          truncate_float32_to_integral_float_in_place__return
truncate_float32_to_integral_float_in_place__convert_through_int32:
    rcall       copy_transform_shadow_to_math_operand           ; size S3
    rcall       float32_to_int32_in_place
    rcall       chain_copy          ; size T95: table-driven copy run
    db          0x00, 0x00, float32_math_operand_byte0_op, float32_coeff_or_volume_work_operand_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    call        int32_to_float32_and_save, 0x0
    rcall       chain_copy          ; size S1: table-driven copy run
    db          0x00, 0x00, float32_coeff_or_volume_work_operand_op, math_temp_result_dword_op, 0x04, math_temp_result_dword_op, float32_transform_shadow_dword_op, 0x04, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
truncate_float32_to_integral_float_in_place__return:
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_apply_clear_set_feature_request
; Address : 0x3432
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep0_apply_clear_set_feature_request:
    decf        usb_setup_w_value_lo_b0, W, BANKED
    bnz         usb_ep0_apply_clear_set_feature_request__check_endpoint_halt
    movf        usb_setup_bm_request_type_b0, W, BANKED
    andlw       0x1F
    bnz         usb_ep0_apply_clear_set_feature_request__check_endpoint_halt
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movf        usb_setup_b_request_b0, W, BANKED
    xorlw       0x03
    bnz         usb_ep0_apply_clear_set_feature_request__clear_device_remote_wakeup
    bsf         usb_ep0_control_flags_b0, 0, BANKED
    bra         usb_ep0_apply_clear_set_feature_request__check_endpoint_halt
usb_ep0_apply_clear_set_feature_request__clear_device_remote_wakeup:
    bcf         usb_ep0_control_flags_b0, 0, BANKED
usb_ep0_apply_clear_set_feature_request__check_endpoint_halt:
    tstfsz      usb_setup_w_value_lo_b0, BANKED
    bra         usb_ep0_apply_clear_set_feature_request__return
    movf        usb_setup_bm_request_type_b0, W, BANKED
    andlw       0x1F
    xorlw       0x02
    bnz         usb_ep0_apply_clear_set_feature_request__return
    movf        usb_setup_w_index_lo_b0, W, BANKED
    andlw       0x0F
    bz          usb_ep0_apply_clear_set_feature_request__return
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    rcall       usb_ep0_endpoint_bdt_addr_from_windex        ; W05-E06 factored
    movf        usb_setup_b_request_b0, W, BANKED
    xorlw       0x03
    bnz         usb_ep0_apply_clear_set_feature_request__clear_in_endpoint_halt
    rcall       load_fsr2_from_target_ptr
    movlw       0x04
    bra         usb_ep0_apply_clear_set_feature_request__write_endpoint_halt_status
usb_ep0_apply_clear_set_feature_request__clear_in_endpoint_halt:
    btfss       usb_setup_w_index_lo_b0, 7, BANKED
    bra         usb_ep0_apply_clear_set_feature_request__clear_out_endpoint_halt
    rcall       load_fsr2_from_target_ptr
    movlw       0x40
    movwf       INDF2, ACCESS
    bra         usb_ep0_apply_clear_set_feature_request__return
usb_ep0_apply_clear_set_feature_request__clear_out_endpoint_halt:
    rcall       load_fsr2_from_target_ptr
    movlw       0x08
usb_ep0_apply_clear_set_feature_request__write_endpoint_halt_status:
    movwf       INDF2, ACCESS
    rcall       load_fsr2_from_target_ptr
    bsf         INDF2, 7, ACCESS
usb_ep0_apply_clear_set_feature_request__return:
    return      0

load_fsr2_from_target_ptr:
    movff       fsr2_target_ptr_lo_phys, FSR2L
    movff       fsr2_target_ptr_hi_phys, FSR2H
    return      0


; ---------------------------------------------------------------------------
; Function: format_uint16_radix_ascii_to_w_pointer
; Address : 0x34C8
; Notes   : Inferred core helper routine. Calls: adc_divide_staged_words, adc_remainder_staged_words.
; ---------------------------------------------------------------------------
format_uint16_radix_ascii_to_w_pointer:
    movwf       float_loop_or_tblptr_low_scratch_byte, ACCESS
    movff       eeprom_mask_or_flash_src_high_scratch_phys, flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys
    movff       timeout_lo_b0_phys, adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys
format_uint16_radix_ascii_to_w_pointer__count_digits:
    rcall       chain_copy          ; size T151: ADC loop parameter staging
    db          0x00, 0x00, adc_loop_parameter_word_op, addr_low_counter_or_payload_scratch_operand, 0x02, timeout_hi_acc_op, saved_w_acc_op, 0x02, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    call        adc_divide_staged_words, 0x0
    movff       addr_low_counter_or_payload_scratch_phys, flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys
    movff       addr_high_table_row_or_checksum_scratch_phys, adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys
    incf        float_loop_or_tblptr_low_scratch_byte, F, ACCESS
    movf        flash_block_or_uart_byte_scratch_byte, W, ACCESS
    iorwf       flash_upper_or_uart_count_scratch_byte, W, ACCESS
    bnz         format_uint16_radix_ascii_to_w_pointer__count_digits
    movf        float_loop_or_tblptr_low_scratch_byte, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    clrf        INDF2, ACCESS
    decf        float_loop_or_tblptr_low_scratch_byte, F, ACCESS
    bra         format_uint16_radix_ascii_to_w_pointer__emit_next_digit    ; jump the dedup body below
; adc_stage_division_operands_from_sample_window — shared ADC sample parameter staging (00A/timeout_lo/
; timeout_hi/00D -> 003/004/saved_w/006) (size S3 dedup; W/STATUS-dead at
; both callers, audited).
adc_stage_division_operands_from_sample_window:
    rcall       chain_copy          ; size T94: table-driven copy run
    db          0x00, 0x00, numeric_format_value_dword_op, addr_low_counter_or_payload_scratch_operand, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    return      0

format_uint16_radix_ascii_to_w_pointer__emit_next_digit:
    rcall       adc_stage_division_operands_from_sample_window           ; size S3
    call        adc_remainder_staged_words, 0x0
    movf        addr_low_counter_or_payload_scratch_byte, W, ACCESS
    movwf       flash_gie_or_float_sign_scratch_byte, ACCESS
    rcall       adc_stage_division_operands_from_sample_window           ; size S3
    call        adc_divide_staged_words, 0x0
    movff       addr_low_counter_or_payload_scratch_phys, eeprom_mask_or_flash_src_high_scratch_phys
    movff       addr_high_table_row_or_checksum_scratch_phys, timeout_lo_b0_phys
    movlw       0x09
    cpfsgt      flash_gie_or_float_sign_scratch_byte, ACCESS
    bra         format_uint16_radix_ascii_to_w_pointer__store_ascii_digit
    movlw       0x07
    addwf       flash_gie_or_float_sign_scratch_byte, F, ACCESS
format_uint16_radix_ascii_to_w_pointer__store_ascii_digit:
    movlw       0x30
    addwf       flash_gie_or_float_sign_scratch_byte, F, ACCESS
    movf        float_loop_or_tblptr_low_scratch_byte, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       float32_sign_or_uart_digit_or_flash_read_tblptrh_save_phys, INDF2
    decf        float_loop_or_tblptr_low_scratch_byte, F, ACCESS
    movf        eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, W, ACCESS
    iorwf       eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS
    bnz         format_uint16_radix_ascii_to_w_pointer__emit_next_digit
    incf        float_loop_or_tblptr_low_scratch_byte, F, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: boot_init_peripherals_and_enter_adc_gate
; Address : 0x355C
; Notes   : Inferred i2c helper; touches adc,i2c,timer. Calls: eeprom_read_byte, flash_write_with_gie_off, eeprom_write_byte_if_changed.
; ---------------------------------------------------------------------------
boot_init_peripherals_and_enter_adc_gate:
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
    movwf       boot_config_marker_valid_b0, BANKED
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    setf        addr_low_counter_or_payload_scratch_byte, ACCESS
    call        eeprom_read_byte, 0x0
    xorlw       0x77
    bz          boot_init_peripherals_and_enter_adc_gate__maybe_rewrite_config_bits
    xorlw       0xFF                            ; (byte ^ 0x77) ^ 0xFF == byte ^ 0x88
    bz          boot_init_peripherals_and_enter_adc_gate__maybe_rewrite_config_bits
    movlb       0x0
    clrf        boot_config_marker_valid_b0, BANKED
boot_init_peripherals_and_enter_adc_gate__maybe_rewrite_config_bits:
    movlb       0x0
    tstfsz      boot_config_marker_valid_b0, BANKED
    call        flash_write_with_gie_off, 0x0
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    setf        count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x02
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    call        eeprom_write_byte_if_changed, 0x0
    bsf         PORTB, 6, ACCESS
    rcall       adaptive_baud_select
    movlw       0x03
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movlw       0xE8
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    call        timer3_blocking_delay, 0x0
    call        restore_eeprom_settings_on_boot, 0x0
    bsf         PIE1, 5, ACCESS
    bsf         active_flags_acc, 3, ACCESS
    movlb       0x0
    bsf         event_flags_b0, 7, BANKED      ; V3.1: boot complete — enable bounded PEN waits
    bra         run_wake_rail_gate_and_dsp_cold_init


; ---------------------------------------------------------------------------
; Function: usb_ep0_stage_in_data_packet
; Address : 0x35F0
; Notes   : Inferred flash helper; touches flash. Calls: usb_ep0_prepare_in_data_copy_pointers, read_low_memory_byte_at_tblptr, usb_ep0_store_in_data_byte_and_advance.
; ---------------------------------------------------------------------------
usb_ep0_stage_in_data_packet:
    movlw       0x08
    movwf       usb_ep0_in_packet_count_b0, BANKED
    subwf       usb_ep0_transfer_remaining_lo_b0, W, BANKED
    movlw       0x00
    subwfb      usb_ep0_transfer_remaining_hi_b0, W, BANKED
    bc          usb_ep0_stage_in_data_packet__stage_packet_length_and_buffer
    movff       usb_ep0_transfer_remaining_lo_phys, usb_ep0_in_packet_count_phys
    tstfsz      usb_ep0_in_data_toggle_state_b0, BANKED
    bra         usb_ep0_stage_in_data_packet__advance_data_toggle_state
    movlw       0x01
    bra         usb_ep0_stage_in_data_packet__store_data_toggle_state
usb_ep0_stage_in_data_packet__advance_data_toggle_state:
    decf        usb_ep0_in_data_toggle_state_b0, W, BANKED
    bnz         usb_ep0_stage_in_data_packet__stage_packet_length_and_buffer
    movlw       0x02
usb_ep0_stage_in_data_packet__store_data_toggle_state:
    movwf       usb_ep0_in_data_toggle_state_b0, BANKED
usb_ep0_stage_in_data_packet__stage_packet_length_and_buffer:
    movff       usb_ep0_in_packet_count_phys, usb_ep0_in_bd_count_phys
    movf        usb_ep0_in_packet_count_b0, W, BANKED
    subwf       usb_ep0_transfer_remaining_lo_b0, F, BANKED
    movlw       0x00
    subwfb      usb_ep0_transfer_remaining_hi_b0, F, BANKED
    movlw       0x04
    movlb       0x0
    movwf       fsr2_target_ptr_hi_b0, BANKED
    movlw       0x24
    movwf       fsr2_target_ptr_lo_b0, BANKED
    btfsc       usb_ep0_control_flags_b0, 1, BANKED
    bra         usb_ep0_stage_in_data_packet__check_table_source_remaining
    bra         usb_ep0_stage_in_data_packet__check_lowpage_source_remaining
usb_ep0_stage_in_data_packet__copy_table_source_byte:
    rcall       usb_ep0_prepare_in_data_copy_pointers
    cpfsgt      TBLPTRH, ACCESS
    bra         usb_ep0_stage_in_data_packet__read_lowpage_table_byte
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         usb_ep0_stage_in_data_packet__store_table_source_byte
usb_ep0_stage_in_data_packet__read_lowpage_table_byte:
    rcall       read_low_memory_byte_at_tblptr
usb_ep0_stage_in_data_packet__store_table_source_byte:
    rcall       usb_ep0_store_in_data_byte_and_advance
usb_ep0_stage_in_data_packet__check_table_source_remaining:
    tstfsz      usb_ep0_in_packet_count_b0, BANKED
    bra         usb_ep0_stage_in_data_packet__copy_table_source_byte
    bra         usb_ep0_stage_in_data_packet__return
usb_ep0_stage_in_data_packet__copy_lowpage_source_byte:
    rcall       usb_ep0_prepare_in_data_copy_pointers
    cpfsgt      TBLPTRH, ACCESS
    bra         usb_ep0_stage_in_data_packet__read_lowpage_source_byte
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         usb_ep0_stage_in_data_packet__store_lowpage_source_byte
usb_ep0_stage_in_data_packet__read_lowpage_source_byte:
    rcall       read_low_memory_byte_at_tblptr
usb_ep0_stage_in_data_packet__store_lowpage_source_byte:
    rcall       usb_ep0_store_in_data_byte_and_advance
usb_ep0_stage_in_data_packet__check_lowpage_source_remaining:
    tstfsz      usb_ep0_in_packet_count_b0, BANKED
    bra         usb_ep0_stage_in_data_packet__copy_lowpage_source_byte
usb_ep0_stage_in_data_packet__return:
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_prepare_in_data_copy_pointers
; Address : 0x365C
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
usb_stage_tblptr_from_flash_ptr_cache:
    movff       usb_ep0_in_source_ptr_lo_phys, TBLPTRL
    movff       usb_ep0_in_source_ptr_hi_phys, TBLPTRH
    clrf        TBLPTRU, ACCESS
    return      0

usb_ep0_prepare_in_data_copy_pointers:
    rcall       usb_stage_tblptr_from_flash_ptr_cache
    rcall       load_fsr2_from_target_ptr
    retlw       0x07


; ---------------------------------------------------------------------------
; Function: usb_ep0_store_in_data_byte_and_advance
; Address : 0x3672
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep0_store_in_data_byte_and_advance:
    movwf       INDF2, ACCESS
    movlb       0x0
    infsnz      fsr2_target_ptr_lo_b0, F, BANKED
    incf        fsr2_target_ptr_hi_b0, F, BANKED
    infsnz      usb_ep0_in_source_ptr_lo_b0, F, BANKED
    incf        usb_ep0_in_source_ptr_hi_b0, F, BANKED
    decf        usb_ep0_in_packet_count_b0, F, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_dispatch_standard_setup_request
; Address : 0x3682
; Notes   : Inferred core helper routine. Calls: usb_ep0_select_get_descriptor_payload, usb_apply_set_configuration, usb_ep0_prepare_get_status_reply.
; ---------------------------------------------------------------------------
usb_ep0_dispatch_standard_setup_request:
    swapf       usb_setup_bm_request_type_b0, W, BANKED
    rrcf        WREG, F, ACCESS
    andlw       0x03
    bnz         usb_ep0_dispatch_standard_setup_request__return
    bra         usb_ep0_dispatch_standard_setup_request__dispatch_request_code
usb_ep0_dispatch_standard_setup_request__set_address:
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movlw       0x04
    movwf       usb_device_state_b0, BANKED
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__get_descriptor:
    rcall       usb_ep0_select_get_descriptor_payload
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__set_configuration:
    call        usb_apply_set_configuration, 0x0
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__get_configuration:
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movlw       0xEB
    bra         usb_ep0_stage_one_byte_lowpage_in_data_pointer
usb_ep0_dispatch_standard_setup_request__get_status:
    rcall       usb_ep0_prepare_get_status_reply
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__clear_or_set_feature:
    rcall       usb_ep0_apply_clear_set_feature_request
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_stage_interface_alt_setting_offset:
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movf        usb_setup_w_index_lo_b0, W, BANKED
    addlw       0xEC
    return      0
usb_ep0_dispatch_standard_setup_request__get_interface:
    rcall       usb_ep0_stage_interface_alt_setting_offset
    movwf       length_mask_or_divisor_low_scratch_byte, ACCESS
    clrf        usb_ep0_in_source_ptr_hi_b0, BANKED
    movff       saved_w_b0_phys, usb_ep0_in_source_ptr_lo_phys
    bra         usb_ep0_mark_one_byte_lowpage_in_data_ready
usb_ep0_dispatch_standard_setup_request__set_interface:
    rcall       usb_ep0_stage_interface_alt_setting_offset
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movff       usb_setup_w_value_lo_phys, INDF2
    bra         usb_ep0_dispatch_standard_setup_request__return
usb_ep0_dispatch_standard_setup_request__dispatch_request_code:
    movf        usb_setup_b_request_b0, W, BANKED
    bz          usb_ep0_dispatch_standard_setup_request__get_status
    xorlw       0x01
    bz          usb_ep0_dispatch_standard_setup_request__clear_or_set_feature
    xorlw       0x02
    bz          usb_ep0_dispatch_standard_setup_request__clear_or_set_feature
    xorlw       0x06
    bz          usb_ep0_dispatch_standard_setup_request__set_address
    xorlw       0x03
    bz          usb_ep0_dispatch_standard_setup_request__get_descriptor
    xorlw       0x01
    bz          usb_ep0_dispatch_standard_setup_request__return
    xorlw       0x0F
    bz          usb_ep0_dispatch_standard_setup_request__get_configuration
    xorlw       0x01
    bz          usb_ep0_dispatch_standard_setup_request__set_configuration
    xorlw       0x03
    bz          usb_ep0_dispatch_standard_setup_request__get_interface
    xorlw       0x01
    bz          usb_ep0_dispatch_standard_setup_request__set_interface
usb_ep0_dispatch_standard_setup_request__return:
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_prepare_get_status_reply
; Address : 0x3710
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep0_prepare_get_status_reply:
    movlb       0x4
    clrf        usb_ep0_get_status_reply_byte0_b4, BANKED
    clrf        usb_ep0_get_status_reply_byte1_b4, BANKED
    bra         usb_ep0_prepare_get_status_reply__dispatch_recipient
usb_ep0_prepare_get_status_reply__device_status:
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    btfss       usb_ep0_control_flags_b0, 0, BANKED
    bra         usb_ep0_prepare_get_status_reply__stage_reply
    movlb       0x4
    bsf         usb_ep0_get_status_reply_byte0_b4, 1, BANKED
    bra         usb_ep0_prepare_get_status_reply__stage_reply
usb_ep0_prepare_get_status_reply__interface_status:
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    bra         usb_ep0_prepare_get_status_reply__stage_reply
usb_ep0_prepare_get_status_reply__endpoint_status:
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    rcall       usb_ep0_endpoint_bdt_addr_from_windex        ; W05-E06 factored
    rcall       load_fsr2_from_target_ptr
    movf        INDF2, W, ACCESS
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    btfss       addr_low_counter_or_payload_scratch_byte, 2, ACCESS
    bra         usb_ep0_prepare_get_status_reply__stage_reply
    movlw       0x01
    movlb       0x4
    movwf       usb_ep0_get_status_reply_byte0_b4, BANKED
    bra         usb_ep0_prepare_get_status_reply__stage_reply
; ---------------------------------------------------------------------------
; usb_ep0_endpoint_bdt_addr_from_windex (W05-E06 factored helper, 2 sites)
;   Input : ram_0x0D3 (BANKED) — selected filter/slot index (4-bit lo) + bit7
;   Output:
;     ram_0x003:ram_0x004 = base + mul_lo  (usb_ep0_apply_clear_set_feature_request site uses
;                                           this as the working filter addr)
;     ram_0x072:ram_0x073 = ram_0x003:004 +/- mul_hi adjustment per bit7
;   Factors an identical 20-instruction block shared by
;     usb_ep0_apply_clear_set_feature_request (L4961 in v32) and
;     usb_ep0_prepare_get_status_reply (L5339 in v32).
;   Uses rcall (within range from both callers).  BSR left unchanged; callers
;   continue to expect BANKED access to bank 0 (ram_0x0D0..ram_0x0D3 live
;   in bank 0).
; ---------------------------------------------------------------------------
usb_ep0_endpoint_bdt_addr_from_windex:
    movf        usb_setup_w_index_lo_b0, W, BANKED
    andlw       0x0F
    mullw       0x08
    movlw       0x04
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movf        PRODL, W, ACCESS
    addwf       addr_low_counter_or_payload_scratch_byte, F, ACCESS
    movf        PRODH, W, ACCESS
    addwfc      addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    movlw       0x01
    btfss       usb_setup_w_index_lo_b0, 7, BANKED
    movlw       0x00
    mullw       0x04
    movf        PRODL, W, ACCESS
    addwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    movwf       fsr2_target_ptr_lo_b0, BANKED
    movf        PRODH, W, ACCESS
    addwfc      addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    movwf       fsr2_target_ptr_hi_b0, BANKED
    return      0
usb_ep0_prepare_get_status_reply__dispatch_recipient:
    movlb       0x0
    movf        usb_setup_bm_request_type_b0, W, BANKED
    andlw       0x1F
    bz          usb_ep0_prepare_get_status_reply__device_status
    xorlw       0x01
    bz          usb_ep0_prepare_get_status_reply__interface_status
    xorlw       0x03
    bz          usb_ep0_prepare_get_status_reply__endpoint_status
usb_ep0_prepare_get_status_reply__stage_reply:
    movlb       0x0
    decf        usb_ep0_control_response_mode_b0, W, BANKED
    bnz         usb_ep0_prepare_get_status_reply__return
    movlw       0x04
    movwf       usb_ep0_in_source_ptr_hi_b0, BANKED
    movlw       0x24
    movwf       usb_ep0_in_source_ptr_lo_b0, BANKED
    bcf         usb_ep0_control_flags_b0, 1, BANKED
    movlw       0x02
    movwf       usb_ep0_transfer_remaining_lo_b0, BANKED
usb_ep0_prepare_get_status_reply__return:
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_select_get_descriptor_payload
; Address : 0x3796
; Notes   : Inferred flash helper; touches flash. Calls: read_low_memory_byte_at_tblptr.
; ---------------------------------------------------------------------------
usb_ep0_select_get_descriptor_payload:
    movf        usb_setup_bm_request_type_b0, W, BANKED
    xorlw       0x80
    bz          usb_ep0_select_get_descriptor_payload__dispatch_descriptor_type
    bra         usb_ep0_select_get_descriptor_payload__return
usb_ep0_select_get_descriptor_payload__device_descriptor:
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movlw       HIGH(usb_device_descriptor)
    movwf       usb_ep0_in_source_ptr_hi_b0, BANKED
    movlw       LOW(usb_device_descriptor)
    movwf       usb_ep0_in_source_ptr_lo_b0, BANKED
    movlw       0x12
    bra         usb_ep0_select_get_descriptor_payload__store_descriptor_length
usb_ep0_select_get_descriptor_payload__configuration_descriptor:
    tstfsz      usb_setup_w_value_lo_b0, BANKED
    bra         usb_ep0_select_get_descriptor_payload__mark_data_stage_dirty
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movlw       HIGH(usb_config_descriptor)
    movwf       usb_ep0_in_source_ptr_hi_b0, BANKED
    movlw       LOW(usb_config_descriptor)
    movwf       usb_ep0_in_source_ptr_lo_b0, BANKED
    clrf        usb_ep0_transfer_remaining_hi_b0, BANKED
    movlw       0x29
usb_ep0_select_get_descriptor_payload__store_descriptor_length:
    movwf       usb_ep0_transfer_remaining_lo_b0, BANKED
    bra         usb_ep0_select_get_descriptor_payload__mark_data_stage_dirty
usb_ep0_select_get_descriptor_payload__string_descriptor:
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    movf        usb_setup_w_value_lo_b0, W, BANKED
    addlw       LOW(string_desc_ptr_table)          ; indexed TBLPTR -> string_desc_ptr_table
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(string_desc_ptr_table)
    movwf       TBLPTRH, ACCESS
    tblrd*+
    movff       TABLAT, usb_ep0_in_source_ptr_lo_phys
    movwf       usb_ep0_in_source_ptr_hi_b0, BANKED
    rcall       usb_stage_tblptr_from_flash_ptr_cache
    movlw       0x07
    cpfsgt      TBLPTRH, ACCESS
    bra         usb_ep0_select_get_descriptor_payload__read_string_length_via_fsr
    tblrd*
    movf        TABLAT, W, ACCESS
    bra         usb_ep0_select_get_descriptor_payload__store_string_length
usb_ep0_select_get_descriptor_payload__read_string_length_via_fsr:
    rcall       read_low_memory_byte_at_tblptr
usb_ep0_select_get_descriptor_payload__store_string_length:
    movlb       0x0
    movwf       usb_ep0_transfer_remaining_lo_b0, BANKED
    clrf        usb_ep0_transfer_remaining_hi_b0, BANKED
    bra         usb_ep0_select_get_descriptor_payload__mark_data_stage_dirty
usb_ep0_select_get_descriptor_payload__dispatch_descriptor_type:
    movf        usb_setup_w_value_hi_b0, W, BANKED
    xorlw       0x01
    bz          usb_ep0_select_get_descriptor_payload__device_descriptor
    xorlw       0x03
    bz          usb_ep0_select_get_descriptor_payload__configuration_descriptor
    xorlw       0x01
    bz          usb_ep0_select_get_descriptor_payload__string_descriptor
usb_ep0_select_get_descriptor_payload__mark_data_stage_dirty:
    bsf         usb_ep0_control_flags_b0, 1, BANKED
usb_ep0_select_get_descriptor_payload__return:
    return      0


; ---------------------------------------------------------------------------
; Function: read_low_memory_byte_at_tblptr
; Address : 0x3810
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
read_low_memory_byte_at_tblptr:
    movff       TBLPTRL, FSR1L
    movff       TBLPTRH, FSR1H
    movf        INDF1, W, ACCESS
    return      0

i2c_secondary_dev_write_call_range_trampoline:
    goto        i2c_secondary_dev_write


; ---------------------------------------------------------------------------
; Function: preset_table_apply_entry_legacy_blocking          (legacy preset table-entry I2C apply)
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
; Called from: poll_src4382_route_monitor (DSP I2C refresh), cmd_dispatch_gated
;              (channel sync), some legacy reconnect/wake paths.
; ---------------------------------------------------------------------------
preset_table_apply_entry_legacy_blocking:
    rcall       preset_table_apply_entry_core
    bnc         preset_table_apply_entry_legacy__success_return
    btfsc       i2c_flag_or_flash_math_uart_cmd_scratch_byte, 0, ACCESS
    bra         preset_table_apply_entry_legacy__pen_timeout_recover
    bra         preset_table_apply_entry_legacy__timeout_recover
preset_table_apply_entry_legacy__success_return:
    return      0
preset_table_apply_entry_legacy__timeout_recover:
    goto        i2c_timeout_recover_advertise
preset_table_apply_entry_legacy__pen_timeout_recover:
    goto        i2c_pen_timeout_recover_advertise

; Shared core for legacy blocking applies and the V3.2 async preset job.
; in : ram_0x013/014 = table-entry flash address.
; out: C=0 success or sentinel no-op; C=1 bounded wait timeout.
;      ram_0x00D.bit0 set only for PEN timeout so legacy callers can keep
;      their separate PEN recovery path.
preset_table_apply_entry_core:
    bcf         float_divisor_or_preset_flag_scratch_byte, 0, ACCESS        ; legacy path uses live A/B remap
    clrf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    rcall       preset_table_stage_header_read
    rcall       flash_read_to_scratch_buffer            ; legacy flash_read remaps active preset B
preset_table_apply_entry_header_copy:
    movff       preset_header_tas_reg_or_uart_block_base_low_scratch_phys, float32_preset_fw_update_scratch_byte0_b0_phys                ; ram_0x02F = TAS reg byte
    movff       preset_table_header_len_source_phys, preset_table_row_len_phys                ; ram_0x031 = byte count
preset_table_apply_entry_header_valid:
    movlw       0x19                                ; >= 25 -> end-of-table sentinel
    subwf       preset_row_len_or_float32_shadow_byte2_acc, W, ACCESS
    bc          preset_table_apply_entry_core__return_success
    ; FIELD-4B: skip volume-family rows (TAS 0x30-0x36).  The volume engine
    ; owns master + per-channel volumes and re-derives them right after
    ; every switch anyway, so the capture-baked values were only ever a
    ; transient overwrite -- but they played LIVE between the master-volume
    ; restore and the engine's per-channel re-walk (2026-06-10 field
    ; incident: loud bass on preset B), persistently if that walk stalled.
    ; Skipping them keeps the user's channel volumes correct end-to-end.
    movlw       0x30
    subwf       float32_preset_fw_update_scratch_byte0_acc, W, ACCESS            ; C=1 if reg >= 0x30
    bnc         preset_table_apply_entry_not_vol
    movlw       0x37
    subwf       float32_preset_fw_update_scratch_byte0_acc, W, ACCESS            ; C=1 if reg >= 0x37
    bnc         preset_table_apply_entry_core__return_success       ; 0x30..0x36 -> benign skip
preset_table_apply_entry_not_vol:
    movlw       0x04                                ; advance past header
    addwf       route_bit_or_tblptr_upper_scratch_byte, W, ACCESS
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    movlw       0x00
    addwfc      route_base_or_flash_addr_low_scratch_byte, W, ACCESS
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    clrf        length_mask_or_divisor_low_scratch_byte, ACCESS
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movff       preset_table_row_len_phys, computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys                ; second read = data block
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    btfsc       float_divisor_or_preset_flag_scratch_byte, 0, ACCESS
    rcall       flash_read_without_preset_remap_to_scratch_buffer          ; async path: physical cursor, no live remap
    btfss       float_divisor_or_preset_flag_scratch_byte, 0, ACCESS
    rcall       flash_read_to_scratch_buffer
    bsf         SSPCON2, 0, ACCESS                  ; SEN — START
    call        wait_sen_bounded, 0x0
    bc          preset_table_apply_entry_timeout
    movlw       0x68                                ; TAS3108 write address
    rcall       i2c_byte_tx
    movf        float32_preset_fw_update_scratch_byte0_acc, W, ACCESS                ; reg byte
    rcall       i2c_byte_tx
    clrf        preset_payload_index_or_float32_shadow_byte1_acc, ACCESS
    bra         preset_table_apply_entry_core__check_payload_count

; Async preset APPLY core.  Reads the job-owned physical cursor directly,
; validates the table header from preset_job_index, then joins the legacy
; payload/write body.  stock_012.bit0 is local to this core invocation and
; only selects the no-remap payload read above; it is cleared by the caller
; before STATUS.C is tested.
preset_table_apply_entry_core_async:
    bsf         float_divisor_or_preset_flag_scratch_byte, 0, ACCESS
    clrf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    rcall       preset_table_stage_header_read
    rcall       flash_read_without_preset_remap_to_scratch_buffer          ; physical cursor, no live remap
    movff       preset_header_tas_reg_or_uart_block_base_low_scratch_phys, float32_preset_fw_update_scratch_byte0_b0_phys
    movff       preset_table_header_len_source_phys, preset_table_row_len_phys
    rcall       preset_table_validate_async_header
    bc          preset_table_apply_entry_timeout
    bra         preset_table_apply_entry_header_valid

preset_table_stage_header_read:
    movff       eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys, addr_low_counter_or_payload_scratch_phys                ; copy 16-bit flash addr (caller staged)
    movff       flash_addr_shadow_low_or_preset_table_addr_hi_phys, addr_high_table_row_or_checksum_scratch_phys
    clrf        length_mask_or_divisor_low_scratch_byte, ACCESS                   ; high byte and TBLPTRU = 0
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    movlw       0x04                                ; first read: 4-byte header (TAS reg + len)
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    return      0

preset_table_validate_async_header:
    movf        float_product_or_output_index_scratch_byte, W, ACCESS            ; header byte 0 must be 0x01
    xorlw       0x01
    bnz         preset_table_async_header_mismatch
    movf        float32_extract_or_quotient_or_preset_uart_index, W, ACCESS            ; header byte 3 must be 0x00
    bnz         preset_table_async_header_mismatch
    movff       preset_job_index_b2_phys, float32_operand_or_flash_addr_shadow_mid_or_preset_job_index_phys
    movlw       0x60
    cpfseq      float_shift_flash_addr_or_preset_index_scratch_byte, ACCESS
    bra         preset_table_async_not_final
    movlw       0xD4
    bra         preset_table_async_compare_len04
preset_table_async_not_final:
    movf        float_shift_flash_addr_or_preset_index_scratch_byte, W, ACCESS
    andlw       0x0F
    bnz         preset_table_async_regular
    swapf       float_shift_flash_addr_or_preset_index_scratch_byte, W, ACCESS
    andlw       0x0F
    addlw       0xC8
preset_table_async_compare_len04:
    xorwf       float32_preset_fw_update_scratch_byte0_acc, W, ACCESS
    bnz         preset_table_async_header_mismatch
    movf        preset_row_len_or_float32_shadow_byte2_acc, W, ACCESS
    xorlw       0x04
    bnz         preset_table_async_header_mismatch
    bcf         STATUS, 0, ACCESS
    return      0
preset_table_async_regular:
    movff       preset_job_index_b2_phys, flash_addr_shadow_upper_or_preset_job_index_or_init_copy_end_phys
    swapf       float_shift_flash_addr_or_preset_index_scratch_byte, W, ACCESS
    andlw       0x0F
    subwf       float_product_flash_addr_or_preset_index_scratch_byte, F, ACCESS
    movlw       0x36
    addwf       float_product_flash_addr_or_preset_index_scratch_byte, W, ACCESS
    xorwf       float32_preset_fw_update_scratch_byte0_acc, W, ACCESS
    bnz         preset_table_async_header_mismatch
    movf        preset_row_len_or_float32_shadow_byte2_acc, W, ACCESS
    xorlw       0x14
    bnz         preset_table_async_header_mismatch
    bcf         STATUS, 0, ACCESS
    return      0
preset_table_async_header_mismatch:
    bcf         i2c_flag_or_flash_math_uart_cmd_scratch_byte, 0, ACCESS            ; mismatch is not a PEN timeout
    bsf         STATUS, 0, ACCESS
    return      0
preset_table_apply_entry_core__send_payload_byte_loop:
    movf        preset_payload_index_or_float32_shadow_byte1_acc, W, ACCESS
    addlw       0x17                                ; data buffer at 0x0017+i
    call        fsr2_page0_read_w, 0x0               ; W04-E03
    rcall       i2c_byte_tx
    incf        preset_payload_index_or_float32_shadow_byte1_acc, F, ACCESS
preset_table_apply_entry_core__check_payload_count:
    movf        preset_row_len_or_float32_shadow_byte2_acc, W, ACCESS
    subwf       preset_payload_index_or_float32_shadow_byte1_acc, W, ACCESS
    bnc         preset_table_apply_entry_core__send_payload_byte_loop
    bsf         SSPCON2, 2, ACCESS                  ; PEN — STOP
    call        wait_pen_bounded, 0x0
    bc          preset_table_apply_entry_pen_timeout
preset_table_apply_entry_core__return_success:
    bcf         STATUS, 0, ACCESS
    return      0
preset_table_apply_entry_timeout:
    bsf         STATUS, 0, ACCESS
    return      0
preset_table_apply_entry_pen_timeout:
    bsf         i2c_flag_or_flash_math_uart_cmd_scratch_byte, 0, ACCESS
    bsf         STATUS, 0, ACCESS
    return      0


usb_stage_bdt_template_status_w:
    movlb       0x1
    movwf       usb_bdt_template_status_b1, BANKED
    movlb       0x0
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
; uart_reconfigure_and_resync_parser to bring up the EUSART, enables GIE/PEIE, clears
; the parser/event/active flag bytes (event_flags, active_flags, ram_0x07F,
; ram_0x0BD, ram_0x0BB, etc.), and pre-seeds the bank-1 register pointer
; cache (ram_0x00F..0x015 = 0x20..0x28) used by the I2C secondary writes.
; This is the post-cold-reset peripheral configuration path; do NOT confuse
; it with hw_standby_shutdown (which performs the inverse OSCCON change).
; ---------------------------------------------------------------------------
adaptive_baud_select:
    btfss       PORTC, 2, ACCESS
    bra         adaptive_baud_select__master_role_31250_path
    rcall       uart_baud_chain_role_prefix
    bra         adaptive_baud_select__common_pin_and_uart_init
adaptive_baud_select__master_role_31250_path:
    bcf         LATB, 2, ACCESS
    rcall       program_uart_31250_baud_common
adaptive_baud_select__common_pin_and_uart_init:
    bcf         LATB, 4, ACCESS
    bcf         LATB, 5, ACCESS
    bcf         LATB, 3, ACCESS
    rcall       clear_lata_audio_pins
    bcf         LATB, 7, ACCESS
    call        uart_reconfigure_and_resync_parser, 0x0
    bsf         INTCON, 7, ACCESS
    bsf         INTCON, 6, ACCESS
    clrf        pending_route_request_b0, BANKED
    clrf        applied_route_shadow_b0, BANKED
    bcf         INTCON3, 4, ACCESS
    bcf         INTCON3, 1, ACCESS
    bcf         INTCON, 2, ACCESS
    bcf         T0CON, 7, ACCESS
    bcf         INTCON, 5, ACCESS
    clrf        channel_enable_mask_b0, BANKED
    clrf        channel_enable_shadow_b0, BANKED
    clrf        src4382_autodetect_scan_index_b0, BANKED
    clrf        src4382_autodetect_countdown_b0, BANKED
    clrf        event_flags_b0, BANKED
    clrf        dsp_fault_flags_b0, BANKED
    clrf        filename_dirty_flags_b0, BANKED
    clrf        active_flags_acc, ACCESS
    clrf        src4382_route_refresh_watchdog_b0, BANKED
    clrf        uart_cmd_reply_data_b0, BANKED
    clrf        an0_delay_b0, BANKED
    clrf        adc_rail_sample_lo_b0, BANKED
    clrf        adc_rail_sample_hi_b0, BANKED
    bcf         ADCON0, 1, ACCESS
    clrf        main_runtime_latch_flags_b0, BANKED
    movlw       0x20
    movlb       0x1
    movwf       tas3108_sync_stage0_reg_addr_b1, BANKED
    movlw       0x21
    movwf       tas3108_sync_stage1_reg_addr_b1, BANKED
    movlw       0x22
    movwf       tas3108_sync_stage2_reg_addr_b1, BANKED
    movlw       0x23
    movwf       tas3108_sync_stage3_reg_addr_b1, BANKED
    movlw       0x25
    movwf       tas3108_sync_stage4_reg_addr_b1, BANKED
    movlw       0x27
    movwf       tas3108_sync_stage5_reg_addr_b1, BANKED
    movlw       0x28
    movwf       tas3108_sync_stage6_reg_addr_b1, BANKED
    retlw       0x28

uart_baud_chain_role_prefix:
    bsf         LATB, 2, ACCESS
    clrf        SPBRGH, ACCESS
    movlw       0x3F
    movwf       SPBRG, ACCESS
    bsf         OSCCON, 1, ACCESS
    return      0

clear_lata_audio_pins:
    bcf         LATA, 6, ACCESS
clear_lata_source_select_pins:
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    return      0


; ---------------------------------------------------------------------------
; stage_tas3108_coeff_input_scratch — shared i2c_coeff_0..3 -> stock_049..04C staging
; (size S3 dedup; W/STATUS-dead at both callers, audited).
; ---------------------------------------------------------------------------
stage_tas3108_coeff_input_scratch:
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, i2c_coeff_0_acc_op, tas3108_coeff_staged_input_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    return      0

; ---------------------------------------------------------------------------
; Function: i2c_emit_tas3108_coeff_from_staged_float
; Address : 0x39A6
; Notes   : Inferred i2c helper routine. Calls: float32_multiply_primary_by_secondary_in_place, main_core_service_38a2, float32_to_int32_in_place.
; ---------------------------------------------------------------------------
i2c_emit_tas3108_coeff_from_staged_float:
    clrf        float_product_flash_addr_or_preset_index_scratch_byte, ACCESS
    clrf        float_product_or_output_index_scratch_byte, ACCESS
    clrf        float32_product_or_uart_base_scratch_byte, ACCESS
    movlw       0x4B
    movwf       float32_product_or_uart_base_high_scratch_byte, ACCESS
    rcall       chain_copy_call_range_trampoline_mid
    db          0x00, 0x00, tas3108_coeff_staged_input_dword_op, float32_i2c_coeff_or_volume_work_operand_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    call        float32_multiply_primary_by_secondary_in_place, 0x0
    rcall       chain_copy_call_range_trampoline_mid
    db          0x00, 0x00, float32_i2c_coeff_or_volume_work_operand_op, tas3108_coeff_transform_work_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, tas3108_coeff_transform_work_dword_op, tas3108_coeff_work_accum_dword_op, 0x04, tas3108_coeff_transform_work_dword_op, float32_transform_shadow_dword_op, 0x04, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       truncate_float32_to_integral_float_in_place
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, float32_transform_shadow_dword_op, tas3108_coeff_result_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movlw       0x80
    xorwf       tas3108_coeff_result_sign_byte, F, ACCESS
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, tas3108_coeff_work_accum_dword_op, float32_accum_work_byte0_op, 0x08, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    call        float32_add_secondary_to_primary_in_place, 0x0
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, float32_accum_work_byte0_op, tas3108_coeff_work_accum_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, tas3108_coeff_work_accum_dword_op, tas3108_coeff_secondary_work_dword_op, 0x04, tas3108_coeff_secondary_work_dword_op, float32_transform_shadow_dword_op, 0x04, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movlw       0x41
    rcall       float32_add_staged_operand_to_ram_window_in_place
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, tas3108_coeff_transform_work_dword_op, float32_transform_shadow_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       truncate_float32_to_integral_float_in_place
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, float32_transform_shadow_dword_op, tas3108_coeff_transform_work_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, tas3108_coeff_transform_work_dword_op, hid_out_coeff_scratch_byte0_op, 0x04, hid_out_coeff_scratch_byte0_op, float32_math_operand_byte0_op, 0x04, 0xFF, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    call        float32_to_int32_in_place, 0x0
    rcall       chain_copy_call_range_trampoline_mid
    db          0x00, 0x00, float32_math_operand_byte0_op, tas3108_coeff_tx_byte3_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movf        tas3108_coeff_tx_byte0_acc, W, ACCESS
    andlw       0x0F
    rcall       i2c_byte_tx
    movf        tas3108_coeff_tx_byte1_acc, W, ACCESS
    rcall       i2c_byte_tx
    movf        tas3108_coeff_tx_byte2_acc, W, ACCESS
    rcall       i2c_byte_tx
    movf        tas3108_coeff_tx_byte3_acc, W, ACCESS
    bra         i2c_byte_tx


signed_hi_bias80_compare_prelude:
    xorlw       0x80
    movwf       PRODL, ACCESS
    movlw       0x80
    subwf       PRODL, W, ACCESS
    retlw       0x00


; ---------------------------------------------------------------------------
; Function: usb_hid_dispatch_out_report_if_ready          (HID OUT consume / dispatch arbiter)
; Address : 0x3A26
; ---------------------------------------------------------------------------
; Top-of-loop slot in run_main_service_pass. Decides whether the device is
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
;     clear, run usb_ep1_out_copy_packet_if_ready to copy the SETUP into the working
;     buffer at 0x015A and then zero the response buffer at bank 1 offsets
;     0x5A..0x99.
;   • If HID-staging is set (a complete OUT report has been latched), call
;     hid_command_dispatch with the opcode in W; on completion, copy 0x40
;     bytes back to bank 1 offset 0x5A as the IN reply via
;     usb_ep1_in_copy_scratch_buffer_to_bdt.
; ---------------------------------------------------------------------------
usb_hid_dispatch_out_report_if_ready:
    movlb       0x0
    movf        usb_device_state_b0, W, BANKED
    xorlw       0x06
    btfsc       STATUS, 2, ACCESS
    btfsc       UCON, 1, ACCESS
    bra         usb_hid_dispatch_out_report_if_ready__skip_and_reprime_uart_rx
    btfss       active_flags_acc, 3, ACCESS
    bra         usb_hid_dispatch_out_report_if_ready__skip_and_reprime_uart_rx
    btfsc       PORTC, 0, ACCESS
    bra         usb_hid_dispatch_out_report_if_ready__usb_runtime_ready
usb_hid_dispatch_out_report_if_ready__skip_and_reprime_uart_rx:
    bsf         RCSTA, 4, ACCESS
    bra         usb_hid_dispatch_out_report_if_ready__return
usb_hid_dispatch_out_report_if_ready__usb_runtime_ready:
    tstfsz      usb_hid_out_report_pending_b0, BANKED
    bra         usb_hid_dispatch_out_report_if_ready__dispatch_latched_report
    movlb       0x4
    btfsc       usb_ep1_out_bd_status_b4, 7, BANKED
    bra         usb_hid_dispatch_out_report_if_ready__return
    call        ram_clear_prepare_page1_address_high, 0x0
    movlw       0x1A
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    movlw       0x40
    movwf       length_mask_or_divisor_low_scratch_byte, ACCESS
    rcall       usb_ep1_out_copy_packet_if_ready
    movlw       0x01
    movlb       0x0
    movwf       usb_hid_out_report_pending_b0, BANKED
    clrf        scratch_loop_counter_acc, ACCESS
usb_hid_dispatch_out_report_if_ready__clear_reply_buffer_loop:
    movlb       0x1
    movlw       0x5A
    addwf       scratch_loop_counter_acc, W, ACCESS
    call        setup_fsr2_page1_or_page2_from_w_carry, 0x0
    clrf        INDF2, ACCESS
    incf        scratch_loop_counter_acc, F, ACCESS
    movlw       0x3F
    cpfsgt      scratch_loop_counter_acc, ACCESS
    bra         usb_hid_dispatch_out_report_if_ready__clear_reply_buffer_loop
    bra         usb_hid_dispatch_out_report_if_ready__return
usb_hid_dispatch_out_report_if_ready__dispatch_latched_report:
    movlb       0x1
    movf        usb_hid_out_opcode_b1, W, BANKED
    call        hid_command_dispatch, 0x0
    movlb       0x4
    btfsc       usb_ep1_in_bd_status_b4, 7, BANKED
    bra         usb_hid_dispatch_out_report_if_ready__return
    rcall       usb_ep1_in_send_hid_reply_buffer
    movlb       0x0
    clrf        usb_hid_out_report_pending_b0, BANKED
usb_hid_dispatch_out_report_if_ready__return:
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
; through uart_link_parser_drain_rx_and_forward).
; ---------------------------------------------------------------------------
uart_rx_with_framing:
    clrf        flash_upper_or_uart_count_scratch_byte, ACCESS
    clrf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    clrf        flash_block_or_uart_byte_scratch_byte, ACCESS
    clrf        eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, ACCESS
    movff       saved_w_b0_phys, addr_low_counter_or_payload_scratch_phys
    movff       status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys, addr_high_table_row_or_checksum_scratch_phys
    call        timer3_arm_interrupt_countdown, 0x0
uart_rx_with_framing__poll_ring:
    call        rx_ring_has_data, 0x0

    bz          uart_rx_with_framing__check_timeout_and_limits
    movff       adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys, eeprom_mask_or_flash_src_high_scratch_phys
    call        rx_ring_read, 0x0
    movwf       flash_block_or_uart_byte_scratch_byte, ACCESS
    movf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, W, ACCESS
    bz          uart_rx_with_framing__wait_for_colon
    movf        flash_upper_or_uart_count_scratch_byte, W, ACCESS
    addwf       count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      flash_end_high_or_loop_mask_scratch_byte, W, ACCESS
    movwf       FSR2H, ACCESS
    movff       adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys, INDF2
    incf        flash_upper_or_uart_count_scratch_byte, F, ACCESS
    bra         uart_rx_with_framing__check_crlf_terminator
uart_rx_with_framing__wait_for_colon:
    movf        flash_block_or_uart_byte_scratch_byte, W, ACCESS
    xorlw       0x3A
    bnz         uart_rx_with_framing__check_crlf_terminator
    movlw       0x01
    movwf       i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
uart_rx_with_framing__check_crlf_terminator:
    clrf        uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, ACCESS
    movf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, W, ACCESS
    bz          uart_rx_with_framing__latch_record_complete_flag
    movf        eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS
    xorlw       0x0D
    bnz         uart_rx_with_framing__latch_record_complete_flag
    movf        flash_block_or_uart_byte_scratch_byte, W, ACCESS
    xorlw       0x0A
    bnz         uart_rx_with_framing__latch_record_complete_flag
    movlw       0x01
    movwf       uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, ACCESS
uart_rx_with_framing__latch_record_complete_flag:
    movff       timeout_hi_b0_phys, timeout_lo_b0_phys
uart_rx_with_framing__check_timeout_and_limits:
    call        timer3_timeout_elapsed_carry, 0x0
    bc          uart_rx_with_framing__stop_timer_return_count
    movf        flash_src_low_or_rx_length_scratch_byte, W, ACCESS
    subwf       flash_upper_or_uart_count_scratch_byte, W, ACCESS
    bc          uart_rx_with_framing__stop_timer_return_count
    movf        eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, W, ACCESS
    bz          uart_rx_with_framing__poll_ring
uart_rx_with_framing__stop_timer_return_count:
    call        timer3_stop_interrupt_countdown, 0x0
    movf        flash_upper_or_uart_count_scratch_byte, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: isr_high_priority_dispatch              (single high-priority ISR)
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
;              advance_preset_job_state_machine sees the zero and advances to APPLY.
;   3. RCIF  : UART RX byte. Stores RCREG into ring at 0x0200+rx_ring_wr,
;              wraps at 0xC0 (192-byte ring). BUG M6: no overflow detection
;              if rx_ring_wr catches up to rx_ring_rd; oldest byte is silently
;              overwritten. The V3.2 hardening plan workstream 2 calls for a
;              full/overflow flag here.
;   4. OERR  : RCSTA.OERR set → full soft-recover: CREN=0, drain RCREG twice,
;              CREN=1, then reset the ring / staged parser bytes so the next
;              byte is consumed as a fresh route byte.
; ---------------------------------------------------------------------------
isr_high_priority_dispatch:
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
    rcall       timer3_reload_high_speed_tick_preload                   ; reload 0xF830 → ~10 ms @ Fosc/4
    bsf         T3CON, 0, ACCESS
    bcf         PIR2, 1, ACCESS                      ; clear TMR3IF
    movlb       0x0
    movf        preset_hold_timer_hi_b0, W, BANKED                 ; HOLDING countdown {hi,lo}
    iorwf       preset_hold_timer_lo_b0, W, BANKED
    bz          main_isr_dispatch__stop_timer3_hold_countdown          ; reached zero -> stop Timer3
    decf        preset_hold_timer_lo_b0, F, BANKED                 ; 16-bit countdown decrement
    btfss       STATUS, 0, ACCESS                    ; borrow into hi byte?
    decf        preset_hold_timer_hi_b0, F, BANKED
    bra         uart_rx_irq_enqueue
main_isr_dispatch__stop_timer3_hold_countdown:
    bcf         T3CON, 0, ACCESS                     ; HOLDING expired: T3 off
    bcf         PIE2, 1, ACCESS                      ; mask Timer3 IE until next job
uart_rx_irq_enqueue:
    btfss       PIR1, 5, ACCESS                      ; RCIF — UART byte arrived?
    bra         main_isr_dispatch__restore_fsr2_and_return
    movlb       0x0
    movlw       0xC0
    cpfslt      rx_ring_wr_b0, BANKED                ; invalid wr >= ring size?
    clrf        rx_ring_wr_b0, BANKED                ; heal before indirect write
    movf        rx_ring_wr_b0, W, BANKED                ; FSR2 = 0x0200 + rx_ring_wr
    call        setup_fsr2_page2_from_w, 0x0               ; W05-E02: FSR2=0x0200|W (movff uses no W)
    movff       RCREG, INDF2                         ; copy RX byte into ring
    incf        rx_ring_wr_b0, F, BANKED
    movlw       0xBF                                 ; ring size = 0xC0 (192 bytes)
    cpfsgt      rx_ring_wr_b0, BANKED                   ; wr > 0xBF -> wrap
    bra         uart_oerr_recover
    clrf        rx_ring_wr_b0, BANKED                   ; wrap to 0
uart_oerr_recover:
    btfss       RCSTA, 1, ACCESS                     ; OERR? (RX overrun)
    bra         main_isr_dispatch__restore_fsr2_and_return
    call        uart_soft_recover_full, 0x0
main_isr_dispatch__restore_fsr2_and_return:
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
; data byte then runs timer3_blocking_delay_1ms to insert a Timer3 1 ms inter-
; frame delay so the receiver's 3-byte parser does not re-sync.
;
; Cross-ref: docs/analysis/SEMANTIC_FUNCTION_MAP.md — note that BF/29 is sent
; separately by report_cmd29_status, NOT here.
; ---------------------------------------------------------------------------
send_status_burst:
    call        mark_chain_tx_emitted_bsr0, 0x0
    movlw       0x05
    rcall       send_status_burst_preamble
    movf        src_route_status_code_acc, W, ACCESS
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
    movf        hid_opcode04_arg2_or_cmd1d_setup_b0, W, BANKED
    goto        uart_tx_byte_blocking

send_status_burst_preamble:
    movwf       i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    call        bf_byte_tx, 0x0
    movf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, W, ACCESS
    goto        uart_tx_byte_blocking

send_status_burst_postamble:
    call        uart_tx_byte_blocking, 0x0
    goto        timer3_blocking_delay_1ms


; ---------------------------------------------------------------------------
; Helper: program_uart_31250_baud_common (W04-E05 size-opt helper)
; SPBRG/SPBRGH program for 31,250 baud on the 8 MHz INTOSC post-prescaler,
; then drop OSCCON bit 1 (select low-power oscillator group for the UART
; pre-timer gate).  Shared prefix of the wake / adaptive-baud / standby-
; shutdown paths.
; ---------------------------------------------------------------------------
program_uart_31250_baud_common:
    clrf        SPBRGH, ACCESS
    movlw       0x7F
    movwf       SPBRG, ACCESS
    bcf         OSCCON, 1, ACCESS
    return      0


compare_adc_rail_sample_to_threshold_w:
    movlb       0x0
    subwf       adc_rail_sample_lo_b0, W, BANKED
    movlw       0x02
    subwfb      adc_rail_sample_hi_b0, W, BANKED
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
; received while standby_event_dispatch's run_wake_rail_gate_and_dsp_cold_init path runs after the
; AN0 rail comes back up.
; ---------------------------------------------------------------------------
hw_standby_shutdown:
    movlw       LOW(hw_standby_shutdown_i2c_table)
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(hw_standby_shutdown_i2c_table)
    movwf       TBLPTRH, ACCESS
    movlw       0x03
    rcall       i2c_secondary_write_table_rows
    btfss       PORTC, 2, ACCESS
    bra         hw_standby_shutdown__select_master_baud
    rcall       uart_baud_chain_role_prefix
    bra         hw_standby_shutdown__drop_outputs_after_baud_select
hw_standby_shutdown__select_master_baud:
    bcf         LATB, 2, ACCESS
    rcall       program_uart_31250_baud_common
hw_standby_shutdown__drop_outputs_after_baud_select:
    bcf         LATB, 4, ACCESS
    rcall       clear_lata_audio_pins
    movlw       0x28
    rcall       compare_adc_rail_sample_to_threshold_w
    bc          hw_standby_shutdown__stop_timer0_and_usb
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    clrf        flash_src_low_or_rx_length_scratch_byte, ACCESS
hw_standby_shutdown__rail_discharge_pulse_loop:
    movff       computed_volume_or_i2c_payload_or_float32_scale_or_adc_eeprom_hi_phys, status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys
    movlw       0x1C
    rcall       i2c_secondary_dev_write_call_range_trampoline
    movlw       0x01
    xorwf       flash_end_high_or_loop_mask_scratch_byte, F, ACCESS
    movlw       0xFA
    rcall       timer3_blocking_delay_ms_from_w      ; W04-E08 factored (250 ms pulse)
    incf        flash_src_low_or_rx_length_scratch_byte, F, ACCESS
    movlw       0x04
    cpfsgt      flash_src_low_or_rx_length_scratch_byte, ACCESS
    bra         hw_standby_shutdown__rail_discharge_pulse_loop
hw_standby_shutdown__stop_timer0_and_usb:
    bcf         LATB, 3, ACCESS
    bcf         T0CON, 7, ACCESS
    bcf         INTCON, 5, ACCESS
    goto        usb_shutdown

hw_standby_shutdown_i2c_table:
    db          0x00,0x1B, 0x00,0x1C, 0x00,0x1D


; ---------------------------------------------------------------------------
; Function: usb_ep1_out_copy_packet_if_ready
; Address : 0x3C82
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep1_out_copy_packet_if_ready:
    movlb       0x0
    clrf        usb_ep1_out_copy_offset_b0, BANKED
    movlb       0x4
    btfsc       usb_ep1_out_bd_status_b4, 7, BANKED
    return      0
    movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS
    subwf       usb_ep1_out_bd_count_b4, W, BANKED
    btfss       STATUS, 0, ACCESS
    movff       usb_ep1_out_bd_count_phys, saved_w_b0_phys
    movlb       0x0
    clrf        usb_ep1_out_copy_offset_b0, BANKED
    bra         usb_ep1_out_copy_packet_if_ready__check_remaining
usb_ep1_out_copy_packet_if_ready__copy_next_byte:
    movlw       0x2C
    addwf       usb_ep1_out_copy_offset_b0, W, BANKED
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x04
    addwfc      FSR2H, F, ACCESS
    movf        usb_ep1_out_copy_offset_b0, W, BANKED
    addwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    movwf       FSR1L, ACCESS
    movlw       0x00
    addwfc      addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    movwf       FSR1H, ACCESS
    movff       INDF2, INDF1
    incf        usb_ep1_out_copy_offset_b0, F, BANKED
usb_ep1_out_copy_packet_if_ready__check_remaining:
    movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS
    subwf       usb_ep1_out_copy_offset_b0, W, BANKED
    bnc         usb_ep1_out_copy_packet_if_ready__copy_next_byte
    movlb       0x4
    movlw       0x40
    movwf       usb_ep1_out_bd_count_b4, BANKED
    lfsr        FSR0, usb_ep1_out_bd_status_phys
    bra         usb_endpoint_mark_state_done


; ---------------------------------------------------------------------------
; Function: fw_update_signature_status_word_helper        (cold init / RAM zero / boot trampoline)
; Address : 0x3CE8
; ---------------------------------------------------------------------------
; Two distinct entry points share the address window:
;
;   fw_update_signature_status_word_helper (helper):
;     Filter on a 4-byte signature loaded by the caller via FSR2 starting at
;     RAM 0x0003. If all four bytes are zero, write a zero pair into RAM at
;     ram_0x007 and return. Otherwise unpack ram_0x005/0x006 into a
;     {ram_0x009,0x00A} 16-bit word, OR a status bit (ram_0x005.bit7) into
;     it, then add 0xFF82 (i.e. -0x7E) to commit the result back to FSR2.
;     This is the tiny helper used during EEPROM/flash signature checks
;     (called from the firmware-update path).
;
;   boot_cold_init__clear_ram_and_runtime_state (cold-boot entry — actual reset target):
;     The branch target stored at 0x1014 jumps here. It clears all of
;     {0x0300, 0x0200, 0x0100, 0x0060} RAM blocks (the entire usable RAM
;     bank set), then continues into peripheral init: TBLPTR seeded for
;     fw_update_status_text_seed_table (the FW-update string), TRISA/B/C set per
;     PIN_SEMANTICS.md (TRISA=0x07, TRISB=0x00, TRISC=0x87), ADCON0/1
;     configured (AN0 analog), MSSP and EUSART (31,250 baud) brought up,
;     then drops into run_main_foreground_loop.
; ---------------------------------------------------------------------------
fw_update_signature_status_word_helper:
    lfsr        FSR2, addr_low_counter_or_payload_scratch_phys
    movf        POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    iorwf       POSTINC2, W, ACCESS
    bnz         fw_update_signature_status_word_helper__decode_nonzero_signature
    rcall       fw_update_signature_load_fsr2_from_status_ptr
    clrf        POSTINC2, ACCESS
    clrf        POSTDEC2, ACCESS
    bra         fw_update_signature_status_word_helper__return
fw_update_signature_status_word_helper__decode_nonzero_signature:
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    andlw       0x7F
    movwf       flash_end_high_or_loop_mask_scratch_byte, ACCESS
    bcf         STATUS, 0, ACCESS
    rlcf        flash_end_high_or_loop_mask_scratch_byte, W, ACCESS
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    clrf        eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    rlcf        eeprom_mask_or_flash_src_high_scratch_byte, F, ACCESS
    rcall       fw_update_signature_load_fsr2_from_status_ptr
    movff       eeprom_or_filename_data_or_flash_buffer_ptr_low_or_signature_low_phys, POSTINC2
    movff       eeprom_mask_or_flash_src_high_scratch_phys, POSTDEC2
    rcall       fw_update_signature_load_fsr2_from_status_ptr
    btfsc       length_mask_or_divisor_low_scratch_byte, 7, ACCESS
    bsf         INDF2, 0, ACCESS
    rcall       fw_update_signature_load_fsr2_from_status_ptr
    movlw       0x82
    addwf       POSTINC2, F, ACCESS
    movlw       0xFF
    addwfc      POSTDEC2, F, ACCESS
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    andlw       0x80
    iorlw       0x3F
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    bcf         length_mask_or_divisor_low_scratch_byte, 7, ACCESS
fw_update_signature_status_word_helper__return:
    return      0

fw_update_signature_load_fsr2_from_status_ptr:
    movf        count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    return      0

clear_postinc0_count_w:
    clrf        POSTINC0, ACCESS
    decf        WREG, F, ACCESS
    bnz         clear_postinc0_count_w
    return      0

boot_cold_init__clear_ram_and_runtime_state:
    lfsr        FSR0, cold_init_bank3_clear_base_phys
    movlw       0xC0
    rcall       clear_postinc0_count_w
    lfsr        FSR0, cold_init_bank2_clear_base_phys
    movlw       0xDE
    rcall       clear_postinc0_count_w
    lfsr        FSR0, cold_init_bank1_clear_base_phys
    movlw       0xE5
    rcall       clear_postinc0_count_w
    lfsr        FSR0, channel_1_source_config_phys
    movlw       0x8D
    rcall       clear_postinc0_count_w

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
    rcall       clear_postinc0_count_w

    ; --- V3.4 SRC/DSP forensic counter clear (BANK 3 upper block) ---
    ; diag_src_n..diag_src_m (0x3C0..0x3C4) live in wipe-protected BANK 3
    ; upper, so this range clear is the only thing that ever zeroes them —
    ; same unconditional-clear rationale as the BANK 2 diag block above.
    lfsr        FSR0, diag_src_n
    movlw       0x05
    rcall       clear_postinc0_count_w

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

    clrf        src_route_status_code_acc, ACCESS
    clrf        active_flags_acc, ACCESS
    movlw       LOW(fw_update_status_text_seed_table)         ; TBLPTR -> fw_update_status_text_seed_table
    movwf       TBLPTRL, ACCESS
    movlw       HIGH(fw_update_status_text_seed_table)
    movwf       TBLPTRH, ACCESS
    movlw       UPPER(fw_update_status_text_seed_table)
    movwf       TBLPTRU, ACCESS
    lfsr        FSR0, fw_update_fail_status_text_phys
    lfsr        FSR1, flash_addr_shadow_upper_or_preset_job_index_or_init_copy_end_phys
boot_cold_init__copy_fw_update_status_text_seed:
    tblrd*+
    movff       TABLAT, POSTINC0
    movf        POSTDEC1, W, ACCESS
    movf        FSR1L, W, ACCESS
    bnz         boot_cold_init__copy_fw_update_status_text_seed
    movlw       UPPER(0x0000)                       ; clear TBLPTRU to program space
    movwf       TBLPTRU, ACCESS
    movlb       0x0
    goto        boot_cold_init__run_peripheral_init

; ---------------------------------------------------------------------------
; Function: flash_erase                    (64-byte block erase w/ A/B remap)
; Address : 0x3DAC
; ---------------------------------------------------------------------------
; Erases program memory in 64-byte blocks from start ram_0x003:006 to end
; ram_0x007:00A (inclusive). EECON1 EEPGD=1, CFGS=0, FREE=1, WREN=1 with
; the standard PIC18 unlock sequence handed off to nvm_unlock_and_set_wr.
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
    bra         flash_erase_without_preset_remap
    ; Remap start address (ram_0x004 = TBLPTRH)
    call        flash_remap_preset_b_start_address, 0x0
flash_erase__remap_end_address:
    ; Remap end address (ram_0x008 = end TBLPTRH)
    movf        eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS
    iorwf       flash_src_low_or_rx_length_scratch_byte, W, ACCESS
    bnz         flash_erase_without_preset_remap
    movlw       0x56
    subwf       flash_end_high_or_loop_mask_scratch_byte, W, ACCESS
    bnc         flash_erase_without_preset_remap
    movlw       0x60
    subwf       flash_end_high_or_loop_mask_scratch_byte, W, ACCESS
    bc          flash_erase_without_preset_remap
    movlw       0x0A
    subwf       flash_end_high_or_loop_mask_scratch_byte, F, ACCESS
flash_erase_without_preset_remap:
    clrf        eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, ACCESS
    rcall       chain_copy_call_range_trampoline_mid ; size T151: flash erase address save
    db          0x00, 0x00, addr_low_counter_or_payload_scratch_operand, timeout_hi_acc_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    bra         flash_erase__check_end_address
flash_erase__stage_next_block:
    movff       flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys, TBLPTRU
    movff       flash_saved_tblptrh_phys, TBLPTRH
    movff       timeout_hi_b0_phys, TBLPTRL
    bsf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    bsf         EECON1, 4, ACCESS
    btfss       INTCON, 7, ACCESS
    bra         flash_erase__unlock_and_advance_block
    bcf         INTCON, 7, ACCESS
    movlw       0x01
    movwf       eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, ACCESS
flash_erase__unlock_and_advance_block:
    rcall       nvm_unlock_and_set_wr
    tstfsz      eeprom_gate_flash_gie_or_uart_timeout_scratch_byte, ACCESS
    bsf         INTCON, 7, ACCESS
    movlw       0x40
    addwf       uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, F, ACCESS
    movlw       0x00
    addwfc      i2c_flag_or_flash_math_uart_cmd_scratch_byte, F, ACCESS
    addwfc      flash_upper_or_uart_count_scratch_byte, F, ACCESS
    addwfc      flash_block_or_uart_byte_scratch_byte, F, ACCESS
flash_erase__check_end_address:
    movf        count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    subwf       uart_channel_index_or_flash_addr_low_or_float32_rx_scratch, W, ACCESS
    movf        flash_end_high_or_loop_mask_scratch_byte, W, ACCESS
    subwfb      i2c_flag_or_flash_math_uart_cmd_scratch_byte, W, ACCESS
    movf        flash_src_low_or_rx_length_scratch_byte, W, ACCESS
    subwfb      flash_upper_or_uart_count_scratch_byte, W, ACCESS
    movf        eeprom_mask_or_flash_src_high_scratch_byte, W, ACCESS
    subwfb      flash_block_or_uart_byte_scratch_byte, W, ACCESS
    btfsc       STATUS, 0, ACCESS
    return      0
    bra         flash_erase__stage_next_block


; ---------------------------------------------------------------------------
; Function: int32_to_float32_and_save
; Address : 0x3E0A
; Notes   : Inferred core helper routine. Calls: float32_pack_mantissa_exponent_sign.
; ---------------------------------------------------------------------------
int32_to_float32_and_save:
    clrf        float_loop_or_tblptr_low_scratch_byte, ACCESS
    movf        flash_gie_or_float_sign_scratch_byte, W, ACCESS
    xorlw       0x80
    addlw       0x80
    bnz         int32_to_float32_and_save__maybe_negate_magnitude
    movlw       0x00
    subwf       flash_block_or_uart_byte_scratch_byte, W, ACCESS
    bnz         int32_to_float32_and_save__maybe_negate_magnitude
    movlw       0x00
    subwf       flash_upper_or_uart_count_scratch_byte, W, ACCESS
    bnz         int32_to_float32_and_save__maybe_negate_magnitude
    movlw       0x00
    subwf       i2c_flag_or_flash_math_uart_cmd_scratch_byte, W, ACCESS
int32_to_float32_and_save__maybe_negate_magnitude:
    bc          int32_to_float32_and_save__pack_result
    comf        flash_gie_or_float_sign_scratch_byte, F, ACCESS
    comf        flash_block_or_uart_byte_scratch_byte, F, ACCESS
    comf        flash_upper_or_uart_count_scratch_byte, F, ACCESS
    negf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    movlw       0x00
    addwfc      flash_upper_or_uart_count_scratch_byte, F, ACCESS
    addwfc      flash_block_or_uart_byte_scratch_byte, F, ACCESS
    addwfc      flash_gie_or_float_sign_scratch_byte, F, ACCESS
    movlw       0x01
    movwf       float_loop_or_tblptr_low_scratch_byte, ACCESS
int32_to_float32_and_save__pack_result:
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, float32_coeff_or_volume_work_operand_op, addr_low_counter_or_payload_scratch_operand, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movlw       0x96
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    movff       flash_addr_low_or_float32_scale_or_flash_read_tblptru_save_phys, computed_volume_or_i2c_payload_or_float32_scale_or_adc_eeprom_hi_phys
    ; W04-E01: factor call+4 movff tail into float32_pack_mantissa_exponent_sign_and_save
    goto        float32_pack_mantissa_exponent_sign_and_save

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
    movff       SSPCON1, addr_high_table_row_or_checksum_scratch_phys
    movlw       0x0F
    andwf       addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    movf        addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
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
    movwf       saved_w_acc, ACCESS
    movwf       SSPBUF, ACCESS
    btfsc       SSPCON1, 7, ACCESS
    bra         i2c_byte_tx__timeout_recover
    rcall       sspcon1_masked_w
    xorlw       0x08
    bz          i2c_byte_tx__recheck_master_mode
    rcall       sspcon1_masked_w
    xorlw       0x0B
    bz          i2c_byte_tx__recheck_master_mode
    bsf         SSPCON1, 4, ACCESS
i2c_byte_tx__wait_sspif_slave_mode:
    call        wait_sspif_bounded, 0x0
    bc          i2c_byte_tx__timeout_recover
    btfss       SSPSTAT, 2, ACCESS
    movf        SSPSTAT, W, ACCESS
    bra         i2c_byte_tx__return
i2c_byte_tx__recheck_master_mode:
    ; Re-check mode (stock pattern preserved)
    rcall       sspcon1_masked_w
    xorlw       0x08
    bz          i2c_byte_tx__wait_bf_clear_master
    rcall       sspcon1_masked_w
    xorlw       0x0B
    bnz         i2c_byte_tx__return
i2c_byte_tx__wait_bf_clear_master:
    ; V3.1: bounded BF wait (stock was unbounded loop)
    call        wait_bf_clear_bounded, 0x0
    bc          i2c_byte_tx__return
    call        i2c_wait_bus_idle, 0x0
    ; V3.1 Fix A: ACKSTAT check after successful master TX
    ; Save/restore BSR — callers may have any bank selected and stock
    ; i2c_byte_tx never touched BSR.
    movff       BSR, flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys              ; save caller's BSR
    movlb       0x0
    btfss       SSPCON2, 6, ACCESS          ; skip if NACK (ACKSTAT=1)
    bra         i2c_byte_tx__ack_received_restore_bsr
    bsf         dsp_fault_flags_b0, 2, BANKED  ; latch ACKSTAT fault
    diag_inc_sat diag_i                      ; V3.2 Layer 5: count I2C transport fault
i2c_byte_tx__ack_received_restore_bsr:
    movff       flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys, BSR              ; restore caller's BSR (also undoes any macro BSR clobber)
    movf        SSPCON2, W, ACCESS
i2c_byte_tx__return:
    return      0
i2c_byte_tx__timeout_recover:
    goto        i2c_timeout_recover_advertise

chain_copy_call_range_trampoline_mid:
    goto        chain_copy

copy_four_bytes_fsr2_to_fsr1:
    movlw       0x04
copy_w_bytes_fsr2_to_fsr1:
    movff       POSTINC2, POSTINC1
    decfsz      WREG, F, ACCESS
    bra         copy_w_bytes_fsr2_to_fsr1
    return      0

copy_four_bytes_fsr0_to_fsr2_rewind2:
    movlw       0x04
copy_four_bytes_fsr0_to_fsr2_rewind2__copy_next:
    movff       POSTINC0, POSTINC2
    decfsz      WREG, F, ACCESS
    bra         copy_four_bytes_fsr0_to_fsr2_rewind2__copy_next
    decf        FSR2L, F, ACCESS
    decf        FSR2L, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: float32_multiply_ram_window_by_staged_operand_in_place
; Address : 0x3EC4
; Notes   : Inferred core helper routine. Calls: float32_multiply_primary_by_secondary_in_place.
; ---------------------------------------------------------------------------
float32_multiply_ram_window_by_staged_operand_in_place:
    movwf       float32_sign_exponent_offset_scratch_acc, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    lfsr        FSR1, fw_update_byte_or_flash_addr_mid_or_float_operand_base_phys
    rcall       copy_four_bytes_fsr2_to_fsr1
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, float32_math_operand_byte0_op, float32_multiply_secondary_operand_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    call        float32_multiply_primary_by_secondary_in_place, 0x0
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, float32_i2c_coeff_or_volume_work_operand_op, float32_secondary_work_byte0_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movf        float32_sign_exponent_offset_scratch_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    lfsr        FSR0, float32_secondary_work_byte0_b0_phys
    rcall       copy_four_bytes_fsr0_to_fsr2_rewind2
rewind_fsr2_after_four_byte_math_result_store:
    decf        FSR2L, F, ACCESS
    decf        FSR2L, F, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: float32_add_staged_operand_to_ram_window_in_place
; Address : 0x3F1E
; Notes   : Inferred core helper routine. Calls: float32_add_secondary_to_primary_in_place.
; ---------------------------------------------------------------------------
float32_add_staged_operand_to_ram_window_in_place:
    movwf       float32_exponent_lo_or_target_offset_scratch_acc, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    lfsr        FSR1, float32_accum_work_byte0_b0_phys
    rcall       copy_four_bytes_fsr2_to_fsr1
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, float32_transform_shadow_dword_op, float32_aux_work_byte0_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    call        float32_add_secondary_to_primary_in_place, 0x0
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, float32_accum_work_byte0_op, math_temp_result_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movf        float32_exponent_lo_or_target_offset_scratch_acc, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    lfsr        FSR0, math_temp_result_buffer_phys
    rcall       copy_four_bytes_fsr0_to_fsr2_rewind2
    bra         rewind_fsr2_after_four_byte_math_result_store


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
    movwf       saved_w_acc, ACCESS
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movlw       0x2F
    cpfsgt      length_mask_or_divisor_low_scratch_byte, ACCESS
    bra         intel_hex_checksum_update__decode_high_alpha_nibble
    movlw       0x3A
    subwf       length_mask_or_divisor_low_scratch_byte, W, ACCESS
    bc          intel_hex_checksum_update__decode_high_alpha_nibble
    movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS
    addlw       0xD0
    bra         intel_hex_checksum_update__store_high_nibble
intel_hex_checksum_update__decode_high_alpha_nibble:
    movlw       0x40
    cpfsgt      length_mask_or_divisor_low_scratch_byte, ACCESS
    bra         intel_hex_checksum_update__decode_low_nibble
    movlw       0x47
    subwf       length_mask_or_divisor_low_scratch_byte, W, ACCESS
    bc          intel_hex_checksum_update__decode_low_nibble
    movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS
    addlw       0xC9
intel_hex_checksum_update__store_high_nibble:
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
intel_hex_checksum_update__decode_low_nibble:
    swapf       addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    movlw       0xF0
    andwf       addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    movlw       0x2F
    cpfsgt      addr_low_counter_or_payload_scratch_byte, ACCESS
    bra         intel_hex_checksum_update__decode_low_alpha_nibble
    movlw       0x3A
    subwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    bc          intel_hex_checksum_update__decode_low_alpha_nibble
    movf        addr_low_counter_or_payload_scratch_byte, W, ACCESS
    addlw       0xD0
    bra         intel_hex_checksum_update__add_low_nibble
intel_hex_checksum_update__decode_low_alpha_nibble:
    movlw       0x40
    cpfsgt      addr_low_counter_or_payload_scratch_byte, ACCESS
    bra         intel_hex_checksum_update__return_decoded_byte
    movlw       0x47
    subwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    bc          intel_hex_checksum_update__return_decoded_byte
    movf        addr_low_counter_or_payload_scratch_byte, W, ACCESS
    addlw       0xC9
intel_hex_checksum_update__add_low_nibble:
    addwf       addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
intel_hex_checksum_update__return_decoded_byte:
    movf        addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep1_in_copy_scratch_buffer_to_bdt
; Address : 0x3FD0
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep1_in_send_hid_reply_buffer:
    call        ram_clear_prepare_page1_address_high, 0x0
    movlw       0x5A
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    movlw       0x40
    movwf       length_mask_or_divisor_low_scratch_byte, ACCESS

usb_ep1_in_copy_scratch_buffer_to_bdt:
    movlw       0x40
    cpfsgt      length_mask_or_divisor_low_scratch_byte, ACCESS
    bra         usb_ep1_in_copy_scratch_buffer_to_bdt__length_clamped
    movwf       length_mask_or_divisor_low_scratch_byte, ACCESS
usb_ep1_in_copy_scratch_buffer_to_bdt__length_clamped:
    clrf        count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    bra         usb_ep1_in_copy_scratch_buffer_to_bdt__check_remaining
usb_ep1_in_copy_scratch_buffer_to_bdt__copy_next_byte:
    movf        count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    rcall       fsr2_from_scratch_base_plus_w
    movlw       0x6C
    addwf       count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    movwf       FSR1L, ACCESS
    clrf        FSR1H, ACCESS
    movlw       0x04
    addwfc      FSR1H, F, ACCESS
    movff       INDF2, INDF1
    incf        count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS
usb_ep1_in_copy_scratch_buffer_to_bdt__check_remaining:
    movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS
    subwf       count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    bnc         usb_ep1_in_copy_scratch_buffer_to_bdt__copy_next_byte
    movff       saved_w_b0_phys, usb_ep1_in_bd_count_phys
    lfsr        FSR0, usb_ep1_in_bd_status_phys

; Shared USB endpoint completion-marker tail for the endpoint buffer helpers.
; in : FSR0 points at the bank-4 endpoint state byte (stock_40C or stock_410).
; out: same byte marked bit3/bit7 done, bit6 normalized through stock_006.
usb_endpoint_mark_state_done:
    movlw       0x40
    andwf       INDF0, F, ACCESS
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    btfss       INDF0, 6, ACCESS
    incf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    swapf       status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    rlncf       status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    rlncf       status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    movf        INDF0, W, ACCESS
    xorwf       status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    andlw       0xBF
    xorwf       status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    movwf       INDF0, ACCESS
    bsf         INDF0, 3, ACCESS
    bsf         INDF0, 7, ACCESS
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
; Used by: preset apply (preset_table_apply_entry_legacy_blocking, preset_job_apply_i2c_entry),
; HID memread, EEPROM-writeback signature paths, flash_erase auto-arm.
; ---------------------------------------------------------------------------

; ---------------------------------------------------------------------------
; Helper: flash_read_to_scratch_buffer (W05-E04 size-opt helper)
; Shared preamble used by 3 callers that want FSR2 dest = 0x0017 (RAM
; scratch) for the next flash_read.  Clears the dest-high byte
; (ram_0x00A) and loads 0x17 into dest-low (ram_0x009), then falls
; through to flash_read so the stacked return goes directly back to the
; original caller.  No explicit branch needed -- the helper body is
; immediately above flash_read's entry point.
; ---------------------------------------------------------------------------
flash_read_to_scratch_buffer:
    clrf        eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    movlw       0x17
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    ; fall through into flash_read
flash_read:
    call        flash_remap_preset_b_start_address_if_active, 0x0
flash_read_without_preset_remap:
    movff       TBLPTRU, flash_addr_low_or_float32_scale_or_flash_read_tblptru_save_phys
    movff       TBLPTRH, float32_sign_or_uart_digit_or_flash_read_tblptrh_save_phys
    movff       TBLPTRL, adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys
    movff       saved_w_b0_phys, TBLPTRU
    movff       addr_high_table_row_or_checksum_scratch_phys, TBLPTRH
    movff       addr_low_counter_or_payload_scratch_phys, TBLPTRL
    bra         flash_read__test_remaining_byte_count

flash_read_without_preset_remap_to_scratch_buffer:
    clrf        eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    movlw       0x17
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    bra         flash_read_without_preset_remap
flash_read__copy_next_program_byte:
    tblrd*+
    movff       eeprom_or_filename_data_or_flash_buffer_ptr_low_or_signature_low_phys, FSR2L
    movff       eeprom_mask_or_flash_src_high_scratch_phys, FSR2H
    movff       TABLAT, INDF2
    infsnz      flash_src_low_or_rx_length_scratch_byte, F, ACCESS
    incf        eeprom_mask_or_flash_src_high_scratch_byte, F, ACCESS
flash_read__test_remaining_byte_count:
    decf        count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        flash_end_high_or_loop_mask_scratch_byte, F, ACCESS
    incf        count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    incf        flash_end_high_or_loop_mask_scratch_byte, W, ACCESS
    bnz         flash_read__copy_next_program_byte
    movff       flash_addr_low_or_float32_scale_or_flash_read_tblptru_save_phys, TBLPTRU
    movff       float32_sign_or_uart_digit_or_flash_read_tblptrh_save_phys, TBLPTRH
    movff       adc_loop_value_or_uart_rx_byte_or_flash_read_tblptrl_save_phys, TBLPTRL
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_arm_out_pingpong_bd
; Address : 0x4080
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_ep0_arm_out_pingpong_bd:
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    movlw       0x08
    movlb       0x1
    movwf       usb_bdt_template_count_b1, BANKED
    movlw       0x04
    movwf       usb_bdt_template_addr_hi_b1, BANKED
    movwf       FSR2H, ACCESS
    movlw       0x1C
    movwf       usb_bdt_template_addr_lo_b1, BANKED
    tstfsz      addr_low_counter_or_payload_scratch_byte, ACCESS
    bra         usb_ep0_arm_out_pingpong_bd__select_odd_bd
    movlw       0x14
    movwf       usb_bdt_template_addr_lo_b1, BANKED
    movlw       0x00
    bra         usb_ep0_arm_out_pingpong_bd__copy_template_and_set_own
usb_ep0_arm_out_pingpong_bd__select_odd_bd:
    movlw       0x04
usb_ep0_arm_out_pingpong_bd__copy_template_and_set_own:
    movwf       FSR2L, ACCESS
    lfsr        FSR0, usb_bdt_template_status_phys
    movlw       0x04
    call        hid_diag_snapshot_copy_block_count_w, 0x0
    movlw       0xFC
    addwf       FSR2L, F, ACCESS
    bsf         INDF2, 7, ACCESS
    movlb       0x0
    return      0

usb_clear_uep1_7:
    clrf        UEP1, ACCESS
    clrf        UEP2, ACCESS
    clrf        UEP3, ACCESS
    clrf        UEP4, ACCESS
    clrf        UEP5, ACCESS
    clrf        UEP6, ACCESS
    clrf        UEP7, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: usb_bus_reset_reinitialize
; Address : 0x40D6
; Notes   : Inferred usb helper; touches usb. Calls: usb_disconnect_handler, usb_ep0_arm_out_pingpong_bd.
; ---------------------------------------------------------------------------
usb_bus_reset_reinitialize:
    movlw       0x03
    movlb       0x0
    movwf       usb_device_state_b0, BANKED
    clrf        UEIE, ACCESS
    clrf        UIR, ACCESS
    movlw       0x7B
    movwf       UIE, ACCESS
    clrf        UADDR, ACCESS
    rcall       usb_clear_uep1_7
    movlw       0x16
    movwf       UEP0, ACCESS
    bsf         UCON, 6, ACCESS
    bra         usb_bus_reset_reinitialize__drain_transaction_flags
usb_bus_reset_reinitialize__clear_transaction_flag:
    bcf         UIR, 3, ACCESS
    clrwdt
usb_bus_reset_reinitialize__drain_transaction_flags:
    btfsc       UIR, 3, ACCESS
    bra         usb_bus_reset_reinitialize__clear_transaction_flag
    bcf         UCON, 6, ACCESS
    bcf         UCON, 4, ACCESS
    movlw       0x04
    rcall       usb_stage_bdt_template_status_w
    movlw       0x00
    rcall       usb_ep0_arm_out_pingpong_bd
    movlw       0x01
    movwf       usb_ep0_out_next_bd_toggle_b0, BANKED
    clrf        usb_ep0_control_flags_b0, BANKED
    clrf        usb_current_configuration_b0, BANKED
    movlw       0x00
    bra         usb_ep1_configure_if_enabled


; ---------------------------------------------------------------------------
; Function: adc_divide_staged_words
; Address : 0x4124
; Notes   : Inferred adc helper; touches adc.
; ---------------------------------------------------------------------------
adc_divide_staged_words:
    clrf        count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    iorwf       length_mask_or_divisor_low_scratch_byte, W, ACCESS
    bz          adc_divide_staged_words__store_quotient_result
    movlw       0x01
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    bra         adc_divide_staged_words__test_divisor_msb
adc_divide_staged_words__normalize_divisor_left:
    bcf         STATUS, 0, ACCESS
    rlcf        length_mask_or_divisor_low_scratch_byte, F, ACCESS
    rlcf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    incf        flash_src_low_or_rx_length_scratch_byte, F, ACCESS
adc_divide_staged_words__test_divisor_msb:
    btfss       status_addr_high_or_i2c_payload_scratch_byte, 7, ACCESS
    bra         adc_divide_staged_words__normalize_divisor_left
adc_divide_staged_words__next_quotient_bit:
    bcf         STATUS, 0, ACCESS
    rlcf        count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS
    rlcf        flash_end_high_or_loop_mask_scratch_byte, F, ACCESS
    rcall       adc_div_compare_subtract_staged_words
    btfsc       STATUS, 0, ACCESS
    bsf         count_flash_page_or_i2c_payload_scratch_byte, 0, ACCESS
adc_divide_staged_words__shift_divisor_right:
    bcf         STATUS, 0, ACCESS
    rrcf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    rrcf        length_mask_or_divisor_low_scratch_byte, F, ACCESS
    decfsz      flash_src_low_or_rx_length_scratch_byte, F, ACCESS
    bra         adc_divide_staged_words__next_quotient_bit
adc_divide_staged_words__store_quotient_result:
    movff       computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys, addr_low_counter_or_payload_scratch_phys
    movff       computed_volume_or_i2c_payload_or_float32_scale_or_adc_eeprom_hi_phys, addr_high_table_row_or_checksum_scratch_phys
    return      0

adc_div_compare_subtract_staged_words:
    movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS
    subwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    subwfb      addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    bnc         adc_div_compare_subtract_staged_words__return
    movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS
    subwf       addr_low_counter_or_payload_scratch_byte, F, ACCESS
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    subwfb      addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
adc_div_compare_subtract_staged_words__return:
    return      0

an0_hysteresis_monitor:
    movlb       0x0                                  ; callers may leave BSR=2; ram_0x0A1 is bank 0
    btfss       active_flags_acc, 3, ACCESS
    bra         an0_hysteresis_monitor__return
    movf        an0_delay_b0, W, BANKED
    xorlw       0x64
    bnz         an0_hysteresis_monitor__increment_delay_counter
    btfsc       ADCON0, 1, ACCESS
    bra         an0_hysteresis_monitor__reset_delay_counter
    movf        ADRESH, W, ACCESS
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    clrf        addr_low_counter_or_payload_scratch_byte, ACCESS
    movf        ADRESL, W, ACCESS
    addwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    movwf       adc_rail_sample_lo_b0, BANKED
    movlw       0x00
    addwfc      addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    movwf       adc_rail_sample_hi_b0, BANKED
    movlw       0x29
    rcall       compare_adc_rail_sample_to_threshold_w
    btfsc       STATUS, 0, ACCESS
    bsf         main_runtime_latch_flags_b0, 2, BANKED
    bsf         ADCON0, 1, ACCESS
    btfss       main_runtime_latch_flags_b0, 2, BANKED
    bra         an0_hysteresis_monitor__reset_delay_counter
    movlw       0x28
    rcall       compare_adc_rail_sample_to_threshold_w
    bc          an0_hysteresis_monitor__reset_delay_counter
    bcf         active_flags_acc, 3, ACCESS
    bsf         event_flags_b0, 2, BANKED
    diag_inc_sat diag_a                              ; V3.2 Layer 5: count AN0-triggered standby
    movlb       0x0                                  ; macro clobbers BSR; restore for the bra below
an0_hysteresis_monitor__reset_delay_counter:
    clrf        an0_delay_b0, BANKED
    bra         an0_hysteresis_monitor__return
an0_hysteresis_monitor__increment_delay_counter:
    incf        an0_delay_b0, F, BANKED
an0_hysteresis_monitor__return:
    return      0


; ---------------------------------------------------------------------------
; Function: format_int16_decimal_ascii_to_w_pointer
; Address : 0x41B6
; Notes   : Inferred core helper routine. Calls: format_uint16_radix_ascii_to_w_pointer.
; ---------------------------------------------------------------------------
format_int16_decimal_ascii_to_w_pointer:
    movwf       float_product_or_output_index_scratch_byte, ACCESS
    movwf       float_product_flash_addr_or_preset_index_scratch_byte, ACCESS
    movf        route_bit_or_tblptr_upper_scratch_byte, W, ACCESS
    rcall       signed_hi_bias80_compare_prelude
    btfsc       STATUS, 2, ACCESS
    subwf       float_divisor_or_preset_flag_scratch_byte, W, ACCESS
    bc          format_int16_decimal_ascii_to_w_pointer__format_magnitude
    movf        float_product_or_output_index_scratch_byte, W, ACCESS
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    movlw       0x2D
    movwf       INDF2, ACCESS
    incf        float_product_or_output_index_scratch_byte, F, ACCESS
    negf        float_divisor_or_preset_flag_scratch_byte, ACCESS
    comf        route_bit_or_tblptr_upper_scratch_byte, F, ACCESS
    btfsc       STATUS, 0, ACCESS
    incf        route_bit_or_tblptr_upper_scratch_byte, F, ACCESS
format_int16_decimal_ascii_to_w_pointer__format_magnitude:
    rcall       chain_copy_call_range_trampoline_mid ; size T151: filter helper address save
    db          0x00, 0x00, float32_i2c_coeff_or_volume_work_operand_op, numeric_format_value_dword_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    movf        float_product_or_output_index_scratch_byte, W, ACCESS
    call        format_uint16_radix_ascii_to_w_pointer, 0x0
    movf        float_product_flash_addr_or_preset_index_scratch_byte, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: timer3_reload_high_speed_tick_preload
; Notes   : Shared 0xF830 Timer3 preload. Leaves W=0x30 like inline callers.
; ---------------------------------------------------------------------------
timer3_reload_high_speed_tick_preload:
    movlw       0xF8
    movwf       TMR3H, ACCESS
    movlw       0x30
    movwf       TMR3L, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: usb_apply_set_configuration
; Address : 0x41FE
; Notes   : Inferred usb helper; touches usb. Calls: usb_ep1_configure_if_enabled.
; ---------------------------------------------------------------------------
usb_apply_set_configuration:
    movlw       0x01
    movwf       usb_ep0_control_response_mode_b0, BANKED
    rcall       usb_clear_uep1_7
    clrf        usb_reset_lowram_clear_index_b0, BANKED
usb_apply_set_configuration__clear_config_status_byte:
    movf        usb_reset_lowram_clear_index_b0, W, BANKED
    addlw       0xEC
    movwf       FSR2L, ACCESS
    clrf        FSR2H, ACCESS
    clrf        INDF2, ACCESS
    incf        usb_reset_lowram_clear_index_b0, F, BANKED
    movf        usb_reset_lowram_clear_index_b0, W, BANKED
    bz          usb_apply_set_configuration__clear_config_status_byte
    movff       usb_setup_w_value_lo_phys, usb_current_configuration_phys
    movf        usb_current_configuration_b0, W, BANKED
    rcall       usb_ep1_configure_if_enabled
    movlb       0x0
    tstfsz      usb_setup_w_value_lo_b0, BANKED
    bra         usb_apply_set_configuration__configured_state
    movlw       0x05
    bra         usb_apply_set_configuration__store_device_state
usb_apply_set_configuration__configured_state:
    movlw       0x06
usb_apply_set_configuration__store_device_state:
    movwf       usb_device_state_b0, BANKED
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
i2c_start_after_idle_bounded:
    rcall       i2c_wait_bus_idle
    bsf         SSPCON2, 0, ACCESS
    bra         wait_sen_bounded
i2c_secondary_dev_random_read:
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    rcall       i2c_start_after_idle_bounded
    bc          i2c_secondary_dev_random_timeout
    movlw       0xE2
    rcall       i2c_byte_tx
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    rcall       i2c_byte_tx
    bsf         SSPCON2, 1, ACCESS
    rcall       wait_rsen_bounded
    bc          i2c_secondary_dev_random_timeout
    movlw       0xE3
    rcall       i2c_byte_tx
    rcall       i2c_receive_sspbuf_bounded
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    bsf         SSPCON2, 5, ACCESS
    bsf         SSPCON2, 4, ACCESS
    rcall       wait_acken_bounded
    bc          i2c_secondary_dev_random_timeout
    bsf         SSPCON2, 2, ACCESS
    rcall       wait_pen_bounded
    bc          i2c_secondary_dev_random_pen_timeout
    movf        count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    bcf         STATUS, 0, ACCESS
    return      0
i2c_secondary_dev_random_timeout:
    rcall       i2c_timeout_recover_advertise
    clrf        WREG, ACCESS
    return      0
i2c_secondary_dev_random_pen_timeout:
    rcall       i2c_pen_timeout_recover_advertise
    clrf        WREG, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: adc_remainder_staged_words
; Address : 0x427A
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
adc_remainder_staged_words:
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    iorwf       length_mask_or_divisor_low_scratch_byte, W, ACCESS
    bz          adc_remainder_staged_words__return
    movlw       0x01
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    bra         adc_remainder_staged_words__test_divisor_msb
adc_remainder_staged_words__normalize_divisor_left:
    bcf         STATUS, 0, ACCESS
    rlcf        length_mask_or_divisor_low_scratch_byte, F, ACCESS
    rlcf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    incf        count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS
adc_remainder_staged_words__test_divisor_msb:
    btfss       status_addr_high_or_i2c_payload_scratch_byte, 7, ACCESS
    bra         adc_remainder_staged_words__normalize_divisor_left
adc_remainder_staged_words__subtract_shifted_divisor:
    rcall       adc_div_compare_subtract_staged_words
adc_remainder_staged_words__shift_divisor_right:
    bcf         STATUS, 0, ACCESS
    rrcf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    rrcf        length_mask_or_divisor_low_scratch_byte, F, ACCESS
    decfsz      count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS
    bra         adc_remainder_staged_words__subtract_shifted_divisor
adc_remainder_staged_words__return:
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
    rcall       config_flash_write_tablat_byte
    movlw       UPPER(_CONFIG1L)
    movwf       TBLPTRU, ACCESS
    clrf        TBLPTRH, ACCESS
    clrf        TBLPTRL, ACCESS
    movlw       0x3A
    rcall       config_flash_write_tablat_byte
    bcf         EECON1, 2, ACCESS
    return      0

config_flash_write_tablat_byte:
    movwf       TABLAT, ACCESS
    tblwt*
    movlw       0xC4
    movwf       EECON1, ACCESS
    rcall       nvm_unlock_and_set_wr
config_flash_write__wait_wr_clear:
    btfsc       EECON1, 1, ACCESS
    bra         config_flash_write__wait_wr_clear
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep0_service_setup_transaction
; Address : 0x42F4
; Notes   : Inferred usb helper; touches usb. Calls: usb_ep0_dispatch_standard_setup_request, usb_ep0_dispatch_hid_setup_request.
; ---------------------------------------------------------------------------
usb_ep0_service_setup_transaction:
    movlb       0x4
    clrf        usb_ep0_in_bd_status_b4, BANKED
    movlb       0x0
    clrf        usb_ep0_in_data_toggle_state_b0, BANKED
    movlb       0x4
    btfss       usb_ep0_out_even_bd_status_b4, 7, BANKED
    bra         usb_ep0_service_setup_transaction__check_odd_out_bd
    clrf        usb_ep0_out_even_bd_status_b4, BANKED
    movlb       0x0
    clrf        usb_ep0_out_next_bd_toggle_b0, BANKED
usb_ep0_service_setup_transaction__check_odd_out_bd:
    movlb       0x4
    btfss       usb_ep0_out_odd_bd_status_b4, 7, BANKED
    bra         usb_ep0_service_setup_transaction__clear_control_state_and_dispatch
    clrf        usb_ep0_out_odd_bd_status_b4, BANKED
    movlw       0x01
    movlb       0x0
    movwf       usb_ep0_out_next_bd_toggle_b0, BANKED
usb_ep0_service_setup_transaction__clear_control_state_and_dispatch:
    movlb       0x0
    clrf        usb_ep0_control_transfer_phase_b0, BANKED
    clrf        usb_ep0_control_response_mode_b0, BANKED
    clrf        usb_ep0_transfer_remaining_lo_b0, BANKED
    clrf        usb_ep0_transfer_remaining_hi_b0, BANKED
    bcf         UCON, 4, ACCESS
    call        usb_ep0_dispatch_standard_setup_request, 0x0
    call        usb_ep0_dispatch_hid_setup_request, 0x0
    goto        usb_ep0_arm_control_transfer_response


; ---------------------------------------------------------------------------
; Function: i2c_tas3108_reg1f_write        (DSP register 0x1F write, V3.1+)
; Address : 0x4368
; ---------------------------------------------------------------------------
; Writes a single byte to TAS3108 register 0x1F (the master-mode / mute
; control register). Used by the standby paths to stage the DSP's mute
; before the rail drops, and by run_wake_rail_gate_and_dsp_cold_init during the wake sequence.
;
; Wire format on the bus:
;   START | 0x68 (DSP write) | 0x1F (reg) | 00 | 00 | 00 | <data> | STOP
; The three zero bytes are the upper 3 bytes of the 32-bit register address
; field (TAS3108 register protocol uses 32-bit addr + N bytes data).
;
; V3.1 hardening: SEN/PEN waits go through wait_sen_bounded / wait_pen_bounded
; and short-circuit to i2c_tas3108_reg1f_write__return_success on timeout. i2c_byte_tx (V3.1+) latches
; ACKSTAT in dsp_fault_flags.bit2 — but this routine does not act on it; it
; is the volume_dsp_write path that drives the retry/escalation.
; ---------------------------------------------------------------------------
i2c_tas3108_reg1f_write:
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    rcall       i2c_start_after_idle_bounded
    bc          i2c_reg1f_timeout
    movlw       0x68
    rcall       i2c_byte_tx
    movlw       0x1F
    rcall       i2c_byte_tx
    rcall       i2c_byte_tx_zero
    rcall       i2c_byte_tx_zero
    rcall       i2c_byte_tx_zero
    rcall       i2c_send_staged_data_byte_and_stop
    bc          i2c_reg1f_pen_timeout
i2c_tas3108_reg1f_write__return_success:
    return      0
i2c_reg1f_timeout:
    bra         i2c_timeout_recover_advertise
i2c_reg1f_pen_timeout:
    bra         i2c_pen_timeout_recover_advertise

i2c_send_staged_data_byte_and_stop:
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    rcall       i2c_byte_tx
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    bra         wait_pen_bounded

i2c_byte_tx_zero:
    movlw       0x00
    bra         i2c_byte_tx


; ---------------------------------------------------------------------------
; Function: uart_tx_ascii_hex_byte
; Address : 0x43A2
; Notes   : Inferred uart helper routine. Calls: hex_scratch_nibble_to_ascii, uart_tx_byte_blocking.
; ---------------------------------------------------------------------------
uart_tx_ascii_hex_byte:
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    swapf       addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    movlw       0x0F
    andwf       addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    rcall       hex_scratch_nibble_to_ascii
    rcall       uart_tx_byte_blocking
    movwf       length_mask_or_divisor_low_scratch_byte, ACCESS
    movff       status_fanout_or_usb_ptr_or_i2c_uart_scratch_phys, addr_high_table_row_or_checksum_scratch_phys
    movlw       0x0F
    rcall       hex_scratch_nibble_to_ascii
    rcall       uart_tx_byte_blocking
    xorwf       length_mask_or_divisor_low_scratch_byte, F, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: hex_scratch_nibble_to_ascii                   (ASCII hex digit lookup)
; Address : 0x43C8
; ---------------------------------------------------------------------------
; Loads ram_0x004 with W (low nibble), then TBLRDs hex_lookup_table[nibble]
; to convert 0..F into ASCII. Twin of nibble_to_hex_ascii (which converts
; ram_0x01B); they exist as two copies because the firmware-update relay
; path needs the conversion in a different scratch register without
; clobbering the main parser's ram_0x01B accumulator.
; ---------------------------------------------------------------------------
hex_scratch_nibble_to_ascii:
    andwf       addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
    movf        addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    call        hex_lookup_table_ptr, 0x0           ; far call: helper lives near nibble_to_hex_ascii
    tblrd*
    movf        TABLAT, W, ACCESS
    return      0

; ---------------------------------------------------------------------------
; Function: eeprom_write_blocking          (single-byte EEPROM write, 4 ms)
; Address : 0x43EA
; ---------------------------------------------------------------------------
; Writes one byte: EEADR=ram_0x003, EEDATA=ram_0x005. Drives the standard
; PIC18 EEPROM unlock (0x55, 0xAA, WR) via nvm_unlock_and_set_wr, then
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
    movff       addr_low_counter_or_payload_scratch_phys, EEADR
    movff       saved_w_b0_phys, EEDATA
    bcf         EECON1, 7, ACCESS
    bcf         EECON1, 6, ACCESS
    bsf         EECON1, 2, ACCESS
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    btfsc       INTCON, 7, ACCESS
    incf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
    bcf         INTCON, 7, ACCESS
    rcall       nvm_unlock_and_set_wr
eeprom_write_blocking__wait_write_complete:
    btfsc       EECON1, 1, ACCESS
    bra         eeprom_write_blocking__wait_write_complete
    btfsc       status_addr_high_or_i2c_payload_scratch_byte, 0, ACCESS
    bra         eeprom_write_blocking__restore_global_interrupt
    bcf         INTCON, 7, ACCESS
    bra         eeprom_write_blocking__clear_write_enable
eeprom_write_blocking__restore_global_interrupt:
    bsf         INTCON, 7, ACCESS
eeprom_write_blocking__clear_write_enable:
    bcf         EECON1, 2, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: nvm_unlock_and_set_wr
; Address : 0x4406
; Notes   : Inferred flash helper; touches flash.
; ---------------------------------------------------------------------------
nvm_unlock_and_set_wr:
    movlw       0x55
    movwf       EECON2, ACCESS
    movlw       0xAA
    movwf       EECON2, ACCESS
    bsf         EECON1, 1, ACCESS
    retlw       0xAA


; ---------------------------------------------------------------------------
; Function: usb_ep0_service_in_transaction
; Address : 0x4412
; Notes   : Inferred usb helper; touches usb. Calls: usb_ep0_stage_in_data_packet.
; ---------------------------------------------------------------------------
usb_ep0_service_in_transaction:
    movf        usb_device_state_b0, W, BANKED
    xorlw       0x04
    bnz         usb_ep0_service_in_transaction__service_payload_stream
    movff       usb_setup_w_value_lo_phys, UADDR
    movf        UADDR, W, ACCESS
    movlw       0x05
    btfsc       STATUS, 2, ACCESS
    movlw       0x03
    movwf       usb_device_state_b0, BANKED
usb_ep0_service_in_transaction__service_payload_stream:
    decf        usb_ep0_control_transfer_phase_b0, W, BANKED
    bnz         usb_ep0_service_in_transaction__return
    call        usb_ep0_stage_in_data_packet, 0x0
    movf        usb_ep0_in_data_toggle_state_b0, W, BANKED
    xorlw       0x02
    movlb       0x4
    bnz         usb_ep0_service_in_transaction__select_next_data_toggle
    movlw       0x04
    bra         usb_ep0_service_in_transaction__arm_in_bd
usb_ep0_service_in_transaction__select_next_data_toggle:
    movlw       0x48
    btfsc       usb_ep0_in_bd_status_b4, 6, BANKED
    movlw       0x08
usb_ep0_service_in_transaction__arm_in_bd:
    movwf       usb_ep0_in_bd_status_b4, BANKED
    bsf         usb_ep0_in_bd_status_b4, 7, BANKED
usb_ep0_service_in_transaction__return:
    return      0


; ---------------------------------------------------------------------------
; Function: map_audio_source_selector_to_route_pair
; Address : 0x4448
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
map_audio_source_selector_to_route_pair:
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    bra         map_audio_source_selector_to_route_pair__decode_selector
map_audio_source_selector_to_route_pair__selector_zero:
    movlw       0x01
    movwf       audio_route_pair_byte0_b0, BANKED
    clrf        audio_route_pair_byte1_b0, BANKED
    bra         map_audio_source_selector_to_route_pair__return
map_audio_source_selector_to_route_pair__selector_one:
    clrf        audio_route_pair_byte0_b0, BANKED
    movlw       0x01
    bra         map_audio_source_selector_to_route_pair__store_pair_byte1
map_audio_source_selector_to_route_pair__selector_two:
    movlw       0x02
    movwf       audio_route_pair_byte0_b0, BANKED
    bra         map_audio_source_selector_to_route_pair__store_pair_byte1
map_audio_source_selector_to_route_pair__selector_three:
    movlw       0x01
    movwf       audio_route_pair_byte0_b0, BANKED
    movlw       0x03
map_audio_source_selector_to_route_pair__store_pair_byte1:
    movwf       audio_route_pair_byte1_b0, BANKED
    bra         map_audio_source_selector_to_route_pair__return
map_audio_source_selector_to_route_pair__decode_selector:
    movf        addr_low_counter_or_payload_scratch_byte, W, ACCESS
    bz          map_audio_source_selector_to_route_pair__selector_zero
    xorlw       0x01
    bz          map_audio_source_selector_to_route_pair__selector_one
    xorlw       0x03
    bz          map_audio_source_selector_to_route_pair__selector_two
    xorlw       0x01
    bz          map_audio_source_selector_to_route_pair__selector_three
map_audio_source_selector_to_route_pair__return:
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
; Used by hw_standby_shutdown (250 ms pulse loop), run_wake_rail_gate_and_dsp_cold_init (settle
; delays), and various fw-update path delays.
; ---------------------------------------------------------------------------
; Helper: timer3_blocking_delay_ms_from_w (W04-E08)
; Loads the 16-bit timer counter as (ram_0x004=0, ram_0x003=W) and falls
; through into timer3_blocking_delay. Used by wake / cold-boot paths that
; always zero the high byte. Saves 4 B per call site (7 sites factored).
; Reorder is safe: timer3_blocking_delay does not read ram_0x003/ram_0x004
; until after its own setup; the two stores to W-relative scratch bytes do
; not depend on order.
; ---------------------------------------------------------------------------
timer3_blocking_delay_ms_from_w:
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    ; fall through into timer3_blocking_delay
timer3_blocking_delay:
    bcf         PIE2, 1, ACCESS
    movlw       0x98
    movwf       T3CON, ACCESS
    bsf         T3CON, 0, ACCESS
    bra         timer3_blocking_delay__check_countdown_remaining
timer3_blocking_delay__reload_next_tick:
    btfss       OSCCON, 1, ACCESS
    bra         timer3_blocking_delay__reload_high_speed_tick
    movlw       0xFC
    movwf       TMR3H, ACCESS
    movlw       0x18
    bra         timer3_blocking_delay__write_low_power_reload_low
timer3_blocking_delay__reload_high_speed_tick:
    rcall       timer3_reload_high_speed_tick_preload
    bra         timer3_blocking_delay__clear_overflow_flag
timer3_blocking_delay__write_low_power_reload_low:
    movwf       TMR3L, ACCESS
timer3_blocking_delay__clear_overflow_flag:
    bcf         PIR2, 1, ACCESS
timer3_blocking_delay__wait_overflow_flag:
    btfss       PIR2, 1, ACCESS
    bra         timer3_blocking_delay__wait_overflow_flag
    decf        addr_low_counter_or_payload_scratch_byte, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
timer3_blocking_delay__check_countdown_remaining:
    movf        addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    iorwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    bnz         timer3_blocking_delay__reload_next_tick
    bcf         T3CON, 0, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: uart_emit_formfeed_colon_text_line
; Address : 0x44B2
; Notes   : Inferred uart helper routine. Calls: uart_tx_byte_blocking, uart_tx_block_from_buffer.
; ---------------------------------------------------------------------------
uart_emit_formfeed_colon_text_line:
    movwf       fw_update_hex_or_float32_quotient_or_uart_block_scratch, ACCESS
    movlw       0x0D
    rcall       uart_tx_byte_blocking
    movlw       0x0A
    rcall       uart_tx_byte_blocking
    movlw       0x0C
    rcall       uart_tx_byte_blocking
    movlw       0x3A
    rcall       uart_tx_byte_blocking
    clrf        float32_product_or_uart_base_high_scratch_byte, ACCESS
    movff       fw_update_hex_byte_or_uart_block_base_low_scratch_phys, preset_header_tas_reg_or_uart_block_base_low_scratch_phys
    rcall       uart_tx_block_from_buffer
    movlw       0x0D
    rcall       uart_tx_byte_blocking
    movlw       0x0A
    bra         uart_tx_byte_blocking

; ---------------------------------------------------------------------------
; Helper: tas3108_write_zero_volume_coeff        (W03-E02 size-opt helper)
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
tas3108_write_zero_volume_coeff:
    ; V3.4 forensic M: every DSP mute write (TAS 0x30 <- 0) passes here.
    movlw       0x04                        ; index 4 = M
    rcall       diag_src_inc_w
    clrf        i2c_coeff_0_acc, ACCESS
    clrf        i2c_coeff_1_acc, ACCESS
    clrf        i2c_coeff_2_acc, ACCESS
    clrf        i2c_coeff_3_acc, ACCESS
    bra         volume_dsp_write

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
    rcall       i2c_start_after_idle_bounded
    bc          coeff_write_timeout
    movlw       0x68
    rcall       i2c_byte_tx
    movlw       0x30
    rcall       i2c_byte_tx
    call        stage_tas3108_coeff_input_scratch, 0x0  ; size S3 (out of rcall reach)
    call        i2c_emit_tas3108_coeff_from_staged_float, 0x0
    bsf         SSPCON2, 2, ACCESS          ; stock STOP wait
    rcall       wait_pen_bounded
    bc          coeff_write_pen_timeout
i2c_tas3108_coeff_write__return_success:
    return      0
coeff_write_timeout:
    bra         i2c_timeout_recover_advertise
coeff_write_pen_timeout:
    bra         i2c_pen_timeout_recover_advertise


; ---------------------------------------------------------------------------
; Function: drive_audio_route_select_latches
; Address : 0x4516
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
drive_audio_route_select_latches:
    tstfsz      src_route_status_code_acc, ACCESS
    bra         drive_audio_route_select_latches__decode_route_code
drive_audio_route_select_latches__all_selects_low:
    bcf         LATA, 3, ACCESS
    bra         drive_audio_route_select_latches__clear_lata4_lata5
drive_audio_route_select_latches__set_lata3_clear_lata4_lata5:
    bsf         LATA, 3, ACCESS
drive_audio_route_select_latches__clear_lata4_lata5:
    bcf         LATA, 4, ACCESS
    bcf         LATA, 5, ACCESS
    bra         drive_audio_route_select_latches__return
drive_audio_route_select_latches__clear_lata3_lata4_set_lata5:
    bcf         LATA, 3, ACCESS
    bcf         LATA, 4, ACCESS
    bra         drive_audio_route_select_latches__set_lata5
drive_audio_route_select_latches__clear_lata3_set_lata4_lata5:
    bcf         LATA, 3, ACCESS
    bsf         LATA, 4, ACCESS
drive_audio_route_select_latches__set_lata5:
    bsf         LATA, 5, ACCESS
    bra         drive_audio_route_select_latches__return
drive_audio_route_select_latches__decode_route_code:
    movf        pending_route_request_b0, W, BANKED
    bz          drive_audio_route_select_latches__all_selects_low
    xorlw       0x05
    bz          drive_audio_route_select_latches__set_lata3_clear_lata4_lata5
    xorlw       0x03
    bz          drive_audio_route_select_latches__clear_lata3_lata4_set_lata5
    xorlw       0x01
    bz          drive_audio_route_select_latches__clear_lata3_set_lata4_lata5
drive_audio_route_select_latches__return:
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
    bra         diag_inc_sat_fsr0__check_below_saturation
    movwf       INDF0, ACCESS             ; counter > 0x0F: clamp to 0x0F
    return      0
diag_inc_sat_fsr0__check_below_saturation:
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
    clrf        uart_current_cmd_code_b0, BANKED
    clrf        current_cmd_data_b0, BANKED
    clrf        uart_cmd_reply_data_b0, BANKED
    bcf         active_flags_acc, 0, ACCESS
    bcf         active_flags_acc, 6, ACCESS
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
; Function: preset_replay_selected_table_blocking
; Address : 0x4574
; Notes   : Replays the selected preset table through the same validated
;           physical-source/header/NACK-aware writer used by async APPLY.
; ---------------------------------------------------------------------------
preset_replay_selected_table_blocking:
    ; V3.4 forensic T: every full blocking preset-table walk (cold init,
    ; wake bring-up, EP0/reconnect reapply) enters here.
    movlw       0x03                        ; index 3 = T
    rcall       diag_src_inc_w
    rcall       preset_job_init_cursor_from_active
preset_replay_selected_table_blocking__apply_next_entry:
    movlw       0x60
    cpfslt      preset_job_index_b2, BANKED
    bra         preset_replay_selected_table_blocking__apply_final_entry
    rcall       preset_job_apply_i2c_from_job_cursor
    bc          preset_replay_selected_table_blocking__return_failure
    rcall       preset_job_advance_cursor_to_next_table_row
    bra         preset_replay_selected_table_blocking__apply_next_entry
preset_replay_selected_table_blocking__apply_final_entry:
    bra         preset_job_apply_i2c_from_job_cursor
preset_replay_selected_table_blocking__return_failure:
    return      0


; ---------------------------------------------------------------------------
; Function: usb_hid_mailbox_send_reply_if_ready
; Address : 0x45A2
; Notes   : Inferred usb helper; touches usb. Calls: stage_hid_ep1_in_report_from_selector, usb_ep1_in_copy_scratch_buffer_to_bdt.
; ---------------------------------------------------------------------------
usb_hid_mailbox_send_reply_if_ready:
    call        stage_hid_ep1_in_report_from_selector, 0x0
    movf        usb_device_state_b0, W, BANKED
    xorlw       0x06
    btfsc       STATUS, 2, ACCESS
    btfsc       UCON, 1, ACCESS
    return      0
    btfss       PORTC, 0, ACCESS
    return      0
    movlb       0x4
    btfsc       usb_ep1_in_bd_status_b4, 7, BANKED
    return      0
    bra         usb_ep1_in_send_hid_reply_buffer


; ---------------------------------------------------------------------------
; Function: uint8_to_float32_and_save
; Address : 0x45CE
; Notes   : Inferred core helper routine. Calls: float32_pack_mantissa_exponent_sign.
; ---------------------------------------------------------------------------
uint8_to_float32_and_save:
    movwf       float_loop_or_tblptr_low_scratch_byte, ACCESS
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    clrf        length_mask_or_divisor_low_scratch_byte, ACCESS
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x96
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    ; W04-E01: factor call+4 movff tail into float32_pack_mantissa_exponent_sign_and_save
    goto        float32_pack_mantissa_exponent_sign_and_save

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
; Used by uart_link_parser_drain_rx_and_forward and uart_rx_with_framing. There is no
; locking — the ISR (uart_rx_irq_enqueue) writes the same backing buffer
; and increments rx_ring_wr; correctness relies on the head/tail pair being
; updated by a single side at a time (cooperative). BUG M6 (rx_ring_no_
; overflow_detect): no full check — the ISR can overwrite the byte that
; this routine is about to read. V3.2 hardening plan workstream 2.
; ---------------------------------------------------------------------------
rx_ring_read:
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    rcall       rx_ring_has_data

    bz          rx_ring_read__return_byte_or_zero
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
    rcall       setup_fsr2_page2_from_w                    ; W05-E02: FSR2=0x0200|W (movf INDF2 overwrites W)
    movf        INDF2, W, ACCESS
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    incf        rx_ring_rd_b0, F, BANKED
    movlw       0xBF
    cpfsgt      rx_ring_rd_b0, BANKED
    bra         rx_ring_read__return_byte_or_zero
    clrf        rx_ring_rd_b0, BANKED
rx_ring_read__return_byte_or_zero:
    movf        addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: usb_ep1_configure_hid_buffers
; Address : 0x4624
; Notes   : Inferred usb helper; touches usb.
; ---------------------------------------------------------------------------
usb_ep1_configure_hid_buffers:
    clrf        usb_ep1_out_copy_offset_b0, BANKED
    movlw       0x1E
    movwf       UEP1, ACCESS
    movlw       0x40
    movlb       0x4
    movwf       usb_ep1_out_bd_count_b4, BANKED
    movlw       0x04
    movwf       usb_ep1_out_bd_addr_hi_b4, BANKED
    movlw       0x2C
    movwf       usb_ep1_out_bd_addr_lo_b4, BANKED
    movlw       0x08
    movwf       usb_ep1_out_bd_status_b4, BANKED
    bsf         usb_ep1_out_bd_status_b4, 7, BANKED
    movlw       0x04
    movwf       usb_ep1_in_bd_addr_hi_b4, BANKED
    movlw       0x6C
    movwf       usb_ep1_in_bd_addr_lo_b4, BANKED
    movlw       0x40
    movwf       usb_ep1_in_bd_status_b4, BANKED
    retlw       0x40


; ---------------------------------------------------------------------------
; Function: i2c_receive_sspbuf_bounded
; Address : 0x464C
; Notes   : Inferred i2c helper; touches i2c.
; ---------------------------------------------------------------------------
i2c_receive_sspbuf_bounded:
    movf        SSPCON1, W, ACCESS
    andlw       0x0F
    xorlw       0x08
    bz          i2c_receive_sspbuf_bounded__enable_rcen
    xorlw       0x0B
    btfsc       STATUS, 2, ACCESS
i2c_receive_sspbuf_bounded__enable_rcen:
    bsf         SSPCON2, 3, ACCESS
    rcall       wait_bf_set_bounded
    bc          i2c_receive_sspbuf_bounded__timeout
    movf        SSPBUF, W, ACCESS
    return      0
i2c_receive_sspbuf_bounded__timeout:
    bra         i2c_secondary_dev_random_timeout


; ---------------------------------------------------------------------------
; Function: fw_update_emit_zero_status_lines
; Address : 0x4672
; Notes   : Inferred core helper routine. Calls: uart_emit_formfeed_colon_text_line.
; ---------------------------------------------------------------------------
fw_update_emit_zero_status_lines:
    lfsr        FSR2, fw_update_zero_status_text_phys
    lfsr        FSR1, hex_byte_save_or_uart_status_block_buffer_phys
    movlw       0x07
    rcall       copy_w_bytes_fsr2_to_fsr1
    movlw       0x1C
    rcall       uart_emit_formfeed_colon_text_line
    movlw       0x1C
    rcall       uart_emit_formfeed_colon_text_line
    movlw       0x1C
    bra         uart_emit_formfeed_colon_text_line


; ---------------------------------------------------------------------------
; Function: uart_tx_block_from_buffer
; Address : 0x4696
; Notes   : Transmits a buffered UART block one byte at a time.
; ---------------------------------------------------------------------------
uart_tx_block_from_buffer:
    clrf        float32_extract_or_quotient_or_preset_uart_index, ACCESS
    bra         uart_tx_block_from_buffer__check_terminator
uart_tx_block_from_buffer__emit_current_byte:
    rcall       uart_tx_block_load_indexed_byte
    rcall       uart_tx_byte_blocking
    incf        float32_extract_or_quotient_or_preset_uart_index, F, ACCESS
uart_tx_block_from_buffer__check_terminator:
    rcall       uart_tx_block_load_indexed_byte
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         uart_tx_block_from_buffer__emit_current_byte


; ---------------------------------------------------------------------------
; Function: uart_tx_block_load_indexed_byte
; Address : 0x46AA
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
uart_tx_block_load_indexed_byte:
    movf        float32_extract_or_quotient_or_preset_uart_index, W, ACCESS
    addwf       float32_product_or_uart_base_scratch_byte, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      float32_product_or_uart_base_high_scratch_byte, W, ACCESS
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
; i2c_secondary_dev_write__return_success leaving the bus best-effort recovered (caller is
; expected to detect failure via dsp_fault_flags or downstream symptoms).
;
; This is the device touched by hw_standby_shutdown's three-write rail
; sequence — an unbounded wait HERE used to be the V1.62b "PBs don't power
; down" signature; bounding it was part of V3.1.
; ---------------------------------------------------------------------------
i2c_secondary_dev_write:
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    rcall       wait_sen_bounded
    bc          i2c_secondary_timeout
    movlw       0xE2
    rcall       i2c_byte_tx
    movf        count_flash_page_or_i2c_payload_scratch_byte, W, ACCESS
    rcall       i2c_byte_tx
    rcall       i2c_send_staged_data_byte_and_stop
    bc          i2c_secondary_pen_timeout
i2c_secondary_dev_write__return_success:
    return      0
i2c_secondary_timeout:
    bra         i2c_timeout_recover_advertise
i2c_secondary_pen_timeout:
    bra         i2c_pen_timeout_recover_advertise


; ---------------------------------------------------------------------------
; Function: eeprom_write_byte_if_changed
; Address : 0x46DE
; Notes   : Inferred flash helper routine. Calls: eeprom_read_byte, eeprom_write_blocking.
; ---------------------------------------------------------------------------
eeprom_write_byte_if_changed:
    movff       computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys, addr_low_counter_or_payload_scratch_phys
    movff       computed_volume_or_i2c_payload_or_float32_scale_or_adc_eeprom_hi_phys, addr_high_table_row_or_checksum_scratch_phys
    rcall       eeprom_read_byte
    xorwf       flash_src_low_or_rx_length_scratch_byte, W, ACCESS
    bz          eeprom_write_byte_if_changed__return_unchanged
    rcall       chain_copy_call_range_trampoline_mid ; size T121: local trampoline keeps descriptor TOS shape
    db          0x00, 0x00, eeprom_addr_or_float32_pack_tail_operand_op, addr_low_counter_or_payload_scratch_operand, 0x03, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
    bra         eeprom_write_blocking
eeprom_write_byte_if_changed__return_unchanged:
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
; Helper: setup_fsr2_page2_from_w                            (W05-E02 size-opt helper)
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
setup_fsr2_page2_from_w:
    movwf       FSR2L, ACCESS
    movlw       0x02
    movwf       FSR2H, ACCESS
    return      0

fsr2_from_scratch_base_plus_w:
    addwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    movwf       FSR2L, ACCESS
    movlw       0x00
    addwfc      addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    movwf       FSR2H, ACCESS
    return      0


; ---------------------------------------------------------------------------
; Function: clear_ram_span_from_staged_addr_count
; Address : 0x473E
; Notes   : Clears a RAM span from an FSR2 pointer and byte count.
; ---------------------------------------------------------------------------
clear_ram_span_from_staged_addr_count:
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    bra         ram_block_clear__check_remaining
ram_block_clear__clear_next_byte:
    movf        status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    rcall       fsr2_from_scratch_base_plus_w
    clrf        INDF2, ACCESS
    incf        status_addr_high_or_i2c_payload_scratch_byte, F, ACCESS
ram_block_clear__check_remaining:
    movf        length_mask_or_divisor_low_scratch_byte, W, ACCESS
    subwf       status_addr_high_or_i2c_payload_scratch_byte, W, ACCESS
    btfsc       STATUS, 0, ACCESS
    return      0
    bra         ram_block_clear__clear_next_byte


; ---------------------------------------------------------------------------
; Function: usb_poll_host_presence_reinit_or_shutdown
; Address : 0x475C
; Notes   : Inferred usb helper; touches usb. Calls: usb_shutdown; includes the
;           former full-UCON re-arm path inline.
; ---------------------------------------------------------------------------
usb_poll_host_presence_reinit_or_shutdown:
    movlb       0x0
    decf        usb_reinit_pending_b0, W, BANKED
    bz          usb_poll_host_presence_reinit_or_shutdown__return
    btfss       PORTC, 0, ACCESS
    bra         usb_poll_host_presence_reinit_or_shutdown__host_absent_shutdown_check
    btfsc       UCON, 3, ACCESS
    bra         usb_poll_host_presence_reinit_or_shutdown__return
    decf        usb_reinit_pending_b0, W, BANKED
    btfsc       STATUS, 2, ACCESS
    rcall       usb_disconnect_wait_clear_state
    clrf        UCON, ACCESS
    movlw       0x15
    movwf       UCFG, ACCESS
    clrf        UIE, ACCESS
    bsf         UCON, 3, ACCESS
    rcall       usb_bus_reset_reinitialize
    movlw       0x01
    movlb       0x0
    movwf       usb_device_state_b0, BANKED
    clrf        usb_reinit_pending_b0, BANKED
    bra         usb_poll_host_presence_reinit_or_shutdown__return
usb_poll_host_presence_reinit_or_shutdown__host_absent_shutdown_check:
    btfss       UCON, 3, ACCESS
    bra         usb_poll_host_presence_reinit_or_shutdown__return
    rcall       usb_shutdown
    clrf        usb_reinit_pending_b0, BANKED
usb_poll_host_presence_reinit_or_shutdown__return:
    return      0


; ---------------------------------------------------------------------------
; Function: timer3_arm_interrupt_countdown
; Address : 0x477A
; Notes   : Inferred timer helper; touches timer.
; ---------------------------------------------------------------------------
timer3_arm_interrupt_countdown:
    movlw       0x98
    movwf       T3CON, ACCESS
    rcall       timer3_reload_high_speed_tick_preload
    movff       addr_low_counter_or_payload_scratch_phys, preset_hold_timer_lo_b0_phys
    movff       addr_high_table_row_or_checksum_scratch_phys, preset_hold_timer_hi_b0_phys
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
;   gate set    -> run_wake_rail_gate_and_dsp_cold_init          (waits AN0 ≥ 0x0236; bug M9: unbounded)
;   gate clear  -> hw_standby_shutdown    (I2C DSP shutdown, T0 disable, OSCCON
;                                          switch, USB disable; sets
;                                          usb_reinit_pending=0x01)
;
; After dispatch the bit is cleared and control falls into cmd_dispatch_gated
; with W=0x01 so the input/volume/mute reconciliation pass runs immediately.
; On a real STDBY broadcast the active gate has already been cleared at
; standby_request_handler, so this routine takes the shutdown path.
;
; V3.2 interaction: advance_preset_job_state_machine detects active_flags.bit3 == 0 and
; cancels the in-flight preset job *before* this routine performs the shutdown,
; so a partially-applied preset never gets "committed" into a hardware-off
; state.
; ---------------------------------------------------------------------------
standby_event_dispatch:
    movlb       0x0
    btfss       event_flags_b0, 2, BANKED              ; pending stdby/wake event?
    bra         standby_event_dispatch__tail_reconcile_state    ; no -> tail-call gate dispatch
    btfss       active_flags_acc, 3, ACCESS             ; gate currently open?
    bra         standby_event_dispatch__shutdown_path    ;   no -> shutdown path
    diag_inc_sat diag_b                              ; V3.2 Layer 5: count bring-up dispatch
    call        run_wake_rail_gate_and_dsp_cold_init, 0x0                  ; gate open -> rail-rise wait
    bra         standby_event_dispatch__clear_pending_event
standby_event_dispatch__shutdown_path:
    diag_inc_sat diag_s                              ; V3.2 Layer 5: count standby dispatch
    call        hw_standby_shutdown, 0x0            ; I2C DSP shutdown / OSC switch
standby_event_dispatch__clear_pending_event:
    bcf         event_flags_b0, 2, BANKED              ; consume the event
standby_event_dispatch__tail_reconcile_state:
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
mssp_hard_reset_smp_master:
mssp_hard_reset:
    movlw       0xC0
    andwf       SSPSTAT, F, ACCESS
    clrf        SSPCON1, ACCESS
    clrf        SSPCON2, ACCESS
    bcf         PIR2, 3, ACCESS
    bsf         SSPSTAT, 7, ACCESS
    bsf         TRISB, 1, ACCESS
    bra         i2c_reenable_sda_sspen

; ---------------------------------------------------------------------------
; Function: run_main_service_pass          (one main-loop pass — service slot)
; Address : 0x47CE
; ---------------------------------------------------------------------------
; Single iteration of the cooperative main loop. run_main_foreground_loop tail-
; calls this between USB SIE polls. Order matters:
;   1. usb_hid_dispatch_out_report_if_ready   USB SIE / endpoint pump (must run frequently)
;   2. uart_link_parser_drain_rx_and_forward  drain native RX ring + parse + forward
;   3. advance_preset_job_state_machine      V3.2: ONE step of the async preset state machine
;                              (see notes near advance_preset_job_state_machine for invariants)
;   4. poll_src4382_route_monitor   refresh DSP I2C state (volume dirty drain etc.)
;   5. standby_event_dispatch  stdby/wake reaction if event_flags.bit2 pending
;   6. persist_dirty_runtime_state_to_eeprom  housekeeping (Timer3 reload, ping fault relay)
;   7. an0_hysteresis_monitor  AN0 ADC threshold tracking (rail rise/fall)
;
; Total worst-case path is dominated by the legacy preset_table_apply_entry_legacy_blocking sites
; reachable from poll_src4382_route_monitor — those are the V3.2 hardening targets
; documented in docs/V32_MAIN_HANG_HARDENING_PLAN.md workstream 1.
; ---------------------------------------------------------------------------
run_main_service_pass:
    movlb       0x02
    clrf        chain_tx_emitted_b2, BANKED
    movlb       0x00
    call        usb_hid_dispatch_out_report_if_ready, 0x0
    call        uart_link_parser_drain_rx_and_forward, 0x0
periodic_service_loop__check_rx_frame_gap:                          ; V3.2 §2: parser stall watchdog
    movlb       0x0
    movf        rx_frame_position_b0, F, BANKED
    btfsc       STATUS, 2, ACCESS               ; Z = parser idle
    bra         periodic_service_loop__clear_rx_frame_gap_timeout
    movf        rx_ring_wr_b0, W, BANKED
    cpfseq      rx_ring_rd_b0, BANKED               ; ring has data? parser about to progress
    bra         periodic_service_loop__clear_rx_frame_gap_timeout
    movlb       0x2
    infsnz      main_rx_frame_gap_timeout_b2, F, BANKED
    bra         periodic_service_loop__reset_stalled_rx_frame
    bra         periodic_service_loop__continue_service_slots
periodic_service_loop__reset_stalled_rx_frame:
    movlb       0x0
    clrf        rx_frame_position_b0, BANKED
    bcf         active_flags_acc, 0, ACCESS
    ; fall through to idle — clears the timeout after reset
periodic_service_loop__clear_rx_frame_gap_timeout:
    movlb       0x2
    clrf        main_rx_frame_gap_timeout_b2, BANKED
periodic_service_loop__continue_service_slots:
    rcall       advance_preset_job_state_machine                  ; V3.2: async preset state machine
    call        poll_src4382_route_monitor, 0x0
    rcall       standby_event_dispatch
    call        persist_dirty_runtime_state_to_eeprom, 0x0
    rcall       filename_reply_emit_next_frame_if_ready          ; V3.3: lowest-priority filename burst
    rcall       ra1_edge_monitor                    ; V3.2 Layer 5: diag_p edge counter
    bra         an0_hysteresis_monitor

; ---------------------------------------------------------------------------
; ra1_edge_monitor — V3.2 Layer 5 RA1 edge counter (diag_p)
; ---------------------------------------------------------------------------
; Polled once per run_main_service_pass pass (= run_main_foreground_loop tick,
; tens of µs).  Compares PORTA bit 1 against diag_ra1_prev shadow byte;
; on either edge (0→1 or 1→0) bumps diag_p (saturating at 0x0F).  Tested
; via the simulator by toggling RA1 in the harness; no real-hardware function is
; assigned to RA1 in V3.2, so this is pure observability infrastructure
; per docs/V163B_DIAGNOSTICS_MENU_SPEC.md "RA1-trigger path" section.
; ---------------------------------------------------------------------------
ra1_edge_monitor:
    movff       BSR, flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys                  ; save caller BSR
    movlb       0x02                            ; V3.2 Layer 5 diag block in BANK 2
    movf        PORTA, W, ACCESS                ; W = PORTA snapshot
    andlw       0x02                            ; isolate RA1
    xorwf       diag_ra1_prev_b2, W, BANKED        ; W = current ^ prev (bit 1 only)
    btfsc       STATUS, 2, ACCESS               ; if Z (no edge), skip increment
    bra         ra1_edge_monitor__restore_bsr_return
    ; Edge detected — refresh shadow and bump counter.
    movf        PORTA, W, ACCESS
    andlw       0x02
    movwf       diag_ra1_prev_b2, BANKED
    diag_inc_sat diag_p                          ; macro re-asserts movlb 0x02
ra1_edge_monitor__restore_bsr_return:
    movff       flash_addr_high_or_adc_loop_or_bsr_save_scratch_phys, BSR                  ; restore caller BSR
    return      0

; ---------------------------------------------------------------------------
; Inline Data Table (0x47E6-0x47FB)
; ---------------------------------------------------------------------------
fw_update_status_text_seed_table:  ; UART status strings for FW update
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
    rcall       bf_frame_header_tx
    movlw       0x29
    rcall       uart_tx_byte_blocking
    movlw       0x01
    btfss       active_flags_acc, 1, ACCESS
    movlw       0x00
    bra         uart_tx_byte_blocking


; ---------------------------------------------------------------------------
; Function: usb_delay_countdown_with_clrwdt          (16-bit countdown busy-wait + WDT clr)
; Address : 0x4812
; ---------------------------------------------------------------------------
; Decrements the 16-bit pair {ram_0x004,ram_0x003} to zero, calling CLRWDT
; on every iteration. This is the ONLY routine in MAIN that ever clears the
; WDT (BUG M8: no_clrwdt_main_loop). Called from usb_disconnect_wait_clear_state
; during USB-disconnect / sleep transitions, where it acts as the
; soft-reset backstop while UCON is being torn down.
; ---------------------------------------------------------------------------
usb_delay_countdown_with_clrwdt__decrement:
    clrwdt
    decf        addr_low_counter_or_payload_scratch_byte, F, ACCESS
    btfss       STATUS, 0, ACCESS
    decf        addr_high_table_row_or_checksum_scratch_byte, F, ACCESS
usb_delay_countdown_with_clrwdt:
usb_delay_countdown_with_clrwdt__check_remaining:
    movf        addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    iorwf       addr_low_counter_or_payload_scratch_byte, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    return      0
    bra         usb_delay_countdown_with_clrwdt__decrement


; ---------------------------------------------------------------------------
; Function: usb_disconnect_wait_clear_state
; Address : 0x4828
; Notes   : Inferred usb helper; touches usb. Calls: usb_delay_countdown_with_clrwdt.
; ---------------------------------------------------------------------------
usb_disconnect_wait_clear_state:
    bcf         UCON, 1, ACCESS
    clrf        UCON, ACCESS
    setf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    setf        addr_low_counter_or_payload_scratch_byte, ACCESS
    rcall       usb_delay_countdown_with_clrwdt
    movlb       0x0
    clrf        usb_device_state_b0, BANKED
    return      0


; ---------------------------------------------------------------------------
; Function: usb_clear_activity_interrupt_after_settle
; Address : 0x483C
; Notes   : Inferred usb helper; touches usb. Calls: usb_activity_settle_delay_with_clrwdt.
; ---------------------------------------------------------------------------
usb_clear_activity_interrupt_after_settle:
    rcall       usb_activity_settle_delay_with_clrwdt
    bcf         UCON, 1, ACCESS
    bcf         UIE, 2, ACCESS
    bra         usb_clear_activity_interrupt_after_settle__poll_flag
usb_clear_activity_interrupt_after_settle__clear_flag:
    bcf         UIR, 2, ACCESS
usb_clear_activity_interrupt_after_settle__poll_flag:
    btfss       UIR, 2, ACCESS
    return      0
    bra         usb_clear_activity_interrupt_after_settle__clear_flag


; ---------------------------------------------------------------------------
; Function: fw_update_emit_bf18_status
; Address : 0x484E
; Notes   : Emits BF/18/01 factory-reset status frame over UART.
; ---------------------------------------------------------------------------
fw_update_emit_bf18_status:
    rcall       bf_byte_tx
    movlw       0x18
    rcall       uart_tx_byte_blocking
    movlw       0x01
    bra         uart_tx_byte_blocking


; ---------------------------------------------------------------------------
; Function: uart_rx_ring_drain_all         (drain RX ring to completion)
; Address : 0x4860
; ---------------------------------------------------------------------------
; Tight loop: while rx_ring has data, dequeue one byte (W is discarded).
; This is the "throw away everything pending" primitive used to clear the
; ring before entering firmware-update relay or after a parser desync —
; NOT used on the hot parsing path (which dequeues and dispatches inline).
; ---------------------------------------------------------------------------
uart_rx_ring_drain_all__discard_next_byte:
    rcall       rx_ring_read
uart_rx_ring_drain_all:
uart_rx_ring_drain_all__check_more:
    rcall       rx_ring_has_data

    btfsc       STATUS, 2, ACCESS
    return      0
    bra         uart_rx_ring_drain_all__discard_next_byte


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
    movff       addr_low_counter_or_payload_scratch_phys, EEADR
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
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    rcall       wait_trmt_bounded
    bc          uart_tx_timeout
uart_tx_byte_send:
    movff       addr_low_counter_or_payload_scratch_phys, TXREG
    movf        addr_low_counter_or_payload_scratch_byte, W, ACCESS
    return      0
uart_tx_timeout:
    rcall       uart_config
    rcall       wait_trmt_bounded
    bc          hard_reset
    bra         uart_tx_byte_send


; ---------------------------------------------------------------------------
; Function: timer0_rearm_50ms_heartbeat        (Timer0 re-arm — ~50 ms heartbeat)
; Address : 0x48A6
; ---------------------------------------------------------------------------
; Re-arms Timer0 with TMR0=0xA471 → ~50 ms overflow @ 16 MHz / 4 / 1024
; prescaler. Called whenever the main service loop wants to schedule a
; "wake me later" tick (post-cmd reconciliation, post-USB-state-change,
; rail wait pre-roll). Returns retlw 0x71 (TMR0L low byte) to keep callers
; consistent with the earlier stock behavior.
; ---------------------------------------------------------------------------
timer0_rearm_50ms_heartbeat:
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
; Note: boot_cold_init__run_peripheral_init is NOT part of i2c_wait_bus_idle —
; it is the tail entry of an unrelated routine landing here by branch
; alias; run_main_foreground_loop is also defined right after, sharing this
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
i2c_wait_bus_idle__poll_mssp_idle:
    movff       SSPCON2, addr_low_counter_or_payload_scratch_phys
    movlw       0x1F
    andwf       addr_low_counter_or_payload_scratch_byte, F, ACCESS                ; mask SEN/RSEN/PEN/RCEN/ACKEN
    btfsc       STATUS, 2, ACCESS                   ; if any of those set, keep spinning
    btfsc       SSPSTAT, 2, ACCESS                  ; AND while R_nW (master in receive)
    bra         i2c_wait_bus_idle_busy
    bcf         STATUS, 0, ACCESS
    retlw       0x1F
i2c_wait_bus_idle_busy:
    rcall       wait_tick
    bnc         i2c_wait_bus_idle__poll_mssp_idle
    rcall       i2c_timeout_recover_advertise
    retlw       0x1F
boot_cold_init__run_peripheral_init:
    call        boot_init_peripherals_and_enter_adc_gate, 0x0
; ---------------------------------------------------------------------------
; run_main_foreground_loop                     (top-level idle/service loop)
; Address : 0x48CA
; ---------------------------------------------------------------------------
; Cooperative super-loop: USB SIE pump, then run_main_service_pass. Tight
; loop because run_main_service_pass must run as often as possible to keep
; UART RX latency below 1 byte time at 31,250 baud (~320 µs/byte) — any
; slower and the rx_ring overflow hazard (M6) becomes likely.
; ---------------------------------------------------------------------------
run_main_foreground_loop:
    call        usb_sie_endpoint_pump, 0x0          ; USB SIE / endpoint pump
    rcall       run_main_service_pass               ; one main-loop pass
    bra         run_main_foreground_loop

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
; Function: i2c_tas3108_reg1f_02_clear_source_pins
; Address : 0x48E2
; Notes   : Inferred i2c helper routine. Calls: i2c_tas3108_reg1f_write.
; ---------------------------------------------------------------------------
i2c_tas3108_reg1f_02_clear_source_pins:
    movlw       0x02
    rcall       i2c_tas3108_reg1f_write
    goto        clear_lata_source_select_pins

; ---------------------------------------------------------------------------
; Function: usb_shutdown                   (USB PHY drop + reinit-pending flag)
; Address : 0x48F0
; ---------------------------------------------------------------------------
; Drops UCON.SUSPND, zeroes UCON entirely, clears ram_0x0CD (USB endpoint
; state machine slot), then sets usb_reinit_pending = 0x01 so the main
; loop's usb_poll_host_presence_reinit_or_shutdown will run its inline full-UCON re-arm path
; on the next pass once PORTC.RC0 indicates host
; presence again.
;
; Returns 0x01 in W (the reinit-pending flag value) so callers can chain
; checks without re-reading the BANKED RAM.
; ---------------------------------------------------------------------------
usb_shutdown:
    bcf         UCON, 1, ACCESS
    clrf        UCON, ACCESS
    movlb       0x0
    clrf        usb_device_state_b0, BANKED
    movlw       0x01
    movwf       usb_reinit_pending_b0, BANKED
    retlw       0x01


; ---------------------------------------------------------------------------
; Function: flash_entry_mute_and_reset      (V3.2+ pop-free flash entry)
; ---------------------------------------------------------------------------
; Called ONLY from the flash-trigger handler in hid_command_dispatch__enter_fw_update_boot_marker
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
flash_entry_mute_and_reset:
    rcall       preset_force_mute               ; (1) DSP coefficients = 0
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS               ; (2) drop audio rails via 0x71
    movlw       0x1B
    rcall       i2c_secondary_dev_write
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x1C
    rcall       i2c_secondary_dev_write
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x1D
    rcall       i2c_secondary_dev_write
    bcf         LATB, 4, ACCESS                 ; (3) amp enable - graceful
    call        clear_lata_audio_pins, 0x0      ;     drop pins while still driven
    movlw       0x64                            ; (4) 100 ms timer3 settle
    rcall       timer3_blocking_delay_ms_from_w      ;     (W04-E08 factored)
    bcf         LATB, 3, ACCESS                 ; (5) final amp gate down
    bra         hard_reset                      ; (6) now do the RESET


; ---------------------------------------------------------------------------
; Function: usb_ep1_configure_if_enabled
; Address : 0x48FE
; Notes   : Inferred core helper routine. Calls: usb_ep1_configure_hid_buffers.
; ---------------------------------------------------------------------------
usb_ep1_configure_if_enabled:
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    decf        addr_low_counter_or_payload_scratch_byte, W, ACCESS
    btfsc       STATUS, 2, ACCESS
    bra         usb_ep1_configure_hid_buffers
    return      0


; ---------------------------------------------------------------------------
; Function: timer3_timeout_elapsed_carry
; Address : 0x490C
; Notes   : Inferred usb helper; touches timer,usb. Calls: usb_disconnect_wait_clear_state.
; ---------------------------------------------------------------------------
timer3_timeout_elapsed_carry:
    btfss       T3CON, 0, ACCESS
    bra         timer3_timeout_elapsed_carry__timer_stopped
    bcf         STATUS, 0, ACCESS
    bra         timer3_timeout_elapsed_carry__return
timer3_timeout_elapsed_carry__timer_stopped:
    bsf         STATUS, 0, ACCESS
timer3_timeout_elapsed_carry__return:
    return      0
usb_reinit_after_wake__clear_pending_and_poll_host:
    btfsc       UCON, 3, ACCESS
    rcall       usb_disconnect_wait_clear_state
    clrf        usb_reinit_pending_b0, BANKED
    bra         usb_poll_host_presence_reinit_or_shutdown


; ---------------------------------------------------------------------------
; Function: usb_activity_settle_delay_with_clrwdt
; Address : 0x4924
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
usb_activity_settle_delay_with_clrwdt:
    movlw       0x03
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    clrf        addr_low_counter_or_payload_scratch_byte, ACCESS
    bra         usb_delay_countdown_with_clrwdt__check_remaining


; ---------------------------------------------------------------------------
; Function: timer3_blocking_delay_1ms
; Address : 0x492E
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
timer3_blocking_delay_1ms:
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movlw       0x01
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    bra         timer3_blocking_delay


; ---------------------------------------------------------------------------
; Function: uart_wake_reconfigure_tx_only_and_resync_parser      (wake-time TX re-arm, RX still off)
; Address : 0x4938
; ---------------------------------------------------------------------------
; Wake-time cmd_dispatch_gated can emit BF/08 over the serial link before the
; reconnect window fully re-opens.  Reuse uart_config to restore baud/SPEN/TXEN,
; then immediately clear CREN so CONTROL polls cannot accumulate into RCREG
; while GIE is still masked across the remaining wake-time housekeeping.
; ---------------------------------------------------------------------------
uart_wake_reconfigure_tx_only_and_resync_parser:
    rcall       uart_config
    bcf         RCSTA, 4, ACCESS
    bra         uart_parser_resync


; ---------------------------------------------------------------------------
; Function: uart_reconfigure_and_resync_parser
; Address : 0x4938
; Notes   : Inferred uart helper routine. Calls: uart_config, uart_parser_resync.
; ---------------------------------------------------------------------------
uart_reconfigure_and_resync_parser:
    rcall       uart_config
    bra         uart_parser_resync


; ---------------------------------------------------------------------------
; Function: timer3_blocking_delay_2ms
; Address : 0x4942
; Notes   : Inferred core helper routine.
; ---------------------------------------------------------------------------
timer3_blocking_delay_2ms:
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movlw       0x02
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    bra         timer3_blocking_delay


; ---------------------------------------------------------------------------
; Function: timer3_stop_interrupt_countdown
; Address : 0x494C
; Notes   : Inferred timer helper; touches timer.
; ---------------------------------------------------------------------------
timer3_stop_interrupt_countdown:
    bcf         T3CON, 0, ACCESS
    bcf         PIR2, 1, ACCESS
    bcf         PIE2, 1, ACCESS
    return      0


copy_computed_volume_to_logical_volume:
    call        chain_copy, 0x0     ; size T89: table-driven copy run
    db          0x00, 0x00, computed_volume_b0_op, logical_volume_b0_op, 0x04, 0xFF  ; chain_copy block descriptor (single db: gpasm pads per directive)
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
wait_trmt_bounded__poll_trmt:
    btfsc       TXSTA, 1, ACCESS            ; TRMT?
    return      0
    rcall       wait_tick
    bnc         wait_trmt_bounded__poll_trmt
    return      0

wait_sen_bounded:
    rcall       wait_seed
    movlw       0x01
    bra         wait_sspcon2_clear_mask_w

wait_rsen_bounded:
    rcall       wait_seed
    movlw       0x02
    bra         wait_sspcon2_clear_mask_w

wait_pen_bounded:
    rcall       wait_seed
    movlw       0x04
    bra         wait_sspcon2_clear_mask_w

wait_acken_bounded:
    rcall       wait_seed
    movlw       0x10
wait_sspcon2_clear_mask_w:
    andwf       SSPCON2, W, ACCESS
    bz          wait_sspcon2_clear_mask_w__return
    rcall       wait_tick
    bnc         wait_sspcon2_clear_mask_w
wait_sspcon2_clear_mask_w__return:
    return      0

wait_bf_clear_bounded:
    rcall       wait_seed
wait_bf_clear_bounded__poll_until_bf_clear:
    btfss       SSPSTAT, 0, ACCESS          ; BF set?
    return      0                           ; BF=0: buffer empty, done
    rcall       wait_tick
    bnc         wait_bf_clear_bounded__poll_until_bf_clear
    return      0                           ; C=1: timed out

wait_bf_set_bounded:
    rcall       wait_seed
wait_bf_set_bounded__poll_until_bf_set:
    btfsc       SSPSTAT, 0, ACCESS          ; BF set?
    return      0
    rcall       wait_tick
    bnc         wait_bf_set_bounded__poll_until_bf_set
    return      0                           ; C=1: timed out

wait_sspif_bounded:
    rcall       wait_seed
wait_sspif_bounded__poll_until_sspif:
    btfsc       PIR1, 3, ACCESS             ; SSPIF set?
    return      0
    rcall       wait_tick
    bnc         wait_sspif_bounded__poll_until_sspif
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
i2c_reenable_sda_sspen:
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
    rcall       mssp_hard_reset_smp_master
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
    movwf       i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS           ; save in ram_0x00D (uart_tx clobbers ram_0x003)
    rcall       bf_byte_tx
    movlw       0x08
    rcall       uart_tx_byte_blocking
    movf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, W, ACCESS
    bra         uart_tx_byte_blocking

bf_frame_header_tx:
    rcall       mark_chain_tx_emitted_bsr0
bf_byte_tx:
    movlw       0xBF
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
    clrf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    bsf         i2c_flag_or_flash_math_uart_cmd_scratch_byte, 0, ACCESS
    bra         i2c_timeout_recover_common

;@routine i2c_timeout_recover_advertise entry_bsr=unknown exit_bsr=0
i2c_timeout_recover_advertise:
    clrf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    btfsc       SSPCON2, 2, ACCESS
    bsf         i2c_flag_or_flash_math_uart_cmd_scratch_byte, 0, ACCESS         ; remember PEN-pending timeout
i2c_timeout_recover_common:
    diag_inc_sat diag_i                      ; I: I2C/MSSP transport timeout
    diag_inc_sat diag_r                      ; R: recovery branch entered
    movlb       0x2
    bsf         i2c_recover_flags_b2, 0, BANKED ; next clean I2C entry bus-clears
    rcall       mssp_hard_reset_smp_master
    btfsc       i2c_flag_or_flash_math_uart_cmd_scratch_byte, 0, ACCESS
    bra         i2c_timeout_skip_bus_probe
    rcall       i2c_bus_clear
    rcall       dsp_ping                     ; updates bit6 if DSP still NACKs
i2c_timeout_skip_bus_probe:
    movlb       0x0
    bcf         SSPCON1, 7, ACCESS           ; clear WCOL after aborted tx
    bcf         SSPCON1, 6, ACCESS           ; clear SSPOV after aborted rx
    bsf         dsp_fault_flags_b0, 2, BANKED   ; keep timeout visible after ACK ping
    rcall       send_dsp_fault_status
    bsf         STATUS, 0, ACCESS
    return      0

; ---------------------------------------------------------------------------
; cmd 0x21 — Diagnostics counter reply burst (V3.2 Layer 5)
; ---------------------------------------------------------------------------
; Reached from uart_link_parser_drain_rx_and_forward dispatch when CONTROL sends
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
;        diag_low_nibble_reply_burst, which walks the 7 counters via POSTINC0.
;   out: returns via uart_link_parser__handler_return_tail (the parser tail
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
    ; chain_tx_emitted is set by shared diag_low_nibble_reply_burst.
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
    ; FSR0 walk and the shared diag_low_nibble_reply_burst helper (cmd 0x22 reuses
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
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movlw       0x21                        ; first sub-cmd byte
    movwf       i2c_coeff_3_acc, ACCESS
    lfsr        FSR0, diag_i_b2_phys                ; 0x2E5 — first diag counter
    bra         diag_low_nibble_reply_burst

; ---------------------------------------------------------------------------
; cmd 0x22 — Reset-cause flags reply burst (V3.2 rev 0x37 Tier-1)
; ---------------------------------------------------------------------------
; Reached from uart_link_parser_drain_rx_and_forward dispatch when CONTROL sends
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
;        calls diag_low_nibble_reply_burst, which walks the 4 reset-cause flag
;        cells via POSTINC0.
;   out: returns via uart_link_parser__handler_return_tail (the parser tail
;        used by every cmd handler), so dispatch + forwarding to PB2
;        stays consistent with stock cmd handlers.
;   side: FSR0-based reads are bank-agnostic; the body never asserts a
;         specific bank.  uart_tx_byte_blocking's timeout fallback does
;         an unconditional `movlb 0x0`, so a wedged-and-recovered TX
;         path can leave BSR at 0 on exit.  Callers that depend on a
;         specific bank must reset BSR themselves.  Same shape as
;         cmd21_diag_query_handler; both share diag_low_nibble_reply_burst.
; ---------------------------------------------------------------------------
cmd22_reset_flags_query_handler:
    ; chain_tx_emitted is set by shared diag_low_nibble_reply_burst.
    ; Reuses diag_low_nibble_reply_burst (defined immediately below) — exactly
    ; the same wire shape as cmd 0x21 but with a different FSR0 base
    ; (reset-cause flag cells) and different sub-cmd range (0x28..0x2B).
    movlw       0x2C                        ; sentinel: stop AFTER BF/2B sent
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movlw       0x28                        ; first sub-cmd byte
    movwf       i2c_coeff_3_acc, ACCESS
    lfsr        FSR0, diag_reset_por_b2_phys        ; 0x2ED — first reset-flag cell
    bra         diag_low_nibble_reply_burst

; ---------------------------------------------------------------------------
; cmd 0x23 — Link-health ping reply (V1.71/V3.2 freshness MVP)
; ---------------------------------------------------------------------------
; Reached from uart_link_parser_drain_rx_and_forward dispatch when CONTROL sends
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
uart_link_parser__handler_return_tail_trampoline:
    goto        uart_link_parser__handler_return_tail

cmd23_health_query_handler:
    rcall       bf_frame_header_tx
    movlw       0x2C
    rcall       uart_tx_byte_blocking
    movlw       0x00
    rcall       uart_tx_byte_blocking
    bcf         active_flags_acc, 6, ACCESS     ; suppress cmd-XOR ACK echo
    bra         uart_link_parser__handler_return_tail_trampoline

; ---------------------------------------------------------------------------
; cmd 0x25 — MAIN identity reply (V1.73/V3.5 diagnostics title)
; ---------------------------------------------------------------------------
; Reached when CONTROL sends [B1/B2, 0x25, id].  Emits seven chain-safe
; frames:
;   BF/4F/id, BF/50/major, BF/51/minor,
;   BF/52/rev_lo_hi, BF/53/rev_lo_lo, BF/54/rev_hi_hi, BF/55/rev_hi_lo
; BF/52..53 intentionally carry the low byte first so older V1.72 CONTROL
; builds still display the legacy xNN revision when paired with V3.5.
; All payload bytes are masked below 0x80; the release revision is split
; into nibbles so future revs above 0x7F cannot look like route bytes.
; ---------------------------------------------------------------------------
cmd25_identity_query_handler:
    ; START carries the full 6-bit route-safe query id; the remaining
    ; six payloads are low nibbles and can reuse diag_low_nibble_reply_burst.
    rcall       bf_frame_header_tx
    movlw       0x4F
    rcall       uart_tx_byte_blocking
    movf        current_cmd_data_b0, W, BANKED        ; query id
    andlw       0x3F
    rcall       uart_tx_byte_blocking

    movlw       0x03                        ; V3.5 identity major
    movwf       length_mask_or_divisor_low_scratch_byte, ACCESS
    movlw       0x05                        ; V3.5 identity minor
    movwf       status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x08                        ; V3.5_IDENTITY_REV_LO_HI
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    movlw       0x04                        ; V3.5_IDENTITY_REV_LO_LO
    movwf       flash_end_high_or_loop_mask_scratch_byte, ACCESS
    movlw       0x00                        ; V3.5_IDENTITY_REV_HI_HI
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    movlw       0x00                        ; V3.5_IDENTITY_REV_HI_LO
    movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    movlw       0x56                        ; sentinel: stop AFTER BF/55 sent
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movlw       0x50                        ; first identity payload sub-cmd
    movwf       i2c_coeff_3_acc, ACCESS
    lfsr        FSR0, saved_w_b0_phys                ; major/minor/rev nibbles staging
    bra         diag_low_nibble_reply_burst

; ---------------------------------------------------------------------------
; cmd 0x26 — preset filename query (V3.5/V1.73 Preset LCD)
; ---------------------------------------------------------------------------
; Reached when CONTROL sends [B1/B2, 0x26, id].  The id format is
; (generation<<2)|(target_bit<<1)|slot.  V1 display uses PB1, but MAIN just
; echoes the id it receives so the same protocol is PB2-ready.
;
; The handler arms a tiny foreground job and returns through the normal parser
; tail.  filename_reply_emit_next_frame_if_ready later emits one BF frame per main-loop pass
; after all other chain senders had a chance to set chain_tx_emitted.
; ---------------------------------------------------------------------------
cmd26_filename_query_handler:
    movlb       0x02
    btfsc       filename_rev_b2, 0, BANKED
    bra         cmd26_filename_query_handler__suppress_ack_and_return
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
    bz          cmd26_filename_query_handler__select_active_ram_source
    movlw       preset_filename_eeprom_a
    btfsc       fn_job_src_kind_b2, 0, BANKED
    movlw       preset_filename_eeprom_b
    movwf       fn_job_src_kind_b2, BANKED       ; requested inactive EEPROM base
    bra         cmd26_filename_len_init
cmd26_filename_query_handler__select_active_ram_source:
    clrf        fn_job_src_kind_b2, BANKED       ; requested slot == active RAM

cmd26_filename_len_init:
    clrf        fn_job_len_b2, BANKED
cmd26_filename_query_handler__scan_printable_length:
    movf        fn_job_len_b2, W, BANKED
    xorlw       preset_filename_len
    bz          cmd26_filename_arm
    movf        fn_job_len_b2, W, BANKED
    rcall       filename_read_source_at_w
    addlw       0xE0                            ; char >= 0x20?
    bnc         cmd26_filename_arm
    sublw       0x5E                            ; char <= 0x7E?
    bnc         cmd26_filename_arm
    incf        fn_job_len_b2, F, BANKED
    bra         cmd26_filename_query_handler__scan_printable_length

cmd26_filename_arm:
    movlw       0x2F                         ; prefix-first default
    movwf       fn_job_start_cmd_b2, BANKED
    movlw       0x10
    cpfsgt      fn_job_len_b2, BANKED           ; len > 16?
    bra         cmd26_filename_query_handler__verify_rev_and_arm_job

cmd26_filename_compare_prefix16:
    movf        fn_job_src_kind_b2, W, BANKED
    movwf       fname_tx_gap_hi_b2, BANKED      ; save requested source kind
    clrf        fn_job_idx_b2, BANKED
cmd26_filename_query_handler__compare_prefix16_next_char:
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
    movlw       preset_filename_eeprom_b
    btfsc       active_flags_acc, 2, ACCESS
    movlw       preset_filename_eeprom_a
    movwf       fn_job_src_kind_b2, BANKED       ; inactive EEPROM base
cmd26_filename_compare_read_other:
    movf        fn_job_idx_b2, W, BANKED
    rcall       filename_read_source_at_w
    movlb       0x02
    cpfseq      fname_tx_gap_lo_b2, BANKED
    bra         cmd26_filename_query_handler__restore_source_after_compare
    incf        fn_job_idx_b2, F, BANKED
    movlw       0x10
    cpfseq      fn_job_idx_b2, BANKED
    bra         cmd26_filename_query_handler__compare_prefix16_next_char
    movlw       0x2E                         ; first 16 match: rest on tail
    movwf       fn_job_start_cmd_b2, BANKED
cmd26_filename_query_handler__restore_source_after_compare:
    movf        fname_tx_gap_hi_b2, W, BANKED
    movwf       fn_job_src_kind_b2, BANKED

cmd26_filename_query_handler__verify_rev_and_arm_job:
    btfsc       filename_rev_b2, 0, BANKED
    bra         cmd26_filename_query_handler__suppress_ack_and_return
    movf        filename_rev_b2, W, BANKED
    cpfseq      fn_job_rev_b2, BANKED
    bra         cmd26_filename_query_handler__suppress_ack_and_return
    clrf        fn_job_idx_b2, BANKED
    clrf        fname_tx_gap_lo_b2, BANKED
    clrf        fname_tx_gap_hi_b2, BANKED
    movlw       0x01
    movwf       fn_job_state_b2, BANKED
cmd26_filename_query_handler__suppress_ack_and_return:
    bcf         active_flags_acc, 6, ACCESS      ; suppress cmd-XOR ACK echo
    bra         uart_link_parser__handler_return_tail_trampoline

filename_read_source_at_w:
    movwf       fn_job_tmp_b2, BANKED
    movf        fn_job_src_kind_b2, W, BANKED
    bz          filename_read_source_at_w__read_active_ram_slot
    addwf       fn_job_tmp_b2, W, BANKED
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    bra         eeprom_read_byte
filename_read_source_at_w__read_active_ram_slot:
    lfsr        FSR2, preset_filename_ram_base
    movf        fn_job_tmp_b2, W, BANKED
    addwf       FSR2L, F, ACCESS
    movf        INDF2, W, ACCESS
    return      0

filename_reply_emit_next_frame_if_ready:
    movlb       0x02
    movf        fn_job_state_b2, W, BANKED
    bz          filename_reply_job_service__return
    btfss       chain_tx_emitted_b2, 0, BANKED
    bra         filename_reply_job_service__check_tx_gap
    clrf        fname_tx_gap_lo_b2, BANKED
    movlw       0x01
    movwf       fname_tx_gap_hi_b2, BANKED
    bra         filename_reply_job_service__return
filename_reply_job_service__check_tx_gap:
    movf        fname_tx_gap_lo_b2, F, BANKED
    bnz         filename_reply_job_service__decrement_gap_low
    movf        fname_tx_gap_hi_b2, F, BANKED
    bz          filename_reply_job_service__ready_to_emit
    decf        fname_tx_gap_hi_b2, F, BANKED
filename_reply_job_service__decrement_gap_low:
    decf        fname_tx_gap_lo_b2, F, BANKED
    bra         filename_reply_job_service__return
filename_reply_job_service__ready_to_emit:
    btfsc       filename_rev_b2, 0, BANKED
    bra         filename_reply_job_service__abort_stale_reply
    movf        filename_rev_b2, W, BANKED
    cpfseq      fn_job_rev_b2, BANKED
    bra         filename_reply_job_service__abort_stale_reply
    movf        fn_job_state_b2, W, BANKED
    xorlw       0x01
    bz          filename_reply_send_start
    xorlw       0x03
    bz          filename_reply_send_len
    xorlw       0x01
    bz          filename_reply_send_char_or_end
filename_reply_job_service__abort_stale_reply:
    clrf        fn_job_state_b2, BANKED
filename_reply_job_service__return:
    return      0

filename_reply_send_start:
    movf        fn_job_start_cmd_b2, W, BANKED
    rcall       filename_emit_id_frame_cmd_w
    incf        fn_job_state_b2, F, BANKED
    return      0

filename_reply_send_len:
    movlw       0x2D
    movwf       i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    movf        fn_job_id_b2, W, BANKED
    xorwf       fn_job_len_b2, W, BANKED
    movwf       flash_upper_or_uart_count_scratch_byte, ACCESS
    rcall       filename_emit_frame
    incf        fn_job_state_b2, F, BANKED
    return      0

filename_reply_send_char_or_end:
    movf        fn_job_idx_b2, W, BANKED
    cpfseq      fn_job_len_b2, BANKED
    bra         filename_reply_send_char
filename_reply_send_end:
    movlw       0x4E
    rcall       filename_emit_id_frame_cmd_w
    clrf        fn_job_state_b2, BANKED
    return      0

filename_reply_send_char:
    movf        fn_job_idx_b2, W, BANKED
    rcall       filename_read_source_at_w
    movwf       flash_upper_or_uart_count_scratch_byte, ACCESS
    movlb       0x02
    movlw       0x30
    addwf       fn_job_idx_b2, W, BANKED
    movwf       i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    rcall       filename_emit_frame
    incf        fn_job_idx_b2, F, BANKED
    return      0

filename_emit_id_frame_cmd_w:
    movwf       i2c_flag_or_flash_math_uart_cmd_scratch_byte, ACCESS
    movf        fn_job_id_b2, W, BANKED
    movwf       flash_upper_or_uart_count_scratch_byte, ACCESS
    rcall       filename_emit_frame
    return      0

filename_emit_frame:
    movlb       0x02
    bsf         chain_tx_emitted_b2, 0, BANKED
    clrf        fname_tx_gap_lo_b2, BANKED
    movlw       0x01
    movwf       fname_tx_gap_hi_b2, BANKED
    movlw       0xBF
    rcall       uart_tx_byte_blocking
    movf        i2c_flag_or_flash_math_uart_cmd_scratch_byte, W, ACCESS
    rcall       uart_tx_byte_blocking
    movf        flash_upper_or_uart_count_scratch_byte, W, ACCESS
    rcall       uart_tx_byte_blocking
    movlb       0x02
    return      0

; ---------------------------------------------------------------------------
; diag_low_nibble_reply_burst — shared helper for cmd 0x21/0x22 and cmd 0x25 tail
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
diag_low_nibble_reply_burst:
    rcall       bf_frame_header_tx
    movf        i2c_coeff_3_acc, W, ACCESS
    rcall       uart_tx_byte_blocking
    movf        POSTINC0, W, ACCESS
    andlw       0x0F                        ; chain-forwarder safe (data < 0x80)
    rcall       uart_tx_byte_blocking
    incf        i2c_coeff_3_acc, F, ACCESS
    movf        addr_high_table_row_or_checksum_scratch_byte, W, ACCESS
    cpfseq      i2c_coeff_3_acc, ACCESS
    bra         diag_low_nibble_reply_burst
    bcf         active_flags_acc, 6, ACCESS     ; suppress cmd-XOR ACK echo
    bra         uart_link_parser__handler_return_tail_trampoline

; ---------------------------------------------------------------------------
; Volume DSP Write (Fix B + B' + recovery)
; ---------------------------------------------------------------------------
volume_dsp_write:
    movlb       0x0
    bcf         dsp_fault_flags_b0, 2, BANKED  ; clear ACKSTAT latch
    rcall       i2c_tas3108_coeff_write
    movlb       0x0                          ; helper may leave BSR != 0
    btfsc       dsp_fault_flags_b0, 2, BANKED  ; NACKed?
    bra         vol_write_nacked
    ; Success: DSP responded, clear all fault state
    bcf         event_flags_b0, 3, BANKED      ; clear volume dirty
    bcf         event_flags_b0, 5, BANKED      ; clear mute dirty only after verified TAS write
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
    rcall       diag_inc_sat_fsr0
    rcall       i2c_bus_clear
    rcall       dsp_ping
vol_exhausted_skip_i2c:
    movlb       0x0                          ; macro / dsp_ping may leave BSR != 0
    btfsc       dsp_fault_flags_b0, 6, BANKED  ; V3.2 Layer 5: skip diag_d if already SET (no transition)
    bra         vol_diag_d_skip
    movlb       0x02
    lfsr        FSR0, diag_d_b2_phys                 ; executed only on 0→1 transition
    rcall       diag_inc_sat_fsr0
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
; Notes   : Keep legacy preset_table_apply_entry_legacy_blocking contract untouched.
;           Return with C=0 on success, C=1 on bounded START/STOP timeout.
; ---------------------------------------------------------------------------
preset_job_init_cursor_from_active:
    movlb       0x2
    clrf        preset_job_index_b2, BANKED
    clrf        preset_job_tbl_lo_b2, BANKED
    movlw       0x56
    btfsc       active_flags_acc, 2, ACCESS
    movlw       0x4C
    movwf       preset_job_tbl_hi_b2, BANKED
    return      0

preset_job_apply_i2c_from_job_cursor:
    movff       preset_job_tbl_lo_b2_phys, eeprom_record_count_or_flash_addr_upper_or_preset_addr_low_phys
    movff       preset_job_tbl_hi_b2_phys, flash_addr_shadow_low_or_preset_table_addr_hi_phys
    bra         preset_job_apply_i2c_entry

preset_job_advance_cursor_to_next_table_row:
    movlb       0x2
    movlw       0x18
    addwf       preset_job_tbl_lo_b2, F, BANKED
    movlw       0x00
    addwfc      preset_job_tbl_hi_b2, F, BANKED
    incf        preset_job_index_b2, F, BANKED
    return      0

preset_job_apply_i2c_entry:
preset_job_apply_i2c_entry:
    ; FIELD-4A/FIELD-10: the shared i2c_byte_tx engine latches
    ; dsp_fault_flags.2 on any master-TX NACK.  A pre-existing latch means a
    ; prior lifecycle write (notably the active7 zero-volume guard) failed, so
    ; do not clear-and-continue into coefficient rows; fail before the row and
    ; let the caller retry from a muted/fault-visible state.
    movlb       0x0
    btfsc       dsp_fault_flags_b0, 2, BANKED
    bra         preset_job_apply_i2c_timeout
preset_job_apply_i2c_entry_go:
    call        preset_table_apply_entry_core_async, 0x0
    bcf         float_divisor_or_preset_flag_scratch_byte, 0, ACCESS     ; C-neutral cleanup before bc
    bc          preset_job_apply_i2c_timeout
    movlb       0x0
    btfss       dsp_fault_flags_b0, 2, BANKED
    bra         preset_job_apply_i2c_entry__return_success
    bsf         STATUS, 0, ACCESS           ; NACKed entry -> C=1, retry it
    bra         preset_job_apply_i2c_timeout
preset_job_apply_i2c_entry__return_success:
    bcf         STATUS, 0, ACCESS           ; C=0: success / benign no-op
    return      0
preset_job_apply_i2c_timeout:
    bra         i2c_timeout_recover_advertise

; ---------------------------------------------------------------------------
; Preset Select Handler (V3.2 non-blocking — cmd=0x20)
; Parser entry: ALWAYS record the target preset and start/coalesce the async
; preset job.  Actual work is done by advance_preset_job_state_machine from the main loop.
;
; V3.4 BUG-V34V173-5: the handler no longer gates on the USB filename-write
; bit (filename_dirty_flags.bit6).  The old parser-entry gate dropped the
; broadcast without storing the target, so a preset change coinciding with a
; host filename write was lost on this unit until the ~6 s full-sync
; re-broadcast (cross-PB preset/coeff desync).  The deferral the gate wanted
; lives in the layer that owns the hazard: preset_job_pending parks un-muted
; while bit6 is set, and the HOLDING -> APPLY transition keeps its bit6
; backstop immediately before preset_load_filename (the only call that can
; clobber the host's just-written filename RAM).  persist_dirty_runtime_state_to_eeprom
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
    bnz         preset_select_handler__return_to_parser
    ; Compare target with current preset
    rcall       preset_target_compare_active_bsr2
    bz          preset_select_handler__return_to_parser  ; no change needed
    ; Start new job
    movlw       0x01                        ; PENDING state
    movwf       preset_job_state_b2, BANKED
    clrf        preset_job_flags_b2, BANKED
    btfsc       active_flags_acc, 4, ACCESS     ; user already muted?
    bsf         preset_job_flags_b2, 1, BANKED ; remember user mute desire
preset_select_handler__return_to_parser:
    bra         uart_link_parser__handler_return_tail_trampoline

preset_target_compare_active_bsr2:
    movf        preset_job_target_b2, W, BANKED
    btfsc       active_flags_acc, 2, ACCESS
    xorlw       0x01
    return      0

preset_filename_begin_xact_w:
    movlb       0x02
    incf        filename_rev_b2, F, BANKED
    movlb       0x00
    btfsc       active_flags_acc, 2, ACCESS
    retlw       preset_filename_eeprom_b
    retlw       preset_filename_eeprom_a

preset_filename_finish_xact_bsr0:
    movlb       0x02
    incf        filename_rev_b2, F, BANKED
    movlb       0x00
    return      0

; --- Persist dirty filename to EEPROM (outgoing preset slot) ---
preset_persist_filename:
    rcall       preset_filename_begin_xact_w   ; seqlock odd: backing store mutating
    movwf       count_flash_page_or_i2c_payload_scratch_byte, ACCESS
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    lfsr        FSR2, preset_filename_ram_base
    movlw       preset_filename_len
    movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
preset_pf_lp:
    movff       POSTINC2, eeprom_or_filename_data_or_flash_buffer_ptr_low_or_signature_low_phys
    rcall       eeprom_write_byte_if_changed
    incf        count_flash_page_or_i2c_payload_scratch_byte, F, ACCESS
    decfsz      eeprom_mask_or_flash_src_high_scratch_byte, F, ACCESS
    bra         preset_pf_lp
    rcall       preset_filename_finish_xact_bsr0 ; seqlock even: stable again
    bcf         filename_dirty_flags_b0, 5, BANKED
    return      0

; --- Load filename from EEPROM (incoming preset slot) ---
preset_load_filename:
    rcall       preset_filename_begin_xact_w   ; seqlock odd: RAM slot mutating
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    lfsr        FSR2, preset_filename_ram_base
    movlw       preset_filename_len
    movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
preset_lf_lp:
    rcall       eeprom_read_byte
    movwf       POSTINC2
    incf        addr_low_counter_or_payload_scratch_byte, F, ACCESS
    decfsz      eeprom_mask_or_flash_src_high_scratch_byte, F, ACCESS
    bra         preset_lf_lp
    bra         preset_filename_finish_xact_bsr0 ; seqlock even: stable again

; --- Force-mute DSP output ---
preset_force_mute:
    movlb       0x0
    bsf         active_flags_acc, 4, ACCESS
    bsf         active_flags_acc, 5, ACCESS
    bcf         event_flags_b0, 5, BANKED
    goto        tas3108_write_zero_volume_coeff   ; tail-call; far-safe after M1 growth

; ---------------------------------------------------------------------------
; Preset Job State Machine (V3.2: async delayed preset switching)
; Called once per main-loop pass from run_main_service_pass.
; States: 0=IDLE, 1=PENDING, 2=HOLDING, 3=APPLY, 4=COMMIT
; ---------------------------------------------------------------------------
advance_preset_job_state_machine:
    movlb       0x2
    movf        preset_job_state_b2, W, BANKED
    bz          preset_job_service__return              ; IDLE — nothing to do

    ; Cancel on standby shutdown or reconnect
    btfss       active_flags_acc, 3, ACCESS     ; active flag clear → standby
    bra         preset_job_cancel
    btfsc       active_flags_acc, 7, ACCESS     ; reconnect pending
    bra         preset_job_cancel

    ; Dispatch by state
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

preset_job_service__return:
    return      0

; --- PENDING (1): persist filename, force mute, configure hold timer ---
preset_job_pending:
    movlb       0x0
    ; V3.4 BUG-V34V173-5/FIELD-10 exploratory follow-up: while a USB cmd 0x03
    ; filename WRITE is in flight (bit6 set), skip filename persistence but
    ; still enter the normal force-mute/timer path.  HOLDING's bit6 backstop
    ; continues to protect preset_load_filename from clobbering host RAM.
    btfsc       filename_dirty_flags_b0, 6, BANKED
    bra         preset_job_pending_force_mute
    ; Persist dirty filename for outgoing preset
    btfsc       filename_dirty_flags_b0, 5, BANKED
    rcall       preset_persist_filename

preset_job_pending_force_mute:
    ; Force mute if user is not already muted
    movlb       0x2
    btfsc       active_flags_acc, 4, ACCESS     ; already muted?
    bra         preset_job_pending_no_mute
    bsf         preset_job_flags_b2, 0, BANKED ; flag: we forced mute
    rcall       preset_force_mute
    bra         preset_job_pending_timer

preset_job_pending_no_mute:
    bcf         preset_job_flags_b2, 0, BANKED ; we did not force mute

preset_job_commit_rearm:
preset_job_pending_timer:
    ; Start ISR-based Timer3 countdown (150 ticks, ~150 ms)
    ; The Timer3 ISR decrements ram_0x08C:08D on each overflow;
    ; HOLDING polls that pair for zero.
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movlw       0x96                        ; 150 decimal
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    rcall       timer3_arm_interrupt_countdown

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
    rcall       preset_target_compare_active_bsr2
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

    ; Initialize table-apply state with a job-owned PHYSICAL cursor.  Async
    ; APPLY bypasses the live active_flags remap, so a later lifecycle or
    ; coalesced target change cannot silently move this transaction's source.
    rcall       preset_job_init_cursor_from_active

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
    ; If CONTROL changed target during APPLY/retry, stop the current table
    ; walk before another row is written and restart from row 0 after the
    ; normal hold window.  The force-mute context stays owned by this job.
    rcall       preset_target_compare_active_bsr2
    bnz         preset_job_commit_rearm
    movlw       0x60                        ; 96 regular entries
    cpfslt      preset_job_index_b2, BANKED    ; skip if index < 96
    bra         preset_job_apply_final      ; index >= 96 → final entry

    ; Apply regular entry from tracked address
    rcall       preset_job_apply_i2c_from_job_cursor
    bc          preset_job_apply_retry      ; timeout: retry same entry next pass

    ; Advance address by 0x18 and increment index
    bra         preset_job_advance_cursor_to_next_table_row

preset_job_apply_retry:
    movlb       0x2
    return      0

preset_job_apply_final:
    ; The regular-entry cursor has advanced to the job-owned physical final
    ; row (A=0x5F00, B=0x5500).
    rcall       preset_job_apply_i2c_from_job_cursor
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
    rcall       preset_target_compare_active_bsr2
    bnz         preset_job_commit_rearm
    ; FIELD-7: existing lifecycle reapply is the final selected-image owner.
    ; It runs immediately after advance_preset_job_state_machine, while TAS30 is still zero.
    bsf         active_flags_acc, 7, ACCESS
    btfss       preset_job_flags_b2, 0, BANKED ; did we force mute?
    bra         preset_job_commit_idle      ; no → leave mute as user had it
    btfsc       preset_job_flags_b2, 1, BANKED ; user wants mute?
    bra         preset_job_commit_idle      ; yes → stay muted

; --- Cancel with unmute (coalesced back to same preset) ---
preset_job_cancel_unmute:
    rcall       timer3_stop_interrupt_countdown     ; stop Timer3 and clear/mask IRQ
    movlb       0x2
    btfss       preset_job_flags_b2, 0, BANKED ; did we force mute?
    bra         preset_job_service__clear_state_and_return
    btfsc       preset_job_flags_b2, 1, BANKED ; user wants mute?
    bra         preset_job_service__clear_state_and_return
    bcf         active_flags_acc, 4, ACCESS
    bcf         active_flags_acc, 5, ACCESS
    movlb       0x0
    bsf         event_flags_b0, 3, BANKED      ; restore volume
    bra         preset_job_service__clear_state_and_return

; --- Cancel (standby/reconnect): clear state, don't touch mute ---
preset_job_cancel:
    rcall       timer3_stop_interrupt_countdown     ; stop Timer3 and clear/mask IRQ
    ; Standby/reconnect owns the next audible lifecycle.  If this job
    ; force-muted a partial image, keep it muted rather than clearing the
    ; safety shadow while the table transaction is incomplete.

preset_job_commit_idle:
preset_job_service__clear_state_and_return:
    movlb       0x2
    clrf        preset_job_state_b2, BANKED
    return      0

; ---------------------------------------------------------------------------
; HID Diagnostic Memory Read (cmd=0x43)
; Request : ram_0x11B=region (0=flash,1=eeprom), 0x11C/0x11D=addr, 0x11E=len
; Response: 0x15A=cmd, 0x15B=status, 0x15C=len, 0x15D..=data (max 61 bytes)
; ---------------------------------------------------------------------------
hid_diag_memread_dispatch:
    movlb       0x1
    lfsr        FSR2, usb_hid_ep1_in_report_cmd_selector_phys
    movlw       0x43
    movwf       POSTINC2, ACCESS
    clrf        POSTINC2, ACCESS
    movf        usb_hid_out_arg3_b1, W, BANKED
    movwf       POSTINC2, ACCESS
    bz          hid_diag_memread__reject_invalid_length
    movlw       0x3D
    cpfsgt      usb_hid_out_arg3_b1, BANKED
    bra         hid_diag_memread__dispatch_region
hid_diag_memread__reject_invalid_length:
    movlw       0x02
    bra         hid_diag_memread__stage_error_status
hid_diag_memread__dispatch_region:
    movf        usb_hid_out_arg0_b1, W, BANKED
    bz          hid_diag_memread__read_flash_region
    xorlw       0x01
    bz          hid_diag_memread__read_eeprom_region
    movlw       0x01
    bra         hid_diag_memread__stage_error_status
hid_diag_memread__read_flash_region:
    movff       usb_hid_out_arg1_phys, addr_low_counter_or_payload_scratch_phys
    movff       usb_hid_out_arg2_phys, addr_high_table_row_or_checksum_scratch_phys
    clrf        length_mask_or_divisor_low_scratch_byte, ACCESS
    clrf        status_addr_high_or_i2c_payload_scratch_byte, ACCESS
    movff       usb_hid_out_arg3_phys, computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys
    clrf        flash_end_high_or_loop_mask_scratch_byte, ACCESS
    movlw       0x5D
    movwf       flash_src_low_or_rx_length_scratch_byte, ACCESS
    movlw       0x01
    movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    call        flash_read, 0x0
    bra         hid_diag_memread__return_response
hid_diag_memread__read_eeprom_region:
    movf        usb_hid_out_arg1_b1, W, BANKED
    movwf       addr_low_counter_or_payload_scratch_byte, ACCESS
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    movf        usb_hid_out_arg3_b1, W, BANKED
    movwf       eeprom_mask_or_flash_src_high_scratch_byte, ACCESS
    lfsr        FSR2, usb_hid_ep1_in_report_byte3_phys
hid_diag_memread__copy_eeprom_byte_loop:
    rcall       eeprom_read_byte
    movwf       POSTINC2, ACCESS
    incf        addr_low_counter_or_payload_scratch_byte, F, ACCESS
    decfsz      eeprom_mask_or_flash_src_high_scratch_byte, F, ACCESS
    bra         hid_diag_memread__copy_eeprom_byte_loop
    bra         hid_diag_memread__return_response
hid_diag_memread__stage_error_status:
    movwf       usb_hid_ep1_in_report_byte1_b1, BANKED
hid_diag_memread__return_response:
    goto        hid_command_dispatch__clear_opcode_and_return

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
hid_diag_snapshot_copy_block_count_w:
    movwf       diff_count_update_compare_or_route_mask_scratch_byte, ACCESS
hid_diag_snapshot_copy_block__copy_next_byte:
    movf        POSTINC0, W, ACCESS
    movwf       POSTINC2, ACCESS
    decfsz      diff_count_update_compare_or_route_mask_scratch_byte, F, ACCESS
    bra         hid_diag_snapshot_copy_block__copy_next_byte
    return      0

hid_diag_snapshot_emit:
    lfsr        FSR2, usb_hid_ep1_in_report_cmd_selector_phys                ; HID IN buffer base
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
    rcall       hid_diag_snapshot_copy_block_count_w
    ; FSR0 now sits on diag_ra1_prev (0x2EC); skip past it to the
    ; reset-cause flag block at 0x2ED.
    incf        FSR0L, F, ACCESS
    ; [10..13] = 4 reset-cause flags from diag_reset_por..diag_reset_sw.
    movlw       0x04
    rcall       hid_diag_snapshot_copy_block_count_w
    ; [14..18] = 5 V3.4 SRC/DSP forensic counters (N L C T M) from
    ; diag_src_n..diag_src_m (0x3C0..0x3C4, BANK 3 upper) — appended
    ; AFTER the reset flags so the legacy 11-cell offsets stay stable
    ; for older hosts.
    lfsr        FSR0, diag_src_n
    movlw       0x05
    rcall       hid_diag_snapshot_copy_block_count_w
    ; [19..63] = padding — host sees length byte at [2]=0x10 so it
    ; stops parsing at offset 18.  Firmware version metadata is
    ; available via the existing cmd 0x06 probe (see hid_dispatch);
    ; cmd 0x44 stays focused on the diag block to keep the handler
    ; small enough to fit before the DSP preset tables at 0x4C00.
    goto        hid_command_dispatch__clear_opcode_and_return

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
; EEPROM Data (V3.5: legacy revision low byte updated at offset 0x82)
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
    db  0x03, 0x05, 0x84, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; V3.5 lineage: V3.2 diagnostics plus cmd 0x25 MAIN identity reply; third byte is the legacy low byte of the 16-bit release revision
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF  ; ................
    db  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x02  ; ................

    END
