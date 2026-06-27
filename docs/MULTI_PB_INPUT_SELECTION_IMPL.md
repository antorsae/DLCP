# Multi-PB Input Selection Unified Persistence IMPL

Date: 2026-06-27
Status: Implemented on CONTROL V1.73 rev `0x57`; hardware gates pending
Source spec: `docs/MULTI_PB_INPUT_SELECTION.md`
Target release line: CONTROL V1.73 and MAIN V3.5

## Goal

Implement the consolidated input-persistence model without minting new release
names:

```text
CONTROL EEPROM = user input intent
MAIN RAM/EEPROM = applied device state, cache, and fallback
```

The user-visible behavior stays the same: PB1 has its own input screen, PB2 can
be `Same as PB1` or a concrete independent input, and the field target PB1
S/PDIF + PB2 AES must survive power cycles. The design change is that PB1 and
PB2 no longer persist through different ownership paths.

Current artifact boundary: the canonical V1.73 artifact has split-input runtime
behavior plus CONTROL-owned PB1 and PB2 persistence. MAIN remains V3.5 and was
not changed for this work.

## Required Reading

Primary required reading before implementation:

- `AGENTS.md`
- `README.md`
- `CODING_STYLE.md`
- `docs/MULTI_PB_INPUT_SELECTION.md`
- `docs/HARDWARE_TEST.md`
- `docs/V16B_SOURCE_REWRITE_SPEC.md`
- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `tests/sim/test_v173_multi_pb_input_selection.py`
- `src/dlcp_fw/flash/dlcp_control_flash.py`
- `src/dlcp_fw/sim/dlcp_sim_native.py`

Context reading if MAIN or route behavior is touched:

- `src/dlcp_fw/asm/dlcp_main_v35.asm`
- `tests/sim/test_v32_main_i2c_service_2100_tables.py`

This docs consolidation deletes the old split runtime spec and persistence
addendum. Do not reintroduce references to those retired files.

## Current Implementation Evidence

CONTROL V1.73 rev `0x57` contains split-input runtime behavior and PB1/PB2
CONTROL-owned persistence:

- `EEPROM_PB1_INPUT_ADDR equ 0x5E`
- `EEPROM_PB2_INPUT_ADDR equ 0x5F`
- `input_pb1_persist_load`
- `input_pb1_persist_save_if_dirty`
- `input_pb1_persist_apply_after_connect`
- `input_pb2_persist_load`
- `input_pb2_persist_save_if_dirty`
- `settings_load_eeprom` calls PB1 and PB2 load after stock settings load.
- `settings_save_eeprom` calls the unified input persistence save helper after
  the stock settings save block.
- PB1 concrete values are encoded as `0xC0..0xC8`.
- PB2 `Same as PB1` is encoded as `0xA0`.
- PB2 concrete values are encoded as `0xB0..0xB8`.
- Invalid PB1 bytes defer migration/write unless a validated MAIN0/PB1 source
  is available; the current chain exposes only ambiguous BF/06, so migration is
  deferred.
- Invalid PB2 bytes decode as linked / `Same as PB1`.

Current CONTROL V1.73 also contains the runtime pieces that must be kept:

- PB1 and PB2 input screens are adjacent in the setup menu.
- PB2 defaults to linked.
- PB2 concrete mode uses addressed command `0x06` frames.
- Linked mode may broadcast PB1 input intent.
- PB2 discovery/fallback code prevents PB1 from becoming unusable when PB2 is
  not yet seen.
- RC5 `0x3F` toggles PB1 between Optical and S/PDIF.

The previous gap was PB1 ownership. PB1 user changes now mark CONTROL EEPROM
`0x5E` dirty and persist through the same dirty-state service as PB2 `0x5F`.

## Non-Goals

- Do not create V1.74 CONTROL, V3.6 MAIN, or new canonical filenames.
- Do not change the command `0x06` input enum.
- Do not remove MAIN's existing input cache or EEPROM behavior.
- Do not make EEPROM writes immediate on every button edge.
- Do not change preset A/B behavior.
- Do not change SRC4382 or TAS3108 routing except where needed to preserve
  existing input application.
- Do not touch MAIN for this persistence consolidation unless a regression is
  discovered that cannot be fixed in CONTROL.

## Implementation Plan

### WU0 - Documentation consolidation

Completed in this docs change:

- Replace the old three-doc spec/persistence split with
  `docs/MULTI_PB_INPUT_SELECTION.md`.
- Keep the implementation ledger at `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`.
- Delete the stale split runtime spec.
- Delete the stale persistence addendum.
- Remove stale references.

