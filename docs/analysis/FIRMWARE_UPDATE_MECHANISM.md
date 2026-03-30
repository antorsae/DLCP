# DLCP Control Unit Firmware Update Mechanism - Complete Analysis

Historical correction note (2026-03-30):

- The CONTROL target in this document should be read as `PIC18F25K20`, not
  `PIC18F2550`.
- Older bootloader/disassembly writeups used `PIC18F2550`-style SFR names for
  the `0xF6C..0xF7F` range; on the real CONTROL silicon those are legacy label
  names, not a literal USB-endpoint block.

## Overview

The DLCP control unit firmware can be updated through the main DLCP's USB connection,
without any direct USB cable to the control board. The Hypex Filter Design software
on a Windows PC orchestrates the process. The main DLCP PIC acts as an intelligent
USB-to-UART bridge, converting binary firmware data received over USB HID into Intel
HEX records sent over the serial link to the control unit's bootloader.

```
┌─────────────────┐     USB HID      ┌─────────────────┐   4mA Current    ┌─────────────────┐
│  Hypex Filter   │  64-byte reports  │   Main DLCP     │   Loop UART     │  Control Unit   │
│  Design (PC)    │ ───────────────► │  (PIC18F2455)   │ ──────────────► │ (PIC18F25K20)   │
│                 │  Binary data      │                 │  Intel HEX      │                 │
│                 │ ◄─────────────── │  Constructs HEX │  records        │  Bootloader at  │
│                 │  Status/ACK       │  records, CRC   │ ◄────────────── │  0x7800-0x7FFF  │
└─────────────────┘                   └─────────────────┘  ACK responses  └─────────────────┘
```

Note: the DLCP main hardware is confirmed as PIC18F2455 (24 KB flash). The USB/SFR behavior used
in this update relay is compatible with the PIC18F2455/2550 family; some disassembly artifacts
use PIC18F2550 SFR symbols.

---

## Part 1: Update Trigger Sequence

### 1.1 USB HID Command Dispatch

The main DLCP firmware processes USB HID packets through a command dispatch chain.
The first byte of each 64-byte HID report is the command code:

**function_000** (0x10AC): Reads command byte from USB HID packet (0x11A)

**label_070** (0x1552): XOR dispatch chain on command byte:

| Command | Handler | Description |
|---------|---------|-------------|
| 0x01 | label_083 (noop) | Status query |
| 0x02 | label_083 (noop) | Status query |
| 0x03 | label_003 | Sub-command dispatch (I2C/DSP) |
| 0x04 | label_013 | Configuration/settings |
| 0x05 | label_023 | Parameter management |
| 0x06 | label_049 | Extended settings |
| 0x07-0x0B | label_054 | EEPROM operations |
| 0x0C | label_053 | Flash operations |
| **0x40** | **label_057** | DLCP self-update |
| **0x41** | **label_066** | Checksum verify |
| **0x42 ('B')** | **label_060** | **Control unit firmware update** |

### 1.2 Firmware Update Init (label_060 at 0x1456)

When the PC sends command 0x42 ('B'), the main PIC executes label_060:

```asm
label_060 (0x1456):
  ; Check if update mode already active
  tstfsz  0xCB              ; Test firmware update flag
  bra     label_064         ; Already active → relay data

  ; === FIRST 0x42 COMMAND: INITIALIZE UPDATE MODE ===

  ; 1. Clear all state variables
  clrf    0x7C-0x87         ; Clear CRC, address, checksum accumulators

  ; 2. Clear serial buffers
  call    function_097       ; Clear 10 bytes at 0x1C7 (RX response buffer)
  call    function_097       ; Clear 45 bytes at 0x19A (TX record buffer)
  call    function_097       ; Clear 8 bytes at 0x1D1 (magic string buffer)

  ; 3. Send factory reset command to control unit
  call    function_107       ; → UART TX: 0xBF, 0x18, 0x01

  ; 4. Wait for bootloader prompt
  call    function_048       ; UART RX: wait for ":FW_Upd\r\n"

  ; 5. Verify magic string
  ; Loop: compare buffer[0x4D+i] with buffer[0x1D1+i] for 6 bytes
  ; Expected: "FW_Upd"

  ; 6. If match: set firmware update mode flag
  movlw   0x01
  movwf   0xCB              ; 0xCB = 1 → update mode active
```

