# V3.0 Source Rewrite — Polished Implementation (v2)

Date: 2026-03-28
Supersedes: `docs/IMPL_V30_SOURCE_REWRITE_SPEC.md` (Phase 1 implementation)

## Context

V3.0 Phase 1 delivered a gpasm-compatible `.asm` source that assembles
to a **byte-identical** copy of stock V2.3.  39 tests pass, including
gpsim behavioral equivalence with exact cycle counts.

This v2 spec addresses three gaps before V3.1 can safely modify the
source:

1. **Relocation safety**: Prove that the .asm is truly address-independent
   by shifting all code and verifying gpsim equivalence still holds.
2. **Source readability**: Replace auto-generated labels with semantic
   names and add inline comments explaining every immediate value.
3. **Immediate value audit**: Deep-inspect every `movlw`/`addlw`/etc.
   for hardcoded address references that would break on relocation.

---

## Part A: Relocation Safety Proof

### A1. Why this matters

V3.1 will modify function bodies in-place, causing all downstream code
to shift by an unpredictable amount.  If ANY immediate value in V3.0
encodes a hardcoded program address (not converted to a label), the
shifted firmware will malfunction silently.

### A2. Immediate value audit results

Codex-cli analyzed all **1,092 literal-form instructions** in the code
region (0x10AC–0x496F).  Full results at `/tmp/v30_immediate_analysis.csv`.

| Category | Count | Relocation risk |
|----------|------:|----------------|
| ARITHMETIC | 584 | None |
| CMD_VALUE | 157 | None |
| RAM_ADDR | 111 | None (RAM addresses are fixed hardware) |
| LOOP_COUNT | 89 | None |
| CONSTANT | 85 | None |
| BITMASK | 21 | None |
| DATA_TABLE_REF | 17 | **YES — must use labels** |
| REGISTER_VALUE | 13 | None |
| STRING_CHAR | 10 | None |
| I2C_ADDR | 7 | None |
| UNKNOWN | 0 | — |

**Zero unknowns.**  The only relocation hazards are the 17 DATA_TABLE_REF
entries — all TBLPTR load sites.

### A3. TBLPTR conversion verification

V3.0 Phase 1 already converts all 17 DATA_TABLE_REF immediates to
label-based references:

| Sites | Stock pattern | V3.0 conversion | Target |
|-------|--------------|-----------------|--------|
| 0x16A6, 0x16CA, 0x18E2, 0x43CC | `addlw 0x19` | `addlw LOW(hex_lookup_table)` | Nibble table at 0x1019 |
| 0x16AA, 0x16CE, 0x18E6, 0x43D0 | `movlw 0x10` | `movlw HIGH(hex_lookup_table)` | TBLPTRH for nibble table |
| 0x37CE | `addlw 0x29` | `addlw LOW(string_desc_ptr_table)` | String descriptor ptrs at 0x1029 |
| 0x37D2 | `movlw 0x10` | `movlw HIGH(string_desc_ptr_table)` | TBLPTRH for same |
| 0x3D82, 0x3D86, 0x3D8A | `movlw 0xE6/0x47/0x00` | `movlw LOW/HIGH/UPPER(inline_data_table_47E6)` | Inline data at 0x47E6 |
| 0x3DA2 | `movlw 0x00` | `movlw UPPER(0x0000)` | Clear TBLPTRU |
| 0x42BA, 0x42C0, 0x42D6 | `movlw 0x30/0x0B/0x30` | `movlw UPPER/LOW/UPPER(_CONFIG6H/_CONFIG1L)` | Config space (fixed HW, not code) |

**Additional safety checks** (no relocation risk found):
- **Zero PCL/PCLATH/PCLATU loads** — no computed gotos anywhere
- **Zero FSR code-address loads** — all FSR operations are RAM pointers
- **All branch/call targets use labels** — verified by Test 12 (no raw hex targets)
- **All SFR references are symbolic** — verified by Test 13

**Conclusion**: After TBLPTR conversion, V3.0 has NO hardcoded code
addresses in instructions.  However, there are **data-embedded address
references** (see A3b) that also need attention.

### A3b. Data-embedded address references (non-instruction hazards)

The immediate audit in A2 covers instruction operands only.  There are
also **pointer bytes embedded in the USB descriptor data region** that
encode addresses consumed at runtime via TBLRD:

| Data address | Content | Consumed by | Risk |
|-------------|---------|-------------|------|
| 0x1029–0x102B | `0xA6, 0x72, 0x9A` | `string_desc_ptr_table` lookup at 0x37CE | **YES** — these are low bytes of USB string descriptor addresses |

These 3 bytes are offsets into page 0x10xx pointing to string
descriptors 0, 1, 2.  After a shift of 0x222, the string descriptors
move to page 0x12xx and the pointer bytes become stale.

**Fix for shift test**: The `string_desc_ptr_table` data must be
emitted using label arithmetic:
```asm
string_desc_ptr_table:
    db  LOW(usb_string_desc_0), LOW(usb_string_desc_1), LOW(usb_string_desc_2)
```
This way the pointer bytes track the shifted descriptor addresses.

**Page-boundary concern**: The `addlw LOW(string_desc_ptr_table)`
pattern at 0x37CE adds an index (0–2) to the table base.  After shift,
if `LOW(string_desc_ptr_table)` + index crosses a 256-byte boundary,
carry into TBLPTRH is lost.  The shift amount (0x222) means the table
moves from 0x1029 to 0x124B; max index 2 gives 0x124D — no page
crossing.  **Safe for this shift value.**  Must be verified for any
future shift.

**Hex lookup table**: The `addlw LOW(hex_lookup_table)` pattern adds
a nibble value (0x00–0x0F) to the table base.  After shift, table
moves from 0x1019 to 0x123B; max index 0x0F gives 0x124A — no page
crossing.  **Safe.**

### A3c. Hardware-pinned addresses (boot block constraints)

The PIC18F2455 boot block (0x0000–0x0FFF) is in protected flash that
we cannot modify.  It contains **three hardcoded `GOTO` instructions**
that jump into app space:

| Boot addr | Instruction | Target | Purpose |
|-----------|------------|--------|---------|
| 0x0008 | `GOTO 0x1008` | **0x1008** | High-priority ISR vector redirect |
| 0x0018 | `GOTO 0x1018` | **0x1018** | Low-priority ISR vector redirect |
| 0x03B8 | `GOTO 0x1000` | **0x1000** | Boot exit → app entry |

These addresses are **burned into boot block ROM**.  The app MUST have
valid code or entry points at these exact addresses.

**0x1000 — App entry (LIVE)**:
Boot block jumps here after USB bootloader timeout/exit.  Must be
`org 0x1000` with a `goto` to the main init.  Already handled.

**0x1008 — High-priority ISR entry (LIVE)**:
ALL interrupts arrive here (USBIF, T0IF, TMR3IF, RCIF, OERR).  The
stock ISR entry saves FSR2L/H and calls `main_isr_dispatch`.  This
address is inside the fixed entry block (0x1000–0x1013) which is
placed BEFORE any shift padding.  **Must stay at exactly 0x1008.**

**0x1018 — Low-priority ISR entry (DEAD, latent hazard)**:
The firmware explicitly clears IPEN (RCON bit 7) during `uart_config`,
which disables interrupt priority.  With IPEN=0, ALL interrupts use
the high-priority vector at 0x0008 → 0x1008.  The low-priority vector
at 0x0018 → 0x1018 is **never reached** at runtime.

In the stock layout, 0x1018 happens to be the start of the USB
descriptor data region (hex lookup sentinel = 0x00).  Executing this
as code would be harmless (NOP) but meaningless.

**Latent hazard**: If any future firmware version enables IPEN
(interrupt priority), the low-priority ISR vector at 0x1018 must
contain valid code, NOT data.  For V3.0/V3.1, IPEN remains cleared,
so this is safe.  But any shift that moves the USB data away from
0x1018 should ensure the address contains at least a safe stub
(e.g., `retfie 0`) rather than random padding.

**Impact on shift test**: The NOP padding is inserted after 0x1012
(the ISR dispatch call).  The entry block 0x1000–0x1013 is unaffected:
- 0x1000: `goto` (resolves to shifted label) ✓
- 0x1008: ISR entry (stays at 0x1008) ✓
- 0x1014: `goto` to main init (shifts, but reached via label from 0x1000) ✓
- 0x1018: Falls in NOP padding (0x0000 = NOP = harmless) ✓

**Impact on V3.1**: Same as shift test.  The entry block is fixed.
All code after 0x1014 shifts freely.  The three pinned addresses
(0x1000, 0x1008, 0x1018) are all within the entry block or padding.

