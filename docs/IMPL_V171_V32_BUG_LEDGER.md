# V1.71 / V3.2 Implementation Bug Ledger

Last updated: 2026-05-11
Scope: deployed `DLCP_Control_V1.71.hex` with `DLCP_Firmware_V3.2.hex`
Status: active; current simulator red tests are green.  `BUG-REV-01` is
hardware-closed; remaining green rows still require the listed live-rig
confirmation.  The hardware rig is currently disconnected, so live closure is
blocked until MAIN USB, CONTROL, LCD camera, and Flipper are reconnected.

This ledger tracks product-firmware bugs in the recommended CONTROL/MAIN pair.
It is separate from:

- `docs/SIM_REWRITE_RUST_PROGRESS.md`, which is machine-readable and tracks
  Rust simulator migration work.
- `docs/V32_SIZE_OPTIMIZATION_PROGRESS.md`, which tracks code-size campaign
  experiments.

The rule for every bug here is:

1. Add or identify a simulator test that expresses the real hardware behavior
   and fails against the current implementation.
2. Keep the repository gate green by marking the red test
   `pytest.mark.xfail(strict=True, reason="<BUG-ID>: ...")` while the bug is
   open, or keep the failing test only on the active fix branch.
3. Prove the red shape at least once with `--runxfail` or by temporarily
   removing the xfail marker.
4. Fix firmware, simulator, or tooling.
5. Remove the xfail and require the test to pass in the normal gate.
6. Run the listed hardware confirmation before marking `done`.

Status values:

- `pending-red`: bug accepted; failing sim test not yet committed.
- `red`: failing sim test exists and is linked here.
- `fixing`: implementation work in progress.
- `green`: sim tests pass without xfail; hardware confirmation pending.
- `done`: sim and hardware gates have passed.
- `blocked`: cannot advance without a named external artifact or operator step.

Completion criteria for this ledger:

- Every active bug has a simulator red/green test listed in the active table
  and guarded by `tests/sim/test_v171_v32_ledger_hardware_gate.py`.
- The simulator gate is green:
  `.venv_ep0/bin/python -m pytest tests/sim -n 16 -q`.
- Hardware readiness is captured in
  `artifacts/probes/v171_v32_ledger_gate/preflight_current.json` by running:
  `.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --preflight --phase all --report-json artifacts/probes/v171_v32_ledger_gate/preflight_current.json`.
  For the full `--phase all` preflight, set the BUG-SETTINGS-01 expected
  tuple first: `DLCP_HW_EXPECTED_VOLUME_LOW`,
  `DLCP_HW_EXPECTED_INPUT`, and `DLCP_HW_EXPECTED_SETUP_PROFILE`.
- Each non-`done` bug has a stable per-bug closure artifact named
  `artifacts/probes/v171_v32_ledger_gate/bug_..._closure_current.json`,
  produced by the command printed from
  `.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --remaining`.
- `artifacts/probes/v171_v32_ledger_gate/artifact_summary_current.json` shows
  no missing, failed, or stale per-bug preflight reports, no missing or stale
  closure reports, and lists every remaining row under
  `ready_to_mark_done`; enforce this with:
  `.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --summarize-artifacts --require-all-ready`.
- Final stop condition:
  `.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --audit-completion --report-json artifacts/probes/v171_v32_ledger_gate/completion_audit_current.json`
  exits `0`; the JSON report includes both ledger status counts and the same
  artifact-readiness summary used by `--summarize-artifacts`, and the runner
  refuses `done` rows that lack explicit `DONE:` evidence in this audit table.
  The JSON `completion_checklist` must pass all four rows:
  `all_active_bugs_done`, `done_rows_have_done_evidence`,
  `hardware_artifacts_ready`, and
  `prompt_to_artifact_checklist_ready`.  The JSON
  `prompt_to_artifact_checklist` must also show each active bug's simulator evidence cell
  as `required_sim_evidence`, required hardware phases, preflight/closure
  artifact paths for non-`done` rows, `DONE:` evidence for `done` rows,
  artifact status, and no blocking reasons.

## Active Bugs

| ID | Status | Area | Symptom | Required red test |
| --- | --- | --- | --- | --- |
| BUG-DIAG-01 | green | CONTROL diagnostics | PB1/PB2 Diagnostics pages stay `n/a` during a static wait even though MAINs are present, and the visible per-PB page must not refresh at half cadence because the hidden PB is the next global target. | `tests/sim/test_v171_v32_layer5_diag_chain.py::{test_v171_v32_layer5_chain_diag_static_wait_updates_pb1_and_pb2,test_v171_v32_layer5_diag_visible_page_refreshes_on_next_cadence}`. |
| BUG-DIAG-02 | green | CONTROL diagnostics/UI | Diagnostics pages stall foreground services: static polling makes buttons less responsive and decoded IR commands are not dispatched while on PB1/PB2 pages. | `test_diag_loop_uses_non_modal_foreground_services`, `test_v171_v32_layer5_chain_sustained_diag_page_keeps_control_responsive`, `test_v171_v32_layer5_chain_diag_page_left_button_exits_promptly`, `test_v171_v32_layer5_diag_page_dispatches_ir_volume_mute_and_preset`, and `test_v171_v32_layer5_diag_page_dispatches_ir_standby_and_wake`. |
| BUG-IR-01 | green | CONTROL IR | Earlier real-IR gates did not move MAIN state, but the operator later explicitly retested real IR and reported that it works on both stock V1.6b and V1.71. The Timer1 non-blocking receiver remains retired; V1.71 rev `0x1C` uses the stock V1.6b in-ISR RC5 decoder path while formal versioned hardware-gate artifacts are collected. | `tests/sim/test_v171_ir_rc5_pulse_train.py::test_v16b_and_v171_rc5_pulse_train_decode_same_command_stress`, `tests/sim/test_v171_hang_modes.py::test_v171_ir_decode_uses_hardware_validated_stock_isr_path`, and `test_v171_profile_ir_actions_match_stock_v16b_dispatch_behavior`. |
| BUG-IR-02 | green | CONTROL IR/UI | Explicit IR standby/wake endpoints emit frames but do not update local CONTROL display state coherently. | `tests/sim/test_v171_v32_user_visible_desync_bugs.py::{test_explicit_ir_standby_updates_control_lcd_state,test_explicit_ir_wake_returns_control_lcd_to_volume}` and `test_v171_v32_layer5_diag_page_dispatches_ir_standby_and_wake`. |
| BUG-STDBY-01 | green | MAIN standby/wake | Volume-screen STBY can emit duplicate `B0/03/00` frames; the second duplicate clears the pending MAIN shutdown event before `standby_event_dispatch`, leaving the logical gate closed but hardware latches still enabled. | `tests/sim/test_v171_v32_standby_reconnect.py::{test_v32_duplicate_standby_preserves_pending_shutdown_event,test_v171_v32_v32_panel_wake_brings_up_main1_via_h2_re_emit}`. |
| BUG-PRESET-01 | green | MAIN release flash / preset filename | After `dlcp_v32_release_flash.py`, active preset A can report/show the B filename (`...v7`) while EEPROM slots verify correctly. | `test_v32_ep0_reapply_reload_filename_ram_for_restored_preset` and `test_v32_release_flash_sim_full_main_post_flash_state`. |
| BUG-PRESET-02 | green | MAIN preset apply | Rapid A/B reversal during apply can finish on the older target. Existing xact-gate tests protect filename transactions but do not prove latest-target convergence. | `tests/sim/test_v171_v32_user_visible_desync_bugs.py::test_rapid_preset_reversal_during_apply_finishes_on_latest_target`. |
| BUG-PRESET-03 | green | CONTROL preset dispatch | IR/menu preset handlers flip local `PRESET_BIT` before the fallible atomic TX helper succeeds; under TX saturation CONTROL can show a preset that was not sent or persisted. | `tests/sim/test_v171_v32_user_visible_desync_bugs.py::test_ir_preset_b_tx_saturation_does_not_change_local_preset_state`. |
| BUG-REV-01 | done | MAIN firmware identity | V3.2 app flash leaves runtime EEPROM identity at old values, e.g. `revision: 0x30 (EEPROM 2.3)`, because the app flasher streams program memory only and the firmware does not migrate the EEPROM tuple. | `test_v32_runtime_eeprom_identity_matches_release_hex_without_seed` and `test_build_v32_release_bumps_runtime_eeprom_revision_marker`. |
| BUG-SETTINGS-01 | green | MAIN release flash / user settings | MAIN app HID cmd `0x40` is a firmware-update handoff, but the V3.2 handler flushed factory defaults into EEPROM first, resetting volume to `-96 dB`, input to analog 1, and potentially the shared setup/profile byte after flash. | `tests/sim/test_dlcp_main_flash.py::test_v32_cmd40_bootloader_entry_preserves_saved_settings_in_source`, `tests/sim/test_v32_flasher_sim_backend_hid.py::test_sim_hid_cmd40_preserves_user_volume_and_input_settings`, and `test_v32_release_flash_sim_full_main_post_flash_state`. |

## Current Verification Snapshot

Green simulator runs through 2026-05-11:

- Consolidated ledger gate before the PB1/PB2 Diagnostics-IR split:
  `pytest -q tests/sim/test_v171_v32_layer5_diag_chain.py
  tests/sim/test_v171_layer5_diag_page.py::test_diag_loop_uses_non_modal_foreground_services
  tests/sim/test_v171_ir_rc5_pulse_train.py
  tests/sim/test_v171_ir_deferred_phase_miss.py
  tests/sim/test_v171_ir_command_matrix.py::test_v171_standby_then_wake_pair_consumed_by_dispatch
  tests/sim/test_v171_ir_command_matrix.py::test_v171_profile_ir_actions_match_stock_v16b_dispatch_behavior
  tests/sim/test_v171_v32_standby_reconnect.py
  tests/sim/test_v171_v32_user_visible_desync_bugs.py
  tests/sim/test_v32_flasher_sim_backend_ep0.py::test_v32_ep0_reapply_reload_filename_ram_for_restored_preset
  tests/sim/test_v32_flasher_sim_backend_hid.py::test_v32_runtime_eeprom_identity_matches_release_hex_without_seed
  tests/sim/test_dlcp_main_flash.py::test_build_v32_release_bumps_runtime_eeprom_revision_marker
  tests/sim/test_v32_release_flash_sim.py::test_v32_release_flash_sim_full_main_post_flash_state`
  -> `39 passed`.
