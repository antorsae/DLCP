from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    ARTIFACTS_DIR,
    PATCHED_CONTROL_HEX,
    PATCHED_CONTROL_HEX_V141,
    PATCHED_CONTROL_HEX_V151B,
    PATCHED_CONTROL_HEX_V161B,
    PATCHED_CONTROL_HEX_V162B,
    PATCHED_CONTROL_HEX_V163B,
    PATCHED_CONTROL_HEX_V164B,
    PATCHED_MAIN_HEX,
    PATCHED_MAIN_HEX_V24,
    PATCHED_MAIN_HEX_V25,
    PATCHED_MAIN_HEX_V26,
    PATCHED_MAIN_HEX_V27,
    PATCHED_MAIN_HEX_V28,
    STOCK_CONTROL_HEX_V14,
    STOCK_CONTROL_HEX_V15B,
    STOCK_CONTROL_HEX_V16B,
    STOCK_MAIN_HEX,
    V30_MAIN_HEX,
    V31_MAIN_HEX,
    V32_MAIN_HEX,
)


# ---------------------------------------------------------------------------
# `--capture-ground-truth` plugin (sim-rewrite Phase 0).  Spec: §4 +
# docs/SIM_REWRITE_RUST_SPEC.md.  P0.1 lays down the directory plumbing
# and a per-test summary.json; P0.2-P0.4 fill in stimulus, RAM/SFR
# snapshots, UART byte streams, LCD raster, and EEPROM dumps.
# ---------------------------------------------------------------------------

GROUND_TRUTH_ROOT = ARTIFACTS_DIR / "ground_truth"


def _ground_truth_root() -> Path:
    """Return the active ground-truth output root.

    Defaults to ``artifacts/ground_truth/`` under the repo, but can
    be overridden via the ``DLCP_GROUND_TRUTH_OUT`` environment
    variable (used historically by an external replay runner to
    write captures into a tempdir without clobbering the blessed
    corpus).
    """
    override = os.environ.get("DLCP_GROUND_TRUTH_OUT")
    if override:
        return Path(override)
    return GROUND_TRUTH_ROOT


_NODEID_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _ground_truth_dirname(nodeid: str) -> str:
    """Map a pytest nodeid to a POSIX-safe, collision-resistant dirname.

    Format: ``<module-stem>__<sanitized-rest>__<hash12>`` where the
    hash12 suffix is the first 12 hex chars (48 bits) of sha1(nodeid).
    At 48 bits the birthday-collision probability stays under 1e-8
    even for corpora well past 100k tests, so the suffix can be
    treated as effectively unique while sanitization remains a
    cosmetic, non-bijective transform.

    Examples:

      tests/sim/test_v17_chain.py::test_v17_stock_v16b_chain_reaches_display
        -> test_v17_chain__test_v17_stock_v16b_chain_reaches_display__<hash>

      tests/sim/test_x.py::test_x[stock/v23]   (hypothetical)
      tests/sim/test_x.py::test_x[stock_v23]   (hypothetical)
        -> distinct dirs because the hash suffix differs.
    """
    file_part, _, rest = nodeid.partition("::")
    stem = Path(file_part).stem
    sanitized = _NODEID_SAFE_RE.sub("_", rest).strip("_")
    digest = hashlib.sha1(nodeid.encode("utf-8")).hexdigest()[:12]
    base = f"{stem}__{sanitized}" if sanitized else stem
    return f"{base}__{digest}"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--capture-ground-truth",
        action="store_true",
        default=False,
        help=(
            "Record per-test ground-truth fixtures under "
            f"{GROUND_TRUTH_ROOT.relative_to(ARTIFACTS_DIR.parent)}/<test_id>/. "
            "Used by the sim-rewrite Phase 0 capture pipeline.  "
            "The output root may be overridden via the "
            "DLCP_GROUND_TRUTH_OUT env var."
        ),
    )


