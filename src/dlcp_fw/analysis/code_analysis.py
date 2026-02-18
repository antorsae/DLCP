#!/usr/bin/env python3
"""
Detailed Code Analysis - Find entry points, analyze main function and ISRs
"""

from pathlib import Path
from typing import Dict, Optional, Tuple


def parse_intel_hex(filepath: str) -> Dict[int, int]:
    memory = {}
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

            if record_type == 0x00:
                base_addr = extended_addr + address
                for i, b in enumerate(data):
                    memory[base_addr + i] = b
            elif record_type == 0x01:
                break
            elif record_type == 0x04:
                extended_addr = int(data_hex, 16) << 16

    return memory


def get_word(memory: Dict[int, int], addr: int) -> Optional[int]:
    if addr in memory and addr + 1 in memory:
        return memory[addr] | (memory[addr + 1] << 8)
    return None


def decode_instruction(
    memory: Dict[int, int], addr: int
) -> Tuple[str, str, int, Optional[int]]:
    word1 = get_word(memory, addr)
    if word1 is None:
        return "DW", "??", 1, None

    word2 = get_word(memory, addr + 2)

    # GOTO
    if (word1 & 0xFF00) == 0xEF00 and word2 is not None:
        k_low = word1 & 0x00FF
        k_high = word2 & 0x0FFF
        target = ((k_high << 8) | k_low) * 2
        return "GOTO", f"0x{target:04X}", 2, target

    # CALL
    if (word1 & 0xFF00) == 0xEC00 and word2 is not None:
        k_low = word1 & 0x00FF
        k_high = word2 & 0x0FFF
        target = ((k_high << 8) | k_low) * 2
        return "CALL", f"0x{target:04X}", 2, target

    # MOVFF
    if (word1 & 0xC000) == 0xC000 and word2 is not None:
        fs = word1 & 0x0FFF
        fd = word2 & 0x0FFF
        return "MOVFF", f"0x{fs:03X}, 0x{fd:03X}", 2, None

    # LFSR
    if (word1 & 0xFF00) == 0xEE00 and word2 is not None:
        f = (word1 >> 4) & 0x03
        k = word2 & 0x0FFF
        return "LFSR", f"{f}, 0x{k:03X}", 2, None

    # RCALL
    if (word1 & 0xF800) == 0xD000:
        n = word1 & 0x07FF
        if n & 0x0400:
            n = n - 0x0800
        target = addr + 2 + n * 2
        return "RCALL", f"0x{target:04X}", 1, target

    # BRA
    if (word1 & 0xF800) == 0xD800:
        n = word1 & 0x07FF
        if n & 0x0400:
            n = n - 0x0800
        target = addr + 2 + n * 2
        return "BRA", f"0x{target:04X}", 1, target

    # Conditional branches
    branch_opcodes = [
        (0xFF00, 0xE000, "BZ"),
        (0xFF00, 0xE100, "BNZ"),
        (0xFF00, 0xE200, "BC"),
        (0xFF00, 0xE300, "BNC"),
        (0xFF00, 0xE400, "BOV"),
        (0xFF00, 0xE500, "BNOV"),
        (0xFF00, 0xE600, "BN"),
        (0xFF00, 0xE700, "BNN"),
    ]

    for mask, pattern, mnemonic in branch_opcodes:
        if (word1 & mask) == pattern:
            n = word1 & 0x00FF
            if n & 0x80:
                n = n - 0x100
            target = addr + 2 + n * 2
            return mnemonic, f"0x{target:04X}", 1, target

    # Single-word instructions
    if (word1 & 0xFF00) == 0x0E00:
        return "MOVLW", f"0x{word1 & 0xFF:02X}", 1, None
    if (word1 & 0xFF00) == 0x0900:
        return "IORLW", f"0x{word1 & 0xFF:02X}", 1, None
    if (word1 & 0xFF00) == 0x0A00:
        return "XORLW", f"0x{word1 & 0xFF:02X}", 1, None
    if (word1 & 0xFF00) == 0x0F00:
        return "ADDLW", f"0x{word1 & 0xFF:02X}", 1, None
    if (word1 & 0xFF00) == 0x0800:
        return "SUBLW", f"0x{word1 & 0xFF:02X}", 1, None
    if (word1 & 0xFF00) == 0x0100:
        return "MOVLB", f"0x{word1 & 0xFF:02X}", 1, None
    if (word1 & 0xFF00) == 0x0C00:
        return "RETLW", f"0x{word1 & 0xFF:02X}", 1, None

    # Bit instructions
    for mask, pattern, mnemonic in [
        (0xFC00, 0x8000, "BSF"),
        (0xFC00, 0x9000, "BCF"),
        (0xFC00, 0xA000, "BTFSS"),
        (0xFC00, 0xB000, "BTFSC"),
        (0xFC00, 0x7000, "BTG"),
    ]:
        if (word1 & mask) == pattern:
            f = word1 & 0xFF
            b = (word1 >> 9) & 0x07
            a = "BSR" if (word1 >> 8) & 1 else "ACCESS"
            return mnemonic, f"0x{f:02X}, {b}, {a}", 1, None

    # Byte instructions
    byte_ops = [
        (0xFE00, 0x6E00, "MOVWF"),
        (0xFC00, 0x6A00, "CLRF"),
        (0xFC00, 0x6800, "SETF"),
        (0xFC00, 0x5000, "MOVF"),
        (0xFC00, 0x2400, "ADDWF"),
        (0xFC00, 0x5800, "SUBWF"),
        (0xFC00, 0x2800, "INCF"),
        (0xFC00, 0x0400, "DECF"),
        (0xFC00, 0x4C00, "DECFSZ"),
        (0xFC00, 0x3C00, "INCFSZ"),
        (0xFC00, 0x3400, "RLCF"),
        (0xFC00, 0x3800, "RRCF"),
    ]

    for mask, pattern, mnemonic in byte_ops:
        if (word1 & mask) == pattern:
            f = word1 & 0xFF
            d = "F" if (word1 >> 9) & 1 else "W"
            a = "BSR" if (word1 >> 8) & 1 else "ACCESS"
            return mnemonic, f"0x{f:02X}, {d}, {a}", 1, None

    # Null instructions
    null_ops = {
        0x0000: "NOP",
        0x0003: "SLEEP",
        0x0004: "CLRWDT",
        0x0005: "PUSH",
        0x0006: "POP",
        0x0010: "RETFIE",
        0x0012: "RETURN",
        0x0008: "TBLRD *",
        0x0009: "TBLRD *+",
        0x000A: "TBLRD *-",
        0x000B: "TBLRD +*",
        0x000C: "TBLWT *",
        0x000D: "TBLWT *+",
        0x000E: "TBLWT *-",
        0x000F: "TBLWT +*",
    }

    if word1 in null_ops:
        return null_ops[word1], "", 1, None

    return "DW", f"0x{word1:04X}", 1, None


