#!/usr/bin/env python3
"""
Data Structure Deep Analysis - Filter counts, gain/delay, filter types
"""

from pathlib import Path
from typing import Dict, Optional
from collections import defaultdict


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


def get_dword(memory: Dict[int, int], addr: int) -> Optional[int]:
    if all(addr + i in memory for i in range(4)):
        return (
            memory[addr]
            | (memory[addr + 1] << 8)
            | (memory[addr + 2] << 16)
            | (memory[addr + 3] << 24)
        )
    return None


def get_bytes(memory: Dict[int, int], addr: int, count: int) -> bytes:
    return bytes(memory.get(addr + i, 0xFF) for i in range(count))


def analyze_eeprom_structure(memory: Dict[int, int]):
    """Analyze EEPROM for filter configuration data"""
    print("=" * 70)
    print("EEPROM STRUCTURE ANALYSIS")
    print("=" * 70)

    eeprom = get_bytes(memory, 0xF00000, 256)

    print("\n  Full EEPROM dump:")
    for i in range(0, 256, 16):
        hex_str = " ".join(f"{b:02X}" for b in eeprom[i : i + 16])
        print(f"    0x{i:02X}: {hex_str}")

    print("\n  Interpreted structure:")
    print(f"    0x00-0x02: Header = {eeprom[0]:02X} {eeprom[1]:02X} {eeprom[2]:02X}")
    print(f"    0x03: Config byte 1 = 0x{eeprom[3]:02X}")
    print(f"    0x04: Config byte 2 = 0x{eeprom[4]:02X}")

    # Look for patterns
    non_ff = [(i, eeprom[i]) for i in range(256) if eeprom[i] != 0xFF]
    print(f"\n  Non-0xFF bytes ({len(non_ff)} found):")
    for addr, val in non_ff:
        print(f"    0x{addr:02X}: 0x{val:02X}")


def analyze_channel_data_structures(memory: Dict[int, int]):
    """Analyze RAM access patterns to find channel data structures"""
    print("\n" + "=" * 70)
    print("CHANNEL DATA STRUCTURE ANALYSIS")
    print("=" * 70)

    # Look for MOVLB instructions to understand bank usage
    bank_usage = defaultdict(set)

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # MOVLB sets bank
        if (word & 0xFF00) == 0x0100:
            bank = word & 0xFF
            # Track what file registers are accessed after MOVLB
            for scan in range(addr + 2, addr + 40, 2):
                w = get_word(memory, scan)
                if w is None:
                    break
                if (w & 0xFF00) == 0x0100:  # Another MOVLB
                    break
                # MOVWF with BSR addressing
                if (w & 0x0100) and (w & 0xFE00) == 0x6E00:
                    f = w & 0xFF
                    bank_usage[bank].add(f)

    print("\n  Bank usage (which file registers per bank):")
    for bank in sorted(bank_usage.keys())[:10]:
        regs = sorted(bank_usage[bank])
        print(f"    Bank {bank:2d}: {len(regs)} registers - ", end="")
        if len(regs) <= 10:
            print(", ".join(f"0x{r:02X}" for r in regs))
        else:
            print(
                ", ".join(f"0x{r:02X}" for r in regs[:8])
                + f" ... ({len(regs) - 8} more)"
            )


def analyze_coefficient_commands(memory: Dict[int, int]):
    """Analyze coefficient upload/download commands to understand format"""
    print("\n" + "=" * 70)
    print("COEFFICIENT COMMAND ANALYSIS")
    print("=" * 70)

    # Find command 0x0A (coefficient upload) handler
    print("\n  Looking for coefficient transfer handlers...")

    # Command 0x0A is compared at 0x1108
    # Find what function is called
    for addr in range(0x1100, 0x1150, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFF00) == 0x0A00 and (word & 0xFF) == 0x0A:
            print(f"\n  Command 0x0A comparison at 0x{addr:04X}")

            # Find the handler call
            for scan in range(addr, addr + 30, 2):
                w = get_word(memory, scan)
                if w and (w & 0xFF00) == 0xEC00:  # CALL
                    w2 = get_word(memory, scan + 2)
                    if w2:
                        target = (((w2 & 0x0FFF) << 8) | (w & 0xFF)) * 2
                        print(f"  Handler CALL at 0x{scan:04X} -> 0x{target:04X}")

                        # Disassemble handler
                        print(f"\n  Handler at 0x{target:04X}:")
                        disasm_function(memory, target, 50)
                        break
            break