### WU1 - EEPROM and RAM ownership audit

Confirm the new CONTROL EEPROM byte is safe:

- Use `rg` and source inspection to prove CONTROL EEPROM `0x5E` is not already
  owned by another V1.73 setting.
- Confirm `0x5F` remains PB2 input mode.
- Confirm CONTROL release flashing preserves EEPROM and does not initialize
  `0x5E` or `0x5F`.
- Record the proof in this IMPL after implementation.

Confirm the new RAM state is safe:

- Add or allocate `input_pending_pb1`.
- Add PB1 persistence flags without colliding with existing `input_split_flags`
  semantics.
- Run the existing RAM-bank safety gate for `control-v173`.

Recommended flag allocation if the audit confirms room:

| Flag | Meaning |
| --- | --- |
| `INPUT_SPLIT_FLAG_PB1_PENDING_VALID` | CONTROL EEPROM `0x5E` decoded to a valid PB1 intent |
| `INPUT_SPLIT_FLAG_PB1_PERSIST_DIRTY` | PB1 CONTROL EEPROM byte needs save |

Use existing PB2 flags unchanged.

### Touchpoint map

Use these V1.73 source regions as the starting map; update exact line numbers in
the implementation evidence if they move:

| Area | Current label / file region |
| --- | --- |
| CONTROL EEPROM save | `settings_save_eeprom`, current PB2 call to `input_pb2_persist_save_if_dirty` |
| CONTROL EEPROM load | `settings_load_eeprom`, current PB2 call to `input_pb2_persist_load` |
| PB2 persistence helpers | `input_pb2_persist_load`, `input_pb2_persist_encode_current`, `input_pb2_persist_save_if_dirty` |
| Cold WAITING sentinels | `boot_waiting_for_dlcp_loop`; do not seed `input_select_cache` from EEPROM before this exits |
| Reconnect completion | `reconnect_wait_loop` / `v171_reconnect_wait_done`; reconnect completion is BF/05 poll-answer based |
| Full-sync pacing | `full_sync_burst` step 2 to `input_frame_send_split_sync`; keep one frame per call |
| Input frame routing | `input_frame_send`, `input_frame_send_current_input_page`, `input_frame_send_targeted` |
| PB2 discovery/fallback | `input_split_latch_pb2_seen`, `INPUT_SPLIT_FLAG_PB2_FALLBACK_ACTIVE` |
| Front-panel commit | `input_commit_selected_input_intent` |
| IR PB1 toggle | RC5 `0x3F` / `RC5_INPUT_OPTICAL_SPDIF_TOGGLE` dispatch path |
| Configured input shortcuts | existing `IR_CMD_INPUT_NEXT` / `IR_CMD_INPUT_PREVIOUS` paths if they change PB1 intent |

### WU2 - Add PB1 CONTROL EEPROM decoder

Add:

```asm
EEPROM_PB1_INPUT_ADDR equ 0x5E
```

Decoder rules:

- `0xC0..0xC8` -> PB1 intent `0x00..0x08`, mark PB1 pending valid.
- every other byte -> no valid CONTROL PB1 intent yet.

Do not write the decoded PB1 value directly into `input_select_cache` during
`settings_load_eeprom`. Keep the WAITING sentinels intact.

The decoded value should land in separate pending RAM, for example
`input_pending_pb1`, plus a valid flag.

Use the existing command `0x06` enum. The field target is PB1 S/PDIF as
`0x5E = 0xC5`; PB2 AES remains `0x5F = 0xB7`.

### WU3 - Apply PB1 intent after handshake

Apply PB1 intent only after an existing connection invariant is true:

- cold boot: after `boot_waiting_for_dlcp_loop` exits by the existing sentinel
  rules,
- reconnect: after `v171_reconnect_wait_done` has accepted a fresh BF/05
  poll-answer mask.

Do not apply PB1 intent merely because one BF/06 frame arrived. At the safe
point:

- If PB1 pending valid is set, copy pending PB1 into the PB1 runtime input
  cache and send command `0x06` according to PB2 mode.
- If PB2 is linked, apply PB1 to both MAINs.
- If PB2 is concrete, apply PB1 only to MAIN0 and leave PB2 concrete intact.
- Do not let a stale MAIN BF/06 overwrite valid CONTROL-owned PB1.

If PB1 pending valid is not set:

- Use only a validated MAIN0/PB1 migration source.
- Store that value in PB1 runtime state.
- Mark PB1 dirty so the dirty save service writes `0xC0 + input`.
- Use compare-before-write so repeated boots do not churn EEPROM.

