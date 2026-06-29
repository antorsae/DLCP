# Test Coverage Audit Prompt

## Mission

You are working in `/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis`.
Read `AGENTS.md`, `docs/TEST_ROBUSTNESS_SPEC.md`,
`docs/TEST_ROBUSTNESS_IMPL.md`, and `docs/TEST_INCIDENTS.md` first.

Perform a deep audit of the existing test coverage.  The goal is not to count
tests.  The goal is to find where the suite can still pass while user-visible
firmware behavior is wrong.

Use the last two months of commits as evidence.  For the current audit date of
2026-06-29, that window starts at 2026-04-29.  If run later, compute the
equivalent two-month window and state the exact dates used.

Do not implement fixes in this pass unless explicitly asked.  Produce a
coverage-gap report that is specific enough to turn into an IMPL or test PR.

## Multi-Agent Requirement

Use multiple independent reviewers/agents for the audit when the available
tooling allows it.  Run between 4 and 16 agents; use multiple engines/models
where available instead of relying on a single model family.

Minimum 4-agent split:

- Commit-history analyst: clusters the last two months of commits and identifies
  behavior areas that repeatedly needed fixes.
- Test-contract analyst: maps existing tests to user-visible invariants and
  flags implementation-shaped assertions.
- Stimulus-fidelity analyst: checks whether tests use realistic stimuli
  (`RB5` pulse train, press/release buttons, chain frames, HID paths, dirty-save
  service) or shortcuts that can miss field bugs.
- Release/hardware analyst: checks canonical HEX coverage, artifact-derived
  metadata, hardware incident promotion, and opt-in hardware gates.

If using more agents, add specialists for LCD/preset UI, PB1/PB2 persistence,
diagnostics identity/health, IR, flash/USB, SRC4382/audio routing, simulator
fidelity, structural RAM/table safety, and exploratory-oracle promotion.

Each agent must produce independent findings with file/test references and a
clear answer to: "Would the old bug have failed this test?"  The final report
must synthesize disagreements instead of averaging them away.

## Context: Why This Audit Exists

Two severe field bugs escaped despite a large passing suite:

1. PB2 input silently relinked to PB1.
   A persisted field setup of `PB1=S/PDIF`, `PB2=AES` could be restored through
   a PB2 raw-status-limited table path.  CONTROL could mark PB2 as
   `Same as PB1`, overwrite PB2 intent, and emit a broadcast input frame
   instead of independent PB1/PB2 route frames.  Previous tests encoded this
   fallback as acceptable behavior.

2. Diagnostics showed `PB1 OK` / `PB2 OK` without version suffix.
   CONTROL could have `identity_seen=1` and `identity_valid=0` after a transient
   identity miss.  It then stopped retrying `cmd 0x25` even while runtime
   diagnostics proved the MAIN was alive.  Previous tests covered the happy
   identity path and page-entry invalidation, not the seen-without-valid stale
   state.

Treat these as seed examples of false confidence:

- implementation-shaped assertions instead of product invariants;
- missing stale-state and poisoned-state setup;
- exact UI text not always asserted;
- realistic stimulus shape not always preserved;
- canonical flashed HEX not always included;
- one-layer checks accepted while another layer was broken.

## Required Commands

Run these commands and cite the relevant output in your report.  Use `rg` for
search.

```bash
git status --short
git log --since='2026-04-29' --date=short --pretty=format:'%h %ad %s' --reverse
git log --since='2026-04-29' --name-status --pretty=format:'COMMIT %h %ad %s' --date=short --reverse -- tests src/dlcp_fw/asm scripts docs
git log --since='2026-04-29' --date=short --pretty=format:'%h %ad %s' --reverse --grep='fix\|Fix\|bug\|Bug\|FIELD\|Harden\|harden\|regression\|coverage\|IR\|input\|diag\|preset\|mute\|wake\|LCD\|EEPROM'
.venv_ep0/bin/python -m pytest tests --collect-only -q
```

Also run focused searches for brittle patterns:

```bash
rg -n "startswith\\(|in lcd|contains|prefix|row0|lcd_lines\\(\\)\\[0\\]|assert .*Volume|assert .*Preset|assert .*PB[12]" tests
rg -n "inject_decoded_ir_event|chain\\.press\\(|set_control_pin|RB5|RC5|IR_ARMED|inhibit" tests
rg -n "V173_CONTROL_HEX|V35_MAIN_HEX|canonical|source-assembled|tmp_path_factory|assemble_v17|assemble_v3" tests
rg -n "EEPROM|dirty|persist|raw_status|PB1|PB2|Same as PB1|input.*intent|cmd06|0x06" tests docs src/dlcp_fw/asm
rg -n "identity|cmd 0x25|cmd25|seen_mask|valid_mask|PB1 OK|PB2 OK|v3\\.5|0091" tests docs src/dlcp_fw/asm
rg -n "xfail|skip\\(|pytest\\.mark\\.skip|TODO|coverage gap|not simulated|hardware-only|local-only" tests docs
```

