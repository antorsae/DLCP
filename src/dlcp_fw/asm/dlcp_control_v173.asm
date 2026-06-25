; ===========================================================================
; DLCP CONTROL V1.73 — feature-bearing source rewrite
; ===========================================================================
; Target MCU : Microchip PIC18F25K20 @ ~16 MHz (4 MIPS)
; Baseline   : Cloned through the V1.72 feature-bearing source rewrite from
;              stock V1.6b.  V1.73 carries the features previously delivered
;              via the V1.61b / V1.62b / V1.63b / V1.64b binary overlays:
;
;                V1.61b — A/B preset switching (control_flags.6 = PRESET_BIT,
;                         preset menu screen, IR RC5 0x38 / 0x39, EEPROM 0x74)
;                V1.62b — UART OERR drain + reconnect wake (RECONNECT_*
;                         flag bits, wake frame on reconnect exit)
;                V1.63b — BF/08 DSP-fault parser + LCD ! indicator
;                         (DSP_FAULT_BIT, bf08_fault_byte, resync-on-clear)
;                V1.64b — explicit IR standby (0x3A) / wake (0x3B) endpoints
;
; Pairs with : V3.1+ MAIN (full feature surface) or stock V2.3 MAIN
;              (degrades gracefully — no presets, no fault UI).
;
; Spec       : docs/V16B_SOURCE_REWRITE_SPEC.md
; Generated  : scripts/convert_v16b_asm_to_gpasm.py produced the V1.7
;              baseline; V1.73 edits land in-place in this file via
;              direct source modification.
;
; Verification: gpasm assembles without errors; vector block (0x0000–0x004B),
;              bootloader (0x7800–0x7FFF), and config bits are byte-identical
;              to stock V1.6b. EEPROM matches stock except the V1.73 identity
;              bytes at 0x70–0x72 and preset byte at 0x74. Canonical release
;              revisions do not live in EEPROM: EEPROM[0x73] is runtime-owned,
;              so the monotonic release revision lives in the flashed metadata
;              block at 0x77B0 instead.
; ===========================================================================

        processor p18f25k20
        radix dec

        include p18f25k20.inc

        include dlcp_control_ram.inc

; The recognition of labels and registers is not always good, therefore
; be treated cautiously the results.

;===============================================================================
; DATA address definitions

Common_RAM      equ     0x000000                            ; size: 96 bytes

;===============================================================================
; CODE area

        ; code

        org     __CODE_START                                ; address: 0x000000

vector_reset:                                               ; address: 0x000000

        goto    bootloader_entry                                   ; dest: 0x007800
        dw      0xffff
        dw      0xffff

vector_int_high:                                            ; address: 0x000008

        goto    isr_entry                                   ; dest: 0x0003a6
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xfe
        call    lcd_command_or_eeprom_read, 0x0                           ; dest: 0x000190
        movlw   0x01

vector_int_low:                                             ; address: 0x000018

        call    lcd_command_or_eeprom_read, 0x0                           ; dest: 0x000190
        movlw   0x75
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d

isr_low_entry_hang_loop:                                                  ; address: 0x000020

        bra     isr_low_entry_hang_loop                                   ; dest: 0x000020
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff

aux_vector_cold_init_entry:                                                  ; address: 0x000040

        goto    app_cold_init                                   ; dest: 0x000366
        dw      0xffff
        dw      0xffff
        goto    isr_entry                                   ; dest: 0x0003a6

app_entry_defensive_stub:                                               ; address: 0x00004c

        ; FIELD-3: a full LCD clear destroys Preset row 0; mark it not-ready
        ; so the page service self-heals if we are parked on the Preset page.
        call    v173_preset_lcd_invalidate, 0x0
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xfe
        call    lcd_command_or_eeprom_read, 0x0                           ; dest: 0x000190
        movlw   0x01
        call    lcd_command_or_eeprom_read, 0x0                           ; dest: 0x000190
        movlw   0x75
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x30
        goto    delay_short_inner_spin_from_w                                ; dest: 0x0001d8


; ===========================================================================
; lcd_command @ 0x000066 — lcd_command
; ---------------------------------------------------------------------------
; Writes a command byte to the HD44780 LCD via the 4-bit nibble interface.
; LCD signals (per PIN_SEMANTICS):
;   RA5 = RS (0=command, 1=data)
;   RB4 = E  (strobe)
;   RB0..RB3 = D4..D7 (data nibble)
; Stages W into 0x017, asserts RS=0 via clrf 0x01 + bsf 0x01,7 (the
; high-bit pattern indicates command mode), then calls lcd_command_or_eeprom_read to
; latch the byte through the nibble engine and return.
; ===========================================================================
; lcd_command:
lcd_command:                                               ; address: 0x000066

        clrf    (Common_RAM + 1), A                         ; reg: 0x001
        bsf     (Common_RAM + 1), 0x7, A                    ; reg: 0x001
        movwf   (Common_RAM + 23), A                        ; reg: 0x017
        movlw   0xfe
        call    lcd_command_or_eeprom_read, 0x0                           ; dest: 0x000190
        movf    (Common_RAM + 23), W, A                     ; reg: 0x017
        goto    lcd_command_or_eeprom_read                                ; dest: 0x000190


; ===========================================================================
; delay_short_loop @ 0x000078 — delay_short_loop
; ---------------------------------------------------------------------------
; 16-bit delay loop scratch helper. Caller stages count via 0x07/0x10/0x11
; and the routine spins, calling delay_parameter_unit every iteration. Used to
; implement variable-duration LCD setup waits (40 ms power-up, 4.5 ms
; nibble-mode-set, 100 µs char delays). Combined with delay_parameter_unit
; for the LCD HD44780 reset sequence at 0x000086+.
; ===========================================================================
; delay_short_loop:
delay_short_loop:                                               ; address: 0x000078

        clrf    (Common_RAM + 7), A                         ; reg: 0x007
        movwf   (Common_RAM + 16), A                        ; reg: 0x010
        clrf    (Common_RAM + 17), A                        ; reg: 0x011
        bcf     Common_RAM, 0x3, A                          ; reg: 0x000
        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     Common_RAM, 0x3, A                          ; reg: 0x000
        movlw   0x05
        movwf   (Common_RAM + 6), A                         ; reg: 0x006
        movlw   0x27
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0x10
        rcall   delay_parameter_unit                                ; dest: 0x0000aa
        movlw   0x03
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0xe8
        rcall   delay_parameter_unit                                ; dest: 0x0000aa
        clrf    (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0x64
        rcall   delay_parameter_unit                                ; dest: 0x0000aa
        clrf    (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0x0a
        rcall   delay_parameter_unit                                ; dest: 0x0000aa
        movf    (Common_RAM + 16), W, A                     ; reg: 0x010
        bra     delay_parameter_unit__maybe_emit_ascii_digit                                   ; dest: 0x0000ba


; ===========================================================================
; delay_parameter_unit @ 0x0000AA — delay_parameter_unit
; ---------------------------------------------------------------------------
; Inner delay primitive used by delay_short_loop / delay_short. Counts down
; the {0x10:0x11} pair through the {0x0C:0x0E:0x0F} scratch chain,
; calling delay_parameter_unit__divide_u16_scratch (0x0001F0, 16-bit divide helper) on each tick to
; advance the working pointer. Returns when the counter reaches zero.
; ===========================================================================
; delay_parameter_unit:
delay_parameter_unit:                                               ; address: 0x0000aa

        movwf   (Common_RAM + 14), A                        ; reg: 0x00e
        movf    (Common_RAM + 17), W, A                     ; reg: 0x011
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movf    (Common_RAM + 16), W, A                     ; reg: 0x010
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        call    delay_parameter_unit__divide_u16_scratch, 0x0                           ; dest: 0x0001f0
        movf    (Common_RAM + 12), W, A                     ; reg: 0x00c

delay_parameter_unit__maybe_emit_ascii_digit:                                                  ; address: 0x0000ba

        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        dcfsnz  (Common_RAM + 6), F, A                      ; reg: 0x006
        bcf     Common_RAM, 0x3, A                          ; reg: 0x000
        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        bz      delay_parameter_unit__apply_zero_suppression
        subwf   (Common_RAM + 6), W, A                      ; reg: 0x006
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        bra     delay_parameter_unit__return                                   ; dest: 0x0000da

delay_parameter_unit__apply_zero_suppression:                                                  ; address: 0x0000ca

        movf    (Common_RAM + 12), W, A                     ; reg: 0x00c
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bcf     Common_RAM, 0x3, A                          ; reg: 0x000
        btfsc   Common_RAM, 0x3, A                          ; reg: 0x000
        bra     delay_parameter_unit__return                                   ; dest: 0x0000da
        addlw   0x30
        goto    lcd_command_or_eeprom_read                                ; dest: 0x000190

delay_parameter_unit__return:                                                  ; address: 0x0000da

        return  0x0


; ===========================================================================
; lcd_string_write_rom @ 0x0000DC — lcd_string_write_rom
; ---------------------------------------------------------------------------
; Reads a NUL-terminated ASCII string from program memory via TBLRD*+,
; passing each character to lcd_char_write (lcd_char_write). Caller seeds
; TBLPTR before calling. Returns when a 0x00 terminator is read.
; Used by the menu/display-loop helpers to print fixed strings (SETUP,
; VOLUME, INPUT, "Zzz...", "Waiting for DLCP", etc.).
; ===========================================================================
; lcd_string_write_rom:
lcd_string_write_rom:                                               ; address: 0x0000dc

        clrf    EECON1, A                                   ; reg: 0xfa6
        bsf     EECON1, EEPGD, A                            ; reg: 0xfa6, bit: 7

lcd_string_write_rom__read_next_char:                                                  ; address: 0x0000e0

        tblrd*+
        movf    TABLAT, W, A                                ; reg: 0xff5
        bz      lcd_string_write_rom__return_on_nul
        rcall   lcd_char_write                                ; dest: 0x0000ec
        bra     lcd_string_write_rom__read_next_char                                   ; dest: 0x0000e0

lcd_string_write_rom__return_on_nul:                                                  ; address: 0x0000ea

        return  0x0


; ===========================================================================
; lcd_char_write @ 0x0000EC — lcd_char_write
; ---------------------------------------------------------------------------
; Writes one byte to the HD44780 LCD via the 4-bit nibble interface.
;   • RS (LATA.5) selected by the BSR/W stage upstream
;   • Latches high nibble (bits 7..4) on D4..D7 = LATB.0..3,
;   • Pulses E (LATB.4) high then low (~450 ns at 16 MHz),
;   • Repeats for low nibble.
; Special-cases command bytes 0x01..0x03 (clear/home/entry-mode-set) which
; need extra settle time — uses delay_parameter_unit to hold E high a few µs longer.
; ===========================================================================
; lcd_char_write:
lcd_char_write:                                               ; address: 0x0000ec

        movwf   (Common_RAM + 21), A                        ; reg: 0x015
        bcf     LATB, LATB4, A                              ; reg: 0xf8a, bit: 4
        bcf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        bcf     TRISB, RB4, A                               ; reg: 0xf93, bit: 4
        bcf     TRISA, RA5, A                               ; reg: 0xf92, bit: 5
        movlw   0xf0
        andwf   TRISB, F, A                                 ; reg: 0xf93
        movf    (Common_RAM + 21), W, A                     ; reg: 0x015
        btfsc   Common_RAM, 0x1, A                          ; reg: 0x000
        goto    lcd_char_write__stage_byte_and_select_mode                                   ; dest: 0x000146
        movlw   0x3a
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x98
        call    delay_short_inner_spin_from_w, 0x0                           ; dest: 0x0001d8
        movlw   0x33
        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        rcall   lcd_char_write__strobe_current_nibble                                ; dest: 0x00016e
        movlw   0x13
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x88
        call    delay_short_inner_spin_from_w, 0x0                           ; dest: 0x0001d8
        rcall   lcd_char_write__strobe_current_nibble                                ; dest: 0x00016e
        movlw   0x64
        call    delay_short_inner_spin_from_w_zero_high, 0x0                           ; dest: 0x0001d6
        rcall   lcd_char_write__strobe_current_nibble                                ; dest: 0x00016e
        movlw   0x64
        call    delay_short_inner_spin_from_w_zero_high, 0x0                           ; dest: 0x0001d6
        movlw   0x22
        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        rcall   lcd_char_write__strobe_current_nibble                                ; dest: 0x00016e
        movlw   0x28
        rcall   lcd_char_write__write_command_byte                                ; dest: 0x000144
        movlw   0x0c
        rcall   lcd_char_write__write_command_byte                                ; dest: 0x000144
        movlw   0x06
        rcall   lcd_char_write__write_command_byte                                ; dest: 0x000144
        bsf     Common_RAM, 0x1, A                          ; reg: 0x000
        movf    (Common_RAM + 21), W, A                     ; reg: 0x015
        bra     lcd_char_write__stage_byte_and_select_mode                                   ; dest: 0x000146

lcd_char_write__write_command_byte:                                               ; address: 0x000144

        bsf     Common_RAM, 0x0, A                          ; reg: 0x000

lcd_char_write__stage_byte_and_select_mode:                                                  ; address: 0x000146

        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        btfss   Common_RAM, 0x0, A                          ; reg: 0x000
        bra     lcd_char_write__data_or_escape_prefix                                   ; dest: 0x000162
        bcf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        sublw   0x03
        bnc     lcd_char_write__start_nibble_strobe
        rcall   lcd_char_write__start_nibble_strobe                                ; dest: 0x00016a
        movlw   0x07
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0xd0
        call    delay_short_inner_spin_from_w, 0x0                           ; dest: 0x0001d8
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

lcd_char_write__data_or_escape_prefix:                                                  ; address: 0x000162

        bsf     Common_RAM, 0x0, A                          ; reg: 0x000
        sublw   0xfe
        bz      lcd_char_write__return_staged_byte
        bsf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5

lcd_char_write__start_nibble_strobe:                                               ; address: 0x00016a

        swapf   (Common_RAM + 20), F, A                     ; reg: 0x014
        btfss   Common_RAM, 0x0, A                          ; reg: 0x000

lcd_char_write__strobe_current_nibble:                                               ; address: 0x00016e

        bcf     Common_RAM, 0x0, A                          ; reg: 0x000
        bsf     LATB, LATB4, A                              ; reg: 0xf8a, bit: 4
        movlw   0xf0
        andwf   PORTB, F, A                                 ; reg: 0xf81
        movf    (Common_RAM + 20), W, A                     ; reg: 0x014
        andlw   0x0f
        iorwf   PORTB, F, A                                 ; reg: 0xf81
        bcf     LATB, LATB4, A                              ; reg: 0xf8a, bit: 4
        swapf   (Common_RAM + 20), F, A                     ; reg: 0x014
        btfsc   Common_RAM, 0x0, A                          ; reg: 0x000
        bra     lcd_char_write__strobe_current_nibble                                ; dest: 0x00016e
        movlw   0x32
        call    delay_short_inner_spin_from_w_zero_high, 0x0                           ; dest: 0x0001d6
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0

lcd_char_write__return_staged_byte:                                                  ; address: 0x00018c

        movf    (Common_RAM + 21), W, A                     ; reg: 0x015
        return  0x0

lcd_command_or_eeprom_read:                                               ; address: 0x000190

        btfsc   (Common_RAM + 1), 0x7, A                    ; reg: 0x001
        goto    lcd_char_write                                ; dest: 0x0000ec


; ===========================================================================
; lcd_command_or_eeprom_read @ 0x000190 — lcd_command_or_eeprom_read (shared dispatch)
; eeprom_read_byte @ 0x000196 — eeprom_read_byte (entry point shares tail)
; ---------------------------------------------------------------------------
; Dual-purpose entry block. PIC18F25K20 EEPROM uses the same EECON1 SFR
; positions as program-memory access (0xA6=EECON1, 0xA7=EECON2, 0xA8=EEDATA,
; 0xA9=EEADR), so a single read primitive serves both paths:
;
;   Entry lcd_command_or_eeprom_read (0x000190) — bit7 of 0x01 selects target:
;     bit7 SET   → goto lcd_char_write (LCD write at 0x0000EC)
;     bit7 CLEAR → fall through into the EEPROM read body at 0x000196
;
;   Entry eeprom_read_byte (0x000196) — direct EEPROM byte read:
;     EEADR (0xA9) = W, EECON1 (0xA6) cleared, EECON1.RD (0xA6.0) set,
;     return EEDATA (0xA8) in W. EEPROM read latency is one cycle on
;     PIC18F25K20 so no NOP is needed before reading EEDATA.
;
; Used by settings_load_eeprom (settings_load_eeprom) at boot, and by every later
; routine that needs to read user-saved display/config bytes from EEPROM.
; ===========================================================================
; eeprom_read_byte:
eeprom_read_byte:                                               ; address: 0x000196

        movwf   EEADR, A                                    ; reg: 0xfa9
        clrf    EECON1, A                                   ; reg: 0xfa6
        bsf     EECON1, RD, A                               ; reg: 0xfa6, bit: 0
        movf    EEDATA, W, A                                ; reg: 0xfa8
        incf    EEADR, F, A                                 ; reg: 0xfa9
        return  0x0


; ===========================================================================
; eeprom_write_byte @ 0x0001A2 — eeprom_write_byte (~3.3 ms, blocking)
; ---------------------------------------------------------------------------
; Writes W to EEPROM at address EEADR. Standard PIC18 unlock sequence:
;   • EECON1.WREN = 1
;   • EECON2 = 0x55, EECON2 = 0xAA
;   • EECON1.WR = 1
; Polls WR until completion (~3.3 ms typical). NOTE: this routine spins
; with WREN/WR set, blocking interrupts via implicit GIE behaviour during
; the unlock window. CONTROL has no WDT (BUG C8) so a stuck WR could
; hang indefinitely on faulty silicon.
; ===========================================================================
; eeprom_write_byte:
eeprom_write_byte:                                               ; address: 0x0001a2

        movwf   EEDATA, A                                   ; reg: 0xfa8
        clrf    EECON1, A                                   ; reg: 0xfa6
        bsf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        movlw   0x55
        movwf   EECON2, A                                   ; reg: 0xfa7
        movlw   0xaa
        movwf   EECON2, A                                   ; reg: 0xfa7
        bsf     EECON1, WR, A                               ; reg: 0xfa6, bit: 1

eeprom_write_byte__wait_write_complete:                                                  ; address: 0x0001b2

        btfsc   EECON1, WR, A                               ; reg: 0xfa6, bit: 1
        bra     eeprom_write_byte__wait_write_complete                                   ; dest: 0x0001b2
        bcf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        incf    EEADR, F, A                                 ; reg: 0xfa9
        return  0x0

EEPROM_PB2_INPUT_ADDR      equ     0x5F
PB2_INPUT_EEPROM_LINKED    equ     0xA0
PB2_INPUT_EEPROM_CONCRETE_BASE equ 0xB0


; ===========================================================================
; delay_short @ 0x0001BC — delay_short
; ---------------------------------------------------------------------------
; Caller stages count in W; routine spins ~200 cycles per unit (50 µs at
; 16 MHz). Common values: W=0xC8 → ~10 ms, W=0x05 → ~250 µs (post-LCD-strobe
; settle). Used everywhere a "short pause" is needed without commandeering
; Timer3.
; ===========================================================================
; delay_short:
delay_short:                                               ; address: 0x0001bc

        clrf    (Common_RAM + 15), A                        ; reg: 0x00f

delay_short_16bit_countdown_from_w:                                               ; address: 0x0001be

        movwf   (Common_RAM + 14), A                        ; reg: 0x00e

delay_short_16bit_countdown_from_w__decrement_outer:                                                  ; address: 0x0001c0

        movlw   0xff
        addwf   (Common_RAM + 14), F, A                     ; reg: 0x00e
        addwfc  (Common_RAM + 15), F, A                     ; reg: 0x00f
        bra     delay_short_16bit_countdown_from_w__run_inner_delay                                   ; dest: 0x0001c8

delay_short_16bit_countdown_from_w__run_inner_delay:                                                  ; address: 0x0001c8

        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        movlw   0x03
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0xe5
        rcall   delay_short_inner_spin_from_w                                ; dest: 0x0001d8
        bra     delay_short_16bit_countdown_from_w__decrement_outer                                   ; dest: 0x0001c0

delay_short_inner_spin_from_w_zero_high:                                               ; address: 0x0001d6

        clrf    (Common_RAM + 13), A                        ; reg: 0x00d

delay_short_inner_spin_from_w:                                               ; address: 0x0001d8

        addlw   0xfa
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        nop
        bnc     delay_short_inner_spin_from_w__finish_outer_tick
        bra     delay_short_inner_spin_from_w__borrow_loop                                   ; dest: 0x0001e2

delay_short_inner_spin_from_w__borrow_loop:                                                  ; address: 0x0001e2

        decf    (Common_RAM + 12), F, A                     ; reg: 0x00c
        bc      delay_short_inner_spin_from_w__borrow_loop

delay_short_inner_spin_from_w__finish_outer_tick:                                                  ; address: 0x0001e6

        decf    (Common_RAM + 12), F, A                     ; reg: 0x00c
        decf    (Common_RAM + 13), F, A                     ; reg: 0x00d
        bc      delay_short_inner_spin_from_w__borrow_loop
        nop
        return  0x0

delay_parameter_unit__divide_u16_scratch:                                               ; address: 0x0001f0

        clrf    (Common_RAM + 17), A                        ; reg: 0x011
        clrf    (Common_RAM + 16), A                        ; reg: 0x010
        movlw   0x10
        movwf   PRODL, A                                    ; reg: 0xff3

delay_parameter_unit__divide_u16_scratch_loop:                                                  ; address: 0x0001f8

        rlcf    (Common_RAM + 13), W, A                     ; reg: 0x00d
        rlcf    (Common_RAM + 16), F, A                     ; reg: 0x010
        rlcf    (Common_RAM + 17), F, A                     ; reg: 0x011
        movf    (Common_RAM + 14), W, A                     ; reg: 0x00e
        subwf   (Common_RAM + 16), W, A                     ; reg: 0x010
        movf    (Common_RAM + 15), W, A                     ; reg: 0x00f
        subwfb  (Common_RAM + 17), W, A                     ; reg: 0x011
        bnc     delay_parameter_unit__divide_u16_scratch_shift_quotient
        movf    (Common_RAM + 14), W, A                     ; reg: 0x00e
        subwf   (Common_RAM + 16), F, A                     ; reg: 0x010
        movf    (Common_RAM + 15), W, A                     ; reg: 0x00f
        subwfb  (Common_RAM + 17), F, A                     ; reg: 0x011
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0

delay_parameter_unit__divide_u16_scratch_shift_quotient:                                                  ; address: 0x000212

        rlcf    (Common_RAM + 12), F, A                     ; reg: 0x00c
        rlcf    (Common_RAM + 13), F, A                     ; reg: 0x00d
        decfsz  PRODL, F, A                                 ; reg: 0xff3
        bra     delay_parameter_unit__divide_u16_scratch_loop                                   ; dest: 0x0001f8
        movf    (Common_RAM + 12), W, A                     ; reg: 0x00c
        return  0x0


; ===========================================================================
; ir_rc5_decode @ 0x00021E — ir_rc5_decode    *** BUG C3 ***
; ---------------------------------------------------------------------------
; RC5 IR remote decoder. Polls RB5 (LATB.5 readback at 0x81.5) collecting
; 16 bits via a tight bit-bang loop. Stores decoded address into 0x01E
; (ir_decoded_addr) and command into 0x01D (ir_decoded_cmd), then sets
; 0x01F.bit0 (ir_armed) so the main event loop dispatches the IR command.
;
; *** BUG C3 (ir_decode_blocks_isr_10ms) ***
; This routine is INVOKED FROM THE ISR (isr_entry at 0x0003A6 jumps to
; 0x000264 which calls here). The polling loop runs ~28,160 cycles, i.e.
; ~7-10 ms with the BSF 0x93,5 at entry KEEPING THE OTHER ISR SOURCES
; MASKED. During that window:
;   • UART RX FIFO can fill (RCREG is 2 deep) — third byte → OERR.
;   • Button RBIF events are missed.
;   • TXIE-driven outgoing frames stall (standby_wake_broadcast standby/wake frame
;     can be delayed by ~10 ms per IR press).
; Stock/V1.6b exposed BUG C4 here because rx_parser_entry only toggled
; CREN and left stale bytes in the hardware FIFO.  V1.72 keeps the
; stock-compatible ISR decode path but hardens rx_parser_entry with the
; V1.62b full FIFO drain plus parser/ring reset, so IR-induced OERR
; pressure recovers cleanly instead of phase-shifting the next frame.
; ===========================================================================
; ir_rc5_decode:
ir_rc5_decode:                                               ; address: 0x00021e

        bsf     TRISB, RB5, A                               ; reg: 0xf93, bit: 5
        clrf    (Common_RAM + 21), A                        ; reg: 0x015
        clrf    (Common_RAM + 20), A                        ; reg: 0x014
        lfsr    0x0, stock_010_b0_phys
        movlw   0x01
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0xba
        call    delay_short_inner_spin_from_w, 0x0                           ; dest: 0x0001d8
        btfsc   PORTB, RB5, A                               ; reg: 0xf81, bit: 5
        bra     ir_rc5_decode__fail_invalid_frame                                   ; dest: 0x0002e4

ir_rc5_decode__capture_sample_loop:                                                  ; address: 0x000236

        movlw   0x03
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x76
        call    delay_short_inner_spin_from_w, 0x0                           ; dest: 0x0001d8
        incf    (Common_RAM + 21), F, A                     ; reg: 0x015
        movlw   0x20                                        ; RC5 0x20 preset next
        cpfsgt  (Common_RAM + 21), A                        ; reg: 0x015
        bra     ir_rc5_decode__shift_port_sample_into_buffer                                   ; dest: 0x00024a
        bra     ir_rc5_decode__begin_frame_decode                                   ; dest: 0x00025e

ir_rc5_decode__shift_port_sample_into_buffer:                                                  ; address: 0x00024a

        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        btfsc   PORTB, RB5, A                               ; reg: 0xf81, bit: 5
        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        incf    (Common_RAM + 20), F, A                     ; reg: 0x014
        btfss   (Common_RAM + 20), 0x3, A                   ; reg: 0x014
        bra     ir_rc5_decode__continue_capture_loop                                   ; dest: 0x00025c
        movf    POSTINC0, F, A                              ; reg: 0xfee
        clrf    (Common_RAM + 20), A                        ; reg: 0x014

ir_rc5_decode__continue_capture_loop:                                                  ; address: 0x00025c

        bra     ir_rc5_decode__capture_sample_loop                                   ; dest: 0x000236

ir_rc5_decode__begin_frame_decode:                                                  ; address: 0x00025e

        lfsr    0x0, stock_010_b0_phys
        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        clrf    (Common_RAM + 20), A                        ; reg: 0x014
        clrf    (Common_RAM + 14), A                        ; reg: 0x00e
        clrf    (Common_RAM + 13), A                        ; reg: 0x00d
        clrf    (Common_RAM + 12), A                        ; reg: 0x00c
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        incf    (Common_RAM + 20), F, A                     ; reg: 0x014
        rcall   ir_rc5_decode_pair_to_flags                                ; dest: 0x0002ee
        btfsc   (Common_RAM + 9), 0x2, A                    ; reg: 0x009
        bra     ir_rc5_decode__fail_invalid_frame                                   ; dest: 0x0002e4
        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        incf    (Common_RAM + 20), F, A                     ; reg: 0x014
        rcall   ir_rc5_decode_pair_to_flags                                ; dest: 0x0002ee
        btfsc   (Common_RAM + 9), 0x2, A                    ; reg: 0x009
        bra     ir_rc5_decode__fail_invalid_frame                                   ; dest: 0x0002e4
        rrcf    (Common_RAM + 9), F, A                      ; reg: 0x009
        rlcf    (Common_RAM + 14), F, A                     ; reg: 0x00e
        movlw   0x05
        movwf   (Common_RAM + 8), A                         ; reg: 0x008

ir_rc5_decode__address_bit_loop:                                                  ; address: 0x000296

        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        incf    (Common_RAM + 20), F, A                     ; reg: 0x014
        btfss   (Common_RAM + 20), 0x2, A                   ; reg: 0x014
        bra     ir_rc5_decode__accumulate_address_bit                                   ; dest: 0x0002aa
        movf    POSTINC0, F, A                              ; reg: 0xfee
        clrf    (Common_RAM + 20), A                        ; reg: 0x014

ir_rc5_decode__accumulate_address_bit:                                                  ; address: 0x0002aa

        rcall   ir_rc5_decode_pair_to_flags                                ; dest: 0x0002ee
        btfsc   (Common_RAM + 9), 0x2, A                    ; reg: 0x009
        bra     ir_rc5_decode__fail_invalid_frame                                   ; dest: 0x0002e4
        rrcf    (Common_RAM + 9), F, A                      ; reg: 0x009
        rlcf    (Common_RAM + 13), F, A                     ; reg: 0x00d
        decfsz  (Common_RAM + 8), F, A                      ; reg: 0x008
        bra     ir_rc5_decode__address_bit_loop                                   ; dest: 0x000296
        movlw   0x06
        movwf   (Common_RAM + 8), A                         ; reg: 0x008

ir_rc5_decode__command_bit_loop:                                                  ; address: 0x0002bc

        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        incf    (Common_RAM + 20), F, A                     ; reg: 0x014
        btfss   (Common_RAM + 20), 0x2, A                   ; reg: 0x014
        bra     ir_rc5_decode__accumulate_command_bit_or_return                                   ; dest: 0x0002d0
        movf    POSTINC0, F, A                              ; reg: 0xfee
        clrf    (Common_RAM + 20), A                        ; reg: 0x014

ir_rc5_decode__accumulate_command_bit_or_return:                                                  ; address: 0x0002d0

        rcall   ir_rc5_decode_pair_to_flags                                ; dest: 0x0002ee
        btfsc   (Common_RAM + 9), 0x2, A                    ; reg: 0x009
        bra     ir_rc5_decode__fail_invalid_frame                                   ; dest: 0x0002e4
        rrcf    (Common_RAM + 9), F, A                      ; reg: 0x009
        rlcf    (Common_RAM + 12), F, A                     ; reg: 0x00c
        decfsz  (Common_RAM + 8), F, A                      ; reg: 0x008
        bra     ir_rc5_decode__command_bit_loop                                   ; dest: 0x0002bc
        movf    (Common_RAM + 12), W, A                     ; reg: 0x00c
        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

ir_rc5_decode__fail_invalid_frame:                                                  ; address: 0x0002e4

        movlw   0xff
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

ir_rc5_decode_pair_to_flags:                                               ; address: 0x0002ee

        clrf    (Common_RAM + 9), A                         ; reg: 0x009
        decfsz  (Common_RAM + 5), W, A                      ; reg: 0x005
        bra     ir_rc5_decode_pair_to_flags__check_zero_pair                                   ; dest: 0x0002f8
        bsf     (Common_RAM + 9), 0x0, A                    ; reg: 0x009
        return  0x0

ir_rc5_decode_pair_to_flags__check_zero_pair:                                                  ; address: 0x0002f8

        movlw   0x02
        cpfseq  (Common_RAM + 5), A                         ; reg: 0x005
        bra     ir_rc5_decode_pair_to_flags__mark_invalid_pair                                   ; dest: 0x000300
        return  0x0

ir_rc5_decode_pair_to_flags__mark_invalid_pair:                                                  ; address: 0x000300

        bsf     (Common_RAM + 9), 0x2, A                    ; reg: 0x009
        return  0x0

lcd_str_firmware_v:                                                  ; address: 0x000304  (tblptr anchor)
        setf    (Common_RAM + 70), B                        ; reg: 0x046
        negf    0x72, B                                     ; reg: 0x072
        cpfslt  0x77, B                                     ; reg: 0x077
        cpfsgt  0x72, B                                     ; reg: 0x072
        subfwb  (Common_RAM + 32), F, A                     ; reg: 0x020
        nop
lcd_str_waiting_for_dlcp:                                                  ; address: 0x000310  (tblptr anchor)
        cpfslt  (Common_RAM + 87), B                        ; reg: 0x057
        btg     0x69, 0x2, A                                ; reg: 0xf69
        movwf   0x69, A                                     ; reg: 0xf69
        addwfc  0x67, W, A                                  ; reg: 0xf67
        movwf   rx_ring_base_b0, B                                     ; reg: 0x066
        addwfc  0x72, W, A                                  ; reg: 0xf72
        dcfsnz  (Common_RAM + 68), W, A                     ; reg: 0x044
        movf    (Common_RAM + 67), W, A                     ; reg: 0x043
        nop
lcd_str_standby_zzz:                                                  ; address: 0x000322  (tblptr anchor)
        btg     (Common_RAM + 90), 0x5, A                   ; reg: 0x05a
        decfsz  CM2CON0, F, A                               ; reg: 0xf7a
        decfsz  (Common_RAM + 46), F, A                     ; reg: 0x02e
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        nop
lcd_str_waiting_for_dlcp_alt:                                                  ; address: 0x000334  (tblptr anchor)
        cpfslt  (Common_RAM + 87), B                        ; reg: 0x057
        btg     0x69, 0x2, A                                ; reg: 0xf69
        movwf   0x69, A                                     ; reg: 0xf69
        addwfc  0x67, W, A                                  ; reg: 0xf67
        movwf   rx_ring_base_b0, B                                     ; reg: 0x066
        addwfc  0x72, W, A                                  ; reg: 0xf72
        dcfsnz  (Common_RAM + 68), W, A                     ; reg: 0x044
        movf    (Common_RAM + 67), W, A                     ; reg: 0x043
        nop
lcd_str_db_suffix:                                                  ; address: 0x000346  (tblptr anchor)
        rrncf   0x64, F, A                                  ; reg: 0xf64
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        dw      0x0020                                      ; ' '
lcd_str_mute:                                                  ; address: 0x000354  (tblptr anchor)
        btg     (Common_RAM + 77), 0x2, B                   ; reg: 0x04d
        cpfsgt  0x74, B                                     ; reg: 0x074
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        nop

app_cold_init:                                                  ; address: 0x000366

        clrf    TBLPTRU, A                                  ; reg: 0xff8
        clrf    Common_RAM, A                               ; reg: 0x000
        clrf    RCSTA, A                                    ; reg: 0xfab
        movlb   0x0
        movlw   0xdf                                        ; TRISA: RA1..RA4 input (buttons), RA5 output (LCD RS)
        movwf   TRISA, A                                    ; reg: 0xf92
        movlw   0x3c                                        ; TRISB: RB0..RB3 output (LCD D4..D7 muxed), RB2/RB3 inputs, RB4 E strobe
        movwf   TRISB, A                                    ; reg: 0xf93
        movlw   0xbd                                        ; TRISC: RC6 TX, RC7 RX, RC1 output (LED), RC0/RC5 inputs (buttons)
        movwf   TRISC, A                                    ; reg: 0xf94
        clrf    CM1CON0, A                                  ; reg: 0xf7b
        clrf    CM2CON0, A                                  ; reg: 0xf7a
        clrf    ANSEL, A                                    ; reg: 0xf7e
        clrf    ANSELH, A                                   ; reg: 0xf7f
        movlw   0x0f                                        ; ADCON1: all PORTA digital (vendor init)
        movwf   ADCON1, A                                   ; reg: 0xfc1
        bcf     IOCB, IOCB7, A                              ; reg: 0xf7d, bit: 7
        bcf     IOCB, IOCB6, A                              ; reg: 0xf7d, bit: 6
        bcf     IOCB, IOCB4, A                              ; reg: 0xf7d, bit: 4
        movlw   0x05                                        ; SPBRG: 31250 baud @ 4MIPS (BRG16=0 BRGH=0 → SPBRG=5)
        movwf   SPBRG, A                                    ; reg: 0xfaf
        bcf     TXSTA, BRGH, A                              ; reg: 0xfac, bit: 2
        bcf     BAUDCON, BRG16, A                           ; reg: 0xfb8, bit: 3
        bcf     TXSTA, SYNC, A                              ; reg: 0xfac, bit: 4
        bsf     RCSTA, SPEN, A                              ; reg: 0xfab, bit: 7
        bcf     RCON, IPEN, A                               ; reg: 0xfd0, bit: 7
        bcf     PIE1, TXIE, A                               ; reg: 0xf9d, bit: 4
        bcf     PIE1, RCIE, A                               ; reg: 0xf9d, bit: 5
        bsf     TXSTA, TXEN, A                              ; reg: 0xfac, bit: 5
        bsf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        goto    app_cold_init__clear_diag_health_and_filename_state                                   ; dest: 0x00103c

isr_entry:                                                  ; address: 0x0003a6

        movff   STATUS, (Common_RAM + 25)                   ; reg1: 0xfd8, reg2: 0x019
        movwf   (Common_RAM + 26), A                        ; reg: 0x01a
        movff   BSR, (Common_RAM + 2)                       ; reg1: 0xfe0, reg2: 0x002
        movff   FSR0L, (Common_RAM + 3)                     ; reg1: 0xfe9, reg2: 0x003
        movff   FSR0H, (Common_RAM + 4)                     ; reg1: 0xfea, reg2: 0x004
        movlb   0x0
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   PIE1, TXIE, A                               ; reg: 0xf9d, bit: 4
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   PIR1, TXIF, A                               ; reg: 0xf9e, bit: 4
        movlw   0x01
        andwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    isr_entry__receive_uart_byte_if_ready                                   ; dest: 0x0003f6
        movf    tx_ring_rd_b0, W, B                                  ; reg: 0x096
        cpfseq  tx_ring_wr_b0, B                                     ; reg: 0x097
        goto    isr_entry__tx_ring_send_next_byte                                   ; dest: 0x0003de
        bcf     PIE1, TXIE, A                               ; reg: 0xf9d, bit: 4
        goto    isr_entry__receive_uart_byte_if_ready                                   ; dest: 0x0003f6

isr_entry__tx_ring_send_next_byte:                                                  ; address: 0x0003de

        lfsr    0x0, tx_ring_base_b0_phys
        movf    tx_ring_rd_b0, W, B                                  ; reg: 0x096
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   TXREG, A                                    ; reg: 0xfad
        incf    tx_ring_rd_b0, F, B                                  ; reg: 0x096
        movlw   0x30
        subwf   tx_ring_rd_b0, W, B                                  ; reg: 0x096
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    isr_entry__receive_uart_byte_if_ready                                   ; dest: 0x0003f6
        clrf    tx_ring_rd_b0, B                                     ; reg: 0x096

isr_entry__receive_uart_byte_if_ready:                                                  ; address: 0x0003f6

        btfss   PIR1, RCIF, A                               ; reg: 0xf9e, bit: 5
        goto    isr_entry__service_portb_change_if_ready
        lfsr    0x0, rx_ring_base_b0_phys
        movf    rx_ring_wr_b0, W, B                                  ; reg: 0x099
        movff   RCREG, PLUSW0                               ; reg1: 0xfae, reg2: 0xfeb
        incf    rx_ring_wr_b0, F, B                                  ; reg: 0x099
        movlw   0x30
        subwf   rx_ring_wr_b0, W, B                                  ; reg: 0x099
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    isr_entry__rollback_rx_write_on_full_ring                                   ; dest: 0x00040c
        clrf    rx_ring_wr_b0, B                                     ; reg: 0x099

isr_entry__rollback_rx_write_on_full_ring:                                                  ; address: 0x00040c

        ; V1.72 hardening: consume RCREG immediately, but roll back the
        ; software write pointer if this byte would overwrite unread data.
        movf    rx_ring_wr_b0, W, B                                  ; reg: 0x099
        cpfseq  rx_ring_rd_b0, B                                     ; reg: 0x098
        goto    isr_entry__service_portb_change_if_ready
        decf    rx_ring_wr_b0, F, B                                  ; reg: 0x099
        movlw   0xff
        cpfseq  rx_ring_wr_b0, B                                     ; reg: 0x099
        goto    isr_entry__service_portb_change_if_ready
        movlw   0x2f
        movwf   rx_ring_wr_b0, B                                     ; reg: 0x099

isr_entry__service_portb_change_if_ready:                                                  ; address: 0x000414

        btfss   INTCON, RBIF, A                             ; reg: 0xff2, bit: 0
        goto    isr_entry__restore_context_and_retfie                                   ; dest: 0x000436
        movf    (Common_RAM + 28), W, A                     ; reg: 0x01c
        iorwf   (Common_RAM + 27), W, A                     ; reg: 0x01b
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    isr_entry__clear_portb_change_flag                                   ; dest: 0x000434
        btfss   control_flags_acc, 0x0, A                   ; reg: 0x01f
        goto    isr_entry__clear_portb_change_flag                                   ; dest: 0x000434
        ; V1.72 hardware fallback (2026-05-09): use the stock V1.6b
        ; in-ISR RC5 decoder.  The failed Timer1 sampler was removed so
        ; there is no dormant path that can arm TMR1IE without a handler.
        ;
        ; V1.73 ISR-scratch preservation (task #7): the blocking decode
        ; (~7-10 ms) clobbers access-bank scratch shared with the
        ; foreground LCD/delay helpers (0x005, 0x008, 0x00C..0x00E,
        ; 0x010..0x013 sample buffer, 0x014/0x015).  A frame arriving
        ; mid-LCD-sequence used to corrupt the interrupted draw (cursor /
        ; delay-count garbage -- the historic LCD glitch class), which
        ; V1.71 papered over by GIE-masking ITS new LCD patch at the cost
        ; of dropping IR frames inside the mask.  Save the full set before
        ; the decode and restore it after the result stores: the decode
        ; logic itself is untouched (BUG-IR-01 hardware-validated path).
        movff   (Common_RAM + 5),  v173_isr_decode_save_b2_phys + 0
        movff   (Common_RAM + 8),  v173_isr_decode_save_b2_phys + 1
        movff   (Common_RAM + 12), v173_isr_decode_save_b2_phys + 2
        movff   (Common_RAM + 13), v173_isr_decode_save_b2_phys + 3
        movff   (Common_RAM + 14), v173_isr_decode_save_b2_phys + 4
        movff   (Common_RAM + 16), v173_isr_decode_save_b2_phys + 5
        movff   (Common_RAM + 17), v173_isr_decode_save_b2_phys + 6
        movff   (Common_RAM + 18), v173_isr_decode_save_b2_phys + 7
        movff   (Common_RAM + 19), v173_isr_decode_save_b2_phys + 8
        movff   (Common_RAM + 20), v173_isr_decode_save_b2_phys + 9
        movff   (Common_RAM + 21), v173_isr_decode_save_b2_phys + 10
        rcall   ir_rc5_decode                                ; dest: 0x00021e
        movwf   ir_decoded_cmd_acc, A                        ; reg: 0x01d
        movff   (Common_RAM + 13), ir_decoded_addr        ; reg1: 0x00d, reg2: 0x01e
        movff   v173_isr_decode_save_b2_phys + 0,  (Common_RAM + 5)
        movff   v173_isr_decode_save_b2_phys + 1,  (Common_RAM + 8)
        movff   v173_isr_decode_save_b2_phys + 2,  (Common_RAM + 12)
        movff   v173_isr_decode_save_b2_phys + 3,  (Common_RAM + 13)
        movff   v173_isr_decode_save_b2_phys + 4,  (Common_RAM + 14)
        movff   v173_isr_decode_save_b2_phys + 5,  (Common_RAM + 16)
        movff   v173_isr_decode_save_b2_phys + 6,  (Common_RAM + 17)
        movff   v173_isr_decode_save_b2_phys + 7,  (Common_RAM + 18)
        movff   v173_isr_decode_save_b2_phys + 8,  (Common_RAM + 19)
        movff   v173_isr_decode_save_b2_phys + 9,  (Common_RAM + 20)
        movff   v173_isr_decode_save_b2_phys + 10, (Common_RAM + 21)
        bcf     control_flags_acc, 0x0, A                   ; reg: 0x01f

isr_entry__clear_portb_change_flag:                                                  ; address: 0x000434

        bcf     INTCON, RBIF, A                             ; reg: 0xff2, bit: 0

isr_entry__restore_context_and_retfie:                                                  ; address: 0x000436

        movff   (Common_RAM + 3), FSR0L                     ; reg1: 0x003, reg2: 0xfe9
        movff   (Common_RAM + 4), FSR0H                     ; reg1: 0x004, reg2: 0xfea
        movff   (Common_RAM + 2), BSR                       ; reg1: 0x002, reg2: 0xfe0
        movf    (Common_RAM + 26), W, A                     ; reg: 0x01a
        movff   (Common_RAM + 25), STATUS                   ; reg1: 0x019, reg2: 0xfd8
        retfie  0x0


; ===========================================================================
; rx_parser_entry @ 0x00044A — rx_parser_entry  (V1.72 hardened)
; ---------------------------------------------------------------------------
; Top of the receive-path service routine. Called every iteration of the
; main event loop (main_event_loop) to drain the RX ring, decode 3-byte
; [route, cmd, data] frames, and update internal state.
;
; Retired BUG C4 (oerr_no_fifo_drain): the first branch now performs the
; V1.62b full soft-recover inline: CREN off, read RCREG twice, CREN on,
; then clear the TX/RX ring indexes and parser phase latches.  This keeps
; a UART overrun from leaving stale FIFO bytes for the next frame.
;
; Retired BUG C5 (no_frame_resync_timeout): foreground loops call
; v171_service_rx_frame_gap after rx_parser_entry.  That helper reloads
; on parser progress and clears rx_frame_position if a partial frame stalls.
; ===========================================================================
; rx_parser_entry:
rx_parser_entry:                                               ; address: 0x00044a

        movlb   0x00                                        ; RX ring/parser BANKED state lives in bank 0
        btfss   RCSTA, OERR, A                              ; reg: 0xfab, bit: 1
        goto    rx_parser_entry__after_oerr_recovery                                   ; dest: 0x000456
        ; ---------------------------------------------------------------
        ; V1.72 inline (V1.62b): full UART soft-recover on OERR
        ; ---------------------------------------------------------------
        ; Stock V1.6b only toggles CREN to clear the OERR latch, which
        ; leaves RCREG partially loaded and the parser state-machine
        ; mid-frame — the cascading symptom of BUG C4 (oerr_no_fifo_drain)
        ; documented in v16b.asm.  V1.62b does a full soft-recover:
        ; drain RCREG twice, re-enable CREN, then reset the TX/RX ring
        ; pointers and the parser's cmd/data/position latches so the
        ; next byte starts a clean frame.  Inline here so the head of
        ; the parser always runs the V1.62b recovery and never the
        ; stock single-toggle.
        bcf     RCSTA, CREN, A
        movf    RCREG, W, A                                 ; drain byte 1
        movf    RCREG, W, A                                 ; drain byte 2 (EUSART FIFO depth 2)
        bsf     RCSTA, CREN, A
        movlb   0x00
        clrf    tx_ring_rd_b0, BANKED                          ; 0x096
        clrf    tx_ring_wr_b0, BANKED                          ; 0x097
        clrf    rx_ring_rd_b0, BANKED                          ; 0x098
        clrf    rx_ring_wr_b0, BANKED                          ; 0x099
        clrf    rx_frame_position_b0, BANKED                   ; 0x0A6
        clrf    rx_parsed_cmd_acc, A                            ; 0x02F
        clrf    rx_parsed_data_acc, A                           ; 0x030

rx_parser_entry__after_oerr_recovery:                                                  ; address: 0x000456

        movf    rx_ring_wr_b0, W, B                                  ; reg: 0x099
        cpfseq  rx_ring_rd_b0, B                                     ; reg: 0x098
        goto    rx_parser_entry__read_next_ring_byte                                   ; dest: 0x000460
        return  0x0

rx_parser_entry__read_next_ring_byte:                                                  ; address: 0x000460

        lfsr    0x0, rx_ring_base_b0_phys
        movf    rx_ring_rd_b0, W, B                                  ; reg: 0x098
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   rx_parser_current_byte_b0, B                                     ; reg: 0x0b6
        incf    rx_ring_rd_b0, F, B                                  ; reg: 0x098
        movlw   0x30
        subwf   rx_ring_rd_b0, W, B                                  ; reg: 0x098
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    rx_parser_entry__echo_fe_byte                                   ; dest: 0x000478
        clrf    rx_ring_rd_b0, B                                     ; reg: 0x098

rx_parser_entry__echo_fe_byte:                                                  ; address: 0x000478

        movlw   0xfe
        cpfseq  rx_parser_current_byte_b0, B                                     ; reg: 0x0b6
        goto    rx_parser_entry__classify_route_or_payload                                   ; dest: 0x00048a
        movff   0x0b6, tx_data_staging_b0_phys                    ; reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        bra     rx_parser_entry                                ; dest: 0x00044a

rx_parser_entry__classify_route_or_payload:                                                  ; address: 0x00048a

        movlw   0x80
        subwf   rx_parser_current_byte_b0, W, B                                  ; reg: 0x0b6
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    rx_parser_entry__payload_phase_gate                                   ; dest: 0x0004d6
        movlw   0xf1
        andwf   rx_parser_current_byte_b0, W, B                                  ; reg: 0x0b6
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        clrf    (Common_RAM + 11), A                        ; reg: 0x00b
        movf    (Common_RAM + 10), W, A                     ; reg: 0x00a
        xorlw   0xb1                                        ; ROUTE addressed MAIN#1
        iorwf   (Common_RAM + 11), W, A                     ; reg: 0x00b
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    rx_parser_entry__check_broadcast_route                                   ; dest: 0x0004ac
        movlw   0xb1                                        ; ROUTE addressed MAIN#1
        movwf   rx_parser_current_byte_b0, B                                     ; reg: 0x0b6

rx_parser_entry__check_broadcast_route:                                                  ; address: 0x0004ac

        movlw   0xb0                                        ; ROUTE broadcast CONTROL→MAIN
        cpfseq  rx_parser_current_byte_b0, B                                     ; reg: 0x0b6
        goto    rx_parser_entry__check_addressed_main1_route                                   ; dest: 0x0004be
        movlw   0x01
        movwf   rx_frame_position_b0, B                                     ; reg: 0x0a6
        bsf     control_flags_acc, 0x2, A                   ; reg: 0x01f
        goto    rx_parser_entry__restart_after_route_byte                                   ; dest: 0x0004d4

rx_parser_entry__check_addressed_main1_route:                                                  ; address: 0x0004be

        movlw   0xb1                                        ; ROUTE addressed MAIN#1
        cpfseq  rx_parser_current_byte_b0, B                                     ; reg: 0x0b6
        goto    rx_parser_entry__reject_unsupported_route                                   ; dest: 0x0004d0
        movlw   0x01
        movwf   rx_frame_position_b0, B                                     ; reg: 0x0a6
        bsf     control_flags_acc, 0x2, A                   ; reg: 0x01f
        goto    rx_parser_entry__restart_after_route_byte                                   ; dest: 0x0004d4

rx_parser_entry__reject_unsupported_route:                                                  ; address: 0x0004d0

        clrf    rx_frame_position_b0, B                                     ; reg: 0x0a6
        bcf     control_flags_acc, 0x2, A                   ; unsupported route: no fresh frame

rx_parser_entry__restart_after_route_byte:                                                  ; address: 0x0004d4

        bra     rx_parser_entry                                ; dest: 0x00044a

rx_parser_entry__payload_phase_gate:                                                  ; address: 0x0004d6

        movf    rx_frame_position_b0, F, B                                  ; reg: 0x0a6
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    rx_parser_entry__payload_ready_gate                                   ; dest: 0x0004e0
        incf    rx_frame_position_b0, F, B                                  ; reg: 0x0a6

rx_parser_entry__payload_ready_gate:                                                  ; address: 0x0004e0

        movlw   0x02
        cpfslt  rx_frame_position_b0, B                                     ; reg: 0x0a6
        goto    rx_parser_entry__capture_cmd_or_dispatch_data                                   ; dest: 0x0004ea
        bra     rx_parser_entry                                ; dest: 0x00044a

rx_parser_entry__capture_cmd_or_dispatch_data:                                                  ; address: 0x0004ea

        movlw   0x02
        cpfseq  rx_frame_position_b0, B                                     ; reg: 0x0a6
        goto    rx_parser_entry__capture_data_and_dispatch                                   ; dest: 0x0004f8
        movff   0x0b6, rx_parsed_cmd_b0_phys                    ; reg2: 0x02f
        bra     rx_parser_entry                                ; dest: 0x00044a

rx_parser_entry__capture_data_and_dispatch:                                                  ; address: 0x0004f8

        movff   0x0b6, rx_parsed_data_b0_phys                    ; reg2: 0x030
        movlw   0x01
        movwf   rx_frame_position_b0, B                                     ; reg: 0x0a6
        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        cpfseq  rx_parsed_cmd_acc, A                        ; reg: 0x02f
        goto    rx_parser_entry__check_status_poll_cmd                                   ; dest: 0x000556
        decfsz  rx_parsed_data_acc, W, A                     ; reg: 0x030
        goto    rx_parser_entry__cmd03_check_standby_data                                   ; dest: 0x000514
        bsf     control_flags_acc, 0x1, A                   ; reg: 0x01f
        bsf     v173_reconnect_fresh_status_mask_b0, 1, B   ; BUG-2: fresh wake echo this attempt
        goto    rx_parser_entry__cmd03_done                                   ; dest: 0x000552

rx_parser_entry__cmd03_check_standby_data:                                                  ; address: 0x000514

        movf    rx_parsed_data_acc, F, A                     ; reg: 0x030
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    rx_parser_entry__cmd03_check_mute_on_data                                   ; dest: 0x000522
        bcf     control_flags_acc, 0x1, A                   ; reg: 0x01f
        goto    rx_parser_entry__cmd03_done                                   ; dest: 0x000552

rx_parser_entry__cmd03_check_mute_on_data:                                                  ; address: 0x000522

        movlw   0x02
        cpfseq  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    rx_parser_entry__cmd03_check_mute_off_data                                   ; dest: 0x000540
        btfsc   control_flags_acc, 0x5, A                   ; reg: 0x01f
        goto    rx_parser_entry__cmd03_mute_on_done                                   ; dest: 0x00053c
        movlw   0x2f
        movwf   mute_blink_counter_lo_b0, B                                     ; reg: 0x0b4
        movlw   0x75
        movwf   mute_blink_counter_hi_b0, B                                     ; reg: 0x0b5
        bsf     control_flags_acc, 0x5, A                   ; reg: 0x01f
        bsf     control_flags_acc, 0x3, A                   ; reg: 0x01f

rx_parser_entry__cmd03_mute_on_done:                                                  ; address: 0x00053c

        goto    rx_parser_entry__cmd03_done                                   ; dest: 0x000552

rx_parser_entry__cmd03_check_mute_off_data:                                                  ; address: 0x000540

        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        cpfseq  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    rx_parser_entry__cmd03_done                                   ; dest: 0x000552
        btfss   control_flags_acc, 0x5, A                   ; reg: 0x01f
        goto    rx_parser_entry__cmd03_done                                   ; dest: 0x000552
        bcf     control_flags_acc, 0x5, A                   ; reg: 0x01f
        bsf     control_flags_acc, 0x3, A                   ; reg: 0x01f

rx_parser_entry__cmd03_done:                                                  ; address: 0x000552

        goto    rx_parser_entry__restart_after_frame                                   ; dest: 0x0005ea

rx_parser_entry__check_status_poll_cmd:                                                  ; address: 0x000556

        movlw   0x04                                        ; CMD status_poll
        cpfseq  rx_parsed_cmd_acc, A                        ; reg: 0x02f
        goto    rx_parser_entry__check_raw_status_cmd                                   ; dest: 0x000562
        goto    rx_parser_entry__restart_after_frame                                   ; dest: 0x0005ea

rx_parser_entry__check_raw_status_cmd:                                                  ; address: 0x000562

        movlw   0x05                                        ; CMD raw_status (MAIN→CONTROL echo)
        cpfseq  rx_parsed_cmd_acc, A                        ; reg: 0x02f
        goto    rx_parser_entry__check_input_select_cmd                                   ; dest: 0x00057a
        movlw   0x04                                        ; CMD status_poll
        cpfslt  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    rx_parser_entry__raw_status_done                                   ; dest: 0x000576
        movff   rx_parsed_data_b0_phys, 0x0a1                    ; reg1: 0x030
        bsf     v173_reconnect_fresh_status_mask_b0, 0, B   ; BUG-2: fresh status-poll answer

rx_parser_entry__raw_status_done:                                                  ; address: 0x000576

        goto    rx_parser_entry__restart_after_frame                                   ; dest: 0x0005ea

rx_parser_entry__check_input_select_cmd:                                                  ; address: 0x00057a

        movlw   0x06                                        ; CMD input_select
        cpfseq  rx_parsed_cmd_acc, A                        ; reg: 0x02f
        goto    rx_parser_entry__check_volume_cmd                                   ; dest: 0x0005ac
        movlw   0x01
        subwf   (Common_RAM + 50), W, A                     ; reg: 0x032
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    rx_parser_entry__input_select_done                                   ; dest: 0x0005a8
        movlw   0x09
        cpfslt  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    rx_parser_entry__input_select_done                                   ; dest: 0x0005a8
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     rx_parser_entry__input_select_accept_legacy
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        bra     rx_parser_entry__input_select_quarantined_split
rx_parser_entry__input_select_accept_legacy:
        movlb   0x00
        movf    input_select_cache_b0, W, B                                  ; reg: 0x0b8
        subwf   rx_parsed_data_acc, W, A                     ; reg: 0x030
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    rx_parser_entry__input_select_done                                   ; dest: 0x0005a8
        movff   rx_parsed_data_b0_phys, 0x0b8                    ; reg1: 0x030
        bsf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        call    map_cmd06_input_select_to_menu_index, 0x0                           ; dest: 0x00061c
        bra     rx_parser_entry__input_select_done

rx_parser_entry__input_select_quarantined_split:
        movlb   0x00

rx_parser_entry__input_select_done:                                                  ; address: 0x0005a8

        goto    rx_parser_entry__restart_after_frame                                   ; dest: 0x0005ea

rx_parser_entry__check_volume_cmd:                                                  ; address: 0x0005ac

        movlw   0x07                                        ; CMD volume (offset 0x60)
        cpfseq  rx_parsed_cmd_acc, A                        ; reg: 0x02f
        goto    rx_parser_entry__check_cmd1d_setting_cmd                                   ; dest: 0x0005d0
        movlw   0x73
        cpfslt  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    rx_parser_entry__volume_done                                   ; dest: 0x0005cc
        movf    volume_cache_b0, W, B                                  ; reg: 0x0b9
        subwf   rx_parsed_data_acc, W, A                     ; reg: 0x030
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    rx_parser_entry__store_volume_cache                                   ; dest: 0x0005c8
        bsf     control_flags_acc, 0x3, A                   ; reg: 0x01f

rx_parser_entry__store_volume_cache:                                                  ; address: 0x0005c8

        movff   rx_parsed_data_b0_phys, 0x0b9                    ; reg1: 0x030

rx_parser_entry__volume_done:                                                  ; address: 0x0005cc

        goto    rx_parser_entry__restart_after_frame                                   ; dest: 0x0005ea

rx_parser_entry__check_cmd1d_setting_cmd:                                                  ; address: 0x0005d0

        movlw   0x1d                                        ; CMD shared_cmd1d_setting (BL timeout / profile)
        cpfseq  rx_parsed_cmd_acc, A                        ; reg: 0x02f
        goto    v171_bf08_case_check                      ; not 0x1D — try V1.72 BF/08
        movf    cmd1d_setting_cache_b0, W, B                                  ; reg: 0x0a7
        subwf   rx_parsed_data_acc, W, A                     ; reg: 0x030
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    rx_parser_entry__restart_after_frame                                   ; dest: 0x0005ea
        movff   rx_parsed_data_b0_phys, 0x0a7                    ; reg1: 0x030
        call    ir_profile_apply_cmd1d_mapping, 0x0                           ; dest: 0x000f54
        bra     rx_parser_entry__restart_after_frame                 ; 0x1D handled — exit

v171_bf08_case_check:
        ; ---------------------------------------------------------------
        ; V1.72 inline (V1.63b): BF/08 DSP-fault dispatch case
        ; ---------------------------------------------------------------
        ; MAIN V3.1+ emits BF/08 routed frames whose data byte carries
        ; the current DSP fault state (0 = clear, non-zero = fault code).
        ; Store the payload byte at the fixed V1.63b RAM slot
        ; (bf08_fault_byte at 0x0BC) so downstream menu/LCD code can
        ; display the fault code, and reflect the fault state into
        ; control_flags.DSP_FAULT_BIT.  On a 1→0 transition, clear the
        ; full-sync counter pair so the main loop re-emits the full
        ; status burst immediately (V1.63b resync-on-clear).
        movlw   0x08                                        ; CMD dsp_fault
        cpfseq  rx_parsed_cmd_acc, A                        ; reg: 0x02f
        goto    v172_bf4f_identity_case_check             ; not BF/08 — try V1.72 identity, then BF/2N

        movff   rx_parsed_data_b0_phys, bf08_fault_byte_b0_phys         ; store payload byte
        ; V3.x MAINs send dsp_fault_flags & 0x44: bit6 is the persistent
        ; DSP-fault latch, bit2 is an ACKSTAT evidence bit.  Do not let an
        ; ACKSTAT-only 0x04 report create a sticky LCD '!' with no later clear.
        btfsc   rx_parsed_data_acc, 6, A
        bra     v171_bf08_set_fault

        ; Payload bit6 clear (0x00 or ACKSTAT-only 0x04) — clear the user
        ; fault indicator.  If the bit was already clear this is a no-op; if
        ; it was set, force a full-sync resync so MAIN gets a fresh status
        ; burst on the next loop iteration.
        btfss   control_flags_acc, DSP_FAULT_BIT, A
        bra     rx_parser_entry__restart_after_frame                 ; already clear
        bcf     control_flags_acc, DSP_FAULT_BIT, A
        movlb   0x01
        ; These bank-1 cells are intentionally not the bank-0 full_sync
        ; counter at 0x09F:0x0A0; leave the stock-derived 0x1A0 cell
        ; unresolved until the original intent is proven.
        clrf    v171_diag_reset_timeout_b1, BANKED
        clrf    stock_1A0_b1, BANKED
        movlb   0x00
        bra     rx_parser_entry__restart_after_frame

v171_bf08_set_fault:
        bsf     control_flags_acc, DSP_FAULT_BIT, A
        bra     rx_parser_entry__restart_after_frame

v172_bf4f_identity_case_check:
        ; ---------------------------------------------------------------
        ; V1.73/V3.4: BF/4F..BF/55 MAIN identity replies for the healthy
        ; Diagnostics title.  BF/52..53 remain the legacy low revision byte
        ; for V1.72/V3.3 compatibility; BF/54..55 add the high byte.
        ; Keep this parser separate from BF/21..2B counters so malformed
        ; identity traffic cannot drift diag state.
        ; ---------------------------------------------------------------
        movlw   0x4F
        cpfslt  rx_parsed_cmd_acc, A                          ; cmd < 0x4F? -> filename/BF/2x path
        bra     v172_bf4f_check_upper
        bra     v172_fname_case_check
v172_bf4f_check_upper:
        movlw   0x56
        cpfslt  rx_parsed_cmd_acc, A                          ; cmd < 0x56? -> identity
        bra     v171_bf2x_case_check
        movlb   0x02
        btfss   v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_PENDING, BANKED
        bra     v172_bf4f_exit_bsr0
        movf    v172_diag_id_expected_cmd_b2, W, BANKED
        xorwf   rx_parsed_cmd_acc, W, A
        bz      v172_bf4f_expected
        ; Wrong START id while waiting for START is a stale reply: ignore
        ; and leave the pending transaction alive.  Any other in-flight
        ; order error aborts the identity transaction.
        movlw   0x4F
        cpfseq  v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_abort
        movlw   0x4F
        cpfseq  rx_parsed_cmd_acc, A
        bra     v172_bf4f_exit_bsr0
        bra     v172_bf4f_start_mismatch
v172_bf4f_expected:
        movlw   0x4F
        cpfseq  v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_payload
        movf    v172_diag_id_pending_id_b2, W, BANKED
        xorwf   rx_parsed_data_acc, W, A
        bnz     v172_bf4f_start_mismatch
        movlw   0x50
        movwf   v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_exit_bsr0
v172_bf4f_start_mismatch:
        ; Ignore stale START with the wrong generation; do not cancel the
        ; live pending query.
        bra     v172_bf4f_exit_bsr0
v172_bf4f_payload:
        movlw   0x10
        cpfslt  rx_parsed_data_acc, A                          ; data >= 0x10?
        bra     v172_bf4f_abort
        movlw   0x50
        cpfseq  v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_payload_minor
        movf    rx_parsed_data_acc, W, A
        movwf   v172_diag_id_tmp_major_b2, BANKED
        movlw   0x51
        movwf   v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_exit_bsr0
v172_bf4f_payload_minor:
        movlw   0x51
        cpfseq  v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_payload_rev_hi
        movf    rx_parsed_data_acc, W, A
        movwf   v172_diag_id_tmp_minor_b2, BANKED
        movlw   0x52
        movwf   v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_exit_bsr0
v172_bf4f_payload_rev_hi:
        movlw   0x52
        cpfseq  v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_payload_rev_lo
        movf    rx_parsed_data_acc, W, A
        movwf   v172_diag_id_tmp_rev_hi_b2, BANKED
        movlw   0x53
        movwf   v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_exit_bsr0
v172_bf4f_payload_rev_lo:
        movlw   0x53
        cpfseq  v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_payload_rev16_hi
        ; BF/53 completes the legacy low revision byte.  V3.4+ continues
        ; with BF/54..55 for the high byte; older identities commit here
        ; with high byte 0.
        swapf   v172_diag_id_tmp_rev_hi_b2, W, BANKED
        andlw   0xF0
        iorwf   rx_parsed_data_acc, W, A
        movwf   v173_diag_id_tmp_rev_lo_b2, BANKED
        movlw   0x03
        cpfseq  v172_diag_id_tmp_major_b2, BANKED
        bra     v172_bf4f_commit_rev8
        movlw   0x04
        cpfseq  v172_diag_id_tmp_minor_b2, BANKED
        bra     v172_bf4f_commit_rev8
        movlw   0x54
        movwf   v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_exit_bsr0
v172_bf4f_commit_rev8:
        clrf    v172_diag_id_tmp_rev_hi_b2, BANKED
        bra     v172_bf4f_commit_common
v172_bf4f_payload_rev16_hi:
        movlw   0x54
        cpfseq  v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_payload_rev16_lo
        movf    rx_parsed_data_acc, W, A
        movwf   v172_diag_id_tmp_rev_hi_b2, BANKED
        movlw   0x55
        movwf   v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_exit_bsr0
v172_bf4f_payload_rev16_lo:
        movlw   0x55
        cpfseq  v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_abort
        swapf   v172_diag_id_tmp_rev_hi_b2, W, BANKED
        andlw   0xF0
        iorwf   rx_parsed_data_acc, W, A
        movwf   v172_diag_id_tmp_rev_hi_b2, BANKED
v172_bf4f_commit_common:
        btfsc   v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_TARGET, BANKED
        bra     v172_bf4f_commit_pb2
        movf    v173_diag_id_tmp_rev_lo_b2, W, BANKED
        movwf   v172_diag_id_pb1_rev_b2, BANKED
        movf    v172_diag_id_tmp_rev_hi_b2, W, BANKED
        movwf   v173_diag_id_pb1_rev_hi_b2, BANKED
        movf    v172_diag_id_tmp_major_b2, W, BANKED
        movwf   v172_diag_id_pb1_major_b2, BANKED
        movf    v172_diag_id_tmp_minor_b2, W, BANKED
        movwf   v172_diag_id_pb1_minor_b2, BANKED
        bsf     v172_diag_id_valid_mask_b2, 0, BANKED
        bsf     v172_diag_id_seen_mask_b2, 0, BANKED
        bra     v172_bf4f_commit_done
v172_bf4f_commit_pb2:
        movf    v173_diag_id_tmp_rev_lo_b2, W, BANKED
        movwf   v172_diag_id_pb2_rev_b2, BANKED
        movf    v172_diag_id_tmp_rev_hi_b2, W, BANKED
        movwf   v173_diag_id_pb2_rev_hi_b2, BANKED
        movf    v172_diag_id_tmp_major_b2, W, BANKED
        movwf   v172_diag_id_pb2_major_b2, BANKED
        movf    v172_diag_id_tmp_minor_b2, W, BANKED
        movwf   v172_diag_id_pb2_minor_b2, BANKED
        bsf     v172_diag_id_valid_mask_b2, 1, BANKED
        bsf     v172_diag_id_seen_mask_b2, 1, BANKED
v172_bf4f_commit_done:
        bcf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_PENDING, BANKED
        bcf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_RETRIED, BANKED
        movlb   0x01
        bsf     v171_diag_flags_b1, V171_DIAG_FLAG_DIRTY, BANKED
        movlb   0x02
        bra     v172_bf4f_exit_bsr0
v172_bf4f_abort:
        bcf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_PENDING, BANKED
v172_bf4f_exit_bsr0:
        movlb   0x00
        bra     rx_parser_entry__restart_after_frame

v172_fname_case_check:
        ; ---------------------------------------------------------------
        ; V1.72/V3.3: BF/2D..4E preset filename replies.
        ; Keep this after BF/08 + BF/4F..53 identity and before BF/2x
        ; diagnostics.  Lower/upper misses fall through to BF/2x.
        ; ---------------------------------------------------------------
        movlw   0x2D
        cpfslt  rx_parsed_cmd_acc, A                          ; cmd < 0x2D?
        bra     v172_fname_check_upper
        bra     v171_bf2x_case_check
v172_fname_check_upper:
        movlw   0x4F
        cpfslt  rx_parsed_cmd_acc, A                          ; cmd < 0x4F?
        bra     v171_bf2x_case_check
        movlb   0x02
        btfss   v172_fname_flags_b2, FNAME_PENDING, BANKED
        bra     fname_exit
        btfss   control_flags_acc, 0x2, A                 ; require fresh BF/Bx route
        bra     fname_exit

        movlw   0x2E
        cpfseq  rx_parsed_cmd_acc, A
        bra     fname_not_start_tail
        bra     fname_start
fname_not_start_tail:
        movlw   0x2F
        cpfseq  rx_parsed_cmd_acc, A
        bra     fname_not_start
fname_start:
        movf    v172_fname_id_b2, W, BANKED
        xorwf   rx_parsed_data_acc, W, A
        bnz     fname_disarm
        bsf     v172_fname_flags_b2, FNAME_ARMED, BANKED
        bcf     v172_fname_flags_b2, FNAME_LEN_SEEN, BANKED
        bcf     v172_fname_flags_b2, FNAME_VALID, BANKED
        clrf    v172_fname_len_b2, BANKED
        clrf    v172_fname_expected_len_b2, BANKED
        bcf     v172_fname_flags_b2, FNAME_TAILDIR, BANKED
        movlw   0x2E
        cpfseq  rx_parsed_cmd_acc, A
        bra     fname_exit
        bsf     v172_fname_flags_b2, FNAME_TAILDIR, BANKED
        bra     fname_exit

fname_not_start:
        btfss   v172_fname_flags_b2, FNAME_ARMED, BANKED
        bra     fname_exit
        movlw   0x2D
        cpfseq  rx_parsed_cmd_acc, A
        bra     fname_not_len
        btfsc   v172_fname_flags_b2, FNAME_LEN_SEEN, BANKED
        bra     fname_abort
        movf    v172_fname_len_b2, F, BANKED
        bnz     fname_abort
        movf    v172_fname_id_b2, W, BANKED
        xorwf   rx_parsed_data_acc, W, A
        movwf   v172_fname_expected_len_b2, BANKED
        movlw   0x1F
        cpfslt  v172_fname_expected_len_b2, BANKED             ; expected_len < 31
        bra     fname_abort
        bsf     v172_fname_flags_b2, FNAME_LEN_SEEN, BANKED
        bra     fname_exit

fname_not_len:
        movlw   0x4E
        cpfseq  rx_parsed_cmd_acc, A
        bra     fname_char
        movf    v172_fname_id_b2, W, BANKED
        xorwf   rx_parsed_data_acc, W, A
        bnz     fname_abort
        btfss   v172_fname_flags_b2, FNAME_LEN_SEEN, BANKED
        bra     fname_abort
        movf    v172_fname_len_b2, W, BANKED
        xorwf   v172_fname_expected_len_b2, W, BANKED
        bnz     fname_abort
        bsf     v172_fname_flags_b2, FNAME_VALID, BANKED
        clrf    v172_fname_retry_b2, BANKED        ; BUG-4: success resets the retry budget
        bcf     v172_fname_flags_b2, FNAME_PENDING, BANKED
        bcf     v172_fname_flags_b2, FNAME_ARMED, BANKED
        bcf     v172_fname_flags_b2, FNAME_WANT_QUERY, BANKED
        bcf     v172_fname_flags_b2, FNAME_QUERY_WAIT, BANKED
        clrf    v172_fname_deadline_lo_b2, BANKED
        clrf    v172_fname_deadline_hi_b2, BANKED
        clrf    v172_fname_scroll_off_b2, BANKED
        movlw   0x11
        cpfslt  v172_fname_len_b2, BANKED                      ; len < 17?
        bra     fname_end_maybe_tail
        bra     fname_end_mark_dirty
fname_end_maybe_tail:
        btfss   v172_fname_flags_b2, FNAME_TAILDIR, BANKED
        bra     fname_end_mark_dirty
        movf    v172_fname_len_b2, W, BANKED
        addlw   0xF0                                        ; len - 16
        movwf   v172_fname_scroll_off_b2, BANKED
fname_end_mark_dirty:
        movlw   FNAME_SCROLL_REST_HOLD
        movwf   v172_fname_scroll_hold_b2, BANKED
        clrf    v172_fname_scroll_div_lo_b2, BANKED
        clrf    v172_fname_scroll_div_hi_b2, BANKED
        call    fname_mark_row_dirty_valid, 0x0
        bra     fname_exit

fname_char:
        btfss   v172_fname_flags_b2, FNAME_LEN_SEEN, BANKED
        bra     fname_abort
        movlw   0x30
        subwf   rx_parsed_cmd_acc, W, A                         ; W = cmd - 0x30
        xorwf   v172_fname_len_b2, W, BANKED
        bnz     fname_abort
        movlw   0x20
        cpfslt  rx_parsed_data_acc, A                           ; data < ' '?
        bra     fname_char_check_high
        bra     fname_abort
fname_char_check_high:
        movlw   0x7F
        cpfslt  rx_parsed_data_acc, A                           ; data < 0x7F?
        bra     fname_abort
        lfsr    0x0, v172_fname_cache_b2_phys
        movf    v172_fname_len_b2, W, BANKED
        addwf   FSR0L, F, A
        movf    rx_parsed_data_acc, W, A
        movwf   INDF0, A
        incf    v172_fname_len_b2, F, BANKED
        bra     fname_exit

fname_abort:
        call    fname_reset_blank_maybe_retry, 0x0  ; BUG-4: bounded retry, not terminal blank
        bra     fname_exit
fname_disarm:
        bcf     v172_fname_flags_b2, FNAME_ARMED, BANKED
        bcf     v172_fname_flags_b2, FNAME_LEN_SEEN, BANKED
        clrf    v172_fname_len_b2, BANKED
        clrf    v172_fname_expected_len_b2, BANKED
fname_exit:
        movlb   0x00
        bcf     control_flags_acc, 0x2, A                  ; filename frame consumed
        bra     rx_parser_entry__restart_after_frame

v171_bf2x_case_check:
        ; ---------------------------------------------------------------
        ; V1.72 (Layer 5 Phase B + Tier-1): BF/21..2B diagnostics replies
        ; plus exact BF/2C link-health replies.
        ; ---------------------------------------------------------------
        ; V3.2 rev 0x37 MAIN emits two reply burst types into BF/2N space:
        ;   * cmd 0x21 -> 7-frame burst BF/21..BF/27  (runtime counters)
        ;   * cmd 0x22 -> 4-frame burst BF/28..BF/2B  (reset-cause flags)
        ;
        ; Cache slot layout (per PB, 11 cells, V32_DIAG_TIER1_SPEC.md):
        ;   PB1 base = v171_diag_pb1_i  (0x080); PB2 base offset = 11
        ;   slot 0 = I  (BF/21)
        ;   slot 1 = D  (BF/22)
        ;   slot 2 = S  (BF/23)
        ;   slot 3 = B  (BF/24)
        ;   slot 4 = R  (BF/25)
        ;   slot 5 = A  (BF/26)
        ;   slot 6 = P  (BF/27)  RUNTIME LAST FRAME -- clears RUNTIME_PENDING,
        ;                        marks PB present, toggles target
        ;   slot 7 = O  (BF/28)  Tier-1: POR flag
        ;   slot 8 = V  (BF/29)  Tier-1: BOR flag
        ;   slot 9 = W  (BF/2A)  Tier-1: WDT flag
        ;   slot 10 = X (BF/2B)  RESET LAST FRAME (Tier-1) -- clears
        ;                        RESET_PENDING, sets reset_seen bit for
        ;                        this PB so the page-entry hook does NOT
        ;                        re-fire cmd 0x22 within the same session
        ;
        ; Link-health must be exact-special-cased.  Do NOT widen the
        ; diagnostics cache range to 0x2C: the cache has exactly 11
        ; cells, so BF/2C would be offset 11 and corrupt adjacent RAM.
        movlw   0x2C
        cpfseq  rx_parsed_cmd_acc, A
        bra     v171_bf2x_diag_range_check
        bra     v171_health_bf2c_reply
v171_bf2x_diag_range_check:
        ; Range gate: accept cmd 0x21..0x2B only.
        movlw   0x21
        cpfslt  rx_parsed_cmd_acc, A                          ; cmd < 0x21? -> exit
        bra     v171_bf2x_check_upper
        bra     rx_parser_entry__restart_after_frame
v171_bf2x_check_upper:
        movlw   0x2C
        cpfslt  rx_parsed_cmd_acc, A                          ; cmd < 0x2C? -> ok
        bra     rx_parser_entry__restart_after_frame                 ; cmd >= 0x2C -> exit
        ; Compute byte offset: (cmd - 0x21) gives 0..10.
        movlw   0x21
        subwf   rx_parsed_cmd_acc, W, A
        movwf   (Common_RAM + 4), A                       ; col_offset
        ; --- Pick "effective target" for this frame's cache routing ---
        ; Two reply burst types share the BF/2N space:
        ;   col 0..6   -- cmd 0x21 reply (runtime cells); use SNAPSHOT
        ;                 v171_diag_runtime_target captured when cmd
        ;                 0x21 was sent.  BF/27 toggles the live target,
        ;                 and reset-cause traffic can interleave, so the
        ;                 live target is not a stable cache key.
        ;   col 7..10  -- cmd 0x22 reply (reset cells, Tier-1); use
        ;                 SNAPSHOT v171_diag_reset_target captured at
        ;                 cmd 0x22 send time.  v171_diag_target can
        ;                 toggle independently between cmd 0x22 send
        ;                 and BF/2B reception (via an interleaved cmd
        ;                 0x21 BF/27 from the OTHER PB), so reading
        ;                 the live target for cmd 0x22 frames would
        ;                 mis-route the 4 reset bytes to the wrong
        ;                 PB's cache cells AND set the wrong
        ;                 v171_diag_reset_seen bit on BF/2B.  See the
        ;                 codex review note attached to commit d3d15cd.
        ; Default = runtime snapshot; cmd 0x22 path overrides with its
        ; reset snapshot.  Keep this in BANK 1: Common_RAM+5 is clobbered
        ; by the in-ISR RC5 decoder.
        movlb   0x01
        movf    v171_diag_runtime_target_b1, W, BANKED
        movwf   v171_diag_effective_target_b1, BANKED        ; effective_target
        movlw   0x07
        cpfslt  (Common_RAM + 4), A                       ; col < 7? skip if so
        bra     v171_bf2x_use_reset_target                ; col >= 7: override
        bra     v171_bf2x_have_effective_target           ; col < 7: keep live
v171_bf2x_use_reset_target:
        movf    v171_diag_reset_target_b1, W, BANKED
        movwf   v171_diag_effective_target_b1, BANKED
v171_bf2x_have_effective_target:
        ; Compute slot base: PB1 base = v171_diag_pb1_i (0x80),
        ; PB2 base = v171_diag_pb2_i (0x8B = 0x80 + 11).  Add 11 (0x0B)
        ; if effective_target bit0 set.
        movlw   v171_diag_pb1_i
        btfsc   v171_diag_effective_target_b1, 0, BANKED
        movlw   v171_diag_pb2_i
        addwf   (Common_RAM + 4), W, A                    ; W = base + col_offset
        ; Write payload via FSR0 in BANK 1 (0x180..0x195 physical).
        movwf   FSR0L, A
        movlw   0x01
        movwf   FSR0H, A
        movff   rx_parsed_data_b0_phys, INDF0                     ; *(slot) = data
        ; Do not redraw on every individual BF/2N cell.  The LCD is
        ; rendered from the complete per-PB cache; mark DIRTY only when
        ; the runtime burst completes (BF/27, via the health-freshness
        ; helper below) or when the reset burst completes (BF/2B).
        ; This keeps sustained Diagnostics pages from turning a single
        ; query into seven full-screen LCD rewrites.
        movlb   0x01
        ; Last-frame dispatch: col_offset 6 = BF/27 (RUNTIME LAST),
        ; col_offset 10 = BF/2B (Tier-1 RESET LAST).
        movlw   0x06
        cpfseq  (Common_RAM + 4), A                       ; col_offset == 6 (BF/27)?
        bra     v171_bf2x_check_reset_last
        ; --- RUNTIME LAST FRAME (BF/27) ---
        ; Mark this PB present so the renderer drops "n/a", clear
        ; RUNTIME_PENDING (cadence skip-on-silent gate), and toggle target
        ; so the next cadence query goes to the OTHER PB.  Target toggle
        ; is HERE (not in the cadence loop) so target stays stable for
        ; the full query/reply round-trip.
        ;
        ; Use v171_diag_effective_target -- which equals
        ; v171_diag_runtime_target on this path (col 6 < 7) -- for the
        ; present-mask OR-in.  The btg below operates on the LIVE
        ; v171_diag_target directly because that's what we're toggling.
        movlw   0x01                                      ; PB1 mask
        btfsc   v171_diag_effective_target_b1, 0, BANKED
        movlw   0x02                                      ; PB2 mask
        iorwf   v171_diag_present_b1, F, BANKED
        ; A completed addressed Diagnostics burst also proves CONTROL
        ; reached that PB.  Count it as link freshness so Diagnostics
        ; pages do not need a competing background cmd 0x23 poll.
        call    v171_health_mark_common_target_fresh, 0x0
        movlb   0x01
        bcf     v171_diag_flags_b1, V171_DIAG_FLAG_RUNTIME_PENDING, BANKED
        btg     v171_diag_target_b1, 0, BANKED               ; flip for next query
        movlb   0x00
        bra     rx_parser_entry__restart_after_frame
v171_bf2x_check_reset_last:
        ; --- RESET LAST FRAME (BF/2B, Tier-1) ---
        ; Tier-1: when the 4-frame BF/28..BF/2B reset-cause burst
        ; completes, mark the reset cells as fresh for this PB so the
        ; page-entry hook does NOT re-fire cmd 0x22 within the same
        ; session, and clear RESET_PENDING.  Do NOT touch the runtime
        ; present mask / runtime target / RUNTIME_PENDING -- those are
        ; managed independently by the cmd 0x21 path above.
        ;
        ; Use v171_diag_effective_target -- which equals
        ; v171_diag_reset_target on this path (col 10 >= 7) -- for the
        ; reset_seen OR-in.  v171_diag_target may have toggled via an
        ; interleaved BF/27 from the OTHER PB during the cmd 0x22
        ; reply burst; reading the live target here would set the
        ; wrong reset_seen bit (codex MEDIUM review fix).
        movlw   0x0A
        cpfseq  (Common_RAM + 4), A                       ; col_offset == 10 (BF/2B)?
        bra     v171_bf2x_check_reset_last_exit_bsr0      ; not last frame -- reset BSR + exit
        movlw   0x01                                      ; PB1 reset_seen bit
        btfsc   v171_diag_effective_target_b1, 0, BANKED
        movlw   0x02                                      ; PB2 reset_seen bit
        iorwf   v171_diag_reset_seen_b1, F, BANKED
        bsf     v171_diag_flags_b1, V171_DIAG_FLAG_DIRTY, BANKED
        bcf     v171_diag_flags_b1, V171_DIAG_FLAG_RESET_PENDING, BANKED
v171_bf2x_check_reset_last_exit_bsr0:
        ; HOT FIX (real-HW disaster 2026-04-20): the prior `bra flow_
        ; rx_parser_entry_05EA` here did NOT reset BSR before returning
        ; to the parser tail.  The parser tail's rx_ring drain path uses
        ; `movf 0x99, W, B` / `cpfseq 0x98, B` (BANKED operand 0x098/099)
        ; expecting BSR=0 to address rx_ring_rd / rx_ring_wr in BANK 0.
        ; With BSR left at 1, those instructions read physical 0x198/199
        ; instead -- which is v171_diag_poll_lo / v171_diag_poll_hi (the
        ; cmd 0x21 cadence countdown).  The parser then mis-parses every
        ; subsequent RX byte: thinks the ring has a different fill level
        ; than reality, drops bytes, frame state corrupts.  Symptoms on
        ; real HW: garbled LCD, button presses lost, backlight off as
        ; idle_timeout aliases v171_diag_reset_seen and counts down
        ; spuriously.
        ;
        ; The pre-Tier-1 V1.72 source had the SAME bra-without-movlb
        ; bug here but its consequence was benign because the aliased
        ; cells were rx_ring body (operand 0x80..0x94 in BANK 0 = upper
        ; half of the 48-byte rx_ring at 0x66..0x95) -- a circular
        ; buffer where corruption gets overwritten on the next wrap.
        ; Phase 3.1's cache extension shifted cells up into the
        ; ring-INDEX / idle-timer / full-sync zone, making the leak
        ; catastrophic.
        movlb   0x00
        bra     rx_parser_entry__restart_after_frame

v171_health_bf2c_reply:
        ; Exact BF/2C health reply.  Expected replies reset the age for
        ; the pending target snapshot.  Unsolicited BF/2C is ignored so
        ; a stale byte cannot falsely mark a PB fresh or touch the
        ; diagnostics cache.
        movlb   0x01
        btfss   v171_health_flags_b1, V171_HEALTH_FLAG_PENDING, BANKED
        bra     v171_health_bf2c_done
        bcf     v171_health_flags_b1, V171_HEALTH_FLAG_PENDING, BANKED
        clrf    v171_health_pending_ticks_b1, BANKED
        bsf     v171_health_flags_b1, V171_HEALTH_FLAG_DISPLAY_DIRTY, BANKED
        btg     v171_health_poll_target_b1, 0, BANKED
        btfsc   v171_health_flags_b1, V171_HEALTH_FLAG_TARGET, BANKED
        bra     v171_health_bf2c_pb2
        clrf    v171_health_age_pb1_b1, BANKED
        bsf     v171_health_seen_mask_b1, 0, BANKED
        bra     v171_health_bf2c_done
v171_health_bf2c_pb2:
        clrf    v171_health_age_pb2_b1, BANKED
        bsf     v171_health_seen_mask_b1, 1, BANKED
v171_health_bf2c_done:
        movlb   0x00
        bra     rx_parser_entry__restart_after_frame

v171_health_mark_common_target_fresh:
        ; Input: v171_diag_effective_target.bit0 = target snapshot (0 PB1, 1 PB2).
        ; Used by the Diagnostics BF/27 last-frame path; a full addressed
        ; diagnostics reply is also a successful PB reachability proof.
        movlb   0x01
        bsf     v171_health_flags_b1, V171_HEALTH_FLAG_DISPLAY_DIRTY, BANKED
        bsf     v171_diag_flags_b1, V171_DIAG_FLAG_DIRTY, BANKED
        btfsc   v171_diag_effective_target_b1, 0, BANKED
        bra     v171_health_mark_common_target_pb2
        clrf    v171_health_age_pb1_b1, BANKED
        bsf     v171_health_seen_mask_b1, 0, BANKED
        movlb   0x00
        return  0x0
v171_health_mark_common_target_pb2:
        clrf    v171_health_age_pb2_b1, BANKED
        bsf     v171_health_seen_mask_b1, 1, BANKED
        movlb   0x00
        return  0x0

rx_parser_entry__restart_after_frame:                                                  ; address: 0x0005ea

        bra     rx_parser_entry                                ; dest: 0x00044a


; ===========================================================================
; tx_byte_enqueue @ 0x0005EC — tx_byte_enqueue   (V1.6b @ 0x00060C in agent map)
; ---------------------------------------------------------------------------
; Enqueues 0x027 (tx_data_staging) into the 48-byte TX ring at 0x036+. The
; ring is read by the ISR via PIE1.TXIE (kicked at the bottom of this
; routine after committing the new tx_ring_wr).  Producer-side index is
; 0x097, consumer-side is 0x096.  Wrapping at 0x30 (= 48 bytes).
;
; *** V1.72 Layer 1 fix for BUG C6 (tx_byte_enqueue_busy_wait) ***
; The V1.6b body busy-waited indefinitely at 0x00060C while the ring
; was at the producer/consumer collision boundary, on the assumption
; that the TX ISR would advance tx_ring_rd within a few microseconds.
; In practice this assumption fails whenever MAIN's main_uart_service
; pauses for tens of milliseconds (V3.2 legacy 97-iter preset apply,
; standby/wake handshake, etc.) — CONTROL stalls inside this routine,
; misses status responses, and the LCD eventually drops to WAITING.
;
; V1.72 replaces the indefinite busy-wait with a bounded 256-tick
; budget.  On a healthy chain the loop exits on the first iteration
; (one-cycle TX ISR latency), so steady-state behavior is unchanged.
; On a saturated chain the budget expires, the byte is dropped
; (tx_ring_wr is NOT committed, so the byte sitting in tx_ring_base
; gets overwritten by the next caller), v171_tx_saturate_count is
; bumped (saturating at 0xFF, see ram.inc for slot rationale), and
; the routine returns with C=1 so callers can decide whether to
; retry, log, or escalate.  Existing callers that ignore C continue
; to function — they just lose the byte rather than hanging the
; whole CONTROL main loop.
;
; Calling convention (V1.72):
;   in : tx_data_staging (0x027) holds the byte to enqueue
;   out: STATUS.C = 0 on commit, 1 on saturation (byte dropped)
;        v171_tx_saturate_count incremented on saturation
;        tx_data_staging, v171_tx_enq_retry are clobbered scratch
; ===========================================================================
; tx_ring_reserve_3 — V1.72 atomic 3-byte frame guard
; ---------------------------------------------------------------------------
; Probes whether the TX ring has at least 3 free slots BEFORE a 3-byte
; frame sender starts enqueueing. If so, the subsequent 3 tx_byte_enqueue
; calls are guaranteed to commit (the main loop is the single producer
; and the ISR only drains — ring_rd can only advance between our calls,
; creating MORE room, never less). If not, returns C=1 without touching
; tx_ring_wr — no partial frame can reach the wire.
;
; Motivation
; ----------
; Without this guard the 3-byte senders (v171_send_wake_cmd_frame,
; v171_send_standby_cmd_frame, serial_tx_routed_frame, poll_frame_send)
; could commit byte 1 (e.g. 0xB0 route), then saturate on byte 2 or 3.
; MAIN's parser would see a partial frame header and either (a) drop it
; via main_service_rx_frame_gap, or worse (b) fuse the next unrelated
; TX byte into the standby/wake data slot — accidental state flip.
; Making the 3-byte frame atomic eliminates that risk entirely.
;
; Saturation accounting
; ---------------------
; On saturation this helper bumps v171_tx_saturate_count the same way
; tx_byte_enqueue does (saturating clamp at 0xFF), so the Layer 5
; diagnostics counter still reflects dropped frames — now at FRAME
; granularity rather than per-byte, which is what field investigation
; actually wants to observe.
;
; Calling convention
; ------------------
;   in : (none)
;   out: STATUS.C = 0  → ring has >= 3 free slots; caller safe to enqueue
;        STATUS.C = 1  → saturated; caller MUST not enqueue (abort)
;        v171_tx_saturate_count bumped on saturation (clamp at 0xFF)
;        v171_tx_enq_retry clobbered (reused as scratch)
; ===========================================================================
tx_ring_reserve_3:
        ; BSR safety: `tx_ring_rd` / `tx_ring_wr` are BANKED operands
        ; (low-byte 0x96/0x97).  Bank 1 at the SAME low bytes holds
        ; `v171_diag_target` / `v171_diag_present`, so if a caller
        ; arrives with BSR=1 (IR dispatch path can enter with arbitrary
        ; BSR) our probe would read wrong cells and either falsely
        ; saturate (aborting a valid STDBY/WAKE frame) or falsely pass
        ; + corrupt the downstream tx_byte_enqueue which has the same
        ; BSR dependency.  Set BSR=0 at entry so the helper is BSR-
        ; agnostic from the caller's perspective; the success path
        ; leaves BSR=0 which is also what tx_byte_enqueue expects.
        movlb   0x00
        movf    tx_ring_rd_b0, W, B                    ; W = rd
        subwf   tx_ring_wr_b0, W, B                    ; W = wr - rd (2's comp)
        btfss   STATUS, C, A                        ; C=1 if wr >= rd (no borrow)
        addlw   0x30                                 ; borrow: W = wr-rd+48 (mod 256 wraps back to occ)
        addlw   0x03                                 ; W = occupancy + 3
        movwf   v171_tx_enq_retry_acc, A                ; scratch
        movlw   0x30                                 ; 48 = ring capacity (one slot reserved)
        cpfslt  v171_tx_enq_retry_acc, A                ; skip next if (occ+3) < 48 → room OK
        bra     tx_ring_reserve_3_saturated
        bcf     STATUS, C, A
        return  0x0

tx_ring_reserve_3_saturated:
        movlb   0x01
        incfsz  v171_tx_saturate_count_b1, F, BANKED
        bra     tx_ring_reserve_3_sat_done
        setf    v171_tx_saturate_count_b1, BANKED       ; clamp at 0xFF
tx_ring_reserve_3_sat_done:
        movlb   0x00
        bsf     STATUS, C, A
        return  0x0


; ===========================================================================
; tx_byte_enqueue:
tx_byte_enqueue:                                               ; address: 0x0005ec

        lfsr    0x0, tx_ring_base_b0_phys
        movf    tx_ring_wr_b0, W, B                                  ; reg: 0x097
        movff   tx_data_staging_b0_phys, PLUSW0                   ; reg1: 0x027, reg2: 0xfeb
        incf    tx_ring_wr_b0, W, B                                  ; reg: 0x097
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        movlw   0x30
        subwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    tx_byte_enqueue__commit_or_wait                                   ; dest: 0x000606
        clrf    tx_data_staging_acc, A                        ; reg: 0x027

tx_byte_enqueue__commit_or_wait:                                                  ; address: 0x000606

        btfss   PIE1, TXIE, A                               ; reg: 0xf9d, bit: 4
        goto    tx_byte_enqueue__commit_success                                   ; dest: 0x000614

        ; V1.72 Layer 1: bounded retry replaces V1.6b indefinite busy-wait.
        ; setf gives 256 polls before saturation (~0.5 ms wall time at
        ; 4 MIPS — comfortably longer than worst-case TX ISR latency on
        ; a healthy link, and bounded enough that CONTROL's main loop
        ; can't be stalled by a wedged downstream).
        setf    v171_tx_enq_retry_acc, A                        ; reg: 0x02d (256-tick budget)

tx_byte_enqueue__wait_for_ring_room:                                                  ; address: 0x00060c

        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        subwf   tx_ring_rd_b0, W, B                                  ; reg: 0x096
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     tx_byte_enqueue__commit_success                   ; room available — commit
        decfsz  v171_tx_enq_retry_acc, F, A                     ; reg: 0x02d (decrement budget)
        bra     tx_byte_enqueue__wait_for_ring_room                   ; budget remains — re-poll

        ; --- V1.72 Layer 1 saturation path ---
        ; Budget exhausted.  Bump saturating counter (clamped at 0xFF
        ; so prolonged saturation doesn't roll back to zero), set C=1,
        ; and return without committing tx_ring_wr.  The byte already
        ; written to tx_ring_base[old_wr] is NOT visible to the ISR
        ; (it never bumps tx_ring_wr) and will be overwritten on the
        ; next successful enqueue.
        movlb   0x01
        incfsz  v171_tx_saturate_count_b1, F, BANKED           ; phys: 0x1ad
        bra     v171_tx_enq_saturate_done
        setf    v171_tx_saturate_count_b1, BANKED              ; phys: 0x1ad (clamp at 0xFF)
v171_tx_enq_saturate_done:
        movlb   0x00
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0 (C=1 = saturated)
        return  0x0

tx_byte_enqueue__commit_success:                                                  ; address: 0x000614

        movff   tx_data_staging_b0_phys, 0x097                    ; reg1: 0x027
        bsf     PIE1, TXIE, A                               ; reg: 0xf9d, bit: 4
        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0 (C=0 = success)
        return  0x0

; Temporarily coerces unknown raw-status values to full-input semantics for
; the legacy map helpers below.  The raw_status_cache byte remains authoritative
; BF/05 evidence, so callers restore it at the shared map return labels.
; Uses v171_tx_enq_retry_acc_phys only across straight-line mapping code; do
; not add calls between save/restore without auditing that scratch byte.  Do
; not use Common_RAM+40/0x028 here: that slot overlaps live IR timer state.
input_raw_status_full_fallback_save:
        movff   raw_status_cache_b0_phys, v171_tx_enq_retry_acc_phys
        movlb   0x00
        movlw   0x03
        cpfsgt  raw_status_cache_b0, BANKED
        return  0x0
        movwf   raw_status_cache_b0, BANKED
        return  0x0

input_raw_status_restore:
        movff   v171_tx_enq_retry_acc_phys, raw_status_cache_b0_phys
        return  0x0

map_cmd06_input_select_to_menu_index:                                               ; address: 0x00061c

        call    input_raw_status_full_fallback_save, 0x0
        clrf    rx_ring_staging_b0, B                                     ; default invalid input_select to Auto
        movf    rx_parsed_data_acc, F, A                     ; reg: 0x030
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    map_cmd06_input_select_to_menu_index__check_input_01                                   ; dest: 0x00062a
        clrf    rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    map_cmd06_input_select_to_menu_index__return                                   ; dest: 0x000768

map_cmd06_input_select_to_menu_index__check_input_01:                                                  ; address: 0x00062a

        decfsz  rx_parsed_data_acc, W, A                     ; reg: 0x030
        goto    map_cmd06_input_select_to_menu_index__check_input_02                                   ; dest: 0x000638
        movlw   0x05
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    map_cmd06_input_select_to_menu_index__return                                   ; dest: 0x000768

map_cmd06_input_select_to_menu_index__check_input_02:                                                  ; address: 0x000638

        movlw   0x02
        cpfseq  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    map_cmd06_input_select_to_menu_index__check_input_03                                   ; dest: 0x000658
        movf    raw_status_cache_b0, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    map_cmd06_input_select_to_menu_index__input_02_status_00                                   ; dest: 0x000650
        movlw   0x06
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    map_cmd06_input_select_to_menu_index__input_02_done                                   ; dest: 0x000654

map_cmd06_input_select_to_menu_index__input_02_status_00:                                                  ; address: 0x000650

        movlw   0x01
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_02_done:                                                  ; address: 0x000654

        goto    map_cmd06_input_select_to_menu_index__return                                   ; dest: 0x000768

map_cmd06_input_select_to_menu_index__check_input_03:                                                  ; address: 0x000658

        movlw   0x03
        cpfseq  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    map_cmd06_input_select_to_menu_index__check_input_04                                   ; dest: 0x000686
        movf    raw_status_cache_b0, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    map_cmd06_input_select_to_menu_index__input_03_status_00                                   ; dest: 0x00067e
        decfsz  raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_03_status_not_00_or_01                                   ; dest: 0x000676
        movlw   0x01
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    map_cmd06_input_select_to_menu_index__input_03_nonzero_status_join                                   ; dest: 0x00067a

map_cmd06_input_select_to_menu_index__input_03_status_not_00_or_01:                                                  ; address: 0x000676

        movlw   0x07
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_03_nonzero_status_join:                                                  ; address: 0x00067a

        goto    map_cmd06_input_select_to_menu_index__input_03_done                                   ; dest: 0x000682

map_cmd06_input_select_to_menu_index__input_03_status_00:                                                  ; address: 0x00067e

        movlw   0x02
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_03_done:                                                  ; address: 0x000682

        goto    map_cmd06_input_select_to_menu_index__return                                   ; dest: 0x000768

map_cmd06_input_select_to_menu_index__check_input_04:                                                  ; address: 0x000686

        movlw   0x04
        cpfseq  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    map_cmd06_input_select_to_menu_index__check_input_05                                   ; dest: 0x0006c4
        movf    raw_status_cache_b0, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    map_cmd06_input_select_to_menu_index__input_04_status_00                                   ; dest: 0x0006bc
        decfsz  raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_04_check_status_02                                   ; dest: 0x0006a0
        movlw   0x02
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_04_check_status_02:                                                  ; address: 0x0006a0

        movlw   0x02
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_04_check_status_03                                   ; dest: 0x0006ac
        movlw   0x01
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_04_check_status_03:                                                  ; address: 0x0006ac

        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_04_nonzero_status_join                                   ; dest: 0x0006b8
        movlw   0x08
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_04_nonzero_status_join:                                                  ; address: 0x0006b8

        goto    map_cmd06_input_select_to_menu_index__input_04_done                                   ; dest: 0x0006c0

map_cmd06_input_select_to_menu_index__input_04_status_00:                                                  ; address: 0x0006bc

        movlw   0x03
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_04_done:                                                  ; address: 0x0006c0

        goto    map_cmd06_input_select_to_menu_index__return                                   ; dest: 0x000768

map_cmd06_input_select_to_menu_index__check_input_05:                                                  ; address: 0x0006c4

        movlw   0x05
        cpfseq  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    map_cmd06_input_select_to_menu_index__check_input_06                                   ; dest: 0x000702
        movf    raw_status_cache_b0, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    map_cmd06_input_select_to_menu_index__input_05_status_00                                   ; dest: 0x0006fa
        decfsz  raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_05_check_status_02                                   ; dest: 0x0006de
        movlw   0x03
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_05_check_status_02:                                                  ; address: 0x0006de

        movlw   0x02
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_05_check_status_03                                   ; dest: 0x0006ea
        movlw   0x02
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_05_check_status_03:                                                  ; address: 0x0006ea

        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_05_nonzero_status_join                                   ; dest: 0x0006f6
        movlw   0x01
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_05_nonzero_status_join:                                                  ; address: 0x0006f6

        goto    map_cmd06_input_select_to_menu_index__input_05_done                                   ; dest: 0x0006fe

map_cmd06_input_select_to_menu_index__input_05_status_00:                                                  ; address: 0x0006fa

        movlw   0x04
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_05_done:                                                  ; address: 0x0006fe

        goto    map_cmd06_input_select_to_menu_index__return                                   ; dest: 0x000768

map_cmd06_input_select_to_menu_index__check_input_06:                                                  ; address: 0x000702

        movlw   0x06
        cpfseq  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    map_cmd06_input_select_to_menu_index__check_input_07                                   ; dest: 0x000730
        decfsz  raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_06_check_status_02                                   ; dest: 0x000714
        movlw   0x04
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_06_check_status_02:                                                  ; address: 0x000714

        movlw   0x02
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_06_check_status_03                                   ; dest: 0x000720
        movlw   0x03
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_06_check_status_03:                                                  ; address: 0x000720

        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_06_done                                   ; dest: 0x00072c
        movlw   0x02
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_06_done:                                                  ; address: 0x00072c

        goto    map_cmd06_input_select_to_menu_index__return                                   ; dest: 0x000768

map_cmd06_input_select_to_menu_index__check_input_07:                                                  ; address: 0x000730

        movlw   0x07
        cpfseq  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    map_cmd06_input_select_to_menu_index__check_input_08                                   ; dest: 0x000754
        movlw   0x02
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_07_check_status_03                                   ; dest: 0x000744
        movlw   0x04
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_07_check_status_03:                                                  ; address: 0x000744

        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__input_07_done                                   ; dest: 0x000750
        movlw   0x03
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__input_07_done:                                                  ; address: 0x000750

        goto    map_cmd06_input_select_to_menu_index__return                                   ; dest: 0x000768

map_cmd06_input_select_to_menu_index__check_input_08:                                                  ; address: 0x000754

        movlw   0x08
        cpfseq  rx_parsed_data_acc, A                        ; reg: 0x030
        goto    map_cmd06_input_select_to_menu_index__return                                   ; dest: 0x000768
        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_cmd06_input_select_to_menu_index__return                                   ; dest: 0x000768
        movlw   0x04
        movwf   rx_ring_staging_b0, B                                     ; reg: 0x0b7

map_cmd06_input_select_to_menu_index__return:                                                  ; address: 0x000768

        call    input_raw_status_restore, 0x0
        return  0x0

; Returns the cmd-0x06 input value in tx_data_staging.  The caller owns the
; PB-specific commit so split-mode PB2 edits cannot overwrite PB1 intent.
map_input_menu_index_to_cmd06_input_select:                                               ; address: 0x00076a

        call    input_raw_status_full_fallback_save, 0x0
        movf    rx_ring_staging_b0, F, B                                  ; reg: 0x0b7
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    map_input_menu_index_to_cmd06_input_select__check_menu_index_01                                   ; dest: 0x000778
        clrf    tx_data_staging_acc, A                        ; map result
        goto    map_input_menu_index_to_cmd06_input_select__return                                   ; dest: 0x0008aa

map_input_menu_index_to_cmd06_input_select__check_menu_index_01:                                                  ; address: 0x000778

        decfsz  rx_ring_staging_b0, W, B                                  ; reg: 0x0b7
        goto    map_input_menu_index_to_cmd06_input_select__check_menu_index_02                                   ; dest: 0x0007b4
        movf    raw_status_cache_b0, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_01_raw_status_00                                   ; dest: 0x0007ac
        decfsz  raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_01_check_raw_status_02                                   ; dest: 0x000790
        movlw   0x03
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_01_check_raw_status_02:                                                  ; address: 0x000790

        movlw   0x02
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_01_check_raw_status_03                                   ; dest: 0x00079c
        movlw   0x04
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_01_check_raw_status_03:                                                  ; address: 0x00079c

        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_01_nonzero_raw_status_done                                   ; dest: 0x0007a8
        movlw   0x05
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_01_nonzero_raw_status_done:                                                  ; address: 0x0007a8

        goto    map_input_menu_index_to_cmd06_input_select__menu_index_01_done                                   ; dest: 0x0007b0

map_input_menu_index_to_cmd06_input_select__menu_index_01_raw_status_00:                                                  ; address: 0x0007ac

        movlw   0x02
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_01_done:                                                  ; address: 0x0007b0

        goto    map_input_menu_index_to_cmd06_input_select__return                                   ; dest: 0x0008aa

map_input_menu_index_to_cmd06_input_select__check_menu_index_02:                                                  ; address: 0x0007b4

        movlw   0x02
        cpfseq  rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    map_input_menu_index_to_cmd06_input_select__check_menu_index_03                                   ; dest: 0x0007f2
        movf    raw_status_cache_b0, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_02_raw_status_00                                   ; dest: 0x0007ea
        decfsz  raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_02_check_raw_status_02                                   ; dest: 0x0007ce
        movlw   0x04
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_02_check_raw_status_02:                                                  ; address: 0x0007ce

        movlw   0x02
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_02_check_raw_status_03                                   ; dest: 0x0007da
        movlw   0x05
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_02_check_raw_status_03:                                                  ; address: 0x0007da

        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_02_nonzero_raw_status_done                                   ; dest: 0x0007e6
        movlw   0x06
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_02_nonzero_raw_status_done:                                                  ; address: 0x0007e6

        goto    map_input_menu_index_to_cmd06_input_select__menu_index_02_done                                   ; dest: 0x0007ee

map_input_menu_index_to_cmd06_input_select__menu_index_02_raw_status_00:                                                  ; address: 0x0007ea

        movlw   0x03
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_02_done:                                                  ; address: 0x0007ee

        goto    map_input_menu_index_to_cmd06_input_select__return                                   ; dest: 0x0008aa

map_input_menu_index_to_cmd06_input_select__check_menu_index_03:                                                  ; address: 0x0007f2

        movlw   0x03
        cpfseq  rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    map_input_menu_index_to_cmd06_input_select__check_menu_index_04                                   ; dest: 0x000830
        movf    raw_status_cache_b0, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_03_raw_status_00                                   ; dest: 0x000828
        decfsz  raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_03_check_raw_status_02                                   ; dest: 0x00080c
        movlw   0x05
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_03_check_raw_status_02:                                                  ; address: 0x00080c

        movlw   0x02
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_03_check_raw_status_03                                   ; dest: 0x000818
        movlw   0x06
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_03_check_raw_status_03:                                                  ; address: 0x000818

        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_03_nonzero_raw_status_done                                   ; dest: 0x000824
        movlw   0x07
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_03_nonzero_raw_status_done:                                                  ; address: 0x000824

        goto    map_input_menu_index_to_cmd06_input_select__menu_index_03_done                                   ; dest: 0x00082c

map_input_menu_index_to_cmd06_input_select__menu_index_03_raw_status_00:                                                  ; address: 0x000828

        movlw   0x04
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_03_done:                                                  ; address: 0x00082c

        goto    map_input_menu_index_to_cmd06_input_select__return                                   ; dest: 0x0008aa

map_input_menu_index_to_cmd06_input_select__check_menu_index_04:                                                  ; address: 0x000830

        movlw   0x04
        cpfseq  rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    map_input_menu_index_to_cmd06_input_select__check_menu_index_05                                   ; dest: 0x00086e
        movf    raw_status_cache_b0, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_04_raw_status_00                                   ; dest: 0x000866
        decfsz  raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_04_check_raw_status_02                                   ; dest: 0x00084a
        movlw   0x06
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_04_check_raw_status_02:                                                  ; address: 0x00084a

        movlw   0x02
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_04_check_raw_status_03                                   ; dest: 0x000856
        movlw   0x07
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_04_check_raw_status_03:                                                  ; address: 0x000856

        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    map_input_menu_index_to_cmd06_input_select__menu_index_04_nonzero_raw_status_done                                   ; dest: 0x000862
        movlw   0x08
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_04_nonzero_raw_status_done:                                                  ; address: 0x000862

        goto    map_input_menu_index_to_cmd06_input_select__menu_index_04_done                                   ; dest: 0x00086a

map_input_menu_index_to_cmd06_input_select__menu_index_04_raw_status_00:                                                  ; address: 0x000866

        movlw   0x05
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__menu_index_04_done:                                                  ; address: 0x00086a

        goto    map_input_menu_index_to_cmd06_input_select__return                                   ; dest: 0x0008aa

map_input_menu_index_to_cmd06_input_select__check_menu_index_05:                                                  ; address: 0x00086e

        movlw   0x05
        cpfseq  rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    map_input_menu_index_to_cmd06_input_select__check_menu_index_06                                   ; dest: 0x00087e
        movlw   0x01
        movwf   tx_data_staging_acc, A                        ; map result
        goto    map_input_menu_index_to_cmd06_input_select__return                                   ; dest: 0x0008aa

map_input_menu_index_to_cmd06_input_select__check_menu_index_06:                                                  ; address: 0x00087e

        movlw   0x06
        cpfseq  rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    map_input_menu_index_to_cmd06_input_select__check_menu_index_07                                   ; dest: 0x00088e
        movlw   0x02
        movwf   tx_data_staging_acc, A                        ; map result
        goto    map_input_menu_index_to_cmd06_input_select__return                                   ; dest: 0x0008aa

map_input_menu_index_to_cmd06_input_select__check_menu_index_07:                                                  ; address: 0x00088e

        movlw   0x07
        cpfseq  rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    map_input_menu_index_to_cmd06_input_select__check_menu_index_08                                   ; dest: 0x00089e
        movlw   0x03
        movwf   tx_data_staging_acc, A                        ; map result
        goto    map_input_menu_index_to_cmd06_input_select__return                                   ; dest: 0x0008aa

map_input_menu_index_to_cmd06_input_select__check_menu_index_08:                                                  ; address: 0x00089e

        movlw   0x08
        cpfseq  rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    map_input_menu_index_to_cmd06_input_select__return                                   ; dest: 0x0008aa
        movlw   0x04
        movwf   tx_data_staging_acc, A                        ; map result

map_input_menu_index_to_cmd06_input_select__return:                                                  ; address: 0x0008aa

        call    input_raw_status_restore, 0x0
        return  0x0


; ===========================================================================
; button_scan_debounce @ 0x0008AC — button_scan_debounce  (V1.6b address)
; ---------------------------------------------------------------------------
; Reads the 6 panel buttons from PORTA / PORTC into 0x027 (raw scan), then
; debounces via a 4-tick stability counter at 0x0BB. Stable values land in
; 0x0BE (button_debounced) which the IR/menu dispatcher consumes.
;
; Button → pin mapping (active LOW; PORTx.read inverted into 0x027 bit):
;   0x027.bit0 = RA3 (Standby)   0x027.bit3 = RA1 (Select)
;   0x027.bit1 = RC0 (Up)         0x027.bit4 = RA4 (Right)
;   0x027.bit2 = RA2 (Down)       0x027.bit5 = RC5 (Left)
; ===========================================================================
; button_scan_debounce:
button_scan_debounce:                                               ; address: 0x0008ac

        movlb   0x00
        setf    tx_data_staging_acc, A                        ; reg: 0x027
        bsf     tx_data_staging_acc, 0x0, A                   ; reg: 0x027
        btfss   PORTA, RA3, A                               ; reg: 0xf80, bit: 3
        bcf     tx_data_staging_acc, 0x0, A                   ; reg: 0x027
        bsf     tx_data_staging_acc, 0x1, A                   ; reg: 0x027
        btfss   PORTC, RC0, A                               ; reg: 0xf82, bit: 0
        bcf     tx_data_staging_acc, 0x1, A                   ; reg: 0x027
        bsf     tx_data_staging_acc, 0x2, A                   ; reg: 0x027
        btfss   PORTA, RA2, A                               ; reg: 0xf80, bit: 2
        bcf     tx_data_staging_acc, 0x2, A                   ; reg: 0x027
        bsf     tx_data_staging_acc, 0x3, A                   ; reg: 0x027
        btfss   PORTA, RA1, A                               ; reg: 0xf80, bit: 1
        bcf     tx_data_staging_acc, 0x3, A                   ; reg: 0x027
        bsf     tx_data_staging_acc, 0x4, A                   ; reg: 0x027
        btfss   PORTC, RC5, A                               ; reg: 0xf82, bit: 5
        bcf     tx_data_staging_acc, 0x4, A                   ; reg: 0x027
        bsf     tx_data_staging_acc, 0x5, A                   ; reg: 0x027
        btfss   PORTA, RA4, A                               ; reg: 0xf80, bit: 4
        bcf     tx_data_staging_acc, 0x5, A                   ; reg: 0x027
        movlw   0xff
        xorwf   tx_data_staging_acc, F, A                     ; reg: 0x027
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        subwf   button_last_scan_b0, W, B                                  ; reg: 0x0bc
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    button_scan_debounce__stable_raw_sample_seen                                   ; dest: 0x0008ea
        clrf    button_debounce_counter_b0, B                                     ; reg: 0x0bb
        movff   tx_data_staging_b0_phys, 0x0bc                    ; reg1: 0x027
        goto    button_scan_debounce__update_event_latch                                   ; dest: 0x0008fc

button_scan_debounce__stable_raw_sample_seen:                                                  ; address: 0x0008ea

        movlw   0x04
        cpfslt  button_debounce_counter_b0, B                                     ; reg: 0x0bb
        goto    button_scan_debounce__commit_debounced_state                                   ; dest: 0x0008f8
        incf    button_debounce_counter_b0, F, B                                  ; reg: 0x0bb
        goto    button_scan_debounce__update_event_latch                                   ; dest: 0x0008fc

button_scan_debounce__commit_debounced_state:                                                  ; address: 0x0008f8

        movff   0x0bc, 0x0be

button_scan_debounce__update_event_latch:                                                  ; address: 0x0008fc

        clrf    button_event_latch_b0, B                                     ; reg: 0x09a
        movf    button_debounced_b0, W, B                                  ; reg: 0x0be
        subwf   button_debounced_prev_b0, W, B                                  ; reg: 0x0bd
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    button_scan_debounce__unchanged_state_repeat_tick                                   ; dest: 0x000918
        movff   0x0be, 0x0bd
        clrf    button_repeat_timer_lo_b0, B                                     ; reg: 0x09b
        clrf    button_repeat_timer_hi_b0, B                                     ; reg: 0x09c
        movff   0x0be, 0x09a
        goto    button_scan_debounce__maybe_emit_repeat_event                                   ; dest: 0x000924

button_scan_debounce__unchanged_state_repeat_tick:                                                  ; address: 0x000918

        rrcf    button_debounced_b0, W, B                                  ; reg: 0x0be
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    button_scan_debounce__maybe_emit_repeat_event                                   ; dest: 0x000924
        infsnz  button_repeat_timer_lo_b0, F, B                                  ; reg: 0x09b
        incf    button_repeat_timer_hi_b0, F, B                                  ; reg: 0x09c

button_scan_debounce__maybe_emit_repeat_event:                                                  ; address: 0x000924

        movlw   0xc9
        subwf   button_repeat_timer_lo_b0, W, B                                  ; reg: 0x09b
        movlw   0x32
        subwfb  button_repeat_timer_hi_b0, W, B                                  ; reg: 0x09c
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    button_scan_debounce__return                                   ; dest: 0x00093e
        movlw   0x28
        movwf   button_repeat_timer_lo_b0, B                                     ; reg: 0x09b
        movlw   0x23
        movwf   button_repeat_timer_hi_b0, B                                     ; reg: 0x09c
        movff   0x0be, 0x09a

button_scan_debounce__return:                                                  ; address: 0x00093e

        return  0x0

;@routine lcd_write_16char_rom_entry entry_bsr=unknown exit_bsr=preserve
lcd_write_16char_rom_entry:                                               ; address: 0x000940

        movff   tx_data_staging_b0_phys, (Common_RAM + 43)        ; reg1: 0x027, reg2: 0x02b
        clrf    (Common_RAM + 44), A                        ; reg: 0x02c
        movf    (Common_RAM + 44), W, A                     ; reg: 0x02c
        mullw   0x10
        movff   PRODL, (Common_RAM + 44)                    ; reg1: 0xff3, reg2: 0x02c
        movf    (Common_RAM + 43), W, A                     ; reg: 0x02b
        mullw   0x10
        movff   PRODL, (Common_RAM + 43)                    ; reg1: 0xff3, reg2: 0x02b
        movf    PRODH, W, A                                 ; reg: 0xff4
        addwf   (Common_RAM + 44), F, A                     ; reg: 0x02c
        movf    (Common_RAM + 43), W, A                     ; reg: 0x02b
        addwf   (Common_RAM + 41), F, A                     ; reg: 0x029
        movf    (Common_RAM + 44), W, A                     ; reg: 0x02c
        addwfc  (Common_RAM + 42), F, A                     ; reg: 0x02a
        clrf    tx_data_staging_acc, A                        ; reg: 0x027

lcd_write_16char_rom_entry__write_next_char:                                                  ; address: 0x000964

        movlw   0x10
        cpfslt  tx_data_staging_acc, A                        ; reg: 0x027
        goto    lcd_write_16char_rom_entry__return                                   ; dest: 0x00098e
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        addwf   (Common_RAM + 41), W, A                     ; reg: 0x029
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        movlw   0x00
        addwfc  (Common_RAM + 42), W, A                     ; reg: 0x02a
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        clrf    EECON1, A                                   ; reg: 0xfa6
        bsf     EECON1, EEPGD, A                            ; reg: 0xfa6, bit: 7
        tblrd*
        movff   TABLAT, (Common_RAM + 40)                   ; reg1: 0xff5, reg2: 0x028
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        call    lcd_char_write, 0x0                           ; dest: 0x0000ec
        incf    tx_data_staging_acc, F, A                     ; reg: 0x027
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     lcd_write_16char_rom_entry__write_next_char                                   ; dest: 0x000964

lcd_write_16char_rom_entry__return:                                                  ; address: 0x00098e

        return  0x0

settings_save_eeprom:                                               ; address: 0x000990

        clrf    EEADR, A                                    ; reg: 0xfa9
        movf    display_state_index_b0, W, B                                  ; reg: 0x0bf
        movwf   tx_data_staging_acc, A
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     settings_save_eeprom__legacy_menu_state
        movlb   0x00
        movlw   0x03
        cpfslt  tx_data_staging_acc, A
        bra     settings_save_eeprom__split_menu_state_ge3
        movf    tx_data_staging_acc, W, A
        bra     settings_save_eeprom__write_display_state
settings_save_eeprom__split_menu_state_ge3:
        movlw   0x07
        cpfslt  tx_data_staging_acc, A
        bra     settings_save_eeprom__clamp_runtime_state
        decf    tx_data_staging_acc, F, A                      ; split 3..6 -> legacy EEPROM 2..5
        movf    tx_data_staging_acc, W, A
        bra     settings_save_eeprom__write_display_state
settings_save_eeprom__legacy_menu_state:
        movlb   0x00
        movlw   0x06
        cpfslt  tx_data_staging_acc, A                        ; runtime PB2 Input is not persistent
        bra     settings_save_eeprom__clamp_runtime_state
        movf    tx_data_staging_acc, W, A
        bra     settings_save_eeprom__write_display_state
settings_save_eeprom__clamp_runtime_state:
        movlw   0x02                                        ; legacy-safe Input state
settings_save_eeprom__write_display_state:
        movlb   0x00
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x01
        movwf   EEADR, A                                    ; reg: 0xfa9
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x02
        movwf   EEADR, A                                    ; reg: 0xfa9
        movf    source_channel_menu_index_b0, W, B                                  ; reg: 0x0c0
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        clrf    tx_data_staging_acc, A                        ; reg: 0x027

settings_save_eeprom__write_next_setting_bank:                                                  ; address: 0x0009ae

        movlw   0x06                                        ; CMD input_select
        cpfslt  tx_data_staging_acc, A                        ; reg: 0x027
        goto    settings_save_eeprom__write_bl_timeout                                   ; dest: 0x000a3a
        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, saved_settings_base_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x09
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, stock_0C7_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x0f
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, stock_0CD_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x15
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, stock_0D3_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x1b                                        ; CMD channel_src_5
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, stock_0D9_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x21
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, stock_0DF_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x27
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, stock_0E5_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        incf    tx_data_staging_acc, F, A                     ; reg: 0x027
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     settings_save_eeprom__write_next_setting_bank                                   ; dest: 0x0009ae

settings_save_eeprom__write_bl_timeout:                                                  ; address: 0x000a3a

        movlw   0x73
        movwf   EEADR, A                                    ; reg: 0xfa9
        movf    backlight_timeout_selection_b0, W, B                                  ; reg: 0x0eb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        call    input_pb2_persist_save_if_dirty, 0x0
        return  0x0

input_pb2_persist_load:
        movlw   EEPROM_PB2_INPUT_ADDR
        call    eeprom_read_byte, 0x0
        movwf   tx_data_staging_acc, A
        movlb   0x01
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_PENDING_CONCRETE, BANKED
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY, BANKED
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE, BANKED
        clrf    input_pending_pb2_b1, BANKED
        movlb   0x00
        movf    tx_data_staging_acc, W, A
        xorlw   PB2_INPUT_EEPROM_LINKED
        bz      input_pb2_persist_load_done
        movf    tx_data_staging_acc, W, A
        andlw   0xF0
        xorlw   PB2_INPUT_EEPROM_CONCRETE_BASE
        bnz     input_pb2_persist_load_done
        movf    tx_data_staging_acc, W, A
        andlw   0x0F
        movlb   0x01
        movwf   input_pending_pb2_b1, BANKED
        movlw   0x09
        cpfslt  input_pending_pb2_b1, BANKED
        bra     input_pb2_persist_load_invalid
        bsf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_PENDING_CONCRETE, BANKED
        bra     input_pb2_persist_load_done_b0
input_pb2_persist_load_invalid:
        clrf    input_pending_pb2_b1, BANKED
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_PENDING_CONCRETE, BANKED
input_pb2_persist_load_done_b0:
        movlb   0x00
input_pb2_persist_load_done:
        movlb   0x00
        return  0x0

input_pb2_persist_encode_current:
        movlb   0x01
        btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        bra     input_pb2_persist_encode_linked
        movlw   0x09
        cpfslt  input_intent_pb2_b1, BANKED
        bra     input_pb2_persist_encode_linked
        movf    input_intent_pb2_b1, W, BANKED
        iorlw   PB2_INPUT_EEPROM_CONCRETE_BASE
        movlb   0x00
        return  0x0
input_pb2_persist_encode_linked:
        movlw   PB2_INPUT_EEPROM_LINKED
        movlb   0x00
        return  0x0

input_pb2_persist_save_if_dirty:
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY, BANKED
        bra     input_pb2_persist_save_done_b0
        call    input_pb2_persist_encode_current, 0x0
        movwf   (Common_RAM + 10), A
        movlw   EEPROM_PB2_INPUT_ADDR
        call    eeprom_read_byte, 0x0
        xorwf   (Common_RAM + 10), W, A
        bz      input_pb2_persist_save_clear_dirty
        movlw   EEPROM_PB2_INPUT_ADDR
        movwf   EEADR, A
        movf    (Common_RAM + 10), W, A
        call    eeprom_write_byte, 0x0
input_pb2_persist_save_clear_dirty:
        movlb   0x01
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY, BANKED
input_pb2_persist_save_done_b0:
        movlb   0x00
        return  0x0


; ===========================================================================
; settings_load_eeprom @ 0x000A46 — settings_load_eeprom  (V1.6b address)
; ---------------------------------------------------------------------------
; Reads saved settings from EEPROM at boot:
;   EEPROM[0x00] -> 0x0BF (display_state_index, V1.6b)
;   EEPROM[0x01] -> 0x0BA (some flag/mode byte)
;   EEPROM[0x02..0x0B] -> 0x0C1..0x0CC (channel config, backlight, etc.)
; Calls eeprom_read_byte (0x000196) for each byte read. The values are then
; reflected into the corresponding outgoing frames (input/volume/mute/
; display) on the next periodic emission.
; ===========================================================================
; settings_load_eeprom:
settings_load_eeprom:                                               ; address: 0x000a46

        movlw   0x00
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   tx_data_staging_acc, A
        movlw   0x06
        cpfslt  tx_data_staging_acc, A
        bra     settings_load_eeprom__clamp_display_state
        movff   tx_data_staging_b0_phys, display_state_index_b0_phys
        bra     settings_load_eeprom__read_setup_state
settings_load_eeprom__clamp_display_state:
        movlw   0x02                                        ; clamp erased/foreign runtime states to Input
        movwf   display_state_index_b0, B                                     ; reg: 0x0bf
settings_load_eeprom__read_setup_state:
        movlw   0x01
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   setup_submenu_index_b0, B                                     ; reg: 0x0ba
        movlw   0x02
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        clrf    tx_data_staging_acc, A                        ; reg: 0x027

settings_load_eeprom__read_next_setting_bank:                                                  ; address: 0x000a60

        movlw   0x06                                        ; CMD input_select
        cpfslt  tx_data_staging_acc, A                        ; reg: 0x027
        goto    settings_load_eeprom__read_bl_timeout                                   ; dest: 0x000afa
        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, saved_settings_base_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x09
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, stock_0C7_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x0f
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, stock_0CD_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x15
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, stock_0D3_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x1b                                        ; CMD channel_src_5
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, stock_0D9_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x21
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, stock_0DF_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x27
        addwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, stock_0E5_b0_phys
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        incf    tx_data_staging_acc, F, A                     ; reg: 0x027
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     settings_load_eeprom__read_next_setting_bank                                   ; dest: 0x000a60

settings_load_eeprom__read_bl_timeout:                                                  ; address: 0x000afa

        movlw   0x73
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   backlight_timeout_selection_b0, B                                     ; reg: 0x0eb
        movlw   0x05
        subwf   backlight_timeout_selection_b0, W, B                                  ; reg: 0x0eb
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    settings_load_eeprom__apply_bl_timeout_runtime_seed                                   ; dest: 0x000b10
        movlw   0x01
        movwf   backlight_timeout_selection_b0, B                                     ; reg: 0x0eb

settings_load_eeprom__apply_bl_timeout_runtime_seed:                                                  ; address: 0x000b10

        call    backlight_timeout_load_threshold, 0x0                           ; dest: 0x001478
        call    input_pb2_persist_load, 0x0
        return  0x0


; ===========================================================================
; serial_tx_routed_frame @ 0x000B16 — serial_tx_routed_frame
; ---------------------------------------------------------------------------
; Builds the standard 3-byte CONTROL→MAIN frame and enqueues it via
; tx_byte_enqueue. Inputs:
;   • W bit pattern → 0xB0 + route (0 broadcast, 1 addressed)
;   • 0x033 = route bits  • 0x034 = cmd byte  • 0x035 = data byte
; The full_sync_counter at 0x09F:0x0A0 is reset on every successful frame
; emission (so the periodic full_sync_burst trigger is debounced by any
; explicit traffic).
; Used by every other full_sync_burst..035 helper as the actual UART driver.
; ===========================================================================
; serial_tx_routed_frame:
serial_tx_routed_frame:                                               ; address: 0x000b16

        ; V1.72 atomic 3-byte frame: reserve ring slots first so partial
        ; frames cannot leak to the wire (see tx_ring_reserve_3 header).
        rcall   tx_ring_reserve_3
        bc      serial_tx_routed_frame_aborted
        movlw   0xb0                                        ; ROUTE broadcast CONTROL→MAIN
        addwf   (Common_RAM + 51), W, A                     ; reg: 0x033
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movff   (Common_RAM + 52), tx_data_staging        ; reg1: 0x034, reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movff   (Common_RAM + 53), tx_data_staging        ; reg1: 0x035, reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        clrf    full_sync_lo_b0, B                                     ; reg: 0x09f
        clrf    full_sync_hi_b0, B                                     ; reg: 0x0a0
        return  0x0

serial_tx_routed_frame_aborted:
        return  0x0


; ===========================================================================
; full_sync_burst @ 0x000B36 — V1.72 Layer 2 one-frame-per-call dispatch
; ---------------------------------------------------------------------------
; *** V1.72 Layer 2 fix for BUG C7 (fullsync_burst_saturates_link) ***
;
; The V1.6b body emitted 5 status frames back-to-back (volume, input,
; mute, cmd1d_setting, standby_wake) with ~250 µs inter-frame delays.
; Total wire-time: ~17 bytes ≈ 5.5 ms at 31,250 baud, which under
; combined load (e.g. user volume nudge during burst, MAIN in 97-iter
; preset apply not draining its RX ring) caused MAIN's RX to stack
; up faster than main_uart_service_1be6 could process — the same
; saturation symptom that triggered the WAITING regression in the
; rapid_ir wire-chain test.
;
; V1.72 Layer 2 replaces the burst with a one-frame-per-call state
; machine.  Each invocation of full_sync_burst (still called from
; the display-loop full-sync timer trigger ~every 80,000 iterations)
; advances v171_full_sync_step (1..6, wraps 6→1) and emits a single
; frame.  Six full triggers complete one cycle, ~480 ms apart at
; typical iteration rate — well above the chain's drain rate, so
; the link never saturates.
;
; Step encoding (see dlcp_control_ram.inc):
;   1 = volume_frame_send          (V1.6b stock)
;   2 = input_frame_send            (V1.6b stock)
;   3 = mute_frame_send             (V1.6b stock)
;   4 = cmd1d_setting_frame_send    (V1.6b stock)
;   5 = standby_wake_broadcast      (V1.6b stock)
;   6 = v171_send_preset_frame_txonly  *** Layer 2 NEW ***
;
; Step 6 is the architectural fix for the preset-desync issue: instead
; of CONTROL relying on the V1.61b retry queue (events tied to
; reconnect / IR press) to push preset state down to MAIN, preset is
; now value-bearing in the periodic broadcast — emitted every full-
; sync cycle just like volume / input / mute / cmd1d_setting / standby.
; CONTROL doesn't need feedback from MAIN to confirm preset state —
; broadcasting the intended target every cycle naturally reconciles
; any divergence (post-wake, post-reflash, post-reset, etc.) within
; one cycle, exactly the way volume already works.  The V1.61b
; 0x070/0x071 retry counter machinery is therefore DEAD; the slot
; v171_full_sync_step repurposes 0x070 (see ram.inc rationale).
;
; The V1.6b inter-frame delay_short calls are also dropped — natural
; iteration spacing between full_sync_burst triggers (orders of
; magnitude longer than the 250 µs delay) gives the chain plenty of
; time to drain between frames.
;
; Each step emits via tail-call (goto, not call) into the corresponding
; frame_send helper.  No return overhead, no shared epilogue.
; ===========================================================================
; full_sync_burst:
full_sync_burst:                                               ; address: 0x000b36

        ; --- Advance step (1..6, wrap 6 → 1) ---
        movlb   0x01
        incf    v171_full_sync_step_b1, F, BANKED              ; reg: 0x070
        movlw   0x06
        cpfsgt  v171_full_sync_step_b1, BANKED                 ; if step > 6, fall through to wrap
        bra     v171_fs_step_in_range
        movlw   0x01
        movwf   v171_full_sync_step_b1, BANKED                 ; wrap step → 1

v171_fs_step_in_range:
        ; --- Dispatch on step ---
        ; W ← step (1..6); decrement chain matches the active step.
        movf    v171_full_sync_step_b1, W, BANKED
        movlb   0x00

        addlw   0xFF                                        ; W -= 1; Z if step was 1
        bnz     v171_fs_try_step_2
        goto    volume_frame_send                           ; step 1: volume
v171_fs_try_step_2:
        addlw   0xFF                                        ; Z if step was 2
        bnz     v171_fs_try_step_3
        goto    input_frame_send_split_sync                 ; step 2: input
v171_fs_try_step_3:
        addlw   0xFF                                        ; Z if step was 3
        bnz     v171_fs_try_step_4
        goto    mute_frame_send                             ; step 3: mute
v171_fs_try_step_4:
        addlw   0xFF                                        ; Z if step was 4
        bnz     v171_fs_try_step_5
        goto    cmd1d_setting_frame_send                    ; step 4: cmd1d_setting
v171_fs_try_step_5:
        addlw   0xFF                                        ; Z if step was 5
        bnz     v171_fs_try_step_6
        goto    standby_wake_broadcast                      ; step 5: standby/wake
v171_fs_try_step_6:
        ; Step must be 6 (wrap above clamps to 1..6); emit preset
        ; without persisting to EEPROM (every-cycle broadcast must not
        ; chew through the 100k-write endurance budget).  User-initiated
        ; preset changes still go through v171_send_preset_frame_and_persist.
        goto    v171_send_preset_frame_txonly               ; step 6: preset


; ===========================================================================
; poll_frame_send @ 0x000B64 — poll_frame_send
; ---------------------------------------------------------------------------
; Emits [B1, 04, 00] — addressed status_poll. MAIN's parser treats cmd=0x04
; as the "respond with full status burst" trigger (bypasses the active
; gate, so even MAINs in standby reply). This is the heartbeat used by
; reconnect_wait_loop (reconnect_wait_loop) to test whether MAIN is responding.
; ===========================================================================
; poll_frame_send:
poll_frame_send:                                               ; address: 0x000b64

        ; V1.72 atomic 3-byte frame: reserve ring slots first (partial-
        ; frame hazard for this emitter was low pre-fix since the
        ; callers in WAITING loops are already cyclic, but closing the
        ; hazard uniformly across all 3-byte senders simplifies the
        ; saturation-counter semantics).
        rcall   tx_ring_reserve_3
        bc      poll_frame_send_aborted
        movlw   0xb1                                        ; ROUTE addressed MAIN#1
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movlw   0x04                                        ; CMD status_poll
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        clrf    tx_data_staging_acc, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        return  0x0

poll_frame_send_aborted:
        return  0x0

        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x17
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, saved_settings_base_b0_phys
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x18
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, stock_0C7_b0_phys
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x19
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, stock_0CD_b0_phys
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x1a
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, stock_0D3_b0_phys
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x1b
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, stock_0D9_b0_phys
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x1c
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, stock_0DF_b0_phys
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x1e
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, stock_0E5_b0_phys
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        movf    (Common_RAM + 53), F, A                     ; reg: 0x035
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    poll_frame_send__orphan_unreachable_tail_send_frame                                   ; dest: 0x000c1e
        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        movwf   (Common_RAM + 53), A                        ; reg: 0x035

poll_frame_send__orphan_unreachable_tail_send_frame:                                                  ; address: 0x000c1e

        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0


; ===========================================================================
; input_frame_send @ 0x000C22 — input_frame_send  (V1.6b refactor)
; ---------------------------------------------------------------------------
; Emits legacy [B0, 0x06, <0x0B8>] before PB2 is discovered, and keeps that
; broadcast behavior while PB2 is linked as "Same as PB1".  Independent split
; mode emits addressed PB1 [B1,0x06,<PB1 intent>]; PB2 uses
; input_frame_send_pb2_targeted.  0x0B8 remains PB1 intent and the boot
; handshake sentinel. NOTE: in V1.4 this same address held a
; *channel_17_config* sender — refactor moved to dedicated helpers per cmd in
; V1.5b+.
; ===========================================================================
; input_frame_send:
input_frame_send:                                               ; address: 0x000c22

        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_frame_send_broadcast
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        bra     input_frame_send_pb1_targeted
input_frame_send_broadcast:
        movlb   0x00
        ; V1.72 atomic 3-byte frame (see tx_ring_reserve_3 header).
        rcall   tx_ring_reserve_3
        bc      input_frame_send_aborted
        movlw   0xb0                                        ; ROUTE broadcast CONTROL→MAIN
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movlw   0x06                                        ; CMD input_select
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movff   0x0b8, tx_data_staging_b0_phys                    ; reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        clrf    full_sync_lo_b0, B                                     ; reg: 0x09f
        clrf    full_sync_hi_b0, B                                     ; reg: 0x0a0
        return  0x0

input_frame_send_aborted:
        return  0x0

input_frame_send_pb1_targeted:
        movlb   0x01
        bcf     input_send_target_b1, 0, BANKED
        bra     input_frame_send_targeted

input_frame_send_pb2_targeted:
        movlb   0x01
        bsf     input_send_target_b1, 0, BANKED
        bra     input_frame_send_targeted

input_frame_send_split_sync:
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_frame_send_split_sync_legacy
        btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        bra     input_frame_send_split_sync_legacy
        bcf     input_send_target_b1, 0, BANKED
        btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_SYNC_TARGET, BANKED
        bsf     input_send_target_b1, 0, BANKED
        rcall   input_frame_send_targeted
        bc      input_frame_send_split_sync_done
        movlb   0x01
        btg     input_split_flags_b1, INPUT_SPLIT_FLAG_SYNC_TARGET, BANKED
input_frame_send_split_sync_done:
        movlb   0x00
        return  0x0
input_frame_send_split_sync_legacy:
        movlb   0x00
        goto    input_frame_send

input_frame_send_current_input_page:
        movlb   0x00
        movlw   0x03
        cpfseq  display_state_index_b0, BANKED
        goto    input_frame_send
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        goto    input_frame_send
        btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        goto    input_frame_send
        goto    input_frame_send_pb2_targeted

input_frame_send_targeted:
        movlb   0x00
        call    tx_ring_reserve_3, 0x0
        bc      input_frame_send_targeted_aborted
        movlw   0xB1
        movlb   0x01
        btfsc   input_send_target_b1, 0, BANKED
        movlw   0xB2
        movlb   0x00
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        movlw   0x06
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        movlb   0x01
        btfsc   input_send_target_b1, 0, BANKED
        bra     input_frame_send_targeted_pb2_data
        movlb   0x00
        movf    input_select_cache_b0, W, B
        bra     input_frame_send_targeted_stage_data
input_frame_send_targeted_pb2_data:
        movlw   0x09
        cpfslt  input_intent_pb2_b1, BANKED
        bra     input_frame_send_targeted_pb2_data_clamp
        movf    input_intent_pb2_b1, W, BANKED
        bra     input_frame_send_targeted_stage_data
input_frame_send_targeted_pb2_data_clamp:
        clrf    input_intent_pb2_b1, BANKED
        movlw   0x00
input_frame_send_targeted_stage_data:
        movlb   0x00
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        clrf    full_sync_lo_b0, B
        clrf    full_sync_hi_b0, B
        bcf     STATUS, C, A
        return  0x0
input_frame_send_targeted_aborted:
        movlb   0x00
        return  0x0


; ===========================================================================
; volume_frame_send @ 0x000C40 — volume_frame_send  (V1.6b refactor)
; ---------------------------------------------------------------------------
; Emits [B0, 0x07, <0x0B9>] — broadcast volume.  0x0B9 holds the cached
; current volume byte (with the protocol's 0x60 offset baked in by MAIN
; on its side). Same V1.4→V1.6b refactor pattern as input_frame_send.
; ===========================================================================
; volume_frame_send:
volume_frame_send:                                               ; address: 0x000c40

        ; V1.72 atomic 3-byte frame (see tx_ring_reserve_3 header).
        call    tx_ring_reserve_3, 0x0
        bc      volume_frame_send_aborted
        movlw   0xb0                                        ; ROUTE broadcast CONTROL→MAIN
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movlw   0x07                                        ; CMD volume (offset 0x60)
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movff   0x0b9, tx_data_staging_b0_phys                    ; reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        clrf    full_sync_lo_b0, B                                     ; reg: 0x09f
        clrf    full_sync_hi_b0, B                                     ; reg: 0x0a0
        return  0x0

volume_frame_send_aborted:
        return  0x0


; ===========================================================================
; cmd1d_setting_frame_send @ 0x000C5E — cmd1d_setting_frame_send  (V1.6b refactor)
; ---------------------------------------------------------------------------
; Emits [B0, 0x1D, <0x0A7>] — broadcast the shared cmd0x1D setup byte.
; 0x0A7 is the runtime cache for that byte and also boot handshake sentinel
; #3: it starts at 0x80 and is replaced by MAIN's BF/1D status once the link
; is up. In V1.6b the same cached byte also feeds the local IR/profile helper
; at 0x000F54, so treating it as a generic cmd0x1D setting is safer than
; assuming it is only an LCD timeout.
; ===========================================================================
; cmd1d_setting_frame_send:
cmd1d_setting_frame_send:                                               ; address: 0x000c5e

        ; V1.72 atomic 3-byte frame (see tx_ring_reserve_3 header).
        call    tx_ring_reserve_3, 0x0
        bc      cmd1d_setting_frame_send_aborted
        movlw   0xb0                                        ; ROUTE broadcast CONTROL→MAIN
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movlw   0x1d                                        ; CMD shared_cmd1d_setting (BL timeout / profile)
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movff   0x0a7, tx_data_staging_b0_phys                    ; reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        clrf    full_sync_lo_b0, B                                     ; reg: 0x09f
        clrf    full_sync_hi_b0, B                                     ; reg: 0x0a0
        return  0x0

cmd1d_setting_frame_send_aborted:
        return  0x0

v171_service_rx_frame_gap:
        ; Foreground parser-stall guard.  Keep the parser front-end untouched
        ; and watch for a non-empty frame state that stops receiving bytes.
        movlb   0x00
        movf    rx_frame_position_b0, F, B
        btfsc   STATUS, Z, A
        bra     v171_service_rx_frame_gap_clear
        movf    rx_ring_wr_b0, W, B
        cpfseq  rx_ring_rd_b0, B
        bra     v171_service_rx_frame_gap_reload
        movf    v171_rx_frame_gap_timeout_b0, F, BANKED
        bnz     v171_service_rx_frame_gap_count
        movlw   V171_RX_FRAME_GAP_RELOAD
        movwf   v171_rx_frame_gap_timeout_b0, BANKED
        return  0x0

v171_service_rx_frame_gap_count:
        infsnz  v171_rx_frame_gap_timeout_b0, F, BANKED
        bra     v171_service_rx_frame_gap_expired
        return  0x0

v171_service_rx_frame_gap_reload:
        movlw   V171_RX_FRAME_GAP_RELOAD
        movwf   v171_rx_frame_gap_timeout_b0, BANKED
        return  0x0

v171_service_rx_frame_gap_clear:
        clrf    v171_rx_frame_gap_timeout_b0, BANKED
        return  0x0

v171_service_rx_frame_gap_expired:
        clrf    rx_frame_position_b0, BANKED
        clrf    v171_rx_frame_gap_timeout_b0, BANKED
        return  0x0

; ===========================================================================
; mute_frame_send @ 0x000C7C — mute_frame_send
; ---------------------------------------------------------------------------
; Emits [B0, 0x03, 0x02/0x03] (broadcast mute_on/mute_off) based on
; 0x01F.bit5 (mute_state — the V1.6b new bit position; in V1.4 it lived
; in 0x01F.bit4, but bit4 was repurposed for display_refresh_pending in
; V1.5b+). Same cmd byte as standby/wake; data discriminates.
; ===========================================================================
; mute_frame_send:
mute_frame_send:                                               ; address: 0x000c7c

        clrf    (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        btfss   control_flags_acc, 0x5, A                   ; reg: 0x01f
        goto    mute_frame_send__stage_mute_off_data                                   ; dest: 0x000c90
        movlw   0x02
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        goto    mute_frame_send__send_staged_frame                                   ; dest: 0x000c94

mute_frame_send__stage_mute_off_data:                                                  ; address: 0x000c90

        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        movwf   (Common_RAM + 53), A                        ; reg: 0x035

mute_frame_send__send_staged_frame:                                                  ; address: 0x000c94

        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0


; ===========================================================================
; V1.73 BUG-V34V173 helper trio (exploratory-bug fixes)
; ---------------------------------------------------------------------------
; v173_volume_clear_mute_notify (BUG-1): the volume keys clear local mute so
;   the LCD renders the volume instead of "Mute"; the chain must hear the
;   same fact explicitly.  On a real mute->unmute transition emit B0/03/03
;   via mute_frame_send (the same atomic-ring sender the mute key already
;   uses from this foreground context).  MAIN V3.4 treats cmd 0x03 as the
;   SOLE mute authority, so the volume frame alone no longer implies unmute
;   -- and a held volume key keeps resetting the full-sync counter, so the
;   periodic mute step alone could be postponed indefinitely.
; v173_waiting_ir_service (BUG-2): the WAITING loops never ran the
;   foreground IR dispatcher, so a frame captured by the IR ISR left
;   IR_ARMED clear forever (IR dead).  Consume-and-re-arm (discard) --
;   dispatching from WAITING is unsafe: IR vol-down would corrupt the 0x80
;   volume boot sentinel during cold WAITING, and the IR standby arm
;   toggles control_flags.bit1, which the WAITING/reconnect flow owns.
; v173_preset_lcd_invalidate (BUG-3): every transition that overlays the
;   Preset page must drop row-0 readiness AND the filename cache (the USB
;   host can rewrite MAIN's stored filename while CONTROL is away), exactly
;   like the normal Preset exit does.  Row 1 stays suppressed until Preset
;   entry repaints the full row-0 title.
; ===========================================================================
v173_volume_clear_mute_notify:
        btfss   control_flags_acc, 0x5, A          ; muted now?
        return  0x0                                ; no -> no extra chain traffic
        bcf     control_flags_acc, 0x5, A          ; local unmute (LCD shows volume)
        goto    mute_frame_send                    ; tail-call: emits B0/03/03

v173_waiting_ir_service:
        btfsc   control_flags_acc, IR_ARMED, A     ; armed -> no pending frame
        return  0x0
        bsf     control_flags_acc, IR_ARMED, A     ; discard frame, re-arm decoder
        return  0x0

v173_preset_lcd_invalidate:
        movlb   0x02
        bsf     v172_fname_row0_status_snap_b2, FNAME_ROW0_NOT_READY, BANKED
        bcf     v172_fname_flags_b2, FNAME_VALID, BANKED
        movlb   0x00
        return  0x0

v173_preset_row0_paint:
        ; FIELD-3: paint Preset row 0 ("Preset" + spaces), seed the status
        ; snap, patch cols 14/15, and mark row 0 ready.  Factored from
        ; v171_prs_screen_draw_body so the per-pass filename service can
        ; SELF-HEAL after any full LCD clear (the post-wake standby-path
        ; bounce blanks the LCD after the entry draw ran).  Enter any bank;
        ; exit BSR=0.
        ; Row 0: "Preset          " (16 characters)
        movlw   0x80
        movwf   (Common_RAM + 1), A
        movlw   0x80                                       ; LCD cursor row 0 col 0
        call    lcd_command, 0x0
        movlw   'P'
        call    lcd_char_write, 0x0
        movlw   'r'
        call    lcd_char_write, 0x0
        movlw   'e'
        call    lcd_char_write, 0x0
        movlw   's'
        call    lcd_char_write, 0x0
        movlw   'e'
        call    lcd_char_write, 0x0
        movlw   't'
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0

        ; Row 0 live status cells: col14 health glyph, col15 A/B/!.
        ; Seed snap invalid so two bounded status patch calls paint both cells.
        movlb   0x02
        movlw   0xFF
        movwf   v172_fname_row0_status_snap_b2, BANKED
        movlb   0x00
        call    v172_preset_status_patch_service, 0x0
        call    v172_preset_status_patch_service, 0x0
        movlb   0x02
        bcf     v172_fname_row0_status_snap_b2, FNAME_ROW0_NOT_READY, BANKED
        movlb   0x00
        return  0x0


; ===========================================================================
; standby_wake_broadcast @ 0x000C98 — standby_wake_broadcast
; ---------------------------------------------------------------------------
; THIS IS THE WAKE/STANDBY ROUTE THAT V1.62b RECONNECT BUG TARGETED.
; Emits [B0, 0x03, 0/1] — broadcast standby_enter or wake based on
; 0x01F.bit1 (connected) at call time:
;    bit1 SET (DISPLAY mode)  → data = 0x01 (wake) — opens MAIN's gate
;    bit1 CLEAR (Zzz mode)    → data = 0x00 (standby) — closes the gate
;
; Stock V1.6b calls this from 0x001294 (the line right before reconnect_wait_loop)
; after the user releases STBY, ensuring every MAIN reopens its
; active_flags.bit3. The V1.62b reconnect_wait_stub initially OMITTED
; this call, leaving MAINs deaf to all subsequent volume/mute/preset
; commands until power cycle (V162B_RECONNECT_WAKE_BUG.md). The fix:
; explicit `call 0x000C98` after `bsf 0x01F, 1` in reconnect_wait_done.
; ===========================================================================
; standby_wake_broadcast:
standby_wake_broadcast:                                               ; address: 0x000c98

        clrf    (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        btfsc   control_flags_acc, 0x1, A                   ; reg: 0x01f
        goto    standby_wake_broadcast__emit_wake_data                                   ; dest: 0x000caa
        clrf    (Common_RAM + 53), A                        ; reg: 0x035
        goto    standby_wake_broadcast__send_frame                                   ; dest: 0x000cae

standby_wake_broadcast__emit_wake_data:                                                  ; address: 0x000caa

        movlw   0x01
        movwf   (Common_RAM + 53), A                        ; reg: 0x035

standby_wake_broadcast__send_frame:                                                  ; address: 0x000cae

        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        bc      standby_wake_broadcast_aborted
        return  0x0

standby_wake_broadcast_aborted:
        return  0x0


; ===========================================================================
; display_loop_iteration @ 0x000CB2 — display_loop_iteration   (V1.6b refactor)
; ---------------------------------------------------------------------------
; One iteration of the display/menu loop. Steps:
;   1. Set INTCON3.RBIE (PIE for button RBIF).
;   2. Call button_scan_debounce (button_scan_debounce @ 0x0008AC) — reads the
;      6 button GPIOs, debounces (threshold 4 stable samples), updates
;      0x0BE (button_debounced).
;   3. Call rx_parser_entry (rx_parser_entry @ 0x00044A) — drain RX ring.
;   4. Decrement 16-bit idle_timeout_counter at 0x09D:0x09E (init 0xEA61
;      = ~60 k iterations). When it crosses zero AND we are still in
;      DISPLAY mode, the panel transitions to standby ("Zzz...").
;   5. Decrement 16-bit full_sync_counter at 0x09F:0x0A0 (init 0x4E20).
;      When it overflows, calls full_sync_burst (full_sync_burst — BUG C7).
; This routine is the periodic "while not in event loop" handler called
; from the main display path.
; ===========================================================================
; display_loop_iteration:
;@routine display_loop_iteration entry_bsr=unknown exit_bsr=0
display_loop_iteration:                                               ; address: 0x000cb2

        bsf     INTCON, RBIE, A                             ; reg: 0xff2, bit: 3

display_loop_iteration__service_tick:                                                  ; address: 0x000cb4

        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        ; Live IR decoding is the stock-compatible RBIF ISR path:
        ; isr_entry calls ir_rc5_decode directly and stores cmd/address.
        ; Retired foreground/Timer1 experimental services stay uncalled.
        movlb   0x00
        call    rx_parser_entry, 0x0                           ; dest: 0x00044a
        call    v171_service_rx_frame_gap, 0x0                     ; legacy-link parser stall guard
        call    v171_health_service, 0x0                          ; link-health ping/age tick
        call    input_split_latch_pb2_seen, 0x0                   ; runtime PB2 input-page enable
        call    v172_preset_filename_service, 0x0                 ; Preset filename query/timeout/LCD tick
        call    v171_health_patch_suffix, 0x0                     ; top-level LCD row-2 suffix
        movf    idle_timeout_hi_b0, W, B                                  ; reg: 0x09e
        xorlw   0xea
        movlw   0x60
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        xorwf   idle_timeout_lo_b0, W, B                                  ; reg: 0x09d
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    display_loop_iteration__tick_idle_timer                                   ; dest: 0x000cce
        rcall   settings_save_eeprom                                ; dest: 0x000990

display_loop_iteration__tick_idle_timer:                                                  ; address: 0x000cce

        movlw   0x61
        subwf   idle_timeout_lo_b0, W, B                                  ; reg: 0x09d
        movlw   0xea
        subwfb  idle_timeout_hi_b0, W, B                                  ; reg: 0x09e
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    display_loop_iteration__service_full_sync_timer                                   ; dest: 0x000ce0
        infsnz  idle_timeout_lo_b0, F, B                                  ; reg: 0x09d
        incf    idle_timeout_hi_b0, F, B                                  ; reg: 0x09e

display_loop_iteration__service_full_sync_timer:                                                  ; address: 0x000ce0

        call    ir_dispatch_configured_or_fixed_shortcuts, 0x0                           ; dest: 0x000dce
        movf    full_sync_hi_b0, W, B                                  ; reg: 0x0a0
        xorlw   0x4e
        movlw   0x20
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        xorwf   full_sync_lo_b0, W, B                                  ; reg: 0x09f
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    display_loop_iteration__tick_full_sync_timer                                   ; dest: 0x000cfe
        rcall   full_sync_burst                                ; dest: 0x000b36
        clrf    full_sync_lo_b0, B                                     ; reg: 0x09f
        clrf    full_sync_hi_b0, B                                     ; reg: 0x0a0
        goto    display_loop_iteration__select_connected_backlight_path                                   ; dest: 0x000d02

display_loop_iteration__tick_full_sync_timer:                                                  ; address: 0x000cfe

        infsnz  full_sync_lo_b0, F, B                                  ; reg: 0x09f
        incf    full_sync_hi_b0, F, B                                  ; reg: 0x0a0

display_loop_iteration__select_connected_backlight_path:                                                  ; address: 0x000d02

        btfsc   control_flags_acc, 0x1, A                   ; reg: 0x01f
        goto    display_loop_iteration__service_backlight_timeout                                   ; dest: 0x000d10
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bcf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        goto    display_loop_iteration__modal_wait_predicates                                   ; dest: 0x000d7a

display_loop_iteration__service_backlight_timeout:                                                  ; address: 0x000d10

        movf    backlight_timeout_selection_b0, F, B                                  ; reg: 0x0eb
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    display_loop_iteration__drive_backlight_on_no_timeout                                   ; dest: 0x000d76
        movf    backlight_timeout_threshold_lo_b0, W, B                                  ; reg: 0x0ec
        subwf   backlight_elapsed_lo_b0, W, B                                  ; reg: 0x0b0
        movf    backlight_timeout_threshold_mid_lo_b0, W, B                                  ; reg: 0x0ed
        subwfb  backlight_elapsed_mid_lo_b0, W, B                                  ; reg: 0x0b1
        movf    backlight_timeout_threshold_mid_hi_b0, W, B                                  ; reg: 0x0ee
        subwfb  backlight_elapsed_mid_hi_b0, W, B                                  ; reg: 0x0b2
        movf    backlight_timeout_threshold_hi_b0, W, B                                  ; reg: 0x0ef
        subwfb  backlight_elapsed_hi_b0, W, B                                  ; reg: 0x0b3
        movf    backlight_elapsed_hi_b0, W, B                                  ; reg: 0x0b3
        xorwf   backlight_timeout_threshold_hi_b0, W, B                                  ; reg: 0x0ef
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        xorlw   0x80
        btfss   STATUS, N, A                                ; reg: 0xfd8, bit: 4
        goto    display_loop_iteration__service_muted_backlight_blink                                   ; dest: 0x000d3e
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bcf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        goto    display_loop_iteration__enter_modal_wait_predicates                                   ; dest: 0x000d72

display_loop_iteration__service_muted_backlight_blink:                                                  ; address: 0x000d3e

        btfss   control_flags_acc, 0x5, A                   ; reg: 0x01f
        goto    display_loop_iteration__drive_backlight_on                                   ; dest: 0x000d64
        infsnz  mute_blink_counter_lo_b0, F, B                                  ; reg: 0x0b4
        incf    mute_blink_counter_hi_b0, F, B                                  ; reg: 0x0b5
        movf    mute_blink_counter_hi_b0, W, B                                  ; reg: 0x0b5
        xorlw   0x75
        movlw   0x30
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        xorwf   mute_blink_counter_lo_b0, W, B                                  ; reg: 0x0b4
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    display_loop_iteration__after_mute_blink_tick                                   ; dest: 0x000d60
        btg     PORTC, RC1, A                               ; reg: 0xf82, bit: 1
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        clrf    mute_blink_counter_lo_b0, B                                     ; reg: 0x0b4
        clrf    mute_blink_counter_hi_b0, B                                     ; reg: 0x0b5

display_loop_iteration__after_mute_blink_tick:                                                  ; address: 0x000d60

        goto    display_loop_iteration__tick_backlight_elapsed                                   ; dest: 0x000d68

display_loop_iteration__drive_backlight_on:                                                  ; address: 0x000d64

        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bsf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1

display_loop_iteration__tick_backlight_elapsed:                                                  ; address: 0x000d68

        incf    backlight_elapsed_lo_b0, F, B                                  ; reg: 0x0b0
        movlw   0x00
        addwfc  backlight_elapsed_mid_lo_b0, F, B                                  ; reg: 0x0b1
        addwfc  backlight_elapsed_mid_hi_b0, F, B                                  ; reg: 0x0b2
        addwfc  backlight_elapsed_hi_b0, F, B                                  ; reg: 0x0b3

display_loop_iteration__enter_modal_wait_predicates:                                                  ; address: 0x000d72

        goto    display_loop_iteration__modal_wait_predicates                                   ; dest: 0x000d7a

display_loop_iteration__drive_backlight_on_no_timeout:                                                  ; address: 0x000d76

        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bsf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1

display_loop_iteration__modal_wait_predicates:                                                  ; address: 0x000d7a

        movlw   0x00
        movf    button_event_latch_b0, F, B                                  ; reg: 0x09a
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   control_flags_acc, 0x3, A                   ; reg: 0x01f
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        ; Input PB2 uses the health dirty bit to redraw its title as
        ; "old"/"lost" while parked in display_loop_iteration.  Keep this
        ; predicate state-specific so ordinary menu pages stay stock-like.
        movlb   0x00
        movlw   0x03
        cpfseq  display_state_index_b0, BANKED
        bra     display_loop_iteration__modal_predicate_ready
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     display_loop_iteration__modal_predicate_ready_b0
        movlb   0x01
        btfss   v171_health_flags_b1, V171_HEALTH_FLAG_DISPLAY_DIRTY, BANKED
        bra     display_loop_iteration__modal_predicate_ready_b0
        movlb   0x00
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A
        bra     display_loop_iteration__modal_predicate_ready
display_loop_iteration__modal_predicate_ready_b0:
        movlb   0x00
display_loop_iteration__modal_predicate_ready:
        movf    (Common_RAM + 24), F, A
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     display_loop_iteration__service_tick                                   ; dest: 0x000cb4
        movlw   0x00
        movf    button_event_latch_b0, F, B                                  ; reg: 0x09a
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   control_flags_acc, 0x4, A                   ; reg: 0x01f
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    display_loop_iteration__handle_standby_toggle                                   ; dest: 0x000db0
        clrf    backlight_elapsed_hi_b0, B                                     ; reg: 0x0b3
        clrf    backlight_elapsed_mid_hi_b0, B                                     ; reg: 0x0b2
        clrf    backlight_elapsed_mid_lo_b0, B                                     ; reg: 0x0b1
        clrf    backlight_elapsed_lo_b0, B                                     ; reg: 0x0b0

display_loop_iteration__handle_standby_toggle:                                                  ; address: 0x000db0

        bcf     control_flags_acc, 0x4, A                   ; reg: 0x01f
        rrcf    button_event_latch_b0, W, B                                  ; reg: 0x09a
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    display_loop_iteration__clear_idle_and_return                                   ; dest: 0x000dc8
        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   button_event_latch_b0, 0x0, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    display_loop_iteration__clear_idle_and_return                                   ; dest: 0x000dc8
        btg     control_flags_acc, 0x1, A                   ; reg: 0x01f

display_loop_iteration__clear_idle_and_return:                                                  ; address: 0x000dc8

        clrf    idle_timeout_lo_b0, B                                     ; reg: 0x09d
        clrf    idle_timeout_hi_b0, B                                     ; reg: 0x09e
        return  0x0

ir_dispatch_configured_or_fixed_shortcuts:                                               ; address: 0x000dce

        movf    (Common_RAM + 27), F, A                     ; reg: 0x01b
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    ir_dispatch_configured_or_fixed_shortcuts__decrement_inhibit_timer                                   ; dest: 0x000dde
        movf    (Common_RAM + 28), F, A                     ; reg: 0x01c
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    ir_dispatch_configured_or_fixed_shortcuts__gate_on_ir_armed_flag                                   ; dest: 0x000de4

ir_dispatch_configured_or_fixed_shortcuts__decrement_inhibit_timer:                                                  ; address: 0x000dde

        decf    (Common_RAM + 27), F, A                     ; reg: 0x01b
        movlw   0x00
        subwfb  (Common_RAM + 28), F, A                     ; reg: 0x01c

ir_dispatch_configured_or_fixed_shortcuts__gate_on_ir_armed_flag:                                                  ; address: 0x000de4

        btfss   control_flags_acc, 0x0, A                   ; reg: 0x01f
        goto    ir_dispatch_configured_or_fixed_shortcuts__match_configured_codes                                   ; dest: 0x000dec
        return  0x0

ir_dispatch_configured_or_fixed_shortcuts__match_configured_codes:                                                  ; address: 0x000dec

        movf    ir_decoded_addr_acc, W, A                     ; reg: 0x01e
        cpfseq  (Common_RAM + 32), A                        ; reg: 0x020
        goto    ir_dispatch_configured_or_fixed_shortcuts__stock_rearm_fallthrough
        movf    ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 33), A                        ; reg: 0x021
        goto    ir_dispatch_configured_or_fixed_shortcuts__check_volume_up_code                                   ; dest: 0x000e0c
        movlw   0x50
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0xc3
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        btg     control_flags_acc, 0x1, A                   ; reg: 0x01f
        bsf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        goto    ir_dispatch_configured_or_fixed_shortcuts__stock_rearm_fallthrough

ir_dispatch_configured_or_fixed_shortcuts__check_volume_up_code:                                                  ; address: 0x000e0c

        movf    ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 34), A                        ; reg: 0x022
        goto    ir_dispatch_configured_or_fixed_shortcuts__check_volume_down_code                                   ; dest: 0x000e32
        movlw   0xd0
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0x07
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        movlw   0x72
        cpfslt  volume_cache_b0, B                                     ; reg: 0x0b9
        goto    ir_dispatch_configured_or_fixed_shortcuts__volume_up_done                                   ; dest: 0x000e2e
        incf    volume_cache_b0, F, B                                  ; reg: 0x0b9
        call    v173_volume_clear_mute_notify, 0x0    ; BUG-1: explicit B0/03/03 on mute->unmute
        rcall   volume_frame_send                                ; dest: 0x000c40
        bsf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        bsf     control_flags_acc, 0x4, A                   ; reg: 0x01f

ir_dispatch_configured_or_fixed_shortcuts__volume_up_done:                                                  ; address: 0x000e2e

        goto    ir_dispatch_configured_or_fixed_shortcuts__stock_rearm_fallthrough

ir_dispatch_configured_or_fixed_shortcuts__check_volume_down_code:                                                  ; address: 0x000e32

        movf    ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 35), A                        ; reg: 0x023
        goto    ir_dispatch_configured_or_fixed_shortcuts__check_mute_toggle_code                                   ; dest: 0x000e58
        movlw   0xd0
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0x07
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        movf    volume_cache_b0, F, B                                  ; reg: 0x0b9
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    ir_dispatch_configured_or_fixed_shortcuts__volume_down_done                                   ; dest: 0x000e54
        decf    volume_cache_b0, F, B                                  ; reg: 0x0b9
        call    v173_volume_clear_mute_notify, 0x0    ; BUG-1: explicit B0/03/03 on mute->unmute
        rcall   volume_frame_send                                ; dest: 0x000c40
        bsf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        bsf     control_flags_acc, 0x4, A                   ; reg: 0x01f

ir_dispatch_configured_or_fixed_shortcuts__volume_down_done:                                                  ; address: 0x000e54

        goto    ir_dispatch_configured_or_fixed_shortcuts__stock_rearm_fallthrough

ir_dispatch_configured_or_fixed_shortcuts__check_mute_toggle_code:                                                  ; address: 0x000e58

        movf    ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 38), A                        ; reg: 0x026
        goto    ir_dispatch_configured_or_fixed_shortcuts__check_input_previous_code                                   ; dest: 0x000e7c
        movlw   0x2f
        movwf   mute_blink_counter_lo_b0, B                                     ; reg: 0x0b4
        movlw   0x75
        movwf   mute_blink_counter_hi_b0, B                                     ; reg: 0x0b5
        btg     control_flags_acc, 0x5, A                   ; reg: 0x01f
        movlw   0x20
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0x4e
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        bsf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        bsf     control_flags_acc, 0x4, A                   ; reg: 0x01f
        rcall   mute_frame_send                                ; dest: 0x000c7c
        goto    ir_dispatch_configured_or_fixed_shortcuts__stock_rearm_fallthrough

ir_dispatch_configured_or_fixed_shortcuts__check_input_previous_code:                                                  ; address: 0x000e7c

        movf    ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 37), A                        ; reg: 0x025
        goto    ir_dispatch_configured_or_fixed_shortcuts__check_input_next_code                                   ; dest: 0x000ee6
        movf    raw_status_cache_b0, F, B                                  ; reg: 0x0a1
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_previous_limit_for_status_one                                   ; dest: 0x000e94
        movlw   0x05                                        ; CMD raw_status (MAIN→CONTROL echo)
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_previous_wrap_or_decrement                                   ; dest: 0x000ebe

ir_dispatch_configured_or_fixed_shortcuts__input_previous_limit_for_status_one:                                                  ; address: 0x000e94

        decfsz  raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_previous_limit_for_status_two                                   ; dest: 0x000ea2
        movlw   0x06                                        ; CMD input_select
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_previous_wrap_or_decrement                                   ; dest: 0x000ebe

ir_dispatch_configured_or_fixed_shortcuts__input_previous_limit_for_status_two:                                                  ; address: 0x000ea2

        movlw   0x02
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_previous_limit_for_status_three                                   ; dest: 0x000eb2
        movlw   0x07                                        ; CMD volume (offset 0x60)
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_previous_wrap_or_decrement                                   ; dest: 0x000ebe

ir_dispatch_configured_or_fixed_shortcuts__input_previous_limit_for_status_three:                                                  ; address: 0x000eb2

        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_previous_limit_unknown_full
        movlw   0x08                                        ; CMD dsp_fault (V1.63b+ BF/08 payload)
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_previous_wrap_or_decrement

ir_dispatch_configured_or_fixed_shortcuts__input_previous_limit_unknown_full:
        movlw   0x08
        movwf   tx_data_staging_acc, A

ir_dispatch_configured_or_fixed_shortcuts__input_previous_wrap_or_decrement:                                                  ; address: 0x000ebe

        movf    rx_ring_staging_b0, F, B                                  ; reg: 0x0b7
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_previous_wrap_to_limit                                   ; dest: 0x000ecc
        decf    rx_ring_staging_b0, F, B                                  ; reg: 0x0b7
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_previous_emit_frame                                   ; dest: 0x000ed0

ir_dispatch_configured_or_fixed_shortcuts__input_previous_wrap_to_limit:                                                  ; address: 0x000ecc

        movff   tx_data_staging_b0_phys, 0x0b7                    ; reg1: 0x027

ir_dispatch_configured_or_fixed_shortcuts__input_previous_emit_frame:                                                  ; address: 0x000ed0

        bsf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        bsf     control_flags_acc, 0x4, A                   ; reg: 0x01f
        movlw   0x58
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0x1b                                        ; CMD channel_src_5
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        call    map_input_menu_index_to_cmd06_input_select, 0x0                           ; dest: 0x00076a
        movff   tx_data_staging_b0_phys, input_select_cache_b0_phys
        rcall   input_frame_send                                ; dest: 0x000c22
        goto    ir_dispatch_configured_or_fixed_shortcuts__stock_rearm_fallthrough

ir_dispatch_configured_or_fixed_shortcuts__check_input_next_code:                                                  ; address: 0x000ee6

        movf    ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 36), A                        ; reg: 0x024
        goto    ir_dispatch_configured_or_fixed_shortcuts__post_configured_fixed_shortcut_probe
        movf    raw_status_cache_b0, F, B                                  ; reg: 0x0a1
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_next_limit_for_status_one                                   ; dest: 0x000efe
        movlw   0x05                                        ; CMD raw_status (MAIN→CONTROL echo)
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_next_wrap_or_increment                                   ; dest: 0x000f28

ir_dispatch_configured_or_fixed_shortcuts__input_next_limit_for_status_one:                                                  ; address: 0x000efe

        decfsz  raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_next_limit_for_status_two                                   ; dest: 0x000f0c
        movlw   0x06                                        ; CMD input_select
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_next_wrap_or_increment                                   ; dest: 0x000f28

ir_dispatch_configured_or_fixed_shortcuts__input_next_limit_for_status_two:                                                  ; address: 0x000f0c

        movlw   0x02
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_next_limit_for_status_three                                   ; dest: 0x000f1c
        movlw   0x07                                        ; CMD volume (offset 0x60)
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_next_wrap_or_increment                                   ; dest: 0x000f28

ir_dispatch_configured_or_fixed_shortcuts__input_next_limit_for_status_three:                                                  ; address: 0x000f1c

        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_next_limit_unknown_full
        movlw   0x08                                        ; CMD dsp_fault (V1.63b+ BF/08 payload)
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_next_wrap_or_increment

ir_dispatch_configured_or_fixed_shortcuts__input_next_limit_unknown_full:
        movlw   0x08
        movwf   tx_data_staging_acc, A

ir_dispatch_configured_or_fixed_shortcuts__input_next_wrap_or_increment:                                                  ; address: 0x000f28

        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        cpfslt  rx_ring_staging_b0, B                                     ; reg: 0x0b7
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_next_wrap_to_zero                                   ; dest: 0x000f36
        incf    rx_ring_staging_b0, F, B                                  ; reg: 0x0b7
        goto    ir_dispatch_configured_or_fixed_shortcuts__input_next_emit_frame                                   ; dest: 0x000f38

ir_dispatch_configured_or_fixed_shortcuts__input_next_wrap_to_zero:                                                  ; address: 0x000f36

        clrf    rx_ring_staging_b0, B                                     ; reg: 0x0b7

ir_dispatch_configured_or_fixed_shortcuts__input_next_emit_frame:                                                  ; address: 0x000f38

        bsf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        bsf     control_flags_acc, 0x4, A                   ; reg: 0x01f
        movlw   0x58
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0x1b                                        ; CMD channel_src_5
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        call    map_input_menu_index_to_cmd06_input_select, 0x0                           ; dest: 0x00076a
        movff   tx_data_staging_b0_phys, input_select_cache_b0_phys
        rcall   input_frame_send                                ; dest: 0x000c22
        goto    ir_dispatch_configured_or_fixed_shortcuts__stock_rearm_fallthrough

ir_dispatch_configured_or_fixed_shortcuts__stock_rearm_fallthrough:                                                  ; stock IR dispatch fallthrough #1

        bsf     control_flags_acc, IR_ARMED, A              ; reg: 0x01f
        return  0x0

ir_dispatch_configured_or_fixed_shortcuts__post_configured_fixed_shortcut_probe:                                                  ; stock IR dispatch exit (no stock case matched)

        ; ---------------------------------------------------------------
        ; V1.72 inline (V1.61b + V1.64b): preset + standby/wake IR shortcuts
        ; ---------------------------------------------------------------
        ; The stock IR dispatch reaches this label when ir_decoded_cmd
        ; did not match any of the menu-configured IR codes stored in
        ; RAM(0x21..0x26).  V1.72 adds four fixed IR shortcuts on top:
        ;
        ;   RC5 0x38 → preset A   (V1.61b)
        ;   RC5 0x39 → preset B   (V1.61b)
        ;   RC5 0x3A → standby    (V1.64b explicit-standby endpoint)
        ;   RC5 0x3B → wake       (V1.64b explicit-wake endpoint)
        ;   RC5 0x3D → preset toggle A/B
        ;   RC5 0x3F → PB1 S/PDIF/Optical toggle
        ;
        ; Fixed shortcuts run only for configured-address commands that
        ; missed every menu-configured IR code stored in RAM(0x21..0x26).
        ; Any other unmapped code falls through to the stock re-arm path.
        movf    ir_decoded_cmd_acc, W, A
        xorlw   RC5_PRESET_A                             ; 0x38
        bz      v171_ir_preset_a_case
        movf    ir_decoded_cmd_acc, W, A
        xorlw   RC5_PRESET_B                             ; 0x39
        bz      v171_ir_preset_b_case
        movf    ir_decoded_cmd_acc, W, A
        xorlw   RC5_STANDBY_ENTER                        ; 0x3A
        bz      v171_ir_standby_case
        movf    ir_decoded_cmd_acc, W, A
        xorlw   RC5_WAKE                                 ; 0x3B
        bz      v171_ir_wake_case
        movf    ir_decoded_cmd_acc, W, A
        xorlw   RC5_PRESET_TOGGLE                        ; 0x3D
        bz      v173_ir_preset_toggle_case
        movf    ir_decoded_cmd_acc, W, A
        xorlw   RC5_INPUT_OPTICAL_SPDIF_TOGGLE           ; 0x3F
        bz      v173_ir_input_optical_spdif_toggle_case
        ; Not a V1.72 shortcut — standard re-arm + return.
        bsf     control_flags_acc, IR_ARMED, A
        return  0x0

v173_ir_preset_toggle_case:
        btfsc   control_flags_acc, PRESET_BIT, A             ; B -> A
        bra     v171_ir_preset_a_case
        bra     v171_ir_preset_b_case                        ; A -> B

v173_ir_input_optical_spdif_toggle_case:
        movlb   0x00
        movlw   0x08
        cpfseq  input_select_cache_b0, BANKED                ; Optical?
        bra     v173_ir_input_toggle_select_optical
        movlw   0x05                                        ; Optical -> S/PDIF
        bra     v173_ir_input_toggle_stage
v173_ir_input_toggle_select_optical:
        movlw   0x08                                        ; anything else -> Optical
v173_ir_input_toggle_stage:
        movwf   rx_parsed_data_acc, A
        call    map_cmd06_input_select_to_menu_index, 0x0
        movff   rx_parsed_data_b0_phys, input_select_cache_b0_phys
        bsf     control_flags_acc, 0x3, A                    ; event_exit
        bsf     control_flags_acc, 0x4, A                    ; display redraw
        movlw   0x58
        movwf   (Common_RAM + 27), A
        movlw   0x1b                                        ; stock input IR inhibit
        movwf   (Common_RAM + 28), A
        rcall   input_frame_send
        bsf     control_flags_acc, IR_ARMED, A
        return  0x0

v171_ir_preset_a_case:
        btfss   control_flags_acc, PRESET_BIT, A             ; already A?
        bra     v171_ir_preset_done                      ; yes — skip emit
        bcf     control_flags_acc, PRESET_BIT, A             ; 0 = preset A
        rcall   v171_send_preset_frame_and_persist
        bc      v171_ir_preset_a_abort
        bsf     control_flags_acc, 0x3, A                    ; event_exit
        bra     v171_ir_preset_done
v171_ir_preset_a_abort:
        bsf     control_flags_acc, PRESET_BIT, A             ; restore B if TX/EEPROM aborted
        bra     v171_ir_preset_done

v171_ir_preset_b_case:
        btfsc   control_flags_acc, PRESET_BIT, A             ; already B?
        bra     v171_ir_preset_done
        bsf     control_flags_acc, PRESET_BIT, A             ; 1 = preset B
        rcall   v171_send_preset_frame_and_persist
        bc      v171_ir_preset_b_abort
        bsf     control_flags_acc, 0x3, A                    ; event_exit
        bra     v171_ir_preset_done
v171_ir_preset_b_abort:
        bcf     control_flags_acc, PRESET_BIT, A             ; restore A if TX/EEPROM aborted

v171_ir_preset_done:
        bsf     control_flags_acc, IR_ARMED, A
        return  0x0

v171_ir_standby_case:
        ; V1.64b explicit standby (RC5 0x3A): emit [B0, 0x03, 0x00]
        ; and set event_exit.  Unlike the RC5 power-toggle (stock 0x32)
        ; this endpoint forces standby regardless of current state.
        rcall   v171_send_standby_cmd_frame
        bc      v171_ir_endpoint_done
        bcf     control_flags_acc, 0x1, A                    ; local UI state = standby
        bsf     control_flags_acc, 0x3, A                    ; event_exit
        bra     v171_ir_endpoint_done

v171_ir_wake_case:
        ; V1.64b explicit wake (RC5 0x3B): emit [B0, 0x03, 0x01] and
        ; set event_exit.  Forces wake regardless of current state.
        rcall   v171_send_wake_cmd_frame
        bc      v171_ir_endpoint_done
        bsf     control_flags_acc, 0x1, A                    ; local UI state = awake
        bsf     control_flags_acc, 0x3, A                    ; event_exit

v171_ir_endpoint_done:
        bsf     control_flags_acc, IR_ARMED, A
        return  0x0

v171_send_standby_cmd_frame:
        ; Emit [0xB0, 0x03, 0x00] — broadcast CMD standby/wake with
        ; data = 0 (standby).  V1.72 atomic: either all 3 bytes commit
        ; or none do (see tx_ring_reserve_3 header for rationale).  On
        ; saturation, returns C=1 with zero bytes on the wire — MAIN
        ; cannot observe a partial frame.
        ; `call` (not `rcall`) because tx_ring_reserve_3 lives in the
        ; low-address helper cluster and is outside ±1024-word range.
        call    tx_ring_reserve_3, 0x0
        bc      v171_send_standby_cmd_frame_aborted
        movlw   0xB0
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        movlw   0x03
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        clrf    tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        return  0x0

v171_send_standby_cmd_frame_aborted:
        return  0x0

v171_send_wake_cmd_frame:
        ; Emit [0xB0, 0x03, 0x01] — broadcast CMD standby/wake with
        ; data = 1 (wake).  V1.72 atomic; see v171_send_standby_cmd_frame
        ; comment.  `call` for the same range reason as the standby
        ; sibling above.
        call    tx_ring_reserve_3, 0x0
        bc      v171_send_wake_cmd_frame_aborted
        movlw   0xB0
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        movlw   0x03
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        movlw   0x01
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        return  0x0

v171_send_wake_cmd_frame_aborted:
        return  0x0

v171_send_preset_frame_txonly:
        ; ---------------------------------------------------------------
        ; V1.72 Layer 2 helper: emit [B0, 0x20, preset_byte] only, NO
        ; EEPROM write.  preset_byte = 0 when PRESET_BIT clear (A),
        ; 1 when set (B).  Used by full_sync_burst's periodic emit so
        ; broadcasting preset every full-sync cycle does NOT chew
        ; through the EEPROM endurance budget (~100k writes/cell).
        ;
        ; V1.72 atomic: either all 3 bytes commit or none (partial
        ; frames cannot fuse the next unrelated TX byte as "data").
        ; `call` (not `rcall`) because this helper lives in the far
        ; V1.72 inline-feature cluster, outside rcall range of
        ; tx_ring_reserve_3.
        ; ---------------------------------------------------------------
        call    tx_ring_reserve_3, 0x0
        bc      v171_send_preset_frame_txonly_aborted
        movlw   0xB0                                     ; ROUTE broadcast CONTROL→MAIN
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        movlw   0x20                                     ; CMD preset_select
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        clrf    WREG, A
        btfsc   control_flags_acc, PRESET_BIT, A
        movlw   0x01
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        return  0x0

v171_send_preset_frame_txonly_aborted:
        return  0x0

v171_send_preset_frame_and_persist:
        ; ---------------------------------------------------------------
        ; V1.72 inline helper: emit [B0, 0x20, preset_byte] AND persist
        ; preset state byte to EEPROM slot 0x74.  Used by user-initiated
        ; paths (IR press, front-panel U/D in preset menu) where we
        ; want the new state to survive a power cycle.  Periodic
        ; broadcasts must use v171_send_preset_frame_txonly instead.
        ; ---------------------------------------------------------------
        rcall   v171_send_preset_frame_txonly
        bc      v171_send_preset_frame_and_persist_aborted
        movlw   EEPROM_PRESET_STATE_ADDR                 ; 0x74
        movwf   EEADR, A
        clrf    WREG, A
        btfsc   control_flags_acc, PRESET_BIT, A
        movlw   0x01
        call    eeprom_write_byte, 0x0
        return  0x0

v171_send_preset_frame_and_persist_aborted:
        return  0x0

v171_preset_screen:
        ; ---------------------------------------------------------------
        ; V1.72 inline (V1.61b): preset A/B menu screen body
        ; ---------------------------------------------------------------
        ; Renders the Preset screen (row 0 "Preset          ", row 1
        ; "Active: A       " or "Active: B       "), runs a tight
        ; button-poll loop that toggles PRESET_BIT on UP/DOWN and
        ; exits on LEFT / RIGHT / SELECT.  Bank-1 RAM 0x72 snapshots
        ; the active preset bit so the screen redraws only when the
        ; user actually flipped state, avoiding mid-frame flicker.
        ; Port of the V1.61b binary-overlay preset_screen, inlined
        ; here so there is no jump-out to an `org 0x7000` stub.
v171_prs_screen_draw:
        bra     v171_prs_screen_draw_body
v171_prs_screen_draw_delayed_query:
        movlb   0x02
        bsf     v172_fname_flags_b2, FNAME_QUERY_WAIT, BANKED
        movlb   0x00
v171_prs_screen_draw_body:
        ; FIELD-3: row-0 paint factored into v173_preset_row0_paint so the
        ; per-pass filename service can self-heal a blanked row 0.
        call    v173_preset_row0_paint, 0x0

        ; Row 1 starts blank; filename service will incrementally repaint.
        movlw   0xC0                                       ; LCD cursor row 1 col 0
        call    lcd_command, 0x0
        movlw   0x10
        movwf   (Common_RAM + 24), A
v172_preset_blank_row1_entry:
        movlw   ' '
        call    lcd_char_write, 0x0
        decfsz  (Common_RAM + 24), F, A
        bra     v172_preset_blank_row1_entry

        movlb   0x02
        clrf    v172_fname_retry_b2, BANKED        ; BUG-4: fresh page visit = fresh budget
        btfsc   v172_fname_flags_b2, FNAME_VALID, BANKED
        bra     v171_prs_screen_cache_check
        bra     v171_prs_screen_query_check_wait
v171_prs_screen_cache_check:
        movf    v172_fname_id_b2, W, BANKED
        andlw   0x01
        movwf   v172_fname_tmp_b2, BANKED
        movlb   0x00
        btfsc   control_flags_acc, PRESET_BIT, A
        bra     v171_prs_screen_cache_expect_b
        movlb   0x02
        movf    v172_fname_tmp_b2, F, BANKED
        bnz     v171_prs_screen_query_check_wait
        call    fname_mark_row_dirty_valid, 0x0
        movlb   0x00
        bra     v171_prs_screen_query_done
v171_prs_screen_cache_expect_b:
        movlb   0x02
        movf    v172_fname_tmp_b2, F, BANKED
        bz      v171_prs_screen_query_check_wait
        call    fname_mark_row_dirty_valid, 0x0
        movlb   0x00
        bra     v171_prs_screen_query_done

v171_prs_screen_query_check_wait:
        movlb   0x02
        btfsc   v172_fname_flags_b2, FNAME_QUERY_WAIT, BANKED
        bra     v171_prs_screen_query_after_settle
        movlb   0x00
        call    fname_reset_and_query, 0x0
        bra     v171_prs_screen_query_done
v171_prs_screen_query_after_settle:
        movlb   0x00
        ; Re-entry and slot-change redraws use one delayed first query.  This
        ; lets screen-change and preset-apply traffic drain without retrying
        ; malformed replies.
        call    fname_reset_and_delay_query, 0x0
v171_prs_screen_query_done:

        ; Snapshot PRESET_BIT in bank-1 0x72 for dirty-check on next loop
        movlb   0x01
        clrf    v171_preset_bit_snapshot_b1, BANKED
        btfsc   control_flags_acc, PRESET_BIT, A
        incf    v171_preset_bit_snapshot_b1, F, BANKED

        ; Consume the key that entered/redrew the Preset page so the freshly
        ; painted screen cannot immediately self-exit on the same latched
        ; LEFT/RIGHT/UP/DOWN event.
        movlb   0x00
        clrf    button_event_latch_b0, BANKED
        bcf     control_flags_acc, 0x3, A

v171_preset_loop:
        movlb   0x00
        call    display_loop_iteration, 0x0
        ; Compare current PRESET_BIT against snapshot — if flipped,
        ; redraw; otherwise fall through to button scan.
        movlb   0x00
        btfsc   control_flags_acc, 0x3, A                    ; event_exit bit?
        bcf     control_flags_acc, 0x3, A
        clrf    WREG, A
        btfsc   control_flags_acc, PRESET_BIT, A
        movlw   0x01
        movlb   0x01
        xorwf   v171_preset_bit_snapshot_b1, W, BANKED
        movlb   0x00
        bz      v171_prs_check_up
        goto    v171_prs_screen_draw_delayed_query

v171_prs_check_up:
        btfss   button_event_latch_b0, 0x1, B                              ; UP pressed?
        goto    v171_prs_check_down
        btfss   control_flags_acc, PRESET_BIT, A             ; already A?
        goto    v171_preset_loop                          ; yes — nothing to do
        bcf     control_flags_acc, PRESET_BIT, A             ; flip to A
        rcall   v171_send_preset_frame_and_persist
        bc      v171_prs_up_abort
        goto    v171_prs_screen_draw_delayed_query
v171_prs_up_abort:
        bsf     control_flags_acc, PRESET_BIT, A             ; restore B if TX/EEPROM aborted
        goto    v171_preset_loop

v171_prs_check_down:
        btfss   button_event_latch_b0, 0x2, B                              ; DOWN pressed?
        goto    v171_preset_exit_check
        btfsc   control_flags_acc, PRESET_BIT, A             ; already B?
        goto    v171_preset_loop                          ; yes — nothing to do
        bsf     control_flags_acc, PRESET_BIT, A             ; flip to B
        rcall   v171_send_preset_frame_and_persist
        bc      v171_prs_down_abort
        goto    v171_prs_screen_draw_delayed_query
v171_prs_down_abort:
        bcf     control_flags_acc, PRESET_BIT, A             ; restore A if TX/EEPROM aborted
        goto    v171_preset_loop

v171_preset_exit_check:
        bcf     control_flags_acc, 0x3, A                    ; clear event_exit
        clrf    WREG, A
        btfsc   button_event_latch_b0, 0x5, B                              ; RIGHT pressed?
        movlw   0x01
        movwf   (Common_RAM + 24), A                      ; ram_0x018
        clrf    WREG, A
        btfsc   button_event_latch_b0, 0x4, B                              ; LEFT pressed?
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A
        movlw   0x01
        btfsc   control_flags_acc, CONNECTED, A              ; disconnected → exit
        clrf    WREG, A
        iorwf   (Common_RAM + 24), F, A
        btfsc   STATUS, Z, A
        bra     v171_preset_loop                          ; no exit condition — loop
        movlb   0x02
        bsf     v172_fname_row0_status_snap_b2, FNAME_ROW0_NOT_READY, BANKED
        btfsc   v172_fname_flags_b2, FNAME_VALID, BANKED
        bra     v171_preset_exit_keep_valid_filename
        movlb   0x00
        call    fname_reset_blank, 0x0
        btfss   control_flags_acc, PRESET_BIT, A
        return  0x0
        movlb   0x02
        bsf     v172_fname_flags_b2, FNAME_QUERY_WAIT, BANKED
        movlb   0x00
        return  0x0
v171_preset_exit_keep_valid_filename:
        movlb   0x00
        return  0x0


; ===========================================================================
; V1.72 Layer 5 Phase B + Tier-1 Phase 3.4 — Diagnostics page
; ---------------------------------------------------------------------------
; Per-PB sparse renderer for the Tier-1 Diagnostics page.
; Rewritten in Phase 3.4 (V32_DIAG_TIER1_SPEC.md §"LCD layouts") to replace
; the dual-PB legacy renderer that displayed
; both PBs simultaneously on a single screen.  The new design renders
; ONE PB per page.  Legacy/PB2-unknown pages are state 4 = PB1 and
; state 5 = PB2; after PB2 discovery inserts Input PB2, the split pages
; shift to state 5 = PB1 and state 6 = PB2 so that:
;   * Per-PB layout has 32 chars to spend on at most 11 cells per PB
;     -- enough room for sparse rendering of all 7 runtime + 4 reset-
;     cause cells WITHOUT prefix overhead eating the available width.
;   * Operator-glanceable: silent PB shows "PBn" + "n/a"; healthy PB
;     shows "PBn OK" with S/B/O context on row 1; issue PB shows the
;     non-zero cells in display order I D R A P V W X S B O.
;
; Cache-source dispatch (PB index 0 -> PB1, 1 -> PB2):
;   * PB1: cache base v171_diag_pb1_i = operand 0x080 (phys 0x180)
;   * PB2: cache base v171_diag_pb2_i = operand 0x08B (phys 0x18B... wait
;     the cache equates use BANKED-form operands so PB2 base operand is
;     0x08B with movlb 0x01 active; physical 0x18B).
;   * Present mask bit: PB1 bit 0, PB2 bit 1.
;   * Title char: '1' for PB1, '2' for PB2.
;
; Layout (16x2 LCD):
;   Healthy (count == 0):
;     Row 0: "PBn" + 13 spaces       (the Healthy branch -- target
;                                     label `v171_diag_render_healthy`
;                                     -- fires when the abnormal-cell
;                                     counter `v171_diag_render_abnormal`
;                                     is 0, where the counter walks
;                                     issue cells I/D/R/A/P/V/W/X;
;                                     OK-context cells S/B/O do NOT
;                                     count toward abnormal)
;     Row 1: sparse OK-context cells S/B/O, or blank if all zero.
;   Absent (present mask bit clear):
;     Row 0: "PBn" + 13 spaces
;     Row 1: "n/a" + 13 spaces
;   Degraded (1 <= count <= 9):
;     Row 0: "PBn!" + " X#" * min(count,4) + spaces to col 16
;            (each " X#" = 3 chars: leading space + letter + value)
;     Row 1: if count <= 4 -> 16 spaces (entire row blank);
;            else "X#" + " X#" * (count-5) + spaces to col 16
;            (first row-1 entry has no leading space; subsequent
;            entries get a leading space).
;   Overflow (count >= 10):
;     Row 0: "PBn!" + " X# X# X# X#" (4 entries, full width)
;     Row 1: "X# X# X# X# X#" (5 entries, 14 chars) + ".."
;
; Counter encoding (unchanged from Phase B baseline):
;   0 -> (cell omitted entirely from sparse render)
;   1..9 -> '1'..'9'
;   A..E -> 'A'..'E'
;   F+   -> '+' (saturated)
;
; Display order:
;   Issue first: I D R A P V W X
;   OK-context counters last: S B O
; Healthy row-1 order is the OK-context subset: S B O.
;
; The screen body runs a non-modal foreground-service subset each tick.
; A 16-bit countdown (v171_diag_poll_lo/hi) gates the next cmd 0x21
; query; on each expiry the target is loaded from the visible PB page
; (PB1 page -> PB1, PB2 page -> PB2), so the displayed PB refreshes at
; the full cadence (~ once per 1 s at the 0x80 reload).
; Exits on RIGHT / LEFT (menu nav) or disconnect (CONNECTED clear),
; matching the V1.61b preset-screen exit semantics.
; ===========================================================================

; ---------------------------------------------------------------------------
; v171_diag_pb_screen -- Tier-1 per-PB diagnostics screen entry
; ---------------------------------------------------------------------------
; Caller convention:
;   in : W = PB index (0 = PB1, 1 = PB2)
;   out: returns when operator navigates LEFT / RIGHT or disconnect
;
; Stash the PB index into v171_diag_render_pb_index so the cadence
; loop's redraw path (`goto v171_diag_screen_draw` from check_redraw)
; picks the right cache base / present-mask bit / title char on every
; redraw.  Then fall through to v171_diag_screen for the page-entry
; hooks (clear reset_seen + first-entry target init) and the initial
; render + cadence loop.
; ---------------------------------------------------------------------------
v171_diag_pb_screen:
        movlb   0x01
        andlw   0x01                                       ; mask to 0 or 1
        movwf   v171_diag_render_pb_index_b1, BANKED
        movlb   0x00
        ; fall through to v171_diag_screen

v171_diag_screen:
        ; Page-entry setup: the cadence send path below reloads
        ; v171_diag_target from v171_diag_render_pb_index before every
        ; query, so the active visible page gets the full ~1 s update
        ; cadence instead of sharing a hidden alternating target.
        ;
        ; Tier-1 page-entry hook: clear v171_diag_reset_seen so the
        ; cadence loop fires cmd 0x22 ONCE per PB on this Diag-page
        ; visit.  The reset-cause flags don't change within a session
        ; (they're set at MAIN cold-init), so re-querying every
        ; cadence cycle would waste chain bandwidth.  Once both PBs
        ; have responded with BF/2B, v171_diag_reset_seen has bits
        ; 0+1 set and the page-entry gate stays closed for the rest
        ; of the session.  Operator must navigate AWAY and back to
        ; re-enter, which clears reset_seen here and re-fires cmd 0x22.
        movlb   0x01
        clrf    v171_diag_reset_seen_b1, BANKED
        ; Drop any stale in-flight transaction state on page entry.
        ; If RUNTIME_PENDING or RESET_PENDING survives with a zero
        ; timeout byte, the cadence loop decrements 0 -> 0xFF and can
        ; block fresh PB queries for 256 poll cadences before retrying.
        clrf    v171_diag_flags_b1, BANKED
        clrf    v171_diag_reset_target_b1, BANKED
        clrf    v171_diag_reset_timeout_b1, BANKED
        clrf    v171_diag_runtime_target_b1, BANKED
        clrf    v171_diag_runtime_timeout_b1, BANKED
        ; --- Tier-1 Phase 3.4 follow-up: cadence prime moved to
        ;     page-entry-only.  Originally the countdown clear lived
        ;     in v171_diag_screen_armed below, which the render
        ;     branches bra to AFTER every redraw.  That meant every
        ;     incoming BF/2N reply reset the countdown to 0 and
        ;     immediately re-fired cmd 0x21 / cmd 0x22 on the next
        ;     loop iteration -- collapsing the intended ~1 s cadence
        ;     to event-driven burst traffic.  On real 2-PB hardware
        ;     that saturates the chain bus and starves the menu's
        ;     button-check loop (codex-cli sim 2026-04-21).
        ;
        ;     New behavior: clear the countdown ONCE on page entry
        ;     so the very first cadence tick fires immediately, then
        ;     every subsequent send respects the ~1 s reload value.
        ;     Snapshot the present mask here too so the first
        ;     check_redraw doesn't fire a spurious redraw against an
        ;     uninitialized snapshot byte.
        clrf    v171_diag_poll_lo_b1, BANKED
        clrf    v171_diag_poll_hi_b1, BANKED
        movf    v171_diag_present_b1, W, BANKED
        movwf   v171_diag_present_snap_b1, BANKED
        ; V1.72 identity query epoch: page re-entry retries identity
        ; after a previous old-MAIN timeout and cancels late replies from
        ; another visible page.
        btfsc   v171_diag_render_pb_index_b1, 0, BANKED
        bra     v172_diag_entry_identity_pb2
        movlb   0x02
        bcf     v172_diag_id_seen_mask_b2, 0, BANKED
        bra     v172_diag_entry_identity_common
v172_diag_entry_identity_pb2:
        movlb   0x02
        bcf     v172_diag_id_seen_mask_b2, 1, BANKED
v172_diag_entry_identity_common:
        bcf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_PENDING, BANKED
        bcf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_RETRIED, BANKED
        clrf    v172_diag_id_timeout_b2, BANKED
        clrf    v172_diag_id_expected_cmd_b2, BANKED
        movlb   0x00

v171_diag_screen_draw:
        ; --- Row 0 cursor + write "PB<n>" prefix (3 chars at cols 0-2) ---
        ; Common to all three layouts (absent/healthy/degraded); the
        ; layout decision picks what comes after column 2 (':' for
        ; degraded, ' ' fill for absent/healthy).
        movlw   0x80                                       ; LCD cursor row 0 col 0
        call    lcd_command, 0x0
        movlw   'P'
        call    lcd_char_write, 0x0
        movlw   'B'
        call    lcd_char_write, 0x0
        movlb   0x01
        movf    v171_diag_render_pb_index_b1, W, BANKED
        addlw   0x31                                       ; pb_index 0->'1', 1->'2'
        movlb   0x00
        call    lcd_char_write, 0x0

        ; --- Decide layout: absent / healthy / degraded ---
        ; Compute per-PB present-mask bit (PB1 -> 0x01, PB2 -> 0x02).
        movlb   0x01
        movlw   0x01
        btfsc   v171_diag_render_pb_index_b1, 0, BANKED
        movlw   0x02
        andwf   v171_diag_present_b1, W, BANKED
        bnz     v171_diag_screen_present
        ; --- ABSENT path ---
        bra     v171_diag_render_absent
v171_diag_screen_present:
        call    v171_health_diag_check_stale, 0x0
        movf    (Common_RAM + 4), F, A
        bnz     v171_diag_render_stale_or_lost
        ; --- Pass 1: count display cells in the operator order
        ;     I/D/R/A/P/V/W/X/S/B/O.
        ;
        ; v171_diag_render_count tracks all non-zero display cells.
        ; v171_diag_render_abnormal tracks issue cells only:
        ;   I/D/R/A/P/V/W/X.
        ; S/B/O are OK-context counters: they render under "PBn OK"
        ; when abnormal==0, or at the end of the degraded sparse list
        ; when any issue counter is present and there is room.
        movlb   0x01
        clrf    v171_diag_render_count_b1, BANKED
        clrf    v171_diag_render_abnormal_b1, BANKED
        clrf    v171_diag_render_walk_idx_b1, BANKED
v171_diag_count_display_loop:
        movlw   0x0B
        cpfslt  v171_diag_render_walk_idx_b1, BANKED          ; idx >= 11 -> done
        bra     v171_diag_count_display_done
        movf    v171_diag_render_walk_idx_b1, W, BANKED
        rcall   v171_diag_value_for_display_order
        bz      v171_diag_count_display_skip
        incf    v171_diag_render_count_b1, F, BANKED
        movlw   0x08
        cpfslt  v171_diag_render_walk_idx_b1, BANKED          ; idx < 8 -> issue
        bra     v171_diag_count_display_skip
        incf    v171_diag_render_abnormal_b1, F, BANKED
v171_diag_count_display_skip:
        incf    v171_diag_render_walk_idx_b1, F, BANKED
        bra     v171_diag_count_display_loop
v171_diag_count_display_done:
        ; --- Branch on abnormal (NOT all-11 count) ---
        movf    v171_diag_render_abnormal_b1, F, BANKED
        bz      v171_diag_render_healthy
        bra     v171_diag_render_degraded

; --- STALE/LOST layout: row 0 = "PBn old" or "PBn lost"; row 1 blank.
v171_diag_render_stale_or_lost:
        call    v172_diag_identity_invalidate_visible, 0x0
        movlb   0x00
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   0x02
        cpfseq  (Common_RAM + 4), A
        bra     v171_diag_render_old
        movlw   'l'
        call    lcd_char_write, 0x0
        movlw   'o'
        call    lcd_char_write, 0x0
        movlw   's'
        call    lcd_char_write, 0x0
        movlw   't'
        call    lcd_char_write, 0x0
        movlb   0x01
        movlw   0x08
        movwf   v171_diag_lcd_pad_count_b1, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
        bra     v171_diag_render_stale_row1_blank
v171_diag_render_old:
        movlw   'o'
        call    lcd_char_write, 0x0
        movlw   'l'
        call    lcd_char_write, 0x0
        movlw   'd'
        call    lcd_char_write, 0x0
        movlb   0x01
        movlw   0x09
        movwf   v171_diag_lcd_pad_count_b1, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
v171_diag_render_stale_row1_blank:
        movlw   0xC0
        call    lcd_command, 0x0
        movlb   0x01
        movlw   0x10
        movwf   v171_diag_lcd_pad_count_b1, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
        bra     v171_diag_screen_armed

; --- ABSENT layout: row 0 = "PBn" + 13 spaces, row 1 = "n/a" + 13 spaces.
v171_diag_render_absent:
        movlb   0x01
        movlw   0x0D
        movwf   v171_diag_lcd_pad_count_b1, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
        movlw   0xC0                                       ; LCD cursor row 1 col 0
        call    lcd_command, 0x0
        movlw   'n'
        call    lcd_char_write, 0x0
        movlw   '/'
        call    lcd_char_write, 0x0
        movlw   'a'
        call    lcd_char_write, 0x0
        movlb   0x01
        movlw   0x0D
        movwf   v171_diag_lcd_pad_count_b1, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
        bra     v171_diag_screen_armed

; --- HEALTHY layout: row 0 = "PBn OK" + spaces,
;                     row 1 = sparse OK-context S/B/O counters, or blank.
v171_diag_render_healthy:
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   'O'
        call    lcd_char_write, 0x0
        movlw   'K'
        call    lcd_char_write, 0x0
        call    v172_diag_render_identity_suffix, 0x0

        movlw   0xC0                                       ; LCD cursor row 1 col 0
        call    lcd_command, 0x0
        movlb   0x01
        clrf    v171_diag_render_emitted_b1, BANKED
        movlw   0x08                                       ; display-order S
        movwf   v171_diag_render_walk_idx_b1, BANKED
v171_diag_healthy_ok_loop:
        movlw   0x0B
        cpfslt  v171_diag_render_walk_idx_b1, BANKED          ; idx >= 11 -> done
        bra     v171_diag_healthy_ok_done
        movf    v171_diag_render_walk_idx_b1, W, BANKED
        rcall   v171_diag_value_for_display_order
        movwf   v171_diag_render_value_b1, BANKED
        bz      v171_diag_healthy_ok_advance
        rcall   v171_diag_emit_row1_token
v171_diag_healthy_ok_advance:
        incf    v171_diag_render_walk_idx_b1, F, BANKED
        bra     v171_diag_healthy_ok_loop
v171_diag_healthy_ok_done:
        movf    v171_diag_render_emitted_b1, F, BANKED
        bnz     v171_diag_healthy_ok_pad_some
        movlw   0x10
        bra     v171_diag_healthy_ok_pad_write
v171_diag_healthy_ok_pad_some:
        movf    v171_diag_render_emitted_b1, W, BANKED
        addwf   WREG, W, A                                 ; W = emitted*2
        addwf   v171_diag_render_emitted_b1, W, BANKED        ; W = emitted*3
        sublw   0x11                                       ; W = 17 - emitted*3
v171_diag_healthy_ok_pad_write:
        movlb   0x01
        movwf   v171_diag_lcd_pad_count_b1, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
        bra     v171_diag_screen_armed

; --- DEGRADED layout: row 0 = "PBn!" + sparse row-0 + pad,
;                     row 1 = sparse row-1 + (pad or "..").
v171_diag_render_degraded:
        ; Finish row-0 prefix: emit '!' (col 3).
        movlw   '!'
        call    lcd_char_write, 0x0

        ; --- Row 0 walk: emit up to 4 non-zero cells as " X#" each. ---
        movlb   0x01
        clrf    v171_diag_render_emitted_b1, BANKED
        clrf    v171_diag_render_walk_idx_b1, BANKED
v171_diag_row0_loop:
        movlw   0x0B
        cpfslt  v171_diag_render_walk_idx_b1, BANKED          ; idx >= 11 -> done
        bra     v171_diag_row0_done
        movlw   0x04
        cpfslt  v171_diag_render_emitted_b1, BANKED          ; emitted >= 4 -> done
        bra     v171_diag_row0_done
        movf    v171_diag_render_walk_idx_b1, W, BANKED
        rcall   v171_diag_value_for_display_order
        movwf   v171_diag_render_value_b1, BANKED
        bz      v171_diag_row0_advance
        ; Non-zero cell -- emit " <letter><val>" (3 chars).
        movlb   0x00
        movlw   ' '
        call    lcd_char_write, 0x0
        movlb   0x01
        movf    v171_diag_render_letter_tmp_b1, W, BANKED
        rcall   v171_diag_letter_for_idx
        movlb   0x00
        call    lcd_char_write, 0x0
        movlb   0x01
        movf    v171_diag_render_value_b1, W, BANKED
        movlb   0x00
        rcall   v171_diag_emit_nib_w
        movlb   0x01
        incf    v171_diag_render_emitted_b1, F, BANKED
v171_diag_row0_advance:
        incf    v171_diag_render_walk_idx_b1, F, BANKED
        bra     v171_diag_row0_loop
v171_diag_row0_done:
        ; Pad row 0: each emitted entry consumes 3 chars; row-0 tail
        ; has 12 chars (cols 4..15).  pad_count = 12 - emitted*3.
        movf    v171_diag_render_emitted_b1, W, BANKED
        addwf   WREG, W, A                                 ; W = emitted*2
        addwf   v171_diag_render_emitted_b1, W, BANKED        ; W = emitted*3
        sublw   0x0C                                       ; W = 12 - emitted*3
        movwf   v171_diag_lcd_pad_count_b1, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces

        ; --- Row 1 cursor ---
        movlw   0xC0                                       ; LCD cursor row 1 col 0
        call    lcd_command, 0x0

        ; If count <= 4, no entries on row 1 -- write 16 spaces.
        movlb   0x01
        movlw   0x05
        cpfslt  v171_diag_render_count_b1, BANKED             ; count >= 5 ?
        bra     v171_diag_row1_walk_setup
        movlw   0x10
        movwf   v171_diag_lcd_pad_count_b1, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
        bra     v171_diag_screen_armed

v171_diag_row1_walk_setup:
        ; Walk again, skipping the first 4 non-zeros (already on row 0),
        ; emitting up to 5 more on row 1.
        movlb   0x01
        clrf    v171_diag_render_emitted_b1, BANKED
        clrf    v171_diag_render_skipped_b1, BANKED
        clrf    v171_diag_render_walk_idx_b1, BANKED
v171_diag_row1_loop:
        movlw   0x0B
        cpfslt  v171_diag_render_walk_idx_b1, BANKED          ; idx >= 11 -> done
        bra     v171_diag_row1_done
        movlw   0x05
        cpfslt  v171_diag_render_emitted_b1, BANKED           ; emitted >= 5 -> done
        bra     v171_diag_row1_done
        movf    v171_diag_render_walk_idx_b1, W, BANKED
        rcall   v171_diag_value_for_display_order
        movwf   v171_diag_render_value_b1, BANKED
        bz      v171_diag_row1_advance
        ; Non-zero cell -- skip the first 4 (they were emitted on row 0).
        movlw   0x04
        cpfslt  v171_diag_render_skipped_b1, BANKED           ; skipped >= 4 -> emit
        bra     v171_diag_row1_emit
        incf    v171_diag_render_skipped_b1, F, BANKED
        bra     v171_diag_row1_advance
v171_diag_row1_emit:
        rcall   v171_diag_emit_row1_token
v171_diag_row1_advance:
        incf    v171_diag_render_walk_idx_b1, F, BANKED
        bra     v171_diag_row1_loop
v171_diag_row1_done:
        ; Decide tail: count >= 10 -> overflow ".."; else pad with spaces.
        ; chars_used on row 1 = 1 (first letter has no leading space)
        ;                       + (emitted - 1) * 3 + 1 (first digit)
        ;                       + (emitted - 1) * 0 ... simpler:
        ; chars_used = emitted * 3 - 1 (since first entry has no leading
        ;              space, save 1 char).
        ; pad_count_no_overflow = 16 - chars_used = 17 - emitted*3.
        movlw   0x0A
        cpfslt  v171_diag_render_count_b1, BANKED             ; count >= 10 ?
        bra     v171_diag_row1_overflow
        ; Non-overflow: pad to 16.
        movf    v171_diag_render_emitted_b1, W, BANKED
        addwf   WREG, W, A                                 ; W = emitted*2
        addwf   v171_diag_render_emitted_b1, W, BANKED        ; W = emitted*3
        sublw   0x11                                       ; W = 17 - emitted*3
        movwf   v171_diag_lcd_pad_count_b1, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
        bra     v171_diag_screen_armed
v171_diag_row1_overflow:
        ; Overflow: emitted == 5, chars_used = 14, write ".." in last 2 cols.
        movlb   0x00
        movlw   '.'
        call    lcd_char_write, 0x0
        movlw   '.'
        call    lcd_char_write, 0x0
        bra     v171_diag_screen_armed

; ---------------------------------------------------------------------------
; v171_diag_cache_idx_for_display_order -- map display-order index to cache idx.
; ---------------------------------------------------------------------------
; Display order index:
;   0=I 1=D 2=R 3=A 4=P 5=V 6=W 7=X 8=S 9=B 10=O
;
; Cache/letter index:
;   0=I 1=D 2=S 3=B 4=R 5=A 6=P 7=O 8=V 9=W 10=X
;
; Caller convention:
;   in : W = display-order index 0..10
;   out: W = cache/letter index, BSR = 1
; ---------------------------------------------------------------------------
v171_diag_cache_idx_for_display_order:
        movlb   0x01
        movwf   v171_diag_render_letter_tmp_b1, BANKED
        movlw   0x00                                      ; display 0 -> cache I
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_order_dec_to_d
        return  0x0
v171_diag_order_dec_to_d:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   0x01                                      ; display 1 -> cache D
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_order_dec_to_r
        return  0x0
v171_diag_order_dec_to_r:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   0x04                                      ; display 2 -> cache R
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_order_dec_to_a
        return  0x0
v171_diag_order_dec_to_a:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   0x05                                      ; display 3 -> cache A
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_order_dec_to_p
        return  0x0
v171_diag_order_dec_to_p:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   0x06                                      ; display 4 -> cache P
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_order_dec_to_v
        return  0x0
v171_diag_order_dec_to_v:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   0x08                                      ; display 5 -> cache V
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_order_dec_to_w
        return  0x0
v171_diag_order_dec_to_w:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   0x09                                      ; display 6 -> cache W
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_order_dec_to_x
        return  0x0
v171_diag_order_dec_to_x:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   0x0A                                      ; display 7 -> cache X
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_order_dec_to_s
        return  0x0
v171_diag_order_dec_to_s:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   0x02                                      ; display 8 -> cache S
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_order_dec_to_b
        return  0x0
v171_diag_order_dec_to_b:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   0x03                                      ; display 9 -> cache B
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_order_dec_to_o
        return  0x0
v171_diag_order_dec_to_o:
        movlw   0x07                                      ; display 10 -> cache O
        return  0x0

; ---------------------------------------------------------------------------
; v171_diag_value_for_display_order -- read one displayed counter value.
; ---------------------------------------------------------------------------
; Caller convention:
;   in : W = display-order index 0..10
;   out: W = cached value, BSR = 1
; Side effect:
;   v171_diag_render_letter_tmp = cache/letter index for the same cell.
; ---------------------------------------------------------------------------
v171_diag_value_for_display_order:
        rcall   v171_diag_cache_idx_for_display_order
        movwf   v171_diag_render_letter_tmp_b1, BANKED
        rcall   v171_diag_load_fsr1_base
        movf    v171_diag_render_letter_tmp_b1, W, BANKED
        movf    PLUSW1, W, A
        movlb   0x01
        return  0x0

; ---------------------------------------------------------------------------
; v171_diag_emit_row1_token -- emit row-1 token using prepared value/letter.
; ---------------------------------------------------------------------------
; Uses:
;   v171_diag_render_letter_tmp = cache/letter index
;   v171_diag_render_value      = low-nibble display value
;   v171_diag_render_emitted    = already-emitted row-1 token count
;
; First token has no leading separator. Later tokens emit one leading space.
; Leaves BSR = 1 on return.
; ---------------------------------------------------------------------------
v171_diag_emit_row1_token:
        movlb   0x01
        movf    v171_diag_render_emitted_b1, F, BANKED
        bz      v171_diag_emit_row1_no_sep
        movlb   0x00
        movlw   ' '
        call    lcd_char_write, 0x0
v171_diag_emit_row1_no_sep:
        movlb   0x01
        movf    v171_diag_render_letter_tmp_b1, W, BANKED
        rcall   v171_diag_letter_for_idx
        movlb   0x00
        call    lcd_char_write, 0x0
        movlb   0x01
        movf    v171_diag_render_value_b1, W, BANKED
        movlb   0x00
        rcall   v171_diag_emit_nib_w
        movlb   0x01
        incf    v171_diag_render_emitted_b1, F, BANKED
        return  0x0

; ---------------------------------------------------------------------------
; v171_diag_load_fsr1_base -- set FSR1 to the per-PB cache base.
; ---------------------------------------------------------------------------
; PB index 0 -> FSR1 = 0x180 (v171_diag_pb1_i physical address)
; PB index 1 -> FSR1 = 0x18B (v171_diag_pb2_i physical address)
;
; Reads v171_diag_render_pb_index from BANK 1.  Leaves BSR=1 on return.
; ---------------------------------------------------------------------------
v171_diag_load_fsr1_base:
        movlb   0x01
        btfsc   v171_diag_render_pb_index_b1, 0, BANKED
        bra     v171_diag_load_fsr1_pb2
        lfsr    0x1, v171_diag_pb1_i_b1_phys
        return  0x0
v171_diag_load_fsr1_pb2:
        lfsr    0x1, v171_diag_pb2_i_b1_phys
        return  0x0

; ---------------------------------------------------------------------------
; v171_diag_letter_for_idx -- decode a cache cell index (0..10) to its letter.
; ---------------------------------------------------------------------------
; Cache order: I D S B R A P O V W X.
;   0 -> 'I'  3 -> 'B'  6 -> 'P'  9 -> 'W'
;   1 -> 'D'  4 -> 'R'  7 -> 'O' 10 -> 'X'
;   2 -> 'S'  5 -> 'A'  8 -> 'V'
;
; Caller convention:
;   in : W = cell index 0..10
;   out: W = letter, BSR = 1
;
; Implementation: cascade of decrement+test instead of a computed-PC
; jump table.  Computed PC (`addwf PCL, F`) is fragile across 256-byte
; flash page boundaries (PCH doesn't auto-increment from a PCL low-byte
; overflow); the cascade is larger but always correct.  Uses a
; dedicated BANK 1 scratch cell (v171_diag_render_letter_tmp) that is
; not touched by the row-walk loops, so callers can hold their own
; state in v171_diag_render_value across calls here.
; ---------------------------------------------------------------------------
v171_diag_letter_for_idx:
        movlb   0x01
        movwf   v171_diag_render_letter_tmp_b1, BANKED
        movlw   'I'
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_letter_dec_to_d
        return  0x0
v171_diag_letter_dec_to_d:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   'D'
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_letter_dec_to_s
        return  0x0
v171_diag_letter_dec_to_s:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   'S'
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_letter_dec_to_b
        return  0x0
v171_diag_letter_dec_to_b:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   'B'
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_letter_dec_to_r
        return  0x0
v171_diag_letter_dec_to_r:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   'R'
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_letter_dec_to_a
        return  0x0
v171_diag_letter_dec_to_a:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   'A'
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_letter_dec_to_p
        return  0x0
v171_diag_letter_dec_to_p:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   'P'
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_letter_dec_to_o
        return  0x0
v171_diag_letter_dec_to_o:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   'O'
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_letter_dec_to_v
        return  0x0
v171_diag_letter_dec_to_v:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   'V'
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_letter_dec_to_w
        return  0x0
v171_diag_letter_dec_to_w:
        decf    v171_diag_render_letter_tmp_b1, F, BANKED
        movlw   'W'
        tstfsz  v171_diag_render_letter_tmp_b1, BANKED
        bra     v171_diag_letter_dec_to_x
        return  0x0
v171_diag_letter_dec_to_x:
        movlw   'X'
        return  0x0

; ---------------------------------------------------------------------------
; v171_diag_pad_spaces -- write v171_diag_lcd_pad_count spaces to the LCD.
; ---------------------------------------------------------------------------
; Counter cell lives in BANK 1 because lcd_char_write's helpers clobber
; access-bank scratch (ram_0x004).  Caller must populate
; v171_diag_lcd_pad_count BEFORE calling.  No-op if count == 0.
;
; BSR is restored to 0 on return.
; ---------------------------------------------------------------------------
v171_diag_pad_spaces:
        movlb   0x01
        movf    v171_diag_lcd_pad_count_b1, F, BANKED
        bz      v171_diag_pad_spaces_done                  ; count == 0 -> no-op
v171_diag_pad_spaces_loop:
        movlb   0x00
        movlw   ' '
        call    lcd_char_write, 0x0
        movlb   0x01                                       ; lcd_char_write may have touched BSR
        decfsz  v171_diag_lcd_pad_count_b1, F, BANKED
        bra     v171_diag_pad_spaces_loop
v171_diag_pad_spaces_done:
        movlb   0x00
        return  0x0

; ---------------------------------------------------------------------------
; v171_clear_lcd_row2 -- blank LCD row 2 before entering one-line screens.
; ---------------------------------------------------------------------------
; The V1.72 boot banner owns both LCD rows.  WAITING only writes row 1, so
; explicitly clear row 2 instead of leaving a stale release banner visible.
; BSR is restored to 0 on return.
; ---------------------------------------------------------------------------
v171_clear_lcd_row2:
        movlw   0xC0                                       ; LCD cursor row 1 col 0
        call    lcd_command, 0x0
        movlb   0x01
        movlw   0x10
        movwf   v171_diag_lcd_pad_count_b1, BANKED
        movlb   0x00
        call    v171_diag_pad_spaces, 0x0
        return  0x0

v171_diag_screen_armed:
        ; Cadence prime + present_snap init MOVED to v171_diag_screen
        ; (page-entry-only) to fix the redraw-vs-cadence collapse
        ; identified by codex-cli sim 2026-04-21.  This label is now
        ; just a fall-through marker preserved for backward
        ; compatibility -- all render branches still bra here, but
        ; the work it used to do is now in the page-entry init block.
        ;
        ; Do NOT add per-redraw setup here without auditing whether
        ; collapsing the cadence is acceptable.  See the v171_diag_loop
        ; comment block + V32_DIAG_TIER1_SPEC.md for the cadence
        ; design intent.

v171_diag_loop:
        ; Do not call display_loop_iteration here: it is a modal helper
        ; that parks internally until a UI event, which stalls the
        ; Diagnostics poll cadence during a static wait.  The Diag page
        ; needs the non-modal subset only: button scan + RX parser +
        ; frame-gap guard, then return to the cadence/redraw logic below.
        bsf     INTCON, RBIE, A
        call    button_scan_debounce, 0x0
        movlb   0x00
        call    rx_parser_entry, 0x0
        call    v171_service_rx_frame_gap, 0x0
        call    v171_health_service, 0x0
        call    ir_dispatch_configured_or_fixed_shortcuts, 0x0
        movlb   0x00
        ; Decrement the 16-bit poll countdown.  When it reaches zero,
        ; enqueue a cmd 0x21 query for the current target PB and reload.
v171_diag_poll_check:
        movlb   0x01
        movf    v171_diag_poll_lo_b1, W, BANKED
        iorwf   v171_diag_poll_hi_b1, W, BANKED
        bnz     v171_diag_loop_dec
        ; Countdown expired.  If RUNTIME_PENDING is still set, wait a
        ; small number of missed cadences before retrying the visible
        ; PB.  The RESET_PENDING timeout below still ages during that
        ; wait so cmd 0x22 cannot freeze behind a silent runtime burst.
        ; The target is loaded from v171_diag_render_pb_index in
        ; v171_diag_send_now, so a silent hidden PB cannot steal the
        ; active page's ~1 s refresh cadence, and one BF/21..BF/27
        ; burst stays in flight at a time.
        movlb   0x01
        btfss   v171_diag_flags_b1, V171_DIAG_FLAG_RUNTIME_PENDING, BANKED
        bra     v171_diag_send_now                         ; previous reply landed
        decf    v171_diag_runtime_timeout_b1, F, BANKED
        bnz     v171_diag_runtime_wait_with_reset_timeout  ; still in timeout window
        ; Previous visible-page query timed out -- retry it.
        call    v171_health_age_visible_diag_target, 0x0
        movlb   0x01
        bcf     v171_diag_flags_b1, V171_DIAG_FLAG_RUNTIME_PENDING, BANKED
        bra     v171_diag_send_now
v171_diag_runtime_wait_with_reset_timeout:
        btfss   v171_diag_flags_b1, V171_DIAG_FLAG_RESET_PENDING, BANKED
        bra     v171_diag_runtime_wait
        decf    v171_diag_reset_timeout_b1, F, BANKED
        bnz     v171_diag_runtime_wait
        movlw   0x01                                       ; PB1 reset_seen bit
        btfsc   v171_diag_reset_target_b1, 0, BANKED
        movlw   0x02                                       ; PB2 reset_seen bit
        iorwf   v171_diag_reset_seen_b1, F, BANKED
        bcf     v171_diag_flags_b1, V171_DIAG_FLAG_RESET_PENDING, BANKED
        bra     v171_diag_runtime_wait
v171_diag_runtime_wait:
        movlw   V171_DIAG_POLL_RELOAD_LO
        movwf   v171_diag_poll_lo_b1, BANKED
        movlw   V171_DIAG_POLL_RELOAD_HI
        movwf   v171_diag_poll_hi_b1, BANKED
        movlb   0x00
        bra     v171_diag_check_redraw
v171_diag_send_now:
        ; BUG-DIAG-01/02: per-PB Diagnostics pages must refresh the PB
        ; the operator is actually viewing at the full cadence.  The
        ; BF/27 parser may toggle v171_diag_target after a reply, but
        ; the next send reloads it from v171_diag_render_pb_index so
        ; hidden PBs cannot make the active page wait every other
        ; cadence cycle.
        movlb   0x01
        movf    v171_diag_render_pb_index_b1, W, BANKED
        andlw   0x01
        movwf   v171_diag_target_b1, BANKED
        call    v172_diag_identity_cadence, 0x0
        bc      v172_diag_identity_skip_runtime
        movlb   0x01
        ; --- Tier-1: cmd 0x22 fire-once-per-PB-per-page-entry hook ---
        ; State machine for the new cmd 0x22 (reset-cause flags) query:
        ;
        ;   * RESET_PENDING set + timeout > 0   -> cmd 0x22 in flight,
        ;                                          decrement timeout, wait.
        ;   * RESET_PENDING set + timeout == 0  -> spec "give up" path:
        ;                                          mark in-flight PB as
        ;                                          reset_seen (so we don't
        ;                                          re-fire), clear PENDING.
        ;   * RESET_PENDING clear + reset_seen.target set -> already
        ;                                          handled (either BF/2B
        ;                                          landed or we gave up).
        ;   * RESET_PENDING clear + reset_seen.target clear -> fire cmd
        ;                                          0x22 now.  Snapshot
        ;                                          v171_diag_target into
        ;                                          v171_diag_reset_target,
        ;                                          reload timeout, set
        ;                                          PENDING, send.
        ;
        ; Both bursts can be in flight to the same PB simultaneously:
        ; cmd 0x21 path uses RUNTIME_PENDING + BF/27 last-frame; cmd 0x22
        ; path uses RESET_PENDING + BF/2B last-frame.  The two pendings
        ; + two last-frames are independent so neither query's completion
        ; bit accidentally clears the other's PENDING flag.
        ;
        ; v171_diag_reset_target captures the in-flight cmd 0x22 target
        ; separately from v171_diag_target because v171_diag_target can
        ; toggle independently (via the cmd 0x21 BF/27 last-frame path)
        ; between cmd 0x22 send and BF/2B reception or timeout.
        btfss   v171_diag_flags_b1, V171_DIAG_FLAG_RESET_PENDING, BANKED
        bra     v171_diag_check_reset_seen                 ; not pending -- proceed
        ; --- RESET_PENDING set: timeout countdown ---
        decf    v171_diag_reset_timeout_b1, F, BANKED
        bnz     v171_diag_send_runtime_only                ; not yet expired
        ; --- Timeout: spec "give up" path ---
        ; Mark the in-flight reset target as reset_seen so the gate
        ; below stays closed for the rest of this Diag-page visit.
        ; Using v171_diag_reset_target (snapshot at send time), NOT
        ; v171_diag_target (which may have toggled).
        movlw   0x01                                       ; PB1 mask
        btfsc   v171_diag_reset_target_b1, 0, BANKED
        movlw   0x02                                       ; PB2 mask
        iorwf   v171_diag_reset_seen_b1, F, BANKED
        bcf     v171_diag_flags_b1, V171_DIAG_FLAG_RESET_PENDING, BANKED
        bra     v171_diag_send_runtime_only
v171_diag_check_reset_seen:
        ; Compute reset_seen mask for the current target: bit0 for PB1,
        ; bit1 for PB2.  If already seen (BF/2B received OR timed out),
        ; skip the cmd 0x22 fire and fall through to cmd 0x21.
        movlw   0x01                                       ; PB1 mask
        btfsc   v171_diag_target_b1, 0, BANKED
        movlw   0x02                                       ; PB2 mask
        andwf   v171_diag_reset_seen_b1, W, BANKED
        bnz     v171_diag_send_runtime_only                ; already seen for this PB
        ; --- reset_seen.target clear AND RESET_PENDING clear: fire ---
        ; Snapshot v171_diag_target.0 into v171_diag_reset_target so
        ; the timeout path knows which PB to give up on (target may
        ; toggle independently before BF/2B arrives or times out).
        movf    v171_diag_target_b1, W, BANKED
        andlw   0x01
        movwf   v171_diag_reset_target_b1, BANKED
        ; Reload timeout counter.  Each cadence cycle is ~1 s so
        ; V171_DIAG_RESET_TIMEOUT_RELOAD = 4 gives ~4 s timeout per spec.
        movlw   V171_DIAG_RESET_TIMEOUT_RELOAD
        movwf   v171_diag_reset_timeout_b1, BANKED
        bsf     v171_diag_flags_b1, V171_DIAG_FLAG_RESET_PENDING, BANKED
        movlb   0x00
        rcall   v171_diag_send_reset_query
        movlb   0x01
v171_diag_send_runtime_only:
        ; Snapshot the runtime target before emitting cmd 0x21.  The
        ; BF/21..BF/27 reply burst is routed to cache via this snapshot
        ; instead of the live target, which may toggle or be reused by
        ; reset-cause query handling before all reply frames land.
        movf    v171_diag_target_b1, W, BANKED
        andlw   0x01
        movwf   v171_diag_runtime_target_b1, BANKED
        movlw   V171_DIAG_RUNTIME_TIMEOUT_RELOAD
        movwf   v171_diag_runtime_timeout_b1, BANKED
        bsf     v171_diag_flags_b1, V171_DIAG_FLAG_RUNTIME_PENDING, BANKED
        movlb   0x00
        rcall   v171_diag_send_runtime_query
        movlb   0x01
        movlw   V171_DIAG_POLL_RELOAD_LO
        movwf   v171_diag_poll_lo_b1, BANKED
        movlw   V171_DIAG_POLL_RELOAD_HI
        movwf   v171_diag_poll_hi_b1, BANKED
        movlb   0x00
        bra     v171_diag_check_redraw

v172_diag_identity_skip_runtime:
        movlb   0x01
        movlw   V171_DIAG_POLL_RELOAD_LO
        movwf   v171_diag_poll_lo_b1, BANKED
        movlw   V171_DIAG_POLL_RELOAD_HI
        movwf   v171_diag_poll_hi_b1, BANKED
        movlb   0x00
        bra     v171_diag_check_redraw

v171_diag_loop_dec:
        ; 16-bit decrement with borrow.
        movf    v171_diag_poll_lo_b1, W, BANKED
        bnz     v171_diag_loop_dec_lo_only
        decf    v171_diag_poll_hi_b1, F, BANKED
v171_diag_loop_dec_lo_only:
        decf    v171_diag_poll_lo_b1, F, BANKED
        movlb   0x00

v171_diag_check_redraw:
        ; Redraw the screen if EITHER the present mask changed since
        ; the last draw OR the parser case set the DIRTY flag (a fresh
        ; counter value landed in the cache).  Snapshot + flag both
        ; live in BANK 1 — must NOT be the access-bank ram_0x005
        ; scratch cell because display_loop_iteration and the LCD
        ; char-write helpers stomp it on every tick.
        movlb   0x01
        btfsc   v171_diag_flags_b1, V171_DIAG_FLAG_DIRTY, BANKED
        bra     v171_diag_do_redraw                        ; cache changed
        btfsc   v171_health_flags_b1, V171_HEALTH_FLAG_DISPLAY_DIRTY, BANKED
        bra     v171_diag_do_redraw                        ; freshness changed
        movf    v171_diag_present_b1, W, BANKED
        xorwf   v171_diag_present_snap_b1, W, BANKED
        bz      v171_diag_redraw_skip                      ; no change
v171_diag_do_redraw:
        movf    v171_diag_present_b1, W, BANKED
        movwf   v171_diag_present_snap_b1, BANKED
        bcf     v171_diag_flags_b1, V171_DIAG_FLAG_DIRTY, BANKED
        bcf     v171_health_flags_b1, V171_HEALTH_FLAG_DISPLAY_DIRTY, BANKED
        movlb   0x00
        goto    v171_diag_screen_draw
v171_diag_redraw_skip:
        movlb   0x00

v171_diag_check_buttons:
        bcf     control_flags_acc, 0x3, A                      ; clear event_exit
        clrf    WREG, A
        btfsc   button_event_latch_b0, 0x5, B                               ; RIGHT pressed?
        movlw   0x01
        movwf   (Common_RAM + 24), A                       ; ram_0x018
        clrf    WREG, A
        btfsc   button_event_latch_b0, 0x4, B                               ; LEFT pressed?
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A
        movlw   0x01
        btfsc   control_flags_acc, CONNECTED, A                ; disconnected → exit
        clrf    WREG, A
        iorwf   (Common_RAM + 24), F, A
        btfsc   STATUS, Z, A
        bra     v171_diag_loop                             ; no exit — keep ticking
        movlb   0x00
        return  0x0


; ---------------------------------------------------------------------------
; v171_diag_emit_letter — write the constant column-letter (W) to the LCD.
; Splits out the common 'I'/'D'/'S'/'B'/'R'/'A'/'P' banner-letter call so
; the row-render code stays compact.  W must be loaded by the caller.
; ---------------------------------------------------------------------------
v171_diag_emit_letter:
        call    lcd_char_write, 0x0
        return  0x0


; ---------------------------------------------------------------------------
; v171_diag_emit_nib_w — encode the low nibble of W per the diagnostics
; spec and write the resulting character to the LCD.  Uses ram_0x004 as
; scratch so callers don't need to preserve it.
;
; Encoding:
;   0       → ' '   (0x20)
;   1..9    → '1'..'9'  (0x31..0x39)
;   A..E    → 'A'..'E'  (0x41..0x45)
;   F       → '+'   (0x2B, saturated display state)
; ---------------------------------------------------------------------------
v171_diag_emit_nib_w:
        andlw   0x0F
        movwf   (Common_RAM + 4), A
        bz      v171_diag_emit_nib_zero
        movlw   0x0F
        cpfslt  (Common_RAM + 4), A                        ; if nib >= 0x0F
        bra     v171_diag_emit_nib_sat
        movlw   0x0A
        cpfslt  (Common_RAM + 4), A                        ; if nib >= 0x0A
        bra     v171_diag_emit_nib_alpha
        ; nib in 1..9 → '1'..'9'
        movlw   0x30
        addwf   (Common_RAM + 4), W, A
        call    lcd_char_write, 0x0
        return  0x0
v171_diag_emit_nib_alpha:
        ; nib in A..E → 'A'..'E'  (0x41 = 'A' = 0x0A + 0x37)
        movlw   0x37
        addwf   (Common_RAM + 4), W, A
        call    lcd_char_write, 0x0
        return  0x0
v171_diag_emit_nib_zero:
        movlw   ' '
        call    lcd_char_write, 0x0
        return  0x0
v171_diag_emit_nib_sat:
        movlw   '+'
        call    lcd_char_write, 0x0
        return  0x0

; ---------------------------------------------------------------------------
; V1.73 Diagnostics MAIN identity LCD helpers.
; ---------------------------------------------------------------------------
v172_diag_render_identity_suffix:
        movlb   0x01
        btfsc   v171_diag_render_pb_index_b1, 0, BANKED
        bra     v172_diag_render_identity_pb2
        movlb   0x02
        btfss   v172_diag_id_valid_mask_b2, 0, BANKED
        bra     v172_diag_render_identity_absent
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   'v'
        call    lcd_char_write, 0x0
        movlb   0x02
        movf    v172_diag_id_pb1_major_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        movlw   '.'
        call    lcd_char_write, 0x0
        movlb   0x02
        movf    v172_diag_id_pb1_minor_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        movlw   ' '
        call    lcd_char_write, 0x0
        movlb   0x02
        movf    v173_diag_id_pb1_rev_hi_b2, W, BANKED
        movwf   v172_diag_id_tmp_rev_hi_b2, BANKED
        swapf   v172_diag_id_tmp_rev_hi_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        movlb   0x02
        movf    v173_diag_id_pb1_rev_hi_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        movlb   0x02
        movf    v172_diag_id_pb1_rev_b2, W, BANKED
        movwf   v172_diag_id_tmp_rev_hi_b2, BANKED
        swapf   v172_diag_id_tmp_rev_hi_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        movlb   0x02
        movf    v172_diag_id_pb1_rev_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        return  0x0
v172_diag_render_identity_pb2:
        movlb   0x02
        btfss   v172_diag_id_valid_mask_b2, 1, BANKED
        bra     v172_diag_render_identity_absent
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   'v'
        call    lcd_char_write, 0x0
        movlb   0x02
        movf    v172_diag_id_pb2_major_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        movlw   '.'
        call    lcd_char_write, 0x0
        movlb   0x02
        movf    v172_diag_id_pb2_minor_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        movlw   ' '
        call    lcd_char_write, 0x0
        movlb   0x02
        movf    v173_diag_id_pb2_rev_hi_b2, W, BANKED
        movwf   v172_diag_id_tmp_rev_hi_b2, BANKED
        swapf   v172_diag_id_tmp_rev_hi_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        movlb   0x02
        movf    v173_diag_id_pb2_rev_hi_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        movlb   0x02
        movf    v172_diag_id_pb2_rev_b2, W, BANKED
        movwf   v172_diag_id_tmp_rev_hi_b2, BANKED
        swapf   v172_diag_id_tmp_rev_hi_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        movlb   0x02
        movf    v172_diag_id_pb2_rev_b2, W, BANKED
        movlb   0x00
        rcall   v172_diag_emit_hex_nib_w
        return  0x0
v172_diag_render_identity_absent:
        movlb   0x01
        movlw   0x0A
        movwf   v171_diag_lcd_pad_count_b1, BANKED
        movlb   0x00
        call    v171_diag_pad_spaces, 0x0
        return  0x0

v172_diag_emit_hex_nib_w:
        andlw   0x0F
        movwf   (Common_RAM + 4), A
        movlw   0x0A
        cpfslt  (Common_RAM + 4), A
        bra     v172_diag_emit_hex_alpha
        movlw   0x30
        addwf   (Common_RAM + 4), W, A
        call    lcd_char_write, 0x0
        return  0x0
v172_diag_emit_hex_alpha:
        movlw   0x37
        addwf   (Common_RAM + 4), W, A
        call    lcd_char_write, 0x0
        return  0x0

v172_diag_identity_invalidate_visible:
        movlb   0x01
        btfsc   v171_diag_render_pb_index_b1, 0, BANKED
        bra     v172_diag_identity_invalidate_pb2
        movlb   0x02
        bcf     v172_diag_id_valid_mask_b2, 0, BANKED
        bcf     v172_diag_id_seen_mask_b2, 0, BANKED
        btfsc   v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_TARGET, BANKED
        bra     v172_diag_identity_invalidate_done
        bcf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_PENDING, BANKED
        bra     v172_diag_identity_invalidate_done
v172_diag_identity_invalidate_pb2:
        movlb   0x02
        bcf     v172_diag_id_valid_mask_b2, 1, BANKED
        bcf     v172_diag_id_seen_mask_b2, 1, BANKED
        btfss   v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_TARGET, BANKED
        bra     v172_diag_identity_invalidate_done
        bcf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_PENDING, BANKED
v172_diag_identity_invalidate_done:
        movlb   0x00
        return  0x0


; ---------------------------------------------------------------------------
; v172_diag_identity_cadence -- one-shot identity query scheduler.
; ---------------------------------------------------------------------------
; Returns C=1 when this cadence was consumed by identity wait/send and
; cmd 0x21/0x22 should be skipped.  Returns C=0 when normal diagnostics
; traffic should proceed.
; ---------------------------------------------------------------------------
v172_diag_identity_cadence:
        movlb   0x02
        btfsc   v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_PENDING, BANKED
        bra     v172_diag_identity_pending
        movlb   0x01
        btfsc   v171_diag_flags_b1, V171_DIAG_FLAG_RUNTIME_PENDING, BANKED
        bra     v172_diag_identity_noop
        btfsc   v171_diag_flags_b1, V171_DIAG_FLAG_RESET_PENDING, BANKED
        bra     v172_diag_identity_noop
        btfsc   v171_diag_target_b1, 0, BANKED
        bra     v172_diag_identity_check_pb2
        btfss   v171_diag_present_b1, 0, BANKED
        bra     v172_diag_identity_noop
        movlb   0x02
        btfsc   v172_diag_id_valid_mask_b2, 0, BANKED
        bra     v172_diag_identity_noop
        btfsc   v172_diag_id_seen_mask_b2, 0, BANKED
        bra     v172_diag_identity_noop
        bcf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_TARGET, BANKED
        bra     v172_diag_identity_start
v172_diag_identity_check_pb2:
        btfss   v171_diag_present_b1, 1, BANKED
        bra     v172_diag_identity_noop
        movlb   0x02
        btfsc   v172_diag_id_valid_mask_b2, 1, BANKED
        bra     v172_diag_identity_noop
        btfsc   v172_diag_id_seen_mask_b2, 1, BANKED
        bra     v172_diag_identity_noop
        bsf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_TARGET, BANKED
v172_diag_identity_start:
        movf    v172_diag_id_next_gen_b2, W, BANKED
        andlw   0x1F
        addwf   WREG, W, A
        movwf   v172_diag_id_pending_id_b2, BANKED
        btfsc   v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_TARGET, BANKED
        bsf     v172_diag_id_pending_id_b2, 0, BANKED
        call    v172_diag_identity_send_query, 0x0
        bc      v172_diag_identity_noop
        movlb   0x02
        movlw   0x4F
        movwf   v172_diag_id_expected_cmd_b2, BANKED
        movlw   V172_DIAG_ID_TIMEOUT_RELOAD
        movwf   v172_diag_id_timeout_b2, BANKED
        bsf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_PENDING, BANKED
        incf    v172_diag_id_next_gen_b2, F, BANKED
        movlw   0x20
        cpfseq  v172_diag_id_next_gen_b2, BANKED
        bra     v172_diag_identity_sent
        clrf    v172_diag_id_next_gen_b2, BANKED
v172_diag_identity_sent:
        movlb   0x00
        bsf     STATUS, C, A
        return  0x0
v172_diag_identity_pending:
        movf    v172_diag_id_timeout_b2, F, BANKED
        bz      v172_diag_identity_timeout
        decf    v172_diag_id_timeout_b2, F, BANKED
        bz      v172_diag_identity_timeout
        movlb   0x00
        bsf     STATUS, C, A
        return  0x0
v172_diag_identity_timeout:
        btfss   v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_RETRIED, BANKED
        bra     v172_diag_identity_retry
        btfsc   v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_TARGET, BANKED
        bra     v172_diag_identity_timeout_pb2
        bsf     v172_diag_id_seen_mask_b2, 0, BANKED
        bra     v172_diag_identity_timeout_done
v172_diag_identity_timeout_pb2:
        bsf     v172_diag_id_seen_mask_b2, 1, BANKED
v172_diag_identity_timeout_done:
        bcf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_PENDING, BANKED
        bcf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_RETRIED, BANKED
        bra     v172_diag_identity_noop
v172_diag_identity_retry:
        bsf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_RETRIED, BANKED
        bcf     v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_PENDING, BANKED
v172_diag_identity_noop:
        movlb   0x00
        bcf     STATUS, C, A
        return  0x0

v172_diag_identity_send_query:
        call    tx_ring_reserve_3, 0x0
        bc      v172_diag_identity_send_abort
        movlw   0xB1
        movlb   0x02
        btfsc   v172_diag_id_flags_b2, V172_DIAG_ID_FLAG_TARGET, BANKED
        movlw   0xB2
        movlb   0x00
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        bc      v172_diag_identity_send_abort
        movlw   0x25
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        bc      v172_diag_identity_send_abort
        movlb   0x02
        movf    v172_diag_id_pending_id_b2, W, BANKED
        movlb   0x00
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        bc      v172_diag_identity_send_abort
        bcf     STATUS, C, A
        return  0x0
v172_diag_identity_send_abort:
        movlb   0x00
        bsf     STATUS, C, A
        return  0x0

; ---------------------------------------------------------------------------
; V1.72/V3.3 Preset filename helpers
; ---------------------------------------------------------------------------
v172_fname_cold_clear:
        lfsr    0x0, v172_fname_cache_b2_phys
        movlw   0x25
        movwf   (Common_RAM + 15), A
v172_fname_clear_low:
        clrf    POSTINC0, A
        decfsz  (Common_RAM + 15), F, A
        bra     v172_fname_clear_low
        lfsr    0x0, v172_fname_scroll_div_lo_b2_phys
        movlw   0x08
        movwf   (Common_RAM + 15), A
v172_fname_clear_high:
        clrf    POSTINC0, A
        decfsz  (Common_RAM + 15), F, A
        bra     v172_fname_clear_high
        movlb   0x00
        return  0x0

fname_mark_row_dirty_blank:
        movlb   0x02
        clrf    v172_fname_render_col_b2, BANKED
        clrf    v172_fname_render_off_b2, BANKED
        bsf     v172_fname_flags_b2, FNAME_ROW_DIRTY, BANKED
        return  0x0

fname_mark_row_dirty_valid:
        movlb   0x02
        clrf    v172_fname_render_col_b2, BANKED
        movf    v172_fname_scroll_off_b2, W, BANKED
        movwf   v172_fname_render_off_b2, BANKED
        bsf     v172_fname_flags_b2, FNAME_ROW_DIRTY, BANKED
        return  0x0

fname_reset_blank:
        movlb   0x02
        clrf    v172_fname_flags_b2, BANKED
        clrf    v172_fname_len_b2, BANKED
        clrf    v172_fname_expected_len_b2, BANKED
        clrf    v172_fname_deadline_lo_b2, BANKED
        clrf    v172_fname_deadline_hi_b2, BANKED
        clrf    v172_fname_scroll_off_b2, BANKED
        clrf    v172_fname_scroll_hold_b2, BANKED
        clrf    v172_fname_scroll_div_lo_b2, BANKED
        clrf    v172_fname_scroll_div_hi_b2, BANKED
        rcall   fname_mark_row_dirty_blank
        return  0x0

fname_reset_and_query:
        rcall   fname_reset_blank
        movlb   0x00
        movlw   0x01
        cpfseq  display_state_index_b0, BANKED
        return  0x0
        btfss   control_flags_acc, CONNECTED, A
        return  0x0
        movlb   0x02
        bsf     v172_fname_flags_b2, FNAME_WANT_QUERY, BANKED
        movlb   0x00
        return  0x0

fname_reset_and_delay_query:
        rcall   fname_reset_blank
        movlb   0x00
        movlw   0x01
        cpfseq  display_state_index_b0, BANKED
        return  0x0
        btfss   control_flags_acc, CONNECTED, A
        return  0x0
        movlb   0x02
        bsf     v172_fname_flags_b2, FNAME_QUERY_WAIT, BANKED
        movlw   FNAME_QUERY_DELAY_LO
        movwf   v172_fname_deadline_lo_b2, BANKED
        movlb   0x00
        btfsc   control_flags_acc, PRESET_BIT, A
        bra     fname_delay_query_slot_b
        movlb   0x02
        movlw   FNAME_QUERY_DELAY_A_HI
        movwf   v172_fname_deadline_hi_b2, BANKED
        movlb   0x00
        return  0x0
fname_delay_query_slot_b:
        movlb   0x02
        movlw   FNAME_QUERY_DELAY_B_HI
        movwf   v172_fname_deadline_hi_b2, BANKED
        movlb   0x00
        return  0x0

fname_reset_blank_maybe_retry:
        ; V1.73 BUG-V34V173-4: a parser abort or pending-deadline expiry is a
        ; transient on a contended chain, not a terminal state.  Blank as
        ; before, but while the retry budget lasts re-arm the existing
        ; delayed-query machinery (fname_reset_and_delay_query re-checks the
        ; Preset page + CONNECTED at fire time, and the query send mints a
        ; fresh generation id so stale frames cannot be misattributed).  The
        ; budget resets on successful reception and on Preset page entry.
        movlb   0x02
        incf    v172_fname_retry_b2, F, BANKED
        movlw   FNAME_RETRY_MAX
        cpfslt  v172_fname_retry_b2, BANKED        ; budget left?
        bra     fname_reset_blank                  ; exhausted -> blank only
        bra     fname_reset_and_delay_query        ; bounded retry (FNAME_QUERY_WAIT)

v172_preset_filename_service:
        movlb   0x00
        movlw   0x01
        cpfseq  display_state_index_b0, BANKED
        return  0x0
        movlb   0x02
        btfss   v172_fname_row0_status_snap_b2, FNAME_ROW0_NOT_READY, BANKED
        bra     v172_preset_filename_service_row0_ready
        ; FIELD-3 self-heal: row 0 was invalidated (standby entry, reconnect,
        ; or a defensive LCD clear) while we are parked on the Preset page.
        ; Repaint it -- but only while awake/CONNECTED: in standby or WAITING
        ; the Zzz/banner overlay owns the LCD and the heal must stay parked.
        movlb   0x00
        btfss   control_flags_acc, 0x1, A
        return  0x0
        call    v173_preset_row0_paint, 0x0
        return  0x0
v172_preset_filename_service_row0_ready:
        ; FIELD-3 belt: the post-wake bounce can blank row 0 through a
        ; corrupted LCD byte sequence AFTER the entry repaint cleared the
        ; not-ready latch, so flag bookkeeping alone cannot be trusted.
        ; Re-assert row 0 every 32 service passes while awake on the Preset
        ; page; rewriting identical characters is invisible on the HD44780.
        incf    v173_row0_reassert_div_b2, F, BANKED
        btfss   v173_row0_reassert_div_b2, 5, BANKED
        bra     v173_row0_reassert_done
        clrf    v173_row0_reassert_div_b2, BANKED
        movlb   0x00
        btfss   control_flags_acc, 0x1, A
        return  0x0
        call    v173_preset_row0_paint, 0x0
        return  0x0
v173_row0_reassert_done:
        movlb   0x00
        call    v172_fname_query_service, 0x0
        call    v172_fname_deadline_service, 0x0
        call    v172_fname_scroll_service, 0x0
        call    v172_preset_status_patch_service, 0x0
        bc      v172_preset_filename_service_done
        call    v172_fname_row1_render_service, 0x0
v172_preset_filename_service_done:
        movlb   0x00
        return  0x0

v172_fname_query_service:
        movlb   0x02
        btfss   v172_fname_flags_b2, FNAME_WANT_QUERY, BANKED
        return  0x0
        btfsc   v172_fname_flags_b2, FNAME_PENDING, BANKED
        return  0x0
        incf    v172_fname_gen_b2, F, BANKED
        movlw   0x20
        cpfseq  v172_fname_gen_b2, BANKED
        bra     v172_fname_query_gen_ok
        clrf    v172_fname_gen_b2, BANKED
v172_fname_query_gen_ok:
        movf    v172_fname_gen_b2, W, BANKED
        movwf   v172_fname_id_b2, BANKED
        rlncf   v172_fname_id_b2, F, BANKED
        rlncf   v172_fname_id_b2, F, BANKED
        bcf     v172_fname_id_b2, 1, BANKED
        movlb   0x00
        btfsc   control_flags_acc, PRESET_BIT, A
        bra     v172_fname_query_slot_b
        movlb   0x02
        bcf     v172_fname_id_b2, 0, BANKED
        bra     v172_fname_query_send
v172_fname_query_slot_b:
        movlb   0x02
        bsf     v172_fname_id_b2, 0, BANKED
v172_fname_query_send:
        call    v172_fname_send_query, 0x0
        bc      v172_fname_query_done
        movlb   0x02
        bsf     v172_fname_flags_b2, FNAME_PENDING, BANKED
        bcf     v172_fname_flags_b2, FNAME_WANT_QUERY, BANKED
        bcf     v172_fname_flags_b2, FNAME_ARMED, BANKED
        bcf     v172_fname_flags_b2, FNAME_LEN_SEEN, BANKED
        clrf    v172_fname_len_b2, BANKED
        clrf    v172_fname_expected_len_b2, BANKED
        movlw   FNAME_PENDING_DEADLINE_LO
        movwf   v172_fname_deadline_lo_b2, BANKED
        movlw   FNAME_PENDING_DEADLINE_HI
        movwf   v172_fname_deadline_hi_b2, BANKED
v172_fname_query_done:
        movlb   0x00
        return  0x0

v172_fname_send_query:
        call    tx_ring_reserve_3, 0x0
        bc      v172_fname_send_abort
        movlw   0xB1
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        bc      v172_fname_send_abort
        movlw   0x26
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        bc      v172_fname_send_abort
        movlb   0x02
        movf    v172_fname_id_b2, W, BANKED
        movlb   0x00
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        bc      v172_fname_send_abort
        bcf     STATUS, C, A
        return  0x0
v172_fname_send_abort:
        movlb   0x00
        bsf     STATUS, C, A
        return  0x0

v172_fname_deadline_service:
        movlb   0x02
        btfsc   v172_fname_flags_b2, FNAME_PENDING, BANKED
        bra     v172_fname_pending_deadline_service
        btfss   v172_fname_flags_b2, FNAME_QUERY_WAIT, BANKED
        return  0x0
        bra     v172_fname_query_delay_service
v172_fname_pending_deadline_service:
        movf    v172_fname_deadline_lo_b2, F, BANKED
        bnz     v172_fname_deadline_dec_lo
        movf    v172_fname_deadline_hi_b2, F, BANKED
        bz      v172_fname_deadline_expire
        decf    v172_fname_deadline_hi_b2, F, BANKED
        decf    v172_fname_deadline_lo_b2, F, BANKED
        return  0x0
v172_fname_deadline_dec_lo:
        decf    v172_fname_deadline_lo_b2, F, BANKED
        return  0x0
v172_fname_deadline_expire:
        rcall   fname_reset_blank_maybe_retry      ; BUG-4: bounded retry, not terminal blank
        return  0x0

v172_fname_query_delay_service:
        movf    v172_fname_deadline_lo_b2, F, BANKED
        bnz     v172_fname_query_delay_dec_lo
        movf    v172_fname_deadline_hi_b2, F, BANKED
        bz      v172_fname_query_delay_expire
        decf    v172_fname_deadline_hi_b2, F, BANKED
        decf    v172_fname_deadline_lo_b2, F, BANKED
        return  0x0
v172_fname_query_delay_dec_lo:
        decf    v172_fname_deadline_lo_b2, F, BANKED
        return  0x0
v172_fname_query_delay_expire:
        movlb   0x00
        movlw   0x01
        cpfseq  display_state_index_b0, BANKED
        bra     v172_fname_query_delay_cancel
        btfss   control_flags_acc, CONNECTED, A
        bra     v172_fname_query_delay_cancel
        ; Do not start the filename reply while a background health ping is
        ; still outstanding.  Holding WAIT here lets BF/2C drain or time out;
        ; v171_health_service suppresses new health pings while WAIT/PENDING.
        movlb   0x01
        btfsc   v171_health_flags_b1, V171_HEALTH_FLAG_PENDING, BANKED
        return  0x0
        movlb   0x02
        bcf     v172_fname_flags_b2, FNAME_QUERY_WAIT, BANKED
        bsf     v172_fname_flags_b2, FNAME_WANT_QUERY, BANKED
        movlb   0x00
        return  0x0
v172_fname_query_delay_cancel:
        call    fname_reset_blank, 0x0
        movlb   0x00
        return  0x0

v172_fname_scroll_service:
        movlb   0x02
        btfss   v172_fname_flags_b2, FNAME_VALID, BANKED
        return  0x0
        movlw   0x11
        cpfslt  v172_fname_len_b2, BANKED
        bra     v172_fname_scroll_active
        return  0x0
v172_fname_scroll_active:
        btfsc   v172_fname_flags_b2, FNAME_ROW_DIRTY, BANKED
        return  0x0
        movf    v172_fname_scroll_div_lo_b2, F, BANKED
        bnz     v172_fname_scroll_dec_lo
        movf    v172_fname_scroll_div_hi_b2, F, BANKED
        bz      v172_fname_scroll_step_ready
        decf    v172_fname_scroll_div_hi_b2, F, BANKED
        decf    v172_fname_scroll_div_lo_b2, F, BANKED
        return  0x0
v172_fname_scroll_dec_lo:
        decf    v172_fname_scroll_div_lo_b2, F, BANKED
        return  0x0
v172_fname_scroll_step_ready:
        movlw   FNAME_SCROLL_DIV_LO
        movwf   v172_fname_scroll_div_lo_b2, BANKED
        movlw   FNAME_SCROLL_DIV_HI
        movwf   v172_fname_scroll_div_hi_b2, BANKED
        movf    v172_fname_scroll_hold_b2, F, BANKED
        bz      v172_fname_scroll_move
        decf    v172_fname_scroll_hold_b2, F, BANKED
        return  0x0
v172_fname_scroll_move:
        movf    v172_fname_len_b2, W, BANKED
        addlw   0xF0                                        ; max_off = len - 16
        movwf   v172_fname_tmp_b2, BANKED
        btfsc   v172_fname_flags_b2, FNAME_TAILDIR, BANKED
        bra     v172_fname_scroll_tail
        movf    v172_fname_scroll_off_b2, W, BANKED
        cpfseq  v172_fname_tmp_b2, BANKED
        bra     v172_fname_scroll_prefix_inc
        clrf    v172_fname_scroll_off_b2, BANKED
        movlw   FNAME_SCROLL_REST_HOLD
        movwf   v172_fname_scroll_hold_b2, BANKED
        bra     v172_fname_scroll_dirty
v172_fname_scroll_prefix_inc:
        incf    v172_fname_scroll_off_b2, F, BANKED
        movf    v172_fname_scroll_off_b2, W, BANKED
        cpfseq  v172_fname_tmp_b2, BANKED
        bra     v172_fname_scroll_dirty
        movlw   FNAME_SCROLL_FAR_HOLD
        movwf   v172_fname_scroll_hold_b2, BANKED
        bra     v172_fname_scroll_dirty
v172_fname_scroll_tail:
        movf    v172_fname_scroll_off_b2, F, BANKED
        bnz     v172_fname_scroll_tail_dec
        movf    v172_fname_tmp_b2, W, BANKED
        movwf   v172_fname_scroll_off_b2, BANKED
        movlw   FNAME_SCROLL_REST_HOLD
        movwf   v172_fname_scroll_hold_b2, BANKED
        bra     v172_fname_scroll_dirty
v172_fname_scroll_tail_dec:
        decf    v172_fname_scroll_off_b2, F, BANKED
        movf    v172_fname_scroll_off_b2, F, BANKED
        bnz     v172_fname_scroll_dirty
        movlw   FNAME_SCROLL_FAR_HOLD
        movwf   v172_fname_scroll_hold_b2, BANKED
v172_fname_scroll_dirty:
        rcall   fname_mark_row_dirty_valid
        return  0x0

v172_preset_status_patch_service:
        movlb   0x02
        clrf    v172_fname_tmp_b2, BANKED
        movlb   0x01
        movlw   V171_HEALTH_STALE_AGE
        cpfslt  v171_health_age_pb1_b1, BANKED
        bra     v172_preset_status_set_health
        movlw   V171_HEALTH_STALE_AGE
        cpfslt  v171_health_age_pb2_b1, BANKED
        bra     v172_preset_status_set_health
        bra     v172_preset_status_preset
v172_preset_status_set_health:
        movlb   0x02
        bsf     v172_fname_tmp_b2, 0, BANKED
v172_preset_status_preset:
        movlb   0x00
        btfsc   control_flags_acc, PRESET_BIT, A
        bra     v172_preset_status_set_b
        bra     v172_preset_status_fault
v172_preset_status_set_b:
        movlb   0x02
        bsf     v172_fname_tmp_b2, 1, BANKED
v172_preset_status_fault:
        movlb   0x00
        btfsc   control_flags_acc, DSP_FAULT_BIT, A
        bra     v172_preset_status_set_fault
        bra     v172_preset_status_check_col14
v172_preset_status_set_fault:
        movlb   0x02
        bsf     v172_fname_tmp_b2, 2, BANKED
v172_preset_status_check_col14:
        movlb   0x02
        movf    v172_fname_tmp_b2, W, BANKED
        xorwf   v172_fname_row0_status_snap_b2, W, BANKED
        andlw   FNAME_ROW0_HEALTH_MASK
        bz      v172_preset_status_check_col15
        movlb   0x00
        movlw   0x8E
        call    lcd_command, 0x0
        movlb   0x02
        movlw   ' '
        btfsc   v172_fname_tmp_b2, 0, BANKED
        movlw   '*'
        movlb   0x00
        call    lcd_char_write, 0x0
        movlb   0x02
        bcf     v172_fname_row0_status_snap_b2, FNAME_ROW0_HEALTH, BANKED
        btfsc   v172_fname_tmp_b2, FNAME_ROW0_HEALTH, BANKED
        bsf     v172_fname_row0_status_snap_b2, FNAME_ROW0_HEALTH, BANKED
        movlw   FNAME_ROW0_SNAP_MASK
        andwf   v172_fname_row0_status_snap_b2, F, BANKED
        movlb   0x00
        bsf     STATUS, C, A
        return  0x0
v172_preset_status_check_col15:
        movf    v172_fname_tmp_b2, W, BANKED
        xorwf   v172_fname_row0_status_snap_b2, W, BANKED
        andlw   FNAME_ROW0_PRESET_FAULT_MASK
        bz      v172_preset_status_no_lcd
        movlb   0x00
        movlw   0x8F
        call    lcd_command, 0x0
        movlb   0x02
        movlw   '!'
        btfsc   v172_fname_tmp_b2, 2, BANKED
        bra     v172_preset_status_write_col15
        movlw   'A'
        btfsc   v172_fname_tmp_b2, 1, BANKED
        movlw   'B'
v172_preset_status_write_col15:
        movlb   0x00
        call    lcd_char_write, 0x0
        movlb   0x02
        bcf     v172_fname_row0_status_snap_b2, FNAME_ROW0_PRESET_B, BANKED
        bcf     v172_fname_row0_status_snap_b2, FNAME_ROW0_DSP_FAULT, BANKED
        btfsc   v172_fname_tmp_b2, FNAME_ROW0_PRESET_B, BANKED
        bsf     v172_fname_row0_status_snap_b2, FNAME_ROW0_PRESET_B, BANKED
        btfsc   v172_fname_tmp_b2, FNAME_ROW0_DSP_FAULT, BANKED
        bsf     v172_fname_row0_status_snap_b2, FNAME_ROW0_DSP_FAULT, BANKED
        movlw   FNAME_ROW0_SNAP_MASK
        andwf   v172_fname_row0_status_snap_b2, F, BANKED
        movlb   0x00
        bsf     STATUS, C, A
        return  0x0
v172_preset_status_no_lcd:
        movlb   0x00
        bcf     STATUS, C, A
        return  0x0

v172_fname_row1_render_service:
        movlb   0x02
        btfss   v172_fname_flags_b2, FNAME_ROW_DIRTY, BANKED
        return  0x0
        movlb   0x00
        movlw   0xC0
        movlb   0x02
        addwf   v172_fname_render_col_b2, W, BANKED
        movlb   0x00
        call    lcd_command, 0x0
        movlb   0x02
        movlw   ' '
        btfss   v172_fname_flags_b2, FNAME_VALID, BANKED
        bra     v172_fname_row1_write
        movf    v172_fname_render_off_b2, W, BANKED
        addwf   v172_fname_render_col_b2, W, BANKED
        movwf   v172_fname_tmp_b2, BANKED
        movf    v172_fname_len_b2, W, BANKED
        cpfslt  v172_fname_tmp_b2, BANKED
        bra     v172_fname_row1_space
        lfsr    0x0, v172_fname_cache_b2_phys
        movf    v172_fname_tmp_b2, W, BANKED
        addwf   FSR0L, F, A
        movf    INDF0, W, A
        bra     v172_fname_row1_write
v172_fname_row1_space:
        movlw   ' '
v172_fname_row1_write:
        movlb   0x00
        call    lcd_char_write, 0x0
        movlb   0x02
        incf    v172_fname_render_col_b2, F, BANKED
        movlw   0x10
        cpfseq  v172_fname_render_col_b2, BANKED
        bra     v172_fname_row1_done
        clrf    v172_fname_render_col_b2, BANKED
        bcf     v172_fname_flags_b2, FNAME_ROW_DIRTY, BANKED
v172_fname_row1_done:
        movlb   0x00
        return  0x0

; ---------------------------------------------------------------------------
; v171_diag_send_query — enqueue a 3-byte cmd 0x21 query for the current
; target PB.  Route is computed from v171_diag_target (0 → 0xB1 PB1,
; 1 → 0xB2 PB2).  Uses tx_ring_reserve_3 before the raw tx_byte_enqueue
; writes so a saturated TX ring drops the whole diagnostics frame rather
; than leaking a partial route/cmd fragment to MAIN.
;
; Per spec, do NOT use the routed-frame helper (full_sync_burst path) —
; that would clobber the periodic-broadcast counter and cause the chain
; to re-burst the entire status set on every diagnostics query.  Going
; raw via tx_byte_enqueue keeps the diagnostics traffic page-local.
; ---------------------------------------------------------------------------
v171_diag_send_runtime_query:
        ; Wrapper: cmd 0x21 (runtime counters, 7-frame BF/21..BF/27).
        ; Tail-calls into v171_diag_send_query_w with cmd byte in W.
        movlw   0x21
        bra     v171_diag_send_query_w

v171_diag_send_reset_query:
        ; Tier-1 wrapper: cmd 0x22 (reset-cause flags, 4-frame
        ; BF/28..BF/2B).  Fired ONCE per Diag-page entry per PB.
        movlw   0x22
        bra     v171_diag_send_query_w

v171_diag_send_query:
        ; Backward-compat alias for callers that historically called
        ; v171_diag_send_query (cmd 0x21 only).  Forwards to the
        ; runtime-query wrapper above.  No new code should call this
        ; -- prefer v171_diag_send_runtime_query / v171_diag_send_reset_query.
        bra     v171_diag_send_runtime_query

v171_diag_send_query_w:
        ; Frame atomicity: reserve three TX slots before writing the
        ; route/cmd/data bytes.  This mirrors serial_tx_routed_frame and
        ; the health-query sender: if the ring is saturated, nothing from
        ; this frame reaches the wire and the cadence retries cleanly.
        ; Keep the per-byte C checks too; they are defensive and preserve
        ; the existing pending-bit cleanup contract if a future edit breaks
        ; the reserve guarantee.
        ;
        ; PENDING reset on abort: caller (cadence loop) sets RUNTIME_PENDING
        ; before calling for cmd 0x21; the page-entry hook sets RESET_PENDING
        ; before calling for cmd 0x22.  On TX abort we clear ONLY the bit
        ; matching the just-aborted query type (dispatched on the cmd byte
        ; saved in (Common_RAM + 28)) so we don't drop tracking of an
        ; already-in-flight OTHER query.
        ;
        ; Concrete bug "clearing both on abort" would cause: the cadence
        ; body fires cmd 0x22 first (sets RESET_PENDING), then cmd 0x21.
        ; If cmd 0x22 sent successfully but cmd 0x21 aborts mid-frame,
        ; the shared abort path would clear RESET_PENDING too even though
        ; cmd 0x22 is still in flight.  The next cadence then sees
        ; RESET_PENDING clear and reset_seen.target still clear, so it
        ; re-fires cmd 0x22 -- a duplicate (mostly harmless on the wire,
        ; but the bookkeeping doesn't match intent).  Codex review LOW
        ; finding against commit 86b1d1a.
        ;
        ; Frame-state recovery on the wire: MAIN's route handler treats
        ; every Bx byte as a frame start (resets frame_pos), so a partial
        ; 1- or 2-byte fragment that landed on the wire ahead of the abort
        ; gets cleaned up by the NEXT genuine route byte -- no permanent
        ; mis-framing.
        ;
        ; Caller convention:
        ;   in : W = cmd byte (0x21 or 0x22)
        ;   out: returns; STATUS.C clear on success, set on TX abort
        ;
        ; Call form: tx_byte_enqueue lives at ~0x05EC; this routine sits
        ; past 0x18xx so rcall overflows the 11-bit relative range and we
        ; must use the absolute call, FAST-zero variant.

        ; Stash cmd byte in BANK 0 access scratch so we can use W for
        ; the route byte first.  ram_0x028 is the V1.72 scratch range
        ; documented in the dlcp_control_ram.inc free-slot audit.
        movwf   (Common_RAM + 28), A                       ; saved cmd byte
        call    tx_ring_reserve_3, 0x0
        bc      v171_diag_send_query_aborted               ; ring saturated; no bytes emitted
        ; --- byte 0: route ---
        movlw   0xB1                                       ; default = PB1 query
        movlb   0x01
        btfsc   v171_diag_target_b1, 0, BANKED                ; bit0 set -> PB2 instead
        movlw   0xB2
        movlb   0x00
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        bc      v171_diag_send_query_aborted               ; ring saturated
        ; --- byte 1: cmd byte (0x21 or 0x22) ---
        movf    (Common_RAM + 28), W, A
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        bc      v171_diag_send_query_aborted
        ; --- byte 2: data 0x00 (final byte) ---
        clrf    tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        bc      v171_diag_send_query_aborted               ; final byte also checked
        return  0x0
v171_diag_send_query_aborted:
        ; TX ring saturated mid-frame.  Clear ONLY the pending bit
        ; matching the just-aborted query type so a sibling query
        ; that already left CONTROL keeps its tracking intact.
        ;
        ; Cmd byte (0x21 or 0x22) lives in (Common_RAM + 28); it was
        ; stashed at routine entry before any TX,
        ; so it is always valid here.  tx_byte_enqueue may have left
        ; BSR anywhere -- re-assert BANK 1 before touching the flag byte.
        movlb   0x01
        movf    (Common_RAM + 28), W, A
        xorlw   0x21
        bz      v171_diag_send_query_aborted_runtime
        ; cmd != 0x21 -> assume cmd 0x22 (the only other type the
        ; helper accepts) and clear RESET_PENDING.  This branch also
        ; covers any future cmd type as "non-runtime" until the helper
        ; gains a real dispatch table.
        bcf     v171_diag_flags_b1, V171_DIAG_FLAG_RESET_PENDING, BANKED
        bra     v171_diag_send_query_aborted_done
v171_diag_send_query_aborted_runtime:
        bcf     v171_diag_flags_b1, V171_DIAG_FLAG_RUNTIME_PENDING, BANKED
v171_diag_send_query_aborted_done:
        movlb   0x00
        return  0x0


; ---------------------------------------------------------------------------
; v171_health_service -- non-blocking per-PB link freshness service.
; ---------------------------------------------------------------------------
; Coarse-ticks via v171_health_tick_div.  On each tick, either sends a
; one-frame health query to the next PB or times out the previous pending
; query, ages that PB, and advances to the other target.  Replies are handled
; by the exact BF/2C parser case.
; ---------------------------------------------------------------------------
input_split_latch_pb2_seen:
        movlb   0x01
        btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_split_latch_done
        btfsc   v171_health_seen_mask_b1, 1, BANKED
        bra     input_split_latch_enable
        btfss   v171_diag_present_b1, 1, BANKED
        bra     input_split_latch_done
input_split_latch_enable:
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_SYNC_TARGET, BANKED
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_PENDING_CONCRETE, BANKED
        bra     input_split_latch_enable_linked
        movff   input_pending_pb2_b1_phys, rx_parsed_data_b0_phys
        movlb   0x00
        call    map_cmd06_input_select_to_menu_index, 0x0
        call    input_screen_compute_menu_max, 0x0
        movf    menu_option_max_index_b0, W, BANKED
        cpfsgt  rx_ring_staging_b0, BANKED
        bra     input_split_latch_pending_row_in_range
        bra     input_split_latch_enable_fallback
input_split_latch_pending_row_in_range:
        call    map_input_menu_index_to_cmd06_input_select, 0x0
        movlb   0x01
        movf    input_pending_pb2_b1, W, BANKED
        movlb   0x00
        xorwf   tx_data_staging_acc, W, A
        bz      input_split_latch_enable_concrete
        bra     input_split_latch_enable_fallback
input_split_latch_enable_concrete:
        movlb   0x01
        bsf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE, BANKED
        movff   input_pending_pb2_b1_phys, input_intent_pb2_b1_phys
        bra     input_split_latch_remap_menu_state
input_split_latch_enable_fallback:
        movlb   0x01
        bsf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bsf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        bsf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE, BANKED
        movff   input_select_cache_b0_phys, input_intent_pb2_b1_phys
        bra     input_split_latch_remap_menu_state
input_split_latch_enable_linked:
        bsf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bsf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE, BANKED
        movff   input_select_cache_b0_phys, input_intent_pb2_b1_phys
input_split_latch_remap_menu_state:
        movlb   0x00
        movlw   0x03
        cpfslt  display_state_index_b0, BANKED
        bra     input_split_latch_check_remap_upper
        bra     input_split_latch_done
input_split_latch_check_remap_upper:
        movlw   0x06
        cpfslt  display_state_index_b0, BANKED
        bra     input_split_latch_done
        incf    display_state_index_b0, F, BANKED
input_split_latch_done:
        movlb   0x00
        return  0x0

v171_health_service:
        movlb   0x01
        incf    v171_health_tick_div_b1, F, BANKED
        bz      v171_health_tick
        movlb   0x00
        return  0x0

v171_health_tick:
        btfss   control_flags_acc, CONNECTED, A
        bra     v171_health_reset_unknown
        ; Diagnostics pages already run addressed cmd 0x21/cmd 0x22
        ; traffic.  Do not add background cmd 0x23 traffic there:
        ; BF/27 completions refresh link age, and runtime timeouts age
        ; the visible PB.
        movlb   0x00
v171_health_check_top_level_page:
	        movlw   0x04
	        cpfslt  display_state_index_b0, BANKED
	        bra     v171_health_check_split_setup_page
	        bra     v171_health_allow_for_page
v171_health_check_split_setup_page:
	        movlw   0x04
	        cpfseq  display_state_index_b0, BANKED
	        return  0x0
	        movlb   0x01
	        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
	        bra     v171_health_done_b0
v171_health_allow_for_page:
	        movlb   0x01
        btfsc   v171_health_flags_b1, V171_HEALTH_FLAG_PENDING, BANKED
        bra     v171_health_pending_timeout
        ; Filename acquisition needs a short quiet link window.  Do not start
        ; a fresh health ping while CONTROL is waiting to query or parsing the
        ; reply; an already-pending health ping is still serviced above.
        movlb   0x02
        btfsc   v172_fname_flags_b2, FNAME_QUERY_WAIT, BANKED
        bra     v171_health_done_b0
        btfsc   v172_fname_flags_b2, FNAME_PENDING, BANKED
        bra     v171_health_done_b0
        btfsc   v172_fname_flags_b2, FNAME_WANT_QUERY, BANKED
        bra     v171_health_done_b0
        movlb   0x01
        call    v171_health_send_query, 0x0
        bc      v171_health_done_b0
        movlb   0x01
        bsf     v171_health_flags_b1, V171_HEALTH_FLAG_PENDING, BANKED
        movlw   V171_HEALTH_PENDING_TICKS
        movwf   v171_health_pending_ticks_b1, BANKED
        bcf     v171_health_flags_b1, V171_HEALTH_FLAG_TARGET, BANKED
        btfsc   v171_health_poll_target_b1, 0, BANKED
        bsf     v171_health_flags_b1, V171_HEALTH_FLAG_TARGET, BANKED
        movlb   0x00
        return  0x0

v171_health_pending_timeout:
        movf    v171_health_pending_ticks_b1, F, BANKED
        bz      v171_health_pending_timeout_expired
        decf    v171_health_pending_ticks_b1, F, BANKED
        movlb   0x00
        return  0x0
v171_health_pending_timeout_expired:
        rcall   v171_health_age_pending_target
        bcf     v171_health_flags_b1, V171_HEALTH_FLAG_PENDING, BANKED
        clrf    v171_health_pending_ticks_b1, BANKED
        bsf     v171_health_flags_b1, V171_HEALTH_FLAG_DISPLAY_DIRTY, BANKED
        btg     v171_health_poll_target_b1, 0, BANKED
        movlb   0x00
        return  0x0

v171_health_age_pending_target:
        movlb   0x01
        btfsc   v171_health_flags_b1, V171_HEALTH_FLAG_TARGET, BANKED
        bra     v171_health_age_pending_pb2
        movlw   0x0F
        cpfseq  v171_health_age_pb1_b1, BANKED
        incf    v171_health_age_pb1_b1, F, BANKED
        return  0x0
v171_health_age_pending_pb2:
        movlw   0x0F
        cpfseq  v171_health_age_pb2_b1, BANKED
        incf    v171_health_age_pb2_b1, F, BANKED
        return  0x0

v171_health_age_visible_diag_target:
        movlb   0x01
        bsf     v171_health_flags_b1, V171_HEALTH_FLAG_DISPLAY_DIRTY, BANKED
        bsf     v171_diag_flags_b1, V171_DIAG_FLAG_DIRTY, BANKED
        btfsc   v171_diag_render_pb_index_b1, 0, BANKED
        bra     v171_health_age_visible_diag_pb2
        movlw   0x0F
        cpfseq  v171_health_age_pb1_b1, BANKED
        incf    v171_health_age_pb1_b1, F, BANKED
        movlb   0x00
        return  0x0
v171_health_age_visible_diag_pb2:
        movlw   0x0F
        cpfseq  v171_health_age_pb2_b1, BANKED
        incf    v171_health_age_pb2_b1, F, BANKED
        movlb   0x00
        return  0x0

v171_health_reset_unknown:
        movlb   0x01
        clrf    v171_health_age_pb1_b1, BANKED
        clrf    v171_health_age_pb2_b1, BANKED
        clrf    v171_health_seen_mask_b1, BANKED
        clrf    v171_health_flags_b1, BANKED
        clrf    v171_health_poll_target_b1, BANKED
        clrf    v171_health_tick_div_b1, BANKED
        clrf    v171_health_pending_ticks_b1, BANKED
v171_health_done_b0:
        movlb   0x00
        return  0x0

; ---------------------------------------------------------------------------
; v171_health_send_query -- enqueue [B1/B2, 0x23, 0x00].
; ---------------------------------------------------------------------------
; Uses tx_ring_reserve_3 so a saturated TX ring drops the whole frame.  Health
; is low priority: if foreground/full-sync traffic is already queued, report
; busy (STATUS.C=1) and let the next health tick try again rather than starting
; a timeout while the ping is still stuck behind older bytes.
; STATUS.C is preserved as the success/fail result for the caller.
; ---------------------------------------------------------------------------
v171_health_send_query:
        movlb   0x00
        movf    tx_ring_wr_b0, W, B
        cpfseq  tx_ring_rd_b0, B
        bra     v171_health_send_query_busy
        call    tx_ring_reserve_3, 0x0
        bc      v171_health_send_query_done
        movlw   0xB1
        movlb   0x01
        btfsc   v171_health_poll_target_b1, 0, BANKED
        movlw   0xB2
        movlb   0x00
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        movlw   0x23
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        clrf    tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        ; V1.73 session-49 fix: periodic idempotent mute re-assert.  A lost
        ; B0/03/02 leaves a MAIN unmuted at full volume while CONTROL shows
        ; Mute, with nothing to heal it: the cmd-03 echo path only syncs
        ; CONTROL toward MAINs, and the full-sync mute step is postponed by
        ; every volume frame.  Ride the health-poll cadence: every 2nd
        ; successful poll enqueue WHILE MUTED, re-broadcast mute_on.  A
        ; consistent MAIN no-ops the redundant frame; a diverged one
        ; re-converges within ~2 poll cycles.  Gated on the muted state so
        ; the idle/unmuted chain carries no extra traffic (keeps the wire
        ; byte-stream identical to V1.73 rev 0x44 outside mute, and the
        ; dangerous direction -- live audio against a muted UI -- is the
        ; one that self-heals).
        ;
        ; The frame is enqueued with the same tx-ring primitives as the
        ; poll itself, NOT via mute_frame_send: serial_tx_routed_frame
        ; clears the full-sync countdown on success, so routing through it
        ; every other muted poll would starve the volume/input/preset
        ; full-sync convergence indefinitely (codex review of b1f35d6).
        ; The hardcoded 0x02 data byte is safe: the bit5 gate above
        ; guarantees CONTROL is muted here.  STATUS.C is forced back to
        ; the poll's success result on every re-assert path.
        btfss   control_flags_acc, 0x5, A           ; only while MUTED
        bra     v171_health_send_query_done
        btfss   control_flags_acc, 0x1, A           ; only while CONNECTED
        bra     v171_health_send_query_done
        movlb   0x02
        incf    v173_mute_reassert_div_b2, F, BANKED
        btfss   v173_mute_reassert_div_b2, 0, BANKED
        bra     v173_mute_reassert_done_b2
        movlb   0x00
        call    tx_ring_reserve_3, 0x0
        bc      v173_mute_reassert_clear_c          ; ring full: poll still OK
        movlw   0xB0
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        movlw   0x03
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
        movlw   0x02
        movwf   tx_data_staging_acc, A
        call    tx_byte_enqueue, 0x0
v173_mute_reassert_clear_c:
        bcf     STATUS, C, A                        ; poll enqueue succeeded
        bra     v171_health_send_query_done
v173_mute_reassert_done_b2:
        movlb   0x00
v171_health_send_query_done:
        movlb   0x00
        return  0x0
v171_health_send_query_busy:
        bsf     STATUS, C, A
        return  0x0

; ---------------------------------------------------------------------------
; v171_health_patch_suffix -- patch top-level row-2 tail with link status.
; ---------------------------------------------------------------------------
; Volume, legacy/PB1 Input, legacy Setup, and split Setup opt in.  Split PB2
; Input is excluded because its title row has dedicated old/lost labels.  The
; routine writes four tail characters at row 2 cols 13..16 only when the health
; state marks the display dirty, so a previous longer suffix is cleared before
; shorter/empty states without adding LCD work to every foreground tick.
; The BL Timeout editor shares the Setup page but sets 0x0A4 while active.
; Skip that live editor state so a dirty health flag cannot overwrite editor
; text such as the final "out)" of "Off (no timeout)".  Do not key this from
; 0x0A3:0x0A2; the menu helper leaves that pointer cached after exit.
; ---------------------------------------------------------------------------
v171_health_patch_suffix:
        movlb   0x01
        btfsc   v171_health_flags_b1, V171_HEALTH_FLAG_DISPLAY_DIRTY, BANKED
        bra     v171_health_patch_suffix_dirty
        movlb   0x00
        return  0x0
v171_health_patch_suffix_dirty:
        movlb   0x00
        btfss   control_flags_acc, CONNECTED, A
        return  0x0
        movlw   0x01
        cpfseq  display_state_index_b0, BANKED
        bra     v171_health_patch_suffix_not_preset
        return  0x0
v171_health_patch_suffix_not_preset:
        movlw   0x03
        cpfslt  display_state_index_b0, BANKED
        bra     v171_health_patch_suffix_check_state3
        bra     v171_health_patch_suffix_top_level
v171_health_patch_suffix_check_state3:
        movlw   0x03
        cpfseq  display_state_index_b0, BANKED
        bra     v171_health_patch_suffix_check_state4
        movlb   0x01
        btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     v171_health_patch_suffix_return_b0
        movlb   0x00
        bra     v171_health_patch_suffix_setup_gate
v171_health_patch_suffix_check_state4:
        movlw   0x04
        cpfseq  display_state_index_b0, BANKED
        return  0x0
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     v171_health_patch_suffix_return_b0
        movlb   0x00
v171_health_patch_suffix_setup_gate:
        movf    menu_option_max_index_b0, F, B
        bz      v171_health_patch_suffix_top_level
        return  0x0
v171_health_patch_suffix_return_b0:
        movlb   0x00
        return  0x0
v171_health_patch_suffix_top_level:
        movlb   0x01
        clrf    v171_health_suffix_mask_b1, BANKED              ; suffix mask
        movlw   V171_HEALTH_STALE_AGE
        cpfslt  v171_health_age_pb1_b1, BANKED                 ; age < stale? skip
        bsf     v171_health_suffix_mask_b1, 0, BANKED
        movlw   V171_HEALTH_STALE_AGE
        cpfslt  v171_health_age_pb2_b1, BANKED
        bsf     v171_health_suffix_mask_b1, 1, BANKED
        ; If PB1 is stale and PB2 has missed any health bucket, the ring
        ; cannot prove PB2 is currently reachable through PB1.  Surface the
        ; shared-path uncertainty as !1 2 instead of a misleading narrow !1.
        btfss   v171_health_suffix_mask_b1, 0, BANKED
        bra     v171_health_patch_have_mask
        movf    v171_health_age_pb2_b1, F, BANKED
        bz      v171_health_patch_have_mask
        bsf     v171_health_suffix_mask_b1, 1, BANKED
v171_health_patch_have_mask:
        ; V1.73 (task #7): the GIE mask that used to wrap this five-byte
        ; suffix patch is retired.  It existed because the blocking in-ISR
        ; RC5 decode clobbered the LCD helpers' access-bank scratch; the
        ; ISR now saves/restores that scratch around the decode, so an IR
        ; frame mid-patch decodes correctly AND the patch's cursor/delay
        ; state survives.  Masking here only made the remote deaf for the
        ; patch duration.
        movlw   0x80
        movwf   (Common_RAM + 1), A
        movlw   0xCC                                        ; row 2 col 13 (1-based)
        call    lcd_command, 0x0
        movlb   0x01
        movlw   0x03
        cpfseq  v171_health_suffix_mask_b1, BANKED
        bra     v171_health_patch_not_both
        movlb   0x00
        movlw   '!'
        call    lcd_char_write, 0x0
        movlw   '1'
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   '2'
        call    lcd_char_write, 0x0
        bra     v171_health_patch_done
v171_health_patch_not_both:
        movlb   0x01
        movf    v171_health_suffix_mask_b1, F, BANKED
        bz      v171_health_patch_clear
        movlb   0x00
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   '!'
        call    lcd_char_write, 0x0
        movlb   0x01
        movlw   '1'
        btfsc   v171_health_suffix_mask_b1, 1, BANKED
        movlw   '2'
        movlb   0x00
        call    lcd_char_write, 0x0
        bra     v171_health_patch_done
v171_health_patch_clear:
        movlb   0x00
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
v171_health_patch_done:
        movlb   0x01
        bcf     v171_health_flags_b1, V171_HEALTH_FLAG_DISPLAY_DIRTY, BANKED
        movlb   0x00
        return  0x0

; ---------------------------------------------------------------------------
; v171_health_diag_check_stale -- classify rendered PB freshness for Diag.
; ---------------------------------------------------------------------------
; out: (Common_RAM + 4) = 0 fresh/unknown, 1 old, 2 lost.  Reads the
; current v171_diag_render_pb_index and the corresponding health age.
; ---------------------------------------------------------------------------
v171_health_diag_check_stale:
        clrf    (Common_RAM + 4), A
        movlb   0x01
        btfsc   v171_diag_render_pb_index_b1, 0, BANKED
        bra     v171_health_diag_check_pb2
        movf    v171_health_age_pb1_b1, W, BANKED
        bra     v171_health_diag_check_have_age
v171_health_diag_check_pb2:
        movlw   V171_HEALTH_STALE_AGE
        cpfslt  v171_health_age_pb1_b1, BANKED
        bra     v171_health_diag_check_pb2_shared
        movf    v171_health_age_pb2_b1, W, BANKED
        bra     v171_health_diag_check_have_age
v171_health_diag_check_pb2_shared:
        movf    v171_health_age_pb2_b1, F, BANKED
        bz      v171_health_diag_check_pb2_fresh_after_pb1
        movf    v171_health_age_pb1_b1, W, BANKED
        bra     v171_health_diag_check_have_age
v171_health_diag_check_pb2_fresh_after_pb1:
        movf    v171_health_age_pb2_b1, W, BANKED
v171_health_diag_check_have_age:
        movwf   v171_health_age_tmp_b1, BANKED
        movlw   V171_HEALTH_LOST_AGE
        cpfslt  v171_health_age_tmp_b1, BANKED
        bra     v171_health_diag_check_lost
        movlw   V171_HEALTH_STALE_AGE
        cpfslt  v171_health_age_tmp_b1, BANKED
        bra     v171_health_diag_check_old
        movlb   0x00
        return  0x0
v171_health_diag_check_old:
        movlw   0x01
        movwf   (Common_RAM + 4), A
        movlb   0x00
        return  0x0
v171_health_diag_check_lost:
        movlw   0x02
        movwf   (Common_RAM + 4), A
        movlb   0x00
        return  0x0


ir_profile_apply_cmd1d_mapping:                                               ; address: 0x000f54

        movlw   0x04
        cpfseq  cmd1d_setting_cache_b0, B                                     ; reg: 0x0a7
        goto    ir_profile_apply_cmd1d_mapping__maybe_profile3                                   ; dest: 0x000f7c
        movlw   0x10                                        ; RC5 0x10 volume up
        movwf   (Common_RAM + 32), A                        ; reg: 0x020
        movlw   0x32
        movwf   (Common_RAM + 33), A                        ; reg: 0x021
        movlw   0x33
        movwf   (Common_RAM + 34), A                        ; reg: 0x022
        movlw   0x34
        movwf   (Common_RAM + 35), A                        ; reg: 0x023
        movlw   0x35
        movwf   (Common_RAM + 38), A                        ; reg: 0x026
        movlw   0x36
        movwf   (Common_RAM + 36), A                        ; reg: 0x024
        movlw   0x37
        movwf   (Common_RAM + 37), A                        ; reg: 0x025
        goto    ir_profile_apply_cmd1d_mapping__return                                   ; dest: 0x000f9e

ir_profile_apply_cmd1d_mapping__maybe_profile3:                                                  ; address: 0x000f7c

        movlw   0x03
        cpfseq  cmd1d_setting_cache_b0, B                                     ; reg: 0x0a7
        goto    ir_profile_apply_cmd1d_mapping__return                                   ; dest: 0x000f9e
        clrf    (Common_RAM + 32), A                        ; reg: 0x020
        movlw   0x0c                                        ; RC5 0x0C standby toggle
        movwf   (Common_RAM + 33), A                        ; reg: 0x021
        movlw   0x10                                        ; RC5 0x10 volume up
        movwf   (Common_RAM + 34), A                        ; reg: 0x022
        movlw   0x11                                        ; RC5 0x11 volume down
        movwf   (Common_RAM + 35), A                        ; reg: 0x023
        movlw   0x20                                        ; RC5 0x20 preset next
        movwf   (Common_RAM + 36), A                        ; reg: 0x024
        movlw   0x21                                        ; RC5 0x21 preset prev / channel down
        movwf   (Common_RAM + 37), A                        ; reg: 0x025
        movlw   0x0d
        movwf   (Common_RAM + 38), A                        ; reg: 0x026

ir_profile_apply_cmd1d_mapping__return:                                                  ; address: 0x000f9e

        return  0x0

menu_option_editor_wait_and_update:                                               ; address: 0x000fa0

        movff   0x0a2, (Common_RAM + 41)                    ; reg2: 0x029
        movff   0x0a3, (Common_RAM + 42)                    ; reg2: 0x02a
        movff   0x0a5, tx_data_staging_b0_phys                    ; reg2: 0x027
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc0
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    lcd_write_16char_rom_entry, 0x0                           ; dest: 0x000940

menu_option_editor__wait_for_input_or_event:                                                  ; address: 0x000fba

        ; Phase 3.4: rcall → call promotion.  v171_diag_pb_screen +
        ; sparse renderer added ~300 bytes ahead of this site, pushing
        ; the relative offset to display_loop_iteration past the bra/
        ; rcall ±1024-instruction limit.  call uses absolute 21-bit
        ; addressing so it's range-immune; semantics are identical.
        call    display_loop_iteration, 0x0                ; dest: 0x000cb2
        movlw   0x00
        movf    button_event_latch_b0, F, B                                  ; reg: 0x09a
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   control_flags_acc, 0x3, A                   ; reg: 0x01f
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     menu_option_editor__wait_for_input_or_event                                   ; dest: 0x000fba
        rrcf    button_event_latch_b0, W, B                                  ; reg: 0x09a
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    menu_option_editor__maybe_decrement_index                                   ; dest: 0x000fec
        movf    menu_option_selected_index_b0, W, B                                  ; reg: 0x0a5
        cpfseq  menu_option_max_index_b0, B                                     ; reg: 0x0a4
        goto    menu_option_editor__increment_index                                   ; dest: 0x000fea
        clrf    menu_option_selected_index_b0, B                                     ; reg: 0x0a5
        goto    menu_option_editor__maybe_decrement_index                                   ; dest: 0x000fec

menu_option_editor__increment_index:                                                  ; address: 0x000fea

        incf    menu_option_selected_index_b0, F, B                                  ; reg: 0x0a5

menu_option_editor__maybe_decrement_index:                                                  ; address: 0x000fec

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   button_event_latch_b0, 0x2, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    menu_option_editor__return                                   ; dest: 0x00100a
        movf    menu_option_selected_index_b0, F, B                                  ; reg: 0x0a5
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    menu_option_editor__decrement_index                                   ; dest: 0x001008
        movff   0x0a4, 0x0a5
        goto    menu_option_editor__return                                   ; dest: 0x00100a

menu_option_editor__decrement_index:                                                  ; address: 0x001008

        decf    menu_option_selected_index_b0, F, B                                  ; reg: 0x0a5

menu_option_editor__return:                                                  ; address: 0x00100a

        return  0x0
menu_title_table:                                                  ; address: 0x00100c  (tblptr anchor)
        movwf   (Common_RAM + 86), B                        ; reg: 0x056
        btg     0x6c, 0x2, B                                ; reg: 0x06c
        cpfsgt  0x6d, B                                     ; reg: 0x06d
        addwfc  (Common_RAM + 58), W, A                     ; reg: 0x03a
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movwf   (Common_RAM + 73), A                        ; reg: 0x049
        btg     0x70, 0x2, B                                ; reg: 0x070
        swapf   0x74, F, A                                  ; reg: 0xf74
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        cpfsgt  (Common_RAM + 83), B                        ; reg: 0x053
        btg     0x74, 0x2, B                                ; reg: 0x074
        addwfc  0x70, W, A                                  ; reg: 0xf70
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020

app_cold_init__clear_diag_health_and_filename_state:                                                  ; address: 0x00103c

        ; ---------------------------------------------------------------
        ; Bug #44 fix: zero V1.72 Tier-1 diag cache cells once at POR.
        ; ---------------------------------------------------------------
        ; Without this, the cache cells at 0x180..0x195 (PB1+PB2 diag
        ; values), 0x196..0x197 (target/present), and 0x19D
        ; (reset_seen) start at random POR RAM.  If a BF/2N reply burst
        ; from MAIN drops some frames (the parser-stall watchdog
        ; v171_service_rx_frame_gap can fire mid-frame on tight bursts),
        ; the cells for dropped frames keep their POR garbage and the
        ; LCD renders values that disagree with cmd 0x44's direct read
        ; of MAIN's BANK 2 (cmd 0x44 reads MAIN's BANK 2 directly via
        ; USB HID, never crossing the BF/2N path).  See
        ; docs/analysis/TASK_44_LCD_VS_CMD44_DIVERGENCE.md.
        ;
        ; Loop form: 24 contiguous cells (0x180..0x197) cleared via
        ; FSR0 + POSTINC0; sparse diag transaction cells above 0x197
        ; are cleared separately.
        ; +20 bytes total; runs once at POR / cold-init exit (NOT in
        ; app_cold_init body proper, because adding code there shifts
        ; isr_entry past 0x0003a6 and breaks the byte-identical vector
        ; block contract gated by test_v171_layer1_vector_block_byte_identical).
        lfsr    0x0, v171_diag_pb1_i_b1_phys                                  ; FSR0 -> first cache cell
        movlw   0x18                                        ; 24 cells (0x180..0x197 inclusive)
        movwf   (Common_RAM + 15), A                        ; transient loop counter
app_cold_init__zero_next_diag_cache_cell:
        clrf    POSTINC0, A                                 ; *FSR0++ = 0
        decfsz  (Common_RAM + 15), F, A
        bra     app_cold_init__zero_next_diag_cache_cell
        movlb   0x01                                        ; reset_seen lives in bank 1
        clrf    v171_diag_reset_seen_b1, BANKED                ; physical 0x19D
        clrf    v171_diag_flags_b1, BANKED                     ; physical 0x19C
        clrf    v171_diag_reset_target_b1, BANKED              ; physical 0x19E
        clrf    v171_diag_reset_timeout_b1, BANKED             ; physical 0x19F
        clrf    v171_diag_runtime_target_b1, BANKED            ; physical 0x1AE
        clrf    v171_diag_runtime_timeout_b1, BANKED           ; physical 0x1AF
        clrf    v171_health_age_pb1_b1, BANKED                 ; link health starts unknown/fresh
        clrf    v171_health_age_pb2_b1, BANKED
        clrf    v171_health_seen_mask_b1, BANKED
        clrf    v171_health_flags_b1, BANKED
        clrf    v171_health_poll_target_b1, BANKED
        clrf    v171_health_tick_div_b1, BANKED
        clrf    input_split_flags_b1, BANKED
        clrf    input_intent_pb2_b1, BANKED
        clrf    input_send_target_b1, BANKED
        clrf    input_pending_pb2_b1, BANKED
        call    v172_fname_cold_clear, 0x0
        movlb   0x00                                        ; restore default bank
        ; --- end Bug #44 fix ---

        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bcf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        movlw   0x0a
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        clrf    (Common_RAM + 28), A                        ; reg: 0x01c
        bsf     IOCB, IOCB5, A                              ; reg: 0xf7d, bit: 5
        bcf     INTCON, RBIF, A                             ; reg: 0xff2, bit: 0
        bcf     INTCON, RBIE, A                             ; reg: 0xff2, bit: 3
        bsf     PIE1, RCIE, A                               ; reg: 0xf9d, bit: 5
        bsf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        bsf     INTCON, PEIE, A                             ; reg: 0xff2, bit: 6
        clrf    tx_ring_rd_b0, B                                     ; reg: 0x096
        clrf    tx_ring_wr_b0, B                                     ; reg: 0x097
        clrf    rx_ring_rd_b0, B                                     ; reg: 0x098
        clrf    rx_ring_wr_b0, B                                     ; reg: 0x099
        bcf     control_flags_acc, 0x2, A                   ; reg: 0x01f
        clrf    rx_frame_position_b0, B                                     ; reg: 0x0a6
        clrf    ir_decoded_cmd_acc, A                        ; reg: 0x01d
        clrf    ir_decoded_cmd_acc, A                        ; reg: 0x01d
        clrf    ir_decoded_addr_acc, A                        ; reg: 0x01e
        clrf    button_repeat_timer_lo_b0, B                                     ; reg: 0x09b
        clrf    button_repeat_timer_hi_b0, B                                     ; reg: 0x09c
        lfsr    0x0, saved_settings_base_b0_phys
        movlw   0x06

app_cold_init__zero_saved_settings_c1_block:                                                  ; address: 0x00106e

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     app_cold_init__zero_saved_settings_c1_block                                   ; dest: 0x00106e
        lfsr    0x0, stock_0C7_b0_phys
        movlw   0x06

app_cold_init__zero_saved_settings_c7_block:                                                  ; address: 0x00107a

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     app_cold_init__zero_saved_settings_c7_block                                   ; dest: 0x00107a
        lfsr    0x0, stock_0CD_b0_phys
        movlw   0x06

app_cold_init__zero_saved_settings_cd_block:                                                  ; address: 0x001086

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     app_cold_init__zero_saved_settings_cd_block                                   ; dest: 0x001086
        lfsr    0x0, stock_0D3_b0_phys
        movlw   0x06

app_cold_init__zero_saved_settings_d3_block:                                                  ; address: 0x001092

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     app_cold_init__zero_saved_settings_d3_block                                   ; dest: 0x001092
        lfsr    0x0, stock_0D9_b0_phys
        movlw   0x06

app_cold_init__zero_saved_settings_d9_block:                                                  ; address: 0x00109e

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     app_cold_init__zero_saved_settings_d9_block                                   ; dest: 0x00109e
        lfsr    0x0, stock_0DF_b0_phys
        movlw   0x06

app_cold_init__zero_saved_settings_df_block_and_version_eeprom:                                                  ; address: 0x0010aa

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     app_cold_init__zero_saved_settings_df_block_and_version_eeprom                                   ; dest: 0x0010aa
        clrf    (Common_RAM + 50), A                        ; reg: 0x032
        bcf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        bcf     control_flags_acc, 0x4, A                   ; reg: 0x01f
        setf    EEADR, A                                    ; reg: 0xfa9
        movlw   0x02
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x70
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        movlw   0x01
        subwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    app_cold_init__ensure_control_minor_eeprom                                   ; dest: 0x0010da
        movlw   0x70
        movwf   EEADR, A                                    ; reg: 0xfa9
        movlw   0x01
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2

app_cold_init__ensure_control_minor_eeprom:                                                  ; address: 0x0010da

        movlw   0x71
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        movlw   0x07                                        ; V1.72 minor byte
        subwf   tx_data_staging_acc, W, A                     ; reg: 0x027
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    app_cold_init__clear_buttons_and_identity_cache                                   ; dest: 0x0010f6
        movlw   0x71
        movwf   EEADR, A                                    ; reg: 0xfa9
        movlw   0x07
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2

app_cold_init__clear_buttons_and_identity_cache:                                                  ; address: 0x0010f6

        clrf    button_last_scan_b0, B                                     ; reg: 0x0bc
        clrf    button_debounced_b0, B                                     ; reg: 0x0be
        clrf    button_debounced_prev_b0, B                                     ; reg: 0x0bd
        clrf    mute_blink_counter_lo_b0, B                                     ; reg: 0x0b4
        clrf    mute_blink_counter_hi_b0, B                                     ; reg: 0x0b5
        clrf    backlight_elapsed_hi_b0, B                                     ; reg: 0x0b3
        clrf    backlight_elapsed_mid_hi_b0, B                                     ; reg: 0x0b2
        clrf    backlight_elapsed_mid_lo_b0, B                                     ; reg: 0x0b1
        clrf    backlight_elapsed_lo_b0, B                                     ; reg: 0x0b0
        lfsr    0x0, v172_diag_id_pb1_major_b2_phys                                  ; V1.72 identity cache
        movlw   0x10
        movwf   (Common_RAM + 4), A
v172_clear_identity_cache_loop:
        clrf    POSTINC0, A
        decfsz  (Common_RAM + 4), F, A
        bra     v172_clear_identity_cache_loop
        lfsr    0x0, v173_diag_id_pb1_rev_hi_b2_phys                         ; V1.73 identity rev16 extension
        movlw   0x03
        movwf   (Common_RAM + 4), A
v173_clear_identity_ext_loop:
        clrf    POSTINC0, A
        decfsz  (Common_RAM + 4), F, A
        bra     v173_clear_identity_ext_loop
        movlw   0x01
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0x2c
        call    delay_short_16bit_countdown_from_w, 0x0                           ; dest: 0x0001be
        call    app_entry_defensive_stub, 0x0                           ; dest: 0x00004c
        movlw   0xc8
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    settings_load_eeprom, 0x0                           ; dest: 0x000a46

        ; ---------------------------------------------------------------
        ; V1.72 inline (V1.61b): stale Setup-index migration
        ; ---------------------------------------------------------------
        ; Stock V1.6b kept restoring EEPROM[0x01] into 0x0BA even after
        ; Setup was reduced to one visible item ("BL Timeout").  Field
        ; units upgraded from older CONTROL releases may retain a
        ; nonzero value there; if left live, the Setup renderer indexes
        ; past the single valid row and prints code bytes as LCD text.
        ; Mirror the V1.61b binary-patch behavior: clamp RAM and scrub
        ; EEPROM[0x01] once, immediately after the stock settings load.
        movlb   0x00                                        ; 0x0BA is bank-0 setup_sub
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        bz      v171_setup_index_clamp_done
        clrf    setup_submenu_index_b0, B                                     ; reg: 0x0ba
        movlw   0x01
        movwf   EEADR, A                                    ; reg: 0xfa9
        clrf    WREG, A                                     ; reg: 0xfe8
        call    eeprom_write_byte, 0x0                       ; dest: 0x0001a2
v171_setup_index_clamp_done:

        ; ---------------------------------------------------------------
        ; V1.72 inline (V1.61b): preset boot init
        ; ---------------------------------------------------------------
        ; Read persisted preset byte from EEPROM slot 0x74 and reflect
        ; it into control_flags.PRESET_BIT so the rest of the boot path
        ; sees the last-saved preset state.  EEPROM byte 0x01 means
        ; preset B; any other value (typically 0x00 or erased 0xFF) is
        ; preset A.  The IR dispatch inline helper
        ; (v171_send_preset_frame_and_persist) writes the same encoding.
        movlw   EEPROM_PRESET_STATE_ADDR                      ; 0x74
        call    eeprom_read_byte, 0x0
        bcf     control_flags_acc, PRESET_BIT, A                 ; default = preset A
        xorlw   0x01
        bnz     v171_preset_boot_init_done
        bsf     control_flags_acc, PRESET_BIT, A                 ; byte was 0x01 → preset B
v171_preset_boot_init_done:

        movlw   0x01
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0xf4
        call    delay_short_16bit_countdown_from_w, 0x0                           ; dest: 0x0001be
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movlw   HIGH(control_release_banner_row1)                  ; baked release banner row 1
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   LOW(control_release_banner_row1)                   ; baked release banner row 1
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        call    lcd_string_write_rom, 0x0                           ; dest: 0x0000dc
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc0                                        ; row 2
        call    lcd_command, 0x0
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   HIGH(control_release_banner_row2)                  ; baked release banner row 2
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   LOW(control_release_banner_row2)                   ; baked release banner row 2
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        call    lcd_string_write_rom, 0x0                           ; dest: 0x0000dc
        movlw   0x03
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0xe8
        call    delay_short_16bit_countdown_from_w, 0x0                           ; dest: 0x0001be
        movlw   0x80
        movwf   input_select_cache_b0, B                                     ; reg: 0x0b8
        movwf   volume_cache_b0, B                                     ; reg: 0x0b9
        movwf   cmd1d_setting_cache_b0, B                                     ; reg: 0x0a7
        movwf   raw_status_cache_b0, B                                     ; reg: 0x0a1
        clrf    v171_waiting_grace_count_lo_b0, B              ; reset 16-bit grace counter (lo)
        clrf    v171_waiting_grace_count_hi_b0, B              ; reset 16-bit grace counter (hi)
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movlw   HIGH(lcd_str_waiting_for_dlcp)                          ; shifted via label
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   LOW(lcd_str_waiting_for_dlcp)                           ; shifted via label
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        call    lcd_string_write_rom, 0x0                           ; dest: 0x0000dc
        call    v171_clear_lcd_row2, 0x0
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bsf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        ; V1.73 round-2 (docs/analysis/CONNECTED_WAITING_WAKE_DELAY_2026-06-10):
        ; the stock open-loop banner delay that sat here (01BE count 0x0FA0,
        ; ~11 s measured at 2.79 ms/unit) is DELETED.  It predated the
        ; closed-loop WAITING machinery and left the foreground dead for its
        ; whole duration (no polls, no RX parsing -- the 47-byte ring
        ; overflows -- no buttons, no IR re-arm).  The cold WAITING loop
        ; below owns the wait: it polls, parses, services IR, and exits on
        ; the four-sentinel boot handshake.  The loop label keeps its
        ; historical 0FA0 name from the deleted delay constant.

boot_waiting_for_dlcp_loop:                                                  ; address: 0x00118c

        ; BUG-V34V173-3: WAITING owns the physical LCD now -- drop Preset
        ; row-0 readiness + filename cache (idempotent; runs per iteration
        ; because this label is also the loop-back target).
        call    v173_preset_lcd_invalidate, 0x0

        ; ---------------------------------------------------------------
        ; V1.72 WAITING-loop operator-recovery (2026-04-21)
        ; ---------------------------------------------------------------
        ; Stock V1.6b/V1.7x WAITING FOR DLCP loop has NO button-poll and
        ; NO timeout: if MAIN stops emitting the boot-handshake sentinel
        ; burst (BF/05/06/07/1D) -- e.g., after STDBY+WAKE, where MAIN
        ; resumes normal heartbeats but doesn't re-emit the initial
        ; burst that clears CONTROL's 4 sentinel caches -- CONTROL is
        ; locked here forever, LCD frozen on "WAITING FOR DLCP", buttons
        ; dead.  Only power-cycle recovers.
        ;
        ; Recovery mechanism: after a ~10 s grace period (counted in
        ; loop iterations, see V171_WAITING_GRACE_THRESHOLD_HI), RIGHT
        ; (0x9A.5) or LEFT (0x9A.4) press triggers a soft CPU `reset`.
        ; The resulting cold-boot path re-primes all four sentinel
        ; caches to 0x80, re-emits the CONTROL->MAIN full_sync_burst,
        ; and re-enters this loop with a clean slate.  MAIN normally
        ; answers each full-sync frame with a status frame that clears
        ; the corresponding sentinel -- so the second pass usually
        ; succeeds even if MAIN never emitted the original post-wake
        ; burst.
        ;
        ; Why the grace period: during normal cold boot MAIN takes
        ; a few seconds to initialize before emitting its sentinel
        ; burst, and the operator may already be touching buttons
        ; (e.g., power-cycling the system).  Without the grace gate,
        ; a spurious button press during that window would
        ; accidentally soft-reset CONTROL.  The 16-bit saturating
        ; counter v171_waiting_grace_count_lo/hi (cleared to 0 on loop
        ; entry, bumped once per iteration, gate arms once the high
        ; byte reaches V171_WAITING_GRACE_THRESHOLD_HI = 4 i.e. 1024
        ; iterations ~= 10.24 s at the ~10 ms/iter delay_short(0xC8))
        ; arms the reset only once the loop has been stuck long enough
        ; that the operator's button press is clearly intentional.
        ;
        ; Why `reset` instead of clearing the caches in place: the
        ; 4 cells (0xB8/0xB9/0xA7/0xA1) are NOT "unset/default"
        ; markers; they are live payloads re-transmitted to MAIN and
        ; rendered on the LCD (e.g., 0xB9=0 displays as "-96.0 dB"
        ; in standby_display).  Clearing them in place would both
        ; emit bogus frames to MAIN and pollute future reconnect
        ; checks (reconnect loop at 0x4679 also exits on "!=0x80"
        ; and the cells only re-prime to 0x80 at cold boot).  A
        ; full soft-reset is the only clean way to restore the
        ; sentinel semantics.
        ;
        ; This does NOT fix the underlying MAIN-side reconnect bug;
        ; that's a V3.2 MAIN change to re-emit the sentinel burst on
        ; wake.  It does fix the user-facing deadlock: operator now
        ; has a guaranteed recovery without cold-booting both MAINs.
        ;
        ; Use button_scan_debounce rather than display_loop_iteration:
        ; display_loop_iteration is a MODAL loop that parks internally
        ; until 0x9A != 0 or control_flags.3 is set (see the tail at
        ; asm:2703-2715 where it branches back to 0CB4).  In the
        ; WAITING state, control_flags.3 is clear and no button is
        ; pressed, so display_loop_iteration would never return --
        ; which would freeze poll_frame_send / rx_parser_entry below
        ; and defeat the whole loop.  button_scan_debounce is the
        ; underlying one-shot that updates the 0x9A event latch;
        ; calling it here lets the loop keep polling MAIN while the
        ; button bitmap stays fresh.
        call    button_scan_debounce, 0x0                  ; one-shot: updates 0x9A
        movlb   0x00                                       ; BSR may have drifted
        ; 16-bit saturating grace counter:
        ;  - if grace_hi >= V171_WAITING_GRACE_THRESHOLD_HI (4), the
        ;    gate is armed: skip the bump, fall through to button test
        ;  - else bump the 16-bit counter (lo first; on lo wrap, hi++)
        ;    and skip the button test (still in grace)
        movlw   V171_WAITING_GRACE_THRESHOLD_HI
        cpfslt  v171_waiting_grace_count_hi_b0, B             ; skip if hi <  threshold_hi
        bra     v171_waiting_cold_armed                    ; hi >= threshold_hi -> armed
        infsnz  v171_waiting_grace_count_lo_b0, F, B          ; bump lo; skip if lo != 0
        incf    v171_waiting_grace_count_hi_b0, F, B          ; lo wrapped -> bump hi
        bra     v171_waiting_cold_past_grace_done          ; still in grace, no buttons
v171_waiting_cold_armed:
        btfsc   button_event_latch_b0, 0x5, B                               ; RIGHT pressed?
        reset                                              ; soft CPU reset
        btfsc   button_event_latch_b0, 0x4, B                               ; LEFT pressed?
        reset                                              ; soft CPU reset
v171_waiting_cold_past_grace_done:

        call    poll_frame_send, 0x0                           ; dest: 0x000b64
        movlw   0xc8
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    rx_parser_entry, 0x0                           ; dest: 0x00044a
        call    v171_service_rx_frame_gap, 0x0             ; cold WAITING parser stall guard (entry/exit movlb 0x0 absorbs rx_parser_entry BSR drift)
        call    v173_waiting_ir_service, 0x0               ; BUG-2: keep IR armed while WAITING
        movlw   0x80
        subwf   input_select_cache_b0, W, B                                  ; reg: 0x0b8
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        movlw   0x80
        subwf   volume_cache_b0, W, B                                  ; reg: 0x0b9
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        andwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        movlw   0x80
        subwf   cmd1d_setting_cache_b0, W, B                                  ; reg: 0x0a7
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        andwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        movlw   0x80
        subwf   raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        andwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     boot_waiting_for_dlcp_loop                                   ; dest: 0x00118c
        movlw   0x61
        movwf   idle_timeout_lo_b0, B                                     ; reg: 0x09d
        movlw   0xea
        movwf   idle_timeout_hi_b0, B                                     ; reg: 0x09e
        clrf    full_sync_lo_b0, B                                     ; reg: 0x09f
        clrf    full_sync_hi_b0, B                                     ; reg: 0x0a0
        bcf     control_flags_acc, 0x5, A                   ; reg: 0x01f
        movlw   0x01
        movwf   (Common_RAM + 50), A                        ; reg: 0x032

post_connect_init:                                                  ; address: 0x0011d8

        btfss   control_flags_acc, 0x1, A                   ; reg: 0x01f
        goto    display_state_entry__enter_standby_waiting                                   ; dest: 0x001250

post_connect_init__dispatch_current_page:                                                  ; address: 0x0011de

        bcf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        movf    display_state_index_b0, F, B                                  ; reg: 0x0bf
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    post_connect_init__non_volume_page_dispatch                                   ; dest: 0x0011f0
        call    volume_screen__draw_current_menu_title, 0x0                           ; dest: 0x0012d0
        goto    display_state_entry__handle_menu_next                                   ; dest: 0x00120a

post_connect_init__non_volume_page_dispatch:                                                  ; address: 0x0011f0

        ; ---------------------------------------------------------------
        ; V1.73 menu dispatch.  Before PB2 discovery this keeps the legacy
        ; 6-state V1.72 ring; after PB2 discovery it inserts Input PB2 as
        ; split state 3 and shifts Setup/PB1 Diag/PB2 Diag to 4/5/6.
        ; ---------------------------------------------------------------
        ; Legacy/PB2-unknown ring:
        ;   0 Volume, 1 Preset, 2 Input, 3 Setup, 4 PB1 Diag, 5 PB2 Diag.
        ; Split/PB2-seen ring:
        ;   0 Volume, 1 Preset, 2 Input PB1, 3 Input PB2, 4 Setup,
        ;   5 PB1 Diag, 6 PB2 Diag.
        movlb   0x00
        decfsz  display_state_index_b0, W, B                                  ; state - 1 == 0?
        goto    v171_menu_ck_state_2
        call    v171_preset_screen, 0x0                     ; state == 1 -> Preset
        goto    display_state_entry__handle_menu_next

v171_menu_ck_state_2:
        movlw   0x02
        cpfseq  display_state_index_b0, B
        goto    v171_menu_ck_state_3                        ; not 2 -- try state 3
        ; Tier-1: state 2 is now Input (was Diagnostics).
        call    input_screen, 0x0              ; state == 2 -> Input
        goto    display_state_entry__handle_menu_next

v171_menu_ck_state_3:
	        movlw   0x03
	        cpfseq  display_state_index_b0, B
	        goto    v171_menu_ck_state_4                        ; not 3 -- try state 4
	        movlb   0x01
	        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
	        bra     v171_menu_state_3_legacy_setup
	        movlb   0x00
	        call    input_screen, 0x0                           ; split state 3 -> Input PB2
	        goto    display_state_entry__handle_menu_next
v171_menu_state_3_legacy_setup:
	        movlb   0x00
	        ; Tier-1: legacy state 3 is Setup (was Input).
	        call    setup_screen, 0x0              ; state == 3 -> Setup
	        goto    display_state_entry__handle_menu_next

v171_menu_ck_state_4:
	        movlw   0x04
	        cpfseq  display_state_index_b0, B
	        goto    v171_menu_ck_state_5                       ; not 4 -- try state 5
	        movlb   0x01
	        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
	        bra     v171_menu_state_4_legacy_pb1_diag
	        movlb   0x00
	        call    setup_screen, 0x0                            ; split state 4 -> Setup
	        goto    display_state_entry__handle_menu_next
v171_menu_state_4_legacy_pb1_diag:
	        movlb   0x00
	        ; Tier-1: legacy state 4 = PB1 Diag (W = PB index 0).
	        movlw   0x00
	        call    v171_diag_pb_screen, 0x0
	        goto    display_state_entry__handle_menu_next

v171_menu_ck_state_5:                                                  ; address: 0x0011fe

	        movlw   0x05
	        cpfseq  display_state_index_b0, B                                     ; reg: 0x0bf
	        goto    v171_menu_ck_state_6
	        movlb   0x01
	        btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
	        bra     v171_menu_state_5_split_pb1_diag
	        movlb   0x00
	        ; Tier-1: legacy state 5 = PB2 Diag (W = PB index 1).
	        movlw   0x01
	        call    v171_diag_pb_screen, 0x0
	        goto    display_state_entry__handle_menu_next
v171_menu_state_5_split_pb1_diag:
	        movlb   0x00
	        movlw   0x00
	        call    v171_diag_pb_screen, 0x0                     ; split state 5 -> PB1 Diag
	        goto    display_state_entry__handle_menu_next

v171_menu_ck_state_6:
	        movlw   0x06
	        cpfseq  display_state_index_b0, B
	        goto    display_state_entry__handle_menu_next
	        movlw   0x01
	        call    v171_diag_pb_screen, 0x0                     ; split state 6 -> PB2 Diag

display_state_entry__handle_menu_next:                                                  ; address: 0x00120a

        movlb   0x00
        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   button_event_latch_b0, 0x5, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    display_state_entry__handle_menu_previous                                   ; dest: 0x001226
        ; Dynamic menu max: legacy/PB2-unknown wraps the 6-state
        ; Vol/Preset/Input/Setup/PB1Diag/PB2Diag ring at state 5.
        ; Split/PB2-seen inserts Input PB2 and wraps at state 6.
        call    input_menu_max_state_to_w
        cpfseq  display_state_index_b0, B                                     ; reg: 0x0bf
        goto    display_state_entry                                   ; dest: 0x001224
        clrf    display_state_index_b0, B                                     ; reg: 0x0bf
        goto    display_state_entry__handle_menu_previous                                   ; dest: 0x001226

display_state_entry:                                                  ; address: 0x001224

        incf    display_state_index_b0, F, B                                  ; reg: 0x0bf

display_state_entry__handle_menu_previous:                                                  ; address: 0x001226

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   button_event_latch_b0, 0x4, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    display_state_entry__rescan_and_route                                   ; dest: 0x001244
        movf    display_state_index_b0, F, B                                  ; reg: 0x0bf
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    display_state_entry__decrement_menu_state_for_previous                                   ; dest: 0x001242
        ; V1.72: nav UP wrap target bumped from 2 -> 3 (V1.61b ring),
        ; then Layer 5 bumped 3 -> 4 (5-state ring).  Tier-1 bumps it
        ; 4 -> 5 so the 6-state ring wraps cleanly (UP at state 0 ->
        ; state 5 = PB2 Diag).
        call    input_menu_max_state_to_w
        movwf   display_state_index_b0, B                                     ; reg: 0x0bf
        goto    display_state_entry__rescan_and_route                                   ; dest: 0x001244

display_state_entry__decrement_menu_state_for_previous:                                                  ; address: 0x001242

        decf    display_state_index_b0, F, B                                  ; reg: 0x0bf

display_state_entry__rescan_and_route:                                                  ; address: 0x001244

        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        btfsc   control_flags_acc, 0x1, A                   ; reg: 0x01f
        bra     post_connect_init__dispatch_current_page                                   ; dest: 0x0011de
        goto    reconnect_wait_loop__send_wake_and_rejoin                                   ; dest: 0x0012ce

display_state_entry__enter_standby_waiting:                                                  ; address: 0x001250

        bcf     control_flags_acc, 0x1, A                   ; reg: 0x01f
        ; BUG-V34V173-3: the standby zzz overlay replaces the Preset LCD owner.
        call    v173_preset_lcd_invalidate, 0x0
        call    standby_wake_broadcast, 0x0                           ; dest: 0x000c98
        call    app_entry_defensive_stub, 0x0                           ; dest: 0x00004c
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movlw   HIGH(lcd_str_standby_zzz)                          ; shifted via label
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   LOW(lcd_str_standby_zzz)                           ; shifted via label
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        call    lcd_string_write_rom, 0x0                           ; dest: 0x0000dc

display_state_entry__standby_wait_loop:                                                  ; address: 0x00126e

        call    display_loop_iteration, 0x0                           ; dest: 0x000cb2
        bcf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        movlw   0x00
        movf    button_event_latch_b0, F, B                                  ; reg: 0x09a
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   control_flags_acc, 0x1, A                   ; reg: 0x01f
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     display_state_entry__standby_wait_loop                                   ; dest: 0x00126e
        clrf    backlight_elapsed_hi_b0, B                                     ; reg: 0x0b3
        clrf    backlight_elapsed_mid_hi_b0, B                                     ; reg: 0x0b2
        clrf    backlight_elapsed_mid_lo_b0, B                                     ; reg: 0x0b1
        clrf    backlight_elapsed_lo_b0, B                                     ; reg: 0x0b0
        bsf     control_flags_acc, 0x1, A                   ; reg: 0x01f
        call    standby_wake_broadcast, 0x0                           ; dest: 0x000c98
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movlw   HIGH(lcd_str_waiting_for_dlcp_alt)                          ; shifted via label
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   LOW(lcd_str_waiting_for_dlcp_alt)                           ; shifted via label
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        call    lcd_string_write_rom, 0x0                           ; dest: 0x0000dc
        call    v171_clear_lcd_row2, 0x0
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bsf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        ; V1.73 round-2 (docs/analysis/CONNECTED_WAITING_WAKE_DELAY_2026-06-10):
        ; the stock open-loop wake banner delay that sat here (01BE count
        ; 0x1388, ~14 s measured at 2.79 ms/unit) is DELETED.  It ran with
        ; control_flags.bit1 still set -- producing the exploratory
        ; "connected + WAITING + intents dead" signature on every
        ; standby->wake -- and it merely open-loop-padded the MAIN wake
        ; bring-up (~8 s deaf adc_boot_gate window).  The reconnect loop
        ; below owns the wait: it polls every ~10 ms, parses, services IR,
        ; and exits on the first fresh-status evidence after MAIN answers.
        bcf     control_flags_acc, 0x1, A                   ; reg: 0x01f

reconnect_wait_loop:                                                  ; address: 0x0012bc

        ; ---------------------------------------------------------------
        ; V1.72 inline (V1.62b): full sentinel-driven reconnect loop
        ; ---------------------------------------------------------------
        ; Stock V1.6b just polled MAIN and waited for CONNECTED to rise.
        ; V1.62b expands this to:
        ;   - Every iteration: poll, wait 0xC8, run parser.
        ;   - Check 4 boot sentinels (input_select_cache 0xB8,
        ;     volume_cache 0xB9, cmd1d_setting_cache 0xA7,
        ;     raw_status_cache 0xA1): each is initialized to 0x80 and
        ;     clears to a legitimate value when MAIN emits the
        ;     corresponding BF reply.
        ;   - If ALL four sentinels are non-0x80 (i.e. cleared), exit.
        ;   - Otherwise increment the retry counter in bank-1 0x73.
        ;     Every 8 iterations, soft-recover UART to flush any
        ;     stalled RX state and keep trying.
        ;
        ; Zero bank-1 0x73 on entry so each reconnect attempt starts
        ; with a fresh retry counter.
        movlb   0x01
        clrf    stock_173_b1, BANKED
        ; ---------------------------------------------------------------
        ; V1.72 reconnect-loop operator-recovery grace counter (2026-04-21)
        ; ---------------------------------------------------------------
        ; Same mechanism as the cold-boot WAITING loop at asm:4448:
        ; after ~10 s stuck here, operator RIGHT/LEFT -> soft reset.
        ; Clear both bytes of the 16-bit grace counter on entry so
        ; each fresh reconnect attempt starts with a full grace
        ; window (prevents counter carry-over from a prior reconnect
        ; attempt being mistaken for a "still stuck" condition).
        ; This IS the loop that wedges after STDBY+WAKE when MAIN
        ; fails to re-emit its sentinel burst -- see the matching
        ; block's comment for the V3.2 MAIN-side root cause tracking.
        movlb   0x00
        clrf    v171_waiting_grace_count_lo_b0, B
        clrf    v171_waiting_grace_count_hi_b0, B
        ; BUG-V34V173-2: a fresh reconnect attempt starts with no liveness
        ; evidence; the RX parser sets mask bits as fresh frames arrive.
        clrf    v173_reconnect_fresh_status_mask_b0, B
        ; BUG-V34V173-3: the Waiting-for-DLCP overlay replaced the Preset
        ; LCD owner.
        call    v173_preset_lcd_invalidate, 0x0

v171_reconnect_wait_body:
        ; Refresh the debounced button event latch at 0x9A via the
        ; one-shot button_scan_debounce (NOT display_loop_iteration,
        ; which parks internally until 0x9A != 0 or control_flags.3
        ; -- neither is true during reconnect-wait, so it would
        ; never return, freezing the whole reconnect loop).  After
        ; this call the grace counter advances and the button gate
        ; below can arm the soft-reset escape.  Inline rather than
        ; sharing a routine with the cold-boot loop to avoid a call
        ; frame.
        call    button_scan_debounce, 0x0                  ; one-shot: updates 0x9A
        movlb   0x00                                       ; BSR may have drifted
        ; 16-bit saturating grace counter (same shape as the
        ; cold-boot WAITING loop at asm:4448).
        movlw   V171_WAITING_GRACE_THRESHOLD_HI
        cpfslt  v171_waiting_grace_count_hi_b0, B             ; skip if hi <  threshold_hi
        bra     v171_reconnect_armed                       ; hi >= threshold_hi -> armed
        infsnz  v171_waiting_grace_count_lo_b0, F, B          ; bump lo; skip if lo != 0
        incf    v171_waiting_grace_count_hi_b0, F, B          ; lo wrapped -> bump hi
        bra     v171_reconnect_past_grace_done             ; still in grace
v171_reconnect_armed:
        btfsc   button_event_latch_b0, 0x5, B                               ; RIGHT pressed?
        reset                                              ; soft CPU reset
        btfsc   button_event_latch_b0, 0x4, B                               ; LEFT pressed?
        reset                                              ; soft CPU reset
v171_reconnect_past_grace_done:
        movlb   0x00
        call    poll_frame_send, 0x0                           ; dest: 0x000b64
        movlw   0xc8
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    rx_parser_entry, 0x0                           ; dest: 0x00044a
        call    v171_service_rx_frame_gap, 0x0             ; reconnect WAITING parser stall guard (entry/exit movlb 0x0 absorbs rx_parser_entry BSR drift)
        call    v173_waiting_ir_service, 0x0               ; BUG-2: keep IR armed while WAITING

        ; BUG-V34V173-2: exit only on link evidence freshly observed during
        ; THIS reconnect attempt.  v173_reconnect_fresh_status_mask is
        ; cleared at reconnect entry and set by the RX parser on a BF/05
        ; status-poll answer (bit0) or a BF/03/01 wake echo (bit1) -- the
        ; B1/04 poll emitted above bypasses MAIN's active gate, so even a
        ; MAIN still in standby answers within one iteration.
        ; The legacy four-sentinel compare (input/volume/cmd1d/raw_status
        ; all != 0x80) measured STALE prior-session cache values: the 0x80
        ; sentinel seed happens exactly once at cold boot, so after any
        ; connected session the compare was vacuously true on the first
        ; iteration and the loop "reconnected" without MAIN answering at
        ; all.  (The V1.72 Bug #45 AND-reduce fix made that compare work
        ; mechanically; this change makes the exit meaningful.  The cold
        ; WAITING loop keeps its sentinel handshake -- there the seed is
        ; fresh.)
        ; Round-2: the exit requires bit0 -- a real status-poll ANSWER.
        ; bit1 (wake echo) is telemetry only: MAIN V3.4 now re-broadcasts
        ; the wake downstream BEFORE its deaf adc_boot_gate window
        ; (parallel two-MAIN wake), so the forwarded B0/03/01 reliably
        ; reaches CONTROL seconds before either MAIN can answer polls;
        ; exiting on the echo would resume the display against a
        ; still-deaf chain and bounce back into WAITING on idle timeout.
        btfsc   v173_reconnect_fresh_status_mask_b0, 0, B
        bra     v171_reconnect_wait_done                    ; fresh poll answer -> connected

        ; Not done yet — increment retry counter.
        movlb   0x01
        incf    stock_173_b1, F, BANKED
        movlw   0x08
        cpfseq  stock_173_b1, BANKED
        bra     v171_reconnect_wait_body                    ; still under 8 — keep polling
        clrf    stock_173_b1, BANKED                                ; 8 retries hit — reset counter

        ; 8 polls without full sentinel clear → kick the UART through
        ; the full V1.62b soft-recover.  The parser-entry inline
        ; already knows how to do this on an OERR latch, so force an
        ; OERR by toggling CREN and let the head of rx_parser_entry
        ; run its recovery on the next loop iteration.
        bcf     RCSTA, CREN, A
        movf    RCREG, W, A
        movf    RCREG, W, A
        bsf     RCSTA, CREN, A
        movlb   0x00
        clrf    tx_ring_rd_b0, BANKED
        clrf    tx_ring_wr_b0, BANKED
        clrf    rx_ring_rd_b0, BANKED
        clrf    rx_ring_wr_b0, BANKED
        clrf    rx_frame_position_b0, BANKED
        clrf    v171_rx_frame_gap_timeout_b0, BANKED
        clrf    rx_parsed_cmd_acc, A
        clrf    rx_parsed_data_acc, A
        bra     v171_reconnect_wait_body

v171_reconnect_wait_done:
        movlb   0x01
        clrf    stock_173_b1, BANKED                                ; clear retry counter
        clrf    v171_health_age_pb1_b1, BANKED                 ; wake/reconnect health unknown
        clrf    v171_health_age_pb2_b1, BANKED
        clrf    v171_health_seen_mask_b1, BANKED
        clrf    v171_health_flags_b1, BANKED
        clrf    v171_health_poll_target_b1, BANKED
        clrf    v171_health_tick_div_b1, BANKED
        movlb   0x00
        bsf     control_flags_acc, CONNECTED, A                ; mark connected

reconnect_wait_loop__send_wake_and_rejoin:                                                  ; address: 0x0012ce

        ; V1.72 (V1.62b): wake frame on reconnect exit (closes the
        ; V162B_RECONNECT_WAKE_BUG gap) plus the V1.62b state re-init:
        ; reload idle timer to stock 0xEA61, zero the full-sync
        ; counter for an immediate burst, clear RECONNECT_WAIT_DONE
        ; (bit 5) and seed control_flags bit 0x032 = 1 so the
        ; post-connect path resumes correctly.
        ;
        ; V1.72 Layer B (atomic 3-byte fix): if the wake broadcast hit
        ; a saturated TX ring (post-sentinel-clear traffic storm), the
        ; atomic sender in serial_tx_routed_frame returns C=1 with
        ; zero bytes on the wire.  Previously this was silently
        ; ignored, leaving MAIN gates closed and the next user commands
        ; dropped until the next full_sync_burst step-5 re-emit
        ; (~480 ms later).  Robust fix: re-enter reconnect_wait_loop on
        ; saturation — its mandatory `delay_short 0xC8` (~10 ms per
        ; iteration) drains the TX ring while it polls MAIN, giving
        ; transient saturation a fast in-band recovery path.
        ;
        ; Note on grace-window interaction: reconnect_wait_loop clears
        ; v171_waiting_grace_count_{lo,hi} on every re-entry, so the
        ; 10.24 s auto-arm of the RIGHT/LEFT soft-reset escape does
        ; NOT accumulate across saturation retries — the counter
        ; can't reach threshold while we bounce through `bra
        ; reconnect_wait_loop` on each failed emit.  button_scan_
        ; debounce still samples RIGHT/LEFT every iteration, but the
        ; escape-gate check reacts only once the grace counter arms,
        ; which in a tight saturation-retry cycle never happens.
        ;
        ; In practice saturation windows are bounded by
        ; ir_rc5_decode's ISR block (~7-10 ms) + MAIN's response-burst
        ; processing (<= a few ms), so 1-3 retry iterations typically
        ; clear it.  Persistent saturation would indicate a wedged
        ; downstream; safety nets in that case are the 480 ms
        ; full_sync_burst step-5 fallback (fires once CONTROL reaches
        ; post_connect_init) and — as a last resort — a power cycle.
        call    standby_wake_broadcast, 0x0                 ; dest: 0x000c98
        bnc     reconnect_wait_loop__wake_frame_queued
        bra     reconnect_wait_loop                         ; retry whole reconnect cycle
reconnect_wait_loop__wake_frame_queued:
        movlw   0x61
        movwf   idle_timeout_lo_b0, BANKED                     ; 0x9D
        movlw   0xEA
        movwf   idle_timeout_hi_b0, BANKED                     ; 0x9E
        clrf    full_sync_lo_b0, BANKED                        ; 0x9F
        clrf    full_sync_hi_b0, BANKED                        ; 0xA0
        bcf     control_flags_acc, RECONNECT_WAIT_DONE, A       ; bit 5
        movlw   0x01
        movwf   (Common_RAM + 50), A                        ; 0x032
        bra     post_connect_init                                   ; dest: 0x0011d8

input_menu_max_state_to_w:
        movlw   0x05
        movlb   0x01
        btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        movlw   0x06
        movlb   0x00
        return  0x0

volume_screen__draw_current_menu_title:                                               ; address: 0x0012d0

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movff   0x0bf, tx_data_staging_b0_phys                    ; reg2: 0x027
        movlw   HIGH(menu_title_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_title_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        call    lcd_write_16char_rom_entry, 0x0                           ; dest: 0x000940

standby_display:                                                  ; address: 0x0012e8

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0x87
        call    lcd_command, 0x0                           ; dest: 0x000066
        btfsc   control_flags_acc, 0x5, A                   ; reg: 0x01f
        goto    volume_screen__write_mute_label                                   ; dest: 0x001354
        movlw   0x60
        cpfslt  volume_cache_b0, B                                     ; reg: 0x0b9
        goto    volume_screen__render_zero_or_positive_volume                                   ; dest: 0x001310
        movlw   0x2d
        call    lcd_char_write, 0x0                           ; dest: 0x0000ec
        movf    volume_cache_b0, W, B                                  ; reg: 0x0b9
        sublw   0x60
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        goto    volume_screen__write_volume_db_suffix                                   ; dest: 0x00132e

volume_screen__render_zero_or_positive_volume:                                                  ; address: 0x001310

        movlw   0x60
        cpfseq  volume_cache_b0, B                                     ; reg: 0x0b9
        goto    volume_screen__write_plus_volume                                   ; dest: 0x001322
        movlw   0x60
        subwf   volume_cache_b0, W, B                                  ; reg: 0x0b9
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        goto    volume_screen__write_volume_db_suffix                                   ; dest: 0x00132e

volume_screen__write_plus_volume:                                                  ; address: 0x001322

        movlw   0x2b
        call    lcd_char_write, 0x0                           ; dest: 0x0000ec
        movlw   0x60
        subwf   volume_cache_b0, W, B                                  ; reg: 0x0b9
        movwf   tx_data_staging_acc, A                        ; reg: 0x027

volume_screen__write_volume_db_suffix:                                                  ; address: 0x00132e

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movf    tx_data_staging_acc, W, A                     ; reg: 0x027
        call    delay_short_loop, 0x0                           ; dest: 0x000078
        movlw   0x2e
        call    lcd_char_write, 0x0                           ; dest: 0x0000ec
        movlw   0x30
        call    lcd_char_write, 0x0                           ; dest: 0x0000ec
        movlw   HIGH(lcd_str_db_suffix)                          ; shifted via label
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   LOW(lcd_str_db_suffix)                           ; shifted via label
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        call    lcd_string_write_rom, 0x0                           ; dest: 0x0000dc
        goto    volume_screen__draw_input_row_and_status_cell                                   ; dest: 0x001360

volume_screen__write_mute_label:                                                  ; address: 0x001354

        movlw   HIGH(lcd_str_mute)                          ; shifted via label
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   LOW(lcd_str_mute)                           ; shifted via label
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        call    lcd_string_write_rom, 0x0                           ; dest: 0x0000dc

volume_screen__draw_input_row_and_status_cell:                                                  ; address: 0x001360

        movff   input_select_cache_b0_phys, rx_parsed_data_b0_phys
        call    map_cmd06_input_select_to_menu_index, 0x0
        movff   0x0b7, tx_data_staging_b0_phys                    ; reg2: 0x027
        movlw   HIGH(menu_input_auto_detect_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_input_auto_detect_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc0
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    lcd_write_16char_rom_entry, 0x0                           ; dest: 0x000940

        ; ---------------------------------------------------------------
        ; V1.72 inline (V1.61b + V1.63b): preset A/B / DSP-fault indicator
        ; ---------------------------------------------------------------
        ; Before the per-frame display_loop_iteration call, write one
        ; character at row 0, column 15 of the LCD:
        ;   DSP_FAULT_BIT set  → '!'   (V1.63b fault indicator)
        ;   DSP_FAULT_BIT clear, PRESET_BIT set   → 'B'
        ;   DSP_FAULT_BIT clear, PRESET_BIT clear → 'A'
        ; The DSP fault takes precedence over the preset letter because
        ; a fault is the operator-visible signal that requires action.
        ; 0x8F is the HD44780 DDRAM command for (row 0, col 15).
        movlw   0x80
        movwf   (Common_RAM + 1), A                    ; LCD command mode
        movlw   0x8F                                   ; row 0, col 15
        call    lcd_command, 0x0
        movlw   'A'
        btfsc   control_flags_acc, PRESET_BIT, A
        movlw   'B'
        btfsc   control_flags_acc, DSP_FAULT_BIT, A        ; V1.63b: fault overrides
        movlw   '!'
        call    lcd_char_write, 0x0

        call    display_loop_iteration, 0x0                           ; dest: 0x000cb2
        ; LEFT/RIGHT are menu-navigation keys owned by the top dispatcher.
        ; Return before processing page-local controls so the previous page
        ; cannot keep writing LCD after a requested menu transition.
        movlb   0x00
        btfsc   button_event_latch_b0, 0x5, B
        return  0x0
        btfsc   button_event_latch_b0, 0x4, B
        return  0x0
        rrcf    button_event_latch_b0, W, B                                  ; reg: 0x09a
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    volume_screen__check_volume_down                                   ; dest: 0x001398
        movlw   0x72
        cpfslt  volume_cache_b0, B                                     ; reg: 0x0b9
        goto    volume_screen__send_volume_after_up                                   ; dest: 0x001392
        incf    volume_cache_b0, F, B                                  ; reg: 0x0b9

volume_screen__send_volume_after_up:                                                  ; address: 0x001392

        call    v173_volume_clear_mute_notify, 0x0    ; BUG-1: explicit B0/03/03 on mute->unmute
        call    volume_frame_send, 0x0                           ; dest: 0x000c40

volume_screen__check_volume_down:                                                  ; address: 0x001398

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   button_event_latch_b0, 0x2, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    volume_screen__check_mute_toggle                                   ; dest: 0x0013b4
        movf    volume_cache_b0, F, B                                  ; reg: 0x0b9
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    volume_screen__send_volume_after_down                                   ; dest: 0x0013ae
        decf    volume_cache_b0, F, B                                  ; reg: 0x0b9

volume_screen__send_volume_after_down:                                                  ; address: 0x0013ae

        call    v173_volume_clear_mute_notify, 0x0    ; BUG-1: explicit B0/03/03 on mute->unmute
        call    volume_frame_send, 0x0                           ; dest: 0x000c40

volume_screen__check_mute_toggle:                                                  ; address: 0x0013b4

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   button_event_latch_b0, 0x3, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    volume_screen__loop_or_return                                   ; dest: 0x0013ce
        btg     control_flags_acc, 0x5, A                   ; reg: 0x01f
        movlw   0x2f
        movwf   mute_blink_counter_lo_b0, B                                     ; reg: 0x0b4
        movlw   0x75
        movwf   mute_blink_counter_hi_b0, B                                     ; reg: 0x0b5
        call    mute_frame_send, 0x0                           ; dest: 0x000c7c

volume_screen__loop_or_return:                                                  ; address: 0x0013ce

        bcf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   button_event_latch_b0, 0x5, B                                ; reg: 0x09a
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   button_event_latch_b0, 0x4, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        movlw   0x01
        btfsc   control_flags_acc, 0x1, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     standby_display                                   ; dest: 0x0012e8
        return  0x0
menu_setup_bl_timeout_entry:                                                  ; address: 0x0013ee  (tblptr anchor)
        dcfsnz  (Common_RAM + 66), W, A                     ; reg: 0x042
        subfwb  (Common_RAM + 32), W, A                     ; reg: 0x020
        negf    0x69, B                                     ; reg: 0x069
        movwf   0x65, B                                     ; reg: 0x065
        btg     0x75, 0x2, A                                ; reg: 0xf75
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020

setup_screen:                                               ; address: 0x0013fe

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        ; Setup title renderer is shared by legacy state 3 and split
        ; state 4.  The title table still has Setup at index 2; without
        ; this remap, the state value can read past the title table and
        ; render raw code bytes on row 0.
        movlw   0x02                                      ; legacy Setup table index
        movwf   tx_data_staging_acc, A                        ; reg: 0x027
        movlw   HIGH(menu_title_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_title_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        call    lcd_write_16char_rom_entry, 0x0                           ; dest: 0x000940
        movff   0x0ba, tx_data_staging_b0_phys                    ; reg2: 0x027
        movlw   HIGH(menu_setup_bl_timeout_entry)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_setup_bl_timeout_entry)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movff   0x0ba, 0x0a5
        movlb   0x00
        clrf    menu_option_max_index_b0, B                                     ; reg: 0x0a4
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc0
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    lcd_write_16char_rom_entry, 0x0                           ; dest: 0x000940
        call    display_loop_iteration, 0x0                           ; dest: 0x000cb2
        ; LEFT/RIGHT belong to the top menu dispatcher.  Do not redraw Setup
        ; or enter its editor after a menu-transition key has been latched.
        movlb   0x00
        btfsc   button_event_latch_b0, 0x5, B
        return  0x0
        btfsc   button_event_latch_b0, 0x4, B
        return  0x0
        btfss   control_flags_acc, 0x3, A                   ; reg: 0x01f
        goto    setup_screen__check_select_for_bl_timeout                                   ; dest: 0x001442
        bcf     control_flags_acc, 0x3, A                   ; reg: 0x01f

setup_screen__check_select_for_bl_timeout:                                                  ; address: 0x001442

        movlb   0x00
        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   button_event_latch_b0, 0x3, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    setup_screen__loop_or_return                                   ; dest: 0x001452
        call    main_event_loop, 0x0                           ; dest: 0x00150e

setup_screen__loop_or_return:                                                  ; address: 0x001452

        movlw   0x01
        btfsc   control_flags_acc, 0x1, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   button_event_latch_b0, 0x3, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   button_event_latch_b0, 0x5, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   button_event_latch_b0, 0x4, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     setup_screen                                ; dest: 0x0013fe
        return  0x0

backlight_timeout_load_threshold:                                               ; address: 0x001478

        decfsz  backlight_timeout_selection_b0, W, B                                  ; reg: 0x0eb
        goto    backlight_timeout_load_threshold__check_selection_2                                   ; dest: 0x001490
        clrf    backlight_timeout_threshold_hi_b0, B                                     ; reg: 0x0ef
        movlw   0x08
        movwf   backlight_timeout_threshold_mid_hi_b0, B                                     ; reg: 0x0ee
        movlw   0x91
        movwf   backlight_timeout_threshold_mid_lo_b0, B                                     ; reg: 0x0ed
        movlw   0x3a
        movwf   backlight_timeout_threshold_lo_b0, B                                     ; reg: 0x0ec
        goto    backlight_timeout_load_threshold__return                                   ; dest: 0x0014cc

backlight_timeout_load_threshold__check_selection_2:                                                  ; address: 0x001490

        movlw   0x02
        cpfseq  backlight_timeout_selection_b0, B                                     ; reg: 0x0eb
        goto    backlight_timeout_load_threshold__check_selection_3                                   ; dest: 0x0014aa
        clrf    backlight_timeout_threshold_hi_b0, B                                     ; reg: 0x0ef
        movlw   0x22
        movwf   backlight_timeout_threshold_mid_hi_b0, B                                     ; reg: 0x0ee
        movlw   0x44
        movwf   backlight_timeout_threshold_mid_lo_b0, B                                     ; reg: 0x0ed
        movlw   0xeb
        movwf   backlight_timeout_threshold_lo_b0, B                                     ; reg: 0x0ec
        goto    backlight_timeout_load_threshold__return                                   ; dest: 0x0014cc

backlight_timeout_load_threshold__check_selection_3:                                                  ; address: 0x0014aa

        movlw   0x03
        cpfseq  backlight_timeout_selection_b0, B                                     ; reg: 0x0eb
        goto    backlight_timeout_load_threshold__clear_disabled                                   ; dest: 0x0014c4
        clrf    backlight_timeout_threshold_hi_b0, B                                     ; reg: 0x0ef
        movlw   0x55
        movwf   backlight_timeout_threshold_mid_hi_b0, B                                     ; reg: 0x0ee
        movlw   0xac
        movwf   backlight_timeout_threshold_mid_lo_b0, B                                     ; reg: 0x0ed
        movlw   0x44
        movwf   backlight_timeout_threshold_lo_b0, B                                     ; reg: 0x0ec
        goto    backlight_timeout_load_threshold__return                                   ; dest: 0x0014cc

backlight_timeout_load_threshold__clear_disabled:                                                  ; address: 0x0014c4

        clrf    backlight_timeout_threshold_hi_b0, B                                     ; reg: 0x0ef
        clrf    backlight_timeout_threshold_mid_hi_b0, B                                     ; reg: 0x0ee
        clrf    backlight_timeout_threshold_mid_lo_b0, B                                     ; reg: 0x0ed
        clrf    backlight_timeout_threshold_lo_b0, B                                     ; reg: 0x0ec

backlight_timeout_load_threshold__return:                                                  ; address: 0x0014cc

        return  0x0
menu_bl_timeout_options_table:
        tstfsz  (Common_RAM + 79), A                        ; reg: 0x04f
        addwfc  0x66, W, A                                  ; reg: 0xf66
        movwf   (Common_RAM + 40), A                        ; reg: 0x028
        addwfc  0x6f, W, A                                  ; reg: 0xf6f
        setf    stock_074_b0, B                                     ; reg: 0x074
        cpfsgt  stock_06D_b0, B                                     ; reg: 0x06d
        btg     stock_06F_b0, 0x2, B                                ; reg: 0x06f
        incf    stock_074_b0, W, B                                  ; reg: 0x074
        rrcf    (Common_RAM + 51), W, A                     ; reg: 0x033
        btg     (Common_RAM + 32), 0x1, B                   ; reg: 0x020
        cpfseq  stock_065_b0, B                                     ; reg: 0x065
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 50), W, A                     ; reg: 0x032
        setf    stock_06D_b0, B                                     ; reg: 0x06d
        addwfc  0x6e, W, A                                  ; reg: 0xf6e
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 53), W, A                     ; reg: 0x035
        setf    stock_06D_b0, B                                     ; reg: 0x06d
        addwfc  0x6e, W, A                                  ; reg: 0xf6e
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020


; ===========================================================================
; main_event_loop @ 0x00150E — main_event_loop  (V1.6b address)
; ---------------------------------------------------------------------------
; The CONTROL panel's top-level event loop. Runs forever after boot setup
; (app_cold_init__zero_saved_settings_d3_block) completes. Per-iteration:
;   1. Stage 0x0BA value into 0x027 (tx_data_staging) — staged for later
;      send if menu state changed.
;   2. Enable RBIE (button port-change interrupt).
;   3. Call button_scan_debounce (button_scan_debounce) and rx_parser_entry
;      (rx_parser_entry) to absorb input/output edges.
;   4. Decrement idle_timeout_counter (0x09D:0x09E init 0xEA61).
;      When zero → trigger transition to standby_display (standby_display).
;   5. Decrement full_sync_counter (0x09F:0x0A0 init 0x4E20).
;      When zero → call full_sync_burst (full_sync_burst — BUG C7).
;   6. Check handshake sentinels (0x0B8/0x0B9/0x0A7/0x0A1) — if any has
;      changed from 0x80 to a real value, the corresponding cached value
;      gets reflected back to MAIN through standby_wake_broadcast/035.
; The loop blocks for the full_sync_counter and idle_timeout overflows;
; user input is handled through the RBIF interrupt and processed by
; lazy debounce on the next iteration.
; ===========================================================================
; main_event_loop:
;@routine main_event_loop entry_bsr=0 exit_bsr=0
main_event_loop:                                               ; address: 0x00150e

        movff   0x0ba, tx_data_staging_b0_phys                    ; reg2: 0x027
        movlw   HIGH(menu_setup_bl_timeout_entry)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_setup_bl_timeout_entry)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    lcd_write_16char_rom_entry, 0x0                           ; dest: 0x000940
        movlb   0x00
        movlw   0x03
        movwf   menu_option_max_index_b0, B                                     ; reg: 0x0a4
        movlw   HIGH(menu_bl_timeout_options_table)
        movwf   stock_0A3_b0, B                                     ; reg: 0x0a3
        movlw   LOW(menu_bl_timeout_options_table)
        movwf   stock_0A2_b0, B                                     ; reg: 0x0a2

bl_timeout_editor__loop:                                                  ; address: 0x001532

        movff   0x0eb, 0x0a5
        call    menu_option_editor_wait_and_update, 0x0                           ; dest: 0x000fa0
        bcf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   button_event_latch_b0, 0x1, B                                ; reg: 0x09a
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   button_event_latch_b0, 0x2, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    bl_timeout_editor__check_select_exit                                   ; dest: 0x001558
        movff   0x0a5, 0x0eb
        rcall   backlight_timeout_load_threshold                                ; dest: 0x001478

bl_timeout_editor__check_select_exit:                                                  ; address: 0x001558

        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   button_event_latch_b0, 0x3, B                                ; reg: 0x09a
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        movlw   0x01
        btfsc   control_flags_acc, 0x1, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     bl_timeout_editor__loop                                   ; dest: 0x001532
        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        return  0x0
menu_source_channel_table:                                                  ; address: 0x001572  (tblptr anchor)
        movwf   (Common_RAM + 83), B                        ; reg: 0x053
        btg     0x75, 0x1, A                                ; reg: 0xf75
        cpfsgt  0x63, B                                     ; reg: 0x063
        rrncf   (Common_RAM + 32), F, B                     ; reg: 0x020
        rrcf    (Common_RAM + 72), W, B                     ; reg: 0x048
        addwfc  (Common_RAM + 58), W, A                     ; reg: 0x03a
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movwf   (Common_RAM + 83), B                        ; reg: 0x053
        btg     0x75, 0x1, A                                ; reg: 0xf75
        cpfsgt  0x63, B                                     ; reg: 0x063
        rrncf   (Common_RAM + 32), F, B                     ; reg: 0x020
        rrcf    (Common_RAM + 72), F, A                     ; reg: 0x048
        addwfc  (Common_RAM + 58), W, A                     ; reg: 0x03a
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movwf   (Common_RAM + 83), B                        ; reg: 0x053
        btg     0x75, 0x1, A                                ; reg: 0xf75
        cpfsgt  0x63, B                                     ; reg: 0x063
        rrncf   (Common_RAM + 32), F, B                     ; reg: 0x020
        rrcf    (Common_RAM + 72), F, B                     ; reg: 0x048
        addwfc  (Common_RAM + 58), W, A                     ; reg: 0x03a
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movwf   (Common_RAM + 83), B                        ; reg: 0x053
        btg     0x75, 0x1, A                                ; reg: 0xf75
        cpfsgt  0x63, B                                     ; reg: 0x063
        rrncf   (Common_RAM + 32), F, B                     ; reg: 0x020
        rlcf    (Common_RAM + 72), W, A                     ; reg: 0x048
        addwfc  (Common_RAM + 58), W, A                     ; reg: 0x03a
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movwf   (Common_RAM + 83), B                        ; reg: 0x053
        btg     0x75, 0x1, A                                ; reg: 0xf75
        cpfsgt  0x63, B                                     ; reg: 0x063
        rrncf   (Common_RAM + 32), F, B                     ; reg: 0x020
        rlcf    (Common_RAM + 72), W, B                     ; reg: 0x048
        addwfc  (Common_RAM + 58), W, A                     ; reg: 0x03a
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movwf   (Common_RAM + 83), B                        ; reg: 0x053
        btg     0x75, 0x1, A                                ; reg: 0xf75
        cpfsgt  0x63, B                                     ; reg: 0x063
        rrncf   (Common_RAM + 32), F, B                     ; reg: 0x020
        rlcf    (Common_RAM + 72), F, A                     ; reg: 0x048
        addwfc  (Common_RAM + 58), W, A                     ; reg: 0x03a
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movf    (Common_RAM + 85), F, B                     ; reg: 0x055
        cpfslt  (Common_RAM + 66), B                        ; reg: 0x042
        cpfsgt  0x75, A                                     ; reg: 0xf75
        movwf   0x69, B                                     ; reg: 0x069
        addwfc  (Common_RAM + 58), W, A                     ; reg: 0x03a
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
menu_routing_table:                                                  ; address: 0x0015e2  (tblptr anchor)
        cpfsgt  (Common_RAM + 76), B                        ; reg: 0x04c
        btg     0x66, 0x2, A                                ; reg: 0xf66
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        setf    (Common_RAM + 82), B                        ; reg: 0x052
        setf    0x67, A                                     ; reg: 0xf67
        addwfc  0x74, W, A                                  ; reg: 0xf74
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        incf    (Common_RAM + 76), F, B                     ; reg: 0x04c
        addwfc  (Common_RAM + 82), W, A                     ; reg: 0x052
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        decfsz  (Common_RAM + 76), W, B                     ; reg: 0x04c
        addwfc  (Common_RAM + 82), W, A                     ; reg: 0x052
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
menu_input_cat_spdif_table:                                                  ; address: 0x001622  (tblptr anchor)
        rrncf   (Common_RAM + 67), W, B                     ; reg: 0x043
        decfsz  (Common_RAM + 84), F, B                     ; reg: 0x054
        rlncf   (Common_RAM + 65), W, B                     ; reg: 0x041
        addwfc  (Common_RAM + 83), W, A                     ; reg: 0x053
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        decfsz  (Common_RAM + 83), F, B                     ; reg: 0x053
        rlncf   (Common_RAM + 80), W, A                     ; reg: 0x050
        rlncf   (Common_RAM + 73), F, A                     ; reg: 0x049
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020

;@routine settings_bank_editor entry_bsr=0 exit_bsr=0
settings_bank_editor:                                                  ; address: 0x001642

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movff   0x0ba, tx_data_staging_b0_phys                    ; reg2: 0x027
        movlw   HIGH(menu_setup_bl_timeout_entry)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_setup_bl_timeout_entry)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        call    lcd_write_16char_rom_entry, 0x0                           ; dest: 0x000940

settings_bank_editor__render_source_channel_row_and_load_value:                                                  ; address: 0x00165a

        movff   0x0c0, tx_data_staging_b0_phys                    ; reg2: 0x027
        movlw   HIGH(menu_source_channel_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_source_channel_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc0
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    lcd_write_16char_rom_entry, 0x0                           ; dest: 0x000940
        movlw   0x06
        cpfslt  source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_editor__render_input_cat_spdif_value_row                                   ; dest: 0x001718
        movf    source_channel_menu_index_b0, F, B                                  ; reg: 0x0c0
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    settings_bank_editor__load_bank1_value                                   ; dest: 0x001692
        lfsr    0x0, saved_settings_base_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   menu_option_selected_index_b0, B                                     ; reg: 0x0a5
        goto    settings_bank_editor__render_routing_value_row                                   ; dest: 0x0016fa

settings_bank_editor__load_bank1_value:                                                  ; address: 0x001692

        decfsz  source_channel_menu_index_b0, W, B                                  ; reg: 0x0c0
        goto    settings_bank_editor__load_bank2_value                                   ; dest: 0x0016a6
        lfsr    0x0, stock_0C7_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   menu_option_selected_index_b0, B                                     ; reg: 0x0a5
        goto    settings_bank_editor__render_routing_value_row                                   ; dest: 0x0016fa

settings_bank_editor__load_bank2_value:                                                  ; address: 0x0016a6

        movlw   0x02
        cpfseq  source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_editor__load_bank3_value                                   ; dest: 0x0016bc
        lfsr    0x0, stock_0CD_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   menu_option_selected_index_b0, B                                     ; reg: 0x0a5
        goto    settings_bank_editor__render_routing_value_row                                   ; dest: 0x0016fa

settings_bank_editor__load_bank3_value:                                                  ; address: 0x0016bc

        movlw   0x03
        cpfseq  source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_editor__load_bank4_value                                   ; dest: 0x0016d2
        lfsr    0x0, stock_0D3_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   menu_option_selected_index_b0, B                                     ; reg: 0x0a5
        goto    settings_bank_editor__render_routing_value_row                                   ; dest: 0x0016fa

settings_bank_editor__load_bank4_value:                                                  ; address: 0x0016d2

        movlw   0x04
        cpfseq  source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_editor__load_bank5_value                                   ; dest: 0x0016e8
        lfsr    0x0, stock_0D9_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   menu_option_selected_index_b0, B                                     ; reg: 0x0a5
        goto    settings_bank_editor__render_routing_value_row                                   ; dest: 0x0016fa

settings_bank_editor__load_bank5_value:                                                  ; address: 0x0016e8

        movlw   0x05
        cpfseq  source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_editor__render_routing_value_row                                   ; dest: 0x0016fa
        lfsr    0x0, stock_0DF_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   menu_option_selected_index_b0, B                                     ; reg: 0x0a5

settings_bank_editor__render_routing_value_row:                                                  ; address: 0x0016fa

        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        movwf   menu_option_max_index_b0, B                                     ; reg: 0x0a4
        movff   0x0a5, tx_data_staging_b0_phys                    ; reg2: 0x027
        movlw   HIGH(menu_routing_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_routing_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xcb
        call    lcd_command, 0x0                           ; dest: 0x000066
        goto    settings_bank_editor__draw_value_and_poll                                   ; dest: 0x00173c

settings_bank_editor__render_input_cat_spdif_value_row:                                                  ; address: 0x001718

        lfsr    0x0, stock_0E5_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   menu_option_selected_index_b0, B                                     ; reg: 0x0a5
        movlw   0x01
        movwf   menu_option_max_index_b0, B                                     ; reg: 0x0a4
        movff   0x0a5, tx_data_staging_b0_phys                    ; reg2: 0x027
        movlw   HIGH(menu_input_cat_spdif_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_input_cat_spdif_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc9
        call    lcd_command, 0x0                           ; dest: 0x000066

settings_bank_editor__draw_value_and_poll:                                                  ; address: 0x00173c

        call    lcd_write_16char_rom_entry, 0x0                           ; dest: 0x000940
        call    display_loop_iteration, 0x0                           ; dest: 0x000cb2
        btfss   control_flags_acc, 0x3, A                   ; reg: 0x01f
        goto    settings_bank_editor__handle_value_increment                                   ; dest: 0x001754
        bcf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        btfss   control_flags_acc, 0x1, A                   ; reg: 0x01f
        goto    settings_bank_editor__handle_value_increment                                   ; dest: 0x001754
        bra     settings_bank_editor                                   ; dest: 0x001642

settings_bank_editor__handle_value_increment:                                                  ; address: 0x001754

        rrcf    button_event_latch_b0, W, B                                  ; reg: 0x09a
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    settings_bank_editor__handle_value_decrement                                   ; dest: 0x001772
        movf    menu_option_selected_index_b0, W, B                                  ; reg: 0x0a5
        cpfseq  menu_option_max_index_b0, B                                     ; reg: 0x0a4
        goto    settings_bank_editor__increment_value                                   ; dest: 0x00176c
        clrf    menu_option_selected_index_b0, B                                     ; reg: 0x0a5
        goto    settings_bank_editor__store_value_after_increment                                   ; dest: 0x00176e

settings_bank_editor__increment_value:                                                  ; address: 0x00176c

        incf    menu_option_selected_index_b0, F, B                                  ; reg: 0x0a5

settings_bank_editor__store_value_after_increment:                                                  ; address: 0x00176e

        call    settings_bank_store_selected_value, 0x0                           ; dest: 0x0017e8

settings_bank_editor__handle_value_decrement:                                                  ; address: 0x001772

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   button_event_latch_b0, 0x2, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    settings_bank_editor__handle_source_channel_next                                   ; dest: 0x001794
        movf    menu_option_selected_index_b0, F, B                                  ; reg: 0x0a5
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    settings_bank_editor__decrement_value                                   ; dest: 0x00178e
        movff   0x0a4, 0x0a5
        goto    settings_bank_editor__store_value_after_decrement                                   ; dest: 0x001790

settings_bank_editor__decrement_value:                                                  ; address: 0x00178e

        decf    menu_option_selected_index_b0, F, B                                  ; reg: 0x0a5

settings_bank_editor__store_value_after_decrement:                                                  ; address: 0x001790

        call    settings_bank_store_selected_value, 0x0                           ; dest: 0x0017e8

settings_bank_editor__handle_source_channel_next:                                                  ; address: 0x001794

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   button_event_latch_b0, 0x5, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    settings_bank_editor__handle_source_channel_previous                                   ; dest: 0x0017b0
        movlw   0x06
        cpfseq  source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_editor__increment_source_channel                                   ; dest: 0x0017ae
        clrf    source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_editor__handle_source_channel_previous                                   ; dest: 0x0017b0

settings_bank_editor__increment_source_channel:                                                  ; address: 0x0017ae

        incf    source_channel_menu_index_b0, F, B                                  ; reg: 0x0c0

settings_bank_editor__handle_source_channel_previous:                                                  ; address: 0x0017b0

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   button_event_latch_b0, 0x4, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    settings_bank_editor__loop_or_return                                   ; dest: 0x0017ce
        movf    source_channel_menu_index_b0, F, B                                  ; reg: 0x0c0
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    settings_bank_editor__decrement_source_channel                                   ; dest: 0x0017cc
        movlw   0x06
        movwf   source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_editor__loop_or_return                                   ; dest: 0x0017ce

settings_bank_editor__decrement_source_channel:                                                  ; address: 0x0017cc

        decf    source_channel_menu_index_b0, F, B                                  ; reg: 0x0c0

settings_bank_editor__loop_or_return:                                                  ; address: 0x0017ce

        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   button_event_latch_b0, 0x3, B                                ; reg: 0x09a
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        movlw   0x01
        btfsc   control_flags_acc, 0x1, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     settings_bank_editor__render_source_channel_row_and_load_value                                   ; dest: 0x00165a
        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        return  0x0

;@routine settings_bank_store_selected_value entry_bsr=0 exit_bsr=0
settings_bank_store_selected_value:                                               ; address: 0x0017e8

        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        movlw   0x06
        cpfslt  source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_store_selected_value__bank6                                   ; dest: 0x001876
        movf    source_channel_menu_index_b0, F, B                                  ; reg: 0x0c0
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    settings_bank_store_selected_value__bank1                                   ; dest: 0x00180a
        lfsr    0x0, saved_settings_base_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb
        goto    settings_bank_store_selected_value__known_bank_done                                   ; dest: 0x001872

settings_bank_store_selected_value__bank1:                                                  ; address: 0x00180a

        decfsz  source_channel_menu_index_b0, W, B                                  ; reg: 0x0c0
        goto    settings_bank_store_selected_value__bank2                                   ; dest: 0x00181e
        lfsr    0x0, stock_0C7_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb
        goto    settings_bank_store_selected_value__known_bank_done                                   ; dest: 0x001872

settings_bank_store_selected_value__bank2:                                                  ; address: 0x00181e

        movlw   0x02
        cpfseq  source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_store_selected_value__bank3                                   ; dest: 0x001834
        lfsr    0x0, stock_0CD_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb
        goto    settings_bank_store_selected_value__known_bank_done                                   ; dest: 0x001872

settings_bank_store_selected_value__bank3:                                                  ; address: 0x001834

        movlw   0x03
        cpfseq  source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_store_selected_value__bank4                                   ; dest: 0x00184a
        lfsr    0x0, stock_0D3_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb
        goto    settings_bank_store_selected_value__known_bank_done                                   ; dest: 0x001872

settings_bank_store_selected_value__bank4:                                                  ; address: 0x00184a

        movlw   0x04
        cpfseq  source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_store_selected_value__bank5                                   ; dest: 0x001860
        lfsr    0x0, stock_0D9_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb
        goto    settings_bank_store_selected_value__known_bank_done                                   ; dest: 0x001872

settings_bank_store_selected_value__bank5:                                                  ; address: 0x001860

        movlw   0x05
        cpfseq  source_channel_menu_index_b0, B                                     ; reg: 0x0c0
        goto    settings_bank_store_selected_value__known_bank_done                                   ; dest: 0x001872
        lfsr    0x0, stock_0DF_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb

settings_bank_store_selected_value__known_bank_done:                                                  ; address: 0x001872

        goto    settings_bank_store_selected_value__return                                   ; dest: 0x001880

settings_bank_store_selected_value__bank6:                                                  ; address: 0x001876

        lfsr    0x0, stock_0E5_b0_phys
        movf    setup_submenu_index_b0, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb

settings_bank_store_selected_value__return:                                                  ; address: 0x001880

        return  0x0
menu_input_auto_detect_table:                                                  ; address: 0x001882  (tblptr anchor)
        btg     (Common_RAM + 65), 0x2, B                   ; reg: 0x041
        movwf   0x74, B                                     ; reg: 0x074
        rlncf   (Common_RAM + 32), W, A                     ; reg: 0x020
        btg     0x65, 0x2, A                                ; reg: 0xf65
        cpfseq  0x65, B                                     ; reg: 0x065
        addwfc  0x74, W, A                                  ; reg: 0xf74
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        decfsz  (Common_RAM + 83), F, B                     ; reg: 0x053
        rlncf   (Common_RAM + 80), W, A                     ; reg: 0x050
        rlncf   (Common_RAM + 73), F, A                     ; reg: 0x049
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movf    (Common_RAM + 85), F, B                     ; reg: 0x055
        addwfc  (Common_RAM + 66), W, A                     ; reg: 0x042
        btg     (Common_RAM + 65), 0x2, B                   ; reg: 0x041
        setf    0x64, B                                     ; reg: 0x064
        addwfc  0x6f, W, A                                  ; reg: 0xf6f
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        rlncf   (Common_RAM + 65), W, B                     ; reg: 0x041
        addwfc  (Common_RAM + 83), W, A                     ; reg: 0x053
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        btg     (Common_RAM + 79), 0x0, A                   ; reg: 0x04f
        setf    0x74, B                                     ; reg: 0x074
        cpfslt  0x63, B                                     ; reg: 0x063
        addwfc  0x6c, W, A                                  ; reg: 0xf6c
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movwf   (Common_RAM + 65), A                        ; reg: 0x041
        negf    0x61, A                                     ; reg: 0xf61
        tstfsz  0x6f, B                                     ; reg: 0x06f
        cpfsgt  0x75, B                                     ; reg: 0x075
        rrcf    (Common_RAM + 32), W, B                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movwf   (Common_RAM + 65), A                        ; reg: 0x041
        negf    0x61, A                                     ; reg: 0xf61
        tstfsz  0x6f, B                                     ; reg: 0x06f
        cpfsgt  0x75, B                                     ; reg: 0x075
        rrcf    (Common_RAM + 32), F, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movwf   (Common_RAM + 65), A                        ; reg: 0x041
        negf    0x61, A                                     ; reg: 0xf61
        tstfsz  0x6f, B                                     ; reg: 0x06f
        cpfsgt  0x75, B                                     ; reg: 0x075
        rrcf    (Common_RAM + 32), F, B                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        movwf   (Common_RAM + 65), A                        ; reg: 0x041
        negf    0x61, A                                     ; reg: 0xf61
        tstfsz  0x6f, B                                     ; reg: 0x06f
        cpfsgt  0x75, B                                     ; reg: 0x075
        rlcf    (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020

input_screen_stage_selected_index:
        movlb   0x00
        movlw   0x03
        cpfseq  display_state_index_b0, BANKED
        bra     input_screen_stage_pb1_index
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_screen_stage_pb1_index_b0
        btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        bra     input_screen_stage_pb2_linked_index
        movff   input_intent_pb2_b1_phys, rx_parsed_data_b0_phys
        movlb   0x00
        call    map_cmd06_input_select_to_menu_index, 0x0
        incf    rx_ring_staging_b0, F, BANKED                  ; PB2 row 0 is Same as PB1
        return  0x0
input_screen_stage_pb2_linked_index:
        movlb   0x00
        clrf    rx_ring_staging_b0, BANKED
        return  0x0
input_screen_stage_pb1_index_b0:
        movlb   0x00
        bra     input_screen_stage_pb1_index
input_screen_stage_pb1_index:
        movlb   0x00
        movff   input_select_cache_b0_phys, rx_parsed_data_b0_phys
input_screen_stage_map_done:
        call    map_cmd06_input_select_to_menu_index, 0x0
        movlb   0x00
        return  0x0

input_screen_write_title:
        movlb   0x00
        movlw   0x03
        cpfseq  display_state_index_b0, BANKED
        bra     input_screen_title_state_2
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_screen_title_legacy
        bsf     v171_diag_render_pb_index_b1, 0, BANKED
        call    v171_health_diag_check_stale, 0x0
        movf    (Common_RAM + 4), F, A
        bz      input_screen_title_pb2_normal
        movlw   0x01
        cpfseq  (Common_RAM + 4), A
        bra     input_screen_title_pb2_lost
        movlw   0x02                                      ; Input PB2 old
        bra     input_screen_title_pb2_stage
input_screen_title_pb2_lost:
        movlw   0x03                                      ; Input PB2 lost
        bra     input_screen_title_pb2_stage
input_screen_title_pb2_normal:
        movlw   0x01                                      ; Input PB2
input_screen_title_pb2_stage:
        movlb   0x01
        bcf     v171_health_flags_b1, V171_HEALTH_FLAG_DISPLAY_DIRTY, BANKED
        movlb   0x00
        movwf   tx_data_staging_acc, A
        bra     input_screen_title_pb_table
input_screen_title_state_2:
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_screen_title_legacy
        movlb   0x00
        clrf    tx_data_staging_acc, A                    ; Input PB1
input_screen_title_pb_table:
        movlw   HIGH(input_pb_title_table)
        movwf   (Common_RAM + 42), A
        movlw   LOW(input_pb_title_table)
        movwf   (Common_RAM + 41), A
        call    lcd_write_16char_rom_entry, 0x0
        return  0x0
input_screen_title_legacy:
        movlb   0x00
        movlw   0x01                                      ; legacy Input table index
        movwf   tx_data_staging_acc, A
        movlw   HIGH(menu_title_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_title_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        call    lcd_write_16char_rom_entry, 0x0
        return  0x0

input_commit_selected_input_intent:
        movlb   0x00
        movlw   0x03
        cpfseq  display_state_index_b0, BANKED
        bra     input_commit_selected_pb1
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_commit_selected_pb1_b0
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        movff   tx_data_staging_b0_phys, input_intent_pb2_b1_phys
        movlb   0x00
        return  0x0
input_commit_selected_pb1_b0:
        movlb   0x00
        bra     input_commit_selected_pb1
input_commit_selected_pb1:
        movff   tx_data_staging_b0_phys, input_select_cache_b0_phys
        movlb   0x00
        return  0x0

input_screen_compute_menu_max:
        movlb   0x00
        movlw   0x03
        cpfsgt  raw_status_cache_b0, BANKED
        bra     input_screen_compute_menu_max_known
        movlw   0x08
        bra     input_screen_compute_menu_max_store
input_screen_compute_menu_max_known:
        movf    raw_status_cache_b0, F, BANKED
        btfss   STATUS, Z, A
        bra     input_screen_compute_menu_max_status_one
        movlw   0x05
        bra     input_screen_compute_menu_max_store
input_screen_compute_menu_max_status_one:
        decfsz  raw_status_cache_b0, W, BANKED
        bra     input_screen_compute_menu_max_status_two
        movlw   0x06
        bra     input_screen_compute_menu_max_store
input_screen_compute_menu_max_status_two:
        movlw   0x02
        cpfseq  raw_status_cache_b0, BANKED
        bra     input_screen_compute_menu_max_status_three
        movlw   0x07
        bra     input_screen_compute_menu_max_store
input_screen_compute_menu_max_status_three:
        movlw   0x08
input_screen_compute_menu_max_store:
        movwf   menu_option_max_index_b0, BANKED
        call    input_screen_adjust_pb2_max_index, 0x0
        return  0x0

input_screen_clamp_staged_row:
        movlb   0x00
        movf    menu_option_max_index_b0, W, BANKED
        cpfsgt  rx_ring_staging_b0, BANKED
        return  0x0
        movff   menu_option_max_index_b0_phys, rx_ring_staging_b0_phys
        return  0x0

input_screen_prepare_selected_row:
        movlb   0x00
        movlw   0x03
        cpfseq  display_state_index_b0, BANKED
        bra     input_screen_prepare_selected_row_not_pb2
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_screen_prepare_selected_row_not_pb2_b0
        movlb   0x00
        movf    rx_ring_staging_b0, F, BANKED
        btfss   STATUS, Z, A
        bra     input_screen_prepare_selected_row_pb2_concrete
        movlb   0x01
        bsf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_PENDING_CONCRETE, BANKED
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE, BANKED
        bsf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY, BANKED
        movff   input_select_cache_b0_phys, input_intent_pb2_b1_phys
        movlb   0x00
        bsf     STATUS, C, A
        return  0x0
input_screen_prepare_selected_row_pb2_concrete:
        decf    rx_ring_staging_b0, F, BANKED
        movlb   0x01
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED
        bcf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE, BANKED
        bsf     input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY, BANKED
        movlb   0x00
        bcf     STATUS, C, A
        return  0x0
input_screen_prepare_selected_row_not_pb2_b0:
        movlb   0x00
input_screen_prepare_selected_row_not_pb2:
        bcf     STATUS, C, A
        return  0x0

input_screen_prepare_option_label:
        movlb   0x00
        movff   rx_ring_staging_b0_phys, tx_data_staging_b0_phys
        movlw   HIGH(menu_input_auto_detect_table)
        movwf   (Common_RAM + 42), A
        movlw   LOW(menu_input_auto_detect_table)
        movwf   (Common_RAM + 41), A
        movlw   0x03
        cpfseq  display_state_index_b0, BANKED
        return  0x0
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_screen_prepare_option_label_b0
        movlb   0x00
        movf    rx_ring_staging_b0, F, BANKED
        btfss   STATUS, Z, A
        bra     input_screen_prepare_option_label_pb2_concrete
        clrf    tx_data_staging_acc, A
        movlw   HIGH(input_pb2_same_as_pb1_table)
        movwf   (Common_RAM + 42), A
        movlw   LOW(input_pb2_same_as_pb1_table)
        movwf   (Common_RAM + 41), A
        return  0x0
input_screen_prepare_option_label_pb2_concrete:
        decf    tx_data_staging_acc, F, A
        return  0x0
input_screen_prepare_option_label_b0:
        movlb   0x00
        return  0x0

input_screen_adjust_pb2_max_index:
        movlb   0x00
        movlw   0x03
        cpfseq  display_state_index_b0, BANKED
        return  0x0
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_screen_adjust_pb2_max_index_b0
        movlb   0x00
        incf    menu_option_max_index_b0, F, BANKED
        return  0x0
input_screen_adjust_pb2_max_index_b0:
        movlb   0x00
        return  0x0

input_screen:                                               ; address: 0x001912

        call    input_screen_stage_selected_index, 0x0
        call    input_screen_compute_menu_max, 0x0
        call    input_screen_clamp_staged_row, 0x0
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    input_screen_write_title, 0x0

input_screen__render_option_row:                                                  ; address: 0x00192a

        call    input_screen_compute_menu_max, 0x0
        call    input_screen_clamp_staged_row, 0x0
        call    input_screen_prepare_option_label, 0x0
        movff   0x0b7, 0x0a5
        movf    raw_status_cache_b0, F, B                                  ; reg: 0x0a1
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    input_screen__status_one_sets_limit                                   ; dest: 0x00194a
        movlw   0x05
        movwf   menu_option_max_index_b0, B                                     ; reg: 0x0a4
        goto    input_screen__draw_option_and_service                                   ; dest: 0x001974

input_screen__status_one_sets_limit:                                                  ; address: 0x00194a

        decfsz  raw_status_cache_b0, W, B                                  ; reg: 0x0a1
        goto    input_screen__status_two_sets_limit                                   ; dest: 0x001958
        movlw   0x06
        movwf   menu_option_max_index_b0, B                                     ; reg: 0x0a4
        goto    input_screen__draw_option_and_service                                   ; dest: 0x001974

input_screen__status_two_sets_limit:                                                  ; address: 0x001958

        movlw   0x02
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    input_screen__status_three_sets_limit                                   ; dest: 0x001968
        movlw   0x07
        movwf   menu_option_max_index_b0, B                                     ; reg: 0x0a4
        goto    input_screen__draw_option_and_service                                   ; dest: 0x001974

input_screen__status_three_sets_limit:                                                  ; address: 0x001968

        movlw   0x03
        cpfseq  raw_status_cache_b0, B                                     ; reg: 0x0a1
        goto    input_screen__status_unknown_sets_limit
        movlw   0x08
        movwf   menu_option_max_index_b0, B                                     ; reg: 0x0a4
        goto    input_screen__draw_option_and_service

input_screen__status_unknown_sets_limit:
        movlw   0x08
        movwf   menu_option_max_index_b0, B

input_screen__draw_option_and_service:                                                  ; address: 0x001974

        call    input_screen_adjust_pb2_max_index, 0x0
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc0
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    lcd_write_16char_rom_entry, 0x0                           ; dest: 0x000940
        call    display_loop_iteration, 0x0                           ; dest: 0x000cb2
        ; LEFT/RIGHT are menu-navigation keys owned by the top dispatcher.
        ; Return before processing page-local input controls so the old page
        ; cannot redraw itself after a requested menu transition.
        movlb   0x00
        btfsc   button_event_latch_b0, 0x5, B
        return  0x0
        btfsc   button_event_latch_b0, 0x4, B
        return  0x0
        ; If an out-of-band transition has already changed state, return so
        ; the dispatcher paints the new owner before any page-local service.
        movlb   0x00
        movlw   0x02
        cpfseq  display_state_index_b0, BANKED
        bra     input_screen__check_state_3
        bra     input_screen__state_still_active
input_screen__check_state_3:
        movlw   0x03
        cpfseq  display_state_index_b0, BANKED
        return  0x0
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_screen__return_b0
        movlb   0x00
input_screen__state_still_active:
        movlb   0x00
        movf    button_event_latch_b0, F, B
        btfss   STATUS, Z, A
        bra     input_screen__check_control_redraw
        movlb   0x01
        btfss   v171_health_flags_b1, V171_HEALTH_FLAG_DISPLAY_DIRTY, BANKED
        bra     input_screen__check_control_redraw
        movlb   0x00
        movlw   0x03
        cpfseq  display_state_index_b0, BANKED
        bra     input_screen__check_control_redraw
        movlb   0x01
        btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED
        bra     input_screen__check_control_redraw_b0
        movlb   0x00
        bra     input_screen
input_screen__check_control_redraw_b0:
        movlb   0x00
        bra     input_screen__check_control_redraw
input_screen__return_b0:
        movlb   0x00
        return  0x0
input_screen__check_control_redraw:
        movlb   0x00
        btfss   control_flags_acc, 0x3, A                   ; reg: 0x01f
        goto    input_screen__handle_option_up                                   ; dest: 0x001996
        bcf     control_flags_acc, 0x3, A                   ; reg: 0x01f
        btfss   control_flags_acc, 0x1, A                   ; reg: 0x01f
        goto    input_screen__handle_option_up                                   ; dest: 0x001996
        bra     input_screen                                ; dest: 0x001912

input_screen__handle_option_up:                                                  ; address: 0x001996

        rrcf    button_event_latch_b0, W, B                                  ; reg: 0x09a
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    input_screen__handle_option_down                                   ; dest: 0x0019c0
        movf    menu_option_selected_index_b0, W, B                                  ; reg: 0x0a5
        cpfseq  menu_option_max_index_b0, B                                     ; reg: 0x0a4
        goto    input_screen__increment_option                                   ; dest: 0x0019ae
        clrf    menu_option_selected_index_b0, B                                     ; reg: 0x0a5
        goto    input_screen__commit_option_after_up                                   ; dest: 0x0019b0

input_screen__increment_option:                                                  ; address: 0x0019ae

        incf    menu_option_selected_index_b0, F, B                                  ; reg: 0x0a5

input_screen__commit_option_after_up:                                                  ; address: 0x0019b0

        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        movff   0x0a5, 0x0b7
        call    input_screen_compute_menu_max, 0x0
        call    input_screen_clamp_staged_row, 0x0
        movff   0x0b7, 0x0a5
        call    input_screen_prepare_selected_row, 0x0
        bc      input_screen__send_option_after_up
        call    map_input_menu_index_to_cmd06_input_select, 0x0                           ; dest: 0x00076a
        call    input_commit_selected_input_intent, 0x0
input_screen__send_option_after_up:
        call    input_frame_send_current_input_page, 0x0

input_screen__handle_option_down:                                                  ; address: 0x0019c0

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   button_event_latch_b0, 0x2, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    input_screen__loop_or_return                                   ; dest: 0x0019ee
        movf    menu_option_selected_index_b0, F, B                                  ; reg: 0x0a5
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    input_screen__decrement_option                                   ; dest: 0x0019dc
        movff   0x0a4, 0x0a5
        goto    input_screen__commit_option_after_down                                   ; dest: 0x0019de

input_screen__decrement_option:                                                  ; address: 0x0019dc

        decf    menu_option_selected_index_b0, F, B                                  ; reg: 0x0a5

input_screen__commit_option_after_down:                                                  ; address: 0x0019de

        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        movff   0x0a5, 0x0b7
        call    input_screen_compute_menu_max, 0x0
        call    input_screen_clamp_staged_row, 0x0
        movff   0x0b7, 0x0a5
        call    input_screen_prepare_selected_row, 0x0
        bc      input_screen__send_option_after_down
        call    map_input_menu_index_to_cmd06_input_select, 0x0                           ; dest: 0x00076a
        call    input_commit_selected_input_intent, 0x0
input_screen__send_option_after_down:
        call    input_frame_send_current_input_page, 0x0

input_screen__loop_or_return:                                                  ; address: 0x0019ee

        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   button_event_latch_b0, 0x5, B                                ; reg: 0x09a
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   button_event_latch_b0, 0x4, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        movlw   0x01
        btfsc   control_flags_acc, 0x1, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     input_screen__render_option_row                                   ; dest: 0x00192a
        return  0x0

input_pb_title_table:
        db      0x49, 0x6E, 0x70, 0x75, 0x74, 0x20, 0x50, 0x42, 0x31, 0x3A, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20 ; "Input PB1:      "
        db      0x49, 0x6E, 0x70, 0x75, 0x74, 0x20, 0x50, 0x42, 0x32, 0x3A, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20 ; "Input PB2:      "
        db      0x49, 0x6E, 0x70, 0x75, 0x74, 0x20, 0x50, 0x42, 0x32, 0x20, 0x6F, 0x6C, 0x64, 0x20, 0x20, 0x20 ; "Input PB2 old   "
        db      0x49, 0x6E, 0x70, 0x75, 0x74, 0x20, 0x50, 0x42, 0x32, 0x20, 0x6C, 0x6F, 0x73, 0x74, 0x20, 0x20 ; "Input PB2 lost  "

input_pb2_same_as_pb1_table:
        db      0x53, 0x61, 0x6D, 0x65, 0x20, 0x61, 0x73, 0x20, 0x50, 0x42, 0x31, 0x20, 0x20, 0x20, 0x20, 0x20 ; "Same as PB1     "

; --- V1.73 boot splash release strings ---
; Row 2 is rewritten by scripts/build_v173_release.py together with the
; monotonic release revision and build-date metadata below.
control_release_banner_row1:
        db      0x46, 0x69, 0x72, 0x6D, 0x77, 0x61, 0x72, 0x65, 0x20, 0x56, 0x31, 0x2E, 0x37, 0x33, 0x00 ; "Firmware V1.73"
control_release_banner_row2:
        db      0x52, 0x65, 0x76, 0x20, 0x78, 0x35, 0x34, 0x20, 0x32, 0x30, 0x32, 0x36, 0x30, 0x36, 0x32, 0x35, 0x00 ; "Rev x54 20260625"

; --- Canonical V1.73 release metadata (flashed app space, not runtime state) ---
        org     0x77b0

control_release_metadata:
        db      0x44, 0x4c, 0x43, 0x50                    ; "DLCP"
        db      0x43, 0x54, 0x52, 0x4c                    ; "CTRL"
        db      0x01, 0x07, 0x33, 0x54                    ; V1.73 + monotonic release revision
        db      0x20, 0x26, 0x06, 0x25                    ; build date 20260625 (BCD YYYYMMDD)

; --- V1.73 bootloader pin (app code may grow beyond stock extents) ---
        org     0x7800

bootloader_entry:                                                  ; address: 0x007800

        goto    bootloader_protocol_entry                                   ; dest: 0x007afe

bootloader_addr_at_or_above_bound_w:                                               ; address: 0x007804

        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x03
        bra     bootloader_addr_compare_common                                   ; dest: 0x00780e

bootloader_addr_below_bound_w:                                               ; address: 0x00780a

        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x04

bootloader_addr_compare_common:                                                  ; address: 0x00780e

        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movf    (Common_RAM + 14), W, A                     ; reg: 0x00e
        subwf   (Common_RAM + 12), W, A                     ; reg: 0x00c
        bnz     bootloader_addr_compare_apply_mode_mask
        movf    (Common_RAM + 13), W, A                     ; reg: 0x00d
        subwf   (Common_RAM + 11), W, A                     ; reg: 0x00b

bootloader_addr_compare_apply_mode_mask:                                                  ; address: 0x00781a

        movlw   0x04
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        movlw   0x01
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x02
        andwf   (Common_RAM + 7), W, A                      ; reg: 0x007
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        return  0x0

bootloader_lcd_clear_display:                                               ; address: 0x00782c

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xfe
        rcall   bootloader_io_dispatch_byte_w                                ; dest: 0x007a34
        movlw   0x01
        rcall   bootloader_io_dispatch_byte_w                                ; dest: 0x007a34
        movlw   0x75
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movlw   0x30
        bra     bootloader_delay_count16_inner_w                                ; dest: 0x007ac2

bootloader_lcd_command_w:                                               ; address: 0x007840

        clrf    (Common_RAM + 1), A                         ; reg: 0x001
        bsf     (Common_RAM + 1), 0x7, A                    ; reg: 0x001
        movwf   (Common_RAM + 22), A                        ; reg: 0x016
        movlw   0xfe
        rcall   bootloader_io_dispatch_byte_w                                ; dest: 0x007a34
        movf    (Common_RAM + 22), W, A                     ; reg: 0x016
        bra     bootloader_io_dispatch_byte_w                                ; dest: 0x007a34

bootloader_parse_hex_from_fsr0:                                               ; address: 0x00784e

        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        movlw   0x80
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        bra     bootloader_parse_hex_init                                   ; dest: 0x007856

bootloader_parse_hex_init:                                                  ; address: 0x007856

        clrf    (Common_RAM + 15), A                        ; reg: 0x00f
        clrf    (Common_RAM + 16), A                        ; reg: 0x010
        clrf    (Common_RAM + 17), A                        ; reg: 0x011
        clrf    (Common_RAM + 17), A                        ; reg: 0x011
        bcf     (Common_RAM + 7), 0x5, A                    ; reg: 0x007

bootloader_parse_hex_read_first_or_sign:                                                  ; address: 0x007860

        rcall   bootloader_input_read_byte_w                                ; dest: 0x007a3c
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        addlw   0xd3
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     (Common_RAM + 7), 0x5, A                    ; reg: 0x007
        addlw   0x2d
        addlw   0xc6
        bc      bootloader_parse_hex_try_alpha_first
        addlw   0x0a
        bnc     bootloader_parse_hex_read_first_or_sign
        bra     bootloader_parse_hex_accept_nibble                                   ; dest: 0x007882

bootloader_parse_hex_try_alpha_first:                                                  ; address: 0x007878

        addlw   0xf3
        bc      bootloader_parse_hex_read_first_or_sign
        addlw   0x06
        bnc     bootloader_parse_hex_read_first_or_sign
        addlw   0x0a

bootloader_parse_hex_accept_nibble:                                                  ; address: 0x007882

        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x04
        movwf   (Common_RAM + 14), A                        ; reg: 0x00e

bootloader_parse_hex_shift_accumulator:                                                  ; address: 0x007888

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 15), F, A                     ; reg: 0x00f
        rlcf    (Common_RAM + 16), F, A                     ; reg: 0x010
        rlcf    (Common_RAM + 17), F, A                     ; reg: 0x011
        rlcf    (Common_RAM + 18), F, A                     ; reg: 0x012
        decfsz  (Common_RAM + 14), F, A                     ; reg: 0x00e
        bra     bootloader_parse_hex_shift_accumulator                                   ; dest: 0x007888
        movf    (Common_RAM + 13), W, A                     ; reg: 0x00d
        iorwf   (Common_RAM + 15), F, A                     ; reg: 0x00f
        decf    (Common_RAM + 5), F, A                      ; reg: 0x005
        bz      bootloader_parse_hex_apply_sign_if_needed
        rcall   bootloader_input_read_byte_w                                ; dest: 0x007a3c
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        addlw   0xc6
        bc      bootloader_parse_hex_try_alpha_next
        addlw   0x0a
        bnc     bootloader_parse_hex_apply_sign_if_needed
        bra     bootloader_parse_hex_accept_nibble                                   ; dest: 0x007882

bootloader_parse_hex_try_alpha_next:                                                  ; address: 0x0078ae

        addlw   0xf3
        bc      bootloader_parse_hex_apply_sign_if_needed
        addlw   0x06
        bnc     bootloader_parse_hex_apply_sign_if_needed
        addlw   0x0a
        bra     bootloader_parse_hex_accept_nibble                                   ; dest: 0x007882

bootloader_parse_hex_apply_sign_if_needed:                                                  ; address: 0x0078ba

        btfss   (Common_RAM + 7), 0x5, A                    ; reg: 0x007
        bra     bootloader_parse_hex_return_low_w                                   ; dest: 0x0078d4
        comf    (Common_RAM + 15), F, A                     ; reg: 0x00f
        comf    (Common_RAM + 16), F, A                     ; reg: 0x010
        comf    (Common_RAM + 17), F, A                     ; reg: 0x011
        comf    (Common_RAM + 18), F, A                     ; reg: 0x012
        incf    (Common_RAM + 15), F, A                     ; reg: 0x00f
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        incf    (Common_RAM + 16), F, A                     ; reg: 0x010
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        incf    (Common_RAM + 17), F, A                     ; reg: 0x011
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        incf    (Common_RAM + 18), F, A                     ; reg: 0x012

bootloader_parse_hex_return_low_w:                                                  ; address: 0x0078d4

        movf    (Common_RAM + 15), W, A                     ; reg: 0x00f
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        clrf    (Common_RAM + 5), A                         ; reg: 0x005

bootloader_emit_hex16_w:                                               ; address: 0x0078dc

        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        clrf    (Common_RAM + 16), A                        ; reg: 0x010
        bcf     Common_RAM, 0x3, A                          ; reg: 0x000
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     Common_RAM, 0x3, A                          ; reg: 0x000
        movlw   0x04
        movwf   (Common_RAM + 4), A                         ; reg: 0x004
        swapf   (Common_RAM + 16), W, A                     ; reg: 0x010
        rcall   bootloader_emit_hex_nibble_w                                ; dest: 0x0078fa
        movf    (Common_RAM + 16), W, A                     ; reg: 0x010
        rcall   bootloader_emit_hex_nibble_w                                ; dest: 0x0078fa
        swapf   (Common_RAM + 15), W, A                     ; reg: 0x00f
        rcall   bootloader_emit_hex_nibble_w                                ; dest: 0x0078fa
        movf    (Common_RAM + 15), W, A                     ; reg: 0x00f

bootloader_emit_hex_nibble_w:                                               ; address: 0x0078fa

        andlw   0x0f
        addlw   0xf6
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        addlw   0x07
        addlw   0x0a
        bra     bootloader_emit_hex_width_gate                                   ; dest: 0x007906

bootloader_emit_hex_width_gate:                                                  ; address: 0x007906

        movwf   (Common_RAM + 11), A                        ; reg: 0x00b
        dcfsnz  (Common_RAM + 4), F, A                      ; reg: 0x004
        bcf     Common_RAM, 0x3, A                          ; reg: 0x000
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        bz      bootloader_emit_hex_leading_zero_gate
        subwf   (Common_RAM + 4), W, A                      ; reg: 0x004
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        bra     bootloader_emit_hex_return                                   ; dest: 0x007924

bootloader_emit_hex_leading_zero_gate:                                                  ; address: 0x007916

        movf    (Common_RAM + 11), W, A                     ; reg: 0x00b
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bcf     Common_RAM, 0x3, A                          ; reg: 0x000
        btfsc   Common_RAM, 0x3, A                          ; reg: 0x000
        bra     bootloader_emit_hex_return                                   ; dest: 0x007924
        addlw   0x30
        bra     bootloader_io_dispatch_byte_w                                ; dest: 0x007a34

bootloader_emit_hex_return:                                                  ; address: 0x007924

        return  0x0

bootloader_emit_bounded_string_from_ptr_w:                                               ; address: 0x007926

        movwf   (Common_RAM + 15), A                        ; reg: 0x00f

bootloader_emit_string_loop:                                                  ; address: 0x007928

        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        return  0x0
        movff   (Common_RAM + 15), FSR0L                    ; reg1: 0x00f, reg2: 0xfe9
        movff   (Common_RAM + 16), FSR0H                    ; reg1: 0x010, reg2: 0xfea
        movf    INDF0, W, A                                 ; reg: 0xfef
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        return  0x0
        rcall   bootloader_io_dispatch_byte_w                                ; dest: 0x007a34
        infsnz  (Common_RAM + 15), F, A                     ; reg: 0x00f
        incf    (Common_RAM + 16), F, A                     ; reg: 0x010
        decf    (Common_RAM + 4), F, A                      ; reg: 0x004
        bra     bootloader_emit_string_loop                                   ; dest: 0x007928

bootloader_lcd_emit_pmem_string:                                               ; address: 0x007946

        clrf    EECON1, A                                   ; reg: 0xfa6
        bsf     EECON1, EEPGD, A                            ; reg: 0xfa6, bit: 7

bootloader_lcd_emit_pmem_string_loop:                                                  ; address: 0x00794a

        tblrd*+
        movf    TABLAT, W, A                                ; reg: 0xff5
        bz      bootloader_lcd_emit_pmem_string_done
        rcall   bootloader_lcd_write_byte_w                                ; dest: 0x007956
        bra     bootloader_lcd_emit_pmem_string_loop                                   ; dest: 0x00794a

bootloader_lcd_emit_pmem_string_done:                                                  ; address: 0x007954

        return  0x0

bootloader_lcd_write_byte_w:                                               ; address: 0x007956

        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        bcf     LATB, LATB4, A                              ; reg: 0xf8a, bit: 4
        bcf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        bcf     TRISB, RB4, A                               ; reg: 0xf93, bit: 4
        bcf     TRISA, RA5, A                               ; reg: 0xf92, bit: 5
        movlw   0xf0
        andwf   TRISB, F, A                                 ; reg: 0xf93
        movf    (Common_RAM + 20), W, A                     ; reg: 0x014
        btfsc   Common_RAM, 0x1, A                          ; reg: 0x000
        bra     bootloader_lcd_write_byte_common                                   ; dest: 0x0079a6
        movlw   0x3a
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movlw   0x98
        rcall   bootloader_delay_count16_inner_w                                ; dest: 0x007ac2
        movlw   0x33
        movwf   (Common_RAM + 19), A                        ; reg: 0x013
        rcall   bootloader_lcd_strobe_nibble                                ; dest: 0x0079cc
        movlw   0x13
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movlw   0x88
        rcall   bootloader_delay_count16_inner_w                                ; dest: 0x007ac2
        rcall   bootloader_lcd_strobe_nibble                                ; dest: 0x0079cc
        movlw   0x64
        rcall   bootloader_delay_count8_inner_w                                ; dest: 0x007ac0
        rcall   bootloader_lcd_strobe_nibble                                ; dest: 0x0079cc
        movlw   0x64
        rcall   bootloader_delay_count8_inner_w                                ; dest: 0x007ac0
        movlw   0x22
        movwf   (Common_RAM + 19), A                        ; reg: 0x013
        rcall   bootloader_lcd_strobe_nibble                                ; dest: 0x0079cc
        movlw   0x28
        rcall   bootloader_lcd_write_command_w                                ; dest: 0x0079a4
        movlw   0x0c
        rcall   bootloader_lcd_write_command_w                                ; dest: 0x0079a4
        movlw   0x06
        rcall   bootloader_lcd_write_command_w                                ; dest: 0x0079a4
        bsf     Common_RAM, 0x1, A                          ; reg: 0x000
        movf    (Common_RAM + 20), W, A                     ; reg: 0x014
        bra     bootloader_lcd_write_byte_common                                   ; dest: 0x0079a6

bootloader_lcd_write_command_w:                                               ; address: 0x0079a4

        bsf     Common_RAM, 0x0, A                          ; reg: 0x000

bootloader_lcd_write_byte_common:                                                  ; address: 0x0079a6

        movwf   (Common_RAM + 19), A                        ; reg: 0x013
        btfss   Common_RAM, 0x0, A                          ; reg: 0x000
        bra     bootloader_lcd_write_data_or_prefix                                   ; dest: 0x0079c0
        bcf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        sublw   0x03
        bnc     bootloader_lcd_write_two_nibbles
        rcall   bootloader_lcd_write_two_nibbles                                ; dest: 0x0079c8
        movlw   0x07
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movlw   0xd0
        rcall   bootloader_delay_count16_inner_w                                ; dest: 0x007ac2
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

bootloader_lcd_write_data_or_prefix:                                                  ; address: 0x0079c0

        bsf     Common_RAM, 0x0, A                          ; reg: 0x000
        sublw   0xfe
        bz      bootloader_lcd_return_saved_w
        bsf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5

bootloader_lcd_write_two_nibbles:                                               ; address: 0x0079c8

        swapf   (Common_RAM + 19), F, A                     ; reg: 0x013
        btfss   Common_RAM, 0x0, A                          ; reg: 0x000

bootloader_lcd_strobe_nibble:                                               ; address: 0x0079cc

        bcf     Common_RAM, 0x0, A                          ; reg: 0x000
        bsf     LATB, LATB4, A                              ; reg: 0xf8a, bit: 4
        movlw   0xf0
        andwf   PORTB, F, A                                 ; reg: 0xf81
        movf    (Common_RAM + 19), W, A                     ; reg: 0x013
        andlw   0x0f
        iorwf   PORTB, F, A                                 ; reg: 0xf81
        bcf     LATB, LATB4, A                              ; reg: 0xf8a, bit: 4
        swapf   (Common_RAM + 19), F, A                     ; reg: 0x013
        btfsc   Common_RAM, 0x0, A                          ; reg: 0x000
        bra     bootloader_lcd_strobe_nibble                                ; dest: 0x0079cc
        movlw   0x32
        rcall   bootloader_delay_count8_inner_w                                ; dest: 0x007ac0
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0

bootloader_lcd_return_saved_w:                                                  ; address: 0x0079e8

        movf    (Common_RAM + 20), W, A                     ; reg: 0x014
        return  0x0

bootloader_uart_rx_byte_with_timeout:                                               ; address: 0x0079ec

        btfsc   RCSTA, OERR, A                              ; reg: 0xfab, bit: 1
        bcf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        bsf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        movff   (Common_RAM + 2), (Common_RAM + 11)         ; reg1: 0x002, reg2: 0x00b
        movff   (Common_RAM + 6), (Common_RAM + 12)         ; reg1: 0x006, reg2: 0x00c
        clrf    (Common_RAM + 13), A                        ; reg: 0x00d
        clrf    (Common_RAM + 14), A                        ; reg: 0x00e

bootloader_uart_rx_wait_loop:                                                  ; address: 0x0079fe

        nop
        bra     bootloader_uart_rx_poll_or_timeout                                   ; dest: 0x007a02

bootloader_uart_rx_poll_or_timeout:                                                  ; address: 0x007a02

        nop
        btfsc   PIR1, RCIF, A                               ; reg: 0xf9e, bit: 5
        bra     bootloader_uart_rx_return_byte_w                                   ; dest: 0x007a24
        setf    WREG, A                                     ; reg: 0xfe8
        addwf   (Common_RAM + 13), F, A                     ; reg: 0x00d
        addwfc  (Common_RAM + 14), F, A                     ; reg: 0x00e
        addwfc  (Common_RAM + 11), F, A                     ; reg: 0x00b
        addwfc  (Common_RAM + 12), F, A                     ; reg: 0x00c
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        infsnz  (Common_RAM + 13), W, A                     ; reg: 0x00d
        incfsz  (Common_RAM + 14), W, A                     ; reg: 0x00e
        bra     bootloader_uart_rx_wait_loop                                   ; dest: 0x0079fe
        movlw   0xb7
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        clrf    (Common_RAM + 14), A                        ; reg: 0x00e
        bra     bootloader_uart_rx_poll_or_timeout                                   ; dest: 0x007a02

bootloader_uart_rx_return_byte_w:                                                  ; address: 0x007a24

        movf    RCREG, W, A                                 ; reg: 0xfae
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

bootloader_uart_tx_byte_w:                                               ; address: 0x007a2a

        btfss   PIR1, TXIF, A                               ; reg: 0xf9e, bit: 4
        bra     bootloader_uart_tx_byte_w                                ; dest: 0x007a2a
        movwf   TXREG, A                                    ; reg: 0xfad
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

bootloader_io_dispatch_byte_w:                                               ; address: 0x007a34

        btfsc   (Common_RAM + 1), 0x7, A                    ; reg: 0x001
        bra     bootloader_lcd_write_byte_w                                ; dest: 0x007956
        btfsc   (Common_RAM + 1), 0x2, A                    ; reg: 0x001
        bra     bootloader_uart_tx_byte_w                                ; dest: 0x007a2a

bootloader_input_read_byte_w:                                               ; address: 0x007a3c

        movf    (Common_RAM + 27), F, A                     ; reg: 0x01b
        bz      bootloader_uart_rx_byte_with_timeout
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        btfsc   (Common_RAM + 27), 0x7, A                   ; reg: 0x01b
        movf    POSTINC0, W, A                              ; reg: 0xfee
        return  0x0

bootloader_eeprom_read_byte_at_w:                                               ; address: 0x007a48

        movwf   EEADR, A                                    ; reg: 0xfa9
        clrf    EECON1, A                                   ; reg: 0xfa6
        bsf     EECON1, RD, A                               ; reg: 0xfa6, bit: 0
        movf    EEDATA, W, A                                ; reg: 0xfa8
        incf    EEADR, F, A                                 ; reg: 0xfa9
        return  0x0

bootloader_eeprom_write_byte_inc_addr_w:                                               ; address: 0x007a54

        movwf   EEDATA, A                                   ; reg: 0xfa8
        clrf    EECON1, A                                   ; reg: 0xfa6
        bsf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        movlw   0x55
        movwf   EECON2, A                                   ; reg: 0xfa7
        movlw   0xaa
        movwf   EECON2, A                                   ; reg: 0xfa7
        bsf     EECON1, WR, A                               ; reg: 0xfa6, bit: 1

bootloader_eeprom_wait_write_done:                                                  ; address: 0x007a64

        btfsc   EECON1, WR, A                               ; reg: 0xfa6, bit: 1
        bra     bootloader_eeprom_wait_write_done                                   ; dest: 0x007a64
        bcf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        incf    EEADR, F, A                                 ; reg: 0xfa9
        return  0x0

bootloader_flash_stage_byte_and_commit_row_w:                                               ; address: 0x007a6e

        movwf   TABLAT, A                                   ; reg: 0xff5
        tblwt*
        incf    TBLPTRL, W, A                               ; reg: 0xff6
        andlw   0x1f
        bnz     bootloader_flash_advance_tblptr_return
        movlw   0x84
        movwf   EECON1, A                                   ; reg: 0xfa6
        movlw   0x55
        movwf   EECON2, A                                   ; reg: 0xfa7
        movlw   0xaa
        movwf   EECON2, A                                   ; reg: 0xfa7
        bsf     EECON1, WR, A                               ; reg: 0xfa6, bit: 1
        bra     bootloader_flash_commit_cleanup                                   ; dest: 0x007a88

bootloader_flash_commit_cleanup:                                                  ; address: 0x007a88

        bcf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2

bootloader_flash_advance_tblptr_return:                                                  ; address: 0x007a8a

        infsnz  TBLPTRL, F, A                               ; reg: 0xff6
        incf    TBLPTRH, F, A                               ; reg: 0xff7
        return  0x0

bootloader_flash_set_low_addr_and_erase_row:                                               ; address: 0x007a90

        movwf   TBLPTRL, A                                  ; reg: 0xff6

bootloader_flash_erase_row_at_tblptr:                                               ; address: 0x007a92

        movlw   0x94
        movwf   EECON1, A                                   ; reg: 0xfa6
        movlw   0x55
        movwf   EECON2, A                                   ; reg: 0xfa7
        movlw   0xaa
        movwf   EECON2, A                                   ; reg: 0xfa7
        bsf     EECON1, WR, A                               ; reg: 0xfa6, bit: 1
        nop
        bcf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        return  0x0

bootloader_delay_count8_w:                                               ; address: 0x007aa6

        clrf    (Common_RAM + 14), A                        ; reg: 0x00e

bootloader_delay_count16_w:                                               ; address: 0x007aa8

        movwf   (Common_RAM + 13), A                        ; reg: 0x00d

bootloader_delay_outer_decrement:                                                  ; address: 0x007aaa

        movlw   0xff
        addwf   (Common_RAM + 13), F, A                     ; reg: 0x00d
        addwfc  (Common_RAM + 14), F, A                     ; reg: 0x00e
        bra     bootloader_delay_outer_tick                                   ; dest: 0x007ab2

bootloader_delay_outer_tick:                                                  ; address: 0x007ab2

        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        movlw   0x03
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movlw   0xe5
        rcall   bootloader_delay_count16_inner_w                                ; dest: 0x007ac2
        bra     bootloader_delay_outer_decrement                                   ; dest: 0x007aaa

bootloader_delay_count8_inner_w:                                               ; address: 0x007ac0

        clrf    (Common_RAM + 12), A                        ; reg: 0x00c

bootloader_delay_count16_inner_w:                                               ; address: 0x007ac2

        addlw   0xfa
        movwf   (Common_RAM + 11), A                        ; reg: 0x00b
        nop
        bnc     bootloader_delay_inner_high_loop
        bra     bootloader_delay_inner_low_loop                                   ; dest: 0x007acc

bootloader_delay_inner_low_loop:                                                  ; address: 0x007acc

        decf    (Common_RAM + 11), F, A                     ; reg: 0x00b
        bc      bootloader_delay_inner_low_loop

bootloader_delay_inner_high_loop:                                                  ; address: 0x007ad0

        decf    (Common_RAM + 11), F, A                     ; reg: 0x00b
        decf    (Common_RAM + 12), F, A                     ; reg: 0x00c
        bc      bootloader_delay_inner_low_loop
        nop
        return  0x0

bootloader_copy_record_field_to_parse_buffer:                                               ; address: 0x007ada

        dcfsnz  PRODL, F, A                                 ; reg: 0xff3
        bra     bootloader_copy_record_field_to_parse_buffer__copy_loop                                   ; dest: 0x007ae2
        movf    POSTINC1, F, A                              ; reg: 0xfe6
        bra     bootloader_copy_record_field_to_parse_buffer                                ; dest: 0x007ada

bootloader_copy_record_field_to_parse_buffer__copy_loop:                                                  ; address: 0x007ae2

        movff   POSTINC1, POSTINC0                          ; reg1: 0xfe6, reg2: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     bootloader_copy_record_field_to_parse_buffer__copy_loop                                   ; dest: 0x007ae2
        return  0x0
        movwf   (Common_RAM + 66), B                        ; reg: 0x042
        btg     0x6f, 0x2, A                                ; reg: 0xf6f
        movwf   stock_06C_b0, B                                     ; reg: 0x06c
        cpfsgt  0x61, A                                     ; reg: 0xf61
        btg     0x65, 0x1, A                                ; reg: 0xf65
        negf    (Common_RAM + 32), B                        ; reg: 0x020
        cpfsgt  0x6f, A                                     ; reg: 0xf6f
        addwfc  0x65, W, A                                  ; reg: 0xf65
        nop

bootloader_protocol_entry:                                                  ; address: 0x007afe

        clrf    TBLPTRU, A                                  ; reg: 0xff8
        clrf    Common_RAM, A                               ; reg: 0x000
        movlw   0x05                                        ; SPBRG: 31250 baud @ 4MIPS (BRG16=0 BRGH=0 → SPBRG=5)
        movwf   SPBRG, A                                    ; reg: 0xfaf
        movlw   0x20
        movwf   TXSTA, A                                    ; reg: 0xfac
        movlw   0x90
        movwf   RCSTA, A                                    ; reg: 0xfab
        movlb   0x0
        movlw   0xdf                                        ; TRISA: RA1..RA4 input (buttons), RA5 output (LCD RS)
        movwf   TRISA, A                                    ; reg: 0xf92
        movlw   0x3c                                        ; TRISB: RB0..RB3 output (LCD D4..D7 muxed), RB2/RB3 inputs, RB4 E strobe
        movwf   TRISB, A                                    ; reg: 0xf93
        movlw   0xbd                                        ; TRISC: RC6 TX, RC7 RX, RC1 output (LED), RC0/RC5 inputs (buttons)
        movwf   TRISC, A                                    ; reg: 0xf94
        clrf    CM1CON0, A                                  ; reg: 0xf7b
        clrf    CM2CON0, A                                  ; reg: 0xf7a
        clrf    ANSEL, A                                    ; reg: 0xf7e
        clrf    ANSELH, A                                   ; reg: 0xf7f
        movlw   0x0f                                        ; ADCON1: all PORTA digital (vendor init)
        movwf   ADCON1, A                                   ; reg: 0xfc1
        movlw   0x05
        rcall   bootloader_delay_count8_w                                ; dest: 0x007aa6
        movlw   0x46
        movwf   stock_076_b0, B                                     ; reg: 0x076
        movlw   0x57
        movwf   stock_077_b0, B                                     ; reg: 0x077
        movlw   0x5f
        movwf   stock_078_b0, B                                     ; reg: 0x078
        movlw   0x55
        movwf   stock_079_b0, B                                     ; reg: 0x079
        movlw   0x70
        movwf   stock_07A_b0, B                                     ; reg: 0x07a
        movlw   0x64
        movwf   stock_07B_b0, B                                     ; reg: 0x07b
        bcf     TRISB, RB6, A                               ; reg: 0xf93, bit: 6
        bcf     LATB, LATB6, A                              ; reg: 0xf8a, bit: 6
        bcf     stock_082_b0, 0x1, B                                ; reg: 0x082
        rcall   bootloader_manual_entry                                ; dest: 0x007f02
        rrcf    stock_082_b0, W, B                                  ; reg: 0x082
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        bc      bootloader_manual_entry_mark_update_pending
        movlw   0xff
        rcall   bootloader_eeprom_read_byte_at_w                                ; dest: 0x007a48
        movwf   control_flags_acc, A                        ; reg: 0x01f
        decfsz  control_flags_acc, W, A                     ; reg: 0x01f
        bra     bootloader_boot_mode_marker_02_handoff                                   ; dest: 0x007b68
        setf    EEADR, A                                    ; reg: 0xfa9
        movlw   0x77
        rcall   bootloader_eeprom_write_byte_inc_addr_w                                ; dest: 0x007a54
        goto    aux_vector_cold_init_entry                                   ; dest: 0x000040
        bra     bootloader_boot_mode_enter_protocol_join                                   ; dest: 0x007b7a

bootloader_boot_mode_marker_02_handoff:                                                  ; address: 0x007b68

        movlw   0x02
        cpfseq  control_flags_acc, A                        ; reg: 0x01f
        bra     bootloader_boot_mode_enter_protocol_join                                   ; dest: 0x007b7a
        movlw   0xfe
        movwf   EEADR, A                                    ; reg: 0xfa9
        movlw   0x01
        rcall   bootloader_eeprom_write_byte_inc_addr_w                                ; dest: 0x007a54
        goto    aux_vector_cold_init_entry                                   ; dest: 0x000040

bootloader_boot_mode_enter_protocol_join:                                                  ; address: 0x007b7a

        bra     bootloader_session_init                                   ; dest: 0x007b82

bootloader_manual_entry_mark_update_pending:                                                  ; address: 0x007b7c

        setf    EEADR, A                                    ; reg: 0xfa9
        movlw   0x00
        rcall   bootloader_eeprom_write_byte_inc_addr_w                                ; dest: 0x007a54

bootloader_session_init:                                                  ; address: 0x007b82

        bsf     TXSTA, TXEN, A                              ; reg: 0xfac, bit: 5
        bsf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        bsf     RCSTA, SPEN, A                              ; reg: 0xfab, bit: 7
        rcall   bootloader_lcd_clear_display                                ; dest: 0x00782c
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bsf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        rcall   bootloader_lcd_command_w                                ; dest: 0x007840
        movlw   0x7a
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   0xec
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        rcall   bootloader_lcd_emit_pmem_string                                ; dest: 0x007946
        lfsr    0x0, stock_024_b0_phys
        movlw   0x1f

bootloader_low_header_cache_clear_loop:                                                  ; address: 0x007ba4

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     bootloader_low_header_cache_clear_loop                                   ; dest: 0x007ba4
        bcf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        movlw   0x40
        movwf   ir_decoded_cmd_acc, A                        ; reg: 0x01d
        clrf    ir_decoded_addr_acc, A                        ; reg: 0x01e
        clrf    (Common_RAM + 32), A                        ; reg: 0x020
        clrf    (Common_RAM + 33), A                        ; reg: 0x021

bootloader_prompt_cycle_reset:                                                  ; address: 0x007bb6

        clrf    (Common_RAM + 8), A                         ; reg: 0x008

bootloader_prompt_magic_copy_loop:                                                  ; address: 0x007bb8

        lfsr    0x0, stock_076_b0_phys
        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 25), A                        ; reg: 0x019
        lfsr    0x0, stock_07C_b0_phys
        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        movff   (Common_RAM + 25), PLUSW0                   ; reg1: 0x019, reg2: 0xfeb
        incf    (Common_RAM + 8), F, A                      ; reg: 0x008
        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        sublw   0x06
        bnz     bootloader_prompt_magic_copy_loop
        rcall   bootloader_prompt_send                                ; dest: 0x007e60

bootloader_receive_record_reset:                                                  ; address: 0x007bd6

        lfsr    0x0, stock_043_b0_phys
        movlw   0x2e

bootloader_receive_record_clear_buffer_loop:                                                  ; address: 0x007bdc

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     bootloader_receive_record_clear_buffer_loop                                   ; dest: 0x007bdc
        movlw   0xf4
        movwf   (Common_RAM + 2), A                         ; reg: 0x002
        movlw   0x01
        movwf   (Common_RAM + 6), A                         ; reg: 0x006

bootloader_wait_for_record_start_colon:                                                  ; address: 0x007bea

        rcall   bootloader_uart_rx_byte_with_timeout                                ; dest: 0x0079ec
        bnc     bootloader_prompt_cycle_reset
        sublw   0x3a
        bnz     bootloader_wait_for_record_start_colon
        lfsr    0x1, stock_043_b0_phys

bootloader_receive_record_body_loop:                                                  ; address: 0x007bf6

        rcall   bootloader_uart_rx_byte_with_timeout                                ; dest: 0x0079ec
        bnc     bootloader_prompt_cycle_reset
        sublw   0x0d
        bnz     bootloader_store_record_body_byte
        clrf    POSTINC1, A                                 ; reg: 0xfe6
        bra     bootloader_record_zero_prefix_gate                                   ; dest: 0x007c0a

bootloader_store_record_body_byte:                                                  ; address: 0x007c02

        movf    RCREG, W, A                                 ; reg: 0xfae
        movwf   POSTINC1, A                                 ; reg: 0xfe6
        bz      bootloader_record_zero_prefix_gate
        bra     bootloader_receive_record_body_loop                                   ; dest: 0x007bf6

bootloader_record_zero_prefix_gate:                                                  ; address: 0x007c0a

        bcf     stock_082_b0, 0x0, B                                ; reg: 0x082
        clrf    control_flags_acc, A                        ; reg: 0x01f

bootloader_record_zero_prefix_check_loop:                                                  ; address: 0x007c0e

        movlw   0x06
        cpfslt  control_flags_acc, A                        ; reg: 0x01f
        bra     bootloader_record_parse_or_finalize_gate                                   ; dest: 0x007c2a
        lfsr    0x0, stock_043_b0_phys
        movf    control_flags_acc, W, A                     ; reg: 0x01f
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x30
        subwf   (Common_RAM + 8), W, A                      ; reg: 0x008
        bz      bootloader_record_zero_prefix_next
        bsf     stock_082_b0, 0x0, B                                ; reg: 0x082

bootloader_record_zero_prefix_next:                                                  ; address: 0x007c26

        incf    control_flags_acc, F, A                     ; reg: 0x01f
        bnz     bootloader_record_zero_prefix_check_loop

bootloader_record_parse_or_finalize_gate:                                                  ; address: 0x007c2a

        rrcf    stock_082_b0, W, B                                  ; reg: 0x082
        bc      bootloader_record_parse_begin
        bra     bootloader_finalize_update_and_reset                                   ; dest: 0x007f56

bootloader_record_parse_begin:                                                  ; address: 0x007c30

        clrf    (Common_RAM + 34), A                        ; reg: 0x022
        clrf    (Common_RAM + 35), A                        ; reg: 0x023
        clrf    control_flags_acc, A                        ; reg: 0x01f

bootloader_record_checksum_sum_loop:                                                  ; address: 0x007c36

        movlw   0x14
        cpfslt  control_flags_acc, A                        ; reg: 0x01f
        bra     bootloader_record_checksum_verify                                   ; dest: 0x007c74
        lfsr    0x0, stock_071_b0_phys
        lfsr    0x1, stock_043_b0_phys
        movf    control_flags_acc, W, A                     ; reg: 0x01f
        mullw   0x02
        movff   PRODL, (Common_RAM + 25)                    ; reg1: 0xff3, reg2: 0x019
        movff   PRODH, (Common_RAM + 26)                    ; reg1: 0xff4, reg2: 0x01a
        incf    (Common_RAM + 25), W, A                     ; reg: 0x019
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x02
        rcall   bootloader_copy_record_field_to_parse_buffer                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        lfsr    0x0, stock_071_b0_phys
        call    bootloader_parse_hex_from_fsr0, 0x0                           ; dest: 0x00784e
        movwf   (Common_RAM + 25), A                        ; reg: 0x019
        movff   (Common_RAM + 16), (Common_RAM + 26)        ; reg1: 0x010, reg2: 0x01a
        movf    (Common_RAM + 25), W, A                     ; reg: 0x019
        addwf   (Common_RAM + 34), F, A                     ; reg: 0x022
        movf    (Common_RAM + 26), W, A                     ; reg: 0x01a
        addwfc  (Common_RAM + 35), F, A                     ; reg: 0x023
        incf    control_flags_acc, F, A                     ; reg: 0x01f
        bnz     bootloader_record_checksum_sum_loop

bootloader_record_checksum_verify:                                                  ; address: 0x007c74

        movf    (Common_RAM + 34), W, A                     ; reg: 0x022
        sublw   0xff
        movwf   (Common_RAM + 25), A                        ; reg: 0x019
        movlw   0xff
        subfwb  (Common_RAM + 35), W, A                     ; reg: 0x023
        movwf   (Common_RAM + 26), A                        ; reg: 0x01a
        movlw   0x01
        addwf   (Common_RAM + 25), W, A                     ; reg: 0x019
        movwf   (Common_RAM + 34), A                        ; reg: 0x022
        movlw   0x00
        addwfc  (Common_RAM + 26), W, A                     ; reg: 0x01a
        movwf   (Common_RAM + 35), A                        ; reg: 0x023
        lfsr    0x0, stock_071_b0_phys
        lfsr    0x1, stock_043_b0_phys
        movlw   0x29
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x02
        rcall   bootloader_copy_record_field_to_parse_buffer                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        lfsr    0x0, stock_071_b0_phys
        call    bootloader_parse_hex_from_fsr0, 0x0                           ; dest: 0x00784e
        movwf   (Common_RAM + 32), A                        ; reg: 0x020
        movff   (Common_RAM + 16), (Common_RAM + 33)        ; reg1: 0x010, reg2: 0x021
        movf    (Common_RAM + 32), W, A                     ; reg: 0x020
        cpfseq  (Common_RAM + 34), A                        ; reg: 0x022
        bra     bootloader_receive_next_record                                   ; dest: 0x007e5e
        tstfsz  (Common_RAM + 33), A                        ; reg: 0x021
        bra     bootloader_receive_next_record                                   ; dest: 0x007e5e
        lfsr    0x0, stock_071_b0_phys
        lfsr    0x1, stock_043_b0_phys
        movlw   0x03
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x04
        rcall   bootloader_copy_record_field_to_parse_buffer                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        lfsr    0x0, stock_071_b0_phys
        call    bootloader_parse_hex_from_fsr0, 0x0                           ; dest: 0x00784e
        movwf   ir_decoded_cmd_acc, A                        ; reg: 0x01d
        movff   (Common_RAM + 16), ir_decoded_addr        ; reg1: 0x010, reg2: 0x01e
        movlw   0x3f
        andwf   ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        movwf   (Common_RAM + 8), A                         ; reg: 0x008
        clrf    (Common_RAM + 9), A                         ; reg: 0x009
        movf    (Common_RAM + 9), W, A                      ; reg: 0x009
        iorwf   (Common_RAM + 8), W, A                      ; reg: 0x008
        bz      bootloader_record_page_aligned_flag_set
        movlw   0x00
        bra     bootloader_record_page_erase_gate                                   ; dest: 0x007cea

bootloader_record_page_aligned_flag_set:                                                  ; address: 0x007ce8

        movlw   0x01

bootloader_record_page_erase_gate:                                                  ; address: 0x007cea

        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        movff   ir_decoded_cmd_b0_phys, (Common_RAM + 11)        ; reg1: 0x01d, reg2: 0x00b
        movff   ir_decoded_addr_b0_phys, (Common_RAM + 12)        ; reg1: 0x01e, reg2: 0x00c
        movlw   0x77
        movwf   (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0xc0
        call    bootloader_addr_below_bound_w, 0x0                           ; dest: 0x00780a
        andwf   (Common_RAM + 28), F, A                     ; reg: 0x01c
        movff   ir_decoded_cmd_b0_phys, (Common_RAM + 11)        ; reg1: 0x01d, reg2: 0x00b
        movff   ir_decoded_addr_b0_phys, (Common_RAM + 12)        ; reg1: 0x01e, reg2: 0x00c
        clrf    (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0x40
        call    bootloader_addr_at_or_above_bound_w, 0x0                           ; dest: 0x007804
        andwf   (Common_RAM + 28), F, A                     ; reg: 0x01c
        bz      bootloader_record_address_range_gate
        movf    ir_decoded_addr_acc, W, A                     ; reg: 0x01e
        iorwf   ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        bz      bootloader_record_address_range_gate
        movff   ir_decoded_addr_b0_phys, TBLPTRH                  ; reg1: 0x01e, reg2: 0xff7
        movf    ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        rcall   bootloader_flash_set_low_addr_and_erase_row                                ; dest: 0x007a90

bootloader_record_address_range_gate:                                                  ; address: 0x007d22

        movff   ir_decoded_cmd_b0_phys, (Common_RAM + 11)        ; reg1: 0x01d, reg2: 0x00b
        movff   ir_decoded_addr_b0_phys, (Common_RAM + 12)        ; reg1: 0x01e, reg2: 0x00c
        movlw   0x77
        movwf   (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0xc0
        call    bootloader_addr_below_bound_w, 0x0                           ; dest: 0x00780a
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        movff   ir_decoded_cmd_b0_phys, (Common_RAM + 11)        ; reg1: 0x01d, reg2: 0x00b
        movff   ir_decoded_addr_b0_phys, (Common_RAM + 12)        ; reg1: 0x01e, reg2: 0x00c
        clrf    (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0x40
        call    bootloader_addr_at_or_above_bound_w, 0x0                           ; dest: 0x007804
        andwf   (Common_RAM + 28), F, A                     ; reg: 0x01c
        bz      bootloader_send_record_status
        clrf    control_flags_acc, A                        ; reg: 0x01f

bootloader_record_flash_write_loop:                                                  ; address: 0x007d4c

        movlw   0x08
        cpfslt  control_flags_acc, A                        ; reg: 0x01f
        bra     bootloader_send_record_status                                   ; dest: 0x007da4
        lfsr    0x0, stock_071_b0_phys
        lfsr    0x1, stock_043_b0_phys
        movf    control_flags_acc, W, A                     ; reg: 0x01f
        mullw   0x04
        movff   PRODL, (Common_RAM + 25)                    ; reg1: 0xff3, reg2: 0x019
        movff   PRODH, (Common_RAM + 26)                    ; reg1: 0xff4, reg2: 0x01a
        movlw   0x09
        addwf   (Common_RAM + 25), W, A                     ; reg: 0x019
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x04
        rcall   bootloader_copy_record_field_to_parse_buffer                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        lfsr    0x0, stock_071_b0_phys
        call    bootloader_parse_hex_from_fsr0, 0x0                           ; dest: 0x00784e
        movwf   (Common_RAM + 32), A                        ; reg: 0x020
        movff   (Common_RAM + 16), (Common_RAM + 33)        ; reg1: 0x010, reg2: 0x021
        movf    control_flags_acc, W, A                     ; reg: 0x01f
        mullw   0x02
        movff   PRODL, (Common_RAM + 25)                    ; reg1: 0xff3, reg2: 0x019
        movff   PRODH, (Common_RAM + 26)                    ; reg1: 0xff4, reg2: 0x01a
        movf    (Common_RAM + 25), W, A                     ; reg: 0x019
        addwf   ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        movf    (Common_RAM + 26), W, A                     ; reg: 0x01a
        addwfc  ir_decoded_addr_acc, W, A                     ; reg: 0x01e
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movf    (Common_RAM + 33), W, A                     ; reg: 0x021
        rcall   bootloader_flash_stage_byte_and_commit_row_w                                ; dest: 0x007a6e
        movf    (Common_RAM + 32), W, A                     ; reg: 0x020
        rcall   bootloader_flash_stage_byte_and_commit_row_w                                ; dest: 0x007a6e
        incf    control_flags_acc, F, A                     ; reg: 0x01f
        bnz     bootloader_record_flash_write_loop

bootloader_send_record_status:                                                  ; address: 0x007da4

        movlw   0x3a
        rcall   bootloader_uart_tx_byte_w                                ; dest: 0x007a2a
        movlw   0x04
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0x02
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        movf    (Common_RAM + 34), W, A                     ; reg: 0x022
        call    bootloader_emit_hex16_w, 0x0                           ; dest: 0x0078dc
        movlw   0x0d
        rcall   bootloader_uart_tx_byte_w                                ; dest: 0x007a2a
        movlw   0x0a
        rcall   bootloader_uart_tx_byte_w                                ; dest: 0x007a2a
        movf    ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        xorlw   0x40
        iorwf   ir_decoded_addr_acc, W, A                     ; reg: 0x01e
        bnz     bootloader_record_0050_cache_gate
        movlw   0x08
        movwf   control_flags_acc, A                        ; reg: 0x01f

bootloader_record_0040_cache_loop:                                                  ; address: 0x007dca

        movlw   0x10
        cpfslt  control_flags_acc, A                        ; reg: 0x01f
        bra     bootloader_record_0040_mark_update_pending                                   ; dest: 0x007e08
        lfsr    0x0, stock_071_b0_phys
        lfsr    0x1, stock_043_b0_phys
        movf    control_flags_acc, W, A                     ; reg: 0x01f
        mullw   0x02
        movff   PRODL, (Common_RAM + 25)                    ; reg1: 0xff3, reg2: 0x019
        movff   PRODH, (Common_RAM + 26)                    ; reg1: 0xff4, reg2: 0x01a
        movlw   0x09
        addwf   (Common_RAM + 25), W, A                     ; reg: 0x019
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x02
        rcall   bootloader_copy_record_field_to_parse_buffer                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        lfsr    0x0, stock_071_b0_phys
        call    bootloader_parse_hex_from_fsr0, 0x0                           ; dest: 0x00784e
        movwf   (Common_RAM + 8), A                         ; reg: 0x008
        lfsr    0x0, stock_024_b0_phys
        movf    control_flags_acc, W, A                     ; reg: 0x01f
        movff   (Common_RAM + 8), PLUSW0                    ; reg1: 0x008, reg2: 0xfeb
        incf    control_flags_acc, F, A                     ; reg: 0x01f
        bnz     bootloader_record_0040_cache_loop

bootloader_record_0040_mark_update_pending:                                                  ; address: 0x007e08

        setf    EEADR, A                                    ; reg: 0xfa9
        movlw   0x00
        rcall   bootloader_eeprom_write_byte_inc_addr_w                                ; dest: 0x007a54

bootloader_record_0050_cache_gate:                                                  ; address: 0x007e0e

        movf    ir_decoded_cmd_acc, W, A                     ; reg: 0x01d
        xorlw   0x50
        iorwf   ir_decoded_addr_acc, W, A                     ; reg: 0x01e
        bnz     bootloader_receive_next_record
        clrf    control_flags_acc, A                        ; reg: 0x01f

bootloader_record_0050_cache_loop:                                                  ; address: 0x007e18

        movlw   0x10                                        ; RC5 0x10 volume up
        cpfslt  control_flags_acc, A                        ; reg: 0x01f
        bra     bootloader_record_0050_rewrite_low_flash_header                                   ; dest: 0x007e5c
        lfsr    0x0, stock_071_b0_phys
        lfsr    0x1, stock_043_b0_phys
        movf    control_flags_acc, W, A                     ; reg: 0x01f
        mullw   0x02
        movff   PRODL, (Common_RAM + 25)                    ; reg1: 0xff3, reg2: 0x019
        movff   PRODH, (Common_RAM + 26)                    ; reg1: 0xff4, reg2: 0x01a
        movlw   0x09
        addwf   (Common_RAM + 25), W, A                     ; reg: 0x019
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x02
        rcall   bootloader_copy_record_field_to_parse_buffer                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        movlw   0x10
        addwf   control_flags_acc, W, A                     ; reg: 0x01f
        movwf   (Common_RAM + 8), A                         ; reg: 0x008
        lfsr    0x0, stock_071_b0_phys
        call    bootloader_parse_hex_from_fsr0, 0x0                           ; dest: 0x00784e
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, stock_024_b0_phys
        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        incf    control_flags_acc, F, A                     ; reg: 0x01f
        bnz     bootloader_record_0050_cache_loop

bootloader_record_0050_rewrite_low_flash_header:                                                  ; address: 0x007e5c

        rcall   bootloader_rewrite_low_flash_header                                ; dest: 0x007e94

bootloader_receive_next_record:                                                  ; address: 0x007e5e

        bra     bootloader_receive_record_reset                                   ; dest: 0x007bd6

bootloader_prompt_send:                                               ; address: 0x007e60

        movlw   0x0d
        call    bootloader_uart_tx_byte_w, 0x0                           ; dest: 0x007a2a
        movlw   0x0a
        call    bootloader_uart_tx_byte_w, 0x0                           ; dest: 0x007a2a
        movlw   0x0c
        call    bootloader_uart_tx_byte_w, 0x0                           ; dest: 0x007a2a
        movlw   0x3a
        call    bootloader_uart_tx_byte_w, 0x0                           ; dest: 0x007a2a
        movlw   0x04
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0x06
        movwf   (Common_RAM + 4), A                         ; reg: 0x004
        clrf    (Common_RAM + 16), A                        ; reg: 0x010
        movlw   0x7c
        call    bootloader_emit_bounded_string_from_ptr_w, 0x0                           ; dest: 0x007926
        movlw   0x0d
        call    bootloader_uart_tx_byte_w, 0x0                           ; dest: 0x007a2a
        movlw   0x0a
        goto    bootloader_uart_tx_byte_w                                ; dest: 0x007a2a

bootloader_rewrite_low_flash_header:                                               ; address: 0x007e94

        clrf    TBLPTRL, A                                  ; reg: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        rcall   bootloader_flash_erase_row_at_tblptr                                ; dest: 0x007a92
        clrf    TBLPTRL, A                                  ; reg: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        movlw   0x00
        call    bootloader_flash_stage_byte_and_commit_row_w, 0x0                           ; dest: 0x007a6e
        movlw   0xef
        call    bootloader_flash_stage_byte_and_commit_row_w, 0x0                           ; dest: 0x007a6e
        movlw   0x02
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        movlw   0x3c
        call    bootloader_flash_stage_byte_and_commit_row_w, 0x0                           ; dest: 0x007a6e
        movlw   0xf0
        call    bootloader_flash_stage_byte_and_commit_row_w, 0x0                           ; dest: 0x007a6e
        movlw   0x04
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        movlw   0xff
        call    bootloader_flash_stage_byte_and_commit_row_w, 0x0                           ; dest: 0x007a6e
        movlw   0xff
        call    bootloader_flash_stage_byte_and_commit_row_w, 0x0                           ; dest: 0x007a6e
        movlw   0x06
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        movlw   0xff
        call    bootloader_flash_stage_byte_and_commit_row_w, 0x0                           ; dest: 0x007a6e
        movlw   0xff
        call    bootloader_flash_stage_byte_and_commit_row_w, 0x0                           ; dest: 0x007a6e
        movlw   0x08
        movwf   control_flags_acc, A                        ; reg: 0x01f

bootloader_rewrite_low_flash_header__cached_byte_loop:                                                  ; address: 0x007ee4

        movlw   0x20
        cpfslt  control_flags_acc, A                        ; reg: 0x01f
        bra     bootloader_rewrite_low_flash_header__return                                   ; dest: 0x007f00
        movff   control_flags_b0_phys, TBLPTRL                  ; reg1: 0x01f, reg2: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        lfsr    0x0, stock_024_b0_phys
        movf    control_flags_acc, W, A                     ; reg: 0x01f
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    bootloader_flash_stage_byte_and_commit_row_w, 0x0                           ; dest: 0x007a6e
        incf    control_flags_acc, F, A                     ; reg: 0x01f
        bnz     bootloader_rewrite_low_flash_header__cached_byte_loop

bootloader_rewrite_low_flash_header__return:                                                  ; address: 0x007f00

        return  0x0


; ===========================================================================
; bootloader_manual_entry @ 0x007F02 — bootloader_manual_entry
; ---------------------------------------------------------------------------
; Manual firmware-update trigger: requires UP+DOWN held (with SELECT NOT
; pressed) for ~5.5 seconds at boot. Polls PORTC.bit0 (Up) and PORTA.bit2
; (Down) plus PORTA.bit1 (Select). On 11 successful 500 ms iterations
; (0x0B), enters the bootloader's HEX-receive loop instead of dropping
; into the application at 0x000040.
;
; Used by users to recover from a bricked main-image flash, or to
; intentionally force firmware update without the host triggering it via
; bootloader_prompt_send's bootloader_prompt path.
; ===========================================================================
; bootloader_manual_entry:
bootloader_manual_entry:                                               ; address: 0x007f02

        clrf    control_flags_acc, A                        ; reg: 0x01f

bootloader_manual_entry__poll_hold_buttons:                                                  ; address: 0x007f04

        movlw   0x0b
        cpfslt  control_flags_acc, A                        ; reg: 0x01f
        bra     bootloader_manual_entry__return                                   ; dest: 0x007f54
        movlw   0x01
        btfsc   PORTC, RC0, A                               ; reg: 0xf82, bit: 0
        clrf    WREG, A                                     ; reg: 0xfe8
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        movlw   0x01
        btfsc   PORTA, RA2, A                               ; reg: 0xf80, bit: 2
        clrf    WREG, A                                     ; reg: 0xfe8
        andwf   (Common_RAM + 28), F, A                     ; reg: 0x01c
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   PORTA, RA1, A                               ; reg: 0xf80, bit: 1
        movlw   0x01
        andwf   (Common_RAM + 28), F, A                     ; reg: 0x01c
        bz      bootloader_manual_entry__delay_next_sample
        movlw   0x01
        movwf   (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0xf4
        call    bootloader_delay_count16_w, 0x0                           ; dest: 0x007aa8
        movlw   0x01
        btfsc   PORTC, RC0, A                               ; reg: 0xf82, bit: 0
        clrf    WREG, A                                     ; reg: 0xfe8
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        movlw   0x01
        btfsc   PORTA, RA2, A                               ; reg: 0xf80, bit: 2
        clrf    WREG, A                                     ; reg: 0xfe8
        andwf   (Common_RAM + 28), F, A                     ; reg: 0x01c
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   PORTA, RA1, A                               ; reg: 0xf80, bit: 1
        movlw   0x01
        andwf   (Common_RAM + 28), F, A                     ; reg: 0x01c
        bz      bootloader_manual_entry__delay_next_sample
        bsf     stock_082_b0, 0x1, B                                ; reg: 0x082

bootloader_manual_entry__delay_next_sample:                                                  ; address: 0x007f4a

        movlw   0x0a
        call    bootloader_delay_count8_w, 0x0                           ; dest: 0x007aa6
        incf    control_flags_acc, F, A                     ; reg: 0x01f
        bnz     bootloader_manual_entry__poll_hold_buttons

bootloader_manual_entry__return:                                                  ; address: 0x007f54

        return  0x0

bootloader_finalize_update_and_reset:                                                  ; address: 0x007f56

        rcall   bootloader_rewrite_low_flash_header                                ; dest: 0x007e94
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bcf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        setf    EEADR, A                                    ; reg: 0xfa9
        movlw   0x01
        call    bootloader_eeprom_write_byte_inc_addr_w, 0x0                           ; dest: 0x007a54
        movlw   0x01
        movwf   (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0x2c
        call    bootloader_delay_count16_w, 0x0                           ; dest: 0x007aa8
        reset
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff
        dw      0xffff

;===============================================================================
; IDLOCS area

        ; idlocs

        org     0x200000

        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff

;===============================================================================
; CONFIG Bits area

        ; config

        org     0x300000

        db      0xff
        db      0x01
        db      0x1f
        db      0x00
        db      0xff
        db      0x00
        db      0x80
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff

;===============================================================================
; EEDATA area

        ; eeprom

        org     __EEPROM_START                              ; address: 0xf00000

        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x01
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0x00
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        ; V1.73 identity bytes at EEPROM 0x70..0x73.
        ; NOTE: EEPROM[0x73] is runtime-owned and must not be repurposed as a
        ; release counter. Canonical release revision lives in
        ; control_release_metadata at 0x77B0.
        db      0x01                                        ; EEPROM 0x70: major
        db      0x07                                        ; EEPROM 0x71: minor (V1.7 family)
        db      0x33                                        ; EEPROM 0x72: .3. (V1.73)
        db      0x01                                        ; EEPROM 0x73: stock-compatible runtime byte
        db      0xff                                        ; EEPROM 0x74: preset byte (erased = A default)
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0xff
        db      0x02

        end
