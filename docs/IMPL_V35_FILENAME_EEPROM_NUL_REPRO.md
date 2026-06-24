# V3.5 Filename EEPROM NUL Regression - Bug Repro IMPL

Date: 2026-06-19
Status: Fixed in V3.5 release rev 0x0085; repro evidence retained
Source spec: live user incident and HID probe evidence from 2026-06-19
Scope: reproduce, localize, and close out the persistent preset filename NUL corruption in simulation and the V3.5 release artifact.

Note: the reproduction sections below preserve the original pre-fix evidence, including strict-xfail results and the `/goal` prompt used to localize the bug. The fix closeout records the post-fix state.

## Requirements

Goal: create a deterministic sim repro and diagnosis for the bug where V3.5 MAIN persists non-filename bytes, including `0x00`, inside preset filename EEPROM slots, causing V1.73 CONTROL Preset LCD scrolling to stop after power cycle or preset/menu churn.

User decisions:

- The bug was not present in the pre-size-optimization line; treat this as a size-saving regression unless evidence disproves it.
- Do not "fix" by rewriting live EEPROM slots first. Preserve evidence and find the writer.
- Produce a `/goal` prompt under 4000 characters for the actual reproduction/root-cause exploration.

Original non-goals during the reproduction phase:

- Do not chase CONTROL LCD rendering until MAIN EEPROM slots are proven clean.
- Do not broaden into unrelated V3.5 release cleanup.

## Docs Read

- `AGENTS.md`: canonical paths, V3.5/V1.73 release ownership, `tests/sim -n 16 -q` gate.
- `README.md`: current V3.5/V1.73 operator path and release-flash commands.
- `CODING_STYLE.md`: MAIN asm style and verification rules.
- `docs/SIMULATION.md`: Rust sim is the only backend; full sim gate is `.venv_ep0/bin/python -m pytest tests/sim -n 16 -q`.
- `docs/TEST_SIMULATOR.md`: historical, stale gpsim-era context; not authoritative over `docs/SIMULATION.md`.
- `docs/V34_FIELD_BUGS_20260610.md`: FIELD-9 adjacent filename RAM corruption and open upstream `rx_ring_wr` writer.
- `docs/V34_SIZE_OPTIMIZATION_FINDINGS.md`: V3.4 size-reclaim context and S/T slice notes; later history check shows `a274dfa` is not the clean baseline for this vector issue.
- `src/dlcp_fw/asm/dlcp_main_v35.lst`: authoritative byte addresses for the app reset/IRQ stub, UART RX ISR, EEPROM writer, and filename persist loop.

## Live Evidence

HID-only probe on two connected V3.5 MAINs:

- `DevSrvsID:4296131830`: active RAM A and EEPROM A are correct, `LX521.4 22MG10F-v5`; EEPROM B is `LX521.4 22MG\x000F-v7` with NUL at offset 12.
- `DevSrvsID:4296131878`: active RAM A and EEPROM A are `LX521.4 22MG10\x00-v5` with NUL at offset 14; EEPROM B is `LX521.4 22MG\x000F-v7` with NUL at offset 12.

The local capture metadata is clean:

- `artifacts/LX521.4/LX521.4_22MG10F-v5.json` raw name has no NUL.
- `artifacts/LX521.4/LX521.4_22MG10F-v7.json` raw name has no NUL.

Diagnosis: this is persistent MAIN EEPROM corruption, not merely volatile RAM or CONTROL scroll state. V3.5 `cmd26_filename_query_handler` scans only printable bytes; a NUL truncates the reported name length, so CONTROL correctly stops scrolling.

### 2026-06-21 live recurrence and EEPROM surgery baseline

After both MAINs were flashed to current V3.5 `rev 0x8F`, the user still saw
Preset filename corruption on the front panel.  Live USB probes found the
current image was post-fix but the persistent filename EEPROM was still
damaged:

- RIGHT `DevSrvsID:4296299389`
  - active preset before surgery: A
  - cmd `0x03` active RAM before surgery: clean
    `LX521.4 22MG10F-v5`
  - EEPROM A before surgery:
    `4c583532312e3420323200473130462d7635ffffffffffffffffffffffff`
    (`LX521.4 22\x00G10F-v5`)
  - EEPROM B before surgery:
    `4c583532312e342032324d470030462d7637ffffffffffffffffffffffff`
    (`LX521.4 22MG\x000F-v7`)
- LEFT `DevSrvsID:4296299545`
  - active preset before surgery: A
  - cmd `0x03` active RAM before surgery:
    `4c583532312e3420323201473130f82d7635ffffffffffffffffffffffff`
    (`LX521.4 22\x01G10\xf8-v5`)
  - EEPROM A before surgery matched the corrupt active RAM bytes above.
  - EEPROM B before surgery:
    `4c583532312e342032324d470030462d7637ffffffffffffffffffffffff`
    (`LX521.4 22MG\x000F-v7`)

Current V3.5 image checks on the same worktree:

- live MAIN version probe: `V3.5 rev 0x8F`
- merged release bytes:
  - `0x0008: 04 ef 08 f0`, bootloader high interrupt vector to `0x1008`
  - `0x1008: d9 cf 01 f0`, first word of `movff FSR2L,isr_save_fsr2l`
- focused regression:
  `.venv_ep0/bin/python -m pytest -q tests/sim/test_main_boot_vector_abi.py tests/sim/test_v35_filename_eeprom_nul_repro.py`
  -> `7 passed, 1 xfailed`; the xfail is the documented historical V3.4
  vector-layout case.

Interpretation boundary: this recurrence does **not** by itself prove current
V3.5 `rev 0x8F` is still writing bad filename bytes.  At the time of the first
probe, persistent EEPROM already contained the bad bytes.  After the surgery
below, any fresh recurrence on the same current image is much stronger evidence
for a still-active writer bug.

Surgery performed on 2026-06-21:

- Wrote expected A slot `LX521.4 22MG10F-v5` and expected B slot
  `LX521.4 22MG10F-v7` through the normal app cmd `0x03` filename write path.
- Forced the MAIN firmware's own filename EEPROM persist service after each
  active-slot write.
- Restored both MAINs to active preset A.
- Artifacts:
  - `artifacts/probes/live_filename_eeprom_surgery_20260621.json`
  - `artifacts/probes/live_filename_eeprom_left_b_repair2_20260621.json`
  - pre-surgery RAM/EEPROM captures:
    `artifacts/probes/live_eeprom_right_000_0bf.bin`,
    `artifacts/probes/live_eeprom_left_000_0bf.bin`,
    `artifacts/probes/live_ram_right_1f0_30f.bin`,
    `artifacts/probes/live_ram_left_1f0_30f.bin`

The first surgery pass repaired RIGHT A/B and LEFT A.  LEFT B initially
verified clean in the immediate surgery report, then a later direct read still
showed the old `LX521.4 22MG\x000F-v7` byte pattern.  A second, stricter LEFT B
pass wrote B again and verified durability across `B -> A -> B -> A` switching.
This ambiguity is useful: it keeps open the possibility of either an incomplete
first persist/verify sequence or a same-symptom live rewrite.  The final
baseline after the second pass is clean.

Final post-surgery baseline:

- `scripts/dlcp_diag.py` reports both MAIN Config fields as
  `LX521.4 22MG10F-v5`.
- Five sequential HID EEPROM reads report RIGHT and LEFT EEPROM A/B all OK:
  - A:
    `4c583532312e342032324d473130462d7635ffffffffffffffffffffffff`
  - B:
    `4c583532312e342032324d473130462d7637ffffffffffffffffffffffff`
- cmd `0x03` active RAM on both MAINs reports `LX521.4 22MG10F-v5`.
- Both MAINs were restored to active preset A.

