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


def _ground_truth_root() -> Path:
    """Return the active ground-truth output root.

    Defaults to ``artifacts/ground_truth/`` under the repo, but can
    be overridden via the ``DLCP_GROUND_TRUTH_OUT`` environment
    variable.  ``scripts/replay_ground_truth.py`` uses the override
    to write replayed captures into a tempdir without clobbering
    the blessed corpus.
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
            "DLCP_GROUND_TRUTH_OUT env var (used by "
            "scripts/replay_ground_truth.py)."
        ),
    )


# ---------------------------------------------------------------------------
# Sim-rewrite Phase 4: DLCP_SIM_BACKEND={gpsim,dual,rust} plugin (P4.3).
# Picks which simulation engine each test runs against:
#
#   gpsim (DEFAULT, also if env var unset)
#       Run against the legacy gpsim PTY harnesses
#       (`chain_gpsim.py`, `wire_chain_gpsim.py`).  This is
#       the pre-Phase-4 behaviour and stays the safe default
#       until Phase 4 is fully migrated.
#
#   rust
#       Run only against the Rust `dlcp-sim` engine via
#       the PyO3 facade (`src/dlcp_fw/sim/dlcp_sim_native.py`).
#       Tests must opt in via `@pytest.mark.dual_supported`.
#       Tests without the marker are skipped with a clear
#       "not yet migrated to rust backend" message so the
#       pytest summary surfaces the migration backlog.
#
#   dual
#       Run every dual-supported test TWICE -- once with
#       gpsim, once with rust -- and rely on the test body
#       to assert identical externally-visible behaviour
#       (UART byte streams, LCD raster, EEPROM contents,
#       RAM snapshots).  The assertion lives in test code,
#       not the plugin: dual mode just runs both sides;
#       divergence makes the test FAIL like any normal
#       assertion failure.  Tests without
#       `@pytest.mark.dual_supported` are skipped, same as
#       rust mode.
#
# Spec reference: docs/SIM_REWRITE_RUST_SPEC.md §3 "Migration
# protocol" / docs/SIM_REWRITE_RUST_PROGRESS.md P4.3.
#
# Migration status: P4.3 lands ONLY the plugin
# infrastructure (env-var detection, marker registration,
# auto-skip).  Subsequent sub-tasks (P4.4 test_v17_*,
# P4.5 test_v171_*, P4.6 test_v31_*/v32_*, P4.7
# remainder) add `@pytest.mark.dual_supported` plus the
# rust-side adapter glue per test.  No tests have the
# marker today; running under DLCP_SIM_BACKEND=dual or
# rust therefore reports "all tests skipped" -- that's
# the expected initial state and is what P4.3's verify
# command checks.
# ---------------------------------------------------------------------------

DLCP_SIM_BACKEND_ENV = "DLCP_SIM_BACKEND"
DLCP_SIM_BACKEND_GPSIM = "gpsim"
DLCP_SIM_BACKEND_RUST = "rust"
DLCP_SIM_BACKEND_DUAL = "dual"
DLCP_SIM_BACKEND_VALID = {
    DLCP_SIM_BACKEND_GPSIM,
    DLCP_SIM_BACKEND_RUST,
    DLCP_SIM_BACKEND_DUAL,
}


def _resolve_dlcp_sim_backend() -> str:
    """Read and validate the DLCP_SIM_BACKEND env var.

    Returns the lowercased backend name.  Defaults to
    `gpsim` (preserving pre-Phase-4 behaviour) when the
    env var is unset or empty.  Raises pytest's
    `UsageError` for invalid values so the failure is
    surfaced clearly at the start of pytest collection
    rather than as a confusing per-test skip later.
    """
    raw = os.environ.get(DLCP_SIM_BACKEND_ENV, DLCP_SIM_BACKEND_GPSIM)
    backend = raw.strip().lower() or DLCP_SIM_BACKEND_GPSIM
    if backend not in DLCP_SIM_BACKEND_VALID:
        valid = ", ".join(sorted(DLCP_SIM_BACKEND_VALID))
        raise pytest.UsageError(
            f"{DLCP_SIM_BACKEND_ENV}={raw!r} is not a recognised backend "
            f"(valid: {valid}).  Spec: docs/SIM_REWRITE_RUST_PROGRESS.md P4.3."
        )
    return backend


def pytest_configure(config: pytest.Config) -> None:
    """Register the `dual_supported` marker so pytest doesn't
    warn `PytestUnknownMarkWarning` for tests that opt in to
    the new backends.  Sourcing the docstring here makes
    `pytest --markers` self-document the migration contract.
    """
    config.addinivalue_line(
        "markers",
        "dual_supported: test has been migrated to the Rust "
        "`dlcp-sim` engine and may run under DLCP_SIM_BACKEND="
        "{rust,dual}.  Without this marker, non-gpsim runs "
        "skip the test as 'not yet migrated'.  Add the marker "
        "AFTER landing the rust-side adapter glue for the "
        "test's chain harness in P4.4..P4.7.",
    )
    config.addinivalue_line(
        "markers",
        "gpsim: test requires the gpsim binary (legacy PTY harness).",
    )
    config.addinivalue_line(
        "markers",
        "wire: gpsim wire-chain test (legacy PTY-bridge multi-MAIN).",
    )
    config.addinivalue_line(
        "markers",
        "slow: long-running simulation test.",
    )
    config.addinivalue_line(
        "markers",
        "hardware: live hardware test; skipped by default unless "
        "--run-hardware is passed.",
    )
    # Stash the resolved backend on the config object so
    # pytest_collection_modifyitems can read it without
    # re-reading the env var (and racing any caller who
    # mutated DLCP_SIM_BACKEND mid-run).
    config._dlcp_sim_backend = _resolve_dlcp_sim_backend()  # type: ignore[attr-defined]


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Apply the DLCP_SIM_BACKEND auto-skip rule.

    For DLCP_SIM_BACKEND in {dual, rust}, every test that
    LACKS `@pytest.mark.dual_supported` gets a skip marker
    added with a clear message pointing at the migration
    plan.  Tests that HAVE the marker are left untouched
    (their adapters are responsible for picking up the
    backend choice at fixture-resolution time).
    """
    backend: str = getattr(
        config, "_dlcp_sim_backend", DLCP_SIM_BACKEND_GPSIM
    )
    if backend == DLCP_SIM_BACKEND_GPSIM:
        return
    skip_reason = (
        f"DLCP_SIM_BACKEND={backend}: test has no "
        "@pytest.mark.dual_supported marker yet -- still gpsim-only "
        "until the matching P4.4..P4.7 migration sub-task lands the "
        "rust-side adapter."
    )
    skip_marker = pytest.mark.skip(reason=skip_reason)
    for item in items:
        if "dual_supported" in {m.name for m in item.iter_markers()}:
            continue
        item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def dlcp_sim_backend(pytestconfig: pytest.Config) -> str:
    """Per-session fixture exposing the resolved DLCP_SIM_BACKEND.

    Tests that need to branch on the backend (e.g. to pick
    between `chain_gpsim.SingleMainChainHarness` and the
    rust facade's equivalent) read this fixture rather
    than `os.environ` so the value is consistent with the
    plugin's auto-skip decisions.
    """
    return getattr(
        pytestconfig, "_dlcp_sim_backend", DLCP_SIM_BACKEND_GPSIM
    )


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
def _ground_truth_capture(request: pytest.FixtureRequest):
    """Open a `GroundTruthContext` for the duration of every test when
    `--capture-ground-truth` is set.  Tests don't see this fixture
    directly; the chain harnesses in `dlcp_fw.sim.{chain,wire_chain,
    control}_gpsim` look up the active context via a module-level
    `ContextVar` and call `record_event(...)` + `snapshot_after_event(...)`
    on every mutator.  The conftest itself takes no init snapshot
    because the chain harnesses don't exist yet at fixture-enter
    time; instead, the first per-event snapshot effectively serves
    as the init snapshot for that harness, and the validator's
    "≥ 1 snapshot per captured test" rule is satisfied as long as
    a test actually drives a chain.
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
