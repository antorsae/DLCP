; ===========================================================================
; V3.2 MAIN — unit-test harness for main_core_service_265c
; ===========================================================================
; This file is APPENDED to a patched copy of src/dlcp_fw/asm/dlcp_main_v32.asm
; where the 0x1000 user-reset `goto flow_app_entry_1014` has been replaced
; with `goto unit_test_entry`, so the chip boots directly into this driver
; instead of the production cold-init path.  The rest of the V3.2 image
; remains intact so that main_core_service_265c, main_flash_service_46de,
; eeprom_read_byte, and eeprom_write_blocking are all reachable.
;
; Test vector
; -----------
; Primes the 19 static source-RAM bytes with distinct nibbled values
; (0xA0..0xB2), sets all four static-block dirty flags (ram_0x0BD bits 0-3;
; bits 4 and 5 are left clear to skip the runtime 0x50..0x5E loop and the
; preset_persist_filename call — those are structurally minimal already and
; not part of the rewrite scope), arms event_flags.bit0, and calls
; main_core_service_265c.  Then it reads EEPROM[0x00..0x14] into a known
; RAM buffer and signals completion via a fixed status byte.
;
; Observability contract (read by the Python test via gpsim `reg` cmds)
; --------------------------------------------------------------------
; 0x01FF (bank 1, offset 0xFF):  0xA5 once the driver finishes.
;                                 Any other value = test never completed.
; 0x01A0 .. 0x01B4 (21 bytes) :  EEPROM snapshot (offset 0x00..0x14).
;
; Expected values after a correct main_core_service_265c run
; ----------------------------------------------------------
;   0x1A0 (EEPROM 0x00) = 0xA3   (computed_volume_3)
;   0x1A1 (EEPROM 0x01) = 0xA2
;   0x1A2 (EEPROM 0x02) = 0xA1
;   0x1A3 (EEPROM 0x03) = 0xA0
;   0x1A4 (EEPROM 0x04) = 0xA4   (input_select)
;   0x1A5 (EEPROM 0x05) = 0xFF   (untouched; init default)
;   0x1A6 (EEPROM 0x06) = 0xFF   (untouched)
;   0x1A7 (EEPROM 0x07) = 0xA7   (ram_0x060)
;   0x1A8 (EEPROM 0x08) = 0xA8
;   0x1A9 (EEPROM 0x09) = 0xA9
;   0x1AA (EEPROM 0x0A) = 0xAA
;   0x1AB (EEPROM 0x0B) = 0xAB
;   0x1AC (EEPROM 0x0C) = 0xAC
;   0x1AD (EEPROM 0x0D) = 0xA5   (ram_0x05F)
;   0x1AE (EEPROM 0x0E) = 0xAE   (ram_0x0B8)
;   0x1AF (EEPROM 0x0F) = 0xAD   (ram_0x0B4)
;   0x1B0 (EEPROM 0x10) = 0xAF   (ram_0x09B)
;   0x1B1 (EEPROM 0x11) = 0xB0
;   0x1B2 (EEPROM 0x12) = 0xB1
;   0x1B3 (EEPROM 0x13) = 0xB2
;   0x1B4 (EEPROM 0x14) = 0xA6   (ram_0x0C3)
; ===========================================================================

UT_STATUS_READY             EQU  0xA5
UT_STATUS_ADDR_BANK1_LO     EQU  0xFF        ; BANKED write with BSR=1 -> 0x01FF
UT_EEPROM_BUF_BANK1_LO      EQU  0xA0        ; BANKED, BSR=1 -> 0x01A0


; The V3.2 source ends with `org 0xF00000` for the EEPROM data block.
; Re-seat the address to code space so gpasm emits our harness as program
; memory.  0x4A80 sits above the current last_used byte (~0x49E1 at
; HEAD) but well below the Preset B anchor at 0x4C00.
        org 0x4A80

unit_test_entry:
        ; -- Minimum init: mask interrupts and select bank 0. --
        clrf        INTCON, ACCESS
        movlb       0x0

        ; -- Prime 19 source RAM bytes (all live in bank 0). --
        movlw       0xA0
        movwf       computed_volume,   BANKED
        movlw       0xA1
        movwf       computed_volume_1, BANKED
        movlw       0xA2
        movwf       computed_volume_2, BANKED
        movlw       0xA3
        movwf       computed_volume_3, BANKED
        movlw       0xA4
        movwf       input_select,      BANKED
        movlw       0xA5
        movwf       ram_0x05F,         BANKED
        movlw       0xA6
        movwf       ram_0x0C3,         BANKED
        movlw       0xA7
        movwf       ram_0x060,         BANKED
        movlw       0xA8
        movwf       ram_0x061,         BANKED
        movlw       0xA9
        movwf       ram_0x062,         BANKED
        movlw       0xAA
        movwf       ram_0x063,         BANKED
        movlw       0xAB
        movwf       ram_0x064,         BANKED
        movlw       0xAC
        movwf       ram_0x065,         BANKED
        movlw       0xAD
        movwf       ram_0x0B4,         BANKED
        movlw       0xAE
        movwf       ram_0x0B8,         BANKED
        movlw       0xAF
        movwf       ram_0x09B,         BANKED
        movlw       0xB0
        movwf       ram_0x09C,         BANKED
        movlw       0xB1
        movwf       ram_0x09D,         BANKED
        movlw       0xB2
        movwf       ram_0x09E,         BANKED

        ; -- Arm the four static-block dirty flags (bits 0..3). --
        movlw       0x0F
        movwf       ram_0x0BD,         BANKED

        ; -- Gate: event_flags.bit0 = 1 -> main_core_service_265c will run --
        bsf         event_flags, 0,    BANKED

        ; -- Call function under test. --
        call        main_core_service_265c, 0x0

        ; -- Dump EEPROM[0x00..0x14] into RAM[0x1A0..0x1B4]. --
        lfsr        FSR2, 0x01A0
        clrf        ram_0x003, ACCESS
        clrf        ram_0x004, ACCESS
unit_test_read_loop:
        rcall       eeprom_read_byte
        movwf       POSTINC2, ACCESS
        incf        ram_0x003, F, ACCESS
        movlw       0x15
        cpfseq      ram_0x003, ACCESS
        bra         unit_test_read_loop

        ; -- Signal completion. --
        movlb       0x1
        movlw       UT_STATUS_READY
        movwf       UT_STATUS_ADDR_BANK1_LO, BANKED

unit_test_halt:
        bra         unit_test_halt
