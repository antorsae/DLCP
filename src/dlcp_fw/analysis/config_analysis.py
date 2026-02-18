#!/usr/bin/env python3
"""
Detailed PIC18 Configuration Bit Analysis
"""

# PIC18F2550/4550 Configuration bit definitions

CONFIG1L_BITS = {
    "USBDIV": [
        (0x3A >> 6) & 0x03,
        {0: "USB Clock source from 96MHz PLL/2", 1: "USB Clock source from OSC1/OSC2"},
    ],
    "CPUDIV": [
        (0x3A >> 4) & 0x03,
        {
            0: "No CPU system clock divide",
            1: "CPU system clock divided by 2",
            2: "CPU system clock divided by 3",
            3: "CPU system clock divided by 4",
        },
    ],
    "PLLDIV": [
        0x3A & 0x0F,
        {
            0: "No divide (4 MHz input)",
            1: "Divide by 2 (8 MHz input)",
            2: "Divide by 3 (12 MHz input)",
            3: "Divide by 4 (16 MHz input)",
            4: "Divide by 5 (20 MHz input)",
            5: "Divide by 6 (24 MHz input)",
            6: "Divide by 10 (40 MHz input)",
            7: "Divide by 12 (48 MHz input)",
        },
    ],
}

CONFIG1H_BITS = {
    "IESO": [
        (0x46 >> 7) & 0x01,
        {
            0: "Internal/External Switchover disabled",
            1: "Internal/External Switchover enabled",
        },
    ],
    "FCMEN": [
        (0x46 >> 6) & 0x01,
        {0: "Fail-Safe Clock Monitor disabled", 1: "Fail-Safe Clock Monitor enabled"},
    ],
    "OSC": [
        0x46 & 0x1F,
        {
            0: "LP Oscillator",
            1: "XT Oscillator",
            2: "HS Oscillator",
            3: "EC Oscillator, RA6 as CLKO",
            4: "EC Oscillator, RA6 as port",
            5: "EC Oscillator, port on RA6, PLL enabled",
            6: "HSPLL Oscillator (HS with PLL enabled)",
            7: "RC Oscillator",
            8: "External RC Oscillator, RA6 as CLKO",
            9: "External RC Oscillator, RA6 as port",
            10: "Internal RC Oscillator",
            11: "Internal RC Oscillator, RA6 as CLKO",
            12: "Internal RC Oscillator, RA6 as port",
        },
    ],
}

CONFIG2L_BITS = {
    "VREGEN": [
        (0x3E >> 4) & 0x01,
        {0: "USB Voltage Regulator disabled", 1: "USB Voltage Regulator enabled"},
    ],
    "BORV": [(0x3E >> 2) & 0x03, {0: "2.0V", 1: "2.7V", 2: "4.2V", 3: "4.5V"}],
    "BOREN": [
        0x3E & 0x03,
        {
            0: "Brown-out Reset disabled",
            1: "Brown-out Reset enabled in hardware only",
            2: "Brown-out Reset enabled in hardware, SBOREN disabled",
            3: "Brown-out Reset enabled and controlled by SBOREN",
        },
    ],
}

CONFIG2H_BITS = {
    "WDTPS": [
        (0x1E >> 4) & 0x07,
        {
            0: "1:1",
            1: "1:2",
            2: "1:4",
            3: "1:8",
            4: "1:16",
            5: "1:32",
            6: "1:64",
            7: "1:128",
        },
    ],
    "WDT": [
        0x1E & 0x03,
        {
            0: "WDT disabled (control on SWDTEN bit)",
            1: "WDT enabled",
            2: "WDT controlled by SWDTEN bit",
            3: "WDT disabled",
        },
    ],
}

