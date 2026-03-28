# V3.0 MAIN — Source-Level Rewrite Specification

Date: 2026-03-28
Status: draft
Depends on: V2.3 stock firmware (baseline), annotated disassembly, SEMANTIC_FUNCTION_MAP.md

## Motivation

### Problem

The DLCP MAIN firmware has been extended via binary patching since V2.4.
Each version (V2.4 A/B presets, V2.5 robustness, V2.6 ACKSTAT, V2.7
bus-clear) injects assembled stubs into erased flash regions and rewires
branch targets.  This approach has reached its limits:

- **Space exhaustion**: V2.7 requires ~132 bytes of new code.  The
  available free space in the 0x4970–0x55FF erased region is nearly
  consumed after V2.6.  Dead-zone scavenging (function_072 gap, etc.)
  yields only fragments.
- **Fragility**: Each patch must carefully avoid clobbering prior
  patches, maintain exact byte offsets, and hand-assemble branch
  targets.  The overlay/remap system in `build_main_presets_ab.py`
  is ~1,300 lines of Python generating ad-hoc assembly.
- **No refactoring**: Binary patching cannot restructure code.  Known
  bugs (M1–M9) that require rearranging logic or inserting checks
  into tight loops are impractical to fix.
- **Maintainability**: Every future feature requires increasingly
  heroic space-finding and offset-juggling.

### Solution

Create **V3.0**: a clean, assembler-ready PIC18F2455 source file that:

1. Assembles via `gpasm` to an **app-only** hex file that is
   **functionally equivalent** to the stock `DLCP Firmware V2.3.hex`,
   verified by high-fidelity gpsim simulation.  Byte-identity is a
   goal (aids debugging) but **not required** — encoding differences
   from gpasm are acceptable as long as behavior is identical.
2. Uses semantic labels, named RAM variables, structured macros, and
   comments — as if we had the original Hypex source.
3. Becomes the new baseline for all future work (V3.1 = V3.0 + A/B
   presets, V3.2 = V3.1 + robustness, etc.), eliminating binary
   patching entirely.

**Baseline image**: `DLCP Firmware V2.3.hex` (app-only, starts at
0x1000).  This is explicitly **not** the full-device recovery image
(`DLCP Firmware V2.3-combined.hex`).  The gpsim harness already handles
seeding app-only hex onto the combined recovery image via
`build_seeded_main_sim_hex()` — V3.0 output feeds into the same
pipeline.

---

## Scope

### In scope

- One `.asm` source file (+ include files) that assembles to an
  **app-only** Intel HEX **functionally equivalent** to
  `DLCP Firmware V2.3.hex`.  Minor encoding differences (access-bit
  choices, NOP padding) are acceptable.
- Config bits (0x300000–0x30000D) reproduced from source.
- EEPROM initial values (0xF00000–0xF000FF) reproduced from source.
- USB descriptor tables emitted as data (`db`/`dw`), not as code.
- Full gpsim simulation parity: the assembled V3.0 hex, when seeded
  via `build_seeded_main_sim_hex()`, must pass every existing V2.3
  gpsim test.
- A build script that invokes gpasm and verifies the output.
- A byte-comparison diagnostic step (assembled hex vs. stock hex) to
  track and understand differences — used for debugging, not as a gate.
- A new pytest fixture (`v30_main_hex`) and equivalence test file.

### Out of scope

- **Boot block** (0x0000–0x07FF): The stock app hex does not contain
  boot block data (the disassembly starts at 0x1000).  Boot block
  content comes from PICkit readback and lives in the combined
  recovery image.  V3.0 does not emit boot block bytes.
- **User ID memory** (0x200000–0x200007): All 0xFF in stock.  Not
  emitted (gpasm default).
- **Full-device recovery image**: A future packer step can merge V3.0
  app hex onto the combined recovery seed, same as today.
- Bug fixes (M1–M9).  V3.0 reproduces V2.3 behavior including all
  known bugs.  Fixes come in V3.1+.
- A/B preset support, robustness patches, ACKSTAT checks.  These
  are future layers on top of V3.0.
- CONTROL firmware.  V3.0 addresses MAIN only.

---

## Deliverables

### D1: Source file — `src/dlcp_fw/asm/dlcp_main_v30.asm`

A single gpasm-compatible PIC18F2455 assembly source file containing:

