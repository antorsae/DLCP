# V3.5 MAIN Volume to TAS3108 Coefficient Sweep Spec

Date: 2026-06-19
Status: test spec from 16 read-only agent reviews plus local source/sim trace

## Goal

Add behavioral and static tests proving that MAIN V3.5 serial volume commands
produce correct TAS3108 live-volume coefficients across the full valid
CONTROL/MAIN volume range: `data 0x00..0x72`, or `-96..+18 dB`. The required
behavioral gate is the full sweep, with exact TAS register `0x30` payloads,
strict monotonic attenuation/gain, and verified RAM ownership.

This spec targets `src/dlcp_fw/asm/dlcp_main_v35.asm`,
`src/dlcp_fw/asm/dlcp_main_ram.inc`, `src/dlcp_fw/sim/dlcp_sim_native.py`, and
`firmware/reference/tas3108.md`.

## Source Trace

`cmd 0x07` is the serial/current-loop volume command. CONTROL sends
`B0 07 <data>`, where `data == 0x60 + dB`; `0x60` is 0 dB. MAIN subtracts
`0x60`, sign-extends into `computed_volume[0..3]`, compares against
`logical_volume[0..3]`, and sets `event_flags.bit3` if changed. It must not
copy `computed_volume` to `logical_volume` here. See
`dlcp_main_v35.asm:2000-2045`.

The dirty drain is `cmd_dispatch_gated__apply_unmuted_volume_dirty`. It only
runs when active and not muted. It selects route trim from
`applied_route_shadow_b0`, adds it to `computed_volume`, converts the signed dB
integer to float, multiplies by `ln(10)/20`, runs
`float32_exp_limit1024_in_place`, stages `i2c_coeff_0..3`, then calls
`volume_dsp_write`. See `dlcp_main_v35.asm:1417-1482` and `3388-3417`.

`i2c_emit_tas3108_coeff_from_staged_float` scales by `2^23`, converts to int,
masks byte 0 with `0x0F`, and emits byte0, byte1, byte2, byte3. The writer is
`i2c_tas3108_coeff_write`: `START | 0x68 | 0x30 | coeff[4] | STOP`. See
`dlcp_main_v35.asm:5573-5628` and `7500-7537`.

`volume_dsp_write` is the ownership boundary. Only a successful TAS ACK clears
`event_flags.bit3/bit5` and copies `computed_volume` to `logical_volume`. NACK
retries must not commit logical volume. See `dlcp_main_v35.asm:9452-9503`.

The TAS3108 spec says I2C writes include the subaddress as the first data byte
(`tas3108.md:579`). Its 28-bit data layout requires byte 0 high nibble clear
(`tas3108.md:1059-1068`). For this firmware path, TAS `0x30..0x33` are the live
master-volume coefficient bytes; `0x31..0x33` are continuation bytes of the
`0x30` transaction, not separate volume starts.

## Expected Coefficients

These are firmware-observed V3.5 outputs from a MAIN-only sim with no route
trim, active gate open, and mute clear. V3.3 and V3.5 produced identical rows
for the full `-96..+18 dB` range. The table below is the golden firmware vector
set, not ideal-math recomputation.

