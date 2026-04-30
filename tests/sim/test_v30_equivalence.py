"""V3.0 MAIN source-rewrite equivalence tests.

Tests 1-16: hex file integrity, data region byte-identity, source quality (AC3),
and post-assembly symbol address validation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import PROJECT_ROOT
from dlcp_fw.sim.hexio import parse_intel_hex


# All tests in this module are backend-agnostic (static source/hex
# analysis, flash-tool CLI plumbing, semantic-guard regex matchers).
# Mark the whole module dual_supported so DLCP_SIM_BACKEND={rust,dual}
# does not auto-skip them.
pytestmark = pytest.mark.dual_supported


# ---------------------------------------------------------------------------
# Test 1: hex file exists
# ---------------------------------------------------------------------------

def test_v30_hex_exists(v30_main_hex):
    assert v30_main_hex.exists()


# ---------------------------------------------------------------------------
# Test 2: config bits identical
# ---------------------------------------------------------------------------

def test_v30_config_bits_identical(v30_main_hex, stock_main_hex):
    """build_seeded_main_sim_hex() preserves config from seed, not V3.0."""
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    for addr in range(0x300000, 0x30000E):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), \
            f"Config mismatch at 0x{addr:06X}"


# ---------------------------------------------------------------------------
# Test 3: EEPROM identical
# ---------------------------------------------------------------------------

def test_v30_eeprom_identical(v30_main_hex, stock_main_hex):
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    for addr in range(0xF00000, 0xF00100):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), \
            f"EEPROM mismatch at 0x{addr:06X}"


# ---------------------------------------------------------------------------
# Test 4: preset table identical
# ---------------------------------------------------------------------------

def test_v30_preset_table_identical(v30_main_hex, stock_main_hex):
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    for addr in range(0x5600, 0x6000):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), \
            f"Preset table mismatch at 0x{addr:06X}"


# ---------------------------------------------------------------------------
# Test 5: USB descriptor content present
# ---------------------------------------------------------------------------

def test_v30_usb_descriptor_content(v30_main_hex, stock_main_hex):
    """USB descriptors must be present in V3.0 output."""
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    # USB device descriptor signature: 18 bytes starting 0x12, 0x01
    dev_desc_stock = bytes(stock.get(0x1088 + i, 0xFF) for i in range(18))
    assert dev_desc_stock[0] == 0x12 and dev_desc_stock[1] == 0x01
    # Find the same 18-byte sequence in V3.0 output
    built_range = bytes(built.get(a, 0xFF) for a in range(0x1000, 0x1200))
    assert dev_desc_stock in built_range, \
        "USB device descriptor not found in V3.0 output"


# ---------------------------------------------------------------------------
# Test 6: app entry at 0x1000
# ---------------------------------------------------------------------------

def test_v30_app_entry_at_0x1000(v30_main_hex):
    built = parse_intel_hex(v30_main_hex)
    assert 0x1000 in built, "No code at 0x1000"


# ---------------------------------------------------------------------------
# Test 7: no boot block emitted
# ---------------------------------------------------------------------------

def test_v30_no_boot_block(v30_main_hex):
    built = parse_intel_hex(v30_main_hex)
    boot_bytes = [a for a in built if a < 0x1000]
    assert boot_bytes == [], \
        f"Boot block bytes: {[hex(a) for a in boot_bytes[:10]]}"


# ---------------------------------------------------------------------------
# Test 8: code size reasonable (+-5% of stock)
# ---------------------------------------------------------------------------

def test_v30_code_size_reasonable(v30_main_hex, stock_main_hex):
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    stock_code = sum(1 for a in range(0x1000, 0x4970) if stock.get(a, 0xFF) != 0xFF)
    built_code = sum(1 for a in range(0x1000, 0x5600) if built.get(a, 0xFF) != 0xFF)
    ratio = built_code / stock_code if stock_code > 0 else 0
    assert 0.95 <= ratio <= 1.05, \
        f"Code size ratio {ratio:.3f} (stock={stock_code}, v30={built_code})"


# ---------------------------------------------------------------------------
# Test 9: diagnostic byte-diff summary (always passes)
# ---------------------------------------------------------------------------

def test_v30_byte_diff_diagnostic(v30_main_hex, stock_main_hex):
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    for label, start, end in [
        ("preset table", 0x5600, 0x6000),
        ("config", 0x300000, 0x30000E),
        ("EEPROM", 0xF00000, 0xF00100),
    ]:
        diffs = sum(1 for a in range(start, end)
                    if stock.get(a, 0xFF) != built.get(a, 0xFF))
        print(f"\n  {label}: {diffs} differences")
    built_total = sum(1 for a in range(0x1000, 0x5600) if a in built)
    print(f"  V3.0 code+data bytes (0x1000-0x55FF): {built_total}")


# ---------------------------------------------------------------------------
# Test 10: semantic labels present (AC3)
# ---------------------------------------------------------------------------

def test_v30_source_has_semantic_labels():
    asm_path = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
    assert asm_path.exists(), f"Missing {asm_path}"
    text = asm_path.read_text()
    for label in [
        "cmd_dispatch_gated", "adc_boot_gate", "i2c_byte_tx",
        "uart_tx_byte_blocking", "send_status_burst", "hw_standby_shutdown",
        "flash_write", "i2c_wait_bus_idle", "hard_reset",
    ]:
        assert label in text, f"Missing label: {label}"


# ---------------------------------------------------------------------------
# Test 11: named RAM equates (AC3)
# ---------------------------------------------------------------------------

def test_v30_source_has_named_ram():
    asm_dir = PROJECT_ROOT / "src" / "dlcp_fw" / "asm"
    combined = ""
    for f in list(asm_dir.glob("*.asm")) + list(asm_dir.glob("*.inc")):
        combined += f.read_text()
    for name in ["active_flags", "event_flags", "logical_volume", "rx_frame_position"]:
        assert name in combined, f"Missing RAM name: {name}"


# ---------------------------------------------------------------------------
# Test 12: no raw branch targets (AC3)
# ---------------------------------------------------------------------------

def test_v30_no_raw_hex_branch_targets():
    asm_path = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
    text = asm_path.read_text()
    raw_target = re.compile(
        r'^\s*(?:goto|call|bra|rcall|bc|bnc|bz|bnz|bov|bnov|bn|bnn)\s+'
        r'(?:0x[0-9A-Fa-f]+|H\'[0-9A-Fa-f]+\')',
        re.MULTILINE | re.IGNORECASE,
    )
    matches = raw_target.findall(text)
    assert matches == [], f"Raw branch targets: {matches[:5]}"


# ---------------------------------------------------------------------------
# Test 13: no raw SFR addresses (AC3)
# ---------------------------------------------------------------------------

def test_v30_sfr_references_are_symbolic():
    asm_path = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
    text = asm_path.read_text()
    sfr_addrs = {
        0xFE8: "WREG", 0xFD8: "STATUS", 0xFE0: "BSR",
        0xFC7: "SSPSTAT", 0xFC6: "SSPCON1", 0xFC5: "SSPCON2",
        0xFC9: "SSPBUF", 0xFAB: "RCSTA", 0xFAC: "TXSTA",
        0xFAD: "TXREG", 0xF80: "PORTA", 0xF81: "PORTB", 0xF82: "PORTC",
    }
    problems = []
    for line in text.splitlines():
        stripped = line.split(";")[0].strip()
        if not stripped or stripped.upper().startswith(("EQU", "DB", "DW", "#")):
            continue
        for addr, name in sfr_addrs.items():
            if re.search(rf'\b0x{addr:03X}\b', stripped, re.IGNORECASE):
                problems.append(f"Raw 0x{addr:03X} not {name}: {stripped[:60]}")
    assert problems == [], \
        f"{len(problems)} raw SFR refs:\n" + "\n".join(problems[:10])


# ---------------------------------------------------------------------------
# Test 14: no per-function org directives
# ---------------------------------------------------------------------------

def test_v30_no_per_function_org():
    asm_path = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
    text = asm_path.read_text()
    orgs = re.findall(r'^\s*org\s+(0x[0-9A-Fa-f]+|H\'[0-9A-Fa-f]+\')',
                      text, re.MULTILINE | re.IGNORECASE)
    allowed = {0x1000, 0x5600, 0xF00000}
    for a in range(0x300000, 0x30000E):
        allowed.add(a)
    for org_str in orgs:
        addr = int(org_str.strip("Hh'"), 16) if "'" in org_str else int(org_str, 16)
        assert addr in allowed, f"Unexpected org 0x{addr:06X}"


# ---------------------------------------------------------------------------
# Test 15: TBLPTR loads use labels
# ---------------------------------------------------------------------------

def test_v30_tblptr_loads_use_labels():
    asm_path = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
    text = asm_path.read_text()
    lines = text.splitlines()
    problems = []
    for i, line in enumerate(lines):
        s = line.split(";")[0].strip().lower()
        ns = lines[i + 1].split(";")[0].strip().lower() if i + 1 < len(lines) else ""
        if re.match(r'movlw\s+(0x[0-9a-f]+|h\'[0-9a-f]+\'|\d+)\s*$', s):
            if re.match(r'movwf\s+tblptr[lhu]', ns):
                problems.append(f"Line {i+1}: bare TBLPTR load: {line.strip()}")
        if re.match(r'addlw\s+(0x[0-9a-f]+|h\'[0-9a-f]+\'|\d+)\s*$', s):
            if re.match(r'movwf\s+tblptrl', ns):
                problems.append(f"Line {i+1}: bare addlw+TBLPTR: {line.strip()}")
    assert problems == [], \
        f"{len(problems)} bare TBLPTR loads:\n" + "\n".join(problems[:10])


# ---------------------------------------------------------------------------
# Test 16: post-assembly symbol address validation (critical)
# ---------------------------------------------------------------------------

def test_v30_key_symbols_at_stock_addresses(v30_main_hex, stock_main_hex):
    """Verify key function entry points land at stock addresses.

    Even without per-function org, addresses SHOULD match because the same
    instructions are emitted in the same order.  Failure indicates a
    converter bug.  Also validates gpsim overlay addresses in manifests.py.
    """
    stock = parse_intel_hex(stock_main_hex)
    built = parse_intel_hex(v30_main_hex)
    critical_addrs = [
        0x45FA,  # rx_ring_read (sim overlay)
        0x4872,  # sim_function_109 (sim overlay)
        0x4896,  # uart_tx_byte_blocking (sim overlay)
        0x489A,  # NOP after uart_tx_byte_blocking goto (sim overlay)
        0x48B6,  # i2c_wait_bus_idle (sim overlay)
        0x447E,  # timer3_blocking_delay (sim overlay -> 0x4492 variant)
        0x4492,  # sim_function_113 (sim overlay, alt i2c_wait_bus_idle)
        0x2D9E,  # sim_function_111 (sim overlay, alt uart_tx_byte_blocking)
        0x2D8C,  # adc_boot_gate entry (test breakpoint)
        0x18EE,  # function_005 (cmd_dispatch_gated)
        0x10AC,  # function_000 (first code after USB data)
    ]
    mismatches = []
    for addr in critical_addrs:
        s = (stock.get(addr, 0xFF), stock.get(addr + 1, 0xFF))
        b = (built.get(addr, 0xFF), built.get(addr + 1, 0xFF))
        if s != b:
            mismatches.append(
                f"0x{addr:04X}: stock={s[0]:02X}{s[1]:02X} v30={b[0]:02X}{b[1]:02X}"
            )
    assert mismatches == [], \
        f"V3.0 symbol addresses diverge from stock (converter bug?):\n" + \
        "\n".join(mismatches)
