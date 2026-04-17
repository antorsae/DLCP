; ===========================================================================
; DLCP CONTROL V1.71 — feature-bearing source rewrite
; ===========================================================================
; Target MCU : Microchip PIC18F25K20 @ ~16 MHz (4 MIPS)
; Baseline   : Cloned from dlcp_control_v17_comments.asm (byte-identical to
;              stock V1.6b).  V1.71 inlines the features previously delivered
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
; Generated  : scripts/convert_v16b_asm_to_gpasm.py produces the V1.7
;              baseline; V1.71 edits land in-place in this file via
;              direct source modification.
;
; Verification: gpasm assembles without errors; vector block (0x0000–0x004B),
;              bootloader (0x7800–0x7FFF), and config bits are byte-identical
;              to stock V1.6b.  EEPROM matches stock except the V1.71 version
;              tuple at 0x71–0x73 and preset byte at 0x74.
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

flow_local_0020:                                                  ; address: 0x000020

        bra     flow_local_0020                                   ; dest: 0x000020
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

flow_local_0040:                                                  ; address: 0x000040

        goto    app_cold_init                                   ; dest: 0x000366
        dw      0xffff
        dw      0xffff
        goto    isr_entry                                   ; dest: 0x0003a6

app_entry_defensive_stub:                                               ; address: 0x00004c

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xfe
        call    lcd_command_or_eeprom_read, 0x0                           ; dest: 0x000190
        movlw   0x01
        call    lcd_command_or_eeprom_read, 0x0                           ; dest: 0x000190
        movlw   0x75
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x30
        goto    control_core_service_01D8                                ; dest: 0x0001d8


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
        bra     flow_delay_parameter_unit_00BA                                   ; dest: 0x0000ba


; ===========================================================================
; delay_parameter_unit @ 0x0000AA — delay_parameter_unit
; ---------------------------------------------------------------------------
; Inner delay primitive used by delay_short_loop / delay_short. Counts down
; the {0x10:0x11} pair through the {0x0C:0x0E:0x0F} scratch chain,
; calling control_core_service_016E (0x0001F0 — 16-bit divide helper) on each tick to
; advance the working pointer. Returns when the counter reaches zero.
; ===========================================================================
; delay_parameter_unit:
delay_parameter_unit:                                               ; address: 0x0000aa

        movwf   (Common_RAM + 14), A                        ; reg: 0x00e
        movf    (Common_RAM + 17), W, A                     ; reg: 0x011
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movf    (Common_RAM + 16), W, A                     ; reg: 0x010
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        call    control_core_service_01F0, 0x0                           ; dest: 0x0001f0
        movf    (Common_RAM + 12), W, A                     ; reg: 0x00c

flow_delay_parameter_unit_00BA:                                                  ; address: 0x0000ba

        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        dcfsnz  (Common_RAM + 6), F, A                      ; reg: 0x006
        bcf     Common_RAM, 0x3, A                          ; reg: 0x000
        movf    (Common_RAM + 7), W, A                      ; reg: 0x007
        bz      flow_delay_parameter_unit_00CA
        subwf   (Common_RAM + 6), W, A                      ; reg: 0x006
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        bra     flow_delay_parameter_unit_00DA                                   ; dest: 0x0000da

flow_delay_parameter_unit_00CA:                                                  ; address: 0x0000ca

        movf    (Common_RAM + 12), W, A                     ; reg: 0x00c
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bcf     Common_RAM, 0x3, A                          ; reg: 0x000
        btfsc   Common_RAM, 0x3, A                          ; reg: 0x000
        bra     flow_delay_parameter_unit_00DA                                   ; dest: 0x0000da
        addlw   0x30
        goto    lcd_command_or_eeprom_read                                ; dest: 0x000190

flow_delay_parameter_unit_00DA:                                                  ; address: 0x0000da

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

flow_lcd_string_write_rom_00E0:                                                  ; address: 0x0000e0

        tblrd*+
        movf    TABLAT, W, A                                ; reg: 0xff5
        bz      flow_lcd_string_write_rom_00EA
        rcall   lcd_char_write                                ; dest: 0x0000ec
        bra     flow_lcd_string_write_rom_00E0                                   ; dest: 0x0000e0

flow_lcd_string_write_rom_00EA:                                                  ; address: 0x0000ea

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
        goto    flow_ccs_0144_0146                                   ; dest: 0x000146
        movlw   0x3a
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x98
        call    control_core_service_01D8, 0x0                           ; dest: 0x0001d8
        movlw   0x33
        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        rcall   control_core_service_016E                                ; dest: 0x00016e
        movlw   0x13
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x88
        call    control_core_service_01D8, 0x0                           ; dest: 0x0001d8
        rcall   control_core_service_016E                                ; dest: 0x00016e
        movlw   0x64
        call    control_core_service_01D6, 0x0                           ; dest: 0x0001d6
        rcall   control_core_service_016E                                ; dest: 0x00016e
        movlw   0x64
        call    control_core_service_01D6, 0x0                           ; dest: 0x0001d6
        movlw   0x22
        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        rcall   control_core_service_016E                                ; dest: 0x00016e
        movlw   0x28
        rcall   control_core_service_0144                                ; dest: 0x000144
        movlw   0x0c
        rcall   control_core_service_0144                                ; dest: 0x000144
        movlw   0x06
        rcall   control_core_service_0144                                ; dest: 0x000144
        bsf     Common_RAM, 0x1, A                          ; reg: 0x000
        movf    (Common_RAM + 21), W, A                     ; reg: 0x015
        bra     flow_ccs_0144_0146                                   ; dest: 0x000146

control_core_service_0144:                                               ; address: 0x000144

        bsf     Common_RAM, 0x0, A                          ; reg: 0x000

flow_ccs_0144_0146:                                                  ; address: 0x000146

        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        btfss   Common_RAM, 0x0, A                          ; reg: 0x000
        bra     flow_ccs_0144_0162                                   ; dest: 0x000162
        bcf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        sublw   0x03
        bnc     control_core_service_016A
        rcall   control_core_service_016A                                ; dest: 0x00016a
        movlw   0x07
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0xd0
        call    control_core_service_01D8, 0x0                           ; dest: 0x0001d8
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

flow_ccs_0144_0162:                                                  ; address: 0x000162

        bsf     Common_RAM, 0x0, A                          ; reg: 0x000
        sublw   0xfe
        bz      flow_ccs_016E_018C
        bsf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5

control_core_service_016A:                                               ; address: 0x00016a

        swapf   (Common_RAM + 20), F, A                     ; reg: 0x014
        btfss   Common_RAM, 0x0, A                          ; reg: 0x000

control_core_service_016E:                                               ; address: 0x00016e

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
        bra     control_core_service_016E                                ; dest: 0x00016e
        movlw   0x32
        call    control_core_service_01D6, 0x0                           ; dest: 0x0001d6
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0

flow_ccs_016E_018C:                                                  ; address: 0x00018c

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

flow_eeprom_write_byte_01B2:                                                  ; address: 0x0001b2

        btfsc   EECON1, WR, A                               ; reg: 0xfa6, bit: 1
        bra     flow_eeprom_write_byte_01B2                                   ; dest: 0x0001b2
        bcf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        incf    EEADR, F, A                                 ; reg: 0xfa9
        return  0x0


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

control_core_service_01BE:                                               ; address: 0x0001be

        movwf   (Common_RAM + 14), A                        ; reg: 0x00e

flow_ccs_01BE_01C0:                                                  ; address: 0x0001c0

        movlw   0xff
        addwf   (Common_RAM + 14), F, A                     ; reg: 0x00e
        addwfc  (Common_RAM + 15), F, A                     ; reg: 0x00f
        bra     flow_ccs_01BE_01C8                                   ; dest: 0x0001c8

flow_ccs_01BE_01C8:                                                  ; address: 0x0001c8

        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        movlw   0x03
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0xe5
        rcall   control_core_service_01D8                                ; dest: 0x0001d8
        bra     flow_ccs_01BE_01C0                                   ; dest: 0x0001c0

control_core_service_01D6:                                               ; address: 0x0001d6

        clrf    (Common_RAM + 13), A                        ; reg: 0x00d

control_core_service_01D8:                                               ; address: 0x0001d8

        addlw   0xfa
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        nop
        bnc     flow_ccs_01D8_01E6
        bra     flow_ccs_01D8_01E2                                   ; dest: 0x0001e2

flow_ccs_01D8_01E2:                                                  ; address: 0x0001e2

        decf    (Common_RAM + 12), F, A                     ; reg: 0x00c
        bc      flow_ccs_01D8_01E2

flow_ccs_01D8_01E6:                                                  ; address: 0x0001e6

        decf    (Common_RAM + 12), F, A                     ; reg: 0x00c
        decf    (Common_RAM + 13), F, A                     ; reg: 0x00d
        bc      flow_ccs_01D8_01E2
        nop
        return  0x0

control_core_service_01F0:                                               ; address: 0x0001f0

        clrf    (Common_RAM + 17), A                        ; reg: 0x011
        clrf    (Common_RAM + 16), A                        ; reg: 0x010
        movlw   0x10
        movwf   PRODL, A                                    ; reg: 0xff3

flow_ccs_01F0_01F8:                                                  ; address: 0x0001f8

        rlcf    (Common_RAM + 13), W, A                     ; reg: 0x00d
        rlcf    (Common_RAM + 16), F, A                     ; reg: 0x010
        rlcf    (Common_RAM + 17), F, A                     ; reg: 0x011
        movf    (Common_RAM + 14), W, A                     ; reg: 0x00e
        subwf   (Common_RAM + 16), W, A                     ; reg: 0x010
        movf    (Common_RAM + 15), W, A                     ; reg: 0x00f
        subwfb  (Common_RAM + 17), W, A                     ; reg: 0x011
        bnc     flow_ccs_01F0_0212
        movf    (Common_RAM + 14), W, A                     ; reg: 0x00e
        subwf   (Common_RAM + 16), F, A                     ; reg: 0x010
        movf    (Common_RAM + 15), W, A                     ; reg: 0x00f
        subwfb  (Common_RAM + 17), F, A                     ; reg: 0x011
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0

flow_ccs_01F0_0212:                                                  ; address: 0x000212

        rlcf    (Common_RAM + 12), F, A                     ; reg: 0x00c
        rlcf    (Common_RAM + 13), F, A                     ; reg: 0x00d
        decfsz  PRODL, F, A                                 ; reg: 0xff3
        bra     flow_ccs_01F0_01F8                                   ; dest: 0x0001f8
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
; The OERR latch exposes BUG C4 in rx_parser_entry because the parser only
; toggles CREN to clear OERR — it does NOT drain RCREG. Stale bytes in
; the hardware FIFO then re-trigger the parser with phase-shifted data,
; which is what produces the V162B "intermittent unresponsive" pattern.
; ===========================================================================
; ir_rc5_decode:
ir_rc5_decode:                                               ; address: 0x00021e

        bsf     TRISB, RB5, A                               ; reg: 0xf93, bit: 5
        clrf    (Common_RAM + 21), A                        ; reg: 0x015
        clrf    (Common_RAM + 20), A                        ; reg: 0x014
        lfsr    0x0, 0x010
        movlw   0x01
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0xba
        call    control_core_service_01D8, 0x0                           ; dest: 0x0001d8
        btfsc   PORTB, RB5, A                               ; reg: 0xf81, bit: 5
        bra     flow_ir_rc5_decode_02E4                                   ; dest: 0x0002e4

flow_ir_rc5_decode_0236:                                                  ; address: 0x000236

        movlw   0x03
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x76
        call    control_core_service_01D8, 0x0                           ; dest: 0x0001d8
        incf    (Common_RAM + 21), F, A                     ; reg: 0x015
        movlw   0x20                                        ; RC5 0x20 preset next
        cpfsgt  (Common_RAM + 21), A                        ; reg: 0x015
        bra     flow_ir_rc5_decode_024A                                   ; dest: 0x00024a
        bra     flow_ir_rc5_decode_025E                                   ; dest: 0x00025e

flow_ir_rc5_decode_024A:                                                  ; address: 0x00024a

        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        btfsc   PORTB, RB5, A                               ; reg: 0xf81, bit: 5
        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        incf    (Common_RAM + 20), F, A                     ; reg: 0x014
        btfss   (Common_RAM + 20), 0x3, A                   ; reg: 0x014
        bra     flow_ir_rc5_decode_025C                                   ; dest: 0x00025c
        movf    POSTINC0, F, A                              ; reg: 0xfee
        clrf    (Common_RAM + 20), A                        ; reg: 0x014

flow_ir_rc5_decode_025C:                                                  ; address: 0x00025c

        bra     flow_ir_rc5_decode_0236                                   ; dest: 0x000236

flow_ir_rc5_decode_025E:                                                  ; address: 0x00025e

        lfsr    0x0, 0x010
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
        rcall   control_core_service_02EE                                ; dest: 0x0002ee
        btfsc   (Common_RAM + 9), 0x2, A                    ; reg: 0x009
        bra     flow_ir_rc5_decode_02E4                                   ; dest: 0x0002e4
        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        incf    (Common_RAM + 20), F, A                     ; reg: 0x014
        rcall   control_core_service_02EE                                ; dest: 0x0002ee
        btfsc   (Common_RAM + 9), 0x2, A                    ; reg: 0x009
        bra     flow_ir_rc5_decode_02E4                                   ; dest: 0x0002e4
        rrcf    (Common_RAM + 9), F, A                      ; reg: 0x009
        rlcf    (Common_RAM + 14), F, A                     ; reg: 0x00e
        movlw   0x05
        movwf   (Common_RAM + 8), A                         ; reg: 0x008

flow_ir_rc5_decode_0296:                                                  ; address: 0x000296

        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        incf    (Common_RAM + 20), F, A                     ; reg: 0x014
        btfss   (Common_RAM + 20), 0x2, A                   ; reg: 0x014
        bra     flow_ir_rc5_decode_02AA                                   ; dest: 0x0002aa
        movf    POSTINC0, F, A                              ; reg: 0xfee
        clrf    (Common_RAM + 20), A                        ; reg: 0x014

flow_ir_rc5_decode_02AA:                                                  ; address: 0x0002aa

        rcall   control_core_service_02EE                                ; dest: 0x0002ee
        btfsc   (Common_RAM + 9), 0x2, A                    ; reg: 0x009
        bra     flow_ir_rc5_decode_02E4                                   ; dest: 0x0002e4
        rrcf    (Common_RAM + 9), F, A                      ; reg: 0x009
        rlcf    (Common_RAM + 13), F, A                     ; reg: 0x00d
        decfsz  (Common_RAM + 8), F, A                      ; reg: 0x008
        bra     flow_ir_rc5_decode_0296                                   ; dest: 0x000296
        movlw   0x06
        movwf   (Common_RAM + 8), A                         ; reg: 0x008

flow_ir_rc5_decode_02BC:                                                  ; address: 0x0002bc

        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        rlcf    INDF0, F, A                                 ; reg: 0xfef
        rlcf    (Common_RAM + 5), F, A                      ; reg: 0x005
        incf    (Common_RAM + 20), F, A                     ; reg: 0x014
        btfss   (Common_RAM + 20), 0x2, A                   ; reg: 0x014
        bra     flow_ir_rc5_decode_02D0                                   ; dest: 0x0002d0
        movf    POSTINC0, F, A                              ; reg: 0xfee
        clrf    (Common_RAM + 20), A                        ; reg: 0x014

flow_ir_rc5_decode_02D0:                                                  ; address: 0x0002d0

        rcall   control_core_service_02EE                                ; dest: 0x0002ee
        btfsc   (Common_RAM + 9), 0x2, A                    ; reg: 0x009
        bra     flow_ir_rc5_decode_02E4                                   ; dest: 0x0002e4
        rrcf    (Common_RAM + 9), F, A                      ; reg: 0x009
        rlcf    (Common_RAM + 12), F, A                     ; reg: 0x00c
        decfsz  (Common_RAM + 8), F, A                      ; reg: 0x008
        bra     flow_ir_rc5_decode_02BC                                   ; dest: 0x0002bc
        movf    (Common_RAM + 12), W, A                     ; reg: 0x00c
        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

flow_ir_rc5_decode_02E4:                                                  ; address: 0x0002e4

        movlw   0xff
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

control_core_service_02EE:                                               ; address: 0x0002ee

        clrf    (Common_RAM + 9), A                         ; reg: 0x009
        decfsz  (Common_RAM + 5), W, A                      ; reg: 0x005
        bra     flow_ccs_02EE_02F8                                   ; dest: 0x0002f8
        bsf     (Common_RAM + 9), 0x0, A                    ; reg: 0x009
        return  0x0

flow_ccs_02EE_02F8:                                                  ; address: 0x0002f8

        movlw   0x02
        cpfseq  (Common_RAM + 5), A                         ; reg: 0x005
        bra     flow_ccs_02EE_0300                                   ; dest: 0x000300
        return  0x0

flow_ccs_02EE_0300:                                                  ; address: 0x000300

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
        movwf   0x66, B                                     ; reg: 0x066
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
        movwf   0x66, B                                     ; reg: 0x066
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
        goto    flow_ccs_0FA0_103C                                   ; dest: 0x00103c

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
        goto    flow_app_cold_init_03F6                                   ; dest: 0x0003f6
        movf    0x96, W, B                                  ; reg: 0x096
        cpfseq  0x97, B                                     ; reg: 0x097
        goto    flow_app_cold_init_03DE                                   ; dest: 0x0003de
        bcf     PIE1, TXIE, A                               ; reg: 0xf9d, bit: 4
        goto    flow_app_cold_init_03F6                                   ; dest: 0x0003f6

flow_app_cold_init_03DE:                                                  ; address: 0x0003de

        lfsr    0x0, 0x036
        movf    0x96, W, B                                  ; reg: 0x096
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   TXREG, A                                    ; reg: 0xfad
        incf    0x96, F, B                                  ; reg: 0x096
        movlw   0x30
        subwf   0x96, W, B                                  ; reg: 0x096
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_app_cold_init_03F6                                   ; dest: 0x0003f6
        clrf    0x96, B                                     ; reg: 0x096

flow_app_cold_init_03F6:                                                  ; address: 0x0003f6

        btfss   PIR1, RCIF, A                               ; reg: 0xf9e, bit: 5
        goto    flow_app_cold_init_0414                                   ; dest: 0x000414
        lfsr    0x0, 0x066
        movf    0x99, W, B                                  ; reg: 0x099
        movff   RCREG, PLUSW0                               ; reg1: 0xfae, reg2: 0xfeb
        incf    0x99, F, B                                  ; reg: 0x099
        movlw   0x30
        subwf   0x99, W, B                                  ; reg: 0x099
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_app_cold_init_0414                                   ; dest: 0x000414
        clrf    0x99, B                                     ; reg: 0x099

flow_app_cold_init_0414:                                                  ; address: 0x000414

        btfss   INTCON, RBIF, A                             ; reg: 0xff2, bit: 0
        goto    flow_app_cold_init_0436                                   ; dest: 0x000436
        movf    (Common_RAM + 28), W, A                     ; reg: 0x01c
        iorwf   (Common_RAM + 27), W, A                     ; reg: 0x01b
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_app_cold_init_0434                                   ; dest: 0x000434
        btfss   control_flags, 0x0, A                   ; reg: 0x01f
        goto    flow_app_cold_init_0434                                   ; dest: 0x000434
        rcall   ir_rc5_decode                                ; dest: 0x00021e
        movwf   ir_decoded_cmd, A                        ; reg: 0x01d
        movff   (Common_RAM + 13), ir_decoded_addr        ; reg1: 0x00d, reg2: 0x01e
        bcf     control_flags, 0x0, A                   ; reg: 0x01f

flow_app_cold_init_0434:                                                  ; address: 0x000434

        bcf     INTCON, RBIF, A                             ; reg: 0xff2, bit: 0

flow_app_cold_init_0436:                                                  ; address: 0x000436

        movff   (Common_RAM + 3), FSR0L                     ; reg1: 0x003, reg2: 0xfe9
        movff   (Common_RAM + 4), FSR0H                     ; reg1: 0x004, reg2: 0xfea
        movff   (Common_RAM + 2), BSR                       ; reg1: 0x002, reg2: 0xfe0
        movf    (Common_RAM + 26), W, A                     ; reg: 0x01a
        movff   (Common_RAM + 25), STATUS                   ; reg1: 0x019, reg2: 0xfd8
        retfie  0x0


; ===========================================================================
; rx_parser_entry @ 0x00044A — rx_parser_entry  *** BUG C4 / C5 ***
; ---------------------------------------------------------------------------
; Top of the receive-path service routine. Called every iteration of the
; main event loop (main_event_loop) to drain the RX ring, decode 3-byte
; [route, cmd, data] frames, and update internal state.
;
; *** BUG C4 (oerr_no_fifo_drain) ***
; First check: btfss RCSTA.OERR (0xAB.1). If set, toggle CREN to clear,
; then NOP, then re-arm CREN. This clears the OERR latch but DOES NOT
; READ RCREG TWICE to drain the 2-deep hardware FIFO. Stale bytes left
; in RCREG re-trigger the parser at the wrong frame phase, corrupting
; subsequent frames until the parser happens to resync on a 0xB0/0xB1/
; 0xBF route byte. The V1.62b fix (`control_uart_soft_recover` at 0x7000+)
; addresses this with a 2x movf RCREG drain.
;
; *** BUG C5 (no_frame_resync_timeout) ***
; The parser tracks position in 0x0A6 (rx_frame_position). If a partial
; frame is received and the source dies, 0x0A6 stays mid-frame forever
; — the next byte received (potentially several seconds later) is
; misinterpreted. There is no per-frame timeout that resets 0x0A6 to 0.
; ===========================================================================
; rx_parser_entry:
rx_parser_entry:                                               ; address: 0x00044a

        btfss   RCSTA, OERR, A                              ; reg: 0xfab, bit: 1
        goto    flow_rx_parser_entry_0456                                   ; dest: 0x000456
        bcf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        nop
        bsf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4