| dB | data | TAS 0x30 payload |
|---:|:----:|:-----------------|
| 18 | 0x72 | 03f6a86c |
| 17 | 0x71 | 03887774 |
| 16 | 0x70 | 03264460 |
| 15 | 0x6F | 02cec32c |
| 14 | 0x6E | 0280b700 |
| 13 | 0x6D | 023b26ec |
| 12 | 0x6C | 01fd1c90 |
| 11 | 0x6B | 01c5d436 |
| 10 | 0x6A | 01947e8c |
| 9 | 0x69 | 01688f3a |
| 8 | 0x68 | 01416318 |
| 7 | 0x67 | 011e7672 |
| 6 | 0x66 | 00ff568e |
| 5 | 0x65 | 00e398d5 |
| 4 | 0x64 | 00cadc47 |
| 3 | 0x63 | 00b4c901 |
| 2 | 0x62 | 00a12162 |
| 1 | 0x61 | 008f9ced |
| 0 | 0x60 | 00800000 |
| -1 | 0x5F | 007214a2 |
| -2 | 0x5E | 0065ab2e |
| -3 | 0x5D | 005a9cac |
| -4 | 0x5C | 0050c109 |
| -5 | 0x5B | 0047f814 |
| -6 | 0x5A | 00402308 |
| -7 | 0x59 | 00392824 |
| -8 | 0x58 | 0032f01a |
| -9 | 0x57 | 002d6416 |
| -10 | 0x56 | 00287348 |
| -11 | 0x55 | 00240c39 |
| -12 | 0x54 | 00201f95 |
| -13 | 0x53 | 001c9fad |
| -14 | 0x52 | 001981d1 |
| -15 | 0x51 | 0016bac1 |
| -16 | 0x50 | 0014408f |
| -17 | 0x4F | 00120bdb |
| -18 | 0x4E | 0010149f |
| -19 | 0x4D | 000e542c |
| -20 | 0x4C | 000cc441 |
| -21 | 0x4B | 000b6020 |
| -22 | 0x4A | 000a22c2 |
| -23 | 0x49 | 000907c5 |
| -24 | 0x48 | 00080bc2 |
| -25 | 0x47 | 00072b42 |
| -26 | 0x46 | 00066305 |
| -27 | 0x45 | 0005b0c5 |
| -28 | 0x44 | 000511df |
| -29 | 0x43 | 00048451 |
| -30 | 0x42 | 00040625 |
| -31 | 0x41 | 000395c4 |
| -32 | 0x40 | 000331a3 |
| -33 | 0x3F | 0002d860 |
| -34 | 0x3E | 000288e6 |
| -35 | 0x3D | 00024216 |
| -36 | 0x3C | 000202fe |
| -37 | 0x3B | 0001cabf |
| -38 | 0x3A | 000198aa |
| -39 | 0x39 | 00016c0e |
| -40 | 0x38 | 00014446 |
| -41 | 0x37 | 000120de |
| -42 | 0x36 | 00010150 |
| -43 | 0x35 | 0000e536 |
| -44 | 0x34 | 0000cc29 |
| -45 | 0x33 | 0000b5da |
| -46 | 0x32 | 0000a1fd |
| -47 | 0x31 | 00009046 |
| -48 | 0x30 | 00008082 |
| -49 | 0x2F | 00007277 |
| -50 | 0x2E | 000065f3 |
| -51 | 0x2D | 00005acd |
| -52 | 0x2C | 000050df |
| -53 | 0x2B | 00004808 |
| -54 | 0x2A | 00004026 |
| -55 | 0x29 | 00003922 |
| -56 | 0x28 | 000032e3 |
| -57 | 0x27 | 00002d52 |
| -58 | 0x26 | 0000285c |
| -59 | 0x25 | 000023f1 |
| -60 | 0x24 | 00002002 |
| -61 | 0x23 | 00001c81 |
| -62 | 0x22 | 00001962 |
| -63 | 0x21 | 0000169b |
| -64 | 0x20 | 00001421 |
| -65 | 0x1F | 000011ed |
| -66 | 0x1E | 00000ff7 |
| -67 | 0x1D | 00000e37 |
| -68 | 0x1C | 00000ca8 |
| -69 | 0x1B | 00000b46 |
| -70 | 0x1A | 00000a09 |
| -71 | 0x19 | 000008f0 |
| -72 | 0x18 | 000007f5 |
| -73 | 0x17 | 00000716 |
| -74 | 0x16 | 0000064f |
| -75 | 0x15 | 0000059e |
| -76 | 0x14 | 00000500 |
| -77 | 0x13 | 00000474 |
| -78 | 0x12 | 000003f7 |
| -79 | 0x11 | 00000388 |
| -80 | 0x10 | 00000325 |
| -81 | 0x0F | 000002cc |
| -82 | 0x0E | 0000027e |
| -83 | 0x0D | 00000238 |
| -84 | 0x0C | 000001f9 |
| -85 | 0x0B | 000001c2 |
| -86 | 0x0A | 00000191 |
| -87 | 0x09 | 00000165 |
| -88 | 0x08 | 0000013e |
| -89 | 0x07 | 0000011b |
| -90 | 0x06 | 000000fc |
| -91 | 0x05 | 000000e0 |
| -92 | 0x04 | 000000c7 |
| -93 | 0x03 | 000000b1 |
| -94 | 0x02 | 0000009e |
| -95 | 0x01 | 0000008d |
| -96 | 0x00 | 0000007d |

