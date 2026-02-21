# HFD v2.12 Reverse Engineering (Codex)

## Scope

Target binary:
- `firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe`
- `firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/mcHID.dll`

Focused goals:
1. Map HFD v2.12 interaction with DLCP over USB HID.
2. Identify where routing options (`Left/Right/L+R/L-R`) are represented and transmitted.
3. Define concrete patch points for adding `R-L` once firmware-side `R-L` exists (per `docs/R_L_ROUTING.md`).

All supporting disassembly artifacts are in:
- `firmware/disasm/PC/HFD_v2.12/`

Concrete byte-level patch manifest:
- `docs/analysis/HFD_v2.12-RL-binary-patch-plan.md`

## Executive Summary

- HFD v2.12 talks to DLCP via `mcHID.dll` HID wrappers (`Read/Write/Connect/GetVendorID/...`).
- The central host command sender is `0x554f50`; it builds a report via `0x554590` and writes it through HID.
- Device VID/PID are hardcoded in the transport path: `VID=0x04D8`, `PID=0xFF89`.
- Host command IDs used by HFD are: `0x03`, `0x04`, `0x05`, `0x06`, `0x40`, `0x41`, `0x42`.
- Routing UI options are hardcoded as four strings and loaded into each channel combo from addresses `0x551710`, `0x551720`, `0x551730`, `0x551740`.
- Selected routing indices are copied to state bytes `+0x5E..+0x63` and sent to DLCP via command `0x05`.
- Firmware update path is implemented in HFD using commands `0x40/0x41/0x42`; this appears to be the control-update relay path through DLCP.

## Binary Interface Architecture

### `mcHID.dll` role

`mcHID.dll` exports the HID abstraction used by HFD, including:
- `Connect`, `Disconnect`
- `GetItemCount`, `GetItem`
- `Read`, `Write`
- `GetVendorID`, `GetProductID`, `GetProductName`
- `SetReadNotify`, `IsAvailable`

See:
- `firmware/disasm/PC/HFD_v2.12/objdump_x_mcHID.dll.txt`
- `firmware/disasm/PC/HFD_v2.12/rabin2_imports_mcHID.txt`

### EXE transport core

Key functions (VA):
- `0x554f1c`: setup/connect helper
- `0x554f50`: packet send wrapper (build + HID write)
- `0x554f98..0x555314`: HID/session dispatcher (enumeration/connect/read)
- `0x553910`: response parser

See:
- `firmware/disasm/PC/HFD_v2.12/disasm_usb_transport_554f1c_555320.asm`
- `firmware/disasm/PC/HFD_v2.12/disasm_response_parser_553910_554520.asm`
- `firmware/disasm/PC/HFD_v2.12/r2_xrefs_mcHID_calls.txt`

## HID Session Flow (Observed)

From `0x554f98` dispatcher:

1. Availability check:
- `IsAvailable(0x04D8,0xFF89)`

2. Device enumeration:
- `GetItemCount()`
- loop `GetItem(i)`
- validate `GetVendorID == 0x04D8` and `GetProductID == 0xFF89`

3. Session setup:
- `SetReadNotify(handle, -1)`
- reads product name via `GetProductName`
- initializes state/UI flags

4. I/O:
- Outgoing reports via `Write(handle, report_ptr)`
- Incoming reports via `Read(handle, buffer_ptr)`
- Responses parsed by `0x553910`

This confirms HFD speaks directly to the DLCP HID endpoint (main unit USB path).

## Report/Payload Format

### Outgoing

At `0x554f50`:
- zeroes 33 bytes at `[ctx + 0x25 .. +0x45]`
- calls `0x554590` to fill payload
- writes report buffer at `[ctx + 0x25]` via HID

At `0x554590`:
- `payload[0]` (`[ctx+0x25]`) set to `0`
- `payload[1]` (`[ctx+0x26]`) set to command ID (`dl`)
- subsequent bytes command-specific

### Incoming

- HID read target is `[ctx + 0x4]`
- parser reads command from `[ctx + 0x5]`

This is consistent with HID report-id style framing (offset-skewed structure in app memory).

## Host Command Surface in HFD v2.12

From packet builder and callsites, active command IDs are:
- `0x03`
- `0x04`
- `0x05`
- `0x06`
- `0x40`
- `0x41`
- `0x42`

Evidence:
- `firmware/disasm/PC/HFD_v2.12/disasm_packet_builder_554590_554980.asm`
- `firmware/disasm/PC/HFD_v2.12/callsites_command_dl_constants_55xxxx.txt`

### Practical semantics (inferred from code/data flow)

- `0x05`: bulk configuration push (includes routing bytes and many setup fields)
- `0x06`: configuration/capability pull; parser updates large state block and re-requests
- `0x04`: targeted setup/update command (subcommand in `cl`)
- `0x03`: message/transaction command used around filter/status operations
- `0x40/0x41/0x42`: firmware-update stream/control path
  - `0x40` and `0x42` stream data from table buffer
  - `0x41` transmits accumulator/finalization state
  - helper `0x554ea4` manipulates 16-bit state (`0x57b36c`) consistent with CRC/LFSR-style processing

## Main vs Control interaction (host perspective)

