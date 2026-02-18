#!/usr/bin/env python3
"""
Deeper Analysis - Focus on USB HID protocol, command structure, and DSP operations
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


def get_string(memory: Dict[int, int], addr: int, max_len: int = 64) -> str:
    result = []
    for i in range(max_len):
        b = memory.get(addr + i, 0)
        if b == 0 or b == 0xFF:
            break
        if 0x20 <= b < 0x7F:
            result.append(chr(b))
    return "".join(result)


def dump_region(memory: Dict[int, int], addr: int, count: int, label: str = ""):
    print(f"\n{label} (0x{addr:04X}):")
    data = get_bytes(memory, addr, count)

    for i in range(0, len(data), 16):
        hex_str = " ".join(f"{b:02X}" for b in data[i : i + 16])
        ascii_str = "".join(
            chr(b) if 0x20 <= b < 0x7F else "." for b in data[i : i + 16]
        )
        print(f"  {addr + i:04X}: {hex_str:48s}  {ascii_str}")


def find_usb_buffers(memory: Dict[int, int]):
    """Find USB endpoint buffer structures in RAM"""
    print("\n" + "=" * 70)
    print("USB ENDPOINT BUFFER ANALYSIS")
    print("=" * 70)

    # PIC18F2550 USB buffer is at 0x400-0x4FF in USB RAM
    # Look for initialization of buffer descriptors

    # BD (Buffer Descriptor) registers are at 0x200-0x2FF in Access Bank
    print("\n  USB Buffer Descriptors are typically at 0x200-0x2FF")
    print("  USB RAM is at 0x400-0x4FF")

    # Look for MOVFF instructions that write to USB buffer area
    print("\n  Looking for USB buffer initialization...")

    # Check for patterns that suggest USB buffer setup
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # Look for LFSR instructions setting up buffer pointers
        if (word & 0xFF00) == 0xEE00:
            word2 = get_word(memory, addr + 2)
            if word2:
                fsr = (word >> 4) & 0x03
                value = word2 & 0x0FFF
                if 0x200 <= value <= 0x500:
                    print(
                        f"    0x{addr:04X}: LFSR {fsr}, 0x{value:03X}  ; USB buffer setup?"
                    )


def analyze_hid_report_desc(memory: Dict[int, int]):
    """Decode the HID report descriptor"""
    print("\n" + "=" * 70)
    print("HID REPORT DESCRIPTOR DECODING")
    print("=" * 70)

    # The HID descriptor said report desc is 29 bytes
    # Need to find where it is

    # HID descriptor at 0x102C said Report Descriptor length = 0x001D (29 bytes)
    # But the actual descriptor is probably stored elsewhere

    # Search for valid HID report descriptor start
    # 0x06 = Usage Page (Global)
    # 0x09 = Usage (Local)
    # 0xA1 = Collection (Main)

    for addr in range(0x1000, 0x6000):
        data = get_bytes(memory, addr, 32)

        # Check for valid HID descriptor patterns
        if len(data) >= 8:
            # Typical start: Usage Page, Usage, Collection
            if data[0] in [0x05, 0x06] and data[2] == 0x09 and data[4] == 0xA1:
                print(f"\n  Found potential HID report descriptor at 0x{addr:04X}")
                dump_region(memory, addr, 32, "HID Report Descriptor")

                # Try to decode it
                decode_hid_descriptor(data)
                break

    # Also check if it's stored as a lookup table
    print("\n  Checking for HID descriptor in USB configuration area...")

    # The config descriptor area should have pointers
    dump_region(memory, 0x102C, 64, "Configuration + HID Descriptors")


def decode_hid_descriptor(data: bytes):
    """Decode HID report descriptor items"""
    print("\n  Decoding HID items:")

    HID_ITEMS = {
        0x01: ("Usage Page", 1),
        0x02: ("Logical Minimum", 1),
        0x03: ("Logical Maximum", 1),
        0x04: ("Physical Minimum", 1),
        0x05: ("Physical Maximum", 1),
        0x06: ("Usage Page", 2),
        0x07: ("Logical Minimum", 2),
        0x08: ("Logical Maximum", 2),
        0x09: ("Usage", 1),
        0x0A: ("Usage", 2),
        0x0B: ("Unit Exponent", 1),
        0x0C: ("Unit", 1),
        0x0D: ("Unit", 2),
        0x14: ("Unit Exponent", 1),
        0x15: ("Logical Minimum", 1),
        0x16: ("Logical Minimum", 2),
        0x17: ("Logical Minimum", 4),
        0x25: ("Logical Maximum", 1),
        0x26: ("Logical Maximum", 2),
        0x27: ("Logical Maximum", 4),
        0x35: ("Physical Minimum", 1),
        0x36: ("Physical Minimum", 2),
        0x45: ("Physical Maximum", 1),
        0x46: ("Physical Maximum", 2),
        0x55: ("Unit Exponent", 1),
        0x65: ("Unit", 1),
        0x66: ("Unit", 2),
        0x75: ("Report Size", 1),
        0x76: ("Report Size", 2),
        0x85: ("Report ID", 1),
        0x95: ("Report Count", 1),
        0x96: ("Report Count", 2),
        0xA1: ("Collection", 1),
        0xA0: ("Collection", 0),
        0xB1: ("Feature", 1),
        0xB2: ("Feature", 2),
        0x81: ("Input", 1),
        0x82: ("Input", 2),
        0x91: ("Output", 1),
        0x92: ("Output", 2),
        0xC0: ("End Collection", 0),
    }

    USAGE_PAGES = {
        0x01: "Generic Desktop",
        0x0C: "Consumer",
        0xFF00: "Vendor Defined",
        0xFF01: "Vendor 1",
    }

    USAGES_GENERIC = {
        0x01: "Pointer",
        0x02: "Mouse",
        0x04: "Joystick",
        0x05: "Game Pad",
        0x06: "Keyboard",
        0x07: "Keypad",
        0x30: "X",
        0x31: "Y",
        0x32: "Z",
        0x36: "Slider",
        0x37: "Dial",
        0x80: "System Control",
        0x01: "Consumer Control",
    }

    i = 0
    while i < len(data):
        byte = data[i]
        item_type = byte & 0xFC
        size = byte & 0x03
        if size == 3:
            size = 4

        if item_type in HID_ITEMS:
            name, _ = HID_ITEMS[item_type]
            value = (
                int.from_bytes(data[i + 1 : i + 1 + size], "little") if size > 0 else 0
            )

            extra = ""
            if name == "Usage Page" and value in USAGE_PAGES:
                extra = f" ({USAGE_PAGES[value]})"
            elif name == "Usage":
                extra = f" (0x{value:04X})"
            elif name == "Collection":
                coll_types = {
                    0: "Physical",
                    1: "Application",
                    2: "Logical",
                    3: "Report",
                }
                extra = f" ({coll_types.get(value, 'Unknown')})"

            print(f"    {name}: {value} (0x{value:X}){extra}")

        i += 1 + size


def find_command_dispatch(memory: Dict[int, int]):
    """Find the USB command dispatch mechanism"""
    print("\n" + "=" * 70)
    print("USB COMMAND DISPATCH ANALYSIS")
    print("=" * 70)

    # Look for switch/case patterns on the first byte of USB data
    # Typical: XORLW command, BNZ to skip, BRA/CALL to handler

    print("\n  Looking for command byte dispatch patterns...")

    dispatch_found = []
    addr = 0x1000

    while addr < 0x6000:
        word = get_word(memory, addr)
        if word is None:
            addr += 2
            continue

        # XORLW followed by BNZ or BZ
        if (word & 0xFF00) == 0x0A00:  # XORLW
            literal = word & 0xFF

            # Check next instruction
            word2 = get_word(memory, addr + 2)
            if word2:
                if (word2 & 0xFF00) == 0xE100:  # BNZ
                    n = word2 & 0xFF
                    if n & 0x80:
                        n = n - 0x100
                    skip_target = addr + 4 + n * 2
                    dispatch_found.append((addr, literal, skip_target))
                elif (word2 & 0xFF00) == 0xE000:  # BZ
                    n = word2 & 0xFF
                    if n & 0x80:
                        n = n - 0x100
                    skip_target = addr + 4 + n * 2
                    dispatch_found.append((addr, literal, skip_target))

        addr += 2

    # Group by proximity to find dispatch tables
    print(f"\n  Found {len(dispatch_found)} command comparisons")

    # Find clusters
    clusters = []
    current_cluster = []

    for item in dispatch_found:
        if not current_cluster or item[0] - current_cluster[-1][0] < 20:
            current_cluster.append(item)
        else:
            if len(current_cluster) >= 3:
                clusters.append(current_cluster)
            current_cluster = [item]

    if len(current_cluster) >= 3:
        clusters.append(current_cluster)

    print(f"\n  Found {len(clusters)} command dispatch clusters:")

    for i, cluster in enumerate(clusters):
        print(f"\n  Cluster {i + 1} at 0x{cluster[0][0]:04X}:")
        for addr, cmd, skip in cluster[:15]:
            print(f"    Command 0x{cmd:02X}: compared at 0x{addr:04X}")


def analyze_filter_coefficients(memory: Dict[int, int]):
    """Look for DSP filter coefficient storage"""
    print("\n" + "=" * 70)
    print("DSP/FILTER COEFFICIENT ANALYSIS")
    print("=" * 70)

    # DSP coefficients are often stored as tables in program memory
    # Look for TBLRD instructions (table read)

    print("\n  Searching for table read operations (filter coefficients?)...")

    tblrd_locs = []
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word in [0x0008, 0x0009, 0x000A, 0x000B]:  # TBLRD variants
            tblrd_locs.append(addr)

    print(f"  Found {len(tblrd_locs)} TBLRD instructions")

    # Look for LFSR instructions that set up table pointers
    print("\n  LFSR table pointer setup:")
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if (word & 0xFF00) == 0xEE00:
            word2 = get_word(memory, addr + 2)
            if word2:
                fsr = (word >> 4) & 0x03
                value = word2 & 0x0FFF
                print(f"    0x{addr:04X}: LFSR {fsr}, 0x{value:03X}")


def analyze_eeprom_structure(memory: Dict[int, int]):
    """Detailed EEPROM structure analysis"""
    print("\n" + "=" * 70)
    print("EEPROM DATA STRUCTURE ANALYSIS")
    print("=" * 70)

    # Get EEPROM data
    eeprom_data = get_bytes(memory, 0xF00000, 256)

    # Parse known structure
    print("\n  EEPROM Layout:")
    print(
        f"    0x00-0x02: Header = {eeprom_data[0]:02X} {eeprom_data[1]:02X} {eeprom_data[2]:02X}"
    )
    print(f"    0x03-0x04: Config = {eeprom_data[3]:02X} {eeprom_data[4]:02X}")

    # Find non-0xFF regions
    print("\n  Non-empty EEPROM regions:")
    i = 0
    while i < 256:
        if eeprom_data[i] != 0xFF:
            start = i
            while i < 256 and eeprom_data[i] != 0xFF:
                i += 1
            end = i

            print(f"\n    0x{start:02X}-0x{end - 1:02X}:")
            hex_str = " ".join(
                f"{b:02X}" for b in eeprom_data[start : min(end, start + 32)]
            )
            print(f"      {hex_str}")

            # Try to interpret
            if start == 0x80:
                print(
                    f"      Version: {eeprom_data[0x80]}.{eeprom_data[0x81]}{chr(eeprom_data[0x82]) if 0x30 <= eeprom_data[0x82] <= 0x39 else ''}"
                )
        else:
            i += 1


def find_usb_strings(memory: Dict[int, int]):
    """Find USB string descriptors"""
    print("\n" + "=" * 70)
    print("USB STRING DESCRIPTOR ANALYSIS")
    print("=" * 70)

    # String descriptors are Unicode (UTF-16LE)
    # Look for patterns: length byte, type 0x03, then Unicode chars

    for addr in range(0x1000, 0x6000):
        b1 = memory.get(addr, 0)
        b2 = memory.get(addr + 1, 0)

        if b2 == 0x03 and b1 >= 4 and b1 <= 64:  # String descriptor type
            length = b1

            # Try to decode as Unicode
            try:
                data = get_bytes(memory, addr, length)
                # Skip length and type, decode UTF-16LE
                text = data[2:].decode("utf-16le", errors="ignore")
                if text and all(c.isprintable() or c.isspace() for c in text):
                    print(f"\n  String descriptor at 0x{addr:04X}:")
                    print(f"    Length: {length}")
                    print(f'    Text: "{text}"')
                    print(f"    Raw: {data.hex()}")
            except Exception:
                pass


def analyze_ram_layout(memory: Dict[int, int]):
    """Analyze how RAM is organized"""
    print("\n" + "=" * 70)
    print("RAM LAYOUT ANALYSIS")
    print("=" * 70)

    # PIC18F2550 has:
    # - Access Bank: 0x00-0x7F (low) + 0xF80-0xFFF (SFRs)
    # - Banked RAM: 0x80-0xFF in each bank (up to 16 banks)

    # USB RAM: 0x400-0x4FF

    print("""
  PIC18F2550 Memory Layout:
  - Access Bank Low:  0x000-0x07F (GPR, direct access)
  - USB RAM:          0x400-0x4FF (USB endpoint buffers)
  - Banked GPR:       Banks 0-15, 0x080-0x0FF each
  - SFR Area:         0xF80-0xFFF (Access Bank High)
