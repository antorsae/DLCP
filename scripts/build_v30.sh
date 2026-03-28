#!/bin/bash
# Build V3.0 MAIN firmware from source.
# Usage: scripts/build_v30.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ASM_DIR="$PROJECT_DIR/src/dlcp_fw/asm"
RELEASE_DIR="$PROJECT_DIR/firmware/patched/releases"
ASM_FILE="$ASM_DIR/dlcp_main_v30.asm"
HEX_FILE="$RELEASE_DIR/DLCP_Firmware_V3.0.hex"
STOCK_HEX="$PROJECT_DIR/firmware/stock/main/DLCP Firmware V2.3.hex"

echo "=== V3.0 MAIN Firmware Build ==="
echo ""

# Step 1: Generate .asm from stock hex
echo "Step 1: Generating assembly source..."
"$PROJECT_DIR/.venv_ep0/bin/python" "$SCRIPT_DIR/disasm_to_source.py"
echo "  -> $ASM_FILE"
echo ""

# Step 2: Assemble with gpasm
echo "Step 2: Assembling with gpasm..."
TMP_HEX=$(mktemp /tmp/v30_XXXXXX.hex)
gpasm -p18f2455 -I "$ASM_DIR" -o "$TMP_HEX" "$ASM_FILE"
echo "  -> $TMP_HEX"
echo ""

# Step 3: Compare data regions with stock
echo "Step 3: Data region byte-comparison..."
"$PROJECT_DIR/.venv_ep0/bin/python" -c "
from dlcp_fw.sim.hexio import parse_intel_hex
from pathlib import Path
stock = parse_intel_hex(Path('$STOCK_HEX'))
built = parse_intel_hex(Path('$TMP_HEX'))
ok = True
for label, start, end in [
    ('Preset table', 0x5600, 0x6000),
    ('Config bits', 0x300000, 0x30000E),
    ('EEPROM', 0xF00000, 0xF00100),
]:
    diffs = sum(1 for a in range(start, end) if stock.get(a, 0xFF) != built.get(a, 0xFF))
    status = 'OK' if diffs == 0 else f'FAIL ({diffs} diffs)'
    print(f'  {label}: {status}')
    if diffs > 0: ok = False
code_diffs = sum(1 for a in range(0x1000, 0x4970) if stock.get(a, 0xFF) != built.get(a, 0xFF))
print(f'  Code region (0x1000-0x496F): {code_diffs} diffs')
if not ok:
    raise SystemExit('Data region mismatch!')
"
echo ""

# Step 4: Copy to release location
echo "Step 4: Copying to release..."
cp "$TMP_HEX" "$HEX_FILE"
rm -f "$TMP_HEX"
echo "  -> $HEX_FILE"
echo ""

echo "=== Build complete ==="
echo "Run tests: .venv_ep0/bin/python -m pytest tests/sim/test_v30_equivalence.py -v"
