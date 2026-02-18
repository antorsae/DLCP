#!/usr/bin/env python3
"""
Channel and DSP Analysis - Find all 6 channels and DSP output interface
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


def find_channel_references(memory: Dict[int, int]):
    """Find all references to channel numbers 0-5 or 1-6"""
    print("=" * 70)
    print("CHANNEL REFERENCE ANALYSIS")
    print("=" * 70)

    # Look for MOVLW instructions with values 0-6 (could be channel indices)
    channel_compares = defaultdict(list)

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # MOVLW with small values
        if (word & 0xFF00) == 0x0E00:
            val = word & 0xFF
            if val <= 6:
                channel_compares[val].append(addr)

        # XORLW with small values (comparisons)
        if (word & 0xFF00) == 0x0A00:
            val = word & 0xFF
            if val <= 6:
                channel_compares[val].append(addr)

        # SUBLW with small values
        if (word & 0xFF00) == 0x0800:
            val = word & 0xFF
            if val <= 6:
                channel_compares[val].append(addr)

    print("\n  References to values 0-6 (potential channel indices):")
    for val in sorted(channel_compares.keys()):
        addrs = channel_compares[val]
        print(f"\n    Value {val}: {len(addrs)} references")
        for a in addrs[:10]:
            word = get_word(memory, a)
            mn = (
                "MOVLW"
                if (word & 0xFF00) == 0x0E00
                else "XORLW"
                if (word & 0xFF00) == 0x0A00
                else "SUBLW"
            )
            print(f"      0x{a:04X}: {mn} {val}")


def find_lfsr_channel_pointers(memory: Dict[int, int]):
    """Find LFSR instructions pointing to channel data structures"""
    print("\n" + "=" * 70)
    print("LFSR CHANNEL POINTER ANALYSIS")
    print("=" * 70)

    lfsr_refs = defaultdict(list)

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        if (word & 0xFF00) == 0xEE00:  # LFSR first word
            word2 = get_word(memory, addr + 2)
            if word2:
                fsr = (word >> 4) & 0x03
                value = word2 & 0x0FFF
                lfsr_refs[value].append((addr, fsr))

    print("\n  LFSR target values (grouped by similar addresses):")

    # Group by address ranges
    ranges = defaultdict(list)
    for value, refs in sorted(lfsr_refs.items()):
        range_key = (value // 16) * 16
        ranges[range_key].extend([(v, refs) for v, refs in [(value, refs)]])

    for range_start in sorted(ranges.keys()):
        print(f"\n  Range 0x{range_start:03X}-0x{range_start + 15:03X}:")
        for value, refs in sorted(lfsr_refs.items()):
            if range_start <= value < range_start + 16:
                addrs = ", ".join(f"0x{a:04X}(FSR{f})" for a, f in refs[:5])
                print(f"    0x{value:03X}: {len(refs)} refs - {addrs}")


def find_spi_i2c_uart(memory: Dict[int, int]):
    """Find SPI, I2C, or UART communication code"""
    print("\n" + "=" * 70)
    print("EXTERNAL INTERFACE ANALYSIS (SPI/I2C/UART)")
    print("=" * 70)

    # PIC18F2550 peripheral registers
    spi_regs = {
        0xFC6: "SSPBUF",  # SPI/I2C buffer
        0xFC7: "SSPCON1",  # SPI/I2C control 1
        0xFC8: "SSPSTAT",  # SPI/I2C status
        0xFC9: "SSPCON2",  # I2C control 2
        0xFCA: "SSPADD",  # I2C address/baud
    }

    usart_regs = {
        0xFAB: "TXSTA",  # TX status
        0xFAC: "RCSTA",  # RX status
        0xFAD: "TXREG",  # TX register
        0xFAE: "RCREG",  # RX register
        0xFAF: "SPBRG",  # Baud rate
        0xFB0: "SPBRGH",  # Baud rate high
    }

    print("\n  SPI/I2C Register Access:")
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # MOVFF accessing SPI/I2C registers
        if (word & 0xC000) == 0xC000:
            word2 = get_word(memory, addr + 2)
            if word2:
                src = word1 = word & 0x0FFF
                dst = word2 & 0x0FFF
                if src in spi_regs or dst in spi_regs:
                    src_name = spi_regs.get(src, f"0x{src:03X}")
                    dst_name = spi_regs.get(dst, f"0x{dst:03X}")
                    print(f"    0x{addr:04X}: MOVFF {src_name}, {dst_name}")

        # MOVWF to SPI/I2C registers
        if (word & 0xFE00) == 0x6E00:
            file_reg = word & 0xFF
            if file_reg in [0xC6, 0xC7, 0xC8]:  # Low byte of SSP registers
                print(f"    0x{addr:04X}: MOVWF to SSP register")

    print("\n  USART Register Access:")
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        if (word & 0xC000) == 0xC000:
            word2 = get_word(memory, addr + 2)
            if word2:
                src = word & 0x0FFF
                dst = word2 & 0x0FFF
                if src in usart_regs or dst in usart_regs:
                    src_name = usart_regs.get(src, f"0x{src:03X}")
                    dst_name = usart_regs.get(dst, f"0x{dst:03X}")
                    print(f"    0x{addr:04X}: MOVFF {src_name}, {dst_name}")


def find_coefficient_operations(memory: Dict[int, int]):
    """Analyze filter coefficient handling"""
    print("\n" + "=" * 70)
    print("FILTER COEFFICIENT ANALYSIS")
    print("=" * 70)

    # Find TBLRD operations (table reads - used to read program memory)
    print("\n  Table Read Operations (reading filter data from flash):")
    tblrd_count = 0
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word in [0x0008, 0x0009, 0x000A, 0x000B, 0x000C, 0x000D, 0x000E, 0x000F]:
            tblrd_count += 1
            ops = {
                0x0008: "TBLRD *",
                0x0009: "TBLRD *+",
                0x000A: "TBLRD *-",
                0x000B: "TBLRD +*",
                0x000C: "TBLWT *",
                0x000D: "TBLWT *+",
                0x000E: "TBLWT *-",
                0x000F: "TBLWT +*",
            }
            if tblrd_count <= 15:
                print(f"    0x{addr:04X}: {ops.get(word, 'TBLRD/TBLWT')}")

    print(f"\n  Total TBLRD/TBLWT operations: {tblrd_count}")

    # Find coefficient data patterns
    print("\n  Searching for coefficient data structures in program memory...")

    # Look for patterns that could be filter coefficients
    # IIR biquad: 5 coefficients (b0, b1, b2, a1, a2) typically 24-bit or 32-bit
    # FIR: many coefficients

    for start_addr in range(0x1000, 0x6000, 0x100):
        # Check for potential coefficient block
        data = get_bytes(memory, start_addr, 32)

        # Skip if mostly 0xFF or 0x00
        if data.count(0xFF) > 28 or data.count(0x00) > 28:
            continue

        # Check for reasonable coefficient values (small signed integers)
        # Coefficients are typically in range -2.0 to +2.0 for audio
        # Represented as 24-bit signed fixed-point


def analyze_filter_command_handlers(memory: Dict[int, int]):
    """Analyze command handlers that deal with filters"""
    print("\n" + "=" * 70)
    print("FILTER COMMAND HANDLER ANALYSIS")
    print("=" * 70)

    # Commands 0x0A, 0x0D, 0x0F, 0x07 appear to be filter-related
    filter_cmds = [0x0A, 0x0D, 0x0F, 0x07, 0x06, 0x05]

    for cmd in filter_cmds:
        print(f"\n  Command 0x{cmd:02X} handlers:")

        # Find where this command is compared
        for addr in range(0x1000, 0x6000, 2):
            word = get_word(memory, addr)
            if (word & 0xFF00) == 0x0A00 and (word & 0xFF) == cmd:
                print(f"    Compared at 0x{addr:04X}")

                # Disassemble a few instructions around it
                print("    Context:")
                for offset in range(-4, 20, 2):
                    a = addr + offset
                    w = get_word(memory, a)
                    if w:
                        if (w & 0xFF00) == 0x0A00:
                            print(f"      0x{a:04X}: XORLW 0x{w & 0xFF:02X}")
                        elif (w & 0xFF00) == 0xE100:
                            print(f"      0x{a:04X}: BNZ ...")
                        elif (w & 0xFF00) == 0xE000:
                            print(f"      0x{a:04X}: BZ ...")
                        elif (w & 0xF800) == 0xD000:
                            print(f"      0x{a:04X}: RCALL ...")
                        elif (w & 0xFF00) == 0xEC00:
                            w2 = get_word(memory, a + 2)
                            if w2:
                                target = (((w2 & 0x0FFF) << 8) | (w & 0xFF)) * 2
                                print(f"      0x{a:04X}: CALL 0x{target:04X}")
                                break
                        elif (w & 0xFF00) == 0xEF00:
                            w2 = get_word(memory, a + 2)
                            if w2:
                                target = (((w2 & 0x0FFF) << 8) | (w & 0xFF)) * 2
                                print(f"      0x{a:04X}: GOTO 0x{target:04X}")
                                break
                break


def find_channel_data_structures(memory: Dict[int, int]):
    """Look for channel data structure arrays"""
    print("\n" + "=" * 70)
    print("CHANNEL DATA STRUCTURE SEARCH")
    print("=" * 70)

    # Look for repeated patterns that could be channel structures
    # Each channel might have: config bytes, coefficient pointers, state variables

    # Search RAM areas for structure patterns
    # In PIC18, RAM is organized as banks of 256 bytes

    print("\n  Looking for channel structures in RAM access patterns...")

    # Count access patterns that suggest arrays
    file_access = defaultdict(int)

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # MOVWF with BSR addressing
        if (word & 0xFE00) == 0x6E00:
            f = word & 0xFF
            a = (word >> 8) & 1
            if a:  # BSR addressing
                file_access[f] += 1

    print("\n  Frequently accessed file registers (potential array elements):")
    for f, count in sorted(file_access.items(), key=lambda x: -x[1])[:20]:
        print(f"    0x{f:02X}: {count} accesses")

    # Look for sequential access patterns (array indexing)
    print("\n  Sequential file register patterns (array indices):")
    sequences = []
    current_seq = []

    for f in sorted(file_access.keys()):
        if not current_seq or f == current_seq[-1] + 1:
            current_seq.append(f)
        else:
            if len(current_seq) >= 6:
                sequences.append(current_seq)
            current_seq = [f]

    if len(current_seq) >= 6:
        sequences.append(current_seq)

    for seq in sequences:
        print(f"    0x{seq[0]:02X}-0x{seq[-1]:02X}: {len(seq)} consecutive registers")


def analyze_dsp_output(memory: Dict[int, int]):
    """Look for how filter data is output to external DSP"""
    print("\n" + "=" * 70)
    print("DSP OUTPUT ANALYSIS")
    print("=" * 70)

    # DLCP likely has a separate DSP chip (like SHARC or similar)
    # The PIC18F acts as a controller, sending filter coefficients to the DSP

    print("""
  DLCP Architecture Theory:
  - PIC18F2550 is the USB interface controller
  - Filter coefficients are uploaded via USB HID
  - PIC18F sends coefficients to external DSP (via SPI/I2C)
  - The actual audio processing is done by the DSP, not PIC18F
