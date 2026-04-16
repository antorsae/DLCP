; ===========================================================================
;          Hypex DLCP — CONTROL panel firmware V1.6b (raw gpdasm dump)
; ===========================================================================
; Source       : DLCP Control Firmware V1.6b.hex
; Target MCU   : Microchip PIC18F25K20 @ ~16 MHz (4 MIPS)
; Format       : raw `gpdasm -p18f25k20` output. One address per line:
;                  AAAAAA:  HHHH  mnemonic  operands
; Symbol model : NONE — no labels, no equates, no relocation. Addresses are
;                hard-coded as instruction-byte offsets from 0x000000.
; HEX policy   : COMMENT-ONLY edits. Never modify or relocate code; this
;                file is a *reference* derived from the binary, not a
;                source for assembly. Re-running gpdasm on the original
;                .hex must reproduce the body byte-for-byte.
;
; ---------------------------------------------------------------------------
; Image layout
; ---------------------------------------------------------------------------
;   0x000000        Reset vector             goto 0x007800 (label_284 / bootloader_entry)
;   0x000008        High-priority IV         goto 0x0003A6 (label_032 / isr_entry)
;   0x000018        Low-priority IV          calls 0x000190, then `bra .` halt at 0x000020
;   0x000040        Secondary entry vector   goto 0x000366 (label_031, app cold-init)
;   0x000048        Alternate IV (mirror)    goto 0x0003A6 (label_032 / isr_entry)
;   0x000066+       Application body         LCD, EEPROM, IR, UART, menu, sync, display loop
;   0x007800        Bootloader entry          (firmware-update protocol)
;   0x008000        end of program memory (32 KB device)
;
; ---------------------------------------------------------------------------
; Position in the V1.x release line
; ---------------------------------------------------------------------------
;   V1.4      Stock baseline (older codebase, ch1-6 raw config commands)
;   V1.5b     First refactor: per-purpose serial helpers, displaced mute bit
;             (mute moved to 0x01F.bit5; bit4 became display_refresh_pending)
; * V1.6b    THIS FILE — current development base. Features:
;             • input/volume/mute/standby/display dedicated frame senders
;               (functions 030/031/033/034/035 — see SEMANTIC_FUNCTION_MAP)
;             • full_sync_burst (function_028) emits 6 channel cfg + vol + input
;             • IR RC5 decode in ISR (function_017 — BUG C3, blocks ~10 ms)
;             • boot handshake polls four sentinels until each != 0x80
;               (BUG C1 — no timeout; hard-fails if MAIN absent)
;   V1.61b   V1.6b + binary AB-preset patch (preset_b_active in 0x01F.bit6)
;   V1.62b   V1.61b + reconnect/UART soft-recover patches at 0x7000+
;             (the wake-bug fix and OERR re-prime path; see V162B docs)
;   V1.63b   V1.62b + BF/08 fault indicator/resync helpers
;   V1.64b   V1.63b + IR endpoint standby/wake hardening
;
; ---------------------------------------------------------------------------
; Serial protocol over the current loop (31,250 baud, 3-byte frame)
; ---------------------------------------------------------------------------
; CONTROL emits routed frames via function_027 (serial_tx_routed_frame):
;   [0xB0+route, cmd, data] enqueued through function_020 (tx_byte_enqueue).
; Frames received from MAIN on the 0xBF-prefixed return path are parsed by
; function_019 (rx_parser_entry) — see the parser at 0x00044A.
;
; CONTROL → MAIN (route 0xB0=broadcast, 0xB1=addressed)
;   0x03/00=standby_enter  0x03/01=wake  0x03/02=mute_on  0x03/03=mute_off
;   0x04/00=status_poll    0x06/n=input_select   0x07/n=volume (offset 0x60)
;   0x17..0x1C=channel src 0x1D=backlight  0x1E=link_addr  0x20=preset_select
;
; MAIN → CONTROL (route 0xBF) — parsed at 0x00044A:
;   0x03=standby_status   0x05=raw_status   0x06=current_input
;   0x07=current_volume   0x18=power_on_notify   0x1D=display_timeout
;   0x29=cmd29_status (preset_b_active bit reflection)
;
; ---------------------------------------------------------------------------
; RAM layout (bank 0 unless noted)
; ---------------------------------------------------------------------------
;   0x01D       ir_decoded_cmd        (RC5 cmd byte from function_017)
;   0x01E       ir_decoded_addr       (RC5 addr byte)
;   0x01F       control_flags         bit0=ir_armed   bit1=connected
;                                     bit2=rx_route_seen
;                                     bit3=event_exit
;                                     bit4=display_refresh_pending (V1.6b)
;                                     bit5=mute_state              (V1.6b)
;                                     bit6=preset_b_active (V1.61b+ patch)
;   0x027       tx_data_staging       (byte to enqueue via function_020)
;   0x02F/0x030 rx_parsed_cmd / rx_parsed_data  (latched by parser)
;   0x036..0x065  TX ring (48 bytes, hardware-driven by ISR via PIE1.TXIE)
;   0x066..0x095  RX ring (48 bytes, written by RCIF in ISR)
;   0x096        tx_ring_rd            (ISR consumer side)
;   0x097        tx_ring_wr            (function_020 producer side)
;   0x098        rx_ring_rd            (parser consumer)
;   0x099        rx_ring_wr            (ISR producer)
;   0x09D:0x09E  idle_timeout_counter  16-bit, init 0xEA61 (~60k)
;   0x09F:0x0A0  full_sync_counter     16-bit, init 0x4E20 (~20k → fullsync)
;   0x0A1        handshake_sentinel_4  init 0x80 — boot wait until != 0x80
;   0x0A6        rx_frame_position     parser state (0=route, 1=cmd, 2=data)
;   0x0A7        handshake_sentinel_3  init 0x80
;   0x0B7       rx_ring_staging        (single-byte holding for parser)
;   0x0B8       handshake_sentinel_1  init 0x80 (likely ch1 volume)
;   0x0B9       handshake_sentinel_2  init 0x80 (likely ch2 volume)
;   0x0BB       button_debounce_counter (threshold 4)
;   0x0BC       button_last_scan
;   0x0BE       button_debounced
;   0x0BF       display_state_index   menu screen 0..3 (Vol/Preset/Input/Setup)
;   0x0C1..0CC  saved settings (loaded by function_026 from EEPROM)
;
; ---------------------------------------------------------------------------
; Pin map (PIC18F25K20)  — see docs/analysis/PIN_SEMANTICS.md
; ---------------------------------------------------------------------------
;   RA1=Select RA2=Down RA3=Standby RA4=Right        (active-low buttons)
;   RA5=LCD RS                              RB0..RB3=LCD D4..D7
;   RB4=LCD E                               RB5=IR RC5 input  RB6=aux output
;   RC0=Up                                  RC1=panel illumination / pwr LED
;   RC5=Left   RC6=UART TX (31,250 baud)    RC7=UART RX
;   ADCON1=0x0F → all PORTA digital
;
; ---------------------------------------------------------------------------
; Known long-standing bugs (cross-refs to docs/analysis/SEMANTIC_FUNCTION_MAP.md)
; ---------------------------------------------------------------------------
;   C1   boot_handshake_infinite_wait    label_204 @ 0x0011FE  CRITICAL
;   C2   reconnect_infinite_wait         label_212/216 @ 0x012BC/0x001322  CRITICAL
;   C3   ir_decode_blocks_isr_10ms       function_017 @ 0x00021E  HIGH
;   C4   oerr_no_fifo_drain              function_019 @ 0x00044A  HIGH
;   C5   no_frame_resync_timeout         parser 0x00044A..0x000606 HIGH
;   C6   tx_full_busywait                label_068 @ 0x00062A  HIGH
;   C7   fullsync_burst_saturates_link   function_028 @ 0x000B36 HIGH
;   C8   no_watchdog_timer               WDTEN=0 (config bits)   MEDIUM
; ===========================================================================

; ---------------------------------------------------------------------------
; Reset vector @ 0x000000 — jumps to bootloader at 0x007800 (label_284).
; The bootloader decides whether to start the app at 0x000040 (cold-init
; label_031 / function_001 etc.) or stay in firmware-update mode.
; ---------------------------------------------------------------------------
000000:  ef00  goto    0x007800             ; -> bootloader_entry (label_284)
000002:  f03c
000004:  ffff  dw      0xffff
000006:  ffff  dw      0xffff

; ---------------------------------------------------------------------------
; High-priority IV @ 0x000008 — vectors to label_032 (isr_entry @ 0x0003A6).
; Handles TXIE (UART TX ring drain), RCIF (UART RX ring fill), RBIF (button
; level change). Also calls function_017 (ir_rc5_decode) — BUG C3, blocks
; ~10 ms during RC5 decode, the source of OERR latching on real hardware.
; ---------------------------------------------------------------------------
000008:  efd3  goto    0x0003a6             ; -> isr_entry (label_032)
00000a:  f001
00000c:  0e80  movlw   0x80                  ; (vector pad / unused stub)
00000e:  6e01  movwf   0x01, 0x0
000010:  0efe  movlw   0xfe
000012:  ecc8  call    0x000190, 0x0
000014:  f000
000016:  0e01  movlw   0x01

; ---------------------------------------------------------------------------
; Low-priority IV @ 0x000018 — calls function_009 (uart_init @ 0x000190),
; then halts at 0x000020 (`bra .`). Effectively unused: low-priority is
; never armed; this region is a defensive dead-end.
; ---------------------------------------------------------------------------
000018:  ecc8  call    0x000190, 0x0        ; uart_init (function_009)
00001a:  f000
00001c:  0e75  movlw   0x75
00001e:  6e0d  movwf   0x0d, 0x0
000020:  d7ff  bra     0x000020             ; HALT — low-IV trap (never triggered)
000022:  ffff  dw      0xffff
000024:  ffff  dw      0xffff
000026:  ffff  dw      0xffff
000028:  ffff  dw      0xffff
00002a:  ffff  dw      0xffff
00002c:  ffff  dw      0xffff
00002e:  ffff  dw      0xffff
000030:  ffff  dw      0xffff
000032:  ffff  dw      0xffff
000034:  ffff  dw      0xffff
000036:  ffff  dw      0xffff
000038:  ffff  dw      0xffff
00003a:  ffff  dw      0xffff
00003c:  ffff  dw      0xffff
00003e:  ffff  dw      0xffff
; ---------------------------------------------------------------------------
; Secondary entry vector @ 0x000040 — bootloader jumps here to start the
; app cold-init at 0x000366 (label_031). The intervening 4 dw FFFF + the
; alternate IV at 0x000048 form a defensive trampoline so a misaligned
; PC landing at 0x000040..0x00005E still reaches an interrupt handler or
; init routine instead of executing 0xFF (sleep) opcodes.
; ---------------------------------------------------------------------------
000040:  efb3  goto    0x000366             ; -> app cold-init (label_031)
000042:  f001
000044:  ffff  dw      0xffff
000046:  ffff  dw      0xffff
000048:  efd3  goto    0x0003a6             ; alt IV mirror -> isr_entry
00004a:  f001
00004c:  0e80  movlw   0x80                  ; function_000 — defensive stub:
00004e:  6e01  movwf   0x01, 0x0             ;   used only if PC drops here.
000050:  0efe  movlw   0xfe
000052:  ecc8  call    0x000190, 0x0        ;   call uart_init
000054:  f000
000056:  0e01  movlw   0x01
000058:  ecc8  call    0x000190, 0x0
00005a:  f000
00005c:  0e75  movlw   0x75
00005e:  6e0d  movwf   0x0d, 0x0
000060:  0e30  movlw   0x30
000062:  efec  goto    0x0001d8             ; -> delay_parameter_unit (function_003)
000064:  f000

; ===========================================================================
; function_001 @ 0x000066 — lcd_command
; ---------------------------------------------------------------------------
; Writes a command byte to the HD44780 LCD via the 4-bit nibble interface.
; LCD signals (per PIN_SEMANTICS):
;   RA5 = RS (0=command, 1=data)
;   RB4 = E  (strobe)
;   RB0..RB3 = D4..D7 (data nibble)
; Stages W into 0x017, asserts RS=0 via clrf 0x01 + bsf 0x01,7 (the
; high-bit pattern indicates command mode), then calls function_009 to
; latch the byte through the nibble engine and return.
; ===========================================================================
000066:  6a01  clrf    0x01, 0x0
000068:  8e01  bsf     0x01, 0x7, 0x0
00006a:  6e17  movwf   0x17, 0x0
00006c:  0efe  movlw   0xfe
00006e:  ecc8  call    0x000190, 0x0
000070:  f000
000072:  5017  movf    0x17, 0x0, 0x0
000074:  efc8  goto    0x000190
000076:  f000
; ===========================================================================
; function_002 @ 0x000078 — delay_short_loop
; ---------------------------------------------------------------------------
; 16-bit delay loop scratch helper. Caller stages count via 0x07/0x10/0x11
; and the routine spins, calling function_003 every iteration. Used to
; implement variable-duration LCD setup waits (40 ms power-up, 4.5 ms
; nibble-mode-set, 100 µs char delays). Combined with delay_parameter_unit
; for the LCD HD44780 reset sequence at 0x000086+.
; ===========================================================================
000078:  6a07  clrf    0x07, 0x0
00007a:  6e10  movwf   0x10, 0x0
00007c:  6a11  clrf    0x11, 0x0
00007e:  9600  bcf     0x00, 0x3, 0x0
000080:  5007  movf    0x07, 0x0, 0x0
000082:  b4d8  skpnz
000084:  8600  bsf     0x00, 0x3, 0x0
000086:  0e05  movlw   0x05
000088:  6e06  movwf   0x06, 0x0
00008a:  0e27  movlw   0x27
00008c:  6e0f  movwf   0x0f, 0x0
00008e:  0e10  movlw   0x10
000090:  d80c  rcall   0x0000aa
000092:  0e03  movlw   0x03
000094:  6e0f  movwf   0x0f, 0x0
000096:  0ee8  movlw   0xe8
000098:  d808  rcall   0x0000aa
00009a:  6a0f  clrf    0x0f, 0x0
00009c:  0e64  movlw   0x64
00009e:  d805  rcall   0x0000aa
0000a0:  6a0f  clrf    0x0f, 0x0
0000a2:  0e0a  movlw   0x0a
0000a4:  d802  rcall   0x0000aa
0000a6:  5010  movf    0x10, 0x0, 0x0
0000a8:  d008  bra     0x0000ba
; ===========================================================================
; function_003 @ 0x0000AA — delay_parameter_unit
; ---------------------------------------------------------------------------
; Inner delay primitive used by function_002 / function_012. Counts down
; the {0x10:0x11} pair through the {0x0C:0x0E:0x0F} scratch chain,
; calling function_008 (0x0001F0 — 16-bit divide helper) on each tick to
; advance the working pointer. Returns when the counter reaches zero.
; ===========================================================================
0000aa:  6e0e  movwf   0x0e, 0x0
0000ac:  5011  movf    0x11, 0x0, 0x0
0000ae:  6e0d  movwf   0x0d, 0x0
0000b0:  5010  movf    0x10, 0x0, 0x0
0000b2:  6e0c  movwf   0x0c, 0x0
0000b4:  ecf8  call    0x0001f0, 0x0
0000b6:  f000
0000b8:  500c  movf    0x0c, 0x0, 0x0
0000ba:  6e0c  movwf   0x0c, 0x0
0000bc:  4e06  dcfsnz  0x06, 0x1, 0x0
0000be:  9600  bcf     0x00, 0x3, 0x0
0000c0:  5007  movf    0x07, 0x0, 0x0
0000c2:  e003  bz      0x0000ca
0000c4:  5c06  subwf   0x06, 0x0, 0x0
0000c6:  b0d8  skpnc
0000c8:  d008  bra     0x0000da
0000ca:  500c  movf    0x0c, 0x0, 0x0
0000cc:  a4d8  skpz
0000ce:  9600  bcf     0x00, 0x3, 0x0
0000d0:  b600  btfsc   0x00, 0x3, 0x0
0000d2:  d003  bra     0x0000da
0000d4:  0f30  addlw   0x30
0000d6:  efc8  goto    0x000190
0000d8:  f000
0000da:  0012  return  0x0
; ===========================================================================
; function_004 @ 0x0000DC — lcd_string_write_rom
; ---------------------------------------------------------------------------
; Reads a NUL-terminated ASCII string from program memory via TBLRD*+,
; passing each character to function_005 (lcd_char_write). Caller seeds
; TBLPTR before calling. Returns when a 0x00 terminator is read.
; Used by the menu/display-loop helpers to print fixed strings (SETUP,
; VOLUME, INPUT, "Zzz...", "Waiting for DLCP", etc.).
; ===========================================================================
0000dc:  6aa6  clrf    0xa6, 0x0            ; EECON1 = 0
0000de:  8ea6  bsf     0xa6, 0x7, 0x0       ; EEPGD=1 (program memory)
0000e0:  0009  tblrd*+                       ; TABLAT = pgm[TBLPTR++]
0000e2:  50f5  movf    0xf5, 0x0, 0x0
0000e4:  e002  bz      0x0000ea
0000e6:  d802  rcall   0x0000ec
0000e8:  d7fb  bra     0x0000e0
0000ea:  0012  return  0x0
; ===========================================================================
; function_005 @ 0x0000EC — lcd_char_write
; ---------------------------------------------------------------------------
; Writes one byte to the HD44780 LCD via the 4-bit nibble interface.
;   • RS (LATA.5) selected by the BSR/W stage upstream
;   • Latches high nibble (bits 7..4) on D4..D7 = LATB.0..3,
;   • Pulses E (LATB.4) high then low (~450 ns at 16 MHz),
;   • Repeats for low nibble.
; Special-cases command bytes 0x01..0x03 (clear/home/entry-mode-set) which
; need extra settle time — uses function_003 to hold E high a few µs longer.
; ===========================================================================
0000ec:  6e15  movwf   0x15, 0x0
0000ee:  988a  bcf     0x8a, 0x4, 0x0       ; LATB.4 (E) = 0 (idle)
0000f0:  9a89  bcf     0x89, 0x5, 0x0
0000f2:  9893  bcf     0x93, 0x4, 0x0
0000f4:  9a92  bcf     0x92, 0x5, 0x0
0000f6:  0ef0  movlw   0xf0
0000f8:  1693  andwf   0x93, 0x1, 0x0
0000fa:  5015  movf    0x15, 0x0, 0x0
0000fc:  b200  btfsc   0x00, 0x1, 0x0
0000fe:  efa3  goto    0x000146
000100:  f000
000102:  0e3a  movlw   0x3a
000104:  6e0d  movwf   0x0d, 0x0
000106:  0e98  movlw   0x98
000108:  ecec  call    0x0001d8, 0x0
00010a:  f000
00010c:  0e33  movlw   0x33
00010e:  6e14  movwf   0x14, 0x0
000110:  d82e  rcall   0x00016e
000112:  0e13  movlw   0x13
000114:  6e0d  movwf   0x0d, 0x0
000116:  0e88  movlw   0x88
000118:  ecec  call    0x0001d8, 0x0
00011a:  f000
00011c:  d828  rcall   0x00016e
00011e:  0e64  movlw   0x64
000120:  eceb  call    0x0001d6, 0x0
000122:  f000
000124:  d824  rcall   0x00016e
000126:  0e64  movlw   0x64
000128:  eceb  call    0x0001d6, 0x0
00012a:  f000
00012c:  0e22  movlw   0x22
00012e:  6e14  movwf   0x14, 0x0
000130:  d81e  rcall   0x00016e
000132:  0e28  movlw   0x28
000134:  d807  rcall   0x000144
000136:  0e0c  movlw   0x0c
000138:  d805  rcall   0x000144
00013a:  0e06  movlw   0x06
00013c:  d803  rcall   0x000144
00013e:  8200  bsf     0x00, 0x1, 0x0
000140:  5015  movf    0x15, 0x0, 0x0
000142:  d001  bra     0x000146
000144:  8000  bsf     0x00, 0x0, 0x0
000146:  6e14  movwf   0x14, 0x0
000148:  a000  btfss   0x00, 0x0, 0x0
00014a:  d00b  bra     0x000162
00014c:  9a89  bcf     0x89, 0x5, 0x0
00014e:  0803  sublw   0x03
000150:  e30c  bnc     0x00016a
000152:  d80b  rcall   0x00016a
000154:  0e07  movlw   0x07
000156:  6e0d  movwf   0x0d, 0x0
000158:  0ed0  movlw   0xd0
00015a:  ecec  call    0x0001d8, 0x0
00015c:  f000
00015e:  80d8  setc
000160:  0012  return  0x0
000162:  8000  bsf     0x00, 0x0, 0x0
000164:  08fe  sublw   0xfe
000166:  e012  bz      0x00018c
000168:  8a89  bsf     0x89, 0x5, 0x0
00016a:  3a14  swapf   0x14, 0x1, 0x0
00016c:  a000  btfss   0x00, 0x0, 0x0
00016e:  9000  bcf     0x00, 0x0, 0x0
000170:  888a  bsf     0x8a, 0x4, 0x0
000172:  0ef0  movlw   0xf0
000174:  1681  andwf   0x81, 0x1, 0x0
000176:  5014  movf    0x14, 0x0, 0x0
000178:  0b0f  andlw   0x0f
00017a:  1281  iorwf   0x81, 0x1, 0x0
00017c:  988a  bcf     0x8a, 0x4, 0x0
00017e:  3a14  swapf   0x14, 0x1, 0x0
000180:  b000  btfsc   0x00, 0x0, 0x0
000182:  d7f5  bra     0x00016e
000184:  0e32  movlw   0x32
000186:  eceb  call    0x0001d6, 0x0
000188:  f000
00018a:  80d8  setc
00018c:  5015  movf    0x15, 0x0, 0x0
00018e:  0012  return  0x0
; ===========================================================================
; function_009 @ 0x000190 — lcd_command_or_eeprom_read (shared dispatch)
; function_010 @ 0x000196 — eeprom_read_byte (entry point shares tail)
; ---------------------------------------------------------------------------
; Dual-purpose entry block. PIC18F25K20 EEPROM uses the same EECON1 SFR
; positions as program-memory access (0xA6=EECON1, 0xA7=EECON2, 0xA8=EEDATA,
; 0xA9=EEADR), so a single read primitive serves both paths:
;
;   Entry function_009 (0x000190) — bit7 of 0x01 selects target:
;     bit7 SET   → goto function_005 (LCD write at 0x0000EC)
;     bit7 CLEAR → fall through into the EEPROM read body at 0x000196
;
;   Entry function_010 (0x000196) — direct EEPROM byte read:
;     EEADR (0xA9) = W, EECON1 (0xA6) cleared, EECON1.RD (0xA6.0) set,
;     return EEDATA (0xA8) in W. EEPROM read latency is one cycle on
;     PIC18F25K20 so no NOP is needed before reading EEDATA.
;
; Used by function_026 (settings_load_eeprom) at boot, and by every later
; routine that needs to read user-saved display/config bytes from EEPROM.
; ===========================================================================
000190:  be01  btfsc   0x01, 0x7, 0x0       ; LCD-mode flag (0x01.bit7) set?
000192:  ef76  goto    0x0000ec             ;  yes -> tail to function_005 (LCD)
000194:  f000
; --- function_010 entry (eeprom_read_byte) ---
000196:  6ea9  movwf   0xa9, 0x0            ; EEADR = W (read address)
000198:  6aa6  clrf    0xa6, 0x0            ; EECON1 = 0 (EEPGD=0, CFGS=0)
00019a:  80a6  bsf     0xa6, 0x0, 0x0       ; EECON1.RD = 1 (start read)
00019c:  50a8  movf    0xa8, 0x0, 0x0       ; W = EEDATA (latched byte)
00019e:  2aa9  incf    0xa9, 0x1, 0x0       ; EEADR++ (auto-advance for sequential reads)
0001a0:  0012  return  0x0

; ===========================================================================
; function_011 @ 0x0001A2 — eeprom_write_byte (~3.3 ms, blocking)
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
0001a2:  6ea8  movwf   0xa8, 0x0            ; EEDATA = W
0001a4:  6aa6  clrf    0xa6, 0x0
0001a6:  84a6  bsf     0xa6, 0x2, 0x0       ; EECON1.WREN = 1
0001a8:  0e55  movlw   0x55
0001aa:  6ea7  movwf   0xa7, 0x0            ; EECON2 = 0x55
0001ac:  0eaa  movlw   0xaa
0001ae:  6ea7  movwf   0xa7, 0x0            ; EECON2 = 0xAA
0001b0:  82a6  bsf     0xa6, 0x1, 0x0       ; EECON1.WR = 1 (start write)
0001b2:  b2a6  btfsc   0xa6, 0x1, 0x0       ; spin while WR set
0001b4:  d7fe  bra     0x0001b2
0001b6:  94a6  bcf     0xa6, 0x2, 0x0       ; EECON1.WREN = 0
0001b8:  2aa9  incf    0xa9, 0x1, 0x0
0001ba:  0012  return  0x0

; ===========================================================================
; function_012 @ 0x0001BC — delay_short
; ---------------------------------------------------------------------------
; Caller stages count in W; routine spins ~200 cycles per unit (50 µs at
; 16 MHz). Common values: W=0xC8 → ~10 ms, W=0x05 → ~250 µs (post-LCD-strobe
; settle). Used everywhere a "short pause" is needed without commandeering
; Timer3.
; ===========================================================================
0001bc:  6a0f  clrf    0x0f, 0x0
0001be:  6e0e  movwf   0x0e, 0x0
0001c0:  0eff  movlw   0xff
0001c2:  260e  addwf   0x0e, 0x1, 0x0
0001c4:  220f  addwfc  0x0f, 0x1, 0x0
0001c6:  d000  bra     0x0001c8
0001c8:  a0d8  skpc
0001ca:  0012  return  0x0
0001cc:  0e03  movlw   0x03
0001ce:  6e0d  movwf   0x0d, 0x0
0001d0:  0ee5  movlw   0xe5
0001d2:  d802  rcall   0x0001d8
0001d4:  d7f5  bra     0x0001c0
0001d6:  6a0d  clrf    0x0d, 0x0
0001d8:  0ffa  addlw   0xfa
0001da:  6e0c  movwf   0x0c, 0x0
0001dc:  0000  nop
0001de:  e303  bnc     0x0001e6
0001e0:  d000  bra     0x0001e2
0001e2:  060c  decf    0x0c, 0x1, 0x0
0001e4:  e2fe  bc      0x0001e2
0001e6:  060c  decf    0x0c, 0x1, 0x0
0001e8:  060d  decf    0x0d, 0x1, 0x0
0001ea:  e2fb  bc      0x0001e2
0001ec:  0000  nop
0001ee:  0012  return  0x0
0001f0:  6a11  clrf    0x11, 0x0
0001f2:  6a10  clrf    0x10, 0x0
0001f4:  0e10  movlw   0x10
0001f6:  6ef3  movwf   0xf3, 0x0
0001f8:  340d  rlcf    0x0d, 0x0, 0x0
0001fa:  3610  rlcf    0x10, 0x1, 0x0
0001fc:  3611  rlcf    0x11, 0x1, 0x0
0001fe:  500e  movf    0x0e, 0x0, 0x0
000200:  5c10  subwf   0x10, 0x0, 0x0
000202:  500f  movf    0x0f, 0x0, 0x0
000204:  5811  subwfb  0x11, 0x0, 0x0
000206:  e305  bnc     0x000212
000208:  500e  movf    0x0e, 0x0, 0x0
00020a:  5e10  subwf   0x10, 0x1, 0x0
00020c:  500f  movf    0x0f, 0x0, 0x0
00020e:  5a11  subwfb  0x11, 0x1, 0x0
000210:  80d8  setc
000212:  360c  rlcf    0x0c, 0x1, 0x0
000214:  360d  rlcf    0x0d, 0x1, 0x0
000216:  2ef3  decfsz  0xf3, 0x1, 0x0
000218:  d7ef  bra     0x0001f8
00021a:  500c  movf    0x0c, 0x0, 0x0
00021c:  0012  return  0x0
; ===========================================================================
; function_017 @ 0x00021E — ir_rc5_decode    *** BUG C3 ***
; ---------------------------------------------------------------------------
; RC5 IR remote decoder. Polls RB5 (LATB.5 readback at 0x81.5) collecting
; 16 bits via a tight bit-bang loop. Stores decoded address into 0x01E
; (ir_decoded_addr) and command into 0x01D (ir_decoded_cmd), then sets
; 0x01F.bit0 (ir_armed) so the main event loop dispatches the IR command.
;
; *** BUG C3 (ir_decode_blocks_isr_10ms) ***
; This routine is INVOKED FROM THE ISR (label_032 at 0x0003A6 jumps to
; 0x000264 which calls here). The polling loop runs ~28,160 cycles, i.e.
; ~7-10 ms with the BSF 0x93,5 at entry KEEPING THE OTHER ISR SOURCES
; MASKED. During that window:
;   • UART RX FIFO can fill (RCREG is 2 deep) — third byte → OERR.
;   • Button RBIF events are missed.
;   • TXIE-driven outgoing frames stall (function_034 standby/wake frame
;     can be delayed by ~10 ms per IR press).
; The OERR latch exposes BUG C4 in function_019 because the parser only
; toggles CREN to clear OERR — it does NOT drain RCREG. Stale bytes in
; the hardware FIFO then re-trigger the parser with phase-shifted data,
; which is what produces the V162B "intermittent unresponsive" pattern.
; ===========================================================================
00021e:  8a93  bsf     0x93, 0x5, 0x0       ; LATB.5 — drive IR sense (debug?) / mask sources
000220:  6a15  clrf    0x15, 0x0            ; bit accumulator hi
000222:  6a14  clrf    0x14, 0x0            ; bit accumulator lo
000224:  ee00  lfsr    0x0, 0x010
000226:  f010
000228:  0e01  movlw   0x01
00022a:  6e0d  movwf   0x0d, 0x0
00022c:  0eba  movlw   0xba
00022e:  ecec  call    0x0001d8, 0x0
000230:  f000
000232:  ba81  btfsc   0x81, 0x5, 0x0
000234:  d057  bra     0x0002e4
000236:  0e03  movlw   0x03
000238:  6e0d  movwf   0x0d, 0x0
00023a:  0e76  movlw   0x76
00023c:  ecec  call    0x0001d8, 0x0
00023e:  f000
000240:  2a15  incf    0x15, 0x1, 0x0
000242:  0e20  movlw   0x20
000244:  6415  cpfsgt  0x15, 0x0
000246:  d001  bra     0x00024a
000248:  d00a  bra     0x00025e
00024a:  80d8  setc
00024c:  ba81  btfsc   0x81, 0x5, 0x0
00024e:  90d8  clrc
000250:  36ef  rlcf    0xef, 0x1, 0x0
000252:  2a14  incf    0x14, 0x1, 0x0
000254:  a614  btfss   0x14, 0x3, 0x0
000256:  d002  bra     0x00025c
000258:  52ee  movf    0xee, 0x1, 0x0
00025a:  6a14  clrf    0x14, 0x0
00025c:  d7ec  bra     0x000236
00025e:  ee00  lfsr    0x0, 0x010
000260:  f010
000262:  6a05  clrf    0x05, 0x0
000264:  6a14  clrf    0x14, 0x0
000266:  6a0e  clrf    0x0e, 0x0
000268:  6a0d  clrf    0x0d, 0x0
00026a:  6a0c  clrf    0x0c, 0x0
00026c:  36ef  rlcf    0xef, 0x1, 0x0
00026e:  3605  rlcf    0x05, 0x1, 0x0
000270:  36ef  rlcf    0xef, 0x1, 0x0
000272:  3605  rlcf    0x05, 0x1, 0x0
000274:  2a14  incf    0x14, 0x1, 0x0
000276:  d83b  rcall   0x0002ee
000278:  b409  btfsc   0x09, 0x2, 0x0
00027a:  d034  bra     0x0002e4
00027c:  6a05  clrf    0x05, 0x0
00027e:  36ef  rlcf    0xef, 0x1, 0x0
000280:  3605  rlcf    0x05, 0x1, 0x0
000282:  36ef  rlcf    0xef, 0x1, 0x0
000284:  3605  rlcf    0x05, 0x1, 0x0
000286:  2a14  incf    0x14, 0x1, 0x0
000288:  d832  rcall   0x0002ee
00028a:  b409  btfsc   0x09, 0x2, 0x0
00028c:  d02b  bra     0x0002e4
00028e:  3209  rrcf    0x09, 0x1, 0x0
000290:  360e  rlcf    0x0e, 0x1, 0x0
000292:  0e05  movlw   0x05
000294:  6e08  movwf   0x08, 0x0
000296:  6a05  clrf    0x05, 0x0
000298:  36ef  rlcf    0xef, 0x1, 0x0
00029a:  3605  rlcf    0x05, 0x1, 0x0
00029c:  36ef  rlcf    0xef, 0x1, 0x0
00029e:  3605  rlcf    0x05, 0x1, 0x0
0002a0:  2a14  incf    0x14, 0x1, 0x0
0002a2:  a414  btfss   0x14, 0x2, 0x0
0002a4:  d002  bra     0x0002aa
0002a6:  52ee  movf    0xee, 0x1, 0x0
0002a8:  6a14  clrf    0x14, 0x0
0002aa:  d821  rcall   0x0002ee
0002ac:  b409  btfsc   0x09, 0x2, 0x0
0002ae:  d01a  bra     0x0002e4
0002b0:  3209  rrcf    0x09, 0x1, 0x0
0002b2:  360d  rlcf    0x0d, 0x1, 0x0
0002b4:  2e08  decfsz  0x08, 0x1, 0x0
0002b6:  d7ef  bra     0x000296
0002b8:  0e06  movlw   0x06
0002ba:  6e08  movwf   0x08, 0x0
0002bc:  6a05  clrf    0x05, 0x0
0002be:  36ef  rlcf    0xef, 0x1, 0x0
0002c0:  3605  rlcf    0x05, 0x1, 0x0
0002c2:  36ef  rlcf    0xef, 0x1, 0x0
0002c4:  3605  rlcf    0x05, 0x1, 0x0
0002c6:  2a14  incf    0x14, 0x1, 0x0
0002c8:  a414  btfss   0x14, 0x2, 0x0
0002ca:  d002  bra     0x0002d0
0002cc:  52ee  movf    0xee, 0x1, 0x0
0002ce:  6a14  clrf    0x14, 0x0
0002d0:  d80e  rcall   0x0002ee
0002d2:  b409  btfsc   0x09, 0x2, 0x0
0002d4:  d007  bra     0x0002e4
0002d6:  3209  rrcf    0x09, 0x1, 0x0
0002d8:  360c  rlcf    0x0c, 0x1, 0x0
0002da:  2e08  decfsz  0x08, 0x1, 0x0
0002dc:  d7ef  bra     0x0002bc
0002de:  500c  movf    0x0c, 0x0, 0x0
0002e0:  90d8  clrc
0002e2:  0012  return  0x0
0002e4:  0eff  movlw   0xff
0002e6:  6e0c  movwf   0x0c, 0x0
0002e8:  6e0d  movwf   0x0d, 0x0
0002ea:  80d8  setc
0002ec:  0012  return  0x0
0002ee:  6a09  clrf    0x09, 0x0
0002f0:  2c05  decfsz  0x05, 0x0, 0x0
0002f2:  d002  bra     0x0002f8
0002f4:  8009  bsf     0x09, 0x0, 0x0
0002f6:  0012  return  0x0
0002f8:  0e02  movlw   0x02
0002fa:  6205  cpfseq  0x05, 0x0
0002fc:  d001  bra     0x000300
0002fe:  0012  return  0x0
000300:  8409  bsf     0x09, 0x2, 0x0
000302:  0012  return  0x0
000304:  6946  setf    0x46, 0x1
000306:  6d72  negf    0x72, 0x1
000308:  6177  cpfslt  0x77, 0x1
00030a:  6572  cpfsgt  0x72, 0x1
00030c:  5620  subfwb  0x20, 0x1, 0x0
00030e:  0000  nop
000310:  6157  cpfslt  0x57, 0x1
000312:  7469  btg     0x69, 0x2, 0x0
000314:  6e69  movwf   0x69, 0x0
000316:  2067  addwfc  0x67, 0x0, 0x0
000318:  6f66  movwf   0x66, 0x1
00031a:  2072  addwfc  0x72, 0x0, 0x0
00031c:  4c44  dcfsnz  0x44, 0x0, 0x0
00031e:  5043  movf    0x43, 0x0, 0x0
000320:  0000  nop
000322:  7a5a  btg     0x5a, 0x5, 0x0
000324:  2e7a  decfsz  0x7a, 0x1, 0x0
000326:  2e2e  decfsz  0x2e, 0x1, 0x0
000328:  2020  addwfc  0x20, 0x0, 0x0
00032a:  2020  addwfc  0x20, 0x0, 0x0
00032c:  2020  addwfc  0x20, 0x0, 0x0
00032e:  2020  addwfc  0x20, 0x0, 0x0
000330:  2020  addwfc  0x20, 0x0, 0x0
000332:  0000  nop
000334:  6157  cpfslt  0x57, 0x1
000336:  7469  btg     0x69, 0x2, 0x0
000338:  6e69  movwf   0x69, 0x0
00033a:  2067  addwfc  0x67, 0x0, 0x0
00033c:  6f66  movwf   0x66, 0x1
00033e:  2072  addwfc  0x72, 0x0, 0x0
000340:  4c44  dcfsnz  0x44, 0x0, 0x0
000342:  5043  movf    0x43, 0x0, 0x0
000344:  0000  nop
000346:  4264  rrncf   0x64, 0x1, 0x0
000348:  2020  addwfc  0x20, 0x0, 0x0
00034a:  2020  addwfc  0x20, 0x0, 0x0
00034c:  2020  addwfc  0x20, 0x0, 0x0
00034e:  2020  addwfc  0x20, 0x0, 0x0
000350:  2020  addwfc  0x20, 0x0, 0x0
000352:  0020  dw      0x0020
000354:  754d  btg     0x4d, 0x2, 0x1
000356:  6574  cpfsgt  0x74, 0x1
000358:  2020  addwfc  0x20, 0x0, 0x0
00035a:  2020  addwfc  0x20, 0x0, 0x0
00035c:  2020  addwfc  0x20, 0x0, 0x0
00035e:  2020  addwfc  0x20, 0x0, 0x0
000360:  2020  addwfc  0x20, 0x0, 0x0
000362:  2020  addwfc  0x20, 0x0, 0x0
000364:  0000  nop
; ===========================================================================
; label_031 @ 0x000366 — app_cold_init (peripheral bring-up)
; ---------------------------------------------------------------------------
; Reached from the secondary entry vector at 0x000040 (bootloader hand-off
; once it determines the app should run). Performs PIC18F25K20 peripheral
; init in the canonical order:
;   1. Clear core slots (TBLPTRU, BSR, ANSEL).
;   2. TRISA = 0xDF, TRISB = 0x3C, TRISC = 0xBD  (per PIN_SEMANTICS:
;      buttons inputs, LCD outputs, IR/UART configured for peripheral).
;   3. Clear the TX/RX ring index pairs at 0x7A/0x7B/0x7E/0x7F.
;   4. ADCON1 = 0x0F (all PORTA digital — buttons, no analog input).
;   5. Drop UART/MSSP enable bits, clear OSCCON.IDLEN/SLPEN/SCS bits to
;      stay in HS oscillator mode.
;   6. Set TXSTA.TXEN (0xAC.5), RCSTA.SPEN (0xAB.7), enable RBIE for
;      button interrupts.
;   7. Tail-call into 0x00103C (label_195 / app_init splash + main entry).
; The canonical TRIS values are documented in PIN_SEMANTICS table.
; ===========================================================================
000366:  6af8  clrf    0xf8, 0x0            ; TBLPTRU = 0
000368:  6a00  clrf    0x00, 0x0            ; (bank 0 scratch clear)
00036a:  6aab  clrf    0xab, 0x0            ; RCSTA = 0 (UART RX off temporarily)
00036c:  0100  movlb   0x0
00036e:  0edf  movlw   0xdf
000370:  6e92  movwf   0x92, 0x0            ; TRISA = 0xDF (RA1..RA4 + RA6/7 in, RA5 out)
000372:  0e3c  movlw   0x3c
000374:  6e93  movwf   0x93, 0x0            ; TRISB = 0x3C (RB2..RB5 in: LCD bus turnaround + IR)
000376:  0ebd  movlw   0xbd
000378:  6e94  movwf   0x94, 0x0            ; TRISC = 0xBD (RC0/RC2..RC5/RC7 in, RC1/RC6 out)
00037a:  6a7b  clrf    0x7b, 0x0
00037c:  6a7a  clrf    0x7a, 0x0
00037e:  6a7e  clrf    0x7e, 0x0
000380:  6a7f  clrf    0x7f, 0x0
000382:  0e0f  movlw   0x0f
000384:  6ec1  movwf   0xc1, 0x0            ; ANSEL low = 0x0F (per-pin analog disable mask)
000386:  9e7d  bcf     0x7d, 0x7, 0x0       ; OSCCON.IDLEN = 0
000388:  9c7d  bcf     0x7d, 0x6, 0x0       ; OSCCON.IRCF2 = 0
00038a:  987d  bcf     0x7d, 0x4, 0x0       ; OSCCON.IRCF0 = 0
00038c:  0e05  movlw   0x05
00038e:  6eaf  movwf   0xaf, 0x0            ; SPBRG seed
000390:  94ac  bcf     0xac, 0x2, 0x0
000392:  96b8  bcf     0xb8, 0x3, 0x0
000394:  98ac  bcf     0xac, 0x4, 0x0
000396:  8eab  bsf     0xab, 0x7, 0x0       ; RCSTA.SPEN = 1 (UART module on)
000398:  9ed0  bcf     0xd0, 0x7, 0x0
00039a:  989d  bcf     0x9d, 0x4, 0x0       ; PIE1.RCIE = 0 (RX IE armed later)
00039c:  9a9d  bcf     0x9d, 0x5, 0x0
00039e:  8aac  bsf     0xac, 0x5, 0x0       ; TXSTA.TXEN = 1 (TX enabled)
0003a0:  88ab  bsf     0xab, 0x4, 0x0       ; RCSTA.CREN = 1 (RX enabled)
0003a2:  ef1e  goto    0x00103c             ; -> label_195 / app_init (LCD splash, IRQ arm)
0003a4:  f008
; ===========================================================================
; label_032 @ 0x0003A6 — isr_entry  (single high-priority ISR)
; ---------------------------------------------------------------------------
; Saves WREG (0xFD8), STATUS (0xFE0), BSR-related shadows (0xFE9, 0xFEA)
; into RAM at 0x019..0x004 since CONTROL does NOT use the FAST shadow.
; Then runs three separate handlers in sequence:
;   • TX path: if TXIE (PIE1.4 @ 0x9D.4) AND TXIF (PIR1.4 @ 0x9E.4) and
;     the TX ring (head 0x96, tail 0x97) is non-empty, pull a byte from
;     the ring at 0x036+ and write to TXREG; clear TX flag if ring empty.
;   • RX path: if RCIF (PIR1.5 @ 0x9E.5), copy RCREG (0xEB) into RX ring
;     at 0x066+rx_ring_wr (0x99); increment + wrap rx_ring_wr at 0x30
;     (48-byte ring).  No ring-overflow check — same hazard pattern as
;     MAIN bug M6.
;   • RBIF path: if RBIF (PIR2.bit5 — port-change interrupt for buttons),
;     toggle/clear and run inline button-debounce (function_023 lazy
;     entry) — actually this leg just sets a flag; the heavy debounce
;     work lives in function_023 in the main loop.
;   • If any flag indicates IR activity (RBIE was set and the bit is
;     persistent), JUMP to function_017 (ir_rc5_decode) — this is the
;     **BUG C3** invocation; the ISR will busy-poll RB5 for ~10 ms.
; Restores BSR/STATUS/WREG and returns with retfie 1 (FAST not used).
; ===========================================================================
0003a6:  cfd8  movff   0xfd8, 0x019         ; save WREG
0003a8:  f019
0003aa:  6e1a  movwf   0x1a, 0x0
0003ac:  cfe0  movff   0xfe0, 0x002         ; save STATUS
0003ae:  f002
0003b0:  cfe9  movff   0xfe9, 0x003         ; save BSR (or FSR0L)
0003b2:  f003
0003b4:  cfea  movff   0xfea, 0x004         ; save FSR0H or related
0003b6:  f004
0003b8:  0100  movlb   0x0
0003ba:  6ae8  clrw
0003bc:  b89d  btfsc   0x9d, 0x4, 0x0
0003be:  0e01  movlw   0x01
0003c0:  6e18  movwf   0x18, 0x0
0003c2:  6ae8  clrw
0003c4:  b89e  btfsc   0x9e, 0x4, 0x0
0003c6:  0e01  movlw   0x01
0003c8:  1618  andwf   0x18, 0x1, 0x0
0003ca:  b4d8  skpnz
0003cc:  effb  goto    0x0003f6
0003ce:  f001
0003d0:  5196  movf    0x96, 0x0, 0x1
0003d2:  6397  cpfseq  0x97, 0x1
0003d4:  efef  goto    0x0003de
0003d6:  f001
0003d8:  989d  bcf     0x9d, 0x4, 0x0
0003da:  effb  goto    0x0003f6
0003dc:  f001
0003de:  ee00  lfsr    0x0, 0x036
0003e0:  f036
0003e2:  5196  movf    0x96, 0x0, 0x1
0003e4:  50eb  movf    0xeb, 0x0, 0x0
0003e6:  6ead  movwf   0xad, 0x0
0003e8:  2b96  incf    0x96, 0x1, 0x1
0003ea:  0e30  movlw   0x30
0003ec:  5d96  subwf   0x96, 0x0, 0x1
0003ee:  a0d8  skpc
0003f0:  effb  goto    0x0003f6
0003f2:  f001
0003f4:  6b96  clrf    0x96, 0x1
0003f6:  aa9e  btfss   0x9e, 0x5, 0x0
0003f8:  ef0a  goto    0x000414
0003fa:  f002
0003fc:  ee00  lfsr    0x0, 0x066
0003fe:  f066
000400:  5199  movf    0x99, 0x0, 0x1
000402:  cfae  movff   0xfae, 0xfeb
000404:  ffeb
000406:  2b99  incf    0x99, 0x1, 0x1
000408:  0e30  movlw   0x30
00040a:  5d99  subwf   0x99, 0x0, 0x1
00040c:  a0d8  skpc
00040e:  ef0a  goto    0x000414
000410:  f002
000412:  6b99  clrf    0x99, 0x1
000414:  a0f2  btfss   0xf2, 0x0, 0x0
000416:  ef1b  goto    0x000436
000418:  f002
00041a:  501c  movf    0x1c, 0x0, 0x0
00041c:  101b  iorwf   0x1b, 0x0, 0x0
00041e:  a4d8  skpz
000420:  ef1a  goto    0x000434
000422:  f002
000424:  a01f  btfss   0x1f, 0x0, 0x0
000426:  ef1a  goto    0x000434
000428:  f002
00042a:  def9  rcall   0x00021e
00042c:  6e1d  movwf   0x1d, 0x0
00042e:  c00d  movff   0x00d, 0x01e
000430:  f01e
000432:  901f  bcf     0x1f, 0x0, 0x0
000434:  90f2  bcf     0xf2, 0x0, 0x0
000436:  c003  movff   0x003, 0xfe9
000438:  ffe9
00043a:  c004  movff   0x004, 0xfea
00043c:  ffea
00043e:  c002  movff   0x002, 0xfe0
000440:  ffe0
000442:  501a  movf    0x1a, 0x0, 0x0
000444:  c019  movff   0x019, 0xfd8
000446:  ffd8
000448:  0010  retfie  0x0

; ===========================================================================
; function_019 @ 0x00044A — rx_parser_entry  *** BUG C4 / C5 ***
; ---------------------------------------------------------------------------
; Top of the receive-path service routine. Called every iteration of the
; main event loop (function_042) to drain the RX ring, decode 3-byte
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
00044a:  a2ab  btfss   0xab, 0x1, 0x0       ; RCSTA.OERR set?
00044c:  ef2b  goto    0x000456             ;  no -> skip OERR recovery
00044e:  f002
000450:  98ab  bcf     0xab, 0x4, 0x0       ; CREN = 0 (clear OERR latch)
000452:  0000  nop                           ; *** BUG C4: no movf RCREG drain here ***
000454:  88ab  bsf     0xab, 0x4, 0x0       ; CREN = 1 (re-enable RX)
000456:  5199  movf    0x99, 0x0, 0x1       ; W = rx_ring_wr
000458:  6398  cpfseq  0x98, 0x1
00045a:  ef30  goto    0x000460
00045c:  f002
00045e:  0012  return  0x0
000460:  ee00  lfsr    0x0, 0x066
000462:  f066
000464:  5198  movf    0x98, 0x0, 0x1
000466:  50eb  movf    0xeb, 0x0, 0x0
000468:  6fb6  movwf   0xb6, 0x1
00046a:  2b98  incf    0x98, 0x1, 0x1
00046c:  0e30  movlw   0x30
00046e:  5d98  subwf   0x98, 0x0, 0x1
000470:  a0d8  skpc
000472:  ef3c  goto    0x000478
000474:  f002
000476:  6b98  clrf    0x98, 0x1
000478:  0efe  movlw   0xfe
00047a:  63b6  cpfseq  0xb6, 0x1
00047c:  ef45  goto    0x00048a
00047e:  f002
000480:  c0b6  movff   0x0b6, 0x027
000482:  f027
000484:  ecf6  call    0x0005ec, 0x0
000486:  f002
000488:  d7e0  bra     0x00044a
00048a:  0e80  movlw   0x80
00048c:  5db6  subwf   0xb6, 0x0, 0x1
00048e:  a0d8  skpc
000490:  ef6b  goto    0x0004d6
000492:  f002
000494:  0ef1  movlw   0xf1
000496:  15b6  andwf   0xb6, 0x0, 0x1
000498:  6e0a  movwf   0x0a, 0x0
00049a:  6a0b  clrf    0x0b, 0x0
00049c:  500a  movf    0x0a, 0x0, 0x0
00049e:  0ab1  xorlw   0xb1
0004a0:  100b  iorwf   0x0b, 0x0, 0x0
0004a2:  a4d8  skpz
0004a4:  ef56  goto    0x0004ac
0004a6:  f002
0004a8:  0eb1  movlw   0xb1
0004aa:  6fb6  movwf   0xb6, 0x1
0004ac:  0eb0  movlw   0xb0
0004ae:  63b6  cpfseq  0xb6, 0x1
0004b0:  ef5f  goto    0x0004be
0004b2:  f002
0004b4:  0e01  movlw   0x01
0004b6:  6fa6  movwf   0xa6, 0x1
0004b8:  841f  bsf     0x1f, 0x2, 0x0
0004ba:  ef6a  goto    0x0004d4
0004bc:  f002
0004be:  0eb1  movlw   0xb1
0004c0:  63b6  cpfseq  0xb6, 0x1
0004c2:  ef68  goto    0x0004d0
0004c4:  f002
0004c6:  0e01  movlw   0x01
0004c8:  6fa6  movwf   0xa6, 0x1
0004ca:  841f  bsf     0x1f, 0x2, 0x0
0004cc:  ef6a  goto    0x0004d4
0004ce:  f002
0004d0:  6ba6  clrf    0xa6, 0x1
0004d2:  841f  bsf     0x1f, 0x2, 0x0
0004d4:  d7ba  bra     0x00044a
0004d6:  53a6  movf    0xa6, 0x1, 0x1
0004d8:  b4d8  skpnz
0004da:  ef70  goto    0x0004e0
0004dc:  f002
0004de:  2ba6  incf    0xa6, 0x1, 0x1
0004e0:  0e02  movlw   0x02
0004e2:  61a6  cpfslt  0xa6, 0x1
0004e4:  ef75  goto    0x0004ea
0004e6:  f002
0004e8:  d7b0  bra     0x00044a
0004ea:  0e02  movlw   0x02
0004ec:  63a6  cpfseq  0xa6, 0x1
0004ee:  ef7c  goto    0x0004f8
0004f0:  f002
0004f2:  c0b6  movff   0x0b6, 0x02f
0004f4:  f02f
0004f6:  d7a9  bra     0x00044a
0004f8:  c0b6  movff   0x0b6, 0x030
0004fa:  f030
0004fc:  0e01  movlw   0x01
0004fe:  6fa6  movwf   0xa6, 0x1
000500:  0e03  movlw   0x03
000502:  622f  cpfseq  0x2f, 0x0
000504:  efab  goto    0x000556
000506:  f002
000508:  2c30  decfsz  0x30, 0x0, 0x0
00050a:  ef8a  goto    0x000514
00050c:  f002
00050e:  821f  bsf     0x1f, 0x1, 0x0
000510:  efa9  goto    0x000552
000512:  f002
000514:  5230  movf    0x30, 0x1, 0x0
000516:  a4d8  skpz
000518:  ef91  goto    0x000522
00051a:  f002
00051c:  921f  bcf     0x1f, 0x1, 0x0
00051e:  efa9  goto    0x000552
000520:  f002
000522:  0e02  movlw   0x02
000524:  6230  cpfseq  0x30, 0x0
000526:  efa0  goto    0x000540
000528:  f002
00052a:  ba1f  btfsc   0x1f, 0x5, 0x0
00052c:  ef9e  goto    0x00053c
00052e:  f002
000530:  0e2f  movlw   0x2f
000532:  6fb4  movwf   0xb4, 0x1
000534:  0e75  movlw   0x75
000536:  6fb5  movwf   0xb5, 0x1
000538:  8a1f  bsf     0x1f, 0x5, 0x0
00053a:  861f  bsf     0x1f, 0x3, 0x0
00053c:  efa9  goto    0x000552
00053e:  f002
000540:  0e03  movlw   0x03
000542:  6230  cpfseq  0x30, 0x0
000544:  efa9  goto    0x000552
000546:  f002
000548:  aa1f  btfss   0x1f, 0x5, 0x0
00054a:  efa9  goto    0x000552
00054c:  f002
00054e:  9a1f  bcf     0x1f, 0x5, 0x0
000550:  861f  bsf     0x1f, 0x3, 0x0
000552:  eff5  goto    0x0005ea
000554:  f002
000556:  0e04  movlw   0x04
000558:  622f  cpfseq  0x2f, 0x0
00055a:  efb1  goto    0x000562
00055c:  f002
00055e:  eff5  goto    0x0005ea
000560:  f002
000562:  0e05  movlw   0x05
000564:  622f  cpfseq  0x2f, 0x0
000566:  efbd  goto    0x00057a
000568:  f002
00056a:  0e04  movlw   0x04
00056c:  6030  cpfslt  0x30, 0x0
00056e:  efbb  goto    0x000576
000570:  f002
000572:  c030  movff   0x030, 0x0a1
000574:  f0a1
000576:  eff5  goto    0x0005ea
000578:  f002
00057a:  0e06  movlw   0x06
00057c:  622f  cpfseq  0x2f, 0x0
00057e:  efd6  goto    0x0005ac
000580:  f002
000582:  0e01  movlw   0x01
000584:  5c32  subwf   0x32, 0x0, 0x0
000586:  b4d8  skpnz
000588:  efd4  goto    0x0005a8
00058a:  f002
00058c:  0e09  movlw   0x09
00058e:  6030  cpfslt  0x30, 0x0
000590:  efd4  goto    0x0005a8
000592:  f002
000594:  51b8  movf    0xb8, 0x0, 0x1
000596:  5c30  subwf   0x30, 0x0, 0x0
000598:  b4d8  skpnz
00059a:  efd4  goto    0x0005a8
00059c:  f002
00059e:  c030  movff   0x030, 0x0b8
0005a0:  f0b8
0005a2:  861f  bsf     0x1f, 0x3, 0x0
0005a4:  ec0e  call    0x00061c, 0x0
0005a6:  f003
0005a8:  eff5  goto    0x0005ea
0005aa:  f002
0005ac:  0e07  movlw   0x07
0005ae:  622f  cpfseq  0x2f, 0x0
0005b0:  efe8  goto    0x0005d0
0005b2:  f002
0005b4:  0e73  movlw   0x73
0005b6:  6030  cpfslt  0x30, 0x0
0005b8:  efe6  goto    0x0005cc
0005ba:  f002
0005bc:  51b9  movf    0xb9, 0x0, 0x1
0005be:  5c30  subwf   0x30, 0x0, 0x0
0005c0:  b4d8  skpnz
0005c2:  efe4  goto    0x0005c8
0005c4:  f002
0005c6:  861f  bsf     0x1f, 0x3, 0x0
0005c8:  c030  movff   0x030, 0x0b9
0005ca:  f0b9
0005cc:  eff5  goto    0x0005ea
0005ce:  f002
0005d0:  0e1d  movlw   0x1d
0005d2:  622f  cpfseq  0x2f, 0x0
0005d4:  eff5  goto    0x0005ea
0005d6:  f002
0005d8:  51a7  movf    0xa7, 0x0, 0x1
0005da:  5c30  subwf   0x30, 0x0, 0x0
0005dc:  b4d8  skpnz
0005de:  eff5  goto    0x0005ea
0005e0:  f002
0005e2:  c030  movff   0x030, 0x0a7
0005e4:  f0a7
0005e6:  ecaa  call    0x000f54, 0x0
0005e8:  f007
0005ea:  d72f  bra     0x00044a
; ===========================================================================
; function_020 @ 0x0005EC — tx_byte_enqueue   (V1.6b @ 0x00060C in agent map)
; ---------------------------------------------------------------------------
; Enqueues 0x027 (tx_data_staging) into the 48-byte TX ring at 0x036+. The
; ring is read by the ISR via PIE1.TXIE (kicked at the bottom of this
; routine after committing the new tx_ring_wr).  Producer-side index is
; 0x097, consumer-side is 0x096.  Wrapping at 0x30 (= 48 bytes).
;
; If the ring is FULL when the producer arrives, the routine drops into
; the busy-wait at 0x00060C (label_068, BUG C6) — see annotation there.
; ===========================================================================
0005ec:  ee00  lfsr    0x0, 0x036           ; FSR0 = 0x0036 (TX ring base)
0005ee:  f036
0005f0:  5197  movf    0x97, 0x0, 0x1       ; W = tx_ring_wr
0005f2:  c027  movff   0x027, 0xfeb         ; INDF0 = tx_data_staging (write byte)
0005f4:  ffeb
0005f6:  2997  incf    0x97, 0x0, 0x1
0005f8:  6e27  movwf   0x27, 0x0
0005fa:  0e30  movlw   0x30                  ; ring size = 48 bytes
0005fc:  5c27  subwf   0x27, 0x0, 0x0       ; wrap?
0005fe:  a0d8  skpc
000600:  ef03  goto    0x000606
000602:  f003
000604:  6a27  clrf    0x27, 0x0
; ===========================================================================
; label_068 (within function_020 path) @ 0x00060C — *** BUG C6 ***
; ---------------------------------------------------------------------------
; tx_full_busywait — when the producer has filled the 48-byte TX ring
; (tx_ring_wr +1 == tx_ring_rd), this loop spins until the ISR consumes
; a byte. There is NO timeout, NO backpressure mechanism, NO escalation.
;
; Fail mode: if the ISR cannot make progress (e.g. TXIE was killed by the
; original V1.62b control_uart_soft_recover — see V162B_STDBY_TXIE_BUG;
; or the EUSART hangs due to a hardware glitch with no WDT to recover),
; CONTROL spins here forever. The standby/wake/preset frame queued just
; before this point never reaches MAIN, and the user sees the "panel
; works but PBs don't react" pattern.
;
; The V1.62b path went a step further by clearing PIE1.TXIE during OERR
; recovery, *guaranteeing* a stranded byte. The 2026-03-14 bug fix
; (V162B_STDBY_TXIE_BUG.md) removed the bcf PIE1, TXIE so this loop
; can at least drain on the next ISR pass.
; ===========================================================================
000606:  a89d  btfss   0x9d, 0x4, 0x0       ; PIE1.TXIE armed?
000608:  ef0a  goto    0x000614             ;  no -> skip and arm
00060a:  f003
00060c:  5027  movf    0x27, 0x0, 0x0       ; W = next-write index
00060e:  5d96  subwf   0x96, 0x0, 0x1       ; compare to tx_ring_rd
000610:  b4d8  skpnz                         ; equal? (ring full)
000612:  d7fc  bra     0x00060c             ; *** BUG C6: spin forever if so ***
000614:  c027  movff   0x027, 0x097         ; commit new tx_ring_wr
000616:  f097
000618:  889d  bsf     0x9d, 0x4, 0x0       ; PIE1.TXIE = 1 (kick ISR)
00061a:  0012  return  0x0
00061c:  5230  movf    0x30, 0x1, 0x0
00061e:  a4d8  skpz
000620:  ef15  goto    0x00062a
000622:  f003
000624:  6bb7  clrf    0xb7, 0x1
000626:  efb4  goto    0x000768
000628:  f003
00062a:  2c30  decfsz  0x30, 0x0, 0x0
00062c:  ef1c  goto    0x000638
00062e:  f003
000630:  0e05  movlw   0x05
000632:  6fb7  movwf   0xb7, 0x1
000634:  efb4  goto    0x000768
000636:  f003
000638:  0e02  movlw   0x02
00063a:  6230  cpfseq  0x30, 0x0
00063c:  ef2c  goto    0x000658
00063e:  f003
000640:  53a1  movf    0xa1, 0x1, 0x1
000642:  b4d8  skpnz
000644:  ef28  goto    0x000650
000646:  f003
000648:  0e06  movlw   0x06
00064a:  6fb7  movwf   0xb7, 0x1
00064c:  ef2a  goto    0x000654
00064e:  f003
000650:  0e01  movlw   0x01
000652:  6fb7  movwf   0xb7, 0x1
000654:  efb4  goto    0x000768
000656:  f003
000658:  0e03  movlw   0x03
00065a:  6230  cpfseq  0x30, 0x0
00065c:  ef43  goto    0x000686
00065e:  f003
000660:  53a1  movf    0xa1, 0x1, 0x1
000662:  b4d8  skpnz
000664:  ef3f  goto    0x00067e
000666:  f003
000668:  2da1  decfsz  0xa1, 0x0, 0x1
00066a:  ef3b  goto    0x000676
00066c:  f003
00066e:  0e01  movlw   0x01
000670:  6fb7  movwf   0xb7, 0x1
000672:  ef3d  goto    0x00067a
000674:  f003
000676:  0e07  movlw   0x07
000678:  6fb7  movwf   0xb7, 0x1
00067a:  ef41  goto    0x000682
00067c:  f003
00067e:  0e02  movlw   0x02
000680:  6fb7  movwf   0xb7, 0x1
000682:  efb4  goto    0x000768
000684:  f003
000686:  0e04  movlw   0x04
000688:  6230  cpfseq  0x30, 0x0
00068a:  ef62  goto    0x0006c4
00068c:  f003
00068e:  53a1  movf    0xa1, 0x1, 0x1
000690:  b4d8  skpnz
000692:  ef5e  goto    0x0006bc
000694:  f003
000696:  2da1  decfsz  0xa1, 0x0, 0x1
000698:  ef50  goto    0x0006a0
00069a:  f003
00069c:  0e02  movlw   0x02
00069e:  6fb7  movwf   0xb7, 0x1
0006a0:  0e02  movlw   0x02
0006a2:  63a1  cpfseq  0xa1, 0x1
0006a4:  ef56  goto    0x0006ac
0006a6:  f003
0006a8:  0e01  movlw   0x01
0006aa:  6fb7  movwf   0xb7, 0x1
0006ac:  0e03  movlw   0x03
0006ae:  63a1  cpfseq  0xa1, 0x1
0006b0:  ef5c  goto    0x0006b8
0006b2:  f003
0006b4:  0e08  movlw   0x08
0006b6:  6fb7  movwf   0xb7, 0x1
0006b8:  ef60  goto    0x0006c0
0006ba:  f003
0006bc:  0e03  movlw   0x03
0006be:  6fb7  movwf   0xb7, 0x1
0006c0:  efb4  goto    0x000768
0006c2:  f003
0006c4:  0e05  movlw   0x05
0006c6:  6230  cpfseq  0x30, 0x0
0006c8:  ef81  goto    0x000702
0006ca:  f003
0006cc:  53a1  movf    0xa1, 0x1, 0x1
0006ce:  b4d8  skpnz
0006d0:  ef7d  goto    0x0006fa
0006d2:  f003
0006d4:  2da1  decfsz  0xa1, 0x0, 0x1
0006d6:  ef6f  goto    0x0006de
0006d8:  f003
0006da:  0e03  movlw   0x03
0006dc:  6fb7  movwf   0xb7, 0x1
0006de:  0e02  movlw   0x02
0006e0:  63a1  cpfseq  0xa1, 0x1
0006e2:  ef75  goto    0x0006ea
0006e4:  f003
0006e6:  0e02  movlw   0x02
0006e8:  6fb7  movwf   0xb7, 0x1
0006ea:  0e03  movlw   0x03
0006ec:  63a1  cpfseq  0xa1, 0x1
0006ee:  ef7b  goto    0x0006f6
0006f0:  f003
0006f2:  0e01  movlw   0x01
0006f4:  6fb7  movwf   0xb7, 0x1
0006f6:  ef7f  goto    0x0006fe
0006f8:  f003
0006fa:  0e04  movlw   0x04
0006fc:  6fb7  movwf   0xb7, 0x1
0006fe:  efb4  goto    0x000768
000700:  f003
000702:  0e06  movlw   0x06
000704:  6230  cpfseq  0x30, 0x0
000706:  ef98  goto    0x000730
000708:  f003
00070a:  2da1  decfsz  0xa1, 0x0, 0x1
00070c:  ef8a  goto    0x000714
00070e:  f003
000710:  0e04  movlw   0x04
000712:  6fb7  movwf   0xb7, 0x1
000714:  0e02  movlw   0x02
000716:  63a1  cpfseq  0xa1, 0x1
000718:  ef90  goto    0x000720
00071a:  f003
00071c:  0e03  movlw   0x03
00071e:  6fb7  movwf   0xb7, 0x1
000720:  0e03  movlw   0x03
000722:  63a1  cpfseq  0xa1, 0x1
000724:  ef96  goto    0x00072c
000726:  f003
000728:  0e02  movlw   0x02
00072a:  6fb7  movwf   0xb7, 0x1
00072c:  efb4  goto    0x000768
00072e:  f003
000730:  0e07  movlw   0x07
000732:  6230  cpfseq  0x30, 0x0
000734:  efaa  goto    0x000754
000736:  f003
000738:  0e02  movlw   0x02
00073a:  63a1  cpfseq  0xa1, 0x1
00073c:  efa2  goto    0x000744
00073e:  f003
000740:  0e04  movlw   0x04
000742:  6fb7  movwf   0xb7, 0x1
000744:  0e03  movlw   0x03
000746:  63a1  cpfseq  0xa1, 0x1
000748:  efa8  goto    0x000750
00074a:  f003
00074c:  0e03  movlw   0x03
00074e:  6fb7  movwf   0xb7, 0x1
000750:  efb4  goto    0x000768
000752:  f003
000754:  0e08  movlw   0x08
000756:  6230  cpfseq  0x30, 0x0
000758:  efb4  goto    0x000768
00075a:  f003
00075c:  0e03  movlw   0x03
00075e:  63a1  cpfseq  0xa1, 0x1
000760:  efb4  goto    0x000768
000762:  f003
000764:  0e04  movlw   0x04
000766:  6fb7  movwf   0xb7, 0x1
000768:  0012  return  0x0
00076a:  53b7  movf    0xb7, 0x1, 0x1
00076c:  a4d8  skpz
00076e:  efbc  goto    0x000778
000770:  f003
000772:  6bb8  clrf    0xb8, 0x1
000774:  ef55  goto    0x0008aa
000776:  f004
000778:  2db7  decfsz  0xb7, 0x0, 0x1
00077a:  efda  goto    0x0007b4
00077c:  f003
00077e:  53a1  movf    0xa1, 0x1, 0x1
000780:  b4d8  skpnz
000782:  efd6  goto    0x0007ac
000784:  f003
000786:  2da1  decfsz  0xa1, 0x0, 0x1
000788:  efc8  goto    0x000790
00078a:  f003
00078c:  0e03  movlw   0x03
00078e:  6fb8  movwf   0xb8, 0x1
000790:  0e02  movlw   0x02
000792:  63a1  cpfseq  0xa1, 0x1
000794:  efce  goto    0x00079c
000796:  f003
000798:  0e04  movlw   0x04
00079a:  6fb8  movwf   0xb8, 0x1
00079c:  0e03  movlw   0x03
00079e:  63a1  cpfseq  0xa1, 0x1
0007a0:  efd4  goto    0x0007a8
0007a2:  f003
0007a4:  0e05  movlw   0x05
0007a6:  6fb8  movwf   0xb8, 0x1
0007a8:  efd8  goto    0x0007b0
0007aa:  f003
0007ac:  0e02  movlw   0x02
0007ae:  6fb8  movwf   0xb8, 0x1
0007b0:  ef55  goto    0x0008aa
0007b2:  f004
0007b4:  0e02  movlw   0x02
0007b6:  63b7  cpfseq  0xb7, 0x1
0007b8:  eff9  goto    0x0007f2
0007ba:  f003
0007bc:  53a1  movf    0xa1, 0x1, 0x1
0007be:  b4d8  skpnz
0007c0:  eff5  goto    0x0007ea
0007c2:  f003
0007c4:  2da1  decfsz  0xa1, 0x0, 0x1
0007c6:  efe7  goto    0x0007ce
0007c8:  f003
0007ca:  0e04  movlw   0x04
0007cc:  6fb8  movwf   0xb8, 0x1
0007ce:  0e02  movlw   0x02
0007d0:  63a1  cpfseq  0xa1, 0x1
0007d2:  efed  goto    0x0007da
0007d4:  f003
0007d6:  0e05  movlw   0x05
0007d8:  6fb8  movwf   0xb8, 0x1
0007da:  0e03  movlw   0x03
0007dc:  63a1  cpfseq  0xa1, 0x1
0007de:  eff3  goto    0x0007e6
0007e0:  f003
0007e2:  0e06  movlw   0x06
0007e4:  6fb8  movwf   0xb8, 0x1
0007e6:  eff7  goto    0x0007ee
0007e8:  f003
0007ea:  0e03  movlw   0x03
0007ec:  6fb8  movwf   0xb8, 0x1
0007ee:  ef55  goto    0x0008aa
0007f0:  f004
0007f2:  0e03  movlw   0x03
0007f4:  63b7  cpfseq  0xb7, 0x1
0007f6:  ef18  goto    0x000830
0007f8:  f004
0007fa:  53a1  movf    0xa1, 0x1, 0x1
0007fc:  b4d8  skpnz
0007fe:  ef14  goto    0x000828
000800:  f004
000802:  2da1  decfsz  0xa1, 0x0, 0x1
000804:  ef06  goto    0x00080c
000806:  f004
000808:  0e05  movlw   0x05
00080a:  6fb8  movwf   0xb8, 0x1
00080c:  0e02  movlw   0x02
00080e:  63a1  cpfseq  0xa1, 0x1
000810:  ef0c  goto    0x000818
000812:  f004
000814:  0e06  movlw   0x06
000816:  6fb8  movwf   0xb8, 0x1
000818:  0e03  movlw   0x03
00081a:  63a1  cpfseq  0xa1, 0x1
00081c:  ef12  goto    0x000824
00081e:  f004
000820:  0e07  movlw   0x07
000822:  6fb8  movwf   0xb8, 0x1
000824:  ef16  goto    0x00082c
000826:  f004
000828:  0e04  movlw   0x04
00082a:  6fb8  movwf   0xb8, 0x1
00082c:  ef55  goto    0x0008aa
00082e:  f004
000830:  0e04  movlw   0x04
000832:  63b7  cpfseq  0xb7, 0x1
000834:  ef37  goto    0x00086e
000836:  f004
000838:  53a1  movf    0xa1, 0x1, 0x1
00083a:  b4d8  skpnz
00083c:  ef33  goto    0x000866
00083e:  f004
000840:  2da1  decfsz  0xa1, 0x0, 0x1
000842:  ef25  goto    0x00084a
000844:  f004
000846:  0e06  movlw   0x06
000848:  6fb8  movwf   0xb8, 0x1
00084a:  0e02  movlw   0x02
00084c:  63a1  cpfseq  0xa1, 0x1
00084e:  ef2b  goto    0x000856
000850:  f004
000852:  0e07  movlw   0x07
000854:  6fb8  movwf   0xb8, 0x1
000856:  0e03  movlw   0x03
000858:  63a1  cpfseq  0xa1, 0x1
00085a:  ef31  goto    0x000862
00085c:  f004
00085e:  0e08  movlw   0x08
000860:  6fb8  movwf   0xb8, 0x1
000862:  ef35  goto    0x00086a
000864:  f004
000866:  0e05  movlw   0x05
000868:  6fb8  movwf   0xb8, 0x1
00086a:  ef55  goto    0x0008aa
00086c:  f004
00086e:  0e05  movlw   0x05
000870:  63b7  cpfseq  0xb7, 0x1
000872:  ef3f  goto    0x00087e
000874:  f004
000876:  0e01  movlw   0x01
000878:  6fb8  movwf   0xb8, 0x1
00087a:  ef55  goto    0x0008aa
00087c:  f004
00087e:  0e06  movlw   0x06
000880:  63b7  cpfseq  0xb7, 0x1
000882:  ef47  goto    0x00088e
000884:  f004
000886:  0e02  movlw   0x02
000888:  6fb8  movwf   0xb8, 0x1
00088a:  ef55  goto    0x0008aa
00088c:  f004
00088e:  0e07  movlw   0x07
000890:  63b7  cpfseq  0xb7, 0x1
000892:  ef4f  goto    0x00089e
000894:  f004
000896:  0e03  movlw   0x03
000898:  6fb8  movwf   0xb8, 0x1
00089a:  ef55  goto    0x0008aa
00089c:  f004
00089e:  0e08  movlw   0x08
0008a0:  63b7  cpfseq  0xb7, 0x1
0008a2:  ef55  goto    0x0008aa
0008a4:  f004
0008a6:  0e04  movlw   0x04
0008a8:  6fb8  movwf   0xb8, 0x1
0008aa:  0012  return  0x0

; ===========================================================================
; function_023 @ 0x0008AC — button_scan_debounce  (V1.6b address)
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
0008ac:  6827  setf    0x27, 0x0            ; preset all bits high
0008ae:  8027  bsf     0x27, 0x0, 0x0
0008b0:  a680  btfss   0x80, 0x3, 0x0       ; PORTA.bit3 = Standby (active-low)
0008b2:  9027  bcf     0x27, 0x0, 0x0
0008b4:  8227  bsf     0x27, 0x1, 0x0
0008b6:  a082  btfss   0x82, 0x0, 0x0       ; PORTC.bit0 = Up
0008b8:  9227  bcf     0x27, 0x1, 0x0
0008ba:  8427  bsf     0x27, 0x2, 0x0
0008bc:  a480  btfss   0x80, 0x2, 0x0       ; PORTA.bit2 = Down
0008be:  9427  bcf     0x27, 0x2, 0x0
0008c0:  8627  bsf     0x27, 0x3, 0x0
0008c2:  a280  btfss   0x80, 0x1, 0x0
0008c4:  9627  bcf     0x27, 0x3, 0x0
0008c6:  8827  bsf     0x27, 0x4, 0x0
0008c8:  aa82  btfss   0x82, 0x5, 0x0
0008ca:  9827  bcf     0x27, 0x4, 0x0
0008cc:  8a27  bsf     0x27, 0x5, 0x0
0008ce:  a880  btfss   0x80, 0x4, 0x0
0008d0:  9a27  bcf     0x27, 0x5, 0x0
0008d2:  0eff  movlw   0xff
0008d4:  1a27  xorwf   0x27, 0x1, 0x0
0008d6:  5027  movf    0x27, 0x0, 0x0
0008d8:  5dbc  subwf   0xbc, 0x0, 0x1
0008da:  b4d8  skpnz
0008dc:  ef75  goto    0x0008ea
0008de:  f004
0008e0:  6bbb  clrf    0xbb, 0x1
0008e2:  c027  movff   0x027, 0x0bc
0008e4:  f0bc
0008e6:  ef7e  goto    0x0008fc
0008e8:  f004
0008ea:  0e04  movlw   0x04
0008ec:  61bb  cpfslt  0xbb, 0x1
0008ee:  ef7c  goto    0x0008f8
0008f0:  f004
0008f2:  2bbb  incf    0xbb, 0x1, 0x1
0008f4:  ef7e  goto    0x0008fc
0008f6:  f004
0008f8:  c0bc  movff   0x0bc, 0x0be
0008fa:  f0be
0008fc:  6b9a  clrf    0x9a, 0x1
0008fe:  51be  movf    0xbe, 0x0, 0x1
000900:  5dbd  subwf   0xbd, 0x0, 0x1
000902:  b4d8  skpnz
000904:  ef8c  goto    0x000918
000906:  f004
000908:  c0be  movff   0x0be, 0x0bd
00090a:  f0bd
00090c:  6b9b  clrf    0x9b, 0x1
00090e:  6b9c  clrf    0x9c, 0x1
000910:  c0be  movff   0x0be, 0x09a
000912:  f09a
000914:  ef92  goto    0x000924
000916:  f004
000918:  31be  rrcf    0xbe, 0x0, 0x1
00091a:  b0d8  skpnc
00091c:  ef92  goto    0x000924
00091e:  f004
000920:  4b9b  infsnz  0x9b, 0x1, 0x1
000922:  2b9c  incf    0x9c, 0x1, 0x1
000924:  0ec9  movlw   0xc9
000926:  5d9b  subwf   0x9b, 0x0, 0x1
000928:  0e32  movlw   0x32
00092a:  599c  subwfb  0x9c, 0x0, 0x1
00092c:  a0d8  skpc
00092e:  ef9f  goto    0x00093e
000930:  f004
000932:  0e28  movlw   0x28
000934:  6f9b  movwf   0x9b, 0x1
000936:  0e23  movlw   0x23
000938:  6f9c  movwf   0x9c, 0x1
00093a:  c0be  movff   0x0be, 0x09a
00093c:  f09a
00093e:  0012  return  0x0
000940:  c027  movff   0x027, 0x02b
000942:  f02b
000944:  6a2c  clrf    0x2c, 0x0
000946:  502c  movf    0x2c, 0x0, 0x0
000948:  0d10  mullw   0x10
00094a:  cff3  movff   0xff3, 0x02c
00094c:  f02c
00094e:  502b  movf    0x2b, 0x0, 0x0
000950:  0d10  mullw   0x10
000952:  cff3  movff   0xff3, 0x02b
000954:  f02b
000956:  50f4  movf    0xf4, 0x0, 0x0
000958:  262c  addwf   0x2c, 0x1, 0x0
00095a:  502b  movf    0x2b, 0x0, 0x0
00095c:  2629  addwf   0x29, 0x1, 0x0
00095e:  502c  movf    0x2c, 0x0, 0x0
000960:  222a  addwfc  0x2a, 0x1, 0x0
000962:  6a27  clrf    0x27, 0x0
000964:  0e10  movlw   0x10
000966:  6027  cpfslt  0x27, 0x0
000968:  efc7  goto    0x00098e
00096a:  f004
00096c:  5027  movf    0x27, 0x0, 0x0
00096e:  2429  addwf   0x29, 0x0, 0x0
000970:  6ef6  movwf   0xf6, 0x0
000972:  0e00  movlw   0x00
000974:  202a  addwfc  0x2a, 0x0, 0x0
000976:  6ef7  movwf   0xf7, 0x0
000978:  6aa6  clrf    0xa6, 0x0
00097a:  8ea6  bsf     0xa6, 0x7, 0x0
00097c:  0008  tblrd*
00097e:  cff5  movff   0xff5, 0x028
000980:  f028
000982:  5028  movf    0x28, 0x0, 0x0
000984:  ec76  call    0x0000ec, 0x0
000986:  f000
000988:  2a27  incf    0x27, 0x1, 0x0
00098a:  a4d8  skpz
00098c:  d7eb  bra     0x000964
00098e:  0012  return  0x0
000990:  6aa9  clrf    0xa9, 0x0
000992:  51bf  movf    0xbf, 0x0, 0x1
000994:  ecd1  call    0x0001a2, 0x0
000996:  f000
000998:  0e01  movlw   0x01
00099a:  6ea9  movwf   0xa9, 0x0
00099c:  51ba  movf    0xba, 0x0, 0x1
00099e:  ecd1  call    0x0001a2, 0x0
0009a0:  f000
0009a2:  0e02  movlw   0x02
0009a4:  6ea9  movwf   0xa9, 0x0
0009a6:  51c0  movf    0xc0, 0x0, 0x1
0009a8:  ecd1  call    0x0001a2, 0x0
0009aa:  f000
0009ac:  6a27  clrf    0x27, 0x0
0009ae:  0e06  movlw   0x06
0009b0:  6027  cpfslt  0x27, 0x0
0009b2:  ef1d  goto    0x000a3a
0009b4:  f005
0009b6:  0e03  movlw   0x03
0009b8:  2427  addwf   0x27, 0x0, 0x0
0009ba:  6ea9  movwf   0xa9, 0x0
0009bc:  ee00  lfsr    0x0, 0x0c1
0009be:  f0c1
0009c0:  5027  movf    0x27, 0x0, 0x0
0009c2:  50eb  movf    0xeb, 0x0, 0x0
0009c4:  ecd1  call    0x0001a2, 0x0
0009c6:  f000
0009c8:  0e09  movlw   0x09
0009ca:  2427  addwf   0x27, 0x0, 0x0
0009cc:  6ea9  movwf   0xa9, 0x0
0009ce:  ee00  lfsr    0x0, 0x0c7
0009d0:  f0c7
0009d2:  5027  movf    0x27, 0x0, 0x0
0009d4:  50eb  movf    0xeb, 0x0, 0x0
0009d6:  ecd1  call    0x0001a2, 0x0
0009d8:  f000
0009da:  0e0f  movlw   0x0f
0009dc:  2427  addwf   0x27, 0x0, 0x0
0009de:  6ea9  movwf   0xa9, 0x0
0009e0:  ee00  lfsr    0x0, 0x0cd
0009e2:  f0cd
0009e4:  5027  movf    0x27, 0x0, 0x0
0009e6:  50eb  movf    0xeb, 0x0, 0x0
0009e8:  ecd1  call    0x0001a2, 0x0
0009ea:  f000
0009ec:  0e15  movlw   0x15
0009ee:  2427  addwf   0x27, 0x0, 0x0
0009f0:  6ea9  movwf   0xa9, 0x0
0009f2:  ee00  lfsr    0x0, 0x0d3
0009f4:  f0d3
0009f6:  5027  movf    0x27, 0x0, 0x0
0009f8:  50eb  movf    0xeb, 0x0, 0x0
0009fa:  ecd1  call    0x0001a2, 0x0
0009fc:  f000
0009fe:  0e1b  movlw   0x1b
000a00:  2427  addwf   0x27, 0x0, 0x0
000a02:  6ea9  movwf   0xa9, 0x0
000a04:  ee00  lfsr    0x0, 0x0d9
000a06:  f0d9
000a08:  5027  movf    0x27, 0x0, 0x0
000a0a:  50eb  movf    0xeb, 0x0, 0x0
000a0c:  ecd1  call    0x0001a2, 0x0
000a0e:  f000
000a10:  0e21  movlw   0x21
000a12:  2427  addwf   0x27, 0x0, 0x0
000a14:  6ea9  movwf   0xa9, 0x0
000a16:  ee00  lfsr    0x0, 0x0df
000a18:  f0df
000a1a:  5027  movf    0x27, 0x0, 0x0
000a1c:  50eb  movf    0xeb, 0x0, 0x0
000a1e:  ecd1  call    0x0001a2, 0x0
000a20:  f000
000a22:  0e27  movlw   0x27
000a24:  2427  addwf   0x27, 0x0, 0x0
000a26:  6ea9  movwf   0xa9, 0x0
000a28:  ee00  lfsr    0x0, 0x0e5
000a2a:  f0e5
000a2c:  5027  movf    0x27, 0x0, 0x0
000a2e:  50eb  movf    0xeb, 0x0, 0x0
000a30:  ecd1  call    0x0001a2, 0x0
000a32:  f000
000a34:  2a27  incf    0x27, 0x1, 0x0
000a36:  a4d8  skpz
000a38:  d7ba  bra     0x0009ae
000a3a:  0e73  movlw   0x73
000a3c:  6ea9  movwf   0xa9, 0x0
000a3e:  51eb  movf    0xeb, 0x0, 0x1
000a40:  ecd1  call    0x0001a2, 0x0
000a42:  f000
000a44:  0012  return  0x0

; ===========================================================================
; function_026 @ 0x000A46 — settings_load_eeprom  (V1.6b address)
; ---------------------------------------------------------------------------
; Reads saved settings from EEPROM at boot:
;   EEPROM[0x00] -> 0x0BF (display_state_index, V1.6b)
;   EEPROM[0x01] -> 0x0BA (some flag/mode byte)
;   EEPROM[0x02..0x0B] -> 0x0C1..0x0CC (channel config, backlight, etc.)
; Calls function_010 (0x000196) for each byte read. The values are then
; reflected into the corresponding outgoing frames (input/volume/mute/
; display) on the next periodic emission.
; ===========================================================================
000a46:  0e00  movlw   0x00                  ; EEPROM addr 0x00
000a48:  eccb  call    0x000196, 0x0        ; function_010 — eeprom_read_byte
000a4a:  f000
000a4c:  6fbf  movwf   0xbf, 0x1            ; 0x0BF = display_state_index
000a4e:  0e01  movlw   0x01                  ; EEPROM addr 0x01
000a50:  eccb  call    0x000196, 0x0
000a52:  f000
000a54:  6fba  movwf   0xba, 0x1            ; 0x0BA = mode flag (V1.6b)
000a56:  0e02  movlw   0x02                  ; EEPROM addr 0x02
000a58:  eccb  call    0x000196, 0x0
000a5a:  f000
000a5c:  6fc0  movwf   0xc0, 0x1
000a5e:  6a27  clrf    0x27, 0x0
000a60:  0e06  movlw   0x06
000a62:  6027  cpfslt  0x27, 0x0
000a64:  ef7d  goto    0x000afa
000a66:  f005
000a68:  0e03  movlw   0x03
000a6a:  2427  addwf   0x27, 0x0, 0x0
000a6c:  eccb  call    0x000196, 0x0
000a6e:  f000
000a70:  6e0a  movwf   0x0a, 0x0
000a72:  ee00  lfsr    0x0, 0x0c1
000a74:  f0c1
000a76:  5027  movf    0x27, 0x0, 0x0
000a78:  c00a  movff   0x00a, 0xfeb
000a7a:  ffeb
000a7c:  0e09  movlw   0x09
000a7e:  2427  addwf   0x27, 0x0, 0x0
000a80:  eccb  call    0x000196, 0x0
000a82:  f000
000a84:  6e0a  movwf   0x0a, 0x0
000a86:  ee00  lfsr    0x0, 0x0c7
000a88:  f0c7
000a8a:  5027  movf    0x27, 0x0, 0x0
000a8c:  c00a  movff   0x00a, 0xfeb
000a8e:  ffeb
000a90:  0e0f  movlw   0x0f
000a92:  2427  addwf   0x27, 0x0, 0x0
000a94:  eccb  call    0x000196, 0x0
000a96:  f000
000a98:  6e0a  movwf   0x0a, 0x0
000a9a:  ee00  lfsr    0x0, 0x0cd
000a9c:  f0cd
000a9e:  5027  movf    0x27, 0x0, 0x0
000aa0:  c00a  movff   0x00a, 0xfeb
000aa2:  ffeb
000aa4:  0e15  movlw   0x15
000aa6:  2427  addwf   0x27, 0x0, 0x0
000aa8:  eccb  call    0x000196, 0x0
000aaa:  f000
000aac:  6e0a  movwf   0x0a, 0x0
000aae:  ee00  lfsr    0x0, 0x0d3
000ab0:  f0d3
000ab2:  5027  movf    0x27, 0x0, 0x0
000ab4:  c00a  movff   0x00a, 0xfeb
000ab6:  ffeb
000ab8:  0e1b  movlw   0x1b
000aba:  2427  addwf   0x27, 0x0, 0x0
000abc:  eccb  call    0x000196, 0x0
000abe:  f000
000ac0:  6e0a  movwf   0x0a, 0x0
000ac2:  ee00  lfsr    0x0, 0x0d9
000ac4:  f0d9
000ac6:  5027  movf    0x27, 0x0, 0x0
000ac8:  c00a  movff   0x00a, 0xfeb
000aca:  ffeb
000acc:  0e21  movlw   0x21
000ace:  2427  addwf   0x27, 0x0, 0x0
000ad0:  eccb  call    0x000196, 0x0
000ad2:  f000
000ad4:  6e0a  movwf   0x0a, 0x0
000ad6:  ee00  lfsr    0x0, 0x0df
000ad8:  f0df
000ada:  5027  movf    0x27, 0x0, 0x0
000adc:  c00a  movff   0x00a, 0xfeb
000ade:  ffeb
000ae0:  0e27  movlw   0x27
000ae2:  2427  addwf   0x27, 0x0, 0x0
000ae4:  eccb  call    0x000196, 0x0
000ae6:  f000
000ae8:  6e0a  movwf   0x0a, 0x0
000aea:  ee00  lfsr    0x0, 0x0e5
000aec:  f0e5
000aee:  5027  movf    0x27, 0x0, 0x0
000af0:  c00a  movff   0x00a, 0xfeb
000af2:  ffeb
000af4:  2a27  incf    0x27, 0x1, 0x0
000af6:  a4d8  skpz
000af8:  d7b3  bra     0x000a60
000afa:  0e73  movlw   0x73
000afc:  eccb  call    0x000196, 0x0
000afe:  f000
000b00:  6feb  movwf   0xeb, 0x1
000b02:  0e05  movlw   0x05
000b04:  5deb  subwf   0xeb, 0x0, 0x1
000b06:  a0d8  skpc
000b08:  ef88  goto    0x000b10
000b0a:  f005
000b0c:  0e01  movlw   0x01
000b0e:  6feb  movwf   0xeb, 0x1
000b10:  ec3c  call    0x001478, 0x0
000b12:  f00a
000b14:  0012  return  0x0

; ===========================================================================
; function_027 @ 0x000B16 — serial_tx_routed_frame
; ---------------------------------------------------------------------------
; Builds the standard 3-byte CONTROL→MAIN frame and enqueues it via
; function_020. Inputs:
;   • W bit pattern → 0xB0 + route (0 broadcast, 1 addressed)
;   • 0x033 = route bits  • 0x034 = cmd byte  • 0x035 = data byte
; The full_sync_counter at 0x09F:0x0A0 is reset on every successful frame
; emission (so the periodic full_sync_burst trigger is debounced by any
; explicit traffic).
; Used by every other function_028..035 helper as the actual UART driver.
; ===========================================================================
000b16:  0eb0  movlw   0xb0
000b18:  2433  addwf   0x33, 0x0, 0x0       ; W = 0xB0 | route
000b1a:  6e27  movwf   0x27, 0x0            ; tx_data_staging
000b1c:  ecf6  call    0x0005ec, 0x0        ; function_020 (enqueue route byte)
000b1e:  f002
000b20:  c034  movff   0x034, 0x027         ; tx_data_staging = cmd
000b22:  f027
000b24:  ecf6  call    0x0005ec, 0x0        ; function_020 (enqueue cmd byte)
000b26:  f002
000b28:  c035  movff   0x035, 0x027         ; tx_data_staging = data
000b2a:  f027
000b2c:  ecf6  call    0x0005ec, 0x0        ; function_020 (enqueue data byte)
000b2e:  f002
000b30:  6b9f  clrf    0x9f, 0x1            ; reset full_sync_counter low
000b32:  6ba0  clrf    0xa0, 0x1            ; reset full_sync_counter high
000b34:  0012  return  0x0

; ===========================================================================
; function_028 @ 0x000B36 — full_sync_burst    *** BUG C7 ***
; ---------------------------------------------------------------------------
; Emits the 5-frame full status sync to MAIN: volume, input, mute,
; backlight, standby/wake — each with a ~250 µs inter-frame delay
; (function_012 with W=0x05). Triggered when full_sync_counter at
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
000b36:  ec20  call    0x000c40, 0x0        ; function_031 — volume_frame_send
000b38:  f006
000b3a:  0e05  movlw   0x05
000b3c:  ecde  call    0x0001bc, 0x0
000b3e:  f000
000b40:  ec11  call    0x000c22, 0x0
000b42:  f006
000b44:  0e05  movlw   0x05
000b46:  ecde  call    0x0001bc, 0x0
000b48:  f000
000b4a:  ec3e  call    0x000c7c, 0x0
000b4c:  f006
000b4e:  0e05  movlw   0x05
000b50:  ecde  call    0x0001bc, 0x0
000b52:  f000
000b54:  ec2f  call    0x000c5e, 0x0
000b56:  f006
000b58:  0e05  movlw   0x05
000b5a:  ecde  call    0x0001bc, 0x0
000b5c:  f000
000b5e:  ec4c  call    0x000c98, 0x0
000b60:  f006
000b62:  0012  return  0x0

; ===========================================================================
; function_029 @ 0x000B64 — poll_frame_send
; ---------------------------------------------------------------------------
; Emits [B1, 04, 00] — addressed status_poll. MAIN's parser treats cmd=0x04
; as the "respond with full status burst" trigger (bypasses the active
; gate, so even MAINs in standby reply). This is the heartbeat used by
; reconnect_wait_loop (label_212) to test whether MAIN is responding.
; ===========================================================================
000b64:  0eb1  movlw   0xb1                  ; route = 0xB1 (addressed)
000b66:  6e27  movwf   0x27, 0x0
000b68:  ecf6  call    0x0005ec, 0x0        ; enqueue route
000b6a:  f002
000b6c:  0e04  movlw   0x04                  ; cmd = 0x04 (status_poll)
000b6e:  6e27  movwf   0x27, 0x0
000b70:  ecf6  call    0x0005ec, 0x0
000b72:  f002
000b74:  6a27  clrf    0x27, 0x0            ; data = 0x00
000b76:  ecf6  call    0x0005ec, 0x0
000b78:  f002
000b7a:  0012  return  0x0
000b7c:  2828  incf    0x28, 0x0, 0x0
000b7e:  6e33  movwf   0x33, 0x0
000b80:  0e17  movlw   0x17
000b82:  6e34  movwf   0x34, 0x0
000b84:  ee00  lfsr    0x0, 0x0c1
000b86:  f0c1
000b88:  5028  movf    0x28, 0x0, 0x0
000b8a:  50eb  movf    0xeb, 0x0, 0x0
000b8c:  6e35  movwf   0x35, 0x0
000b8e:  dfc3  rcall   0x000b16
000b90:  0012  return  0x0
000b92:  2828  incf    0x28, 0x0, 0x0
000b94:  6e33  movwf   0x33, 0x0
000b96:  0e18  movlw   0x18
000b98:  6e34  movwf   0x34, 0x0
000b9a:  ee00  lfsr    0x0, 0x0c7
000b9c:  f0c7
000b9e:  5028  movf    0x28, 0x0, 0x0
000ba0:  50eb  movf    0xeb, 0x0, 0x0
000ba2:  6e35  movwf   0x35, 0x0
000ba4:  dfb8  rcall   0x000b16
000ba6:  0012  return  0x0
000ba8:  2828  incf    0x28, 0x0, 0x0
000baa:  6e33  movwf   0x33, 0x0
000bac:  0e19  movlw   0x19
000bae:  6e34  movwf   0x34, 0x0
000bb0:  ee00  lfsr    0x0, 0x0cd
000bb2:  f0cd
000bb4:  5028  movf    0x28, 0x0, 0x0
000bb6:  50eb  movf    0xeb, 0x0, 0x0
000bb8:  6e35  movwf   0x35, 0x0
000bba:  dfad  rcall   0x000b16
000bbc:  0012  return  0x0
000bbe:  2828  incf    0x28, 0x0, 0x0
000bc0:  6e33  movwf   0x33, 0x0
000bc2:  0e1a  movlw   0x1a
000bc4:  6e34  movwf   0x34, 0x0
000bc6:  ee00  lfsr    0x0, 0x0d3
000bc8:  f0d3
000bca:  5028  movf    0x28, 0x0, 0x0
000bcc:  50eb  movf    0xeb, 0x0, 0x0
000bce:  6e35  movwf   0x35, 0x0
000bd0:  dfa2  rcall   0x000b16
000bd2:  0012  return  0x0
000bd4:  2828  incf    0x28, 0x0, 0x0
000bd6:  6e33  movwf   0x33, 0x0
000bd8:  0e1b  movlw   0x1b
000bda:  6e34  movwf   0x34, 0x0
000bdc:  ee00  lfsr    0x0, 0x0d9
000bde:  f0d9
000be0:  5028  movf    0x28, 0x0, 0x0
000be2:  50eb  movf    0xeb, 0x0, 0x0
000be4:  6e35  movwf   0x35, 0x0
000be6:  df97  rcall   0x000b16
000be8:  0012  return  0x0
000bea:  2828  incf    0x28, 0x0, 0x0
000bec:  6e33  movwf   0x33, 0x0
000bee:  0e1c  movlw   0x1c
000bf0:  6e34  movwf   0x34, 0x0
000bf2:  ee00  lfsr    0x0, 0x0df
000bf4:  f0df
000bf6:  5028  movf    0x28, 0x0, 0x0
000bf8:  50eb  movf    0xeb, 0x0, 0x0
000bfa:  6e35  movwf   0x35, 0x0
000bfc:  df8c  rcall   0x000b16
000bfe:  0012  return  0x0
000c00:  2828  incf    0x28, 0x0, 0x0
000c02:  6e33  movwf   0x33, 0x0
000c04:  0e1e  movlw   0x1e
000c06:  6e34  movwf   0x34, 0x0
000c08:  ee00  lfsr    0x0, 0x0e5
000c0a:  f0e5
000c0c:  5028  movf    0x28, 0x0, 0x0
000c0e:  50eb  movf    0xeb, 0x0, 0x0
000c10:  6e35  movwf   0x35, 0x0
000c12:  5235  movf    0x35, 0x1, 0x0
000c14:  a4d8  skpz
000c16:  ef0f  goto    0x000c1e
000c18:  f006
000c1a:  0e03  movlw   0x03
000c1c:  6e35  movwf   0x35, 0x0
000c1e:  df7b  rcall   0x000b16
000c20:  0012  return  0x0
; ===========================================================================
; function_030 @ 0x000C22 — input_frame_send  (V1.6b refactor)
; ---------------------------------------------------------------------------
; Emits [B0, 0x06, <0x0B8>] — broadcast input selection. 0x0B8 is the
; cached input value (also one of the boot handshake sentinels; MAIN
; overwrites it during status burst response). NOTE: in V1.4 this same
; address held a *channel_17_config* sender — refactor moved to dedicated
; helpers per cmd in V1.5b+.
; ===========================================================================
000c22:  0eb0  movlw   0xb0                  ; broadcast route
000c24:  6e27  movwf   0x27, 0x0
000c26:  ecf6  call    0x0005ec, 0x0
000c28:  f002
000c2a:  0e06  movlw   0x06                  ; cmd = 0x06 (input_select)
000c2c:  6e27  movwf   0x27, 0x0
000c2e:  ecf6  call    0x0005ec, 0x0
000c30:  f002
000c32:  c0b8  movff   0x0b8, 0x027         ; data = current input (handshake_sentinel_1)
000c34:  f027
000c36:  ecf6  call    0x0005ec, 0x0
000c38:  f002
000c3a:  6b9f  clrf    0x9f, 0x1            ; reset full_sync_counter
000c3c:  6ba0  clrf    0xa0, 0x1
000c3e:  0012  return  0x0

; ===========================================================================
; function_031 @ 0x000C40 — volume_frame_send  (V1.6b refactor)
; ---------------------------------------------------------------------------
; Emits [B0, 0x07, <0x0B9>] — broadcast volume.  0x0B9 holds the cached
; current volume byte (with the protocol's 0x60 offset baked in by MAIN
; on its side). Same V1.4→V1.6b refactor pattern as function_030.
; ===========================================================================
000c40:  0eb0  movlw   0xb0
000c42:  6e27  movwf   0x27, 0x0
000c44:  ecf6  call    0x0005ec, 0x0
000c46:  f002
000c48:  0e07  movlw   0x07                  ; cmd = 0x07 (volume_set)
000c4a:  6e27  movwf   0x27, 0x0
000c4c:  ecf6  call    0x0005ec, 0x0
000c4e:  f002
000c50:  c0b9  movff   0x0b9, 0x027         ; data = current volume (handshake_sentinel_2)
000c52:  f027
000c54:  ecf6  call    0x0005ec, 0x0
000c56:  f002
000c58:  6b9f  clrf    0x9f, 0x1
000c5a:  6ba0  clrf    0xa0, 0x1
000c5c:  0012  return  0x0
000c5e:  0eb0  movlw   0xb0
000c60:  6e27  movwf   0x27, 0x0
000c62:  ecf6  call    0x0005ec, 0x0
000c64:  f002
000c66:  0e1d  movlw   0x1d
000c68:  6e27  movwf   0x27, 0x0
000c6a:  ecf6  call    0x0005ec, 0x0
000c6c:  f002
000c6e:  c0a7  movff   0x0a7, 0x027
000c70:  f027
000c72:  ecf6  call    0x0005ec, 0x0
000c74:  f002
000c76:  6b9f  clrf    0x9f, 0x1
000c78:  6ba0  clrf    0xa0, 0x1
000c7a:  0012  return  0x0
; ===========================================================================
; function_033 @ 0x000C7C — mute_frame_send
; ---------------------------------------------------------------------------
; Emits [B0, 0x03, 0x02/0x03] (broadcast mute_on/mute_off) based on
; 0x01F.bit5 (mute_state — the V1.6b new bit position; in V1.4 it lived
; in 0x01F.bit4, but bit4 was repurposed for display_refresh_pending in
; V1.5b+). Same cmd byte as standby/wake; data discriminates.
; ===========================================================================
000c7c:  6a33  clrf    0x33, 0x0            ; route = 0xB0 broadcast
000c7e:  0e03  movlw   0x03
000c80:  6e34  movwf   0x34, 0x0            ; cmd = 0x03 (cmd03 family)
000c82:  aa1f  btfss   0x1f, 0x5, 0x0       ; mute_state set (V1.6b bit5)?
000c84:  ef48  goto    0x000c90             ;  no -> data = 0x03 (mute_off)
000c86:  f006
000c88:  0e02  movlw   0x02                  ; yes -> data = 0x02 (mute_on)
000c8a:  6e35  movwf   0x35, 0x0
000c8c:  ef4a  goto    0x000c94
000c8e:  f006
000c90:  0e03  movlw   0x03                  ; data = 0x03 (mute_off)
000c92:  6e35  movwf   0x35, 0x0
000c94:  df40  rcall   0x000b16             ; -> function_027
000c96:  0012  return  0x0
; ===========================================================================
; function_034 @ 0x000C98 — standby_wake_broadcast
; ---------------------------------------------------------------------------
; THIS IS THE WAKE/STANDBY ROUTE THAT V1.62b RECONNECT BUG TARGETED.
; Emits [B0, 0x03, 0/1] — broadcast standby_enter or wake based on
; 0x01F.bit1 (connected) at call time:
;    bit1 SET (DISPLAY mode)  → data = 0x01 (wake) — opens MAIN's gate
;    bit1 CLEAR (Zzz mode)    → data = 0x00 (standby) — closes the gate
;
; Stock V1.6b calls this from 0x001294 (the line right before label_212)
; after the user releases STBY, ensuring every MAIN reopens its
; active_flags.bit3. The V1.62b reconnect_wait_stub initially OMITTED
; this call, leaving MAINs deaf to all subsequent volume/mute/preset
; commands until power cycle (V162B_RECONNECT_WAKE_BUG.md). The fix:
; explicit `call 0x000C98` after `bsf 0x01F, 1` in reconnect_wait_done.
; ===========================================================================
000c98:  6a33  clrf    0x33, 0x0            ; route bits = 0 (broadcast = 0xB0)
000c9a:  0e03  movlw   0x03
000c9c:  6e34  movwf   0x34, 0x0            ; cmd = 0x03 (standby/wake/mute)
000c9e:  b21f  btfsc   0x1f, 0x1, 0x0       ; connected (DISPLAY mode)?
000ca0:  ef55  goto    0x000caa             ;  yes -> data = 0x01 (wake)
000ca2:  f006
000ca4:  6a35  clrf    0x35, 0x0            ;  no  -> data = 0x00 (standby)
000ca6:  ef57  goto    0x000cae
000ca8:  f006
000caa:  0e01  movlw   0x01                  ; data = 0x01 (wake)
000cac:  6e35  movwf   0x35, 0x0
000cae:  df33  rcall   0x000b16             ; -> function_027 (emit frame)
000cb0:  0012  return  0x0
; ===========================================================================
; function_035 @ 0x000CB2 — display_loop_iteration   (V1.6b refactor)
; ---------------------------------------------------------------------------
; One iteration of the display/menu loop. Steps:
;   1. Set INTCON3.RBIE (PIE for button RBIF).
;   2. Call function_023 (button_scan_debounce @ 0x0008AC) — reads the
;      6 button GPIOs, debounces (threshold 4 stable samples), updates
;      0x0BE (button_debounced).
;   3. Call function_019 (rx_parser_entry @ 0x00044A) — drain RX ring.
;   4. Decrement 16-bit idle_timeout_counter at 0x09D:0x09E (init 0xEA61
;      = ~60 k iterations). When it crosses zero AND we are still in
;      DISPLAY mode, the panel transitions to standby ("Zzz...").
;   5. Decrement 16-bit full_sync_counter at 0x09F:0x0A0 (init 0x4E20).
;      When it overflows, calls function_028 (full_sync_burst — BUG C7).
; This routine is the periodic "while not in event loop" handler called
; from the main display path.
; ===========================================================================
000cb2:  86f2  bsf     0xf2, 0x3, 0x0       ; INTCON3.RBIE = 1 (button IRQ on)
000cb4:  ec56  call    0x0008ac, 0x0        ; function_023 — button_scan_debounce
000cb6:  f004
000cb8:  ec25  call    0x00044a, 0x0        ; function_019 — rx_parser_entry
000cba:  f002
000cbc:  519e  movf    0x9e, 0x0, 0x1       ; W = idle_timeout_hi
000cbe:  0aea  xorlw   0xea                  ; cmp to 0xEA (init high byte)
000cc0:  0e60  movlw   0x60
000cc2:  b4d8  skpnz
000cc4:  199d  xorwf   0x9d, 0x0, 0x1       ; check init low byte too
000cc6:  a4d8  skpz
000cc8:  ef67  goto    0x000cce
000cca:  f006
000ccc:  de61  rcall   0x000990
000cce:  0e61  movlw   0x61
000cd0:  5d9d  subwf   0x9d, 0x0, 0x1
000cd2:  0eea  movlw   0xea
000cd4:  599e  subwfb  0x9e, 0x0, 0x1
000cd6:  b0d8  skpnc
000cd8:  ef70  goto    0x000ce0
000cda:  f006
000cdc:  4b9d  infsnz  0x9d, 0x1, 0x1
000cde:  2b9e  incf    0x9e, 0x1, 0x1
000ce0:  ece7  call    0x000dce, 0x0
000ce2:  f006
000ce4:  51a0  movf    0xa0, 0x0, 0x1
000ce6:  0a4e  xorlw   0x4e
000ce8:  0e20  movlw   0x20
000cea:  b4d8  skpnz
000cec:  199f  xorwf   0x9f, 0x0, 0x1
000cee:  a4d8  skpz
000cf0:  ef7f  goto    0x000cfe
000cf2:  f006
000cf4:  df20  rcall   0x000b36
000cf6:  6b9f  clrf    0x9f, 0x1
000cf8:  6ba0  clrf    0xa0, 0x1
000cfa:  ef81  goto    0x000d02
000cfc:  f006
000cfe:  4b9f  infsnz  0x9f, 0x1, 0x1
000d00:  2ba0  incf    0xa0, 0x1, 0x1
000d02:  b21f  btfsc   0x1f, 0x1, 0x0
000d04:  ef88  goto    0x000d10
000d06:  f006
000d08:  9294  bcf     0x94, 0x1, 0x0
000d0a:  928b  bcf     0x8b, 0x1, 0x0
000d0c:  efbd  goto    0x000d7a
000d0e:  f006
000d10:  53eb  movf    0xeb, 0x1, 0x1
000d12:  b4d8  skpnz
000d14:  efbb  goto    0x000d76
000d16:  f006
000d18:  51ec  movf    0xec, 0x0, 0x1
000d1a:  5db0  subwf   0xb0, 0x0, 0x1
000d1c:  51ed  movf    0xed, 0x0, 0x1
000d1e:  59b1  subwfb  0xb1, 0x0, 0x1
000d20:  51ee  movf    0xee, 0x0, 0x1
000d22:  59b2  subwfb  0xb2, 0x0, 0x1
000d24:  51ef  movf    0xef, 0x0, 0x1
000d26:  59b3  subwfb  0xb3, 0x0, 0x1
000d28:  51b3  movf    0xb3, 0x0, 0x1
000d2a:  19ef  xorwf   0xef, 0x0, 0x1
000d2c:  b0d8  skpnc
000d2e:  0a80  xorlw   0x80
000d30:  a8d8  skpn
000d32:  ef9f  goto    0x000d3e
000d34:  f006
000d36:  9294  bcf     0x94, 0x1, 0x0
000d38:  928b  bcf     0x8b, 0x1, 0x0
000d3a:  efb9  goto    0x000d72
000d3c:  f006
000d3e:  aa1f  btfss   0x1f, 0x5, 0x0
000d40:  efb2  goto    0x000d64
000d42:  f006
000d44:  4bb4  infsnz  0xb4, 0x1, 0x1
000d46:  2bb5  incf    0xb5, 0x1, 0x1
000d48:  51b5  movf    0xb5, 0x0, 0x1
000d4a:  0a75  xorlw   0x75
000d4c:  0e30  movlw   0x30
000d4e:  b4d8  skpnz
000d50:  19b4  xorwf   0xb4, 0x0, 0x1
000d52:  a4d8  skpz
000d54:  efb0  goto    0x000d60
000d56:  f006
000d58:  7282  btg     0x82, 0x1, 0x0
000d5a:  9294  bcf     0x94, 0x1, 0x0
000d5c:  6bb4  clrf    0xb4, 0x1
000d5e:  6bb5  clrf    0xb5, 0x1
000d60:  efb4  goto    0x000d68
000d62:  f006
000d64:  9294  bcf     0x94, 0x1, 0x0
000d66:  828b  bsf     0x8b, 0x1, 0x0
000d68:  2bb0  incf    0xb0, 0x1, 0x1
000d6a:  0e00  movlw   0x00
000d6c:  23b1  addwfc  0xb1, 0x1, 0x1
000d6e:  23b2  addwfc  0xb2, 0x1, 0x1
000d70:  23b3  addwfc  0xb3, 0x1, 0x1
000d72:  efbd  goto    0x000d7a
000d74:  f006
000d76:  9294  bcf     0x94, 0x1, 0x0
000d78:  828b  bsf     0x8b, 0x1, 0x0
000d7a:  0e00  movlw   0x00
000d7c:  539a  movf    0x9a, 0x1, 0x1
000d7e:  a4d8  skpz
000d80:  0e01  movlw   0x01
000d82:  6e18  movwf   0x18, 0x0
000d84:  6ae8  clrw
000d86:  b61f  btfsc   0x1f, 0x3, 0x0
000d88:  0e01  movlw   0x01
000d8a:  1218  iorwf   0x18, 0x1, 0x0
000d8c:  b4d8  skpnz
000d8e:  d792  bra     0x000cb4
000d90:  0e00  movlw   0x00
000d92:  539a  movf    0x9a, 0x1, 0x1
000d94:  a4d8  skpz
000d96:  0e01  movlw   0x01
000d98:  6e18  movwf   0x18, 0x0
000d9a:  6ae8  clrw
000d9c:  b81f  btfsc   0x1f, 0x4, 0x0
000d9e:  0e01  movlw   0x01
000da0:  1218  iorwf   0x18, 0x1, 0x0
000da2:  b4d8  skpnz
000da4:  efd8  goto    0x000db0
000da6:  f006
000da8:  6bb3  clrf    0xb3, 0x1
000daa:  6bb2  clrf    0xb2, 0x1
000dac:  6bb1  clrf    0xb1, 0x1
000dae:  6bb0  clrf    0xb0, 0x1
000db0:  981f  bcf     0x1f, 0x4, 0x0
000db2:  319a  rrcf    0x9a, 0x0, 0x1
000db4:  a0d8  skpc
000db6:  efe4  goto    0x000dc8
000db8:  f006
000dba:  96d8  clrov
000dbc:  a19a  btfss   0x9a, 0x0, 0x1
000dbe:  86d8  setov
000dc0:  b6d8  skpnov
000dc2:  efe4  goto    0x000dc8
000dc4:  f006
000dc6:  721f  btg     0x1f, 0x1, 0x0
000dc8:  6b9d  clrf    0x9d, 0x1
000dca:  6b9e  clrf    0x9e, 0x1
000dcc:  0012  return  0x0
000dce:  521b  movf    0x1b, 0x1, 0x0
000dd0:  a4d8  skpz
000dd2:  efef  goto    0x000dde
000dd4:  f006
000dd6:  521c  movf    0x1c, 0x1, 0x0
000dd8:  b4d8  skpnz
000dda:  eff2  goto    0x000de4
000ddc:  f006
000dde:  061b  decf    0x1b, 0x1, 0x0
000de0:  0e00  movlw   0x00
000de2:  5a1c  subwfb  0x1c, 0x1, 0x0
000de4:  a01f  btfss   0x1f, 0x0, 0x0
000de6:  eff6  goto    0x000dec
000de8:  f006
000dea:  0012  return  0x0
000dec:  501e  movf    0x1e, 0x0, 0x0
000dee:  6220  cpfseq  0x20, 0x0
000df0:  efa8  goto    0x000f50
000df2:  f007
000df4:  501d  movf    0x1d, 0x0, 0x0
000df6:  6221  cpfseq  0x21, 0x0
000df8:  ef06  goto    0x000e0c
000dfa:  f007
000dfc:  0e50  movlw   0x50
000dfe:  6e1b  movwf   0x1b, 0x0
000e00:  0ec3  movlw   0xc3
000e02:  6e1c  movwf   0x1c, 0x0
000e04:  721f  btg     0x1f, 0x1, 0x0
000e06:  861f  bsf     0x1f, 0x3, 0x0
000e08:  efa8  goto    0x000f50
000e0a:  f007
000e0c:  501d  movf    0x1d, 0x0, 0x0
000e0e:  6222  cpfseq  0x22, 0x0
000e10:  ef19  goto    0x000e32
000e12:  f007
000e14:  0ed0  movlw   0xd0
000e16:  6e1b  movwf   0x1b, 0x0
000e18:  0e07  movlw   0x07
000e1a:  6e1c  movwf   0x1c, 0x0
000e1c:  0e72  movlw   0x72
000e1e:  61b9  cpfslt  0xb9, 0x1
000e20:  ef17  goto    0x000e2e
000e22:  f007
000e24:  2bb9  incf    0xb9, 0x1, 0x1
000e26:  9a1f  bcf     0x1f, 0x5, 0x0
000e28:  df0b  rcall   0x000c40
000e2a:  861f  bsf     0x1f, 0x3, 0x0
000e2c:  881f  bsf     0x1f, 0x4, 0x0
000e2e:  efa8  goto    0x000f50
000e30:  f007
000e32:  501d  movf    0x1d, 0x0, 0x0
000e34:  6223  cpfseq  0x23, 0x0
000e36:  ef2c  goto    0x000e58
000e38:  f007
000e3a:  0ed0  movlw   0xd0
000e3c:  6e1b  movwf   0x1b, 0x0
000e3e:  0e07  movlw   0x07
000e40:  6e1c  movwf   0x1c, 0x0
000e42:  53b9  movf    0xb9, 0x1, 0x1
000e44:  b4d8  skpnz
000e46:  ef2a  goto    0x000e54
000e48:  f007
000e4a:  07b9  decf    0xb9, 0x1, 0x1
000e4c:  9a1f  bcf     0x1f, 0x5, 0x0
000e4e:  def8  rcall   0x000c40
000e50:  861f  bsf     0x1f, 0x3, 0x0
000e52:  881f  bsf     0x1f, 0x4, 0x0
000e54:  efa8  goto    0x000f50
000e56:  f007
000e58:  501d  movf    0x1d, 0x0, 0x0
000e5a:  6226  cpfseq  0x26, 0x0
000e5c:  ef3e  goto    0x000e7c
000e5e:  f007
000e60:  0e2f  movlw   0x2f
000e62:  6fb4  movwf   0xb4, 0x1
000e64:  0e75  movlw   0x75
000e66:  6fb5  movwf   0xb5, 0x1
000e68:  7a1f  btg     0x1f, 0x5, 0x0
000e6a:  0e20  movlw   0x20
000e6c:  6e1b  movwf   0x1b, 0x0
000e6e:  0e4e  movlw   0x4e
000e70:  6e1c  movwf   0x1c, 0x0
000e72:  861f  bsf     0x1f, 0x3, 0x0
000e74:  881f  bsf     0x1f, 0x4, 0x0
000e76:  df02  rcall   0x000c7c
000e78:  efa8  goto    0x000f50
000e7a:  f007
000e7c:  501d  movf    0x1d, 0x0, 0x0
000e7e:  6225  cpfseq  0x25, 0x0
000e80:  ef73  goto    0x000ee6
000e82:  f007
000e84:  53a1  movf    0xa1, 0x1, 0x1
000e86:  a4d8  skpz
000e88:  ef4a  goto    0x000e94
000e8a:  f007
000e8c:  0e05  movlw   0x05
000e8e:  6e27  movwf   0x27, 0x0
000e90:  ef5f  goto    0x000ebe
000e92:  f007
000e94:  2da1  decfsz  0xa1, 0x0, 0x1
000e96:  ef51  goto    0x000ea2
000e98:  f007
000e9a:  0e06  movlw   0x06
000e9c:  6e27  movwf   0x27, 0x0
000e9e:  ef5f  goto    0x000ebe
000ea0:  f007
000ea2:  0e02  movlw   0x02
000ea4:  63a1  cpfseq  0xa1, 0x1
000ea6:  ef59  goto    0x000eb2
000ea8:  f007
000eaa:  0e07  movlw   0x07
000eac:  6e27  movwf   0x27, 0x0
000eae:  ef5f  goto    0x000ebe
000eb0:  f007
000eb2:  0e03  movlw   0x03
000eb4:  63a1  cpfseq  0xa1, 0x1
000eb6:  ef5f  goto    0x000ebe
000eb8:  f007
000eba:  0e08  movlw   0x08
000ebc:  6e27  movwf   0x27, 0x0
000ebe:  53b7  movf    0xb7, 0x1, 0x1
000ec0:  b4d8  skpnz
000ec2:  ef66  goto    0x000ecc
000ec4:  f007
000ec6:  07b7  decf    0xb7, 0x1, 0x1
000ec8:  ef68  goto    0x000ed0
000eca:  f007
000ecc:  c027  movff   0x027, 0x0b7
000ece:  f0b7
000ed0:  861f  bsf     0x1f, 0x3, 0x0
000ed2:  881f  bsf     0x1f, 0x4, 0x0
000ed4:  0e58  movlw   0x58
000ed6:  6e1b  movwf   0x1b, 0x0
000ed8:  0e1b  movlw   0x1b
000eda:  6e1c  movwf   0x1c, 0x0
000edc:  ecb5  call    0x00076a, 0x0
000ede:  f003
000ee0:  dea0  rcall   0x000c22
000ee2:  efa8  goto    0x000f50
000ee4:  f007
000ee6:  501d  movf    0x1d, 0x0, 0x0
000ee8:  6224  cpfseq  0x24, 0x0
000eea:  efa7  goto    0x000f4e
000eec:  f007
000eee:  53a1  movf    0xa1, 0x1, 0x1
000ef0:  a4d8  skpz
000ef2:  ef7f  goto    0x000efe
000ef4:  f007
000ef6:  0e05  movlw   0x05
000ef8:  6e27  movwf   0x27, 0x0
000efa:  ef94  goto    0x000f28
000efc:  f007
000efe:  2da1  decfsz  0xa1, 0x0, 0x1
000f00:  ef86  goto    0x000f0c
000f02:  f007
000f04:  0e06  movlw   0x06
000f06:  6e27  movwf   0x27, 0x0
000f08:  ef94  goto    0x000f28
000f0a:  f007
000f0c:  0e02  movlw   0x02
000f0e:  63a1  cpfseq  0xa1, 0x1
000f10:  ef8e  goto    0x000f1c
000f12:  f007
000f14:  0e07  movlw   0x07
000f16:  6e27  movwf   0x27, 0x0
000f18:  ef94  goto    0x000f28
000f1a:  f007
000f1c:  0e03  movlw   0x03
000f1e:  63a1  cpfseq  0xa1, 0x1
000f20:  ef94  goto    0x000f28
000f22:  f007
000f24:  0e08  movlw   0x08
000f26:  6e27  movwf   0x27, 0x0
000f28:  5027  movf    0x27, 0x0, 0x0
000f2a:  61b7  cpfslt  0xb7, 0x1
000f2c:  ef9b  goto    0x000f36
000f2e:  f007
000f30:  2bb7  incf    0xb7, 0x1, 0x1
000f32:  ef9c  goto    0x000f38
000f34:  f007
000f36:  6bb7  clrf    0xb7, 0x1
000f38:  861f  bsf     0x1f, 0x3, 0x0
000f3a:  881f  bsf     0x1f, 0x4, 0x0
000f3c:  0e58  movlw   0x58
000f3e:  6e1b  movwf   0x1b, 0x0
000f40:  0e1b  movlw   0x1b
000f42:  6e1c  movwf   0x1c, 0x0
000f44:  ecb5  call    0x00076a, 0x0
000f46:  f003
000f48:  de6c  rcall   0x000c22
000f4a:  efa8  goto    0x000f50
000f4c:  f007
000f4e:  801f  bsf     0x1f, 0x0, 0x0
000f50:  801f  bsf     0x1f, 0x0, 0x0
000f52:  0012  return  0x0
000f54:  0e04  movlw   0x04
000f56:  63a7  cpfseq  0xa7, 0x1
000f58:  efbe  goto    0x000f7c
000f5a:  f007
000f5c:  0e10  movlw   0x10
000f5e:  6e20  movwf   0x20, 0x0
000f60:  0e32  movlw   0x32
000f62:  6e21  movwf   0x21, 0x0
000f64:  0e33  movlw   0x33
000f66:  6e22  movwf   0x22, 0x0
000f68:  0e34  movlw   0x34
000f6a:  6e23  movwf   0x23, 0x0
000f6c:  0e35  movlw   0x35
000f6e:  6e26  movwf   0x26, 0x0
000f70:  0e36  movlw   0x36
000f72:  6e24  movwf   0x24, 0x0
000f74:  0e37  movlw   0x37
000f76:  6e25  movwf   0x25, 0x0
000f78:  efcf  goto    0x000f9e
000f7a:  f007
000f7c:  0e03  movlw   0x03
000f7e:  63a7  cpfseq  0xa7, 0x1
000f80:  efcf  goto    0x000f9e
000f82:  f007
000f84:  6a20  clrf    0x20, 0x0
000f86:  0e0c  movlw   0x0c
000f88:  6e21  movwf   0x21, 0x0
000f8a:  0e10  movlw   0x10
000f8c:  6e22  movwf   0x22, 0x0
000f8e:  0e11  movlw   0x11
000f90:  6e23  movwf   0x23, 0x0
000f92:  0e20  movlw   0x20
000f94:  6e24  movwf   0x24, 0x0
000f96:  0e21  movlw   0x21
000f98:  6e25  movwf   0x25, 0x0
000f9a:  0e0d  movlw   0x0d
000f9c:  6e26  movwf   0x26, 0x0
000f9e:  0012  return  0x0
000fa0:  c0a2  movff   0x0a2, 0x029
000fa2:  f029
000fa4:  c0a3  movff   0x0a3, 0x02a
000fa6:  f02a
000fa8:  c0a5  movff   0x0a5, 0x027
000faa:  f027
000fac:  0e80  movlw   0x80
000fae:  6e01  movwf   0x01, 0x0
000fb0:  0ec0  movlw   0xc0
000fb2:  ec33  call    0x000066, 0x0
000fb4:  f000
000fb6:  eca0  call    0x000940, 0x0
000fb8:  f004
000fba:  de7b  rcall   0x000cb2
000fbc:  0e00  movlw   0x00
000fbe:  539a  movf    0x9a, 0x1, 0x1
000fc0:  a4d8  skpz
000fc2:  0e01  movlw   0x01
000fc4:  6e18  movwf   0x18, 0x0
000fc6:  6ae8  clrw
000fc8:  b61f  btfsc   0x1f, 0x3, 0x0
000fca:  0e01  movlw   0x01
000fcc:  1218  iorwf   0x18, 0x1, 0x0
000fce:  b4d8  skpnz
000fd0:  d7f4  bra     0x000fba
000fd2:  319a  rrcf    0x9a, 0x0, 0x1
000fd4:  32e8  rrcf    0xe8, 0x1, 0x0
000fd6:  a0d8  skpc
000fd8:  eff6  goto    0x000fec
000fda:  f007
000fdc:  51a5  movf    0xa5, 0x0, 0x1
000fde:  63a4  cpfseq  0xa4, 0x1
000fe0:  eff5  goto    0x000fea
000fe2:  f007
000fe4:  6ba5  clrf    0xa5, 0x1
000fe6:  eff6  goto    0x000fec
000fe8:  f007
000fea:  2ba5  incf    0xa5, 0x1, 0x1
000fec:  96d8  clrov
000fee:  a59a  btfss   0x9a, 0x2, 0x1
000ff0:  86d8  setov
000ff2:  b6d8  skpnov
000ff4:  ef05  goto    0x00100a
000ff6:  f008
000ff8:  53a5  movf    0xa5, 0x1, 0x1
000ffa:  a4d8  skpz
000ffc:  ef04  goto    0x001008
000ffe:  f008
001000:  c0a4  movff   0x0a4, 0x0a5
001002:  f0a5
001004:  ef05  goto    0x00100a
001006:  f008
001008:  07a5  decf    0xa5, 0x1, 0x1
00100a:  0012  return  0x0
00100c:  6f56  movwf   0x56, 0x1
00100e:  756c  btg     0x6c, 0x2, 0x1
001010:  656d  cpfsgt  0x6d, 0x1
001012:  203a  addwfc  0x3a, 0x0, 0x0
001014:  2020  addwfc  0x20, 0x0, 0x0
001016:  2020  addwfc  0x20, 0x0, 0x0
001018:  2020  addwfc  0x20, 0x0, 0x0
00101a:  2020  addwfc  0x20, 0x0, 0x0
00101c:  6e49  movwf   0x49, 0x0
00101e:  7570  btg     0x70, 0x2, 0x1
001020:  3a74  swapf   0x74, 0x1, 0x0
001022:  2020  addwfc  0x20, 0x0, 0x0
001024:  2020  addwfc  0x20, 0x0, 0x0
001026:  2020  addwfc  0x20, 0x0, 0x0
001028:  2020  addwfc  0x20, 0x0, 0x0
00102a:  2020  addwfc  0x20, 0x0, 0x0
00102c:  6553  cpfsgt  0x53, 0x1
00102e:  7574  btg     0x74, 0x2, 0x1
001030:  2070  addwfc  0x70, 0x0, 0x0
001032:  2020  addwfc  0x20, 0x0, 0x0
001034:  2020  addwfc  0x20, 0x0, 0x0
001036:  2020  addwfc  0x20, 0x0, 0x0
001038:  2020  addwfc  0x20, 0x0, 0x0
00103a:  2020  addwfc  0x20, 0x0, 0x0
00103c:  9294  bcf     0x94, 0x1, 0x0
00103e:  928b  bcf     0x8b, 0x1, 0x0
001040:  0e0a  movlw   0x0a
001042:  6e1b  movwf   0x1b, 0x0
001044:  6a1c  clrf    0x1c, 0x0
001046:  8a7d  bsf     0x7d, 0x5, 0x0
001048:  90f2  bcf     0xf2, 0x0, 0x0
00104a:  96f2  bcf     0xf2, 0x3, 0x0
00104c:  8a9d  bsf     0x9d, 0x5, 0x0
00104e:  8ef2  bsf     0xf2, 0x7, 0x0
001050:  8cf2  bsf     0xf2, 0x6, 0x0
001052:  6b96  clrf    0x96, 0x1
001054:  6b97  clrf    0x97, 0x1
001056:  6b98  clrf    0x98, 0x1
001058:  6b99  clrf    0x99, 0x1
00105a:  941f  bcf     0x1f, 0x2, 0x0
00105c:  6ba6  clrf    0xa6, 0x1
00105e:  6a1d  clrf    0x1d, 0x0
001060:  6a1d  clrf    0x1d, 0x0
001062:  6a1e  clrf    0x1e, 0x0
001064:  6b9b  clrf    0x9b, 0x1
001066:  6b9c  clrf    0x9c, 0x1
001068:  ee00  lfsr    0x0, 0x0c1
00106a:  f0c1
00106c:  0e06  movlw   0x06
00106e:  6aee  clrf    0xee, 0x0
001070:  2ee8  decfsz  0xe8, 0x1, 0x0
001072:  d7fd  bra     0x00106e
001074:  ee00  lfsr    0x0, 0x0c7
001076:  f0c7
001078:  0e06  movlw   0x06
00107a:  6aee  clrf    0xee, 0x0
00107c:  2ee8  decfsz  0xe8, 0x1, 0x0
00107e:  d7fd  bra     0x00107a
001080:  ee00  lfsr    0x0, 0x0cd
001082:  f0cd
001084:  0e06  movlw   0x06
001086:  6aee  clrf    0xee, 0x0
001088:  2ee8  decfsz  0xe8, 0x1, 0x0
00108a:  d7fd  bra     0x001086
00108c:  ee00  lfsr    0x0, 0x0d3
00108e:  f0d3
001090:  0e06  movlw   0x06
001092:  6aee  clrf    0xee, 0x0
001094:  2ee8  decfsz  0xe8, 0x1, 0x0
001096:  d7fd  bra     0x001092
001098:  ee00  lfsr    0x0, 0x0d9
00109a:  f0d9
00109c:  0e06  movlw   0x06
00109e:  6aee  clrf    0xee, 0x0
0010a0:  2ee8  decfsz  0xe8, 0x1, 0x0
0010a2:  d7fd  bra     0x00109e
0010a4:  ee00  lfsr    0x0, 0x0df
0010a6:  f0df
0010a8:  0e06  movlw   0x06
0010aa:  6aee  clrf    0xee, 0x0
0010ac:  2ee8  decfsz  0xe8, 0x1, 0x0
0010ae:  d7fd  bra     0x0010aa
0010b0:  6a32  clrf    0x32, 0x0
0010b2:  961f  bcf     0x1f, 0x3, 0x0
0010b4:  981f  bcf     0x1f, 0x4, 0x0
0010b6:  68a9  setf    0xa9, 0x0
0010b8:  0e02  movlw   0x02
0010ba:  ecd1  call    0x0001a2, 0x0
0010bc:  f000
0010be:  0e70  movlw   0x70
0010c0:  eccb  call    0x000196, 0x0
0010c2:  f000
0010c4:  6e27  movwf   0x27, 0x0
0010c6:  0e01  movlw   0x01
0010c8:  5c27  subwf   0x27, 0x0, 0x0
0010ca:  b4d8  skpnz
0010cc:  ef6d  goto    0x0010da
0010ce:  f008
0010d0:  0e70  movlw   0x70
0010d2:  6ea9  movwf   0xa9, 0x0
0010d4:  0e01  movlw   0x01
0010d6:  ecd1  call    0x0001a2, 0x0
0010d8:  f000
0010da:  0e71  movlw   0x71
0010dc:  eccb  call    0x000196, 0x0
0010de:  f000
0010e0:  6e27  movwf   0x27, 0x0
0010e2:  0e06  movlw   0x06
0010e4:  5c27  subwf   0x27, 0x0, 0x0
0010e6:  b4d8  skpnz
0010e8:  ef7b  goto    0x0010f6
0010ea:  f008
0010ec:  0e71  movlw   0x71
0010ee:  6ea9  movwf   0xa9, 0x0
0010f0:  0e06  movlw   0x06
0010f2:  ecd1  call    0x0001a2, 0x0
0010f4:  f000
0010f6:  6bbc  clrf    0xbc, 0x1
0010f8:  6bbe  clrf    0xbe, 0x1
0010fa:  6bbd  clrf    0xbd, 0x1
0010fc:  6bb4  clrf    0xb4, 0x1
0010fe:  6bb5  clrf    0xb5, 0x1
001100:  6bb3  clrf    0xb3, 0x1
001102:  6bb2  clrf    0xb2, 0x1
001104:  6bb1  clrf    0xb1, 0x1
001106:  6bb0  clrf    0xb0, 0x1
001108:  0e01  movlw   0x01
00110a:  6e0f  movwf   0x0f, 0x0
00110c:  0e2c  movlw   0x2c
00110e:  ecdf  call    0x0001be, 0x0
001110:  f000
001112:  ec26  call    0x00004c, 0x0
001114:  f000
001116:  0ec8  movlw   0xc8
001118:  ecde  call    0x0001bc, 0x0
00111a:  f000
00111c:  ec23  call    0x000a46, 0x0
00111e:  f005
001120:  0e01  movlw   0x01
001122:  6e0f  movwf   0x0f, 0x0
001124:  0ef4  movlw   0xf4
001126:  ecdf  call    0x0001be, 0x0
001128:  f000
00112a:  0e80  movlw   0x80
00112c:  6e01  movwf   0x01, 0x0
00112e:  ec33  call    0x000066, 0x0
001130:  f000
001132:  0e03  movlw   0x03
001134:  6ef7  movwf   0xf7, 0x0
001136:  0e04  movlw   0x04
001138:  6ef6  movwf   0xf6, 0x0
00113a:  ec6e  call    0x0000dc, 0x0
00113c:  f000
00113e:  0e80  movlw   0x80
001140:  6e01  movwf   0x01, 0x0
001142:  0e01  movlw   0x01
001144:  ec3c  call    0x000078, 0x0
001146:  f000
001148:  0e2e  movlw   0x2e
00114a:  ec76  call    0x0000ec, 0x0
00114c:  f000
00114e:  0e80  movlw   0x80
001150:  6e01  movwf   0x01, 0x0
001152:  0e06  movlw   0x06
001154:  ec3c  call    0x000078, 0x0
001156:  f000
001158:  0e03  movlw   0x03
00115a:  6e0f  movwf   0x0f, 0x0
00115c:  0ee8  movlw   0xe8
00115e:  ecdf  call    0x0001be, 0x0
001160:  f000
001162:  0e80  movlw   0x80
001164:  6fb8  movwf   0xb8, 0x1
001166:  6fb9  movwf   0xb9, 0x1
001168:  6fa7  movwf   0xa7, 0x1
00116a:  6fa1  movwf   0xa1, 0x1
00116c:  6e01  movwf   0x01, 0x0
00116e:  ec33  call    0x000066, 0x0
001170:  f000
001172:  0e03  movlw   0x03
001174:  6ef7  movwf   0xf7, 0x0
001176:  0e10  movlw   0x10
001178:  6ef6  movwf   0xf6, 0x0
00117a:  ec6e  call    0x0000dc, 0x0
00117c:  f000
00117e:  9294  bcf     0x94, 0x1, 0x0
001180:  828b  bsf     0x8b, 0x1, 0x0
001182:  0e0f  movlw   0x0f
001184:  6e0f  movwf   0x0f, 0x0
001186:  0ea0  movlw   0xa0
001188:  ecdf  call    0x0001be, 0x0
00118a:  f000
00118c:  ecb2  call    0x000b64, 0x0
00118e:  f005
001190:  0ec8  movlw   0xc8
001192:  ecde  call    0x0001bc, 0x0
001194:  f000
001196:  ec25  call    0x00044a, 0x0
001198:  f002
00119a:  0e80  movlw   0x80
00119c:  5db8  subwf   0xb8, 0x0, 0x1
00119e:  a4d8  skpz
0011a0:  0e01  movlw   0x01
0011a2:  6e18  movwf   0x18, 0x0
0011a4:  0e80  movlw   0x80
0011a6:  5db9  subwf   0xb9, 0x0, 0x1
0011a8:  a4d8  skpz
0011aa:  0e01  movlw   0x01
0011ac:  1618  andwf   0x18, 0x1, 0x0
0011ae:  0e80  movlw   0x80
0011b0:  5da7  subwf   0xa7, 0x0, 0x1
0011b2:  a4d8  skpz
0011b4:  0e01  movlw   0x01
0011b6:  1618  andwf   0x18, 0x1, 0x0
0011b8:  0e80  movlw   0x80
0011ba:  5da1  subwf   0xa1, 0x0, 0x1
0011bc:  a4d8  skpz
0011be:  0e01  movlw   0x01
0011c0:  1618  andwf   0x18, 0x1, 0x0
0011c2:  b4d8  skpnz
0011c4:  d7e3  bra     0x00118c
0011c6:  0e61  movlw   0x61
0011c8:  6f9d  movwf   0x9d, 0x1
0011ca:  0eea  movlw   0xea
0011cc:  6f9e  movwf   0x9e, 0x1
0011ce:  6b9f  clrf    0x9f, 0x1
0011d0:  6ba0  clrf    0xa0, 0x1
0011d2:  9a1f  bcf     0x1f, 0x5, 0x0
; ===========================================================================
; label_201 @ 0x0011D8 — post_connect_init
; ---------------------------------------------------------------------------
; Reached after boot_handshake_wait completes (all four sentinels !=
; 0x80). Clears 0x01F.bit3 (event_exit) so the main event loop can return,
; reads display_state_index (0x0BF) to decide which screen to render
; (0=Volume, 1=Preset[V1.62b+], 2=Input, 3=Setup), and writes a marker
; byte to EEPROM (~0x44 in code path) indicating connected state.
; ---------------------------------------------------------------------------
0011d4:  0e01  movlw   0x01
0011d6:  6e32  movwf   0x32, 0x0
0011d8:  a21f  btfss   0x1f, 0x1, 0x0       ; 0x1F.bit1 = connected?
0011da:  ef28  goto    0x001250             ;  no -> jump out (back to standby/wait)
0011dc:  f009
0011de:  961f  bcf     0x1f, 0x3, 0x0       ; 0x1F.bit3 (event_exit) = 0
0011e0:  53bf  movf    0xbf, 0x1, 0x1       ; W = display_state_index
0011e2:  a4d8  skpz
0011e4:  eff8  goto    0x0011f0
0011e6:  f008
0011e8:  ec68  call    0x0012d0, 0x0        ; display_state == 0 -> volume screen
0011ea:  f009
0011ec:  ef05  goto    0x00120a
0011ee:  f009
0011f0:  2dbf  decfsz  0xbf, 0x0, 0x1       ; display_state -- == 0 ? (state==1)
0011f2:  efff  goto    0x0011fe
0011f4:  f008
0011f6:  ec89  call    0x001912, 0x0        ; display_state == 1 -> setup/preset screen
0011f8:  f00c
0011fa:  ef05  goto    0x00120a
0011fc:  f009

; ===========================================================================
; label_204 @ 0x0011FE — boot_handshake_wait    *** BUG C1 ***
; ---------------------------------------------------------------------------
; Polls four handshake sentinels (0x0B8, 0x0B9, 0x0A7, 0x0A1) until each
; differs from 0x80 — the value MAIN's full status burst eventually
; overwrites with real channel volume / config bytes. Calls 0x0013FE on
; each iteration which kicks the periodic poll/refresh.
;
; *** BUG C1 (boot_handshake_infinite_wait) ***
; If MAIN never responds (chain broken, MAIN unflashed, MAIN stuck in
; firmware-update bootloader, etc.) this loop runs forever. The LCD shows
; "Waiting for DLCP" indefinitely; the only escape is power cycle.
; CONTROL has no WDT (BUG C8), so the loop is unrecoverable. The V1.62b
; "reconnect_wait_stub" patch at 0x7000+ replaces the analogous reconnect
; loop (label_212/216) with a soft-recover + bounded retry pattern, but
; the BOOT handshake here was NOT touched by V1.62b.
; ===========================================================================
0011fe:  0e02  movlw   0x02
001200:  63bf  cpfseq  0xbf, 0x1            ; display_state_index == 2 ?
001202:  ef05  goto    0x00120a             ;  no -> skip handshake check
001204:  f009
001206:  ecff  call    0x0013fe, 0x0        ; *** C1: poll/refresh, no timeout ***
001208:  f009
00120a:  96d8  clrov
00120c:  ab9a  btfss   0x9a, 0x5, 0x1
00120e:  86d8  setov
001210:  b6d8  skpnov
001212:  ef13  goto    0x001226
001214:  f009
001216:  0e02  movlw   0x02
001218:  63bf  cpfseq  0xbf, 0x1
00121a:  ef12  goto    0x001224
00121c:  f009
00121e:  6bbf  clrf    0xbf, 0x1
001220:  ef13  goto    0x001226
001222:  f009

; ===========================================================================
; label_206 @ 0x001224 — display_state_entry
; ---------------------------------------------------------------------------
; Increments 0x0BF (display_state_index) — cycles the menu screen on each
; re-entry. Display state values:
;   0 = Volume     1 = Preset (V1.62b/V1.61b only — preset A/B selector)
;   2 = Input      3 = Setup
; Stock V1.6b only uses 0/2/3; V1.61b+ patch enables preset state via
; 0x01F.bit6 (preset_b_active). The clrov / btfss 0x9A.bit4 sequence
; below is the V1.6b mode-disable check that skips the Preset slot
; (it's always odd -> overflow check after increment).
; ===========================================================================
001224:  2bbf  incf    0xbf, 0x1, 0x1       ; display_state_index++
001226:  96d8  clrov
001228:  a99a  btfss   0x9a, 0x4, 0x1
00122a:  86d8  setov
00122c:  b6d8  skpnov
00122e:  ef22  goto    0x001244
001230:  f009
001232:  53bf  movf    0xbf, 0x1, 0x1
001234:  a4d8  skpz
001236:  ef21  goto    0x001242
001238:  f009
00123a:  0e02  movlw   0x02
00123c:  6fbf  movwf   0xbf, 0x1
00123e:  ef22  goto    0x001244
001240:  f009
001242:  07bf  decf    0xbf, 0x1, 0x1
001244:  ec56  call    0x0008ac, 0x0
001246:  f004
001248:  b21f  btfsc   0x1f, 0x1, 0x0
00124a:  d7c9  bra     0x0011de
00124c:  ef67  goto    0x0012ce
00124e:  f009
001250:  921f  bcf     0x1f, 0x1, 0x0
001252:  ec4c  call    0x000c98, 0x0
001254:  f006
001256:  ec26  call    0x00004c, 0x0
001258:  f000
00125a:  0e80  movlw   0x80
00125c:  6e01  movwf   0x01, 0x0
00125e:  ec33  call    0x000066, 0x0
001260:  f000
001262:  0e03  movlw   0x03
001264:  6ef7  movwf   0xf7, 0x0
001266:  0e22  movlw   0x22
001268:  6ef6  movwf   0xf6, 0x0
00126a:  ec6e  call    0x0000dc, 0x0
00126c:  f000
00126e:  ec59  call    0x000cb2, 0x0
001270:  f006
001272:  961f  bcf     0x1f, 0x3, 0x0
001274:  0e00  movlw   0x00
001276:  539a  movf    0x9a, 0x1, 0x1
001278:  a4d8  skpz
00127a:  0e01  movlw   0x01
00127c:  6e18  movwf   0x18, 0x0
00127e:  6ae8  clrw
001280:  b21f  btfsc   0x1f, 0x1, 0x0
001282:  0e01  movlw   0x01
001284:  1218  iorwf   0x18, 0x1, 0x0
001286:  b4d8  skpnz
001288:  d7f2  bra     0x00126e
00128a:  6bb3  clrf    0xb3, 0x1
00128c:  6bb2  clrf    0xb2, 0x1
00128e:  6bb1  clrf    0xb1, 0x1
001290:  6bb0  clrf    0xb0, 0x1
001292:  821f  bsf     0x1f, 0x1, 0x0
001294:  ec4c  call    0x000c98, 0x0
001296:  f006
001298:  0e80  movlw   0x80
00129a:  6e01  movwf   0x01, 0x0
00129c:  ec33  call    0x000066, 0x0
00129e:  f000
0012a0:  0e03  movlw   0x03
0012a2:  6ef7  movwf   0xf7, 0x0
0012a4:  0e34  movlw   0x34
0012a6:  6ef6  movwf   0xf6, 0x0
0012a8:  ec6e  call    0x0000dc, 0x0
0012aa:  f000
0012ac:  9294  bcf     0x94, 0x1, 0x0
0012ae:  828b  bsf     0x8b, 0x1, 0x0
0012b0:  0e13  movlw   0x13
0012b2:  6e0f  movwf   0x0f, 0x0
0012b4:  0e88  movlw   0x88
0012b6:  ecdf  call    0x0001be, 0x0
0012b8:  f000
; ===========================================================================
; label_212 @ 0x0012BC — reconnect_wait_loop    *** BUG C2 ***
; ---------------------------------------------------------------------------
; Reconnect/Zzz... → DISPLAY transition. Drops 0x01F.bit1 (connected),
; then loops:
;   1. function_029 (poll_frame_send @ 0x000B64): emits [B1, 04, 00] on UART
;   2. delay 200 ms (function_012 with W=0xC8)
;   3. function_019 (rx_parser_entry @ 0x00044A): drains RX
;   4. test 0x01F.bit1 — if set, MAIN replied -> jump to label_201
;
; *** BUG C2 (reconnect_infinite_wait) ***
; If MAIN never returns the BF/03/01 frame that sets bit1, this loop
; spins forever. The LCD shows "Waiting for DLCP". CONTROL never sends a
; wake frame to MAIN if MAIN's active gate has been cleared by an earlier
; broadcast standby — so this poll is silent on the wire from MAIN's
; perspective. The V1.62b patch replaces this exact loop with
; reconnect_wait_stub at 0x7000+ which:
;   • bounds the wait to 8 retries before soft-recovering
;   • emits the wake frame (function_034) explicitly on exit (this fixes
;     the V162B_RECONNECT_WAKE_BUG — without that wake call, MAIN's
;     active_flags.bit3 stays cleared and every command is silently
;     dropped at MAIN's cmd_dispatch_gated label_144).
; ===========================================================================
0012ba:  921f  bcf     0x1f, 0x1, 0x0       ; clear connected (entering reconnect mode)
0012bc:  ecb2  call    0x000b64, 0x0        ; function_029 — emit poll [B1,04,00]
0012be:  f005
0012c0:  0ec8  movlw   0xc8                  ; W = 200 (200 ms unit)
0012c2:  ecde  call    0x0001bc, 0x0        ; function_012 — short delay
0012c4:  f000
0012c6:  ec25  call    0x00044a, 0x0        ; function_019 — drain RX (parse reply)
0012c8:  f002
0012ca:  a21f  btfss   0x1f, 0x1, 0x0       ; connected flag now set?
0012cc:  d7f7  bra     0x0012bc             ; *** BUG C2: spin forever otherwise ***
0012ce:  d784  bra     0x0011d8             ; reconnected -> goto label_201
0012d0:  0e80  movlw   0x80
0012d2:  6e01  movwf   0x01, 0x0
0012d4:  ec33  call    0x000066, 0x0
0012d6:  f000
0012d8:  c0bf  movff   0x0bf, 0x027
0012da:  f027
0012dc:  0e10  movlw   0x10
0012de:  6e2a  movwf   0x2a, 0x0
0012e0:  0e0c  movlw   0x0c
0012e2:  6e29  movwf   0x29, 0x0
0012e4:  eca0  call    0x000940, 0x0
0012e6:  f004

; ===========================================================================
; label_214 @ 0x0012E8 — standby_display ("Zzz...")
; ---------------------------------------------------------------------------
; Renders the standby screen on the LCD: "Zzz..." centered, backlight on.
; Sets 0x01.bit7 (LCD-mode flag for function_009 dispatch), then sends
; LCD command 0x87 (set DDRAM address) followed by the "Zzz..." string
; via function_004 / function_005. The screen stays here until a button
; press triggers the wake transition, which goes through
; reconnect_wait_loop (label_212, 0x0012BC, BUG C2).
; ===========================================================================
0012e8:  0e80  movlw   0x80
0012ea:  6e01  movwf   0x01, 0x0            ; LCD-mode flag = 1
0012ec:  0e87  movlw   0x87                  ; LCD cmd: DDRAM address 0x07 (mid line)
0012ee:  ec33  call    0x000066, 0x0        ; function_001 — lcd_command
0012f0:  f000
0012f2:  ba1f  btfsc   0x1f, 0x5, 0x0
0012f4:  efaa  goto    0x001354
0012f6:  f009
0012f8:  0e60  movlw   0x60
0012fa:  61b9  cpfslt  0xb9, 0x1
0012fc:  ef88  goto    0x001310
0012fe:  f009
001300:  0e2d  movlw   0x2d
001302:  ec76  call    0x0000ec, 0x0
001304:  f000
001306:  51b9  movf    0xb9, 0x0, 0x1
001308:  0860  sublw   0x60
00130a:  6e27  movwf   0x27, 0x0
00130c:  ef97  goto    0x00132e
00130e:  f009
001310:  0e60  movlw   0x60
001312:  63b9  cpfseq  0xb9, 0x1
001314:  ef91  goto    0x001322
001316:  f009
001318:  0e60  movlw   0x60
00131a:  5db9  subwf   0xb9, 0x0, 0x1
00131c:  6e27  movwf   0x27, 0x0
00131e:  ef97  goto    0x00132e
001320:  f009
001322:  0e2b  movlw   0x2b
001324:  ec76  call    0x0000ec, 0x0
001326:  f000
001328:  0e60  movlw   0x60
00132a:  5db9  subwf   0xb9, 0x0, 0x1
00132c:  6e27  movwf   0x27, 0x0
00132e:  0e80  movlw   0x80
001330:  6e01  movwf   0x01, 0x0
001332:  5027  movf    0x27, 0x0, 0x0
001334:  ec3c  call    0x000078, 0x0
001336:  f000
001338:  0e2e  movlw   0x2e
00133a:  ec76  call    0x0000ec, 0x0
00133c:  f000
00133e:  0e30  movlw   0x30
001340:  ec76  call    0x0000ec, 0x0
001342:  f000
001344:  0e03  movlw   0x03
001346:  6ef7  movwf   0xf7, 0x0
001348:  0e46  movlw   0x46
00134a:  6ef6  movwf   0xf6, 0x0
00134c:  ec6e  call    0x0000dc, 0x0
00134e:  f000
001350:  efb0  goto    0x001360
001352:  f009
001354:  0e03  movlw   0x03
001356:  6ef7  movwf   0xf7, 0x0
001358:  0e54  movlw   0x54
00135a:  6ef6  movwf   0xf6, 0x0
00135c:  ec6e  call    0x0000dc, 0x0
00135e:  f000
001360:  c0b7  movff   0x0b7, 0x027
001362:  f027
001364:  0e18  movlw   0x18
001366:  6e2a  movwf   0x2a, 0x0
001368:  0e82  movlw   0x82
00136a:  6e29  movwf   0x29, 0x0
00136c:  0e80  movlw   0x80
00136e:  6e01  movwf   0x01, 0x0
001370:  0ec0  movlw   0xc0
001372:  ec33  call    0x000066, 0x0
001374:  f000
001376:  eca0  call    0x000940, 0x0
001378:  f004
00137a:  ec59  call    0x000cb2, 0x0
00137c:  f006
00137e:  319a  rrcf    0x9a, 0x0, 0x1
001380:  32e8  rrcf    0xe8, 0x1, 0x0
001382:  a0d8  skpc
001384:  efcc  goto    0x001398
001386:  f009
001388:  0e72  movlw   0x72
00138a:  61b9  cpfslt  0xb9, 0x1
00138c:  efc9  goto    0x001392
00138e:  f009
001390:  2bb9  incf    0xb9, 0x1, 0x1
001392:  9a1f  bcf     0x1f, 0x5, 0x0
001394:  ec20  call    0x000c40, 0x0
001396:  f006
001398:  96d8  clrov
00139a:  a59a  btfss   0x9a, 0x2, 0x1
00139c:  86d8  setov
00139e:  b6d8  skpnov
0013a0:  efda  goto    0x0013b4
0013a2:  f009
0013a4:  53b9  movf    0xb9, 0x1, 0x1
0013a6:  b4d8  skpnz
0013a8:  efd7  goto    0x0013ae
0013aa:  f009
0013ac:  07b9  decf    0xb9, 0x1, 0x1
0013ae:  9a1f  bcf     0x1f, 0x5, 0x0
0013b0:  ec20  call    0x000c40, 0x0
0013b2:  f006
0013b4:  96d8  clrov
0013b6:  a79a  btfss   0x9a, 0x3, 0x1
0013b8:  86d8  setov
0013ba:  b6d8  skpnov
0013bc:  efe7  goto    0x0013ce
0013be:  f009
0013c0:  7a1f  btg     0x1f, 0x5, 0x0
0013c2:  0e2f  movlw   0x2f
0013c4:  6fb4  movwf   0xb4, 0x1
0013c6:  0e75  movlw   0x75
0013c8:  6fb5  movwf   0xb5, 0x1
0013ca:  ec3e  call    0x000c7c, 0x0
0013cc:  f006
0013ce:  961f  bcf     0x1f, 0x3, 0x0
0013d0:  6ae8  clrw
0013d2:  bb9a  btfsc   0x9a, 0x5, 0x1
0013d4:  0e01  movlw   0x01
0013d6:  6e18  movwf   0x18, 0x0
0013d8:  6ae8  clrw
0013da:  b99a  btfsc   0x9a, 0x4, 0x1
0013dc:  0e01  movlw   0x01
0013de:  1218  iorwf   0x18, 0x1, 0x0
0013e0:  0e01  movlw   0x01
0013e2:  b21f  btfsc   0x1f, 0x1, 0x0
0013e4:  6ae8  clrw
0013e6:  1218  iorwf   0x18, 0x1, 0x0
0013e8:  b4d8  skpnz
0013ea:  d77e  bra     0x0012e8
0013ec:  0012  return  0x0
0013ee:  4c42  dcfsnz  0x42, 0x0, 0x0
0013f0:  5420  subfwb  0x20, 0x0, 0x0
0013f2:  6d69  negf    0x69, 0x1
0013f4:  6f65  movwf   0x65, 0x1
0013f6:  7475  btg     0x75, 0x2, 0x0
0013f8:  2020  addwfc  0x20, 0x0, 0x0
0013fa:  2020  addwfc  0x20, 0x0, 0x0
0013fc:  2020  addwfc  0x20, 0x0, 0x0
0013fe:  0e80  movlw   0x80
001400:  6e01  movwf   0x01, 0x0
001402:  ec33  call    0x000066, 0x0
001404:  f000
001406:  c0bf  movff   0x0bf, 0x027
001408:  f027
00140a:  0e10  movlw   0x10
00140c:  6e2a  movwf   0x2a, 0x0
00140e:  0e0c  movlw   0x0c
001410:  6e29  movwf   0x29, 0x0
001412:  eca0  call    0x000940, 0x0
001414:  f004
001416:  c0ba  movff   0x0ba, 0x027
001418:  f027
00141a:  0e13  movlw   0x13
00141c:  6e2a  movwf   0x2a, 0x0
00141e:  0eee  movlw   0xee
001420:  6e29  movwf   0x29, 0x0
001422:  c0ba  movff   0x0ba, 0x0a5
001424:  f0a5
001426:  6ba4  clrf    0xa4, 0x1
001428:  0e80  movlw   0x80
00142a:  6e01  movwf   0x01, 0x0
00142c:  0ec0  movlw   0xc0
00142e:  ec33  call    0x000066, 0x0
001430:  f000
001432:  eca0  call    0x000940, 0x0
001434:  f004
001436:  ec59  call    0x000cb2, 0x0
001438:  f006
00143a:  a61f  btfss   0x1f, 0x3, 0x0
00143c:  ef21  goto    0x001442
00143e:  f00a
001440:  961f  bcf     0x1f, 0x3, 0x0
001442:  96d8  clrov
001444:  a79a  btfss   0x9a, 0x3, 0x1
001446:  86d8  setov
001448:  b6d8  skpnov
00144a:  ef29  goto    0x001452
00144c:  f00a
00144e:  ec87  call    0x00150e, 0x0
001450:  f00a
001452:  0e01  movlw   0x01
001454:  b21f  btfsc   0x1f, 0x1, 0x0
001456:  6ae8  clrw
001458:  6e18  movwf   0x18, 0x0
00145a:  6ae8  clrw
00145c:  b79a  btfsc   0x9a, 0x3, 0x1
00145e:  0e01  movlw   0x01
001460:  1218  iorwf   0x18, 0x1, 0x0
001462:  6ae8  clrw
001464:  bb9a  btfsc   0x9a, 0x5, 0x1
001466:  0e01  movlw   0x01
001468:  1218  iorwf   0x18, 0x1, 0x0
00146a:  6ae8  clrw
00146c:  b99a  btfsc   0x9a, 0x4, 0x1
00146e:  0e01  movlw   0x01
001470:  1218  iorwf   0x18, 0x1, 0x0
001472:  b4d8  skpnz
001474:  d7c4  bra     0x0013fe
001476:  0012  return  0x0
001478:  2deb  decfsz  0xeb, 0x0, 0x1
00147a:  ef48  goto    0x001490
00147c:  f00a
00147e:  6bef  clrf    0xef, 0x1
001480:  0e08  movlw   0x08
001482:  6fee  movwf   0xee, 0x1
001484:  0e91  movlw   0x91
001486:  6fed  movwf   0xed, 0x1
001488:  0e3a  movlw   0x3a
00148a:  6fec  movwf   0xec, 0x1
00148c:  ef66  goto    0x0014cc
00148e:  f00a
001490:  0e02  movlw   0x02
001492:  63eb  cpfseq  0xeb, 0x1
001494:  ef55  goto    0x0014aa
001496:  f00a
001498:  6bef  clrf    0xef, 0x1
00149a:  0e22  movlw   0x22
00149c:  6fee  movwf   0xee, 0x1
00149e:  0e44  movlw   0x44
0014a0:  6fed  movwf   0xed, 0x1
0014a2:  0eeb  movlw   0xeb
0014a4:  6fec  movwf   0xec, 0x1
0014a6:  ef66  goto    0x0014cc
0014a8:  f00a
0014aa:  0e03  movlw   0x03
0014ac:  63eb  cpfseq  0xeb, 0x1
0014ae:  ef62  goto    0x0014c4
0014b0:  f00a
0014b2:  6bef  clrf    0xef, 0x1
0014b4:  0e55  movlw   0x55
0014b6:  6fee  movwf   0xee, 0x1
0014b8:  0eac  movlw   0xac
0014ba:  6fed  movwf   0xed, 0x1
0014bc:  0e44  movlw   0x44
0014be:  6fec  movwf   0xec, 0x1
0014c0:  ef66  goto    0x0014cc
0014c2:  f00a
0014c4:  6bef  clrf    0xef, 0x1
0014c6:  6bee  clrf    0xee, 0x1
0014c8:  6bed  clrf    0xed, 0x1
0014ca:  6bec  clrf    0xec, 0x1
0014cc:  0012  return  0x0
0014ce:  664f  tstfsz  0x4f, 0x0
0014d0:  2066  addwfc  0x66, 0x0, 0x0
0014d2:  6e28  movwf   0x28, 0x0
0014d4:  206f  addwfc  0x6f, 0x0, 0x0
0014d6:  6974  setf    0x74, 0x1
0014d8:  656d  cpfsgt  0x6d, 0x1
0014da:  756f  btg     0x6f, 0x2, 0x1
0014dc:  2974  incf    0x74, 0x0, 0x1
0014de:  3033  rrcf    0x33, 0x0, 0x0
0014e0:  7320  btg     0x20, 0x1, 0x1
0014e2:  6365  cpfseq  0x65, 0x1
0014e4:  2020  addwfc  0x20, 0x0, 0x0
0014e6:  2020  addwfc  0x20, 0x0, 0x0
0014e8:  2020  addwfc  0x20, 0x0, 0x0
0014ea:  2020  addwfc  0x20, 0x0, 0x0
0014ec:  2020  addwfc  0x20, 0x0, 0x0
0014ee:  2032  addwfc  0x32, 0x0, 0x0
0014f0:  696d  setf    0x6d, 0x1
0014f2:  206e  addwfc  0x6e, 0x0, 0x0
0014f4:  2020  addwfc  0x20, 0x0, 0x0
0014f6:  2020  addwfc  0x20, 0x0, 0x0
0014f8:  2020  addwfc  0x20, 0x0, 0x0
0014fa:  2020  addwfc  0x20, 0x0, 0x0
0014fc:  2020  addwfc  0x20, 0x0, 0x0
0014fe:  2035  addwfc  0x35, 0x0, 0x0
001500:  696d  setf    0x6d, 0x1
001502:  206e  addwfc  0x6e, 0x0, 0x0
001504:  2020  addwfc  0x20, 0x0, 0x0
001506:  2020  addwfc  0x20, 0x0, 0x0
001508:  2020  addwfc  0x20, 0x0, 0x0
00150a:  2020  addwfc  0x20, 0x0, 0x0
00150c:  2020  addwfc  0x20, 0x0, 0x0

; ===========================================================================
; function_042 @ 0x00150E — main_event_loop  (V1.6b address)
; ---------------------------------------------------------------------------
; The CONTROL panel's top-level event loop. Runs forever after boot setup
; (label_195) completes. Per-iteration:
;   1. Stage 0x0BA value into 0x027 (tx_data_staging) — staged for later
;      send if menu state changed.
;   2. Enable RBIE (button port-change interrupt).
;   3. Call function_023 (button_scan_debounce) and function_019
;      (rx_parser_entry) to absorb input/output edges.
;   4. Decrement idle_timeout_counter (0x09D:0x09E init 0xEA61).
;      When zero → trigger transition to standby_display (label_214).
;   5. Decrement full_sync_counter (0x09F:0x0A0 init 0x4E20).
;      When zero → call function_028 (full_sync_burst — BUG C7).
;   6. Check handshake sentinels (0x0B8/0x0B9/0x0A7/0x0A1) — if any has
;      changed from 0x80 to a real value, the corresponding cached value
;      gets reflected back to MAIN through function_034/035.
; The loop blocks for the full_sync_counter and idle_timeout overflows;
; user input is handled through the RBIF interrupt and processed by
; lazy debounce on the next iteration.
; ===========================================================================
00150e:  c0ba  movff   0x0ba, 0x027         ; stage menu/mode flag for forwarding
001510:  f027
001512:  0e13  movlw   0x13
001514:  6e2a  movwf   0x2a, 0x0
001516:  0eee  movlw   0xee
001518:  6e29  movwf   0x29, 0x0
00151a:  0e80  movlw   0x80
00151c:  6e01  movwf   0x01, 0x0
00151e:  ec33  call    0x000066, 0x0
001520:  f000
001522:  eca0  call    0x000940, 0x0
001524:  f004
001526:  0e03  movlw   0x03
001528:  6fa4  movwf   0xa4, 0x1
00152a:  0e14  movlw   0x14
00152c:  6fa3  movwf   0xa3, 0x1
00152e:  0ece  movlw   0xce
001530:  6fa2  movwf   0xa2, 0x1
001532:  c0eb  movff   0x0eb, 0x0a5
001534:  f0a5
001536:  ecd0  call    0x000fa0, 0x0
001538:  f007
00153a:  961f  bcf     0x1f, 0x3, 0x0
00153c:  6ae8  clrw
00153e:  b39a  btfsc   0x9a, 0x1, 0x1
001540:  0e01  movlw   0x01
001542:  6e18  movwf   0x18, 0x0
001544:  6ae8  clrw
001546:  b59a  btfsc   0x9a, 0x2, 0x1
001548:  0e01  movlw   0x01
00154a:  1218  iorwf   0x18, 0x1, 0x0
00154c:  b4d8  skpnz
00154e:  efac  goto    0x001558
001550:  f00a
001552:  c0a5  movff   0x0a5, 0x0eb
001554:  f0eb
001556:  df90  rcall   0x001478
001558:  6ae8  clrw
00155a:  b79a  btfsc   0x9a, 0x3, 0x1
00155c:  0e01  movlw   0x01
00155e:  6e18  movwf   0x18, 0x0
001560:  0e01  movlw   0x01
001562:  b21f  btfsc   0x1f, 0x1, 0x0
001564:  6ae8  clrw
001566:  1218  iorwf   0x18, 0x1, 0x0
001568:  b4d8  skpnz
00156a:  d7e3  bra     0x001532
00156c:  ec56  call    0x0008ac, 0x0
00156e:  f004
001570:  0012  return  0x0
001572:  6f53  movwf   0x53, 0x1
001574:  7275  btg     0x75, 0x1, 0x0
001576:  6563  cpfsgt  0x63, 0x1
001578:  4320  rrncf   0x20, 0x1, 0x1
00157a:  3148  rrcf    0x48, 0x0, 0x1
00157c:  203a  addwfc  0x3a, 0x0, 0x0
00157e:  2020  addwfc  0x20, 0x0, 0x0
001580:  2020  addwfc  0x20, 0x0, 0x0
001582:  6f53  movwf   0x53, 0x1
001584:  7275  btg     0x75, 0x1, 0x0
001586:  6563  cpfsgt  0x63, 0x1
001588:  4320  rrncf   0x20, 0x1, 0x1
00158a:  3248  rrcf    0x48, 0x1, 0x0
00158c:  203a  addwfc  0x3a, 0x0, 0x0
00158e:  2020  addwfc  0x20, 0x0, 0x0
001590:  2020  addwfc  0x20, 0x0, 0x0
001592:  6f53  movwf   0x53, 0x1
001594:  7275  btg     0x75, 0x1, 0x0
001596:  6563  cpfsgt  0x63, 0x1
001598:  4320  rrncf   0x20, 0x1, 0x1
00159a:  3348  rrcf    0x48, 0x1, 0x1
00159c:  203a  addwfc  0x3a, 0x0, 0x0
00159e:  2020  addwfc  0x20, 0x0, 0x0
0015a0:  2020  addwfc  0x20, 0x0, 0x0
0015a2:  6f53  movwf   0x53, 0x1
0015a4:  7275  btg     0x75, 0x1, 0x0
0015a6:  6563  cpfsgt  0x63, 0x1
0015a8:  4320  rrncf   0x20, 0x1, 0x1
0015aa:  3448  rlcf    0x48, 0x0, 0x0
0015ac:  203a  addwfc  0x3a, 0x0, 0x0
0015ae:  2020  addwfc  0x20, 0x0, 0x0
0015b0:  2020  addwfc  0x20, 0x0, 0x0
0015b2:  6f53  movwf   0x53, 0x1
0015b4:  7275  btg     0x75, 0x1, 0x0
0015b6:  6563  cpfsgt  0x63, 0x1
0015b8:  4320  rrncf   0x20, 0x1, 0x1
0015ba:  3548  rlcf    0x48, 0x0, 0x1
0015bc:  203a  addwfc  0x3a, 0x0, 0x0
0015be:  2020  addwfc  0x20, 0x0, 0x0
0015c0:  2020  addwfc  0x20, 0x0, 0x0
0015c2:  6f53  movwf   0x53, 0x1
0015c4:  7275  btg     0x75, 0x1, 0x0
0015c6:  6563  cpfsgt  0x63, 0x1
0015c8:  4320  rrncf   0x20, 0x1, 0x1
0015ca:  3648  rlcf    0x48, 0x1, 0x0
0015cc:  203a  addwfc  0x3a, 0x0, 0x0
0015ce:  2020  addwfc  0x20, 0x0, 0x0
0015d0:  2020  addwfc  0x20, 0x0, 0x0
0015d2:  5355  movf    0x55, 0x1, 0x1
0015d4:  6142  cpfslt  0x42, 0x1
0015d6:  6475  cpfsgt  0x75, 0x0
0015d8:  6f69  movwf   0x69, 0x1
0015da:  203a  addwfc  0x3a, 0x0, 0x0
0015dc:  2020  addwfc  0x20, 0x0, 0x0
0015de:  2020  addwfc  0x20, 0x0, 0x0
0015e0:  2020  addwfc  0x20, 0x0, 0x0
0015e2:  654c  cpfsgt  0x4c, 0x1
0015e4:  7466  btg     0x66, 0x2, 0x0
0015e6:  2020  addwfc  0x20, 0x0, 0x0
0015e8:  2020  addwfc  0x20, 0x0, 0x0
0015ea:  2020  addwfc  0x20, 0x0, 0x0
0015ec:  2020  addwfc  0x20, 0x0, 0x0
0015ee:  2020  addwfc  0x20, 0x0, 0x0
0015f0:  2020  addwfc  0x20, 0x0, 0x0
0015f2:  6952  setf    0x52, 0x1
0015f4:  6867  setf    0x67, 0x0
0015f6:  2074  addwfc  0x74, 0x0, 0x0
0015f8:  2020  addwfc  0x20, 0x0, 0x0
0015fa:  2020  addwfc  0x20, 0x0, 0x0
0015fc:  2020  addwfc  0x20, 0x0, 0x0
0015fe:  2020  addwfc  0x20, 0x0, 0x0
001600:  2020  addwfc  0x20, 0x0, 0x0
001602:  2b4c  incf    0x4c, 0x1, 0x1
001604:  2052  addwfc  0x52, 0x0, 0x0
001606:  2020  addwfc  0x20, 0x0, 0x0
001608:  2020  addwfc  0x20, 0x0, 0x0
00160a:  2020  addwfc  0x20, 0x0, 0x0
00160c:  2020  addwfc  0x20, 0x0, 0x0
00160e:  2020  addwfc  0x20, 0x0, 0x0
001610:  2020  addwfc  0x20, 0x0, 0x0
001612:  2d4c  decfsz  0x4c, 0x0, 0x1
001614:  2052  addwfc  0x52, 0x0, 0x0
001616:  2020  addwfc  0x20, 0x0, 0x0
001618:  2020  addwfc  0x20, 0x0, 0x0
00161a:  2020  addwfc  0x20, 0x0, 0x0
00161c:  2020  addwfc  0x20, 0x0, 0x0
00161e:  2020  addwfc  0x20, 0x0, 0x0
001620:  2020  addwfc  0x20, 0x0, 0x0
001622:  4143  rrncf   0x43, 0x0, 0x1
001624:  2f54  decfsz  0x54, 0x1, 0x1
001626:  4541  rlncf   0x41, 0x0, 0x1
001628:  2053  addwfc  0x53, 0x0, 0x0
00162a:  2020  addwfc  0x20, 0x0, 0x0
00162c:  2020  addwfc  0x20, 0x0, 0x0
00162e:  2020  addwfc  0x20, 0x0, 0x0
001630:  2020  addwfc  0x20, 0x0, 0x0
001632:  2f53  decfsz  0x53, 0x1, 0x1
001634:  4450  rlncf   0x50, 0x0, 0x0
001636:  4649  rlncf   0x49, 0x1, 0x0
001638:  2020  addwfc  0x20, 0x0, 0x0
00163a:  2020  addwfc  0x20, 0x0, 0x0
00163c:  2020  addwfc  0x20, 0x0, 0x0
00163e:  2020  addwfc  0x20, 0x0, 0x0
001640:  2020  addwfc  0x20, 0x0, 0x0
001642:  0e80  movlw   0x80
001644:  6e01  movwf   0x01, 0x0
001646:  ec33  call    0x000066, 0x0
001648:  f000
00164a:  c0ba  movff   0x0ba, 0x027
00164c:  f027
00164e:  0e13  movlw   0x13
001650:  6e2a  movwf   0x2a, 0x0
001652:  0eee  movlw   0xee
001654:  6e29  movwf   0x29, 0x0
001656:  eca0  call    0x000940, 0x0
001658:  f004
00165a:  c0c0  movff   0x0c0, 0x027
00165c:  f027
00165e:  0e15  movlw   0x15
001660:  6e2a  movwf   0x2a, 0x0
001662:  0e72  movlw   0x72
001664:  6e29  movwf   0x29, 0x0
001666:  0e80  movlw   0x80
001668:  6e01  movwf   0x01, 0x0
00166a:  0ec0  movlw   0xc0
00166c:  ec33  call    0x000066, 0x0
00166e:  f000
001670:  eca0  call    0x000940, 0x0
001672:  f004
001674:  0e06  movlw   0x06
001676:  61c0  cpfslt  0xc0, 0x1
001678:  ef8c  goto    0x001718
00167a:  f00b
00167c:  53c0  movf    0xc0, 0x1, 0x1
00167e:  a4d8  skpz
001680:  ef49  goto    0x001692
001682:  f00b
001684:  ee00  lfsr    0x0, 0x0c1
001686:  f0c1
001688:  51ba  movf    0xba, 0x0, 0x1
00168a:  50eb  movf    0xeb, 0x0, 0x0
00168c:  6fa5  movwf   0xa5, 0x1
00168e:  ef7d  goto    0x0016fa
001690:  f00b
001692:  2dc0  decfsz  0xc0, 0x0, 0x1
001694:  ef53  goto    0x0016a6
001696:  f00b
001698:  ee00  lfsr    0x0, 0x0c7
00169a:  f0c7
00169c:  51ba  movf    0xba, 0x0, 0x1
00169e:  50eb  movf    0xeb, 0x0, 0x0
0016a0:  6fa5  movwf   0xa5, 0x1
0016a2:  ef7d  goto    0x0016fa
0016a4:  f00b
0016a6:  0e02  movlw   0x02
0016a8:  63c0  cpfseq  0xc0, 0x1
0016aa:  ef5e  goto    0x0016bc
0016ac:  f00b
0016ae:  ee00  lfsr    0x0, 0x0cd
0016b0:  f0cd
0016b2:  51ba  movf    0xba, 0x0, 0x1
0016b4:  50eb  movf    0xeb, 0x0, 0x0
0016b6:  6fa5  movwf   0xa5, 0x1
0016b8:  ef7d  goto    0x0016fa
0016ba:  f00b
0016bc:  0e03  movlw   0x03
0016be:  63c0  cpfseq  0xc0, 0x1
0016c0:  ef69  goto    0x0016d2
0016c2:  f00b
0016c4:  ee00  lfsr    0x0, 0x0d3
0016c6:  f0d3
0016c8:  51ba  movf    0xba, 0x0, 0x1
0016ca:  50eb  movf    0xeb, 0x0, 0x0
0016cc:  6fa5  movwf   0xa5, 0x1
0016ce:  ef7d  goto    0x0016fa
0016d0:  f00b
0016d2:  0e04  movlw   0x04
0016d4:  63c0  cpfseq  0xc0, 0x1
0016d6:  ef74  goto    0x0016e8
0016d8:  f00b
0016da:  ee00  lfsr    0x0, 0x0d9
0016dc:  f0d9
0016de:  51ba  movf    0xba, 0x0, 0x1
0016e0:  50eb  movf    0xeb, 0x0, 0x0
0016e2:  6fa5  movwf   0xa5, 0x1
0016e4:  ef7d  goto    0x0016fa
0016e6:  f00b
0016e8:  0e05  movlw   0x05
0016ea:  63c0  cpfseq  0xc0, 0x1
0016ec:  ef7d  goto    0x0016fa
0016ee:  f00b
0016f0:  ee00  lfsr    0x0, 0x0df
0016f2:  f0df
0016f4:  51ba  movf    0xba, 0x0, 0x1
0016f6:  50eb  movf    0xeb, 0x0, 0x0
0016f8:  6fa5  movwf   0xa5, 0x1
0016fa:  0e03  movlw   0x03
0016fc:  6fa4  movwf   0xa4, 0x1
0016fe:  c0a5  movff   0x0a5, 0x027
001700:  f027
001702:  0e15  movlw   0x15
001704:  6e2a  movwf   0x2a, 0x0
001706:  0ee2  movlw   0xe2
001708:  6e29  movwf   0x29, 0x0
00170a:  0e80  movlw   0x80
00170c:  6e01  movwf   0x01, 0x0
00170e:  0ecb  movlw   0xcb
001710:  ec33  call    0x000066, 0x0
001712:  f000
001714:  ef9e  goto    0x00173c
001716:  f00b
001718:  ee00  lfsr    0x0, 0x0e5
00171a:  f0e5
00171c:  51ba  movf    0xba, 0x0, 0x1
00171e:  50eb  movf    0xeb, 0x0, 0x0
001720:  6fa5  movwf   0xa5, 0x1
001722:  0e01  movlw   0x01
001724:  6fa4  movwf   0xa4, 0x1
001726:  c0a5  movff   0x0a5, 0x027
001728:  f027
00172a:  0e16  movlw   0x16
00172c:  6e2a  movwf   0x2a, 0x0
00172e:  0e22  movlw   0x22
001730:  6e29  movwf   0x29, 0x0
001732:  0e80  movlw   0x80
001734:  6e01  movwf   0x01, 0x0
001736:  0ec9  movlw   0xc9
001738:  ec33  call    0x000066, 0x0
00173a:  f000
00173c:  eca0  call    0x000940, 0x0
00173e:  f004
001740:  ec59  call    0x000cb2, 0x0
001742:  f006
001744:  a61f  btfss   0x1f, 0x3, 0x0
001746:  efaa  goto    0x001754
001748:  f00b
00174a:  961f  bcf     0x1f, 0x3, 0x0
00174c:  a21f  btfss   0x1f, 0x1, 0x0
00174e:  efaa  goto    0x001754
001750:  f00b
001752:  d777  bra     0x001642
001754:  319a  rrcf    0x9a, 0x0, 0x1
001756:  32e8  rrcf    0xe8, 0x1, 0x0
001758:  a0d8  skpc
00175a:  efb9  goto    0x001772
00175c:  f00b
00175e:  51a5  movf    0xa5, 0x0, 0x1
001760:  63a4  cpfseq  0xa4, 0x1
001762:  efb6  goto    0x00176c
001764:  f00b
001766:  6ba5  clrf    0xa5, 0x1
001768:  efb7  goto    0x00176e
00176a:  f00b
00176c:  2ba5  incf    0xa5, 0x1, 0x1
00176e:  ecf4  call    0x0017e8, 0x0
001770:  f00b
001772:  96d8  clrov
001774:  a59a  btfss   0x9a, 0x2, 0x1
001776:  86d8  setov
001778:  b6d8  skpnov
00177a:  efca  goto    0x001794
00177c:  f00b
00177e:  53a5  movf    0xa5, 0x1, 0x1
001780:  a4d8  skpz
001782:  efc7  goto    0x00178e
001784:  f00b
001786:  c0a4  movff   0x0a4, 0x0a5
001788:  f0a5
00178a:  efc8  goto    0x001790
00178c:  f00b
00178e:  07a5  decf    0xa5, 0x1, 0x1
001790:  ecf4  call    0x0017e8, 0x0
001792:  f00b
001794:  96d8  clrov
001796:  ab9a  btfss   0x9a, 0x5, 0x1
001798:  86d8  setov
00179a:  b6d8  skpnov
00179c:  efd8  goto    0x0017b0
00179e:  f00b
0017a0:  0e06  movlw   0x06
0017a2:  63c0  cpfseq  0xc0, 0x1
0017a4:  efd7  goto    0x0017ae
0017a6:  f00b
0017a8:  6bc0  clrf    0xc0, 0x1
0017aa:  efd8  goto    0x0017b0
0017ac:  f00b
0017ae:  2bc0  incf    0xc0, 0x1, 0x1
0017b0:  96d8  clrov
0017b2:  a99a  btfss   0x9a, 0x4, 0x1
0017b4:  86d8  setov
0017b6:  b6d8  skpnov
0017b8:  efe7  goto    0x0017ce
0017ba:  f00b
0017bc:  53c0  movf    0xc0, 0x1, 0x1
0017be:  a4d8  skpz
0017c0:  efe6  goto    0x0017cc
0017c2:  f00b
0017c4:  0e06  movlw   0x06
0017c6:  6fc0  movwf   0xc0, 0x1
0017c8:  efe7  goto    0x0017ce
0017ca:  f00b
0017cc:  07c0  decf    0xc0, 0x1, 0x1
0017ce:  6ae8  clrw
0017d0:  b79a  btfsc   0x9a, 0x3, 0x1
0017d2:  0e01  movlw   0x01
0017d4:  6e18  movwf   0x18, 0x0
0017d6:  0e01  movlw   0x01
0017d8:  b21f  btfsc   0x1f, 0x1, 0x0
0017da:  6ae8  clrw
0017dc:  1218  iorwf   0x18, 0x1, 0x0
0017de:  b4d8  skpnz
0017e0:  d73c  bra     0x00165a
0017e2:  ec56  call    0x0008ac, 0x0
0017e4:  f004
0017e6:  0012  return  0x0
0017e8:  ec56  call    0x0008ac, 0x0
0017ea:  f004
0017ec:  0e06  movlw   0x06
0017ee:  61c0  cpfslt  0xc0, 0x1
0017f0:  ef3b  goto    0x001876
0017f2:  f00c
0017f4:  53c0  movf    0xc0, 0x1, 0x1
0017f6:  a4d8  skpz
0017f8:  ef05  goto    0x00180a
0017fa:  f00c
0017fc:  ee00  lfsr    0x0, 0x0c1
0017fe:  f0c1
001800:  51ba  movf    0xba, 0x0, 0x1
001802:  c0a5  movff   0x0a5, 0xfeb
001804:  ffeb
001806:  ef39  goto    0x001872
001808:  f00c
00180a:  2dc0  decfsz  0xc0, 0x0, 0x1
00180c:  ef0f  goto    0x00181e
00180e:  f00c
001810:  ee00  lfsr    0x0, 0x0c7
001812:  f0c7
001814:  51ba  movf    0xba, 0x0, 0x1
001816:  c0a5  movff   0x0a5, 0xfeb
001818:  ffeb
00181a:  ef39  goto    0x001872
00181c:  f00c
00181e:  0e02  movlw   0x02
001820:  63c0  cpfseq  0xc0, 0x1
001822:  ef1a  goto    0x001834
001824:  f00c
001826:  ee00  lfsr    0x0, 0x0cd
001828:  f0cd
00182a:  51ba  movf    0xba, 0x0, 0x1
00182c:  c0a5  movff   0x0a5, 0xfeb
00182e:  ffeb
001830:  ef39  goto    0x001872
001832:  f00c
001834:  0e03  movlw   0x03
001836:  63c0  cpfseq  0xc0, 0x1
001838:  ef25  goto    0x00184a
00183a:  f00c
00183c:  ee00  lfsr    0x0, 0x0d3
00183e:  f0d3
001840:  51ba  movf    0xba, 0x0, 0x1
001842:  c0a5  movff   0x0a5, 0xfeb
001844:  ffeb
001846:  ef39  goto    0x001872
001848:  f00c
00184a:  0e04  movlw   0x04
00184c:  63c0  cpfseq  0xc0, 0x1
00184e:  ef30  goto    0x001860
001850:  f00c
001852:  ee00  lfsr    0x0, 0x0d9
001854:  f0d9
001856:  51ba  movf    0xba, 0x0, 0x1
001858:  c0a5  movff   0x0a5, 0xfeb
00185a:  ffeb
00185c:  ef39  goto    0x001872
00185e:  f00c
001860:  0e05  movlw   0x05
001862:  63c0  cpfseq  0xc0, 0x1
001864:  ef39  goto    0x001872
001866:  f00c
001868:  ee00  lfsr    0x0, 0x0df
00186a:  f0df
00186c:  51ba  movf    0xba, 0x0, 0x1
00186e:  c0a5  movff   0x0a5, 0xfeb
001870:  ffeb
001872:  ef40  goto    0x001880
001874:  f00c
001876:  ee00  lfsr    0x0, 0x0e5
001878:  f0e5
00187a:  51ba  movf    0xba, 0x0, 0x1
00187c:  c0a5  movff   0x0a5, 0xfeb
00187e:  ffeb
001880:  0012  return  0x0
001882:  7541  btg     0x41, 0x2, 0x1
001884:  6f74  movwf   0x74, 0x1
001886:  4420  rlncf   0x20, 0x0, 0x0
001888:  7465  btg     0x65, 0x2, 0x0
00188a:  6365  cpfseq  0x65, 0x1
00188c:  2074  addwfc  0x74, 0x0, 0x0
00188e:  2020  addwfc  0x20, 0x0, 0x0
001890:  2020  addwfc  0x20, 0x0, 0x0
001892:  2f53  decfsz  0x53, 0x1, 0x1
001894:  4450  rlncf   0x50, 0x0, 0x0
001896:  4649  rlncf   0x49, 0x1, 0x0
001898:  2020  addwfc  0x20, 0x0, 0x0
00189a:  2020  addwfc  0x20, 0x0, 0x0
00189c:  2020  addwfc  0x20, 0x0, 0x0
00189e:  2020  addwfc  0x20, 0x0, 0x0
0018a0:  2020  addwfc  0x20, 0x0, 0x0
0018a2:  5355  movf    0x55, 0x1, 0x1
0018a4:  2042  addwfc  0x42, 0x0, 0x0
0018a6:  7541  btg     0x41, 0x2, 0x1
0018a8:  6964  setf    0x64, 0x1
0018aa:  206f  addwfc  0x6f, 0x0, 0x0
0018ac:  2020  addwfc  0x20, 0x0, 0x0
0018ae:  2020  addwfc  0x20, 0x0, 0x0
0018b0:  2020  addwfc  0x20, 0x0, 0x0
0018b2:  4541  rlncf   0x41, 0x0, 0x1
0018b4:  2053  addwfc  0x53, 0x0, 0x0
0018b6:  2020  addwfc  0x20, 0x0, 0x0
0018b8:  2020  addwfc  0x20, 0x0, 0x0
0018ba:  2020  addwfc  0x20, 0x0, 0x0
0018bc:  2020  addwfc  0x20, 0x0, 0x0
0018be:  2020  addwfc  0x20, 0x0, 0x0
0018c0:  2020  addwfc  0x20, 0x0, 0x0
0018c2:  704f  btg     0x4f, 0x0, 0x0
0018c4:  6974  setf    0x74, 0x1
0018c6:  6163  cpfslt  0x63, 0x1
0018c8:  206c  addwfc  0x6c, 0x0, 0x0
0018ca:  2020  addwfc  0x20, 0x0, 0x0
0018cc:  2020  addwfc  0x20, 0x0, 0x0
0018ce:  2020  addwfc  0x20, 0x0, 0x0
0018d0:  2020  addwfc  0x20, 0x0, 0x0
0018d2:  6e41  movwf   0x41, 0x0
0018d4:  6c61  negf    0x61, 0x0
0018d6:  676f  tstfsz  0x6f, 0x1
0018d8:  6575  cpfsgt  0x75, 0x1
0018da:  3120  rrcf    0x20, 0x0, 0x1
0018dc:  2020  addwfc  0x20, 0x0, 0x0
0018de:  2020  addwfc  0x20, 0x0, 0x0
0018e0:  2020  addwfc  0x20, 0x0, 0x0
0018e2:  6e41  movwf   0x41, 0x0
0018e4:  6c61  negf    0x61, 0x0
0018e6:  676f  tstfsz  0x6f, 0x1
0018e8:  6575  cpfsgt  0x75, 0x1
0018ea:  3220  rrcf    0x20, 0x1, 0x0
0018ec:  2020  addwfc  0x20, 0x0, 0x0
0018ee:  2020  addwfc  0x20, 0x0, 0x0
0018f0:  2020  addwfc  0x20, 0x0, 0x0
0018f2:  6e41  movwf   0x41, 0x0
0018f4:  6c61  negf    0x61, 0x0
0018f6:  676f  tstfsz  0x6f, 0x1
0018f8:  6575  cpfsgt  0x75, 0x1
0018fa:  3320  rrcf    0x20, 0x1, 0x1
0018fc:  2020  addwfc  0x20, 0x0, 0x0
0018fe:  2020  addwfc  0x20, 0x0, 0x0
001900:  2020  addwfc  0x20, 0x0, 0x0
001902:  6e41  movwf   0x41, 0x0
001904:  6c61  negf    0x61, 0x0
001906:  676f  tstfsz  0x6f, 0x1
001908:  6575  cpfsgt  0x75, 0x1
00190a:  3420  rlcf    0x20, 0x0, 0x0
00190c:  2020  addwfc  0x20, 0x0, 0x0
00190e:  2020  addwfc  0x20, 0x0, 0x0
001910:  2020  addwfc  0x20, 0x0, 0x0
001912:  0e80  movlw   0x80
001914:  6e01  movwf   0x01, 0x0
001916:  ec33  call    0x000066, 0x0
001918:  f000
00191a:  c0bf  movff   0x0bf, 0x027
00191c:  f027
00191e:  0e10  movlw   0x10
001920:  6e2a  movwf   0x2a, 0x0
001922:  0e0c  movlw   0x0c
001924:  6e29  movwf   0x29, 0x0
001926:  eca0  call    0x000940, 0x0
001928:  f004
00192a:  c0b7  movff   0x0b7, 0x027
00192c:  f027
00192e:  0e18  movlw   0x18
001930:  6e2a  movwf   0x2a, 0x0
001932:  0e82  movlw   0x82
001934:  6e29  movwf   0x29, 0x0
001936:  c0b7  movff   0x0b7, 0x0a5
001938:  f0a5
00193a:  53a1  movf    0xa1, 0x1, 0x1
00193c:  a4d8  skpz
00193e:  efa5  goto    0x00194a
001940:  f00c
001942:  0e05  movlw   0x05
001944:  6fa4  movwf   0xa4, 0x1
001946:  efba  goto    0x001974
001948:  f00c
00194a:  2da1  decfsz  0xa1, 0x0, 0x1
00194c:  efac  goto    0x001958
00194e:  f00c
001950:  0e06  movlw   0x06
001952:  6fa4  movwf   0xa4, 0x1
001954:  efba  goto    0x001974
001956:  f00c
001958:  0e02  movlw   0x02
00195a:  63a1  cpfseq  0xa1, 0x1
00195c:  efb4  goto    0x001968
00195e:  f00c
001960:  0e07  movlw   0x07
001962:  6fa4  movwf   0xa4, 0x1
001964:  efba  goto    0x001974
001966:  f00c
001968:  0e03  movlw   0x03
00196a:  63a1  cpfseq  0xa1, 0x1
00196c:  efba  goto    0x001974
00196e:  f00c
001970:  0e08  movlw   0x08
001972:  6fa4  movwf   0xa4, 0x1
001974:  0e80  movlw   0x80
001976:  6e01  movwf   0x01, 0x0
001978:  0ec0  movlw   0xc0
00197a:  ec33  call    0x000066, 0x0
00197c:  f000
00197e:  eca0  call    0x000940, 0x0
001980:  f004
001982:  ec59  call    0x000cb2, 0x0
001984:  f006
001986:  a61f  btfss   0x1f, 0x3, 0x0
001988:  efcb  goto    0x001996
00198a:  f00c
00198c:  961f  bcf     0x1f, 0x3, 0x0
00198e:  a21f  btfss   0x1f, 0x1, 0x0
001990:  efcb  goto    0x001996
001992:  f00c
001994:  d7be  bra     0x001912
001996:  319a  rrcf    0x9a, 0x0, 0x1
001998:  32e8  rrcf    0xe8, 0x1, 0x0
00199a:  a0d8  skpc
00199c:  efe0  goto    0x0019c0
00199e:  f00c
0019a0:  51a5  movf    0xa5, 0x0, 0x1
0019a2:  63a4  cpfseq  0xa4, 0x1
0019a4:  efd7  goto    0x0019ae
0019a6:  f00c
0019a8:  6ba5  clrf    0xa5, 0x1
0019aa:  efd8  goto    0x0019b0
0019ac:  f00c
0019ae:  2ba5  incf    0xa5, 0x1, 0x1
0019b0:  ec56  call    0x0008ac, 0x0
0019b2:  f004
0019b4:  c0a5  movff   0x0a5, 0x0b7
0019b6:  f0b7
0019b8:  ecb5  call    0x00076a, 0x0
0019ba:  f003
0019bc:  ec11  call    0x000c22, 0x0
0019be:  f006
0019c0:  96d8  clrov
0019c2:  a59a  btfss   0x9a, 0x2, 0x1
0019c4:  86d8  setov
0019c6:  b6d8  skpnov
0019c8:  eff7  goto    0x0019ee
0019ca:  f00c
0019cc:  53a5  movf    0xa5, 0x1, 0x1
0019ce:  a4d8  skpz
0019d0:  efee  goto    0x0019dc
0019d2:  f00c
0019d4:  c0a4  movff   0x0a4, 0x0a5
0019d6:  f0a5
0019d8:  efef  goto    0x0019de
0019da:  f00c
0019dc:  07a5  decf    0xa5, 0x1, 0x1
0019de:  ec56  call    0x0008ac, 0x0
0019e0:  f004
0019e2:  c0a5  movff   0x0a5, 0x0b7
0019e4:  f0b7
0019e6:  ecb5  call    0x00076a, 0x0
0019e8:  f003
0019ea:  ec11  call    0x000c22, 0x0
0019ec:  f006
0019ee:  6ae8  clrw
0019f0:  bb9a  btfsc   0x9a, 0x5, 0x1
0019f2:  0e01  movlw   0x01
0019f4:  6e18  movwf   0x18, 0x0
0019f6:  6ae8  clrw
0019f8:  b99a  btfsc   0x9a, 0x4, 0x1
0019fa:  0e01  movlw   0x01
0019fc:  1218  iorwf   0x18, 0x1, 0x0
0019fe:  0e01  movlw   0x01
001a00:  b21f  btfsc   0x1f, 0x1, 0x0
001a02:  6ae8  clrw
001a04:  1218  iorwf   0x18, 0x1, 0x0
001a06:  b4d8  skpnz
001a08:  d790  bra     0x00192a
001a0a:  0012  return  0x0
001a0c:  ffff  dw      0xffff
001a0e:  ffff  dw      0xffff
001a10:  ffff  dw      0xffff
001a12:  ffff  dw      0xffff
001a14:  ffff  dw      0xffff
001a16:  ffff  dw      0xffff
001a18:  ffff  dw      0xffff
001a1a:  ffff  dw      0xffff
001a1c:  ffff  dw      0xffff
001a1e:  ffff  dw      0xffff
001a20:  ffff  dw      0xffff
001a22:  ffff  dw      0xffff
001a24:  ffff  dw      0xffff
001a26:  ffff  dw      0xffff
001a28:  ffff  dw      0xffff
001a2a:  ffff  dw      0xffff
001a2c:  ffff  dw      0xffff
001a2e:  ffff  dw      0xffff
001a30:  ffff  dw      0xffff
001a32:  ffff  dw      0xffff
001a34:  ffff  dw      0xffff
001a36:  ffff  dw      0xffff
001a38:  ffff  dw      0xffff
001a3a:  ffff  dw      0xffff
001a3c:  ffff  dw      0xffff
001a3e:  ffff  dw      0xffff
001a40:  ffff  dw      0xffff
001a42:  ffff  dw      0xffff
001a44:  ffff  dw      0xffff
001a46:  ffff  dw      0xffff
001a48:  ffff  dw      0xffff
001a4a:  ffff  dw      0xffff
001a4c:  ffff  dw      0xffff
001a4e:  ffff  dw      0xffff
001a50:  ffff  dw      0xffff
001a52:  ffff  dw      0xffff
001a54:  ffff  dw      0xffff
001a56:  ffff  dw      0xffff
001a58:  ffff  dw      0xffff
001a5a:  ffff  dw      0xffff
001a5c:  ffff  dw      0xffff
001a5e:  ffff  dw      0xffff
001a60:  ffff  dw      0xffff
001a62:  ffff  dw      0xffff
001a64:  ffff  dw      0xffff
001a66:  ffff  dw      0xffff
001a68:  ffff  dw      0xffff
001a6a:  ffff  dw      0xffff
001a6c:  ffff  dw      0xffff
001a6e:  ffff  dw      0xffff
001a70:  ffff  dw      0xffff
001a72:  ffff  dw      0xffff
001a74:  ffff  dw      0xffff
001a76:  ffff  dw      0xffff
001a78:  ffff  dw      0xffff
001a7a:  ffff  dw      0xffff
001a7c:  ffff  dw      0xffff
001a7e:  ffff  dw      0xffff
001a80:  ffff  dw      0xffff
001a82:  ffff  dw      0xffff
001a84:  ffff  dw      0xffff
001a86:  ffff  dw      0xffff
001a88:  ffff  dw      0xffff
001a8a:  ffff  dw      0xffff
001a8c:  ffff  dw      0xffff
001a8e:  ffff  dw      0xffff
001a90:  ffff  dw      0xffff
001a92:  ffff  dw      0xffff
001a94:  ffff  dw      0xffff
001a96:  ffff  dw      0xffff
001a98:  ffff  dw      0xffff
001a9a:  ffff  dw      0xffff
001a9c:  ffff  dw      0xffff
001a9e:  ffff  dw      0xffff
001aa0:  ffff  dw      0xffff
001aa2:  ffff  dw      0xffff
001aa4:  ffff  dw      0xffff
001aa6:  ffff  dw      0xffff
001aa8:  ffff  dw      0xffff
001aaa:  ffff  dw      0xffff
001aac:  ffff  dw      0xffff
001aae:  ffff  dw      0xffff
001ab0:  ffff  dw      0xffff
001ab2:  ffff  dw      0xffff
001ab4:  ffff  dw      0xffff
001ab6:  ffff  dw      0xffff
001ab8:  ffff  dw      0xffff
001aba:  ffff  dw      0xffff
001abc:  ffff  dw      0xffff
001abe:  ffff  dw      0xffff
001ac0:  ffff  dw      0xffff
001ac2:  ffff  dw      0xffff
001ac4:  ffff  dw      0xffff
001ac6:  ffff  dw      0xffff
001ac8:  ffff  dw      0xffff
001aca:  ffff  dw      0xffff
001acc:  ffff  dw      0xffff
001ace:  ffff  dw      0xffff
001ad0:  ffff  dw      0xffff
001ad2:  ffff  dw      0xffff
001ad4:  ffff  dw      0xffff
001ad6:  ffff  dw      0xffff
001ad8:  ffff  dw      0xffff
001ada:  ffff  dw      0xffff
001adc:  ffff  dw      0xffff
001ade:  ffff  dw      0xffff
001ae0:  ffff  dw      0xffff
001ae2:  ffff  dw      0xffff
001ae4:  ffff  dw      0xffff
001ae6:  ffff  dw      0xffff
001ae8:  ffff  dw      0xffff
001aea:  ffff  dw      0xffff
001aec:  ffff  dw      0xffff
001aee:  ffff  dw      0xffff
001af0:  ffff  dw      0xffff
001af2:  ffff  dw      0xffff
001af4:  ffff  dw      0xffff
001af6:  ffff  dw      0xffff
001af8:  ffff  dw      0xffff
001afa:  ffff  dw      0xffff
001afc:  ffff  dw      0xffff
001afe:  ffff  dw      0xffff
001b00:  ffff  dw      0xffff
001b02:  ffff  dw      0xffff
001b04:  ffff  dw      0xffff
001b06:  ffff  dw      0xffff
001b08:  ffff  dw      0xffff
001b0a:  ffff  dw      0xffff
001b0c:  ffff  dw      0xffff
001b0e:  ffff  dw      0xffff
001b10:  ffff  dw      0xffff
001b12:  ffff  dw      0xffff
001b14:  ffff  dw      0xffff
001b16:  ffff  dw      0xffff
001b18:  ffff  dw      0xffff
001b1a:  ffff  dw      0xffff
001b1c:  ffff  dw      0xffff
001b1e:  ffff  dw      0xffff
001b20:  ffff  dw      0xffff
001b22:  ffff  dw      0xffff
001b24:  ffff  dw      0xffff
001b26:  ffff  dw      0xffff
001b28:  ffff  dw      0xffff
001b2a:  ffff  dw      0xffff
001b2c:  ffff  dw      0xffff
001b2e:  ffff  dw      0xffff
001b30:  ffff  dw      0xffff
001b32:  ffff  dw      0xffff
001b34:  ffff  dw      0xffff
001b36:  ffff  dw      0xffff
001b38:  ffff  dw      0xffff
001b3a:  ffff  dw      0xffff
001b3c:  ffff  dw      0xffff
001b3e:  ffff  dw      0xffff
001b40:  ffff  dw      0xffff
001b42:  ffff  dw      0xffff
001b44:  ffff  dw      0xffff
001b46:  ffff  dw      0xffff
001b48:  ffff  dw      0xffff
001b4a:  ffff  dw      0xffff
001b4c:  ffff  dw      0xffff
001b4e:  ffff  dw      0xffff
001b50:  ffff  dw      0xffff
001b52:  ffff  dw      0xffff
001b54:  ffff  dw      0xffff
001b56:  ffff  dw      0xffff
001b58:  ffff  dw      0xffff
001b5a:  ffff  dw      0xffff
001b5c:  ffff  dw      0xffff
001b5e:  ffff  dw      0xffff
001b60:  ffff  dw      0xffff
001b62:  ffff  dw      0xffff
001b64:  ffff  dw      0xffff
001b66:  ffff  dw      0xffff
001b68:  ffff  dw      0xffff
001b6a:  ffff  dw      0xffff
001b6c:  ffff  dw      0xffff
001b6e:  ffff  dw      0xffff
001b70:  ffff  dw      0xffff
001b72:  ffff  dw      0xffff
001b74:  ffff  dw      0xffff
001b76:  ffff  dw      0xffff
001b78:  ffff  dw      0xffff
001b7a:  ffff  dw      0xffff
001b7c:  ffff  dw      0xffff
001b7e:  ffff  dw      0xffff
001b80:  ffff  dw      0xffff
001b82:  ffff  dw      0xffff
001b84:  ffff  dw      0xffff
001b86:  ffff  dw      0xffff
001b88:  ffff  dw      0xffff
001b8a:  ffff  dw      0xffff
001b8c:  ffff  dw      0xffff
001b8e:  ffff  dw      0xffff
001b90:  ffff  dw      0xffff
001b92:  ffff  dw      0xffff
001b94:  ffff  dw      0xffff
001b96:  ffff  dw      0xffff
001b98:  ffff  dw      0xffff
001b9a:  ffff  dw      0xffff
001b9c:  ffff  dw      0xffff
001b9e:  ffff  dw      0xffff
001ba0:  ffff  dw      0xffff
001ba2:  ffff  dw      0xffff
001ba4:  ffff  dw      0xffff
001ba6:  ffff  dw      0xffff
001ba8:  ffff  dw      0xffff
001baa:  ffff  dw      0xffff
001bac:  ffff  dw      0xffff
001bae:  ffff  dw      0xffff
001bb0:  ffff  dw      0xffff
001bb2:  ffff  dw      0xffff
001bb4:  ffff  dw      0xffff
001bb6:  ffff  dw      0xffff
001bb8:  ffff  dw      0xffff
001bba:  ffff  dw      0xffff
001bbc:  ffff  dw      0xffff
001bbe:  ffff  dw      0xffff
001bc0:  ffff  dw      0xffff
001bc2:  ffff  dw      0xffff
001bc4:  ffff  dw      0xffff
001bc6:  ffff  dw      0xffff
001bc8:  ffff  dw      0xffff
001bca:  ffff  dw      0xffff
001bcc:  ffff  dw      0xffff
001bce:  ffff  dw      0xffff
001bd0:  ffff  dw      0xffff
001bd2:  ffff  dw      0xffff
001bd4:  ffff  dw      0xffff
001bd6:  ffff  dw      0xffff
001bd8:  ffff  dw      0xffff
001bda:  ffff  dw      0xffff
001bdc:  ffff  dw      0xffff
001bde:  ffff  dw      0xffff
001be0:  ffff  dw      0xffff
001be2:  ffff  dw      0xffff
001be4:  ffff  dw      0xffff
001be6:  ffff  dw      0xffff
001be8:  ffff  dw      0xffff
001bea:  ffff  dw      0xffff
001bec:  ffff  dw      0xffff
001bee:  ffff  dw      0xffff
001bf0:  ffff  dw      0xffff
001bf2:  ffff  dw      0xffff
001bf4:  ffff  dw      0xffff
001bf6:  ffff  dw      0xffff
001bf8:  ffff  dw      0xffff
001bfa:  ffff  dw      0xffff
001bfc:  ffff  dw      0xffff
001bfe:  ffff  dw      0xffff
001c00:  ffff  dw      0xffff
001c02:  ffff  dw      0xffff
001c04:  ffff  dw      0xffff
001c06:  ffff  dw      0xffff
001c08:  ffff  dw      0xffff
001c0a:  ffff  dw      0xffff
001c0c:  ffff  dw      0xffff
001c0e:  ffff  dw      0xffff
001c10:  ffff  dw      0xffff
001c12:  ffff  dw      0xffff
001c14:  ffff  dw      0xffff
001c16:  ffff  dw      0xffff
001c18:  ffff  dw      0xffff
001c1a:  ffff  dw      0xffff
001c1c:  ffff  dw      0xffff
001c1e:  ffff  dw      0xffff
001c20:  ffff  dw      0xffff
001c22:  ffff  dw      0xffff
001c24:  ffff  dw      0xffff
001c26:  ffff  dw      0xffff
001c28:  ffff  dw      0xffff
001c2a:  ffff  dw      0xffff
001c2c:  ffff  dw      0xffff
001c2e:  ffff  dw      0xffff
001c30:  ffff  dw      0xffff
001c32:  ffff  dw      0xffff
001c34:  ffff  dw      0xffff
001c36:  ffff  dw      0xffff
001c38:  ffff  dw      0xffff
001c3a:  ffff  dw      0xffff
001c3c:  ffff  dw      0xffff
001c3e:  ffff  dw      0xffff
001c40:  ffff  dw      0xffff
001c42:  ffff  dw      0xffff
001c44:  ffff  dw      0xffff
001c46:  ffff  dw      0xffff
001c48:  ffff  dw      0xffff
001c4a:  ffff  dw      0xffff
001c4c:  ffff  dw      0xffff
001c4e:  ffff  dw      0xffff
001c50:  ffff  dw      0xffff
001c52:  ffff  dw      0xffff
001c54:  ffff  dw      0xffff
001c56:  ffff  dw      0xffff
001c58:  ffff  dw      0xffff
001c5a:  ffff  dw      0xffff
001c5c:  ffff  dw      0xffff
001c5e:  ffff  dw      0xffff
001c60:  ffff  dw      0xffff
001c62:  ffff  dw      0xffff
001c64:  ffff  dw      0xffff
001c66:  ffff  dw      0xffff
001c68:  ffff  dw      0xffff
001c6a:  ffff  dw      0xffff
001c6c:  ffff  dw      0xffff
001c6e:  ffff  dw      0xffff
001c70:  ffff  dw      0xffff
001c72:  ffff  dw      0xffff
001c74:  ffff  dw      0xffff
001c76:  ffff  dw      0xffff
001c78:  ffff  dw      0xffff
001c7a:  ffff  dw      0xffff
001c7c:  ffff  dw      0xffff
001c7e:  ffff  dw      0xffff
001c80:  ffff  dw      0xffff
001c82:  ffff  dw      0xffff
001c84:  ffff  dw      0xffff
001c86:  ffff  dw      0xffff
001c88:  ffff  dw      0xffff
001c8a:  ffff  dw      0xffff
001c8c:  ffff  dw      0xffff
001c8e:  ffff  dw      0xffff
001c90:  ffff  dw      0xffff
001c92:  ffff  dw      0xffff
001c94:  ffff  dw      0xffff
001c96:  ffff  dw      0xffff
001c98:  ffff  dw      0xffff
001c9a:  ffff  dw      0xffff
001c9c:  ffff  dw      0xffff
001c9e:  ffff  dw      0xffff
001ca0:  ffff  dw      0xffff
001ca2:  ffff  dw      0xffff
001ca4:  ffff  dw      0xffff
001ca6:  ffff  dw      0xffff
001ca8:  ffff  dw      0xffff
001caa:  ffff  dw      0xffff
001cac:  ffff  dw      0xffff
001cae:  ffff  dw      0xffff
001cb0:  ffff  dw      0xffff
001cb2:  ffff  dw      0xffff
001cb4:  ffff  dw      0xffff
001cb6:  ffff  dw      0xffff
001cb8:  ffff  dw      0xffff
001cba:  ffff  dw      0xffff
001cbc:  ffff  dw      0xffff
001cbe:  ffff  dw      0xffff
001cc0:  ffff  dw      0xffff
001cc2:  ffff  dw      0xffff
001cc4:  ffff  dw      0xffff
001cc6:  ffff  dw      0xffff
001cc8:  ffff  dw      0xffff
001cca:  ffff  dw      0xffff
001ccc:  ffff  dw      0xffff
001cce:  ffff  dw      0xffff
001cd0:  ffff  dw      0xffff
001cd2:  ffff  dw      0xffff
001cd4:  ffff  dw      0xffff
001cd6:  ffff  dw      0xffff
001cd8:  ffff  dw      0xffff
001cda:  ffff  dw      0xffff
001cdc:  ffff  dw      0xffff
001cde:  ffff  dw      0xffff
001ce0:  ffff  dw      0xffff
001ce2:  ffff  dw      0xffff
001ce4:  ffff  dw      0xffff
001ce6:  ffff  dw      0xffff
001ce8:  ffff  dw      0xffff
001cea:  ffff  dw      0xffff
001cec:  ffff  dw      0xffff
001cee:  ffff  dw      0xffff
001cf0:  ffff  dw      0xffff
001cf2:  ffff  dw      0xffff
001cf4:  ffff  dw      0xffff
001cf6:  ffff  dw      0xffff
001cf8:  ffff  dw      0xffff
001cfa:  ffff  dw      0xffff
001cfc:  ffff  dw      0xffff
001cfe:  ffff  dw      0xffff
001d00:  ffff  dw      0xffff
001d02:  ffff  dw      0xffff
001d04:  ffff  dw      0xffff
001d06:  ffff  dw      0xffff
001d08:  ffff  dw      0xffff
001d0a:  ffff  dw      0xffff
001d0c:  ffff  dw      0xffff
001d0e:  ffff  dw      0xffff
001d10:  ffff  dw      0xffff
001d12:  ffff  dw      0xffff
001d14:  ffff  dw      0xffff
001d16:  ffff  dw      0xffff
001d18:  ffff  dw      0xffff
001d1a:  ffff  dw      0xffff
001d1c:  ffff  dw      0xffff
001d1e:  ffff  dw      0xffff
001d20:  ffff  dw      0xffff
001d22:  ffff  dw      0xffff
001d24:  ffff  dw      0xffff
001d26:  ffff  dw      0xffff
001d28:  ffff  dw      0xffff
001d2a:  ffff  dw      0xffff
001d2c:  ffff  dw      0xffff
001d2e:  ffff  dw      0xffff
001d30:  ffff  dw      0xffff
001d32:  ffff  dw      0xffff
001d34:  ffff  dw      0xffff
001d36:  ffff  dw      0xffff
001d38:  ffff  dw      0xffff
001d3a:  ffff  dw      0xffff
001d3c:  ffff  dw      0xffff
001d3e:  ffff  dw      0xffff
001d40:  ffff  dw      0xffff
001d42:  ffff  dw      0xffff
001d44:  ffff  dw      0xffff
001d46:  ffff  dw      0xffff
001d48:  ffff  dw      0xffff
001d4a:  ffff  dw      0xffff
001d4c:  ffff  dw      0xffff
001d4e:  ffff  dw      0xffff
001d50:  ffff  dw      0xffff
001d52:  ffff  dw      0xffff
001d54:  ffff  dw      0xffff
001d56:  ffff  dw      0xffff
001d58:  ffff  dw      0xffff
001d5a:  ffff  dw      0xffff
001d5c:  ffff  dw      0xffff
001d5e:  ffff  dw      0xffff
001d60:  ffff  dw      0xffff
001d62:  ffff  dw      0xffff
001d64:  ffff  dw      0xffff
001d66:  ffff  dw      0xffff
001d68:  ffff  dw      0xffff
001d6a:  ffff  dw      0xffff
001d6c:  ffff  dw      0xffff
001d6e:  ffff  dw      0xffff
001d70:  ffff  dw      0xffff
001d72:  ffff  dw      0xffff
001d74:  ffff  dw      0xffff
001d76:  ffff  dw      0xffff
001d78:  ffff  dw      0xffff
001d7a:  ffff  dw      0xffff
001d7c:  ffff  dw      0xffff
001d7e:  ffff  dw      0xffff
001d80:  ffff  dw      0xffff
001d82:  ffff  dw      0xffff
001d84:  ffff  dw      0xffff
001d86:  ffff  dw      0xffff
001d88:  ffff  dw      0xffff
001d8a:  ffff  dw      0xffff
001d8c:  ffff  dw      0xffff
001d8e:  ffff  dw      0xffff
001d90:  ffff  dw      0xffff
001d92:  ffff  dw      0xffff
001d94:  ffff  dw      0xffff
001d96:  ffff  dw      0xffff
001d98:  ffff  dw      0xffff
001d9a:  ffff  dw      0xffff
001d9c:  ffff  dw      0xffff
001d9e:  ffff  dw      0xffff
001da0:  ffff  dw      0xffff
001da2:  ffff  dw      0xffff
001da4:  ffff  dw      0xffff
001da6:  ffff  dw      0xffff
001da8:  ffff  dw      0xffff
001daa:  ffff  dw      0xffff
001dac:  ffff  dw      0xffff
001dae:  ffff  dw      0xffff
001db0:  ffff  dw      0xffff
001db2:  ffff  dw      0xffff
001db4:  ffff  dw      0xffff
001db6:  ffff  dw      0xffff
001db8:  ffff  dw      0xffff
001dba:  ffff  dw      0xffff
001dbc:  ffff  dw      0xffff
001dbe:  ffff  dw      0xffff
001dc0:  ffff  dw      0xffff
001dc2:  ffff  dw      0xffff
001dc4:  ffff  dw      0xffff
001dc6:  ffff  dw      0xffff
001dc8:  ffff  dw      0xffff
001dca:  ffff  dw      0xffff
001dcc:  ffff  dw      0xffff
001dce:  ffff  dw      0xffff
001dd0:  ffff  dw      0xffff
001dd2:  ffff  dw      0xffff
001dd4:  ffff  dw      0xffff
001dd6:  ffff  dw      0xffff
001dd8:  ffff  dw      0xffff
001dda:  ffff  dw      0xffff
001ddc:  ffff  dw      0xffff
001dde:  ffff  dw      0xffff
001de0:  ffff  dw      0xffff
001de2:  ffff  dw      0xffff
001de4:  ffff  dw      0xffff
001de6:  ffff  dw      0xffff
001de8:  ffff  dw      0xffff
001dea:  ffff  dw      0xffff
001dec:  ffff  dw      0xffff
001dee:  ffff  dw      0xffff
001df0:  ffff  dw      0xffff
001df2:  ffff  dw      0xffff
001df4:  ffff  dw      0xffff
001df6:  ffff  dw      0xffff
001df8:  ffff  dw      0xffff
001dfa:  ffff  dw      0xffff
001dfc:  ffff  dw      0xffff
001dfe:  ffff  dw      0xffff
001e00:  ffff  dw      0xffff
001e02:  ffff  dw      0xffff
001e04:  ffff  dw      0xffff
001e06:  ffff  dw      0xffff
001e08:  ffff  dw      0xffff
001e0a:  ffff  dw      0xffff
001e0c:  ffff  dw      0xffff
001e0e:  ffff  dw      0xffff
001e10:  ffff  dw      0xffff
001e12:  ffff  dw      0xffff
001e14:  ffff  dw      0xffff
001e16:  ffff  dw      0xffff
001e18:  ffff  dw      0xffff
001e1a:  ffff  dw      0xffff
001e1c:  ffff  dw      0xffff
001e1e:  ffff  dw      0xffff
001e20:  ffff  dw      0xffff
001e22:  ffff  dw      0xffff
001e24:  ffff  dw      0xffff
001e26:  ffff  dw      0xffff
001e28:  ffff  dw      0xffff
001e2a:  ffff  dw      0xffff
001e2c:  ffff  dw      0xffff
001e2e:  ffff  dw      0xffff
001e30:  ffff  dw      0xffff
001e32:  ffff  dw      0xffff
001e34:  ffff  dw      0xffff
001e36:  ffff  dw      0xffff
001e38:  ffff  dw      0xffff
001e3a:  ffff  dw      0xffff
001e3c:  ffff  dw      0xffff
001e3e:  ffff  dw      0xffff
001e40:  ffff  dw      0xffff
001e42:  ffff  dw      0xffff
001e44:  ffff  dw      0xffff
001e46:  ffff  dw      0xffff
001e48:  ffff  dw      0xffff
001e4a:  ffff  dw      0xffff
001e4c:  ffff  dw      0xffff
001e4e:  ffff  dw      0xffff
001e50:  ffff  dw      0xffff
001e52:  ffff  dw      0xffff
001e54:  ffff  dw      0xffff
001e56:  ffff  dw      0xffff
001e58:  ffff  dw      0xffff
001e5a:  ffff  dw      0xffff
001e5c:  ffff  dw      0xffff
001e5e:  ffff  dw      0xffff
001e60:  ffff  dw      0xffff
001e62:  ffff  dw      0xffff
001e64:  ffff  dw      0xffff
001e66:  ffff  dw      0xffff
001e68:  ffff  dw      0xffff
001e6a:  ffff  dw      0xffff
001e6c:  ffff  dw      0xffff
001e6e:  ffff  dw      0xffff
001e70:  ffff  dw      0xffff
001e72:  ffff  dw      0xffff
001e74:  ffff  dw      0xffff
001e76:  ffff  dw      0xffff
001e78:  ffff  dw      0xffff
001e7a:  ffff  dw      0xffff
001e7c:  ffff  dw      0xffff
001e7e:  ffff  dw      0xffff
001e80:  ffff  dw      0xffff
001e82:  ffff  dw      0xffff
001e84:  ffff  dw      0xffff
001e86:  ffff  dw      0xffff
001e88:  ffff  dw      0xffff
001e8a:  ffff  dw      0xffff
001e8c:  ffff  dw      0xffff
001e8e:  ffff  dw      0xffff
001e90:  ffff  dw      0xffff
001e92:  ffff  dw      0xffff
001e94:  ffff  dw      0xffff
001e96:  ffff  dw      0xffff
001e98:  ffff  dw      0xffff
001e9a:  ffff  dw      0xffff
001e9c:  ffff  dw      0xffff
001e9e:  ffff  dw      0xffff
001ea0:  ffff  dw      0xffff
001ea2:  ffff  dw      0xffff
001ea4:  ffff  dw      0xffff
001ea6:  ffff  dw      0xffff
001ea8:  ffff  dw      0xffff
001eaa:  ffff  dw      0xffff
001eac:  ffff  dw      0xffff
001eae:  ffff  dw      0xffff
001eb0:  ffff  dw      0xffff
001eb2:  ffff  dw      0xffff
001eb4:  ffff  dw      0xffff
001eb6:  ffff  dw      0xffff
001eb8:  ffff  dw      0xffff
001eba:  ffff  dw      0xffff
001ebc:  ffff  dw      0xffff
001ebe:  ffff  dw      0xffff
001ec0:  ffff  dw      0xffff
001ec2:  ffff  dw      0xffff
001ec4:  ffff  dw      0xffff
001ec6:  ffff  dw      0xffff
001ec8:  ffff  dw      0xffff
001eca:  ffff  dw      0xffff
001ecc:  ffff  dw      0xffff
001ece:  ffff  dw      0xffff
001ed0:  ffff  dw      0xffff
001ed2:  ffff  dw      0xffff
001ed4:  ffff  dw      0xffff
001ed6:  ffff  dw      0xffff
001ed8:  ffff  dw      0xffff
001eda:  ffff  dw      0xffff
001edc:  ffff  dw      0xffff
001ede:  ffff  dw      0xffff
001ee0:  ffff  dw      0xffff
001ee2:  ffff  dw      0xffff
001ee4:  ffff  dw      0xffff
001ee6:  ffff  dw      0xffff
001ee8:  ffff  dw      0xffff
001eea:  ffff  dw      0xffff
001eec:  ffff  dw      0xffff
001eee:  ffff  dw      0xffff
001ef0:  ffff  dw      0xffff
001ef2:  ffff  dw      0xffff
001ef4:  ffff  dw      0xffff
001ef6:  ffff  dw      0xffff
001ef8:  ffff  dw      0xffff
001efa:  ffff  dw      0xffff
001efc:  ffff  dw      0xffff
001efe:  ffff  dw      0xffff
001f00:  ffff  dw      0xffff
001f02:  ffff  dw      0xffff
001f04:  ffff  dw      0xffff
001f06:  ffff  dw      0xffff
001f08:  ffff  dw      0xffff
001f0a:  ffff  dw      0xffff
001f0c:  ffff  dw      0xffff
001f0e:  ffff  dw      0xffff
001f10:  ffff  dw      0xffff
001f12:  ffff  dw      0xffff
001f14:  ffff  dw      0xffff
001f16:  ffff  dw      0xffff
001f18:  ffff  dw      0xffff
001f1a:  ffff  dw      0xffff
001f1c:  ffff  dw      0xffff
001f1e:  ffff  dw      0xffff
001f20:  ffff  dw      0xffff
001f22:  ffff  dw      0xffff
001f24:  ffff  dw      0xffff
001f26:  ffff  dw      0xffff
001f28:  ffff  dw      0xffff
001f2a:  ffff  dw      0xffff
001f2c:  ffff  dw      0xffff
001f2e:  ffff  dw      0xffff
001f30:  ffff  dw      0xffff
001f32:  ffff  dw      0xffff
001f34:  ffff  dw      0xffff
001f36:  ffff  dw      0xffff
001f38:  ffff  dw      0xffff
001f3a:  ffff  dw      0xffff
001f3c:  ffff  dw      0xffff
001f3e:  ffff  dw      0xffff
001f40:  ffff  dw      0xffff
001f42:  ffff  dw      0xffff
001f44:  ffff  dw      0xffff
001f46:  ffff  dw      0xffff
001f48:  ffff  dw      0xffff
001f4a:  ffff  dw      0xffff
001f4c:  ffff  dw      0xffff
001f4e:  ffff  dw      0xffff
001f50:  ffff  dw      0xffff
001f52:  ffff  dw      0xffff
001f54:  ffff  dw      0xffff
001f56:  ffff  dw      0xffff
001f58:  ffff  dw      0xffff
001f5a:  ffff  dw      0xffff
001f5c:  ffff  dw      0xffff
001f5e:  ffff  dw      0xffff
001f60:  ffff  dw      0xffff
001f62:  ffff  dw      0xffff
001f64:  ffff  dw      0xffff
001f66:  ffff  dw      0xffff
001f68:  ffff  dw      0xffff
001f6a:  ffff  dw      0xffff
001f6c:  ffff  dw      0xffff
001f6e:  ffff  dw      0xffff
001f70:  ffff  dw      0xffff
001f72:  ffff  dw      0xffff
001f74:  ffff  dw      0xffff
001f76:  ffff  dw      0xffff
001f78:  ffff  dw      0xffff
001f7a:  ffff  dw      0xffff
001f7c:  ffff  dw      0xffff
001f7e:  ffff  dw      0xffff
001f80:  ffff  dw      0xffff
001f82:  ffff  dw      0xffff
001f84:  ffff  dw      0xffff
001f86:  ffff  dw      0xffff
001f88:  ffff  dw      0xffff
001f8a:  ffff  dw      0xffff
001f8c:  ffff  dw      0xffff
001f8e:  ffff  dw      0xffff
001f90:  ffff  dw      0xffff
001f92:  ffff  dw      0xffff
001f94:  ffff  dw      0xffff
001f96:  ffff  dw      0xffff
001f98:  ffff  dw      0xffff
001f9a:  ffff  dw      0xffff
001f9c:  ffff  dw      0xffff
001f9e:  ffff  dw      0xffff
001fa0:  ffff  dw      0xffff
001fa2:  ffff  dw      0xffff
001fa4:  ffff  dw      0xffff
001fa6:  ffff  dw      0xffff
001fa8:  ffff  dw      0xffff
001faa:  ffff  dw      0xffff
001fac:  ffff  dw      0xffff
001fae:  ffff  dw      0xffff
001fb0:  ffff  dw      0xffff
001fb2:  ffff  dw      0xffff
001fb4:  ffff  dw      0xffff
001fb6:  ffff  dw      0xffff
001fb8:  ffff  dw      0xffff
001fba:  ffff  dw      0xffff
001fbc:  ffff  dw      0xffff
001fbe:  ffff  dw      0xffff
001fc0:  ffff  dw      0xffff
001fc2:  ffff  dw      0xffff
001fc4:  ffff  dw      0xffff
001fc6:  ffff  dw      0xffff
001fc8:  ffff  dw      0xffff
001fca:  ffff  dw      0xffff
001fcc:  ffff  dw      0xffff
001fce:  ffff  dw      0xffff
001fd0:  ffff  dw      0xffff
001fd2:  ffff  dw      0xffff
001fd4:  ffff  dw      0xffff
001fd6:  ffff  dw      0xffff
001fd8:  ffff  dw      0xffff
001fda:  ffff  dw      0xffff
001fdc:  ffff  dw      0xffff
001fde:  ffff  dw      0xffff
001fe0:  ffff  dw      0xffff
001fe2:  ffff  dw      0xffff
001fe4:  ffff  dw      0xffff
001fe6:  ffff  dw      0xffff
001fe8:  ffff  dw      0xffff
001fea:  ffff  dw      0xffff
001fec:  ffff  dw      0xffff
001fee:  ffff  dw      0xffff
001ff0:  ffff  dw      0xffff
001ff2:  ffff  dw      0xffff
001ff4:  ffff  dw      0xffff
001ff6:  ffff  dw      0xffff
001ff8:  ffff  dw      0xffff
001ffa:  ffff  dw      0xffff
001ffc:  ffff  dw      0xffff
001ffe:  ffff  dw      0xffff
002000:  ffff  dw      0xffff
002002:  ffff  dw      0xffff
002004:  ffff  dw      0xffff
002006:  ffff  dw      0xffff
002008:  ffff  dw      0xffff
00200a:  ffff  dw      0xffff
00200c:  ffff  dw      0xffff
00200e:  ffff  dw      0xffff
002010:  ffff  dw      0xffff
002012:  ffff  dw      0xffff
002014:  ffff  dw      0xffff
002016:  ffff  dw      0xffff
002018:  ffff  dw      0xffff
00201a:  ffff  dw      0xffff
00201c:  ffff  dw      0xffff
00201e:  ffff  dw      0xffff
002020:  ffff  dw      0xffff
002022:  ffff  dw      0xffff
002024:  ffff  dw      0xffff
002026:  ffff  dw      0xffff
002028:  ffff  dw      0xffff
00202a:  ffff  dw      0xffff
00202c:  ffff  dw      0xffff
00202e:  ffff  dw      0xffff
002030:  ffff  dw      0xffff
002032:  ffff  dw      0xffff
002034:  ffff  dw      0xffff
002036:  ffff  dw      0xffff
002038:  ffff  dw      0xffff
00203a:  ffff  dw      0xffff
00203c:  ffff  dw      0xffff
00203e:  ffff  dw      0xffff
002040:  ffff  dw      0xffff
002042:  ffff  dw      0xffff
002044:  ffff  dw      0xffff
002046:  ffff  dw      0xffff
002048:  ffff  dw      0xffff
00204a:  ffff  dw      0xffff
00204c:  ffff  dw      0xffff
00204e:  ffff  dw      0xffff
002050:  ffff  dw      0xffff
002052:  ffff  dw      0xffff
002054:  ffff  dw      0xffff
002056:  ffff  dw      0xffff
002058:  ffff  dw      0xffff
00205a:  ffff  dw      0xffff
00205c:  ffff  dw      0xffff
00205e:  ffff  dw      0xffff
002060:  ffff  dw      0xffff
002062:  ffff  dw      0xffff
002064:  ffff  dw      0xffff
002066:  ffff  dw      0xffff
002068:  ffff  dw      0xffff
00206a:  ffff  dw      0xffff
00206c:  ffff  dw      0xffff
00206e:  ffff  dw      0xffff
002070:  ffff  dw      0xffff
002072:  ffff  dw      0xffff
002074:  ffff  dw      0xffff
002076:  ffff  dw      0xffff
002078:  ffff  dw      0xffff
00207a:  ffff  dw      0xffff
00207c:  ffff  dw      0xffff
00207e:  ffff  dw      0xffff
002080:  ffff  dw      0xffff
002082:  ffff  dw      0xffff
002084:  ffff  dw      0xffff
002086:  ffff  dw      0xffff
002088:  ffff  dw      0xffff
00208a:  ffff  dw      0xffff
00208c:  ffff  dw      0xffff
00208e:  ffff  dw      0xffff
002090:  ffff  dw      0xffff
002092:  ffff  dw      0xffff
002094:  ffff  dw      0xffff
002096:  ffff  dw      0xffff
002098:  ffff  dw      0xffff
00209a:  ffff  dw      0xffff
00209c:  ffff  dw      0xffff
00209e:  ffff  dw      0xffff
0020a0:  ffff  dw      0xffff
0020a2:  ffff  dw      0xffff
0020a4:  ffff  dw      0xffff
0020a6:  ffff  dw      0xffff
0020a8:  ffff  dw      0xffff
0020aa:  ffff  dw      0xffff
0020ac:  ffff  dw      0xffff
0020ae:  ffff  dw      0xffff
0020b0:  ffff  dw      0xffff
0020b2:  ffff  dw      0xffff
0020b4:  ffff  dw      0xffff
0020b6:  ffff  dw      0xffff
0020b8:  ffff  dw      0xffff
0020ba:  ffff  dw      0xffff
0020bc:  ffff  dw      0xffff
0020be:  ffff  dw      0xffff
0020c0:  ffff  dw      0xffff
0020c2:  ffff  dw      0xffff
0020c4:  ffff  dw      0xffff
0020c6:  ffff  dw      0xffff
0020c8:  ffff  dw      0xffff
0020ca:  ffff  dw      0xffff
0020cc:  ffff  dw      0xffff
0020ce:  ffff  dw      0xffff
0020d0:  ffff  dw      0xffff
0020d2:  ffff  dw      0xffff
0020d4:  ffff  dw      0xffff
0020d6:  ffff  dw      0xffff
0020d8:  ffff  dw      0xffff
0020da:  ffff  dw      0xffff
0020dc:  ffff  dw      0xffff
0020de:  ffff  dw      0xffff
0020e0:  ffff  dw      0xffff
0020e2:  ffff  dw      0xffff
0020e4:  ffff  dw      0xffff
0020e6:  ffff  dw      0xffff
0020e8:  ffff  dw      0xffff
0020ea:  ffff  dw      0xffff
0020ec:  ffff  dw      0xffff
0020ee:  ffff  dw      0xffff
0020f0:  ffff  dw      0xffff
0020f2:  ffff  dw      0xffff
0020f4:  ffff  dw      0xffff
0020f6:  ffff  dw      0xffff
0020f8:  ffff  dw      0xffff
0020fa:  ffff  dw      0xffff
0020fc:  ffff  dw      0xffff
0020fe:  ffff  dw      0xffff
002100:  ffff  dw      0xffff
002102:  ffff  dw      0xffff
002104:  ffff  dw      0xffff
002106:  ffff  dw      0xffff
002108:  ffff  dw      0xffff
00210a:  ffff  dw      0xffff
00210c:  ffff  dw      0xffff
00210e:  ffff  dw      0xffff
002110:  ffff  dw      0xffff
002112:  ffff  dw      0xffff
002114:  ffff  dw      0xffff
002116:  ffff  dw      0xffff
002118:  ffff  dw      0xffff
00211a:  ffff  dw      0xffff
00211c:  ffff  dw      0xffff
00211e:  ffff  dw      0xffff
002120:  ffff  dw      0xffff
002122:  ffff  dw      0xffff
002124:  ffff  dw      0xffff
002126:  ffff  dw      0xffff
002128:  ffff  dw      0xffff
00212a:  ffff  dw      0xffff
00212c:  ffff  dw      0xffff
00212e:  ffff  dw      0xffff
002130:  ffff  dw      0xffff
002132:  ffff  dw      0xffff
002134:  ffff  dw      0xffff
002136:  ffff  dw      0xffff
002138:  ffff  dw      0xffff
00213a:  ffff  dw      0xffff
00213c:  ffff  dw      0xffff
00213e:  ffff  dw      0xffff
002140:  ffff  dw      0xffff
002142:  ffff  dw      0xffff
002144:  ffff  dw      0xffff
002146:  ffff  dw      0xffff
002148:  ffff  dw      0xffff
00214a:  ffff  dw      0xffff
00214c:  ffff  dw      0xffff
00214e:  ffff  dw      0xffff
002150:  ffff  dw      0xffff
002152:  ffff  dw      0xffff
002154:  ffff  dw      0xffff
002156:  ffff  dw      0xffff
002158:  ffff  dw      0xffff
00215a:  ffff  dw      0xffff
00215c:  ffff  dw      0xffff
00215e:  ffff  dw      0xffff
002160:  ffff  dw      0xffff
002162:  ffff  dw      0xffff
002164:  ffff  dw      0xffff
002166:  ffff  dw      0xffff
002168:  ffff  dw      0xffff
00216a:  ffff  dw      0xffff
00216c:  ffff  dw      0xffff
00216e:  ffff  dw      0xffff
002170:  ffff  dw      0xffff
002172:  ffff  dw      0xffff
002174:  ffff  dw      0xffff
002176:  ffff  dw      0xffff
002178:  ffff  dw      0xffff
00217a:  ffff  dw      0xffff
00217c:  ffff  dw      0xffff
00217e:  ffff  dw      0xffff
002180:  ffff  dw      0xffff
002182:  ffff  dw      0xffff
002184:  ffff  dw      0xffff
002186:  ffff  dw      0xffff
002188:  ffff  dw      0xffff
00218a:  ffff  dw      0xffff
00218c:  ffff  dw      0xffff
00218e:  ffff  dw      0xffff
002190:  ffff  dw      0xffff
002192:  ffff  dw      0xffff
002194:  ffff  dw      0xffff
002196:  ffff  dw      0xffff
002198:  ffff  dw      0xffff
00219a:  ffff  dw      0xffff
00219c:  ffff  dw      0xffff
00219e:  ffff  dw      0xffff
0021a0:  ffff  dw      0xffff
0021a2:  ffff  dw      0xffff
0021a4:  ffff  dw      0xffff
0021a6:  ffff  dw      0xffff
0021a8:  ffff  dw      0xffff
0021aa:  ffff  dw      0xffff
0021ac:  ffff  dw      0xffff
0021ae:  ffff  dw      0xffff
0021b0:  ffff  dw      0xffff
0021b2:  ffff  dw      0xffff
0021b4:  ffff  dw      0xffff
0021b6:  ffff  dw      0xffff
0021b8:  ffff  dw      0xffff
0021ba:  ffff  dw      0xffff
0021bc:  ffff  dw      0xffff
0021be:  ffff  dw      0xffff
0021c0:  ffff  dw      0xffff
0021c2:  ffff  dw      0xffff
0021c4:  ffff  dw      0xffff
0021c6:  ffff  dw      0xffff
0021c8:  ffff  dw      0xffff
0021ca:  ffff  dw      0xffff
0021cc:  ffff  dw      0xffff
0021ce:  ffff  dw      0xffff
0021d0:  ffff  dw      0xffff
0021d2:  ffff  dw      0xffff
0021d4:  ffff  dw      0xffff
0021d6:  ffff  dw      0xffff
0021d8:  ffff  dw      0xffff
0021da:  ffff  dw      0xffff
0021dc:  ffff  dw      0xffff
0021de:  ffff  dw      0xffff
0021e0:  ffff  dw      0xffff
0021e2:  ffff  dw      0xffff
0021e4:  ffff  dw      0xffff
0021e6:  ffff  dw      0xffff
0021e8:  ffff  dw      0xffff
0021ea:  ffff  dw      0xffff
0021ec:  ffff  dw      0xffff
0021ee:  ffff  dw      0xffff
0021f0:  ffff  dw      0xffff
0021f2:  ffff  dw      0xffff
0021f4:  ffff  dw      0xffff
0021f6:  ffff  dw      0xffff
0021f8:  ffff  dw      0xffff
0021fa:  ffff  dw      0xffff
0021fc:  ffff  dw      0xffff
0021fe:  ffff  dw      0xffff
002200:  ffff  dw      0xffff
002202:  ffff  dw      0xffff
002204:  ffff  dw      0xffff
002206:  ffff  dw      0xffff
002208:  ffff  dw      0xffff
00220a:  ffff  dw      0xffff
00220c:  ffff  dw      0xffff
00220e:  ffff  dw      0xffff
002210:  ffff  dw      0xffff
002212:  ffff  dw      0xffff
002214:  ffff  dw      0xffff
002216:  ffff  dw      0xffff
002218:  ffff  dw      0xffff
00221a:  ffff  dw      0xffff
00221c:  ffff  dw      0xffff
00221e:  ffff  dw      0xffff
002220:  ffff  dw      0xffff
002222:  ffff  dw      0xffff
002224:  ffff  dw      0xffff
002226:  ffff  dw      0xffff
002228:  ffff  dw      0xffff
00222a:  ffff  dw      0xffff
00222c:  ffff  dw      0xffff
00222e:  ffff  dw      0xffff
002230:  ffff  dw      0xffff
002232:  ffff  dw      0xffff
002234:  ffff  dw      0xffff
002236:  ffff  dw      0xffff
002238:  ffff  dw      0xffff
00223a:  ffff  dw      0xffff
00223c:  ffff  dw      0xffff
00223e:  ffff  dw      0xffff
002240:  ffff  dw      0xffff
002242:  ffff  dw      0xffff
002244:  ffff  dw      0xffff
002246:  ffff  dw      0xffff
002248:  ffff  dw      0xffff
00224a:  ffff  dw      0xffff
00224c:  ffff  dw      0xffff
00224e:  ffff  dw      0xffff
002250:  ffff  dw      0xffff
002252:  ffff  dw      0xffff
002254:  ffff  dw      0xffff
002256:  ffff  dw      0xffff
002258:  ffff  dw      0xffff
00225a:  ffff  dw      0xffff
00225c:  ffff  dw      0xffff
00225e:  ffff  dw      0xffff
002260:  ffff  dw      0xffff
002262:  ffff  dw      0xffff
002264:  ffff  dw      0xffff
002266:  ffff  dw      0xffff
002268:  ffff  dw      0xffff
00226a:  ffff  dw      0xffff
00226c:  ffff  dw      0xffff
00226e:  ffff  dw      0xffff
002270:  ffff  dw      0xffff
002272:  ffff  dw      0xffff
002274:  ffff  dw      0xffff
002276:  ffff  dw      0xffff
002278:  ffff  dw      0xffff
00227a:  ffff  dw      0xffff
00227c:  ffff  dw      0xffff
00227e:  ffff  dw      0xffff
002280:  ffff  dw      0xffff
002282:  ffff  dw      0xffff
002284:  ffff  dw      0xffff
002286:  ffff  dw      0xffff
002288:  ffff  dw      0xffff
00228a:  ffff  dw      0xffff
00228c:  ffff  dw      0xffff
00228e:  ffff  dw      0xffff
002290:  ffff  dw      0xffff
002292:  ffff  dw      0xffff
002294:  ffff  dw      0xffff
002296:  ffff  dw      0xffff
002298:  ffff  dw      0xffff
00229a:  ffff  dw      0xffff
00229c:  ffff  dw      0xffff
00229e:  ffff  dw      0xffff
0022a0:  ffff  dw      0xffff
0022a2:  ffff  dw      0xffff
0022a4:  ffff  dw      0xffff
0022a6:  ffff  dw      0xffff
0022a8:  ffff  dw      0xffff
0022aa:  ffff  dw      0xffff
0022ac:  ffff  dw      0xffff
0022ae:  ffff  dw      0xffff
0022b0:  ffff  dw      0xffff
0022b2:  ffff  dw      0xffff
0022b4:  ffff  dw      0xffff
0022b6:  ffff  dw      0xffff
0022b8:  ffff  dw      0xffff
0022ba:  ffff  dw      0xffff
0022bc:  ffff  dw      0xffff
0022be:  ffff  dw      0xffff
0022c0:  ffff  dw      0xffff
0022c2:  ffff  dw      0xffff
0022c4:  ffff  dw      0xffff
0022c6:  ffff  dw      0xffff
0022c8:  ffff  dw      0xffff
0022ca:  ffff  dw      0xffff
0022cc:  ffff  dw      0xffff
0022ce:  ffff  dw      0xffff
0022d0:  ffff  dw      0xffff
0022d2:  ffff  dw      0xffff
0022d4:  ffff  dw      0xffff
0022d6:  ffff  dw      0xffff
0022d8:  ffff  dw      0xffff
0022da:  ffff  dw      0xffff
0022dc:  ffff  dw      0xffff
0022de:  ffff  dw      0xffff
0022e0:  ffff  dw      0xffff
0022e2:  ffff  dw      0xffff
0022e4:  ffff  dw      0xffff
0022e6:  ffff  dw      0xffff
0022e8:  ffff  dw      0xffff
0022ea:  ffff  dw      0xffff
0022ec:  ffff  dw      0xffff
0022ee:  ffff  dw      0xffff
0022f0:  ffff  dw      0xffff
0022f2:  ffff  dw      0xffff
0022f4:  ffff  dw      0xffff
0022f6:  ffff  dw      0xffff
0022f8:  ffff  dw      0xffff
0022fa:  ffff  dw      0xffff
0022fc:  ffff  dw      0xffff
0022fe:  ffff  dw      0xffff
002300:  ffff  dw      0xffff
002302:  ffff  dw      0xffff
002304:  ffff  dw      0xffff
002306:  ffff  dw      0xffff
002308:  ffff  dw      0xffff
00230a:  ffff  dw      0xffff
00230c:  ffff  dw      0xffff
00230e:  ffff  dw      0xffff
002310:  ffff  dw      0xffff
002312:  ffff  dw      0xffff
002314:  ffff  dw      0xffff
002316:  ffff  dw      0xffff
002318:  ffff  dw      0xffff
00231a:  ffff  dw      0xffff
00231c:  ffff  dw      0xffff
00231e:  ffff  dw      0xffff
002320:  ffff  dw      0xffff
002322:  ffff  dw      0xffff
002324:  ffff  dw      0xffff
002326:  ffff  dw      0xffff
002328:  ffff  dw      0xffff
00232a:  ffff  dw      0xffff
00232c:  ffff  dw      0xffff
00232e:  ffff  dw      0xffff
002330:  ffff  dw      0xffff
002332:  ffff  dw      0xffff
002334:  ffff  dw      0xffff
002336:  ffff  dw      0xffff
002338:  ffff  dw      0xffff
00233a:  ffff  dw      0xffff
00233c:  ffff  dw      0xffff
00233e:  ffff  dw      0xffff
002340:  ffff  dw      0xffff
002342:  ffff  dw      0xffff
002344:  ffff  dw      0xffff
002346:  ffff  dw      0xffff
002348:  ffff  dw      0xffff
00234a:  ffff  dw      0xffff
00234c:  ffff  dw      0xffff
00234e:  ffff  dw      0xffff
002350:  ffff  dw      0xffff
002352:  ffff  dw      0xffff
002354:  ffff  dw      0xffff
002356:  ffff  dw      0xffff
002358:  ffff  dw      0xffff
00235a:  ffff  dw      0xffff
00235c:  ffff  dw      0xffff
00235e:  ffff  dw      0xffff
002360:  ffff  dw      0xffff
002362:  ffff  dw      0xffff
002364:  ffff  dw      0xffff
002366:  ffff  dw      0xffff
002368:  ffff  dw      0xffff
00236a:  ffff  dw      0xffff
00236c:  ffff  dw      0xffff
00236e:  ffff  dw      0xffff
002370:  ffff  dw      0xffff
002372:  ffff  dw      0xffff
002374:  ffff  dw      0xffff
002376:  ffff  dw      0xffff
002378:  ffff  dw      0xffff
00237a:  ffff  dw      0xffff
00237c:  ffff  dw      0xffff
00237e:  ffff  dw      0xffff
002380:  ffff  dw      0xffff
002382:  ffff  dw      0xffff
002384:  ffff  dw      0xffff
002386:  ffff  dw      0xffff
002388:  ffff  dw      0xffff
00238a:  ffff  dw      0xffff
00238c:  ffff  dw      0xffff
00238e:  ffff  dw      0xffff
002390:  ffff  dw      0xffff
002392:  ffff  dw      0xffff
002394:  ffff  dw      0xffff
002396:  ffff  dw      0xffff
002398:  ffff  dw      0xffff
00239a:  ffff  dw      0xffff
00239c:  ffff  dw      0xffff
00239e:  ffff  dw      0xffff
0023a0:  ffff  dw      0xffff
0023a2:  ffff  dw      0xffff
0023a4:  ffff  dw      0xffff
0023a6:  ffff  dw      0xffff
0023a8:  ffff  dw      0xffff
0023aa:  ffff  dw      0xffff
0023ac:  ffff  dw      0xffff
0023ae:  ffff  dw      0xffff
0023b0:  ffff  dw      0xffff
0023b2:  ffff  dw      0xffff
0023b4:  ffff  dw      0xffff
0023b6:  ffff  dw      0xffff
0023b8:  ffff  dw      0xffff
0023ba:  ffff  dw      0xffff
0023bc:  ffff  dw      0xffff
0023be:  ffff  dw      0xffff
0023c0:  ffff  dw      0xffff
0023c2:  ffff  dw      0xffff
0023c4:  ffff  dw      0xffff
0023c6:  ffff  dw      0xffff
0023c8:  ffff  dw      0xffff
0023ca:  ffff  dw      0xffff
0023cc:  ffff  dw      0xffff
0023ce:  ffff  dw      0xffff
0023d0:  ffff  dw      0xffff
0023d2:  ffff  dw      0xffff
0023d4:  ffff  dw      0xffff
0023d6:  ffff  dw      0xffff
0023d8:  ffff  dw      0xffff
0023da:  ffff  dw      0xffff
0023dc:  ffff  dw      0xffff
0023de:  ffff  dw      0xffff
0023e0:  ffff  dw      0xffff
0023e2:  ffff  dw      0xffff
0023e4:  ffff  dw      0xffff
0023e6:  ffff  dw      0xffff
0023e8:  ffff  dw      0xffff
0023ea:  ffff  dw      0xffff
0023ec:  ffff  dw      0xffff
0023ee:  ffff  dw      0xffff
0023f0:  ffff  dw      0xffff
0023f2:  ffff  dw      0xffff
0023f4:  ffff  dw      0xffff
0023f6:  ffff  dw      0xffff
0023f8:  ffff  dw      0xffff
0023fa:  ffff  dw      0xffff
0023fc:  ffff  dw      0xffff
0023fe:  ffff  dw      0xffff
002400:  ffff  dw      0xffff
002402:  ffff  dw      0xffff
002404:  ffff  dw      0xffff
002406:  ffff  dw      0xffff
002408:  ffff  dw      0xffff
00240a:  ffff  dw      0xffff
00240c:  ffff  dw      0xffff
00240e:  ffff  dw      0xffff
002410:  ffff  dw      0xffff
002412:  ffff  dw      0xffff
002414:  ffff  dw      0xffff
002416:  ffff  dw      0xffff
002418:  ffff  dw      0xffff
00241a:  ffff  dw      0xffff
00241c:  ffff  dw      0xffff
00241e:  ffff  dw      0xffff
002420:  ffff  dw      0xffff
002422:  ffff  dw      0xffff
002424:  ffff  dw      0xffff
002426:  ffff  dw      0xffff
002428:  ffff  dw      0xffff
00242a:  ffff  dw      0xffff
00242c:  ffff  dw      0xffff
00242e:  ffff  dw      0xffff
002430:  ffff  dw      0xffff
002432:  ffff  dw      0xffff
002434:  ffff  dw      0xffff
002436:  ffff  dw      0xffff
002438:  ffff  dw      0xffff
00243a:  ffff  dw      0xffff
00243c:  ffff  dw      0xffff
00243e:  ffff  dw      0xffff
002440:  ffff  dw      0xffff
002442:  ffff  dw      0xffff
002444:  ffff  dw      0xffff
002446:  ffff  dw      0xffff
002448:  ffff  dw      0xffff
00244a:  ffff  dw      0xffff
00244c:  ffff  dw      0xffff
00244e:  ffff  dw      0xffff
002450:  ffff  dw      0xffff
002452:  ffff  dw      0xffff
002454:  ffff  dw      0xffff
002456:  ffff  dw      0xffff
002458:  ffff  dw      0xffff
00245a:  ffff  dw      0xffff
00245c:  ffff  dw      0xffff
00245e:  ffff  dw      0xffff
002460:  ffff  dw      0xffff
002462:  ffff  dw      0xffff
002464:  ffff  dw      0xffff
002466:  ffff  dw      0xffff
002468:  ffff  dw      0xffff
00246a:  ffff  dw      0xffff
00246c:  ffff  dw      0xffff
00246e:  ffff  dw      0xffff
002470:  ffff  dw      0xffff
002472:  ffff  dw      0xffff
002474:  ffff  dw      0xffff
002476:  ffff  dw      0xffff
002478:  ffff  dw      0xffff
00247a:  ffff  dw      0xffff
00247c:  ffff  dw      0xffff
00247e:  ffff  dw      0xffff
002480:  ffff  dw      0xffff
002482:  ffff  dw      0xffff
002484:  ffff  dw      0xffff
002486:  ffff  dw      0xffff
002488:  ffff  dw      0xffff
00248a:  ffff  dw      0xffff
00248c:  ffff  dw      0xffff
00248e:  ffff  dw      0xffff
002490:  ffff  dw      0xffff
002492:  ffff  dw      0xffff
002494:  ffff  dw      0xffff
002496:  ffff  dw      0xffff
002498:  ffff  dw      0xffff
00249a:  ffff  dw      0xffff
00249c:  ffff  dw      0xffff
00249e:  ffff  dw      0xffff
0024a0:  ffff  dw      0xffff
0024a2:  ffff  dw      0xffff
0024a4:  ffff  dw      0xffff
0024a6:  ffff  dw      0xffff
0024a8:  ffff  dw      0xffff
0024aa:  ffff  dw      0xffff
0024ac:  ffff  dw      0xffff
0024ae:  ffff  dw      0xffff
0024b0:  ffff  dw      0xffff
0024b2:  ffff  dw      0xffff
0024b4:  ffff  dw      0xffff
0024b6:  ffff  dw      0xffff
0024b8:  ffff  dw      0xffff
0024ba:  ffff  dw      0xffff
0024bc:  ffff  dw      0xffff
0024be:  ffff  dw      0xffff
0024c0:  ffff  dw      0xffff
0024c2:  ffff  dw      0xffff
0024c4:  ffff  dw      0xffff
0024c6:  ffff  dw      0xffff
0024c8:  ffff  dw      0xffff
0024ca:  ffff  dw      0xffff
0024cc:  ffff  dw      0xffff
0024ce:  ffff  dw      0xffff
0024d0:  ffff  dw      0xffff
0024d2:  ffff  dw      0xffff
0024d4:  ffff  dw      0xffff
0024d6:  ffff  dw      0xffff
0024d8:  ffff  dw      0xffff
0024da:  ffff  dw      0xffff
0024dc:  ffff  dw      0xffff
0024de:  ffff  dw      0xffff
0024e0:  ffff  dw      0xffff
0024e2:  ffff  dw      0xffff
0024e4:  ffff  dw      0xffff
0024e6:  ffff  dw      0xffff
0024e8:  ffff  dw      0xffff
0024ea:  ffff  dw      0xffff
0024ec:  ffff  dw      0xffff
0024ee:  ffff  dw      0xffff
0024f0:  ffff  dw      0xffff
0024f2:  ffff  dw      0xffff
0024f4:  ffff  dw      0xffff
0024f6:  ffff  dw      0xffff
0024f8:  ffff  dw      0xffff
0024fa:  ffff  dw      0xffff
0024fc:  ffff  dw      0xffff
0024fe:  ffff  dw      0xffff
002500:  ffff  dw      0xffff
002502:  ffff  dw      0xffff
002504:  ffff  dw      0xffff
002506:  ffff  dw      0xffff
002508:  ffff  dw      0xffff
00250a:  ffff  dw      0xffff
00250c:  ffff  dw      0xffff
00250e:  ffff  dw      0xffff
002510:  ffff  dw      0xffff
002512:  ffff  dw      0xffff
002514:  ffff  dw      0xffff
002516:  ffff  dw      0xffff
002518:  ffff  dw      0xffff
00251a:  ffff  dw      0xffff
00251c:  ffff  dw      0xffff
00251e:  ffff  dw      0xffff
002520:  ffff  dw      0xffff
002522:  ffff  dw      0xffff
002524:  ffff  dw      0xffff
002526:  ffff  dw      0xffff
002528:  ffff  dw      0xffff
00252a:  ffff  dw      0xffff
00252c:  ffff  dw      0xffff
00252e:  ffff  dw      0xffff
002530:  ffff  dw      0xffff
002532:  ffff  dw      0xffff
002534:  ffff  dw      0xffff
002536:  ffff  dw      0xffff
002538:  ffff  dw      0xffff
00253a:  ffff  dw      0xffff
00253c:  ffff  dw      0xffff
00253e:  ffff  dw      0xffff
002540:  ffff  dw      0xffff
002542:  ffff  dw      0xffff
002544:  ffff  dw      0xffff
002546:  ffff  dw      0xffff
002548:  ffff  dw      0xffff
00254a:  ffff  dw      0xffff
00254c:  ffff  dw      0xffff
00254e:  ffff  dw      0xffff
002550:  ffff  dw      0xffff
002552:  ffff  dw      0xffff
002554:  ffff  dw      0xffff
002556:  ffff  dw      0xffff
002558:  ffff  dw      0xffff
00255a:  ffff  dw      0xffff
00255c:  ffff  dw      0xffff
00255e:  ffff  dw      0xffff
002560:  ffff  dw      0xffff
002562:  ffff  dw      0xffff
002564:  ffff  dw      0xffff
002566:  ffff  dw      0xffff
002568:  ffff  dw      0xffff
00256a:  ffff  dw      0xffff
00256c:  ffff  dw      0xffff
00256e:  ffff  dw      0xffff
002570:  ffff  dw      0xffff
002572:  ffff  dw      0xffff
002574:  ffff  dw      0xffff
002576:  ffff  dw      0xffff
002578:  ffff  dw      0xffff
00257a:  ffff  dw      0xffff
00257c:  ffff  dw      0xffff
00257e:  ffff  dw      0xffff
002580:  ffff  dw      0xffff
002582:  ffff  dw      0xffff
002584:  ffff  dw      0xffff
002586:  ffff  dw      0xffff
002588:  ffff  dw      0xffff
00258a:  ffff  dw      0xffff
00258c:  ffff  dw      0xffff
00258e:  ffff  dw      0xffff
002590:  ffff  dw      0xffff
002592:  ffff  dw      0xffff
002594:  ffff  dw      0xffff
002596:  ffff  dw      0xffff
002598:  ffff  dw      0xffff
00259a:  ffff  dw      0xffff
00259c:  ffff  dw      0xffff
00259e:  ffff  dw      0xffff
0025a0:  ffff  dw      0xffff
0025a2:  ffff  dw      0xffff
0025a4:  ffff  dw      0xffff
0025a6:  ffff  dw      0xffff
0025a8:  ffff  dw      0xffff
0025aa:  ffff  dw      0xffff
0025ac:  ffff  dw      0xffff
0025ae:  ffff  dw      0xffff
0025b0:  ffff  dw      0xffff
0025b2:  ffff  dw      0xffff
0025b4:  ffff  dw      0xffff
0025b6:  ffff  dw      0xffff
0025b8:  ffff  dw      0xffff
0025ba:  ffff  dw      0xffff
0025bc:  ffff  dw      0xffff
0025be:  ffff  dw      0xffff
0025c0:  ffff  dw      0xffff
0025c2:  ffff  dw      0xffff
0025c4:  ffff  dw      0xffff
0025c6:  ffff  dw      0xffff
0025c8:  ffff  dw      0xffff
0025ca:  ffff  dw      0xffff
0025cc:  ffff  dw      0xffff
0025ce:  ffff  dw      0xffff
0025d0:  ffff  dw      0xffff
0025d2:  ffff  dw      0xffff
0025d4:  ffff  dw      0xffff
0025d6:  ffff  dw      0xffff
0025d8:  ffff  dw      0xffff
0025da:  ffff  dw      0xffff
0025dc:  ffff  dw      0xffff
0025de:  ffff  dw      0xffff
0025e0:  ffff  dw      0xffff
0025e2:  ffff  dw      0xffff
0025e4:  ffff  dw      0xffff
0025e6:  ffff  dw      0xffff
0025e8:  ffff  dw      0xffff
0025ea:  ffff  dw      0xffff
0025ec:  ffff  dw      0xffff
0025ee:  ffff  dw      0xffff
0025f0:  ffff  dw      0xffff
0025f2:  ffff  dw      0xffff
0025f4:  ffff  dw      0xffff
0025f6:  ffff  dw      0xffff
0025f8:  ffff  dw      0xffff
0025fa:  ffff  dw      0xffff
0025fc:  ffff  dw      0xffff
0025fe:  ffff  dw      0xffff
002600:  ffff  dw      0xffff
002602:  ffff  dw      0xffff
002604:  ffff  dw      0xffff
002606:  ffff  dw      0xffff
002608:  ffff  dw      0xffff
00260a:  ffff  dw      0xffff
00260c:  ffff  dw      0xffff
00260e:  ffff  dw      0xffff
002610:  ffff  dw      0xffff
002612:  ffff  dw      0xffff
002614:  ffff  dw      0xffff
002616:  ffff  dw      0xffff
002618:  ffff  dw      0xffff
00261a:  ffff  dw      0xffff
00261c:  ffff  dw      0xffff
00261e:  ffff  dw      0xffff
002620:  ffff  dw      0xffff
002622:  ffff  dw      0xffff
002624:  ffff  dw      0xffff
002626:  ffff  dw      0xffff
002628:  ffff  dw      0xffff
00262a:  ffff  dw      0xffff
00262c:  ffff  dw      0xffff
00262e:  ffff  dw      0xffff
002630:  ffff  dw      0xffff
002632:  ffff  dw      0xffff
002634:  ffff  dw      0xffff
002636:  ffff  dw      0xffff
002638:  ffff  dw      0xffff
00263a:  ffff  dw      0xffff
00263c:  ffff  dw      0xffff
00263e:  ffff  dw      0xffff
002640:  ffff  dw      0xffff
002642:  ffff  dw      0xffff
002644:  ffff  dw      0xffff
002646:  ffff  dw      0xffff
002648:  ffff  dw      0xffff
00264a:  ffff  dw      0xffff
00264c:  ffff  dw      0xffff
00264e:  ffff  dw      0xffff
002650:  ffff  dw      0xffff
002652:  ffff  dw      0xffff
002654:  ffff  dw      0xffff
002656:  ffff  dw      0xffff
002658:  ffff  dw      0xffff
00265a:  ffff  dw      0xffff
00265c:  ffff  dw      0xffff
00265e:  ffff  dw      0xffff
002660:  ffff  dw      0xffff
002662:  ffff  dw      0xffff
002664:  ffff  dw      0xffff
002666:  ffff  dw      0xffff
002668:  ffff  dw      0xffff
00266a:  ffff  dw      0xffff
00266c:  ffff  dw      0xffff
00266e:  ffff  dw      0xffff
002670:  ffff  dw      0xffff
002672:  ffff  dw      0xffff
002674:  ffff  dw      0xffff
002676:  ffff  dw      0xffff
002678:  ffff  dw      0xffff
00267a:  ffff  dw      0xffff
00267c:  ffff  dw      0xffff
00267e:  ffff  dw      0xffff
002680:  ffff  dw      0xffff
002682:  ffff  dw      0xffff
002684:  ffff  dw      0xffff
002686:  ffff  dw      0xffff
002688:  ffff  dw      0xffff
00268a:  ffff  dw      0xffff
00268c:  ffff  dw      0xffff
00268e:  ffff  dw      0xffff
002690:  ffff  dw      0xffff
002692:  ffff  dw      0xffff
002694:  ffff  dw      0xffff
002696:  ffff  dw      0xffff
002698:  ffff  dw      0xffff
00269a:  ffff  dw      0xffff
00269c:  ffff  dw      0xffff
00269e:  ffff  dw      0xffff
0026a0:  ffff  dw      0xffff
0026a2:  ffff  dw      0xffff
0026a4:  ffff  dw      0xffff
0026a6:  ffff  dw      0xffff
0026a8:  ffff  dw      0xffff
0026aa:  ffff  dw      0xffff
0026ac:  ffff  dw      0xffff
0026ae:  ffff  dw      0xffff
0026b0:  ffff  dw      0xffff
0026b2:  ffff  dw      0xffff
0026b4:  ffff  dw      0xffff
0026b6:  ffff  dw      0xffff
0026b8:  ffff  dw      0xffff
0026ba:  ffff  dw      0xffff
0026bc:  ffff  dw      0xffff
0026be:  ffff  dw      0xffff
0026c0:  ffff  dw      0xffff
0026c2:  ffff  dw      0xffff
0026c4:  ffff  dw      0xffff
0026c6:  ffff  dw      0xffff
0026c8:  ffff  dw      0xffff
0026ca:  ffff  dw      0xffff
0026cc:  ffff  dw      0xffff
0026ce:  ffff  dw      0xffff
0026d0:  ffff  dw      0xffff
0026d2:  ffff  dw      0xffff
0026d4:  ffff  dw      0xffff
0026d6:  ffff  dw      0xffff
0026d8:  ffff  dw      0xffff
0026da:  ffff  dw      0xffff
0026dc:  ffff  dw      0xffff
0026de:  ffff  dw      0xffff
0026e0:  ffff  dw      0xffff
0026e2:  ffff  dw      0xffff
0026e4:  ffff  dw      0xffff
0026e6:  ffff  dw      0xffff
0026e8:  ffff  dw      0xffff
0026ea:  ffff  dw      0xffff
0026ec:  ffff  dw      0xffff
0026ee:  ffff  dw      0xffff
0026f0:  ffff  dw      0xffff
0026f2:  ffff  dw      0xffff
0026f4:  ffff  dw      0xffff
0026f6:  ffff  dw      0xffff
0026f8:  ffff  dw      0xffff
0026fa:  ffff  dw      0xffff
0026fc:  ffff  dw      0xffff
0026fe:  ffff  dw      0xffff
002700:  ffff  dw      0xffff
002702:  ffff  dw      0xffff
002704:  ffff  dw      0xffff
002706:  ffff  dw      0xffff
002708:  ffff  dw      0xffff
00270a:  ffff  dw      0xffff
00270c:  ffff  dw      0xffff
00270e:  ffff  dw      0xffff
002710:  ffff  dw      0xffff
002712:  ffff  dw      0xffff
002714:  ffff  dw      0xffff
002716:  ffff  dw      0xffff
002718:  ffff  dw      0xffff
00271a:  ffff  dw      0xffff
00271c:  ffff  dw      0xffff
00271e:  ffff  dw      0xffff
002720:  ffff  dw      0xffff
002722:  ffff  dw      0xffff
002724:  ffff  dw      0xffff
002726:  ffff  dw      0xffff
002728:  ffff  dw      0xffff
00272a:  ffff  dw      0xffff
00272c:  ffff  dw      0xffff
00272e:  ffff  dw      0xffff
002730:  ffff  dw      0xffff
002732:  ffff  dw      0xffff
002734:  ffff  dw      0xffff
002736:  ffff  dw      0xffff
002738:  ffff  dw      0xffff
00273a:  ffff  dw      0xffff
00273c:  ffff  dw      0xffff
00273e:  ffff  dw      0xffff
002740:  ffff  dw      0xffff
002742:  ffff  dw      0xffff
002744:  ffff  dw      0xffff
002746:  ffff  dw      0xffff
002748:  ffff  dw      0xffff
00274a:  ffff  dw      0xffff
00274c:  ffff  dw      0xffff
00274e:  ffff  dw      0xffff
002750:  ffff  dw      0xffff
002752:  ffff  dw      0xffff
002754:  ffff  dw      0xffff
002756:  ffff  dw      0xffff
002758:  ffff  dw      0xffff
00275a:  ffff  dw      0xffff
00275c:  ffff  dw      0xffff
00275e:  ffff  dw      0xffff
002760:  ffff  dw      0xffff
002762:  ffff  dw      0xffff
002764:  ffff  dw      0xffff
002766:  ffff  dw      0xffff
002768:  ffff  dw      0xffff
00276a:  ffff  dw      0xffff
00276c:  ffff  dw      0xffff
00276e:  ffff  dw      0xffff
002770:  ffff  dw      0xffff
002772:  ffff  dw      0xffff
002774:  ffff  dw      0xffff
002776:  ffff  dw      0xffff
002778:  ffff  dw      0xffff
00277a:  ffff  dw      0xffff
00277c:  ffff  dw      0xffff
00277e:  ffff  dw      0xffff
002780:  ffff  dw      0xffff
002782:  ffff  dw      0xffff
002784:  ffff  dw      0xffff
002786:  ffff  dw      0xffff
002788:  ffff  dw      0xffff
00278a:  ffff  dw      0xffff
00278c:  ffff  dw      0xffff
00278e:  ffff  dw      0xffff
002790:  ffff  dw      0xffff
002792:  ffff  dw      0xffff
002794:  ffff  dw      0xffff
002796:  ffff  dw      0xffff
002798:  ffff  dw      0xffff
00279a:  ffff  dw      0xffff
00279c:  ffff  dw      0xffff
00279e:  ffff  dw      0xffff
0027a0:  ffff  dw      0xffff
0027a2:  ffff  dw      0xffff
0027a4:  ffff  dw      0xffff
0027a6:  ffff  dw      0xffff
0027a8:  ffff  dw      0xffff
0027aa:  ffff  dw      0xffff
0027ac:  ffff  dw      0xffff
0027ae:  ffff  dw      0xffff
0027b0:  ffff  dw      0xffff
0027b2:  ffff  dw      0xffff
0027b4:  ffff  dw      0xffff
0027b6:  ffff  dw      0xffff
0027b8:  ffff  dw      0xffff
0027ba:  ffff  dw      0xffff
0027bc:  ffff  dw      0xffff
0027be:  ffff  dw      0xffff
0027c0:  ffff  dw      0xffff
0027c2:  ffff  dw      0xffff
0027c4:  ffff  dw      0xffff
0027c6:  ffff  dw      0xffff
0027c8:  ffff  dw      0xffff
0027ca:  ffff  dw      0xffff
0027cc:  ffff  dw      0xffff
0027ce:  ffff  dw      0xffff
0027d0:  ffff  dw      0xffff
0027d2:  ffff  dw      0xffff
0027d4:  ffff  dw      0xffff
0027d6:  ffff  dw      0xffff
0027d8:  ffff  dw      0xffff
0027da:  ffff  dw      0xffff
0027dc:  ffff  dw      0xffff
0027de:  ffff  dw      0xffff
0027e0:  ffff  dw      0xffff
0027e2:  ffff  dw      0xffff
0027e4:  ffff  dw      0xffff
0027e6:  ffff  dw      0xffff
0027e8:  ffff  dw      0xffff
0027ea:  ffff  dw      0xffff
0027ec:  ffff  dw      0xffff
0027ee:  ffff  dw      0xffff
0027f0:  ffff  dw      0xffff
0027f2:  ffff  dw      0xffff
0027f4:  ffff  dw      0xffff
0027f6:  ffff  dw      0xffff
0027f8:  ffff  dw      0xffff
0027fa:  ffff  dw      0xffff
0027fc:  ffff  dw      0xffff
0027fe:  ffff  dw      0xffff
002800:  ffff  dw      0xffff
002802:  ffff  dw      0xffff
002804:  ffff  dw      0xffff
002806:  ffff  dw      0xffff
002808:  ffff  dw      0xffff
00280a:  ffff  dw      0xffff
00280c:  ffff  dw      0xffff
00280e:  ffff  dw      0xffff
002810:  ffff  dw      0xffff
002812:  ffff  dw      0xffff
002814:  ffff  dw      0xffff
002816:  ffff  dw      0xffff
002818:  ffff  dw      0xffff
00281a:  ffff  dw      0xffff
00281c:  ffff  dw      0xffff
00281e:  ffff  dw      0xffff
002820:  ffff  dw      0xffff
002822:  ffff  dw      0xffff
002824:  ffff  dw      0xffff
002826:  ffff  dw      0xffff
002828:  ffff  dw      0xffff
00282a:  ffff  dw      0xffff
00282c:  ffff  dw      0xffff
00282e:  ffff  dw      0xffff
002830:  ffff  dw      0xffff
002832:  ffff  dw      0xffff
002834:  ffff  dw      0xffff
002836:  ffff  dw      0xffff
002838:  ffff  dw      0xffff
00283a:  ffff  dw      0xffff
00283c:  ffff  dw      0xffff
00283e:  ffff  dw      0xffff
002840:  ffff  dw      0xffff
002842:  ffff  dw      0xffff
002844:  ffff  dw      0xffff
002846:  ffff  dw      0xffff
002848:  ffff  dw      0xffff
00284a:  ffff  dw      0xffff
00284c:  ffff  dw      0xffff
00284e:  ffff  dw      0xffff
002850:  ffff  dw      0xffff
002852:  ffff  dw      0xffff
002854:  ffff  dw      0xffff
002856:  ffff  dw      0xffff
002858:  ffff  dw      0xffff
00285a:  ffff  dw      0xffff
00285c:  ffff  dw      0xffff
00285e:  ffff  dw      0xffff
002860:  ffff  dw      0xffff
002862:  ffff  dw      0xffff
002864:  ffff  dw      0xffff
002866:  ffff  dw      0xffff
002868:  ffff  dw      0xffff
00286a:  ffff  dw      0xffff
00286c:  ffff  dw      0xffff
00286e:  ffff  dw      0xffff
002870:  ffff  dw      0xffff
002872:  ffff  dw      0xffff
002874:  ffff  dw      0xffff
002876:  ffff  dw      0xffff
002878:  ffff  dw      0xffff
00287a:  ffff  dw      0xffff
00287c:  ffff  dw      0xffff
00287e:  ffff  dw      0xffff
002880:  ffff  dw      0xffff
002882:  ffff  dw      0xffff
002884:  ffff  dw      0xffff
002886:  ffff  dw      0xffff
002888:  ffff  dw      0xffff
00288a:  ffff  dw      0xffff
00288c:  ffff  dw      0xffff
00288e:  ffff  dw      0xffff
002890:  ffff  dw      0xffff
002892:  ffff  dw      0xffff
002894:  ffff  dw      0xffff
002896:  ffff  dw      0xffff
002898:  ffff  dw      0xffff
00289a:  ffff  dw      0xffff
00289c:  ffff  dw      0xffff
00289e:  ffff  dw      0xffff
0028a0:  ffff  dw      0xffff
0028a2:  ffff  dw      0xffff
0028a4:  ffff  dw      0xffff
0028a6:  ffff  dw      0xffff
0028a8:  ffff  dw      0xffff
0028aa:  ffff  dw      0xffff
0028ac:  ffff  dw      0xffff
0028ae:  ffff  dw      0xffff
0028b0:  ffff  dw      0xffff
0028b2:  ffff  dw      0xffff
0028b4:  ffff  dw      0xffff
0028b6:  ffff  dw      0xffff
0028b8:  ffff  dw      0xffff
0028ba:  ffff  dw      0xffff
0028bc:  ffff  dw      0xffff
0028be:  ffff  dw      0xffff
0028c0:  ffff  dw      0xffff
0028c2:  ffff  dw      0xffff
0028c4:  ffff  dw      0xffff
0028c6:  ffff  dw      0xffff
0028c8:  ffff  dw      0xffff
0028ca:  ffff  dw      0xffff
0028cc:  ffff  dw      0xffff
0028ce:  ffff  dw      0xffff
0028d0:  ffff  dw      0xffff
0028d2:  ffff  dw      0xffff
0028d4:  ffff  dw      0xffff
0028d6:  ffff  dw      0xffff
0028d8:  ffff  dw      0xffff
0028da:  ffff  dw      0xffff
0028dc:  ffff  dw      0xffff
0028de:  ffff  dw      0xffff
0028e0:  ffff  dw      0xffff
0028e2:  ffff  dw      0xffff
0028e4:  ffff  dw      0xffff
0028e6:  ffff  dw      0xffff
0028e8:  ffff  dw      0xffff
0028ea:  ffff  dw      0xffff
0028ec:  ffff  dw      0xffff
0028ee:  ffff  dw      0xffff
0028f0:  ffff  dw      0xffff
0028f2:  ffff  dw      0xffff
0028f4:  ffff  dw      0xffff
0028f6:  ffff  dw      0xffff
0028f8:  ffff  dw      0xffff
0028fa:  ffff  dw      0xffff
0028fc:  ffff  dw      0xffff
0028fe:  ffff  dw      0xffff
002900:  ffff  dw      0xffff
002902:  ffff  dw      0xffff
002904:  ffff  dw      0xffff
002906:  ffff  dw      0xffff
002908:  ffff  dw      0xffff
00290a:  ffff  dw      0xffff
00290c:  ffff  dw      0xffff
00290e:  ffff  dw      0xffff
002910:  ffff  dw      0xffff
002912:  ffff  dw      0xffff
002914:  ffff  dw      0xffff
002916:  ffff  dw      0xffff
002918:  ffff  dw      0xffff
00291a:  ffff  dw      0xffff
00291c:  ffff  dw      0xffff
00291e:  ffff  dw      0xffff
002920:  ffff  dw      0xffff
002922:  ffff  dw      0xffff
002924:  ffff  dw      0xffff
002926:  ffff  dw      0xffff
002928:  ffff  dw      0xffff
00292a:  ffff  dw      0xffff
00292c:  ffff  dw      0xffff
00292e:  ffff  dw      0xffff
002930:  ffff  dw      0xffff
002932:  ffff  dw      0xffff
002934:  ffff  dw      0xffff
002936:  ffff  dw      0xffff
002938:  ffff  dw      0xffff
00293a:  ffff  dw      0xffff
00293c:  ffff  dw      0xffff
00293e:  ffff  dw      0xffff
002940:  ffff  dw      0xffff
002942:  ffff  dw      0xffff
002944:  ffff  dw      0xffff
002946:  ffff  dw      0xffff
002948:  ffff  dw      0xffff
00294a:  ffff  dw      0xffff
00294c:  ffff  dw      0xffff
00294e:  ffff  dw      0xffff
002950:  ffff  dw      0xffff
002952:  ffff  dw      0xffff
002954:  ffff  dw      0xffff
002956:  ffff  dw      0xffff
002958:  ffff  dw      0xffff
00295a:  ffff  dw      0xffff
00295c:  ffff  dw      0xffff
00295e:  ffff  dw      0xffff
002960:  ffff  dw      0xffff
002962:  ffff  dw      0xffff
002964:  ffff  dw      0xffff
002966:  ffff  dw      0xffff
002968:  ffff  dw      0xffff
00296a:  ffff  dw      0xffff
00296c:  ffff  dw      0xffff
00296e:  ffff  dw      0xffff
002970:  ffff  dw      0xffff
002972:  ffff  dw      0xffff
002974:  ffff  dw      0xffff
002976:  ffff  dw      0xffff
002978:  ffff  dw      0xffff
00297a:  ffff  dw      0xffff
00297c:  ffff  dw      0xffff
00297e:  ffff  dw      0xffff
002980:  ffff  dw      0xffff
002982:  ffff  dw      0xffff
002984:  ffff  dw      0xffff
002986:  ffff  dw      0xffff
002988:  ffff  dw      0xffff
00298a:  ffff  dw      0xffff
00298c:  ffff  dw      0xffff
00298e:  ffff  dw      0xffff
002990:  ffff  dw      0xffff
002992:  ffff  dw      0xffff
002994:  ffff  dw      0xffff
002996:  ffff  dw      0xffff
002998:  ffff  dw      0xffff
00299a:  ffff  dw      0xffff
00299c:  ffff  dw      0xffff
00299e:  ffff  dw      0xffff
0029a0:  ffff  dw      0xffff
0029a2:  ffff  dw      0xffff
0029a4:  ffff  dw      0xffff
0029a6:  ffff  dw      0xffff
0029a8:  ffff  dw      0xffff
0029aa:  ffff  dw      0xffff
0029ac:  ffff  dw      0xffff
0029ae:  ffff  dw      0xffff
0029b0:  ffff  dw      0xffff
0029b2:  ffff  dw      0xffff
0029b4:  ffff  dw      0xffff
0029b6:  ffff  dw      0xffff
0029b8:  ffff  dw      0xffff
0029ba:  ffff  dw      0xffff
0029bc:  ffff  dw      0xffff
0029be:  ffff  dw      0xffff
0029c0:  ffff  dw      0xffff
0029c2:  ffff  dw      0xffff
0029c4:  ffff  dw      0xffff
0029c6:  ffff  dw      0xffff
0029c8:  ffff  dw      0xffff
0029ca:  ffff  dw      0xffff
0029cc:  ffff  dw      0xffff
0029ce:  ffff  dw      0xffff
0029d0:  ffff  dw      0xffff
0029d2:  ffff  dw      0xffff
0029d4:  ffff  dw      0xffff
0029d6:  ffff  dw      0xffff
0029d8:  ffff  dw      0xffff
0029da:  ffff  dw      0xffff
0029dc:  ffff  dw      0xffff
0029de:  ffff  dw      0xffff
0029e0:  ffff  dw      0xffff
0029e2:  ffff  dw      0xffff
0029e4:  ffff  dw      0xffff
0029e6:  ffff  dw      0xffff
0029e8:  ffff  dw      0xffff
0029ea:  ffff  dw      0xffff
0029ec:  ffff  dw      0xffff
0029ee:  ffff  dw      0xffff
0029f0:  ffff  dw      0xffff
0029f2:  ffff  dw      0xffff
0029f4:  ffff  dw      0xffff
0029f6:  ffff  dw      0xffff
0029f8:  ffff  dw      0xffff
0029fa:  ffff  dw      0xffff
0029fc:  ffff  dw      0xffff
0029fe:  ffff  dw      0xffff
002a00:  ffff  dw      0xffff
002a02:  ffff  dw      0xffff
002a04:  ffff  dw      0xffff
002a06:  ffff  dw      0xffff
002a08:  ffff  dw      0xffff
002a0a:  ffff  dw      0xffff
002a0c:  ffff  dw      0xffff
002a0e:  ffff  dw      0xffff
002a10:  ffff  dw      0xffff
002a12:  ffff  dw      0xffff
002a14:  ffff  dw      0xffff
002a16:  ffff  dw      0xffff
002a18:  ffff  dw      0xffff
002a1a:  ffff  dw      0xffff
002a1c:  ffff  dw      0xffff
002a1e:  ffff  dw      0xffff
002a20:  ffff  dw      0xffff
002a22:  ffff  dw      0xffff
002a24:  ffff  dw      0xffff
002a26:  ffff  dw      0xffff
002a28:  ffff  dw      0xffff
002a2a:  ffff  dw      0xffff
002a2c:  ffff  dw      0xffff
002a2e:  ffff  dw      0xffff
002a30:  ffff  dw      0xffff
002a32:  ffff  dw      0xffff
002a34:  ffff  dw      0xffff
002a36:  ffff  dw      0xffff
002a38:  ffff  dw      0xffff
002a3a:  ffff  dw      0xffff
002a3c:  ffff  dw      0xffff
002a3e:  ffff  dw      0xffff
002a40:  ffff  dw      0xffff
002a42:  ffff  dw      0xffff
002a44:  ffff  dw      0xffff
002a46:  ffff  dw      0xffff
002a48:  ffff  dw      0xffff
002a4a:  ffff  dw      0xffff
002a4c:  ffff  dw      0xffff
002a4e:  ffff  dw      0xffff
002a50:  ffff  dw      0xffff
002a52:  ffff  dw      0xffff
002a54:  ffff  dw      0xffff
002a56:  ffff  dw      0xffff
002a58:  ffff  dw      0xffff
002a5a:  ffff  dw      0xffff
002a5c:  ffff  dw      0xffff
002a5e:  ffff  dw      0xffff
002a60:  ffff  dw      0xffff
002a62:  ffff  dw      0xffff
002a64:  ffff  dw      0xffff
002a66:  ffff  dw      0xffff
002a68:  ffff  dw      0xffff
002a6a:  ffff  dw      0xffff
002a6c:  ffff  dw      0xffff
002a6e:  ffff  dw      0xffff
002a70:  ffff  dw      0xffff
002a72:  ffff  dw      0xffff
002a74:  ffff  dw      0xffff
002a76:  ffff  dw      0xffff
002a78:  ffff  dw      0xffff
002a7a:  ffff  dw      0xffff
002a7c:  ffff  dw      0xffff
002a7e:  ffff  dw      0xffff
002a80:  ffff  dw      0xffff
002a82:  ffff  dw      0xffff
002a84:  ffff  dw      0xffff
002a86:  ffff  dw      0xffff
002a88:  ffff  dw      0xffff
002a8a:  ffff  dw      0xffff
002a8c:  ffff  dw      0xffff
002a8e:  ffff  dw      0xffff
002a90:  ffff  dw      0xffff
002a92:  ffff  dw      0xffff
002a94:  ffff  dw      0xffff
002a96:  ffff  dw      0xffff
002a98:  ffff  dw      0xffff
002a9a:  ffff  dw      0xffff
002a9c:  ffff  dw      0xffff
002a9e:  ffff  dw      0xffff
002aa0:  ffff  dw      0xffff
002aa2:  ffff  dw      0xffff
002aa4:  ffff  dw      0xffff
002aa6:  ffff  dw      0xffff
002aa8:  ffff  dw      0xffff
002aaa:  ffff  dw      0xffff
002aac:  ffff  dw      0xffff
002aae:  ffff  dw      0xffff
002ab0:  ffff  dw      0xffff
002ab2:  ffff  dw      0xffff
002ab4:  ffff  dw      0xffff
002ab6:  ffff  dw      0xffff
002ab8:  ffff  dw      0xffff
002aba:  ffff  dw      0xffff
002abc:  ffff  dw      0xffff
002abe:  ffff  dw      0xffff
002ac0:  ffff  dw      0xffff
002ac2:  ffff  dw      0xffff
002ac4:  ffff  dw      0xffff
002ac6:  ffff  dw      0xffff
002ac8:  ffff  dw      0xffff
002aca:  ffff  dw      0xffff
002acc:  ffff  dw      0xffff
002ace:  ffff  dw      0xffff
002ad0:  ffff  dw      0xffff
002ad2:  ffff  dw      0xffff
002ad4:  ffff  dw      0xffff
002ad6:  ffff  dw      0xffff
002ad8:  ffff  dw      0xffff
002ada:  ffff  dw      0xffff
002adc:  ffff  dw      0xffff
002ade:  ffff  dw      0xffff
002ae0:  ffff  dw      0xffff
002ae2:  ffff  dw      0xffff
002ae4:  ffff  dw      0xffff
002ae6:  ffff  dw      0xffff
002ae8:  ffff  dw      0xffff
002aea:  ffff  dw      0xffff
002aec:  ffff  dw      0xffff
002aee:  ffff  dw      0xffff
002af0:  ffff  dw      0xffff
002af2:  ffff  dw      0xffff
002af4:  ffff  dw      0xffff
002af6:  ffff  dw      0xffff
002af8:  ffff  dw      0xffff
002afa:  ffff  dw      0xffff
002afc:  ffff  dw      0xffff
002afe:  ffff  dw      0xffff
002b00:  ffff  dw      0xffff
002b02:  ffff  dw      0xffff
002b04:  ffff  dw      0xffff
002b06:  ffff  dw      0xffff
002b08:  ffff  dw      0xffff
002b0a:  ffff  dw      0xffff
002b0c:  ffff  dw      0xffff
002b0e:  ffff  dw      0xffff
002b10:  ffff  dw      0xffff
002b12:  ffff  dw      0xffff
002b14:  ffff  dw      0xffff
002b16:  ffff  dw      0xffff
002b18:  ffff  dw      0xffff
002b1a:  ffff  dw      0xffff
002b1c:  ffff  dw      0xffff
002b1e:  ffff  dw      0xffff
002b20:  ffff  dw      0xffff
002b22:  ffff  dw      0xffff
002b24:  ffff  dw      0xffff
002b26:  ffff  dw      0xffff
002b28:  ffff  dw      0xffff
002b2a:  ffff  dw      0xffff
002b2c:  ffff  dw      0xffff
002b2e:  ffff  dw      0xffff
002b30:  ffff  dw      0xffff
002b32:  ffff  dw      0xffff
002b34:  ffff  dw      0xffff
002b36:  ffff  dw      0xffff
002b38:  ffff  dw      0xffff
002b3a:  ffff  dw      0xffff
002b3c:  ffff  dw      0xffff
002b3e:  ffff  dw      0xffff
002b40:  ffff  dw      0xffff
002b42:  ffff  dw      0xffff
002b44:  ffff  dw      0xffff
002b46:  ffff  dw      0xffff
002b48:  ffff  dw      0xffff
002b4a:  ffff  dw      0xffff
002b4c:  ffff  dw      0xffff
002b4e:  ffff  dw      0xffff
002b50:  ffff  dw      0xffff
002b52:  ffff  dw      0xffff
002b54:  ffff  dw      0xffff
002b56:  ffff  dw      0xffff
002b58:  ffff  dw      0xffff
002b5a:  ffff  dw      0xffff
002b5c:  ffff  dw      0xffff
002b5e:  ffff  dw      0xffff
002b60:  ffff  dw      0xffff
002b62:  ffff  dw      0xffff
002b64:  ffff  dw      0xffff
002b66:  ffff  dw      0xffff
002b68:  ffff  dw      0xffff
002b6a:  ffff  dw      0xffff
002b6c:  ffff  dw      0xffff
002b6e:  ffff  dw      0xffff
002b70:  ffff  dw      0xffff
002b72:  ffff  dw      0xffff
002b74:  ffff  dw      0xffff
002b76:  ffff  dw      0xffff
002b78:  ffff  dw      0xffff
002b7a:  ffff  dw      0xffff
002b7c:  ffff  dw      0xffff
002b7e:  ffff  dw      0xffff
002b80:  ffff  dw      0xffff
002b82:  ffff  dw      0xffff
002b84:  ffff  dw      0xffff
002b86:  ffff  dw      0xffff
002b88:  ffff  dw      0xffff
002b8a:  ffff  dw      0xffff
002b8c:  ffff  dw      0xffff
002b8e:  ffff  dw      0xffff
002b90:  ffff  dw      0xffff
002b92:  ffff  dw      0xffff
002b94:  ffff  dw      0xffff
002b96:  ffff  dw      0xffff
002b98:  ffff  dw      0xffff
002b9a:  ffff  dw      0xffff
002b9c:  ffff  dw      0xffff
002b9e:  ffff  dw      0xffff
002ba0:  ffff  dw      0xffff
002ba2:  ffff  dw      0xffff
002ba4:  ffff  dw      0xffff
002ba6:  ffff  dw      0xffff
002ba8:  ffff  dw      0xffff
002baa:  ffff  dw      0xffff
002bac:  ffff  dw      0xffff
002bae:  ffff  dw      0xffff
002bb0:  ffff  dw      0xffff
002bb2:  ffff  dw      0xffff
002bb4:  ffff  dw      0xffff
002bb6:  ffff  dw      0xffff
002bb8:  ffff  dw      0xffff
002bba:  ffff  dw      0xffff
002bbc:  ffff  dw      0xffff
002bbe:  ffff  dw      0xffff
002bc0:  ffff  dw      0xffff
002bc2:  ffff  dw      0xffff
002bc4:  ffff  dw      0xffff
002bc6:  ffff  dw      0xffff
002bc8:  ffff  dw      0xffff
002bca:  ffff  dw      0xffff
002bcc:  ffff  dw      0xffff
002bce:  ffff  dw      0xffff
002bd0:  ffff  dw      0xffff
002bd2:  ffff  dw      0xffff
002bd4:  ffff  dw      0xffff
002bd6:  ffff  dw      0xffff
002bd8:  ffff  dw      0xffff
002bda:  ffff  dw      0xffff
002bdc:  ffff  dw      0xffff
002bde:  ffff  dw      0xffff
002be0:  ffff  dw      0xffff
002be2:  ffff  dw      0xffff
002be4:  ffff  dw      0xffff
002be6:  ffff  dw      0xffff
002be8:  ffff  dw      0xffff
002bea:  ffff  dw      0xffff
002bec:  ffff  dw      0xffff
002bee:  ffff  dw      0xffff
002bf0:  ffff  dw      0xffff
002bf2:  ffff  dw      0xffff
002bf4:  ffff  dw      0xffff
002bf6:  ffff  dw      0xffff
002bf8:  ffff  dw      0xffff
002bfa:  ffff  dw      0xffff
002bfc:  ffff  dw      0xffff
002bfe:  ffff  dw      0xffff
002c00:  ffff  dw      0xffff
002c02:  ffff  dw      0xffff
002c04:  ffff  dw      0xffff
002c06:  ffff  dw      0xffff
002c08:  ffff  dw      0xffff
002c0a:  ffff  dw      0xffff
002c0c:  ffff  dw      0xffff
002c0e:  ffff  dw      0xffff
002c10:  ffff  dw      0xffff
002c12:  ffff  dw      0xffff
002c14:  ffff  dw      0xffff
002c16:  ffff  dw      0xffff
002c18:  ffff  dw      0xffff
002c1a:  ffff  dw      0xffff
002c1c:  ffff  dw      0xffff
002c1e:  ffff  dw      0xffff
002c20:  ffff  dw      0xffff
002c22:  ffff  dw      0xffff
002c24:  ffff  dw      0xffff
002c26:  ffff  dw      0xffff
002c28:  ffff  dw      0xffff
002c2a:  ffff  dw      0xffff
002c2c:  ffff  dw      0xffff
002c2e:  ffff  dw      0xffff
002c30:  ffff  dw      0xffff
002c32:  ffff  dw      0xffff
002c34:  ffff  dw      0xffff
002c36:  ffff  dw      0xffff
002c38:  ffff  dw      0xffff
002c3a:  ffff  dw      0xffff
002c3c:  ffff  dw      0xffff
002c3e:  ffff  dw      0xffff
002c40:  ffff  dw      0xffff
002c42:  ffff  dw      0xffff
002c44:  ffff  dw      0xffff
002c46:  ffff  dw      0xffff
002c48:  ffff  dw      0xffff
002c4a:  ffff  dw      0xffff
002c4c:  ffff  dw      0xffff
002c4e:  ffff  dw      0xffff
002c50:  ffff  dw      0xffff
002c52:  ffff  dw      0xffff
002c54:  ffff  dw      0xffff
002c56:  ffff  dw      0xffff
002c58:  ffff  dw      0xffff
002c5a:  ffff  dw      0xffff
002c5c:  ffff  dw      0xffff
002c5e:  ffff  dw      0xffff
002c60:  ffff  dw      0xffff
002c62:  ffff  dw      0xffff
002c64:  ffff  dw      0xffff
002c66:  ffff  dw      0xffff
002c68:  ffff  dw      0xffff
002c6a:  ffff  dw      0xffff
002c6c:  ffff  dw      0xffff
002c6e:  ffff  dw      0xffff
002c70:  ffff  dw      0xffff
002c72:  ffff  dw      0xffff
002c74:  ffff  dw      0xffff
002c76:  ffff  dw      0xffff
002c78:  ffff  dw      0xffff
002c7a:  ffff  dw      0xffff
002c7c:  ffff  dw      0xffff
002c7e:  ffff  dw      0xffff
002c80:  ffff  dw      0xffff
002c82:  ffff  dw      0xffff
002c84:  ffff  dw      0xffff
002c86:  ffff  dw      0xffff
002c88:  ffff  dw      0xffff
002c8a:  ffff  dw      0xffff
002c8c:  ffff  dw      0xffff
002c8e:  ffff  dw      0xffff
002c90:  ffff  dw      0xffff
002c92:  ffff  dw      0xffff
002c94:  ffff  dw      0xffff
002c96:  ffff  dw      0xffff
002c98:  ffff  dw      0xffff
002c9a:  ffff  dw      0xffff
002c9c:  ffff  dw      0xffff
002c9e:  ffff  dw      0xffff
002ca0:  ffff  dw      0xffff
002ca2:  ffff  dw      0xffff
002ca4:  ffff  dw      0xffff
002ca6:  ffff  dw      0xffff
002ca8:  ffff  dw      0xffff
002caa:  ffff  dw      0xffff
002cac:  ffff  dw      0xffff
002cae:  ffff  dw      0xffff
002cb0:  ffff  dw      0xffff
002cb2:  ffff  dw      0xffff
002cb4:  ffff  dw      0xffff
002cb6:  ffff  dw      0xffff
002cb8:  ffff  dw      0xffff
002cba:  ffff  dw      0xffff
002cbc:  ffff  dw      0xffff
002cbe:  ffff  dw      0xffff
002cc0:  ffff  dw      0xffff
002cc2:  ffff  dw      0xffff
002cc4:  ffff  dw      0xffff
002cc6:  ffff  dw      0xffff
002cc8:  ffff  dw      0xffff
002cca:  ffff  dw      0xffff
002ccc:  ffff  dw      0xffff
002cce:  ffff  dw      0xffff
002cd0:  ffff  dw      0xffff
002cd2:  ffff  dw      0xffff
002cd4:  ffff  dw      0xffff
002cd6:  ffff  dw      0xffff
002cd8:  ffff  dw      0xffff
002cda:  ffff  dw      0xffff
002cdc:  ffff  dw      0xffff
002cde:  ffff  dw      0xffff
002ce0:  ffff  dw      0xffff
002ce2:  ffff  dw      0xffff
002ce4:  ffff  dw      0xffff
002ce6:  ffff  dw      0xffff
002ce8:  ffff  dw      0xffff
002cea:  ffff  dw      0xffff
002cec:  ffff  dw      0xffff
002cee:  ffff  dw      0xffff
002cf0:  ffff  dw      0xffff
002cf2:  ffff  dw      0xffff
002cf4:  ffff  dw      0xffff
002cf6:  ffff  dw      0xffff
002cf8:  ffff  dw      0xffff
002cfa:  ffff  dw      0xffff
002cfc:  ffff  dw      0xffff
002cfe:  ffff  dw      0xffff
002d00:  ffff  dw      0xffff
002d02:  ffff  dw      0xffff
002d04:  ffff  dw      0xffff
002d06:  ffff  dw      0xffff
002d08:  ffff  dw      0xffff
002d0a:  ffff  dw      0xffff
002d0c:  ffff  dw      0xffff
002d0e:  ffff  dw      0xffff
002d10:  ffff  dw      0xffff
002d12:  ffff  dw      0xffff
002d14:  ffff  dw      0xffff
002d16:  ffff  dw      0xffff
002d18:  ffff  dw      0xffff
002d1a:  ffff  dw      0xffff
002d1c:  ffff  dw      0xffff
002d1e:  ffff  dw      0xffff
002d20:  ffff  dw      0xffff
002d22:  ffff  dw      0xffff
002d24:  ffff  dw      0xffff
002d26:  ffff  dw      0xffff
002d28:  ffff  dw      0xffff
002d2a:  ffff  dw      0xffff
002d2c:  ffff  dw      0xffff
002d2e:  ffff  dw      0xffff
002d30:  ffff  dw      0xffff
002d32:  ffff  dw      0xffff
002d34:  ffff  dw      0xffff
002d36:  ffff  dw      0xffff
002d38:  ffff  dw      0xffff
002d3a:  ffff  dw      0xffff
002d3c:  ffff  dw      0xffff
002d3e:  ffff  dw      0xffff
002d40:  ffff  dw      0xffff
002d42:  ffff  dw      0xffff
002d44:  ffff  dw      0xffff
002d46:  ffff  dw      0xffff
002d48:  ffff  dw      0xffff
002d4a:  ffff  dw      0xffff
002d4c:  ffff  dw      0xffff
002d4e:  ffff  dw      0xffff
002d50:  ffff  dw      0xffff
002d52:  ffff  dw      0xffff
002d54:  ffff  dw      0xffff
002d56:  ffff  dw      0xffff
002d58:  ffff  dw      0xffff
002d5a:  ffff  dw      0xffff
002d5c:  ffff  dw      0xffff
002d5e:  ffff  dw      0xffff
002d60:  ffff  dw      0xffff
002d62:  ffff  dw      0xffff
002d64:  ffff  dw      0xffff
002d66:  ffff  dw      0xffff
002d68:  ffff  dw      0xffff
002d6a:  ffff  dw      0xffff
002d6c:  ffff  dw      0xffff
002d6e:  ffff  dw      0xffff
002d70:  ffff  dw      0xffff
002d72:  ffff  dw      0xffff
002d74:  ffff  dw      0xffff
002d76:  ffff  dw      0xffff
002d78:  ffff  dw      0xffff
002d7a:  ffff  dw      0xffff
002d7c:  ffff  dw      0xffff
002d7e:  ffff  dw      0xffff
002d80:  ffff  dw      0xffff
002d82:  ffff  dw      0xffff
002d84:  ffff  dw      0xffff
002d86:  ffff  dw      0xffff
002d88:  ffff  dw      0xffff
002d8a:  ffff  dw      0xffff
002d8c:  ffff  dw      0xffff
002d8e:  ffff  dw      0xffff
002d90:  ffff  dw      0xffff
002d92:  ffff  dw      0xffff
002d94:  ffff  dw      0xffff
002d96:  ffff  dw      0xffff
002d98:  ffff  dw      0xffff
002d9a:  ffff  dw      0xffff
002d9c:  ffff  dw      0xffff
002d9e:  ffff  dw      0xffff
002da0:  ffff  dw      0xffff
002da2:  ffff  dw      0xffff
002da4:  ffff  dw      0xffff
002da6:  ffff  dw      0xffff
002da8:  ffff  dw      0xffff
002daa:  ffff  dw      0xffff
002dac:  ffff  dw      0xffff
002dae:  ffff  dw      0xffff
002db0:  ffff  dw      0xffff
002db2:  ffff  dw      0xffff
002db4:  ffff  dw      0xffff
002db6:  ffff  dw      0xffff
002db8:  ffff  dw      0xffff
002dba:  ffff  dw      0xffff
002dbc:  ffff  dw      0xffff
002dbe:  ffff  dw      0xffff
002dc0:  ffff  dw      0xffff
002dc2:  ffff  dw      0xffff
002dc4:  ffff  dw      0xffff
002dc6:  ffff  dw      0xffff
002dc8:  ffff  dw      0xffff
002dca:  ffff  dw      0xffff
002dcc:  ffff  dw      0xffff
002dce:  ffff  dw      0xffff
002dd0:  ffff  dw      0xffff
002dd2:  ffff  dw      0xffff
002dd4:  ffff  dw      0xffff
002dd6:  ffff  dw      0xffff
002dd8:  ffff  dw      0xffff
002dda:  ffff  dw      0xffff
002ddc:  ffff  dw      0xffff
002dde:  ffff  dw      0xffff
002de0:  ffff  dw      0xffff
002de2:  ffff  dw      0xffff
002de4:  ffff  dw      0xffff
002de6:  ffff  dw      0xffff
002de8:  ffff  dw      0xffff
002dea:  ffff  dw      0xffff
002dec:  ffff  dw      0xffff
002dee:  ffff  dw      0xffff
002df0:  ffff  dw      0xffff
002df2:  ffff  dw      0xffff
002df4:  ffff  dw      0xffff
002df6:  ffff  dw      0xffff
002df8:  ffff  dw      0xffff
002dfa:  ffff  dw      0xffff
002dfc:  ffff  dw      0xffff
002dfe:  ffff  dw      0xffff
002e00:  ffff  dw      0xffff
002e02:  ffff  dw      0xffff
002e04:  ffff  dw      0xffff
002e06:  ffff  dw      0xffff
002e08:  ffff  dw      0xffff
002e0a:  ffff  dw      0xffff
002e0c:  ffff  dw      0xffff
002e0e:  ffff  dw      0xffff
002e10:  ffff  dw      0xffff
002e12:  ffff  dw      0xffff
002e14:  ffff  dw      0xffff
002e16:  ffff  dw      0xffff
002e18:  ffff  dw      0xffff
002e1a:  ffff  dw      0xffff
002e1c:  ffff  dw      0xffff
002e1e:  ffff  dw      0xffff
002e20:  ffff  dw      0xffff
002e22:  ffff  dw      0xffff
002e24:  ffff  dw      0xffff
002e26:  ffff  dw      0xffff
002e28:  ffff  dw      0xffff
002e2a:  ffff  dw      0xffff
002e2c:  ffff  dw      0xffff
002e2e:  ffff  dw      0xffff
002e30:  ffff  dw      0xffff
002e32:  ffff  dw      0xffff
002e34:  ffff  dw      0xffff
002e36:  ffff  dw      0xffff
002e38:  ffff  dw      0xffff
002e3a:  ffff  dw      0xffff
002e3c:  ffff  dw      0xffff
002e3e:  ffff  dw      0xffff
002e40:  ffff  dw      0xffff
002e42:  ffff  dw      0xffff
002e44:  ffff  dw      0xffff
002e46:  ffff  dw      0xffff
002e48:  ffff  dw      0xffff
002e4a:  ffff  dw      0xffff
002e4c:  ffff  dw      0xffff
002e4e:  ffff  dw      0xffff
002e50:  ffff  dw      0xffff
002e52:  ffff  dw      0xffff
002e54:  ffff  dw      0xffff
002e56:  ffff  dw      0xffff
002e58:  ffff  dw      0xffff
002e5a:  ffff  dw      0xffff
002e5c:  ffff  dw      0xffff
002e5e:  ffff  dw      0xffff
002e60:  ffff  dw      0xffff
002e62:  ffff  dw      0xffff
002e64:  ffff  dw      0xffff
002e66:  ffff  dw      0xffff
002e68:  ffff  dw      0xffff
002e6a:  ffff  dw      0xffff
002e6c:  ffff  dw      0xffff
002e6e:  ffff  dw      0xffff
002e70:  ffff  dw      0xffff
002e72:  ffff  dw      0xffff
002e74:  ffff  dw      0xffff
002e76:  ffff  dw      0xffff
002e78:  ffff  dw      0xffff
002e7a:  ffff  dw      0xffff
002e7c:  ffff  dw      0xffff
002e7e:  ffff  dw      0xffff
002e80:  ffff  dw      0xffff
002e82:  ffff  dw      0xffff
002e84:  ffff  dw      0xffff
002e86:  ffff  dw      0xffff
002e88:  ffff  dw      0xffff
002e8a:  ffff  dw      0xffff
002e8c:  ffff  dw      0xffff
002e8e:  ffff  dw      0xffff
002e90:  ffff  dw      0xffff
002e92:  ffff  dw      0xffff
002e94:  ffff  dw      0xffff
002e96:  ffff  dw      0xffff
002e98:  ffff  dw      0xffff
002e9a:  ffff  dw      0xffff
002e9c:  ffff  dw      0xffff
002e9e:  ffff  dw      0xffff
002ea0:  ffff  dw      0xffff
002ea2:  ffff  dw      0xffff
002ea4:  ffff  dw      0xffff
002ea6:  ffff  dw      0xffff
002ea8:  ffff  dw      0xffff
002eaa:  ffff  dw      0xffff
002eac:  ffff  dw      0xffff
002eae:  ffff  dw      0xffff
002eb0:  ffff  dw      0xffff
002eb2:  ffff  dw      0xffff
002eb4:  ffff  dw      0xffff
002eb6:  ffff  dw      0xffff
002eb8:  ffff  dw      0xffff
002eba:  ffff  dw      0xffff
002ebc:  ffff  dw      0xffff
002ebe:  ffff  dw      0xffff
002ec0:  ffff  dw      0xffff
002ec2:  ffff  dw      0xffff
002ec4:  ffff  dw      0xffff
002ec6:  ffff  dw      0xffff
002ec8:  ffff  dw      0xffff
002eca:  ffff  dw      0xffff
002ecc:  ffff  dw      0xffff
002ece:  ffff  dw      0xffff
002ed0:  ffff  dw      0xffff
002ed2:  ffff  dw      0xffff
002ed4:  ffff  dw      0xffff
002ed6:  ffff  dw      0xffff
002ed8:  ffff  dw      0xffff
002eda:  ffff  dw      0xffff
002edc:  ffff  dw      0xffff
002ede:  ffff  dw      0xffff
002ee0:  ffff  dw      0xffff
002ee2:  ffff  dw      0xffff
002ee4:  ffff  dw      0xffff
002ee6:  ffff  dw      0xffff
002ee8:  ffff  dw      0xffff
002eea:  ffff  dw      0xffff
002eec:  ffff  dw      0xffff
002eee:  ffff  dw      0xffff
002ef0:  ffff  dw      0xffff
002ef2:  ffff  dw      0xffff
002ef4:  ffff  dw      0xffff
002ef6:  ffff  dw      0xffff
002ef8:  ffff  dw      0xffff
002efa:  ffff  dw      0xffff
002efc:  ffff  dw      0xffff
002efe:  ffff  dw      0xffff
002f00:  ffff  dw      0xffff
002f02:  ffff  dw      0xffff
002f04:  ffff  dw      0xffff
002f06:  ffff  dw      0xffff
002f08:  ffff  dw      0xffff
002f0a:  ffff  dw      0xffff
002f0c:  ffff  dw      0xffff
002f0e:  ffff  dw      0xffff
002f10:  ffff  dw      0xffff
002f12:  ffff  dw      0xffff
002f14:  ffff  dw      0xffff
002f16:  ffff  dw      0xffff
002f18:  ffff  dw      0xffff
002f1a:  ffff  dw      0xffff
002f1c:  ffff  dw      0xffff
002f1e:  ffff  dw      0xffff
002f20:  ffff  dw      0xffff
002f22:  ffff  dw      0xffff
002f24:  ffff  dw      0xffff
002f26:  ffff  dw      0xffff
002f28:  ffff  dw      0xffff
002f2a:  ffff  dw      0xffff
002f2c:  ffff  dw      0xffff
002f2e:  ffff  dw      0xffff
002f30:  ffff  dw      0xffff
002f32:  ffff  dw      0xffff
002f34:  ffff  dw      0xffff
002f36:  ffff  dw      0xffff
002f38:  ffff  dw      0xffff
002f3a:  ffff  dw      0xffff
002f3c:  ffff  dw      0xffff
002f3e:  ffff  dw      0xffff
002f40:  ffff  dw      0xffff
002f42:  ffff  dw      0xffff
002f44:  ffff  dw      0xffff
002f46:  ffff  dw      0xffff
002f48:  ffff  dw      0xffff
002f4a:  ffff  dw      0xffff
002f4c:  ffff  dw      0xffff
002f4e:  ffff  dw      0xffff
002f50:  ffff  dw      0xffff
002f52:  ffff  dw      0xffff
002f54:  ffff  dw      0xffff
002f56:  ffff  dw      0xffff
002f58:  ffff  dw      0xffff
002f5a:  ffff  dw      0xffff
002f5c:  ffff  dw      0xffff
002f5e:  ffff  dw      0xffff
002f60:  ffff  dw      0xffff
002f62:  ffff  dw      0xffff
002f64:  ffff  dw      0xffff
002f66:  ffff  dw      0xffff
002f68:  ffff  dw      0xffff
002f6a:  ffff  dw      0xffff
002f6c:  ffff  dw      0xffff
002f6e:  ffff  dw      0xffff
002f70:  ffff  dw      0xffff
002f72:  ffff  dw      0xffff
002f74:  ffff  dw      0xffff
002f76:  ffff  dw      0xffff
002f78:  ffff  dw      0xffff
002f7a:  ffff  dw      0xffff
002f7c:  ffff  dw      0xffff
002f7e:  ffff  dw      0xffff
002f80:  ffff  dw      0xffff
002f82:  ffff  dw      0xffff
002f84:  ffff  dw      0xffff
002f86:  ffff  dw      0xffff
002f88:  ffff  dw      0xffff
002f8a:  ffff  dw      0xffff
002f8c:  ffff  dw      0xffff
002f8e:  ffff  dw      0xffff
002f90:  ffff  dw      0xffff
002f92:  ffff  dw      0xffff
002f94:  ffff  dw      0xffff
002f96:  ffff  dw      0xffff
002f98:  ffff  dw      0xffff
002f9a:  ffff  dw      0xffff
002f9c:  ffff  dw      0xffff
002f9e:  ffff  dw      0xffff
002fa0:  ffff  dw      0xffff
002fa2:  ffff  dw      0xffff
002fa4:  ffff  dw      0xffff
002fa6:  ffff  dw      0xffff
002fa8:  ffff  dw      0xffff
002faa:  ffff  dw      0xffff
002fac:  ffff  dw      0xffff
002fae:  ffff  dw      0xffff
002fb0:  ffff  dw      0xffff
002fb2:  ffff  dw      0xffff
002fb4:  ffff  dw      0xffff
002fb6:  ffff  dw      0xffff
002fb8:  ffff  dw      0xffff
002fba:  ffff  dw      0xffff
002fbc:  ffff  dw      0xffff
002fbe:  ffff  dw      0xffff
002fc0:  ffff  dw      0xffff
002fc2:  ffff  dw      0xffff
002fc4:  ffff  dw      0xffff
002fc6:  ffff  dw      0xffff
002fc8:  ffff  dw      0xffff
002fca:  ffff  dw      0xffff
002fcc:  ffff  dw      0xffff
002fce:  ffff  dw      0xffff
002fd0:  ffff  dw      0xffff
002fd2:  ffff  dw      0xffff
002fd4:  ffff  dw      0xffff
002fd6:  ffff  dw      0xffff
002fd8:  ffff  dw      0xffff
002fda:  ffff  dw      0xffff
002fdc:  ffff  dw      0xffff
002fde:  ffff  dw      0xffff
002fe0:  ffff  dw      0xffff
002fe2:  ffff  dw      0xffff
002fe4:  ffff  dw      0xffff
002fe6:  ffff  dw      0xffff
002fe8:  ffff  dw      0xffff
002fea:  ffff  dw      0xffff
002fec:  ffff  dw      0xffff
002fee:  ffff  dw      0xffff
002ff0:  ffff  dw      0xffff
002ff2:  ffff  dw      0xffff
002ff4:  ffff  dw      0xffff
002ff6:  ffff  dw      0xffff
002ff8:  ffff  dw      0xffff
002ffa:  ffff  dw      0xffff
002ffc:  ffff  dw      0xffff
002ffe:  ffff  dw      0xffff
003000:  ffff  dw      0xffff
003002:  ffff  dw      0xffff
003004:  ffff  dw      0xffff
003006:  ffff  dw      0xffff
003008:  ffff  dw      0xffff
00300a:  ffff  dw      0xffff
00300c:  ffff  dw      0xffff
00300e:  ffff  dw      0xffff
003010:  ffff  dw      0xffff
003012:  ffff  dw      0xffff
003014:  ffff  dw      0xffff
003016:  ffff  dw      0xffff
003018:  ffff  dw      0xffff
00301a:  ffff  dw      0xffff
00301c:  ffff  dw      0xffff
00301e:  ffff  dw      0xffff
003020:  ffff  dw      0xffff
003022:  ffff  dw      0xffff
003024:  ffff  dw      0xffff
003026:  ffff  dw      0xffff
003028:  ffff  dw      0xffff
00302a:  ffff  dw      0xffff
00302c:  ffff  dw      0xffff
00302e:  ffff  dw      0xffff
003030:  ffff  dw      0xffff
003032:  ffff  dw      0xffff
003034:  ffff  dw      0xffff
003036:  ffff  dw      0xffff
003038:  ffff  dw      0xffff
00303a:  ffff  dw      0xffff
00303c:  ffff  dw      0xffff
00303e:  ffff  dw      0xffff
003040:  ffff  dw      0xffff
003042:  ffff  dw      0xffff
003044:  ffff  dw      0xffff
003046:  ffff  dw      0xffff
003048:  ffff  dw      0xffff
00304a:  ffff  dw      0xffff
00304c:  ffff  dw      0xffff
00304e:  ffff  dw      0xffff
003050:  ffff  dw      0xffff
003052:  ffff  dw      0xffff
003054:  ffff  dw      0xffff
003056:  ffff  dw      0xffff
003058:  ffff  dw      0xffff
00305a:  ffff  dw      0xffff
00305c:  ffff  dw      0xffff
00305e:  ffff  dw      0xffff
003060:  ffff  dw      0xffff
003062:  ffff  dw      0xffff
003064:  ffff  dw      0xffff
003066:  ffff  dw      0xffff
003068:  ffff  dw      0xffff
00306a:  ffff  dw      0xffff
00306c:  ffff  dw      0xffff
00306e:  ffff  dw      0xffff
003070:  ffff  dw      0xffff
003072:  ffff  dw      0xffff
003074:  ffff  dw      0xffff
003076:  ffff  dw      0xffff
003078:  ffff  dw      0xffff
00307a:  ffff  dw      0xffff
00307c:  ffff  dw      0xffff
00307e:  ffff  dw      0xffff
003080:  ffff  dw      0xffff
003082:  ffff  dw      0xffff
003084:  ffff  dw      0xffff
003086:  ffff  dw      0xffff
003088:  ffff  dw      0xffff
00308a:  ffff  dw      0xffff
00308c:  ffff  dw      0xffff
00308e:  ffff  dw      0xffff
003090:  ffff  dw      0xffff
003092:  ffff  dw      0xffff
003094:  ffff  dw      0xffff
003096:  ffff  dw      0xffff
003098:  ffff  dw      0xffff
00309a:  ffff  dw      0xffff
00309c:  ffff  dw      0xffff
00309e:  ffff  dw      0xffff
0030a0:  ffff  dw      0xffff
0030a2:  ffff  dw      0xffff
0030a4:  ffff  dw      0xffff
0030a6:  ffff  dw      0xffff
0030a8:  ffff  dw      0xffff
0030aa:  ffff  dw      0xffff
0030ac:  ffff  dw      0xffff
0030ae:  ffff  dw      0xffff
0030b0:  ffff  dw      0xffff
0030b2:  ffff  dw      0xffff
0030b4:  ffff  dw      0xffff
0030b6:  ffff  dw      0xffff
0030b8:  ffff  dw      0xffff
0030ba:  ffff  dw      0xffff
0030bc:  ffff  dw      0xffff
0030be:  ffff  dw      0xffff
0030c0:  ffff  dw      0xffff
0030c2:  ffff  dw      0xffff
0030c4:  ffff  dw      0xffff
0030c6:  ffff  dw      0xffff
0030c8:  ffff  dw      0xffff
0030ca:  ffff  dw      0xffff
0030cc:  ffff  dw      0xffff
0030ce:  ffff  dw      0xffff
0030d0:  ffff  dw      0xffff
0030d2:  ffff  dw      0xffff
0030d4:  ffff  dw      0xffff
0030d6:  ffff  dw      0xffff
0030d8:  ffff  dw      0xffff
0030da:  ffff  dw      0xffff
0030dc:  ffff  dw      0xffff
0030de:  ffff  dw      0xffff
0030e0:  ffff  dw      0xffff
0030e2:  ffff  dw      0xffff
0030e4:  ffff  dw      0xffff
0030e6:  ffff  dw      0xffff
0030e8:  ffff  dw      0xffff
0030ea:  ffff  dw      0xffff
0030ec:  ffff  dw      0xffff
0030ee:  ffff  dw      0xffff
0030f0:  ffff  dw      0xffff
0030f2:  ffff  dw      0xffff
0030f4:  ffff  dw      0xffff
0030f6:  ffff  dw      0xffff
0030f8:  ffff  dw      0xffff
0030fa:  ffff  dw      0xffff
0030fc:  ffff  dw      0xffff
0030fe:  ffff  dw      0xffff
003100:  ffff  dw      0xffff
003102:  ffff  dw      0xffff
003104:  ffff  dw      0xffff
003106:  ffff  dw      0xffff
003108:  ffff  dw      0xffff
00310a:  ffff  dw      0xffff
00310c:  ffff  dw      0xffff
00310e:  ffff  dw      0xffff
003110:  ffff  dw      0xffff
003112:  ffff  dw      0xffff
003114:  ffff  dw      0xffff
003116:  ffff  dw      0xffff
003118:  ffff  dw      0xffff
00311a:  ffff  dw      0xffff
00311c:  ffff  dw      0xffff
00311e:  ffff  dw      0xffff
003120:  ffff  dw      0xffff
003122:  ffff  dw      0xffff
003124:  ffff  dw      0xffff
003126:  ffff  dw      0xffff
003128:  ffff  dw      0xffff
00312a:  ffff  dw      0xffff
00312c:  ffff  dw      0xffff
00312e:  ffff  dw      0xffff
003130:  ffff  dw      0xffff
003132:  ffff  dw      0xffff
003134:  ffff  dw      0xffff
003136:  ffff  dw      0xffff
003138:  ffff  dw      0xffff
00313a:  ffff  dw      0xffff
00313c:  ffff  dw      0xffff
00313e:  ffff  dw      0xffff
003140:  ffff  dw      0xffff
003142:  ffff  dw      0xffff
003144:  ffff  dw      0xffff
003146:  ffff  dw      0xffff
003148:  ffff  dw      0xffff
00314a:  ffff  dw      0xffff
00314c:  ffff  dw      0xffff
00314e:  ffff  dw      0xffff
003150:  ffff  dw      0xffff
003152:  ffff  dw      0xffff
003154:  ffff  dw      0xffff
003156:  ffff  dw      0xffff
003158:  ffff  dw      0xffff
00315a:  ffff  dw      0xffff
00315c:  ffff  dw      0xffff
00315e:  ffff  dw      0xffff
003160:  ffff  dw      0xffff
003162:  ffff  dw      0xffff
003164:  ffff  dw      0xffff
003166:  ffff  dw      0xffff
003168:  ffff  dw      0xffff
00316a:  ffff  dw      0xffff
00316c:  ffff  dw      0xffff
00316e:  ffff  dw      0xffff
003170:  ffff  dw      0xffff
003172:  ffff  dw      0xffff
003174:  ffff  dw      0xffff
003176:  ffff  dw      0xffff
003178:  ffff  dw      0xffff
00317a:  ffff  dw      0xffff
00317c:  ffff  dw      0xffff
00317e:  ffff  dw      0xffff
003180:  ffff  dw      0xffff
003182:  ffff  dw      0xffff
003184:  ffff  dw      0xffff
003186:  ffff  dw      0xffff
003188:  ffff  dw      0xffff
00318a:  ffff  dw      0xffff
00318c:  ffff  dw      0xffff
00318e:  ffff  dw      0xffff
003190:  ffff  dw      0xffff
003192:  ffff  dw      0xffff
003194:  ffff  dw      0xffff
003196:  ffff  dw      0xffff
003198:  ffff  dw      0xffff
00319a:  ffff  dw      0xffff
00319c:  ffff  dw      0xffff
00319e:  ffff  dw      0xffff
0031a0:  ffff  dw      0xffff
0031a2:  ffff  dw      0xffff
0031a4:  ffff  dw      0xffff
0031a6:  ffff  dw      0xffff
0031a8:  ffff  dw      0xffff
0031aa:  ffff  dw      0xffff
0031ac:  ffff  dw      0xffff
0031ae:  ffff  dw      0xffff
0031b0:  ffff  dw      0xffff
0031b2:  ffff  dw      0xffff
0031b4:  ffff  dw      0xffff
0031b6:  ffff  dw      0xffff
0031b8:  ffff  dw      0xffff
0031ba:  ffff  dw      0xffff
0031bc:  ffff  dw      0xffff
0031be:  ffff  dw      0xffff
0031c0:  ffff  dw      0xffff
0031c2:  ffff  dw      0xffff
0031c4:  ffff  dw      0xffff
0031c6:  ffff  dw      0xffff
0031c8:  ffff  dw      0xffff
0031ca:  ffff  dw      0xffff
0031cc:  ffff  dw      0xffff
0031ce:  ffff  dw      0xffff
0031d0:  ffff  dw      0xffff
0031d2:  ffff  dw      0xffff
0031d4:  ffff  dw      0xffff
0031d6:  ffff  dw      0xffff
0031d8:  ffff  dw      0xffff
0031da:  ffff  dw      0xffff
0031dc:  ffff  dw      0xffff
0031de:  ffff  dw      0xffff
0031e0:  ffff  dw      0xffff
0031e2:  ffff  dw      0xffff
0031e4:  ffff  dw      0xffff
0031e6:  ffff  dw      0xffff
0031e8:  ffff  dw      0xffff
0031ea:  ffff  dw      0xffff
0031ec:  ffff  dw      0xffff
0031ee:  ffff  dw      0xffff
0031f0:  ffff  dw      0xffff
0031f2:  ffff  dw      0xffff
0031f4:  ffff  dw      0xffff
0031f6:  ffff  dw      0xffff
0031f8:  ffff  dw      0xffff
0031fa:  ffff  dw      0xffff
0031fc:  ffff  dw      0xffff
0031fe:  ffff  dw      0xffff
003200:  ffff  dw      0xffff
003202:  ffff  dw      0xffff
003204:  ffff  dw      0xffff
003206:  ffff  dw      0xffff
003208:  ffff  dw      0xffff
00320a:  ffff  dw      0xffff
00320c:  ffff  dw      0xffff
00320e:  ffff  dw      0xffff
003210:  ffff  dw      0xffff
003212:  ffff  dw      0xffff
003214:  ffff  dw      0xffff
003216:  ffff  dw      0xffff
003218:  ffff  dw      0xffff
00321a:  ffff  dw      0xffff
00321c:  ffff  dw      0xffff
00321e:  ffff  dw      0xffff
003220:  ffff  dw      0xffff
003222:  ffff  dw      0xffff
003224:  ffff  dw      0xffff
003226:  ffff  dw      0xffff
003228:  ffff  dw      0xffff
00322a:  ffff  dw      0xffff
00322c:  ffff  dw      0xffff
00322e:  ffff  dw      0xffff
003230:  ffff  dw      0xffff
003232:  ffff  dw      0xffff
003234:  ffff  dw      0xffff
003236:  ffff  dw      0xffff
003238:  ffff  dw      0xffff
00323a:  ffff  dw      0xffff
00323c:  ffff  dw      0xffff
00323e:  ffff  dw      0xffff
003240:  ffff  dw      0xffff
003242:  ffff  dw      0xffff
003244:  ffff  dw      0xffff
003246:  ffff  dw      0xffff
003248:  ffff  dw      0xffff
00324a:  ffff  dw      0xffff
00324c:  ffff  dw      0xffff
00324e:  ffff  dw      0xffff
003250:  ffff  dw      0xffff
003252:  ffff  dw      0xffff
003254:  ffff  dw      0xffff
003256:  ffff  dw      0xffff
003258:  ffff  dw      0xffff
00325a:  ffff  dw      0xffff
00325c:  ffff  dw      0xffff
00325e:  ffff  dw      0xffff
003260:  ffff  dw      0xffff
003262:  ffff  dw      0xffff
003264:  ffff  dw      0xffff
003266:  ffff  dw      0xffff
003268:  ffff  dw      0xffff
00326a:  ffff  dw      0xffff
00326c:  ffff  dw      0xffff
00326e:  ffff  dw      0xffff
003270:  ffff  dw      0xffff
003272:  ffff  dw      0xffff
003274:  ffff  dw      0xffff
003276:  ffff  dw      0xffff
003278:  ffff  dw      0xffff
00327a:  ffff  dw      0xffff
00327c:  ffff  dw      0xffff
00327e:  ffff  dw      0xffff
003280:  ffff  dw      0xffff
003282:  ffff  dw      0xffff
003284:  ffff  dw      0xffff
003286:  ffff  dw      0xffff
003288:  ffff  dw      0xffff
00328a:  ffff  dw      0xffff
00328c:  ffff  dw      0xffff
00328e:  ffff  dw      0xffff
003290:  ffff  dw      0xffff
003292:  ffff  dw      0xffff
003294:  ffff  dw      0xffff
003296:  ffff  dw      0xffff
003298:  ffff  dw      0xffff
00329a:  ffff  dw      0xffff
00329c:  ffff  dw      0xffff
00329e:  ffff  dw      0xffff
0032a0:  ffff  dw      0xffff
0032a2:  ffff  dw      0xffff
0032a4:  ffff  dw      0xffff
0032a6:  ffff  dw      0xffff
0032a8:  ffff  dw      0xffff
0032aa:  ffff  dw      0xffff
0032ac:  ffff  dw      0xffff
0032ae:  ffff  dw      0xffff
0032b0:  ffff  dw      0xffff
0032b2:  ffff  dw      0xffff
0032b4:  ffff  dw      0xffff
0032b6:  ffff  dw      0xffff
0032b8:  ffff  dw      0xffff
0032ba:  ffff  dw      0xffff
0032bc:  ffff  dw      0xffff
0032be:  ffff  dw      0xffff
0032c0:  ffff  dw      0xffff
0032c2:  ffff  dw      0xffff
0032c4:  ffff  dw      0xffff
0032c6:  ffff  dw      0xffff
0032c8:  ffff  dw      0xffff
0032ca:  ffff  dw      0xffff
0032cc:  ffff  dw      0xffff
0032ce:  ffff  dw      0xffff
0032d0:  ffff  dw      0xffff
0032d2:  ffff  dw      0xffff
0032d4:  ffff  dw      0xffff
0032d6:  ffff  dw      0xffff
0032d8:  ffff  dw      0xffff
0032da:  ffff  dw      0xffff
0032dc:  ffff  dw      0xffff
0032de:  ffff  dw      0xffff
0032e0:  ffff  dw      0xffff
0032e2:  ffff  dw      0xffff
0032e4:  ffff  dw      0xffff
0032e6:  ffff  dw      0xffff
0032e8:  ffff  dw      0xffff
0032ea:  ffff  dw      0xffff
0032ec:  ffff  dw      0xffff
0032ee:  ffff  dw      0xffff
0032f0:  ffff  dw      0xffff
0032f2:  ffff  dw      0xffff
0032f4:  ffff  dw      0xffff
0032f6:  ffff  dw      0xffff
0032f8:  ffff  dw      0xffff
0032fa:  ffff  dw      0xffff
0032fc:  ffff  dw      0xffff
0032fe:  ffff  dw      0xffff
003300:  ffff  dw      0xffff
003302:  ffff  dw      0xffff
003304:  ffff  dw      0xffff
003306:  ffff  dw      0xffff
003308:  ffff  dw      0xffff
00330a:  ffff  dw      0xffff
00330c:  ffff  dw      0xffff
00330e:  ffff  dw      0xffff
003310:  ffff  dw      0xffff
003312:  ffff  dw      0xffff
003314:  ffff  dw      0xffff
003316:  ffff  dw      0xffff
003318:  ffff  dw      0xffff
00331a:  ffff  dw      0xffff
00331c:  ffff  dw      0xffff
00331e:  ffff  dw      0xffff
003320:  ffff  dw      0xffff
003322:  ffff  dw      0xffff
003324:  ffff  dw      0xffff
003326:  ffff  dw      0xffff
003328:  ffff  dw      0xffff
00332a:  ffff  dw      0xffff
00332c:  ffff  dw      0xffff
00332e:  ffff  dw      0xffff
003330:  ffff  dw      0xffff
003332:  ffff  dw      0xffff
003334:  ffff  dw      0xffff
003336:  ffff  dw      0xffff
003338:  ffff  dw      0xffff
00333a:  ffff  dw      0xffff
00333c:  ffff  dw      0xffff
00333e:  ffff  dw      0xffff
003340:  ffff  dw      0xffff
003342:  ffff  dw      0xffff
003344:  ffff  dw      0xffff
003346:  ffff  dw      0xffff
003348:  ffff  dw      0xffff
00334a:  ffff  dw      0xffff
00334c:  ffff  dw      0xffff
00334e:  ffff  dw      0xffff
003350:  ffff  dw      0xffff
003352:  ffff  dw      0xffff
003354:  ffff  dw      0xffff
003356:  ffff  dw      0xffff
003358:  ffff  dw      0xffff
00335a:  ffff  dw      0xffff
00335c:  ffff  dw      0xffff
00335e:  ffff  dw      0xffff
003360:  ffff  dw      0xffff
003362:  ffff  dw      0xffff
003364:  ffff  dw      0xffff
003366:  ffff  dw      0xffff
003368:  ffff  dw      0xffff
00336a:  ffff  dw      0xffff
00336c:  ffff  dw      0xffff
00336e:  ffff  dw      0xffff
003370:  ffff  dw      0xffff
003372:  ffff  dw      0xffff
003374:  ffff  dw      0xffff
003376:  ffff  dw      0xffff
003378:  ffff  dw      0xffff
00337a:  ffff  dw      0xffff
00337c:  ffff  dw      0xffff
00337e:  ffff  dw      0xffff
003380:  ffff  dw      0xffff
003382:  ffff  dw      0xffff
003384:  ffff  dw      0xffff
003386:  ffff  dw      0xffff
003388:  ffff  dw      0xffff
00338a:  ffff  dw      0xffff
00338c:  ffff  dw      0xffff
00338e:  ffff  dw      0xffff
003390:  ffff  dw      0xffff
003392:  ffff  dw      0xffff
003394:  ffff  dw      0xffff
003396:  ffff  dw      0xffff
003398:  ffff  dw      0xffff
00339a:  ffff  dw      0xffff
00339c:  ffff  dw      0xffff
00339e:  ffff  dw      0xffff
0033a0:  ffff  dw      0xffff
0033a2:  ffff  dw      0xffff
0033a4:  ffff  dw      0xffff
0033a6:  ffff  dw      0xffff
0033a8:  ffff  dw      0xffff
0033aa:  ffff  dw      0xffff
0033ac:  ffff  dw      0xffff
0033ae:  ffff  dw      0xffff
0033b0:  ffff  dw      0xffff
0033b2:  ffff  dw      0xffff
0033b4:  ffff  dw      0xffff
0033b6:  ffff  dw      0xffff
0033b8:  ffff  dw      0xffff
0033ba:  ffff  dw      0xffff
0033bc:  ffff  dw      0xffff
0033be:  ffff  dw      0xffff
0033c0:  ffff  dw      0xffff
0033c2:  ffff  dw      0xffff
0033c4:  ffff  dw      0xffff
0033c6:  ffff  dw      0xffff
0033c8:  ffff  dw      0xffff
0033ca:  ffff  dw      0xffff
0033cc:  ffff  dw      0xffff
0033ce:  ffff  dw      0xffff
0033d0:  ffff  dw      0xffff
0033d2:  ffff  dw      0xffff
0033d4:  ffff  dw      0xffff
0033d6:  ffff  dw      0xffff
0033d8:  ffff  dw      0xffff
0033da:  ffff  dw      0xffff
0033dc:  ffff  dw      0xffff
0033de:  ffff  dw      0xffff
0033e0:  ffff  dw      0xffff
0033e2:  ffff  dw      0xffff
0033e4:  ffff  dw      0xffff
0033e6:  ffff  dw      0xffff
0033e8:  ffff  dw      0xffff
0033ea:  ffff  dw      0xffff
0033ec:  ffff  dw      0xffff
0033ee:  ffff  dw      0xffff
0033f0:  ffff  dw      0xffff
0033f2:  ffff  dw      0xffff
0033f4:  ffff  dw      0xffff
0033f6:  ffff  dw      0xffff
0033f8:  ffff  dw      0xffff
0033fa:  ffff  dw      0xffff
0033fc:  ffff  dw      0xffff
0033fe:  ffff  dw      0xffff
003400:  ffff  dw      0xffff
003402:  ffff  dw      0xffff
003404:  ffff  dw      0xffff
003406:  ffff  dw      0xffff
003408:  ffff  dw      0xffff
00340a:  ffff  dw      0xffff
00340c:  ffff  dw      0xffff
00340e:  ffff  dw      0xffff
003410:  ffff  dw      0xffff
003412:  ffff  dw      0xffff
003414:  ffff  dw      0xffff
003416:  ffff  dw      0xffff
003418:  ffff  dw      0xffff
00341a:  ffff  dw      0xffff
00341c:  ffff  dw      0xffff
00341e:  ffff  dw      0xffff
003420:  ffff  dw      0xffff
003422:  ffff  dw      0xffff
003424:  ffff  dw      0xffff
003426:  ffff  dw      0xffff
003428:  ffff  dw      0xffff
00342a:  ffff  dw      0xffff
00342c:  ffff  dw      0xffff
00342e:  ffff  dw      0xffff
003430:  ffff  dw      0xffff
003432:  ffff  dw      0xffff
003434:  ffff  dw      0xffff
003436:  ffff  dw      0xffff
003438:  ffff  dw      0xffff
00343a:  ffff  dw      0xffff
00343c:  ffff  dw      0xffff
00343e:  ffff  dw      0xffff
003440:  ffff  dw      0xffff
003442:  ffff  dw      0xffff
003444:  ffff  dw      0xffff
003446:  ffff  dw      0xffff
003448:  ffff  dw      0xffff
00344a:  ffff  dw      0xffff
00344c:  ffff  dw      0xffff
00344e:  ffff  dw      0xffff
003450:  ffff  dw      0xffff
003452:  ffff  dw      0xffff
003454:  ffff  dw      0xffff
003456:  ffff  dw      0xffff
003458:  ffff  dw      0xffff
00345a:  ffff  dw      0xffff
00345c:  ffff  dw      0xffff
00345e:  ffff  dw      0xffff
003460:  ffff  dw      0xffff
003462:  ffff  dw      0xffff
003464:  ffff  dw      0xffff
003466:  ffff  dw      0xffff
003468:  ffff  dw      0xffff
00346a:  ffff  dw      0xffff
00346c:  ffff  dw      0xffff
00346e:  ffff  dw      0xffff
003470:  ffff  dw      0xffff
003472:  ffff  dw      0xffff
003474:  ffff  dw      0xffff
003476:  ffff  dw      0xffff
003478:  ffff  dw      0xffff
00347a:  ffff  dw      0xffff
00347c:  ffff  dw      0xffff
00347e:  ffff  dw      0xffff
003480:  ffff  dw      0xffff
003482:  ffff  dw      0xffff
003484:  ffff  dw      0xffff
003486:  ffff  dw      0xffff
003488:  ffff  dw      0xffff
00348a:  ffff  dw      0xffff
00348c:  ffff  dw      0xffff
00348e:  ffff  dw      0xffff
003490:  ffff  dw      0xffff
003492:  ffff  dw      0xffff
003494:  ffff  dw      0xffff
003496:  ffff  dw      0xffff
003498:  ffff  dw      0xffff
00349a:  ffff  dw      0xffff
00349c:  ffff  dw      0xffff
00349e:  ffff  dw      0xffff
0034a0:  ffff  dw      0xffff
0034a2:  ffff  dw      0xffff
0034a4:  ffff  dw      0xffff
0034a6:  ffff  dw      0xffff
0034a8:  ffff  dw      0xffff
0034aa:  ffff  dw      0xffff
0034ac:  ffff  dw      0xffff
0034ae:  ffff  dw      0xffff
0034b0:  ffff  dw      0xffff
0034b2:  ffff  dw      0xffff
0034b4:  ffff  dw      0xffff
0034b6:  ffff  dw      0xffff
0034b8:  ffff  dw      0xffff
0034ba:  ffff  dw      0xffff
0034bc:  ffff  dw      0xffff
0034be:  ffff  dw      0xffff
0034c0:  ffff  dw      0xffff
0034c2:  ffff  dw      0xffff
0034c4:  ffff  dw      0xffff
0034c6:  ffff  dw      0xffff
0034c8:  ffff  dw      0xffff
0034ca:  ffff  dw      0xffff
0034cc:  ffff  dw      0xffff
0034ce:  ffff  dw      0xffff
0034d0:  ffff  dw      0xffff
0034d2:  ffff  dw      0xffff
0034d4:  ffff  dw      0xffff
0034d6:  ffff  dw      0xffff
0034d8:  ffff  dw      0xffff
0034da:  ffff  dw      0xffff
0034dc:  ffff  dw      0xffff
0034de:  ffff  dw      0xffff
0034e0:  ffff  dw      0xffff
0034e2:  ffff  dw      0xffff
0034e4:  ffff  dw      0xffff
0034e6:  ffff  dw      0xffff
0034e8:  ffff  dw      0xffff
0034ea:  ffff  dw      0xffff
0034ec:  ffff  dw      0xffff
0034ee:  ffff  dw      0xffff
0034f0:  ffff  dw      0xffff
0034f2:  ffff  dw      0xffff
0034f4:  ffff  dw      0xffff
0034f6:  ffff  dw      0xffff
0034f8:  ffff  dw      0xffff
0034fa:  ffff  dw      0xffff
0034fc:  ffff  dw      0xffff
0034fe:  ffff  dw      0xffff
003500:  ffff  dw      0xffff
003502:  ffff  dw      0xffff
003504:  ffff  dw      0xffff
003506:  ffff  dw      0xffff
003508:  ffff  dw      0xffff
00350a:  ffff  dw      0xffff
00350c:  ffff  dw      0xffff
00350e:  ffff  dw      0xffff
003510:  ffff  dw      0xffff
003512:  ffff  dw      0xffff
003514:  ffff  dw      0xffff
003516:  ffff  dw      0xffff
003518:  ffff  dw      0xffff
00351a:  ffff  dw      0xffff
00351c:  ffff  dw      0xffff
00351e:  ffff  dw      0xffff
003520:  ffff  dw      0xffff
003522:  ffff  dw      0xffff
003524:  ffff  dw      0xffff
003526:  ffff  dw      0xffff
003528:  ffff  dw      0xffff
00352a:  ffff  dw      0xffff
00352c:  ffff  dw      0xffff
00352e:  ffff  dw      0xffff
003530:  ffff  dw      0xffff
003532:  ffff  dw      0xffff
003534:  ffff  dw      0xffff
003536:  ffff  dw      0xffff
003538:  ffff  dw      0xffff
00353a:  ffff  dw      0xffff
00353c:  ffff  dw      0xffff
00353e:  ffff  dw      0xffff
003540:  ffff  dw      0xffff
003542:  ffff  dw      0xffff
003544:  ffff  dw      0xffff
003546:  ffff  dw      0xffff
003548:  ffff  dw      0xffff
00354a:  ffff  dw      0xffff
00354c:  ffff  dw      0xffff
00354e:  ffff  dw      0xffff
003550:  ffff  dw      0xffff
003552:  ffff  dw      0xffff
003554:  ffff  dw      0xffff
003556:  ffff  dw      0xffff
003558:  ffff  dw      0xffff
00355a:  ffff  dw      0xffff
00355c:  ffff  dw      0xffff
00355e:  ffff  dw      0xffff
003560:  ffff  dw      0xffff
003562:  ffff  dw      0xffff
003564:  ffff  dw      0xffff
003566:  ffff  dw      0xffff
003568:  ffff  dw      0xffff
00356a:  ffff  dw      0xffff
00356c:  ffff  dw      0xffff
00356e:  ffff  dw      0xffff
003570:  ffff  dw      0xffff
003572:  ffff  dw      0xffff
003574:  ffff  dw      0xffff
003576:  ffff  dw      0xffff
003578:  ffff  dw      0xffff
00357a:  ffff  dw      0xffff
00357c:  ffff  dw      0xffff
00357e:  ffff  dw      0xffff
003580:  ffff  dw      0xffff
003582:  ffff  dw      0xffff
003584:  ffff  dw      0xffff
003586:  ffff  dw      0xffff
003588:  ffff  dw      0xffff
00358a:  ffff  dw      0xffff
00358c:  ffff  dw      0xffff
00358e:  ffff  dw      0xffff
003590:  ffff  dw      0xffff
003592:  ffff  dw      0xffff
003594:  ffff  dw      0xffff
003596:  ffff  dw      0xffff
003598:  ffff  dw      0xffff
00359a:  ffff  dw      0xffff
00359c:  ffff  dw      0xffff
00359e:  ffff  dw      0xffff
0035a0:  ffff  dw      0xffff
0035a2:  ffff  dw      0xffff
0035a4:  ffff  dw      0xffff
0035a6:  ffff  dw      0xffff
0035a8:  ffff  dw      0xffff
0035aa:  ffff  dw      0xffff
0035ac:  ffff  dw      0xffff
0035ae:  ffff  dw      0xffff
0035b0:  ffff  dw      0xffff
0035b2:  ffff  dw      0xffff
0035b4:  ffff  dw      0xffff
0035b6:  ffff  dw      0xffff
0035b8:  ffff  dw      0xffff
0035ba:  ffff  dw      0xffff
0035bc:  ffff  dw      0xffff
0035be:  ffff  dw      0xffff
0035c0:  ffff  dw      0xffff
0035c2:  ffff  dw      0xffff
0035c4:  ffff  dw      0xffff
0035c6:  ffff  dw      0xffff
0035c8:  ffff  dw      0xffff
0035ca:  ffff  dw      0xffff
0035cc:  ffff  dw      0xffff
0035ce:  ffff  dw      0xffff
0035d0:  ffff  dw      0xffff
0035d2:  ffff  dw      0xffff
0035d4:  ffff  dw      0xffff
0035d6:  ffff  dw      0xffff
0035d8:  ffff  dw      0xffff
0035da:  ffff  dw      0xffff
0035dc:  ffff  dw      0xffff
0035de:  ffff  dw      0xffff
0035e0:  ffff  dw      0xffff
0035e2:  ffff  dw      0xffff
0035e4:  ffff  dw      0xffff
0035e6:  ffff  dw      0xffff
0035e8:  ffff  dw      0xffff
0035ea:  ffff  dw      0xffff
0035ec:  ffff  dw      0xffff
0035ee:  ffff  dw      0xffff
0035f0:  ffff  dw      0xffff
0035f2:  ffff  dw      0xffff
0035f4:  ffff  dw      0xffff
0035f6:  ffff  dw      0xffff
0035f8:  ffff  dw      0xffff
0035fa:  ffff  dw      0xffff
0035fc:  ffff  dw      0xffff
0035fe:  ffff  dw      0xffff
003600:  ffff  dw      0xffff
003602:  ffff  dw      0xffff
003604:  ffff  dw      0xffff
003606:  ffff  dw      0xffff
003608:  ffff  dw      0xffff
00360a:  ffff  dw      0xffff
00360c:  ffff  dw      0xffff
00360e:  ffff  dw      0xffff
003610:  ffff  dw      0xffff
003612:  ffff  dw      0xffff
003614:  ffff  dw      0xffff
003616:  ffff  dw      0xffff
003618:  ffff  dw      0xffff
00361a:  ffff  dw      0xffff
00361c:  ffff  dw      0xffff
00361e:  ffff  dw      0xffff
003620:  ffff  dw      0xffff
003622:  ffff  dw      0xffff
003624:  ffff  dw      0xffff
003626:  ffff  dw      0xffff
003628:  ffff  dw      0xffff
00362a:  ffff  dw      0xffff
00362c:  ffff  dw      0xffff
00362e:  ffff  dw      0xffff
003630:  ffff  dw      0xffff
003632:  ffff  dw      0xffff
003634:  ffff  dw      0xffff
003636:  ffff  dw      0xffff
003638:  ffff  dw      0xffff
00363a:  ffff  dw      0xffff
00363c:  ffff  dw      0xffff
00363e:  ffff  dw      0xffff
003640:  ffff  dw      0xffff
003642:  ffff  dw      0xffff
003644:  ffff  dw      0xffff
003646:  ffff  dw      0xffff
003648:  ffff  dw      0xffff
00364a:  ffff  dw      0xffff
00364c:  ffff  dw      0xffff
00364e:  ffff  dw      0xffff
003650:  ffff  dw      0xffff
003652:  ffff  dw      0xffff
003654:  ffff  dw      0xffff
003656:  ffff  dw      0xffff
003658:  ffff  dw      0xffff
00365a:  ffff  dw      0xffff
00365c:  ffff  dw      0xffff
00365e:  ffff  dw      0xffff
003660:  ffff  dw      0xffff
003662:  ffff  dw      0xffff
003664:  ffff  dw      0xffff
003666:  ffff  dw      0xffff
003668:  ffff  dw      0xffff
00366a:  ffff  dw      0xffff
00366c:  ffff  dw      0xffff
00366e:  ffff  dw      0xffff
003670:  ffff  dw      0xffff
003672:  ffff  dw      0xffff
003674:  ffff  dw      0xffff
003676:  ffff  dw      0xffff
003678:  ffff  dw      0xffff
00367a:  ffff  dw      0xffff
00367c:  ffff  dw      0xffff
00367e:  ffff  dw      0xffff
003680:  ffff  dw      0xffff
003682:  ffff  dw      0xffff
003684:  ffff  dw      0xffff
003686:  ffff  dw      0xffff
003688:  ffff  dw      0xffff
00368a:  ffff  dw      0xffff
00368c:  ffff  dw      0xffff
00368e:  ffff  dw      0xffff
003690:  ffff  dw      0xffff
003692:  ffff  dw      0xffff
003694:  ffff  dw      0xffff
003696:  ffff  dw      0xffff
003698:  ffff  dw      0xffff
00369a:  ffff  dw      0xffff
00369c:  ffff  dw      0xffff
00369e:  ffff  dw      0xffff
0036a0:  ffff  dw      0xffff
0036a2:  ffff  dw      0xffff
0036a4:  ffff  dw      0xffff
0036a6:  ffff  dw      0xffff
0036a8:  ffff  dw      0xffff
0036aa:  ffff  dw      0xffff
0036ac:  ffff  dw      0xffff
0036ae:  ffff  dw      0xffff
0036b0:  ffff  dw      0xffff
0036b2:  ffff  dw      0xffff
0036b4:  ffff  dw      0xffff
0036b6:  ffff  dw      0xffff
0036b8:  ffff  dw      0xffff
0036ba:  ffff  dw      0xffff
0036bc:  ffff  dw      0xffff
0036be:  ffff  dw      0xffff
0036c0:  ffff  dw      0xffff
0036c2:  ffff  dw      0xffff
0036c4:  ffff  dw      0xffff
0036c6:  ffff  dw      0xffff
0036c8:  ffff  dw      0xffff
0036ca:  ffff  dw      0xffff
0036cc:  ffff  dw      0xffff
0036ce:  ffff  dw      0xffff
0036d0:  ffff  dw      0xffff
0036d2:  ffff  dw      0xffff
0036d4:  ffff  dw      0xffff
0036d6:  ffff  dw      0xffff
0036d8:  ffff  dw      0xffff
0036da:  ffff  dw      0xffff
0036dc:  ffff  dw      0xffff
0036de:  ffff  dw      0xffff
0036e0:  ffff  dw      0xffff
0036e2:  ffff  dw      0xffff
0036e4:  ffff  dw      0xffff
0036e6:  ffff  dw      0xffff
0036e8:  ffff  dw      0xffff
0036ea:  ffff  dw      0xffff
0036ec:  ffff  dw      0xffff
0036ee:  ffff  dw      0xffff
0036f0:  ffff  dw      0xffff
0036f2:  ffff  dw      0xffff
0036f4:  ffff  dw      0xffff
0036f6:  ffff  dw      0xffff
0036f8:  ffff  dw      0xffff
0036fa:  ffff  dw      0xffff
0036fc:  ffff  dw      0xffff
0036fe:  ffff  dw      0xffff
003700:  ffff  dw      0xffff
003702:  ffff  dw      0xffff
003704:  ffff  dw      0xffff
003706:  ffff  dw      0xffff
003708:  ffff  dw      0xffff
00370a:  ffff  dw      0xffff
00370c:  ffff  dw      0xffff
00370e:  ffff  dw      0xffff
003710:  ffff  dw      0xffff
003712:  ffff  dw      0xffff
003714:  ffff  dw      0xffff
003716:  ffff  dw      0xffff
003718:  ffff  dw      0xffff
00371a:  ffff  dw      0xffff
00371c:  ffff  dw      0xffff
00371e:  ffff  dw      0xffff
003720:  ffff  dw      0xffff
003722:  ffff  dw      0xffff
003724:  ffff  dw      0xffff
003726:  ffff  dw      0xffff
003728:  ffff  dw      0xffff
00372a:  ffff  dw      0xffff
00372c:  ffff  dw      0xffff
00372e:  ffff  dw      0xffff
003730:  ffff  dw      0xffff
003732:  ffff  dw      0xffff
003734:  ffff  dw      0xffff
003736:  ffff  dw      0xffff
003738:  ffff  dw      0xffff
00373a:  ffff  dw      0xffff
00373c:  ffff  dw      0xffff
00373e:  ffff  dw      0xffff
003740:  ffff  dw      0xffff
003742:  ffff  dw      0xffff
003744:  ffff  dw      0xffff
003746:  ffff  dw      0xffff
003748:  ffff  dw      0xffff
00374a:  ffff  dw      0xffff
00374c:  ffff  dw      0xffff
00374e:  ffff  dw      0xffff
003750:  ffff  dw      0xffff
003752:  ffff  dw      0xffff
003754:  ffff  dw      0xffff
003756:  ffff  dw      0xffff
003758:  ffff  dw      0xffff
00375a:  ffff  dw      0xffff
00375c:  ffff  dw      0xffff
00375e:  ffff  dw      0xffff
003760:  ffff  dw      0xffff
003762:  ffff  dw      0xffff
003764:  ffff  dw      0xffff
003766:  ffff  dw      0xffff
003768:  ffff  dw      0xffff
00376a:  ffff  dw      0xffff
00376c:  ffff  dw      0xffff
00376e:  ffff  dw      0xffff
003770:  ffff  dw      0xffff
003772:  ffff  dw      0xffff
003774:  ffff  dw      0xffff
003776:  ffff  dw      0xffff
003778:  ffff  dw      0xffff
00377a:  ffff  dw      0xffff
00377c:  ffff  dw      0xffff
00377e:  ffff  dw      0xffff
003780:  ffff  dw      0xffff
003782:  ffff  dw      0xffff
003784:  ffff  dw      0xffff
003786:  ffff  dw      0xffff
003788:  ffff  dw      0xffff
00378a:  ffff  dw      0xffff
00378c:  ffff  dw      0xffff
00378e:  ffff  dw      0xffff
003790:  ffff  dw      0xffff
003792:  ffff  dw      0xffff
003794:  ffff  dw      0xffff
003796:  ffff  dw      0xffff
003798:  ffff  dw      0xffff
00379a:  ffff  dw      0xffff
00379c:  ffff  dw      0xffff
00379e:  ffff  dw      0xffff
0037a0:  ffff  dw      0xffff
0037a2:  ffff  dw      0xffff
0037a4:  ffff  dw      0xffff
0037a6:  ffff  dw      0xffff
0037a8:  ffff  dw      0xffff
0037aa:  ffff  dw      0xffff
0037ac:  ffff  dw      0xffff
0037ae:  ffff  dw      0xffff
0037b0:  ffff  dw      0xffff
0037b2:  ffff  dw      0xffff
0037b4:  ffff  dw      0xffff
0037b6:  ffff  dw      0xffff
0037b8:  ffff  dw      0xffff
0037ba:  ffff  dw      0xffff
0037bc:  ffff  dw      0xffff
0037be:  ffff  dw      0xffff
0037c0:  ffff  dw      0xffff
0037c2:  ffff  dw      0xffff
0037c4:  ffff  dw      0xffff
0037c6:  ffff  dw      0xffff
0037c8:  ffff  dw      0xffff
0037ca:  ffff  dw      0xffff
0037cc:  ffff  dw      0xffff
0037ce:  ffff  dw      0xffff
0037d0:  ffff  dw      0xffff
0037d2:  ffff  dw      0xffff
0037d4:  ffff  dw      0xffff
0037d6:  ffff  dw      0xffff
0037d8:  ffff  dw      0xffff
0037da:  ffff  dw      0xffff
0037dc:  ffff  dw      0xffff
0037de:  ffff  dw      0xffff
0037e0:  ffff  dw      0xffff
0037e2:  ffff  dw      0xffff
0037e4:  ffff  dw      0xffff
0037e6:  ffff  dw      0xffff
0037e8:  ffff  dw      0xffff
0037ea:  ffff  dw      0xffff
0037ec:  ffff  dw      0xffff
0037ee:  ffff  dw      0xffff
0037f0:  ffff  dw      0xffff
0037f2:  ffff  dw      0xffff
0037f4:  ffff  dw      0xffff
0037f6:  ffff  dw      0xffff
0037f8:  ffff  dw      0xffff
0037fa:  ffff  dw      0xffff
0037fc:  ffff  dw      0xffff
0037fe:  ffff  dw      0xffff
003800:  ffff  dw      0xffff
003802:  ffff  dw      0xffff
003804:  ffff  dw      0xffff
003806:  ffff  dw      0xffff
003808:  ffff  dw      0xffff
00380a:  ffff  dw      0xffff
00380c:  ffff  dw      0xffff
00380e:  ffff  dw      0xffff
003810:  ffff  dw      0xffff
003812:  ffff  dw      0xffff
003814:  ffff  dw      0xffff
003816:  ffff  dw      0xffff
003818:  ffff  dw      0xffff
00381a:  ffff  dw      0xffff
00381c:  ffff  dw      0xffff
00381e:  ffff  dw      0xffff
003820:  ffff  dw      0xffff
003822:  ffff  dw      0xffff
003824:  ffff  dw      0xffff
003826:  ffff  dw      0xffff
003828:  ffff  dw      0xffff
00382a:  ffff  dw      0xffff
00382c:  ffff  dw      0xffff
00382e:  ffff  dw      0xffff
003830:  ffff  dw      0xffff
003832:  ffff  dw      0xffff
003834:  ffff  dw      0xffff
003836:  ffff  dw      0xffff
003838:  ffff  dw      0xffff
00383a:  ffff  dw      0xffff
00383c:  ffff  dw      0xffff
00383e:  ffff  dw      0xffff
003840:  ffff  dw      0xffff
003842:  ffff  dw      0xffff
003844:  ffff  dw      0xffff
003846:  ffff  dw      0xffff
003848:  ffff  dw      0xffff
00384a:  ffff  dw      0xffff
00384c:  ffff  dw      0xffff
00384e:  ffff  dw      0xffff
003850:  ffff  dw      0xffff
003852:  ffff  dw      0xffff
003854:  ffff  dw      0xffff
003856:  ffff  dw      0xffff
003858:  ffff  dw      0xffff
00385a:  ffff  dw      0xffff
00385c:  ffff  dw      0xffff
00385e:  ffff  dw      0xffff
003860:  ffff  dw      0xffff
003862:  ffff  dw      0xffff
003864:  ffff  dw      0xffff
003866:  ffff  dw      0xffff
003868:  ffff  dw      0xffff
00386a:  ffff  dw      0xffff
00386c:  ffff  dw      0xffff
00386e:  ffff  dw      0xffff
003870:  ffff  dw      0xffff
003872:  ffff  dw      0xffff
003874:  ffff  dw      0xffff
003876:  ffff  dw      0xffff
003878:  ffff  dw      0xffff
00387a:  ffff  dw      0xffff
00387c:  ffff  dw      0xffff
00387e:  ffff  dw      0xffff
003880:  ffff  dw      0xffff
003882:  ffff  dw      0xffff
003884:  ffff  dw      0xffff
003886:  ffff  dw      0xffff
003888:  ffff  dw      0xffff
00388a:  ffff  dw      0xffff
00388c:  ffff  dw      0xffff
00388e:  ffff  dw      0xffff
003890:  ffff  dw      0xffff
003892:  ffff  dw      0xffff
003894:  ffff  dw      0xffff
003896:  ffff  dw      0xffff
003898:  ffff  dw      0xffff
00389a:  ffff  dw      0xffff
00389c:  ffff  dw      0xffff
00389e:  ffff  dw      0xffff
0038a0:  ffff  dw      0xffff
0038a2:  ffff  dw      0xffff
0038a4:  ffff  dw      0xffff
0038a6:  ffff  dw      0xffff
0038a8:  ffff  dw      0xffff
0038aa:  ffff  dw      0xffff
0038ac:  ffff  dw      0xffff
0038ae:  ffff  dw      0xffff
0038b0:  ffff  dw      0xffff
0038b2:  ffff  dw      0xffff
0038b4:  ffff  dw      0xffff
0038b6:  ffff  dw      0xffff
0038b8:  ffff  dw      0xffff
0038ba:  ffff  dw      0xffff
0038bc:  ffff  dw      0xffff
0038be:  ffff  dw      0xffff
0038c0:  ffff  dw      0xffff
0038c2:  ffff  dw      0xffff
0038c4:  ffff  dw      0xffff
0038c6:  ffff  dw      0xffff
0038c8:  ffff  dw      0xffff
0038ca:  ffff  dw      0xffff
0038cc:  ffff  dw      0xffff
0038ce:  ffff  dw      0xffff
0038d0:  ffff  dw      0xffff
0038d2:  ffff  dw      0xffff
0038d4:  ffff  dw      0xffff
0038d6:  ffff  dw      0xffff
0038d8:  ffff  dw      0xffff
0038da:  ffff  dw      0xffff
0038dc:  ffff  dw      0xffff
0038de:  ffff  dw      0xffff
0038e0:  ffff  dw      0xffff
0038e2:  ffff  dw      0xffff
0038e4:  ffff  dw      0xffff
0038e6:  ffff  dw      0xffff
0038e8:  ffff  dw      0xffff
0038ea:  ffff  dw      0xffff
0038ec:  ffff  dw      0xffff
0038ee:  ffff  dw      0xffff
0038f0:  ffff  dw      0xffff
0038f2:  ffff  dw      0xffff
0038f4:  ffff  dw      0xffff
0038f6:  ffff  dw      0xffff
0038f8:  ffff  dw      0xffff
0038fa:  ffff  dw      0xffff
0038fc:  ffff  dw      0xffff
0038fe:  ffff  dw      0xffff
003900:  ffff  dw      0xffff
003902:  ffff  dw      0xffff
003904:  ffff  dw      0xffff
003906:  ffff  dw      0xffff
003908:  ffff  dw      0xffff
00390a:  ffff  dw      0xffff
00390c:  ffff  dw      0xffff
00390e:  ffff  dw      0xffff
003910:  ffff  dw      0xffff
003912:  ffff  dw      0xffff
003914:  ffff  dw      0xffff
003916:  ffff  dw      0xffff
003918:  ffff  dw      0xffff
00391a:  ffff  dw      0xffff
00391c:  ffff  dw      0xffff
00391e:  ffff  dw      0xffff
003920:  ffff  dw      0xffff
003922:  ffff  dw      0xffff
003924:  ffff  dw      0xffff
003926:  ffff  dw      0xffff
003928:  ffff  dw      0xffff
00392a:  ffff  dw      0xffff
00392c:  ffff  dw      0xffff
00392e:  ffff  dw      0xffff
003930:  ffff  dw      0xffff
003932:  ffff  dw      0xffff
003934:  ffff  dw      0xffff
003936:  ffff  dw      0xffff
003938:  ffff  dw      0xffff
00393a:  ffff  dw      0xffff
00393c:  ffff  dw      0xffff
00393e:  ffff  dw      0xffff
003940:  ffff  dw      0xffff
003942:  ffff  dw      0xffff
003944:  ffff  dw      0xffff
003946:  ffff  dw      0xffff
003948:  ffff  dw      0xffff
00394a:  ffff  dw      0xffff
00394c:  ffff  dw      0xffff
00394e:  ffff  dw      0xffff
003950:  ffff  dw      0xffff
003952:  ffff  dw      0xffff
003954:  ffff  dw      0xffff
003956:  ffff  dw      0xffff
003958:  ffff  dw      0xffff
00395a:  ffff  dw      0xffff
00395c:  ffff  dw      0xffff
00395e:  ffff  dw      0xffff
003960:  ffff  dw      0xffff
003962:  ffff  dw      0xffff
003964:  ffff  dw      0xffff
003966:  ffff  dw      0xffff
003968:  ffff  dw      0xffff
00396a:  ffff  dw      0xffff
00396c:  ffff  dw      0xffff
00396e:  ffff  dw      0xffff
003970:  ffff  dw      0xffff
003972:  ffff  dw      0xffff
003974:  ffff  dw      0xffff
003976:  ffff  dw      0xffff
003978:  ffff  dw      0xffff
00397a:  ffff  dw      0xffff
00397c:  ffff  dw      0xffff
00397e:  ffff  dw      0xffff
003980:  ffff  dw      0xffff
003982:  ffff  dw      0xffff
003984:  ffff  dw      0xffff
003986:  ffff  dw      0xffff
003988:  ffff  dw      0xffff
00398a:  ffff  dw      0xffff
00398c:  ffff  dw      0xffff
00398e:  ffff  dw      0xffff
003990:  ffff  dw      0xffff
003992:  ffff  dw      0xffff
003994:  ffff  dw      0xffff
003996:  ffff  dw      0xffff
003998:  ffff  dw      0xffff
00399a:  ffff  dw      0xffff
00399c:  ffff  dw      0xffff
00399e:  ffff  dw      0xffff
0039a0:  ffff  dw      0xffff
0039a2:  ffff  dw      0xffff
0039a4:  ffff  dw      0xffff
0039a6:  ffff  dw      0xffff
0039a8:  ffff  dw      0xffff
0039aa:  ffff  dw      0xffff
0039ac:  ffff  dw      0xffff
0039ae:  ffff  dw      0xffff
0039b0:  ffff  dw      0xffff
0039b2:  ffff  dw      0xffff
0039b4:  ffff  dw      0xffff
0039b6:  ffff  dw      0xffff
0039b8:  ffff  dw      0xffff
0039ba:  ffff  dw      0xffff
0039bc:  ffff  dw      0xffff
0039be:  ffff  dw      0xffff
0039c0:  ffff  dw      0xffff
0039c2:  ffff  dw      0xffff
0039c4:  ffff  dw      0xffff
0039c6:  ffff  dw      0xffff
0039c8:  ffff  dw      0xffff
0039ca:  ffff  dw      0xffff
0039cc:  ffff  dw      0xffff
0039ce:  ffff  dw      0xffff
0039d0:  ffff  dw      0xffff
0039d2:  ffff  dw      0xffff
0039d4:  ffff  dw      0xffff
0039d6:  ffff  dw      0xffff
0039d8:  ffff  dw      0xffff
0039da:  ffff  dw      0xffff
0039dc:  ffff  dw      0xffff
0039de:  ffff  dw      0xffff
0039e0:  ffff  dw      0xffff
0039e2:  ffff  dw      0xffff
0039e4:  ffff  dw      0xffff
0039e6:  ffff  dw      0xffff
0039e8:  ffff  dw      0xffff
0039ea:  ffff  dw      0xffff
0039ec:  ffff  dw      0xffff
0039ee:  ffff  dw      0xffff
0039f0:  ffff  dw      0xffff
0039f2:  ffff  dw      0xffff
0039f4:  ffff  dw      0xffff
0039f6:  ffff  dw      0xffff
0039f8:  ffff  dw      0xffff
0039fa:  ffff  dw      0xffff
0039fc:  ffff  dw      0xffff
0039fe:  ffff  dw      0xffff
003a00:  ffff  dw      0xffff
003a02:  ffff  dw      0xffff
003a04:  ffff  dw      0xffff
003a06:  ffff  dw      0xffff
003a08:  ffff  dw      0xffff
003a0a:  ffff  dw      0xffff
003a0c:  ffff  dw      0xffff
003a0e:  ffff  dw      0xffff
003a10:  ffff  dw      0xffff
003a12:  ffff  dw      0xffff
003a14:  ffff  dw      0xffff
003a16:  ffff  dw      0xffff
003a18:  ffff  dw      0xffff
003a1a:  ffff  dw      0xffff
003a1c:  ffff  dw      0xffff
003a1e:  ffff  dw      0xffff
003a20:  ffff  dw      0xffff
003a22:  ffff  dw      0xffff
003a24:  ffff  dw      0xffff
003a26:  ffff  dw      0xffff
003a28:  ffff  dw      0xffff
003a2a:  ffff  dw      0xffff
003a2c:  ffff  dw      0xffff
003a2e:  ffff  dw      0xffff
003a30:  ffff  dw      0xffff
003a32:  ffff  dw      0xffff
003a34:  ffff  dw      0xffff
003a36:  ffff  dw      0xffff
003a38:  ffff  dw      0xffff
003a3a:  ffff  dw      0xffff
003a3c:  ffff  dw      0xffff
003a3e:  ffff  dw      0xffff
003a40:  ffff  dw      0xffff
003a42:  ffff  dw      0xffff
003a44:  ffff  dw      0xffff
003a46:  ffff  dw      0xffff
003a48:  ffff  dw      0xffff
003a4a:  ffff  dw      0xffff
003a4c:  ffff  dw      0xffff
003a4e:  ffff  dw      0xffff
003a50:  ffff  dw      0xffff
003a52:  ffff  dw      0xffff
003a54:  ffff  dw      0xffff
003a56:  ffff  dw      0xffff
003a58:  ffff  dw      0xffff
003a5a:  ffff  dw      0xffff
003a5c:  ffff  dw      0xffff
003a5e:  ffff  dw      0xffff
003a60:  ffff  dw      0xffff
003a62:  ffff  dw      0xffff
003a64:  ffff  dw      0xffff
003a66:  ffff  dw      0xffff
003a68:  ffff  dw      0xffff
003a6a:  ffff  dw      0xffff
003a6c:  ffff  dw      0xffff
003a6e:  ffff  dw      0xffff
003a70:  ffff  dw      0xffff
003a72:  ffff  dw      0xffff
003a74:  ffff  dw      0xffff
003a76:  ffff  dw      0xffff
003a78:  ffff  dw      0xffff
003a7a:  ffff  dw      0xffff
003a7c:  ffff  dw      0xffff
003a7e:  ffff  dw      0xffff
003a80:  ffff  dw      0xffff
003a82:  ffff  dw      0xffff
003a84:  ffff  dw      0xffff
003a86:  ffff  dw      0xffff
003a88:  ffff  dw      0xffff
003a8a:  ffff  dw      0xffff
003a8c:  ffff  dw      0xffff
003a8e:  ffff  dw      0xffff
003a90:  ffff  dw      0xffff
003a92:  ffff  dw      0xffff
003a94:  ffff  dw      0xffff
003a96:  ffff  dw      0xffff
003a98:  ffff  dw      0xffff
003a9a:  ffff  dw      0xffff
003a9c:  ffff  dw      0xffff
003a9e:  ffff  dw      0xffff
003aa0:  ffff  dw      0xffff
003aa2:  ffff  dw      0xffff
003aa4:  ffff  dw      0xffff
003aa6:  ffff  dw      0xffff
003aa8:  ffff  dw      0xffff
003aaa:  ffff  dw      0xffff
003aac:  ffff  dw      0xffff
003aae:  ffff  dw      0xffff
003ab0:  ffff  dw      0xffff
003ab2:  ffff  dw      0xffff
003ab4:  ffff  dw      0xffff
003ab6:  ffff  dw      0xffff
003ab8:  ffff  dw      0xffff
003aba:  ffff  dw      0xffff
003abc:  ffff  dw      0xffff
003abe:  ffff  dw      0xffff
003ac0:  ffff  dw      0xffff
003ac2:  ffff  dw      0xffff
003ac4:  ffff  dw      0xffff
003ac6:  ffff  dw      0xffff
003ac8:  ffff  dw      0xffff
003aca:  ffff  dw      0xffff
003acc:  ffff  dw      0xffff
003ace:  ffff  dw      0xffff
003ad0:  ffff  dw      0xffff
003ad2:  ffff  dw      0xffff
003ad4:  ffff  dw      0xffff
003ad6:  ffff  dw      0xffff
003ad8:  ffff  dw      0xffff
003ada:  ffff  dw      0xffff
003adc:  ffff  dw      0xffff
003ade:  ffff  dw      0xffff
003ae0:  ffff  dw      0xffff
003ae2:  ffff  dw      0xffff
003ae4:  ffff  dw      0xffff
003ae6:  ffff  dw      0xffff
003ae8:  ffff  dw      0xffff
003aea:  ffff  dw      0xffff
003aec:  ffff  dw      0xffff
003aee:  ffff  dw      0xffff
003af0:  ffff  dw      0xffff
003af2:  ffff  dw      0xffff
003af4:  ffff  dw      0xffff
003af6:  ffff  dw      0xffff
003af8:  ffff  dw      0xffff
003afa:  ffff  dw      0xffff
003afc:  ffff  dw      0xffff
003afe:  ffff  dw      0xffff
003b00:  ffff  dw      0xffff
003b02:  ffff  dw      0xffff
003b04:  ffff  dw      0xffff
003b06:  ffff  dw      0xffff
003b08:  ffff  dw      0xffff
003b0a:  ffff  dw      0xffff
003b0c:  ffff  dw      0xffff
003b0e:  ffff  dw      0xffff
003b10:  ffff  dw      0xffff
003b12:  ffff  dw      0xffff
003b14:  ffff  dw      0xffff
003b16:  ffff  dw      0xffff
003b18:  ffff  dw      0xffff
003b1a:  ffff  dw      0xffff
003b1c:  ffff  dw      0xffff
003b1e:  ffff  dw      0xffff
003b20:  ffff  dw      0xffff
003b22:  ffff  dw      0xffff
003b24:  ffff  dw      0xffff
003b26:  ffff  dw      0xffff
003b28:  ffff  dw      0xffff
003b2a:  ffff  dw      0xffff
003b2c:  ffff  dw      0xffff
003b2e:  ffff  dw      0xffff
003b30:  ffff  dw      0xffff
003b32:  ffff  dw      0xffff
003b34:  ffff  dw      0xffff
003b36:  ffff  dw      0xffff
003b38:  ffff  dw      0xffff
003b3a:  ffff  dw      0xffff
003b3c:  ffff  dw      0xffff
003b3e:  ffff  dw      0xffff
003b40:  ffff  dw      0xffff
003b42:  ffff  dw      0xffff
003b44:  ffff  dw      0xffff
003b46:  ffff  dw      0xffff
003b48:  ffff  dw      0xffff
003b4a:  ffff  dw      0xffff
003b4c:  ffff  dw      0xffff
003b4e:  ffff  dw      0xffff
003b50:  ffff  dw      0xffff
003b52:  ffff  dw      0xffff
003b54:  ffff  dw      0xffff
003b56:  ffff  dw      0xffff
003b58:  ffff  dw      0xffff
003b5a:  ffff  dw      0xffff
003b5c:  ffff  dw      0xffff
003b5e:  ffff  dw      0xffff
003b60:  ffff  dw      0xffff
003b62:  ffff  dw      0xffff
003b64:  ffff  dw      0xffff
003b66:  ffff  dw      0xffff
003b68:  ffff  dw      0xffff
003b6a:  ffff  dw      0xffff
003b6c:  ffff  dw      0xffff
003b6e:  ffff  dw      0xffff
003b70:  ffff  dw      0xffff
003b72:  ffff  dw      0xffff
003b74:  ffff  dw      0xffff
003b76:  ffff  dw      0xffff
003b78:  ffff  dw      0xffff
003b7a:  ffff  dw      0xffff
003b7c:  ffff  dw      0xffff
003b7e:  ffff  dw      0xffff
003b80:  ffff  dw      0xffff
003b82:  ffff  dw      0xffff
003b84:  ffff  dw      0xffff
003b86:  ffff  dw      0xffff
003b88:  ffff  dw      0xffff
003b8a:  ffff  dw      0xffff
003b8c:  ffff  dw      0xffff
003b8e:  ffff  dw      0xffff
003b90:  ffff  dw      0xffff
003b92:  ffff  dw      0xffff
003b94:  ffff  dw      0xffff
003b96:  ffff  dw      0xffff
003b98:  ffff  dw      0xffff
003b9a:  ffff  dw      0xffff
003b9c:  ffff  dw      0xffff
003b9e:  ffff  dw      0xffff
003ba0:  ffff  dw      0xffff
003ba2:  ffff  dw      0xffff
003ba4:  ffff  dw      0xffff
003ba6:  ffff  dw      0xffff
003ba8:  ffff  dw      0xffff
003baa:  ffff  dw      0xffff
003bac:  ffff  dw      0xffff
003bae:  ffff  dw      0xffff
003bb0:  ffff  dw      0xffff
003bb2:  ffff  dw      0xffff
003bb4:  ffff  dw      0xffff
003bb6:  ffff  dw      0xffff
003bb8:  ffff  dw      0xffff
003bba:  ffff  dw      0xffff
003bbc:  ffff  dw      0xffff
003bbe:  ffff  dw      0xffff
003bc0:  ffff  dw      0xffff
003bc2:  ffff  dw      0xffff
003bc4:  ffff  dw      0xffff
003bc6:  ffff  dw      0xffff
003bc8:  ffff  dw      0xffff
003bca:  ffff  dw      0xffff
003bcc:  ffff  dw      0xffff
003bce:  ffff  dw      0xffff
003bd0:  ffff  dw      0xffff
003bd2:  ffff  dw      0xffff
003bd4:  ffff  dw      0xffff
003bd6:  ffff  dw      0xffff
003bd8:  ffff  dw      0xffff
003bda:  ffff  dw      0xffff
003bdc:  ffff  dw      0xffff
003bde:  ffff  dw      0xffff
003be0:  ffff  dw      0xffff
003be2:  ffff  dw      0xffff
003be4:  ffff  dw      0xffff
003be6:  ffff  dw      0xffff
003be8:  ffff  dw      0xffff
003bea:  ffff  dw      0xffff
003bec:  ffff  dw      0xffff
003bee:  ffff  dw      0xffff
003bf0:  ffff  dw      0xffff
003bf2:  ffff  dw      0xffff
003bf4:  ffff  dw      0xffff
003bf6:  ffff  dw      0xffff
003bf8:  ffff  dw      0xffff
003bfa:  ffff  dw      0xffff
003bfc:  ffff  dw      0xffff
003bfe:  ffff  dw      0xffff
003c00:  ffff  dw      0xffff
003c02:  ffff  dw      0xffff
003c04:  ffff  dw      0xffff
003c06:  ffff  dw      0xffff
003c08:  ffff  dw      0xffff
003c0a:  ffff  dw      0xffff
003c0c:  ffff  dw      0xffff
003c0e:  ffff  dw      0xffff
003c10:  ffff  dw      0xffff
003c12:  ffff  dw      0xffff
003c14:  ffff  dw      0xffff
003c16:  ffff  dw      0xffff
003c18:  ffff  dw      0xffff
003c1a:  ffff  dw      0xffff
003c1c:  ffff  dw      0xffff
003c1e:  ffff  dw      0xffff
003c20:  ffff  dw      0xffff
003c22:  ffff  dw      0xffff
003c24:  ffff  dw      0xffff
003c26:  ffff  dw      0xffff
003c28:  ffff  dw      0xffff
003c2a:  ffff  dw      0xffff
003c2c:  ffff  dw      0xffff
003c2e:  ffff  dw      0xffff
003c30:  ffff  dw      0xffff
003c32:  ffff  dw      0xffff
003c34:  ffff  dw      0xffff
003c36:  ffff  dw      0xffff
003c38:  ffff  dw      0xffff
003c3a:  ffff  dw      0xffff
003c3c:  ffff  dw      0xffff
003c3e:  ffff  dw      0xffff
003c40:  ffff  dw      0xffff
003c42:  ffff  dw      0xffff
003c44:  ffff  dw      0xffff
003c46:  ffff  dw      0xffff
003c48:  ffff  dw      0xffff
003c4a:  ffff  dw      0xffff
003c4c:  ffff  dw      0xffff
003c4e:  ffff  dw      0xffff
003c50:  ffff  dw      0xffff
003c52:  ffff  dw      0xffff
003c54:  ffff  dw      0xffff
003c56:  ffff  dw      0xffff
003c58:  ffff  dw      0xffff
003c5a:  ffff  dw      0xffff
003c5c:  ffff  dw      0xffff
003c5e:  ffff  dw      0xffff
003c60:  ffff  dw      0xffff
003c62:  ffff  dw      0xffff
003c64:  ffff  dw      0xffff
003c66:  ffff  dw      0xffff
003c68:  ffff  dw      0xffff
003c6a:  ffff  dw      0xffff
003c6c:  ffff  dw      0xffff
003c6e:  ffff  dw      0xffff
003c70:  ffff  dw      0xffff
003c72:  ffff  dw      0xffff
003c74:  ffff  dw      0xffff
003c76:  ffff  dw      0xffff
003c78:  ffff  dw      0xffff
003c7a:  ffff  dw      0xffff
003c7c:  ffff  dw      0xffff
003c7e:  ffff  dw      0xffff
003c80:  ffff  dw      0xffff
003c82:  ffff  dw      0xffff
003c84:  ffff  dw      0xffff
003c86:  ffff  dw      0xffff
003c88:  ffff  dw      0xffff
003c8a:  ffff  dw      0xffff
003c8c:  ffff  dw      0xffff
003c8e:  ffff  dw      0xffff
003c90:  ffff  dw      0xffff
003c92:  ffff  dw      0xffff
003c94:  ffff  dw      0xffff
003c96:  ffff  dw      0xffff
003c98:  ffff  dw      0xffff
003c9a:  ffff  dw      0xffff
003c9c:  ffff  dw      0xffff
003c9e:  ffff  dw      0xffff
003ca0:  ffff  dw      0xffff
003ca2:  ffff  dw      0xffff
003ca4:  ffff  dw      0xffff
003ca6:  ffff  dw      0xffff
003ca8:  ffff  dw      0xffff
003caa:  ffff  dw      0xffff
003cac:  ffff  dw      0xffff
003cae:  ffff  dw      0xffff
003cb0:  ffff  dw      0xffff
003cb2:  ffff  dw      0xffff
003cb4:  ffff  dw      0xffff
003cb6:  ffff  dw      0xffff
003cb8:  ffff  dw      0xffff
003cba:  ffff  dw      0xffff
003cbc:  ffff  dw      0xffff
003cbe:  ffff  dw      0xffff
003cc0:  ffff  dw      0xffff
003cc2:  ffff  dw      0xffff
003cc4:  ffff  dw      0xffff
003cc6:  ffff  dw      0xffff
003cc8:  ffff  dw      0xffff
003cca:  ffff  dw      0xffff
003ccc:  ffff  dw      0xffff
003cce:  ffff  dw      0xffff
003cd0:  ffff  dw      0xffff
003cd2:  ffff  dw      0xffff
003cd4:  ffff  dw      0xffff
003cd6:  ffff  dw      0xffff
003cd8:  ffff  dw      0xffff
003cda:  ffff  dw      0xffff
003cdc:  ffff  dw      0xffff
003cde:  ffff  dw      0xffff
003ce0:  ffff  dw      0xffff
003ce2:  ffff  dw      0xffff
003ce4:  ffff  dw      0xffff
003ce6:  ffff  dw      0xffff
003ce8:  ffff  dw      0xffff
003cea:  ffff  dw      0xffff
003cec:  ffff  dw      0xffff
003cee:  ffff  dw      0xffff
003cf0:  ffff  dw      0xffff
003cf2:  ffff  dw      0xffff
003cf4:  ffff  dw      0xffff
003cf6:  ffff  dw      0xffff
003cf8:  ffff  dw      0xffff
003cfa:  ffff  dw      0xffff
003cfc:  ffff  dw      0xffff
003cfe:  ffff  dw      0xffff
003d00:  ffff  dw      0xffff
003d02:  ffff  dw      0xffff
003d04:  ffff  dw      0xffff
003d06:  ffff  dw      0xffff
003d08:  ffff  dw      0xffff
003d0a:  ffff  dw      0xffff
003d0c:  ffff  dw      0xffff
003d0e:  ffff  dw      0xffff
003d10:  ffff  dw      0xffff
003d12:  ffff  dw      0xffff
003d14:  ffff  dw      0xffff
003d16:  ffff  dw      0xffff
003d18:  ffff  dw      0xffff
003d1a:  ffff  dw      0xffff
003d1c:  ffff  dw      0xffff
003d1e:  ffff  dw      0xffff
003d20:  ffff  dw      0xffff
003d22:  ffff  dw      0xffff
003d24:  ffff  dw      0xffff
003d26:  ffff  dw      0xffff
003d28:  ffff  dw      0xffff
003d2a:  ffff  dw      0xffff
003d2c:  ffff  dw      0xffff
003d2e:  ffff  dw      0xffff
003d30:  ffff  dw      0xffff
003d32:  ffff  dw      0xffff
003d34:  ffff  dw      0xffff
003d36:  ffff  dw      0xffff
003d38:  ffff  dw      0xffff
003d3a:  ffff  dw      0xffff
003d3c:  ffff  dw      0xffff
003d3e:  ffff  dw      0xffff
003d40:  ffff  dw      0xffff
003d42:  ffff  dw      0xffff
003d44:  ffff  dw      0xffff
003d46:  ffff  dw      0xffff
003d48:  ffff  dw      0xffff
003d4a:  ffff  dw      0xffff
003d4c:  ffff  dw      0xffff
003d4e:  ffff  dw      0xffff
003d50:  ffff  dw      0xffff
003d52:  ffff  dw      0xffff
003d54:  ffff  dw      0xffff
003d56:  ffff  dw      0xffff
003d58:  ffff  dw      0xffff
003d5a:  ffff  dw      0xffff
003d5c:  ffff  dw      0xffff
003d5e:  ffff  dw      0xffff
003d60:  ffff  dw      0xffff
003d62:  ffff  dw      0xffff
003d64:  ffff  dw      0xffff
003d66:  ffff  dw      0xffff
003d68:  ffff  dw      0xffff
003d6a:  ffff  dw      0xffff
003d6c:  ffff  dw      0xffff
003d6e:  ffff  dw      0xffff
003d70:  ffff  dw      0xffff
003d72:  ffff  dw      0xffff
003d74:  ffff  dw      0xffff
003d76:  ffff  dw      0xffff
003d78:  ffff  dw      0xffff
003d7a:  ffff  dw      0xffff
003d7c:  ffff  dw      0xffff
003d7e:  ffff  dw      0xffff
003d80:  ffff  dw      0xffff
003d82:  ffff  dw      0xffff
003d84:  ffff  dw      0xffff
003d86:  ffff  dw      0xffff
003d88:  ffff  dw      0xffff
003d8a:  ffff  dw      0xffff
003d8c:  ffff  dw      0xffff
003d8e:  ffff  dw      0xffff
003d90:  ffff  dw      0xffff
003d92:  ffff  dw      0xffff
003d94:  ffff  dw      0xffff
003d96:  ffff  dw      0xffff
003d98:  ffff  dw      0xffff
003d9a:  ffff  dw      0xffff
003d9c:  ffff  dw      0xffff
003d9e:  ffff  dw      0xffff
003da0:  ffff  dw      0xffff
003da2:  ffff  dw      0xffff
003da4:  ffff  dw      0xffff
003da6:  ffff  dw      0xffff
003da8:  ffff  dw      0xffff
003daa:  ffff  dw      0xffff
003dac:  ffff  dw      0xffff
003dae:  ffff  dw      0xffff
003db0:  ffff  dw      0xffff
003db2:  ffff  dw      0xffff
003db4:  ffff  dw      0xffff
003db6:  ffff  dw      0xffff
003db8:  ffff  dw      0xffff
003dba:  ffff  dw      0xffff
003dbc:  ffff  dw      0xffff
003dbe:  ffff  dw      0xffff
003dc0:  ffff  dw      0xffff
003dc2:  ffff  dw      0xffff
003dc4:  ffff  dw      0xffff
003dc6:  ffff  dw      0xffff
003dc8:  ffff  dw      0xffff
003dca:  ffff  dw      0xffff
003dcc:  ffff  dw      0xffff
003dce:  ffff  dw      0xffff
003dd0:  ffff  dw      0xffff
003dd2:  ffff  dw      0xffff
003dd4:  ffff  dw      0xffff
003dd6:  ffff  dw      0xffff
003dd8:  ffff  dw      0xffff
003dda:  ffff  dw      0xffff
003ddc:  ffff  dw      0xffff
003dde:  ffff  dw      0xffff
003de0:  ffff  dw      0xffff
003de2:  ffff  dw      0xffff
003de4:  ffff  dw      0xffff
003de6:  ffff  dw      0xffff
003de8:  ffff  dw      0xffff
003dea:  ffff  dw      0xffff
003dec:  ffff  dw      0xffff
003dee:  ffff  dw      0xffff
003df0:  ffff  dw      0xffff
003df2:  ffff  dw      0xffff
003df4:  ffff  dw      0xffff
003df6:  ffff  dw      0xffff
003df8:  ffff  dw      0xffff
003dfa:  ffff  dw      0xffff
003dfc:  ffff  dw      0xffff
003dfe:  ffff  dw      0xffff
003e00:  ffff  dw      0xffff
003e02:  ffff  dw      0xffff
003e04:  ffff  dw      0xffff
003e06:  ffff  dw      0xffff
003e08:  ffff  dw      0xffff
003e0a:  ffff  dw      0xffff
003e0c:  ffff  dw      0xffff
003e0e:  ffff  dw      0xffff
003e10:  ffff  dw      0xffff
003e12:  ffff  dw      0xffff
003e14:  ffff  dw      0xffff
003e16:  ffff  dw      0xffff
003e18:  ffff  dw      0xffff
003e1a:  ffff  dw      0xffff
003e1c:  ffff  dw      0xffff
003e1e:  ffff  dw      0xffff
003e20:  ffff  dw      0xffff
003e22:  ffff  dw      0xffff
003e24:  ffff  dw      0xffff
003e26:  ffff  dw      0xffff
003e28:  ffff  dw      0xffff
003e2a:  ffff  dw      0xffff
003e2c:  ffff  dw      0xffff
003e2e:  ffff  dw      0xffff
003e30:  ffff  dw      0xffff
003e32:  ffff  dw      0xffff
003e34:  ffff  dw      0xffff
003e36:  ffff  dw      0xffff
003e38:  ffff  dw      0xffff
003e3a:  ffff  dw      0xffff
003e3c:  ffff  dw      0xffff
003e3e:  ffff  dw      0xffff
003e40:  ffff  dw      0xffff
003e42:  ffff  dw      0xffff
003e44:  ffff  dw      0xffff
003e46:  ffff  dw      0xffff
003e48:  ffff  dw      0xffff
003e4a:  ffff  dw      0xffff
003e4c:  ffff  dw      0xffff
003e4e:  ffff  dw      0xffff
003e50:  ffff  dw      0xffff
003e52:  ffff  dw      0xffff
003e54:  ffff  dw      0xffff
003e56:  ffff  dw      0xffff
003e58:  ffff  dw      0xffff
003e5a:  ffff  dw      0xffff
003e5c:  ffff  dw      0xffff
003e5e:  ffff  dw      0xffff
003e60:  ffff  dw      0xffff
003e62:  ffff  dw      0xffff
003e64:  ffff  dw      0xffff
003e66:  ffff  dw      0xffff
003e68:  ffff  dw      0xffff
003e6a:  ffff  dw      0xffff
003e6c:  ffff  dw      0xffff
003e6e:  ffff  dw      0xffff
003e70:  ffff  dw      0xffff
003e72:  ffff  dw      0xffff
003e74:  ffff  dw      0xffff
003e76:  ffff  dw      0xffff
003e78:  ffff  dw      0xffff
003e7a:  ffff  dw      0xffff
003e7c:  ffff  dw      0xffff
003e7e:  ffff  dw      0xffff
003e80:  ffff  dw      0xffff
003e82:  ffff  dw      0xffff
003e84:  ffff  dw      0xffff
003e86:  ffff  dw      0xffff
003e88:  ffff  dw      0xffff
003e8a:  ffff  dw      0xffff
003e8c:  ffff  dw      0xffff
003e8e:  ffff  dw      0xffff
003e90:  ffff  dw      0xffff
003e92:  ffff  dw      0xffff
003e94:  ffff  dw      0xffff
003e96:  ffff  dw      0xffff
003e98:  ffff  dw      0xffff
003e9a:  ffff  dw      0xffff
003e9c:  ffff  dw      0xffff
003e9e:  ffff  dw      0xffff
003ea0:  ffff  dw      0xffff
003ea2:  ffff  dw      0xffff
003ea4:  ffff  dw      0xffff
003ea6:  ffff  dw      0xffff
003ea8:  ffff  dw      0xffff
003eaa:  ffff  dw      0xffff
003eac:  ffff  dw      0xffff
003eae:  ffff  dw      0xffff
003eb0:  ffff  dw      0xffff
003eb2:  ffff  dw      0xffff
003eb4:  ffff  dw      0xffff
003eb6:  ffff  dw      0xffff
003eb8:  ffff  dw      0xffff
003eba:  ffff  dw      0xffff
003ebc:  ffff  dw      0xffff
003ebe:  ffff  dw      0xffff
003ec0:  ffff  dw      0xffff
003ec2:  ffff  dw      0xffff
003ec4:  ffff  dw      0xffff
003ec6:  ffff  dw      0xffff
003ec8:  ffff  dw      0xffff
003eca:  ffff  dw      0xffff
003ecc:  ffff  dw      0xffff
003ece:  ffff  dw      0xffff
003ed0:  ffff  dw      0xffff
003ed2:  ffff  dw      0xffff
003ed4:  ffff  dw      0xffff
003ed6:  ffff  dw      0xffff
003ed8:  ffff  dw      0xffff
003eda:  ffff  dw      0xffff
003edc:  ffff  dw      0xffff
003ede:  ffff  dw      0xffff
003ee0:  ffff  dw      0xffff
003ee2:  ffff  dw      0xffff
003ee4:  ffff  dw      0xffff
003ee6:  ffff  dw      0xffff
003ee8:  ffff  dw      0xffff
003eea:  ffff  dw      0xffff
003eec:  ffff  dw      0xffff
003eee:  ffff  dw      0xffff
003ef0:  ffff  dw      0xffff
003ef2:  ffff  dw      0xffff
003ef4:  ffff  dw      0xffff
003ef6:  ffff  dw      0xffff
003ef8:  ffff  dw      0xffff
003efa:  ffff  dw      0xffff
003efc:  ffff  dw      0xffff
003efe:  ffff  dw      0xffff
003f00:  ffff  dw      0xffff
003f02:  ffff  dw      0xffff
003f04:  ffff  dw      0xffff
003f06:  ffff  dw      0xffff
003f08:  ffff  dw      0xffff
003f0a:  ffff  dw      0xffff
003f0c:  ffff  dw      0xffff
003f0e:  ffff  dw      0xffff
003f10:  ffff  dw      0xffff
003f12:  ffff  dw      0xffff
003f14:  ffff  dw      0xffff
003f16:  ffff  dw      0xffff
003f18:  ffff  dw      0xffff
003f1a:  ffff  dw      0xffff
003f1c:  ffff  dw      0xffff
003f1e:  ffff  dw      0xffff
003f20:  ffff  dw      0xffff
003f22:  ffff  dw      0xffff
003f24:  ffff  dw      0xffff
003f26:  ffff  dw      0xffff
003f28:  ffff  dw      0xffff
003f2a:  ffff  dw      0xffff
003f2c:  ffff  dw      0xffff
003f2e:  ffff  dw      0xffff
003f30:  ffff  dw      0xffff
003f32:  ffff  dw      0xffff
003f34:  ffff  dw      0xffff
003f36:  ffff  dw      0xffff
003f38:  ffff  dw      0xffff
003f3a:  ffff  dw      0xffff
003f3c:  ffff  dw      0xffff
003f3e:  ffff  dw      0xffff
003f40:  ffff  dw      0xffff
003f42:  ffff  dw      0xffff
003f44:  ffff  dw      0xffff
003f46:  ffff  dw      0xffff
003f48:  ffff  dw      0xffff
003f4a:  ffff  dw      0xffff
003f4c:  ffff  dw      0xffff
003f4e:  ffff  dw      0xffff
003f50:  ffff  dw      0xffff
003f52:  ffff  dw      0xffff
003f54:  ffff  dw      0xffff
003f56:  ffff  dw      0xffff
003f58:  ffff  dw      0xffff
003f5a:  ffff  dw      0xffff
003f5c:  ffff  dw      0xffff
003f5e:  ffff  dw      0xffff
003f60:  ffff  dw      0xffff
003f62:  ffff  dw      0xffff
003f64:  ffff  dw      0xffff
003f66:  ffff  dw      0xffff
003f68:  ffff  dw      0xffff
003f6a:  ffff  dw      0xffff
003f6c:  ffff  dw      0xffff
003f6e:  ffff  dw      0xffff
003f70:  ffff  dw      0xffff
003f72:  ffff  dw      0xffff
003f74:  ffff  dw      0xffff
003f76:  ffff  dw      0xffff
003f78:  ffff  dw      0xffff
003f7a:  ffff  dw      0xffff
003f7c:  ffff  dw      0xffff
003f7e:  ffff  dw      0xffff
003f80:  ffff  dw      0xffff
003f82:  ffff  dw      0xffff
003f84:  ffff  dw      0xffff
003f86:  ffff  dw      0xffff
003f88:  ffff  dw      0xffff
003f8a:  ffff  dw      0xffff
003f8c:  ffff  dw      0xffff
003f8e:  ffff  dw      0xffff
003f90:  ffff  dw      0xffff
003f92:  ffff  dw      0xffff
003f94:  ffff  dw      0xffff
003f96:  ffff  dw      0xffff
003f98:  ffff  dw      0xffff
003f9a:  ffff  dw      0xffff
003f9c:  ffff  dw      0xffff
003f9e:  ffff  dw      0xffff
003fa0:  ffff  dw      0xffff
003fa2:  ffff  dw      0xffff
003fa4:  ffff  dw      0xffff
003fa6:  ffff  dw      0xffff
003fa8:  ffff  dw      0xffff
003faa:  ffff  dw      0xffff
003fac:  ffff  dw      0xffff
003fae:  ffff  dw      0xffff
003fb0:  ffff  dw      0xffff
003fb2:  ffff  dw      0xffff
003fb4:  ffff  dw      0xffff
003fb6:  ffff  dw      0xffff
003fb8:  ffff  dw      0xffff
003fba:  ffff  dw      0xffff
003fbc:  ffff  dw      0xffff
003fbe:  ffff  dw      0xffff
003fc0:  ffff  dw      0xffff
003fc2:  ffff  dw      0xffff
003fc4:  ffff  dw      0xffff
003fc6:  ffff  dw      0xffff
003fc8:  ffff  dw      0xffff
003fca:  ffff  dw      0xffff
003fcc:  ffff  dw      0xffff
003fce:  ffff  dw      0xffff
003fd0:  ffff  dw      0xffff
003fd2:  ffff  dw      0xffff
003fd4:  ffff  dw      0xffff
003fd6:  ffff  dw      0xffff
003fd8:  ffff  dw      0xffff
003fda:  ffff  dw      0xffff
003fdc:  ffff  dw      0xffff
003fde:  ffff  dw      0xffff
003fe0:  ffff  dw      0xffff
003fe2:  ffff  dw      0xffff
003fe4:  ffff  dw      0xffff
003fe6:  ffff  dw      0xffff
003fe8:  ffff  dw      0xffff
003fea:  ffff  dw      0xffff
003fec:  ffff  dw      0xffff
003fee:  ffff  dw      0xffff
003ff0:  ffff  dw      0xffff
003ff2:  ffff  dw      0xffff
003ff4:  ffff  dw      0xffff
003ff6:  ffff  dw      0xffff
003ff8:  ffff  dw      0xffff
003ffa:  ffff  dw      0xffff
003ffc:  ffff  dw      0xffff
003ffe:  ffff  dw      0xffff
004000:  ffff  dw      0xffff
004002:  ffff  dw      0xffff
004004:  ffff  dw      0xffff
004006:  ffff  dw      0xffff
004008:  ffff  dw      0xffff
00400a:  ffff  dw      0xffff
00400c:  ffff  dw      0xffff
00400e:  ffff  dw      0xffff
004010:  ffff  dw      0xffff
004012:  ffff  dw      0xffff
004014:  ffff  dw      0xffff
004016:  ffff  dw      0xffff
004018:  ffff  dw      0xffff
00401a:  ffff  dw      0xffff
00401c:  ffff  dw      0xffff
00401e:  ffff  dw      0xffff
004020:  ffff  dw      0xffff
004022:  ffff  dw      0xffff
004024:  ffff  dw      0xffff
004026:  ffff  dw      0xffff
004028:  ffff  dw      0xffff
00402a:  ffff  dw      0xffff
00402c:  ffff  dw      0xffff
00402e:  ffff  dw      0xffff
004030:  ffff  dw      0xffff
004032:  ffff  dw      0xffff
004034:  ffff  dw      0xffff
004036:  ffff  dw      0xffff
004038:  ffff  dw      0xffff
00403a:  ffff  dw      0xffff
00403c:  ffff  dw      0xffff
00403e:  ffff  dw      0xffff
004040:  ffff  dw      0xffff
004042:  ffff  dw      0xffff
004044:  ffff  dw      0xffff
004046:  ffff  dw      0xffff
004048:  ffff  dw      0xffff
00404a:  ffff  dw      0xffff
00404c:  ffff  dw      0xffff
00404e:  ffff  dw      0xffff
004050:  ffff  dw      0xffff
004052:  ffff  dw      0xffff
004054:  ffff  dw      0xffff
004056:  ffff  dw      0xffff
004058:  ffff  dw      0xffff
00405a:  ffff  dw      0xffff
00405c:  ffff  dw      0xffff
00405e:  ffff  dw      0xffff
004060:  ffff  dw      0xffff
004062:  ffff  dw      0xffff
004064:  ffff  dw      0xffff
004066:  ffff  dw      0xffff
004068:  ffff  dw      0xffff
00406a:  ffff  dw      0xffff
00406c:  ffff  dw      0xffff
00406e:  ffff  dw      0xffff
004070:  ffff  dw      0xffff
004072:  ffff  dw      0xffff
004074:  ffff  dw      0xffff
004076:  ffff  dw      0xffff
004078:  ffff  dw      0xffff
00407a:  ffff  dw      0xffff
00407c:  ffff  dw      0xffff
00407e:  ffff  dw      0xffff
004080:  ffff  dw      0xffff
004082:  ffff  dw      0xffff
004084:  ffff  dw      0xffff
004086:  ffff  dw      0xffff
004088:  ffff  dw      0xffff
00408a:  ffff  dw      0xffff
00408c:  ffff  dw      0xffff
00408e:  ffff  dw      0xffff
004090:  ffff  dw      0xffff
004092:  ffff  dw      0xffff
004094:  ffff  dw      0xffff
004096:  ffff  dw      0xffff
004098:  ffff  dw      0xffff
00409a:  ffff  dw      0xffff
00409c:  ffff  dw      0xffff
00409e:  ffff  dw      0xffff
0040a0:  ffff  dw      0xffff
0040a2:  ffff  dw      0xffff
0040a4:  ffff  dw      0xffff
0040a6:  ffff  dw      0xffff
0040a8:  ffff  dw      0xffff
0040aa:  ffff  dw      0xffff
0040ac:  ffff  dw      0xffff
0040ae:  ffff  dw      0xffff
0040b0:  ffff  dw      0xffff
0040b2:  ffff  dw      0xffff
0040b4:  ffff  dw      0xffff
0040b6:  ffff  dw      0xffff
0040b8:  ffff  dw      0xffff
0040ba:  ffff  dw      0xffff
0040bc:  ffff  dw      0xffff
0040be:  ffff  dw      0xffff
0040c0:  ffff  dw      0xffff
0040c2:  ffff  dw      0xffff
0040c4:  ffff  dw      0xffff
0040c6:  ffff  dw      0xffff
0040c8:  ffff  dw      0xffff
0040ca:  ffff  dw      0xffff
0040cc:  ffff  dw      0xffff
0040ce:  ffff  dw      0xffff
0040d0:  ffff  dw      0xffff
0040d2:  ffff  dw      0xffff
0040d4:  ffff  dw      0xffff
0040d6:  ffff  dw      0xffff
0040d8:  ffff  dw      0xffff
0040da:  ffff  dw      0xffff
0040dc:  ffff  dw      0xffff
0040de:  ffff  dw      0xffff
0040e0:  ffff  dw      0xffff
0040e2:  ffff  dw      0xffff
0040e4:  ffff  dw      0xffff
0040e6:  ffff  dw      0xffff
0040e8:  ffff  dw      0xffff
0040ea:  ffff  dw      0xffff
0040ec:  ffff  dw      0xffff
0040ee:  ffff  dw      0xffff
0040f0:  ffff  dw      0xffff
0040f2:  ffff  dw      0xffff
0040f4:  ffff  dw      0xffff
0040f6:  ffff  dw      0xffff
0040f8:  ffff  dw      0xffff
0040fa:  ffff  dw      0xffff
0040fc:  ffff  dw      0xffff
0040fe:  ffff  dw      0xffff
004100:  ffff  dw      0xffff
004102:  ffff  dw      0xffff
004104:  ffff  dw      0xffff
004106:  ffff  dw      0xffff
004108:  ffff  dw      0xffff
00410a:  ffff  dw      0xffff
00410c:  ffff  dw      0xffff
00410e:  ffff  dw      0xffff
004110:  ffff  dw      0xffff
004112:  ffff  dw      0xffff
004114:  ffff  dw      0xffff
004116:  ffff  dw      0xffff
004118:  ffff  dw      0xffff
00411a:  ffff  dw      0xffff
00411c:  ffff  dw      0xffff
00411e:  ffff  dw      0xffff
004120:  ffff  dw      0xffff
004122:  ffff  dw      0xffff
004124:  ffff  dw      0xffff
004126:  ffff  dw      0xffff
004128:  ffff  dw      0xffff
00412a:  ffff  dw      0xffff
00412c:  ffff  dw      0xffff
00412e:  ffff  dw      0xffff
004130:  ffff  dw      0xffff
004132:  ffff  dw      0xffff
004134:  ffff  dw      0xffff
004136:  ffff  dw      0xffff
004138:  ffff  dw      0xffff
00413a:  ffff  dw      0xffff
00413c:  ffff  dw      0xffff
00413e:  ffff  dw      0xffff
004140:  ffff  dw      0xffff
004142:  ffff  dw      0xffff
004144:  ffff  dw      0xffff
004146:  ffff  dw      0xffff
004148:  ffff  dw      0xffff
00414a:  ffff  dw      0xffff
00414c:  ffff  dw      0xffff
00414e:  ffff  dw      0xffff
004150:  ffff  dw      0xffff
004152:  ffff  dw      0xffff
004154:  ffff  dw      0xffff
004156:  ffff  dw      0xffff
004158:  ffff  dw      0xffff
00415a:  ffff  dw      0xffff
00415c:  ffff  dw      0xffff
00415e:  ffff  dw      0xffff
004160:  ffff  dw      0xffff
004162:  ffff  dw      0xffff
004164:  ffff  dw      0xffff
004166:  ffff  dw      0xffff
004168:  ffff  dw      0xffff
00416a:  ffff  dw      0xffff
00416c:  ffff  dw      0xffff
00416e:  ffff  dw      0xffff
004170:  ffff  dw      0xffff
004172:  ffff  dw      0xffff
004174:  ffff  dw      0xffff
004176:  ffff  dw      0xffff
004178:  ffff  dw      0xffff
00417a:  ffff  dw      0xffff
00417c:  ffff  dw      0xffff
00417e:  ffff  dw      0xffff
004180:  ffff  dw      0xffff
004182:  ffff  dw      0xffff
004184:  ffff  dw      0xffff
004186:  ffff  dw      0xffff
004188:  ffff  dw      0xffff
00418a:  ffff  dw      0xffff
00418c:  ffff  dw      0xffff
00418e:  ffff  dw      0xffff
004190:  ffff  dw      0xffff
004192:  ffff  dw      0xffff
004194:  ffff  dw      0xffff
004196:  ffff  dw      0xffff
004198:  ffff  dw      0xffff
00419a:  ffff  dw      0xffff
00419c:  ffff  dw      0xffff
00419e:  ffff  dw      0xffff
0041a0:  ffff  dw      0xffff
0041a2:  ffff  dw      0xffff
0041a4:  ffff  dw      0xffff
0041a6:  ffff  dw      0xffff
0041a8:  ffff  dw      0xffff
0041aa:  ffff  dw      0xffff
0041ac:  ffff  dw      0xffff
0041ae:  ffff  dw      0xffff
0041b0:  ffff  dw      0xffff
0041b2:  ffff  dw      0xffff
0041b4:  ffff  dw      0xffff
0041b6:  ffff  dw      0xffff
0041b8:  ffff  dw      0xffff
0041ba:  ffff  dw      0xffff
0041bc:  ffff  dw      0xffff
0041be:  ffff  dw      0xffff
0041c0:  ffff  dw      0xffff
0041c2:  ffff  dw      0xffff
0041c4:  ffff  dw      0xffff
0041c6:  ffff  dw      0xffff
0041c8:  ffff  dw      0xffff
0041ca:  ffff  dw      0xffff
0041cc:  ffff  dw      0xffff
0041ce:  ffff  dw      0xffff
0041d0:  ffff  dw      0xffff
0041d2:  ffff  dw      0xffff
0041d4:  ffff  dw      0xffff
0041d6:  ffff  dw      0xffff
0041d8:  ffff  dw      0xffff
0041da:  ffff  dw      0xffff
0041dc:  ffff  dw      0xffff
0041de:  ffff  dw      0xffff
0041e0:  ffff  dw      0xffff
0041e2:  ffff  dw      0xffff
0041e4:  ffff  dw      0xffff
0041e6:  ffff  dw      0xffff
0041e8:  ffff  dw      0xffff
0041ea:  ffff  dw      0xffff
0041ec:  ffff  dw      0xffff
0041ee:  ffff  dw      0xffff
0041f0:  ffff  dw      0xffff
0041f2:  ffff  dw      0xffff
0041f4:  ffff  dw      0xffff
0041f6:  ffff  dw      0xffff
0041f8:  ffff  dw      0xffff
0041fa:  ffff  dw      0xffff
0041fc:  ffff  dw      0xffff
0041fe:  ffff  dw      0xffff
004200:  ffff  dw      0xffff
004202:  ffff  dw      0xffff
004204:  ffff  dw      0xffff
004206:  ffff  dw      0xffff
004208:  ffff  dw      0xffff
00420a:  ffff  dw      0xffff
00420c:  ffff  dw      0xffff
00420e:  ffff  dw      0xffff
004210:  ffff  dw      0xffff
004212:  ffff  dw      0xffff
004214:  ffff  dw      0xffff
004216:  ffff  dw      0xffff
004218:  ffff  dw      0xffff
00421a:  ffff  dw      0xffff
00421c:  ffff  dw      0xffff
00421e:  ffff  dw      0xffff
004220:  ffff  dw      0xffff
004222:  ffff  dw      0xffff
004224:  ffff  dw      0xffff
004226:  ffff  dw      0xffff
004228:  ffff  dw      0xffff
00422a:  ffff  dw      0xffff
00422c:  ffff  dw      0xffff
00422e:  ffff  dw      0xffff
004230:  ffff  dw      0xffff
004232:  ffff  dw      0xffff
004234:  ffff  dw      0xffff
004236:  ffff  dw      0xffff
004238:  ffff  dw      0xffff
00423a:  ffff  dw      0xffff
00423c:  ffff  dw      0xffff
00423e:  ffff  dw      0xffff
004240:  ffff  dw      0xffff
004242:  ffff  dw      0xffff
004244:  ffff  dw      0xffff
004246:  ffff  dw      0xffff
004248:  ffff  dw      0xffff
00424a:  ffff  dw      0xffff
00424c:  ffff  dw      0xffff
00424e:  ffff  dw      0xffff
004250:  ffff  dw      0xffff
004252:  ffff  dw      0xffff
004254:  ffff  dw      0xffff
004256:  ffff  dw      0xffff
004258:  ffff  dw      0xffff
00425a:  ffff  dw      0xffff
00425c:  ffff  dw      0xffff
00425e:  ffff  dw      0xffff
004260:  ffff  dw      0xffff
004262:  ffff  dw      0xffff
004264:  ffff  dw      0xffff
004266:  ffff  dw      0xffff
004268:  ffff  dw      0xffff
00426a:  ffff  dw      0xffff
00426c:  ffff  dw      0xffff
00426e:  ffff  dw      0xffff
004270:  ffff  dw      0xffff
004272:  ffff  dw      0xffff
004274:  ffff  dw      0xffff
004276:  ffff  dw      0xffff
004278:  ffff  dw      0xffff
00427a:  ffff  dw      0xffff
00427c:  ffff  dw      0xffff
00427e:  ffff  dw      0xffff
004280:  ffff  dw      0xffff
004282:  ffff  dw      0xffff
004284:  ffff  dw      0xffff
004286:  ffff  dw      0xffff
004288:  ffff  dw      0xffff
00428a:  ffff  dw      0xffff
00428c:  ffff  dw      0xffff
00428e:  ffff  dw      0xffff
004290:  ffff  dw      0xffff
004292:  ffff  dw      0xffff
004294:  ffff  dw      0xffff
004296:  ffff  dw      0xffff
004298:  ffff  dw      0xffff
00429a:  ffff  dw      0xffff
00429c:  ffff  dw      0xffff
00429e:  ffff  dw      0xffff
0042a0:  ffff  dw      0xffff
0042a2:  ffff  dw      0xffff
0042a4:  ffff  dw      0xffff
0042a6:  ffff  dw      0xffff
0042a8:  ffff  dw      0xffff
0042aa:  ffff  dw      0xffff
0042ac:  ffff  dw      0xffff
0042ae:  ffff  dw      0xffff
0042b0:  ffff  dw      0xffff
0042b2:  ffff  dw      0xffff
0042b4:  ffff  dw      0xffff
0042b6:  ffff  dw      0xffff
0042b8:  ffff  dw      0xffff
0042ba:  ffff  dw      0xffff
0042bc:  ffff  dw      0xffff
0042be:  ffff  dw      0xffff
0042c0:  ffff  dw      0xffff
0042c2:  ffff  dw      0xffff
0042c4:  ffff  dw      0xffff
0042c6:  ffff  dw      0xffff
0042c8:  ffff  dw      0xffff
0042ca:  ffff  dw      0xffff
0042cc:  ffff  dw      0xffff
0042ce:  ffff  dw      0xffff
0042d0:  ffff  dw      0xffff
0042d2:  ffff  dw      0xffff
0042d4:  ffff  dw      0xffff
0042d6:  ffff  dw      0xffff
0042d8:  ffff  dw      0xffff
0042da:  ffff  dw      0xffff
0042dc:  ffff  dw      0xffff
0042de:  ffff  dw      0xffff
0042e0:  ffff  dw      0xffff
0042e2:  ffff  dw      0xffff
0042e4:  ffff  dw      0xffff
0042e6:  ffff  dw      0xffff
0042e8:  ffff  dw      0xffff
0042ea:  ffff  dw      0xffff
0042ec:  ffff  dw      0xffff
0042ee:  ffff  dw      0xffff
0042f0:  ffff  dw      0xffff
0042f2:  ffff  dw      0xffff
0042f4:  ffff  dw      0xffff
0042f6:  ffff  dw      0xffff
0042f8:  ffff  dw      0xffff
0042fa:  ffff  dw      0xffff
0042fc:  ffff  dw      0xffff
0042fe:  ffff  dw      0xffff
004300:  ffff  dw      0xffff
004302:  ffff  dw      0xffff
004304:  ffff  dw      0xffff
004306:  ffff  dw      0xffff
004308:  ffff  dw      0xffff
00430a:  ffff  dw      0xffff
00430c:  ffff  dw      0xffff
00430e:  ffff  dw      0xffff
004310:  ffff  dw      0xffff
004312:  ffff  dw      0xffff
004314:  ffff  dw      0xffff
004316:  ffff  dw      0xffff
004318:  ffff  dw      0xffff
00431a:  ffff  dw      0xffff
00431c:  ffff  dw      0xffff
00431e:  ffff  dw      0xffff
004320:  ffff  dw      0xffff
004322:  ffff  dw      0xffff
004324:  ffff  dw      0xffff
004326:  ffff  dw      0xffff
004328:  ffff  dw      0xffff
00432a:  ffff  dw      0xffff
00432c:  ffff  dw      0xffff
00432e:  ffff  dw      0xffff
004330:  ffff  dw      0xffff
004332:  ffff  dw      0xffff
004334:  ffff  dw      0xffff
004336:  ffff  dw      0xffff
004338:  ffff  dw      0xffff
00433a:  ffff  dw      0xffff
00433c:  ffff  dw      0xffff
00433e:  ffff  dw      0xffff
004340:  ffff  dw      0xffff
004342:  ffff  dw      0xffff
004344:  ffff  dw      0xffff
004346:  ffff  dw      0xffff
004348:  ffff  dw      0xffff
00434a:  ffff  dw      0xffff
00434c:  ffff  dw      0xffff
00434e:  ffff  dw      0xffff
004350:  ffff  dw      0xffff
004352:  ffff  dw      0xffff
004354:  ffff  dw      0xffff
004356:  ffff  dw      0xffff
004358:  ffff  dw      0xffff
00435a:  ffff  dw      0xffff
00435c:  ffff  dw      0xffff
00435e:  ffff  dw      0xffff
004360:  ffff  dw      0xffff
004362:  ffff  dw      0xffff
004364:  ffff  dw      0xffff
004366:  ffff  dw      0xffff
004368:  ffff  dw      0xffff
00436a:  ffff  dw      0xffff
00436c:  ffff  dw      0xffff
00436e:  ffff  dw      0xffff
004370:  ffff  dw      0xffff
004372:  ffff  dw      0xffff
004374:  ffff  dw      0xffff
004376:  ffff  dw      0xffff
004378:  ffff  dw      0xffff
00437a:  ffff  dw      0xffff
00437c:  ffff  dw      0xffff
00437e:  ffff  dw      0xffff
004380:  ffff  dw      0xffff
004382:  ffff  dw      0xffff
004384:  ffff  dw      0xffff
004386:  ffff  dw      0xffff
004388:  ffff  dw      0xffff
00438a:  ffff  dw      0xffff
00438c:  ffff  dw      0xffff
00438e:  ffff  dw      0xffff
004390:  ffff  dw      0xffff
004392:  ffff  dw      0xffff
004394:  ffff  dw      0xffff
004396:  ffff  dw      0xffff
004398:  ffff  dw      0xffff
00439a:  ffff  dw      0xffff
00439c:  ffff  dw      0xffff
00439e:  ffff  dw      0xffff
0043a0:  ffff  dw      0xffff
0043a2:  ffff  dw      0xffff
0043a4:  ffff  dw      0xffff
0043a6:  ffff  dw      0xffff
0043a8:  ffff  dw      0xffff
0043aa:  ffff  dw      0xffff
0043ac:  ffff  dw      0xffff
0043ae:  ffff  dw      0xffff
0043b0:  ffff  dw      0xffff
0043b2:  ffff  dw      0xffff
0043b4:  ffff  dw      0xffff
0043b6:  ffff  dw      0xffff
0043b8:  ffff  dw      0xffff
0043ba:  ffff  dw      0xffff
0043bc:  ffff  dw      0xffff
0043be:  ffff  dw      0xffff
0043c0:  ffff  dw      0xffff
0043c2:  ffff  dw      0xffff
0043c4:  ffff  dw      0xffff
0043c6:  ffff  dw      0xffff
0043c8:  ffff  dw      0xffff
0043ca:  ffff  dw      0xffff
0043cc:  ffff  dw      0xffff
0043ce:  ffff  dw      0xffff
0043d0:  ffff  dw      0xffff
0043d2:  ffff  dw      0xffff
0043d4:  ffff  dw      0xffff
0043d6:  ffff  dw      0xffff
0043d8:  ffff  dw      0xffff
0043da:  ffff  dw      0xffff
0043dc:  ffff  dw      0xffff
0043de:  ffff  dw      0xffff
0043e0:  ffff  dw      0xffff
0043e2:  ffff  dw      0xffff
0043e4:  ffff  dw      0xffff
0043e6:  ffff  dw      0xffff
0043e8:  ffff  dw      0xffff
0043ea:  ffff  dw      0xffff
0043ec:  ffff  dw      0xffff
0043ee:  ffff  dw      0xffff
0043f0:  ffff  dw      0xffff
0043f2:  ffff  dw      0xffff
0043f4:  ffff  dw      0xffff
0043f6:  ffff  dw      0xffff
0043f8:  ffff  dw      0xffff
0043fa:  ffff  dw      0xffff
0043fc:  ffff  dw      0xffff
0043fe:  ffff  dw      0xffff
004400:  ffff  dw      0xffff
004402:  ffff  dw      0xffff
004404:  ffff  dw      0xffff
004406:  ffff  dw      0xffff
004408:  ffff  dw      0xffff
00440a:  ffff  dw      0xffff
00440c:  ffff  dw      0xffff
00440e:  ffff  dw      0xffff
004410:  ffff  dw      0xffff
004412:  ffff  dw      0xffff
004414:  ffff  dw      0xffff
004416:  ffff  dw      0xffff
004418:  ffff  dw      0xffff
00441a:  ffff  dw      0xffff
00441c:  ffff  dw      0xffff
00441e:  ffff  dw      0xffff
004420:  ffff  dw      0xffff
004422:  ffff  dw      0xffff
004424:  ffff  dw      0xffff
004426:  ffff  dw      0xffff
004428:  ffff  dw      0xffff
00442a:  ffff  dw      0xffff
00442c:  ffff  dw      0xffff
00442e:  ffff  dw      0xffff
004430:  ffff  dw      0xffff
004432:  ffff  dw      0xffff
004434:  ffff  dw      0xffff
004436:  ffff  dw      0xffff
004438:  ffff  dw      0xffff
00443a:  ffff  dw      0xffff
00443c:  ffff  dw      0xffff
00443e:  ffff  dw      0xffff
004440:  ffff  dw      0xffff
004442:  ffff  dw      0xffff
004444:  ffff  dw      0xffff
004446:  ffff  dw      0xffff
004448:  ffff  dw      0xffff
00444a:  ffff  dw      0xffff
00444c:  ffff  dw      0xffff
00444e:  ffff  dw      0xffff
004450:  ffff  dw      0xffff
004452:  ffff  dw      0xffff
004454:  ffff  dw      0xffff
004456:  ffff  dw      0xffff
004458:  ffff  dw      0xffff
00445a:  ffff  dw      0xffff
00445c:  ffff  dw      0xffff
00445e:  ffff  dw      0xffff
004460:  ffff  dw      0xffff
004462:  ffff  dw      0xffff
004464:  ffff  dw      0xffff
004466:  ffff  dw      0xffff
004468:  ffff  dw      0xffff
00446a:  ffff  dw      0xffff
00446c:  ffff  dw      0xffff
00446e:  ffff  dw      0xffff
004470:  ffff  dw      0xffff
004472:  ffff  dw      0xffff
004474:  ffff  dw      0xffff
004476:  ffff  dw      0xffff
004478:  ffff  dw      0xffff
00447a:  ffff  dw      0xffff
00447c:  ffff  dw      0xffff
00447e:  ffff  dw      0xffff
004480:  ffff  dw      0xffff
004482:  ffff  dw      0xffff
004484:  ffff  dw      0xffff
004486:  ffff  dw      0xffff
004488:  ffff  dw      0xffff
00448a:  ffff  dw      0xffff
00448c:  ffff  dw      0xffff
00448e:  ffff  dw      0xffff
004490:  ffff  dw      0xffff
004492:  ffff  dw      0xffff
004494:  ffff  dw      0xffff
004496:  ffff  dw      0xffff
004498:  ffff  dw      0xffff
00449a:  ffff  dw      0xffff
00449c:  ffff  dw      0xffff
00449e:  ffff  dw      0xffff
0044a0:  ffff  dw      0xffff
0044a2:  ffff  dw      0xffff
0044a4:  ffff  dw      0xffff
0044a6:  ffff  dw      0xffff
0044a8:  ffff  dw      0xffff
0044aa:  ffff  dw      0xffff
0044ac:  ffff  dw      0xffff
0044ae:  ffff  dw      0xffff
0044b0:  ffff  dw      0xffff
0044b2:  ffff  dw      0xffff
0044b4:  ffff  dw      0xffff
0044b6:  ffff  dw      0xffff
0044b8:  ffff  dw      0xffff
0044ba:  ffff  dw      0xffff
0044bc:  ffff  dw      0xffff
0044be:  ffff  dw      0xffff
0044c0:  ffff  dw      0xffff
0044c2:  ffff  dw      0xffff
0044c4:  ffff  dw      0xffff
0044c6:  ffff  dw      0xffff
0044c8:  ffff  dw      0xffff
0044ca:  ffff  dw      0xffff
0044cc:  ffff  dw      0xffff
0044ce:  ffff  dw      0xffff
0044d0:  ffff  dw      0xffff
0044d2:  ffff  dw      0xffff
0044d4:  ffff  dw      0xffff
0044d6:  ffff  dw      0xffff
0044d8:  ffff  dw      0xffff
0044da:  ffff  dw      0xffff
0044dc:  ffff  dw      0xffff
0044de:  ffff  dw      0xffff
0044e0:  ffff  dw      0xffff
0044e2:  ffff  dw      0xffff
0044e4:  ffff  dw      0xffff
0044e6:  ffff  dw      0xffff
0044e8:  ffff  dw      0xffff
0044ea:  ffff  dw      0xffff
0044ec:  ffff  dw      0xffff
0044ee:  ffff  dw      0xffff
0044f0:  ffff  dw      0xffff
0044f2:  ffff  dw      0xffff
0044f4:  ffff  dw      0xffff
0044f6:  ffff  dw      0xffff
0044f8:  ffff  dw      0xffff
0044fa:  ffff  dw      0xffff
0044fc:  ffff  dw      0xffff
0044fe:  ffff  dw      0xffff
004500:  ffff  dw      0xffff
004502:  ffff  dw      0xffff
004504:  ffff  dw      0xffff
004506:  ffff  dw      0xffff
004508:  ffff  dw      0xffff
00450a:  ffff  dw      0xffff
00450c:  ffff  dw      0xffff
00450e:  ffff  dw      0xffff
004510:  ffff  dw      0xffff
004512:  ffff  dw      0xffff
004514:  ffff  dw      0xffff
004516:  ffff  dw      0xffff
004518:  ffff  dw      0xffff
00451a:  ffff  dw      0xffff
00451c:  ffff  dw      0xffff
00451e:  ffff  dw      0xffff
004520:  ffff  dw      0xffff
004522:  ffff  dw      0xffff
004524:  ffff  dw      0xffff
004526:  ffff  dw      0xffff
004528:  ffff  dw      0xffff
00452a:  ffff  dw      0xffff
00452c:  ffff  dw      0xffff
00452e:  ffff  dw      0xffff
004530:  ffff  dw      0xffff
004532:  ffff  dw      0xffff
004534:  ffff  dw      0xffff
004536:  ffff  dw      0xffff
004538:  ffff  dw      0xffff
00453a:  ffff  dw      0xffff
00453c:  ffff  dw      0xffff
00453e:  ffff  dw      0xffff
004540:  ffff  dw      0xffff
004542:  ffff  dw      0xffff
004544:  ffff  dw      0xffff
004546:  ffff  dw      0xffff
004548:  ffff  dw      0xffff
00454a:  ffff  dw      0xffff
00454c:  ffff  dw      0xffff
00454e:  ffff  dw      0xffff
004550:  ffff  dw      0xffff
004552:  ffff  dw      0xffff
004554:  ffff  dw      0xffff
004556:  ffff  dw      0xffff
004558:  ffff  dw      0xffff
00455a:  ffff  dw      0xffff
00455c:  ffff  dw      0xffff
00455e:  ffff  dw      0xffff
004560:  ffff  dw      0xffff
004562:  ffff  dw      0xffff
004564:  ffff  dw      0xffff
004566:  ffff  dw      0xffff
004568:  ffff  dw      0xffff
00456a:  ffff  dw      0xffff
00456c:  ffff  dw      0xffff
00456e:  ffff  dw      0xffff
004570:  ffff  dw      0xffff
004572:  ffff  dw      0xffff
004574:  ffff  dw      0xffff
004576:  ffff  dw      0xffff
004578:  ffff  dw      0xffff
00457a:  ffff  dw      0xffff
00457c:  ffff  dw      0xffff
00457e:  ffff  dw      0xffff
004580:  ffff  dw      0xffff
004582:  ffff  dw      0xffff
004584:  ffff  dw      0xffff
004586:  ffff  dw      0xffff
004588:  ffff  dw      0xffff
00458a:  ffff  dw      0xffff
00458c:  ffff  dw      0xffff
00458e:  ffff  dw      0xffff
004590:  ffff  dw      0xffff
004592:  ffff  dw      0xffff
004594:  ffff  dw      0xffff
004596:  ffff  dw      0xffff
004598:  ffff  dw      0xffff
00459a:  ffff  dw      0xffff
00459c:  ffff  dw      0xffff
00459e:  ffff  dw      0xffff
0045a0:  ffff  dw      0xffff
0045a2:  ffff  dw      0xffff
0045a4:  ffff  dw      0xffff
0045a6:  ffff  dw      0xffff
0045a8:  ffff  dw      0xffff
0045aa:  ffff  dw      0xffff
0045ac:  ffff  dw      0xffff
0045ae:  ffff  dw      0xffff
0045b0:  ffff  dw      0xffff
0045b2:  ffff  dw      0xffff
0045b4:  ffff  dw      0xffff
0045b6:  ffff  dw      0xffff
0045b8:  ffff  dw      0xffff
0045ba:  ffff  dw      0xffff
0045bc:  ffff  dw      0xffff
0045be:  ffff  dw      0xffff
0045c0:  ffff  dw      0xffff
0045c2:  ffff  dw      0xffff
0045c4:  ffff  dw      0xffff
0045c6:  ffff  dw      0xffff
0045c8:  ffff  dw      0xffff
0045ca:  ffff  dw      0xffff
0045cc:  ffff  dw      0xffff
0045ce:  ffff  dw      0xffff
0045d0:  ffff  dw      0xffff
0045d2:  ffff  dw      0xffff
0045d4:  ffff  dw      0xffff
0045d6:  ffff  dw      0xffff
0045d8:  ffff  dw      0xffff
0045da:  ffff  dw      0xffff
0045dc:  ffff  dw      0xffff
0045de:  ffff  dw      0xffff
0045e0:  ffff  dw      0xffff
0045e2:  ffff  dw      0xffff
0045e4:  ffff  dw      0xffff
0045e6:  ffff  dw      0xffff
0045e8:  ffff  dw      0xffff
0045ea:  ffff  dw      0xffff
0045ec:  ffff  dw      0xffff
0045ee:  ffff  dw      0xffff
0045f0:  ffff  dw      0xffff
0045f2:  ffff  dw      0xffff
0045f4:  ffff  dw      0xffff
0045f6:  ffff  dw      0xffff
0045f8:  ffff  dw      0xffff
0045fa:  ffff  dw      0xffff
0045fc:  ffff  dw      0xffff
0045fe:  ffff  dw      0xffff
004600:  ffff  dw      0xffff
004602:  ffff  dw      0xffff
004604:  ffff  dw      0xffff
004606:  ffff  dw      0xffff
004608:  ffff  dw      0xffff
00460a:  ffff  dw      0xffff
00460c:  ffff  dw      0xffff
00460e:  ffff  dw      0xffff
004610:  ffff  dw      0xffff
004612:  ffff  dw      0xffff
004614:  ffff  dw      0xffff
004616:  ffff  dw      0xffff
004618:  ffff  dw      0xffff
00461a:  ffff  dw      0xffff
00461c:  ffff  dw      0xffff
00461e:  ffff  dw      0xffff
004620:  ffff  dw      0xffff
004622:  ffff  dw      0xffff
004624:  ffff  dw      0xffff
004626:  ffff  dw      0xffff
004628:  ffff  dw      0xffff
00462a:  ffff  dw      0xffff
00462c:  ffff  dw      0xffff
00462e:  ffff  dw      0xffff
004630:  ffff  dw      0xffff
004632:  ffff  dw      0xffff
004634:  ffff  dw      0xffff
004636:  ffff  dw      0xffff
004638:  ffff  dw      0xffff
00463a:  ffff  dw      0xffff
00463c:  ffff  dw      0xffff
00463e:  ffff  dw      0xffff
004640:  ffff  dw      0xffff
004642:  ffff  dw      0xffff
004644:  ffff  dw      0xffff
004646:  ffff  dw      0xffff
004648:  ffff  dw      0xffff
00464a:  ffff  dw      0xffff
00464c:  ffff  dw      0xffff
00464e:  ffff  dw      0xffff
004650:  ffff  dw      0xffff
004652:  ffff  dw      0xffff
004654:  ffff  dw      0xffff
004656:  ffff  dw      0xffff
004658:  ffff  dw      0xffff
00465a:  ffff  dw      0xffff
00465c:  ffff  dw      0xffff
00465e:  ffff  dw      0xffff
004660:  ffff  dw      0xffff
004662:  ffff  dw      0xffff
004664:  ffff  dw      0xffff
004666:  ffff  dw      0xffff
004668:  ffff  dw      0xffff
00466a:  ffff  dw      0xffff
00466c:  ffff  dw      0xffff
00466e:  ffff  dw      0xffff
004670:  ffff  dw      0xffff
004672:  ffff  dw      0xffff
004674:  ffff  dw      0xffff
004676:  ffff  dw      0xffff
004678:  ffff  dw      0xffff
00467a:  ffff  dw      0xffff
00467c:  ffff  dw      0xffff
00467e:  ffff  dw      0xffff
004680:  ffff  dw      0xffff
004682:  ffff  dw      0xffff
004684:  ffff  dw      0xffff
004686:  ffff  dw      0xffff
004688:  ffff  dw      0xffff
00468a:  ffff  dw      0xffff
00468c:  ffff  dw      0xffff
00468e:  ffff  dw      0xffff
004690:  ffff  dw      0xffff
004692:  ffff  dw      0xffff
004694:  ffff  dw      0xffff
004696:  ffff  dw      0xffff
004698:  ffff  dw      0xffff
00469a:  ffff  dw      0xffff
00469c:  ffff  dw      0xffff
00469e:  ffff  dw      0xffff
0046a0:  ffff  dw      0xffff
0046a2:  ffff  dw      0xffff
0046a4:  ffff  dw      0xffff
0046a6:  ffff  dw      0xffff
0046a8:  ffff  dw      0xffff
0046aa:  ffff  dw      0xffff
0046ac:  ffff  dw      0xffff
0046ae:  ffff  dw      0xffff
0046b0:  ffff  dw      0xffff
0046b2:  ffff  dw      0xffff
0046b4:  ffff  dw      0xffff
0046b6:  ffff  dw      0xffff
0046b8:  ffff  dw      0xffff
0046ba:  ffff  dw      0xffff
0046bc:  ffff  dw      0xffff
0046be:  ffff  dw      0xffff
0046c0:  ffff  dw      0xffff
0046c2:  ffff  dw      0xffff
0046c4:  ffff  dw      0xffff
0046c6:  ffff  dw      0xffff
0046c8:  ffff  dw      0xffff
0046ca:  ffff  dw      0xffff
0046cc:  ffff  dw      0xffff
0046ce:  ffff  dw      0xffff
0046d0:  ffff  dw      0xffff
0046d2:  ffff  dw      0xffff
0046d4:  ffff  dw      0xffff
0046d6:  ffff  dw      0xffff
0046d8:  ffff  dw      0xffff
0046da:  ffff  dw      0xffff
0046dc:  ffff  dw      0xffff
0046de:  ffff  dw      0xffff
0046e0:  ffff  dw      0xffff
0046e2:  ffff  dw      0xffff
0046e4:  ffff  dw      0xffff
0046e6:  ffff  dw      0xffff
0046e8:  ffff  dw      0xffff
0046ea:  ffff  dw      0xffff
0046ec:  ffff  dw      0xffff
0046ee:  ffff  dw      0xffff
0046f0:  ffff  dw      0xffff
0046f2:  ffff  dw      0xffff
0046f4:  ffff  dw      0xffff
0046f6:  ffff  dw      0xffff
0046f8:  ffff  dw      0xffff
0046fa:  ffff  dw      0xffff
0046fc:  ffff  dw      0xffff
0046fe:  ffff  dw      0xffff
004700:  ffff  dw      0xffff
004702:  ffff  dw      0xffff
004704:  ffff  dw      0xffff
004706:  ffff  dw      0xffff
004708:  ffff  dw      0xffff
00470a:  ffff  dw      0xffff
00470c:  ffff  dw      0xffff
00470e:  ffff  dw      0xffff
004710:  ffff  dw      0xffff
004712:  ffff  dw      0xffff
004714:  ffff  dw      0xffff
004716:  ffff  dw      0xffff
004718:  ffff  dw      0xffff
00471a:  ffff  dw      0xffff
00471c:  ffff  dw      0xffff
00471e:  ffff  dw      0xffff
004720:  ffff  dw      0xffff
004722:  ffff  dw      0xffff
004724:  ffff  dw      0xffff
004726:  ffff  dw      0xffff
004728:  ffff  dw      0xffff
00472a:  ffff  dw      0xffff
00472c:  ffff  dw      0xffff
00472e:  ffff  dw      0xffff
004730:  ffff  dw      0xffff
004732:  ffff  dw      0xffff
004734:  ffff  dw      0xffff
004736:  ffff  dw      0xffff
004738:  ffff  dw      0xffff
00473a:  ffff  dw      0xffff
00473c:  ffff  dw      0xffff
00473e:  ffff  dw      0xffff
004740:  ffff  dw      0xffff
004742:  ffff  dw      0xffff
004744:  ffff  dw      0xffff
004746:  ffff  dw      0xffff
004748:  ffff  dw      0xffff
00474a:  ffff  dw      0xffff
00474c:  ffff  dw      0xffff
00474e:  ffff  dw      0xffff
004750:  ffff  dw      0xffff
004752:  ffff  dw      0xffff
004754:  ffff  dw      0xffff
004756:  ffff  dw      0xffff
004758:  ffff  dw      0xffff
00475a:  ffff  dw      0xffff
00475c:  ffff  dw      0xffff
00475e:  ffff  dw      0xffff
004760:  ffff  dw      0xffff
004762:  ffff  dw      0xffff
004764:  ffff  dw      0xffff
004766:  ffff  dw      0xffff
004768:  ffff  dw      0xffff
00476a:  ffff  dw      0xffff
00476c:  ffff  dw      0xffff
00476e:  ffff  dw      0xffff
004770:  ffff  dw      0xffff
004772:  ffff  dw      0xffff
004774:  ffff  dw      0xffff
004776:  ffff  dw      0xffff
004778:  ffff  dw      0xffff
00477a:  ffff  dw      0xffff
00477c:  ffff  dw      0xffff
00477e:  ffff  dw      0xffff
004780:  ffff  dw      0xffff
004782:  ffff  dw      0xffff
004784:  ffff  dw      0xffff
004786:  ffff  dw      0xffff
004788:  ffff  dw      0xffff
00478a:  ffff  dw      0xffff
00478c:  ffff  dw      0xffff
00478e:  ffff  dw      0xffff
004790:  ffff  dw      0xffff
004792:  ffff  dw      0xffff
004794:  ffff  dw      0xffff
004796:  ffff  dw      0xffff
004798:  ffff  dw      0xffff
00479a:  ffff  dw      0xffff
00479c:  ffff  dw      0xffff
00479e:  ffff  dw      0xffff
0047a0:  ffff  dw      0xffff
0047a2:  ffff  dw      0xffff
0047a4:  ffff  dw      0xffff
0047a6:  ffff  dw      0xffff
0047a8:  ffff  dw      0xffff
0047aa:  ffff  dw      0xffff
0047ac:  ffff  dw      0xffff
0047ae:  ffff  dw      0xffff
0047b0:  ffff  dw      0xffff
0047b2:  ffff  dw      0xffff
0047b4:  ffff  dw      0xffff
0047b6:  ffff  dw      0xffff
0047b8:  ffff  dw      0xffff
0047ba:  ffff  dw      0xffff
0047bc:  ffff  dw      0xffff
0047be:  ffff  dw      0xffff
0047c0:  ffff  dw      0xffff
0047c2:  ffff  dw      0xffff
0047c4:  ffff  dw      0xffff
0047c6:  ffff  dw      0xffff
0047c8:  ffff  dw      0xffff
0047ca:  ffff  dw      0xffff
0047cc:  ffff  dw      0xffff
0047ce:  ffff  dw      0xffff
0047d0:  ffff  dw      0xffff
0047d2:  ffff  dw      0xffff
0047d4:  ffff  dw      0xffff
0047d6:  ffff  dw      0xffff
0047d8:  ffff  dw      0xffff
0047da:  ffff  dw      0xffff
0047dc:  ffff  dw      0xffff
0047de:  ffff  dw      0xffff
0047e0:  ffff  dw      0xffff
0047e2:  ffff  dw      0xffff
0047e4:  ffff  dw      0xffff
0047e6:  ffff  dw      0xffff
0047e8:  ffff  dw      0xffff
0047ea:  ffff  dw      0xffff
0047ec:  ffff  dw      0xffff
0047ee:  ffff  dw      0xffff
0047f0:  ffff  dw      0xffff
0047f2:  ffff  dw      0xffff
0047f4:  ffff  dw      0xffff
0047f6:  ffff  dw      0xffff
0047f8:  ffff  dw      0xffff
0047fa:  ffff  dw      0xffff
0047fc:  ffff  dw      0xffff
0047fe:  ffff  dw      0xffff
004800:  ffff  dw      0xffff
004802:  ffff  dw      0xffff
004804:  ffff  dw      0xffff
004806:  ffff  dw      0xffff
004808:  ffff  dw      0xffff
00480a:  ffff  dw      0xffff
00480c:  ffff  dw      0xffff
00480e:  ffff  dw      0xffff
004810:  ffff  dw      0xffff
004812:  ffff  dw      0xffff
004814:  ffff  dw      0xffff
004816:  ffff  dw      0xffff
004818:  ffff  dw      0xffff
00481a:  ffff  dw      0xffff
00481c:  ffff  dw      0xffff
00481e:  ffff  dw      0xffff
004820:  ffff  dw      0xffff
004822:  ffff  dw      0xffff
004824:  ffff  dw      0xffff
004826:  ffff  dw      0xffff
004828:  ffff  dw      0xffff
00482a:  ffff  dw      0xffff
00482c:  ffff  dw      0xffff
00482e:  ffff  dw      0xffff
004830:  ffff  dw      0xffff
004832:  ffff  dw      0xffff
004834:  ffff  dw      0xffff
004836:  ffff  dw      0xffff
004838:  ffff  dw      0xffff
00483a:  ffff  dw      0xffff
00483c:  ffff  dw      0xffff
00483e:  ffff  dw      0xffff
004840:  ffff  dw      0xffff
004842:  ffff  dw      0xffff
004844:  ffff  dw      0xffff
004846:  ffff  dw      0xffff
004848:  ffff  dw      0xffff
00484a:  ffff  dw      0xffff
00484c:  ffff  dw      0xffff
00484e:  ffff  dw      0xffff
004850:  ffff  dw      0xffff
004852:  ffff  dw      0xffff
004854:  ffff  dw      0xffff
004856:  ffff  dw      0xffff
004858:  ffff  dw      0xffff
00485a:  ffff  dw      0xffff
00485c:  ffff  dw      0xffff
00485e:  ffff  dw      0xffff
004860:  ffff  dw      0xffff
004862:  ffff  dw      0xffff
004864:  ffff  dw      0xffff
004866:  ffff  dw      0xffff
004868:  ffff  dw      0xffff
00486a:  ffff  dw      0xffff
00486c:  ffff  dw      0xffff
00486e:  ffff  dw      0xffff
004870:  ffff  dw      0xffff
004872:  ffff  dw      0xffff
004874:  ffff  dw      0xffff
004876:  ffff  dw      0xffff
004878:  ffff  dw      0xffff
00487a:  ffff  dw      0xffff
00487c:  ffff  dw      0xffff
00487e:  ffff  dw      0xffff
004880:  ffff  dw      0xffff
004882:  ffff  dw      0xffff
004884:  ffff  dw      0xffff
004886:  ffff  dw      0xffff
004888:  ffff  dw      0xffff
00488a:  ffff  dw      0xffff
00488c:  ffff  dw      0xffff
00488e:  ffff  dw      0xffff
004890:  ffff  dw      0xffff
004892:  ffff  dw      0xffff
004894:  ffff  dw      0xffff
004896:  ffff  dw      0xffff
004898:  ffff  dw      0xffff
00489a:  ffff  dw      0xffff
00489c:  ffff  dw      0xffff
00489e:  ffff  dw      0xffff
0048a0:  ffff  dw      0xffff
0048a2:  ffff  dw      0xffff
0048a4:  ffff  dw      0xffff
0048a6:  ffff  dw      0xffff
0048a8:  ffff  dw      0xffff
0048aa:  ffff  dw      0xffff
0048ac:  ffff  dw      0xffff
0048ae:  ffff  dw      0xffff
0048b0:  ffff  dw      0xffff
0048b2:  ffff  dw      0xffff
0048b4:  ffff  dw      0xffff
0048b6:  ffff  dw      0xffff
0048b8:  ffff  dw      0xffff
0048ba:  ffff  dw      0xffff
0048bc:  ffff  dw      0xffff
0048be:  ffff  dw      0xffff
0048c0:  ffff  dw      0xffff
0048c2:  ffff  dw      0xffff
0048c4:  ffff  dw      0xffff
0048c6:  ffff  dw      0xffff
0048c8:  ffff  dw      0xffff
0048ca:  ffff  dw      0xffff
0048cc:  ffff  dw      0xffff
0048ce:  ffff  dw      0xffff
0048d0:  ffff  dw      0xffff
0048d2:  ffff  dw      0xffff
0048d4:  ffff  dw      0xffff
0048d6:  ffff  dw      0xffff
0048d8:  ffff  dw      0xffff
0048da:  ffff  dw      0xffff
0048dc:  ffff  dw      0xffff
0048de:  ffff  dw      0xffff
0048e0:  ffff  dw      0xffff
0048e2:  ffff  dw      0xffff
0048e4:  ffff  dw      0xffff
0048e6:  ffff  dw      0xffff
0048e8:  ffff  dw      0xffff
0048ea:  ffff  dw      0xffff
0048ec:  ffff  dw      0xffff
0048ee:  ffff  dw      0xffff
0048f0:  ffff  dw      0xffff
0048f2:  ffff  dw      0xffff
0048f4:  ffff  dw      0xffff
0048f6:  ffff  dw      0xffff
0048f8:  ffff  dw      0xffff
0048fa:  ffff  dw      0xffff
0048fc:  ffff  dw      0xffff
0048fe:  ffff  dw      0xffff
004900:  ffff  dw      0xffff
004902:  ffff  dw      0xffff
004904:  ffff  dw      0xffff
004906:  ffff  dw      0xffff
004908:  ffff  dw      0xffff
00490a:  ffff  dw      0xffff
00490c:  ffff  dw      0xffff
00490e:  ffff  dw      0xffff
004910:  ffff  dw      0xffff
004912:  ffff  dw      0xffff
004914:  ffff  dw      0xffff
004916:  ffff  dw      0xffff
004918:  ffff  dw      0xffff
00491a:  ffff  dw      0xffff
00491c:  ffff  dw      0xffff
00491e:  ffff  dw      0xffff
004920:  ffff  dw      0xffff
004922:  ffff  dw      0xffff
004924:  ffff  dw      0xffff
004926:  ffff  dw      0xffff
004928:  ffff  dw      0xffff
00492a:  ffff  dw      0xffff
00492c:  ffff  dw      0xffff
00492e:  ffff  dw      0xffff
004930:  ffff  dw      0xffff
004932:  ffff  dw      0xffff
004934:  ffff  dw      0xffff
004936:  ffff  dw      0xffff
004938:  ffff  dw      0xffff
00493a:  ffff  dw      0xffff
00493c:  ffff  dw      0xffff
00493e:  ffff  dw      0xffff
004940:  ffff  dw      0xffff
004942:  ffff  dw      0xffff
004944:  ffff  dw      0xffff
004946:  ffff  dw      0xffff
004948:  ffff  dw      0xffff
00494a:  ffff  dw      0xffff
00494c:  ffff  dw      0xffff
00494e:  ffff  dw      0xffff
004950:  ffff  dw      0xffff
004952:  ffff  dw      0xffff
004954:  ffff  dw      0xffff
004956:  ffff  dw      0xffff
004958:  ffff  dw      0xffff
00495a:  ffff  dw      0xffff
00495c:  ffff  dw      0xffff
00495e:  ffff  dw      0xffff
004960:  ffff  dw      0xffff
004962:  ffff  dw      0xffff
004964:  ffff  dw      0xffff
004966:  ffff  dw      0xffff
004968:  ffff  dw      0xffff
00496a:  ffff  dw      0xffff
00496c:  ffff  dw      0xffff
00496e:  ffff  dw      0xffff
004970:  ffff  dw      0xffff
004972:  ffff  dw      0xffff
004974:  ffff  dw      0xffff
004976:  ffff  dw      0xffff
004978:  ffff  dw      0xffff
00497a:  ffff  dw      0xffff
00497c:  ffff  dw      0xffff
00497e:  ffff  dw      0xffff
004980:  ffff  dw      0xffff
004982:  ffff  dw      0xffff
004984:  ffff  dw      0xffff
004986:  ffff  dw      0xffff
004988:  ffff  dw      0xffff
00498a:  ffff  dw      0xffff
00498c:  ffff  dw      0xffff
00498e:  ffff  dw      0xffff
004990:  ffff  dw      0xffff
004992:  ffff  dw      0xffff
004994:  ffff  dw      0xffff
004996:  ffff  dw      0xffff
004998:  ffff  dw      0xffff
00499a:  ffff  dw      0xffff
00499c:  ffff  dw      0xffff
00499e:  ffff  dw      0xffff
0049a0:  ffff  dw      0xffff
0049a2:  ffff  dw      0xffff
0049a4:  ffff  dw      0xffff
0049a6:  ffff  dw      0xffff
0049a8:  ffff  dw      0xffff
0049aa:  ffff  dw      0xffff
0049ac:  ffff  dw      0xffff
0049ae:  ffff  dw      0xffff
0049b0:  ffff  dw      0xffff
0049b2:  ffff  dw      0xffff
0049b4:  ffff  dw      0xffff
0049b6:  ffff  dw      0xffff
0049b8:  ffff  dw      0xffff
0049ba:  ffff  dw      0xffff
0049bc:  ffff  dw      0xffff
0049be:  ffff  dw      0xffff
0049c0:  ffff  dw      0xffff
0049c2:  ffff  dw      0xffff
0049c4:  ffff  dw      0xffff
0049c6:  ffff  dw      0xffff
0049c8:  ffff  dw      0xffff
0049ca:  ffff  dw      0xffff
0049cc:  ffff  dw      0xffff
0049ce:  ffff  dw      0xffff
0049d0:  ffff  dw      0xffff
0049d2:  ffff  dw      0xffff
0049d4:  ffff  dw      0xffff
0049d6:  ffff  dw      0xffff
0049d8:  ffff  dw      0xffff
0049da:  ffff  dw      0xffff
0049dc:  ffff  dw      0xffff
0049de:  ffff  dw      0xffff
0049e0:  ffff  dw      0xffff
0049e2:  ffff  dw      0xffff
0049e4:  ffff  dw      0xffff
0049e6:  ffff  dw      0xffff
0049e8:  ffff  dw      0xffff
0049ea:  ffff  dw      0xffff
0049ec:  ffff  dw      0xffff
0049ee:  ffff  dw      0xffff
0049f0:  ffff  dw      0xffff
0049f2:  ffff  dw      0xffff
0049f4:  ffff  dw      0xffff
0049f6:  ffff  dw      0xffff
0049f8:  ffff  dw      0xffff
0049fa:  ffff  dw      0xffff
0049fc:  ffff  dw      0xffff
0049fe:  ffff  dw      0xffff
004a00:  ffff  dw      0xffff
004a02:  ffff  dw      0xffff
004a04:  ffff  dw      0xffff
004a06:  ffff  dw      0xffff
004a08:  ffff  dw      0xffff
004a0a:  ffff  dw      0xffff
004a0c:  ffff  dw      0xffff
004a0e:  ffff  dw      0xffff
004a10:  ffff  dw      0xffff
004a12:  ffff  dw      0xffff
004a14:  ffff  dw      0xffff
004a16:  ffff  dw      0xffff
004a18:  ffff  dw      0xffff
004a1a:  ffff  dw      0xffff
004a1c:  ffff  dw      0xffff
004a1e:  ffff  dw      0xffff
004a20:  ffff  dw      0xffff
004a22:  ffff  dw      0xffff
004a24:  ffff  dw      0xffff
004a26:  ffff  dw      0xffff
004a28:  ffff  dw      0xffff
004a2a:  ffff  dw      0xffff
004a2c:  ffff  dw      0xffff
004a2e:  ffff  dw      0xffff
004a30:  ffff  dw      0xffff
004a32:  ffff  dw      0xffff
004a34:  ffff  dw      0xffff
004a36:  ffff  dw      0xffff
004a38:  ffff  dw      0xffff
004a3a:  ffff  dw      0xffff
004a3c:  ffff  dw      0xffff
004a3e:  ffff  dw      0xffff
004a40:  ffff  dw      0xffff
004a42:  ffff  dw      0xffff
004a44:  ffff  dw      0xffff
004a46:  ffff  dw      0xffff
004a48:  ffff  dw      0xffff
004a4a:  ffff  dw      0xffff
004a4c:  ffff  dw      0xffff
004a4e:  ffff  dw      0xffff
004a50:  ffff  dw      0xffff
004a52:  ffff  dw      0xffff
004a54:  ffff  dw      0xffff
004a56:  ffff  dw      0xffff
004a58:  ffff  dw      0xffff
004a5a:  ffff  dw      0xffff
004a5c:  ffff  dw      0xffff
004a5e:  ffff  dw      0xffff
004a60:  ffff  dw      0xffff
004a62:  ffff  dw      0xffff
004a64:  ffff  dw      0xffff
004a66:  ffff  dw      0xffff
004a68:  ffff  dw      0xffff
004a6a:  ffff  dw      0xffff
004a6c:  ffff  dw      0xffff
004a6e:  ffff  dw      0xffff
004a70:  ffff  dw      0xffff
004a72:  ffff  dw      0xffff
004a74:  ffff  dw      0xffff
004a76:  ffff  dw      0xffff
004a78:  ffff  dw      0xffff
004a7a:  ffff  dw      0xffff
004a7c:  ffff  dw      0xffff
004a7e:  ffff  dw      0xffff
004a80:  ffff  dw      0xffff
004a82:  ffff  dw      0xffff
004a84:  ffff  dw      0xffff
004a86:  ffff  dw      0xffff
004a88:  ffff  dw      0xffff
004a8a:  ffff  dw      0xffff
004a8c:  ffff  dw      0xffff
004a8e:  ffff  dw      0xffff
004a90:  ffff  dw      0xffff
004a92:  ffff  dw      0xffff
004a94:  ffff  dw      0xffff
004a96:  ffff  dw      0xffff
004a98:  ffff  dw      0xffff
004a9a:  ffff  dw      0xffff
004a9c:  ffff  dw      0xffff
004a9e:  ffff  dw      0xffff
004aa0:  ffff  dw      0xffff
004aa2:  ffff  dw      0xffff
004aa4:  ffff  dw      0xffff
004aa6:  ffff  dw      0xffff
004aa8:  ffff  dw      0xffff
004aaa:  ffff  dw      0xffff
004aac:  ffff  dw      0xffff
004aae:  ffff  dw      0xffff
004ab0:  ffff  dw      0xffff
004ab2:  ffff  dw      0xffff
004ab4:  ffff  dw      0xffff
004ab6:  ffff  dw      0xffff
004ab8:  ffff  dw      0xffff
004aba:  ffff  dw      0xffff
004abc:  ffff  dw      0xffff
004abe:  ffff  dw      0xffff
004ac0:  ffff  dw      0xffff
004ac2:  ffff  dw      0xffff
004ac4:  ffff  dw      0xffff
004ac6:  ffff  dw      0xffff
004ac8:  ffff  dw      0xffff
004aca:  ffff  dw      0xffff
004acc:  ffff  dw      0xffff
004ace:  ffff  dw      0xffff
004ad0:  ffff  dw      0xffff
004ad2:  ffff  dw      0xffff
004ad4:  ffff  dw      0xffff
004ad6:  ffff  dw      0xffff
004ad8:  ffff  dw      0xffff
004ada:  ffff  dw      0xffff
004adc:  ffff  dw      0xffff
004ade:  ffff  dw      0xffff
004ae0:  ffff  dw      0xffff
004ae2:  ffff  dw      0xffff
004ae4:  ffff  dw      0xffff
004ae6:  ffff  dw      0xffff
004ae8:  ffff  dw      0xffff
004aea:  ffff  dw      0xffff
004aec:  ffff  dw      0xffff
004aee:  ffff  dw      0xffff
004af0:  ffff  dw      0xffff
004af2:  ffff  dw      0xffff
004af4:  ffff  dw      0xffff
004af6:  ffff  dw      0xffff
004af8:  ffff  dw      0xffff
004afa:  ffff  dw      0xffff
004afc:  ffff  dw      0xffff
004afe:  ffff  dw      0xffff
004b00:  ffff  dw      0xffff
004b02:  ffff  dw      0xffff
004b04:  ffff  dw      0xffff
004b06:  ffff  dw      0xffff
004b08:  ffff  dw      0xffff
004b0a:  ffff  dw      0xffff
004b0c:  ffff  dw      0xffff
004b0e:  ffff  dw      0xffff
004b10:  ffff  dw      0xffff
004b12:  ffff  dw      0xffff
004b14:  ffff  dw      0xffff
004b16:  ffff  dw      0xffff
004b18:  ffff  dw      0xffff
004b1a:  ffff  dw      0xffff
004b1c:  ffff  dw      0xffff
004b1e:  ffff  dw      0xffff
004b20:  ffff  dw      0xffff
004b22:  ffff  dw      0xffff
004b24:  ffff  dw      0xffff
004b26:  ffff  dw      0xffff
004b28:  ffff  dw      0xffff
004b2a:  ffff  dw      0xffff
004b2c:  ffff  dw      0xffff
004b2e:  ffff  dw      0xffff
004b30:  ffff  dw      0xffff
004b32:  ffff  dw      0xffff
004b34:  ffff  dw      0xffff
004b36:  ffff  dw      0xffff
004b38:  ffff  dw      0xffff
004b3a:  ffff  dw      0xffff
004b3c:  ffff  dw      0xffff
004b3e:  ffff  dw      0xffff
004b40:  ffff  dw      0xffff
004b42:  ffff  dw      0xffff
004b44:  ffff  dw      0xffff
004b46:  ffff  dw      0xffff
004b48:  ffff  dw      0xffff
004b4a:  ffff  dw      0xffff
004b4c:  ffff  dw      0xffff
004b4e:  ffff  dw      0xffff
004b50:  ffff  dw      0xffff
004b52:  ffff  dw      0xffff
004b54:  ffff  dw      0xffff
004b56:  ffff  dw      0xffff
004b58:  ffff  dw      0xffff
004b5a:  ffff  dw      0xffff
004b5c:  ffff  dw      0xffff
004b5e:  ffff  dw      0xffff
004b60:  ffff  dw      0xffff
004b62:  ffff  dw      0xffff
004b64:  ffff  dw      0xffff
004b66:  ffff  dw      0xffff
004b68:  ffff  dw      0xffff
004b6a:  ffff  dw      0xffff
004b6c:  ffff  dw      0xffff
004b6e:  ffff  dw      0xffff
004b70:  ffff  dw      0xffff
004b72:  ffff  dw      0xffff
004b74:  ffff  dw      0xffff
004b76:  ffff  dw      0xffff
004b78:  ffff  dw      0xffff
004b7a:  ffff  dw      0xffff
004b7c:  ffff  dw      0xffff
004b7e:  ffff  dw      0xffff
004b80:  ffff  dw      0xffff
004b82:  ffff  dw      0xffff
004b84:  ffff  dw      0xffff
004b86:  ffff  dw      0xffff
004b88:  ffff  dw      0xffff
004b8a:  ffff  dw      0xffff
004b8c:  ffff  dw      0xffff
004b8e:  ffff  dw      0xffff
004b90:  ffff  dw      0xffff
004b92:  ffff  dw      0xffff
004b94:  ffff  dw      0xffff
004b96:  ffff  dw      0xffff
004b98:  ffff  dw      0xffff
004b9a:  ffff  dw      0xffff
004b9c:  ffff  dw      0xffff
004b9e:  ffff  dw      0xffff
004ba0:  ffff  dw      0xffff
004ba2:  ffff  dw      0xffff
004ba4:  ffff  dw      0xffff
004ba6:  ffff  dw      0xffff
004ba8:  ffff  dw      0xffff
004baa:  ffff  dw      0xffff
004bac:  ffff  dw      0xffff
004bae:  ffff  dw      0xffff
004bb0:  ffff  dw      0xffff
004bb2:  ffff  dw      0xffff
004bb4:  ffff  dw      0xffff
004bb6:  ffff  dw      0xffff
004bb8:  ffff  dw      0xffff
004bba:  ffff  dw      0xffff
004bbc:  ffff  dw      0xffff
004bbe:  ffff  dw      0xffff
004bc0:  ffff  dw      0xffff
004bc2:  ffff  dw      0xffff
004bc4:  ffff  dw      0xffff
004bc6:  ffff  dw      0xffff
004bc8:  ffff  dw      0xffff
004bca:  ffff  dw      0xffff
004bcc:  ffff  dw      0xffff
004bce:  ffff  dw      0xffff
004bd0:  ffff  dw      0xffff
004bd2:  ffff  dw      0xffff
004bd4:  ffff  dw      0xffff
004bd6:  ffff  dw      0xffff
004bd8:  ffff  dw      0xffff
004bda:  ffff  dw      0xffff
004bdc:  ffff  dw      0xffff
004bde:  ffff  dw      0xffff
004be0:  ffff  dw      0xffff
004be2:  ffff  dw      0xffff
004be4:  ffff  dw      0xffff
004be6:  ffff  dw      0xffff
004be8:  ffff  dw      0xffff
004bea:  ffff  dw      0xffff
004bec:  ffff  dw      0xffff
004bee:  ffff  dw      0xffff
004bf0:  ffff  dw      0xffff
004bf2:  ffff  dw      0xffff
004bf4:  ffff  dw      0xffff
004bf6:  ffff  dw      0xffff
004bf8:  ffff  dw      0xffff
004bfa:  ffff  dw      0xffff
004bfc:  ffff  dw      0xffff
004bfe:  ffff  dw      0xffff
004c00:  ffff  dw      0xffff
004c02:  ffff  dw      0xffff
004c04:  ffff  dw      0xffff
004c06:  ffff  dw      0xffff
004c08:  ffff  dw      0xffff
004c0a:  ffff  dw      0xffff
004c0c:  ffff  dw      0xffff
004c0e:  ffff  dw      0xffff
004c10:  ffff  dw      0xffff
004c12:  ffff  dw      0xffff
004c14:  ffff  dw      0xffff
004c16:  ffff  dw      0xffff
004c18:  ffff  dw      0xffff
004c1a:  ffff  dw      0xffff
004c1c:  ffff  dw      0xffff
004c1e:  ffff  dw      0xffff
004c20:  ffff  dw      0xffff
004c22:  ffff  dw      0xffff
004c24:  ffff  dw      0xffff
004c26:  ffff  dw      0xffff
004c28:  ffff  dw      0xffff
004c2a:  ffff  dw      0xffff
004c2c:  ffff  dw      0xffff
004c2e:  ffff  dw      0xffff
004c30:  ffff  dw      0xffff
004c32:  ffff  dw      0xffff
004c34:  ffff  dw      0xffff
004c36:  ffff  dw      0xffff
004c38:  ffff  dw      0xffff
004c3a:  ffff  dw      0xffff
004c3c:  ffff  dw      0xffff
004c3e:  ffff  dw      0xffff
004c40:  ffff  dw      0xffff
004c42:  ffff  dw      0xffff
004c44:  ffff  dw      0xffff
004c46:  ffff  dw      0xffff
004c48:  ffff  dw      0xffff
004c4a:  ffff  dw      0xffff
004c4c:  ffff  dw      0xffff
004c4e:  ffff  dw      0xffff
004c50:  ffff  dw      0xffff
004c52:  ffff  dw      0xffff
004c54:  ffff  dw      0xffff
004c56:  ffff  dw      0xffff
004c58:  ffff  dw      0xffff
004c5a:  ffff  dw      0xffff
004c5c:  ffff  dw      0xffff
004c5e:  ffff  dw      0xffff
004c60:  ffff  dw      0xffff
004c62:  ffff  dw      0xffff
004c64:  ffff  dw      0xffff
004c66:  ffff  dw      0xffff
004c68:  ffff  dw      0xffff
004c6a:  ffff  dw      0xffff
004c6c:  ffff  dw      0xffff
004c6e:  ffff  dw      0xffff
004c70:  ffff  dw      0xffff
004c72:  ffff  dw      0xffff
004c74:  ffff  dw      0xffff
004c76:  ffff  dw      0xffff
004c78:  ffff  dw      0xffff
004c7a:  ffff  dw      0xffff
004c7c:  ffff  dw      0xffff
004c7e:  ffff  dw      0xffff
004c80:  ffff  dw      0xffff
004c82:  ffff  dw      0xffff
004c84:  ffff  dw      0xffff
004c86:  ffff  dw      0xffff
004c88:  ffff  dw      0xffff
004c8a:  ffff  dw      0xffff
004c8c:  ffff  dw      0xffff
004c8e:  ffff  dw      0xffff
004c90:  ffff  dw      0xffff
004c92:  ffff  dw      0xffff
004c94:  ffff  dw      0xffff
004c96:  ffff  dw      0xffff
004c98:  ffff  dw      0xffff
004c9a:  ffff  dw      0xffff
004c9c:  ffff  dw      0xffff
004c9e:  ffff  dw      0xffff
004ca0:  ffff  dw      0xffff
004ca2:  ffff  dw      0xffff
004ca4:  ffff  dw      0xffff
004ca6:  ffff  dw      0xffff
004ca8:  ffff  dw      0xffff
004caa:  ffff  dw      0xffff
004cac:  ffff  dw      0xffff
004cae:  ffff  dw      0xffff
004cb0:  ffff  dw      0xffff
004cb2:  ffff  dw      0xffff
004cb4:  ffff  dw      0xffff
004cb6:  ffff  dw      0xffff
004cb8:  ffff  dw      0xffff
004cba:  ffff  dw      0xffff
004cbc:  ffff  dw      0xffff
004cbe:  ffff  dw      0xffff
004cc0:  ffff  dw      0xffff
004cc2:  ffff  dw      0xffff
004cc4:  ffff  dw      0xffff
004cc6:  ffff  dw      0xffff
004cc8:  ffff  dw      0xffff
004cca:  ffff  dw      0xffff
004ccc:  ffff  dw      0xffff
004cce:  ffff  dw      0xffff
004cd0:  ffff  dw      0xffff
004cd2:  ffff  dw      0xffff
004cd4:  ffff  dw      0xffff
004cd6:  ffff  dw      0xffff
004cd8:  ffff  dw      0xffff
004cda:  ffff  dw      0xffff
004cdc:  ffff  dw      0xffff
004cde:  ffff  dw      0xffff
004ce0:  ffff  dw      0xffff
004ce2:  ffff  dw      0xffff
004ce4:  ffff  dw      0xffff
004ce6:  ffff  dw      0xffff
004ce8:  ffff  dw      0xffff
004cea:  ffff  dw      0xffff
004cec:  ffff  dw      0xffff
004cee:  ffff  dw      0xffff
004cf0:  ffff  dw      0xffff
004cf2:  ffff  dw      0xffff
004cf4:  ffff  dw      0xffff
004cf6:  ffff  dw      0xffff
004cf8:  ffff  dw      0xffff
004cfa:  ffff  dw      0xffff
004cfc:  ffff  dw      0xffff
004cfe:  ffff  dw      0xffff
004d00:  ffff  dw      0xffff
004d02:  ffff  dw      0xffff
004d04:  ffff  dw      0xffff
004d06:  ffff  dw      0xffff
004d08:  ffff  dw      0xffff
004d0a:  ffff  dw      0xffff
004d0c:  ffff  dw      0xffff
004d0e:  ffff  dw      0xffff
004d10:  ffff  dw      0xffff
004d12:  ffff  dw      0xffff
004d14:  ffff  dw      0xffff
004d16:  ffff  dw      0xffff
004d18:  ffff  dw      0xffff
004d1a:  ffff  dw      0xffff
004d1c:  ffff  dw      0xffff
004d1e:  ffff  dw      0xffff
004d20:  ffff  dw      0xffff
004d22:  ffff  dw      0xffff
004d24:  ffff  dw      0xffff
004d26:  ffff  dw      0xffff
004d28:  ffff  dw      0xffff
004d2a:  ffff  dw      0xffff
004d2c:  ffff  dw      0xffff
004d2e:  ffff  dw      0xffff
004d30:  ffff  dw      0xffff
004d32:  ffff  dw      0xffff
004d34:  ffff  dw      0xffff
004d36:  ffff  dw      0xffff
004d38:  ffff  dw      0xffff
004d3a:  ffff  dw      0xffff
004d3c:  ffff  dw      0xffff
004d3e:  ffff  dw      0xffff
004d40:  ffff  dw      0xffff
004d42:  ffff  dw      0xffff
004d44:  ffff  dw      0xffff
004d46:  ffff  dw      0xffff
004d48:  ffff  dw      0xffff
004d4a:  ffff  dw      0xffff
004d4c:  ffff  dw      0xffff
004d4e:  ffff  dw      0xffff
004d50:  ffff  dw      0xffff
004d52:  ffff  dw      0xffff
004d54:  ffff  dw      0xffff
004d56:  ffff  dw      0xffff
004d58:  ffff  dw      0xffff
004d5a:  ffff  dw      0xffff
004d5c:  ffff  dw      0xffff
004d5e:  ffff  dw      0xffff
004d60:  ffff  dw      0xffff
004d62:  ffff  dw      0xffff
004d64:  ffff  dw      0xffff
004d66:  ffff  dw      0xffff
004d68:  ffff  dw      0xffff
004d6a:  ffff  dw      0xffff
004d6c:  ffff  dw      0xffff
004d6e:  ffff  dw      0xffff
004d70:  ffff  dw      0xffff
004d72:  ffff  dw      0xffff
004d74:  ffff  dw      0xffff
004d76:  ffff  dw      0xffff
004d78:  ffff  dw      0xffff
004d7a:  ffff  dw      0xffff
004d7c:  ffff  dw      0xffff
004d7e:  ffff  dw      0xffff
004d80:  ffff  dw      0xffff
004d82:  ffff  dw      0xffff
004d84:  ffff  dw      0xffff
004d86:  ffff  dw      0xffff
004d88:  ffff  dw      0xffff
004d8a:  ffff  dw      0xffff
004d8c:  ffff  dw      0xffff
004d8e:  ffff  dw      0xffff
004d90:  ffff  dw      0xffff
004d92:  ffff  dw      0xffff
004d94:  ffff  dw      0xffff
004d96:  ffff  dw      0xffff
004d98:  ffff  dw      0xffff
004d9a:  ffff  dw      0xffff
004d9c:  ffff  dw      0xffff
004d9e:  ffff  dw      0xffff
004da0:  ffff  dw      0xffff
004da2:  ffff  dw      0xffff
004da4:  ffff  dw      0xffff
004da6:  ffff  dw      0xffff
004da8:  ffff  dw      0xffff
004daa:  ffff  dw      0xffff
004dac:  ffff  dw      0xffff
004dae:  ffff  dw      0xffff
004db0:  ffff  dw      0xffff
004db2:  ffff  dw      0xffff
004db4:  ffff  dw      0xffff
004db6:  ffff  dw      0xffff
004db8:  ffff  dw      0xffff
004dba:  ffff  dw      0xffff
004dbc:  ffff  dw      0xffff
004dbe:  ffff  dw      0xffff
004dc0:  ffff  dw      0xffff
004dc2:  ffff  dw      0xffff
004dc4:  ffff  dw      0xffff
004dc6:  ffff  dw      0xffff
004dc8:  ffff  dw      0xffff
004dca:  ffff  dw      0xffff
004dcc:  ffff  dw      0xffff
004dce:  ffff  dw      0xffff
004dd0:  ffff  dw      0xffff
004dd2:  ffff  dw      0xffff
004dd4:  ffff  dw      0xffff
004dd6:  ffff  dw      0xffff
004dd8:  ffff  dw      0xffff
004dda:  ffff  dw      0xffff
004ddc:  ffff  dw      0xffff
004dde:  ffff  dw      0xffff
004de0:  ffff  dw      0xffff
004de2:  ffff  dw      0xffff
004de4:  ffff  dw      0xffff
004de6:  ffff  dw      0xffff
004de8:  ffff  dw      0xffff
004dea:  ffff  dw      0xffff
004dec:  ffff  dw      0xffff
004dee:  ffff  dw      0xffff
004df0:  ffff  dw      0xffff
004df2:  ffff  dw      0xffff
004df4:  ffff  dw      0xffff
004df6:  ffff  dw      0xffff
004df8:  ffff  dw      0xffff
004dfa:  ffff  dw      0xffff
004dfc:  ffff  dw      0xffff
004dfe:  ffff  dw      0xffff
004e00:  ffff  dw      0xffff
004e02:  ffff  dw      0xffff
004e04:  ffff  dw      0xffff
004e06:  ffff  dw      0xffff
004e08:  ffff  dw      0xffff
004e0a:  ffff  dw      0xffff
004e0c:  ffff  dw      0xffff
004e0e:  ffff  dw      0xffff
004e10:  ffff  dw      0xffff
004e12:  ffff  dw      0xffff
004e14:  ffff  dw      0xffff
004e16:  ffff  dw      0xffff
004e18:  ffff  dw      0xffff
004e1a:  ffff  dw      0xffff
004e1c:  ffff  dw      0xffff
004e1e:  ffff  dw      0xffff
004e20:  ffff  dw      0xffff
004e22:  ffff  dw      0xffff
004e24:  ffff  dw      0xffff
004e26:  ffff  dw      0xffff
004e28:  ffff  dw      0xffff
004e2a:  ffff  dw      0xffff
004e2c:  ffff  dw      0xffff
004e2e:  ffff  dw      0xffff
004e30:  ffff  dw      0xffff
004e32:  ffff  dw      0xffff
004e34:  ffff  dw      0xffff
004e36:  ffff  dw      0xffff
004e38:  ffff  dw      0xffff
004e3a:  ffff  dw      0xffff
004e3c:  ffff  dw      0xffff
004e3e:  ffff  dw      0xffff
004e40:  ffff  dw      0xffff
004e42:  ffff  dw      0xffff
004e44:  ffff  dw      0xffff
004e46:  ffff  dw      0xffff
004e48:  ffff  dw      0xffff
004e4a:  ffff  dw      0xffff
004e4c:  ffff  dw      0xffff
004e4e:  ffff  dw      0xffff
004e50:  ffff  dw      0xffff
004e52:  ffff  dw      0xffff
004e54:  ffff  dw      0xffff
004e56:  ffff  dw      0xffff
004e58:  ffff  dw      0xffff
004e5a:  ffff  dw      0xffff
004e5c:  ffff  dw      0xffff
004e5e:  ffff  dw      0xffff
004e60:  ffff  dw      0xffff
004e62:  ffff  dw      0xffff
004e64:  ffff  dw      0xffff
004e66:  ffff  dw      0xffff
004e68:  ffff  dw      0xffff
004e6a:  ffff  dw      0xffff
004e6c:  ffff  dw      0xffff
004e6e:  ffff  dw      0xffff
004e70:  ffff  dw      0xffff
004e72:  ffff  dw      0xffff
004e74:  ffff  dw      0xffff
004e76:  ffff  dw      0xffff
004e78:  ffff  dw      0xffff
004e7a:  ffff  dw      0xffff
004e7c:  ffff  dw      0xffff
004e7e:  ffff  dw      0xffff
004e80:  ffff  dw      0xffff
004e82:  ffff  dw      0xffff
004e84:  ffff  dw      0xffff
004e86:  ffff  dw      0xffff
004e88:  ffff  dw      0xffff
004e8a:  ffff  dw      0xffff
004e8c:  ffff  dw      0xffff
004e8e:  ffff  dw      0xffff
004e90:  ffff  dw      0xffff
004e92:  ffff  dw      0xffff
004e94:  ffff  dw      0xffff
004e96:  ffff  dw      0xffff
004e98:  ffff  dw      0xffff
004e9a:  ffff  dw      0xffff
004e9c:  ffff  dw      0xffff
004e9e:  ffff  dw      0xffff
004ea0:  ffff  dw      0xffff
004ea2:  ffff  dw      0xffff
004ea4:  ffff  dw      0xffff
004ea6:  ffff  dw      0xffff
004ea8:  ffff  dw      0xffff
004eaa:  ffff  dw      0xffff
004eac:  ffff  dw      0xffff
004eae:  ffff  dw      0xffff
004eb0:  ffff  dw      0xffff
004eb2:  ffff  dw      0xffff
004eb4:  ffff  dw      0xffff
004eb6:  ffff  dw      0xffff
004eb8:  ffff  dw      0xffff
004eba:  ffff  dw      0xffff
004ebc:  ffff  dw      0xffff
004ebe:  ffff  dw      0xffff
004ec0:  ffff  dw      0xffff
004ec2:  ffff  dw      0xffff
004ec4:  ffff  dw      0xffff
004ec6:  ffff  dw      0xffff
004ec8:  ffff  dw      0xffff
004eca:  ffff  dw      0xffff
004ecc:  ffff  dw      0xffff
004ece:  ffff  dw      0xffff
004ed0:  ffff  dw      0xffff
004ed2:  ffff  dw      0xffff
004ed4:  ffff  dw      0xffff
004ed6:  ffff  dw      0xffff
004ed8:  ffff  dw      0xffff
004eda:  ffff  dw      0xffff
004edc:  ffff  dw      0xffff
004ede:  ffff  dw      0xffff
004ee0:  ffff  dw      0xffff
004ee2:  ffff  dw      0xffff
004ee4:  ffff  dw      0xffff
004ee6:  ffff  dw      0xffff
004ee8:  ffff  dw      0xffff
004eea:  ffff  dw      0xffff
004eec:  ffff  dw      0xffff
004eee:  ffff  dw      0xffff
004ef0:  ffff  dw      0xffff
004ef2:  ffff  dw      0xffff
004ef4:  ffff  dw      0xffff
004ef6:  ffff  dw      0xffff
004ef8:  ffff  dw      0xffff
004efa:  ffff  dw      0xffff
004efc:  ffff  dw      0xffff
004efe:  ffff  dw      0xffff
004f00:  ffff  dw      0xffff
004f02:  ffff  dw      0xffff
004f04:  ffff  dw      0xffff
004f06:  ffff  dw      0xffff
004f08:  ffff  dw      0xffff
004f0a:  ffff  dw      0xffff
004f0c:  ffff  dw      0xffff
004f0e:  ffff  dw      0xffff
004f10:  ffff  dw      0xffff
004f12:  ffff  dw      0xffff
004f14:  ffff  dw      0xffff
004f16:  ffff  dw      0xffff
004f18:  ffff  dw      0xffff
004f1a:  ffff  dw      0xffff
004f1c:  ffff  dw      0xffff
004f1e:  ffff  dw      0xffff
004f20:  ffff  dw      0xffff
004f22:  ffff  dw      0xffff
004f24:  ffff  dw      0xffff
004f26:  ffff  dw      0xffff
004f28:  ffff  dw      0xffff
004f2a:  ffff  dw      0xffff
004f2c:  ffff  dw      0xffff
004f2e:  ffff  dw      0xffff
004f30:  ffff  dw      0xffff
004f32:  ffff  dw      0xffff
004f34:  ffff  dw      0xffff
004f36:  ffff  dw      0xffff
004f38:  ffff  dw      0xffff
004f3a:  ffff  dw      0xffff
004f3c:  ffff  dw      0xffff
004f3e:  ffff  dw      0xffff
004f40:  ffff  dw      0xffff
004f42:  ffff  dw      0xffff
004f44:  ffff  dw      0xffff
004f46:  ffff  dw      0xffff
004f48:  ffff  dw      0xffff
004f4a:  ffff  dw      0xffff
004f4c:  ffff  dw      0xffff
004f4e:  ffff  dw      0xffff
004f50:  ffff  dw      0xffff
004f52:  ffff  dw      0xffff
004f54:  ffff  dw      0xffff
004f56:  ffff  dw      0xffff
004f58:  ffff  dw      0xffff
004f5a:  ffff  dw      0xffff
004f5c:  ffff  dw      0xffff
004f5e:  ffff  dw      0xffff
004f60:  ffff  dw      0xffff
004f62:  ffff  dw      0xffff
004f64:  ffff  dw      0xffff
004f66:  ffff  dw      0xffff
004f68:  ffff  dw      0xffff
004f6a:  ffff  dw      0xffff
004f6c:  ffff  dw      0xffff
004f6e:  ffff  dw      0xffff
004f70:  ffff  dw      0xffff
004f72:  ffff  dw      0xffff
004f74:  ffff  dw      0xffff
004f76:  ffff  dw      0xffff
004f78:  ffff  dw      0xffff
004f7a:  ffff  dw      0xffff
004f7c:  ffff  dw      0xffff
004f7e:  ffff  dw      0xffff
004f80:  ffff  dw      0xffff
004f82:  ffff  dw      0xffff
004f84:  ffff  dw      0xffff
004f86:  ffff  dw      0xffff
004f88:  ffff  dw      0xffff
004f8a:  ffff  dw      0xffff
004f8c:  ffff  dw      0xffff
004f8e:  ffff  dw      0xffff
004f90:  ffff  dw      0xffff
004f92:  ffff  dw      0xffff
004f94:  ffff  dw      0xffff
004f96:  ffff  dw      0xffff
004f98:  ffff  dw      0xffff
004f9a:  ffff  dw      0xffff
004f9c:  ffff  dw      0xffff
004f9e:  ffff  dw      0xffff
004fa0:  ffff  dw      0xffff
004fa2:  ffff  dw      0xffff
004fa4:  ffff  dw      0xffff
004fa6:  ffff  dw      0xffff
004fa8:  ffff  dw      0xffff
004faa:  ffff  dw      0xffff
004fac:  ffff  dw      0xffff
004fae:  ffff  dw      0xffff
004fb0:  ffff  dw      0xffff
004fb2:  ffff  dw      0xffff
004fb4:  ffff  dw      0xffff
004fb6:  ffff  dw      0xffff
004fb8:  ffff  dw      0xffff
004fba:  ffff  dw      0xffff
004fbc:  ffff  dw      0xffff
004fbe:  ffff  dw      0xffff
004fc0:  ffff  dw      0xffff
004fc2:  ffff  dw      0xffff
004fc4:  ffff  dw      0xffff
004fc6:  ffff  dw      0xffff
004fc8:  ffff  dw      0xffff
004fca:  ffff  dw      0xffff
004fcc:  ffff  dw      0xffff
004fce:  ffff  dw      0xffff
004fd0:  ffff  dw      0xffff
004fd2:  ffff  dw      0xffff
004fd4:  ffff  dw      0xffff
004fd6:  ffff  dw      0xffff
004fd8:  ffff  dw      0xffff
004fda:  ffff  dw      0xffff
004fdc:  ffff  dw      0xffff
004fde:  ffff  dw      0xffff
004fe0:  ffff  dw      0xffff
004fe2:  ffff  dw      0xffff
004fe4:  ffff  dw      0xffff
004fe6:  ffff  dw      0xffff
004fe8:  ffff  dw      0xffff
004fea:  ffff  dw      0xffff
004fec:  ffff  dw      0xffff
004fee:  ffff  dw      0xffff
004ff0:  ffff  dw      0xffff
004ff2:  ffff  dw      0xffff
004ff4:  ffff  dw      0xffff
004ff6:  ffff  dw      0xffff
004ff8:  ffff  dw      0xffff
004ffa:  ffff  dw      0xffff
004ffc:  ffff  dw      0xffff
004ffe:  ffff  dw      0xffff
005000:  ffff  dw      0xffff
005002:  ffff  dw      0xffff
005004:  ffff  dw      0xffff
005006:  ffff  dw      0xffff
005008:  ffff  dw      0xffff
00500a:  ffff  dw      0xffff
00500c:  ffff  dw      0xffff
00500e:  ffff  dw      0xffff
005010:  ffff  dw      0xffff
005012:  ffff  dw      0xffff
005014:  ffff  dw      0xffff
005016:  ffff  dw      0xffff
005018:  ffff  dw      0xffff
00501a:  ffff  dw      0xffff
00501c:  ffff  dw      0xffff
00501e:  ffff  dw      0xffff
005020:  ffff  dw      0xffff
005022:  ffff  dw      0xffff
005024:  ffff  dw      0xffff
005026:  ffff  dw      0xffff
005028:  ffff  dw      0xffff
00502a:  ffff  dw      0xffff
00502c:  ffff  dw      0xffff
00502e:  ffff  dw      0xffff
005030:  ffff  dw      0xffff
005032:  ffff  dw      0xffff
005034:  ffff  dw      0xffff
005036:  ffff  dw      0xffff
005038:  ffff  dw      0xffff
00503a:  ffff  dw      0xffff
00503c:  ffff  dw      0xffff
00503e:  ffff  dw      0xffff
005040:  ffff  dw      0xffff
005042:  ffff  dw      0xffff
005044:  ffff  dw      0xffff
005046:  ffff  dw      0xffff
005048:  ffff  dw      0xffff
00504a:  ffff  dw      0xffff
00504c:  ffff  dw      0xffff
00504e:  ffff  dw      0xffff
005050:  ffff  dw      0xffff
005052:  ffff  dw      0xffff
005054:  ffff  dw      0xffff
005056:  ffff  dw      0xffff
005058:  ffff  dw      0xffff
00505a:  ffff  dw      0xffff
00505c:  ffff  dw      0xffff
00505e:  ffff  dw      0xffff
005060:  ffff  dw      0xffff
005062:  ffff  dw      0xffff
005064:  ffff  dw      0xffff
005066:  ffff  dw      0xffff
005068:  ffff  dw      0xffff
00506a:  ffff  dw      0xffff
00506c:  ffff  dw      0xffff
00506e:  ffff  dw      0xffff
005070:  ffff  dw      0xffff
005072:  ffff  dw      0xffff
005074:  ffff  dw      0xffff
005076:  ffff  dw      0xffff
005078:  ffff  dw      0xffff
00507a:  ffff  dw      0xffff
00507c:  ffff  dw      0xffff
00507e:  ffff  dw      0xffff
005080:  ffff  dw      0xffff
005082:  ffff  dw      0xffff
005084:  ffff  dw      0xffff
005086:  ffff  dw      0xffff
005088:  ffff  dw      0xffff
00508a:  ffff  dw      0xffff
00508c:  ffff  dw      0xffff
00508e:  ffff  dw      0xffff
005090:  ffff  dw      0xffff
005092:  ffff  dw      0xffff
005094:  ffff  dw      0xffff
005096:  ffff  dw      0xffff
005098:  ffff  dw      0xffff
00509a:  ffff  dw      0xffff
00509c:  ffff  dw      0xffff
00509e:  ffff  dw      0xffff
0050a0:  ffff  dw      0xffff
0050a2:  ffff  dw      0xffff
0050a4:  ffff  dw      0xffff
0050a6:  ffff  dw      0xffff
0050a8:  ffff  dw      0xffff
0050aa:  ffff  dw      0xffff
0050ac:  ffff  dw      0xffff
0050ae:  ffff  dw      0xffff
0050b0:  ffff  dw      0xffff
0050b2:  ffff  dw      0xffff
0050b4:  ffff  dw      0xffff
0050b6:  ffff  dw      0xffff
0050b8:  ffff  dw      0xffff
0050ba:  ffff  dw      0xffff
0050bc:  ffff  dw      0xffff
0050be:  ffff  dw      0xffff
0050c0:  ffff  dw      0xffff
0050c2:  ffff  dw      0xffff
0050c4:  ffff  dw      0xffff
0050c6:  ffff  dw      0xffff
0050c8:  ffff  dw      0xffff
0050ca:  ffff  dw      0xffff
0050cc:  ffff  dw      0xffff
0050ce:  ffff  dw      0xffff
0050d0:  ffff  dw      0xffff
0050d2:  ffff  dw      0xffff
0050d4:  ffff  dw      0xffff
0050d6:  ffff  dw      0xffff
0050d8:  ffff  dw      0xffff
0050da:  ffff  dw      0xffff
0050dc:  ffff  dw      0xffff
0050de:  ffff  dw      0xffff
0050e0:  ffff  dw      0xffff
0050e2:  ffff  dw      0xffff
0050e4:  ffff  dw      0xffff
0050e6:  ffff  dw      0xffff
0050e8:  ffff  dw      0xffff
0050ea:  ffff  dw      0xffff
0050ec:  ffff  dw      0xffff
0050ee:  ffff  dw      0xffff
0050f0:  ffff  dw      0xffff
0050f2:  ffff  dw      0xffff
0050f4:  ffff  dw      0xffff
0050f6:  ffff  dw      0xffff
0050f8:  ffff  dw      0xffff
0050fa:  ffff  dw      0xffff
0050fc:  ffff  dw      0xffff
0050fe:  ffff  dw      0xffff
005100:  ffff  dw      0xffff
005102:  ffff  dw      0xffff
005104:  ffff  dw      0xffff
005106:  ffff  dw      0xffff
005108:  ffff  dw      0xffff
00510a:  ffff  dw      0xffff
00510c:  ffff  dw      0xffff
00510e:  ffff  dw      0xffff
005110:  ffff  dw      0xffff
005112:  ffff  dw      0xffff
005114:  ffff  dw      0xffff
005116:  ffff  dw      0xffff
005118:  ffff  dw      0xffff
00511a:  ffff  dw      0xffff
00511c:  ffff  dw      0xffff
00511e:  ffff  dw      0xffff
005120:  ffff  dw      0xffff
005122:  ffff  dw      0xffff
005124:  ffff  dw      0xffff
005126:  ffff  dw      0xffff
005128:  ffff  dw      0xffff
00512a:  ffff  dw      0xffff
00512c:  ffff  dw      0xffff
00512e:  ffff  dw      0xffff
005130:  ffff  dw      0xffff
005132:  ffff  dw      0xffff
005134:  ffff  dw      0xffff
005136:  ffff  dw      0xffff
005138:  ffff  dw      0xffff
00513a:  ffff  dw      0xffff
00513c:  ffff  dw      0xffff
00513e:  ffff  dw      0xffff
005140:  ffff  dw      0xffff
005142:  ffff  dw      0xffff
005144:  ffff  dw      0xffff
005146:  ffff  dw      0xffff
005148:  ffff  dw      0xffff
00514a:  ffff  dw      0xffff
00514c:  ffff  dw      0xffff
00514e:  ffff  dw      0xffff
005150:  ffff  dw      0xffff
005152:  ffff  dw      0xffff
005154:  ffff  dw      0xffff
005156:  ffff  dw      0xffff
005158:  ffff  dw      0xffff
00515a:  ffff  dw      0xffff
00515c:  ffff  dw      0xffff
00515e:  ffff  dw      0xffff
005160:  ffff  dw      0xffff
005162:  ffff  dw      0xffff
005164:  ffff  dw      0xffff
005166:  ffff  dw      0xffff
005168:  ffff  dw      0xffff
00516a:  ffff  dw      0xffff
00516c:  ffff  dw      0xffff
00516e:  ffff  dw      0xffff
005170:  ffff  dw      0xffff
005172:  ffff  dw      0xffff
005174:  ffff  dw      0xffff
005176:  ffff  dw      0xffff
005178:  ffff  dw      0xffff
00517a:  ffff  dw      0xffff
00517c:  ffff  dw      0xffff
00517e:  ffff  dw      0xffff
005180:  ffff  dw      0xffff
005182:  ffff  dw      0xffff
005184:  ffff  dw      0xffff
005186:  ffff  dw      0xffff
005188:  ffff  dw      0xffff
00518a:  ffff  dw      0xffff
00518c:  ffff  dw      0xffff
00518e:  ffff  dw      0xffff
005190:  ffff  dw      0xffff
005192:  ffff  dw      0xffff
005194:  ffff  dw      0xffff
005196:  ffff  dw      0xffff
005198:  ffff  dw      0xffff
00519a:  ffff  dw      0xffff
00519c:  ffff  dw      0xffff
00519e:  ffff  dw      0xffff
0051a0:  ffff  dw      0xffff
0051a2:  ffff  dw      0xffff
0051a4:  ffff  dw      0xffff
0051a6:  ffff  dw      0xffff
0051a8:  ffff  dw      0xffff
0051aa:  ffff  dw      0xffff
0051ac:  ffff  dw      0xffff
0051ae:  ffff  dw      0xffff
0051b0:  ffff  dw      0xffff
0051b2:  ffff  dw      0xffff
0051b4:  ffff  dw      0xffff
0051b6:  ffff  dw      0xffff
0051b8:  ffff  dw      0xffff
0051ba:  ffff  dw      0xffff
0051bc:  ffff  dw      0xffff
0051be:  ffff  dw      0xffff
0051c0:  ffff  dw      0xffff
0051c2:  ffff  dw      0xffff
0051c4:  ffff  dw      0xffff
0051c6:  ffff  dw      0xffff
0051c8:  ffff  dw      0xffff
0051ca:  ffff  dw      0xffff
0051cc:  ffff  dw      0xffff
0051ce:  ffff  dw      0xffff
0051d0:  ffff  dw      0xffff
0051d2:  ffff  dw      0xffff
0051d4:  ffff  dw      0xffff
0051d6:  ffff  dw      0xffff
0051d8:  ffff  dw      0xffff
0051da:  ffff  dw      0xffff
0051dc:  ffff  dw      0xffff
0051de:  ffff  dw      0xffff
0051e0:  ffff  dw      0xffff
0051e2:  ffff  dw      0xffff
0051e4:  ffff  dw      0xffff
0051e6:  ffff  dw      0xffff
0051e8:  ffff  dw      0xffff
0051ea:  ffff  dw      0xffff
0051ec:  ffff  dw      0xffff
0051ee:  ffff  dw      0xffff
0051f0:  ffff  dw      0xffff
0051f2:  ffff  dw      0xffff
0051f4:  ffff  dw      0xffff
0051f6:  ffff  dw      0xffff
0051f8:  ffff  dw      0xffff
0051fa:  ffff  dw      0xffff
0051fc:  ffff  dw      0xffff
0051fe:  ffff  dw      0xffff
005200:  ffff  dw      0xffff
005202:  ffff  dw      0xffff
005204:  ffff  dw      0xffff
005206:  ffff  dw      0xffff
005208:  ffff  dw      0xffff
00520a:  ffff  dw      0xffff
00520c:  ffff  dw      0xffff
00520e:  ffff  dw      0xffff
005210:  ffff  dw      0xffff
005212:  ffff  dw      0xffff
005214:  ffff  dw      0xffff
005216:  ffff  dw      0xffff
005218:  ffff  dw      0xffff
00521a:  ffff  dw      0xffff
00521c:  ffff  dw      0xffff
00521e:  ffff  dw      0xffff
005220:  ffff  dw      0xffff
005222:  ffff  dw      0xffff
005224:  ffff  dw      0xffff
005226:  ffff  dw      0xffff
005228:  ffff  dw      0xffff
00522a:  ffff  dw      0xffff
00522c:  ffff  dw      0xffff
00522e:  ffff  dw      0xffff
005230:  ffff  dw      0xffff
005232:  ffff  dw      0xffff
005234:  ffff  dw      0xffff
005236:  ffff  dw      0xffff
005238:  ffff  dw      0xffff
00523a:  ffff  dw      0xffff
00523c:  ffff  dw      0xffff
00523e:  ffff  dw      0xffff
005240:  ffff  dw      0xffff
005242:  ffff  dw      0xffff
005244:  ffff  dw      0xffff
005246:  ffff  dw      0xffff
005248:  ffff  dw      0xffff
00524a:  ffff  dw      0xffff
00524c:  ffff  dw      0xffff
00524e:  ffff  dw      0xffff
005250:  ffff  dw      0xffff
005252:  ffff  dw      0xffff
005254:  ffff  dw      0xffff
005256:  ffff  dw      0xffff
005258:  ffff  dw      0xffff
00525a:  ffff  dw      0xffff
00525c:  ffff  dw      0xffff
00525e:  ffff  dw      0xffff
005260:  ffff  dw      0xffff
005262:  ffff  dw      0xffff
005264:  ffff  dw      0xffff
005266:  ffff  dw      0xffff
005268:  ffff  dw      0xffff
00526a:  ffff  dw      0xffff
00526c:  ffff  dw      0xffff
00526e:  ffff  dw      0xffff
005270:  ffff  dw      0xffff
005272:  ffff  dw      0xffff
005274:  ffff  dw      0xffff
005276:  ffff  dw      0xffff
005278:  ffff  dw      0xffff
00527a:  ffff  dw      0xffff
00527c:  ffff  dw      0xffff
00527e:  ffff  dw      0xffff
005280:  ffff  dw      0xffff
005282:  ffff  dw      0xffff
005284:  ffff  dw      0xffff
005286:  ffff  dw      0xffff
005288:  ffff  dw      0xffff
00528a:  ffff  dw      0xffff
00528c:  ffff  dw      0xffff
00528e:  ffff  dw      0xffff
005290:  ffff  dw      0xffff
005292:  ffff  dw      0xffff
005294:  ffff  dw      0xffff
005296:  ffff  dw      0xffff
005298:  ffff  dw      0xffff
00529a:  ffff  dw      0xffff
00529c:  ffff  dw      0xffff
00529e:  ffff  dw      0xffff
0052a0:  ffff  dw      0xffff
0052a2:  ffff  dw      0xffff
0052a4:  ffff  dw      0xffff
0052a6:  ffff  dw      0xffff
0052a8:  ffff  dw      0xffff
0052aa:  ffff  dw      0xffff
0052ac:  ffff  dw      0xffff
0052ae:  ffff  dw      0xffff
0052b0:  ffff  dw      0xffff
0052b2:  ffff  dw      0xffff
0052b4:  ffff  dw      0xffff
0052b6:  ffff  dw      0xffff
0052b8:  ffff  dw      0xffff
0052ba:  ffff  dw      0xffff
0052bc:  ffff  dw      0xffff
0052be:  ffff  dw      0xffff
0052c0:  ffff  dw      0xffff
0052c2:  ffff  dw      0xffff
0052c4:  ffff  dw      0xffff
0052c6:  ffff  dw      0xffff
0052c8:  ffff  dw      0xffff
0052ca:  ffff  dw      0xffff
0052cc:  ffff  dw      0xffff
0052ce:  ffff  dw      0xffff
0052d0:  ffff  dw      0xffff
0052d2:  ffff  dw      0xffff
0052d4:  ffff  dw      0xffff
0052d6:  ffff  dw      0xffff
0052d8:  ffff  dw      0xffff
0052da:  ffff  dw      0xffff
0052dc:  ffff  dw      0xffff
0052de:  ffff  dw      0xffff
0052e0:  ffff  dw      0xffff
0052e2:  ffff  dw      0xffff
0052e4:  ffff  dw      0xffff
0052e6:  ffff  dw      0xffff
0052e8:  ffff  dw      0xffff
0052ea:  ffff  dw      0xffff
0052ec:  ffff  dw      0xffff
0052ee:  ffff  dw      0xffff
0052f0:  ffff  dw      0xffff
0052f2:  ffff  dw      0xffff
0052f4:  ffff  dw      0xffff
0052f6:  ffff  dw      0xffff
0052f8:  ffff  dw      0xffff
0052fa:  ffff  dw      0xffff
0052fc:  ffff  dw      0xffff
0052fe:  ffff  dw      0xffff
005300:  ffff  dw      0xffff
005302:  ffff  dw      0xffff
005304:  ffff  dw      0xffff
005306:  ffff  dw      0xffff
005308:  ffff  dw      0xffff
00530a:  ffff  dw      0xffff
00530c:  ffff  dw      0xffff
00530e:  ffff  dw      0xffff
005310:  ffff  dw      0xffff
005312:  ffff  dw      0xffff
005314:  ffff  dw      0xffff
005316:  ffff  dw      0xffff
005318:  ffff  dw      0xffff
00531a:  ffff  dw      0xffff
00531c:  ffff  dw      0xffff
00531e:  ffff  dw      0xffff
005320:  ffff  dw      0xffff
005322:  ffff  dw      0xffff
005324:  ffff  dw      0xffff
005326:  ffff  dw      0xffff
005328:  ffff  dw      0xffff
00532a:  ffff  dw      0xffff
00532c:  ffff  dw      0xffff
00532e:  ffff  dw      0xffff
005330:  ffff  dw      0xffff
005332:  ffff  dw      0xffff
005334:  ffff  dw      0xffff
005336:  ffff  dw      0xffff
005338:  ffff  dw      0xffff
00533a:  ffff  dw      0xffff
00533c:  ffff  dw      0xffff
00533e:  ffff  dw      0xffff
005340:  ffff  dw      0xffff
005342:  ffff  dw      0xffff
005344:  ffff  dw      0xffff
005346:  ffff  dw      0xffff
005348:  ffff  dw      0xffff
00534a:  ffff  dw      0xffff
00534c:  ffff  dw      0xffff
00534e:  ffff  dw      0xffff
005350:  ffff  dw      0xffff
005352:  ffff  dw      0xffff
005354:  ffff  dw      0xffff
005356:  ffff  dw      0xffff
005358:  ffff  dw      0xffff
00535a:  ffff  dw      0xffff
00535c:  ffff  dw      0xffff
00535e:  ffff  dw      0xffff
005360:  ffff  dw      0xffff
005362:  ffff  dw      0xffff
005364:  ffff  dw      0xffff
005366:  ffff  dw      0xffff
005368:  ffff  dw      0xffff
00536a:  ffff  dw      0xffff
00536c:  ffff  dw      0xffff
00536e:  ffff  dw      0xffff
005370:  ffff  dw      0xffff
005372:  ffff  dw      0xffff
005374:  ffff  dw      0xffff
005376:  ffff  dw      0xffff
005378:  ffff  dw      0xffff
00537a:  ffff  dw      0xffff
00537c:  ffff  dw      0xffff
00537e:  ffff  dw      0xffff
005380:  ffff  dw      0xffff
005382:  ffff  dw      0xffff
005384:  ffff  dw      0xffff
005386:  ffff  dw      0xffff
005388:  ffff  dw      0xffff
00538a:  ffff  dw      0xffff
00538c:  ffff  dw      0xffff
00538e:  ffff  dw      0xffff
005390:  ffff  dw      0xffff
005392:  ffff  dw      0xffff
005394:  ffff  dw      0xffff
005396:  ffff  dw      0xffff
005398:  ffff  dw      0xffff
00539a:  ffff  dw      0xffff
00539c:  ffff  dw      0xffff
00539e:  ffff  dw      0xffff
0053a0:  ffff  dw      0xffff
0053a2:  ffff  dw      0xffff
0053a4:  ffff  dw      0xffff
0053a6:  ffff  dw      0xffff
0053a8:  ffff  dw      0xffff
0053aa:  ffff  dw      0xffff
0053ac:  ffff  dw      0xffff
0053ae:  ffff  dw      0xffff
0053b0:  ffff  dw      0xffff
0053b2:  ffff  dw      0xffff
0053b4:  ffff  dw      0xffff
0053b6:  ffff  dw      0xffff
0053b8:  ffff  dw      0xffff
0053ba:  ffff  dw      0xffff
0053bc:  ffff  dw      0xffff
0053be:  ffff  dw      0xffff
0053c0:  ffff  dw      0xffff
0053c2:  ffff  dw      0xffff
0053c4:  ffff  dw      0xffff
0053c6:  ffff  dw      0xffff
0053c8:  ffff  dw      0xffff
0053ca:  ffff  dw      0xffff
0053cc:  ffff  dw      0xffff
0053ce:  ffff  dw      0xffff
0053d0:  ffff  dw      0xffff
0053d2:  ffff  dw      0xffff
0053d4:  ffff  dw      0xffff
0053d6:  ffff  dw      0xffff
0053d8:  ffff  dw      0xffff
0053da:  ffff  dw      0xffff
0053dc:  ffff  dw      0xffff
0053de:  ffff  dw      0xffff
0053e0:  ffff  dw      0xffff
0053e2:  ffff  dw      0xffff
0053e4:  ffff  dw      0xffff
0053e6:  ffff  dw      0xffff
0053e8:  ffff  dw      0xffff
0053ea:  ffff  dw      0xffff
0053ec:  ffff  dw      0xffff
0053ee:  ffff  dw      0xffff
0053f0:  ffff  dw      0xffff
0053f2:  ffff  dw      0xffff
0053f4:  ffff  dw      0xffff
0053f6:  ffff  dw      0xffff
0053f8:  ffff  dw      0xffff
0053fa:  ffff  dw      0xffff
0053fc:  ffff  dw      0xffff
0053fe:  ffff  dw      0xffff
005400:  ffff  dw      0xffff
005402:  ffff  dw      0xffff
005404:  ffff  dw      0xffff
005406:  ffff  dw      0xffff
005408:  ffff  dw      0xffff
00540a:  ffff  dw      0xffff
00540c:  ffff  dw      0xffff
00540e:  ffff  dw      0xffff
005410:  ffff  dw      0xffff
005412:  ffff  dw      0xffff
005414:  ffff  dw      0xffff
005416:  ffff  dw      0xffff
005418:  ffff  dw      0xffff
00541a:  ffff  dw      0xffff
00541c:  ffff  dw      0xffff
00541e:  ffff  dw      0xffff
005420:  ffff  dw      0xffff
005422:  ffff  dw      0xffff
005424:  ffff  dw      0xffff
005426:  ffff  dw      0xffff
005428:  ffff  dw      0xffff
00542a:  ffff  dw      0xffff
00542c:  ffff  dw      0xffff
00542e:  ffff  dw      0xffff
005430:  ffff  dw      0xffff
005432:  ffff  dw      0xffff
005434:  ffff  dw      0xffff
005436:  ffff  dw      0xffff
005438:  ffff  dw      0xffff
00543a:  ffff  dw      0xffff
00543c:  ffff  dw      0xffff
00543e:  ffff  dw      0xffff
005440:  ffff  dw      0xffff
005442:  ffff  dw      0xffff
005444:  ffff  dw      0xffff
005446:  ffff  dw      0xffff
005448:  ffff  dw      0xffff
00544a:  ffff  dw      0xffff
00544c:  ffff  dw      0xffff
00544e:  ffff  dw      0xffff
005450:  ffff  dw      0xffff
005452:  ffff  dw      0xffff
005454:  ffff  dw      0xffff
005456:  ffff  dw      0xffff
005458:  ffff  dw      0xffff
00545a:  ffff  dw      0xffff
00545c:  ffff  dw      0xffff
00545e:  ffff  dw      0xffff
005460:  ffff  dw      0xffff
005462:  ffff  dw      0xffff
005464:  ffff  dw      0xffff
005466:  ffff  dw      0xffff
005468:  ffff  dw      0xffff
00546a:  ffff  dw      0xffff
00546c:  ffff  dw      0xffff
00546e:  ffff  dw      0xffff
005470:  ffff  dw      0xffff
005472:  ffff  dw      0xffff
005474:  ffff  dw      0xffff
005476:  ffff  dw      0xffff
005478:  ffff  dw      0xffff
00547a:  ffff  dw      0xffff
00547c:  ffff  dw      0xffff
00547e:  ffff  dw      0xffff
005480:  ffff  dw      0xffff
005482:  ffff  dw      0xffff
005484:  ffff  dw      0xffff
005486:  ffff  dw      0xffff
005488:  ffff  dw      0xffff
00548a:  ffff  dw      0xffff
00548c:  ffff  dw      0xffff
00548e:  ffff  dw      0xffff
005490:  ffff  dw      0xffff
005492:  ffff  dw      0xffff
005494:  ffff  dw      0xffff
005496:  ffff  dw      0xffff
005498:  ffff  dw      0xffff
00549a:  ffff  dw      0xffff
00549c:  ffff  dw      0xffff
00549e:  ffff  dw      0xffff
0054a0:  ffff  dw      0xffff
0054a2:  ffff  dw      0xffff
0054a4:  ffff  dw      0xffff
0054a6:  ffff  dw      0xffff
0054a8:  ffff  dw      0xffff
0054aa:  ffff  dw      0xffff
0054ac:  ffff  dw      0xffff
0054ae:  ffff  dw      0xffff
0054b0:  ffff  dw      0xffff
0054b2:  ffff  dw      0xffff
0054b4:  ffff  dw      0xffff
0054b6:  ffff  dw      0xffff
0054b8:  ffff  dw      0xffff
0054ba:  ffff  dw      0xffff
0054bc:  ffff  dw      0xffff
0054be:  ffff  dw      0xffff
0054c0:  ffff  dw      0xffff
0054c2:  ffff  dw      0xffff
0054c4:  ffff  dw      0xffff
0054c6:  ffff  dw      0xffff
0054c8:  ffff  dw      0xffff
0054ca:  ffff  dw      0xffff
0054cc:  ffff  dw      0xffff
0054ce:  ffff  dw      0xffff
0054d0:  ffff  dw      0xffff
0054d2:  ffff  dw      0xffff
0054d4:  ffff  dw      0xffff
0054d6:  ffff  dw      0xffff
0054d8:  ffff  dw      0xffff
0054da:  ffff  dw      0xffff
0054dc:  ffff  dw      0xffff
0054de:  ffff  dw      0xffff
0054e0:  ffff  dw      0xffff
0054e2:  ffff  dw      0xffff
0054e4:  ffff  dw      0xffff
0054e6:  ffff  dw      0xffff
0054e8:  ffff  dw      0xffff
0054ea:  ffff  dw      0xffff
0054ec:  ffff  dw      0xffff
0054ee:  ffff  dw      0xffff
0054f0:  ffff  dw      0xffff
0054f2:  ffff  dw      0xffff
0054f4:  ffff  dw      0xffff
0054f6:  ffff  dw      0xffff
0054f8:  ffff  dw      0xffff
0054fa:  ffff  dw      0xffff
0054fc:  ffff  dw      0xffff
0054fe:  ffff  dw      0xffff
005500:  ffff  dw      0xffff
005502:  ffff  dw      0xffff
005504:  ffff  dw      0xffff
005506:  ffff  dw      0xffff
005508:  ffff  dw      0xffff
00550a:  ffff  dw      0xffff
00550c:  ffff  dw      0xffff
00550e:  ffff  dw      0xffff
005510:  ffff  dw      0xffff
005512:  ffff  dw      0xffff
005514:  ffff  dw      0xffff
005516:  ffff  dw      0xffff
005518:  ffff  dw      0xffff
00551a:  ffff  dw      0xffff
00551c:  ffff  dw      0xffff
00551e:  ffff  dw      0xffff
005520:  ffff  dw      0xffff
005522:  ffff  dw      0xffff
005524:  ffff  dw      0xffff
005526:  ffff  dw      0xffff
005528:  ffff  dw      0xffff
00552a:  ffff  dw      0xffff
00552c:  ffff  dw      0xffff
00552e:  ffff  dw      0xffff
005530:  ffff  dw      0xffff
005532:  ffff  dw      0xffff
005534:  ffff  dw      0xffff
005536:  ffff  dw      0xffff
005538:  ffff  dw      0xffff
00553a:  ffff  dw      0xffff
00553c:  ffff  dw      0xffff
00553e:  ffff  dw      0xffff
005540:  ffff  dw      0xffff
005542:  ffff  dw      0xffff
005544:  ffff  dw      0xffff
005546:  ffff  dw      0xffff
005548:  ffff  dw      0xffff
00554a:  ffff  dw      0xffff
00554c:  ffff  dw      0xffff
00554e:  ffff  dw      0xffff
005550:  ffff  dw      0xffff
005552:  ffff  dw      0xffff
005554:  ffff  dw      0xffff
005556:  ffff  dw      0xffff
005558:  ffff  dw      0xffff
00555a:  ffff  dw      0xffff
00555c:  ffff  dw      0xffff
00555e:  ffff  dw      0xffff
005560:  ffff  dw      0xffff
005562:  ffff  dw      0xffff
005564:  ffff  dw      0xffff
005566:  ffff  dw      0xffff
005568:  ffff  dw      0xffff
00556a:  ffff  dw      0xffff
00556c:  ffff  dw      0xffff
00556e:  ffff  dw      0xffff
005570:  ffff  dw      0xffff
005572:  ffff  dw      0xffff
005574:  ffff  dw      0xffff
005576:  ffff  dw      0xffff
005578:  ffff  dw      0xffff
00557a:  ffff  dw      0xffff
00557c:  ffff  dw      0xffff
00557e:  ffff  dw      0xffff
005580:  ffff  dw      0xffff
005582:  ffff  dw      0xffff
005584:  ffff  dw      0xffff
005586:  ffff  dw      0xffff
005588:  ffff  dw      0xffff
00558a:  ffff  dw      0xffff
00558c:  ffff  dw      0xffff
00558e:  ffff  dw      0xffff
005590:  ffff  dw      0xffff
005592:  ffff  dw      0xffff
005594:  ffff  dw      0xffff
005596:  ffff  dw      0xffff
005598:  ffff  dw      0xffff
00559a:  ffff  dw      0xffff
00559c:  ffff  dw      0xffff
00559e:  ffff  dw      0xffff
0055a0:  ffff  dw      0xffff
0055a2:  ffff  dw      0xffff
0055a4:  ffff  dw      0xffff
0055a6:  ffff  dw      0xffff
0055a8:  ffff  dw      0xffff
0055aa:  ffff  dw      0xffff
0055ac:  ffff  dw      0xffff
0055ae:  ffff  dw      0xffff
0055b0:  ffff  dw      0xffff
0055b2:  ffff  dw      0xffff
0055b4:  ffff  dw      0xffff
0055b6:  ffff  dw      0xffff
0055b8:  ffff  dw      0xffff
0055ba:  ffff  dw      0xffff
0055bc:  ffff  dw      0xffff
0055be:  ffff  dw      0xffff
0055c0:  ffff  dw      0xffff
0055c2:  ffff  dw      0xffff
0055c4:  ffff  dw      0xffff
0055c6:  ffff  dw      0xffff
0055c8:  ffff  dw      0xffff
0055ca:  ffff  dw      0xffff
0055cc:  ffff  dw      0xffff
0055ce:  ffff  dw      0xffff
0055d0:  ffff  dw      0xffff
0055d2:  ffff  dw      0xffff
0055d4:  ffff  dw      0xffff
0055d6:  ffff  dw      0xffff
0055d8:  ffff  dw      0xffff
0055da:  ffff  dw      0xffff
0055dc:  ffff  dw      0xffff
0055de:  ffff  dw      0xffff
0055e0:  ffff  dw      0xffff
0055e2:  ffff  dw      0xffff
0055e4:  ffff  dw      0xffff
0055e6:  ffff  dw      0xffff
0055e8:  ffff  dw      0xffff
0055ea:  ffff  dw      0xffff
0055ec:  ffff  dw      0xffff
0055ee:  ffff  dw      0xffff
0055f0:  ffff  dw      0xffff
0055f2:  ffff  dw      0xffff
0055f4:  ffff  dw      0xffff
0055f6:  ffff  dw      0xffff
0055f8:  ffff  dw      0xffff
0055fa:  ffff  dw      0xffff
0055fc:  ffff  dw      0xffff
0055fe:  ffff  dw      0xffff
005600:  ffff  dw      0xffff
005602:  ffff  dw      0xffff
005604:  ffff  dw      0xffff
005606:  ffff  dw      0xffff
005608:  ffff  dw      0xffff
00560a:  ffff  dw      0xffff
00560c:  ffff  dw      0xffff
00560e:  ffff  dw      0xffff
005610:  ffff  dw      0xffff
005612:  ffff  dw      0xffff
005614:  ffff  dw      0xffff
005616:  ffff  dw      0xffff
005618:  ffff  dw      0xffff
00561a:  ffff  dw      0xffff
00561c:  ffff  dw      0xffff
00561e:  ffff  dw      0xffff
005620:  ffff  dw      0xffff
005622:  ffff  dw      0xffff
005624:  ffff  dw      0xffff
005626:  ffff  dw      0xffff
005628:  ffff  dw      0xffff
00562a:  ffff  dw      0xffff
00562c:  ffff  dw      0xffff
00562e:  ffff  dw      0xffff
005630:  ffff  dw      0xffff
005632:  ffff  dw      0xffff
005634:  ffff  dw      0xffff
005636:  ffff  dw      0xffff
005638:  ffff  dw      0xffff
00563a:  ffff  dw      0xffff
00563c:  ffff  dw      0xffff
00563e:  ffff  dw      0xffff
005640:  ffff  dw      0xffff
005642:  ffff  dw      0xffff
005644:  ffff  dw      0xffff
005646:  ffff  dw      0xffff
005648:  ffff  dw      0xffff
00564a:  ffff  dw      0xffff
00564c:  ffff  dw      0xffff
00564e:  ffff  dw      0xffff
005650:  ffff  dw      0xffff
005652:  ffff  dw      0xffff
005654:  ffff  dw      0xffff
005656:  ffff  dw      0xffff
005658:  ffff  dw      0xffff
00565a:  ffff  dw      0xffff
00565c:  ffff  dw      0xffff
00565e:  ffff  dw      0xffff
005660:  ffff  dw      0xffff
005662:  ffff  dw      0xffff
005664:  ffff  dw      0xffff
005666:  ffff  dw      0xffff
005668:  ffff  dw      0xffff
00566a:  ffff  dw      0xffff
00566c:  ffff  dw      0xffff
00566e:  ffff  dw      0xffff
005670:  ffff  dw      0xffff
005672:  ffff  dw      0xffff
005674:  ffff  dw      0xffff
005676:  ffff  dw      0xffff
005678:  ffff  dw      0xffff
00567a:  ffff  dw      0xffff
00567c:  ffff  dw      0xffff
00567e:  ffff  dw      0xffff
005680:  ffff  dw      0xffff
005682:  ffff  dw      0xffff
005684:  ffff  dw      0xffff
005686:  ffff  dw      0xffff
005688:  ffff  dw      0xffff
00568a:  ffff  dw      0xffff
00568c:  ffff  dw      0xffff
00568e:  ffff  dw      0xffff
005690:  ffff  dw      0xffff
005692:  ffff  dw      0xffff
005694:  ffff  dw      0xffff
005696:  ffff  dw      0xffff
005698:  ffff  dw      0xffff
00569a:  ffff  dw      0xffff
00569c:  ffff  dw      0xffff
00569e:  ffff  dw      0xffff
0056a0:  ffff  dw      0xffff
0056a2:  ffff  dw      0xffff
0056a4:  ffff  dw      0xffff
0056a6:  ffff  dw      0xffff
0056a8:  ffff  dw      0xffff
0056aa:  ffff  dw      0xffff
0056ac:  ffff  dw      0xffff
0056ae:  ffff  dw      0xffff
0056b0:  ffff  dw      0xffff
0056b2:  ffff  dw      0xffff
0056b4:  ffff  dw      0xffff
0056b6:  ffff  dw      0xffff
0056b8:  ffff  dw      0xffff
0056ba:  ffff  dw      0xffff
0056bc:  ffff  dw      0xffff
0056be:  ffff  dw      0xffff
0056c0:  ffff  dw      0xffff
0056c2:  ffff  dw      0xffff
0056c4:  ffff  dw      0xffff
0056c6:  ffff  dw      0xffff
0056c8:  ffff  dw      0xffff
0056ca:  ffff  dw      0xffff
0056cc:  ffff  dw      0xffff
0056ce:  ffff  dw      0xffff
0056d0:  ffff  dw      0xffff
0056d2:  ffff  dw      0xffff
0056d4:  ffff  dw      0xffff
0056d6:  ffff  dw      0xffff
0056d8:  ffff  dw      0xffff
0056da:  ffff  dw      0xffff
0056dc:  ffff  dw      0xffff
0056de:  ffff  dw      0xffff
0056e0:  ffff  dw      0xffff
0056e2:  ffff  dw      0xffff
0056e4:  ffff  dw      0xffff
0056e6:  ffff  dw      0xffff
0056e8:  ffff  dw      0xffff
0056ea:  ffff  dw      0xffff
0056ec:  ffff  dw      0xffff
0056ee:  ffff  dw      0xffff
0056f0:  ffff  dw      0xffff
0056f2:  ffff  dw      0xffff
0056f4:  ffff  dw      0xffff
0056f6:  ffff  dw      0xffff
0056f8:  ffff  dw      0xffff
0056fa:  ffff  dw      0xffff
0056fc:  ffff  dw      0xffff
0056fe:  ffff  dw      0xffff
005700:  ffff  dw      0xffff
005702:  ffff  dw      0xffff
005704:  ffff  dw      0xffff
005706:  ffff  dw      0xffff
005708:  ffff  dw      0xffff
00570a:  ffff  dw      0xffff
00570c:  ffff  dw      0xffff
00570e:  ffff  dw      0xffff
005710:  ffff  dw      0xffff
005712:  ffff  dw      0xffff
005714:  ffff  dw      0xffff
005716:  ffff  dw      0xffff
005718:  ffff  dw      0xffff
00571a:  ffff  dw      0xffff
00571c:  ffff  dw      0xffff
00571e:  ffff  dw      0xffff
005720:  ffff  dw      0xffff
005722:  ffff  dw      0xffff
005724:  ffff  dw      0xffff
005726:  ffff  dw      0xffff
005728:  ffff  dw      0xffff
00572a:  ffff  dw      0xffff
00572c:  ffff  dw      0xffff
00572e:  ffff  dw      0xffff
005730:  ffff  dw      0xffff
005732:  ffff  dw      0xffff
005734:  ffff  dw      0xffff
005736:  ffff  dw      0xffff
005738:  ffff  dw      0xffff
00573a:  ffff  dw      0xffff
00573c:  ffff  dw      0xffff
00573e:  ffff  dw      0xffff
005740:  ffff  dw      0xffff
005742:  ffff  dw      0xffff
005744:  ffff  dw      0xffff
005746:  ffff  dw      0xffff
005748:  ffff  dw      0xffff
00574a:  ffff  dw      0xffff
00574c:  ffff  dw      0xffff
00574e:  ffff  dw      0xffff
005750:  ffff  dw      0xffff
005752:  ffff  dw      0xffff
005754:  ffff  dw      0xffff
005756:  ffff  dw      0xffff
005758:  ffff  dw      0xffff
00575a:  ffff  dw      0xffff
00575c:  ffff  dw      0xffff
00575e:  ffff  dw      0xffff
005760:  ffff  dw      0xffff
005762:  ffff  dw      0xffff
005764:  ffff  dw      0xffff
005766:  ffff  dw      0xffff
005768:  ffff  dw      0xffff
00576a:  ffff  dw      0xffff
00576c:  ffff  dw      0xffff
00576e:  ffff  dw      0xffff
005770:  ffff  dw      0xffff
005772:  ffff  dw      0xffff
005774:  ffff  dw      0xffff
005776:  ffff  dw      0xffff
005778:  ffff  dw      0xffff
00577a:  ffff  dw      0xffff
00577c:  ffff  dw      0xffff
00577e:  ffff  dw      0xffff
005780:  ffff  dw      0xffff
005782:  ffff  dw      0xffff
005784:  ffff  dw      0xffff
005786:  ffff  dw      0xffff
005788:  ffff  dw      0xffff
00578a:  ffff  dw      0xffff
00578c:  ffff  dw      0xffff
00578e:  ffff  dw      0xffff
005790:  ffff  dw      0xffff
005792:  ffff  dw      0xffff
005794:  ffff  dw      0xffff
005796:  ffff  dw      0xffff
005798:  ffff  dw      0xffff
00579a:  ffff  dw      0xffff
00579c:  ffff  dw      0xffff
00579e:  ffff  dw      0xffff
0057a0:  ffff  dw      0xffff
0057a2:  ffff  dw      0xffff
0057a4:  ffff  dw      0xffff
0057a6:  ffff  dw      0xffff
0057a8:  ffff  dw      0xffff
0057aa:  ffff  dw      0xffff
0057ac:  ffff  dw      0xffff
0057ae:  ffff  dw      0xffff
0057b0:  ffff  dw      0xffff
0057b2:  ffff  dw      0xffff
0057b4:  ffff  dw      0xffff
0057b6:  ffff  dw      0xffff
0057b8:  ffff  dw      0xffff
0057ba:  ffff  dw      0xffff
0057bc:  ffff  dw      0xffff
0057be:  ffff  dw      0xffff
0057c0:  ffff  dw      0xffff
0057c2:  ffff  dw      0xffff
0057c4:  ffff  dw      0xffff
0057c6:  ffff  dw      0xffff
0057c8:  ffff  dw      0xffff
0057ca:  ffff  dw      0xffff
0057cc:  ffff  dw      0xffff
0057ce:  ffff  dw      0xffff
0057d0:  ffff  dw      0xffff
0057d2:  ffff  dw      0xffff
0057d4:  ffff  dw      0xffff
0057d6:  ffff  dw      0xffff
0057d8:  ffff  dw      0xffff
0057da:  ffff  dw      0xffff
0057dc:  ffff  dw      0xffff
0057de:  ffff  dw      0xffff
0057e0:  ffff  dw      0xffff
0057e2:  ffff  dw      0xffff
0057e4:  ffff  dw      0xffff
0057e6:  ffff  dw      0xffff
0057e8:  ffff  dw      0xffff
0057ea:  ffff  dw      0xffff
0057ec:  ffff  dw      0xffff
0057ee:  ffff  dw      0xffff
0057f0:  ffff  dw      0xffff
0057f2:  ffff  dw      0xffff
0057f4:  ffff  dw      0xffff
0057f6:  ffff  dw      0xffff
0057f8:  ffff  dw      0xffff
0057fa:  ffff  dw      0xffff
0057fc:  ffff  dw      0xffff
0057fe:  ffff  dw      0xffff
005800:  ffff  dw      0xffff
005802:  ffff  dw      0xffff
005804:  ffff  dw      0xffff
005806:  ffff  dw      0xffff
005808:  ffff  dw      0xffff
00580a:  ffff  dw      0xffff
00580c:  ffff  dw      0xffff
00580e:  ffff  dw      0xffff
005810:  ffff  dw      0xffff
005812:  ffff  dw      0xffff
005814:  ffff  dw      0xffff
005816:  ffff  dw      0xffff
005818:  ffff  dw      0xffff
00581a:  ffff  dw      0xffff
00581c:  ffff  dw      0xffff
00581e:  ffff  dw      0xffff
005820:  ffff  dw      0xffff
005822:  ffff  dw      0xffff
005824:  ffff  dw      0xffff
005826:  ffff  dw      0xffff
005828:  ffff  dw      0xffff
00582a:  ffff  dw      0xffff
00582c:  ffff  dw      0xffff
00582e:  ffff  dw      0xffff
005830:  ffff  dw      0xffff
005832:  ffff  dw      0xffff
005834:  ffff  dw      0xffff
005836:  ffff  dw      0xffff
005838:  ffff  dw      0xffff
00583a:  ffff  dw      0xffff
00583c:  ffff  dw      0xffff
00583e:  ffff  dw      0xffff
005840:  ffff  dw      0xffff
005842:  ffff  dw      0xffff
005844:  ffff  dw      0xffff
005846:  ffff  dw      0xffff
005848:  ffff  dw      0xffff
00584a:  ffff  dw      0xffff
00584c:  ffff  dw      0xffff
00584e:  ffff  dw      0xffff
005850:  ffff  dw      0xffff
005852:  ffff  dw      0xffff
005854:  ffff  dw      0xffff
005856:  ffff  dw      0xffff
005858:  ffff  dw      0xffff
00585a:  ffff  dw      0xffff
00585c:  ffff  dw      0xffff
00585e:  ffff  dw      0xffff
005860:  ffff  dw      0xffff
005862:  ffff  dw      0xffff
005864:  ffff  dw      0xffff
005866:  ffff  dw      0xffff
005868:  ffff  dw      0xffff
00586a:  ffff  dw      0xffff
00586c:  ffff  dw      0xffff
00586e:  ffff  dw      0xffff
005870:  ffff  dw      0xffff
005872:  ffff  dw      0xffff
005874:  ffff  dw      0xffff
005876:  ffff  dw      0xffff
005878:  ffff  dw      0xffff
00587a:  ffff  dw      0xffff
00587c:  ffff  dw      0xffff
00587e:  ffff  dw      0xffff
005880:  ffff  dw      0xffff
005882:  ffff  dw      0xffff
005884:  ffff  dw      0xffff
005886:  ffff  dw      0xffff
005888:  ffff  dw      0xffff
00588a:  ffff  dw      0xffff
00588c:  ffff  dw      0xffff
00588e:  ffff  dw      0xffff
005890:  ffff  dw      0xffff
005892:  ffff  dw      0xffff
005894:  ffff  dw      0xffff
005896:  ffff  dw      0xffff
005898:  ffff  dw      0xffff
00589a:  ffff  dw      0xffff
00589c:  ffff  dw      0xffff
00589e:  ffff  dw      0xffff
0058a0:  ffff  dw      0xffff
0058a2:  ffff  dw      0xffff
0058a4:  ffff  dw      0xffff
0058a6:  ffff  dw      0xffff
0058a8:  ffff  dw      0xffff
0058aa:  ffff  dw      0xffff
0058ac:  ffff  dw      0xffff
0058ae:  ffff  dw      0xffff
0058b0:  ffff  dw      0xffff
0058b2:  ffff  dw      0xffff
0058b4:  ffff  dw      0xffff
0058b6:  ffff  dw      0xffff
0058b8:  ffff  dw      0xffff
0058ba:  ffff  dw      0xffff
0058bc:  ffff  dw      0xffff
0058be:  ffff  dw      0xffff
0058c0:  ffff  dw      0xffff
0058c2:  ffff  dw      0xffff
0058c4:  ffff  dw      0xffff
0058c6:  ffff  dw      0xffff
0058c8:  ffff  dw      0xffff
0058ca:  ffff  dw      0xffff
0058cc:  ffff  dw      0xffff
0058ce:  ffff  dw      0xffff
0058d0:  ffff  dw      0xffff
0058d2:  ffff  dw      0xffff
0058d4:  ffff  dw      0xffff
0058d6:  ffff  dw      0xffff
0058d8:  ffff  dw      0xffff
0058da:  ffff  dw      0xffff
0058dc:  ffff  dw      0xffff
0058de:  ffff  dw      0xffff
0058e0:  ffff  dw      0xffff
0058e2:  ffff  dw      0xffff
0058e4:  ffff  dw      0xffff
0058e6:  ffff  dw      0xffff
0058e8:  ffff  dw      0xffff
0058ea:  ffff  dw      0xffff
0058ec:  ffff  dw      0xffff
0058ee:  ffff  dw      0xffff
0058f0:  ffff  dw      0xffff
0058f2:  ffff  dw      0xffff
0058f4:  ffff  dw      0xffff
0058f6:  ffff  dw      0xffff
0058f8:  ffff  dw      0xffff
0058fa:  ffff  dw      0xffff
0058fc:  ffff  dw      0xffff
0058fe:  ffff  dw      0xffff
005900:  ffff  dw      0xffff
005902:  ffff  dw      0xffff
005904:  ffff  dw      0xffff
005906:  ffff  dw      0xffff
005908:  ffff  dw      0xffff
00590a:  ffff  dw      0xffff
00590c:  ffff  dw      0xffff
00590e:  ffff  dw      0xffff
005910:  ffff  dw      0xffff
005912:  ffff  dw      0xffff
005914:  ffff  dw      0xffff
005916:  ffff  dw      0xffff
005918:  ffff  dw      0xffff
00591a:  ffff  dw      0xffff
00591c:  ffff  dw      0xffff
00591e:  ffff  dw      0xffff
005920:  ffff  dw      0xffff
005922:  ffff  dw      0xffff
005924:  ffff  dw      0xffff
005926:  ffff  dw      0xffff
005928:  ffff  dw      0xffff
00592a:  ffff  dw      0xffff
00592c:  ffff  dw      0xffff
00592e:  ffff  dw      0xffff
005930:  ffff  dw      0xffff
005932:  ffff  dw      0xffff
005934:  ffff  dw      0xffff
005936:  ffff  dw      0xffff
005938:  ffff  dw      0xffff
00593a:  ffff  dw      0xffff
00593c:  ffff  dw      0xffff
00593e:  ffff  dw      0xffff
005940:  ffff  dw      0xffff
005942:  ffff  dw      0xffff
005944:  ffff  dw      0xffff
005946:  ffff  dw      0xffff
005948:  ffff  dw      0xffff
00594a:  ffff  dw      0xffff
00594c:  ffff  dw      0xffff
00594e:  ffff  dw      0xffff
005950:  ffff  dw      0xffff
005952:  ffff  dw      0xffff
005954:  ffff  dw      0xffff
005956:  ffff  dw      0xffff
005958:  ffff  dw      0xffff
00595a:  ffff  dw      0xffff
00595c:  ffff  dw      0xffff
00595e:  ffff  dw      0xffff
005960:  ffff  dw      0xffff
005962:  ffff  dw      0xffff
005964:  ffff  dw      0xffff
005966:  ffff  dw      0xffff
005968:  ffff  dw      0xffff
00596a:  ffff  dw      0xffff
00596c:  ffff  dw      0xffff
00596e:  ffff  dw      0xffff
005970:  ffff  dw      0xffff
005972:  ffff  dw      0xffff
005974:  ffff  dw      0xffff
005976:  ffff  dw      0xffff
005978:  ffff  dw      0xffff
00597a:  ffff  dw      0xffff
00597c:  ffff  dw      0xffff
00597e:  ffff  dw      0xffff
005980:  ffff  dw      0xffff
005982:  ffff  dw      0xffff
005984:  ffff  dw      0xffff
005986:  ffff  dw      0xffff
005988:  ffff  dw      0xffff
00598a:  ffff  dw      0xffff
00598c:  ffff  dw      0xffff
00598e:  ffff  dw      0xffff
005990:  ffff  dw      0xffff
005992:  ffff  dw      0xffff
005994:  ffff  dw      0xffff
005996:  ffff  dw      0xffff
005998:  ffff  dw      0xffff
00599a:  ffff  dw      0xffff
00599c:  ffff  dw      0xffff
00599e:  ffff  dw      0xffff
0059a0:  ffff  dw      0xffff
0059a2:  ffff  dw      0xffff
0059a4:  ffff  dw      0xffff
0059a6:  ffff  dw      0xffff
0059a8:  ffff  dw      0xffff
0059aa:  ffff  dw      0xffff
0059ac:  ffff  dw      0xffff
0059ae:  ffff  dw      0xffff
0059b0:  ffff  dw      0xffff
0059b2:  ffff  dw      0xffff
0059b4:  ffff  dw      0xffff
0059b6:  ffff  dw      0xffff
0059b8:  ffff  dw      0xffff
0059ba:  ffff  dw      0xffff
0059bc:  ffff  dw      0xffff
0059be:  ffff  dw      0xffff
0059c0:  ffff  dw      0xffff
0059c2:  ffff  dw      0xffff
0059c4:  ffff  dw      0xffff
0059c6:  ffff  dw      0xffff
0059c8:  ffff  dw      0xffff
0059ca:  ffff  dw      0xffff
0059cc:  ffff  dw      0xffff
0059ce:  ffff  dw      0xffff
0059d0:  ffff  dw      0xffff
0059d2:  ffff  dw      0xffff
0059d4:  ffff  dw      0xffff
0059d6:  ffff  dw      0xffff
0059d8:  ffff  dw      0xffff
0059da:  ffff  dw      0xffff
0059dc:  ffff  dw      0xffff
0059de:  ffff  dw      0xffff
0059e0:  ffff  dw      0xffff
0059e2:  ffff  dw      0xffff
0059e4:  ffff  dw      0xffff
0059e6:  ffff  dw      0xffff
0059e8:  ffff  dw      0xffff
0059ea:  ffff  dw      0xffff
0059ec:  ffff  dw      0xffff
0059ee:  ffff  dw      0xffff
0059f0:  ffff  dw      0xffff
0059f2:  ffff  dw      0xffff
0059f4:  ffff  dw      0xffff
0059f6:  ffff  dw      0xffff
0059f8:  ffff  dw      0xffff
0059fa:  ffff  dw      0xffff
0059fc:  ffff  dw      0xffff
0059fe:  ffff  dw      0xffff
005a00:  ffff  dw      0xffff
005a02:  ffff  dw      0xffff
005a04:  ffff  dw      0xffff
005a06:  ffff  dw      0xffff
005a08:  ffff  dw      0xffff
005a0a:  ffff  dw      0xffff
005a0c:  ffff  dw      0xffff
005a0e:  ffff  dw      0xffff
005a10:  ffff  dw      0xffff
005a12:  ffff  dw      0xffff
005a14:  ffff  dw      0xffff
005a16:  ffff  dw      0xffff
005a18:  ffff  dw      0xffff
005a1a:  ffff  dw      0xffff
005a1c:  ffff  dw      0xffff
005a1e:  ffff  dw      0xffff
005a20:  ffff  dw      0xffff
005a22:  ffff  dw      0xffff
005a24:  ffff  dw      0xffff
005a26:  ffff  dw      0xffff
005a28:  ffff  dw      0xffff
005a2a:  ffff  dw      0xffff
005a2c:  ffff  dw      0xffff
005a2e:  ffff  dw      0xffff
005a30:  ffff  dw      0xffff
005a32:  ffff  dw      0xffff
005a34:  ffff  dw      0xffff
005a36:  ffff  dw      0xffff
005a38:  ffff  dw      0xffff
005a3a:  ffff  dw      0xffff
005a3c:  ffff  dw      0xffff
005a3e:  ffff  dw      0xffff
005a40:  ffff  dw      0xffff
005a42:  ffff  dw      0xffff
005a44:  ffff  dw      0xffff
005a46:  ffff  dw      0xffff
005a48:  ffff  dw      0xffff
005a4a:  ffff  dw      0xffff
005a4c:  ffff  dw      0xffff
005a4e:  ffff  dw      0xffff
005a50:  ffff  dw      0xffff
005a52:  ffff  dw      0xffff
005a54:  ffff  dw      0xffff
005a56:  ffff  dw      0xffff
005a58:  ffff  dw      0xffff
005a5a:  ffff  dw      0xffff
005a5c:  ffff  dw      0xffff
005a5e:  ffff  dw      0xffff
005a60:  ffff  dw      0xffff
005a62:  ffff  dw      0xffff
005a64:  ffff  dw      0xffff
005a66:  ffff  dw      0xffff
005a68:  ffff  dw      0xffff
005a6a:  ffff  dw      0xffff
005a6c:  ffff  dw      0xffff
005a6e:  ffff  dw      0xffff
005a70:  ffff  dw      0xffff
005a72:  ffff  dw      0xffff
005a74:  ffff  dw      0xffff
005a76:  ffff  dw      0xffff
005a78:  ffff  dw      0xffff
005a7a:  ffff  dw      0xffff
005a7c:  ffff  dw      0xffff
005a7e:  ffff  dw      0xffff
005a80:  ffff  dw      0xffff
005a82:  ffff  dw      0xffff
005a84:  ffff  dw      0xffff
005a86:  ffff  dw      0xffff
005a88:  ffff  dw      0xffff
005a8a:  ffff  dw      0xffff
005a8c:  ffff  dw      0xffff
005a8e:  ffff  dw      0xffff
005a90:  ffff  dw      0xffff
005a92:  ffff  dw      0xffff
005a94:  ffff  dw      0xffff
005a96:  ffff  dw      0xffff
005a98:  ffff  dw      0xffff
005a9a:  ffff  dw      0xffff
005a9c:  ffff  dw      0xffff
005a9e:  ffff  dw      0xffff
005aa0:  ffff  dw      0xffff
005aa2:  ffff  dw      0xffff
005aa4:  ffff  dw      0xffff
005aa6:  ffff  dw      0xffff
005aa8:  ffff  dw      0xffff
005aaa:  ffff  dw      0xffff
005aac:  ffff  dw      0xffff
005aae:  ffff  dw      0xffff
005ab0:  ffff  dw      0xffff
005ab2:  ffff  dw      0xffff
005ab4:  ffff  dw      0xffff
005ab6:  ffff  dw      0xffff
005ab8:  ffff  dw      0xffff
005aba:  ffff  dw      0xffff
005abc:  ffff  dw      0xffff
005abe:  ffff  dw      0xffff
005ac0:  ffff  dw      0xffff
005ac2:  ffff  dw      0xffff
005ac4:  ffff  dw      0xffff
005ac6:  ffff  dw      0xffff
005ac8:  ffff  dw      0xffff
005aca:  ffff  dw      0xffff
005acc:  ffff  dw      0xffff
005ace:  ffff  dw      0xffff
005ad0:  ffff  dw      0xffff
005ad2:  ffff  dw      0xffff
005ad4:  ffff  dw      0xffff
005ad6:  ffff  dw      0xffff
005ad8:  ffff  dw      0xffff
005ada:  ffff  dw      0xffff
005adc:  ffff  dw      0xffff
005ade:  ffff  dw      0xffff
005ae0:  ffff  dw      0xffff
005ae2:  ffff  dw      0xffff
005ae4:  ffff  dw      0xffff
005ae6:  ffff  dw      0xffff
005ae8:  ffff  dw      0xffff
005aea:  ffff  dw      0xffff
005aec:  ffff  dw      0xffff
005aee:  ffff  dw      0xffff
005af0:  ffff  dw      0xffff
005af2:  ffff  dw      0xffff
005af4:  ffff  dw      0xffff
005af6:  ffff  dw      0xffff
005af8:  ffff  dw      0xffff
005afa:  ffff  dw      0xffff
005afc:  ffff  dw      0xffff
005afe:  ffff  dw      0xffff
005b00:  ffff  dw      0xffff
005b02:  ffff  dw      0xffff
005b04:  ffff  dw      0xffff
005b06:  ffff  dw      0xffff
005b08:  ffff  dw      0xffff
005b0a:  ffff  dw      0xffff
005b0c:  ffff  dw      0xffff
005b0e:  ffff  dw      0xffff
005b10:  ffff  dw      0xffff
005b12:  ffff  dw      0xffff
005b14:  ffff  dw      0xffff
005b16:  ffff  dw      0xffff
005b18:  ffff  dw      0xffff
005b1a:  ffff  dw      0xffff
005b1c:  ffff  dw      0xffff
005b1e:  ffff  dw      0xffff
005b20:  ffff  dw      0xffff
005b22:  ffff  dw      0xffff
005b24:  ffff  dw      0xffff
005b26:  ffff  dw      0xffff
005b28:  ffff  dw      0xffff
005b2a:  ffff  dw      0xffff
005b2c:  ffff  dw      0xffff
005b2e:  ffff  dw      0xffff
005b30:  ffff  dw      0xffff
005b32:  ffff  dw      0xffff
005b34:  ffff  dw      0xffff
005b36:  ffff  dw      0xffff
005b38:  ffff  dw      0xffff
005b3a:  ffff  dw      0xffff
005b3c:  ffff  dw      0xffff
005b3e:  ffff  dw      0xffff
005b40:  ffff  dw      0xffff
005b42:  ffff  dw      0xffff
005b44:  ffff  dw      0xffff
005b46:  ffff  dw      0xffff
005b48:  ffff  dw      0xffff
005b4a:  ffff  dw      0xffff
005b4c:  ffff  dw      0xffff
005b4e:  ffff  dw      0xffff
005b50:  ffff  dw      0xffff
005b52:  ffff  dw      0xffff
005b54:  ffff  dw      0xffff
005b56:  ffff  dw      0xffff
005b58:  ffff  dw      0xffff
005b5a:  ffff  dw      0xffff
005b5c:  ffff  dw      0xffff
005b5e:  ffff  dw      0xffff
005b60:  ffff  dw      0xffff
005b62:  ffff  dw      0xffff
005b64:  ffff  dw      0xffff
005b66:  ffff  dw      0xffff
005b68:  ffff  dw      0xffff
005b6a:  ffff  dw      0xffff
005b6c:  ffff  dw      0xffff
005b6e:  ffff  dw      0xffff
005b70:  ffff  dw      0xffff
005b72:  ffff  dw      0xffff
005b74:  ffff  dw      0xffff
005b76:  ffff  dw      0xffff
005b78:  ffff  dw      0xffff
005b7a:  ffff  dw      0xffff
005b7c:  ffff  dw      0xffff
005b7e:  ffff  dw      0xffff
005b80:  ffff  dw      0xffff
005b82:  ffff  dw      0xffff
005b84:  ffff  dw      0xffff
005b86:  ffff  dw      0xffff
005b88:  ffff  dw      0xffff
005b8a:  ffff  dw      0xffff
005b8c:  ffff  dw      0xffff
005b8e:  ffff  dw      0xffff
005b90:  ffff  dw      0xffff
005b92:  ffff  dw      0xffff
005b94:  ffff  dw      0xffff
005b96:  ffff  dw      0xffff
005b98:  ffff  dw      0xffff
005b9a:  ffff  dw      0xffff
005b9c:  ffff  dw      0xffff
005b9e:  ffff  dw      0xffff
005ba0:  ffff  dw      0xffff
005ba2:  ffff  dw      0xffff
005ba4:  ffff  dw      0xffff
005ba6:  ffff  dw      0xffff
005ba8:  ffff  dw      0xffff
005baa:  ffff  dw      0xffff
005bac:  ffff  dw      0xffff
005bae:  ffff  dw      0xffff
005bb0:  ffff  dw      0xffff
005bb2:  ffff  dw      0xffff
005bb4:  ffff  dw      0xffff
005bb6:  ffff  dw      0xffff
005bb8:  ffff  dw      0xffff
005bba:  ffff  dw      0xffff
005bbc:  ffff  dw      0xffff
005bbe:  ffff  dw      0xffff
005bc0:  ffff  dw      0xffff
005bc2:  ffff  dw      0xffff
005bc4:  ffff  dw      0xffff
005bc6:  ffff  dw      0xffff
005bc8:  ffff  dw      0xffff
005bca:  ffff  dw      0xffff
005bcc:  ffff  dw      0xffff
005bce:  ffff  dw      0xffff
005bd0:  ffff  dw      0xffff
005bd2:  ffff  dw      0xffff
005bd4:  ffff  dw      0xffff
005bd6:  ffff  dw      0xffff
005bd8:  ffff  dw      0xffff
005bda:  ffff  dw      0xffff
005bdc:  ffff  dw      0xffff
005bde:  ffff  dw      0xffff
005be0:  ffff  dw      0xffff
005be2:  ffff  dw      0xffff
005be4:  ffff  dw      0xffff
005be6:  ffff  dw      0xffff
005be8:  ffff  dw      0xffff
005bea:  ffff  dw      0xffff
005bec:  ffff  dw      0xffff
005bee:  ffff  dw      0xffff
005bf0:  ffff  dw      0xffff
005bf2:  ffff  dw      0xffff
005bf4:  ffff  dw      0xffff
005bf6:  ffff  dw      0xffff
005bf8:  ffff  dw      0xffff
005bfa:  ffff  dw      0xffff
005bfc:  ffff  dw      0xffff
005bfe:  ffff  dw      0xffff
005c00:  ffff  dw      0xffff
005c02:  ffff  dw      0xffff
005c04:  ffff  dw      0xffff
005c06:  ffff  dw      0xffff
005c08:  ffff  dw      0xffff
005c0a:  ffff  dw      0xffff
005c0c:  ffff  dw      0xffff
005c0e:  ffff  dw      0xffff
005c10:  ffff  dw      0xffff
005c12:  ffff  dw      0xffff
005c14:  ffff  dw      0xffff
005c16:  ffff  dw      0xffff
005c18:  ffff  dw      0xffff
005c1a:  ffff  dw      0xffff
005c1c:  ffff  dw      0xffff
005c1e:  ffff  dw      0xffff
005c20:  ffff  dw      0xffff
005c22:  ffff  dw      0xffff
005c24:  ffff  dw      0xffff
005c26:  ffff  dw      0xffff
005c28:  ffff  dw      0xffff
005c2a:  ffff  dw      0xffff
005c2c:  ffff  dw      0xffff
005c2e:  ffff  dw      0xffff
005c30:  ffff  dw      0xffff
005c32:  ffff  dw      0xffff
005c34:  ffff  dw      0xffff
005c36:  ffff  dw      0xffff
005c38:  ffff  dw      0xffff
005c3a:  ffff  dw      0xffff
005c3c:  ffff  dw      0xffff
005c3e:  ffff  dw      0xffff
005c40:  ffff  dw      0xffff
005c42:  ffff  dw      0xffff
005c44:  ffff  dw      0xffff
005c46:  ffff  dw      0xffff
005c48:  ffff  dw      0xffff
005c4a:  ffff  dw      0xffff
005c4c:  ffff  dw      0xffff
005c4e:  ffff  dw      0xffff
005c50:  ffff  dw      0xffff
005c52:  ffff  dw      0xffff
005c54:  ffff  dw      0xffff
005c56:  ffff  dw      0xffff
005c58:  ffff  dw      0xffff
005c5a:  ffff  dw      0xffff
005c5c:  ffff  dw      0xffff
005c5e:  ffff  dw      0xffff
005c60:  ffff  dw      0xffff
005c62:  ffff  dw      0xffff
005c64:  ffff  dw      0xffff
005c66:  ffff  dw      0xffff
005c68:  ffff  dw      0xffff
005c6a:  ffff  dw      0xffff
005c6c:  ffff  dw      0xffff
005c6e:  ffff  dw      0xffff
005c70:  ffff  dw      0xffff
005c72:  ffff  dw      0xffff
005c74:  ffff  dw      0xffff
005c76:  ffff  dw      0xffff
005c78:  ffff  dw      0xffff
005c7a:  ffff  dw      0xffff
005c7c:  ffff  dw      0xffff
005c7e:  ffff  dw      0xffff
005c80:  ffff  dw      0xffff
005c82:  ffff  dw      0xffff
005c84:  ffff  dw      0xffff
005c86:  ffff  dw      0xffff
005c88:  ffff  dw      0xffff
005c8a:  ffff  dw      0xffff
005c8c:  ffff  dw      0xffff
005c8e:  ffff  dw      0xffff
005c90:  ffff  dw      0xffff
005c92:  ffff  dw      0xffff
005c94:  ffff  dw      0xffff
005c96:  ffff  dw      0xffff
005c98:  ffff  dw      0xffff
005c9a:  ffff  dw      0xffff
005c9c:  ffff  dw      0xffff
005c9e:  ffff  dw      0xffff
005ca0:  ffff  dw      0xffff
005ca2:  ffff  dw      0xffff
005ca4:  ffff  dw      0xffff
005ca6:  ffff  dw      0xffff
005ca8:  ffff  dw      0xffff
005caa:  ffff  dw      0xffff
005cac:  ffff  dw      0xffff
005cae:  ffff  dw      0xffff
005cb0:  ffff  dw      0xffff
005cb2:  ffff  dw      0xffff
005cb4:  ffff  dw      0xffff
005cb6:  ffff  dw      0xffff
005cb8:  ffff  dw      0xffff
005cba:  ffff  dw      0xffff
005cbc:  ffff  dw      0xffff
005cbe:  ffff  dw      0xffff
005cc0:  ffff  dw      0xffff
005cc2:  ffff  dw      0xffff
005cc4:  ffff  dw      0xffff
005cc6:  ffff  dw      0xffff
005cc8:  ffff  dw      0xffff
005cca:  ffff  dw      0xffff
005ccc:  ffff  dw      0xffff
005cce:  ffff  dw      0xffff
005cd0:  ffff  dw      0xffff
005cd2:  ffff  dw      0xffff
005cd4:  ffff  dw      0xffff
005cd6:  ffff  dw      0xffff
005cd8:  ffff  dw      0xffff
005cda:  ffff  dw      0xffff
005cdc:  ffff  dw      0xffff
005cde:  ffff  dw      0xffff
005ce0:  ffff  dw      0xffff
005ce2:  ffff  dw      0xffff
005ce4:  ffff  dw      0xffff
005ce6:  ffff  dw      0xffff
005ce8:  ffff  dw      0xffff
005cea:  ffff  dw      0xffff
005cec:  ffff  dw      0xffff
005cee:  ffff  dw      0xffff
005cf0:  ffff  dw      0xffff
005cf2:  ffff  dw      0xffff
005cf4:  ffff  dw      0xffff
005cf6:  ffff  dw      0xffff
005cf8:  ffff  dw      0xffff
005cfa:  ffff  dw      0xffff
005cfc:  ffff  dw      0xffff
005cfe:  ffff  dw      0xffff
005d00:  ffff  dw      0xffff
005d02:  ffff  dw      0xffff
005d04:  ffff  dw      0xffff
005d06:  ffff  dw      0xffff
005d08:  ffff  dw      0xffff
005d0a:  ffff  dw      0xffff
005d0c:  ffff  dw      0xffff
005d0e:  ffff  dw      0xffff
005d10:  ffff  dw      0xffff
005d12:  ffff  dw      0xffff
005d14:  ffff  dw      0xffff
005d16:  ffff  dw      0xffff
005d18:  ffff  dw      0xffff
005d1a:  ffff  dw      0xffff
005d1c:  ffff  dw      0xffff
005d1e:  ffff  dw      0xffff
005d20:  ffff  dw      0xffff
005d22:  ffff  dw      0xffff
005d24:  ffff  dw      0xffff
005d26:  ffff  dw      0xffff
005d28:  ffff  dw      0xffff
005d2a:  ffff  dw      0xffff
005d2c:  ffff  dw      0xffff
005d2e:  ffff  dw      0xffff
005d30:  ffff  dw      0xffff
005d32:  ffff  dw      0xffff
005d34:  ffff  dw      0xffff
005d36:  ffff  dw      0xffff
005d38:  ffff  dw      0xffff
005d3a:  ffff  dw      0xffff
005d3c:  ffff  dw      0xffff
005d3e:  ffff  dw      0xffff
005d40:  ffff  dw      0xffff
005d42:  ffff  dw      0xffff
005d44:  ffff  dw      0xffff
005d46:  ffff  dw      0xffff
005d48:  ffff  dw      0xffff
005d4a:  ffff  dw      0xffff
005d4c:  ffff  dw      0xffff
005d4e:  ffff  dw      0xffff
005d50:  ffff  dw      0xffff
005d52:  ffff  dw      0xffff
005d54:  ffff  dw      0xffff
005d56:  ffff  dw      0xffff
005d58:  ffff  dw      0xffff
005d5a:  ffff  dw      0xffff
005d5c:  ffff  dw      0xffff
005d5e:  ffff  dw      0xffff
005d60:  ffff  dw      0xffff
005d62:  ffff  dw      0xffff
005d64:  ffff  dw      0xffff
005d66:  ffff  dw      0xffff
005d68:  ffff  dw      0xffff
005d6a:  ffff  dw      0xffff
005d6c:  ffff  dw      0xffff
005d6e:  ffff  dw      0xffff
005d70:  ffff  dw      0xffff
005d72:  ffff  dw      0xffff
005d74:  ffff  dw      0xffff
005d76:  ffff  dw      0xffff
005d78:  ffff  dw      0xffff
005d7a:  ffff  dw      0xffff
005d7c:  ffff  dw      0xffff
005d7e:  ffff  dw      0xffff
005d80:  ffff  dw      0xffff
005d82:  ffff  dw      0xffff
005d84:  ffff  dw      0xffff
005d86:  ffff  dw      0xffff
005d88:  ffff  dw      0xffff
005d8a:  ffff  dw      0xffff
005d8c:  ffff  dw      0xffff
005d8e:  ffff  dw      0xffff
005d90:  ffff  dw      0xffff
005d92:  ffff  dw      0xffff
005d94:  ffff  dw      0xffff
005d96:  ffff  dw      0xffff
005d98:  ffff  dw      0xffff
005d9a:  ffff  dw      0xffff
005d9c:  ffff  dw      0xffff
005d9e:  ffff  dw      0xffff
005da0:  ffff  dw      0xffff
005da2:  ffff  dw      0xffff
005da4:  ffff  dw      0xffff
005da6:  ffff  dw      0xffff
005da8:  ffff  dw      0xffff
005daa:  ffff  dw      0xffff
005dac:  ffff  dw      0xffff
005dae:  ffff  dw      0xffff
005db0:  ffff  dw      0xffff
005db2:  ffff  dw      0xffff
005db4:  ffff  dw      0xffff
005db6:  ffff  dw      0xffff
005db8:  ffff  dw      0xffff
005dba:  ffff  dw      0xffff
005dbc:  ffff  dw      0xffff
005dbe:  ffff  dw      0xffff
005dc0:  ffff  dw      0xffff
005dc2:  ffff  dw      0xffff
005dc4:  ffff  dw      0xffff
005dc6:  ffff  dw      0xffff
005dc8:  ffff  dw      0xffff
005dca:  ffff  dw      0xffff
005dcc:  ffff  dw      0xffff
005dce:  ffff  dw      0xffff
005dd0:  ffff  dw      0xffff
005dd2:  ffff  dw      0xffff
005dd4:  ffff  dw      0xffff
005dd6:  ffff  dw      0xffff
005dd8:  ffff  dw      0xffff
005dda:  ffff  dw      0xffff
005ddc:  ffff  dw      0xffff
005dde:  ffff  dw      0xffff
005de0:  ffff  dw      0xffff
005de2:  ffff  dw      0xffff
005de4:  ffff  dw      0xffff
005de6:  ffff  dw      0xffff
005de8:  ffff  dw      0xffff
005dea:  ffff  dw      0xffff
005dec:  ffff  dw      0xffff
005dee:  ffff  dw      0xffff
005df0:  ffff  dw      0xffff
005df2:  ffff  dw      0xffff
005df4:  ffff  dw      0xffff
005df6:  ffff  dw      0xffff
005df8:  ffff  dw      0xffff
005dfa:  ffff  dw      0xffff
005dfc:  ffff  dw      0xffff
005dfe:  ffff  dw      0xffff
005e00:  ffff  dw      0xffff
005e02:  ffff  dw      0xffff
005e04:  ffff  dw      0xffff
005e06:  ffff  dw      0xffff
005e08:  ffff  dw      0xffff
005e0a:  ffff  dw      0xffff
005e0c:  ffff  dw      0xffff
005e0e:  ffff  dw      0xffff
005e10:  ffff  dw      0xffff
005e12:  ffff  dw      0xffff
005e14:  ffff  dw      0xffff
005e16:  ffff  dw      0xffff
005e18:  ffff  dw      0xffff
005e1a:  ffff  dw      0xffff
005e1c:  ffff  dw      0xffff
005e1e:  ffff  dw      0xffff
005e20:  ffff  dw      0xffff
005e22:  ffff  dw      0xffff
005e24:  ffff  dw      0xffff
005e26:  ffff  dw      0xffff
005e28:  ffff  dw      0xffff
005e2a:  ffff  dw      0xffff
005e2c:  ffff  dw      0xffff
005e2e:  ffff  dw      0xffff
005e30:  ffff  dw      0xffff
005e32:  ffff  dw      0xffff
005e34:  ffff  dw      0xffff
005e36:  ffff  dw      0xffff
005e38:  ffff  dw      0xffff
005e3a:  ffff  dw      0xffff
005e3c:  ffff  dw      0xffff
005e3e:  ffff  dw      0xffff
005e40:  ffff  dw      0xffff
005e42:  ffff  dw      0xffff
005e44:  ffff  dw      0xffff
005e46:  ffff  dw      0xffff
005e48:  ffff  dw      0xffff
005e4a:  ffff  dw      0xffff
005e4c:  ffff  dw      0xffff
005e4e:  ffff  dw      0xffff
005e50:  ffff  dw      0xffff
005e52:  ffff  dw      0xffff
005e54:  ffff  dw      0xffff
005e56:  ffff  dw      0xffff
005e58:  ffff  dw      0xffff
005e5a:  ffff  dw      0xffff
005e5c:  ffff  dw      0xffff
005e5e:  ffff  dw      0xffff
005e60:  ffff  dw      0xffff
005e62:  ffff  dw      0xffff
005e64:  ffff  dw      0xffff
005e66:  ffff  dw      0xffff
005e68:  ffff  dw      0xffff
005e6a:  ffff  dw      0xffff
005e6c:  ffff  dw      0xffff
005e6e:  ffff  dw      0xffff
005e70:  ffff  dw      0xffff
005e72:  ffff  dw      0xffff
005e74:  ffff  dw      0xffff
005e76:  ffff  dw      0xffff
005e78:  ffff  dw      0xffff
005e7a:  ffff  dw      0xffff
005e7c:  ffff  dw      0xffff
005e7e:  ffff  dw      0xffff
005e80:  ffff  dw      0xffff
005e82:  ffff  dw      0xffff
005e84:  ffff  dw      0xffff
005e86:  ffff  dw      0xffff
005e88:  ffff  dw      0xffff
005e8a:  ffff  dw      0xffff
005e8c:  ffff  dw      0xffff
005e8e:  ffff  dw      0xffff
005e90:  ffff  dw      0xffff
005e92:  ffff  dw      0xffff
005e94:  ffff  dw      0xffff
005e96:  ffff  dw      0xffff
005e98:  ffff  dw      0xffff
005e9a:  ffff  dw      0xffff
005e9c:  ffff  dw      0xffff
005e9e:  ffff  dw      0xffff
005ea0:  ffff  dw      0xffff
005ea2:  ffff  dw      0xffff
005ea4:  ffff  dw      0xffff
005ea6:  ffff  dw      0xffff
005ea8:  ffff  dw      0xffff
005eaa:  ffff  dw      0xffff
005eac:  ffff  dw      0xffff
005eae:  ffff  dw      0xffff
005eb0:  ffff  dw      0xffff
005eb2:  ffff  dw      0xffff
005eb4:  ffff  dw      0xffff
005eb6:  ffff  dw      0xffff
005eb8:  ffff  dw      0xffff
005eba:  ffff  dw      0xffff
005ebc:  ffff  dw      0xffff
005ebe:  ffff  dw      0xffff
005ec0:  ffff  dw      0xffff
005ec2:  ffff  dw      0xffff
005ec4:  ffff  dw      0xffff
005ec6:  ffff  dw      0xffff
005ec8:  ffff  dw      0xffff
005eca:  ffff  dw      0xffff
005ecc:  ffff  dw      0xffff
005ece:  ffff  dw      0xffff
005ed0:  ffff  dw      0xffff
005ed2:  ffff  dw      0xffff
005ed4:  ffff  dw      0xffff
005ed6:  ffff  dw      0xffff
005ed8:  ffff  dw      0xffff
005eda:  ffff  dw      0xffff
005edc:  ffff  dw      0xffff
005ede:  ffff  dw      0xffff
005ee0:  ffff  dw      0xffff
005ee2:  ffff  dw      0xffff
005ee4:  ffff  dw      0xffff
005ee6:  ffff  dw      0xffff
005ee8:  ffff  dw      0xffff
005eea:  ffff  dw      0xffff
005eec:  ffff  dw      0xffff
005eee:  ffff  dw      0xffff
005ef0:  ffff  dw      0xffff
005ef2:  ffff  dw      0xffff
005ef4:  ffff  dw      0xffff
005ef6:  ffff  dw      0xffff
005ef8:  ffff  dw      0xffff
005efa:  ffff  dw      0xffff
005efc:  ffff  dw      0xffff
005efe:  ffff  dw      0xffff
005f00:  ffff  dw      0xffff
005f02:  ffff  dw      0xffff
005f04:  ffff  dw      0xffff
005f06:  ffff  dw      0xffff
005f08:  ffff  dw      0xffff
005f0a:  ffff  dw      0xffff
005f0c:  ffff  dw      0xffff
005f0e:  ffff  dw      0xffff
005f10:  ffff  dw      0xffff
005f12:  ffff  dw      0xffff
005f14:  ffff  dw      0xffff
005f16:  ffff  dw      0xffff
005f18:  ffff  dw      0xffff
005f1a:  ffff  dw      0xffff
005f1c:  ffff  dw      0xffff
005f1e:  ffff  dw      0xffff
005f20:  ffff  dw      0xffff
005f22:  ffff  dw      0xffff
005f24:  ffff  dw      0xffff
005f26:  ffff  dw      0xffff
005f28:  ffff  dw      0xffff
005f2a:  ffff  dw      0xffff
005f2c:  ffff  dw      0xffff
005f2e:  ffff  dw      0xffff
005f30:  ffff  dw      0xffff
005f32:  ffff  dw      0xffff
005f34:  ffff  dw      0xffff
005f36:  ffff  dw      0xffff
005f38:  ffff  dw      0xffff
005f3a:  ffff  dw      0xffff
005f3c:  ffff  dw      0xffff
005f3e:  ffff  dw      0xffff
005f40:  ffff  dw      0xffff
005f42:  ffff  dw      0xffff
005f44:  ffff  dw      0xffff
005f46:  ffff  dw      0xffff
005f48:  ffff  dw      0xffff
005f4a:  ffff  dw      0xffff
005f4c:  ffff  dw      0xffff
005f4e:  ffff  dw      0xffff
005f50:  ffff  dw      0xffff
005f52:  ffff  dw      0xffff
005f54:  ffff  dw      0xffff
005f56:  ffff  dw      0xffff
005f58:  ffff  dw      0xffff
005f5a:  ffff  dw      0xffff
005f5c:  ffff  dw      0xffff
005f5e:  ffff  dw      0xffff
005f60:  ffff  dw      0xffff
005f62:  ffff  dw      0xffff
005f64:  ffff  dw      0xffff
005f66:  ffff  dw      0xffff
005f68:  ffff  dw      0xffff
005f6a:  ffff  dw      0xffff
005f6c:  ffff  dw      0xffff
005f6e:  ffff  dw      0xffff
005f70:  ffff  dw      0xffff
005f72:  ffff  dw      0xffff
005f74:  ffff  dw      0xffff
005f76:  ffff  dw      0xffff
005f78:  ffff  dw      0xffff
005f7a:  ffff  dw      0xffff
005f7c:  ffff  dw      0xffff
005f7e:  ffff  dw      0xffff
005f80:  ffff  dw      0xffff
005f82:  ffff  dw      0xffff
005f84:  ffff  dw      0xffff
005f86:  ffff  dw      0xffff
005f88:  ffff  dw      0xffff
005f8a:  ffff  dw      0xffff
005f8c:  ffff  dw      0xffff
005f8e:  ffff  dw      0xffff
005f90:  ffff  dw      0xffff
005f92:  ffff  dw      0xffff
005f94:  ffff  dw      0xffff
005f96:  ffff  dw      0xffff
005f98:  ffff  dw      0xffff
005f9a:  ffff  dw      0xffff
005f9c:  ffff  dw      0xffff
005f9e:  ffff  dw      0xffff
005fa0:  ffff  dw      0xffff
005fa2:  ffff  dw      0xffff
005fa4:  ffff  dw      0xffff
005fa6:  ffff  dw      0xffff
005fa8:  ffff  dw      0xffff
005faa:  ffff  dw      0xffff
005fac:  ffff  dw      0xffff
005fae:  ffff  dw      0xffff
005fb0:  ffff  dw      0xffff
005fb2:  ffff  dw      0xffff
005fb4:  ffff  dw      0xffff
005fb6:  ffff  dw      0xffff
005fb8:  ffff  dw      0xffff
005fba:  ffff  dw      0xffff
005fbc:  ffff  dw      0xffff
005fbe:  ffff  dw      0xffff
005fc0:  ffff  dw      0xffff
005fc2:  ffff  dw      0xffff
005fc4:  ffff  dw      0xffff
005fc6:  ffff  dw      0xffff
005fc8:  ffff  dw      0xffff
005fca:  ffff  dw      0xffff
005fcc:  ffff  dw      0xffff
005fce:  ffff  dw      0xffff
005fd0:  ffff  dw      0xffff
005fd2:  ffff  dw      0xffff
005fd4:  ffff  dw      0xffff
005fd6:  ffff  dw      0xffff
005fd8:  ffff  dw      0xffff
005fda:  ffff  dw      0xffff
005fdc:  ffff  dw      0xffff
005fde:  ffff  dw      0xffff
005fe0:  ffff  dw      0xffff
005fe2:  ffff  dw      0xffff
005fe4:  ffff  dw      0xffff
005fe6:  ffff  dw      0xffff
005fe8:  ffff  dw      0xffff
005fea:  ffff  dw      0xffff
005fec:  ffff  dw      0xffff
005fee:  ffff  dw      0xffff
005ff0:  ffff  dw      0xffff
005ff2:  ffff  dw      0xffff
005ff4:  ffff  dw      0xffff
005ff6:  ffff  dw      0xffff
005ff8:  ffff  dw      0xffff
005ffa:  ffff  dw      0xffff
005ffc:  ffff  dw      0xffff
005ffe:  ffff  dw      0xffff
006000:  ffff  dw      0xffff
006002:  ffff  dw      0xffff
006004:  ffff  dw      0xffff
006006:  ffff  dw      0xffff
006008:  ffff  dw      0xffff
00600a:  ffff  dw      0xffff
00600c:  ffff  dw      0xffff
00600e:  ffff  dw      0xffff
006010:  ffff  dw      0xffff
006012:  ffff  dw      0xffff
006014:  ffff  dw      0xffff
006016:  ffff  dw      0xffff
006018:  ffff  dw      0xffff
00601a:  ffff  dw      0xffff
00601c:  ffff  dw      0xffff
00601e:  ffff  dw      0xffff
006020:  ffff  dw      0xffff
006022:  ffff  dw      0xffff
006024:  ffff  dw      0xffff
006026:  ffff  dw      0xffff
006028:  ffff  dw      0xffff
00602a:  ffff  dw      0xffff
00602c:  ffff  dw      0xffff
00602e:  ffff  dw      0xffff
006030:  ffff  dw      0xffff
006032:  ffff  dw      0xffff
006034:  ffff  dw      0xffff
006036:  ffff  dw      0xffff
006038:  ffff  dw      0xffff
00603a:  ffff  dw      0xffff
00603c:  ffff  dw      0xffff
00603e:  ffff  dw      0xffff
006040:  ffff  dw      0xffff
006042:  ffff  dw      0xffff
006044:  ffff  dw      0xffff
006046:  ffff  dw      0xffff
006048:  ffff  dw      0xffff
00604a:  ffff  dw      0xffff
00604c:  ffff  dw      0xffff
00604e:  ffff  dw      0xffff
006050:  ffff  dw      0xffff
006052:  ffff  dw      0xffff
006054:  ffff  dw      0xffff
006056:  ffff  dw      0xffff
006058:  ffff  dw      0xffff
00605a:  ffff  dw      0xffff
00605c:  ffff  dw      0xffff
00605e:  ffff  dw      0xffff
006060:  ffff  dw      0xffff
006062:  ffff  dw      0xffff
006064:  ffff  dw      0xffff
006066:  ffff  dw      0xffff
006068:  ffff  dw      0xffff
00606a:  ffff  dw      0xffff
00606c:  ffff  dw      0xffff
00606e:  ffff  dw      0xffff
006070:  ffff  dw      0xffff
006072:  ffff  dw      0xffff
006074:  ffff  dw      0xffff
006076:  ffff  dw      0xffff
006078:  ffff  dw      0xffff
00607a:  ffff  dw      0xffff
00607c:  ffff  dw      0xffff
00607e:  ffff  dw      0xffff
006080:  ffff  dw      0xffff
006082:  ffff  dw      0xffff
006084:  ffff  dw      0xffff
006086:  ffff  dw      0xffff
006088:  ffff  dw      0xffff
00608a:  ffff  dw      0xffff
00608c:  ffff  dw      0xffff
00608e:  ffff  dw      0xffff
006090:  ffff  dw      0xffff
006092:  ffff  dw      0xffff
006094:  ffff  dw      0xffff
006096:  ffff  dw      0xffff
006098:  ffff  dw      0xffff
00609a:  ffff  dw      0xffff
00609c:  ffff  dw      0xffff
00609e:  ffff  dw      0xffff
0060a0:  ffff  dw      0xffff
0060a2:  ffff  dw      0xffff
0060a4:  ffff  dw      0xffff
0060a6:  ffff  dw      0xffff
0060a8:  ffff  dw      0xffff
0060aa:  ffff  dw      0xffff
0060ac:  ffff  dw      0xffff
0060ae:  ffff  dw      0xffff
0060b0:  ffff  dw      0xffff
0060b2:  ffff  dw      0xffff
0060b4:  ffff  dw      0xffff
0060b6:  ffff  dw      0xffff
0060b8:  ffff  dw      0xffff
0060ba:  ffff  dw      0xffff
0060bc:  ffff  dw      0xffff
0060be:  ffff  dw      0xffff
0060c0:  ffff  dw      0xffff
0060c2:  ffff  dw      0xffff
0060c4:  ffff  dw      0xffff
0060c6:  ffff  dw      0xffff
0060c8:  ffff  dw      0xffff
0060ca:  ffff  dw      0xffff
0060cc:  ffff  dw      0xffff
0060ce:  ffff  dw      0xffff
0060d0:  ffff  dw      0xffff
0060d2:  ffff  dw      0xffff
0060d4:  ffff  dw      0xffff
0060d6:  ffff  dw      0xffff
0060d8:  ffff  dw      0xffff
0060da:  ffff  dw      0xffff
0060dc:  ffff  dw      0xffff
0060de:  ffff  dw      0xffff
0060e0:  ffff  dw      0xffff
0060e2:  ffff  dw      0xffff
0060e4:  ffff  dw      0xffff
0060e6:  ffff  dw      0xffff
0060e8:  ffff  dw      0xffff
0060ea:  ffff  dw      0xffff
0060ec:  ffff  dw      0xffff
0060ee:  ffff  dw      0xffff
0060f0:  ffff  dw      0xffff
0060f2:  ffff  dw      0xffff
0060f4:  ffff  dw      0xffff
0060f6:  ffff  dw      0xffff
0060f8:  ffff  dw      0xffff
0060fa:  ffff  dw      0xffff
0060fc:  ffff  dw      0xffff
0060fe:  ffff  dw      0xffff
006100:  ffff  dw      0xffff
006102:  ffff  dw      0xffff
006104:  ffff  dw      0xffff
006106:  ffff  dw      0xffff
006108:  ffff  dw      0xffff
00610a:  ffff  dw      0xffff
00610c:  ffff  dw      0xffff
00610e:  ffff  dw      0xffff
006110:  ffff  dw      0xffff
006112:  ffff  dw      0xffff
006114:  ffff  dw      0xffff
006116:  ffff  dw      0xffff
006118:  ffff  dw      0xffff
00611a:  ffff  dw      0xffff
00611c:  ffff  dw      0xffff
00611e:  ffff  dw      0xffff
006120:  ffff  dw      0xffff
006122:  ffff  dw      0xffff
006124:  ffff  dw      0xffff
006126:  ffff  dw      0xffff
006128:  ffff  dw      0xffff
00612a:  ffff  dw      0xffff
00612c:  ffff  dw      0xffff
00612e:  ffff  dw      0xffff
006130:  ffff  dw      0xffff
006132:  ffff  dw      0xffff
006134:  ffff  dw      0xffff
006136:  ffff  dw      0xffff
006138:  ffff  dw      0xffff
00613a:  ffff  dw      0xffff
00613c:  ffff  dw      0xffff
00613e:  ffff  dw      0xffff
006140:  ffff  dw      0xffff
006142:  ffff  dw      0xffff
006144:  ffff  dw      0xffff
006146:  ffff  dw      0xffff
006148:  ffff  dw      0xffff
00614a:  ffff  dw      0xffff
00614c:  ffff  dw      0xffff
00614e:  ffff  dw      0xffff
006150:  ffff  dw      0xffff
006152:  ffff  dw      0xffff
006154:  ffff  dw      0xffff
006156:  ffff  dw      0xffff
006158:  ffff  dw      0xffff
00615a:  ffff  dw      0xffff
00615c:  ffff  dw      0xffff
00615e:  ffff  dw      0xffff
006160:  ffff  dw      0xffff
006162:  ffff  dw      0xffff
006164:  ffff  dw      0xffff
006166:  ffff  dw      0xffff
006168:  ffff  dw      0xffff
00616a:  ffff  dw      0xffff
00616c:  ffff  dw      0xffff
00616e:  ffff  dw      0xffff
006170:  ffff  dw      0xffff
006172:  ffff  dw      0xffff
006174:  ffff  dw      0xffff
006176:  ffff  dw      0xffff
006178:  ffff  dw      0xffff
00617a:  ffff  dw      0xffff
00617c:  ffff  dw      0xffff
00617e:  ffff  dw      0xffff
006180:  ffff  dw      0xffff
006182:  ffff  dw      0xffff
006184:  ffff  dw      0xffff
006186:  ffff  dw      0xffff
006188:  ffff  dw      0xffff
00618a:  ffff  dw      0xffff
00618c:  ffff  dw      0xffff
00618e:  ffff  dw      0xffff
006190:  ffff  dw      0xffff
006192:  ffff  dw      0xffff
006194:  ffff  dw      0xffff
006196:  ffff  dw      0xffff
006198:  ffff  dw      0xffff
00619a:  ffff  dw      0xffff
00619c:  ffff  dw      0xffff
00619e:  ffff  dw      0xffff
0061a0:  ffff  dw      0xffff
0061a2:  ffff  dw      0xffff
0061a4:  ffff  dw      0xffff
0061a6:  ffff  dw      0xffff
0061a8:  ffff  dw      0xffff
0061aa:  ffff  dw      0xffff
0061ac:  ffff  dw      0xffff
0061ae:  ffff  dw      0xffff
0061b0:  ffff  dw      0xffff
0061b2:  ffff  dw      0xffff
0061b4:  ffff  dw      0xffff
0061b6:  ffff  dw      0xffff
0061b8:  ffff  dw      0xffff
0061ba:  ffff  dw      0xffff
0061bc:  ffff  dw      0xffff
0061be:  ffff  dw      0xffff
0061c0:  ffff  dw      0xffff
0061c2:  ffff  dw      0xffff
0061c4:  ffff  dw      0xffff
0061c6:  ffff  dw      0xffff
0061c8:  ffff  dw      0xffff
0061ca:  ffff  dw      0xffff
0061cc:  ffff  dw      0xffff
0061ce:  ffff  dw      0xffff
0061d0:  ffff  dw      0xffff
0061d2:  ffff  dw      0xffff
0061d4:  ffff  dw      0xffff
0061d6:  ffff  dw      0xffff
0061d8:  ffff  dw      0xffff
0061da:  ffff  dw      0xffff
0061dc:  ffff  dw      0xffff
0061de:  ffff  dw      0xffff
0061e0:  ffff  dw      0xffff
0061e2:  ffff  dw      0xffff
0061e4:  ffff  dw      0xffff
0061e6:  ffff  dw      0xffff
0061e8:  ffff  dw      0xffff
0061ea:  ffff  dw      0xffff
0061ec:  ffff  dw      0xffff
0061ee:  ffff  dw      0xffff
0061f0:  ffff  dw      0xffff
0061f2:  ffff  dw      0xffff
0061f4:  ffff  dw      0xffff
0061f6:  ffff  dw      0xffff
0061f8:  ffff  dw      0xffff
0061fa:  ffff  dw      0xffff
0061fc:  ffff  dw      0xffff
0061fe:  ffff  dw      0xffff
006200:  ffff  dw      0xffff
006202:  ffff  dw      0xffff
006204:  ffff  dw      0xffff
006206:  ffff  dw      0xffff
006208:  ffff  dw      0xffff
00620a:  ffff  dw      0xffff
00620c:  ffff  dw      0xffff
00620e:  ffff  dw      0xffff
006210:  ffff  dw      0xffff
006212:  ffff  dw      0xffff
006214:  ffff  dw      0xffff
006216:  ffff  dw      0xffff
006218:  ffff  dw      0xffff
00621a:  ffff  dw      0xffff
00621c:  ffff  dw      0xffff
00621e:  ffff  dw      0xffff
006220:  ffff  dw      0xffff
006222:  ffff  dw      0xffff
006224:  ffff  dw      0xffff
006226:  ffff  dw      0xffff
006228:  ffff  dw      0xffff
00622a:  ffff  dw      0xffff
00622c:  ffff  dw      0xffff
00622e:  ffff  dw      0xffff
006230:  ffff  dw      0xffff
006232:  ffff  dw      0xffff
006234:  ffff  dw      0xffff
006236:  ffff  dw      0xffff
006238:  ffff  dw      0xffff
00623a:  ffff  dw      0xffff
00623c:  ffff  dw      0xffff
00623e:  ffff  dw      0xffff
006240:  ffff  dw      0xffff
006242:  ffff  dw      0xffff
006244:  ffff  dw      0xffff
006246:  ffff  dw      0xffff
006248:  ffff  dw      0xffff
00624a:  ffff  dw      0xffff
00624c:  ffff  dw      0xffff
00624e:  ffff  dw      0xffff
006250:  ffff  dw      0xffff
006252:  ffff  dw      0xffff
006254:  ffff  dw      0xffff
006256:  ffff  dw      0xffff
006258:  ffff  dw      0xffff
00625a:  ffff  dw      0xffff
00625c:  ffff  dw      0xffff
00625e:  ffff  dw      0xffff
006260:  ffff  dw      0xffff
006262:  ffff  dw      0xffff
006264:  ffff  dw      0xffff
006266:  ffff  dw      0xffff
006268:  ffff  dw      0xffff
00626a:  ffff  dw      0xffff
00626c:  ffff  dw      0xffff
00626e:  ffff  dw      0xffff
006270:  ffff  dw      0xffff
006272:  ffff  dw      0xffff
006274:  ffff  dw      0xffff
006276:  ffff  dw      0xffff
006278:  ffff  dw      0xffff
00627a:  ffff  dw      0xffff
00627c:  ffff  dw      0xffff
00627e:  ffff  dw      0xffff
006280:  ffff  dw      0xffff
006282:  ffff  dw      0xffff
006284:  ffff  dw      0xffff
006286:  ffff  dw      0xffff
006288:  ffff  dw      0xffff
00628a:  ffff  dw      0xffff
00628c:  ffff  dw      0xffff
00628e:  ffff  dw      0xffff
006290:  ffff  dw      0xffff
006292:  ffff  dw      0xffff
006294:  ffff  dw      0xffff
006296:  ffff  dw      0xffff
006298:  ffff  dw      0xffff
00629a:  ffff  dw      0xffff
00629c:  ffff  dw      0xffff
00629e:  ffff  dw      0xffff
0062a0:  ffff  dw      0xffff
0062a2:  ffff  dw      0xffff
0062a4:  ffff  dw      0xffff
0062a6:  ffff  dw      0xffff
0062a8:  ffff  dw      0xffff
0062aa:  ffff  dw      0xffff
0062ac:  ffff  dw      0xffff
0062ae:  ffff  dw      0xffff
0062b0:  ffff  dw      0xffff
0062b2:  ffff  dw      0xffff
0062b4:  ffff  dw      0xffff
0062b6:  ffff  dw      0xffff
0062b8:  ffff  dw      0xffff
0062ba:  ffff  dw      0xffff
0062bc:  ffff  dw      0xffff
0062be:  ffff  dw      0xffff
0062c0:  ffff  dw      0xffff
0062c2:  ffff  dw      0xffff
0062c4:  ffff  dw      0xffff
0062c6:  ffff  dw      0xffff
0062c8:  ffff  dw      0xffff
0062ca:  ffff  dw      0xffff
0062cc:  ffff  dw      0xffff
0062ce:  ffff  dw      0xffff
0062d0:  ffff  dw      0xffff
0062d2:  ffff  dw      0xffff
0062d4:  ffff  dw      0xffff
0062d6:  ffff  dw      0xffff
0062d8:  ffff  dw      0xffff
0062da:  ffff  dw      0xffff
0062dc:  ffff  dw      0xffff
0062de:  ffff  dw      0xffff
0062e0:  ffff  dw      0xffff
0062e2:  ffff  dw      0xffff
0062e4:  ffff  dw      0xffff
0062e6:  ffff  dw      0xffff
0062e8:  ffff  dw      0xffff
0062ea:  ffff  dw      0xffff
0062ec:  ffff  dw      0xffff
0062ee:  ffff  dw      0xffff
0062f0:  ffff  dw      0xffff
0062f2:  ffff  dw      0xffff
0062f4:  ffff  dw      0xffff
0062f6:  ffff  dw      0xffff
0062f8:  ffff  dw      0xffff
0062fa:  ffff  dw      0xffff
0062fc:  ffff  dw      0xffff
0062fe:  ffff  dw      0xffff
006300:  ffff  dw      0xffff
006302:  ffff  dw      0xffff
006304:  ffff  dw      0xffff
006306:  ffff  dw      0xffff
006308:  ffff  dw      0xffff
00630a:  ffff  dw      0xffff
00630c:  ffff  dw      0xffff
00630e:  ffff  dw      0xffff
006310:  ffff  dw      0xffff
006312:  ffff  dw      0xffff
006314:  ffff  dw      0xffff
006316:  ffff  dw      0xffff
006318:  ffff  dw      0xffff
00631a:  ffff  dw      0xffff
00631c:  ffff  dw      0xffff
00631e:  ffff  dw      0xffff
006320:  ffff  dw      0xffff
006322:  ffff  dw      0xffff
006324:  ffff  dw      0xffff
006326:  ffff  dw      0xffff
006328:  ffff  dw      0xffff
00632a:  ffff  dw      0xffff
00632c:  ffff  dw      0xffff
00632e:  ffff  dw      0xffff
006330:  ffff  dw      0xffff
006332:  ffff  dw      0xffff
006334:  ffff  dw      0xffff
006336:  ffff  dw      0xffff
006338:  ffff  dw      0xffff
00633a:  ffff  dw      0xffff
00633c:  ffff  dw      0xffff
00633e:  ffff  dw      0xffff
006340:  ffff  dw      0xffff
006342:  ffff  dw      0xffff
006344:  ffff  dw      0xffff
006346:  ffff  dw      0xffff
006348:  ffff  dw      0xffff
00634a:  ffff  dw      0xffff
00634c:  ffff  dw      0xffff
00634e:  ffff  dw      0xffff
006350:  ffff  dw      0xffff
006352:  ffff  dw      0xffff
006354:  ffff  dw      0xffff
006356:  ffff  dw      0xffff
006358:  ffff  dw      0xffff
00635a:  ffff  dw      0xffff
00635c:  ffff  dw      0xffff
00635e:  ffff  dw      0xffff
006360:  ffff  dw      0xffff
006362:  ffff  dw      0xffff
006364:  ffff  dw      0xffff
006366:  ffff  dw      0xffff
006368:  ffff  dw      0xffff
00636a:  ffff  dw      0xffff
00636c:  ffff  dw      0xffff
00636e:  ffff  dw      0xffff
006370:  ffff  dw      0xffff
006372:  ffff  dw      0xffff
006374:  ffff  dw      0xffff
006376:  ffff  dw      0xffff
006378:  ffff  dw      0xffff
00637a:  ffff  dw      0xffff
00637c:  ffff  dw      0xffff
00637e:  ffff  dw      0xffff
006380:  ffff  dw      0xffff
006382:  ffff  dw      0xffff
006384:  ffff  dw      0xffff
006386:  ffff  dw      0xffff
006388:  ffff  dw      0xffff
00638a:  ffff  dw      0xffff
00638c:  ffff  dw      0xffff
00638e:  ffff  dw      0xffff
006390:  ffff  dw      0xffff
006392:  ffff  dw      0xffff
006394:  ffff  dw      0xffff
006396:  ffff  dw      0xffff
006398:  ffff  dw      0xffff
00639a:  ffff  dw      0xffff
00639c:  ffff  dw      0xffff
00639e:  ffff  dw      0xffff
0063a0:  ffff  dw      0xffff
0063a2:  ffff  dw      0xffff
0063a4:  ffff  dw      0xffff
0063a6:  ffff  dw      0xffff
0063a8:  ffff  dw      0xffff
0063aa:  ffff  dw      0xffff
0063ac:  ffff  dw      0xffff
0063ae:  ffff  dw      0xffff
0063b0:  ffff  dw      0xffff
0063b2:  ffff  dw      0xffff
0063b4:  ffff  dw      0xffff
0063b6:  ffff  dw      0xffff
0063b8:  ffff  dw      0xffff
0063ba:  ffff  dw      0xffff
0063bc:  ffff  dw      0xffff
0063be:  ffff  dw      0xffff
0063c0:  ffff  dw      0xffff
0063c2:  ffff  dw      0xffff
0063c4:  ffff  dw      0xffff
0063c6:  ffff  dw      0xffff
0063c8:  ffff  dw      0xffff
0063ca:  ffff  dw      0xffff
0063cc:  ffff  dw      0xffff
0063ce:  ffff  dw      0xffff
0063d0:  ffff  dw      0xffff
0063d2:  ffff  dw      0xffff
0063d4:  ffff  dw      0xffff
0063d6:  ffff  dw      0xffff
0063d8:  ffff  dw      0xffff
0063da:  ffff  dw      0xffff
0063dc:  ffff  dw      0xffff
0063de:  ffff  dw      0xffff
0063e0:  ffff  dw      0xffff
0063e2:  ffff  dw      0xffff
0063e4:  ffff  dw      0xffff
0063e6:  ffff  dw      0xffff
0063e8:  ffff  dw      0xffff
0063ea:  ffff  dw      0xffff
0063ec:  ffff  dw      0xffff
0063ee:  ffff  dw      0xffff
0063f0:  ffff  dw      0xffff
0063f2:  ffff  dw      0xffff
0063f4:  ffff  dw      0xffff
0063f6:  ffff  dw      0xffff
0063f8:  ffff  dw      0xffff
0063fa:  ffff  dw      0xffff
0063fc:  ffff  dw      0xffff
0063fe:  ffff  dw      0xffff
006400:  ffff  dw      0xffff
006402:  ffff  dw      0xffff
006404:  ffff  dw      0xffff
006406:  ffff  dw      0xffff
006408:  ffff  dw      0xffff
00640a:  ffff  dw      0xffff
00640c:  ffff  dw      0xffff
00640e:  ffff  dw      0xffff
006410:  ffff  dw      0xffff
006412:  ffff  dw      0xffff
006414:  ffff  dw      0xffff
006416:  ffff  dw      0xffff
006418:  ffff  dw      0xffff
00641a:  ffff  dw      0xffff
00641c:  ffff  dw      0xffff
00641e:  ffff  dw      0xffff
006420:  ffff  dw      0xffff
006422:  ffff  dw      0xffff
006424:  ffff  dw      0xffff
006426:  ffff  dw      0xffff
006428:  ffff  dw      0xffff
00642a:  ffff  dw      0xffff
00642c:  ffff  dw      0xffff
00642e:  ffff  dw      0xffff
006430:  ffff  dw      0xffff
006432:  ffff  dw      0xffff
006434:  ffff  dw      0xffff
006436:  ffff  dw      0xffff
006438:  ffff  dw      0xffff
00643a:  ffff  dw      0xffff
00643c:  ffff  dw      0xffff
00643e:  ffff  dw      0xffff
006440:  ffff  dw      0xffff
006442:  ffff  dw      0xffff
006444:  ffff  dw      0xffff
006446:  ffff  dw      0xffff
006448:  ffff  dw      0xffff
00644a:  ffff  dw      0xffff
00644c:  ffff  dw      0xffff
00644e:  ffff  dw      0xffff
006450:  ffff  dw      0xffff
006452:  ffff  dw      0xffff
006454:  ffff  dw      0xffff
006456:  ffff  dw      0xffff
006458:  ffff  dw      0xffff
00645a:  ffff  dw      0xffff
00645c:  ffff  dw      0xffff
00645e:  ffff  dw      0xffff
006460:  ffff  dw      0xffff
006462:  ffff  dw      0xffff
006464:  ffff  dw      0xffff
006466:  ffff  dw      0xffff
006468:  ffff  dw      0xffff
00646a:  ffff  dw      0xffff
00646c:  ffff  dw      0xffff
00646e:  ffff  dw      0xffff
006470:  ffff  dw      0xffff
006472:  ffff  dw      0xffff
006474:  ffff  dw      0xffff
006476:  ffff  dw      0xffff
006478:  ffff  dw      0xffff
00647a:  ffff  dw      0xffff
00647c:  ffff  dw      0xffff
00647e:  ffff  dw      0xffff
006480:  ffff  dw      0xffff
006482:  ffff  dw      0xffff
006484:  ffff  dw      0xffff
006486:  ffff  dw      0xffff
006488:  ffff  dw      0xffff
00648a:  ffff  dw      0xffff
00648c:  ffff  dw      0xffff
00648e:  ffff  dw      0xffff
006490:  ffff  dw      0xffff
006492:  ffff  dw      0xffff
006494:  ffff  dw      0xffff
006496:  ffff  dw      0xffff
006498:  ffff  dw      0xffff
00649a:  ffff  dw      0xffff
00649c:  ffff  dw      0xffff
00649e:  ffff  dw      0xffff
0064a0:  ffff  dw      0xffff
0064a2:  ffff  dw      0xffff
0064a4:  ffff  dw      0xffff
0064a6:  ffff  dw      0xffff
0064a8:  ffff  dw      0xffff
0064aa:  ffff  dw      0xffff
0064ac:  ffff  dw      0xffff
0064ae:  ffff  dw      0xffff
0064b0:  ffff  dw      0xffff
0064b2:  ffff  dw      0xffff
0064b4:  ffff  dw      0xffff
0064b6:  ffff  dw      0xffff
0064b8:  ffff  dw      0xffff
0064ba:  ffff  dw      0xffff
0064bc:  ffff  dw      0xffff
0064be:  ffff  dw      0xffff
0064c0:  ffff  dw      0xffff
0064c2:  ffff  dw      0xffff
0064c4:  ffff  dw      0xffff
0064c6:  ffff  dw      0xffff
0064c8:  ffff  dw      0xffff
0064ca:  ffff  dw      0xffff
0064cc:  ffff  dw      0xffff
0064ce:  ffff  dw      0xffff
0064d0:  ffff  dw      0xffff
0064d2:  ffff  dw      0xffff
0064d4:  ffff  dw      0xffff
0064d6:  ffff  dw      0xffff
0064d8:  ffff  dw      0xffff
0064da:  ffff  dw      0xffff
0064dc:  ffff  dw      0xffff
0064de:  ffff  dw      0xffff
0064e0:  ffff  dw      0xffff
0064e2:  ffff  dw      0xffff
0064e4:  ffff  dw      0xffff
0064e6:  ffff  dw      0xffff
0064e8:  ffff  dw      0xffff
0064ea:  ffff  dw      0xffff
0064ec:  ffff  dw      0xffff
0064ee:  ffff  dw      0xffff
0064f0:  ffff  dw      0xffff
0064f2:  ffff  dw      0xffff
0064f4:  ffff  dw      0xffff
0064f6:  ffff  dw      0xffff
0064f8:  ffff  dw      0xffff
0064fa:  ffff  dw      0xffff
0064fc:  ffff  dw      0xffff
0064fe:  ffff  dw      0xffff
006500:  ffff  dw      0xffff
006502:  ffff  dw      0xffff
006504:  ffff  dw      0xffff
006506:  ffff  dw      0xffff
006508:  ffff  dw      0xffff
00650a:  ffff  dw      0xffff
00650c:  ffff  dw      0xffff
00650e:  ffff  dw      0xffff
006510:  ffff  dw      0xffff
006512:  ffff  dw      0xffff
006514:  ffff  dw      0xffff
006516:  ffff  dw      0xffff
006518:  ffff  dw      0xffff
00651a:  ffff  dw      0xffff
00651c:  ffff  dw      0xffff
00651e:  ffff  dw      0xffff
006520:  ffff  dw      0xffff
006522:  ffff  dw      0xffff
006524:  ffff  dw      0xffff
006526:  ffff  dw      0xffff
006528:  ffff  dw      0xffff
00652a:  ffff  dw      0xffff
00652c:  ffff  dw      0xffff
00652e:  ffff  dw      0xffff
006530:  ffff  dw      0xffff
006532:  ffff  dw      0xffff
006534:  ffff  dw      0xffff
006536:  ffff  dw      0xffff
006538:  ffff  dw      0xffff
00653a:  ffff  dw      0xffff
00653c:  ffff  dw      0xffff
00653e:  ffff  dw      0xffff
006540:  ffff  dw      0xffff
006542:  ffff  dw      0xffff
006544:  ffff  dw      0xffff
006546:  ffff  dw      0xffff
006548:  ffff  dw      0xffff
00654a:  ffff  dw      0xffff
00654c:  ffff  dw      0xffff
00654e:  ffff  dw      0xffff
006550:  ffff  dw      0xffff
006552:  ffff  dw      0xffff
006554:  ffff  dw      0xffff
006556:  ffff  dw      0xffff
006558:  ffff  dw      0xffff
00655a:  ffff  dw      0xffff
00655c:  ffff  dw      0xffff
00655e:  ffff  dw      0xffff
006560:  ffff  dw      0xffff
006562:  ffff  dw      0xffff
006564:  ffff  dw      0xffff
006566:  ffff  dw      0xffff
006568:  ffff  dw      0xffff
00656a:  ffff  dw      0xffff
00656c:  ffff  dw      0xffff
00656e:  ffff  dw      0xffff
006570:  ffff  dw      0xffff
006572:  ffff  dw      0xffff
006574:  ffff  dw      0xffff
006576:  ffff  dw      0xffff
006578:  ffff  dw      0xffff
00657a:  ffff  dw      0xffff
00657c:  ffff  dw      0xffff
00657e:  ffff  dw      0xffff
006580:  ffff  dw      0xffff
006582:  ffff  dw      0xffff
006584:  ffff  dw      0xffff
006586:  ffff  dw      0xffff
006588:  ffff  dw      0xffff
00658a:  ffff  dw      0xffff
00658c:  ffff  dw      0xffff
00658e:  ffff  dw      0xffff
006590:  ffff  dw      0xffff
006592:  ffff  dw      0xffff
006594:  ffff  dw      0xffff
006596:  ffff  dw      0xffff
006598:  ffff  dw      0xffff
00659a:  ffff  dw      0xffff
00659c:  ffff  dw      0xffff
00659e:  ffff  dw      0xffff
0065a0:  ffff  dw      0xffff
0065a2:  ffff  dw      0xffff
0065a4:  ffff  dw      0xffff
0065a6:  ffff  dw      0xffff
0065a8:  ffff  dw      0xffff
0065aa:  ffff  dw      0xffff
0065ac:  ffff  dw      0xffff
0065ae:  ffff  dw      0xffff
0065b0:  ffff  dw      0xffff
0065b2:  ffff  dw      0xffff
0065b4:  ffff  dw      0xffff
0065b6:  ffff  dw      0xffff
0065b8:  ffff  dw      0xffff
0065ba:  ffff  dw      0xffff
0065bc:  ffff  dw      0xffff
0065be:  ffff  dw      0xffff
0065c0:  ffff  dw      0xffff
0065c2:  ffff  dw      0xffff
0065c4:  ffff  dw      0xffff
0065c6:  ffff  dw      0xffff
0065c8:  ffff  dw      0xffff
0065ca:  ffff  dw      0xffff
0065cc:  ffff  dw      0xffff
0065ce:  ffff  dw      0xffff
0065d0:  ffff  dw      0xffff
0065d2:  ffff  dw      0xffff
0065d4:  ffff  dw      0xffff
0065d6:  ffff  dw      0xffff
0065d8:  ffff  dw      0xffff
0065da:  ffff  dw      0xffff
0065dc:  ffff  dw      0xffff
0065de:  ffff  dw      0xffff
0065e0:  ffff  dw      0xffff
0065e2:  ffff  dw      0xffff
0065e4:  ffff  dw      0xffff
0065e6:  ffff  dw      0xffff
0065e8:  ffff  dw      0xffff
0065ea:  ffff  dw      0xffff
0065ec:  ffff  dw      0xffff
0065ee:  ffff  dw      0xffff
0065f0:  ffff  dw      0xffff
0065f2:  ffff  dw      0xffff
0065f4:  ffff  dw      0xffff
0065f6:  ffff  dw      0xffff
0065f8:  ffff  dw      0xffff
0065fa:  ffff  dw      0xffff
0065fc:  ffff  dw      0xffff
0065fe:  ffff  dw      0xffff
006600:  ffff  dw      0xffff
006602:  ffff  dw      0xffff
006604:  ffff  dw      0xffff
006606:  ffff  dw      0xffff
006608:  ffff  dw      0xffff
00660a:  ffff  dw      0xffff
00660c:  ffff  dw      0xffff
00660e:  ffff  dw      0xffff
006610:  ffff  dw      0xffff
006612:  ffff  dw      0xffff
006614:  ffff  dw      0xffff
006616:  ffff  dw      0xffff
006618:  ffff  dw      0xffff
00661a:  ffff  dw      0xffff
00661c:  ffff  dw      0xffff
00661e:  ffff  dw      0xffff
006620:  ffff  dw      0xffff
006622:  ffff  dw      0xffff
006624:  ffff  dw      0xffff
006626:  ffff  dw      0xffff
006628:  ffff  dw      0xffff
00662a:  ffff  dw      0xffff
00662c:  ffff  dw      0xffff
00662e:  ffff  dw      0xffff
006630:  ffff  dw      0xffff
006632:  ffff  dw      0xffff
006634:  ffff  dw      0xffff
006636:  ffff  dw      0xffff
006638:  ffff  dw      0xffff
00663a:  ffff  dw      0xffff
00663c:  ffff  dw      0xffff
00663e:  ffff  dw      0xffff
006640:  ffff  dw      0xffff
006642:  ffff  dw      0xffff
006644:  ffff  dw      0xffff
006646:  ffff  dw      0xffff
006648:  ffff  dw      0xffff
00664a:  ffff  dw      0xffff
00664c:  ffff  dw      0xffff
00664e:  ffff  dw      0xffff
006650:  ffff  dw      0xffff
006652:  ffff  dw      0xffff
006654:  ffff  dw      0xffff
006656:  ffff  dw      0xffff
006658:  ffff  dw      0xffff
00665a:  ffff  dw      0xffff
00665c:  ffff  dw      0xffff
00665e:  ffff  dw      0xffff
006660:  ffff  dw      0xffff
006662:  ffff  dw      0xffff
006664:  ffff  dw      0xffff
006666:  ffff  dw      0xffff
006668:  ffff  dw      0xffff
00666a:  ffff  dw      0xffff
00666c:  ffff  dw      0xffff
00666e:  ffff  dw      0xffff
006670:  ffff  dw      0xffff
006672:  ffff  dw      0xffff
006674:  ffff  dw      0xffff
006676:  ffff  dw      0xffff
006678:  ffff  dw      0xffff
00667a:  ffff  dw      0xffff
00667c:  ffff  dw      0xffff
00667e:  ffff  dw      0xffff
006680:  ffff  dw      0xffff
006682:  ffff  dw      0xffff
006684:  ffff  dw      0xffff
006686:  ffff  dw      0xffff
006688:  ffff  dw      0xffff
00668a:  ffff  dw      0xffff
00668c:  ffff  dw      0xffff
00668e:  ffff  dw      0xffff
006690:  ffff  dw      0xffff
006692:  ffff  dw      0xffff
006694:  ffff  dw      0xffff
006696:  ffff  dw      0xffff
006698:  ffff  dw      0xffff
00669a:  ffff  dw      0xffff
00669c:  ffff  dw      0xffff
00669e:  ffff  dw      0xffff
0066a0:  ffff  dw      0xffff
0066a2:  ffff  dw      0xffff
0066a4:  ffff  dw      0xffff
0066a6:  ffff  dw      0xffff
0066a8:  ffff  dw      0xffff
0066aa:  ffff  dw      0xffff
0066ac:  ffff  dw      0xffff
0066ae:  ffff  dw      0xffff
0066b0:  ffff  dw      0xffff
0066b2:  ffff  dw      0xffff
0066b4:  ffff  dw      0xffff
0066b6:  ffff  dw      0xffff
0066b8:  ffff  dw      0xffff
0066ba:  ffff  dw      0xffff
0066bc:  ffff  dw      0xffff
0066be:  ffff  dw      0xffff
0066c0:  ffff  dw      0xffff
0066c2:  ffff  dw      0xffff
0066c4:  ffff  dw      0xffff
0066c6:  ffff  dw      0xffff
0066c8:  ffff  dw      0xffff
0066ca:  ffff  dw      0xffff
0066cc:  ffff  dw      0xffff
0066ce:  ffff  dw      0xffff
0066d0:  ffff  dw      0xffff
0066d2:  ffff  dw      0xffff
0066d4:  ffff  dw      0xffff
0066d6:  ffff  dw      0xffff
0066d8:  ffff  dw      0xffff
0066da:  ffff  dw      0xffff
0066dc:  ffff  dw      0xffff
0066de:  ffff  dw      0xffff
0066e0:  ffff  dw      0xffff
0066e2:  ffff  dw      0xffff
0066e4:  ffff  dw      0xffff
0066e6:  ffff  dw      0xffff
0066e8:  ffff  dw      0xffff
0066ea:  ffff  dw      0xffff
0066ec:  ffff  dw      0xffff
0066ee:  ffff  dw      0xffff
0066f0:  ffff  dw      0xffff
0066f2:  ffff  dw      0xffff
0066f4:  ffff  dw      0xffff
0066f6:  ffff  dw      0xffff
0066f8:  ffff  dw      0xffff
0066fa:  ffff  dw      0xffff
0066fc:  ffff  dw      0xffff
0066fe:  ffff  dw      0xffff
006700:  ffff  dw      0xffff
006702:  ffff  dw      0xffff
006704:  ffff  dw      0xffff
006706:  ffff  dw      0xffff
006708:  ffff  dw      0xffff
00670a:  ffff  dw      0xffff
00670c:  ffff  dw      0xffff
00670e:  ffff  dw      0xffff
006710:  ffff  dw      0xffff
006712:  ffff  dw      0xffff
006714:  ffff  dw      0xffff
006716:  ffff  dw      0xffff
006718:  ffff  dw      0xffff
00671a:  ffff  dw      0xffff
00671c:  ffff  dw      0xffff
00671e:  ffff  dw      0xffff
006720:  ffff  dw      0xffff
006722:  ffff  dw      0xffff
006724:  ffff  dw      0xffff
006726:  ffff  dw      0xffff
006728:  ffff  dw      0xffff
00672a:  ffff  dw      0xffff
00672c:  ffff  dw      0xffff
00672e:  ffff  dw      0xffff
006730:  ffff  dw      0xffff
006732:  ffff  dw      0xffff
006734:  ffff  dw      0xffff
006736:  ffff  dw      0xffff
006738:  ffff  dw      0xffff
00673a:  ffff  dw      0xffff
00673c:  ffff  dw      0xffff
00673e:  ffff  dw      0xffff
006740:  ffff  dw      0xffff
006742:  ffff  dw      0xffff
006744:  ffff  dw      0xffff
006746:  ffff  dw      0xffff
006748:  ffff  dw      0xffff
00674a:  ffff  dw      0xffff
00674c:  ffff  dw      0xffff
00674e:  ffff  dw      0xffff
006750:  ffff  dw      0xffff
006752:  ffff  dw      0xffff
006754:  ffff  dw      0xffff
006756:  ffff  dw      0xffff
006758:  ffff  dw      0xffff
00675a:  ffff  dw      0xffff
00675c:  ffff  dw      0xffff
00675e:  ffff  dw      0xffff
006760:  ffff  dw      0xffff
006762:  ffff  dw      0xffff
006764:  ffff  dw      0xffff
006766:  ffff  dw      0xffff
006768:  ffff  dw      0xffff
00676a:  ffff  dw      0xffff
00676c:  ffff  dw      0xffff
00676e:  ffff  dw      0xffff
006770:  ffff  dw      0xffff
006772:  ffff  dw      0xffff
006774:  ffff  dw      0xffff
006776:  ffff  dw      0xffff
006778:  ffff  dw      0xffff
00677a:  ffff  dw      0xffff
00677c:  ffff  dw      0xffff
00677e:  ffff  dw      0xffff
006780:  ffff  dw      0xffff
006782:  ffff  dw      0xffff
006784:  ffff  dw      0xffff
006786:  ffff  dw      0xffff
006788:  ffff  dw      0xffff
00678a:  ffff  dw      0xffff
00678c:  ffff  dw      0xffff
00678e:  ffff  dw      0xffff
006790:  ffff  dw      0xffff
006792:  ffff  dw      0xffff
006794:  ffff  dw      0xffff
006796:  ffff  dw      0xffff
006798:  ffff  dw      0xffff
00679a:  ffff  dw      0xffff
00679c:  ffff  dw      0xffff
00679e:  ffff  dw      0xffff
0067a0:  ffff  dw      0xffff
0067a2:  ffff  dw      0xffff
0067a4:  ffff  dw      0xffff
0067a6:  ffff  dw      0xffff
0067a8:  ffff  dw      0xffff
0067aa:  ffff  dw      0xffff
0067ac:  ffff  dw      0xffff
0067ae:  ffff  dw      0xffff
0067b0:  ffff  dw      0xffff
0067b2:  ffff  dw      0xffff
0067b4:  ffff  dw      0xffff
0067b6:  ffff  dw      0xffff
0067b8:  ffff  dw      0xffff
0067ba:  ffff  dw      0xffff
0067bc:  ffff  dw      0xffff
0067be:  ffff  dw      0xffff
0067c0:  ffff  dw      0xffff
0067c2:  ffff  dw      0xffff
0067c4:  ffff  dw      0xffff
0067c6:  ffff  dw      0xffff
0067c8:  ffff  dw      0xffff
0067ca:  ffff  dw      0xffff
0067cc:  ffff  dw      0xffff
0067ce:  ffff  dw      0xffff
0067d0:  ffff  dw      0xffff
0067d2:  ffff  dw      0xffff
0067d4:  ffff  dw      0xffff
0067d6:  ffff  dw      0xffff
0067d8:  ffff  dw      0xffff
0067da:  ffff  dw      0xffff
0067dc:  ffff  dw      0xffff
0067de:  ffff  dw      0xffff
0067e0:  ffff  dw      0xffff
0067e2:  ffff  dw      0xffff
0067e4:  ffff  dw      0xffff
0067e6:  ffff  dw      0xffff
0067e8:  ffff  dw      0xffff
0067ea:  ffff  dw      0xffff
0067ec:  ffff  dw      0xffff
0067ee:  ffff  dw      0xffff
0067f0:  ffff  dw      0xffff
0067f2:  ffff  dw      0xffff
0067f4:  ffff  dw      0xffff
0067f6:  ffff  dw      0xffff
0067f8:  ffff  dw      0xffff
0067fa:  ffff  dw      0xffff
0067fc:  ffff  dw      0xffff
0067fe:  ffff  dw      0xffff
006800:  ffff  dw      0xffff
006802:  ffff  dw      0xffff
006804:  ffff  dw      0xffff
006806:  ffff  dw      0xffff
006808:  ffff  dw      0xffff
00680a:  ffff  dw      0xffff
00680c:  ffff  dw      0xffff
00680e:  ffff  dw      0xffff
006810:  ffff  dw      0xffff
006812:  ffff  dw      0xffff
006814:  ffff  dw      0xffff
006816:  ffff  dw      0xffff
006818:  ffff  dw      0xffff
00681a:  ffff  dw      0xffff
00681c:  ffff  dw      0xffff
00681e:  ffff  dw      0xffff
006820:  ffff  dw      0xffff
006822:  ffff  dw      0xffff
006824:  ffff  dw      0xffff
006826:  ffff  dw      0xffff
006828:  ffff  dw      0xffff
00682a:  ffff  dw      0xffff
00682c:  ffff  dw      0xffff
00682e:  ffff  dw      0xffff
006830:  ffff  dw      0xffff
006832:  ffff  dw      0xffff
006834:  ffff  dw      0xffff
006836:  ffff  dw      0xffff
006838:  ffff  dw      0xffff
00683a:  ffff  dw      0xffff
00683c:  ffff  dw      0xffff
00683e:  ffff  dw      0xffff
006840:  ffff  dw      0xffff
006842:  ffff  dw      0xffff
006844:  ffff  dw      0xffff
006846:  ffff  dw      0xffff
006848:  ffff  dw      0xffff
00684a:  ffff  dw      0xffff
00684c:  ffff  dw      0xffff
00684e:  ffff  dw      0xffff
006850:  ffff  dw      0xffff
006852:  ffff  dw      0xffff
006854:  ffff  dw      0xffff
006856:  ffff  dw      0xffff
006858:  ffff  dw      0xffff
00685a:  ffff  dw      0xffff
00685c:  ffff  dw      0xffff
00685e:  ffff  dw      0xffff
006860:  ffff  dw      0xffff
006862:  ffff  dw      0xffff
006864:  ffff  dw      0xffff
006866:  ffff  dw      0xffff
006868:  ffff  dw      0xffff
00686a:  ffff  dw      0xffff
00686c:  ffff  dw      0xffff
00686e:  ffff  dw      0xffff
006870:  ffff  dw      0xffff
006872:  ffff  dw      0xffff
006874:  ffff  dw      0xffff
006876:  ffff  dw      0xffff
006878:  ffff  dw      0xffff
00687a:  ffff  dw      0xffff
00687c:  ffff  dw      0xffff
00687e:  ffff  dw      0xffff
006880:  ffff  dw      0xffff
006882:  ffff  dw      0xffff
006884:  ffff  dw      0xffff
006886:  ffff  dw      0xffff
006888:  ffff  dw      0xffff
00688a:  ffff  dw      0xffff
00688c:  ffff  dw      0xffff
00688e:  ffff  dw      0xffff
006890:  ffff  dw      0xffff
006892:  ffff  dw      0xffff
006894:  ffff  dw      0xffff
006896:  ffff  dw      0xffff
006898:  ffff  dw      0xffff
00689a:  ffff  dw      0xffff
00689c:  ffff  dw      0xffff
00689e:  ffff  dw      0xffff
0068a0:  ffff  dw      0xffff
0068a2:  ffff  dw      0xffff
0068a4:  ffff  dw      0xffff
0068a6:  ffff  dw      0xffff
0068a8:  ffff  dw      0xffff
0068aa:  ffff  dw      0xffff
0068ac:  ffff  dw      0xffff
0068ae:  ffff  dw      0xffff
0068b0:  ffff  dw      0xffff
0068b2:  ffff  dw      0xffff
0068b4:  ffff  dw      0xffff
0068b6:  ffff  dw      0xffff
0068b8:  ffff  dw      0xffff
0068ba:  ffff  dw      0xffff
0068bc:  ffff  dw      0xffff
0068be:  ffff  dw      0xffff
0068c0:  ffff  dw      0xffff
0068c2:  ffff  dw      0xffff
0068c4:  ffff  dw      0xffff
0068c6:  ffff  dw      0xffff
0068c8:  ffff  dw      0xffff
0068ca:  ffff  dw      0xffff
0068cc:  ffff  dw      0xffff
0068ce:  ffff  dw      0xffff
0068d0:  ffff  dw      0xffff
0068d2:  ffff  dw      0xffff
0068d4:  ffff  dw      0xffff
0068d6:  ffff  dw      0xffff
0068d8:  ffff  dw      0xffff
0068da:  ffff  dw      0xffff
0068dc:  ffff  dw      0xffff
0068de:  ffff  dw      0xffff
0068e0:  ffff  dw      0xffff
0068e2:  ffff  dw      0xffff
0068e4:  ffff  dw      0xffff
0068e6:  ffff  dw      0xffff
0068e8:  ffff  dw      0xffff
0068ea:  ffff  dw      0xffff
0068ec:  ffff  dw      0xffff
0068ee:  ffff  dw      0xffff
0068f0:  ffff  dw      0xffff
0068f2:  ffff  dw      0xffff
0068f4:  ffff  dw      0xffff
0068f6:  ffff  dw      0xffff
0068f8:  ffff  dw      0xffff
0068fa:  ffff  dw      0xffff
0068fc:  ffff  dw      0xffff
0068fe:  ffff  dw      0xffff
006900:  ffff  dw      0xffff
006902:  ffff  dw      0xffff
006904:  ffff  dw      0xffff
006906:  ffff  dw      0xffff
006908:  ffff  dw      0xffff
00690a:  ffff  dw      0xffff
00690c:  ffff  dw      0xffff
00690e:  ffff  dw      0xffff
006910:  ffff  dw      0xffff
006912:  ffff  dw      0xffff
006914:  ffff  dw      0xffff
006916:  ffff  dw      0xffff
006918:  ffff  dw      0xffff
00691a:  ffff  dw      0xffff
00691c:  ffff  dw      0xffff
00691e:  ffff  dw      0xffff
006920:  ffff  dw      0xffff
006922:  ffff  dw      0xffff
006924:  ffff  dw      0xffff
006926:  ffff  dw      0xffff
006928:  ffff  dw      0xffff
00692a:  ffff  dw      0xffff
00692c:  ffff  dw      0xffff
00692e:  ffff  dw      0xffff
006930:  ffff  dw      0xffff
006932:  ffff  dw      0xffff
006934:  ffff  dw      0xffff
006936:  ffff  dw      0xffff
006938:  ffff  dw      0xffff
00693a:  ffff  dw      0xffff
00693c:  ffff  dw      0xffff
00693e:  ffff  dw      0xffff
006940:  ffff  dw      0xffff
006942:  ffff  dw      0xffff
006944:  ffff  dw      0xffff
006946:  ffff  dw      0xffff
006948:  ffff  dw      0xffff
00694a:  ffff  dw      0xffff
00694c:  ffff  dw      0xffff
00694e:  ffff  dw      0xffff
006950:  ffff  dw      0xffff
006952:  ffff  dw      0xffff
006954:  ffff  dw      0xffff
006956:  ffff  dw      0xffff
006958:  ffff  dw      0xffff
00695a:  ffff  dw      0xffff
00695c:  ffff  dw      0xffff
00695e:  ffff  dw      0xffff
006960:  ffff  dw      0xffff
006962:  ffff  dw      0xffff
006964:  ffff  dw      0xffff
006966:  ffff  dw      0xffff
006968:  ffff  dw      0xffff
00696a:  ffff  dw      0xffff
00696c:  ffff  dw      0xffff
00696e:  ffff  dw      0xffff
006970:  ffff  dw      0xffff
006972:  ffff  dw      0xffff
006974:  ffff  dw      0xffff
006976:  ffff  dw      0xffff
006978:  ffff  dw      0xffff
00697a:  ffff  dw      0xffff
00697c:  ffff  dw      0xffff
00697e:  ffff  dw      0xffff
006980:  ffff  dw      0xffff
006982:  ffff  dw      0xffff
006984:  ffff  dw      0xffff
006986:  ffff  dw      0xffff
006988:  ffff  dw      0xffff
00698a:  ffff  dw      0xffff
00698c:  ffff  dw      0xffff
00698e:  ffff  dw      0xffff
006990:  ffff  dw      0xffff
006992:  ffff  dw      0xffff
006994:  ffff  dw      0xffff
006996:  ffff  dw      0xffff
006998:  ffff  dw      0xffff
00699a:  ffff  dw      0xffff
00699c:  ffff  dw      0xffff
00699e:  ffff  dw      0xffff
0069a0:  ffff  dw      0xffff
0069a2:  ffff  dw      0xffff
0069a4:  ffff  dw      0xffff
0069a6:  ffff  dw      0xffff
0069a8:  ffff  dw      0xffff
0069aa:  ffff  dw      0xffff
0069ac:  ffff  dw      0xffff
0069ae:  ffff  dw      0xffff
0069b0:  ffff  dw      0xffff
0069b2:  ffff  dw      0xffff
0069b4:  ffff  dw      0xffff
0069b6:  ffff  dw      0xffff
0069b8:  ffff  dw      0xffff
0069ba:  ffff  dw      0xffff
0069bc:  ffff  dw      0xffff
0069be:  ffff  dw      0xffff
0069c0:  ffff  dw      0xffff
0069c2:  ffff  dw      0xffff
0069c4:  ffff  dw      0xffff
0069c6:  ffff  dw      0xffff
0069c8:  ffff  dw      0xffff
0069ca:  ffff  dw      0xffff
0069cc:  ffff  dw      0xffff
0069ce:  ffff  dw      0xffff
0069d0:  ffff  dw      0xffff
0069d2:  ffff  dw      0xffff
0069d4:  ffff  dw      0xffff
0069d6:  ffff  dw      0xffff
0069d8:  ffff  dw      0xffff
0069da:  ffff  dw      0xffff
0069dc:  ffff  dw      0xffff
0069de:  ffff  dw      0xffff
0069e0:  ffff  dw      0xffff
0069e2:  ffff  dw      0xffff
0069e4:  ffff  dw      0xffff
0069e6:  ffff  dw      0xffff
0069e8:  ffff  dw      0xffff
0069ea:  ffff  dw      0xffff
0069ec:  ffff  dw      0xffff
0069ee:  ffff  dw      0xffff
0069f0:  ffff  dw      0xffff
0069f2:  ffff  dw      0xffff
0069f4:  ffff  dw      0xffff
0069f6:  ffff  dw      0xffff
0069f8:  ffff  dw      0xffff
0069fa:  ffff  dw      0xffff
0069fc:  ffff  dw      0xffff
0069fe:  ffff  dw      0xffff
006a00:  ffff  dw      0xffff
006a02:  ffff  dw      0xffff
006a04:  ffff  dw      0xffff
006a06:  ffff  dw      0xffff
006a08:  ffff  dw      0xffff
006a0a:  ffff  dw      0xffff
006a0c:  ffff  dw      0xffff
006a0e:  ffff  dw      0xffff
006a10:  ffff  dw      0xffff
006a12:  ffff  dw      0xffff
006a14:  ffff  dw      0xffff
006a16:  ffff  dw      0xffff
006a18:  ffff  dw      0xffff
006a1a:  ffff  dw      0xffff
006a1c:  ffff  dw      0xffff
006a1e:  ffff  dw      0xffff
006a20:  ffff  dw      0xffff
006a22:  ffff  dw      0xffff
006a24:  ffff  dw      0xffff
006a26:  ffff  dw      0xffff
006a28:  ffff  dw      0xffff
006a2a:  ffff  dw      0xffff
006a2c:  ffff  dw      0xffff
006a2e:  ffff  dw      0xffff
006a30:  ffff  dw      0xffff
006a32:  ffff  dw      0xffff
006a34:  ffff  dw      0xffff
006a36:  ffff  dw      0xffff
006a38:  ffff  dw      0xffff
006a3a:  ffff  dw      0xffff
006a3c:  ffff  dw      0xffff
006a3e:  ffff  dw      0xffff
006a40:  ffff  dw      0xffff
006a42:  ffff  dw      0xffff
006a44:  ffff  dw      0xffff
006a46:  ffff  dw      0xffff
006a48:  ffff  dw      0xffff
006a4a:  ffff  dw      0xffff
006a4c:  ffff  dw      0xffff
006a4e:  ffff  dw      0xffff
006a50:  ffff  dw      0xffff
006a52:  ffff  dw      0xffff
006a54:  ffff  dw      0xffff
006a56:  ffff  dw      0xffff
006a58:  ffff  dw      0xffff
006a5a:  ffff  dw      0xffff
006a5c:  ffff  dw      0xffff
006a5e:  ffff  dw      0xffff
006a60:  ffff  dw      0xffff
006a62:  ffff  dw      0xffff
006a64:  ffff  dw      0xffff
006a66:  ffff  dw      0xffff
006a68:  ffff  dw      0xffff
006a6a:  ffff  dw      0xffff
006a6c:  ffff  dw      0xffff
006a6e:  ffff  dw      0xffff
006a70:  ffff  dw      0xffff
006a72:  ffff  dw      0xffff
006a74:  ffff  dw      0xffff
006a76:  ffff  dw      0xffff
006a78:  ffff  dw      0xffff
006a7a:  ffff  dw      0xffff
006a7c:  ffff  dw      0xffff
006a7e:  ffff  dw      0xffff
006a80:  ffff  dw      0xffff
006a82:  ffff  dw      0xffff
006a84:  ffff  dw      0xffff
006a86:  ffff  dw      0xffff
006a88:  ffff  dw      0xffff
006a8a:  ffff  dw      0xffff
006a8c:  ffff  dw      0xffff
006a8e:  ffff  dw      0xffff
006a90:  ffff  dw      0xffff
006a92:  ffff  dw      0xffff
006a94:  ffff  dw      0xffff
006a96:  ffff  dw      0xffff
006a98:  ffff  dw      0xffff
006a9a:  ffff  dw      0xffff
006a9c:  ffff  dw      0xffff
006a9e:  ffff  dw      0xffff
006aa0:  ffff  dw      0xffff
006aa2:  ffff  dw      0xffff
006aa4:  ffff  dw      0xffff
006aa6:  ffff  dw      0xffff
006aa8:  ffff  dw      0xffff
006aaa:  ffff  dw      0xffff
006aac:  ffff  dw      0xffff
006aae:  ffff  dw      0xffff
006ab0:  ffff  dw      0xffff
006ab2:  ffff  dw      0xffff
006ab4:  ffff  dw      0xffff
006ab6:  ffff  dw      0xffff
006ab8:  ffff  dw      0xffff
006aba:  ffff  dw      0xffff
006abc:  ffff  dw      0xffff
006abe:  ffff  dw      0xffff
006ac0:  ffff  dw      0xffff
006ac2:  ffff  dw      0xffff
006ac4:  ffff  dw      0xffff
006ac6:  ffff  dw      0xffff
006ac8:  ffff  dw      0xffff
006aca:  ffff  dw      0xffff
006acc:  ffff  dw      0xffff
006ace:  ffff  dw      0xffff
006ad0:  ffff  dw      0xffff
006ad2:  ffff  dw      0xffff
006ad4:  ffff  dw      0xffff
006ad6:  ffff  dw      0xffff
006ad8:  ffff  dw      0xffff
006ada:  ffff  dw      0xffff
006adc:  ffff  dw      0xffff
006ade:  ffff  dw      0xffff
006ae0:  ffff  dw      0xffff
006ae2:  ffff  dw      0xffff
006ae4:  ffff  dw      0xffff
006ae6:  ffff  dw      0xffff
006ae8:  ffff  dw      0xffff
006aea:  ffff  dw      0xffff
006aec:  ffff  dw      0xffff
006aee:  ffff  dw      0xffff
006af0:  ffff  dw      0xffff
006af2:  ffff  dw      0xffff
006af4:  ffff  dw      0xffff
006af6:  ffff  dw      0xffff
006af8:  ffff  dw      0xffff
006afa:  ffff  dw      0xffff
006afc:  ffff  dw      0xffff
006afe:  ffff  dw      0xffff
006b00:  ffff  dw      0xffff
006b02:  ffff  dw      0xffff
006b04:  ffff  dw      0xffff
006b06:  ffff  dw      0xffff
006b08:  ffff  dw      0xffff
006b0a:  ffff  dw      0xffff
006b0c:  ffff  dw      0xffff
006b0e:  ffff  dw      0xffff
006b10:  ffff  dw      0xffff
006b12:  ffff  dw      0xffff
006b14:  ffff  dw      0xffff
006b16:  ffff  dw      0xffff
006b18:  ffff  dw      0xffff
006b1a:  ffff  dw      0xffff
006b1c:  ffff  dw      0xffff
006b1e:  ffff  dw      0xffff
006b20:  ffff  dw      0xffff
006b22:  ffff  dw      0xffff
006b24:  ffff  dw      0xffff
006b26:  ffff  dw      0xffff
006b28:  ffff  dw      0xffff
006b2a:  ffff  dw      0xffff
006b2c:  ffff  dw      0xffff
006b2e:  ffff  dw      0xffff
006b30:  ffff  dw      0xffff
006b32:  ffff  dw      0xffff
006b34:  ffff  dw      0xffff
006b36:  ffff  dw      0xffff
006b38:  ffff  dw      0xffff
006b3a:  ffff  dw      0xffff
006b3c:  ffff  dw      0xffff
006b3e:  ffff  dw      0xffff
006b40:  ffff  dw      0xffff
006b42:  ffff  dw      0xffff
006b44:  ffff  dw      0xffff
006b46:  ffff  dw      0xffff
006b48:  ffff  dw      0xffff
006b4a:  ffff  dw      0xffff
006b4c:  ffff  dw      0xffff
006b4e:  ffff  dw      0xffff
006b50:  ffff  dw      0xffff
006b52:  ffff  dw      0xffff
006b54:  ffff  dw      0xffff
006b56:  ffff  dw      0xffff
006b58:  ffff  dw      0xffff
006b5a:  ffff  dw      0xffff
006b5c:  ffff  dw      0xffff
006b5e:  ffff  dw      0xffff
006b60:  ffff  dw      0xffff
006b62:  ffff  dw      0xffff
006b64:  ffff  dw      0xffff
006b66:  ffff  dw      0xffff
006b68:  ffff  dw      0xffff
006b6a:  ffff  dw      0xffff
006b6c:  ffff  dw      0xffff
006b6e:  ffff  dw      0xffff
006b70:  ffff  dw      0xffff
006b72:  ffff  dw      0xffff
006b74:  ffff  dw      0xffff
006b76:  ffff  dw      0xffff
006b78:  ffff  dw      0xffff
006b7a:  ffff  dw      0xffff
006b7c:  ffff  dw      0xffff
006b7e:  ffff  dw      0xffff
006b80:  ffff  dw      0xffff
006b82:  ffff  dw      0xffff
006b84:  ffff  dw      0xffff
006b86:  ffff  dw      0xffff
006b88:  ffff  dw      0xffff
006b8a:  ffff  dw      0xffff
006b8c:  ffff  dw      0xffff
006b8e:  ffff  dw      0xffff
006b90:  ffff  dw      0xffff
006b92:  ffff  dw      0xffff
006b94:  ffff  dw      0xffff
006b96:  ffff  dw      0xffff
006b98:  ffff  dw      0xffff
006b9a:  ffff  dw      0xffff
006b9c:  ffff  dw      0xffff
006b9e:  ffff  dw      0xffff
006ba0:  ffff  dw      0xffff
006ba2:  ffff  dw      0xffff
006ba4:  ffff  dw      0xffff
006ba6:  ffff  dw      0xffff
006ba8:  ffff  dw      0xffff
006baa:  ffff  dw      0xffff
006bac:  ffff  dw      0xffff
006bae:  ffff  dw      0xffff
006bb0:  ffff  dw      0xffff
006bb2:  ffff  dw      0xffff
006bb4:  ffff  dw      0xffff
006bb6:  ffff  dw      0xffff
006bb8:  ffff  dw      0xffff
006bba:  ffff  dw      0xffff
006bbc:  ffff  dw      0xffff
006bbe:  ffff  dw      0xffff
006bc0:  ffff  dw      0xffff
006bc2:  ffff  dw      0xffff
006bc4:  ffff  dw      0xffff
006bc6:  ffff  dw      0xffff
006bc8:  ffff  dw      0xffff
006bca:  ffff  dw      0xffff
006bcc:  ffff  dw      0xffff
006bce:  ffff  dw      0xffff
006bd0:  ffff  dw      0xffff
006bd2:  ffff  dw      0xffff
006bd4:  ffff  dw      0xffff
006bd6:  ffff  dw      0xffff
006bd8:  ffff  dw      0xffff
006bda:  ffff  dw      0xffff
006bdc:  ffff  dw      0xffff
006bde:  ffff  dw      0xffff
006be0:  ffff  dw      0xffff
006be2:  ffff  dw      0xffff
006be4:  ffff  dw      0xffff
006be6:  ffff  dw      0xffff
006be8:  ffff  dw      0xffff
006bea:  ffff  dw      0xffff
006bec:  ffff  dw      0xffff
006bee:  ffff  dw      0xffff
006bf0:  ffff  dw      0xffff
006bf2:  ffff  dw      0xffff
006bf4:  ffff  dw      0xffff
006bf6:  ffff  dw      0xffff
006bf8:  ffff  dw      0xffff
006bfa:  ffff  dw      0xffff
006bfc:  ffff  dw      0xffff
006bfe:  ffff  dw      0xffff
006c00:  ffff  dw      0xffff
006c02:  ffff  dw      0xffff
006c04:  ffff  dw      0xffff
006c06:  ffff  dw      0xffff
006c08:  ffff  dw      0xffff
006c0a:  ffff  dw      0xffff
006c0c:  ffff  dw      0xffff
006c0e:  ffff  dw      0xffff
006c10:  ffff  dw      0xffff
006c12:  ffff  dw      0xffff
006c14:  ffff  dw      0xffff
006c16:  ffff  dw      0xffff
006c18:  ffff  dw      0xffff
006c1a:  ffff  dw      0xffff
006c1c:  ffff  dw      0xffff
006c1e:  ffff  dw      0xffff
006c20:  ffff  dw      0xffff
006c22:  ffff  dw      0xffff
006c24:  ffff  dw      0xffff
006c26:  ffff  dw      0xffff
006c28:  ffff  dw      0xffff
006c2a:  ffff  dw      0xffff
006c2c:  ffff  dw      0xffff
006c2e:  ffff  dw      0xffff
006c30:  ffff  dw      0xffff
006c32:  ffff  dw      0xffff
006c34:  ffff  dw      0xffff
006c36:  ffff  dw      0xffff
006c38:  ffff  dw      0xffff
006c3a:  ffff  dw      0xffff
006c3c:  ffff  dw      0xffff
006c3e:  ffff  dw      0xffff
006c40:  ffff  dw      0xffff
006c42:  ffff  dw      0xffff
006c44:  ffff  dw      0xffff
006c46:  ffff  dw      0xffff
006c48:  ffff  dw      0xffff
006c4a:  ffff  dw      0xffff
006c4c:  ffff  dw      0xffff
006c4e:  ffff  dw      0xffff
006c50:  ffff  dw      0xffff
006c52:  ffff  dw      0xffff
006c54:  ffff  dw      0xffff
006c56:  ffff  dw      0xffff
006c58:  ffff  dw      0xffff
006c5a:  ffff  dw      0xffff
006c5c:  ffff  dw      0xffff
006c5e:  ffff  dw      0xffff
006c60:  ffff  dw      0xffff
006c62:  ffff  dw      0xffff
006c64:  ffff  dw      0xffff
006c66:  ffff  dw      0xffff
006c68:  ffff  dw      0xffff
006c6a:  ffff  dw      0xffff
006c6c:  ffff  dw      0xffff
006c6e:  ffff  dw      0xffff
006c70:  ffff  dw      0xffff
006c72:  ffff  dw      0xffff
006c74:  ffff  dw      0xffff
006c76:  ffff  dw      0xffff
006c78:  ffff  dw      0xffff
006c7a:  ffff  dw      0xffff
006c7c:  ffff  dw      0xffff
006c7e:  ffff  dw      0xffff
006c80:  ffff  dw      0xffff
006c82:  ffff  dw      0xffff
006c84:  ffff  dw      0xffff
006c86:  ffff  dw      0xffff
006c88:  ffff  dw      0xffff
006c8a:  ffff  dw      0xffff
006c8c:  ffff  dw      0xffff
006c8e:  ffff  dw      0xffff
006c90:  ffff  dw      0xffff
006c92:  ffff  dw      0xffff
006c94:  ffff  dw      0xffff
006c96:  ffff  dw      0xffff
006c98:  ffff  dw      0xffff
006c9a:  ffff  dw      0xffff
006c9c:  ffff  dw      0xffff
006c9e:  ffff  dw      0xffff
006ca0:  ffff  dw      0xffff
006ca2:  ffff  dw      0xffff
006ca4:  ffff  dw      0xffff
006ca6:  ffff  dw      0xffff
006ca8:  ffff  dw      0xffff
006caa:  ffff  dw      0xffff
006cac:  ffff  dw      0xffff
006cae:  ffff  dw      0xffff
006cb0:  ffff  dw      0xffff
006cb2:  ffff  dw      0xffff
006cb4:  ffff  dw      0xffff
006cb6:  ffff  dw      0xffff
006cb8:  ffff  dw      0xffff
006cba:  ffff  dw      0xffff
006cbc:  ffff  dw      0xffff
006cbe:  ffff  dw      0xffff
006cc0:  ffff  dw      0xffff
006cc2:  ffff  dw      0xffff
006cc4:  ffff  dw      0xffff
006cc6:  ffff  dw      0xffff
006cc8:  ffff  dw      0xffff
006cca:  ffff  dw      0xffff
006ccc:  ffff  dw      0xffff
006cce:  ffff  dw      0xffff
006cd0:  ffff  dw      0xffff
006cd2:  ffff  dw      0xffff
006cd4:  ffff  dw      0xffff
006cd6:  ffff  dw      0xffff
006cd8:  ffff  dw      0xffff
006cda:  ffff  dw      0xffff
006cdc:  ffff  dw      0xffff
006cde:  ffff  dw      0xffff
006ce0:  ffff  dw      0xffff
006ce2:  ffff  dw      0xffff
006ce4:  ffff  dw      0xffff
006ce6:  ffff  dw      0xffff
006ce8:  ffff  dw      0xffff
006cea:  ffff  dw      0xffff
006cec:  ffff  dw      0xffff
006cee:  ffff  dw      0xffff
006cf0:  ffff  dw      0xffff
006cf2:  ffff  dw      0xffff
006cf4:  ffff  dw      0xffff
006cf6:  ffff  dw      0xffff
006cf8:  ffff  dw      0xffff
006cfa:  ffff  dw      0xffff
006cfc:  ffff  dw      0xffff
006cfe:  ffff  dw      0xffff
006d00:  ffff  dw      0xffff
006d02:  ffff  dw      0xffff
006d04:  ffff  dw      0xffff
006d06:  ffff  dw      0xffff
006d08:  ffff  dw      0xffff
006d0a:  ffff  dw      0xffff
006d0c:  ffff  dw      0xffff
006d0e:  ffff  dw      0xffff
006d10:  ffff  dw      0xffff
006d12:  ffff  dw      0xffff
006d14:  ffff  dw      0xffff
006d16:  ffff  dw      0xffff
006d18:  ffff  dw      0xffff
006d1a:  ffff  dw      0xffff
006d1c:  ffff  dw      0xffff
006d1e:  ffff  dw      0xffff
006d20:  ffff  dw      0xffff
006d22:  ffff  dw      0xffff
006d24:  ffff  dw      0xffff
006d26:  ffff  dw      0xffff
006d28:  ffff  dw      0xffff
006d2a:  ffff  dw      0xffff
006d2c:  ffff  dw      0xffff
006d2e:  ffff  dw      0xffff
006d30:  ffff  dw      0xffff
006d32:  ffff  dw      0xffff
006d34:  ffff  dw      0xffff
006d36:  ffff  dw      0xffff
006d38:  ffff  dw      0xffff
006d3a:  ffff  dw      0xffff
006d3c:  ffff  dw      0xffff
006d3e:  ffff  dw      0xffff
006d40:  ffff  dw      0xffff
006d42:  ffff  dw      0xffff
006d44:  ffff  dw      0xffff
006d46:  ffff  dw      0xffff
006d48:  ffff  dw      0xffff
006d4a:  ffff  dw      0xffff
006d4c:  ffff  dw      0xffff
006d4e:  ffff  dw      0xffff
006d50:  ffff  dw      0xffff
006d52:  ffff  dw      0xffff
006d54:  ffff  dw      0xffff
006d56:  ffff  dw      0xffff
006d58:  ffff  dw      0xffff
006d5a:  ffff  dw      0xffff
006d5c:  ffff  dw      0xffff
006d5e:  ffff  dw      0xffff
006d60:  ffff  dw      0xffff
006d62:  ffff  dw      0xffff
006d64:  ffff  dw      0xffff
006d66:  ffff  dw      0xffff
006d68:  ffff  dw      0xffff
006d6a:  ffff  dw      0xffff
006d6c:  ffff  dw      0xffff
006d6e:  ffff  dw      0xffff
006d70:  ffff  dw      0xffff
006d72:  ffff  dw      0xffff
006d74:  ffff  dw      0xffff
006d76:  ffff  dw      0xffff
006d78:  ffff  dw      0xffff
006d7a:  ffff  dw      0xffff
006d7c:  ffff  dw      0xffff
006d7e:  ffff  dw      0xffff
006d80:  ffff  dw      0xffff
006d82:  ffff  dw      0xffff
006d84:  ffff  dw      0xffff
006d86:  ffff  dw      0xffff
006d88:  ffff  dw      0xffff
006d8a:  ffff  dw      0xffff
006d8c:  ffff  dw      0xffff
006d8e:  ffff  dw      0xffff
006d90:  ffff  dw      0xffff
006d92:  ffff  dw      0xffff
006d94:  ffff  dw      0xffff
006d96:  ffff  dw      0xffff
006d98:  ffff  dw      0xffff
006d9a:  ffff  dw      0xffff
006d9c:  ffff  dw      0xffff
006d9e:  ffff  dw      0xffff
006da0:  ffff  dw      0xffff
006da2:  ffff  dw      0xffff
006da4:  ffff  dw      0xffff
006da6:  ffff  dw      0xffff
006da8:  ffff  dw      0xffff
006daa:  ffff  dw      0xffff
006dac:  ffff  dw      0xffff
006dae:  ffff  dw      0xffff
006db0:  ffff  dw      0xffff
006db2:  ffff  dw      0xffff
006db4:  ffff  dw      0xffff
006db6:  ffff  dw      0xffff
006db8:  ffff  dw      0xffff
006dba:  ffff  dw      0xffff
006dbc:  ffff  dw      0xffff
006dbe:  ffff  dw      0xffff
006dc0:  ffff  dw      0xffff
006dc2:  ffff  dw      0xffff
006dc4:  ffff  dw      0xffff
006dc6:  ffff  dw      0xffff
006dc8:  ffff  dw      0xffff
006dca:  ffff  dw      0xffff
006dcc:  ffff  dw      0xffff
006dce:  ffff  dw      0xffff
006dd0:  ffff  dw      0xffff
006dd2:  ffff  dw      0xffff
006dd4:  ffff  dw      0xffff
006dd6:  ffff  dw      0xffff
006dd8:  ffff  dw      0xffff
006dda:  ffff  dw      0xffff
006ddc:  ffff  dw      0xffff
006dde:  ffff  dw      0xffff
006de0:  ffff  dw      0xffff
006de2:  ffff  dw      0xffff
006de4:  ffff  dw      0xffff
006de6:  ffff  dw      0xffff
006de8:  ffff  dw      0xffff
006dea:  ffff  dw      0xffff
006dec:  ffff  dw      0xffff
006dee:  ffff  dw      0xffff
006df0:  ffff  dw      0xffff
006df2:  ffff  dw      0xffff
006df4:  ffff  dw      0xffff
006df6:  ffff  dw      0xffff
006df8:  ffff  dw      0xffff
006dfa:  ffff  dw      0xffff
006dfc:  ffff  dw      0xffff
006dfe:  ffff  dw      0xffff
006e00:  ffff  dw      0xffff
006e02:  ffff  dw      0xffff
006e04:  ffff  dw      0xffff
006e06:  ffff  dw      0xffff
006e08:  ffff  dw      0xffff
006e0a:  ffff  dw      0xffff
006e0c:  ffff  dw      0xffff
006e0e:  ffff  dw      0xffff
006e10:  ffff  dw      0xffff
006e12:  ffff  dw      0xffff
006e14:  ffff  dw      0xffff
006e16:  ffff  dw      0xffff
006e18:  ffff  dw      0xffff
006e1a:  ffff  dw      0xffff
006e1c:  ffff  dw      0xffff
006e1e:  ffff  dw      0xffff
006e20:  ffff  dw      0xffff
006e22:  ffff  dw      0xffff
006e24:  ffff  dw      0xffff
006e26:  ffff  dw      0xffff
006e28:  ffff  dw      0xffff
006e2a:  ffff  dw      0xffff
006e2c:  ffff  dw      0xffff
006e2e:  ffff  dw      0xffff
006e30:  ffff  dw      0xffff
006e32:  ffff  dw      0xffff
006e34:  ffff  dw      0xffff
006e36:  ffff  dw      0xffff
006e38:  ffff  dw      0xffff
006e3a:  ffff  dw      0xffff
006e3c:  ffff  dw      0xffff
006e3e:  ffff  dw      0xffff
006e40:  ffff  dw      0xffff
006e42:  ffff  dw      0xffff
006e44:  ffff  dw      0xffff
006e46:  ffff  dw      0xffff
006e48:  ffff  dw      0xffff
006e4a:  ffff  dw      0xffff
006e4c:  ffff  dw      0xffff
006e4e:  ffff  dw      0xffff
006e50:  ffff  dw      0xffff
006e52:  ffff  dw      0xffff
006e54:  ffff  dw      0xffff
006e56:  ffff  dw      0xffff
006e58:  ffff  dw      0xffff
006e5a:  ffff  dw      0xffff
006e5c:  ffff  dw      0xffff
006e5e:  ffff  dw      0xffff
006e60:  ffff  dw      0xffff
006e62:  ffff  dw      0xffff
006e64:  ffff  dw      0xffff
006e66:  ffff  dw      0xffff
006e68:  ffff  dw      0xffff
006e6a:  ffff  dw      0xffff
006e6c:  ffff  dw      0xffff
006e6e:  ffff  dw      0xffff
006e70:  ffff  dw      0xffff
006e72:  ffff  dw      0xffff
006e74:  ffff  dw      0xffff
006e76:  ffff  dw      0xffff
006e78:  ffff  dw      0xffff
006e7a:  ffff  dw      0xffff
006e7c:  ffff  dw      0xffff
006e7e:  ffff  dw      0xffff
006e80:  ffff  dw      0xffff
006e82:  ffff  dw      0xffff
006e84:  ffff  dw      0xffff
006e86:  ffff  dw      0xffff
006e88:  ffff  dw      0xffff
006e8a:  ffff  dw      0xffff
006e8c:  ffff  dw      0xffff
006e8e:  ffff  dw      0xffff
006e90:  ffff  dw      0xffff
006e92:  ffff  dw      0xffff
006e94:  ffff  dw      0xffff
006e96:  ffff  dw      0xffff
006e98:  ffff  dw      0xffff
006e9a:  ffff  dw      0xffff
006e9c:  ffff  dw      0xffff
006e9e:  ffff  dw      0xffff
006ea0:  ffff  dw      0xffff
006ea2:  ffff  dw      0xffff
006ea4:  ffff  dw      0xffff
006ea6:  ffff  dw      0xffff
006ea8:  ffff  dw      0xffff
006eaa:  ffff  dw      0xffff
006eac:  ffff  dw      0xffff
006eae:  ffff  dw      0xffff
006eb0:  ffff  dw      0xffff
006eb2:  ffff  dw      0xffff
006eb4:  ffff  dw      0xffff
006eb6:  ffff  dw      0xffff
006eb8:  ffff  dw      0xffff
006eba:  ffff  dw      0xffff
006ebc:  ffff  dw      0xffff
006ebe:  ffff  dw      0xffff
006ec0:  ffff  dw      0xffff
006ec2:  ffff  dw      0xffff
006ec4:  ffff  dw      0xffff
006ec6:  ffff  dw      0xffff
006ec8:  ffff  dw      0xffff
006eca:  ffff  dw      0xffff
006ecc:  ffff  dw      0xffff
006ece:  ffff  dw      0xffff
006ed0:  ffff  dw      0xffff
006ed2:  ffff  dw      0xffff
006ed4:  ffff  dw      0xffff
006ed6:  ffff  dw      0xffff
006ed8:  ffff  dw      0xffff
006eda:  ffff  dw      0xffff
006edc:  ffff  dw      0xffff
006ede:  ffff  dw      0xffff
006ee0:  ffff  dw      0xffff
006ee2:  ffff  dw      0xffff
006ee4:  ffff  dw      0xffff
006ee6:  ffff  dw      0xffff
006ee8:  ffff  dw      0xffff
006eea:  ffff  dw      0xffff
006eec:  ffff  dw      0xffff
006eee:  ffff  dw      0xffff
006ef0:  ffff  dw      0xffff
006ef2:  ffff  dw      0xffff
006ef4:  ffff  dw      0xffff
006ef6:  ffff  dw      0xffff
006ef8:  ffff  dw      0xffff
006efa:  ffff  dw      0xffff
006efc:  ffff  dw      0xffff
006efe:  ffff  dw      0xffff
006f00:  ffff  dw      0xffff
006f02:  ffff  dw      0xffff
006f04:  ffff  dw      0xffff
006f06:  ffff  dw      0xffff
006f08:  ffff  dw      0xffff
006f0a:  ffff  dw      0xffff
006f0c:  ffff  dw      0xffff
006f0e:  ffff  dw      0xffff
006f10:  ffff  dw      0xffff
006f12:  ffff  dw      0xffff
006f14:  ffff  dw      0xffff
006f16:  ffff  dw      0xffff
006f18:  ffff  dw      0xffff
006f1a:  ffff  dw      0xffff
006f1c:  ffff  dw      0xffff
006f1e:  ffff  dw      0xffff
006f20:  ffff  dw      0xffff
006f22:  ffff  dw      0xffff
006f24:  ffff  dw      0xffff
006f26:  ffff  dw      0xffff
006f28:  ffff  dw      0xffff
006f2a:  ffff  dw      0xffff
006f2c:  ffff  dw      0xffff
006f2e:  ffff  dw      0xffff
006f30:  ffff  dw      0xffff
006f32:  ffff  dw      0xffff
006f34:  ffff  dw      0xffff
006f36:  ffff  dw      0xffff
006f38:  ffff  dw      0xffff
006f3a:  ffff  dw      0xffff
006f3c:  ffff  dw      0xffff
006f3e:  ffff  dw      0xffff
006f40:  ffff  dw      0xffff
006f42:  ffff  dw      0xffff
006f44:  ffff  dw      0xffff
006f46:  ffff  dw      0xffff
006f48:  ffff  dw      0xffff
006f4a:  ffff  dw      0xffff
006f4c:  ffff  dw      0xffff
006f4e:  ffff  dw      0xffff
006f50:  ffff  dw      0xffff
006f52:  ffff  dw      0xffff
006f54:  ffff  dw      0xffff
006f56:  ffff  dw      0xffff
006f58:  ffff  dw      0xffff
006f5a:  ffff  dw      0xffff
006f5c:  ffff  dw      0xffff
006f5e:  ffff  dw      0xffff
006f60:  ffff  dw      0xffff
006f62:  ffff  dw      0xffff
006f64:  ffff  dw      0xffff
006f66:  ffff  dw      0xffff
006f68:  ffff  dw      0xffff
006f6a:  ffff  dw      0xffff
006f6c:  ffff  dw      0xffff
006f6e:  ffff  dw      0xffff
006f70:  ffff  dw      0xffff
006f72:  ffff  dw      0xffff
006f74:  ffff  dw      0xffff
006f76:  ffff  dw      0xffff
006f78:  ffff  dw      0xffff
006f7a:  ffff  dw      0xffff
006f7c:  ffff  dw      0xffff
006f7e:  ffff  dw      0xffff
006f80:  ffff  dw      0xffff
006f82:  ffff  dw      0xffff
006f84:  ffff  dw      0xffff
006f86:  ffff  dw      0xffff
006f88:  ffff  dw      0xffff
006f8a:  ffff  dw      0xffff
006f8c:  ffff  dw      0xffff
006f8e:  ffff  dw      0xffff
006f90:  ffff  dw      0xffff
006f92:  ffff  dw      0xffff
006f94:  ffff  dw      0xffff
006f96:  ffff  dw      0xffff
006f98:  ffff  dw      0xffff
006f9a:  ffff  dw      0xffff
006f9c:  ffff  dw      0xffff
006f9e:  ffff  dw      0xffff
006fa0:  ffff  dw      0xffff
006fa2:  ffff  dw      0xffff
006fa4:  ffff  dw      0xffff
006fa6:  ffff  dw      0xffff
006fa8:  ffff  dw      0xffff
006faa:  ffff  dw      0xffff
006fac:  ffff  dw      0xffff
006fae:  ffff  dw      0xffff
006fb0:  ffff  dw      0xffff
006fb2:  ffff  dw      0xffff
006fb4:  ffff  dw      0xffff
006fb6:  ffff  dw      0xffff
006fb8:  ffff  dw      0xffff
006fba:  ffff  dw      0xffff
006fbc:  ffff  dw      0xffff
006fbe:  ffff  dw      0xffff
006fc0:  ffff  dw      0xffff
006fc2:  ffff  dw      0xffff
006fc4:  ffff  dw      0xffff
006fc6:  ffff  dw      0xffff
006fc8:  ffff  dw      0xffff
006fca:  ffff  dw      0xffff
006fcc:  ffff  dw      0xffff
006fce:  ffff  dw      0xffff
006fd0:  ffff  dw      0xffff
006fd2:  ffff  dw      0xffff
006fd4:  ffff  dw      0xffff
006fd6:  ffff  dw      0xffff
006fd8:  ffff  dw      0xffff
006fda:  ffff  dw      0xffff
006fdc:  ffff  dw      0xffff
006fde:  ffff  dw      0xffff
006fe0:  ffff  dw      0xffff
006fe2:  ffff  dw      0xffff
006fe4:  ffff  dw      0xffff
006fe6:  ffff  dw      0xffff
006fe8:  ffff  dw      0xffff
006fea:  ffff  dw      0xffff
006fec:  ffff  dw      0xffff
006fee:  ffff  dw      0xffff
006ff0:  ffff  dw      0xffff
006ff2:  ffff  dw      0xffff
006ff4:  ffff  dw      0xffff
006ff6:  ffff  dw      0xffff
006ff8:  ffff  dw      0xffff
006ffa:  ffff  dw      0xffff
006ffc:  ffff  dw      0xffff
006ffe:  ffff  dw      0xffff
007000:  ffff  dw      0xffff
007002:  ffff  dw      0xffff
007004:  ffff  dw      0xffff
007006:  ffff  dw      0xffff
007008:  ffff  dw      0xffff
00700a:  ffff  dw      0xffff
00700c:  ffff  dw      0xffff
00700e:  ffff  dw      0xffff
007010:  ffff  dw      0xffff
007012:  ffff  dw      0xffff
007014:  ffff  dw      0xffff
007016:  ffff  dw      0xffff
007018:  ffff  dw      0xffff
00701a:  ffff  dw      0xffff
00701c:  ffff  dw      0xffff
00701e:  ffff  dw      0xffff
007020:  ffff  dw      0xffff
007022:  ffff  dw      0xffff
007024:  ffff  dw      0xffff
007026:  ffff  dw      0xffff
007028:  ffff  dw      0xffff
00702a:  ffff  dw      0xffff
00702c:  ffff  dw      0xffff
00702e:  ffff  dw      0xffff
007030:  ffff  dw      0xffff
007032:  ffff  dw      0xffff
007034:  ffff  dw      0xffff
007036:  ffff  dw      0xffff
007038:  ffff  dw      0xffff
00703a:  ffff  dw      0xffff
00703c:  ffff  dw      0xffff
00703e:  ffff  dw      0xffff
007040:  ffff  dw      0xffff
007042:  ffff  dw      0xffff
007044:  ffff  dw      0xffff
007046:  ffff  dw      0xffff
007048:  ffff  dw      0xffff
00704a:  ffff  dw      0xffff
00704c:  ffff  dw      0xffff
00704e:  ffff  dw      0xffff
007050:  ffff  dw      0xffff
007052:  ffff  dw      0xffff
007054:  ffff  dw      0xffff
007056:  ffff  dw      0xffff
007058:  ffff  dw      0xffff
00705a:  ffff  dw      0xffff
00705c:  ffff  dw      0xffff
00705e:  ffff  dw      0xffff
007060:  ffff  dw      0xffff
007062:  ffff  dw      0xffff
007064:  ffff  dw      0xffff
007066:  ffff  dw      0xffff
007068:  ffff  dw      0xffff
00706a:  ffff  dw      0xffff
00706c:  ffff  dw      0xffff
00706e:  ffff  dw      0xffff
007070:  ffff  dw      0xffff
007072:  ffff  dw      0xffff
007074:  ffff  dw      0xffff
007076:  ffff  dw      0xffff
007078:  ffff  dw      0xffff
00707a:  ffff  dw      0xffff
00707c:  ffff  dw      0xffff
00707e:  ffff  dw      0xffff
007080:  ffff  dw      0xffff
007082:  ffff  dw      0xffff
007084:  ffff  dw      0xffff
007086:  ffff  dw      0xffff
007088:  ffff  dw      0xffff
00708a:  ffff  dw      0xffff
00708c:  ffff  dw      0xffff
00708e:  ffff  dw      0xffff
007090:  ffff  dw      0xffff
007092:  ffff  dw      0xffff
007094:  ffff  dw      0xffff
007096:  ffff  dw      0xffff
007098:  ffff  dw      0xffff
00709a:  ffff  dw      0xffff
00709c:  ffff  dw      0xffff
00709e:  ffff  dw      0xffff
0070a0:  ffff  dw      0xffff
0070a2:  ffff  dw      0xffff
0070a4:  ffff  dw      0xffff
0070a6:  ffff  dw      0xffff
0070a8:  ffff  dw      0xffff
0070aa:  ffff  dw      0xffff
0070ac:  ffff  dw      0xffff
0070ae:  ffff  dw      0xffff
0070b0:  ffff  dw      0xffff
0070b2:  ffff  dw      0xffff
0070b4:  ffff  dw      0xffff
0070b6:  ffff  dw      0xffff
0070b8:  ffff  dw      0xffff
0070ba:  ffff  dw      0xffff
0070bc:  ffff  dw      0xffff
0070be:  ffff  dw      0xffff
0070c0:  ffff  dw      0xffff
0070c2:  ffff  dw      0xffff
0070c4:  ffff  dw      0xffff
0070c6:  ffff  dw      0xffff
0070c8:  ffff  dw      0xffff
0070ca:  ffff  dw      0xffff
0070cc:  ffff  dw      0xffff
0070ce:  ffff  dw      0xffff
0070d0:  ffff  dw      0xffff
0070d2:  ffff  dw      0xffff
0070d4:  ffff  dw      0xffff
0070d6:  ffff  dw      0xffff
0070d8:  ffff  dw      0xffff
0070da:  ffff  dw      0xffff
0070dc:  ffff  dw      0xffff
0070de:  ffff  dw      0xffff
0070e0:  ffff  dw      0xffff
0070e2:  ffff  dw      0xffff
0070e4:  ffff  dw      0xffff
0070e6:  ffff  dw      0xffff
0070e8:  ffff  dw      0xffff
0070ea:  ffff  dw      0xffff
0070ec:  ffff  dw      0xffff
0070ee:  ffff  dw      0xffff
0070f0:  ffff  dw      0xffff
0070f2:  ffff  dw      0xffff
0070f4:  ffff  dw      0xffff
0070f6:  ffff  dw      0xffff
0070f8:  ffff  dw      0xffff
0070fa:  ffff  dw      0xffff
0070fc:  ffff  dw      0xffff
0070fe:  ffff  dw      0xffff
007100:  ffff  dw      0xffff
007102:  ffff  dw      0xffff
007104:  ffff  dw      0xffff
007106:  ffff  dw      0xffff
007108:  ffff  dw      0xffff
00710a:  ffff  dw      0xffff
00710c:  ffff  dw      0xffff
00710e:  ffff  dw      0xffff
007110:  ffff  dw      0xffff
007112:  ffff  dw      0xffff
007114:  ffff  dw      0xffff
007116:  ffff  dw      0xffff
007118:  ffff  dw      0xffff
00711a:  ffff  dw      0xffff
00711c:  ffff  dw      0xffff
00711e:  ffff  dw      0xffff
007120:  ffff  dw      0xffff
007122:  ffff  dw      0xffff
007124:  ffff  dw      0xffff
007126:  ffff  dw      0xffff
007128:  ffff  dw      0xffff
00712a:  ffff  dw      0xffff
00712c:  ffff  dw      0xffff
00712e:  ffff  dw      0xffff
007130:  ffff  dw      0xffff
007132:  ffff  dw      0xffff
007134:  ffff  dw      0xffff
007136:  ffff  dw      0xffff
007138:  ffff  dw      0xffff
00713a:  ffff  dw      0xffff
00713c:  ffff  dw      0xffff
00713e:  ffff  dw      0xffff
007140:  ffff  dw      0xffff
007142:  ffff  dw      0xffff
007144:  ffff  dw      0xffff
007146:  ffff  dw      0xffff
007148:  ffff  dw      0xffff
00714a:  ffff  dw      0xffff
00714c:  ffff  dw      0xffff
00714e:  ffff  dw      0xffff
007150:  ffff  dw      0xffff
007152:  ffff  dw      0xffff
007154:  ffff  dw      0xffff
007156:  ffff  dw      0xffff
007158:  ffff  dw      0xffff
00715a:  ffff  dw      0xffff
00715c:  ffff  dw      0xffff
00715e:  ffff  dw      0xffff
007160:  ffff  dw      0xffff
007162:  ffff  dw      0xffff
007164:  ffff  dw      0xffff
007166:  ffff  dw      0xffff
007168:  ffff  dw      0xffff
00716a:  ffff  dw      0xffff
00716c:  ffff  dw      0xffff
00716e:  ffff  dw      0xffff
007170:  ffff  dw      0xffff
007172:  ffff  dw      0xffff
007174:  ffff  dw      0xffff
007176:  ffff  dw      0xffff
007178:  ffff  dw      0xffff
00717a:  ffff  dw      0xffff
00717c:  ffff  dw      0xffff
00717e:  ffff  dw      0xffff
007180:  ffff  dw      0xffff
007182:  ffff  dw      0xffff
007184:  ffff  dw      0xffff
007186:  ffff  dw      0xffff
007188:  ffff  dw      0xffff
00718a:  ffff  dw      0xffff
00718c:  ffff  dw      0xffff
00718e:  ffff  dw      0xffff
007190:  ffff  dw      0xffff
007192:  ffff  dw      0xffff
007194:  ffff  dw      0xffff
007196:  ffff  dw      0xffff
007198:  ffff  dw      0xffff
00719a:  ffff  dw      0xffff
00719c:  ffff  dw      0xffff
00719e:  ffff  dw      0xffff
0071a0:  ffff  dw      0xffff
0071a2:  ffff  dw      0xffff
0071a4:  ffff  dw      0xffff
0071a6:  ffff  dw      0xffff
0071a8:  ffff  dw      0xffff
0071aa:  ffff  dw      0xffff
0071ac:  ffff  dw      0xffff
0071ae:  ffff  dw      0xffff
0071b0:  ffff  dw      0xffff
0071b2:  ffff  dw      0xffff
0071b4:  ffff  dw      0xffff
0071b6:  ffff  dw      0xffff
0071b8:  ffff  dw      0xffff
0071ba:  ffff  dw      0xffff
0071bc:  ffff  dw      0xffff
0071be:  ffff  dw      0xffff
0071c0:  ffff  dw      0xffff
0071c2:  ffff  dw      0xffff
0071c4:  ffff  dw      0xffff
0071c6:  ffff  dw      0xffff
0071c8:  ffff  dw      0xffff
0071ca:  ffff  dw      0xffff
0071cc:  ffff  dw      0xffff
0071ce:  ffff  dw      0xffff
0071d0:  ffff  dw      0xffff
0071d2:  ffff  dw      0xffff
0071d4:  ffff  dw      0xffff
0071d6:  ffff  dw      0xffff
0071d8:  ffff  dw      0xffff
0071da:  ffff  dw      0xffff
0071dc:  ffff  dw      0xffff
0071de:  ffff  dw      0xffff
0071e0:  ffff  dw      0xffff
0071e2:  ffff  dw      0xffff
0071e4:  ffff  dw      0xffff
0071e6:  ffff  dw      0xffff
0071e8:  ffff  dw      0xffff
0071ea:  ffff  dw      0xffff
0071ec:  ffff  dw      0xffff
0071ee:  ffff  dw      0xffff
0071f0:  ffff  dw      0xffff
0071f2:  ffff  dw      0xffff
0071f4:  ffff  dw      0xffff
0071f6:  ffff  dw      0xffff
0071f8:  ffff  dw      0xffff
0071fa:  ffff  dw      0xffff
0071fc:  ffff  dw      0xffff
0071fe:  ffff  dw      0xffff
007200:  ffff  dw      0xffff
007202:  ffff  dw      0xffff
007204:  ffff  dw      0xffff
007206:  ffff  dw      0xffff
007208:  ffff  dw      0xffff
00720a:  ffff  dw      0xffff
00720c:  ffff  dw      0xffff
00720e:  ffff  dw      0xffff
007210:  ffff  dw      0xffff
007212:  ffff  dw      0xffff
007214:  ffff  dw      0xffff
007216:  ffff  dw      0xffff
007218:  ffff  dw      0xffff
00721a:  ffff  dw      0xffff
00721c:  ffff  dw      0xffff
00721e:  ffff  dw      0xffff
007220:  ffff  dw      0xffff
007222:  ffff  dw      0xffff
007224:  ffff  dw      0xffff
007226:  ffff  dw      0xffff
007228:  ffff  dw      0xffff
00722a:  ffff  dw      0xffff
00722c:  ffff  dw      0xffff
00722e:  ffff  dw      0xffff
007230:  ffff  dw      0xffff
007232:  ffff  dw      0xffff
007234:  ffff  dw      0xffff
007236:  ffff  dw      0xffff
007238:  ffff  dw      0xffff
00723a:  ffff  dw      0xffff
00723c:  ffff  dw      0xffff
00723e:  ffff  dw      0xffff
007240:  ffff  dw      0xffff
007242:  ffff  dw      0xffff
007244:  ffff  dw      0xffff
007246:  ffff  dw      0xffff
007248:  ffff  dw      0xffff
00724a:  ffff  dw      0xffff
00724c:  ffff  dw      0xffff
00724e:  ffff  dw      0xffff
007250:  ffff  dw      0xffff
007252:  ffff  dw      0xffff
007254:  ffff  dw      0xffff
007256:  ffff  dw      0xffff
007258:  ffff  dw      0xffff
00725a:  ffff  dw      0xffff
00725c:  ffff  dw      0xffff
00725e:  ffff  dw      0xffff
007260:  ffff  dw      0xffff
007262:  ffff  dw      0xffff
007264:  ffff  dw      0xffff
007266:  ffff  dw      0xffff
007268:  ffff  dw      0xffff
00726a:  ffff  dw      0xffff
00726c:  ffff  dw      0xffff
00726e:  ffff  dw      0xffff
007270:  ffff  dw      0xffff
007272:  ffff  dw      0xffff
007274:  ffff  dw      0xffff
007276:  ffff  dw      0xffff
007278:  ffff  dw      0xffff
00727a:  ffff  dw      0xffff
00727c:  ffff  dw      0xffff
00727e:  ffff  dw      0xffff
007280:  ffff  dw      0xffff
007282:  ffff  dw      0xffff
007284:  ffff  dw      0xffff
007286:  ffff  dw      0xffff
007288:  ffff  dw      0xffff
00728a:  ffff  dw      0xffff
00728c:  ffff  dw      0xffff
00728e:  ffff  dw      0xffff
007290:  ffff  dw      0xffff
007292:  ffff  dw      0xffff
007294:  ffff  dw      0xffff
007296:  ffff  dw      0xffff
007298:  ffff  dw      0xffff
00729a:  ffff  dw      0xffff
00729c:  ffff  dw      0xffff
00729e:  ffff  dw      0xffff
0072a0:  ffff  dw      0xffff
0072a2:  ffff  dw      0xffff
0072a4:  ffff  dw      0xffff
0072a6:  ffff  dw      0xffff
0072a8:  ffff  dw      0xffff
0072aa:  ffff  dw      0xffff
0072ac:  ffff  dw      0xffff
0072ae:  ffff  dw      0xffff
0072b0:  ffff  dw      0xffff
0072b2:  ffff  dw      0xffff
0072b4:  ffff  dw      0xffff
0072b6:  ffff  dw      0xffff
0072b8:  ffff  dw      0xffff
0072ba:  ffff  dw      0xffff
0072bc:  ffff  dw      0xffff
0072be:  ffff  dw      0xffff
0072c0:  ffff  dw      0xffff
0072c2:  ffff  dw      0xffff
0072c4:  ffff  dw      0xffff
0072c6:  ffff  dw      0xffff
0072c8:  ffff  dw      0xffff
0072ca:  ffff  dw      0xffff
0072cc:  ffff  dw      0xffff
0072ce:  ffff  dw      0xffff
0072d0:  ffff  dw      0xffff
0072d2:  ffff  dw      0xffff
0072d4:  ffff  dw      0xffff
0072d6:  ffff  dw      0xffff
0072d8:  ffff  dw      0xffff
0072da:  ffff  dw      0xffff
0072dc:  ffff  dw      0xffff
0072de:  ffff  dw      0xffff
0072e0:  ffff  dw      0xffff
0072e2:  ffff  dw      0xffff
0072e4:  ffff  dw      0xffff
0072e6:  ffff  dw      0xffff
0072e8:  ffff  dw      0xffff
0072ea:  ffff  dw      0xffff
0072ec:  ffff  dw      0xffff
0072ee:  ffff  dw      0xffff
0072f0:  ffff  dw      0xffff
0072f2:  ffff  dw      0xffff
0072f4:  ffff  dw      0xffff
0072f6:  ffff  dw      0xffff
0072f8:  ffff  dw      0xffff
0072fa:  ffff  dw      0xffff
0072fc:  ffff  dw      0xffff
0072fe:  ffff  dw      0xffff
007300:  ffff  dw      0xffff
007302:  ffff  dw      0xffff
007304:  ffff  dw      0xffff
007306:  ffff  dw      0xffff
007308:  ffff  dw      0xffff
00730a:  ffff  dw      0xffff
00730c:  ffff  dw      0xffff
00730e:  ffff  dw      0xffff
007310:  ffff  dw      0xffff
007312:  ffff  dw      0xffff
007314:  ffff  dw      0xffff
007316:  ffff  dw      0xffff
007318:  ffff  dw      0xffff
00731a:  ffff  dw      0xffff
00731c:  ffff  dw      0xffff
00731e:  ffff  dw      0xffff
007320:  ffff  dw      0xffff
007322:  ffff  dw      0xffff
007324:  ffff  dw      0xffff
007326:  ffff  dw      0xffff
007328:  ffff  dw      0xffff
00732a:  ffff  dw      0xffff
00732c:  ffff  dw      0xffff
00732e:  ffff  dw      0xffff
007330:  ffff  dw      0xffff
007332:  ffff  dw      0xffff
007334:  ffff  dw      0xffff
007336:  ffff  dw      0xffff
007338:  ffff  dw      0xffff
00733a:  ffff  dw      0xffff
00733c:  ffff  dw      0xffff
00733e:  ffff  dw      0xffff
007340:  ffff  dw      0xffff
007342:  ffff  dw      0xffff
007344:  ffff  dw      0xffff
007346:  ffff  dw      0xffff
007348:  ffff  dw      0xffff
00734a:  ffff  dw      0xffff
00734c:  ffff  dw      0xffff
00734e:  ffff  dw      0xffff
007350:  ffff  dw      0xffff
007352:  ffff  dw      0xffff
007354:  ffff  dw      0xffff
007356:  ffff  dw      0xffff
007358:  ffff  dw      0xffff
00735a:  ffff  dw      0xffff
00735c:  ffff  dw      0xffff
00735e:  ffff  dw      0xffff
007360:  ffff  dw      0xffff
007362:  ffff  dw      0xffff
007364:  ffff  dw      0xffff
007366:  ffff  dw      0xffff
007368:  ffff  dw      0xffff
00736a:  ffff  dw      0xffff
00736c:  ffff  dw      0xffff
00736e:  ffff  dw      0xffff
007370:  ffff  dw      0xffff
007372:  ffff  dw      0xffff
007374:  ffff  dw      0xffff
007376:  ffff  dw      0xffff
007378:  ffff  dw      0xffff
00737a:  ffff  dw      0xffff
00737c:  ffff  dw      0xffff
00737e:  ffff  dw      0xffff
007380:  ffff  dw      0xffff
007382:  ffff  dw      0xffff
007384:  ffff  dw      0xffff
007386:  ffff  dw      0xffff
007388:  ffff  dw      0xffff
00738a:  ffff  dw      0xffff
00738c:  ffff  dw      0xffff
00738e:  ffff  dw      0xffff
007390:  ffff  dw      0xffff
007392:  ffff  dw      0xffff
007394:  ffff  dw      0xffff
007396:  ffff  dw      0xffff
007398:  ffff  dw      0xffff
00739a:  ffff  dw      0xffff
00739c:  ffff  dw      0xffff
00739e:  ffff  dw      0xffff
0073a0:  ffff  dw      0xffff
0073a2:  ffff  dw      0xffff
0073a4:  ffff  dw      0xffff
0073a6:  ffff  dw      0xffff
0073a8:  ffff  dw      0xffff
0073aa:  ffff  dw      0xffff
0073ac:  ffff  dw      0xffff
0073ae:  ffff  dw      0xffff
0073b0:  ffff  dw      0xffff
0073b2:  ffff  dw      0xffff
0073b4:  ffff  dw      0xffff
0073b6:  ffff  dw      0xffff
0073b8:  ffff  dw      0xffff
0073ba:  ffff  dw      0xffff
0073bc:  ffff  dw      0xffff
0073be:  ffff  dw      0xffff
0073c0:  ffff  dw      0xffff
0073c2:  ffff  dw      0xffff
0073c4:  ffff  dw      0xffff
0073c6:  ffff  dw      0xffff
0073c8:  ffff  dw      0xffff
0073ca:  ffff  dw      0xffff
0073cc:  ffff  dw      0xffff
0073ce:  ffff  dw      0xffff
0073d0:  ffff  dw      0xffff
0073d2:  ffff  dw      0xffff
0073d4:  ffff  dw      0xffff
0073d6:  ffff  dw      0xffff
0073d8:  ffff  dw      0xffff
0073da:  ffff  dw      0xffff
0073dc:  ffff  dw      0xffff
0073de:  ffff  dw      0xffff
0073e0:  ffff  dw      0xffff
0073e2:  ffff  dw      0xffff
0073e4:  ffff  dw      0xffff
0073e6:  ffff  dw      0xffff
0073e8:  ffff  dw      0xffff
0073ea:  ffff  dw      0xffff
0073ec:  ffff  dw      0xffff
0073ee:  ffff  dw      0xffff
0073f0:  ffff  dw      0xffff
0073f2:  ffff  dw      0xffff
0073f4:  ffff  dw      0xffff
0073f6:  ffff  dw      0xffff
0073f8:  ffff  dw      0xffff
0073fa:  ffff  dw      0xffff
0073fc:  ffff  dw      0xffff
0073fe:  ffff  dw      0xffff
007400:  ffff  dw      0xffff
007402:  ffff  dw      0xffff
007404:  ffff  dw      0xffff
007406:  ffff  dw      0xffff
007408:  ffff  dw      0xffff
00740a:  ffff  dw      0xffff
00740c:  ffff  dw      0xffff
00740e:  ffff  dw      0xffff
007410:  ffff  dw      0xffff
007412:  ffff  dw      0xffff
007414:  ffff  dw      0xffff
007416:  ffff  dw      0xffff
007418:  ffff  dw      0xffff
00741a:  ffff  dw      0xffff
00741c:  ffff  dw      0xffff
00741e:  ffff  dw      0xffff
007420:  ffff  dw      0xffff
007422:  ffff  dw      0xffff
007424:  ffff  dw      0xffff
007426:  ffff  dw      0xffff
007428:  ffff  dw      0xffff
00742a:  ffff  dw      0xffff
00742c:  ffff  dw      0xffff
00742e:  ffff  dw      0xffff
007430:  ffff  dw      0xffff
007432:  ffff  dw      0xffff
007434:  ffff  dw      0xffff
007436:  ffff  dw      0xffff
007438:  ffff  dw      0xffff
00743a:  ffff  dw      0xffff
00743c:  ffff  dw      0xffff
00743e:  ffff  dw      0xffff
007440:  ffff  dw      0xffff
007442:  ffff  dw      0xffff
007444:  ffff  dw      0xffff
007446:  ffff  dw      0xffff
007448:  ffff  dw      0xffff
00744a:  ffff  dw      0xffff
00744c:  ffff  dw      0xffff
00744e:  ffff  dw      0xffff
007450:  ffff  dw      0xffff
007452:  ffff  dw      0xffff
007454:  ffff  dw      0xffff
007456:  ffff  dw      0xffff
007458:  ffff  dw      0xffff
00745a:  ffff  dw      0xffff
00745c:  ffff  dw      0xffff
00745e:  ffff  dw      0xffff
007460:  ffff  dw      0xffff
007462:  ffff  dw      0xffff
007464:  ffff  dw      0xffff
007466:  ffff  dw      0xffff
007468:  ffff  dw      0xffff
00746a:  ffff  dw      0xffff
00746c:  ffff  dw      0xffff
00746e:  ffff  dw      0xffff
007470:  ffff  dw      0xffff
007472:  ffff  dw      0xffff
007474:  ffff  dw      0xffff
007476:  ffff  dw      0xffff
007478:  ffff  dw      0xffff
00747a:  ffff  dw      0xffff
00747c:  ffff  dw      0xffff
00747e:  ffff  dw      0xffff
007480:  ffff  dw      0xffff
007482:  ffff  dw      0xffff
007484:  ffff  dw      0xffff
007486:  ffff  dw      0xffff
007488:  ffff  dw      0xffff
00748a:  ffff  dw      0xffff
00748c:  ffff  dw      0xffff
00748e:  ffff  dw      0xffff
007490:  ffff  dw      0xffff
007492:  ffff  dw      0xffff
007494:  ffff  dw      0xffff
007496:  ffff  dw      0xffff
007498:  ffff  dw      0xffff
00749a:  ffff  dw      0xffff
00749c:  ffff  dw      0xffff
00749e:  ffff  dw      0xffff
0074a0:  ffff  dw      0xffff
0074a2:  ffff  dw      0xffff
0074a4:  ffff  dw      0xffff
0074a6:  ffff  dw      0xffff
0074a8:  ffff  dw      0xffff
0074aa:  ffff  dw      0xffff
0074ac:  ffff  dw      0xffff
0074ae:  ffff  dw      0xffff
0074b0:  ffff  dw      0xffff
0074b2:  ffff  dw      0xffff
0074b4:  ffff  dw      0xffff
0074b6:  ffff  dw      0xffff
0074b8:  ffff  dw      0xffff
0074ba:  ffff  dw      0xffff
0074bc:  ffff  dw      0xffff
0074be:  ffff  dw      0xffff
0074c0:  ffff  dw      0xffff
0074c2:  ffff  dw      0xffff
0074c4:  ffff  dw      0xffff
0074c6:  ffff  dw      0xffff
0074c8:  ffff  dw      0xffff
0074ca:  ffff  dw      0xffff
0074cc:  ffff  dw      0xffff
0074ce:  ffff  dw      0xffff
0074d0:  ffff  dw      0xffff
0074d2:  ffff  dw      0xffff
0074d4:  ffff  dw      0xffff
0074d6:  ffff  dw      0xffff
0074d8:  ffff  dw      0xffff
0074da:  ffff  dw      0xffff
0074dc:  ffff  dw      0xffff
0074de:  ffff  dw      0xffff
0074e0:  ffff  dw      0xffff
0074e2:  ffff  dw      0xffff
0074e4:  ffff  dw      0xffff
0074e6:  ffff  dw      0xffff
0074e8:  ffff  dw      0xffff
0074ea:  ffff  dw      0xffff
0074ec:  ffff  dw      0xffff
0074ee:  ffff  dw      0xffff
0074f0:  ffff  dw      0xffff
0074f2:  ffff  dw      0xffff
0074f4:  ffff  dw      0xffff
0074f6:  ffff  dw      0xffff
0074f8:  ffff  dw      0xffff
0074fa:  ffff  dw      0xffff
0074fc:  ffff  dw      0xffff
0074fe:  ffff  dw      0xffff
007500:  ffff  dw      0xffff
007502:  ffff  dw      0xffff
007504:  ffff  dw      0xffff
007506:  ffff  dw      0xffff
007508:  ffff  dw      0xffff
00750a:  ffff  dw      0xffff
00750c:  ffff  dw      0xffff
00750e:  ffff  dw      0xffff
007510:  ffff  dw      0xffff
007512:  ffff  dw      0xffff
007514:  ffff  dw      0xffff
007516:  ffff  dw      0xffff
007518:  ffff  dw      0xffff
00751a:  ffff  dw      0xffff
00751c:  ffff  dw      0xffff
00751e:  ffff  dw      0xffff
007520:  ffff  dw      0xffff
007522:  ffff  dw      0xffff
007524:  ffff  dw      0xffff
007526:  ffff  dw      0xffff
007528:  ffff  dw      0xffff
00752a:  ffff  dw      0xffff
00752c:  ffff  dw      0xffff
00752e:  ffff  dw      0xffff
007530:  ffff  dw      0xffff
007532:  ffff  dw      0xffff
007534:  ffff  dw      0xffff
007536:  ffff  dw      0xffff
007538:  ffff  dw      0xffff
00753a:  ffff  dw      0xffff
00753c:  ffff  dw      0xffff
00753e:  ffff  dw      0xffff
007540:  ffff  dw      0xffff
007542:  ffff  dw      0xffff
007544:  ffff  dw      0xffff
007546:  ffff  dw      0xffff
007548:  ffff  dw      0xffff
00754a:  ffff  dw      0xffff
00754c:  ffff  dw      0xffff
00754e:  ffff  dw      0xffff
007550:  ffff  dw      0xffff
007552:  ffff  dw      0xffff
007554:  ffff  dw      0xffff
007556:  ffff  dw      0xffff
007558:  ffff  dw      0xffff
00755a:  ffff  dw      0xffff
00755c:  ffff  dw      0xffff
00755e:  ffff  dw      0xffff
007560:  ffff  dw      0xffff
007562:  ffff  dw      0xffff
007564:  ffff  dw      0xffff
007566:  ffff  dw      0xffff
007568:  ffff  dw      0xffff
00756a:  ffff  dw      0xffff
00756c:  ffff  dw      0xffff
00756e:  ffff  dw      0xffff
007570:  ffff  dw      0xffff
007572:  ffff  dw      0xffff
007574:  ffff  dw      0xffff
007576:  ffff  dw      0xffff
007578:  ffff  dw      0xffff
00757a:  ffff  dw      0xffff
00757c:  ffff  dw      0xffff
00757e:  ffff  dw      0xffff
007580:  ffff  dw      0xffff
007582:  ffff  dw      0xffff
007584:  ffff  dw      0xffff
007586:  ffff  dw      0xffff
007588:  ffff  dw      0xffff
00758a:  ffff  dw      0xffff
00758c:  ffff  dw      0xffff
00758e:  ffff  dw      0xffff
007590:  ffff  dw      0xffff
007592:  ffff  dw      0xffff
007594:  ffff  dw      0xffff
007596:  ffff  dw      0xffff
007598:  ffff  dw      0xffff
00759a:  ffff  dw      0xffff
00759c:  ffff  dw      0xffff
00759e:  ffff  dw      0xffff
0075a0:  ffff  dw      0xffff
0075a2:  ffff  dw      0xffff
0075a4:  ffff  dw      0xffff
0075a6:  ffff  dw      0xffff
0075a8:  ffff  dw      0xffff
0075aa:  ffff  dw      0xffff
0075ac:  ffff  dw      0xffff
0075ae:  ffff  dw      0xffff
0075b0:  ffff  dw      0xffff
0075b2:  ffff  dw      0xffff
0075b4:  ffff  dw      0xffff
0075b6:  ffff  dw      0xffff
0075b8:  ffff  dw      0xffff
0075ba:  ffff  dw      0xffff
0075bc:  ffff  dw      0xffff
0075be:  ffff  dw      0xffff
0075c0:  ffff  dw      0xffff
0075c2:  ffff  dw      0xffff
0075c4:  ffff  dw      0xffff
0075c6:  ffff  dw      0xffff
0075c8:  ffff  dw      0xffff
0075ca:  ffff  dw      0xffff
0075cc:  ffff  dw      0xffff
0075ce:  ffff  dw      0xffff
0075d0:  ffff  dw      0xffff
0075d2:  ffff  dw      0xffff
0075d4:  ffff  dw      0xffff
0075d6:  ffff  dw      0xffff
0075d8:  ffff  dw      0xffff
0075da:  ffff  dw      0xffff
0075dc:  ffff  dw      0xffff
0075de:  ffff  dw      0xffff
0075e0:  ffff  dw      0xffff
0075e2:  ffff  dw      0xffff
0075e4:  ffff  dw      0xffff
0075e6:  ffff  dw      0xffff
0075e8:  ffff  dw      0xffff
0075ea:  ffff  dw      0xffff
0075ec:  ffff  dw      0xffff
0075ee:  ffff  dw      0xffff
0075f0:  ffff  dw      0xffff
0075f2:  ffff  dw      0xffff
0075f4:  ffff  dw      0xffff
0075f6:  ffff  dw      0xffff
0075f8:  ffff  dw      0xffff
0075fa:  ffff  dw      0xffff
0075fc:  ffff  dw      0xffff
0075fe:  ffff  dw      0xffff
007600:  ffff  dw      0xffff
007602:  ffff  dw      0xffff
007604:  ffff  dw      0xffff
007606:  ffff  dw      0xffff
007608:  ffff  dw      0xffff
00760a:  ffff  dw      0xffff
00760c:  ffff  dw      0xffff
00760e:  ffff  dw      0xffff
007610:  ffff  dw      0xffff
007612:  ffff  dw      0xffff
007614:  ffff  dw      0xffff
007616:  ffff  dw      0xffff
007618:  ffff  dw      0xffff
00761a:  ffff  dw      0xffff
00761c:  ffff  dw      0xffff
00761e:  ffff  dw      0xffff
007620:  ffff  dw      0xffff
007622:  ffff  dw      0xffff
007624:  ffff  dw      0xffff
007626:  ffff  dw      0xffff
007628:  ffff  dw      0xffff
00762a:  ffff  dw      0xffff
00762c:  ffff  dw      0xffff
00762e:  ffff  dw      0xffff
007630:  ffff  dw      0xffff
007632:  ffff  dw      0xffff
007634:  ffff  dw      0xffff
007636:  ffff  dw      0xffff
007638:  ffff  dw      0xffff
00763a:  ffff  dw      0xffff
00763c:  ffff  dw      0xffff
00763e:  ffff  dw      0xffff
007640:  ffff  dw      0xffff
007642:  ffff  dw      0xffff
007644:  ffff  dw      0xffff
007646:  ffff  dw      0xffff
007648:  ffff  dw      0xffff
00764a:  ffff  dw      0xffff
00764c:  ffff  dw      0xffff
00764e:  ffff  dw      0xffff
007650:  ffff  dw      0xffff
007652:  ffff  dw      0xffff
007654:  ffff  dw      0xffff
007656:  ffff  dw      0xffff
007658:  ffff  dw      0xffff
00765a:  ffff  dw      0xffff
00765c:  ffff  dw      0xffff
00765e:  ffff  dw      0xffff
007660:  ffff  dw      0xffff
007662:  ffff  dw      0xffff
007664:  ffff  dw      0xffff
007666:  ffff  dw      0xffff
007668:  ffff  dw      0xffff
00766a:  ffff  dw      0xffff
00766c:  ffff  dw      0xffff
00766e:  ffff  dw      0xffff
007670:  ffff  dw      0xffff
007672:  ffff  dw      0xffff
007674:  ffff  dw      0xffff
007676:  ffff  dw      0xffff
007678:  ffff  dw      0xffff
00767a:  ffff  dw      0xffff
00767c:  ffff  dw      0xffff
00767e:  ffff  dw      0xffff
007680:  ffff  dw      0xffff
007682:  ffff  dw      0xffff
007684:  ffff  dw      0xffff
007686:  ffff  dw      0xffff
007688:  ffff  dw      0xffff
00768a:  ffff  dw      0xffff
00768c:  ffff  dw      0xffff
00768e:  ffff  dw      0xffff
007690:  ffff  dw      0xffff
007692:  ffff  dw      0xffff
007694:  ffff  dw      0xffff
007696:  ffff  dw      0xffff
007698:  ffff  dw      0xffff
00769a:  ffff  dw      0xffff
00769c:  ffff  dw      0xffff
00769e:  ffff  dw      0xffff
0076a0:  ffff  dw      0xffff
0076a2:  ffff  dw      0xffff
0076a4:  ffff  dw      0xffff
0076a6:  ffff  dw      0xffff
0076a8:  ffff  dw      0xffff
0076aa:  ffff  dw      0xffff
0076ac:  ffff  dw      0xffff
0076ae:  ffff  dw      0xffff
0076b0:  ffff  dw      0xffff
0076b2:  ffff  dw      0xffff
0076b4:  ffff  dw      0xffff
0076b6:  ffff  dw      0xffff
0076b8:  ffff  dw      0xffff
0076ba:  ffff  dw      0xffff
0076bc:  ffff  dw      0xffff
0076be:  ffff  dw      0xffff
0076c0:  ffff  dw      0xffff
0076c2:  ffff  dw      0xffff
0076c4:  ffff  dw      0xffff
0076c6:  ffff  dw      0xffff
0076c8:  ffff  dw      0xffff
0076ca:  ffff  dw      0xffff
0076cc:  ffff  dw      0xffff
0076ce:  ffff  dw      0xffff
0076d0:  ffff  dw      0xffff
0076d2:  ffff  dw      0xffff
0076d4:  ffff  dw      0xffff
0076d6:  ffff  dw      0xffff
0076d8:  ffff  dw      0xffff
0076da:  ffff  dw      0xffff
0076dc:  ffff  dw      0xffff
0076de:  ffff  dw      0xffff
0076e0:  ffff  dw      0xffff
0076e2:  ffff  dw      0xffff
0076e4:  ffff  dw      0xffff
0076e6:  ffff  dw      0xffff
0076e8:  ffff  dw      0xffff
0076ea:  ffff  dw      0xffff
0076ec:  ffff  dw      0xffff
0076ee:  ffff  dw      0xffff
0076f0:  ffff  dw      0xffff
0076f2:  ffff  dw      0xffff
0076f4:  ffff  dw      0xffff
0076f6:  ffff  dw      0xffff
0076f8:  ffff  dw      0xffff
0076fa:  ffff  dw      0xffff
0076fc:  ffff  dw      0xffff
0076fe:  ffff  dw      0xffff
007700:  ffff  dw      0xffff
007702:  ffff  dw      0xffff
007704:  ffff  dw      0xffff
007706:  ffff  dw      0xffff
007708:  ffff  dw      0xffff
00770a:  ffff  dw      0xffff
00770c:  ffff  dw      0xffff
00770e:  ffff  dw      0xffff
007710:  ffff  dw      0xffff
007712:  ffff  dw      0xffff
007714:  ffff  dw      0xffff
007716:  ffff  dw      0xffff
007718:  ffff  dw      0xffff
00771a:  ffff  dw      0xffff
00771c:  ffff  dw      0xffff
00771e:  ffff  dw      0xffff
007720:  ffff  dw      0xffff
007722:  ffff  dw      0xffff
007724:  ffff  dw      0xffff
007726:  ffff  dw      0xffff
007728:  ffff  dw      0xffff
00772a:  ffff  dw      0xffff
00772c:  ffff  dw      0xffff
00772e:  ffff  dw      0xffff
007730:  ffff  dw      0xffff
007732:  ffff  dw      0xffff
007734:  ffff  dw      0xffff
007736:  ffff  dw      0xffff
007738:  ffff  dw      0xffff
00773a:  ffff  dw      0xffff
00773c:  ffff  dw      0xffff
00773e:  ffff  dw      0xffff
007740:  ffff  dw      0xffff
007742:  ffff  dw      0xffff
007744:  ffff  dw      0xffff
007746:  ffff  dw      0xffff
007748:  ffff  dw      0xffff
00774a:  ffff  dw      0xffff
00774c:  ffff  dw      0xffff
00774e:  ffff  dw      0xffff
007750:  ffff  dw      0xffff
007752:  ffff  dw      0xffff
007754:  ffff  dw      0xffff
007756:  ffff  dw      0xffff
007758:  ffff  dw      0xffff
00775a:  ffff  dw      0xffff
00775c:  ffff  dw      0xffff
00775e:  ffff  dw      0xffff
007760:  ffff  dw      0xffff
007762:  ffff  dw      0xffff
007764:  ffff  dw      0xffff
007766:  ffff  dw      0xffff
007768:  ffff  dw      0xffff
00776a:  ffff  dw      0xffff
00776c:  ffff  dw      0xffff
00776e:  ffff  dw      0xffff
007770:  ffff  dw      0xffff
007772:  ffff  dw      0xffff
007774:  ffff  dw      0xffff
007776:  ffff  dw      0xffff
007778:  ffff  dw      0xffff
00777a:  ffff  dw      0xffff
00777c:  ffff  dw      0xffff
00777e:  ffff  dw      0xffff
007780:  ffff  dw      0xffff
007782:  ffff  dw      0xffff
007784:  ffff  dw      0xffff
007786:  ffff  dw      0xffff
007788:  ffff  dw      0xffff
00778a:  ffff  dw      0xffff
00778c:  ffff  dw      0xffff
00778e:  ffff  dw      0xffff
007790:  ffff  dw      0xffff
007792:  ffff  dw      0xffff
007794:  ffff  dw      0xffff
007796:  ffff  dw      0xffff
007798:  ffff  dw      0xffff
00779a:  ffff  dw      0xffff
00779c:  ffff  dw      0xffff
00779e:  ffff  dw      0xffff
0077a0:  ffff  dw      0xffff
0077a2:  ffff  dw      0xffff
0077a4:  ffff  dw      0xffff
0077a6:  ffff  dw      0xffff
0077a8:  ffff  dw      0xffff
0077aa:  ffff  dw      0xffff
0077ac:  ffff  dw      0xffff
0077ae:  ffff  dw      0xffff
0077b0:  ffff  dw      0xffff
0077b2:  ffff  dw      0xffff
0077b4:  ffff  dw      0xffff
0077b6:  ffff  dw      0xffff
0077b8:  ffff  dw      0xffff
0077ba:  ffff  dw      0xffff
0077bc:  ffff  dw      0xffff
0077be:  ffff  dw      0xffff
0077c0:  ffff  dw      0xffff
0077c2:  ffff  dw      0xffff
0077c4:  ffff  dw      0xffff
0077c6:  ffff  dw      0xffff
0077c8:  ffff  dw      0xffff
0077ca:  ffff  dw      0xffff
0077cc:  ffff  dw      0xffff
0077ce:  ffff  dw      0xffff
0077d0:  ffff  dw      0xffff
0077d2:  ffff  dw      0xffff
0077d4:  ffff  dw      0xffff
0077d6:  ffff  dw      0xffff
0077d8:  ffff  dw      0xffff
0077da:  ffff  dw      0xffff
0077dc:  ffff  dw      0xffff
0077de:  ffff  dw      0xffff
0077e0:  ffff  dw      0xffff
0077e2:  ffff  dw      0xffff
0077e4:  ffff  dw      0xffff
0077e6:  ffff  dw      0xffff
0077e8:  ffff  dw      0xffff
0077ea:  ffff  dw      0xffff
0077ec:  ffff  dw      0xffff
0077ee:  ffff  dw      0xffff
0077f0:  ffff  dw      0xffff
0077f2:  ffff  dw      0xffff
0077f4:  ffff  dw      0xffff
0077f6:  ffff  dw      0xffff
0077f8:  ffff  dw      0xffff
0077fa:  ffff  dw      0xffff
0077fc:  ffff  dw      0xffff
0077fe:  ffff  dw      0xffff

; ===========================================================================
; ===========================================================================
; BOOTLOADER REGION (0x007800 — 0x007FFF)
; ===========================================================================
; The 2 KB bootloader resides in the upper window of the 32 KB device.
; The reset vector at 0x000000 jumps here unconditionally; the bootloader
; then either:
;   • Stays in firmware-update protocol (if the host issues an Intel HEX
;     stream over UART matching the expected protocol, see HFD docs).
;   • Drops into the application by jumping to 0x000040 (the secondary
;     entry vector that calls label_031 / app_cold_init at 0x000366).
;
; The bootloader is also the manual recovery target: holding UP+DOWN
; (without SELECT) for ~5.5 s on the front panel triggers
; function_082 (bootloader_manual_entry @ 0x007F02) which stays in this
; region waiting for new firmware over UART.
;
; This region is preserved BIT-FOR-BIT across V1.4/V1.5b/V1.6b/V1.6Xb
; releases — the ABI patches at 0x7000 (V1.61b+) sit just BELOW the
; bootloader, in the gap between the application end and 0x7800.
; ===========================================================================

; ===========================================================================
; label_284 @ 0x007800 — bootloader_entry
; ---------------------------------------------------------------------------
; First instruction in bootloader; jumps over 0x007804..0x007AFC table /
; data area to the actual bootloader main at 0x007AFE.
; ===========================================================================
007800:  ef7f  goto    0x007afe             ; -> bootloader main loop
007802:  f03d
007804:  6e0d  movwf   0x0d, 0x0
007806:  0e03  movlw   0x03
007808:  d002  bra     0x00780e
00780a:  6e0d  movwf   0x0d, 0x0
00780c:  0e04  movlw   0x04
00780e:  6e07  movwf   0x07, 0x0
007810:  500e  movf    0x0e, 0x0, 0x0
007812:  5c0c  subwf   0x0c, 0x0, 0x0
007814:  e102  bnz     0x00781a
007816:  500d  movf    0x0d, 0x0, 0x0
007818:  5c0b  subwf   0x0b, 0x0, 0x0
00781a:  0e04  movlw   0x04
00781c:  b0d8  skpnc
00781e:  0e01  movlw   0x01
007820:  b4d8  skpnz
007822:  0e02  movlw   0x02
007824:  1407  andwf   0x07, 0x0, 0x0
007826:  a4d8  skpz
007828:  0e01  movlw   0x01
00782a:  0012  return  0x0
00782c:  0e80  movlw   0x80
00782e:  6e01  movwf   0x01, 0x0
007830:  0efe  movlw   0xfe
007832:  d900  rcall   0x007a34
007834:  0e01  movlw   0x01
007836:  d8fe  rcall   0x007a34
007838:  0e75  movlw   0x75
00783a:  6e0c  movwf   0x0c, 0x0
00783c:  0e30  movlw   0x30
00783e:  d141  bra     0x007ac2
007840:  6a01  clrf    0x01, 0x0
007842:  8e01  bsf     0x01, 0x7, 0x0
007844:  6e16  movwf   0x16, 0x0
007846:  0efe  movlw   0xfe
007848:  d8f5  rcall   0x007a34
00784a:  5016  movf    0x16, 0x0, 0x0
00784c:  d0f3  bra     0x007a34
00784e:  6a05  clrf    0x05, 0x0
007850:  0e80  movlw   0x80
007852:  6e1b  movwf   0x1b, 0x0
007854:  d000  bra     0x007856
007856:  6a0f  clrf    0x0f, 0x0
007858:  6a10  clrf    0x10, 0x0
00785a:  6a11  clrf    0x11, 0x0
00785c:  6a11  clrf    0x11, 0x0
00785e:  9a07  bcf     0x07, 0x5, 0x0
007860:  d8ed  rcall   0x007a3c
007862:  a0d8  skpc
007864:  0012  return  0x0
007866:  0fd3  addlw   0xd3
007868:  b4d8  skpnz
00786a:  8a07  bsf     0x07, 0x5, 0x0
00786c:  0f2d  addlw   0x2d
00786e:  0fc6  addlw   0xc6
007870:  e203  bc      0x007878
007872:  0f0a  addlw   0x0a
007874:  e3f5  bnc     0x007860
007876:  d005  bra     0x007882
007878:  0ff3  addlw   0xf3
00787a:  e2f2  bc      0x007860
00787c:  0f06  addlw   0x06
00787e:  e3f0  bnc     0x007860
007880:  0f0a  addlw   0x0a
007882:  6e0d  movwf   0x0d, 0x0
007884:  0e04  movlw   0x04
007886:  6e0e  movwf   0x0e, 0x0
007888:  90d8  clrc
00788a:  360f  rlcf    0x0f, 0x1, 0x0
00788c:  3610  rlcf    0x10, 0x1, 0x0
00788e:  3611  rlcf    0x11, 0x1, 0x0
007890:  3612  rlcf    0x12, 0x1, 0x0
007892:  2e0e  decfsz  0x0e, 0x1, 0x0
007894:  d7f9  bra     0x007888
007896:  500d  movf    0x0d, 0x0, 0x0
007898:  120f  iorwf   0x0f, 0x1, 0x0
00789a:  0605  decf    0x05, 0x1, 0x0
00789c:  e00e  bz      0x0078ba
00789e:  d8ce  rcall   0x007a3c
0078a0:  a0d8  skpc
0078a2:  0012  return  0x0
0078a4:  0fc6  addlw   0xc6
0078a6:  e203  bc      0x0078ae
0078a8:  0f0a  addlw   0x0a
0078aa:  e307  bnc     0x0078ba
0078ac:  d7ea  bra     0x007882
0078ae:  0ff3  addlw   0xf3
0078b0:  e204  bc      0x0078ba
0078b2:  0f06  addlw   0x06
0078b4:  e302  bnc     0x0078ba
0078b6:  0f0a  addlw   0x0a
0078b8:  d7e4  bra     0x007882
0078ba:  aa07  btfss   0x07, 0x5, 0x0
0078bc:  d00b  bra     0x0078d4
0078be:  1e0f  comf    0x0f, 0x1, 0x0
0078c0:  1e10  comf    0x10, 0x1, 0x0
0078c2:  1e11  comf    0x11, 0x1, 0x0
0078c4:  1e12  comf    0x12, 0x1, 0x0
0078c6:  2a0f  incf    0x0f, 0x1, 0x0
0078c8:  b4d8  skpnz
0078ca:  2a10  incf    0x10, 0x1, 0x0
0078cc:  b4d8  skpnz
0078ce:  2a11  incf    0x11, 0x1, 0x0
0078d0:  b4d8  skpnz
0078d2:  2a12  incf    0x12, 0x1, 0x0
0078d4:  500f  movf    0x0f, 0x0, 0x0
0078d6:  80d8  setc
0078d8:  0012  return  0x0
0078da:  6a05  clrf    0x05, 0x0
0078dc:  6e0f  movwf   0x0f, 0x0
0078de:  6a10  clrf    0x10, 0x0
0078e0:  9600  bcf     0x00, 0x3, 0x0
0078e2:  5005  movf    0x05, 0x0, 0x0
0078e4:  b4d8  skpnz
0078e6:  8600  bsf     0x00, 0x3, 0x0
0078e8:  0e04  movlw   0x04
0078ea:  6e04  movwf   0x04, 0x0
0078ec:  3810  swapf   0x10, 0x0, 0x0
0078ee:  d805  rcall   0x0078fa
0078f0:  5010  movf    0x10, 0x0, 0x0
0078f2:  d803  rcall   0x0078fa
0078f4:  380f  swapf   0x0f, 0x0, 0x0
0078f6:  d801  rcall   0x0078fa
0078f8:  500f  movf    0x0f, 0x0, 0x0
0078fa:  0b0f  andlw   0x0f
0078fc:  0ff6  addlw   0xf6
0078fe:  b0d8  skpnc
007900:  0f07  addlw   0x07
007902:  0f0a  addlw   0x0a
007904:  d000  bra     0x007906
007906:  6e0b  movwf   0x0b, 0x0
007908:  4e04  dcfsnz  0x04, 0x1, 0x0
00790a:  9600  bcf     0x00, 0x3, 0x0
00790c:  5005  movf    0x05, 0x0, 0x0
00790e:  e003  bz      0x007916
007910:  5c04  subwf   0x04, 0x0, 0x0
007912:  b0d8  skpnc
007914:  d007  bra     0x007924
007916:  500b  movf    0x0b, 0x0, 0x0
007918:  a4d8  skpz
00791a:  9600  bcf     0x00, 0x3, 0x0
00791c:  b600  btfsc   0x00, 0x3, 0x0
00791e:  d002  bra     0x007924
007920:  0f30  addlw   0x30
007922:  d088  bra     0x007a34
007924:  0012  return  0x0
007926:  6e0f  movwf   0x0f, 0x0
007928:  5004  movf    0x04, 0x0, 0x0
00792a:  b4d8  skpnz
00792c:  0012  return  0x0
00792e:  c00f  movff   0x00f, 0xfe9
007930:  ffe9
007932:  c010  movff   0x010, 0xfea
007934:  ffea
007936:  50ef  movf    0xef, 0x0, 0x0
007938:  b4d8  skpnz
00793a:  0012  return  0x0
00793c:  d87b  rcall   0x007a34
00793e:  4a0f  infsnz  0x0f, 0x1, 0x0
007940:  2a10  incf    0x10, 0x1, 0x0
007942:  0604  decf    0x04, 0x1, 0x0
007944:  d7f1  bra     0x007928
007946:  6aa6  clrf    0xa6, 0x0
007948:  8ea6  bsf     0xa6, 0x7, 0x0
00794a:  0009  tblrd*+
00794c:  50f5  movf    0xf5, 0x0, 0x0
00794e:  e002  bz      0x007954
007950:  d802  rcall   0x007956
007952:  d7fb  bra     0x00794a
007954:  0012  return  0x0
007956:  6e14  movwf   0x14, 0x0
007958:  988a  bcf     0x8a, 0x4, 0x0
00795a:  9a89  bcf     0x89, 0x5, 0x0
00795c:  9893  bcf     0x93, 0x4, 0x0
00795e:  9a92  bcf     0x92, 0x5, 0x0
007960:  0ef0  movlw   0xf0
007962:  1693  andwf   0x93, 0x1, 0x0
007964:  5014  movf    0x14, 0x0, 0x0
007966:  b200  btfsc   0x00, 0x1, 0x0
007968:  d01e  bra     0x0079a6
00796a:  0e3a  movlw   0x3a
00796c:  6e0c  movwf   0x0c, 0x0
00796e:  0e98  movlw   0x98
007970:  d8a8  rcall   0x007ac2
007972:  0e33  movlw   0x33
007974:  6e13  movwf   0x13, 0x0
007976:  d82a  rcall   0x0079cc
007978:  0e13  movlw   0x13
00797a:  6e0c  movwf   0x0c, 0x0
00797c:  0e88  movlw   0x88
00797e:  d8a1  rcall   0x007ac2
007980:  d825  rcall   0x0079cc
007982:  0e64  movlw   0x64
007984:  d89d  rcall   0x007ac0
007986:  d822  rcall   0x0079cc
007988:  0e64  movlw   0x64
00798a:  d89a  rcall   0x007ac0
00798c:  0e22  movlw   0x22
00798e:  6e13  movwf   0x13, 0x0
007990:  d81d  rcall   0x0079cc
007992:  0e28  movlw   0x28
007994:  d807  rcall   0x0079a4
007996:  0e0c  movlw   0x0c
007998:  d805  rcall   0x0079a4
00799a:  0e06  movlw   0x06
00799c:  d803  rcall   0x0079a4
00799e:  8200  bsf     0x00, 0x1, 0x0
0079a0:  5014  movf    0x14, 0x0, 0x0
0079a2:  d001  bra     0x0079a6
0079a4:  8000  bsf     0x00, 0x0, 0x0
0079a6:  6e13  movwf   0x13, 0x0
0079a8:  a000  btfss   0x00, 0x0, 0x0
0079aa:  d00a  bra     0x0079c0
0079ac:  9a89  bcf     0x89, 0x5, 0x0
0079ae:  0803  sublw   0x03
0079b0:  e30b  bnc     0x0079c8
0079b2:  d80a  rcall   0x0079c8
0079b4:  0e07  movlw   0x07
0079b6:  6e0c  movwf   0x0c, 0x0
0079b8:  0ed0  movlw   0xd0
0079ba:  d883  rcall   0x007ac2
0079bc:  80d8  setc
0079be:  0012  return  0x0
0079c0:  8000  bsf     0x00, 0x0, 0x0
0079c2:  08fe  sublw   0xfe
0079c4:  e011  bz      0x0079e8
0079c6:  8a89  bsf     0x89, 0x5, 0x0
0079c8:  3a13  swapf   0x13, 0x1, 0x0
0079ca:  a000  btfss   0x00, 0x0, 0x0
0079cc:  9000  bcf     0x00, 0x0, 0x0
0079ce:  888a  bsf     0x8a, 0x4, 0x0
0079d0:  0ef0  movlw   0xf0
0079d2:  1681  andwf   0x81, 0x1, 0x0
0079d4:  5013  movf    0x13, 0x0, 0x0
0079d6:  0b0f  andlw   0x0f
0079d8:  1281  iorwf   0x81, 0x1, 0x0
0079da:  988a  bcf     0x8a, 0x4, 0x0
0079dc:  3a13  swapf   0x13, 0x1, 0x0
0079de:  b000  btfsc   0x00, 0x0, 0x0
0079e0:  d7f5  bra     0x0079cc
0079e2:  0e32  movlw   0x32
0079e4:  d86d  rcall   0x007ac0
0079e6:  80d8  setc
0079e8:  5014  movf    0x14, 0x0, 0x0
0079ea:  0012  return  0x0
0079ec:  b2ab  btfsc   0xab, 0x1, 0x0
0079ee:  98ab  bcf     0xab, 0x4, 0x0
0079f0:  88ab  bsf     0xab, 0x4, 0x0
0079f2:  c002  movff   0x002, 0x00b
0079f4:  f00b
0079f6:  c006  movff   0x006, 0x00c
0079f8:  f00c
0079fa:  6a0d  clrf    0x0d, 0x0
0079fc:  6a0e  clrf    0x0e, 0x0
0079fe:  0000  nop
007a00:  d000  bra     0x007a02
007a02:  0000  nop
007a04:  ba9e  btfsc   0x9e, 0x5, 0x0
007a06:  d00e  bra     0x007a24
007a08:  68e8  setf    0xe8, 0x0
007a0a:  260d  addwf   0x0d, 0x1, 0x0
007a0c:  220e  addwfc  0x0e, 0x1, 0x0
007a0e:  220b  addwfc  0x0b, 0x1, 0x0
007a10:  220c  addwfc  0x0c, 0x1, 0x0
007a12:  a0d8  skpc
007a14:  0012  return  0x0
007a16:  480d  infsnz  0x0d, 0x0, 0x0
007a18:  3c0e  incfsz  0x0e, 0x0, 0x0
007a1a:  d7f1  bra     0x0079fe
007a1c:  0eb7  movlw   0xb7
007a1e:  6e0d  movwf   0x0d, 0x0
007a20:  6a0e  clrf    0x0e, 0x0
007a22:  d7ef  bra     0x007a02
007a24:  50ae  movf    0xae, 0x0, 0x0
007a26:  80d8  setc
007a28:  0012  return  0x0
007a2a:  a89e  btfss   0x9e, 0x4, 0x0
007a2c:  d7fe  bra     0x007a2a
007a2e:  6ead  movwf   0xad, 0x0
007a30:  80d8  setc
007a32:  0012  return  0x0
007a34:  be01  btfsc   0x01, 0x7, 0x0
007a36:  d78f  bra     0x007956
007a38:  b401  btfsc   0x01, 0x2, 0x0
007a3a:  d7f7  bra     0x007a2a
007a3c:  521b  movf    0x1b, 0x1, 0x0
007a3e:  e0d6  bz      0x0079ec
007a40:  80d8  setc
007a42:  be1b  btfsc   0x1b, 0x7, 0x0
007a44:  50ee  movf    0xee, 0x0, 0x0
007a46:  0012  return  0x0
007a48:  6ea9  movwf   0xa9, 0x0
007a4a:  6aa6  clrf    0xa6, 0x0
007a4c:  80a6  bsf     0xa6, 0x0, 0x0
007a4e:  50a8  movf    0xa8, 0x0, 0x0
007a50:  2aa9  incf    0xa9, 0x1, 0x0
007a52:  0012  return  0x0
007a54:  6ea8  movwf   0xa8, 0x0
007a56:  6aa6  clrf    0xa6, 0x0
007a58:  84a6  bsf     0xa6, 0x2, 0x0
007a5a:  0e55  movlw   0x55
007a5c:  6ea7  movwf   0xa7, 0x0
007a5e:  0eaa  movlw   0xaa
007a60:  6ea7  movwf   0xa7, 0x0
007a62:  82a6  bsf     0xa6, 0x1, 0x0
007a64:  b2a6  btfsc   0xa6, 0x1, 0x0
007a66:  d7fe  bra     0x007a64
007a68:  94a6  bcf     0xa6, 0x2, 0x0
007a6a:  2aa9  incf    0xa9, 0x1, 0x0
007a6c:  0012  return  0x0
007a6e:  6ef5  movwf   0xf5, 0x0
007a70:  000c  tblwt*
007a72:  28f6  incf    0xf6, 0x0, 0x0
007a74:  0b1f  andlw   0x1f
007a76:  e109  bnz     0x007a8a
007a78:  0e84  movlw   0x84
007a7a:  6ea6  movwf   0xa6, 0x0
007a7c:  0e55  movlw   0x55
007a7e:  6ea7  movwf   0xa7, 0x0
007a80:  0eaa  movlw   0xaa
007a82:  6ea7  movwf   0xa7, 0x0
007a84:  82a6  bsf     0xa6, 0x1, 0x0
007a86:  d000  bra     0x007a88
007a88:  94a6  bcf     0xa6, 0x2, 0x0
007a8a:  4af6  infsnz  0xf6, 0x1, 0x0
007a8c:  2af7  incf    0xf7, 0x1, 0x0
007a8e:  0012  return  0x0
007a90:  6ef6  movwf   0xf6, 0x0
007a92:  0e94  movlw   0x94
007a94:  6ea6  movwf   0xa6, 0x0
007a96:  0e55  movlw   0x55
007a98:  6ea7  movwf   0xa7, 0x0
007a9a:  0eaa  movlw   0xaa
007a9c:  6ea7  movwf   0xa7, 0x0
007a9e:  82a6  bsf     0xa6, 0x1, 0x0
007aa0:  0000  nop
007aa2:  94a6  bcf     0xa6, 0x2, 0x0
007aa4:  0012  return  0x0
007aa6:  6a0e  clrf    0x0e, 0x0
007aa8:  6e0d  movwf   0x0d, 0x0
007aaa:  0eff  movlw   0xff
007aac:  260d  addwf   0x0d, 0x1, 0x0
007aae:  220e  addwfc  0x0e, 0x1, 0x0
007ab0:  d000  bra     0x007ab2
007ab2:  a0d8  skpc
007ab4:  0012  return  0x0
007ab6:  0e03  movlw   0x03
007ab8:  6e0c  movwf   0x0c, 0x0
007aba:  0ee5  movlw   0xe5
007abc:  d802  rcall   0x007ac2
007abe:  d7f5  bra     0x007aaa
007ac0:  6a0c  clrf    0x0c, 0x0
007ac2:  0ffa  addlw   0xfa
007ac4:  6e0b  movwf   0x0b, 0x0
007ac6:  0000  nop
007ac8:  e303  bnc     0x007ad0
007aca:  d000  bra     0x007acc
007acc:  060b  decf    0x0b, 0x1, 0x0
007ace:  e2fe  bc      0x007acc
007ad0:  060b  decf    0x0b, 0x1, 0x0
007ad2:  060c  decf    0x0c, 0x1, 0x0
007ad4:  e2fb  bc      0x007acc
007ad6:  0000  nop
007ad8:  0012  return  0x0
007ada:  4ef3  dcfsnz  0xf3, 0x1, 0x0
007adc:  d002  bra     0x007ae2
007ade:  52e6  movf    0xe6, 0x1, 0x0
007ae0:  d7fc  bra     0x007ada
007ae2:  cfe6  movff   0xfe6, 0xfee
007ae4:  ffee
007ae6:  2ee8  decfsz  0xe8, 0x1, 0x0
007ae8:  d7fc  bra     0x007ae2
007aea:  0012  return  0x0
007aec:  6f42  movwf   0x42, 0x1
007aee:  746f  btg     0x6f, 0x2, 0x0
007af0:  6f6c  movwf   0x6c, 0x1
007af2:  6461  cpfsgt  0x61, 0x0
007af4:  7265  btg     0x65, 0x1, 0x0
007af6:  6d20  negf    0x20, 0x1
007af8:  646f  cpfsgt  0x6f, 0x0
007afa:  2065  addwfc  0x65, 0x0, 0x0
007afc:  0000  nop

; ===========================================================================
; bootloader_main @ 0x007AFE
; ---------------------------------------------------------------------------
; Entry from bootloader_entry. Performs minimal init (zero TBLPTRU/BSR),
; arms UART RX/TX (TXSTA, RCSTA, BAUDCON), and enters the firmware-update
; protocol read loop — function_066 (bootloader_oerr_handler at 0x79EC)
; and function_080 (bootloader_prompt_send at 0x7E60) live in this
; region. The protocol is a host-driven Intel HEX upload similar to the
; MAIN bootloader path; the prompt sent on TX is `:FW_Upd\r\n`.
; ===========================================================================
007afe:  6af8  clrf    0xf8, 0x0            ; TBLPTRU = 0
007b00:  6a00  clrf    0x00, 0x0
007b02:  0e05  movlw   0x05
007b04:  6eaf  movwf   0xaf, 0x0            ; SPBRG seed
007b06:  0e20  movlw   0x20
007b08:  6eac  movwf   0xac, 0x0            ; TXSTA
007b0a:  0e90  movlw   0x90
007b0c:  6eab  movwf   0xab, 0x0
007b0e:  0100  movlb   0x0
007b10:  0edf  movlw   0xdf
007b12:  6e92  movwf   0x92, 0x0
007b14:  0e3c  movlw   0x3c
007b16:  6e93  movwf   0x93, 0x0
007b18:  0ebd  movlw   0xbd
007b1a:  6e94  movwf   0x94, 0x0
007b1c:  6a7b  clrf    0x7b, 0x0
007b1e:  6a7a  clrf    0x7a, 0x0
007b20:  6a7e  clrf    0x7e, 0x0
007b22:  6a7f  clrf    0x7f, 0x0
007b24:  0e0f  movlw   0x0f
007b26:  6ec1  movwf   0xc1, 0x0
007b28:  0e05  movlw   0x05
007b2a:  dfbd  rcall   0x007aa6
007b2c:  0e46  movlw   0x46
007b2e:  6f76  movwf   0x76, 0x1
007b30:  0e57  movlw   0x57
007b32:  6f77  movwf   0x77, 0x1
007b34:  0e5f  movlw   0x5f
007b36:  6f78  movwf   0x78, 0x1
007b38:  0e55  movlw   0x55
007b3a:  6f79  movwf   0x79, 0x1
007b3c:  0e70  movlw   0x70
007b3e:  6f7a  movwf   0x7a, 0x1
007b40:  0e64  movlw   0x64
007b42:  6f7b  movwf   0x7b, 0x1
007b44:  9c93  bcf     0x93, 0x6, 0x0
007b46:  9c8a  bcf     0x8a, 0x6, 0x0
007b48:  9382  bcf     0x82, 0x1, 0x1
007b4a:  d9db  rcall   0x007f02
007b4c:  3182  rrcf    0x82, 0x0, 0x1
007b4e:  32e8  rrcf    0xe8, 0x1, 0x0
007b50:  e215  bc      0x007b7c
007b52:  0eff  movlw   0xff
007b54:  df79  rcall   0x007a48
007b56:  6e1f  movwf   0x1f, 0x0
007b58:  2c1f  decfsz  0x1f, 0x0, 0x0
007b5a:  d006  bra     0x007b68
007b5c:  68a9  setf    0xa9, 0x0
007b5e:  0e77  movlw   0x77
007b60:  df79  rcall   0x007a54
007b62:  ef20  goto    0x000040
007b64:  f000
007b66:  d009  bra     0x007b7a
007b68:  0e02  movlw   0x02
007b6a:  621f  cpfseq  0x1f, 0x0
007b6c:  d006  bra     0x007b7a
007b6e:  0efe  movlw   0xfe
007b70:  6ea9  movwf   0xa9, 0x0
007b72:  0e01  movlw   0x01
007b74:  df6f  rcall   0x007a54
007b76:  ef20  goto    0x000040
007b78:  f000
007b7a:  d003  bra     0x007b82
007b7c:  68a9  setf    0xa9, 0x0
007b7e:  0e00  movlw   0x00
007b80:  df69  rcall   0x007a54
007b82:  8aac  bsf     0xac, 0x5, 0x0
007b84:  88ab  bsf     0xab, 0x4, 0x0
007b86:  8eab  bsf     0xab, 0x7, 0x0
007b88:  de51  rcall   0x00782c
007b8a:  9294  bcf     0x94, 0x1, 0x0
007b8c:  828b  bsf     0x8b, 0x1, 0x0
007b8e:  0e80  movlw   0x80
007b90:  6e01  movwf   0x01, 0x0
007b92:  de56  rcall   0x007840
007b94:  0e7a  movlw   0x7a
007b96:  6ef7  movwf   0xf7, 0x0
007b98:  0eec  movlw   0xec
007b9a:  6ef6  movwf   0xf6, 0x0
007b9c:  ded4  rcall   0x007946
007b9e:  ee00  lfsr    0x0, 0x024
007ba0:  f024
007ba2:  0e1f  movlw   0x1f
007ba4:  6aee  clrf    0xee, 0x0
007ba6:  2ee8  decfsz  0xe8, 0x1, 0x0
007ba8:  d7fd  bra     0x007ba4
007baa:  9ef2  bcf     0xf2, 0x7, 0x0
007bac:  0e40  movlw   0x40
007bae:  6e1d  movwf   0x1d, 0x0
007bb0:  6a1e  clrf    0x1e, 0x0
007bb2:  6a20  clrf    0x20, 0x0
007bb4:  6a21  clrf    0x21, 0x0
007bb6:  6a08  clrf    0x08, 0x0
007bb8:  ee00  lfsr    0x0, 0x076
007bba:  f076
007bbc:  5008  movf    0x08, 0x0, 0x0
007bbe:  50eb  movf    0xeb, 0x0, 0x0
007bc0:  6e19  movwf   0x19, 0x0
007bc2:  ee00  lfsr    0x0, 0x07c
007bc4:  f07c
007bc6:  5008  movf    0x08, 0x0, 0x0
007bc8:  c019  movff   0x019, 0xfeb
007bca:  ffeb
007bcc:  2a08  incf    0x08, 0x1, 0x0
007bce:  5008  movf    0x08, 0x0, 0x0
007bd0:  0806  sublw   0x06
007bd2:  e1f2  bnz     0x007bb8
007bd4:  d945  rcall   0x007e60
007bd6:  ee00  lfsr    0x0, 0x043
007bd8:  f043
007bda:  0e2e  movlw   0x2e
007bdc:  6aee  clrf    0xee, 0x0
007bde:  2ee8  decfsz  0xe8, 0x1, 0x0
007be0:  d7fd  bra     0x007bdc
007be2:  0ef4  movlw   0xf4
007be4:  6e02  movwf   0x02, 0x0
007be6:  0e01  movlw   0x01
007be8:  6e06  movwf   0x06, 0x0
007bea:  df00  rcall   0x0079ec
007bec:  e3e4  bnc     0x007bb6
007bee:  083a  sublw   0x3a
007bf0:  e1fc  bnz     0x007bea
007bf2:  ee10  lfsr    0x1, 0x043
007bf4:  f043
007bf6:  defa  rcall   0x0079ec
007bf8:  e3de  bnc     0x007bb6
007bfa:  080d  sublw   0x0d
007bfc:  e102  bnz     0x007c02
007bfe:  6ae6  clrf    0xe6, 0x0
007c00:  d004  bra     0x007c0a
007c02:  50ae  movf    0xae, 0x0, 0x0
007c04:  6ee6  movwf   0xe6, 0x0
007c06:  e001  bz      0x007c0a
007c08:  d7f6  bra     0x007bf6
007c0a:  9182  bcf     0x82, 0x0, 0x1
007c0c:  6a1f  clrf    0x1f, 0x0
007c0e:  0e06  movlw   0x06
007c10:  601f  cpfslt  0x1f, 0x0
007c12:  d00b  bra     0x007c2a
007c14:  ee00  lfsr    0x0, 0x043
007c16:  f043
007c18:  501f  movf    0x1f, 0x0, 0x0
007c1a:  50eb  movf    0xeb, 0x0, 0x0
007c1c:  6e08  movwf   0x08, 0x0
007c1e:  0e30  movlw   0x30
007c20:  5c08  subwf   0x08, 0x0, 0x0
007c22:  e001  bz      0x007c26
007c24:  8182  bsf     0x82, 0x0, 0x1
007c26:  2a1f  incf    0x1f, 0x1, 0x0
007c28:  e1f2  bnz     0x007c0e
007c2a:  3182  rrcf    0x82, 0x0, 0x1
007c2c:  e201  bc      0x007c30
007c2e:  d193  bra     0x007f56
007c30:  6a22  clrf    0x22, 0x0
007c32:  6a23  clrf    0x23, 0x0
007c34:  6a1f  clrf    0x1f, 0x0
007c36:  0e14  movlw   0x14
007c38:  601f  cpfslt  0x1f, 0x0
007c3a:  d01c  bra     0x007c74
007c3c:  ee00  lfsr    0x0, 0x071
007c3e:  f071
007c40:  ee10  lfsr    0x1, 0x043
007c42:  f043
007c44:  501f  movf    0x1f, 0x0, 0x0
007c46:  0d02  mullw   0x02
007c48:  cff3  movff   0xff3, 0x019
007c4a:  f019
007c4c:  cff4  movff   0xff4, 0x01a
007c4e:  f01a
007c50:  2819  incf    0x19, 0x0, 0x0
007c52:  6ef3  movwf   0xf3, 0x0
007c54:  0e02  movlw   0x02
007c56:  df41  rcall   0x007ada
007c58:  6aef  clrf    0xef, 0x0
007c5a:  ee00  lfsr    0x0, 0x071
007c5c:  f071
007c5e:  ec27  call    0x00784e, 0x0
007c60:  f03c
007c62:  6e19  movwf   0x19, 0x0
007c64:  c010  movff   0x010, 0x01a
007c66:  f01a
007c68:  5019  movf    0x19, 0x0, 0x0
007c6a:  2622  addwf   0x22, 0x1, 0x0
007c6c:  501a  movf    0x1a, 0x0, 0x0
007c6e:  2223  addwfc  0x23, 0x1, 0x0
007c70:  2a1f  incf    0x1f, 0x1, 0x0
007c72:  e1e1  bnz     0x007c36
007c74:  5022  movf    0x22, 0x0, 0x0
007c76:  08ff  sublw   0xff
007c78:  6e19  movwf   0x19, 0x0
007c7a:  0eff  movlw   0xff
007c7c:  5423  subfwb  0x23, 0x0, 0x0
007c7e:  6e1a  movwf   0x1a, 0x0
007c80:  0e01  movlw   0x01
007c82:  2419  addwf   0x19, 0x0, 0x0
007c84:  6e22  movwf   0x22, 0x0
007c86:  0e00  movlw   0x00
007c88:  201a  addwfc  0x1a, 0x0, 0x0
007c8a:  6e23  movwf   0x23, 0x0
007c8c:  ee00  lfsr    0x0, 0x071
007c8e:  f071
007c90:  ee10  lfsr    0x1, 0x043
007c92:  f043
007c94:  0e29  movlw   0x29
007c96:  6ef3  movwf   0xf3, 0x0
007c98:  0e02  movlw   0x02
007c9a:  df1f  rcall   0x007ada
007c9c:  6aef  clrf    0xef, 0x0
007c9e:  ee00  lfsr    0x0, 0x071
007ca0:  f071
007ca2:  ec27  call    0x00784e, 0x0
007ca4:  f03c
007ca6:  6e20  movwf   0x20, 0x0
007ca8:  c010  movff   0x010, 0x021
007caa:  f021
007cac:  5020  movf    0x20, 0x0, 0x0
007cae:  6222  cpfseq  0x22, 0x0
007cb0:  d0d6  bra     0x007e5e
007cb2:  6621  tstfsz  0x21, 0x0
007cb4:  d0d4  bra     0x007e5e
007cb6:  ee00  lfsr    0x0, 0x071
007cb8:  f071
007cba:  ee10  lfsr    0x1, 0x043
007cbc:  f043
007cbe:  0e03  movlw   0x03
007cc0:  6ef3  movwf   0xf3, 0x0
007cc2:  0e04  movlw   0x04
007cc4:  df0a  rcall   0x007ada
007cc6:  6aef  clrf    0xef, 0x0
007cc8:  ee00  lfsr    0x0, 0x071
007cca:  f071
007ccc:  ec27  call    0x00784e, 0x0
007cce:  f03c
007cd0:  6e1d  movwf   0x1d, 0x0
007cd2:  c010  movff   0x010, 0x01e
007cd4:  f01e
007cd6:  0e3f  movlw   0x3f
007cd8:  141d  andwf   0x1d, 0x0, 0x0
007cda:  6e08  movwf   0x08, 0x0
007cdc:  6a09  clrf    0x09, 0x0
007cde:  5009  movf    0x09, 0x0, 0x0
007ce0:  1008  iorwf   0x08, 0x0, 0x0
007ce2:  e002  bz      0x007ce8
007ce4:  0e00  movlw   0x00
007ce6:  d001  bra     0x007cea
007ce8:  0e01  movlw   0x01
007cea:  6e1c  movwf   0x1c, 0x0
007cec:  c01d  movff   0x01d, 0x00b
007cee:  f00b
007cf0:  c01e  movff   0x01e, 0x00c
007cf2:  f00c
007cf4:  0e77  movlw   0x77
007cf6:  6e0e  movwf   0x0e, 0x0
007cf8:  0ec0  movlw   0xc0
007cfa:  ec05  call    0x00780a, 0x0
007cfc:  f03c
007cfe:  161c  andwf   0x1c, 0x1, 0x0
007d00:  c01d  movff   0x01d, 0x00b
007d02:  f00b
007d04:  c01e  movff   0x01e, 0x00c
007d06:  f00c
007d08:  6a0e  clrf    0x0e, 0x0
007d0a:  0e40  movlw   0x40
007d0c:  ec02  call    0x007804, 0x0
007d0e:  f03c
007d10:  161c  andwf   0x1c, 0x1, 0x0
007d12:  e007  bz      0x007d22
007d14:  501e  movf    0x1e, 0x0, 0x0
007d16:  101d  iorwf   0x1d, 0x0, 0x0
007d18:  e004  bz      0x007d22
007d1a:  c01e  movff   0x01e, 0xff7
007d1c:  fff7
007d1e:  501d  movf    0x1d, 0x0, 0x0
007d20:  deb7  rcall   0x007a90
007d22:  c01d  movff   0x01d, 0x00b
007d24:  f00b
007d26:  c01e  movff   0x01e, 0x00c
007d28:  f00c
007d2a:  0e77  movlw   0x77
007d2c:  6e0e  movwf   0x0e, 0x0
007d2e:  0ec0  movlw   0xc0
007d30:  ec05  call    0x00780a, 0x0
007d32:  f03c
007d34:  6e1c  movwf   0x1c, 0x0
007d36:  c01d  movff   0x01d, 0x00b
007d38:  f00b
007d3a:  c01e  movff   0x01e, 0x00c
007d3c:  f00c
007d3e:  6a0e  clrf    0x0e, 0x0
007d40:  0e40  movlw   0x40
007d42:  ec02  call    0x007804, 0x0
007d44:  f03c
007d46:  161c  andwf   0x1c, 0x1, 0x0
007d48:  e02d  bz      0x007da4
007d4a:  6a1f  clrf    0x1f, 0x0
007d4c:  0e08  movlw   0x08
007d4e:  601f  cpfslt  0x1f, 0x0
007d50:  d029  bra     0x007da4
007d52:  ee00  lfsr    0x0, 0x071
007d54:  f071
007d56:  ee10  lfsr    0x1, 0x043
007d58:  f043
007d5a:  501f  movf    0x1f, 0x0, 0x0
007d5c:  0d04  mullw   0x04
007d5e:  cff3  movff   0xff3, 0x019
007d60:  f019
007d62:  cff4  movff   0xff4, 0x01a
007d64:  f01a
007d66:  0e09  movlw   0x09
007d68:  2419  addwf   0x19, 0x0, 0x0
007d6a:  6ef3  movwf   0xf3, 0x0
007d6c:  0e04  movlw   0x04
007d6e:  deb5  rcall   0x007ada
007d70:  6aef  clrf    0xef, 0x0
007d72:  ee00  lfsr    0x0, 0x071
007d74:  f071
007d76:  ec27  call    0x00784e, 0x0
007d78:  f03c
007d7a:  6e20  movwf   0x20, 0x0
007d7c:  c010  movff   0x010, 0x021
007d7e:  f021
007d80:  501f  movf    0x1f, 0x0, 0x0
007d82:  0d02  mullw   0x02
007d84:  cff3  movff   0xff3, 0x019
007d86:  f019
007d88:  cff4  movff   0xff4, 0x01a
007d8a:  f01a
007d8c:  5019  movf    0x19, 0x0, 0x0
007d8e:  241d  addwf   0x1d, 0x0, 0x0
007d90:  6ef6  movwf   0xf6, 0x0
007d92:  501a  movf    0x1a, 0x0, 0x0
007d94:  201e  addwfc  0x1e, 0x0, 0x0
007d96:  6ef7  movwf   0xf7, 0x0
007d98:  5021  movf    0x21, 0x0, 0x0
007d9a:  de69  rcall   0x007a6e
007d9c:  5020  movf    0x20, 0x0, 0x0
007d9e:  de67  rcall   0x007a6e
007da0:  2a1f  incf    0x1f, 0x1, 0x0
007da2:  e1d4  bnz     0x007d4c
007da4:  0e3a  movlw   0x3a
007da6:  de41  rcall   0x007a2a
007da8:  0e04  movlw   0x04
007daa:  6e01  movwf   0x01, 0x0
007dac:  0e02  movlw   0x02
007dae:  6e05  movwf   0x05, 0x0
007db0:  5022  movf    0x22, 0x0, 0x0
007db2:  ec6e  call    0x0078dc, 0x0
007db4:  f03c
007db6:  0e0d  movlw   0x0d
007db8:  de38  rcall   0x007a2a
007dba:  0e0a  movlw   0x0a
007dbc:  de36  rcall   0x007a2a
007dbe:  501d  movf    0x1d, 0x0, 0x0
007dc0:  0a40  xorlw   0x40
007dc2:  101e  iorwf   0x1e, 0x0, 0x0
007dc4:  e124  bnz     0x007e0e
007dc6:  0e08  movlw   0x08
007dc8:  6e1f  movwf   0x1f, 0x0
007dca:  0e10  movlw   0x10
007dcc:  601f  cpfslt  0x1f, 0x0
007dce:  d01c  bra     0x007e08
007dd0:  ee00  lfsr    0x0, 0x071
007dd2:  f071
007dd4:  ee10  lfsr    0x1, 0x043
007dd6:  f043
007dd8:  501f  movf    0x1f, 0x0, 0x0
007dda:  0d02  mullw   0x02
007ddc:  cff3  movff   0xff3, 0x019
007dde:  f019
007de0:  cff4  movff   0xff4, 0x01a
007de2:  f01a
007de4:  0e09  movlw   0x09
007de6:  2419  addwf   0x19, 0x0, 0x0
007de8:  6ef3  movwf   0xf3, 0x0
007dea:  0e02  movlw   0x02
007dec:  de76  rcall   0x007ada
007dee:  6aef  clrf    0xef, 0x0
007df0:  ee00  lfsr    0x0, 0x071
007df2:  f071
007df4:  ec27  call    0x00784e, 0x0
007df6:  f03c
007df8:  6e08  movwf   0x08, 0x0
007dfa:  ee00  lfsr    0x0, 0x024
007dfc:  f024
007dfe:  501f  movf    0x1f, 0x0, 0x0
007e00:  c008  movff   0x008, 0xfeb
007e02:  ffeb
007e04:  2a1f  incf    0x1f, 0x1, 0x0
007e06:  e1e1  bnz     0x007dca
007e08:  68a9  setf    0xa9, 0x0
007e0a:  0e00  movlw   0x00
007e0c:  de23  rcall   0x007a54
007e0e:  501d  movf    0x1d, 0x0, 0x0
007e10:  0a50  xorlw   0x50
007e12:  101e  iorwf   0x1e, 0x0, 0x0
007e14:  e124  bnz     0x007e5e
007e16:  6a1f  clrf    0x1f, 0x0
007e18:  0e10  movlw   0x10
007e1a:  601f  cpfslt  0x1f, 0x0
007e1c:  d01f  bra     0x007e5c
007e1e:  ee00  lfsr    0x0, 0x071
007e20:  f071
007e22:  ee10  lfsr    0x1, 0x043
007e24:  f043
007e26:  501f  movf    0x1f, 0x0, 0x0
007e28:  0d02  mullw   0x02
007e2a:  cff3  movff   0xff3, 0x019
007e2c:  f019
007e2e:  cff4  movff   0xff4, 0x01a
007e30:  f01a
007e32:  0e09  movlw   0x09
007e34:  2419  addwf   0x19, 0x0, 0x0
007e36:  6ef3  movwf   0xf3, 0x0
007e38:  0e02  movlw   0x02
007e3a:  de4f  rcall   0x007ada
007e3c:  6aef  clrf    0xef, 0x0
007e3e:  0e10  movlw   0x10
007e40:  241f  addwf   0x1f, 0x0, 0x0
007e42:  6e08  movwf   0x08, 0x0
007e44:  ee00  lfsr    0x0, 0x071
007e46:  f071
007e48:  ec27  call    0x00784e, 0x0
007e4a:  f03c
007e4c:  6e0a  movwf   0x0a, 0x0
007e4e:  ee00  lfsr    0x0, 0x024
007e50:  f024
007e52:  5008  movf    0x08, 0x0, 0x0
007e54:  c00a  movff   0x00a, 0xfeb
007e56:  ffeb
007e58:  2a1f  incf    0x1f, 0x1, 0x0
007e5a:  e1de  bnz     0x007e18
007e5c:  d81b  rcall   0x007e94
007e5e:  d6bb  bra     0x007bd6
007e60:  0e0d  movlw   0x0d
007e62:  ec15  call    0x007a2a, 0x0
007e64:  f03d
007e66:  0e0a  movlw   0x0a
007e68:  ec15  call    0x007a2a, 0x0
007e6a:  f03d
007e6c:  0e0c  movlw   0x0c
007e6e:  ec15  call    0x007a2a, 0x0
007e70:  f03d
007e72:  0e3a  movlw   0x3a
007e74:  ec15  call    0x007a2a, 0x0
007e76:  f03d
007e78:  0e04  movlw   0x04
007e7a:  6e01  movwf   0x01, 0x0
007e7c:  0e06  movlw   0x06
007e7e:  6e04  movwf   0x04, 0x0
007e80:  6a10  clrf    0x10, 0x0
007e82:  0e7c  movlw   0x7c
007e84:  ec93  call    0x007926, 0x0
007e86:  f03c
007e88:  0e0d  movlw   0x0d
007e8a:  ec15  call    0x007a2a, 0x0
007e8c:  f03d
007e8e:  0e0a  movlw   0x0a
007e90:  ef15  goto    0x007a2a
007e92:  f03d
007e94:  6af6  clrf    0xf6, 0x0
007e96:  6af7  clrf    0xf7, 0x0
007e98:  ddfc  rcall   0x007a92
007e9a:  6af6  clrf    0xf6, 0x0
007e9c:  6af7  clrf    0xf7, 0x0
007e9e:  0e00  movlw   0x00
007ea0:  ec37  call    0x007a6e, 0x0
007ea2:  f03d
007ea4:  0eef  movlw   0xef
007ea6:  ec37  call    0x007a6e, 0x0
007ea8:  f03d
007eaa:  0e02  movlw   0x02
007eac:  6ef6  movwf   0xf6, 0x0
007eae:  6af7  clrf    0xf7, 0x0
007eb0:  0e3c  movlw   0x3c
007eb2:  ec37  call    0x007a6e, 0x0
007eb4:  f03d
007eb6:  0ef0  movlw   0xf0
007eb8:  ec37  call    0x007a6e, 0x0
007eba:  f03d
007ebc:  0e04  movlw   0x04
007ebe:  6ef6  movwf   0xf6, 0x0
007ec0:  6af7  clrf    0xf7, 0x0
007ec2:  0eff  movlw   0xff
007ec4:  ec37  call    0x007a6e, 0x0
007ec6:  f03d
007ec8:  0eff  movlw   0xff
007eca:  ec37  call    0x007a6e, 0x0
007ecc:  f03d
007ece:  0e06  movlw   0x06
007ed0:  6ef6  movwf   0xf6, 0x0
007ed2:  6af7  clrf    0xf7, 0x0
007ed4:  0eff  movlw   0xff
007ed6:  ec37  call    0x007a6e, 0x0
007ed8:  f03d
007eda:  0eff  movlw   0xff
007edc:  ec37  call    0x007a6e, 0x0
007ede:  f03d
007ee0:  0e08  movlw   0x08
007ee2:  6e1f  movwf   0x1f, 0x0
007ee4:  0e20  movlw   0x20
007ee6:  601f  cpfslt  0x1f, 0x0
007ee8:  d00b  bra     0x007f00
007eea:  c01f  movff   0x01f, 0xff6
007eec:  fff6
007eee:  6af7  clrf    0xf7, 0x0
007ef0:  ee00  lfsr    0x0, 0x024
007ef2:  f024
007ef4:  501f  movf    0x1f, 0x0, 0x0
007ef6:  50eb  movf    0xeb, 0x0, 0x0
007ef8:  ec37  call    0x007a6e, 0x0
007efa:  f03d
007efc:  2a1f  incf    0x1f, 0x1, 0x0
007efe:  e1f2  bnz     0x007ee4
007f00:  0012  return  0x0

; ===========================================================================
; function_082 @ 0x007F02 — bootloader_manual_entry
; ---------------------------------------------------------------------------
; Manual firmware-update trigger: requires UP+DOWN held (with SELECT NOT
; pressed) for ~5.5 seconds at boot. Polls PORTC.bit0 (Up) and PORTA.bit2
; (Down) plus PORTA.bit1 (Select). On 11 successful 500 ms iterations
; (0x0B), enters the bootloader's HEX-receive loop instead of dropping
; into the application at 0x000040.
;
; Used by users to recover from a bricked main-image flash, or to
; intentionally force firmware update without the host triggering it via
; function_080's bootloader_prompt path.
; ===========================================================================
007f02:  6a1f  clrf    0x1f, 0x0            ; counter = 0
007f04:  0e0b  movlw   0x0b                  ; need 11 stable 500 ms polls
007f06:  601f  cpfslt  0x1f, 0x0            ; counter < 11?
007f08:  d025  bra     0x007f54             ; threshold reached -> stay in bootloader
007f0a:  0e01  movlw   0x01
007f0c:  b082  btfsc   0x82, 0x0, 0x0
007f0e:  6ae8  clrw
007f10:  6e1c  movwf   0x1c, 0x0
007f12:  0e01  movlw   0x01
007f14:  b480  btfsc   0x80, 0x2, 0x0
007f16:  6ae8  clrw
007f18:  161c  andwf   0x1c, 0x1, 0x0
007f1a:  6ae8  clrw
007f1c:  b280  btfsc   0x80, 0x1, 0x0
007f1e:  0e01  movlw   0x01
007f20:  161c  andwf   0x1c, 0x1, 0x0
007f22:  e013  bz      0x007f4a
007f24:  0e01  movlw   0x01
007f26:  6e0e  movwf   0x0e, 0x0
007f28:  0ef4  movlw   0xf4
007f2a:  ec54  call    0x007aa8, 0x0
007f2c:  f03d
007f2e:  0e01  movlw   0x01
007f30:  b082  btfsc   0x82, 0x0, 0x0
007f32:  6ae8  clrw
007f34:  6e1c  movwf   0x1c, 0x0
007f36:  0e01  movlw   0x01
007f38:  b480  btfsc   0x80, 0x2, 0x0
007f3a:  6ae8  clrw
007f3c:  161c  andwf   0x1c, 0x1, 0x0
007f3e:  6ae8  clrw
007f40:  b280  btfsc   0x80, 0x1, 0x0
007f42:  0e01  movlw   0x01
007f44:  161c  andwf   0x1c, 0x1, 0x0
007f46:  e001  bz      0x007f4a
007f48:  8382  bsf     0x82, 0x1, 0x1
007f4a:  0e0a  movlw   0x0a
007f4c:  ec53  call    0x007aa6, 0x0
007f4e:  f03d
007f50:  2a1f  incf    0x1f, 0x1, 0x0
007f52:  e1d8  bnz     0x007f04
007f54:  0012  return  0x0
007f56:  df9e  rcall   0x007e94
007f58:  9294  bcf     0x94, 0x1, 0x0
007f5a:  928b  bcf     0x8b, 0x1, 0x0
007f5c:  68a9  setf    0xa9, 0x0
007f5e:  0e01  movlw   0x01
007f60:  ec2a  call    0x007a54, 0x0
007f62:  f03d
007f64:  0e01  movlw   0x01
007f66:  6e0e  movwf   0x0e, 0x0
007f68:  0e2c  movlw   0x2c
007f6a:  ec54  call    0x007aa8, 0x0
007f6c:  f03d
007f6e:  00ff  reset
007f70:  ffff  dw      0xffff
007f72:  ffff  dw      0xffff
007f74:  ffff  dw      0xffff
007f76:  ffff  dw      0xffff
007f78:  ffff  dw      0xffff
007f7a:  ffff  dw      0xffff
007f7c:  ffff  dw      0xffff
007f7e:  ffff  dw      0xffff
007f80:  ffff  dw      0xffff
007f82:  ffff  dw      0xffff
007f84:  ffff  dw      0xffff
007f86:  ffff  dw      0xffff
007f88:  ffff  dw      0xffff
007f8a:  ffff  dw      0xffff
007f8c:  ffff  dw      0xffff
007f8e:  ffff  dw      0xffff
007f90:  ffff  dw      0xffff
007f92:  ffff  dw      0xffff
007f94:  ffff  dw      0xffff
007f96:  ffff  dw      0xffff
007f98:  ffff  dw      0xffff
007f9a:  ffff  dw      0xffff
007f9c:  ffff  dw      0xffff
007f9e:  ffff  dw      0xffff
007fa0:  ffff  dw      0xffff
007fa2:  ffff  dw      0xffff
007fa4:  ffff  dw      0xffff
007fa6:  ffff  dw      0xffff
007fa8:  ffff  dw      0xffff
007faa:  ffff  dw      0xffff
007fac:  ffff  dw      0xffff
007fae:  ffff  dw      0xffff
007fb0:  ffff  dw      0xffff
007fb2:  ffff  dw      0xffff
007fb4:  ffff  dw      0xffff
007fb6:  ffff  dw      0xffff
007fb8:  ffff  dw      0xffff
007fba:  ffff  dw      0xffff
007fbc:  ffff  dw      0xffff
007fbe:  ffff  dw      0xffff
007fc0:  ffff  dw      0xffff
007fc2:  ffff  dw      0xffff
007fc4:  ffff  dw      0xffff
007fc6:  ffff  dw      0xffff
007fc8:  ffff  dw      0xffff
007fca:  ffff  dw      0xffff
007fcc:  ffff  dw      0xffff
007fce:  ffff  dw      0xffff
007fd0:  ffff  dw      0xffff
007fd2:  ffff  dw      0xffff
007fd4:  ffff  dw      0xffff
007fd6:  ffff  dw      0xffff
007fd8:  ffff  dw      0xffff
007fda:  ffff  dw      0xffff
007fdc:  ffff  dw      0xffff
007fde:  ffff  dw      0xffff
007fe0:  ffff  dw      0xffff
007fe2:  ffff  dw      0xffff
007fe4:  ffff  dw      0xffff
007fe6:  ffff  dw      0xffff
007fe8:  ffff  dw      0xffff
007fea:  ffff  dw      0xffff
007fec:  ffff  dw      0xffff
007fee:  ffff  dw      0xffff
007ff0:  ffff  dw      0xffff
007ff2:  ffff  dw      0xffff
007ff4:  ffff  dw      0xffff
007ff6:  ffff  dw      0xffff
007ff8:  ffff  dw      0xffff
007ffa:  ffff  dw      0xffff
007ffc:  ffff  dw      0xffff
007ffe:  ffff  dw      0xffff
200000:  ff  db      0xff
200001:  ff  db      0xff
200002:  ff  db      0xff
200003:  ff  db      0xff
200004:  ff  db      0xff
200005:  ff  db      0xff
200006:  ff  db      0xff
200007:  ff  db      0xff
300000:  ff  db      0xff
300001:  01  db      0x01
300002:  1f  db      0x1f
300003:  00  db      0x00
300004:  ff  db      0xff
300005:  00  db      0x00
300006:  80  db      0x80
300007:  ff  db      0xff
300008:  ff  db      0xff
300009:  ff  db      0xff
30000a:  ff  db      0xff
30000b:  ff  db      0xff
30000c:  ff  db      0xff
30000d:  ff  db      0xff
f00000:  00    db      0x00
f00001:  00    db      0x00
f00002:  00    db      0x00
f00003:  00    db      0x00
f00004:  00    db      0x00
f00005:  00    db      0x00
f00006:  00    db      0x00
f00007:  00    db      0x00
f00008:  00    db      0x00
f00009:  00    db      0x00
f0000a:  00    db      0x00
f0000b:  00    db      0x00
f0000c:  00    db      0x00
f0000d:  00    db      0x00
f0000e:  00    db      0x00
f0000f:  00    db      0x00
f00010:  00    db      0x00
f00011:  00    db      0x00
f00012:  00    db      0x00
f00013:  00    db      0x00
f00014:  00    db      0x00
f00015:  01    db      0x01
f00016:  01    db      0x01
f00017:  01    db      0x01
f00018:  01    db      0x01
f00019:  01    db      0x01
f0001a:  01    db      0x01
f0001b:  01    db      0x01
f0001c:  01    db      0x01
f0001d:  01    db      0x01
f0001e:  01    db      0x01
f0001f:  01    db      0x01
f00020:  01    db      0x01
f00021:  01    db      0x01
f00022:  01    db      0x01
f00023:  01    db      0x01
f00024:  01    db      0x01
f00025:  01    db      0x01
f00026:  01    db      0x01
f00027:  00    db      0x00
f00028:  00    db      0x00
f00029:  00    db      0x00
f0002a:  00    db      0x00
f0002b:  00    db      0x00
f0002c:  00    db      0x00
f0002d:  00    db      0x00
f0002e:  00    db      0x00
f0002f:  00    db      0x00
f00030:  00    db      0x00
f00031:  00    db      0x00
f00032:  00    db      0x00
f00033:  ff    db      0xff
f00034:  ff    db      0xff
f00035:  ff    db      0xff
f00036:  ff    db      0xff
f00037:  ff    db      0xff
f00038:  ff    db      0xff
f00039:  ff    db      0xff
f0003a:  ff    db      0xff
f0003b:  ff    db      0xff
f0003c:  ff    db      0xff
f0003d:  ff    db      0xff
f0003e:  ff    db      0xff
f0003f:  ff    db      0xff
f00040:  ff    db      0xff
f00041:  ff    db      0xff
f00042:  ff    db      0xff
f00043:  ff    db      0xff
f00044:  ff    db      0xff
f00045:  ff    db      0xff
f00046:  ff    db      0xff
f00047:  ff    db      0xff
f00048:  ff    db      0xff
f00049:  ff    db      0xff
f0004a:  ff    db      0xff
f0004b:  ff    db      0xff
f0004c:  ff    db      0xff
f0004d:  ff    db      0xff
f0004e:  ff    db      0xff
f0004f:  ff    db      0xff
f00050:  ff    db      0xff
f00051:  ff    db      0xff
f00052:  ff    db      0xff
f00053:  ff    db      0xff
f00054:  ff    db      0xff
f00055:  ff    db      0xff
f00056:  ff    db      0xff
f00057:  ff    db      0xff
f00058:  ff    db      0xff
f00059:  ff    db      0xff
f0005a:  ff    db      0xff
f0005b:  ff    db      0xff
f0005c:  ff    db      0xff
f0005d:  ff    db      0xff
f0005e:  ff    db      0xff
f0005f:  ff    db      0xff
f00060:  ff    db      0xff
f00061:  ff    db      0xff
f00062:  ff    db      0xff
f00063:  ff    db      0xff
f00064:  ff    db      0xff
f00065:  ff    db      0xff
f00066:  ff    db      0xff
f00067:  ff    db      0xff
f00068:  ff    db      0xff
f00069:  ff    db      0xff
f0006a:  ff    db      0xff
f0006b:  ff    db      0xff
f0006c:  ff    db      0xff
f0006d:  ff    db      0xff
f0006e:  ff    db      0xff
f0006f:  ff    db      0xff
f00070:  01    db      0x01
f00071:  06    db      0x06
f00072:  30    db      0x30                                 ; '0'
f00073:  01    db      0x01
f00074:  ff    db      0xff
f00075:  ff    db      0xff
f00076:  ff    db      0xff
f00077:  ff    db      0xff
f00078:  ff    db      0xff
f00079:  ff    db      0xff
f0007a:  ff    db      0xff
f0007b:  ff    db      0xff
f0007c:  ff    db      0xff
f0007d:  ff    db      0xff
f0007e:  ff    db      0xff
f0007f:  ff    db      0xff
f00080:  ff    db      0xff
f00081:  ff    db      0xff
f00082:  ff    db      0xff
f00083:  ff    db      0xff
f00084:  ff    db      0xff
f00085:  ff    db      0xff
f00086:  ff    db      0xff
f00087:  ff    db      0xff
f00088:  ff    db      0xff
f00089:  ff    db      0xff
f0008a:  ff    db      0xff
f0008b:  ff    db      0xff
f0008c:  ff    db      0xff
f0008d:  ff    db      0xff
f0008e:  ff    db      0xff
f0008f:  ff    db      0xff
f00090:  ff    db      0xff
f00091:  ff    db      0xff
f00092:  ff    db      0xff
f00093:  ff    db      0xff
f00094:  ff    db      0xff
f00095:  ff    db      0xff
f00096:  ff    db      0xff
f00097:  ff    db      0xff
f00098:  ff    db      0xff
f00099:  ff    db      0xff
f0009a:  ff    db      0xff
f0009b:  ff    db      0xff
f0009c:  ff    db      0xff
f0009d:  ff    db      0xff
f0009e:  ff    db      0xff
f0009f:  ff    db      0xff
f000a0:  ff    db      0xff
f000a1:  ff    db      0xff
f000a2:  ff    db      0xff
f000a3:  ff    db      0xff
f000a4:  ff    db      0xff
f000a5:  ff    db      0xff
f000a6:  ff    db      0xff
f000a7:  ff    db      0xff
f000a8:  ff    db      0xff
f000a9:  ff    db      0xff
f000aa:  ff    db      0xff
f000ab:  ff    db      0xff
f000ac:  ff    db      0xff
f000ad:  ff    db      0xff
f000ae:  ff    db      0xff
f000af:  ff    db      0xff
f000b0:  ff    db      0xff
f000b1:  ff    db      0xff
f000b2:  ff    db      0xff
f000b3:  ff    db      0xff
f000b4:  ff    db      0xff
f000b5:  ff    db      0xff
f000b6:  ff    db      0xff
f000b7:  ff    db      0xff
f000b8:  ff    db      0xff
f000b9:  ff    db      0xff
f000ba:  ff    db      0xff
f000bb:  ff    db      0xff
f000bc:  ff    db      0xff
f000bd:  ff    db      0xff
f000be:  ff    db      0xff
f000bf:  ff    db      0xff
f000c0:  ff    db      0xff
f000c1:  ff    db      0xff
f000c2:  ff    db      0xff
f000c3:  ff    db      0xff
f000c4:  ff    db      0xff
f000c5:  ff    db      0xff
f000c6:  ff    db      0xff
f000c7:  ff    db      0xff
f000c8:  ff    db      0xff
f000c9:  ff    db      0xff
f000ca:  ff    db      0xff
f000cb:  ff    db      0xff
f000cc:  ff    db      0xff
f000cd:  ff    db      0xff
f000ce:  ff    db      0xff
f000cf:  ff    db      0xff
f000d0:  ff    db      0xff
f000d1:  ff    db      0xff
f000d2:  ff    db      0xff
f000d3:  ff    db      0xff
f000d4:  ff    db      0xff
f000d5:  ff    db      0xff
f000d6:  ff    db      0xff
f000d7:  ff    db      0xff
f000d8:  ff    db      0xff
f000d9:  ff    db      0xff
f000da:  ff    db      0xff
f000db:  ff    db      0xff
f000dc:  ff    db      0xff
f000dd:  ff    db      0xff
f000de:  ff    db      0xff
f000df:  ff    db      0xff
f000e0:  ff    db      0xff
f000e1:  ff    db      0xff
f000e2:  ff    db      0xff
f000e3:  ff    db      0xff
f000e4:  ff    db      0xff
f000e5:  ff    db      0xff
f000e6:  ff    db      0xff
f000e7:  ff    db      0xff
f000e8:  ff    db      0xff
f000e9:  ff    db      0xff
f000ea:  ff    db      0xff
f000eb:  ff    db      0xff
f000ec:  ff    db      0xff
f000ed:  ff    db      0xff
f000ee:  ff    db      0xff
f000ef:  ff    db      0xff
f000f0:  ff    db      0xff
f000f1:  ff    db      0xff
f000f2:  ff    db      0xff
f000f3:  ff    db      0xff
f000f4:  ff    db      0xff
f000f5:  ff    db      0xff
f000f6:  ff    db      0xff
f000f7:  ff    db      0xff
f000f8:  ff    db      0xff
f000f9:  ff    db      0xff
f000fa:  ff    db      0xff
f000fb:  ff    db      0xff
f000fc:  ff    db      0xff
f000fd:  ff    db      0xff
f000fe:  ff    db      0xff
f000ff:  02    db      0x02
