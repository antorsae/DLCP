# V1.71 rev 0x04 + V3.2 rev 0x38: STDBY/WAKE `WAITING FOR DLCP` on real hardware

Date: 2026-04-22
Status: reproduced on the current canonical pair

## Scope

This note records the real-hardware standby/wake behavior of the
current canonical pair:

- CONTROL source release metadata: `V1.71 / rev 0x04`
  (`src/dlcp_fw/asm/dlcp_control_v171.asm`, `control_release_metadata`)
- MAIN source release metadata: `V3.2 / rev 0x38`
  (`src/dlcp_fw/asm/dlcp_main_v32.asm`, EEPROM tuple `0x03, 0x02, 0x38`)

Important MAIN-flasher caveat: live USB `--info-only` still reports the
legacy EEPROM marker byte (`0x30` on the rig) because the MAIN flash
path writes app flash only and does not rewrite EEPROM version bytes.
So for MAIN, the canonical source revision is `0x38`, but the live
USB revision byte is not a reliable deployment stamp.

## Real-hardware repro

Artifacts:

- full paired LCD+USB run:
  `artifacts/probes/live_seq_lcd_usb/20260422_193753/report.json`
- wake LCD capture:
  `artifacts/probes/live_seq_lcd_usb/20260422_193753/lcd/after_wake/runs/20260422_193941/capture_1.jpg`
- wake LCD OCR summary:
  `artifacts/probes/live_seq_lcd_usb/20260422_193753/lcd/after_wake/runs/20260422_193941/summary.json`

Observed sequence:

1. After power-cycle, both MAINs were visible on USB, healthy, and on
   preset `B`.
2. `MUTE` and unmute both worked normally from CONTROL/IR.
3. `STANDBY` made both MAINs disappear from USB, which matches the
   intended V3.2 USB shutdown path.
4. `WAKE` reproducibly landed the CONTROL LCD on `WAITING FOR DLCP`.
5. While the LCD still showed `WAITING FOR DLCP`, both MAINs had
   already re-enumerated and probed healthy:
   - both in app mode
   - both HID `version: 3.2`
   - LEFT routed all `L`, RIGHT routed all `R`
   - `chain_gate_open(bit3)=1`
   - `stdby_wake_pending(bit2)=0`
   - diag counters `S=1, B=1`, all fault counters `0`
   - stable healthy UART register snapshots (`TXSTA=0x03`,
     `RCSTA=0xE0`)

That hardware result is the key discriminator: for the current pair,
the post-wake field symptom is no longer "MAIN failed to wake".  The
MAINs are awake and sane while CONTROL remains on the `WAITING` screen.

## What Changed Versus The Earlier MAIN-side Theory

The earlier V3.2 hardening plan assumed the remaining wake wedge was
still MAIN-side: MAIN would wake, but fail to re-emit the
sentinel-clearing `BF/05/07/03/06/1D` burst.  That was true for the
older wake path, but it is no longer the best explanation for the
current canonical source.

Current `V3.2` `adc_boot_gate` now does all of the following:

- quiesces the UART before the long wake-time blind window
- re-arms TX before wake-time housekeeping traffic
- explicitly calls `send_status_burst` during wake
- then re-runs full UART bring-up before RX resumes

So the current real-hardware failure cannot be explained as "MAIN never
finished wake" or "MAIN never sent any wake-time status at all".

## Root Cause In Current Code

The remaining root cause is CONTROL-side reconnect fragility, not MAIN
standby exit.

Two explicit CONTROL defects line up with the hardware behavior:

### 1. IR decode still blocks UART service at exactly the wrong time

`ir_rc5_decode` still runs inside the CONTROL ISR and still holds the
other interrupt sources off for roughly 7-10 ms.  The source comment
already documents the consequence:

- UART RX FIFO can overflow (`OERR`)
- TXIE-driven outgoing frames stall
- standby/wake traffic is delayed into the same vulnerable window

The 2026-04-22 live repro used the RC5 `STANDBY` / `WAKE` endpoint
path, so this bug is directly on the reproduced path: the operator's
IR wake press, the outbound wake frame, the reconnect poll, and the
inbound MAIN status burst all coincide.

V1.71 hardens OERR recovery at the parser head, but it does not remove
the fundamental timing hazard: the critical wake-time bytes can still be
lost or phase-shifted before the parser gets a clean pass.

### 2. The critical reconnect frames are still "best effort"

The CONTROL-side 3-byte wake/poll transmit paths all enqueue bytes via
`tx_byte_enqueue`, but they ignore `STATUS.C` on return:

- `poll_frame_send`
- `serial_tx_routed_frame` / `standby_wake_broadcast`
- `v171_send_wake_cmd_frame`
- `v171_send_standby_cmd_frame`

That matters because V1.71 Layer 1 deliberately changed
`tx_byte_enqueue` from "hang forever" to "drop the byte and return C=1"
when the TX ring is saturated.  For diagnostics traffic this is handled
correctly: `v171_diag_send_query_w` checks `C` after every byte and
aborts the frame atomically.  The wake/reconnect path does not.

So the current standby/wake path can do this on real hardware:

1. IR decode stalls TX/RX servicing.
2. The TX ring backs up.
3. CONTROL emits wake or reconnect poll bytes through a path that does
   not check for saturation.
4. One byte of a 3-byte frame is silently dropped.
5. MAIN may still wake, but CONTROL does not get a clean reconnect
   exchange and remains on `WAITING FOR DLCP`.

This fits the live result: MAINs can already be awake, active, and
passing audio while CONTROL is still stranded on the reconnect screen,
at least on the IR-driven wake path used for this repro.

## Why This Matches The Rig Better Than A MAIN-side Diagnosis

- The MAINs are alive on USB while CONTROL shows `WAITING`.
- Both MAINs report healthy wake completion (`gate_open=1`,
  `stdby_wake_pending=0`, only one `S/B` pair).
- Audio continuation after wake is consistent with MAIN-side wake having
  completed.
- The remaining failure is therefore at the CONTROL protocol/UI layer:
  CONTROL did not complete its own reconnect handshake cleanly even
  though the downstream MAIN state is already normal.

## Practical Implication

The current canonical pair still has a real standby/wake regression.
The user-visible symptom is `WAITING FOR DLCP`, but the failing side is
CONTROL reconnect handling, not MAIN wake sequencing.

The next firmware work should therefore target CONTROL:

1. remove or defer the IR decoder from the ISR hot path during wake /
   reconnect-sensitive windows
2. make wake/poll TX frame emission atomic by checking `STATUS.C`
   after each `tx_byte_enqueue` and retrying or aborting cleanly
3. add a real end-to-end standby/wake test for the current canonical
   pair that covers the explicit `STANDBY` / `WAKE` endpoint path on
   real hardware, not only source-level structural guards
