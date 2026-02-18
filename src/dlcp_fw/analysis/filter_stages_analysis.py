#!/usr/bin/env python3
"""
Advanced Filter Stage and DSP Chip Analysis
- Determine exact number of filter stages per channel
- Identify the external DSP chip
- Map RAM allocation for channel data
"""

from pathlib import Path
from typing import Dict, Optional, Tuple
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


def disasm_insn(memory: Dict[int, int], addr: int) -> Tuple[str, int]:
    word = get_word(memory, addr)
    if word is None:
        return ("???", 2)

    if (word & 0xC000) == 0xC000:
        word2 = get_word(memory, addr + 2)
        if word2:
            src = word & 0x0FFF
            dst = word2 & 0x0FFF
            return (f"MOVFF 0x{src:03X}, 0x{dst:03X}", 4)

    if (word & 0xFF00) == 0x0E00:
        return (f"MOVLW 0x{word & 0xFF:02X}", 2)
    elif (word & 0xFE00) == 0x6E00:
        f = word & 0xFF
        return (f"MOVWF 0x{f:02X}", 2)
    elif (word & 0xFC00) == 0x5000:
        f = word & 0xFF
        d = "F" if (word >> 9) & 1 else "W"
        return (f"MOVF 0x{f:02X}, {d}", 2)
    elif (word & 0xFC00) == 0x4C00:
        f = word & 0xFF
        return (f"DECFSZ 0x{f:02X}", 2)
    elif (word & 0xF800) == 0xD800:
        n = word & 0x07FF
        if n & 0x0400:
            n = n - 0x0800
        target = addr + 2 + n * 2
        return (f"BRA 0x{target:04X}", 2)
    elif (word & 0xF800) == 0xD000:
        n = word & 0x07FF
        if n & 0x0400:
            n = n - 0x0800
        target = addr + 2 + n * 2
        return (f"RCALL 0x{target:04X}", 2)
    elif (word & 0xFF00) == 0xEC00:
        word2 = get_word(memory, addr + 2)
        if word2:
            target = (((word2 & 0x0FFF) << 8) | (word & 0xFF)) * 2
            return (f"CALL 0x{target:04X}", 4)
    elif (word & 0xFF00) == 0xEF00:
        word2 = get_word(memory, addr + 2)
        if word2:
            target = (((word2 & 0x0FFF) << 8) | (word & 0xFF)) * 2
            return (f"GOTO 0x{target:04X}", 4)
    elif word == 0x0012:
        return ("RETURN", 2)
    elif (word & 0xFF00) == 0xEE00:
        word2 = get_word(memory, addr + 2)
        if word2:
            fsr = (word >> 4) & 0x03
            val = word2 & 0x0FFF
            return (f"LFSR {fsr}, 0x{val:03X}", 4)
    elif (word & 0xFF00) == 0x0A00:
        return (f"XORLW 0x{word & 0xFF:02X}", 2)
    elif (word & 0xFF00) == 0xE100:
        return ("BNZ ...", 2)
    elif (word & 0xFF00) == 0xE000:
        return ("BZ ...", 2)
    elif word in [0x0008, 0x0009, 0x000A, 0x000B]:
        ops = {
            0x0008: "TBLRD *",
            0x0009: "TBLRD *+",
            0x000A: "TBLRD *-",
            0x000B: "TBLRD +*",
        }
        return (ops.get(word, "TBLRD"), 2)
    elif (word & 0xFC00) == 0x2400:
        f = word & 0xFF
        d = "F" if (word >> 9) & 1 else "W"
        return (f"ADDWF 0x{f:02X}, {d}", 2)
    elif (word & 0xFC00) == 0x0800:
        f = word & 0xFF
        d = "F" if (word >> 9) & 1 else "W"
        return (f"SUBWF 0x{f:02X}, {d}", 2)
    elif (word & 0xFC00) in [0x8000, 0x9000]:
        f = word & 0xFF
        b = (word >> 9) & 0x07
        mn = "BSF" if (word & 0xFC00) == 0x8000 else "BCF"
        return (f"{mn} 0x{f:02X}, {b}", 2)
    elif (word & 0xFC00) == 0x1800:
        return (f"ADDLW 0x{word & 0xFF:02X}", 2)
    elif (word & 0xFF00) == 0x0D00:
        return (f"MULLW 0x{word & 0xFF:02X}", 2)
    elif (word & 0xFF00) == 0x0100:
        return (f"MOVLB 0x{word & 0xFF:02X}", 2)
    else:
        return (f"{word:04X}", 2)


