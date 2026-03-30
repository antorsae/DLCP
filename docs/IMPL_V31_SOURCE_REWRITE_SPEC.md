# V3.1 MAIN Source Rewrite — Implementation Prompt

Date: 2026-03-28
Status: completed (V3.1 hex committed, 80-test gate passing)
Parent spec: `docs/V31_SOURCE_REWRITE_SPEC.md`

Implementation note (2026-03-30): the committed repo assembles V3.1 via
the `assemble_v30(...)` helper command documented in `AGENTS.md`. The
optional `scripts/build_v31.sh` snippet below was a planning example and
is not a committed canonical entrypoint.

## Goal

Build `dlcp_main_v31.asm` by editing a copy of the canonical V3.0
commented source (`dlcp_main_v30_comments.asm`), modifying function
bodies **in-place** to add all V2.4–V2.7 features.  No jump-out hooks,
no patch regions, no fixed-address stubs.  Assemble with gpasm, use
the dynamic gpsim manifests (already built for the shift test) for
simulation, validate with the 5 V2.7 robustness tests (all must PASS).

Working directory: `/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis`
Python venv: `.venv_ep0/bin/python`
gpasm: `/opt/homebrew/bin/gpasm`

---

## Proven Infrastructure (from V3.0 relocation shift test)

The V3.0 shift test (commit `dd7cd2f`) proved that code can shift
freely and built the infrastructure V3.1 needs:

| Component | Module | Purpose |
|-----------|--------|---------|
| `parse_gpasm_symbols()` | `v30_symbols.py` | Extracts label→address from `.lst` |
| `assemble_v30()` | `v30_symbols.py` | Assembles with gpasm, returns hex path |
| `main_serial_mailbox_hooks_dynamic(symbols)` | `manifests.py` | Templates overlay ASM with shifted addresses |
| `overlay_manifests` param | `main_gpsim.py` | Injects custom overlays into `run_main_mailbox_gpsim()` |
| `V30_MAIN_ASM_COMMENTS` | `paths.py` | Canonical V3.0 commented source path |

V3.1 reuses ALL of this.  The only new pieces needed are:
- `V31_MAIN_HEX` and `V31_MAIN_ASM` path constants
- V3.1 test file
- The actual V3.1 `.asm` source

---

## Design Principle: Functions Are Complete

Every modified function contains its full enhanced logic inline.  The
reader never has to chase a `goto patch_region` to understand what a
function does.  New helper functions (bounded waits, recovery, bus-clear,
DSP ping) are added as regular functions in the natural code flow — NOT
at `org 0x5400` or any other pinned address.

Because function bodies grow, **all addresses after the first edit shift**.
This is intentional.  All branch targets, call targets, and data
references use symbolic labels.  The gpasm assembler resolves everything.
The shift test proved this is safe: AN0 boot exits at the exact stock
cycle count (4,061,516) even with 0x222 bytes of padding inserted.

### Hardware-pinned entry block (0x1000–0x1019)

The boot block (ROM) has hardcoded `GOTO` to 0x1000, 0x1008, and 0x1018.
The entry block is fixed:

```asm
    org 0x1000
app_entry:              ; 0x1000 — boot exit target
    goto app_init
    dw 0xFFFF, 0xFFFF   ; 0x1004–0x1007 padding
isr_high_entry:         ; 0x1008 — HIGH-PRIORITY ISR (all interrupts)
    movff FSR2L, isr_save_fsr2l
    movff FSR2H, isr_save_fsr2h
    call  main_isr_dispatch, 0x1
app_init:               ; 0x1014 — shifts freely
    goto main_flash_service
isr_low_stub:           ; 0x1018 — LOW-PRIORITY ISR (dead, safety stub)
    retfie 0
    ; Everything after 0x101A shifts freely
```

### Flash memory constraint

PIC18F2455 has **24KB flash** (0x0000–0x5FFF).  Preset A occupies
0x5600–0x5FFF (flash ceiling).  Cannot move.

---

## Phase 1: Infrastructure

### 1A. Path constants

Add to `src/dlcp_fw/paths.py`:
```python
V31_MAIN_HEX = FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V3.1.hex"
V31_MAIN_ASM = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v31.asm"
```

### 1B. Pytest fixture

Add to `tests/sim/conftest.py`:
```python
@pytest.fixture(scope="session")
def v31_main_hex() -> Path:
    if not V31_MAIN_HEX.exists():
        raise RuntimeError(f"missing V3.1 main HEX: {V31_MAIN_HEX}")
    return V31_MAIN_HEX
```

