"""Disassembly-to-source converter for DLCP MAIN PIC18F2455 V3.0.

Decodes stock V2.3 hex bytes into gpasm-compatible assembly with symbolic
labels, named SFRs, and TBLPTR label references.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional

from dlcp_fw.asm.region_manifest import classify_address
from dlcp_fw.paths import (
    PROJECT_ROOT,
    STOCK_MAIN_HEX,
    SEMANTIC_FUNCTION_MAP,
)
from dlcp_fw.sim.hexio import parse_intel_hex

# ---------------------------------------------------------------------------
# SFR name table — parsed from gputils header
# ---------------------------------------------------------------------------

_GPUTILS_HEADER = Path("/opt/homebrew/share/gputils/header/p18f2455.inc")

# Preferred SFR names (first match wins for each address)
_SFR_PREFERRED = {
    0xF92: "TRISA", 0xF93: "TRISB", 0xF94: "TRISC",
    0xFB8: "BAUDCON", 0xFB2: "TMR3L", 0xFD6: "TMR0L",
    0xFCE: "TMR1L", 0xFBB: "CCPR2L", 0xFBE: "CCPR1L",
    0xFC3: "ADRESL", 0xFF3: "PRODL", 0xFF6: "TBLPTRL",
    0xFD2: "HLVDCON", 0xFD9: "FSR2L", 0xFE1: "FSR1L",
    0xFE9: "FSR0L", 0xFFD: "TOSL", 0xF66: "UFRML",
    0xFF9: "PCL",
}


def _parse_sfr_names() -> Dict[int, str]:
    """Parse SFR EQU definitions from the gputils p18f2455.inc header."""
    names: Dict[int, str] = {}
    text = _GPUTILS_HEADER.read_text()
    for m in re.finditer(r"^(\w+)\s+EQU\s+H'([0-9A-Fa-f]+)'", text, re.MULTILINE):
        name = m.group(1)
        addr = int(m.group(2), 16)
        if addr < 0xF00:
            continue
        if addr >= 0x200000:
            continue
        if addr in _SFR_PREFERRED:
            names[addr] = _SFR_PREFERRED[addr]
        elif addr not in names:
            names[addr] = name
    return names


_SFR_NAMES: Dict[int, str] = {}


def _get_sfr_names() -> Dict[int, str]:
    global _SFR_NAMES
    if not _SFR_NAMES:
        _SFR_NAMES = _parse_sfr_names()
    return _SFR_NAMES


# ---------------------------------------------------------------------------
# Label pool — from annotated disassembly + semantic function map
# ---------------------------------------------------------------------------

def _parse_annotated_labels() -> Dict[int, str]:
    """Parse function_NNN and label_NNN from annotated disassembly."""
    asm_path = PROJECT_ROOT / "firmware" / "disasm" / "main" / "gpdasm_output.annotated.asm"
    labels: Dict[int, str] = {}
    text = asm_path.read_text()

    for m in re.finditer(
        r"^((?:function|label)_\d+):\s*;\s*address:\s*0x([0-9a-fA-F]+)",
        text, re.MULTILINE,
    ):
        name = m.group(1)
        addr = int(m.group(2), 16)
        labels[addr] = name
    return labels


def _parse_semantic_map() -> Dict[str, str]:
    """Parse semantic function map: auto-name -> semantic-name.

    Only parses the MAIN section to avoid CONTROL namespace collisions.
    """
    mapping: Dict[str, str] = {}
    text = SEMANTIC_FUNCTION_MAP.read_text()

    # Extract only the MAIN sections (functions + labels + registers)
    # Stop at CONTROL section
    main_start = text.find("## MAIN Functions")
    control_start = text.find("## CONTROL Functions")
    if main_start < 0:
        return mapping
    main_text = text[main_start:control_start] if control_start > 0 else text[main_start:]

    # Match table rows: | function_NNN | `semantic_name` | ...
    for m in re.finditer(
        r"\|\s*((?:function|label)_\d+)\s*\|\s*`(\w+)`\s*\|",
        main_text,
    ):
        auto_name = m.group(1)
        semantic_name = m.group(2)
        mapping[auto_name] = semantic_name
    return mapping


def _build_label_pool() -> Dict[int, str]:
    """Build address -> label name mapping with semantic overrides."""
    auto_labels = _parse_annotated_labels()
    semantic_map = _parse_semantic_map()

    labels: Dict[int, str] = {}
    for addr, auto_name in auto_labels.items():
        if auto_name in semantic_map:
            labels[addr] = semantic_map[auto_name]
        else:
            labels[addr] = auto_name
    return labels


# ---------------------------------------------------------------------------
# USB data region sub-labels
# ---------------------------------------------------------------------------

_USB_DATA_LABELS: Dict[int, tuple[str, str]] = {
    0x1018: ("hex_lookup_sentinel", "NUL byte sentinel"),
    0x1019: ("hex_lookup_table", "ASCII hex digits: 0-9, A-F"),
    0x1029: ("string_desc_ptr_table", "String descriptor offset table"),
    0x102C: ("usb_config_descriptor", "USB Configuration Descriptor"),
    0x1035: ("usb_interface_descriptor", "USB Interface Descriptor"),
    0x103E: ("usb_hid_descriptor", "USB HID Descriptor"),
    0x1047: ("usb_ep1_in_descriptor", "Endpoint 1 IN (interrupt)"),
    0x104E: ("usb_ep1_out_descriptor", "Endpoint 1 OUT (interrupt)"),
    0x1055: ("usb_hid_report_descriptor", "HID Report Descriptor"),
    0x1072: ("usb_string_desc_1", 'String Descriptor 1: "Hypex BV"'),
    0x1088: ("usb_device_descriptor", "USB Device Descriptor"),
    0x109A: ("usb_string_desc_2", 'String Descriptor 2: "DLCP"'),
    0x10A6: ("usb_string_desc_0", "String Descriptor 0: LANGID"),
    0x10AA: ("usb_data_pad", "Padding to code boundary"),
}

# Inline data table within code range
_INLINE_DATA_LABELS: Dict[int, tuple[str, str]] = {
    0x47E6: ("inline_data_table_47E6", "UART status strings for FW update"),
}


# ---------------------------------------------------------------------------
# TBLPTR load site mapping — direct loads to convert to label references
# ---------------------------------------------------------------------------

# Sites where addlw <low> / movwf TBLPTRL / movlw <high> / movwf TBLPTRH
# are used for hex_lookup_table (0x1019)
_ADDLW_TBLPTR_SITES = {
    # addr of addlw instruction -> (target_label, low_byte)
    # The addlw has LOW(target) as operand
}

# Map of (TBLPTRH_value, TBLPTRL_value) -> label_name for direct loads
_TBLPTR_DIRECT_TARGETS: Dict[tuple[int, int, int], str] = {
    # (TBLPTRU, TBLPTRH, TBLPTRL) -> label
    (0x00, 0x47, 0xE6): "inline_data_table_47E6",
    (0x30, 0x00, 0x0B): "_CONFIG6H",
    (0x30, 0x00, 0x00): "_CONFIG1L",
}

# Map target values for addlw patterns
_TBLPTR_ADDLW_TARGETS: Dict[tuple[int, int], str] = {
    # (TBLPTRH_value, addlw_value) -> label for LOW()
    (0x10, 0x19): "hex_lookup_table",
    (0x10, 0x29): "string_desc_ptr_table",
}


# ---------------------------------------------------------------------------
# Config bit symbolic names
# ---------------------------------------------------------------------------

_CONFIG_REGS = [
    (0x300000, "_CONFIG1L"),
    (0x300001, "_CONFIG1H"),
    (0x300002, "_CONFIG2L"),
    (0x300003, "_CONFIG2H"),
    (0x300005, "_CONFIG3H"),
    (0x300006, "_CONFIG4L"),
    (0x300008, "_CONFIG5L"),
    (0x300009, "_CONFIG5H"),
    (0x30000A, "_CONFIG6L"),
    (0x30000B, "_CONFIG6H"),
    (0x30000C, "_CONFIG7L"),
    (0x30000D, "_CONFIG7H"),
]


# ---------------------------------------------------------------------------
# RAM variable names from semantic map
# ---------------------------------------------------------------------------

_RAM_NAMES: Dict[int, str] = {
    0x001: "isr_save_fsr2l",
    0x002: "isr_save_fsr2h",
    0x05E: "active_flags",
    0x07E: "event_flags",
    0x066: "logical_volume",
    0x067: "logical_volume_1",
    0x068: "logical_volume_2",
    0x069: "logical_volume_3",
    0x06E: "computed_volume",
    0x06F: "computed_volume_1",
    0x070: "computed_volume_2",
    0x071: "computed_volume_3",
    0x095: "usb_reinit_pending",
    0x098: "rx_frame_position",
    0x099: "input_select",
    0x0B3: "input_select_mirror",
    0x0C6: "rx_ring_rd",
    0x0C7: "rx_ring_wr",
    0x055: "i2c_coeff_0",
    0x056: "i2c_coeff_1",
    0x057: "i2c_coeff_2",
    0x058: "i2c_coeff_3",
}


# ---------------------------------------------------------------------------
# PIC18 Instruction Decoder
# ---------------------------------------------------------------------------

def _sign_extend(value: int, bits: int) -> int:
    """Sign-extend a value from the given number of bits."""
    if value & (1 << (bits - 1)):
        return value - (1 << bits)
    return value


def _sfr_name(addr: int) -> str:
    """Return symbolic SFR name or raw hex for a file register address."""
    sfrs = _get_sfr_names()
    # For SFRs in the access bank (0xF60-0xFFF map to 0x060-0x0FF in access)
    if addr in sfrs:
        return sfrs[addr]
    return f"0x{addr:03X}"


def _ram_name(addr: int) -> str:
    """Return named RAM variable or generic ram_0xNNN."""
    if addr in _RAM_NAMES:
        return _RAM_NAMES[addr]
    return f"ram_0x{addr:03X}"


def _file_reg_name(f: int, a: int) -> str:
    """Return the name for a file register operand.

    f: 8-bit file register field from instruction
    a: access bit (0=access bank, 1=BSR bank)
    """
    if a == 0:
        # Access bank: 0x00-0x5F -> GPR access, 0x60-0xFF -> SFR 0xF60-0xFFF
        if f >= 0x60:
            sfr_addr = 0xF00 + f
            return _sfr_name(sfr_addr)
        else:
            return _ram_name(f)
    else:
        # BSR-banked: actual address = BSR:f
        return _ram_name(f)


class Instruction:
    """A decoded PIC18 instruction."""

    def __init__(self, addr: int, mnemonic: str, operands: str = "",
                 size: int = 2, comment: str = "", is_branch: bool = False,
                 branch_target: Optional[int] = None, raw_words: list[int] | None = None):
        self.addr = addr
        self.mnemonic = mnemonic
        self.operands = operands
        self.size = size
        self.comment = comment
        self.is_branch = is_branch
        self.branch_target = branch_target
        self.raw_words = raw_words or []


def _decode_byte_oriented(word: int, addr: int) -> Optional[Instruction]:
    """Decode byte-oriented file register instructions."""
    opcode = (word >> 8) & 0xFF
    f = word & 0xFF
    d_bit = (word >> 9) & 1  # destination: 0=W, 1=F
    a_bit = (word >> 8) & 1  # access: 0=ACCESS, 1=BANKED

    # The actual opcode nibble is bits 15-12 and 11-10
    op_hi4 = (word >> 12) & 0xF
    op_mid2 = (word >> 10) & 0x3

    dest = "F" if d_bit else "W"
    acc = "BANKED" if a_bit else "ACCESS"
    reg = _file_reg_name(f, a_bit)

    mnemonics_dfa = {
        (0x0, 0x1): "decf",     # 0000 01da
        (0x0, 0x2): "sublw",    # actually no — this is different
    }

    # Decode based on opcode pattern
    # 0000 000a — NOP (a=0), or MOVS/TBLRD etc for other patterns
    if word == 0x0000:
        return Instruction(addr, "nop", raw_words=[word])
    if word == 0x0003:
        return Instruction(addr, "sleep", raw_words=[word])
    if word == 0x0004:
        return Instruction(addr, "clrwdt", raw_words=[word])
    if word == 0x0005:
        return Instruction(addr, "push", raw_words=[word])
    if word == 0x0006:
        return Instruction(addr, "pop", raw_words=[word])
    if word == 0x0007:
        return Instruction(addr, "daw", raw_words=[word])
    if word == 0x0008:
        return Instruction(addr, "tblrd*", raw_words=[word])
    if word == 0x0009:
        return Instruction(addr, "tblrd*+", raw_words=[word])
    if word == 0x000A:
        return Instruction(addr, "tblrd*-", raw_words=[word])
    if word == 0x000B:
        return Instruction(addr, "tblrd+*", raw_words=[word])
    if word == 0x000C:
        return Instruction(addr, "tblwt*", raw_words=[word])
    if word == 0x000D:
        return Instruction(addr, "tblwt*+", raw_words=[word])
    if word == 0x000E:
        return Instruction(addr, "tblwt*-", raw_words=[word])
    if word == 0x000F:
        return Instruction(addr, "tblwt+*", raw_words=[word])
    if word == 0x00FF:
        return Instruction(addr, "reset", raw_words=[word])
    # RETURN: 0000 0000 0001 001s (0x0012 or 0x0013)
    if (word & 0xFFFE) == 0x0012:
        s = word & 1
        return Instruction(addr, "return", f"{'1' if s else '0'}", raw_words=[word])
    # RETFIE: 0000 0000 0001 000s (0x0010 or 0x0011)
    if (word & 0xFFFE) == 0x0010:
        s = word & 1
        return Instruction(addr, "retfie", f"{'1' if s else '0'}", raw_words=[word])

    # MOVLB: 0000 0001 0000 kkkk
    if (word & 0xFFF0) == 0x0100:
        k = word & 0x0F
        return Instruction(addr, "movlb", f"0x{k:X}", raw_words=[word])

    # Literal operations: 0000 1xxx kkkkkkkk
    if op_hi4 == 0x0 and (word >> 8) & 0xF >= 0x08:
        k = word & 0xFF
        sub = (word >> 8) & 0xF
        lit_ops = {
            0x08: "sublw", 0x09: "iorlw", 0x0A: "xorlw", 0x0B: "andlw",
            0x0C: "retlw", 0x0D: "mullw", 0x0E: "movlw", 0x0F: "addlw",
        }
        mn = lit_ops.get(sub)
        if mn:
            if mn == "retlw":
                return Instruction(addr, mn, f"0x{k:02X}", raw_words=[word])
            return Instruction(addr, mn, f"0x{k:02X}", raw_words=[word])

    # MULWF: 0000 001a ffff ffff
    if (word >> 9) == 0b0000001:
        a = (word >> 8) & 1
        f = word & 0xFF
        acc = "BANKED" if a else "ACCESS"
        reg = _file_reg_name(f, a)
        return Instruction(addr, "mulwf", f"{reg}, {acc}", raw_words=[word])

    # DECF: 0000 01da ffff ffff
    if (word >> 10) == 0b000001:
        d = (word >> 9) & 1
        a = (word >> 8) & 1
        f = word & 0xFF
        dest = "F" if d else "W"
        acc = "BANKED" if a else "ACCESS"
        reg = _file_reg_name(f, a)
        return Instruction(addr, "decf", f"{reg}, {dest}, {acc}", raw_words=[word])

    # Byte-oriented: 0bXXXX XXda ffff ffff (for opcodes 0x02-0x06, 0x1-0x3, etc.)
    byte_ops_4bit = {
        0x02: {0: "mulwf"},  # already handled above
        0x04: {0: "decf"},   # already handled above
    }

    # Major opcode groups (bits 15-12):
    # 0001: iorwf(00)/andwf(01)/xorwf(10)/comf(11)
    # 0010: addwfc(00)/addwf(01)/incf(10)/decfsz(11)
    # 0011: rrcf(00)/rlcf(01)/swapf(10)/incfsz(11)
    # 0100: rrncf(00)/rlncf(01)/infsnz(10)/dcfsnz(11)
    # 0101: movf(00)/subfwb(01)/subwfb(10)/subwf(11)
    # 0110: cpfslt(00)/cpfseq(01)/cpfsgt(10)/tstfsz(11)
    # 0111: setf(00)/clrf(01)/negf(10)/movwf(11)

    op_6 = (word >> 10) & 0x3F  # bits 15-10
    byte_ops = {
        0b000100: "iorwf",    0b000101: "andwf",
        0b000110: "xorwf",    0b000111: "comf",
        0b001000: "addwfc",   0b001001: "addwf",
        0b001010: "incf",     0b001011: "decfsz",
        0b001100: "rrcf",     0b001101: "rlcf",
        0b001110: "swapf",    0b001111: "incfsz",
        0b010000: "rrncf",    0b010001: "rlncf",
        0b010010: "infsnz",   0b010011: "dcfsnz",
        0b010100: "movf",     0b010101: "subfwb",
        0b010110: "subwfb",   0b010111: "subwf",
    }

    if op_6 in byte_ops:
        d = (word >> 9) & 1
        a = (word >> 8) & 1
        f = word & 0xFF
        dest = "F" if d else "W"
        acc = "BANKED" if a else "ACCESS"
        reg = _file_reg_name(f, a)
        return Instruction(addr, byte_ops[op_6], f"{reg}, {dest}, {acc}", raw_words=[word])

    # Single-operand group 0110: 0110 XXXa ffff ffff
    # bits 11-9 = subopcode, bit 8 = access
    if op_hi4 == 0x6:
        sub3 = (word >> 9) & 0x7
        a = (word >> 8) & 1
        f = word & 0xFF
        acc = "BANKED" if a else "ACCESS"
        reg = _file_reg_name(f, a)
        group6_ops = {
            0: "cpfslt", 1: "cpfseq", 2: "cpfsgt", 3: "tstfsz",
            4: "setf", 5: "clrf", 6: "negf", 7: "movwf",
        }
        mn = group6_ops.get(sub3)
        if mn:
            return Instruction(addr, mn, f"{reg}, {acc}", raw_words=[word])

    # Bit-oriented: 1000-1011 (btfss/btfsc/bsf/bcf)
    # 1000 bbba ffff ffff = bsf
    # 1001 bbba ffff ffff = bcf
    # 1010 bbba ffff ffff = btfss
    # 1011 bbba ffff ffff = btfsc
    if op_hi4 in (0x8, 0x9, 0xA, 0xB):
        bit_ops = {0x8: "bsf", 0x9: "bcf", 0xA: "btfss", 0xB: "btfsc"}
        bit = (word >> 9) & 7
        a = (word >> 8) & 1
        f = word & 0xFF
        acc = "BANKED" if a else "ACCESS"
        reg = _file_reg_name(f, a)
        return Instruction(addr, bit_ops[op_hi4], f"{reg}, {bit}, {acc}", raw_words=[word])

    return None


def decode_pic18_instruction(
    word: int, addr: int, mem: Dict[int, int], labels: Dict[int, str]
) -> Instruction:
    """Decode a single PIC18 instruction word (plus second word if two-word).

    Returns (Instruction, bytes_consumed).
    """
    op_hi4 = (word >> 12) & 0xF

    # --- Two-word instructions ---

    # MOVFF: 1100 ffff ffff ffff / 1111 ffff ffff ffff
    if op_hi4 == 0xC:
        fs = word & 0x0FFF
        word2 = mem.get(addr + 2, 0xFF) | (mem.get(addr + 3, 0xFF) << 8)
        fd = word2 & 0x0FFF
        sfrs = _get_sfr_names()
        fs_name = sfrs.get(fs, _ram_name(fs) if fs < 0xF00 else f"0x{fs:03X}")
        fd_name = sfrs.get(fd, _ram_name(fd) if fd < 0xF00 else f"0x{fd:03X}")
        return Instruction(addr, "movff", f"{fs_name}, {fd_name}", size=4,
                          raw_words=[word, word2])

    # CALL: 1110 110s kkkk kkkk / 1111 kkkk kkkk kkkk
    if (word & 0xFE00) == 0xEC00:
        s = (word >> 8) & 1
        word2 = mem.get(addr + 2, 0xFF) | (mem.get(addr + 3, 0xFF) << 8)
        target = (((word2 & 0x0FFF) << 8) | (word & 0x00FF)) << 1
        label = labels.get(target, f"loc_{target:04X}")
        return Instruction(addr, "call", f"{label}, 0x{s:X}", size=4,
                          is_branch=True, branch_target=target,
                          raw_words=[word, word2])

    # GOTO: 1110 1111 kkkk kkkk / 1111 kkkk kkkk kkkk
    if (word & 0xFF00) == 0xEF00:
        word2 = mem.get(addr + 2, 0xFF) | (mem.get(addr + 3, 0xFF) << 8)
        target = (((word2 & 0x0FFF) << 8) | (word & 0x00FF)) << 1
        label = labels.get(target, f"loc_{target:04X}")
        return Instruction(addr, "goto", label, size=4,
                          is_branch=True, branch_target=target,
                          raw_words=[word, word2])

    # LFSR: 1110 1110 00ff kkkk / 1111 0000 kkkk kkkk
    if (word & 0xFFC0) == 0xEE00:
        fsr_n = (word >> 4) & 3
        k_hi = word & 0x0F
        word2 = mem.get(addr + 2, 0xFF) | (mem.get(addr + 3, 0xFF) << 8)
        k_lo = word2 & 0xFF
        k = (k_hi << 8) | k_lo
        return Instruction(addr, "lfsr", f"FSR{fsr_n}, 0x{k:04X}", size=4,
                          raw_words=[word, word2])

    # --- Relative branches ---

    # BRA: 1101 0nnn nnnn nnnn (11-bit signed)
    if (word & 0xF800) == 0xD000:
        k = word & 0x7FF
        target = addr + 2 + 2 * _sign_extend(k, 11)
        label = labels.get(target, f"loc_{target:04X}")
        return Instruction(addr, "bra", label, is_branch=True,
                          branch_target=target, raw_words=[word])

    # RCALL: 1101 1nnn nnnn nnnn (11-bit signed)
    if (word & 0xF800) == 0xD800:
        k = word & 0x7FF
        target = addr + 2 + 2 * _sign_extend(k, 11)
        label = labels.get(target, f"loc_{target:04X}")
        return Instruction(addr, "rcall", label, is_branch=True,
                          branch_target=target, raw_words=[word])

    # Conditional branches: 1110 0xxx nnnn nnnn (8-bit signed)
    cond_branches = {
        0xE0: "bz", 0xE1: "bnz", 0xE2: "bc", 0xE3: "bnc",
        0xE4: "bov", 0xE5: "bnov", 0xE6: "bn", 0xE7: "bnn",
    }
    hi_byte = (word >> 8) & 0xFF
    if hi_byte in cond_branches:
        k = word & 0xFF
        target = addr + 2 + 2 * _sign_extend(k, 8)
        label = labels.get(target, f"loc_{target:04X}")
        return Instruction(addr, cond_branches[hi_byte], label,
                          is_branch=True, branch_target=target,
                          raw_words=[word])

    # --- Single-word decoded above ---
    result = _decode_byte_oriented(word, addr)
    if result:
        return result

    # Undecodable — emit as dw
    return Instruction(addr, "dw", f"0x{word:04X}", raw_words=[word])


# ---------------------------------------------------------------------------
# TBLPTR load pattern detection and conversion
# ---------------------------------------------------------------------------

def _try_parse_hex(s: str) -> Optional[int]:
    """Try to parse a hex operand like 0x1A or bail."""
    try:
        return int(s, 16)
    except ValueError:
        return None


def _get_movwf_tblptr_target(instr: Instruction) -> Optional[str]:
    """If instr is 'movwf TBLPTRx, ACCESS', return 'TBLPTRL'/'TBLPTRH'/'TBLPTRU'."""
    if instr.mnemonic == "movwf":
        tgt = instr.operands.split(",")[0].strip()
        if tgt in ("TBLPTRL", "TBLPTRH", "TBLPTRU"):
            return tgt
    return None


def _find_label_for_addr(addr: int, labels: Dict[int, str]) -> Optional[str]:
    """Find a label for a target address, checking all label sources."""
    if addr in labels:
        return labels[addr]
    for daddr, (dname, _) in _USB_DATA_LABELS.items():
        if daddr == addr:
            return dname
    for daddr, (dname, _) in _INLINE_DATA_LABELS.items():
        if daddr == addr:
            return dname
    return None


def _convert_tblptr_loads(instructions: list[Instruction], labels: Dict[int, str]) -> None:
    """Post-process instruction list to convert TBLPTR loads to label refs."""
    n = len(instructions)
    converted: set[int] = set()  # indices already converted

    for i in range(n - 1):
        if i in converted:
            continue
        cur = instructions[i]
        nxt = instructions[i + 1]

        # --- Pattern: addlw <imm> / movwf TBLPTRL ---
        if cur.mnemonic == "addlw" and _get_movwf_tblptr_target(nxt) == "TBLPTRL":
            val = _try_parse_hex(cur.operands)
            if val is None:
                continue
            # Look for TBLPTRH load nearby
            for j in range(i + 2, min(i + 8, n - 1)):
                cj = instructions[j]
                nj = instructions[j + 1] if j + 1 < n else None
                if cj.mnemonic == "movlw" and nj and _get_movwf_tblptr_target(nj) == "TBLPTRH":
                    h_val = _try_parse_hex(cj.operands)
                    if h_val is None:
                        break
                    key = (h_val, val)
                    if key in _TBLPTR_ADDLW_TARGETS:
                        lbl = _TBLPTR_ADDLW_TARGETS[key]
                        cur.operands = f"LOW({lbl})"
                        cur.comment = f"indexed TBLPTR -> {lbl}"
                        cj.operands = f"HIGH({lbl})"
                        converted.update([i, j])
                    break
            continue

        # --- Pattern: movlw <imm> / movwf TBLPTRx ---
        if cur.mnemonic != "movlw":
            continue
        tgt = _get_movwf_tblptr_target(nxt)
        if tgt is None:
            continue

        val = _try_parse_hex(cur.operands)
        if val is None:
            continue

        # Collect all TBLPTR component values from nearby instructions
        components: Dict[str, tuple[int, int, int]] = {}  # reg -> (value, instr_idx, movwf_idx)
        components[tgt] = (val, i, i + 1)

        # Scan ahead for more TBLPTR loads (movlw/movwf or clrf patterns)
        j = i + 2
        while j < min(i + 10, n - 1):
            ij = instructions[j]
            nj = instructions[j + 1] if j + 1 < n else None

            # movlw <imm> / movwf TBLPTRx
            if ij.mnemonic == "movlw" and nj:
                tgt2 = _get_movwf_tblptr_target(nj)
                if tgt2 and tgt2 not in components:
                    v2 = _try_parse_hex(ij.operands)
                    if v2 is not None:
                        components[tgt2] = (v2, j, j + 1)
                        j += 2
                        continue

            # clrf TBLPTRx (equivalent to movlw 0x00 + movwf)
            if ij.mnemonic == "clrf":
                clrf_tgt = ij.operands.split(",")[0].strip()
                if clrf_tgt in ("TBLPTRL", "TBLPTRH", "TBLPTRU") and clrf_tgt not in components:
                    components[clrf_tgt] = (0x00, j, j)
                    j += 1
                    continue

            j += 1  # skip non-TBLPTR instructions but keep looking

        # Standalone TBLPTRU=0 (clearing after config access):
        # If only TBLPTRU is loaded and value is 0, emit UPPER(0x0000)
        if tgt == "TBLPTRU" and val == 0 and "TBLPTRL" not in components and "TBLPTRH" not in components:
            cur.operands = "UPPER(0x0000)"
            cur.comment = "clear TBLPTRU to program space"
            converted.add(i)
            continue

        # Reconstruct target address from collected components
        u = components.get("TBLPTRU", (0, -1, -1))[0]
        h = components.get("TBLPTRH", (None, -1, -1))[0]
        l = components.get("TBLPTRL", (None, -1, -1))[0]

        if h is None or l is None:
            continue

        target_addr = (u << 16) | (h << 8) | l
        lbl = _find_label_for_addr(target_addr, labels)
        if not lbl:
            # Check direct targets table
            key3 = (u, h, l)
            lbl = _TBLPTR_DIRECT_TARGETS.get(key3)
        if not lbl:
            continue

        # Apply label conversion to all collected components
        for reg, (_, li, mi) in components.items():
            if reg == "TBLPTRL":
                if instructions[li].mnemonic == "movlw":
                    instructions[li].operands = f"LOW({lbl})"
                    instructions[li].comment = f"TBLPTR -> {lbl}"
            elif reg == "TBLPTRH":
                if instructions[li].mnemonic == "movlw":
                    instructions[li].operands = f"HIGH({lbl})"
            elif reg == "TBLPTRU":
                if instructions[li].mnemonic == "movlw":
                    instructions[li].operands = f"UPPER({lbl})"
            converted.add(li)
            converted.add(mi)


# ---------------------------------------------------------------------------
# Assembly source emitter
# ---------------------------------------------------------------------------

def _emit_data_region(mem: Dict[int, int], start: int, end: int,
                      labels: Dict[int, str], all_labels: Dict[int, str]) -> list[str]:
    """Emit a data region as dw directives with word-aligned labels.

    PIC18 flash is word-addressed; gpasm `db` pads odd-count lines with 0x00.
    We emit `dw` values (2 bytes each) to guarantee byte-exact output.
    Labels at odd addresses use EQU based on the preceding even-address label.
    """
    lines: list[str] = []

    # Collect all labels in this region (USB, inline, and code labels)
    region_labels: Dict[int, str] = {}
    for addr in range(start, end):
        if addr in _USB_DATA_LABELS:
            region_labels[addr] = _USB_DATA_LABELS[addr][0]
        elif addr in _INLINE_DATA_LABELS:
            region_labels[addr] = _INLINE_DATA_LABELS[addr][0]
        elif addr in all_labels:
            region_labels[addr] = all_labels[addr]

    # Split labels into even-address (positional) and odd-address (EQU)
    odd_labels: Dict[int, str] = {}
    even_labels: Dict[int, str] = {}
    for addr, name in sorted(region_labels.items()):
        if addr & 1:
            odd_labels[addr] = name
        else:
            even_labels[addr] = name

    # Emit data as dw directives with even-aligned labels
    addr = start
    if addr & 1:
        addr -= 1  # align down to word boundary

    while addr < end:
        # Emit labels at this even address
        if addr in even_labels:
            lbl_name = even_labels[addr]
            comment = ""
            if addr in _USB_DATA_LABELS:
                comment = f"  ; {_USB_DATA_LABELS[addr][1]}"
            elif addr in _INLINE_DATA_LABELS:
                comment = f"  ; {_INLINE_DATA_LABELS[addr][1]}"
            lines.append(f"{lbl_name}:{comment}")

        # Emit up to 8 words (16 bytes) per dw line
        chunk_words = []
        chunk_addr = addr
        max_words = 8
        while len(chunk_words) < max_words and chunk_addr < end:
            # Don't cross an even label boundary (except at start)
            if chunk_addr > addr and chunk_addr in even_labels:
                break
            lo = mem.get(chunk_addr, 0xFF)
            hi = mem.get(chunk_addr + 1, 0xFF) if chunk_addr + 1 < end else 0xFF
            chunk_words.append((hi << 8) | lo)
            chunk_addr += 2

        hex_str = ", ".join(f"0x{w:04X}" for w in chunk_words)
        lines.append(f"    dw  {hex_str}")
        addr = chunk_addr

    # Emit EQU for odd-addressed labels AFTER data (avoids forward refs)
    if odd_labels:
        even_addrs = sorted(even_labels.keys())
        lines.append("")
        lines.append("; Sub-labels at odd byte addresses (EQU offsets)")
        for odd_addr, odd_name in sorted(odd_labels.items()):
            base_addr = None
            base_name = None
            for ea in reversed(even_addrs):
                if ea <= odd_addr:
                    base_addr = ea
                    base_name = even_labels[ea]
                    break
            if base_addr is not None:
                offset = odd_addr - base_addr
                comment = ""
                if odd_addr in _USB_DATA_LABELS:
                    comment = f"  ; {_USB_DATA_LABELS[odd_addr][1]}"
                lines.append(f"{odd_name}  EQU  {base_name} + 0x{offset:X}{comment}")

    return lines


def _emit_preset_table(mem: Dict[int, int]) -> list[str]:
    """Emit the DSP preset table as dw directives."""
    lines = [
        "",
        "; ---------------------------------------------------------------------------",
        "; DSP Preset Table A",
        "; ---------------------------------------------------------------------------",
        "    org 0x5600",
        "preset_table_a:",
    ]
    for base in range(0x5600, 0x6000, 16):
        words = []
        for off in range(0, 16, 2):
            lo = mem.get(base + off, 0xFF)
            hi = mem.get(base + off + 1, 0xFF)
            words.append(f"0x{(hi << 8) | lo:04X}")
        lines.append(f"    dw  {', '.join(words)}")
    return lines


def _emit_eeprom(mem: Dict[int, int]) -> list[str]:
    """Emit EEPROM initialization data."""
    lines = [
        "",
        "; ---------------------------------------------------------------------------",
        "; EEPROM Data",
        "; ---------------------------------------------------------------------------",
        "    org 0xF00000",
        "eeprom_data:",
    ]
    for base in range(0xF00000, 0xF00100, 16):
        byte_vals = [mem.get(base + i, 0xFF) for i in range(16)]
        hex_str = ", ".join(f"0x{b:02X}" for b in byte_vals)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in byte_vals)
        lines.append(f"    db  {hex_str}  ; {ascii_str}")
    return lines


def _emit_config(mem: Dict[int, int]) -> list[str]:
    """Emit configuration bit directives using raw hex values."""
    lines = [
        "",
        "; ---------------------------------------------------------------------------",
        "; Configuration Bits",
        "; ---------------------------------------------------------------------------",
    ]
    for addr, reg_name in _CONFIG_REGS:
        val = mem.get(addr, 0xFF)
        lines.append(f"    __CONFIG  {reg_name}, 0x{val:02X}")
    return lines


def _collect_all_ram_addresses(mem: Dict[int, int], labels: Dict[int, str]) -> set[int]:
    """Scan all code regions to find RAM addresses used by instructions."""
    ram_addrs: set[int] = set()

    for start, end, rtype in [
        (0x1000, 0x1018, "code"),
        (0x10AC, 0x47E6, "code"),
        (0x47FC, 0x4970, "code"),
    ]:
        addr = start
        while addr < end:
            word = mem.get(addr, 0xFF) | (mem.get(addr + 1, 0xFF) << 8)
            instr = decode_pic18_instruction(word, addr, mem, labels)

            # Extract RAM references from the operands string
            if instr.mnemonic == "movff":
                # MOVFF has two 12-bit addresses
                fs = instr.raw_words[0] & 0x0FFF
                fd = instr.raw_words[1] & 0x0FFF
                if fs < 0xF00:
                    ram_addrs.add(fs)
                if fd < 0xF00:
                    ram_addrs.add(fd)
            elif instr.mnemonic not in ("dw", "nop", "sleep", "clrwdt", "push", "pop",
                                         "daw", "reset", "retfie", "return",
                                         "tblrd*", "tblrd*+", "tblrd*-", "tblrd+*",
                                         "tblwt*", "tblwt*+", "tblwt*-", "tblwt+*",
                                         "goto", "call", "bra", "rcall",
                                         "bz", "bnz", "bc", "bnc", "bov", "bnov", "bn", "bnn",
                                         "movlw", "addlw", "sublw", "iorlw", "xorlw",
                                         "andlw", "retlw", "mullw", "lfsr"):
                # Byte-oriented or bit-oriented — f register
                f = instr.raw_words[0] & 0xFF if instr.raw_words else 0
                a = (instr.raw_words[0] >> 8) & 1 if instr.raw_words else 0
                if a == 0 and f < 0x60:
                    ram_addrs.add(f)
                elif a == 1:
                    ram_addrs.add(f)

            addr += instr.size
    return ram_addrs


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def convert(output_path: Path | None = None) -> Path:
    """Convert stock V2.3 hex to gpasm-compatible V3.0 assembly source.

    Also emits dlcp_main_ram.inc alongside the .asm file.
    Returns the path to the generated .asm file.
    """
    if output_path is None:
        output_path = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"

    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    mem = parse_intel_hex(STOCK_MAIN_HEX)
    labels = _build_label_pool()

    # Add USB data labels and inline data labels to the pool
    all_labels = dict(labels)
    for addr, (name, _) in _USB_DATA_LABELS.items():
        all_labels[addr] = name
    for addr, (name, _) in _INLINE_DATA_LABELS.items():
        all_labels[addr] = name

    # Decode code regions
    code_regions = [
        (0x1000, 0x1018),
        (0x10AC, 0x47E6),
        (0x47FC, 0x4970),
    ]

    all_instructions: list[Instruction] = []
    extra_targets: set[int] = set()

    for code_start, code_end in code_regions:
        addr = code_start
        while addr < code_end:
            word = mem.get(addr, 0xFF) | (mem.get(addr + 1, 0xFF) << 8)
            instr = decode_pic18_instruction(word, addr, mem, all_labels)
            all_instructions.append(instr)
            if instr.branch_target is not None:
                extra_targets.add(instr.branch_target)
            addr += instr.size

    # Add generated labels for branch targets not in the label pool
    for target in extra_targets:
        if target not in all_labels:
            all_labels[target] = f"loc_{target:04X}"

    # Re-decode with complete label pool (so branch targets resolve)
    all_instructions = []
    for code_start, code_end in code_regions:
        addr = code_start
        while addr < code_end:
            word = mem.get(addr, 0xFF) | (mem.get(addr + 1, 0xFF) << 8)
            instr = decode_pic18_instruction(word, addr, mem, all_labels)
            all_instructions.append(instr)
            addr += instr.size

    # Convert TBLPTR loads to label references
    _convert_tblptr_loads(all_instructions, all_labels)

    # Collect RAM addresses and generate RAM include
    ram_addrs = _collect_all_ram_addresses(mem, all_labels)
    _generate_ram_include(ram_addrs, output_dir / "dlcp_main_ram.inc")

    # Emit the assembly source
    lines: list[str] = []

    # Header
    lines.extend([
        "    LIST P=18F2455",
        '    #include <p18f2455.inc>',
        '    #include "dlcp_main_ram.inc"',
        "",
    ])

    # Config bits
    lines.extend(_emit_config(mem))
    lines.append("")

    # App entry
    lines.extend([
        "; ---------------------------------------------------------------------------",
        "; App Entry (0x1000)",
        "; ---------------------------------------------------------------------------",
        "    org 0x1000",
    ])

    # Emit entry code region (0x1000-0x1017)
    for instr in all_instructions:
        if instr.addr >= 0x1018:
            break
        _emit_instruction(lines, instr, all_labels)

    # USB data region
    lines.extend([
        "",
        "; ---------------------------------------------------------------------------",
        "; USB Descriptors and Data Tables (0x1018-0x10AB)",
        "; ---------------------------------------------------------------------------",
    ])
    lines.extend(_emit_data_region(mem, 0x1018, 0x10AC, labels, all_labels))

    # Main code region
    lines.extend([
        "",
        "; ---------------------------------------------------------------------------",
        "; Application Code",
        "; ---------------------------------------------------------------------------",
    ])
    for instr in all_instructions:
        if instr.addr < 0x10AC:
            continue
        if instr.addr >= 0x47E6:
            break
        _emit_instruction(lines, instr, all_labels)

    # Inline data table at 0x47E6
    lines.extend([
        "",
        "; ---------------------------------------------------------------------------",
        "; Inline Data Table (0x47E6-0x47FB)",
        "; ---------------------------------------------------------------------------",
    ])
    lines.extend(_emit_data_region(mem, 0x47E6, 0x47FC, labels, all_labels))

    # Remaining code after inline data
    lines.extend([
        "",
        "; ---------------------------------------------------------------------------",
        "; Remaining Code (0x47FC-0x496F)",
        "; ---------------------------------------------------------------------------",
    ])
    for instr in all_instructions:
        if instr.addr < 0x47FC:
            continue
        _emit_instruction(lines, instr, all_labels)

    # Erased flash padding
    lines.extend([
        "",
        "; ---------------------------------------------------------------------------",
        "; Erased Flash Padding",
        "; ---------------------------------------------------------------------------",
        "    fill 0xFFFF, (0x5600 - $) / 2",
    ])

    # Preset table
    lines.extend(_emit_preset_table(mem))

    # EEPROM
    lines.extend(_emit_eeprom(mem))

    # End
    lines.extend([
        "",
        "    END",
        "",
    ])

    output_path.write_text("\n".join(lines))
    return output_path


def _emit_instruction(lines: list[str], instr: Instruction, labels: Dict[int, str]) -> None:
    """Emit a single instruction with optional label prefix."""
    # Check if there's a label at this address
    label_name = labels.get(instr.addr)

    # Add section comment for functions
    if label_name and label_name.startswith("function_") or (
        label_name and not label_name.startswith("label_") and
        not label_name.startswith("loc_") and
        label_name in _SEMANTIC_FUNCTION_ADDRS
    ):
        lines.append("")

    if label_name:
        lines.append(f"{label_name}:")

    # Format instruction
    if instr.operands:
        asm_line = f"    {instr.mnemonic:<12s}{instr.operands}"
    else:
        asm_line = f"    {instr.mnemonic}"

    if instr.comment:
        asm_line = f"{asm_line:<52s}; {instr.comment}"

    lines.append(asm_line)


# Cache of semantic function addresses for section comment logic
_SEMANTIC_FUNCTION_ADDRS: set[str] = set()


def _generate_ram_include(ram_addrs: set[int], output_path: Path) -> None:
    """Generate dlcp_main_ram.inc with EQU definitions for all RAM variables."""
    lines = [
        "; DLCP MAIN V3.0 RAM variable definitions",
        "; Auto-generated by disasm_to_source.py",
        "",
    ]

    # Named RAM first
    named = {}
    unnamed = {}
    for addr in sorted(ram_addrs):
        if addr in _RAM_NAMES:
            named[addr] = _RAM_NAMES[addr]
        else:
            unnamed[addr] = f"ram_0x{addr:03X}"

    if named:
        lines.append("; --- Named RAM variables ---")
        for addr in sorted(named.keys()):
            name = named[addr]
            lines.append(f"{name:<28s}EQU  0x{addr:03X}")
        lines.append("")

    if unnamed:
        lines.append("; --- Unnamed RAM variables ---")
        for addr in sorted(unnamed.keys()):
            name = unnamed[addr]
            lines.append(f"{name:<28s}EQU  0x{addr:03X}")
        lines.append("")

    output_path.write_text("\n".join(lines))