- `LIST P=18F2455` directive and `#include <p18f2455.inc>`
- `__CONFIG` directives matching the stock configuration bits
  exactly (see §Config Bits below).  Note: gputils `p18f2455.inc`
  documents that `__CONFIG` is the legacy form; the header uses it
  with `_CONFIGxY` address symbols and `_OPTION_VALUE_xY` constants.
- `org` directives placing code and data at their original addresses
- Semantic label names from `SEMANTIC_FUNCTION_MAP.md` (e.g.,
  `main_isr_dispatch`, `adc_boot_gate`, `uart_tx_byte_blocking`)
- Named RAM variable definitions via `equ` or `cblock` (e.g.,
  `active_gate equ 0x05E`, `preset_b_active_bit equ 2`)
- Properly separated code vs. data sections:
  - USB descriptor tables as `db`/`dw` data blocks with comments
  - ASCII string tables as `db` with string literals
  - DSP preset/coefficient table (0x5600–0x5FFF) as `dw` data
  - Erased flash regions (0x4970–0x55FF) as `fill 0xFF`
- All 131 functions and 600+ labels with semantic names where known,
  original auto-names (`function_NNN`, `label_NNN`) where not yet
  identified
- Program memory from 0x1000–0x496F (code) + 0x5600–0x5FFF (data)
- No boot block (0x0000–0x07FF) — out of scope, handled by recovery
  image seed

### D2: Include files (optional)

- `dlcp_main_ram.inc` — RAM variable and bit definitions
- `dlcp_main_macros.inc` — common patterns (e.g., `WAIT_BF_CLEAR`,
  `I2C_START`, `UART_TX`) as macros for readability (expanding to
  identical code)

### D3: Build script — `scripts/build_v30.sh`

```bash
#!/bin/bash
# Assemble V3.0 and verify against stock V2.3
set -euo pipefail

GPASM=${GPASM:-gpasm}
SRC=src/dlcp_fw/asm/dlcp_main_v30.asm
OUT=firmware/patched/releases/DLCP_Firmware_V3.0.hex
STOCK="firmware/stock/main/DLCP Firmware V2.3.hex"

$GPASM -p18f2455 -o "$OUT" "$SRC"

# Byte-compare (diagnostic, not a hard gate)
python3 -c "
from dlcp_fw.sim.hexio import parse_intel_hex
stock = parse_intel_hex('$STOCK')
built = parse_intel_hex('$OUT')
mismatches = []
for addr in sorted(set(stock) | set(built)):
    s = stock.get(addr, 0xFF)
    b = built.get(addr, 0xFF)
    if s != b:
        mismatches.append((addr, s, b))
if mismatches:
    for a, s, b in mismatches[:20]:
        print(f'  0x{a:06X}: stock=0x{s:02X} built=0x{b:02X}')
    print(f'Total byte differences: {len(mismatches)}')
    print('WARNING: not byte-identical (functional equivalence via gpsim is the real gate)')
else:
    print('OK: byte-identical to stock V2.3')
"
```

### D4: gpsim functional equivalence test

A new pytest file `tests/sim/test_v30_equivalence.py` that:

1. Loads the assembled V3.0 hex into the existing `MainChainHarness`
2. Runs the full V2.3 test scenarios (boot, wake/standby, volume,
   status burst, UART RX, I2C DSP writes, USB descriptors)
3. Compares all observable outputs (UART TX frames, I2C bus
   transactions, RAM state snapshots) against the stock V2.3
   baseline
4. Verifies the preset table at 0x5600–0x5FFF is identical

---

## Technical Approach

### Phase 1: Automated disassembly-to-source conversion

Write a Python converter (`src/dlcp_fw/analysis/disasm_to_source.py`,
thin entrypoint at `scripts/disasm_to_source.py`) that:

1. **Parses the stock hex** (`DLCP Firmware V2.3.hex`) byte-by-byte
   into a memory image (0x1000–0x5FFF program, 0xF00000–0xF000FF
   EEPROM, 0x300000–0x30000D config)
2. **Parses the annotated disassembly** (`gpdasm_output.annotated.asm`)
   to extract:
   - Function boundaries and labels with semantic names
   - Instruction addresses and opcodes
   - Data regions (USB descriptors, strings, preset tables)
