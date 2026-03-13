# MAIN AN0 Standby Trace

Date: 2026-03-09
Scope: MAIN firmware static analysis only
Primary source: `firmware/disasm/main/gpdasm_output.asm`

## Summary

MAIN uses `RA0 / AN0` as a dedicated analog standby/wake sense input.

It is not a generic ADC measurement. The same AN0 path is used in two places:

- a boot/wake gate that waits until the ADC sample is high enough
- a runtime monitor with hysteresis that can request standby when the sample drops

This AN0 path feeds the same internal standby event machinery used by CONTROL `cmd=0x03` standby commands. It also drives the `BF 03 <0|1>` standby state reported back to CONTROL.

What static analysis proves:

- `AN0` is the only configured ADC channel
- AN0 participates directly in standby/wake behavior
- MAIN uses three threshold values around `0x0228..0x0236`
- CONTROL `WAITING FOR DLCP` can be caused by AN0 faults during wake/standby handling

What static analysis does not prove:

- the exact board-level net wired into `RA0 / AN0`
- whether every observed field `WAITING FOR DLCP` hang is actually caused by AN0

## ADC Configuration

Boot-time hardware init configures the ADC as follows:

- `TRISA = 0x07` at `0x356E`, so `RA0..RA2` are inputs
- `ADCON0 = 0x01` at `0x3580`
- `ADCON1 = 0x0C` at `0x3584`
- `ADCON2 = 0xB5` at `0x3588`

References:

- `firmware/disasm/main/gpdasm_output.asm:356E`
- `firmware/disasm/main/gpdasm_output.asm:3580`
- `firmware/disasm/main/gpdasm_output.asm:3584`
- `firmware/disasm/main/gpdasm_output.asm:3588`

For PIC18F2455/2550-class devices, `ADCON0=0x01` means:

- ADC enabled
- channel select `CHS=0000`
- selected input = `AN0`

No code was found that switches to a different ADC channel later.

## Threshold Table

| Context | Compare | Decimal | Approx. %FS | Approx. V at 5 Vref | Meaning | Code |
|---|---:|---:|---:|---:|---|---|
| Boot/wake wait | `>= 0x0236` | 566 | 55.3% | 2.77 V | MAIN may complete wake/bring-up | `0x2DBC..0x2DC6` |
| Runtime high arm | `>= 0x0229` | 553 | 54.1% | 2.70 V | Arm high-state latch `0x94.bit2` | `0x418E..0x4198` |
| Runtime low trip | `< 0x0228` | 552 | 53.9% | 2.70 V | Clear active bit `0x5E.bit3`, raise standby event `0x7E.bit2` | `0x41A0..0x41AC` |

Notes:

- The runtime path implements 1-count hysteresis around `0x0228/0x0229`.
- The simulator uses `0x0230` as a stable logical-high sample and `0x0220` as a stable logical-low sample to straddle this threshold band.
- The gpsim boot hook writes `0x0237` as an above-threshold surrogate, which matches the boot gate behavior.

References:

- `firmware/disasm/main/gpdasm_output.asm:2DBC`
- `firmware/disasm/main/gpdasm_output.asm:418E`
- `firmware/disasm/main/gpdasm_output.asm:41A0`
- `src/dlcp_fw/sim/manifests.py:795`
- `src/dlcp_fw/sim/chain_gpsim.py:102`

## Shared Standby State Bits

The AN0 path does not operate in isolation. It feeds a small internal state machine:

- `0x5E.bit3`: MAIN active/standby state bit
- `0x7E.bit2`: standby event request
- `0x94.bit2`: runtime AN0 high-state latch
- `0xA1`: debounce / dwell counter for runtime ADC monitoring

Two key facts:

1. `0x5E.bit3` is the state exported to CONTROL as `BF 03 <0|1>`.
2. `0x7E.bit2` is the event bit consumed by the wake/standby dispatcher.

References:

- `firmware/disasm/main/gpdasm_output.asm:3BCC`
- `firmware/disasm/main/gpdasm_output.asm:4796`
- `firmware/disasm/main/gpdasm_output.asm:416E`

## Full Call Trace

### 1. Boot path initializes AN0 and forces first wake gate

During startup, MAIN enables ADC on AN0, sets `0x5E.bit3`, and jumps into `function_024`:

- `0x35EA`: `bsf (Common_RAM + 94), 0x3`
- `0x35EC`: `goto function_024`

This means boot always passes through the AN0 gate before normal operation continues.

References:

- `firmware/disasm/main/gpdasm_output.asm:35EA`
- `firmware/disasm/main/gpdasm_output.asm:35EC`

### 2. `function_024` is the boot/wake ADC gate

`function_024`:

- disables `GIE`
- starts ADC conversion on AN0
- waits for conversion completion
- reads `ADRESH:ADRESL` into `0x89:0x88`
- loops until sample is at least `0x0236`

Key sequence:

- `0x2D96`: start conversion
- `0x2DA2`: if `GO` still set, skip result handling
- `0x2DA6..0x2DB8`: capture 10-bit ADC result
- `0x2DBC..0x2DC6`: compare against `0x0236`
- `0x2DC6`: `bnc label_341` loops again if below threshold

After threshold is met, the function continues wake/bring-up work:

- serial clock/baud selection
- GPIO state setup
- further initialization

References:

- `firmware/disasm/main/gpdasm_output.asm:2D8C`
- `firmware/disasm/main/gpdasm_output.asm:2D96`
- `firmware/disasm/main/gpdasm_output.asm:2DA6`
- `firmware/disasm/main/gpdasm_output.asm:2DBC`
- `firmware/disasm/main/gpdasm_output.asm:2DD2`

### 3. CONTROL standby commands feed the same state machine

CONTROL STBY commands arrive as `cmd=0x03` subcommands. In MAIN dispatch:

- `data=0x00` reaches `label_155`
- `data=0x01` reaches `label_154`

These handlers operate on the same two bits used by the ADC path:

- `label_155` drives standby request by clearing `0x5E.bit3` and setting `0x7E.bit2` when MAIN was active
- `label_154` drives wake request by setting `0x5E.bit3` and `0x7E.bit2` when MAIN was in standby

This is why AN0 faults and CONTROL STBY commands converge on the same downstream handling.

References:

- `firmware/disasm/main/gpdasm_output.asm:1CFC`
- `firmware/disasm/main/gpdasm_output.asm:1C9A`
- `firmware/disasm/main/gpdasm_output.asm:1C7E`

### 4. Main service loop periodically checks standby events and AN0 runtime state

The periodic service function is `function_102`:

- call `function_100`
- run other maintenance
- jump to `label_529`

`label_529` is the runtime AN0 monitor.

References:

- `firmware/disasm/main/gpdasm_output.asm:47CE`
- `firmware/disasm/main/gpdasm_output.asm:47DA`
- `firmware/disasm/main/gpdasm_output.asm:47E2`

### 5. `label_529` implements runtime AN0 hysteresis

Runtime ADC logic only runs when `0x5E.bit3` is set:

- `0x416E`: if `0x5E.bit3` clear, return immediately

Then:

- `0x4172..0x4176`: require `0xA1 == 0x64` before evaluating the ADC result
- `0x4178`: if conversion still running, skip result handling
- `0x417C..0x418C`: read AN0 sample into `0x89:0x88`
- `0x418E..0x4198`: if sample `>= 0x0229`, set `0x94.bit2`
- `0x419A`: start next conversion
- `0x419C`: if latch not armed, return
- `0x41A0..0x41A8`: if sample is still `>= 0x0228`, return
- `0x41AA..0x41AC`: otherwise clear `0x5E.bit3` and set `0x7E.bit2`

So the runtime monitor does not immediately force a wake. It requests standby by raising the same event bit used by the command path.

References:

- `firmware/disasm/main/gpdasm_output.asm:416E`
- `firmware/disasm/main/gpdasm_output.asm:418E`
- `firmware/disasm/main/gpdasm_output.asm:419C`
- `firmware/disasm/main/gpdasm_output.asm:41AA`

### 6. `function_100` consumes standby event `0x7E.bit2`

`function_100` is the event dispatcher:

- if `0x7E.bit2` is clear, nothing happens
- if `0x7E.bit2` is set and `0x5E.bit3` is set, it calls `function_024`
- if `0x7E.bit2` is set and `0x5E.bit3` is clear, it calls `function_051`
- then it clears `0x7E.bit2`

That gives the exact wake/standby split:

- `bit3 = 1` + event => wake/bring-up path
- `bit3 = 0` + event => standby/power-down path

