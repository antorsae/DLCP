#!/usr/bin/env python3
"""Deep analysis of DLCP Control Unit firmware"""

from pathlib import Path

from dlcp_fw.paths import STOCK_CONTROL_HEX_V14, STOCK_CONTROL_HEX_V15B, STOCK_CONTROL_HEX_V16B


def parse_intel_hex(filepath):
    """Parse Intel HEX file and return memory dict"""
    memory = {}
    extended_addr = 0

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line.startswith(":"):
                continue

            byte_count = int(line[1:3], 16)
            addr = int(line[3:7], 16)
            record_type = int(line[7:9], 16)

            if record_type == 0x00:
                for i in range(byte_count):
                    data = int(line[9 + i * 2 : 11 + i * 2], 16)
                    memory[extended_addr + addr + i] = data
            elif record_type == 0x01:
                break
            elif record_type == 0x04:
                extended_addr = int(line[9:13], 16) << 16

    return memory


def read_word(memory, addr):
    """Read 16-bit word from memory (PIC18 little-endian)"""
    lo = memory.get(addr, 0xFF)
    hi = memory.get(addr + 1, 0xFF)
    return (hi << 8) | lo


def decode_config(config_bytes):
    """Decode PIC18F2550 configuration bytes"""
    configs = {}

    if len(config_bytes) >= 14:
        config1l = config_bytes[0]
        config1h = config_bytes[1]
        config2l = config_bytes[2]
        config2h = config_bytes[3]
        config3h = config_bytes[5]
        config4l = config_bytes[6]

        configs["CONFIG1L"] = {
            "value": config1l,
            "USBDIV": (config1l >> 5) & 0x1,
            "CPUDIV": (config1l >> 3) & 0x3,
            "PLLDIV": config1l & 0x7,
        }

        configs["CONFIG1H"] = {
            "value": config1h,
            "FOSC": config1h & 0x0F,
            "FCMEN": (config1h >> 6) & 0x1,
            "IESO": (config1h >> 7) & 0x1,
        }

        configs["CONFIG2L"] = {
            "value": config2l,
            "VREGEN": (config2l >> 5) & 0x1,
            "BORV": (config2l >> 3) & 0x3,
            "BOR": (config2l >> 1) & 0x3,
            "PWRT": config2l & 0x1,
        }

        configs["CONFIG2H"] = {
            "value": config2h,
            "WDTPS": (config2h >> 1) & 0x0F,
            "WDT": config2h & 0x1,
        }

        configs["CONFIG3H"] = {
            "value": config3h,
            "MCLRE": (config3h >> 7) & 0x1,
            "PBADEN": (config3h >> 1) & 0x1,
            "CCP2MX": config3h & 0x1,
        }

        configs["CONFIG4L"] = {
            "value": config4l,
            "DEBUG": (config4l >> 7) & 0x1,
            "XINST": (config4l >> 6) & 0x1,
            "LVP": (config4l >> 2) & 0x1,
            "STVREN": config4l & 0x1,
        }

    return configs


def find_strings(memory, min_len=4):
    """Find ASCII strings in memory"""
    strings = []
    current = []
    start_addr = 0

    for addr in sorted(memory.keys()):
        if addr > 0x10000:
            continue
        byte = memory[addr]
        if 0x20 <= byte <= 0x7E:
            if not current:
                start_addr = addr
            current.append(chr(byte))
        else:
            if len(current) >= min_len:
                strings.append((start_addr, "".join(current)))
            current = []

    if len(current) >= min_len:
        strings.append((start_addr, "".join(current)))

    return strings


def analyze_code_regions(memory):
    """Analyze code regions in memory"""
    regions = []

    code_addrs = [a for a in sorted(memory.keys()) if a < 0x300000]
    if not code_addrs:
        return regions

    start = code_addrs[0]
    prev = start

    for addr in code_addrs[1:]:
        if addr > prev + 10:
            regions.append((start, prev))
            start = addr
        prev = addr

    regions.append((start, prev))
    return regions


def find_call_targets(memory):
    """Find all call targets in code"""
    targets = set()

    for addr in sorted(memory.keys()):
        if addr > 0x10000 or addr % 2 != 0:
            continue

        word = read_word(memory, addr)

        if (word & 0xF000) == 0xE000:
            op = (word >> 8) & 0x0F
            if op in [0x0C, 0x0D]:
                target_low = word & 0xFF
                word2 = read_word(memory, addr + 2)
                target_high = word2 & 0x0F
                target = (target_high << 8) | target_low
                targets.add(target)

    return sorted(targets)


def find_reset_vector(memory):
    """Find reset vector"""
    word = read_word(memory, 0)
    word2 = read_word(memory, 2)

    if (word & 0xF000) == 0xEF00:
        target = ((word2 & 0x0F) << 8) | ((word >> 8) & 0x0F) | ((word & 0xFF) << 0)
        return target
    return None


def analyze_interrupt_vectors(memory):
    """Analyze interrupt vectors"""
    vectors = {}

    word = read_word(memory, 0x08)
    word2 = read_word(memory, 0x0A)
    if (word & 0xF000) == 0xEF00 or word != 0xFFFF:
        vectors["high_priority"] = 0x08

    word = read_word(memory, 0x18)
    if word != 0xFFFF:
        vectors["low_priority"] = 0x18

    return vectors