### 1.3 Factory Reset Command (function_107 at 0x484E)

```asm
function_107:
  movlw   0xBF              ; Command prefix byte
  call    function_111      ; UART TX
  movlw   0x18              ; Sub-command: factory reset / enter bootloader
  call    function_111      ; UART TX
  movlw   0x01              ; Parameter: 0x01
  goto    function_111      ; UART TX (tail call)
```

The control unit application receives this 3-byte command (0xBF, 0x18, 0x01),
writes 0x00 to EEPROM address 0xFF, and executes a `RESET` instruction. On the
next boot, the bootloader reads EEPROM[0xFF] = 0x00 and enters bootloader mode
instead of jumping to the application.

Important version note:
- CONTROL firmware **V1.4** contains the application-side `cmd=0x18` handler, so this automated
  bootloader entry works.
- CONTROL firmware **V1.5b/V1.6b** remove that handler; in those versions you must enter the
  bootloader manually (button combo during power-on) before streaming records.

---

## Part 2: Data Relay (function_003)

### 2.1 Relay Architecture

When subsequent USB HID packets arrive with command byte 0x42 and the update flag
(0xCB) is set, the main PIC calls **function_003** (0x15CE):

```
USB HID Packet (64 bytes)              UART Intel HEX Record
┌────┬────┬────────────────────┐       ┌──────────────────────────────────┐
│0x42│Addr│  Binary data       │  ───► │:10AAAA00DDDDDDDDDDDDDDDDDDDDDDDDCC│
│cmd │Hi:Lo│ (up to 16 bytes)  │       │ ^  ^     ^                       ^│
└────┴────┴────────────────────┘       │ │  │     │                       ││
                                        │ len addr  data (hex ASCII)    chksum│
                                        └──────────────────────────────────┘
```

### 2.2 function_003 Detailed Flow (0x15CE)

```asm
function_003:
  ; 1. Copy 8-byte header from 0x1E5 to 0x01D
  lfsr    FSR2, 0x1E5       ; Source: USB packet header area
  lfsr    FSR1, 0x01D       ; Dest: working header buffer
  movlw   0x08
  ; loop: copy 8 bytes

  ; 2. Process data bytes with CRC calculation
  ; For each data byte from USB packet:
  ;   - Shift into 16-bit CRC register (0x7C:0x7D)
  ;   - XOR with polynomial 0x4402 on feedback
  ;   - Track running address in 0x84:0x85

  ; 3. Address bounds check
  ; Address must be >= 0x0040 and < 0x77C0
  ; (protects reset vectors and bootloader region)

  ; 4. Build Intel HEX record in TX buffer (0x19A)
  ; Header: ':' (0x3A), '1', '0' (16 bytes per record)
  ; Address: 4 hex digits from 0x84:0x85
  ; Data: convert each binary byte to 2 hex ASCII digits
  ;   Uses lookup table at flash 0x1019: "0123456789ABCDEF"
  ;   function_004 reads TBLPTRL = nibble + 0x19, TBLPTRH = 0x10

  ; 5. Send Intel HEX record over UART
  movlw   0x0D              ; CR
  call    function_111
  movlw   0x0A              ; LF
  call    function_111
  ; ... send hex record bytes via function_091 ...

  ; 6. Wait for bootloader acknowledgment
  call    function_048       ; RX: wait for ":XX\r\n" from bootloader

  ; 7. Verify acknowledgment
  ; Compare received checksum against expected
  ; function_059 processes the received checksum

  ; 8. Retry on failure (up to 25 attempts)
  ; If mismatch: send '!' (0x21) + error info, resend record
  ; If retry count (0x9F) reaches 0x19 (25): abort → label_109
```

### 2.3 Hex Digit Lookup Table

At flash address 0x1019, the firmware stores an ASCII hex lookup table:

```
0x1019: '0' '1' '2' '3' '4' '5' '6' '7' '8' '9' 'A' 'B' 'C' 'D' 'E' 'F'
```

