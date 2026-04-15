# DLCP Robustness Plan

Status:

- 2026-03-10 correction: the first `V2.5` MAIN artifact had a bad MSSP-idle wait implementation in the patched `function_113` path; the current repo copy of `DLCP_Firmware_V2.5.hex` has been rebuilt with stock-equivalent wait semantics. Treat any earlier exported/flashed `V2.5` copy as bad.
- MAIN `V2.5` is now implemented on top of the `V2.4` A/B preset patch base.
- CONTROL `V1.62b` is now implemented on top of the `V1.61b` A/B preset patch base.
- 2026-03-11 correction: physical MCU inspection confirms CONTROL is `PIC18F25K20` and MAIN is `PIC18F2455`. CONTROL builders are now retargeted to `PIC18F25K20`. MAIN builders and MAIN gpsim harnesses are now retargeted to `PIC18F2455`.
- 2026-03-12 update: the repo-local `gpsim-xtc` fork now supports `p18f25k20`, and CONTROL gpsim harnesses use the real target instead of the old `p18f2550` surrogate model.
- 2026-03-11 MAIN `V2.5` timeout policy was hardened again: the patched wait loops now use 16-bit measured loop budgets instead of raw `0xFF` spins, first failure does local UART/MSSP reinit, and hard reset is only taken after a repeated failure in the same operation path.
- Current rebuilt `DLCP_Firmware_V2.5.hex` SHA-256: `1822159bb9fe5312b2e2d09173e2d8d8b1e843b7ed65412d06efa36aa6997717`
- A raw-main `gpsim` harness now exists and runs CONTROL against the real `V2.5` MAIN parser and timeout code via native-ring injection.
- Current raw-main simulation status:
  - basic CONTROL gpsim regressions now run on the real `p18f25k20` model from the repo-local `gpsim-xtc` fork
  - MAIN-side native-ring runs now progress through the stock `function_079` Timer3 wait using native `p18f2455` Timer3 behavior; the earlier compare harness failure was in the repo harness, not the gpsim core overflow path
  - earlier reconnect conclusions for `V2.5 + V1.61b` and `V2.5 + V1.62b` were collected before the `p18f25k20` port and should be treated as pre-port evidence pending revalidation under the new CONTROL model
  - hardware bench validation of the rebuilt MAIN `V2.5` with `V1.61b` CONTROL is still pending and remains the release-critical next step

Versioning (as of 2026-03-30):

- MAIN releases: `V2.4` (A/B only), `V2.5` (+ robustness), `V2.6` (+ DSP ACKSTAT), `V2.7` (+ bus-clear/ping/PEN), `V3.0` (source rewrite), `V3.1` (all features inline)
- CONTROL releases: `V1.41`–`V1.61b` (A/B), `V1.62b` (+ reconnect), `V1.63b` (+ BF/08 fault UI/resync), `V1.64b` (+ explicit IR standby/wake endpoints)
- This document was originally written targeting V2.5/V1.62b as next releases

This document consolidates the stock deadlock findings, ranks the earlier analyses by trust level, and defines the implementation order needed to reduce `WAITING FOR DLCP` hangs without breaking deployed `V1.61b` control units.

## Inputs

Primary source documents:

- `docs/analysis/STOCK_SYNC_DEADLOCK_ANALYSIS_2026-03-08-gpt-5.2-pro.md`
- `docs/analysis/STOCK_SYNC_DEADLOCK_ANALYSIS_2026-03-08-gpt-5.4-xhigh.md`
- `docs/analysis/STOCK_SYNC_DEADLOCK_ANALYSIS_2026-03-08-opus-4.6.md`

Direct validation sources:

- `firmware/disasm/main/gpdasm_output.asm`
- `firmware/disasm/control/v1.4_disasm.asm`
- `firmware/disasm/control/v1.5b_disasm.asm`
- `firmware/disasm/control/v1.6b_disasm.asm`
- `firmware/stock/main/DLCP Firmware V2.3.hex`
- `firmware/stock/control/DLCP Control Firmware V1.4.hex`
- `firmware/reference/39632e.pdf` (authoritative)
- `firmware/reference/39632e.md` (line-stable converted companion)

## Analysis Assessment

Recommended baseline:

- `gpt-5.4-xhigh` is the best baseline. It identifies the important transport and wait-state issues and its recommended patch targets mostly match the disassembly.

Useful but incomplete:

- `gpt-5.2-pro` is a good short summary of the highest-confidence problems, especially MAIN-side hard waits and disabled watchdog behavior.

Useful but too absolute in places:

- `opus-4.6` adds valuable detail, but some statements are stronger than the code proves.
- In particular, claims such as "guaranteed OERR on every EEPROM write" or "no frame resynchronization mechanism at all" should be treated as probable risk statements, not hard facts.

## Confirmed Findings

### 1. CONTROL has real permanent wait states

Stock `V1.4` has two explicit forever loops:

- boot wait at `label_204` / `0x11DE`
- reconnect wait at `label_216` / `0x130A`

Both repeatedly send the same poll frame `B1 04 00`, parse RX, and loop without timeout or recovery.

Operational effect:

- if MAIN stops responding, CONTROL can stay on `WAITING FOR DLCP` forever
- if MAIN partially responds but required status fields do not update, CONTROL can still stay in the wait loop

### 2. MAIN has real hard-stop paths

The following MAIN functions use unbounded blocking waits:

- `function_111` at `0x4896`: UART TX waits on `TXSTA.TRMT`
- `function_113` at `0x48B6`: MSSP idle wait
- `function_056` at `0x3E68`: SSP completion / buffer waits
- `function_072` at `0x4368`: generic I2C start/stop path
- `function_093` at `0x46BA`: I2C transaction helper

Operational effect:

- if MAIN wedges in one of these loops, it stops servicing control commands
- this directly matches the field symptom "control still reacts, but volume changes do not take effect"

### 3. Both MCUs use RX rings without a full-state

CONTROL:

- ISR writes into the RX ring and wraps
- foreground treats `write == read` as empty
- there is no overflow/full distinction

MAIN:

- same pattern in the UART RX ring
- overflow can silently overwrite unread bytes and collapse into the empty state

Operational effect:

- under burst traffic or long blocking sections, serial state can be lost without an explicit fault
- this is a credible cause of command loss and parser misalignment

### 4. CONTROL traffic volume matters

`V1.4` and `V1.5b` use a very heavy periodic full-sync burst.

`V1.6b` reduces that burst significantly and is therefore the right CONTROL base for a robustness release.

Operational effect:

- reducing traffic does not fix the fundamental bugs
- but it lowers transport pressure and is worth preserving in `V1.62b`

### 5. WDT is effectively off in stock

Confirmed from stock config records and disassembly:

- MAIN stock `CONFIG2H = 0x1E`
- CONTROL stock `CONFIG2H = 0x00`
- neither stock application writes `WDTCON`

Operational effect:

- deadlocks do not self-recover
- watchdog should be treated as a later safety net, not the primary fix

### 6. MAIN has at least one additional I2C failure amplifier

MAIN checks `SSPCON1.WCOL` in `function_056`.

I did not find an explicit `WCOL` clear path elsewhere in the MAIN disassembly.

Operational effect:

- an I2C write-collision path may leave MAIN in a state where DSP updates stop working until reset
- this fits the symptom where the UI still appears alive but audio changes stop applying

## Likely Field Failure Chains

### Chain A: MAIN hard hang -> CONTROL permanent wait

1. MAIN enters an unbounded I2C or UART wait.
2. CONTROL keeps polling.
3. CONTROL eventually lands in boot/reconnect wait logic.
4. No timeout exists, so `WAITING FOR DLCP` becomes permanent.

This is the highest-confidence explanation for the full hang symptom.

### Chain B: MAIN alive but no longer acts on commands

1. MAIN hits a transport fault, parser misalignment, or I2C error state.
2. CONTROL still appears responsive locally.
3. Volume/input/mute commands are sent but no longer applied by MAIN.
4. Link health degrades further and CONTROL later falls back to `WAITING FOR DLCP`.

This is the highest-confidence explanation for the "volume changes do nothing" symptom.

### Chain C: one bad unit propagates failure through a chain

1. One MAIN stops forwarding or responding in a timely way.
2. Upstream CONTROL continues synchronous polling/sending.
3. Transport pressure and blocking behavior strand downstream communication.

This remains a credible explanation for multi-unit lockups.

## Compatibility Answer

Yes: patching MAIN first is compatible with the goal "`V2.5` must work with existing `V1.61b`".

That is only true if `V2.5` follows these rules:

- keep the current-loop frame format unchanged: still `route/cmd/data`
- keep the existing poll/response behavior used by stock and `V1.61b`
- do not require any new CONTROL command for MAIN recovery
- make all new recovery logic local to MAIN
- preserve existing preset command behavior used by `V1.61b`, including `cmd=0x20`
- after any local recovery or soft reset, return to stock-compatible boot/link behavior

In practice, `V2.5` should be a wire-compatible robustness release, not a protocol revision.

## Release Strategy

