# V1.7 CONTROL Source Rewrite — Polished Implementation

Codename: "V1.7" — the byte-identical source rebuild of stock V1.6b
(analog of MAIN V3.0).  The feature-bearing successor V1.71 is
specified separately in `docs/V16B_SOURCE_REWRITE_SPEC.md`.

Date: 2026-04-17
Status: draft
Parent spec: `docs/V16B_SOURCE_REWRITE_SPEC.md` (V1.71
  feature-bearing source rewrite)
Modeled on: `docs/IMPL_V30_SOURCE_REWRITE_SPECv2.md` (V3.0 MAIN
  polished implementation)

## Context

The CONTROL firmware has never had a source-level rewrite.  All
V1.4 / V1.5b / V1.6b artifacts are vendor-supplied `.hex` images;
all V1.61b–V1.64b feature work has been binary-patch overlays
produced by the Python builders under `src/dlcp_fw/patch/`.

This document is the CONTROL analog of
`docs/IMPL_V30_SOURCE_REWRITE_SPECv2.md`.  It defines the work
required to produce **V1.7** — a byte-identical source rebuild of
stock V1.6b — so that the feature-bearing V1.71 source specified
in `docs/V16B_SOURCE_REWRITE_SPEC.md` can be built on top of it
with full relocation safety.

Version nomenclature (mirrors MAIN):

| Label | Relationship | Corresponding MAIN version |
|-------|-------------|----------------------------|
| V1.6b | Stock vendor firmware (binary only) | V2.3 |
| V1.7  | Byte-identical source rebuild of V1.6b | V3.0 |
| V1.71 | Feature-bearing source rewrite (inlines V1.61b–V1.64b) | V3.1 |

Deliverable: `src/dlcp_fw/asm/dlcp_control_v17.asm`
(auto-labeled first pass) and
`src/dlcp_fw/asm/dlcp_control_v17_comments.asm` (canonical
commented source), both of which assemble with `gpasm` to a hex
image byte-identical to `firmware/stock/control/DLCP Control
Firmware V1.6b.hex` in the code, config, and EEPROM regions.

Three gaps must be closed before V1.71 can safely modify the
source:

1. **Relocation safety**: prove that the `.asm` is truly
   address-independent by shifting all code and verifying gpsim
   equivalence still holds.
2. **Source readability**: replace auto-generated labels with
   semantic names and add inline comments explaining every
   immediate value.
3. **Immediate value audit**: deep-inspect every
   `movlw`/`addlw`/etc. for hardcoded address references that
   would break on relocation.

---

## Part A: Relocation Safety Proof

### A1. Why this matters

V1.71 will modify function bodies in-place, causing all downstream
application code to shift by an unpredictable amount.  If ANY
immediate value in V1.7 encodes a hardcoded program address that
was not converted to a label, the shifted firmware will
malfunction silently — often in ways that only appear at the
chain-level (the wire cascade in V162B_RECONNECT_WAKE_BUG is a
cautionary example of how a 3-byte omission can mask itself for
months).

### A2. Immediate value audit

**Run this audit BEFORE Phase 1 step 1** (see Execution Order).
The audit produces `/tmp/v17_immediate_analysis.csv` which the
conversion script consumes to decide which literal operands need
label substitution.  It also anchors the TBLPTR site list
(A3) and the A2 categorization table below.

Extract every literal-form instruction (`movlw`, `addlw`, `sublw`,
`iorlw`, `xorlw`, `retlw`, `mullw`, `andlw`) from the V1.6b
disassembly code region (0x004C to end-of-application-code).
Classify each by category:

| Category | Relocation risk |
|----------|-----------------|
| ARITHMETIC | None |
| CMD_VALUE (serial protocol command byte) | None |
| RAM_ADDR (GPR / SFR address) | None (RAM is fixed hardware) |
| LOOP_COUNT | None |
| CONSTANT | None |
| BITMASK | None |
| DATA_TABLE_REF | **YES — must use labels** |
| REGISTER_VALUE | None |
| STRING_CHAR | None |
| RC5_CODE (IR button code) | None |
| EEPROM_ADDR | None (0xF00000 region is fixed) |
| UNKNOWN | must be driven to zero |

**Goal: zero UNKNOWN classifications.**  Any literal that does
not cleanly fit a category is a silent relocation risk.

Reuse the V3.0 audit pipeline (Python script backed by a CSV
dump) adapted for the K20 instruction set and CONTROL-specific
categories.  Store the audit results at
`/tmp/v17_immediate_analysis.csv` (not committed).

### A3. TBLPTR conversion verification

The CONTROL firmware reads character and string data via TBLPTR
for LCD strings and potentially RC5 and menu lookup tables.  All
TBLRD load sites must use `LOW(label)` / `HIGH(label)` /
`UPPER(label)` forms, not raw immediates.

Candidate regions (to audit and label during Phase 1):

- LCD string tables referenced by the menu and volume display
- Any RC5 scan-code translation table
- Menu screen dispatch table (if present)
- Serial command-response templates (if stored as ROM data)

Each data region referenced via TBLPTR must be given a named
label in the commented source and rewritten to use label
arithmetic at the load sites.

### A3b. Data-embedded address references (non-instruction
hazards)