3. **Classifies each address range** using the region manifest
   (`src/dlcp_fw/asm/region_manifest.py`) as primary authority:
   - **Code**: instructions that decode to valid PIC18 mnemonics and
     are reachable from the call/jump graph (or are marked as code
     in the manifest — TBLRD-accessed tables that look like code
     must be overridden to data in the manifest)
   - **Data**: USB descriptor tables, ASCII strings, DSP coefficient
     tables, lookup tables — emitted as `db`/`dw` directives
   - **Erased**: 0xFF-filled regions — emitted as `fill` or omitted
   - **Out of range**: 0x0000–0x0FFF (not in app hex, handled by
     recovery image seed)
4. **Emits a .asm file** with:
   - Proper `org` directives for each contiguous block
   - Semantic labels where available
   - PIC18 mnemonics with symbolic register names (from p18f2455.inc)
   - Data sections with human-readable formatting
   - Comments cross-referencing the semantic function map

### Phase 2: Data region identification

The annotated disassembly incorrectly decodes data as instructions.
These regions must be identified and emitted as raw data:

| Region | Address range | Content | Emit as |
|--------|--------------|---------|---------|
| USB descriptors block | 0x1018–0x1087 | Mixed: pointer tables, HID report desc, config desc | `db`/`dw` raw data |
| USB device descriptor | 0x1088–0x1099 | 18 bytes (starts `0x12, 0x01, 0x00, 0x02`) | `db` with field comments |
| USB string descriptors | 0x1072–0x1087 | "Hypex BV", "DLCP", etc. | `db` with ASCII comments |
| USB config descriptor | ~0x102C–0x1054 | Config + interface + HID + endpoint (`0x09, 0x02, 0x29, 0x00`) | `db` with field comments |
| USB HID report descriptor | ~0x1055–0x1071 | HID report map | `db` |
| Lookup/jump tables | Various (identified by `TBLRD*` readers, `addwf PCL` patterns) | Computed goto targets, coefficient indices | `dw` or `goto` table |
| DSP preset table A | 0x5600–0x5FFF | TAS3108 coefficients | `dw` with structure comments |
| EEPROM init data | 0xF00000–0xF000FF | Filename, version, config | `org 0xF00000` + `db` |

**Key challenges**:

1. The USB descriptor area (0x1018–0x10FF approx) is interleaved with
   pointer tables and the disassembler decodes it all as instructions.
   The converter must use the **stock hex bytes as ground truth**, not
   the disassembler's instruction decoding.

2. `TBLRD*`-accessed lookup tables appear inline with code.  These
   cannot be identified by call-graph reachability alone.  A **manual
   region manifest** is required — a list of `(start_addr, end_addr,
   type)` tuples that the converter consults before deciding code vs
   data.  The manifest is seeded from the semantic function map and
   refined iteratively during byte-comparison.

3. The exact USB descriptor boundaries listed above are approximate.
   Step 1 of implementation must dump the raw hex bytes in the
   0x1018–0x10FF range and identify each descriptor by its standard
   USB/HID header bytes.

### Phase 3: Code region reconstruction

For each function identified in the semantic map:

1. **Decode from hex bytes** — not from the disassembler output (which
   may misparse data as code).  Use the PIC18 instruction set encoding
   to re-derive mnemonics.
2. **Resolve symbolic operands** — replace numeric register addresses
   with symbolic names from `p18f2455.inc` (e.g., `0xFAB` → `RCSTA`,
   `0xFC6` → `SSPCON1`).
3. **Resolve branch targets** — replace numeric destinations with
   labels (e.g., `goto 0x003B1E` → `goto main_isr_dispatch`).
4. **Verify round-trip** — assemble the **whole image** (not individual
   functions — PIC18 multi-word instructions and absolute `call`/`goto`
   encodings require full-image context) and compare the output bytes
   against the stock hex.  Iterate on mismatches.

### Phase 4: Assembly and byte-comparison diagnostic

1. Assemble `dlcp_main_v30.asm` with `gpasm -p18f2455`
2. Parse both hex files into byte dictionaries
3. Run byte-comparison diagnostic to identify and categorize
   differences:
   - **Data regions** (preset table, config, EEPROM): must be
     identical — any mismatch here is a real bug
   - **Code regions** (0x1000–0x496F): differences are expected
     from gpasm encoding choices — log them, investigate any that
     look like wrong instructions (vs. just access-bit flips)
