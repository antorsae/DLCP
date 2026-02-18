#!/usr/bin/env python3
"""
Deep Firmware Analysis - Trace execution, identify functionality, map data structures
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Function:
    address: int
    end_address: int
    instructions: List[Tuple]
    callers: Set[int]
    callees: Set[int]
    returns: List[int]
    name: str = ""


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


def get_byte(memory: Dict[int, int], addr: int) -> Optional[int]:
    return memory.get(addr)


def decode_inst(
    memory: Dict[int, int], addr: int
) -> Tuple[str, str, int, Optional[int], dict]:
    """Returns (mnemonic, operands, size, branch_target, extra_info)"""
    word1 = get_word(memory, addr)
    if word1 is None:
        return "DW", "??", 1, None, {}

    word2 = get_word(memory, addr + 2)
    extra = {"raw": [word1]}

    # GOTO
    if (word1 & 0xFF00) == 0xEF00 and word2 is not None:
        k_low = word1 & 0x00FF
        k_high = word2 & 0x0FFF
        target = ((k_high << 8) | k_low) * 2
        extra["raw"].append(word2)
        return "GOTO", f"0x{target:04X}", 2, target, extra

    # CALL
    if (word1 & 0xFF00) == 0xEC00 and word2 is not None:
        k_low = word1 & 0x00FF
        k_high = word2 & 0x0FFF
        s = (word2 >> 8) & 0x01
        target = ((k_high << 8) | k_low) * 2
        extra["raw"].append(word2)
        extra["s"] = s
        return "CALL", f"0x{target:04X}", 2, target, extra

    # MOVFF
    if (word1 & 0xC000) == 0xC000 and word2 is not None:
        fs = word1 & 0x0FFF
        fd = word2 & 0x0FFF
        extra["raw"].append(word2)
        extra["src"] = fs
        extra["dst"] = fd
        return "MOVFF", f"0x{fs:03X}, 0x{fd:03X}", 2, None, extra

    # LFSR
    if (word1 & 0xFF00) == 0xEE00 and word2 is not None:
        f = (word1 >> 4) & 0x03
        k = word2 & 0x0FFF
        extra["raw"].append(word2)
        extra["fsr"] = f
        extra["value"] = k
        return "LFSR", f"{f}, 0x{k:03X}", 2, None, extra

    # RCALL
    if (word1 & 0xF800) == 0xD000:
        n = word1 & 0x07FF
        if n & 0x0400:
            n = n - 0x0800
        target = addr + 2 + n * 2
        extra["relative"] = n
        return "RCALL", f"0x{target:04X}", 1, target, extra

    # BRA
    if (word1 & 0xF800) == 0xD800:
        n = word1 & 0x07FF
        if n & 0x0400:
            n = n - 0x0800
        target = addr + 2 + n * 2
        extra["relative"] = n
        return "BRA", f"0x{target:04X}", 1, target, extra

    # Conditional branches
    branch_map = [
        (0xFF00, 0xE000, "BZ"),
        (0xFF00, 0xE100, "BNZ"),
        (0xFF00, 0xE200, "BC"),
        (0xFF00, 0xE300, "BNC"),
        (0xFF00, 0xE400, "BOV"),
        (0xFF00, 0xE500, "BNOV"),
        (0xFF00, 0xE600, "BN"),
        (0xFF00, 0xE700, "BNN"),
    ]
    for mask, pattern, mnemonic in branch_map:
        if (word1 & mask) == pattern:
            n = word1 & 0x00FF
            if n & 0x80:
                n = n - 0x100
            target = addr + 2 + n * 2
            extra["relative"] = n
            return mnemonic, f"0x{target:04X}", 1, target, extra

    # MOVLW
    if (word1 & 0xFF00) == 0x0E00:
        k = word1 & 0x00FF
        extra["literal"] = k
        return "MOVLW", f"0x{k:02X}", 1, None, extra

    # IORLW
    if (word1 & 0xFF00) == 0x0900:
        k = word1 & 0x00FF
        extra["literal"] = k
        return "IORLW", f"0x{k:02X}", 1, None, extra

    # XORLW
    if (word1 & 0xFF00) == 0x0A00:
        k = word1 & 0x00FF
        extra["literal"] = k
        return "XORLW", f"0x{k:02X}", 1, None, extra

    # ANDLW
    if (word1 & 0xFF00) == 0x0B00:
        k = word1 & 0x00FF
        extra["literal"] = k
        return "ANDLW", f"0x{k:02X}", 1, None, extra

    # ADDLW
    if (word1 & 0xFF00) == 0x0F00:
        k = word1 & 0x00FF
        extra["literal"] = k
        return "ADDLW", f"0x{k:02X}", 1, None, extra

    # SUBLW
    if (word1 & 0xFF00) == 0x0800:
        k = word1 & 0x00FF
        extra["literal"] = k
        return "SUBLW", f"0x{k:02X}", 1, None, extra

    # MOVLB
    if (word1 & 0xFF00) == 0x0100:
        k = word1 & 0x00FF
        extra["bank"] = k
        return "MOVLB", f"0x{k:02X}", 1, None, extra

    # RETLW
    if (word1 & 0xFF00) == 0x0C00:
        k = word1 & 0x00FF
        extra["literal"] = k
        return "RETLW", f"0x{k:02X}", 1, None, extra

    # Bit instructions
    bit_ops = [
        (0xFC00, 0x8000, "BSF"),
        (0xFC00, 0x9000, "BCF"),
        (0xFC00, 0xA000, "BTFSS"),
        (0xFC00, 0xB000, "BTFSC"),
        (0xFC00, 0x7000, "BTG"),
    ]
    for mask, pattern, mnemonic in bit_ops:
        if (word1 & mask) == pattern:
            f = word1 & 0xFF
            b = (word1 >> 9) & 0x07
            a = "BSR" if (word1 >> 8) & 1 else "ACCESS"
            extra["file"] = f
            extra["bit"] = b
            extra["access"] = a
            return mnemonic, f"0x{f:02X}, {b}, {a}", 1, None, extra

    # Byte-oriented file register operations
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
        (0xFC00, 0x4400, "RLNCF"),
        (0xFC00, 0x5C00, "SUBWFB"),
        (0xFC00, 0x2000, "ADDWFC"),
        (0xFC00, 0x6200, "CPFSGT"),
        (0xFC00, 0x6400, "CPFSLT"),
        (0xFC00, 0x6000, "CPFSEQ"),
        (0xFC00, 0x6600, "TSTFSZ"),
        (0xFC00, 0x6C00, "NEGF"),
        (0xFC00, 0x3000, "SWAPF"),
    ]
    for mask, pattern, mnemonic in byte_ops:
        if (word1 & mask) == pattern:
            f = word1 & 0xFF
            d = "F" if (word1 >> 9) & 1 else "W"
            a = "BSR" if (word1 >> 8) & 1 else "ACCESS"
            extra["file"] = f
            extra["dest"] = d
            extra["access"] = a
            return mnemonic, f"0x{f:02X}, {d}, {a}", 1, None, extra

    # Null/other instructions
    null_map = {
        0x0000: ("NOP", ""),
        0x0003: ("SLEEP", ""),
        0x0004: ("CLRWDT", ""),
        0x0005: ("PUSH", ""),
        0x0006: ("POP", ""),
        0x0010: ("RETFIE", ""),
        0x0012: ("RETURN", ""),
        0x0008: ("TBLRD", "*"),
        0x0009: ("TBLRD", "*+"),
        0x000A: ("TBLRD", "*-"),
        0x000B: ("TBLRD", "+*"),
        0x000C: ("TBLWT", "*"),
        0x000D: ("TBLWT", "*+"),
        0x000E: ("TBLWT", "*-"),
        0x000F: ("TBLWT", "+*"),
    }
    if word1 in null_map:
        mn, op = null_map[word1]
        return mn, op, 1, None, extra

    return "DW", f"0x{word1:04X}", 1, None, extra


def disasm_function(
    memory: Dict[int, int], start: int, max_insns: int = 200
) -> Function:
    """Disassemble a complete function"""
    instructions = []
    addr = start
    returns = []
    callees = set()

    for _ in range(max_insns):
        mn, op, size, target, extra = decode_inst(memory, addr)
        instructions.append((addr, mn, op, size, target, extra))

        if mn in ["CALL", "RCALL"] and target:
            callees.add(target)

        if mn in ["RETURN", "RETFIE"]:
            returns.append(addr)
            break
        if mn == "RETLW":
            returns.append(addr)
            # Could be a lookup table, continue a bit
            if len(returns) > 20:
                break

        addr += size * 2

    end_addr = instructions[-1][0] + instructions[-1][3] * 2 if instructions else start

    return Function(
        address=start,
        end_address=end_addr,
        instructions=instructions,
        callers=set(),
        callees=callees,
        returns=returns,
    )


def find_all_functions(
    memory: Dict[int, int], start: int, end: int
) -> Dict[int, Function]:
    """Find all functions in a range by looking for CALL targets and RETURNs"""
    functions = {}

    # First pass: find all call targets
    call_targets = set()
    addr = start
    while addr < end:
        mn, op, size, target, extra = decode_inst(memory, addr)
        if mn in ["CALL", "RCALL"] and target and start <= target < end:
            call_targets.add(target)
        addr += size * 2

    # Add entry points
    call_targets.add(0x1008)  # High priority ISR
    call_targets.add(0x3D4E)  # Main function

    # Disassemble each function
    for target in sorted(call_targets):
        if target not in functions:
            func = disasm_function(memory, target)
            functions[target] = func

    return functions


# PIC18F2550 SFR definitions
SFR = {
    # USB Registers
    0xF60: "UADDR",
    0xF61: "UCFG",
    0xF62: "USTAT",
    0xF63: "UCON",
    0xF64: "UIR",
    0xF65: "UEIR",
    0xF66: "UEP0",
    0xF67: "UEP1",
    0xF68: "UEP2",
    0xF69: "UEP3",
    0xF6A: "UEP4",
    0xF6B: "UEP5",
    0xF6C: "UEP6",
    0xF6D: "UEP7",
    0xF6E: "UEP8",
    0xF6F: "UEP9",
    0xF70: "UEP10",
    0xF71: "UEP11",
    0xF72: "UEP12",
    0xF73: "UEP13",
    0xF74: "UEP14",
    0xF75: "UEP15",
    # Core Registers
    0xFD0: "TOSU",
    0xFD1: "TOSH",
    0xFD2: "TOSL",
    0xFD3: "STKPTR",
    0xFD4: "PCLATU",
    0xFD5: "PCLATH",
    0xFD6: "PCL",
    0xFD8: "TBLPTRU",
    0xFD9: "TBLPTRH",
    0xFDA: "TBLPTRL",
    0xFDB: "TABLAT",
    0xFDC: "PRODH",
    0xFDD: "PRODL",
    0xFE0: "INTCON",
    0xFE1: "INTCON2",
    0xFE2: "INTCON3",
    0xFE3: "INDF0",
    0xFE4: "POSTINC0",
    0xFE5: "POSTDEC0",
    0xFE6: "PREINC0",
    0xFE7: "PLUSW0",
    0xFE8: "FSR0H",
    0xFE9: "FSR0L",
    0xFEA: "WREG",
    0xFEB: "INDF1",
    0xFEC: "POSTINC1",
    0xFED: "POSTDEC1",
    0xFEE: "PREINC1",
    0xFEF: "PLUSW1",
    0xFF0: "FSR1H",
    0xFF1: "FSR1L",
    0xFF2: "BSR",
    0xFF3: "INDF2",
    0xFF4: "POSTINC2",
    0xFF5: "POSTDEC2",
    0xFF6: "PREINC2",
    0xFF7: "PLUSW2",
    0xFF8: "FSR2H",
    0xFF9: "FSR2L",
    0xFFA: "STATUS",
    0xFFB: "TMR0U",
    0xFFC: "TMR0H",
    0xFFD: "TMR0L",
    0xFFE: "TRISB",
    0xFFF: "TRISC",
    # PORT Registers
    0xF80: "PORTA",
    0xF81: "PORTB",
    0xF82: "PORTC",
    0xF83: "PORTD",
    0xF84: "PORTE",
    0xF92: "TRISA",
    0xF93: "TRISB",
    0xF94: "TRISC",
    0xF95: "TRISD",
    0xF96: "TRISE",
    0xF89: "LATA",
    0xF8A: "LATB",
    0xF8B: "LATC",
    # Timer Registers
    0xFCC: "T0CON",
    0xFCD: "T1CON",
    0xFCE: "TMR1L",
    0xFCF: "TMR1H",
    0xFD0: "T1CON",
    0xFD1: "T2CON",
    0xFD2: "PR2",
    0xFD3: "TMR2",
    # ADC Registers
    0xFC0: "ADCON0",
    0xFC1: "ADCON1",
    0xFC2: "ADCON2",
    0xFC3: "ADRESL",
    0xFC4: "ADRESH",
    # EEPROM Control
    0xFA6: "EECON1",
    0xFA7: "EECON2",
    0xFA8: "EEDATA",
    0xFA9: "EEADR",
    # SPI
    0xFC6: "SSPBUF",
    0xFC7: "SSPCON1",
    0xFC8: "SSPSTAT",
}


def reg_name(addr: int) -> str:
    if addr in SFR:
        return SFR[addr]
    return f"0x{addr:03X}"


def analyze_usb_init(memory: Dict[int, int]):
    """Find USB initialization code"""
    print("\n" + "=" * 70)
    print("USB INITIALIZATION ANALYSIS")
    print("=" * 70)

    usb_regs = {
        0xF60,
        0xF61,
        0xF62,
        0xF63,
        0xF64,
        0xF65,
        0xF66,
        0xF67,
        0xF68,
        0xF69,
        0xF6A,
    }

    for addr in range(0x1000, 0x6000, 2):
        mn, op, size, target, extra = decode_inst(memory, addr)

        if mn == "MOVFF":
            src = extra.get("src", 0)
            dst = extra.get("dst", 0)
            if src in usb_regs or dst in usb_regs:
                print(f"  0x{addr:04X}: MOVFF {reg_name(src)}, {reg_name(dst)}")
        elif mn in ["MOVWF", "CLRF", "SETF", "BSF", "BCF"]:
            f = extra.get("file", 0)
            if f in usb_regs:
                print(
                    f"  0x{addr:04X}: {mn} {reg_name(f)}, {extra.get('bit', '')} {extra.get('access', '')}"
                )


def analyze_eeprom_access(memory: Dict[int, int]):
    """Find EEPROM access patterns"""
    print("\n" + "=" * 70)
    print("EEPROM ACCESS ANALYSIS")
    print("=" * 70)

    eeprom_regs = {0xFA6, 0xFA7, 0xFA8, 0xFA9}

    for addr in range(0x1000, 0x6000, 2):
        mn, op, size, target, extra = decode_inst(memory, addr)

        if mn == "MOVFF":
            src = extra.get("src", 0)
            dst = extra.get("dst", 0)
            if src in eeprom_regs or dst in eeprom_regs:
                print(f"  0x{addr:04X}: MOVFF {reg_name(src)}, {reg_name(dst)}")
        elif mn in ["MOVWF", "CLRF", "SETF", "BSF", "BCF"]:
            f = extra.get("file", 0)
            if f in eeprom_regs:
                print(f"  0x{addr:04X}: {mn} {reg_name(f)}")


def find_command_handler(memory: Dict[int, int]):
    """Look for command dispatch tables or switch statements"""
    print("\n" + "=" * 70)
    print("COMMAND HANDLER ANALYSIS")
    print("=" * 70)

    # Look for XORLW patterns that compare against command bytes
    for addr in range(0x1000, 0x6000, 2):
        mn, op, size, target, extra = decode_inst(memory, addr)

        if mn == "XORLW":
            literal = extra.get("literal", 0)
            next_addr = addr + 2

            # Check if followed by BNZ (branch if not zero)
            mn2, op2, _, target2, _ = decode_inst(memory, next_addr)
            if mn2 == "BNZ":
                print(
                    f"  0x{addr:04X}: XORLW 0x{literal:02X} ; Check command 0x{literal:02X}"
                )
                print(
                    f"  0x{next_addr:04X}: BNZ 0x{target2:04X}  ; Skip if not this command"
                )

                # Try to find what happens if it matches
                next_addr2 = next_addr + 2
                for _ in range(5):
                    mn3, op3, size3, target3, extra3 = decode_inst(memory, next_addr2)
                    if mn3 in ["BRA", "GOTO", "CALL", "RCALL"]:
                        print(
                            f"  0x{next_addr2:04X}: {mn3} {op3}  ; Handler for command 0x{literal:02X}"
                        )
                        break
                    next_addr2 += size3 * 2


def extract_hid_report_descriptor(memory: Dict[int, int]):
    """Try to find and decode the HID report descriptor"""
    print("\n" + "=" * 70)
    print("HID REPORT DESCRIPTOR SEARCH")
    print("=" * 70)

    # Look for descriptor in program memory
    # HID descriptors are usually at fixed locations or referenced from config

    # Check the configuration descriptor area for report descriptor length
    # Report desc length was 0x001D (29 bytes) according to HID descriptor

    # Look for a sequence of bytes that could be a HID report descriptor
    # Typical start: 0x06 (Usage Page), 0x09 (Usage), 0xA1 (Collection)

    for addr in range(0x1000, 0x6000):
        b1 = get_byte(memory, addr)
        b2 = get_byte(memory, addr + 1)
        b3 = get_byte(memory, addr + 2)

        # HID report descriptor typically starts with Usage Page
        if b1 == 0x06 and b3 == 0x09:  # Usage Page, then Usage
            print(f"  Potential HID report descriptor at 0x{addr:04X}")

            # Try to dump it
            desc = []
            for i in range(32):
                b = get_byte(memory, addr + i)
                if b is not None:
                    desc.append(b)

            print(f"  Bytes: {' '.join(f'{b:02X}' for b in desc)}")
            break


def analyze_main_loop(memory: Dict[int, int]):
    """Analyze the main function structure"""
    print("\n" + "=" * 70)
    print("MAIN FUNCTION ANALYSIS (0x3D4E)")
    print("=" * 70)

    func = disasm_function(memory, 0x3D4E, 100)

    for addr, mn, op, size, target, extra in func.instructions[:50]:
        raw = " ".join(f"{w:04X}" for w in extra.get("raw", [0]))
        print(f"  0x{addr:04X}: {raw:12s}  {mn:8s} {op}")


def analyze_isr(memory: Dict[int, int]):
    """Analyze interrupt service routine"""
    print("\n" + "=" * 70)
    print("HIGH PRIORITY ISR ANALYSIS (0x1008)")
    print("=" * 70)

    # The ISR at 0x1008 saves context then jumps somewhere
    func = disasm_function(memory, 0x1008, 50)

    for addr, mn, op, size, target, extra in func.instructions:
        raw = " ".join(f"{w:04X}" for w in extra.get("raw", [0]))

        # Add SFR names
        if mn == "MOVFF":
            src = extra.get("src", 0)
            dst = extra.get("dst", 0)
            op = f"{reg_name(src)}, {reg_name(dst)}"

        print(f"  0x{addr:04X}: {raw:12s}  {mn:8s} {op}")

        if mn == "GOTO":
            print(f"\n  ISR continues at 0x{target:04X}")
            break


def find_string_tables(memory: Dict[int, int]):
    """Find string tables and lookup tables"""
    print("\n" + "=" * 70)
    print("STRING/TABLE ANALYSIS")
    print("=" * 70)

    # The hex digit table at 0x1018
    print("\n  Hex digit lookup table at 0x1018:")
    hex_str = ""
    for i in range(16):
        b = get_byte(memory, 0x1019 + i)
        if b and 0x30 <= b <= 0x46:
            hex_str += chr(b)
    print(f"    '{hex_str}'")

    # Look for RETLW sequences (lookup tables)
    print("\n  Lookup tables (RETLW sequences):")

    addr = 0x1000
    while addr < 0x6000:
        count = 0
        start = addr

        # Count consecutive RETLW instructions
        while count < 20:
            mn, op, size, target, extra = decode_inst(memory, addr)
            if mn == "RETLW":
                count += 1
                addr += 2
            else:
                break

        if count >= 5:
            print(f"    0x{start:04X}: {count} entries")
            # Print first few values
            values = []
            for i in range(min(count, 10)):
                mn, op, _, _, extra = decode_inst(memory, start + i * 2)
                values.append(f"0x{extra.get('literal', 0):02X}")
            print(f"      Values: {', '.join(values)}")

        addr += 2


def analyze_data_flow(memory: Dict[int, int]):
    """Analyze how data flows through the firmware"""
    print("\n" + "=" * 70)
    print("DATA FLOW ANALYSIS")
    print("=" * 70)

    # Count accesses to different memory regions
    ram_access = defaultdict(int)

    for addr in range(0x1000, 0x6000, 2):
        mn, op, size, target, extra = decode_inst(memory, addr)

        if mn in ["MOVWF", "MOVF", "CLRF", "SETF", "BSF", "BCF", "BTFSS", "BTFSC"]:
            f = extra.get("file", 0)
            if f < 0xF00:  # Not SFR
                bank = extra.get("access", "ACCESS")
                ram_access[(f, bank)] += 1

        if mn == "MOVFF":
            src = extra.get("src", 0)
            dst = extra.get("dst", 0)
            if src < 0xF00:
                ram_access[(src, "INDIRECT")] += 1
            if dst < 0xF00:
                ram_access[(dst, "INDIRECT")] += 1

    # Find most accessed RAM locations
    print("\n  Most accessed RAM locations:")
    sorted_access = sorted(ram_access.items(), key=lambda x: -x[1])[:20]
    for (addr, bank), count in sorted_access:
        print(f"    0x{addr:02X} ({bank}): {count} accesses")


def main():
    hex_file = str(Path(__file__).resolve().parents[3] / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex")
    memory = parse_intel_hex(hex_file)

    print("=" * 70)
    print("HYPEX DLCP FIRMWARE V2.3 - DEEP ANALYSIS")
    print("=" * 70)

    analyze_isr(memory)
    analyze_main_loop(memory)
    find_command_handler(memory)
    analyze_usb_init(memory)
    analyze_eeprom_access(memory)
    find_string_tables(memory)
    extract_hid_report_descriptor(memory)
    analyze_data_flow(memory)


if __name__ == "__main__":
    main()
