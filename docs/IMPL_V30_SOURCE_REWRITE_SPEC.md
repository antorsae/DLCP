# V3.0 MAIN Source Rewrite — Implementation Prompt

Date: 2026-03-28
Parent spec: `docs/V30_SOURCE_REWRITE_SPEC.md`

## Parent Spec Supersessions

This implementation prompt **supersedes** the following parent spec sections
where they conflict with the design decisions below:

- **Address pinning**: Parent says "org directives placing code and data at
  their original addresses" and shows `org 0x1100`, `org 0x4970` in the
  source structure.  **Superseded**: no per-function `org`.  Only structural
  anchors use `org`.
- **Data/code split**: Parent uses 0x1018–0x10FF (data) / 0x1100 (code start).
  **Superseded**: boundary is 0x10AC (function_000 starts there).
- **Byte identity**: Parent says "Byte-identity is a goal."  **Clarified**:
  byte identity is validated for data regions only.  Code addresses may
  differ in theory, though in practice they should match (see §Address
  Stability below).
- **AC2 test list**: Parent lists `test_main_gpsim_preset_banks.py` and
  `test_main_gpsim_mailbox.py`.  **Superseded**: those are patched-only
  tests (A/B preset `cmd=0x20`), not stock-compatible.
- **"No test logic changes"**: Parent says "Minimal test infrastructure
  changes...no test logic changes."  **Superseded**: V3.0 needs new test
  files and a post-assembly symbol validation step.

All other parent spec content remains authoritative.

---

## Goal

Implement the V3.0 source-level rewrite of the DLCP MAIN PIC18F2455 firmware.
The result is an assembler-ready `.asm` source that gpasm compiles to an
app-only hex **functionally equivalent** to `DLCP Firmware V2.3.hex`,
validated by gpsim simulation.

**Key design principle**: The V3.0 source reads like natural, maintainable
assembly — NOT like a binary dump with `org` at every function.  Functions
are placed sequentially by the assembler.  Only structural anchors use `org`.
All references use symbolic labels.

All work happens in:
```
/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis
```

Python venv: `.venv_ep0/bin/python`

## Methodology: Red-Green-Refactor

1. **Write failing tests first** (red).
2. **Implement just enough to make them pass** (green).
3. **Refactor/clean up** while keeping tests green.
4. **Repeat** until full acceptance criteria are met.

---

## Address Layout Philosophy

### Structural anchors only

| Anchor | Address | Why pinned |
|--------|---------|-----------|
| `org 0x1000` | App entry | Bootloader's `goto` lands here |
| `org 0x5600` | Preset table A | TBLRD target with hardcoded pointer loads |
| `org 0xF00000` | EEPROM init data | Hardware address space |
| `__CONFIG` | 0x300000+ | Hardware config registers |

Everything else (functions, USB descriptors, inline data) flows naturally
from the preceding code/data without `org`.

### Address Stability — Why Addresses SHOULD Match Stock

Even without per-function `org`, the assembled V3.0 output should place
functions at the **same addresses** as stock V2.3.  This is because:

1. All instructions are the same (decoded from stock hex, re-encoded by gpasm)
2. All functions are emitted in the same order
3. PIC18 instruction sizes are deterministic — access-bit encoding only
   changes a single bit within the same 2-byte word, not the word count
4. USB descriptor data is emitted at the same relative offset from app entry
5. The `fill 0xFF, (0x5600 - $)` pads to the preset table

**If addresses DON'T match, it indicates a converter bug** (wrong instruction,
missing instruction, extra padding, etc.) that must be investigated and fixed.

This is critical because the **gpsim simulation infrastructure**
(`src/dlcp_fw/sim/manifests.py`) uses hardcoded stock function addresses
for simulation overlay patches:
- `org 0x45FA` (sim_function_087 = rx_ring_read)
- `org 0x4872` (sim_function_109)
- `org 0x4896` (uart_tx_byte_blocking)
- `org 0x48B6` (i2c_wait_bus_idle)
- `org 0x447E` (timer3_blocking_delay)

These overlays MUST land at the correct function addresses.  A post-assembly
symbol validation step (Test 16 below) catches any misalignment.

### TBLPTR Load Conversion

The stock firmware loads TBLPTR with hardcoded immediates.  V3.0 converts
these to label-based references for source readability and future relocatability.

**Pattern 1: Direct movlw/movwf**
```asm
; Stock:                         ; V3.0:
movlw  0x18                      movlw  LOW(usb_config_descriptor)
movwf  TBLPTRL                   movwf  TBLPTRL
movlw  0x10                      movlw  HIGH(usb_config_descriptor)
movwf  TBLPTRH                   movwf  TBLPTRH
```

**Pattern 2: Indexed addlw/movwf (hex lookup table at 0x1019)**

Four sites in the firmware use this pattern (at 0x16A6, 0x16CA, 0x18E2,
0x43CC):
```asm
; Stock:                         ; V3.0:
addlw  0x19                      addlw  LOW(hex_lookup_table)
movwf  TBLPTRL                   movwf  TBLPTRL
movlw  0x10                      movlw  HIGH(hex_lookup_table)
movwf  TBLPTRH                   movwf  TBLPTRH
```