The migration source is valid only when source is known to be MAIN0/PB1,
command is `0x06`, and payload is in the closed allowlist `0x00..0x08`. If the
implementation can see only ambiguous BF/06 traffic, defer migration and leave
PB1 dirty clear rather than writing CONTROL EEPROM from an uncertain source.

This preserves existing deployed units when a MAIN0 source can be validated:
their MAIN input cache becomes the first CONTROL-owned PB1 value after the
updated CONTROL firmware runs. If source cannot be validated, migration is
deferred until a user intent path writes PB1 through CONTROL.

### WU4 - Unify persistence save helpers

Replace the PB2-only save helper with a small input persistence save routine
that handles PB1 and PB2:

- PB1 dirty: encode `0xC0 + input`, compare with EEPROM `0x5E`, write only if
  changed, then clear PB1 dirty only after the byte is equal or the write is
  known to have completed successfully.
- PB2 dirty: keep existing `0xA0` / `0xB0..0xB8` encoding at EEPROM `0x5F`,
  compare before write, then clear PB2 dirty only after equality/success.

Keep the call site in `settings_save_eeprom` so both PB1 and PB2 share the same
dirty-state save service and user caveat.

### WU5 - Mark PB1 dirty from every PB1 user-intent path

Audit and update all PB1 input-changing paths:

- `Input PB1` front-panel screen selection.
- RC5 `0x3F` Optical/S/PDIF toggle.
- Configured input next/previous shortcuts if they change PB1 intent.

Host/USB writes to MAIN state are not automatically CONTROL user intent. Include
a host path only if the implementation proves it is the same user-facing PB1
input setting that the front panel edits.

Each path must:

- update the same PB1 runtime value,
- set PB1 dirty,
- call the centralized input-send helper,
- respect PB2 linked vs concrete mode.

Navigation that only previews rows must not dirty EEPROM.

### WU6 - Preserve PB2 behavior

Keep existing PB2 semantics:

- erased or invalid `0x5F` means linked,
- PB2 linked row stores `0xA0`,
- PB2 concrete stores `0xB0..0xB8`,
- PB2 DOWN navigation works from `Same as PB1` to concrete rows,
- PB2 concrete is not overwritten by PB1 changes,
- temporary runtime fallback may link PB2 when the current source-list class
  cannot represent the persisted concrete value, but this must not rewrite
  EEPROM `0x5F`.

Any refactor must retain the existing PB2 persistence tests and PB2 DOWN tests.

### WU7 - Tests

Add or update focused tests in `tests/sim/test_v173_multi_pb_input_selection.py`:

- PB1 CONTROL EEPROM `0x5E = 0xC5` boots to PB1 S/PDIF even when MAIN EEPROM
  has a stale different input.
- PB1 invalid/erased `0x5E` defers migration when BF/06 source is ambiguous;
  if a future implementation can prove MAIN0/PB1 source, it may write
  `0xC0 + value` only after the dirty save service.
- PB1 invalid/erased `0x5E` does not migrate invalid or ambiguous BF/06
  payloads `0x09`, `0x7F`, `0x80`, or `0xFF`.
- PB1 front-panel change marks PB1 dirty and eventually commits `0x5E`.
- PB1 RC5 `0x3F` toggle marks PB1 dirty and persists through power cycle.
- PB1 change with PB2 linked updates both MAINs and leaves PB2 EEPROM linked.
- PB1 change with PB2 concrete updates only MAIN0 and leaves PB2 concrete.
- PB2 concrete AES at `0x5F = 0xB7` plus PB1 S/PDIF at `0x5E = 0xC5`
  survives cold boot.
- Invalid PB2 `0x5F` still decodes to linked.
- Repeated save-service runs and reconnect/full-sync cycles do not write EEPROM
  when `0x5E` and `0x5F` already match the encoded runtime intent.
- CONTROL release-flash safety preserves `0x5E` and `0x5F`.
- Updated CONTROL with stock/legacy MAIN still boots single-PB, defers PB1
  migration unless a valid source is proven, and uses broadcast `cmd 0x06`
  before PB2 discovery.

Run the earlier MAIN route-table/channel-6 tests only if MAIN or routing
behavior changes:

- PB2 AES route payload still uses `0xFF, 0xF5, 0x06, 0x14, 0x40, 0x08`.
- The route table lookup does not regress across flash page boundaries.

Expected focused commands:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim/test_dlcp_control_flash_safety.py -q
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v173_release.py
```

If MAIN or routing changes, also run:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim/test_v32_main_i2c_service_2100_tables.py -q
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim/test_flash_table_page_carry_audit.py -q
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v35_release.py
```