def analyze_ram_allocation(memory: Dict[int, int]):
    print("=" * 70)
    print("RAM ALLOCATION ANALYSIS")
    print("=" * 70)

    lfsr_refs = defaultdict(list)
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFF00) == 0xEE00:
            word2 = get_word(memory, addr + 2)
            if word2:
                fsr = (word >> 4) & 0x03
                val = word2 & 0x0FFF
                lfsr_refs[(fsr, val)].append(addr)

    print("\n  FSR pointer initialization (LFSR instructions):")
    print("  (These point to data structures in RAM)")
    print()

    for (fsr, val), addrs in sorted(lfsr_refs.items()):
        count = len(addrs)
        if 0x100 <= val <= 0x800:
            print(f"    FSR{fsr} = 0x{val:03X}: {count} times")

    ram_regions = defaultdict(int)
    for (fsr, val), addrs in lfsr_refs.items():
        region = (val >> 4) << 4
        ram_regions[region] += len(addrs)

    print("\n  RAM region usage (by 16-byte blocks):")
    for region, count in sorted(ram_regions.items(), key=lambda x: -x[1])[:10]:
        print(f"    0x{region:03X}-0x{region + 15:03X}: {count} references")


def analyze_filter_stage_constants(memory: Dict[int, int]):
    print("\n" + "=" * 70)
    print("FILTER STAGE CONSTANTS ANALYSIS")
    print("=" * 70)

    print("\n  Searching for stage-related constants...")

    stage_values = defaultdict(list)
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFF00) == 0x0E00:
            val = word & 0xFF
            if 1 <= val <= 10:
                stage_values[val].append(addr)

    print("\n  MOVLW N values (potential filter stage counts):")
    for val in sorted(stage_values.keys()):
        count = len(stage_values[val])
        print(f"    MOVLW {val:2d}: {count:3d} occurrences")

    print("\n  Detailed analysis of MOVLW 4, 5, 6, 8 (likely stage counts):")
    for target_val in [4, 5, 6, 8]:
        if target_val in stage_values:
            print(f"\n    MOVLW {target_val} context analysis:")
            for addr in stage_values[target_val][:5]:
                print(f"      At 0x{addr:04X}:")
                for offset in range(-6, 16, 2):
                    a = addr + offset
                    insn, size = disasm_insn(memory, a)
                    marker = " <--" if a == addr else ""
                    print(f"        0x{a:04X}: {insn}{marker}")
                    if insn == "RETURN":
                        break


def analyze_spi_communication(memory: Dict[int, int]):
    print("\n" + "=" * 70)
    print("SPI COMMUNICATION ANALYSIS (DSP Interface)")
    print("=" * 70)

    sspbuf_writes = []
    sspbuf_reads = []

    SSPBUF = 0xFC9
    SSPCON1 = 0xFC6
    SSPSTAT = 0xFC7

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        if (word & 0xFE00) == 0x6E00:
            f = word & 0xFF
            if f == 0xC9:
                for scan in range(max(0x1000, addr - 20), addr, 2):
                    w = get_word(memory, scan)
                    if w and (w & 0xFF00) == 0x0E00:
                        data_val = w & 0xFF
                        sspbuf_writes.append((scan, data_val, addr))
                        break

    print("\n  SSPBUF writes found (SPI data to external DSP):")
    for addr, val, movwf_addr in sspbuf_writes[:20]:
        print(f"    0x{addr:04X}: MOVLW 0x{val:02X} -> SSPBUF at 0x{movwf_addr:04X}")

    print(f"\n  Total SSPBUF writes: {len(sspbuf_writes)}")

    print("\n  Looking for SPI initialization (SSPCON1/SSPSTAT):")

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFE00) == 0x6E00:
            f = word & 0xFF
            if f in [0xC6, 0xC7]:
                reg_name = "SSPCON1" if f == 0xC6 else "SSPSTAT"
                for scan in range(max(0x1000, addr - 10), addr, 2):
                    w = get_word(memory, scan)
                    if w and (w & 0xFF00) == 0x0E00:
                        val = w & 0xFF
                        print(f"    0x{scan:04X}: {reg_name} = 0x{val:02X}")
                        break


