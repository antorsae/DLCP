# HFD v2.12 Reverse Engineering

This directory contains resources and notes related to the reverse engineering and subsequent disassembly of the `Hypex Filter Design V2.12.exe` Windows binary.

## Scope

The primary objective is to enable an additional routing option `R-L/Diff` mapping to `ItemIndex = 4` in the 6 channel source setup comboboxes.

## Execution

The analysis utilized `pefile` and `capstone` (x86, 32-bit). Key discoveries include:
- The binary is a Borland Delphi (VCL) executable (`ImageBase: 0x00400000`).
- Interaction with the DLCP Main Unit goes through `mcHID.dll` (`Connect`, `Write`, `Read`, `Disconnect`).
- Front-panel Channel Source mappings (`Left`, `Right`, `L+R/Mid`, `L-R/Side`) correspond directly to `ItemIndex` variables. These are harvested and bundled into a global state structure, then transmitted via **USB Command `0x05`** (`dl = 0x05` -> `call 0x554f50`).
- The 6 ComboBox instances are populated with 4 static string literals starting at Virtual Address `0x550658` (`TStrings.Add`).

## Patch Strategy
To support `R-L` (Index 4), the binary requires the injection of a new string and patching of 6 unrolled VCL initialization blocks to detour to a Code Cave, where the 5th `TStrings.Add` instruction will be executed. See `docs/analysis/HFD_v2.12-gemini.md` for full implementation strategy.
