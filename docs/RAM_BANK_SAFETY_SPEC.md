# RAM Bank Safety SPEC

Date: 2026-06-07
Status: Implemented source spec
Scope: Source-assembled MAIN V3.3 and CONTROL V1.72 RAM access safety

## Problem

PIC18 RAM banking bugs are too easy to ship in the current source style.
The recent Preset filename LCD blank-line bug came from a banked access to a
bank-0 delay counter while the caller had left `BSR=2`; the instruction hit a
MAIN UART RX ring byte at the same low operand in bank 2 instead of the intended
bank-0 cell. One line of local `movlb 0x0` fixed the bug, but local assertions
do not make the source robust.

The repository needs a principled, fail-closed guard that proves RAM accesses
are bank-safe before firmware is accepted.

## Goals

- Make RAM ownership explicit for MAIN V3.3 and CONTROL V1.72.
- Forbid direct RAM f-operand access in target sources:
  - no new `ram_0xNNN` use in executable code
  - no raw numeric RAM operands such as `0x73, BANKED`
  - no bank-ambiguous semantic names such as `fn_job_idx` without a bank suffix
- Require RAM symbols to encode their bank/access class in the name, for
  example `fn_job_idx_b2`, `v172_fname_flags_b2`, `an0_delay_b0`, or
  `tmp0_acc`.
- Require a machine-checkable RAM manifest to be the source of truth for
  address, bank, operand, owner, alias policy, and access-mode permissions.
- Add a fail-closed checker that statically proves each `BANKED`, `ACCESS`,
  `movff`, and `lfsr` RAM use is legal.
- Integrate the checker into release-build and pytest paths so failures block
  normal V3.3/V1.72 work.
- Measure whether the guard changes MAIN program size. Pure source renames and
  static checkers must not emit new firmware instructions; if the checker finds
  a real RAM-bank bug that requires a local `movlb`, the exact MAIN size delta
  must be measured and accepted explicitly.

## Non-Goals

- Do not change DLCP runtime behavior.
- Do not add firmware code merely to make the checker easier.
- Do not rewrite all historical firmware versions in the first pass.
- Do not depend on human review comments such as "callers must movlb first" as
  the enforcement mechanism.
- Do not treat file size on disk as a firmware size metric.

## Required Target Sources

- MAIN source: `src/dlcp_fw/asm/dlcp_main_v33.asm`
- MAIN RAM include: `src/dlcp_fw/asm/dlcp_main_ram.inc`
- CONTROL source: `src/dlcp_fw/asm/dlcp_control_v172.asm`
- CONTROL RAM include: `src/dlcp_fw/asm/dlcp_control_ram.inc`
- Release builders:
  - `scripts/build_v33_release.py`
  - `scripts/build_v172_release.py`

Older sources may remain report-only unless the implementation touches them.

## RAM Manifest Contract

The implementation shall add one repository-owned manifest, either YAML or a
Python data structure, for MAIN and CONTROL target RAM cells. The manifest must
record at least:

- MCU target: `main_v33` or `control_v172`
- symbolic cell name
- physical address
- bank number
- 8-bit f-operand value
- access class: `banked`, `access`, `sfr`, `indirect_only`, or `constant`
- owner/subsystem
- whether aliasing is forbidden or intentionally allowed
- optional comments for stock-derived unknown cells

Example shape:

```yaml
main_v33:
  an0_delay_b0:
    phys: 0x0A1
    bank: 0
    op: 0xA1
    access: banked
    owner: an0_hysteresis_monitor
    aliases: forbidden
  fn_job_idx_b2:
    phys: 0x2F6
    bank: 2
    op: 0xF6
    access: banked
    owner: preset_filename_reply
    aliases: forbidden
```

The `.inc` files may stay committed, but they must be generated from or
validated against this manifest. Drift between manifest and committed include
files is a build/test failure.

## Symbol Naming Rules

RAM cell names in target executable sources must include bank/access class:

- `*_b0`, `*_b1`, `*_b2`, ... for banked GPR cells
- `*_acc` for cells intentionally accessed through `ACCESS`
- `*_sfr` for SFR symbols
- `*_phys` for full physical addresses used by `movff` or `lfsr`
- `*_op` for 8-bit f-operands used by normal f-operand instructions

The checker must reject a RAM symbol that does not map to exactly one manifest
entry.

Unknown stock-derived cells may use explicit generated names such as
`stock_0A1_b0` until they receive better semantic names. That is acceptable
because it is still bank-explicit and machine-checkable. Bare `ram_0x0A1` is not
acceptable in target executable code.

