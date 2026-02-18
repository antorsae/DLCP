#!/usr/bin/env python3
"""
PIC18 Firmware Analyzer for HYPEX DLCP
Correctly parses Intel HEX and disassembles PIC18 code
"""

from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# PIC18 Instruction Set - opcode masks and mnemonics
PIC18_INSTRUCTIONS = [
    (0xFF00, 0xEF00, "GOTO", 2),  # GOTO k (2 words)
    (0xFF00, 0xEC00, "CALL", 2),  # CALL k (2 words)
    (0xFF00, 0xEE00, "LFSR", 1),  # LFSR f, k
    (0xFF00, 0xF000, "BRA", 1),  # BRA n
    (0xFC00, 0xD000, "RCALL", 1),  # RCALL n
    (0xFFE0, 0xF020, "CALLW", 1),  # CALLW
    (0xFF00, 0xC000, "MOVFF", 2),  # MOVFF fs, fd (2 words)
    (0xFF00, 0x0100, "MOVLB", 1),  # MOVLB k
    (0xFFC0, 0x6E00, "MOVWF", 1),  # MOVWF f, a
    (0xFFC0, 0x5000, "MOVF", 1),  # MOVF f, d, a
    (0xFFC0, 0x0E00, "MOVLW", 1),  # MOVLW k
    (0xFFC0, 0x0F00, "ADDLW", 1),  # ADDLW k
    (0xFFC0, 0x0900, "IORLW", 1),  # IORLW k
    (0xFFC0, 0x0A00, "XORLW", 1),  # XORLW k
    (0xFFC0, 0x0800, "SUBLW", 1),  # SUBLW k
    (0xFFC0, 0x0D00, "MULLW", 1),  # MULLW k
    (0xFFC0, 0x2400, "ADDWF", 1),  # ADDWF f, d, a
    (0xFFC0, 0x2800, "INCF", 1),  # INCF f, d, a
    (0xFFC0, 0x2C00, "RLCF", 1),  # RLCF f, d, a
    (0xFFC0, 0x3400, "DECF", 1),  # DECF f, d, a
    (0xFFC0, 0x3800, "RLNCF", 1),  # RLNCF f, d, a
    (0xFFC0, 0x3C00, "INFSNZ", 1),  # INFSNZ f, d, a
    (0xFFC0, 0x4000, "DECFSZ", 1),  # DECFSZ f, d, a
    (0xFFC0, 0x4400, "RRCF", 1),  # RRCF f, d, a
    (0xFFC0, 0x4800, "SWAPF", 1),  # SWAPF f, d, a
    (0xFFC0, 0x4C00, "INCFSZ", 1),  # INCFSZ f, d, a
    (0xFFC0, 0x5000, "MOVF", 1),  # MOVF f, d, a
    (0xFFC0, 0x5400, "RLNCF", 1),  # RLNCF f, d, a (alt)
    (0xFFC0, 0x5800, "SUBWF", 1),  # SUBWF f, d, a
    (0xFFC0, 0x5C00, "SUBWFB", 1),  # SUBWFB f, d, a
    (0xFFC0, 0x6000, "CPFSEQ", 1),  # CPFSEQ f, a
    (0xFFC0, 0x6200, "CPFSGT", 1),  # CPFSGT f, a
    (0xFFC0, 0x6400, "CPFSLT", 1),  # CPFSLT f, a
    (0xFFC0, 0x6600, "TSTFSZ", 1),  # TSTFSZ f, a
    (0xFFC0, 0x6800, "SETF", 1),  # SETF f, a
    (0xFFC0, 0x6A00, "CLRF", 1),  # CLRF f, a
    (0xFFC0, 0x6C00, "NEGF", 1),  # NEGF f, a
    (0xFFC0, 0x7000, "BTG", 1),  # BTG f, b, a
    (0xFFC0, 0x8000, "BSF", 1),  # BSF f, b, a
    (0xFFC0, 0x9000, "BCF", 1),  # BCF f, b, a
    (0xFFC0, 0xA000, "BTFSS", 1),  # BTFSS f, b, a
    (0xFFC0, 0xB000, "BTFSC", 1),  # BTFSC f, b, a
    (0xFFFF, 0x0003, "SLEEP", 1),  # SLEEP
    (0xFFFF, 0x0004, "CLRWDT", 1),  # CLRWDT
    (0xFFFF, 0x0000, "NOP", 1),  # NOP
    (0xFFFF, 0x0005, "PUSH", 1),  # PUSH
    (0xFFFF, 0x0006, "POP", 1),  # POP
    (0xFFFF, 0x0007, "DAW", 1),  # DAW
    (0xFFFF, 0x0008, "TBLRD*", 1),  # TBLRD*
    (0xFFFF, 0x0009, "TBLRD*+", 1),  # TBLRD*+
    (0xFFFF, 0x000A, "TBLRD*-", 1),  # TBLRD*-
    (0xFFFF, 0x000B, "TBLRD+*", 1),  # TBLRD+*
    (0xFFFF, 0x000C, "TBLWT*", 1),  # TBLWT*
    (0xFFFF, 0x000D, "TBLWT*+", 1),  # TBLWT*+
    (0xFFFF, 0x000E, "TBLWT*-", 1),  # TBLWT*-
    (0xFFFF, 0x000F, "TBLWT+*", 1),  # TBLWT+*
    (0xFFFF, 0x0010, "RETFIE", 1),  # RETFIE
    (0xFFFF, 0x0011, "RETURN", 1),  # RETURN
    (0xFFFF, 0x0012, "RETLW", 1),  # RETLW k (needs k)
    (0xFF00, 0x0012, "RETLW", 1),  # RETLW k
    (0xFFE0, 0xF020, "CALLW", 1),  # CALLW
    (0xFFFF, 0x0019, "RETLW", 1),  # RETLW with s=1
    (0xFF00, 0x0200, "MULWF", 1),  # MULWF f, a
    (0xFF00, 0x0300, "ADDWFC", 1),  # ADDWFC f, d, a
    (0xFFC0, 0x2000, "ADDWFC", 1),  # ADDWFC f, d, a
    (0xFE00, 0xE000, "BZ", 1),  # BZ
    (0xFE00, 0xE200, "BNZ", 1),  # BNZ
    (0xFE00, 0xE400, "BC", 1),  # BC
    (0xFE00, 0xE600, "BNC", 1),  # BNC
    (0xFE00, 0xE800, "BOV", 1),  # BOV
    (0xFE00, 0xEA00, "BNOV", 1),  # BNOV
    (0xFE00, 0xEC00, "BN", 1),  # BN
    (0xFE00, 0xEE00, "BNN", 1),  # BNN
    (0xFF00, 0x0400, "CLRW", 1),  # CLRW (actually IORLW 0xFF variant)
    (0xFC00, 0x7000, "BTG", 1),  # BTG f, b, a
    (0xF800, 0xF000, "BRA", 1),  # BRA n
    (0xC000, 0xC000, "MOVFF", 2),  # MOVFF fs, fd
    (0xFC00, 0x6C00, "NEGF", 1),  # NEGF f, a
    (0xFC00, 0x6A00, "CLRF", 1),  # CLRF f, a
    (0xFC00, 0x6800, "SETF", 1),  # SETF f, a
    (0xFE00, 0x6E00, "MOVWF", 1),  # MOVWF f, a
    (0xFC00, 0x5000, "MOVF", 1),  # MOVF f, d, a
]


