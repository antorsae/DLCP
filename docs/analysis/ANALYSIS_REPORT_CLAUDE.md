# HYPEX DLCP Firmware V2.3 Analysis Report (Corrected)

## Executive Summary

The DLCP firmware is a PIC18F24/25xx-family microcontroller application (on the
target hardware: **PIC18F2455**, 24 KB flash) that serves as a
USB-to-I2C bridge between host PC software (Hypex Filter Design) and a **Texas
Instruments TAS3108** audio DSP. The system is a 6-channel digital loudspeaker
crossover/correction processor running at 96 kHz sample rate. Each channel has
**15 IIR biquad filter stages** (90 biquads total) with 28-bit coefficients.
Coefficients are computed by the host software and uploaded via USB HID, then
transferred to the TAS3108 over I2C at ~33 kHz.

## Hardware Identification

| Property | Value |
|----------|-------|
| **Microcontroller** | PIC18F2455 (24 KB flash; app image uses 0x1000–0x5FFF) |
| **USB VID** | 0x04D8 (Microchip Technology) |
| **USB PID** | 0xFF89 |
| **Manufacturer** | Hypex BV |
| **Product Name** | DLCP |
| **Firmware Version** | 2.3 (EEPROM: V2.30) |
| **bcdDevice** | 0.01 |
| **DSP Chip** | TI TAS3108 (I2C addr 0x34) |
| **Audio Channels** | 6 |
| **Biquads/Channel** | 15 |
| **Sample Rate** | 96 kHz |

## Memory Map

| Region | Address Range | Size | Description |
|--------|---------------|------|-------------|
| Bootloader | 0x0000-0x0FFF | 4 KB | USB HID bootloader (not in HEX, write-protected only) |
| Vectors + Data | 0x1000-0x10AB | 172 B | Reset/ISR vectors + USB descriptor tables |
| Application Code | 0x10AC-0x496F | 14.2 KB | Main firmware code (132 functions) |
| Unused Gap | 0x4970-0x55FF | 3.1 KB | Erased flash (available for patches) |
| DSP / Config Table | 0x5600-0x5FFF | 0xA00 (2.5 KB) | Persistent DSP/config upload script + const data |
| User IDs | 0x200000 | 8 bytes | Device identification (all 0xFF) |
| Config Words | 0x300000 | 14 bytes | MCU configuration |
| EEPROM | 0xF00000 | 256 bytes | Persistent settings |

**HEX file total: 20,758 bytes** (code: 20,480 + config: 14 + EEPROM: 256 + UIDs: 8)

## Configuration Analysis

All values verified against gputils PIC18F24/25xx config bit definitions
(PIC18F2455/PIC18F2550 share the relevant CONFIG layout for the fields used
here).

```
CONFIG1L (0x300000): 0x3A
  - USBDIV = 1: USB clock from 96 MHz PLL/2 (= 48 MHz)
  - CPUDIV = OSC4_PLL6: Primary Osc /4, PLL 96 MHz /6 (= 16 MHz CPU clock)
  - PLLDIV = 3: Divide by 3 (12 MHz external clock input)

CONFIG1H (0x300001): 0x46
  - FOSC = ECPLLIO_EC: EC oscillator, PLL enabled, port function on RA6
  - FCMEN = ON: Fail-Safe Clock Monitor enabled
  - IESO = OFF: Oscillator Switchover disabled

CONFIG2L (0x300002): 0x3E
  - VREGEN = ON: USB voltage regulator enabled
  - BORV = 3: Brown-out voltage 2.05V (minimum setting)
  - BOREN = ON: Brown-out Reset enabled in hardware, disabled in Sleep
  - PWRT = ON: Power-up Timer enabled

CONFIG2H (0x300003): 0x1E
  - WDTPS = 32768: Watchdog postscaler 1:32768
  - WDT = OFF: Controlled by SWDTEN bit

CONFIG3H (0x300005): 0x00
  - MCLRE = OFF: MCLR pin disabled, RE3 input enabled
  - PBADEN = OFF: PORTB<4:0> digital I/O on Reset
  - CCP2MX = OFF: CCP2 on RB3

CONFIG4L (0x300006): 0x80
  - DEBUG = OFF: Background debugger disabled, RB6/RB7 as I/O
  - XINST = OFF: Legacy instruction mode
  - LVP = OFF: Low-Voltage Programming disabled
  - STVREN = OFF: Stack overflow/underflow will NOT cause Reset
```

