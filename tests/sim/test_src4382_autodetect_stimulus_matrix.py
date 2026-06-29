from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from dlcp_fw.paths import PROJECT_ROOT
from dlcp_fw.sim import src4382_autodetect_matrix as matrix


def _load_cli_module():
    script = PROJECT_ROOT / "scripts" / "sim_src4382_autodetect_matrix.py"
    spec = importlib.util.spec_from_file_location("sim_src4382_autodetect_matrix", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def fresh_result() -> dict[str, object]:
    return matrix.run_matrix(plans=matrix.fresh_acquisition_matrix())


@pytest.fixture(scope="module")
def continuous_result() -> dict[str, object]:
    return matrix.run_matrix(plans=[matrix.continuous_user_timeline()])


@pytest.fixture(scope="module")
def robustness_result() -> dict[str, object]:
    return matrix.run_matrix(
        plans=[matrix.rxckr_nonzero_unlocked(), matrix.rxckr_hole_locked()]
    )


@pytest.fixture(scope="module")
def artifact_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out_dir = tmp_path_factory.mktemp("src4382_autodetect_matrix_artifacts")
    matrix.run_matrix(
        plans=[matrix.fresh_acquisition_matrix()[1]],
        out_dir=out_dir,
        argv=["scripts/sim_src4382_autodetect_matrix.py", "--out-dir", str(out_dir)],
    )
    return out_dir


def test_receiver_status_driver_tracks_selected_src4382_rx() -> None:
    phase = matrix.SourcePhase(
        "unit",
        matrix.DRIVER_STEP_TICKS,
        (matrix.DigitalSourceState("RX4", rxckr=0x02, unlock=0x00, non_pcm=0xA5),),
    )

    class FakeChain:
        def __init__(self) -> None:
            self.regs = {
                (0, matrix.SRC_REG_RX_CONTROL): 0x0B,
                (1, matrix.SRC_REG_RX_CONTROL): 0x09,
            }

        def read_main_src4382_reg(self, unit: int, subaddr: int) -> int:
            return self.regs.get((unit, subaddr), 0)

        def poke_main_src4382_reg(self, unit: int, subaddr: int, value: int) -> None:
            self.regs[(unit, subaddr)] = value & 0xFF

    fake = FakeChain()
    updates = matrix._apply_phase_status(fake, phase)  # type: ignore[arg-type]

    assert updates[0]["selected_rx"] == "RX4"
    assert fake.regs[(0, matrix.SRC_REG_RX_STATUS)] == 0x02
    assert fake.regs[(0, matrix.SRC_REG_RX_LOCK)] == 0x00
    assert fake.regs[(0, matrix.SRC_REG_NON_PCM)] == 0xA5
    assert updates[1]["selected_rx"] == "RX2"
    assert fake.regs[(1, matrix.SRC_REG_RX_STATUS)] == 0x00
    assert fake.regs[(1, matrix.SRC_REG_RX_LOCK)] == matrix.UNLOCK_BIT


def test_rx4_only_source_is_seen_only_after_firmware_selects_rx4(
    fresh_result: dict[str, object],
) -> None:
    current_rows = [
        row
        for row in fresh_result["current_trace"]  # type: ignore[index]
        if row["schedule_id"] == "fresh_optical"
    ]
    assert {row["unit"] for row in current_rows} == {"PB1", "PB2"}
    for row in current_rows:
        assert row["selected_candidate_rx"] == "RX4"
        assert row["detected_route"] == 4
        assert 0x0B in row["src4382_write_values"]["0x0D"]


def test_manifest_trace_and_comparison_schemas_are_valid(artifact_dir: Path) -> None:
    required = {
        "stimuli.json",
        "manifest.json",
        "stock_trace.jsonl",
        "current_trace.jsonl",
        "comparison.json",
        "comparison.md",
        "oracle_card.md",
    }
    assert required <= {path.name for path in artifact_dir.iterdir()}

    stimuli = json.loads((artifact_dir / "stimuli.json").read_text(encoding="utf-8"))
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    comparison = json.loads((artifact_dir / "comparison.json").read_text(encoding="utf-8"))
    stock_rows = _jsonl(artifact_dir / "stock_trace.jsonl")
    current_rows = _jsonl(artifact_dir / "current_trace.jsonl")

    assert manifest["format"] == matrix.FORMAT
    assert manifest["schema_version"] == 1
    assert manifest["phase_scale"] == 1.0
    assert manifest["stimuli_sha256"] == matrix.canonical_sha256(stimuli)
    assert manifest["execution_order"] == [matrix.STOCK_COMBO.combo_id, matrix.CURRENT_COMBO.combo_id]
    assert "control_sha256" in manifest["combos"][matrix.STOCK_COMBO.combo_id]
    assert "main_sha256" in manifest["combos"][matrix.CURRENT_COMBO.combo_id]
    assert comparison["stimuli_sha256"] == manifest["stimuli_sha256"]
    assert "Overall:" in (artifact_dir / "comparison.md").read_text(encoding="utf-8")

    matrix.validate_trace_rows(stock_rows)
    matrix.validate_trace_rows(current_rows)
    assert {row["unit"] for row in stock_rows} == {"PB1", "PB2"}
    assert {row["unit"] for row in current_rows} == {"PB1", "PB2"}


def test_stock_reference_trace_runs_before_current_trace(artifact_dir: Path) -> None:
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["execution_order"] == [matrix.STOCK_COMBO.combo_id, matrix.CURRENT_COMBO.combo_id]
    stock_rows = _jsonl(artifact_dir / "stock_trace.jsonl")
    current_rows = _jsonl(artifact_dir / "current_trace.jsonl")
    assert all(row["combo_id"] == matrix.STOCK_COMBO.combo_id for row in stock_rows)
    assert all(row["combo_id"] == matrix.CURRENT_COMBO.combo_id for row in current_rows)


def test_compare_traces_uses_stock_reference_first() -> None:
    stimuli = {"format": matrix.FORMAT, "plans": []}
    stock = [
        {
            "schedule_id": "fresh_optical",
            "phase_id": "fresh_optical",
            "unit": "PB1",
            "detected_route": 4,
            "expected_route": 4,
            "wrong_route": False,
            "waiting": False,
            "muted_pcm": False,
            "notes": [],
        }
    ]
    current = [{**stock[0], "detected_route": 1, "wrong_route": True}]
    comparison = matrix.compare_traces(stock, current, stimuli)
    assert comparison["overall"] == "regression"
    assert comparison["pairs"][0]["classification"] == "current_worse"


def test_current_v35_fresh_acquisition_detects_spdif_optical_and_usb(
    fresh_result: dict[str, object],
) -> None:
    pairs = fresh_result["comparison"]["pairs"]  # type: ignore[index]
    by_schedule = {(pair["schedule_id"], pair["unit"]): pair for pair in pairs}
    for unit in ("PB1", "PB2"):
        assert by_schedule[("fresh_spdif", unit)]["current_detected_route"] == 1
        assert by_schedule[("fresh_spdif", unit)]["classification"] == "match"
        assert by_schedule[("fresh_optical", unit)]["current_detected_route"] == 4
        assert by_schedule[("fresh_optical", unit)]["classification"] == "match"
        assert ("fresh_usb_audio", unit) in by_schedule
        assert by_schedule[("fresh_usb_audio", unit)]["classification"] in {
            "match",
            "needs_human",
        }
    assert fresh_result["comparison"]["overall"] == "pass"  # type: ignore[index]


def test_continuous_user_timeline_classifies_short_gap_handoff(
    continuous_result: dict[str, object],
) -> None:
    comparison = continuous_result["comparison"]  # type: ignore[index]
    assert comparison["overall"] == "pass"
    classes = {pair["classification"] for pair in comparison["pairs"]}
    assert "handoff_delayed_by_hard_loss" in classes
    current_rows = continuous_result["current_trace"]  # type: ignore[index]
    delayed = [row for row in current_rows if row["handoff_delayed_by_hard_loss"]]
    assert delayed
    assert all(not row["wrong_route"] for row in delayed)


def test_current_rejects_unlocked_rxckr_candidate_without_counting_as_regression(
    robustness_result: dict[str, object],
) -> None:
    pairs = [
        pair
        for pair in robustness_result["comparison"]["pairs"]  # type: ignore[index]
        if pair["schedule_id"] == "rxckr_nonzero_unlocked"
    ]
    assert {pair["classification"] for pair in pairs} == {"intended_robustness"}
    assert all(pair["current_detected_route"] == 0 for pair in pairs)


def test_current_holds_locked_rxckr_hole_after_acquisition(
    robustness_result: dict[str, object],
) -> None:
    pairs = [
        pair
        for pair in robustness_result["comparison"]["pairs"]  # type: ignore[index]
        if pair["schedule_id"] == "rxckr_hole_locked"
        and pair["phase_id"] == "locked_estimator_hole"
    ]
    assert {pair["current_detected_route"] for pair in pairs} == {1}
    assert {pair["classification"] for pair in pairs} == {"match"}


@pytest.mark.slow
def test_sustained_hard_loss_eventually_clears_or_rescans() -> None:
    result = matrix.run_matrix(plans=[matrix.sustained_silence_clear()])
    pairs = [
        pair
        for pair in result["comparison"]["pairs"]
        if pair["phase_id"] == "hard_unlock_silence"
    ]
    assert result["comparison"]["overall"] == "pass"
    assert {pair["current_detected_route"] for pair in pairs} == {0}


def test_two_digital_sources_selects_only_live_route_and_keeps_pbs_consistent() -> None:
    result = matrix.run_matrix(plans=[matrix.two_digital_sources()])
    pairs = result["comparison"]["pairs"]
    assert result["comparison"]["overall"] == "pass"
    assert {pair["current_detected_route"] for pair in pairs} <= {1, 4}
    assert len({pair["current_detected_route"] for pair in pairs}) == 1


def test_forced_optical_failure_fails_before_model_invocation() -> None:
    result = matrix.run_matrix(
        plans=[matrix.fresh_acquisition_matrix()[1]],
        force_current_optical_failure_units={"PB1", "PB2"},
    )
    assert result["comparison"]["overall"] == "regression"
    assert {pair["classification"] for pair in result["comparison"]["pairs"]} == {
        "current_worse"
    }


def test_oracle_card_is_generated_without_invoking_model(artifact_dir: Path) -> None:
    card = (artifact_dir / "oracle_card.md").read_text(encoding="utf-8")
    assert "stock=" in card
    assert "current=" in card
    assert "comparison.json" in card
    assert len(card.encode("utf-8")) <= matrix.CARD_SIZE_LIMIT
    assert "/Users/" not in card
    assert "$HOME" not in card
    assert "stock_trace.jsonl" in card


def test_cli_writes_artifacts_and_returns_nonzero_on_forced_regression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _load_cli_module()
    out_dir = tmp_path / "cli"

    def fake_run_matrix(**kwargs):
        out = kwargs["out_dir"]
        out.mkdir(parents=True, exist_ok=True)
        for name in (
            "stimuli.json",
            "manifest.json",
            "stock_trace.jsonl",
            "current_trace.jsonl",
            "comparison.json",
            "comparison.md",
            "oracle_card.md",
        ):
            (out / name).write_text("{}\n", encoding="utf-8")
        return {"comparison": {"overall": "regression", "pass": False}}

    monkeypatch.setattr(cli, "run_matrix", fake_run_matrix)
    rc = cli.main(["--out-dir", str(out_dir), "--quiet"])
    assert rc == 1
    assert (out_dir / "oracle_card.md").exists()
    rc_refuse = cli.main(["--out-dir", str(out_dir), "--quiet"])
    assert rc_refuse == 2


def test_cli_invokes_fake_model_without_shell_and_records_errors(tmp_path: Path) -> None:
    good = tmp_path / "good_model.py"
    good.write_text(
        "import sys\nsys.stdin.read()\nprint('{\"overall\":\"pass\",\"confidence\":1,\"findings\":[]}')\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "model"
    out_dir.mkdir()
    verdict = matrix.run_model_oracle(
        out_dir,
        oracle_card="card",
        model_cmd=f"{sys.executable} {good}",
        timeout=10,
    )
    assert verdict["overall"] == "pass"
    assert (out_dir / "oracle_verdict.json").exists()

    bad = tmp_path / "bad_model.py"
    bad.write_text("import sys\nsys.stdin.read()\nprint('not json')\n", encoding="utf-8")
    with pytest.raises(Exception):
        matrix.run_model_oracle(
            out_dir,
            oracle_card="card",
            model_cmd=f"{sys.executable} {bad}",
            timeout=10,
        )
    error = json.loads((out_dir / "oracle_error.json").read_text(encoding="utf-8"))
    assert error["run_ok"] is False
    assert error["model_argv"][0] == sys.executable