- PB1/PB2 Diagnostics-page IR split:
  `pytest -q tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_diag_page_dispatches_ir_volume_mute_and_preset
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_diag_page_dispatches_ir_standby_and_wake`
  -> `4 passed`.
- Diagnostics page behavior: static PB1/PB2 refresh, PB cache isolation,
  mixed-counter LCD rendering, LEFT responsiveness, no counter cascade,
  decoded IR volume/mute/preset, decoded IR standby/wake on PB1 and PB2.
- IR decode/dispatch path: V1.6b and V1.71 both pass the same RB5 RC5
  pulse-train stress suite in sim, including the current Hypex profile-1
  commands used by the Flipper hardware sender, and V1.71 profile dispatch
  state/frame deltas match stock V1.6b for profile-1 and profile-2 commands.
- User-visible CONTROL regressions: preset-screen STBY, explicit IR
  standby/wake, IR preset TX-saturation rollback, rapid B->A preset reversal.
- BUG-IR-02 standby/wake hardware-helper coverage is also pinned at the CLI
  unit-test level: the `preset-standby-wake` phase sends `STANDBY`, waits for
  `Zzz...` standby LCD evidence, sends `WAKE`, and waits for `Volume` after
  wake before the phase can pass.
- Standby/wake reconnect: V1.71 panel STBY/WAKE returns both V3.2 MAINs and
  CONTROL to Volume, and V3.2 duplicate-standby handling preserves a pending
  hardware-shutdown event.
- Broader IR/preset sweep:
  `pytest -q tests/sim/test_v171_ir_command_matrix.py
  tests/sim/test_v171_ir_endpoints.py tests/sim/test_v171_preset_inline.py
  tests/sim/test_v171_v32_dual_main_preset_sync.py`
  -> `25 passed`; this covers shared IR volume/mute/power behavior,
  V1.71 explicit IR standby/wake endpoints, preset IR A/B shortcuts, and
  dual-MAIN preset convergence/filename/DSP agreement.
- BUG-IR-01 fallback gate after the 2026-05-09 live V1.71 failure:
  `pytest -q tests/sim/test_v171_hang_modes.py::test_v171_ir_decode_uses_hardware_validated_stock_isr_path
  tests/sim/test_v171_hang_modes.py::test_v171_display_loop_no_longer_calls_legacy_ir_service
  tests/sim/test_v171_ir_deferred_phase_miss.py
  tests/sim/test_v171_ir_rc5_pulse_train.py`
  -> `10 passed`.  Broader IR/control follow-up after rebuilding V1.71
  rev `0x1A`:
  `pytest -q tests/sim/test_v171_ir_command_matrix.py
  tests/sim/test_v171_ir_endpoints.py tests/sim/test_v171_preset_inline.py
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_diag_page_dispatches_ir_volume_mute_and_preset
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_diag_page_dispatches_ir_standby_and_wake
  tests/sim/test_dlcp_control_flash_safety.py`
  -> `38 passed`.
- V3.2 release-flash/revision regressions: runtime EEPROM identity, V3.2
  builder revision marker, EP0 reapply filename RAM, release-flash post-state,
  and exact release-flash preservation of non-default MAIN volume, input, and
  shared setup/profile settings.
- BUG-SETTINGS-01 focused exact-preservation follow-up:
  `pytest -q tests/sim/test_dlcp_main_flash.py::test_v32_cmd40_bootloader_entry_preserves_saved_settings_in_source
  tests/sim/test_v32_flasher_sim_backend_hid.py::test_sim_hid_cmd40_preserves_user_volume_and_input_settings
  tests/sim/test_v32_release_flash_sim.py::test_v32_release_flash_sim_full_main_post_flash_state
  tests/sim/test_v171_v32_ledger_hardware_gate.py`
  -> `68 passed`.  This includes the shared setup/profile byte
  `EEPROM[0x0E]` / `RAM[0x0B8]` and exact input preservation through the full
  release-flash sim ceremony.
- Broader MAIN flasher regression pass after the exact input/profile restore:
  `pytest -q tests/sim/test_dlcp_main_flash.py
  tests/sim/test_v32_flasher_sim_backend_hid.py
  tests/sim/test_v32_release_flash_sim.py`
  -> `46 passed, 3 warnings`.
- Hardware-gate runner mapping:
  `pytest -q tests/sim/test_v171_v32_ledger_hardware_gate.py`
  -> `66 passed`; this pins every active ledger bug to a `--bug` hardware
  phase selection, verifies the ledger hardware phase-map table matches the
  runner, verifies runner phase opt-in/env contracts for the live hardware tests,
  verifies runner phase resource requirements for MAIN visibility, LCD camera,
  and Flipper access,
  verifies the completion-audit table covers every active bug, verifies
  the top-level `Last updated`, verification snapshot, and audit dates stay in sync, verifies
  active-table `done` status matches explicit `DONE:` hardware evidence in the
  completion audit, verifies every active bug has named simulator evidence tests that exist and are not
  xfailed, verifies the active table's explicit required-red-test node IDs
  resolve to real non-xfailed simulator tests, verifies the completion-criteria
  checklist documents the required artifacts and final stop condition, and verifies alias
  expansion/de-duplication, list-mode discovery output, report-json per-bug
  closure phase maps and computed `bug_closure` status, automatic default
  report writing and stdout closure summaries for live `--preflight` /
  `--execute` runs, `--require-bug-closed` enforcement for live closure
  verification, that every active status uses the documented vocabulary, that every phase node exists in
  `tests/hardware/test_live_state_transitions.py` and every live test is
  reachable from the runner, the multi-phase execute pause behavior required
  for PB1/PB2 Diagnostics button/IR, the Diagnostics IR gate's explicit
  Hypex-profile contract for `F1`/`F2` and `STANDBY`/`WAKE`, the no-OCR IR
  receiver sweep, the preflight rejection of host-only camera inventories
  unless `DLCP_HW_CAMERA_SELECTOR` is set, the settings-preservation preflight
  requirement for `DLCP_HW_EXPECTED_VOLUME_LOW`, `DLCP_HW_EXPECTED_INPUT`, and
  `DLCP_HW_EXPECTED_SETUP_PROFILE`,
  byte-literal validation for those required settings env vars in both the
  runner preflight and the direct live settings pytest,
  the guard that real-IR legacy stress cannot pass with zero stress repeats,
  the same settings env names surfaced by `--list`, dry-run, `--remaining`,
  and its combined plan,
  the `--report-json` preflight and
  phase execution artifact paths, preservation of HID/camera/Flipper inventory
  errors in that JSON report, V1.6b-vs-V1.71 real-IR operator runs, the
  expected CONTROL hex identity and payload hashes recorded in legacy-IR
  `result.json` artifacts, the same expected CONTROL hex identity and CRC
  printed by the runner dry run / list view and emitted in phase JSON payloads,
  and the exact stock-V1.6b/V1.71 flash commands printed for `BUG-IR-01`, plus the
  `--remaining` non-probing list of non-`done` bugs, exact per-bug closure
  commands, and stable per-bug report paths, and the explicit filter that keeps already-`done` rows out of
  `--remaining` even when selected by `--bug`, plus the `--audit-completion`
  stop-condition command that fails until every active row is `done`, including
  the ledger documentation of that stop condition, exact agreement between the
  audit's remaining-bug set and the active table's non-`done` rows, and the
  embedded artifact-readiness summary in the audit report, and the runner-side
  rejection of `done` rows that lack explicit `DONE:` audit evidence, and the
  audit JSON `completion_checklist` that separately reports active-row,
  `DONE:`-evidence, hardware-artifact readiness, and prompt-to-artifact
  readiness, and the
  `prompt_to_artifact_checklist` that maps each active bug to its simulator
  evidence cell, required hardware phases, artifact paths or `DONE:` evidence,
  and blockers, and
  the `--summarize-artifacts --require-all-ready` reader and default
  `artifact_summary_current.json` report path for stable per-bug preflight and
  closure reports, plus schema-11 evidence-identity rejection for stale reports
  produced against older ledger, runner, hardware-test, live hardware helper,
  hardware runbook, flash helper, V3.2 MAIN, V1.71 CONTROL, or stock V1.6b
  CONTROL files, and the
  runner-side rejection of pytest phases that skipped without passing a live
  hardware test.  Rerun after
  tightening the CONTROL bootloader-entry instructions, camera preflight, and
  report-json / remaining-bug support, plus the combined `--remaining`
  execution-order guard that keeps the stock V1.6b real-IR baseline
  immediately followed by the V1.71 restore/stress phase:
  `.venv_ep0/bin/python -m pytest -q tests/sim/test_v171_v32_ledger_hardware_gate.py`
  -> `66 passed`.  This now includes a guard that every live hardware phase is
  required by at least one active ledger bug, so the `preset-mute` timing phase
  cannot be orphaned outside closure readiness, and a guard that the active
  table lists every concrete simulator evidence test used for each bug.  It
  also verifies that every bug detail section documents a `Red test target`,
  and that Diagnostics hardware prompts stay on the one-second static-cadence
  contract instead of drifting back to a two-second settle.
- Diagnostics focused gate after the V1.71 rev `0x1C` visible-page cadence
  rebuild:
  `.venv_ep0/bin/python -m pytest -q tests/sim/test_v171_layer5_diag_page.py
  tests/sim/test_v171_v32_layer5_diag_chain.py`
  -> `57 passed`.  The focused failure subset also passes:
  `test_phase3_4_renderer_movlb_discipline_before_banked_writes`,
  `test_diag_loop_retries_visible_page_on_silent_pb`,
  `test_v171_v32_layer5_chain_diag_static_wait_updates_pb1_and_pb2`, and
  `test_v171_v32_layer5_diag_visible_page_refreshes_on_next_cadence`
  -> `5 passed`.
- Flipper IR sender/profile support:
  `.venv_ep0/bin/python -m pytest -q tests/sim/test_hardware_flipper_ir.py
  tests/sim/test_v171_v32_ledger_hardware_gate.py`
  -> `73 passed`; this now covers both Hypex-profile RC5 (`addr=0x10`) and
  standard RC5 (`addr=0x00`) action names.  The hardware legacy-IR test also
  collected cleanly after adding `DLCP_HW_IR_PROFILE=HYPEX|STANDARD`:
  `.venv_ep0/bin/python -m pytest tests/hardware/test_live_state_transitions.py::test_live_ir_legacy_command_stress_from_volume --collect-only -q`
  -> `1 test collected`.
