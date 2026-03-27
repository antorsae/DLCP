# DLCP Firmware Semantic Function Map

Working document: maps auto-generated labels (`function_NNN`, `label_NNN`)
to human-readable names based on code analysis, simulation evidence, and
patch comments.

Status: **DRAFT r3** — opus-4.6 + codex-cli cross-reviewed 2026-03-27.  r2→r3:
removed MAIN/CONTROL namespace collisions (function_074, function_083, function_111),
fixed BF protocol table (05/06/07 swapped, removed phantom BF/04, added BF/29),
added version-divergence notes for CONTROL functions 030–035 and 0x01F bits 4/5,
added missing labels (label_201, label_216), fixed typos and cross-references.

## Conventions

- **Confidence**: `certain` = verified by multiple sources or direct code evidence;
  `likely` = strong circumstantial evidence; `uncertain` = best guess from context.
- Addresses are for the primary version (MAIN V2.3, CONTROL V1.4) unless noted.
- Where V1.6b address differs, shown in parentheses.

---

## MAIN Functions (PIC18F2455)

### Command dispatch & gate

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_005 | `cmd_dispatch_gated` | 0x18F2 | certain | Gates on 0x5E.bit3; label_144 returns 0 if gate closed. V162B_RECONNECT_WAKE_BUG. |
| function_100 | `standby_event_dispatch` | 0x4796 | certain | Checks 0x7E.bit2 + 0x5E.bit3; calls function_024 or function_051. MAIN_AN0_STANDBY_TRACE. |
| function_102 | `periodic_service_loop` | 0x47CE | certain | Calls function_100, runs label_529 AN0 monitor. |
| function_103 | `report_cmd29_status` | 0x47FC | certain | Sends BF/29/<bit1 of 0x5E>. NOT the standby status (that's in function_050). Codex-cli corrected. |

### Standby / wake / boot

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_024 | `adc_boot_gate` | 0x2D8C | certain | Waits AN0 >= 0x0236 (label_341). Bug M9: no timeout. MAIN_AN0_STANDBY_TRACE. |
| function_051 | `hw_standby_shutdown` | 0x3C0C | certain | I2C DSP shutdown, baud rate change, OSCCON switch, Timer0 disable, USB disable. V162B_RECONNECT_WAKE_BUG. |
| function_116 | `usb_shutdown` | varies | likely | Clears UCON; final step of function_051. |

### I2C / MSSP (DSP communication)

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_056 | `i2c_byte_tx` | 0x3EB8 | certain | Writes SSPBUF, checks WCOL, waits SSPIF/BF. No ACKSTAT check. Codex-cli confirmed. |
| function_072 | `i2c_tas3108_reg1f_write` | 0x4368 | certain | START, 0x68 (TAS3108 write addr), 0x1F, 0x00 ×3, data, STOP. Codex-cli review: write, NOT read. |
| function_081 | `i2c_tas3108_coeff_write` | 0x44E4 | certain | TAS3108 volume/coefficient write: 0x68, 0x30, bytes from 0x55-0x58. Codex-cli confirmed address. |
| function_093 | `i2c_secondary_dev_write` | 0x46C0 | certain | START, 0xE2 (secondary dev 0x71 write addr), reg/data, STOP. NOT TAS3108. |
| function_113 | `i2c_wait_bus_idle` | 0x48B6 | certain | Spins while SSPCON2[4:0]!=0 or SSPSTAT.R!=0. Bug M1: no timeout. |
| function_067 | `i2c_secondary_dev_random_read` | 0x423C | certain | Sends 0xE2, reg, repeated START, 0xE3, reads 1 byte, NACK, STOP. Codex-cli: address corrected. |
| function_101 | `mssp_hard_reset` | 0x47B2 | certain | clrf SSPCON1, clrf SSPCON2, re-enables SSPEN. Used by V2.5 recovery. Codex-cli: address corrected. |

### UART serial

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_111 | `uart_tx_byte_blocking` | 0x4896 | certain | Waits TXSTA.TRMT (label_605: tight loop, no timeout = bug M2), writes TXREG. |
| function_087 | `rx_ring_read` | 0x45FA | likely | Reads from native ring at 0x0200; checks write_idx != read_idx. |
| function_050 | `send_status_burst` | 0x3B96 | certain | Emits BF/05, BF/07, BF/03, BF/06, BF/1D from cached RAM. Includes standby status. NOT DSP readback. Codex-cli verified. |
| function_048 | `uart_rx_with_framing` | 0x3AA4 | likely | Waits for ':' + Intel HEX record + CR/LF (firmware update mode). |
| function_083 | `uart_config` | 0x4546 | certain | Sets SPBRG=0x7F, TXSTA, RCSTA for 31,250 baud. Previously misattributed to CONTROL. |

### Flash / EEPROM

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_025 | `flash_write` | 0x2E6E | certain | Program memory write via TBLWT*. Patched for A/B preset remap in V2.4+. |
| function_054 | `flash_erase` | 0x3DAC | certain | Erases 64-byte blocks. Patched for preset remap. |
| function_061 | `flash_read` | 0x4028 | certain | TBLRD*+ loop, copies to RAM. Patched for preset remap. |
| function_069 | `flash_write_with_gie_off` | 0x42B8 | likely | GIE=0 during write. Bug M7: GIE never restored before return. |
| function_074 | `tblrd_lookup` | 0x43C8 | certain | Masks W, adds 0x19, TBLRD from 0x10xx table. Previously misidentified as flash_page_erase at 0x7A92. |
| function_075 | `eeprom_write_blocking` | 0x43EA | certain | 4ms GIE=0 window. Bug M3: guarantees OERR during serial RX. |

### Timer / delay / misc

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_079 | `timer3_blocking_delay` | 0x449E | likely | Up to 1500ms. Bug M5: no timeout awareness. |
| function_045 | `adaptive_baud_select` | 0x3926 | likely | Selects baud rate based on RC2 strap. |
| function_114 | `hard_reset` | 0x48D4 | certain | Clears INTCON, executes RESET instruction. Panic endpoint. |
| function_127 | `usb_disconnect_handler` | 0x4962 | likely | Only place CLRWDT appears. Bug M8. |
| function_003 | `fw_update_relay` | 0x15CE | likely | USB HID → Intel HEX UART relay for firmware update. |

---

## MAIN Labels (PIC18F2455)

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| label_144 | `cmd_gate_reject` | varies | certain | `return 0` when 0x5E.bit3 clear. V162B_RECONNECT_WAKE_BUG. |
| label_149 | `parser_route_phase_handler` | 0x1C36 | likely | Parser phase logic using 0x5E.bit0. NOT cmd=0x04 handler. Codex-cli corrected. |
| label_154 | `wake_request_handler` | 0x1C7E | certain | cmd=0x03 data=0x01: sets 0x5E.bit3, sets 0x7E.bit2. MAIN_AN0_STANDBY_TRACE. |
| label_158 | `cmd03_mute_on_handler` | varies | certain | cmd=0x03 data=0x02: sets mute bits 0x5E.4/5, sets 0x7E.5 dirty. Codex-cli added. |
| label_166 | `cmd03_mute_off_handler` | varies | certain | cmd=0x03 data=0x03: clears mute. Codex-cli added. |
| label_167 | `cmd03_subdispatch` | 0x1CFC | certain | Routes cmd=0x03 data 0/1/2/3 → standby/wake/mute-on/mute-off. Codex-cli added. |
| label_168 | `cmd04_status_response` | 0x1D0E | certain | Calls function_050 (send_status_burst). Codex-cli added. |
| label_169 | `cmd06_input_select_handler` | 0x1D14 | likely | Updates 0x099/0x0B3 from command data. Codex-cli added. |
| label_155 | `standby_request_handler` | 0x1C9A | certain | cmd=0x03 data=0x00: clears 0x5E.bit3, sets 0x7E.bit2. |
| label_171 | `volume_cmd_handler` | 0x1D2A | certain | Computes 32-bit volume into 0x06E-0x071, compares with 0x066-0x069, sets dirty bit 0x7E.bit3 on change. State committed BEFORE I2C write. Codex-cli: address corrected, upgraded to certain. |
| label_185 | `cmd_dispatch_xor_chain` | 0x1E2E | likely | XOR chain routing cmd 0x03-0x1E to handlers. |
| label_341 | `adc_boot_gate_loop` | 0x2D8C | certain | Waits AN0 >= 0x0236. Inside function_024. |
| label_529 | `an0_hysteresis_monitor` | 0x416E | certain | Runtime ADC check. High arm 0x0229, low trip 0x0228. |
| label_605 | `uart_tx_trmt_busywait` | 0x489A | certain | Bug M2: infinite TRMT poll. |
| label_607 | `main_processing_loop` | 0x48CA | certain | Top of main loop: calls function_026 / function_102. |

**ISR labels** (function_049 at 0x3B1E):

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_049 | `main_isr_dispatch` | 0x3B1E | certain | Handles USBIF, T0IF, TMR3IF, RCIF, OERR. Codex-cli added. |
| label_479 | `timer0_irq_handler` | varies | certain | T0IF handler. |
| label_480 | `timer3_irq_handler` | varies | certain | TMR3IF handler. |
| label_482 | `uart_rx_irq_enqueue` | 0x3B5C | certain | Reads RCREG, stores to ring at 0x0200+wr. |
| label_483 | `uart_oerr_recover` | 0x3B7C | certain | Toggles CREN. Bug M4: no FIFO drain. Resets 0x098. |

---

## MAIN Registers

### RAM variables

| Address | Bits | Semantic name | Evidence |
|---------|------|--------------|----------|
| 0x05E | bit 3 | `active_gate` | 1=open (commands processed), 0=closed (commands dropped at label_144). |
| 0x05E | bit 2 | `preset_b_active` | 1=preset B, 0=preset A. V2.4+ patch only; no stock V2.3 use. |
| 0x05E | bit 0 | `rx_route_is_b1` | Set on route 0xB1, cleared on 0xB0/other. Also forced high by OERR recovery. Codex-cli corrected: NOT oerr_flag. |
| 0x07E | bit 2 | `standby_event_pending` | Set by label_154/155, cleared by function_100 after dispatch. |
| 0x07E | bit 3 | `volume_dirty` | Set by label_171 volume handler. Cleared unconditionally after I2C write attempt (BUG: no success check). |
| 0x066-0x069 | — | `logical_volume` | Cached volume state reported to CONTROL (fire-and-forget). |
| 0x06E-0x071 | — | `computed_volume` | New volume after cmd processing, before DSP write. |
| 0x095 | — | `usb_reinit_pending` | Set to 0x01 by function_116 after USB shutdown; polled/cleared during USB reinit (0x4700/0x4918). Codex-cli corrected: NOT sleep_flag. |
| 0x098 | — | `rx_frame_position` | 0=route, 1=cmd, 2=data in 3-byte frame parser. |
| 0x0C6 | — | `rx_ring_rd` | Read index into 0x0200 ring (192 bytes). |
| 0x0C7 | — | `rx_ring_wr` | Write index. Bug M6: no overflow detection. |

### SFR (hardware)

| Address | PIC name | Semantic context |
|---------|----------|-----------------|
| 0xFAB | RCSTA | `uart_rx_control`. OERR at bit 1, CREN at bit 4, SPEN at bit 7. |
| 0xFAC | TXSTA | `uart_tx_control`. TRMT at bit 1, TXEN at bit 5. |
| 0xFAD | TXREG | `uart_tx_data`. |
| 0xFAE | RCREG | `uart_rx_data`. 2-byte FIFO. |
| 0xFAF | SPBRG | `uart_baud_low`. Stock=0x1F (31,250 baud at 16MHz). |
| 0xFC5 | SSPCON2 | `i2c_control`. SEN(0), RSEN(1), PEN(2), RCEN(3), ACKEN(4), ACKDT(5), **ACKSTAT(6)** (NEVER checked = DSP deafness bug). |
| 0xFC6 | SSPCON1 | `i2c_config`. WCOL(7), SSPEN(5). |
| 0xFC7 | SSPSTAT | `i2c_status`. BF(0), R/W(2), P(4). |
| 0xFC9 | SSPBUF | `i2c_data_buffer`. |
| 0xFD3 | OSCCON | `osc_control`. SCS1 at bit 1. function_051 sets SCS1 for standby. |
| 0xFD5 | T0CON | `timer0_control`. TMR0ON at bit 7. |
| 0xFF2 | INTCON | `interrupt_control`. GIE at bit 7, PEIE at bit 6, T0IE at bit 5. |

---

## CONTROL Functions (PIC18F25K20)

### LCD

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_001 | `lcd_command` | 0x0066 | certain | Writes command byte to LCD via nibble interface. |
| function_004 | `lcd_string_write` | 0x00DC | certain | TBLRD*+ loop; reads string from program memory, calls function_005 per char. |
| function_005 | `lcd_char_write` | 0x00EC | certain | Writes single character to LCD. |

### EEPROM

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_010 | `eeprom_read_byte` | 0x0196 | certain | EEADR=W, RD, returns EEDATA. |
| function_011 | `eeprom_write_byte` | 0x01A2 | certain | EEDATA=W, WREN, unlock 0x55/0xAA, WR, polls WR. |

### Timing

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_012 | `delay_short` | 0x01BC | certain | Count in W. ~200 cycles per unit. Used for 200ms delays (W=0xC8). |

### IR / buttons

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_017 | `ir_rc5_decode` | 0x021E | certain | In ISR. Blocks ~10ms (28,160 cycles). Collects 16 RC5 bits via RB5 polling. Bug C3: guarantees OERR. |
| function_023 | `button_scan_debounce` | 0x08C8 (0x08AC) | certain | Reads 6 GPIOs, debounces (threshold 4), outputs to 0x0BE. |
| function_043 | `ir_dispatch` | 0x0E2E (0x17E8) | likely | Checks IR_ARMED (0x01F.0), dispatches to label_166. |

### UART

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_019 | `rx_parser_entry` | 0x044A | certain | Checks OERR, reads RX ring, parses 3-byte frames. Bug C4: no FIFO drain on OERR. |
| function_020 | `tx_byte_enqueue` | 0x0608 (0x05EC) | certain | Enqueues to 48-byte TX ring. Bug C6: label_068 busy-wait if full. |

### Serial protocol

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_026 | `settings_load_eeprom` | 0x0A62 (0x0A46) | certain | Reads EEPROM, loads display state to 0x0BF, params to 0x0C1-0x0CC. |
| function_027 | `serial_tx_routed_frame` | 0x0B32 (0x0B16) | certain | Constructs [0xB0+route, cmd, data], calls function_020 3x. |
| function_028 | `full_sync_burst` | 0x0B52 (0x0B36) | certain | Sends ~6 channel config frames + volume + input via function_027. |
| function_029 | `poll_frame_send` | 0x0BD6 (0x0B64) | certain | Sends [B1, 04, 00] status poll to MAIN. |
| function_030 | `input_frame_send` | 0x0BEE (0x0C22) | certain | V1.6b: sends input selection frame. V1.4: sends cmd 0x17 channel config. Codex-cli added. |
| function_031 | `volume_frame_send` | 0x0C04 (0x0C40) | certain | V1.6b: sends volume setting frame. V1.4: sends cmd 0x18 channel config. Codex-cli corrected. |
| function_033 | `mute_frame_send` | 0x0C30 (0x0C7C) | certain | V1.6b: sends mute on/off frame. V1.4: sends cmd 0x1A channel config. Codex-cli added. |
| function_034 | `standby_wake_broadcast` | 0x0C46 (0x0C98) | certain | V1.6b: checks 0x01F.bit1, sends [B0, 03, 01] (wake) or [B0, 03, 00] (standby). V1.4: sends cmd 0x1B channel config. V162B_RECONNECT_WAKE_BUG. |
| function_035 | `display_loop_iteration` | 0x0C5C (0x0CB2) | certain | V1.6b: one iteration of the display loop, sends status frames, checks buttons/IR. V1.4: sends cmd 0x1C channel config. |

> **Version note (functions 030–035):** These functions were completely refactored
> between V1.4 and V1.6b. In V1.4 they are simple channel-config senders (cmds
> 0x17–0x1C via function_027). In V1.6b they became dedicated input/volume/mute/
> standby/display helpers. Semantic names follow V1.6b (the active development base).

### UI / menu

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_042 | `main_event_loop` | 0x0D24 (0x150E) | certain | Enables RBIE, calls button_scan + rx_parser, checks idle timeout, full-sync counter, handshake sentinels. |
| function_046 | `volume_display_format` | 0x131E | likely | Formats -96.0 to +18.0 dB for LCD. |
| function_082 | `bootloader_manual_entry` | 0x7F02 | certain | Hold UP+DOWN+not-SELECT for ~5.5s. FIRMWARE_UPDATE_MECHANISM. |

### Bootloader

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| function_066 | `bootloader_oerr_handler` | 0x79EC | likely | OERR with timeout counter (unlike function_019). |
| function_080 | `bootloader_prompt_send` | 0x7E60 | likely | Sends `:FW_Upd\r\n`. |

---

## CONTROL Labels

| Auto-name | Semantic name | Address | Confidence | Evidence |
|-----------|--------------|---------|------------|----------|
| label_032 | `isr_entry` | 0x03A6 | certain | High-priority ISR. Handles TXIE, RCIF, RBIF. |
| label_038 | `frame_parse_continue` | varies | likely | Inside function_019 parser. |
| label_068 | `tx_full_busywait` | 0x0628 | certain | Bug C6: no timeout. |
| label_166 | `ir_cmd_dispatch` | 0x0E4C (0x0E54) | likely | Routes IR command to handlers after debounce. |
| label_195 | `app_init` | 0x1092 | likely | Splash screen, backlight, IRQ setup. |
| label_201 | `post_connect_init` | 0x1100 | likely | RAM clear loop, clears 0x01F.bit3 (event_exit), EEPROM marker write, loads settings. V1.62b reconnect exit target. |
| label_204 | `boot_handshake_wait` | 0x11DE | certain | Waits 4 params != 0x80. Bug C1: no timeout. |
| label_205 | `check_connected` | 0x1226 | likely | Tests 0x01F.bit1. |
| label_206 | `display_state_entry` | 0x122C | likely | Menu/volume screen loop entry. |
| label_212 | `reconnect_wait_loop` | 0x12BC | certain | Polls MAIN, waits bit1=1. Bug C2: no timeout. Replaced by V1.62b's reconnect_wait_stub. |
| label_214 | `standby_display` | 0x129E | likely | Prints "Zzz...", waits for button. |
| label_216 | `reconnect_poll_loop` | 0x130A | certain | Polls MAIN (function_029), 200ms delay, parses RX (function_019), checks 0x01F.bit1; loops until connected. Bug C2: no timeout. |
| label_284 | `bootloader_entry` | 0x7800 | certain | Reset vector target. |

---

## CONTROL Registers

### RAM variables

| Address | Bits | Semantic name | Evidence |
|---------|------|--------------|----------|
| 0x01F | bit 0 | `ir_armed` | Set by function_017 ISR, cleared after dispatch. |
| 0x01F | bit 1 | `connected` | Set by BF/03/01 response = DISPLAY mode. |
| 0x01F | bit 2 | `rx_route_seen` | Set when parser latches route byte (0x04B8/0x04CA/0x04D2), cleared at 0x105A. Codex-cli corrected: NOT standby_bus. |
| 0x01F | bit 3 | `event_exit` | Allows function_042 blocking loop to exit. |
| 0x01F | bit 4 | V1.4: `mute_state`; V1.5b+: `display_refresh_pending` | **V1.4:** mute flag (bsf/bcf 0x4 at 0x0538/0x054E). **V1.5b/V1.6b:** display refresh flag; mute moved to bit 5. |
| 0x01F | bit 5 | V1.5b+: `mute_state` | 1=muted. V1.5b/V1.6b only (bit 4 in V1.4). Set/cleared by cmd=0x03 data=0x02/0x03; toggled by UI at 0x0E68. |
| 0x01F | bit 6 | `preset_b_active` | V1.62b patch only: 1=preset B. No stock V1.6b use. |
| 0x01D | — | `ir_decoded_cmd` | RC5 command byte from function_017. |
| 0x01E | — | `ir_decoded_addr` | RC5 address byte from function_017. |
| 0x027 | — | `tx_data_staging` | Byte to enqueue via function_020. |
| 0x02F | — | `rx_parsed_cmd` | Command byte from RX parser. |
| 0x030 | — | `rx_parsed_data` | Data byte from RX parser. |
| 0x096 | — | `tx_ring_rd` | TX ring read index. |
| 0x097 | — | `tx_ring_wr` | TX ring write index. |
| 0x098 | — | `rx_ring_rd` | RX ring read index (48-byte ring at 0x066). |
| 0x099 | — | `rx_ring_wr` | RX ring write index. |
| 0x09D:0x09E | — | `idle_timeout_counter` | 16-bit. Initial=0xEA61 (59,969). Decrements each function_035. Triggers reconnect at 0. |
| 0x09F:0x0A0 | — | `full_sync_counter` | 16-bit. Triggers full_sync_burst at 0x4E20 (20,000). |
| 0x0A6 | — | `frame_position` | Parser state: 0=route, 1=cmd, 2=data. |
| 0x0B8 | — | `handshake_sentinel_1` | Initialized 0x80. Non-0x80 when MAIN responds. Likely ch1 volume from MAIN. |
| 0x0B9 | — | `handshake_sentinel_2` | Same. Likely ch2 volume from MAIN. |
| 0x0A7 | — | `handshake_sentinel_3` | Same. |
| 0x0A1 | — | `handshake_sentinel_4` | Same. |
| 0x0BB | — | `button_debounce_counter` | Increments until stable (threshold 4). |
| 0x0BC | — | `button_last_scan` | Previous raw button state. |
| 0x0BE | — | `button_debounced` | Stable button output. |
| 0x0BF | — | `display_state_index` | Menu screen: 0=Volume, 1=Preset(V1.62b), 2=Input, 3=Setup. |

---

## Serial Protocol Commands

### CONTROL → MAIN (route 0xB0=broadcast, 0xB1=addressed)

| Cmd | Data | Semantic name | Notes |
|-----|------|--------------|-------|
| 0x03 | 0x00 | `standby_enter` | Clears MAIN active_gate. All MAINs. |
| 0x03 | 0x01 | `wake` | Sets MAIN active_gate. All MAINs. |
| 0x03 | 0x02 | `mute_on` | Sets MAIN mute bits. Codex-cli added. |
| 0x03 | 0x03 | `mute_off` | Clears MAIN mute bits. Codex-cli added. |
| 0x04 | 0x00 | `status_poll` | MAIN responds with full status. Bypasses active gate. |
| 0x06 | val | `input_select` | Selects audio input source. |
| 0x07 | val+0xA0 | `volume_set` | Volume level. 0x60=0dB, 0xA0 offset. |
| 0x17-0x1C | data | `channel_N_source_config` | Channels 1-6 source routing. |
| 0x1D | val | `backlight_timeout` | Display timeout setting. |
| 0x1E | addr | `link_address_config` | Current-loop address assignment. |
| 0x20 | 0/1 | `preset_select` | A/B preset toggle. V2.4+ only. |

### MAIN → CONTROL (route 0xBF)

| Cmd | Data | Semantic name | Notes |
|-----|------|--------------|-------|
| 0x03 | 0/1 | `standby_status` | Reports 0x5E.bit3 value. |
| 0x05 | val | `report_05f` | Data from RAM 0x05F. Semantic TBD. |
| 0x06 | val | `current_input` | Input selection from RAM 0x099. |
| 0x07 | val | `current_volume` | Volume: RAM 0x06E + 0x60 offset. NOT DSP readback. |
| 0x18 | 0x01 | `power_on_notify` | Sent at boot. |
| 0x1D | val | `display_timeout` | Display setting from RAM 0x0B8. |
| 0x29 | 0/1 | `cmd29_status` | Bit 1 of 0x5E. Sent by function_103, NOT part of status burst. |

> **Note:** Inbound cmd 0x04 (`status_poll`) triggers function_050 which replies
> with the burst above (BF/05, BF/07, BF/03, BF/06, BF/1D). There is no BF/04
> response frame.

---

## V1.62b Patch-Specific Labels

| Label | Semantic name | Address | Evidence |
|-------|--------------|---------|----------|
| `reconnect_wait_stub` | `v162b_reconnect_entry` | 0x7000+ | Replaces label_212. 4-register handshake with 8-retry soft-recover. |
| `reconnect_wait_loop` | `v162b_reconnect_poll_loop` | 0x7000+ | Poll → delay → parse → handshake check → loop. |
| `reconnect_wait_done` | `v162b_reconnect_exit` | 0x7000+ | Sets connected, sends wake, resets counters, → label_201. |
| `control_uart_soft_recover` | `v162b_uart_reprime` | 0x7000+ | CREN toggle, drain RCREG 2x, clear parser state (0x096-0x099, 0x0A6, 0x02F, 0x030). |
| `parser_entry_stub` | `v162b_oerr_guard` | 0x044A | Checks OERR before stock parser. Calls control_uart_soft_recover if set. |
| `preset_boot_init_wrapper` | `v162b_preset_init` | 0x7000 | Loads EEPROM[0x74], sets 0x01F.6, inits retry counter. |
| `full_sync_entry_stub` | `v162b_preset_retry_hook` | 0x0B36 | Emits one preset frame per sync cycle (retry counter 0x170). |
| `send_preset_frame` | `v162b_preset_broadcast` | 0x7000+ | [B0, 0x20, 0/1] + EEPROM persist + retry queue. |
| `send_preset_frame_txonly` | `v162b_preset_tx_only` | 0x7000+ | [B0, 0x20, 0/1] without EEPROM or retry. |

---

## Known Bug Cross-Reference

| Bug ID | Semantic name | Location | Severity |
|--------|--------------|----------|----------|
| M1 | `i2c_busywait_no_timeout` | 11 sites incl. function_113 | CRITICAL |
| M2 | `uart_tx_trmt_busywait` | function_111 / label_605 | HIGH |
| M3 | `eeprom_write_disables_gie` | function_075 | HIGH |
| M4 | `oerr_no_fifo_drain` | label_483 | HIGH |
| M5 | `timer3_blocking_delay` | function_079 | MEDIUM-HIGH |
| M6 | `rx_ring_no_overflow_detect` | ISR at 0x3B60 | MEDIUM |
| M7 | `flash_write_gie_leak` | function_069 | MEDIUM |
| M8 | `no_clrwdt_main_loop` | function_127 only | MEDIUM |
| M9 | `adc_boot_gate_no_timeout` | function_024 | MEDIUM |
| C1 | `boot_handshake_infinite_wait` | label_204 | CRITICAL |
| C2 | `reconnect_infinite_wait` | label_212 / label_216 | CRITICAL |
| C3 | `ir_decode_blocks_isr_10ms` | function_017 in ISR | HIGH |
| C4 | `oerr_no_fifo_drain` | function_019 | HIGH |
| C5 | `no_frame_resync_timeout` | parser 0x0478-0x0606 | HIGH |
| C6 | `tx_full_busywait` | label_068 | HIGH |
| C7 | `fullsync_burst_saturates_link` | function_028 | HIGH |
| C8 | `no_watchdog_timer` | WDTEN=0 | MEDIUM |
| DSP1 | `i2c_ackstat_never_checked` | function_056, function_081 | CRITICAL |
| DSP2 | `dirty_bit_cleared_unconditionally` | label_171 / 0x07E.bit3 | HIGH |
| DSP3 | `no_dsp_readback` | no TAS3108 read via 0x69 | HIGH |