### WU8 - Build and release artifacts

If CONTROL source changes:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v173_release.py
```

If MAIN source changes:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v35_release.py
```

Do not mint ad-hoc release filenames. The canonical artifacts are:

- `firmware/patched/releases/DLCP_Control_V1.73.hex`
- `firmware/patched/releases/DLCP_Firmware_V3.5.hex`

Record the resulting revision bytes in this IMPL after implementation.

### WU9 - Evidence capture

For every persistence test or hardware gate, capture these observables when the
tooling supports them:

- CONTROL EEPROM `0x5E` and `0x5F` before and after save,
- PB1/PB2 dirty flags before and after the save service,
- route/cmd/data frames emitted for PB1 and PB2,
- the validated migration source used for PB1, including payload,
- the cold WAITING or reconnect transition point used before applying PB1,
- final PB1/PB2 applied input from MAIN-visible state.

## Acceptance Checklist

- [x] `docs/MULTI_PB_INPUT_SELECTION.md` is the only behavior spec.
- [x] `docs/MULTI_PB_INPUT_SELECTION_IMPL.md` is the only implementation ledger.
- [x] No references remain to deleted multi-PB spec/persistence docs.
- [x] CONTROL defines and decodes PB1 EEPROM `0x5E`.
- [x] CONTROL keeps PB2 EEPROM `0x5F` behavior compatible.
- [x] PB1 and PB2 use the same dirty-state save service.
- [x] PB1 pending value does not break WAITING sentinels.
- [x] Valid CONTROL PB1 intent overrides stale MAIN input cache after handshake.
- [x] Invalid CONTROL PB1 intent migrates only from validated MAIN0/PB1 source
      or defers without writing.
- [x] PB1 RC5 toggle persists through CONTROL EEPROM.
- [x] PB2 concrete mode remains independent of PB1 changes.
- [x] V1.73 canonical build script was used for CONTROL source changes; V3.5
      MAIN was not changed for this implementation.
- [x] Focused sim/static tests pass.
- [x] Hardware gates are documented as pending or completed with evidence.
- [x] Review findings table has no open High or Medium findings.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| PB1 pending load corrupts WAITING handshake | Store PB1 decode in separate pending RAM; apply only after handshake |
| EEPROM `0x5E` collision | Perform source and EEPROM-layout audit before implementation |
| Excess EEPROM wear | Compare before write and reuse dirty-state save service |
| Migration changes existing units unexpectedly | Invalid `0x5E` imports only validated MAIN0 BF/06; otherwise migration defers |
| PB2 concrete overwritten by PB1 change | Centralized send helper must branch on PB2 linked/concrete mode |
| RC5 toggle bypasses persistence | Treat RC5 toggle as the same PB1 user-intent path as front panel |
| Release-flash loses settings | Keep CONTROL flash tool app-flash-only and add/preserve tests |

## Review Plan

Run eight independent review passes before implementation:

1. Simplicity and scope.
2. Correctness against firmware contracts.
3. Operations, release, and tests.
4. UX and operator mental model.
5. Safety and data-integrity.
6. Performance, timing, and EEPROM endurance.
7. Migration and backward compatibility.
8. Maintainability and observability.

High and Medium findings must be resolved in this IMPL before implementation
starts. Low findings may remain if they are explicitly listed with rationale.

## Review Findings

| ID | Severity | Pass | Status | Resolution |
| --- | --- | --- | --- | --- |
| R1 | Medium | Safety/data | Resolved | WU3 now requires validated MAIN0/PB1 `cmd 0x06` source and invalid BF/06 negative tests. |
| R2 | Medium | Safety/data | Resolved | WU4 now clears dirty only after EEPROM equality or successful commit. |
| R3 | Medium | Simplicity/scope | Resolved | Spec and IMPL now define this as CONTROL-only unless a MAIN regression is discovered. |
| R4 | Medium | Simplicity/scope | Resolved | WU3 now names cold WAITING exit and reconnect BF/05 poll-answer completion invariants. |
| R5 | Medium | Simplicity/scope | Resolved | WU5 narrows PB1 dirty paths and treats host writes as excluded unless proven user intent. |
| R6 | Medium | UX/operator | Resolved | Status now states target behavior and current artifact boundary. |
| R7 | Medium | UX/operator | Resolved | Hardware gates now include first-run migration from invalid `0x5E`. |
| R8 | Medium | Operations | Resolved | HARDWARE_TEST stale PB2 persistence wording updated; gates include RAM safety and builder commands. |
| R9 | Medium | Maintainability | Resolved | Added touchpoint map and WU9 required observables. |
| R10 | High | Compatibility/correctness/timing | Resolved | Corrected command `0x06` enum; field target is `0x5E = 0xC5`, `0x5F = 0xB7`. |
| R11 | Medium | Compatibility | Resolved | Added stock/legacy MAIN compatibility gate. |
| R12 | Medium | Timing | Resolved | Full-sync now explicitly preserves one-frame-per-call split-sync pacing. |
| R13 | Medium | Timing | Resolved | Added no-churn EEPROM tests for clean save/reconnect/full-sync cycles. |
| R14 | Medium | Correctness | Resolved | Spec now distinguishes PB2 persisted concrete mode from temporary runtime fallback. |