- Legacy-IR hardware artifact support:
  `.venv_ep0/bin/python -m pytest tests/hardware/test_live_state_transitions.py::test_live_ir_legacy_command_stress_from_volume --collect-only -q`
  -> `1 test collected` after adding pass/fail `result.json` capture under
  `artifacts/probes/hardware_state_test/pytest/legacy_ir_stress/...`.  The
  artifact payload now also records the expected CONTROL hex path, static
  release metadata, payload CRC, and payload/application/bootloader SHA-256
  hashes for the requested `DLCP_HW_EXPECTED_CONTROL_VERSION`.
- IR receiver-sweep diagnostic support:
  `.venv_ep0/bin/python -m pytest -q tests/sim/test_hardware_state_test.py
  tests/sim/test_v171_v32_ledger_hardware_gate.py`
  -> `111 passed`; this includes artifact-path reporting for both no-state-
  change failures and Flipper/sender command failures.  The live opt-in test
  also collects cleanly:
  `.venv_ep0/bin/python -m pytest tests/hardware/test_live_state_transitions.py::test_live_ir_receiver_profile_sweep_records_any_state_change --collect-only -q`
  -> `1 test collected`.
- Hardware helper + ledger support after the V1.71 rev `0x1C` rebuild:
  `.venv_ep0/bin/python -m pytest -q tests/sim/test_hardware_state_test.py
  tests/sim/test_hardware_flipper_ir.py
  tests/sim/test_v171_v32_ledger_hardware_gate.py`
  -> `118 passed`.
- Full simulator gate:
  `.venv_ep0/bin/python -m pytest tests/sim -n 16 -q`
  -> `989 passed, 6 skipped, 7 warnings` after the V1.71 rev `0x1C`
  visible-Diagnostics-page cadence rebuild, V1.71 rev `0x1A`
  stock-compatible IR fallback rebuild, CONTROL-flash first-ACK
  timeout/watchdog hardening, HFD update-stream disassembly contract test, and
  safe-wrapper timeout-guidance regression, preset-convergence failure artifact
  capture, standard-RC5 Flipper profile support, no-OCR IR receiver-sweep
  artifact support, stricter hardware-gate preflight, JSON report support, and
  the ledger completion-audit/simulator-evidence/active-table resolver,
  date-sync guard, active status-vs-completion audit, per-bug closure-map, computed
  closure-status, default report-artifact / `--require-bug-closed` guards,
  active status-vocabulary guard, completion-criteria checklist guard,
  preservation of already-`done` ledger status in preflight/list reports, and
  the `--remaining` per-bug closure-command view, already-`done` filter, and
  `--audit-completion` stop condition plus ledger documentation guard, and
  stable closure-artifact summary reporting with the `--require-all-ready`
  pre-ledger-mutation gate, the `--list-phases` spelling alias, and byte-literal
  validation for the required settings-preservation env vars, plus the real-IR
  legacy-stress minimum-repeat guard, skipped-phase rejection, and direct
  live-settings pytest byte-range rejection, and expected CONTROL hex identity
  capture in legacy-IR hardware artifacts:
  `.venv_ep0/bin/python -m pytest tests/sim -n 16 -q` ->
  `989 passed, 6 skipped, 7 warnings`.
- Live hardware test collection:
  `.venv_ep0/bin/python -m pytest tests/hardware/test_live_state_transitions.py --collect-only -q`
  -> `16 tests collected`.  The phase runner collect/report path also works:
  `.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --collect --phase all --report-json artifacts/probes/v171_v32_ledger_gate/collect_only.json`
  -> `16 tests collected` and wrote the JSON command manifest.
  After the later positive operator IR report, the full collect/report path was
  rerun with
  `--report-json artifacts/probes/v171_v32_ledger_gate/collect_after_ir_operator_report.json`
  and again collected `16` hardware tests while writing the phase command
  manifest plus the per-bug `bug_phase_map` closure map and `bug_closure`
  status object.  Because this was a collect-only run, every selected
  closure row is intentionally `not_run` until a real `--execute` report
  records phase return codes.  Real `--preflight` and `--execute` runs now
  auto-write timestamped reports under
  `artifacts/probes/v171_v32_ledger_gate/` even when `--report-json` is not
  supplied, so hardware closure attempts always leave an audit artifact.
  Current phase-selector enumeration also resolves cleanly:
  `.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --list --report-json artifacts/probes/v171_v32_ledger_gate/list_phases_current.json`
  -> `0`, listing all 20 canonical hardware phase selectors, both alias
  selectors, every `BUG-*` selector expansion, and the selected all-phase
  manifest.  The spelling alias `--list-phases --bug BUG-IR-01` also resolves
  and writes `artifacts/probes/v171_v32_ledger_gate/list_phases_alias_current.json`.
- HFD CONTROL-update contract spot check after correcting the sequence docs:
  `.venv_ep0/bin/python -m pytest -q
  tests/sim/test_dlcp_control_flash_safety.py::test_hfd_v212_control_update_disassembly_contract_is_documented
  tests/sim/test_dlcp_control_flash_safety.py::test_flash_control_starts_with_first_hfd_data_report`
  -> `2 passed`; this pins that HFD's first `0x42` already carries bytes
  0..29 and that our flasher does not send a separate magic/init report.
- CONTROL safe-flash focused gate after adding the timeout-guidance regression:
  `.venv_ep0/bin/python -m pytest -q tests/sim/test_dlcp_control_flash_safety.py`
  -> `16 passed`; rerun after the visible-Diagnostics-page cadence rebuild
  reports V1.71 rev `0x1C` and CRC `0x3707`.

Hardware confirmation remains required before any row can move from `green` to
`done`; `BUG-REV-01` is the first closed row.  Live hardware status from
2026-05-09 after reconnecting MAINs,
camera, and Flipper:

- CONTROL flash relay: HFD-style streaming is confirmed.  With CONTROL already
  in manual `UP+DOWN` bootloader mode, `scripts/flash_control_safe.sh --path
  'DevSrvsID:4298194038' --pace-ms 0 --init-delay-ms 0 --yes` streamed the
  V1.71 payload and returned CRC verify `41 00 aa`; CONTROL rebooted to
  `Volume` / `Active: A`.  A later operator reboot still left CONTROL in app
  mode (`Volume` / `Active: A`), so the V1.71 rev `0x1C` reflash is still
  blocked on a successful manual `UP+DOWN` bootloader entry.  When CONTROL is
  not in bootloader, the safe wrapper now fails under `--live-timeout-s`
  instead of leaving a hung host process; the observed app-mode retry exited
  with code 124 after a 5 s watchdog.  A later 2026-05-09 retry after an
  ordinary CONTROL reboot timed out on both current MAIN relay paths
  (`DevSrvsID:4298202446` RIGHT and `DevSrvsID:4298202769` LEFT) with a 20 s
  watchdog, and camera OCR again read `Volume` / `Active: A`; that confirms the
  reboot did not enter the manual CONTROL bootloader.  The operator/runbook
  text now matches the bootloader disassembly: hold `UP+DOWN` for at least
  6 s and do not press `SELECT`; a shell syntax check and V1.71 preflight pass
  (`bash -n scripts/flash_control_safe.sh` and
  `scripts/flash_control_safe.sh --hex
  firmware/patched/releases/DLCP_Control_V1.71.hex --preflight-only`) confirm
  the wrapper still parses and reports V1.71 rev `0x1C` CRC `0x3707`.  A
  current OCR poll still reads `Volume` / `Active: A`, so CONTROL has not yet
  entered bootloader.  The stock V1.6b payload preflight also passes and
  reports CRC `0x2199`, ready for the first cross-version IR baseline flash
  once bootloader entry succeeds.  A later camera capture briefly looked like
  a bootloader screen to human inspection, but stock V1.6b live flash attempts
  through both current MAIN paths (`DevSrvsID:4298202446` and
  `DevSrvsID:4298202769`) still timed out after 180 s with no first ACK.  The
  follow-up image artifact
  `artifacts/probes/hardware_lcd/runs/20260509_214605/capture_1.jpg` showed
  an app screen (`Volume:-96.0dB A` / `Auto Detect`), so the V1.6b baseline
  flash is still not complete.
- MAIN identity: the targeted live identity gate passed for V3.2 rev `0x55`
  with A/B/A filename RAM/readback on both connected MAINs.  A live
  before/after V3.2 release-flash run also passed on both connected MAINs:
  `scripts/dlcp_v32_release_flash.py --right --path 'DevSrvsID:4298181537'`
  and `scripts/dlcp_v32_release_flash.py --left --path 'DevSrvsID:4298194038'`
  each reported stable pre/post settings `-96 dB` / input `0x00` /
  setup-profile `0x04`, verified A/B preset EEPROM + filename RAM, restored
  the correct all-channel route, and the formal settings gate passed with
  `DLCP_HW_EXPECTED_VOLUME_LOW=0xA0`, `DLCP_HW_EXPECTED_INPUT=0x00`,
  `DLCP_HW_EXPECTED_SETUP_PROFILE=0x04`.  An attempted MAIN-only EP0 seed of
  `-60 dB` / input `0x03` held for about 2 seconds but was then overwritten by
  CONTROL's stable broadcast back to `0xA0` / `0x00`, so a non-default volume
  hardware proof still needs the operator to set volume through CONTROL before
  flashing.  BUG-SETTINGS-01 remains open only for that stronger volume proof
  and the real-IR profile dispatch confirmation.
  After the later IR-failure and front-panel-A checks, the identity phase was
  rerun on the current pair and again passed (`1 passed, 3 warnings`), with
  the test restoring preset A after its A/B/A probe.
- Physical preset A: `front-panel-preset-a` passed on the connected pair
  without additional operator input because the rig was already on
  `Volume` / `Active: A`; both MAINs and the CONTROL LCD agreed on preset A
  and the active filename RAM matched `LX521.4 22MG10F-v5`.  The corresponding
  physical preset B gate still requires the operator to select B from the
  CONTROL front panel before running.
