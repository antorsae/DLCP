#!/usr/bin/env python3
"""Build the canonical V3.2 MAIN release and bump its EEPROM revision."""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from pathlib import Path

from dlcp_fw.paths import V32_MAIN_ASM, V32_MAIN_HEX
from dlcp_fw.sim.v30_symbols import assemble_v30


_EEPROM_REV_RE = re.compile(
    r"(^\s*db\s+0x03,\s*0x02,\s*0x)([0-9A-Fa-f]{2})(\b.*$)",
    re.MULTILINE,
)


def read_v32_release_revision(asm_path: Path = V32_MAIN_ASM) -> int:
    text = asm_path.read_text(encoding="utf-8")
    org_pos = text.find("org 0xF00000")
    if org_pos < 0:
        raise RuntimeError(f"EEPROM data block not found in {asm_path}")
    match = _EEPROM_REV_RE.search(text, pos=org_pos)
    if match is None:
        raise RuntimeError(f"V3.2 EEPROM version tuple not found in {asm_path}")
    return int(match.group(2), 16)


def _rewrite_v32_release_revision(text: str) -> tuple[str, int, int]:
    org_pos = text.find("org 0xF00000")
    if org_pos < 0:
        raise RuntimeError("EEPROM data block not found")
    match = _EEPROM_REV_RE.search(text, pos=org_pos)
    if match is None:
        raise RuntimeError("V3.2 EEPROM version tuple not found")
    old_rev = int(match.group(2), 16)
    if old_rev >= 0xFF:
        raise RuntimeError(
            f"V3.2 EEPROM revision already at 0x{old_rev:02X}; cannot bump further"
        )
    new_rev = old_rev + 1
    updated = text[: match.start(2)] + f"{new_rev:02X}" + text[match.end(2) :]
    return updated, old_rev, new_rev


def bump_v32_release_revision(asm_path: Path = V32_MAIN_ASM) -> tuple[int, int]:
    text = asm_path.read_text(encoding="utf-8")
    try:
        updated, old_rev, new_rev = _rewrite_v32_release_revision(text)
    except RuntimeError as exc:
        raise RuntimeError(f"{exc} in {asm_path}") from exc
    asm_path.write_text(updated, encoding="utf-8")
    return old_rev, new_rev


def build_v32_release(
    *,
    asm_path: Path = V32_MAIN_ASM,
    output_hex: Path = V32_MAIN_HEX,
    gpasm: str = "gpasm",
) -> tuple[int, int, Path]:
    original_text = asm_path.read_text(encoding="utf-8")
    try:
        updated_text, old_rev, new_rev = _rewrite_v32_release_revision(original_text)
    except RuntimeError as exc:
        raise RuntimeError(f"{exc} in {asm_path}") from exc

    asm_path.write_text(updated_text, encoding="utf-8")
    source_lst = asm_path.with_suffix(".lst")
    # Capture the pre-build `.lst` state so we can restore it on failure.
    # The V3.x symbol-resolution path in
    # `dlcp_fw.sim.v30_symbols.load_gpasm_symbols_for_hex` falls back to
    # this source-side listing when the release HEX has no sibling `.lst`,
    # so a partial listing from a failed gpasm run would silently poison
    # address lookups for `V32_MAIN_HEX` unless we roll it back.
    original_lst = source_lst.read_bytes() if source_lst.exists() else None
    output_hex.parent.mkdir(parents=True, exist_ok=True)
    tmpdir_obj = tempfile.TemporaryDirectory(prefix="v32_release_", dir=str(output_hex.parent))
    tmpdir = Path(tmpdir_obj.name)
    temp_hex = tmpdir / output_hex.name
    try:
        assemble_v30(
            asm_path,
            temp_hex,
            output_lst=source_lst,
            gpasm=gpasm,
        )
        shutil.copy2(temp_hex, output_hex)
    except Exception:
        asm_path.write_text(original_text, encoding="utf-8")
        if original_lst is None:
            if source_lst.exists():
                source_lst.unlink()
        else:
            source_lst.write_bytes(original_lst)
        raise
    finally:
        tmpdir_obj.cleanup()
    release_lst = output_hex.with_suffix(".lst")
    if release_lst.exists() and release_lst.resolve() != source_lst.resolve():
        release_lst.unlink()
    return old_rev, new_rev, output_hex


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Bump the canonical V3.2 EEPROM revision and assemble "
            "firmware/patched/releases/DLCP_Firmware_V3.2.hex"
        ),
    )
    ap.add_argument("--gpasm", default="gpasm", help="gpasm executable (default: gpasm)")
    args = ap.parse_args(argv)

    old_rev, new_rev, output_hex = build_v32_release(gpasm=args.gpasm)
    print(
        "built canonical V3.2 release: "
        f"{output_hex} (EEPROM rev 0x{old_rev:02X} -> 0x{new_rev:02X})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