The `addlw` adds the table base offset to an index in WREG.  Since
addresses are stable (same layout), `LOW(hex_lookup_table)` resolves
to 0x19 and `HIGH(hex_lookup_table)` to 0x10 — identical to stock.

**Page-boundary carry note**: The `addlw LOW(table)` pattern assumes
`index + LOW(table)` does NOT carry into TBLPTRH.  In stock, the hex
lookup table at 0x1019 with max index 0x0F gives 0x1019+0x0F=0x1028 —
no carry.  This constraint must be preserved: if a future version moves
this table, ensure it doesn't cross a 256-byte page boundary.  For V3.0,
addresses match stock, so this is safe.

### Inline Data Within Code Region

The stock firmware has inline data tables within the code range that must
NOT be decoded as instructions.  Known instances:

| Address (stock) | Size | Content | Accessed by |
|----------------|------|---------|-------------|
| 0x1019–0x10AB | ~148 bytes | USB descriptors, pointer/lookup tables | TBLRD via function_074, USB engine |
| 0x47E6–0x47FB | 22 bytes | Data table (string/parameter data) | TBLRD via flash_read (TBLPTR=0x47E6) |

The region manifest must classify these as "data" sub-regions so the
converter emits them as `db`/`dw` rather than decoding them as instructions.

---

## Phase 0: Boundary Discovery (before tests or manifest)

### Step 0.1: Hex dump USB descriptor area

Dump raw hex bytes at 0x1018–0x10AB and identify USB descriptor boundaries
by standard header bytes.  Document the exact boundaries.

### Step 0.2: Identify ALL TBLPTR load sites

Grep the annotated disassembly for all `movwf TBLPTRL/H/U` and `addlw`
patterns to find every TBLPTR load site.  For each, determine:
- What data table it targets
- Whether it uses direct `movlw` or indexed `addlw`
- What label should replace the hardcoded immediate

### Step 0.3: Identify inline data tables

Search for TBLRD instruction sites and trace their TBLPTR values to find
all inline data tables within the code range.  Add each to the region
manifest.

Known: 0x47E6–0x47FB (22 bytes, accessed via `flash_read` with
TBLPTR=0x47E6).

---

## Phase 1: Test Infrastructure (write tests first — they MUST fail)

### 1A. Path constant

Add to `src/dlcp_fw/paths.py`:
```python
V30_MAIN_HEX = FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V3.0.hex"
```

### 1B. Pytest fixture

Add to `tests/sim/conftest.py`:
```python
@pytest.fixture(scope="session")
def v30_main_hex() -> Path:
    if not V30_MAIN_HEX.exists():
        raise RuntimeError(f"missing V3.0 main HEX: {V30_MAIN_HEX}")
    return V30_MAIN_HEX
```

### 1C. Equivalence tests — `tests/sim/test_v30_equivalence.py`

**Test 1: hex file exists**
```python
def test_v30_hex_exists(v30_main_hex):
    assert v30_main_hex.exists()
```

**Test 2: config bits identical (byte-compare gate — gpsim cannot validate)**
```python
def test_v30_config_bits_identical(v30_main_hex, stock_main_hex):
    """build_seeded_main_sim_hex() preserves config from seed, not V3.0."""
    from dlcp_fw.sim.hexio import parse_intel_hex
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    for addr in range(0x300000, 0x30000E):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), \
            f"Config mismatch at 0x{addr:06X}"
```

**Test 3: EEPROM identical (byte-compare gate)**
```python
def test_v30_eeprom_identical(v30_main_hex, stock_main_hex):
    from dlcp_fw.sim.hexio import parse_intel_hex
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    for addr in range(0xF00000, 0xF00100):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), \
            f"EEPROM mismatch at 0x{addr:06X}"
```

**Test 4: preset table identical (byte-compare gate — MAIN_APP_PATCH_LIMIT=0x5600)**
```python
def test_v30_preset_table_identical(v30_main_hex, stock_main_hex):
    from dlcp_fw.sim.hexio import parse_intel_hex
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    for addr in range(0x5600, 0x6000):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), \
            f"Preset table mismatch at 0x{addr:06X}"
```

**Test 5: USB descriptor content present**
```python
def test_v30_usb_descriptor_content(v30_main_hex, stock_main_hex):
    """USB descriptors must be present in V3.0 output.
    Compare content, not fixed addresses — descriptors follow app entry
    and should be at the same offset if entry stub is same size."""
    from dlcp_fw.sim.hexio import parse_intel_hex
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    # USB device descriptor signature: 18 bytes starting 0x12, 0x01
    # Find it in stock to get the canonical content
    dev_desc_stock = bytes(stock.get(0x1088 + i, 0xFF) for i in range(18))
    assert dev_desc_stock[0] == 0x12 and dev_desc_stock[1] == 0x01
    # Find the same 18-byte sequence in V3.0 output
    built_range = bytes(built.get(a, 0xFF) for a in range(0x1000, 0x1200))
    assert dev_desc_stock in built_range, \
        "USB device descriptor not found in V3.0 output"
```

