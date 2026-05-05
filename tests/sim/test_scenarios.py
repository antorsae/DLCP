from __future__ import annotations

from dlcp_fw.sim.scenarios import run_fault_matrix, run_preset_ab_roundtrip

import pytest

# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
pytestmark = pytest.mark.dual_supported


def test_roundtrip_scenario_defaults() -> None:
    res = run_preset_ab_roundtrip()
    assert res.control_frames >= 2
    assert res.bus_events >= 2
    # MAIN cmd=0x20 is idempotent; steady-state no-op preset sets do not re-apply.
    assert res.left_apply >= 2
    assert res.right_apply >= 2
    assert res.digest_a != res.digest_b


def test_fault_matrix_executes_all_cases() -> None:
    out = run_fault_matrix()
    assert set(out.keys()) == {"drop_first", "duplicate_first", "corrupt_cmd", "corrupt_route"}
    assert all(isinstance(v, bool) for v in out.values())
