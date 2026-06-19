# Coding Style

This file is authoritative for repository coding style. It starts with MAIN PIC18
assembly because that is where naming drift is currently highest; extend it as
CONTROL, Python, Rust, or tool-specific conventions are made explicit.

Where this document is silent, follow the surrounding file's established style.
Do not reformat or rename unrelated code while making a functional change.

## MAIN PIC18 Assembly

Scope: `src/dlcp_fw/asm/dlcp_main_v34.asm`,
`src/dlcp_fw/asm/dlcp_main_v35.asm`, and shared MAIN include files such as
`src/dlcp_fw/asm/dlcp_main_ram.inc`.

Style conventions:

- PIC SFR/register symbols from `p18f2455.inc` stay uppercase, for example
  `INTCON`, `SSPCON2`, `TXSTA`, `CREN`, and `WREG`.
- Instructions are lower-case, for example `movlw`, `movwf`, `btfsc`, `bra`,
  `rcall`, and `return`.
- Assembler directives are uppercase where already established, especially
  `EQU`, `MACRO`, and `ENDM`. Preserve local directive style for existing
  header/config blocks.
- Runtime labels and RAM aliases use `lower_snake_case`.
- Protocol constants, device register constants, and bit masks use
  `UPPER_SNAKE_CASE`.
- Auto-generated `stock_*`, `ram_0x*`, `_op`, and `_phys` aliases are
  address-stable. Do not rename them for cosmetics only.
- Helper labels that name a WREG input or result use `_w`, not `_W`, unless the
  token is the PIC symbol `WREG`.
- Raw source line numbers are avoided in comments. Use labels, document/test
  IDs, bug IDs, or stable hardware/protocol names instead.

## Comments

- Comments must describe current behavior. When a bug has been fixed, update or
  remove comments that still describe the old failure mode.
- Prefer contract comments near ownership boundaries: interrupt/shared RAM,
  UART/chain ownership, flash/EEPROM staging, I2C recovery, wake/standby gates,
  and builder-owned identity fields.
- Avoid comments that depend on physical line numbers or temporary listings.
  Listing addresses are acceptable only when the address itself is the contract.

## Renames

- Rename runtime labels only when the new name improves a maintained contract or
  removes real ambiguity. Cosmetic-only label churn makes listing review harder.
- Any label/RAM alias rename must update all call sites, tests, docs, and
  generated ledgers that rely on the old name.
- Preserve generated alias spelling unless regenerating the alias source of
  truth in the same change.

## Verification

- For style/comment-only MAIN source edits, assemble to temporary outputs rather
  than publishing a canonical release.
- `scripts/build_v34_release.py` and sibling release builders update revision
  metadata. Do not use them merely to check a style-only edit unless the intent
  is to publish a new canonical release.
- If code generation is intended to remain unchanged, compare the temporary HEX
  against the relevant baseline and report the result.
- If code generation changes, run the focused tests for the touched behavior and
  the applicable release gates from `AGENTS.md`.