**Test 6: app entry at 0x1000**
```python
def test_v30_app_entry_at_0x1000(v30_main_hex):
    from dlcp_fw.sim.hexio import parse_intel_hex
    built = parse_intel_hex(v30_main_hex)
    assert 0x1000 in built, "No code at 0x1000"
```

**Test 7: no boot block emitted**
```python
def test_v30_no_boot_block(v30_main_hex):
    from dlcp_fw.sim.hexio import parse_intel_hex
    built = parse_intel_hex(v30_main_hex)
    boot_bytes = [a for a in built if a < 0x1000]
    assert boot_bytes == [], f"Boot block bytes: {[hex(a) for a in boot_bytes[:10]]}"
```

**Test 8: code size reasonable (±5% of stock)**
```python
def test_v30_code_size_reasonable(v30_main_hex, stock_main_hex):
    from dlcp_fw.sim.hexio import parse_intel_hex
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    stock_code = sum(1 for a in range(0x1000, 0x4970) if stock.get(a, 0xFF) != 0xFF)
    built_code = sum(1 for a in range(0x1000, 0x5600) if built.get(a, 0xFF) != 0xFF)
    ratio = built_code / stock_code if stock_code > 0 else 0
    assert 0.95 <= ratio <= 1.05, \
        f"Code size ratio {ratio:.3f} (stock={stock_code}, v30={built_code})"
```

**Test 9: diagnostic byte-diff summary (always passes)**
```python
def test_v30_byte_diff_diagnostic(v30_main_hex, stock_main_hex):
    from dlcp_fw.sim.hexio import parse_intel_hex
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    for label, start, end in [
        ("preset table", 0x5600, 0x6000),
        ("config", 0x300000, 0x30000E),
        ("EEPROM", 0xF00000, 0xF00100),
    ]:
        diffs = sum(1 for a in range(start, end)
                    if stock.get(a, 0xFF) != built.get(a, 0xFF))
        print(f"\n  {label}: {diffs} differences")
    built_total = sum(1 for a in range(0x1000, 0x5600) if a in built)
    print(f"  V3.0 code+data bytes (0x1000-0x55FF): {built_total}")
```

**Test 10: semantic labels present (AC3)**
```python
def test_v30_source_has_semantic_labels():
    from dlcp_fw.paths import PROJECT_ROOT
    asm_path = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
    assert asm_path.exists()
    text = asm_path.read_text()
    for label in [
        "cmd_dispatch_gated", "adc_boot_gate", "i2c_byte_tx",
        "uart_tx_byte_blocking", "send_status_burst", "hw_standby_shutdown",
        "flash_write", "i2c_wait_bus_idle", "hard_reset",
    ]:
        assert label in text, f"Missing label: {label}"
```

**Test 11: named RAM equates (AC3)**
```python
def test_v30_source_has_named_ram():
    from dlcp_fw.paths import PROJECT_ROOT
    asm_dir = PROJECT_ROOT / "src" / "dlcp_fw" / "asm"
    combined = ""
    for f in list(asm_dir.glob("*.asm")) + list(asm_dir.glob("*.inc")):
        combined += f.read_text()
    for name in ["active_flags", "event_flags", "logical_volume", "rx_frame_position"]:
        assert name in combined, f"Missing RAM name: {name}"
```

**Test 12: no raw branch targets (AC3)**
```python
def test_v30_no_raw_hex_branch_targets():
    import re
    from dlcp_fw.paths import PROJECT_ROOT
    asm_path = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
    text = asm_path.read_text()
    raw_target = re.compile(
        r'^\s*(?:goto|call|bra|rcall|bc|bnc|bz|bnz|bov|bnov|bn|bnn)\s+'
        r'(?:0x[0-9A-Fa-f]+|H\'[0-9A-Fa-f]+\')',
        re.MULTILINE | re.IGNORECASE,
    )
    matches = raw_target.findall(text)
    assert matches == [], f"Raw branch targets: {matches[:5]}"
```

**Test 13: no raw SFR addresses (AC3)**
```python
def test_v30_sfr_references_are_symbolic():
    import re
    from dlcp_fw.paths import PROJECT_ROOT
    asm_path = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
    text = asm_path.read_text()
    sfr_addrs = {
        0xFE8: "WREG", 0xFD8: "STATUS", 0xFE0: "BSR",
        0xFC7: "SSPSTAT", 0xFC6: "SSPCON1", 0xFC5: "SSPCON2",
        0xFC9: "SSPBUF", 0xFAB: "RCSTA", 0xFAC: "TXSTA",
        0xFAD: "TXREG", 0xF80: "PORTA", 0xF81: "PORTB", 0xF82: "PORTC",
    }
    problems = []
    for line in text.splitlines():
        stripped = line.split(";")[0].strip()
        if not stripped or stripped.upper().startswith(("EQU", "DB", "DW", "#")):
            continue
        for addr, name in sfr_addrs.items():
            if re.search(rf'\b0x{addr:03X}\b', stripped, re.IGNORECASE):
                problems.append(f"Raw 0x{addr:03X} not {name}: {stripped[:60]}")
    assert problems == [], f"{len(problems)} raw SFR refs:\n" + "\n".join(problems[:10])
```

