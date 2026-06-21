# V3.5 TBLPTR EEPROM Walker Bugfix IMPL

Date: 2026-06-21

Source docs:

- `docs/MEMORY_CORRUPTION_INSTRUMENTATION_SPEC.md`
- `docs/MEMORY_CORRUPTION_INSTRUMENTATION_IMPL.md`
- `docs/IMPL_V35_FILENAME_EEPROM_NUL_REPRO.md` for historical contrast with the earlier fixed IRQ-vector filename bug

## Status

Implemented in canonical V3.5 release rev `0x0090`.  This IMPL targets the
rev `0x008F` recurrence where V1.73 + V3.5 could rewrite preset-B filename
EEPROM byte `0x8F` from `0x31` to `0x00` after a clean firmware-path repair.

## Implementation Closeout

Changed `src/dlcp_fw/asm/dlcp_main_v35.asm` only for MAIN behavior.  CONTROL
was not changed for this bugfix.

The static EEPROM block walker now calls
`eeprom_persist_static_record_write_if_changed`, a local helper that:

- stages `ram_0x007` into EEADR through `eeprom_read_byte`
- compares the current EEPROM byte with the desired byte in `ram_0x009`
- tail-calls `eeprom_write_blocking` only when changed
- never calls `chain_copy`
- does not touch `TBLPTR`

Canonical build:

```bash
.venv_ep0/bin/python scripts/build_v35_release.py
# built canonical V3.5 release: firmware/patched/releases/DLCP_Firmware_V3.5.hex (release rev 0x008F -> 0x0090)
```

Listing proof from `src/dlcp_fw/asm/dlcp_main_v35.lst`:

- `eeprom_persist_block_walker`: `0x20E4`
- walker record write call: `0x210A rcall eeprom_persist_static_record_write_if_changed`
- `eeprom_persist_static_record_write_if_changed`: `0x211E`
- `eeprom_persist_static_records`: `0x2134`
- generic `eeprom_write_byte_if_changed`: `0x3C30`, still owns the shared
  `chain_copy` path for callers that do not hold `TBLPTR` live

Net source-level code-size delta for this bugfix is `+10` program words:
removed one `clrf` in the walker and added an 11-word local helper.

Clean replay artifact:

- `artifacts/reanalysis/memory_corruption/20260621T160440Z_v173-v35-live-like_00350173/`

The clean trace reports 3537 trace records, `overflowed=False`, `dropped=0`,
first violation `none`, and corrupt preset-B units `none`.

## Where The Bug Is Documented

The primary root-cause writeup is in
`docs/MEMORY_CORRUPTION_INSTRUMENTATION_SPEC.md`, section
"2026-06-21 Simulator Finding".  The implementation closeout in
`docs/MEMORY_CORRUPTION_INSTRUMENTATION_IMPL.md` records the same evidence and
artifact path.

Key documented evidence:

- first protected writer: MAIN0 `EepromArm`
- bad byte: EEPROM `0x8F` (`preset_filename_eeprom_b + 0x0C`)
- value: `0x31 -> 0x00`
- PC: `0x3984`, `nvm_unlock_and_set_wr`, `bsf EECON1.WR`
- stack: `run_main_foreground_loop -> run_main_service_pass ->
  persist_dirty_runtime_state_to_eeprom -> eeprom_persist_block_walker ->
  eeprom_write_blocking`
- artifact:
  `artifacts/reanalysis/memory_corruption/20260621T145830Z_v173-v35-live-like_00350173/`

The current failing prevention gate is
`tests/sim/test_memory_corruption_instrumentation.py::test_v173_v35_filename_eeprom_guard_rejects_runtime_writes_after_repair`.

## Root Cause

`eeprom_persist_block_walker` reads a packed `(eeprom_offset, ram_src)` table
with `TBLRD*+` and keeps the table cursor live in `TBLPTR` while it calls
`eeprom_write_byte_if_changed`.

That helper can take the changed-byte path:

```asm
eeprom_write_byte_if_changed:
    ...
    rcall       chain_copy_call_range_trampoline_mid
    db          0x00, 0x00, eeprom_addr_or_float32_pack_tail_operand_op, addr_low_counter_or_payload_scratch_operand, 0x03, 0xFF
    bra         eeprom_write_blocking
```

`chain_copy` is explicitly documented as clobbering `TBLPTR`.  After the first
changed static record, the walker resumes `tblrd*+` from the chain-copy
descriptor/resume cursor instead of `eeprom_persist_static_records`, so it can
consume bogus offset/data pairs and write into the filename EEPROM slot.

CONTROL is only the stimulus source.  The writer is MAIN firmware.

## Implementation Plan

### 1. Patch Only The V3.5 MAIN Walker

Edit `src/dlcp_fw/asm/dlcp_main_v35.asm`.

Do not change CONTROL and do not change the shared
`eeprom_write_byte_if_changed` helper globally unless implementation evidence
proves the local fix is impossible.