def disassemble_region(memory: Dict[int, int], start: int, end: int, label: str = ""):
    print(f"\n{'=' * 70}")
    print(f"{label} (0x{start:04X} - 0x{end:04X})")
    print("=" * 70)

    addr = start
    while addr < end:
        mnemonic, operands, size, target = decode_instruction(memory, addr)

        word1 = get_word(memory, addr)
        word2 = get_word(memory, addr + 2) if size == 2 else None

        if word2 is not None:
            words_str = f"{word1:04X} {word2:04X}"
        else:
            words_str = f"{word1:04X}      "

        print(f"  0x{addr:04X}: {words_str}  {mnemonic:8s} {operands}")
        addr += size * 2


def analyze_isr(memory: Dict[int, int], entry_addr: int, name: str):
    print(f"\n{'=' * 70}")
    print(f"{name} Analysis (Entry: 0x{entry_addr:04X})")
    print("=" * 70)

    addr = entry_addr
    for _ in range(30):
        mnemonic, operands, size, target = decode_instruction(memory, addr)
        word1 = get_word(memory, addr)
        word2 = get_word(memory, addr + 2) if size == 2 else None

        if word2 is not None:
            words_str = f"{word1:04X} {word2:04X}"
        else:
            words_str = f"{word1:04X}      "

        print(f"  0x{addr:04X}: {words_str}  {mnemonic:8s} {operands}")

        if mnemonic in ["RETFIE", "RETURN", "GOTO"]:
            break

        addr += size * 2


