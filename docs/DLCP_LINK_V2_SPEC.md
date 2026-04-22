# DLCP Link v2 — Lean Robust Current-Loop Protocol Specification

Date: 2026-04-22
Status: draft / preferred canonical protocol / not implemented in committed repo builds
Scope: replacement for the legacy 3-byte `route/cmd/data` current-loop protocol between CONTROL and chained MAIN units

## Purpose

This document defines the canonical replacement for the legacy DLCP
current-loop UART protocol.

It is written for the current source-controlled firmware line where we
have full freedom to change both sides:

- CONTROL: `src/dlcp_fw/asm/dlcp_control_v171.asm`
- MAIN: `src/dlcp_fw/asm/dlcp_main_v32.asm`

The goal is not a minimal compatibility patch. The goal is a transport
and session protocol that remains correct under:

- byte loss
- duplicated frames
- stale reconnect traffic
- parser desynchronization
- chain-forwarding ambiguity
- temporary service starvation

## Why The Legacy Protocol Must Be Replaced

The current wire protocol is fundamentally:

- fixed 3-byte frames
- no start-of-frame marker
- no checksum or CRC
- no sequence number
- no session or epoch marker
- no source identity in replies
- no explicit ACK / NACK
- no explicit reconnect transaction

Operationally, reconnect correctness is inferred from side effects in
shared UI/status caches rather than from an explicit wire-level
handshake.

That design is fragile against both current and future failures:

1. A single dropped byte can corrupt frame alignment.
2. A stale reply can satisfy a reconnect predicate incorrectly.
3. PB1 and PB2 replies can collapse into one shared truth.
4. Broadcasts that provoke multiple replies can collide.
5. Partial TX publication can put broken commands on the wire.
6. Parser state can survive a torn frame and poison later traffic.
7. CONTROL UI state is too tightly coupled to transport internals.

The 2026-04-22 real-hardware repro confirms that the legacy model is no
longer trustworthy as a reconnect proof: both MAINs were already awake
and healthy while CONTROL still showed `WAITING FOR DLCP`
(`docs/analysis/V171_V32_STDBY_WAKE_WAITING_REAL_HW_2026-04-22.md`).

## Design Goals

DLCP Link v2 must provide all of the following:

1. Explicit packet framing and integrity protection.
2. Deterministic resynchronization after torn or corrupt traffic.
3. Explicit per-node identity on every accepted reply.
4. Explicit session freshness across reconnect and wake cycles.
5. Idempotent command handling under retries and duplicate delivery.
6. No broadcast-driven reply collisions.
7. Packet-atomic TX publication.
8. Bounded parser state and bounded error recovery.
9. A clean separation between:
   - link liveness
   - command acceptance
   - command completion
   - state freshness
   - UI/rendering state
10. A model that still works if CONTROL suffers a temporary service gap.

## Non-Goals

This spec does not aim to preserve on-wire compatibility with:

- stock CONTROL `V1.4` / `V1.5b` / `V1.6b`
- patched CONTROL `V1.41` .. `V1.64b`
- stock/patched/source MAIN `V2.x` / `V3.x`

The canonical `Link v2` release is a paired CONTROL+MAIN deployment.
Mixed old/new protocol operation is out of scope for the shipping
revision described here.

## Physical / Firmware Constraints

The protocol must fit the existing hardware model:

- physical medium: 31,250 baud current-loop UART
- chain topology: `CONTROL <> PB1 <> PB2 ...`
- no shared collision-detect hardware
- MAIN-to-MAIN forwarding remains software-mediated
- target MCUs are PIC18-class devices with small RAM and no dynamic
  allocation

These constraints drive two architectural choices:

1. `Link v2` is master-driven. CONTROL is the only session master.
2. MAIN-originated upstream traffic is request/response only. MAINs do
   not emit unsolicited packets in the canonical design.

## Core Model

`Link v2` has three layers:

1. Transport layer:
   - framed packets
   - CRC
   - byte-gap timeout
   - store-and-forward chain routing
2. Session layer:
   - `session`
   - `boot_nonce`
   - duplicate suppression
   - request/response matching
3. Command/state layer:
   - discovery
   - health polling
   - full-state snapshots
   - parameter writes
   - multi-node two-phase commit for disruptive operations

