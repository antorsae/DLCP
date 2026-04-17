"""V1.7 CONTROL source-rewrite symbol parser and shift builder.

CONTROL-side analog of :mod:`dlcp_fw.sim.v30_symbols` for MAIN.  The
gpasm symbol-table parser is reused from the MAIN helpers; this file
adds the CONTROL-specific shift-test assembler helper and a
``parse_v17_symbols`` alias whose signature matches the spec.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List

from .v30_symbols import parse_gpasm_symbols

# Re-export under the spec-mandated name.
parse_v17_symbols = parse_gpasm_symbols


_VECTOR_BLOCK_END_LABEL = "control_core_service_004C"
_BOOTLOADER_LABEL = "bootloader_entry"
_RAM_INC_NAME = "dlcp_control_ram.inc"
_SHIFT_WORDS = 0x111  # 0x111 NOP words = 0x222 bytes (matches spec §A4)
_SHIFT_BYTES = _SHIFT_WORDS * 2


def assemble_v17(
    asm_path: Path,
    output_hex: Path,
    *,
    output_lst: Path | None = None,
    gpasm: str = "gpasm",
) -> Path:
    """Assemble a V1.7 .asm source with gpasm (PIC18F25K20)."""
    cmd = [gpasm, "-p18f25k20", "-o", str(output_hex), str(asm_path)]
    cp = subprocess.run(
        cmd, capture_output=True, text=True, check=False, cwd=str(asm_path.parent)
    )
    # gpasm for PIC18F25K20 emits benign warnings about CONFIG/IDLOCS
    # addresses exceeding the code range when we dump raw ``db`` bytes
    # at 0x200000/0x300000.  Only real errors should fail the build.
    errors = [
        line for line in (cp.stdout + cp.stderr).splitlines()
        if "Error" in line and "Warning" not in line
    ]
    if errors or cp.returncode != 0:
        raise RuntimeError(
            f"gpasm failed ({cp.returncode}):\n" + "\n".join(errors[:20])
        )
    auto_lsts = (
        asm_path.with_suffix(".lst"),
        output_hex.with_suffix(".lst"),
    )
    if output_lst is not None:
        import shutil
        existing = [path for path in auto_lsts if path.exists()]
        if not existing:
            raise RuntimeError(
                "gpasm did not produce a listing at any expected location: "
                + ", ".join(str(p) for p in auto_lsts)
            )
        freshest = max(existing, key=lambda p: p.stat().st_mtime_ns)
        if freshest.resolve() != output_lst.resolve():
            shutil.copy2(freshest, output_lst)
    return output_hex


def build_shifted_asm(source_asm: Path, output_asm: Path) -> Path:
    """Create the V1.7 shift-test source from the canonical commented source.

    Transformations (spec §A4):

    1.  Insert 0x111 NOP words (= 0x222 bytes) of padding immediately before
        the first application-code label after the vector block
        (``control_core_service_004C`` at stock 0x004C).
    2.  Pin the bootloader at 0x7800 with an explicit ``org 0x7800``
        directive before ``bootloader_entry:`` and strip the erased-flash
        ``dw 0xffff`` fill that preceded the bootloader, because the
        shift pushes the fill past 0x7800 and would collide.

    The shifted source assembles with gpasm and produces a hex image whose
    vector block (0x0000–0x004B) is byte-identical to stock V1.6b, whose
    application code starts at 0x026E (stock 0x004C + 0x222), and whose
    bootloader (0x7800–0x7FFF) is byte-identical to stock.

    The RAM include file (``dlcp_control_ram.inc``) is symlinked into the
    output directory so gpasm can resolve it.
    """
    text = source_asm.read_text(encoding="utf-8")
    lines = text.split("\n")
    out: List[str] = []
    padding_inserted = False
    bootloader_pinned = False

    # Strip the leading ``dw 0xffff`` run immediately above bootloader_entry.
    # Walk from the bottom to find the bootloader and the last preceding
    # non-``dw 0xffff`` line, then blank out those dw lines.
    bootloader_idx = None
    for i, line in enumerate(lines):
        if line.startswith(f"{_BOOTLOADER_LABEL}:"):
            bootloader_idx = i
            break
    if bootloader_idx is None:
        raise RuntimeError(
            f"Could not find '{_BOOTLOADER_LABEL}:' in {source_asm}"
        )

    # Walk upward from bootloader_idx until we see a non-blank, non-``dw 0xffff``
    # line.  Mark the ``dw 0xffff`` lines for removal and record the insertion
    # point for ``org 0x7800``.
    drop_start = bootloader_idx
    i = bootloader_idx - 1
    while i >= 0:
        s = lines[i].strip()
        if s == "" or s == "dw      0xffff" or s == "dw 0xffff":
            drop_start = i
            i -= 1
            continue
        break
    dropped_range = range(drop_start, bootloader_idx)

    for idx, line in enumerate(lines):
        if idx in dropped_range:
            # Skip the pre-bootloader dw 0xffff fill; replaced by org below.
            continue
        if not bootloader_pinned and idx == bootloader_idx:
            out.append("")
            out.append("; --- Bootloader pinned at 0x7800 ---")
            out.append("        org     0x7800")
            out.append("")
            out.append(line)
            bootloader_pinned = True
            continue

        if not padding_inserted and line.startswith(f"{_VECTOR_BLOCK_END_LABEL}:"):
            out.append("")
            out.append("; --- Relocation safety padding (shift test) ---")
            out.append(
                f"        fill    0x0000, 0x{_SHIFT_BYTES:X}"
                f"    ; 0x{_SHIFT_WORDS:X} NOP words = 0x{_SHIFT_BYTES:X} bytes"
            )
            out.append("")
            padding_inserted = True

        out.append(line)

    if not padding_inserted:
        raise RuntimeError(
            f"Could not find '{_VECTOR_BLOCK_END_LABEL}:' to anchor padding"
        )
    if not bootloader_pinned:
        raise RuntimeError("Could not pin bootloader at 0x7800")

    output_asm.write_text("\n".join(out), encoding="utf-8")

    # Symlink the RAM include so gpasm can resolve it.
    ram_inc = source_asm.parent / _RAM_INC_NAME
    target_inc = output_asm.parent / _RAM_INC_NAME
    if ram_inc.exists() and not target_inc.exists():
        target_inc.symlink_to(ram_inc.resolve())

    return output_asm


__all__ = [
    "assemble_v17",
    "build_shifted_asm",
    "parse_v17_symbols",
]
