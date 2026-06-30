# IMPL CONTROL Flash Relay Handshake Failure

Date: 2026-06-30
Status: Implemented - simulator-backed, live hardware not run
Source spec: `docs/CONTROL_FLASH_RELAY_HANDSHAKE_FAILURE.md`
Scope: MAIN V3.5 CONTROL-flash relay arming semantics, Python flasher error
handling, and simulator fidelity sufficient to prove current-bad to fixed-good
and fixed-good to newer-good CONTROL flash transitions.

## Implementation Result

Implemented on the MAIN V3.5 line only.  Canonical
`firmware/patched/releases/DLCP_Firmware_V3.5.hex` is now rev `0x009A`, SHA-256
`7d84601e588df6840c9f1d5d849cc7b74eaa9d0b07ec7c9f9c2c8487adfeb157`.
CONTROL V1.73 is rev `0x62` / build `20260630`, SHA-256
`5b1c5bf41ade024a6fdad1df8715a7952e9be630d64be7445a71b0c45e684b4a`.

Firmware/flasher changes:

- MAIN returns `42 12 ...` for unarmed CONTROL relay sessions instead of a
  success-looking `42 00 ...`.
- MAIN clears the relay-session flag with the relay accumulators.
- MAIN keeps `0x77BF` inside the flashable CONTROL app window and flushes the
  saved final `0x77B0` record at the exclusive `0x77C0` bootloader boundary.
- MAIN returns after each 30-byte HID relay payload instead of falling through
  into the CR/LF helper, so a partial downstream `:10` Intel HEX data record is
  not split at a HID report boundary.
- `dlcp_control_flash.py` aborts immediately on nonzero `0x42` status; `0x12`
  prints concise manual `UP+DOWN` bootloader guidance with no traceback.
- The native simulator can now run a full-chain MAIN HID report while CONTROL
  keeps executing, and models the EUSART `RCREG` latch plus 64-byte program
  erase rows needed by the real CONTROL bootloader path.

Implemented proof:

- Fast flasher/reject tests:
  `tests/sim/test_dlcp_control_flash_safety.py -m "not slow"` -> `32 passed`.
- Structural relay/listing tests:
  `tests/sim/test_v34_v173_refactoring_contracts.py -k "relay or listing_size"`
  -> `3 passed`.
- Slow full-chain relay simulations:
  `tests/sim/test_dlcp_control_flash_safety.py -k 'full_chain_fixed_main_flashes_control_v173_through_real_bootloader or full_chain_fixed_main_flashes_newer_v173_through_real_bootloader'`
  -> `2 passed, 32 deselected in 49.37s`; both current-bad to fixed-good and
  fixed-good to newer-good end at `41 00 aa`, verify CONTROL flash
  readback/metadata, and assert complete routed `:10` data records.
- Rust release simulator gate:
  `cargo test --release -p dlcp-sim` -> passed.
