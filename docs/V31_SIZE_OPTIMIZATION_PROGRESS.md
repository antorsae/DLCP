# V3.1 MAIN Size Optimization Progress

Date: 2026-04-11
Status: active
Target source: `src/dlcp_fw/asm/dlcp_main_v31.asm`
Target build: `firmware/patched/releases/DLCP_Firmware_V3.1.hex`

## Baseline Size Snapshot

- Current baseline source: accepted recombined `W05-R01` current-main candidate
- Baseline assembly: clean via `assemble_v30()`
- Baseline collected validation suite: `89` selected tests across the full-file and targeted-node gate listed in `docs/V31_SIZE_OPTIMIZATION_SPEC_and_IMPL.md`
- Baseline measured size:
  - `used_bytes_pre_preset_b=15149`
  - `last_used_pre_preset_b=0x4B8F`
  - `free_bytes_before_0x4C00=112`
- Wave-launch baseline on current `main` before `W05`:
  - `used_bytes_pre_preset_b=15257`
  - `last_used_pre_preset_b=0x4BFB`
  - `free_bytes_before_0x4C00=4`
- Previous accepted campaign baseline (`W02-R01`):
  - `used_bytes_pre_preset_b=15103`
  - `last_used_pre_preset_b=0x4B61`
  - `free_bytes_before_0x4C00=158`
- Net improvement vs pre-`W05` current-`main` baseline:
  - `-108` used bytes before Preset B
  - `+108` free bytes before `0x4C00`
- Net delta vs accepted `W02-R01` baseline:
  - `+46` used bytes before Preset B
  - `-46` free bytes before `0x4C00`
  - post-`W02` feature additions still consume slack, but `W05-R01`
    recovers most of the current-main regression.

## Gate Status

- `2026-04-11`: coordinator collected the exact current V3.1 gate with:
  - `89 tests collected`
  - file mix: 9 full files plus 5 targeted nodes from 4 additional
    files
- `2026-04-11`: `W05-R01` passed the refreshed parallel V3.1 gate with:
  - `86 passed, 2 skipped, 1 xfailed in 493.63s (0:08:13)`
  - skip detail: `tests/sim/test_v31_usb_hid_dispatch.py:221` —
    `cmd 0x06 response not staged in RAM (no USB in gpsim)`
  - expected `xfail`:
    `tests/sim/test_v31_v163b_robustness.py::test_wire_mssp_stop_cascade_full_dsp_recovery`
    — gpsim wire-chain STOP-state model still blocks the final
    post-recovery DSP write in V3.1
- `2026-04-11`: `W05-R01` also passed the local smoke gate with:
  - `DLCP_GPSIM_BIN=/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/scripts/gpsim-xtc ../analysis/.venv_ep0/bin/python -m pytest -q tests/sim/test_v31_happy_path.py`
  - `16 passed in 768.59s (0:12:48)`
- `2026-04-11`: first recombined `W05` child with all eight parents
  (`W05-R01a`) assembled to `used=15127`, `last_used=0x4B79`,
  `free=134`, but failed the reconnect wake gate and was rejected before
  merge.
- Acceptance gate command:

```bash
DLCP_GPSIM_BIN=/path/to/built/scripts/gpsim-xtc \
.venv_ep0/bin/python -m pytest -n 16 -q \
  tests/sim/test_firmware_version_label.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_v31_dsp_boot_equivalence.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v31_review_findings.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_v31_usb_preset_ab.py \
  tests/sim/test_v31_v163b_robustness.py \
  tests/sim/test_main_dsp_deafness_chain.py::test_main_dsp_deafness_chain_ackstat_dirty_readback[main_v31] \
  tests/sim/test_main_dsp_deafness_chain.py::test_main_v31_immune_to_dsp_deafness_chain \
  tests/sim/test_wire_chain_gpsim.py::test_wire_supported_patched_pairs_reach_display[v162b_v31] \
  tests/sim/test_reconnect_wake_gate.py::test_v31_v163b_wire_chain_standby_reconnect_dsp_gate \
  tests/sim/test_wire_chain_gpsim_stock_faults.py::test_wire_extended_mssp_stop_fault_degrades_dsp_command_path[main_v31]
```

## Structural Review Inventory

| Item | Classification | Notes |
| --- | --- | --- |
| app entry block | `high-risk / do not touch` | Must preserve `0x1000` boot entry, ISR dispatch setup, and flash-service jump topology |
| USB descriptors and related tables | `high-risk / do not touch` | External USB identity surface; size work only if descriptor bytes are proven redundant |
| HID dispatch and update-relay logic | `high-risk / do not touch` | Largest externally visible command surface |
| UART, I2C, flash, preset, EEPROM, and recovery helpers | `mixed` | Reviewed function-by-function below |
| post-stock V3.1 wait/recovery helper block | `optimize locally` | Good candidate area for helper sharing and wrapper removal; no new code islands allowed |
| post-stock DSP fault/status helpers | `share/reuse candidate` | Multiple short UART status emitters exist; reuse must beat call overhead |
| post-stock preset filename helpers | `keep (audited 2026-04-11)` | 2-caller helper factoring for the shared `movlw 0x60 / btfsc / movlw 0x83` EE-base selector in `preset_persist_filename` / `preset_load_filename` was evaluated and rejected as wash: +4 B with `call`, break-even with `rcall`. Loop bodies differ by register convention (`ram_0x007/008` vs `ram_0x003/004`). Left as-is. |
| Preset B table at `org 0x4C00` | `high-risk / do not touch` | Fixed anchor, not a patch area |
| erased padding to Preset A | `keep` | Data layout artifact; not executable |
| Preset A table at `org 0x5600` | `high-risk / do not touch` | Fixed anchor |
| EEPROM data block at `org 0xF00000` | `high-risk / do not touch` | Data anchor, externally observed version bytes |

## Function Review Inventory

