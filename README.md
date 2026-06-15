# DLCP Firmware: V3.4 MAIN + V1.73 CONTROL

Drop-in replacement firmware for the **Hypex DLCP**.  The recommended release pair is:

- MAIN: [`firmware/patched/releases/DLCP_Firmware_V3.4.hex`](firmware/patched/releases/DLCP_Firmware_V3.4.hex) (`V3.4 / rev 0xAC`)
- CONTROL: [`firmware/patched/releases/DLCP_Control_V1.73.hex`](firmware/patched/releases/DLCP_Control_V1.73.hex) (`V1.73 / rev 0x47 / build 20260611`)

This README focuses on the recommended V3.4 + V1.73 deployment.  All
user-facing comparisons below use stock MAIN V2.3 + CONTROL V1.6b as the
baseline.  Against that stock baseline, V3.4/V1.73 adds A/B presets, PB1/PB2
diagnostics, MAIN identity display, bounded I2C and chain recovery, RAM-bank
and ISR scratch hardening, SRC4382 robustness, DSP coefficient safety, and wake
I2C phase-order hardening.  Older patched and rewrite releases are historical
implementation steps; see [docs/RELEASE_ARCHIVE.md](docs/RELEASE_ARCHIVE.md).

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
.venv_ep0/bin/python -c "from dlcp_fw.paths import V34_MAIN_HEX; print(V34_MAIN_HEX)"
.venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --help
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
PYTHONPATH=src .venv_ep0/bin/python -c "from dlcp_fw.paths import V173_CONTROL_HEX, V34_MAIN_HEX; from dlcp_fw.sim.dlcp_sim_native import Chain; c = Chain.from_v171_v32(control_hex_path=str(V173_CONTROL_HEX), main_hex_path=str(V34_MAIN_HEX)); c.run_until_connected(limit=200); print(c.lcd_lines())"
```

## Why Upgrade

Stock DLCP firmware, especially **MAIN V2.3 + CONTROL V1.6b**, can wedge into
`WAITING FOR DLCP` and require a full power cycle.  The V3.4 + V1.73 pair is
built around robustness fixes for the real failure modes seen on hardware and
shows each MAIN's version/revision directly on the PB1/PB2 Diagnostics pages.

| Area | Stock V2.3 + V1.6b | V3.4 + V1.73 |
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

**Coordinated switching.**  Stock firmware has one active DSP configuration and
no coordinated A/B preset handoff.  In a two-MAIN chain, V3.4 uses a
mute/wait/apply sequence so left and right switch together instead of one side
audibly moving first, with parser/chain-TX arbitration hardened to prevent
forwarded frames from colliding with local replies.  Current V3.4 also makes
preset APPLY transaction-owned and validates each DSP row header before
advancing, so a preset change cannot commit a partial or mixed coefficient
image and then unmute.

**SRC4382 input handling.**  Stock Auto Detect can flap on transient receiver
status and manual digital input selection can depend on stale receiver/TAS
state.  V3.4 reduces Auto Detect polling, debounces source-loss detection, and
primes the SRC route when a fixed digital input is selected.  The rationale is
practical: Auto Detect should not spend the foreground loop constantly querying
the receiver, a single transient status sample should not flap the selected
route, and selecting S/PDIF/USB/AES/Optical manually must restore the
receiver/TAS path without depending on a previous Auto Detect scan.  Current
V3.4 additionally treats `RXCKR=0` with `UNLOCK=0` as a locked estimator hole
instead of hard source loss, keeps route refresh from dirtying master volume
while unmuted, records SRC/DSP forensic counters over USB (`N/L/C/T/M`), and
classifies bounded SEN/PEN timeout exits through the same visible I2C recovery
path.

**Wake/reconnect DSP safety.**  The wake path now keeps audio muted, drains
route/channel sync before the final selected-preset writer, runs the final
reassert through the validated preset-table path, waits for the post-wake
device-init barrier, then applies late input-route side effects and volume
restore.  This preserves the route-sync fix without letting early I2C side
effects create startup `I6` or a live wrong DSP image.

**Live diagnostics.**  CONTROL adds PB1/PB2 diagnostics pages.  On the
recommended V1.73 + V3.4 pair, each healthy Diagnostics page also shows that
MAIN's live identity, for example `PB1 OK v3.4 xAC` and `PB2 OK v3.4 xAC`.
The full MAIN counter set, including USB-only SRC/DSP counters, is available
over USB:

```bash
.venv_ep0/bin/python scripts/dlcp_diag.py --json --watch --interval 1
```

LCD status format:

- `PB1 OK v3.4 xNN` / `PB2 OK v3.4 xNN`: V1.73 CONTROL has a fresh, healthy
  snapshot from a V3.4 MAIN and has completed that MAIN's identity query.
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
- `P`: RA1 edge events (sim-only observability; no assigned V3.4 hardware function)
- `O/V/W/X`: POR, brownout, watchdog-timeout latch, software-reset flags
- `N/L/C/T/M` (MAIN V3.4 USB `cmd 0x44` only; not shown on the V1.73 CONTROL
  LCD): SRC non-PCM mute episodes, Auto Detect source-loss confirmations, route
  changes, preset table walks, and DSP mute writes

The simulator fault-injection matrix covers every CONTROL LCD-displayed
Diagnostics field (`I/D/S/B/R/A/P/O/V/W/X`) from stimulus through MAIN counter,
CONTROL cache, and PB1/PB2 LCD rendering.  `P` is intentionally scoped to the
simulator-only RA1 PORTA-edge invariant until PIC18F2455 RA1 analog masking is
modeled.  `W` is a structural RCON.TO readout bucket; current V1.73/V3.4
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
If they are missing, `scripts/dlcp_v34_release_flash.py --left/--right` prints
a warning and flashes the canonical V3.4 MAIN without baking A/B preset
captures.  In that mode, upload the desired DSP project/settings afterward
with Hypex Filter Design, or capture local preset tables into
`artifacts/LX521.4/` and rerun the CLI wrapper.

### Recommended: CLI

Flash MAIN PB1 / left:

```bash
.venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --left
```

Flash MAIN PB2 / right:

```bash
.venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --right
```

When the LX521.4 capture files are not present, expect this warning:

```text
WARNING: local A/B preset captures are incomplete; flashing canonical V3.4 without baked presets.
```

Flash CONTROL:

```bash
scripts/flash_control_safe.sh --preflight-only
scripts/flash_control_safe.sh
```

`scripts/flash_control_safe.sh` defaults to
`firmware/patched/releases/DLCP_Control_V1.73.hex`. CONTROL must be in its
bootloader before the live flash.  Power-cycle while holding **UP + DOWN** for
about 6 seconds; do not press SELECT.  After CONTROL flashing, power-cycle once
so V1.73 starts cleanly from cold boot.

Useful post-flash checks:

```bash
.venv_ep0/bin/python scripts/dlcp_main_flash.py --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py --info-only
.venv_ep0/bin/python scripts/dlcp_diag.py --json
```

### Alternative: HFD

Hypex Filter Design can be used for a basic firmware update with the same release HEX files:

- MAIN firmware: `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
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
- For the full V3.4 + V1.73 two-MAIN deployment, use the CLI path.