**Test 14: no per-function org directives**
```python
def test_v30_no_per_function_org():
    import re
    from dlcp_fw.paths import PROJECT_ROOT
    asm_path = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
    text = asm_path.read_text()
    orgs = re.findall(r'^\s*org\s+(0x[0-9A-Fa-f]+|H\'[0-9A-Fa-f]+\')',
                      text, re.MULTILINE | re.IGNORECASE)
    allowed = {0x1000, 0x5600, 0xF00000}
    for a in range(0x300000, 0x30000E):
        allowed.add(a)
    for org_str in orgs:
        addr = int(org_str.strip("Hh'"), 16) if "'" in org_str else int(org_str, 16)
        assert addr in allowed, f"Unexpected org 0x{addr:06X}"
```

**Test 15: TBLPTR loads use labels**
```python
def test_v30_tblptr_loads_use_labels():
    import re
    from dlcp_fw.paths import PROJECT_ROOT
    asm_path = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
    text = asm_path.read_text()
    lines = text.splitlines()
    problems = []
    for i, line in enumerate(lines):
        s = line.split(";")[0].strip().lower()
        ns = lines[i + 1].split(";")[0].strip().lower() if i + 1 < len(lines) else ""
        if re.match(r'movlw\s+(0x[0-9a-f]+|h\'[0-9a-f]+\'|\d+)\s*$', s):
            if re.match(r'movwf\s+tblptr[lhu]', ns):
                problems.append(f"Line {i+1}: bare TBLPTR load: {line.strip()}")
        # Also check addlw <bare literal> followed by movwf tblptrl
        if re.match(r'addlw\s+(0x[0-9a-f]+|h\'[0-9a-f]+\'|\d+)\s*$', s):
            if re.match(r'movwf\s+tblptrl', ns):
                problems.append(f"Line {i+1}: bare addlw+TBLPTR: {line.strip()}")
    assert problems == [], \
        f"{len(problems)} bare TBLPTR loads:\n" + "\n".join(problems[:10])
```

**Test 16: post-assembly symbol address validation (critical)**
```python
def test_v30_key_symbols_at_stock_addresses(v30_main_hex, stock_main_hex):
    """Verify that key function entry points land at their stock addresses.
    Even without per-function org, addresses SHOULD match because the same
    instructions are emitted in the same order.  If this fails, it indicates
    a converter bug (wrong instruction, missing data, etc.).

    This test also validates that the gpsim overlay infrastructure
    (manifests.py hardcoded addresses) will work with V3.0 hex."""
    from dlcp_fw.sim.hexio import parse_intel_hex
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    # Key addresses used by gpsim manifests.py overlays + test breakpoints
    critical_addrs = [
        # gpsim manifests.py overlay landing addresses (ALL of them):
        0x45FA,  # rx_ring_read (sim overlay)
        0x4872,  # sim_function_109 (sim overlay)
        0x4896,  # uart_tx_byte_blocking (sim overlay)
        0x489A,  # NOP after uart_tx_byte_blocking goto (sim overlay)
        0x48B6,  # i2c_wait_bus_idle (sim overlay)
        0x447E,  # timer3_blocking_delay (sim overlay → 0x4492 variant)
        0x4492,  # sim_function_113 (sim overlay, alt i2c_wait_bus_idle)
        0x2D9E,  # sim_function_111 (sim overlay, alt uart_tx_byte_blocking)
        0x2D8C,  # adc_boot_gate entry (test breakpoint)
        # Key function entries:
        0x18EE,  # function_005 (cmd_dispatch_gated) — NOTE: entry is
                 # 0x18EE, not 0x18F2 (0x18F2 is the btfss inside)
        0x10AC,  # function_000 (first code after USB data)
    ]
    mismatches = []
    for addr in critical_addrs:
        s = (stock.get(addr, 0xFF), stock.get(addr + 1, 0xFF))
        b = (built.get(addr, 0xFF), built.get(addr + 1, 0xFF))
        if s != b:
            mismatches.append(
                f"0x{addr:04X}: stock={s[0]:02X}{s[1]:02X} v30={b[0]:02X}{b[1]:02X}"
            )
    assert mismatches == [], \
        f"V3.0 symbol addresses diverge from stock (converter bug?):\n" + \
        "\n".join(mismatches)
```

### 1D. gpsim equivalence tests — `tests/sim/test_v30_gpsim_equivalence.py`

**Stock-compatible test inventory** (precise per-function breakdown):