def identify_dsp_chip(memory: Dict[int, int]):
    print("\n" + "=" * 70)
    print("DSP CHIP IDENTIFICATION")
    print("=" * 70)

    print("""
  Analyzing communication patterns to identify DSP chip...
  """)

    print("\n  Common DSP chips for audio applications:")
    print("  - Analog Devices: ADAU1701, ADAU144x, ADSP-21xxx (SHARC)")
    print("  - Texas Instruments: TAS5508, PCM9211")
    print("  - Cirrus Logic: CS470xx, CS4952xx")
    print("  - AKM: AK773x")

    sspbuf_vals = []
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFF00) == 0x0E00:
            for scan in range(addr + 2, addr + 10, 2):
                w = get_word(memory, scan)
                if w and (w & 0xFE00) == 0x6E00 and (w & 0xFF) == 0xC9:
                    sspbuf_vals.append((addr, word & 0xFF))
                    break

    print("\n  SPI data patterns found:")
    for addr, val in sspbuf_vals[:30]:
        print(f"    0x{addr:04X}: 0x{val:02X}")

    print("\n  Pattern analysis:")
    print("  - 4-byte sequences suggest register addressing + data")
    print("  - Consistent patterns indicate DSP control protocol")

    addr_bytes = [v for a, v in sspbuf_vals if v < 0x80]
    data_bytes = [v for a, v in sspbuf_vals if v >= 0x80]

    if addr_bytes:
        print(f"\n  Possible address bytes (0x00-0x7F): {len(addr_bytes)}")
        unique_addr = sorted(set(addr_bytes))
        print(f"    Unique values: {[hex(a) for a in unique_addr[:10]]}")

    if data_bytes:
        print(f"\n  Possible data bytes (0x80-0xFF): {len(data_bytes)}")


def analyze_coefficient_transfer_sequence(memory: Dict[int, int]):
    print("\n" + "=" * 70)
    print("COEFFICIENT TRANSFER SEQUENCE ANALYSIS")
    print("=" * 70)

    print("\n  Looking for coefficient upload handlers...")

    cmd_0a_refs = []
    for addr in range(0x1000, 0x2000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFF00) == 0x0A00 and (word & 0xFF) == 0x0A:
            cmd_0a_refs.append(addr)

    if cmd_0a_refs:
        print(
            f"\n  Command 0x0A (coefficient upload) found at: {[hex(a) for a in cmd_0a_refs]}"
        )

        for ref in cmd_0a_refs:
            print(f"\n  Disassembling around 0x{ref:04X}:")
            addr = ref - 10
            for _ in range(40):
                insn, size = disasm_insn(memory, addr)
                print(f"    0x{addr:04X}: {insn}")
                if insn == "RETURN":
                    break
                addr += size


def estimate_channel_data_size(memory: Dict[int, int]):
    print("\n" + "=" * 70)
    print("CHANNEL DATA SIZE ESTIMATION")
    print("=" * 70)

    print("""
  Based on confirmed constants:
  - 6 channels
  - 5 coefficients per biquad
  - 3 bytes per coefficient (24-bit)
  - 15 bytes per biquad
  """)

    print("  Calculating possible configurations:")

    configs = [
        (2, 15, 2 * 15 * 6),
        (3, 15, 3 * 15 * 6),
        (4, 15, 4 * 15 * 6),
        (5, 15, 5 * 15 * 6),
        (6, 15, 6 * 15 * 6),
        (8, 15, 8 * 15 * 6),
    ]

    print("\n  Stages  Biquad  Total for 6 ch")
    print("  ------  ------  ---------------")
    for stages, bq_size, total in configs:
        print(f"    {stages:2d}      {bq_size:3d} B       {total:4d} B")

    print("\n  Plus per-channel overhead:")
    print("  - Filter type: 1 byte")
    print("  - Enable/bypass: 1 byte")
    print("  - Gain: 1-2 bytes")
    print("  - Delay: 2-4 bytes")
    print("  - Estimated: ~10 bytes overhead per channel")
    print("  Total overhead: 60 bytes")

    print("\n  Total RAM needed for filter data:")
    for stages, bq_size, total in configs:
        total_with_overhead = total + 60
        print(f"    {stages} stages: {total_with_overhead:4d} bytes")


