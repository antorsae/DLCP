"""Build paired V3.1 diagnostic variants with and without padding NOPs.

The canonical V3.1 source in ``dlcp_main_v31.asm`` is the current
``WITHOUT_NOPS`` diagnosis baseline. This builder emits two explicit
non-canonical artifacts from that same logic base:

- ``WITH_NOPS``: restores the inert padding NOP blocks removed during
  the cleanup pass
- ``WITHOUT_NOPS``: exact copy of the current canonical source

Both variants produce their own ``.hex`` and matching ``.lst`` outputs so
the label-driven V3.1 sim/test harness can target either one via
``DLCP_FW_V31_MAIN_ASM`` / ``DLCP_FW_V31_MAIN_HEX``.
"""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.paths import FIRMWARE_PATCHED_DIR, V31_MAIN_ASM
from dlcp_fw.sim.v30_symbols import assemble_v30

_WITHOUT_NOPS_ASM = "dlcp_main_v31_without_nops.asm"
_WITH_NOPS_ASM = "dlcp_main_v31_with_nops.asm"
_WITHOUT_NOPS_HEX = "DLCP_Firmware_V3.1_WITHOUT_NOPS.hex"
_WITH_NOPS_HEX = "DLCP_Firmware_V3.1_WITH_NOPS.hex"

_WITH_NOPS_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        """    movlb       0x0
    bsf         ram_0x0BD, 0, BANKED
    call        main_timer_service_48a6, 0x0
""",
        """    movlb       0x0
    nop
    bsf         ram_0x0BD, 0, BANKED
    call        main_timer_service_48a6, 0x0
""",
    ),
    (
        """flow_main_uart_service_1be6_1d6c:
    bsf         event_flags, 3, BANKED
    ; V3.1 Fix B': do NOT copy computed->logical here (deferred to volume_dsp_write)
    bra         flow_main_uart_service_1be6_1e6c
""",
        """flow_main_uart_service_1be6_1d6c:
    bsf         event_flags, 3, BANKED
    ; V3.1 Fix B': do NOT copy computed->logical here (deferred to volume_dsp_write)
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    bra         flow_main_uart_service_1be6_1e6c
""",
    ),
)


def _write_variant(asm_name: str, text: str) -> Path:
    asm_path = V31_MAIN_ASM.with_name(asm_name)
    asm_path.write_text(text, encoding="utf-8")
    return asm_path


def _build_variant(asm_path: Path, hex_name: str) -> Path:
    hex_path = FIRMWARE_PATCHED_DIR / hex_name
    lst_path = hex_path.with_suffix(".lst")
    assemble_v30(asm_path, hex_path, output_lst=lst_path)
    return hex_path


def _render_with_nops(source_text: str) -> str:
    text = source_text
    for before, after in _WITH_NOPS_REPLACEMENTS:
        if before not in text:
            raise RuntimeError("V3.1 source drifted; NOP variant anchor not found")
        text = text.replace(before, after, 1)
    return text


def build_variants() -> tuple[Path, Path, Path, Path]:
    source_text = V31_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    without_nops_asm = _write_variant(_WITHOUT_NOPS_ASM, source_text)
    with_nops_asm = _write_variant(_WITH_NOPS_ASM, _render_with_nops(source_text))

    without_nops_hex = _build_variant(without_nops_asm, _WITHOUT_NOPS_HEX)
    with_nops_hex = _build_variant(with_nops_asm, _WITH_NOPS_HEX)

    return without_nops_asm, without_nops_hex, with_nops_asm, with_nops_hex


def main() -> int:
    without_nops_asm, without_nops_hex, with_nops_asm, with_nops_hex = build_variants()
    print(without_nops_asm)
    print(without_nops_hex)
    print(with_nops_asm)
    print(with_nops_hex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