- Real IR has positive operator-reported hardware evidence after the earlier
  failed artifacts: on 2026-05-10, the operator retested real IR and reported
  that it works on both stock CONTROL V1.6b and CONTROL V1.71.  The earlier
  failures are kept below as rig/session artifacts, not as the current
  conclusion.  The previous
  V1.71 rev `0x19` run failed at the first volume command: both MAINs stayed
  at logical volume low `0xA0`.  Both MAINs reported shared setup/profile byte
  `ram_0x0B8 = 0x04` (`BF/1D` Hypex RC5 profile), and Flipper CLI help
  confirms `ir tx <protocol> <address> <command>` arguments are hex-formatted,
  so that failure was not explained by the profile byte or decimal argument
  parsing.  A later current-firmware `preset-convergence` hardware phase also
  failed: after a Flipper F2 request, both MAINs stayed on preset A until the
  15 s timeout.  The lower-level Flipper helper also accepted and echoed
  `ir tx RC5 10 39` (F2) with no CLI error, and an immediate MAIN snapshot
  still showed both sides on preset A, so that known failure was below the host
  command serialization layer.  Both payloads pass safe-flasher preflight:
  stock V1.6b CRC `0x2199`; V1.71 rev `0x1C` CRC `0x3707`.  A direct
  `VOL_UP` helper check likewise emitted `ir tx RC5 10 33` with no Flipper CLI
  error and both MAIN logical-volume lows remained `0xA0`, so that failed live
  session was broad IR receive/dispatch, not preset-only behavior.  After the
  ambiguous stock-style CONTROL app screen (`Volume:-96.0dB A` /
  `Auto Detect`) appeared, the V1.6b-labelled hardware baseline gate was run:
  `DLCP_HW_IR_LEGACY_STRESS=1 DLCP_HW_EXPECTED_CONTROL_VERSION=V1.6b
  pytest -q -s tests/hardware/test_live_state_transitions.py::test_live_ir_legacy_command_stress_from_volume --run-hardware`.
  It failed at the first volume command with both MAINs unchanged
  (`0xA0 -> 0xA0`).  A follow-up direct Flipper command was accepted as
  `ir tx RC5 10 33`.  Standard RC5 profile was also checked directly with
  `ir tx RC5 00 10` (`Vol+` for profile type `0x03`); both MAINs again stayed
  at logical volume low `0xA0`.  The later operator test supersedes the
  "known-good baseline unavailable" suspicion; formal closure still needs the
  exact working command/profile matrix or versioned runner artifacts.  The
  test harness now exposes `DLCP_HW_IR_PROFILE=STANDARD` so future baseline
  runs can explicitly test the profile if the CONTROL setup byte was reset
  from Hypex to standard RC5.
  The Hypex-profile V1.6b-labelled failure is captured in
  `artifacts/probes/hardware_state_test/pytest/legacy_ir_stress/20260509_220554/result.json`;
  it records start LCD `Volume` / `Active: A`, Flipper command
  `ir tx RC5 10 33`, and unchanged final volumes
  `DevSrvsID:4298202446=0xA0`, `DevSrvsID:4298202769=0xA0`.
  The equivalent standard-profile artifact is
  `artifacts/probes/hardware_state_test/pytest/legacy_ir_stress/20260509_220802/result.json`;
  it records Flipper command `ir tx RC5 00 10` with the same unchanged
  `0xA0` final volumes.
  The rig is presently in a CONTROL app screen rather than the manual update
  bootloader.

Operator wrapper for the remaining hardware evidence:
`scripts/run_v171_v32_ledger_hardware_gate.py`.  Its default dry-run mode
prints every phase, exact env vars, and manual preconditions; execute targeted
phases with, for example,
`.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --execute --phase diag-ir-actions`.
The `diag-ir-actions` alias expands to the PB1 and PB2 per-page gates and
sets `DLCP_HW_EXPECTED_DIAG_PAGE` accordingly.  Multi-phase `--execute` runs
pause before each phase by default, because PB1/PB2 Diagnostics button/IR and
the V1.6b-vs-V1.71 real-IR pair both require manual repositioning or firmware
changes between phases; `--no-pause` is the explicit unattended override.
The runner also accepts `--bug BUG-...` selectors using the phase map below,
so `--bug BUG-DIAG-02` expands to the PB1/PB2 diagnostics data, button, and IR
gates.
Use `--list` / `--list-phases --bug BUG-...` to print the resolved phase list
without probing hardware or invoking pytest.
Use `--remaining` to print only the non-`done` ledger bugs with their exact
`--preflight --bug BUG-...` and `--execute --keep-going --bug BUG-...
--require-bug-closed BUG-...` closure commands and stable per-bug
`--report-json artifacts/probes/v171_v32_ledger_gate/bug_..._{preflight,closure}_current.json`
paths; this mode also avoids probing hardware.  It prints phase-required
operator env vars such as `DLCP_HW_EXPECTED_VOLUME_LOW` and
`DLCP_HW_EXPECTED_INPUT`, plus `DLCP_HW_EXPECTED_SETUP_PROFILE` for
`BUG-SETTINGS-01`, and prints the expected CONTROL hex identity / CRC for the
stock V1.6b and V1.71 legacy-IR phases.  It also prints a deduplicated
combined plan that runs all remaining bug selectors once with
`--mirror-selected-bug-reports`, writing `remaining_preflight_current.json` /
`remaining_closure_current.json` plus the stable per-bug report paths consumed
by the artifact summary.  If a combined run fails for one bug but another
bug's own required phases passed, the artifact summary can still mark the
unaffected bug ready while leaving the failed bug not ready.
Use `--summarize-artifacts --require-all-ready` after live runs to read those
stable per-bug preflight and closure reports, list readiness failures, and
list which bugs have passed both readiness and closure evidence and are ready
to mark `done`.  Without `--report-json`, this mode writes
`artifacts/probes/v171_v32_ledger_gate/artifact_summary_current.json`.  Each
report carries an evidence identity over this ledger's hardware phase-map
contract, the runner, the hardware runbook, the hardware test file, live
hardware helper modules, flash helper modules, the safe CONTROL flash wrapper,
canonical V3.2 MAIN hex, canonical V1.71 CONTROL hex, and stock V1.6b CONTROL
hex; the summary refuses stale PASS/PASS artifacts while allowing mutable
ledger status / `DONE:` evidence edits after live artifacts are captured.  The
current report schema is `11`, bumped after schema `6` added the hardware
runbook to the evidence identity and schema `5` added expected CONTROL hex
identity to legacy-IR phase and remaining-plan payloads.  Schema `7` records
whether the current PASS preflight report selected every phase required by the
bug; a generic PASS preflight for the wrong phase set is not sufficient to mark
a bug ready.  Schema `8` adds the completion-audit prompt-to-artifact checklist,
schema `9` makes that checklist a top-level completion blocker, and schema
`10` records the `DONE:` evidence line for already-closed rows.  Schema `11`
rejects weak `DONE:` rows that lack a concrete pass result and command or
artifact path.

Earlier hardware readiness preflight on 2026-05-09 after reconnecting MAINs,
camera, and Flipper, before the host-camera-only filter was added:
`.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --preflight --phase all`
-> PASS, with two MAIN HID devices in app mode, three visible camera entries,
and one Flipper serial candidate (`/dev/cu.usbmodemflip_Ovarlide1`).  The
non-manual hardware identity phase also passed:
`.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --execute --no-pause --phase identity`
-> `1 passed` / `PASS [identity]`.  Live closure still requires the manual
front-panel, Diagnostics-page, release-flash settings, and cross-version
real-IR phases listed below.  Rerun the current stricter preflight after
reconnecting; host-only cameras no longer satisfy camera-required phases unless
`DLCP_HW_CAMERA_SELECTOR` is explicitly set.

Latest hardware-disconnected preflight on 2026-05-09:
`.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --preflight --bug BUG-IR-01`
-> FAIL as expected with zero MAIN HID devices and zero Flipper serial
candidates; camera inventory still lists host cameras only.  This is a rig
availability state, not a firmware result.  Reconnect the hardware before
using the live phase results for closure.
The full gate preflight has the same blocker:
`.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --preflight --phase all --report-json artifacts/probes/v171_v32_ledger_gate/disconnected_preflight.json`
-> FAIL with zero MAIN HID devices, zero external LCD camera candidates, and
zero Flipper serial candidates; camera inventory lists only the host camera
entries.  Set `DLCP_HW_CAMERA_SELECTOR` only if one of the listed cameras is
intentionally aimed at the DLCP LCD.  The JSON report records the selected
phase commands and the preflight failures.
After that disconnected preflight, the operator retested real IR on 2026-05-10
and reported that it works on both stock CONTROL V1.6b and CONTROL V1.71.  The
workspace still cannot see the rig: `.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --preflight --bug BUG-IR-01 --report-json artifacts/probes/v171_v32_ledger_gate/ir_preflight_after_operator_report.json`
-> FAIL with zero MAIN HID devices, zero external LCD camera candidates, and
zero Flipper serial candidates.  Treat the IR result as positive
operator-reported hardware evidence until a versioned gate report can be
captured from this workspace.
Latest preflight on 2026-05-11:
`.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --preflight --phase all --report-json artifacts/probes/v171_v32_ledger_gate/preflight_current.json`
-> FAIL with zero MAIN HID devices, zero external LCD camera candidates, and
zero Flipper serial candidates; camera inventory lists only
`MacBook Pro Camera` and `MacBook Pro Desk View Camera`.  The full preflight
also requires the BUG-SETTINGS-01 expected settings tuple, and currently
reports `DLCP_HW_EXPECTED_INPUT`, `DLCP_HW_EXPECTED_SETUP_PROFILE`, and
`DLCP_HW_EXPECTED_VOLUME_LOW` as missing.  The runner wrote the stable report
`artifacts/probes/v171_v32_ledger_gate/preflight_current.json`,
including stdout `Bug closure status` and JSON `bug_closure` rows.  Because
this was a preflight-only run, every selected non-`done` closure row is
correctly `not_run`, while already-closed `BUG-REV-01` stays `done`; this
artifact only proves current rig availability, not firmware behavior.
The combined mirrored preflight was also refreshed after the schema-11 bump:
`.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --preflight --bug BUG-DIAG-01 --bug BUG-DIAG-02 --bug BUG-IR-01 --bug BUG-IR-02 --bug BUG-PRESET-01 --bug BUG-PRESET-02 --bug BUG-PRESET-03 --bug BUG-SETTINGS-01 --bug BUG-STDBY-01 --mirror-selected-bug-reports --report-json artifacts/probes/v171_v32_ledger_gate/remaining_preflight_current.json`
-> FAIL for the same disconnected-rig / missing-settings reasons, and rewrote
each `bug_*_preflight_current.json` mirror with current schema-11 identity.
The completion audit command also records the current blocker:
`.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --audit-completion --report-json artifacts/probes/v171_v32_ledger_gate/completion_audit_current.json`
-> FAIL with `BUG-REV-01` done and the remaining nine rows still `green`.
The runner wrote
`artifacts/probes/v171_v32_ledger_gate/completion_audit_current.json`,
including the prompt-to-artifact checklist with `BUG-REV-01` ready and the
remaining nine rows blocked by `ledger_status_not_done` and
`hardware_artifacts_not_ready`.
The stable artifact summary currently confirms no remaining live closure is
ready:
`.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --summarize-artifacts --require-all-ready --python .venv_ep0/bin/python`
-> every remaining `green` row is not ready; the current preflight evidence is
the disconnected-rig `FAIL`, closure reports are still missing, and
`BUG-REV-01` is ledger `done`.  The command exits `1` until every non-`done`
row is ready and writes
`artifacts/probes/v171_v32_ledger_gate/artifact_summary_current.json`.