## Why This Header Shape

This spec intentionally uses a lean on-wire envelope.

Packet format overhead is:

- `1` leading delimiter
- `4` fixed header bytes
- `2` CRC bytes

Fixed overhead before payload: `7` bytes.

At `31,250` baud `8N1`, every extra wire byte costs about `0.32 ms`.
This link is a control plane, not a bulk pipe, but it is still slow
enough that unnecessary bytes directly add:

- queue pressure
- forwarding latency
- exposure to service-starvation windows

The header is therefore compressed as far as I think is prudent without
dropping any of the important correctness properties.

## Transport Format

### Frame Encoding

Use a single leading delimiter with escaping:

- `0x7E` = start-of-frame
- `0x7D` = escape byte
- escaped byte on wire = `0x7D`, then `(byte ^ 0x20)`

Bytes escaped inside the frame body:

- `0x7E`
- `0x7D`

There is no trailing delimiter.

Receiver rule:

- if `0x7E` is seen while assembling a packet, abandon the partial
  packet and treat the new `0x7E` as the start of a fresh frame

This keeps resynchronization explicit while saving one byte per packet.

### Packet Body

Unescaped packet body:

```text
type_len | hop | seq | session | payload[len] | crc16_lo | crc16_hi
```

Field definitions:

- `type_len`:
  - upper nibble = message type `1..15`
  - lower nibble = payload length `0..15`
- `hop`:
  - on downstream CONTROL-originated packets:
    - `0x01..0xFE` = hop count to destination
    - `0xFF` = broadcast
  - on upstream MAIN-originated replies:
    - `0x01` at origin
    - each forwarder increments by `1`
    - CONTROL receives the final chain index here
- `seq`:
  - request sequence number
- `session`:
  - CONTROL-owned session freshness marker
- `crc16`:
  - CRC-16/CCITT-FALSE over `type_len .. payload`
  - polynomial `0x1021`, init `0xFFFF`, xorout `0x0000`

### `MAX_PAYLOAD = 15`

`Link v2` sets `MAX_PAYLOAD = 15`.

Reason:

- the lower nibble of `type_len` naturally encodes `0..15`
- all required responses fit in `<= 12` bytes today
- `15` leaves headroom without needing another length byte

This is a deliberate ceiling, not a generic bulk-transfer protocol.
Large diagnostics or dump-style traffic should use explicit paged reads
or USB/HID, not the control link.

### Parser State Machine

Receiver state machine:

1. `WAIT_SOF`
2. `READ_TYPELEN`
3. `READ_FIXED_HEADER`
4. `READ_PAYLOAD`
5. `READ_CRC`
6. `ESCAPED`

Mandatory drop conditions:

- byte-gap timeout
- malformed escape
- RX overflow
- CRC mismatch
- invalid type nibble (`0`)
- impossible payload length (`> 15`)

Any drop returns immediately to `WAIT_SOF`.

The parser must not preserve partially interpreted command state across
packet drops.

Byte-gap timeout:

- `T_BYTE_GAP_MAX = 20 ms`

## Addressing And Forwarding

### Downstream

For packets moving from CONTROL toward the chain tail:

- `hop = 0xFF`:
  - local consume allowed
  - forward unchanged downstream
- `hop = 0x01`:
  - consume locally
  - do not forward
- `hop > 0x01`:
  - decrement `hop`
  - forward downstream
  - do not consume locally

### Upstream

For replies moving toward CONTROL:

- responder emits with `hop = 0x01`
- each upstream forwarder increments `hop`
- each upstream forwarder recomputes `crc16`

At CONTROL:

- `hop = 0x01` means PB1
- `hop = 0x02` means PB2

So `Link v2` has explicit per-packet reply identity even though the
wire header is small.

### Reply Collision Rule

Only addressed requests may generate replies.

Broadcast commands must not generate immediate replies.

If CONTROL needs confirmation after a broadcast:

- send the broadcast command
- then poll nodes individually

This is mandatory. It avoids multi-node reply collisions by
construction.

## Session Model

### CONTROL-Owned `session`

CONTROL owns an 8-bit `session` counter.

CONTROL must increment `session` whenever it performs a global link
reconnect, including:

- cold boot
- post-standby wake reconnect
- explicit operator resync
- detection of topology loss requiring rediscovery

Each MAIN stores the most recent accepted `session`.

Packets from an older session are ignored.

### MAIN-Owned `boot_nonce`

Each MAIN exposes an 8-bit `boot_nonce` in `HELLO_RSP`, `HEALTH_RSP`,
and `STATE_RSP`.

`boot_nonce` must change on every MAIN reset or cold boot.

Purpose:

- detect a node reset within the same CONTROL session
- invalidate stale cached state for that node

### Duplicate Handling

Each MAIN must retain enough metadata to recognize the last accepted
request in the current session:

- `last_seq`
- `last_type`
- `last_reply`

If a duplicate request arrives:

- do not reapply the operation blindly
- resend the cached reply if available

For disruptive operations, `txn_id` adds a second idempotence key.

## Control Policy State

CONTROL must maintain distinct state for each discovered node:

- `node_present`
- `node_hop`
- `boot_nonce`
- `session_seen`
- `hello_valid`
- `health_valid`
- `state_valid`
- `last_health_age`
- `actual_power_state`
- `desired_power_state`
- `fault_summary`
- `pending_txn`
- `applied_txn`

`WAITING FOR DLCP` must no longer depend on payload sentinels or shared
status caches.

Instead, UI readiness depends on explicit per-node criteria:

- every required node has valid `HELLO_RSP`
- every required node has fresh `HEALTH_RSP`
- every required node has a known `actual_power_state`

Installation policy:

- CONTROL stores `required_node_count`
- nodes beyond that count are optional unless explicitly configured

## Message Type Catalog

`Link v2` uses a 4-bit type space.

| Type nibble | Message |
|---|---|
| `0x1` | `HELLO_REQ` |
| `0x2` | `HELLO_RSP` |
| `0x3` | `HEALTH_REQ` |
| `0x4` | `HEALTH_RSP` |
| `0x5` | `STATE_REQ` |
| `0x6` | `STATE_RSP` |
| `0x7` | `SET_PARAM_REQ` |
| `0x8` | `STATUS_RSP` |
| `0x9` | `PREPARE_REQ` |
| `0xA` | `COMMIT_CMD` |
| `0xB` | `ABORT_CMD` |
| `0xC` | `RESULT_REQ` |
| `0xD` | `RESULT_RSP` |
| `0xE` | `COUNTERS_REQ` |
| `0xF` | `COUNTERS_RSP` |

`STATUS_RSP` replaces separate `ACK` and `NACK`.

This keeps the type space within one nibble without losing success vs
rejection semantics.

## Payloads

### `HELLO_REQ`

Payload: empty

### `HELLO_RSP`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `fw_major` |
| 1 | `fw_minor` |
| 2 | `fw_rev` |
| 3 | `boot_nonce` |
| 4 | `caps_lo` |
| 5 | `caps_hi` |
| 6 | `status_flags` |
| 7 | `profile_id` |

`profile_id` is fixed to `0x20` for `DLCP Link v2`.

`HELLO_RSP` is where the peer proves it is speaking this profile.

### `HEALTH_REQ`

Payload: empty

### `HEALTH_RSP`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `boot_nonce` |
| 1 | `actual_power_state` |
| 2 | `status_flags` |
| 3 | `fault_summary` |
| 4 | `pending_txn` |
| 5 | `applied_txn` |

`status_flags` bits:

- bit 0: muted
- bit 1: degraded
- bit 2: state_dirty
- bit 3: counters_dirty
- bit 4: upstream_seen_recently

### `STATE_REQ`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `fields_mask_lo` |
| 1 | `fields_mask_hi` |

For `v2.0`, CONTROL should request the default full state mask.

### `STATE_RSP`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `boot_nonce` |
| 1 | `actual_power_state` |
| 2 | `desired_power_state` |
| 3 | `mute_state` |
| 4 | `input_id` |
| 5 | `preset_id` |
| 6 | `volume_q2_lo` |
| 7 | `volume_q2_hi` |
| 8 | `fault_flags_lo` |
| 9 | `fault_flags_hi` |
| 10 | `pending_txn` |
| 11 | `applied_txn` |

