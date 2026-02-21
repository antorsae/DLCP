# HFD v4.97 Reverse Engineering (Codex)

## Scope

Target artifacts:
- `firmware/stock/PC/HFD_v4.97/Setup.exe`
- `firmware/stock/PC/HFD_v4.97/Resources/HFD.exe`
- `firmware/stock/PC/HFD_v4.97/Resources/mcHID.dll`

Primary goal:
- Determine exactly how HFD v4.97 retrieves and displays **DSP Filename** in the main window (`Device info`).

Secondary goal:
- Confirm related write path (setting DSP filename), because read/write usually share the same command family.

Supporting disassembly artifacts:
- `firmware/disasm/PC/HFD_v4.97/`

## Installer Unpack Findings

`Setup.exe` is a PE bootstrapper, not a plain Inno package.

- `innoextract` does not apply.
- `7z` extraction yields PE sections/resources only, not a hidden app payload archive.
- Actual app payload is already present under `Resources/` (`HFD.exe`, `mcHID.dll`, docs, sample files).

Evidence:
- `firmware/disasm/PC/HFD_v4.97/installer_unpack_notes.txt`
- `firmware/stock/PC/HFD_v4.97/_setup_extracted/`

## Key Exported Routines (HFD.exe)

From export table (`rabin2 -E` / `objdump`):

- `ReadAttachedDSPFilename` at `0x00ac0d54`
- `UpdateFilename` at `0x00ac0c74`
- `ReadAttachedProductInfo` at `0x00ac0b94`
- `ReadAttachedConfigurationInfo` at `0x00ac0288`
- `Connect` at `0x00abff70`
- `ReadLastCommandResult` at `0x00abfd5c`
- `ReadLastErrorStr` at `0x00abfd48`

Artifacts:
- `firmware/disasm/PC/HFD_v4.97/objdump_x_HFD_v4.97.exe.txt`
- `firmware/disasm/PC/HFD_v4.97/disasm_sym_ReadAttachedDSPFilename.asm`
- `firmware/disasm/PC/HFD_v4.97/disasm_sym_UpdateFilename.asm`

## HID API Surface (mcHID)

HFD v4.97 imports expected HID primitives from `mcHID.dll`:

- `Connect`, `Disconnect`
- `IsAvailable`, `GetHandle`
- `Read`, `Write`
- `SetReadNotify`
- `GetVendorID`, `GetProductID`, `GetProductName`, `GetSerialNumber`

Evidence:
- `firmware/disasm/PC/HFD_v4.97/rabin2_imports_HFD_v4.97.txt`

## Transport Stack (Relevant Layer)

The DSP filename calls use a common transaction stack:

1. `fcn.00abfdec` (preflight/guard)
   - validates device/session state and command-busy conditions.
   - artifact: `disasm_fcn_00abfdec_preflight_guard.asm`

2. `fcn.00aca588` (request object builder)
   - takes a stack argument (`ret 4`): timeout value.
   - initializes request object, writes timeout at `[req + 0x2c]`.
   - artifact: `disasm_fcn_00aca588_request_builder.asm`

3. `fcn.00ac012c` (exchange wrapper)
   - builds request (`call 0x00aca588`), executes transport (`0x004e0830`, `0x004e08f8`), copies response text to `[ctx + 0x98]`.
   - returns status from `[req + 0x2a]`.
   - artifact: `disasm_fcn_00ac012c_exchange_wrapper.asm`

4. `fcn.004e08f8` (poll/read transaction stage)
   - loops with `0x40` byte buffers and timeout-related values (`0x3e8`, etc.), consistent with HID report exchange.
   - artifact: `disasm_fcn_004e08f8_transport_poll.asm`

## DSP Filename Read Path (Definitive)

Routine: `sym.HFD.exe_ReadAttachedDSPFilename` (`0x00ac0d54`)

Critical instructions:
- `mov byte [eax + 0x46], 3`
- `mov byte [eax + 0x47], 8`
- `mov ecx, 0x64`
- `mov dx, 2`
- `call 0x00ac012c`

Interpretation:
- HFD emits command family `0x03` with subcommand `0x08` to read DSP filename.
- Timeout argument is `0x64` (100), passed via stack into `fcn.00aca588`.

Response handling:
- On success, filename is copied from context offset `[ctx + 0x103ac]` to caller output buffer.
- Status/error text is copied from `[ctx + 0x98]`.
- Final result is normalized through `call 0x00abff18` (last-result/last-error state update path).