| Test file | Stock test functions | Use in V3.0 |
|-----------|---------------------|-------------|
| `test_main_gpsim_an0_boot.py` | `test_main_boot_gate_exits_with_real_an0_stimulus[stock_v23]` | YES |
| `test_main_gpsim_i2c_regfile.py` | All 7 `stock_main_hex` tests | YES |
| `test_main_gpsim_fault_injection.py` | All 3 `stock_main_hex` tests | YES |
| `test_main_gpsim_command_matrix.py` | All parametrized (uses local `STOCK_MAIN_HEX`) | YES |
| `test_main_gpsim_command_edges.py` | All parametrized (uses local `STOCK_MAIN_HEX`) | YES |
| `test_main_gpsim_cmd03_instruction_path.py` | ALL tests take `patched_fixture` — this is a **patched-only** file despite importing `STOCK_MAIN_HEX` for comparison | NO (exclude entirely) |
| `test_main_stdby_pin_io.py` | **MIXED** — `test_stdby_pin_io_local_mode` uses `STOCK_MAIN_HEX`; `FIRMWARE_COMBOS` parametrize has 3 stock entries (`v23+v14`, `v23+v15b`, `v23+v16b`); skip patched entries | YES (stock entries only) |
| `test_wire_chain_gpsim.py` | **MIXED** — functions using `_new_stock_wire_chain(stock_control_hex_v14, stock_main_hex)` are stock; skip anything using `_new_patched_wire_chain` | YES (stock functions only) |
| `test_wire_chain_gpsim_stock_faults.py` | **MIXED** — parametrize includes `STOCK_MAIN_HEX` AND various `PATCHED_MAIN_HEX_*` entries; replicate ONLY the `STOCK_MAIN_HEX` parametrize entries | YES (STOCK_MAIN_HEX entries only) |
| `test_chain_gpsim_waiting.py` | All 4 tests take `stock_main_hex` fixture | YES (all) |
| `test_main_dsp_deafness_chain.py` | **MIXED** — parametrize has `STOCK_MAIN_HEX` plus patched entries; replicate ONLY the `STOCK_MAIN_HEX` entry | YES (stock entry only) |

**NOT stock-compatible** (exclude from V3.0):
- `test_main_gpsim_preset_banks.py` — A/B preset `cmd=0x20` (V2.4+)
- `test_main_gpsim_mailbox.py` — defaults to patched hex
- `test_main_gpsim_filename_ab.py` — A/B preset filename

**AN0 boot gate**: Assert the exact stock cycle count `4_061_516`.
Since addresses should match (Test 16 validates this), the cycle count
should be identical.  A different cycle count indicates a behavioral
divergence that must be investigated.

The V3.0 gpsim equivalence file replicates each stock-compatible test
using `v30_main_hex` (or `V30_MAIN_HEX` path) instead of stock.
Same harness calls, same assertions, same expected values.

---

## Phase 2: Region Manifest — `src/dlcp_fw/asm/region_manifest.py`

Classifies the **stock** address space for the converter.

### Test first — `tests/sim/test_region_manifest.py`

```python
def test_manifest_covers_full_stock_range():
    from dlcp_fw.asm.region_manifest import classify_address
    for addr in range(0x1000, 0x6000):
        assert classify_address(addr) in ("code", "data", "erased")

def test_manifest_usb_data_boundary():
    from dlcp_fw.asm.region_manifest import classify_address
    for addr in range(0x1018, 0x10AC):
        assert classify_address(addr) == "data"
    assert classify_address(0x10AC) == "code"

def test_manifest_inline_data_0x47E6():
    """Inline data table at 0x47E6-0x47FB must be classified as data."""
    from dlcp_fw.asm.region_manifest import classify_address
    for addr in range(0x47E6, 0x47FC):
        assert classify_address(addr) == "data"

def test_manifest_preset_table():
    from dlcp_fw.asm.region_manifest import classify_address
    for addr in range(0x5600, 0x6000):
        assert classify_address(addr) == "data"

def test_manifest_erased():
    from dlcp_fw.asm.region_manifest import classify_address
    for addr in range(0x4970, 0x5600):
        assert classify_address(addr) == "erased"

def test_manifest_known_code():
    from dlcp_fw.asm.region_manifest import classify_address
    for addr in [0x1000, 0x10AC, 0x18F2, 0x2D8C, 0x4896]:
        assert classify_address(addr) == "code"
```

### Implement

Create `src/dlcp_fw/asm/__init__.py` (empty) and
`src/dlcp_fw/asm/region_manifest.py`.

Stock region boundaries:

| Start | End (excl) | Type | Content |
|-------|-----------|------|---------|
| 0x1000 | 0x1018 | code | App entry + ISR dispatch stubs |
| 0x1018 | 0x10AC | data | USB descriptors, pointer/lookup tables |
| 0x10AC | 0x47E6 | code | function_000 through pre-inline-data code |
| 0x47E6 | 0x47FC | data | Inline data table (22 bytes, TBLRD target) |
| 0x47FC | 0x4970 | code | Remaining code after inline data |
| 0x4970 | 0x5600 | erased | Free flash |
| 0x5600 | 0x6000 | data | DSP preset table A |

