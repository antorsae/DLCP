#!/usr/bin/env python3
"""
Ultra Deep Analysis - Map commands to functions, understand the complete protocol
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


def decode_hid_report_desc(data: bytes):
    """Fully decode HID report descriptor"""
    print("\n" + "=" * 70)
    print("HID REPORT DESCRIPTOR - FULL DECODE")
    print("=" * 70)

    items = []
    i = 0
    while i < len(data):
        byte = data[i]
        prefix = byte & 0xFC
        size = byte & 0x03
        if size == 3:
            size = 4

        if prefix == 0:
            # Main item
            main_types = {
                0xA0: "Collection",
                0xA1: "Collection",
                0xB0: "Feature",
                0xB1: "Feature",
                0x80: "Input",
                0x81: "Input",
                0x90: "Output",
                0x91: "Output",
                0xC0: "End Collection",
            }
            name = main_types.get(byte, f"Main_{byte:02X}")
        elif prefix == 0x04:
            # Global item
            global_types = {
                0x04: "Usage Page",
                0x14: "Logical Min",
                0x24: "Logical Max",
                0x34: "Physical Min",
                0x44: "Physical Max",
                0x54: "Unit Exponent",
                0x64: "Unit",
                0x74: "Report Size",
                0x84: "Report ID",
                0x94: "Report Count",
            }
            name = global_types.get(prefix, f"Global_{prefix:02X}")
        elif prefix == 0x08:
            # Local item
            local_types = {
                0x08: "Usage",
                0x10: "Usage Min",
                0x18: "Usage Max",
                0x20: "Designator Index",
                0x28: "Designator Min",
                0x30: "Designator Max",
                0x38: "String Index",
                0x40: "String Min",
                0x48: "String Max",
                0x50: "Delimiter",
            }
            name = local_types.get(prefix, f"Local_{prefix:02X}")
        else:
            name = f"Item_{byte:02X}"

        value = int.from_bytes(data[i + 1 : i + 1 + size], "little") if size > 0 else 0

        items.append((i, name, value, size))
        i += 1 + size

        if name == "End Collection" and i > 20:
            break

    # Print formatted
    for offset, name, value, size in items:
        val_str = f"0x{value:X}" if value < 256 else f"0x{value:04X}"

        extra = ""
        if name == "Usage Page":
            pages = {
                0x01: "Generic Desktop",
                0x0C: "Consumer",
                0xFF00: "Vendor Defined",
            }
            extra = f" ({pages.get(value, 'Unknown')})"
        elif name == "Collection":
            types = {
                0: "Physical",
                1: "Application",
                2: "Logical",
                3: "Report",
                4: "Named Array",
            }
            extra = f" ({types.get(value, 'Type ' + str(value))})"
        elif name in ["Input", "Output", "Feature"]:
            flags = []
            if value & 1:
                flags.append("Constant")
            else:
                flags.append("Data")
            if value & 2:
                flags.append("Variable")
            else:
                flags.append("Array")
            if value & 4:
                flags.append("Relative")
            else:
                flags.append("Absolute")
            if value & 8:
                flags.append("Wrap")
            if value & 16:
                flags.append("NonLinear")
            if value & 32:
                flags.append("NoPreferred")
            if value & 64:
                flags.append("NullState")
            if value & 128:
                flags.append("Volatile")
            extra = f" ({', '.join(flags)})"

        print(f"  0x{offset:02X}: {name:15s} = {val_str:8s}{extra}")

    return items


def find_all_command_handlers(memory: Dict[int, int]):
    """Map command bytes to their handler functions"""
    print("\n" + "=" * 70)
    print("COMMAND HANDLER MAPPING")
    print("=" * 70)

    # Find all XORLW followed by BNZ patterns
    commands = defaultdict(list)

    addr = 0x1000
    while addr < 0x6000:
        word = get_word(memory, addr)
        if word is None:
            addr += 2
            continue

        # XORLW
        if (word & 0xFF00) == 0x0A00:
            cmd_byte = word & 0xFF

            # Look at next several instructions for the handler
            scan_addr = addr + 2
            for _ in range(10):
                word2 = get_word(memory, scan_addr)
                if word2 is None:
                    break

                # BNZ means "branch if not equal" - skip to next comparison
                if (word2 & 0xFF00) == 0xE100:  # BNZ
                    n = word2 & 0xFF
                    if n & 0x80:
                        n = n - 0x100
                    # The handler is at the instruction after BNZ if command matches
                    handler_addr = scan_addr + 2
                    commands[cmd_byte].append(("match", addr, handler_addr))
                    break

                # BZ means "branch if equal" - handler is the branch target
                if (word2 & 0xFF00) == 0xE000:  # BZ
                    n = word2 & 0xFF
                    if n & 0x80:
                        n = n - 0x100
                    handler_addr = scan_addr + 4 + n * 2
                    commands[cmd_byte].append(("branch", addr, handler_addr))
                    break

                # BRA or GOTO after XORLW + BNZ sequence might be handler
                if (word2 & 0xF800) == 0xD800:  # BRA
                    n = word2 & 0x07FF
                    if n & 0x0400:
                        n = n - 0x0800
                    target = scan_addr + 2 + n * 2
                    commands[cmd_byte].append(("bra", scan_addr, target))

                scan_addr += 2

        addr += 2

    # Print command summary
    print("\n  Unique command bytes found:", len(commands))
    print("\n  Command byte -> Handler locations:")

    for cmd in sorted(commands.keys()):
        handlers = commands[cmd]
        print(f"\n    0x{cmd:02X}:")
        for htype, cmp_addr, handler_addr in handlers[:5]:
            print(
                f"      {htype}: compared at 0x{cmp_addr:04X}, handler near 0x{handler_addr:04X}"
            )


def disasm_block(memory: Dict[int, int], start: int, count: int = 20):
    """Disassemble a block of instructions"""
    result = []
    addr = start

    for _ in range(count):
        word = get_word(memory, addr)
        if word is None:
            break

        # Quick decode
        if (word & 0xFF00) == 0xEF00:
            word2 = get_word(memory, addr + 2)
            if word2:
                target = (((word2 & 0x0FFF) << 8) | (word & 0xFF)) * 2
                result.append(f"0x{addr:04X}: GOTO 0x{target:04X}")
                addr += 4
                continue

        if (word & 0xFF00) == 0xEC00:
            word2 = get_word(memory, addr + 2)
            if word2:
                target = (((word2 & 0x0FFF) << 8) | (word & 0xFF)) * 2
                result.append(f"0x{addr:04X}: CALL 0x{target:04X}")
                addr += 4
                continue

        if (word & 0xC000) == 0xC000:
            word2 = get_word(memory, addr + 2)
            if word2:
                fs = word1 & 0x0FFF
                fd = word2 & 0x0FFF
                result.append(f"0x{addr:04X}: MOVFF 0x{fs:03X}, 0x{fd:03X}")
                addr += 4
                continue

        if (word & 0xFF00) == 0x0E00:
            result.append(f"0x{addr:04X}: MOVLW 0x{word & 0xFF:02X}")
        elif (word & 0xFF00) == 0x0A00:
            result.append(f"0x{addr:04X}: XORLW 0x{word & 0xFF:02X}")
        elif (word & 0xFF00) == 0xE100:
            result.append(f"0x{addr:04X}: BNZ ...")
        elif (word & 0xFF00) == 0xE000:
            result.append(f"0x{addr:04X}: BZ ...")
        elif word == 0x0012:
            result.append(f"0x{addr:04X}: RETURN")
            break
        elif word == 0x0010:
            result.append(f"0x{addr:04X}: RETFIE")
            break
        else:
            result.append(f"0x{addr:04X}: {word:04X}")

        addr += 2

    return result


def analyze_usb_state_machine(memory: Dict[int, int]):
    """Analyze USB state handling"""
    print("\n" + "=" * 70)
    print("USB STATE MACHINE ANALYSIS")
    print("=" * 70)

    # Look for UIR (USB Interrupt Register) bit tests
    # UIR bits: ACTVIF, UERRIF, TRNIF, IDLEIF, STALLIF, URSTIF, SOFIF

    uir_bits = {
        0: "ACTVIF (Activity)",
        1: "UERRIF (USB Error)",
        2: "TRNIF (Transaction)",
        3: "IDLEIF (Idle)",
        4: "STALLIF (Stall)",
        5: "URSTIF (USB Reset)",
        6: "SOFIF (Start of Frame)",
    }

    # Look for BTFSS/BTFSC on UIR register (0xF64)
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # BTFSS or BTFSC
        if (word & 0xFC00) in [0xA000, 0xB000]:
            file_reg = word & 0xFF
            bit = (word >> 9) & 0x07

            if file_reg == 0x64:  # UIR is at 0xF64, but in access bank it's just offset
                mn = "BTFSS" if (word & 0xFC00) == 0xA000 else "BTFSC"
                bit_name = uir_bits.get(bit, f"Bit {bit}")
                print(f"  0x{addr:04X}: {mn} UIR, {bit_name}")


def find_data_tables(memory: Dict[int, int]):
    """Find embedded data tables"""
    print("\n" + "=" * 70)
    print("EMBEDDED DATA TABLES")
    print("=" * 70)

    # Look for regions with consistent patterns
    # Data tables often have: length byte, type byte, data...

    tables_found = []

    addr = 0x1000
    while addr < 0x6000:
        # Check for potential descriptor or table
        b0 = memory.get(addr, 0xFF)
        b1 = memory.get(addr + 1, 0xFF)

        # USB descriptor patterns
        if b0 in [0x09, 0x12, 0x07] and b1 in [
            0x01,
            0x02,
            0x03,
            0x04,
            0x05,
            0x21,
            0x22,
        ]:
            # Likely a USB descriptor
            if b0 == 0x09 and b1 == 0x02:  # Configuration descriptor
                total_len = memory.get(addr + 2, 0) | (memory.get(addr + 3, 0) << 8)
                tables_found.append(("Config Desc", addr, total_len))
            elif b0 == 0x09 and b1 == 0x04:  # Interface descriptor
                tables_found.append(("Interface Desc", addr, 9))
            elif b0 == 0x09 and b1 == 0x21:  # HID descriptor
                tables_found.append(("HID Desc", addr, 9))
            elif b0 == 0x07 and b1 == 0x05:  # Endpoint descriptor
                tables_found.append(("Endpoint Desc", addr, 7))

        addr += 1

    print("\n  USB Descriptors found:")
    for name, addr, size in tables_found:
        data = get_bytes(memory, addr, size)
        print(f"    {name} at 0x{addr:04X} ({size} bytes)")
        print(f"      {data.hex()}")


def analyze_main_loop_structure(memory: Dict[int, int]):
    """Understand the main loop structure"""
    print("\n" + "=" * 70)
    print("MAIN LOOP STRUCTURE")
    print("=" * 70)

    # Main function starts at 0x3D4E
    # Trace to find the main loop

    print("\n  Main entry at 0x3D4E")
    print("\n  Tracing main function flow...")

    visited = set()
    branches = []

    def trace(addr, depth=0):
        if depth > 5 or addr in visited:
            return
        visited.add(addr)

        for _ in range(50):
            word = get_word(memory, addr)
            if word is None:
                return

            if (word & 0xFF00) == 0xEF00:  # GOTO
                word2 = get_word(memory, addr + 2)
                if word2:
                    target = (((word2 & 0x0FFF) << 8) | (word & 0xFF)) * 2
                    print(f"    {'  ' * depth}0x{addr:04X}: GOTO 0x{target:04X}")
                    trace(target, depth + 1)
                return

            elif (word & 0xFF00) == 0xEC00:  # CALL
                word2 = get_word(memory, addr + 2)
                if word2:
                    target = (((word2 & 0x0FFF) << 8) | (word & 0xFF)) * 2
                    print(f"    {'  ' * depth}0x{addr:04X}: CALL 0x{target:04X}")
                addr += 4

            elif (word & 0xF800) == 0xD800:  # BRA
                n = word & 0x07FF
                if n & 0x0400:
                    n = n - 0x0800
                target = addr + 2 + n * 2
                print(f"    {'  ' * depth}0x{addr:04X}: BRA 0x{target:04X}")
                branches.append((addr, target))
                addr = target

            elif word == 0x0012:  # RETURN
                print(f"    {'  ' * depth}0x{addr:04X}: RETURN")
                return

            else:
                addr += 2

    trace(0x3D4E)

    # Find backward branches (loops)
    print("\n  Potential loops (backward branches):")
    for src, dst in branches:
        if dst < src:
            print(f"    0x{src:04X} -> 0x{dst:04X} (loop back)")


def summarize_firmware(memory: Dict[int, int]):
    """Create a high-level summary"""
    print("\n" + "=" * 70)
    print("FIRMWARE FUNCTIONALITY SUMMARY")
    print("=" * 70)

    print("""
  DEVICE TYPE: Digital Crossover / DSP Controller
  
  USB INTERFACE:
  - HID Class device (no custom drivers needed)
  - 64-byte bidirectional reports
  - Vendor-defined usage page (0xFF00)
  
  PROTOCOL:
  - Command/response protocol over HID
  - Commands identified: 0x01-0x4C
  - Multiple command handler clusters suggest:
    * Configuration commands
    * Filter coefficient upload/download
    * DSP parameter control
    * Status query commands
  
  EEPROM STORAGE:
  - Stores device configuration
  - Version info: 2.30
  - Checksum at offset 0xFF
  
  DSP/FILTER HANDLING:
  - Table read operations (TBLRD) for coefficient access
  - LFSR pointers to data structures
  - Multiple filter channels supported (indices 0x61-0x65)
  
  MEMORY USAGE:
  - Heavy use of banked RAM (banks 0-4, 9, 17-18, 25, 161)
  - Indirect addressing for data structures
  - USB RAM at 0x400-0x4FF for endpoint buffers
  
  COMMAND CATEGORIES (based on dispatch clusters):
  - Cluster at 0x1160: Basic commands (0x01-0x03)
  - Cluster at 0x1554: Filter/config commands (0x01-0x4C)
  - Cluster at 0x3AE4: Special commands (0x0A, 0x0D, 0x3A)
  - Cluster at 0x4470: Additional commands
  
  KEY FUNCTIONS (by call frequency):
  - 0x48C6: Called from main - likely USB task handler
  - Functions in 0x4400-0x4BFF: Main application logic
  - Functions in 0x4800-0x4FFF: USB/DSP routines
""")


def main():
    hex_file = str(Path(__file__).resolve().parents[3] / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex")
    memory = parse_intel_hex(hex_file)

    print("=" * 70)
    print("HYPEX DLCP FIRMWARE V2.3 - ULTRA DEEP ANALYSIS")
    print("=" * 70)

    # Decode the HID report descriptor found earlier
    hid_data = get_bytes(memory, 0x104C, 32)
    decode_hid_report_desc(hid_data)

    find_all_command_handlers(memory)
    analyze_usb_state_machine(memory)
    find_data_tables(memory)
    analyze_main_loop_structure(memory)
    summarize_firmware(memory)


if __name__ == "__main__":
    main()