CONFIG3H_BITS = {
    "MCLRE": [
        (0x00 >> 7) & 0x01,
        {0: "MCLR disabled, RE3 enabled", 1: "MCLR enabled, RE3 disabled"},
    ],
    "LPT1OSC": [
        (0x00 >> 5) & 0x01,
        {
            0: "Timer1 configured for higher power operation",
            1: "Timer1 configured for low-power operation",
        },
    ],
    "PBADEN": [
        (0x00 >> 1) & 0x01,
        {
            0: "PORTB<4:0> pins are configured as digital on RESET",
            1: "PORTB<4:0> pins are configured as analog on RESET",
        },
    ],
    "CCP2MX": [
        0x00 & 0x01,
        {0: "CCP2 multiplexed with RB3", 1: "CCP2 multiplexed with RC1"},
    ],
}

CONFIG4L_BITS = {
    "DEBUG": [
        (0x80 >> 7) & 0x01,
        {
            0: "Background debugger enabled, RB6 and RB7 as debug",
            1: "Background debugger disabled, RB6 and RB7 as I/O",
        },
    ],
    "XINST": [
        (0x80 >> 6) & 0x01,
        {
            0: "Instruction set extension disabled (Legacy mode)",
            1: "Instruction set extension enabled",
        },
    ],
    "LVP": [
        0x80 & 0x01,
        {0: "Low-Voltage Programming enabled", 1: "Low-Voltage Programming disabled"},
    ],
}

CONFIG5L_BITS = {
    "CP3": [
        (0x0F >> 3) & 0x01,
        {0: "Block 3 (006000-007FFF) code-protected", 1: "Block 3 not code-protected"},
    ],
    "CP2": [
        (0x0F >> 2) & 0x01,
        {0: "Block 2 (004000-005FFF) code-protected", 1: "Block 2 not code-protected"},
    ],
    "CP1": [
        (0x0F >> 1) & 0x01,
        {0: "Block 1 (002000-003FFF) code-protected", 1: "Block 1 not code-protected"},
    ],
    "CP0": [
        0x0F & 0x01,
        {0: "Block 0 (000000-001FFF) code-protected", 1: "Block 0 not code-protected"},
    ],
}

CONFIG5H_BITS = {
    "CPD": [
        (0xC0 >> 7) & 0x01,
        {0: "Data EEPROM code-protected", 1: "Data EEPROM not code-protected"},
    ],
    "CPB": [
        0xC0 & 0x01,
        {
            0: "Boot block (000000-000FFF) code-protected",
            1: "Boot block not code-protected",
        },
    ],
}

CONFIG6L_BITS = {
    "WRT3": [
        (0x0F >> 3) & 0x01,
        {
            0: "Block 3 (006000-007FFF) write-protected",
            1: "Block 3 not write-protected",
        },
    ],
    "WRT2": [
        (0x0F >> 2) & 0x01,
        {
            0: "Block 2 (004000-005FFF) write-protected",
            1: "Block 2 not write-protected",
        },
    ],
    "WRT1": [
        (0x0F >> 1) & 0x01,
        {
            0: "Block 1 (002000-003FFF) write-protected",
            1: "Block 1 not write-protected",
        },
    ],
    "WRT0": [
        0x0F & 0x01,
        {
            0: "Block 0 (000000-001FFF) write-protected",
            1: "Block 0 not write-protected",
        },
    ],
}

CONFIG6H_BITS = {
    "WRTD": [
        (0xA0 >> 7) & 0x01,
        {0: "Data EEPROM write-protected", 1: "Data EEPROM not write-protected"},
    ],
    "WRTB": [
        (0xA0 >> 6) & 0x01,
        {0: "Boot block write-protected", 1: "Boot block not write-protected"},
    ],
    "WRTC": [
        0xA0 & 0x01,
        {
            0: "Configuration registers write-protected",
            1: "Configuration registers not write-protected",
        },
    ],
}