@dataclass
class IntelHexRecord:
    byte_count: int
    address: int
    record_type: int
    data: bytes
    checksum: int


@dataclass
class PIC18Instruction:
    address: int
    raw_words: List[int]
    mnemonic: str
    operands: str
    size_words: int
    is_valid: bool = True
    is_branch: bool = False
    branch_target: Optional[int] = None


def parse_intel_hex(
    filepath: str,
) -> Tuple[Dict[int, int], Dict[int, List[Tuple[int, int]]]]:
    """Parse Intel HEX file and return memory regions."""
    memory = {}
    regions = defaultdict(list)
    extended_addr = 0

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line.startswith(":"):
                continue

            byte_count = int(line[1:3], 16)
            address = int(line[3:7], 16)
            record_type = int(line[7:9], 16)

            data_hex = line[9 : 9 + byte_count * 2]
            data = bytes.fromhex(data_hex)
            checksum = int(line[9 + byte_count * 2 : 9 + byte_count * 2 + 2], 16)

            if record_type == 0x00:  # Data record
                base_addr = extended_addr + address
                for i, b in enumerate(data):
                    memory[base_addr + i] = b
                regions[extended_addr >> 16].append((base_addr, len(data)))
            elif record_type == 0x01:  # EOF
                break
            elif record_type == 0x04:  # Extended linear address
                extended_addr = int(data_hex, 16) << 16
            elif record_type == 0x02:  # Extended segment address
                extended_addr = int(data_hex, 16) << 4

    return memory, dict(regions)