- `scripts/check_ram_access_safety.py --target main-v35` -> OK.
- Full simulator gate:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 32 -q` ->
  `2150 passed, 2 skipped, 2 xfailed, 7 warnings in 991.13s`.

Live hardware flash was not run as part of this implementation.

## Source Requirements

Goals:

- Forbid success-looking `42 00 00 00` responses when MAIN has not accepted
  CONTROL's `FW_Upd` bootloader prompt.
- Keep the HFD-compatible first-report contract: the first host `0x42` report
  already carries firmware bytes at payload offsets `2..31`.
- Make `dlcp_control_flash.py` abort immediately on relay-not-armed status with
  manual `UP+DOWN` bootloader guidance.
- Prove the fix in simulation, not only by static tests or hardware:
  - current bad behavior is reproduced by a stable negative fixture;
  - fixed MAIN refuses to silently stream when the relay is not armed;
  - fixed MAIN can flash CONTROL through a faithful full-chain simulation of
    the real MAIN relay and real CONTROL bootloader prompt/write path;
  - fixed-good to newer-good is simulated against real artifact bytes so future
    CONTROL updates do not regress to false ACKs or untested manual-only
    behavior.

Non-goals:

- No live flashing during implementation unless the user separately requests a
  hardware run.
- No V3.4 change.  This is a V3.5 line fix.
- No broad flash-protocol rewrite.
- No synthetic `41 00 aa` success model.  If the simulator cannot prove the
  real firmware path, this IMPL remains blocked; hardware evidence is field
  closure, not a substitute for the requested simulation proof.
- No CONTROL app-side `BF/18/01` handoff in this IMPL unless the full-chain
  simulator proves fixed-good to newer-good cannot be met without it and a
  separate mini-IMPL/review approves that extra CONTROL blast radius.

Explicit user decisions:

- `0x42` input streaming must not be accepted when the relay is unarmed.
- Simplicity, reliability, less code, and simulation fidelity outrank
  convenience features.
- Both current-bad to fixed-good and fixed-good to newer-good must be simulated.

## Required Docs Read

- `AGENTS.md`: canonical layout, current V3.5/V1.73 artifacts, builders, tests,
  and safe flash scripts.
- `README.md`: upgrade path, manual CONTROL bootloader requirement, simulator
  gates, and role-safe live flash commands.
- `CODING_STYLE.md`: assembly style and verification rules.
- `docs/CONTROL_FLASH_RELAY_HANDSHAKE_FAILURE.md`: source incident/spec.
- `docs/analysis/FIRMWARE_UPDATE_MECHANISM.md`: HFD `0x42`/`0x41` contract,
  first-report payload offsets, and old CONTROL app-handoff limitations.
- `docs/TEST_ROBUSTNESS_SPEC.md` and `docs/TEST_ROBUSTNESS_IMPL.md`:
  canonical artifact parity, negative proof, and hardware-incident promotion.
- `docs/TEST_INCIDENTS.md`: `TR-20260630-003`.
- `docs/SIMULATION.md`: Rust `Chain` facade and current simulator API limits.
- `docs/HARDWARE_TEST.md`: role-safe relay MAIN path and live smoke rules.
- `docs/IMPL_V171_V32_BUG_LEDGER.md`: live evidence that manual bootloader mode
  can complete with `41 00 aa`.

## Current Implementation Evidence

- `src/dlcp_fw/asm/dlcp_main_v35.asm`
  - `fw_update_start_relay_handshake` sends `BF/18/01`, reads a prompt, and sets
    `fw_update_relay_session_active_b0` only after matching expected bytes.
  - Current inactive-session code branches to
    `hid_command_dispatch__emit_opcode_status`, which stages a normal `0x42`
    response and can return `42 00...` without calling `fw_update_relay`.
  - `stage_hid_ep1_in_report_from_selector` falls to an empty reply for selector
    `0x42`, so writing a new status byte before this generic stager would be
    clobbered.
  - `hid_command_dispatch__validate_fw_update_signature` keeps final `0x41`
    failure byte `0x11` on CRC mismatch.
- `src/dlcp_fw/asm/dlcp_main_ram.inc`
  - Relay state is stable at `fw_update_relay_session_active_b0 == 0x0CB`.
  - Signature accumulator is `0x07C/0x07D`.
- `src/dlcp_fw/flash/dlcp_control_flash.py`
  - `build_control_stream()` creates the `0x0000..0x77BF` stream.
  - The stream loop sends 30 bytes per `0x42` report and currently validates
    only `resp[0]`.
- `tests/sim/test_dlcp_control_flash_safety.py`
  - Existing tests cover static preflight, HFD first-report shape, timeout
    guidance, and wrapper path selection.
  - They do not cover `0x42` relay-not-armed status or full-chain CONTROL relay
    flash simulation.
- `src/dlcp_fw/sim/dlcp_sim_native.py`
  - `Chain.firmware_hid_report()` exercises the real MAIN app HID dispatcher but
    is not enough by itself to prove CONTROL bootloader prompt timing or flash
    writes.
- `src/dlcp_fw/flash/sim_backend.py`
  - Existing `SimHidBackend` models MAIN self-flash-style `0x40/0x41`; it must
    not be reused as CONTROL-through-MAIN proof.

## Gap Analysis

Missing or weak:

- MAIN needs a non-clobbering inactive-relay `0x42` error path.
- Host flasher needs early rejection for nonzero `0x42` stream status.
- The simulator lacks a focused full-chain CONTROL relay flash harness that
  proves real prompt consumption, relay-session set, CRC match, final `41 00 aa`,
  and target CONTROL metadata/bytes.
- Old-bug proof must not depend on `HEAD^` or a local checked-out artifact.
- Public release metadata is already stale in `README.md`; docs must be
  reconciled from canonical HEX values.

## Proposed Implementation

### WU1 - Define The Minimal Status Contract

Document and implement:

- `0x42 resp[1] == 0x00`: relay was armed and this stream report was accepted.
- `0x42 resp[1] == 0x12`: MAIN did not accept CONTROL's bootloader prompt; no
  payload bytes were relayed for this report.
- Existing `0x41 resp[1] == 0x11` remains the final CRC mismatch status.

This is guaranteed for `dlcp_control_flash.py`.  Do not claim HFD fails fast on
`resp[1]` unless a parser test proves it; HFD remains documented as requiring
manual bootloader entry.

### WU2 - MAIN V3.5 Non-Clobbering Fail-Fast Path

Update only `src/dlcp_fw/asm/dlcp_main_v35.asm` for the mandatory firmware
change.

Required sequence for inactive relay:

1. Attempt the existing handshake and prompt match.
2. If `fw_update_relay_session_active_b0` is still clear, clear relay
   accumulators and directly clear `fw_update_relay_session_active_b0`.  Do not
   assume `fw_update_clear_relay_status_accumulators` clears the session flag;
   it currently clears only CRC/checksum/address accumulators.
3. Stage or write the `0x42` response first.
4. Write `usb_hid_ep1_in_report_byte1_b1 = 0x12` after any generic response
   staging, or write response bytes 0 and 1 directly.
5. Branch to `hid_command_dispatch__clear_opcode_and_return`.
6. Do not call `fw_update_relay`.

Do not write `0x12` before `stage_hid_ep1_in_report_from_selector`; selector
`0x42` currently falls to empty-reply staging and clears byte 1.

Prompt robustness:

- Keep fail-fast small, but do not mark the incident fixed unless the full-chain
  simulator success tests in WU5 pass.
- If those tests show MAIN misses a valid simulated `:FW_Upd\r\n`, add the
  smallest bounded prompt retry/resync or in-record `FW_Upd` matcher needed to
  accept the real bootloader prompt.  Record code-size delta and keep the
  maximum wait bounded by the flasher report timeout.

### WU3 - Python Flasher Early Abort

Update `src/dlcp_fw/flash/dlcp_control_flash.py`:

- After every `0x42` response, reject nonzero `resp[1]` immediately.
- Introduce a small typed exception such as `ControlRelayNotArmedError` for
  `resp[1] == 0x12`; keep other unexpected stream statuses as ordinary
  `RuntimeError` or a shared stream-status error only if a second caller needs
  it.
- For `resp[1] == 0x12`, raise/print an actionable error:
  - relay did not arm;
  - the payload was not fully streamed;
  - enter CONTROL bootloader with `UP+DOWN` for at least 6 seconds, do not press
    `SELECT`;
  - verify the selected MAIN HID is physically connected to CONTROL.
- Catch `ControlRelayNotArmedError` in `main()` so the CLI prints concise
  guidance to stderr and exits nonzero without a Python traceback.  Tests must
  cover both direct `flash_control()` behavior and CLI-facing output.
- Improve final `41 11...` error text to mention that old MAIN firmware may
  have silently streamed while relay state stayed clear.
- Do not automatically retry the same payload.

### WU4 - Full-Chain CONTROL Relay Simulator Harness

Add the smallest simulator/harness work needed to drive a real CONTROL flash
through MAIN:

- Use real `Chain` cores loaded from CONTROL and MAIN HEX artifacts.
- Drive host `0x42`/`0x41` reports through the MAIN app HID service.
- Advance CONTROL and MAIN together so CONTROL bootloader prompt bytes can be
  produced and consumed by MAIN's `uart_rx_with_framing`.
- Use real CONTROL bootloader code for writes whenever possible.
- Verify target CONTROL flash bytes and release metadata from simulator memory
  after final `41 00 aa`.
- The success contract must include prompt cadence, Intel HEX record parsing,
  per-record ACK/checksum responses, CONTROL flash mutation, EOF/finalize
  behavior, and post-stream metadata readback.  A prompt-only hook is not enough.

Allowed implementation shapes, in preferred order:

1. Extend the native simulator/facade minimally so a test can put CONTROL into
   manual bootloader state and step a full host-report exchange while all cores
   keep running.
2. If existing bootloader code runs but prompt timing is dropped, fix the UART
   event/prompt timing fidelity instead of adding a Python bootloader model.
3. Only if the real CONTROL bootloader cannot be run in sim for a documented
   silicon-model reason, add a narrow native bootloader peripheral/harness that
   consumes and writes the same Intel HEX records.  It must expose its synthetic
   boundary in the test name and cannot satisfy "real bootloader" acceptance
   without a follow-up fidelity issue.

Disallowed:

- Returning `41 00 aa` from Python based only on `crc_stream()`.
- Reusing MAIN self-flash `SimHidBackend` as CONTROL relay proof.
- Declaring hardware-only success while leaving requested simulator transitions
  unimplemented.

### WU5 - Deterministic Regression Tests

Add focused tests in `tests/sim/test_dlcp_control_flash_safety.py` and V3.5
structural coverage where appropriate.

1. `test_v35_control_relay_unarmed_first_report_fails_fast`
   - Fixed V3.5 MAIN, current V1.73 CONTROL app mode, first `0x42`.
   - Assert `resp[:2] == b"\x42\x12"`, no second report, session `0`,
     signature `0x0000`.
   - Fails on old behavior because it returns `42 00...`.

2. `test_flash_control_aborts_on_relay_not_armed_status`
   - Fake HID returns `42 12...` on first stream report.
   - Assert `flash_control()` writes one report and raises manual bootloader
     guidance.

3. `test_v35_relay_inactive_status_is_not_clobbered_by_empty_reply_stager`
   - V3.5 source/listing structural test.
   - Assert inactive-session reject writes status after generic staging or writes
     response bytes directly, and cannot branch from the `0x12` write into the
     empty `0x42` success stager.
   - Assert the reject path clears `fw_update_relay_session_active_b0` and does
     not rely on the accumulator helper for that session clear.

4. `test_control_flash_old_behavior_fixture_reproduces_false_ack`
   - Stable negative proof, not `HEAD^`.
   - Prefer deterministic temp source mutation that restores the old inactive
     branch to `hid_command_dispatch__emit_opcode_status`; alternatively use a
     checked-in non-release bad fixture with SHA and provenance.
   - If using temp assembly, emit a sibling `.lst` and assert the HID dispatcher
     symbols resolve from that listing; also assert `dispatch_hits > 0` so stale
     fallback PCs cannot create a false harness result.
   - Assert the bad fixture returns `42 00...`, session `0`, signature `0x0000`,
     and final `41 11...`.

5. `test_fixed_main_manual_bootloader_control_flash_reaches_4100aa`
   - Full-chain sim, fixed V3.5 MAIN, current-bad V1.73 CONTROL initial image,
     new-good V1.73 target stream.
   - Mark `pytest.mark.slow`; this is a full 1022-report relay simulation and
     is mandatory before publishing/acceptance, not part of the fast edit loop.
   - Put CONTROL in simulated manual `UP+DOWN` bootloader state.
   - Assert real prompt consumption, relay session set, final `41 00 aa`, and
     target CONTROL release metadata/bytes.

6. `test_fixed_good_to_newer_good_control_flash_reaches_4100aa`
   - Full-chain sim, fixed-good CONTROL initial image and a newer target image
     generated in `tmp_path` through the release-builder path, for example
     `build_v173_release(asm_path=tmp_asm, output_hex=tmp_hex,
     build_date=...)`.
   - Mark `pytest.mark.slow`; this is the second full-stream publish gate.
   - If using temp MAIN or CONTROL artifacts, emit/read matching listings or
     metadata from the generated files and assert the simulator did not fall
     back to stale symbol addresses.
   - A metadata-only mutation may be kept as supplemental relay byte-transport
     coverage, but it cannot satisfy newer-good acceptance.  If retained, it
     must run `detect_static_hex_control_release_info` and bootloader preflight
     on the generated target.
   - Prefer app-mode handoff only if the real current CONTROL supports it or a
     separately reviewed CONTROL handoff mini-IMPL is accepted; otherwise use
     simulated manual bootloader but name the test as manual-mode relay
     coverage, not app-handoff coverage.
   - Assert final `41 00 aa` and target metadata/bytes.

Pin explicit simulator step budgets for each helper path.  Timeout is a test
failure with its own message, not an accepted firmware status.

### WU6 - V3.5 Build, Size, And Artifact Gates

Before publishing:

- Temp-assemble first when iterating.
- Add/extend a V3.5 listing/headroom test.  V3.4 structural tests are not enough.
  The V3.5 listing gate must enforce `min_margin >= 1700` bytes before
  `org 0x4C00` against the current ~1750-byte baseline.  Any lower floor needs
  an explicit IMPL update with measured delta and rationale before publish.
- Run RAM safety with the real script:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35
```