- `high-risk / do not touch`:
  `hid_command_dispatch`, `fw_update_relay`, `cmd_dispatch_gated`, `main_uart_service_1be6`, `main_i2c_service_2100`, `main_i2c_service_27f0`, `adc_boot_gate`, `flash_write (V3.1: preset B address remap prologue)`, `main_usb_service_2f4e`, `main_isr_dispatch`, `main_flash_service_3ce8`, `flash_erase (V3.1: preset B address remap prologue)`, `i2c_byte_tx (V3.1 enhanced)`, `main_adc_service_4124`, `i2c_tas3108_reg1f_write (V3.1 enhanced)`, `i2c_tas3108_coeff_write (V3.1 enhanced — Fix F: boot-gated PEN)`, `i2c_secondary_dev_write (V3.1 enhanced)`, `i2c_wait_bus_idle (stock — unbounded spin)`, `hard_reset`
- `high-risk / do not touch (pending coverage)` — 2026-04-11:
  `flash_read (V3.1: preset B address remap prologue)` — reclassified
  from `keep` to align with `flash_write` and `flash_erase`. The three
  functions share a near-identical 13-instruction preset-B remap
  prologue (26 B inlined in `flash_read` + 26 B in `flash_write` +
  ~48 B in `flash_erase` with its dual start/end remap). Consolidating
  into a shared `preset_b_remap_r04` helper could save ~36 B but is
  **blocked on the prerequisite gpsim test documented in Open Questions
  And Blocked Tooling below**. Do not land consolidation until that
  test is in place and green on the current baseline.
- `optimize locally`:
  `main_core_service_3188`, `main_i2c_service_464c`, `rx_ring_has_data`, `uart_tx_byte_blocking (V3.1 enhanced)`, `send_status_burst`, `report_cmd29_status`, `factory_reset_status_emit`
- `share/reuse candidate`:
  `send_status_burst`, `main_uart_service_44b2`, `report_cmd29_status`, `factory_reset_status_emit`
- `resolved dead code / removed in W02-R01`:
  `wait_mssp_idle_bounded`, `recover_mssp`
- `keep`:
  `main_core_service_15b0`, `main_core_service_15be`, `nibble_to_hex_ascii`, `main_core_service_1e88`, `main_core_service_2328`, `main_core_service_24ac`, `main_core_service_24c2`, `main_core_service_263e`, `main_core_service_2650`, `main_core_service_265c`, `main_core_service_297e`, `main_core_service_2abc`, `main_core_service_2b8e`, `main_core_service_2b9e`, `main_core_service_2bac`, `main_flash_service_2bb8`, `main_core_service_2ca8`, `main_core_service_2d80`, `main_core_service_301a`, `main_core_service_30cc`, `main_core_service_30d8`, `main_i2c_service_32f8`, `main_core_service_3398`, `main_core_service_3432`, `main_core_service_34c8`, `main_i2c_service_355c`, `main_flash_service_35f0`, `main_flash_service_365c`, `main_core_service_3672`, `main_core_service_3682`, `main_core_service_3710`, `main_flash_service_3796`, `main_flash_service_3810`, `main_i2c_service_381c`, `main_core_service_38a2`, `adaptive_baud_select`, `main_i2c_service_39a6`, `main_usb_service_3a26`, `uart_rx_with_framing`, `hw_standby_shutdown`, `main_core_service_3c82`, `main_core_service_3e0a`, `main_core_service_3ec4`, `main_core_service_3f1e`, `intel_hex_checksum_update`, `main_core_service_3fd0`, `main_core_service_4080`, `main_usb_service_40d6`, `main_core_service_41b6`, `main_usb_service_41fe`, `i2c_secondary_dev_random_read`, `main_core_service_427a`, `flash_write_with_gie_off`, `main_usb_service_42f4`, `main_core_service_432e`, `main_uart_service_43a2`, `tblrd_lookup`, `eeprom_write_blocking`, `main_flash_service_4406`, `main_usb_service_4412`, `main_core_service_4448`, `timer3_blocking_delay`, `main_uart_service_44b2`, `main_core_service_4516`, `uart_config`, `main_core_service_4574`, `main_usb_service_45a2`, `main_core_service_45ce`, `rx_ring_read`, `main_usb_service_4624`, `main_core_service_4672`, `uart_tx_block_from_buffer`, `main_core_service_46aa`, `main_flash_service_46de`, `main_usb_service_4700`, `main_usb_service_4720`, `ram_block_clear`, `main_usb_service_475c`, `main_timer_service_477a`, `standby_event_dispatch`, `mssp_hard_reset`, `periodic_service_loop`, `main_usb_service_4812`, `main_usb_service_4828`, `main_usb_service_483c`, `main_uart_service_4860`, `eeprom_read_byte`, `main_timer_service_48a6`, `main_i2c_service_48e2`, `usb_shutdown`, `main_core_service_48fe`, `main_usb_service_490c`, `main_core_service_4924`, `main_core_service_492e`, `main_uart_service_4938`, `main_core_service_4942`, `main_timer_service_494c`, `main_core_service_4954`, `main_uart_service_495e`, `usb_disconnect_handler`, `main_i2c_service_4966`, `main_core_service_496c`

## Wave Ledger