Hardware phase map for `scripts/run_v171_v32_ledger_hardware_gate.py --bug`:

| Bug(s) | Required phase(s) |
| --- | --- |
| BUG-REV-01 | `identity` |
| BUG-PRESET-01 | `identity`, then `front-panel-preset-a`, `front-panel-preset-b` |
| BUG-PRESET-02 | `rapid-toggle`, plus `front-panel-preset-a` / `front-panel-preset-b`; manual rapid physical A/B if the operator can reproduce the in-progress switch |
| BUG-PRESET-03 | Covered by sim for the saturated path; ordinary live path covered by `front-panel-preset-a`, `front-panel-preset-b`, `preset-convergence`, `rapid-toggle` |
| BUG-STDBY-01 | `front-panel-standby-wake`, `preset-standby-wake`, `reconnect-soak` |
| BUG-IR-01 | `ir-receiver-sweep`, then `ir-legacy-v16b`, then `ir-legacy-v171`; compare both versioned runs |
| BUG-IR-02 | `diag-ir-actions`, plus `preset-mute` and `preset-standby-wake`; the runner sets a strict standby-LCD env opt-in so the standby/wake sweep requires literal standby text rather than the guarded blank fallback |
| BUG-DIAG-01 | `diag-layout-pb1`, `diag-pb1`, `diag-pb2` |
| BUG-DIAG-02 | `diag-pb1`, `diag-pb2`, `diag-button-actions`, `diag-ir-actions` |
| BUG-SETTINGS-01 | `settings`, then rerun the relevant release-flash ceremony, `identity`, and `ir-receiver-sweep` |

For BUG-IR-02, the `preset-standby-wake` phase sets
`DLCP_HW_REQUIRE_STANDBY_LCD_ZZZ=1`, which makes the live pytest wrapper pass
`--no-standby-blank-fallback` to `scripts/hardware_state_test.py`; the closure
artifact must therefore contain literal `Zzz...` standby LCD evidence before
`WAKE`.

## Completion Audit

Audit date: 2026-05-11

Objective: address every implementation bug listed in this ledger by proving a
sim red test, fixing the code, making the sim gate green, and then passing the
listed hardware confirmation before changing status from `green` to `done`.

| Bug | Simulator evidence | Hardware evidence still required |
| --- | --- | --- |
| BUG-DIAG-01 | `test_v171_v32_layer5_chain_diag_static_wait_updates_pb1_and_pb2` passes in the consolidated ledger gate. | Run PB1 and PB2 static-wait hardware gates with `DLCP_HW_LAYER5_AT_DIAG=1` and `DLCP_HW_LAYER5_REQUIRE_PB1_DATA=1` / `DLCP_HW_LAYER5_REQUIRE_PB2_DATA=1`. |
| BUG-DIAG-02 | Diagnostics non-modal loop, LEFT responsiveness, sustained-page responsiveness, and diagnostics IR volume/mute/preset/standby/wake tests pass in sim on PB1 and PB2. | Run `test_live_manual_diagnostics_buttons_remain_responsive` twice with `DLCP_HW_LAYER5_AT_DIAG=1 DLCP_HW_LAYER5_BUTTON_ACTIONS=1 DLCP_HW_EXPECTED_DIAG_PAGE=PB1|PB2`, then run `test_live_diagnostics_page_ir_actions_dispatch_on_real_silicon` twice with `DLCP_HW_LAYER5_AT_DIAG=1 DLCP_HW_LAYER5_IR_ACTIONS=1 DLCP_HW_EXPECTED_DIAG_PAGE=PB1|PB2 DLCP_HW_IR_PROFILE=HYPEX`. |
| BUG-IR-01 | RB5 pulse-train parity passes for stock V1.6b and V1.71 across Hypex profile-1, standard profile, and V1.71 endpoint commands; decoded profile dispatch deltas match stock V1.6b. | POSITIVE OPERATOR REPORT: on 2026-05-10, real IR works on both stock CONTROL V1.6b and CONTROL V1.71. Formal closure still needs either the versioned `ir-legacy-v16b` / `ir-legacy-v171` report artifacts, or the exact shared command/profile set recorded in the ledger; this workspace could not preflight the rig after the report. |
| BUG-IR-02 | Explicit IR standby/wake UI-state tests and diagnostics standby/wake IR sim tests pass. | On hardware, confirm IR `STANDBY` shows `Zzz` and IR `WAKE` returns CONTROL to `Volume` with both MAINs awake; covered by the diagnostics IR hardware gate, ordinary preset/mute timing sweep, and ordinary standby/wake checks. |
| BUG-STDBY-01 | Source-level duplicate-standby guard and V1.71+V3.2 panel STBY/WAKE reconnect test pass. | Run `test_live_manual_front_panel_standby_wake_from_volume` with `DLCP_HW_FRONT_PANEL_STBY_WAKE_CONFIRM=1`, plus `test_live_preset_standby_wake_timing_sweep_passes_for_configured_delays` and `test_live_reconnect_responsiveness_soak_passes_for_configured_iterations` on hardware. |
| BUG-PRESET-01 | EP0 reapply filename-RAM test and release-flash post-state assertion pass. | `test_live_v32_release_identity_and_ab_filename_ram` passed on the connected pair; `front-panel-preset-a` also passed on the connected pair (`1 passed, 3 warnings`). Still run physical `front-panel-preset-b` with `DLCP_HW_FRONT_PANEL_PRESET_CONFIRM=1 DLCP_HW_EXPECTED_PRESET=B`. |
| BUG-PRESET-02 | Rapid preset reversal during apply finishes on latest target in sim. | Run IR rapid-toggle hardware convergence after the real-IR receiver gate passes, plus the physical front-panel A/B gate. If the user can reproduce an in-progress physical rapid toggle, final visible/audible preset must match the last request. |
| BUG-PRESET-03 | IR preset TX-saturation rollback test passes in sim. | No dedicated hardware step unless TX saturation is reproduced; normal preset A/B hardware checks cover the non-saturated path. The current IR `preset-convergence` phase failed before any MAIN preset change, so it is receiver-path evidence, not a preset-state rollback result. |
| BUG-REV-01 | Runtime EEPROM identity and builder revision-marker tests pass; release-flash sim post-state passes. | DONE: `.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --execute --no-pause --phase identity` -> `1 passed` / `PASS [identity]`; both connected MAINs matched canonical V3.2 runtime identity/revision and A/B filename RAM. |
| BUG-SETTINGS-01 | Source guard proves cmd `0x40` no longer calls the factory-default EEPROM flush; sim HID and release-flash tests preserve non-default volume/input/setup-profile exactly. | PARTIAL: real right+left release-flash preserved the stable CONTROL-owned settings (`0xA0` / `0x00` / `0x04`) and identity after flash. Still run a stronger hardware proof after setting non-default volume through CONTROL, plus the ordinary real-IR stress gate to confirm the configured Hypex RC5 profile dispatches. |

Additional live hardware gate added on 2026-05-09:
`tests/hardware/test_live_state_transitions.py::test_live_v32_release_identity_and_ab_filename_ram`.
It is opt-in via `DLCP_HW_RELEASE_IDENTITY_CONFIRM=1`, can be run with one MAIN
connected at a time, and confirms:

- runtime HID identity matches the canonical V3.2 release;
- runtime EEPROM identity/revision matches the canonical V3.2 release;
- active filename RAM and HID cmd `0x03` readback match preset A
  `LX521.4 22MG10F-v5` and preset B `LX521.4 22MG10F-v7` after EP0 A/B/A
  switching.

Additional Diagnostics-page IR hardware gate added on 2026-05-09:
`tests/hardware/test_live_state_transitions.py::test_live_diagnostics_page_ir_actions_dispatch_on_real_silicon`.
It is opt-in via `DLCP_HW_LAYER5_AT_DIAG=1` and
`DLCP_HW_LAYER5_IR_ACTIONS=1`, and the per-page hardware gate additionally
sets `DLCP_HW_EXPECTED_DIAG_PAGE=PB1|PB2` and
`DLCP_HW_IR_PROFILE=HYPEX`.  It starts from the operator-positioned
Diagnostics page, sends real Flipper IR volume, mute, `F1`/`F2` preset,
explicit `STANDBY`, and explicit `WAKE` commands, and asserts MAIN-side state
changes, literal `Zzz...` on the CONTROL LCD after STANDBY, plus CONTROL LCD
return to `Volume` after wake.  Both PB1 and PB2 runs are required for
BUG-DIAG-02 hardware completion.  Standard RC5 profile
evidence belongs in the receiver-sweep and legacy-stress gates because it does
not provide the V1.71-only explicit endpoint commands.

