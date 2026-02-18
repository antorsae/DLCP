#!/usr/bin/env python3
"""
Deep DSP Communication Analysis - Understand SPI/I2C protocol to external DSP
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


def get_bytes(memory: Dict[int, int], addr: int, count: int) -> bytes:
    return bytes(memory.get(addr + i, 0xFF) for i in range(count))


def analyze_spi_communication(memory: Dict[int, int]):
    """Deep dive into SPI communication"""
    print("=" * 70)
    print("SPI COMMUNICATION PROTOCOL ANALYSIS")
    print("=" * 70)

    # Find all SSPBUF writes and reads
    sspbuf_writes = []
    sspbuf_reads = []

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # MOVFF to SSPBUF (write)
        if (word & 0xC000) == 0xC000:
            word2 = get_word(memory, addr + 2)
            if word2:
                dst = word2 & 0x0FFF
                if dst == 0xFC6:  # SSPBUF
                    src = word & 0x0FFF
                    sspbuf_writes.append((addr, src))

        # MOVFF from SSPBUF (read)
        if (word & 0xC000) == 0xC000:
            src = word & 0x0FFF
            if src == 0xFC6:  # SSPBUF
                word2 = get_word(memory, addr + 2)
                if word2:
                    dst = word2 & 0x0FFF
                    sspbuf_reads.append((addr, dst))

    print(f"\n  SSPBUF Writes (data sent to external DSP): {len(sspbuf_writes)}")
    print(f"  SSPBUF Reads (data received from external DSP): {len(sspbuf_reads)}")

    # Analyze patterns in SSPBUF writes
    print("\n  SSPBUF Write Analysis:")
    print("  (Data source registers - these hold bytes to send to DSP)")

    src_counts = defaultdict(int)
    for addr, src in sspbuf_writes:
        src_counts[src] += 1

    for src, count in sorted(src_counts.items(), key=lambda x: -x[1]):
        print(f"    Source 0x{src:03X}: {count} writes")

    return sspbuf_writes, sspbuf_reads


def trace_spi_functions(memory: Dict[int, int], sspbuf_writes, sspbuf_reads):
    """Trace back from SPI operations to find the functions that do DSP communication"""
    print("\n" + "=" * 70)
    print("SPI FUNCTION TRACING")
    print("=" * 70)

    # Find functions that contain SSPBUF writes
    spi_functions = set()

    for write_addr, src in sspbuf_writes:
        # Walk backwards to find function start
        addr = write_addr
        for _ in range(200):
            addr -= 2
            word = get_word(memory, addr)
            if word is None:
                break

            # Found a CALL or GOTO target?
            if (word & 0xFF00) == 0xEF00 or (word & 0xFF00) == 0xEC00:
                # This might be the function entry
                break

            # Found RETURN?
            if word == 0x0012 or word == 0x0010:
                # Previous instruction might be function start
                spi_functions.add(addr + 2)
                break

    print(f"\n  Found {len(spi_functions)} potential SPI functions")
    for func_addr in sorted(spi_functions)[:10]:
        print(f"    0x{func_addr:04X}")

    # Disassemble a key SPI function
    if sspbuf_writes:
        # Find the function containing the first SSPBUF write
        first_write = sspbuf_writes[0][0]

        print(f"\n  Analyzing SPI function near 0x{first_write:04X}:")

        # Disassemble from a bit before the write
        start = first_write - 30
        if start < 0x1000:
            start = 0x1000

        addr = start
        for _ in range(30):
            word = get_word(memory, addr)
            if word is None:
                break

            # Quick decode
            if (word & 0xC000) == 0xC000:
                word2 = get_word(memory, addr + 2)
                if word2:
                    src = word & 0x0FFF
                    dst = word2 & 0x0FFF
                    marker = " <-- SSPBUF" if dst == 0xFC6 or src == 0xFC6 else ""
                    print(f"    0x{addr:04X}: MOVFF 0x{src:03X}, 0x{dst:03X}{marker}")
                    addr += 4
                    continue

            if (word & 0xFF00) == 0x0E00:
                print(f"    0x{addr:04X}: MOVLW 0x{word & 0xFF:02X}")
            elif word == 0x0012:
                print(f"    0x{addr:04X}: RETURN")
                break
            else:
                print(f"    0x{addr:04X}: {word:04X}")

            addr += 2


def analyze_channel_loop(memory: Dict[int, int]):
    """Find loops that iterate over 6 channels"""
    print("\n" + "=" * 70)
    print("6-CHANNEL LOOP ANALYSIS")
    print("=" * 70)

    # Look for decrement-and-test patterns
    # Channel loop would look like: counter = 6, loop: ... decfsz counter, goto loop

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # DECFSZ or DCFSNZ followed by BRA back
        if (word & 0xFC00) == 0x4C00:  # DECFSZ
            f = word & 0xFF

            # Check next instruction for BRA backward
            word2 = get_word(memory, addr + 2)
            if word2 and (word2 & 0xF800) == 0xD800:  # BRA
                n = word2 & 0x07FF
                if n & 0x0400:  # Negative (backward)
                    target = addr + 2 + 2 + ((n - 0x0800) * 2)
                    if target < addr:  # Backward branch = loop
                        print(
                            f"  Loop at 0x{addr:04X}: DECFSZ 0x{f:02X}, BRA 0x{target:04X}"
                        )

    # Also look for MOVLW 6 followed by loop setup
    print("\n  MOVLW 6 followed by loop patterns:")
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if (word & 0xFF00) == 0x0E00 and (word & 0xFF) == 6:
            print(f"    0x{addr:04X}: MOVLW 6")

            # Look ahead for MOVWF to a counter variable
            for offset in range(2, 10, 2):
                word2 = get_word(memory, addr + offset)
                if word2 and (word2 & 0xFE00) == 0x6E00:
                    f = word2 & 0xFF
                    print(
                        f"    0x{addr + offset:04X}: MOVWF 0x{f:02X}  ; Loop counter = 6"
                    )
                    break
            break


def find_coefficient_format(memory: Dict[int, int]):
    """Try to determine the coefficient data format"""
    print("\n" + "=" * 70)
    print("COEFFICIENT FORMAT ANALYSIS")
    print("=" * 70)

    # IIR biquad coefficients: b0, b1, b2, a1, a2 (5 per filter)
    # Typically 24-bit or 32-bit fixed point

    # Look at how many bytes are transferred per coefficient
    # Find SPI write sequences

    print("""
  Common DSP Coefficient Formats:
  - IIR Biquad: 5 coefficients (b0, b1, b2, a1, a2)
  - FIR: N coefficients
  - Typically 24-bit or 32-bit fixed point (Q1.23 or Q1.31)
  
  Looking for coefficient transfer patterns...