### 2026-06-21 post-power-cycle recurrence

After the clean surgery baseline above, the user performed a full power cycle,
toggled A/B several times, changed volume, and navigated the front-panel menus.
Both MAIN USB connections were then read without performing any writes.

Read-only check artifact:
`artifacts/probes/live_filename_eeprom_post_powercycle_check_20260621.json`.

Results:

- `scripts/dlcp_diag.py` still looked clean because both MAINs were active on
  preset A:
  - LEFT `DevSrvsID:4296310320`: Config `LX521.4 22MG10F-v5`, HEALTHY
  - RIGHT `DevSrvsID:4296310231`: Config `LX521.4 22MG10F-v5`, HEALTHY
- Five repeated raw EEPROM reads were stable:
  - RIGHT EEPROM A: OK
  - RIGHT EEPROM B: BAD
    `4c583532312e342032324d470030462d7637ffffffffffffffffffffffff`
    (`LX521.4 22MG\x000F-v7`)
  - LEFT EEPROM A: OK
  - LEFT EEPROM B: BAD
    `4c583532312e342032324d470030462d7637ffffffffffffffffffffffff`
    (`LX521.4 22MG\x000F-v7`)
- In both MAINs the only B-slot diff from expected is offset 12:
  expected `0x31` (`'1'`), got `0x00`.
- cmd `0x03` active RAM remained clean because both MAINs were back on
  active preset A:
  `4c583532312e342032324d473130462d7635ffffffffffffffffffffffff`
  (`LX521.4 22MG10F-v5`).

This materially changes the confidence boundary.  The earlier 2026-06-21
finding could still be explained as stale EEPROM inherited from the pre-fix
image.  This post-surgery recurrence happened after both A/B EEPROM slots had
been verified clean on current V3.5 `rev 0x8F`, so it is strong evidence of a
still-active current-image path that rewrites or mis-persists preset B under
power-cycle / A-B churn.  The writer is not yet proven; the next repro should
focus on preset-B switch/load/persist paths and any boot-time B-slot copy or
dirty-service trigger rather than the already-fixed high-IRQ vector alignment
alone.

## Implementation Evidence

- `src/dlcp_fw/asm/dlcp_main_v35.asm` / `.lst`: `cmd26_filename_query_handler` reads active RAM for the active preset and EEPROM for inactive slots; it stops length scan at non-printable bytes. `preset_persist_filename` copies `0x02C0..0x02DD` to EEPROM base `0x60` or `0x83`. `preset_load_filename` copies EEPROM back to active RAM. `uart_rx_irq_enqueue` already clamps `rx_ring_wr >= 0xC0` before `RCREG -> INDF2`, so the old FIELD-9 adjacent-RAM write is guarded.
- Seeded V3.x MAIN images preserve the stock bootloader high interrupt vector at `0x0008`: bytes `04 EF 08 F0`, i.e. `GOTO 0x1008`.
- Pre-fix V3.5 placed `movff FSR2L,isr_save_fsr2l` at `0x1006`; bytes at `0x1008` were `01 F0 DA CF`, the second word of the FSR2L `MOVFF` plus the first word of `movff FSR2H,isr_save_fsr2h`.
- V3.2 and V3.3 release images have the expected `movff FSR2L` bytes at `0x1008`. V3.4 does not. V3.5 does after the rev `0x0085` fix.
- `src/dlcp_fw/flash/dlcp_main_flash.py`: release finalize writes active filename via HID `cmd 0x03`, forces EEPROM persist, then verifies flash plus EEPROM via HID diag memread.
- `src/dlcp_fw/flash/dlcp_release_flash_common.py`: V3.5 wrapper uses clean local capture sidecars when they are present.
  `scripts/dlcp_v35_release_flash.py --left` forwards
  `--capture-a artifacts/LX521.4/LX521.4_22MG10F-v5.bin --meta-a ... --capture-b artifacts/LX521.4/LX521.4_22MG10F-v7.bin --meta-b ... --all-ch L`;
  `--right` forwards the same overlays with `--all-ch R`.
