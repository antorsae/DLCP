"""Helpers for building V3.2 MAIN unit-test firmware images.

The pattern: start from `src/dlcp_fw/asm/dlcp_main_v32.asm` and patch its
0x1000 user-reset `goto` to jump into a test-harness driver instead of
the normal cold-init path.  The harness `.asm` is appended at the end
of the source so the assembler places it after the production body but
before Preset B (we have plenty of slack in that 0x1000..0x4BFF band).

This keeps every production helper (main_core_service_*, main_flash_
service_46de, eeprom_read_byte/write_blocking, etc.) linked into the
unit-test image, while bypassing cold-init's USB / I2C / ISR bring-up
so the harness sees deterministic CPU/RAM state.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from dlcp_fw.paths import V32_MAIN_ASM
from dlcp_fw.sim.v30_symbols import assemble_v30

# The exact line in V32_MAIN_ASM that puts `goto flow_app_entry_1014`
# at address 0x1000.  Substituted with `goto unit_test_entry` so the
# user-reset vector jumps straight into our driver.
_RESET_LINE_PROD = (
    "    goto        flow_app_entry_1014                 "
    "; 0x1000 user reset trampoline"
)
_RESET_LINE_TEST = (
    "    goto        unit_test_entry                     "
    "; TEST HARNESS: redirect to unit_test_entry"
)


def build_unit_test_firmware(
    harness_asm: Path,
    out_dir: Path,
    *,
    name: str = "unit_test",
) -> tuple[Path, Path]:
    """Assemble a V3.2 MAIN image with the 0x1000 reset redirected
    to `unit_test_entry` defined by *harness_asm*.

    Returns (patched_asm_path, output_hex_path).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    prod_src = V32_MAIN_ASM.read_text(encoding="utf-8")

    if _RESET_LINE_PROD not in prod_src:
        raise RuntimeError(
            "could not find the reset-vector trampoline line in "
            f"{V32_MAIN_ASM} (refactor may have renamed it); unit-test "
            "firmware builder needs its substitution anchor updated"
        )
    patched = prod_src.replace(_RESET_LINE_PROD, _RESET_LINE_TEST, 1)

    # gpasm treats `END` as "stop reading the file" — anything after it is
    # silently dropped.  Strip the trailing END directive so the harness
    # we append gets assembled, and add a fresh END at the very end.
    end_re = re.compile(r"^\s*END\s*$", re.IGNORECASE | re.MULTILINE)
    if not end_re.search(patched):
        raise RuntimeError(
            "expected a trailing `END` directive in V3.2 source; not found"
        )
    patched = end_re.sub("; END — removed for unit-test harness append", patched, count=1)

    harness_src = harness_asm.read_text(encoding="utf-8")
    if "unit_test_entry:" not in harness_src:
        raise RuntimeError(
            f"{harness_asm} must define a label `unit_test_entry:` "
            "that the patched reset vector can jump to"
        )

    combined = (
        patched
        + "\n\n; " + "=" * 75
        + f"\n; Appended unit-test harness from {harness_asm.name}\n; "
        + "=" * 75 + "\n\n"
        + harness_src
        + "\n\n        END\n"
    )

    asm_out = out_dir / f"{name}.asm"
    hex_out = out_dir / f"{name}.hex"
    lst_out = out_dir / f"{name}.lst"

    # Copy the RAM include next to the output asm so gpasm resolves it.
    ram_inc = V32_MAIN_ASM.with_name("dlcp_main_ram.inc")
    shutil.copy2(ram_inc, out_dir / ram_inc.name)

    asm_out.write_text(combined, encoding="utf-8")
    assemble_v30(asm_out, hex_out, output_lst=lst_out)
    return asm_out, hex_out