""")

    # Find TBLRD sequences (reading from program memory)
    print("\n  TBLRD sequences (reading coefficient data):")

    tblrd_seqs = []
    addr = 0x1000
    while addr < 0x6000:
        word = get_word(memory, addr)
        if word in [0x0008, 0x0009, 0x000A, 0x000B]:
            # Found TBLRD
            seq_start = addr
            seq_count = 0

            while addr < 0x6000:
                w = get_word(memory, addr)
                if w in [0x0008, 0x0009, 0x000A, 0x000B]:
                    seq_count += 1
                    addr += 2
                else:
                    break

            if seq_count >= 2:
                tblrd_seqs.append((seq_start, seq_count))
        addr += 2

    for start, count in tblrd_seqs[:10]:
        print(f"    0x{start:04X}: {count} consecutive TBLRD operations")


def analyze_command_0x0a_0x0d(memory: Dict[int, int]):
    """Analyze filter coefficient upload/download commands"""
    print("\n" + "=" * 70)
    print("FILTER COEFFICIENT COMMAND ANALYSIS (0x0A, 0x0D)")
    print("=" * 70)

    # Disassemble around command 0x0A handler
    print("\n  Command 0x0A (Filter Coefficient Upload) handler:")

    # Find the XORLW 0x0A
    for addr in range(0x1000, 0x2000, 2):
        word = get_word(memory, addr)
        if (word & 0xFF00) == 0x0A00 and (word & 0xFF) == 0x0A:
            print(f"    Command comparison at 0x{addr:04X}")

            # Trace to the handler
            for offset in range(2, 20, 2):
                w = get_word(memory, addr + offset)
                if (w & 0xFF00) == 0xEC00:  # CALL
                    word2 = get_word(memory, addr + offset + 2)
                    if word2:
                        target = (((word2 & 0x0FFF) << 8) | (w & 0xFF)) * 2
                        print(f"    Handler at 0x{target:04X}")

                        # Disassemble handler
                        print("\n    Handler disassembly:")
                        haddr = target
                        for _ in range(40):
                            hw = get_word(memory, haddr)
                            if hw is None:
                                break

                            if (hw & 0xC000) == 0xC000:
                                hw2 = get_word(memory, haddr + 2)
                                if hw2:
                                    src = hw & 0x0FFF
                                    dst = hw2 & 0x0FFF
                                    print(
                                        f"      0x{haddr:04X}: MOVFF 0x{src:03X}, 0x{dst:03X}"
                                    )
                                    haddr += 4
                                    continue

                            if (hw & 0xFF00) == 0x0E00:
                                print(f"      0x{haddr:04X}: MOVLW 0x{hw & 0xFF:02X}")
                            elif (hw & 0xF800) == 0xD000:
                                print(f"      0x{haddr:04X}: RCALL ...")
                            elif hw == 0x0012:
                                print(f"      0x{haddr:04X}: RETURN")
                                break
                            elif hw in [0x0008, 0x0009]:
                                print(f"      0x{haddr:04X}: TBLRD")
                            else:
                                print(f"      0x{haddr:04X}: {hw:04X}")

                            haddr += 2
                        break
            break


def find_dsp_chip_type(memory: Dict[int, int]):
    """Try to identify the external DSP chip"""
    print("\n" + "=" * 70)
    print("EXTERNAL DSP IDENTIFICATION")
    print("=" * 70)

    # Look for initialization sequences that might identify the DSP
    # Common DSPs: SHARC, ADAU1701, TAS3108, etc.

    print("""
  Common DSP chips used in audio crossovers:
  - Analog Devices SHARC (ADSP-21xxx)
  - Analog Devices ADAU1701/1401 (SigmaDSP)
  - Texas Instruments TAS3108
  - Cirrus Logic CS4952xx
  
  The SPI/I2C communication pattern may reveal the DSP type.