`volume_q2` is signed quarter-dB.

### `SET_PARAM_REQ`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `param_id` |
| 1 | `value_lo` |
| 2 | `value_hi` |
| 3 | `apply_flags` |

Initial `param_id` set:

- `0x01` = `volume_q2`
- `0x02` = `mute`
- `0x03` = `input_id`
- `0x04` = `route_mode`

`SET_PARAM_REQ` is for immediate addressed changes where strict
cross-node simultaneity is not required.

### `STATUS_RSP`

Used as the reply to:

- `SET_PARAM_REQ`
- `PREPARE_REQ`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `for_type` |
| 1 | `status_code` |
| 2 | `arg0` |
| 3 | `arg1` |

`status_code` values:

- `0x00` = applied
- `0x01` = accepted and pending
- `0x02` = prepared / ready
- `0x80` = malformed payload
- `0x81` = unsupported message
- `0x82` = unsupported parameter or op
- `0x83` = invalid state
- `0x84` = busy
- `0x85` = stale session

Codes `< 0x80` are success-like.
Codes `>= 0x80` are rejection-like.

### `PREPARE_REQ`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `txn_id` |
| 1 | `op_id` |
| 2 | `arg_lo` |
| 3 | `arg_hi` |
| 4 | `op_flags` |

Initial `op_id` set:

- `0x01` = `WAKE`
- `0x02` = `STANDBY`
- `0x03` = `PRESET_APPLY`
- `0x04` = `INPUT_SWITCH`
- `0x05` = `ROUTE_CHANGE`

`PREPARE_REQ` must only stage state. It must not perform the operation.

### `COMMIT_CMD`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `txn_id` |
| 1 | `op_id` |

`COMMIT_CMD` may be sent as:

- addressed commit, or
- broadcast commit after all required nodes reported `ready`

Broadcast `COMMIT_CMD` must not generate replies.

### `ABORT_CMD`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `txn_id` |
| 1 | `op_id` |

### `RESULT_REQ`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `txn_id` |
| 1 | `op_id` |

### `RESULT_RSP`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `txn_id` |
| 1 | `op_id` |
| 2 | `result_state` |
| 3 | `reason_code` |
| 4 | `actual_power_state` |
| 5 | `status_flags` |

`result_state` values:

- `0x00` = none
- `0x01` = prepared
- `0x02` = applied
- `0x03` = failed
- `0x04` = aborted

### `COUNTERS_REQ`

Payload: empty

### `COUNTERS_RSP`

Payload:

| Byte | Meaning |
|---|---|
| 0 | `diag_i2c` |
| 1 | `diag_dsp` |
| 2 | `diag_standby` |
| 3 | `diag_boot` |
| 4 | `diag_recovery` |
| 5 | `diag_an0` |
| 6 | `diag_ra1_or_reserved` |
| 7 | `diag_proto_errors` |

## Request / Response Policy

CONTROL uses stop-and-wait:

- one addressed request outstanding at a time
- wait for reply or timeout
- then send the next request

Default policy:

- `T_RSP_DEFAULT = 30 ms`
- `N_RETRY_DEFAULT = 3`

If CONTROL does not receive a valid reply after `3` attempts:

- mark the node stale
- do not update UI from old caches
- enter rediscovery/reconnect policy as needed

Retries must reuse the same `seq` for the same logical request.

## Discovery And Reconnect

CONTROL discovers nodes by addressed probing, not by broadcast:

1. increment `session`
2. clear per-node freshness state
3. for `hop = 1 .. required_node_count`:
   - send `HELLO_REQ(hop)`
   - require `HELLO_RSP`
   - record returned `hop`, `boot_nonce`, capabilities, version
4. for each discovered node:
   - send `STATE_REQ`
   - record explicit state

Optional topology extension:

- CONTROL may continue probing above `required_node_count`
- extra discovered nodes are tracked but do not block base readiness

### Reconnect Completion Rule

CONTROL exits `WAITING FOR DLCP` only when every required node has:

- valid `HELLO_RSP` in the current `session`
- fresh `STATE_RSP` or `HEALTH_RSP`
- known `actual_power_state`

No reconnect rule may depend on stale payload bytes or sentinel values.