### Clock Derivation

```
External Clock (12 MHz) --> PLLDIV /3 --> 4 MHz --> 96 MHz PLL
                                                      |
                                          +-----------+-----------+
                                          |                       |
                                      USBDIV /2               CPUDIV /6
                                          |                       |
                                     48 MHz USB              16 MHz CPU
```

## Protection Analysis

| Region | Code Protect | Write Protect | Table Read Protect |
|--------|:------------:|:-------------:|:-----------------:|
| Boot Block (0x0000-0x0FFF) | NO (CPB=1) | **YES** (WRTB=0) | NO (EBTRB=1) |
| Block 0 (0x1000-0x1FFF) | No | No | No |
| Block 1 (0x2000-0x3FFF) | No | No | No |
| Block 2 (0x4000-0x5FFF) | No | No | No |
| EEPROM | No (CPD=1) | No (WRTD=1) | N/A |
| Config Registers | N/A | NO (WRTC=1) | N/A |

The boot block is **only write-protected** -- it can be read and table-read. It is
NOT code-protected or table-read-protected. Configuration registers are NOT
write-protected and can be changed by the application or bootloader.

## USB Interface

- **Class**: HID (Human Interface Device)
- **Endpoints**: EP1 IN (0x81, Interrupt) + EP1 OUT (0x01, Interrupt)
- **Report Size**: 64 bytes IN, 64 bytes OUT
- **Polling Interval**: 1 ms (both endpoints)
- **Power**: 100 mA max from USB (Bus Powered)
- **HID Version**: 1.11
- **Usage Page**: 0xFF00 (Vendor Defined)

### Device Descriptor (at 0x1088, 18 bytes)

```
12 01 00 02 00 00 00 08 D8 04 89 FF 01 00 01 02 00 01
```

| Field | Value | Notes |
|-------|-------|-------|
| bcdUSB | 0x0200 | USB 2.0 Full Speed |
| bMaxPacketSize0 | 8 | EP0 max packet size |
| idVendor | 0x04D8 | Microchip Technology |
| idProduct | 0xFF89 | DLCP product |
| bcdDevice | 0x0001 | Version 0.01 |
| iManufacturer | 1 | "Hypex BV" |
| iProduct | 2 | "DLCP" |
| iSerialNumber | 0 | None |
| bNumConfigurations | 1 | |

### Configuration Descriptor (at 0x102C, 41 bytes total)

```
09 02 29 00 01 01 00 80 32   Config: 41 bytes, 100 mA, bus-powered
09 04 00 00 02 03 00 00 00   Interface 0: HID class, 2 endpoints
09 21 11 01 00 01 22 1D 00   HID 1.11, report descriptor = 29 bytes
07 05 81 03 40 00 01          EP1 IN:  Interrupt, 64 bytes, 1 ms
07 05 01 03 40 00 01          EP1 OUT: Interrupt, 64 bytes, 1 ms
```

### HID Report Descriptor (at 0x1055, 29 bytes)

```
06 FF 00     Usage Page (Vendor Defined 0xFF00)
09 01        Usage (1)
A1 01        Collection (Application)
  19 01        Usage Minimum (1)
  29 40        Usage Maximum (64)
  15 00        Logical Minimum (0)
  26 FF 00     Logical Maximum (255)
  75 08        Report Size (8)
  95 40        Report Count (64)
  81 00        Input (Data, Array, Absolute)
  19 01        Usage Minimum (1)
  29 40        Usage Maximum (64)
  91 00        Output (Data, Array, Absolute)
C0           End Collection
```

Standard vendor-defined 64-byte bidirectional HID interface. No Report IDs.

### String Descriptors

| Index | Address | Content |
|-------|---------|---------|
| 0 | 0x10A6 | Language: 0x0409 (English US) |
| 1 | 0x1072 | "Hypex BV" (Manufacturer) |
| 2 | 0x109A | "DLCP" (Product) |

## Key Entry Points

| Address | Instruction | Description |
|---------|-------------|-------------|
| 0x1000 | `GOTO 0x1014` | Reset vector |
| 0x1004 | `DW 0xFFFF, 0xFFFF` | Erased flash (padding) |
| 0x1008 | `MOVFF FSR2L, 0x001` | High-priority ISR: save FSR2L |
| 0x100C | `MOVFF FSR2H, 0x002` | ISR: save FSR2H |
| 0x1010 | `CALL 0x3B1E, FAST` | ISR: call handler with fast return |
| 0x1014 | `GOTO 0x3D4E` | Jump to main function |

### Interrupt Structure

The ISR at 0x1008 saves FSR2 (indirect addressing pointer) then calls the
interrupt handler at 0x3B1E using a fast call (hardware context save). The
handler returns via RETFIE at 0x3B94 (the only RETFIE in actual code).

The PIC18 interrupt vectors are remapped by the bootloader:
- High-priority: 0x0008 (boot) -> 0x1008 (app)
- Low-priority: 0x0018 (boot) -> not used

## Code Analysis Statistics

| Metric | Count |
|--------|-------|
| Actual Code Size | ~14.2 KB (0x10AC-0x496F) |
| Total Instruction Words | 6,150 |
| CALL Instructions | 353 |
| RCALL Instructions | 42 |
| GOTO Instructions | 25 |
| Functions (RETURN) | 103 |
| Interrupt Returns (RETFIE) | 1 (at 0x3B94) |
| Unique Call Targets | 132 |
| Table Read (TBLRD) | 10 |
| Table Write (TBLWT) | 3 |

## Function Regions

Based on CALL target analysis (132 unique targets):

| Region | Functions | Description |
|--------|-----------|-------------|
| 0x1000-0x17FF | 4 | Initialization, entry |
| 0x1800-0x1FFF | 4 | Early setup routines |
| 0x2000-0x27FF | 8 | |
| 0x2800-0x2FFF | 11 | |
| 0x3000-0x37FF | 15 | |
| 0x3800-0x3FFF | 19 | ISR handler at 0x3B1E, main at 0x3D4E |
| 0x4000-0x47FF | 43 | Main application logic, command handlers |
| 0x4800-0x496F | 28 | Small utility functions (SPI/DSP routines) |

### Dense Function Cluster (0x4800-0x496F)

This region contains many tiny functions (2-6 instructions each) that appear to
be SPI/DSP register access routines. Functions at 0x495A-0x496E are only 2 words
each (a single instruction + RETURN), likely single-register read/write wrappers.

## Data Regions

### USB Descriptor Tables (0x1018-0x10AB)

```
0x1018: Hex character lookup table "0123456789ABCDEF" (17 bytes)
0x1029: Unknown data (3 bytes)
0x102C: Configuration Descriptor block (41 bytes)
0x1055: HID Report Descriptor (29 bytes)
0x1072: String Descriptor: "Hypex BV" (22 bytes)
0x1088: Device Descriptor (18 bytes)
0x109A: String Descriptor: "DLCP" (12 bytes)
0x10A6: String Descriptor: Language ID 0x0409 (4 bytes)
0x10AA: Padding (2 bytes)
```

### DSP Register Initialization Table (0x5600-0x5FF6)

TAS3108 configuration/coefficient upload table stored in PIC flash at
`0x5600–0x5FFF` (`0xA00` bytes). It is laid out as 24-byte slots (12 PIC words):

```
Word 0:  (TAS3108_subaddress << 8) | 0x01    (0x01 marks a valid I2C-write slot)
Word 1:  data_size (0x0004=marker/ctrl, 0x0014=biquad, 0x0010=other DSP init)
Words 2-11: payload (up to 20 bytes; padded inside the 24-byte slot)
```

In the shipped V2.3 image, the `op==0x01` slots decode as:
- 6 channel markers: subaddrs `0xC8..0xCD`, length `0x0004`
- 90 biquad writes: subaddrs `0x37..0x90`, length `0x0014` (20-byte payload)
- 1 commit/apply record: subaddr `0xD4`, length `0x0004`
- 2 additional 16-byte writes: subaddrs `0x32` and `0x35`, length `0x0010`

All coefficient payload data is zero in the default table (flat/bypass).

### Unused Flash Gap (0x4970-0x55FF)

3,216 bytes of erased flash (all 0xFFFF). This space is available for code patches.

## EEPROM Contents (0xF00000, 256 bytes)