| Wave | Experiment | Executor | Scope | Hypothesis | Assembles | Used Bytes | Last Used | Free Bytes | Delta | Tests | Result | Merged | Risk | Notes |
| --- | --- | --- | --- | --- | --- | ---: | --- | ---: | ---: | --- | --- | --- | --- | --- |
| W01 | W01-E01 | `coordinator` | apparent `movff X, X` no-op clusters | Removing self-move source noise will shrink emitted code | yes | 15203 | `0x4BC5` | 58 | 0 | not run | reject | no | low | No binary delta. These lines were not a usable size lever in this source build. |
| W01 | W01-E02 | `coordinator` | `main_core_service_3188`, post-stock helper block, `uart_tx_byte_blocking` | Remove empty `main_core_service_496e` stub and replace one-call `recover_uart` wrapper with direct `uart_config` call | yes | 15186 | `0x4BB9` | 70 | -17 | `78 passed, 2 skipped` (parallel, `511.93s`) | accepted baseline | yes | low | Accepted baseline before W02 launched. |
| W02 | W02-E01 | `Kuhn` | `rx_ring_has_data` | Return raw XOR difference instead of normalizing to `0` or `1` | yes | 15145 | `0x4B8B` | 116 | -41 | `16 passed` fast checks + `78 passed, 2 skipped` | parent accepted into `W02-R01` | yes | low | Shared-workspace run. Caller audit showed all four current call sites only gate on zero/nonzero. Parent delta is advisory only. |
| W02 | W02-E02 | `Planck` | bounded wait helper block | Share a common success tail across `wait_trmt_bounded`, `wait_sen_bounded`, `wait_pen_bounded`, and `wait_bf_clear_bounded` while preserving timeout C-flag semantics | yes | 15115 | `0x4B6D` | 146 | -71 | `8 passed` fast checks + `78 passed, 2 skipped` | parent accepted into `W02-R01` | yes | low | Shared-workspace run. Timeout paths still returned directly with carry set by `wait_tick`; only success paths branched to the shared clear-carry return. Parent delta is advisory only. |
| W02 | W02-E03 | `Zeno` | `main_i2c_service_464c` | Collapse duplicated mode nibble extraction into a smaller local pattern | yes | 15131 | `0x4B7D` | 130 | -55 | `7 passed` fast checks + `78 passed, 2 skipped` | parent accepted into `W02-R01` | yes | low | Shared-workspace run. Truth table preserved via a single `SSPCON1` read, one mask, then `xorlw 0x08` / `xorlw 0x0B`. Parent delta is advisory only. |
| W02 | W02-E04 | `Mendel` | UART BF status emitters | Factor shared `BF` frame emission if call overhead still saves bytes | yes | 15186 | `0x4BB9` | 70 | 0 | not run | reject / no-gain | no | low | No size-positive rewrite in this scope without paying it back in call overhead or frame-order risk. |
| W02 | W02-E05 | `Erdos` | `wait_mssp_idle_bounded` | Remove unreferenced helper if it is truly dead in current source/build | yes | 15145 | `0x4B8B` | 116 | -41 | `7 passed` fast checks + `78 passed, 2 skipped` | parent accepted into `W02-R01` | yes | high | Shared-workspace run. Static source search found only the label definition before removal. Parent delta is advisory only. |
| W02 | W02-E06 | `Hooke` | `recover_mssp` | Remove unreferenced MSSP recovery wrapper if it is truly dead in current source/build | yes | 15131 | `0x4B7D` | 130 | -55 | `7 passed` fast checks + `78 passed, 2 skipped` | parent accepted into `W02-R01` | yes | high | Shared-workspace run. Static source search found no direct `call`, `goto`, or `bra` references before removal. Parent delta is advisory only. |
| W02 | W02-E07 | `Dalton` | `main_usb_service_4720`, `main_core_service_496a` | Remove empty return wrapper and its only callsite | yes | 15145 | `0x4B8B` | 116 | -41 | `12 passed` fast checks + `78 passed, 2 skipped` | parent accepted into `W02-R01` | yes | low | Shared-workspace run. Callsite audit found exactly one reference before removal. Parent delta is advisory only. |
| W02 | W02-E08 | `Ptolemy` | `main_usb_service_42f4`, `main_core_service_495a` | Replace single-use wrapper call with direct call to `flow_main_core_service_3188_3194` and delete wrapper | yes | 15145 | `0x4B8B` | 116 | -41 | `35 passed` fast checks + `78 passed, 2 skipped` | parent accepted into `W02-R01` | yes | low | Shared-workspace run. Wrapper had one callsite and only a `goto` body. Parent delta is advisory only. |
| W02 | W02-R01 | `coordinator` | recombination of `W02-E01`, `W02-E02`, `W02-E03`, `W02-E05`, `W02-E06`, `W02-E07`, `W02-E08` on top of `W01-E02` | Keep all proven-compatible W02 parents in the live tree and validate the combined candidate end-to-end | yes | 15103 | `0x4B61` | 158 | -83 | `78 passed, 2 skipped` (parallel, `507.86s`) | accepted baseline | yes | medium | Authoritative coordinator rebuild/gate on the actual current tree. The `spawn_agent` wave unexpectedly shared the workspace, so this recombined row, not the parent rows, is the authoritative size/test record. |
| W03 | W03-E01 | `Bernoulli` | `main_core_service_3188`, `main_core_service_496c` | Remove empty return wrapper and its single remaining callsite if the net size drops | in progress | n/a | n/a | n/a | n/a | not run yet | launched | no | low | Isolated worktree: `artifacts/reanalysis/size_opt_w03/W03-E01` |
| W03 | W03-E02 | `Popper` | `adaptive_baud_select`, `main_uart_service_4938` | Inline the single-call UART init wrapper if the net size drops | in progress | n/a | n/a | n/a | n/a | not run yet | launched | no | low | Isolated worktree: `artifacts/reanalysis/size_opt_w03/W03-E02` |
| W03 | W03-E03 | `Poincare` | `main_usb_service_483c`, `main_core_service_4924` | Inline the single-call USB timer wrapper via direct inner-label call if it assembles cleanly and saves bytes | in progress | n/a | n/a | n/a | n/a | not run yet | launched | no | medium | Isolated worktree: `artifacts/reanalysis/size_opt_w03/W03-E03` |
| W03 | W03-E04 | `Kant` | two `main_uart_service_495e` callsites plus wrapper | Inline the two-callsite UART-enable wrapper and remove it if the net size drops | in progress | n/a | n/a | n/a | n/a | not run yet | launched | no | low | Isolated worktree: `artifacts/reanalysis/size_opt_w03/W03-E04` |
| W03 | W03-E05 | `Locke` | two `usb_disconnect_handler` callsites plus wrapper | Inline the two-callsite `clrwdt` wrapper and remove it if the net size drops | in progress | n/a | n/a | n/a | n/a | not run yet | launched | no | low | Isolated worktree: `artifacts/reanalysis/size_opt_w03/W03-E05` |
| W03 | W03-E06 | `Newton` | single `main_timer_service_494c` callsite plus wrapper | Inline the timer-stop wrapper after `uart_rx_with_framing` if the net size drops | in progress | n/a | n/a | n/a | n/a | not run yet | launched | no | medium | Isolated worktree: `artifacts/reanalysis/size_opt_w03/W03-E06` |
| W03 | W03-E07 | `Kepler` | `i2c_wait_bus_idle` | Tighten the local idle-spin implementation without changing its spin condition truth table | in progress | n/a | n/a | n/a | n/a | not run yet | launched | no | medium | Isolated worktree: `artifacts/reanalysis/size_opt_w03/W03-E07` |
| W03 | W03-E08 | `Parfit` | `adc_boot_gate` callsite plus `main_i2c_service_4966` | Inline the single-call MSSP disable wrapper if the net size drops | in progress | n/a | n/a | n/a | n/a | not run yet | launched | no | high | Isolated worktree: `artifacts/reanalysis/size_opt_w03/W03-E08` |
| W04 | W04-E01 | TBD | `movlw 0x00` → delete before `clrf`, 10 sites | `clrf F` on PIC18 does not read W, so the preceding literal load is dead. Each delete saves 2 B. | not run | n/a | n/a | n/a | -20 est | not run | queued (post-W03) | no | low | 2026-04-11 Codex audit: all 10 sites verified safe. Sites in `dlcp_main_v31.asm`: 475, 550, 1342, 1362, 1881, 2874, 3799, 4713, 7086, 7149. Each callee running after the clrf was verified not to consume W on entry. |
| W04 | W04-E02 | TBD | `movlw 0x00` + `movwf X` → `clrf X`, 11 safe sites + double-clrf fix at 5797 | Same opcode count, removes 2-byte literal load per site. | not run | n/a | n/a | n/a | -22 est | not run | queued (post-W03) | no | low | 2026-04-11 Codex audit: 11 safe sites in `dlcp_main_v31.asm`: 372, 1604, 1634, 1669, 3204, 3506, 3540, 3596, 5121, 5766, 6234. Site 5797 is load-bearing because W=0 is reused by the next `movwf POSTDEC2` at 5799 — fix by pairing both stores into `clrf POSTINC2` / `clrf POSTDEC2`. Do not apply the single-pair rewrite at 5797 alone. |
| W04 | W04-E03 | TBD | Reopen `W01-E01`: remove the `movff ram_0x020..023, ram_0x020..023` self-move cluster at `dlcp_main_v31.asm:2691-2694` | `W01-E01` "no binary delta" result appears to be a measurement artifact. `.lst` shows each self-move emits `C0xx Fxxx` (4 B). Validate via `mem[0x1000..0x4BFF]` content diff per new spec `## Measurement Gotchas`. | not run | n/a | n/a | n/a | -16 est | not run | queued (post-W03) | no | medium | 2026-04-11 Codex audit: cluster is the no-op branch of a conditional copy inside `main_core_service_24c2`; the sibling branch at 2673-2676 copies `ram_0x024..027` → `ram_0x020..023`. No ISR context (no `retfie`), all ACCESS addressing, no gpsim probe references to `0x252E` or the symbol. `assemble_v30()` at `src/dlcp_fw/sim/v30_symbols.py:80-128` does no padding injection — deletion should produce a real delta. |
| W04 | W04-E04 | TBD | Self-move sweep wave 2 — cluster at `dlcp_main_v31.asm:3331-3332` | Extend `W04-E03` methodology to the second cluster | not run | n/a | n/a | n/a | -8 est | not run | queued (post-W03, contingent on E03) | no | medium | Contingent on `W04-E03` landing cleanly with an authoritative content-diff validation. Run in a fresh isolated worktree. |
| W04 | W04-E05 | TBD | Self-move sweep wave 3 — remaining ~14 `movff X, X` instances | Complete the sweep across the source file | not run | n/a | n/a | n/a | -56 est | not run | queued (post-W03, contingent on E03+E04) | no | medium | Contingent on `W04-E03` + `W04-E04`. Full site list is tracked in the Dead Code Candidate List row below. Run each site in its own isolated worktree; do not stack deletes without re-running the gate. |
| W04 | W04-E06 | TBD | Retry `W01-E04` BF-status-frame sharing using `rcall` instead of `call` | `rcall` is 2 B vs `call` 4 B; may flip the break-even that rejected `W01-E04`. Targets: `report_cmd29_status` (0x47FC) and `factory_reset_status_emit` (0x484E). | not run | n/a | n/a | n/a | -4 to -6 est | not run | queued (post-W03) | no | low | Requires the shared helper to be placed within ±1024 words of both call sites for `rcall` to reach. Savings are small; this slot mainly serves as a methodology check for rcall-based shared-helper experiments. |
| W04 | W04-E07 | TBD | `send_status_burst` Variant A — extract `BF <id>` preamble helper, keep inter-frame `main_core_service_492e` calls | Reduce per-frame boilerplate in the 5-frame emitter at `dlcp_main_v31.asm:5616-5656` (baseline 118 B) | not run | n/a | n/a | n/a | -14 to -24 est | not run | queued (post-W03) | no | medium | 2026-04-11 Codex audit: no test asserts the TX byte order of `send_status_burst`; only RX synthetic injections at `src/dlcp_fw/sim/control_gpsim.py:538,557`. `call`-based Variant A saves only 14 B (below campaign 15 B threshold); `rcall`-based Variant A saves 24 B but requires all 5 call sites within ±1024 words of helper. `main_core_service_492e` tail-calls `timer3_blocking_delay` — inter-frame spacing is load-bearing, do not collapse. |
| W04 | W04-E08 | TBD | Confirmation variant of `W04-E01` | Independent subagent re-applies the `W04-E01` edits and re-measures to guard against copy/paste error in the mechanical edit | not run | n/a | n/a | n/a | -20 est (matches E01) | not run | queued (post-W03) | no | low | Per spec `## Parallelism Rule` line 373-375: when fewer than 8 fresh ideas remain, fill slots with confirmation variants rather than dropping to serial. This slot validates that `W04-E01` produces the same measured delta in two independent runs. |
| W04 | W04-R01 | `coordinator` | Recombine `W04-E01` + `W04-E02` + `W04-E06` + `W04-E07` on top of the post-`W03` baseline | Merge disjoint-scope low-risk wins after parent experiments land cleanly. Holds back `W04-E03..E05` for a separate recombination round after content-diff validation of self-move removal. | pending | n/a | n/a | n/a | -50 to -72 est | pending | pending | pending | low | Standard recombination per spec `## Experiment Recombination Rule`. Parent IDs captured in `## Recombination Lineage` below. `E03..E05` held back and recombined separately into `W04-R02` (next pass) once their content-diff validation is authoritative. |
| W05 | W05-E01 | `Darwin` | audited dead `movlw 0x00` deletes before `clrf` at 10 sites | Remove W-independent zero literal loads | advisory only | n/a | n/a | n/a | -20 est | worker test run invalid before `DLCP_GPSIM_BIN` fix | parent kept only via coordinator recombination | yes | low | Worker isolation failed; authoritative evidence comes from `W05-R01a` / `W05-R01`, not the worker artifact. |
| W05 | W05-E02 | `Zeno` | audited `movlw 0x00` / `movwf` collapses to `clrf` at 11 sites plus paired zero-store rewrite | Save 2 B per site without behavior change | advisory only | n/a | n/a | n/a | -22 est | caused `W05-R01a` reconnect gate regression | reject | no | medium | Rejected after coordinator proved that converting `movwf` to `clrf` perturbs STATUS and breaks `test_v31_v163b_wire_chain_standby_reconnect_dsp_gate`. |
| W05 | W05-E03 | `Harvey` | remove self-move cluster at `dlcp_main_v31.asm:2691-2694` | Delete 4 emitted no-op `movff X, X` instructions | advisory only | n/a | n/a | n/a | -16 est | worker artifact contaminated | parent kept only via coordinator recombination | yes | medium | Accepted through `W05-R01`; standalone worker metrics were non-authoritative. |
| W05 | W05-E04 | `Mencius` | remove self-move cluster at `dlcp_main_v31.asm:3331-3334` | Delete 4 emitted no-op `movff X, X` instructions | advisory only | n/a | n/a | n/a | -16 est | worker artifact contaminated | parent kept only via coordinator recombination | yes | medium | Accepted through `W05-R01`; standalone worker metrics were non-authoritative. |
| W05 | W05-E05 | `Copernicus` | remove self-move cluster at `dlcp_main_v31.asm:4151-4154` | Delete 4 emitted no-op `movff X, X` instructions | advisory only | n/a | n/a | n/a | -16 est | worker artifact contaminated | parent kept only via coordinator recombination | yes | medium | Accepted through `W05-R01`; standalone worker metrics were non-authoritative. |
| W05 | W05-E06 | `Dewey` | remove self-move cluster at `dlcp_main_v31.asm:4264-4267` | Delete 4 emitted no-op `movff X, X` instructions | advisory only | n/a | n/a | n/a | -16 est | worker artifact contaminated | parent kept only via coordinator recombination | yes | medium | Accepted through `W05-R01`; standalone worker metrics were non-authoritative. |
| W05 | W05-E07 | `Confucius` | remove self-move cluster at `dlcp_main_v31.asm:4581-4584` | Delete 4 emitted no-op `movff X, X` instructions | advisory only | n/a | n/a | n/a | -16 est | worker artifact contaminated | parent kept only via coordinator recombination | yes | medium | Accepted through `W05-R01`; standalone worker metrics were non-authoritative. |
| W05 | W05-E08 | `Peirce` | remove self-move cluster at `dlcp_main_v31.asm:6628-6629` | Delete 2 emitted no-op `movff X, X` instructions | advisory only | n/a | n/a | n/a | -8 est | worker artifact contaminated | parent kept only via coordinator recombination | yes | medium | Accepted through `W05-R01`; standalone worker metrics were non-authoritative. |
| W05 | W05-R01a | `coordinator` | recombination of `W05-E01` through `W05-E08` on current `main` | Keep the full low-risk wave if the combined child passes | yes | 15127 | `0x4B79` | 134 | -130 | `16 passed` smoke + full gate `1 failed` (`test_v31_v163b_wire_chain_standby_reconnect_dsp_gate`) | reject / regression | no | medium | Authoritative coordinator rebuild after freezing worker contamination. This child proved the `W05-E02` flag-changing rewrite was not safe. |
| W05 | W05-R01 | `coordinator` | recombination of `W05-E01`, `W05-E03`, `W05-E04`, `W05-E05`, `W05-E06`, `W05-E07`, `W05-E08` on current `main` | Keep the dead literal deletes and self-move removals while backing out the regressing STATUS-sensitive zeroing rewrite | yes | 15149 | `0x4B8F` | 112 | -108 | `16 passed` smoke (`768.59s`); reconnect node `1 passed` (`82.96s`); full gate `86 passed, 2 skipped, 1 xfailed` (`493.63s`) | accepted baseline | yes | medium | Authoritative accepted baseline for current `main`. |
| W06 | W06-E01 | TBD | `call` to `rcall` sweep (Part 1) | Replace `call` with `rcall` where target is definitively within ±1024 words | not run | n/a | n/a | n/a | -122 est | not run | queued | no | low | First half of 122 statically verified sites. |
| W06 | W06-E02 | TBD | `call` to `rcall` sweep (Part 2) | Replace `call` with `rcall` where target is definitively within ±1024 words | not run | n/a | n/a | n/a | -122 est | not run | queued | no | low | Second half of 122 statically verified sites. |
| W06 | W06-E03 | TBD | Tail-call optimization | Replace `call` + `return 0` with `bra` or `goto` based on target distance | not run | n/a | n/a | n/a | -40 est | not run | queued | no | low | 11 sites identified. |
| W06 | W06-E04 | TBD | Redundant `iorlw 0x00` removal | Remove `iorlw 0x00` after `rx_ring_has_data` since it returns raw XOR difference | not run | n/a | n/a | n/a | -8 est | not run | queued | no | low | 4 sites identified in `main_uart_service_1be6`. |
| W06 | W06-E05 | TBD | `send_status_burst` preamble helper | Extract `movlw <ID> / call uart_tx_byte_blocking` preamble | not run | n/a | n/a | n/a | -28 est | not run | queued | no | medium | 5 sites in `send_status_burst`, 2 in other emitters. |
| W06 | W06-E06 | TBD | `movlw 0x00` + `movwf` → `clrf` (Safe Site 1) | Line 372: safely convert to `clrf` as `Z` flag is immediately clobbered by `xorwf` | not run | n/a | n/a | n/a | -2 est | not run | queued | no | low | Z flag equivalence verified statically. |
| W06 | W06-E07 | TBD | `movlw 0x00` + `movwf` → `clrf` (Safe Sites 2 & 3) | Lines 5738 and 6206: safely convert to `clrf` as `Z` flag is immediately clobbered by `swapf` | not run | n/a | n/a | n/a | -4 est | not run | queued | no | low | Z flag equivalence verified statically. |
| W06 | W06-E08 | TBD | Confirmation variant of `W06-E05` | Independent subagent re-applies `W06-E05` edits to guard against copy/paste error | not run | n/a | n/a | n/a | -28 est | not run | queued | no | low | Fills parallel wave slot per spec rule. |

