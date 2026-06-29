# Test Robustness Spec

Last updated: 2026-06-29
Status: Proposed
Scope: DLCP firmware simulator, release-artifact, hardware-gate, and documentation tests under `tests/`, `scripts/`, and `docs/`.

## Purpose

The current test suite has high volume but still allowed significant
user-visible bugs to escape:

- stale Diagnostics MAIN identity text after a MAIN firmware change, observed
  as `PB1 OK v330091` instead of current V3.5 identity text;
- CONTROL LCD row corruption or missing row fields while tests accepted only a
  prefix such as `Volume`, `Preset`, or `PB1`;
- release-candidate fragility from table placement and source/layout movement;
- live degraded states, such as MAIN USB disappearance or software-reset
  flags, that are not promoted into deterministic simulator or hardware gates
  quickly enough.

This spec defines the minimum robustness contract for tests that protect
current MAIN V3.5 and CONTROL V1.73 behavior and future release lines.

## Existing Test Guidance Found

There is no single existing test-quality policy.  Current guidance is split:

- `AGENTS.md` is the authoritative test inventory and release-path map.
- `README.md` defines current fast/full simulator gates, flash preflights, and
  post-flash smoke commands.
- `docs/SIMULATION.md` explains the Rust universal-clock simulator and public
  `Chain` API.
- `docs/TEST_SIMULATOR.md` is historical preset-simulator guidance and points
  readers back to `AGENTS.md` for the current matrix.
- `docs/HARDWARE_TEST.md` defines live-rig smoke tests, hardware markers, role
  classification before flashing, LCD OCR checks, IR/front-panel gates, and
  redaction rules for local-only raw hardware artifacts.
- `CODING_STYLE.md` requires focused tests and release gates when code
  generation changes.

Missing from those documents:

- an assertion-quality standard for LCD rows and user-visible text;
- a stale-state/upgrade-state requirement for caches and persistence;
- a rule that release-artifact tests must cover canonical HEX payloads, not
  only freshly assembled temp images;
- a policy for promoting live incidents into deterministic regressions;
- mutation or negative tests for fragile layout and parser/display contracts;
- evidence requirements that make it obvious which tests would have failed
  before a fix.

## Goals

1. Make tests fail for user-visible row corruption, stale suffixes, and missing
   LCD fields.
2. Make tests cover dirty temporal sequences: firmware changes under a live
   CONTROL, reconnects, degraded MAIN visibility, software resets, delayed
   dirty-state saves, and power-cycle persistence.
3. Exercise both source-assembled temporary images and canonical release HEX
   artifacts wherever the operator will flash canonical artifacts.
4. Add structural guards for low-level table/layout contracts whose movement
   can change firmware-visible behavior.
5. Convert hardware incidents into a repeatable path: classify, minimize,
   reproduce in simulator when possible, and add a live hardware gate when it
   cannot be simulated.
6. Keep tests pragmatic.  Add helpers and parameterization only when they
   remove repeated fragile assertions or clearly increase failure quality.

## Non-Goals

- This spec does not require rewriting the whole simulator suite.
- This spec does not make live hardware tests mandatory for every change.
- This spec does not require CI to run hardware tests.
- This spec does not replace feature-specific specs such as diagnostics,
  SRC4382, preset filename, or multi-PB input selection specs.
- This spec does not authorize firmware changes by itself.

## Test Robustness Contract

### 1. IR Receiver-Layer And Dispatcher-Layer Separation

IR tests must identify which layer they cover.

Decoded-event tests that call `inject_decoded_ir_event` are dispatcher-layer
tests.  They are appropriate for broad command matrices, wrong-address checks,
menu-state permutations, and state-machine edge cases because they bypass the
Manchester receiver and enter at the decoded command/address registers.

Receiver-layer tests must drive CONTROL.RB5 with a real RC5 pulse train when a
bug or feature claim depends on port-B IOC, RBIF rearming, inhibit timers, or
the bit-bang Manchester decoder.  The current mandatory receiver smoke set is:

- POWER wake from standby, followed by another real standby command;
- volume, mute, preset shortcut, and input shortcut from the Volume menu;
- explicit standby and wake shortcuts;
- Diagnostics-page IR dispatch for both PB1 and PB2 pages.

The receiver-layer smoke set should stay small.  Do not clone every dispatcher
matrix into pulse-train form unless the bug is specifically in decode timing,
RB5 edge handling, IR rearm/inhibit state, or a user-visible path that decoded
event injection cannot prove.

### 2. Exact LCD Assertions By Default

For deterministic simulator tests, LCD row assertions must compare exact
16-character strings by default.

Allowed exceptions:

- transient wait loops where the exact row is intentionally variable;
- long scrolling filename windows where the test asserts a precise window,
  cursor ownership, and row length;
- issue token rows where order is explicitly documented as variable.