### 1C. Test file — `tests/sim/test_v31_v163b_robustness.py`

Replicate all 5 tests from `test_v27_v163b_robustness.py` using
`V31_MAIN_HEX` and `PATCHED_CONTROL_HEX_V163B`.  No xfails.

The tests use `main_serial_mailbox_hooks_dynamic(symbols)` for gpsim
overlays, where `symbols` comes from `parse_gpasm_symbols()` on the
V3.1 listing file.  This is the same pattern as the shift test.

### 1D. Build and assemble

Use the existing `assemble_v30()` helper from `v30_symbols.py` (it
works for any PIC18F2455 .asm, not just V3.0):

```python
from dlcp_fw.sim.v30_symbols import assemble_v30, parse_gpasm_symbols
from dlcp_fw.paths import V31_MAIN_ASM, V31_MAIN_HEX

assemble_v30(V31_MAIN_ASM, V31_MAIN_HEX, output_lst=V31_MAIN_ASM.with_suffix(".lst"))
symbols = parse_gpasm_symbols(V31_MAIN_ASM.with_suffix(".lst"))
```

Or as a local throwaway shell script (`scripts/build_v31.sh` was a planning
example and is not committed in the current tree):
```bash
#!/bin/bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ASM="$PROJECT_DIR/src/dlcp_fw/asm/dlcp_main_v31.asm"
OUT="$PROJECT_DIR/firmware/patched/releases/DLCP_Firmware_V3.1.hex"
gpasm -p18f2455 -I "$(dirname "$ASM")" -o "$OUT" "$ASM"
echo "Built: $OUT"
echo "Listing: ${ASM%.asm}.lst"
```

---

## Phase 2: Create V3.1 ASM Source

### 2A. Start from V3.0 commented source

```bash
cp src/dlcp_fw/asm/dlcp_main_v30_comments.asm src/dlcp_fw/asm/dlcp_main_v31.asm
```

This is the canonical source: zero auto-labels, 132 function headers,
semantic names throughout, `string_desc_ptr_table` already uses
label-relative `db` (from shift test fix).  All TBLPTR loads already
use `LOW(label)` / `HIGH(label)` / `UPPER(label)`.

### 2B. RAM include additions

Add to `dlcp_main_ram.inc` (or a V3.1-specific include):
```asm
; V3.1 named RAM additions
dsp_fault_flags         EQU  0x07F   ; bit2=ACKSTAT, bit6=DSP ping, bits[5:3]=retry
boot_flags              EQU  0x07E   ; bit7=boot-complete (gates PEN timeout)
timeout_lo              EQU  0x00B   ; bounded wait countdown low byte
timeout_hi              EQU  0x00C   ; bounded wait countdown high byte
```

### 2C. USB version update

In the USB string descriptor data area, change the version bytes:
- Major: `0x32` ('2') → `0x33` ('3')
- Minor: `0x33` ('3') → `0x31` ('1')

So the USB-reported version becomes "3.1".

---

## Phase 2D: Inline Function Enhancements

Each enhanced function is modified **in-place** in the V3.0 source.
The stock function body is replaced with the enhanced version.
Surrounding functions are untouched and shift naturally.

### Enhanced: `i2c_byte_tx` (stock function_056)

**Stock behavior**: Writes SSPBUF, checks WCOL, waits SSPIF (unbounded),
reads BF, calls i2c_wait_bus_idle (unbounded).  No ACKSTAT check.

**V3.1 behavior**: Same logic but with bounded SSPIF wait, bounded BF
wait, bounded idle wait, ACKSTAT latch on exit, and two-strike recovery.

