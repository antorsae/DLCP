#!/usr/bin/env python3
"""
Focused A/B probe for DLCP "DSP Filename" persistence.

Goal:
- Upload two HFD projects with identical coefficients but different DSP filenames.
- Dump DLCP flash after each upload.
- Pinpoint which bytes changed (if any), with emphasis on 0x5600..0x5FFF.

Examples:
  # Interactive full workflow: baseline -> upload A -> upload B -> analysis
  python3 -m dlcp_fw.flash.dsp_filename_ab_probe run \
    --name-a "LXS214_22MG10F-v4" \
    --name-b "LXS214_22MG10F-v5"

  # Single capture only
  python3 -m dlcp_fw.flash.dsp_filename_ab_probe capture --out dump.bin

  # Analyze two existing dumps
  python3 -m dlcp_fw.flash.dsp_filename_ab_probe analyze \
    --before dump_A.bin --after dump_B.bin \
    --report-out report_A_to_B.md --json-out report_A_to_B.json
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import pathlib
import time
from collections import defaultdict
from datetime import datetime, timezone

from dlcp_fw.paths import SIM_ARTIFACTS_DIR

VID_DEFAULT = 0x04D8
PID_DEFAULT = 0xFF89

START_DEFAULT = 0x0800
SIZE_DEFAULT = 0x7800
CHUNK_DEFAULT = 0xFF

TABLE_BASE = 0x5600
TABLE_SIZE = 0x0A00
TABLE_TAIL_BASE = 0x5F00


def parse_int(s: str) -> int:
    return int(s, 0)


def idx_for_addr(addr: int) -> int:
    if not (0 <= addr <= 0xFF):
        raise ValueError(f"addr out of range: 0x{addr:02X}")
    return (addr - 0xEC) & 0xFF


def _hex(addr: int) -> str:
    return f"0x{addr:04X}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slice_by_addr(data: bytes, dump_start: int, begin: int, end_excl: int) -> bytes:
    lo = max(begin, dump_start)
    hi = min(end_excl, dump_start + len(data))
    if hi <= lo:
        return b""
    return data[lo - dump_start : hi - dump_start]


class DlcpEp0:
    """EP0 helper (same primitive used in reanalysis_20260214/dlcp_ep0_flash_dump.py)."""

    def __init__(self, vid: int, pid: int) -> None:
        try:
            import usb.core  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "pyusb is required for capture/run commands. Install with: "
                "python3 -m pip install pyusb"
            ) from exc
        self._usb_core = usb.core
        dev = self._usb_core.find(idVendor=vid, idProduct=pid)
        if dev is None:
            raise RuntimeError(f"DLCP not found (VID:PID = {vid:04X}:{pid:04X})")
        self.dev = dev
        self._prepare()

    def _prepare(self) -> None:
        try:
            self.dev.set_configuration()
        except self._usb_core.USBError:
            pass

    def _poke(self, addr: int, value: int, in_dir: bool, read_len: int = 0) -> bytes:
        if not (0 <= value <= 0xFF):
            raise ValueError(f"value out of range: 0x{value:02X}")

        bm = 0x80 if in_dir else 0x00  # standard + device recipient
        b_request = 0x0B
        w_value = value
        w_index = idx_for_addr(addr)
        try:
            if in_dir:
                data = self.dev.ctrl_transfer(bm, b_request, w_value, w_index, read_len)
                return bytes(data)
            self.dev.ctrl_transfer(bm, b_request, w_value, w_index, None)
            return b""
        except self._usb_core.USBError as exc:
            raise RuntimeError(
                f"USB control transfer failed: {exc}\n"
                "Try:\n"
                "  1) quit HFD and any app using DLCP USB\n"
                "  2) replug DLCP\n"
                "  3) run via sudo"
            ) from exc

    def set_pointer(self, addr16: int) -> None:
        lo = addr16 & 0xFF
        hi = (addr16 >> 8) & 0xFF
        self._poke(0x75, lo, in_dir=False)
        self._poke(0x76, hi, in_dir=False)

    def read_exact(self, n: int) -> bytes:
        if n <= 0:
            return b""
        # The hardware 0xE8 bulk-read path produces shifted/garbled captures on
        # real DLCP units. Stream everything through the stable 0xE7 path.
        out = bytearray()
        remaining = n
        while remaining:
            chunk = min(remaining, 0xFF)
            data = self._poke(0xE7, chunk, in_dir=True, read_len=chunk)
            if len(data) != chunk:
                raise RuntimeError(f"short read: expected {chunk}, got {len(data)}")
            out.extend(data)
            remaining -= chunk
        return bytes(out)


def dump_flash(
    *,
    out_path: pathlib.Path,
    vid: int,
    pid: int,
    start: int,
    size: int,
    chunk: int,
) -> bytes:
    if start < 0 or start > 0xFFFF:
        raise ValueError("start must be in 0..0xFFFF")
    if size <= 0:
        raise ValueError("size must be > 0")
    if chunk <= 0:
        raise ValueError("chunk must be > 0")

    dev = DlcpEp0(vid=vid, pid=pid)
    dev.set_pointer(start)
    out = bytearray()
    remaining = size
    while remaining:
        n = min(chunk, remaining)
        out.extend(dev.read_exact(n))
        remaining -= n
        done = size - remaining
        print(f"\rread 0x{done:04X}/0x{size:04X}", end="", flush=True)
    print()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out)
    print(f"wrote {len(out)} bytes -> {out_path}")
    return bytes(out)


def _contiguous_ranges(changed_offsets: list[int], start_addr: int) -> list[tuple[int, int]]:
    if not changed_offsets:
        return []
    ranges: list[tuple[int, int]] = []
    s = changed_offsets[0]
    p = changed_offsets[0]
    for i in changed_offsets[1:]:
        if i == p + 1:
            p = i
            continue
        ranges.append((start_addr + s, start_addr + p))
        s = p = i
    ranges.append((start_addr + s, start_addr + p))
    return ranges


@dataclasses.dataclass
class EntryChange:
    index: int
    entry_addr: int
    op: int
    sub: int
    length: int
    changed_offsets: list[int]
    changed_count: int


@dataclasses.dataclass
class DiffAnalysis:
    before_sha256: str
    after_sha256: str
    start_addr: int
    size: int
    total_changed: int
    changed_ranges: list[tuple[int, int]]
    sample_changes: list[tuple[int, int, int]]
    region_counts: dict[str, int]
    entry_changes: list[EntryChange]
    table_sha_before: str
    table_sha_after: str
    table_main_sha_before: str
    table_main_sha_after: str
    table_tail_sha_before: str
    table_tail_sha_after: str
    inference: str


def _classify_region(addr: int) -> str:
    if 0x0800 <= addr <= 0x0FFF:
        return "low_window_0800_0fff"
    if 0x1000 <= addr <= 0x55FF:
        return "app_code_1000_55ff"
    if 0x5600 <= addr <= 0x5EFF:
        return "dsp_table_main_5600_5eff"
    if 0x5F00 <= addr <= 0x5FFF:
        return "dsp_table_tail_5f00_5fff"
    if 0x6000 <= addr <= 0x7FFF:
        return "high_window_6000_7fff"
    return "outside_common_dump_window"


def _inference_from_counts(total_changed: int, counts: dict[str, int]) -> str:
    nonzero = {k: v for k, v in counts.items() if v}
    if total_changed == 0:
        return "No byte changes detected."

    only_tail = (
        counts.get("dsp_table_tail_5f00_5fff", 0) > 0
        and counts.get("dsp_table_main_5600_5eff", 0) == 0
        and counts.get("app_code_1000_55ff", 0) == 0
        and counts.get("low_window_0800_0fff", 0) == 0
        and counts.get("high_window_6000_7fff", 0) == 0
    )
    if only_tail:
        return (
            "Tail-only table changes (0x5F00..0x5FFF). "
            "This is compatible with metadata/token updates (candidate filename storage)."
        )

    if counts.get("dsp_table_main_5600_5eff", 0) > 0 and counts.get("app_code_1000_55ff", 0) == 0:
        return (
            "Changes include DSP table main area (0x5600..0x5EFF). "
            "This usually means coefficient/config payload changed."
        )

    if counts.get("app_code_1000_55ff", 0) > 0:
        return (
            "Unexpected app code region changes detected. "
            "This is not expected for pure HFD filter upload metadata changes."
        )

    return f"Mixed changes detected across regions: {nonzero}"


def analyze_bytes(before: bytes, after: bytes, *, start_addr: int) -> DiffAnalysis:
    if len(before) != len(after):
        raise ValueError(f"length mismatch: before={len(before)} after={len(after)}")
    changed_offsets = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    changed_ranges = _contiguous_ranges(changed_offsets, start_addr)
    sample_changes = [
        (start_addr + i, before[i], after[i])
        for i in changed_offsets[:128]
    ]

    region_counts: dict[str, int] = defaultdict(int)
    for off in changed_offsets:
        addr = start_addr + off
        region_counts[_classify_region(addr)] += 1

    entry_to_offsets: dict[int, list[int]] = defaultdict(list)
    for off in changed_offsets:
        addr = start_addr + off
        if not (TABLE_BASE <= addr < TABLE_BASE + TABLE_SIZE):
            continue
        idx = (addr - TABLE_BASE) // 24
        off_in_entry = (addr - TABLE_BASE) % 24
        entry_to_offsets[idx].append(off_in_entry)

    entry_changes: list[EntryChange] = []
    for idx in sorted(entry_to_offsets):
        entry_addr = TABLE_BASE + idx * 24
        off = entry_addr - start_addr
        if off < 0 or off + 24 > len(after):
            continue
        entry = after[off : off + 24]
        op = entry[0]
        sub = entry[1]
        length = entry[2] | (entry[3] << 8)
        offs = sorted(set(entry_to_offsets[idx]))
        entry_changes.append(
            EntryChange(
                index=idx,
                entry_addr=entry_addr,
                op=op,
                sub=sub,
                length=length,
                changed_offsets=offs,
                changed_count=len(offs),
            )
        )

    table_before = _slice_by_addr(before, start_addr, TABLE_BASE, TABLE_BASE + TABLE_SIZE)
    table_after = _slice_by_addr(after, start_addr, TABLE_BASE, TABLE_BASE + TABLE_SIZE)
    table_main_before = _slice_by_addr(before, start_addr, TABLE_BASE, TABLE_TAIL_BASE)
    table_main_after = _slice_by_addr(after, start_addr, TABLE_BASE, TABLE_TAIL_BASE)
    table_tail_before = _slice_by_addr(before, start_addr, TABLE_TAIL_BASE, TABLE_BASE + TABLE_SIZE)
    table_tail_after = _slice_by_addr(after, start_addr, TABLE_TAIL_BASE, TABLE_BASE + TABLE_SIZE)

    counts = {
        "low_window_0800_0fff": region_counts.get("low_window_0800_0fff", 0),
        "app_code_1000_55ff": region_counts.get("app_code_1000_55ff", 0),
        "dsp_table_main_5600_5eff": region_counts.get("dsp_table_main_5600_5eff", 0),
        "dsp_table_tail_5f00_5fff": region_counts.get("dsp_table_tail_5f00_5fff", 0),
        "high_window_6000_7fff": region_counts.get("high_window_6000_7fff", 0),
        "outside_common_dump_window": region_counts.get("outside_common_dump_window", 0),
    }

    return DiffAnalysis(
        before_sha256=_sha256(before),
        after_sha256=_sha256(after),
        start_addr=start_addr,
        size=len(before),
        total_changed=len(changed_offsets),
        changed_ranges=changed_ranges,
        sample_changes=sample_changes,
        region_counts=counts,
        entry_changes=entry_changes,
        table_sha_before=_sha256(table_before),
        table_sha_after=_sha256(table_after),
        table_main_sha_before=_sha256(table_main_before),
        table_main_sha_after=_sha256(table_main_after),
        table_tail_sha_before=_sha256(table_tail_before),
        table_tail_sha_after=_sha256(table_tail_after),
        inference=_inference_from_counts(len(changed_offsets), counts),
    )


def _analysis_to_json_dict(a: DiffAnalysis) -> dict[str, object]:
    return {
        "before_sha256": a.before_sha256,
        "after_sha256": a.after_sha256,
        "start_addr": a.start_addr,
        "size": a.size,
        "total_changed": a.total_changed,
        "changed_ranges": [{"start": s, "end": e} for s, e in a.changed_ranges],
        "sample_changes": [
            {"addr": addr, "before": b0, "after": b1} for addr, b0, b1 in a.sample_changes
        ],
        "region_counts": a.region_counts,
        "entry_changes": [
            {
                "index": e.index,
                "entry_addr": e.entry_addr,
                "op": e.op,
                "sub": e.sub,
                "length": e.length,
                "changed_offsets": e.changed_offsets,
                "changed_count": e.changed_count,
            }
            for e in a.entry_changes
        ],
        "table_sha_before": a.table_sha_before,
        "table_sha_after": a.table_sha_after,
        "table_main_sha_before": a.table_main_sha_before,
        "table_main_sha_after": a.table_main_sha_after,
        "table_tail_sha_before": a.table_tail_sha_before,
        "table_tail_sha_after": a.table_tail_sha_after,
        "inference": a.inference,
    }


def write_markdown_report(
    *,
    out_path: pathlib.Path,
    label: str,
    before_path: pathlib.Path,
    after_path: pathlib.Path,
    analysis: DiffAnalysis,
    max_ranges: int = 128,
    max_entries: int = 128,
) -> None:
    lines: list[str] = []
    lines.append(f"# DLCP DSP Filename A/B Probe Report: {label}")
    lines.append("")
    lines.append(f"- UTC timestamp: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Before dump: `{before_path}`")
    lines.append(f"- After dump: `{after_path}`")
    lines.append(f"- Dump address window: {_hex(analysis.start_addr)}..{_hex(analysis.start_addr + analysis.size - 1)}")
    lines.append("")
    lines.append("## Hashes")
    lines.append("")
    lines.append(f"- before sha256: `{analysis.before_sha256}`")
    lines.append(f"- after sha256: `{analysis.after_sha256}`")
    lines.append(f"- table 0x5600..0x5FFF before: `{analysis.table_sha_before}`")
    lines.append(f"- table 0x5600..0x5FFF after: `{analysis.table_sha_after}`")
    lines.append(f"- table main 0x5600..0x5EFF before: `{analysis.table_main_sha_before}`")
    lines.append(f"- table main 0x5600..0x5EFF after: `{analysis.table_main_sha_after}`")
    lines.append(f"- table tail 0x5F00..0x5FFF before: `{analysis.table_tail_sha_before}`")
    lines.append(f"- table tail 0x5F00..0x5FFF after: `{analysis.table_tail_sha_after}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- total changed bytes: **{analysis.total_changed}**")
    lines.append(f"- inference: {analysis.inference}")
    lines.append("- changed bytes by region:")
    for key, val in analysis.region_counts.items():
        lines.append(f"  - {key}: {val}")
    lines.append("")
    lines.append("## Changed Ranges")
    lines.append("")
    if not analysis.changed_ranges:
        lines.append("- none")
    else:
        for i, (s, e) in enumerate(analysis.changed_ranges[:max_ranges], start=1):
            lines.append(f"- {i}. {_hex(s)}..{_hex(e)} ({e - s + 1} bytes)")
        if len(analysis.changed_ranges) > max_ranges:
            lines.append(f"- ... truncated {len(analysis.changed_ranges) - max_ranges} more ranges")
    lines.append("")
    lines.append("## Table Entry Changes (0x5600..0x5FFF @ 24-byte stride view)")
    lines.append("")
    if not analysis.entry_changes:
        lines.append("- none")
    else:
        for ec in analysis.entry_changes[:max_entries]:
            offs = ",".join(str(x) for x in ec.changed_offsets)
            lines.append(
                f"- idx={ec.index} addr={_hex(ec.entry_addr)} "
                f"op=0x{ec.op:02X} sub=0x{ec.sub:02X} len=0x{ec.length:04X} "
                f"changed_offsets=[{offs}]"
            )
        if len(analysis.entry_changes) > max_entries:
            lines.append(f"- ... truncated {len(analysis.entry_changes) - max_entries} more entries")
    lines.append("")
    lines.append("## Sample Byte Diffs")
    lines.append("")
    if not analysis.sample_changes:
        lines.append("- none")
    else:
        for addr, b0, b1 in analysis.sample_changes:
            lines.append(f"- {_hex(addr)}: 0x{b0:02X} -> 0x{b1:02X}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="ascii")


def _cmd_capture(args: argparse.Namespace) -> int:
    dump_flash(
        out_path=args.out,
        vid=args.vid,
        pid=args.pid,
        start=args.start,
        size=args.size,
        chunk=args.chunk,
    )
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    before = args.before.read_bytes()
    after = args.after.read_bytes()
    a = analyze_bytes(before, after, start_addr=args.start)
    print(f"changed bytes: {a.total_changed}")
    print("region counts:", json.dumps(a.region_counts, sort_keys=True))
    print("inference:", a.inference)

    if args.report_out is not None:
        write_markdown_report(
            out_path=args.report_out,
            label=args.label,
            before_path=args.before,
            after_path=args.after,
            analysis=a,
            max_ranges=args.max_ranges,
            max_entries=args.max_entries,
        )
        print(f"wrote report: {args.report_out}")

    if args.json_out is not None:
        payload = _analysis_to_json_dict(a)
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="ascii")
        print(f"wrote json: {args.json_out}")
    return 0


def _prompt(msg: str, assume_yes: bool) -> None:
    if assume_yes:
        print(f"[skip prompt] {msg}")
        return
    input(msg)


def _cmd_run(args: argparse.Namespace) -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    out_dir = args.out_dir / f"{stamp}_{args.session_tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    dump0 = out_dir / "00_baseline.bin"
    dump1 = out_dir / "10_after_A.bin"
    dump2 = out_dir / "20_after_B.bin"

    print("Step 0: capture baseline dump")
    dump_flash(
        out_path=dump0,
        vid=args.vid,
        pid=args.pid,
        start=args.start,
        size=args.size,
        chunk=args.chunk,
    )

    _prompt(
        "\nNow in HFD: upload profile A (coefficients fixed, filename changed only).\n"
        f"Target filename A: {args.name_a}\n"
        "Press Enter when upload is complete and device is stable... ",
        args.assume_yes,
    )
    time.sleep(args.settle_s)
    print("Step 1: capture after A")
    dump_flash(
        out_path=dump1,
        vid=args.vid,
        pid=args.pid,
        start=args.start,
        size=args.size,
        chunk=args.chunk,
    )

    _prompt(
        "\nNow in HFD: upload profile B with IDENTICAL coefficients, filename only changed.\n"
        f"Target filename B: {args.name_b}\n"
        "Press Enter when upload is complete and device is stable... ",
        args.assume_yes,
    )
    time.sleep(args.settle_s)
    print("Step 2: capture after B")
    dump_flash(
        out_path=dump2,
        vid=args.vid,
        pid=args.pid,
        start=args.start,
        size=args.size,
        chunk=args.chunk,
    )

    a0 = analyze_bytes(dump0.read_bytes(), dump1.read_bytes(), start_addr=args.start)
    a1 = analyze_bytes(dump1.read_bytes(), dump2.read_bytes(), start_addr=args.start)
    a2 = analyze_bytes(dump0.read_bytes(), dump2.read_bytes(), start_addr=args.start)

    report0 = out_dir / "report_01_baseline_to_A.md"
    report1 = out_dir / "report_02_A_to_B.md"
    report2 = out_dir / "report_03_baseline_to_B.md"
    json0 = out_dir / "report_01_baseline_to_A.json"
    json1 = out_dir / "report_02_A_to_B.json"
    json2 = out_dir / "report_03_baseline_to_B.json"

    write_markdown_report(
        out_path=report0,
        label=f"baseline -> A ({args.name_a})",
        before_path=dump0,
        after_path=dump1,
        analysis=a0,
        max_ranges=args.max_ranges,
        max_entries=args.max_entries,
    )
    write_markdown_report(
        out_path=report1,
        label=f"A ({args.name_a}) -> B ({args.name_b})",
        before_path=dump1,
        after_path=dump2,
        analysis=a1,
        max_ranges=args.max_ranges,
        max_entries=args.max_entries,
    )
    write_markdown_report(
        out_path=report2,
        label=f"baseline -> B ({args.name_b})",
        before_path=dump0,
        after_path=dump2,
        analysis=a2,
        max_ranges=args.max_ranges,
        max_entries=args.max_entries,
    )
    json0.write_text(json.dumps(_analysis_to_json_dict(a0), indent=2, sort_keys=True), encoding="ascii")
    json1.write_text(json.dumps(_analysis_to_json_dict(a1), indent=2, sort_keys=True), encoding="ascii")
    json2.write_text(json.dumps(_analysis_to_json_dict(a2), indent=2, sort_keys=True), encoding="ascii")

    print("\nCompleted A/B probe.")
    print(f"- output dir: {out_dir}")
    print(f"- baseline->A changed bytes: {a0.total_changed}")
    print(f"- A->B changed bytes: {a1.total_changed}")
    print(f"- baseline->B changed bytes: {a2.total_changed}")
    print(f"- A->B inference: {a1.inference}")
    print("- reports:")
    print(f"  - {report0}")
    print(f"  - {report1}")
    print(f"  - {report2}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_cap = sub.add_parser("capture", help="capture one flash snapshot via EP0 primitive")
    p_cap.add_argument("--vid", type=parse_int, default=VID_DEFAULT)
    p_cap.add_argument("--pid", type=parse_int, default=PID_DEFAULT)
    p_cap.add_argument("--start", type=parse_int, default=START_DEFAULT)
    p_cap.add_argument("--size", type=parse_int, default=SIZE_DEFAULT)
    p_cap.add_argument("--chunk", type=parse_int, default=CHUNK_DEFAULT)
    p_cap.add_argument("--out", type=pathlib.Path, required=True)

    p_an = sub.add_parser("analyze", help="analyze two existing dumps")
    p_an.add_argument("--before", type=pathlib.Path, required=True)
    p_an.add_argument("--after", type=pathlib.Path, required=True)
    p_an.add_argument("--start", type=parse_int, default=START_DEFAULT)
    p_an.add_argument("--label", default="A/B dump diff")
    p_an.add_argument("--report-out", type=pathlib.Path, default=None)
    p_an.add_argument("--json-out", type=pathlib.Path, default=None)
    p_an.add_argument("--max-ranges", type=int, default=128)
    p_an.add_argument("--max-entries", type=int, default=128)

    p_run = sub.add_parser(
        "run",
        help="interactive baseline->A->B capture and analysis workflow",
    )
    p_run.add_argument("--vid", type=parse_int, default=VID_DEFAULT)
    p_run.add_argument("--pid", type=parse_int, default=PID_DEFAULT)
    p_run.add_argument("--start", type=parse_int, default=START_DEFAULT)
    p_run.add_argument("--size", type=parse_int, default=SIZE_DEFAULT)
    p_run.add_argument("--chunk", type=parse_int, default=CHUNK_DEFAULT)
    p_run.add_argument("--name-a", default="profile_A")
    p_run.add_argument("--name-b", default="profile_B")
    p_run.add_argument("--session-tag", default="dsp_filename_ab")
    p_run.add_argument(
        "--out-dir",
        type=pathlib.Path,
        default=SIM_ARTIFACTS_DIR / "dsp_filename_ab_probe",
    )
    p_run.add_argument("--settle-s", type=float, default=1.5)
    p_run.add_argument("--assume-yes", action="store_true")
    p_run.add_argument("--max-ranges", type=int, default=128)
    p_run.add_argument("--max-entries", type=int, default=128)

    return ap


def main() -> int:
    ap = _build_parser()
    args = ap.parse_args()

    if args.cmd == "capture":
        return _cmd_capture(args)
    if args.cmd == "analyze":
        return _cmd_analyze(args)
    if args.cmd == "run":
        return _cmd_run(args)
    raise SystemExit(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