The immediate audit in A2 covers instruction operands only.
There may also be pointer bytes embedded in data tables that
encode addresses consumed at runtime via TBLRD.  Known examples
in MAIN V3.0 were the USB string-descriptor pointer table; the
CONTROL equivalent (if any) would be a menu dispatch pointer
table.

**Fix pattern** (from V3.0): emit such pointer bytes using label
arithmetic, e.g.:
```asm
menu_screen_ptr_table:
    db  LOW(menu_screen_volume), LOW(menu_screen_input), ...
```
so pointer values track their targets through a shift.

**Page-boundary concern**: `addlw LOW(label)` patterns that add
an index to a table base can lose carry into TBLPTRH if the
indexed address crosses a 256-byte boundary.  Verify for the
chosen shift amount (Part A4) that no table crosses a page
boundary post-shift.  Any future shift re-verifies.

### A3c. Hardware-pinned addresses

The PIC18F25K20 exposes three fixed CPU vectors in the core
reset/interrupt layout.  Unlike MAIN (where the PIC18F2455 boot
block holds hardcoded `GOTO`s into the application at 0x1000,
0x1008, 0x1018), the K20 CPU itself performs the jumps:

| CPU vector | V1.6b stock target | Status |
|------------|--------------------|--------|
| 0x0000 | `goto 0x7800` (bootloader entry) | **LIVE** — reset vector |
| 0x0008 | `goto 0x03A6` (high-priority ISR) | **LIVE** — all interrupts land here (IPEN is cleared) |
| 0x0018 | `call 0x0190` (context save), then `movlw`/`movwf`/`bra $` | **LATENT** — low-priority ISR. Never reached while IPEN=0, but bytes populated |

In addition, V1.6b stock contains auxiliary branch targets at
0x0040 (`goto 0x0366`) and 0x0048 (`goto 0x03A6`).  Their call
source is not definitively identified in the current semantic
map; they are likely bootloader handoff entry points or a
soft-reset re-entry pattern.  **V1.7 preserves these bytes
verbatim.**  Their identification is an open audit item but not
a blocker for the rewrite.

**Vector-block layout (0x0000–0x004B)**:

V1.7 pins the entire vector block with a single `org 0x0000`
and emits bytes that reproduce the stock image exactly.  All
`goto` / `call` targets inside the block are written as symbolic
labels (`bootloader_entry`, `isr_dispatch`, `isr_save_context`,
`early_bootstrap_031`) that resolve to the correct shifted
addresses at link time.

**Latent hazard for IPEN**: if any future firmware version
enables IPEN, the low-priority vector at 0x0018 must contain
valid code.  V1.7 preserves stock bytes so this stays
consistent with V1.6b behavior.  For V1.71 (feature-bearing),
the spec keeps IPEN cleared — no change needed.

### A3d. Bootloader block (0x7800–0x7FFF)

The top 2 KB of flash holds the vendor bootloader.  It is
**not** rewritten by V1.7.  Implementation:

```asm
    org 0x7800
bootloader_image:
    db  0x??, 0x??, ...     ; byte-for-byte clone from stock V1.6b
    ...
```

Extract the bootloader bytes from the stock hex during Phase 1
and emit them via a `.inc` file or generated `db` block.  This
ensures that reset handoff (0x0000 → 0x7800), any bootloader
self-reference, and any USB/serial protocol embedded in the
bootloader remain bit-exact.

The bootloader CANNOT move — it is the reset-vector target and
rewriting it is explicitly out of scope.

### A4. Shift test methodology

**Goal**: insert 0x222 bytes (0x111 NOP words = 273 words) of
padding after the vector block at 0x004C, shifting ALL subsequent
application code by 0x222 bytes.  The bootloader uses `org
0x7800` so it stays pinned.  Run the full V1.7 gpsim test suite
against the shifted hex to prove behavioral equivalence.

**Why 0x222 specifically** (matches MAIN V3.0): a shift that is
not a multiple of 256 forces every `addlw LOW(label)` + index
pattern to cross a page boundary for at least some index values,
exercising carry into TBLPTRH.  A smaller shift (e.g. 0x100) can
silently leave a table below a 256-byte boundary after the shift
and miss the carry-safety bug entirely.

**Implementation**:

1. Copy `dlcp_control_v17_comments.asm` to
   `dlcp_control_v17_shifted.asm`.
2. Immediately after the 0x004B byte of the vector block, insert:
   ```asm
   ; Relocation safety padding — proves no hardcoded addresses remain
       fill    0x0000, 0x111   ; 0x111 NOP words = 0x222 bytes
   ```
3. All application-code labels shift by 0x222.  Vector-block
   `goto` / `call` targets resolve through labels and continue to
   land on the correct (shifted) code.
4. Convert any data-table pointer bytes to label-relative `db`
   values (see A3b).
5. Assemble with gpasm.  Verify no errors.
6. Resulting hex:
   - Vector block at 0x0000–0x004B (byte layout unchanged; `goto`
     / `call` encode different target addresses)
   - Application code at ~0x026E (shifted from ~0x004C)
   - Code end at (stock code end + 0x222)
   - Bootloader at 0x7800 (unchanged — pinned by `org 0x7800`)