def get_word(memory: Dict[int, int], addr: int) -> Optional[int]:
    """Get a 16-bit word from memory (little-endian)."""
    if addr in memory and addr + 1 in memory:
        return memory[addr] | (memory[addr + 1] << 8)
    return None


def decode_pic18_instruction(
    word1: int, word2: Optional[int] = None
) -> Tuple[str, str, int, bool, Optional[int]]:
    """Decode a PIC18 instruction. Returns (mnemonic, operands, size_words, is_branch, branch_target)."""

    # GOTO - 4-bit opcode + 20-bit address
    if (word1 & 0xFF00) == 0xEF00:
        if word2 is not None:
            # Full 20-bit address: k7:k0 from word1 low byte, k19:k8 from word2 low 12 bits
            k_low = word1 & 0x00FF  # bits 7:0
            k_high = word2 & 0x0FFF  # bits 19:8
            target = (k_high << 8) | k_low
            target = target * 2  # Convert word address to byte address
            return "GOTO", f"0x{target:04X}", 2, True, target
        return "GOTO", "??", 2, True, None

    # CALL - 4-bit opcode + 20-bit address
    if (word1 & 0xFF00) == 0xEC00:
        if word2 is not None:
            k_low = word1 & 0x00FF
            k_high = word2 & 0x0FFF
            s = (word2 >> 8) & 0x01
            target = (k_high << 8) | k_low
            target = target * 2
            if s:
                return "CALL", f"0x{target:04X}, 1", 2, True, target
            return "CALL", f"0x{target:04X}", 2, True, target
        return "CALL", "??", 2, True, None

    # MOVFF - 2-word instruction
    if (word1 & 0xC000) == 0xC000:
        if word2 is not None:
            fs = word1 & 0x0FFF
            fd = word2 & 0x0FFF
            return "MOVFF", f"0x{fs:03X}, 0x{fd:03X}", 2, False, None
        return "MOVFF", "??", 2, False, None

    # LFSR - load FSR register
    if (word1 & 0xFF00) == 0xEE00:
        if word2 is not None:
            f = (word1 >> 4) & 0x03
            k = word2 & 0x0FFF
            return "LFSR", f"{f}, 0x{k:03X}", 2, False, None
        return "LFSR", "??", 2, False, None

    # BRA - relative branch
    if (word1 & 0xF800) == 0xD000 or (word1 & 0xFF00) == 0xD000:
        # Actually RCALL is 0xD000-0xD7FF, BRA is 0xD800-0xDFFF
        pass

    if (word1 & 0xF800) == 0xD000:
        n = word1 & 0x07FF
        if n & 0x0400:  # Sign extend
            n = n - 0x0800
        return "RCALL", f"0x{n:03X}", 1, True, None

    if (word1 & 0xF800) == 0xD800:
        n = word1 & 0x07FF
        if n & 0x0400:  # Sign extend
            n = n - 0x0800
        return "BRA", f"*{n:+d}", 1, True, None

    # Conditional branches (BZ, BNZ, BC, BNC, etc.)
    if (word1 & 0xFF00) == 0xE000:
        n = word1 & 0x00FF
        if n & 0x80:  # Sign extend
            n = n - 0x100
        return "BZ", f"*{n:+d}", 1, True, None
    if (word1 & 0xFF00) == 0xE100:
        n = word1 & 0x00FF
        if n & 0x80:
            n = n - 0x100
        return "BNZ", f"*{n:+d}", 1, True, None
    if (word1 & 0xFF00) == 0xE200:
        n = word1 & 0x00FF
        if n & 0x80:
            n = n - 0x100
        return "BC", f"*{n:+d}", 1, True, None
    if (word1 & 0xFF00) == 0xE300:
        n = word1 & 0x00FF
        if n & 0x80:
            n = n - 0x100
        return "BNC", f"*{n:+d}", 1, True, None
    if (word1 & 0xFF00) == 0xE400:
        n = word1 & 0x00FF
        if n & 0x80:
            n = n - 0x100
        return "BOV", f"*{n:+d}", 1, True, None
    if (word1 & 0xFF00) == 0xE500:
        n = word1 & 0x00FF
        if n & 0x80:
            n = n - 0x100
        return "BNOV", f"*{n:+d}", 1, True, None
    if (word1 & 0xFF00) == 0xE600:
        n = word1 & 0x00FF
        if n & 0x80:
            n = n - 0x100
        return "BN", f"*{n:+d}", 1, True, None
    if (word1 & 0xFF00) == 0xE700:
        n = word1 & 0x00FF
        if n & 0x80:
            n = n - 0x100
        return "BNN", f"*{n:+d}", 1, True, None

    # MOVLW
    if (word1 & 0xFF00) == 0x0E00:
        k = word1 & 0x00FF
        return "MOVLW", f"0x{k:02X}", 1, False, None

    # ADDLW
    if (word1 & 0xFF00) == 0x0F00:
        k = word1 & 0x00FF
        return "ADDLW", f"0x{k:02X}", 1, False, None

    # IORLW
    if (word1 & 0xFF00) == 0x0900:
        k = word1 & 0x00FF
        return "IORLW", f"0x{k:02X}", 1, False, None

    # XORLW
    if (word1 & 0xFF00) == 0x0A00:
        k = word1 & 0x00FF
        return "XORLW", f"0x{k:02X}", 1, False, None

    # ANDLW
    if (word1 & 0xFF00) == 0x0B00:
        k = word1 & 0x00FF
        return "ANDLW", f"0x{k:02X}", 1, False, None

    # SUBLW
    if (word1 & 0xFF00) == 0x0800:
        k = word1 & 0x00FF
        return "SUBLW", f"0x{k:02X}", 1, False, None

    # MULLW
    if (word1 & 0xFF00) == 0x0D00:
        k = word1 & 0x00FF
        return "MULLW", f"0x{k:02X}", 1, False, None

    # RETLW
    if (word1 & 0xFF00) == 0x0C00:
        k = word1 & 0x00FF
        return "RETLW", f"0x{k:02X}", 1, False, None

    # MOVLB
    if (word1 & 0xFF00) == 0x0100:
        k = word1 & 0x00FF
        return "MOVLB", f"0x{k:02X}", 1, False, None

    # MOVWF
    if (word1 & 0xFE00) == 0x6E00:
        f = word1 & 0x00FF
        a = (word1 >> 8) & 0x01
        if a:
            return "MOVWF", f"0x{f:02X}, BSR", 1, False, None
        return "MOVWF", f"0x{f:02X}, ACCESS", 1, False, None

    # CLRF
    if (word1 & 0xFC00) == 0x6A00:
        f = word1 & 0x00FF
        a = (word1 >> 8) & 0x01
        if a:
            return "CLRF", f"0x{f:02X}, BSR", 1, False, None
        return "CLRF", f"0x{f:02X}, ACCESS", 1, False, None

    # SETF
    if (word1 & 0xFC00) == 0x6800:
        f = word1 & 0x00FF
        a = (word1 >> 8) & 0x01
        return "SETF", f"0x{f:02X}, {'BSR' if a else 'ACCESS'}", 1, False, None

    # MOVF
    if (word1 & 0xFC00) == 0x5000:
        f = word1 & 0x00FF
        d = (word1 >> 9) & 0x01
        a = (word1 >> 8) & 0x01
        return (
            "MOVF",
            f"0x{f:02X}, {'F' if d else 'W'}, {'BSR' if a else 'ACCESS'}",
            1,
            False,
            None,
        )

    # ADDWF
    if (word1 & 0xFC00) == 0x2400:
        f = word1 & 0x00FF
        d = (word1 >> 9) & 0x01
        a = (word1 >> 8) & 0x01
        return (
            "ADDWF",
            f"0x{f:02X}, {'F' if d else 'W'}, {'BSR' if a else 'ACCESS'}",
            1,
            False,
            None,
        )

    # SUBWF
    if (word1 & 0xFC00) == 0x5800:
        f = word1 & 0x00FF
        d = (word1 >> 9) & 0x01
        a = (word1 >> 8) & 0x01
        return (
            "SUBWF",
            f"0x{f:02X}, {'F' if d else 'W'}, {'BSR' if a else 'ACCESS'}",
            1,
            False,
            None,
        )

    # INCF
    if (word1 & 0xFC00) == 0x2800:
        f = word1 & 0x00FF
        d = (word1 >> 9) & 0x01
        a = (word1 >> 8) & 0x01
        return (
            "INCF",
            f"0x{f:02X}, {'F' if d else 'W'}, {'BSR' if a else 'ACCESS'}",
            1,
            False,
            None,
        )

    # DECF
    if (word1 & 0xFC00) == 0x0400:
        f = word1 & 0x00FF
        d = (word1 >> 9) & 0x01
        a = (word1 >> 8) & 0x01
        return (
            "DECF",
            f"0x{f:02X}, {'F' if d else 'W'}, {'BSR' if a else 'ACCESS'}",
            1,
            False,
            None,
        )

    # DECFSZ
    if (word1 & 0xFC00) == 0x4C00:
        f = word1 & 0x00FF
        d = (word1 >> 9) & 0x01
        a = (word1 >> 8) & 0x01
        return (
            "DECFSZ",
            f"0x{f:02X}, {'F' if d else 'W'}, {'BSR' if a else 'ACCESS'}",
            1,
            False,
            None,
        )

    # INCFSZ
    if (word1 & 0xFC00) == 0x3C00:
        f = word1 & 0x00FF
        d = (word1 >> 9) & 0x01
        a = (word1 >> 8) & 0x01
        return (
            "INCFSZ",
            f"0x{f:02X}, {'F' if d else 'W'}, {'BSR' if a else 'ACCESS'}",
            1,
            False,
            None,
        )

    # BSF
    if (word1 & 0xFC00) == 0x8000:
        f = word1 & 0x00FF
        b = (word1 >> 9) & 0x07
        a = (word1 >> 8) & 0x01
        return "BSF", f"0x{f:02X}, {b}, {'BSR' if a else 'ACCESS'}", 1, False, None

    # BCF
    if (word1 & 0xFC00) == 0x9000:
        f = word1 & 0x00FF
        b = (word1 >> 9) & 0x07
        a = (word1 >> 8) & 0x01
        return "BCF", f"0x{f:02X}, {b}, {'BSR' if a else 'ACCESS'}", 1, False, None

    # BTFSS
    if (word1 & 0xFC00) == 0xA000:
        f = word1 & 0x00FF
        b = (word1 >> 9) & 0x07
        a = (word1 >> 8) & 0x01
        return "BTFSS", f"0x{f:02X}, {b}, {'BSR' if a else 'ACCESS'}", 1, False, None

    # BTFSC
    if (word1 & 0xFC00) == 0xB000:
        f = word1 & 0x00FF
        b = (word1 >> 9) & 0x07
        a = (word1 >> 8) & 0x01
        return "BTFSC", f"0x{f:02X}, {b}, {'BSR' if a else 'ACCESS'}", 1, False, None

    # BTG
    if (word1 & 0xFC00) == 0x7000:
        f = word1 & 0x00FF
        b = (word1 >> 9) & 0x07
        a = (word1 >> 8) & 0x01
        return "BTG", f"0x{f:02X}, {b}, {'BSR' if a else 'ACCESS'}", 1, False, None

    # NOP
    if word1 == 0x0000:
        return "NOP", "", 1, False, None

    # SLEEP
    if word1 == 0x0003:
        return "SLEEP", "", 1, False, None

    # CLRWDT
    if word1 == 0x0004:
        return "CLRWDT", "", 1, False, None

    # RETURN
    if word1 == 0x0012:
        return "RETURN", "", 1, False, None

    # RETFIE
    if word1 == 0x0010:
        return "RETFIE", "", 1, False, None

    # PUSH
    if word1 == 0x0005:
        return "PUSH", "", 1, False, None

    # POP
    if word1 == 0x0006:
        return "POP", "", 1, False, None

    # TBLRD variants
    if word1 == 0x0008:
        return "TBLRD", "*", 1, False, None
    if word1 == 0x0009:
        return "TBLRD", "*+", 1, False, None
    if word1 == 0x000A:
        return "TBLRD", "*-", 1, False, None
    if word1 == 0x000B:
        return "TBLRD", "+*", 1, False, None

    # TBLWT variants
    if word1 == 0x000C:
        return "TBLWT", "*", 1, False, None
    if word1 == 0x000D:
        return "TBLWT", "*+", 1, False, None
    if word1 == 0x000E:
        return "TBLWT", "*-", 1, False, None
    if word1 == 0x000F:
        return "TBLWT", "+*", 1, False, None

    # CPFSEQ
    if (word1 & 0xFC00) == 0x6200:
        f = word1 & 0x00FF
        a = (word1 >> 8) & 0x01
        return "CPFSEQ", f"0x{f:02X}, {'BSR' if a else 'ACCESS'}", 1, False, None

    # CPFSGT
    if (word1 & 0xFC00) == 0x6400:
        f = word1 & 0x00FF
        a = (word1 >> 8) & 0x01
        return "CPFSGT", f"0x{f:02X}, {'BSR' if a else 'ACCESS'}", 1, False, None

    # CPFSLT
    if (word1 & 0xFC00) == 0x6000:
        f = word1 & 0x00FF
        a = (word1 >> 8) & 0x01
        return "CPFSLT", f"0x{f:02X}, {'BSR' if a else 'ACCESS'}", 1, False, None

    # RLCF
    if (word1 & 0xFC00) == 0x3400:
        f = word1 & 0x00FF
        d = (word1 >> 9) & 0x01
        a = (word1 >> 8) & 0x01
        return (
            "RLCF",
            f"0x{f:02X}, {'F' if d else 'W'}, {'BSR' if a else 'ACCESS'}",
            1,
            False,
            None,
        )

    # RRCF
    if (word1 & 0xFC00) == 0x3800:
        f = word1 & 0x00FF
        d = (word1 >> 9) & 0x01
        a = (word1 >> 8) & 0x01
        return (
            "RRCF",
            f"0x{f:02X}, {'F' if d else 'W'}, {'BSR' if a else 'ACCESS'}",
            1,
            False,
            None,
        )

    # SWAPF
    if (word1 & 0xFC00) == 0x3C00 or (word1 & 0xFC00) == 0x3800:
        f = word1 & 0x00FF
        d = (word1 >> 9) & 0x01
        a = (word1 >> 8) & 0x01
        return (
            "SWAPF",
            f"0x{f:02X}, {'F' if d else 'W'}, {'BSR' if a else 'ACCESS'}",
            1,
            False,
            None,
        )

    # Default: unknown
    return "DW", f"0x{word1:04X}", 1, False, None


def disassemble_region(
    memory: Dict[int, int], start: int, end: int
) -> List[PIC18Instruction]:
    """Disassemble a region of memory."""
    instructions = []
    addr = start

    while addr < end:
        word1 = get_word(memory, addr)
        if word1 is None:
            addr += 2
            continue

        # Check for 2-word instructions
        word2 = get_word(memory, addr + 2)

        mnemonic, operands, size_words, is_branch, branch_target = (
            decode_pic18_instruction(word1, word2)
        )

        raw_words = [word1]
        if size_words == 2 and word2 is not None:
            raw_words.append(word2)

        inst = PIC18Instruction(
            address=addr,
            raw_words=raw_words,
            mnemonic=mnemonic,
            operands=operands,
            size_words=size_words,
            is_branch=is_branch,
            branch_target=branch_target,
        )
        instructions.append(inst)

        addr += size_words * 2

    return instructions


def extract_usb_descriptors(
    memory: Dict[int, int], code_start: int, code_end: int
) -> List[dict]:
    """Extract USB descriptors from code memory."""
    descriptors = []

    # Look for USB descriptor patterns
    # Device descriptor starts with 0x12 0x01 (length, type)
    addr = code_start
    while addr < code_end - 18:
        # Check for device descriptor
        if memory.get(addr) == 0x12 and memory.get(addr + 1) == 0x01:
            desc = {
                "type": "device",
                "address": addr,
                "data": bytes([memory.get(addr + i, 0) for i in range(18)]),
            }
            descriptors.append(desc)
            addr += 18
            continue

        # Check for configuration descriptor (length 9, type 2)
        if memory.get(addr) == 0x09 and memory.get(addr + 1) == 0x02:
            total_len = memory.get(addr + 2, 0) | (memory.get(addr + 3, 0) << 8)
            desc = {
                "type": "configuration",
                "address": addr,
                "data": bytes(
                    [memory.get(addr + i, 0) for i in range(min(total_len, 64))]
                ),
            }
            descriptors.append(desc)
            addr += total_len
            continue

        addr += 1

    return descriptors