""")

    # Look for PORT register access (bit-banged SPI?)
    print("  PORT Register Access (potential bit-banged SPI):")

    port_regs = {
        0xF80: "PORTA",
        0xF81: "PORTB",
        0xF82: "PORTC",
        0xF89: "LATA",
        0xF8A: "LATB",
        0xF8B: "LATC",
        0xF92: "TRISA",
        0xF93: "TRISB",
        0xF94: "TRISC",
    }

    port_access = defaultdict(list)

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # BSF/BCF on PORT registers
        if (word & 0xFC00) in [0x8000, 0x9000]:  # BSF, BCF
            f = word & 0xFF
            b = (word >> 9) & 0x07
            a = (word >> 8) & 1

            if not a:  # ACCESS bank - could be PORT registers
                port_access[(f, b)].append(addr)

    # Find frequently toggled bits (likely SPI clock, data, CS)
    print("\n  Frequently accessed port bits:")
    for (f, b), addrs in sorted(port_access.items(), key=lambda x: -len(x[1]))[:15]:
        print(f"    PORT 0x{f:02X} bit {b}: {len(addrs)} accesses")


def main():
    hex_file = str(Path(__file__).resolve().parents[3] / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex")
    memory = parse_intel_hex(hex_file)

    print("=" * 70)
    print("DLCP CHANNEL AND DSP ANALYSIS")
    print("=" * 70)

    find_channel_references(memory)
    find_lfsr_channel_pointers(memory)
    find_spi_i2c_uart(memory)
    find_coefficient_operations(memory)
    analyze_filter_command_handlers(memory)
    find_channel_data_structures(memory)
    analyze_dsp_output(memory)


if __name__ == "__main__":
    main()