**function_004** (0x18DE) converts a nibble to ASCII hex:
```asm
function_004:
  andwf   0x1B, F           ; Mask to 4 bits (0x0F applied before call)
  movf    0x1B, W
  addlw   0x19              ; TBLPTRL = nibble + 0x19
  movwf   TBLPTRL
  movlw   0x10              ; TBLPTRH = 0x10
  movwf   TBLPTRH
  tblrd*                    ; Read ASCII hex digit from flash
  return                    ; TABLAT = hex character
```

### 2.4 UART Transmit (function_111 at 0x4896)

```asm
function_111:
  movff   WREG, 0x003       ; Save byte
label_605:
  btfss   TXSTA, TRMT       ; Wait for shift register empty
  bra     label_605
  movff   0x003, TXREG      ; Transmit byte
  movf    0x003, W           ; Return sent byte in W
  return
```

### 2.5 UART Receive with Framing (function_048 at 0x3AA4)

```asm
function_048:
  ; Start timer for timeout
  call    function_099       ; Configure Timer3

  ; Wait for ':' start marker
label_473:
  call    function_109       ; Check RX buffer count
  bz      label_477          ; Timeout check
  call    function_087       ; Read byte from RX ring buffer

  ; Before ':' received (0x0D == 0): wait for 0x3A (':')
  xorlw   0x3A
  bnz     label_475          ; Not ':' yet

  ; After ':' received: collect data bytes
  ; Store in destination buffer at 0x107:0x108 + offset

  ; Look for CR+LF (0x0D, 0x0A) terminator
  ; Previous byte was 0x0D AND current byte is 0x0A → record complete
  ; Set 0x0C = 1 to signal completion

  ; Return byte count in W
```

---

## Part 3: Control Unit Bootloader (0x7800-0x7FFF)

### 3.1 Bootloader Entry Point (0x7800)

The **control bootloader** reset vector at 0x0000 always contains `GOTO 0x7800`, ensuring
the bootloader runs first on every power-on or reset.

```asm
label_284 (0x7800):
  goto    label_315          ; → 0x7AFE (bootloader init)
```

### 3.2 Hardware Initialization (label_315 at 0x7AFE)

```asm
label_315:
  clrf    TBLPTRU            ; Upper address byte = 0
  clrf    SPBRGH
  movlw   0x05
  movwf   SPBRG              ; Baud rate divisor = 5
  movlw   0x20
  movwf   TXSTA              ; BRGH=1, async mode
  movlw   0x90
  movwf   RCSTA              ; SPEN=1, CREN=1

  ; Port direction
  movlw   0xDF
  movwf   TRISA              ; RA5 output (LCD RS)
  movlw   0x3C
  movwf   TRISB              ; RB2-RB5 inputs, RB0-1,6-7 outputs
  movlw   0xBD
  movwf   TRISC              ; RC1,RC6 outputs; RC0,2-5,7 inputs

  ; Clear the legacy-disassembly 0xF76..0xF7B label block.
  ; Older notes called these UEP10..UEP15, but on the confirmed
  ; PIC18F25K20 target they are not literal USB endpoint registers.

  ; All pins digital
  movlw   0x0F
  movwf   ADCON1

  ; Store "FW_Upd" magic string at RAM 0x076-0x07B
  ; 0x46='F', 0x57='W', 0x5F='_', 0x55='U', 0x70='p', 0x64='d'

  ; Check for manual button entry
  call    function_082        ; Check button combo

  ; Check EEPROM boot mode
  ; → Determines whether to enter bootloader or jump to application
```

### 3.3 Button-Based Bootloader Entry (function_082 at 0x7F02)

Manual entry requires holding specific buttons for ~5.5 seconds during power-on:

```asm
function_082:
  ; Required (per control app pin mapping):
  ;   RC0=LOW  (Up button pressed, active-low)
  ;   RA2=LOW  (Down button pressed, active-low)
  ;   RA1=HIGH (Select button NOT pressed)
  ; Must be held for 11 loop iterations with delays (~5.5 seconds)

  btfsc   PORTC, RC0         ; RC0 must be LOW
  return                     ; Not pressed → skip
  btfsc   PORTA, RA2         ; RA2 must be LOW
  return                     ; Not pressed → skip
  btfss   PORTA, RA1         ; RA1 must be HIGH
  return                     ; Also pressed → skip (wrong combo)

  ; Hold check loop: 11 iterations
  movlw   0x0B
  movwf   counter
  ; Inner delay loop per iteration
  ; Total hold time: ~5.5 seconds

  bsf     0x082, bit1        ; Set "buttons held" flag
  return
```

### 3.4 EEPROM Boot Mode State Machine (0x7B4C)

EEPROM address 0xFF serves as a boot mode selector:

```asm
  movlw   0xFF
  call    function_070        ; Read EEPROM[0xFF]

  ; Check button flag first
  btfsc   0x082, bit1         ; Manual button entry?
  bra     write_00_enter_bl   ; → Write 0x00, enter bootloader

  ; EEPROM value dispatch:
  xorlw   0x01
  bz      normal_boot         ; 0x01 → write 0x77, jump to app at 0x0040
  xorlw   0x03                ; XOR chain: tests for 0x02
  bz      special_boot        ; 0x02 → write 0x01 to EEPROM[0xFE], jump to app
  ; Any other value (including 0x00) → fall through to bootloader

write_00_enter_bl:
  movlw   0xFF
  movwf   EEADR
  movlw   0x00
  call    function_071        ; Write 0x00 to EEPROM[0xFF]
  ; Fall through to bootloader main loop
```

| EEPROM[0xFF] | Action |
|-------------|--------|
| **0x00** | Enter bootloader mode (update pending) |
| **0x01** | Normal boot: write 0x77 to EEPROM[0xFF], jump to app |
| **0x02** | Special mode: write 0x01 to EEPROM[0xFE], jump to app |
| **Button held** | Force 0x00, enter bootloader |

### 3.5 Bootloader Main Loop (0x7B82-0x7E5E)

#### Initialization

```asm
  bsf     TXSTA, TXEN         ; Enable UART transmitter
  bsf     RCSTA, CREN         ; Enable continuous receive
  bsf     RCSTA, SPEN         ; Enable serial port
  call    function_055         ; LCD init (HD44780 4-bit mode)
  bsf     LATC, LATC1         ; Turn on backlight/LED
  call    function_056         ; Display version on LCD
  call    function_061         ; Display "Bootloader mode" on LCD
```

#### Prompt and Receive Loop

```asm
label_321 (0x7BB6):
  ; Copy "FW_Upd" to secondary buffer
  ; Send prompt via function_080

label_323 (0x7BD6):
  ; Clear receive buffer at 0x043 (46 bytes)
  ; Set UART timeout values
  ; Wait for ':' (0x3A) character
  call    function_066         ; RX with timeout
  bnc     label_321            ; Timeout → resend prompt
  sublw   0x3A
  bnz     wait_for_colon       ; Not ':' → keep waiting

  ; Receive rest of line until CR (0x0D)
  lfsr    FSR1, 0x043          ; Buffer pointer
  ; Loop: receive bytes via function_066, store until CR
  ; Null-terminate on CR
```

#### Prompt Format (function_080 at 0x7E60)

The bootloader sends its readiness prompt:

```
0x0D 0x0A 0x0C ':' [4-hex-digit-address] 0x0D 0x0A
  CR   LF  FF  ':'     (buffer ID)         CR   LF
```

#### All-Zero Check (EOF Detection)

```asm
label_328 (0x7C0A):
  ; Check if first 6 characters after ':' are all '0'
  ; If ":000000..." → end of file → jump to label_351 (finalize)
  ; Otherwise → parse as Intel HEX record
```

### 3.6 Intel HEX Record Processing

#### Parsing (0x7C30-0x7CB4)

```asm
  ; Parse 20 hex character pairs (40 hex chars = 20 bytes):
  ;   [2: byte_count] [4: address] [2: record_type] [32: data (16 bytes)]
  ; Using function_057 (ASCII hex → binary converter)

  ; Compute running checksum
  ; After parsing: verify checksum
  movf    0x022, W            ; Computed checksum
  cpfseq  expected            ; Match?
  bra     label_345            ; Mismatch → discard, get next record
```