def disasm_function(memory: Dict[int, int], start: int, max_insns: int):
    """Disassemble a function with focus on data movement"""
    addr = start
    for _ in range(max_insns):
        word = get_word(memory, addr)
        if word is None:
            break

        if (word & 0xC000) == 0xC000:
            word2 = get_word(memory, addr + 2)
            if word2:
                src = word & 0x0FFF
                dst = word2 & 0x0FFF
                print(f"    0x{addr:04X}: MOVFF 0x{src:03X}, 0x{dst:03X}")
                addr += 4
                continue

        if (word & 0xFF00) == 0x0E00:
            print(f"    0x{addr:04X}: MOVLW 0x{word & 0xFF:02X}")
        elif (word & 0xFE00) == 0x6E00:
            f = word & 0xFF
            a = "BSR" if (word >> 8) & 1 else "ACCESS"
            print(f"    0x{addr:04X}: MOVWF 0x{f:02X}, {a}")
        elif (word & 0xFC00) == 0x5000:
            f = word & 0xFF
            d = "F" if (word >> 9) & 1 else "W"
            print(f"    0x{addr:04X}: MOVF 0x{f:02X}, {d}")
        elif (word & 0xF800) == 0xD000:
            n = word & 0x07FF
            if n & 0x0400:
                n = n - 0x0800
            target = addr + 2 + n * 2
            print(f"    0x{addr:04X}: RCALL 0x{target:04X}")
        elif word == 0x0012:
            print(f"    0x{addr:04X}: RETURN")
            break
        elif (word & 0xFF00) == 0xEE00:
            word2 = get_word(memory, addr + 2)
            if word2:
                fsr = (word >> 4) & 0x03
                val = word2 & 0x0FFF
                print(f"    0x{addr:04X}: LFSR {fsr}, 0x{val:03X}")
                addr += 4
                continue
        elif word in [0x0008, 0x0009, 0x000A, 0x000B]:
            ops = {0x0008: "TBLRD *", 0x0009: "TBLRD *+", 0x000A: "TBLRD *-"}
            print(f"    0x{addr:04X}: {ops.get(word, 'TBLRD')}")
        else:
            print(f"    0x{addr:04X}: {word:04X}")

        addr += 2


def find_filter_count(memory: Dict[int, int]):
    """Try to determine how many filter stages per channel"""
    print("\n" + "=" * 70)
    print("FILTER COUNT ANALYSIS")
    print("=" * 70)

    # Look for loops that iterate over filter stages
    # Common pattern: MOVLW N -> MOVWF counter -> loop: ... decfsz -> bra loop

    print("\n  Searching for filter stage loops...")

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # MOVLW with values that could be filter counts (2-10)
        if (word & 0xFF00) == 0x0E00:
            val = word & 0xFF
            if 2 <= val <= 12:
                # Check if followed by loop pattern
                for scan in range(addr + 2, addr + 30, 2):
                    w = get_word(memory, scan)
                    if w and (w & 0xFE00) == 0x6E00:
                        counter_reg = w & 0xFF

                        # Look for DECFSZ
                        for scan2 in range(scan + 2, scan + 100, 2):
                            w2 = get_word(memory, scan2)
                            if w2 and (w2 & 0xFC00) == 0x4C00:
                                f = w2 & 0xFF
                                if f == counter_reg:
                                    # Found DECFSZ on same register - this is a loop!
                                    w3 = get_word(memory, scan2 + 2)
                                    if w3 and (w3 & 0xF800) == 0xD800:
                                        n = w3 & 0x07FF
                                        if n & 0x0400:
                                            n = n - 0x0800
                                        if n < 0:  # Backward branch
                                            print(
                                                f"    Loop at 0x{addr:04X}: count={val}, counter=0x{counter_reg:02X}"
                                            )
                                            print(
                                                f"      Loop body: 0x{addr:04X} - 0x{scan2:04X}"
                                            )
                                            break
                        break


def analyze_gain_delay_commands(memory: Dict[int, int]):
    """Analyze gain and delay command implementations"""
    print("\n" + "=" * 70)
    print("GAIN/DELAY IMPLEMENTATION ANALYSIS")
    print("=" * 70)

    # Command 0x17 - Set Gain
    # Command 0x21 - Set Delay
    # Command 0x29 - Get Gain

    gain_commands = {
        0x17: "SET_GAIN",
        0x21: "SET_DELAY",
        0x29: "GET_GAIN",
    }

    for cmd, name in gain_commands.items():
        print(f"\n  Command 0x{cmd:02X} ({name}):")

        for addr in range(0x1000, 0x6000, 2):
            word = get_word(memory, addr)
            if word and (word & 0xFF00) == 0x0A00 and (word & 0xFF) == cmd:
                print(f"    Found at 0x{addr:04X}")

                # Trace to handler
                for scan in range(addr, addr + 40, 2):
                    w = get_word(memory, scan)
                    if w and (w & 0xFF00) == 0xEC00:  # CALL
                        w2 = get_word(memory, scan + 2)
                        if w2:
                            target = (((w2 & 0x0FFF) << 8) | (w & 0xFF)) * 2
                            print(f"    Handler: 0x{target:04X}")
                            print(f"    Handler disassembly:")
                            disasm_function(memory, target, 25)
                            break
                break


