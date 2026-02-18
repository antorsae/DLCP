from __future__ import annotations

from dlcp_fw.sim.scenarios import verify_patch_compat


def test_patch_compatibility_bytes(patched_main_hex, patched_control_hex) -> None:
    verify_patch_compat(patched_main_hex, patched_control_hex)
