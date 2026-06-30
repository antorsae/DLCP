# Test Coverage Audit - 2026-06-29

Scope: `/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis`

Audit window: 2026-04-29 through 2026-06-29 inclusive.

This is a read-only coverage-gap report. It does not implement firmware or test
fixes.

## 1. Executive Summary

Top 5 coverage risks, ordered by severity:

1. **Critical - `cmd 0x06` input routing broadcast is now forbidden, but current
   coverage still encodes it as acceptable before PB2 discovery.**  Input route
   frames must be addressed only to known reachable PBs. If PB2 has persisted
   concrete intent but is not yet discovered, PB1 changes must use `B1/06`, PB2
   intent must remain pending, and `B0/06` must not be emitted. Current code
   comments still describe legacy pre-discovery `B0/06` behavior in
   `src/dlcp_fw/asm/dlcp_control_v173.asm`, and
   `tests/sim/test_v173_multi_pb_input_selection.py::test_valid_pb2_eeprom_stays_pending_on_single_pb_chain_until_discovery`
   currently expects `B0`.

2. **Critical - a known Diag-page front-panel standby behavior remains a strict
   xfail.**  `tests/sim/test_v34_v173_field_repros_20260613.py::test_diag_page_front_panel_stby_enters_standby_and_closes_both_main_gates`
   is still marked strict-xfail. A user-visible standby failure can remain
   known-broken while the suite is green.

3. **High - PB2 concrete-input regressions are stronger after the June fixes,
   but the matrix is still incomplete.**  The current suite now catches the
   escaped PB2 DOWN/raw-status relink and PB1 S/PDIF + PB2 AES cold-boot path,
   but it still needs canonical coverage for raw-status variants,
   blackout/reconnect, standby/wake, and the new no-`B0/06` invariant.

4. **High - Diagnostics identity has the right regression shape, but negative
   paths are not fully behavioral/canonical.**  `seen=1, valid=0` retry exists,
   and canonical stale-valid replacement exists. Gaps remain for canonical
   poisoned state, malformed `BF/4F..55` reply sequences, old/lost suffix
   clearing, PB2 old-MAIN re-entry, and identity interleaving with filename
   traffic.

5. **High - high-interest exploratory oracle cards are not all mapped to
   deterministic regressions, hardware gates, or explicit defer decisions.**
   Those cards are discovery evidence, not coverage, until each has a tracked
   disposition.

Additional risks remain around stale current-line hardware gates and shortcut
stimuli. They are covered below in the release-artifact, stimulus-fidelity, and
hardware sections.

## 2. Method And Inputs

Docs read first:

- `AGENTS.md`
- `docs/TEST_ROBUSTNESS_SPEC.md`
- `docs/TEST_ROBUSTNESS_IMPL.md`
- `docs/TEST_INCIDENTS.md`

Required commands run:

```bash
git status --short
git log --since='2026-04-29' --date=short --pretty=format:'%h %ad %s' --reverse
git log --since='2026-04-29' --name-status --pretty=format:'COMMIT %h %ad %s' --date=short --reverse -- tests src/dlcp_fw/asm scripts docs
git log --since='2026-04-29' --date=short --pretty=format:'%h %ad %s' --reverse --grep='fix\|Fix\|bug\|Bug\|FIELD\|Harden\|harden\|regression\|coverage\|IR\|input\|diag\|preset\|mute\|wake\|LCD\|EEPROM'
.venv_ep0/bin/python -m pytest tests --collect-only -q
```

Key command outputs:

- Initial `git status --short`: no tracked modifications; untracked proposal
  docs, `docs/analysis/hypex_dsp_diyaudio_thread.md`, and `uv.lock` were
  present.
- Current `git status --short` after writing this report: the same pre-existing
  untracked files plus `docs/TEST_COVERAGE_AUDIT_2026-06-29.md`.
- Pytest collect-only: `2144 tests collected in 0.40s`.
- Focused `rg` searches found remaining prefix/row0 LCD assertions, decoded IR
  shortcuts, canonical V1.73/V3.5 artifact usage, `Same as PB1` linked-mode
  tests, strict xfails, and hardware-only gates.