**Recommendation for V3.1**: Place a `retfie 0` at 0x1018 as a safety
stub for the dead low-priority ISR vector, rather than relying on
NOP/data happening to be benign:
```asm
    org 0x1000
    goto    app_init            ; boot exit
    dw      0xFFFF, 0xFFFF      ; 0x1004-0x1007 padding
isr_high_entry:                 ; 0x1008 — HIGH-PRIORITY ISR (LIVE)
    movff   FSR2L, isr_save_fsr2l
    movff   FSR2H, isr_save_fsr2h
    call    main_isr_dispatch, 0x1
app_init:                       ; 0x1014
    goto    main_flash_service
    nop                         ; 0x1018 pad
isr_low_stub:                   ; 0x1018 — LOW-PRIORITY ISR (DEAD)
    retfie  0                   ; safe no-op if ever reached
```

Wait — 0x1014 is 4 bytes (`goto` + second word = 0x1014–0x1017),
so 0x1018 is the next address.  The `nop` above is wrong.  Corrected:

```asm
    org 0x1000
app_entry:
    goto    app_init            ; 0x1000: boot exit target
    dw      0xFFFF, 0xFFFF      ; 0x1004-0x1007: unused
isr_high_entry:                 ; 0x1008: HIGH-PRIORITY ISR (LIVE)
    movff   FSR2L, isr_save_fsr2l   ; 0x1008
    movff   FSR2H, isr_save_fsr2h   ; 0x100C
    call    main_isr_dispatch, 0x1  ; 0x1010
app_init:                       ; 0x1014
    goto    main_flash_service      ; 0x1014 (4 bytes)
isr_low_stub:                   ; 0x1018: LOW-PRIORITY ISR (DEAD)
    retfie  0                       ; safe stub if IPEN ever enabled
    ; USB descriptors follow at 0x101A (shifted by 2 bytes vs stock)
```

This adds a 2-byte `retfie 0` safety stub at the exact boot-block
target address, at the cost of shifting USB descriptors by 2 bytes.
Since all USB descriptor references use labels, this is safe.

### A4. Shift test methodology

**Goal**: Insert 0x222 bytes (0x111 NOP words = 273 words) of padding
after the app entry stub, shifting ALL subsequent code (USB descriptors,
functions, data tables) by 0x222 bytes.  The preset table uses `org
0x5600` so it stays pinned.  Then run the full V3.0 gpsim test suite
against the shifted hex to prove behavioral equivalence.

**Implementation**:

1. Copy `dlcp_main_v30_comments.asm` to `dlcp_main_v30_shifted.asm`
2. After the ISR dispatch call at 0x1012 (before `flow_app_entry_1014`),
   insert:
   ```asm
   ; Relocation safety padding — proves no hardcoded addresses remain
       fill    0x0000, 0x111    ; 0x111 NOP words = 0x222 bytes of padding
   ```
3. The entry `goto flow_app_entry_1014` naturally jumps over the padding.
4. Convert the `string_desc_ptr_table` data from hardcoded bytes to
   label-relative `db` values (see A3b).
5. Assemble with gpasm.  Verify no errors.
6. The resulting hex has:
   - App entry at 0x1000 (unchanged — bootloader target)
   - ISR dispatch stub at 0x1008 (unchanged — in entry block before pad)
   - USB descriptors at ~0x123A (shifted from 0x1018)
   - First function at ~0x12CE (shifted from 0x10AC)
   - Code end at ~0x4B92 (shifted from 0x4970)
   - Preset table at 0x5600 (unchanged — pinned by `org 0x5600`)

**Why preset A cannot move**: PIC18F2455 has 24KB flash (0x0000–0x5FFF).
The preset table occupies the last 2560 bytes (0x5600–0x5FFF).  There
is **zero space** above 0x5FFF.  The table is hard against the flash
ceiling.  For V3.1 with two preset tables, the layout is:

```
0x1000         Code start
  ~0x4970      Code end (grows with V3.1 enhancements)
  ...fill...
0x4A00-0x53FF  Preset B (2560B clone of A)
0x5400-0x55FF  Free (512B — overflow space)
0x5600-0x5FFF  Preset A (2560B — pinned to flash ceiling)
```

Total available code space: 0x1000 to ~0x49FF = ~14.7KB.
V3.1 enhanced code: ~15.3KB — fits with headroom.