```asm
i2c_byte_tx:
    movff   WREG, saved_w
    movwf   SSPBUF, ACCESS
    btfsc   SSPCON1, WCOL, ACCESS
    bra     i2c_byte_tx_wcol
    ; Bounded SSPIF wait
    call    wait_sspif_bounded
    bc      i2c_byte_tx_timeout
    ; BF drain path (stock mode_bf logic)
    btfss   SSPSTAT, BF, ACCESS
    bra     i2c_byte_tx_post_bf
    movf    SSPBUF, W, ACCESS       ; drain
i2c_byte_tx_post_bf:
    ; MSSP idle wait
    call    wait_mssp_idle_bounded
    bc      i2c_byte_tx_timeout
    ; Fix A: ACKSTAT check
    btfsc   SSPCON2, ACKSTAT, ACCESS
    bsf     dsp_fault_flags, 2, BANKED
    return
i2c_byte_tx_wcol:
    bcf     SSPCON1, WCOL, ACCESS
    movf    saved_w, W, ACCESS
    movwf   SSPBUF, ACCESS
    call    wait_sspif_bounded
    bc      i2c_byte_tx_timeout
    call    wait_mssp_idle_bounded
    bc      i2c_byte_tx_timeout
    btfsc   SSPCON2, ACKSTAT, ACCESS
    bsf     dsp_fault_flags, 2, BANKED
    return
i2c_byte_tx_timeout:
    call    recover_mssp
    call    wait_sspif_bounded
    bc      hard_reset_jump
    call    wait_mssp_idle_bounded
    bc      hard_reset_jump
    btfsc   SSPCON2, ACKSTAT, ACCESS
    bsf     dsp_fault_flags, 2, BANKED
    return
hard_reset_jump:
    goto    hard_reset
```

### Enhanced: `uart_tx_byte_blocking` (stock function_111)

**Stock**: Saves W, writes TXREG, spins on TXSTA.TRMT (unbounded).

**V3.1**: Bounded TRMT wait, two-strike recovery.

```asm
uart_tx_byte_blocking:
    movff   WREG, ram_0x003
    movwf   TXREG, ACCESS
    call    wait_trmt_bounded
    bc      uart_tx_timeout
    return
uart_tx_timeout:
    call    recover_uart
    call    wait_trmt_bounded
    bc      hard_reset_jump
    return
```

### Enhanced: `i2c_wait_bus_idle` (stock function_113)

**Stock**: Polls SSPCON2[4:0]==0 && SSPSTAT.R==0, unbounded.

**V3.1**: Bounded version with recovery.

```asm
i2c_wait_bus_idle:
    call    wait_mssp_idle_bounded
    bc      i2c_idle_timeout
    return
i2c_idle_timeout:
    call    recover_mssp
    call    wait_mssp_idle_bounded
    bc      hard_reset_jump
    return
```

### Enhanced: `i2c_tas3108_reg1f_write` (stock function_072)

**Stock**: START, 0x68, 0x1F, 0x00×3, data, STOP — all unbounded.

**V3.1**: Same I2C sequence but using bounded `i2c_byte_tx` (which
now has built-in timeouts) and bounded SEN/PEN waits.

### Enhanced: `i2c_tas3108_coeff_write` (stock function_081)

Contains the PEN busy-wait at stock label_572.

**V3.1 Fix F**: Replace the stock `btfss SSPCON2,PEN / return / bra`
loop with a boot-gated bounded PEN wait:

```asm
    ; Inside i2c_tas3108_coeff_write, at the PEN wait site:
    btfss   boot_flags, 7, ACCESS   ; boot complete?
    bra     .pen_stock              ; no → stock unbounded (safe during boot)
    call    wait_pen_bounded
    bc      .pen_timeout
    bra     .pen_done
.pen_timeout:
    call    recover_mssp
    bsf     dsp_fault_flags, 6, BANKED
    bra     .pen_done
.pen_stock:
    btfss   SSPCON2, PEN, ACCESS
    bra     .pen_done
    bra     .pen_stock
.pen_done:
    ; continue with rest of function
```

### Enhanced: `i2c_secondary_dev_write` (stock function_093)

**V3.1**: Same I2C sequence (START, 0xE2, reg, data, STOP) but using
bounded waits via `i2c_byte_tx` and bounded SEN/PEN waits.

### Enhanced: volume_cmd_handler (stock label_171)

**Fix B hook**: Replace stock `call i2c_tas3108_coeff_write` at the
volume write site with `call volume_dsp_write`.

**Fix B'**: NOP out the premature `movff` sequence that copies
computed_volume to logical_volume BEFORE the I2C write.

### Enhanced: cmd_dispatch_xor_chain (stock label_185)

**V2.4**: Add `cmd=0x20` case in the XOR dispatch chain.  When
`cmd XOR 0x1F == 0` (i.e. cmd=0x1F is the last stock case), add
a new `xorlw 0x01; bz preset_select_handler` to catch cmd=0x20.

### Enhanced: flash_write / flash_erase / flash_read

**V2.4**: Add preset-aware prologues that check `active_flags.2`
(preset B active) and remap TBLPTR high byte from 0x56–0x5F to
0x4A–0x53 when preset B is active.  This is the function prologue,
not a `goto patch_region`.