**Why the bootloader cannot move**: PIC18F25K20 has 32 KB of
flash (0x0000–0x7FFF).  The bootloader occupies the top 2 KB
(0x7800–0x7FFF) and is the reset-vector target.  Moving it would
require rewriting vendor-provided update logic, which is out of
scope.

For V1.71 (feature-bearing) with an inline code growth of ~1 KB:

```
0x0000         Reset + ISR vectors (fixed)
0x004C         Application code start (fixed)
  ~end         Application code end (shifts as features added)
  ...fill...
0x7800–0x7FFF  Bootloader (pinned by org 0x7800)
```

Total available code space: 0x004C to 0x77FF ≈ 30.6 KB.  Stock
V1.6b uses less than this — exact number to be captured during
Phase 1 and recorded in the acceptance table.  V1.71 inline
enhancements add on the order of 1–1.5 KB, leaving headroom.

**ISR path validation**: The PIC18F25K20 CPU core sends all
interrupts to 0x0008 (with IPEN=0).  The V1.7 image places the
`goto isr_dispatch` at 0x0008 inside the fixed vector block,
BEFORE the shift padding.  At 0x0008 the stock ISR handoff
executes, and `goto isr_dispatch` resolves through a label to the
shifted dispatch body.  **ISR path is safe** — the entry block is
before the padding, and the goto target is label-resolved.

**gpsim overlay update for shifted hex**:

The gpsim simulation infrastructure has hardcoded CONTROL
addresses in MULTIPLE locations that must all be updated for the
shifted hex:

**1. Overlay function `org` addresses** (in `manifests.py` or a
CONTROL-specific equivalent).  After shift, every `org` targeting
a CONTROL function must use the new address.

| Symbol | Stock addr | Shifted addr | Used in |
|--------|-----------|-------------|---------|
| `lcd_command` | TBD from audit | TBD from `.lst` | LCD command capture |
| `lcd_write_char` | TBD | TBD | LCD char capture |
| `ir_rc5_decode` | TBD | TBD | IR frame injection |
| `uart_rx_parser` | TBD | TBD | RX parser stimulus |
| `uart_tx_enqueue` | TBD | TBD | TX byte capture |
| `eeprom_read_byte` | TBD | TBD | EEPROM read shim |
| `eeprom_write_byte` | TBD | TBD | EEPROM write shim |
| `main_event_loop` | TBD | TBD | Boot-gate fast-forward |

**2. Overlay precondition bytes**: any byte-value preconditions
that verify a function prologue (e.g. `0x0450: 0xA0`) must be
updated for shifted code.

**3. Hardcoded `goto` targets in overlay ASM**: become
label-relative, or regenerated from the shifted `.lst`.

**4. Breakpoint constants in test / harness code**: any
CONTROL-specific breakpoint addresses used by
`src/dlcp_fw/sim/control_gpsim.py` or test fixtures must switch
to symbol lookup.

**Approach**: write a `parse_v17_symbols(lst_path)` helper (or
generalize the existing `parse_gpasm_symbols` in
`src/dlcp_fw/sim/v30_symbols.py`) that returns a
`Dict[str, int]` of label → address.  Then build a
`control_overlays_dynamic(symbols)` manifest that templates
overlay ASM with the correct addresses.

### A5. Shift test validation

Run the V1.7 gpsim equivalence suite against the shifted hex.
Each must PASS:

| Test | Expected outcome |
|------|------------------|
| Boot reaches Volume screen | Same LCD capture as stock |
| IR RC5 decode latency | Same cycle window as stock |
| UART TX frame emission | Same TX bytes as stock |
| UART RX parser state | Same register state after known frames |
| EEPROM read/write round-trip | Same EEPROM bytes as stock |
| Full-sync burst | Same frame sequence as stock |
| Chain reaches display (V1.7 + V3.0 MAIN) | LCD reaches Volume screen |
| Chain blackout/wake WAITING (V1.7 + V3.0 MAIN) | WAITING state reached on wake |

**Note on cycle-count equivalence**: PIC18 instruction execution
timing is address-independent — `goto` and `call` are 2 cycles
regardless of target distance.  The only way cycle counts can
diverge is if a hardcoded address escaped the audit, so any
divergence is a real bug.

### A6. Implementation steps

1. Generate first-pass `dlcp_control_v17.asm` from the annotated
   V1.6b disassembly.  Replace `Common_RAM + N` references with
   named equates from a new
   `src/dlcp_fw/asm/dlcp_control_ram.inc`.  Replace raw SFR
   addresses with symbolic names (via `p18f25k20.inc`).
2. Verify first-pass assembly produces byte-identical output
   versus stock V1.6b (code + config + EEPROM).
3. Produce `dlcp_control_v17_comments.asm` (Part B): rename
   every `function_NNN` / `label_NNN` to semantic names, add
   function header blocks.  Assembly must still be byte-identical.
4. Create `dlcp_control_v17_shifted.asm` from `_comments.asm` +
   NOP padding.
5. Convert any data pointer tables to label-relative `db` values.
6. Assemble → shifted hex + `.lst` listing (verify no errors).
7. Write `parse_v17_symbols()` (or reuse the V3.0 helper).
8. Write `control_overlays_dynamic(symbols)` manifest builder.
9. Update CONTROL overlay preconditions, breakpoint constants,
   and `goto` targets in `manifests.py` / `control_gpsim.py`.