## Steady-State Polling

In active operation, CONTROL polls each required node round-robin:

- `HEALTH_REQ` period target: `200 ms` per node

In standby or quiescent states:

- `HEALTH_REQ` period target: `1000 ms` per node

If `HEALTH_RSP.status_flags.state_dirty = 1`:

- CONTROL issues `STATE_REQ` to refresh the full snapshot

If `HEALTH_RSP.status_flags.counters_dirty = 1`:

- CONTROL may issue `COUNTERS_REQ`

This keeps normal link traffic low while still making liveness and
pending state explicit.

## Operation Model

### Immediate Per-Node Parameters

For operations that do not require exact cross-node simultaneity,
CONTROL uses `SET_PARAM_REQ` addressed per node.

Examples:

- volume step
- mute toggle
- non-critical route or input updates on a single node

Result semantics:

- `STATUS_RSP(applied)` means the node accepted and applied the
  parameter
- `STATUS_RSP(accepted and pending)` means the node accepted but needs
  time before the change is fully reflected
- rejection-like `STATUS_RSP` means no state change happened

### Multi-Node Disruptive Operations

For disruptive or synchrony-sensitive operations, CONTROL uses a
two-phase transaction:

1. `PREPARE_REQ(hop=node_i, txn_id, op_id, arg, flags)`
2. receive `STATUS_RSP(ready)` from every required node
3. send `COMMIT_CMD(txn_id, op_id)` as broadcast
4. poll `RESULT_REQ` per node until all required nodes report terminal
   state

Examples:

- wake
- standby
- preset apply
- synchronized input switch

This model separates:

- node parsed and staged the request
- node actually completed the operation

That distinction is mandatory. The legacy protocol blurred it.

### Idempotence Rules

Each node must track:

- current prepared transaction
- last applied transaction

Rules:

- duplicate `PREPARE_REQ` with same `(session, txn_id, op_id)`:
  - reply `STATUS_RSP(ready)`
  - do not restage a second copy
- duplicate `COMMIT_CMD` for the prepared transaction:
  - harmless
  - do not double-apply
- `RESULT_REQ` for the last applied transaction:
  - must return the remembered terminal state

## Power-State State Machine

Per node:

- `STANDBY`
- `WAKING`
- `ACTIVE`
- `DEGRADED`
- `FAULT`

CONTROL tracks both:

- `desired_power_state`
- `actual_power_state`

`desired_power_state` changes when CONTROL initiates an operation.
`actual_power_state` changes only when confirmed by `STATE_RSP` or
`RESULT_RSP`.

This prevents UI from equating command sent with node reached state.

## Example Flows

### Cold Boot

1. CONTROL boots, increments `session`.
2. CONTROL probes `hop=1..required_node_count` with `HELLO_REQ`.
3. Each node replies with `HELLO_RSP`.
4. CONTROL polls `STATE_REQ` for each discovered node.
5. UI becomes ready only after explicit per-node state exists.

### Wake

1. CONTROL increments `txn_id`.
2. CONTROL sends addressed `PREPARE_REQ(WAKE)` to each required node.
3. Each node replies `STATUS_RSP(ready)`.
4. CONTROL sends broadcast `COMMIT_CMD(WAKE)`.
5. CONTROL polls `RESULT_REQ(WAKE)` until each required node reports
   `applied`.
6. CONTROL polls `STATE_REQ` to refresh full state if needed.

No stale pre-wake status may satisfy this flow because `session`,
`txn_id`, and `boot_nonce` make freshness explicit.

### Standby

Same as wake, with `op_id = STANDBY`.

### Preset Apply

1. CONTROL stages `PREPARE_REQ(PRESET_APPLY, preset_id)`.
2. Nodes validate resources and reply `STATUS_RSP(ready)` or rejection.
3. CONTROL broadcasts `COMMIT_CMD`.
4. CONTROL polls `RESULT_REQ`.
5. UI updates only after all required nodes report terminal state.

## Failure Coverage Matrix

