#!/usr/bin/env python3
"""Generate the V3.0 MAIN assembly source from stock V2.3 hex."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dlcp_fw.analysis.disasm_to_source import convert
from dlcp_fw.paths import PROJECT_ROOT

output = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
convert(output_path=output)
print(f"Generated: {output}")
print(f"RAM include: {output.parent / 'dlcp_main_ram.inc'}")