10. Write `tests/sim/test_v17_relocation.py`:
    - Shifted hex assembles without errors
    - Shifted hex vector block at 0x0000 byte-identical to stock
    - Shifted hex bootloader at 0x7800 byte-identical to stock
    - Shifted hex config bits match stock
    - Shifted hex EEPROM matches stock
    - Shifted hex code region is larger than stock by ~0x222
    - gpsim boot flow reaches Volume screen at same cycle count
    - gpsim command matrix matches stock TX bytes
    - gpsim chain (V1.7 + V3.0 MAIN) reaches display
    - gpsim chain blackout/wake WAITING
11. Run full suite.

---

## Part B: Source Readability Enhancement

### B0. Primary semantic reference: `firmware/disasm/control/v16b.asm`

The repo already contains a manually curated CONTROL V1.6b
reference at `firmware/disasm/control/v16b.asm` (17,309 lines).
Its header states explicitly:

> "COMMENT-ONLY edits. Never modify or relocate code; this
> file is a *reference* derived from the binary, not a source
> for assembly.  Re-running gpdasm on the original .hex must
> reproduce the body byte-for-byte."

This file is the **primary semantic source of truth** for the
V1.7 rewrite.  Beyond raw disassembly it already contains:

- Image layout map (reset/ISR vectors, bootloader entry,
  application body, device memory boundaries).
- Position in the V1.x release line (what V1.4 / V1.5b / V1.6b
  differ on, and how V1.61b–V1.64b extend V1.6b).
- Serial protocol tables (route bytes, cmd bytes, parser
  dispatch, both CONTROL→MAIN and MAIN→CONTROL directions).
- RAM layout with bit-level semantics for the flag registers
  (0x01F bits 0–6 in stock, bit assignments per version).
- Per-function commentary with bug tags (C1 no-timeout handshake,
  C3 IR-in-ISR, C6 TX ring overrun, etc.).
- Function-address index that names the serial frame builders,
  the parser, the IR decoder, the full-sync burst, and the
  display loop.

**Use `v16b.asm` as the sole primary reference.**  It supersedes
the older gpdasm artifacts in the same directory
(`v1.6b_disasm.asm` and `v1.6b_disasm.annotated.asm`): those files
are the raw auto-generated gpdasm output and the earlier
auto-annotated overlay.  They pre-date the curated semantic
labels and commentary now in `v16b.asm`.  The V1.7 rewrite does
not consume them.

For version-divergence context (what changed between V1.4 / V1.5b
/ V1.6b), the companion files `v14.asm` and `v15b.asm` in the
same directory offer comparable curated references.
`docs/analysis/SEMANTIC_FUNCTION_MAP.md` r3 remains a useful
cross-check on label confidence levels but is no longer the
primary source of function names.

### B0a. Gpdasm-reference → gpasm-source conversion

`v16b.asm` is a gpdasm reference, not a gpasm input.  Its
per-line format is `AAAAAA:  HHHH  mnemonic  operand ; comment`,
which mpasm/gpasm reject with `Error[1102] Parser error:
syntax error` (every instruction line fails).  Operands are raw
hex (e.g. `goto 0x007800`), not labels — the semantic names live
only in the trailing comments (e.g. `; -> bootloader_entry
(label_284)`).

V1.7 requires a NEW assembler-ready file
(`src/dlcp_fw/asm/dlcp_control_v17.asm`) produced by a conversion
pipeline that reads `v16b.asm` and emits gpasm-compatible source:

1. **Header**: add `LIST P=18F25K20`, `#include "p18f25k20.inc"`,
   and `#include "dlcp_control_ram.inc"`.
2. **Configuration bits**: emit `CONFIG` directives that match
   the stock config region at 0x300000–0x30000D.
3. **Segment directives**: add `org 0x0000` (vector block),
   `org 0x7800` (bootloader block, as a verbatim `db` dump),
   and `org 0xF00000` (EEPROM data), plus any required alignment.
4. **Per-line conversion**: strip the `AAAAAA:  HHHH  ` prefix,
   keep the mnemonic + operand.  Collapse continuation words of
   two-word instructions (e.g. the `f03c` after `ef00 goto`)
   into the single gpasm source line.
5. **Label emission**: for each branch / call / TBLPTR target
   address, emit a `label_name:` anchor at the target address and
   rewrite the operand to use that label.  Derive the label name
   from the `v16b.asm` trailing comment when available
   (`; -> bootloader_entry (label_284)` → `bootloader_entry`);
   fall back to `addr_XXXX` when no comment is present.
6. **RAM references**: rewrite `0x0NN, 0x0` access (Access Bank,
   GPR) into named equates defined in `dlcp_control_ram.inc`.
   Seed the equates from the RAM-layout section of `v16b.asm`.
7. **SFR references**: replace raw SFR addresses with symbolic
   names from `p18f25k20.inc`.
8. **Data tables**: re-emit `db`/`dw` tables with labeled
   anchors; convert any embedded address bytes to label
   arithmetic (`LOW(foo)` / `HIGH(foo)` / `UPPER(foo)` —
   see A3b).
9. **Preserve commentary**: port the rich inline prose from
   `v16b.asm` (header blocks, function banners, bug tags,
   version-context notes) into `dlcp_control_v17.asm` verbatim
   where feasible.  Comments do not affect assembled bytes.
