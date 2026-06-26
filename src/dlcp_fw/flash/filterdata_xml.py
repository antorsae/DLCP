#!/usr/bin/env python3
"""Build a DLCP HFD preset table from a Hypex FilterData ``Config.xml``.

The output is the raw 0x0A00-byte table captured by ``dlcp_read_coeffs.py`` and
accepted by ``dlcp_hfd_upload.py``.
"""

from __future__ import annotations

import argparse
import cmath
import hashlib
import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Sequence


getcontext().prec = 50

TABLE_SIZE = 0x0A00
SLOT_SIZE = 0x18
SLOT_PAYLOAD_SIZE = 0x14
CHANNEL_COUNT = 6
BIQUADS_PER_CHANNEL = 15
BIQUAD_REG_BASE = 0x37
CHANNEL_CONFIG_REG_BASE = 0xC8
GAIN_REG_FIRST = 0x31
GAIN_REG_LAST = 0x36
COEFF_SCALE = Decimal(1 << 23)
COEFF_MODULO = 1 << 28
HFD_MATCH_FREQUENCY_HZ = 2000.0
MAX_FILTERDATA_XML_BYTES = 2_000_000
MAX_FILTERDATA_XML_ELEMENTS = 5000
MAX_PROCESSOBJ_COUNT = 256
MIN_SAMPLE_RATE_HZ = Decimal(8000)
MAX_SAMPLE_RATE_HZ = Decimal(384000)
MIN_Q = Decimal("0")
MAX_Q = Decimal("100")
MIN_GAIN_DB = Decimal("-144")
MAX_GAIN_DB = Decimal("48")
MIN_DELAY_MS = Decimal("0")
MAX_DELAY_MS = Decimal("2550")
MIN_COEFF = Decimal("-16")
MAX_COEFF = Decimal("16")


@dataclass(frozen=True)
class Biquad:
    group_id: int
    index: int
    enabled: bool
    filter_type: str
    f1: Decimal
    gain: Decimal
    q1: Decimal
    zconst: Decimal
    shelf_hl: str
    b0: Decimal
    b1: Decimal
    b2: Decimal
    a1: Decimal
    a2: Decimal


@dataclass(frozen=True)
class FilterDataProject:
    path: Path
    proc_sampling_rate: Decimal
    gains_db: dict[int, Decimal]
    delays: dict[int, Decimal]
    biquads: dict[int, list[Biquad]]


def _decimal_attr(node: ET.Element, name: str = "value") -> Decimal:
    try:
        value = Decimal(node.attrib[name])
    except (KeyError, InvalidOperation) as exc:
        raise RuntimeError(f"invalid decimal attribute {name!r} on {node.tag}") from exc
    if not value.is_finite():
        raise RuntimeError(f"non-finite decimal attribute {name!r} on {node.tag}")
    return value


def _child_decimal(node: ET.Element, tag: str) -> Decimal:
    child = node.find(tag)
    if child is None:
        raise RuntimeError(f"missing <{tag}> under processobj {node.attrib!r}")
    return _decimal_attr(child)


def _process_group_id(node: ET.Element) -> int | None:
    raw = node.attrib.get("groupid")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _biquad_index(node: ET.Element) -> int:
    title = node.attrib.get("title", "")
    match = re.fullmatch(r"BQ\s+(\d+)", title)
    if match is None:
        raise RuntimeError(f"cannot parse biquad title {title!r}")
    return int(match.group(1))


def _read_xml_bytes(path: Path) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise RuntimeError(f"{path}: cannot stat XML input: {exc}") from exc
    if size > MAX_FILTERDATA_XML_BYTES:
        raise RuntimeError(
            f"{path}: XML input is {size} bytes, max {MAX_FILTERDATA_XML_BYTES}"
        )
    data = path.read_bytes()
    lowered = data.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise RuntimeError(f"{path}: DTD/entity declarations are not supported")
    return data


