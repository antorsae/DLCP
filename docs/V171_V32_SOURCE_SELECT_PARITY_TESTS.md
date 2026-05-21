# V1.71/V3.2 Source-Select Parity Tests

Status: implemented in `tests/sim/test_v171_v32_source_select_parity.py`

Scope: source selection in a two-MAIN DLCP chain, comparing stock
`V1.6b CONTROL + V2.3 MAIN` against current `V1.71 CONTROL + V3.2 MAIN`.

## Why This Exists

The RCA S/PDIF hardware test exposed a gap in our simulator coverage. We had
V3.2-only checks for selected SRC4382 behavior and one front-panel S/PDIF
regression, but we did not have a stock-vs-current two-PB parity matrix for
manual source selection. That meant a CONTROL/menu or MAIN command-routing
change could silently diverge between PB1 and PB2 without a parity test
catching it.

## Tested Surfaces

### CONTROL menu protocol parity

Test: `test_front_panel_input_menu_emits_same_manual_source_sequence_as_stock`

This boots both chains, navigates to the `Input` menu, presses `UP` through one
full fixed-input cycle, and compares emitted `B0/06/<input>` frames.

Expected sequence:

| Displayed source | Emitted input byte |
| --- | ---: |
| S/PDIF | `0x05` |
| USB Audio | `0x06` |
| AES | `0x07` |
| Optical | `0x08` |
| Analogue 1 | `0x01` |
| Analogue 2 | `0x02` |
| Analogue 3 | `0x03` |
| Analogue 4 | `0x04` |

This catches CONTROL-side menu-ring regressions, including the V1.71 state-index
shift caused by the added Preset and PB diagnostics pages.

### MAIN manual-source route parity matrix

Test: `test_manual_source_route_matrix_matches_stock_for_both_pb_roles`

This injects every manual `cmd 0x06` input byte `0x01..0x08` under each seeded
MAIN source-status value `0x00..0x03`. The test freezes UART forwarding and
places the same frame in PB1 and PB2 RX queues so the seeded `BF/05` status is
not overwritten by live background status frames while the command is settling.
For every case it checks both PB roles:

- `input_select`
- `input_select_mirror`
- `src_route_request`
- `route_shadow`

The expected route matrix is pinned to the stock `V1.6b + V2.3` behavior:

| `BF/05` status | `0x01` | `0x02` | `0x03` | `0x04` | `0x05` | `0x06` | `0x07` | `0x08` |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0x00` | `0` | `1` | `3` | `3` | `4` | `0` | `0` | `0` |
| `0x01` | `0` | `5` | `1` | `3` | `3` | `4` | `0` | `0` |
| `0x02` | `0` | `5` | `6` | `1` | `3` | `3` | `4` | `0` |
| `0x03` | `0` | `5` | `6` | `7` | `1` | `3` | `3` | `4` |

This is the parity test that answers whether manual source selection is PB1-only
or applies to both MAINs. Expected behavior is that PB1 and PB2 both consume the
same `B0/06` selection and converge to the same route state. The separate
front-panel S/PDIF test below covers live CONTROL-to-PB1-to-PB2 forwarding.

### Front-panel S/PDIF end-to-end parity

Test: `test_displayed_spdif_front_panel_path_matches_stock_for_both_pb_roles`

This models the user-observed path: from Auto Detect, navigate to `Input`, press
`UP` once to select displayed `S/PDIF`, and then verify:

- CONTROL emits `B0/06/05`
- both PB1 and PB2 set input `0x05`
- both PB1 and PB2 request/shadow route `1`
- both SRC4382 models converge to `0x0D=0x09`, `0x08=0x70`
- both MAINs refresh the TAS3108 volume coefficient

This is the direct regression for the RCA S/PDIF manual-input report.

### Current V3.2 SRC4382 hardening on both PB roles

Test: `test_current_source_present_routes_program_src4382_on_both_pb_roles`

This is deliberately not a stock-parity assertion. Stock V2.3 does not always
rewrite the SRC4382 receiver/transmitter pair on external-mux routes after Auto
Detect. V3.2 intentionally improves that behavior by priming the default
receiver route for `0/5/6/7`.

The test proves the improvement applies to both PB roles in the two-MAIN chain:

- explicit source commands invalidate stale route state
- PB1 and PB2 both converge to the expected route
- PB1 and PB2 both write the expected SRC4382 receiver/transmitter pair
- PB1 and PB2 both refresh TAS3108 volume after the source transition

### Auto Detect selected-state parity

Test: `test_autodetect_startup_selected_state_matches_stock_for_both_pb_roles`

This verifies startup selected-source state only:

- `input_select == 0`
- `input_select_mirror == 0`
- `src_route_request == 0`
- `route_shadow == 0`

It intentionally does not compare Auto Detect SRC4382 polling cadence, because
V3.2 reduced that cadence by design. Cadence and debounce behavior remain covered
by `tests/sim/test_v32_src4382_autodetect_polling.py`.

## Non-Goals

- No acoustic assertion. These tests prove firmware route/SRC programming, not
  whether a physical RCA/USB/AES/optical cable is attached to a given MAIN.
- No byte-for-byte SRC4382 traffic parity for routes where V3.2 intentionally
  improves stock behavior.
- No Auto Detect cadence parity, because reduced polling and source-loss
  debounce are deliberate V3.2 changes.

## Targeted Command

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v171_v32_source_select_parity.py
```