For each high-risk cluster below, inspect representative diffs with
`git show --stat <hash>` and `git show --name-only <hash>`.  Use full diffs
where needed; do not infer from commit subjects alone.

## Commit Clusters To Classify

Use the commit history to build a coverage-risk map.  At minimum classify these
clusters:

- Simulator migration and gpsim retirement, 2026-04-29 through 2026-05-06:
  dual-supported migrations, deleted gpsim-only tests, rust facade fidelity,
  timing/cadence probes, retired skips, revived coverage.
- IR receiver and dispatcher work, especially 2026-05-06 through 2026-05-09
  and 2026-06-25:
  real RC5 pulse trains, decoded-event injection, rearm/inhibit state,
  front-panel/IR shortcut paths.
- Diagnostics, identity, and health display work, especially 2026-05-15
  through 2026-05-29 and 2026-06-27 through 2026-06-29:
  polling cadence, OK-context counters, stale identity, PB present/old/lost
  states, exact LCD rows.
- Source selection and multi-PB input work, especially 2026-05-21,
  2026-06-22, 2026-06-25, 2026-06-27, and 2026-06-29:
  PB1/PB2 persistence, raw-status table classes, PB2 rediscovery, `Same as
  PB1`, full-sync frames, MAIN audio route state.
- Preset filename and LCD ownership work, especially 2026-05-31,
  2026-06-07, 2026-06-19, and 2026-06-27:
  row ownership, scroll windows, page reentry, standby/wake, missing filename.
- V3.4/V1.73 field-bug line, especially 2026-06-09 through 2026-06-15:
  muted DSP refreshes, preset DSP safety, wake I2C ordering, parser watchdog,
  WAITING/LCD atomicity, standby/wake latency, lost mute frames.
- Flash, USB, and release-artifact work, especially 2026-06-11 through
  2026-06-15 and 2026-06-19 through 2026-06-23:
  string-less devices, transient HID faults, target HEX identity, canonical
  artifact metadata, single-MAIN auto-pick.
- Low-level structural hazards:
  RAM-bank aliasing, ISR/foreground scratch collision, TBLPTR/page carry,
  EEPROM walkers, table placement, release metadata regions.
- Exploratory chain bug-hunt work:
  what random/oracle findings were promoted to deterministic regressions, and
  what findings remained heuristic, deferred, ignored, or hardware-only.

## Audit Method

For every cluster:

1. Identify the user-visible or operator-visible contract.
   Examples: exact LCD rows, audible routing, mute state, USB identity,
   source selection, persistent settings, IR responsiveness, healthy/lost PB
   diagnostics.

2. Identify the implementation seams touched by the commits.
   Examples: CONTROL RAM flags, MAIN EEPROM bytes, chain frames, SRC4382
   registers, TAS3108 registers, LCD row owner, release metadata, simulator
   timing model.

3. Find the tests that claim to cover that contract.
   Name exact test files and node IDs when possible.  Distinguish:
   source-assembled temp fixtures, canonical release HEX fixtures, static
   structural tests, simulator behavioral tests, exploratory oracle tests, and
   opt-in hardware gates.

4. Ask whether the tests would fail for the old bug.
   Do not accept "it touches the area" as coverage.  State one of:
   would fail, would not fail, unclear without mutation, or only fails after
   new regression added.

5. Look for false-confidence patterns:
   prefix LCD assertions, row0-only checks, tests that force internal registers
   into impossible combinations, tests that skip dirty-save timing, decoded IR
   injection standing in for receiver coverage, tests that assert the current
   implementation fallback, missing canonical HEX cases, no negative stale
   state, no chain-frame assertion, no MAIN-side route/DSP assertion, no
   hardware gate for unsimulated physics.

6. Propose a minimal test improvement.
   Each proposed test must include:
   test name, fixture/artifacts, stimulus, expected observable, old-bug failure
   mode, estimated runtime class, and whether hardware is required.

## Required Matrices

Include these tables in the report.

### 1. Commit Cluster Coverage Matrix

Columns:

- Date range / commits
- Behavior area
- Primary files touched
- Existing tests
- Missing invariant or weak assertion
- Proposed regression or refactor
- Severity: Critical, High, Medium, Low
- Runtime: fast, normal, slow, hardware