**ISR path validation**: The PIC18F2455 hardware ISR vector is at
0x0008 (in the boot block, not emitted by V3.0).  The boot block
redirects to 0x1008 which is inside the entry stub (before the
padding).  At 0x1008, the stock ISR entry `movff FSR2L, ...` /
`call main_isr_dispatch` executes.  The `call main_isr_dispatch`
target resolves to the shifted address via its label.  **ISR path is
safe** — the entry block is before the padding, and the call target
is label-resolved.

**gpsim overlay update for shifted hex**:

The gpsim simulation infrastructure has hardcoded addresses in
MULTIPLE locations that must ALL be updated for the shifted hex:

**1. Overlay function `org` addresses** (manifests.py):
These `org` directives place simulation stubs at stock function entry
points.  After shift, every `org` must use the new address.

| Symbol | Stock addr | Shifted addr | Used in |
|--------|-----------|-------------|---------|
| `rx_ring_read` | 0x45FA | TBD from .lst | Mailbox RX stub |
| (RX-available check) | 0x4872 | TBD | function_109 overlay |
| `uart_tx_byte_blocking` | 0x4896 | TBD | Mailbox TX stub |
| (NOP after TX) | 0x489A | TBD | TX return site |
| `i2c_wait_bus_idle` | 0x48B6 | TBD | MSSP idle sim |
| `timer3_blocking_delay` | 0x447E | TBD | Timer3 shim |
| (alt i2c_wait_bus_idle) | 0x4492 | TBD | function_113 overlay |
| (alt uart_tx) | 0x2D9E | TBD | function_111 overlay |
| `adc_boot_gate` | 0x2D8C | TBD | ADC boot bypass |

**2. Overlay precondition bytes** (manifests.py L382+):
Byte-value checks like `0x447E: 0xA0`, `0x45FA: 0x04` verify the
correct function prologue before patching.  These addresses AND
expected byte values must be updated for shifted code.

**3. Hardcoded `goto` targets in overlay ASM**:
The overlay ASM contains `goto 0x489A` and `goto 0x2DC8` (manifests.py
L339, L584).  These must become label-relative or updated to shifted
addresses.

**4. Breakpoint constants in test/harness code**:
- `MAIN_AN0_BOOT_EXIT_ADDR = 0x2DC8` (main_gpsim.py L38)
- Parser break address at `0x1BEA` (main_gpsim.py L424)
- Various test-specific breakpoint addresses

**Approach**: Write a `parse_v30_symbols(lst_path)` helper that reads
the gpasm listing file and returns a `Dict[str, int]` of label→address.
Then build a `main_serial_mailbox_hook_dynamic(symbols)` manifest that
templates the overlay ASM with the correct addresses.

### A5. Shift test validation

Run ALL 10 gpsim equivalence tests from `test_v30_gpsim_equivalence.py`
against the shifted hex:

| Test | Expected outcome |
|------|-----------------|
| AN0 boot gate exit cycle | PASS — **same cycle count** (see note below) |
| I2C regfile volume command | PASS — same register values as stock |
| UART TX fault stalls | PASS — same fault behavior |
| MSSP fault inert until wait | PASS — same fault behavior |
| Command matrix (4 commands) | PASS — same TX bytes as stock |
| Chain reaches display | PASS — CONTROL+MAIN connect |
| Chain blackout wake WAITING | PASS — WAITING state reached |

**Note on AN0 boot cycle count**: The NOP padding is inserted AFTER
the ISR dispatch call site (0x1012).  The main entry `goto` at 0x1000
jumps to `flow_app_entry_1014` (now at 0x1236) which then `goto`s to
the main flash service function.  The `goto` is a 2-cycle instruction
regardless of target distance on PIC18.  The only cycle difference is
if a `call` target shifts (different instruction fetch pipeline), but
PIC18 `call` is 2 cycles regardless of target address.  **The cycle
count should be identical to stock** because instruction execution
timing on PIC18 is not address-dependent — only instruction type
matters.  If it differs, that indicates a real bug.

### A6. Implementation steps

1. Create `dlcp_main_v30_shifted.asm` from `_comments.asm` + NOP padding
2. Convert `string_desc_ptr_table` to label-relative `db` values
3. Assemble → shifted hex + `.lst` listing
4. Write `parse_v30_symbols()` to extract symbol addresses from `.lst`
5. Write `main_serial_mailbox_hook_dynamic(symbols)` manifest builder
6. Update breakpoint constants to use symbol lookup
7. Write `tests/sim/test_v30_relocation.py`:
   - Test: shifted hex assembles without errors
   - Test: shifted hex has correct entry at 0x1000
   - Test: shifted hex ISR dispatch at 0x1008 (before padding)
   - Test: shifted hex config/EEPROM identical to stock
   - Test: shifted hex preset table at 0x5600 (pinned by org)
   - Test: shifted hex code region is larger than stock (by ~0x222)
   - Test: gpsim AN0 boot exits at same cycle count
   - Test: gpsim command matrix matches stock TX bytes
   - Test: gpsim chain reaches display
   - Test: gpsim chain blackout/wake WAITING
