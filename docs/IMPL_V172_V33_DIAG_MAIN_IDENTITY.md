# V1.72/V3.3 Diagnostics MAIN Identity - Implementation Guide

Last updated: 2026-05-29
Status: implemented for V1.72/V3.3 Diagnostics identity; preset filename work
remains separate and out of scope for this change.
Targets: CONTROL V1.72+ and MAIN V3.3+.

## Why This Is Separate From `V32_DIAG_TIER1_SPEC.md`

`docs/V32_DIAG_TIER1_SPEC.md` is the locked V1.71/V3.2 baseline: runtime
diagnostics (`cmd 0x21`), reset-cause diagnostics (`cmd 0x22`), health ping
(`cmd 0x23`), and HID `cmd 0x44`.

This feature is a successor feature. It changes neither V1.71 nor V3.2. Keep
the detailed protocol, RAM, render, flashing, and red/green implementation plan
here so the V3.2 spec remains a stable reference for deployed units.

Related docs:

- `docs/V32_DIAG_TIER1_SPEC.md` - implemented diagnostics baseline.
- `docs/V171_V32_LINK_HEALTH_FRESHNESS_SPEC.md` - stale/lost semantics.
- `docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md` - counter/fault coverage.
- `docs/PRESET_FILENAME_LCD_SPEC.md` - separate V1.72/V3.3 preset filename
  feature; coordinate command/reply ranges, parser order, and BANK 2 RAM if
  both features land together.

## User-Facing Behavior

Current healthy Diagnostics page:

```text
PB1 OK
S1 B1 O1
```

V1.72/V3.3+ target behavior when the visible PB has a valid MAIN identity:

```text
PB1 OK v3.3 x71
S1 B1 O1
```

The requested full spelling `PB1 OK v3.3 rev x71` does not fit on a 16-column
LCD row. The LCD format is therefore:

```text
PBn OK vM.m xRR
```

This is 15 characters for single-digit major/minor and a two-hex-digit release
revision, leaving one trailing pad. Host tools and docs should continue to
spell the same marker as `rev 0xRR`.

Display priority:

- Fresh + healthy + valid identity: row 0 `PBn OK vM.m xRR`, row 1 unchanged
  OK-context `S/B/O` tokens or blank.
- Fresh + healthy + no identity: current row 0 `PBn OK`, row 1 unchanged.
- Fresh + issue: current `PBn! ...` layout; omit identity even if a valid
  identity is cached.
- Stale/lost: current `PBn old` / `PBn lost`; omit identity and invalidate the
  cached identity for that PB.
- Never seen: current `PBn` / `n/a`; omit identity.
- If a future version string cannot fit `PBn OK vM.m xRR`, fall back to
  `PBn OK`; do not truncate into row-1 counters.

## Chain Protocol

Do not change existing diagnostics contracts:

- `cmd 0x21` remains the 7-frame runtime burst, `BF/21..BF/27`.
- `cmd 0x22` remains the 4-frame reset-cause burst, `BF/28..BF/2B`.
- `cmd 0x23` remains the one-frame health ping, `BF/2C`.
- HID `cmd 0x44` remains the 11-cell MAIN-local diag snapshot.
- Preset filename, if implemented, keeps `cmd 0x24` and `BF/2F..BF/4E`.

Add one addressed query:

```text
CONTROL -> MAIN: [B1/B2, 0x25, id]
```

Route rules:

- `B1` addresses PB1.
- `B2` is forwarded by PB1 to downstream PB2; PB1 must not answer a `B2`
  identity query.
- PB2 replies are forwarded upstream by PB1 unchanged.
- Every reply data byte must remain `< 0x80` so no byte can be misread as a
  route byte by the current-loop forwarder.

`id` is a chain-safe byte chosen by CONTROL:

```text
bit 0      target PB index: 0 = PB1, 1 = PB2
bits 5..1  5-bit generation counter
bit 6      0
bit 7      0
```

So:

```text
id = ((gen & 0x1F) << 1) | pb_index
```

MAIN echoes `id` in the START frame so CONTROL can reject stale replies after a
page flip, timeout, or PB1->PB2 query transition. A 5-bit generation gives the
same stale-reply safety class as the filename protocol while staying
route-safe.