### 2. Escaped-Bug Lessons Matrix

Rows must include at least:

- PB2 persisted concrete input relinked to PB1
- Diagnostics identity seen-without-valid
- LCD row displacement / missing filename
- IR works for wake then stops responding
- PB1/PB2 lost or degraded after preset/front-panel actions

Columns:

- Why previous tests missed it
- What old test gave false confidence
- What invariant should have existed
- New or proposed test node
- Whether canonical HEX is covered
- Whether realistic stimulus is covered

### 3. Release Artifact Coverage Matrix

Rows:

- Current MAIN canonical HEX
- Current CONTROL canonical HEX
- Source-assembled current MAIN
- Source-assembled current CONTROL
- Historical compatibility artifacts still exercised

Columns:

- Test files / node IDs
- Metadata/identity derived from artifact or hardcoded
- UI/menu/persistence covered
- chain/audio/DSP covered
- gaps

### 4. Stimulus Fidelity Matrix

Rows:

- IR receiver layer
- IR dispatcher layer
- Front-panel buttons
- USB/HID EP0
- Chain UART frames
- Power/standby/wake
- PB discovery/loss/reconnect
- Dirty EEPROM save service

Columns:

- Realistic stimulus helper
- Shortcuts currently used
- Known risks
- Tests that must not use shortcuts
- Proposed fixture cleanup

## Special Checks Required

Pay particular attention to these questions:

- Are any tests still accepting `Same as PB1` fallback for a persisted PB2
  concrete source?
- Are all PB1/PB2 input persistence tests checking EEPROM, CONTROL intent,
  emitted `cmd 0x06` frames, MAIN route state, and LCD label where relevant?
- Is there a matrix covering `PB1=S/PDIF`, `PB2=AES` and other asymmetric
  field-realistic pairs across cold boot, PB2 rediscovery, standby/wake, and
  dirty-save timing?
- Can any Diagnostics page stabilize at `PBn OK` without version for a current
  V3.5 MAIN?
- Do diagnostics tests cover `seen=1, valid=0`, old MAIN, missing MAIN, stale
  valid identity, and page reentry separately?
- Do LCD tests assert exact 16-character rows or explain why not?
- Are Preset filename tests checking row-owner atomicity after page changes,
  front-panel preset actions, IR actions, standby/wake, and PB lost/old states?
- Are receiver-layer IR claims proven with RB5 pulse trains, not only decoded
  event injection?
- Do button tests use press/release timing, not raw one-shot `chain.press`
  where the firmware loop can consume a stale event twice?
- Are canonical HEX artifacts used anywhere an operator-flashed behavior is
  being guarded?
- Are hardware incidents in `docs/TEST_INCIDENTS.md` complete and linked to
  deterministic regressions or explicit hardware gates?
- Did the gpsim retirement remove any behavioral assertion that has not been
  replaced in rust-native tests?
- Do exploratory oracle findings have a deterministic regression, or are they
  only documented as interesting cards?

## Output Format

Write the report as Markdown.  Keep it factual and specific.

Required sections:

1. Executive Summary
   - Top 5 coverage risks, ordered by severity.

2. Method And Inputs
   - Exact date window, commands run, docs read, current git status.

3. Commit-Derived Risk Map
   - The Commit Cluster Coverage Matrix.

4. Escaped-Bug Analysis
   - The Escaped-Bug Lessons Matrix and a short explanation of the two known
     misses.

5. Current Test Weaknesses
   - Concrete brittle tests or helper patterns, with file paths and line
     numbers where possible.

6. Proposed Minimal Regression Set
   - A prioritized list of tests to add or refactor.  Each entry must include
     node ID, stimulus, assertions, and why it would fail on old behavior.

7. Hardware Gate Recommendations
   - Only for contracts that cannot be simulated with the current rust facade.

8. Open Questions / Unclear Items
   - Areas where mutation or hardware confirmation is required before claiming
     coverage.

9. Appendix: Evidence
   - Selected commit hashes, test node IDs, and grep findings.

## Quality Bar

Be skeptical.  A test is not robust just because it is slow, end-to-end, or
near the touched code.  It is robust only if it asserts the product contract at
the layer where the bug would be visible.

Prefer small, high-signal regressions over large brittle transcripts.  For
critical release behavior, require at least one test that checks multiple
observable layers together, for example LCD + chain frame + EEPROM + MAIN
route/DSP state.

When in doubt, answer this explicitly:

> Would this test have failed before the bug fix, for the exact field stimulus?

If the answer is no or unclear, call it a gap.