def analyze_configuration_bits(memory: Dict[int, int]) -> dict:
    """Analyze PIC18 configuration bits."""
    config = {}

    # Configuration registers at 0x300000-0x30000D
    config_addr = 0x300000

    config_names = [
        "CONFIG1L",
        "CONFIG1H",
        "CONFIG2L",
        "CONFIG2H",
        "CONFIG3L",
        "CONFIG3H",
        "CONFIG4L",
        "CONFIG4H",
        "CONFIG5L",
        "CONFIG5H",
        "CONFIG6L",
        "CONFIG6H",
        "CONFIG7L",
        "CONFIG7H",
    ]

    for i, name in enumerate(config_names):
        addr = config_addr + i
        if addr in memory:
            config[name] = memory[addr]

    return config


def main():
    hex_file = str(Path(__file__).resolve().parents[3] / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex")

    print("Parsing Intel HEX file...")
    memory, regions = parse_intel_hex(hex_file)

    # Identify memory regions
    print("\n=== Memory Regions ===")
    for ext_addr, ranges in sorted(regions.items()):
        if ext_addr == 0x00:  # Program memory
            for start, size in ranges:
                print(
                    f"  Program: 0x{start:06X} - 0x{start + size - 1:06X} ({size} bytes)"
                )
        elif ext_addr == 0x00F0:  # EEPROM
            for start, size in ranges:
                print(
                    f"  EEPROM:  0x{start:06X} - 0x{start + size - 1:06X} ({size} bytes)"
                )
        elif ext_addr == 0x0030:  # Configuration
            for start, size in ranges:
                print(
                    f"  Config:  0x{start:06X} - 0x{start + size - 1:06X} ({size} bytes)"
                )
        elif ext_addr == 0x0020:  # User IDs
            for start, size in ranges:
                print(
                    f"  User ID: 0x{start:06X} - 0x{start + size - 1:06X} ({size} bytes)"
                )

    # Analyze configuration bits
    print("\n=== Configuration Bits ===")
    config = analyze_configuration_bits(memory)
    for name, value in config.items():
        print(f"  {name}: 0x{value:02X}")

    # Analyze reset vector
    print("\n=== Reset Vector Analysis ===")
    reset_word1 = get_word(memory, 0x1000)
    reset_word2 = get_word(memory, 0x1002)
    if reset_word1:
        mnemonic, operands, size, is_branch, target = decode_pic18_instruction(
            reset_word1, reset_word2
        )
        print(f"  0x1000: {mnemonic} {operands}")
        if target:
            print(f"  Reset jumps to: 0x{target:04X}")

    # Analyze interrupt vectors
    print("\n=== Interrupt Vectors ===")
    # High priority interrupt at 0x1008
    high_isr = get_word(memory, 0x1008)
    high_isr2 = get_word(memory, 0x100A)
    if high_isr:
        mnemonic, operands, size, is_branch, target = decode_pic18_instruction(
            high_isr, high_isr2
        )
        print(f"  High priority ISR (0x1008): {mnemonic} {operands}")

    # Low priority interrupt at 0x1018
    low_isr = get_word(memory, 0x1018)
    low_isr2 = get_word(memory, 0x101A)
    if low_isr:
        mnemonic, operands, size, is_branch, target = decode_pic18_instruction(
            low_isr, low_isr2
        )
        print(f"  Low priority ISR (0x1018): {mnemonic} {operands}")

    # Disassemble first 100 instructions
    print("\n=== First 50 Instructions (starting at 0x1000) ===")
    instructions = disassemble_region(memory, 0x1000, 0x1100)
    for inst in instructions[:50]:
        words_str = " ".join(f"{w:04X}" for w in inst.raw_words)
        print(
            f"  0x{inst.address:04X}: {words_str:12s}  {inst.mnemonic} {inst.operands}"
        )

    # Extract USB descriptors
    print("\n=== USB Descriptors ===")
    descriptors = extract_usb_descriptors(memory, 0x1000, 0x6000)
    for desc in descriptors:
        print(f"  {desc['type']} descriptor at 0x{desc['address']:04X}:")
        data_hex = " ".join(f"{b:02X}" for b in desc["data"][:32])
        print(f"    {data_hex}")

    # Find strings in memory
    print("\n=== Embedded Strings ===")
    strings_found = []
    addr = 0x1000
    current_string = ""
    string_start = 0

    while addr < 0x6000:
        b = memory.get(addr, 0)
        if 0x20 <= b < 0x7F:
            if not current_string:
                string_start = addr
            current_string += chr(b)
        else:
            if len(current_string) >= 4:
                strings_found.append((string_start, current_string))
            current_string = ""
        addr += 1

    for saddr, s in strings_found[:20]:
        print(f'  0x{saddr:04X}: "{s}"')

    # Count instructions
    print("\n=== Code Statistics ===")
    all_instructions = disassemble_region(memory, 0x1000, 0x6000)

    call_count = sum(
        1 for i in all_instructions if i.mnemonic == "CALL" or i.mnemonic == "RCALL"
    )
    goto_count = sum(1 for i in all_instructions if i.mnemonic == "GOTO")
    return_count = sum(1 for i in all_instructions if i.mnemonic == "RETURN")
    retfie_count = sum(1 for i in all_instructions if i.mnemonic == "RETFIE")
    retlw_count = sum(1 for i in all_instructions if i.mnemonic == "RETLW")

    print(f"  Total instructions: {len(all_instructions)}")
    print(f"  CALL/RCALL: {call_count}")
    print(f"  GOTO: {goto_count}")
    print(f"  RETURN: {return_count}")
    print(f"  RETFIE: {retfie_count}")
    print(f"  RETLW: {retlw_count}")
    print(f"  Functions (RETURN+RETFIE): {return_count + retfie_count}")

    # Find function entry points
    print("\n=== Potential Function Entry Points ===")
    call_targets = set()
    for inst in all_instructions:
        if inst.mnemonic == "CALL" and inst.branch_target:
            call_targets.add(inst.branch_target)

    for target in sorted(call_targets)[:30]:
        word1 = get_word(memory, target)
        word2 = get_word(memory, target + 2)
        if word1:
            mnemonic, operands, _, _, _ = decode_pic18_instruction(word1, word2)
            print(f"  0x{target:04X}: {mnemonic} {operands}")


if __name__ == "__main__":
    main()