flow_rx_parser_entry_0456:                                                  ; address: 0x000456

        movf    0x99, W, B                                  ; reg: 0x099
        cpfseq  0x98, B                                     ; reg: 0x098
        goto    flow_rx_parser_entry_0460                                   ; dest: 0x000460
        return  0x0

flow_rx_parser_entry_0460:                                                  ; address: 0x000460

        lfsr    0x0, 0x066
        movf    0x98, W, B                                  ; reg: 0x098
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   0xb6, B                                     ; reg: 0x0b6
        incf    0x98, F, B                                  ; reg: 0x098
        movlw   0x30
        subwf   0x98, W, B                                  ; reg: 0x098
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_rx_parser_entry_0478                                   ; dest: 0x000478
        clrf    0x98, B                                     ; reg: 0x098

flow_rx_parser_entry_0478:                                                  ; address: 0x000478

        movlw   0xfe
        cpfseq  0xb6, B                                     ; reg: 0x0b6
        goto    flow_rx_parser_entry_048A                                   ; dest: 0x00048a
        movff   0x0b6, tx_data_staging                    ; reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        bra     rx_parser_entry                                ; dest: 0x00044a

flow_rx_parser_entry_048A:                                                  ; address: 0x00048a

        movlw   0x80
        subwf   0xb6, W, B                                  ; reg: 0x0b6
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_rx_parser_entry_04D6                                   ; dest: 0x0004d6
        movlw   0xf1
        andwf   0xb6, W, B                                  ; reg: 0x0b6
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        clrf    (Common_RAM + 11), A                        ; reg: 0x00b
        movf    (Common_RAM + 10), W, A                     ; reg: 0x00a
        xorlw   0xb1                                        ; ROUTE addressed MAIN#1
        iorwf   (Common_RAM + 11), W, A                     ; reg: 0x00b
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_rx_parser_entry_04AC                                   ; dest: 0x0004ac
        movlw   0xb1                                        ; ROUTE addressed MAIN#1
        movwf   0xb6, B                                     ; reg: 0x0b6

flow_rx_parser_entry_04AC:                                                  ; address: 0x0004ac

        movlw   0xb0                                        ; ROUTE broadcast CONTROL→MAIN
        cpfseq  0xb6, B                                     ; reg: 0x0b6
        goto    flow_rx_parser_entry_04BE                                   ; dest: 0x0004be
        movlw   0x01
        movwf   0xa6, B                                     ; reg: 0x0a6
        bsf     control_flags, 0x2, A                   ; reg: 0x01f
        goto    flow_rx_parser_entry_04D4                                   ; dest: 0x0004d4

flow_rx_parser_entry_04BE:                                                  ; address: 0x0004be

        movlw   0xb1                                        ; ROUTE addressed MAIN#1
        cpfseq  0xb6, B                                     ; reg: 0x0b6
        goto    flow_rx_parser_entry_04D0                                   ; dest: 0x0004d0
        movlw   0x01
        movwf   0xa6, B                                     ; reg: 0x0a6
        bsf     control_flags, 0x2, A                   ; reg: 0x01f
        goto    flow_rx_parser_entry_04D4                                   ; dest: 0x0004d4

flow_rx_parser_entry_04D0:                                                  ; address: 0x0004d0

        clrf    0xa6, B                                     ; reg: 0x0a6
        bsf     control_flags, 0x2, A                   ; reg: 0x01f

flow_rx_parser_entry_04D4:                                                  ; address: 0x0004d4

        bra     rx_parser_entry                                ; dest: 0x00044a

flow_rx_parser_entry_04D6:                                                  ; address: 0x0004d6

        movf    0xa6, F, B                                  ; reg: 0x0a6
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_rx_parser_entry_04E0                                   ; dest: 0x0004e0
        incf    0xa6, F, B                                  ; reg: 0x0a6

flow_rx_parser_entry_04E0:                                                  ; address: 0x0004e0

        movlw   0x02
        cpfslt  0xa6, B                                     ; reg: 0x0a6
        goto    flow_rx_parser_entry_04EA                                   ; dest: 0x0004ea
        bra     rx_parser_entry                                ; dest: 0x00044a

flow_rx_parser_entry_04EA:                                                  ; address: 0x0004ea

        movlw   0x02
        cpfseq  0xa6, B                                     ; reg: 0x0a6
        goto    flow_rx_parser_entry_04F8                                   ; dest: 0x0004f8
        movff   0x0b6, rx_parsed_cmd                    ; reg2: 0x02f
        bra     rx_parser_entry                                ; dest: 0x00044a

flow_rx_parser_entry_04F8:                                                  ; address: 0x0004f8

        movff   0x0b6, rx_parsed_data                    ; reg2: 0x030
        movlw   0x01
        movwf   0xa6, B                                     ; reg: 0x0a6
        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        cpfseq  rx_parsed_cmd, A                        ; reg: 0x02f
        goto    flow_rx_parser_entry_0556                                   ; dest: 0x000556
        decfsz  rx_parsed_data, W, A                     ; reg: 0x030
        goto    flow_rx_parser_entry_0514                                   ; dest: 0x000514
        bsf     control_flags, 0x1, A                   ; reg: 0x01f
        goto    flow_rx_parser_entry_0552                                   ; dest: 0x000552

flow_rx_parser_entry_0514:                                                  ; address: 0x000514

        movf    rx_parsed_data, F, A                     ; reg: 0x030
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_rx_parser_entry_0522                                   ; dest: 0x000522
        bcf     control_flags, 0x1, A                   ; reg: 0x01f
        goto    flow_rx_parser_entry_0552                                   ; dest: 0x000552

flow_rx_parser_entry_0522:                                                  ; address: 0x000522

        movlw   0x02
        cpfseq  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_rx_parser_entry_0540                                   ; dest: 0x000540
        btfsc   control_flags, 0x5, A                   ; reg: 0x01f
        goto    flow_rx_parser_entry_053C                                   ; dest: 0x00053c
        movlw   0x2f
        movwf   0xb4, B                                     ; reg: 0x0b4
        movlw   0x75
        movwf   0xb5, B                                     ; reg: 0x0b5
        bsf     control_flags, 0x5, A                   ; reg: 0x01f
        bsf     control_flags, 0x3, A                   ; reg: 0x01f

flow_rx_parser_entry_053C:                                                  ; address: 0x00053c

        goto    flow_rx_parser_entry_0552                                   ; dest: 0x000552

flow_rx_parser_entry_0540:                                                  ; address: 0x000540

        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        cpfseq  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_rx_parser_entry_0552                                   ; dest: 0x000552
        btfss   control_flags, 0x5, A                   ; reg: 0x01f
        goto    flow_rx_parser_entry_0552                                   ; dest: 0x000552
        bcf     control_flags, 0x5, A                   ; reg: 0x01f
        bsf     control_flags, 0x3, A                   ; reg: 0x01f

flow_rx_parser_entry_0552:                                                  ; address: 0x000552

        goto    flow_rx_parser_entry_05EA                                   ; dest: 0x0005ea

flow_rx_parser_entry_0556:                                                  ; address: 0x000556

        movlw   0x04                                        ; CMD status_poll
        cpfseq  rx_parsed_cmd, A                        ; reg: 0x02f
        goto    flow_rx_parser_entry_0562                                   ; dest: 0x000562
        goto    flow_rx_parser_entry_05EA                                   ; dest: 0x0005ea

flow_rx_parser_entry_0562:                                                  ; address: 0x000562

        movlw   0x05                                        ; CMD raw_status (MAIN→CONTROL echo)
        cpfseq  rx_parsed_cmd, A                        ; reg: 0x02f
        goto    flow_rx_parser_entry_057A                                   ; dest: 0x00057a
        movlw   0x04                                        ; CMD status_poll
        cpfslt  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_rx_parser_entry_0576                                   ; dest: 0x000576
        movff   rx_parsed_data, 0x0a1                    ; reg1: 0x030

flow_rx_parser_entry_0576:                                                  ; address: 0x000576

        goto    flow_rx_parser_entry_05EA                                   ; dest: 0x0005ea

flow_rx_parser_entry_057A:                                                  ; address: 0x00057a

        movlw   0x06                                        ; CMD input_select
        cpfseq  rx_parsed_cmd, A                        ; reg: 0x02f
        goto    flow_rx_parser_entry_05AC                                   ; dest: 0x0005ac
        movlw   0x01
        subwf   (Common_RAM + 50), W, A                     ; reg: 0x032
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_rx_parser_entry_05A8                                   ; dest: 0x0005a8
        movlw   0x09
        cpfslt  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_rx_parser_entry_05A8                                   ; dest: 0x0005a8
        movf    0xb8, W, B                                  ; reg: 0x0b8
        subwf   rx_parsed_data, W, A                     ; reg: 0x030
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_rx_parser_entry_05A8                                   ; dest: 0x0005a8
        movff   rx_parsed_data, 0x0b8                    ; reg1: 0x030
        bsf     control_flags, 0x3, A                   ; reg: 0x01f
        call    control_core_service_061C, 0x0                           ; dest: 0x00061c

flow_rx_parser_entry_05A8:                                                  ; address: 0x0005a8

        goto    flow_rx_parser_entry_05EA                                   ; dest: 0x0005ea

flow_rx_parser_entry_05AC:                                                  ; address: 0x0005ac

        movlw   0x07                                        ; CMD volume (offset 0x60)
        cpfseq  rx_parsed_cmd, A                        ; reg: 0x02f
        goto    flow_rx_parser_entry_05D0                                   ; dest: 0x0005d0
        movlw   0x73
        cpfslt  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_rx_parser_entry_05CC                                   ; dest: 0x0005cc
        movf    0xb9, W, B                                  ; reg: 0x0b9
        subwf   rx_parsed_data, W, A                     ; reg: 0x030
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_rx_parser_entry_05C8                                   ; dest: 0x0005c8
        bsf     control_flags, 0x3, A                   ; reg: 0x01f

flow_rx_parser_entry_05C8:                                                  ; address: 0x0005c8

        movff   rx_parsed_data, 0x0b9                    ; reg1: 0x030

flow_rx_parser_entry_05CC:                                                  ; address: 0x0005cc

        goto    flow_rx_parser_entry_05EA                                   ; dest: 0x0005ea

flow_rx_parser_entry_05D0:                                                  ; address: 0x0005d0

        movlw   0x1d                                        ; CMD shared_cmd1d_setting (BL timeout / profile)
        cpfseq  rx_parsed_cmd, A                        ; reg: 0x02f
        goto    flow_rx_parser_entry_05EA                                   ; dest: 0x0005ea
        movf    0xa7, W, B                                  ; reg: 0x0a7
        subwf   rx_parsed_data, W, A                     ; reg: 0x030
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_rx_parser_entry_05EA                                   ; dest: 0x0005ea
        movff   rx_parsed_data, 0x0a7                    ; reg1: 0x030
        call    control_core_service_0F54, 0x0                           ; dest: 0x000f54

flow_rx_parser_entry_05EA:                                                  ; address: 0x0005ea

        bra     rx_parser_entry                                ; dest: 0x00044a


; ===========================================================================
; tx_byte_enqueue @ 0x0005EC — tx_byte_enqueue   (V1.6b @ 0x00060C in agent map)
; ---------------------------------------------------------------------------
; Enqueues 0x027 (tx_data_staging) into the 48-byte TX ring at 0x036+. The
; ring is read by the ISR via PIE1.TXIE (kicked at the bottom of this
; routine after committing the new tx_ring_wr).  Producer-side index is
; 0x097, consumer-side is 0x096.  Wrapping at 0x30 (= 48 bytes).
;
; If the ring is FULL when the producer arrives, the routine drops into
; the busy-wait at 0x00060C (flow_ccs_061C_062A, BUG C6) — see annotation there.
; ===========================================================================
; tx_byte_enqueue:
tx_byte_enqueue:                                               ; address: 0x0005ec

        lfsr    0x0, 0x036
        movf    0x97, W, B                                  ; reg: 0x097
        movff   tx_data_staging, PLUSW0                   ; reg1: 0x027, reg2: 0xfeb
        incf    0x97, W, B                                  ; reg: 0x097
        movwf   tx_data_staging, A                        ; reg: 0x027
        movlw   0x30
        subwf   tx_data_staging, W, A                     ; reg: 0x027
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_tx_byte_enqueue_0606                                   ; dest: 0x000606
        clrf    tx_data_staging, A                        ; reg: 0x027

flow_tx_byte_enqueue_0606:                                                  ; address: 0x000606

        btfss   PIE1, TXIE, A                               ; reg: 0xf9d, bit: 4
        goto    flow_tx_byte_enqueue_0614                                   ; dest: 0x000614

flow_tx_byte_enqueue_060C:                                                  ; address: 0x00060c

        movf    tx_data_staging, W, A                     ; reg: 0x027
        subwf   0x96, W, B                                  ; reg: 0x096
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_tx_byte_enqueue_060C                                   ; dest: 0x00060c

flow_tx_byte_enqueue_0614:                                                  ; address: 0x000614

        movff   tx_data_staging, 0x097                    ; reg1: 0x027
        bsf     PIE1, TXIE, A                               ; reg: 0xf9d, bit: 4
        return  0x0

control_core_service_061C:                                               ; address: 0x00061c

        movf    rx_parsed_data, F, A                     ; reg: 0x030
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_061C_062A                                   ; dest: 0x00062a
        clrf    0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_061C_0768                                   ; dest: 0x000768

flow_ccs_061C_062A:                                                  ; address: 0x00062a

        decfsz  rx_parsed_data, W, A                     ; reg: 0x030
        goto    flow_ccs_061C_0638                                   ; dest: 0x000638
        movlw   0x05
        movwf   0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_061C_0768                                   ; dest: 0x000768

flow_ccs_061C_0638:                                                  ; address: 0x000638

        movlw   0x02
        cpfseq  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_ccs_061C_0658                                   ; dest: 0x000658
        movf    0xa1, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_061C_0650                                   ; dest: 0x000650
        movlw   0x06
        movwf   0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_061C_0654                                   ; dest: 0x000654

flow_ccs_061C_0650:                                                  ; address: 0x000650

        movlw   0x01
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_0654:                                                  ; address: 0x000654

        goto    flow_ccs_061C_0768                                   ; dest: 0x000768

flow_ccs_061C_0658:                                                  ; address: 0x000658

        movlw   0x03
        cpfseq  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_ccs_061C_0686                                   ; dest: 0x000686
        movf    0xa1, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_061C_067E                                   ; dest: 0x00067e
        decfsz  0xa1, W, B                                  ; reg: 0x0a1
        goto    flow_ccs_061C_0676                                   ; dest: 0x000676
        movlw   0x01
        movwf   0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_061C_067A                                   ; dest: 0x00067a

flow_ccs_061C_0676:                                                  ; address: 0x000676

        movlw   0x07
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_067A:                                                  ; address: 0x00067a

        goto    flow_ccs_061C_0682                                   ; dest: 0x000682

flow_ccs_061C_067E:                                                  ; address: 0x00067e

        movlw   0x02
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_0682:                                                  ; address: 0x000682

        goto    flow_ccs_061C_0768                                   ; dest: 0x000768

flow_ccs_061C_0686:                                                  ; address: 0x000686

        movlw   0x04
        cpfseq  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_ccs_061C_06C4                                   ; dest: 0x0006c4
        movf    0xa1, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_061C_06BC                                   ; dest: 0x0006bc
        decfsz  0xa1, W, B                                  ; reg: 0x0a1
        goto    flow_ccs_061C_06A0                                   ; dest: 0x0006a0
        movlw   0x02
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_06A0:                                                  ; address: 0x0006a0

        movlw   0x02
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_061C_06AC                                   ; dest: 0x0006ac
        movlw   0x01
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_06AC:                                                  ; address: 0x0006ac

        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_061C_06B8                                   ; dest: 0x0006b8
        movlw   0x08
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_06B8:                                                  ; address: 0x0006b8

        goto    flow_ccs_061C_06C0                                   ; dest: 0x0006c0

flow_ccs_061C_06BC:                                                  ; address: 0x0006bc

        movlw   0x03
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_06C0:                                                  ; address: 0x0006c0

        goto    flow_ccs_061C_0768                                   ; dest: 0x000768

flow_ccs_061C_06C4:                                                  ; address: 0x0006c4

        movlw   0x05
        cpfseq  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_ccs_061C_0702                                   ; dest: 0x000702
        movf    0xa1, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_061C_06FA                                   ; dest: 0x0006fa
        decfsz  0xa1, W, B                                  ; reg: 0x0a1
        goto    flow_ccs_061C_06DE                                   ; dest: 0x0006de
        movlw   0x03
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_06DE:                                                  ; address: 0x0006de

        movlw   0x02
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_061C_06EA                                   ; dest: 0x0006ea
        movlw   0x02
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_06EA:                                                  ; address: 0x0006ea

        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_061C_06F6                                   ; dest: 0x0006f6
        movlw   0x01
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_06F6:                                                  ; address: 0x0006f6

        goto    flow_ccs_061C_06FE                                   ; dest: 0x0006fe

flow_ccs_061C_06FA:                                                  ; address: 0x0006fa

        movlw   0x04
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_06FE:                                                  ; address: 0x0006fe

        goto    flow_ccs_061C_0768                                   ; dest: 0x000768

flow_ccs_061C_0702:                                                  ; address: 0x000702

        movlw   0x06
        cpfseq  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_ccs_061C_0730                                   ; dest: 0x000730
        decfsz  0xa1, W, B                                  ; reg: 0x0a1
        goto    flow_ccs_061C_0714                                   ; dest: 0x000714
        movlw   0x04
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_0714:                                                  ; address: 0x000714

        movlw   0x02
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_061C_0720                                   ; dest: 0x000720
        movlw   0x03
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_0720:                                                  ; address: 0x000720

        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_061C_072C                                   ; dest: 0x00072c
        movlw   0x02
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_072C:                                                  ; address: 0x00072c

        goto    flow_ccs_061C_0768                                   ; dest: 0x000768

flow_ccs_061C_0730:                                                  ; address: 0x000730

        movlw   0x07
        cpfseq  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_ccs_061C_0754                                   ; dest: 0x000754
        movlw   0x02
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_061C_0744                                   ; dest: 0x000744
        movlw   0x04
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_0744:                                                  ; address: 0x000744

        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_061C_0750                                   ; dest: 0x000750
        movlw   0x03
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_0750:                                                  ; address: 0x000750

        goto    flow_ccs_061C_0768                                   ; dest: 0x000768

flow_ccs_061C_0754:                                                  ; address: 0x000754

        movlw   0x08
        cpfseq  rx_parsed_data, A                        ; reg: 0x030
        goto    flow_ccs_061C_0768                                   ; dest: 0x000768
        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_061C_0768                                   ; dest: 0x000768
        movlw   0x04
        movwf   0xb7, B                                     ; reg: 0x0b7

flow_ccs_061C_0768:                                                  ; address: 0x000768

        return  0x0

control_core_service_076A:                                               ; address: 0x00076a

        movf    0xb7, F, B                                  ; reg: 0x0b7
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_076A_0778                                   ; dest: 0x000778
        clrf    0xb8, B                                     ; reg: 0x0b8
        goto    flow_ccs_076A_08AA                                   ; dest: 0x0008aa

flow_ccs_076A_0778:                                                  ; address: 0x000778

        decfsz  0xb7, W, B                                  ; reg: 0x0b7
        goto    flow_ccs_076A_07B4                                   ; dest: 0x0007b4
        movf    0xa1, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_076A_07AC                                   ; dest: 0x0007ac
        decfsz  0xa1, W, B                                  ; reg: 0x0a1
        goto    flow_ccs_076A_0790                                   ; dest: 0x000790
        movlw   0x03
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_0790:                                                  ; address: 0x000790

        movlw   0x02
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_076A_079C                                   ; dest: 0x00079c
        movlw   0x04
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_079C:                                                  ; address: 0x00079c

        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_076A_07A8                                   ; dest: 0x0007a8
        movlw   0x05
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_07A8:                                                  ; address: 0x0007a8

        goto    flow_ccs_076A_07B0                                   ; dest: 0x0007b0

flow_ccs_076A_07AC:                                                  ; address: 0x0007ac

        movlw   0x02
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_07B0:                                                  ; address: 0x0007b0

        goto    flow_ccs_076A_08AA                                   ; dest: 0x0008aa

flow_ccs_076A_07B4:                                                  ; address: 0x0007b4

        movlw   0x02
        cpfseq  0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_076A_07F2                                   ; dest: 0x0007f2
        movf    0xa1, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_076A_07EA                                   ; dest: 0x0007ea
        decfsz  0xa1, W, B                                  ; reg: 0x0a1
        goto    flow_ccs_076A_07CE                                   ; dest: 0x0007ce
        movlw   0x04
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_07CE:                                                  ; address: 0x0007ce

        movlw   0x02
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_076A_07DA                                   ; dest: 0x0007da
        movlw   0x05
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_07DA:                                                  ; address: 0x0007da

        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_076A_07E6                                   ; dest: 0x0007e6
        movlw   0x06
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_07E6:                                                  ; address: 0x0007e6

        goto    flow_ccs_076A_07EE                                   ; dest: 0x0007ee