Multi-agent review was used. Independent reviewers covered commit history,
test contracts, stimulus fidelity, PB1/PB2 persistence, Diagnostics identity,
LCD/preset UI, and release/hardware coverage. Two broad agents exceeded context;
a narrower release/hardware replacement completed.

### Updated Decisions Since Draft

- `B0/06` input broadcast is no longer an open question. It is forbidden for
  input routing. `cmd 0x06` must be addressed to PBs known reachable.
- "Single PB" must mean no persisted PB2 concrete intent and no PB2 observed in
  session. If EEPROM `0x5F` contains concrete PB2 intent, CONTROL must treat
  PB2 as expected-but-pending, not nonexistent.
- High-interest exploratory oracle cards that lack deterministic regression,
  hardware gate, or explicit defer/ignore rationale are a real coverage gap.

## 3. Commit-Derived Risk Map

| Date range / commits | Behavior area | Primary files touched | Existing tests | Missing invariant or weak assertion | Proposed regression or refactor | Severity | Runtime |
|---|---|---|---|---|---|---|---|
| 2026-04-29 to 2026-05-06; `5a56279`, `e023c01`, `0f62b2d` | gpsim retirement / Rust sole simulator | `src/dlcp_fw/sim/*`, `crates/dlcp-sim*`, deleted gpsim tests | rust-native sim tests, `check_gpsim_excision.py` | Deleted gpsim-only assertions are not fully mapped to rust-native nodes | Maintain a deletion-to-rust-coverage ledger | High | normal |
| 2026-05-06 to 2026-05-09 and 2026-06-25/29; `a3851f4`, `e4fe1b4`, `7086fba` | IR receiver and shortcut paths | `dlcp_control_v173.asm`, sim native pin helpers | `test_v171_ir_rc5_pulse_train.py`, IR command matrix | Decoded injection does not prove RB5 receiver rearm/inhibit | Add RB5 coverage for current-line Diag shortcut and PB input F4/F5 paths | High | slow |
| 2026-05-15 to 2026-05-29 and 2026-06-27/29; `50d3119`, `c650bf9`, `165b7d1` | Diagnostics identity / health | `dlcp_control_v172/v173.asm`, `dlcp_main_v35.asm` | `test_v172_v33_diag_identity.py` | Malformed identity frames, old/lost cache clear, canonical seen-without-valid | Canonical poisoned-state and malformed `BF/4F..55` runtime tests | High | slow |
| 2026-05-21, 2026-06-22/25/27/29; `1fe8cae`, `7abe29b`, `c650bf9`, `165b7d1` | PB1/PB2 input persistence | `dlcp_control_v173.asm`, `dlcp_control_ram.inc` | `test_v173_multi_pb_input_selection.py` | `B0/06` still accepted before PB2 discovery; raw-status/reconnect matrix incomplete | No-`B0/06` invariant plus PB2 concrete raw-status/reconnect matrix | Critical | slow |
| 2026-05-31, 2026-06-07/19/27; `1393f6e`, `d81a52f`, `17b59e9` | Preset filename LCD ownership | `dlcp_control_v172/v173.asm`, LCD tests | `test_preset_filename_lcd_spec.py` | Adjacent compatibility/hardware tests still accept prefix/legacy display | Require exact filename-capable layout in current hardware gate | High | hardware |
| 2026-06-09 to 2026-06-15; `8b0dead`, `947ca22`, `d69d689`, `a274dfa` | V3.4/V1.73 field-bug line | `dlcp_main_v34.asm`, `dlcp_control_v173.asm` | field repro suites, preset safety tests | Diag STBY repro remains xfailed | Fix or split xfail into explicit known-failing product gate | Critical | normal |
| 2026-06-11 to 2026-06-23; `26be54e`, `1122dcf`, `1725ff1` | Flash/USB/release artifacts | flashers, release builders, FilterData XML | flasher sim backend, V35 release flash tests | Some identity expectations still source-derived | Derive canonical expectations from HEX bytes | Medium | fast |
| entire window | RAM/TBLPTR/table structural hazards | asm sources, RAM incs, memtrace | RAM safety, table page carry, ISR scratch tests | Behavior can pass until rare corruption path | Keep structural gates required for release builders | High | fast |
| 2026-06-09 onward | exploratory oracle promotion | `scripts/sim_chain_exploratory.py`, oracle scripts | promoted field repro tests | Cards without mapped disposition are not coverage | Add card-disposition ledger and gate high-interest unmapped cards | High | fast |