When publishing canonical MAIN:

```bash
.venv_ep0/bin/python scripts/build_v35_release.py
```

If a separately reviewed CONTROL app-handoff change is added, also run:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
.venv_ep0/bin/python scripts/build_v173_release.py
scripts/flash_control_safe.sh --preflight-only
```

### WU7 - Docs And Artifact Metadata Reconciliation

Unconditionally parse canonical artifact metadata and reconcile public docs:

- `README.md`
- `AGENTS.md`
- `docs/CONTROL_FLASH_RELAY_HANDSHAKE_FAILURE.md`
- `docs/TEST_ROBUSTNESS_IMPL.md`
- `docs/TEST_INCIDENTS.md`
- `docs/HARDWARE_TEST.md`
- `docs/analysis/FIRMWARE_UPDATE_MECHANISM.md`

README currently lags current artifacts, so this is required even if CONTROL is
not rebuilt.  Record artifact-derived MAIN rev, CONTROL rev/build, SHA256, and
the exact tests that prove the relay contract.  Also scan/update any other
public "current canonical" metadata claims encountered during the edit.

## Likely Files

Code:

- `src/dlcp_fw/asm/dlcp_main_v35.asm`
- `src/dlcp_fw/flash/dlcp_control_flash.py`
- `src/dlcp_fw/sim/dlcp_sim_native.py`
- `crates/dlcp-sim-py/src/lib.rs`
- `crates/dlcp-sim/src/...` only for the minimal full-chain relay/prompt
  fidelity hook

Tests:

- `tests/sim/test_dlcp_control_flash_safety.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py` or a new V3.5-specific
  structural test file for relay/headroom coverage
- Rust simulator tests if native behavior changes

Artifacts/docs:

- `firmware/patched/releases/DLCP_Firmware_V3.5.hex`
- `firmware/patched/releases/DLCP_Control_V1.73.hex` only if a separately
  approved CONTROL change occurs
- docs listed in WU7

## Test Plan

Focused tests:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_dlcp_control_flash_safety.py -m "not slow"
.venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_refactoring_contracts.py -k "v35 and (relay or fw_update or headroom)"
```

