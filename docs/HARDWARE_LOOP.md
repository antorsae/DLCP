# DLCP Hardware-In-The-Loop Runbook

## Scope

This document is the executable runbook for real-hardware DLCP DSP testing with:

- DLCP USB HID for MAIN firmware flashing
- DLCP USB audio output as `USB Audio DAC`
- `UMIK-2` as the measurement microphone

Current release guidance:

- stock `V2.3-combined.hex` remains a useful known-good acoustic baseline
- canonical `V3.1.hex` with baked preset captures is the current recommended
  deployed MAIN release
- suspect local `V3.1` experiments are compared against those good references;
  they are not canonical release images
- `V3.1_diag_memread_usb_safe.hex` and related `V3.1_diag*` images are optional
  local diagnostic artifacts only

For the operator flashing workflow, use [`docs/V31_RELEASE.md`](V31_RELEASE.md).
This runbook is for acoustic characterization and regression isolation.

This runbook is written for a blank-context LLM agent. It assumes nothing
beyond the repository checkout, the connected hardware, and the commands below.

## Canonical Execution Environment

Use the virtual environment Python for every command in this workflow:

```bash
.venv_ep0/bin/python
```

Do not use system Python for the hardware-loop workflow. The venv already has
the HID and plotting dependencies needed by the new CLI.

The canonical hardware-loop entrypoint is:

```bash
.venv_ep0/bin/python scripts/hardware_loop.py
```

Available subcommands:

- `detect`
- `probe-playback`
- `probe-capture`
- `gen-sweep`
- `analyze`
- `run-once`
- `run-matrix`

## What The CLI Does

`scripts/hardware_loop.py` provides the pieces that were previously only
described in this repo:

- resolves input devices by name, not by fragile AVFoundation index
- resolves the output device by name through `SwitchAudioSource`
- generates a logarithmic sweep WAV plus JSON sidecar
- records from `UMIK-2`
- plays through `USB Audio DAC`
- deconvolves stimulus/capture into an impulse response and magnitude trace
- writes machine-readable metrics and a plot
- optionally flashes a firmware image before measurement
- when flashing with `--capture-a`, it bakes preset A into app flash, writes the
  active filename slot after flashing, and verifies the preset A flash window
  via EP0
- rejects short AVFoundation captures and retries with more pre-roll before
  playback so truncated host captures do not masquerade as firmware DSP faults

Important workflow rule:

- do not use `scripts/dlcp_main_flash.py --capture-a ...` as the primary
  measurement workflow
- use `scripts/hardware_loop.py run-once` or `run-matrix` instead

Reason:

- `dlcp_main_flash.py --capture-a` is now usable across supported versions
- when firmware exposes HID `cmd 0x43`, it performs an in-firmware diag-memread verify
- when firmware does not expose `cmd 0x43`, it warns and skips that verify path
- `hardware_loop.py` uses a version-neutral finalize path:
  - flash app bytes
  - write filename via stock `cmd03`
  - verify preset A flash bytes via EP0
  - then run playback/capture/analyze in the same command

## Required Inputs

These files must exist before the matrix run starts:

- `presetA.bin`
- `presetA.json`

Expected release images:

- `firmware/stock/main/DLCP Firmware V2.3-combined.hex`
- `firmware/patched/releases/DLCP_Firmware_V3.1.hex`

Optional local suspect images:

- any non-canonical `V3.1` experiment hex you explicitly want to compare
- `firmware/patched/releases/DLCP_Firmware_V3.1_diag_memread_usb_safe.hex`
  only when the test explicitly targets that diagnostic variant

## Hard Preconditions

Before any measurement or flash:

- close HFD
- close any other program using the DLCP HID interface
- keep the DLCP connected over USB
- keep `UMIK-2` connected directly to the host
- do not move the mic during a comparison block

If HFD is left open, either flashing or audio capture may fail in non-obvious
ways. Treat that as an invalid run.

## Device Detection

Run this first:

```bash
.venv_ep0/bin/python scripts/hardware_loop.py detect --json
```

Pass condition:

- one audio output named `USB Audio DAC`
- one audio input named `UMIK-2`
- at least one DLCP HID device in `app` or `bootloader` mode

The command reports:

- current macOS input device
- current macOS output device
- input/output channel counts
- current sample rate for each audio device
- AVFoundation input indices
- DLCP HID mode and product string

Do not hard-code `UMIK-2` as AVFoundation `:1` in any automation. The tool
already resolves the mic by name.

## Sample-Rate Policy

The tool supports mismatched stimulus and capture rates, but blank-agent runs
must be explicit.

Use this rule:

1. read the `USB Audio DAC` sample rate from `detect`
2. if it is `44100`, run playback stimulus at `44100`
3. if it is `48000`, run playback stimulus at `48000`
4. keep `UMIK-2` capture at `48000`

The analyzer will resample the capture onto the stimulus sample rate before
deconvolution.

Recommended explicit settings on this host, based on the verified inventory:

- stimulus sample rate: `44100`
- capture sample rate: `48000`

Capture timing rule:

- the hardware-loop tool now uses a larger default pre-roll before playback and
  verifies that the recorded WAV is long enough to contain the requested sweep
- if a run still reports a short capture after retries, treat that as a host
  capture failure and do not draw any firmware conclusion from it

If Audio MIDI Setup is used to force the DAC to `48000`, update the commands
below accordingly.

## Host Sanity Checks

### Playback probe

```bash
.venv_ep0/bin/python scripts/hardware_loop.py probe-playback \
  --output-device "USB Audio DAC" \
  --wav artifacts/probes/hardware_loop/dlcp_probe.wav
```

Expected behavior:

- the script switches output to `USB Audio DAC`
- plays the probe WAV once
- restores the previous output device

### Capture probe

```bash
.venv_ep0/bin/python scripts/hardware_loop.py probe-capture \
  --input-device "UMIK-2" \
  --duration 1.0 \
  --sample-rate 48000 \
  --channels 2 \
  --out artifacts/probes/hardware_loop/umik_probe.wav
```

Expected behavior:

- a valid WAV is written
- the capture is not empty

If either probe fails, stop. That is a host-audio problem, not a firmware
problem.

## Output Layout

All automated runs live under:

```text
artifacts/probes/hardware_loop/
├── fw/
└── runs/
```

Each `run-once` or `run-matrix` measurement creates a run directory:

```text
artifacts/probes/hardware_loop/runs/<timestamp>_<tag>/
```

Minimum contents per run:

- `firmware.hex`
- `firmware.json`
- `stimulus.wav`
- `stimulus.json`
- `capture.wav`
- `response_ir.wav`
- `response_mag.csv`
- `response_mag.png`
- `metrics.json`
- `run.json`
- `notes.txt`

`run-matrix` also writes:

- `summary.json`

## First Characterization Block

Before any broader matrix, do this exact two-point characterization first:

1. flash stock `V2.3`, bake `presetA.bin`, run the sweep at amplitude `0.2`
2. flash canonical `V3.1`, bake the exact same `presetA.bin`, run the exact
   same sweep
3. compare the second run against the first run
4. only after both runs are acoustically sane, add suspect local images

Signal quality rule for this host:

- `--amplitude 0.5` can fall below the SNR needed for stable comparisons
- prefer `--amplitude 1.0` when the goal is discriminating firmware behavior
  rather than keeping playback conservative

Comparison-band rule:

- `run-once` and `run-matrix` now default the pass/fail comparison band to the
  actual sweep band from the generated or supplied stimulus manifest
- override with `--compare-min-hz` / `--compare-max-hz` only when you
  intentionally want the pass/fail band to differ from the sweep

The first run must establish that the acoustic measurement itself is healthy.
The second run must establish that the current release image is acoustically
close to the known-good baseline on the same hardware and mic placement.

## Exact Baseline Command

This is the canonical known-good baseline run:

```bash
.venv_ep0/bin/python scripts/hardware_loop.py run-once \
  --tag v23_baseline \
  --hex "firmware/stock/main/DLCP Firmware V2.3-combined.hex" \
  --capture-a presetA.bin \
  --input-device "UMIK-2" \
  --output-device "USB Audio DAC" \
  --sample-rate 44100 \
  --capture-sample-rate 48000 \
  --amplitude 0.2
```

What this does:

1. bakes `presetA.bin` into the app flash image
2. flashes the resulting MAIN image
3. writes the active config filename via stock `cmd03`
4. verifies the preset A flash window at `0x5600`
5. generates a default log sweep
6. captures the acoustic response
7. analyzes the response
8. writes the artifacts listed above

Optional route normalization:

```bash
.venv_ep0/bin/python scripts/hardware_loop.py run-once \
  --tag v23_allch_l \
  --hex "firmware/stock/main/DLCP Firmware V2.3-combined.hex" \
  --capture-a presetA.bin \
  --all-ch L \
  --input-device "UMIK-2" \
  --output-device "USB Audio DAC" \
  --sample-rate 44100 \
  --capture-sample-rate 48000 \
  --amplitude 0.2
```

Only use `--all-ch L` or `--all-ch R` if the whole comparison block uses the
same route policy. Do not normalize only one side of a comparison.

## Exact Release-Reference Comparison Command

Run this immediately after the `V2.3` baseline, without moving the microphone:

```bash
.venv_ep0/bin/python scripts/hardware_loop.py run-once \
  --tag v31_release_reference \
  --hex firmware/patched/releases/DLCP_Firmware_V3.1.hex \
  --capture-a presetA.bin \
  --input-device "UMIK-2" \
  --output-device "USB Audio DAC" \
  --sample-rate 44100 \
  --capture-sample-rate 48000 \
  --amplitude 0.2 \
  --baseline-csv artifacts/probes/hardware_loop/runs/<v23_baseline_run>/response_mag.csv
```

Expected result:

- `decision` should be `GO`
- `classification` should usually be `PASS_MATCHES_BASELINE` or
  `PASS_NEAR_BASELINE`

If this run does not come back `GO`, do not start testing suspect local
variants yet. Fix the measurement setup or the release image first.

## Exact Matrix Command

This is the canonical firmware-comparison matrix:

```bash
.venv_ep0/bin/python scripts/hardware_loop.py run-matrix \
  --tag v23_v31_release_matrix \
  --capture-a presetA.bin \
  --input-device "UMIK-2" \
  --output-device "USB Audio DAC" \
  --sample-rate 44100 \
  --capture-sample-rate 48000 \
  --amplitude 0.2 \
  --hex "firmware/stock/main/DLCP Firmware V2.3-combined.hex" \
  --hex firmware/patched/releases/DLCP_Firmware_V3.1.hex \
  --hex <local_suspect_v31_a.hex> \
  --hex <local_suspect_v31_b.hex>
```

Behavior:

- each candidate is baked with the same `presetA.bin`
- each candidate is flashed before its measurement
- the first run is stock `V2.3` and becomes the baseline for the remaining runs
- the second run is canonical `V3.1` and serves as the release reference
- each later run is compared against the baseline `response_mag.csv`

If per-driver near-field measurements are required, rerun the same matrix with a
different `--tag` and a different physical mic position.

## Default Stimulus

Unless an explicit stimulus is supplied, `run-once` and `run-matrix` generate:

- logarithmic sine sweep
- `20 Hz` to `20 kHz`
- `4.0 s` sweep length
- `0.5 s` pre-roll silence
- `1.0 s` post-roll silence
- `0.2` amplitude
- stereo output

The generated files are:

- `stimulus.wav`
- `stimulus.json`

If you want to pre-generate the sweep explicitly:

```bash
.venv_ep0/bin/python scripts/hardware_loop.py gen-sweep \
  --out artifacts/probes/hardware_loop/reference/default_sweep_44k1.wav \
  --json-out artifacts/probes/hardware_loop/reference/default_sweep_44k1.json \
  --sample-rate 44100
```

Then use it in later runs:

```bash
.venv_ep0/bin/python scripts/hardware_loop.py run-once \
  --tag v23_reuse_stimulus \
  --hex "firmware/stock/main/DLCP Firmware V2.3-combined.hex" \
  --capture-a presetA.bin \
  --stimulus artifacts/probes/hardware_loop/reference/default_sweep_44k1.wav \
  --manifest artifacts/probes/hardware_loop/reference/default_sweep_44k1.json \
  --input-device "UMIK-2" \
  --output-device "USB Audio DAC" \
  --capture-sample-rate 48000 \
  --amplitude 0.2
```

## Analysis Outputs

The analyzer:

- mixes stereo capture to mono by default
- resamples capture to the stimulus sample rate when needed
- deconvolves stimulus and capture into an impulse response
- computes a smoothed log-frequency magnitude trace
- writes CSV, PNG, and JSON metrics

Standalone analysis command:

```bash
.venv_ep0/bin/python scripts/hardware_loop.py analyze \
  --stimulus <run_dir>/stimulus.wav \
  --manifest <run_dir>/stimulus.json \
  --capture <run_dir>/capture.wav \
  --out-dir <run_dir>/reanalyze
```

Baseline comparison form:

```bash
.venv_ep0/bin/python scripts/hardware_loop.py analyze \
  --stimulus <candidate_run>/stimulus.wav \
  --manifest <candidate_run>/stimulus.json \
  --capture <candidate_run>/capture.wav \
  --baseline-csv <baseline_run>/response_mag.csv \
  --out-dir <candidate_run>/reanalyze
```

## Machine Decision Rules

The analyzer writes both `classification` and top-level `decision` into
`metrics.json`.

These are the actual thresholds used by the tool.

### Capture validity

`FAIL_CAPTURE_INVALID` if either condition is true:

- capture peak reaches clip threshold
- signal-to-noise ratio is below `10 dB`

### Comparison against baseline

The comparison band is `100 Hz .. 10 kHz`.

`PASS_MATCHES_BASELINE` if:

- `compare_rms_db <= 3.0`
- and `abs(compare_mean_db) <= 3.0`

`PASS_NEAR_BASELINE` if:

- `compare_rms_db <= 6.0`
- and `abs(compare_mean_db) <= 6.0`

`FAIL_LOW_LEVEL` if:

- `compare_mean_db <= -12.0`

`FAIL_SHAPE_MISMATCH` otherwise.

If no baseline is supplied and the capture is valid, the classification is:

- `VALID_NO_BASELINE`

Top-level decision mapping:

- `GO` for `VALID_NO_BASELINE`, `PASS_MATCHES_BASELINE`,
  `PASS_NEAR_BASELINE`
- `NOGO` for `FAIL_CAPTURE_INVALID`, `FAIL_LOW_LEVEL`, `FAIL_SHAPE_MISMATCH`

## Human Interpretation Rules

Treat the machine classification as the first pass, not the only pass.

Use this interpretation:

- `PASS_MATCHES_BASELINE`
  - candidate is acoustically equivalent to the known-good baseline for this
    mic position
- `PASS_NEAR_BASELINE`
  - candidate is close enough to the baseline that the regression is probably
    not in this firmware delta
- `FAIL_LOW_LEVEL`
  - candidate is globally attenuated relative to baseline
  - this is consistent with the earlier “only UM, low volume” reports
- `FAIL_SHAPE_MISMATCH`
  - candidate is not simply quieter; the spectral shape differs
  - suspect routing, partial band loss, wrong DSP state, or wrong active path
- `FAIL_CAPTURE_INVALID`
  - the run is unusable and must not be used for firmware conclusions
- `GO`
  - the run is acceptable as either a valid baseline capture or a
    baseline-matching candidate
- `NOGO`
  - the run is either invalid or materially different from the good baseline

## Firmware Decision Logic

Run the matrix in this order:

1. `DLCP Firmware V2.3-combined.hex`
2. `DLCP_Firmware_V3.1.hex`
3. one or more explicit suspect local `V3.1` experiment hexes

Interpretation:

If step 1 passes and step 2 passes:

- the measurement chain is healthy
- the current release image is acoustically aligned with the known-good baseline

If step 2 fails:

- stop
- do not interpret any suspect-image result until the release reference path is fixed

If step 2 passes and a suspect local image fails:

- the regression is in the suspect delta, not in the release baseline
- narrow investigation to the code changes unique to that suspect image

If step 2 passes and a suspect local image also passes:

- that suspect delta is probably not the acoustic regression boundary
- move to the next suspect image or refine the experiment boundary

If a suspect image changes only routing or level materially:

- suspect route policy, preset placement, or DSP load completeness before
  assuming a lower-level timing fault

## Per-Driver Near-Field Procedure

Use this when a candidate is audible only from one path or one band.

For each physical driver/output path:

1. keep the firmware and sweep unchanged
2. move the mic to a repeatable near-field position
3. rerun `run-once` with a tag naming the driver
4. do not compare runs taken from different mic positions directly

Example:

```bash
.venv_ep0/bin/python scripts/hardware_loop.py run-once \
  --tag v31_stockbf_midwoofer_nearfield \
  --hex firmware/patched/releases/DLCP_Firmware_V3.1_diag_stock_bf.hex \
  --capture-a presetA.bin \
  --input-device "UMIK-2" \
  --output-device "USB Audio DAC" \
  --sample-rate 44100 \
  --capture-sample-rate 48000 \
  --amplitude 0.2
```

The tag must carry the physical measurement context because the tool cannot
infer mic placement.

## Failure Handling

If `detect` cannot find `UMIK-2` or `USB Audio DAC`:

- stop and fix the host audio topology

If `detect` shows the DLCP only in `bootloader` mode:

- flashing can still proceed
- do not start audio-only measurements until the device returns to `app`

If a run returns `FAIL_CAPTURE_INVALID`:

- check that HFD is closed
- rerun `probe-playback`
- rerun `probe-capture`
- confirm the mic position and that the room is not excessively noisy
- rerun the same firmware once before moving on

If a run clips:

- reduce the sweep amplitude with `--amplitude`

If the DAC sample rate differs from the command you planned to use:

- either change the DAC rate manually in Audio MIDI Setup
- or rerun with the explicit `--sample-rate` matching the detected DAC rate

## What A Successful Campaign Leaves Behind

A successful campaign should produce a `summary.json` that makes the firmware
boundary obvious:

- `V2.3` baseline classification
- canonical `V3.1` release-reference classification
- the first suspect local image that diverges materially from the two good
  references

That is the point at which the firmware investigation should narrow to the code
delta unique to that boundary, not continue as a broad search through flash
contents or simulation-only state.