- The wrapper has two important bypass/degrade cases:
  - If any local capture or sidecar is missing, it prints
    `WARNING: local A/B preset captures are incomplete; flashing canonical V3.5 without baked presets`
    and forwards only `--hex ... --all-ch L|R`.  That path does not repair
    filename EEPROM.
  - `--finalize-only` only runs the IR profile finalize; it does not rerun the
    A/B capture overlay ceremony.  This is explicit in the user-facing help and
    in the lower-level MAIN flasher error messages.
- `src/dlcp_fw/sim/dlcp_sim_native.py`: Python facade exposes `Chain.from_v171_v32`, `firmware_hid_report`, `read_main_reg`, `write_main_reg`, `read_main_eeprom_byte`, and `write_main_eeprom_byte`; this is sufficient for a black-box repro and byte-level EEPROM oracle.
- Existing tests cover pieces but not this bug: `test_v32_usb_filename_xact_gate.py`, `test_v32_flasher_sim_backend_hid.py`, `test_v34_field_bugs_20260610.py`, and `test_preset_filename_lcd_spec.py`.

## Reproduction Results

This section records the pre-fix behavior unless explicitly marked post-fix.

Added `tests/sim/test_v35_filename_eeprom_nul_repro.py`.

Focused test result:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_filename_eeprom_nul_repro.py
```

Pre-fix result after adding the static vector guard: `1 passed, 2 xfailed in 11.85s`.

Current focused prevention-gate result:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_main_boot_vector_abi.py tests/sim/test_v35_filename_eeprom_nul_repro.py tests/sim/test_sim_chain_exploratory_preset_safety.py tests/sim/test_sim_exploratory_oracle_format.py
```

Pre-fix result: `23 passed, 5 xfailed in 32.78s`.

