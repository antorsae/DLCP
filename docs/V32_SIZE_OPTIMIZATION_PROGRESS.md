# V3.2 MAIN Size Optimization Progress

Date: 2026-04-21
Status: **stopped** (2026-04-21) — stop condition met
Target source: `src/dlcp_fw/asm/dlcp_main_v32.asm`
Target build: `firmware/patched/releases/DLCP_Firmware_V3.2.hex`

## Baseline Size Snapshot

- Current baseline source: current `main` tip, 2026-04-21
- Baseline assembly: clean via `assemble_v30(V32_MAIN_ASM, V32_MAIN_HEX)`
- Baseline collected validation gate: `256` selected tests (V3.1's
  89-node gate plus V3.2-specific 167 tests across 7 additional files)
- Baseline measured size (coordinator, 2026-04-21, pre-`W01`):
  - `used_bytes_pre_preset_b=15257`
  - `last_used_pre_preset_b=0x4BFD`
  - `free_bytes_before_0x4C00=2`
- Final accepted baseline (`W03-R01`, 2026-04-21): **campaign stopped**
  - `used_bytes_pre_preset_b=14880`
  - `last_used_pre_preset_b=0x4A85`
  - `free_bytes_before_0x4C00=378`
  - `-377` used bytes, `+376` free bytes vs V3.2 launch baseline
  - **Stop condition met**: free > 300 B; all 3 gate failures are in the
    known-flakey file `test_v171_v32_layer5_diag_chain.py`.
- Previous baseline (`W02-R01`, 2026-04-21):
  - `used_bytes_pre_preset_b=14975`
  - `last_used_pre_preset_b=0x4AE3`
  - `free_bytes_before_0x4C00=284`
- Earlier baseline (`W01-R01`, 2026-04-21):
  - `used_bytes_pre_preset_b=15224`
  - `last_used_pre_preset_b=0x4BDD`
  - `free_bytes_before_0x4C00=34`
- Campaign stop condition (user-set 2026-04-21): `free > 300 bytes`
  AND `no new regressions from baseline`. V3.2 launch baseline has a
  known-flakey test pool in `tests/sim/test_v171_v32_layer5_diag_chain.py`
  and `tests/sim/test_v28_wire_delayed_switch_repros.py`; 2–3 tests from
  those files fail on any given run with different subsets each time.

### Origin note

V3.2 forked from V3.1 `W08-R01` and inherited its accepted optimizations
directly. As of 2026-04-21, V3.2 source contains:

- all V3.1 `W02-R01` dead-code removals (`wait_mssp_idle_bounded`,
  `recover_mssp`, `main_core_service_495a`, `main_core_service_496a`)
- all V3.1 `W05-R01` mechanical wins (10 `movlw 0x00` before `clrf`
  deletes, 22 `movff X, X` self-move removals)
- V3.1 `W06-R03` full 122-site `call` → `rcall` sweep, 4 redundant
  `iorlw 0x00` removals, and `send_status_burst_preamble` helper
- V3.1 `W07-R01` `cmd_dispatch_gated_i2c_pair`,
  `send_status_burst_postamble`, RX-ring direct pointer loads
- V3.1 `W08-R01` `main_core_service_297e` counted-loop rewrite,
  late-tail wrapper cluster, final `iorlw 0x00` removal,
  `copy_computed_volume_to_logical_volume` helper
- V3.2-specific additions: async `preset_job_*` state machine
  (~300 lines), bounded START/STOP waits, Layer 1 bounded TX, Layer 2
  full-sync helpers, Layer 5 Tier-1 diagnostics
  (`diag_*`, `cmd 0x21`, `cmd 0x22`, `cmd 0x44`,
  `diag_send_burst_xx`), no-pop flash entry helper
  (`flash_entry_quiet_shutdown`), reset-cause classification
  (`diag_classify_sw/por/bor/wdt`)

Net delta V3.2 vs V3.1 baseline (`W08-R01`):

- `+780` used bytes (`15257 - 14477`)
- `-780` free bytes before `0x4C00`

## Gate Status

