#!/usr/bin/env python3
"""
Deterministic byte-level patcher for Hypex Filter Design v2.12.

This adds an `R-L` routing item to each of the six channel routing combo boxes.
The patch is fixed-address and validated with strict pre/post byte assertions.

Default one-command usage:
  python3 scripts/patch_hfd_v212_rl.py
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

DEFAULT_INPUT = (
    ROOT
    / "firmware"
    / "stock"
    / "PC"
    / "HFD_v2.12"
    / "Hypex Filter Design 2.12"
    / "Hypex Filter Design V2.12.exe"
)
DEFAULT_OUTPUT = (
    ROOT
    / "firmware"
    / "patched"
    / "PC"
    / "HFD_v2.12"
    / "Hypex Filter Design 2.12"
    / "Hypex Filter Design V2.12-RL.exe"
)

EXPECTED_STOCK_SHA256 = "95cb809fb9fd13251ae8572187e548a3ea1ea5ff747d8ace1e0bb77fc5e9e5a5"
EXPECTED_PATCHED_SHA256 = "34c6314bedaf7259cb2642c71651291360f4986a938ed725f6ca1c00dd11d8b3"

# IMAGE layout for VA checks.
CODE_FILE_BASE = 0x00000400
CODE_VA_BASE = 0x00401000


@dataclass(frozen=True)
class HookPatch:
    name: str
    file_offset: int
    before: bytes
    after: bytes
    target_va: int


@dataclass(frozen=True)
class BlobPatch:
    name: str
    file_offset: int
    before: bytes
    after: bytes


HOOK_PATCHES = (
    HookPatch(
        name="hook_ch1",
        file_offset=0x14FAB0,
        before=bytes.fromhex("8B8314030000"),
        after=bytes.fromhex("E83B54010090"),
        target_va=0x565AF0,
    ),
    HookPatch(
        name="hook_ch2",
        file_offset=0x14FBF1,
        before=bytes.fromhex("8B8318030000"),
        after=bytes.fromhex("E81953010090"),
        target_va=0x565B0F,
    ),
    HookPatch(
        name="hook_ch3",
        file_offset=0x14FD32,
        before=bytes.fromhex("8B831C030000"),
        after=bytes.fromhex("E8F751010090"),
        target_va=0x565B2E,
    ),
    HookPatch(
        name="hook_ch4",
        file_offset=0x14FE73,
        before=bytes.fromhex("8B8320030000"),
        after=bytes.fromhex("E8D550010090"),
        target_va=0x565B4D,
    ),
    HookPatch(
        name="hook_ch5",
        file_offset=0x14FFB4,
        before=bytes.fromhex("8B8324030000"),
        after=bytes.fromhex("E8B34F010090"),
        target_va=0x565B6C,
    ),
    HookPatch(
        name="hook_ch6",
        file_offset=0x1500F5,
        before=bytes.fromhex("8B8328030000"),
        after=bytes.fromhex("E8914E010090"),
        target_va=0x565B8B,
    ),
)

CAVE_PAYLOAD = bytes.fromhex(
    "538b83140300008b8014020000baac5b56008b08ff51385b8b8314030000c353"
    "8b83180300008b8014020000baac5b56008b08ff51385b8b8318030000c3538b"
    "831c0300008b8014020000baac5b56008b08ff51385b8b831c030000c3538b83"
    "200300008b8014020000baac5b56008b08ff51385b8b8320030000c3538b8324"
    "0300008b8014020000baac5b56008b08ff51385b8b8324030000c3538b832803"
    "00008b8014020000baac5b56008b08ff51385b8b8328030000c3522d4c00"
)

BLOB_PATCHES = HOOK_PATCHES + (
    BlobPatch(
        name="code_cave_payload",
        file_offset=0x164EF0,
        before=b"\x00" * len(CAVE_PAYLOAD),
        after=CAVE_PAYLOAD,
    ),
)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_to_va(file_offset: int) -> int:
    return CODE_VA_BASE + (file_offset - CODE_FILE_BASE)


def _get_slice(data: bytes | bytearray, offset: int, size: int) -> bytes:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise RuntimeError(f"slice out of range: off=0x{offset:X} size=0x{size:X} len=0x{len(data):X}")
    return bytes(data[offset : offset + size])


def _assert_bytes(data: bytes | bytearray, patch: BlobPatch, expected: bytes, phase: str) -> None:
    got = _get_slice(data, patch.file_offset, len(expected))
    if got != expected:
        raise RuntimeError(
            f"{phase} assertion failed for {patch.name} at 0x{patch.file_offset:08X}: "
            f"got={got.hex()} expected={expected.hex()}"
        )


def _assert_hook_targets(data: bytes | bytearray) -> None:
    for hook in HOOK_PATCHES:
        call = _get_slice(data, hook.file_offset, 5)
        if call[0] != 0xE8:
            raise RuntimeError(
                f"post assertion failed for {hook.name} at 0x{hook.file_offset:08X}: "
                f"missing CALL opcode (got 0x{call[0]:02X})"
            )
        rel = int.from_bytes(call[1:5], byteorder="little", signed=True)
        next_va = _file_to_va(hook.file_offset) + 5
        target_va = (next_va + rel) & 0xFFFFFFFF
        if target_va != hook.target_va:
            raise RuntimeError(
                f"post assertion failed for {hook.name} target: got=0x{target_va:08X} "
                f"expected=0x{hook.target_va:08X}"
            )


def _patch_bytes(input_bytes: bytes) -> bytes:
    out = bytearray(input_bytes)

    for patch in BLOB_PATCHES:
        _assert_bytes(out, patch, patch.before, phase="pre")

    for patch in BLOB_PATCHES:
        out[patch.file_offset : patch.file_offset + len(patch.after)] = patch.after

    for patch in BLOB_PATCHES:
        _assert_bytes(out, patch, patch.after, phase="post")
    _assert_hook_targets(out)

    return bytes(out)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministically patch HFD v2.12 EXE to add R-L routing option."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"input stock EXE (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output patched EXE (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="patch input file in place (overrides --output)",
    )
    parser.add_argument(
        "--skip-input-sha256-check",
        action="store_true",
        help="allow patching non-canonical input image (still enforces byte assertions)",
    )
    parser.add_argument(
        "--skip-output-sha256-check",
        action="store_true",
        help="skip deterministic output hash check",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    input_path = args.input.resolve()
    output_path = input_path if args.in_place else args.output.resolve()

    if not input_path.is_file():
        raise SystemExit(f"input EXE not found: {input_path}")
    if not args.in_place and output_path == input_path:
        raise SystemExit("refusing to overwrite input without --in-place")

    src = input_path.read_bytes()
    src_sha = _sha256_hex(src)
    if not args.skip_input_sha256_check and src_sha != EXPECTED_STOCK_SHA256:
        raise SystemExit(
            "input sha256 mismatch:\n"
            f"  got:      {src_sha}\n"
            f"  expected: {EXPECTED_STOCK_SHA256}\n"
            "Use --skip-input-sha256-check only if you intentionally patch a known-compatible variant."
        )

    try:
        patched = _patch_bytes(src)
    except RuntimeError as exc:
        raise SystemExit(f"patch failed: {exc}")
    patched_sha = _sha256_hex(patched)
    if not args.skip_output_sha256_check and patched_sha != EXPECTED_PATCHED_SHA256:
        raise SystemExit(
            "patched sha256 mismatch (unexpected non-deterministic result):\n"
            f"  got:      {patched_sha}\n"
            f"  expected: {EXPECTED_PATCHED_SHA256}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(patched)

    print("HFD v2.12 R-L patch: OK")
    print(f"input:  {input_path}")
    print(f"output: {output_path}")
    print(f"size:   {len(patched)} bytes")
    print(f"sha256: {patched_sha}")
    print(f"patches: {len(BLOB_PATCHES)} regions ({len(HOOK_PATCHES)} hooks + cave payload)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
