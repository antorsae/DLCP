# DLCP Control Unit Firmware - Complete Disassembly Analysis

Historical correction note (2026-03-30):

- This analysis predates the consolidated MCU-target correction in
  `docs/analysis/MCU_TARGET_CORRECTION_2026-03-11.md`.
- Read CONTROL hardware references here as `PIC18F25K20`, not `PIC18F2550`.
- Read MAIN hardware references here as `PIC18F2455`.
- Where older disassembly text uses USB-style SFR names, treat them as legacy
  label names rather than a claim that the CONTROL silicon exposes the same USB
  peripheral block as `PIC18F2550`.

## Executive Summary

The DLCP Control Unit is a PIC18F-based front panel controller providing a user interface (16x2 HD44780 LCD, 6 buttons, RC-5 IR receiver) for the main DLCP audio crossover. It communicates over a **31,250 baud UART** (MIDI standard rate) using a **3-byte binary protocol**: `sync_byte, command, data`. The control board handles volume (-96.0 to +18.0 dB), mute, input selection, standby, per-channel source routing, and backlight management. Up to 6 DLCP units can be daisy-chained with a single control board.

This analysis is based on full PIC18F disassembly of all three firmware versions (V1.4, V1.5b, V1.6b) and cross-referenced with the DLCP main firmware V2.3 (PIC18F2455-class hardware).

---

## Hardware Architecture

### Control Board MCU
| Parameter | Value | Evidence |
|-----------|-------|----------|
| MCU Family | PIC18F25K20-class | Older disassembly symbols used `UEP*`/USB-style names, but the confirmed CONTROL target is `PIC18F25K20`; see MCU-target correction note above |
| Flash | 32 KB (0x0000-0x7FFF) | Hex file: 33,046 bytes including config/EEPROM |
| RAM | ~2 KB | Access bank + Bank 0 usage traced |
| EEPROM | 256 bytes | EEPROM region in hex file |
| Oscillator | **12 MHz XT crystal** | SPBRG=5, BRGH=0, BRG16=0 → 12M/(64×6) = 31,250 |
| UART Baud | 31,250 (MIDI rate) | Confirmed from init code at 0x0366 |
| USB | Present in silicon; not exposed/used as a product interface | Control board has no USB connector in the DLCP system; bootloader update is via the serial link |

### GPIO Configuration (from label_031 at 0x0366)
```
TRISA = 0xDF (1101_1111)
  RA0    = input  (unused)
  RA1    = input  → Button: Select/Mute toggle
  RA2    = input  → Button: Volume Down / Menu Down
  RA3    = input  → Button: Standby
  RA4    = input  → Button: Menu Right
  RA5    = OUTPUT → LCD RS (Register Select)
  RA6-7  = input

TRISB = 0x3C (0011_1100)
  RB0    = OUTPUT → LCD D4 (data bit 4)
  RB1    = OUTPUT → LCD D5 (data bit 5)
  RB2    = input  → LCD D6 (input after init, output during write)
  RB3    = input  → LCD D7 (input after init, output during write)
  RB4    = OUTPUT → LCD E (Enable strobe), set output after init
  RB5    = input  → IR receiver (PORTB-on-change interrupt)
  RB6-7  = output

TRISC = 0xBD (1011_1101)
  RC0    = input  → Button: Volume Up / Menu Up
  RC1    = OUTPUT → Backlight LED
  RC2    = input  (unused)
  RC3    = input  (unused)
  RC4    = input  (unused)
  RC5    = input  → Button: Menu Left
  RC6    = OUTPUT → UART TX (serial to main unit)
  RC7    = input  → UART RX (serial from main unit)

ADCON1 = 0x0F: All analog pins disabled (digital I/O only)
```

### LCD Interface (HD44780, 4-bit mode)
| Signal | Pin | Direction | Function |
|--------|-----|-----------|----------|
| D4-D7 | RB0-RB3 | Output during write | 4-bit data bus (low nibble of port) |
| E | RB4 | Output | Enable strobe (bit-banged) |
| RS | RA5 | Output | Register Select (0=command, 1=data) |
| R/W | Tied LOW | - | Write-only mode |

**Init sequence** (standard HD44780):
`0x33 → 0x33 → 0x22 → 0x28 (4-bit, 2-line) → 0x0C (display on, no cursor) → 0x06 (auto-increment)`

### Button Mapping (from function_023 at 0x08C8)
| Bit in 0x09A | MCU Pin | Label | Function (Volume) | Function (Setup) |
|--------------|---------|-------|--------------------|-------------------|
| 0 | RA3 | Stby | Standby toggle | Standby toggle |
| 1 | RC0 | Up | Volume Up | Navigate Up |
| 2 | RA2 | Down | Volume Down | Navigate Down |
| 3 | RA1 | Select | Mute Toggle | Enter/Confirm |
| 4 | RC5 | Left | Menu Left | Menu Left |
| 5 | RA4 | Right | Menu Right | Menu Right |

