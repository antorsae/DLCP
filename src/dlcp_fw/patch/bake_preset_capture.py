#!/usr/bin/env python3
"""Bake captured preset tables and EEPROM names into a V3.1 HEX image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dlcp_fw.flash.read_coeffs import NAME_LEN, PRESET_FLASH_BASE, PRESET_NAME_EEPROM_BASE, encode_name_slot
from dlcp_fw.paths import V31_DIAG_MEMREAD_USB_SAFE_HEX
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex


EEPROM_BASE = 0xF00000
TABLE_SIZE = 0x0A00


def _load_capture_metadata(
    capture_path: Path,
    *,
    explicit_meta: Path | None,
    name_override: str | None,
    preset: str,
) -> tuple[bytes, bytes, str]:
    table = capture_path.read_bytes()
    if len(table) != TABLE_SIZE:
        raise RuntimeError(f"{capture_path} has {len(table)} bytes, expected {TABLE_SIZE}")

    meta_path = explicit_meta if explicit_meta is not None else capture_path.with_suffix(".json")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raw_hex = str(meta.get("config_name_raw_hex", ""))
        config_name = str(meta.get("config_name", ""))
        if len(raw_hex) != NAME_LEN * 2:
            raise RuntimeError(f"{meta_path} has invalid config_name_raw_hex length")
        name_slot = bytes.fromhex(raw_hex)
        return table, name_slot, config_name

    if name_override is None:
        raise RuntimeError(
            f"missing metadata sidecar for {capture_path}; provide --name-{preset.lower()} or --meta-{preset.lower()}"
        )
    return table, encode_name_slot(name_override), name_override


def _patch_capture(mem: dict[int, int], *, preset: str, table: bytes, name_slot: bytes) -> None:
    flash_base = PRESET_FLASH_BASE[preset]
    ee_base = EEPROM_BASE + PRESET_NAME_EEPROM_BASE[preset]
    for idx, value in enumerate(table):
        mem[flash_base + idx] = value
    for idx, value in enumerate(name_slot):
        mem[ee_base + idx] = value


def _sha256_hex(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _cmd_bake(args: argparse.Namespace) -> int:
    base_hex = args.base_hex
    mem = parse_intel_hex(base_hex)
    summary: dict[str, object] = {
        "base_hex": str(base_hex),
        "patched_presets": [],
    }

    for preset in ("A", "B"):
        capture_path = getattr(args, f"capture_{preset.lower()}")
        if capture_path is None:
            continue
        table, name_slot, config_name = _load_capture_metadata(
            capture_path,
            explicit_meta=getattr(args, f"meta_{preset.lower()}"),
            name_override=getattr(args, f"name_{preset.lower()}"),
            preset=preset,
        )
        _patch_capture(mem, preset=preset, table=table, name_slot=name_slot)
        summary["patched_presets"].append(
            {
                "preset": preset,
                "capture": str(capture_path),
                "config_name": config_name,
                "table_sha256": _sha256_hex(table),
                "flash_base": PRESET_FLASH_BASE[preset],
                "eeprom_base": EEPROM_BASE + PRESET_NAME_EEPROM_BASE[preset],
            }
        )

    if not summary["patched_presets"]:
        raise RuntimeError("nothing to bake; provide --capture-a and/or --capture-b")

    out_hex = args.out
    out_hex.parent.mkdir(parents=True, exist_ok=True)
    write_intel_hex(out_hex, mem)
    print(f"wrote baked hex: {out_hex}")

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="ascii")
        print(f"wrote manifest: {args.json_out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Patch one or both captured preset tables plus EEPROM config-name "
            "slots into a V3.1 diagnostic HEX."
        )
    )
    parser.add_argument("--base-hex", type=Path, default=V31_DIAG_MEMREAD_USB_SAFE_HEX)
    parser.add_argument("--capture-a", type=Path, default=None)
    parser.add_argument("--capture-b", type=Path, default=None)
    parser.add_argument("--meta-a", type=Path, default=None)
    parser.add_argument("--meta-b", type=Path, default=None)
    parser.add_argument("--name-a", default=None, help="ASCII config name if no sidecar JSON exists")
    parser.add_argument("--name-b", default=None, help="ASCII config name if no sidecar JSON exists")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return _cmd_bake(args)


if __name__ == "__main__":
    raise SystemExit(main())