flow_ccs_076A_07EA:                                                  ; address: 0x0007ea

        movlw   0x03
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_07EE:                                                  ; address: 0x0007ee

        goto    flow_ccs_076A_08AA                                   ; dest: 0x0008aa

flow_ccs_076A_07F2:                                                  ; address: 0x0007f2

        movlw   0x03
        cpfseq  0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_076A_0830                                   ; dest: 0x000830
        movf    0xa1, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_076A_0828                                   ; dest: 0x000828
        decfsz  0xa1, W, B                                  ; reg: 0x0a1
        goto    flow_ccs_076A_080C                                   ; dest: 0x00080c
        movlw   0x05
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_080C:                                                  ; address: 0x00080c

        movlw   0x02
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_076A_0818                                   ; dest: 0x000818
        movlw   0x06
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_0818:                                                  ; address: 0x000818

        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_076A_0824                                   ; dest: 0x000824
        movlw   0x07
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_0824:                                                  ; address: 0x000824

        goto    flow_ccs_076A_082C                                   ; dest: 0x00082c

flow_ccs_076A_0828:                                                  ; address: 0x000828

        movlw   0x04
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_082C:                                                  ; address: 0x00082c

        goto    flow_ccs_076A_08AA                                   ; dest: 0x0008aa

flow_ccs_076A_0830:                                                  ; address: 0x000830

        movlw   0x04
        cpfseq  0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_076A_086E                                   ; dest: 0x00086e
        movf    0xa1, F, B                                  ; reg: 0x0a1
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_076A_0866                                   ; dest: 0x000866
        decfsz  0xa1, W, B                                  ; reg: 0x0a1
        goto    flow_ccs_076A_084A                                   ; dest: 0x00084a
        movlw   0x06
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_084A:                                                  ; address: 0x00084a

        movlw   0x02
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_076A_0856                                   ; dest: 0x000856
        movlw   0x07
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_0856:                                                  ; address: 0x000856

        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_076A_0862                                   ; dest: 0x000862
        movlw   0x08
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_0862:                                                  ; address: 0x000862

        goto    flow_ccs_076A_086A                                   ; dest: 0x00086a

flow_ccs_076A_0866:                                                  ; address: 0x000866

        movlw   0x05
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_086A:                                                  ; address: 0x00086a

        goto    flow_ccs_076A_08AA                                   ; dest: 0x0008aa

flow_ccs_076A_086E:                                                  ; address: 0x00086e

        movlw   0x05
        cpfseq  0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_076A_087E                                   ; dest: 0x00087e
        movlw   0x01
        movwf   0xb8, B                                     ; reg: 0x0b8
        goto    flow_ccs_076A_08AA                                   ; dest: 0x0008aa

flow_ccs_076A_087E:                                                  ; address: 0x00087e

        movlw   0x06
        cpfseq  0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_076A_088E                                   ; dest: 0x00088e
        movlw   0x02
        movwf   0xb8, B                                     ; reg: 0x0b8
        goto    flow_ccs_076A_08AA                                   ; dest: 0x0008aa

flow_ccs_076A_088E:                                                  ; address: 0x00088e

        movlw   0x07
        cpfseq  0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_076A_089E                                   ; dest: 0x00089e
        movlw   0x03
        movwf   0xb8, B                                     ; reg: 0x0b8
        goto    flow_ccs_076A_08AA                                   ; dest: 0x0008aa

flow_ccs_076A_089E:                                                  ; address: 0x00089e

        movlw   0x08
        cpfseq  0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_076A_08AA                                   ; dest: 0x0008aa
        movlw   0x04
        movwf   0xb8, B                                     ; reg: 0x0b8

flow_ccs_076A_08AA:                                                  ; address: 0x0008aa

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

        setf    tx_data_staging, A                        ; reg: 0x027
        bsf     tx_data_staging, 0x0, A                   ; reg: 0x027
        btfss   PORTA, RA3, A                               ; reg: 0xf80, bit: 3
        bcf     tx_data_staging, 0x0, A                   ; reg: 0x027
        bsf     tx_data_staging, 0x1, A                   ; reg: 0x027
        btfss   PORTC, RC0, A                               ; reg: 0xf82, bit: 0
        bcf     tx_data_staging, 0x1, A                   ; reg: 0x027
        bsf     tx_data_staging, 0x2, A                   ; reg: 0x027
        btfss   PORTA, RA2, A                               ; reg: 0xf80, bit: 2
        bcf     tx_data_staging, 0x2, A                   ; reg: 0x027
        bsf     tx_data_staging, 0x3, A                   ; reg: 0x027
        btfss   PORTA, RA1, A                               ; reg: 0xf80, bit: 1
        bcf     tx_data_staging, 0x3, A                   ; reg: 0x027
        bsf     tx_data_staging, 0x4, A                   ; reg: 0x027
        btfss   PORTC, RC5, A                               ; reg: 0xf82, bit: 5
        bcf     tx_data_staging, 0x4, A                   ; reg: 0x027
        bsf     tx_data_staging, 0x5, A                   ; reg: 0x027
        btfss   PORTA, RA4, A                               ; reg: 0xf80, bit: 4
        bcf     tx_data_staging, 0x5, A                   ; reg: 0x027
        movlw   0xff
        xorwf   tx_data_staging, F, A                     ; reg: 0x027
        movf    tx_data_staging, W, A                     ; reg: 0x027
        subwf   0xbc, W, B                                  ; reg: 0x0bc
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_button_scan_debounce_08EA                                   ; dest: 0x0008ea
        clrf    0xbb, B                                     ; reg: 0x0bb
        movff   tx_data_staging, 0x0bc                    ; reg1: 0x027
        goto    flow_button_scan_debounce_08FC                                   ; dest: 0x0008fc

flow_button_scan_debounce_08EA:                                                  ; address: 0x0008ea

        movlw   0x04
        cpfslt  0xbb, B                                     ; reg: 0x0bb
        goto    flow_button_scan_debounce_08F8                                   ; dest: 0x0008f8
        incf    0xbb, F, B                                  ; reg: 0x0bb
        goto    flow_button_scan_debounce_08FC                                   ; dest: 0x0008fc

flow_button_scan_debounce_08F8:                                                  ; address: 0x0008f8

        movff   0x0bc, 0x0be

flow_button_scan_debounce_08FC:                                                  ; address: 0x0008fc

        clrf    0x9a, B                                     ; reg: 0x09a
        movf    0xbe, W, B                                  ; reg: 0x0be
        subwf   0xbd, W, B                                  ; reg: 0x0bd
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_button_scan_debounce_0918                                   ; dest: 0x000918
        movff   0x0be, 0x0bd
        clrf    0x9b, B                                     ; reg: 0x09b
        clrf    0x9c, B                                     ; reg: 0x09c
        movff   0x0be, 0x09a
        goto    flow_button_scan_debounce_0924                                   ; dest: 0x000924

flow_button_scan_debounce_0918:                                                  ; address: 0x000918

        rrcf    0xbe, W, B                                  ; reg: 0x0be
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_button_scan_debounce_0924                                   ; dest: 0x000924
        infsnz  0x9b, F, B                                  ; reg: 0x09b
        incf    0x9c, F, B                                  ; reg: 0x09c

flow_button_scan_debounce_0924:                                                  ; address: 0x000924

        movlw   0xc9
        subwf   0x9b, W, B                                  ; reg: 0x09b
        movlw   0x32
        subwfb  0x9c, W, B                                  ; reg: 0x09c
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_button_scan_debounce_093E                                   ; dest: 0x00093e
        movlw   0x28
        movwf   0x9b, B                                     ; reg: 0x09b
        movlw   0x23
        movwf   0x9c, B                                     ; reg: 0x09c
        movff   0x0be, 0x09a

flow_button_scan_debounce_093E:                                                  ; address: 0x00093e

        return  0x0

control_core_service_0940:                                               ; address: 0x000940

        movff   tx_data_staging, (Common_RAM + 43)        ; reg1: 0x027, reg2: 0x02b
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
        clrf    tx_data_staging, A                        ; reg: 0x027

flow_ccs_0940_0964:                                                  ; address: 0x000964

        movlw   0x10
        cpfslt  tx_data_staging, A                        ; reg: 0x027
        goto    flow_ccs_0940_098E                                   ; dest: 0x00098e
        movf    tx_data_staging, W, A                     ; reg: 0x027
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
        incf    tx_data_staging, F, A                     ; reg: 0x027
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_ccs_0940_0964                                   ; dest: 0x000964

flow_ccs_0940_098E:                                                  ; address: 0x00098e

        return  0x0

control_core_service_0990:                                               ; address: 0x000990

        clrf    EEADR, A                                    ; reg: 0xfa9
        movf    0xbf, W, B                                  ; reg: 0x0bf
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x01
        movwf   EEADR, A                                    ; reg: 0xfa9
        movf    0xba, W, B                                  ; reg: 0x0ba
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x02
        movwf   EEADR, A                                    ; reg: 0xfa9
        movf    0xc0, W, B                                  ; reg: 0x0c0
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        clrf    tx_data_staging, A                        ; reg: 0x027

flow_ccs_0990_09AE:                                                  ; address: 0x0009ae

        movlw   0x06                                        ; CMD input_select
        cpfslt  tx_data_staging, A                        ; reg: 0x027
        goto    flow_ccs_0990_0A3A                                   ; dest: 0x000a3a
        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, 0x0c1
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x09
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, 0x0c7
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x0f
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, 0x0cd
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x15
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, 0x0d3
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x1b                                        ; CMD channel_src_5
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, 0x0d9
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x21
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, 0x0df
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x27
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        movwf   EEADR, A                                    ; reg: 0xfa9
        lfsr    0x0, 0x0e5
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        incf    tx_data_staging, F, A                     ; reg: 0x027
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_ccs_0990_09AE                                   ; dest: 0x0009ae

flow_ccs_0990_0A3A:                                                  ; address: 0x000a3a

        movlw   0x73
        movwf   EEADR, A                                    ; reg: 0xfa9
        movf    0xeb, W, B                                  ; reg: 0x0eb
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
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
        movwf   0xbf, B                                     ; reg: 0x0bf
        movlw   0x01
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   0xba, B                                     ; reg: 0x0ba
        movlw   0x02
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   0xc0, B                                     ; reg: 0x0c0
        clrf    tx_data_staging, A                        ; reg: 0x027

flow_settings_load_eeprom_0A60:                                                  ; address: 0x000a60

        movlw   0x06                                        ; CMD input_select
        cpfslt  tx_data_staging, A                        ; reg: 0x027
        goto    flow_settings_load_eeprom_0AFA                                   ; dest: 0x000afa
        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, 0x0c1
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x09
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, 0x0c7
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x0f
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, 0x0cd
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x15
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, 0x0d3
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x1b                                        ; CMD channel_src_5
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, 0x0d9
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x21
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, 0x0df
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        movlw   0x27
        addwf   tx_data_staging, W, A                     ; reg: 0x027
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, 0x0e5
        movf    tx_data_staging, W, A                     ; reg: 0x027
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        incf    tx_data_staging, F, A                     ; reg: 0x027
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_settings_load_eeprom_0A60                                   ; dest: 0x000a60

flow_settings_load_eeprom_0AFA:                                                  ; address: 0x000afa

        movlw   0x73
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   0xeb, B                                     ; reg: 0x0eb
        movlw   0x05
        subwf   0xeb, W, B                                  ; reg: 0x0eb
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_settings_load_eeprom_0B10                                   ; dest: 0x000b10
        movlw   0x01
        movwf   0xeb, B                                     ; reg: 0x0eb

flow_settings_load_eeprom_0B10:                                                  ; address: 0x000b10

        call    control_core_service_1478, 0x0                           ; dest: 0x001478
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

        movlw   0xb0                                        ; ROUTE broadcast CONTROL→MAIN
        addwf   (Common_RAM + 51), W, A                     ; reg: 0x033
        movwf   tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movff   (Common_RAM + 52), tx_data_staging        ; reg1: 0x034, reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movff   (Common_RAM + 53), tx_data_staging        ; reg1: 0x035, reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        clrf    0x9f, B                                     ; reg: 0x09f
        clrf    0xa0, B                                     ; reg: 0x0a0
        return  0x0


; ===========================================================================
; full_sync_burst @ 0x000B36 — full_sync_burst    *** BUG C7 ***
; ---------------------------------------------------------------------------
; Emits the 5-frame full status sync to MAIN: volume, input, mute,
; backlight, standby/wake — each with a ~250 µs inter-frame delay
; (delay_short with W=0x05). Triggered when full_sync_counter at
; 0x09F:0x0A0 overflows past 0x4E20 (about 20,000 idle ticks ≈ depends
; on event-loop period).
;
; *** BUG C7 (fullsync_burst_saturates_link) ***
; Five 3-byte frames + 4 inter-frame gaps = ~17 bytes back-to-back over
; the 31,250-baud link (~5.5 ms wire time). MAIN's RX ring is 192 bytes
; so this in itself does not overflow it, but combined with any in-flight
; user command (volume nudge during burst) the RX side can stack up
; faster than main_uart_service_1be6 drains it. The V3.2 hardening plan
; calls for either rate-limiting bursts to one frame per main loop pass,
; or moving sync to a request/response model.
; ===========================================================================
; full_sync_burst:
full_sync_burst:                                               ; address: 0x000b36

        call    volume_frame_send, 0x0                           ; dest: 0x000c40
        movlw   0x05                                        ; CMD raw_status (MAIN→CONTROL echo)
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    input_frame_send, 0x0                           ; dest: 0x000c22
        movlw   0x05                                        ; CMD raw_status (MAIN→CONTROL echo)
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    mute_frame_send, 0x0                           ; dest: 0x000c7c
        movlw   0x05                                        ; CMD raw_status (MAIN→CONTROL echo)
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    cmd1d_setting_frame_send, 0x0                           ; dest: 0x000c5e
        movlw   0x05                                        ; CMD raw_status (MAIN→CONTROL echo)
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    standby_wake_broadcast, 0x0                           ; dest: 0x000c98
        return  0x0


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

        movlw   0xb1                                        ; ROUTE addressed MAIN#1
        movwf   tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movlw   0x04                                        ; CMD status_poll
        movwf   tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        clrf    tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x17
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, 0x0c1
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x18
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, 0x0c7
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x19
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, 0x0cd
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x1a
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, 0x0d3
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x1b
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, 0x0d9
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x1c
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, 0x0df
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0
        incf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movwf   (Common_RAM + 51), A                        ; reg: 0x033
        movlw   0x1e
        movwf   (Common_RAM + 52), A                        ; reg: 0x034
        lfsr    0x0, 0x0e5
        movf    (Common_RAM + 40), W, A                     ; reg: 0x028
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        movf    (Common_RAM + 53), F, A                     ; reg: 0x035
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_poll_frame_send_0C1E                                   ; dest: 0x000c1e
        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        movwf   (Common_RAM + 53), A                        ; reg: 0x035

flow_poll_frame_send_0C1E:                                                  ; address: 0x000c1e

        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
        return  0x0


; ===========================================================================
; input_frame_send @ 0x000C22 — input_frame_send  (V1.6b refactor)
; ---------------------------------------------------------------------------
; Emits [B0, 0x06, <0x0B8>] — broadcast input selection. 0x0B8 is the
; cached input value (also one of the boot handshake sentinels; MAIN
; overwrites it during status burst response). NOTE: in V1.4 this same
; address held a *channel_17_config* sender — refactor moved to dedicated
; helpers per cmd in V1.5b+.
; ===========================================================================
; input_frame_send:
input_frame_send:                                               ; address: 0x000c22

        movlw   0xb0                                        ; ROUTE broadcast CONTROL→MAIN
        movwf   tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movlw   0x06                                        ; CMD input_select
        movwf   tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movff   0x0b8, tx_data_staging                    ; reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        clrf    0x9f, B                                     ; reg: 0x09f
        clrf    0xa0, B                                     ; reg: 0x0a0
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

        movlw   0xb0                                        ; ROUTE broadcast CONTROL→MAIN
        movwf   tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movlw   0x07                                        ; CMD volume (offset 0x60)
        movwf   tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movff   0x0b9, tx_data_staging                    ; reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        clrf    0x9f, B                                     ; reg: 0x09f
        clrf    0xa0, B                                     ; reg: 0x0a0
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

        movlw   0xb0                                        ; ROUTE broadcast CONTROL→MAIN
        movwf   tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movlw   0x1d                                        ; CMD shared_cmd1d_setting (BL timeout / profile)
        movwf   tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movff   0x0a7, tx_data_staging                    ; reg2: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        clrf    0x9f, B                                     ; reg: 0x09f
        clrf    0xa0, B                                     ; reg: 0x0a0
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
        btfss   control_flags, 0x5, A                   ; reg: 0x01f
        goto    flow_mute_frame_send_0C90                                   ; dest: 0x000c90
        movlw   0x02
        movwf   (Common_RAM + 53), A                        ; reg: 0x035
        goto    flow_mute_frame_send_0C94                                   ; dest: 0x000c94

flow_mute_frame_send_0C90:                                                  ; address: 0x000c90

        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        movwf   (Common_RAM + 53), A                        ; reg: 0x035

flow_mute_frame_send_0C94:                                                  ; address: 0x000c94

        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
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
        btfsc   control_flags, 0x1, A                   ; reg: 0x01f
        goto    flow_standby_wake_broadcast_0CAA                                   ; dest: 0x000caa
        clrf    (Common_RAM + 53), A                        ; reg: 0x035
        goto    flow_standby_wake_broadcast_0CAE                                   ; dest: 0x000cae

flow_standby_wake_broadcast_0CAA:                                                  ; address: 0x000caa

        movlw   0x01
        movwf   (Common_RAM + 53), A                        ; reg: 0x035

flow_standby_wake_broadcast_0CAE:                                                  ; address: 0x000cae

        rcall   serial_tx_routed_frame                                ; dest: 0x000b16
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
display_loop_iteration:                                               ; address: 0x000cb2

        bsf     INTCON, RBIE, A                             ; reg: 0xff2, bit: 3

flow_display_loop_iteration_0CB4:                                                  ; address: 0x000cb4

        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        call    rx_parser_entry, 0x0                           ; dest: 0x00044a
        movf    0x9e, W, B                                  ; reg: 0x09e
        xorlw   0xea
        movlw   0x60
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        xorwf   0x9d, W, B                                  ; reg: 0x09d
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_display_loop_iteration_0CCE                                   ; dest: 0x000cce
        rcall   control_core_service_0990                                ; dest: 0x000990

flow_display_loop_iteration_0CCE:                                                  ; address: 0x000cce

        movlw   0x61
        subwf   0x9d, W, B                                  ; reg: 0x09d
        movlw   0xea
        subwfb  0x9e, W, B                                  ; reg: 0x09e
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_display_loop_iteration_0CE0                                   ; dest: 0x000ce0
        infsnz  0x9d, F, B                                  ; reg: 0x09d
        incf    0x9e, F, B                                  ; reg: 0x09e

flow_display_loop_iteration_0CE0:                                                  ; address: 0x000ce0

        call    control_core_service_0DCE, 0x0                           ; dest: 0x000dce
        movf    0xa0, W, B                                  ; reg: 0x0a0
        xorlw   0x4e
        movlw   0x20
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        xorwf   0x9f, W, B                                  ; reg: 0x09f
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_display_loop_iteration_0CFE                                   ; dest: 0x000cfe
        rcall   full_sync_burst                                ; dest: 0x000b36
        clrf    0x9f, B                                     ; reg: 0x09f
        clrf    0xa0, B                                     ; reg: 0x0a0
        goto    flow_display_loop_iteration_0D02                                   ; dest: 0x000d02

flow_display_loop_iteration_0CFE:                                                  ; address: 0x000cfe

        infsnz  0x9f, F, B                                  ; reg: 0x09f
        incf    0xa0, F, B                                  ; reg: 0x0a0

flow_display_loop_iteration_0D02:                                                  ; address: 0x000d02

        btfsc   control_flags, 0x1, A                   ; reg: 0x01f
        goto    flow_display_loop_iteration_0D10                                   ; dest: 0x000d10
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bcf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        goto    flow_display_loop_iteration_0D7A                                   ; dest: 0x000d7a

flow_display_loop_iteration_0D10:                                                  ; address: 0x000d10

        movf    0xeb, F, B                                  ; reg: 0x0eb
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_display_loop_iteration_0D76                                   ; dest: 0x000d76
        movf    0xec, W, B                                  ; reg: 0x0ec
        subwf   0xb0, W, B                                  ; reg: 0x0b0
        movf    0xed, W, B                                  ; reg: 0x0ed
        subwfb  0xb1, W, B                                  ; reg: 0x0b1
        movf    0xee, W, B                                  ; reg: 0x0ee
        subwfb  0xb2, W, B                                  ; reg: 0x0b2
        movf    0xef, W, B                                  ; reg: 0x0ef
        subwfb  0xb3, W, B                                  ; reg: 0x0b3
        movf    0xb3, W, B                                  ; reg: 0x0b3
        xorwf   0xef, W, B                                  ; reg: 0x0ef
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        xorlw   0x80
        btfss   STATUS, N, A                                ; reg: 0xfd8, bit: 4
        goto    flow_display_loop_iteration_0D3E                                   ; dest: 0x000d3e
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bcf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        goto    flow_display_loop_iteration_0D72                                   ; dest: 0x000d72