Evidence:
- `firmware/disasm/PC/HFD_v4.97/disasm_sym_ReadAttachedDSPFilename.asm`

## DSP Filename Write Path (Definitive)

Routine: `sym.HFD.exe_UpdateFilename` (`0x00ac0c74`)

Critical instructions:
- `mov byte [eax + 0x46], 3`
- `mov byte [eax + 0x47], 9`
- copies user-provided filename bytes into command payload window starting at `[ctx + 0x45 + 3]` (effectively payload after cmd/subcmd bytes).
- `mov ecx, 0x64`
- `mov dx, 2`
- `call 0x00ac012c`

Interpretation:
- HFD emits command family `0x03` with subcommand `0x09` to set/update DSP filename on the attached DLCP.

Evidence:
- `firmware/disasm/PC/HFD_v4.97/disasm_sym_UpdateFilename.asm`

## MAIN Firmware Storage/Persistence for DSP Filename (Definitive)

The host-side `0x03/0x08` and `0x03/0x09` operations map to a concrete MAIN
firmware storage path.

- Runtime RAM filename slot:
  - `0x02C0..0x02DD` (30 bytes), implemented as base `0x02BE + idx`
    with `idx=0x02..0x1F`.
- Write path (`cmd=0x03, subcmd=0x09`):
  - copies host payload bytes into `0x02C0..0x02DD`;
  - converts input `0x00` to stored `0xFF` (erase/sentinel style);
  - sets dirty flag `0x0BD.5`.
- Erase path (`cmd=0x03, subcmd=0x0A`):
  - sets the same slot to `0xFF`.
- Read path (`cmd=0x03, subcmd=0x08` response family):
  - returns bytes from `0x02C0..0x02DD`.

Persistence across reboot:

- Dirty handler checks `0x0BD.5` and writes RAM filename bytes to EEPROM
  `0x60..0x7D`.
- Boot/init (`function_007`) reads EEPROM `0x60..0x7D` and reconstructs
  RAM `0x02C0..0x02DD`.

Primary evidence:
- `firmware/disasm/main/gpdasm_output.asm` (`label_003`, `label_238`,
  `function_007`, `function_015`, `function_094`, `function_110`)

## Saved EEPROM Dump Decode

Using the captured dump:

- `firmware/dumps/eeprom.bin`

Decoded filename persistence region:

- EEPROM `0x60..0x7D` is all `0xFF`.

Conclusion:

- In this specific dump, there is no persisted DSP filename payload.
- So no prior filename string can be recovered from this EEPROM image.

## Product Info vs DSP Filename

`ReadAttachedProductInfo` is separate (`0x00ac0b94`) and does not use the `0x03/0x08` filename pattern directly.

`ReadAttachedProductInfo` reads multiple fields from context offsets (`0x106c0`, `0x106c1`, `0x106c2`, etc.), while DSP filename read specifically pulls from `0x103ac` after the `0x03/0x08` transaction.

Evidence:
- `firmware/disasm/PC/HFD_v4.97/disasm_sym_ReadAttachedProductInfo.asm`

## UI Binding Evidence for Main Window

Direct static string evidence in `HFD.exe` includes:
- `"DSP filename"`
- `"LblDSPFilename"`
- `"GetDeviceDSPFilename"`
- `"aNewDSPFilename"`
- `"SetFilename"`

This is consistent with a UI label/property pipeline where device model refresh pulls DSP filename from the `ReadAttachedDSPFilename` command path.

Evidence:
- `firmware/disasm/PC/HFD_v4.97/strings_HFD_v4.97.txt`

Note:
- Direct intra-code xrefs into `ReadAttachedDSPFilename` are sparse/absent in static pass (likely Delphi RTTI/event indirection and/or method table dispatch), but command-level behavior is still explicit in the routine itself.

## Practical Conclusion

For v4.97, DSP filename displayed in main window is retrieved from the device via host transaction:

- **Read:** command family `0x03`, subcommand `0x08`
- **Write:** command family `0x03`, subcommand `0x09`

So the displayed value is not a UI-local cache only; it is backed by explicit DLCP command/response exchange.

## Suggested Next Validation (Dynamic)

To fully close the loop on wire-level framing:

1. Capture HID traffic while pressing connect/refresh in v4.97.
2. Filter for reports containing command bytes corresponding to `0x03/0x08` and `0x03/0x09`.
3. Correlate returned payload bytes with displayed `DSP filename` text.

This would provide packet-level confirmation in addition to current static proof.
