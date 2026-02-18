#!/usr/bin/env python3
"""Analyze DLCP Control Firmware hex files."""

from pathlib import Path

from dlcp_fw.paths import STOCK_CONTROL_HEX_V14, STOCK_CONTROL_HEX_V15B, STOCK_CONTROL_HEX_V16B

def parse_intel_hex(filename):
    """Parse Intel HEX file and return binary data with address map."""
    data = {}
    ext_addr = 0
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if not line.startswith(':'):
                continue
            byte_count = int(line[1:3], 16)
            address = int(line[3:7], 16)
            record_type = int(line[7:9], 16)
            if record_type == 0x00:  # Data record
                full_addr = ext_addr + address
                for i in range(byte_count):
                    b = int(line[9 + i*2:11 + i*2], 16)
                    data[full_addr + i] = b
            elif record_type == 0x04:  # Extended linear address
                ext_addr = int(line[9:13], 16) << 16
            elif record_type == 0x01:  # EOF
                break
    return data

def extract_strings(data, min_len=4):
    """Extract printable ASCII strings from binary data."""
    strings = []
    addrs = sorted(data.keys())
    current = []
    start_addr = None
    for addr in addrs:
        b = data[addr]
        if 0x20 <= b <= 0x7E:
            if not current:
                start_addr = addr
            current.append(chr(b))
        else:
            if len(current) >= min_len:
                strings.append((start_addr, ''.join(current)))
            current = []
            start_addr = None
    if len(current) >= min_len:
        strings.append((start_addr, ''.join(current)))
    return strings

def analyze_regions(data):
    """Analyze memory regions to determine MCU type."""
    if not data:
        return
    addrs = sorted(data.keys())
    regions = []
    start = addrs[0]
    prev = addrs[0]
    for addr in addrs[1:]:
        if addr > prev + 16:  # Gap
            regions.append((start, prev))
            start = addr
        prev = addr
    regions.append((start, prev))
    return regions

def find_patterns(data):
    """Find interesting byte patterns - UART config, SFR writes, etc."""
    addrs = sorted(data.keys())
    findings = []

    # Look for PIC18F instruction patterns
    # MOVLW + MOVWF to SFR addresses (SPBRG, RCSTA, TXSTA, etc.)
    for i in range(len(addrs) - 3):
        a = addrs[i]
        # Check for consecutive addresses (instruction words)
        if a + 1 in data and a + 2 in data and a + 3 in data:
            w0 = data[a] | (data[a+1] << 8)
            w1 = data[a+2] | (data[a+3] << 8)
            # MOVLW = 0x0Exx, MOVWF = 0x6Exx
            if (w0 >> 8) == 0x0E and (w1 >> 8) == 0x6E:
                value = w0 & 0xFF
                dest = w1 & 0xFF
                # Map SFR addresses (PIC18 access bank SFR mapping)
                sfr_names = {
                    0xAB: 'RCSTA', 0xAC: 'TXSTA', 0xAF: 'SPBRG',
                    0xB0: 'SPBRGH', 0xB8: 'BAUDCON',
                    0xC6: 'SSPCON1', 0xC7: 'SSPCON2', 0xC8: 'SSPADD',
                    0xC9: 'SSPSTAT', 0xD5: 'T0CON', 0xD3: 'OSCCON',
                    0x92: 'TRISA', 0x93: 'TRISB', 0x94: 'TRISC',
                    0x80: 'PORTA', 0x81: 'PORTB', 0x82: 'PORTC',
                    0x89: 'LATA', 0x8A: 'LATB', 0x8B: 'LATC',
                }
                if dest in sfr_names:
                    findings.append((a, f"MOVLW 0x{value:02X} → MOVWF {sfr_names[dest]} (0x{dest:02X})"))
    return findings

def diff_hex_files(data1, data2, name1, name2):
    """Compare two firmware versions."""
    all_addrs = sorted(set(list(data1.keys()) + list(data2.keys())))
    diffs = []
    for addr in all_addrs:
        v1 = data1.get(addr)
        v2 = data2.get(addr)
        if v1 != v2:
            diffs.append((addr, v1, v2))
    return diffs