4. Use the diagnostic to guide iterative fixes, but do NOT chase
   byte-parity at the cost of source cleanliness

### Phase 5: gpsim simulation validation

1. Add a `V30_MAIN_HEX` path constant to `src/dlcp_fw/paths.py`
2. Add a `v30_main_hex` pytest fixture to `tests/sim/conftest.py`
3. Load V3.0 hex into `MainChainHarness` via
   `build_seeded_main_sim_hex()` (same pipeline as stock V2.3)
4. Run the stock-compatible subset of the test suite with V3.0 hex
5. Wire-chain tests with stock CONTROL must pass
6. Any test that passes with `DLCP Firmware V2.3.hex` must pass with
   `DLCP_Firmware_V3.0.hex`

**Note**: Minimal test infrastructure changes are required (new path
constant + fixture).  No test logic changes.

---

## Config Bits

Raw register values extracted from the stock hex (verified from the
Intel HEX record `:0E0000003A463E1EFF0080FF0FC00FA00F40CB` at
extended address 0x0030):

| Register | Address | Value | Decoded |
|----------|---------|-------|---------|
| CONFIG1L | 0x300000 | **0x3A** | PLLDIV=3, CPUDIV=OSC4_PLL6, USBDIV=2 |
| CONFIG1H | 0x300001 | **0x46** | FOSC=ECPLLIO_EC, FCMEN=ON, IESO=OFF |
| CONFIG2L | 0x300002 | **0x3E** | PWRT=ON, BOR=ON, BORV=3, VREGEN=ON |
| CONFIG2H | 0x300003 | **0x1E** | WDT=OFF, WDTPS=32768 |
| (skip)   | 0x300004 | 0xFF  | (reserved, not a config register) |
| CONFIG3H | 0x300005 | **0x00** | CCP2MX=OFF, PBADEN=OFF, LPT1OSC=OFF, MCLRE=OFF |
| CONFIG4L | 0x300006 | **0x80** | STVREN=OFF, LVP=OFF, XINST=OFF, DEBUG=OFF |
| (skip)   | 0x300007 | 0xFF  | (reserved) |
| CONFIG5L | 0x300008 | **0x0F** | CP0=OFF, CP1=OFF, CP2=OFF (+ CP3=OFF) |
| CONFIG5H | 0x300009 | **0xC0** | CPB=OFF, CPD=OFF |
| CONFIG6L | 0x30000A | **0x0F** | WRT0=OFF, WRT1=OFF, WRT2=OFF (+ WRT3=OFF) |
| CONFIG6H | 0x30000B | **0xA0** | WRTC=OFF, WRTB=ON, WRTD=OFF |
| CONFIG7L | 0x30000C | **0x0F** | EBTR0=OFF, EBTR1=OFF, EBTR2=OFF (+ EBTR3=OFF) |
| CONFIG7H | 0x30000D | **0x40** | EBTRB=OFF |

Note: CONFIG5L/6L/7L are **0x0F** (not 0x07) — the PIC18F2455 has
4 code protection blocks (0–3), and the stock firmware disables
protection on all 4.

Symbolic form using gputils `p18f2455.inc` constants:

```asm
; Configuration bits — must match stock V2.3 exactly
; Verify assembled output against raw values above.
  __CONFIG _CONFIG1L, _PLLDIV_3_1L & _CPUDIV_OSC4_PLL6_1L & _USBDIV_2_1L
  __CONFIG _CONFIG1H, _FOSC_ECPLLIO_EC_1H & _FCMEN_ON_1H & _IESO_OFF_1H
  __CONFIG _CONFIG2L, _PWRT_ON_2L & _BOR_ON_2L & _BORV_3_2L & _VREGEN_ON_2L
  __CONFIG _CONFIG2H, _WDT_OFF_2H & _WDTPS_32768_2H
  __CONFIG _CONFIG3H, _CCP2MX_OFF_3H & _PBADEN_OFF_3H & _LPT1OSC_OFF_3H & _MCLRE_OFF_3H
  __CONFIG _CONFIG4L, _STVREN_OFF_4L & _LVP_OFF_4L & _XINST_OFF_4L
  __CONFIG _CONFIG5L, _CP0_OFF_5L & _CP1_OFF_5L & _CP2_OFF_5L & _CP3_OFF_5L
  __CONFIG _CONFIG5H, _CPB_OFF_5H & _CPD_OFF_5H
  __CONFIG _CONFIG6L, _WRT0_OFF_6L & _WRT1_OFF_6L & _WRT2_OFF_6L & _WRT3_OFF_6L
  __CONFIG _CONFIG6H, _WRTC_OFF_6H & _WRTB_ON_6H & _WRTD_OFF_6H
  __CONFIG _CONFIG7L, _EBTR0_OFF_7L & _EBTR1_OFF_7L & _EBTR2_OFF_7L & _EBTR3_OFF_7L
  __CONFIG _CONFIG7H, _EBTRB_OFF_7H
```

