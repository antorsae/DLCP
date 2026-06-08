# Mute DSP Refresh Bug Implementation Plan

Date: 2026-06-09
Status: Reviewed - ready for implementation
Source spec: `docs/MUTE_DSP_REFRESH_BUG_SPEC.md`
Scope: BUG-MUTE-REFRESH-01 in canonical MAIN V3.4 + CONTROL V1.73 only.

## Source Requirements

Goals:

- Fix live mute drop-outs where audio returns periodically after MUTE.
- MAIN V3.4 must not write a non-zero TAS3108 volume coefficient (`0x30`) from
  automated refresh paths while mute is an active target state.
- Preserve V3.1+ verified TAS write behavior: ACK-gated dirty clear,
  computed-to-logical volume copy only after ACK for the verified path, bounded
  retry/recovery, and visible BF/08 fault reporting.
- Record MAIN build size/free-space delta and keep V3.4 release margins valid.

Non-goals:

- No CONTROL cadence retries/delays as the primary fix.
- No unrelated V3.4/V1.73 refactors.
- No V3.5/version promotion work in this task.

Resolved policy decision:

- V1.73 compatibility is preserved: a real CONTROL volume action while muted is
  an unmute action because CONTROL clears local mute before sending `cmd 0x07`
  and later emits `B0/03/03`.  Automated MAIN refreshes (`cmd 0x06`, SRC route,
  wake/reapply, HID import, full-sync input, retry/recovery) must not use that
  behavior to clear mute.  Tests must distinguish explicit user volume/unmute
  from automated coefficient refresh.

## Required Docs Read

- `AGENTS.md`, `README.md`
- `docs/MUTE_DSP_REFRESH_BUG_SPEC.md`
- `docs/SIMULATION.md`, `docs/TEST_SIMULATOR.md`
- `docs/REFACTORING_V34_V173_SPEC.md`,
  `docs/IMPL_REFACTORING_V34_V173.md`
- `docs/HARDWARE_TEST.md`, `docs/V32_RELEASE.md`, `docs/V171_RELEASE.md`
- `docs/IMPL_V171_V32_BUG_LEDGER.md` for strict-xfail lifecycle convention

## Current Evidence

New regression file:

- `tests/sim/test_v34_mute_refresh_bug.py`

