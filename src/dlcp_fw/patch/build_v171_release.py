#!/usr/bin/env python3
"""Build the canonical V1.71 CONTROL release and bump its release revision."""

from __future__ import annotations

import argparse
from datetime import date
import re
import shutil
import tempfile
from pathlib import Path

from dlcp_fw.paths import V171_CONTROL_ASM, V171_CONTROL_HEX
from dlcp_fw.sim.v17_symbols import assemble_v17


_RELEASE_REV_RE = re.compile(
    r"(^\s*db\s+0x01,\s*0x07,\s*0x31,\s*0x)([0-9A-Fa-f]{2})(\b.*$)",
    re.MULTILINE,
)
_BUILD_DATE_RE = re.compile(
    r"(^\s*db\s+0x)([0-9A-Fa-f]{2})(,\s*0x)([0-9A-Fa-f]{2})"
    r"(,\s*0x)([0-9A-Fa-f]{2})(,\s*0x)([0-9A-Fa-f]{2})"
    r"(\s*;\s*build date\s+)([0-9]{8})(.*$)",
    re.MULTILINE,
)
_BANNER_ROW2_RE = re.compile(
    r"(^\s*db\s+)(0x[0-9A-Fa-f]{2}(?:,\s*0x[0-9A-Fa-f]{2})*)"
    r"(\s*;\s*\")([^\"]+)(\".*$)",
    re.MULTILINE,
)


def read_v171_release_revision(asm_path: Path = V171_CONTROL_ASM) -> int:
    text = asm_path.read_text(encoding="utf-8")
    marker = text.find("control_release_metadata:")
    if marker < 0:
        raise RuntimeError(f"control_release_metadata block not found in {asm_path}")
    match = _RELEASE_REV_RE.search(text, pos=marker)
    if match is None:
        raise RuntimeError(f"V1.71 release-revision tuple not found in {asm_path}")
    return int(match.group(2), 16)


def _rewrite_v171_release_revision(text: str) -> tuple[str, int, int]:
    marker = text.find("control_release_metadata:")
    if marker < 0:
        raise RuntimeError("control_release_metadata block not found")
    match = _RELEASE_REV_RE.search(text, pos=marker)
    if match is None:
        raise RuntimeError("V1.71 release-revision tuple not found")
    old_rev = int(match.group(2), 16)
    if old_rev >= 0xFF:
        raise RuntimeError(
            f"V1.71 release revision already at 0x{old_rev:02X}; cannot bump further"
        )
    new_rev = old_rev + 1
    updated = text[: match.start(2)] + f"{new_rev:02X}" + text[match.end(2) :]
    return updated, old_rev, new_rev


def _validate_build_date(build_date: str) -> str:
    value = build_date.strip()
    if not re.fullmatch(r"\d{8}", value):
        raise RuntimeError(f"build date must be YYYYMMDD, got {build_date!r}")
    try:
        date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
    except ValueError as exc:
        raise RuntimeError(f"invalid build date {build_date!r}") from exc
    return value


def _build_date_bcd_bytes(build_date: str) -> tuple[int, int, int, int]:
    values = [int(build_date[i : i + 2], 16) for i in range(0, 8, 2)]
    return values[0], values[1], values[2], values[3]


def _db_bytes(values: list[int]) -> str:
    return ", ".join(f"0x{value:02X}" for value in values)


def _rewrite_v171_build_date(text: str, build_date: str) -> str:
    marker = text.find("control_release_metadata:")
    if marker < 0:
        raise RuntimeError("control_release_metadata block not found")
    match = _BUILD_DATE_RE.search(text, pos=marker)
    if match is None:
        raise RuntimeError("V1.71 build-date metadata line not found")
    b0, b1, b2, b3 = _build_date_bcd_bytes(build_date)
    return (
        text[: match.start(2)]
        + f"{b0:02X}"
        + text[match.end(2) : match.start(4)]
        + f"{b1:02X}"
        + text[match.end(4) : match.start(6)]
        + f"{b2:02X}"
        + text[match.end(6) : match.start(8)]
        + f"{b3:02X}"
        + text[match.end(8) : match.start(10)]
        + build_date
        + text[match.end(10) :]
    )