| Offset | Value(s) | Description |
|--------|----------|-------------|
| 0x00-0x02 | 0xFF, 0xFF, 0xFF | Unprogrammed (erased) |
| 0x03 | 0xA0 | Configuration byte |
| 0x04-0x05 | 0x01, 0x00 | Setting (possibly channel config) |
| 0x06-0x09 | 0x00, 0x00, 0x00, 0x00 | Zeros |
| 0x0A-0x0C | 0x01, 0x01, 0x01 | Three flags (all enabled) |
| 0x0D | 0x03 | Parameter |
| 0x0E | 0x04 | Parameter |
| 0x0F | 0x01 | Parameter |
| 0x10-0x13 | 0x00, 0x00, 0x00, 0x00 | Zeros |
| 0x14 | 0x01 | Flag |
| 0x15-0x3F | 0xFF | Unused |
| 0x40 | 0x03 | Setting |
| 0x41-0x7F | 0xFF | Unused |
| 0x80-0x82 | 0x02, 0x03, 0x30 | Version: V2.30 |
| 0x83-0xFE | 0xFF | Unused |
| 0xFF | 0x02 | Checksum/validation |

## DSP Configuration & Filter Analysis

### DSP Identification: Texas Instruments TAS3108

| Property | Value | Evidence |
|----------|-------|----------|
| **DSP Chip** | TI TAS3108 | I2C address 0x68, confirmed by diyAudio/Hypex docs |
| **I2C Address** | 0x34 (7-bit) = 0x68/0x69 (write/read) | Firmware: `MOVLW 0x68` at 0x228C, 0x3874, 0x4376, 0x44EE |
| **I2C Bus Speed** | ~33 kHz | SSPADD=0x77, Fosc=16 MHz: 16M/(4×120)=33.3 kHz |
| **DSP Core Clock** | 135 MHz | TAS3108 datasheet |
| **Data Path** | 48-bit audio | TAS3108 datasheet |
| **Coefficient Width** | 28-bit | TAS3108 datasheet |
| **Multiplier** | 28×48-bit, single-cycle | 76-bit accumulator |
| **Internal CPU** | 8051 @ 24 MHz | Embedded in TAS3108 for algorithm control |
| **Processing Rate** | 96 kHz | Hypex DLCP product specifications |

### Audio Channels: 6

The DLCP operates as a 6-channel digital crossover/correction processor.

**Firmware evidence:**
- `MOVLW 0x06` at 0x2428 followed by `MOVWF 0x164` sets channel count
- DSP init table has 6 coefficient groups (0xC8-0xCD)
- Volume control section has 6 registers (TAS3108 regs 0x31-0x36)
- EEPROM offsets 0x0A-0x0C store per-channel enable flags (3 pairs)

**Typical configurations:** 3-way stereo or 2-way + sub stereo crossover.

### Filter Type: IIR Biquad Only

The DLCP firmware uses **IIR biquad filters exclusively**. While the TAS3108 hardware
supports both FIR and IIR, the DLCP firmware only implements IIR biquads.

Each biquad implements the standard transfer function:

```
y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]
```

5 coefficients per biquad: b0, b1, b2, a1, a2 (28-bit each, stored in 32-bit
TAS3108 registers).

### Biquads Per Channel: 15

Each channel has **15 biquad IIR filter stages** (confirmed by both firmware analysis
and Hypex documentation).

**Firmware evidence:**
- `MOVLW 0x0F` (15) at 0x242C stored into per-channel registers 0x165-0x16A
- DSP init table has exactly 15 register entries per channel group
- Each entry has a 20-byte data payload = 5 coefficients × 4 bytes = 1 biquad

**Total:** 15 biquads × 6 channels = **90 biquads** across the entire system.

### Filter Coefficient Storage & Upload

**Static default table (PIC flash 0x5600-0x5FFF):**
All coefficient data initialized to zero (bypass/flat response). The host software
computes and uploads actual coefficient values at runtime.

**Upload path:**
```
PC (Hypex Filter Design)
  |
  | USB HID 64-byte reports (commands 0x0A upload, 0x0D download)
  v
PIC18F2455 (USB controller)
  |
  | I2C Master @ 33 kHz (address 0x68)
  v
TAS3108 (coefficient RAM)
  |
  | Internal 135 MHz DSP core
  v
Audio output (6-ch DAC)
```

**Coefficient format:**
- TAS3108 native: 28-bit signed fixed-point, stored in 32-bit registers
- USB transfer: likely 3 bytes per coefficient (24-bit) with PIC converting to 28-bit
- 5 coefficients per biquad = 20 bytes per biquad (TAS3108 side)

### DSP / Config Table (0x5600-0x5FFF) - Decoded

The table uses 24-byte entries (12 PIC words each):