## Recombination Lineage

- `W02-R01` parents:
  - accepted baseline `W01-E02`
  - successful W02 parents `W02-E01`, `W02-E02`, `W02-E03`, `W02-E05`, `W02-E06`, `W02-E07`, `W02-E08`
- `W02-E04` was rejected for no size gain.
- The W02 subagents unexpectedly shared the live workspace, so parent byte counts above are advisory snapshots only.
- `W02-R01` is the accepted recombined baseline for the next wave.
- `W05-R01a` parents:
  - current-main launch baseline
  - `W05-E01`, `W05-E02`, `W05-E03`, `W05-E04`, `W05-E05`, `W05-E06`, `W05-E07`, `W05-E08`
  - rejected because `W05-E02` changed STATUS semantics and broke the reconnect wake gate
- `W05-R01` parents:
  - current-main launch baseline
  - `W05-E01`, `W05-E03`, `W05-E04`, `W05-E05`, `W05-E06`, `W05-E07`, `W05-E08`
  - accepted after coordinator-only rebuild and full-gate validation
- `W05` repeated the W02 isolation failure: several workers mutated the
  coordinator checkout instead of staying inside their assigned
  worktrees. Parent rows are therefore advisory only; `W05-R01a` and
  `W05-R01` are the authoritative records.