Reply:

```text
Frame  Byte    Data                 Meaning
  1    BF/4F   id                   START, echo CONTROL query id
  2    BF/50   major low nibble      e.g. 0x03 for V3.x
  3    BF/51   minor low nibble      e.g. 0x03 for V3.3
  4    BF/52   release rev high nibble
  5    BF/53   release rev low nibble    LAST FRAME
```

Example: V3.3 / rev `0x71`, query id `0x04`, replies:

```text
BF 4F 04
BF 50 03
BF 51 03
BF 52 07
BF 53 01
```

CONTROL accepts the transaction only when:

- identity query `PENDING` is set,
- `BF/4F.data == pending_id`,
- frames then arrive in exact order `BF/50`, `BF/51`, `BF/52`, `BF/53`, and
- non-START payload data is `0x00..0x0F`.

Namespace rationale:

- `BF/25` is already a runtime reply byte for counter `R`, but that is in the
  reply namespace. Request `cmd 0x25` is free after V3.3's planned `cmd 0x24`
  filename query.
- `BF/2D..BF/2E` stay unused as the gap between health (`BF/2C`) and filename
  (`BF/2F..BF/4E`).
- `BF/4F..BF/53` sits immediately after the filename range and is disjoint from
  all V1.71/V3.2 diagnostic reply ranges.
- The release revision is split into nibbles so revs above `0x7F` never put a
  data byte `>= 0x80` on the chain.

## MAIN V3.3 Changes

Files expected:

- `src/dlcp_fw/asm/dlcp_main_v33.asm`
- `scripts/build_v33_release.py`
- `firmware/patched/releases/DLCP_Firmware_V3.3.hex`
- `src/dlcp_fw/flash/dlcp_v33_release_flash.py`
- `scripts/dlcp_v33_release_flash.py`
- `tests/sim/test_dlcp_v33_release_flash.py`
- `src/dlcp_fw/paths.py` constants for V3.3 source/release paths
- `src/dlcp_fw/sim/v30_symbols.py` canonical `.lst` fallback for V3.3
- `AGENTS.md`, `docs/RELEASE_ARCHIVE.md`, and release docs updated in the same
  change

Implementation steps:

1. Version tuple:
   - HID `cmd 0x06` major/minor should report `3.3`.
   - EEPROM identity tuple is at EEPROM offsets `0x80..0x82`:
     `EEPROM[0x80] = 0x03`, `EEPROM[0x81] = 0x03`, `EEPROM[0x82] = rev`.
   - In source terms, `eeprom_data[0x80]` is major, `[0x81]` is minor, and
     `[0x82]` is the release rev. Do not place the tuple at `0x82..0x84`.
   - The build script must derive all identity bytes from one `new_rev` value
     and rewrite the static EEPROM tuple, the boot-time EEPROM migration
     literals for `EEPROM[0x80]`, `[0x81]`, and `[0x82]`, and the `cmd 0x25`
     identity literals.
   - The MAIN flasher streams app flash and does not program Intel HEX EEPROM
     records; post-flash readback must therefore verify live EEPROM
     `0x80..0x82` equals the target tuple.

2. Dispatch:
   - Add `cmd 0x25` in `cmd_dispatch_xor_chain`.
   - If `cmd 0x24` filename support lands first, the XOR chain after `cmd 0x23`
     should be:
     ```asm
     xorlw 0x07            ; 0x23 ^ 0x24 = cmd 0x24
     btfsc STATUS,2,ACCESS
     goto  cmd24_filename_query_handler
     xorlw 0x01            ; 0x24 ^ 0x25 = cmd 0x25
     btfsc STATUS,2,ACCESS
     goto  cmd25_identity_query_handler
     ```
   - If filename support is not present in a branch, use the direct cumulative
     delta from `0x23` to `0x25` and keep tests explicit.