Current focused results:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_mute_refresh_bug.py
# 1 passed, 1 xfailed

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q --runxfail tests/sim/test_v34_mute_refresh_bug.py
# 1 passed, 1 failed; failing evidence: active=0x28, events=0x80, dsp30=00120bdb
```

Reproducer:

1. Boot canonical `DLCP_Firmware_V3.4.hex` in MAIN-only Rust sim.
2. Inject `B0 03 02`: MAIN sets mute bits and writes TAS `0x30=00000000`.
3. Inject `B0 06 00`: MAIN clears bit4 and writes TAS `0x30=00120bdb`.

Related confirmed surfaces from exploratory sim:

- `B0 06 05` while muted also clears bit4 and writes `00120bdb`.
- Standby then wake while muted restores non-zero coefficient.
- Changed `B0 07 xx` while muted currently clears mute; this is compatible
  with CONTROL volume-key behavior only when it is a user action.

## Bit Ownership

`active_flags.bit4`

- Set by explicit mute-on (`cmd 0x03 data 0x02`).
- Set/cleared by HID/settings import.
- Set by SRC4382 non-PCM/status monitor.
- Set by `preset_force_mute`.
- Cleared by explicit mute-off (`cmd 0x03 data 0x03`), current dirty-volume
  refresh, and preset forced-mute release paths.

`active_flags.bit5`

- Mute shadow: expected DSP coefficient state, used to decide whether a mute
  refresh is needed.
- Must stay coherent with actual zero/non-zero TAS `0x30` writes.

`event_flags.bit3`

- Volume/route/TAS coefficient dirty.  Can be raised by serial volume, route
  refresh, HID import, wake/reapply, and table/apply paths.

`event_flags.bit5`

- Mute dirty.  Raised when bit4 and bit5 differ.  Existing code handles it
  after the bit3 volume path.

`preset_job_flags.bit0/bit1`

- Distinguishes MAIN-forced mute from user-requested mute during preset jobs.
  This distinction must not be collapsed into a generic bit4 check.

## Gap Analysis

Existing tests prove immediate mute/unmute, SRC liveness, and preset switching,
but not that target mute survives later coefficient refreshes.  Existing
assertions read only the latest TAS payload, which can miss a transient
non-zero write followed by re-mute.  The Python facade may need a completed
TAS write-history helper so tests can reject any non-zero `0x30` payload during
a muted window.

The first implementation attempt must avoid a naive “if bit4 then zero” patch
unless bit4 ownership is handled.  SRC non-PCM/status can also set bit4; tests
must prove source recovery does not create a sticky automatic mute.

## Implementation Work Units

### WU1 - Improve Test Oracle And Xfail Shape

- Keep setup/boot/immediate mute tests non-xfailed.
- Strict-xfail only current red automated-refresh cases.
- Add or expose a Python facade helper for all completed TAS3108 writes after a
  capture point, e.g. per-unit payload history for subaddr `0x30`.
- Every muted-window regression must assert no completed `0x30` payload is
  non-zero while MAIN is logically muted.
- Add a stale-xfail guard or documented grep command that fails closure if
  `BUG-MUTE-REFRESH-01` remains in `pytest.mark.xfail`.

### WU2 - V3.4/V1.73 Behavior Tests

Add V3.4-targeted tests in/near `tests/sim/test_v34_mute_refresh_bug.py`.
Current-red strict-xfail until fixed:

- Auto Detect input refresh: mute, inject `B0 06 00`, no non-zero `0x30`, bit4
  and bit5 stay set.
- Fixed-input refresh: parameterize fixed digital routes or distinct route
  pairs, not only `0x05`.
- Wake/reapply: mute, standby, wake, wait through reapply, no non-zero `0x30`.
- Natural V1.73/V3.4 full-chain cadence: after MUTE, prove CONTROL emitted
  periodic `B0/06` input frame before the next mute step, and both MAINs remain
  muted with only zero/absent `0x30` writes through at least one full-sync cycle.
- Real SRC Auto Detect service: seed SRC4382 status/registers so
  `main_i2c_service_27f0` raises the route event, not just direct frame
  injection; assert SRC route writes still happen and TAS `0x30` stays zero.
- V1.73 source-shape guard: pin full-sync step order and sender encodings for
  volume/input/mute in V1.73 source.

Green/non-xfail compatibility tests:

- Immediate mute writes zero.
- Explicit unmute `B0 03 03` restores non-zero coefficient.
- Real CONTROL volume action while muted follows V1.73 compatibility behavior:
  local CONTROL unmute state and MAIN audio restoration happen coherently.
- Preset forced-mute commit restore, user-mute-during-job stays muted,
  coalesced cancel restore, and standby/reconnect cancel behavior.
- SRC non-PCM/status auto-mute followed by source recovery/fixed input, both
  with and without explicit user mute, to avoid sticky automatic mute.

### WU3 - HID/Settings Import Coverage

Promote HID import from audit-only to required tests.

- Use `Chain.firmware_hid_report` or existing HID sim helpers to drive the real
  firmware HID settings import path.
- Imported mute-on plus changed volume/input/filter must leave bit4/bit5 set
  and allow only zero/absent `0x30` writes.
- Imported mute-off restores latent non-zero volume.
- Exercise NACK/ACK behavior or explicitly document why pre-ACK logical copy is
  unchanged and covered elsewhere.

### WU4 - MAIN ASM Fix

Edit `src/dlcp_fw/asm/dlcp_main_v34.asm`.

Required design:

- Automated refresh paths must not clear mute merely because coefficient dirty
  is set.
- Explicit user unmute remains `cmd 0x03 data 0x03`.
- Explicit user volume remains a compatibility unmute path only when it is a
  real user volume command.  The implementation must distinguish this from
  route/input/SRC/HID/wake refresh.
- If a verified zero write handles both volume-dirty and mute-dirty, coalesce
  `event_flags.bit5` so the later direct zero-write branch does not duplicate
  raw unverified TAS traffic in the same pass.
- Preserve `volume_dsp_write` success and NACK/retry/fault contracts.
- Define direct zero-write failure handling.  Preferred: ensure a NACKed direct
  zero write schedules/keeps a verified muted refresh; otherwise document the
  out-of-scope rationale and add a test proving the next muted dirty refresh
  forces zero after faults clear.

Also audit all TAS `0x30` writers:

- `volume_dsp_write`
- `clrf_i2c_coeff_0123_and_write` callers
- `main_core_service_4574` / preset table apply path
- any baked/canonical preset table entry that can target `0x30`

Either prove canonical/baked preset tables do not write `0x30`, or guard the
table-apply path when muted.

### WU5 - V3.4 NACK/Retry Tests

Add V3.4 tests with TAS3108 address/data NACK while muted and dirty:

- Dirty bit remains pending across retryable NACK.
- Retries never write non-zero `0x30` while muted.
- Exhaustion still surfaces BF/08/fault counters.
- After fault clears, final successful write is zero and bit4/bit5 remain
  coherent.

### WU6 - Build, Size, And Release Gates

Do not use the release builder as the only size source because it bumps rev.
Use temp direct `assemble_v30()` builds for clean current baseline and
candidate, then run canonical builder once at the end.

Record:

- Clean current pre-fix V3.4 baseline and post-fix V3.4 candidate
  `used_bytes_pre_preset_b`, `last_used_pre_preset_b`,
  `free_bytes_before_0x4C00`, `free_object_words`, and `byte_margin`.
- Actual bug-fix size delta: post-fix V3.4 minus pre-fix V3.4.
- V3.3 reference metrics if needed for release-history context; these do not
  replace the V3.4-to-V3.4 bug-fix delta.
- `0x1000..0x4BFF` diff summary for current V3.4 baseline versus candidate.
- Final canonical V3.4 rev/SHA/CRC/listing path.

Acceptance requires `free_object_words >= 64` and `byte_margin >= 128` unless a
separate size-recovery plan is added before release.

## Test Commands

Pre-fix red proof:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_mute_refresh_bug.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q --runxfail tests/sim/test_v34_mute_refresh_bug.py
```