- All buttons are **active-low** (XORed with 0xFF in software)
- **Debounce**: 5 consecutive stable readings (counter at 0x0BB, threshold 4)
- **Auto-repeat**: After 12,999 iterations, then every 9,000 iterations

### Front Panel Layout
```
┌─────────────────────────────────────────────────┐
│  [IR]  [Up]                                     │
│                                                 │
│  [Left] [Select] [Right] [Stby]                 │
│                                                 │
│  [────LCD 16x2────]  [Down]                     │
└─────────────────────────────────────────────────┘
```

### Connection to Main Unit
```
┌──────────────┐   CAT5 cable (max 10m)   ┌──────────────┐
│ Control Board │◄─────────────────────────│ Main PIC     │
│ PIC18F25K20  │   4mA current-mode       │ PIC18F2455   │
│ 12 MHz XT    │   optically isolated     │ 48 MHz HSPLL │
│ 31,250 baud  │   via J3 Midi pins       │ 31,250 baud* │
└──────────────┘                          └──────────────┘

* Main PIC switches to 8 MHz internal + SPBRG=0x3F
  when RC2=HIGH (control board detected)
```

---

## Interrupt Service Routine (label_032 at 0x03A6)

Three interrupt sources handled in single ISR (no priority levels, IPEN=0):

### 1. UART TX Interrupt (TXIE + TXIF)
- 48-byte circular TX buffer at 0x036-0x065
- Read pointer: 0x096, Write pointer: 0x097
- On interrupt: read byte from buffer[read_ptr], write to TXREG
- If read_ptr == write_ptr: disable TXIE (buffer empty)
- Pointer wraps at 0x30 (48)

### 2. UART RX Interrupt (RCIF)
- 48-byte circular RX buffer at 0x066-0x095
- Write pointer: 0x099
- On interrupt: read RCREG, store at buffer[write_ptr++]
- Pointer wraps at 0x30 (48)

### 3. PORTB Change Interrupt (RBIF)
- Triggered by change on RB5 (IR receiver)
- Guards: debounce timer (0x01B:0x01C) must be zero, IR armed flag (bit 0 of 0x01F) must be set
- Calls function_017 (IR decoder at 0x021E)
- Stores decoded command in 0x01D, address in 0x01E
- Clears IR armed flag

**Context save**: STATUS (0x019), W (0x01A), BSR (0x002), FSR0 (0x003:0x004)

---

## IR Remote Control (function_017 at 0x021E)

### Protocol: RC-5 (Philips)
- 14-bit Manchester encoded frames
- 36 kHz carrier, demodulated by IR receiver module on RB5
- Format: 2 start bits + 1 toggle + 5 address + 6 command

### Two Configurable Remote Profiles

Selected by register 0x0A7 (the shared `cmd=0x1D` setup byte; values `0x03`
and `0x04` select the RC-5 profile):

**Profile 1 (type 0x04): Custom Hypex remote, address 0x10**

| Register | RC-5 Code | Function |
|----------|-----------|----------|
| 0x021 | 0x32 | Power/Standby toggle |
| 0x022 | 0x33 | Volume Up |
| 0x023 | 0x34 | Volume Down |
| 0x026 | 0x35 | Mute toggle |
| 0x024 | 0x36 | Input cycle up |
| 0x025 | 0x37 | Input cycle down |

**Profile 2 (type 0x03): Standard RC-5 remote, address 0x00**

| Register | RC-5 Code | Function |
|----------|-----------|----------|
| 0x021 | 0x0C | Power/Standby (standard Standby) |
| 0x022 | 0x10 | Volume Up (standard Vol+) |
| 0x023 | 0x11 | Volume Down (standard Vol-) |
| 0x024 | 0x20 | Input cycle up (standard Ch+) |
| 0x025 | 0x21 | Input cycle down (standard Ch-) |
| 0x026 | 0x0D | Mute toggle (standard Mute) |

### IR Command Processing (label_166 at 0x0E4C)

Each IR command has an independent debounce/repeat timer:

| Command | Debounce Ticks | Approx. Delay |
|---------|----------------|---------------|
| Power | 0xC350 (50,000) | ~500 ms |
| Volume +/- | 0x03E8 (1,000) | ~10 ms (fast repeat) |
| Mute | 0x4E20 (20,000) | ~200 ms |
| Input +/- | 0x1B58 (7,000) | ~70 ms |

---

## Serial Communication Protocol

### Physical Layer
- **Baud rate**: 31,250 (MIDI standard)
- **Format**: 8N1 asynchronous
- **Interface**: 4mA optically isolated current-mode (J3 Midi pins)
- **Half-duplex capable**: Both sides TX/RX on same link