Post-fix focused gate:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_main_boot_vector_abi.py tests/sim/test_v35_filename_eeprom_nul_repro.py tests/sim/test_v35_v173_release_builders.py tests/sim/test_dlcp_v35_release_flash.py tests/sim/test_firmware_version_label.py::test_v35_usb_and_eeprom_version_match_release_identity tests/sim/test_v172_v33_diag_identity.py::test_v35_cmd25_identity_handler_emits_16bit_revision_nibbles tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_diag_ok_title_shows_visible_main_identity
```

Post-fix result: `24 passed, 1 xfailed in 44.64s`. The remaining xfail is the historical V3.4 boot-vector mismatch.

Control case:

- `test_v35_main_only_filename_force_persist_is_byte_exact` passes.
- MAIN-only V3.5 persists the staged `0x02C0..0x02DD` filename slot byte-exactly to EEPROM A when no CONTROL chain traffic is present.

Static root-cause case:

- Pre-fix, `test_v35_seeded_boot_irq_vector_targets_fsr2l_save_word` was a strict xfail for `BUG-V35-FNAME-EEPROM`.
- It proved the seeded bootloader vector still targeted `0x1008`, while the V3.5 app ISR FSR2L save started at `0x1006`.
- Post-fix, the same guard passes for V3.5.

Failing full-chain case:

- Pre-fix, `test_v35_full_chain_filename_force_persist_is_byte_exact` was a strict xfail for `BUG-V35-FNAME-EEPROM`.
- Pre-fix, `test_v35_full_chain_filename_eeprom_a_b_survive_churn_and_power_cycle` was a strict xfail for the same bug and covered both A/B filename slots through menu churn and POR reset.
- Running it with `--runxfail` fails while active filename RAM remains clean.
- Observed EEPROM A after full-chain force persist:
  `4c583532312e342032324d47b22300b12300b22300b12300b22300b12300`
- Expected EEPROM A:
  `4c583532312e342032324d473130462d7635ffffffffffffffffffffffff`
- First diff is offset 12. A NUL appears at offset 14 in this phase. The corrupt tail is chain-frame-looking data (`b2 23 00 b1 23 00 ...`), not bytes from the staged filename.

Trace localization:

- A temporary PyO3 watchpoint helper, `trace_main_ram_transitions`, was added to `crates/dlcp-sim-py/src/lib.rs` and exposed through `src/dlcp_fw/sim/dlcp_sim_native.py`.
- Around the first bad byte:
  - `preset_pf_lp` at `0x4292` correctly reads filename bytes through `POSTINC2` until EEPROM offset `0x6B`.
  - During UART interrupt service, `setup_fsr2_page2_from_w` at `0x3C34` moves `FSR2L` from the filename cursor `0xCC` to RX-ring offset `0x0F`.
  - The ISR restore path at `0x3212` restores `FSR2L` to stale `0x00`, because the bootloader jumped to `0x1008` and skipped the FSR2L save at `0x1006`.
  - The next `preset_pf_lp` iteration at `0x4292` reads `0xB2` from `0x0200` instead of `0x31` from `0x02CC`.
- Therefore `eeprom_write_byte_if_changed` and `eeprom_write_blocking` are downstream; they write the bad byte they are handed.

## Fix Closeout

Implemented fix:

- Added one intentional pad word after the V3.5 app reset trampoline so the preserved bootloader high-IRQ vector at byte address `0x1008` enters on `movff FSR2L,isr_save_fsr2l`.
- Rebuilt the canonical V3.5 release with `scripts/build_v35_release.py`, bumping release revision `0x0084 -> 0x0085`.
- Converted the V3.5 boot-vector and filename EEPROM repros from xfail to passing regression tests.
- Kept V3.4 as a documented strict xfail in the cross-version boot-vector ABI gate.

Listing confirmation after the fix:

- `0x1000`: `bra app_entry__jump_to_cold_init`
- `0x1002`, `0x1004`, `0x1006`: three `0xFFFF` pad words
- `0x1008`: `movff FSR2L,isr_save_fsr2l_b0_phys`
- `0x100C`: `movff FSR2H,isr_save_fsr2h_b0_phys`
- `0x1010`: `call isr_high_priority_dispatch, FAST=1`
- `0x1014`: cold-init branch target

Full post-fix gate:

```bash
.venv_ep0/bin/python -m pytest tests -n 16 -q
```

Result: `1757 passed, 21 skipped, 4 xfailed, 7 warnings in 652.03s`.

Current unrelated sim blocker:

- Direct end-to-end firmware HID/cmd03 through `firmware_hid_report` currently segfaults in the native sim.
- Existing HID-path coverage also segfaults, e.g. `tests/sim/test_v32_flasher_sim_backend_hid.py::test_sim_hid_cmd03_write_then_read_round_trips_filename`.
- Until that is fixed or bypassed, the deterministic repro uses lower-level RAM staging plus the firmware dirty-service persist path.

History / regression boundary:

- `79ecbfd` (`Prepare V3.4 V1.73 release work`) used `goto flow_app_entry_1014` at `0x1000`; with two filler words, the FSR2L save started at `0x1008`.
- `1591503` (`Fix V3.4 muted DSP refreshes`) changed the reset trampoline to `bra flow_app_entry_1014` but left the same two filler words. That saved two bytes but moved the ISR stub to `0x1006`, while the preserved bootloader vector still jumps to `0x1008`.
- Later size-reclaim commits, including `5eeeb82`, inherit the bad alignment. The late `chain_copy` work is not required to explain this failure.
- The user-observed timing may require full-chain UART traffic and EEPROM filename persistence, which is why MAIN-only and some older tests did not expose it.

Useful listing PCs for the next pass:

- `eeprom_write_blocking = 0x3948`
- `eeprom_write_byte_if_changed = 0x3C12`
- `preset_persist_filename = 0x4284`
- `preset_pf_lp = 0x4292`

## Root Cause

Root cause: V3.5's app interrupt stub is two bytes earlier than the bootloader high interrupt vector target.

The stock bootloader vector preserved in seeded/release MAIN images jumps to `0x1008`. V3.5's size-saving reset trampoline uses a 2-byte `bra` at `0x1000` but still has only two filler words before the ISR stub, so `movff FSR2L,isr_save_fsr2l` starts at `0x1006`. Entering at `0x1008` skips that low-byte save. UART RX interrupts then use FSR2 for the RX ring and restore a stale low byte. When the foreground filename EEPROM persist loop resumes, its `POSTINC2` source cursor points into `0x0200..` instead of `0x02C0..`, so the persisted filename tail becomes current-loop frame bytes such as `B2 23 00 B1 23 00`.

This is why the live EEPROM contains NULs and why CONTROL later stops scrolling: `cmd26_filename_query_handler` scans until a non-printable byte and treats the embedded NUL as the end of the name.

Missing coverage that let this through:

- No static gate asserted that the bootloader high-IRQ vector target equals the first word of the app ISR FSR2L save.
- No full-chain regression asserted preset filename EEPROM A/B remain byte-exact under UART traffic after forced filename persist.
- Existing FIELD-9 coverage only proved invalid `rx_ring_wr` cannot write directly into filename RAM; it did not cover ISR vector alignment or EEPROM poisoning through a corrupted FSR2 cursor.
- Native sim HID/cmd03 coverage is currently blocked by the `firmware_hid_report` segfault, so the deterministic repro uses lower-level dirty-service triggering.

Preventive gates now added in the firmware-fix commit:

- `tests/sim/test_main_boot_vector_abi.py` statically pins seeded bootloader reset/high-IRQ vectors and app ISR stub alignment. V3.2/V3.3/V3.5 pass; V3.4 remains a documented strict xfail.
- `tests/sim/test_v35_filename_eeprom_nul_repro.py` includes byte-exact full-chain filename EEPROM A/B persistence through forced persist, menu churn, and POR reset.

Additional exploratory working-tree changes from the repro pass, to commit or discard separately:

- `scripts/sim_chain_exploratory.py` now samples preset-A/preset-B filename EEPROM raw bytes per MAIN and emits high-severity incidents when idle persistent slots diverge from the expected session slot.
- `scripts/sim_exploratory_oracle_format.py` now renders EEPROM slot state in oracle cards and ranks embedded-NUL filename EEPROM corruption as a high-priority realistic signal.
- `CODING_STYLE.md` now marks fixed-entry boot/vector/ISR/FSR/scratch size optimizations as high risk and requires byte-level structural gates.

## Proposed Work Units

Completed:

- Added focused sim repro file `tests/sim/test_v35_filename_eeprom_nul_repro.py`.
- Added helpers for 30-byte filename slots, EEPROM reads, active RAM reads, staging, and forced dirty-service persist.
- Proved MAIN-only clean persist and full-chain EEPROM corruption while RAM stays clean.
- Added a strict xfail static vector-alignment guard.
- Added `tests/sim/test_main_boot_vector_abi.py` as the cross-version static ABI gate.
- Restored V3.5 vector/stub alignment by adding the third pad word before the ISR stub.
- Rebuilt canonical `DLCP_Firmware_V3.5.hex` at release revision `0x0085`.
- Converted the V3.5 static and full-chain repros into passing regression tests.
- Ran the full `tests -n 16 -q` gate successfully.
- Extended filename persistence coverage to A/B slots, menu churn, and POR reset.
- Extended exploratory sim/oracle tooling to capture and rank persistent filename EEPROM corruption.
- Documented fixed-address size-optimization risk in `CODING_STYLE.md`.
- Added temporary trace instrumentation and localized the bad source byte to `preset_pf_lp` after the ISR restores a stale FSR2L.

Remaining:

1. Decide separately whether to keep or remove the temporary trace-helper changes in the dirty working tree.
2. Fix or bypass the native sim `firmware_hid_report` segfault separately so release-like cmd03 coverage can be restored.

## Likely Files

- Add/update: `tests/sim/test_v35_filename_eeprom_nul_repro.py`.
- Possibly add: `artifacts/reanalysis/v35_filename_eeprom_nul_*/` generated logs.
- Possibly edit during fix: `src/dlcp_fw/asm/dlcp_main_v35.asm`, builder/release docs, and any V3.4/V3.5 vector-layout test.
- Temporary instrumentation already touched: `src/dlcp_fw/sim/dlcp_sim_native.py` and `crates/dlcp-sim-py/src/lib.rs`.
- Do not repair live EEPROM before flashing a fixed MAIN and verifying the EEPROM/RAM slots.

## Test Plan

Focused:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_filename_eeprom_nul_repro.py
.venv_ep0/bin/python -m pytest -q tests/sim/test_main_boot_vector_abi.py tests/sim/test_v35_filename_eeprom_nul_repro.py tests/sim/test_sim_chain_exploratory_preset_safety.py tests/sim/test_sim_exploratory_oracle_format.py
.venv_ep0/bin/python -m pytest -q tests/sim/test_v32_flasher_sim_backend_hid.py tests/sim/test_v32_usb_filename_xact_gate.py
```