## 4. Escaped-Bug Analysis

| Escaped bug lesson | Why previous tests missed it | What old test gave false confidence | What invariant should have existed | New or proposed test node | Canonical HEX covered? | Realistic stimulus covered? |
|---|---|---|---|---|---|---|
| PB2 persisted concrete input relinked to PB1 | Tests accepted linked fallback and did not join EEPROM, intent, frames, MAIN route, and LCD | PB2 could fall back to `Same as PB1` under some table classes | Concrete PB2 EEPROM must never relink unless user explicitly selected linked | Existing canonical cold-boot tests plus proposed no-`B0/06` regression | partly | partly |
| Diagnostics identity seen-without-valid | Happy identity and page-entry invalidation did not poison `seen=1, valid=0` | `PBn OK` prefix and row0-only checks | Healthy current MAIN must retry until exact version suffix or explicit old/lost state | Existing source test; add canonical clone | source now; canonical stale-valid yes | yes in sim |
| LCD row displacement / missing filename | Row0/prefix checks missed leading spaces and row1 blanking | `startswith("Preset")`, `startswith("Volume")` | Exact 16-char rows unless OCR exception documented | Existing canonical preset tests; tighten current hardware gate | yes in sim | hardware gate loose |
| IR works for wake then stops responding | Decoded injection bypassed RB5 receiver state | Dispatcher-only command matrix | RB5 pulse train must rearm after wake/inhibit windows | Existing RB5 wake/rearm tests; add current Diag shortcut RB5 smoke | yes | yes in sim; hardware opt-in |
| PB1/PB2 lost or degraded after preset/front-panel actions | One layer checked while another broke | LCD-only or route-only assertions | LCD + chain frame + EEPROM + MAIN route/DSP together | Add PB1 S/PDIF + PB2 AES through standby/wake/front-panel preset | partly | needs hardware for audio |

The two known misses share the same shape: the old tests asserted an
implementation fallback or one visible layer rather than the product contract.
The PB2 bug needed EEPROM + CONTROL intent + emitted frame + MAIN route/DSP +
LCD coverage in one path. The Diagnostics bug needed a poisoned stale-state
setup, not only happy identity and page-entry reset.

## 5. Current Test Weaknesses

- `cmd 0x06` input route broadcast remains encoded as acceptable before PB2
  discovery. This is now wrong policy. The test to update is
  `tests/sim/test_v173_multi_pb_input_selection.py::test_valid_pb2_eeprom_stays_pending_on_single_pb_chain_until_discovery`;
  it currently expects `B0` at
  `tests/sim/test_v173_multi_pb_input_selection.py:1918`. The matching firmware
  comment still describes legacy pre-discovery `B0/06` at
  `src/dlcp_fw/asm/dlcp_control_v173.asm:3222`.
- Prefix/row0 checks remain in compatibility and hardware tests, including
  `tests/sim/test_v34_v173_compatibility.py:79`,
  `tests/sim/test_v34_v173_compatibility.py:142`,
  `tests/sim/test_v34_v173_compatibility.py:205`, and
  `tests/hardware/test_live_state_transitions.py:807`.
- Diag IR dispatch tests preserve only page prefix after actions, not exact
  16-character rows, for example
  `tests/sim/test_v172_v33_diag_identity.py:802` and
  `tests/sim/test_v172_v33_diag_identity.py:843`.
- PB2 old/lost input title tests check the title but not the row-1 body or
  EEPROM preservation at `tests/sim/test_v173_multi_pb_input_selection.py:1229`.