### UART Configuration (Control Board)
```
SPBRG   = 0x05
BRGH    = 0  (low speed)
BRG16   = 0  (8-bit baud gen)
SYNC    = 0  (async)
SPEN    = 1  (serial port enable)
TXEN    = 1  (transmit enable)
CREN    = 1  (continuous receive)
Baud = Fosc / (64 × (SPBRG+1)) = 12,000,000 / (64 × 6) = 31,250
```

### Message Format
```
Byte 0: Routing byte (0xBx range)
Byte 1: Command ID
Byte 2: Data byte
```

### Routing Byte Encoding
```
  Bit 7-4: 0xB (header identifier)
  Bit 3-1: Unit address (0-7, for linked multi-DLCP systems)
  Bit 0:   0 = broadcast/link, 1 = local command

  Control board masks with 0xF1 to extract routing:
    Even 0xBx (B0, B2, B4...) → broadcast (forwarded to all units)
    Odd  0xBx (B1, B3, B5..BF) → local (processed by addressed unit only)
```

| Byte | Direction | Meaning |
|------|-----------|---------|
| 0xB0 | Control → Main | Broadcast to all linked DLCPs |
| 0xB1 | Control → Main | Local command (this unit only) |
| 0xBF | Main → Control | Local response (main PIC default) |

### Control Board → Main PIC Commands

Sent via function_020 (TX ring buffer at 0x036):

| Routing | Cmd | Data | Function | Sender |
|---------|-----|------|----------|--------|
| 0xB1 | 0x04 | 0x00 | Request full status | function_029 |
| 0xB0 | 0x07 | 0x00-0x72 | Set volume level | function_038 |
| 0xB0 | 0x06 | 0x00-0x07 | Select input source | function_037 |
| 0xB0+n | 0x03 | 0x00 | Standby OFF | function_041 |
| 0xB0+n | 0x03 | 0x01 | Standby ON | function_041 |
| 0xB0+n | 0x03 | 0x02 | Mute ON | function_040 |
| 0xB0+n | 0x03 | 0x03 | Mute OFF | function_040 |
| 0xB0 | 0x1D | timeout | Backlight timeout | function_039 |
| 0xB0+n | 0x17 | data | Channel 1 source config | function_030 |
| 0xB0+n | 0x18 | data | Channel 2 source config | function_031 |
| 0xB0+n | 0x19 | data | Channel 3 source config | function_032 |
| 0xB0+n | 0x1A | data | Channel 4 source config | function_033 |
| 0xB0+n | 0x1B | data | Channel 5 source config | function_034 |
| 0xB0+n | 0x1C | data | Channel 6 source config | function_035 |
| 0xB0+n | 0x1E | addr | Link address config | function_036 |

### Main PIC → Control Board Responses

Sent via function_111 (blocking TX) with 0xBF sync:

| Routing | Cmd | Data | Meaning | Source |
|---------|-----|------|---------|--------|
| 0xBF | 0x05 | value | Current volume level | function_050 |
| 0xBF | 0x07 | value+0x60 | Current input selection | function_050 |
| 0xBF | 0x03 | 0/1 | Mute status | function_050 |
| 0xBF | 0x06 | value | Source configuration | function_050 |
| 0xBF | 0x1D | value | Display/timeout setting | function_050 |
| 0xBF | 0x29 | 0/1 | Standby status | function_103 |
| 0xBF | 0x18 | 0x01 | Power-on notification | function_107 |

### Receive Processing (Control Board Side)

function_019 (0x044A) reads from RX ring buffer and parses protocol:
1. Check for overrun error (OERR) → toggle CREN to recover
2. Read byte from buffer[0x098]
3. If byte == 0xFE: echo back (diagnostic)
4. If byte ≥ 0x80: check routing (mask 0xF1)
   - Match 0xB1 → local command, start 3-byte collection
   - Match 0xB0 → broadcast, start 3-byte collection
   - No match → ignore
5. State machine (counter 0x0A6) collects bytes 2 and 3:
   - Byte 2 → 0x02F (command ID)
   - Byte 3 → 0x030 (data)
   - Sets bit 2 of 0x01F (command received flag)

### Command Dispatch (Main PIC Side, label_185 at 0x1E2E)

XOR chain matching received command IDs:

| Cmd | Action | PIC Handler |
|-----|--------|-------------|
| 0x03 | Mute control (sub-commands 0-3) | label_167 |
| 0x04 | Request full status → sends function_050 | label_168 |
| 0x06 | Set source configuration | label_169 |
| 0x07 | Set volume (value + 0xA0 signed) | label_171 |
| 0x10 | Query standby status → sends 0x29 | label_175 |
| 0x17 | Set Channel 1 source | label_176 |
| 0x18 | Set Channel 2 source | label_177 |
| 0x19 | Set Channel 3 source | label_178 |
| 0x1A | Set Channel 4 source | label_179 |
| 0x1B | Set Channel 5 source | label_180 |
| 0x1C | Set Channel 6 source | label_181 |
| 0x1D | Set backlight/timeout | label_182 |
| 0x1E | Set DLCP link address | label_184 |

