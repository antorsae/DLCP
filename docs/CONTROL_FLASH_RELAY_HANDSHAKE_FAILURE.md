# CONTROL Flash Relay Handshake Failure

Date: 2026-06-30

Status: fixed in MAIN V3.5 rev `0x009A`; live hardware not run

## Summary

CONTROL flashing through MAIN can appear to stream successfully while MAIN has
not actually armed the CONTROL firmware-update relay.  In that state every host
`0x42` data report can receive a clean-looking `42 00 00 00` response, but no
payload bytes are relayed to CONTROL and MAIN's relay CRC accumulator remains
zero.  The operator only sees the real failure at final `0x41` verify:

```text
streaming: report=1019 pos=0x776A/77C0 ( 99.7%) resp[0..3]=42 00 00 00
sending CRC verify (0x41)...
verify resp[0..7] = 41 11 00 00 00 00 00 00
RuntimeError: CRC verify failed (resp[2]=0x00, expected 0xAA)
```

MAIN V3.5 rev `0x009A` changes that failure from a late full-stream CRC failure
into an immediate `42 12 ...` relay-not-armed response.  The repo flasher now
aborts on that status with manual bootloader guidance instead of streaming the
remaining reports.  The same V3.5 build also fixes the relay's final application
record boundary so the `0x77B0..0x77BF` CONTROL metadata row is sent and
acknowledged before final `0x41` verification, and fixes packet-boundary CR/LF
injection so a 30-byte HID report boundary cannot split a downstream `:10`
Intel HEX data record.

Manual CONTROL bootloader entry remains the live operator path unless app-side
handoff has been separately validated: power-cycle CONTROL while holding
`UP+DOWN` for at least 6 seconds, do not press `SELECT`, then run
`scripts/flash_control_safe.sh` through the explicit relay MAIN HID path.

## Affected Behavior

The visible symptom is "I have to flash CONTROL twice" or "CONTROL flash reaches
99-100 percent and then fails CRC verify."  The root failure is earlier: MAIN
does not see or accept CONTROL's `FW_Upd` bootloader prompt during the first
`0x42` handshake, so `fw_update_relay_session_active_b0` never becomes set.

For the 2026-06-30 reproduction:

- previous deployed CONTROL artifact: V1.73 rev `0x5F`, build `20260629`
- target CONTROL artifact: V1.73 rev `0x60`, build `20260630`
- fixed MAIN artifact: canonical V3.5 rev `0x009A`
- target stream length: `0x77C0` bytes, 1022 reports
- expected relay CRC: `0x2780`
- observed final verify: `41 11 00`

## Firmware Mechanism

MAIN command `0x42` is the CONTROL firmware relay entry.  The first host `0x42`
report already contains firmware bytes at payload offsets `2..31`; there is no
separate magic/init-only report.

The intended first-report sequence is:

1. MAIN clears relay state.
2. MAIN sends `BF 18 01` to CONTROL.
3. CONTROL enters bootloader and emits `:FW_Upd\r\n`.
4. MAIN matches `FW_Upd`, sets relay-session flag `0xCB`, and relays that same
   first `0x42` report.
5. Later `0x42` reports are forwarded as Intel HEX records.
6. Final host `0x41` compares the host CRC against MAIN's relay accumulator.

The failure path is:

1. MAIN clears relay state.
2. MAIN sends `BF 18 01`.
3. MAIN does not accept a valid `FW_Upd` prompt inside its handshake window.
4. MAIN leaves relay-session flag `0xCB` clear.
5. MAIN still returns through the normal HID response path for `0x42`.
6. The host streams every report, seeing `42 00 00 00`.
7. No bytes were relayed, so MAIN's CRC accumulator is still wrong.
8. Final `0x41` returns error byte `0x11` and no success byte `0xAA`.

## Simulator Evidence

A local old-to-new simulation of the old behavior reproduced the first failure
exactly:

```text
pass1 stream 1022 100.0% resp 42 00 00 00
pass1 verify 41 11 00 00 00 00 00 00 ...
```

A second pass on the same simulated device also failed:

```text
pass2 stream 1022 100.0% resp 42 00 00 00
pass2 verify 41 11 00 00 00 00 00 00 ...
summary pass1_ok False pass2_ok False
```

The simulator therefore reproduces the first failure, but not the reported
"second attempt works" behavior.  That second-attempt behavior likely depends
on a real CONTROL bootloader/reset state transition that the current rust
facade does not model faithfully.

The diagnostic accumulator probe showed:

```text
expected_crc=0x2780 len=30656 reports=1022
report=1    sig=0x0000 session=0x00
report=500  sig=0x0000 session=0x00
report=1000 sig=0x0000 session=0x00
report=1022 sig=0x0000 session=0x00
preverify sig=0x0000 expected=0x2780 session=0x00
```

The fix added a full-chain HID helper that keeps MAIN and CONTROL running while
each host report is serviced.  That exposed and fixed two simulator fidelity
issues required for real CONTROL bootloader proof:

- EUSART `RCREG` now keeps the last received byte latched after the RX FIFO
  drains, matching the CONTROL bootloader's double-read behavior.
- Program-memory erase uses the 64-byte PIC18F25K20 erase row rather than the
  32-byte write latch size.

The full-chain simulations now pass:

- `tests/sim/test_dlcp_control_flash_safety.py::test_full_chain_fixed_main_flashes_control_v173_through_real_bootloader`
  proves current deployed/control image to fixed target reaches `41 00 aa` and
  readback matches the target application window plus release metadata.
- `tests/sim/test_dlcp_control_flash_safety.py::test_full_chain_fixed_main_flashes_newer_v173_through_real_bootloader`
  proves fixed-good to newer-good using a builder-generated newer V1.73 target
  artifact.

The tests simulate CONTROL manual bootloader reset during the first report; they
do not claim app-mode `BF/18/01` handoff field closure.

## Stock V2.3 Lineage

This is not a new V3.5 invention.  Stock MAIN V2.3 has the same static control
flow in `firmware/disasm/main/gpdasm_output.annotated.asm`:

- `label_060` at `0x1456` handles host `0x42`.
- It clears relay state, sends `BF 18 01`, waits for `FW_Upd`, and sets RAM
  `0x0CB` only on a prompt match.
- If `0x0CB` remains clear, `label_064` branches to `label_056`, the normal HID
  response path, not to a hard error path.
- Final `label_066` handles host `0x41`; on CRC mismatch it writes `0x11` into
  response byte `0x15B`.

The source-equivalent V3.0 rewrite in `src/dlcp_fw/asm/dlcp_main_v30.asm`
matches the same relay structure.  A runtime stock-V2.3 replay through
`Chain.firmware_hid_report` was inconclusive because that helper is documented
as a V3.x EP1 dispatcher path and did not capture a valid stock V2.3 EP1 IN
response for this command.  The disassembly is the authoritative evidence for
the stock behavior shape.

The stock-latent bug is usually hidden when paired with CONTROL versions whose
application-side `BF/18/01` handoff works.  It becomes operator-visible with
CONTROL lines where app-side bootloader entry is unreliable or absent.

## Residual Risk

- App-mode CONTROL bootloader handoff is still not claimed as a field-closed
  convenience path.
- Live hardware flash confirmation was not run for this fix.
- Operators using older MAIN firmware can still see the late `41 11 00` failure
  shape or malformed downstream Intel HEX records; flash MAINs to V3.5 rev
  `0x009A` or newer first.

## Implemented Fix

- MAIN V3.5 rejects unarmed `0x42` relay sessions with response byte `0x12`
  after the normal empty-reply stager, so the status is not clobbered.
- Relay status cleanup now also clears the relay-session flag.
- The relay keeps `0x77BF` inside the flashable app window and flushes any saved
  final record when the stream cursor reaches the exclusive `0x77C0` bootloader
  limit.
- The relay returns to the HID handler after each 30-byte payload report instead
  of falling through into the CR/LF helper, so partial downstream Intel HEX data
  records stay contiguous across HID packet boundaries.
- `dlcp_control_flash.py` rejects nonzero `0x42` stream status immediately; for
  `0x12` it raises `ControlRelayNotArmedError` and the CLI prints concise
  `UP+DOWN` bootloader guidance without a Python traceback.
- The final `41 11` error text now calls out older MAIN firmware that may have
  ACKed stream reports while the relay stayed inactive.

## Regression Coverage

- Fast negative and flasher coverage:
  - `test_flash_control_aborts_when_main_reports_relay_not_armed`
  - `test_cli_reports_relay_not_armed_without_traceback`
  - `test_source_assembled_v35_unarmed_relay_rejects_first_42_report`
  - `test_canonical_v35_unarmed_relay_rejects_first_42_report_after_release_build`
  - `test_old_relay_false_ack_behavior_reproduces_with_temp_mutation`
- Structural V3.5 pins:
  - `test_v35_control_flash_relay_rejects_unarmed_session_before_empty_status`
  - `test_v35_control_flash_relay_flushes_final_app_record_before_limit`
- Slow full-chain proof:
  - `test_full_chain_fixed_main_flashes_control_v173_through_real_bootloader`
  - `test_full_chain_fixed_main_flashes_newer_v173_through_real_bootloader`
  - both tests also assert emitted MAIN relay `:10` data records are complete
    per UART route, not split by packet-boundary CR/LF.

## Operational Guidance Until Fixed

Use the manual CONTROL bootloader path for live CONTROL flashing:

```bash
# Power-cycle CONTROL while holding UP+DOWN for at least 6s.
# Do not press SELECT.
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" \
  --hex firmware/patched/releases/DLCP_Control_V1.73.hex \
  --preflight-only

scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" \
  --hex firmware/patched/releases/DLCP_Control_V1.73.hex
```

If fixed MAIN returns `42 12`, the relay did not arm and the payload was not
streamed; re-enter manual bootloader mode and retry.  If final verify returns
`41 11 00`, do not treat the flash as complete; that shape usually means an
older MAIN relay path or another CRC/transport failure.