- V3.5 version-label tests still use a source-derived revision helper in one
  path rather than deriving expectations solely from the HEX under test at
  `tests/sim/test_firmware_version_label.py:177`.
- Live hardware identity coverage is partly V3.2-oriented, while current
  closure should be V1.73/V3.5; see
  `tests/hardware/test_live_state_transitions.py:536` and
  `tests/hardware/test_live_state_transitions.py:1519`.
- High-interest exploratory oracle cards are not all dispositioned as
  deterministic test, hardware gate, defer, or ignore.

### Special Check Findings

- Tests still accept `Same as PB1` only for explicit linked mode. I did not find
  a current test accepting it as fallback for persisted concrete PB2. The
  remaining problem is broader: `B0/06` is still accepted before PB2 discovery.
- PB1/PB2 persistence coverage now checks many layers, but not consistently in
  one field-realistic matrix across cold boot, PB2 rediscovery, standby/wake,
  dirty-save timing, LCD, frames, EEPROM, and MAIN route/DSP.
- Diagnostics can now fail the `seen=1, valid=0` old bug in source-fixture
  coverage, and canonical stale-valid replacement is covered. Missing canonical
  poisoned-state and old/lost/page-reentry separation remain gaps.
- Exact LCD coverage is strongest in current canonical Diag and preset filename
  tests. Adjacent compatibility and hardware/OCR tests still use prefix checks.
- Receiver-layer IR claims are proven for several current RB5 paths, but decoded
  injection remains in dispatcher and field-style matrices; those must not be
  cited as receiver-layer closure.
- Several button paths use realistic press/release helpers, but `chain.press()`
  still appears in field-style tests and should not be used for loop-consumption
  bugs.
- Current canonical HEX artifacts are used for key V1.73/V3.5 PB2, Diag, preset,
  and IR coverage, but some release metadata expectations remain source-derived.
- Hardware incidents are partially promoted. Current-line hardware gates remain
  stale/loose in places.
- gpsim retirement removed many assertions; replacement coverage exists for the
  major behavior lines, but there is no concise ledger mapping every deleted
  gpsim-only assertion to a rust-native test.
- Exploratory oracle findings do not all have deterministic regressions or
  documented dispositions; this is now a concrete gap.

## 6. Proposed Minimal Regression Set

1. **No input broadcast for `cmd 0x06`.**
   - Node: `tests/sim/test_v173_multi_pb_input_selection.py::test_input_routing_never_broadcasts_cmd06_for_single_or_pending_pb2`
   - Fixture/artifacts: canonical `V173_CONTROL_HEX` + `V35_MAIN_HEX`.
   - Stimulus: PB1 known, PB2 unseen; run both no-PB2-intent and persisted
     PB2 concrete intent cases; change PB1 input and force full-sync input step.
   - Expected observable: `B1/06/<pb1>` only; no `B0/06`; no `B2/06` until PB2
     discovery; pending PB2 concrete EEPROM and RAM intent unchanged.
   - Old-bug failure mode: old broadcast/relink behavior emits `B0/06`.
   - Runtime: slow.
   - Hardware required: no.

2. **PB2 concrete applies only after addressed PB2 discovery.**
   - Node: `tests/sim/test_v173_multi_pb_input_selection.py::test_pending_pb2_concrete_applies_as_b2_after_health_discovery`
   - Fixture/artifacts: canonical `V173_CONTROL_HEX` + `V35_MAIN_HEX`.
   - Stimulus: EEPROM `PB1=S/PDIF`, `PB2=AES`; start with PB2 unseen; allow
     addressed PB2 health reply; then force input sync.
   - Expected observable: before discovery, no `B0/06`; after discovery,
     `B2/06/AES`, exact PB2 LCD row, MAIN PB2 route/SRC state.
   - Old-bug failure mode: old behavior either broadcasts PB1 or relinks PB2.
   - Runtime: slow.
   - Hardware required: no.