flow_display_loop_iteration_0D3E:                                                  ; address: 0x000d3e

        btfss   control_flags, 0x5, A                   ; reg: 0x01f
        goto    flow_display_loop_iteration_0D64                                   ; dest: 0x000d64
        infsnz  0xb4, F, B                                  ; reg: 0x0b4
        incf    0xb5, F, B                                  ; reg: 0x0b5
        movf    0xb5, W, B                                  ; reg: 0x0b5
        xorlw   0x75
        movlw   0x30
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        xorwf   0xb4, W, B                                  ; reg: 0x0b4
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_display_loop_iteration_0D60                                   ; dest: 0x000d60
        btg     PORTC, RC1, A                               ; reg: 0xf82, bit: 1
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        clrf    0xb4, B                                     ; reg: 0x0b4
        clrf    0xb5, B                                     ; reg: 0x0b5

flow_display_loop_iteration_0D60:                                                  ; address: 0x000d60

        goto    flow_display_loop_iteration_0D68                                   ; dest: 0x000d68

flow_display_loop_iteration_0D64:                                                  ; address: 0x000d64

        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bsf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1

flow_display_loop_iteration_0D68:                                                  ; address: 0x000d68

        incf    0xb0, F, B                                  ; reg: 0x0b0
        movlw   0x00
        addwfc  0xb1, F, B                                  ; reg: 0x0b1
        addwfc  0xb2, F, B                                  ; reg: 0x0b2
        addwfc  0xb3, F, B                                  ; reg: 0x0b3

flow_display_loop_iteration_0D72:                                                  ; address: 0x000d72

        goto    flow_display_loop_iteration_0D7A                                   ; dest: 0x000d7a

flow_display_loop_iteration_0D76:                                                  ; address: 0x000d76

        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bsf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1

flow_display_loop_iteration_0D7A:                                                  ; address: 0x000d7a

        movlw   0x00
        movf    0x9a, F, B                                  ; reg: 0x09a
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   control_flags, 0x3, A                   ; reg: 0x01f
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_display_loop_iteration_0CB4                                   ; dest: 0x000cb4
        movlw   0x00
        movf    0x9a, F, B                                  ; reg: 0x09a
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   control_flags, 0x4, A                   ; reg: 0x01f
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_display_loop_iteration_0DB0                                   ; dest: 0x000db0
        clrf    0xb3, B                                     ; reg: 0x0b3
        clrf    0xb2, B                                     ; reg: 0x0b2
        clrf    0xb1, B                                     ; reg: 0x0b1
        clrf    0xb0, B                                     ; reg: 0x0b0

flow_display_loop_iteration_0DB0:                                                  ; address: 0x000db0

        bcf     control_flags, 0x4, A                   ; reg: 0x01f
        rrcf    0x9a, W, B                                  ; reg: 0x09a
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_display_loop_iteration_0DC8                                   ; dest: 0x000dc8
        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x0, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_display_loop_iteration_0DC8                                   ; dest: 0x000dc8
        btg     control_flags, 0x1, A                   ; reg: 0x01f

flow_display_loop_iteration_0DC8:                                                  ; address: 0x000dc8

        clrf    0x9d, B                                     ; reg: 0x09d
        clrf    0x9e, B                                     ; reg: 0x09e
        return  0x0

control_core_service_0DCE:                                               ; address: 0x000dce

        movf    (Common_RAM + 27), F, A                     ; reg: 0x01b
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_0DCE_0DDE                                   ; dest: 0x000dde
        movf    (Common_RAM + 28), F, A                     ; reg: 0x01c
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_0DCE_0DE4                                   ; dest: 0x000de4

flow_ccs_0DCE_0DDE:                                                  ; address: 0x000dde

        decf    (Common_RAM + 27), F, A                     ; reg: 0x01b
        movlw   0x00
        subwfb  (Common_RAM + 28), F, A                     ; reg: 0x01c

flow_ccs_0DCE_0DE4:                                                  ; address: 0x000de4

        btfss   control_flags, 0x0, A                   ; reg: 0x01f
        goto    flow_ccs_0DCE_0DEC                                   ; dest: 0x000dec
        return  0x0

flow_ccs_0DCE_0DEC:                                                  ; address: 0x000dec

        movf    ir_decoded_addr, W, A                     ; reg: 0x01e
        cpfseq  (Common_RAM + 32), A                        ; reg: 0x020
        goto    flow_ccs_0DCE_0F50                                   ; dest: 0x000f50
        movf    ir_decoded_cmd, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 33), A                        ; reg: 0x021
        goto    flow_ccs_0DCE_0E0C                                   ; dest: 0x000e0c
        movlw   0x50
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0xc3
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        btg     control_flags, 0x1, A                   ; reg: 0x01f
        bsf     control_flags, 0x3, A                   ; reg: 0x01f
        goto    flow_ccs_0DCE_0F50                                   ; dest: 0x000f50

flow_ccs_0DCE_0E0C:                                                  ; address: 0x000e0c

        movf    ir_decoded_cmd, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 34), A                        ; reg: 0x022
        goto    flow_ccs_0DCE_0E32                                   ; dest: 0x000e32
        movlw   0xd0
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0x07
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        movlw   0x72
        cpfslt  0xb9, B                                     ; reg: 0x0b9
        goto    flow_ccs_0DCE_0E2E                                   ; dest: 0x000e2e
        incf    0xb9, F, B                                  ; reg: 0x0b9
        bcf     control_flags, 0x5, A                   ; reg: 0x01f
        rcall   volume_frame_send                                ; dest: 0x000c40
        bsf     control_flags, 0x3, A                   ; reg: 0x01f
        bsf     control_flags, 0x4, A                   ; reg: 0x01f

flow_ccs_0DCE_0E2E:                                                  ; address: 0x000e2e

        goto    flow_ccs_0DCE_0F50                                   ; dest: 0x000f50

flow_ccs_0DCE_0E32:                                                  ; address: 0x000e32

        movf    ir_decoded_cmd, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 35), A                        ; reg: 0x023
        goto    flow_ccs_0DCE_0E58                                   ; dest: 0x000e58
        movlw   0xd0
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0x07
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        movf    0xb9, F, B                                  ; reg: 0x0b9
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_0DCE_0E54                                   ; dest: 0x000e54
        decf    0xb9, F, B                                  ; reg: 0x0b9
        bcf     control_flags, 0x5, A                   ; reg: 0x01f
        rcall   volume_frame_send                                ; dest: 0x000c40
        bsf     control_flags, 0x3, A                   ; reg: 0x01f
        bsf     control_flags, 0x4, A                   ; reg: 0x01f

flow_ccs_0DCE_0E54:                                                  ; address: 0x000e54

        goto    flow_ccs_0DCE_0F50                                   ; dest: 0x000f50

flow_ccs_0DCE_0E58:                                                  ; address: 0x000e58

        movf    ir_decoded_cmd, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 38), A                        ; reg: 0x026
        goto    flow_ccs_0DCE_0E7C                                   ; dest: 0x000e7c
        movlw   0x2f
        movwf   0xb4, B                                     ; reg: 0x0b4
        movlw   0x75
        movwf   0xb5, B                                     ; reg: 0x0b5
        btg     control_flags, 0x5, A                   ; reg: 0x01f
        movlw   0x20
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0x4e
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        bsf     control_flags, 0x3, A                   ; reg: 0x01f
        bsf     control_flags, 0x4, A                   ; reg: 0x01f
        rcall   mute_frame_send                                ; dest: 0x000c7c
        goto    flow_ccs_0DCE_0F50                                   ; dest: 0x000f50

flow_ccs_0DCE_0E7C:                                                  ; address: 0x000e7c

        movf    ir_decoded_cmd, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 37), A                        ; reg: 0x025
        goto    flow_ccs_0DCE_0EE6                                   ; dest: 0x000ee6
        movf    0xa1, F, B                                  ; reg: 0x0a1
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_0DCE_0E94                                   ; dest: 0x000e94
        movlw   0x05                                        ; CMD raw_status (MAIN→CONTROL echo)
        movwf   tx_data_staging, A                        ; reg: 0x027
        goto    flow_ccs_0DCE_0EBE                                   ; dest: 0x000ebe

flow_ccs_0DCE_0E94:                                                  ; address: 0x000e94

        decfsz  0xa1, W, B                                  ; reg: 0x0a1
        goto    flow_ccs_0DCE_0EA2                                   ; dest: 0x000ea2
        movlw   0x06                                        ; CMD input_select
        movwf   tx_data_staging, A                        ; reg: 0x027
        goto    flow_ccs_0DCE_0EBE                                   ; dest: 0x000ebe

flow_ccs_0DCE_0EA2:                                                  ; address: 0x000ea2

        movlw   0x02
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_0DCE_0EB2                                   ; dest: 0x000eb2
        movlw   0x07                                        ; CMD volume (offset 0x60)
        movwf   tx_data_staging, A                        ; reg: 0x027
        goto    flow_ccs_0DCE_0EBE                                   ; dest: 0x000ebe

flow_ccs_0DCE_0EB2:                                                  ; address: 0x000eb2

        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_0DCE_0EBE                                   ; dest: 0x000ebe
        movlw   0x08                                        ; CMD dsp_fault (V1.63b+ BF/08 payload)
        movwf   tx_data_staging, A                        ; reg: 0x027

flow_ccs_0DCE_0EBE:                                                  ; address: 0x000ebe

        movf    0xb7, F, B                                  ; reg: 0x0b7
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_0DCE_0ECC                                   ; dest: 0x000ecc
        decf    0xb7, F, B                                  ; reg: 0x0b7
        goto    flow_ccs_0DCE_0ED0                                   ; dest: 0x000ed0

flow_ccs_0DCE_0ECC:                                                  ; address: 0x000ecc

        movff   tx_data_staging, 0x0b7                    ; reg1: 0x027

flow_ccs_0DCE_0ED0:                                                  ; address: 0x000ed0

        bsf     control_flags, 0x3, A                   ; reg: 0x01f
        bsf     control_flags, 0x4, A                   ; reg: 0x01f
        movlw   0x58
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0x1b                                        ; CMD channel_src_5
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        call    control_core_service_076A, 0x0                           ; dest: 0x00076a
        rcall   input_frame_send                                ; dest: 0x000c22
        goto    flow_ccs_0DCE_0F50                                   ; dest: 0x000f50

flow_ccs_0DCE_0EE6:                                                  ; address: 0x000ee6

        movf    ir_decoded_cmd, W, A                     ; reg: 0x01d
        cpfseq  (Common_RAM + 36), A                        ; reg: 0x024
        goto    flow_ccs_0DCE_0F4E                                   ; dest: 0x000f4e
        movf    0xa1, F, B                                  ; reg: 0x0a1
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_0DCE_0EFE                                   ; dest: 0x000efe
        movlw   0x05                                        ; CMD raw_status (MAIN→CONTROL echo)
        movwf   tx_data_staging, A                        ; reg: 0x027
        goto    flow_ccs_0DCE_0F28                                   ; dest: 0x000f28

flow_ccs_0DCE_0EFE:                                                  ; address: 0x000efe

        decfsz  0xa1, W, B                                  ; reg: 0x0a1
        goto    flow_ccs_0DCE_0F0C                                   ; dest: 0x000f0c
        movlw   0x06                                        ; CMD input_select
        movwf   tx_data_staging, A                        ; reg: 0x027
        goto    flow_ccs_0DCE_0F28                                   ; dest: 0x000f28

flow_ccs_0DCE_0F0C:                                                  ; address: 0x000f0c

        movlw   0x02
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_0DCE_0F1C                                   ; dest: 0x000f1c
        movlw   0x07                                        ; CMD volume (offset 0x60)
        movwf   tx_data_staging, A                        ; reg: 0x027
        goto    flow_ccs_0DCE_0F28                                   ; dest: 0x000f28

flow_ccs_0DCE_0F1C:                                                  ; address: 0x000f1c

        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_0DCE_0F28                                   ; dest: 0x000f28
        movlw   0x08                                        ; CMD dsp_fault (V1.63b+ BF/08 payload)
        movwf   tx_data_staging, A                        ; reg: 0x027

flow_ccs_0DCE_0F28:                                                  ; address: 0x000f28

        movf    tx_data_staging, W, A                     ; reg: 0x027
        cpfslt  0xb7, B                                     ; reg: 0x0b7
        goto    flow_ccs_0DCE_0F36                                   ; dest: 0x000f36
        incf    0xb7, F, B                                  ; reg: 0x0b7
        goto    flow_ccs_0DCE_0F38                                   ; dest: 0x000f38

flow_ccs_0DCE_0F36:                                                  ; address: 0x000f36

        clrf    0xb7, B                                     ; reg: 0x0b7

flow_ccs_0DCE_0F38:                                                  ; address: 0x000f38

        bsf     control_flags, 0x3, A                   ; reg: 0x01f
        bsf     control_flags, 0x4, A                   ; reg: 0x01f
        movlw   0x58
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        movlw   0x1b                                        ; CMD channel_src_5
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        call    control_core_service_076A, 0x0                           ; dest: 0x00076a
        rcall   input_frame_send                                ; dest: 0x000c22
        goto    flow_ccs_0DCE_0F50                                   ; dest: 0x000f50

flow_ccs_0DCE_0F4E:                                                  ; stock IR dispatch fallthrough #1

        bsf     control_flags, IR_ARMED, A              ; reg: 0x01f

flow_ccs_0DCE_0F50:                                                  ; stock IR dispatch exit (no stock case matched)

        ; ---------------------------------------------------------------
        ; V1.71 inline (V1.61b + V1.64b): preset + standby/wake IR shortcuts
        ; ---------------------------------------------------------------
        ; The stock IR dispatch reaches this label when ir_decoded_cmd
        ; did not match any of the menu-configured IR codes stored in
        ; RAM(0x21..0x26).  V1.71 adds four fixed IR shortcuts on top:
        ;
        ;   RC5 0x38 → preset A   (V1.61b)
        ;   RC5 0x39 → preset B   (V1.61b)
        ;   RC5 0x3A → standby    (V1.64b explicit-standby endpoint)
        ;   RC5 0x3B → wake       (V1.64b explicit-wake endpoint)
        ;
        ; All four are handled inline before re-arming the IR gate; any
        ; other unmapped code falls through to the stock re-arm path.
        movf    ir_decoded_cmd, W, A
        xorlw   RC5_PRESET_A                             ; 0x38
        bz      v171_ir_preset_a_case
        movf    ir_decoded_cmd, W, A
        xorlw   RC5_PRESET_B                             ; 0x39
        bz      v171_ir_preset_b_case
        movf    ir_decoded_cmd, W, A
        xorlw   RC5_STANDBY_ENTER                        ; 0x3A
        bz      v171_ir_standby_case
        movf    ir_decoded_cmd, W, A
        xorlw   RC5_WAKE                                 ; 0x3B
        bz      v171_ir_wake_case
        ; Not a V1.71 shortcut — standard re-arm + return.
        bsf     control_flags, IR_ARMED, A
        return  0x0

v171_ir_preset_a_case:
        btfss   control_flags, PRESET_BIT, A             ; already A?
        bra     v171_ir_preset_done                      ; yes — skip emit
        bcf     control_flags, PRESET_BIT, A             ; 0 = preset A
        rcall   v171_send_preset_frame_and_persist
        bsf     control_flags, 0x3, A                    ; event_exit
        bra     v171_ir_preset_done

v171_ir_preset_b_case:
        btfsc   control_flags, PRESET_BIT, A             ; already B?
        bra     v171_ir_preset_done
        bsf     control_flags, PRESET_BIT, A             ; 1 = preset B
        rcall   v171_send_preset_frame_and_persist
        bsf     control_flags, 0x3, A                    ; event_exit

v171_ir_preset_done:
        bsf     control_flags, IR_ARMED, A
        return  0x0

v171_ir_standby_case:
        ; V1.64b explicit standby (RC5 0x3A): emit [B0, 0x03, 0x00]
        ; and set event_exit.  Unlike the RC5 power-toggle (stock 0x32)
        ; this endpoint forces standby regardless of current state.
        rcall   v171_send_standby_cmd_frame
        bsf     control_flags, 0x3, A                    ; event_exit
        bra     v171_ir_endpoint_done

v171_ir_wake_case:
        ; V1.64b explicit wake (RC5 0x3B): emit [B0, 0x03, 0x01] and
        ; set event_exit.  Forces wake regardless of current state.
        rcall   v171_send_wake_cmd_frame
        bsf     control_flags, 0x3, A                    ; event_exit

v171_ir_endpoint_done:
        bsf     control_flags, IR_ARMED, A
        return  0x0

v171_send_standby_cmd_frame:
        ; Emit [0xB0, 0x03, 0x00] — broadcast CMD standby/wake with
        ; data = 0 (standby).  Rides the normal TX pipeline via
        ; tx_byte_enqueue.
        movlw   0xB0
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        movlw   0x03
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        clrf    tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        return  0x0

v171_send_wake_cmd_frame:
        ; Emit [0xB0, 0x03, 0x01] — broadcast CMD standby/wake with
        ; data = 1 (wake).  Rides the normal TX pipeline.
        movlw   0xB0
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        movlw   0x03
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        movlw   0x01
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        return  0x0

v171_send_preset_frame_and_persist:
        ; ---------------------------------------------------------------
        ; V1.71 inline helper: emit [B0, 0x20, preset_byte] and persist
        ; preset state byte to EEPROM slot 0x74.
        ; preset_byte = 0 when PRESET_BIT clear (A), 1 when set (B).
        ; The TX frame goes through tx_byte_enqueue so it rides the
        ; normal ISR-drained UART pipeline; the EEPROM write is blocking
        ; (~3.3 ms) via the stock eeprom_write_byte helper.
        ; ---------------------------------------------------------------
        movlw   0xB0                                     ; ROUTE broadcast CONTROL→MAIN
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        movlw   0x20                                     ; CMD preset_select
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        clrf    WREG, A
        btfsc   control_flags, PRESET_BIT, A
        movlw   0x01
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        movlw   EEPROM_PRESET_STATE_ADDR                 ; 0x74
        movwf   EEADR, A
        clrf    WREG, A
        btfsc   control_flags, PRESET_BIT, A
        movlw   0x01
        call    eeprom_write_byte, 0x0
        return  0x0

control_core_service_0F54:                                               ; address: 0x000f54

        movlw   0x04
        cpfseq  0xa7, B                                     ; reg: 0x0a7
        goto    flow_ccs_0F54_0F7C                                   ; dest: 0x000f7c
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
        goto    flow_ccs_0F54_0F9E                                   ; dest: 0x000f9e

flow_ccs_0F54_0F7C:                                                  ; address: 0x000f7c

        movlw   0x03
        cpfseq  0xa7, B                                     ; reg: 0x0a7
        goto    flow_ccs_0F54_0F9E                                   ; dest: 0x000f9e
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

flow_ccs_0F54_0F9E:                                                  ; address: 0x000f9e

        return  0x0

control_core_service_0FA0:                                               ; address: 0x000fa0

        movff   0x0a2, (Common_RAM + 41)                    ; reg2: 0x029
        movff   0x0a3, (Common_RAM + 42)                    ; reg2: 0x02a
        movff   0x0a5, tx_data_staging                    ; reg2: 0x027
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc0
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    control_core_service_0940, 0x0                           ; dest: 0x000940

flow_ccs_0FA0_0FBA:                                                  ; address: 0x000fba

        rcall   display_loop_iteration                                ; dest: 0x000cb2
        movlw   0x00
        movf    0x9a, F, B                                  ; reg: 0x09a
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   control_flags, 0x3, A                   ; reg: 0x01f
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_ccs_0FA0_0FBA                                   ; dest: 0x000fba
        rrcf    0x9a, W, B                                  ; reg: 0x09a
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_ccs_0FA0_0FEC                                   ; dest: 0x000fec
        movf    0xa5, W, B                                  ; reg: 0x0a5
        cpfseq  0xa4, B                                     ; reg: 0x0a4
        goto    flow_ccs_0FA0_0FEA                                   ; dest: 0x000fea
        clrf    0xa5, B                                     ; reg: 0x0a5
        goto    flow_ccs_0FA0_0FEC                                   ; dest: 0x000fec

flow_ccs_0FA0_0FEA:                                                  ; address: 0x000fea

        incf    0xa5, F, B                                  ; reg: 0x0a5

flow_ccs_0FA0_0FEC:                                                  ; address: 0x000fec

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x2, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_ccs_0FA0_100A                                   ; dest: 0x00100a
        movf    0xa5, F, B                                  ; reg: 0x0a5
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_0FA0_1008                                   ; dest: 0x001008
        movff   0x0a4, 0x0a5
        goto    flow_ccs_0FA0_100A                                   ; dest: 0x00100a

flow_ccs_0FA0_1008:                                                  ; address: 0x001008

        decf    0xa5, F, B                                  ; reg: 0x0a5

flow_ccs_0FA0_100A:                                                  ; address: 0x00100a

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

flow_ccs_0FA0_103C:                                                  ; address: 0x00103c

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
        clrf    0x96, B                                     ; reg: 0x096
        clrf    0x97, B                                     ; reg: 0x097
        clrf    0x98, B                                     ; reg: 0x098
        clrf    0x99, B                                     ; reg: 0x099
        bcf     control_flags, 0x2, A                   ; reg: 0x01f
        clrf    0xa6, B                                     ; reg: 0x0a6
        clrf    ir_decoded_cmd, A                        ; reg: 0x01d
        clrf    ir_decoded_cmd, A                        ; reg: 0x01d
        clrf    ir_decoded_addr, A                        ; reg: 0x01e
        clrf    0x9b, B                                     ; reg: 0x09b
        clrf    0x9c, B                                     ; reg: 0x09c
        lfsr    0x0, 0x0c1
        movlw   0x06

flow_ccs_0FA0_106E:                                                  ; address: 0x00106e

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     flow_ccs_0FA0_106E                                   ; dest: 0x00106e
        lfsr    0x0, 0x0c7
        movlw   0x06

