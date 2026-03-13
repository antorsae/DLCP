# MCU Target Correction (2026-03-11)

Status update (2026-03-12):

- the repo-local `gpsim-xtc` fork now supports `PIC18F25K20`
- CONTROL gpsim harnesses now select `p18f25k20` directly
- references below to the installed system `gpsim` lacking `p18f25k20` are historical context for why the fork was needed

Physical MCU inspection confirms:

- CONTROL board MCU: `PIC18F25K20`
- MAIN board MCU: `PIC18F2455`

This corrects earlier repo assumptions that treated CONTROL as `PIC18F2550-class`
and, in one later note, MAIN as `PIC18F2550`.

## Main Conclusions

### 1. MAIN `V2.5` remains valid

`V2.5` MAIN patching is still consistent with physical `PIC18F2455` hardware.

Why:

- the MAIN patch uses shared PIC18F2455/2550 SFRs and config addresses
- the patch lives inside the real application space used by stock `V2.3`
- the earlier bad `V2.5` hardware flash was caused by the separate MSSP-idle
  wait bug, not by the MCU-family targeting assumption

Result:

- treat MAIN as `PIC18F2455`
- MAIN builders and MAIN gpsim harnesses can now target `PIC18F2455` directly
- keep MAIN patch logic/release conclusions
- correct docs that previously promoted `PIC18F2550` as the MAIN target

### 2. CONTROL analysis was partly mislabeled

The old CONTROL disassembly was interpreted with `PIC18F2550` SFR names.
That is wrong for the real `PIC18F25K20`.

Important address block:

- `PIC18F2550` labels `0xF6C..0xF7F` as `USTAT/UCON/UADDR/UCFG/UEP0..UEP15`
- `PIC18F25K20` maps this region to `SSPMSK/SLRCON/CM2CON1/CM2CON0/CM1CON0/WPUB/IOCB/ANSEL/ANSELH`

Implication:

- old CONTROL claims about "USB endpoint" or "USB guard" behavior in this
  region are really claims about analog/comparator/PORTB-change configuration
- CONTROL standby/wake and button/IR analysis remains broadly useful, but any
  interpretation of the `0xF6C..0xF7F` block must be redone under the
  `PIC18F25K20` map

Concrete example from startup:

- in stock CONTROL startup, writes previously labeled as clearing `UEP10`,
  `UEP11`, `UEP14`, `UEP15` are, on `PIC18F25K20`, actually clearing
  `CM2CON0`, `CM1CON0`, `ANSEL`, `ANSELH`

### 3. CONTROL patched artifacts are still safe

The CONTROL patch builders were retargeted to `PIC18F25K20`.

Rebuilt artifacts:

- `firmware/patched/releases/DLCP_Control_V1.61b.hex`
- `firmware/patched/releases/DLCP_Control_V1.62b.hex`

Safety result:

- the `V1.62b` patch stub assembles to byte-identical output under
  `PIC18F25K20` and `PIC18F2550` headers
- this is expected because the patch code touches only shared SFRs such as
  `RCSTA`, `PIE1`, `SPBRG`, `EEADR`, `EEDATA`, `EECON1/2`, `INTCON`

Meaning:

- CONTROL patch artifacts were not invalidated by the earlier wrong target
  header
- the builder target is now corrected to match the real silicon

### 4. CONTROL gpsim now has an exact target path

At the time of the original correction note, the installed system `gpsim`
binary did **not** support `p18f25k20`.

That gap is now closed by the repo-local `gpsim-xtc` fork under
`vendor/gpsim-0.32.1-xtc/`, with build outputs under
`artifacts/tools/gpsim-xtc/`.

Result:

- CONTROL instruction-level simulation can now run on the exact
  `PIC18F25K20` target through `gpsim-xtc`
- the old `p18f2550` surrogate-model limitation no longer applies to current
  CONTROL gpsim runs
- remaining chain/reconnect gaps are now concentrated in MAIN-side simulation
  fidelity, especially Timer3/native-ring behavior

## Regenerated Practical Conclusions

1. MAIN `V2.5` conclusions still stand.
2. `V1.62b` remains a valid release candidate at the firmware-artifact level.
3. The strongest claim we can make for CONTROL is:
   - real patch bytes are safe and correctly targeted now
   - current CONTROL gpsim execution now uses the exact `PIC18F25K20` model
   - any remaining reconnect uncertainty is now about MAIN-side simulation
     shims and hardware validation, not CONTROL processor targeting
4. Any future deep CONTROL static analysis should use `PIC18F25K20` register
   naming, especially around:
   - `0xF6C..0xF7F`
   - comparator setup
   - `ANSEL/ANSELH`
   - `IOCB/WPUB`