#### function_057 (0x784E) - ASCII Hex Parser

```asm
function_057:
  ; Input: FSR0 points to ASCII hex string in buffer
  ; Output: 0x00F:0x010:0x011:0x012 = parsed 32-bit value
  ;
  ; For each character:
  ;   '0'-'9' → value 0x0-0x9
  ;   'A'-'F' → value 0xA-0xF
  ;   '-'     → set negative flag
  ;
  ; Shifts result left 4 bits for each nibble, ORs in new nibble
  ; Handles sign (two's complement negation)
```

#### Address Validation and Flash Write

```asm
  ; Parse address from record
  ; Result: 0x01D = addr_low, 0x01E = addr_high

  ; Bounds check 1: address < 0x77C0 (bootloader protection)
  movlw   0x77
  ; ... compare ...

  ; Bounds check 2: address >= 0x0040 (vector table protection)
  movlw   0x40
  ; ... compare ...

  ; Only 0x0040-0x77BF is writable!

  ; If page-aligned (lower 6 bits == 0): erase 64-byte page first
  call    function_074         ; Flash erase

  ; Write 16 data bytes (8 word pairs)
  ; For each word:
  movf    data_byte, W
  call    function_072         ; Write to flash holding register
  ; function_072 auto-flushes every 32 bytes
```

### 3.7 Flash Write Primitives

#### function_072 (0x7A6E) - Flash Write with Auto-Flush

```asm
function_072:
  movwf   TABLAT              ; Load byte into table latch
  tblwt*                      ; Write to holding register (no increment)
  incf    TBLPTRL, W
  andlw   0x1F                ; Check 32-byte boundary
  bnz     skip_flush          ; Not boundary → just increment pointer

  ; At 32-byte boundary: commit holding registers to flash
  movlw   0x84                ; EECON1 = EEPGD | WREN (flash write mode)
  movwf   EECON1
  movlw   0x55                ; Unlock sequence
  movwf   EECON2
  movlw   0xAA
  movwf   EECON2
  bsf     EECON1, WR          ; Execute write
  bcf     EECON1, WREN        ; Disable writes

skip_flush:
  infsnz  TBLPTRL, F          ; Increment table pointer
  incf    TBLPTRH, F
  return
```

#### function_074 (0x7A92) - Flash Page Erase

```asm
function_074:
  movlw   0x94                ; EECON1 = EEPGD | FREE | WREN
  movwf   EECON1              ; (flash erase mode, 64-byte block)
  movlw   0x55                ; Unlock sequence
  movwf   EECON2
  movlw   0xAA
  movwf   EECON2
  bsf     EECON1, WR          ; Execute erase
  nop                          ; Required NOP
  bcf     EECON1, WREN        ; Disable writes
  return
```

### 3.8 Acknowledgment

After successfully writing a record:

```asm
  movlw   0x3A                ; Send ':' over UART
  call    function_067
  movlw   0x04
  movwf   0x001               ; Output mode = UART
  movf    0x022, W            ; Checksum value
  call    function_058         ; Send as 2-digit hex ASCII
  movlw   0x0D                ; CR
  call    function_067
  movlw   0x0A                ; LF
  call    function_067
```

Response format: `:XX\r\n` where XX = checksum in hex ASCII.

### 3.9 Special Record Handling

#### Address 0x0040 Record

When the record targeting address 0x0040 is received, the first 8 bytes of
data are saved to RAM buffer (0x024) for later use in writing the reset vector.
EEPROM[0xFF] is set to 0x00 (bootloader mode), creating a safety net:

```asm
  ; Save data bytes at indices 8-15 to RAM 0x024
  setf    EEADR               ; EEADR = 0xFF
  movlw   0x00
  call    function_071         ; Write 0x00 → ensures bootloader on next reset
```

#### Address 0x0050 Record

When the record for address 0x0050 is received, additional data is saved
and the reset vector is written:

```asm
  ; Save data to RAM 0x024[16..31]
  call    function_081         ; Write reset vector and interrupt vectors
```

### 3.10 Reset Vector Write (function_081 at 0x7E94)