10. **Byte-identity gate**: assemble with gpasm; `diff` the
    emitted hex against stock V1.6b in code, config, and
    EEPROM regions.  Iterate until zero diffs.

A conversion helper script (e.g.
`scripts/convert_v16b_asm_to_gpasm.py`) can automate most of
steps 1–8; steps 9–10 are validated by the Phase 1 equivalence
tests.

#### B0a.1 Edge cases the conversion script MUST handle

The steps above gloss over several non-obvious cases; an
implementer will hit all of them on day one.  Resolve up front:

1. **Two-word instruction continuations.**  PIC18 `goto`, `call`,
   `lfsr`, and `movff` are 2 words.  gpdasm prints each word on
   its own line:
   ```
   000000:  ef00  goto    label_274
   000002:  f03c
   ```
   The second row has a hex word but no mnemonic and no comment.
   Detection rule: any row whose instruction field is blank
   after stripping `AAAAAA:  HHHH  ` is a continuation — drop it
   entirely.  gpasm emits the second word itself from the
   preceding mnemonic.

2. **Code vs data demarcation.**  `dw 0xffff` emitted by gpdasm
   is ambiguous — it could be erased-flash fill OR a real data
   table containing a literal `0xFFFF`.  Rules:
   - Contiguous runs of `dw 0xffff` AFTER the last reachable
     instruction in a region are erased fill.  Do NOT emit them.
   - `dw 0xffff` BETWEEN two reachable labels must be preserved
     as a `dw` (it was intentional padding or alignment).
   - Anything reachable via TBLPTR (see Phase 1 step 8 below) is
     data; emit as a labeled `db`/`dw` block regardless of value.
   Use `v16b.asm`'s section banners (reset vector, ISR entry,
   function_XXX, data table) as the ground truth for region
   boundaries.

3. **Relative vs absolute branch targets.**  PIC18 branch ops
   come in two flavors:
   - Absolute: `goto addr`, `call addr, fast_bit` — target is a
     full 21-bit address.  Rewrite to `goto label`, `call label,
     0`.
   - Relative: `bra offset`, `rcall offset`, `btfsc/btfss + bra`.
     The gpdasm output shows a resolved destination
     (`bra label_003 ; dest: 0x000020`).  Rewrite to
     `bra label_003`; gpasm recomputes the offset.
   Self-loops (`bra $` = `bra .-2`) should be emitted as
   `bra label_here` with an explicit label on the same line, not
   as `bra $`.

4. **Config directive format.**  The stock bytes at
   0x300000–0x30000D are the 14 PIC18F25K20 config bytes.  Two
   valid emission formats:
   ```asm
   ; (a) Modern — one CONFIG per fuse byte
       CONFIG  FOSC = INTIO67
       CONFIG  WDTEN = OFF
       ...
   ; (b) Legacy — raw bytes at address
       org     0x300000
       db      0x24, 0x1F, ...
   ```
   Prefer (a) because it names the fuse bits semantically, but
   the extraction script from Phase 1 step 1 must map each
   stock byte to the equivalent named CONFIG value.  The
   PIC18F25K20 fuse map lives in `p18f25k20.inc`.  If any byte
   does not map cleanly to named fuses (bootloader-reserved
   bits, factory calibration, etc.), fall back to (b) for that
   specific byte and document why.

5. **`movff` operand layout.**  gpdasm prints
   `movff 0xFAE, 0x001` but gpasm requires symbolic SFR / BANKED
   forms where relevant.  Apply the SFR rename pass (step 7)
   before the output is emitted.

6. **Access-bank vs banked resolution.**  GPRs below 0x60 are
   in the Access Bank.  gpdasm prints them with `, A` (access);
   banked access prints `, 0x1`.  Keep the bank argument exact:
   the conversion must not rewrite an explicit `, 0x1` into `A`.

### B1. Label quality improvements

All 75 auto-labeled functions and 339 labels in V1.6b receive
semantic names in `dlcp_control_v17_comments.asm`.  The names
come from the function-address index already curated in
`v16b.asm` — that file is the authoritative source for every
rename, and no function requires fresh naming work.  The table
below is a high-signal sample, not an exhaustive list.  For the
remaining ~58 functions the conversion script copies the name
straight from `v16b.asm`.

- **Functions**: rename by responsibility.  Sample mappings
  (cross-checked against `v16b.asm` header and
  `SEMANTIC_FUNCTION_MAP.md` r3):
  - `function_000` → `app_init`
  - `function_009` → `isr_save_context`
  - `function_010` → `eeprom_read_byte`
  - `function_011` → `eeprom_write_byte`
  - `function_015` → `delay_loop`
  - `function_017` → `ir_rc5_decode`
  - `function_019` → `uart_rx_parser` (aka `rx_parser_entry`
    in `v16b.asm`)
  - `function_020` → `uart_tx_enqueue` (aka `tx_byte_enqueue`)
  - `function_026` → `eeprom_settings_load`
  - `function_027` → `serial_tx_routed_frame`
  - `function_028` → `serial_full_sync_burst`
  - `function_030` → `serial_send_input_frame`
  - `function_031` → `serial_send_volume_frame`
  - `function_032` → `serial_send_cmd1d_frame`
  - `function_033` → `serial_send_mute_frame`
  - `function_034` → `serial_send_standby_frame`
  - `function_035` → `serial_display_loop_iteration`
  - `function_042` → `main_event_loop`
  - (remaining functions inherit names from `v16b.asm` where
    confidence is high; `control_core_service_XXXX` for the
    residue)