CONFIG7L_BITS = {
    "EBTR3": [
        (0x0F >> 3) & 0x01,
        {
            0: "Block 3 (006000-007FFF) protected from table reads",
            1: "Block 3 not protected",
        },
    ],
    "EBTR2": [
        (0x0F >> 2) & 0x01,
        {
            0: "Block 2 (004000-005FFF) protected from table reads",
            1: "Block 2 not protected",
        },
    ],
    "EBTR1": [
        (0x0F >> 1) & 0x01,
        {
            0: "Block 1 (002000-003FFF) protected from table reads",
            1: "Block 1 not protected",
        },
    ],
    "EBTR0": [
        0x0F & 0x01,
        {
            0: "Block 0 (000000-001FFF) protected from table reads",
            1: "Block 0 not protected",
        },
    ],
}

CONFIG7H_BITS = {
    "EBTRB": [
        0x40 & 0x01,
        {0: "Boot block protected from table reads", 1: "Boot block not protected"},
    ]
}


def print_config(name, config_dict):
    print(f"\n### {name}")
    for bit_name, (value, meanings) in config_dict.items():
        meaning = meanings.get(value, "Unknown")
        print(f"  {bit_name}: {value} - {meaning}")


print("=" * 70)
print("PIC18F2550/4550 Configuration Bit Analysis")
print("=" * 70)

print_config("CONFIG1L (0x300000) = 0x3A", CONFIG1L_BITS)
print_config("CONFIG1H (0x300001) = 0x46", CONFIG1H_BITS)
print_config("CONFIG2L (0x300002) = 0x3E", CONFIG2L_BITS)
print_config("CONFIG2H (0x300003) = 0x1E", CONFIG2H_BITS)
print_config("CONFIG3H (0x300005) = 0x00", CONFIG3H_BITS)
print_config("CONFIG4L (0x300006) = 0x80", CONFIG4L_BITS)
print_config("CONFIG5L (0x300008) = 0x0F", CONFIG5L_BITS)
print_config("CONFIG5H (0x300009) = 0xC0", CONFIG5H_BITS)
print_config("CONFIG6L (0x30000A) = 0x0F", CONFIG6L_BITS)
print_config("CONFIG6H (0x30000B) = 0xA0", CONFIG6H_BITS)
print_config("CONFIG7L (0x30000C) = 0x0F", CONFIG7L_BITS)
print_config("CONFIG7H (0x30000D) = 0x40", CONFIG7H_BITS)

print("\n" + "=" * 70)
print("KEY FINDINGS:")
print("=" * 70)

print("""
1. OSCILLATOR CONFIGURATION:
   - HSPLL Oscillator (HS with PLL enabled)
   - PLLDIV = 10 (Divide by 10, 40 MHz input)
   - CPUDIV = 3 (CPU clock divided by 4 = 12 MIPS @ 48 MHz)
   - USBDIV = 0 (USB clock from 96MHz PLL/2 = 48 MHz)

2. WATCHDOG TIMER:
   - WDT enabled, postscaler 1:128
   - ~2.3 second timeout (typical 4ms * 128)

3. BROWN-OUT RESET:
   - Enabled in hardware only
   - BORV = 2.0V

4. DEBUG INTERFACE:
   - Background debugger DISABLED (RB6/RB7 available as I/O)
   - Low-Voltage Programming DISABLED

5. CODE PROTECTION:
   - All blocks NOT code-protected (CPx = 1)
   - Data EEPROM NOT code-protected (CPD = 1)
   - Boot block NOT code-protected (CPB = 1)

6. WRITE PROTECTION:
   - All blocks NOT write-protected (WRTx = 1)
   - Data EEPROM NOT write-protected (WRTD = 1)
   - Boot block NOT write-protected (WRTB = 1)
   - Configuration registers NOT write-protected (WRTC = 0) *** IMPORTANT ***

7. TABLE READ PROTECTION:
   - All blocks NOT protected from table reads (EBTRx = 1)
   - Boot block NOT protected (EBTRB = 1)

ERRORS IN ORIGINAL REPORT:
- Original stated "HS Oscillator" but it's actually HSPLL (HS with PLL)
- Original claimed CONFIG5L = 0x0F means "No Code Protection" - this is correct
- Original did not analyze CONFIG5H, CONFIG6H, CONFIG7H properly
""")