def main():
    hex_file = str(Path(__file__).resolve().parents[3] / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex")
    memory = parse_intel_hex(hex_file)

    # Analyze reset vector and main entry
    print("=" * 70)
    print("RESET VECTOR ANALYSIS")
    print("=" * 70)

    # Reset vector at 0x1000
    disassemble_region(memory, 0x1000, 0x1010, "Reset Vector")

    # Vector table
    print("\n" + "=" * 70)
    print("INTERRUPT VECTOR TABLE")
    print("=" * 70)
    print("  PIC18 interrupt vectors:")
    print("  0x0008 - High Priority Interrupt (not in this file - bootloader)")
    print("  0x0018 - Low Priority Interrupt (not in this file - bootloader)")
    print("  0x1008 - High Priority ISR (application)")
    print("  0x1018 - Low Priority ISR location (contains data?)")

    # Analyze high priority ISR
    analyze_isr(memory, 0x1008, "High Priority ISR")

    # What's at 0x1014? (second GOTO target)
    disassemble_region(memory, 0x1014, 0x1020, "GOTO from Reset Vector")

    # The actual main function
    print("\n" + "=" * 70)
    print("MAIN FUNCTION (Target of 0x1014 GOTO)")
    print("=" * 70)

    # Find the main entry point
    word1 = get_word(memory, 0x1014)
    word2 = get_word(memory, 0x1016)
    if word1 and (word1 & 0xFF00) == 0xEF00 and word2:
        k_low = word1 & 0x00FF
        k_high = word2 & 0x0FFF
        main_addr = ((k_high << 8) | k_low) * 2
        print(f"  Main function entry point: 0x{main_addr:04X}")

        # Disassemble first part of main
        disassemble_region(memory, main_addr, main_addr + 0x40, "Main Function Start")

    # Find all CALL targets to identify functions
    print("\n" + "=" * 70)
    print("FUNCTION ANALYSIS (CALL targets)")
    print("=" * 70)

    call_targets = set()
    for addr in range(0x1000, 0x6000, 2):
        mnemonic, operands, size, target = decode_instruction(memory, addr)
        if mnemonic in ["CALL", "RCALL"] and target:
            call_targets.add(target)

    print(f"\nFound {len(call_targets)} unique function call targets:")

    # Group by address ranges to find functional areas
    ranges = {}
    for target in sorted(call_targets):
        range_key = (target // 0x400) * 0x400
        if range_key not in ranges:
            ranges[range_key] = []
        ranges[range_key].append(target)

    for range_start in sorted(ranges.keys()):
        targets = ranges[range_start]
        print(
            f"\n  Range 0x{range_start:04X}-0x{range_start + 0x3FF:04X}: {len(targets)} functions"
        )
        for t in targets[:5]:
            mnemonic, operands, _, _ = decode_instruction(memory, t)
            print(f"    0x{t:04X}: {mnemonic} {operands}")
        if len(targets) > 5:
            print(f"    ... and {len(targets) - 5} more")

    # Look for USB-related code
    print("\n" + "=" * 70)
    print("USB INITIALIZATION ANALYSIS")
    print("=" * 70)

    # USB registers for PIC18F2550/4550
    usb_regs = {
        0xF70: "UIE",
        0xF71: "UEIE",
        0xF72: "UEP0",
        0xF73: "UEP1",
        0xF74: "UEP2",
        0xF75: "UEP3",
        0xF76: "UEP4",
        0xF77: "UEP5",
        0xF60: "UADDR",
        0xF61: "UCFG",
        0xF62: "USTAT",
        0xF63: "UCON",
        0xF64: "UIR",
        0xF65: "UEIR",
    }

    # Look for access to USB registers
    for addr in range(0x1000, 0x2000, 2):
        word1 = get_word(memory, addr)
        if word1 is None:
            continue

        # MOVFF instruction accessing USB registers?
        if (word1 & 0xC000) == 0xC000:
            word2 = get_word(memory, addr + 2)
            if word2:
                fs = word1 & 0x0FFF
                fd = word2 & 0x0FFF
                if fs in usb_regs or fd in usb_regs:
                    reg_s = usb_regs.get(fs, f"0x{fs:03X}")
                    reg_d = usb_regs.get(fd, f"0x{fd:03X}")
                    print(f"  0x{addr:04X}: MOVFF {reg_s}, {reg_d}")


if __name__ == "__main__":
    main()