```
Word 0:  (TAS3108_subaddress << 8) | 0x01
Word 1:  data_size (0x0004=marker/ctrl, 0x0014=biquad, 0x0010=other DSP init)
Words 2-11: coefficient data payload (20 bytes, all zeros = bypass)
```

**Channel Group Map:**

| Group Marker | Channel | TAS3108 Regs | Biquads | Flash Range |
|:------------:|:-------:|:------------:|:-------:|:-----------:|
| 0xC8 | 1 | 0x37-0x45 | 15 | 0x5600-0x577F |
| 0xC9 | 2 | 0x46-0x54 | 15 | 0x5780-0x58FF |
| 0xCA | 3 | 0x55-0x63 | 15 | 0x5900-0x5A7F |
| 0xCB | 4 | 0x64-0x72 | 15 | 0x5A80-0x5BFF |
| 0xCC | 5 | 0x73-0x81 | 15 | 0x5C00-0x5D7F |
| 0xCD | 6 | 0x82-0x90 | 15 | 0x5D80-0x5EFF |
| 0xD4 | Commit/apply | - | - | 0x5F00 |

Additional `op==0x01` records present in the stock table:
- `0x5F30`: subaddr `0x32`, length `0x0010` (payload all 0x00 in stock image)
- `0x5FA8`: subaddr `0x35`, length `0x0010` (payload all 0x00 in stock image)

Other 24-byte slots in `0x5600..0x5FFF` have `op==0x00` and appear to be padding
and/or unrelated constant data; for patching/presets, treat the whole `0xA00`
region as one persisted blob.

### Preset & Configuration Support

No built-in multi-bank preset system (A/B/C) is present in the stock V2.3 USB
command dispatch (prior analyses claimed a `0x80` bank-select command; it is not
in the top-level dispatch chain).

Persistence in stock firmware:
- DSP coefficient/config table persists in program flash (`0x5600..0x5FFF`).
- EEPROM (`0xF00000`, 256 bytes) stores small settings (enable flags, version,
  validation byte, etc.).

### Per-Channel Parameters

| Parameter | Evidence | Notes |
|-----------|----------|-------|
| 15 biquad filters | DSP table, MOVLW 0x0F | Configurable filter type per biquad |
| Gain/Delay/Mute/etc | USB/serial command handlers in firmware | Exact register mapping needs per-command tracing; do not assume 0x31-0x36 without verification |

### Initialization Sequence

At startup (0x3566-0x35D6), the PIC initializes:
1. GPIO ports (TRISA=0x07, TRISB=0x00, TRISC=0x87)
2. I2C master (SSPCON1=0x38, SSPADD=0x77)
3. ADC (ADCON0=0x01, ADCON1=0x0C, ADCON2=0xB5)
4. Timers (T0CON=0x07, T1CON=0x80)
5. TAS3108 detection via I2C read, checking for response 0x77 or 0x88
6. If TAS3108 found: initialize DSP with coefficient table from flash
7. Load EEPROM configuration (channel enables, filter types)
8. Enable USB and enter main loop

### Second I2C Device (Address 0x71)

A second I2C device is accessed at 8-bit address 0xE2/0xE3 (7-bit: 0x71):
- Function at 0x423C performs single-byte read transactions
- Uses START → Write 0xE2 → reg addr → RESTART → Write 0xE3 → Read → NACK → STOP
- Possibly an EEPROM, GPIO expander, or secondary DSP/DAC

### I2C Communication Summary

| Address (8-bit) | 7-bit | R/W | Device | Locations |
|:----------------:|:-----:|:---:|--------|-----------|
| 0x68 | 0x34 | W | TAS3108 (write) | 0x228C, 0x3874, 0x4376, 0x44EE |
| 0x69 | 0x34 | R | TAS3108 (read) | (implied) |
| 0xE2 | 0x71 | W | Secondary device | 0x424A, 0x46C4 |
| 0xE3 | 0x71 | R | Secondary device | 0x425C, 0x2144 |

I2C START conditions found at: 0x2286, 0x386E, 0x4244, 0x4370, 0x44E8, 0x46BE

## Patching Feasibility

### Advantages:
1. **Application Not Protected** -- Code can be read and modified freely
2. **Config Not Write-Protected** -- WRTC=1, config bits can be changed
3. **Boot Block Readable** -- CPB=1 and EBTRB=1, bootloader code can be examined
4. **Standard Format** -- Intel HEX, well-documented PIC18 architecture
5. **USB Bootloader** -- Updates via USB HID (application area)
6. **3.1 KB Free Space** -- Erased gap at 0x4970-0x55FF for new code
7. **Tools Available** -- gpdasm, gpasm, gplink, Ghidra, radare2, rizin

