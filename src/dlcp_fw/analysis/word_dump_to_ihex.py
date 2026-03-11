"""Convert and combine DLCP tabular exports into Intel HEX."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Sequence

from dlcp_fw.paths import (
    STOCK_MAIN_COMBINED_HEX,
    STOCK_MAIN_CONFIG_BITS_EXPORT,
    STOCK_MAIN_EE_DATA_EXPORT,
    STOCK_MAIN_HEX,
    STOCK_MAIN_PROGRAM_MEMORY_EXPORT,
    STOCK_MAIN_USER_ID_EXPORT,
)
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex


class WordDumpError(RuntimeError):
    """Raised when a tabular export cannot be parsed safely."""


@dataclass(frozen=True)
class ExportSummary:
    format_name: str
    row_count: int
    byte_count: int
    min_addr: int
    max_addr: int
    base_addr: int | None = None


@dataclass(frozen=True)
class CombinedSummary:
    input_summaries: tuple[tuple[Path, ExportSummary], ...]
    byte_count: int
    min_addr: int
    max_addr: int


CONFIG_REPORT_ROW_RE = re.compile(r"^\s*([0-9A-F]{6})\s+(\S+)\s+([0-9A-F]{2})\b")
CONFIG_REPORT_RANGE = range(0x300000, 0x30000E)
CONFIG_MASKED_LOW_BYTES = {0x300008, 0x30000A, 0x30000C}


def parse_int(s: str) -> int:
    return int(s, 0)


def _parse_hex_word(token: str, *, path: Path, lineno: int) -> int:
    if len(token) != 4:
        raise WordDumpError(f"{path}:{lineno}: expected 4 hex digits, got {token!r}")
    try:
        return int(token, 16)
    except ValueError as exc:
        raise WordDumpError(f"{path}:{lineno}: invalid hex word {token!r}") from exc


def _parse_hex_byte(token: str, *, path: Path, lineno: int) -> int:
    tok = token.strip()
    if tok.lower().startswith("0x"):
        tok = tok[2:]
    if len(tok) != 2:
        raise WordDumpError(f"{path}:{lineno}: expected 2 hex digits, got {token!r}")
    try:
        return int(tok, 16)
    except ValueError as exc:
        raise WordDumpError(f"{path}:{lineno}: invalid hex byte {token!r}") from exc


def _build_summary(
    *,
    format_name: str,
    row_count: int,
    mem: Dict[int, int],
    base_addr: int | None = None,
) -> ExportSummary:
    if not mem:
        raise WordDumpError(f"{format_name}: no data parsed")
    return ExportSummary(
        format_name=format_name,
        row_count=row_count,
        byte_count=len(mem),
        min_addr=min(mem),
        max_addr=max(mem),
        base_addr=base_addr,
    )


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="ascii").splitlines()


def parse_tabular_word_dump(path: Path) -> tuple[Dict[int, int], ExportSummary]:
    mem: Dict[int, int] = {}
    row_count = 0

    for lineno, raw_line in enumerate(_read_lines(path), 1):
        line = raw_line.strip()
        if not line or line.startswith("Address"):
            continue

        parts = line.split()
        if not parts:
            continue

        try:
            base_addr = int(parts[0], 16)
        except ValueError as exc:
            raise WordDumpError(f"{path}:{lineno}: invalid base address {parts[0]!r}") from exc
        if base_addr & 0x1:
            raise WordDumpError(f"{path}:{lineno}: odd base address 0x{base_addr:04X}")

        words: list[int] = []
        for token in parts[1:9]:
            if len(token) != 4:
                break
            words.append(_parse_hex_word(token, path=path, lineno=lineno))
        if not words:
            raise WordDumpError(f"{path}:{lineno}: no 16-bit words found")

        row_count += 1
        for idx, word in enumerate(words):
            addr = base_addr + idx * 2
            mem[addr] = word & 0xFF
            mem[addr + 1] = (word >> 8) & 0xFF

    return mem, _build_summary(format_name="word_dump", row_count=row_count, mem=mem)


def parse_byte_page_dump(path: Path, *, base_addr: int) -> tuple[Dict[int, int], ExportSummary]:
    mem: Dict[int, int] = {}
    row_count = 0

    for lineno, raw_line in enumerate(_read_lines(path), 1):
        line = raw_line.strip()
        if not line or line.startswith("Address"):
            continue

        parts = line.split()
        if len(parts) < 17:
            raise WordDumpError(f"{path}:{lineno}: expected 16 data bytes")
        try:
            row_offset = int(parts[0], 16)
        except ValueError as exc:
            raise WordDumpError(f"{path}:{lineno}: invalid row offset {parts[0]!r}") from exc

        row_count += 1
        for idx, token in enumerate(parts[1:17]):
            mem[base_addr + row_offset + idx] = _parse_hex_byte(token, path=path, lineno=lineno)

    return mem, _build_summary(
        format_name="byte_page",
        row_count=row_count,
        mem=mem,
        base_addr=base_addr,
    )


def parse_addressed_byte_table(path: Path) -> tuple[Dict[int, int], ExportSummary]:
    mem: Dict[int, int] = {}
    row_count = 0

    for lineno, raw_line in enumerate(_read_lines(path), 1):
        line = raw_line.strip()
        if not line or line.startswith("Address"):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        try:
            addr = int(parts[0], 16)
        except ValueError:
            continue

        mem[addr] = _parse_hex_byte(parts[1], path=path, lineno=lineno)
        row_count += 1

    if not mem:
        raise WordDumpError(f"{path}: no addressed bytes found")
    return mem, _build_summary(format_name="addressed_bytes", row_count=row_count, mem=mem)


def parse_decoded_config_report(
    path: Path,
    *,
    reference_bytes: Mapping[int, int] | None = None,
) -> tuple[Dict[int, int], ExportSummary]:
    mem: Dict[int, int] = {}
    row_count = 0

    for raw_line in _read_lines(path):
        m = CONFIG_REPORT_ROW_RE.match(raw_line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        value = int(m.group(3), 16)
        mem[addr] = value
        row_count += 1

    if not mem:
        raise WordDumpError(f"{path}: no decoded config rows found")

    if reference_bytes is not None:
        for addr in CONFIG_MASKED_LOW_BYTES:
            if addr in mem and addr in reference_bytes and (reference_bytes[addr] & 0x07) == mem[addr]:
                mem[addr] = reference_bytes[addr]
        for addr in CONFIG_REPORT_RANGE:
            if addr not in mem and addr in reference_bytes:
                mem[addr] = reference_bytes[addr]

    return mem, _build_summary(format_name="decoded_config_report", row_count=row_count, mem=mem)


def parse_export(
    path: Path,
    *,
    addressless_byte_base: int | None = None,
    config_reference_bytes: Mapping[int, int] | None = None,
) -> tuple[Dict[int, int], ExportSummary]:
    lines = _read_lines(path)
    first = ""
    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped:
            first = stripped
            break
    if not first:
        raise WordDumpError(f"{path}: empty file")

    if first.startswith(":"):
        mem = parse_intel_hex(path)
        return mem, _build_summary(format_name="intel_hex", row_count=len(lines), mem=mem)

    if first.startswith("Address"):
        if any(CONFIG_REPORT_ROW_RE.match(line) for line in lines):
            return parse_decoded_config_report(path, reference_bytes=config_reference_bytes)
        second_parts: list[str] | None = None
        for raw_line in lines[1:]:
            stripped = raw_line.strip()
            if not stripped:
                continue
            second_parts = stripped.split()
            break
        if not second_parts:
            raise WordDumpError(f"{path}: no data rows found")
        if len(second_parts) >= 9 and all(len(tok) == 4 for tok in second_parts[1:9]):
            return parse_tabular_word_dump(path)
        if len(second_parts) >= 17 and all(len(tok) == 2 for tok in second_parts[1:17]):
            if addressless_byte_base is None:
                raise WordDumpError(
                    f"{path}: byte-page export requires an explicit base address"
                )
            return parse_byte_page_dump(path, base_addr=addressless_byte_base)
        if len(second_parts) >= 2:
            return parse_addressed_byte_table(path)

    raise WordDumpError(f"{path}: unsupported export format")


def convert_tabular_word_dump_to_ihex(
    input_path: Path,
    output_path: Path,
    *,
    chunk: int = 16,
) -> ExportSummary:
    mem, summary = parse_tabular_word_dump(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_intel_hex(output_path, mem, chunk=chunk)
    return summary


def _merge_memories(
    regions: Sequence[tuple[Path, Dict[int, int]]],
) -> Dict[int, int]:
    merged: Dict[int, int] = {}
    owner: Dict[int, Path] = {}

    for path, mem in regions:
        for addr, value in mem.items():
            prev = merged.get(addr)
            if prev is not None and prev != value:
                raise WordDumpError(
                    f"byte conflict at 0x{addr:06X}: "
                    f"{owner[addr]}=0x{prev:02X}, {path}=0x{value:02X}"
                )
            merged[addr] = value
            owner[addr] = path
    return merged


def combine_exports_to_ihex(
    input_paths: Sequence[Path],
    output_path: Path,
    *,
    addressless_byte_base: int = 0xF00000,
    config_reference_hex: Path | None = None,
    chunk: int = 16,
) -> CombinedSummary:
    config_reference_bytes = None
    if config_reference_hex is not None:
        config_reference_bytes = parse_intel_hex(config_reference_hex)

    parsed: list[tuple[Path, Dict[int, int], ExportSummary]] = []
    for path in input_paths:
        mem, summary = parse_export(
            path,
            addressless_byte_base=addressless_byte_base,
            config_reference_bytes=config_reference_bytes,
        )
        parsed.append((path, mem, summary))

    merged = _merge_memories([(path, mem) for path, mem, _ in parsed])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_intel_hex(output_path, merged, chunk=chunk)

    return CombinedSummary(
        input_summaries=tuple((path, summary) for path, _, summary in parsed),
        byte_count=len(merged),
        min_addr=min(merged),
        max_addr=max(merged),
    )


def combine_v23_main_exports_to_ihex(
    output_path: Path,
    *,
    program_memory_path: Path = STOCK_MAIN_PROGRAM_MEMORY_EXPORT,
    config_bits_path: Path = STOCK_MAIN_CONFIG_BITS_EXPORT,
    ee_data_path: Path = STOCK_MAIN_EE_DATA_EXPORT,
    user_id_path: Path = STOCK_MAIN_USER_ID_EXPORT,
    eeprom_base: int = 0xF00000,
    config_reference_hex: Path = STOCK_MAIN_HEX,
    chunk: int = 16,
) -> CombinedSummary:
    return combine_exports_to_ihex(
        [program_memory_path, config_bits_path, ee_data_path, user_id_path],
        output_path,
        addressless_byte_base=eeprom_base,
        config_reference_hex=config_reference_hex,
        chunk=chunk,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Convert DLCP tabular exports into Intel HEX."
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    convert_ap = sub.add_parser("convert-dump", help="convert a word dump to Intel HEX")
    convert_ap.add_argument("input_dump", type=Path, help="input tabular word dump")
    convert_ap.add_argument("output_hex", type=Path, help="output Intel HEX path")
    convert_ap.add_argument(
        "--chunk",
        type=int,
        default=16,
        help="Intel HEX data bytes per record (default: 16)",
    )

    combine_ap = sub.add_parser(
        "combine",
        help="combine mixed DLCP exports into one Intel HEX",
    )
    combine_ap.add_argument("output_hex", type=Path, help="output Intel HEX path")
    combine_ap.add_argument("inputs", nargs="+", type=Path, help="input export files")
    combine_ap.add_argument(
        "--addressless-byte-base",
        type=parse_int,
        default=0xF00000,
        help="base address for 16x16 byte-page exports without an explicit address",
    )
    combine_ap.add_argument(
        "--config-reference-hex",
        type=Path,
        default=None,
        help="Intel HEX used to fill/normalize decoded config-report exports",
    )
    combine_ap.add_argument(
        "--chunk",
        type=int,
        default=16,
        help="Intel HEX data bytes per record (default: 16)",
    )

    main_ap = sub.add_parser(
        "combine-v23-main-exports",
        help="combine the stock V2.3 main export fragments into one Intel HEX",
    )
    main_ap.add_argument(
        "--program-memory",
        type=Path,
        default=STOCK_MAIN_PROGRAM_MEMORY_EXPORT,
        help="main program-memory word export",
    )
    main_ap.add_argument(
        "--configuration-bits",
        type=Path,
        default=STOCK_MAIN_CONFIG_BITS_EXPORT,
        help="decoded configuration-bit export",
    )
    main_ap.add_argument(
        "--ee-data",
        type=Path,
        default=STOCK_MAIN_EE_DATA_EXPORT,
        help="extra addressed export",
    )
    main_ap.add_argument(
        "--user-id",
        type=Path,
        default=STOCK_MAIN_USER_ID_EXPORT,
        help="user ID addressed export",
    )
    main_ap.add_argument(
        "--output",
        type=Path,
        default=STOCK_MAIN_COMBINED_HEX,
        help="output Intel HEX path",
    )
    main_ap.add_argument(
        "--eeprom-base",
        type=parse_int,
        default=0xF00000,
        help="EEPROM base used for addressless 0x100-byte exports",
    )
    main_ap.add_argument(
        "--config-reference-hex",
        type=Path,
        default=STOCK_MAIN_HEX,
        help="Intel HEX used to fill/normalize decoded config-report bytes",
    )
    main_ap.add_argument(
        "--chunk",
        type=int,
        default=16,
        help="Intel HEX data bytes per record (default: 16)",
    )

    return ap


def _print_export_summary(path: Path, summary: ExportSummary) -> None:
    base_text = ""
    if summary.base_addr is not None:
        base_text = f" base=0x{summary.base_addr:06X}"
    print(
        f"input: {path} format={summary.format_name}{base_text} "
        f"rows={summary.row_count} bytes={summary.byte_count} "
        f"range=0x{summary.min_addr:06X}-0x{summary.max_addr:06X}"
    )


def _print_combined_summary(output_path: Path, summary: CombinedSummary) -> None:
    print("combine: OK")
    for path, export_summary in summary.input_summaries:
        _print_export_summary(path, export_summary)
    print("output:", output_path)
    print("bytes:", summary.byte_count)
    print(f"range: 0x{summary.min_addr:06X}-0x{summary.max_addr:06X}")


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(argv) if argv is not None else None
    if args_list is None:
        import sys

        args_list = sys.argv[1:]
    if args_list and args_list[0] not in {
        "convert-dump",
        "combine",
        "combine-v23-main-exports",
    }:
        args_list = ["convert-dump", *args_list]

    ap = build_arg_parser()
    args = ap.parse_args(args_list)

    if args.cmd == "convert-dump":
        summary = convert_tabular_word_dump_to_ihex(
            args.input_dump.resolve(),
            args.output_hex.resolve(),
            chunk=args.chunk,
        )
        print("word-dump-to-ihex: OK")
        _print_export_summary(args.input_dump.resolve(), summary)
        print("output:", args.output_hex.resolve())
        return 0

    if args.cmd == "combine":
        summary = combine_exports_to_ihex(
            [path.resolve() for path in args.inputs],
            args.output_hex.resolve(),
            addressless_byte_base=args.addressless_byte_base,
            config_reference_hex=args.config_reference_hex.resolve() if args.config_reference_hex else None,
            chunk=args.chunk,
        )
        _print_combined_summary(args.output_hex.resolve(), summary)
        return 0

    if args.cmd == "combine-v23-main-exports":
        summary = combine_v23_main_exports_to_ihex(
            args.output.resolve(),
            program_memory_path=args.program_memory.resolve(),
            config_bits_path=args.configuration_bits.resolve(),
            ee_data_path=args.ee_data.resolve(),
            user_id_path=args.user_id.resolve(),
            eeprom_base=args.eeprom_base,
            config_reference_hex=args.config_reference_hex.resolve(),
            chunk=args.chunk,
        )
        _print_combined_summary(args.output.resolve(), summary)
        return 0

    raise AssertionError(f"unhandled command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