3. **Diag page front-panel STBY must close both MAIN gates.**
   - Node: existing xfailed
     `tests/sim/test_v34_v173_field_repros_20260613.py::test_diag_page_front_panel_stby_enters_standby_and_closes_both_main_gates`.
   - Fixture/artifacts: current V1.73/V3.5 source or canonical variant.
   - Stimulus: press/release front-panel STBY from PB1/PB2 Diag pages.
   - Expected observable: standby LCD state and both MAIN active gates closed;
     wake restores.
   - Old-bug failure mode: current known failure remains xfailed.
   - Runtime: normal/slow.
   - Hardware required: no for sim; hardware gate recommended.

4. **Canonical Diagnostics identity retry from poisoned `seen=1, valid=0`.**
   - Node:
     `tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_canonical_diag_identity_retries_seen_without_valid_after_runtime_reply`
   - Fixture/artifacts: canonical `V173_CONTROL_HEX` + `V35_MAIN_HEX`.
   - Stimulus: poison identity state to `seen=1, valid=0`; enter PB1/PB2 Diag.
   - Expected observable: `cmd 0x25` re-emitted; suffixless state transient
     only; exact final rows.
   - Old-bug failure mode: stale `PBn OK` without version remains stable.
   - Runtime: slow.
   - Hardware required: no.

5. **Malformed identity replies do not commit identity.**
   - Node:
     `tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_cmd25_malformed_reply_sequences_do_not_commit_identity`
   - Fixture/artifacts: current V1.73/V3.5.
   - Stimulus: wrong `BF/4F` id, out-of-order `BF/50..55`, duplicate frame,
     missing frame, payload `>=0x10`, interleaved `BF/21..2B` and filename
     traffic.
   - Expected observable: no valid mask, no suffix, retry remains enabled.
   - Old-bug failure mode: unclear for the known bug; closes adjacent parser
     false-positive risk.
   - Runtime: normal.
   - Hardware required: no.

6. **Exploratory oracle card disposition gate.**
   - Node:
     `tests/sim/test_sim_chain_exploratory_preset_safety.py::test_high_interest_oracle_cards_have_regression_or_disposition`
   - Fixture/artifacts: oracle output index / curated card manifest.
   - Stimulus: parse high-interest cards.
   - Expected observable: every card maps to deterministic regression, hardware
     gate, defer with owner/reason, or ignored with reason.
   - Old-bug failure mode: old process lets findings remain heuristic only.
   - Runtime: fast.
   - Hardware required: no.

7. **Current hardware front-panel preset layout must be filename-capable.**
   - Node:
     `tests/hardware/test_live_state_transitions.py::test_live_manual_front_panel_preset_selection_requires_filename_capable_preset_layout`
   - Fixture/artifacts: current V1.73/V3.5 hardware.
   - Stimulus: operator physical preset selection.
   - Expected observable: reject legacy `Volume` / `Active: X`; require
     filename-capable Preset layout plus MAIN filename RAM.
   - Old-bug failure mode: missing filename row would be accepted today.
   - Runtime: hardware.
   - Hardware required: yes.

### Release Artifact Coverage Matrix

| Artifact row | Test files / node IDs | Metadata/identity source | UI/menu/persistence covered | chain/audio/DSP covered | Gaps |
|---|---|---|---|---|---|
| Current MAIN canonical HEX | `test_v172_v33_diag_identity.py`, V35 flash/version tests | mostly artifact-derived; one source-helper weakness remains | covered through canonical diag/preset/input tests | volume/TAS tests cover behavior | Make artifact-derived identity universal |
| Current CONTROL canonical HEX | PB2, diag, IR, control flash safety tests | parsed in flash safety; expected release rev documented | strong for PB1/PB2 persistence | chain/IR strong; audio split | live PB2 gate stale in docs |
| Source-assembled current MAIN | temp V3.5 fixtures | source/build helpers | broad behavior | broad behavior | can mask published HEX skew |
| Source-assembled current CONTROL | temp V1.73 fixtures | source/build helpers | broad behavior | broad behavior | some row0-only source tests |
| Historical compatibility artifacts | V3.2/V3.3/V3.4, V1.71/V1.72 | mixed | compatibility covered | mixed | do not treat as current release closure |

### Stimulus Fidelity Matrix

