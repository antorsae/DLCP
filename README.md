# DLCP Firmware V3.5 + V1.73

Community replacement firmware for the **Hypex DLCP** (Digital Loudspeaker
Control Processor).  It is a drop-in upgrade for the stock firmware, flashed
over the DLCP's own USB port — no programmer needed.

A DLCP system has one **CONTROL** unit (front panel: LCD, buttons, IR
receiver) and one or two **MAIN** boards (`PB1`/`PB2`, e.g. left and right
speaker).  You flash two files:

| Unit | File | Identity |
|---|---|---|
| MAIN (each board) | [`firmware/patched/releases/DLCP_Firmware_V3.5.hex`](firmware/patched/releases/DLCP_Firmware_V3.5.hex) | `V3.5 / rev 0x009B` |
| CONTROL (front panel) | [`firmware/patched/releases/DLCP_Control_V1.73.hex`](firmware/patched/releases/DLCP_Control_V1.73.hex) | `V1.73 / rev 0x63 / build 20260702` |

```text
SHA-256
7238d08cacf32f25358cf1a83d86984cb7c1d454ce46051bafe56acc3eed1071  DLCP_Firmware_V3.5.hex
9a28543e99ff1806a470826283323e9438a29dd6a4aa6917a27152a1631c2ee1  DLCP_Control_V1.73.hex
```

The stock firmware (MAIN **V2.3** + CONTROL **V1.6b**, the baseline for every
comparison below) was reverse-engineered, rebuilt as maintainable assembly
source, hardened against its real-world failure modes, and extended with A/B
presets, per-board input selection, and live diagnostics.  Every release is
validated in a cycle-accurate simulator before it goes near hardware.

