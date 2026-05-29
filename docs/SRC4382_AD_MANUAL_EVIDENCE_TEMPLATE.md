# SRC4382 Auto Detect Manual Evidence Template

Use this template to record the manual hardware evidence required to close
`BUG-SRC4382-AD-01`.  Save the completed report as:

```text
artifacts/probes/v171_v32_ledger_gate/bug_src4382_ad_01_manual_evidence.md
```

Closure requires a `pass` verdict with the current canonical V1.71 CONTROL and
both current canonical V3.2 MAIN revisions and SHA256 hashes explicitly
confirmed, fixed-input audio including fixed digital source selection after
Auto Detect, Auto Detect audio, user actions, soak duration, and `I`/`R` growth
all explicitly accounted for.
`n/a` is acceptable only for optional captures.

Before closing the ledger, run:

```bash
.venv_ep0/bin/python scripts/validate_src4382_manual_evidence.py \
  artifacts/probes/v171_v32_ledger_gate/bug_src4382_ad_01_manual_evidence.md
```

## Date/Time

-

## Firmware

CONTROL: V1.71 / rev 0x37 / build 20260529

CONTROL SHA256: 49d59a819f06df9458519d4b488675ffcf4194bd5ddf410980a154b1ac51f7d4

CONTROL flashed/running V1.71? yes/no:

MAIN PB1: V3.2 / rev 0x71

MAIN PB1 SHA256: 2c5945184b3a849a910e46c31fd1113e00b481f8b1ce5c3de3604cfc16a15e36

MAIN PB1 visible/running V3.2? yes/no:

MAIN PB2: V3.2 / rev 0x71

MAIN PB2 SHA256: 2c5945184b3a849a910e46c31fd1113e00b481f8b1ce5c3de3604cfc16a15e36

MAIN PB2 visible/running V3.2? yes/no:

## Test Setup

Source/input:

Preset:

Volume:

Audio material or measurement used for low-band check:

## Fixed-Input Playback

Normal low-band output? yes/no:

Fixed digital sources tested after Auto Detect (S/PDIF, USB Audio, AES, Optical as available):

Any fixed digital source silent? yes/no:

Notes:

## Auto Detect Playback

Selected same source? yes/no:

Normal low-band output? yes/no:

Notes:

## User Actions While Playing

Volume responsive? yes/no:

Mute/unmute responsive? yes/no:

Preset A/B responsive and audio correct after switch? yes/no:

Standby/wake responsive and both MAINs recover? yes/no:

Explicit input selection responsive? yes/no:

## Soak

Auto Detect no-source duration >= 30 min? yes/no, duration:

Fixed-input playback duration >= 1 h? yes/no, duration:

UI stalls observed? yes/no:

Volume A/B badge pulsing or abnormal LCD refresh observed? yes/no/details:

Unexplained I/R growth observed? yes/no:

PB1 before/after diag I/R:

PB2 before/after diag I/R:

I/R growth explanation if any:

## Optional Captures

Audio capture / SPL / RTA:

SCL/SDA capture:

Probe logs:

## Verdict

Pass/fail:

Remaining concerns:
