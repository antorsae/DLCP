# DLCP Firmware: V3.5 MAIN + V1.73 CONTROL

Drop-in replacement firmware for the **Hypex DLCP**.  The current
non-hardware-gated candidate pair is:

- MAIN: [`firmware/patched/releases/DLCP_Firmware_V3.5.hex`](firmware/patched/releases/DLCP_Firmware_V3.5.hex) (`V3.5 / rev 0x0090`)
- CONTROL: [`firmware/patched/releases/DLCP_Control_V1.73.hex`](firmware/patched/releases/DLCP_Control_V1.73.hex) (`V1.73 / rev 0x53 / build 20260622`)

CONTROL `rev 0x53` includes the PB2 `Same as PB1` + `DOWN` fix, the
follow-up BF/08 ACKSTAT-only stale-`!` fix found by the broad simulator gate,
and persistent PB2 input settings with `Same as PB1` as the erased/unknown
EEPROM default.  Non-hardware gates are green; live PB2 DOWN, audio-routing,
and persistence field gates are still required before hardware field closure.

This README focuses on the current V3.5 + V1.73 candidate deployment.  All
user-facing comparisons below use stock MAIN V2.3 + CONTROL V1.6b as the
baseline.  Against that stock baseline, V3.5/V1.73 adds A/B presets, PB1/PB2
diagnostics, MAIN identity display, bounded I2C and chain recovery, RAM-bank
and ISR scratch hardening, SRC4382 robustness, DSP coefficient safety, and wake
I2C phase-order hardening.  The current source line is also materially more
maintainable: the MAIN assembly has semantic labels for the major service
paths/RAM roles, and the V3.4/V3.5 size-reclaim campaign recovered roughly
2 KB of contiguous MAIN flash headroom for future features.  Older patched and
rewrite releases are historical implementation steps; see
[docs/RELEASE_ARCHIVE.md](docs/RELEASE_ARCHIVE.md).

## Fresh Clone Setup

From a clean machine, clone the repo and install the Python tooling needed for
flashing and USB probes:

```bash
git clone https://github.com/antorsae/DLCP.git
cd DLCP

# Install uv if needed.  Homebrew is also fine: brew install uv
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# Create the repo-local virtualenv used by every command below.
uv venv .venv_ep0 --python 3.12
uv pip install --python .venv_ep0/bin/python -e .
```

Quick flashing/probe setup check:

```bash
.venv_ep0/bin/python -c "from dlcp_fw.paths import V35_MAIN_HEX; print(V35_MAIN_HEX)"
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --help
```

For simulation, tests, or firmware-development work, install the optional dev
dependencies and build the native Rust simulator extension:

```bash
uv pip install --python .venv_ep0/bin/python -e ".[dev]"
PYO3_PYTHON="$PWD/.venv_ep0/bin/python" cargo build --release -p dlcp-sim-py
bash crates/dlcp-sim-py/build.sh
```

If `cargo` is missing, install a stable Rust toolchain first, then rerun the
two Rust build commands.  Quick simulator check:

```bash
PYTHONPATH=src .venv_ep0/bin/python -c "from dlcp_fw.paths import V173_CONTROL_HEX, V35_MAIN_HEX; from dlcp_fw.sim.dlcp_sim_native import Chain; c = Chain.from_v171_v32(control_hex_path=str(V173_CONTROL_HEX), main_hex_path=str(V35_MAIN_HEX)); c.run_until_connected(limit=200); print(c.lcd_lines())"
```

## Why Upgrade

Stock DLCP firmware, especially **MAIN V2.3 + CONTROL V1.6b**, can wedge into
`WAITING FOR DLCP` and require a full power cycle.  The V3.5 + V1.73 pair is
built around robustness fixes for the real failure modes seen on hardware and
shows each MAIN's version/revision directly on the PB1/PB2 Diagnostics pages.

| Area | Stock V2.3 + V1.6b | V3.5 + V1.73 |
|---|---|---|
| Chain hangs | Unbounded waits can leave CONTROL stuck on `WAITING FOR DLCP`. | Bounded waits, UART recovery, reconnect hardening, and a front-panel WAITING escape after the grace window. |
| I2C/MSSP | MAIN can spin forever on DSP/SRC bus conditions. | Runtime Start/Restart/Stop/ACKEN/BF/SSPIF waits are bounded; wake/reconnect now separates route sync, device-init barrier, late input-route side effects, and volume restore. |
| DSP faults | No user-visible fault reporting. | MAIN advertises persistent DSP-path faults with `BF/08`; CONTROL shows `!` and resyncs when the fault clears. |
| Diagnostics | No useful live PB health view. | PB1/PB2 LCD diagnostics, per-MAIN version/rev on healthy pages, plus USB HID snapshots for counters and reset causes. |
| UI under diagnostics | Not applicable. | Diagnostics pages refresh near 1 Hz and keep buttons/IR responsive. |
| SRC/input routing | Auto Detect and manual digital inputs can flap or depend on stale receiver/TAS state. | Auto Detect is rate-limited and debounced, locked RXCKR estimator holes hold route, hard loss/reacquire is explicit, and fixed inputs prime the receiver/TAS path. |
| Presets | One active DSP configuration. | A/B DSP preset banks with coordinated delayed switching, validated per-row APPLY, and no unmute until the selected coefficient image is proven. |
| Flashing | Firmware update can be opaque and resets are hard to reason about. | CLI path prints before/after identity, preserves user settings, and performs post-flash finalizers. |
| IR | Stock RC5 command handling only. | Stock-compatible RC5 path plus shortcuts for preset A/B and explicit standby/wake. |

## What You Get

**A/B presets.**  MAIN stores two full DSP configurations.  CONTROL adds a Preset page and IR shortcuts:

- `0x38`: preset A
- `0x39`: preset B
- `0x3A`: standby
- `0x3B`: wake

**Per-PB input selection.**  Once CONTROL has seen PB2, the menu order becomes
`Volume -> Preset -> Input PB1 -> Input PB2 -> Setup -> PB1 Diag -> PB2 Diag`.
PB2 initially shows `Same as PB1`, preserving the stock-style broadcast input
behavior for both MAINs.  Selecting a concrete PB2 source makes PB1 and PB2
independent and sends addressed input frames; selecting `Same as PB1` again
returns to broadcast behavior.  CONTROL `rev 0x53` persists the PB2 input
choice in a guarded CONTROL EEPROM byte and keeps it pending until PB2 is
rediscovered after boot.  The Volume page always shows PB1's source.
This fixes the stock MASTER/FOLLOWER digital-input problem: stock CONTROL
broadcasts one global input selection, so choosing `Optical` makes both PB1 and
PB2 listen to their local optical receivers even though the follower is normally
fed by PB1 over the RJ45/CAT/AES link.  For that tandem wiring, the recommended
setup is:

```text
Input PB1: Auto Detect   # or the real external source, e.g. Optical
Input PB2: AES
```

If PB2 health ages out, the PB2 input title can show `old` or `lost`, but the
page remains available after PB2 has been discovered.  The reported PB2
`Same as PB1` + `DOWN` reboot is simulator/canonical-HEX fixed in CONTROL
`rev 0x52` and retained in `rev 0x53`, but not live field-closed until the
hardware gate in
[`docs/HARDWARE_TEST.md`](docs/HARDWARE_TEST.md) passes.

**Coordinated switching.**  Stock firmware has one active DSP configuration and
no coordinated A/B preset handoff.  In a two-MAIN chain, V3.5 uses a
mute/wait/apply sequence so left and right switch together instead of one side
audibly moving first, with parser/chain-TX arbitration hardened to prevent
forwarded frames from colliding with local replies.  Current V3.5 also makes
preset APPLY transaction-owned and validates each DSP row header before
advancing, so a preset change cannot commit a partial or mixed coefficient
image and then unmute.

**SRC4382 input handling.**  Stock Auto Detect can flap on transient receiver
status and manual digital input selection can depend on stale receiver/TAS
state.  V3.5 reduces Auto Detect polling, debounces source-loss detection, and
primes the SRC route when a fixed digital input is selected.  The rationale is
practical: Auto Detect should not spend the foreground loop constantly querying
the receiver, a single transient status sample should not flap the selected
route, and selecting S/PDIF/USB/AES/Optical manually must restore the
receiver/TAS path without depending on a previous Auto Detect scan.  Current
V3.5 additionally treats `RXCKR=0` with `UNLOCK=0` as a locked estimator hole
instead of hard source loss, keeps route refresh from dirtying master volume
while unmuted, records SRC/DSP forensic counters over USB (`N/L/C/T/M`), and
classifies bounded SEN/PEN timeout exits through the same visible I2C recovery
path.  V3.5 also exposes USB `cmd 0x45` as a tiny SRC4382 page-0 raw register
read for operator diagnostics.  The host tool assembles selected receiver,
lock/payload/error evidence, `0x32..0x33` ratio bytes, and IEC61937 PC/PD bytes
from multiple reads.  V1a is read-only, page-0-only, has no firmware-side
register whitelist/decode/cache, and does not add CONTROL/LCD/current-loop
behavior.

**Wake/reconnect DSP safety.**  The wake path now keeps audio muted, drains
route/channel sync before the final selected-preset writer, runs the final
reassert through the validated preset-table path, waits for the post-wake
device-init barrier, then applies late input-route side effects and volume
restore.  This preserves the route-sync fix without letting early I2C side
effects create startup `I6` or a live wrong DSP image.

**Maintainable MAIN source and headroom.**  The current V3.5 MAIN source lives
in `src/dlcp_fw/asm/dlcp_main_v35.asm`, with the historical V3.4 source kept
stable for reproducible rebuilds.  The reanalysis work replaced opaque
auto-labels with semantic labels across the high-value control flow and RAM
roles, with rename decisions tracked in
`artifacts/reanalysis/dlcp_main_v34_rename_ledger.tsv`.  The same engineering
pass reclaimed the MAIN app region from the edge of the fixed `0x4C00` preset
table wall to controlled feature budget; the current V3.5 listing leaves
`1826` bytes before `0x4C00`.  That reserve is deliberate
feature budget for future diagnostics, safety checks, and controlled UI/audio
behavior changes.

**Live diagnostics.**  CONTROL adds PB1/PB2 diagnostics pages.  On the
current V1.73 + V3.5 candidate pair, each healthy Diagnostics page also shows that
MAIN's live identity, for example `PB1 OK v3.5 0090` and `PB2 OK v3.5 0090`.
The full MAIN counter set, including USB-only SRC/DSP counters, is available
over USB:

```bash
.venv_ep0/bin/python scripts/dlcp_diag.py --json --watch --interval 1
```

The selected-source SRC4382 signal snapshot is available over USB `cmd 0x45`.
By default it queries every attached MAIN and prints a human-readable ASCII
table.  Use an explicit HID path when you want a single unit; paths are
redacted by default in command output.  The default snapshot includes the
ratio and PC/PD bytes, decoded lock, payload, route consistency, SRC4382
status bits, and input/output sample-rate evidence.  The firmware command
itself only reads one requested page-0 register; all register selection and
decode lives in the host tool.  Exact output rates are derived from the exposed
clock/divider registers only when they prove the path is clocked from the DLCP
24 MHz MCLK:

```bash
.venv_ep0/bin/python scripts/dlcp_src4382_diag.py
.venv_ep0/bin/python scripts/dlcp_src4382_diag.py --path "$MAIN_PATH"
```

Machine-readable output remains available with `--json`:

```bash
.venv_ep0/bin/python scripts/dlcp_src4382_diag.py --json --path "$MAIN_PATH"
```

LCD status format:

- `PB1 OK v3.5 NNNN` / `PB2 OK v3.5 NNNN`: V1.73 CONTROL has a fresh, healthy
  snapshot from a V3.5 MAIN and has completed that MAIN's identity query.
- `PB1 OK` / `PB2 OK`: fresh, healthy snapshot from an older MAIN that does not
  support the identity reply yet, or identity has not completed yet.
- `PB1! ...` / `PB2! ...`: fresh snapshot with one or more issue counters
  non-zero, such as `I7`, `D1`, `R1`, `A1`, `P1`, `V1`, `W1`, or `X1`.
  OK-context tokens such as `S1`, `B1`, or `O1` may also appear when an issue
  row has room, but they do not select the `PBn!` layout by themselves. Version
  text is intentionally suppressed on issue pages.
- `PB1 old` / `PB2 old`: CONTROL has an older snapshot but has not declared the
  PB lost. Version text is intentionally suppressed.
- `PB1 lost` / `PB2 lost`: CONTROL has not received fresh diagnostics within
  the loss window. Version text is intentionally suppressed.

Counters:

- `I`: I2C/MSSP transport faults
- `D`: DSP fault episodes
- `S`: standby dispatches
- `B`: bring-up/wake dispatches
- `R`: recovery branch entries
- `A`: AN0 standby triggers
- `P`: RA1 edge events (sim-only observability; no assigned V3.5 hardware function)
- `O/V/W/X`: POR, brownout, watchdog-timeout latch, software-reset flags
- `N/L/C/T/M` (MAIN V3.5 USB `cmd 0x44` only; not shown on the V1.73 CONTROL
  LCD): SRC non-PCM mute episodes, Auto Detect source-loss confirmations, route
  changes, preset table walks, and DSP mute writes

The simulator fault-injection matrix covers every CONTROL LCD-displayed
Diagnostics field (`I/D/S/B/R/A/P/O/V/W/X`) from stimulus through MAIN counter,
CONTROL cache, and PB1/PB2 LCD rendering.  `P` is intentionally scoped to the
simulator-only RA1 PORTA-edge invariant until PIC18F2455 RA1 analog masking is
modeled.  `W` is a structural RCON.TO readout bucket; current V1.73/V3.5
releases leave WDT disabled, so it should stay 0 unless WDT policy changes or a
test injects that reset cause.  The USB-only MAIN `N/L/C/T/M` fields are covered
by `cmd 0x44`/`dlcp_diag.py` tests, not by CONTROL LCD matrix tests.  `T`, `M`,
and `C` are normal context counters during boot, preset changes, standby/wake,
source reacquire, and mute transitions; `N` and `L` are useful source-condition
evidence and should be interpreted against the expected live audio state.

For raw state capture when USB still works but the chain or LCD is unhealthy:

```bash
.venv_ep0/bin/python scripts/dlcp_probe_chain_link.py
```

## Upgrade Path

There are two supported ways to flash the release pair.

Use the **CLI path** for the normal two-PB deployment.  It is the canonical
path because it bakes A/B preset captures when local captures are available,
applies L/R routing, verifies identity, and preserves user settings.  With no
local captures, it flashes the release unbaked and prints the post-flash DSP
upload instructions.

Use the **HFD path** only when you want a stock-style firmware update through
Hypex Filter Design.  HFD can stream the HEX files, but it does not run the
repo's A/B capture baking, L/R routing, or post-flash verification/finalization
steps.

### Prepare

Close HFD or any other app using the DLCP USB HID device before running CLI tools.

For the CLI A/B preset flow, keep the captured DSP tables under:

```text
artifacts/LX521.4/LX521.4_22MG10F-v5.bin
artifacts/LX521.4/LX521.4_22MG10F-v5.json
artifacts/LX521.4/LX521.4_22MG10F-v7.bin
artifacts/LX521.4/LX521.4_22MG10F-v7.json
```

The `.json` sidecars carry the config-name metadata used after flashing.
These files are local operator artifacts and may be absent in a fresh clone.
If they are missing, `scripts/dlcp_v35_release_flash.py` prints a warning and
flashes the canonical V3.5 MAIN without baking A/B preset captures.  In that
mode, upload the desired DSP project/settings afterward with Hypex Filter
Design, or capture local preset tables into
`artifacts/LX521.4/` and rerun the CLI wrapper.

### CLI Validation Flash

Inventory and identify the two MAIN roles first.  USB order is not a safe role
selector.

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py detect
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
export LEFT_HID='<hid path reported for LEFT/PB1>'
export RIGHT_HID='<hid path reported for RIGHT/PB2>'
```

Flash MAIN PB1 / left:

```bash
: "${LEFT_HID:?set LEFT_HID from identify-mains output}"
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --path "$LEFT_HID" --left
```

Flash MAIN PB2 / right:

```bash
: "${RIGHT_HID:?set RIGHT_HID from identify-mains output}"
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --path "$RIGHT_HID" --right
```

When the LX521.4 capture files are not present, expect this warning:

```text
WARNING: local A/B preset captures are incomplete; flashing canonical V3.5 without baked presets.
```

Flash CONTROL:

```bash
# Use the MAIN HID relay physically connected to CONTROL, normally LEFT/PB1.
: "${LEFT_HID:?set LEFT_HID from identify-mains output}"
export CONTROL_RELAY_MAIN_HID="$LEFT_HID"
: "${CONTROL_RELAY_MAIN_HID:?set relay MAIN HID path}"
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" --preflight-only
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID"
```

`scripts/flash_control_safe.sh` defaults to
`firmware/patched/releases/DLCP_Control_V1.73.hex`. CONTROL flashing is
relayed through a MAIN USB HID path; refresh `LEFT_HID`/`RIGHT_HID` after any
MAIN USB re-enumeration and pass the relay MAIN path explicitly. CONTROL must
be in its bootloader before the live flash. Power-cycle while holding
**UP + DOWN** for about 6 seconds; do not press SELECT. After CONTROL flashing,
power-cycle once so V1.73 starts cleanly from cold boot.

Useful post-flash checks:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
.venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$LEFT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$RIGHT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$LEFT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$RIGHT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_diag.py --path "$LEFT_HID" --json
.venv_ep0/bin/python scripts/dlcp_diag.py --path "$RIGHT_HID" --json
```

### Alternative: HFD

Hypex Filter Design can be used for a basic firmware update with the same release HEX files:

- MAIN firmware: `firmware/patched/releases/DLCP_Firmware_V3.5.hex`
- CONTROL firmware: `firmware/patched/releases/DLCP_Control_V1.73.hex`

For CONTROL V1.6b/V1.71/V1.72/V1.73, enter the CONTROL bootloader manually
first: power-cycle while holding **UP + DOWN** for about 6 seconds.  Then run
the HFD control firmware update.

Important HFD caveats:

- HFD flashes the HEX payload; it does not bake local A/B preset captures.
- HFD does not set all MAIN channels to left/right after flashing.
- HFD does not set or verify the MAIN IR profile.  Set the intended profile
  afterward (`hypex` for the Hypex remote, or `rc5` for standard RC5), or use
  the CLI flasher/finalizer so the setting is applied and read back.
- HFD does not run the repo's post-flash filename, identity,
  settings-preservation, and diagnostics checks.
- For the full V3.5 + V1.73 two-MAIN deployment, use the CLI path.

## Validate