Any exception must include a short comment naming why prefix, containment, or
row-length-only matching is acceptable.

### 3. Stale-State And Upgrade Tests

Any feature with cached, persisted, or cross-MCU state must include at least
one test that seeds a stale prior value and then verifies the real refresh path
replaces it.

Required categories:

- Diagnostics MAIN identity valid/seen masks and per-PB cached version bytes.
- CONTROL EEPROM settings and dirty-save lifecycle.
- MAIN EEPROM/runtime identity bytes after release builders update metadata.
- Preset filename cache and row owner state after page changes, standby/wake,
  reconnect, and stale/lost PB health.
- PB1/PB2 input selection after cold boot, PB2 rediscovery, and independent
  PB2 routing.

### 4. Canonical Artifact Parity

Tests that guard release behavior must run against at least one canonical HEX
artifact path when that is what operators flash.  Freshly assembled temp HEX
fixtures are still useful for source tests, but they do not replace canonical
artifact coverage.

Expected version/revision text and metadata assertions must derive from the
canonical artifact under test, not from README prose or stale release notes.
If a test is about stale cached identity or persisted release behavior, that
same regression must include a canonical artifact case.

At minimum, canonical artifact coverage is required for:

- current MAIN release identity and diagnostics display;
- current CONTROL release UI/menu/persistence behavior;
- release builder metadata/revision update contracts;
- flash safety and preflight tests.

### 5. Structural Guards For Layout-Sensitive Firmware

Low-level tables and routines that depend on `LOW(label)+offset`,
`TBLPTR`, page carry, banked RAM, fixed `org` regions, or release metadata
must have structural tests that inspect listings, HEX bytes, or symbol maps.

Structural tests must name the reason a movement is safe or unsafe.  Examples:

- low-only MAIN tables must remain page-local;
- LCD ROM-entry tables may cross a page only when every reader is known
  carry-safe, and first-screen title tables should stay page-local when
  feasible;
- release metadata and bootloader regions must not overlap;
- RAM-bank aliases must remain unique and covered by the RAM safety gate.

### 6. Negative Or Mutation Proof For High-Risk Fixes

For fixes in display rendering, parser state, routing, persistence, I2C/SRC
recovery, or flash/release builders, tests should include a negative proof when
practical:

- seed the stale/bad state that existed before the fix and prove it is cleared;
- mutate a small branch/table constant in a temp source and prove the focused
  test fails;
- or assert a canonical bad fixture is rejected.

The IMPL may skip mutation proof for a narrow change only when it records the
reason and adds an equivalent stale-state or structural regression.

### 7. Hardware Incident Promotion

Every significant hardware incident must be recorded in a test gap note or
issue-like doc section with:

- observed LCD/USB/audio state and exact firmware versions/revisions;
- whether USB/HID enumeration was present;
- whether the simulator can reproduce it;
- the deterministic regression added, or the hardware gate required if it
  cannot be simulated yet.

Hardware tests remain opt-in with `--run-hardware`, but live closure must use
the role-safe commands in `docs/HARDWARE_TEST.md` and explicit MAIN HID paths.
Raw hardware artifacts, including HID paths, serials, camera names, Flipper
ports, command JSON, and media paths, are local-only.  Committed/shared
incident evidence must use role labels, redacted or hash-only identifiers,
cropped LCD-only media when media is needed, and stripped metadata.

### 8. Test Evidence Standard

When a robustness test is added for a bug, its name or docstring must make clear
which escaped behavior it would catch.  The final evidence must include:

- focused test command;
- whether the test fails against the old behavior or only guards future
  regression;
- broader gate command selected from `AGENTS.md`, `README.md`, or the relevant
  feature spec;
- hardware gate status or explicit no-hardware reason.

## Acceptance Criteria

This spec is implemented when:

1. a reviewed IMPL identifies current brittle assertions and converts the
   highest-risk LCD/diag/persistence tests to exact or justified assertions;
2. stale identity cache and stale persisted input paths have deterministic
   regression coverage;
3. canonical current MAIN/CONTROL HEX artifacts are included in release-facing
   simulator gates, with expected identity/revision values derived from those
   artifacts;
4. layout-sensitive LCD and route/input tables have structural guards;
5. `docs/HARDWARE_TEST.md` or a linked doc records a mandatory incident
   template and how hardware incidents are promoted to simulator or hardware
   gates with sanitized evidence;
6. IR tests document whether they are receiver-layer or dispatcher-layer, with
   current user-visible IR paths covered by real RB5 pulse trains;
7. focused and broader test commands are documented with expected scope and
   skip policy.

## Open Questions

- Whether CI should run the full current `tests/sim -n 16` gate for every
  release-candidate commit or only for release-builder changes.
- Whether to add a pytest marker such as `release_artifact` for tests that must
  use canonical HEX payloads.