---

## Volume System

### Encoding (Control Board Side)
```
Register 0xB9: volume level
Range: 0x00 to 0x72 (0 to 114 decimal)
Reference: 0x60 (96) = 0.0 dB

Display logic (function_046 at 0x131E):
  if volume < 0x60: show "-" + (0x60 - volume) + ".0 dB"
  if volume == 0x60: show "0.0 dB"
  if volume > 0x60: show "+" + (volume - 0x60) + ".0 dB"

Full range: -96.0 dB to +18.0 dB in 1.0 dB steps
Mute: separate state flag (bit 4 of 0x01F), not volume=0
```

### Volume on Main PIC (Command 0x07)
```
Received value + 0xA0 = signed volume offset
  0x00 + 0xA0 = 0xA0 = -96 (minimum)
  0x60 + 0xA0 = 0x00 = 0 dB
  0x72 + 0xA0 = 0x12 = +18 dB (maximum)
Stored as 32-bit signed in bank0:0x6E-0x71
Change sets dirty flag → I2C write to TAS3108 DSP registers 0x31-0x36
```

---

## Main Loop State Machine

### State Diagram
```
                     ┌─────────────┐
                     │  POWER ON   │
                     └──────┬──────┘
                            │
                     ┌──────▼──────┐
                     │    INIT     │ label_031 (0x0366)
                     │ GPIO, UART  │ → GOTO label_195
                     └──────┬──────┘
                            │
                     ┌──────▼──────┐
                     │  APP INIT   │ label_195 (0x1092)
                     │ Enable IRQs │
                     │ Clear state │
                     │ Read EEPROM │
                     │ Splash:     │
                     │ "Firmware   │
                     │  V1.4"      │
                     │ "Waiting    │
                     │  for DLCP"  │
                     │ Backlight ON│
                     └──────┬──────┘
                            │
                     ┌──────▼──────┐
                     │  WAITING    │ label_204 (0x11DE)
              ┌──────│ Poll main   │
              │      │ Wait for    │
              │      │ response    │──┐
              │      └─────────────┘  │ Any state var != 0x80
              │ All state == 0x80     │
              └───────────────────────┘
                            │
                     ┌──────▼──────┐
                     │   ACTIVE    │ label_205 (0x1226)
         ┌───────────│ Check       │
         │           │ connected   │
         │           └──────┬──────┘
         │                  │ Connected
         │           ┌──────▼──────┐
         │           │ DISPLAY     │ label_206 (0x122C)
         │           │ menu[0xBF]: │
         │           │  0: Volume  │ function_046
         │           │  1: Input   │ function_052
         │           │  2: Setup   │ function_047
         │           │ L/R = cycle │
         │           └──────┬──────┘
         │                  │ Loop while connected
         │                  │
         │ Not connected    │
         │           ┌──────▼──────┐
         └──────────►│  STANDBY    │ label_214 (0x129E)
                     │ "Zzz..."    │
                     │ Wait for    │
                     │ button/cmd  │
                     └──────┬──────┘
                            │ Button or command
                     ┌──────▼──────┐
                     │ RECONNECT   │ label_216 (0x130A)
                     │ "Waiting    │
                     │  for DLCP"  │
                     │ Poll main   │
                     └──────┬──────┘
                            │ Connected
                            └──► ACTIVE
```

### Startup Sequence Detail (label_195 at 0x1092)
1. RC1 output, backlight OFF
2. Disable IR interrupt (clear RBIE), enable UART RX interrupt (RCIE)
3. Enable global + peripheral interrupts (GIE, PEIE)
4. Clear TX/RX buffer pointers, protocol state, IR state
5. Clear 6 × 6-byte channel parameter blocks (0x0C1-0x0E4)
6. **EEPROM version check**: Read EEPROM[0xFF], if ≠ 0x02 → write 0x02
7. **EEPROM config check**: Read EEPROM[0x71], if ≠ 0x04 → write 0x04
8. Initialize display state: volume=0x80, input=0x80, backlight_timeout=0x80, mode=0x80
9. LCD clear, display "Firmware V1.4", backlight ON
10. Wait ~4 seconds, then enter WAITING state

### Event Handler (function_042 at 0x0D24)
Called repeatedly in display loops. Does:
1. Enable IR interrupt (RBIE)
2. Scan buttons (function_023)
3. Process serial RX (function_019)
4. Check idle timeout (counter 0x09D:0x09E)
5. Handle display dimming/timeout (function_043)
6. Return when any event occurs (button press, serial command, IR, or timeout)

---

## Complete Function Map

### Vector Table & Early Code (0x0000-0x0066)
| Address | Label | Function |
|---------|-------|----------|
| 0x0000 | vector_reset | GOTO 0x7800 (bootloader) |
| 0x0008 | vector_int_high | GOTO label_032 (ISR) |
| 0x0040 | label_004 | GOTO label_031 (init, post-bootloader entry) |
| 0x004C | function_000 | LCD clear + init display |