Preferred patch: replace the single call from
`eeprom_persist_block_walker` to
`eeprom_write_byte_if_changed_rcall_trampoline` with a local helper that does a
plain EEPROM read/compare/write and never touches `TBLPTR`.

Sketch:

```asm
    ; record setup already did:
    ;   computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch = EEPROM offset
    ;   eeprom_or_filename_data_or_flash_buffer_ptr_low_or_signature_low = new byte
    rcall       eeprom_persist_static_record_write_if_changed

eeprom_persist_static_record_write_if_changed:
    movff       computed_volume_or_flash_count_eeprom_addr_adc_usb_ptr_scratch_phys, addr_low_counter_or_payload_scratch_phys
    rcall       eeprom_read_byte
    xorwf       eeprom_or_filename_data_or_flash_buffer_ptr_low_or_signature_low_phys, W, ACCESS
    bz          eeprom_persist_static_record_write_if_changed__return
    movff       eeprom_or_filename_data_or_flash_buffer_ptr_low_or_signature_low_phys, saved_w_b0_phys
    bra         eeprom_write_blocking
eeprom_persist_static_record_write_if_changed__return:
    return      0
```

Remove the now-unneeded `clrf flash_end_high_or_loop_mask_scratch_byte` in the
walker if the local helper does not use EEPROM high address staging.

Rationale:

- `eeprom_read_byte` and `eeprom_write_blocking` do not use `TBLPTR`.
- No `TBLPTR` save area is needed, so there is no interrupt-window risk from
  restoring scratch after `eeprom_write_blocking` re-enables GIE.
- The fix is local to the only proven bad live-`TBLPTR` call site.

### 2. Preserve Or Improve Code Size

After assembling, inspect `src/dlcp_fw/asm/dlcp_main_v35.lst` around:

- `eeprom_persist_block_walker`
- `eeprom_persist_static_record_write_if_changed`
- `eeprom_write_byte_if_changed`
- `chain_copy`

Record the net program-word delta in this IMPL.  The expected cost is small:
one local helper plus a removed high-byte clear, with no broad helper contract
change.

### 3. Update Tests For Fixed Behavior

The current positive-repro test should stop requiring corruption after the
firmware fix:

- update or replace
  `test_v173_v35_live_like_churn_reproduces_preset_b_0x8f_nul` so it still
  verifies the live-like stimulus and filename query traffic, but asserts no
  protected write and a clean final preset-B slot.
- keep
  `test_v173_v35_filename_eeprom_guard_rejects_runtime_writes_after_repair` as
  the prevention gate.
- keep direct MAIN-only and CONTROL+single-MAIN isolation tests green.

If historical pre-fix evidence is still useful, preserve it in docs/artifacts,
not as a passing test that requires the bug.

### 4. Rebuild Canonical V3.5

Run:

```bash
.venv_ep0/bin/python scripts/build_v35_release.py
```

This should bump the V3.5 release metadata and update the canonical
`firmware/patched/releases/DLCP_Firmware_V3.5.hex`.

Do not change V3.4 unless explicitly requested; V3.4 is historical.

### 5. Required Validation

Minimum focused gate:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_memory_corruption_instrumentation.py::test_v173_v35_filename_eeprom_guard_rejects_runtime_writes_after_repair
.venv_ep0/bin/python -m pytest -q tests/sim/test_memory_corruption_instrumentation.py
.venv_ep0/bin/python scripts/memory_corruption_trace.py --expect-clean
```

Regression and build gates:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_filename_eeprom_nul_repro.py
.venv_ep0/bin/python -m pytest -q tests/sim/test_ram_bank_safety.py
.venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35 --target control-v173
.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_v173_release_builders.py
.venv_ep0/bin/python -m pytest -q tests/sim/test_firmware_version_label.py::test_v35_usb_and_eeprom_version_match_release_identity
.venv_ep0/bin/python -m pytest -q tests/sim/test_v172_v33_diag_identity.py::test_v35_cmd25_identity_handler_emits_16bit_revision_nibbles
.venv_ep0/bin/python -m pytest -q tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_diag_ok_title_shows_visible_main_identity
```

If time allows:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

### Validation Results

Run after rebuilding canonical V3.5 rev `0x0090`:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_memory_corruption_instrumentation.py::test_v173_v35_filename_eeprom_guard_rejects_runtime_writes_after_repair
# 1 passed in 53.17s

.venv_ep0/bin/python -m pytest -q tests/sim/test_memory_corruption_instrumentation.py
# 8 passed in 164.26s

.venv_ep0/bin/python scripts/memory_corruption_trace.py --expect-clean
# first violation: none; corrupt preset-B units: none; overflowed: False dropped=0

.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_filename_eeprom_nul_repro.py tests/sim/test_ram_bank_safety.py
# 23 passed in 59.98s

.venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35 --target control-v173
# RAM bank safety: OK (main-v35, control-v173)

.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_v173_release_builders.py tests/sim/test_firmware_version_label.py::test_v35_usb_and_eeprom_version_match_release_identity tests/sim/test_v172_v33_diag_identity.py::test_v35_cmd25_identity_handler_emits_16bit_revision_nibbles tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_diag_ok_title_shows_visible_main_identity
# 11 passed in 21.17s
```

The full `tests/sim -n 16 -q` optional gate was not run in this work unit.

## Deployment Boundary

Do not flash live hardware in this implementation task unless the user asks.

After a fixed build is flashed, remember that firmware cannot prove whether
already-corrupted EEPROM has been repaired.  Existing bad filename EEPROM
still needs the release flash overlay path or the documented surgery/repair
path, followed by readback.

## Review Ledger

Eight independent review passes were applied to this IMPL:

1. Evidence/root-cause: traced the live recurrence to MAIN `EepromArm` at
   `0x3984`; rejected CONTROL as direct writer.
2. Assembly call graph: confirmed the live stack reaches
   `eeprom_persist_block_walker` and then `eeprom_write_byte_if_changed`.
3. `TBLPTR` contract: confirmed `chain_copy` declares `TBLPTR` clobbered,
   making the walker's live cursor invalid after changed-byte writes.
4. Interrupt-window safety: rejected a blind `TBLPTR` RAM save/restore as the
   first choice because `eeprom_write_blocking` can restore GIE before caller
   scratch restoration.
5. Code-size review: selected a small local no-`TBLPTR` write-if-changed helper
   instead of broad helper contract changes.
6. Test design: identified the existing failing guard and the positive-repro
   test that must be converted to fixed-behavior coverage.
7. Release process: scoped rebuild to canonical V3.5 and retained V3.4 as a
   historical line.
8. Operator safety: separated firmware bugfix from live EEPROM repair and
   avoided any default hardware flashing.

No high or medium review findings remain open.  The only implementation
caveat is to verify the local helper's assembled listing and net size before
declaring the release complete.

## Handoff Goal Prompt

The following `/goal` prompt is 2441 characters, counted with Python `len()`:

```text
/goal Implement the V3.5 MAIN TBLPTR EEPROM-walker bugfix from docs/IMPL_V35_TBLPTR_EEPROM_WALKER_BUGFIX.md.

Required reads: AGENTS.md, CODING_STYLE.md, docs/MEMORY_CORRUPTION_INSTRUMENTATION_SPEC.md section "2026-06-21 Simulator Finding", docs/MEMORY_CORRUPTION_INSTRUMENTATION_IMPL.md "Implementation Closeout", docs/IMPL_V35_TBLPTR_EEPROM_WALKER_BUGFIX.md, src/dlcp_fw/asm/dlcp_main_v35.asm around persist_dirty_runtime_state_to_eeprom/eeprom_persist_block_walker/eeprom_write_byte_if_changed/chain_copy, tests/sim/test_memory_corruption_instrumentation.py, tests/sim/memory_corruption_helpers.py.

Bug: V3.5 MAIN keeps the packed EEPROM-persist table cursor in TBLPTR while eeprom_persist_block_walker calls eeprom_write_byte_if_changed. On changed bytes that helper reaches chain_copy, whose contract clobbers TBLPTR. The walker then resumes tblrd*+ from the wrong cursor and can write bogus EEPROM pairs including preset-B filename EEPROM 0x8F <- 0x00. CONTROL is stimulus only.

Implement the local fix in src/dlcp_fw/asm/dlcp_main_v35.asm: replace the walker call to eeprom_write_byte_if_changed_rcall_trampoline with a local static-record write-if-changed helper that stages EEADR from the record offset, calls eeprom_read_byte, compares W with the staged new byte, and tail-calls eeprom_write_blocking only when changed. The helper must not call chain_copy and must not touch TBLPTR. Do not make broad CONTROL changes. Do not change V3.4 unless explicitly redirected.

Update tests so the live-like churn case asserts fixed behavior: filename-query traffic is still observed, no protected writes occur after clean repair, trace does not drop/overflow, and MAIN0/MAIN1 preset-B EEPROM slots remain clean. Keep the guard test test_v173_v35_filename_eeprom_guard_rejects_runtime_writes_after_repair as the prevention gate.

Run scripts/build_v35_release.py, inspect the listing around the walker/helper, record net size/revision in the IMPL, then validate:
.venv_ep0/bin/python -m pytest -q tests/sim/test_memory_corruption_instrumentation.py
.venv_ep0/bin/python scripts/memory_corruption_trace.py --expect-clean
.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_filename_eeprom_nul_repro.py tests/sim/test_ram_bank_safety.py
.venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35 --target control-v173
Run the V3.5 identity/release-builder focused tests listed in the IMPL. Do not flash hardware unless asked.
```