## Checker Contract

The checker shall parse assembly source and, after assembly, relevant `.lst`
files. It must fail closed: an unknown or indeterminate RAM access is an error,
not a warning.

Required checks:

- f-operand RAM instructions using `BANKED` must be preceded on every static
  path by a proven `movlb` for the manifest bank, or by a routine contract that
  proves the same BSR state.
- f-operand RAM instructions using `ACCESS` must reference only manifest cells
  marked `access: true` or recognized SFR/common RAM symbols.
- raw numeric RAM f-operands in executable source are forbidden unless they are
  SFRs or explicitly declared generated constants.
- `ram_0xNNN` operands are forbidden in target executable source.
- `movff` operands must use physical-address symbols or SFRs; using an 8-bit
  banked operand symbol is forbidden.
- `lfsr` targets must use physical-address symbols for RAM.
- duplicate physical addresses are forbidden unless the manifest marks a
  deliberate alias and names the owning relationship.
- generated `.inc` output must match the checked-in include files or the build
  fails with a clear regeneration instruction.
- routine entry/exit BSR contracts must be explicit for routines that touch
  banked RAM before a local `movlb`.
- calls are BSR-clobbering unless a routine contract says otherwise.

## Routine Contract Comments

The checker may use structured comments in assembly source:

```asm
;@routine an0_hysteresis_monitor entry_bsr=unknown exit_bsr=unknown
;@routine v172_fname_deadline_service entry_bsr=0 exit_bsr=0
;@routine lcd_char_write entry_bsr=0 exit_bsr=clobber
```

Contracts are not optional for routines that rely on inherited BSR. The safer
default remains a local `movlb` before banked RAM access.

## Macro Policy

RAM access macros may be introduced, but they are not required for the first
guard. A mandatory macro rewrite is risky because helper macros that emit
`movlb` can increase MAIN code size.

Preferred first-pass enforcement:

- manifest-backed aliases
- explicit source `movlb`
- static BSR proof
- build/test integration

Optional later macro helpers are allowed for new code or narrow migrations only
when the size delta is measured and accepted.

## MAIN Size Requirement

The implementation must prove whether MAIN size changed.

For a pure checker/alias implementation, the expected result is:

- no change to `used_bytes_pre_preset_b`
- no change to `last_used_pre_preset_b`
- no change to `free_bytes_before_0x4C00`
- preferably byte-identical program bytes in `0x1000..0x4BFF`

Use a temp `assemble_v30()` build for measurement. Do not use
`scripts/build_v33_release.py` for the size baseline because that script bumps
release identity bytes.

Required metric window:

- MAIN code/data before Preset B: `0x1000..0x4BFF`
- Preset B anchor: `0x4C00`

## Test Requirements

The implementation must add focused tests that fail on the known bug shape:

- `an0_hysteresis_monitor` touching the bank-0 delay counter with no proven
  `BSR=0`
- a bank-2 symbol accessed after a path with proven `BSR=0`
- branch targets that prove a matching bank
- branch merges where multiple possible BSR values make a banked access
  indeterminate
- internal calls whose source-visible bodies preserve or set BSR
- external calls defaulting to BSR-clobbering
- routine-contract entry and exit mismatches
- recursive routine contracts where the recursive edge is assumed but the
  contract body is still verified
- labeled unreachable executable `BANKED` access failing closed
- a `movff` using an 8-bit banked operand alias
- a raw numeric RAM operand in target source
- duplicate same-physical-address manifest entries without an explicit alias

The implementation must also keep the existing preset filename native-chain
tests passing, because they are the behavioral regression that exposed the bug.

## Acceptance Criteria

- `scripts/check_ram_access_safety.py --target main-v33 --target control-v172`
  exits non-zero on any unsafe or unknown target RAM access.
- The canonical V3.3 and V1.72 builders run the checker before copying release
  hex files.
- `pytest` has a focused RAM bank safety test module covering checker behavior
  and the known Preset filename bug class.
- Target source executable RAM accesses no longer use raw `ram_0xNNN` names or
  raw numeric RAM operands except documented SFR/common-RAM exceptions.
- MAIN size report is recorded in the IMPL with before/after metrics.
- If MAIN program bytes change, the IMPL explains why and records the exact
  byte delta. Unexpected growth blocks acceptance.
- No hardware flash or deployment is required for this tooling-only feature.