Low findings intentionally left as notes:

- The retired split-doc filenames are not repeated verbatim so a mechanical
  stale-reference `rg` returns no matches.
- Broader context docs remain in required/context reading because assembly
  changes have high coupling, but only CONTROL files are in expected scope.

## Implementation Evidence

Implemented on 2026-06-27 on the existing CONTROL V1.73 line. MAIN V3.5 was
not changed for this work.

Changed implementation files:

- `src/dlcp_fw/asm/dlcp_control_ram.inc`
  - added PB1 pending RAM at physical `0x1BE`,
  - added `INPUT_SPLIT_FLAG_PB1_PENDING_VALID`,
  - added `INPUT_SPLIT_FLAG_PB1_PERSIST_DIRTY`.
- `src/dlcp_fw/asm/dlcp_control_v173.asm`
  - added PB1 EEPROM constants `0x5E` / `0xC0..0xC8`,
  - added PB1 load/save/apply helpers,
  - changed `settings_save_eeprom` to call unified input persistence save,
  - changed `settings_load_eeprom` to load PB1 and PB2 persistence,
  - applies valid PB1 pending intent after cold WAITING exit and reconnect
    completion,
  - marks PB1 dirty from front-panel PB1 selection, fixed RC5 `0x3F`, and
    configured input next/previous shortcuts,
  - preserved PB2 `0x5F` linked/concrete behavior.
- `firmware/patched/releases/DLCP_Control_V1.73.hex`
  - rebuilt by the canonical V1.73 builder.
- `tests/sim/test_v173_multi_pb_input_selection.py`
  - added PB1 `0x5E` decoder, valid restore, invalid/ambiguous BF/06
    quarantine, PB1 front-panel/F5/configured shortcut dirty-save coverage,
    PB1+PB2 no-churn EEPROM trace coverage, and canonical PB1 S/PDIF + PB2 AES
    channel-6 route regression.
- `tests/sim/test_dlcp_control_flash_safety.py`
  - added static proof that the control flash stream ignores EEPROM records at
    `0xF0005E` and `0xF0005F`.
- `docs/MULTI_PB_INPUT_SELECTION.md`
- `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`
- `docs/HARDWARE_TEST.md`
  - consolidated behavior/implementation docs and removed stale PB2
    non-persistence wording.

Build evidence:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v173_release.py
```

Result:

```text
built canonical V1.73 CONTROL release: firmware/patched/releases/DLCP_Control_V1.73.hex (current release rev 0x57)
```

Focused gate evidence:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q
# 163 passed in 1296.34s (0:21:36)

PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim/test_dlcp_control_flash_safety.py -q
# 27 passed in 0.84s

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
# RAM bank safety: OK (control-v173)
```

MAIN/routing gates were not run for this implementation because no MAIN source
or route-table code was changed. The existing multi-PB suite includes the
canonical PB1 S/PDIF + PB2 AES channel-6 route-payload regression against
MAIN V3.5.

Migration decision:

- Current CONTROL chain BF/06 traffic is ambiguous for PB1 migration; the code
  therefore defers invalid/erased `0x5E` migration and does not dirty CONTROL
  EEPROM from BF/06 unless a future implementation can prove MAIN0/PB1 source.
- Valid `0x5E` always wins over stale MAIN EEPROM after handshake.
- User-facing PB1 intent paths seed `0x5E` through the same dirty save service
  used by PB2 `0x5F`.

Hardware evidence:

- Live hardware gates are pending. Required field checks remain PB1 S/PDIF
  `0x5E = 0xC5`, PB2 AES `0x5F = 0xB7`, power-cycle persistence after dirty
  save, PB2 channel-6 audio, PB2 concrete independence after PB1 changes, RC5
  `0x3F` persistence, and release-flash settings preservation.