### LCD Primitives (0x0066-0x0190)
| Address | Function | Description |
|---------|----------|-------------|
| 0x0066 | function_001 | LCD command send (RS=0, cursor position) |
| 0x0078 | function_002 | Binary→decimal conversion + LCD output |
| 0x00AA | function_003 | Division helper for decimal conversion |
| 0x00DC | function_004 | Flash string output (TBLRD*+ until null) |
| 0x00EC | function_005 | LCD byte write (4-bit nibble mode) |
| 0x016E | function_008 | LCD nibble write helper (E strobe) |
| 0x0190 | function_009 | Output dispatcher (bit 7 of 0x01 → LCD vs other) |

### EEPROM & Timing (0x0196-0x0218)
| Address | Function | Description |
|---------|----------|-------------|
| 0x0196 | function_010 | EEPROM byte read |
| 0x01A2 | function_011 | EEPROM byte write |
| 0x01BC | function_012 | Millisecond delay (W × 1ms) |
| 0x01BE | function_013 | Long delay (reg_0x0F × W ms) |
| 0x01D8 | function_015 | Microsecond delay (TMR0-based) |
| 0x01F0 | function_016 | Long arithmetic helper |

### IR Decoder (0x021E-0x0364)
| Address | Function | Description |
|---------|----------|-------------|
| 0x021E | function_017 | RC-5 IR frame decoder (RB5 sampling) |

### Hardware Init & ISR (0x0366-0x0448)
| Address | Function | Description |
|---------|----------|-------------|
| 0x0366 | label_031 | Hardware init (GPIO, UART, ADC off) |
| 0x03A6 | label_032 | Interrupt service routine |

### Serial Protocol (0x044A-0x0608)
| Address | Function | Description |
|---------|----------|-------------|
| 0x044A | function_019 | Serial RX processing + protocol parser |
| 0x0460 | label_039 | Read byte from RX buffer |
| 0x048A | label_041 | Routing byte detection (0xB0/0xB1) |
| 0x04F8 | label_049 | Command dispatch after 3-byte collection |
| 0x0608 | function_020 | Serial TX (enqueue to ring buffer, enable TXIE) |

### Button & Display Engine (0x08C8-0x0D22)
| Address | Function | Description |
|---------|----------|-------------|
| 0x08C8 | function_023 | Button scan (6 pins, debounce, auto-repeat) |
| 0x095C | function_024 | Menu header display (16-char string from flash) |
| 0x09AC | function_025 | EEPROM state save (menu + channel params) |
| 0x0A62 | function_026 | LCD contrast/calibration |
| 0x0B32 | function_027 | Generic 3-byte serial message send |
| 0x0B52 | function_028 | Full state broadcast (all 6 channels + globals) |
| 0x0BD6 | function_029 | Status poll request (B1 04 00) |

### Per-Channel Serial Senders (0x0BEE-0x0C92)
| Address | Function | Cmd | Data Source |
|---------|----------|-----|-------------|
| 0x0BEE | function_030 | 0x17 | Channel config block 1 (0x0C1) |
| 0x0C04 | function_031 | 0x18 | Channel config block 2 (0x0C7) |
| 0x0C1A | function_032 | 0x19 | Channel config block 3 (0x0CD) |
| 0x0C30 | function_033 | 0x1A | Channel config block 4 (0x0D3) |
| 0x0C46 | function_034 | 0x1B | Channel config block 5 (0x0D9) |
| 0x0C5C | function_035 | 0x1C | Channel config block 6 (0x0DF) |
| 0x0C72 | function_036 | 0x1E | Link address (0x0E5) |

### Global Command Senders (0x0C94-0x0D22)
| Address | Function | Sends | Description |
|---------|----------|-------|-------------|
| 0x0C94 | function_037 | B0 06 [0xB8] | Input selection |
| 0x0CB2 | function_038 | B0 07 [0xB9] | Volume level |
| 0x0CD0 | function_039 | B0 1D [0xA7] | Backlight timeout |
| 0x0CEE | function_040 | Bx 03 02/03 | Mute ON/OFF |
| 0x0D0A | function_041 | Bx 03 00/01 | Standby OFF/ON |
| 0x0D24 | function_042 | - | Event handler loop (buttons+serial+IR+timeout) |

### Display Screens (0x0E2E-0x1A5E)
| Address | Function | Description |
|---------|----------|-------------|
| 0x0E2E | function_043 | Timeout/dimming handler |
| 0x0E4C | label_166 | IR command dispatch (6 functions) |
| 0x1092 | label_195 | Application entry point |
| 0x11DE | label_204 | WAITING loop (poll until main responds) |
| 0x1226 | label_205 | Main loop (check connected/standby) |
| 0x122C | label_206 | Active mode (menu state switch) |
| 0x129E | label_214 | Standby mode ("Zzz...") |
| 0x131E | function_046 | Volume screen display + button handling |
| 0x1492 | function_047 | Setup screen display + sub-menu navigation |
| 0x15FC | function_049 | Setup sub-menu item execution |
| 0x1730 | function_050 | Setup item configuration |
| 0x1A00 | function_052 | Input screen display + selection |

