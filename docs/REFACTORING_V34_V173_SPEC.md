# REFACTORING_V34_V173 SPEC

Date: 2026-06-08
Status: Reviewed source spec
Targets: MAIN V3.4 and CONTROL V1.73
Scope: source-level simplification and lifecycle hardening for the current
V3.3/V1.72 behavior set, with no user-visible feature loss.

Baseline note: this implementation spec uses V3.3/V1.72 as the immediate code
lineage baseline.  User-facing release comparison in `README.md` is against the
stock pair, MAIN V2.3 + CONTROL V1.6b.

## Purpose

V3.4/V1.73 is a refactoring release pair.  It exists to make the firmware
simpler and more robust by consolidating duplicated lifecycle code, clarifying
state ownership, and replacing ad-hoc UI recovery paths with deterministic
page/service contracts.

This is not a new product-feature release.  The observable V3.3/V1.72 behavior
must remain intact unless a current bug is fixed by a tighter lifecycle
contract and covered by tests.

The motivating rule for this wave is:

- do not add Preset LCD redraw/retry hacks such as a row-0 full redraw recovery
  path;
- instead, make page ownership, row readiness, filename cache validity, chain
  transmission arbitration, and reset/reconnect state transitions explicit.

## Required New Release Pair

The implementation shall create a new source-assembled release pair:

- MAIN source: `src/dlcp_fw/asm/dlcp_main_v34.asm`
- MAIN release HEX: `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- MAIN builder: `scripts/build_v34_release.py`
- MAIN release flasher wrapper: `scripts/dlcp_v34_release_flash.py`
- CONTROL source: `src/dlcp_fw/asm/dlcp_control_v173.asm`
- CONTROL release HEX: `firmware/patched/releases/DLCP_Control_V1.73.hex`
- CONTROL builder: `scripts/build_v173_release.py`

The implementation shall add matching constants and release-tool wiring in
`src/dlcp_fw/paths.py` and relevant flash/build modules.

Before behavior refactoring starts, the new pair shall also be fully wired into:

- native simulator artifact/listing lookup;
- RAM-bank checker targets `main-v34` and `control-v173`;
- release builders that run target-specific RAM-bank safety before publishing
  release HEX files;
- flash-wrapper tests that allow V3.4/V1.73 flashing and pin the accepted
  CONTROL safe-flash default.

Promotion status: as of 2026-06-14, V3.4/V1.73 is the recommended operator
release pair.  `README.md` and `scripts/flash_control_safe.sh` now default to
MAIN V3.4 rev `0xAC` plus CONTROL V1.73 rev `0x47`; V3.3/V1.72 remains the
previous supported rollback pair.

## Goals

1. Preserve the complete V3.3/V1.72 behavior surface:
   A/B presets, preset filename LCD, diagnostics identity, BF/08 fault
   handling, SRC4382 Auto Detect behavior, reconnect robustness, IR shortcuts,
   flash safety, release builders, and existing compatibility with older pairs
   where tests currently require it.
2. Reduce lifecycle ambiguity by making reset, reconnect, page entry/exit,
   filename query/cache, UART parser, and I2C recovery ownership explicit.
3. Remove meaningful duplication when it reduces real maintenance risk without
   increasing firmware size unnecessarily.
4. Improve robustness with fail-closed structural tests and simulator tests,
   not sleeps, retries, or opportunistic redraw recovery.
5. Measure MAIN and CONTROL size deltas.  MAIN growth is not acceptable unless
   caused by a necessary bug fix and explicitly justified.
6. Keep RAM bank safety guardrails strong: semantic bank-explicit aliases,
   physical aliases for `movff`/`lfsr`, and machine-readable routine BSR
   contracts where code relies on a BSR state.
7. Preserve staged deploy and rollback safety across V3.4/V1.72 and
   V3.3/V1.73 mixed-version combinations.

## Non-Goals

- No DLCP_LINK_V2 protocol replacement.
- No new UI page, new CONTROL LCD/chain diagnostics counter, or new hardware
  deployment flow beyond the V3.4/V1.73 release plumbing.  Later V3.4 field
  fixes added MAIN-only USB `cmd 0x44` SRC/DSP forensic counters `N/L/C/T/M`;
  those are not rendered by V1.73 CONTROL.
- No full macro rewrite of RAM access that emits hidden `movlb` instructions.
- No broad historical-source migration for older firmware versions unless a
  shared test/helper requires a compatibility alias.
- No live hardware flash unless separately requested.
- No Preset row-0 full redraw/retry workaround as a substitute for page
  lifecycle correctness.

## Required Refactoring Areas

### MAIN M1: Release Identity And Source Lineage

V3.4 shall derive all MAIN identity literals from one source of truth:

- HID/version label bytes;
- EEPROM identity bytes;
- boot-time runtime identity migration literals;
- `cmd 0x25` diagnostics identity nibbles;
- release metadata/comments.

The V3.4 source header shall not retain stale V3.2/V3.3 build text.

### MAIN M2: Cold Init And Reset State

Cold/runtime init shall deterministically clear all volatile upper bank-2
runtime state that must not survive reset, including `preset_job_*`,
diagnostics volatile state, filename job state, parser-gap state, I2C recovery
latches, and SRC4382 debounce state.

This should be expressed as named ranges or a compact table/macro so future
bank-2 state cannot be silently missed.

Reset-cause classification shall distinguish software reset from unknown
fall-through, or explicitly name the current catch-all as `sw_or_unknown`.

### MAIN M3: Chain TX Arbitration

Every MAIN-to-chain byte producer shall set the pass-local chain activity flag
through one helper or one clearly audited pattern:

- parser pass-through route/cmd/data forwarding;
- status and fault replies;
- diagnostics bursts;
- identity replies;
- filename replies.

Filename reply jobs must never interleave with a forwarded downstream frame in
the same service pass.

Filename reply pacing is a hard behavioral contract:

- replies remain incremental and non-blocking;
- at most one filename 3-byte frame is emitted per MAIN service tick;
- filename reply frames honor the existing V3.3 minimum inter-frame gap of
  2 ms start-to-start, or a stricter measured gap if the filename protocol spec
  is explicitly updated;
- every serial reply producer participates in the pass-local
  `chain_tx_emitted` contract;
- filename replies cannot splice into status, fault, diagnostics, identity, or
  forwarded-chain traffic.

Native chain tests shall stress filename replies interleaved with diagnostics
identity/status traffic and prove no RX overflow, parser drift, or retry storm.

### MAIN M4: Filename And Preset Job Lifecycle

The filename reply job shall have a documented busy/replacement policy for
repeated `cmd 0x26` queries.  Filename writers shall directly cancel any active
filename reply job, rather than relying only on indirect revision wrap checks.

The V3.4 policy is deterministic replacement with wire-visible generation
safety: CONTROL must allocate a fresh wire-visible query id for any replacement
while a previous filename transaction is pending.  MAIN aborts the current
filename job only for a fresh wire id/route.  Any same-id duplicate while active
is idempotent or ignored, even if CONTROL's derived RAM/EEPROM source changed,
because the existing reply wire format does not carry source kind.  Restart
begins at the START frame with pacing state reset only for a fresh wire
id/route.  Filename writers, preset swaps, and reconnect cleanup cancel the job
before changing the source RAM.  CONTROL rejects stale filename frames by route
plus query id; the plan must not claim same-id stale frames are distinguishable
without adding a new wire epoch.  Because the current generation field is
finite, CONTROL must not reuse a wire id for the same route/slot until stale
frames for that route/slot are expired or drained; otherwise the implementation
must add a stronger wire epoch.

Filename transaction bits shall have one begin/end contract.  If a successful
persist makes the active RAM/EEPROM name coherent, the preset-select gate shall
not stay closed longer than required.

The async preset job cancellation paths shall use one shared contract for:

- stopping Timer3;
- clearing preset job state;
- reconciling forced-mute and user-mute intent;
- preserving intentionally muted hardware state during reconnect/standby.

Unused preset job RAM shall be removed or marked reserved-free.

Every active V3.4 upper-bank runtime RAM symbol, including copied V3.3 state,
shall have lifecycle metadata: `volatile_cold_clear`, `runtime_preserve`,
`eeprom_shadow`, `scratch`, `sfr_alias`, or `derived`.  Preserved ranges require
a `preserve_reason`.  Volatile filename/preset/I2C/UART/reconnect cells must be
included in the cold-init manifest or fail tests.

### MAIN M5: I2C And DSP Recovery

Bounded I2C timeout recovery shall have one contract: after recovery, the
current transaction either aborts or explicitly restarts from a known state.
Callers must not accidentally continue an I2C transaction after a timeout
recovery path has reset the bus.

The implementation shall include a call-site inventory for every bounded I2C
wait site, including entry BSR, scratch assumptions, WREG/STATUS/FSR/TBLPTR
clobbers, timeout branch target, and whether retry, abort, or degraded
continuation is correct.  Structural or behavioral tests must prove every call
site handles the timeout/carry result or is explicitly safe to continue.

The START/SEN and STOP/PEN timeout paths shall be classified correctly.
Async preset apply recovery shall share the common observability path for
diagnostics counters, BF/08 fault reporting, and recovery flags, while still
allowing retry of the same preset table entry.

The `i2c_recover_flags` bits shall have non-overlapping meanings; one bit shall
not mean both "deferred work remains" and "immediate recovery already ran."

### MAIN M6: Parser And Reply Helpers

The parser tail-byte lifecycle shall have semantic aliases and helper comments,
not hidden `active_flags.bit6`/`stock_0BC` ownership.

Repeated BF frame emission shall use a shared helper where it clearly reduces
duplication without increasing size or changing timing.

The cumulative XOR dispatch chain shall be protected by tests or generated
comments/macros so adding V3.4 commands cannot silently break later commands.

### CONTROL C1: Display Service Ownership

CONTROL shall split the current modal `display_loop_iteration` shape into:

- a non-modal foreground/display service tick that runs parser, parser-gap,
  filename, health, and LCD patch work exactly once;
- modal page wrappers that loop by calling the non-modal tick.

Diagnostics shall keep using the non-modal path.  Preset, Volume, Input, Setup,
Standby, and Diagnostics shall share page-exit predicates for LEFT/RIGHT or
disconnect transitions.

The V1.73 display tick shall have a documented, source-tested order.  The
minimum required phases are:

1. UART receive/parser and parser-gap service before display-state mutation
   that depends on fresh frames.
2. Page entry/exit and standby/reconnect reconciliation before page body
   drawing.
3. Preset row-0 readiness/title/preset-letter service before filename row
   rendering.
4. Diagnostics identity/fault suffix service without disturbing Preset filename
   state.
5. One bounded LCD work unit per tick unless an atomic boot/Waiting draw is
   explicitly documented.

Tests shall pin the actual V1.73 call order and cover immediate LEFT/RIGHT
transitions between Preset, Input, Setup, and Diagnostics without row0/row1
incoherence.

### CONTROL C2: Preset Filename LCD Lifecycle

Preset filename rendering shall be governed by page ownership:

- Preset row 0 must be marked not-ready on exit/navigation.
- Preset row 0 readiness may be cleared only after the Preset row-0 paint and
  row-1 entry blank have completed.
- Row-1 filename/cache rendering is forbidden while row 0 is not ready.
- Same-slot cache reuse shall not issue a fresh filename query.
- Query deadlines and delayed-query countdowns shall share one decrement
  primitive with separate expiry actions unless implementation proves the shared
  primitive grows code; in that case duplicated countdown paths may remain only
  with source tests proving identical decrement semantics and separate expiry
  actions.
- Row-0 status bits shall have named masks, including the page-active/readiness
  bit.

Preset row-0 status masks shall separately name health/fault state, preset-B
state, and row0-not-ready state.  Tests shall prove the preset letter writes
only columns 14/15, readiness survives until page exit explicitly clears it,
and row0 readiness cannot erase the filename row.

Whole-row recovery redraws or blind retries are explicitly out of scope.

### CONTROL C3: UART Parser, TX, And BSR Contracts

CONTROL shall centralize the following where doing so is byte-neutral,
net-shrinking, or removes a concrete lifecycle divergence.  If a helper would
grow code without fixing a tested divergence, duplicated code may remain only
with machine-readable routine contracts or source tests proving equivalent
behavior:

- BSR-safe parser continuation after banked BF handlers;
- `rx_parser_entry` plus frame-gap service wrapper;
- UART soft-recover/ring-clear sequence;
- atomic 3-byte TX frame reservation/enqueue pattern.

Banked BF handlers must return through a single BSR-restoring tail or have an
explicit machine-readable routine contract.

### CONTROL C4: WAITING And Reconnect Lifecycle

Cold WAITING and reconnect WAITING shall share the same sentinel-reduce,
button-grace, parser-gap, and connected-state reinitialization contracts either
through common helpers/macros or through duplicated code protected by source
tests and comments when helper extraction would grow code without reducing a
known divergence risk.

The current reconnect wake saturation retry caveat shall either remain
explicitly documented and tested as preserved behavior, or be fixed with a
separate test proving the operator reset escape remains reachable during
persistent saturation.

### CONTROL C5: Diagnostics, Health, And Identity

Diagnostics identity display invalidation shall not implicitly reset retry
epoch state.  Page entry owns retry epoch reset; stale/lost visible invalidation
owns only visible validity and pending state.

Diagnostics identity epoch behavior shall be precise:

- page entry, reconnect, or source change may issue one identity query per
  source;
- timeout marks the source seen and suppresses retries until page re-entry or
  reconnect;
- stale/lost replies suppress the suffix without resetting the epoch;
- issue pages suppress identity suffix display without clearing valid cached
  identity;
- a fresh visible reply updates the suffix without disturbing unrelated
  diagnostics fields.

Write-only health state shall either be removed or used in stale/lost/unknown
classification.

PB1/PB2 identity commit/render duplication shall be factored if the helper is
smaller or clearly safer.

BF/08 fault-clear comments and aliases shall match the real bank/field being
cleared.  If the intended behavior is to clear `full_sync_lo/hi`, code must use
the real bank-0 aliases; if not, the misleading comment must be removed.

### CONTROL C6: Settings, Preset Encoding, And Release Literals

V1.73 shall derive release major/minor/patch/rev/build-date strings, metadata,
and EEPROM image identity from one source of truth.

Settings save/load loops should be generated or expressed from one source-level
map if that reduces duplication without size growth.

Preset byte encoding and boot restore shall share one central contract:
`0x01` means B; `0x00`, `0xFF`, and invalid values mean A unless a legacy path
explicitly documents a different policy.

### Cross-Cutting X1: RAM Bank Safety Lifecycle

The implementation shall improve the existing RAM bank safety system rather
than bypass it:

- add semantic aliases for active lifecycle cells still hidden behind
  `stock_*`;
- model range/base pointers used by `lfsr`;
- prefer physical aliases for full-address operands;
- expand `;@routine entry_bsr=... exit_bsr=...` coverage for BSR-sensitive
  helpers;
- keep checker/generator parser logic DRY where practical.

`build_v34_release.py` and `build_v173_release.py` shall call
`assert_targets_safe(["main-v34"])` and
`assert_targets_safe(["control-v173"])` respectively after assembly and before
copying the final release HEX into place.  Rollback tests shall prove failed
RAM safety leaves ASM/LST/HEX artifacts unchanged.

The checker manifest shall model all V3.4/V1.73 `lfsr` RAM bases with owner,
length, lifecycle, and access policy, and generated range-base `_phys` aliases
shall be required for RAM `lfsr` operands.  Raw numeric `lfsr` to RAM is always
forbidden, even when the range is modeled.  Raw numeric `lfsr` to non-RAM/SFR
requires an explicit whitelist entry.

## Mixed-Version Compatibility

V3.4/V1.73 shall support normal field deployment ordering:

- V3.4 MAINs with V1.72 CONTROL during staged MAIN-first flash;
- V3.3 MAINs with V1.73 CONTROL during rollback or CONTROL-first tests;
- V3.2 MAINs with V1.73 CONTROL, where diagnostics MAIN identity is
  unavailable and must time out cleanly;
- V3.4 MAINs with V1.71 CONTROL behavior where filename/identity features are
  not available.

The minimum simulator matrix is:

- V1.73 + V3.4 on PB1/PB2;
- V1.73 + V3.3 on PB1/PB2;
- V1.72 + V3.4 on PB1/PB2;
- V1.73 + V3.2 on PB1/PB2 with no-identity timeout;
- V1.71 + V3.4 for old-CONTROL compatibility.

Protocol tests shall structurally pin command IDs and BF reply ranges used by
filename and diagnostics identity traffic: only filename emitters may use
`BF/2D..4E`, diagnostics identity must stay in `BF/4F..53`, and `cmd 0x25` /
`cmd 0x26` dispatch constants must remain pinned.  Legacy echo bytes `0x2D`,
`0x2E`, `0x2F`, and `0x4E` must also be covered by adversarial old-MAIN tests.

## Test Requirements

The implementation shall add or update tests that cover:

- V3.4/V1.73 source identity, path constants, builders, and release artifacts;
- V3.4/V1.73 simulator/listing wiring, proving new HEX/listing artifacts are
  loaded and not silently mapped to V3.3/V1.72;
- V3.4/V1.73 build scripts updating all identity literals consistently;
- MAIN cold-init clear coverage, especially `preset_job_*`;
- MAIN chain TX arbitration coverage for every sender;
- MAIN filename busy/cancel policy and writer cancellation;
- MAIN filename fresh-id replacement, same-id duplicate idempotence, stale-frame
  rejection, and measured 2 ms frame pacing;
- MAIN same-id/different-derived-source duplicates treated as idempotent/ignored
  unless a new wire epoch is added;
- MAIN filename generation wraparound/no-reuse behavior with stale-burst tests;
- MAIN I2C timeout abort/retry contract and SEN/PEN classification;
- MAIN async preset APPLY timeout BF/08 surfacing, diagnostics counters,
  non-overlapping `i2c_recover_flags`, and same-entry retry;
- CONTROL non-modal service tick versus modal page loops;
- CONTROL Preset re-entry with no sampled row-0 blank while row 1 contains a
  filename/cache character;
- CONTROL same-slot cache reuse with zero fresh filename queries;
- CONTROL parser BSR tail and parser-gap wrapper structure;
- CONTROL WAITING/reconnect shared lifecycle coverage;
- RAM bank safety checker coverage for new aliases/ranges/contracts;
- mixed-version compatibility gates proving V3.3/V1.72 behavior is preserved
  and staged V3.4/V1.72 plus V3.3/V1.73 deployment is safe;
- V1.73 old/pre-feature MAIN filename echo adversarial cases for legacy bytes
  `0x2D`, `0x2E`, `0x2F`, and `0x4E`;
- `tests/sim/test_dlcp_v34_release_flash.py`, mirroring V3.3 flash-wrapper
  expectations for canonical path, warning text, explicit left/right routing,
  info-only passthrough, missing-capture warning, and explicit-route failure;
- CONTROL safe-flash tests proving the default is
  `firmware/patched/releases/DLCP_Control_V1.73.hex` after promotion, while
  explicit `--hex firmware/patched/releases/DLCP_Control_V1.72.hex` remains
  usable for rollback.

RAM safety regression shall run old and new targets together:

```sh
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py \
  --target main-v33 --target control-v172 --target main-v34 --target control-v173