- USB HID endpoint is on DLCP main path (VID/PID device).
- HFD command surface includes firmware-update logic (`0x40/0x41/0x42`) and update status strings.
- Given DLCP architecture and existing firmware-update analysis, HFD reaches control firmware indirectly via main relay/update mechanism.

Relevant strings:
- `"Firmware update complete"`
- `"CRC error during Firmware update"`
- `"Function not supported in this product or firmware version"`

See:
- `firmware/disasm/PC/HFD_v2.12/strings_focus_HFD_v2.12.txt`

## Routing Pipeline (Critical for R-L)

## 1) UI option strings

Current option literals (shortstring records):
- `0x551710`: `Left`
- `0x551720`: `Right`
- `0x551730`: `L+R/Mid`
- `0x551740`: `L-R/Side`

See:
- `firmware/disasm/PC/HFD_v2.12/disasm_routing_strings_551700_551820.asm`

## 2) Combo initialization

Each channel-routing combo is populated with exactly those 4 strings.
Repeated blocks at:
- `0x550664/67a/690/6a6`
- `0x5507a5/7bb/7d1/7e7`
- and same pattern for remaining channels

See:
- `firmware/disasm/PC/HFD_v2.12/disasm_routing_combo_init_550620_550b00.asm`

## 3) Apply from UI to model

Callback at `0x551988`:
- reads combo selected indices (`+0x218` fields for six channel controls)
- stores into global route bytes:
  - ch1..ch6 -> `[state + 0x5E .. +0x63]`
- sends command `dl=0x05` (unless specific mode suppresses immediate send)

See:
- `firmware/disasm/PC/HFD_v2.12/disasm_routing_combo_apply_551980_551c00.asm`

## 4) Device response to model

Parser (`cmd 0x05` path near `0x553eb6`):
- copies incoming bytes `[+0x17..+0x1C]` into `[state +0x5E..+0x63]`

Parser (`cmd 0x06` path near `0x553ffc`) also updates broad state.

See:
- `firmware/disasm/PC/HFD_v2.12/disasm_cmd5_response_parse_553e70_553ffc.asm`
- `firmware/disasm/PC/HFD_v2.12/disasm_cmd6_response_and_fwupdate_dispatch_553ff0_554440.asm`

## 5) Outgoing packet packing

`cmd 0x05` builder case (`0x554738`) includes route bytes in outgoing payload.
No hard 2-bit packing is used; route values are byte fields, so value `4` is representable.

See:
- `firmware/disasm/PC/HFD_v2.12/disasm_packet_builder_554590_554980.asm`

## Implication: feasibility of adding `R-L` in HFD v2.12

Feasibility is good if firmware already accepts route value `4`.

Why:
- Route path is index-based byte transport, not fixed bitfield.
- Combo selected index is directly written/read and transported.
- Main blockers are UI list cardinality and any mode-specific assumptions expecting max index 3.

## Patch Plan for HFD v2.12 (`R-L`)

## A) UI option expansion (required)

1. Add new route label string (recommended `R-L`) in new data region/cave.
2. Extend each channel combo initialization block to add a 5th item.
   - Existing 4 AddItem-style calls are explicit and repeated per channel.
   - Patch either each block or common helper if found/introduced.

Primary patch region:
- `0x550620..0x550b00` (repeated combo setup sequences)

## B) Keep model transport unchanged (mostly)

No protocol rewrite required:
- Selection callback (`0x551988`) already forwards combo index byte.
- Command `0x05` already transmits route bytes as plain bytes.

## C) Defensive range handling (recommended)

Add/patch clamps for route values where UI is refreshed from device state:
- If any code path assumes `0..3`, expand to `0..4`.
- Candidate audit points:
  - combo refresh logic in `0x5574a4` region
  - any `SetItemIndex`/combo-state helper wrappers

## D) Mode-specific text/profile logic (audit)

There is separate routing-profile logic and alternate labels around:
- `0x556fcb..0x557360`
- `0x55710c` data region (`Left`, `Sub`, `Mid/Sub` etc.)

This appears related to mode-dependent UI; verify adding 5th routing option does not conflict with this path.

## Validation Plan for HFD patch

1. Static patch checks:
- 5th route string present
- each channel combo init has 5 insertions
- no corruption of nearby Pascal shortstring records

2. Runtime functional checks:
- Load profile with route value 4 from device -> UI shows `R-L`
- Change channel route to `R-L` in UI -> `cmd 0x05` emitted with value `4`
- Roundtrip save/load preserves value `4`

3. Compatibility checks:
- values `0..3` behavior unchanged
- firmware update flow (`0x40/0x41/0x42`) unaffected

## Important Caveats

- This RE pass is static (no live dynamic tracing under Windows in this pass).
- Some semantics (`cmd 0x03/0x04` sub-operations) are inferred from memory effects and should be treated as high-confidence inference, not vendor-spec truth.
- For production patching, prefer relocating new code/data into a verified code cave rather than in-place expansion of packed data regions.

## Quick Address Index

- HID sender: `0x554f50`
- HID dispatcher/enumeration: `0x554f98`
- Packet builder: `0x554590`
- Response parser: `0x553910`
- Route strings: `0x551710`, `0x551720`, `0x551730`, `0x551740`
- Route combo init blocks: `0x550664+`
- Route apply callback: `0x551988`
- Cmd5 parse route import: `0x553f99..0x553fba`
- Firmware-update command dispatch: `0x554245..0x554420`