**Implementation note**: The exact macro names above need verification
against the installed `/opt/homebrew/share/gputils/header/p18f2455.inc`.
If any symbolic form does not produce the exact byte value, fall back
to raw hex: `__CONFIG H'300000', H'3A'`, etc.

---

## Memory Map

```
PIC18F2455 Program Memory (24 KB = 0x6000 bytes, byte-addressed)

Hardware vectors (NOT in V3.0 app-only output):
  0x0000         PIC18 reset vector (jumps to app entry)
  0x0008         High-priority ISR vector
  0x0018         Low-priority ISR vector
  0x0000–0x07FF  Boot block (2 KB, write-protected by CONFIG6H.WRTB=ON)

V3.0 app-only output covers:
  0x1000–0x1017  App entry + ISR dispatch stubs (NOT the PIC18 reset
                 vector — that's at 0x0000 in the boot block.  0x1000 is
                 where the boot block's goto lands.)
  0x1018–0x10FF  USB descriptors + string tables + pointer tables (DATA)
  0x1100–0x496F  Application code (131 functions, ~14.5 KB)
  0x4970–0x55FF  Erased flash (all 0xFF — V2.4+ patches went here)
  0x5600–0x5FFF  DSP preset table A (2.5 KB, DATA)

EEPROM (256 bytes):
  0xF00000–0xF000FF  EEPROM init image (filename at 0x60, version at 0x80)

Config Registers:
  0x300000–0x30000D  Configuration bits (12 registers, 2 reserved/skipped)

Not in V3.0 output (supplied by recovery image seed):
  0x0000–0x0FFF  Boot block + block 0 lower
  0x200000–0x200007  User ID memory (all 0xFF)
```

---

## RAM Variable Definitions

From `SEMANTIC_FUNCTION_MAP.md`, emitted as `equ` directives:

```asm
; --- General-purpose RAM (Access Bank) ---
active_flags        equ 0x05E
ACTIVE_GATE_BIT     equ 3       ; 0x05E.3 — 1=commands processed
PRESET_B_BIT        equ 2       ; 0x05E.2 — (V2.4+ only, unused in V3.0)
RX_ROUTE_B1_BIT     equ 0       ; 0x05E.0 — set on route 0xB1

event_flags         equ 0x07E
STANDBY_PENDING_BIT equ 2       ; 0x07E.2
VOLUME_DIRTY_BIT    equ 3       ; 0x07E.3

logical_volume      equ 0x066   ; 4 bytes (0x066–0x069)
computed_volume     equ 0x06E   ; 4 bytes (0x06E–0x071)

usb_reinit_pending  equ 0x095
rx_frame_position   equ 0x098
rx_ring_rd          equ 0x0C6
rx_ring_wr          equ 0x0C7

; --- RX ring buffer (Bank 2) ---
rx_ring_base        equ 0x200   ; 192 bytes (0x200–0x2BF)

; --- Scratch / unknown RAM (placeholder scheme) ---
; RAM locations used by code but not yet semantically identified
; get placeholder names: ram_0xNNN (address) or scratch_N (sequential).
; These are refined as analysis progresses — they do NOT block V3.0.
; Example: ram_0x060 equ 0x060
```

**Placeholder scheme**: The semantic function map names ~30 RAM
locations.  The firmware uses many more (scratch registers, loop
counters, temporaries).  These get `ram_0xNNN` placeholder names in
V3.0 — every `equ` has an address, every address has an `equ`, but
not every name is semantically meaningful yet.  This satisfies AC3
("every RAM variable used has a named equ") without requiring
complete reverse-engineering of all scratch usage.

**Note**: `tx_mailbox_base` (0x740) is a gpsim simulation overlay
artifact, not a stock firmware structure.  It is NOT included in the
V3.0 source RAM definitions.

