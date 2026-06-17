#!/usr/bin/env python3
"""Build the canonical V3.4 MAIN release and bump its 16-bit revision."""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from pathlib import Path

from dlcp_fw.analysis.ram_bank_safety import assert_targets_safe
from dlcp_fw.paths import V34_MAIN_ASM, V34_MAIN_HEX
from dlcp_fw.sim.v30_symbols import assemble_v30


_EEPROM_REV_LO_RE = re.compile(
    r"(^\s*db\s+0x03,\s*0x04,\s*0x)([0-9A-Fa-f]{2})(\b.*$)",
    re.MULTILINE,
)
_RUNTIME_REV_LO_RE = re.compile(
    r"(^\s*movlw\s+0x)([0-9A-Fa-f]{2})(\s*;\s*V3\.4_RUNTIME_EEPROM_REV(?:_LO)?\b.*$)",
    re.MULTILINE,
)
_IDENTITY_REV_LO_HI_RE = re.compile(
    r"(^\s*movlw\s+0x)([0-9A-Fa-f]{2})(\s*;\s*V3\.4_IDENTITY_REV_LO_HI\b.*$)",
    re.MULTILINE,
)
_IDENTITY_REV_LO_LO_RE = re.compile(
    r"(^\s*movlw\s+0x)([0-9A-Fa-f]{2})(\s*;\s*V3\.4_IDENTITY_REV_LO_LO\b.*$)",
    re.MULTILINE,
)
_IDENTITY_REV_HI_HI_RE = re.compile(
    r"(^\s*movlw\s+0x)([0-9A-Fa-f]{2})(\s*;\s*V3\.4_IDENTITY_REV_HI_HI\b.*$)",
    re.MULTILINE,
)
_IDENTITY_REV_HI_LO_RE = re.compile(
    r"(^\s*movlw\s+0x)([0-9A-Fa-f]{2})(\s*;\s*V3\.4_IDENTITY_REV_HI_LO\b.*$)",
    re.MULTILINE,
)


def read_v34_release_revision(asm_path: Path = V34_MAIN_ASM) -> int:
    text = asm_path.read_text(encoding="utf-8")
    try:
        return _read_identity_revision(text)
    except RuntimeError as exc:
        raise RuntimeError(f"{exc} in {asm_path}") from exc


def _read_identity_revision(text: str) -> int:
    nibbles = []
    for regex, label in (
        (_IDENTITY_REV_HI_HI_RE, "V3.4 identity revision high-byte high nibble"),
        (_IDENTITY_REV_HI_LO_RE, "V3.4 identity revision high-byte low nibble"),
        (_IDENTITY_REV_LO_HI_RE, "V3.4 identity revision low-byte high nibble"),
        (_IDENTITY_REV_LO_LO_RE, "V3.4 identity revision low-byte low nibble"),
    ):
        match = regex.search(text)
        if match is None:
            raise RuntimeError(f"{label} literal not found")
        value = int(match.group(2), 16)
        if value > 0x0F:
            raise RuntimeError(f"{label} literal is not a nibble: 0x{value:02X}")
        nibbles.append(value)
    return (nibbles[0] << 12) | (nibbles[1] << 8) | (nibbles[2] << 4) | nibbles[3]


def _rewrite_match(text: str, regex: re.Pattern[str], value: int, label: str) -> str:
    match = regex.search(text)
    if match is None:
        raise RuntimeError(f"{label} literal not found")
    return text[: match.start(2)] + f"{value:02X}" + text[match.end(2) :]