def analyze_filter_type_encoding(memory: Dict[int, int]):
    """Find how filter types are encoded"""
    print("\n" + "=" * 70)
    print("FILTER TYPE ENCODING ANALYSIS")
    print("=" * 70)

    # Look for comparisons against filter type values
    # Filter types might be: LP, HP, BP, BS, PEAK, LS, HS, AP

    print("\n  Looking for filter type comparisons...")

    # Search for XORLW with values 0-20 (potential filter type codes)
    type_refs = defaultdict(list)

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFF00) == 0x0A00:
            val = word & 0xFF
            if val <= 20:
                type_refs[val].append(addr)

    print("\n  Values compared (potential filter types):")
    for val in sorted(type_refs.keys()):
        addrs = type_refs[val]
        if len(addrs) <= 3:  # Filter types are typically compared once
            print(
                f"    Value {val:2d}: {len(addrs)} refs at {[hex(a) for a in addrs[:3]]}"
            )


def analyze_usb_packet_structure(memory: Dict[int, int]):
    """Analyze how USB packets are parsed to understand data format"""
    print("\n" + "=" * 70)
    print("USB PACKET STRUCTURE ANALYSIS")
    print("=" * 70)

    # USB data is typically in a buffer accessed via pointers
    # Look for how the packet bytes are accessed

    # Find where packet bytes are read
    print("\n  USB packet byte access patterns:")

    # Look for indirect access (FSR) patterns
    # Byte 0 = command, Byte 1 = channel, Byte 2 = param, etc.

    # Find MOVFF instructions that copy from USB buffer
    usb_access = []

    for addr in range(0x1000, 0x2000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xC000) == 0xC000:
            word2 = get_word(memory, addr + 2)
            if word2:
                src = word & 0x0FFF
                dst = word2 & 0x0FFF

                # Check if accessing RAM locations used for USB buffer
                # USB buffer typically at 0x400-0x4FF or in GPR
                if 0x100 <= src <= 0x200 or 0x100 <= dst <= 0x200:
                    usb_access.append((addr, src, dst))

    print(f"  Found {len(usb_access)} potential USB buffer accesses")


def analyze_data_transfer_sizes(memory: Dict[int, int]):
    """Analyze how much data is transferred for each operation"""
    print("\n" + "=" * 70)
    print("DATA TRANSFER SIZE ANALYSIS")
    print("=" * 70)

    # Look for MOVLW with transfer sizes
    # IIR biquad = 5 coefficients * 3 bytes = 15 bytes minimum
    # Multiple biquads would be multiples

    print("\n  Looking for data size constants...")

    size_constants = defaultdict(list)

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFF00) == 0x0E00:
            val = word & 0xFF

            # Common sizes for audio DSP
            if val in [5, 6, 8, 10, 12, 15, 16, 20, 24, 30, 32, 40, 48, 60, 64]:
                size_constants[val].append(addr)

    print("\n  Potentially significant size constants:")
    for val in sorted(size_constants.keys()):
        addrs = size_constants[val]
        print(f"    {val:2d} bytes: {len(addrs)} refs")


def estimate_filters_per_channel(memory: Dict[int, int]):
    """Estimate number of filter stages per channel based on code analysis"""
    print("\n" + "=" * 70)
    print("FILTERS PER CHANNEL ESTIMATION")
    print("=" * 70)

    print("""
  Analysis Method:
  - Look at data structure sizes
  - Find coefficient transfer loops
  - Analyze RAM allocation per channel
""")

    # Based on USB HID report size of 64 bytes
    # And typical IIR biquad structure

    print("""
  Theoretical Calculations:
  ==========================
  USB Report: 64 bytes
  - Byte 0: Command
  - Byte 1: Channel/Filter ID  
  - Byte 2-3: Parameter
  - Bytes 4-63: Data (60 bytes max payload)
  
  IIR Biquad:
  - 5 coefficients (b0, b1, b2, a1, a2)
  - 24-bit each = 15 bytes per biquad
  - 60 bytes could hold 4 biquads
  
  However, coefficients might be sent in multiple packets.
  
  Common configurations:
  - 2-4 biquads per channel = typical crossover
  - 8+ biquads = parametric EQ
""")


def main():
    hex_file = str(Path(__file__).resolve().parents[3] / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex")
    memory = parse_intel_hex(hex_file)

    print("=" * 70)
    print("DLCP DATA STRUCTURE DEEP ANALYSIS")
    print("=" * 70)

    analyze_eeprom_structure(memory)
    analyze_channel_data_structures(memory)
    analyze_coefficient_commands(memory)
    find_filter_count(memory)
    analyze_gain_delay_commands(memory)
    analyze_filter_type_encoding(memory)
    analyze_usb_packet_structure(memory)
    analyze_data_transfer_sizes(memory)
    estimate_filters_per_channel(memory)


if __name__ == "__main__":
    main()