def _rewrite_v171_banner_row2(text: str, revision: int, build_date: str) -> str:
    marker = text.find("control_release_banner_row2:")
    if marker < 0:
        raise RuntimeError("control_release_banner_row2 block not found")
    match = _BANNER_ROW2_RE.search(text, pos=marker)
    if match is None:
        raise RuntimeError("V1.71 release banner row 2 db line not found")
    row = f"Rev x{revision:02X} {build_date}"
    if len(row) != 16:
        raise RuntimeError(f"release banner row 2 must be 16 chars, got {row!r}")
    values = [ord(ch) for ch in row] + [0x00]
    return (
        text[: match.start(2)]
        + _db_bytes(values)
        + text[match.end(2) : match.start(4)]
        + row
        + text[match.end(4) :]
    )


def _rewrite_v171_release_metadata(
    text: str,
    *,
    build_date: str,
) -> tuple[str, int, int]:
    updated, old_rev, new_rev = _rewrite_v171_release_revision(text)
    updated = _rewrite_v171_build_date(updated, build_date)
    updated = _rewrite_v171_banner_row2(updated, new_rev, build_date)
    return updated, old_rev, new_rev


def bump_v171_release_revision(
    asm_path: Path = V171_CONTROL_ASM,
    *,
    build_date: str | None = None,
) -> tuple[int, int]:
    text = asm_path.read_text(encoding="utf-8")
    release_date = _validate_build_date(build_date or date.today().strftime("%Y%m%d"))
    try:
        updated, old_rev, new_rev = _rewrite_v171_release_metadata(
            text,
            build_date=release_date,
        )
    except RuntimeError as exc:
        raise RuntimeError(f"{exc} in {asm_path}") from exc
    asm_path.write_text(updated, encoding="utf-8")
    return old_rev, new_rev


def build_v171_release(
    *,
    asm_path: Path = V171_CONTROL_ASM,
    output_hex: Path = V171_CONTROL_HEX,
    gpasm: str = "gpasm",
    build_date: str | None = None,
) -> tuple[int, int, Path]:
    original_text = asm_path.read_text(encoding="utf-8")
    release_date = _validate_build_date(build_date or date.today().strftime("%Y%m%d"))
    try:
        updated_text, old_rev, new_rev = _rewrite_v171_release_metadata(
            original_text,
            build_date=release_date,
        )
    except RuntimeError as exc:
        raise RuntimeError(f"{exc} in {asm_path}") from exc

    source_lst = asm_path.with_suffix(".lst")
    # Mirror the V3.2 builder's `.lst` rollback so a failed gpasm run
    # cannot leave a partial listing beside the source.  V1.71 does not
    # currently have a symbol-resolution consumer for this listing, but
    # the symmetry keeps the release builders' failure semantics aligned.
    original_lst: bytes | None = None
    asm_modified = False
    output_hex.parent.mkdir(parents=True, exist_ok=True)
    tmpdir_obj = tempfile.TemporaryDirectory(prefix="v171_release_", dir=str(output_hex.parent))
    tmpdir = Path(tmpdir_obj.name)
    temp_hex = tmpdir / output_hex.name
    build_ok = False
    try:
        if source_lst.exists():
            original_lst = source_lst.read_bytes()
        asm_path.write_text(updated_text, encoding="utf-8")
        asm_modified = True
        assemble_v17(
            asm_path,
            temp_hex,
            output_lst=source_lst,
            gpasm=gpasm,
        )
        shutil.copy2(temp_hex, output_hex)
        build_ok = True
    finally:
        if not build_ok:
            # Rollback exceptions chain to the original via `__context__`.
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
            "Bump the canonical V1.71 CONTROL release revision and assemble "
            "firmware/patched/releases/DLCP_Control_V1.71.hex"
        ),
    )
    ap.add_argument("--gpasm", default="gpasm", help="gpasm executable (default: gpasm)")
    ap.add_argument(
        "--build-date",
        default=None,
        help="build date to bake into metadata/banner as YYYYMMDD (default: today)",
    )
    args = ap.parse_args(argv)

    old_rev, new_rev, output_hex = build_v171_release(
        gpasm=args.gpasm,
        build_date=args.build_date,
    )
    print(
        "built canonical V1.71 CONTROL release: "
        f"{output_hex} (release rev 0x{old_rev:02X} -> 0x{new_rev:02X})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