""")

    # Find which banks are used
    bank_access = defaultdict(set)

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # MOVLB sets the bank
        if (word & 0xFF00) == 0x0100:
            bank = word & 0xFF
            bank_access["MOVLB"].add(bank)

        # File register operations with BSR
        if (word & 0x0100) == 0x0100:  # a=1 means BSR
            if (word & 0xFC00) in [0x5000, 0x6E00, 0x6A00, 0x6800, 0x2400, 0x2800]:
                f = word & 0xFF
                bank_access["BSR file"].add(f)

    print(f"  Banks accessed via MOVLB: {sorted(bank_access['MOVLB'])}")
    print(
        f"  File registers via BSR: {[hex(x) for x in sorted(bank_access['BSR file'])]}"
    )


def trace_main_execution(memory: Dict[int, int]):
    """Trace main execution path"""
    print("\n" + "=" * 70)
    print("MAIN EXECUTION TRACE")
    print("=" * 70)

    # Start at 0x3D4E and trace
    visited = set()
    trace = []

    def trace_from(addr, depth=0, max_depth=50):
        if depth > max_depth or addr in visited or addr < 0x1000 or addr > 0x6000:
            return
        visited.add(addr)

        for _ in range(30):
            word = get_word(memory, addr)
            if word is None:
                break

            # Decode instruction
            if (word & 0xFF00) == 0xEF00:  # GOTO
                word2 = get_word(memory, addr + 2)
                if word2:
                    target = (((word2 & 0x0FFF) << 8) | (word & 0xFF)) * 2
                    trace.append((addr, "GOTO", target))
                    trace_from(target, depth + 1)
                return

            elif (word & 0xFF00) == 0xEC00:  # CALL
                word2 = get_word(memory, addr + 2)
                if word2:
                    target = (((word2 & 0x0FFF) << 8) | (word & 0xFF)) * 2
                    trace.append((addr, "CALL", target))
                addr += 4

            elif (word & 0xF800) == 0xD000:  # RCALL
                n = word & 0x07FF
                if n & 0x0400:
                    n = n - 0x0800
                target = addr + 2 + n * 2
                trace.append((addr, "RCALL", target))
                addr += 2

            elif (word & 0xF800) == 0xD800:  # BRA
                n = word & 0x07FF
                if n & 0x0400:
                    n = n - 0x0800
                target = addr + 2 + n * 2
                trace.append((addr, "BRA", target))
                addr = target

            elif word == 0x0012:  # RETURN
                trace.append((addr, "RETURN", None))
                return

            elif word == 0x0010:  # RETFIE
                trace.append((addr, "RETFIE", None))
                return

            else:
                addr += 2

    trace_from(0x3D4E)

    print("\n  Execution flow:")
    for addr, op, target in trace[:30]:
        if target:
            print(f"    0x{addr:04X}: {op} 0x{target:04X}")
        else:
            print(f"    0x{addr:04X}: {op}")


def main():
    hex_file = str(Path(__file__).resolve().parents[3] / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex")
    memory = parse_intel_hex(hex_file)

    print("=" * 70)
    print("HYPEX DLCP FIRMWARE V2.3 - DEEP PROTOCOL ANALYSIS")
    print("=" * 70)

    trace_main_execution(memory)
    analyze_hid_report_desc(memory)
    find_usb_strings(memory)
    find_command_dispatch(memory)
    find_usb_buffers(memory)
    analyze_filter_coefficients(memory)
    analyze_eeprom_structure(memory)
    analyze_ram_layout(memory)


if __name__ == "__main__":
    main()