- `W04-R01` planned parents (pending `W03` closure and `W04` experiment results):
  - post-`W03` baseline (expected `W03-R01` if `W03` produces a successful recombination)
  - `W04-E01` encoding subs — `movlw 0x00` removal before `clrf`
  - `W04-E02` encoding subs — `movlw 0x00 / movwf` → `clrf`
  - `W04-E06` rcall-based BF status frame sharing (if positive delta)
  - `W04-E07` `send_status_burst` Variant A helper (if positive delta)
- `W04-R02` (planned, contingent on `W04-E03..E05`): recombine the self-move removal sweep parents after content-diff validation lands, stacked on top of `W04-R01`.

## Accepted Size Reductions

- `W01-E02`: removed the empty `main_core_service_496e` stub path and one-call `recover_uart` wrapper, saving `17` bytes before Preset B.
- `W02-R01` accepted actions:
  - `rx_ring_has_data`: replaced 0/1 normalization with direct zero/nonzero XOR return
  - bounded wait helpers: shared a common success tail across four helpers
  - `main_i2c_service_464c`: collapsed duplicated `SSPCON1 & 0x0F` extraction/compare logic
  - `wait_mssp_idle_bounded`: removed after static unreferenced proof and full-gate validation
  - `recover_mssp`: removed after static unreferenced proof and full-gate validation
  - `main_core_service_496a`: removed empty wrapper and its only callsite
  - `main_core_service_495a`: removed single-use `goto` wrapper via direct call to `flow_main_core_service_3188_3194`