### Enhanced: filename boot load (near label_20BE area)

**V2.4**: At the boot filename load site, add preset-aware EEPROM
base selection (0x60 for preset A, 0x83 for preset B).

---

## Phase 2E: New Functions

These are genuinely new functions that don't exist in stock.  They are
placed **after the last stock function** in the natural code flow,
before the erased-flash fill and preset tables.

### `volume_dsp_write` (Fix B + B' + V2.7 recovery)

```asm
volume_dsp_write:
    bcf     dsp_fault_flags, 2, BANKED  ; clear ACKSTAT latch
    call    i2c_tas3108_coeff_write     ; I2C write (uses enhanced i2c_byte_tx)
    btfsc   dsp_fault_flags, 2, BANKED  ; NACKed?
    bra     .nacked

    ; Success: clear dirty, mark boot complete, commit volume, report
    movlb   0x0
    bcf     boot_flags, 3, BANKED       ; clear volume dirty
    bsf     boot_flags, 7, BANKED       ; boot-complete gate
    movff   computed_volume, logical_volume
    movff   computed_volume_1, logical_volume_1
    movff   computed_volume_2, logical_volume_2
    movff   computed_volume_3, logical_volume_3
    movlw   0x07
    andwf   dsp_fault_flags, F, BANKED  ; clear retry counter
    call    send_dsp_fault_status
    return

.nacked:
    movlw   0x08
    addwf   dsp_fault_flags, F, BANKED  ; bump retry [5:3]
    movf    dsp_fault_flags, W, BANKED
    andlw   0x38
    sublw   0x28                         ; 5 retries?
    bc      .retry_ok
    ; Exhausted: bus-clear + ping + report + give up
    call    i2c_bus_clear
    call    dsp_ping
    call    send_dsp_fault_status
    movlb   0x0
    bcf     boot_flags, 3, BANKED
    movlw   0x07
    andwf   dsp_fault_flags, F, BANKED
    return
.retry_ok:
    return                               ; dirty bit stays → main loop retries
```

### `i2c_bus_clear` (Fix C)

9 SCL clocks + manual STOP.  Placed naturally near other I2C functions.

```asm
i2c_bus_clear:
    bcf     SSPCON1, SSPEN, ACCESS      ; release pins to GPIO
    bsf     TRISB, 1, ACCESS            ; SCL input (pulled high)
    bsf     TRISB, 0, ACCESS            ; SDA input (pulled high)
    movlw   0x09
    movwf   timeout_lo, ACCESS
.clk_loop:
    bcf     TRISB, 1, ACCESS            ; SCL low
    bcf     LATB, 1, ACCESS
    nop
    nop
    bsf     TRISB, 1, ACCESS            ; SCL high
    nop
    nop
    btfsc   PORTB, 0, ACCESS            ; SDA released?
    bra     .stop
    decfsz  timeout_lo, F, ACCESS
    bra     .clk_loop
.stop:
    bcf     TRISB, 0, ACCESS            ; SDA output
    bcf     LATB, 0, ACCESS             ; SDA low
    nop
    bsf     TRISB, 1, ACCESS            ; SCL high
    nop
    nop
    bsf     TRISB, 0, ACCESS            ; SDA high = STOP condition
    movlw   0x28                         ; I2C master + SSPEN
    movwf   SSPCON1, ACCESS
    return
```

### `dsp_ping` (Fix D)

```asm
dsp_ping:
    bsf     SSPCON2, SEN, ACCESS
    call    wait_sen_bounded
    bc      .nack
    movlw   0x68                         ; TAS3108 write address
    call    i2c_byte_tx
    bsf     SSPCON2, PEN, ACCESS         ; STOP
    btfss   SSPCON2, ACKSTAT, ACCESS
    bcf     dsp_fault_flags, 6, BANKED   ; ACK → clear fault
    btfsc   SSPCON2, ACKSTAT, ACCESS
.nack:
    bsf     dsp_fault_flags, 6, BANKED   ; NACK → set fault
    return
```

### `send_dsp_fault_status` (Fix E)

```asm
send_dsp_fault_status:
    movlb   0x00
    movf    dsp_fault_flags, W, BANKED
    andlw   0x44                         ; bits 6 + 2
    movwf   ram_0x003, ACCESS
    movlw   0xBF
    call    uart_tx_byte_blocking
    movlw   0x08
    call    uart_tx_byte_blocking
    movf    ram_0x003, W, ACCESS
    call    uart_tx_byte_blocking
    return
```