def extract_eeprom(memory):
    """Extract EEPROM data"""
    eeprom = {}
    for addr in range(0xF00000, 0xF00100):
        if addr in memory:
            eeprom[addr - 0xF00000] = memory[addr]
    return eeprom


def main():
    versions = [
        ("V1.4 (baseline)", str(STOCK_CONTROL_HEX_V14)),
        (
            "V1.5b (BETA, prevents bootloader)",
            str(STOCK_CONTROL_HEX_V15B),
        ),
        ("V1.6b (BETA, combi display)", str(STOCK_CONTROL_HEX_V16B)),
    ]

    print("=" * 80)
    print("DLCP CONTROL UNIT FIRMWARE ANALYSIS")
    print("=" * 80)

    all_analysis = {}
    config_addr = {
        "CONFIG1L": 0x300000,
        "CONFIG1H": 0x300001,
        "CONFIG2L": 0x300002,
        "CONFIG2H": 0x300003,
        "CONFIG3H": 0x300005,
        "CONFIG4L": 0x300006,
    }

    for name, path in versions:
        print(f"\n{'=' * 80}")
        print(f"VERSION: {name}")
        print(f"File: {path}")
        print("=" * 80)

        memory = parse_intel_hex(path)

        config_bytes = [memory.get(0x300000 + i, 0xFF) for i in range(14)]
        configs = decode_config(config_bytes)

        print("\n--- CONFIGURATION WORDS ---")
        for cfg_name, cfg_data in configs.items():
            val = cfg_data["value"]
            print(f"\n{cfg_name} (0x{config_addr[cfg_name]:06X}): 0x{val:02X}")
            for bit_name, bit_val in cfg_data.items():
                if bit_name != "value":
                    print(f"  {bit_name}: {bit_val}")

        code_regions = analyze_code_regions(memory)
        print(f"\n--- CODE REGIONS ---")
        total_code = 0
        for start, end in code_regions:
            size = end - start + 1
            total_code += size
            print(f"  0x{start:04X} - 0x{end:04X}: {size} bytes")
        print(f"  Total code: {total_code} bytes")

        strings = find_strings(memory)
        print(f"\n--- STRINGS ({len(strings)} found) ---")
        for addr, s in strings[:20]:
            print(
                f'  0x{addr:04X}: "{s[:60]}..."'
                if len(s) > 60
                else f'  0x{addr:04X}: "{s}"'
            )
        if len(strings) > 20:
            print(f"  ... and {len(strings) - 20} more")

        reset = find_reset_vector(memory)
        print(f"\n--- RESET VECTOR ---")
        if reset:
            print(f"  Reset jumps to: 0x{reset:04X}")

        int_vecs = analyze_interrupt_vectors(memory)
        print(f"\n--- INTERRUPT VECTORS ---")
        for vec_name, vec_addr in int_vecs.items():
            print(f"  {vec_name}: 0x{vec_addr:04X}")

        targets = find_call_targets(memory)
        print(f"\n--- CALL TARGETS ({len(targets)} unique) ---")
        print(f"  First 20: {[hex(t) for t in targets[:20]]}")

        eeprom = extract_eeprom(memory)
        print(f"\n--- EEPROM ({len(eeprom)} bytes) ---")
        if eeprom:
            non_ff = [(a, v) for a, v in eeprom.items() if v != 0xFF]
            print(f"  Non-0xFF bytes: {len(non_ff)}")
            for addr, val in non_ff[:10]:
                print(f"  0x{addr:02X}: 0x{val:02X}")

        all_analysis[name] = {
            "memory": memory,
            "configs": configs,
            "strings": strings,
            "code_regions": code_regions,
            "call_targets": targets,
            "reset": reset,
            "eeprom": eeprom,
        }

    print("\n" + "=" * 80)
    print("VERSION COMPARISON")
    print("=" * 80)

    v14 = all_analysis[versions[0][0]]
    v15b = all_analysis[versions[1][0]]
    v16b = all_analysis[versions[2][0]]

    print("\n--- STRING DIFFERENCES ---")
    v14_strs = set(s for _, s in v14["strings"])
    v15b_strs = set(s for _, s in v15b["strings"])
    v16b_strs = set(s for _, s in v16b["strings"])

    if v14_strs != v15b_strs:
        print(f"\nV1.4 vs V1.5b:")
        print(f"  Only in V1.4: {v14_strs - v15b_strs}")
        print(f"  Only in V1.5b: {v15b_strs - v14_strs}")

    if v14_strs != v16b_strs:
        print(f"\nV1.4 vs V1.6b:")
        print(f"  Only in V1.4: {v14_strs - v16b_strs}")
        print(f"  Only in V1.6b: {v16b_strs - v14_strs}")

    print("\n--- CONFIG DIFFERENCES ---")
    for cfg_name in v14["configs"]:
        if v14["configs"][cfg_name] != v15b["configs"][cfg_name]:
            print(f"\n{cfg_name}:")
            print(f"  V1.4:   0x{v14['configs'][cfg_name]['value']:02X}")
            print(f"  V1.5b: 0x{v15b['configs'][cfg_name]['value']:02X}")
            print(f"  V1.6b: 0x{v16b['configs'][cfg_name]['value']:02X}")


if __name__ == "__main__":
    main()
