# V3.1 MAIN Size Optimization Progress

Date: 2026-03-30
Status: active
Target source: `src/dlcp_fw/asm/dlcp_main_v31.asm`
Target build: `firmware/patched/releases/DLCP_Firmware_V3.1.hex`

## Baseline Size Snapshot

- Current baseline source: accepted recombined `W02-R01` working-tree candidate
- Baseline assembly: clean via `assemble_v30()`
- Baseline collected validation suite: `80` selected tests across the full-file and targeted-node gate listed in `docs/V31_SIZE_OPTIMIZATION_SPEC_and_IMPL.md`
- Baseline measured size:
  - `used_bytes_pre_preset_b=15103`
  - `last_used_pre_preset_b=0x4B61`
  - `free_bytes_before_0x4C00=158`
- Previous accepted baseline:
  - `used_bytes_pre_preset_b=15186`
  - `last_used_pre_preset_b=0x4BB9`
  - `free_bytes_before_0x4C00=70`
- Net improvement vs accepted `W01-E02` baseline:
  - `-83` used bytes before Preset B
  - `+88` free bytes before `0x4C00`
- Net improvement vs original pre-W01 source:
  - `-100` used bytes before Preset B
  - `+100` free bytes before `0x4C00`

## Gate Status

- `2026-03-30`: coordinator reran the expanded parallel V3.1 gate on the accepted recombined candidate `W02-R01` with:
  - `78 passed, 2 skipped in 507.86s (0:08:27)`
  - skip detail: `tests/sim/test_v31_usb_hid_dispatch.py:221` —
    `cmd 0x06 response not staged in RAM (no USB in gpsim)`
- `2026-03-30`: earlier accepted baseline `W01-E02` also passed the same gate with:
  - `78 passed, 2 skipped in 511.93s (0:08:31)`
- Acceptance gate command:

```bash
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
| post-stock preset filename helpers | `optimize locally` | Candidate area for loop/body tightening if net bytes improve |
| Preset B table at `org 0x4C00` | `high-risk / do not touch` | Fixed anchor, not a patch area |
| erased padding to Preset A | `keep` | Data layout artifact; not executable |
| Preset A table at `org 0x5600` | `high-risk / do not touch` | Fixed anchor |
| EEPROM data block at `org 0xF00000` | `high-risk / do not touch` | Data anchor, externally observed version bytes |

## Function Review Inventory

- `high-risk / do not touch`:
  `hid_command_dispatch`, `fw_update_relay`, `cmd_dispatch_gated`, `main_uart_service_1be6`, `main_i2c_service_2100`, `main_i2c_service_27f0`, `adc_boot_gate`, `flash_write (V3.1: preset B address remap prologue)`, `main_usb_service_2f4e`, `main_isr_dispatch`, `main_flash_service_3ce8`, `flash_erase (V3.1: preset B address remap prologue)`, `i2c_byte_tx (V3.1 enhanced)`, `main_adc_service_4124`, `i2c_tas3108_reg1f_write (V3.1 enhanced)`, `i2c_tas3108_coeff_write (V3.1 enhanced — Fix F: boot-gated PEN)`, `i2c_secondary_dev_write (V3.1 enhanced)`, `i2c_wait_bus_idle (stock — unbounded spin)`, `hard_reset`
- `optimize locally`:
  `main_core_service_3188`, `main_i2c_service_464c`, `rx_ring_has_data`, `uart_tx_byte_blocking (V3.1 enhanced)`, `send_status_burst`, `report_cmd29_status`, `factory_reset_status_emit`
- `share/reuse candidate`:
  `send_status_burst`, `main_uart_service_44b2`, `report_cmd29_status`, `factory_reset_status_emit`
- `resolved dead code / removed in W02-R01`:
  `wait_mssp_idle_bounded`, `recover_mssp`
- `keep`:
  `main_core_service_15b0`, `main_core_service_15be`, `nibble_to_hex_ascii`, `main_core_service_1e88`, `main_core_service_2328`, `main_core_service_24ac`, `main_core_service_24c2`, `main_core_service_263e`, `main_core_service_2650`, `main_core_service_265c`, `main_core_service_297e`, `main_core_service_2abc`, `main_core_service_2b8e`, `main_core_service_2b9e`, `main_core_service_2bac`, `main_flash_service_2bb8`, `main_core_service_2ca8`, `main_core_service_2d80`, `main_core_service_301a`, `main_core_service_30cc`, `main_core_service_30d8`, `main_i2c_service_32f8`, `main_core_service_3398`, `main_core_service_3432`, `main_core_service_34c8`, `main_i2c_service_355c`, `main_flash_service_35f0`, `main_flash_service_365c`, `main_core_service_3672`, `main_core_service_3682`, `main_core_service_3710`, `main_flash_service_3796`, `main_flash_service_3810`, `main_i2c_service_381c`, `main_core_service_38a2`, `adaptive_baud_select`, `main_i2c_service_39a6`, `main_usb_service_3a26`, `uart_rx_with_framing`, `hw_standby_shutdown`, `main_core_service_3c82`, `main_core_service_3e0a`, `main_core_service_3ec4`, `main_core_service_3f1e`, `intel_hex_checksum_update`, `main_core_service_3fd0`, `flash_read (V3.1: preset B address remap prologue)`, `main_core_service_4080`, `main_usb_service_40d6`, `main_core_service_41b6`, `main_usb_service_41fe`, `i2c_secondary_dev_random_read`, `main_core_service_427a`, `flash_write_with_gie_off`, `main_usb_service_42f4`, `main_core_service_432e`, `main_uart_service_43a2`, `tblrd_lookup`, `eeprom_write_blocking`, `main_flash_service_4406`, `main_usb_service_4412`, `main_core_service_4448`, `timer3_blocking_delay`, `main_uart_service_44b2`, `main_core_service_4516`, `uart_config`, `main_core_service_4574`, `main_usb_service_45a2`, `main_core_service_45ce`, `rx_ring_read`, `main_usb_service_4624`, `main_core_service_4672`, `uart_tx_block_from_buffer`, `main_core_service_46aa`, `main_flash_service_46de`, `main_usb_service_4700`, `main_usb_service_4720`, `ram_block_clear`, `main_usb_service_475c`, `main_timer_service_477a`, `standby_event_dispatch`, `mssp_hard_reset`, `periodic_service_loop`, `main_usb_service_4812`, `main_usb_service_4828`, `main_usb_service_483c`, `main_uart_service_4860`, `eeprom_read_byte`, `main_timer_service_48a6`, `main_i2c_service_48e2`, `usb_shutdown`, `main_core_service_48fe`, `main_usb_service_490c`, `main_core_service_4924`, `main_core_service_492e`, `main_uart_service_4938`, `main_core_service_4942`, `main_timer_service_494c`, `main_core_service_4954`, `main_uart_service_495e`, `usb_disconnect_handler`, `main_i2c_service_4966`, `main_core_service_496c`

## Wave Ledger

| Wave | Experiment | Subagent | Scope | Hypothesis | Assembles | Used Bytes | Last Used | Free Bytes | Delta | Tests | Result | Merged | Risk | Notes |
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

## Recombination Lineage

- `W02-R01` parents:
  - accepted baseline `W01-E02`
  - successful W02 parents `W02-E01`, `W02-E02`, `W02-E03`, `W02-E05`, `W02-E06`, `W02-E07`, `W02-E08`
- `W02-E04` was rejected for no size gain.
- The W02 subagents unexpectedly shared the live workspace, so parent byte counts above are advisory snapshots only.
- `W02-R01` is the accepted recombined baseline for the next wave.

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
- Current accepted baseline:
  - `used_bytes_pre_preset_b=15103`
  - `last_used_pre_preset_b=0x4B61`
  - `free_bytes_before_0x4C00=158`
- Authoritative savings:
  - `-83` bytes vs accepted `W01-E02` baseline
  - `-100` bytes vs original pre-W01 source

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

## Dead Code Candidate List

| Label / Range | Why It Looks Dead | Static Evidence | Dynamic Evidence | Tests To Cover Removal | Risk | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| `wait_mssp_idle_bounded` | Post-stock helper had no current source call sites | `rg` over `src/dlcp_fw/asm/dlcp_main_v31.asm` found no `call`, `goto`, or `bra` references before deletion | `W02-R01` full gate passed after deletion | full V3.1 gate plus I2C recovery and robustness files | high | removed in `W02-R01` |
| `recover_mssp` | Post-stock helper had no current source call sites | `rg` over `src/dlcp_fw/asm/dlcp_main_v31.asm` found no `call`, `goto`, or `bra` references before deletion | `W02-R01` full gate passed after deletion | full V3.1 gate plus robustness files | high | removed in `W02-R01` |

## Open Questions And Blocked Tooling

- No current tooling blocker.
- Process note: W02 showed that `spawn_agent` workers can mutate the live workspace unless isolation is enforced manually. Future waves must use per-experiment isolated worktrees under `artifacts/reanalysis/...` rather than relying on implicit fork isolation.
- Next-wave priorities:
  - collect `W03-E01..W03-E08` results from the isolated worktrees and accept only coordinator-validated survivors
  - prefer fresh low-risk locals first: wrapper removal audits near the tail of the stock block, localized USB helper consolidation, and additional I2C helper tightening that does not create new fixed-address code
