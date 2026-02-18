#!/usr/bin/env python3
"""
Deep Coefficient Format Analysis - Determine exact biquad count and format
"""

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
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


def get_bytes(memory: Dict[int, int], addr: int, count: int) -> bytes:
    return bytes(memory.get(addr + i, 0xFF) for i in range(count))


def analyze_size_15_handlers(memory: Dict[int, int]):
    """Analyze where size=15 is used (5 coefficients * 3 bytes)"""
    print("=" * 70)
    print("SIZE=15 ANALYSIS (Potential Biquad Size: 5 coeffs * 3 bytes)")
    print("=" * 70)

    # Find all MOVLW 15 instructions
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFF00) == 0x0E00 and (word & 0xFF) == 15:
            print(f"\n  0x{addr:04X}: MOVLW 15")

            # Disassemble context
            for offset in range(-10, 30, 2):
                a = addr + offset
                w = get_word(memory, a)
                if w is None:
                    continue

                marker = " <--" if a == addr else ""

                if (w & 0xFF00) == 0x0E00:
                    print(f"    0x{a:04X}: MOVLW 0x{w & 0xFF:02X}{marker}")
                elif (w & 0xFE00) == 0x6E00:
                    f = w & 0xFF
                    print(f"    0x{a:04X}: MOVWF 0x{f:02X}")
                elif (w & 0xC000) == 0xC000:
                    w2 = get_word(memory, a + 2)
                    if w2:
                        src = w & 0x0FFF
                        dst = w2 & 0x0FFF
                        print(f"    0x{a:04X}: MOVFF 0x{src:03X}, 0x{dst:03X}")
                elif (w & 0xF800) == 0xD000:
                    n = w & 0x07FF
                    if n & 0x0400:
                        n = n - 0x0800
                    target = a + 2 + n * 2
                    print(f"    0x{a:04X}: RCALL 0x{target:04X}")
                elif (w & 0xFF00) == 0xEE00:
                    w2 = get_word(memory, a + 2)
                    if w2:
                        fsr = (w >> 4) & 0x03
                        val = w2 & 0x0FFF
                        print(f"    0x{a:04X}: LFSR {fsr}, 0x{val:03X}")
                elif w in [0x0008, 0x0009]:
                    print(f"    0x{a:04X}: TBLRD")
                elif w == 0x0012:
                    print(f"    0x{a:04X}: RETURN")
                    break


def analyze_size_5_handlers(memory: Dict[int, int]):
    """Analyze where size=5 is used (number of biquad coefficients)"""
    print("\n" + "=" * 70)
    print("SIZE=5 ANALYSIS (Number of Biquad Coefficients)")
    print("=" * 70)

    for addr in range(0x1000, 0x2000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFF00) == 0x0E00 and (word & 0xFF) == 5:
            print(f"\n  0x{addr:04X}: MOVLW 5")

            # Check context
            for offset in range(-6, 20, 2):
                a = addr + offset
                w = get_word(memory, a)
                if w is None:
                    continue

                marker = " <--" if a == addr else ""

                if (w & 0xFF00) == 0x0E00:
                    print(f"    0x{a:04X}: MOVLW 0x{w & 0xFF:02X}{marker}")
                elif (w & 0xFE00) == 0x6E00:
                    print(f"    0x{a:04X}: MOVWF 0x{w & 0xFF:02X}")
                elif (w & 0xC000) == 0xC000:
                    w2 = get_word(memory, a + 2)
                    if w2:
                        print(
                            f"    0x{a:04X}: MOVFF 0x{w & 0x0FFF:03X}, 0x{w2 & 0x0FFF:03X}"
                        )
                elif (w & 0xFC00) == 0x4C00:
                    print(f"    0x{a:04X}: DECFSZ 0x{w & 0xFF:02X}  ; Loop counter!")
                    # This is likely a coefficient loop
                    w2 = get_word(memory, a + 2)
                    if w2 and (w2 & 0xF800) == 0xD800:
                        n = w2 & 0x07FF
                        if n & 0x0400:
                            n = n - 0x0800
                        if n < 0:
                            print(
                                f"    0x{a + 2:04X}: BRA 0x{a + 2 + 2 + n * 2:04X}  ; Loop back"
                            )
                elif w == 0x0012:
                    print(f"    0x{a:04X}: RETURN")
                    break


