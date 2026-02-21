# HFD v2.12 RE Artifacts

This folder contains focused reverse-engineering artifacts for:
- `firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe`
- `firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/mcHID.dll`

Notes:
- Addresses are image virtual addresses (VA).
- Disassembly was generated with `objdump -d -Mintel` unless noted.
- `0x554f50` is the central host->DLCP HID command sender.

## Key files

- `disasm_usb_transport_554f1c_555320.asm`
  - USB/HID transport wrapper and dispatcher.
  - Enumerate/connect/read/write flow via `mcHID` thunks.
- `disasm_packet_builder_554590_554980.asm`
  - Packet construction for command IDs (`0x03..0x06`, `0x40..0x42`).
- `disasm_response_parser_553910_554520.asm`
  - Incoming report parser and state-application logic.
- `disasm_cmd5_response_parse_553e70_553ffc.asm`
  - Command `0x05` response handling. Includes routing byte import.
- `disasm_cmd6_response_and_fwupdate_dispatch_553ff0_554440.asm`
  - Command `0x06` response handling and firmware-update dispatch (`0x40..0x42`).
- `disasm_cmd3_txlogic_554c00_554ed0.asm`
  - Command `0x03` transmit-side logic and helper routines.
- `disasm_routing_combo_init_550620_550b00.asm`
  - UI combo initialization for channel routing options.
- `disasm_routing_combo_apply_551980_551c00.asm`
  - UI callback that copies combo indices into route state and emits `cmd 0x05`.
- `disasm_routing_mode_logic_556fcb_557360.asm`
  - Mode-dependent routing control logic.
- `disasm_routing_refresh_5574a4_557780.asm`
  - Large routing/UI refresh routine.
- `disasm_routing_strings_551700_551820.asm`
  - Embedded shortstrings (`Left`, `Right`, `L+R/Mid`, `L-R/Side`).

## Metadata / support

- `objdump_x_HFD_v2.12.exe.txt`
- `objdump_p_HFD_v2.12.exe.txt`
- `objdump_x_mcHID.dll.txt`
- `rabin2_imports_HFD_v2.12.txt`
- `rabin2_imports_mcHID.txt`
- `r2_xrefs_mcHID_calls.txt`
- `strings_HFD_v2.12.txt`
- `strings_focus_HFD_v2.12.txt`
- `callsites_to_554f50_from_55xxxx.txt`
- `callsites_command_dl_constants_55xxxx.txt`