---

## Source File Structure

```asm
;============================================================
; DLCP MAIN Firmware V3.0
; PIC18F2455 — Source-level reconstruction from V2.3 stock
;
; Functionally identical to: DLCP Firmware V2.3.hex
; Assembled with: gpasm -p18f2455
;============================================================

    LIST P=18F2455
    #include <p18f2455.inc>
    #include "dlcp_main_ram.inc"      ; RAM and bit definitions

;--- Configuration bits ---
    [__CONFIG directives — see §Config Bits]

;--- App entry + ISR dispatch (0x1000–0x1017) ---
;    NOTE: This is NOT the PIC18 reset vector (that's at 0x0000 in the
;    boot block).  0x1000 is where the bootloader's goto lands.
    org 0x1000
app_entry:
    goto app_start                   ; → 0x1014
    dw 0xFFFF, 0xFFFF               ; unused slots
isr_dispatch_stub:
    movff FSR2L, isr_save_fsr2l
    movff FSR2H, isr_save_fsr2h
    call main_isr_dispatch           ; fast-return ISR

;--- USB descriptors + data tables (0x1018–0x10FF) ---
;    The disassembler incorrectly decodes this region as instructions.
;    All bytes here are emitted as raw db/dw from the stock hex.
    org 0x1018
    ; [USB pointer tables, config desc, HID report desc, string descs,
    ;  device descriptor — exact boundaries from hex dump analysis]
usb_device_descriptor:               ; @ 0x1088
    db 0x12, 0x01, ...              ; bLength, bDescriptorType, ...

;--- Application code (0x1100–0x496F) ---
    org 0x1100

; ---- Command dispatch ----
cmd_dispatch_gated:                  ; function_005 @ 0x18F2
    btfss active_flags, ACTIVE_GATE_BIT
    return
    ; ...

; ---- Boot / standby ----
adc_boot_gate:                       ; function_024 @ 0x2D8C
    ; ...

; ---- I2C / MSSP ----
i2c_byte_tx:                         ; function_056 @ 0x3EB8
    ; ...

; [... all 131 functions in address order ...]

;--- Erased flash (0x4970–0x55FF) ---
    org 0x4970
    fill 0xFF, (0x5600 - 0x4970)    ; free space for future patches

;--- DSP preset table A (0x5600–0x5FFF) ---
    org 0x5600
preset_table_a:
    ; TAS3108 coefficient data — 0x0A00 bytes
    dw 0x0000, 0x0000, ...          ; [structured with DSP comments]

;--- EEPROM initial data ---
    org 0xF00000
eeprom_data:
    db 0xFF, 0xFF, ...              ; 0x00–0x5F: defaults
    db "LX521.4 V15 L22M"           ; 0x60–0x7D: filename slot A
    db ...
    db 0x02, 0x03, 0x30             ; 0x80–0x82: version 2.3.0

    END
```

---

## Toolchain

### Assembler

- **gpasm** 1.5.2 (gputils), already installed at `/opt/homebrew/bin/gpasm`
- Invocation: `gpasm -p18f2455 -o output.hex input.asm`
- Include path: gputils ships `p18f2455.inc` with register and config
  bit definitions

### Reverse-engineering / disambiguation

Available locally for resolving code-vs-data ambiguities, verifying
control flow, and cross-checking the gpdasm-based annotated disassembly:

- **radare2** 6.0.8 — `/opt/homebrew/bin/r2`
  PIC18 support via `r2 -a pic -b 16`.  Useful for:
  - Cross-reference analysis (`axt`/`axf`) to find TBLRD data readers
  - Call-graph generation (`agC`) to validate reachability
  - Entropy/string heuristics to confirm data regions
  - Quick byte-level inspection without loading a full project

- **Ghidra** 12.0.4 — `/opt/homebrew/bin/ghidraRun`
  PIC-18 processor module.  Useful for:
  - Decompiler output to understand complex function logic
  - Auto-analysis of cross-references and data flow
  - Headless analysis via `analyzeHeadless` for batch scripts
  - Visual call graph and memory map exploration

These tools supplement (not replace) the gpdasm-based annotated
disassembly.  Use them when the annotated disassembly is ambiguous
about whether a region is code or data, or when function semantics
are unclear from the assembly alone.

### Verification

