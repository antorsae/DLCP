# SRC4382 USB Diagnostics Spec

Last updated: 2026-05-13
Status: draft, not implemented
Scope: MAIN V3.2+ USB HID diagnostics for the SRC4382. CONTROL LCD/UART presentation is intentionally out of scope for this first pass.

## Purpose

Add a USB-visible diagnostic surface for the SRC4382 so a host tool can answer:

- Which digital receiver/input is selected by the MAIN firmware.
- Whether the receiver path is locked, unstable, or reporting errors.
- Whether the selected stream looks like linear PCM or a known compressed/non-PCM payload.
- What sample-rate evidence is available.
- What audio serial format the MAIN configured internally.
- What source-reported channel-status metadata says about word length, sample frequency, and consumer/professional mode.

The endpoint must be read-only from the operator perspective. It may perform temporary internal reads and temporary page selection, but it must not expose arbitrary SRC4382 writes over USB.

## Non-Goals

- No CONTROL diagnostics page yet.
- No UART-chain diagnostic frame yet.
- No arbitrary SRC4382 register write endpoint.
- No firmware-side full IEC 60958/AES3 decoder unless it proves cheap enough.
- No claim that the SRC4382 can detect IEEE float PCM. It can expose PCM/non-PCM evidence and raw channel-status/user-data bytes; float-looking PCM is not reliably distinguishable at this layer.
- No change to the existing audio routing or input-selection behavior.

## Existing Firmware Baseline

The MAIN already talks to the SRC4382 over the secondary I2C path using device address `0xE2` for writes and `0xE3` for reads.

Relevant V3.2 code paths:

- `i2c_secondary_dev_write` writes one SRC4382 register through the secondary bus.
- `i2c_secondary_dev_random_read` reads one SRC4382 register through the secondary bus.
- Boot initialization writes page-0 registers including `0x01`, `0x03`, `0x04`, `0x05`, `0x06`, `0x07`, `0x08`, `0x0D`, `0x0E`, `0x0F`, `0x10`, `0x11`, `0x1C`, `0x1D`, `0x2D`, and `0x2E`.
- Input selection writes `0x0D` and `0x08`:
  - Input 1: `0x0D=0x09`, `0x08=0x70`
  - Input 2: `0x0D=0x0A`, `0x08=0xB0`
  - Input 3: `0x0D=0x08`, `0x08=0x30`
  - Input 4: `0x0D=0x0B`, `0x08=0xF0`
- Auto-detect reads `0x13`, then `0x12` when `0x13` is nonzero.

Current USB diagnostic commands:

- `0x43`: diagnostic flash/EEPROM memory read.
- `0x44`: V3.2 Layer 5 health snapshot.

This spec reserves `0x45` and `0x46` for SRC4382 diagnostics.

## Diagnostic Evidence

| Evidence | SRC4382 source | Firmware should return | Host should decode |
| --- | --- | --- | --- |
| Selected receiver | page 0 `0x0D` | Raw register plus derived receiver index | RX1..RX4 from the low RXMUX bits |
| TX/output bypass path | page 0 `0x08` | Raw register | Match against known firmware values |
| SRC/DIT status | page 0 `0x0A` | Raw register | READY/RATIO/TSLIP/TBTI status bits |
| Non-PCM flags | page 0 `0x12` | Raw register | IEC 61937 and DTS CD/LD evidence |
| Receiver status | page 0 `0x13` | Raw register | Recovered-clock rate class, not exact sample rate |
| Receiver errors | page 0 `0x14`, `0x15` | Raw registers | CSCRC/PARITY/VBIT/BPERR/QCHG/UNLOCK/QCRC/RBTI/OSLIP |
| IEC 61937 payload | page 0 `0x29..0x2C` | Raw PC/PD registers | Payload type, if present |
| SRC ratio | page 0 `0x32`, then `0x33` | Raw integer/fractional registers read in order | Estimate input rate only if output rate is known |
| Internal port format | page 0 `0x03`, `0x05`, `0x2F` | Raw registers | MAIN-configured serial format and SRC output word length |
| Channel status | page 1 selected bytes | Raw channel 1 and channel 2 bytes | Source-reported sample frequency, word length, PCM/non-PCM metadata |

Important reliability split:

- Internal bit format is configuration, so it is high confidence. Current firmware configures 24-bit left-justified on the active audio serial path and does not write SRC output word-length register `0x2F`, whose reset default is 24-bit.
- Incoming bit depth and nominal sample frequency are source-reported metadata from channel-status bytes. They should be displayed as "reported by source" rather than treated as measured truth.
- The ratio registers can support a measured-rate estimate, but only after the host supplies or learns the SRC output rate. The first host tool should display the raw ratio by default and compute rate only when `--output-rate-hz` is provided.

## HID Command 0x45: Selected-Signal Snapshot

`0x45` returns one compact, read-only SRC4382 snapshot for the currently selected receiver path.

Request report:

| Offset | Name | Value |
| --- | --- | --- |
| 0 | command | `0x45` |
| 1 | subcommand | `0x00` for selected-signal snapshot |
| 2 | flags | bit 0: request page-1 channel-status bytes; bit 1: request IEC 61937 PC/PD bytes |
| 3..63 | reserved | `0x00` |

Response report:

| Offset | Name | Value |
| --- | --- | --- |
| 0 | command | `0x45` |
| 1 | status | `0x00` OK, `0x01` I2C error, `0x02` unsupported, `0x03` bad request, `0x04` partial snapshot |
| 2 | payload_len | `0x22` for schema 1 |
| 3 | schema_rev | `0x01` |
| 4 | snapshot_flags | See below |
| 5 | selected_rx | `0..3` for RX1..RX4, `0xFF` unknown |
| 6 | reg_0d_receiver_control | Raw page-0 `0x0D` |
| 7 | reg_08_tx_control | Raw page-0 `0x08` |
| 8 | reg_0a_src_dit_status | Raw page-0 `0x0A` |
| 9 | reg_12_non_pcm | Raw page-0 `0x12` |
| 10 | reg_13_receiver_status | Raw page-0 `0x13` |
| 11 | reg_14_receiver_error_1 | Raw page-0 `0x14` |
| 12 | reg_15_receiver_error_2 | Raw page-0 `0x15` |
| 13 | reg_32_ratio_integer | Raw page-0 `0x32`, read before `0x33` |
| 14 | reg_33_ratio_fraction | Raw page-0 `0x33`, read immediately after `0x32` |
| 15 | reg_03_port_a_control | Raw page-0 `0x03` |
| 16 | reg_05_port_b_control | Raw page-0 `0x05` |
| 17 | reg_2d_src_control_1 | Raw page-0 `0x2D` |
| 18 | reg_2e_src_control_2 | Raw page-0 `0x2E` |
| 19 | reg_2f_src_word_length | Raw page-0 `0x2F` |
| 20 | cs_ch1_byte0 | Page-1 channel 1 status byte 0, or `0xFF` if absent |
| 21 | cs_ch1_byte1 | Page-1 channel 1 status byte 1, or `0xFF` if absent |
| 22 | cs_ch1_byte2 | Page-1 channel 1 status byte 2, or `0xFF` if absent |
| 23 | cs_ch1_byte3 | Page-1 channel 1 status byte 3, or `0xFF` if absent |
| 24 | cs_ch1_byte4 | Page-1 channel 1 status byte 4, or `0xFF` if absent |
| 25 | cs_ch1_byte5 | Page-1 channel 1 status byte 5, or `0xFF` if absent |
| 26 | cs_ch2_byte0 | Page-1 channel 2 status byte 0, or `0xFF` if absent |
| 27 | cs_ch2_byte1 | Page-1 channel 2 status byte 1, or `0xFF` if absent |
| 28 | cs_ch2_byte2 | Page-1 channel 2 status byte 2, or `0xFF` if absent |
| 29 | cs_ch2_byte3 | Page-1 channel 2 status byte 3, or `0xFF` if absent |
| 30 | cs_ch2_byte4 | Page-1 channel 2 status byte 4, or `0xFF` if absent |
| 31 | cs_ch2_byte5 | Page-1 channel 2 status byte 5, or `0xFF` if absent |
| 32 | reg_29_pc_high | Raw page-0 `0x29`, or `0xFF` if not requested |
| 33 | reg_2a_pc_low | Raw page-0 `0x2A`, or `0xFF` if not requested |
| 34 | reg_2b_pd_high | Raw page-0 `0x2B`, or `0xFF` if not requested |
| 35 | reg_2c_pd_low | Raw page-0 `0x2C`, or `0xFF` if not requested |
| 36 | reserved | `0x00` |

`snapshot_flags`:

| Bit | Meaning |
| --- | --- |
| 0 | Page-1 channel-status bytes are present |
| 1 | IEC 61937 PC/PD bytes are present |
| 2 | One or more I2C reads failed; missing fields are filled with `0xFF` |
| 3 | The endpoint temporarily changed SRC4382 page select and restored page 0 |
| 4 | The endpoint temporarily froze channel-status transfer and restored receiver control |
| 5..7 | Reserved |

Response length note: `payload_len` counts bytes starting at offset 3. Schema 1 has 34 payload bytes, so `payload_len=0x22`.

### Read Sequence

The firmware sequence for `0x45` should be:

1. Read page-0 registers while page 0 is selected.
2. Read `0x32` and `0x33` consecutively when ratio is requested. Do not read any other SRC4382 register between them.
3. If page-1 channel-status bytes are requested:
   - Save page-0 `0x0D`.
   - Optionally set `RXBTD` in `0x0D` to freeze receiver C/U transfer while copying channel-status bytes. This should be enabled only after a hardware check confirms no audio interruption.
   - Write page select register `0x7F=0x01`.
   - Read channel-status bytes 0..5 for channel 1 and channel 2 from page 1.
   - Write page select register `0x7F=0x00`.
   - Restore saved `0x0D` if it was changed.
4. On any I2C error, finish the HID response with `status=0x04` or `0x01`, set snapshot flag bit 2, and fill missing fields with `0xFF`.
5. Always leave the SRC4382 on page 0 before returning.

The first implementation may omit the RXBTD freeze and still return page-1 bytes. If omitted, the host must treat channel-status bytes as a best-effort snapshot and may poll twice to confirm stability.

## HID Command 0x46: Raw Read Window

`0x46` is an optional debug endpoint for bounded raw reads. It exists to debug host-side decoders without adding new firmware fields for every SRC4382 register. It must remain read-only and must never expose arbitrary writes.

Request report:

| Offset | Name | Value |
| --- | --- | --- |
| 0 | command | `0x46` |
| 1 | page | `0x00`, `0x01`, or `0x02` |
| 2 | start_reg | Register address on the selected page |
| 3 | count | Number of bytes, maximum `0x30` |
| 4 | flags | bit 0: restore page 0 after read, must be set by host |
| 5..63 | reserved | `0x00` |

Response report:

| Offset | Name | Value |
| --- | --- | --- |
| 0 | command | `0x46` |
| 1 | status | `0x00` OK, `0x01` I2C error, `0x02` unsupported, `0x03` bad request |
| 2 | count | Number of returned data bytes |
| 3..50 | data | Raw bytes |
| 51..63 | reserved | `0x00` |

Firmware rules:

- Reject `count > 0x30`.
- Reject pages outside `0x00..0x02`.
- Restore page 0 before returning, even if a read fails.
- Do not support write flags.
- Keep this endpoint behind the same release safety bar as `0x43`: useful for diagnostics, but not necessary for normal operation.

## Host-Side Decoding

The host tool should live next to the existing USB diagnostics scripts, for example `scripts/dlcp_src4382_diag.py`.

Required output fields:

- Selected receiver: RX1, RX2, RX3, RX4, or unknown.
- Lock state: derive from receiver error/status registers. `UNLOCK` must be surfaced directly.
- Receiver errors: show named bits from `0x14` and `0x15`.
- Non-PCM: show IEC 61937/DTS flags from `0x12`, plus PC/PD payload type when PC/PD bytes are available.
- SRC ratio: print raw `SRI/SRF` and fixed-point ratio.
- Estimated input sample rate: print only when `--output-rate-hz` is supplied or a later host profile provides the DLCP output rate. Mark it as estimated.
- Receiver clock class: decode `0x13` as a coarse class only, not as an exact sample rate.
- Channel-status sample frequency and word length: decode page-1 bytes if stable, but label as source-reported.
- Internal serial format: decode `0x03`, `0x05`, and `0x2F`.

### Ratio Handling

The datasheet defines `SRI` as the SRC input-to-output sampling-ratio integer part and `SRF` as the fractional part. The host should treat the pair as fixed-point:

```text
ratio = SRI + (SRF / 2048.0)
estimated_input_hz = ratio * output_hz
```

This estimate should be marked unstable unless two consecutive snapshots match or fall within a small tolerance while the receiver is locked.

### Bit Format Handling