If sim facade/Rust instrumentation changes:

```bash
PYO3_PYTHON="$PWD/.venv_ep0/bin/python" cargo build --release -p dlcp-sim-py
bash crates/dlcp-sim-py/build.sh
cargo test --release -p dlcp-sim
```

Broader gate after repro/fix:

```bash
.venv_ep0/bin/python -m pytest tests -n 16 -q
```

Pre-fix behavior: at least one focused repro failed or emitted an artifact proving first corruption.
Post-fix behavior: full suite reports `1757 passed, 21 skipped, 4 xfailed`.

## Deployment And Smoke

Firmware artifact updated: canonical V3.5 release hex rebuilt at revision `0x0085`. Live EEPROM repair is still separate from this IMPL; after flashing the fixed MAIN, verify HID-only active RAM and EEPROM A/B reads before any live preset/UI exercise.

## Acceptance Criteria

- A sim test or exploration artifact reproduces a NUL at one of the live offsets. Done: full-chain repro corrupts EEPROM A offset 14 to `0x00` while RAM stays clean.
- The vector-layout regression is statically captured. Done: pre-fix strict xfail proved the boot vector targeted `0x1008` while the FSR2L save started at `0x1006`; post-fix V3.5 passes with the save at `0x1008`.
- The first bad writer/mechanism is identified. Done: ISR vector misalignment skips FSR2L save; UART ISR restores stale FSR2L; `preset_pf_lp` reads RX ring bytes via `POSTINC2`.
- The smallest observed historical boundary is identified. Done: `79ecbfd` aligned; `1591503` misaligned.
- No live EEPROM rewrite is done before root-cause evidence is captured.