All non-mute volume payloads in the full valid range must satisfy:

- exactly 4 bytes
- `payload[0] & 0xF0 == 0`
- integer value is `0 < value <= 0x03F6A86C`
- values strictly increase as dB goes from -96 to +18
- TAS register snapshot `0x30..0x33` equals the final payload bytes

## Primary Test Module

Create `tests/sim/test_v35_volume_tas30_semantics.py`.

Use `RustChain.from_v3x_main_only(str(V35_MAIN_HEX))` as the primary fixture.
Inject serial frames with `inject_main_frames_fifo([[0xB0, 0x07, data]],
fifo_limit=47)`. Use `reset_main_dsp_write_log(0)` immediately before each
stimulus and observe `read_main_dsp_write_payloads(0, 0x30)`.

Before the sweep, force deterministic state:

- active gate open: `active_flags` at `0x05E`, bit3 set
- user mute clear: clear `active_flags.bit4`, `active_flags.bit5`, and
  `main_runtime_latch_flags` at `0x094`, bit5
- no-trim route: set `applied_route_shadow_b0` at `0x0AB` to `1` or another
  receiver route
- clear route trim scratch `0x09A` and poison-prone trim bytes unless a trim
  test needs them
- settle boot/preset traffic before resetting the TAS write log

### Required Behavioral Tests

1. `test_v35_serial_volume_full_range_writes_exact_tas30_coefficients`

   Sweep every valid data byte `0x00..0x72` (recommended order: `0x72` down to
   `0x00` to exercise monotonically decreasing commands from +18 dB to -96 dB,
   or reset/settle between values if using ascending order). For each step,
   assert one new completed TAS start at `0x30`, payload equals the table above,
   no starts at `0x31..0x36`, regs `0x30..0x33` equal the payload,
   `computed_volume` and `logical_volume` both equal the signed dB value after
   ACK, `event_flags.bit3/bit5` clear, and `dsp_fault_flags & 0x44 == 0`.

2. `test_v35_volume_sweep_matches_v33_payloads`

   Run the full exact sweep on `V33_MAIN_HEX` and `V35_MAIN_HEX`. Assert the
   effective TAS `0x30` payload value for every data byte is byte-identical for
   the full valid range. This uses V3.3 as the pre-size-reclaim
   source-assembled baseline and guards the V3.4/V3.5 size-reclaim lineage from
   altering audio math accidentally. Do not require V3.3 to match V3.5's newer
   transaction-count and `0x31..0x36` volume-family-start behavior.

3. `test_v35_volume_route_trim_poison_does_not_contaminate_no_trim_route`

   Poison `pending_route_request_b0`, route trim bytes, and
   `route_volume_trim_offset_b0`; keep `applied_route_shadow_b0` on a no-trim
   receiver route. Assert the exact baseline payloads still appear. This should
   fail if the selector regresses from `applied_route_shadow_b0` to
   `pending_route_request_b0` or reuses stale trim.

4. `test_v35_muted_volume_sweep_updates_latent_volume_but_keeps_tas30_zero`

   With user mute set, send changed `B0/07` frames. Assert `computed_volume`
   tracks the requested dB and mute remains owned by `cmd 0x03`; TAS `0x30`
   receives only zero writes or remains zero. Bare volume must not unmute.

5. `test_v35_standby_volume_sweep_defers_tas_until_wake`

   With active gate closed, send volume frames. Assert cache/dirty state changes
   but no TAS `0x30` write occurs. After wake and unmuted settle, assert the
   final requested volume writes once and commits logical volume.

6. `test_v35_preset_a_and_b_have_identical_live_volume_sweep`

   Apply preset A, settle, sweep selected anchors or the full table. Apply
   preset B, settle, repeat. Assert the same TAS `0x30` payload sequence for
   both presets while separately confirming the biquad image `0x37..0x90`
   differs or matches its active-preset golden image.

7. `test_v35_volume_nack_does_not_commit_logical_until_ack`

   Use `inject_main_tas3108_address_nack` and `inject_main_tas3108_data_nack`.
   Assert NACK stats increment, `event_flags.bit3` remains set during retry,
   `logical_volume != computed_volume` before ACK, and only a successful
   payload clears dirty and copies computed to logical. Persistent NACK should
   set DSP fault without committing logical volume.