# ---------------------------------------------------------------------------
# Sim-rewrite: rust is the only sim backend.  The DLCP_SIM_BACKEND env
# var that selected gpsim/rust/dual during the migration period was
# retired in PF.4 phase 2 batch 9 alongside the gpsim wrapper modules.
#
# Two pieces of legacy infrastructure are preserved as inert
# scaffolding so the tests that still reference them keep working:
#
#   * ``@pytest.mark.dual_supported`` marker — registered to avoid
#     ``PytestUnknownMarkWarning``.  223+ tests still carry the
#     marker; today it is purely informational ("this test was
#     ported during the migration") and has no runtime effect.
#
#   * ``dlcp_sim_backend`` fixture — returns ``"rust"`` constant.
#     One test still takes it as a parameter (legacy migration
#     plumbing in test_v171_v32_standby_reconnect.py); the value
#     is read-only.
#
# The migration-era auto-skip rule (skip every tests/sim item lacking
# ``dual_supported``) was retired in PF.4 phase 2 follow-up: it was
# grossly over-conservative.  Of the 28 unmarked tests, 27 pass / skip
# / xfail cleanly on rust; the remaining one was a buggy slice-end
# anchor in test_v171_sentinel_reconnect.py that has since been fixed.
# All sim tests now run; nothing is auto-skipped.
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Register the ``dual_supported`` marker (legacy from migration
    period; now functionally inert).

    The remaining legacy markers (``slow``, ``hardware``) are
    registered in the project's root ``pytest.ini``.
    """
    config.addinivalue_line(
        "markers",
        "dual_supported: legacy marker from the gpsim->rust migration "
        "period.  After PF.4 phase 2 batch 9 the marker has no runtime "
        "effect; 223+ tests still carry it from the porting era.  New "
        "tests don't need to add it.",
    )


@pytest.fixture(scope="session")
def dlcp_sim_backend() -> str:
    """Inert fixture: returns the constant ``"rust"``.

    Legacy from the gpsim->rust migration period; tests that still
    take this fixture as a parameter keep collecting cleanly.  New
    tests don't need to take it.
    """
    return "rust"


def _capture_enabled(config: pytest.Config) -> bool:
    return bool(config.getoption("--capture-ground-truth"))


def _ground_truth_dir_for(item: pytest.Item) -> Path:
    return _ground_truth_root() / _ground_truth_dirname(item.nodeid)


@pytest.fixture
def ground_truth_dir(request: pytest.FixtureRequest) -> Path | None:
    """Per-test fixture: returns the directory where ground-truth
    artifacts for the current test should be written, or ``None`` if
    ``--capture-ground-truth`` is not set.

    Created lazily so tests that don't opt in pay no I/O cost.  The
    directory persists across pytest invocations so an external runner
    can sweep ``artifacts/ground_truth/`` and treat each subdirectory
    as one captured fixture.  (The historical
    ``scripts/capture_gpsim_ground_truth.py`` runner was retired in
    PF.4 phase 1.)
    """
    if not _capture_enabled(request.config):
        return None
    out_dir = _ground_truth_dir_for(request.node)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


@pytest.fixture(autouse=True)
def _ground_truth_capture(request: pytest.FixtureRequest):
    """Open a `GroundTruthContext` for the duration of every test when
    `--capture-ground-truth` is set.

    Originally fed by ``record_event(...)`` /
    ``snapshot_after_event(...)`` calls inside the gpsim chain
    harnesses (``dlcp_fw.sim.{chain,wire_chain,control}_gpsim``).
    Those harnesses were retired in PF.4 phase 2; the fixture now
    runs as a no-op snapshot scaffold preserved for any external
    runner that opts into ``--capture-ground-truth``.  No live
    consumer exists in-tree.
    """
    if not _capture_enabled(request.config):
        yield
        return
    from dlcp_fw.sim.ground_truth import GroundTruthContext  # local import
    out_dir = _ground_truth_dir_for(request.node)
    with GroundTruthContext(out_dir):
        yield


def _aggregate_outcome(phases: dict[str, dict]) -> str:
    """Reduce per-phase outcomes to a single overall outcome.

    Worst-of ordering, matching pytest's user-facing status:
    ``failed`` > ``error`` > ``skipped`` > ``passed``.

    The makereport hook translates ``failed`` from a fixture
    phase (``setup``/``teardown``) into ``error`` before storing
    it here, so:

    * call-phase failure → ``failed`` (pytest's ``F``).
    * setup or teardown exception → ``error`` (pytest's ``E``).
      A test whose call passes but whose teardown fails is
      therefore reported as ``error``, not ``failed``.
    * any phase reports ``skipped`` and no failure or error
      occurred → ``skipped`` (the teardown ``passed`` that
      typically follows a setup skip MUST NOT mask the skip).
    * everything else → ``passed``.

    A test that has both a call failure and a teardown error is
    reported as ``failed`` since ``failed`` wins the precedence;
    the per-phase data in summary.json still records both.
    """
    outcomes = {p["outcome"] for p in phases.values()}
    if "failed" in outcomes:
        return "failed"
    if "error" in outcomes:
        return "error"
    if "skipped" in outcomes:
        return "skipped"
    if "passed" in outcomes:
        return "passed"
    return "unknown"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    if not _capture_enabled(item.config):
        return
    report = outcome.get_result()
    # Capture every phase (setup / call / teardown) so setup-fixture
    # errors and teardown failures aren't dropped from summary.json.
    out_dir = _ground_truth_dir_for(item)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary.json"

    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = {}
    else:
        summary = {}

    summary.setdefault("nodeid", item.nodeid)
    summary.setdefault("captured_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    summary.setdefault("schema_version", 1)
    phases = summary.setdefault("phases", {})

    # pytest's TestReport.outcome is one of {"passed", "failed",
    # "skipped"}; both setup AND teardown phase failures are what
    # pytest classifies as an "error" (the `E` in `-v` output)
    # rather than a regular test failure (the `F`, which only the
    # call phase produces).  Translate fixture-phase failed -> error
    # here so the aggregator can distinguish the two.
    phase_outcome = report.outcome
    if report.when in ("setup", "teardown") and report.outcome == "failed":
        phase_outcome = "error"

    phases[report.when] = {
        "outcome": phase_outcome,
        "duration_sec": getattr(report, "duration", None),
        "longrepr": str(report.longrepr) if report.failed else None,
    }
    summary["outcome"] = _aggregate_outcome(phases)
    summary["last_phase"] = report.when

    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


@pytest.fixture(scope="session")
def patched_main_hex() -> Path:
    if not PATCHED_MAIN_HEX.exists():
        raise RuntimeError(f"missing patched main HEX: {PATCHED_MAIN_HEX}")
    return PATCHED_MAIN_HEX


@pytest.fixture(scope="session")
def patched_control_hex() -> Path:
    if not PATCHED_CONTROL_HEX.exists():
        raise RuntimeError(f"missing patched control HEX: {PATCHED_CONTROL_HEX}")
    return PATCHED_CONTROL_HEX


@pytest.fixture(scope="session")
def patched_main_hex_v24() -> Path:
    if not PATCHED_MAIN_HEX_V24.exists():
        raise RuntimeError(f"missing patched main HEX: {PATCHED_MAIN_HEX_V24}")
    return PATCHED_MAIN_HEX_V24


@pytest.fixture(scope="session")
def patched_main_hex_v25() -> Path:
    if not PATCHED_MAIN_HEX_V25.exists():
        raise RuntimeError(f"missing patched main HEX: {PATCHED_MAIN_HEX_V25}")
    return PATCHED_MAIN_HEX_V25


@pytest.fixture(scope="session")
def patched_main_hex_v26() -> Path:
    if not PATCHED_MAIN_HEX_V26.exists():
        raise RuntimeError(f"missing patched main HEX: {PATCHED_MAIN_HEX_V26}")
    return PATCHED_MAIN_HEX_V26


@pytest.fixture(scope="session")
def patched_main_hex_v27() -> Path:
    if not PATCHED_MAIN_HEX_V27.exists():
        raise RuntimeError(f"missing patched main HEX: {PATCHED_MAIN_HEX_V27}")
    return PATCHED_MAIN_HEX_V27


@pytest.fixture(scope="session")
def patched_main_hex_v28() -> Path:
    if not PATCHED_MAIN_HEX_V28.exists():
        raise RuntimeError(f"missing patched main HEX: {PATCHED_MAIN_HEX_V28}")
    return PATCHED_MAIN_HEX_V28


@pytest.fixture(scope="session")
def patched_control_hex_v141() -> Path:
    if not PATCHED_CONTROL_HEX_V141.exists():
        raise RuntimeError(f"missing patched control HEX: {PATCHED_CONTROL_HEX_V141}")
    return PATCHED_CONTROL_HEX_V141


@pytest.fixture(scope="session")
def patched_control_hex_v151b() -> Path:
    if not PATCHED_CONTROL_HEX_V151B.exists():
        raise RuntimeError(f"missing patched control HEX: {PATCHED_CONTROL_HEX_V151B}")
    return PATCHED_CONTROL_HEX_V151B


@pytest.fixture(scope="session")
def patched_control_hex_v161b() -> Path:
    if not PATCHED_CONTROL_HEX_V161B.exists():
        raise RuntimeError(f"missing patched control HEX: {PATCHED_CONTROL_HEX_V161B}")
    return PATCHED_CONTROL_HEX_V161B


@pytest.fixture(scope="session")
def patched_control_hex_v162b() -> Path:
    if not PATCHED_CONTROL_HEX_V162B.exists():
        raise RuntimeError(f"missing patched control HEX: {PATCHED_CONTROL_HEX_V162B}")
    return PATCHED_CONTROL_HEX_V162B


@pytest.fixture(scope="session")
def patched_control_hex_v163b() -> Path:
    if not PATCHED_CONTROL_HEX_V163B.exists():
        raise RuntimeError(f"missing patched control HEX: {PATCHED_CONTROL_HEX_V163B}")
    return PATCHED_CONTROL_HEX_V163B


@pytest.fixture(scope="session")
def patched_control_hex_v164b() -> Path:
    if not PATCHED_CONTROL_HEX_V164B.exists():
        raise RuntimeError(f"missing patched control HEX: {PATCHED_CONTROL_HEX_V164B}")
    return PATCHED_CONTROL_HEX_V164B


@pytest.fixture(scope="session")
def stock_main_hex() -> Path:
    if not STOCK_MAIN_HEX.exists():
        raise RuntimeError(f"missing stock main HEX: {STOCK_MAIN_HEX}")
    return STOCK_MAIN_HEX


@pytest.fixture(scope="session")
def stock_control_hex_v14() -> Path:
    if not STOCK_CONTROL_HEX_V14.exists():
        raise RuntimeError(f"missing stock control HEX: {STOCK_CONTROL_HEX_V14}")
    return STOCK_CONTROL_HEX_V14


@pytest.fixture(scope="session")
def stock_control_hex_v15b() -> Path:
    if not STOCK_CONTROL_HEX_V15B.exists():
        raise RuntimeError(f"missing stock control HEX: {STOCK_CONTROL_HEX_V15B}")
    return STOCK_CONTROL_HEX_V15B


@pytest.fixture(scope="session")
def v30_main_hex() -> Path:
    if not V30_MAIN_HEX.exists():
        raise RuntimeError(f"missing V3.0 main HEX: {V30_MAIN_HEX}")
    return V30_MAIN_HEX


@pytest.fixture(scope="session")
def stock_control_hex_v16b() -> Path:
    if not STOCK_CONTROL_HEX_V16B.exists():
        raise RuntimeError(f"missing stock control HEX: {STOCK_CONTROL_HEX_V16B}")
    return STOCK_CONTROL_HEX_V16B


@pytest.fixture(scope="session")
def v31_main_hex() -> Path:
    if not V31_MAIN_HEX.exists():
        raise RuntimeError(f"missing V3.1 main HEX: {V31_MAIN_HEX}")
    return V31_MAIN_HEX
