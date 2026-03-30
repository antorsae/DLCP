# DLCP Reanalysis Corrections (2026-02-16)

Migration note (2026-03-30): path names in this historical correction log use
the pre-migration layout. Map `disasm/...` to `firmware/disasm/...`,
`patched/...` to `firmware/patched/releases/...`, builder/verification modules
to `src/dlcp_fw/patch/...`, and script entrypoints to `scripts/...`.

## Corrected Findings

1. **Main current-loop command `0x1F` is not free/unused.**
- In `firmware/disasm/main/gpdasm_output.asm`, command decode around `0x1E48..0x1E6A` includes an existing handler branch for `0x1F`.
- Preset patch uses new command `0x20` specifically to avoid collision.

2. **Main MCU physical target is `PIC18F2455`, not `PIC18F2550`.**
- Physical inspection confirms the MAIN board MCU is `PIC18F2455`.
- The earlier temporary switch to `PIC18F2550` was a tooling assumption, not a hardware confirmation.
- The MAIN patch remains valid because the patch uses shared `18F2455/2550` SFR/config layouts relevant to the current hooks.

3. **Control firmware `function_036` original `0x1E` data path is not a clean A/B channel already.**
- Original code at `0x0C72` transmits cmd `0x1E`.
- Original data mapping block at `0x0C84..0x0C8E` transforms zero into `0x03`, not true boolean.
- For presets this was patched to explicit `0/1` mapping before transmit.

4. **Control submenu value for `USBaudio` is per-DLCP slot by default, not global.**
- Original save path at `0x1964..0x196C` writes only `0x0E5[0xBA]`.
- Preset behavior requires chain-wide sync, so this was patched to mirror one value into `0x0E5..0x0EA`.

5. **Some Python analysis scripts contain speculative/incorrect conclusions and are not authoritative.**
- Example: `dsp_comm_analysis.py` prints speculative DSP guesses inconsistent with known TAS3108 hardware.
- Example: several scripts infer semantics from pattern-matching without validating against control-flow.
- Disassembly-level verification should remain primary.

6. **Control MCU physical target is `PIC18F25K20`, not `PIC18F2550`.**
- Physical inspection confirms the CONTROL board MCU is `PIC18F25K20`.
- Earlier CONTROL disassembly labels in the `0xF6C..0xF7F` range were therefore interpreted with the wrong SFR names.
- CONTROL patch builders are now retargeted to `PIC18F25K20`.
- The repo-local `gpsim-xtc` fork now supports `p18f25k20`, so current CONTROL gpsim runs can use the real target. Older surrogate-model results should be treated as historical.

## Verified Technical Baselines

- Main preset table logical A range: `0x5600..0x5FFF` (`0xA00` bytes).
- Control V1.4 large free code area exists from about `0x1AFA` upward; patch stubs placed at `0x7000+`.
- Control menu string tables are fixed 16-byte entries:
  - menu labels at `0x1660`
  - two-option table at `0x1710`.

## Resulting Patch Artifacts

- `firmware/patched/releases/DLCP_Firmware_V2.31.hex`
- `firmware/patched/releases/DLCP_Control_V1.41.hex`
- Build scripts:
  - `src/dlcp_fw/patch/build_main_presets_ab.py`
  - `src/dlcp_fw/patch/build_control_presets_ab.py`
- Validation:
  - `src/dlcp_fw/patch/verify_presets_ab.py`
  - `scripts/sim_presets_ab.py`