Support sub-region overrides for additional TBLRD inline data discovered
during Phase 0.

---

## Phase 3: Disassembly-to-Source Converter

### Test first — `tests/sim/test_disasm_to_source.py`

```python
def test_converter_produces_asm_file(tmp_path):
    from dlcp_fw.analysis.disasm_to_source import convert
    out = tmp_path / "test.asm"
    convert(output_path=out)
    assert out.exists()
    assert out.stat().st_size > 10000

def test_converter_structural_org_only(tmp_path):
    import re
    from dlcp_fw.analysis.disasm_to_source import convert
    out = tmp_path / "test.asm"
    convert(output_path=out)
    text = out.read_text()
    orgs = re.findall(r'^\s*org\s+(0x[0-9A-Fa-f]+)', text, re.MULTILINE | re.IGNORECASE)
    for org_str in orgs:
        addr = int(org_str, 16)
        assert addr in {0x1000, 0x5600, 0xF00000} or 0x300000 <= addr <= 0x30000D

def test_converter_has_config(tmp_path):
    from dlcp_fw.analysis.disasm_to_source import convert
    out = tmp_path / "test.asm"
    convert(output_path=out)
    assert "__CONFIG" in out.read_text()

def test_converter_assembles(tmp_path):
    """The converter must emit the .asm AND any required .inc files
    into the same directory, so gpasm -I finds them."""
    import subprocess
    from dlcp_fw.analysis.disasm_to_source import convert
    out_asm = tmp_path / "test.asm"
    out_hex = tmp_path / "test.hex"
    convert(output_path=out_asm)  # must also emit dlcp_main_ram.inc alongside
    result = subprocess.run(
        ["gpasm", "-p18f2455", "-I", str(tmp_path), "-o", str(out_hex), str(out_asm)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f"gpasm failed:\n{result.stderr}"
```

### Implement — `src/dlcp_fw/analysis/disasm_to_source.py`

#### Source structure emitted

```asm
    LIST P=18F2455
    #include <p18f2455.inc>
    #include "dlcp_main_ram.inc"

; --- Configuration bits ---
    __CONFIG _CONFIG1L, _PLLDIV_3_1L & ...
    ; [all config directives]

; --- App entry (0x1000) ---
    org 0x1000
app_entry:
    goto app_start
    dw 0xFFFF, 0xFFFF
isr_dispatch_stub:
    movff FSR2L, isr_save_fsr2l
    ; ...

; --- USB Descriptors (data, follows entry naturally) ---
hex_lookup_table:                ; @ 0x1019 in stock
    db 0x30, 0x31, ...          ; "0123456789ABCDEF"
usb_config_descriptor:
    db 0x09, 0x02, ...
    ; [all USB data from stock hex bytes]
usb_device_descriptor:
    db 0x12, 0x01, ...

; --- Application Code (flows naturally, NO per-function org) ---
usb_ep0_handler:                 ; function_000 (@ 0x10AC in stock)
    movff WREG, ...
    ; ...

cmd_dispatch_gated:              ; function_005 (@ 0x18EE in stock)
    btfss active_flags, ACTIVE_GATE_BIT
    return
    ; ...

; [... all functions in stock address order ...]

inline_data_table_47E6:          ; data table (@ 0x47E6 in stock)
    db ...                       ; 22 bytes of table data

; [... remaining functions ...]

hard_reset:                      ; function_114 (@ 0x48D4 in stock)
    clrf INTCON, ACCESS
    reset

; --- Erased flash padding ---
    fill 0xFF, (0x5600 - $)

; --- DSP Preset Table A ---
    org 0x5600
preset_table_a:
    dw 0x0000, ...

; --- EEPROM ---
    org 0xF00000
eeprom_data:
    db 0xFF, ...
    db "LX521.4 V15 L22M"       ; filename slot A
    ; ...

    END
```

#### PIC18 Instruction Decoding

**Decode from stock hex bytes, NOT from disassembler text.**

`parse_intel_hex()` returns `Dict[int, int]` keyed by byte address.
Little-endian: `word = mem[addr] | (mem[addr+1] << 8)`

**Instruction walk** (walk by instruction width, consume multi-word):

```python
addr = region_start  # byte address, must be even
while addr < region_end:
    word = mem.get(addr, 0xFF) | (mem.get(addr + 1, 0xFF) << 8)
    instr, is_two_word = decode_pic18_instruction(word)

    if is_two_word:
        word2 = mem.get(addr + 2, 0xFF) | (mem.get(addr + 3, 0xFF) << 8)
        instr = finalize_two_word(instr, word, word2)
        addr += 4  # consume both words
    else:
        addr += 2  # consume one word
```

**Two-word instructions** (must consume second word, not revisit as opcode):
- `MOVFF fs, fd` — word1: `1100 ffff ffff ffff`, word2: `1111 ffff ffff ffff`
- `CALL k, s` — word1: `1110 110s kkkk kkkk`, word2: `1111 kkkk kkkk kkkk`
- `GOTO k` — word1: `1110 1111 kkkk kkkk`, word2: `1111 kkkk kkkk kkkk`
- `LFSR f, k` — word1: `1110 1110 00ff kkkk`, word2: `1111 0000 kkkk kkkk`