References:

- `firmware/disasm/main/gpdasm_output.asm:4796`
- `firmware/disasm/main/gpdasm_output.asm:479C`
- `firmware/disasm/main/gpdasm_output.asm:47A0`
- `firmware/disasm/main/gpdasm_output.asm:47A6`
- `firmware/disasm/main/gpdasm_output.asm:47AA`

### 7. `function_051` is the standby-side handler

`function_051` performs standby-side work:

- sends `function_093` operations with subcommands `0x1B`, `0x1C`, `0x1D`
- changes serial clock/baud and related pins
- compares last AN0 value against `0x0228`
- executes further output and timing shutdown logic
- finally jumps to `function_116`

Important consequence:

- this function performs peripheral traffic before the final low-power/output-off stage
- if MAIN hangs here, logical standby can be requested without full analog/DSP/amp shutdown completing

References:

- `firmware/disasm/main/gpdasm_output.asm:3C0C`
- `firmware/disasm/main/gpdasm_output.asm:3C24`
- `firmware/disasm/main/gpdasm_output.asm:3C48`
- `firmware/disasm/main/gpdasm_output.asm:3C7E`

### 8. MAIN reports standby state back to CONTROL

MAIN status response path `function_103` emits:

- `BF`
- `03`
- `01` if `0x5E.bit3` is set
- `00` if `0x5E.bit3` is clear

References:

- `firmware/disasm/main/gpdasm_output.asm:3BCC`
- `firmware/disasm/main/gpdasm_output.asm:3BD2`
- `firmware/disasm/main/gpdasm_output.asm:3BD4`

This is the state CONTROL uses during connect/reconnect logic.

## Why AN0 Can Lead To `WAITING FOR DLCP`

### Case A: boot/wake gate never completes

If AN0 stays below `0x0236` during `function_024`, MAIN never completes wake/bring-up. CONTROL keeps polling and eventually shows `WAITING FOR DLCP`.

This is a real AN0-originating `WAITING` path.

### Case B: runtime AN0 falsely trips low

If AN0 briefly drops below the runtime low threshold after having armed high, MAIN clears `0x5E.bit3` and raises `0x7E.bit2`. That forces the standby-side path on the next service cycle.

If CONTROL is polling during that transition, it can observe `BF 03 00` or missing responses and enter standby/reconnect behavior.

### Case C: AN0 event plus standby-side hang

This is the most important mixed-failure case.

If AN0 falsely requests standby but MAIN hangs inside `function_051` before shutdown side effects finish, CONTROL can be driven toward `WAITING FOR DLCP` while the audio path may still be physically active.

This matches the general pattern:

- CONTROL thinks the unit is no longer ready
- MAIN does not complete the expected standby/wake handshake
- DSP/amp shutdown may not have completed yet

AN0 alone does not prove this field symptom, but AN0 plus a MAIN blocking wait can produce it.

## Why `WAITING FOR DLCP` Does Not Necessarily Mean Real Standby Happened

CONTROL can enter `WAITING FOR DLCP` from reconnect logic, not only from a true STBY button sequence.

The key CONTROL-side nuance is documented in:

- `docs/analysis/SIMULATION_STDBY_WAIT_DIAGNOSIS.md`

That matters because:

- `WAITING FOR DLCP` on the LCD does not by itself prove MAIN completed a real standby transition
- it may instead reflect missing/inconsistent status during reconnect

So if audio keeps playing normally while CONTROL says `WAITING FOR DLCP`, the best static interpretation is:

- pure AN0 thresholding is probably not the whole story
- either MAIN never really completed standby
- or CONTROL entered reconnect/wait logic due to transport/state mismatch
- or AN0 triggered the event, then MAIN hung before shutdown side effects completed

## Practical Conclusions

1. `RA0 / AN0` is definitively part of the standby/wake mechanism.
2. The boot threshold is `0x0236`.
3. The runtime hysteresis band is `0x0229` / `0x0228`.
4. AN0 faults can cause `WAITING FOR DLCP`, especially around wake.
5. `WAITING FOR DLCP` while audio continues playing implies either:
   - CONTROL reconnect logic without true standby completion, or
   - AN0-triggered standby request combined with a MAIN-side hang before shutdown completed
6. This makes AN0 a real contributor to wake/standby failures, but not the best standalone explanation for all field hangs.