- **Labels**: use `flow_<parent>_<purpose>` pattern, matching
  the naming convention already adopted in
  `dlcp_main_v30_comments.asm`.
- **Service groups**: for functions whose purpose is uncertain,
  use `control_core_service_XXXX` as a placeholder and mark the
  semantic-map / `v16b.asm` entry as `uncertain` until tracing
  resolves it.

All label renames MUST preserve byte-identical output.

### B2. Inline immediate value comments

Every `movlw` / `addlw` / `sublw` / `iorlw` / `xorlw` / `retlw` /
`mullw` / `andlw` instruction gets a comment explaining the
immediate value's meaning.  Reuse (or extend) the V3.0 script
`scripts/annotate_immediates.py` with a CONTROL-specific CSV.

Priority order (high-signal categories first):

1. DATA_TABLE_REF (already converted to labels — comment
   explains why).
2. RC5_CODE (IR button codes).
3. CMD_VALUE (serial protocol bytes).
4. REGISTER_VALUE (SFR writes — document the bit meaning).
5. ARITHMETIC / BITMASK (skip low-value constants).

### B3. Function-level comments

Every function gets a header block:

```asm
; ---------------------------------------------------------------------------
; Function: uart_rx_parser
; Address : 0x0450   (stock V1.6b — confirm from listing)
; Notes   : Three-byte frame parser (route / cmd / data).  Stock has bug
;           C3 (no OERR drain).  Fixed inline in V1.71.
; ---------------------------------------------------------------------------
uart_rx_parser:
```

Initial headers can be terse; parameter / side-effect / caller
info may be added incrementally for critical functions.

---

## Part C: Tooling Enhancement

### C1. Shift test uses commented source

The shift test (Part A) uses `dlcp_control_v17_comments.asm`
(not the raw first-pass output) so it validates both:

- label renames assemble cleanly, and
- relocation safety holds on the canonical source.

### C2. Annotation script

Extend `scripts/annotate_immediates.py` (originally written for
V3.0) to understand:

- PIC18F25K20 SFR names (via `p18f25k20.inc`).
- CONTROL-specific categories (RC5_CODE, CMD_VALUE subsets for
  the CONTROL-side protocol).

### C3. Tests

```python
def test_v17_asm_assembles_identical():
    """First-pass .asm must produce byte-identical hex versus stock."""
    # code, config, EEPROM all match stock V1.6b

def test_v17_comments_assembles_identical():
    """Commented .asm must also produce byte-identical hex."""

def test_v17_comments_no_auto_labels():
    """No function_NNN or label_NNN remain."""
    text = Path("src/dlcp_fw/asm/dlcp_control_v17_comments.asm").read_text()
    assert "function_0" not in text
    assert "label_0" not in text

def test_v17_comments_all_functions_documented():
    """Every function has a header comment."""
    text = Path("src/dlcp_fw/asm/dlcp_control_v17_comments.asm").read_text()
    assert text.count("; Function:") >= 70

def test_v17_bootloader_preserved():
    """0x7800–0x7FFF byte-identical to stock."""
```

---

## Execution Order

### Phase 0: Pre-conversion audit (prerequisite)

1. Run the immediate-value audit (per A2) over the V1.6b code
   region.  Produce `/tmp/v17_immediate_analysis.csv`.  Fill the
   A2 category counts and the A3 TBLPTR site table into the
   spec with real numbers (replacing the "TBD" rows).
2. Measure the stock V1.6b code-end address.  Grep the last
   non-`0xffff` byte in `firmware/disasm/control/v1.6b_disasm.asm`
   below 0x7800.  Stock V1.6b application code ends at `0x1A0B`
   (first non-0xFF byte walking backward from 0x7000).  Headroom
   below the 0x7800 bootloader is `0x7800 − 0x1A0C = 0x5DF4 bytes`
   (~24 KB).  After the `0x222`-byte shift, the shifted
   application code ends at `0x1C2D`, leaving `0x5BD2 bytes`
   (~23 KB) before the bootloader.  V1.71's ~1–1.5 KB inline
   feature growth fits comfortably.

### Phase 1: Baseline source (proves byte-identical rebuild)

1. Write `scripts/extract_v16b_static_regions.py`.  It parses
   `firmware/stock/control/DLCP Control Firmware V1.6b.hex` and
   emits three generated artifacts:
   - `src/dlcp_fw/asm/dlcp_control_bootloader.inc` — verbatim
     `db` block for the 0x7800–0x7FFF bootloader region.
   - A `CONFIG` stanza for the 14 bytes at 0x300000–0x30000D,
     written either inline in `dlcp_control_v17.asm` or to a
     sibling `dlcp_control_config.inc`.
   - An `org 0xF00000` EEPROM `db` block with all 256 bytes.