3. Handler:
   - Read the query `id` from the existing parsed data byte staging cell.
   - Mask `id` to `< 0x40`; mask major, minor, rev_hi, and rev_lo with
     `andlw 0x0F` before transmit.
   - Emit five complete frames: `BF/4F/id`, `BF/50/major`, `BF/51/minor`,
     `BF/52/rev_hi`, `BF/53/rev_lo`.
   - MAIN space is tight: emit only the `BF/4F/id` START frame explicitly,
     stage major/minor/rev nibbles in scratch RAM, and reuse the existing
     `diag_send_burst_xx` loop for `BF/50..BF/53`.
   - Suppress the legacy unknown-command ACK echo before the parser tail:
     `bcf active_flags, 6, ACCESS`.
   - A blocking five-frame transaction is acceptable only because CONTROL
     serializes identity against `cmd 0x21`/`cmd 0x22`; the compact handler
     keeps the code-size cost low while preserving atomic frame ordering.

4. Source of truth:
   - Major/minor must match HID `cmd 0x06`.
   - Rev must match live EEPROM `0x82`.
   - Tests must assert that `BF/50`, `BF/51`, and reconstructed `BF/52..BF/53`
     match `detect_static_hex_eeprom_version(V33_MAIN_HEX)` and live post-flash
     EEPROM readback.

## CONTROL V1.72 Changes

Files expected:

- `src/dlcp_fw/asm/dlcp_control_v172.asm`
- `scripts/build_v172_release.py`
- `firmware/patched/releases/DLCP_Control_V1.72.hex`
- `src/dlcp_fw/paths.py` constants for V1.72 source/release paths

Suggested BANK 2 allocation if the preset filename feature also uses
`0x220..0x244`:

```text
0x245  v172_diag_id_pb1_major
0x246  v172_diag_id_pb1_minor
0x247  v172_diag_id_pb1_rev
0x248  v172_diag_id_pb2_major
0x249  v172_diag_id_pb2_minor
0x24A  v172_diag_id_pb2_rev
0x24B  v172_diag_id_valid_mask      ; bit0 PB1, bit1 PB2
0x24C  v172_diag_id_seen_mask       ; bit0 PB1 queried/gave-up, bit1 PB2
0x24D  v172_diag_id_pending_id
0x24E  v172_diag_id_flags           ; bit0 PENDING, bit1 TARGET
0x24F  v172_diag_id_timeout
0x250  v172_diag_id_next_gen        ; 5-bit generation source
0x251  v172_diag_id_expected_cmd    ; 0x4F..0x53 while pending
0x252  v172_diag_id_tmp_major       ; staged, not committed until BF/53
0x253  v172_diag_id_tmp_minor
0x254  v172_diag_id_tmp_rev_hi
```

### Query Scheduling And State

Identity is static metadata. Do not poll it once per second.

Per-PB epoch rules:

- Clear `valid_mask`, `seen_mask`, and any matching pending transaction on
  wake, reconnect, or link-health stale/lost transition for that PB.
- If a PB becomes stale/lost while visible, mark the Diagnostics page dirty and
  suppress identity immediately.
- If a stale/lost PB later becomes fresh while the operator is still parked on
  that PB page, schedule one identity query in the new epoch.
- If an issue counter makes the page `PBn!`, keep any cached identity but do not
  render it. When the issue clears and the PB is fresh, the suffix may reappear.

Scheduling rules:

- On PB Diagnostics page entry, clear the visible PB's `seen` bit so that a
  page re-entry retries after a previous timeout.
- If `PENDING` targets the other PB on page entry/page flip, cancel that pending
  transaction, clear `PENDING`, allocate a new generation id, and query the
  visible PB. Late replies with the old id are discarded.
- Schedule identity only when the visible PB is fresh, `valid` is clear,
  `seen` is clear, `PENDING` is clear, and runtime/reset diagnostic pending
  bits are clear.
- CONTROL must not issue `cmd 0x25` in the same cadence cycle as `cmd 0x21` or
  `cmd 0x22`. After sending `cmd 0x25`, pause `cmd 0x21`/`cmd 0x22` sends until
  `BF/53` or identity timeout. This prevents a page-entry burst of
  `7 + 4 + 5 = 16` frames from exactly filling the 48-byte CONTROL RX ring.
