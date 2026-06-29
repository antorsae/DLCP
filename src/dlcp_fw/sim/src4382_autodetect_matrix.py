"""Deterministic SRC4382 Auto Detect stock/current stimulus matrix."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any, Iterable, Sequence

from dlcp_fw.paths import (
    PROJECT_ROOT,
    SIM_ARTIFACTS_DIR,
    STOCK_CONTROL_HEX_V16B,
    STOCK_MAIN_COMBINED_HEX,
    V173_CONTROL_HEX,
    V35_MAIN_HEX,
)
from dlcp_fw.sim import dlcp_sim_native
from dlcp_fw.sim.dlcp_sim_native import Chain
from dlcp_fw.sim.oracle_json import extract_json_object


MANIFEST_SCHEMA_VERSION = 1
FORMAT = "src4382_autodetect_matrix"

SIM_TICKS_PER_SECOND = 48_000_000
SHORT_PHASE_TICKS = SIM_TICKS_PER_SECOND
DRIVER_STEP_TICKS = 250_000
LOCKED_SOURCE_CONVERGENCE_TICKS = SIM_TICKS_PER_SECOND
SHORT_SILENCE_GRACE_TICKS = SIM_TICKS_PER_SECOND
HARD_LOSS_CLEAR_TICKS = 14 * SIM_TICKS_PER_SECOND
CARD_SIZE_LIMIT = 16_384

INPUT_SELECT = 0x099
INPUT_SELECT_MIRROR = 0x0B3
SCAN_CANDIDATE_INDEX = 0x0B6
SCAN_MISS_DEBOUNCE = 0x0BA
I2C_SLOW_COUNTER = 0x0BB
SRC_ROUTE_STATUS = 0x05F
SRC_ROUTE_REQUEST = 0x093
EVENT_FLAGS = 0x07E
ROUTE_SHADOW = 0x0AB

SRC_REG_TX_CONTROL_2 = 0x08
SRC_REG_RX_CONTROL = 0x0D
SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
SRC_REG_RX_LOCK = 0x14
UNLOCK_BIT = 0x04

TAS_REG_VOLUME_COEFF = 0x30

RX_TABLE = {
    "RX1": {"rx_control": 0x08, "route": 3, "tx_control": 0x30, "index": 0, "label": "AES"},
    "RX2": {"rx_control": 0x09, "route": 1, "tx_control": 0x70, "index": 1, "label": "S/PDIF"},
    "RX3": {"rx_control": 0x0A, "route": 2, "tx_control": 0xB0, "index": 2, "label": "USB Audio"},
    "RX4": {"rx_control": 0x0B, "route": 4, "tx_control": 0xF0, "index": 3, "label": "Optical"},
}
RX_BY_CONTROL = {entry["rx_control"]: rx for rx, entry in RX_TABLE.items()}
ROUTE_TO_RX = {entry["route"]: rx for rx, entry in RX_TABLE.items()}

TRACE_REQUIRED_FIELDS = (
    "combo_id",
    "schedule_id",
    "phase_id",
    "elapsed_ticks",
    "unit",
    "active_receivers",
    "analog",
    "selected_candidate_rx",
    "candidate_index",
    "reg_0d",
    "reg_08",
    "reg_13",
    "reg_14",
    "reg_12",
    "input_select",
    "route_request_0x093",
    "route_shadow_0x0ab",
    "source_status_0x05f",
    "event_flags_0x07e",
    "src4382_stats",
    "src4382_write_values",
    "source_driver_update",
    "tas30_payload_present",
    "tas30_muted",
    "lcd",
    "connected",
    "waiting",
    "detected_route",
    "expected_route",
    "wrong_route",
    "route_missing_after_budget",
    "pb_divergence",
    "muted_pcm",
    "held_previous_within_hard_loss",
    "handoff_delayed_by_hard_loss",
    "intended_robustness",
    "notes",
)


@dataclass(frozen=True)
class ComboConfig:
    combo_id: str
    control_hex: Path
    main_hex: Path
    description: str


@dataclass(frozen=True)
class DigitalSourceState:
    receiver: str
    rxckr: int = 0x01
    unlock: int = 0x00
    non_pcm: int = 0x00


@dataclass(frozen=True)
class SourcePhase:
    phase_id: str
    duration_ticks: int
    active_sources: tuple[DigitalSourceState, ...] = ()
    analog: tuple[str, ...] = ()
    expected_route: int | None = None
    allow_previous_hold: bool = False
    expected_live_routes: tuple[int, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class StimulusPlan:
    schedule_id: str
    phases: tuple[SourcePhase, ...]
    setup_mode: str = "boot_auto_detect"
    description: str = ""


@dataclass
class ComboRun:
    combo: ComboConfig
    traces: list[dict[str, Any]]
    stimuli: dict[str, Any]


STOCK_COMBO = ComboConfig(
    "stock_v16b_v23",
    STOCK_CONTROL_HEX_V16B,
    STOCK_MAIN_COMBINED_HEX,
    "stock CONTROL V1.6b + MAIN V2.3",
)
CURRENT_COMBO = ComboConfig(
    "current_v173_v35",
    V173_CONTROL_HEX,
    V35_MAIN_HEX,
    "current CONTROL V1.73 + MAIN V3.5",
)


def continuous_user_timeline() -> StimulusPlan:
    return StimulusPlan(
        "continuous_user_timeline",
        (
            SourcePhase("silence_a", SHORT_PHASE_TICKS, notes="initial silence"),
            SourcePhase("spdif", SHORT_PHASE_TICKS, (_locked("RX2"),), expected_route=1),
            SourcePhase("silence_b", SHORT_PHASE_TICKS, allow_previous_hold=True),
            SourcePhase(
                "spdif_plus_analog1",
                SHORT_PHASE_TICKS,
                (_locked("RX2"),),
                ("Analog 1",),
                expected_route=1,
            ),
            SourcePhase("silence_c", SHORT_PHASE_TICKS, allow_previous_hold=True),
            SourcePhase(
                "optical",
                SHORT_PHASE_TICKS,
                (_locked("RX4"),),
                expected_route=4,
                allow_previous_hold=True,
            ),
            SourcePhase("silence_d", SHORT_PHASE_TICKS, allow_previous_hold=True),
            SourcePhase(
                "usb_audio",
                SHORT_PHASE_TICKS,
                (_locked("RX3"),),
                expected_route=2,
                allow_previous_hold=True,
            ),
        ),
        description="exact short-gap source timeline requested by operator",
    )


def fresh_acquisition_matrix() -> tuple[StimulusPlan, ...]:
    return (
        StimulusPlan(
            "fresh_spdif",
            (SourcePhase("fresh_spdif", LOCKED_SOURCE_CONVERGENCE_TICKS, (_locked("RX2"),), expected_route=1),),
            description="S/PDIF from cleared Auto Detect state",
        ),
        StimulusPlan(
            "fresh_optical",
            (SourcePhase("fresh_optical", LOCKED_SOURCE_CONVERGENCE_TICKS, (_locked("RX4"),), expected_route=4),),
            description="Optical from cleared Auto Detect state",
        ),
        StimulusPlan(
            "fresh_usb_audio",
            (SourcePhase("fresh_usb_audio", LOCKED_SOURCE_CONVERGENCE_TICKS, (_locked("RX3"),), expected_route=2),),
            description="USB Audio from cleared Auto Detect state",
        ),
    )


def rxckr_hole_locked() -> StimulusPlan:
    return StimulusPlan(
        "rxckr_hole_locked",
        (
            SourcePhase("acquire_spdif", LOCKED_SOURCE_CONVERGENCE_TICKS, (_locked("RX2"),), expected_route=1),
            SourcePhase(
                "locked_estimator_hole",
                SHORT_PHASE_TICKS,
                (DigitalSourceState("RX2", rxckr=0x00, unlock=0x00),),
                expected_route=1,
                allow_previous_hold=True,
            ),
        ),
        description="selected receiver has RXCKR=0 while UNLOCK=0",
    )


def rxckr_nonzero_unlocked() -> StimulusPlan:
    return StimulusPlan(
        "rxckr_nonzero_unlocked",
        (
            SourcePhase(
                "false_candidate",
                2 * LOCKED_SOURCE_CONVERGENCE_TICKS,
                (DigitalSourceState("RX2", rxckr=0x01, unlock=UNLOCK_BIT),),
                expected_route=None,
                expected_live_routes=(),
                notes="RXCKR evidence exists but formal UNLOCK is set",
            ),
        ),
        description="candidate has RXCKR!=0 but UNLOCK=1",
    )


def sustained_silence_clear() -> StimulusPlan:
    return StimulusPlan(
        "sustained_silence_clear",
        (
            SourcePhase("acquire_spdif", LOCKED_SOURCE_CONVERGENCE_TICKS, (_locked("RX2"),), expected_route=1),
            SourcePhase("hard_unlock_silence", HARD_LOSS_CLEAR_TICKS, expected_route=0),
        ),
        description="selected route then sustained RXCKR=0/UNLOCK=1",
    )


def two_digital_sources() -> StimulusPlan:
    return StimulusPlan(
        "two_digital_sources",
        (
            SourcePhase(
                "spdif_and_optical",
                LOCKED_SOURCE_CONVERGENCE_TICKS,
                (_locked("RX2"), _locked("RX4")),
                expected_route=None,
                expected_live_routes=(1, 4),
            ),
        ),
        description="RX2 and RX4 locked simultaneously",
    )


def default_stimulus_plans() -> tuple[StimulusPlan, ...]:
    return (
        continuous_user_timeline(),
        *fresh_acquisition_matrix(),
        rxckr_nonzero_unlocked(),
        rxckr_hole_locked(),
        sustained_silence_clear(),
        two_digital_sources(),
    )


def default_output_root() -> Path:
    return SIM_ARTIFACTS_DIR / "src4382_autodetect_matrix"


def timestamped_output_dir(root: Path | None = None) -> Path:
    root = default_output_root() if root is None else root
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    candidate = root / stamp
    suffix = 1
    while candidate.exists():
        candidate = root / f"{stamp}_{suffix:02d}"
        suffix += 1
    return candidate


def run_matrix(
    *,
    plans: Sequence[StimulusPlan] | None = None,
    out_dir: Path | None = None,
    argv: Sequence[str] | None = None,
    model_cmd: str | None = None,
    model_timeout: int = 120,
    force_current_optical_failure_units: Iterable[str] = (),
) -> dict[str, Any]:
    """Run stock then current, optionally writing the full artifact set."""
    selected_plans = tuple(default_stimulus_plans() if plans is None else plans)
    stimuli = _stimuli_document(selected_plans)
    stock = run_combo(STOCK_COMBO, selected_plans)
    current = run_combo(CURRENT_COMBO, selected_plans)
    forced_units = set(force_current_optical_failure_units)
    if forced_units:
        _force_optical_failure(current.traces, forced_units)
    comparison = compare_traces(stock.traces, current.traces, stimuli)
    card = render_oracle_card(stimuli, comparison)

    result = {
        "stimuli": stimuli,
        "stock_trace": stock.traces,
        "current_trace": current.traces,
        "comparison": comparison,
        "oracle_card": card,
        "out_dir": str(out_dir) if out_dir else None,
    }
    if out_dir is not None:
        write_artifacts(
            out_dir,
            stimuli=stimuli,
            stock_trace=stock.traces,
            current_trace=current.traces,
            comparison=comparison,
            oracle_card=card,
            argv=argv or (),
            model_cmd=model_cmd,
            model_timeout=model_timeout,
        )
    return result


def run_combo(combo: ComboConfig, plans: Sequence[StimulusPlan]) -> ComboRun:
    traces: list[dict[str, Any]] = []
    for plan in plans:
        chain = _boot_chain(combo)
        _assert_or_prepare_autodetect(chain)
        for phase in plan.phases:
            _run_phase(chain, combo, plan, phase, traces)
    return ComboRun(combo, traces, _stimuli_document(plans))


def compare_traces(
    stock_trace: Sequence[dict[str, Any]],
    current_trace: Sequence[dict[str, Any]],
    stimuli: dict[str, Any],
) -> dict[str, Any]:
    stock_latest = _latest_by_key(stock_trace)
    current_latest = _latest_by_key(current_trace)
    pairs: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []

    for key in sorted(current_latest):
        current = current_latest[key]
        stock = stock_latest.get(key)
        classification = _classify_pair(stock, current)
        pair = {
            "schedule_id": key[0],
            "phase_id": key[1],
            "unit": key[2],
            "stock_detected_route": stock.get("detected_route") if stock else None,
            "current_detected_route": current.get("detected_route"),
            "expected_route": current.get("expected_route"),
            "classification": classification,
            "current_worse": classification == "current_worse",
            "notes": current.get("notes", []),
        }
        pairs.append(pair)
        if pair["current_worse"]:
            regressions.append(pair)

    return {
        "format": FORMAT,
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "stimuli_sha256": canonical_sha256(stimuli),
        "execution_order": [STOCK_COMBO.combo_id, CURRENT_COMBO.combo_id],
        "overall": "regression" if regressions else "pass",
        "pass": not regressions,
        "pairs": pairs,
        "regressions": regressions,
        "summary": _summary_from_pairs(pairs),
    }


def write_artifacts(
    out_dir: Path,
    *,
    stimuli: dict[str, Any],
    stock_trace: Sequence[dict[str, Any]],
    current_trace: Sequence[dict[str, Any]],
    comparison: dict[str, Any],
    oracle_card: str,
    argv: Sequence[str],
    model_cmd: str | None,
    model_timeout: int,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "stimuli.json", stimuli)
    _write_jsonl(out_dir / "stock_trace.jsonl", stock_trace)
    _write_jsonl(out_dir / "current_trace.jsonl", current_trace)
    _write_json(out_dir / "comparison.json", comparison)
    (out_dir / "comparison.md").write_text(render_comparison_md(comparison), encoding="utf-8")
    (out_dir / "oracle_card.md").write_text(oracle_card, encoding="utf-8")
    manifest = build_manifest(
        out_dir,
        stimuli=stimuli,
        argv=argv,
        card_size=len(oracle_card.encode("utf-8")),
    )
    _write_json(out_dir / "manifest.json", manifest)

    if model_cmd:
        run_model_oracle(
            out_dir,
            oracle_card=oracle_card,
            model_cmd=model_cmd,
            timeout=model_timeout,
        )


def build_manifest(
    out_dir: Path,
    *,
    stimuli: dict[str, Any],
    argv: Sequence[str],
    card_size: int,
) -> dict[str, Any]:
    artifacts = {
        name: (out_dir / name).exists()
        for name in (
            "stimuli.json",
            "stock_trace.jsonl",
            "current_trace.jsonl",
            "comparison.json",
            "comparison.md",
            "oracle_card.md",
        )
    }
    return {
        "format": FORMAT,
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "argv": list(argv),
        "simulator_backend_version": getattr(dlcp_sim_native, "__version__", None),
        "timebase": {
            "SIM_TICKS_PER_SECOND": SIM_TICKS_PER_SECOND,
            "SHORT_PHASE_TICKS": SHORT_PHASE_TICKS,
            "DRIVER_STEP_TICKS": DRIVER_STEP_TICKS,
            "LOCKED_SOURCE_CONVERGENCE_TICKS": LOCKED_SOURCE_CONVERGENCE_TICKS,
            "SHORT_SILENCE_GRACE_TICKS": SHORT_SILENCE_GRACE_TICKS,
            "HARD_LOSS_CLEAR_TICKS": HARD_LOSS_CLEAR_TICKS,
        },
        "phase_scale": 1.0,
        "execution_order": [STOCK_COMBO.combo_id, CURRENT_COMBO.combo_id],
        "combos": {
            combo.combo_id: _combo_manifest(combo)
            for combo in (STOCK_COMBO, CURRENT_COMBO)
        },
        "release_identity": {},
        "git_dirty_summary": _git_dirty_summary(),
        "stimuli_sha256": canonical_sha256(stimuli),
        "artifact_completion": artifacts,
        "oracle_card_size": card_size,
        "artifact_dir": _repo_relative(out_dir),
    }


def run_model_oracle(
    out_dir: Path,
    *,
    oracle_card: str,
    model_cmd: str,
    timeout: int,
) -> dict[str, Any]:
    argv = shlex.split(model_cmd)
    if not argv:
        raise ValueError("--model-cmd parsed to an empty argv")
    prompt = _model_prompt(oracle_card)
    card_digest = hashlib.sha256(oracle_card.encode("utf-8")).hexdigest()
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"model command exited {proc.returncode}")
        verdict = extract_json_object(proc.stdout)
        _write_json(out_dir / "oracle_verdict.json", verdict)
        return verdict
    except Exception as exc:
        error = {
            "run_ok": False,
            "model_argv": argv,
            "timeout": timeout,
            "card_sha256": card_digest,
            "error": str(exc),
        }
        if "proc" in locals():
            error.update(
                {
                    "returncode": proc.returncode,
                    "stdout_snippet": proc.stdout[:500],
                    "stderr_snippet": proc.stderr[:500],
                }
            )
        _write_json(out_dir / "oracle_error.json", error)
        raise


def render_oracle_card(stimuli: dict[str, Any], comparison: dict[str, Any]) -> str:
    lines = [
        "# SRC4382 Auto Detect Oracle Card",
        "",
        f"format: {FORMAT}",
        f"schema_version: {MANIFEST_SCHEMA_VERSION}",
        f"stimuli_sha256: {canonical_sha256(stimuli)}",
        f"overall: {comparison['overall']}",
        "",
        "## Summary",
    ]
    for key, value in comparison["summary"].items():
        lines.append(f"- {key}: {value}")
    lines += ["", "## Phase Outcomes"]
    for pair in comparison["pairs"]:
        lines.append(
            "- {schedule_id}/{phase_id}/{unit}: stock={stock_detected_route} "
            "current={current_detected_route} expected={expected_route} "
            "class={classification}".format(**pair)
        )
    if comparison["regressions"]:
        lines += ["", "## Regressions"]
        for item in comparison["regressions"]:
            lines.append(f"- {item['schedule_id']}/{item['phase_id']}/{item['unit']}")
    lines += [
        "",
        "## Acceptable Divergences",
        "- current_v173_v35 may reject RXCKR!=0 candidates when 0x14.UNLOCK is set",
        "- current_v173_v35 may hold a prior route during the short hard-loss grace window",
        "",
        "## Artifact Paths",
        "- stimuli.json",
        "- stock_trace.jsonl",
        "- current_trace.jsonl",
        "- comparison.json",
        "- comparison.md",
    ]
    card = "\n".join(lines) + "\n"
    return _redact_card(card[:CARD_SIZE_LIMIT])


def render_comparison_md(comparison: dict[str, Any]) -> str:
    lines = [
        "# SRC4382 Auto Detect Comparison",
        "",
        f"Overall: {comparison['overall']}",
        "",
        "| Schedule | Phase | Unit | Stock | Current | Expected | Classification |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for pair in comparison["pairs"]:
        lines.append(
            "| {schedule_id} | {phase_id} | {unit} | {stock_detected_route} | "
            "{current_detected_route} | {expected_route} | {classification} |".format(**pair)
        )
    return "\n".join(lines) + "\n"


def canonical_sha256(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_trace_rows(rows: Sequence[dict[str, Any]]) -> None:
    for row in rows:
        missing = [field for field in TRACE_REQUIRED_FIELDS if field not in row]
        if missing:
            raise AssertionError(f"trace row missing fields: {missing}")


def _locked(receiver: str) -> DigitalSourceState:
    return DigitalSourceState(receiver=receiver, rxckr=0x01, unlock=0x00, non_pcm=0x00)


def _boot_chain(combo: ComboConfig) -> Chain:
    chain = Chain.from_v171_v32(
        control_hex_path=str(combo.control_hex),
        main_hex_path=str(combo.main_hex),
    )
    chunks = chain.run_until_connected(limit=300)
    if chunks >= 300 or not chain.is_connected() or chain.is_waiting():
        raise RuntimeError(f"{combo.combo_id} did not connect: lcd={chain.lcd_lines()!r}")
    return chain


def _assert_or_prepare_autodetect(chain: Chain) -> None:
    lcd = chain.lcd_lines()
    if lcd[1] != "Auto Detect     ":
        raise RuntimeError(f"chain did not boot to Auto Detect: lcd={lcd!r}")
    for unit in (0, 1):
        chain.write_main_reg(unit, INPUT_SELECT, 0x00)
        chain.write_main_reg(unit, INPUT_SELECT_MIRROR, 0x00)
        chain.write_main_reg(unit, SCAN_CANDIDATE_INDEX, 0x00)
        chain.write_main_reg(unit, SCAN_MISS_DEBOUNCE, 0x00)
        chain.write_main_reg(unit, I2C_SLOW_COUNTER, 0x65)
        chain.write_main_reg(unit, SRC_ROUTE_REQUEST, 0x00)
        chain.write_main_reg(unit, ROUTE_SHADOW, 0x00)
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_CONTROL, 0x08)
        chain.poke_main_src4382_reg(unit, SRC_REG_TX_CONTROL_2, 0x30)
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_STATUS, 0x00)
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_LOCK, UNLOCK_BIT)
        chain.poke_main_src4382_reg(unit, SRC_REG_NON_PCM, 0x00)
        chain.reset_main_src4382_stats(unit)
        chain.reset_main_dsp_write_log(unit)


def _run_phase(
    chain: Chain,
    combo: ComboConfig,
    plan: StimulusPlan,
    phase: SourcePhase,
    traces: list[dict[str, Any]],
) -> None:
    start = chain.current_tick()
    previous_routes = {unit: chain.read_main_reg(unit, ROUTE_SHADOW) for unit in (0, 1)}
    elapsed = 0
    while elapsed < phase.duration_ticks:
        updates = _apply_phase_status(chain, phase)
        step = min(DRIVER_STEP_TICKS, phase.duration_ticks - elapsed)
        chain.step_ticks(step)
        elapsed += step
        _apply_phase_status(chain, phase)
    updates = _apply_phase_status(chain, phase)
    for unit in (0, 1):
        traces.append(
            _trace_row(
                chain,
                combo=combo,
                plan=plan,
                phase=phase,
                unit=unit,
                elapsed_ticks=chain.current_tick() - start,
                previous_route=previous_routes[unit],
                driver_update=updates[unit],
            )
        )


def _apply_phase_status(chain: Chain, phase: SourcePhase) -> dict[int, dict[str, Any]]:
    active = {state.receiver: state for state in phase.active_sources}
    updates = {}
    for unit in (0, 1):
        rx_control = chain.read_main_src4382_reg(unit, SRC_REG_RX_CONTROL)
        selected_rx = RX_BY_CONTROL.get(0x08 | (rx_control & 0x03), "RX1")
        state = active.get(selected_rx)
        if state is None:
            rxckr = 0x00
            unlock = UNLOCK_BIT
            non_pcm = 0x00
        else:
            rxckr = state.rxckr & 0x03
            unlock = state.unlock & UNLOCK_BIT
            non_pcm = state.non_pcm & 0xFF
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_STATUS, rxckr)
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_LOCK, unlock)
        chain.poke_main_src4382_reg(unit, SRC_REG_NON_PCM, non_pcm)
        updates[unit] = {
            "selected_rx": selected_rx,
            "active_receivers": sorted(active),
            "rxckr": rxckr,
            "unlock": unlock,
            "non_pcm": non_pcm,
        }
    return updates


def _trace_row(
    chain: Chain,
    *,
    combo: ComboConfig,
    plan: StimulusPlan,
    phase: SourcePhase,
    unit: int,
    elapsed_ticks: int,
    previous_route: int,
    driver_update: dict[str, Any],
) -> dict[str, Any]:
    reg_0d = chain.read_main_src4382_reg(unit, SRC_REG_RX_CONTROL)
    selected_rx = RX_BY_CONTROL.get(0x08 | (reg_0d & 0x03), "RX1")
    candidate_index = int(RX_TABLE[selected_rx]["index"])
    route = chain.read_main_reg(unit, ROUTE_SHADOW)
    expected_live_routes = phase.expected_live_routes or tuple(
        int(RX_TABLE[state.receiver]["route"]) for state in phase.active_sources
    )
    expected_route = phase.expected_route
    tas_payload = chain.read_main_dsp_write_payload(unit, TAS_REG_VOLUME_COEFF)
    wrong_route = _is_wrong_route(route, expected_route, expected_live_routes, previous_route, phase)
    missing = bool(expected_route not in (None, 0) and route != expected_route)
    held_previous = bool(
        phase.allow_previous_hold
        and route != 0
        and route == previous_route
        and route not in expected_live_routes
    )
    handoff_delayed = bool(held_previous and expected_route not in (None, 0))
    intended = bool(plan.schedule_id == "rxckr_nonzero_unlocked" and route == 0)
    muted_pcm = bool(tas_payload == b"\x00\x00\x00\x00" and expected_live_routes)
    notes = [phase.notes] if phase.notes else []
    if handoff_delayed:
        notes.append("held previous route within hard-loss grace")
    if intended:
        notes.append("rejected unlocked RXCKR candidate")
    return {
        "combo_id": combo.combo_id,
        "schedule_id": plan.schedule_id,
        "phase_id": phase.phase_id,
        "elapsed_ticks": elapsed_ticks,
        "unit": f"PB{unit + 1}",
        "active_receivers": [state.receiver for state in phase.active_sources],
        "analog": list(phase.analog),
        "selected_candidate_rx": selected_rx,
        "candidate_index": candidate_index,
        "reg_0d": reg_0d,
        "reg_08": chain.read_main_src4382_reg(unit, SRC_REG_TX_CONTROL_2),
        "reg_13": chain.read_main_src4382_reg(unit, SRC_REG_RX_STATUS),
        "reg_14": chain.read_main_src4382_reg(unit, SRC_REG_RX_LOCK),
        "reg_12": chain.read_main_src4382_reg(unit, SRC_REG_NON_PCM),
        "input_select": chain.read_main_reg(unit, INPUT_SELECT),
        "route_request_0x093": chain.read_main_reg(unit, SRC_ROUTE_REQUEST),
        "route_shadow_0x0ab": route,
        "source_status_0x05f": chain.read_main_reg(unit, SRC_ROUTE_STATUS),
        "event_flags_0x07e": chain.read_main_reg(unit, EVENT_FLAGS),
        "src4382_stats": _stats_subset(chain.read_main_src4382_stats(unit)),
        "src4382_write_values": {
            "0x0D": chain.read_main_src4382_write_values(unit, SRC_REG_RX_CONTROL),
            "0x08": chain.read_main_src4382_write_values(unit, SRC_REG_TX_CONTROL_2),
        },
        "source_driver_update": driver_update,
        "tas30_payload_present": tas_payload is not None,
        "tas30_muted": tas_payload == b"\x00\x00\x00\x00",
        "lcd": list(chain.lcd_lines()),
        "connected": chain.is_connected(),
        "waiting": chain.is_waiting(),
        "detected_route": route,
        "expected_route": expected_route,
        "wrong_route": wrong_route,
        "route_missing_after_budget": missing,
        "pb_divergence": False,
        "muted_pcm": muted_pcm,
        "held_previous_within_hard_loss": held_previous,
        "handoff_delayed_by_hard_loss": handoff_delayed,
        "intended_robustness": intended,
        "notes": notes,
    }


def _is_wrong_route(
    route: int,
    expected_route: int | None,
    live_routes: Sequence[int],
    previous_route: int,
    phase: SourcePhase,
) -> bool:
    if expected_route is not None:
        if route == expected_route:
            return False
        if phase.allow_previous_hold and route == previous_route and route != 0:
            return False
        return expected_route != 0
    if live_routes:
        return route not in (0, *live_routes)
    if phase.allow_previous_hold and route == previous_route:
        return False
    return route not in (0, previous_route)


def _classify_pair(stock: dict[str, Any] | None, current: dict[str, Any]) -> str:
    if (
        stock is not None
        and current.get("wrong_route")
        and stock.get("wrong_route")
        and stock.get("detected_route") == current.get("detected_route")
    ):
        return "needs_human"
    if current.get("wrong_route") or current.get("waiting") or current.get("muted_pcm"):
        return "current_worse"
    if current.get("intended_robustness"):
        return "intended_robustness"
    if current.get("handoff_delayed_by_hard_loss"):
        return "handoff_delayed_by_hard_loss"
    if stock is None:
        return "needs_human"
    if (
        stock.get("detected_route") not in (current.get("detected_route"), None)
        and current.get("expected_route") is None
        and not current.get("active_receivers")
    ):
        return "needs_human"
    return "match"


def _latest_by_key(rows: Sequence[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    latest = {}
    for row in rows:
        latest[(row["schedule_id"], row["phase_id"], row["unit"])] = row
    return latest


def _summary_from_pairs(pairs: Sequence[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for pair in pairs:
        classification = str(pair["classification"])
        summary[classification] = summary.get(classification, 0) + 1
    return summary


def _stimuli_document(plans: Sequence[StimulusPlan]) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "phase_scale": 1.0,
        "timebase": {
            "SIM_TICKS_PER_SECOND": SIM_TICKS_PER_SECOND,
            "DRIVER_STEP_TICKS": DRIVER_STEP_TICKS,
        },
        "plans": [_plan_to_dict(plan) for plan in plans],
    }


def _plan_to_dict(plan: StimulusPlan) -> dict[str, Any]:
    return {
        "schedule_id": plan.schedule_id,
        "setup_mode": plan.setup_mode,
        "description": plan.description,
        "phases": [
            {
                "phase_id": phase.phase_id,
                "duration_ticks": phase.duration_ticks,
                "active_sources": [state.__dict__ for state in phase.active_sources],
                "analog": list(phase.analog),
                "expected_route": phase.expected_route,
                "allow_previous_hold": phase.allow_previous_hold,
                "expected_live_routes": list(phase.expected_live_routes),
                "notes": phase.notes,
            }
            for phase in plan.phases
        ],
    }


def _combo_manifest(combo: ComboConfig) -> dict[str, str]:
    return {
        "description": combo.description,
        "control_hex": _repo_relative(combo.control_hex),
        "control_sha256": _file_sha256(combo.control_hex),
        "main_hex": _repo_relative(combo.main_hex),
        "main_sha256": _file_sha256(combo.main_hex),
    }


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _git_dirty_summary() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        return [f"git status unavailable: {exc}"]
    return proc.stdout.splitlines()


def _stats_subset(stats: dict[str, object]) -> dict[str, Any]:
    return {
        "bytes_acked": stats["bytes_acked"],
        "write_transactions": stats["write_transactions"],
        "read_transactions": stats["read_transactions"],
        "writes_by_subaddr_0d": stats["writes_by_subaddr"][SRC_REG_RX_CONTROL],
        "writes_by_subaddr_08": stats["writes_by_subaddr"][SRC_REG_TX_CONTROL_2],
        "reads_by_subaddr_13": stats["reads_by_subaddr"][SRC_REG_RX_STATUS],
        "reads_by_subaddr_14": stats["reads_by_subaddr"][SRC_REG_RX_LOCK],
    }


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _force_optical_failure(rows: list[dict[str, Any]], units: set[str]) -> None:
    for row in rows:
        if row["schedule_id"] == "fresh_optical" and row["unit"] in units:
            row["detected_route"] = 1
            row["route_shadow_0x0ab"] = 1
            row["wrong_route"] = True
            row["route_missing_after_budget"] = True
            row["notes"] = [*row.get("notes", []), "forced optical failure"]


def _redact_card(card: str) -> str:
    home = str(Path.home())
    card = card.replace(home, "$HOME")
    card = card.replace(str(PROJECT_ROOT), ".")
    for key, value in os.environ.items():
        if value and len(value) > 8:
            card = card.replace(value, f"${key}")
    return card


def _model_prompt(oracle_card: str) -> str:
    return (
        "You are judging a DLCP SRC4382 Auto Detect stock/current trace card.\n"
        "Read only the card below. Do not write files, call tools, access the "
        "network, or mutate the repo. Return only one JSON object with keys "
        "overall, confidence, and findings.\n\n"
        f"{oracle_card}"
    )
