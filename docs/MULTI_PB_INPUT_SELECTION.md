# Multi-PB Input Selection Persistent Settings

Date: 2026-06-22
Status: Implemented in local CONTROL V1.73 x53 candidate
Related docs:

- `docs/MULTI_PB_INPUT_SELECTION_SPEC.md`
- `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`
- `docs/MULTI_PB_INPUT_SELECTION_PERSISTENCE_IMPL.md`

V1.73 x52 multi-PB input selection was runtime-only: PB2 started as
`Same as PB1` after PB2 discovery and no PB2 input state was persisted in
CONTROL EEPROM.  The local V1.73 x53 candidate adds persistent PB2 input
settings with a deliberately narrow EEPROM encoding.  EEPROM is still treated
as untrusted input and decoded before any menu, table, route, or current-loop
command path can use it.

This file is the canonical persistence guardrail.  It must be committed or
otherwise tracked with any persistence implementation; do not leave persistence
rules only in scratch notes or terminal output.

## Current Persistent Contract

CONTROL owns one new EEPROM byte:

| Address | Owner | Values | Default/migration behavior |
| ---: | --- | --- | --- |
| `0x5F` | CONTROL PB2 input persistence | `0xA0`, `0xB0..0xB8` | `0xFF` and every unknown byte decode as `PB2 = Same as PB1` |

EEPROM ownership audit summary:

- Existing CONTROL settings load/save owns `0x00..0x2D` plus `0x73`.
- V1.7x identity/preset bytes already own `0x70..0x74`.
- Stock/user bytes `0x75..0xFE` are not used for PB2 persistence.
- `0x5F` is erased (`0xFF`) in the baked CONTROL image and is not touched by
  the existing settings load/save paths before this feature.

Encoding:

| EEPROM byte | Meaning after sanitized decode |
| ---: | --- |
| `0xA0` | linked, PB2 follows PB1 via broadcast (`Same as PB1`) |
| `0xB0` | concrete PB2 Auto Detect, `cmd 0x06` payload `0x00` |
| `0xB1` | concrete PB2 Analogue 1, payload `0x01` |
| `0xB2` | concrete PB2 Analogue 2, payload `0x02` |
| `0xB3` | concrete PB2 Analogue 3, payload `0x03` |
| `0xB4` | concrete PB2 Analogue 4, payload `0x04` |
| `0xB5` | concrete PB2 S/PDIF, payload `0x05` |
| `0xB6` | concrete PB2 USB Audio, payload `0x06` |
| `0xB7` | concrete PB2 AES, payload `0x07` |
| `0xB8` | concrete PB2 Optical, payload `0x08` |
| anything else, including `0xFF` | linked default |

Load behavior:

- `settings_load_eeprom` calls `input_pb2_persist_load`.
- Load clears dirty/fallback state and decodes only the bytes above.
- Concrete values are stored as pending sanitized state; they do not set
  `PB2_SEEN`, do not expose `Input PB2`, and do not send addressed PB2 frames.
- `input_split_latch_pb2_seen` applies the pending value only after existing
  PB2 health or Diagnostics evidence discovers PB2.

Save behavior:

- User changes on the PB2 Input page set a dirty flag.
- `settings_save_eeprom` calls `input_pb2_persist_save_if_dirty`.
- Save re-encodes only sanitized linked/concrete runtime state.
- Save compares the encoded byte with EEPROM and skips writes when unchanged.
- Runtime fallback caused by an unavailable persisted concrete source does not
  overwrite the persisted byte on unrelated settings saves.

## Required Guardrails

1. EEPROM ownership first

   Pick a documented unused byte only after an EEPROM map audit.  Do not reuse
   stock/user bytes like `0x75..0xFE` casually.  The audit must update the
   EEPROM layout docs and tests before source code starts reading or writing
   the new byte.  The audit deliverable is a byte-by-byte `0x00..0xFF` map with
   owner, current use, stock/current values, migration default, preservation
   rule, and rollback behavior.

2. Treat `0xFF` as normal first-boot input

   Erased EEPROM is `0xFF`.  Load code must explicitly map `0xFF` and all
   unknown values to a safe default, normally `PB2 = Same as PB1`.

3. Validate on load before use

   The EEPROM byte must never directly become a menu index, table index, route
   byte, or `cmd 0x06` payload.  Load must decode the raw byte into the existing
   runtime representation only after allowlist validation.

4. Validate again at use sites

   Even after sanitized load, keep defensive clamps before:

   - LCD label lookup
   - menu UP/DOWN wrap
   - `cmd 0x06` mapping
   - full-sync / targeted PB2 send

5. Use allowlists, not loose ranges

   If valid persisted values are `{linked, auto, spdif, usb, aes, optical,
   analogue1, analogue2, analogue3, analogue4}`, decode only those values.
   Unknown means default.  Do not accept a broad numeric range and then depend
   on later code to reject holes.

6. Test all invalid values

   Add exhaustive decoder coverage for every preload value in `0x00..0xFF`.
   Every non-allowlisted byte must decode to `PB2 = Same as PB1`.  Boot tests
   must include at least `0xFF`, `0x80`, and `0x7F`, then assert no garbage LCD,
   no invalid frame, and no reset/hang.