Slow full-chain relay tests, mandatory before publish/acceptance:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_dlcp_control_flash_safety.py -m slow -k "control_flash"
```

Native simulator gate if Rust/PyO3 changes:

```bash
cargo test --release -p dlcp-sim
PYO3_PYTHON="$PWD/.venv_ep0/bin/python" cargo build --release -p dlcp-sim-py
bash crates/dlcp-sim-py/build.sh
```

Publish/safety gates:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35
.venv_ep0/bin/python scripts/build_v35_release.py
.venv_ep0/bin/python -m pytest tests/sim -n 32 -q -k "v35 or v173 or flash"
.venv_ep0/bin/python -m pytest tests/sim -n 32 -q
```

Hardware is optional field closure after simulation passes.  If run, use the
role-safe manual-bootloader gate:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py detect
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
: "${LEFT_HID:?set LEFT_HID from identify-mains output}"
export CONTROL_RELAY_MAIN_HID="$LEFT_HID"
# Power-cycle CONTROL while holding UP+DOWN for at least 6s; do not press SELECT.
# Confirm LCD shows Bootloader mode before live flash.
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" --preflight-only
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID"
```

## Deployment And Smoke Plan

No live deployment is part of writing or reviewing this IMPL.

Implementation deployment sequence, if separately approved:

1. Build and test the fixed MAIN.
2. Flash MAINs first; old bad MAIN cannot relay the new fail-fast behavior.
3. Flash CONTROL only through an explicit relay MAIN path.
4. Require manual CONTROL bootloader unless a separate reviewed app-side handoff
   exists and has passed sim plus hardware confirmation.
5. Refresh HID paths after MAIN re-enumeration.

Post-flash smoke:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
.venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$LEFT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$RIGHT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_diag.py --path "$LEFT_HID" --json
.venv_ep0/bin/python scripts/dlcp_diag.py --path "$RIGHT_HID" --json
```