### Limitations:
1. **No Source Code** -- Modifications must be at assembly level
2. **No Debug Interface** -- Background debugger disabled in config
3. **Boot Block Write-Protected** -- Cannot modify bootloader via software
4. **No Symbols** -- Function purposes must be reverse-engineered
5. **External DSP** -- DSP behavior depends on register table (0x5600+)

## Errata from Previous Report

The previous ANALYSIS_REPORT.md contained the following errors:

### Critical Errors (wrong conclusions):

| # | Field | Previous (Wrong) | Correct |
|---|-------|-------------------|---------|
| 1 | FOSC oscillator | HSPLL (HS + PLL) | ECPLLIO (EC + PLL, I/O on RA6) |
| 2 | PLLDIV | Divide by 12 (48 MHz crystal) | Divide by 3 (12 MHz ext. clock) |
| 3 | CPUDIV with PLL | PLL/4 = 24 MHz CPU | PLL/6 = 16 MHz CPU |
| 4 | BORV threshold | 4.5V | 2.05V (minimum setting) |
| 5 | WDTPS postscaler | 1:2 | 1:32768 |
| 6 | LVP | Enabled | Disabled |
| 7 | CPB (boot code protect) | YES (CPB=0) | NO (CPB=1) |
| 8 | WRTC (config write prot.) | YES (WRTC=0) | NO (WRTC=1) |
| 9 | EBTRB (boot table read) | YES (EBTRB=0) | NO (EBTRB=1) |
| 10 | Instruction at 0x1010 | MOVFF 0xD8F, 0x01D | CALL 0x3B1E, FAST |
| 11 | bcdDevice release | 1.00 | 0.01 |

### Moderate Errors (incomplete/misleading):

| # | Issue | Detail |
|---|-------|--------|
| 12 | EP1 OUT missing | Config descriptor has 2 endpoints; report only showed EP1 IN |
| 13 | EEPROM offset | Report says 0xA0 at offset 0x02; it is at offset 0x03 |
| 14 | EEPROM data | Report omits 18 non-FF bytes (offsets 0x04-0x14) |
| 15 | STVREN omitted | Stack overflow reset disabled (STVREN=0) not mentioned |
| 16 | PWRT omitted | Power-up Timer enabled (PWRTEN=0) not mentioned |
| 17 | Code statistics | All counts were wrong due to data-as-code confusion |
| 18 | "12 RETFIE" | Actually 1 RETFIE in code; 12 were data values (0x0010) |
| 19 | 0x4800-0x5FFF | Listed as "USB and DSP routines" -- actually data tables |
| 20 | "Boot block fully protected" | Only write-protected; readable and table-readable |

### Root Cause

Most errors stem from two issues:
1. **Incorrect config bit polarity** -- PIC18 protection bits use active-low logic
   (0 = protected, 1 = unprotected). The report inverted several of these.
2. **Data treated as code** -- The DSP/config table (0x5600-0x5FFF) and the USB
   descriptor area (0x1018-0x10AB) were disassembled as instructions, inflating
   counts and producing false RETFIE/instruction statistics.

## Files

| File | Description |
|------|-------------|
| `DLCP Firmware V2.3.hex` | Original firmware (Intel HEX, 58 KB text) |
| `analysis/code_only.bin` | Code section binary (20,480 bytes, 0x1000-0x5FFF) |
| `analysis/eeprom.bin` | EEPROM contents (256 bytes) |
| `analysis/firmware.bin` | Full binary (sparse, 15 MB) |
| `analysis/disasm/gpdasm_output.asm` | gpdasm full disassembly |

## Tools Used

- **gpdasm** (gputils 1.5.2) -- PIC18F24/25xx disassembly and config decoding
- **Python 3** -- HEX parsing, USB descriptor decoding, instruction scanning
- **gputils p18f2455.inc / p18f2550.inc** -- Config bit definitions

---
*Re-analysis performed: 2026-02-13*
*Verified against Microchip PIC18F2455/2550 family datasheet + gputils 1.5.2 definitions,*
*TI TAS3108 datasheet (SLES152B), and Hypex DLCP product documentation*
