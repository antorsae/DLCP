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
;              to stock V1.6b. EEPROM matches stock except the V1.71 identity
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
        goto    flow_app_cold_init_040C                                   ; dest: 0x00040c
        clrf    0x99, B                                     ; reg: 0x099

flow_app_cold_init_040C:                                                  ; address: 0x00040c

        ; V1.71 hardening: consume RCREG immediately, but roll back the
        ; software write pointer if this byte would overwrite unread data.
        movf    0x99, W, B                                  ; reg: 0x099
        cpfseq  0x98, B                                     ; reg: 0x098
        goto    flow_app_cold_init_0414                                   ; dest: 0x000414
        decf    0x99, F, B                                  ; reg: 0x099
        movlw   0xff
        cpfseq  0x99, B                                     ; reg: 0x099
        goto    flow_app_cold_init_0414                                   ; dest: 0x000414
        movlw   0x2f
        movwf   0x99, B                                     ; reg: 0x099

flow_app_cold_init_0414:                                                  ; address: 0x000414

        btfss   INTCON, RBIF, A                             ; reg: 0xff2, bit: 0
        goto    flow_app_cold_init_0436                                   ; dest: 0x000436
        movf    (Common_RAM + 28), W, A                     ; reg: 0x01c
        iorwf   (Common_RAM + 27), W, A                     ; reg: 0x01b
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_app_cold_init_0434                                   ; dest: 0x000434
        btfss   control_flags, 0x0, A                   ; reg: 0x01f
        goto    flow_app_cold_init_0434                                   ; dest: 0x000434
        setf    v171_ir_decode_pending, BANKED            ; deferred foreground service

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
        ; ---------------------------------------------------------------
        ; V1.71 inline (V1.62b): full UART soft-recover on OERR
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
        clrf    tx_ring_rd, BANKED                          ; 0x096
        clrf    tx_ring_wr, BANKED                          ; 0x097
        clrf    rx_ring_rd, BANKED                          ; 0x098
        clrf    rx_ring_wr, BANKED                          ; 0x099
        clrf    rx_frame_position, BANKED                   ; 0x0A6
        clrf    rx_parsed_cmd, A                            ; 0x02F
        clrf    rx_parsed_data, A                           ; 0x030

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
        goto    v171_bf08_case_check                      ; not 0x1D — try V1.71 BF/08
        movf    0xa7, W, B                                  ; reg: 0x0a7
        subwf   rx_parsed_data, W, A                     ; reg: 0x030
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_rx_parser_entry_05EA                                   ; dest: 0x0005ea
        movff   rx_parsed_data, 0x0a7                    ; reg1: 0x030
        call    control_core_service_0F54, 0x0                           ; dest: 0x000f54
        bra     flow_rx_parser_entry_05EA                 ; 0x1D handled — exit

v171_bf08_case_check:
        ; ---------------------------------------------------------------
        ; V1.71 inline (V1.63b): BF/08 DSP-fault dispatch case
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
        cpfseq  rx_parsed_cmd, A                        ; reg: 0x02f
        goto    v171_bf2x_case_check                      ; not BF/08 — try BF/2N (Layer 5)

        movff   rx_parsed_data, bf08_fault_byte         ; store payload byte
        movf    rx_parsed_data, W, A
        bnz     v171_bf08_set_fault

        ; Payload == 0 — clear fault.  If the bit was already clear this
        ; is a no-op; if it was set, force a full-sync resync so MAIN
        ; gets a fresh status burst on the next loop iteration.
        btfss   control_flags, DSP_FAULT_BIT, A
        bra     flow_rx_parser_entry_05EA                 ; already clear
        bcf     control_flags, DSP_FAULT_BIT, A
        movlb   0x01
        clrf    0x9F, BANKED                             ; full_sync_lo = 0
        clrf    0xA0, BANKED                             ; full_sync_hi = 0
        movlb   0x00
        bra     flow_rx_parser_entry_05EA

v171_bf08_set_fault:
        bsf     control_flags, DSP_FAULT_BIT, A
        bra     flow_rx_parser_entry_05EA

v171_bf2x_case_check:
        ; ---------------------------------------------------------------
        ; V1.71 (Layer 5 Phase B + Tier-1): BF/21..2B diagnostics replies
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
        ; Range gate: accept cmd 0x21..0x2B only.
        movlw   0x21
        cpfslt  rx_parsed_cmd, A                          ; cmd < 0x21? -> exit
        bra     v171_bf2x_check_upper
        bra     flow_rx_parser_entry_05EA
v171_bf2x_check_upper:
        movlw   0x2C
        cpfslt  rx_parsed_cmd, A                          ; cmd < 0x2C? -> ok
        bra     flow_rx_parser_entry_05EA                 ; cmd >= 0x2C -> exit
        ; Compute byte offset: (cmd - 0x21) gives 0..10.
        movlw   0x21
        subwf   rx_parsed_cmd, W, A
        movwf   (Common_RAM + 4), A                       ; col_offset
        ; --- Pick "effective target" for this frame's cache routing ---
        ; Two reply burst types share the BF/2N space:
        ;   col 0..6   -- cmd 0x21 reply (runtime cells); use LIVE
        ;                 v171_diag_target.  This burst's last frame
        ;                 BF/27 toggles target as a side effect, so
        ;                 the "live target at frame arrival" is the
        ;                 right thing.
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
        ; Default = live target; cmd 0x22 path overrides with snapshot.
        movlb   0x01
        movf    v171_diag_target, W, BANKED
        movwf   (Common_RAM + 5), A                       ; effective_target
        movlw   0x07
        cpfslt  (Common_RAM + 4), A                       ; col < 7? skip if so
        bra     v171_bf2x_use_reset_target                ; col >= 7: override
        bra     v171_bf2x_have_effective_target           ; col < 7: keep live
v171_bf2x_use_reset_target:
        movf    v171_diag_reset_target, W, BANKED
        movwf   (Common_RAM + 5), A
v171_bf2x_have_effective_target:
        ; Compute slot base: PB1 base = v171_diag_pb1_i (0x80),
        ; PB2 base = v171_diag_pb2_i (0x8B = 0x80 + 11).  Add 11 (0x0B)
        ; if effective_target bit0 set.
        movlw   v171_diag_pb1_i
        btfsc   (Common_RAM + 5), 0, A
        movlw   v171_diag_pb2_i
        addwf   (Common_RAM + 4), W, A                    ; W = base + col_offset
        ; Write payload via FSR0 in BANK 1 (0x180..0x195 physical).
        movwf   FSR0L, A
        movlw   0x01
        movwf   FSR0H, A
        movff   rx_parsed_data, INDF0                     ; *(slot) = data
        ; Mark the screen dirty so check_redraw redraws on the next
        ; loop iteration even when v171_diag_present is unchanged.
        ; Without this, the screen freezes against later counter
        ; updates once both PBs have been seen present at least once.
        movlb   0x01
        bsf     v171_diag_flags, V171_DIAG_FLAG_DIRTY, BANKED
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
        ; Use (Common_RAM + 5) effective_target -- which equals
        ; v171_diag_target on this path (col 6 < 7) -- for the
        ; present-mask OR-in.  The btg below operates on the LIVE
        ; v171_diag_target directly because that's what we're toggling.
        movlw   0x01                                      ; PB1 mask
        btfsc   (Common_RAM + 5), 0, A
        movlw   0x02                                      ; PB2 mask
        iorwf   v171_diag_present, F, BANKED
        bcf     v171_diag_flags, V171_DIAG_FLAG_RUNTIME_PENDING, BANKED
        btg     v171_diag_target, 0, BANKED               ; flip for next query
        movlb   0x00
        bra     flow_rx_parser_entry_05EA