8. `test_v173_v35_control_chain_volume_drives_both_mains`

   Use `from_v171_v32(control_hex_path=V173_CONTROL_HEX,
   main_hex_path=V35_MAIN_HEX)`, drive real CONTROL volume input, and assert
   both MAINs converge to the same TAS `0x30` payload for the same state. This
   is secondary to the MAIN-only gate because full-chain traffic is noisier.

## HID Settings Import Risk

Two agents flagged a separate high-risk HID settings path. Opcode `0x05` copies
four bytes from the HID report into `computed_volume_3_b0_op`, but `chain_copy`
increments forward, so the destination can spill across `0x071..0x074` instead
of updating `computed_volume[0..3]` at `0x06E..0x071`. The same HID path calls
`copy_computed_volume_to_logical_volume` before verified TAS ACK.

Add a separate expected-fail or bug-repro test until fixed:

- send HID settings volume `FF FF FF E2`
- assert `computed_volume[0..3] == E2 FF FF FF`
- assert `event_flags.bit3` is set when volume changes
- with TAS NACK injected, assert `logical_volume` does not advance before ACK

This is not equivalent to serial `cmd 0x07`; do not use HID as the primary
volume-command sweep.

## Static Contracts

Create `tests/sim/test_v35_volume_tas3108_contracts.py` for source/listing
guards. Assert:

- `volume_cmd_handler` stages `data - 0x60`, sign-extends to
  `computed_volume`, sets only `event_flags.bit3`, and does not call
  `copy_computed_volume_to_logical_volume` or any TAS writer
- muted and unmuted dirty dispatch split at `active_flags.bit4`
- unmuted math uses `applied_route_shadow_b0`, clears trim scratch, stages
  `47 C9 EB 3D`, calls `float32_exp_limit1024_in_place`, and calls
  `volume_dsp_write`
- `float32_exp_limit1024_in_place` keeps the 10-pass square loop shape
- `i2c_emit_tas3108_coeff_from_staged_float` keeps byte order and high-nibble
  mask
- `i2c_tas3108_coeff_write` writes only TAS address `0x68`, subaddress `0x30`,
  staged coeff bytes, and the timeout recovery labels
- zero-volume helper clears `i2c_coeff_0..3` and routes through
  `volume_dsp_write`, not a direct write
- RAM aliases are pinned: `i2c_coeff_0..3 = 0x055..0x058`,
  `logical_volume = 0x066..0x069`, `computed_volume = 0x06E..0x071`,
  `event_flags = 0x07E`, `dsp_fault_flags = 0x07F`,
  `pending_route_request = 0x093`, `route_volume_trim_offset = 0x09A`,
  `applied_route_shadow = 0x0AB`
- listing labels exist and address order follows the pipeline:
  `volume_cmd_handler`, `cmd_dispatch_gated__apply_unmuted_volume_dirty`,
  `float32_exp_limit1024_in_place`,
  `i2c_emit_tas3108_coeff_from_staged_float`, `i2c_tas3108_coeff_write`,
  `volume_dsp_write`

## Hardware Smoke

The simulator observes byte storage and completed I2C writes, not analog audio.
Because this code path has a documented prior case where simulation passed but
hardware dropped coefficient writes, add one low-volume hardware smoke after
sim and mutation tests pass:

- flashed V1.73 CONTROL + V3.5 MAIN on both MAINs
- unmuted active source, no preset transition in progress
- step 0, -6, -12, -18, -24, -30 dB
- confirm no mute, no DSP fault, and audible output decreases monotonically
- repeat once after preset A->B->A and once after standby/wake

## Non-Goals

- Do not validate out-of-protocol runtime volume bytes above `0x72` in the
  primary sweep. Add a separate clamp/policy test if the project wants MAIN to
  reject impossible host/HID values.
- Do not treat TAS `0x31..0x33` register bytes as separate volume starts. They
  are payload continuation bytes from the `0x30` transaction.
- Do not update the golden table for a future math rewrite silently. If volume
  math is intentionally reimplemented, regenerate and review these vectors as a
  deliberate spec change.