def main():
    files = {
        'V1.4': str(STOCK_CONTROL_HEX_V14),
        'V1.5b': str(STOCK_CONTROL_HEX_V15B),
        'V1.6b': str(STOCK_CONTROL_HEX_V16B),
    }

    firmwares = {}
    for name, path in files.items():
        if Path(path).exists():
            firmwares[name] = parse_intel_hex(path)
            print(f"=== {name}: Loaded {len(firmwares[name])} bytes ===")
        else:
            print(f"WARNING: {path} not found")

    for name, data in firmwares.items():
        print(f"\n{'='*60}")
        print(f"  FIRMWARE {name}")
        print(f"{'='*60}")

        # Memory regions
        regions = analyze_regions(data)
        print(f"\nMemory Regions ({len(regions)}):")
        total_code = 0
        for start, end in regions:
            size = end - start + 1
            total_code += size
            region_type = "CODE"
            if start >= 0x300000:
                region_type = "CONFIG"
            elif start >= 0xF00000:
                region_type = "EEPROM"
            print(f"  0x{start:06X} - 0x{end:06X}  ({size:5d} bytes) [{region_type}]")
        print(f"  Total: {total_code} bytes")

        # Check for PIC18 vs PIC16 indicators
        # PIC18 reset vector at 0x0000 is typically GOTO (0xEFxx 0xFxxx)
        if 0x0000 in data and 0x0001 in data:
            w = data[0] | (data[1] << 8)
            print(f"\n  Reset vector word: 0x{w:04X}")
            if (w & 0xFF00) == 0xEF00:
                dest_lo = w & 0xFF
                if 0x0002 in data and 0x0003 in data:
                    w2 = data[2] | (data[3] << 8)
                    dest = (dest_lo | ((w2 & 0x0FFF) << 8)) * 2
                    print(f"  PIC18 GOTO 0x{dest:06X}")

        # Config bits
        config_addrs = [a for a in sorted(data.keys()) if 0x300000 <= a <= 0x30000F]
        if config_addrs:
            print(f"\n  Configuration Bits:")
            for a in config_addrs:
                config_names = {
                    0x300000: 'CONFIG1L', 0x300001: 'CONFIG1H',
                    0x300002: 'CONFIG2L', 0x300003: 'CONFIG2H',
                    0x300004: 'CONFIG3L', 0x300005: 'CONFIG3H',
                    0x300006: 'CONFIG4L', 0x300007: 'CONFIG4H',
                    0x300008: 'CONFIG5L', 0x300009: 'CONFIG5H',
                    0x30000A: 'CONFIG6L', 0x30000B: 'CONFIG6H',
                    0x30000C: 'CONFIG7L', 0x30000D: 'CONFIG7H',
                }
                cname = config_names.get(a, f'CONFIG_{a & 0xFF:02X}')
                print(f"    {cname} (0x{a:06X}) = 0x{data[a]:02X}")

        # EEPROM
        eeprom_addrs = [a for a in sorted(data.keys()) if 0xF00000 <= a <= 0xF000FF]
        if eeprom_addrs:
            print(f"\n  EEPROM Data ({len(eeprom_addrs)} bytes):")
            line = "    "
            for i, a in enumerate(eeprom_addrs):
                line += f"{data[a]:02X} "
                if (i + 1) % 16 == 0:
                    print(line)
                    line = "    "
            if len(line.strip()) > 0:
                print(line)

        # Strings
        strings = extract_strings(data, min_len=3)
        if strings:
            print(f"\n  Strings Found ({len(strings)}):")
            for addr, s in strings:
                print(f"    0x{addr:06X}: \"{s}\"")

        # SFR patterns
        findings = find_patterns(data)
        if findings:
            print(f"\n  SFR Configuration ({len(findings)} MOVLW+MOVWF pairs):")
            for addr, desc in findings:
                print(f"    0x{addr:06X}: {desc}")

    # Diff versions
    if 'V1.4' in firmwares and 'V1.5b' in firmwares:
        diffs = diff_hex_files(firmwares['V1.4'], firmwares['V1.5b'], 'V1.4', 'V1.5b')
        print(f"\n{'='*60}")
        print(f"  DIFF: V1.4 vs V1.5b ({len(diffs)} byte differences)")
        print(f"{'='*60}")
        # Group diffs into regions
        if diffs:
            regions = []
            start = diffs[0][0]
            prev = diffs[0][0]
            count = 1
            for addr, v1, v2 in diffs[1:]:
                if addr > prev + 4:
                    regions.append((start, prev, count))
                    start = addr
                    count = 0
                prev = addr
                count += 1
            regions.append((start, prev, count))
            print(f"  Changed regions: {len(regions)}")
            for start, end, cnt in regions[:30]:
                size = end - start + 1
                region_type = "CODE" if start < 0x300000 else ("CONFIG" if start < 0xF00000 else "EEPROM")
                print(f"    0x{start:06X}-0x{end:06X} ({size} bytes) [{region_type}]")

    if 'V1.5b' in firmwares and 'V1.6b' in firmwares:
        diffs = diff_hex_files(firmwares['V1.5b'], firmwares['V1.6b'], 'V1.5b', 'V1.6b')
        print(f"\n{'='*60}")
        print(f"  DIFF: V1.5b vs V1.6b ({len(diffs)} byte differences)")
        print(f"{'='*60}")
        if diffs:
            regions = []
            start = diffs[0][0]
            prev = diffs[0][0]
            count = 1
            for addr, v1, v2 in diffs[1:]:
                if addr > prev + 4:
                    regions.append((start, prev, count))
                    start = addr
                    count = 0
                prev = addr
                count += 1
            regions.append((start, prev, count))
            print(f"  Changed regions: {len(regions)}")
            for start, end, cnt in regions[:30]:
                size = end - start + 1
                region_type = "CODE" if start < 0x300000 else ("CONFIG" if start < 0xF00000 else "EEPROM")
                print(f"    0x{start:06X}-0x{end:06X} ({size} bytes) [{region_type}]")

    # String diff between V1.4 and V1.6b
    if 'V1.4' in firmwares and 'V1.6b' in firmwares:
        s14 = set(s for _, s in extract_strings(firmwares['V1.4'], 3))
        s16 = set(s for _, s in extract_strings(firmwares['V1.6b'], 3))
        added = s16 - s14
        removed = s14 - s16
        if added or removed:
            print(f"\n  String Changes V1.4 → V1.6b:")
            for s in sorted(removed):
                print(f"    - \"{s}\"")
            for s in sorted(added):
                print(f"    + \"{s}\"")

if __name__ == '__main__':
    main()