- Use an atomic `tx_ring_reserve_3`-style sender. On TX saturation, emit no
  bytes, do not set `PENDING`, do not advance `next_gen`, and retry later.
- On successful enqueue, snapshot target and `pending_id`, set
  `expected_cmd = 0x4F`, set `PENDING`, and advance `next_gen`.
- On timeout, clear `PENDING`, set `seen` for that PB, leave `valid` clear, and
  do not retry until page re-entry, wake, reconnect, or stale/lost recovery
  clears `seen`.

Do not send identity queries through the old V1.71 diagnostics helper as-is.
That helper is specialized for `cmd 0x21`/`cmd 0x22`, sends data `0x00`, and
has two-way abort cleanup. Use a dedicated identity sender or extend the shared
helper to accept a data byte and to dispatch abort cleanup separately for
`0x21`, `0x22`, and `0x25`.

### Parser

Add a separate parser for `BF/4F..BF/53`; do not widen the existing
`BF/21..BF/2B` diagnostics parser.

Parser ordering with filename support:

- The identity range check must run before the filename parser's
  `cmd >= 0x4F -> tail` exit, or the filename upper-exit branch must fall
  through to identity parsing before the common tail.
- Tests must pin `BF/4E` as filename END, `BF/4F` as identity START, and
  `BF/54` as ignored.

State machine:

- While `expected_cmd == 0x4F`, accept only `BF/4F` with data equal to
  `pending_id`. A mismatched `BF/4F` is a stale START: ignore it and leave
  `PENDING`, `expected_cmd`, and caches unchanged.
- While waiting for START, stray identity middle/end frames (`BF/50..BF/53`) are
  ignored and leave the pending transaction alive until timeout.
- After a matching START, require exact command order: `0x50`, `0x51`, `0x52`,
  `0x53`.
- Non-START payload bytes must be `0x00..0x0F`. A larger payload byte after a
  matching START aborts the transaction.
- Do not overwrite committed PB major/minor/rev cells until `BF/53` validates.
  Stage major/minor/rev_hi in temp cells and commit the complete tuple only on
  `BF/53`.
- On in-transaction bad order, invalid payload, or timeout: clear `PENDING`,
  leave `valid` clear, do not disturb runtime/reset caches, and mark `seen` on
  timeout only.
- `BF/21..BF/2B` diagnostic replies and `BF/2F..BF/4E` filename replies do not
  alter identity phase or caches.

Banking and scratch contract:

- Every `v172_diag_id_*` BANKED access must self-assert `movlb 0x02`.
- Every `BF/4F..BF/53` parser exit path, including success, mismatch, bad
  order, timeout, and ignored stale START, must restore `movlb 0x00` before
  branching to the parser tail.
- Identity LCD helpers must not keep live values in access scratch across
  `lcd_char_write`; reload from BANK 2 or use dedicated BANK 2 temp cells.

### Rendering

- In the healthy branch only, after writing `PBn OK`, check the valid bit.
- If valid and the format fits, emit ` vM.m xRR` then pad to 16.
- Exact healthy row with identity must be `PB1 OK v3.3 x71 `, length 16.
- If invalid/unavailable, keep current `PBn OK` + spaces.
- Row 1 remains the current OK-context `S/B/O` sparse line.
- Issue/stale/lost/n/a branches must not call the identity renderer.

### Backwards Compatibility

- V1.72 + V3.2: old MAIN has no `cmd 0x25` handler and may echo the query data
  byte. Since `id < 0x40`, CONTROL treats it as stray non-route data, times out
  identity, and keeps current `PBn OK`.
- V1.71 + V3.3: old CONTROL never sends `cmd 0x25`.
- V1.72 + mixed V3.2/V3.3 MAINs: each PB can independently have identity valid
  or invalid; diagnostics counters still render normally.

Mixed-version matrix:

| PB1 MAIN | PB2 MAIN | Expected PB1 row | Expected PB2 row |
|---|---|---|---|
| V3.2 | V3.2 | `PB1 OK` | `PB2 OK` |
| V3.3 rev N | V3.2 | `PB1 OK v3.3 xNN` | `PB2 OK` |
| V3.2 | V3.3 rev M | `PB1 OK` | `PB2 OK v3.3 xMM` |
| V3.3 rev N | V3.3 rev M | `PB1 OK v3.3 xNN` | `PB2 OK v3.3 xMM` |

