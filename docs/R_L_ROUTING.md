# DLCP R-L Routing Extension

Focused design and implementation guide for extending DLCP channel routing with
a new `R-L` mode while preserving stock behavior for existing modes.

## Status

`R-L` is **not implemented** in the current patched releases. This document
captures confirmed routing behavior and concrete patch instructions.

## Scope

- MAIN firmware command/decoder path for source routing (`cmd 0x17..0x1C`).
- CONTROL firmware UI/command emission path for source options.
- Test and verification requirements to prevent regressions.

## Current Routing Behavior

### Command surface

Channel source commands are:

| Channel | Cmd | Source byte (MAIN RAM) |
|---------|-----|-------------------------|
| CH1 | `0x17` | `0x0A5` |
| CH2 | `0x18` | `0x0A6` |
| CH3 | `0x19` | `0x0A7` |
| CH4 | `0x1A` | `0x0A8` |
| CH5 | `0x1B` | `0x0A9` |
| CH6 | `0x1C` | `0x0AA` |

Dispatch compare chain is in
`firmware/disasm/main/gpdasm_output.asm:2428` onward.

### MAIN decode semantics

`function_078` maps source value -> selector pair (left_coef_sel, right_coef_sel):
`firmware/disasm/main/gpdasm_output.asm:8613`.

| Source value | User meaning | Selector pair |
|--------------|--------------|---------------|
| `0` | `L` | `(1,0)` |
| `1` | `R` | `(0,1)` |
| `2` | `L+R` | `(2,2)` |
| `3` | `L-R` | `(1,3)` |

Selector -> coefficient conversion in apply path:
`firmware/disasm/main/gpdasm_output.asm:3128`.

| Selector | Coefficient |
|----------|-------------|
| `0` | `0.0` (via conversion routine) |
| `1` | `+1.0` (via conversion routine) |
| `2` | `+0.5` (`0x3F000000`) |
| `3` | `-1.0` (`0xBF800000`) |

This means:
- `L+R` is implemented as `+0.5*L + +0.5*R`.
- `L-R` is implemented as `+1.0*L + -1.0*R`.

### Per-channel selector storage slots

Selector pair output slots are not fully linear across channels:

| Channel | Left selector slot | Right selector slot |
|---------|--------------------|---------------------|
| CH1 | `0x0D7` | `0x0D8` |
| CH2 | `0x0DB` | `0x0DC` |
| CH3 | `0x0DF` | `0x0E0` |
| CH4 | `0x1D9` | `0x1DA` |
| CH5 | `0x0E4` | `0x0E5` |
| CH6 | `0x1E0` | `0x1E1` |

Write sites are in `function_008` at
`firmware/disasm/main/gpdasm_output.asm:2927` through `:2970`.

### Observed behavior for out-of-range source value `4`

Current firmware command handlers (`cmd 0x17..0x1C`) write incoming source
bytes into all six source mirrors `0x0A5..0x0AA`
(`firmware/disasm/main/gpdasm_output.asm:2300`,
`firmware/disasm/main/gpdasm_output.asm:2312`,
`firmware/disasm/main/gpdasm_output.asm:2324`,
`firmware/disasm/main/gpdasm_output.asm:2336`,
`firmware/disasm/main/gpdasm_output.asm:2348`,
`firmware/disasm/main/gpdasm_output.asm:2360`).

So `data=4` can be latched for any channel, but decode has no explicit case for
`4`, so it falls through to the default selector pair `(0,1)`, effectively
behaving like `R` during apply.

### Startup sanitizer behavior

Startup/source sanitizer clamps source values to `<=3` in
`firmware/disasm/main/gpdasm_output.asm:2604` onward.

Known oddity:
- `firmware/disasm/main/gpdasm_output.asm:2648` writes `0x64` instead of
  `0x65` in the CH6 clamp branch (`cmd 0x1C` path mirror), which can leave CH6
  unsanitized in some cases.

## CONTROL Source Option Context

### Existing source labels in stock control

All stock control variants already contain four source labels:
`Left`, `Right`, `L+R`, `L-R`.

| Firmware | Source label table start |
|----------|--------------------------|
| V1.4 | `0x16D0` |
| V1.5b | `0x16C2` |
| V1.6b | `0x15E2` |

### Existing source option count limits

Source option max is currently `3` (four options `0..3`):

| Firmware | Address | Current literal |
|----------|---------|-----------------|
| V1.4 | `0x17E8` | `movlw 0x03` |
| V1.5b | `0x17DA` | `movlw 0x03` |
| V1.6b | `0x16FA` | `movlw 0x03` |

