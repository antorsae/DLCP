# PIC18 Rust Simulator Fidelity Audit

Date: 2026-06-14

Scope: `crates/dlcp-sim` PIC18 executor/core fidelity, with emphasis on PIC18F2455 behavior that can let DLCP firmware bugs pass simulation.

## Executive Verdict

Commit `0f62b2de18eb7e7d3eb6805e93f4bfad3e0f015b` is directionally correct and necessary. DS39632E says the return stack pointer is readable/writable, the Top-of-Stack registers are readable/writable, and software may restore TOSU:TOSH:TOSL before returning. The commit fixed the main failure mode by writing staged TOS SFR writes through into the simulator's external `Stack`, instead of only changing the SFR mirror.

The commit was too narrowly tested. It only pinned a `MOVWF TOSL` low-byte computed return. The generic write path meant `MOVFF` destinations already worked after the fix, but that was not tested and the code comment said otherwise. This audit added regression coverage for `MOVFF` to TOSL/TOSH and for neighboring stack/PC semantics.

The practical reason the bug escaped is that the suite had strong end-to-end DLCP behavior tests but no direct architectural unit test for "software writes TOS, then RETURN pops the modified address". The V3.4 `chain_copy` idiom at `src/dlcp_fw/asm/dlcp_main_v34.asm` reads TOSL/TOSH into TBLPTR and later writes TOSL/TOSH before `return`; without a TOS write-through assertion, the simulator could show the new SFR values while returning through the stale internal stack entry.

## Fixes Implemented

Files changed by this audit:

- `crates/dlcp-sim/src/core.rs`
- `crates/dlcp-sim/src/exec.rs`

Implemented:

- Added post-instruction staging for software writes to `STKPTR` and `PCL`, mirroring the existing TOS staging pattern.
- Applied `STKPTR` software writes to the authoritative `Stack`, then mirrored STKPTR/TOS SFRs back to data memory.
- Implemented PCL read/write side effects:
  - PCL reads refresh PCL/PCLATH/PCLATU from current PC.
  - PCL writes load PC from PCLATU:PCLATH:written-PCL.
  - One-cycle instructions that write PCL are billed as 2 Tcy for the pipeline flush.
- Fixed `CLRF INDF0` when FSR resolves to STATUS: STATUS result-write is now suppressed and only Z is set, matching the direct `CLRF STATUS` rule.
- Fixed FSR-indirect accesses whose resolved pointer target is another FSR virtual register: reads now return `0x00`, writes are NOPs, and PRE/POST pointer updates still happen at the documented time.
- Corrected the stale MOVFF/TOS comment and added tests for the MOVFF path.

New/expanded Rust unit coverage:

- `movff_tos_write_through_patches_computed_return_high_byte`
- `movwf_stkptr_write_changes_internal_depth_and_tos_mirror`
- `addwf_pcl_computed_goto_refreshes_latches_and_bills_branch_cycle`
- `movwf_pcl_uses_pclath_and_bills_branch_cycle`
- `movf_pcl_updates_latches_from_current_pc`
- `clrf_indf0_pointing_at_status_preserves_flags_except_z`
- `movf_indf0_pointing_at_virtual_register_reads_zero`
- `setf_indf0_pointing_at_virtual_register_is_nop`
- `movf_postinc0_pointing_at_virtual_register_reads_zero_and_increments`
- `setf_postinc0_pointing_at_virtual_register_is_nop_but_increments`
- `movf_preinc0_landing_on_virtual_register_reads_zero`
- `movf_plusw0_landing_on_virtual_register_reads_zero`

## Datasheet Anchors

Primary reference: `firmware/reference/39632e.md`.

- PC/PCL/PCLATH/PCLATU transfer rules: lines 2329-2335.
- Stack/TOS readability and writability: lines 2341-2349.
- STKPTR writability and underflow/overflow behavior: lines 2369-2379.
- PUSH/POP and TOS modification: lines 2383-2387.
- STKPTR bit semantics: lines 2391-2402.
- Computed GOTO via `ADDWF PCL`: lines 2436-2444.
- STATUS destination suppression for flag-affecting instructions: lines 2990-2994.
- FSR indirect/POSTINC/PREINC/PLUSW behavior: lines 3096-3134.
- FSR pointing at virtual registers returns 0 / writes as NOP: lines 3136-3144.

## Audited Subsystems

Confirmed or improved:

- Return stack/TOS/STKPTR: TOS write-through is now covered for MOVWF and MOVFF; STKPTR writes now update real stack depth.
- PCL/PCLATH/PCLATU: previously documented as deferred; now modeled for reads, writes, computed goto, and cycle cost for 1-Tcy PCL writers.
- STATUS write suppression: direct STATUS cases were mostly covered; `CLRF` through FSR indirection is now fixed.
- FSR addressing: existing implementation covers INDF/POSTINC/POSTDEC/PREINC/PLUSW ordering and single-commit behavior; this audit also fixed the DS39632E virtual-target read-zero/write-NOP case.
- Access Bank/BSR routing: existing tests and implementation cover the 0x00-0x5F low access bank and 0xF60-0xFFF SFR window.
- Stack overflow/underflow/STVREN: existing tests cover latch-only and reset policies.
- TBLPTR/TABLAT/TBLRD/TBLWT, EUSART, MSSP, timers, USB facade: reviewed at interface level, not exhaustively re-derived in this pass.

Confirmed bugs fixed in this pass:

- Software writes to `STKPTR` previously changed only the SFR mirror. They now update the authoritative stack depth and refresh STKPTR/TOS mirrors.
- Software writes to `PCL` previously changed only the raw SFR byte. They now perform computed control transfer through PCLATU:PCLATH:PCL and charge the 2-Tcy branch cost for one-word PCL-writing instructions.
- PCL reads now refresh PCL/PCLATH/PCLATU from the current PC before returning the low byte.
- `CLRF` through FSR indirection to STATUS previously cleared STATUS instead of applying the STATUS destination-suppression rule.
- FSR-indirect access with FSR pointing at `INDFn`/`POSTINCn`/`POSTDECn`/`PREINCn`/`PLUSWn` previously treated that virtual address as ordinary SFR storage. It now reads zero or drops the write, while preserving PRE/POST FSR mutation.

Suspicious / recommended follow-up:

- Interrupt safety around firmware TOS-rewrite helpers remains a firmware-level concern for historical V3.4 source review. Current V3.5 rev `0x0095` fixes `chain_copy` by preserving the caller's `GIE`, masking only the `TOSL/TOSH` commit window, and restoring `GIE` only if it was previously set; the strict chain-copy xfail was replaced by `tests/sim/test_v34_v173_refactoring_contracts.py::test_v35_chain_copy_tos_rewrite_masks_and_restores_prior_gie`.
- The multicore diagnostics stale-health path now intentionally expects the current `PB1 old` layout when PB1 health age exceeds the stale threshold. Operator hardware evidence from 2026-06-14 reported the same `old` LCD symptom while `scripts/dlcp_diag.py` saw V3.4 `DEGRADED (i2c_transport_faults=6)`, matching the current PB Diagnostics stale-health contract rather than a CPU-core regression.
- Add an ISA-level property/fuzz pack for writable core SFRs and indirect targets so future executor work probes PCL, PCLATH/PCLATU, STKPTR flags, TOSU masking, STATUS via indirect, and FSR-to-virtual-register accesses across multiple instructions, not only curated examples.

## Why the TOS Bug Escaped

The suite's older tests validated broad DLCP workflows and stack push/pop basics, but did not assert the architectural coupling between the TOS SFR window and the return-stack RAM. That is the exact shape that matters for computed returns. A simulator can pass "TOS SFR reads back what firmware wrote" while still failing the real behavior, because RETURN consumes the stack entry, not the SFR mirror.

The bug also sat behind a firmware optimization pattern: V3.4 `chain_copy` places inline descriptors after a call and rewrites TOS to skip those bytes before returning. That pattern is uncommon enough that ordinary call/return and chain behavior tests did not force a precise stack-entry assertion.

## Command Results

Passed:

- `cargo fmt --package dlcp-sim`
- `cargo test -p dlcp-sim --lib`
  - `627 passed, 1 ignored`
- `cargo test -p dlcp-sim --release`
  - Full release Rust gate passed after updating the multicore diagnostics test to assert the current stale-health layout (`PB1 old`, blank row 1).
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q`
  - `1641 passed, 2 skipped, 3 xfailed, 7 warnings`

## Bottom Line

The original TOS write-through commit should stand. This audit broadens it into a stronger PIC18 core-SFR fidelity fix set and adds the tests that would have caught the original class of bug earlier. The high-confidence CPU-core gaps found in this pass were fixed and pinned; the remaining work is broader property coverage.
