# V1.71 CONTROL Release Workflow

## Scope

This is the operator runbook for the recommended CONTROL deployment as
of 2026-04-21.

- recommended CONTROL release: `firmware/patched/releases/DLCP_Control_V1.71.hex`
- recommended MAIN release: `firmware/patched/releases/DLCP_Firmware_V3.2.hex`
  (see [`docs/V32_RELEASE.md`](V32_RELEASE.md) for the matching MAIN flow)
- recommended flashing path: use `scripts/flash_control_safe.sh`
  with `--hex firmware/patched/releases/DLCP_Control_V1.71.hex`

V1.71 supersedes V1.64b for chains paired with V3.2 MAIN.  V1.64b
remains the canonical fallback for chains running V3.1 / V2.x MAIN
that do not need the V1.71-specific features.

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
- **Layer 5 (Diagnostics page)** — adds a top-level menu entry
  `Diagnostics(2)` between `Preset(1)` and `Input(3)`.  When entered,
  CONTROL polls each PB with `cmd 0x21` on a ~1 s cadence and renders
  the seven returned counter values per PB on a compact 16x2 LCD
  layout.  See
  [`docs/V163B_DIAGNOSTICS_MENU_SPEC.md`](V163B_DIAGNOSTICS_MENU_SPEC.md).
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
  This is an operator-facing mitigation only; the underlying
  MAIN-side reconnect-burst gap is tracked in
  [`docs/V32_MAIN_HANG_HARDENING_PLAN.md`](V32_MAIN_HANG_HARDENING_PLAN.md)
  as an open hardening workstream.

EEPROM layout: V1.71 preserves the V1.6x preset slot at EEPROM
`0x74` and version-tuple format.  Existing CONTROL EEPROM contents
are read transparently — no re-baking required when upgrading from
V1.62b / V1.63b / V1.64b.

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

What the wrapper does:

1. bootloader-integrity preflight (refuses to flash if the bootloader
   region of the attached unit doesn't match the trusted reference)
2. explicit operator confirmation prompt (skip with `--yes` for
   automated rigs)
3. CRC verify is enabled (the wrapper refuses `--no-verify`,
   `--skip-bootloader-check`, `--force-unsafe`)

After flashing, power-cycle the CONTROL once so the new code path is
active from cold boot rather than hot-reload.

## Quick Checks

Read the CONTROL's reported version label after flashing.  V1.71
reports the same EEPROM version-byte tuple as V1.64b (so the bytes
the operator sees are the byte-stable layout); the visible difference
is the new top-level Diagnostics menu entry.  Walk Volume → RIGHT →
RIGHT and confirm the LCD shows `1:Ix...P` / `2:Ix...P` (or
`1:n/a` / `2:n/a` if no MAIN supports cmd 0x21).

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
- `tests/sim/test_v171_layer5_diag_page.py` (Layer 5 Phase B)
- `tests/sim/test_v171_v32_layer5_diag_chain.py` (Layer 5 Phase C)

The WAITING-loop operator-recovery path is validated structurally
(assembler build + zero-regression diff against the pre-fix baseline
of 453 failures) and hand-traced against the codex review chain at
HEAD=`2a07c02`.  There is no behavioral sim test that drives the
button pins in a wedged WAITING state; operator validation is
covered in `docs/HARDWARE_TEST.md` §"WAITING FOR DLCP recovery".

See [`docs/HARDWARE_TEST.md`](HARDWARE_TEST.md) §"Diagnostics page"
for the live-rig walk-through of the Layer 5 path.

## Release Notes

- V1.71 is the recommended CONTROL release for chains paired with
  V3.2 MAIN.
- V1.64b remains the canonical fallback for chains paired with V3.1
  or earlier MAIN that do not need the Diagnostics page.
- V1.7 (the byte-identical source rebuild of stock V1.6b) is
  available as `src/dlcp_fw/asm/dlcp_control_v17.asm` for operators
  who want a source-built equivalent of the stock unpatched CONTROL.