flow_ccs_0FA0_107A:                                                  ; address: 0x00107a

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     flow_ccs_0FA0_107A                                   ; dest: 0x00107a
        lfsr    0x0, 0x0cd
        movlw   0x06

flow_ccs_0FA0_1086:                                                  ; address: 0x001086

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     flow_ccs_0FA0_1086                                   ; dest: 0x001086
        lfsr    0x0, 0x0d3
        movlw   0x06

flow_ccs_0FA0_1092:                                                  ; address: 0x001092

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     flow_ccs_0FA0_1092                                   ; dest: 0x001092
        lfsr    0x0, 0x0d9
        movlw   0x06

flow_ccs_0FA0_109E:                                                  ; address: 0x00109e

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     flow_ccs_0FA0_109E                                   ; dest: 0x00109e
        lfsr    0x0, 0x0df
        movlw   0x06

flow_ccs_0FA0_10AA:                                                  ; address: 0x0010aa

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     flow_ccs_0FA0_10AA                                   ; dest: 0x0010aa
        clrf    (Common_RAM + 50), A                        ; reg: 0x032
        bcf     control_flags, 0x3, A                   ; reg: 0x01f
        bcf     control_flags, 0x4, A                   ; reg: 0x01f
        setf    EEADR, A                                    ; reg: 0xfa9
        movlw   0x02
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2
        movlw   0x70
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   tx_data_staging, A                        ; reg: 0x027
        movlw   0x01
        subwf   tx_data_staging, W, A                     ; reg: 0x027
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_0FA0_10DA                                   ; dest: 0x0010da
        movlw   0x70
        movwf   EEADR, A                                    ; reg: 0xfa9
        movlw   0x01
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2

flow_ccs_0FA0_10DA:                                                  ; address: 0x0010da

        movlw   0x71
        call    eeprom_read_byte, 0x0                           ; dest: 0x000196
        movwf   tx_data_staging, A                        ; reg: 0x027
        movlw   0x06                                        ; CMD input_select
        subwf   tx_data_staging, W, A                     ; reg: 0x027
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_0FA0_10F6                                   ; dest: 0x0010f6
        movlw   0x71
        movwf   EEADR, A                                    ; reg: 0xfa9
        movlw   0x06
        call    eeprom_write_byte, 0x0                           ; dest: 0x0001a2

flow_ccs_0FA0_10F6:                                                  ; address: 0x0010f6

        clrf    0xbc, B                                     ; reg: 0x0bc
        clrf    0xbe, B                                     ; reg: 0x0be
        clrf    0xbd, B                                     ; reg: 0x0bd
        clrf    0xb4, B                                     ; reg: 0x0b4
        clrf    0xb5, B                                     ; reg: 0x0b5
        clrf    0xb3, B                                     ; reg: 0x0b3
        clrf    0xb2, B                                     ; reg: 0x0b2
        clrf    0xb1, B                                     ; reg: 0x0b1
        clrf    0xb0, B                                     ; reg: 0x0b0
        movlw   0x01
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0x2c
        call    control_core_service_01BE, 0x0                           ; dest: 0x0001be
        call    app_entry_defensive_stub, 0x0                           ; dest: 0x00004c
        movlw   0xc8
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    settings_load_eeprom, 0x0                           ; dest: 0x000a46

        ; ---------------------------------------------------------------
        ; V1.71 inline (V1.61b): preset boot init
        ; ---------------------------------------------------------------
        ; Read persisted preset byte from EEPROM slot 0x74 and reflect
        ; it into control_flags.PRESET_BIT so the rest of the boot path
        ; sees the last-saved preset state.  EEPROM byte 0x01 means
        ; preset B; any other value (typically 0x00 or erased 0xFF) is
        ; preset A.  The IR dispatch inline helper
        ; (v171_send_preset_frame_and_persist) writes the same encoding.
        movlw   EEPROM_PRESET_STATE_ADDR                      ; 0x74
        call    eeprom_read_byte, 0x0
        bcf     control_flags, PRESET_BIT, A                 ; default = preset A
        xorlw   0x01
        bnz     v171_preset_boot_init_done
        bsf     control_flags, PRESET_BIT, A                 ; byte was 0x01 → preset B
v171_preset_boot_init_done:

        movlw   0x01
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0xf4
        call    control_core_service_01BE, 0x0                           ; dest: 0x0001be
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movlw   HIGH(lcd_str_firmware_v)                          ; shifted via label
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   LOW(lcd_str_firmware_v)                           ; shifted via label
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        call    lcd_string_write_rom, 0x0                           ; dest: 0x0000dc
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0x01
        call    delay_short_loop, 0x0                           ; dest: 0x000078
        movlw   0x2e
        call    lcd_char_write, 0x0                           ; dest: 0x0000ec
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0x06
        call    delay_short_loop, 0x0                           ; dest: 0x000078
        movlw   0x03
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0xe8
        call    control_core_service_01BE, 0x0                           ; dest: 0x0001be
        movlw   0x80
        movwf   0xb8, B                                     ; reg: 0x0b8
        movwf   0xb9, B                                     ; reg: 0x0b9
        movwf   0xa7, B                                     ; reg: 0x0a7
        movwf   0xa1, B                                     ; reg: 0x0a1
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movlw   HIGH(lcd_str_waiting_for_dlcp)                          ; shifted via label
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   LOW(lcd_str_waiting_for_dlcp)                           ; shifted via label
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        call    lcd_string_write_rom, 0x0                           ; dest: 0x0000dc
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bsf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        movlw   0x0f
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0xa0
        call    control_core_service_01BE, 0x0                           ; dest: 0x0001be

flow_ccs_0FA0_118C:                                                  ; address: 0x00118c

        call    poll_frame_send, 0x0                           ; dest: 0x000b64
        movlw   0xc8
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    rx_parser_entry, 0x0                           ; dest: 0x00044a
        movlw   0x80
        subwf   0xb8, W, B                                  ; reg: 0x0b8
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        movlw   0x80
        subwf   0xb9, W, B                                  ; reg: 0x0b9
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        andwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        movlw   0x80
        subwf   0xa7, W, B                                  ; reg: 0x0a7
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        andwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        movlw   0x80
        subwf   0xa1, W, B                                  ; reg: 0x0a1
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        andwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_ccs_0FA0_118C                                   ; dest: 0x00118c
        movlw   0x61
        movwf   0x9d, B                                     ; reg: 0x09d
        movlw   0xea
        movwf   0x9e, B                                     ; reg: 0x09e
        clrf    0x9f, B                                     ; reg: 0x09f
        clrf    0xa0, B                                     ; reg: 0x0a0
        bcf     control_flags, 0x5, A                   ; reg: 0x01f
        movlw   0x01
        movwf   (Common_RAM + 50), A                        ; reg: 0x032

post_connect_init:                                                  ; address: 0x0011d8

        btfss   control_flags, 0x1, A                   ; reg: 0x01f
        goto    flow_display_state_entry_1250                                   ; dest: 0x001250

flow_post_connect_init_11DE:                                                  ; address: 0x0011de

        bcf     control_flags, 0x3, A                   ; reg: 0x01f
        movf    0xbf, F, B                                  ; reg: 0x0bf
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_post_connect_init_11F0                                   ; dest: 0x0011f0
        call    control_core_service_12D0, 0x0                           ; dest: 0x0012d0
        goto    flow_boot_handshake_wait_120A                                   ; dest: 0x00120a

flow_post_connect_init_11F0:                                                  ; address: 0x0011f0

        decfsz  0xbf, W, B                                  ; reg: 0x0bf
        goto    boot_handshake_wait                                   ; dest: 0x0011fe
        call    control_core_service_1912, 0x0                           ; dest: 0x001912
        goto    flow_boot_handshake_wait_120A                                   ; dest: 0x00120a

boot_handshake_wait:                                                  ; address: 0x0011fe

        movlw   0x02
        cpfseq  0xbf, B                                     ; reg: 0x0bf
        goto    flow_boot_handshake_wait_120A                                   ; dest: 0x00120a
        call    control_core_service_13FE, 0x0                           ; dest: 0x0013fe

flow_boot_handshake_wait_120A:                                                  ; address: 0x00120a

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x5, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_display_state_entry_1226                                   ; dest: 0x001226
        movlw   0x02
        cpfseq  0xbf, B                                     ; reg: 0x0bf
        goto    display_state_entry                                   ; dest: 0x001224
        clrf    0xbf, B                                     ; reg: 0x0bf
        goto    flow_display_state_entry_1226                                   ; dest: 0x001226

display_state_entry:                                                  ; address: 0x001224

        incf    0xbf, F, B                                  ; reg: 0x0bf

flow_display_state_entry_1226:                                                  ; address: 0x001226

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x4, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_display_state_entry_1244                                   ; dest: 0x001244
        movf    0xbf, F, B                                  ; reg: 0x0bf
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_display_state_entry_1242                                   ; dest: 0x001242
        movlw   0x02
        movwf   0xbf, B                                     ; reg: 0x0bf
        goto    flow_display_state_entry_1244                                   ; dest: 0x001244

flow_display_state_entry_1242:                                                  ; address: 0x001242

        decf    0xbf, F, B                                  ; reg: 0x0bf

flow_display_state_entry_1244:                                                  ; address: 0x001244

        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        btfsc   control_flags, 0x1, A                   ; reg: 0x01f
        bra     flow_post_connect_init_11DE                                   ; dest: 0x0011de
        goto    flow_reconnect_wait_loop_12CE                                   ; dest: 0x0012ce

flow_display_state_entry_1250:                                                  ; address: 0x001250

        bcf     control_flags, 0x1, A                   ; reg: 0x01f
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

flow_display_state_entry_126E:                                                  ; address: 0x00126e

        call    display_loop_iteration, 0x0                           ; dest: 0x000cb2
        bcf     control_flags, 0x3, A                   ; reg: 0x01f
        movlw   0x00
        movf    0x9a, F, B                                  ; reg: 0x09a
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   control_flags, 0x1, A                   ; reg: 0x01f
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_display_state_entry_126E                                   ; dest: 0x00126e
        clrf    0xb3, B                                     ; reg: 0x0b3
        clrf    0xb2, B                                     ; reg: 0x0b2
        clrf    0xb1, B                                     ; reg: 0x0b1
        clrf    0xb0, B                                     ; reg: 0x0b0
        bsf     control_flags, 0x1, A                   ; reg: 0x01f
        call    standby_wake_broadcast, 0x0                           ; dest: 0x000c98
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movlw   HIGH(lcd_str_waiting_for_dlcp_alt)                          ; shifted via label
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   LOW(lcd_str_waiting_for_dlcp_alt)                           ; shifted via label
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        call    lcd_string_write_rom, 0x0                           ; dest: 0x0000dc
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bsf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        movlw   0x13
        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        movlw   0x88
        call    control_core_service_01BE, 0x0                           ; dest: 0x0001be
        bcf     control_flags, 0x1, A                   ; reg: 0x01f

reconnect_wait_loop:                                                  ; address: 0x0012bc

        call    poll_frame_send, 0x0                           ; dest: 0x000b64
        movlw   0xc8
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    rx_parser_entry, 0x0                           ; dest: 0x00044a
        btfss   control_flags, 0x1, A                   ; reg: 0x01f
        bra     reconnect_wait_loop                                   ; dest: 0x0012bc

flow_reconnect_wait_loop_12CE:                                                  ; address: 0x0012ce

        bra     post_connect_init                                   ; dest: 0x0011d8

control_core_service_12D0:                                               ; address: 0x0012d0

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movff   0x0bf, tx_data_staging                    ; reg2: 0x027
        movlw   HIGH(menu_title_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_title_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        call    control_core_service_0940, 0x0                           ; dest: 0x000940

standby_display:                                                  ; address: 0x0012e8

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0x87
        call    lcd_command, 0x0                           ; dest: 0x000066
        btfsc   control_flags, 0x5, A                   ; reg: 0x01f
        goto    flow_standby_display_1354                                   ; dest: 0x001354
        movlw   0x60
        cpfslt  0xb9, B                                     ; reg: 0x0b9
        goto    flow_standby_display_1310                                   ; dest: 0x001310
        movlw   0x2d
        call    lcd_char_write, 0x0                           ; dest: 0x0000ec
        movf    0xb9, W, B                                  ; reg: 0x0b9
        sublw   0x60
        movwf   tx_data_staging, A                        ; reg: 0x027
        goto    flow_standby_display_132E                                   ; dest: 0x00132e

flow_standby_display_1310:                                                  ; address: 0x001310

        movlw   0x60
        cpfseq  0xb9, B                                     ; reg: 0x0b9
        goto    flow_standby_display_1322                                   ; dest: 0x001322
        movlw   0x60
        subwf   0xb9, W, B                                  ; reg: 0x0b9
        movwf   tx_data_staging, A                        ; reg: 0x027
        goto    flow_standby_display_132E                                   ; dest: 0x00132e

flow_standby_display_1322:                                                  ; address: 0x001322

        movlw   0x2b
        call    lcd_char_write, 0x0                           ; dest: 0x0000ec
        movlw   0x60
        subwf   0xb9, W, B                                  ; reg: 0x0b9
        movwf   tx_data_staging, A                        ; reg: 0x027

flow_standby_display_132E:                                                  ; address: 0x00132e

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movf    tx_data_staging, W, A                     ; reg: 0x027
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
        goto    flow_standby_display_1360                                   ; dest: 0x001360

flow_standby_display_1354:                                                  ; address: 0x001354

        movlw   HIGH(lcd_str_mute)                          ; shifted via label
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   LOW(lcd_str_mute)                           ; shifted via label
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        call    lcd_string_write_rom, 0x0                           ; dest: 0x0000dc

flow_standby_display_1360:                                                  ; address: 0x001360

        movff   0x0b7, tx_data_staging                    ; reg2: 0x027
        movlw   HIGH(menu_input_auto_detect_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_input_auto_detect_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc0
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    control_core_service_0940, 0x0                           ; dest: 0x000940

        ; ---------------------------------------------------------------
        ; V1.71 inline (V1.61b): preset A/B indicator at row 0 column 15
        ; ---------------------------------------------------------------
        ; Before the per-frame display_loop_iteration call, write either
        ; 'A' or 'B' at the rightmost column of the top LCD row based on
        ; control_flags.PRESET_BIT.  0x8F = LCD DDRAM command for
        ; (row 0, col 15).  This is the same code the V1.61b binary
        ; overlay's volume_indicator_stub emitted, but inlined here so
        ; the Volume / Input-type screen render loop flows without a
        ; jump-out hook.
        movlw   0x80
        movwf   (Common_RAM + 1), A                    ; LCD command mode
        movlw   0x8F                                   ; row 0, col 15
        call    lcd_command, 0x0
        movlw   'A'
        btfsc   control_flags, PRESET_BIT, A
        movlw   'B'
        call    lcd_char_write, 0x0

        call    display_loop_iteration, 0x0                           ; dest: 0x000cb2
        rrcf    0x9a, W, B                                  ; reg: 0x09a
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_standby_display_1398                                   ; dest: 0x001398
        movlw   0x72
        cpfslt  0xb9, B                                     ; reg: 0x0b9
        goto    flow_standby_display_1392                                   ; dest: 0x001392
        incf    0xb9, F, B                                  ; reg: 0x0b9

flow_standby_display_1392:                                                  ; address: 0x001392

        bcf     control_flags, 0x5, A                   ; reg: 0x01f
        call    volume_frame_send, 0x0                           ; dest: 0x000c40

flow_standby_display_1398:                                                  ; address: 0x001398

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x2, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_standby_display_13B4                                   ; dest: 0x0013b4
        movf    0xb9, F, B                                  ; reg: 0x0b9
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_standby_display_13AE                                   ; dest: 0x0013ae
        decf    0xb9, F, B                                  ; reg: 0x0b9

flow_standby_display_13AE:                                                  ; address: 0x0013ae

        bcf     control_flags, 0x5, A                   ; reg: 0x01f
        call    volume_frame_send, 0x0                           ; dest: 0x000c40

flow_standby_display_13B4:                                                  ; address: 0x0013b4

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x3, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_standby_display_13CE                                   ; dest: 0x0013ce
        btg     control_flags, 0x5, A                   ; reg: 0x01f
        movlw   0x2f
        movwf   0xb4, B                                     ; reg: 0x0b4
        movlw   0x75
        movwf   0xb5, B                                     ; reg: 0x0b5
        call    mute_frame_send, 0x0                           ; dest: 0x000c7c

flow_standby_display_13CE:                                                  ; address: 0x0013ce

        bcf     control_flags, 0x3, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   0x9a, 0x5, B                                ; reg: 0x09a
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   0x9a, 0x4, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        movlw   0x01
        btfsc   control_flags, 0x1, A                   ; reg: 0x01f
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

control_core_service_13FE:                                               ; address: 0x0013fe

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movff   0x0bf, tx_data_staging                    ; reg2: 0x027
        movlw   HIGH(menu_title_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_title_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        call    control_core_service_0940, 0x0                           ; dest: 0x000940
        movff   0x0ba, tx_data_staging                    ; reg2: 0x027
        movlw   HIGH(menu_setup_bl_timeout_entry)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_setup_bl_timeout_entry)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movff   0x0ba, 0x0a5
        clrf    0xa4, B                                     ; reg: 0x0a4
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc0
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    control_core_service_0940, 0x0                           ; dest: 0x000940
        call    display_loop_iteration, 0x0                           ; dest: 0x000cb2
        btfss   control_flags, 0x3, A                   ; reg: 0x01f
        goto    flow_ccs_13FE_1442                                   ; dest: 0x001442
        bcf     control_flags, 0x3, A                   ; reg: 0x01f

flow_ccs_13FE_1442:                                                  ; address: 0x001442

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x3, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_ccs_13FE_1452                                   ; dest: 0x001452
        call    main_event_loop, 0x0                           ; dest: 0x00150e

flow_ccs_13FE_1452:                                                  ; address: 0x001452

        movlw   0x01
        btfsc   control_flags, 0x1, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   0x9a, 0x3, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   0x9a, 0x5, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   0x9a, 0x4, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     control_core_service_13FE                                ; dest: 0x0013fe
        return  0x0

control_core_service_1478:                                               ; address: 0x001478

        decfsz  0xeb, W, B                                  ; reg: 0x0eb
        goto    flow_ccs_1478_1490                                   ; dest: 0x001490
        clrf    0xef, B                                     ; reg: 0x0ef
        movlw   0x08
        movwf   0xee, B                                     ; reg: 0x0ee
        movlw   0x91
        movwf   0xed, B                                     ; reg: 0x0ed
        movlw   0x3a
        movwf   0xec, B                                     ; reg: 0x0ec
        goto    flow_ccs_1478_14CC                                   ; dest: 0x0014cc

flow_ccs_1478_1490:                                                  ; address: 0x001490

        movlw   0x02
        cpfseq  0xeb, B                                     ; reg: 0x0eb
        goto    flow_ccs_1478_14AA                                   ; dest: 0x0014aa
        clrf    0xef, B                                     ; reg: 0x0ef
        movlw   0x22
        movwf   0xee, B                                     ; reg: 0x0ee
        movlw   0x44
        movwf   0xed, B                                     ; reg: 0x0ed
        movlw   0xeb
        movwf   0xec, B                                     ; reg: 0x0ec
        goto    flow_ccs_1478_14CC                                   ; dest: 0x0014cc

flow_ccs_1478_14AA:                                                  ; address: 0x0014aa

        movlw   0x03
        cpfseq  0xeb, B                                     ; reg: 0x0eb
        goto    flow_ccs_1478_14C4                                   ; dest: 0x0014c4
        clrf    0xef, B                                     ; reg: 0x0ef
        movlw   0x55
        movwf   0xee, B                                     ; reg: 0x0ee
        movlw   0xac
        movwf   0xed, B                                     ; reg: 0x0ed
        movlw   0x44
        movwf   0xec, B                                     ; reg: 0x0ec
        goto    flow_ccs_1478_14CC                                   ; dest: 0x0014cc

flow_ccs_1478_14C4:                                                  ; address: 0x0014c4

        clrf    0xef, B                                     ; reg: 0x0ef
        clrf    0xee, B                                     ; reg: 0x0ee
        clrf    0xed, B                                     ; reg: 0x0ed
        clrf    0xec, B                                     ; reg: 0x0ec

flow_ccs_1478_14CC:                                                  ; address: 0x0014cc

        return  0x0
        tstfsz  (Common_RAM + 79), A                        ; reg: 0x04f
        addwfc  0x66, W, A                                  ; reg: 0xf66
        movwf   (Common_RAM + 40), A                        ; reg: 0x028
        addwfc  0x6f, W, A                                  ; reg: 0xf6f
        setf    0x74, B                                     ; reg: 0x074
        cpfsgt  0x6d, B                                     ; reg: 0x06d
        btg     0x6f, 0x2, B                                ; reg: 0x06f
        incf    0x74, W, B                                  ; reg: 0x074
        rrcf    (Common_RAM + 51), W, A                     ; reg: 0x033
        btg     (Common_RAM + 32), 0x1, B                   ; reg: 0x020
        cpfseq  0x65, B                                     ; reg: 0x065
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 50), W, A                     ; reg: 0x032
        setf    0x6d, B                                     ; reg: 0x06d
        addwfc  0x6e, W, A                                  ; reg: 0xf6e
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 32), W, A                     ; reg: 0x020
        addwfc  (Common_RAM + 53), W, A                     ; reg: 0x035
        setf    0x6d, B                                     ; reg: 0x06d
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
; (flow_ccs_0FA0_1092) completes. Per-iteration:
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
main_event_loop:                                               ; address: 0x00150e

        movff   0x0ba, tx_data_staging                    ; reg2: 0x027
        movlw   HIGH(menu_setup_bl_timeout_entry)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_setup_bl_timeout_entry)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    control_core_service_0940, 0x0                           ; dest: 0x000940
        movlw   0x03
        movwf   0xa4, B                                     ; reg: 0x0a4
        movlw   0x14
        movwf   0xa3, B                                     ; reg: 0x0a3
        movlw   0xce
        movwf   0xa2, B                                     ; reg: 0x0a2