No-deploy criteria:

- Full-chain simulator success is missing or synthetic.
- First unarmed `0x42` still returns `42 00...`.
- Host flasher streams after nonzero `0x42` status.
- V3.5 headroom/RAM safety is unproven.
- Public docs disagree with canonical artifact metadata.

## Acceptance Criteria

- Inactive relay returns `42 12...` from real MAIN firmware path and does not
  call `fw_update_relay`.
- Python flasher aborts on nonzero `0x42 resp[1]` before report 2.
- Stable negative proof reproduces the old false ACK without relying on `HEAD^`.
- Full-chain simulation proves current-bad/current-old CONTROL image to
  fixed-good CONTROL target reaches `41 00 aa` through real CONTROL bootloader
  firmware execution under the simulator and verifies target bytes/metadata.
- Full-chain simulation proves fixed-good to newer-good reaches `41 00 aa` and
  verifies target bytes/metadata using a builder-shaped newer CONTROL artifact.
- Synthetic/native bootloader harnesses may be useful temporary fidelity tests,
  but they cannot close WU5 or acceptance unless the IMPL is explicitly revised
  and re-reviewed.
- If manual bootloader is the simulated success precondition, the test names and
  docs say so; app-mode handoff is not claimed unless separately implemented and
  tested.
- V3.5 MAIN is rebuilt, RAM-safe, and passes the `min_margin >= 1700` headroom
  gate.
