# V2.7 MAIN + V1.63b CONTROL — Implementation Status

Date: 2026-03-28
Status: superseded by V3.1 source rewrite (all deferred fixes now implemented inline in `dlcp_main_v31.asm`)

## Implemented and verified

| Fix | MCU | Where | Verified |
|-----|-----|-------|----------|
| A: ACKSTAT latch | MAIN V2.6+ | `patch_function_056_mode_bf` + `ackstat_first_byte_check` at 0x46BE | DSP deafness chain test: NACK detected, retry counter active |
| B: Conditional dirty clear | MAIN V2.6+ | `volume_dsp_write_v26` at 0x3E6C | Dirty bit kept during NACKs, 5-retry budget |
| B': Deferred volume commit | MAIN V2.6+ | NOP at 0x1D6E, commit in wrapper | Status RAM unchanged during NACKs |
| C: I2C bus-clear | MAIN V2.7 | 0x436C (function_072 dead zone, 54B) | Boot OK, called from wrapper max-retry path |
| E': BF/08 parser | CONTROL V1.63b | `bf08_check_stub` hooks 0x05D0 | Built, awaits Fix E |
| E'': Fault UI | CONTROL V1.63b | `volume_indicator_stub` shows "!" | Built, awaits Fix E |
| E''': Resync on clear | CONTROL V1.63b | Sets 0x0A0=0x4E on BF/08 data=0 | Built, awaits Fix E |

## Deferred (4 xfails)

| Fix | Bytes needed | Blocker |
|-----|-------------|---------|
| D: DSP ping | 26B | function_113 dead zone only 10B (label_606 at 0x48C6 live); function_111 zone only 12B (function_112 at 0x48A6 live) |
| E: BF/08 status TX | 24B | No dead zone remaining |
| F: PEN timeout hook | 20B | Boot hang when enhanced recovery runs without I2C devices; 12B at 0x489A too small for boot guard + bounded wait + stock fallback |
| Cascade recovery | — | Depends on Fix D |

## Why the wait loop repack failed

Codex-cli proposed a correct repack plan (shared seed/tick helpers, saving ~46B)
that would free 92 contiguous bytes at 0x55A0-0x55FB. The plan is sound but
blocked by gpasm's label resolution:

1. The V2.5 base ASM defines `function_113_patch` at `org 0x542A` which
   references `patch_wait_mssp_idle_c` (defined at `org 0x5500`).

2. The V2.7 composition replaces the `org 0x5500` section with repacked
   code. But the V2.5 base's reference at 0x542A is textually BEFORE
   the repacked definition. gpasm Error[113] "Symbol not previously
   defined" fires because gpasm cannot resolve forward references for
   `call` across `org` boundaries in this configuration.

3. Moving `function_113_patch` into the repacked region creates a
   cascade: `patch_function_056_core` (at `org 0x4970`) references
   `function_113_patch`, and is ALSO before the repacked region.
   Moving that creates further cascades.

4. The fundamental issue: the string-composition approach (V2.5 base +
   V2.6 replacements + V2.7 replacements) creates an ASM where code at
   multiple `org` addresses cross-references labels that aren't defined
   in text order. gpasm's 2-pass resolution doesn't handle this for
   `call`/`rcall` instructions.

## Path forward: V3.0 source rewrite

The correct solution is a from-scratch `.asm` source file where:
- All labels are defined before first use (or gpasm can resolve them)
- All wait loops, cores, and new code are in a single coherent block
- The binary patch builder is replaced by a full assembler invocation
- Space allocation is explicit and verified at build time

This eliminates the composition fragility and provides unlimited space
for Fix D/E/F plus future features.

## Test coverage

49 tests total: 30 passed, 19 xfailed, 0 failures.

V2.7 + V1.63b specific:
- 3 passed (bus-clear V2.3/V2.6/V2.7)
- 4 xfailed on V2.7 (D/E/F deferred)
- 4 xfailed on V2.6/V1.62b (expected: no D/E/F)

All existing V2.6 + V1.62b tests pass unchanged (33 tests).
