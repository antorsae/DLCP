"""V3.0 source-rewrite symbol parser and assembly helpers."""

from __future__ import annotations

from functools import lru_cache
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict

from dlcp_fw.paths import (
    V30_MAIN_ASM,
    V30_MAIN_HEX,
    V31_MAIN_ASM_CANONICAL,
    V31_MAIN_HEX_CANONICAL,
    V32_MAIN_ASM,
    V32_MAIN_HEX,
)

from .hexio import parse_intel_hex


def parse_gpasm_symbols(lst_path: Path) -> Dict[str, int]:
    """Extract label→address mapping from a gpasm listing file.

    Parses the SYMBOL TABLE section and returns only ADDRESS-type entries
    (code/data labels), ignoring CONSTANT entries (SFR names, bit fields).
    """
    text = lst_path.read_text(encoding="utf-8", errors="replace")
    # Find start of symbol table
    idx = text.find("SYMBOL TABLE")
    if idx < 0:
        raise ValueError(f"No SYMBOL TABLE found in {lst_path}")
    table_text = text[idx:]

    # ADDRESS entries: label name, ADDRESS, hex value
    pattern = re.compile(
        r"^(\w+)\s+ADDRESS\s+([0-9A-Fa-f]+)\s+\d+",
        re.MULTILINE,
    )
    symbols: Dict[str, int] = {}
    for m in pattern.finditer(table_text):
        name = m.group(1)
        addr = int(m.group(2), 16)
        symbols[name] = addr
    return symbols


@lru_cache(maxsize=None)
def load_gpasm_symbols_for_hex(main_hex: Path) -> Dict[str, int] | None:
    """Load gpasm symbols for *main_hex*.

    Resolution order:
    1. sibling ``.lst`` beside *main_hex*
    2. source-side canonical ``.lst`` for known V3.x release HEXes

    Returns ``None`` when no usable listing is found. This lets stock and
    binary-patched images keep their fixed-address fallbacks, while canonical
    source-assembled V3.x releases can still resolve labels even though the
    release builder does not retain a sibling ``.lst`` in the releases dir.
    """
    release_hex = Path(main_hex).resolve()
    lst_candidates = [Path(main_hex).with_suffix(".lst")]

    canonical_source_lsts = {
        V30_MAIN_HEX.resolve(): V30_MAIN_ASM.with_suffix(".lst"),
        V31_MAIN_HEX_CANONICAL.resolve(): V31_MAIN_ASM_CANONICAL.with_suffix(".lst"),
        V32_MAIN_HEX.resolve(): V32_MAIN_ASM.with_suffix(".lst"),
    }
    fallback_lst = canonical_source_lsts.get(release_hex)
    if fallback_lst is not None and fallback_lst not in lst_candidates:
        lst_candidates.append(fallback_lst)

    for lst_path in lst_candidates:
        if not lst_path.exists():
            continue
        try:
            symbols = parse_gpasm_symbols(lst_path)
        except ValueError:
            continue
        if symbols:
            return symbols
    return None


@lru_cache(maxsize=None)
def _load_code_window(
    main_hex: Path,
    start_addr: int,
    end_addr: int,
) -> bytes:
    mem = parse_intel_hex(Path(main_hex))
    return bytes(mem.get(addr, 0xFF) for addr in range(start_addr, end_addr))


def find_code_signature(
    main_hex: Path,
    signature: bytes,
    *,
    start_addr: int = 0x1000,
    end_addr: int = 0x5600,
) -> int | None:
    """Return the address of *signature* within the code window, if found."""
    code = _load_code_window(Path(main_hex), start_addr, end_addr)
    idx = code.find(signature)
    if idx < 0:
        return None
    return start_addr + idx