## Validate

Fast simulator gate:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -k "v34 or v173 or v33 or v172 or v32 or v171"
```

Full simulator gate:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

Current non-hardware verification snapshot:

- V3.4/V1.73 FIELD-10 focused regressions: `2 passed`
- V3.4/V1.73 focused bug/regression set: `95 passed, 3 xfailed`
- full simulator gate: `1655 passed, 2 skipped, 3 xfailed, 7 warnings`
- 30-minute exploratory hunt against MAIN V3.4 rev `0xAC` + CONTROL V1.73: no
  live wrong coefficient image and no unreconciled HIGH/MEDIUM safety finding

Hardware runbook:

- [docs/HARDWARE_TEST.md](docs/HARDWARE_TEST.md)

Core implementation docs:

- Current MAIN release flow: `scripts/dlcp_v34_release_flash.py`; historical
  V3.2 MAIN runbook: [docs/V32_RELEASE.md](docs/V32_RELEASE.md)
- Current CONTROL release flow: `scripts/flash_control_safe.sh`; historical
  V1.71 CONTROL runbook: [docs/V171_RELEASE.md](docs/V171_RELEASE.md)
- V3.4/V1.73 refactoring release: [docs/REFACTORING_V34_V173_SPEC.md](docs/REFACTORING_V34_V173_SPEC.md) and [docs/IMPL_REFACTORING_V34_V173.md](docs/IMPL_REFACTORING_V34_V173.md)
- V3.4/V1.73 field bug ledger: [docs/V34_FIELD_BUGS_20260610.md](docs/V34_FIELD_BUGS_20260610.md)
- Historical V1.71/V3.2 bug ledger: [docs/IMPL_V171_V32_BUG_LEDGER.md](docs/IMPL_V171_V32_BUG_LEDGER.md)
- Historical V3.2 robustness plan: [docs/V32_MAIN_HANG_HARDENING_PLAN.md](docs/V32_MAIN_HANG_HARDENING_PLAN.md)
- Base diagnostics protocol inherited by current LCD diagnostics: [docs/V32_DIAG_TIER1_SPEC.md](docs/V32_DIAG_TIER1_SPEC.md)
- Diagnostics MAIN identity introduced in V1.72/V3.3 and reused by V1.73/V3.4: [docs/IMPL_V172_V33_DIAG_MAIN_IDENTITY.md](docs/IMPL_V172_V33_DIAG_MAIN_IDENTITY.md)
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