def analyze_filter_stage_loops(memory: Dict[int, int]):
    """Find loops that iterate over filter stages"""
    print("\n" + "=" * 70)
    print("FILTER STAGE LOOP ANALYSIS")
    print("=" * 70)

    # Look for DECFSZ followed by BRA backward
    loops_found = []

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFC00) == 0x4C00:  # DECFSZ
            f = word & 0xFF

            word2 = get_word(memory, addr + 2)
            if word2 and (word2 & 0xF800) == 0xD800:  # BRA
                n = word2 & 0x07FF
                if n & 0x0400:
                    n = n - 0x0800

                if n < 0:  # Backward branch = loop
                    loop_start = addr + 2 + 2 + n * 2
                    loop_size = addr - loop_start + 4
                    loops_found.append((loop_start, addr, f, loop_size))

    print(f"\n  Found {len(loops_found)} loops:")
    for start, end, counter, size in loops_found[:15]:
        print(
            f"    0x{start:04X}-0x{end:04X}: counter=0x{counter:02X}, size={size} bytes"
        )

    # Analyze loop body sizes
    print("\n  Loop body size analysis:")
    print("  (Size indicates how much work per iteration)")

    # Group by size
    size_groups = defaultdict(list)
    for start, end, counter, size in loops_found:
        size_groups[size].append((start, end, counter))

    for size in sorted(size_groups.keys()):
        loops = size_groups[size]
        print(f"\n    {size} bytes per iteration: {len(loops)} loops")
        for start, end, counter in loops[:3]:
            print(f"      0x{start:04X}: counter=0x{counter:02X}")


def analyze_coefficient_structure(memory: Dict[int, int]):
    """Analyze the coefficient data structure format"""
    print("\n" + "=" * 70)
    print("COEFFICIENT DATA STRUCTURE FORMAT")
    print("=" * 70)

    print("""
  IIR Biquad Coefficient Formats:
  ================================
  Standard form: y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]
  
  Common storage formats:
  1. 5 x 24-bit = 15 bytes (most common for audio DSP)
  2. 5 x 32-bit = 20 bytes (higher precision)
  3. 5 x 16-bit = 10 bytes (lower precision)
  
  The DLCP likely uses 24-bit (Q1.23) or 32-bit (Q1.31) fixed-point.
""")


def trace_command_0x0a_detailed(memory: Dict[int, int]):
    """Detailed trace of coefficient upload command"""
    print("\n" + "=" * 70)
    print("DETAILED COMMAND 0x0A TRACE (Coefficient Upload)")
    print("=" * 70)

    # Find command 0x0A at 0x1108 and trace execution
    print("\n  Command dispatcher at 0x10C0 area:")

    addr = 0x10C0
    for _ in range(80):
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

        if (word & 0xFF00) == 0x0A00:
            print(f"    0x{addr:04X}: XORLW 0x{word & 0xFF:02X}  ; Check command byte")
        elif (word & 0xFF00) == 0xE100:
            print(f"    0x{addr:04X}: BNZ ...  ; Skip if not matched")
        elif (word & 0xFF00) == 0xE000:
            print(f"    0x{addr:04X}: BZ ...  ; Branch if matched")
        elif (word & 0xF800) == 0xD000:
            n = word & 0x07FF
            if n & 0x0400:
                n = n - 0x0800
            target = addr + 2 + n * 2
            print(f"    0x{addr:04X}: RCALL 0x{target:04X}")
        elif (word & 0xFF00) == 0xEC00:
            word2 = get_word(memory, addr + 2)
            if word2:
                target = (((word2 & 0x0FFF) << 8) | (word & 0xFF)) * 2
                print(f"    0x{addr:04X}: CALL 0x{target:04X}")
                addr += 4
                continue
        elif (word & 0xFF00) == 0xEF00:
            word2 = get_word(memory, addr + 2)
            if word2:
                target = (((word2 & 0x0FFF) << 8) | (word & 0xFF)) * 2
                print(f"    0x{addr:04X}: GOTO 0x{target:04X}")
                addr += 4
                continue
        elif word == 0x0012:
            print(f"    0x{addr:04X}: RETURN")
            break
        elif (word & 0xFF00) == 0x0E00:
            print(f"    0x{addr:04X}: MOVLW 0x{word & 0xFF:02X}")
        elif (word & 0xFE00) == 0x6E00:
            print(f"    0x{addr:04X}: MOVWF 0x{word & 0xFF:02X}")
        else:
            print(f"    0x{addr:04X}: {word:04X}")

        addr += 2


