from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.manifests import control_disable_boot_wait, control_reset_to_appstart
from dlcp_fw.sim.overlay import OverlayError, OverlayManifest, apply_overlay, apply_overlays


# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
pytestmark = pytest.mark.dual_supported


def test_reset_overlay_applies_temp_only(tmp_path: Path, patched_control_hex: Path) -> None:
    src_before = patched_control_hex.read_bytes()
    out_hex = tmp_path / "sim.hex"
    res = apply_overlay(patched_control_hex, out_hex, control_reset_to_appstart())
    assert res.changed_bytes >= 1
    assert out_hex.exists()
    assert patched_control_hex.read_bytes() == src_before
    mem = parse_intel_hex(out_hex)
    assert mem[0x0000] == 0x20
    assert mem[0x0001] == 0xEF
    assert mem[0x0002] == 0x00
    assert mem[0x0003] == 0xF0


def test_overlay_chain(tmp_path: Path, patched_control_hex: Path) -> None:
    out_hex = tmp_path / "sim.hex"
    results = apply_overlays(
        patched_control_hex,
        out_hex,
        manifests=[control_reset_to_appstart(), control_disable_boot_wait()],
    )
    assert len(results) == 2
    mem = parse_intel_hex(out_hex)
    assert mem[0x0000] == 0x20
    assert mem[0x0052] == 0x00
    assert mem[0x0053] == 0x00
    assert mem[0x0054] == 0x00
    assert mem[0x0055] == 0x00


def test_precondition_failure(tmp_path: Path, patched_control_hex: Path) -> None:
    bad = OverlayManifest(
        name="bad",
        preconditions={0x0C76: 0x99},
        byte_patches={0x0C76: 0x20},
    )
    out_hex = tmp_path / "sim.hex"
    with pytest.raises(OverlayError):
        apply_overlay(patched_control_hex, out_hex, bad)
