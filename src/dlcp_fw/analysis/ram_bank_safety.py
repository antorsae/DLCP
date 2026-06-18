"""Static RAM bank-safety checks for source-assembled DLCP firmware."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from dlcp_fw.asm.ram_bank_manifest import (
    GENERATED_ALIAS_END,
    GENERATED_ALIAS_START,
    RamCell,
    TARGET_SPECS,
    alias_equate_lines,
    cells_by_source_name,
    clear_manifest_cache,
    expected_alias_block,
    load_manifest,
    project_relative,
)


F_OPERAND_MNEMONICS = (
    "movwf|movf|clrf|setf|"
    "addwf|addwfc|subfwb|subwf|subwfb|negf|"
    "btfsc|btfss|bsf|bcf|btg|"
    "cpfslt|cpfseq|cpfsgt|"
    "incf|incfsz|infsnz|decf|decfsz|dcfsnz|"
    "iorwf|andwf|xorwf|comf|"
    "rlcf|rlncf|rrcf|rrncf|swapf|"
    "tstfsz"
)

F_OPERAND_RE = re.compile(
    rf"\b(?P<mnemonic>{F_OPERAND_MNEMONICS})\s+"
    rf"(?P<operand>[A-Za-z_]\w*|0x[0-9A-Fa-f]+)"
    rf"(?P<rest>[^;\n]*)",
    re.IGNORECASE,
)
MOVLB_RE = re.compile(r"\bmovlb\s+0x([0-9A-Fa-f]+)\b", re.IGNORECASE)
LABEL_RE = re.compile(r"^([A-Za-z_]\w*):\s*$")
LABEL_PREFIX_RE = re.compile(r"^\s*([A-Za-z_]\w*):\s*(.*)$")
CALL_RE = re.compile(r"\b(?:call|rcall)\s+([A-Za-z_]\w*)\b", re.IGNORECASE)
BRANCH_RE = re.compile(
    r"\b(?:bra|goto|bz|bnz|bc|bnc|bn|bnn|bov|bnov)\s+([A-Za-z_]\w*)\b",
    re.IGNORECASE,
)
MOVFF_RE = re.compile(r"\bmovff\s+([^,\s;]+)\s*,\s*([^,\s;]+)", re.IGNORECASE)
LFSR_RE = re.compile(r"\blfsr\s+[^,\s;]+\s*,\s*([^;\s]+)", re.IGNORECASE)
RAW_RAM_RE = re.compile(r"\bram_0x[0-9A-Fa-f]{3}\b")
STOCK_BANK_ALIAS_RE = re.compile(r"^stock_([0-9A-Fa-f]{3})_b([0-9])$")
STOCK_PHYS_ALIAS_RE = re.compile(r"^stock_([0-9A-Fa-f]{3})_b([0-9])_phys$")
BANK_SUFFIX_ALIAS_RE = re.compile(r"^(.+)_b[0-9]$")
BANK_SUFFIX_PHYS_ALIAS_RE = re.compile(r"^(.+)_b[0-9]_phys$")
RAW_NUMERIC_RE = re.compile(r"^0x([0-9A-Fa-f]{1,4})$")
NUMERIC_BANKED_RE = re.compile(
    rf"\b(?:{F_OPERAND_MNEMONICS})\s+0x([0-9A-Fa-f]{{2,3}})(?:[^;\n]*),\s*(?:BANKED|B)\b",
    re.IGNORECASE,
)
NUMERIC_ACCESS_RE = re.compile(
    rf"\b(?:{F_OPERAND_MNEMONICS})\s+0x([0-9A-Fa-f]{{2,3}})(?:[^;\n]*),\s*(?:ACCESS|A)\b",
    re.IGNORECASE,
)
ROUTINE_CONTRACT_RE = re.compile(r";\s*@routine\s+([A-Za-z_]\w*)\s*(.*)$")
CONTRACT_FIELD_RE = re.compile(r"\b(entry_bsr|exit_bsr)=([A-Za-z0-9_]+)\b")

CONDITIONAL_BRANCH_MNEMONICS = {"bz", "bnz", "bc", "bnc", "bn", "bnn", "bov", "bnov"}
UNCONDITIONAL_BRANCH_MNEMONICS = {"bra", "goto"}
CALL_MNEMONICS = {"call", "rcall"}
RETURN_MNEMONICS = {"return", "retlw", "retfie"}
SKIP_MNEMONICS = {
    "btfsc",
    "btfss",
    "cpfseq",
    "cpfsgt",
    "cpfslt",
    "decfsz",
    "incfsz",
    "dcfsnz",
    "infsnz",
    "tstfsz",
}
DATA_DIRECTIVES = {
    "__config",
    "cblock",
    "code",
    "constant",
    "data",
    "db",
    "de",
    "dt",
    "dw",
    "else",
    "end",
    "endc",
    "endif",
    "endm",
    "equ",
    "errorlevel",
    "extern",
    "fill",
    "global",
    "if",
    "ifdef",
    "ifndef",
    "include",
    "list",
    "macro",
    "org",
    "processor",
    "radix",
    "res",
    "set",
    "space",
    "udata",
}

CONTROL_REGISTERS = {"W", "F", "A", "B", "ACCESS", "BANKED"}
SFR_NAMES = {
    "BSR",
    "FSR0L",
    "FSR0H",
    "FSR1L",
    "FSR1H",
    "FSR2L",
    "FSR2H",
    "INDF0",
    "POSTINC0",
    "POSTDEC0",
    "PREINC0",
    "PLUSW0",
    "INDF1",
    "POSTINC1",
    "POSTDEC1",
    "PREINC1",
    "PLUSW1",
    "INDF2",
    "POSTINC2",
    "POSTDEC2",
    "PREINC2",
    "PLUSW2",
    "STATUS",
    "WREG",
    "INTCON",
    "PORTA",
    "PORTB",
    "PORTC",
    "PORTD",
    "PORTE",
    "LATA",
    "LATB",
    "LATC",
    "TRISA",
    "TRISB",
    "TRISC",
    "ADCON0",
    "ADCON1",
    "ADCON2",
    "SSPCON1",
    "SSPCON2",
    "SSPSTAT",
    "SSPBUF",
    "PIR1",
    "PIR2",
    "PIE1",
    "PIE2",
    "RCSTA",
    "TXSTA",
    "TXREG",
    "RCREG",
    "T0CON",
    "T1CON",
    "T2CON",
    "T3CON",
    "TMR0L",
    "TMR0H",
    "TMR1L",
    "TMR1H",
    "TMR2",
    "TMR3L",
    "TMR3H",
    "RCON",
    "EECON1",
    "EECON2",
    "EEADR",
    "EEDATA",
    "EEADRH",
    "EEDATH",
    "TBLPTRL",
    "TBLPTRH",
    "TBLPTRU",
    "TABLAT",
    "UCON",
    "UIR",
    "UIE",
    "UCFG",
    "UEP0",
    "UEP1",
    "BD0STAT",
    "BD0CNT",
    "BD0ADRL",
    "BD0ADRH",
    "BD1STAT",
    "BD1CNT",
    "BD1ADRL",
    "BD1ADRH",
}


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    code: str
    message: str

    def format(self) -> str:
        return f"{project_relative(self.path)}:{self.line}: {self.code}: {self.message}"


class RamSafetyError(RuntimeError):
    def __init__(self, findings: Iterable[Finding]):
        self.findings = list(findings)
        super().__init__("\n".join(f.format() for f in self.findings))


BsrState = frozenset[int] | None


@dataclass(frozen=True)
class RoutineContract:
    label: str
    line: int
    entry_bsr: int | None = None
    exit_bsr: int | str | None = None


@dataclass(frozen=True)
class _AsmNode:
    index: int
    line_index: int
    lineno: int
    body: str
    mnemonic: str
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class _AsmProgram:
    path: Path
    lines: list[str]
    nodes: list[_AsmNode]
    line_to_node: dict[int, int]
    labels: dict[str, int]
    contracts: dict[str, RoutineContract]


def _strip_comment(line: str) -> str:
    return line.split(";", 1)[0].rstrip()


def _is_executable_line(line: str) -> bool:
    body = _strip_comment(line).strip()
    if not body:
        return False
    if body.endswith(":"):
        return False
    return True


def _contains_ram_alias(cell: RamCell, operand: str) -> bool:
    return operand == cell.alias or operand == cell.op_alias or operand == cell.phys_alias


def _access_mode(rest: str) -> str | None:
    if re.search(r",\s*(?:BANKED|B)\b", rest, re.IGNORECASE):
        return "banked"
    if re.search(r",\s*(?:ACCESS|A)\b", rest, re.IGNORECASE):
        return "access"
    return None


def render_alias_block(target: str) -> str:
    return expected_alias_block(target)


def install_alias_block(target: str) -> bool:
    """Install/update the generated alias block. Returns True if changed."""
    spec = TARGET_SPECS[target]
    text = spec.inc_path.read_text(encoding="utf-8")
    block = expected_alias_block(target).rstrip("\n")
    pattern = re.compile(
        re.escape(GENERATED_ALIAS_START) + r".*?" + re.escape(GENERATED_ALIAS_END),
        re.DOTALL,
    )
    if pattern.search(text):
        updated = pattern.sub(block, text)
    else:
        updated = text.rstrip() + "\n\n" + block + "\n"
    if updated == text:
        return False
    spec.inc_path.write_text(updated, encoding="utf-8")
    clear_manifest_cache()
    return True


def check_alias_block(target: str) -> list[Finding]:
    spec = TARGET_SPECS[target]
    text = spec.inc_path.read_text(encoding="utf-8")
    expected = expected_alias_block(target).rstrip("\n")
    pattern = re.compile(
        re.escape(GENERATED_ALIAS_START) + r".*?" + re.escape(GENERATED_ALIAS_END),
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        return [
            Finding(
                spec.inc_path,
                1,
                "RAM_ALIAS_BLOCK_MISSING",
                "generated RAM alias block missing; run scripts/check_ram_access_safety.py --fix-aliases",
            )
        ]
    actual = match.group(0).rstrip("\n")
    if actual != expected:
        return [
            Finding(
                spec.inc_path,
                text[: match.start()].count("\n") + 1,
                "RAM_ALIAS_BLOCK_STALE",
                "generated RAM alias block is stale; run scripts/check_ram_access_safety.py --fix-aliases",
            )
        ]
    return []


def check_manifest_collisions(target: str) -> list[Finding]:
    spec = TARGET_SPECS[target]
    cells = [cell for cell in load_manifest(target).values() if cell.alias_of is None]
    by_phys: dict[int, list[RamCell]] = {}
    for cell in cells:
        if cell.access == "access":
            continue
        by_phys.setdefault(cell.phys, []).append(cell)
    findings = []
    for phys, owners in sorted(by_phys.items()):
        distinct_sources = sorted({c.source_name for c in owners})
        non_stock_sources = sorted({c.source_name for c in owners if c.owner != "stock-derived"})
        if len(non_stock_sources) > 1:
            findings.append(
                Finding(
                    spec.inc_path,
                    1,
                    "RAM_PHYS_COLLISION",
                    f"0x{phys:03X} has multiple RAM owners: {', '.join(non_stock_sources)}",
                )
            )
    return findings


def _line_bsr_before(lines: list[str], index: int, *, max_scan: int = 120) -> int | None:
    """Return a locally proven BSR before *index*, or None if unknown."""
    for cursor in range(index - 1, max(-1, index - max_scan - 1), -1):
        body = _strip_comment(lines[cursor]).strip()
        if not body:
            continue
        if CALL_RE.search(body):
            return None
        match = MOVLB_RE.search(body)
        if match is not None:
            return int(match.group(1), 16)
    return None


def _resolve_cell(cells: dict[str, RamCell], operand: str) -> RamCell | None:
    return cells.get(operand)


def _table_data_lines(lines: list[str]) -> set[int]:
    out: set[int] = set()
    in_table = False
    for idx, line in enumerate(lines):
        body = _strip_comment(line).strip()
        label_match = LABEL_RE.match(body) or LABEL_PREFIX_RE.match(body)
        if label_match:
            label = label_match.group(1)
            in_table = "tblptr anchor" in line.lower() or label.endswith("_table")
            continue
        if in_table:
            out.add(idx)
    return out


def check_source_text(
    target: str,
    text: str,
    *,
    path: Path | None = None,
    enforce_bsr: bool = True,
) -> list[Finding]:
    spec = TARGET_SPECS[target]
    cells = load_manifest(target)
    source_names = cells_by_source_name(target)
    lines = text.splitlines()
    finding_path = path or spec.asm_path
    table_lines = _table_data_lines(lines)
    findings: list[Finding] = []

    for lineno, line in enumerate(lines, start=1):
        if lineno - 1 in table_lines:
            continue
        body = _strip_comment(line)
        if not _is_executable_line(line):
            continue
        if RAW_RAM_RE.search(body):
            findings.append(
                Finding(
                    finding_path,
                    lineno,
                    "RAM_RAW_SYMBOL",
                    "raw ram_0xNNN operand in target executable source",
                )
            )
        numeric_banked = NUMERIC_BANKED_RE.search(body)
        numeric_access = NUMERIC_ACCESS_RE.search(body)
        if numeric_banked or numeric_access:
            hint = _comment_phys_hint(line)
            numeric_is_sfr = hint is not None and hint >= 0xF00
        else:
            numeric_is_sfr = False
        if (numeric_banked or numeric_access) and not numeric_is_sfr:
            findings.append(
                Finding(
                    finding_path,
                    lineno,
                    "RAM_RAW_NUMERIC",
                    "raw numeric RAM operand in target executable source",
                )
            )
        movff = MOVFF_RE.search(body)
        if movff is not None:
            for operand in movff.groups():
                operand = operand.strip()
                cell = cells.get(operand)
                if cell is None and operand.endswith("_phys"):
                    findings.append(
                        Finding(
                            finding_path,
                            lineno,
                            "RAM_UNKNOWN_PHYS_ALIAS",
                            f"movff operand {operand} is not present in the generated RAM manifest",
                        )
                    )
                    continue
                if cell is not None and not operand.endswith("_phys"):
                    findings.append(
                        Finding(
                            finding_path,
                            lineno,
                            "RAM_MOVFF_NEEDS_PHYS",
                            f"movff operand {operand} must use *_phys alias",
                        )
                    )
        lfsr = LFSR_RE.search(body)
        if lfsr is not None:
            operand = lfsr.group(1).strip()
            raw_numeric = RAW_NUMERIC_RE.match(operand)
            if raw_numeric is not None and int(raw_numeric.group(1), 16) < 0xF00:
                findings.append(
                    Finding(
                        finding_path,
                        lineno,
                        "RAM_LFSR_RAW_NUMERIC",
                        "raw numeric RAM lfsr target must use a generated *_phys alias",
                    )
                )
            cell = cells.get(operand)
            if cell is None and operand.endswith("_phys"):
                findings.append(
                    Finding(
                        finding_path,
                        lineno,
                        "RAM_UNKNOWN_PHYS_ALIAS",
                        f"lfsr target {operand} is not present in the generated RAM manifest",
                    )
                )
                continue
            if cell is not None and not operand.endswith("_phys"):
                findings.append(
                    Finding(
                        finding_path,
                        lineno,
                        "RAM_LFSR_NEEDS_PHYS",
                        f"lfsr target {operand} must use *_phys alias",
                    )
                )
        fop = F_OPERAND_RE.search(body)
        if fop is None:
            continue
        operand = fop.group("operand")
        if operand in SFR_NAMES or operand in CONTROL_REGISTERS:
            continue
        mode = _access_mode(fop.group("rest"))
        if mode is None:
            continue
        cell = _resolve_cell(cells, operand)
        if cell is None and operand in source_names:
            findings.append(
                Finding(
                    finding_path,
                    lineno,
                    "RAM_AMBIGUOUS_SYMBOL",
                    f"{operand} must use bank/access-explicit alias",
                )
            )
            continue
        if cell is None:
            continue
        if operand.endswith("_phys"):
            findings.append(
                Finding(
                    finding_path,
                    lineno,
                    "RAM_FOP_NEEDS_OP_ALIAS",
                    f"f-operand {operand} must use bank/access or *_op alias, not *_phys",
                )
            )
            continue
        if mode == "access":
            if cell.access != "access":
                findings.append(
                    Finding(
                        finding_path,
                        lineno,
                        "RAM_ACCESS_ALIAS_REQUIRED",
                        f"{operand} is not an ACCESS alias",
                    )
                )
            continue
        if cell.access == "access":
            findings.append(
                Finding(
                    finding_path,
                    lineno,
                    "RAM_BANKED_ALIAS_REQUIRED",
                    f"{operand} is an ACCESS alias used with BANKED",
                )
            )
            continue
    if enforce_bsr:
        findings.extend(check_bsr_cfg_text(target, text, path=finding_path))
    return findings


def _check_main_an0_guard(text: str, *, path: Path) -> list[Finding]:
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if _strip_comment(line).strip() == "an0_hysteresis_monitor:")
    except StopIteration:
        return [
            Finding(
                path,
                1,
                "RAM_AN0_GUARD_MISSING",
                "an0_hysteresis_monitor label missing",
            )
        ]
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if LABEL_RE.match(_strip_comment(lines[idx]).strip()):
            end = idx
            break
    findings: list[Finding] = []
    for idx in range(start + 1, end):
        body = _strip_comment(lines[idx])
        if "an0_delay_b0" not in body:
            continue
        fop = F_OPERAND_RE.search(body)
        if fop is None or _access_mode(fop.group("rest")) != "banked":
            continue
        bsr = _line_bsr_before(lines, idx)
        if bsr != 0:
            findings.append(
                Finding(
                    path,
                    idx + 1,
                    "RAM_AN0_BSR_GUARD",
                    "an0_hysteresis_monitor must prove BSR=0 before an0_delay_b0",
                )
            )
    return findings


def check_source(target: str) -> list[Finding]:
    spec = TARGET_SPECS[target]
    findings = check_source_text(
        target,
        spec.asm_path.read_text(encoding="utf-8"),
        path=spec.asm_path,
        enforce_bsr=True,
    )
    return findings


def _cell_for_source(
    target: str,
    source_name: str,
    *,
    access: str,
    bank: int | None = None,
) -> RamCell | None:
    cells = load_manifest(target)
    source = cells_by_source_name(target).get(source_name)
    if source is None:
        return None
    if access == "access":
        return cells.get(f"{source.alias.rsplit('_b', 1)[0]}_acc")
    if bank is not None and source.bank != bank:
        raw = re.match(r"^ram_0x([0-9A-Fa-f]{3})$", source_name)
        if raw is not None:
            phys = (bank << 8) | (int(raw.group(1), 16) & 0xFF)
            return _cell_for_phys(target, phys, access="banked")
    return source


def _cell_for_phys(target: str, phys: int, *, access: str) -> RamCell | None:
    candidates = [
        cell
        for cell in load_manifest(target).values()
        if cell.alias_of is None and cell.phys == phys and cell.access == access
    ]
    if not candidates:
        return None
    # Prefer semantic aliases over generated stock_NNN names.
    candidates.sort(key=lambda c: (c.alias.startswith("stock_"), len(c.alias), c.alias))
    return candidates[0]


def _cell_for_stock_alias_with_bsr(
    target: str,
    operand: str,
    *,
    bsr: int | None,
    access: str,
) -> RamCell | None:
    if access != "banked":
        return None
    stock = STOCK_BANK_ALIAS_RE.match(operand)
    if stock is None:
        return None
    encoded_phys = int(stock.group(1), 16)
    encoded_bank = int(stock.group(2))
    actual_bank = bsr if bsr is not None else encoded_bank
    actual_phys = (actual_bank << 8) | (encoded_phys & 0xFF)
    return _cell_for_phys(target, actual_phys, access="banked")


def _comment_phys_hint(line: str) -> int | None:
    comment = line.split(";", 1)[1] if ";" in line else ""
    match = re.search(r"\breg:\s*0x([0-9A-Fa-f]{3})\b", comment)
    if match is not None:
        return int(match.group(1), 16)
    return None


def _parse_bsr_value(value: str) -> int | str | None:
    lowered = value.lower()
    if lowered in {"any", "unknown", "clobber"}:
        return None
    if lowered == "preserve":
        return "preserve"
    if lowered.startswith("0x"):
        return int(lowered, 16)
    if lowered.isdigit():
        return int(lowered)
    return None


def _bsr_state_text(state: BsrState) -> str:
    if state is None:
        return "unknown"
    return "{" + ",".join(str(v) for v in sorted(state)) + "}"


def _join_bsr(old: BsrState, new: BsrState) -> BsrState:
    if old is None or new is None:
        return None
    return frozenset(set(old) | set(new))


def _state_satisfies_required(state: BsrState, required: int | None) -> bool:
    if required is None:
        return True
    return state == frozenset({required})


def _split_label_prefix(body: str) -> tuple[str | None, str]:
    match = LABEL_PREFIX_RE.match(body)
    if match is None:
        return None, body
    return match.group(1), match.group(2).strip()


def _mnemonic(body: str) -> str:
    stripped = body.strip()
    if not stripped:
        return ""
    return stripped.split(None, 1)[0].lower()


def _is_macro_start(body: str) -> bool:
    parts = body.strip().split()
    return len(parts) >= 2 and parts[1].lower() == "macro"


def _is_directive_or_data(body: str) -> bool:
    parts = body.strip().split()
    if not parts:
        return True
    if len(parts) >= 2 and parts[1].lower() in {"equ", "set"}:
        return True
    return parts[0].lower() in DATA_DIRECTIVES


def _parse_contracts(line: str, *, lineno: int) -> list[RoutineContract]:
    out: list[RoutineContract] = []
    match = ROUTINE_CONTRACT_RE.search(line)
    if match is None:
        return out
    fields = {field.lower(): value for field, value in CONTRACT_FIELD_RE.findall(match.group(2))}
    entry_raw = fields.get("entry_bsr", "unknown")
    exit_raw = fields.get("exit_bsr", "unknown")
    entry = _parse_bsr_value(entry_raw)
    exit_value = _parse_bsr_value(exit_raw)
    if entry == "preserve":
        entry = None
    out.append(
        RoutineContract(
            label=match.group(1),
            line=lineno,
            entry_bsr=entry if isinstance(entry, int) else None,
            exit_bsr=exit_value,
        )
    )
    return out


def _parse_program(text: str, *, path: Path) -> _AsmProgram:
    lines = text.splitlines()
    table_lines = _table_data_lines(lines)
    nodes: list[_AsmNode] = []
    labels: dict[str, int] = {}
    line_to_node: dict[int, int] = {}
    contracts: dict[str, RoutineContract] = {}
    pending_labels: list[str] = []
    in_macro = False

    for line_index, line in enumerate(lines):
        lineno = line_index + 1
        for contract in _parse_contracts(line, lineno=lineno):
            contracts[contract.label] = contract
        body = _strip_comment(line).strip()
        if not body:
            continue
        if in_macro:
            if _mnemonic(body) == "endm":
                in_macro = False
            continue
        label, remainder = _split_label_prefix(body)
        if label is not None:
            if line_index in table_lines or "tblptr anchor" in line.lower():
                pending_labels.clear()
                continue
            if remainder:
                pending_labels.append(label)
                body = remainder
            else:
                pending_labels.append(label)
                continue
        if _is_macro_start(body):
            pending_labels.clear()
            in_macro = True
            continue
        if _is_directive_or_data(body) or line_index in table_lines:
            pending_labels.clear()
            continue
        mnemonic = _mnemonic(body)
        node = _AsmNode(
            index=len(nodes),
            line_index=line_index,
            lineno=lineno,
            body=body,
            mnemonic=mnemonic,
            labels=tuple(pending_labels),
        )
        for pending in pending_labels:
            labels[pending] = node.index
        pending_labels = []
        line_to_node[line_index] = node.index
        nodes.append(node)

    return _AsmProgram(
        path=path,
        lines=lines,
        nodes=nodes,
        line_to_node=line_to_node,
        labels=labels,
        contracts=contracts,
    )


def _next_node(program: _AsmProgram, node: _AsmNode) -> int | None:
    nxt = node.index + 1
    if nxt < len(program.nodes):
        return nxt
    return None


def _skip_node(program: _AsmProgram, node: _AsmNode) -> int | None:
    nxt = node.index + 2
    if nxt < len(program.nodes):
        return nxt
    return None


def _branch_target_node(program: _AsmProgram, body: str) -> int | None:
    match = BRANCH_RE.search(body)
    if match is None:
        return None
    return program.labels.get(match.group(1))


def _call_target_label(body: str) -> str | None:
    match = CALL_RE.search(body)
    if match is None:
        return None
    return match.group(1)


def _transfer_bsr(body: str, state: BsrState) -> BsrState:
    match = MOVLB_RE.search(body)
    if match is not None:
        return frozenset({int(match.group(1), 16)})
    if re.search(r"\bclrf\s+BSR\b", body, re.IGNORECASE):
        return frozenset({0})
    if re.search(r"\bmovwf\s+BSR\b", body, re.IGNORECASE):
        return None
    movff = MOVFF_RE.search(body)
    if movff is not None and movff.group(2).strip().upper() == "BSR":
        return None
    return state


def _contract_exit_state(contract: RoutineContract | None, call_state: BsrState) -> BsrState:
    if contract is None or contract.exit_bsr is None:
        return None
    if contract.exit_bsr == "preserve":
        return call_state
    if isinstance(contract.exit_bsr, int):
        return frozenset({contract.exit_bsr})
    return None


def _default_roots(target: str, program: _AsmProgram) -> list[tuple[int, BsrState, str]]:
    roots: list[tuple[int, BsrState, str]] = []
    if program.nodes:
        roots.append((0, None, "first executable instruction"))
    target_root_labels = {
        "main-v33": (
            # Reset enters the app trampoline; interrupt dispatch starts at the
            # vector spill/call body, which has no source label in this file.
            "app_entry__jump_to_cold_init",
            "hid_command_dispatch",
            "isr_high_priority_dispatch",
        ),
        "main-v34": (
            # V3.4 is the V3.3 successor and starts from the same CFG roots.
            "app_entry__jump_to_cold_init",
            "hid_command_dispatch",
            "isr_high_priority_dispatch",
        ),
        "control-v172": (
            "vector_reset",
            "vector_int_high",
            "vector_int_low",
            "flow_local_0040",
            "app_entry_defensive_stub",
            "main_event_loop",
            "flow_main_event_loop_1642",
            "control_core_service_17E8",
        ),
        "control-v173": (
            "vector_reset",
            "vector_int_high",
            "vector_int_low",
            "flow_local_0040",
            "app_entry_defensive_stub",
            "main_event_loop",
            "flow_main_event_loop_1642",
            "control_core_service_17E8",
        ),
    }
    for label in target_root_labels.get(target, ()):
        if label in program.labels:
            contract = program.contracts.get(label)
            entry_state: BsrState = (
                frozenset({contract.entry_bsr})
                if contract is not None and contract.entry_bsr is not None
                else None
            )
            roots.append((program.labels[label], entry_state, label))

    return roots


def _banked_access_finding(
    *,
    target: str,
    program: _AsmProgram,
    node: _AsmNode,
    state: BsrState,
) -> Finding | None:
    cells = load_manifest(target)
    fop = F_OPERAND_RE.search(node.body)
    if fop is None or _access_mode(fop.group("rest")) != "banked":
        return None
    operand = fop.group("operand")
    if operand in SFR_NAMES or operand in CONTROL_REGISTERS:
        return None
    cell = _resolve_cell(cells, operand)
    if cell is None or cell.access == "access" or operand.endswith("_phys"):
        return None
    if state == frozenset({cell.bank}):
        return None
    if state is None or cell.bank in state:
        return Finding(
            program.path,
            node.lineno,
            "RAM_BSR_INDETERMINATE",
            f"{operand} requires BSR={cell.bank}, CFG state={_bsr_state_text(state)}",
        )
    return Finding(
        program.path,
        node.lineno,
        "RAM_BSR_MISMATCH",
        f"{operand} requires BSR={cell.bank}, CFG state={_bsr_state_text(state)}",
    )


def check_bsr_cfg_text(
    target: str,
    text: str,
    *,
    path: Path | None = None,
) -> list[Finding]:
    spec = TARGET_SPECS[target]
    finding_path = path or spec.asm_path
    program = _parse_program(text, path=finding_path)
    findings: list[Finding] = []
    seen_findings: set[tuple[int, str, str]] = set()

    def add_finding(finding: Finding | None) -> None:
        if finding is None:
            return
        key = (finding.line, finding.code, finding.message)
        if key in seen_findings:
            return
        seen_findings.add(key)
        findings.append(finding)

    all_state_at: dict[int, BsrState] = {}
    summary_cache: dict[tuple[int, tuple[int, ...] | None], set[BsrState]] = {}
    active_summaries: set[tuple[int, tuple[int, ...] | None]] = set()

    def state_key(state: BsrState) -> tuple[int, ...] | None:
        if state is None:
            return None
        return tuple(sorted(state))

    def record_reached(node_index: int, state: BsrState) -> None:
        old = all_state_at.get(node_index, frozenset())
        if node_index not in all_state_at:
            all_state_at[node_index] = state
            return
        all_state_at[node_index] = _join_bsr(old, state)

    def summarize(start_node: int, entry_state: BsrState) -> set[BsrState]:
        key = (start_node, state_key(entry_state))
        if key in summary_cache:
            return summary_cache[key]
        if key in active_summaries:
            return {None}

        active_summaries.add(key)
        local_state_at: dict[int, BsrState] = {}
        worklist: list[int] = []
        exits: set[BsrState] = set()

        def enqueue(node_index: int | None, state: BsrState) -> None:
            if node_index is None:
                return
            old = local_state_at.get(node_index, frozenset())
            if node_index not in local_state_at:
                local_state_at[node_index] = state
                worklist.append(node_index)
                return
            joined = _join_bsr(old, state)
            if joined != old:
                local_state_at[node_index] = joined
                worklist.append(node_index)

        enqueue(start_node, entry_state)
        while worklist:
            node = program.nodes[worklist.pop(0)]
            state = local_state_at[node.index]
            record_reached(node.index, state)
            add_finding(_banked_access_finding(target=target, program=program, node=node, state=state))
            next_state = _transfer_bsr(node.body, state)
            mnemonic = node.mnemonic

            if mnemonic in RETURN_MNEMONICS:
                exits.add(next_state)
                continue
            if mnemonic in {"reset", "sleep"}:
                continue
            if mnemonic in CALL_MNEMONICS:
                target_label = _call_target_label(node.body)
                contract = program.contracts.get(target_label or "")
                call_exits: set[BsrState]
                if contract is not None:
                    if not _state_satisfies_required(state, contract.entry_bsr):
                        add_finding(
                            Finding(
                                finding_path,
                                node.lineno,
                                "RAM_BSR_CONTRACT_ENTRY_MISMATCH",
                                f"{target_label} requires entry BSR={contract.entry_bsr}, call state={_bsr_state_text(state)}",
                            )
                        )
                    if target_label in program.labels:
                        callee_entry: BsrState = (
                            frozenset({contract.entry_bsr})
                            if contract.entry_bsr is not None
                            else next_state
                        )
                        expected_exit = _contract_exit_state(contract, next_state)
                        callee_key = (program.labels[target_label], state_key(callee_entry))
                        if contract.exit_bsr is not None and callee_key not in active_summaries:
                            actual_exits = summarize(program.labels[target_label], callee_entry)
                            for actual_exit in actual_exits:
                                if actual_exit != expected_exit:
                                    add_finding(
                                        Finding(
                                            finding_path,
                                            node.lineno,
                                            "RAM_BSR_CONTRACT_EXIT_MISMATCH",
                                            f"{target_label} declares exit BSR={_bsr_state_text(expected_exit)}, actual exit={_bsr_state_text(actual_exit)}",
                                        )
                                    )
                    call_exits = {_contract_exit_state(contract, next_state)}
                elif target_label in program.labels:
                    call_exits = summarize(program.labels[target_label], next_state)
                else:
                    call_exits = {None}
                for exit_state in call_exits:
                    enqueue(_next_node(program, node), exit_state)
                continue
            if mnemonic in UNCONDITIONAL_BRANCH_MNEMONICS:
                enqueue(_branch_target_node(program, node.body), next_state)
                continue
            if mnemonic in CONDITIONAL_BRANCH_MNEMONICS:
                enqueue(_branch_target_node(program, node.body), next_state)
                enqueue(_next_node(program, node), next_state)
                continue
            if mnemonic in SKIP_MNEMONICS:
                enqueue(_next_node(program, node), next_state)
                enqueue(_skip_node(program, node), next_state)
                continue
            enqueue(_next_node(program, node), next_state)

        active_summaries.remove(key)
        summary_cache[key] = exits
        return exits

    for node_index, state, _why in _default_roots(target, program):
        summarize(node_index, state)

    for label, contract in sorted(program.contracts.items()):
        if label not in program.labels:
            add_finding(
                Finding(
                    finding_path,
                    contract.line,
                    "RAM_BSR_CONTRACT_LABEL_MISSING",
                    f"{label} declares a BSR contract but has no executable label",
                )
            )
            continue
        if contract.exit_bsr is None:
            continue
        entry_state: BsrState = (
            frozenset({contract.entry_bsr})
            if contract.entry_bsr is not None
            else None
        )
        expected_exit = _contract_exit_state(contract, entry_state)
        for actual_exit in summarize(program.labels[label], entry_state):
            if actual_exit != expected_exit:
                add_finding(
                    Finding(
                        finding_path,
                        contract.line,
                        "RAM_BSR_CONTRACT_EXIT_MISMATCH",
                        f"{label} declares exit BSR={_bsr_state_text(expected_exit)}, actual exit={_bsr_state_text(actual_exit)}",
                    )
                )

    def enqueue(node_index: int | None, state: BsrState) -> None:
        if node_index is None:
            return

    for node in program.nodes:
        if node.index in all_state_at:
            continue
        if not node.labels:
            continue
        fop = F_OPERAND_RE.search(node.body)
        if fop is None or _access_mode(fop.group("rest")) != "banked":
            continue
        operand = fop.group("operand")
        if operand in SFR_NAMES or operand in CONTROL_REGISTERS:
            continue
        cell = _resolve_cell(load_manifest(target), operand)
        if cell is None or cell.access == "access":
            continue
        add_finding(
            Finding(
                finding_path,
                node.lineno,
                "RAM_BSR_UNREACHED",
                f"{operand} BANKED access was not reached by CFG roots",
            )
        )

    return sorted(findings, key=lambda f: (str(f.path), f.line, f.code, f.message))


def migrate_source_aliases(target: str) -> bool:
    """Rewrite target executable RAM operands to manifest-backed aliases.

    The rewrite is deliberately operand-position-only and preserves comments.
    Returns True when the source file changed.
    """
    spec = TARGET_SPECS[target]
    cells = load_manifest(target)
    source_names = cells_by_source_name(target)
    original = spec.asm_path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    line_text = [line.rstrip("\n") for line in lines]
    table_lines = _table_data_lines(line_text)
    updated_lines: list[str] = []

    for idx, line in enumerate(lines):
        newline = "\n" if line.endswith("\n") else ""
        raw_line = line[:-1] if newline else line
        body, sep, comment = raw_line.partition(";")
        if idx in table_lines:
            updated_lines.append(raw_line + newline)
            continue

        def replace_movff(match: re.Match[str]) -> str:
            left = match.group(1).strip()
            right = match.group(2).strip()

            def repl_operand(operand: str) -> str:
                cell = cells.get(operand)
                if cell is not None:
                    return cell.phys_alias if cell.alias_of is None else cell.alias
                stock_phys = STOCK_PHYS_ALIAS_RE.match(operand)
                if stock_phys is not None:
                    cell2 = _cell_for_phys(target, int(stock_phys.group(1), 16), access="banked")
                    return cell2.phys_alias if cell2 is not None else operand
                banked_phys = BANK_SUFFIX_PHYS_ALIAS_RE.match(operand)
                if banked_phys is not None and banked_phys.group(1) in source_names:
                    return source_names[banked_phys.group(1)].phys_alias
                source = source_names.get(operand)
                if source is not None:
                    return source.phys_alias
                raw = re.match(r"^ram_0x([0-9A-Fa-f]{3})$", operand)
                if raw is not None:
                    phys = int(raw.group(1), 16)
                    cell2 = _cell_for_phys(target, phys, access="banked")
                    return cell2.phys_alias if cell2 is not None else operand
                return operand

            new_left = repl_operand(left)
            new_right = repl_operand(right)
            text = match.group(0)
            text = re.sub(re.escape(left), new_left, text, count=1)
            return re.sub(re.escape(right) + r"$", new_right, text, count=1)

        body = MOVFF_RE.sub(replace_movff, body)

        def replace_lfsr(match: re.Match[str]) -> str:
            operand = match.group(1).strip()
            new_operand = operand
            cell = cells.get(operand)
            if cell is not None:
                new_operand = cell.phys_alias if cell.alias_of is None else cell.alias
            elif STOCK_PHYS_ALIAS_RE.match(operand):
                stock_phys = STOCK_PHYS_ALIAS_RE.match(operand)
                assert stock_phys is not None
                cell2 = _cell_for_phys(target, int(stock_phys.group(1), 16), access="banked")
                if cell2 is not None:
                    new_operand = cell2.phys_alias
            elif BANK_SUFFIX_PHYS_ALIAS_RE.match(operand):
                banked_phys = BANK_SUFFIX_PHYS_ALIAS_RE.match(operand)
                assert banked_phys is not None
                source = source_names.get(banked_phys.group(1))
                if source is not None:
                    new_operand = source.phys_alias
            elif operand in source_names:
                new_operand = source_names[operand].phys_alias
            else:
                raw_numeric = RAW_NUMERIC_RE.match(operand)
                if raw_numeric is not None:
                    phys = int(raw_numeric.group(1), 16)
                    if phys < 0xF00:
                        cell2 = _cell_for_phys(target, phys, access="banked")
                        if cell2 is not None:
                            new_operand = cell2.phys_alias
                raw = re.match(r"^ram_0x([0-9A-Fa-f]{3})$", operand)
                if raw is not None:
                    cell2 = _cell_for_phys(target, int(raw.group(1), 16), access="banked")
                    if cell2 is not None:
                        new_operand = cell2.phys_alias
            return match.group(0)[: match.start(1) - match.start(0)] + new_operand

        body = LFSR_RE.sub(replace_lfsr, body)

        def replace_fop(match: re.Match[str]) -> str:
            operand = match.group("operand")
            rest = match.group("rest")
            mode = _access_mode(rest)
            if mode is None or operand in SFR_NAMES or operand in CONTROL_REGISTERS:
                return match.group(0)
            replacement = operand
            bsr = _line_bsr_before(line_text, idx)
            if operand.startswith("0x"):
                literal = int(operand, 16)
                if mode == "access":
                    hint = _comment_phys_hint(raw_line)
                    if hint is not None and hint >= 0xF00:
                        return match.group(0)
                    cell = _cell_for_phys(target, literal, access="access")
                else:
                    hint = _comment_phys_hint(raw_line)
                    if hint is not None and hint < 0xF00:
                        phys = hint
                    else:
                        phys = ((bsr or 0) << 8) | literal
                    cell = _cell_for_phys(target, phys, access="banked")
                if cell is not None:
                    replacement = cell.alias
            else:
                if mode == "access":
                    cell = _cell_for_source(target, operand, access="access")
                else:
                    cell = _cell_for_stock_alias_with_bsr(
                        target,
                        operand,
                        bsr=bsr,
                        access="banked",
                    )
                    if cell is None:
                        raw = re.match(r"^ram_0x([0-9A-Fa-f]{3})$", operand)
                        bank = bsr if raw is not None else None
                        cell = _cell_for_source(
                            target,
                            operand,
                            access="banked",
                            bank=bank,
                        )
                    if cell is None:
                        banked_alias = BANK_SUFFIX_ALIAS_RE.match(operand)
                        if banked_alias is not None:
                            cell = _cell_for_source(
                                target,
                                banked_alias.group(1),
                                access="banked",
                            )
                if cell is not None:
                    replacement = cell.alias
            if replacement == operand:
                return match.group(0)
            return match.group(0)[: match.start("operand") - match.start(0)] + replacement + rest

        body = F_OPERAND_RE.sub(replace_fop, body)
        updated_lines.append(body + (sep + comment if sep else "") + newline)

    updated = "".join(updated_lines)
    if updated == original:
        return False
    spec.asm_path.write_text(updated, encoding="utf-8")
    clear_manifest_cache()
    return True


def check_targets(targets: Iterable[str]) -> list[Finding]:
    findings: list[Finding] = []
    for target in targets:
        findings.extend(check_alias_block(target))
        findings.extend(check_manifest_collisions(target))
        findings.extend(check_source(target))
    return findings


def assert_targets_safe(targets: Iterable[str]) -> None:
    findings = check_targets(targets)
    if findings:
        raise RamSafetyError(findings)