`CALL`/`GOTO` target byte address reconstruction:
`target = ((word2 & 0x0FFF) << 8) | (word1 & 0x00FF)` left-shifted by 1.
**Verify against Table 28-2 in 39632e.pdf.**

**Undecodable / filler words in code regions**: The stock code contains
`dw 0xFFFF` filler words at 0x1004 and 0x1006 (between app entry `goto`
and the ISR dispatch stub).  These are NOT valid PIC18 instructions.
The decoder MUST handle this: when a word in a code-classified region does
not decode to any valid PIC18 instruction, emit it as `dw 0xNNNN`.  This
preserves byte-identity without misinterpreting the data.  The same applies
to any second-word of a two-word instruction that appears as `0xFnnn`
when the first word is NOT a two-word opcode — it's filler or padding,
not an instruction.

**Relative branches** (BRA, RCALL, Bcc):
- BRA/RCALL: k is 11-bit signed, `target = PC + 2 + 2*sign_extend_11(k)`
- Bcc: k is 8-bit signed, `target = PC + 2 + 2*sign_extend_8(k)`
- PC here is the byte address of the instruction itself

All targets must resolve to labels.

**SFR Symbolic Names**: Parse from `/opt/homebrew/share/gputils/header/p18f2455.inc`.
Extract all `^(\w+)\s+EQU\s+H'([0-9A-Fa-f]+)'` lines.  Do NOT hardcode.

**TBLPTR load conversion**: Identify `movlw <imm>` + `movwf TBLPTRx` and
`addlw <imm>` + `movwf TBLPTRL` sequences.  Replace immediates with
`LOW(label)` / `HIGH(label)` / `UPPER(label)`.

**Label pool** (priority order):
1. Semantic function map → `cmd_dispatch_gated`, etc.
   **Important**: Map semantic names by auto-name (e.g., `function_005` →
   `cmd_dispatch_gated`), NOT by address.  The semantic map lists `0x18F2`
   for `cmd_dispatch_gated`, but the annotated disassembly shows
   `function_005` entry at `0x18EE` — the map address is an internal site,
   not the function entry.  Always match on the auto-name, then apply the
   semantic rename to wherever the annotated disasm places that label.
2. Annotated disassembly → `label_NNN`, `function_NNN`
3. Generated → `loc_XXXX` for unlabeled targets

**Access bank**: emit `, ACCESS` for a=0, `, BANKED` for a=1.

**Data emission**:
- USB descriptors: `db` with field comments, labeled for TBLPTR
- Inline data (0x47E6 etc.): `db` with label
- Preset table: `dw` at `org 0x5600`
- EEPROM: `db` at `org 0xF00000`
- Erased: `fill 0xFF, (0x5600 - $)`

**Config bits**: Symbolic form from spec, verified against gputils header.
Fall back to raw `__CONFIG H'300000', H'3A'` if needed.

### Converter must emit include files alongside the .asm

The `convert()` function takes `output_path` for the `.asm` file.  It MUST
also emit `dlcp_main_ram.inc` (and optionally `dlcp_main_macros.inc`) into
the **same directory** as the `.asm` output.  This is required because:
- The `.asm` uses `#include "dlcp_main_ram.inc"` (quoted, local path)
- `gpasm -I <dir>` must find the include file
- Tests that assemble in tmp_path need the include alongside the `.asm`

### Thin entrypoint — `scripts/disasm_to_source.py`

```python
#!/usr/bin/env python3
from dlcp_fw.analysis.disasm_to_source import convert
from dlcp_fw.paths import PROJECT_ROOT
convert(output_path=PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm")
```

### RAM include — `src/dlcp_fw/asm/dlcp_main_ram.inc`

Named RAM equates from spec.  Add `ram_0xNNN` placeholders for all other
RAM addresses used by decoded instructions.  Generated by the converter
into the same directory as the `.asm` file.

---

## Phase 4: Build Script — `scripts/build_v30.sh`

Create per spec D3.  `chmod +x`.  Byte-comparison step should compare
data regions only (preset, config, EEPROM) — code addresses may theoretically
differ.

---

## Phase 5: Assemble and Iterate

1. `scripts/disasm_to_source.py` → generate `.asm`
2. `scripts/build_v30.sh` → assemble with gpasm
3. `pytest tests/sim/test_v30_equivalence.py -v` → fix failures
4. `pytest tests/sim/test_region_manifest.py tests/sim/test_disasm_to_source.py -v`
5. Iterate until all pass, especially **Test 16 (symbol address validation)**

---

## Phase 6: gpsim Simulation Validation

Primary acceptance gate.

```bash
.venv_ep0/bin/python -m pytest tests/sim/test_v30_gpsim_equivalence.py -v
```

(`pytest-timeout` not installed — do not use `--timeout`.)