def _rewrite_v34_release_revision(text: str) -> tuple[str, int, int]:
    org_pos = text.find("org 0xF00000")
    if org_pos < 0:
        raise RuntimeError("EEPROM data block not found")
    match = _EEPROM_REV_LO_RE.search(text, pos=org_pos)
    if match is None:
        raise RuntimeError("V3.4 EEPROM version tuple not found")
    old_rev = _read_identity_revision(text)
    new_rev = (old_rev + 1) & 0xFFFF
    new_lo = new_rev & 0xFF
    updated = text[: match.start(2)] + f"{new_lo:02X}" + text[match.end(2) :]
    updated = _rewrite_match(
        updated,
        _RUNTIME_REV_LO_RE,
        new_lo,
        "V3.4 runtime EEPROM revision low byte",
    )
    for regex, value in (
        (_IDENTITY_REV_LO_HI_RE, (new_rev >> 4) & 0x0F),
        (_IDENTITY_REV_LO_LO_RE, new_rev & 0x0F),
        (_IDENTITY_REV_HI_HI_RE, (new_rev >> 12) & 0x0F),
        (_IDENTITY_REV_HI_LO_RE, (new_rev >> 8) & 0x0F),
    ):
        updated = _rewrite_match(updated, regex, value, "V3.4 identity revision nibble")
    return updated, old_rev, new_rev


def bump_v34_release_revision(asm_path: Path = V34_MAIN_ASM) -> tuple[int, int]:
    text = asm_path.read_text(encoding="utf-8")
    try:
        updated, old_rev, new_rev = _rewrite_v34_release_revision(text)
    except RuntimeError as exc:
        raise RuntimeError(f"{exc} in {asm_path}") from exc
    asm_path.write_text(updated, encoding="utf-8")
    return old_rev, new_rev


def build_v34_release(
    *,
    asm_path: Path = V34_MAIN_ASM,
    output_hex: Path = V34_MAIN_HEX,
    gpasm: str = "gpasm",
) -> tuple[int, int, Path]:
    original_text = asm_path.read_text(encoding="utf-8")
    try:
        updated_text, old_rev, new_rev = _rewrite_v34_release_revision(original_text)
    except RuntimeError as exc:
        raise RuntimeError(f"{exc} in {asm_path}") from exc

    source_lst = asm_path.with_suffix(".lst")
    # The V3.x symbol-resolution path in
    # `dlcp_fw.sim.v30_symbols.load_gpasm_symbols_for_hex` falls back to
    # this source-side listing when the release HEX has no sibling `.lst`,
    # so a partial listing from a failed gpasm run would silently poison
    # address lookups for `V34_MAIN_HEX` unless we roll it back.
    original_lst: bytes | None = None
    asm_modified = False
    output_hex.parent.mkdir(parents=True, exist_ok=True)
    tmpdir_obj = tempfile.TemporaryDirectory(prefix="v34_release_", dir=str(output_hex.parent))
    tmpdir = Path(tmpdir_obj.name)
    temp_hex = tmpdir / output_hex.name
    build_ok = False
    try:
        if source_lst.exists():
            original_lst = source_lst.read_bytes()
        asm_path.write_text(updated_text, encoding="utf-8")
        asm_modified = True
        assemble_v30(
            asm_path,
            temp_hex,
            output_lst=source_lst,
            gpasm=gpasm,
        )
        assert_targets_safe(["main-v34"])
        shutil.copy2(temp_hex, output_hex)
        build_ok = True
    finally:
        if not build_ok:
            # Rollback.  If a rollback step itself raises, Python chains
            # it to the original exception via `__context__`, so the
            # operator sees both rather than silently losing information.
            if asm_modified:
                asm_path.write_text(original_text, encoding="utf-8")
            if original_lst is None:
                if source_lst.exists():
                    source_lst.unlink()
            else:
                source_lst.write_bytes(original_lst)
        tmpdir_obj.cleanup()
    release_lst = output_hex.with_suffix(".lst")
    if release_lst.exists() and release_lst.resolve() != source_lst.resolve():
        release_lst.unlink()
    return old_rev, new_rev, output_hex


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Bump the canonical V3.4 16-bit release revision and assemble "
            "firmware/patched/releases/DLCP_Firmware_V3.4.hex"
        ),
    )
    ap.add_argument("--gpasm", default="gpasm", help="gpasm executable (default: gpasm)")
    args = ap.parse_args(argv)

    old_rev, new_rev, output_hex = build_v34_release(gpasm=args.gpasm)
    print(
        "built canonical V3.4 release: "
        f"{output_hex} (release rev 0x{old_rev:04X} -> 0x{new_rev:04X})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
