# MAIN Clock Timing (PIC18F2455)

Date: 2026-03-11

This note resolves the MAIN clock/timing basis from the stock firmware image and
the `PIC18F2455/2550/4455/4550` datasheet in:

- `firmware/reference/39632e.pdf` (authoritative)
- `firmware/reference/39632e.md` (line-stable converted companion)

If the Markdown conversion drops or mangles table cells, treat the PDF as ground
truth.

## Conclusion

Stock MAIN should be timed as:

- external source into `OSC1/CLKI`: `12 MHz`
- oscillator mode: `ECPIO` (external clock, PLL enabled, RA6 as port)
- system clock `Fosc`: `16 MHz`
- instruction clock: `Fosc/4 = 4 MHz`
- instruction cycle `Tcy`: `250 ns`

This does **not** match a raw `24 MHz` crystal/input interpretation.

## Primary Evidence

### 1. Stock configuration words

From stock MAIN `V2.3`:

- `CONFIG1L = 0x3A`
- `CONFIG1H = 0x46`

These bytes are present in the stock MAIN hex at `0x300000` and `0x300001`.

### 2. Datasheet decode

From `CONFIG1L` / `CONFIG1H` in the datasheet:

- `CPUDIV1:CPUDIV0 = 11`
  - in PLL modes, this means `96 MHz PLL / 6` for the system clock
  - source: [39632e.md](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/reference/39632e.md#L11469)
- `PLLDIV2:PLLDIV0 = 010`
  - this means `divide by 3` for a `12 MHz oscillator input`
  - source: [39632e.md](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/reference/39632e.md#L11469)
- `FOSC3:FOSC0 = 0110`
  - this means `ECPIO`: external clock, PLL enabled, RA6 as port
  - source: [39632e.md](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/reference/39632e.md#L11489)

The stock disassembly summary agrees:

- `PLLDIV = 3`
- `CPUDIV = OSC4_PLL6`
- `USBDIV = 2`
- `FOSC = ECPLLIO_EC`

See [gpdasm_short.asm](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/disasm/main/gpdasm_short.asm#L9).

## Derived Clock Chain

The datasheet clock path is:

1. `12 MHz` external clock enters `OSC1/CLKI`
2. `PLLDIV=/3` produces `4 MHz` PLL input
3. the USB PLL runs at `96 MHz`
4. `CPUDIV=/6` produces `16 MHz` system clock `Fosc`
5. PIC18 instruction rate is `Fosc/4 = 4 MHz`

Instruction cycle rule:

- one instruction cycle is four oscillator periods
- source: [39632e.md](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/reference/39632e.md#L2473)

Therefore:

- `Fosc = 16 MHz`
- `Tcy = 1 / 4 MHz = 250 ns`

## Runtime Cross-Checks

### UART

MAIN UART init sets:

- `TXSTA = 0x06`
- `BAUDCON = 0x48`
- `SPBRGH = 0x00`
- `SPBRG = 0x7F`

See [gpdasm_output.asm](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/disasm/main/gpdasm_output.asm#L8821).

This means:

- asynchronous mode
- `BRGH = 1`
- `BRG16 = 1`
- `n = 127`

Datasheet baud formula for async `BRGH=1`, `BRG16=1` is:

- `baud = Fosc / (4 * (n + 1))`
- source: [39632e.md](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/reference/39632e.md#L9714)

With `Fosc = 16 MHz`:

- `baud = 16,000,000 / (4 * 128) = 31,250`

This matches the DLCP current-loop link exactly.

If `Fosc` were `24 MHz`, the same register settings would produce:

- `24,000,000 / (4 * 128) = 46,875`

That does **not** match stock behavior.

### I2C / MSSP

MAIN sets:

- `SSPADD = 0x77`

See [gpdasm_output.asm](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/disasm/main/gpdasm_output.asm#L6188).

Datasheet master-I2C formula:

- `Fscl = Fosc / (4 * (SSPADD + 1))`
- source: [39632e.md](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/reference/39632e.md#L8581)

With `Fosc = 16 MHz`:

- `Fscl = 16,000,000 / (4 * 120) = 33,333.33 Hz`

## Timing Numbers Relevant To `V2.5`

### Serial wire time

At `31,250` baud, `8N1`:

- `10` bits per byte
- `320 us` per byte on the wire

At MAIN instruction rate (`4 MHz`):

- `320 us / 250 ns = 1280 Tcy` per byte

### Current `V2.5` timeout budgets

The rebuilt `V2.5` MAIN patch uses a 16-bit loop seed:

- `timeout_lo = 0x00`
- `timeout_hi = 0x10`

See [build_main_presets_ab.py](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/src/dlcp_fw/patch/build_main_presets_ab.py#L232).

Using the actual PIC18 instruction timing and the emitted helper structure:

- simple wait helpers (`TRMT`, `SSPIF`, `BF`, `SEN`, `PEN`) timeout after about `20,520` instruction cycles
  - about `5.13 ms`
  - about `16` serial byte-times at `31,250` baud
- packed MSSP-idle wait helper times out after about `41,000` instruction cycles
  - about `10.25 ms`
  - about `32` serial byte-times at `31,250` baud

These are the numbers that should be used when reasoning about the current
`V2.5` robustness patch.

## Implications

1. MAIN timing should be modeled with `Fosc = 16 MHz`, not `12 MHz`.
2. MAIN serial wire pacing in gpsim-style harnesses should use `1280 Tcy/byte`.
3. Any older repo text that assumed MAIN was `12 MHz` / `960 Tcy/byte` is stale.
4. A physical `24 MHz` oscillator on the board would only make sense if it is
   externally divided or otherwise transformed before the PIC clock input.
   Stock PIC config does not support a raw `24 MHz` input interpretation.