def _parse_xml_root(path: Path) -> ET.Element:
    try:
        root = ET.fromstring(_read_xml_bytes(path))
    except ET.ParseError as exc:
        raise RuntimeError(f"{path}: invalid XML: {exc}") from exc
    element_count = sum(1 for _ in root.iter())
    if element_count > MAX_FILTERDATA_XML_ELEMENTS:
        raise RuntimeError(
            f"{path}: XML has {element_count} elements, max {MAX_FILTERDATA_XML_ELEMENTS}"
        )
    process_count = len(root.findall(".//processobj"))
    if process_count > MAX_PROCESSOBJ_COUNT:
        raise RuntimeError(
            f"{path}: XML has {process_count} processobj nodes, max {MAX_PROCESSOBJ_COUNT}"
        )
    return root


def _require_range(value: Decimal, *, name: str, lo: Decimal, hi: Decimal) -> None:
    if not (lo <= value <= hi):
        raise RuntimeError(f"{name} {value} outside range {lo}..{hi}")


def _validate_project(project: FilterDataProject) -> None:
    fs = project.proc_sampling_rate
    _require_range(
        fs,
        name="sample rate",
        lo=MIN_SAMPLE_RATE_HZ,
        hi=MAX_SAMPLE_RATE_HZ,
    )
    nyquist = fs / Decimal(2)
    for group_id in range(1, CHANNEL_COUNT + 1):
        if group_id in project.gains_db:
            _require_range(
                project.gains_db[group_id],
                name=f"group {group_id} gain",
                lo=MIN_GAIN_DB,
                hi=MAX_GAIN_DB,
            )
        if group_id in project.delays:
            _require_range(
                project.delays[group_id],
                name=f"group {group_id} delay",
                lo=MIN_DELAY_MS,
                hi=MAX_DELAY_MS,
            )
        for row in project.biquads[group_id]:
            if not (Decimal(0) < row.f1 < nyquist):
                raise RuntimeError(
                    f"group {group_id} BQ {row.index} frequency {row.f1} "
                    f"outside range 0..Nyquist ({nyquist})"
                )
            _require_range(
                row.q1,
                name=f"group {group_id} BQ {row.index} Q",
                lo=MIN_Q,
                hi=MAX_Q,
            )
            if row.q1 == 0:
                raise RuntimeError(f"group {group_id} BQ {row.index} Q must be > 0")
            _require_range(
                row.gain,
                name=f"group {group_id} BQ {row.index} gain",
                lo=MIN_GAIN_DB,
                hi=MAX_GAIN_DB,
            )
            for coeff_name, coeff in (
                ("b0", row.b0),
                ("b1", row.b1),
                ("b2", row.b2),
                ("a1", row.a1),
                ("a2", row.a2),
            ):
                if not (MIN_COEFF <= coeff < MAX_COEFF):
                    raise RuntimeError(
                        f"group {group_id} BQ {row.index} {coeff_name} "
                        f"{coeff} outside range {MIN_COEFF}..<{MAX_COEFF}"
                    )


def parse_filterdata_xml(path: Path) -> FilterDataProject:
    root = _parse_xml_root(path)
    device = root.find(".//device")
    if device is None or "procsamplingrate" not in device.attrib:
        raise RuntimeError(f"{path}: missing device procsamplingrate")

    gains_db: dict[int, Decimal] = {}
    delays: dict[int, Decimal] = {}
    biquads: dict[int, list[Biquad]] = {
        gid: [] for gid in range(1, CHANNEL_COUNT + 1)
    }

    for process in root.findall(".//processobj"):
        process_type = process.attrib.get("processtype")
        group_id = _process_group_id(process)
        if group_id is None or not (1 <= group_id <= CHANNEL_COUNT):
            continue

        if process_type == "ptGain":
            gain = process.find("gain")
            if gain is None:
                raise RuntimeError(f"missing <gain> under processobj {process.attrib!r}")
            gains_db[group_id] = _decimal_attr(gain)
        elif process_type == "ptDelay":
            delay = process.find("delay")
            if delay is None:
                raise RuntimeError(f"missing <delay> under processobj {process.attrib!r}")
            delays[group_id] = _decimal_attr(delay)
        elif process_type == "ptBiQuad":
            filter_type_node = process.find("filtertype")
            filter_type = (
                filter_type_node.attrib.get("value", "")
                if filter_type_node is not None
                else ""
            )
            shelf_hl_node = process.find("shelfhl")
            biquads[group_id].append(
                Biquad(
                    group_id=group_id,
                    index=_biquad_index(process),
                    enabled=process.attrib.get("enabled") == "true",
                    filter_type=filter_type,
                    f1=_child_decimal(process, "f1"),
                    gain=_child_decimal(process, "gain"),
                    q1=_child_decimal(process, "q1"),
                    zconst=_child_decimal(process, "zconst"),
                    shelf_hl=(
                        shelf_hl_node.attrib.get("value", "")
                        if shelf_hl_node is not None
                        else ""
                    ),
                    b0=_child_decimal(process, "b0"),
                    b1=_child_decimal(process, "b1"),
                    b2=_child_decimal(process, "b2"),
                    a1=_child_decimal(process, "a1"),
                    a2=_child_decimal(process, "a2"),
                )
            )

    for group_id, rows in biquads.items():
        rows.sort(key=lambda row: row.index)
        if len(rows) != BIQUADS_PER_CHANNEL:
            raise RuntimeError(
                f"{path}: group {group_id} has {len(rows)} biquads, "
                f"expected {BIQUADS_PER_CHANNEL}"
            )
        expected = list(range(1, BIQUADS_PER_CHANNEL + 1))
        got = [row.index for row in rows]
        if got != expected:
            raise RuntimeError(f"{path}: group {group_id} biquad order {got!r}")

    project = FilterDataProject(
        path=path,
        proc_sampling_rate=_decimal_attr(device, "procsamplingrate"),
        gains_db=gains_db,
        delays=delays,
        biquads=biquads,
    )
    _validate_project(project)
    return project


def detect_coefficient_mode(project: FilterDataProject) -> str:
    """Return ``direct`` or ``legacy`` for the XML coefficient convention.

    Newer HFD exports store coefficients in the same sign/gain convention used
    by the DLCP upload stream. Older files store textbook biquad denominator
    signs and leave per-channel gain in the ptGain object.
    """

    direct = 0
    legacy = 0
    for rows in project.biquads.values():
        for row in rows:
            if row.a1 == 0 and row.a2 == 0:
                continue
            if row.a1 >= 0 and row.a2 <= 0:
                direct += 1
            elif row.a1 <= 0 and row.a2 >= 0:
                legacy += 1
    return "direct" if direct >= legacy else "legacy"


def _encode_coeff(value: Decimal) -> bytes:
    scaled = int((value * COEFF_SCALE).to_integral_value(rounding=ROUND_HALF_UP))
    raw = scaled % COEFF_MODULO
    return raw.to_bytes(4, "big")


def _gain_linear(gain_db: Decimal) -> Decimal:
    return Decimal(10) ** (gain_db / Decimal(20))


def _delay_code(delay: Decimal) -> int:
    _require_range(delay, name="delay", lo=MIN_DELAY_MS, hi=MAX_DELAY_MS)
    return int(delay / Decimal(10))


def _row(header_reg: int, payload: bytes) -> bytes:
    if len(payload) > SLOT_PAYLOAD_SIZE:
        raise RuntimeError(f"payload for reg 0x{header_reg:02X} is too long")
    return (
        bytes([0x01, header_reg & 0xFF, len(payload), 0x00])
        + payload
        + bytes(SLOT_PAYLOAD_SIZE - len(payload))
    )