### MAIN `V2.5`

Purpose:

- fix the most likely initiating faults on MAIN
- remain compatible with current deployed `V1.61b`
- be deployable on its own

Required support matrix:

- `MAIN V2.5` + `CONTROL V1.61b`: required
- `MAIN V2.5` + `CONTROL V1.62b`: required

### CONTROL `V1.62b`

Purpose:

- remove permanent `WAITING FOR DLCP` states
- improve parser and queue robustness
- keep the reduced `V1.6b` sync style

Release policy:

- only `V1.62b` is planned as the robustness CONTROL release
- no new `V1.42` or `V1.52b` ports are planned

## Implementation Plan

### Phase 1: MAIN `V2.5` first, wire-compatible with `V1.61b`

Goal:

- fix the initiating failures without depending on a new CONTROL build

Work items:

1. Add bounded timeout and recovery to:
   - `function_111`
   - `function_113`
   - `function_056`
   - `function_072`
   - `function_093`
2. On timeout, prefer local peripheral recovery first:
   - reset MSSP state
   - clear or reinitialize UART state
   - clear latched error state where possible
3. If local recovery fails or the state is not trustworthy, soft-reset MAIN.
4. Preserve all existing wire-visible behavior after recovery:
   - same poll replies
   - same routing semantics
   - same preset command handling
5. Do not add any mandatory new protocol element in `V2.5`.

Acceptance criteria:

- `V2.5 + V1.61b` boots reliably
- `V2.5 + V1.61b` recovers from transient active-path MAIN timeout faults
- induced MAIN timeout no longer leads to permanent `WAITING FOR DLCP` during normal active-display operation
- current raw-main `gpsim` also shows reconnect after clearing the induced wake / standby UART-timeout fault
- hardware validation and comparative reconnect robustness vs `V1.62b` are still pending
- volume/input/mute still work with existing `V1.61b`

### Phase 2: CONTROL `V1.62b`

Goal:

- remove permanent wait behavior and improve transport recovery

Implemented in the first `V1.62b` candidate:

1. Add a parser-entry hook at `0x044A`:
   - preserve stock parser flow when no UART overrun is present
   - on `OERR`, drain `RCREG`, reset UART cursors, and clear parser state
2. Replace the weak wake reconnect loop at `0x12BC`:
   - do not exit reconnect based on `BF 03` state alone
   - require the same stronger non-`0x80` status handshake used by the stock boot path
   - periodically re-prime UART/parser state while continuing to show `WAITING FOR DLCP`
3. Preserve the reduced `V1.6b` sync pattern rather than reintroducing a large full-sync burst.
4. Keep protocol fully compatible with both `V2.4` and `V2.5`.

Remaining follow-up items:

1. Decide whether the boot-side wait path should use the same stronger reconnect wrapper.
2. Add RX ring full detection or controlled overwrite policy.
3. Add parser idle timeout so partial frames do not persist forever.
4. Add timeout to TX enqueue full-spin paths.

Acceptance criteria:

- raw-main `gpsim` shows `V2.5 + V1.62b` recovering from the wake / reconnect `WAITING FOR DLCP` case that strands `V2.5 + V1.61b`
- reconnect works after transient MAIN reset/recovery
- no protocol change is required on MAIN for basic operation

### Phase 3: optional safety net work

Only do this after Phases 1 and 2 are stable.

Candidates:

- add watchdog recovery
- review `STVREN`
- add internal fault counters or reset-cause diagnostics

Reason for delaying WDT:

- watchdog alone would convert silent hangs into resets, but would not solve transport corruption
- CONTROL stock configuration is especially sensitive because software-only WDT enable would be too aggressive without matching config and `CLRWDT` placement work

## Patch Policy

For the robustness work:

- do not change the current-loop packet format
- do not require paired flashing of MAIN and CONTROL
- keep `V2.5` independently deployable against existing `V1.61b`
- keep `V1.62b` as a compatible CONTROL-side improvement, not a protocol fork

## Validation Strategy

The validation goal is not just "system boots". The tests must:

- reproduce `WAITING FOR DLCP` on stock firmware under realistic fault conditions
- show that `V2.5 + V1.61b` reduces or eliminates permanent hangs caused by transient MAIN failures
- distinguish active-path recovery from standby-exit / reconnect recovery
- show that `V2.5 + V1.62b` further reduces reconnect dwell and parser-related lockups
- preserve the negative case where a genuinely absent MAIN still results in `WAITING FOR DLCP`

The test split should be:

- stock reproduction tests
- `V2.5 + V1.61b` compatibility and recovery tests
- `V2.5 + V1.62b` full robustness tests