This critical routine is called LAST, after all application code is written:

```asm
function_081:
  ; 1. Erase page 0 (0x0000-0x003F)
  clrf    TBLPTRL
  clrf    TBLPTRH
  call    function_074         ; Erase 64-byte page

  ; 2. Write reset vector: GOTO 0x7800 (always points to bootloader!)
  ; 0x0000: 0xEF00 → GOTO low byte
  ; 0x0002: 0xF03C → GOTO high byte
  ;         Decodes to: GOTO 0x7800

  ; 3. Write 0xFFFF at 0x0004-0x0007 (unused vector slots)

  ; 4. Write application interrupt vectors at 0x0008-0x001F
  ;    From saved buffer at RAM 0x024 (received from 0x0040/0x0050 records)

  ; This ensures:
  ;   - Reset always goes to bootloader first
  ;   - Application code starts at 0x0040 (via GOTO at 0x0040)
  ;   - Interrupt vectors at 0x0008+ point to application ISR
```

### 3.11 End-of-File Handling (label_351 at 0x7F56)

```asm
label_351:
  call    function_081         ; Write final reset vector (if not already done)
  bcf     LATC, LATC1          ; Turn off LED/backlight
  setf    EEADR                ; EEADR = 0xFF
  movlw   0x01
  call    function_071          ; Write 0x01 to EEPROM[0xFF] (valid app)
  ; Delay ~300ms
  reset                         ; Software reset → boots into new application
```

---

## Part 4: UART Communication Details

### 4.1 Baud Rate

**Control unit bootloader**: SPBRG=5, TXSTA=0x20 (BRGH=0, TXEN=1), BRG16=0 (default)
- CONFIG1H=0x01 → XT oscillator mode, 12 MHz crystal
- Baud = 12,000,000 / (64 × (5+1)) = 12,000,000 / 384 = **31,250 baud exactly**
- This matches the MIDI baud rate — the serial link operates at MIDI speed

**Main DLCP firmware**: Dual-speed depending on RC2 pin:
- RC2=HIGH: SPBRG=0x3F (63), SCS1=1 (internal oscillator)
- RC2=LOW: SPBRG=0x7F (127), SCS1=0 (primary oscillator, 48MHz USB)

**Main firmware UART**: TXSTA=0x06 (BRGH=1), BAUDCON=0x48 (BRG16=1)

### 4.2 UART RX Ring Buffer (Main Firmware)

The main firmware uses interrupt-driven UART receive with a 192-byte circular buffer:

```
Bank 2 RAM: 0x200-0x2BF (192 bytes)
Write pointer: 0x0C7 (ISR increments)
Read pointer:  0x0C6 (main loop reads)
Wrap point:    0xBF (191)
```

Overrun recovery: toggle CREN to clear OERR flag.

### 4.3 Serial Protocol Framing

The bootloader uses a simple text-based protocol over UART:

```
Bootloader → Host:  CR LF FF ':' <address> CR LF     (prompt/ready)
Host → Bootloader:  ':' <Intel HEX record> CR          (data)
Bootloader → Host:  ':' <checksum> CR LF                (ACK)

End of file:        ':000000...' (all-zero record)
```

---

## Part 5: Safety Features

### 5.1 Bootloader Self-Protection

The bootloader refuses to write to addresses >= 0x77C0, preventing it from
overwriting itself. The protected ranges:

```
0x0000-0x003F  Reset vector + interrupt vectors (written LAST, atomically)
0x0040-0x77BF  Application code (writable by bootloader)
0x77C0-0x7FFF  Bootloader code (NEVER overwritten)
```

### 5.2 Reset Vector Safety

The reset vector at 0x0000 always contains `GOTO 0x7800`, ensuring the
bootloader runs on every boot. The application entry point is at 0x0040,
reached only when the bootloader explicitly jumps there after checking
EEPROM[0xFF].

The reset vector page (0x0000-0x001F) is erased and written LAST. This
minimizes the time window where a power failure could leave the device
without a valid reset vector. Even if interrupted, EEPROM[0xFF] will be
0x00 (bootloader mode), so the next boot re-enters the bootloader.