""")

    # Check for I2C vs SPI mode in SSPCON1
    # SSPCON1 bits 3-0 = SSPM: mode selection
    # 0000 = SPI Master, Fosc/4
    # 0001 = SPI Master, Fosc/16
    # 0010 = SPI Master, Fosc/64
    # 0011 = SPI Master, TMR2/2
    # 0110 = I2C Slave, 7-bit
    # 0111 = I2C Slave, 10-bit
    # 1000 = I2C Master

    print("  Looking for SSPCON1 initialization...")
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if (word & 0xFE00) == 0x6E00:  # MOVWF
            f = word & 0xFF
            if f == 0xC7:  # SSPCON1 low byte
                # Look for MOVLW before
                word2 = get_word(memory, addr - 2)
                if word2 and (word2 & 0xFF00) == 0x0E00:
                    val = word2 & 0xFF
                    mode = val & 0x0F
                    modes = {
                        0: "SPI Master Fosc/4",
                        1: "SPI Master Fosc/16",
                        2: "SPI Master Fosc/64",
                        6: "I2C Slave 7-bit",
                        7: "I2C Slave 10-bit",
                        8: "I2C Master",
                    }
                    print(f"    SSPCON1 = 0x{val:02X} at 0x{addr - 2:04X}")
                    print(f"    Mode: {modes.get(mode, 'Unknown')}")
                    print(f"    CKP = {(val >> 4) & 1}, SSPEN = {(val >> 5) & 1}")


def main():
    hex_file = str(Path(__file__).resolve().parents[3] / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex")
    memory = parse_intel_hex(hex_file)

    print("=" * 70)
    print("DLCP DSP COMMUNICATION DEEP DIVE")
    print("=" * 70)

    sspbuf_writes, sspbuf_reads = analyze_spi_communication(memory)
    trace_spi_functions(memory, sspbuf_writes, sspbuf_reads)
    analyze_channel_loop(memory)
    find_coefficient_format(memory)
    analyze_command_0x0a_0x0d(memory)
    find_dsp_chip_type(memory)


if __name__ == "__main__":
    main()