### Bounded Wait Helpers

Shared timeout infrastructure using 16-bit countdown:

```asm
wait_seed:
    movlw   0x00
    movwf   timeout_lo, ACCESS
    movlw   0x10
    movwf   timeout_hi, ACCESS
    return

wait_tick:
    decfsz  timeout_lo, F, ACCESS
    return
    decfsz  timeout_hi, F, ACCESS
    return
    bsf     STATUS, C, ACCESS           ; Carry = timeout
    return

wait_sspif_bounded:
    call    wait_seed
.loop:
    btfsc   PIR1, SSPIF, ACCESS
    bra     .done
    call    wait_tick
    bnc     .loop
    return                               ; C=1: timed out
.done:
    bcf     PIR1, SSPIF, ACCESS
    bcf     STATUS, C, ACCESS            ; C=0: success
    return

wait_trmt_bounded:
    call    wait_seed
.loop:
    btfsc   TXSTA, TRMT, ACCESS
    bra     .done
    call    wait_tick
    bnc     .loop
    return
.done:
    bcf     STATUS, C, ACCESS
    return

wait_mssp_idle_bounded:
    call    wait_seed
.loop:
    movf    SSPCON2, W, ACCESS
    andlw   0x1F
    bnz     .tick
    btfsc   SSPSTAT, R_NOT_W, ACCESS
    bra     .tick
    bcf     STATUS, C, ACCESS
    return
.tick:
    call    wait_tick
    bnc     .loop
    return

wait_sen_bounded:
    call    wait_seed
.loop:
    btfss   SSPCON2, SEN, ACCESS
    bra     .done
    call    wait_tick
    bnc     .loop
    return
.done:
    bcf     STATUS, C, ACCESS
    return

wait_pen_bounded:
    call    wait_seed
.loop:
    btfss   SSPCON2, PEN, ACCESS
    bra     .done
    call    wait_tick
    bnc     .loop
    return
.done:
    bcf     STATUS, C, ACCESS
    return

wait_bf_bounded:
    call    wait_seed
.loop:
    btfss   SSPSTAT, BF, ACCESS
    bra     .done
    call    wait_tick
    bnc     .loop
    return
.done:
    bcf     STATUS, C, ACCESS
    return
```

### Recovery Helpers

```asm
recover_mssp:
    call    mssp_hard_reset              ; stock function_101
    return

recover_uart:
    call    uart_config                  ; stock function_083
    return
```

### Preset Select Handler (V2.4)

```asm
preset_select_handler:
    ; cmd=0x20 data in WREG: 0=preset A, 1=preset B
    btfsc   STATUS, Z, ACCESS
    bra     .select_a
    bsf     active_flags, 2, ACCESS     ; preset B
    bra     .apply
.select_a:
    bcf     active_flags, 2, ACCESS     ; preset A
.apply:
    ; trigger DSP table re-apply and filename swap
    ; [details from V2.4 cmd_tail_patch logic]
    return
```

---

## Phase 2F: Preset Tables and Tail

After all code, emit erased fill and preset tables.  Preset A MUST
stay at `org 0x5600` (flash ceiling, 24KB PIC18F2455).

```asm
    ; Erased flash padding to preset B
    fill    0xFFFF, (0x4A00 - $)

    org     0x4A00
preset_table_b:
    ; 2560 bytes — clone of preset A data (same dw values)
    dw  ...

    ; Erased flash padding to preset A
    fill    0xFFFF, (0x5600 - $)

    org     0x5600
preset_table_a:
    ; 2560 bytes — stock preset A data (pinned to flash ceiling)
    dw  ...
```

The flash bank remap in function_025/054/061 prologues translates
TBLPTR high byte: `0x56` ↔ `0x4A` when preset B is active.  These
use `HIGH(preset_table_a)` and `HIGH(preset_table_b)` respectively.

**Code space budget**: If code grows beyond 0x49FF, it collides with
preset B at 0x4A00.  The 512B gap at 0x5400–0x55FF is available as
overflow if needed (matching the V2.5 patch region layout).

---

## Phase 3: gpsim Simulation (uses existing infrastructure)

The shift test already built the dynamic manifest infrastructure.
V3.1 reuses it directly — no new manifest code needed.

### 3A. Assemble and extract symbols

