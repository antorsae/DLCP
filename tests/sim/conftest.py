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
    GPSIM_XTC_BIN_DIR,
    GPSIM_XTC_BINARY,
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

if GPSIM_XTC_BIN_DIR.exists():
    os.environ["PATH"] = f"{GPSIM_XTC_BIN_DIR}{os.pathsep}{os.environ.get('PATH', '')}"
if GPSIM_XTC_BINARY.exists() and "DLCP_GPSIM_BIN" not in os.environ:
    os.environ["DLCP_GPSIM_BIN"] = str(GPSIM_XTC_BINARY)


# ---------------------------------------------------------------------------
# `--capture-ground-truth` plugin (sim-rewrite Phase 0).  Spec: §4 +
# docs/SIM_REWRITE_RUST_SPEC.md.  P0.1 lays down the directory plumbing
# and a per-test summary.json; P0.2-P0.4 fill in stimulus, RAM/SFR
# snapshots, UART byte streams, LCD raster, and EEPROM dumps.
# ---------------------------------------------------------------------------

GROUND_TRUTH_ROOT = ARTIFACTS_DIR / "ground_truth"


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
            "Used by the sim-rewrite Phase 0 capture pipeline."
        ),
    )


def _capture_enabled(config: pytest.Config) -> bool:
    return bool(config.getoption("--capture-ground-truth"))


def _ground_truth_dir_for(item: pytest.Item) -> Path:
    return GROUND_TRUTH_ROOT / _ground_truth_dirname(item.nodeid)


@pytest.fixture
def ground_truth_dir(request: pytest.FixtureRequest) -> Path | None:
    """Per-test fixture: returns the directory where ground-truth
    artifacts for the current test should be written, or ``None`` if
    ``--capture-ground-truth`` is not set.

    Created lazily so tests that don't opt in pay no I/O cost.  The
    directory persists across pytest invocations so an external runner
    (``scripts/capture_gpsim_ground_truth.py``) can sweep
    ``artifacts/ground_truth/`` and treat each subdirectory as one
    captured fixture.
    """
    if not _capture_enabled(request.config):
        return None
    out_dir = _ground_truth_dir_for(request.node)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


@pytest.fixture(autouse=True)
def _ground_truth_stimulus_recorder(request: pytest.FixtureRequest):
    """Open a `StimulusRecorder` for the duration of every test when
    `--capture-ground-truth` is set.  Tests don't see this fixture
    directly; the chain harnesses in `dlcp_fw.sim.chain_gpsim` and
    `dlcp_fw.sim.wire_chain_gpsim` pick the active recorder up via
    a module-level `ContextVar` and write through it on every
    mutator call (`press`, `set_blackout`, `set_main_*_fault`, etc.).
    The result is a per-test `stimulus.jsonl` parallel to the
    `summary.json` written by `pytest_runtest_makereport`.
    """
    if not _capture_enabled(request.config):
        yield
        return
    # Local import keeps the conftest lightweight when capture is off.
    from dlcp_fw.sim.ground_truth import StimulusRecorder
    out_dir = _ground_truth_dir_for(request.node)
    out_dir.mkdir(parents=True, exist_ok=True)
    with StimulusRecorder(out_dir / "stimulus.jsonl"):
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