Fix failures by tracing gpsim execution divergence points.  Common causes:
wrong instruction, wrong branch target, data decoded as code, TBLPTR label
not resolved.

---

## Phase 7: Source Cleanup (AC3)

```bash
.venv_ep0/bin/python -m pytest tests/sim/test_v30_equivalence.py -v -k "source or sfr or branch or tblptr or org"
```

---

## What gpsim CAN and CANNOT validate

**CAN** (overlaid at 0x1000-0x55FF by `build_seeded_main_sim_hex()`):
- Code execution, branches, RAM, I2C/UART/Timer, interrupts, stock bugs

**CANNOT** (preserved from seed, not V3.0):
- Config bits — byte-compare only
- EEPROM — byte-compare only
- Preset table (0x5600+) — byte-compare only (MAIN_APP_PATCH_LIMIT=0x5600)
- Boot block — out of scope

---

## Files Created/Modified

### New files

| File | Purpose |
|------|---------|
| `src/dlcp_fw/asm/__init__.py` | Package init |
| `src/dlcp_fw/asm/region_manifest.py` | Stock address classification |
| `src/dlcp_fw/asm/dlcp_main_ram.inc` | RAM definitions |
| `src/dlcp_fw/asm/dlcp_main_v30.asm` | Generated V3.0 source |
| `src/dlcp_fw/analysis/disasm_to_source.py` | Converter |
| `scripts/disasm_to_source.py` | Entrypoint |
| `scripts/build_v30.sh` | Build + data byte-compare |
| `tests/sim/test_v30_equivalence.py` | Hex + AC3 tests |
| `tests/sim/test_v30_gpsim_equivalence.py` | gpsim behavioral tests |
| `tests/sim/test_region_manifest.py` | Manifest tests |
| `tests/sim/test_disasm_to_source.py` | Converter tests |

### Modified files

| File | Change |
|------|--------|
| `src/dlcp_fw/paths.py` | Add `V30_MAIN_HEX` |
| `tests/sim/conftest.py` | Add `v30_main_hex` fixture |

---

## Execution Checklist

1. [ ] Phase 0: hex dump USB area, find TBLPTR sites, find inline data tables
2. [ ] Add `V30_MAIN_HEX` to paths.py + fixture to conftest.py
3. [ ] Write test_v30_equivalence.py — all fail
4. [ ] Write test_v30_gpsim_equivalence.py — all fail
5. [ ] Write test_region_manifest.py — fail
6. [ ] Implement region manifest — tests pass
7. [ ] Write test_disasm_to_source.py — fail
8. [ ] Implement converter + RAM include + entrypoint
9. [ ] Create build_v30.sh
10. [ ] Generate .asm → assemble → run data tests → iterate
11. [ ] Run Test 16 (symbol validation) — addresses must match stock
12. [ ] Run AC3 tests (labels, RAM, SFR, branches, TBLPTR, org)
13. [ ] Run gpsim equivalence — iterate until pass
14. [ ] Wire-chain e2e + stock faults
15. [ ] All tests green

---

## Key Reference Files

| What | Path |
|------|------|
| Stock V2.3 hex | `firmware/stock/main/DLCP Firmware V2.3.hex` |
| Combined recovery image | `firmware/stock/main/DLCP Firmware V2.3-combined.hex` |
| Annotated disassembly | `firmware/disasm/main/gpdasm_output.annotated.asm` |
| Semantic function map | `docs/analysis/SEMANTIC_FUNCTION_MAP.md` |
| PIC18F2455 datasheet | `firmware/reference/39632e.pdf` |
| gputils header | `/opt/homebrew/share/gputils/header/p18f2455.inc` |
| Hex parser | `src/dlcp_fw/sim/hexio.py` |
| gpsim seeder | `src/dlcp_fw/sim/main_gpsim.py` — `build_seeded_main_sim_hex()` |
| gpsim overlays | `src/dlcp_fw/sim/manifests.py` (hardcoded stock addresses) |
| Seeder constants | `MAIN_APP_PATCH_START=0x1000`, `MAIN_APP_PATCH_LIMIT=0x5600` |

---

## Constraints

- Python: `.venv_ep0/bin/python`
- gpasm: `/opt/homebrew/bin/gpasm` 1.5.2
- gputils header: `/opt/homebrew/share/gputils/header/p18f2455.inc`
- No new dependencies; `pytest-timeout` NOT installed
- gpasm-compatible `.asm` (not MPLAB XC8)
- V3.0 = V2.3 behavior including all bugs — no fixes
- App-only hex (no boot block)
- No per-function `org` — structural anchors only
- TBLPTR loads use `LOW`/`HIGH`/`UPPER(label)`, not bare literals
- Data regions byte-identical to stock
- Code: gpsim is sole behavioral gate
- Addresses SHOULD match stock (same instructions, same order); validated by Test 16
- Data/code boundary at 0x10AC, not 0x1100
- Inline data at 0x47E6-0x47FB must be emitted as data, not decoded as code
- SFR addresses parsed from p18f2455.inc, not hardcoded