| Failure | `Link v2` mitigation |
|---|---|
| Partial TX publication | packet-atomic TX commit |
| Lost or duplicated addressed request | `seq` + retry + cached reply |
| Stale reconnect traffic | `session` |
| Node reset during session | `boot_nonce` |
| Parser desync after torn frame | delimiter + escape + CRC + byte-gap timeout |
| PB1/PB2 ambiguity | explicit upstream `hop` identity |
| Broadcast reply collision | broadcast packets never solicit replies |
| MAIN service stall during operation | `RESULT_REQ` timeout and per-node stale detection |
| RX overflow / OERR / FERR | parser reset + hardware recovery without preserving partial packet state |
| False UI readiness from payload caches | explicit `HELLO/HEALTH/STATE` validity model |

## Firmware Architecture Requirements

`Link v2` requires these implementation rules on both sides.

### 1. Packet-Atomic TX

TX publication must be packet-atomic.

Allowed implementation shapes:

- dedicated packet buffer with ready flag
- raw-byte ring with reserve/commit pointers

Required behavior:

- either the whole encoded packet becomes visible to TX service
- or none of it does

Publishing byte-by-byte before the packet is complete is forbidden.

### 2. Store-And-Forward Routing

Forwarders must:

- receive a whole valid packet
- mutate `hop` as required
- recompute CRC
- retransmit the new packet

Cut-through byte forwarding is not compatible with `Link v2`.

### 3. ISR Scope

ISR must do only low-level capture/service:

- RX byte enqueue
- TX byte dequeue kick
- lightweight timer bookkeeping

ISR must not do:

- long IR decode
- packet parser logic
- session/state-machine logic

This rule is specifically intended to remove the current class of
failures where IR decode stalls UART service in the worst possible
window.

### 4. RX Error Recovery

On OERR/FERR/RX overflow:

- drain hardware RX as required
- reset parser state
- preserve unrelated TX state

RX recovery must not clear queued outgoing packets.

## Migration Plan

Canonical deployment plan:

1. freeze this wire spec
2. implement `Link v2` in simulator helpers first
3. implement MAIN parser/forwarder + request handlers
4. implement CONTROL link manager + per-node state model
5. gate with wire/gpsim fault injection
6. flash CONTROL and MAIN together as a pair

The canonical release should not carry the legacy 3-byte parser unless a
temporary bring-up build explicitly needs it.

Recommended implementation order:

1. Transport:
   - framing
   - CRC
   - packet parser
   - packet-atomic TX
2. Discovery:
   - `HELLO_REQ/RSP`
   - `HEALTH_REQ/RSP`
   - `STATE_REQ/RSP`
3. Immediate parameters:
   - `SET_PARAM_REQ`
4. Transactions:
   - `PREPARE_REQ`
   - `COMMIT_CMD`
   - `RESULT_REQ/RSP`
5. Diagnostics:
   - `COUNTERS_REQ/RSP`

## Validation Plan

Minimum protocol gates:

1. Corrupt-byte injection:
   - CRC failure must drop one packet and recover on the next delimiter.
2. Byte-drop injection:
   - partial packet must not poison later packets.
3. Duplicate request injection:
   - duplicate `PREPARE_REQ` / `SET_PARAM_REQ` must be idempotent.
4. Stale-session injection:
   - old `session` packets must be ignored.
5. Mid-transaction node reset:
   - `boot_nonce` change must force rediscovery.
6. Broadcast commit soak:
   - no collisions because commit gets no reply.
7. PB2 forwarding fault:
   - PB1 cannot mislabel PB2 as itself.
8. CONTROL service stall injection:
   - link must recover without false-ready UI state.
9. Long soak:
   - repeated wake/standby/preset transactions without permanent wait.

Hardware release gate:

- repeated standby/wake cycles on a two-MAIN rig
- repeated preset apply while audio active
- forced cable / forwarding fault tests
- diagnostics counter readback after injected faults

## Bottom Line

`Link v2` is intentionally conservative in control semantics and lean on
the wire:

- stop-and-wait instead of pipelined transport
- addressed request/response instead of unsolicited events
- explicit sessions and transactions instead of inferred liveness
- compact header with CRC and explicit hop identity

That is the right tradeoff for this product.

The current DLCP failures are not just missing retries. They are the
result of a protocol that has no explicit concept of packet integrity,
identity, freshness, or completion. `DLCP Link v2` fixes those missing
concepts directly.