## Harness Prerequisites

Before the new robustness tests are meaningful, the simulator must stop masking the failure paths we want to measure.

Required harness changes:

1. CONTROL gpsim harness must support running without the standby-disable overlay.
   Current harness behavior keeps CONTROL in DISPLAY mode for standalone testing and hides the reconnect path that shows `WAITING FOR DLCP`.
2. MAIN gpsim harness must support running without unconditional I2C bypass when testing MAIN deadlock behavior.
   Internal PIC `EECON1.WR` waits now run natively; only the external
   MSSP/I2C bypass remains as an optional compatibility overlay when no
   slave model is attached. The chain harness now defaults to attaching
   generic `cfg71` (`0x71`) and `dsp34` (`0x34`) `i2c_regfile` slaves when
   `bypass_i2c=False`. Fidelity tests should prefer the real
   `i2c_regfile` bus path over the bypass.
   The fixed wire-UART harness now also supports bounded one-way wake-time
   drop/delay faults on the real `RC6/RC7` path. Current characterization does
   not show a clean MAIN-only split: with `V1.61b`, tested bounded wake faults
   strand both `V2.4` and `V2.5`; with `V1.62b`, lighter bounded wake-delay
   release tests reconnect both. The same remains true for the newer one-shot
   external `cfg71` wake-time I2C faults: they now auto-expire on the next
   `N` matching transactions, but the observed split is still primarily
   CONTROL-side (`V1.61b` strands both MAIN versions; `V1.62b` reconnects both).
   The same remains true for newer higher-fidelity internal gpsim core faults:
   one-shot EUSART `TRMT` busy delay and one-shot MSSP stop/idle busy delay
   still separate `V1.61b` from `V1.62b` more clearly than they separate
   `V2.4` from `V2.5`.
3. Add test-only fault overlays for MAIN timeout paths.
   These should force persistent busy/stuck conditions in specific wait loops so the recovery code can be exercised deterministically.
4. Persist LCD timelines and key events under `artifacts/sim/current/robustness/`.
   Robustness tests should leave behind enough evidence to inspect whether CONTROL actually entered and exited `WAITING FOR DLCP`.

These harness changes are test-only and must not change production HEX files.

## Fault Injection Plan

### 1. Stock boot WAITING baseline

Purpose:

- prove the CONTROL LCD path can show `WAITING FOR DLCP` on real stock code in simulation

Method:

- boot stock CONTROL `V1.4` with no cooperating MAIN
- no synthetic heartbeat injection

Expected result:

- LCD shows `Waiting for DLCP`
- system stays there for the full test budget

This is the baseline proof that the LCD and wait-loop observation path are working.

### 2. Transient MAIN-response blackout

Purpose:

- reproduce the field case where CONTROL was healthy, then MAIN stopped responding

Method:

- boot CONTROL + MAIN into normal display
- after stable link-up, stop or drop `MAIN -> CONTROL` responses for a bounded interval
- then restore MAIN stepping or response delivery

Expected result:

- stock `2.3 + 1.4`: CONTROL enters `WAITING FOR DLCP` and remains stuck
- `V2.5 + V1.61b`: active-path faults should recover locally, and current raw-main `gpsim` also shows recovery after the induced wake fault is cleared
- `V2.5 + V1.62b`: same as above, with the reconnect-hardened CONTROL-side logic still expected to give lower dwell and better margin

### 3. Forced MAIN MSSP/I2C stuck-busy fault

Purpose:

- exercise the highest-confidence initiating fault on MAIN

Method:

- add a test-only overlay that makes one of these MAIN waits remain busy:
  - `function_113`
  - `function_056`
  - `function_072`
  - `function_093`
- inject the fault during active volume or input traffic

Expected result:

- stock MAIN stops acting on commands and later strands CONTROL in `WAITING FOR DLCP`
- `V2.5` hits timeout/recovery and resumes stock-compatible communication

This is the most important fault-injection test for `V2.5`.

### 4. Forced MAIN UART TX stall

Purpose:

- exercise the second major unbounded wait in MAIN

Method:

- add a test-only overlay that keeps `function_111` waiting on `TXSTA.TRMT`
- inject the fault while MAIN is expected to transmit status/response traffic

Expected result:

- stock hangs permanently
- `V2.5` times out, recovers or resets, and reconnects with `V1.61b`

### 5. CONTROL reconnect parser fault / OERR-style fault

Purpose:

- verify `V1.62b` actually improves reconnect behavior rather than only shortening happy-path timing

Method:

- during reconnect, inject byte-level damage:
  - partial frame
  - dropped byte
  - constrained FIFO depth
  - repeated burst pressure

Expected result:

- `V1.61b` is more likely to remain stuck or take longer to recover
- `V1.62b` drains/reinitializes/resynchronizes and returns to display when MAIN becomes healthy again

### 6. Burst-pressure / overflow test

Purpose:

- stress the RX rings and parser under heavy traffic

Method:

- run reconnect or active-display traffic with limited RX FIFO depth
- combine periodic status traffic with user actions such as repeated volume changes or preset changes

Expected result:

- stock builds show more persistent desync or `WAITING FOR DLCP` lockup
- `V1.62b` tolerates the same pressure better because of timeout and parser hardening

### 7. Two-main chain transient fault

Purpose:

- reproduce the field case where one bad MAIN strands the chain

Method:

- use the existing chain diagnoser topology
- stall `MAIN0` temporarily while CONTROL and the rest of the chain remain active

Expected result:

- stock can strand CONTROL in `WAITING FOR DLCP`
- `V2.5 + V1.62b` recovers once the delayed MAIN times out/resets and resumes forwarding/responding

### 8. Permanent no-main negative control

Purpose:

- ensure the robustness work does not hide a genuine missing-main condition

Method:

- keep MAIN absent or silent for the entire run

Expected result:

- all builds should still show `WAITING FOR DLCP`
- patched behavior should not fake a healthy display when no MAIN exists

## Required Measurements

Each runtime-fault test should record at least:

- whether `WAITING FOR DLCP` was seen
- time to first `WAITING FOR DLCP`
- total `WAITING FOR DLCP` dwell time
- whether the system recovered back to display
- time to recovery
- number of MAIN timeout/recovery/reset events
- CONTROL LCD timeline around the failure and recovery window

These metrics matter more than a simple pass/fail boolean because a patch may improve recovery without fully eliminating visible waiting.

## Recommended Test Matrix

Minimum required test coverage before release:

- stock `2.3 + 1.4` boot WAITING baseline
- stock `2.3 + 1.4` transient MAIN-response blackout
- stock `2.3 + 1.4` forced MAIN I2C-stall fault
- `V2.5 + V1.61b`
- `V2.5 + V1.62b`
- `V2.5 + V1.61b` transient MAIN-response blackout
- `V2.5 + V1.61b` forced MAIN I2C-stall fault
- `V2.5 + V1.61b` forced MAIN UART-TX stall
- `V2.5 + V1.61b` raw-main runtime timeout recovery
- `V2.5 + V1.61b` raw-main wake / reconnect timeout characterization
- `V2.5 + V1.62b` reconnect parser-fault test
- `V2.5 + V1.62b` burst-pressure / overflow test
- transient MAIN fault during active volume changes
- standby exit and reconnect
- long-run soak with repeated preset, input, and volume operations
- chained-unit scenario with one delayed or faulted MAIN
- permanent no-main negative control

## Pass Criteria

The release bars should be:

- stock baseline tests must reproduce `WAITING FOR DLCP` and remain stuck within the test budget
- `V2.5 + V1.61b` must recover from transient active-path MAIN timeout faults without entering permanent `WAITING FOR DLCP`
- current raw-main `gpsim` result shows `V2.5 + V1.61b` reconnecting after the induced wake fault is cleared; comparative reconnect robustness vs `V1.62b` still needs hardware validation
- the new shared external-I2C gpsim fault paths (`cfg71` address-phase SCL
  stretch, data-phase NACK, and bounded data-triggered SDA-low hold) each
  drive both `V2.4 + V1.61b` and `V2.5 + V1.61b` into `WAITING`, and both
  recover after the same fault is cleared or expires, so they are real shared
  stressors but not yet reproducers for the field-observed V2.4-only stranded
  case
- `V2.5 + V1.61b` must preserve all existing wire-visible semantics used by `V1.61b`
- `V2.5 + V1.62b` must recover faster and more consistently than `V2.5 + V1.61b` in reconnect/parser-fault scenarios
- the current raw-main `gpsim` result meets that wake / reconnect recovery bar for `V2.5 + V1.62b`
- permanent no-main tests must still remain in `WAITING FOR DLCP`

## Bottom Line

The most important design decision is not version numbering; it is release coupling.

`MAIN V2.5` should be built first as a wire-compatible robustness release that already works with existing `CONTROL V1.61b`.

`CONTROL V1.62b` should then add CONTROL-side timeout and parser hardening, but it must remain protocol-compatible with `V2.5` and should not be required to obtain the main reliability win.