def assemble_v30(
    asm_path: Path,
    output_hex: Path,
    *,
    output_lst: Path | None = None,
    gpasm: str = "gpasm",
) -> Path:
    """Assemble a V3.0 .asm source with gpasm.

    Returns the path to the output hex.  gpasm auto-generates a ``.lst``
    file next to the source; if *output_lst* is given the listing is
    copied there.
    """
    cmd = [gpasm, "-p18f2455", "-o", str(output_hex), str(asm_path)]
    cp = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(asm_path.parent),
    )
    errors = [
        line for line in (cp.stdout + cp.stderr).splitlines()
        if "Error" in line and "Warning" not in line
    ]
    if errors or cp.returncode != 0:
        raise RuntimeError(
            f"gpasm failed ({cp.returncode}):\n" + "\n".join(errors[:20])
        )
    # gpasm may place the listing beside the source file or beside the
    # requested output basename, depending on invocation details.
    auto_lsts = (
        asm_path.with_suffix(".lst"),
        output_hex.with_suffix(".lst"),
    )
    if output_lst is not None:
        import shutil

        existing_lsts = [path for path in auto_lsts if path.exists()]
        if not existing_lsts:
            raise RuntimeError(
                "gpasm did not produce listing at any expected location: "
                + ", ".join(str(path) for path in auto_lsts)
            )
        freshest_lst = max(
            existing_lsts,
            key=lambda path: (
                path.stat().st_mtime_ns,
                1 if path == output_hex.with_suffix(".lst") else 0,
            ),
        )
        if freshest_lst.resolve() != output_lst.resolve():
            shutil.copy2(freshest_lst, output_lst)
    return output_hex


def build_shifted_asm(source_asm: Path, output_asm: Path) -> Path:
    """Create a shifted copy of the V3.0 source for relocation testing.

    Inserts 0x111 NOP words (0x222 bytes) of padding after the ISR dispatch
    call, and converts string_desc_ptr_table data to label-relative ``db``
    values so embedded pointers track shifted addresses.

    The RAM include file (``dlcp_main_ram.inc``) is symlinked into the
    output directory so gpasm can resolve it.
    """
    text = source_asm.read_text(encoding="utf-8")
    lines = text.split("\n")
    out: list[str] = []
    padding_inserted = False
    ptr_table_converted = False

    for line in lines:
        stripped = line.strip()

        # Insert NOP padding after the ISR dispatch call
        if not padding_inserted and stripped.startswith("call") and "main_isr_dispatch" in stripped:
            out.append(line)
            out.append("")
            out.append("; --- Relocation safety padding (shift test) ---")
            out.append("    fill    0x0000, 0x222    ; 0x222 bytes = 0x111 NOP words")
            out.append("")
            padding_inserted = True
            continue

        # Fix erased flash fill: the stock formula divides by 2 which can yield
        # an odd byte count after padding.  Use the raw byte gap instead.
        if "(0x5600 - $) / 2" in stripped:
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}fill 0xFFFF, (0x5600 - $)")
            continue

        # Convert string descriptor pointer table from hardcoded dw to label-relative db
        if not ptr_table_converted and "0xA646" in stripped and "0x9A72" in stripped:
            indent = line[: len(line) - len(line.lstrip())]
            out.append(
                f"{indent}db  0x46, LOW(usb_string_desc_0), "
                f"LOW(usb_string_desc_1), LOW(usb_string_desc_2)"
            )
            ptr_table_converted = True
            continue

        out.append(line)

    if not padding_inserted:
        raise RuntimeError("Could not find ISR dispatch call for padding insertion")
    if not ptr_table_converted:
        raise RuntimeError("Could not find string_desc_ptr_table data for conversion")

    output_asm.write_text("\n".join(out), encoding="utf-8")

    # Symlink the RAM inc file so gpasm finds it
    ram_inc = source_asm.parent / "dlcp_main_ram.inc"
    target_inc = output_asm.parent / "dlcp_main_ram.inc"
    if ram_inc.exists() and not target_inc.exists():
        target_inc.symlink_to(ram_inc.resolve())

    return output_asm