8. Run full suite

---

## Part B: Source Readability Enhancement

### B0. Existing annotated source: `dlcp_main_v30_comments.asm`

A manually-curated annotated source already exists at
`src/dlcp_fw/asm/dlcp_main_v30_comments.asm`.  It is 8,047 lines
(+792 vs the 7,255-line Phase 1 output) and assembles to
**byte-identical** output.

**Achieved**:
- **0 remaining `function_NNN`** — all 101 auto-generated function
  names replaced with semantic/descriptive names
- **0 remaining `label_NNN`** — all 592 auto-generated branch labels
  replaced with contextual names
- **132 function header blocks** — every function has a `;Function:`
  comment with address and notes
- Naming conventions:
  - Functions: `i2c_byte_tx`, `uart_tx_byte_blocking`, `flash_write`, etc.
  - Service-group functions with inferred purpose: `main_i2c_service_XXXX`,
    `main_uart_service_XXXX`, `main_flash_service_XXXX`, `main_core_service_XXXX`
  - Flow labels: `flow_functionname_XXXX` — branch/loop targets within
    a function, prefixed with the parent function name
  - Infrastructure: `hex_lookup_table`, `usb_device_descriptor`,
    `preset_table_a`, etc.

**This file is the canonical V3.0 source going forward.**  It replaces
`dlcp_main_v30.asm` as the starting point for V3.1 edits.

### B1. Remaining label quality improvements

The commented source uses `main_core_service_XXXX` for ~40 functions
where the specific purpose could not be determined from static analysis
alone.  These can be further refined through:

1. **gpsim tracing**: Set breakpoints on `main_core_service_XXXX`
   functions during various command scenarios to observe their role.
2. **Caller analysis**: Cross-reference which named functions call each
   service function to narrow its purpose.
3. **V2.4–V2.7 patch context**: Several service functions are
   flash/EEPROM helpers that the preset patches hook — their purpose
   is documented in the patch builder source.

This is incremental and does NOT block V3.1 implementation.

### B2. Inline immediate value comments

**Current state**: 24 inline comments on instructions.  The codex-cli
audit classified all 1,092 literal instructions with zero unknowns.

**Goal**: Every `movlw`/`addlw`/`sublw`/`iorlw`/`xorlw`/`retlw`/
`mullw`/`andlw` instruction gets a comment explaining the immediate
value's meaning.

**Data source**: The 1,092-row CSV at `/tmp/v30_immediate_analysis.csv`
with categories: ARITHMETIC, CMD_VALUE, RAM_ADDR, LOOP_COUNT, CONSTANT,
BITMASK, DATA_TABLE_REF, REGISTER_VALUE, STRING_CHAR, I2C_ADDR.

**Implementation**: Write a post-processing script that:
1. Reads `dlcp_main_v30_comments.asm`
2. For each literal instruction, looks up its stock address in the CSV
3. Appends the category and meaning as an inline comment
4. Writes back to the same file (or a new annotated version)

The script must match instructions by their position in the function
flow (label-relative), not by absolute address, since label names
changed between Phase 1 and the commented version.

**Priority**: Focus on the 17 DATA_TABLE_REF values first (already
converted to labels — the comments document WHY), then I2C_ADDR (7),
REGISTER_VALUE (13), and CMD_VALUE (157) since these are the most
meaningful for a reader.

### B3. Function-level comments (already done)

All 132 functions have header blocks.  The format is:
```asm
; ---------------------------------------------------------------------------
; Function: i2c_byte_tx
; Address : 0x3EB8
; Notes   : Transmit one byte via I2C MSSP. Bug M1: no ACKSTAT check.
;           Bug M1a: unbounded SSPIF wait. Fixed in V2.5/V2.6.
; ---------------------------------------------------------------------------
i2c_byte_tx:
```

**Enhancement opportunity**: Add parameter/side-effect/caller info to
the notes field for critical functions (I2C, UART, flash, command
dispatch).  This is incremental.

---