flow_main_event_loop_1532:                                                  ; address: 0x001532

        movff   0x0eb, 0x0a5
        call    control_core_service_0FA0, 0x0                           ; dest: 0x000fa0
        bcf     control_flags, 0x3, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   0x9a, 0x1, B                                ; reg: 0x09a
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   0x9a, 0x2, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_main_event_loop_1558                                   ; dest: 0x001558
        movff   0x0a5, 0x0eb
        rcall   control_core_service_1478                                ; dest: 0x001478

flow_main_event_loop_1558:                                                  ; address: 0x001558

        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   0x9a, 0x3, B                                ; reg: 0x09a
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        movlw   0x01
        btfsc   control_flags, 0x1, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_main_event_loop_1532                                   ; dest: 0x001532
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

flow_main_event_loop_1642:                                                  ; address: 0x001642

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movff   0x0ba, tx_data_staging                    ; reg2: 0x027
        movlw   HIGH(menu_setup_bl_timeout_entry)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_setup_bl_timeout_entry)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        call    control_core_service_0940, 0x0                           ; dest: 0x000940

flow_main_event_loop_165A:                                                  ; address: 0x00165a

        movff   0x0c0, tx_data_staging                    ; reg2: 0x027
        movlw   HIGH(menu_source_channel_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_source_channel_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc0
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    control_core_service_0940, 0x0                           ; dest: 0x000940
        movlw   0x06
        cpfslt  0xc0, B                                     ; reg: 0x0c0
        goto    flow_main_event_loop_1718                                   ; dest: 0x001718
        movf    0xc0, F, B                                  ; reg: 0x0c0
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_main_event_loop_1692                                   ; dest: 0x001692
        lfsr    0x0, 0x0c1
        movf    0xba, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   0xa5, B                                     ; reg: 0x0a5
        goto    flow_main_event_loop_16FA                                   ; dest: 0x0016fa

flow_main_event_loop_1692:                                                  ; address: 0x001692

        decfsz  0xc0, W, B                                  ; reg: 0x0c0
        goto    flow_main_event_loop_16A6                                   ; dest: 0x0016a6
        lfsr    0x0, 0x0c7
        movf    0xba, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   0xa5, B                                     ; reg: 0x0a5
        goto    flow_main_event_loop_16FA                                   ; dest: 0x0016fa

flow_main_event_loop_16A6:                                                  ; address: 0x0016a6

        movlw   0x02
        cpfseq  0xc0, B                                     ; reg: 0x0c0
        goto    flow_main_event_loop_16BC                                   ; dest: 0x0016bc
        lfsr    0x0, 0x0cd
        movf    0xba, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   0xa5, B                                     ; reg: 0x0a5
        goto    flow_main_event_loop_16FA                                   ; dest: 0x0016fa

flow_main_event_loop_16BC:                                                  ; address: 0x0016bc

        movlw   0x03
        cpfseq  0xc0, B                                     ; reg: 0x0c0
        goto    flow_main_event_loop_16D2                                   ; dest: 0x0016d2
        lfsr    0x0, 0x0d3
        movf    0xba, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   0xa5, B                                     ; reg: 0x0a5
        goto    flow_main_event_loop_16FA                                   ; dest: 0x0016fa

flow_main_event_loop_16D2:                                                  ; address: 0x0016d2

        movlw   0x04
        cpfseq  0xc0, B                                     ; reg: 0x0c0
        goto    flow_main_event_loop_16E8                                   ; dest: 0x0016e8
        lfsr    0x0, 0x0d9
        movf    0xba, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   0xa5, B                                     ; reg: 0x0a5
        goto    flow_main_event_loop_16FA                                   ; dest: 0x0016fa

flow_main_event_loop_16E8:                                                  ; address: 0x0016e8

        movlw   0x05
        cpfseq  0xc0, B                                     ; reg: 0x0c0
        goto    flow_main_event_loop_16FA                                   ; dest: 0x0016fa
        lfsr    0x0, 0x0df
        movf    0xba, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   0xa5, B                                     ; reg: 0x0a5

flow_main_event_loop_16FA:                                                  ; address: 0x0016fa

        movlw   0x03                                        ; CMD standby/wake (data 00=standby 01=wake 02=mute_on 03=mute_off)
        movwf   0xa4, B                                     ; reg: 0x0a4
        movff   0x0a5, tx_data_staging                    ; reg2: 0x027
        movlw   HIGH(menu_routing_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_routing_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xcb
        call    lcd_command, 0x0                           ; dest: 0x000066
        goto    flow_main_event_loop_173C                                   ; dest: 0x00173c

flow_main_event_loop_1718:                                                  ; address: 0x001718

        lfsr    0x0, 0x0e5
        movf    0xba, W, B                                  ; reg: 0x0ba
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   0xa5, B                                     ; reg: 0x0a5
        movlw   0x01
        movwf   0xa4, B                                     ; reg: 0x0a4
        movff   0x0a5, tx_data_staging                    ; reg2: 0x027
        movlw   HIGH(menu_input_cat_spdif_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_input_cat_spdif_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc9
        call    lcd_command, 0x0                           ; dest: 0x000066

flow_main_event_loop_173C:                                                  ; address: 0x00173c

        call    control_core_service_0940, 0x0                           ; dest: 0x000940
        call    display_loop_iteration, 0x0                           ; dest: 0x000cb2
        btfss   control_flags, 0x3, A                   ; reg: 0x01f
        goto    flow_main_event_loop_1754                                   ; dest: 0x001754
        bcf     control_flags, 0x3, A                   ; reg: 0x01f
        btfss   control_flags, 0x1, A                   ; reg: 0x01f
        goto    flow_main_event_loop_1754                                   ; dest: 0x001754
        bra     flow_main_event_loop_1642                                   ; dest: 0x001642

flow_main_event_loop_1754:                                                  ; address: 0x001754

        rrcf    0x9a, W, B                                  ; reg: 0x09a
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_main_event_loop_1772                                   ; dest: 0x001772
        movf    0xa5, W, B                                  ; reg: 0x0a5
        cpfseq  0xa4, B                                     ; reg: 0x0a4
        goto    flow_main_event_loop_176C                                   ; dest: 0x00176c
        clrf    0xa5, B                                     ; reg: 0x0a5
        goto    flow_main_event_loop_176E                                   ; dest: 0x00176e

flow_main_event_loop_176C:                                                  ; address: 0x00176c

        incf    0xa5, F, B                                  ; reg: 0x0a5

flow_main_event_loop_176E:                                                  ; address: 0x00176e

        call    control_core_service_17E8, 0x0                           ; dest: 0x0017e8

flow_main_event_loop_1772:                                                  ; address: 0x001772

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x2, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_main_event_loop_1794                                   ; dest: 0x001794
        movf    0xa5, F, B                                  ; reg: 0x0a5
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_main_event_loop_178E                                   ; dest: 0x00178e
        movff   0x0a4, 0x0a5
        goto    flow_main_event_loop_1790                                   ; dest: 0x001790

flow_main_event_loop_178E:                                                  ; address: 0x00178e

        decf    0xa5, F, B                                  ; reg: 0x0a5

flow_main_event_loop_1790:                                                  ; address: 0x001790

        call    control_core_service_17E8, 0x0                           ; dest: 0x0017e8

flow_main_event_loop_1794:                                                  ; address: 0x001794

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x5, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_main_event_loop_17B0                                   ; dest: 0x0017b0
        movlw   0x06
        cpfseq  0xc0, B                                     ; reg: 0x0c0
        goto    flow_main_event_loop_17AE                                   ; dest: 0x0017ae
        clrf    0xc0, B                                     ; reg: 0x0c0
        goto    flow_main_event_loop_17B0                                   ; dest: 0x0017b0

flow_main_event_loop_17AE:                                                  ; address: 0x0017ae

        incf    0xc0, F, B                                  ; reg: 0x0c0

flow_main_event_loop_17B0:                                                  ; address: 0x0017b0

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x4, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_main_event_loop_17CE                                   ; dest: 0x0017ce
        movf    0xc0, F, B                                  ; reg: 0x0c0
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_main_event_loop_17CC                                   ; dest: 0x0017cc
        movlw   0x06
        movwf   0xc0, B                                     ; reg: 0x0c0
        goto    flow_main_event_loop_17CE                                   ; dest: 0x0017ce

flow_main_event_loop_17CC:                                                  ; address: 0x0017cc

        decf    0xc0, F, B                                  ; reg: 0x0c0

flow_main_event_loop_17CE:                                                  ; address: 0x0017ce

        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   0x9a, 0x3, B                                ; reg: 0x09a
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        movlw   0x01
        btfsc   control_flags, 0x1, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_main_event_loop_165A                                   ; dest: 0x00165a
        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        return  0x0

control_core_service_17E8:                                               ; address: 0x0017e8

        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        movlw   0x06
        cpfslt  0xc0, B                                     ; reg: 0x0c0
        goto    flow_ccs_17E8_1876                                   ; dest: 0x001876
        movf    0xc0, F, B                                  ; reg: 0x0c0
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_17E8_180A                                   ; dest: 0x00180a
        lfsr    0x0, 0x0c1
        movf    0xba, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb
        goto    flow_ccs_17E8_1872                                   ; dest: 0x001872

flow_ccs_17E8_180A:                                                  ; address: 0x00180a

        decfsz  0xc0, W, B                                  ; reg: 0x0c0
        goto    flow_ccs_17E8_181E                                   ; dest: 0x00181e
        lfsr    0x0, 0x0c7
        movf    0xba, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb
        goto    flow_ccs_17E8_1872                                   ; dest: 0x001872

flow_ccs_17E8_181E:                                                  ; address: 0x00181e

        movlw   0x02
        cpfseq  0xc0, B                                     ; reg: 0x0c0
        goto    flow_ccs_17E8_1834                                   ; dest: 0x001834
        lfsr    0x0, 0x0cd
        movf    0xba, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb
        goto    flow_ccs_17E8_1872                                   ; dest: 0x001872

flow_ccs_17E8_1834:                                                  ; address: 0x001834

        movlw   0x03
        cpfseq  0xc0, B                                     ; reg: 0x0c0
        goto    flow_ccs_17E8_184A                                   ; dest: 0x00184a
        lfsr    0x0, 0x0d3
        movf    0xba, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb
        goto    flow_ccs_17E8_1872                                   ; dest: 0x001872

flow_ccs_17E8_184A:                                                  ; address: 0x00184a

        movlw   0x04
        cpfseq  0xc0, B                                     ; reg: 0x0c0
        goto    flow_ccs_17E8_1860                                   ; dest: 0x001860
        lfsr    0x0, 0x0d9
        movf    0xba, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb
        goto    flow_ccs_17E8_1872                                   ; dest: 0x001872

flow_ccs_17E8_1860:                                                  ; address: 0x001860

        movlw   0x05
        cpfseq  0xc0, B                                     ; reg: 0x0c0
        goto    flow_ccs_17E8_1872                                   ; dest: 0x001872
        lfsr    0x0, 0x0df
        movf    0xba, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb

flow_ccs_17E8_1872:                                                  ; address: 0x001872

        goto    flow_ccs_17E8_1880                                   ; dest: 0x001880

flow_ccs_17E8_1876:                                                  ; address: 0x001876

        lfsr    0x0, 0x0e5
        movf    0xba, W, B                                  ; reg: 0x0ba
        movff   0x0a5, PLUSW0                               ; reg2: 0xfeb

flow_ccs_17E8_1880:                                                  ; address: 0x001880

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

control_core_service_1912:                                               ; address: 0x001912

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        call    lcd_command, 0x0                           ; dest: 0x000066
        movff   0x0bf, tx_data_staging                    ; reg2: 0x027
        movlw   HIGH(menu_title_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_title_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        call    control_core_service_0940, 0x0                           ; dest: 0x000940

flow_ccs_1912_192A:                                                  ; address: 0x00192a

        movff   0x0b7, tx_data_staging                    ; reg2: 0x027
        movlw   HIGH(menu_input_auto_detect_table)                          ; shifted via label
        movwf   (Common_RAM + 42), A                        ; reg: 0x02a
        movlw   LOW(menu_input_auto_detect_table)                           ; shifted via label
        movwf   (Common_RAM + 41), A                        ; reg: 0x029
        movff   0x0b7, 0x0a5
        movf    0xa1, F, B                                  ; reg: 0x0a1
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_1912_194A                                   ; dest: 0x00194a
        movlw   0x05
        movwf   0xa4, B                                     ; reg: 0x0a4
        goto    flow_ccs_1912_1974                                   ; dest: 0x001974

flow_ccs_1912_194A:                                                  ; address: 0x00194a

        decfsz  0xa1, W, B                                  ; reg: 0x0a1
        goto    flow_ccs_1912_1958                                   ; dest: 0x001958
        movlw   0x06
        movwf   0xa4, B                                     ; reg: 0x0a4
        goto    flow_ccs_1912_1974                                   ; dest: 0x001974

flow_ccs_1912_1958:                                                  ; address: 0x001958

        movlw   0x02
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_1912_1968                                   ; dest: 0x001968
        movlw   0x07
        movwf   0xa4, B                                     ; reg: 0x0a4
        goto    flow_ccs_1912_1974                                   ; dest: 0x001974

flow_ccs_1912_1968:                                                  ; address: 0x001968

        movlw   0x03
        cpfseq  0xa1, B                                     ; reg: 0x0a1
        goto    flow_ccs_1912_1974                                   ; dest: 0x001974
        movlw   0x08
        movwf   0xa4, B                                     ; reg: 0x0a4

flow_ccs_1912_1974:                                                  ; address: 0x001974

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xc0
        call    lcd_command, 0x0                           ; dest: 0x000066
        call    control_core_service_0940, 0x0                           ; dest: 0x000940
        call    display_loop_iteration, 0x0                           ; dest: 0x000cb2
        btfss   control_flags, 0x3, A                   ; reg: 0x01f
        goto    flow_ccs_1912_1996                                   ; dest: 0x001996
        bcf     control_flags, 0x3, A                   ; reg: 0x01f
        btfss   control_flags, 0x1, A                   ; reg: 0x01f
        goto    flow_ccs_1912_1996                                   ; dest: 0x001996
        bra     control_core_service_1912                                ; dest: 0x001912

flow_ccs_1912_1996:                                                  ; address: 0x001996

        rrcf    0x9a, W, B                                  ; reg: 0x09a
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        goto    flow_ccs_1912_19C0                                   ; dest: 0x0019c0
        movf    0xa5, W, B                                  ; reg: 0x0a5
        cpfseq  0xa4, B                                     ; reg: 0x0a4
        goto    flow_ccs_1912_19AE                                   ; dest: 0x0019ae
        clrf    0xa5, B                                     ; reg: 0x0a5
        goto    flow_ccs_1912_19B0                                   ; dest: 0x0019b0

flow_ccs_1912_19AE:                                                  ; address: 0x0019ae

        incf    0xa5, F, B                                  ; reg: 0x0a5

flow_ccs_1912_19B0:                                                  ; address: 0x0019b0

        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        movff   0x0a5, 0x0b7
        call    control_core_service_076A, 0x0                           ; dest: 0x00076a
        call    input_frame_send, 0x0                           ; dest: 0x000c22

flow_ccs_1912_19C0:                                                  ; address: 0x0019c0

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x2, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_ccs_1912_19EE                                   ; dest: 0x0019ee
        movf    0xa5, F, B                                  ; reg: 0x0a5
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_1912_19DC                                   ; dest: 0x0019dc
        movff   0x0a4, 0x0a5
        goto    flow_ccs_1912_19DE                                   ; dest: 0x0019de

flow_ccs_1912_19DC:                                                  ; address: 0x0019dc

        decf    0xa5, F, B                                  ; reg: 0x0a5

flow_ccs_1912_19DE:                                                  ; address: 0x0019de

        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        movff   0x0a5, 0x0b7
        call    control_core_service_076A, 0x0                           ; dest: 0x00076a
        call    input_frame_send, 0x0                           ; dest: 0x000c22

flow_ccs_1912_19EE:                                                  ; address: 0x0019ee

        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   0x9a, 0x5, B                                ; reg: 0x09a
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; reg: 0x018
        clrf    WREG, A                                     ; reg: 0xfe8
        btfsc   0x9a, 0x4, B                                ; reg: 0x09a
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        movlw   0x01
        btfsc   control_flags, 0x1, A                   ; reg: 0x01f
        clrf    WREG, A                                     ; reg: 0xfe8
        iorwf   (Common_RAM + 24), F, A                     ; reg: 0x018
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_ccs_1912_192A                                   ; dest: 0x00192a
        return  0x0

; --- V1.71 bootloader pin (app code may grow beyond stock extents) ---
        org     0x7800

bootloader_entry:                                                  ; address: 0x007800

        goto    flow_ccs_7ADA_7AFE                                   ; dest: 0x007afe

control_core_service_7804:                                               ; address: 0x007804

        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x03
        bra     flow_ccs_780A_780E                                   ; dest: 0x00780e

control_core_service_780A:                                               ; address: 0x00780a

        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x04

flow_ccs_780A_780E:                                                  ; address: 0x00780e

        movwf   (Common_RAM + 7), A                         ; reg: 0x007
        movf    (Common_RAM + 14), W, A                     ; reg: 0x00e
        subwf   (Common_RAM + 12), W, A                     ; reg: 0x00c
        bnz     flow_ccs_780A_781A
        movf    (Common_RAM + 13), W, A                     ; reg: 0x00d
        subwf   (Common_RAM + 11), W, A                     ; reg: 0x00b

flow_ccs_780A_781A:                                                  ; address: 0x00781a

        movlw   0x04
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        movlw   0x01
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x02
        andwf   (Common_RAM + 7), W, A                      ; reg: 0x007
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        movlw   0x01
        return  0x0

control_core_service_782C:                                               ; address: 0x00782c

        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0xfe
        rcall   control_core_service_7A34                                ; dest: 0x007a34
        movlw   0x01
        rcall   control_core_service_7A34                                ; dest: 0x007a34
        movlw   0x75
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movlw   0x30
        bra     control_core_service_7AC2                                ; dest: 0x007ac2

control_core_service_7840:                                               ; address: 0x007840

        clrf    (Common_RAM + 1), A                         ; reg: 0x001
        bsf     (Common_RAM + 1), 0x7, A                    ; reg: 0x001
        movwf   (Common_RAM + 22), A                        ; reg: 0x016
        movlw   0xfe
        rcall   control_core_service_7A34                                ; dest: 0x007a34
        movf    (Common_RAM + 22), W, A                     ; reg: 0x016
        bra     control_core_service_7A34                                ; dest: 0x007a34

control_core_service_784E:                                               ; address: 0x00784e

        clrf    (Common_RAM + 5), A                         ; reg: 0x005
        movlw   0x80
        movwf   (Common_RAM + 27), A                        ; reg: 0x01b
        bra     flow_ccs_784E_7856                                   ; dest: 0x007856

flow_ccs_784E_7856:                                                  ; address: 0x007856

        clrf    (Common_RAM + 15), A                        ; reg: 0x00f
        clrf    (Common_RAM + 16), A                        ; reg: 0x010
        clrf    (Common_RAM + 17), A                        ; reg: 0x011
        clrf    (Common_RAM + 17), A                        ; reg: 0x011
        bcf     (Common_RAM + 7), 0x5, A                    ; reg: 0x007

flow_ccs_784E_7860:                                                  ; address: 0x007860

        rcall   control_core_service_7A3C                                ; dest: 0x007a3c
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        addlw   0xd3
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     (Common_RAM + 7), 0x5, A                    ; reg: 0x007
        addlw   0x2d
        addlw   0xc6
        bc      flow_ccs_784E_7878
        addlw   0x0a
        bnc     flow_ccs_784E_7860
        bra     flow_ccs_784E_7882                                   ; dest: 0x007882

flow_ccs_784E_7878:                                                  ; address: 0x007878

        addlw   0xf3
        bc      flow_ccs_784E_7860
        addlw   0x06
        bnc     flow_ccs_784E_7860
        addlw   0x0a

flow_ccs_784E_7882:                                                  ; address: 0x007882

        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        movlw   0x04
        movwf   (Common_RAM + 14), A                        ; reg: 0x00e

flow_ccs_784E_7888:                                                  ; address: 0x007888

        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        rlcf    (Common_RAM + 15), F, A                     ; reg: 0x00f
        rlcf    (Common_RAM + 16), F, A                     ; reg: 0x010
        rlcf    (Common_RAM + 17), F, A                     ; reg: 0x011
        rlcf    (Common_RAM + 18), F, A                     ; reg: 0x012
        decfsz  (Common_RAM + 14), F, A                     ; reg: 0x00e
        bra     flow_ccs_784E_7888                                   ; dest: 0x007888
        movf    (Common_RAM + 13), W, A                     ; reg: 0x00d
        iorwf   (Common_RAM + 15), F, A                     ; reg: 0x00f
        decf    (Common_RAM + 5), F, A                      ; reg: 0x005
        bz      flow_ccs_784E_78BA
        rcall   control_core_service_7A3C                                ; dest: 0x007a3c
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        addlw   0xc6
        bc      flow_ccs_784E_78AE
        addlw   0x0a
        bnc     flow_ccs_784E_78BA
        bra     flow_ccs_784E_7882                                   ; dest: 0x007882

flow_ccs_784E_78AE:                                                  ; address: 0x0078ae

        addlw   0xf3
        bc      flow_ccs_784E_78BA
        addlw   0x06
        bnc     flow_ccs_784E_78BA
        addlw   0x0a
        bra     flow_ccs_784E_7882                                   ; dest: 0x007882

flow_ccs_784E_78BA:                                                  ; address: 0x0078ba

        btfss   (Common_RAM + 7), 0x5, A                    ; reg: 0x007
        bra     flow_ccs_784E_78D4                                   ; dest: 0x0078d4
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

flow_ccs_784E_78D4:                                                  ; address: 0x0078d4

        movf    (Common_RAM + 15), W, A                     ; reg: 0x00f
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        clrf    (Common_RAM + 5), A                         ; reg: 0x005

control_core_service_78DC:                                               ; address: 0x0078dc

        movwf   (Common_RAM + 15), A                        ; reg: 0x00f
        clrf    (Common_RAM + 16), A                        ; reg: 0x010
        bcf     Common_RAM, 0x3, A                          ; reg: 0x000
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bsf     Common_RAM, 0x3, A                          ; reg: 0x000
        movlw   0x04
        movwf   (Common_RAM + 4), A                         ; reg: 0x004
        swapf   (Common_RAM + 16), W, A                     ; reg: 0x010
        rcall   control_core_service_78FA                                ; dest: 0x0078fa
        movf    (Common_RAM + 16), W, A                     ; reg: 0x010
        rcall   control_core_service_78FA                                ; dest: 0x0078fa
        swapf   (Common_RAM + 15), W, A                     ; reg: 0x00f
        rcall   control_core_service_78FA                                ; dest: 0x0078fa
        movf    (Common_RAM + 15), W, A                     ; reg: 0x00f

control_core_service_78FA:                                               ; address: 0x0078fa

        andlw   0x0f
        addlw   0xf6
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        addlw   0x07
        addlw   0x0a
        bra     flow_ccs_78FA_7906                                   ; dest: 0x007906

flow_ccs_78FA_7906:                                                  ; address: 0x007906

        movwf   (Common_RAM + 11), A                        ; reg: 0x00b
        dcfsnz  (Common_RAM + 4), F, A                      ; reg: 0x004
        bcf     Common_RAM, 0x3, A                          ; reg: 0x000
        movf    (Common_RAM + 5), W, A                      ; reg: 0x005
        bz      flow_ccs_78FA_7916
        subwf   (Common_RAM + 4), W, A                      ; reg: 0x004
        btfsc   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        bra     flow_ccs_78FA_7924                                   ; dest: 0x007924

flow_ccs_78FA_7916:                                                  ; address: 0x007916

        movf    (Common_RAM + 11), W, A                     ; reg: 0x00b
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bcf     Common_RAM, 0x3, A                          ; reg: 0x000
        btfsc   Common_RAM, 0x3, A                          ; reg: 0x000
        bra     flow_ccs_78FA_7924                                   ; dest: 0x007924
        addlw   0x30
        bra     control_core_service_7A34                                ; dest: 0x007a34

flow_ccs_78FA_7924:                                                  ; address: 0x007924

        return  0x0

control_core_service_7926:                                               ; address: 0x007926

        movwf   (Common_RAM + 15), A                        ; reg: 0x00f

flow_ccs_7926_7928:                                                  ; address: 0x007928

        movf    (Common_RAM + 4), W, A                      ; reg: 0x004
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        return  0x0
        movff   (Common_RAM + 15), FSR0L                    ; reg1: 0x00f, reg2: 0xfe9
        movff   (Common_RAM + 16), FSR0H                    ; reg1: 0x010, reg2: 0xfea
        movf    INDF0, W, A                                 ; reg: 0xfef
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        return  0x0
        rcall   control_core_service_7A34                                ; dest: 0x007a34
        infsnz  (Common_RAM + 15), F, A                     ; reg: 0x00f
        incf    (Common_RAM + 16), F, A                     ; reg: 0x010
        decf    (Common_RAM + 4), F, A                      ; reg: 0x004
        bra     flow_ccs_7926_7928                                   ; dest: 0x007928

control_core_service_7946:                                               ; address: 0x007946

        clrf    EECON1, A                                   ; reg: 0xfa6
        bsf     EECON1, EEPGD, A                            ; reg: 0xfa6, bit: 7

flow_ccs_7946_794A:                                                  ; address: 0x00794a

        tblrd*+
        movf    TABLAT, W, A                                ; reg: 0xff5
        bz      flow_ccs_7946_7954
        rcall   control_core_service_7956                                ; dest: 0x007956
        bra     flow_ccs_7946_794A                                   ; dest: 0x00794a

flow_ccs_7946_7954:                                                  ; address: 0x007954

        return  0x0

control_core_service_7956:                                               ; address: 0x007956

        movwf   (Common_RAM + 20), A                        ; reg: 0x014
        bcf     LATB, LATB4, A                              ; reg: 0xf8a, bit: 4
        bcf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        bcf     TRISB, RB4, A                               ; reg: 0xf93, bit: 4
        bcf     TRISA, RA5, A                               ; reg: 0xf92, bit: 5
        movlw   0xf0
        andwf   TRISB, F, A                                 ; reg: 0xf93
        movf    (Common_RAM + 20), W, A                     ; reg: 0x014
        btfsc   Common_RAM, 0x1, A                          ; reg: 0x000
        bra     flow_ccs_79A4_79A6                                   ; dest: 0x0079a6
        movlw   0x3a
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movlw   0x98
        rcall   control_core_service_7AC2                                ; dest: 0x007ac2
        movlw   0x33
        movwf   (Common_RAM + 19), A                        ; reg: 0x013
        rcall   control_core_service_79CC                                ; dest: 0x0079cc
        movlw   0x13
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movlw   0x88
        rcall   control_core_service_7AC2                                ; dest: 0x007ac2
        rcall   control_core_service_79CC                                ; dest: 0x0079cc
        movlw   0x64
        rcall   control_core_service_7AC0                                ; dest: 0x007ac0
        rcall   control_core_service_79CC                                ; dest: 0x0079cc
        movlw   0x64
        rcall   control_core_service_7AC0                                ; dest: 0x007ac0
        movlw   0x22
        movwf   (Common_RAM + 19), A                        ; reg: 0x013
        rcall   control_core_service_79CC                                ; dest: 0x0079cc
        movlw   0x28
        rcall   control_core_service_79A4                                ; dest: 0x0079a4
        movlw   0x0c
        rcall   control_core_service_79A4                                ; dest: 0x0079a4
        movlw   0x06
        rcall   control_core_service_79A4                                ; dest: 0x0079a4
        bsf     Common_RAM, 0x1, A                          ; reg: 0x000
        movf    (Common_RAM + 20), W, A                     ; reg: 0x014
        bra     flow_ccs_79A4_79A6                                   ; dest: 0x0079a6

control_core_service_79A4:                                               ; address: 0x0079a4

        bsf     Common_RAM, 0x0, A                          ; reg: 0x000

flow_ccs_79A4_79A6:                                                  ; address: 0x0079a6

        movwf   (Common_RAM + 19), A                        ; reg: 0x013
        btfss   Common_RAM, 0x0, A                          ; reg: 0x000
        bra     flow_ccs_79A4_79C0                                   ; dest: 0x0079c0
        bcf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5
        sublw   0x03
        bnc     control_core_service_79C8
        rcall   control_core_service_79C8                                ; dest: 0x0079c8
        movlw   0x07
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movlw   0xd0
        rcall   control_core_service_7AC2                                ; dest: 0x007ac2
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

flow_ccs_79A4_79C0:                                                  ; address: 0x0079c0

        bsf     Common_RAM, 0x0, A                          ; reg: 0x000
        sublw   0xfe
        bz      flow_ccs_79CC_79E8
        bsf     LATA, LATA5, A                              ; reg: 0xf89, bit: 5

control_core_service_79C8:                                               ; address: 0x0079c8

        swapf   (Common_RAM + 19), F, A                     ; reg: 0x013
        btfss   Common_RAM, 0x0, A                          ; reg: 0x000

control_core_service_79CC:                                               ; address: 0x0079cc

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
        bra     control_core_service_79CC                                ; dest: 0x0079cc
        movlw   0x32
        rcall   control_core_service_7AC0                                ; dest: 0x007ac0
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0

flow_ccs_79CC_79E8:                                                  ; address: 0x0079e8

        movf    (Common_RAM + 20), W, A                     ; reg: 0x014
        return  0x0

control_core_service_79EC:                                               ; address: 0x0079ec

        btfsc   RCSTA, OERR, A                              ; reg: 0xfab, bit: 1
        bcf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        bsf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        movff   (Common_RAM + 2), (Common_RAM + 11)         ; reg1: 0x002, reg2: 0x00b
        movff   (Common_RAM + 6), (Common_RAM + 12)         ; reg1: 0x006, reg2: 0x00c
        clrf    (Common_RAM + 13), A                        ; reg: 0x00d
        clrf    (Common_RAM + 14), A                        ; reg: 0x00e

flow_ccs_79EC_79FE:                                                  ; address: 0x0079fe

        nop
        bra     flow_ccs_79EC_7A02                                   ; dest: 0x007a02

flow_ccs_79EC_7A02:                                                  ; address: 0x007a02

        nop
        btfsc   PIR1, RCIF, A                               ; reg: 0xf9e, bit: 5
        bra     flow_ccs_79EC_7A24                                   ; dest: 0x007a24
        setf    WREG, A                                     ; reg: 0xfe8
        addwf   (Common_RAM + 13), F, A                     ; reg: 0x00d
        addwfc  (Common_RAM + 14), F, A                     ; reg: 0x00e
        addwfc  (Common_RAM + 11), F, A                     ; reg: 0x00b
        addwfc  (Common_RAM + 12), F, A                     ; reg: 0x00c
        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        infsnz  (Common_RAM + 13), W, A                     ; reg: 0x00d
        incfsz  (Common_RAM + 14), W, A                     ; reg: 0x00e
        bra     flow_ccs_79EC_79FE                                   ; dest: 0x0079fe
        movlw   0xb7
        movwf   (Common_RAM + 13), A                        ; reg: 0x00d
        clrf    (Common_RAM + 14), A                        ; reg: 0x00e
        bra     flow_ccs_79EC_7A02                                   ; dest: 0x007a02

flow_ccs_79EC_7A24:                                                  ; address: 0x007a24

        movf    RCREG, W, A                                 ; reg: 0xfae
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

control_core_service_7A2A:                                               ; address: 0x007a2a

        btfss   PIR1, TXIF, A                               ; reg: 0xf9e, bit: 4
        bra     control_core_service_7A2A                                ; dest: 0x007a2a
        movwf   TXREG, A                                    ; reg: 0xfad
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0

control_core_service_7A34:                                               ; address: 0x007a34

        btfsc   (Common_RAM + 1), 0x7, A                    ; reg: 0x001
        bra     control_core_service_7956                                ; dest: 0x007956
        btfsc   (Common_RAM + 1), 0x2, A                    ; reg: 0x001
        bra     control_core_service_7A2A                                ; dest: 0x007a2a

control_core_service_7A3C:                                               ; address: 0x007a3c

        movf    (Common_RAM + 27), F, A                     ; reg: 0x01b
        bz      control_core_service_79EC
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0
        btfsc   (Common_RAM + 27), 0x7, A                   ; reg: 0x01b
        movf    POSTINC0, W, A                              ; reg: 0xfee
        return  0x0

control_core_service_7A48:                                               ; address: 0x007a48

        movwf   EEADR, A                                    ; reg: 0xfa9
        clrf    EECON1, A                                   ; reg: 0xfa6
        bsf     EECON1, RD, A                               ; reg: 0xfa6, bit: 0
        movf    EEDATA, W, A                                ; reg: 0xfa8
        incf    EEADR, F, A                                 ; reg: 0xfa9
        return  0x0

control_core_service_7A54:                                               ; address: 0x007a54

        movwf   EEDATA, A                                   ; reg: 0xfa8
        clrf    EECON1, A                                   ; reg: 0xfa6
        bsf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        movlw   0x55
        movwf   EECON2, A                                   ; reg: 0xfa7
        movlw   0xaa
        movwf   EECON2, A                                   ; reg: 0xfa7
        bsf     EECON1, WR, A                               ; reg: 0xfa6, bit: 1

flow_ccs_7A54_7A64:                                                  ; address: 0x007a64

        btfsc   EECON1, WR, A                               ; reg: 0xfa6, bit: 1
        bra     flow_ccs_7A54_7A64                                   ; dest: 0x007a64
        bcf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2
        incf    EEADR, F, A                                 ; reg: 0xfa9
        return  0x0

control_core_service_7A6E:                                               ; address: 0x007a6e

        movwf   TABLAT, A                                   ; reg: 0xff5
        tblwt*
        incf    TBLPTRL, W, A                               ; reg: 0xff6
        andlw   0x1f
        bnz     flow_ccs_7A6E_7A8A
        movlw   0x84
        movwf   EECON1, A                                   ; reg: 0xfa6
        movlw   0x55
        movwf   EECON2, A                                   ; reg: 0xfa7
        movlw   0xaa
        movwf   EECON2, A                                   ; reg: 0xfa7
        bsf     EECON1, WR, A                               ; reg: 0xfa6, bit: 1
        bra     flow_ccs_7A6E_7A88                                   ; dest: 0x007a88

flow_ccs_7A6E_7A88:                                                  ; address: 0x007a88

        bcf     EECON1, WREN, A                             ; reg: 0xfa6, bit: 2

flow_ccs_7A6E_7A8A:                                                  ; address: 0x007a8a

        infsnz  TBLPTRL, F, A                               ; reg: 0xff6
        incf    TBLPTRH, F, A                               ; reg: 0xff7
        return  0x0

control_core_service_7A90:                                               ; address: 0x007a90

        movwf   TBLPTRL, A                                  ; reg: 0xff6

control_core_service_7A92:                                               ; address: 0x007a92

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

control_core_service_7AA6:                                               ; address: 0x007aa6

        clrf    (Common_RAM + 14), A                        ; reg: 0x00e

control_core_service_7AA8:                                               ; address: 0x007aa8

        movwf   (Common_RAM + 13), A                        ; reg: 0x00d

flow_ccs_7AA8_7AAA:                                                  ; address: 0x007aaa

        movlw   0xff
        addwf   (Common_RAM + 13), F, A                     ; reg: 0x00d
        addwfc  (Common_RAM + 14), F, A                     ; reg: 0x00e
        bra     flow_ccs_7AA8_7AB2                                   ; dest: 0x007ab2

flow_ccs_7AA8_7AB2:                                                  ; address: 0x007ab2

        btfss   STATUS, C, A                                ; reg: 0xfd8, bit: 0
        return  0x0
        movlw   0x03
        movwf   (Common_RAM + 12), A                        ; reg: 0x00c
        movlw   0xe5
        rcall   control_core_service_7AC2                                ; dest: 0x007ac2
        bra     flow_ccs_7AA8_7AAA                                   ; dest: 0x007aaa

control_core_service_7AC0:                                               ; address: 0x007ac0

        clrf    (Common_RAM + 12), A                        ; reg: 0x00c

control_core_service_7AC2:                                               ; address: 0x007ac2

        addlw   0xfa
        movwf   (Common_RAM + 11), A                        ; reg: 0x00b
        nop
        bnc     flow_ccs_7AC2_7AD0
        bra     flow_ccs_7AC2_7ACC                                   ; dest: 0x007acc

flow_ccs_7AC2_7ACC:                                                  ; address: 0x007acc

        decf    (Common_RAM + 11), F, A                     ; reg: 0x00b
        bc      flow_ccs_7AC2_7ACC

flow_ccs_7AC2_7AD0:                                                  ; address: 0x007ad0

        decf    (Common_RAM + 11), F, A                     ; reg: 0x00b
        decf    (Common_RAM + 12), F, A                     ; reg: 0x00c
        bc      flow_ccs_7AC2_7ACC
        nop
        return  0x0

control_core_service_7ADA:                                               ; address: 0x007ada

        dcfsnz  PRODL, F, A                                 ; reg: 0xff3
        bra     flow_ccs_7ADA_7AE2                                   ; dest: 0x007ae2
        movf    POSTINC1, F, A                              ; reg: 0xfe6
        bra     control_core_service_7ADA                                ; dest: 0x007ada

flow_ccs_7ADA_7AE2:                                                  ; address: 0x007ae2

        movff   POSTINC1, POSTINC0                          ; reg1: 0xfe6, reg2: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     flow_ccs_7ADA_7AE2                                   ; dest: 0x007ae2
        return  0x0
        movwf   (Common_RAM + 66), B                        ; reg: 0x042
        btg     0x6f, 0x2, A                                ; reg: 0xf6f
        movwf   0x6c, B                                     ; reg: 0x06c
        cpfsgt  0x61, A                                     ; reg: 0xf61
        btg     0x65, 0x1, A                                ; reg: 0xf65
        negf    (Common_RAM + 32), B                        ; reg: 0x020
        cpfsgt  0x6f, A                                     ; reg: 0xf6f
        addwfc  0x65, W, A                                  ; reg: 0xf65
        nop

flow_ccs_7ADA_7AFE:                                                  ; address: 0x007afe

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
        rcall   control_core_service_7AA6                                ; dest: 0x007aa6
        movlw   0x46
        movwf   0x76, B                                     ; reg: 0x076
        movlw   0x57
        movwf   0x77, B                                     ; reg: 0x077
        movlw   0x5f
        movwf   0x78, B                                     ; reg: 0x078
        movlw   0x55
        movwf   0x79, B                                     ; reg: 0x079
        movlw   0x70
        movwf   0x7a, B                                     ; reg: 0x07a
        movlw   0x64
        movwf   0x7b, B                                     ; reg: 0x07b
        bcf     TRISB, RB6, A                               ; reg: 0xf93, bit: 6
        bcf     LATB, LATB6, A                              ; reg: 0xf8a, bit: 6
        bcf     0x82, 0x1, B                                ; reg: 0x082
        rcall   bootloader_manual_entry                                ; dest: 0x007f02
        rrcf    0x82, W, B                                  ; reg: 0x082
        rrcf    WREG, F, A                                  ; reg: 0xfe8
        bc      flow_ccs_7ADA_7B7C
        movlw   0xff
        rcall   control_core_service_7A48                                ; dest: 0x007a48
        movwf   control_flags, A                        ; reg: 0x01f
        decfsz  control_flags, W, A                     ; reg: 0x01f
        bra     flow_ccs_7ADA_7B68                                   ; dest: 0x007b68
        setf    EEADR, A                                    ; reg: 0xfa9
        movlw   0x77
        rcall   control_core_service_7A54                                ; dest: 0x007a54
        goto    flow_local_0040                                   ; dest: 0x000040
        bra     flow_ccs_7ADA_7B7A                                   ; dest: 0x007b7a

flow_ccs_7ADA_7B68:                                                  ; address: 0x007b68

        movlw   0x02
        cpfseq  control_flags, A                        ; reg: 0x01f
        bra     flow_ccs_7ADA_7B7A                                   ; dest: 0x007b7a
        movlw   0xfe
        movwf   EEADR, A                                    ; reg: 0xfa9
        movlw   0x01
        rcall   control_core_service_7A54                                ; dest: 0x007a54
        goto    flow_local_0040                                   ; dest: 0x000040

flow_ccs_7ADA_7B7A:                                                  ; address: 0x007b7a

        bra     flow_ccs_7ADA_7B82                                   ; dest: 0x007b82

flow_ccs_7ADA_7B7C:                                                  ; address: 0x007b7c

        setf    EEADR, A                                    ; reg: 0xfa9
        movlw   0x00
        rcall   control_core_service_7A54                                ; dest: 0x007a54

flow_ccs_7ADA_7B82:                                                  ; address: 0x007b82

        bsf     TXSTA, TXEN, A                              ; reg: 0xfac, bit: 5
        bsf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4
        bsf     RCSTA, SPEN, A                              ; reg: 0xfab, bit: 7
        rcall   control_core_service_782C                                ; dest: 0x00782c
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bsf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        movlw   0x80
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        rcall   control_core_service_7840                                ; dest: 0x007840
        movlw   0x7a
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movlw   0xec
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        rcall   control_core_service_7946                                ; dest: 0x007946
        lfsr    0x0, 0x024
        movlw   0x1f

flow_ccs_7ADA_7BA4:                                                  ; address: 0x007ba4

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     flow_ccs_7ADA_7BA4                                   ; dest: 0x007ba4
        bcf     INTCON, GIE, A                              ; reg: 0xff2, bit: 7
        movlw   0x40
        movwf   ir_decoded_cmd, A                        ; reg: 0x01d
        clrf    ir_decoded_addr, A                        ; reg: 0x01e
        clrf    (Common_RAM + 32), A                        ; reg: 0x020
        clrf    (Common_RAM + 33), A                        ; reg: 0x021

flow_ccs_7ADA_7BB6:                                                  ; address: 0x007bb6

        clrf    (Common_RAM + 8), A                         ; reg: 0x008

flow_ccs_7ADA_7BB8:                                                  ; address: 0x007bb8

        lfsr    0x0, 0x076
        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 25), A                        ; reg: 0x019
        lfsr    0x0, 0x07c
        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        movff   (Common_RAM + 25), PLUSW0                   ; reg1: 0x019, reg2: 0xfeb
        incf    (Common_RAM + 8), F, A                      ; reg: 0x008
        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        sublw   0x06
        bnz     flow_ccs_7ADA_7BB8
        rcall   control_core_service_7E60                                ; dest: 0x007e60

flow_ccs_7ADA_7BD6:                                                  ; address: 0x007bd6

        lfsr    0x0, 0x043
        movlw   0x2e

flow_ccs_7ADA_7BDC:                                                  ; address: 0x007bdc

        clrf    POSTINC0, A                                 ; reg: 0xfee
        decfsz  WREG, F, A                                  ; reg: 0xfe8
        bra     flow_ccs_7ADA_7BDC                                   ; dest: 0x007bdc
        movlw   0xf4
        movwf   (Common_RAM + 2), A                         ; reg: 0x002
        movlw   0x01
        movwf   (Common_RAM + 6), A                         ; reg: 0x006

flow_ccs_7ADA_7BEA:                                                  ; address: 0x007bea

        rcall   control_core_service_79EC                                ; dest: 0x0079ec
        bnc     flow_ccs_7ADA_7BB6
        sublw   0x3a
        bnz     flow_ccs_7ADA_7BEA
        lfsr    0x1, 0x043

flow_ccs_7ADA_7BF6:                                                  ; address: 0x007bf6

        rcall   control_core_service_79EC                                ; dest: 0x0079ec
        bnc     flow_ccs_7ADA_7BB6
        sublw   0x0d
        bnz     flow_ccs_7ADA_7C02
        clrf    POSTINC1, A                                 ; reg: 0xfe6
        bra     flow_ccs_7ADA_7C0A                                   ; dest: 0x007c0a

flow_ccs_7ADA_7C02:                                                  ; address: 0x007c02

        movf    RCREG, W, A                                 ; reg: 0xfae
        movwf   POSTINC1, A                                 ; reg: 0xfe6
        bz      flow_ccs_7ADA_7C0A
        bra     flow_ccs_7ADA_7BF6                                   ; dest: 0x007bf6

flow_ccs_7ADA_7C0A:                                                  ; address: 0x007c0a

        bcf     0x82, 0x0, B                                ; reg: 0x082
        clrf    control_flags, A                        ; reg: 0x01f

flow_ccs_7ADA_7C0E:                                                  ; address: 0x007c0e

        movlw   0x06
        cpfslt  control_flags, A                        ; reg: 0x01f
        bra     flow_ccs_7ADA_7C2A                                   ; dest: 0x007c2a
        lfsr    0x0, 0x043
        movf    control_flags, W, A                     ; reg: 0x01f
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        movwf   (Common_RAM + 8), A                         ; reg: 0x008
        movlw   0x30
        subwf   (Common_RAM + 8), W, A                      ; reg: 0x008
        bz      flow_ccs_7ADA_7C26
        bsf     0x82, 0x0, B                                ; reg: 0x082

flow_ccs_7ADA_7C26:                                                  ; address: 0x007c26

        incf    control_flags, F, A                     ; reg: 0x01f
        bnz     flow_ccs_7ADA_7C0E

flow_ccs_7ADA_7C2A:                                                  ; address: 0x007c2a

        rrcf    0x82, W, B                                  ; reg: 0x082
        bc      flow_ccs_7ADA_7C30
        bra     flow_bootloader_manual_entry_7F56                                   ; dest: 0x007f56

flow_ccs_7ADA_7C30:                                                  ; address: 0x007c30

        clrf    (Common_RAM + 34), A                        ; reg: 0x022
        clrf    (Common_RAM + 35), A                        ; reg: 0x023
        clrf    control_flags, A                        ; reg: 0x01f

flow_ccs_7ADA_7C36:                                                  ; address: 0x007c36

        movlw   0x14
        cpfslt  control_flags, A                        ; reg: 0x01f
        bra     flow_ccs_7ADA_7C74                                   ; dest: 0x007c74
        lfsr    0x0, 0x071
        lfsr    0x1, 0x043
        movf    control_flags, W, A                     ; reg: 0x01f
        mullw   0x02
        movff   PRODL, (Common_RAM + 25)                    ; reg1: 0xff3, reg2: 0x019
        movff   PRODH, (Common_RAM + 26)                    ; reg1: 0xff4, reg2: 0x01a
        incf    (Common_RAM + 25), W, A                     ; reg: 0x019
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x02
        rcall   control_core_service_7ADA                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        lfsr    0x0, 0x071
        call    control_core_service_784E, 0x0                           ; dest: 0x00784e
        movwf   (Common_RAM + 25), A                        ; reg: 0x019
        movff   (Common_RAM + 16), (Common_RAM + 26)        ; reg1: 0x010, reg2: 0x01a
        movf    (Common_RAM + 25), W, A                     ; reg: 0x019
        addwf   (Common_RAM + 34), F, A                     ; reg: 0x022
        movf    (Common_RAM + 26), W, A                     ; reg: 0x01a
        addwfc  (Common_RAM + 35), F, A                     ; reg: 0x023
        incf    control_flags, F, A                     ; reg: 0x01f
        bnz     flow_ccs_7ADA_7C36

flow_ccs_7ADA_7C74:                                                  ; address: 0x007c74

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
        lfsr    0x0, 0x071
        lfsr    0x1, 0x043
        movlw   0x29
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x02
        rcall   control_core_service_7ADA                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        lfsr    0x0, 0x071
        call    control_core_service_784E, 0x0                           ; dest: 0x00784e
        movwf   (Common_RAM + 32), A                        ; reg: 0x020
        movff   (Common_RAM + 16), (Common_RAM + 33)        ; reg1: 0x010, reg2: 0x021
        movf    (Common_RAM + 32), W, A                     ; reg: 0x020
        cpfseq  (Common_RAM + 34), A                        ; reg: 0x022
        bra     flow_ccs_7ADA_7E5E                                   ; dest: 0x007e5e
        tstfsz  (Common_RAM + 33), A                        ; reg: 0x021
        bra     flow_ccs_7ADA_7E5E                                   ; dest: 0x007e5e
        lfsr    0x0, 0x071
        lfsr    0x1, 0x043
        movlw   0x03
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x04
        rcall   control_core_service_7ADA                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        lfsr    0x0, 0x071
        call    control_core_service_784E, 0x0                           ; dest: 0x00784e
        movwf   ir_decoded_cmd, A                        ; reg: 0x01d
        movff   (Common_RAM + 16), ir_decoded_addr        ; reg1: 0x010, reg2: 0x01e
        movlw   0x3f
        andwf   ir_decoded_cmd, W, A                     ; reg: 0x01d
        movwf   (Common_RAM + 8), A                         ; reg: 0x008
        clrf    (Common_RAM + 9), A                         ; reg: 0x009
        movf    (Common_RAM + 9), W, A                      ; reg: 0x009
        iorwf   (Common_RAM + 8), W, A                      ; reg: 0x008
        bz      flow_ccs_7ADA_7CE8
        movlw   0x00
        bra     flow_ccs_7ADA_7CEA                                   ; dest: 0x007cea

flow_ccs_7ADA_7CE8:                                                  ; address: 0x007ce8

        movlw   0x01

flow_ccs_7ADA_7CEA:                                                  ; address: 0x007cea

        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        movff   ir_decoded_cmd, (Common_RAM + 11)        ; reg1: 0x01d, reg2: 0x00b
        movff   ir_decoded_addr, (Common_RAM + 12)        ; reg1: 0x01e, reg2: 0x00c
        movlw   0x77
        movwf   (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0xc0
        call    control_core_service_780A, 0x0                           ; dest: 0x00780a
        andwf   (Common_RAM + 28), F, A                     ; reg: 0x01c
        movff   ir_decoded_cmd, (Common_RAM + 11)        ; reg1: 0x01d, reg2: 0x00b
        movff   ir_decoded_addr, (Common_RAM + 12)        ; reg1: 0x01e, reg2: 0x00c
        clrf    (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0x40
        call    control_core_service_7804, 0x0                           ; dest: 0x007804
        andwf   (Common_RAM + 28), F, A                     ; reg: 0x01c
        bz      flow_ccs_7ADA_7D22
        movf    ir_decoded_addr, W, A                     ; reg: 0x01e
        iorwf   ir_decoded_cmd, W, A                     ; reg: 0x01d
        bz      flow_ccs_7ADA_7D22
        movff   ir_decoded_addr, TBLPTRH                  ; reg1: 0x01e, reg2: 0xff7
        movf    ir_decoded_cmd, W, A                     ; reg: 0x01d
        rcall   control_core_service_7A90                                ; dest: 0x007a90

flow_ccs_7ADA_7D22:                                                  ; address: 0x007d22

        movff   ir_decoded_cmd, (Common_RAM + 11)        ; reg1: 0x01d, reg2: 0x00b
        movff   ir_decoded_addr, (Common_RAM + 12)        ; reg1: 0x01e, reg2: 0x00c
        movlw   0x77
        movwf   (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0xc0
        call    control_core_service_780A, 0x0                           ; dest: 0x00780a
        movwf   (Common_RAM + 28), A                        ; reg: 0x01c
        movff   ir_decoded_cmd, (Common_RAM + 11)        ; reg1: 0x01d, reg2: 0x00b
        movff   ir_decoded_addr, (Common_RAM + 12)        ; reg1: 0x01e, reg2: 0x00c
        clrf    (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0x40
        call    control_core_service_7804, 0x0                           ; dest: 0x007804
        andwf   (Common_RAM + 28), F, A                     ; reg: 0x01c
        bz      flow_ccs_7ADA_7DA4
        clrf    control_flags, A                        ; reg: 0x01f

flow_ccs_7ADA_7D4C:                                                  ; address: 0x007d4c

        movlw   0x08
        cpfslt  control_flags, A                        ; reg: 0x01f
        bra     flow_ccs_7ADA_7DA4                                   ; dest: 0x007da4
        lfsr    0x0, 0x071
        lfsr    0x1, 0x043
        movf    control_flags, W, A                     ; reg: 0x01f
        mullw   0x04
        movff   PRODL, (Common_RAM + 25)                    ; reg1: 0xff3, reg2: 0x019
        movff   PRODH, (Common_RAM + 26)                    ; reg1: 0xff4, reg2: 0x01a
        movlw   0x09
        addwf   (Common_RAM + 25), W, A                     ; reg: 0x019
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x04
        rcall   control_core_service_7ADA                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        lfsr    0x0, 0x071
        call    control_core_service_784E, 0x0                           ; dest: 0x00784e
        movwf   (Common_RAM + 32), A                        ; reg: 0x020
        movff   (Common_RAM + 16), (Common_RAM + 33)        ; reg1: 0x010, reg2: 0x021
        movf    control_flags, W, A                     ; reg: 0x01f
        mullw   0x02
        movff   PRODL, (Common_RAM + 25)                    ; reg1: 0xff3, reg2: 0x019
        movff   PRODH, (Common_RAM + 26)                    ; reg1: 0xff4, reg2: 0x01a
        movf    (Common_RAM + 25), W, A                     ; reg: 0x019
        addwf   ir_decoded_cmd, W, A                     ; reg: 0x01d
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        movf    (Common_RAM + 26), W, A                     ; reg: 0x01a
        addwfc  ir_decoded_addr, W, A                     ; reg: 0x01e
        movwf   TBLPTRH, A                                  ; reg: 0xff7
        movf    (Common_RAM + 33), W, A                     ; reg: 0x021
        rcall   control_core_service_7A6E                                ; dest: 0x007a6e
        movf    (Common_RAM + 32), W, A                     ; reg: 0x020
        rcall   control_core_service_7A6E                                ; dest: 0x007a6e
        incf    control_flags, F, A                     ; reg: 0x01f
        bnz     flow_ccs_7ADA_7D4C

flow_ccs_7ADA_7DA4:                                                  ; address: 0x007da4

        movlw   0x3a
        rcall   control_core_service_7A2A                                ; dest: 0x007a2a
        movlw   0x04
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0x02
        movwf   (Common_RAM + 5), A                         ; reg: 0x005
        movf    (Common_RAM + 34), W, A                     ; reg: 0x022
        call    control_core_service_78DC, 0x0                           ; dest: 0x0078dc
        movlw   0x0d
        rcall   control_core_service_7A2A                                ; dest: 0x007a2a
        movlw   0x0a
        rcall   control_core_service_7A2A                                ; dest: 0x007a2a
        movf    ir_decoded_cmd, W, A                     ; reg: 0x01d
        xorlw   0x40
        iorwf   ir_decoded_addr, W, A                     ; reg: 0x01e
        bnz     flow_ccs_7ADA_7E0E
        movlw   0x08
        movwf   control_flags, A                        ; reg: 0x01f

flow_ccs_7ADA_7DCA:                                                  ; address: 0x007dca

        movlw   0x10
        cpfslt  control_flags, A                        ; reg: 0x01f
        bra     flow_ccs_7ADA_7E08                                   ; dest: 0x007e08
        lfsr    0x0, 0x071
        lfsr    0x1, 0x043
        movf    control_flags, W, A                     ; reg: 0x01f
        mullw   0x02
        movff   PRODL, (Common_RAM + 25)                    ; reg1: 0xff3, reg2: 0x019
        movff   PRODH, (Common_RAM + 26)                    ; reg1: 0xff4, reg2: 0x01a
        movlw   0x09
        addwf   (Common_RAM + 25), W, A                     ; reg: 0x019
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x02
        rcall   control_core_service_7ADA                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        lfsr    0x0, 0x071
        call    control_core_service_784E, 0x0                           ; dest: 0x00784e
        movwf   (Common_RAM + 8), A                         ; reg: 0x008
        lfsr    0x0, 0x024
        movf    control_flags, W, A                     ; reg: 0x01f
        movff   (Common_RAM + 8), PLUSW0                    ; reg1: 0x008, reg2: 0xfeb
        incf    control_flags, F, A                     ; reg: 0x01f
        bnz     flow_ccs_7ADA_7DCA

flow_ccs_7ADA_7E08:                                                  ; address: 0x007e08

        setf    EEADR, A                                    ; reg: 0xfa9
        movlw   0x00
        rcall   control_core_service_7A54                                ; dest: 0x007a54

flow_ccs_7ADA_7E0E:                                                  ; address: 0x007e0e

        movf    ir_decoded_cmd, W, A                     ; reg: 0x01d
        xorlw   0x50
        iorwf   ir_decoded_addr, W, A                     ; reg: 0x01e
        bnz     flow_ccs_7ADA_7E5E
        clrf    control_flags, A                        ; reg: 0x01f

flow_ccs_7ADA_7E18:                                                  ; address: 0x007e18

        movlw   0x10                                        ; RC5 0x10 volume up
        cpfslt  control_flags, A                        ; reg: 0x01f
        bra     flow_ccs_7ADA_7E5C                                   ; dest: 0x007e5c
        lfsr    0x0, 0x071
        lfsr    0x1, 0x043
        movf    control_flags, W, A                     ; reg: 0x01f
        mullw   0x02
        movff   PRODL, (Common_RAM + 25)                    ; reg1: 0xff3, reg2: 0x019
        movff   PRODH, (Common_RAM + 26)                    ; reg1: 0xff4, reg2: 0x01a
        movlw   0x09
        addwf   (Common_RAM + 25), W, A                     ; reg: 0x019
        movwf   PRODL, A                                    ; reg: 0xff3
        movlw   0x02
        rcall   control_core_service_7ADA                                ; dest: 0x007ada
        clrf    INDF0, A                                    ; reg: 0xfef
        movlw   0x10
        addwf   control_flags, W, A                     ; reg: 0x01f
        movwf   (Common_RAM + 8), A                         ; reg: 0x008
        lfsr    0x0, 0x071
        call    control_core_service_784E, 0x0                           ; dest: 0x00784e
        movwf   (Common_RAM + 10), A                        ; reg: 0x00a
        lfsr    0x0, 0x024
        movf    (Common_RAM + 8), W, A                      ; reg: 0x008
        movff   (Common_RAM + 10), PLUSW0                   ; reg1: 0x00a, reg2: 0xfeb
        incf    control_flags, F, A                     ; reg: 0x01f
        bnz     flow_ccs_7ADA_7E18

flow_ccs_7ADA_7E5C:                                                  ; address: 0x007e5c

        rcall   control_core_service_7E94                                ; dest: 0x007e94

flow_ccs_7ADA_7E5E:                                                  ; address: 0x007e5e

        bra     flow_ccs_7ADA_7BD6                                   ; dest: 0x007bd6

control_core_service_7E60:                                               ; address: 0x007e60

        movlw   0x0d
        call    control_core_service_7A2A, 0x0                           ; dest: 0x007a2a
        movlw   0x0a
        call    control_core_service_7A2A, 0x0                           ; dest: 0x007a2a
        movlw   0x0c
        call    control_core_service_7A2A, 0x0                           ; dest: 0x007a2a
        movlw   0x3a
        call    control_core_service_7A2A, 0x0                           ; dest: 0x007a2a
        movlw   0x04
        movwf   (Common_RAM + 1), A                         ; reg: 0x001
        movlw   0x06
        movwf   (Common_RAM + 4), A                         ; reg: 0x004
        clrf    (Common_RAM + 16), A                        ; reg: 0x010
        movlw   0x7c
        call    control_core_service_7926, 0x0                           ; dest: 0x007926
        movlw   0x0d
        call    control_core_service_7A2A, 0x0                           ; dest: 0x007a2a
        movlw   0x0a
        goto    control_core_service_7A2A                                ; dest: 0x007a2a

control_core_service_7E94:                                               ; address: 0x007e94

        clrf    TBLPTRL, A                                  ; reg: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        rcall   control_core_service_7A92                                ; dest: 0x007a92
        clrf    TBLPTRL, A                                  ; reg: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        movlw   0x00
        call    control_core_service_7A6E, 0x0                           ; dest: 0x007a6e
        movlw   0xef
        call    control_core_service_7A6E, 0x0                           ; dest: 0x007a6e
        movlw   0x02
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        movlw   0x3c
        call    control_core_service_7A6E, 0x0                           ; dest: 0x007a6e
        movlw   0xf0
        call    control_core_service_7A6E, 0x0                           ; dest: 0x007a6e
        movlw   0x04
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        movlw   0xff
        call    control_core_service_7A6E, 0x0                           ; dest: 0x007a6e
        movlw   0xff
        call    control_core_service_7A6E, 0x0                           ; dest: 0x007a6e
        movlw   0x06
        movwf   TBLPTRL, A                                  ; reg: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        movlw   0xff
        call    control_core_service_7A6E, 0x0                           ; dest: 0x007a6e
        movlw   0xff
        call    control_core_service_7A6E, 0x0                           ; dest: 0x007a6e
        movlw   0x08
        movwf   control_flags, A                        ; reg: 0x01f

flow_ccs_7E94_7EE4:                                                  ; address: 0x007ee4

        movlw   0x20
        cpfslt  control_flags, A                        ; reg: 0x01f
        bra     flow_ccs_7E94_7F00                                   ; dest: 0x007f00
        movff   control_flags, TBLPTRL                  ; reg1: 0x01f, reg2: 0xff6
        clrf    TBLPTRH, A                                  ; reg: 0xff7
        lfsr    0x0, 0x024
        movf    control_flags, W, A                     ; reg: 0x01f
        movf    PLUSW0, W, A                                ; reg: 0xfeb
        call    control_core_service_7A6E, 0x0                           ; dest: 0x007a6e
        incf    control_flags, F, A                     ; reg: 0x01f
        bnz     flow_ccs_7E94_7EE4

flow_ccs_7E94_7F00:                                                  ; address: 0x007f00

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

        clrf    control_flags, A                        ; reg: 0x01f

flow_bootloader_manual_entry_7F04:                                                  ; address: 0x007f04

        movlw   0x0b
        cpfslt  control_flags, A                        ; reg: 0x01f
        bra     flow_bootloader_manual_entry_7F54                                   ; dest: 0x007f54
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
        bz      flow_bootloader_manual_entry_7F4A
        movlw   0x01
        movwf   (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0xf4
        call    control_core_service_7AA8, 0x0                           ; dest: 0x007aa8
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
        bz      flow_bootloader_manual_entry_7F4A
        bsf     0x82, 0x1, B                                ; reg: 0x082

flow_bootloader_manual_entry_7F4A:                                                  ; address: 0x007f4a

        movlw   0x0a
        call    control_core_service_7AA6, 0x0                           ; dest: 0x007aa6
        incf    control_flags, F, A                     ; reg: 0x01f
        bnz     flow_bootloader_manual_entry_7F04

flow_bootloader_manual_entry_7F54:                                                  ; address: 0x007f54

        return  0x0

flow_bootloader_manual_entry_7F56:                                                  ; address: 0x007f56

        rcall   control_core_service_7E94                                ; dest: 0x007e94
        bcf     TRISC, RC1, A                               ; reg: 0xf94, bit: 1
        bcf     LATC, LATC1, A                              ; reg: 0xf8b, bit: 1
        setf    EEADR, A                                    ; reg: 0xfa9
        movlw   0x01
        call    control_core_service_7A54, 0x0                           ; dest: 0x007a54
        movlw   0x01
        movwf   (Common_RAM + 14), A                        ; reg: 0x00e
        movlw   0x2c
        call    control_core_service_7AA8, 0x0                           ; dest: 0x007aa8
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
        ; V1.71 (V1.61b): version tuple at EEPROM 0x70..0x73 bumped to 1.71
        ; encoding: 0x01 0x07 '1' 0x01 (major, minor, ASCII sub, reserved)
        db      0x01                                        ; EEPROM 0x70: major
        db      0x07                                        ; EEPROM 0x71: minor (V1.7 family)
        db      0x31                                        ; EEPROM 0x72: '1' (V1.71)
        db      0x01                                        ; EEPROM 0x73: reserved
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