There are two separate questions:

1. What format is the MAIN feeding internally?
2. What format does the external source claim it is sending?

The first is answered from registers `0x03`, `0x05`, and `0x2F`. This is firmware configuration. The current expected decode is 24-bit left-justified on the active path and 24-bit SRC output word length.

The second is answered from DIR channel-status bytes on page 1. It is source metadata, not a direct measurement. The host should display raw bytes when the decode is unknown or inconsistent.

Float handling: no reliable float indicator exists in the SRC4382 status set. If the source sends float samples while declaring linear PCM, this endpoint should not claim to detect that.

## Simulator Requirements

The Rust SRC4382 model must be strengthened before the new tests can represent real hardware behavior:

- Model page select register `0x7F`.
- Maintain independent page-0, page-1, and page-2 register storage.
- Preserve current page-0 behavior for existing boot and input-selection tests.
- Add test knobs for:
  - `0x12` non-PCM flags.
  - `0x13` receiver status.
  - `0x14` and `0x15` receiver errors.
  - `0x29..0x2C` IEC 61937 PC/PD fields.
  - `0x32/0x33` ratio fields.
  - page-1 channel-status bytes.
- Verify that a HID snapshot using page 1 restores page 0.
- Verify that no raw write endpoint exists.

## Required Tests

Red tests must land before firmware implementation.

Unit/host tests:

- Parse a synthetic `0x45` response with locked PCM, stable ratio, and channel-status bytes.
- Parse a synthetic `0x45` response with `UNLOCK`, receiver errors, and missing page-1 bytes.
- Parse IEC 61937 PC/PD bytes for at least AC-3, MPEG, AAC, DTS, and unknown payload types.
- Decode internal serial format from known firmware values: `0x03=0x30`, `0x05=0x08`, `0x2F=0x00`.
- Confirm the host does not print an exact sample rate unless an output rate is provided.
- Confirm "float" is never inferred from SRC4382 status alone.

Simulator tests:

- `cmd 0x45` returns the seeded SRC4382 page-0 status registers through the firmware USB HID path.
- `cmd 0x45` returns seeded page-1 channel-status bytes and restores page 0.
- `cmd 0x45` reports partial snapshot status when the simulated SRC4382 NACKs one read.
- `cmd 0x46` reads bounded raw windows and rejects out-of-range pages/counts.
- Existing V3.2 `0x43` and `0x44` diagnostics remain unchanged.

Hardware tests:

- With a known locked digital source, `dlcp_src4382_diag.py` reports receiver lock and no new I2C diagnostic fault.
- Poll `0x45` at 1 Hz for at least 60 seconds while audio plays; audio must not mute, click, or switch inputs.
- Run the same source at 44.1 kHz, 48 kHz, and 96 kHz if available. The raw ratio and source-reported channel status must change coherently.
- Feed known non-PCM/IEC 61937 content if available and verify the non-PCM fields are surfaced.
- Disconnect the digital input and verify `UNLOCK` or equivalent receiver-error state is surfaced without hanging USB.

## Implementation Plan

1. Add host parser and synthetic parser tests.
2. Add Rust SRC4382 page/status modeling.
3. Add failing firmware-path USB HID tests for `0x45`.
4. Implement minimal V3.2 USB dispatch for `0x45`.
5. Add `scripts/dlcp_src4382_diag.py`.
6. Add optional `0x46` only if raw-read debugging is needed after `0x45` is working.
7. Run the sim gate.
8. Run the hardware polling and sample-rate evidence gate.

## Open Questions

- What exact output sample rate should the host use for estimated input-rate display on the deployed DLCP path? Until this is confirmed, require `--output-rate-hz` for exact estimates.
- Should `cmd 0x45` freeze receiver C/U transfer with `RXBTD` while reading page 1? This likely improves metadata consistency, but it must be hardware-checked for audio side effects.
- Is `cmd 0x46` worth shipping in the canonical release, or should it remain a local debug build feature?
- Which known digital source should be the hardware baseline for 44.1/48/96 kHz validation?

## References

- TI SRC4382 datasheet, register maps and I2C access.
- Existing MAIN V3.2 SRC4382 I2C call sites in `src/dlcp_fw/asm/dlcp_main_v32.asm`.
- Existing USB diagnostics in `docs/V32_DIAG_TIER1_SPEC.md` and `src/dlcp_fw/flash/dlcp_diag.py`.