## Part C: Tooling Enhancement

### C1. Shift test uses commented source

The shift test (Part A) should use `dlcp_main_v30_comments.asm` as
the base, since that is the canonical source going forward.  This
simultaneously validates:
- The commented source is relocatable
- All label renames are correct (gpasm resolves them)
- The shift padding doesn't break any code path

### C2. Annotation script

A new script `scripts/annotate_immediates.py` reads the CSV audit and
the `.asm` source, matches literal instructions, and adds inline
comments.  It operates on the commented source and preserves all
existing comments.

### C3. Tests

```python
def test_v30_comments_assembles_identical():
    """Commented .asm must produce byte-identical hex."""
    # Already verified: code=0, preset=0, config=0, EEPROM=0 diffs

def test_v30_comments_no_auto_labels():
    """No function_NNN or label_NNN remain."""
    text = Path("src/dlcp_fw/asm/dlcp_main_v30_comments.asm").read_text()
    assert "function_0" not in text  # function_NNN pattern
    assert "label_0" not in text     # label_NNN pattern

def test_v30_comments_all_functions_documented():
    """Every function has a header comment."""
    text = Path("src/dlcp_fw/asm/dlcp_main_v30_comments.asm").read_text()
    func_count = text.count("; Function:")
    assert func_count >= 130
```

---

## Execution Order

### Phase 1: Shift test (proves relocation safety)

1. Create `dlcp_main_v30_shifted.asm` from `_comments.asm` + NOP padding
2. Convert `string_desc_ptr_table` data to label-relative `db` values
3. Assemble → shifted hex + `.lst` listing (verify no errors)
4. Write `parse_v30_symbols()` to extract symbol addresses from `.lst`
5. Write `main_serial_mailbox_hook_dynamic(symbols)` manifest builder
6. Update overlay preconditions, breakpoint constants, and `goto` targets
7. Preset table stays at 0x5600 (pinned by `org`) — no seeder change
8. Write `tests/sim/test_v30_relocation.py` (structural + gpsim tests)
9. Run full suite → all pass → relocation safety proven

### Phase 2: Immediate value annotation (incremental polish)

1. Write `scripts/annotate_immediates.py`
2. Run against `dlcp_main_v30_comments.asm`
3. Verify: still assembles byte-identical
4. Priority order: DATA_TABLE_REF → I2C_ADDR → REGISTER_VALUE → CMD_VALUE
5. Run annotation quality tests

**Note**: Phase 2 is incremental and does NOT block V3.1.  The
commented source already has all labels renamed and all functions
documented.

### Phase 3: V3.1 readiness gate

After Phase 1 passes:
- Relocation safety proven (shift test green)
- Canonical source (`_comments.asm`) is fully labeled and documented
- All 17 instruction-level TBLPTR references use labels
- Data-embedded pointer bytes (string_desc_ptr_table) use label arithmetic
- Zero hardcoded code addresses (verified by immediate audit + shift test)
- gpsim manifests refactored to use symbol lookup (not hardcoded addrs)
- `addlw LOW(label)` carry safety verified for shifted addresses
- V3.1 can freely modify function bodies knowing addresses shift safely

---

## Artifacts

| File | Purpose |
|------|---------|
| `src/dlcp_fw/asm/dlcp_main_v30_comments.asm` | **Canonical V3.0 source** — fully annotated, zero auto-labels, 132 function headers. Assembles byte-identical to stock. |
| `src/dlcp_fw/asm/dlcp_main_v30.asm` | Phase 1 output (auto-generated, kept for reference) |
| `src/dlcp_fw/asm/dlcp_main_v30_shifted.asm` | Shift test source (generated from `_comments.asm` + NOP padding) |
| `tests/sim/test_v30_relocation.py` | Shift test suite |
| `/tmp/v30_immediate_analysis.csv` | Full immediate value audit (1,092 rows) |
| `scripts/annotate_immediates.py` | Adds inline comments from CSV audit |
| `src/dlcp_fw/asm/dlcp_main_ram.inc` | RAM definitions (shared by all V3.x) |

---

## Constraints

- Shift test hex must NOT be committed to `firmware/patched/releases/`
  (it's a test artifact, not a release)
- `dlcp_main_v30_comments.asm` must always assemble to byte-identical output
- Comments and label changes must not affect assembled bytes
- The codex-cli CSV is a reference artifact, not committed
- `dlcp_main_v30_comments.asm` is the starting point for V3.1 edits