- `W05-R01` accepted actions:
  - removed 10 dead `movlw 0x00` instructions that immediately preceded `clrf`
  - removed 6 self-move clusters totaling 22 emitted `movff X, X` instructions
  - explicitly rejected the STATUS-mutating `movwf` → `clrf` rewrite family (`W05-E02`)
- Current accepted baseline:
  - `used_bytes_pre_preset_b=15149`
  - `last_used_pre_preset_b=0x4B8F`
  - `free_bytes_before_0x4C00=112`
- Authoritative savings:
  - `-108` bytes vs pre-`W05` current-main baseline
  - `+108` free bytes before `0x4C00` vs pre-`W05` current-main baseline

## Cumulative Action Log

- 2026-03-29: recorded baseline metrics from current V3.1 source (`15203` bytes used before `0x4C00`, `58` bytes free)
- 2026-03-29: rejected `W01-E01`; apparent self-move no-ops do not change emitted size in this source build
- 2026-03-29: created `W01-E02`; wrapper/stub removal candidate improves slack before Preset B from `58` to `70` bytes
- 2026-03-30: verified the expanded 80-node parallel V3.1 gate returns cleanly on `W01-E02` with `78 passed, 2 skipped in 511.93s`
- 2026-03-30: accepted `W01-E02` as the new baseline for the next optimization wave
- 2026-03-30: launched W02 as an 8-subagent wave from the `W01-E02` baseline
- 2026-03-30: discovered that W02 subagents shared the live workspace instead of staying isolated, so parent experiment deltas became non-authoritative snapshots
- 2026-03-30: retained the successful W02 parents in the live tree and treated the result as recombined candidate `W02-R01`
- 2026-03-30: coordinator rebuilt `W02-R01` and measured `15103` bytes used before `0x4C00`, `last_used=0x4B61`, `free=158`
- 2026-03-30: coordinator reran the expanded 80-node parallel V3.1 gate on `W02-R01` and got `78 passed, 2 skipped in 507.86s`
- 2026-03-30: accepted `W02-R01` as the new baseline for the next optimization wave
- 2026-03-30: created eight isolated W03 git worktrees under `artifacts/reanalysis/size_opt_w03/` and launched `W03-E01..W03-E08` against the `W02-R01` baseline
- 2026-04-11: measured current working tree state against the `W02-R01` accepted baseline: `last_used_pre_preset_b=0x4B83`, `free_bytes_before_0x4C00=124`. Delta `+34` used bytes (free slack dropped from 158 → 124) is attributed to post-`W02` feature additions landing outside the campaign: the restored cmd 0x07 HID upload reseed guard (`dlcp_main_v31.asm:469-477`) and the delayed preset switch helper cluster (`dlcp_main_v31.asm:8097-8153`). `W04` experiments must measure against the current tree, not the frozen `W02-R01` numbers.
- 2026-04-11: Codex-audited five size-optimization candidates — encoding substitutions, `movff X, X` self-moves, preset EE-base helper factoring, shared preset-B remap helper, `send_status_burst` Variant A. The preset EE-base helper refactor was rejected as a wash (break-even at best with `rcall`, +4 B with `call`, no third caller). The shared remap helper refactor was deferred as `high-risk / pending coverage` — potential savings ~36 B but blocked on a new gpsim test for physical preset-B flash-write validation. The remaining three candidates were scheduled as `W04-E01`, `W04-E02`, `W04-E06`, `W04-E07`, plus a confirmation variant at `W04-E08`.
- 2026-04-11: external review of the `W01-E01` rejection found its "no binary delta" result inconsistent with `.lst` evidence — each `movff X, X` self-move emits 4 bytes of object code, and `assemble_v30()` does no padding injection. Reopened self-move removal as `W04-E03..E05` with mandatory content-diff validation per the new `## Measurement Gotchas` section in the spec. First target: the cluster at `dlcp_main_v31.asm:2691-2694` inside `main_core_service_24c2`, which is the no-op branch of a conditional copy paired with a sibling branch at 2673-2676.
- 2026-04-11: logged the shared preset-B remap helper as a blocked optimization under `## Open Questions And Blocked Tooling`, with a prerequisite gpsim regression test to drive USB HID `cmd 0x07` + 8 data chunks with `active_flags.2 = 1` and verify `flash[0x4C00..0x4CBF]` content. Current preset-B write coverage is pure-Python via `MainUnitModel.upload_hfd_table` at `src/dlcp_fw/sim/main_model.py:183,191` and does not exercise the assembly remap prologue at all. This is a standing V3.1 coverage gap independent of the optimization campaign.
- 2026-04-11: queued `W04` wave of 8 experiments (`W04-E01..E08`) against the post-`W03` baseline. Wave will launch after `W03-E01..E08` complete and any successful parents recombine into `W03-R01` (or equivalent). Realistic combined target for `W04-R01`: `-50` to `-72` bytes (low-risk floor). If `W04-E03..E05` self-move sweep lands cleanly, an additional `W04-R02` recombination is planned for another `-80` bytes.