For all rows, issue/stale/lost/n/a states override identity.

## Test Plan

Implemented coverage:

- `tests/sim/test_v172_v33_diag_identity.py`
  - compact V3.3 cmd `0x25` handler structure
  - V1.72 identity parser/scheduler source wiring
  - V1.72 boot splash and Waiting row-2 cleanup
  - PB1 and PB2 healthy LCD identity titles through the two-MAIN chain
  - IR volume, mute, preset, standby, and wake dispatch while parked on PB1/PB2
    identity-enabled Diagnostics pages
  - issue-state suffix suppression
  - V1.72 + V3.2 backward compatibility after identity timeout
- `tests/sim/test_v172_v33_release_builders.py`
  - V3.3 builder bumps EEPROM/runtime/cmd25 identity revision literals
  - V3.3/V1.72 builders roll source/HEX/listing back on assembly failure
  - V1.72 builder keeps metadata, build date, and boot banner synchronized
- `tests/sim/test_dlcp_v33_release_flash.py`
  - V3.3 release wrapper forwards canonical release args
  - missing local preset captures warn and flash the unbaked release
  - info-only passthrough and explicit-route enforcement
- `tests/sim/test_firmware_version_label.py`
  - V3.3 HID major/minor, EEPROM major/minor, and release revision stay in sync
- `tests/sim/test_dlcp_control_flash_safety.py`
  - V1.72 static release metadata detection
  - V1.72 preflight target identity output
  - `flash_control_safe.sh` defaults to V1.72

MAIN source tests:

- `cmd 0x25` dispatch exists after `cmd 0x24` when filename support is present.
- Handler emits exactly `BF/4F..BF/53` and suppresses the legacy ACK echo.
- START id is `< 0x40`; major/minor/rev payload bytes are `<= 0x0F`; every
  emitted data byte is `< 0x80`.
- Emitted major/minor match the HID `cmd 0x06` tuple.
- Emitted rev nibbles reconstruct EEPROM release marker `0x82`.

MAIN build/flasher tests:

- `build_v33_release.py` bumps exactly once and updates static EEPROM tuple,
  boot-time EEPROM migration literals, and `cmd 0x25` identity literals.
- Failed `gpasm` rolls back source, release HEX, and source-side `.lst`.
- Static HEX probes report HID `3.3` and EEPROM tuple `3.3 rev 0xRR`.
- `scripts/dlcp_v33_release_flash.py --preflight-only --verbose` prints target
  firmware version `3.3` and target EEPROM revision `0xRR`.
- Sim/live post-flash readback shows live EEPROM `0x80..0x82` equals the target
  tuple; a mutation where HID is `3.3` but EEPROM/runtime rev is stale fails.

CONTROL source tests:

- Identity reply parser range is `BF/4F..BF/53`; diagnostics range remains
  `BF/21..BF/2B`.
- Filename parser coexistence: `BF/4E` is filename END, `BF/4F` is identity
  START, and `BF/54` is ignored.
- Parser does not set valid until `BF/53`.
- Parser routes through pending id/target snapshot, not live `v171_diag_target`.
- Healthy renderer has exact row 0 `PB1 OK v3.3 x71 `, including trailing pad.
- Issue/stale/lost/n/a renderers omit identity.
- BANK 2 and BSR discipline: all identity RAM accesses assert `movlb 0x02`;
  all parser exits restore `movlb 0x00`.
- Dedicated identity sender uses atomic 3-byte reserve/enqueue and does not use
  the old diag helper with data forced to `0x00`.

Behavioral tests:

- V1.72 + V3.3 PB1 rev `0x71`, PB2 rev `0x70` show independent identities.
- OK-context counters render on row 1 under the identity title, e.g. row 0
  `PB1 OK v3.3 x71 ` and row 1 `S1 B1 O1        `.
- O-only reset context still uses the healthy identity title and never `PBn!`.
- V1.72 + V3.2 times out identity and still accepts subsequent `cmd 0x21` /
  `cmd 0x22` replies without parser drift.