- `parse_intel_hex()` from `src/dlcp_fw/sim/hexio.py` for hex comparison
- Existing gpsim harness (`MainChainHarness`) for simulation
- Existing pytest suite for behavioral regression

### No new dependencies

V3.0 requires no tools beyond what the project already has installed.

---

## Risks and Mitigations

### Risk: Data/code misclassification

The disassembler decodes everything as instructions.  USB descriptors
(0x1018–0x10FF), the DSP preset table (0x5600–0x5FFF), and inline
`TBLRD*`-accessed lookup tables must be emitted as raw data.

Call-graph reachability alone is insufficient: `TBLRD*` data is
accessed via table pointer, not via call/goto, so it appears
"unreachable" but is real data interleaved with code.

**Mitigation**: Use a manual region manifest (code/data/erased
classification per address range) seeded from the semantic function
map and refined iteratively.  Use the stock hex bytes as ground truth
for every byte-comparison pass.

### Risk: gpasm instruction encoding differences

Some PIC18 instructions have multiple valid encodings (e.g., `movf`
with access bit 0 vs 1 when the register is in Access Bank).  gpasm
may choose a different encoding than the original Microchip assembler.

**Mitigation**: Since byte-identity is not required, these differences
are acceptable as long as functional equivalence holds.  The byte-
comparison diagnostic tracks them for visibility.  Use clean `movf`/
`btfss`/etc. mnemonics — do NOT fall back to `dw` raw opcodes just
for encoding parity.

### Risk: gpasm config bit macros

The exact macro names in `p18f2455.inc` for gputils may differ from
Microchip's MPLAB XC8 assembler.

**Mitigation**: Test config bit output first.  Fall back to raw
`__CONFIG addr, value` if needed.

### Risk: Boot block / recovery image interaction

The stock app hex does not include boot block data.  The PICkit 5
readback (combined recovery image) does contain non-FF boot block
bytes.  V3.0 is app-only and does not emit boot block.

**Mitigation**: The gpsim harness already handles this via
`build_seeded_main_sim_hex()`, which merges app-only hex onto the
combined recovery image seed.  V3.0 output feeds into the same
pipeline — no boot block in V3.0 source.

### Risk: Access bank encoding ambiguity

PIC18 instructions that reference registers 0x00–0x5F or 0xF60–0xFFF
can use Access Bank mode (a=0) or BSR-relative mode (a=1).  gpasm
may choose a different access-bit encoding than the original Microchip
assembler, producing functionally equivalent but byte-different output.

**Mitigation**: Acceptable — functional equivalence is the gate, not
byte parity.  Use clean mnemonics with explicit `, A` or `, B` access
specifiers for clarity.  The byte-comparison diagnostic will flag
these for visibility.

### Risk: Relative branch range changes

If labels are reordered or code structure changes even slightly, a
`bra` (±1024 words) or `rcall` (±1024 words) target may go out of
range.

**Mitigation**: V3.0 preserves the exact same address layout as V2.3.
Every `org` directive pins code at its original address.  No code
movement occurs in V3.0.

---

## Acceptance Criteria

### AC1: Clean assembly

`gpasm -p18f2455 dlcp_main_v30.asm` produces an app-only hex file
covering:

- Program memory 0x1000–0x496F: functionally equivalent to stock
- Preset table 0x5600–0x5FFF: data-identical to stock (these are
  DSP coefficients — encoding differences are not acceptable here)
- Config bits 0x300000–0x30000D: identical to stock
- EEPROM 0xF00000–0xF000FF: identical to stock
- Erased regions (0x4970–0x55FF): don't care
- Boot block / User ID: not emitted (out of scope)

Byte-identity across code regions is a goal but not a hard gate.
Minor gpasm encoding differences (access-bit, NOP padding) are
acceptable if gpsim simulation passes.

### AC2: gpsim full simulation pass

V3.0 hex loaded into `MainChainHarness` (via
`build_seeded_main_sim_hex()`) passes the stock-compatible gpsim
tests.  Specifically:

- `test_main_gpsim_an0_boot.py` — ADC gate, app_start entry
- `test_main_gpsim_preset_banks.py` — preset table read
- `test_main_gpsim_i2c_regfile.py` — I2C/DSP writes
- `test_main_gpsim_fault_injection.py` — fault behavior
- `test_main_gpsim_command_matrix.py` — command dispatch
- `test_main_gpsim_mailbox.py` — UART TX output
- `test_wire_chain_gpsim.py` — end-to-end with CONTROL
- `test_wire_chain_gpsim_stock_faults.py` — known V2.3 bugs