## Original Goal Prompt

The following pre-fix `/goal` prompt is preserved for history. It is 2827 characters, counted with Python `len()`:

```text
/goal Reproduce and prove BUG-V35-FNAME-EEPROM from docs/IMPL_V35_FILENAME_EEPROM_NUL_REPRO.md, then update that IMPL with evidence. Do not implement the firmware fix unless explicitly redirected.

Required reads:
- AGENTS.md, README.md, CODING_STYLE.md, docs/SIMULATION.md
- docs/IMPL_V35_FILENAME_EEPROM_NUL_REPRO.md
- tests/sim/test_v35_filename_eeprom_nul_repro.py
- src/dlcp_fw/asm/dlcp_main_v35.asm and .lst around 0x1000, 0x31E6, 0x320E, 0x3C12, 0x3948, 0x4284
- docs/V34_SIZE_OPTIMIZATION_FINDINGS.md around S1/S2 and T121 notes

Known evidence:
- Live V3.5 EEPROM names had in-body NULs; local capture JSON names are clean.
- Current focused repro: `.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_filename_eeprom_nul_repro.py` gives `1 passed, 2 xfailed`.
- MAIN-only filename persist passes; full V1.73+V3.5 chain persist corrupts EEPROM A to `4c583532312e342032324d47b22300b12300b22300b12300b22300b12300` while active filename RAM stays `4c583532312e342032324d473130462d7635ffffffffffffffffffffffff`.
- Static xfail shows the seeded bootloader high IRQ vector bytes at 0x0008 are `04 ef 08 f0` => GOTO 0x1008, but V35 app bytes at 0x1008 are `01 f0 da cf`, the second word of `movff FSR2L,...` plus the first word of `movff FSR2H,...`; the FSR2L save actually starts at 0x1006.
- History scan: `79ecbfd` had `goto flow_app_entry_1014` at 0x1000 and FSR2L save aligned at 0x1008; `1591503` changed it to `bra` without adding a filler word, moving the save to 0x1006. V3.2/V3.3 release hexes align; current V3.4/V3.5 do not.

Process:
1. Re-run the focused repro and one `--runxfail` for each xfail to capture exact failing bytes/messages.
2. Reproduce the trace evidence with `trace_main_ram_transitions`: watch FSR2L/H, 0x001/0x002, 0x003/0x005/0x009, RX ring 0x0200.., and filename RAM 0x02C0.. during dirty-service persist.
3. Confirm the mechanism: UART ISR entered at 0x1008 skips `movff FSR2L,isr_save_fsr2l`; ISR uses FSR2 for RX ring at `uart_rx_irq_enqueue`; restore writes stale FSR2L; `preset_pf_lp` then `movff POSTINC2,0x009` reads RX-ring bytes instead of filename RAM.
4. Confirm the symptom link: `cmd26_filename_query_handler` treats the EEPROM NUL/non-printable as filename terminator, explaining stopped LCD scrolling after EEPROM reload/power cycle.
5. Compare V3.2, V3.3, current V3.4, current V3.5 merged bytes at 0x0008 and 0x1000..0x1015. Record exact bytes.
6. Update the IMPL with commands/results, root cause, earliest observed bad commit, remaining risks, and a fix recommendation. Preserve unrelated dirty files.

Done when the IMPL contains enough evidence for a narrow fix goal: restore IRQ-vector/stub alignment (prefer adding one filler word before the ISR stub or otherwise ensure the bootloader vector target lands on `movff FSR2L`) plus tests that fail before and pass after.
```

## Reviewer Findings

Review pass 1 - Simplicity/scope: no High/Medium. Low: avoid expanding the fix into HID/cmd03 simulator repair. Disposition: HID segfault is documented as separate; the root-cause proof uses deterministic dirty-service and static vector tests.

Review pass 2 - Correctness/contract: no High/Medium. Low: `a274dfa` is not the clean pre-size baseline for this specific vector issue. Disposition: history section records `79ecbfd` aligned and `1591503` first observed bad.

Review pass 3 - Ops/tests/deploy: no High/Medium. Low: full `tests/sim -n 16 -q` was not run in the reproduction-only pass. Disposition: full `tests -n 16 -q` was run during the fix closeout and passed.

Review pass 4 - Firmware/data integrity: no High/Medium. Low: live repair would destroy evidence. Disposition: explicit non-goal and acceptance criterion added.

Review pass 5 - Regression archaeology: no High/Medium. Low: first observed bad commit includes functional mute-refresh work plus a size-saving reset-trampoline edit. Disposition: fix recommendation targets the minimal vector-layout invariant, not the whole commit.

Zero unresolved High or Medium findings.