## Target `R-L` Semantics

Define new source value `4` as:

- `R-L = -1.0*L + +1.0*R`
- selector pair `(3,1)`

This is the exact algebraic opposite of existing `L-R` (`(1,3)`).

## Implementation Instructions

## 1) MAIN firmware changes (required)

1. Extend source decode to handle value `4` explicitly.
   - For value `4`, output selector pair `(3,1)`.
   - Keep values `0..3` byte-for-byte equivalent in behavior.
2. Keep unknown/out-of-range handling deterministic.
   - Recommended: clamp to `0` or `1` explicitly instead of silent fallthrough.
3. Extend startup sanitizer max from `3` to `4` for all CH source bytes.
4. Fix CH6 sanitizer typo:
   - Change `movwf 0x64` to `movwf 0x65` in CH6 clamp branch
     (`firmware/disasm/main/gpdasm_output.asm:2648`).

Practical patch approach:
- Prefer a dedicated stub hook from apply callsite
  (`firmware/disasm/main/gpdasm_output.asm:2921`, call to `function_078`) to
  avoid tight in-place edits in stock function body.
- Ensure no overlap with existing AB preset stub region (`0x5400..0x55FF`).

## 2) CONTROL firmware changes (menu-enabled builds)

For variants with setup source editing (V1.41 and V1.51b):

1. Increase source option max from `3` to `4` at the addresses listed above.
2. Add fifth source label `R-L` after existing `L-R`.
3. Ensure source enum mapping remains:
   - `0: Left`, `1: Right`, `2: L+R`, `3: L-R`, `4: R-L`.
4. Ensure USBaudio option table remains separate and unshifted.

For V1.61b:
- No front-panel setup menu path for source editing; host-command path still
  must accept `data=4` once MAIN is extended.

## 3) Verifier updates

Update static verifier checks (`src/dlcp_fw/patch/verify_presets_ab.py`) to
assert:

- MAIN decoder hook/stub bytes for `R-L` case are present.
- MAIN sanitizer now allows `0..4`.
- CH6 sanitizer fix is present.
- CONTROL source max literal changed only in intended builds/addresses.

## Regression Test Plan

## MAIN semantic tests

Add gpsim tests that validate selectors and effective routing for all channels:

1. `cmd 0x17..0x1C` with data `0..4`.
2. Assert selector slots for each channel:
   - CH1 `0x0D7/0x0D8`
   - CH5 `0x0E4/0x0E5`
   - CH6 `0x1E0/0x1E1`
3. Assert value `4` maps to `(3,1)` exactly.
4. Assert values `0..3` remain unchanged from stock/patched baseline.

## MAIN persistence/sanitizer tests

1. Preload EEPROM source bytes with `4`, boot, assert source mirrors remain `4`.
2. Preload invalid values (`5`, `0xFF`), boot, assert deterministic clamp.
3. Explicit CH6 invalid test to prove sanitizer typo fix is effective.

## CONTROL emission tests

For V1.41 and V1.51b:

1. Navigate setup source options and select `R-L`.
2. Assert emitted frames are unchanged except new `data=4` value.
3. Verify display label for `data=4` is `R-L`.

For V1.61b:

1. Inject host command `cmd 0x17..0x1C data=4`.
2. Verify no parser regressions and correct frame/response behavior.

## Cross-version parity checks

Run full suite for all patched release lines:

- `DLCP_Control_V1.41` + MAIN `V2.4`
- `DLCP_Control_V1.51b` + MAIN `V2.4`
- `DLCP_Control_V1.61b` + MAIN `V2.4`

## Risks and Notes

1. **Numeric headroom**: `L-R`/`R-L` use full-scale +/-1 mix and may clip if
   both channels are hot; this is unchanged from existing `L-R`.
2. **Host UI mismatch**: If HFD UI does not expose value `4`, raw command path
   can still support it.
3. **No DSP silicon simulation**: gpsim validates firmware routing math and
   register writes, not analog audio output.

## Quick checklist

- [ ] MAIN decode supports value `4 -> (3,1)`.
- [ ] MAIN sanitizer allows `0..4`.
- [ ] CH6 sanitizer typo fixed.
- [ ] CONTROL source menu supports value `4` where applicable.
- [ ] Verifier asserts new patch invariants.
- [ ] Regression suite passes across V1.41/V1.51b/V1.61b.
