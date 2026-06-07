"""RAM bank manifest helpers for source-assembled DLCP firmware.

The target assembly sources still carry many stock-derived RAM cells.  This
module turns the checked-in RAM include files into a bank-explicit manifest and
provides canonical aliases for source-level safety checks.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
import re

from dlcp_fw.paths import PROJECT_ROOT, V17_CONTROL_RAM_INC, V172_CONTROL_ASM, V33_MAIN_ASM


@dataclass(frozen=True)
class RamCell:
    target: str
    source_name: str
    alias: str
    phys: int
    bank: int
    operand: int
    access: str = "banked"
    owner: str = "stock-derived"
    alias_of: str | None = None
    strict_bsr: bool = True

    @property
    def phys_alias(self) -> str:
        return f"{self.alias}_phys"

    @property
    def op_alias(self) -> str:
        return f"{self.alias}_op"


@dataclass(frozen=True)
class TargetRamSpec:
    key: str
    asm_path: Path
    inc_path: Path
    mcu: str


MAIN_RAM_INC = V33_MAIN_ASM.parent / "dlcp_main_ram.inc"

TARGET_SPECS: dict[str, TargetRamSpec] = {
    "main-v33": TargetRamSpec(
        key="main-v33",
        asm_path=V33_MAIN_ASM,
        inc_path=MAIN_RAM_INC,
        mcu="pic18f2455",
    ),
    "control-v172": TargetRamSpec(
        key="control-v172",
        asm_path=V172_CONTROL_ASM,
        inc_path=V17_CONTROL_RAM_INC,
        mcu="pic18f25k20",
    ),
}

GENERATED_ALIAS_START = "; --- RAM bank safety generated aliases: BEGIN ---"
GENERATED_ALIAS_END = "; --- RAM bank safety generated aliases: END ---"

_EQU_RE = re.compile(r"^\s*(\w+)\s+(?:EQU|equ)\s+(\S+)\s*(?:;(.*))?$")
_RAW_RAM_RE = re.compile(r"^ram_0x([0-9A-Fa-f]{3})$")
_STOCK_ALIAS_RE = re.compile(r"^stock_([0-9A-Fa-f]{3})_b([0-9])$")
_STOCK_PHYS_ALIAS_RE = re.compile(r"^stock_([0-9A-Fa-f]{3})_b([0-9])_phys$")
_MOVLB_RE = re.compile(r"\bmovlb\s+0x([0-9A-Fa-f]+)\b", re.IGNORECASE)

_BANK_HINT_RE = re.compile(
    r"physical\s+0x([0-9A-Fa-f]{3})|\bBANK\s+([0-9])\b",
    re.IGNORECASE,
)

_F_OPERAND_MNEMONICS = (
    "movwf|movf|clrf|setf|"
    "addwf|addwfc|subfwb|subwf|subwfb|negf|"
    "btfsc|btfss|bsf|bcf|btg|"
    "cpfslt|cpfseq|cpfsgt|"
    "incf|incfsz|infsnz|decf|decfsz|dcfsnz|"
    "iorwf|andwf|xorwf|comf|"
    "rlcf|rlncf|rrcf|rrncf|swapf|"
    "tstfsz"
)
_SOURCE_FOP_RE = re.compile(
    rf"\b(?:{_F_OPERAND_MNEMONICS})\s+"
    rf"(?P<operand>[A-Za-z_]\w*|0x[0-9A-Fa-f]+)"
    rf"(?P<rest>[^;\n]*)",
    re.IGNORECASE,
)
_SOURCE_MOVFF_RE = re.compile(r"\bmovff\s+([^,\s;]+)\s*,\s*([^,\s;]+)", re.IGNORECASE)
_SOURCE_LFSR_RE = re.compile(r"\blfsr\s+[^,\s;]+\s*,\s*([^;\s]+)", re.IGNORECASE)
_SOURCE_LABEL_RE = re.compile(r"^\s*([A-Za-z_]\w*):.*$")

_EXPLICIT_SOURCE_RAM_NAMES: dict[str, set[str]] = {
    "main-v33": {
        "dsp_fault_flags",
        "i2c_recover_flags",
        "src4382_loss_debounce",
        "timeout_lo",
        "timeout_hi",
        "saved_w",
        "current_cmd_data",
        "filename_dirty_flags",
        "preset_hold_timer_lo",
        "preset_hold_timer_hi",
        "preset_job_state",
        "preset_job_target",
        "preset_job_index",
        "preset_job_delay",
        "preset_job_flags",
        "preset_job_tbl_lo",
        "preset_job_tbl_hi",
    },
    "control-v172": set(),
}

_EXPLICIT_STOCK_PHYS: dict[str, set[int]] = {
    "main-v33": {
        0x166,
        0x167,
        0x168,
        0x169,
        0x1A1,
        0x1A2,
        0x1A3,
        0x1C7,
    },
    "control-v172": {
        0x065,
        0x06D,
        0x06F,
        0x074,
        0x0AE,
        0x0AF,
    },
}


def project_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def parse_equates(path: Path) -> list[tuple[str, int | None, str, str, list[str]]]:
    """Parse numeric/symbolic EQU lines with inherited comment blocks."""
    out: list[tuple[str, int | None, str, str, list[str]]] = []
    comments: list[str] = []
    in_generated_alias_block = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.strip() == GENERATED_ALIAS_START:
            in_generated_alias_block = True
            continue
        if line.strip() == GENERATED_ALIAS_END:
            in_generated_alias_block = False
            continue
        if in_generated_alias_block:
            continue
        if not line.strip():
            comments.clear()
            continue
        if line.lstrip().startswith(";"):
            comments.append(line)
            continue
        match = _EQU_RE.match(line)
        if match is None:
            comments.clear()
            continue
        name = match.group(1)
        raw_value = match.group(2)
        own_comment = (match.group(3) or "").strip()
        value: int | None
        if raw_value.lower().startswith("0x"):
            try:
                value = int(raw_value, 16)
            except ValueError:
                value = None
        elif raw_value.isdigit():
            value = int(raw_value)
        else:
            value = None
        out.append((name, value, raw_value, own_comment, list(comments)))
    return out


def _is_ram_cell_name(name: str) -> bool:
    if name == "Common_RAM":
        return False
    if _RAW_RAM_RE.match(name):
        return True
    return bool(name) and name[0].islower()


def _is_constant_name(name: str) -> bool:
    return bool(name) and name.upper() == name


def _bank_from_comments(name: str, own_comment: str, block_comments: list[str]) -> int | None:
    if name.startswith(("v171_diag_", "v171_health_")):
        return 1
    if name.startswith("v171_diag_render_"):
        return 1
    if name.startswith("v172_"):
        return 2
    joined = own_comment + "\n" + "\n".join(block_comments)
    physical_match = re.search(r"physical\s+0x([0-9A-Fa-f]{3})", joined, re.IGNORECASE)
    if physical_match is not None:
        return int(physical_match.group(1), 16) >> 8
    bank_match = re.search(r"\bBANK\s+([0-9])\b", joined, re.IGNORECASE)
    if bank_match is not None:
        return int(bank_match.group(1))
    return None


def _semantic_stock_alias(phys: int, bank: int, access: str) -> str | None:
    if phys == 0x0A1:
        return "an0_delay_acc" if access == "access" else "an0_delay_b0"
    return None


def _alias_for(name: str, bank: int, access: str) -> str:
    raw = _RAW_RAM_RE.match(name)
    if raw is not None:
        semantic = _semantic_stock_alias(int(raw.group(1), 16), bank, access)
        if semantic is not None:
            return semantic
        if access == "access":
            return f"stock_{raw.group(1).upper()}_acc"
        return f"stock_{raw.group(1).upper()}_b{bank}"
    if access == "access":
        return f"{name}_acc"
    return f"{name}_b{bank}"


def _is_table_data_line_mask(lines: list[str]) -> list[bool]:
    mask = [False] * len(lines)
    in_table = False
    for idx, line in enumerate(lines):
        body = line.split(";", 1)[0].strip()
        label_match = _SOURCE_LABEL_RE.match(body)
        if label_match:
            label = label_match.group(1)
            in_table = "tblptr anchor" in line.lower() or label.endswith("_table")
            continue
        if in_table:
            mask[idx] = True
    return mask


def _line_bsr_before(lines: list[str], index: int, *, max_scan: int = 160) -> int | None:
    for cursor in range(index - 1, max(-1, index - max_scan - 1), -1):
        body = lines[cursor].split(";", 1)[0].strip()
        if not body:
            continue
        if re.search(r"\b(?:call|rcall)\b", body, re.IGNORECASE):
            return None
        match = _MOVLB_RE.search(body)
        if match is not None:
            return int(match.group(1), 16)
    return None


def _comment_phys_hint(line: str) -> int | None:
    comment = line.split(";", 1)[1] if ";" in line else ""
    match = re.search(r"\breg:\s*0x([0-9A-Fa-f]{3})\b", comment)
    if match is not None:
        return int(match.group(1), 16)
    return None


def _source_equate_values(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    for name, value, _raw, _comment, _block in parse_equates(path):
        if value is not None:
            out[name] = value
    return out


def _source_inferred_stock_cells(target: str, known_names: set[str]) -> set[int]:
    spec = TARGET_SPECS[target]
    lines = spec.asm_path.read_text(encoding="utf-8").splitlines()
    table_mask = _is_table_data_line_mask(lines)
    phys_values: set[int] = set()

    def add_phys(phys: int) -> None:
        if 0 <= phys < 0xF00:
            phys_values.add(phys)

    for idx, line in enumerate(lines):
        if table_mask[idx]:
            continue
        body = line.split(";", 1)[0]
        hint = _comment_phys_hint(line)
        for movff in _SOURCE_MOVFF_RE.finditer(body):
            for operand in movff.groups():
                raw = re.match(r"^0x([0-9A-Fa-f]{2,3})$", operand.strip())
                if raw is not None and hint is not None:
                    add_phys(hint)
                stock_phys = _STOCK_PHYS_ALIAS_RE.match(operand.strip())
                if stock_phys is not None:
                    add_phys(int(stock_phys.group(1), 16))
        lfsr = _SOURCE_LFSR_RE.search(body)
        if lfsr is not None:
            operand = lfsr.group(1).strip()
            raw = re.match(r"^0x([0-9A-Fa-f]{2,3})$", operand)
            if raw is not None:
                add_phys(int(raw.group(1), 16))
        fop = _SOURCE_FOP_RE.search(body)
        if fop is None:
            continue
        operand = fop.group("operand")
        rest = fop.group("rest")
        is_banked = re.search(r",\s*(?:BANKED|B)\b", rest, re.IGNORECASE) is not None
        is_access = re.search(r",\s*(?:ACCESS|A)\b", rest, re.IGNORECASE) is not None
        if not (is_banked or is_access):
            continue
        if operand in known_names and _STOCK_ALIAS_RE.match(operand) is None:
            continue
        raw_literal = re.match(r"^0x([0-9A-Fa-f]{2,3})$", operand)
        if raw_literal is not None:
            literal = int(raw_literal.group(1), 16)
            if hint is not None:
                add_phys(hint)
            elif is_banked:
                bsr = _line_bsr_before(lines, idx)
                add_phys(((bsr or 0) << 8) | literal)
            elif literal > 0x5F:
                add_phys(literal)
            continue
        raw_ram = _RAW_RAM_RE.match(operand)
        if raw_ram is not None and is_banked:
            literal = int(raw_ram.group(1), 16) & 0xFF
            bsr = _line_bsr_before(lines, idx)
            add_phys(((bsr if bsr is not None else int(raw_ram.group(1), 16) >> 8) << 8) | literal)
            continue
        stock = _STOCK_ALIAS_RE.match(operand)
        if stock is not None and is_banked:
            literal = int(stock.group(1), 16) & 0xFF
            encoded_bank = int(stock.group(2))
            bsr = _line_bsr_before(lines, idx)
            add_phys(((bsr if bsr is not None else encoded_bank) << 8) | literal)
    return phys_values


@lru_cache(maxsize=None)
def load_manifest(target: str) -> dict[str, RamCell]:
    spec = TARGET_SPECS[target]
    cells: dict[str, RamCell] = {}

    def add_family(cell: RamCell) -> None:
        if cell.alias in cells:
            return
        cells[cell.alias] = cell
        cells[cell.op_alias] = replace(cell, alias=cell.op_alias, alias_of=cell.alias)
        cells[cell.phys_alias] = replace(cell, alias=cell.phys_alias, alias_of=cell.alias)

    def make_cell(
        *,
        source_name: str,
        phys: int,
        access: str = "banked",
        owner: str,
    ) -> RamCell:
        bank = phys >> 8
        alias = _alias_for(source_name, bank, access)
        return RamCell(
            target=target,
            source_name=source_name,
            alias=alias,
            phys=phys,
            bank=bank,
            operand=phys & 0xFF,
            access=access,
            owner=owner,
            strict_bsr=(
                access == "banked"
                and (bank != 0 or alias == "an0_delay_b0")
            ),
        )

    for name, value, raw_value, own_comment, block_comments in parse_equates(spec.inc_path):
        if _is_constant_name(name) or not _is_ram_cell_name(name):
            continue
        if value is None:
            continue
        raw_match = _RAW_RAM_RE.match(name)
        if raw_match is not None:
            phys = int(raw_match.group(1), 16)
            bank = phys >> 8
        else:
            hinted_bank = _bank_from_comments(name, own_comment, block_comments)
            if value >= 0x100:
                phys = value
                bank = phys >> 8
            elif hinted_bank is not None:
                bank = hinted_bank
                phys = (bank << 8) | value
            else:
                bank = 0
                phys = value
        if phys >= 0xF00:
            continue
        owner = "stock-derived" if raw_match is not None else name
        cell = make_cell(
            source_name=name,
            phys=phys,
            access="banked",
            owner=owner,
        )
        add_family(cell)
        if phys <= 0x5F:
            add_family(
                make_cell(
                    source_name=name,
                    phys=phys,
                    access="access",
                    owner=owner,
                )
            )

    source_equates = _source_equate_values(spec.asm_path)
    for name in sorted(_EXPLICIT_SOURCE_RAM_NAMES[target]):
        phys = source_equates.get(name)
        if phys is None:
            continue
        if phys >= 0xF00:
            continue
        add_family(make_cell(source_name=name, phys=phys, access="banked", owner=name))
        if phys <= 0x5F:
            add_family(make_cell(source_name=name, phys=phys, access="access", owner=name))

    known_names = {cell.alias for cell in cells.values()} | {
        cell.source_name for cell in cells.values()
    }
    for phys in sorted(_source_inferred_stock_cells(target, known_names) | _EXPLICIT_STOCK_PHYS[target]):
        add_family(
            make_cell(
                source_name=f"ram_0x{phys:03X}",
                phys=phys,
                access="banked",
                owner="stock-derived",
            )
        )
        if phys <= 0x5F:
            add_family(
                make_cell(
                    source_name=f"ram_0x{phys:03X}",
                    phys=phys,
                    access="access",
                    owner="stock-derived",
                )
            )
    return cells


def clear_manifest_cache() -> None:
    load_manifest.cache_clear()


def cells_by_source_name(target: str) -> dict[str, RamCell]:
    out: dict[str, RamCell] = {}
    for cell in load_manifest(target).values():
        if cell.alias_of is None and cell.access == "banked":
            out[cell.source_name] = cell
    return out


def alias_equate_lines(target: str) -> list[str]:
    """Return the generated alias block for *target*."""
    cells = load_manifest(target)
    primary = [
        cell
        for name, cell in cells.items()
        if cell.alias_of is None
    ]
    primary.sort(key=lambda c: (c.phys, c.alias))
    lines = [
        GENERATED_ALIAS_START,
        "; Generated from ram_bank_manifest.py.  Do not hand-edit this block.",
    ]
    for cell in primary:
        lines.append(
            f"{cell.alias:<32} EQU  0x{cell.phys:03X}    ; "
            f"phys 0x{cell.phys:03X}, bank {cell.bank}, owner {cell.owner}"
        )
        lines.append(
            f"{cell.op_alias:<32} EQU  0x{cell.operand:02X}     ; 8-bit f operand for {cell.alias}"
        )
        lines.append(
            f"{cell.phys_alias:<32} EQU  0x{cell.phys:03X}    ; physical address for movff/lfsr"
        )
    lines.append(GENERATED_ALIAS_END)
    return lines


def expected_alias_block(target: str) -> str:
    return "\n".join(alias_equate_lines(target)) + "\n"