Post-fix focused closure, expected zero xfails:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_mute_refresh_bug.py
PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from pathlib import Path
import sys

needle = "BUG-MUTE-REFRESH-01"
bad = []
for path in Path("tests").rglob("test_*.py"):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if "pytest.mark.xfail" not in line:
            continue
        window = "\n".join(lines[idx:idx + 8])
        if needle in window:
            bad.append(f"{path}:{idx + 1}")
if bad:
    print("stale BUG-MUTE-REFRESH-01 xfail(s):")
    print("\n".join(bad))
    sys.exit(1)
PY
```

Required V3.4/V1.73 release-adjacent regression set:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_ram_bank_safety.py \
  tests/sim/test_firmware_version_label.py
```

Also run V3.4-converted or V3.4-parameterized SRC route/TAS audio-path tests.
Older `test_v32_*` and `test_v171_v32_*` files are compatibility context only,
not sufficient closure for this V3.4/V1.73 bug.

Before release-ready:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

If full suite is not run, status is sim-focused only, not release-ready.

## Hardware / Deploy Plan

No flashing is part of this IMPL-writing task.

Later live validation is MAIN-only by default because the fix is MAIN-only.
CONTROL flash is conditional on explicit approval or confirmed non-V1.73
installation.

Role-safe sequence required before any live MAIN flash:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
# export refreshed LEFT_HID and RIGHT_HID from the identification output
.venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --path "$LEFT_HID" --info-only | tee artifacts/probes/mute_refresh_left_preflash_info.txt
.venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --path "$RIGHT_HID" --info-only | tee artifacts/probes/mute_refresh_right_preflash_info.txt
.venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --left --path "$LEFT_HID" --profile <preflash-profile>
.venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --right --path "$RIGHT_HID" --profile <preflash-profile>
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
```

Preconditions:

- Capture pre-flash volume/input/profile and use matching `--profile`, or
  explicitly document an intentional profile override.
- Start unmuted before release flash unless mute persistence across flash is
  separately implemented and tested.

Live smoke artifact should be stored under `artifacts/probes/` and include:

- timestamp, MAIN rev/SHA/CRC, CONTROL identity, HID paths, role mapping;
- pre/post `dlcp_diag.py --json` snapshots;
- volume/input/profile before and after;
- 20+ second muted playback observation, muted input navigation, muted
  standby/wake, explicit unmute restore;
- PASS/FAIL verdict and rollback-not-run or rollback command evidence.

## Acceptance Criteria

- BUG-MUTE-REFRESH-01 xfails removed; focused bug tests pass with zero xfail.
- No muted-window test observes a non-zero TAS `0x30` write from automated
  refresh paths.
- Explicit unmute and V1.73 volume-action compatibility pass.
- HID import, SRC route, wake/reapply, preset forced-mute, and NACK/retry
  coverage pass.
- V3.4 build succeeds; size/free-space delta and margin gates are recorded.
- Required V3.4/V1.73 tests pass; full sim gate passes before release-ready.

## Reviewer Findings And Disposition

Ten independent review agents ran on the first draft:

1. Simplicity/scope
2. MAIN mute-state correctness
3. DSP/I2C verified-write
4. CONTROL/full-sync integration
5. SRC4382/input-route coverage
6. Preset/standby/wake lifecycle
7. HID/settings/flash persistence
8. Tests/xfail lifecycle
9. Release/build/size/ops
10. Similar-bug/performance

High/Medium findings resolved in this revision:

- Removed V3.5 scope drift; constrained to V3.4/V1.73.
- Replaced old-artifact test closure with mandatory V3.4/V1.73 tests.
- Resolved volume-while-muted policy as V1.73 compatibility unmute for real
  volume actions only.
- Required V1.73 full-sync source/chain guards.
- Required TAS write-history oracle, not latest-payload-only assertions.
- Split green setup/immediate mute tests from strict xfail refresh tests.
- Required per-case xfail handling and stale-xfail closure guard.
- Added V3.4 SRC real-service and fixed-input route coverage.
- Added HID/settings import as required implementation/test work.
- Added muted NACK/retry/fault coverage.
- Added bit ownership table and SRC automatic-mute recovery tests.
- Added duplicate bit3/bit5 coalescing requirement.
- Added all-TAS-`0x30` writer audit, including preset table apply.
- Added V3.4 direct-build size metrics and margin gates.
- Replaced unsafe live flash commands with role-safe MAIN-only validation.
- Added profile preservation, start-unmuted precondition, and smoke artifact
  requirements.

Remaining Low issues:

- None blocking.  The hardware smoke artifact template can be expanded during
  implementation if live validation is actually performed.

Review gate summary: zero unresolved High or Medium findings.

## Post-Implementation Evidence Placeholder

- Actual files changed:
- Actual size/free-space delta:
- Exact test commands/results:
- Deploy/hardware evidence or no-deploy reason:
- Remaining low-risk issues:
- Final acceptance status:
