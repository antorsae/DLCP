# V1.71 CONTROL Release Workflow

## Scope

This is the operator runbook for the recommended CONTROL deployment as
of 2026-04-21.

- recommended CONTROL release: `firmware/patched/releases/DLCP_Control_V1.71.hex`
- recommended MAIN release: `firmware/patched/releases/DLCP_Firmware_V3.2.hex`
  (see [`docs/V32_RELEASE.md`](V32_RELEASE.md) for the matching MAIN flow)
- canonical CONTROL builder: `scripts/build_v171_release.py`
- recommended flashing path: use `scripts/flash_control_safe.sh`
  with `--hex firmware/patched/releases/DLCP_Control_V1.71.hex`
- active implementation bugs for the V1.71/V3.2 pair are tracked in
  [`docs/IMPL_V171_V32_BUG_LEDGER.md`](IMPL_V171_V32_BUG_LEDGER.md)
- Diagnostics counter fault-injection closure is tracked separately in
  [`docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md`](V171_V32_DIAG_FAULT_INJECTION_MATRIX.md)
  and
  [`docs/IMPL_V171_V32_DIAG_FAULT_INJECTION_MATRIX.md`](IMPL_V171_V32_DIAG_FAULT_INJECTION_MATRIX.md)

V1.71 supersedes V1.64b for chains paired with V3.2 MAIN.  V1.64b
remains the canonical fallback for chains running V3.1 / V2.x MAIN
that do not need the V1.71-specific features.

## Current Validation Status (2026-05-23)

The historical 2026-04-22 hardware issue for the recommended pair was:

- canonical CONTROL revision then: `V1.71 / rev 0x19`
- current canonical CONTROL revision: `V1.71 / rev 0x35 / build 20260528`
- canonical MAIN revision then: `V3.2 / rev 0x53`
- reproduced symptom: after `STDBY -> WAKE`, CONTROL could remain on
  `WAITING FOR DLCP` while both MAINs are already awake, healthy, and
  visible on USB

The source tree now carries simulator regressions for the wake/reconnect
contract, including duplicate standby-frame idempotence on MAIN, plus the
active V1.71/V3.2 bug ledger.  Live hardware confirmation is still required
before the ledger rows can be marked `done`.  See
[`docs/analysis/V171_V32_STDBY_WAKE_WAITING_REAL_HW_2026-04-22.md`](analysis/V171_V32_STDBY_WAKE_WAITING_REAL_HW_2026-04-22.md)
and [`docs/IMPL_V171_V32_BUG_LEDGER.md`](IMPL_V171_V32_BUG_LEDGER.md).

2026-05-10 Diagnostics note: V1.71 rev `0x1C` keeps the stock-compatible
V1.6b IR receiver path and refreshes the visible PB Diagnostics page at the
full cadence.

Diagnostics counter matrix status: the full displayed counter matrix in
[`docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md`](V171_V32_DIAG_FAULT_INJECTION_MATRIX.md)
now has simulator coverage for every displayed row without `gap`, `partial`,
`PB1-only`, source-hook-only, seeded-render-only, or navigation-driven rows.
`P` is explicitly simulator-only PORTA-edge coverage and remains
hardware-realistic not-applicable until PIC18F2455 RA1 analog masking is
modeled.  The bug-ledger audit and live-rig evidence remain separate final
release requirements.

2026-05-09 IR note: V1.71 rev `0x1A` uses the stock-compatible V1.6b
in-ISR RC5 decoder path again.  The Timer1 non-blocking receiver passed
rust-sim pulse tests but decoded no real Flipper IR in the earlier hardware
session; keep that Timer1 path out of the live ISR path until a
hardware-validated replacement exists.  Later operator testing confirmed real
IR works on both stock CONTROL V1.6b and CONTROL V1.71 with the
stock-compatible path.

## What's New vs V1.64b

V1.71 is a feature-bearing source rebuild of the V1.7 stock-equivalent
source.  It inlines V1.61b–V1.64b features (preset shortcuts, BF/08
fault indicator, reconnect/OERR soft-recover, IR endpoints) per
[`docs/V16B_SOURCE_REWRITE_SPEC.md`](V16B_SOURCE_REWRITE_SPEC.md), and
adds three new layers on top:

- **Layer 1 (bounded TX)** — `tx_byte_enqueue` no longer busy-waits
  when the TX ring is full.  V1.6b's unbounded busy-wait could hang
  CONTROL when MAIN's `main_uart_service` paused for tens of
  milliseconds (V3.x legacy 97-iter preset apply, EEPROM block writes,
  etc).  The new path drops one byte and signals saturation via
  `STATUS.C` so callers can decide policy.
- **Layer 2 (one-frame-per-trigger full-sync)** — `full_sync_burst`
  emits ONE frame per trigger instead of the V1.6b multi-frame burst.
  This reduces TX-ring pressure under reconnect/full-sync churn and
  prevents the V3.x legacy preset apply from coinciding with multiple
  frames in the same TX window.
- **Layer 5 (Diagnostics pages, Tier-1)** — adds two deepest-menu
  entries `PB1 Diag(4)` and `PB2 Diag(5)` after the existing Setup(3)
  state, giving a 6-state Tier-1 ring
  (`Volume(0) → Preset(1) → Input(2) → Setup(3) → PB1 Diag(4) → PB2 Diag(5) → Volume(0)`).
  When a PB Diag page is active, CONTROL fires `cmd 0x22` (4
  reset-cause flags) once on page entry and then polls the
  corresponding PB with `cmd 0x21` (7 runtime counters) on a ~1 s
  cadence; the BF/2N reply burst populates 11 cache cells per PB.
  CONTROL renders the cache in one of four 16x2 layouts
  (Absent/Healthy/Degraded/Overflow) per the cache health.  See
  [`docs/V32_DIAG_TIER1_SPEC.md`](V32_DIAG_TIER1_SPEC.md) for
  the Tier-1 layout dispatch and
  [`docs/V163B_DIAGNOSTICS_MENU_SPEC.md`](V163B_DIAGNOSTICS_MENU_SPEC.md)
  for the original (pre-Tier-1) layout.
- **WAITING FOR DLCP operator recovery (2026-04-21)** — the stock
  V1.6b/V1.7x WAITING loops had no button poll and no timeout; if
  MAIN failed to emit the sentinel-clearing boot handshake
  (`BF/05/06/07/1D`) CONTROL was locked on `WAITING FOR DLCP`
  forever and only a power-cycle recovered.  V1.71 adds a bounded
  operator escape: after ~10 s of being stuck in either the
  cold-boot WAITING loop or the V1.62b reconnect loop, pressing
  the front-panel `RIGHT` or `LEFT` button triggers a PIC18 soft
  `RESET`.  The reset preserves the bootloader region, re-primes
  all four sentinel caches, and re-emits the CONTROL→MAIN
  full-sync burst — MAIN normally answers each full-sync frame
  with a status frame that clears the corresponding sentinel, so
  the second boot pass usually completes even when the first one
  stalled.  Implementation notes: 16-bit grace counter
  `v171_waiting_grace_count_lo`/`_hi` at RAM 0x0A8/0x0A9, gate
  arms when the high byte reaches `V171_WAITING_GRACE_THRESHOLD_HI`
  (= 4, i.e. 1024 iterations × ~10 ms/iter dominated by
  `delay_short(0xC8)` ≈ 10.24 s).  The button bitmap is refreshed
  via the one-shot `button_scan_debounce` (which reads the
  front-panel button GPIOs on PORTA/PORTC, not the IR dispatch
  path), so the WAITING loops keep polling MAIN in parallel with
  the grace counter.  The ~10 s gate prevents accidental resets
  from stray button presses during normal cold-boot MAIN warmup.
  This remains an operator-facing mitigation even with the paired
  V3.2 wake-path hardening: if the chain still wedges for any other
  reason, the front-panel `RIGHT`/`LEFT` escape guarantees a local
  recovery path without power-cycling the MAINs. Ongoing broader
  MAIN hardening is tracked in
  [`docs/V32_MAIN_HANG_HARDENING_PLAN.md`](V32_MAIN_HANG_HARDENING_PLAN.md).

EEPROM layout: V1.71 preserves the V1.6x preset slot at EEPROM
`0x74` and the legacy V1.71 identity bytes at `0x70..0x72`.
Canonical release revision is not stored in EEPROM because
EEPROM `0x73` is runtime-owned. The canonical builder bumps a
monotonic release revision in a flashed metadata block at app-flash
`0x77B0..0x77BB`, bakes the build date into `0x77BC..0x77BF`, and
updates the boot LCD splash to print both values:

```text
Firmware V1.71
Rev xNN YYYYMMDD
```

Existing CONTROL EEPROM contents are read
transparently — no re-baking required when upgrading from
V1.62b / V1.63b / V1.64b.

## Canonical Build

Each canonical `V1.71` CONTROL build must reuse the canonical release
filename and bump the monotonic release revision:

```bash
scripts/build_v171_release.py
```

That command:

1. increments the release revision byte in `control_release_metadata`
2. bakes the build date into metadata and the LCD-visible release banner
3. assembles `src/dlcp_fw/asm/dlcp_control_v171.asm`
4. rewrites the canonical release artifact at
   `firmware/patched/releases/DLCP_Control_V1.71.hex`

The build is transactional: if `gpasm` fails, the source revision byte
is rolled back and the existing canonical hex is left untouched.

## Required Local Inputs

None — CONTROL flashing is binary-only (no preset capture required).
The captured preset captures are MAIN-side only and live under
`artifacts/LX521.4/` per the V3.2 release flow.

## Flash Commands

Preflight (no flash):

```bash
scripts/flash_control_safe.sh \
  --hex firmware/patched/releases/DLCP_Control_V1.71.hex \
  --preflight-only
```

Live flash (writes to attached CONTROL):

```bash
scripts/flash_control_safe.sh \
  --hex firmware/patched/releases/DLCP_Control_V1.71.hex
```

CONTROL must already be in its manual bootloader.  Power-cycle while holding
`UP + DOWN` for at least 6 seconds; do not touch `SELECT`.  The bootloader
check samples `UP` and `DOWN` active-low for 11 stable delay loops
(approximately 5.5 s) and rejects the combo if `SELECT` is also pressed.  If
the LCD returns to `Volume`, CONTROL is still running the app and the flash
will time out waiting for the bootloader prompt.  The safe wrapper protects
that path with `--live-timeout-s` (default 180 s).  For quick operator retries,
use a shorter watchdog, for example `--live-timeout-s 10`.

What the wrapper does:

1. bootloader-integrity preflight (refuses to flash if the bootloader
   region of the attached unit doesn't match the trusted reference)
2. explicit operator confirmation prompt (skip with `--yes` for
   automated rigs)
3. CRC verify is enabled (the wrapper refuses `--no-verify`,
   `--skip-bootloader-check`, `--force-unsafe`)

After flashing, power-cycle the CONTROL once so the new code path is
active from cold boot rather than hot-reload.

During preflight/live flash the flasher reports the target
`V1.71 / rev 0xNN / build YYYYMMDD` from the hex. Unlike MAIN, the current CONTROL
update relay does not expose a live CONTROL version/revision probe
back to the host, so device-versus-hex compare is not available yet.

## Quick Checks

Read the CONTROL's reported version label after flashing. The visible
label remains `V1.71`; the monotonic release revision is a build-time
metadata field reported by the flash preflight, not a front-panel
string.

Walk Volume → RIGHT four times to reach PB1 Diag (V1.71 Tier-1 menu
state 4), then wait about 1 second without LEFT/RIGHT cycling.  The
LCD must update from any initial `PB1` / `n/a` render to either
`PB1` / `OK` (all-zero counters) or `PB1:` + cell entries (non-zero
counters).  Press RIGHT once more to reach PB2 Diag (state 5), wait about
1 second, and require the same static update behavior for PB2.

Run the strict static-wait gates after manually positioning CONTROL on
each page:

```bash
DLCP_HW_LAYER5_AT_DIAG=1 \
DLCP_HW_LAYER5_REQUIRE_PB1_DATA=1 \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_diagnostics_pb1_data_lands_on_real_silicon \
  --run-hardware

DLCP_HW_LAYER5_AT_DIAG=1 \
DLCP_HW_LAYER5_REQUIRE_PB2_DATA=1 \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_diagnostics_pb2_data_lands_on_real_silicon \
  --run-hardware
```

To verify Diagnostics does not starve normal IR/UI work, run:

```bash
DLCP_HW_LAYER5_AT_DIAG=1 \
DLCP_HW_LAYER5_IR_ACTIONS=1 \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_diagnostics_page_ir_actions_dispatch_on_real_silicon \
  --run-hardware
```

For the full Diagnostics page operator walk-through see
[`docs/HARDWARE_TEST.md`](HARDWARE_TEST.md) §"Diagnostics page".

## MAIN Pairing

V1.71 CONTROL is designed to pair with V3.2 MAIN.  Earlier MAINs
(V2.x, V3.0, V3.1) will continue to drive the chain for basic
volume/preset/input/setup operation, but the V1.71-specific features
behave as follows:

- **Diagnostics page** — visible in the menu, but PB rows render
  `n/a` permanently against a non-V3.2 MAIN because earlier MAIN
  releases don't know cmd 0x21.  Layer 5 was specifically designed so
  this degraded state never blocks the existing volume/input/setup
  behavior.
- **Layer 1 bounded TX** — always active; it's a CONTROL-side fix
  that doesn't require any MAIN-side change.
- **Layer 2 one-frame-per-trigger** — always active; benefits any
  MAIN release.

For new deployments, flash V3.2 MAIN alongside V1.71 CONTROL.  For
existing deployments running V3.1 MAIN, V1.71 CONTROL is a drop-in
CONTROL-only upgrade — the Diagnostics page just shows `n/a` until
the MAINs are upgraded.

## Compatibility Matrix

| CONTROL | MAIN | Notes |
|---|---|---|
| V1.71 | V3.2 | recommended; full Layer 5 Diagnostics + Layer 1/2 hardening |
| V1.71 | V3.1 | basic operation works; Diagnostics shows `n/a` |
| V1.71 | V3.0 | basic operation works; Diagnostics shows `n/a` |
| V1.71 | V2.x | basic operation works; Diagnostics shows `n/a` |
| V1.64b | V3.2 | basic operation works; no Diagnostics page in menu |

## Verification

Sim coverage for V1.71 in isolation and in chain combinations is in:

- `tests/sim/test_v171_baseline.py` (structural gates)
- `tests/sim/test_v171_preset_inline.py` (V1.61b feature parity)
- `tests/sim/test_v171_ir_endpoints.py` (V1.64b feature parity)
- `tests/sim/test_v171_fault_indicator.py` (V1.63b feature parity)
- `tests/sim/test_v171_reconnect_wake.py` (V1.62b feature parity)
- `tests/sim/test_v171_preset_menu.py` (V1.61b Phase B.4)
- `tests/sim/test_v171_full_sync_retry.py` (V1.61b Phase B.5)
- `tests/sim/test_v171_sentinel_reconnect.py` (V1.62b Phase C.3)
- `tests/sim/test_v171_v31_chain.py` (V1.71 × V3.1 MAIN chain)
- `tests/sim/test_v171_v32_standby_reconnect.py` (V1.71 × V3.2 standby/wake reconnect gate)
- `tests/sim/test_v171_layer5_diag_page.py` (Layer 5 Phase B)
- `tests/sim/test_v171_v32_layer5_diag_chain.py` (Layer 5 Phase C)

The WAITING-loop operator-recovery path is validated structurally
(assembler build + zero-regression diff against the pre-fix baseline
of 453 failures) and hand-traced against the codex review chain at
HEAD=`2a07c02`.  There is no behavioral sim test that drives the
button pins in a wedged WAITING state; operator validation is
covered in `docs/HARDWARE_TEST.md` §"WAITING FOR DLCP recovery".

See [`docs/HARDWARE_TEST.md`](HARDWARE_TEST.md) §"Diagnostics page"
for the live-rig walk-through of the Layer 5 path.  For Diagnostics
counter-specific release closure, also require the separate fault-injection
matrix and implementation plan linked above.

## Release Notes

- V1.71 is the recommended CONTROL release for chains paired with
  V3.2 MAIN.
- V1.64b remains the canonical fallback for chains paired with V3.1
  or earlier MAIN that do not need the Diagnostics page.
- V1.7 (the byte-identical source rebuild of stock V1.6b) is
  available as `src/dlcp_fw/asm/dlcp_control_v17.asm` for operators
  who want a source-built equivalent of the stock unpatched CONTROL.