7. Require a migration discriminator

   A legacy byte that numerically matches a future enum must not be trusted as
   an intentional PB2 setting.  Either prove the selected byte is erased/unused
   across all supported stock/current images and captured field EEPROMs, or use
   a schema marker/versioned encoding.  Without that proof or marker, every
   pre-migration value must decode to `PB2 = Same as PB1`.

8. Keep persisted PB2 state latent until PB2 discovery

   Loading a valid PB2 setting must not set `PB2_SEEN`, must not expose the PB2
   page on a single-PB/PB2-unknown system, and must not change legacy broadcast
   sends.  Decode into a pending/sanitized value at boot, then apply it only
   when existing health or Diagnostics evidence discovers PB2.

9. Do not rely on release flash to initialize EEPROM

   The current CONTROL app flash path does not program EEPROM defaults.  A
   persistence implementation must migrate in firmware boot/save logic and
   prove release-flash/settings preservation explicitly.

10. Protect EEPROM endurance

   Persist only on explicit user save/commit paths.  Compare with the current
   EEPROM or a shadow byte and skip writes when unchanged.  Navigation, redraw,
   health polling, reconnect, full-sync, and relink cycles must not write
   EEPROM by themselves.

## Minimal Persistent Encoding Contract

Do not persist UI row numbers, route bytes, or live MAIN state.  Persist one
CONTROL-owned PB2 setting enum at EEPROM `0x5F` and decode it to the current
runtime model:

```text
linked      -> set PB2_LINKED; PB2 follows PB1 via broadcast
auto        -> clear PB2_LINKED; input_intent_pb2 = 0x00
spdif       -> clear PB2_LINKED; input_intent_pb2 = 0x05
usb         -> clear PB2_LINKED; input_intent_pb2 = 0x06
aes         -> clear PB2_LINKED; input_intent_pb2 = 0x07
optical     -> clear PB2_LINKED; input_intent_pb2 = 0x08
analogue1   -> clear PB2_LINKED; input_intent_pb2 = 0x01
analogue2   -> clear PB2_LINKED; input_intent_pb2 = 0x02
analogue3   -> clear PB2_LINKED; input_intent_pb2 = 0x03
analogue4   -> clear PB2_LINKED; input_intent_pb2 = 0x04
unknown/0xFF/pre-migration -> set PB2_LINKED; PB2 follows PB1 via broadcast
```

The stored enum uses `0xA0` for linked and `0xB0..0xB8` for the concrete
source payloads above.  The `0xA*`/`0xB*` discriminator avoids accidentally
accepting legacy raw `cmd 0x06` values such as `0x00..0x08` as intentional PB2
settings.  The decoder is closed: every other byte defaults to linked mode.

If a valid persisted concrete source is not available in the current
`raw_status_cache` source-list class, the runtime fallback for that boot is
linked `Same as PB1`; do not send a hidden unavailable source.  Do not overwrite
the persisted byte merely because the source was unavailable unless the user
explicitly saves a new PB2 setting.  A generic settings save caused by an
unrelated menu change must preserve the original persisted PB2 enum while this
fallback is active.

Raw field EEPROM captures used to prove ownership or migration safety are local
evidence only.  Shared or committed docs should contain byte ownership,
classification, migration decisions, redacted value summaries, and hashes where
useful, not raw EEPROM dumps.

## Acceptance Requirements

- First boot on erased EEPROM (`0xFF`) always behaves like `Same as PB1`.
- Corrupt EEPROM cannot select an invalid LCD row or emit an invalid
  `cmd 0x06` payload.
- Existing PB2 row clamps and targeted-send clamps remain in place; persistence
  does not replace them.
- Release-flash/settings-preservation gates must prove the new byte is
  preserved or intentionally initialized according to the documented migration
  rule before hardware deployment closure.
- Valid persisted settings stay pending and inactive until PB2 discovery; before
  PB2 discovery the UI remains legacy `Input:` and sends remain broadcast.
- Repeated navigation, redraw, health, reconnect, full-sync, and relink cycles
  do not write the PB2 EEPROM byte.

## Implementation Evidence

Implemented files:

- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `tests/sim/test_v173_multi_pb_input_selection.py`
- `src/dlcp_fw/sim/dlcp_sim_native.py`
- `crates/dlcp-sim-py/src/lib.rs`

Simulator evidence run during implementation:

```bash
.venv/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'pb2_full_sync_clamps_corrupt_intent or malformed_pb2_state_recovers_to_active_max_commit or pb2_same_as_pb1_down_clamps_unknown_raw_status'
.venv/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'decoder_is_closed_allowlist or display_state_save_load_remaps or pb2_menu_state_and_malformed_row'
.venv/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'user_selected_concrete_round_trips or same_as_pb1_round_trips or split_display_states_save or malformed_bf06_payloads or dirty_flag_prevents'
.venv/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'every_user_selected_concrete or valid_pb2_eeprom_stays_pending or corrupt_runtime_pb2_intent or navigation_full_sync_and_relink'
.venv/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -n 8
PYTHONPATH=src .venv/bin/python scripts/check_ram_access_safety.py --target control-v173
```

The focused persistence subsets passed, including the all-concrete save/readback
and endurance additions: latest added subset `4 passed, 107 deselected`.
The full multi-PB file passed: `111 passed`.
RAM bank safety passed for `control-v173`.