Fast simulator gate:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -k "v35 or v34 or v173 or v33 or v172 or v32 or v171"
```

Full simulator gate:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

Current non-hardware x53 verification snapshot:

- Full multi-PB persistence file:
  `111 passed in 164.64s`
- CONTROL RAM-bank safety: `OK (control-v173)`
- collect-only: `2003 tests collected`
- full simulator gate:
  `1978 passed, 2 skipped, 4 xfailed, 1 warning in 1665.78s`
- Phase 5 gate: `P5.gate GREEN`
- gpsim excision gate: `gpsim retirement clean: no live references found`
- CONTROL x53 SHA-256:
  `3a7dd25e29c3ce731a2783d1370fb5f2b387ba4a4be7c6a48b3bb19dfb207302`

This is not live field closure for PB2 DOWN, multi-PB audio routing, or PB2
input persistence; run the dedicated hardware gates before calling those field
closed on hardware.

Recent adjacent non-hardware verification snapshot:

- SRC4382 USB diagnostics focused tests: `65 passed`
- Adjacent SRC4382 Auto Detect/audio-path regressions: `51 passed`, `9 passed`
- V3.5/V1.73 release-path focused tests: `19 passed`
- V3.4/V1.73 FIELD-10 focused regressions: `2 passed`
- V3.4/V1.73 historical focused bug/regression set: `95 passed, 3 xfailed`
- 1-hour exploratory hunt and targeted replay triage against MAIN V3.4 rev
  `0x0083` + CONTROL V1.73: no live wrong coefficient image and no
  unreconciled HIGH/MEDIUM safety finding

Hardware runbook:

- [docs/HARDWARE_TEST.md](docs/HARDWARE_TEST.md)

Core implementation docs:

- Current MAIN release flow: `scripts/dlcp_v35_release_flash.py`; historical
  V3.2 MAIN runbook: [docs/V32_RELEASE.md](docs/V32_RELEASE.md)
- Current CONTROL release flow: `scripts/flash_control_safe.sh`; historical
  V1.71 CONTROL runbook: [docs/V171_RELEASE.md](docs/V171_RELEASE.md)
- V3.4/V1.73 refactoring release inherited by V3.5: [docs/REFACTORING_V34_V173_SPEC.md](docs/REFACTORING_V34_V173_SPEC.md) and [docs/IMPL_REFACTORING_V34_V173.md](docs/IMPL_REFACTORING_V34_V173.md)
- V3.4/V1.73 field bug ledger: [docs/V34_FIELD_BUGS_20260610.md](docs/V34_FIELD_BUGS_20260610.md)
- Historical V1.71/V3.2 bug ledger: [docs/IMPL_V171_V32_BUG_LEDGER.md](docs/IMPL_V171_V32_BUG_LEDGER.md)
- Historical V3.2 robustness plan: [docs/V32_MAIN_HANG_HARDENING_PLAN.md](docs/V32_MAIN_HANG_HARDENING_PLAN.md)
- Base diagnostics protocol inherited by current LCD diagnostics: [docs/V32_DIAG_TIER1_SPEC.md](docs/V32_DIAG_TIER1_SPEC.md)
- Diagnostics MAIN identity introduced in V1.72/V3.3 and reused by V1.73/V3.5: [docs/IMPL_V172_V33_DIAG_MAIN_IDENTITY.md](docs/IMPL_V172_V33_DIAG_MAIN_IDENTITY.md)
- Historical diagnostics fault matrix inherited by current LCD counter tests: [docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md](docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md)
- Historical diagnostics matrix implementation: [docs/IMPL_V171_V32_DIAG_FAULT_INJECTION_MATRIX.md](docs/IMPL_V171_V32_DIAG_FAULT_INJECTION_MATRIX.md)
- Historical Rust simulator rewrite spec; current simulator gate is above: [docs/SIM_REWRITE_RUST_SPEC.md](docs/SIM_REWRITE_RUST_SPEC.md)

## Disclaimer

**NO WARRANTY, EXPRESS OR IMPLIED.** The Hypex DLCP is end-of-life hardware.
This firmware is a community bugfix, not a supported product.  Use it entirely
at your own risk.

Recovery from a bad flash may require a PICkit programmer and direct MCU
recovery.  Do not flash these images unless you are comfortable with PIC
firmware recovery.