def find_channel_index_usage(memory: Dict[int, int]):
    """Find how channel index is used to access data"""
    print("\n" + "=" * 70)
    print("CHANNEL INDEXING ANALYSIS")
    print("=" * 70)

    # Look for multiplication or offset calculation based on channel
    # Common pattern: channel * struct_size

    print("\n  Looking for channel offset calculations...")

    # MOVLW followed by operations that use it as multiplier/offset
    for addr in range(0x1000, 0x2000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFF00) == 0x0E00:
            val = word & 0xFF

            # Check if this is used as a struct size multiplier
            # Pattern: MOVLW N -> used in multiplication or offset
            if val in [5, 6, 8, 10, 12, 15, 16, 20, 24, 30, 32, 48]:
                # Check next few instructions
                for scan in range(addr + 2, addr + 20, 2):
                    w = get_word(memory, scan)
                    if w is None:
                        break

                    # Look for MULWF, ADDWF, or offset calculation
                    if (w & 0xFC00) == 0x2400:  # ADDWF
                        print(
                            f"  0x{addr:04X}: MOVLW {val} -> 0x{scan:04X}: ADDWF (offset calc)"
                        )
                        break
                    if (w & 0xFF00) == 0x0D00:  # MULLW
                        w2 = get_word(memory, addr - 2)
                        if w2 and (w2 & 0xFF00) == 0x0E00:
                            ch = w2 & 0xFF
                            if ch <= 5:
                                print(
                                    f"  0x{addr - 2:04X}: MOVLW {ch} (channel) -> MULLW {val} = offset"
                                )
                                break


def analyze_program_memory_tables(memory: Dict[int, int]):
    """Look for coefficient tables stored in program memory"""
    print("\n" + "=" * 70)
    print("PROGRAM MEMORY TABLE ANALYSIS")
    print("=" * 70)

    # Look for areas that might contain filter coefficient tables
    # These would be read via TBLRD

    print("\n  Searching for potential coefficient data in program memory...")

    # Look for blocks of data that could be coefficients
    # Coefficients are typically small integers (-2.0 to +2.0)
    # In Q1.23 format: range is roughly -16777216 to +16777216

    candidates = []

    for start in range(0x1000, 0x6000, 0x20):
        # Check 32-byte block
        data = get_bytes(memory, start, 32)

        # Skip if mostly 0xFF
        if data.count(0xFF) > 24:
            continue

        # Check if data looks like coefficients (not code)
        # Code typically has patterns, coefficients are more random
        unique_bytes = len(set(data))

        if unique_bytes > 10 and unique_bytes < 30:
            # Might be data
            candidates.append((start, unique_bytes, data[:16]))

    print(f"\n  Found {len(candidates)} potential data blocks:")
    for addr, unique, sample in candidates[:10]:
        hex_str = " ".join(f"{b:02X}" for b in sample)
        print(f"    0x{addr:04X}: {unique} unique bytes: {hex_str}")


def main():
    hex_file = str(Path(__file__).resolve().parents[3] / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex")
    memory = parse_intel_hex(hex_file)

    print("=" * 70)
    print("DLCP COEFFICIENT FORMAT DEEP ANALYSIS")
    print("=" * 70)

    analyze_size_15_handlers(memory)
    analyze_size_5_handlers(memory)
    analyze_filter_stage_loops(memory)
    analyze_coefficient_structure(memory)
    trace_command_0x0a_detailed(memory)
    find_channel_index_usage(memory)
    analyze_program_memory_tables(memory)


if __name__ == "__main__":
    main()