2. Define RAM equates in `src/dlcp_fw/asm/dlcp_control_ram.inc`
   (analogous to `dlcp_main_ram.inc`), seeded from the RAM
   layout block in `v16b.asm` (lines 66–102).  The authoritative
   list is:

   | Addr | Equate | Notes |
   |------|--------|-------|
   | 0x01D | `ir_decoded_cmd` | RC5 cmd byte (from `ir_rc5_decode`) |
   | 0x01E | `ir_decoded_addr` | RC5 addr byte |
   | 0x01F | `control_flags` | bit layout — see V1.71 spec table |
   | 0x027 | `tx_data_staging` | byte to enqueue via `uart_tx_enqueue` |
   | 0x02F | `rx_parsed_cmd` | latched by parser |
   | 0x030 | `rx_parsed_data` | latched by parser |
   | 0x036–0x065 | `tx_ring_base` | 48-byte TX ring (ISR consumer) |
   | 0x066–0x095 | `rx_ring_base` | 48-byte RX ring (ISR producer) |
   | 0x096 | `tx_ring_rd` | ISR consumer index |
   | 0x097 | `tx_ring_wr` | producer index |
   | 0x098 | `rx_ring_rd` | parser consumer index |
   | 0x099 | `rx_ring_wr` | ISR producer index |
   | 0x09D / 0x09E | `idle_timeout_lo` / `idle_timeout_hi` | 16-bit, init 0xEA61 |
   | 0x09F / 0x0A0 | `full_sync_lo` / `full_sync_hi` | 16-bit, init 0x4E20 (~20k → fullsync) |
   | 0x0A1 | `raw_status_cache` | boot sentinel #4, init 0x80 until BF/05 |
   | 0x0A6 | `rx_frame_position` | parser state: 0 = route, 1 = cmd, 2 = data |
   | 0x0A7 | `cmd1d_setting_cache` | boot sentinel #3, init 0x80 until BF/1D |
   | 0x0B7 | `rx_ring_staging` | single-byte holding cell for parser |
   | 0x0B8 | `input_select_cache` | boot sentinel #1, init 0x80 until BF/06 |
   | 0x0B9 | `volume_cache` | boot sentinel #2, init 0x80 until BF/07 |
   | 0x0BB | `button_debounce_counter` | threshold = 4 |
   | 0x0BC | `button_last_scan` | |
   | 0x0BE | `button_debounced` | |
   | 0x0BF | `display_state_index` | menu screen 0..3 (Vol/Preset/Input/Setup) |
   | 0x0C1–0x0CC | `saved_settings_base` | loaded by `eeprom_settings_load` from EEPROM |

   For V1.71, three additional equates are needed (added to
   `dlcp_control_ram.inc` as part of the V1.71 edits, not V1.7):
   `bf08_fault_byte` at a free GPR slot (V1.63b used 0x0BC —
   collides with `button_last_scan` in V1.6b; verify the
   V1.63b patch actually wrote elsewhere or relocate for V1.71),
   and the flag bits `RECONNECT_PENDING` / `RECONNECT_PRIMED` /
   `RECONNECT_WAIT_DONE` / `DSP_FAULT_BIT` in `control_flags`.
3. Write `scripts/convert_v16b_asm_to_gpasm.py` (per B0a) to
   mechanically convert the curated gpdasm reference into a
   gpasm-ready source.  Input: `firmware/disasm/control/v16b.asm`.
   Output: `src/dlcp_fw/asm/dlcp_control_v17.asm`.  The script
   consumes the extracted static-region artifacts from step 1.
4. Produce `dlcp_control_v17.asm` via the conversion script.
   Port `v16b.asm`'s inline prose into the generated file where
   helpful.
5. Trace the call graph for the aux vectors at 0x0040 and
   0x0048.  Record in a comment block whether they are reachable
   at runtime, and document the handoff path (stock behavior
   suggests bootloader → cold-init at 0x0366 for 0x0040, and
   a duplicate of the high-priority ISR entry at 0x03A6 for
   0x0048).  Confirm byte preservation rationale or flag as an
   open question for V1.71.
6. Assemble with gpasm.  Verify code, config, and EEPROM regions
   are byte-identical to stock V1.6b.  Iterate until zero diffs.
7. Add `tests/sim/test_v17_equivalence.py` (hex integrity tests
   + gpsim behavioral equivalence with stock).

### Phase 2: Source readability (produces canonical `_comments.asm`)

1. Produce `dlcp_control_v17_comments.asm` by extending the
   Phase-1 conversion pass: rename every `function_NNN` /
   `label_NNN` / `addr_XXXX` using the names curated in
   `v16b.asm` (see B1).  Add function header blocks (B3).
   The conversion can run in a single pass that emits the
   commented source directly — there is no reason to commit a
   raw `dlcp_control_v17.asm` separately once the commented
   source assembles byte-identical.
2. Assemble `_comments.asm`; confirm byte-identical output.
3. Extend `scripts/annotate_immediates.py` for CONTROL (B2 / C2).
4. Run the annotator against `_comments.asm`; verify the
   annotated output still assembles byte-identical.
5. Priority order for inline comments: DATA_TABLE_REF →
   RC5_CODE → CMD_VALUE → REGISTER_VALUE.
6. Run annotation-quality tests (C3).

### Phase 3: Relocation safety proof