### 5.3 EEPROM State Machine

```
┌──────────┐   Power-on reset    ┌──────────────┐
│  APP     │ ──────────────────► │  BOOTLOADER  │
│ running  │                     │  checks      │
└──────────┘                     │  EEPROM[FF]  │
     ▲                           └──────┬───────┘
     │                                  │
     │                    ┌─────────────┼─────────────┐
     │                    │             │             │
     │              ┌─────▼─────┐ ┌────▼────┐ ┌─────▼─────┐
     │              │ FF = 0x01 │ │ FF=0x02 │ │ FF = 0x00 │
     │              │ Valid app │ │ Special │ │ Update    │
     │              └─────┬─────┘ └────┬────┘ └─────┬─────┘
     │                    │            │             │
     │              Write 0x77   Write 0x01    Stay in BL
     │              to [FF]      to [FE]       Wait for
     │                    │            │        HEX data
     └────────────────────┴────────────┘             │
           Jump to 0x0040 (app)                      │
                                                     │
                                          ┌──────────▼──────────┐
                                          │ Receive & flash     │
                                          │ Intel HEX records   │
                                          │ over UART           │
                                          └──────────┬──────────┘
                                                     │ EOF received
                                          ┌──────────▼──────────┐
                                          │ Write reset vector  │
                                          │ Write 0x01 to [FF]  │
                                          │ RESET instruction   │
                                          └─────────────────────┘
```

### 5.4 Checksum Verification

Every Intel HEX record is verified:
1. **Main PIC** computes CRC on binary data before constructing HEX record
2. **Bootloader** independently verifies Intel HEX checksum
3. **Acknowledgment** echoes the computed checksum for main PIC to verify
4. **Retries** on mismatch (up to 25 attempts per record)

### 5.5 Timeout Recovery

The bootloader's UART receive (function_066) has a multi-level countdown timer.
On timeout, it returns to the prompt loop and resends the readiness marker,
allowing the host to resynchronize.

---

## Part 6: Complete Update Sequence

```
Step  PC (Hypex FD)              Main DLCP PIC              Control Unit
─────────────────────────────────────────────────────────────────────────
 1.   User selects "Update
      Control Firmware"
 2.   Send USB HID [0x42, ...]  ──►
 3.                              Clear state, prepare
 4.                              Send 0xBF 0x18 0x01  ────►
 5.                                                        Receive factory
                                                            reset command
 6.                                                        Write 0x00 →
                                                            EEPROM[0xFF]
 7.                                                        Execute RESET
 8.                                                        ─── rebooting ───
 9.                                                        Bootloader runs
10.                                                        EEPROM[FF]=0x00
                                                            → stay in BL
11.                                                        Init UART
12.                                                        LCD: "Bootloader
                                                                  mode"
13.                              ◄──────────────────────── Send ":FW_Upd\r\n"
14.                              Verify "FW_Upd" match
15.                              Set 0xCB=1 (update mode)
16.   ◄── USB HID status/ACK ──
17.   Send [0x42, addr, data...] ──►
18.                              Convert binary → Intel HEX
                                  Compute CRC
                                  Build ":10AAAA00DD...CC"
19.                              Send HEX record      ────►
20.                                                        Parse HEX record
21.                                                        Verify checksum
22.                                                        Erase flash page
                                                            (if aligned)
23.                                                        Write to flash
                                                            (32-byte blocks)
24.                              ◄──────────────────────── Send ":XX\r\n" ACK
25.                              Verify ACK checksum
26.   ◄── USB HID ACK ─────────
      ... (repeat 17-26 for all records) ...
27.   Send [0x42, EOF record]    ──►
28.                              Send ":000000..." EOF ────►
29.                                                        Write reset vector
                                                            (function_081)
30.                                                        GOTO 0x7800 at
                                                            addr 0x0000
31.                                                        App vectors at
                                                            0x0008-0x001F
32.                                                        Write 0x01 →
                                                            EEPROM[0xFF]
33.                                                        Execute RESET
34.                                                        ─── rebooting ───
35.                                                        Bootloader runs
36.                                                        EEPROM[FF]=0x01
                                                            → jump to app
37.                                                        Application runs
                                                            normally
```