- Docs, hardware runbook, and incident disposition are updated from
  artifact-derived values.
- Remaining hardware gate, if any, is field confirmation only, not a substitute
  for simulator acceptance.

## Risks, Assumptions, And Open Questions

Risks:

- Full-chain simulator fidelity work may reveal a deeper UART/prompt scheduling
  gap.  If so, fix the simulator path narrowly before changing firmware around a
  bad model.
- Prompt retry/scanner code in MAIN can consume flash and alter timing.  Add it
  only when full-chain simulation shows valid prompt bytes are missed by current
  matching.
- CONTROL app-side handoff would increase blast radius; keep it separate unless
  required and reviewed.

Assumptions:

- `0x12` is safe for the repo flasher's `0x42` stream status.  HFD behavior is
  not assumed.
- A deterministic source mutation is preferable to committing a bad release HEX
  fixture unless mutation assembly proves too expensive.

Open questions:

- What is the smallest simulator API that can run CONTROL manual bootloader
  prompt/write behavior while host reports drive MAIN app HID?
- Does current V1.73 app firmware contain any usable `BF/18/01` handoff, or is
  future app-mode convenience a separate CONTROL feature?

## Reviewer Findings And Iteration History

Initial draft reviewed by 16 requested agents/passes.  The tool initially
spawned 14 new agents because two pre-existing agents held slots; after closing
completed reviewers, two replacement agents completed the less-is-more and
safety/release-risk passes.

| Reviewer | Severity | Finding | Disposition | IMPL change |
| --- | --- | --- | --- | --- |
| Simplicity, reliability, MAIN assembly, hardware, release, ops reviewers | High | `0x12` could be clobbered by normal `0x42` empty-reply staging | Addressed | WU2 now specifies staging/writing order and structural/sim tests |
| Multiple reviewers | High | Simulator success was optional/hardware-substitutable despite user request | Addressed | WU4/WU5/acceptance make full-chain simulator success blocking |
| Multiple reviewers | High/Medium | Prompt retry/robust `FW_Upd` requirements were silently deferred | Addressed | WU2 requires prompt robustness if full-chain sim shows current match misses valid prompt; incident cannot close without sim success |
| Multiple reviewers | Medium | Old-bug fixture depended on `HEAD^` | Addressed | WU5 requires deterministic mutation or committed fixture |
| Multiple reviewers | Medium | Wrong RAM safety script names | Addressed | WU6/Test Plan use `scripts/check_ram_access_safety.py --target ...` |
| Multiple reviewers | Medium/Low | README/metadata drift was conditional | Addressed | WU7 requires unconditional artifact-derived reconciliation |
| Hardware reviewer | Medium | Manual bootloader hardware gate omitted preconditions | Addressed | Test/deploy plan requires detect, identify, `UP+DOWN`, LCD confirmation |
| HFD/compat reviewers | Medium/Low | Repo flasher fail-fast was conflated with HFD behavior | Addressed | WU1 scopes `0x12` guarantee to repo flasher unless HFD parser proof is added |
| MAIN assembly/release reviewers | High/Medium | Acceptance still allowed synthetic success, newer-good could be metadata-only, V3.5 headroom was not numeric, and `TEST_ROBUSTNESS_IMPL` could drift | Addressed | WU5/WU6/WU7/acceptance now require real CONTROL bootloader execution, release-builder-shaped newer artifact, `min_margin >= 1700`, and `TEST_ROBUSTNESS_IMPL` reconciliation |
| Safety/release reviewer | Medium | Hardware runbook metadata could drift from rebuilt artifacts | Addressed | WU7/acceptance now include `docs/HARDWARE_TEST.md` and public current-canonical metadata scans |

Recheck status: complete.  Sixteen spawned reviewer agents/passes confirmed zero
unresolved High/Medium findings after the final revision.  No Low findings are
intentionally carried as implementation blockers; live hardware remains optional
field confirmation and is not a substitute for simulator acceptance.