```

At minimum, focused simulator tests shall run before broad gates.  Full
simulator tests are required before release-ready status.

## Size Requirements

MAIN V3.4 size must be measured against a clean current V3.3 reassembly
performed during the implementation.  Do not rely on historical ledger rows as
the acceptance baseline because the checked-in ledger contains multiple
optimization-era measurements.  Use the same metrics as the V3.3 size ledger:

- `used_bytes_pre_preset_b`;
- `last_used_pre_preset_b`;
- `free_bytes_before_0x4C00`;
- byte-identical or explained program-byte diff in `0x1000..0x4BFF`;
- listing/object-word end address before `org 0x4C00`.

Any MAIN growth must be tied to a necessary bug fix and accepted explicitly in
the implementation evidence.  Pure source hygiene should assemble byte-for-byte
or shrink.  The original refactoring target was `free_object_words >= 64`, but
the current promoted V3.4 field-fix line intentionally accepted a tighter floor:
at least 10 free bytes before `org 0x4C00` by the listing-fit metric.  The
release cannot proceed with unexplained growth or with less than the current
numeric floor.

Measure after each CONTROL work unit that touches app code.  CONTROL V1.73
shall record app-space growth and prove it remains below
`control_release_metadata` and the bootloader/pin region constraints already
guarded by existing tests.  The size gate shall fail on overlap or on an
unreviewed approach to those regions.  V1.73 must satisfy
`free_object_words >= 64` (`byte_margin >= 128`) between the last app-code word
and `control_release_metadata`, and separately before any bootloader/pin/config
boundary by the listing-fit metric.

## Deployment Policy

Implementation and simulator verification do not require hardware flashing.

If live flashing is later approved, use role-safe MAIN flashing only:

After every `identify-mains --require-left-right` command, refresh/export
`LEFT_HID` and `RIGHT_HID` from the latest identify output before using either
path.  Do not reuse HID paths across USB re-enumeration.

```sh
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py detect
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
# refresh/export LEFT_HID and RIGHT_HID from the latest identify output
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --path "$LEFT_HID" --left
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --path "$RIGHT_HID" --right
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
# refresh/export LEFT_HID and RIGHT_HID from the latest identify output
# Power-cycle CONTROL while holding UP+DOWN for ~6s to enter bootloader; do not press SELECT.
# CONTROL re-enumerates independently; do not reuse MAIN HID paths for CONTROL flashing.
scripts/flash_control_safe.sh --hex firmware/patched/releases/DLCP_Control_V1.73.hex --preflight-only
scripts/flash_control_safe.sh --hex firmware/patched/releases/DLCP_Control_V1.73.hex
# Cold power-cycle CONTROL plus both MAINs before smoke probes.
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
# refresh/export LEFT_HID and RIGHT_HID from the latest identify output
```

Post-flash checks, if live deploy runs:

```sh
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$LEFT_HID" --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$RIGHT_HID" --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_preset.py --path "$LEFT_HID" --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_preset.py --path "$RIGHT_HID" --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_diag.py --json --ch-map LEFT="$LEFT_HID" --ch-map RIGHT="$RIGHT_HID"
```

Hardware acceptance for Preset filename LCD still requires OCR/raw capture
evidence; a blank row alone is not proof.

If hardware smoke runs, first verify app-resident PB1/PB2 Diagnostics MAIN
identity reports `v3.4 xNN`, then verify Preset page A/B row0 and filename
rows, Preset B -> next menu -> standby -> wake -> Preset, and rollback commands.
Record exact flash commands, HID paths/routes, release identities, LCD
probe/OCR or raw LCD captures, and a JSON/text report artifact under
`artifacts/`.

## Acceptance Criteria

- `docs/REFACTORING_V34_V173_SPEC.md` and
  `docs/IMPL_REFACTORING_V34_V173.md` are reviewed with 5 independent roles
  and have no unresolved High or Medium findings.
- V3.4 and V1.73 source/build/release paths are added without breaking
  V3.3/V1.72 compatibility tests.
- V3.4/V1.73 simulator path support, listing lookup, and chain helper coverage
  are explicit and tested.
- The Preset LCD bug remains solved through lifecycle ordering, not row redraw
  or retry recovery.
- MAIN chain TX arbitration prevents filename replies from interleaving with
  forwarded chain frames.
- MAIN filename reply pacing and deterministic replacement policy pass under
  diagnostics/status interleaving.
- MAIN reset/cold-init cannot start with stale `preset_job_*` state.
- MAIN I2C recovery has an explicit abort/retry contract and correct SEN/PEN
  classification.
- CONTROL page loops use one non-modal service tick and shared exit/lifecycle
  predicates.
- RAM bank safety passes for V3.4/V1.73 and remains enforced in builders/tests.
- Mixed-version deploy/rollback simulator matrix passes.
- Focused tests, release-builder tests, RAM safety tests, Preset filename LCD
  tests, Diagnostics identity tests, and full `tests/sim` pass or have
  documented existing skips/xfails.
- MAIN and CONTROL size deltas are recorded and acceptable.
- Hardware deploy is recorded as not run unless separately approved and run.