- Back-to-back `cmd 0x22` + `cmd 0x21` + `cmd 0x25` must be rejected by the
  scheduler; identity waits for runtime/reset pending bits to clear.
- TX saturation during identity send emits no partial frame, leaves `PENDING`
  clear, does not advance generation, and retries later.
- PB1 pending -> flip to PB2 cancels PB1 pending; a late PB1 START does not
  prevent the matching PB2 identity from validating.
- Health stale/lost invalidates cached identity; fresh recovery while visible
  schedules one new identity query.
- Cached identity + later issue counter/reset flag renders `PBn!` with no
  `v3.3`/`xRR`; clearing the issue restores the suffix only in the healthy
  branch.
- Cached identity + stale/lost/n/a renders no suffix; stale/lost also clears
  identity validity for that PB.
- Rev `0xA0` renders as `xA0` and no chain data byte `>= 0x80` appears.
- PB1 forwards `B2/25/id` to PB2 without answering; PB2 identity replies are
  forwarded upstream unchanged.

Malformed protocol table:

| Sequence | Expected result |
|---|---|
| `BF/50..BF/53` without matching `BF/4F` | no valid bit; pending waits until timeout; next clean transaction commits |
| duplicate `BF/4F` with matching id after START | abort pending; no valid bit |
| `BF/4F` wrong id while waiting for START | ignore; pending and expected START remain |
| `BF/50 0x10` after matching START | abort; no valid bit; runtime/reset caches unchanged |
| `BF/4F, BF/50, BF/52, BF/53` | abort on bad order; no mixed stale commit |
| late `BF/53` after timeout | ignored; next clean transaction commits |
| interleaved `BF/21..BF/2B` during identity pending | diagnostic caches update normally; identity phase unchanged |
| interleaved filename `BF/2F..BF/4E` during identity pending | filename parser behavior unchanged; identity phase unchanged |
| old-MAIN ACK/echo data byte after `cmd 0x25` | no parser drift; next diagnostic reply parses |
| partial `BF/4F` frame then frame-gap timeout then `BF/21` | partial identity frame cleared; runtime diag parses normally |

Mixed MAIN simulation matrix:

- `PB1=V3.2, PB2=V3.2`: both rows remain suffixless and counters update.
- `PB1=V3.3, PB2=V3.2`: PB1 shows suffix, PB2 suffixless.
- `PB1=V3.2, PB2=V3.3`: PB1 suffixless, PB2 shows suffix through PB1
  forwarding path.
- `PB1=V3.3 rev N, PB2=V3.3 rev M`: each PB shows its own live rev.

## Hardware Gate

Role-safe setup:

1. Run `scripts/hardware_state_test.py identify-mains --require-left-right` and
   record the HID paths for PB1/PB2.
2. Flash with explicit `--path` arguments; do not rely on enumeration order.
3. Record each target HEX SHA and intended rev before flashing.
4. After each MAIN flash, run `scripts/dlcp_main_flash.py --info-only --path ...`
   and confirm HID `3.3` plus live EEPROM `3.3 rev 0xRR`.
5. Flash CONTROL V1.72, then power-cycle the full chain so CONTROL starts a new
   identity epoch.

Different V3.3 revs without ad-hoc filenames:

- Build canonical `DLCP_Firmware_V3.3.hex` at rev N and flash PB1.
- Rebuild the same canonical path to rev N+1 and flash PB2.
- Record per-device live readback because the canonical file only represents
  the most recent build.

LCD gates:

- Two V3.3 MAINs with different revs: navigate to PB1/PB2 Diagnostics and
  verify row 0 shows each MAIN's live rev.
- Mixed V3.2/V3.3 in both directions:
  - PB1 V3.2 / PB2 V3.3 proves PB2 identity works through PB1 forwarding.
  - PB1 V3.3 / PB2 V3.2 proves identities are independent.
- Force or seed an issue state after a valid identity is cached and verify
  `PBn!` shows no version suffix.
- Force stale/lost or disconnect/reconnect after a valid identity is cached and
  verify the suffix disappears until a fresh identity transaction completes.