---

## Part 7: Key Functions Reference

### Control Unit Bootloader (v1.4_disasm.asm)

| Function | Address | Description |
|----------|---------|-------------|
| label_315 | 0x7AFE | Bootloader init (UART, ports, magic string) |
| function_082 | 0x7F02 | Button combo check (Up+Down for ~5.5s; Select must not be pressed) |
| label_321 | 0x7BB6 | Main bootloader loop (prompt + receive) |
| function_080 | 0x7E60 | Send readiness prompt over UART |
| function_066 | 0x79EC | UART RX with timeout |
| function_067 | 0x7A2A | UART TX (wait for TXIF) |
| function_057 | 0x784E | ASCII hex to binary parser |
| function_072 | 0x7A6E | Flash write with 32-byte auto-flush |
| function_074 | 0x7A92 | Flash page erase (64 bytes) |
| function_070 | 0x7A48 | EEPROM read |
| function_071 | 0x7A54 | EEPROM write with unlock |
| function_081 | 0x7E94 | Write reset vector and app vectors |
| function_055 | - | LCD init (HD44780 4-bit mode) |
| function_061 | - | Display string from flash |
| label_351 | 0x7F56 | EOF handler (finalize, write EEPROM, reset) |

### Main DLCP Firmware (gpdasm_output.asm)

| Function | Address | Description |
|----------|---------|-------------|
| function_000 | 0x10AC | HID command dispatch (reads 0x11A) |
| label_070 | 0x1552 | XOR dispatch chain (0x42='B' → update) |
| label_060 | 0x1456 | Firmware update init (trigger + verify) |
| function_003 | 0x15CE | Data relay (binary → Intel HEX → UART) |
| function_004 | 0x18DE | Nibble to hex ASCII (table at 0x1019) |
| function_107 | 0x484E | Factory reset cmd (0xBF 0x18 0x01) |
| function_048 | 0x3AA4 | UART RX with framing (wait for `:...\r\n`) |
| function_097 | 0x473E | Memory clear (addr, count) |
| function_111 | 0x4896 | UART TX single byte (blocking) |
| function_087 | 0x45FA | Read from UART RX ring buffer |
| function_109 | 0x4872 | Check UART RX data available |
| function_059 | 0x3F78 | Checksum computation |
| function_091 | 0x4696 | Block UART TX from buffer |

---

## Part 8: Memory Map

### Control Unit Flash

```
0x0000-0x0003   Reset vector: GOTO 0x7800 (bootloader)
0x0004-0x0007   Reserved (0xFFFF)
0x0008-0x001F   Application interrupt vectors
0x0020-0x003F   Early application code (page 0)
0x0040-0x77BF   Application code (updatable region)
0x77C0-0x7FFF   Bootloader (protected, never overwritten)
0x300000-0x30000D  Configuration words
0xF00000-0xF000FF  EEPROM (256 bytes)
  └─ 0xF000FF      Boot mode selector
```

### Control Unit RAM (Bootloader Usage)

| Address | Usage |
|---------|-------|
| 0x001 | Output mode (0x80=LCD, 0x04=UART) |
| 0x002 | UART timeout high byte |
| 0x006 | UART timeout low byte |
| 0x008 | Loop counter / index |
| 0x01B | Input mode (0x00=UART, 0x80=buffer) |
| 0x01D | Write address low byte |
| 0x01E | Write address high byte |
| 0x01F | Byte/pair counter |
| 0x020-0x021 | Parsed checksum value |
| 0x022-0x023 | Running checksum accumulator |
| 0x024-0x043 | Saved vector data (from 0x0040/0x0050 records) |
| 0x043-0x070 | UART receive buffer (46 bytes) |
| 0x071-0x075 | Temp buffer for hex parsing |
| 0x076-0x07B | "FW_Upd" magic string |
| 0x07C-0x081 | Secondary copy buffer |
| 0x082 | Flags (bit1 = buttons held) |

---

*Analysis based on: DLCP Control Firmware V1.4 (v1.4_disasm.asm), Main DLCP Firmware V2.3 (gpdasm_output.asm)*
*Completed: 2026-02-14*