```python
from dlcp_fw.sim.v30_symbols import assemble_v30, parse_gpasm_symbols

assemble_v30(V31_MAIN_ASM, V31_MAIN_HEX,
             output_lst=V31_MAIN_ASM.with_suffix(".lst"))
symbols = parse_gpasm_symbols(V31_MAIN_ASM.with_suffix(".lst"))
```

### 3B. Build dynamic overlay

```python
from dlcp_fw.sim.manifests import (
    main_reset_to_appstart,
    main_serial_mailbox_hooks_dynamic,
)

overlay = main_serial_mailbox_hooks_dynamic(symbols)
```

This templates the same mailbox/timer/MSSP overlay ASM with V3.1's
shifted function addresses.  The `run_main_mailbox_gpsim()` function
accepts `overlay_manifests=[overlay]` to inject the custom overlay.

### 3C. Seeder: no change needed

`build_seeded_main_sim_hex()` copies 0x1000–0x5600 from the app hex.
Preset A stays at 0x5600.  Preset B at 0x4A00 is within the copy
range.  No constant changes needed.

---

## Phase 4: Assemble and Test

1. Assemble: `assemble_v30(V31_MAIN_ASM, V31_MAIN_HEX)`
2. Extract symbols: `parse_gpasm_symbols(lst_path)`
3. Build overlay: `main_serial_mailbox_hooks_dynamic(symbols)`
4. Run tests: `.venv_ep0/bin/python -m pytest tests/sim/test_v31_v163b_robustness.py -v`
5. Iterate on failures

---

## Phase 5: Verification

After the 5 robustness tests pass:
- Config bits byte-identical to stock
- EEPROM byte-identical to stock (preset B filename slot at 0x83–0xA0 may differ)
- Preset A table byte-identical to stock
- Preset B table byte-identical to preset A
- USB version reports "3.1"
- No boot block emitted
- App entry at 0x1000, ISR at 0x1008
- `retfie 0` safety stub at 0x1018
- Source has no `goto *_patch` redirects
- Source has no `org` within the code body (only 0x1000, 0x4A00, 0x5600,
  0xF00000, config)

---

## Key Reference Files

| What | Path |
|------|------|
| V3.0 commented source (start point) | `src/dlcp_fw/asm/dlcp_main_v30_comments.asm` |
| V3.0 RAM include | `src/dlcp_fw/asm/dlcp_main_ram.inc` |
| Symbol parser + assembly helper | `src/dlcp_fw/sim/v30_symbols.py` |
| Dynamic manifest builder | `src/dlcp_fw/sim/manifests.py` (`main_serial_mailbox_hooks_dynamic`) |
| gpsim overlay injection | `src/dlcp_fw/sim/main_gpsim.py` (`overlay_manifests` param) |
| V2.5 patch ASM (reference) | `src/dlcp_fw/patch/build_main_presets_ab.py` (`_PATCH_ASM_V25`) |
| V2.6 DSP fixes (reference) | same file (`_V26_056_CORE`, `_V26_DSP_FIXES`) |
| V2.7 I2C fixes (reference) | same file (`_V27_I2C_FIXES`, `_V27_REPACKED_REGION`) |
| V2.7 test file (model for V3.1) | `tests/sim/test_v27_v163b_robustness.py` |
| V1.63b CONTROL hex | `firmware/patched/releases/DLCP_Control_V1.63b.hex` |
| Shift test (proves relocation) | `tests/sim/test_v30_relocation.py` |

---

## Constraints

- Python: `.venv_ep0/bin/python`
- gpasm: `/opt/homebrew/bin/gpasm` 1.5.2
- gpasm default radix is hex — use `0x` prefix for all numeric literals
- No binary patching — pure source edits
- No `goto *_patch` hooks — functions are enhanced in-place
- No `org` within the code body — only structural anchors (0x1000, 0x4A00, 0x5600, 0xF00000, config)
- Entry block (0x1000–0x1019) is fixed — 0x1000, 0x1008, 0x1018 are boot-block-pinned
- PIC18F2455 = 24KB flash (0x0000–0x5FFF) — preset A pinned to flash ceiling
- `string_desc_ptr_table` MUST use label-relative `db` (shift test requirement)
- V3.1 pairs with V1.63b CONTROL (already built)
- V3.1 pairs with V1.63b CONTROL (already built)
- Data regions (config, EEPROM, preset A) byte-identical to stock
- Preset B is a clone of preset A
- gpsim overlays updated for V3.1 addresses