- 2026-04-11: measured the actual current-`main` launch baseline for `W05` at `used=15257`, `last_used=0x4BFB`, `free=4`; this superseded the stale `W04` planning numbers.
- 2026-04-11: verified that the exact current V3.1 gate now collects `89` selected tests, not `80`.
- 2026-04-11: `W05` again exposed worker-isolation failure — several workers mutated the coordinator checkout despite explicit worktree ownership. Coordinator rows, not worker rows, are authoritative.
- 2026-04-11: fixed gpsim test execution in auxiliary worktrees by pinning `DLCP_GPSIM_BIN` to a built repo-local `scripts/gpsim-xtc` wrapper. The Homebrew `gpsim` fallback prints the banner but never emits the `**gpsim>` prompt expected by the harness.
- 2026-04-11: built first recombined `W05` child (`W05-R01a`) with all eight parents, measured `used=15127`, `last_used=0x4B79`, `free=134`, and ran the exact full gate. Result: `1 failed, 85 passed, 2 skipped, 1 xfailed`; failing node was `test_v31_v163b_wire_chain_standby_reconnect_dsp_gate`.
- 2026-04-11: isolated the `W05-R01a` regression to `W05-E02`; reverting only the `movwf` → `clrf` rewrite family restored the reconnect wake gate (`1 passed in 82.96s`).
- 2026-04-11: built accepted `W05-R01` with `W05-E01` plus the six self-move clusters, measured `used=15149`, `last_used=0x4B8F`, `free=112`, passed smoke (`16 passed in 768.59s`), and passed the refreshed full gate (`86 passed, 2 skipped, 1 xfailed in 493.63s`).

## Dead Code Candidate List