Tests that operate on patched-only hex (e.g., `test_bus_faults.py`
which uses `patched_main_hex`, `test_scenarios.py` which uses the
model layer) are not in scope — they test patch features V3.0 does
not include.

(Any gpsim test that passes with `DLCP Firmware V2.3.hex` must pass
with `DLCP_Firmware_V3.0.hex`.)

### AC3: Source readability

- Every function has a semantic label (or documented `function_NNN`
  placeholder for unidentified functions)
- Every RAM variable used has a named `equ`
- Every SFR reference uses the symbolic name from `p18f2455.inc`
- Data regions are clearly separated and commented
- No raw hex addresses in branch targets — all use labels

### AC4: No behavioral changes

V3.0 reproduces all V2.3 behavior including known bugs (M1–M9).
No fix, no optimization, no "improvement."  This is a format change
only.

---

## Future Work (not V3.0)

Once V3.0 is validated, the following become straightforward source
edits instead of binary patching:

- **V3.1**: A/B preset support (currently V2.4 binary patch)
- **V3.2**: Robustness — bounded wait loops (currently V2.5 binary patch)
- **V3.3**: ACKSTAT checks (currently V2.6 binary patch)
- **V3.4**: I2C bus-clear, DSP ping, fault reporting (currently V2.7,
  blocked by space exhaustion)
- **V3.5+**: Bug fixes for M1–M9, code restructuring, new features
  — no longer constrained by available erased flash

The source-level approach also enables:
- Code size optimization (consolidate duplicated patterns)
- Memory map reorganization (move preset table, reclaim space)
- Proper flash wear-leveling for EEPROM emulation
- Conditional assembly (`#ifdef`) for feature variants
- Automated regression via `make` + `pytest`

---

## Implementation Plan

| Step | Description | Verification |
|------|-------------|--------------|
| 0 | Hex dump 0x1018–0x10FF, identify USB descriptor boundaries | Documented boundary table |
| 1 | Create region manifest (code/data/erased per address range) | Manifest covers 0x1000–0x5FFF |
| 2 | Write `src/dlcp_fw/analysis/disasm_to_source.py` converter | Runs without error |
| 3 | Generate initial `dlcp_main_v30.asm` from converter | File exists, gpasm accepts it |
| 4 | Fix data/code misclassifications (USB, strings, TBLRD tables) | Data regions byte-identical |
| 5 | Fix config bits and EEPROM | Config/EEPROM byte-identical |
| 6 | Byte-comparison diagnostic: review code-region diffs | Diffs understood and categorized |
| 7 | Add `V30_MAIN_HEX` path + `v30_main_hex` fixture | Fixture loads without error |
| 8 | **gpsim simulation suite with V3.0 hex** | **AC2 met (primary gate)** |
| 9 | Source cleanup: semantic labels, comments, includes | AC3 met |
| 10 | Wire-chain end-to-end with stock CONTROL | AC4 met |

Steps 3–5 are iterative: assemble, compare, fix, repeat.
Step 8 (gpsim) is the primary acceptance gate.

---

## File Locations

All new files follow the path policy in `CLAUDE.md` (implementation
under `src/dlcp_fw/`, thin entrypoints under `scripts/`):

| Deliverable | Path |
|-------------|------|
| Source file | `src/dlcp_fw/asm/dlcp_main_v30.asm` |
| RAM definitions | `src/dlcp_fw/asm/dlcp_main_ram.inc` |
| Macros (optional) | `src/dlcp_fw/asm/dlcp_main_macros.inc` |
| Region manifest | `src/dlcp_fw/asm/region_manifest.py` |
| Build script | `scripts/build_v30.sh` |
| Converter (impl) | `src/dlcp_fw/analysis/disasm_to_source.py` |
| Converter (entry) | `scripts/disasm_to_source.py` |
| Path constant | `src/dlcp_fw/paths.py` (add `V30_MAIN_HEX`) |
| Output hex | `firmware/patched/releases/DLCP_Firmware_V3.0.hex` |
| Equivalence test | `tests/sim/test_v30_equivalence.py` |
| Fixture update | `tests/sim/conftest.py` (add `v30_main_hex`) |