- **What do I gain?** → [Why upgrade](#why-upgrade--what-you-gain-over-stock)
- **How do I flash it?** → [Quick flash guide](#quick-flash-guide)
- **Why is it more reliable?** → [Robustness vs stock](#robustness-vs-stock--what-was-broken-and-how-it-was-fixed)
- **Older releases** (V2.4–V3.4, V1.41–V1.72) → [docs/RELEASE_ARCHIVE.md](docs/RELEASE_ARCHIVE.md)

## Why upgrade — what you gain over stock

### It stops hanging

The stock pair's best-known failure: the display wedges on `WAITING FOR DLCP`
— or volume/mute/input silently stop responding — and only a power cycle
recovers it.  V3.5 + V1.73 bound every wait, recover from every bus/UART fault
they can, report the ones they can't, and even then give you a way out: if
CONTROL is ever stuck on a waiting screen for ~10 s, pressing **LEFT** or
**RIGHT** soft-resets it without pulling power.  Details and mechanisms are in
[Robustness vs stock](#robustness-vs-stock--what-was-broken-and-how-it-was-fixed).

### Two DSP tunings, switchable from the couch (A/B presets)

Stock holds one DSP configuration; changing tunings means a PC and Hypex
Filter Design.  V3.5 stores **two complete DSP preset banks** and lets you
switch instantly:

- **Preset screen** on CONTROL (UP/DOWN selects A or B); the active letter is
  shown on the screen, and the loaded configuration's **filename** scrolls on
  the second line so you can see *which* tuning is active, not just a letter.
- **IR shortcuts** — see the [remote table](#a-more-useful-ir-remote) below.
- In a two-board system the switch is **coordinated**: both MAINs mute,
  switch, verify, and unmute together, so left and right never audibly change
  one after the other.
- A preset change can never half-apply: the DSP coefficient image is validated
  row-by-row and audio stays muted until the selected image is proven.

The release flasher compiles the two presets from your Hypex Filter Design
FilterData XML and bakes them in at flash time (this repo's defaults are
LX521.4 tunings — see the flash guide).

### Independent inputs for two-board systems

Stock CONTROL broadcasts **one global input selection** to all boards.  In the
common master/follower wiring (PB2 fed from PB1 over the RJ45/AES link),
selecting `Optical` forces *both* boards to their local optical receivers —
and the follower goes silent.

V1.73 adds separate `Input PB1` and `Input PB2` menu pages.  PB2 defaults to
`Same as PB1` (stock-like linked behavior); selecting a concrete PB2 source
makes the boards independent.  The recommended tandem setup:

```text
Input PB1: Auto Detect   # or the real external source, e.g. Optical
Input PB2: AES           # the link from PB1
```

Both choices persist in CONTROL EEPROM across power cycles (give it ~5 s
after a change before switching off).  The full menu order becomes
`Volume → Preset → Input PB1 → Input PB2 → Setup → PB1 Diag → PB2 Diag`.

### The front panel, mapped

Six buttons: **UP, DOWN, LEFT, RIGHT, SELECT, STBY**.  LEFT/RIGHT move
between pages (wrapping in both directions); UP/DOWN and SELECT act on the
current page.  Stock V1.6b has three pages (`Volume → Input → Setup`);
Preset, per-board input selection, and both Diagnostics pages are new.

This is the exact 16x2 LCD flow captured from a two-MAIN simulation using the
canonical V1.73 CONTROL and V3.5 MAIN images.  Follow the arrowheads with
**RIGHT**; **LEFT** traverses the same ring in reverse:

```text
┌────────────────┐ → ┌────────────────┐ → ┌────────────────┐ → ┌────────────────┐
│Volume:-17.0dB A│   │Preset         A│   │Input PB1:      │   │Input PB2:      │
│Auto Detect     │   │521.4 22MG10F-v5│   │Auto Detect     │   │Same as PB1     │
└────────────────┘   └────────────────┘   └────────────────┘   └────────────────┘
        ▲                                                               │
        │                                                               ▼
┌────────────────┐ ← ┌────────────────┐ ← ┌────────────────┐ ←──────────┘
│PB2 OK v3.5 009B│   │PB1 OK v3.5 009B│   │Setup           │
│O1              │   │O1              │   │BL Timeout      │
└────────────────┘   └────────────────┘   └────────────────┘
```

The values are one clean power-on example: volume and source follow saved
settings, and `O1` is normal power-on-reset context, not a fault.  The Preset
row shows one 16-character window of the active FilterData name; longer names
scroll.  Before PB2 has ever replied there is one `Input:` page and no separate
`Input PB2:` entry.  Discovery renames it `Input PB1:` and inserts the PB2 input
page for the rest of that CONTROL session.  The two Diagnostics pages remain
available so an absent, old, or lost PB can still be inspected.

| Page | Shows | UP / DOWN | SELECT |
|---|---|---|---|
| `Volume` | Volume in dB (or blinking `Mute`), PB1 source, link health, active preset letter (`!` if DSP fault) | Volume in 1 dB steps (also unmutes) | Toggle mute |
| `Preset` | Active preset A/B, link-health glyph; second line: the loaded config's filename, scrolling | UP = preset A, DOWN = preset B | — |
| `Input PB1` | PB1 source | Cycle: Auto Detect · S/PDIF · USB Audio · AES · Optical · Analogue 1–4 | — |
| `Input PB2` | PB2 source (title shows `old`/`lost` if PB2 stops reporting) | Same list plus `Same as PB1` (default) | — |
| `Setup` | `BL Timeout` | — | Enter/leave the timeout editor |
| `PB1 Diag` / `PB2 Diag` | Live health per board: `PBn OK v3.5 NNNN`, issue counters, reset causes (park ~1 s to populate) | — | — |

V1.73 exposes one Setup item.  SELECT opens its editor; UP/DOWN cycles the four
actual LCD values, and LEFT/RIGHT returns to the surrounding page ring:

```text
┌────────────────┐   SELECT   ┌────────────────┐
│Setup           │ ─────────→ │BL Timeout      │
│BL Timeout      │            │30 sec          │
└────────────────┘            └────────────────┘
                                  UP / DOWN
                                      ↕
                Off (no timeout) ↔ 30 sec ↔ 2 min ↔ 5 min ⟲
```

Outside the page ring:

- **STBY** puts the system into standby (`Zzz...`).  Any front-panel button —
  or the IR wake — wakes it; the display shows `Waiting for DLCP` until the
  boards answer.
- **Boot:** splash (`Firmware V1.73` / `Rev x63 20260702`) →
  `Waiting for DLCP` → `Volume`.
- **Waiting-screen escape:** stuck for ~10 s → LEFT or RIGHT soft-resets
  CONTROL (no power cycle).
- **Bootloader** (for flashing): power-cycle while holding UP + DOWN ~6 s →
  `Bootloader mode`.

### A more useful IR remote

All stock RC5 handling (volume, mute, input) is preserved.  On top of it,
these commands are recognized (Hypex remote profile, RC5 address `0x10`;
a plain-RC5 profile is also selectable):

| Remote key | RC5 cmd | Action |
|---|---|---|
| F1 | `0x38` | Select preset A |
| F2 | `0x39` | Select preset B |
| F4 | `0x3D` | Toggle preset A/B (held-key repeat suppressed) |
| F5 | `0x3F` | Toggle PB1 input between S/PDIF and Optical |
| — | `0x3A` | Force standby (explicit, not a toggle) |
| — | `0x3B` | Force wake (explicit, not a toggle) |

The explicit standby/wake commands are ideal for home-automation senders
(e.g. a Flipper or programmable remote): they are idempotent, so blindly
sending "wake" is always safe.

### You can see what it's doing

Stock gives you no fault feedback at all.  The new pair adds:

- **DSP fault flag:** if a MAIN detects a persistent DSP-path fault it says
  so; CONTROL shows `!` on the display and resynchronizes when it clears.
- **Diagnostics pages** (`PB1 Diag` / `PB2 Diag` at the end of the menu):
  per-board live health refreshed ~1 Hz while buttons/IR stay responsive.
  A healthy page shows that board's firmware identity, e.g.
  `PB1 OK v3.5 009B`.  Status forms: `PBn OK` (healthy), `PBn! …` (issue
  counters non-zero), `PBn old` (stale data), `PBn lost` (no data), `n/a`
  (MAIN too old to report).
- **Counters** on the diag pages tell you *why*: `I` I2C/bus recoveries,
  `D` DSP fault episodes, `S`/`B` standby/wake dispatches, `R` recovery
  branches, `A` AN0 standby triggers, and reset causes `O`/`V`/`W`/`X`
  (power-on / brownout / watchdog / software).
- **USB tools** for deeper inspection:

```bash
.venv_ep0/bin/python scripts/dlcp_diag.py --json --watch --interval 1   # counters, reset causes, SRC/DSP forensics
.venv_ep0/bin/python scripts/dlcp_src4382_diag.py                      # digital receiver: lock, source, sample rate, PCM vs non-PCM
```

### Smarter digital input handling

Stock Auto Detect can flap on a transient receiver blip, and manually
selecting a digital input could leave the receiver path in a stale state.
V3.5 rate-limits Auto Detect polling, debounces source-loss (a ~1 s blip no
longer drops the route), treats a locked-but-idle receiver as "hold the
route" rather than "source lost", and re-primes the receiver/DSP path
whenever you pick a fixed input.  A detect/re-detect cycle can never write a
louder-than-set master volume.

### Small comforts

- **No pop when flashing:** firmware updates mute the DSP and drop the amp
  rails gracefully before resetting.  Stock resets cold and pops.
- **Settings survive updates:** the flasher snapshots volume/input/setup
  before flashing and restores them after.
- **Identity everywhere:** the flasher prints device identity before/after;
  the CONTROL boot splash shows `Firmware V1.73` + `Rev x63 20260702`; the
  diag pages show each MAIN's version live.

## Quick flash guide

**Order: MAIN board(s) first, CONTROL last.**  CONTROL is flashed *through* a
MAIN over the speaker link, and the safe relay handshake needs MAIN V3.5.

### One-time setup

```bash
git clone https://github.com/antorsae/DLCP.git
cd DLCP

# Install uv if needed (Homebrew also fine: brew install uv)
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

uv venv .venv_ep0 --python 3.12
uv pip install --python .venv_ep0/bin/python -e .

# sanity check
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --help
```

Notes:

- Close Hypex Filter Design (or anything else holding the DLCP USB device).
- Linux: you need HID access to VID `0x04D8` PID `0xFF89` (udev rule or run
  with sufficient privileges).

### Preset data (required for MAIN V3.5)

The V3.5 flasher **bakes the A/B presets from Hypex Filter Design FilterData
XML at flash time** and refuses to flash without them (no silent unbaked
firmware).  Place your HFD 4.97 FilterData exports at:

```text
artifacts/LX521.4/FilterData/LX521.4 22MG10F-v5/Config.xml   # becomes preset A
artifacts/LX521.4/FilterData/LX521.4 22MG10F-v8/Config.xml   # becomes preset B
```

These default names/checksums are this repo's LX521.4 deployment.  For other
speakers, supply your own FilterData via the lower-level flasher's
`--filterdata-*` options (`scripts/dlcp_main_flash.py --help`).

### Step 1 — Flash the MAIN board(s) → V3.5

Identify which USB device is which board first (USB enumeration order is
**not** a safe role selector):

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
export LEFT_HID='<hid path reported for LEFT/PB1>'
export RIGHT_HID='<hid path reported for RIGHT/PB2>'
```

Then preflight (no USB writes) and flash, one board at a time:

```bash
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --path "$LEFT_HID"  --left  --preflight-only
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --path "$LEFT_HID"  --left

.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --path "$RIGHT_HID" --right --preflight-only
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --path "$RIGHT_HID" --right
```

Single-board system: you can omit `--path`; the tool auto-selects only when
exactly one matching MAIN is visible.  If `identify-mains` cannot classify
your boards (fresh/unusual routing), connect one board at a time and take the
path from `scripts/hardware_state_test.py detect`.

The flasher automatically: probes identity and warns on same/newer firmware
(no silent downgrade), verifies the preset tables' SHA-256 before any USB
write, never touches the bootloader region, enters flash mode pop-free,
CRC-verifies the written image, restores your volume/input/setup settings,
applies all-channel L/R routing, writes the preset A/B names, and sets the IR
profile (`hypex` default; `--profile rc5` for standard remotes).  If the
post-flash step is interrupted, re-run with `--finalize-only`.

### Step 2 — Flash the CONTROL panel → V1.73

1. Put CONTROL into its bootloader: **power-cycle while holding UP + DOWN for
   about 6 seconds** (do not press SELECT).  If the LCD comes back to the
   Volume screen it is still in the app — try again.
2. Preflight, then flash (relayed through a MAIN's USB port):

```bash
# One MAIN visible: the wrapper auto-selects it.
scripts/flash_control_safe.sh --preflight-only
scripts/flash_control_safe.sh

# Two MAINs visible: pass the MAIN physically wired to CONTROL (normally LEFT/PB1).
scripts/flash_control_safe.sh --path "$LEFT_HID" --preflight-only
scripts/flash_control_safe.sh --path "$LEFT_HID"
```

3. Power-cycle once after flashing so V1.73 starts from a cold boot.

The wrapper defaults to the canonical V1.73 hex, refuses to write if the
image's bootloader region differs from the trusted stock reference, streams
only the application window, CRC-verifies the result, and aborts immediately
with guidance if the relay was not armed (MAIN V3.5 detects a missed
bootloader handshake instead of letting the flash "succeed" and then fail).

### Step 3 — Verify

```bash
.venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$LEFT_HID"  --info-only   # expect V3.5 rev 0x009B
.venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$RIGHT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py     --path "$LEFT_HID"  --info-only   # active preset + config name
.venv_ep0/bin/python scripts/dlcp_diag.py --json                                  # counters + reset causes
```

On CONTROL: the boot splash shows `Firmware V1.73` / `Rev x63 20260702`, and
the `PB1 Diag` / `PB2 Diag` pages show each MAIN as `PBn OK v3.5 009B`.

### Alternative: Hypex Filter Design

HFD can stream the same two HEX files as a plain firmware update (for
CONTROL, enter the bootloader manually as above first).  But HFD skips
everything the CLI does around the flash: no preset baking, no L/R routing,
no IR profile, no settings preservation, no identity/CRC verification.  Use
the CLI path for real deployments.

### If something goes wrong

- **CONTROL flash interrupted / timed out:** the device stays in its
  bootloader.  Re-enter the bootloader (UP + DOWN power-cycle) and re-run the
  same `flash_control_safe.sh` command.
- **MAIN post-flash finalize interrupted:** re-run the release flasher with
  `--finalize-only`.
- **Worst case** (interrupted MAIN app flash and no USB): recovery needs a
  PICkit programmer — see [docs/RECOVERY.md](docs/RECOVERY.md).  Don't flash
  what you can't recover.

## Robustness vs stock — what was broken and how it was fixed

Stock V2.3 + V1.6b fails in specific, reproducible ways.  Each one below was
root-caused in the disassembly, fixed at the mechanism level, and pinned with
regression tests.

| Symptom on stock | Root cause | Fix in V3.5 + V1.73 |
|---|---|---|
| `WAITING FOR DLCP` forever; only a power cycle recovers | CONTROL's boot and reconnect paths poll in **infinite loops** with no timeout, hidden behind two blind banner delays (~14 s + ~11 s of dead UI) | Closed-loop reconnect driven by a fresh MAIN status reply; the blind delays were deleted; waiting screens keep servicing IR; after ~10 s stuck, LEFT/RIGHT soft-resets CONTROL |
| Volume/mute/input dead while the display stays alive | MAIN has **11 unbounded I2C busy-waits**; a stuck DSP/receiver bus spins the CPU forever | Every I2C wait has a time budget; on timeout: MSSP reset → 9-clock bus-clear to free a stuck slave → DSP ping; the incident is counted and reported |
| Whole board freezes mid-operation | UART transmit spins forever on a hardware flag | Bounded TX with an escalation ladder: retry → force-mute + degraded flag → controlled soft reset (mute asserted first) |
| Buttons/remote ignored after changing a setting | EEPROM writes block interrupts ~4 ms → guaranteed UART overrun → stock's overrun handler **permanently desyncs** the 3-byte frame parser | Overrun recovery drains the FIFO and re-enables reception without losing frame position; a gap watchdog resyncs on real mid-frame stalls; RX rings drop-oldest instead of corrupting unread data |
| Remote flaky while the panel is busy | RC5 IR decode runs ~10 ms **inside the interrupt handler** and shares scratch RAM with the foreground LCD code | The ISR saves/restores the shared scratch set; decoding no longer corrupts foreground state |
| Speakers stay silent after standby | Wake is a single fire-and-forget frame; a board that misses it stays deaf until power cycle | Wake is re-broadcast at wake-gate entry, duplicate wakes are idempotent, and mute state re-converges automatically within ~2 health polls |
| Loud pop on every firmware update | Flash entry is a bare `RESET` that tristates the amp-control pins in one instruction cycle | Flash entry mutes the DSP, drops the secondary rail, settles ~100 ms, then resets |
| No fault feedback of any kind | Fire-and-forget protocol: no acknowledgements, no checksums, no fault path | DSP faults are latched and advertised; CONTROL shows `!` and resyncs on clear; every recovery increments a visible counter |

### How the fixes were accomplished

1. **Reverse engineering.**  The stock MAIN and CONTROL images were
   disassembled and annotated instruction-by-instruction into a semantic
   function map ([docs/analysis/](docs/analysis/SEMANTIC_FUNCTION_MAP.md)),
   which is where the failure modes above were found — the infinite polls,
   the unbounded waits, the destructive overrun handler.
2. **Binary patches first (V2.4–V2.8 / V1.41–V1.64b).**  The earliest fixes
   were surgical patches on the stock binaries: bounded timeouts, DSP
   acknowledge checks, bus-clear + ping recovery, fault advertisement, UART
   overrun recovery.  They proved the mechanisms on hardware but were cramped
   into spare flash bytes.
3. **Full source rewrite (V3.0 / V1.7).**  Both firmwares were rebuilt as
   assembly source that assembles **byte-identical to stock** — proving the
   source is a faithful reconstruction before changing anything.
4. **Feature lines on that source (V3.1+ / V1.71+).**  All fixes moved
   inline into maintainable source with semantic labels and shared RAM
   definitions.  This is what makes the deeper fixes possible at all:
   transaction-owned preset application, phased wake sequencing, ISR scratch
   isolation — none of which fit in a binary patch.
5. **Guard rails on every build.**  Canonical build scripts bump the
   revision, rebuild, and refuse to publish unless a static RAM-bank safety
   checker passes; regression tests include *semantic guards* that scan the
   built HEX for specific instruction patterns (for example, the exact opcode
   that caused a standby regression in an early patch can never reappear
   unnoticed).

Two deliberate design rules run through all of it: **no unbounded wait
anywhere** (a watchdog timer is intentionally left off — it would convert
hangs into mystery resets instead of fixing their causes; bounded waits plus
an explicit recovery ladder do, see [docs/ROBUSTNESS.md](docs/ROBUSTNESS.md)),
and **never unmute on an unproven DSP image** (audio safety beats speed
everywhere the two conflict — preset APPLY validates every coefficient row,
skips the volume rows, and unmutes only after the image is verified).

### How it's tested

The whole system runs in a **cycle-accurate Rust PIC18 simulator**
([crates/dlcp-sim/](crates/dlcp-sim/), [docs/SIMULATION.md](docs/SIMULATION.md))
that executes the *actual release HEX images* of both MCUs together with
TAS3108 DSP and SRC4382 receiver models in a single clock domain.  On top of
it:

- **~2,175 simulator tests**, written red-first (the failing test exists
  before the fix), run on every release:
  `.venv_ep0/bin/python -m pytest tests/sim -n 16 -q`.
- A **fault-injection matrix** drives every diagnostics counter from stimulus
  (stuck I2C line, brownout, UART burst, DSP NACK…) through the MAIN counter,
  the link protocol, and the CONTROL cache to the rendered LCD.
- **Exploratory campaigns** inject randomized IR/button/USB/fault sequences
  for hours and flag any divergence between the boards' audio state for
  adversarial triage; confirmed findings become deterministic regression
  tests.
- **Live hardware gates** on a two-MAIN LX521.4 rig (standby/wake soak, A/B
  switching, IR sweeps, reflash pop checks) close each release —
  [docs/HARDWARE_TEST.md](docs/HARDWARE_TEST.md).

## Current status

- Simulator gate: `2175 passed` (2026-07-02) on the released pair; RAM-bank
  safety OK for both images.
- The current pair is fully sim-verified but **not yet field-closed on live
  hardware** for: PB2 DOWN behavior, multi-board audio routing, input
  persistence, the IR field gates, and the test-robustness incident list.
  Run the hardware gates in
  [docs/HARDWARE_TEST.md](docs/HARDWARE_TEST.md) before treating those as
  hardware-proven.
- Per-revision change history lives in the git log and
  [docs/RELEASE_ARCHIVE.md](docs/RELEASE_ARCHIVE.md).

## For developers

Repository layout, canonical paths, and operational commands are in
[AGENTS.md](AGENTS.md).  Quick pointers:

- **Build the releases:** `scripts/build_v35_release.py` (MAIN),
  `scripts/build_v173_release.py` (CONTROL) — each bumps the revision,
  updates identity literals, runs RAM-bank safety, and republishes the
  canonical HEX.  Source: `src/dlcp_fw/asm/dlcp_main_v35.asm`,
  `src/dlcp_fw/asm/dlcp_control_v173.asm`.
- **Dev environment** (simulator + tests):

```bash
uv pip install --python .venv_ep0/bin/python -e ".[dev]"
PYO3_PYTHON="$PWD/.venv_ep0/bin/python" cargo build --release -p dlcp-sim-py
bash crates/dlcp-sim-py/build.sh

# smoke test: boot the full CONTROL+MAIN chain to the Volume screen
PYTHONPATH=src .venv_ep0/bin/python -c "from dlcp_fw.paths import V173_CONTROL_HEX, V35_MAIN_HEX; from dlcp_fw.sim.dlcp_sim_native import Chain; c = Chain.from_v171_v32(control_hex_path=str(V173_CONTROL_HEX), main_hex_path=str(V35_MAIN_HEX)); c.run_until_connected(limit=200); print(c.lcd_lines())"
```

- **Test gates:** full `tests/sim -n 16 -q`; focused
  `-k "v35 or v173 or v34 or v33 or v32"`.
- **Key docs:** [docs/ROBUSTNESS.md](docs/ROBUSTNESS.md) (findings + policy),
  [docs/V32_DIAG_TIER1_SPEC.md](docs/V32_DIAG_TIER1_SPEC.md) (diagnostics
  protocol), [docs/PRESET_FILENAME_LCD_SPEC.md](docs/PRESET_FILENAME_LCD_SPEC.md)
  (preset/filename UI), [docs/V34_FIELD_BUGS_20260610.md](docs/V34_FIELD_BUGS_20260610.md)
  (field-incident ledger), [docs/SIM_REWRITE_RUST_SPEC.md](docs/SIM_REWRITE_RUST_SPEC.md)
  (simulator design), [docs/TEST_ROBUSTNESS_IMPL.md](docs/TEST_ROBUSTNESS_IMPL.md)
  (test-robustness gates).
- Working in a git worktree: symlink `artifacts/LX521.4` from the base
  checkout so the FilterData XML is visible (see AGENTS.md).

## Disclaimer

**NO WARRANTY, EXPRESS OR IMPLIED.**  The Hypex DLCP is end-of-life hardware.
This firmware is a community bugfix, not a supported product.  Use it entirely
at your own risk.

Recovery from a bad flash may require a PICkit programmer and direct MCU
recovery ([docs/RECOVERY.md](docs/RECOVERY.md)).  Do not flash these images
unless you are comfortable with PIC firmware recovery.