def _coefficient_values(
    row: Biquad,
    *,
    mode: str,
    is_first_biquad: bool,
    gain_linear: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    b0 = row.b0
    b1 = row.b1
    b2 = row.b2
    a1 = row.a1
    a2 = row.a2

    if mode == "legacy":
        if is_first_biquad:
            b0 *= gain_linear
            b1 *= gain_linear
            b2 *= gain_linear
        a1 = -a1
        a2 = -a2
    elif mode != "direct":
        raise ValueError(f"unknown coefficient mode {mode!r}")

    return b0, b1, b2, a1, a2


def _hfd_s_pair(frequency: float, q: float) -> tuple[complex, complex]:
    omega = 2.0 * math.pi * frequency
    if math.isclose(q, 0.5, rel_tol=0.0, abs_tol=1e-15):
        root = complex(-omega)
        return root, root
    if q > 0.5:
        real = -omega / (2.0 * q)
        imag = omega * math.sqrt(1.0 - (1.0 / (4.0 * q * q)))
        return complex(real, imag), complex(real, -imag)

    split = math.sqrt((1.0 / (4.0 * q * q)) - 1.0)
    slow = -omega * ((1.0 / (2.0 * q)) - split)
    fast = -omega * ((1.0 / (2.0 * q)) + split)
    return complex(slow), complex(fast)


def _hfd_s_domain_filter(
    row: Biquad,
) -> tuple[list[complex], list[complex], float]:
    frequency = float(row.f1)
    q = float(row.q1)
    gain_db = float(row.gain)

    if (not row.enabled) or row.filter_type == "ftUnity":
        return [], [], 1.0
    if row.filter_type == "ftHighPass2":
        return [0j, 0j], list(_hfd_s_pair(frequency, q)), 1.0
    if row.filter_type == "ftLowPass2":
        return (
            [],
            list(_hfd_s_pair(frequency, q)),
            (2.0 * math.pi * frequency) ** 2,
        )
    if row.filter_type == "ftAllPass2":
        poles = list(_hfd_s_pair(frequency, q))
        return [-pole for pole in poles], poles, 1.0
    if row.filter_type == "ftBoostCut":
        gain_abs = 10.0 ** (abs(gain_db) / 20.0)
        if gain_db >= 0.0:
            pole_frequency, pole_q = frequency, q
            zero_frequency, zero_q = frequency, q / gain_abs
        else:
            pole_frequency, pole_q = frequency, q / gain_abs
            zero_frequency, zero_q = frequency, q
        return (
            list(_hfd_s_pair(zero_frequency, zero_q)),
            list(_hfd_s_pair(pole_frequency, pole_q)),
            1.0,
        )
    if row.filter_type == "ftShelf2":
        factor = 10.0 ** (abs(gain_db) / 80.0)
        if row.shelf_hl == "stLowShelf":
            if gain_db >= 0.0:
                pole_frequency = frequency / factor
                zero_frequency = frequency * factor
            else:
                pole_frequency = frequency * factor
                zero_frequency = frequency / factor
            sconst = 1.0
        elif row.shelf_hl == "stHighShelf":
            if gain_db >= 0.0:
                pole_frequency = frequency * factor
                zero_frequency = frequency / factor
            else:
                pole_frequency = frequency / factor
                zero_frequency = frequency * factor
            sconst = 10.0 ** (gain_db / 20.0)
        else:
            raise RuntimeError(
                f"unsupported HFD shelf type {row.shelf_hl!r} "
                f"for group {row.group_id} BQ {row.index}"
            )
        return (
            list(_hfd_s_pair(zero_frequency, q)),
            list(_hfd_s_pair(pole_frequency, q)),
            sconst,
        )

    raise RuntimeError(
        f"unsupported HFD semantic filter {row.filter_type!r} "
        f"for group {row.group_id} BQ {row.index}"
    )


def _hfd_response(
    point: complex,
    zeros: list[complex],
    poles: list[complex],
    constant: float,
) -> complex:
    value = complex(constant)
    for zero in zeros:
        value *= point - zero
    for pole in poles:
        value /= point - pole
    return value


def _hfd_z_domain_filter(
    row: Biquad,
    *,
    sample_rate: float,
) -> tuple[list[complex], list[complex], float]:
    zeros, poles, sconst = _hfd_s_domain_filter(row)
    zconst = sconst * (sample_rate ** (len(zeros) - len(poles)))
    zzeros = [cmath.exp(zero / sample_rate) for zero in zeros]
    zpoles = [cmath.exp(pole / sample_rate) for pole in poles]

    while len(zzeros) < 2:
        zzeros.append(0j)
    while len(zpoles) < 2:
        zpoles.append(0j)

    s_point = 1j * 2.0 * math.pi * HFD_MATCH_FREQUENCY_HZ
    z_point = cmath.exp(
        1j * 2.0 * math.pi * HFD_MATCH_FREQUENCY_HZ / sample_rate
    )
    analog_response = _hfd_response(s_point, zeros, poles, sconst)
    digital_response = _hfd_response(z_point, zzeros, zpoles, zconst)
    zconst *= abs(analog_response / digital_response)
    return zzeros, zpoles, zconst


def _hfd_pz_values(
    row: Biquad,
    *,
    sample_rate: float,
    is_first_biquad: bool,
    gain_linear: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    zzeros, zpoles, zconst = _hfd_z_domain_filter(row, sample_rate=sample_rate)

    if (not row.enabled) or row.filter_type == "ftUnity":
        values = [zconst, 0.0, 0.0, 0.0, 0.0]
    else:
        zero_sum = (zzeros[0] + zzeros[1]).real
        zero_product = (zzeros[0] * zzeros[1]).real
        pole_sum = (zpoles[0] + zpoles[1]).real
        pole_product = (zpoles[0] * zpoles[1]).real
        values = [
            zconst,
            -zconst * zero_sum,
            zconst * zero_product,
            pole_sum,
            -pole_product,
        ]

    if is_first_biquad:
        gain = float(gain_linear)
        values[0] *= gain
        values[1] *= gain
        values[2] *= gain

    return (
        Decimal(str(values[0])),
        Decimal(str(values[1])),
        Decimal(str(values[2])),
        Decimal(str(values[3])),
        Decimal(str(values[4])),
    )

def build_preset_table_from_project(
    project: FilterDataProject,
    *,
    mode: str = "auto",
) -> bytes:
    if mode == "auto":
        mode = detect_coefficient_mode(project)
    if mode not in {"direct", "legacy", "hfd-pz"}:
        raise ValueError(
            f"mode must be auto, direct, legacy, or hfd-pz, got {mode!r}"
        )

    out = bytearray()
    for group_id in range(1, CHANNEL_COUNT + 1):
        delay = project.delays.get(group_id, Decimal(0))
        out += _row(
            CHANNEL_CONFIG_REG_BASE + group_id - 1,
            bytes([0x00, _delay_code(delay) & 0xFF, 0x00, 0x00]),
        )

        gain = _gain_linear(project.gains_db.get(group_id, Decimal(0)))
        for index, biquad in enumerate(project.biquads[group_id], start=1):
            if mode == "hfd-pz":
                values = _hfd_pz_values(
                    biquad,
                    sample_rate=float(project.proc_sampling_rate),
                    is_first_biquad=(index == 1),
                    gain_linear=gain,
                )
            else:
                values = _coefficient_values(
                    biquad,
                    mode=mode,
                    is_first_biquad=(index == 1),
                    gain_linear=gain,
                )
            payload = b"".join(_encode_coeff(value) for value in values)
            reg = (
                BIQUAD_REG_BASE
                + ((group_id - 1) * BIQUADS_PER_CHANNEL)
                + index
                - 1
            )
            out += _row(reg, payload)

    out += bytes([0x01, 0xD4, 0x04, 0x00, 0x00, 0x00, 0x00, 0x01])
    for reg in range(GAIN_REG_FIRST, GAIN_REG_LAST + 1):
        out += bytes([0x01, reg, 0x10, 0x00]) + bytes(16)
        out += (
            bytes([0x01, reg, 0x10, 0x00])
            + bytes.fromhex("00800000")
            + bytes(12)
        )

    if len(out) > TABLE_SIZE:
        raise RuntimeError(
            f"generated table is {len(out)} bytes, expected <= {TABLE_SIZE}"
        )
    out += b"\xFF" * (TABLE_SIZE - len(out))
    return bytes(out)


def build_preset_table(xml_path: Path, *, mode: str = "auto") -> bytes:
    return build_preset_table_from_project(parse_filterdata_xml(xml_path), mode=mode)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def first_diff(got: bytes, expected: bytes) -> tuple[int, int | None, int | None] | None:
    limit = min(len(got), len(expected))
    for idx in range(limit):
        if got[idx] != expected[idx]:
            return idx, got[idx], expected[idx]
    if len(got) != len(expected):
        got_byte = got[limit] if limit < len(got) else None
        expected_byte = expected[limit] if limit < len(expected) else None
        return limit, got_byte, expected_byte
    return None


def _count_diffs(got: bytes, expected: bytes) -> int:
    return sum(a != b for a, b in zip(got, expected)) + abs(
        len(got) - len(expected)
    )


def _print_sources(root: Path) -> None:
    for xml in sorted(root.glob("*/Config.xml")):
        print(xml)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a DLCP 0x0A00 preset table from Hypex FilterData Config.xml"
        ),
    )
    parser.add_argument("xml", nargs="?", type=Path, help="FilterData Config.xml")
    parser.add_argument("-o", "--output", type=Path, help="write generated .bin here")
    parser.add_argument("--stdout", action="store_true", help="write binary table to stdout")
    parser.add_argument("--verify", type=Path, help="byte-compare generated table to a .bin")
    parser.add_argument(
        "--mode",
        choices=("auto", "direct", "legacy", "hfd-pz"),
        default="auto",
        help=(
            "coefficient convention; hfd-pz ignores b0/b1/b2/a1/a2 and "
            "rebuilds them from HFD pole/zero fields (default: auto)"
        ),
    )
    parser.add_argument(
        "--list-sources",
        type=Path,
        metavar="DIR",
        help="list */Config.xml files under a FilterData directory and exit",
    )
    args = parser.parse_args(argv)

    if args.list_sources is not None:
        _print_sources(args.list_sources)
        return 0

    if args.xml is None:
        parser.error("xml is required unless --list-sources is used")
    if args.stdout and args.output is not None:
        parser.error("--stdout and --output are mutually exclusive")

    project = parse_filterdata_xml(args.xml)
    resolved_mode = detect_coefficient_mode(project) if args.mode == "auto" else args.mode
    table = build_preset_table_from_project(project, mode=resolved_mode)
    info = sys.stderr if args.stdout else sys.stdout

    if args.stdout:
        sys.stdout.buffer.write(table)
    elif args.output is not None:
        args.output.write_bytes(table)

    print(f"source: {args.xml}", file=info)
    print(f"mode: {resolved_mode}", file=info)
    print(
        f"generated: {len(table)} bytes sha256={sha256_hex(table)}",
        file=info,
    )
    if args.output is not None:
        print(f"wrote: {args.output}", file=info)

    if args.verify is None:
        return 0

    expected = args.verify.read_bytes()
    diff = first_diff(table, expected)
    if diff is None:
        print(f"verify: MATCH {args.verify}", file=info)
        return 0

    idx, got, exp = diff
    got_text = "<eof>" if got is None else f"0x{got:02X}"
    exp_text = "<eof>" if exp is None else f"0x{exp:02X}"
    print(
        f"verify: MISMATCH {args.verify} first_diff=0x{idx:04X} "
        f"generated={got_text} expected={exp_text} "
        f"diff_bytes={_count_diffs(table, expected)}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
