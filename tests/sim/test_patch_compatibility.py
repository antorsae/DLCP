from __future__ import annotations

from dlcp_fw.paths import STOCK_MAIN_COMBINED_HEX, STOCK_MAIN_HEX
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.main_gpsim import build_seeded_main_sim_hex
from dlcp_fw.sim.manifests import main_v25_timeout_test_hooks
from dlcp_fw.sim.overlay import apply_overlay
from dlcp_fw.sim.scenarios import verify_patch_compat


# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.  Mark the
# whole module dual_supported so DLCP_SIM_BACKEND={rust,dual} does
# not auto-skip them.
import pytest

pytestmark = pytest.mark.dual_supported


def test_patch_compatibility_bytes(patched_main_hex, patched_control_hex) -> None:
    verify_patch_compat(patched_main_hex, patched_control_hex)


def test_main_v25_timeout_overlay_preserves_existing_wait_helper_bodies(
    patched_main_hex_v25,
    tmp_path,
) -> None:
    base = parse_intel_hex(patched_main_hex_v25)
    out_hex = tmp_path / "main_v25_timeout_overlay.hex"

    apply_overlay(patched_main_hex_v25, out_hex, main_v25_timeout_test_hooks())
    overlaid = parse_intel_hex(out_hex)

    for addr in range(0x5506, 0x556E):
        assert overlaid.get(addr, 0xFF) == base.get(addr, 0xFF)
    for addr in range(0x5574, 0x5600):
        assert overlaid.get(addr, 0xFF) == base.get(addr, 0xFF)

    assert any(overlaid.get(addr, 0xFF) != 0xFF for addr in range(0x53F8, 0x5400))
    assert any(overlaid.get(addr, 0xFF) != 0xFF for addr in range(0x54BA, 0x54C0))


def test_seeded_main_sim_hex_merges_app_only_hex_onto_recovery_context(tmp_path) -> None:
    out_hex = tmp_path / "seeded_stock_main.hex"
    build_seeded_main_sim_hex(STOCK_MAIN_HEX, out_hex)

    seeded = parse_intel_hex(out_hex)
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    combined = parse_intel_hex(STOCK_MAIN_COMBINED_HEX)

    for addr in range(0x0000, 0x1000):
        assert seeded.get(addr, 0xFF) == combined.get(addr, 0xFF)
    for addr in range(0x1000, 0x5600):
        assert seeded.get(addr, 0xFF) == stock.get(addr, 0xFF)
    for addr in range(0x5600, 0x6000):
        assert seeded.get(addr, 0xFF) == combined.get(addr, 0xFF)
    for addr in range(0x300000, 0x30000E):
        assert seeded.get(addr, 0xFF) == combined.get(addr, 0xFF)
    for addr in range(0xF00000, 0xF00100):
        assert seeded.get(addr, 0xFF) == combined.get(addr, 0xFF)
    for addr in range(0x200000, 0x200008):
        assert seeded.get(addr, 0xFF) == combined.get(addr, 0xFF)


def test_seeded_main_sim_hex_preserves_full_device_input_verbatim(tmp_path) -> None:
    out_hex = tmp_path / "seeded_combined_main.hex"
    build_seeded_main_sim_hex(STOCK_MAIN_COMBINED_HEX, out_hex)

    seeded = parse_intel_hex(out_hex)
    combined = parse_intel_hex(STOCK_MAIN_COMBINED_HEX)
    assert seeded == combined
