# DLCP Firmware: V3.2 MAIN + V1.71 CONTROL

Drop-in replacement firmware for the **Hypex DLCP**.  The current release pair is:

- MAIN: [`firmware/patched/releases/DLCP_Firmware_V3.2.hex`](firmware/patched/releases/DLCP_Firmware_V3.2.hex) (`V3.2 / rev 0x6E`)
- CONTROL: [`firmware/patched/releases/DLCP_Control_V1.71.hex`](firmware/patched/releases/DLCP_Control_V1.71.hex) (`V1.71 / rev 0x35 / build 20260528`)

This README focuses on the supported V3.2 + V1.71 deployment.  Older patched and rewrite releases are historical; see [docs/RELEASE_ARCHIVE.md](docs/RELEASE_ARCHIVE.md).

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
.venv_ep0/bin/python -c "from dlcp_fw.paths import V32_MAIN_HEX; print(V32_MAIN_HEX)"
.venv_ep0/bin/python scripts/dlcp_v32_release_flash.py --help
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
PYTHONPATH=src .venv_ep0/bin/python -c "from dlcp_fw.sim.dlcp_sim_native import Chain; c = Chain.from_v171_v32(); c.step_ticks(48_000_000); print(c.lcd_lines())"
```

## Why Upgrade

Stock DLCP firmware, especially **MAIN V2.3 + CONTROL V1.6b**, can wedge into `WAITING FOR DLCP` and require a full power cycle.  The V3.2 + V1.71 pair is built around robustness fixes for the real failure modes seen on hardware.

| Area | Stock V2.3 + V1.6b | V3.2 + V1.71 |
|---|---|---|
| Chain hangs | Unbounded waits can leave CONTROL stuck on `WAITING FOR DLCP`. | Bounded waits, UART recovery, reconnect hardening, and a front-panel WAITING escape after the grace window. |
| I2C/MSSP | MAIN can spin forever on DSP/SRC bus conditions. | Runtime Start/Restart/Stop/ACKEN/BF/SSPIF waits are bounded and route through recovery helpers. |
| DSP faults | No user-visible fault reporting. | MAIN advertises persistent DSP-path faults with `BF/08`; CONTROL shows `!` and resyncs when the fault clears. |
| Diagnostics | No useful live PB health view. | PB1/PB2 LCD diagnostics plus USB HID snapshots for counters and reset causes. |
| UI under diagnostics | Not applicable. | Diagnostics pages refresh near 1 Hz and keep buttons/IR responsive. |
| Presets | One active DSP configuration. | A/B DSP preset banks with coordinated delayed switching across two MAINs. |
| Flashing | Firmware update can be opaque and resets are hard to reason about. | CLI path prints before/after identity, preserves user settings, and performs post-flash finalizers. |
| IR | Stock RC5 command handling only. | Stock-compatible RC5 path plus V1.71 shortcuts for preset A/B and explicit standby/wake. |

## What You Get

**A/B presets.**  MAIN stores two full DSP configurations.  CONTROL adds a Preset page and IR shortcuts:

- `0x38`: preset A
- `0x39`: preset B
- `0x3A`: standby
- `0x3B`: wake

**Coordinated switching.**  In a two-MAIN chain, V3.2 coordinates the mute/wait/apply sequence so left and right switch together instead of one side audibly moving first.

**SRC4382 input handling.**  V3.2 rev `0x6E` reduces SRC4382 Auto Detect
polling, debounces source-loss detection, and primes the SRC route when a
fixed digital input is selected.  The rationale is practical: Auto Detect
should not spend the foreground loop constantly querying the receiver, a single
transient status sample should not flap the selected route, and selecting
S/PDIF/USB/AES/Optical manually must restore the receiver/TAS path without
depending on a previous Auto Detect scan.

**Live diagnostics.**  CONTROL adds PB1/PB2 diagnostics pages.  The same data is available over USB:

```bash
.venv_ep0/bin/python scripts/dlcp_diag.py --json --watch --interval 1
```

LCD status format:

- `PB1 OK` / `PB2 OK`: fresh snapshot, no displayed abnormal counters or reset flags.
- `PB1! ...` / `PB2! ...`: fresh snapshot with one or more non-zero diagnostics; tokens such as `I7`, `A1`, `S1`, `B1`, or `O1` identify the fields that changed.
- `PB1 old` / `PB2 old`: CONTROL has an older snapshot but has not declared the PB lost.
- `PB1 lost` / `PB2 lost`: CONTROL has not received fresh diagnostics within the loss window.

Counters:

- `I`: I2C/MSSP transport faults
- `D`: DSP fault episodes
- `S`: standby dispatches
- `B`: bring-up/wake dispatches
- `R`: recovery branch entries
- `A`: AN0 standby triggers
- `P`: RA1 edge events
- `O/V/W/X`: POR, brownout, watchdog, software-reset flags

The simulator fault-injection matrix now covers every displayed Diagnostics
field from stimulus through MAIN counter, CONTROL cache, and PB1/PB2 LCD
rendering.  `P` is intentionally scoped to the simulator-only RA1 PORTA-edge
invariant until PIC18F2455 RA1 analog masking is modeled.

For raw state capture when USB still works but the chain or LCD is unhealthy:

```bash
.venv_ep0/bin/python scripts/dlcp_probe_chain_link.py
```

## Upgrade Path

There are two supported ways to flash the release pair.

Use the **CLI path** for the normal two-PB deployment.  It is the canonical path because it bakes A/B preset captures when local captures are available, applies L/R routing, verifies identity, and preserves user settings.  With no local captures, it flashes the release unbaked and prints the post-flash DSP upload instructions.

Use the **HFD path** only when you want a stock-style firmware update through Hypex Filter Design.  HFD can stream the HEX files, but it does not run the repo's A/B capture baking, L/R routing, or post-flash verification/finalization steps.

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
If they are missing, `scripts/dlcp_v32_release_flash.py --left/--right` prints
a warning and flashes the canonical V3.2 MAIN without baking A/B preset
captures.  In that mode, upload the desired DSP project/settings afterward
with Hypex Filter Design, or capture local preset tables into
`artifacts/LX521.4/` and rerun the CLI wrapper.

### Recommended: CLI

Flash MAIN PB1 / left:

```bash
.venv_ep0/bin/python scripts/dlcp_v32_release_flash.py --left
```

Flash MAIN PB2 / right:

```bash
.venv_ep0/bin/python scripts/dlcp_v32_release_flash.py --right
```

When the LX521.4 capture files are not present, expect this warning:

```text
WARNING: local A/B preset captures are incomplete; flashing canonical V3.2 without baked presets.
```

Flash CONTROL:

```bash
scripts/flash_control_safe.sh --preflight-only
scripts/flash_control_safe.sh
```

CONTROL must be in its bootloader before the live flash.  Power-cycle while holding **UP + DOWN** for about 6 seconds; do not press SELECT.  After CONTROL flashing, power-cycle once so V1.71 starts cleanly from cold boot.

Useful post-flash checks:

```bash
.venv_ep0/bin/python scripts/dlcp_main_flash.py --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py --info-only
.venv_ep0/bin/python scripts/dlcp_diag.py --json
```

### Alternative: HFD

Hypex Filter Design can be used for a basic firmware update with the same release HEX files:

- MAIN firmware: `firmware/patched/releases/DLCP_Firmware_V3.2.hex`
- CONTROL firmware: `firmware/patched/releases/DLCP_Control_V1.71.hex`

For CONTROL V1.6b/V1.71, enter the CONTROL bootloader manually first: power-cycle while holding **UP + DOWN** for about 6 seconds.  Then run the HFD control firmware update.

Important HFD caveats:

- HFD flashes the HEX payload; it does not bake local A/B preset captures.
- HFD does not set all MAIN channels to left/right after flashing.
- HFD does not run the repo's post-flash filename, identity, settings-preservation, and diagnostics checks.
- For the full V3.2 + V1.71 two-MAIN deployment, use the CLI path.

## Validate

Fast simulator gate:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -k "v32 or v171"
```

Full simulator gate:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

Current non-hardware verification snapshot:

- `tests --collect-only`: `1130 tests collected`
- focused Diagnostics fault matrix gate: `30 passed`
- broader Diagnostics/SRC gate: `116 passed`
- full simulator gate: `1112 passed, 1 skipped`

Hardware runbook:

- [docs/HARDWARE_TEST.md](docs/HARDWARE_TEST.md)

Core implementation docs:

- MAIN release flow: [docs/V32_RELEASE.md](docs/V32_RELEASE.md)
- CONTROL release flow: [docs/V171_RELEASE.md](docs/V171_RELEASE.md)
- Active bug ledger: [docs/IMPL_V171_V32_BUG_LEDGER.md](docs/IMPL_V171_V32_BUG_LEDGER.md)
- Robustness plan: [docs/V32_MAIN_HANG_HARDENING_PLAN.md](docs/V32_MAIN_HANG_HARDENING_PLAN.md)
- Diagnostics protocol: [docs/V32_DIAG_TIER1_SPEC.md](docs/V32_DIAG_TIER1_SPEC.md)
- Diagnostics fault matrix: [docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md](docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md)
- Diagnostics matrix implementation: [docs/IMPL_V171_V32_DIAG_FAULT_INJECTION_MATRIX.md](docs/IMPL_V171_V32_DIAG_FAULT_INJECTION_MATRIX.md)
- Simulator details: [docs/SIM_REWRITE_RUST_SPEC.md](docs/SIM_REWRITE_RUST_SPEC.md)

## Disclaimer

**NO WARRANTY, EXPRESS OR IMPLIED.** The Hypex DLCP is end-of-life hardware.  This firmware is a community bugfix, not a supported product.  Use it entirely at your own risk.

Recovery from a bad flash may require a PICkit programmer and direct MCU recovery.  Do not flash these images unless you are comfortable with PIC firmware recovery.