### Bootloader (0x7800-0x7FFF)
| Address | Function | Description |
|---------|----------|-------------|
| 0x7800 | label_284 | Bootloader entry (USB HID) |
| 0x7AEC | - | "Bootloader mode" string |
| 0x78xx | - | LCD write (own implementation) |
| 0x79xx | - | Intel HEX parser |
| 0x7Axx | - | Flash erase/write |

---

## RAM Map (Access Bank + Bank 0)

### Access Bank (0x000-0x05F)
| Address | Name | Description |
|---------|------|-------------|
| 0x000 | flags | Bit 0: LCD cmd mode, Bit 1: LCD initialized, Bit 3: suppress leading zeros |
| 0x001 | output_target | Bit 7: 1=LCD output, 0=other |
| 0x002 | isr_bsr | ISR context: saved BSR |
| 0x003-004 | isr_fsr0 | ISR context: saved FSR0L:H |
| 0x006 | div_counter | Decimal conversion counter |
| 0x007 | div_flag | Zero-suppression flag |
| 0x00A-00B | temp_match | Routing byte match temp |
| 0x00C | ir_command | Decoded RC-5 6-bit command |
| 0x00D | ir_address | Decoded RC-5 5-bit address / delay multiplier |
| 0x00E | ir_toggle | RC-5 toggle/field bit |
| 0x00F | delay_hi | Long delay high byte |
| 0x010-013 | ir_buffer | IR sample buffer (32 bits) |
| 0x014 | bit_counter | IR bit position |
| 0x015 | lcd_byte | LCD data byte being written |
| 0x017 | lcd_temp | LCD command temp |
| 0x018 | event_flags | Composite event detection temp |
| 0x019-01A | isr_save | ISR context: saved STATUS, W |
| 0x01B-01C | ir_debounce | 16-bit IR repeat timer |
| 0x01D | last_ir_cmd | Last decoded IR command |
| 0x01E | last_ir_addr | Last decoded IR address |
| 0x01F | state_flags | **State flag register** (see below) |
| 0x020 | ir_addr_cfg | Configured RC-5 address to respond to |
| 0x021-026 | ir_cmd_cfg | Configured RC-5 command values (6 functions) |
| 0x027 | temp / button_raw | General temp, also raw button accumulator |
| 0x028 | loop_counter | Channel iteration counter |
| 0x029-02A | str_base | String table base address (L:H) |
| 0x02B-02C | str_calc | String address calculation temps |
| 0x02F | uart_cmd | Received UART command ID |
| 0x030 | uart_data | Received UART data byte |
| 0x033 | tx_unit | TX message: unit address offset |
| 0x034 | tx_cmd | TX message: command ID |
| 0x035 | tx_data | TX message: data byte |

### State Flags Register (0x01F)
| Bit | Name | Meaning |
|-----|------|---------|
| 0 | IR_ARMED | IR decoder ready to accept next frame |
| 1 | CONNECTED | Main DLCP unit is connected and responding |
| 2 | CMD_RECEIVED | Serial command has been received and parsed |
| 3 | REFRESH | LCD display needs refresh |
| 4 | MUTE | Mute state active |

### Bank 0 (0x060-0x0FF)
| Address | Name | Description |
|---------|------|-------------|
| 0x036-065 | tx_buffer | TX ring buffer (48 bytes) |
| 0x066-095 | rx_buffer | RX ring buffer (48 bytes) |
| 0x096 | tx_rd_ptr | TX buffer read pointer |
| 0x097 | tx_wr_ptr | TX buffer write pointer |
| 0x098 | rx_rd_ptr | RX buffer read pointer |
| 0x099 | rx_wr_ptr | RX buffer write pointer |
| 0x09A | btn_edge | Debounced button state (edge-detected bitmap) |
| 0x09B-09C | btn_repeat | Button auto-repeat timer (16-bit) |
| 0x09D-09E | idle_timer | Display idle/dim timeout (16-bit) |
| 0x09F-0A0 | comm_idle | Communication idle counter |
| 0x0A1 | raw_status | Raw status byte from MAIN (also boot sentinel #4) |
| 0x0A4 | setup_max | Setup sub-menu max items |
| 0x0A5 | setup_sel | Setup sub-menu current selection |
| 0x0A6 | proto_state | Serial protocol state machine counter |
| 0x0A7 | cmd1d_setting | Shared cmd `0x1D` setup byte; used for backlight/timeout state and the local IR profile selector |
| 0x0B0-0B3 | tick_count | 32-bit tick counter |
| 0x0B4-0B5 | vol_preset | Volume preset/dim values |
| 0x0B6 | rx_byte | Current UART byte being processed |
| 0x0B8 | input_sel | Current input source selection (0x00-0x07) |
| 0x0B9 | volume | Current volume (0x00-0x72 = -96.0 to +18.0 dB) |
| 0x0BA | setup_sub | Setup sub-menu item selection |
| 0x0BB | btn_stable | Button debounce stable count |
| 0x0BC | btn_raw | Raw button state (current scan) |
| 0x0BD | btn_prev | Previous debounced button state |
| 0x0BE | btn_debounced | Current debounced button state |
| 0x0BF | menu_state | Menu screen (0=Volume, 1=Input, 2=Setup) |
| 0x0C0 | param_misc | Miscellaneous parameter |
| 0x0C1-0C6 | ch_param_1 | Channel parameter block 1 (cmd 0x17) |
| 0x0C7-0CC | ch_param_2 | Channel parameter block 2 (cmd 0x18) |
| 0x0CD-0D2 | ch_param_3 | Channel parameter block 3 (cmd 0x19) |
| 0x0D3-0D8 | ch_param_4 | Channel parameter block 4 (cmd 0x1A) |
| 0x0D9-0DE | ch_param_5 | Channel parameter block 5 (cmd 0x1B) |
| 0x0DF-0E4 | ch_param_6 | Channel parameter block 6 (cmd 0x1C) |
| 0x0E5-0EA | link_params | Link address parameters (cmd 0x1E) |

---

## String Data Table (Program Flash)

### Startup & Status Strings (0x0304-0x0366)
| Address | String (16 chars) | Usage |
|---------|-------------------|-------|
| 0x0304 | `"Firmware V"` | Boot splash line 1 prefix |
| 0x0310 | `"Waiting for DLCP"` | Boot splash line 2 |
| 0x0322 | `"Zzz...          "` | Standby mode LCD line 1 |
| 0x0334 | `"Waiting for DLCP"` | Reconnection LCD line 2 |
| 0x0346 | `"dB           "` | Volume display suffix |
| 0x0354 | `"Mute            "` | Mute indicator (LCD line 2) |

### Menu Header Strings (0x1062-0x1092)
| Address | String (16 chars) | Menu State |
|---------|-------------------|------------|
| 0x1062 | `"Volume:         "` | 0 |
| 0x1072 | `"Input:          "` | 1 |
| 0x1082 | `"Setup           "` | 2 |

### Setup Sub-Menu Strings (0x1422-0x1492)
| Address | String (16 chars) | Usage |
|---------|-------------------|-------|
| 0x1422 | `"DLCP 1          "` | Unit 1 (V1.4/V1.5b only) |
| 0x1432 | `"DLCP 2          "` | Unit 2 |
| 0x1442 | `"DLCP 3          "` | Unit 3 |
| 0x1452 | `"DLCP 4          "` | Unit 4 |
| 0x1462 | `"DLCP 5          "` | Unit 5 |
| 0x1472 | `"DLCP 6          "` | Unit 6 |
| 0x1482 | `"BL Timeout      "` | Backlight timeout |

---

## EEPROM Layout (256 bytes)

| Offset | Default | Description |
|--------|---------|-------------|
| 0x00 | - | Menu state (saved on change) |
| 0x01 | - | Setup sub-menu selection |
| 0x02 | - | Display mode parameter |
| 0x03-0x08 | - | Channel params block 1 (6 bytes, cmd 0x17 data) |
| 0x09-0x0E | - | Channel params block 2 (6 bytes, cmd 0x18 data) |
| 0x0F-0x14 | - | Channel params block 3 (6 bytes, cmd 0x19 data) |
| 0x15-0x1A | - | Channel params block 4 (6 bytes, cmd 0x1A data) |
| 0x1B-0x20 | - | Channel params block 5 (6 bytes, cmd 0x1B data) |
| 0x21-0x26 | - | Channel params block 6 (6 bytes, cmd 0x1C data) |
| 0x27-0x56 | - | Additional channel/link config |
| 0x70 | 0x01 | Display contrast/mode |
| 0x71 | 0x04 | Band count / timeout default |
| 0xFE | 0x01 | Unknown flag |
| 0xFF | 0x02 | Firmware state marker (version check) |

---

## Firmware Version Differences

### V1.4 (Baseline)
- Full functionality including per-DLCP channel routing via buttons
- CONFIG1L = 0x00
- Bootloader accessible via PC command
- 54 function call targets, 41 strings
- EEPROM: version byte 0x04

### V1.5b (BETA)
- **4,763 bytes changed** across 60 code regions vs V1.4
- CONFIG1L = 0xFF → different oscillator config prevents USB bootloader enumeration
- CONFIG5-7 = 0xFF (code protection removed)
- Same feature set as V1.4
- EEPROM: version byte 0x04

### V1.6b (BETA)
- **5,166 bytes changed** vs V1.5b across 16 regions (more focused changes)
- **Combo display**: Volume + Input shown together on LCD line 1+2
- **Channel routing removed** from push-button menu (only via HFD software)
- "DLCP 1-6" strings removed from setup menu
- Bootloader only via up+down during power-up (no PC command)
- EEPROM: version byte 0x06
- 46 function call targets, 37 strings

### Key Config Changes (V1.4 → V1.5b/V1.6b)
| Config | V1.4 | V1.5b+ | Effect |
|--------|------|--------|--------|
| CONFIG1L | 0x00 | 0xFF | Prevents USB bootloader enumeration |
| CONFIG5-7 | Partial | 0xFF | All code protection removed |

---

## Complete System Interaction

```
┌──────────────────────────────────────────────────────────────┐
│                      USER INTERFACE                          │
│  ┌──────┐ ┌──────────┐ ┌──────────────────────────────────┐ │
│  │  IR  │ │ Buttons  │ │        HD44780 16x2 LCD          │ │
│  │RC-5  │ │ 6 keys   │ │ "Volume:-45.0dB "               │ │
│  │2 prof│ │debounced │ │ "Mute            "               │ │
│  └──┬───┘ └────┬─────┘ └───────────────────────────┬─────┘ │
│     │ RB5      │ RA1-4,RC0,RC5                     │ 4-bit │
│  ┌──▼──────────▼────────────────────────────────────▼─────┐ │
│  │           CONTROL BOARD (PIC18F25xx, 12 MHz XT)        │ │
│  │  ISR:  TX ring buf (48B) | RX ring buf (48B) | IR     │ │
│  │  Main: Button scan → Debounce → Event dispatch         │ │
│  │        Serial parse → Command handler                  │ │
│  │        Menu state machine (Vol/Input/Setup)            │ │
│  │  UART: 31,250 baud, 8N1, interrupt-driven              │ │
│  └────────────────────────┬───────────────────────────────┘ │
└───────────────────────────┼─────────────────────────────────┘
                            │ J3: 4mA current-mode serial
                            │ (optically isolated, CAT5, max 10m)
                            │ 3-byte protocol: routing + cmd + data
┌───────────────────────────┼─────────────────────────────────┐
│  ┌────────────────────────▼───────────────────────────────┐ │
│  │           MAIN BOARD (PIC18F2455, 48 MHz HSPLL)        │ │
│  │  UART RX ISR → 192-byte ring buffer                    │ │
│  │  Command dispatch: 13 commands (0x03-0x1E)             │ │
│  │  Volume → 32-bit signed → dirty flag → I2C            │ │
│  │  Flash coefficient storage (0x5600-0x5F3F)             │ │
│  │  USB HID interface (to PC / HFD software)              │ │
│  └────────────────────────┬───────────────────────────────┘ │
│                           │ I2C (100 kHz)                    │
│  ┌────────────────────────▼───────────────────────────────┐ │
│  │           TAS3108 DSP (0x68, 135 MHz)                  │ │
│  │  6-channel audio processing                            │ │
│  │  15 IIR biquads per channel (coefficients in flash)    │ │
│  │  Volume: registers 0x31-0x36 (per-channel)             │ │
│  │  Delay: 0-10ms per channel                             │ │
│  └────────────────────────────────────────────────────────┘ │
│                         MAIN UNIT                            │
└──────────────────────────────────────────────────────────────┘
```

---

## Main PIC UART Implementation

### UART Configuration (function_083 at 0x4546)
```
TXSTA   = 0x06  (BRGH=1, 8-bit async)
RCSTA   = 0x80  (SPEN=1)
BAUDCON = 0x48  (BRG16=1)
SPBRG   = 0x7F  (default 93,750 baud @ 48 MHz)
→ Then TXEN and CREN enabled
```

### Adaptive Baud Rate (function_045 at 0x3926)
| RC2 | SPBRG | Clock | Baud Rate | Mode |
|-----|-------|-------|-----------|------|
| LOW | 0x7F | 48 MHz (HSPLL) | 93,750 | Standalone/Link |
| HIGH | 0x3F | 8 MHz (internal) | 31,250 | Control board connected |

### Main PIC RX Buffer
- ISR at label_482 (0x3B5C)
- 192-byte circular buffer at Bank 2 (0x200-0x2BF)
- Write pointer: bank0:0xC7

### Main PIC TX
- function_111 (0x4896): blocking synchronous byte send
- Waits for TRMT (shift register empty)
- function_120 (0x492E): 1ms inter-message delay between 3-byte messages

---

*Analysis completed: 2026-02-14*
*Control firmware versions analyzed: V1.4, V1.5b, V1.6b (full PIC18F disassembly)*
*Main firmware cross-referenced: V2.3 (`PIC18F2455` hardware; older disassembly symbol sets may mention `PIC18F2550`)*
*Confidence: High on all sections — verified from both sides of the serial link*