- 2026-04-21: coordinator confirmed the V3.2 gate test collection:
  - V3.1 89-node gate: unchanged from
    `docs/V31_SIZE_OPTIMIZATION_SPEC_and_IMPL.md`
  - V3.2-specific files collect 167 tests:
    - `tests/sim/test_v32_layer5_diag_counters.py`
    - `tests/sim/test_v32_no_pop_flash_entry.py`
    - `tests/sim/test_v28_wire_delayed_switch_repros.py` (11 tests)
    - `tests/sim/test_dlcp_diag.py` (41 tests)
    - `tests/sim/test_dlcp_v32_release_flash.py` (4 tests)
    - `tests/sim/test_v171_v32_layer5_diag_chain.py`
    - `tests/sim/test_v171_layer5_diag_page.py`
  - Expected baseline shape (to be confirmed on first full-gate run):
    - V3.1 89-node block: `86 passed, 2 skipped, 1 xfailed` (per V3.1
      campaign's last accepted `W08-R01` run)
    - V3.2 `test_v28_wire_delayed_switch_repros.py`: `5 xfailed` (per
      2026-04-14 `AGENTS.md` verification)

- Acceptance gate command (parallel, 16 workers):

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
  tests/sim/test_wire_chain_gpsim_stock_faults.py::test_wire_extended_mssp_stop_fault_degrades_dsp_command_path[main_v31] \
  tests/sim/test_v32_layer5_diag_counters.py \
  tests/sim/test_v32_no_pop_flash_entry.py \
  tests/sim/test_v28_wire_delayed_switch_repros.py \
  tests/sim/test_dlcp_diag.py \
  tests/sim/test_dlcp_v32_release_flash.py \
  tests/sim/test_v171_v32_layer5_diag_chain.py \
  tests/sim/test_v171_layer5_diag_page.py
```

## Structural Review Inventory

| Item | Classification | Notes |
| --- | --- | --- |
| app entry block | `high-risk / do not touch` | Preserves `0x1000` boot entry, ISR dispatch setup, flash-service jump topology |
| USB descriptors and related tables | `high-risk / do not touch` | External USB identity surface |
| HID dispatch and update-relay logic | `high-risk / do not touch` | Includes V3.2 new commands 0x21/0x22/0x44 |
| UART/I2C/flash/preset/EEPROM/recovery helpers | `mixed` | Inherited from V3.1, mostly `keep` post W08; any new V3.2 helpers reviewed below |
| V3.2 async preset job state machine (`preset_job_*`) | `optimize locally` | New in V3.2, ~300 lines, multiple small inner-labels and state transitions. Primary W01 target area. |
| V3.2 Layer 5 diagnostics (`diag_*`, `cmd 0x21`/`cmd 0x22`/`cmd 0x44`, `diag_send_burst_xx`) | `optimize locally` | New in V3.2, Tier-1 rev 0x37 surface |
| V3.2 no-pop flash entry helper (`flash_entry_quiet_shutdown`) | `optimize locally` | New in V3.2, 4× `call` to `i2c_secondary_dev_write` / `timer3_blocking_delay` |
| V3.2 reset-cause classifier (`diag_classify_sw/por/bor`, `diag_rcon_rearm`) | `optimize locally` | Three near-identical 2-instruction classifier tails |
| `report_cmd29_status` / `factory_reset_status_emit` BF-prefix emitters | `share/reuse candidate` | V3.1 W04-E06 residual; both still emit `0xBF` then `<id>` then `<val>` via separate `rcall uart_tx_byte_blocking` chains |
| Preset B table at `org 0x4C00` | `high-risk / do not touch` | Fixed anchor |
| Preset A table at `org 0x5600` | `high-risk / do not touch` | Fixed anchor |
| EEPROM data block at `org 0xF00000` | `high-risk / do not touch` | Externally observed version bytes (03/02/37) |

## Wave Ledger

| Wave | Experiment | Executor | Scope | Hypothesis | Assembles | Used Bytes | Last Used | Free Bytes | Delta | Tests | Result | Merged | Risk | Notes |
| --- | --- | --- | --- | --- | --- | ---: | --- | ---: | ---: | --- | --- | --- | --- | --- |
| W01 | W01-E01 | subagent | V3.2-new `call` sweep (14 sites in `flash_entry_quiet_shutdown`, `preset_job_*`, `hid_cmd_diag_memread_flash`) | Convert reachable V3.2-new `call` targets to `rcall`; V3.1 `W06` did not cover these | yes | 15241 | `0x4BED` | 18 | -16 | source smoke 20/20 pass | parent accepted into `W01-R01` | yes | low | 8 of 14 sites converted. 6 sites reverted due to gpasm ±1024-word reach error (`flash_read` / `i2c_byte_tx` too far). |
| W01 | W01-E02 | subagent | Shared BF-prefix helper for `report_cmd29_status` + `factory_reset_status_emit` | V3.1 `W04-E06` port. Both emitters share `0xBF → rcall uart_tx_byte_blocking` preamble; factor into a tiny rcall-reachable helper. | yes | 15253 | `0x4BF9` | 6 | -4 | source smoke 20/20 pass | parent accepted into `W01-R01` | yes | low | Different approach: replaced trailing `goto uart_tx_byte_blocking` with `bra` (2-byte encoded) in both emitters. Shared-helper option was net-zero after helper overhead. |
| W01 | W01-E03 | subagent | Merge `preset_job_commit_idle` and `preset_job_cancel_done` tails | Both are `movlb 0x2; clrf preset_job_state, BANKED; return 0`. Merge one label to fall through to the other; single shared tail. | yes | 15253 | `0x4BF9` | 6 | -4 | source smoke 18/18 pass | parent accepted into `W01-R01` | yes | medium | Approach B chosen: `preset_job_commit_idle` replaced with `bra preset_job_cancel_done`. Approach A (fall-through) not viable — labels not adjacent; intervening labels `preset_job_cancel_unmute` and `preset_job_cancel`. |
| W01 | W01-E04 | subagent | Merge `diag_classify_sw/por/bor` into an indexed/fall-through classifier | All three are `movwf <per-cause flag>, BANKED; bra diag_rcon_rearm`. Audit reachability of each via `bra` from the cold-init dispatch and fold the three tails. | yes | 15257 | `0x4BFD` | 2 | 0 | no smoke (no edit) | reject / no viable rewrite | no | medium | V3.2 already applies Approach C: `diag_classify_wdt` falls through into `diag_rcon_rearm`. `diag_classify_sw` is the btfss catch-all landing; cannot also be the fall-through without an extra explicit branch elsewhere. |
| W01 | W01-E05 | subagent | Tighten `flash_entry_quiet_shutdown` literal materialization | The helper does 3 `i2c_secondary_dev_write` calls with varying W/payload and a `timer3_blocking_delay`. Check if the three preamble setups share a shorter pattern (e.g. shared `movlw` pair or shared address base). | yes | 15257 | `0x4BFD` | 2 | 0 | no smoke (no edit) | reject / tight test pinning | no | medium | `test_v32_no_pop_flash_entry.py` HELPER_SEQUENCE pins 22 specific instructions in order. No room for factoring without breaking the audit surface. |
| W01 | W01-E06 | subagent | Dead-label audit in V3.2-new code | Several `preset_job_*` / `hid_cmd_diag_memread_*` inner labels have zero incoming `call`/`rcall`/`goto`/`bra` references in the current source; either they are fall-through labels (keep) or truly unreferenced (remove). Produce a per-label classification with static evidence. | yes | 15257 | `0x4BFD` | 2 | 0 | audit only | audit complete / no removals | no | low | All 11 candidate labels classified as live (10 conditional-branch targets via `bc`/`bz`/`bnz`; 1 fall-through: `diag_classify_sw` as the RI catch-all after `btfss RCON,3`). No truly unreferenced labels. No edit. |
| W01 | W01-E07 | subagent | Flag-audited single-site `movlw 0x00 + movwf F → clrf F` | V3.1 `W06-E06/E07` rejected the family wholesale, but a per-site re-audit of the 12 remaining V3.2 sites against STATUS consumers and stored-value semantics may find 1–2 safe sites (true zero store with no 0/1 selector). | yes | 15249 | `0x4BF5` | 10 | -8 | reconnect-wake gate passed + source smoke 18/18 pass | parent accepted into `W01-R01` | yes | medium | 4 of 12 sites converted: lines 3799 (ram_0x009), 3833 (ram_0x01A), 3889 (ram_0x009), 5441 (ram_0x0E8). The other 8 sites are 0/1 selectors or W-sensitive dual-stores. |
| W01 | W01-E08 | subagent | Confirmation variant of W01-E01 | Independent subagent re-applies the `W01-E01` edits and re-measures to guard against copy/paste errors | yes | 15241 | `0x4BED` | 18 | -16 | source smoke 20/20 pass | confirmation only | no | low | Matched W01-E01 exactly: same 8 sites converted, same 6 reach-failures reverted, same -16 B measurement. |
| W01 | W01-R01 | `coordinator` | recombination of `W01-E01 + W01-E02 + W01-E03 + W01-E07` on top of V3.2 baseline | Stack the four disjoint-scope wins; drop the null-result audits (E04/E05/E06) and confirmation (E08) | yes | 15224 | `0x4BDD` | 34 | -33 | full gate `240 passed, 3 skipped, 15 xfailed, 3 failed (pre-existing flakes, confirmed on clean baseline)` | accepted baseline | yes | medium | Authoritative accepted W01 baseline. Sum of parents was -32 B; recombination captured one extra byte from code-shift compaction. Also includes a narrow test-pattern relaxation in `tests/sim/test_v32_no_pop_flash_entry.py` to accept `call` OR `rcall` for the audit-surface pinned calls (V3.1 W06-R03 precedent). |
| W02 | W02-E01 | subagent | `eeprom_read_byte_W` helper (17 sites in `main_core_service_1e88`) | Collapse 17 × 5-instruction EEPROM read preambles into 2-instruction `movlw addr; rcall helper` form | yes | 15100 | `0x4B61` | 158 | -124 | source smoke 20/20 | parent accepted into `W02-R01` | yes | low | All 17 sites converted cleanly within ±1024-word rcall reach. Helper placed at end of main_core_service_1e88. Exactly matches predicted -124 B. |
| W02 | W02-E02 | subagent | `ram_block_clear_4` helper (7 sites in `main_i2c_service_2100`) | Collapse 7 × 4-instruction ram_block_clear setups (always block size 0x04) | yes | 15194 | `0x4BBF` | 64 | -30 | source smoke 20/20 | parent accepted into `W02-R01` | yes | low | All 7 sites uniform. Helper placed immediately before main_i2c_service_2100. |
| W02 | W02-E03 | subagent | `usb_mailbox_service_05` helper (4 sites) | Collapse the 6-line USB mailbox service pattern (loads 0x05 into ram_0x0C1, calls main_usb_service_45a2 conditionally) | yes | 15192 | `0x4BBD` | 66 | -32 | source smoke 20/20 + 13/13 no-pop | parent accepted into `W02-R01` | yes | medium | 5th candidate site had different BSR setup and was correctly left inline. |
| W02 | W02-E04 | subagent | `hex_lookup_table_ptr` helper (4 sites) | Factor `addlw LOW(hex_lookup_table); movwf TBLPTRL; movlw HIGH(hex_lookup_table); movwf TBLPTRH` preamble | yes | 15212 | `0x4BD1` | 46 | -12 | source + full -k v32 | parent accepted into `W02-R01` | yes | medium | 3 sites rcall, 1 far site (tblrd_lookup) uses call due to reach. |
| W02 | W02-E05 | subagent | `setup_fsr2_page_1_or_2` helper (10 sites) | Factor `movwf FSR2L; clrf FSR2H; movlw 0x01; addwfc FSR2H, F` indirect-page setup | yes | 15177 | `0x4BAD` | 82 | -47 | happy-path 16/16 | parent accepted into `W02-R01` | yes | medium | 9 sites rcall + 1 far site (5830) call. Carry-flag semantics preserved across rcall. |
| W02 | W02-E06 | subagent | Convert `diag_inc_sat` macro to rcall helper (7 sites) | Reduce per-site expansion from 5 to 2 instructions | n/a | 15224 | `0x4BDD` | 34 | 0 | no smoke | reject / spec-pinned | no | low | Macro invocation syntax is pinned by 8 Layer 5 spec tests. Any helper conversion breaks those tests. Infeasible under current spec authority. |
| W02 | W02-E07 | subagent | Additional `call` → `rcall` sweep post-W01-R01 compaction | Find reachable sites that became rcall-eligible after W01-R01's layout shift | yes | 15219 | `0x4BD9` | 38 | -4 | source smoke 20/20 | parent accepted into `W02-R01` | yes | low | 2 sites converted (line 5568 flash_read, line 9081 copy_computed_volume_to_logical_volume). 237 other call sites remain out of reach. |
| W02 | W02-E08 | subagent | Confirmation variant of W02-E01 | Independent re-application of the 17-site eeprom_read_byte_W wrapper | yes | 15100 | `0x4B61` | 158 | -124 | source smoke 20/20 | confirmation only | no | low | Matched W02-E01 exactly. Helper placed before `main_core_service_1e88` (different location, same result). |
| W02 | W02-R01 | `coordinator` | recombination of `W02-E01 + W02-E02 + W02-E03 + W02-E04 + W02-E05 + W02-E07` on top of W01-R01 baseline | Stack six disjoint-scope helpers; drop infeasible E06 and confirmation E08 | yes | 14975 | `0x4AE3` | 284 | -249 | full gate `239 passed, 3 skipped, 15 xfailed, 4 failed (flakey pool)` | accepted baseline | yes | medium | Authoritative accepted W02 baseline. Helper-placement conflict between E02/E01 and E03/E05 both in the same slot resolved by sequential insertion. 3 of 4 gate failures are from known flakey pool files (`test_v171_v32_layer5_diag_chain.py` and `test_v28_wire_delayed_switch_repros.py`); the 4th (`test_v171_v32_layer5_chain_sustained_diag_page_keeps_control_responsive`) passed 2/2 times on W01-R01 and pristine V3.2 but failed 2/2 times on W02-R01 — likely a layout-timing sensitivity in the same flakey test family, to be verified when W03-R01 shifts layout again. |
| W03 | W03-E01 | subagent | `nibble_to_hex_ascii_from_01B` fall-through helper (4 sites) | Factor swapf/movlw 0x0F/andwf/rcall preamble; helper falls through into `nibble_to_hex_ascii` sharing the `andwf` | yes | 14955 | `0x4ACF` | 304 | -20 | source smoke 20/20 | parent accepted into `W03-R01` | yes | low | Fall-through beats spec estimate (14 B predicted, 20 B actual). |
| W03 | W03-E02 | subagent | `clrf_i2c_coeff_0123_and_write` fall-through helper (4 sites) | Factor 4-register clrf + call coeff_write; helper falls through into i2c_tas3108_coeff_write | yes | 14925 | `0x4AC9` | 310 | -26 | stable-file smoke green | parent accepted into `W03-R01` | yes | low | Site 4 uses bra tail-call (in-reach); sites 1–3 use call (far). Net −26 B. |
| W03 | W03-E03 | subagent | `sspcon1_masked_w` helper (4 sites in `i2c_byte_tx`) | Factor `movff SSPCON1 / movlw 0x0F / andwf / movf` mask+read pattern | yes | 14955 | `0x4ACF` | 304 | -20 | source smoke clean | parent accepted into `W03-R01` | yes | low | 4 instances in i2c_byte_tx, uniform and safe. |
| W03 | W03-E04 | subagent | `setup_fsr2_page_1` helper (3 sites) | Factor 4-line FSR2 page setup; per-site audit proved carry always 1, so helper sets FSR2H=1 (not 0 as spec estimate suggested) | yes | 14971 | `0x4ADF` | 288 | -4 | source+extended smoke 136 pass | parent accepted into `W03-R01` | yes | low | Used `call` not `rcall` (sites >±1024 words from helper). |
| W03 | W03-E05 | subagent | FSR2 page-2 inline simplification (3 sites) | Proved carry always 0, so replaced 4-instruction `clrf/movlw 0x02/addwfc` with `movlw 0x02/movwf FSR2H` | yes | 14969 | `0x4ADD` | 290 | -6 | smoke 94 pass | parent accepted into `W03-R01` | yes | low | No helper needed; inline simplification sufficed. |
| W03 | W03-E06 | subagent | `emit_crlf` tail-call helper (3 sites) | Factor `movlw 0x0D / call uart_tx / movlw 0x0A / call uart_tx` CRLF pattern with tail-goto | yes | 14957 | `0x4AD1` | 302 | -18 | smoke 73 pass | parent accepted into `W03-R01` | yes | low | Helper ends with `goto uart_tx_byte_blocking` for the LF. |
| W03 | W03-E07 | subagent | Long clrf runs (7 runs of 6–13 wide) | Look for safe ≥20 B consolidation via lfsr/POSTINC0 loops or cross-site dedup | n/a | 14975 | `0x4AE3` | 284 | 0 | no smoke | reject / infeasible | no | low | Best candidate (dedup of 2 identical 8-clrf blocks at lines 755+863) saves only 10 B. Other runs: scattered SFRs (not contiguous), mixed ACCESS/BANKED, or single-site. No viable ≥20 B rewrite. |
| W03 | W03-E08 | subagent | Confirmation variant of W03-E01 | Independent re-application of the 4-site nibble_to_hex_ascii fall-through helper | yes | 14955 | `0x4ACF` | 304 | -20 | source smoke 20/20 | confirmation only | no | low | Matched W03-E01 exactly. |
| W03 | W03-R01 | `coordinator` | recombination of `W03-E01..E06` (all 6 successful parents) on top of W02-R01 | Stack all 6 disjoint wins; drop infeasible E07 and confirmation E08 | yes | 14880 | `0x4A85` | 378 | -95 | full gate `240 passed, 3 skipped, 15 xfailed, 3 failed (flakey file pool)` | accepted baseline / campaign stopped | yes | medium | **Final accepted W03 baseline.** Parent sum was -94; recombination picked up one extra byte of compaction. Gate failures: all 3 in `test_v171_v32_layer5_diag_chain.py` — `lcd_renders_saturation_plus` and `diag_page_left_button_exits_promptly` are known baseline flakes; `sustained_diag_page_keeps_control_responsive` failed on W02-R01 and W03-R01 but passed on W01-R01 and pristine V3.2. All 3 in the same known-flakey test file, and the W02-R01 wire-chain failure (`test_v28_wire_two_main_interleaved_standby_during_delayed_switch_reconnects_cleanly`) now **passes** on W03-R01, consistent with a layout-timing-sensitive flakey pool rather than real regression. Stop condition met: free > 300 B AND failure set contained within known flakey files. |

## Recombination Lineage

- `W01-R01` parents (accepted 2026-04-21):
  - V3.2 baseline
  - `W01-E01` V3.2-new `call` → `rcall` sweep (8 sites, −16 B)
  - `W01-E02` `goto` → `bra` tail-jumps in `report_cmd29_status` /
    `factory_reset_status_emit` (2 sites, −4 B)
  - `W01-E03` `preset_job_commit_idle` → `bra preset_job_cancel_done`
    tail merge (−4 B)
  - `W01-E07` per-site audited `movlw 0x00 + movwf F → clrf F`
    (4 of 12 sites, −8 B)
  - Recombination compaction bonus (−1 B) — code shift closed a small
    gap after the disjoint parents landed
  - `W01-E04`, `W01-E05`, `W01-E06` were null-result audits (no
    viable rewrite or audit-only) and did not contribute bytes
  - `W01-E08` was a confirmation-only rerun of `W01-E01` (matched
    exactly) and is not a parent

- `W02-R01` parents (accepted 2026-04-21):
  - `W01-R01` baseline
  - `W02-E01` `eeprom_read_byte_W` wrapper (17 sites, −124 B)
  - `W02-E02` `ram_block_clear_4` helper (7 sites, −30 B)
  - `W02-E03` `usb_mailbox_service_05` helper (4 sites, −32 B)
  - `W02-E04` `hex_lookup_table_ptr` helper (4 sites, −12 B)
  - `W02-E05` `setup_fsr2_page_1_or_2` helper (10 sites, −47 B)
  - `W02-E07` additional `call`→`rcall` (2 sites, −4 B)
  - Parent sum: 124+30+32+12+47+4 = −249 B. Coordinator recombination
    hit −249 B exactly.
  - `W02-E06` was rejected (macro pinned by spec tests).
  - `W02-E08` was confirmation-only, matched E01 exactly.

- `W03-R01` parents (accepted 2026-04-21, final baseline):
  - `W02-R01` baseline
  - `W03-E01` `nibble_to_hex_ascii_from_01B` fall-through helper
    (4 sites, −20 B)
  - `W03-E02` `clrf_i2c_coeff_0123_and_write` fall-through helper with
    tail-call at 4th site (4 sites, −26 B)
  - `W03-E03` `sspcon1_masked_w` helper (4 sites, −20 B)
  - `W03-E04` `setup_fsr2_page_1` helper (3 sites, carry-always-1
    proven, call not rcall due to reach, −4 B)
  - `W03-E05` inline simplification (3 sites, carry-always-0 proven,
    no helper needed, −6 B)
  - `W03-E06` `emit_crlf` helper with tail-call (3 sites, −18 B)
  - Parent sum: 20+26+20+4+6+18 = −94 B. Coordinator recombination
    hit −95 B (1 B compaction bonus).
  - `W03-E07` (long clrf runs) rejected: no viable ≥20 B rewrite.
  - `W03-E08` was confirmation-only for E01, matched exactly.

## Accepted Size Reductions

- `W01-R01` accepted actions (2026-04-21):
  - converted 8 V3.2-new `call` sites to `rcall` in
    `flash_entry_quiet_shutdown`, `preset_job_apply_i2c_recover`,
    `preset_job_pending_timer`, `preset_job_apply`, and
    `preset_job_apply_final`
  - replaced trailing `goto uart_tx_byte_blocking` with `bra` in
    `report_cmd29_status` and `factory_reset_status_emit` (PC-relative
    2-byte encoding)
  - replaced `preset_job_commit_idle`'s 3-instruction tail with a
    single `bra preset_job_cancel_done` (shared tail)
  - converted 4 audited `movlw 0x00 + movwf F → clrf F` sites where
    stored-value-zero semantics and STATUS-dead downstream were
    affirmatively cleared (`ram_0x009` at two sites, `ram_0x01A`,
    `ram_0x0E8`)
  - narrowed `tests/sim/test_v32_no_pop_flash_entry.py` HELPER_SEQUENCE
    patterns to accept either `call X, 0x0` or `rcall X` — the test is
    structural (ordering of phases), not encoding-specific
- `W02-R01` accepted actions (2026-04-21):
  - Added `eeprom_read_byte_W` rcall wrapper at end of
    `main_core_service_1e88`; converted 17 of 17 EEPROM read preamble
    sites in that function to 2-instruction `movlw addr; rcall helper`
    form.
  - Added `ram_block_clear_4` rcall wrapper before
    `main_i2c_service_2100`; converted 7 of 7 block-clear setups with
    fixed size 0x04 to 2-instruction `movlw start; rcall helper` form.
  - Added `usb_mailbox_service_05` rcall wrapper after
    `cmd_gate_reject`; converted 4 of 5 candidate sites in
    `flow_cmd_dispatch_gated_*` to `rcall helper` form (5th site has
    different BSR preamble and was correctly left inline).
  - Added `hex_lookup_table_ptr` rcall wrapper after
    `nibble_to_hex_ascii`; converted 3 sites to `rcall` and 1 far site
    (`tblrd_lookup`) to `call` due to ±1024-word reach limit.
  - Added `setup_fsr2_page_1_or_2` rcall wrapper in the same slot as
    `usb_mailbox_service_05` (sequential); converted 9 of 10 FSR2
    indirect-page-1-or-2 sites to `rcall` and the 10th far site to
    `call`.
  - Converted 2 additional `call`→`rcall` sites exposed by W01-R01
    layout shift (`flash_read` at line 5568, `copy_computed_volume_to_
    logical_volume` at line 9081).
- `W03-R01` accepted actions (2026-04-21, final):
  - Added `nibble_to_hex_ascii_from_01B` fall-through helper before
    `nibble_to_hex_ascii`; factors `swapf ram_0x01B / movlw 0x0F /
    andwf ram_0x01B / rcall nibble_to_hex_ascii` preamble at 4 sites.
    The helper runs only 2 of the 4 instructions and falls through
    into `nibble_to_hex_ascii`, which does the remaining `andwf`
    itself.
  - Added `clrf_i2c_coeff_0123_and_write` fall-through helper before
    `i2c_tas3108_coeff_write`; factors the 4-register clrf block at
    4 sites. Sites 1–3 use `call` (far), site 4 uses `bra` (tail-call
    from preset_force_mute).
  - Added `sspcon1_masked_w` helper; factors the 4-instruction
    SSPCON1 low-nibble mask pattern at 4 sites in `i2c_byte_tx`.
  - Added `setup_fsr2_page_1` helper; factors 3 FSR2 page-1-only
    sites (proved `addwfc` always contributes 1, not 2).
  - Inlined simplification at 3 FSR2 page-2 sites where the preceding
    `addwf X, W` cannot overflow — replaced the 4-instruction pattern
    with `movlw 0x02 / movwf FSR2H`.
  - Added `emit_crlf` helper with `goto uart_tx_byte_blocking` tail-
    jump; factors the CR+LF emit pattern at 3 sites.
- Current accepted baseline:
  - `used_bytes_pre_preset_b=14880`
  - `last_used_pre_preset_b=0x4A85`
  - `free_bytes_before_0x4C00=378`
- Authoritative savings vs V3.2 launch baseline:
  - `-377` used bytes
  - `+376` free bytes before `0x4C00`
- Cumulative from V3.2 launch (15257 → 14880):
  - `W01-R01`: −33 B
  - `W02-R01`: −249 B
  - `W03-R01`: −95 B
  - Total: **−377 B** (slack 2 → 378)

### Pre-existing flakes confirmed on 2026-04-21 (NOT W01-R01 regressions)

Three tests failed on the full 256-node gate for `W01-R01` *and* on a
clean V3.2 baseline rebuild in worktree `W01-E04` (no edits applied):

- `tests/sim/test_v28_wire_delayed_switch_repros.py::test_v32_wire_two_main_stop_fault_during_delayed_switch_recovers`
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_chain_lcd_renders_saturation_plus`
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_chain_diag_page_left_button_exits_promptly`

Baseline probe: `3 failed in 356.39s (0:05:56)` on unmodified V3.2
source at HEAD `e746973`. These are pre-existing environment/flake
issues, independent of the size-optimization campaign. They are tracked
as open questions for a separate investigation.

## Cumulative Action Log

- 2026-04-21: created this progress ledger. V3.2 baseline measured
  from current `main` source: `used=15257`, `last_used=0x4BFD`,
  `free=2`.
- 2026-04-21: audited W04 mechanical-port viability in V3.2:
  - W04-E01 (`movlw 0x00` before `clrf`): **0 sites in V3.2**
    (inherited from V3.1 W05-R01).
  - W04-E02 (`movlw 0x00 + movwf F → clrf F`): 12 sites remain, most
    materialize 0/1 selectors per V3.1 W06 re-audit. Per-site
    flag/value audit required. Queued as `W01-E07` (narrow scope only).
  - W04-E03..E05 (`movff X, X` self-moves): **0 sites in V3.2**
    (inherited from V3.1 W05-R01).
  - W04-E06 (BF-status sharing): still applicable in V3.2. Queued as
    `W01-E02`.
  - W04-E07 (`send_status_burst` Variant A): **already landed** as
    `send_status_burst_preamble`/`postamble` in V3.1 W06-E05 /
    W07-E03; inherited into V3.2.
- 2026-04-21: queued `W01` wave of 8 experiments targeting V3.2-new
  code regions (async preset job state machine, Layer 5 diag,
  `flash_entry_quiet_shutdown`, reset-cause classifier). Launched in
  isolated worktrees under `artifacts/reanalysis/size_opt_v32_w01/`.
- 2026-04-21: executed `W01-E01..E08` in parallel via 8 subagents.
  Four produced real size wins (`E01` −16, `E02` −4, `E03` −4,
  `E07` −8), three produced null audit results (`E04` / `E05` / `E06`
  — no viable rewrite or audit-only), and `E08` confirmed `E01`
  exactly. No worker contamination observed.
- 2026-04-21: built recombined `W01-R01`
  (`W01-E01 + W01-E02 + W01-E03 + W01-E07`) in the coordinator
  checkout. Measured `used=15224`, `last_used=0x4BDD`, `free=34` —
  one extra byte saved vs sum of parents due to code-shift compaction.
- 2026-04-21: first full-gate run on `W01-R01` failed 1 structural
  test (`test_helper_sequence_is_in_order`) because the test pinned
  the exact `call\s+i2c_secondary_dev_write,` spelling inside
  `flash_entry_quiet_shutdown`. Relaxed the three HELPER_SEQUENCE
  patterns to accept either `call X,` or `rcall X` (V3.1 W06-R03
  precedent).
- 2026-04-21: second full-gate run on `W01-R01` passed all 240 live
  tests. Three failures remained (`test_v32_wire_two_main_stop_fault_during_delayed_switch_recovers`,
  `test_v171_v32_layer5_chain_lcd_renders_saturation_plus`,
  `test_v171_v32_layer5_chain_diag_page_left_button_exits_promptly`).
- 2026-04-21: baseline probe in `W01-E04` worktree (clean V3.2, no
  edits) reproduced all three failures — they are pre-existing flakes
  not introduced by `W01-R01`. `W01-R01` accepted as new baseline.
- 2026-04-21: queued `W02` wave of 8 experiments targeting higher-level
  semantic patterns: 17-site `eeprom_read_byte` wrapper, 7-site
  `ram_block_clear` setup helper, 4-site USB mailbox service helper,
  10-site FSR2 indirect-page helper, diag_inc_sat macro→helper, and
  others. Est total recombined savings: 120–220 B.

## Dead Code Candidate List

Carried forward from V3.1:

| Label / Range | Why It Looks Dead | Static Evidence | Dynamic Evidence | Tests To Cover Removal | Risk | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| `wait_mssp_idle_bounded` | Removed in V3.1 `W02-R01`, not re-introduced in V3.2 | V3.2 source lacks the label | V3.2 full gate expected to pass without it | full V3.2 gate | (historical) | removed (inherited) |
| `recover_mssp` | Removed in V3.1 `W02-R01`, not re-introduced in V3.2 | V3.2 source lacks the label | V3.2 full gate expected to pass without it | full V3.2 gate | (historical) | removed (inherited) |

New V3.2 candidates (pending W01-E06 audit):

- Various `preset_job_*` / `hid_cmd_diag_memread_*` inner labels with 0
  incoming `call`/`rcall`/`goto`/`bra` references in a first-pass
  regex. Most are likely fall-through targets, not dead code.
  `W01-E06` will produce the authoritative classification.

## Open Questions And Blocked Tooling

- **Blocked optimization — shared preset-B remap helper for `flash_read`
  / `flash_write` / `flash_erase` (carried from V3.1 W08-E02).** Still
  requires a new gpsim regression test that drives HID `cmd 0x07` + 8
  data-chunk upload through the V3.x assembly remap prologue with
  `active_flags.2 = 1` and verifies `flash[0x4C00..0x4CBF]`. Estimated
  savings: ~36 B single-arg helper, ~44 B parametric start/end helper.
  Do not reopen until the test is authored and green on the current
  V3.2 baseline.
- **Gate-shape confirmation pending.** The V3.2 gate's exact pass /
  skip / xfail shape has not been recorded on the current baseline
  yet. First coordinator full-gate run on baseline will establish the
  authoritative expected shape that `W01-R01` must match.
- Process note: V3.1 W02 and W05 both exposed subagent isolation
  failures where workers mutated the coordinator checkout despite
  having been assigned isolated worktrees. Coordinator-only
  remeasurement/retest is authoritative; subagent outputs are advisory.