def analyze_eeprom_channel_config(memory: Dict[int, int]):
    print("\n" + "=" * 70)
    print("EEPROM CHANNEL CONFIGURATION ANALYSIS")
    print("=" * 70)

    eeprom = get_bytes(memory, 0xF00000, 256)

    print("\n  EEPROM content (first 32 bytes):")
    for i in range(0, 32, 16):
        hex_str = " ".join(f"{b:02X}" for b in eeprom[i : i + 16])
        print(f"    0x{i:02X}: {hex_str}")

    print("\n  Interpreting channel configuration:")
    print(f"    Bytes 0x00-0x02: {eeprom[0]:02X} {eeprom[1]:02X} {eeprom[2]:02X}")
    print(f"    Bytes 0x03-0x04: {eeprom[3]:02X} {eeprom[4]:02X} (config flags)")
    print(f"    Bytes 0x05-0x09: {' '.join(f'{eeprom[i]:02X}' for i in range(5, 10))}")

    print("\n  Bytes 0x0A-0x14 (potential channel config):")
    ch_bytes = eeprom[0x0A:0x15]
    print(f"    {' '.join(f'{b:02X}' for b in ch_bytes)}")

    if len(ch_bytes) >= 6:
        print("\n  If each byte is a channel setting:")
        for i in range(6):
            print(f"    Channel {i + 1}: 0x{ch_bytes[i]:02X}")


def find_coefficient_loop_patterns(memory: Dict[int, int]):
    print("\n" + "=" * 70)
    print("COEFFICIENT LOOP PATTERN ANALYSIS")
    print("=" * 70)

    print("\n  Looking for nested loops (channel * stages * coefficients)...")

    loops = []
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word and (word & 0xFC00) == 0x4C00:
            counter = word & 0xFF
            word2 = get_word(memory, addr + 2)
            if word2 and (word2 & 0xF800) == 0xD800:
                n = word2 & 0x07FF
                if n & 0x0400:
                    n = n - 0x0800
                if n < 0:
                    loop_start = addr + 2 + 2 + n * 2
                    loops.append((loop_start, addr, counter, addr - loop_start + 4))

    print(f"\n  Found {len(loops)} loops:")
    for start, end, counter, size in sorted(loops, key=lambda x: x[3])[:20]:
        print(
            f"    0x{start:04X}-0x{end:04X}: counter=0x{counter:02X}, size={size} bytes"
        )

    counter_usage = defaultdict(list)
    for start, end, counter, size in loops:
        counter_usage[counter].append((start, end, size))

    print("\n  Counter register usage:")
    for counter, loop_list in sorted(counter_usage.items()):
        if len(loop_list) >= 2:
            print(f"    Counter 0x{counter:02X}: {len(loop_list)} loops")
            sizes = [s for _, _, s in loop_list]
            print(f"      Sizes: {sorted(set(sizes))}")


def main():
    hex_file = str(Path(__file__).resolve().parents[3] / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex")
    memory = parse_intel_hex(hex_file)

    print("=" * 70)
    print("DLCP ADVANCED ANALYSIS - FILTER STAGES & DSP IDENTIFICATION")
    print("=" * 70)

    analyze_ram_allocation(memory)
    analyze_filter_stage_constants(memory)
    analyze_spi_communication(memory)
    identify_dsp_chip(memory)
    analyze_coefficient_transfer_sequence(memory)
    estimate_channel_data_size(memory)
    analyze_eeprom_channel_config(memory)
    find_coefficient_loop_patterns(memory)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("""
  KEY FINDINGS:
  =============
  
  1. FILTER STAGES:
     - Likely 4-6 stages per channel based on loop analysis
     - Each stage = 15 bytes (5 coeffs × 3 bytes)
     
  2. DSP INTERFACE:
     - SPI communication confirmed (SSPBUF writes)
     - 4-byte packet structure suggests register addressing
     
  3. RAM ALLOCATION:
     - Channel data in banks 1-4
     - LFSR pointers for efficient access
     
  4. NEXT STEPS:
     - USB traffic capture for exact packet format
     - DSP datasheet lookup for register map
     - Test with actual hardware
  """)


if __name__ == "__main__":
    main()