v171_bf2x_check_reset_last:
        ; --- RESET LAST FRAME (BF/2B, Tier-1) ---
        ; Tier-1: when the 4-frame BF/28..BF/2B reset-cause burst
        ; completes, mark the reset cells as fresh for this PB so the
        ; page-entry hook does NOT re-fire cmd 0x22 within the same
        ; session, and clear RESET_PENDING.  Do NOT touch the runtime
        ; present mask / runtime target / RUNTIME_PENDING -- those are
        ; managed independently by the cmd 0x21 path above.
        ;
        ; Use (Common_RAM + 5) effective_target -- which equals
        ; v171_diag_reset_target on this path (col 10 >= 7) -- for the
        ; reset_seen OR-in.  v171_diag_target may have toggled via an
        ; interleaved BF/27 from the OTHER PB during the cmd 0x22
        ; reply burst; reading the live target here would set the
        ; wrong reset_seen bit (codex MEDIUM review fix).
        movlw   0x0A
        cpfseq  (Common_RAM + 4), A                       ; col_offset == 10 (BF/2B)?
        bra     v171_bf2x_check_reset_last_exit_bsr0      ; not last frame -- reset BSR + exit
        movlw   0x01                                      ; PB1 reset_seen bit
        btfsc   (Common_RAM + 5), 0, A
        movlw   0x02                                      ; PB2 reset_seen bit
        iorwf   v171_diag_reset_seen, F, BANKED
        bcf     v171_diag_flags, V171_DIAG_FLAG_RESET_PENDING, BANKED
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
        ; The pre-Tier-1 V1.71 source had the SAME bra-without-movlb
        ; bug here but its consequence was benign because the aliased
        ; cells were rx_ring body (operand 0x80..0x94 in BANK 0 = upper
        ; half of the 48-byte rx_ring at 0x66..0x95) -- a circular
        ; buffer where corruption gets overwritten on the next wrap.
        ; Phase 3.1's cache extension shifted cells up into the
        ; ring-INDEX / idle-timer / full-sync zone, making the leak
        ; catastrophic.
        movlb   0x00
        bra     flow_rx_parser_entry_05EA

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
; *** V1.71 Layer 1 fix for BUG C6 (tx_byte_enqueue_busy_wait) ***
; The V1.6b body busy-waited indefinitely at 0x00060C while the ring
; was at the producer/consumer collision boundary, on the assumption
; that the TX ISR would advance tx_ring_rd within a few microseconds.
; In practice this assumption fails whenever MAIN's main_uart_service
; pauses for tens of milliseconds (V3.2 legacy 97-iter preset apply,
; standby/wake handshake, etc.) — CONTROL stalls inside this routine,
; misses status responses, and the LCD eventually drops to WAITING.
;
; V1.71 replaces the indefinite busy-wait with a bounded 256-tick
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
; Calling convention (V1.71):
;   in : tx_data_staging (0x027) holds the byte to enqueue
;   out: STATUS.C = 0 on commit, 1 on saturation (byte dropped)
;        v171_tx_saturate_count incremented on saturation
;        tx_data_staging, v171_tx_enq_retry are clobbered scratch
; ===========================================================================
; tx_ring_reserve_3 — V1.71 atomic 3-byte frame guard
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
        movf    tx_ring_rd, W, B                    ; W = rd
        subwf   tx_ring_wr, W, B                    ; W = wr - rd (2's comp)
        btfss   STATUS, C, A                        ; C=1 if wr >= rd (no borrow)
        addlw   0x30                                 ; borrow: W = wr-rd+48 (mod 256 wraps back to occ)
        addlw   0x03                                 ; W = occupancy + 3
        movwf   v171_tx_enq_retry, A                ; scratch
        movlw   0x30                                 ; 48 = ring capacity (one slot reserved)
        cpfslt  v171_tx_enq_retry, A                ; skip next if (occ+3) < 48 → room OK
        bra     tx_ring_reserve_3_saturated
        bcf     STATUS, C, A
        return  0x0

tx_ring_reserve_3_saturated:
        movlb   0x01
        incfsz  v171_tx_saturate_count, F, BANKED
        bra     tx_ring_reserve_3_sat_done
        setf    v171_tx_saturate_count, BANKED       ; clamp at 0xFF
tx_ring_reserve_3_sat_done:
        movlb   0x00
        bsf     STATUS, C, A
        return  0x0


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

        ; V1.71 Layer 1: bounded retry replaces V1.6b indefinite busy-wait.
        ; setf gives 256 polls before saturation (~0.5 ms wall time at
        ; 4 MIPS — comfortably longer than worst-case TX ISR latency on
        ; a healthy link, and bounded enough that CONTROL's main loop
        ; can't be stalled by a wedged downstream).
        setf    v171_tx_enq_retry, A                        ; reg: 0x02d (256-tick budget)

flow_tx_byte_enqueue_060C:                                                  ; address: 0x00060c

        movf    tx_data_staging, W, A                     ; reg: 0x027
        subwf   0x96, W, B                                  ; reg: 0x096
        btfss   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        bra     flow_tx_byte_enqueue_0614                   ; room available — commit
        decfsz  v171_tx_enq_retry, F, A                     ; reg: 0x02d (decrement budget)
        bra     flow_tx_byte_enqueue_060C                   ; budget remains — re-poll

        ; --- V1.71 Layer 1 saturation path ---
        ; Budget exhausted.  Bump saturating counter (clamped at 0xFF
        ; so prolonged saturation doesn't roll back to zero), set C=1,
        ; and return without committing tx_ring_wr.  The byte already
        ; written to tx_ring_base[old_wr] is NOT visible to the ISR
        ; (it never bumps tx_ring_wr) and will be overwritten on the
        ; next successful enqueue.
        movlb   0x01
        incfsz  v171_tx_saturate_count, F, BANKED           ; reg: 0x0ad
        bra     v171_tx_enq_saturate_done
        setf    v171_tx_saturate_count, BANKED              ; reg: 0x0ad (clamp at 0xFF)
v171_tx_enq_saturate_done:
        movlb   0x00
        bsf     STATUS, C, A                                ; reg: 0xfd8, bit: 0 (C=1 = saturated)
        return  0x0

flow_tx_byte_enqueue_0614:                                                  ; address: 0x000614

        movff   tx_data_staging, 0x097                    ; reg1: 0x027
        bsf     PIE1, TXIE, A                               ; reg: 0xf9d, bit: 4
        bcf     STATUS, C, A                                ; reg: 0xfd8, bit: 0 (C=0 = success)
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

        ; V1.71 atomic 3-byte frame: reserve ring slots first so partial
        ; frames cannot leak to the wire (see tx_ring_reserve_3 header).
        rcall   tx_ring_reserve_3
        bc      serial_tx_routed_frame_aborted
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

serial_tx_routed_frame_aborted:
        return  0x0


; ===========================================================================
; full_sync_burst @ 0x000B36 — V1.71 Layer 2 one-frame-per-call dispatch
; ---------------------------------------------------------------------------
; *** V1.71 Layer 2 fix for BUG C7 (fullsync_burst_saturates_link) ***
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
; V1.71 Layer 2 replaces the burst with a one-frame-per-call state
; machine.  Each invocation of full_sync_burst (still called from
; the existing label_147 trigger ~every 80,000 main-loop iterations)
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
        incf    v171_full_sync_step, F, BANKED              ; reg: 0x070
        movlw   0x06
        cpfsgt  v171_full_sync_step, BANKED                 ; if step > 6, fall through to wrap
        bra     v171_fs_step_in_range
        movlw   0x01
        movwf   v171_full_sync_step, BANKED                 ; wrap step → 1

v171_fs_step_in_range:
        ; --- Dispatch on step ---
        ; W ← step (1..6); decrement chain matches the active step.
        movf    v171_full_sync_step, W, BANKED
        movlb   0x00

        addlw   0xFF                                        ; W -= 1; Z if step was 1
        bnz     v171_fs_try_step_2
        goto    volume_frame_send                           ; step 1: volume
v171_fs_try_step_2:
        addlw   0xFF                                        ; Z if step was 2
        bnz     v171_fs_try_step_3
        goto    input_frame_send                            ; step 2: input
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

        ; V1.71 atomic 3-byte frame: reserve ring slots first (partial-
        ; frame hazard for this emitter was low pre-fix since the
        ; callers in WAITING loops are already cyclic, but closing the
        ; hazard uniformly across all 3-byte senders simplifies the
        ; saturation-counter semantics).
        rcall   tx_ring_reserve_3
        bc      poll_frame_send_aborted
        movlw   0xb1                                        ; ROUTE addressed MAIN#1
        movwf   tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        movlw   0x04                                        ; CMD status_poll
        movwf   tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        clrf    tx_data_staging, A                        ; reg: 0x027
        call    tx_byte_enqueue, 0x0                           ; dest: 0x0005ec
        return  0x0

poll_frame_send_aborted:
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

        ; V1.71 atomic 3-byte frame (see tx_ring_reserve_3 header).
        rcall   tx_ring_reserve_3
        bc      input_frame_send_aborted
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

input_frame_send_aborted:
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

        ; V1.71 atomic 3-byte frame (see tx_ring_reserve_3 header).
        rcall   tx_ring_reserve_3
        bc      volume_frame_send_aborted
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

        ; V1.71 atomic 3-byte frame (see tx_ring_reserve_3 header).
        rcall   tx_ring_reserve_3
        bc      cmd1d_setting_frame_send_aborted
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

cmd1d_setting_frame_send_aborted:
        return  0x0

v171_service_pending_ir_decode:
        ; Foreground completion of the deferred RC5 decode.  The ISR only
        ; latches `v171_ir_decode_pending`; the expensive decoder runs here.
        movf    v171_ir_decode_pending, F, BANKED
        btfsc   STATUS, Z, A
        return  0x0
        btfss   control_flags, IR_ARMED, A
        goto    v171_service_pending_ir_decode_drop
        clrf    v171_ir_decode_pending, BANKED
        call    ir_rc5_decode, 0x0                         ; rcall ir_rc5_decode
        movwf   ir_decoded_cmd, A
        movff   (Common_RAM + 13), ir_decoded_addr
        bcf     control_flags, IR_ARMED, A
        return  0x0

v171_service_pending_ir_decode_drop:
        clrf    v171_ir_decode_pending, BANKED
        return  0x0


; ===========================================================================
; V1.71 IR non-blocking decoder (task #152 / V171_IR_NONBLOCK_DECODER_SPEC.md)
; ---------------------------------------------------------------------------
; Replaces the broken deferred-decode design (bc61c70 / task #151).
; State machine: IDLE → SAMPLING (32 Timer1 ticks at 889 µs) → DONE.
; Sample handler reads RB5 once per Timer1 tick, accumulates Manchester
; bits into a byte-indexed 4-byte buffer (buf0=samples 1-8, buf1=9-16,
; buf2=17-24, buf3=25-32).  On completion, post-process copies the
; buffer into (Common_RAM+16..19) at 0x010..0x013 and reuses the legacy
; ir_rc5_decode body's Manchester pair-validation logic at
; flow_ir_rc5_decode_025E (no further RB5 reads -- pure post-process).
;
; All state lives in BANK 1 (movlb 0x01); see RAM equates at
; v171_ir_state in dlcp_control_ram.inc.  These routines are NOT
; reachable yet from the ISR -- M2 commit lands the bodies for
; structural review; M3 commit wires the ISR dispatch.
; ===========================================================================

; v171_ir_start_decode @ called from RBIF ISR after RB5=LOW falling edge
; confirmed and IR_ARMED set.  Initializes state machine + arms Timer1
; for the FIRST sample at 445 µs (mid-second-half of S1, where RB5 is
; still LOW for bit '1' Manchester at the inverted-TSOP convention the
; firmware expects).
;
; Clobbers: W, STATUS, BSR (movlb 0x1).  Does NOT preserve caller W.
; This is safe because the V1.71 isr_entry header at asm:786-792
; saves W/STATUS/BSR/FSR0/FSR0H to scratch RAM and restores them on
; exit (W restored at asm:872).
v171_ir_start_decode:
        movlb   0x1
        clrf    v171_ir_buf0, BANKED
        clrf    v171_ir_buf1, BANKED
        clrf    v171_ir_buf2, BANKED
        clrf    v171_ir_buf3, BANKED
        clrf    v171_ir_sample_count, BANKED
        clrf    v171_ir_flags, BANKED
        movlw   0x01                                ; SAMPLING state
        movwf   v171_ir_state, BANKED
        ; Arm Timer1 for 445 µs first sample.  T1CON=0x81 = TMR1ON +
        ; RD16 (16-bit writes via TMR1H buffer).  In RD16 mode, the
        ; TMR1H write goes to a buffer; the TMR1L write triggers
        ; atomic 16-bit load of the counter.  Clear PIR1.TMR1IF
        ; first so a stale flag doesn't fire immediately.
        movlw   V171_IR_TMR1_FIRST_HI
        movwf   TMR1H, A
        movlw   V171_IR_TMR1_FIRST_LO
        movwf   TMR1L, A
        bcf     PIR1, TMR1IF, A
        bsf     PIE1, TMR1IE, A
        movlw   0x81                                ; TMR1ON + RD16
        movwf   T1CON, A
        return  0x0


; v171_ir_sample_handler @ called from Timer1 ISR (TMR1IF set).
; Reads PORTB.RB5, shifts the resulting Manchester bit into the buffer
; byte indexed by sample_count >> 3, increments sample_count.  If
; sample_count >= 32, transitions to DONE (calls v171_ir_post_process).
; Otherwise reloads TMR1 with full-period preload (0xF595) for the next
; 889 µs sample.
;
; Uses FSR0 to address buf[byte_index] directly so we don't need a
; multi-way branch dispatch BEFORE the rlcf -- avoids the carry-
; clobber bug codex caught in the v2 implementation where addlw
; (used for branch dispatch) clobbered the RB5-derived carry before
; the rlcf consumed it.
v171_ir_sample_handler:
        ; First compute byte_index = sample_count >> 3 and form the
        ; 12-bit physical address of buf[byte_index].  Since
        ; v171_ir_buf0 lives at physical 0x1D7 (BANK 1), buf[k] is at
        ; 0x1D7 + k for k=0..3.  Loading FSR0 = 0x1D7 + k lets us
        ; rlcf INDF0 directly without any carry-clobbering arithmetic
        ; AFTER we set carry from RB5.
        movlb   0x1
        movf    v171_ir_sample_count, W, BANKED
        rrncf   WREG, W, A                          ; W = count >> 1
        rrncf   WREG, W, A                          ; W = count >> 2
        rrncf   WREG, W, A                          ; W = count >> 3
        andlw   0x03                                ; W = byte_index 0..3
        addlw   0xD7                                ; W = 0xD7 + byte_index
                                                    ; (physical low byte of v171_ir_buf{k})
        movwf   FSR0L, A
        movlw   0x01
        movwf   FSR0H, A                            ; FSR0 = 0x1D7 + byte_index
        ; NOW set carry from RB5 -- nothing between this and rlcf
        ; touches STATUS.C.  Polarity matches legacy decoder
        ; (asm:573-576): C=1 default; btfsc PORTB.RB5 (skip clear if
        ; RB5 LOW); bcf C → C=0 if RB5 HIGH.
        bsf     STATUS, C, A
        btfsc   PORTB, RB5, A
        bcf     STATUS, C, A
        ; rlcf rotates INDF0 left through C: new bit 0 = old C, new
        ; C = old bit 7.  We don't care about the new C (next
        ; iteration will reset it from RB5 anyway).
        rlcf    INDF0, F, A
        ; Advance sample_count.
        incf    v171_ir_sample_count, F, BANKED
        ; Check if we've collected all 32 samples.
        movlw   V171_IR_TOTAL_SAMPLES
        cpfslt  v171_ir_sample_count, BANKED
        bra     v171_ir_decode_done
        ; Reload TMR1 for next 889 µs sample.  RD16 buffered write:
        ; TMR1H first, then TMR1L triggers atomic 16-bit load.
        movlw   V171_IR_TMR1_FULL_HI
        movwf   TMR1H, A
        movlw   V171_IR_TMR1_FULL_LO
        movwf   TMR1L, A
        return  0x0

; v171_ir_decode_done @ tail-call from sample_handler when 32 samples
; collected.  Disables Timer1, calls v171_ir_post_process to extract
; addr/cmd from the buffer, clears IR_ARMED, returns to IDLE state.
v171_ir_decode_done:
        bcf     T1CON, TMR1ON, A
        bcf     PIE1, TMR1IE, A
        bcf     PIR1, TMR1IF, A
        rcall   v171_ir_post_process
        movlb   0x1
        clrf    v171_ir_state, BANKED
        clrf    v171_ir_sample_count, BANKED
        bcf     control_flags, IR_ARMED, A
        return  0x0


; v171_ir_post_process @ Manchester pair validation + addr/cmd extraction.
; Copies buf0..buf3 (BANK 1) into (Common_RAM+16)..(Common_RAM+19) at
; physical 0x010..0x013, then jumps into the legacy decoder's
; post-process path at flow_ir_rc5_decode_025E.  That path is pure
; post-process (no further RB5 reads, codex-confirmed asm:587+).  It
; walks the 32-sample buffer through control_core_service_02EE for
; Manchester pair validation and writes the decoded address into
; (Common_RAM+13) and returns the decoded command in W -- caller writes
; both to ir_decoded_cmd / ir_decoded_addr.
v171_ir_post_process:
        movlb   0x1
        movff   v171_ir_buf0, (Common_RAM + 16)
        movff   v171_ir_buf1, (Common_RAM + 17)
        movff   v171_ir_buf2, (Common_RAM + 18)
        movff   v171_ir_buf3, (Common_RAM + 19)
        movlb   0x0
        ; Call the legacy post-process.  flow_ir_rc5_decode_025E sets
        ; up its own FSR0 = 0x010 (the buffer base, which we just
        ; populated) and clears its scratch (Common_RAM+5/+20/+14/+13/
        ; +12) at entry.  No further RB5 reads -- pure post-process
        ; via control_core_service_02EE for Manchester pair validation
        ; (codex-confirmed asm:600,609,632,657).  On return, W holds
        ; decoded command and (Common_RAM+13) holds decoded address;
        ; mirrors the legacy ir_rc5_decode return contract used by
        ; the original ISR caller at asm:828-830.
        call    flow_ir_rc5_decode_025E, 0x0
        movwf   ir_decoded_cmd, A
        movff   (Common_RAM + 13), ir_decoded_addr
        return  0x0


v171_service_rx_frame_gap:
        ; Foreground parser-stall guard.  Keep the parser front-end untouched
        ; and watch for a non-empty frame state that stops receiving bytes.
        movlb   0x00
        movf    rx_frame_position, F, B
        btfsc   STATUS, Z, A
        bra     v171_service_rx_frame_gap_clear
        movf    rx_ring_wr, W, B
        cpfseq  rx_ring_rd, B
        bra     v171_service_rx_frame_gap_reload
        movf    v171_rx_frame_gap_timeout, F, BANKED
        bnz     v171_service_rx_frame_gap_count
        movlw   V171_RX_FRAME_GAP_RELOAD
        movwf   v171_rx_frame_gap_timeout, BANKED
        return  0x0

v171_service_rx_frame_gap_count:
        infsnz  v171_rx_frame_gap_timeout, F, BANKED
        bra     v171_service_rx_frame_gap_expired
        return  0x0

v171_service_rx_frame_gap_reload:
        movlw   V171_RX_FRAME_GAP_RELOAD
        movwf   v171_rx_frame_gap_timeout, BANKED
        return  0x0

v171_service_rx_frame_gap_clear:
        clrf    v171_rx_frame_gap_timeout, BANKED
        return  0x0

v171_service_rx_frame_gap_expired:
        clrf    rx_frame_position, BANKED
        clrf    v171_rx_frame_gap_timeout, BANKED
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
display_loop_iteration:                                               ; address: 0x000cb2

        bsf     INTCON, RBIE, A                             ; reg: 0xff2, bit: 3

flow_display_loop_iteration_0CB4:                                                  ; address: 0x000cb4

        call    button_scan_debounce, 0x0                           ; dest: 0x0008ac
        call    v171_service_pending_ir_decode, 0x0                 ; deferred RC5 decode
        movlb   0x00
        call    rx_parser_entry, 0x0                           ; dest: 0x00044a
        call    v171_service_rx_frame_gap, 0x0                     ; legacy-link parser stall guard
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
        bc      v171_ir_endpoint_done
        bsf     control_flags, 0x3, A                    ; event_exit
        bra     v171_ir_endpoint_done

v171_ir_wake_case:
        ; V1.64b explicit wake (RC5 0x3B): emit [B0, 0x03, 0x01] and
        ; set event_exit.  Forces wake regardless of current state.
        rcall   v171_send_wake_cmd_frame
        bc      v171_ir_endpoint_done
        bsf     control_flags, 0x3, A                    ; event_exit

v171_ir_endpoint_done:
        bsf     control_flags, IR_ARMED, A
        return  0x0

v171_send_standby_cmd_frame:
        ; Emit [0xB0, 0x03, 0x00] — broadcast CMD standby/wake with
        ; data = 0 (standby).  V1.71 atomic: either all 3 bytes commit
        ; or none do (see tx_ring_reserve_3 header for rationale).  On
        ; saturation, returns C=1 with zero bytes on the wire — MAIN
        ; cannot observe a partial frame.
        ; `call` (not `rcall`) because tx_ring_reserve_3 lives in the
        ; low-address helper cluster and is outside ±1024-word range.
        call    tx_ring_reserve_3, 0x0
        bc      v171_send_standby_cmd_frame_aborted
        movlw   0xB0
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        movlw   0x03
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        clrf    tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        return  0x0

v171_send_standby_cmd_frame_aborted:
        return  0x0

v171_send_wake_cmd_frame:
        ; Emit [0xB0, 0x03, 0x01] — broadcast CMD standby/wake with
        ; data = 1 (wake).  V1.71 atomic; see v171_send_standby_cmd_frame
        ; comment.  `call` for the same range reason as the standby
        ; sibling above.
        call    tx_ring_reserve_3, 0x0
        bc      v171_send_wake_cmd_frame_aborted
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

v171_send_wake_cmd_frame_aborted:
        return  0x0

v171_send_preset_frame_txonly:
        ; ---------------------------------------------------------------
        ; V1.71 Layer 2 helper: emit [B0, 0x20, preset_byte] only, NO
        ; EEPROM write.  preset_byte = 0 when PRESET_BIT clear (A),
        ; 1 when set (B).  Used by full_sync_burst's periodic emit so
        ; broadcasting preset every full-sync cycle does NOT chew
        ; through the EEPROM endurance budget (~100k writes/cell).
        ;
        ; V1.71 atomic: either all 3 bytes commit or none (partial
        ; frames cannot fuse the next unrelated TX byte as "data").
        ; `call` (not `rcall`) because this helper lives in the far
        ; V1.71 inline-feature cluster, outside rcall range of
        ; tx_ring_reserve_3.
        ; ---------------------------------------------------------------
        call    tx_ring_reserve_3, 0x0
        bc      v171_send_preset_frame_txonly_aborted
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
        return  0x0

v171_send_preset_frame_txonly_aborted:
        return  0x0

v171_send_preset_frame_and_persist:
        ; ---------------------------------------------------------------
        ; V1.71 inline helper: emit [B0, 0x20, preset_byte] AND persist
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
        btfsc   control_flags, PRESET_BIT, A
        movlw   0x01
        call    eeprom_write_byte, 0x0
        return  0x0

v171_send_preset_frame_and_persist_aborted:
        return  0x0

v171_preset_screen:
        ; ---------------------------------------------------------------
        ; V1.71 inline (V1.61b): preset A/B menu screen body
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

        ; Row 1: "Active: X       " where X is A or B based on PRESET_BIT.
        movlw   0xC0                                       ; LCD cursor row 1 col 0
        call    lcd_command, 0x0
        movlw   'A'
        call    lcd_char_write, 0x0
        movlw   'c'
        call    lcd_char_write, 0x0
        movlw   't'
        call    lcd_char_write, 0x0
        movlw   'i'
        call    lcd_char_write, 0x0
        movlw   'v'
        call    lcd_char_write, 0x0
        movlw   'e'
        call    lcd_char_write, 0x0
        movlw   ':'
        call    lcd_char_write, 0x0
        movlw   ' '
        call    lcd_char_write, 0x0
        movlw   'A'
        btfsc   control_flags, PRESET_BIT, A
        movlw   'B'
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

        ; Snapshot PRESET_BIT in bank-1 0x72 for dirty-check on next loop
        movlb   0x01
        clrf    0x72, BANKED
        btfsc   control_flags, PRESET_BIT, A
        incf    0x72, F, BANKED

v171_preset_loop:
        movlb   0x00
        call    display_loop_iteration, 0x0
        ; Compare current PRESET_BIT against snapshot — if flipped,
        ; redraw; otherwise fall through to button scan.
        movlb   0x00
        btfsc   control_flags, 0x3, A                    ; event_exit bit?
        bcf     control_flags, 0x3, A
        clrf    WREG, A
        btfsc   control_flags, PRESET_BIT, A
        movlw   0x01
        movlb   0x01
        xorwf   0x72, W, BANKED
        movlb   0x00
        bz      v171_prs_check_up
        goto    v171_prs_screen_draw

v171_prs_check_up:
        btfss   0x9a, 0x1, B                              ; UP pressed?
        goto    v171_prs_check_down
        btfss   control_flags, PRESET_BIT, A             ; already A?
        goto    v171_preset_loop                          ; yes — nothing to do
        bcf     control_flags, PRESET_BIT, A             ; flip to A
        rcall   v171_send_preset_frame_and_persist
        goto    v171_prs_screen_draw

v171_prs_check_down:
        btfss   0x9a, 0x2, B                              ; DOWN pressed?
        goto    v171_preset_exit_check
        btfsc   control_flags, PRESET_BIT, A             ; already B?
        goto    v171_preset_loop                          ; yes — nothing to do
        bsf     control_flags, PRESET_BIT, A             ; flip to B
        rcall   v171_send_preset_frame_and_persist
        goto    v171_prs_screen_draw

v171_preset_exit_check:
        bcf     control_flags, 0x3, A                    ; clear event_exit
        clrf    WREG, A
        btfsc   0x9a, 0x5, B                              ; RIGHT pressed?
        movlw   0x01
        movwf   (Common_RAM + 24), A                      ; ram_0x018
        clrf    WREG, A
        btfsc   0x9a, 0x4, B                              ; LEFT pressed?
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A
        movlw   0x01
        btfsc   control_flags, CONNECTED, A              ; disconnected → exit
        clrf    WREG, A
        iorwf   (Common_RAM + 24), F, A
        btfsc   STATUS, Z, A
        bra     v171_preset_loop                          ; no exit condition — loop
        movlb   0x00
        return  0x0


; ===========================================================================
; V1.71 Layer 5 Phase B + Tier-1 Phase 3.4 — Diagnostics page
; ---------------------------------------------------------------------------
; Per-PB Option-D sparse renderer for the Tier-1 Diagnostics page.
; Rewritten in Phase 3.4 (V32_DIAG_TIER1_SPEC.md §"LCD layouts (Option D
; -- locked)") to replace the dual-PB legacy renderer that displayed
; both PBs simultaneously on a single screen.  The new design renders
; ONE PB per page (state 4 = PB1, state 5 = PB2) so that:
;   * Per-PB layout has 32 chars to spend on at most 11 cells per PB
;     -- enough room for sparse rendering of all 7 runtime + 4 reset-
;     cause cells WITHOUT prefix overhead eating the available width.
;   * Operator-glanceable: silent PB shows "PBn" + "n/a"; healthy PB
;     shows "PBn" + "OK"; degraded PB shows the non-zero cells in the
;     fixed display order I D S B R A P O V W X.
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
;                                     the 7 runtime cells I/D/S/B/R/A/P
;                                     plus the 3 abnormal-reset cells
;                                     V/W/X; the POR `O` flag may be 1
;                                     on a normal cold boot and does
;                                     NOT count toward the abnormal
;                                     total)
;     Row 1: "OK" + 14 spaces
;   Absent (present mask bit clear):
;     Row 0: "PBn" + 13 spaces
;     Row 1: "n/a" + 13 spaces
;   Degraded (1 <= count <= 9):
;     Row 0: "PBn:" + " X#" * min(count,4) + spaces to col 16
;            (each " X#" = 3 chars: leading space + letter + value)
;     Row 1: if count <= 4 -> 16 spaces (entire row blank);
;            else "X#" + " X#" * (count-5) + spaces to col 16
;            (first row-1 entry has no leading space; subsequent
;            entries get a leading space).
;   Overflow (count >= 10):
;     Row 0: "PBn:" + " X# X# X# X#" (4 entries, full width)
;     Row 1: "X# X# X# X# X#" (5 entries, 14 chars) + ".."
;
; Counter encoding (unchanged from Phase B baseline):
;   0 -> (cell omitted entirely from sparse render)
;   1..9 -> '1'..'9'
;   A..E -> 'A'..'E'
;   F+   -> '+' (saturated)
;
; Display order (static, matches cache slot order):
;   0=I 1=D 2=S 3=B 4=R 5=A 6=P 7=O 8=V 9=W 10=X
; -- runtime counters first (I..P), reset-cause flags last (O..X).
;
; The screen body loops calling display_loop_iteration each tick.  A
; 16-bit countdown (v171_diag_poll_lo/hi) gates the next cmd 0x21
; query; on each expiry we alternate between PB1 and PB2 so each PB
; refreshes at half the cadence (~ once per 2 s at the 0x80 reload).
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
        movwf   v171_diag_render_pb_index, BANKED
        movlb   0x00
        ; fall through to v171_diag_screen

v171_diag_screen:
        ; First-entry setup: if no PB has ever replied, initialize
        ; target=0 so the very first cadence-driven query goes to PB1
        ; per spec.  Target now toggles only on BF/27 reception (the
        ; LAST frame of the 7-frame burst), not in the cadence loop,
        ; so we don't pre-flip it any more.  Subsequent entries pick
        ; up the existing alternating target without a reset.
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
        clrf    v171_diag_reset_seen, BANKED
        movf    v171_diag_present, F, BANKED
        bnz     v171_diag_screen_skip_init
        bcf     v171_diag_target, 0, BANKED
v171_diag_screen_skip_init:
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
        clrf    v171_diag_poll_lo, BANKED
        clrf    v171_diag_poll_hi, BANKED
        movf    v171_diag_present, W, BANKED
        movwf   v171_diag_present_snap, BANKED
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
        movf    v171_diag_render_pb_index, W, BANKED
        addlw   0x31                                       ; pb_index 0->'1', 1->'2'
        movlb   0x00
        call    lcd_char_write, 0x0

        ; --- Decide layout: absent / healthy / degraded ---
        ; Compute per-PB present-mask bit (PB1 -> 0x01, PB2 -> 0x02).
        movlb   0x01
        movlw   0x01
        btfsc   v171_diag_render_pb_index, 0, BANKED
        movlw   0x02
        andwf   v171_diag_present, W, BANKED
        bnz     v171_diag_screen_present
        ; --- ABSENT path ---
        bra     v171_diag_render_absent
v171_diag_screen_present:
        ; --- Pass 1: count cells across 11 cache slots in 3 sub-passes:
        ;     [0..6]  = runtime counters (I D S B R A P): always abnormal.
        ;     [7]     = POR flag (O):                     "expected" -- set on
        ;                                                 every cold-init via
        ;                                                 the Phase 2.2 cascade,
        ;                                                 so it does NOT count
        ;                                                 as abnormal (else the
        ;                                                 healthy "OK" gate
        ;                                                 below would be
        ;                                                 unreachable).
        ;     [8..10] = abnormal reset flags (V W X = BOR / WDT / SW).
        ;
        ; v171_diag_render_count tracks all-11 non-zero count (used for
        ; degraded layout's row-1 entry-count gating).
        ; v171_diag_render_abnormal tracks the runtime + abnormal-reset
        ; subset (used for the healthy-vs-degraded gate below).
        ;
        ; Healthy "OK" displays when abnormal == 0 (regardless of POR).
        ; The Option-D layout's "OK" omits POR from the screen -- POR
        ; is "expected" and not operator-actionable.  Operators see
        ; "OK" for a clean cold-boot regardless of which reset cell is
        ; set, as long as no runtime counters have fired and no
        ; abnormal reset (BOR/WDT/SW) is pending.
        rcall   v171_diag_load_fsr1_base
        movlb   0x01
        clrf    v171_diag_render_count, BANKED
        clrf    v171_diag_render_abnormal, BANKED
        ; Sub-pass A: walk runtime cells [0..6], increment BOTH counters.
        movlw   0x07
        movwf   v171_diag_render_walk_idx, BANKED
v171_diag_count_runtime_loop:
        movf    POSTINC1, W, A
        bz      v171_diag_count_runtime_skip
        incf    v171_diag_render_count, F, BANKED
        incf    v171_diag_render_abnormal, F, BANKED
v171_diag_count_runtime_skip:
        decfsz  v171_diag_render_walk_idx, F, BANKED
        bra     v171_diag_count_runtime_loop
        ; Sub-pass B: cell [7] = POR.  Increment only the all-11 count.
        movf    POSTINC1, W, A
        bz      v171_diag_count_por_skip
        incf    v171_diag_render_count, F, BANKED
v171_diag_count_por_skip:
        ; Sub-pass C: walk abnormal-reset cells [8..10], increment BOTH.
        movlw   0x03
        movwf   v171_diag_render_walk_idx, BANKED
v171_diag_count_abnormal_loop:
        movf    POSTINC1, W, A
        bz      v171_diag_count_abnormal_skip
        incf    v171_diag_render_count, F, BANKED
        incf    v171_diag_render_abnormal, F, BANKED
v171_diag_count_abnormal_skip:
        decfsz  v171_diag_render_walk_idx, F, BANKED
        bra     v171_diag_count_abnormal_loop
        ; --- Branch on abnormal (NOT all-11 count) ---
        movf    v171_diag_render_abnormal, F, BANKED
        bz      v171_diag_render_healthy
        bra     v171_diag_render_degraded

; --- ABSENT layout: row 0 = "PBn" + 13 spaces, row 1 = "n/a" + 13 spaces.
v171_diag_render_absent:
        movlb   0x01
        movlw   0x0D
        movwf   v171_diag_lcd_pad_count, BANKED
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
        movwf   v171_diag_lcd_pad_count, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
        bra     v171_diag_screen_armed

; --- HEALTHY layout: row 0 = "PBn" + 13 spaces, row 1 = "OK" + 14 spaces.
v171_diag_render_healthy:
        movlb   0x01
        movlw   0x0D
        movwf   v171_diag_lcd_pad_count, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
        movlw   0xC0                                       ; LCD cursor row 1 col 0
        call    lcd_command, 0x0
        movlw   'O'
        call    lcd_char_write, 0x0
        movlw   'K'
        call    lcd_char_write, 0x0
        movlb   0x01
        movlw   0x0E
        movwf   v171_diag_lcd_pad_count, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
        bra     v171_diag_screen_armed

; --- DEGRADED layout: row 0 = "PBn:" + sparse row-0 + pad,
;                     row 1 = sparse row-1 + (pad or "..").
v171_diag_render_degraded:
        ; Finish row-0 prefix: emit ':' (col 3).
        movlw   ':'
        call    lcd_char_write, 0x0

        ; --- Row 0 walk: emit up to 4 non-zero cells as " X#" each. ---
        rcall   v171_diag_load_fsr1_base
        movlb   0x01
        clrf    v171_diag_render_emitted, BANKED
        clrf    v171_diag_render_walk_idx, BANKED
v171_diag_row0_loop:
        movlw   0x0B
        cpfslt  v171_diag_render_walk_idx, BANKED          ; idx >= 11 -> done
        bra     v171_diag_row0_done
        movlw   0x04
        cpfslt  v171_diag_render_emitted, BANKED          ; emitted >= 4 -> done
        bra     v171_diag_row0_done
        movf    POSTINC1, W, A
        movwf   v171_diag_render_value, BANKED
        bz      v171_diag_row0_advance
        ; Non-zero cell -- emit " <letter><val>" (3 chars).
        movlb   0x00
        movlw   ' '
        call    lcd_char_write, 0x0
        movlb   0x01
        movf    v171_diag_render_walk_idx, W, BANKED
        rcall   v171_diag_letter_for_idx
        movlb   0x00
        call    lcd_char_write, 0x0
        movlb   0x01
        movf    v171_diag_render_value, W, BANKED
        movlb   0x00
        rcall   v171_diag_emit_nib_w
        movlb   0x01
        incf    v171_diag_render_emitted, F, BANKED
v171_diag_row0_advance:
        incf    v171_diag_render_walk_idx, F, BANKED
        bra     v171_diag_row0_loop
v171_diag_row0_done:
        ; Pad row 0: each emitted entry consumes 3 chars; row-0 tail
        ; has 12 chars (cols 4..15).  pad_count = 12 - emitted*3.
        movf    v171_diag_render_emitted, W, BANKED
        addwf   WREG, W, A                                 ; W = emitted*2
        addwf   v171_diag_render_emitted, W, BANKED        ; W = emitted*3
        sublw   0x0C                                       ; W = 12 - emitted*3
        movwf   v171_diag_lcd_pad_count, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces

        ; --- Row 1 cursor ---
        movlw   0xC0                                       ; LCD cursor row 1 col 0
        call    lcd_command, 0x0

        ; If count <= 4, no entries on row 1 -- write 16 spaces.
        movlb   0x01
        movlw   0x05
        cpfslt  v171_diag_render_count, BANKED             ; count >= 5 ?
        bra     v171_diag_row1_walk_setup
        movlw   0x10
        movwf   v171_diag_lcd_pad_count, BANKED
        movlb   0x00
        rcall   v171_diag_pad_spaces
        bra     v171_diag_screen_armed

v171_diag_row1_walk_setup:
        ; Walk again, skipping the first 4 non-zeros (already on row 0),
        ; emitting up to 5 more on row 1.
        rcall   v171_diag_load_fsr1_base
        movlb   0x01
        clrf    v171_diag_render_emitted, BANKED
        clrf    v171_diag_render_skipped, BANKED
        clrf    v171_diag_render_walk_idx, BANKED
v171_diag_row1_loop:
        movlw   0x0B
        cpfslt  v171_diag_render_walk_idx, BANKED          ; idx >= 11 -> done
        bra     v171_diag_row1_done
        movlw   0x05
        cpfslt  v171_diag_render_emitted, BANKED           ; emitted >= 5 -> done
        bra     v171_diag_row1_done
        movf    POSTINC1, W, A
        movwf   v171_diag_render_value, BANKED
        bz      v171_diag_row1_advance
        ; Non-zero cell -- skip the first 4 (they were emitted on row 0).
        movlw   0x04
        cpfslt  v171_diag_render_skipped, BANKED           ; skipped >= 4 -> emit
        bra     v171_diag_row1_emit
        incf    v171_diag_render_skipped, F, BANKED
        bra     v171_diag_row1_advance
v171_diag_row1_emit:
        ; First entry on row 1 has no leading space; subsequent entries
        ; get a " " separator first.
        movf    v171_diag_render_emitted, F, BANKED
        bz      v171_diag_row1_emit_no_sep
        movlb   0x00
        movlw   ' '
        call    lcd_char_write, 0x0
        bra     v171_diag_row1_emit_letter
v171_diag_row1_emit_no_sep:
        movlb   0x00
v171_diag_row1_emit_letter:
        movlb   0x01
        movf    v171_diag_render_walk_idx, W, BANKED
        rcall   v171_diag_letter_for_idx
        movlb   0x00
        call    lcd_char_write, 0x0
        movlb   0x01
        movf    v171_diag_render_value, W, BANKED
        movlb   0x00
        rcall   v171_diag_emit_nib_w
        movlb   0x01
        incf    v171_diag_render_emitted, F, BANKED
v171_diag_row1_advance:
        incf    v171_diag_render_walk_idx, F, BANKED
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
        cpfslt  v171_diag_render_count, BANKED             ; count >= 10 ?
        bra     v171_diag_row1_overflow
        ; Non-overflow: pad to 16.
        movf    v171_diag_render_emitted, W, BANKED
        addwf   WREG, W, A                                 ; W = emitted*2
        addwf   v171_diag_render_emitted, W, BANKED        ; W = emitted*3
        sublw   0x11                                       ; W = 17 - emitted*3
        movwf   v171_diag_lcd_pad_count, BANKED
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
; v171_diag_load_fsr1_base -- set FSR1 to the per-PB cache base.
; ---------------------------------------------------------------------------
; PB index 0 -> FSR1 = 0x180 (v171_diag_pb1_i physical address)
; PB index 1 -> FSR1 = 0x18B (v171_diag_pb2_i physical address)
;
; Reads v171_diag_render_pb_index from BANK 1.  Leaves BSR=1 on return.
; ---------------------------------------------------------------------------
v171_diag_load_fsr1_base:
        movlb   0x01
        btfsc   v171_diag_render_pb_index, 0, BANKED
        bra     v171_diag_load_fsr1_pb2
        lfsr    0x1, 0x180
        return  0x0
v171_diag_load_fsr1_pb2:
        lfsr    0x1, 0x18B
        return  0x0

; ---------------------------------------------------------------------------
; v171_diag_letter_for_idx -- decode a cell index (0..10) to its letter.
; ---------------------------------------------------------------------------
; Display order: I D S B R A P O V W X (matches cache slot order).
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
        movwf   v171_diag_render_letter_tmp, BANKED
        movlw   'I'
        tstfsz  v171_diag_render_letter_tmp, BANKED
        bra     v171_diag_letter_dec_to_d
        return  0x0
v171_diag_letter_dec_to_d:
        decf    v171_diag_render_letter_tmp, F, BANKED
        movlw   'D'
        tstfsz  v171_diag_render_letter_tmp, BANKED
        bra     v171_diag_letter_dec_to_s
        return  0x0
v171_diag_letter_dec_to_s:
        decf    v171_diag_render_letter_tmp, F, BANKED
        movlw   'S'
        tstfsz  v171_diag_render_letter_tmp, BANKED
        bra     v171_diag_letter_dec_to_b
        return  0x0
v171_diag_letter_dec_to_b:
        decf    v171_diag_render_letter_tmp, F, BANKED
        movlw   'B'
        tstfsz  v171_diag_render_letter_tmp, BANKED
        bra     v171_diag_letter_dec_to_r
        return  0x0
v171_diag_letter_dec_to_r:
        decf    v171_diag_render_letter_tmp, F, BANKED
        movlw   'R'
        tstfsz  v171_diag_render_letter_tmp, BANKED
        bra     v171_diag_letter_dec_to_a
        return  0x0
v171_diag_letter_dec_to_a:
        decf    v171_diag_render_letter_tmp, F, BANKED
        movlw   'A'
        tstfsz  v171_diag_render_letter_tmp, BANKED
        bra     v171_diag_letter_dec_to_p
        return  0x0
v171_diag_letter_dec_to_p:
        decf    v171_diag_render_letter_tmp, F, BANKED
        movlw   'P'
        tstfsz  v171_diag_render_letter_tmp, BANKED
        bra     v171_diag_letter_dec_to_o
        return  0x0
v171_diag_letter_dec_to_o:
        decf    v171_diag_render_letter_tmp, F, BANKED
        movlw   'O'
        tstfsz  v171_diag_render_letter_tmp, BANKED
        bra     v171_diag_letter_dec_to_v
        return  0x0
v171_diag_letter_dec_to_v:
        decf    v171_diag_render_letter_tmp, F, BANKED
        movlw   'V'
        tstfsz  v171_diag_render_letter_tmp, BANKED
        bra     v171_diag_letter_dec_to_w
        return  0x0
v171_diag_letter_dec_to_w:
        decf    v171_diag_render_letter_tmp, F, BANKED
        movlw   'W'
        tstfsz  v171_diag_render_letter_tmp, BANKED
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
        movf    v171_diag_lcd_pad_count, F, BANKED
        bz      v171_diag_pad_spaces_done                  ; count == 0 -> no-op
v171_diag_pad_spaces_loop:
        movlb   0x00
        movlw   ' '
        call    lcd_char_write, 0x0
        movlb   0x01                                       ; lcd_char_write may have touched BSR
        decfsz  v171_diag_lcd_pad_count, F, BANKED
        bra     v171_diag_pad_spaces_loop
v171_diag_pad_spaces_done:
        movlb   0x00
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
        call    display_loop_iteration, 0x0
        movlb   0x00
        ; Decrement the 16-bit poll countdown.  When it reaches zero,
        ; enqueue a cmd 0x21 query for the current target PB and reload.
        movlb   0x01
        movf    v171_diag_poll_lo, W, BANKED
        iorwf   v171_diag_poll_hi, W, BANKED
        bnz     v171_diag_loop_dec
        ; Countdown expired.  Normally target only toggles on BF/27
        ; reception (in v171_bf2x_case_check) so it stays stable for
        ; the full query/reply round-trip.  But that means a SILENT
        ; or unsupported PB would never advance the target -- polling
        ; would lock onto the silent slot forever and the responding
        ; PB would never get re-queried.  Skip-on-silent gate: if
        ; RUNTIME_PENDING is still set when the cadence expires, the
        ; previous query never completed, so advance target now (and
        ; clear PENDING) before sending the next query.
        movlb   0x01
        btfss   v171_diag_flags, V171_DIAG_FLAG_RUNTIME_PENDING, BANKED
        bra     v171_diag_send_now                         ; previous reply landed
        ; Previous query timed out -- skip the silent target.
        btg     v171_diag_target, 0, BANKED
v171_diag_send_now:
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
        btfss   v171_diag_flags, V171_DIAG_FLAG_RESET_PENDING, BANKED
        bra     v171_diag_check_reset_seen                 ; not pending -- proceed
        ; --- RESET_PENDING set: timeout countdown ---
        decf    v171_diag_reset_timeout, F, BANKED
        bnz     v171_diag_send_runtime_only                ; not yet expired
        ; --- Timeout: spec "give up" path ---
        ; Mark the in-flight reset target as reset_seen so the gate
        ; below stays closed for the rest of this Diag-page visit.
        ; Using v171_diag_reset_target (snapshot at send time), NOT
        ; v171_diag_target (which may have toggled).
        movlw   0x01                                       ; PB1 mask
        btfsc   v171_diag_reset_target, 0, BANKED
        movlw   0x02                                       ; PB2 mask
        iorwf   v171_diag_reset_seen, F, BANKED
        bcf     v171_diag_flags, V171_DIAG_FLAG_RESET_PENDING, BANKED
        bra     v171_diag_send_runtime_only
v171_diag_check_reset_seen:
        ; Compute reset_seen mask for the current target: bit0 for PB1,
        ; bit1 for PB2.  If already seen (BF/2B received OR timed out),
        ; skip the cmd 0x22 fire and fall through to cmd 0x21.
        movlw   0x01                                       ; PB1 mask
        btfsc   v171_diag_target, 0, BANKED
        movlw   0x02                                       ; PB2 mask
        andwf   v171_diag_reset_seen, W, BANKED
        bnz     v171_diag_send_runtime_only                ; already seen for this PB
        ; --- reset_seen.target clear AND RESET_PENDING clear: fire ---
        ; Snapshot v171_diag_target.0 into v171_diag_reset_target so
        ; the timeout path knows which PB to give up on (target may
        ; toggle independently before BF/2B arrives or times out).
        movf    v171_diag_target, W, BANKED
        andlw   0x01
        movwf   v171_diag_reset_target, BANKED
        ; Reload timeout counter.  Each cadence cycle is ~1 s so
        ; V171_DIAG_RESET_TIMEOUT_RELOAD = 4 gives ~4 s timeout per spec.
        movlw   V171_DIAG_RESET_TIMEOUT_RELOAD
        movwf   v171_diag_reset_timeout, BANKED
        bsf     v171_diag_flags, V171_DIAG_FLAG_RESET_PENDING, BANKED
        movlb   0x00
        rcall   v171_diag_send_reset_query
        movlb   0x01
v171_diag_send_runtime_only:
        bsf     v171_diag_flags, V171_DIAG_FLAG_RUNTIME_PENDING, BANKED
        movlb   0x00
        rcall   v171_diag_send_runtime_query
        movlb   0x01
        movlw   V171_DIAG_POLL_RELOAD_LO
        movwf   v171_diag_poll_lo, BANKED
        movlw   V171_DIAG_POLL_RELOAD_HI
        movwf   v171_diag_poll_hi, BANKED
        movlb   0x00
        bra     v171_diag_check_redraw

v171_diag_loop_dec:
        ; 16-bit decrement with borrow.
        movf    v171_diag_poll_lo, W, BANKED
        bnz     v171_diag_loop_dec_lo_only
        decf    v171_diag_poll_hi, F, BANKED
v171_diag_loop_dec_lo_only:
        decf    v171_diag_poll_lo, F, BANKED
        movlb   0x00

v171_diag_check_redraw:
        ; Redraw the screen if EITHER the present mask changed since
        ; the last draw OR the parser case set the DIRTY flag (a fresh
        ; counter value landed in the cache).  Snapshot + flag both
        ; live in BANK 1 — must NOT be the access-bank ram_0x005
        ; scratch cell because display_loop_iteration and the LCD
        ; char-write helpers stomp it on every tick.
        movlb   0x01
        btfsc   v171_diag_flags, V171_DIAG_FLAG_DIRTY, BANKED
        bra     v171_diag_do_redraw                        ; cache changed
        movf    v171_diag_present, W, BANKED
        xorwf   v171_diag_present_snap, W, BANKED
        bz      v171_diag_redraw_skip                      ; no change
v171_diag_do_redraw:
        movf    v171_diag_present, W, BANKED
        movwf   v171_diag_present_snap, BANKED
        bcf     v171_diag_flags, V171_DIAG_FLAG_DIRTY, BANKED
        movlb   0x00
        goto    v171_diag_screen_draw
v171_diag_redraw_skip:
        movlb   0x00

v171_diag_check_buttons:
        bcf     control_flags, 0x3, A                      ; clear event_exit
        clrf    WREG, A
        btfsc   0x9a, 0x5, B                               ; RIGHT pressed?
        movlw   0x01
        movwf   (Common_RAM + 24), A                       ; ram_0x018
        clrf    WREG, A
        btfsc   0x9a, 0x4, B                               ; LEFT pressed?
        movlw   0x01
        iorwf   (Common_RAM + 24), F, A
        movlw   0x01
        btfsc   control_flags, CONNECTED, A                ; disconnected → exit
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
; v171_diag_send_query — enqueue a 3-byte cmd 0x21 query for the current
; target PB.  Route is computed from v171_diag_target (0 → 0xB1 PB1,
; 1 → 0xB2 PB2).  Reuses the raw tx_byte_enqueue path (Layer-1 bounded);
; if any byte saturates the ring it is silently dropped — the caller will
; naturally retry on the next poll-cadence expiry.
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
        ; Frame atomicity: tx_byte_enqueue (Layer 1) drops a single
        ; byte on TX-ring saturation and signals via STATUS.C=1.  We
        ; check C after every byte (including the final data byte)
        ; and bail on the first dropped byte so we don't keep pumping
        ; the rest of an already-broken frame.
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
        ; the route byte first.  ram_0x028 is the V1.71 scratch range
        ; documented in the dlcp_control_ram.inc free-slot audit.
        movwf   (Common_RAM + 28), A                       ; saved cmd byte
        ; --- byte 0: route ---
        movlw   0xB1                                       ; default = PB1 query
        movlb   0x01
        btfsc   v171_diag_target, 0, BANKED                ; bit0 set -> PB2 instead
        movlw   0xB2
        movlb   0x00
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        bc      v171_diag_send_query_aborted               ; ring saturated
        ; --- byte 1: cmd byte (0x21 or 0x22) ---
        movf    (Common_RAM + 28), W, A
        movwf   tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        bc      v171_diag_send_query_aborted
        ; --- byte 2: data 0x00 (final byte) ---
        clrf    tx_data_staging, A
        call    tx_byte_enqueue, 0x0
        bc      v171_diag_send_query_aborted               ; final byte also checked
        return  0x0
v171_diag_send_query_aborted:
        ; TX ring saturated mid-frame.  Clear ONLY the pending bit
        ; matching the just-aborted query type so a sibling query
        ; that already left CONTROL keeps its tracking intact.
        ;
        ; Cmd byte (0x21 or 0x22) lives in (Common_RAM + 28); it was
        ; stashed at the top of v171_diag_send_query_w before any TX,
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
        bcf     v171_diag_flags, V171_DIAG_FLAG_RESET_PENDING, BANKED
        bra     v171_diag_send_query_aborted_done
v171_diag_send_query_aborted_runtime:
        bcf     v171_diag_flags, V171_DIAG_FLAG_RUNTIME_PENDING, BANKED
v171_diag_send_query_aborted_done:
        movlb   0x00
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

        ; Phase 3.4: rcall → call promotion.  v171_diag_pb_screen +
        ; sparse renderer added ~300 bytes ahead of this site, pushing
        ; the relative offset to display_loop_iteration past the bra/
        ; rcall ±1024-instruction limit.  call uses absolute 21-bit
        ; addressing so it's range-immune; semantics are identical.
        call    display_loop_iteration, 0x0                ; dest: 0x000cb2
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

        ; ---------------------------------------------------------------
        ; Bug #44 fix: zero V1.71 Tier-1 diag cache cells once at POR.
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
        ; FSR0 + POSTINC0; reset_seen at 0x19D cleared separately.
        ; +20 bytes total; runs once at POR / cold-init exit (NOT in
        ; app_cold_init body proper, because adding code there shifts
        ; isr_entry past 0x0003a6 and breaks the byte-identical vector
        ; block contract gated by test_v171_layer1_vector_block_byte_identical).
        lfsr    0x0, 0x180                                  ; FSR0 -> first cache cell
        movlw   0x18                                        ; 24 cells (0x180..0x197 inclusive)
        movwf   (Common_RAM + 15), A                        ; transient loop counter
flow_v171_diag_cache_zero:
        clrf    POSTINC0, A                                 ; *FSR0++ = 0
        decfsz  (Common_RAM + 15), F, A
        bra     flow_v171_diag_cache_zero
        movlb   0x01                                        ; reset_seen lives in bank 1
        clrf    v171_diag_reset_seen, BANKED                ; physical 0x19D
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
        movlw   0x07                                        ; V1.71 minor byte
        subwf   tx_data_staging, W, A                     ; reg: 0x027
        btfsc   STATUS, Z, A                                ; reg: 0xfd8, bit: 2
        goto    flow_ccs_0FA0_10F6                                   ; dest: 0x0010f6
        movlw   0x71
        movwf   EEADR, A                                    ; reg: 0xfa9
        movlw   0x07
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
        clrf    v171_waiting_grace_count_lo, B              ; reset 16-bit grace counter (lo)
        clrf    v171_waiting_grace_count_hi, B              ; reset 16-bit grace counter (hi)
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

        ; ---------------------------------------------------------------
        ; V1.71 WAITING-loop operator-recovery (2026-04-21)
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
        cpfslt  v171_waiting_grace_count_hi, B             ; skip if hi <  threshold_hi
        bra     v171_waiting_cold_armed                    ; hi >= threshold_hi -> armed
        infsnz  v171_waiting_grace_count_lo, F, B          ; bump lo; skip if lo != 0
        incf    v171_waiting_grace_count_hi, F, B          ; lo wrapped -> bump hi
        bra     v171_waiting_cold_past_grace_done          ; still in grace, no buttons
v171_waiting_cold_armed:
        btfsc   0x9a, 0x5, B                               ; RIGHT pressed?
        reset                                              ; soft CPU reset
        btfsc   0x9a, 0x4, B                               ; LEFT pressed?
        reset                                              ; soft CPU reset
v171_waiting_cold_past_grace_done:

        call    poll_frame_send, 0x0                           ; dest: 0x000b64
        movlw   0xc8
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    rx_parser_entry, 0x0                           ; dest: 0x00044a
        call    v171_service_rx_frame_gap, 0x0             ; cold WAITING parser stall guard (entry/exit movlb 0x0 absorbs rx_parser_entry BSR drift)
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

        ; ---------------------------------------------------------------
        ; V1.71 inline (V1.61b + Layer 5 + Tier-1): 6-way menu dispatch
        ; ---------------------------------------------------------------
        ; Stock V1.6b had 3 menu states (0 = Volume, 1 = Input, 2 = Setup).
        ; V1.71 inlined V1.61b (Preset as state 1) and then Layer 5
        ; (Diagnostics as state 2 between Preset and Input).  V1.71
        ; Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20) reworks the menu:
        ;
        ; - Diagnostics moves from state 2 to states 4-5 (deepest menu),
        ;   with one PB per state.  Operators reach the diag pages
        ;   intentionally during troubleshooting, not by accident
        ;   during routine browsing.
        ; - Input shifts back to state 2; Setup shifts to state 3.
        ; - PB2 Diag is ALWAYS in the menu cycle.  If only PB1 is wired
        ;   (or PB2 is silent), the renderer shows "n/a" for PB2 — see
        ;   v171_diag_pb_screen.
        ;
        ; New ring:
        ;   0 = Volume       (default fall-through)
        ;   1 = Preset       -> v171_preset_screen
        ;   2 = Input        -> control_core_service_1912
        ;   3 = Setup        -> control_core_service_13FE
        ;   4 = PB1 Diag     -> v171_diag_pb_screen with PB-index 0
        ;   5 = PB2 Diag     -> v171_diag_pb_screen with PB-index 1
        ;
        ; Nav wrap literals downstream are bumped from 0x04 (5-state ring)
        ; to 0x05 (6-state ring).
        movlb   0x00
        decfsz  0xbf, W, B                                  ; state - 1 == 0?
        goto    v171_menu_ck_state_2
        rcall   v171_preset_screen                          ; state == 1 -> Preset
        goto    flow_boot_handshake_wait_120A

v171_menu_ck_state_2:
        movlw   0x02
        cpfseq  0xbf, B
        goto    v171_menu_ck_state_3                        ; not 2 -- try Setup
        ; Tier-1: state 2 is now Input (was Diagnostics).
        call    control_core_service_1912, 0x0              ; state == 2 -> Input
        goto    flow_boot_handshake_wait_120A

v171_menu_ck_state_3:
        movlw   0x03
        cpfseq  0xbf, B
        goto    v171_menu_ck_state_4                        ; not 3 -- try PB1 Diag
        ; Tier-1: state 3 is now Setup (was Input).
        call    control_core_service_13FE, 0x0              ; state == 3 -> Setup
        goto    flow_boot_handshake_wait_120A

v171_menu_ck_state_4:
        movlw   0x04
        cpfseq  0xbf, B
        goto    boot_handshake_wait                         ; not 4 -- try PB2 Diag
        ; Tier-1: state 4 = PB1 Diag (W = PB index 0).
        movlw   0x00
        rcall   v171_diag_pb_screen
        goto    flow_boot_handshake_wait_120A

boot_handshake_wait:                                                  ; address: 0x0011fe

        movlw   0x05
        cpfseq  0xbf, B                                     ; reg: 0x0bf
        goto    flow_boot_handshake_wait_120A                                   ; dest: 0x00120a
        ; Tier-1: state 5 = PB2 Diag (W = PB index 1).
        movlw   0x01
        rcall   v171_diag_pb_screen

flow_boot_handshake_wait_120A:                                                  ; address: 0x00120a

        bcf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfss   0x9a, 0x5, B                                ; reg: 0x09a
        bsf     STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        btfsc   STATUS, OV, A                               ; reg: 0xfd8, bit: 3
        goto    flow_display_state_entry_1226                                   ; dest: 0x001226
        ; V1.71: nav DOWN upper-bound bumped from 2 -> 3 (V1.61b ring),
        ; then Layer 5 bumped 3 -> 4 (5-state ring).  Tier-1 bumps it
        ; 4 -> 5 so the 6-state Vol/Preset/Input/Setup/PB1Diag/PB2Diag
        ; ring wraps cleanly (DOWN at state 5 -> state 0).
        movlw   0x05
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
        ; V1.71: nav UP wrap target bumped from 2 -> 3 (V1.61b ring),
        ; then Layer 5 bumped 3 -> 4 (5-state ring).  Tier-1 bumps it
        ; 4 -> 5 so the 6-state ring wraps cleanly (UP at state 0 ->
        ; state 5 = PB2 Diag).
        movlw   0x05
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

        ; ---------------------------------------------------------------
        ; V1.71 inline (V1.62b): full sentinel-driven reconnect loop
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
        clrf    0x73, BANKED
        ; ---------------------------------------------------------------
        ; V1.71 reconnect-loop operator-recovery grace counter (2026-04-21)
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
        clrf    v171_waiting_grace_count_lo, B
        clrf    v171_waiting_grace_count_hi, B

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
        cpfslt  v171_waiting_grace_count_hi, B             ; skip if hi <  threshold_hi
        bra     v171_reconnect_armed                       ; hi >= threshold_hi -> armed
        infsnz  v171_waiting_grace_count_lo, F, B          ; bump lo; skip if lo != 0
        incf    v171_waiting_grace_count_hi, F, B          ; lo wrapped -> bump hi
        bra     v171_reconnect_past_grace_done             ; still in grace
v171_reconnect_armed:
        btfsc   0x9a, 0x5, B                               ; RIGHT pressed?
        reset                                              ; soft CPU reset
        btfsc   0x9a, 0x4, B                               ; LEFT pressed?
        reset                                              ; soft CPU reset
v171_reconnect_past_grace_done:
        movlb   0x00
        call    poll_frame_send, 0x0                           ; dest: 0x000b64
        movlw   0xc8
        call    delay_short, 0x0                           ; dest: 0x0001bc
        call    rx_parser_entry, 0x0                           ; dest: 0x00044a
        call    v171_service_rx_frame_gap, 0x0             ; reconnect WAITING parser stall guard (entry/exit movlb 0x0 absorbs rx_parser_entry BSR drift)

        ; Accumulate sentinel-cleared bits into ram_0x018.
        ; Each block: if sentinel != 0x80 → set ram_0x018 to 1, else
        ; AND 1 (first test initializes, subsequent tests AND-reduce).
        ; Bug #45 CONTROL-side fix (2026-05-03): the original V1.71
        ; AND-reduce had a spurious `clrf WREG, A` between the `subwf`
        ; and the `btfss STATUS, Z, A` test in each of the four blocks
        ; below.  CLRF on PIC18 always sets STATUS.Z = 1, so the
        ; subsequent `btfss STATUS, Z` ALWAYS skipped the `movlw 0x01`,
        ; leaving WREG = 0 from the clrf.  ram_0x018 was therefore set
        ; to 0 unconditionally, the `bnz v171_reconnect_wait_done`
        ; below NEVER fired, and CONTROL stayed parked on `Waiting
        ; for DLCP` indefinitely after a STDBY/WAKE cycle even though
        ; all four sentinels had been cleared by MAIN's status burst.
        ; The cold-boot WAITING loop (`v171_waiting_cold_past_grace_done`
        ; at asm:4747; AND-reduce body at asm:4754-4773) does NOT have
        ; the spurious clrf and works correctly -- this fix matches
        ; its proven pattern.  Removing the four `clrf WREG, A`
        ; instructions saves 8 bytes total in the V1.71 release;
        ; downstream addresses shift accordingly.
        movlw   0x80
        subwf   input_select_cache, W, B                     ; 0xB8
        btfss   STATUS, Z, A
        movlw   0x01
        movwf   (Common_RAM + 24), A                        ; ram_0x018

        movlw   0x80
        subwf   volume_cache, W, B                           ; 0xB9
        btfss   STATUS, Z, A
        movlw   0x01
        andwf   (Common_RAM + 24), F, A

        movlw   0x80
        subwf   cmd1d_setting_cache, W, B                    ; 0xA7
        btfss   STATUS, Z, A
        movlw   0x01
        andwf   (Common_RAM + 24), F, A

        movlw   0x80
        subwf   raw_status_cache, W, B                       ; 0xA1
        btfss   STATUS, Z, A
        movlw   0x01
        andwf   (Common_RAM + 24), F, A

        movf    (Common_RAM + 24), F, A
        bnz     v171_reconnect_wait_done                    ; all sentinels cleared

        ; Not done yet — increment retry counter.
        movlb   0x01
        incf    0x73, F, BANKED
        movlw   0x08
        cpfseq  0x73, BANKED
        bra     v171_reconnect_wait_body                    ; still under 8 — keep polling
        clrf    0x73, BANKED                                ; 8 retries hit — reset counter

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
        clrf    tx_ring_rd, BANKED
        clrf    tx_ring_wr, BANKED
        clrf    rx_ring_rd, BANKED
        clrf    rx_ring_wr, BANKED
        clrf    rx_frame_position, BANKED
        clrf    v171_rx_frame_gap_timeout, BANKED
        clrf    rx_parsed_cmd, A
        clrf    rx_parsed_data, A
        bra     v171_reconnect_wait_body

v171_reconnect_wait_done:
        movlb   0x01
        clrf    0x73, BANKED                                ; clear retry counter
        movlb   0x00
        bsf     control_flags, CONNECTED, A                ; mark connected

flow_reconnect_wait_loop_12CE:                                                  ; address: 0x0012ce

        ; V1.71 (V1.62b): wake frame on reconnect exit (closes the
        ; V162B_RECONNECT_WAKE_BUG gap) plus the V1.62b state re-init:
        ; reload idle timer to stock 0xEA61, zero the full-sync
        ; counter for an immediate burst, clear RECONNECT_WAIT_DONE
        ; (bit 5) and seed control_flags bit 0x032 = 1 so the
        ; post-connect path resumes correctly.
        ;
        ; V1.71 Layer B (atomic 3-byte fix): if the wake broadcast hit
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
        bnc     flow_reconnect_wait_loop_12CE_delivered
        bra     reconnect_wait_loop                         ; retry whole reconnect cycle
flow_reconnect_wait_loop_12CE_delivered:
        movlw   0x61
        movwf   idle_timeout_lo, BANKED                     ; 0x9D
        movlw   0xEA
        movwf   idle_timeout_hi, BANKED                     ; 0x9E
        clrf    full_sync_lo, BANKED                        ; 0x9F
        clrf    full_sync_hi, BANKED                        ; 0xA0
        bcf     control_flags, RECONNECT_WAIT_DONE, A       ; bit 5
        movlw   0x01
        movwf   (Common_RAM + 50), A                        ; 0x032
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
        ; V1.71 inline (V1.61b + V1.63b): preset A/B / DSP-fault indicator
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
        btfsc   control_flags, PRESET_BIT, A
        movlw   'B'
        btfsc   control_flags, DSP_FAULT_BIT, A        ; V1.63b: fault overrides
        movlw   '!'
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
        ; V1.71 Tier-1 menu rework remap: see control_core_service_1912.
        ; Setup is now state 3 in the new ring but the legacy table has
        ; Setup at index 2.  Without this remap, state 3 reads
        ; table[3] = past-end (raw code bytes) and the LCD shows
        ; gibberish for the Setup title row -- the user-reported
        ; "garbled chars over BL Timeout" symptom.  Force the Setup
        ; title to read from table[2] (the legacy Setup slot).
        movlw   0x02                                      ; legacy Setup table index
        movwf   tx_data_staging, A                        ; reg: 0x027
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
        ; V1.71 Tier-1 menu rework remap: menu_title_table is the
        ; stock V1.6b 3-entry table (Vol=0, Input=1, Setup=2).  After
        ; Phase 3.3 reshuffled the ring (Vol=0, Preset=1, Input=2,
        ; Setup=3, PB1Diag=4, PB2Diag=5), state index 2 (Input) used
        ; to read table[state]=table[2]="Setup" -- garbled title.
        ; Force the Input title to read from table[1] (the legacy
        ; Input slot) regardless of where Input lives in the new ring.
        movlw   0x01                                      ; legacy Input table index
        movwf   tx_data_staging, A                        ; reg: 0x027
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

; --- Canonical V1.71 release metadata (flashed app space, not runtime state) ---
        org     0x77b0

control_release_metadata:
        db      0x44, 0x4c, 0x43, 0x50                    ; "DLCP"
        db      0x43, 0x54, 0x52, 0x4c                    ; "CTRL"
        db      0x01, 0x07, 0x31, 0x12                    ; V1.71 + monotonic release revision
        db      0xff, 0xff, 0xff, 0xff

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
        ; V1.71 identity bytes at EEPROM 0x70..0x73.
        ; NOTE: EEPROM[0x73] is runtime-owned and must not be repurposed as a
        ; release counter. Canonical release revision lives in
        ; control_release_metadata at 0x77B0.
        db      0x01                                        ; EEPROM 0x70: major
        db      0x07                                        ; EEPROM 0x71: minor (V1.7 family)
        db      0x31                                        ; EEPROM 0x72: '1' (V1.71)
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