| Layer | Realistic stimulus helper | Shortcuts currently used | Known risks | Tests that must not use shortcuts | Proposed fixture cleanup |
|---|---|---|---|---|---|
| IR receiver layer | RB5 pulse train helper | decoded IR injection | misses rearm/inhibit/timing | wake, standby, current shortcut claims | add RB5 current-line Diag shortcut smoke |
| IR dispatcher layer | decoded event injection | by design | cannot prove receiver | command matrix only | label dispatcher-only tests clearly |
| Front-panel buttons | `set_control_pin` press/release helpers | `chain.press()` | stale one-shot consumption | standby/wake, PB actions | prefer press/release in field repros |
| USB/HID EP0 | sim backend HID/EP0 tests | monkeypatched `main_flash` unit glue | transport bugs missed | flasher/release identity | keep backend integration required |
| Chain UART frames | frame capture/assertions | direct RAM state seeds | hides wire discovery timing | PB2 rediscovery/reconnect | add health-discovery path tests |
| Power/standby/wake | sim gate/state checks, hardware gates | direct flag writes | ordering/I2C wake bugs | Diag STBY, PB persistence | unxfail Diag STBY regression |
| PB discovery/loss/reconnect | addressed health ping `B2/23/00` and `BF/2C` reply | direct `HEALTH_SEEN_MASK` writes | misses timing and pending state | PB2 concrete restore | canonical reconnect matrix |
| Dirty EEPROM save service | memory trace + forced save sentinel | forced idle-save | natural timeout edge | persistence lifecycle | add POR-before-save negative |

## 7. Hardware Gate Recommendations

- Add current V1.73/V3.5 live Diagnostics identity gate with artifact-derived
  expected OCR rows.
- Tighten front-panel preset hardware gate so `Volume` / `Active: X` is no
  longer accepted for filename-capable current release behavior.
- Add a live PB1 S/PDIF + PB2 AES power-cycle/persistence/audio route gate.
- Update stale PB2 field-closure docs from V1.73 rev `0x52` to current rev
  `0x5C` / build `20260628`.
- Keep SRC4382 acoustic confirmation hardware-only; the simulator can prove
  register/route contracts, not acoustic low-band correctness.

## 8. Open Questions / Unclear Items

- Whether malformed `cmd 0x25` reply handling should be tested via injected
  frames only or full MAIN/CONTROL interleaving with filename traffic. Best
  answer is likely both: injected parser tests for byte-level edge cases plus
  one full interleaving regression for the field-shaped state-machine risk.

The following are no longer open questions:

- Early boot `B0/06/PB1` before PB2 concrete latch is forbidden.
- V3.5 `chain_copy` now masks GIE around the TOS-sensitive commit and restores
  the prior GIE state; the former strict xfail is replaced by
  `test_v35_chain_copy_tos_rewrite_masks_and_restores_prior_gie`.
- Unmapped high-interest exploratory oracle cards are a coverage gap.

## 9. Appendix: Evidence

Selected commits inspected or classified:

- `5a56279` - gpsim-only deletion
- `e023c01` - gpsim wrapper excision
- `a3851f4` - RC5 pulse-train IR coverage
- `8b0dead`, `947ca22`, `d69d689`, `a274dfa` - V3.4/V1.73 field-bug line
- `26be54e`, `1122dcf`, `1725ff1` - V3.5 flash/release path
- `1fe8cae`, `7abe29b`, `c650bf9`, `165b7d1` - multi-PB input and robustness hardening
- `7086fba` - V1.73 x5C validation and diagnostics

Selected grep findings:

- Prefix/row0 LCD assertions remain in compatibility/hardware tests.
- `inject_decoded_ir_event` remains in dispatcher and field-style IR tests.
- `V173_CONTROL_HEX` and `V35_MAIN_HEX` are used in current canonical PB2,
  diag, preset, and IR coverage.
- `Same as PB1` is still accepted for explicit linked setting. It must not be
  accepted as fallback for persisted concrete PB2.
- Remaining xfail audit reports only the historical V3.4 boot-vector ABI xfail.