1. Create `dlcp_control_v17_shifted.asm` from
   `dlcp_control_v17_comments.asm` + NOP padding (Part A4).
2. Convert any pointer-table data to label-relative `db` values
   (A3b).
3. Assemble → shifted hex + `.lst` listing (verify no errors).
4. Write `parse_v17_symbols()` to extract symbol addresses from
   the `.lst`.
5. Write `control_overlays_dynamic(symbols)` manifest builder.
6. Update CONTROL overlay preconditions, breakpoint constants,
   and `goto` targets in `src/dlcp_fw/sim/manifests.py` and
   `src/dlcp_fw/sim/control_gpsim.py`.
7. Bootloader stays at 0x7800 (pinned by `org`) — no change.
8. Write `tests/sim/test_v17_relocation.py` (structural +
   gpsim tests per A5).
9. Run full suite → all pass → relocation safety proven.

### Phase 4: V1.71 readiness gate

After Phases 1–3 pass:
- Byte-identical V1.7 baseline proven (Phase 1 tests green).
- Canonical source (`_comments.asm`) fully labeled and
  annotated (Phase 2).
- Relocation safety proven (Phase 3 shift test green).
- All instruction-level TBLPTR references use labels.
- Data-embedded pointer bytes use label arithmetic.
- Zero hardcoded code addresses (verified by immediate audit +
  shift test).
- gpsim CONTROL manifests refactored to use symbol lookup (not
  hardcoded addresses).
- `addlw LOW(label)` carry safety verified for shifted
  addresses.
- Aux vector 0x0040 / 0x0048 rationale documented; preserved
  verbatim.
- V1.71 can freely modify function bodies knowing addresses
  shift safely.

---

## Artifacts

| File | Purpose |
|------|---------|
| `firmware/disasm/control/v16b.asm` | **Primary semantic reference** (pre-existing).  Curated commentary on image layout, serial protocol, RAM bit semantics, per-function purpose, bug tags.  Not assembler input.  Supersedes the older `v1.6b_disasm.asm` and `v1.6b_disasm.annotated.asm` artifacts, which are not used by the rewrite. |
| `scripts/extract_v16b_static_regions.py` | Parses stock V1.6b hex.  Emits the bootloader `.inc`, `CONFIG` stanza, and EEPROM `db` block consumed by the conversion pipeline. |
| `scripts/convert_v16b_asm_to_gpasm.py` | Mechanical conversion from the curated gpdasm reference to a gpasm-ready source (per B0a).  Reads `v16b.asm` + the extracted static-region artifacts, writes `dlcp_control_v17.asm` (or directly `_comments.asm`). |
| `src/dlcp_fw/asm/dlcp_control_v17.asm` | Phase 1 raw output (auto-generated labels, byte-identical to stock V1.6b).  Optional: may be collapsed into `_comments.asm` directly if the conversion pass can emit the commented source in one step. |
| `src/dlcp_fw/asm/dlcp_control_v17_comments.asm` | **Canonical V1.7 source** — fully annotated, zero auto-labels, every function headered.  Assembles byte-identical to stock. |
| `src/dlcp_fw/asm/dlcp_control_v17_shifted.asm` | Shift test source (generated from `_comments.asm` + NOP padding). |
| `src/dlcp_fw/asm/dlcp_control_ram.inc` | RAM equates shared by V1.7 and V1.71.  Seeded from the RAM layout section of `v16b.asm`. |
| `src/dlcp_fw/asm/dlcp_control_bootloader.inc` (or similar) | Byte-for-byte bootloader image (0x7800–0x7FFF). |
| `tests/sim/test_v17_equivalence.py` | Hex integrity + source quality tests. |
| `tests/sim/test_v17_relocation.py` | Shift test suite. |
| `/tmp/v17_immediate_analysis.csv` | Full immediate value audit (reference artifact, not committed). |
| `scripts/annotate_immediates.py` | Adds inline comments from CSV audit (extended for CONTROL). |
| `src/dlcp_fw/sim/v30_symbols.py` (extended) or new sibling | `parse_v17_symbols()` + `control_overlays_dynamic()`. |

Add path constants to `src/dlcp_fw/paths.py`:

- `V17_CONTROL_ASM`
- `V17_CONTROL_ASM_COMMENTS`
- `V17_CONTROL_HEX` (alias for the rebuilt byte-identical output
  if committed; otherwise the test fixture generates it on the
  fly)

These mirror the `V30_MAIN_ASM*` / `V30_MAIN_HEX` constants used
for MAIN.

---

## Constraints

- Shift test hex must NOT be committed to
  `firmware/patched/releases/` (it is a test artifact, not a
  release).
- `dlcp_control_v17_comments.asm` must always assemble to
  byte-identical output versus stock V1.6b across code, config,
  and EEPROM regions.
- Bootloader region (0x7800–0x7FFF) must be byte-identical to
  stock — it is a verbatim `db` block.
- All data tables referenced by TBLRD must use label arithmetic.
- Comments and label changes must never affect assembled bytes.
- The codex-cli / script CSV is a reference artifact, not
  committed.
- `dlcp_control_v17_comments.asm` is the starting point for
  V1.71 edits; V1.71 inherits its label scheme and header
  conventions.
- This spec does NOT rewrite the bootloader.  Any future
  bootloader work is a separate project.