Additional Diagnostics-page physical button hardware gate added on 2026-05-09:
`tests/hardware/test_live_state_transitions.py::test_live_manual_diagnostics_buttons_remain_responsive`.
It is opt-in via `DLCP_HW_LAYER5_AT_DIAG=1` and
`DLCP_HW_LAYER5_BUTTON_ACTIONS=1`, and the per-page hardware gate additionally
sets `DLCP_HW_EXPECTED_DIAG_PAGE=PB1|PB2`.  It starts from the
operator-positioned Diagnostics page, prompts for a physical RIGHT press,
prompts the operator to reposition back to the same page, then prompts for a
physical LEFT press.  Both PB1 and PB2 runs are required for BUG-DIAG-02
hardware completion.

Additional real-IR cross-version stress hardware gate added on 2026-05-09:
`tests/hardware/test_live_state_transitions.py::test_live_ir_legacy_command_stress_from_volume`.
It is opt-in via `DLCP_HW_IR_LEGACY_STRESS=1` and should be run once on
known-good stock V1.6b CONTROL and again on V1.71 CONTROL.  It uses only
commands expected to work on both versions from the current Hypex RC5 profile:
volume up/down, mute toggle, and POWER standby/wake toggle.  The test clamps
  `DLCP_HW_IR_STRESS_REPEATS` to at least one iteration so a closure artifact
  cannot pass without sending real IR commands, records expected CONTROL hex
  identity and payload hashes, and requires each POWER wake to return the
  CONTROL LCD to `Volume` with row 2 matching the original active preset.

Additional real-IR receiver sweep diagnostic added on 2026-05-09:
`tests/hardware/test_live_state_transitions.py::test_live_ir_receiver_profile_sweep_records_any_state_change`.
It is opt-in via `DLCP_HW_IR_RECEIVER_SWEEP=1` and invokes
`scripts/hardware_state_test.py ir-receiver-sweep --require-any-change`.  It
does not use LCD OCR; it sends a configurable Hypex/standard RC5 action list
and records MAIN-visible volume, preset, mute, active, input, and profile
deltas under
`artifacts/probes/hardware_state_test/pytest/ir_receiver_sweep/.../result.json`.
This is diagnostic evidence for the current "no IR command moves anything"
blocker; it does not replace the required V1.6b and V1.71 legacy stress
comparison.

Additional physical front-panel preset hardware gate added on 2026-05-09:
`tests/hardware/test_live_state_transitions.py::test_live_manual_front_panel_preset_selection_updates_mains_and_filename_ram`.
It is opt-in via `DLCP_HW_FRONT_PANEL_PRESET_CONFIRM=1` and
`DLCP_HW_EXPECTED_PRESET=A|B`.  The operator selects A or B from CONTROL's
physical Preset screen before starting the test.  The gate then verifies the
CONTROL LCD active-preset row, both MAIN active-preset bits, and both MAIN
active filename RAM values against the baked V3.2 release captures.

Additional physical front-panel standby/wake hardware gate added on 2026-05-09:
`tests/hardware/test_live_state_transitions.py::test_live_manual_front_panel_standby_wake_from_volume`.
It is opt-in via `DLCP_HW_FRONT_PANEL_STBY_WAKE_CONFIRM=1`.  The test starts
from `Volume`, waits while the operator presses physical `STBY`, confirms
MAIN standby evidence plus literal `Zzz...` on the CONTROL LCD, waits while
the operator presses physical `STBY` again for wake, and then verifies both
MAINs return active/unmuted on the original preset and CONTROL LCD returns to
`Volume`.

## BUG-DIAG-01: Diagnostics Static-Wait Does Not Converge

Observed behavior:

- Real hardware: entering PB1/PB2 Diagnostics and waiting can leave the LCD at
  `PBn` / `n/a`.
- Sim reproduction: after navigating to the diagnostics page and running a
  static wait, `diag_present` remains `0x00` and the LCD remains `n/a`.
- Existing passing tests work around this by repeatedly cycling LEFT/RIGHT to
  force the foreground loop to make progress.

Original test gap:

- Earlier simulator and hardware procedures exercised the LEFT/RIGHT
  convergence workaround instead of the desired static-wait behavior.
- The current simulator gate and hardware runbook now require static wait as
  the pass condition.

Red test target:

- Add a static-wait test near the Layer 5 diagnostics chain tests.
- Navigate to PB1 Diag, run enough simulated time for at least one 1-second
  cadence, and assert PB1 becomes present and LCD is not `n/a`.
- Navigate to PB2 Diag or advance to PB2, run the same bounded cadence, and
  assert PB2 becomes present and LCD is not `n/a`.
- The test must not inject LEFT/RIGHT cycles after entering the target page.

Acceptance:

- Healthy two-MAIN chain reaches `OK` or concrete counters on both pages within
  1 second cadence.
- `n/a` is rendered only when the target PB is actually absent or has timed out
  under a defined absence policy.

Implementation result:

- `v171_diag_loop` no longer calls modal `display_loop_iteration`; it services
  button scan, RX parser, frame-gap guard, and decoded IR dispatch once per
  diagnostics loop pass.
- The cadence send path now reloads `v171_diag_target` from the visible
  per-PB page before every `cmd 0x21` / `cmd 0x22` query, so PB2 cannot sit
  visible while the next cadence polls hidden PB1 first.
- Runtime cmd `0x21` replies are routed through a send-time target snapshot and
  a small timeout, so CONTROL does not overwrite the in-flight target or mix
  PB1/PB2 BF/21..BF/27 cache cells while diagnostics traffic is interleaved.
- `test_v171_v32_layer5_chain_diag_static_wait_updates_pb1_and_pb2` now passes
  without LEFT/RIGHT cycling.
- `test_v171_v32_layer5_diag_visible_page_refreshes_on_next_cadence` now
  forces the stale hidden-target state and proves the visible PB page refreshes
  on the next cadence.

Hardware confirmation:

- From Volume, press RIGHT to PB1 Diag and wait one second. PB1 must not
  remain `n/a`; do not use a longer multi-second settle as the pass condition.
- Move to PB2 Diag and wait one second. PB2 must not remain `n/a`; do not use
  LEFT/RIGHT cycling or a longer multi-second settle as the pass condition.

## BUG-DIAG-02: Diagnostics Page Stalls UI Responsiveness

Observed behavior:

- On PB1/PB2 Diagnostics pages, touch-button responsiveness becomes worse.
- This is likely coupled to the foreground busy-loop / diagnostic polling
  design, but it should be measured as an independent user-visible bug.

Red test target:

- Add a diagnostics responsiveness test near the Layer 5 diagnostics chain
  tests.
- Enter PB1 Diag, allow the diag cadence to start, then inject LEFT, RIGHT, and
  STBY-like actions in separate subcases.
- Assert the display state or standby action changes within the same tick budget
  used for ordinary menu navigation.
- Assert the diagnostic poller does not fill the TX queue indefinitely, starve
  parser work, or require extra user cycling to resume normal UI progress.

Acceptance:

- Diagnostics polling is non-blocking from the user's perspective.
- Normal menu navigation latency is preserved while counters are refreshing.

Implementation result:

- Diagnostics page tests now cover static refresh, LEFT exit responsiveness,
  sustained-page responsiveness, and decoded IR volume/mute/preset/standby/wake
  while PB1 and PB2 pages remain active.

Hardware confirmation:

- On PB1 and PB2 pages, tap LEFT/RIGHT/STBY during refresh. The action must be
  visibly accepted without the current "less responsive" feel.
- While staying on PB1/PB2 pages, send IR volume, mute, preset A/B, standby,
  and wake. Each must dispatch without leaving the page wedged.
- Optional automated physical-button check:
  `DLCP_HW_LAYER5_AT_DIAG=1 DLCP_HW_LAYER5_BUTTON_ACTIONS=1 DLCP_HW_EXPECTED_DIAG_PAGE=PB1 pytest -q tests/hardware/test_live_state_transitions.py::test_live_manual_diagnostics_buttons_remain_responsive --run-hardware -s`,
  then repeat with `DLCP_HW_EXPECTED_DIAG_PAGE=PB2`.
- Optional automated IR check:
  `DLCP_HW_LAYER5_AT_DIAG=1 DLCP_HW_LAYER5_IR_ACTIONS=1 DLCP_HW_EXPECTED_DIAG_PAGE=PB1 DLCP_HW_IR_PROFILE=HYPEX pytest -q tests/hardware/test_live_state_transitions.py::test_live_diagnostics_page_ir_actions_dispatch_on_real_silicon --run-hardware`,
  then repeat with `DLCP_HW_EXPECTED_DIAG_PAGE=PB2`.

## BUG-IR-01: V1.71 IR Real-Receiver Regression

Observed behavior:

- Original expectation: real IR should work on stock V1.6b and V1.71 must pass
  the same shared-command stress.
- Hardware evidence is mixed but now positive overall: earlier V1.71 and
  V1.6b-labelled runs failed to move MAIN-visible state with
  Flipper-generated Hypex and standard RC5 volume commands, but the operator
  later explicitly retested real IR and reported that it works on both stock
  CONTROL V1.6b and CONTROL V1.71.  Treat the earlier failures as session/profile/sender
  artifacts until a versioned runner report proves otherwise.
- Existing V1.71 tests are insufficient because command-matrix tests inject
  decoded IR events, and RC5 pulse tests use ideal synthetic trains rather than
  a comparator against known-good V1.6b behavior.

Red test target:

- Build a shared IR stress harness that can run the same stimulus against
  stock V1.6b and V1.71.
- Use the real decoder path: pin transitions / Timer1 sampling / dispatch, not
  `inject_decoded_ir_event`.
- Cover at least volume up/down, mute, power, preset next/previous, and the
  V1.71 explicit preset/standby endpoints where applicable.
- Include toggle-bit changes, repeat frames, realistic inter-frame gaps, phase
  offsets, bounded jitter, and both receiver polarity hypotheses until a real
  capture pins polarity.
- The required assertion is parity: V1.71 must match V1.6b for shared IR
  commands. V1.71-only commands may add behavior, but cannot regress shared
  decode/dispatch.

Acceptance:

- V1.71 passes the same IR stress suite as V1.6b for all shared profile
  commands.
- Any polarity or timing assumption used by the sim test is documented.

Implementation result:

- `test_v16b_and_v171_rc5_pulse_train_decode_same_command_stress` now drives
  both stock V1.6b and V1.71 through the RB5 RC5 pulse path and passes for
  the current Hypex profile-1 commands, the standard profile commands, and
  V1.71-only endpoints.
- `test_v171_profile_ir_actions_match_stock_v16b_dispatch_behavior` now
  verifies decoded profile-1/profile-2 volume, mute, power, and input/preset
  dispatch state/frame deltas against stock V1.6b.
- `test_v171_ir_decode_uses_hardware_validated_stock_isr_path` pins the
  current firmware shape: V1.71 rev `0x1C` uses the stock-compatible in-ISR
  RC5 decoder path and keeps the failed Timer1 receiver out of the live ISR
  path until that design is proven on real hardware.
- This proves simulator parity for the decoder path; it does not by itself
  close a hardware-only receiver/range/polarity/electrical issue.

Hardware confirmation:

- After reconnecting MAIN USB and Flipper, either capture the exact working
  real-IR command/profile matrix or run the no-OCR receiver sweep:
  `DLCP_HW_IR_RECEIVER_SWEEP=1 pytest -q tests/hardware/test_live_state_transitions.py::test_live_ir_receiver_profile_sweep_records_any_state_change --run-hardware`.
  At least one Hypex or standard RC5 action must change MAIN-visible state.
  If it fails despite the operator's successful real-IR test, debug the
  test sender/profile/session setup before attributing the result to V1.71.
- Baseline/compare gate:
  `DLCP_HW_IR_LEGACY_STRESS=1 pytest -q tests/hardware/test_live_state_transitions.py::test_live_ir_legacy_command_stress_from_volume --run-hardware`
  must pass on stock V1.6b CONTROL and then again on V1.71 CONTROL.
- Re-run the same command classes with the real remote or Flipper capture on
  V1.71 and confirm each command is accepted repeatedly.
- Earlier V1.6b-labelled negative evidence: after the CONTROL LCD showed a
  stock-style Volume screen (`Volume:-96.0dB A` / `Auto Detect`), the baseline
  gate was run with `DLCP_HW_EXPECTED_CONTROL_VERSION=V1.6b` and failed at the
  first volume command: both MAINs stayed at logical volume low `0xA0`.  A
  direct Flipper `VOL_UP` command still emitted `ir tx RC5 10 33` without a
  CLI error.  A standard RC5 profile `Vol+` command (`ir tx RC5 00 10`) also
  left both MAIN volume lows unchanged.  This made that live session look like
  a broader real-IR baseline/profile/sender problem, but it is superseded by
  the later operator report that real IR works on both V1.6b and V1.71.
  Shortened artifact-producing reruns with
  `DLCP_HW_IR_STRESS_REPEATS=1 DLCP_HW_TIMEOUT_S=5` wrote Hypex-profile
  evidence to
  `artifacts/probes/hardware_state_test/pytest/legacy_ir_stress/20260509_220554/result.json`
  and standard-profile evidence to
  `artifacts/probes/hardware_state_test/pytest/legacy_ir_stress/20260509_220802/result.json`,
  both with unchanged `0xA0` final volumes.
- Later operator-reported positive evidence: after the failed artifacts above,
  the operator retested real IR on 2026-05-10 and reported that it works on
  both stock CONTROL V1.6b and CONTROL V1.71.  That supersedes the earlier
  "total receive path failure" suspicion as a hardware-session result, but it
  is not yet a formal close artifact because this workspace could not see the
  MAINs, LCD camera, or Flipper when the post-report `BUG-IR-01` preflight was
  run.  Capture either the versioned runner reports or the exact shared
  command/profile matrix before moving this row to `done`.
- Earlier current-firmware negative evidence: `scripts/run_v171_v32_ledger_hardware_gate.py
  --execute --no-pause --phase preset-convergence` failed on 2026-05-09;
  both MAINs remained preset A after the Flipper F2 request.  This no longer
  proves that IR-dependent hardware phases are globally blocked after the
  later successful operator real-IR test, but it remains an artifact that the
  automated Flipper/profile session can fail.  Direct helper check:
  `scripts/hardware_flipper_ir.py --action F2` emitted `ir tx RC5 10 39`
  without a Flipper CLI error, and both MAINs still reported preset A.  A
  direct `VOL_UP` helper check emitted `ir tx RC5 10 33`; both MAIN logical
  volume low bytes remained `0xA0`.  A repeat `preset-convergence` run after
  adding failure artifact capture again failed the same way; the self-contained
  artifact at
  `artifacts/probes/hardware_state_test/pytest/preset_convergence/20260509_210843/result.json`
  records baseline LCD `Volume` / `Active: A`, Flipper command
  `ir tx RC5 10 39`, and final LEFT/RIGHT MAIN state still on preset A with
  `LX521.4 22MG10F-v5`.

## BUG-IR-02: Explicit IR Standby/Wake Local UI State

Observed behavior:

- Explicit IR standby/wake endpoints could emit `[B0, 0x03, 0x00/0x01]` but
  leave CONTROL's local display state stale.

Red test target:

- Add explicit decoded-IR standby and wake tests that start from `Volume`,
  exercise the V1.71-only endpoint handlers, and assert CONTROL's local
  connected/display state follows the successfully emitted frame.
- The standby endpoint must move the LCD to `Zzz` without waiting for unrelated
  menu traffic.
- The wake endpoint must restore the local connected state and return CONTROL
  through reconnect to `Volume`.
- Add diagnostics-page IR standby/wake coverage so the same endpoint handlers
  work while PB1/PB2 foreground diagnostics are active.

Implementation result:

- `v171_ir_standby_case` clears `control_flags.CONNECTED` after a successful
  standby frame, so the LCD transitions to `Zzz`.
- `v171_ir_wake_case` sets `control_flags.CONNECTED` after a successful wake
  frame, so the UI proceeds through wake/reconnect back to Volume.
- Green tests:
  `test_explicit_ir_standby_updates_control_lcd_state`,
  `test_explicit_ir_wake_returns_control_lcd_to_volume`, and the diagnostics
  IR standby/wake test.

Hardware confirmation:

- From Volume, send IR standby. CONTROL must show `Zzz` and both MAINs must
  enter standby.
- From standby, send IR wake. CONTROL must return to Volume and both MAINs must
  wake.

## BUG-STDBY-01: Duplicate Standby Cancels Pending Shutdown

Observed behavior:

- From the Volume screen, CONTROL can emit duplicate `B0/03/00` standby
  frames during one physical STBY action.
- In V3.2 MAIN, the first frame clears `active_flags.bit3` and sets
  `event_flags.bit2` for `standby_event_dispatch`.
- If the duplicate frame arrives before the dispatcher runs, the handler sees
  the gate already closed and used to clear `event_flags.bit2`.  That cancels
  the pending hardware shutdown: the MAIN looks logically inactive, but
  `diag_s` stays at 0 and the amp-enable latches can remain high.

Original test gap:

- Preset-screen STBY happened to leave enough time for the dispatcher to run,
  so the existing user-visible STBY test passed.
- The Volume-screen panel STBY/WAKE reconnect gate exposed the failure because
  it required `diag_s >= 1` before attempting wake.

Red test target:

- Add a V3.2 MAIN regression that injects two standby frames before
  `standby_event_dispatch` runs and asserts the pending shutdown event remains
  set after the duplicate.
- Assert the first frame closes the logical active gate, but the duplicate
  does not clear the pending hardware-shutdown work item.
- Add a V1.71+V3.2 chain test from the Volume screen where one physical STBY
  action can produce duplicate standby traffic and wake must still bring both
  MAINs and CONTROL back to Volume.

Implementation result:

- `standby_request_handler` now treats duplicate standby with the gate already
  closed as idempotent and preserves any pending `event_flags.bit2` shutdown
  event.
- Green tests:
  `test_v32_duplicate_standby_preserves_pending_shutdown_event`,
  `test_v171_v32_v32_panel_wake_brings_up_main1_via_h2_re_emit`, and the full
  `tests/sim/test_v171_v32_standby_reconnect.py` file.

Hardware confirmation:

- From Volume, press physical STBY once. CONTROL must show `Zzz`, both MAINs
  must enter standby, and wake must return to Volume without `WAITING FOR DLCP`.
- Automated/manual companion:
  `DLCP_HW_FRONT_PANEL_STBY_WAKE_CONFIRM=1 pytest -q tests/hardware/test_live_state_transitions.py::test_live_manual_front_panel_standby_wake_from_volume --run-hardware -s`.
- Run the existing preset-standby/wake timing sweep and reconnect
  responsiveness soak on the real rig.

## BUG-PRESET-01: Release Flash Leaves Active Filename RAM Stale

Observed behavior:

- After `scripts/dlcp_v32_release_flash.py --right`, flash/EEPROM verification
  can pass for preset A and B, but active preset A can still show the B filename
  (`...v7`).
- The user connected USB to one MAIN at a time, so cross-device USB serial
  rediscovery is not the likely cause.

Current suspected mechanism:

- The release flasher finalizes A and B filenames, then restores preset A using
  the EP0 active-preset path.
- The EP0 bit-7 reapply path re-applies DSP state but does not reload filename
  RAM from the selected EEPROM slot.
- The normal serial `cmd 0x20` preset job does call the filename loader.

Original test gap:

- `tests/sim/test_v32_release_flash_sim.py` verifies EEPROM slots and routing,
  but does not assert the post-restore active filename RAM shown to the user.
- It also does not cover the exact one-connected-MAIN operational sequence for
  `--right` followed by `--left`.

Red test target:

- Add a release-flash sim test with a single exposed MAIN and blank serial.
- Do not seed V3.2 identity unless the test explicitly says it is isolating a
  different behavior.
- Run the flasher finalize path.
- Assert:
  - active preset restored to A;
  - EEPROM A filename is `LX521.4 22MG10F-v5`;
  - EEPROM B filename is `LX521.4 22MG10F-v7`;
  - active filename RAM is `LX521.4 22MG10F-v5`;
  - subsequent CONTROL/front-panel A/B switches keep active bits, filename RAM,
    and DSP data aligned.

Acceptance:

- Both left and right release-flash operations finish with the active filename
  matching the restored preset.
- Front-panel A/B switching never displays the wrong filename for the active
  preset.

Implementation result:

- V3.2 EP0 reapply reloads filename RAM from the selected EEPROM slot unless a
  filename write transaction is dirty/in-flight.
- Release-flash sim now asserts restored active A has live filename RAM
  `LX521.4 22MG10F-v5`.

Hardware confirmation:

- Flash right, then left, with USB connected to one MAIN at a time.
- After each flash, select A and B from CONTROL and verify displayed filename:
  A = `...v5`, B = `...v7`.
- Optional automated MAIN-only check:
  `DLCP_HW_RELEASE_IDENTITY_CONFIRM=1 pytest -q tests/hardware/test_live_state_transitions.py::test_live_v32_release_identity_and_ab_filename_ram --run-hardware`.
- Physical front-panel check:
  run `DLCP_HW_FRONT_PANEL_PRESET_CONFIRM=1 DLCP_HW_EXPECTED_PRESET=A pytest -q tests/hardware/test_live_state_transitions.py::test_live_manual_front_panel_preset_selection_updates_mains_and_filename_ram --run-hardware`,
  then repeat with `DLCP_HW_EXPECTED_PRESET=B`.

## BUG-PRESET-02: Preset Apply Does Not Always Finish On Latest Target

Observed behavior:

- Existing protection around filename transactions does not prove that rapid
  A/B target changes during apply converge to the latest target.
- A regression test now lives in
  `tests/sim/test_v171_v32_user_visible_desync_bugs.py`.

Red test target:

- Keep or promote
  `test_rapid_preset_reversal_during_apply_finishes_on_latest_target`.
- The test should drive a target reversal while MAIN is in the apply window and
  assert the final active preset, filename RAM, and DSP state all match the last
  CONTROL target without waiting for a later periodic rebroadcast.

Acceptance:

- MAIN records or rechecks pending target changes during apply.
- The final observable state always matches the latest target requested by
  CONTROL.

Implementation result:

- V3.2 MAIN rechecks `preset_job_target` during apply commit and rearms the
  delayed-apply job when the target changed during the apply window.
- `test_rapid_preset_reversal_during_apply_finishes_on_latest_target` now
  passes without xfail.

Hardware confirmation:

- Rapidly toggle A/B from the front panel during an in-progress switch.
- Final display and audible/user-visible preset must match the last selected
  target.

## BUG-PRESET-03: Preset TX Saturation Rolls Back Local State

Observed behavior:

- IR/menu preset handlers updated local `PRESET_BIT` before calling the
  fallible atomic TX/persist helper.
- If the 3-byte TX reservation failed, no preset frame was emitted and EEPROM
  was not persisted, but CONTROL could still show the new preset locally.

Red test target:

- Add a CONTROL preset-dispatch test that forces the atomic TX reservation path
  to fail before any preset frame is emitted.
- Trigger an IR or preset-menu request for the opposite preset.
- Assert the local `PRESET_BIT`, LCD-visible preset state, and persisted preset
  byte all remain on the previous preset when the helper returns carry set.
- Assert the TX-saturation counter increments so the rollback path is tied to
  the real failure mode rather than a silent no-op.

Implementation result:

- IR preset A/B and preset-menu UP/DOWN now restore the previous `PRESET_BIT`
  when `v171_send_preset_frame_and_persist` returns carry set.
- `test_ir_preset_b_tx_saturation_does_not_change_local_preset_state` now
  passes without xfail and reads the saturation counter at its physical address
  `0x1AD`.

Hardware confirmation:

- No dedicated operator step is required unless TX saturation is reproduced on
  hardware; normal preset A/B hardware checks cover the non-saturated path.

## BUG-REV-01: V3.2 Runtime Revision Does Not Match Release HEX

Observed behavior:

- After flashing V3.2, the flasher can report `revision: 0x30 (EEPROM 2.3)`.
- The release HEX contains a V3.2 EEPROM tuple, but the MAIN app flasher streams
  program memory only, and the firmware boot path does not migrate the runtime
  EEPROM revision byte.

Original test gap:

- Static version-label tests inspect HEX contents.
- Some V3.2 chain helpers seed identity manually, which masks the real runtime
  problem.

Red test target:

- Add a runtime identity test that boots the canonical V3.2 HEX in sim without
  post-boot identity seeding.
- Assert EEPROM identity bytes match the canonical release tuple from the HEX,
  including the revision byte.
- The test should fail today with the old stock tuple/revision.

Acceptance:

- A flashed V3.2 app reports V3.2 and the current release revision after boot.
- Release-flash logs no longer show stale `EEPROM 2.3` identity after flashing.
- Tests that need V3.2 identity do not rely on manual fixture seeding.

Implementation result:

- V3.2 boot EEPROM identity now writes the V3.2 tuple and a builder-managed
  runtime revision literal.
- `scripts/build_v32_release.py` bumps the HEX EEPROM tuple and runtime EEPROM
  revision marker together.

Hardware confirmation:

- Flash V3.2 using `scripts/dlcp_v32_release_flash.py`.
- Confirm the post-flash report shows V3.2 and the current revision byte from
  `firmware/patched/releases/DLCP_Firmware_V3.2.hex`.
- Automated MAIN-only check passed on the connected pair:
  `.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --execute --no-pause --phase identity`
  -> `1 passed` / `PASS [identity]`.

## BUG-SETTINGS-01: Release Flash Resets User Settings

Observed behavior:

- After a V3.2 MAIN release flash, the MAIN could return with logical volume
  `-96 dB` and input reset to analog 1 even though the operator did not change
  those settings.
- This also raised the risk that related EEPROM-backed setup, including the
  IR profile byte, could be reset during the flash ceremony.

Root cause:

- MAIN HID command `0x40` is the app-to-bootloader firmware-update handoff.
- The V3.2 handler had reused the factory-default EEPROM flush path before
  setting the bootloader marker, so entering firmware-update mode rewrote the
  saved user-settings block.
- The bootloader stream itself only writes application flash, not EEPROM; the
  settings reset came from app firmware just before reset into bootloader.

Original test gap:

- Flash-path tests asserted that the simulated bootloader stream completed,
  but they did not seed non-default EEPROM-backed settings before the
  app-to-bootloader transition.
- The simulator backend did not record settings at the `cmd 0x40` handoff, so
  release-flash tests could not prove preservation across the transition.

Red test target:

- Add a source-level guard proving the V3.2 `cmd 0x40` handler does not call
  the factory-default EEPROM flush path.
- Add a HID simulator test that seeds non-default computed/logical volume and
  input selection, sends app `cmd 0x40`, and asserts those EEPROM-backed
  values are unchanged after the mode switch.
- Extend the release-flash sim path to seed non-default settings before flash
  and assert the same values after bootloader verify and app return.

Acceptance:

- Entering bootloader through app `cmd 0x40` changes only the bootloader-entry
  marker required for safe firmware update.
- Volume, input selection, input mirror, and setup/profile bytes are preserved
  exactly across the release-flash ceremony unless the operator explicitly
  changes them.
- The flasher restores captured runtime settings after app return and again
  after preset/channel-map finalization, because CONTROL sync frames can
  transiently clobber input/profile RAM during the ceremony; the firmware
  handoff itself still must not perform a factory reset.

Implementation result:

- V3.2 `cmd 0x40` no longer calls the factory-default EEPROM flush before
  bootloader entry.
- `SimHidBackend._handle_app_to_bootloader` records and preserves the
  user-settings block, including EEPROM/RAM setup-profile byte `0x0E` /
  `0x0B8`, when switching to bootloader mode.
- `dlcp_main_flash.py` snapshots runtime settings before flash, restores them
  through EP0 after the app returns, verifies readback, and restores once more
  after preset/channel-map finalization.
- Green tests:
  `test_v32_cmd40_bootloader_entry_preserves_saved_settings_in_source`,
  `test_sim_hid_cmd40_preserves_user_volume_and_input_settings`, and the
  BUG-SETTINGS-01 exact volume/input/setup-profile assertions in
  `test_v32_release_flash_sim_full_main_post_flash_state`.

Hardware confirmation:

- Before a live V3.2 release flash, record the MAIN logical volume low byte,
  input byte, and setup/profile byte (`ram_0x0B8`) for each target MAIN.
- Flash the MAIN using `scripts/dlcp_v32_release_flash.py`.
- Run:
  `DLCP_HW_RELEASE_SETTINGS_CONFIRM=1 DLCP_HW_EXPECTED_VOLUME_LOW=<pre_flash_low> DLCP_HW_EXPECTED_INPUT=<pre_flash_input> DLCP_HW_EXPECTED_SETUP_PROFILE=<pre_flash_profile> pytest -q -s tests/hardware/test_live_state_transitions.py::test_live_v32_release_flash_preserves_expected_user_settings --run-hardware`.
- Then run the identity gate to confirm runtime identity and A/B filename RAM
  still match the canonical V3.2 release.
- Completed partial hardware run on 2026-05-09:
  right path `DevSrvsID:4298181537` and left path `DevSrvsID:4298194038`
  preserved `logical/computed low=0xA0`, `input/mirror=0x00`, and
  `setup/profile=0x04` through live release-flash, with both preset EEPROM
  verifies OK and post-flash identity gate passing.  A stronger non-default
  volume run remains pending because CONTROL rebroadcasted its stable
  `0xA0` volume about 2 seconds after a MAIN-only EP0 seed to `0xC4`.  The
  current connected pair still passes the settings gate with those stable
  values:
  `DLCP_HW_RELEASE_SETTINGS_CONFIRM=1 DLCP_HW_EXPECTED_VOLUME_LOW=0xA0 DLCP_HW_EXPECTED_INPUT=0x00 DLCP_HW_EXPECTED_SETUP_PROFILE=0x04 pytest -q -s tests/hardware/test_live_state_transitions.py::test_live_v32_release_flash_preserves_expected_user_settings --run-hardware`
  -> `1 passed, 3 warnings`.

## Tracking Rules

- Update this file in the same change that adds a red test, starts a fix, or
  marks a bug green/done.
- Every xfail introduced for this ledger must include the bug ID in its reason.
- A bug cannot move to `green` while its required test is still xfailed.
- A bug cannot move to `done` without the listed hardware confirmation, unless
  the entry is explicitly changed to document why hardware confirmation is no
  longer applicable.
- Release docs may link to this file, but this file remains the source of truth
  for active implementation bugs in the V1.71/V3.2 pair.