| Label / Range | Why It Looks Dead | Static Evidence | Dynamic Evidence | Tests To Cover Removal | Risk | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| `wait_mssp_idle_bounded` | Post-stock helper had no current source call sites | `rg` over `src/dlcp_fw/asm/dlcp_main_v31.asm` found no `call`, `goto`, or `bra` references before deletion | `W02-R01` full gate passed after deletion | full V3.1 gate plus I2C recovery and robustness files | high | removed in `W02-R01` |
| `recover_mssp` | Post-stock helper had no current source call sites | `rg` over `src/dlcp_fw/asm/dlcp_main_v31.asm` found no `call`, `goto`, or `bra` references before deletion | `W02-R01` full gate passed after deletion | full V3.1 gate plus robustness files | high | removed in `W02-R01` |
| `movff X, X` self-move cluster — 22 instances across `dlcp_main_v31.asm` | V2.3-stock fossils carried verbatim into the V3.1 source rewrite. Each `movff X, X` is functionally a no-op but the assembler emits a 4-byte `C0xx Fxxx` instruction. Listing-level confirmation: `firmware/patched/releases/DLCP_Firmware_V3.1.lst:3480` shows `00252E C020 F020` for the first site. | 2026-04-11 Codex review of cluster at 2691-2694: no `retfie` context, all ACCESS addressing, the cluster is the no-op branch of a conditional copy in `main_core_service_24c2` with sibling branch at 2673-2676 actually copying `ram_0x024..027` → `ram_0x020..023`. Same static pattern held for the additional clusters accepted in `W05-R01`. | `W05-R01` removed all 22 self-moves and passed the refreshed full V3.1 gate (`86 passed, 2 skipped, 1 xfailed`). | full V3.1 89-node gate | medium | removed in `W05-R01` |

## Open Questions And Blocked Tooling

- **Blocked optimization — shared preset-B remap helper for `flash_read` / `flash_write` / `flash_erase`.** All three functions contain a near-identical 13-instruction prologue that tests `active_flags.2`, range-checks `ram_0x004`, and subtracts `0x0A` from `ram_0x004` in place. `flash_erase` duplicates the prologue again for the end address (`ram_0x008`). Inlined total: ~100 B. A shared `preset_b_remap_r04` helper called via `rcall` from four sites (`flash_read`, `flash_write`, `flash_erase` start, `flash_erase` end) could save ~36 B; a parametric variant that also handles the end-address case could save ~44 B. Stack depth is not a concern — Codex static call-graph analysis shows max nesting to these functions is ≤20, well below the 31-entry PIC18F2455 hardware stack.
  - **Prerequisite blocker**: there is currently NO gpsim regression test that drives a real USB HID `cmd 0x07` + 8 data-chunk upload sequence with `active_flags.2 = 1` and verifies the written bytes land at `flash[0x4C00..0x4CBF]`. All existing V3.1 preset-B write coverage is pure Python via `MainUnitModel.upload_hfd_table` at `src/dlcp_fw/sim/main_model.py:183,191`, which does not run the V3.1 assembly remap prologue at all.
  - **Required test sketch** (from 2026-04-11 Codex review, patterns borrowed from `tests/sim/test_v31_combined_dsp_table_apply.py:288-395`): build seeded sim hex via `build_seeded_main_sim_hex`, apply overlays, write AN0 bootstrap + I2C regfile STCs, break at parser idle, set `active_flags.2 = 1`, inject 8 HID `cmd 0x07` chunks via `reg(0xFE8)` / `reg(0x11B)` / `reg(0x11C..131)` writes, run until hid_dispatch returns 8 times, then either (a) use gpsim's program-memory read command if available, or (b) call `flash_read` with `active_flags.2 = 0` and a payload that targets `0x4C00` to read the remapped bytes back into RAM, then probe RAM with `reg()` commands. Assert the buffer content equals the injected payload.
  - **Action**: the required test is a standing V3.1 coverage gap independent of this optimization. Write the test as a separate PR, verify it passes on the current post-`W03` baseline, then unblock `preset_b_remap_r04` helper consolidation as a future wave candidate (e.g. `W05-E0x`). Until that test exists and is green, leave `flash_read` / `flash_write` / `flash_erase` alone.
- Process note: W02 showed that `spawn_agent` workers can mutate the live workspace unless isolation is enforced manually. Future waves must use per-experiment isolated worktrees under `artifacts/reanalysis/...` rather than relying on implicit fork isolation.
- Process note (2026-04-11): W05 showed that even explicit worker-owned worktrees can still contaminate the coordinator checkout. Freeze workers as soon as contamination is detected and treat only coordinator remeasurement/retest as authoritative.
- Process note (2026-04-11): `W01-E01` rejection surfaced a measurement-methodology gap. Any experiment result claiming "no binary delta" must capture `used_bytes_pre_preset_b`, `last_used_pre_preset_b`, and `free_bytes_before_0x4C00` metrics AND a `mem[0x1000..0x4BFF]` content diff — not just file-size-on-disk. See new `## Measurement Gotchas` section in `docs/V31_SIZE_OPTIMIZATION_SPEC_and_IMPL.md`.
- Process note (2026-04-11): flag-setting equivalence matters. `movlw 0x00` / `movwf F` is not semantically interchangeable with `clrf F` when downstream code can observe STATUS. `W05-E02` is the proof case; do not retry that family without explicit flag audits per site.
- Next-wave priorities:
  - refresh the stale `W03` / `W04` rows against current `main` and discard any plan that assumed the pre-`W05` layout
  - prefer fresh low-risk locals first: wrapper removal audits near the tail of the stock block, localized USB helper consolidation, and additional I2C helper tightening that does not create new fixed-address code
  - revisit zero-materialization only with explicit STATUS-proofed rewrites; do not retry blanket `movwf` → `clrf`
  - author the blocked-optimization prerequisite gpsim test for physical preset-B flash-write validation so a future wave can safely revisit shared preset-B remap helpers if more slack is needed
  - execute the newly queued `W06` wave containing the `call`-to-`rcall` conversions, tail-call optimizations, and safe flag-audited zero-materialization cleanups.
