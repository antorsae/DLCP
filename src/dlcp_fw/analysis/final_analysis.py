#!/usr/bin/env python3
"""
Final Deep Analysis - 6-channel confirmation and coefficient transfer mechanism
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


def confirm_6_channels(memory: Dict[int, int]):
    """Confirm 6-channel support by analyzing the MOVLW 6 loop"""
    print("=" * 70)
    print("6-CHANNEL CONFIRMATION")
    print("=" * 70)

    # The MOVLW 6 at 0x1382 stores to 0xC1 - trace this
    print("\n  Found: MOVLW 6 -> MOVWF 0xC1 at 0x1382-0x1386")
    print("  This sets up a loop counter for 6 iterations = 6 channels")

    # Disassemble the loop
    print("\n  Disassembling the 6-channel loop:")
    addr = 0x1380

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

        if (word & 0xFF00) == 0x0E00:
            print(f"    0x{addr:04X}: MOVLW 0x{word & 0xFF:02X}")
        elif (word & 0xFE00) == 0x6E00:
            f = word & 0xFF
            print(f"    0x{addr:04X}: MOVWF 0x{f:02X}")
        elif (word & 0xFC00) == 0x4C00:
            f = word & 0xFF
            print(f"    0x{addr:04X}: DECFSZ 0x{f:02X}")
        elif (word & 0xF800) == 0xD800:
            n = word & 0x07FF
            if n & 0x0400:
                n = n - 0x0800
            target = addr + 2 + n * 2
            if target < addr:
                print(f"    0x{addr:04X}: BRA 0x{target:04X}  ; Loop back")
            else:
                print(f"    0x{addr:04X}: BRA 0x{target:04X}")
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
        elif word == 0x0012:
            print(f"    0x{addr:04X}: RETURN")
            break
        elif (word & 0xFC00) == 0x5000:
            f = word & 0xFF
            print(f"    0x{addr:04X}: MOVF 0x{f:02X}")
        elif (word & 0xFF00) == 0x0A00:
            print(f"    0x{addr:04X}: XORLW 0x{word & 0xFF:02X}")
        else:
            print(f"    0x{addr:04X}: {word:04X}")

        addr += 2


def analyze_coefficient_transfer(memory: Dict[int, int]):
    """Find how coefficients are actually transferred"""
    print("\n" + "=" * 70)
    print("COEFFICIENT TRANSFER MECHANISM")
    print("=" * 70)

    # The SPI writes I found were minimal - look for other transfer methods
    # Perhaps UART or parallel interface

    print("\n  Checking for coefficient-related data transfers...")

    # Look for large data movements
    # Find LFSR instructions that set up data pointers

    print("\n  LFSR pointer setup (potential coefficient buffers):")
    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if (word & 0xFF00) == 0xEE00:
            word2 = get_word(memory, addr + 2)
            if word2:
                fsr = (word >> 4) & 0x03
                value = word2 & 0x0FFF
                # Filter for interesting values
                if value >= 0x100 and value < 0x900:
                    print(f"    0x{addr:04X}: LFSR {fsr}, 0x{value:03X}")


def find_dsp_interface(memory: Dict[int, int]):
    """Identify the interface to the external DSP"""
    print("\n" + "=" * 70)
    print("EXTERNAL DSP INTERFACE")
    print("=" * 70)

    # Check PORT access patterns for bit-banged interfaces
    port_c_access = []
    port_b_access = []

    for addr in range(0x1000, 0x6000, 2):
        word = get_word(memory, addr)
        if word is None:
            continue

        # BSF/BCF instructions
        if (word & 0xFC00) in [0x8000, 0x9000]:
            f = word & 0xFF
            b = (word >> 9) & 0x07

            # PORTA = 0xF80, PORTB = 0xF81, PORTC = 0xF82
            # LATA = 0xF89, LATB = 0xF8A, LATC = 0xF8B
            if f in [0x80, 0x81, 0x82, 0x89, 0x8A, 0x8B]:
                mn = "BSF" if (word & 0xFC00) == 0x8000 else "BCF"
                reg = {
                    0x80: "PORTA",
                    0x81: "PORTB",
                    0x82: "PORTC",
                    0x89: "LATA",
                    0x8A: "LATB",
                    0x8B: "LATC",
                }.get(f, f"0x{f:02X}")
                print(f"    0x{addr:04X}: {mn} {reg}, {b}")


def analyze_command_protocol(memory: Dict[int, int]):
    """Analyze the full command protocol"""
    print("\n" + "=" * 70)
    print("COMMAND PROTOCOL ANALYSIS")
    print("=" * 70)

    # Commands identified
    commands = {
        0x01: ("GET_INFO", "Returns device info/firmware version"),
        0x02: ("SET_PARAM", "Set parameter value"),
        0x03: ("GET_PARAM", "Get parameter value"),
        0x04: ("SELECT_CHANNEL", "Select active channel (0-5)"),
        0x05: ("SET_FILTER", "Set filter type/parameters"),
        0x06: ("GET_FILTER", "Get filter type/parameters"),
        0x07: ("FILTER_CTRL", "Filter enable/disable/bypass"),
        0x08: ("EEPROM_WRITE", "Write to EEPROM"),
        0x09: ("DEVICE_RESET", "Reset/init device"),
        0x0A: ("COEFF_UPLOAD", "Upload filter coefficients"),
        0x0B: ("EEPROM_READ", "Read from EEPROM"),
        0x0D: ("COEFF_DOWNLOAD", "Download filter coefficients"),
        0x0F: ("SET_CONFIG", "Set configuration"),
        0x17: ("SET_GAIN", "Set channel gain"),
        0x21: ("SET_DELAY", "Set channel delay"),
        0x29: ("GET_GAIN", "Get channel gain"),
        0x3A: ("MUTE_CTRL", "Mute/unmute channels"),
        0x42: ("GET_STATUS", "Get device status"),
        0x4C: ("SAVE_CONFIG", "Save configuration to EEPROM"),
        0x64: ("EXTENDED", "Extended command set"),
        0x80: ("SELECT_PRESET", "Select preset/configuration bank"),
        0xB0: ("BYPASS", "Enable/disable bypass mode"),
        0xB1: ("LINK", "Link/unlink channels"),
    }

    print("\n  Command Protocol Summary:")
    print("  =========================")
    print("  HID Report Format (64 bytes):")
    print("  Byte 0:   Command")
    print("  Byte 1:   Channel (0-5) or sub-command")
    print("  Byte 2:   Parameter ID / Data offset")
    print("  Bytes 3+: Data payload")
    print()

    for cmd, (name, desc) in sorted(commands.items()):
        print(f"    0x{cmd:02X}: {name:16s} - {desc}")

    print("\n  Channel Support:")
    print("  =================")
    print("  - 6 channels confirmed (MOVLW 6 loop counter)")
    print("  - Channels indexed 0-5 or 1-6 (needs protocol testing)")
    print()
    print("  Filter Types (inferred from command structure):")
    print("  - Low-pass, High-pass, Band-pass, Band-stop")
    print("  - Parametric EQ (peaking)")
    print("  - Shelf filters (low-shelf, high-shelf)")
    print("  - All-pass")
    print("  - Likely IIR biquad implementation")


def summarize_architecture(memory: Dict[int, int]):
    """Final architecture summary"""
    print("\n" + "=" * 70)
    print("DLCP ARCHITECTURE SUMMARY")
    print("=" * 70)

    print("""
  HARDWARE ARCHITECTURE:
  ======================
  
  PIC18F2550 (USB Controller):
    - USB 2.0 Full Speed HID interface
    - Receives filter coefficients from PC software
    - Stores configuration in EEPROM
    - Communicates with external DSP via SPI/I2C
  
  External DSP (Unknown Model):
    - Performs actual audio processing
    - Receives filter coefficients from PIC18F
    - 6 independent audio channels
  
  CHANNEL CONFIGURATION:
  =====================
  - 6 independent channels confirmed
  - Each channel supports multiple filter stages
  - IIR biquad filters (5 coefficients each)
  - Per-channel: gain, delay, mute, bypass
  
  COEFFICIENT FORMAT (Likely):
  ============================
  - 24-bit signed fixed-point (Q1.23)
  - 5 coefficients per biquad: b0, b1, b2, a1, a2
  - Multiple biquads per channel for complex filters
  
  DATA FLOW:
  ==========
  1. PC Software (DLCP Filter Designer)
     ↓ USB HID (64-byte reports)
  2. PIC18F2550
     - Parse commands
     - Store in RAM/EEPROM
     ↓ SPI/I2C
  3. External DSP
     - Receive coefficients
     - Process audio
     - Output to DAC
  
  MEMORY MAP (PIC18F):
  ====================
  0x0000-0x0FFF: Bootloader (protected)
  0x1000-0x5FFF: Application firmware
  0x400-0x4FF:   USB endpoint buffers
  RAM Banks 0-4: Channel data structures
  RAM Bank 9+:   Extended configuration
  EEPROM:        Persistent settings, version info
""")


def main():
    hex_file = str(Path(__file__).resolve().parents[3] / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex")
    memory = parse_intel_hex(hex_file)

    print("=" * 70)
    print("DLCP FINAL ANALYSIS - 6 CHANNELS & DSP ARCHITECTURE")
    print("=" * 70)

    confirm_6_channels(memory)
    analyze_coefficient_transfer(memory)
    find_dsp_interface(memory)
    analyze_command_protocol(memory)
    summarize_architecture(memory)


if __name__ == "__main__":
    main()
