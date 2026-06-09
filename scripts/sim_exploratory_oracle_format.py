#!/usr/bin/env python3
"""Render exploratory chain-sim sessions into agent-readable stimulus->response cards.

`scripts/sim_chain_exploratory.py` drives the rust CONTROL+PB1+PB2 chain with seeded
random stimulus and dumps raw JSONL (events / observations / incidents).  Those files
are faithful but verbose; a human or an LLM "semantic oracle" reasoning about whether
the firmware behaved correctly needs the stimulus paired with the resulting
externally-observable state, with the *changes* between consecutive observations
highlighted.

This tool does that pairing.  It never touches the simulator, so it is cheap and
deterministic: it merges the event stream (stimuli) and the observation stream by
universal tick, then renders one timeline block per observation showing the stimuli
that led to it and the state deltas it produced.

Subcommands:
  index <hunt_dir|run_dir>
      Emit a JSON list of every session found, with quick metadata
      (run_dir, session_id, campaign, seed, n_stimuli, n_obs, connected, final_lcd).

  card <run_dir> --session-id N
      Print one markdown session card to stdout.

  render-all <hunt_dir|run_dir> --out <cards_dir>
      Render every session under the path to `<cards_dir>/<runid>__sNNNN.md` and
      write `<cards_dir>/index.json` describing all rendered cards.  This is the
      input the agent-oracle workflow consumes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


# --- decode tables ----------------------------------------------------------

CONTROL_CONNECTED_MASK = 0x02
CONTROL_MUTE_MASK = 0x20
CONTROL_PRESET_B_MASK = 0x40
MAIN_ACTIVE_PRESET_MASK = 0x04
MAIN_ACTIVE_GATE_MASK = 0x08

IR_CMD_NAMES = {
    # profile-0x04 Hypex codes (current de-masked harness, addr 0x10)
    0x32: "power",
    0x33: "volume_up",
    0x34: "volume_down",
    0x35: "mute",
    0x36: "input_up",
    0x37: "input_down",
    # V1.71 hardcoded inline shortcuts (profile-independent)
    0x38: "preset_a",
    0x39: "preset_b",
    0x3A: "standby",
    0x3B: "wake",
    # legacy synthetic-map codes (pre-2026-06-09 corpus, addr 0x10 + RC-5 codes)
    0x0C: "power(legacy)",
    0x0D: "mute(legacy)",
    0x10: "volume_up(legacy)",
    0x11: "volume_down(legacy)",
    0x20: "input_up(legacy)",
    0x21: "input_down(legacy)",
}

HOST_CMD_NAMES = {
    0x03: "filename/cfg",
    0x06: "input_select",
    0x07: "volume",
    0x20: "preset_switch",
    0x25: "identity",
    0x43: "diag_memread",
    0x44: "diag_snapshot",
}

# Events that set up a session but are not, themselves, a paired stimulus block.
SETUP_ACTIONS = {
    "init",
    "apply_reset_all",
    "apply_reset_all_error",
    "run_until_connected",
    "post_boot_config",
}


# --- jsonl loading ----------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # tolerate a trailing partially-written line when a generator is
                # still appending to this file concurrently
                continue
    return out


def _iter_run_dirs(root: Path) -> list[Path]:
    """A run dir is a directory that holds a manifest.json + events.jsonl."""
    if (root / "manifest.json").exists() and (root / "events.jsonl").exists():
        return [root]
    runs = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "manifest.json").exists():
            runs.append(child)
    return runs


# --- humanization -----------------------------------------------------------

def _stimulus_str(event: dict[str, Any]) -> str:
    action = event["action"]
    params = event.get("params", {})
    result = event.get("result", {})
    ok = result.get("ok", True)
    suffix = "" if ok else "  [ACTION RAISED: %s]" % result.get("error", "?")
    if action == "step":
        ticks = int(params.get("ticks", 0))
        return f"idle-step {ticks/1e6:.1f}M ticks"
    if action == "press":
        return f"button:{params.get('key')}" + suffix
    if action == "ir":
        cmd = int(params.get("cmd", -1)) & 0xFF
        return f"IR:{IR_CMD_NAMES.get(cmd, f'0x{cmd:02X}')}" + suffix
    if action == "host_cmd":
        cmd = int(params.get("cmd", -1)) & 0xFF
        data = int(params.get("data", 0)) & 0xFF
        name = HOST_CMD_NAMES.get(cmd, f"0x{cmd:02X}")
        return f"host:{name}(data=0x{data:02X},route=0x{int(params.get('route',0xBF)):02X})" + suffix
    if action in ("hid_filename_write",):
        return f"USB:filename_write(unit={params.get('unit')}, name={params.get('name')!r})" + suffix
    if action in ("hid_filename_read",):
        return f"USB:filename_read(unit={params.get('unit')})" + suffix
    if action == "src_nack":
        return f"fault:SRC4382_nack(unit={params.get('unit')}, phase={params.get('phase')}, n={params.get('count')})" + suffix
    if action == "tas_nack":
        return f"fault:TAS3108_nack(unit={params.get('unit')}, phase={params.get('phase')}, n={params.get('count')})" + suffix
    if action == "src_reg":
        return f"setup:SRC4382_reg(unit={params.get('unit')}, reg=0x{int(params.get('reg',0)):02X}, val=0x{int(params.get('value',0)):02X})" + suffix
    if action == "mssp_stop":
        return f"fault:MSSP_stop_stuck(unit={params.get('unit')}, cycles={params.get('cycles')}, n={params.get('count')})" + suffix
    if action == "line_hold":
        return f"fault:I2C_line_hold(scl_low={params.get('scl_low')}, sda_low={params.get('sda_low')})" + suffix
    if action == "link_drop":
        return f"fault:UART_link_drop({params.get('link')})" + suffix
    if action == "blackout":
        return f"fault:blackout({int(params.get('fault_ticks',0))/1e6:.1f}M ticks) then reconnect" + suffix
    if action == "reset_main":
        return f"fault:reset_PB{int(params.get('unit',0))+1}(source={params.get('source')})" + suffix
    if action == "reset_all":
        return f"fault:reset_all(source={params.get('source')})" + suffix
    if action == "raw_main_bytes":
        raw = params.get("bytes", [])
        return f"synthetic:raw_uart_bytes(unit={params.get('unit')}, n={len(raw)})" + suffix
    if action == "triplet":
        return f"chain_frame:[route=0x{int(params.get('route',0xBF)):02X}, cmd=0x{int(params.get('cmd',0)):02X}, data=0x{int(params.get('data',0)):02X}]" + suffix
    if action == "an0":
        return f"electrical:AN0_sample(unit={params.get('unit')}, value=0x{int(params.get('value',0)):04X})" + suffix
    if action == "ra1_edge":
        return f"electrical:RA1_edge(unit={params.get('unit')}, level={params.get('level')})" + suffix
    return f"{action}({params})" + suffix


# --- state vector extraction ------------------------------------------------

def _nonzero(d: dict[str, Any]) -> dict[str, int]:
    return {k: int(v) for k, v in d.items() if int(v)}


def _state_vector(obs: dict[str, Any]) -> dict[str, Any]:
    ctl = obs["control"]
    flags = int(ctl["flags"])
    sv: dict[str, Any] = {
        "lcd0": obs["lcd"][0],
        "lcd1": obs["lcd"][1],
        "connected": bool(obs["is_connected"]),
        "waiting": bool(obs["is_waiting"]),
        "disp_state": int(ctl["display_state"]),
        "vol": int(ctl["volume"]),
        "input": int(ctl["input"]),
        "ctl_mute": bool(flags & CONTROL_MUTE_MASK),
        "ctl_presetB": bool(flags & CONTROL_PRESET_B_MASK),
        "diag_present": int(ctl.get("diag_present", 0)),
        "fname_flags": int(ctl["fname"]["flags"]),
        "fname_len": int(ctl["fname"]["len"]),
        "fname_explen": int(ctl["fname"]["expected_len"]),
        "fname_id": int(ctl["fname"]["id"]),
        "fname_cache": ctl["fname"]["cache"],
        "diag_pb1": list(ctl.get("diag_pb1", [])),
        "diag_pb2": list(ctl.get("diag_pb2", [])),
    }
    for idx, m in enumerate(obs["main"]):
        tag = f"PB{idx+1}"
        tas = m.get("tas_stats", {}) or {}
        src = m.get("src_stats", {}) or {}
        sv[f"{tag}_gate"] = int(m["active_gate"])
        sv[f"{tag}_preset"] = int(m["active_preset"])
        sv[f"{tag}_job"] = int(m["preset_job_state"])
        sv[f"{tag}_job_target"] = int(m.get("preset_job_target", 0))
        sv[f"{tag}_diag"] = _nonzero(m["diag"])
        sv[f"{tag}_reset"] = _nonzero(m["reset"])
        sv[f"{tag}_fname"] = m["filename_ram"]
        sv[f"{tag}_tas_ack"] = int(tas.get("bytes_acked", 0))
        sv[f"{tag}_tas_nack"] = int(tas.get("bytes_nacked", 0))
        sv[f"{tag}_src_wr"] = int(src.get("write_transactions", 0))
        sv[f"{tag}_src_rd"] = int(src.get("read_transactions", 0))
        # enriched MAIN state (mute/volume/route/event/fault) — only present in
        # corpus generated after the 2026-06-09 capture enrichment.
        sv[f"{tag}_mute_latch"] = int(m.get("mute_latch", 0))
        sv[f"{tag}_event_flags"] = int(m.get("event_flags", 0))
        sv[f"{tag}_dsp_fault"] = int(m.get("dsp_fault_flags", 0))
        sv[f"{tag}_logical_vol"] = int(m.get("logical_volume", 0))
        sv[f"{tag}_computed_vol"] = int(m.get("computed_volume", 0))
        sv[f"{tag}_input"] = int(m.get("input_select", 0))
        sv[f"{tag}_input_mirror"] = int(m.get("input_mirror", 0))
        sv[f"{tag}_tas30"] = m.get("tas30_last_write", "")
        sv[f"{tag}_tas30_count"] = int(m.get("tas30_write_count", 0))
        # actual preset-coefficient fingerprint (biquad range 0x37..0x90)
        sv[f"{tag}_dsp_digest"] = m.get("dsp_biquad_digest", "")
        sv[f"{tag}_dsp_full"] = m.get("dsp_full_digest", "")
    return sv


# Fields whose cumulative deltas matter (counters); rendered as Δ.
_COUNTER_FIELDS = {
    "PB1_tas_ack", "PB2_tas_ack", "PB1_tas_nack", "PB2_tas_nack",
    "PB1_src_wr", "PB2_src_wr", "PB1_src_rd", "PB2_src_rd",
    "PB1_tas30_count", "PB2_tas30_count",
}


def _fmt_value(field: str, value: Any) -> str:
    if field in ("vol",):
        return f"0x{int(value):02X}"
    if field in ("fname_flags",):
        return f"0x{int(value):02X}"
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _diff(prev: dict[str, Any] | None, cur: dict[str, Any]) -> list[str]:
    if prev is None:
        return []
    changes: list[str] = []
    for k, v in cur.items():
        pv = prev.get(k)
        if pv == v:
            continue
        if k in _COUNTER_FIELDS:
            delta = int(v) - int(pv or 0)
            if delta:
                changes.append(f"{k} +{delta}" if delta > 0 else f"{k} {delta}")
        else:
            changes.append(f"{k}: {_fmt_value(k, pv)}→{_fmt_value(k, v)}")
    return changes


# --- timeline merge ---------------------------------------------------------

def _event_tick(event: dict[str, Any], carry: int) -> int:
    res = event.get("result", {})
    if isinstance(res, dict) and isinstance(res.get("tick"), int):
        return int(res["tick"])
    return carry


def _session_timeline(
    events: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    session_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sess_events = [e for e in events if int(e["session_id"]) == session_id]
    sess_events.sort(key=lambda e: int(e["event_id"]))
    sess_obs = [o for o in observations if int(o["session_id"]) == session_id]
    # observations.jsonl preserves write order, which is tick-monotonic per session
    return sess_events, sess_obs


def _merge(
    sess_events: list[dict[str, Any]],
    sess_obs: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    timeline: list[tuple[int, int, int, str, dict[str, Any]]] = []
    carry = 0
    for e in sess_events:
        t = _event_tick(e, carry)
        carry = t
        # event sorts before an observation sharing its tick (kind=0)
        timeline.append((t, 0, int(e["event_id"]), "event", e))
    for seq, o in enumerate(sess_obs):
        timeline.append((int(o["tick"]), 1, seq, "obs", o))
    timeline.sort(key=lambda x: (x[0], x[1], x[2]))
    return [(kind, payload) for (_t, _k, _s, kind, payload) in timeline]


# --- card rendering ---------------------------------------------------------

def _setup_summary(sess_events: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    init = next((e for e in sess_events if e["action"] == "init"), None)
    if init:
        p = init["params"]
        lines.append(
            f"- initial conditions: active_preset={p.get('active_preset')} "
            f"reset_source={p.get('reset_source')} src_initial={p.get('src_initial')}"
        )
        lines.append(
            f"- PB1 slots: A={p.get('slot_a_pb1')!r} B={p.get('slot_b_pb1')!r}  |  "
            f"PB2 slots: A={p.get('slot_a_pb2')!r} B={p.get('slot_b_pb2')!r}"
        )
    ruc = next((e for e in sess_events if e["action"] == "run_until_connected"), None)
    if ruc:
        r = ruc.get("result", {})
        lines.append(
            f"- boot: connected={r.get('connected')} chunks={r.get('chunks')} "
            f"lcd={r.get('lcd')}"
        )
    return lines


def render_card(run_dir: Path, session_id: int) -> str:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    events = _load_jsonl(run_dir / "events.jsonl")
    observations = _load_jsonl(run_dir / "observations.jsonl")
    incidents = _load_jsonl(run_dir / "incidents.jsonl")
    sess_events, sess_obs = _session_timeline(events, observations, session_id)
    if not sess_events:
        raise SystemExit(f"no events for session {session_id} in {run_dir}")
    campaign = next(
        (e["params"].get("campaign") for e in sess_events if e["action"] == "init"),
        "?",
    )

    out: list[str] = []
    out.append(f"# Exploratory session card — {run_dir.name} / session {session_id}")
    out.append("")
    out.append(f"- campaign: `{campaign}`")
    out.append(f"- seed: `{manifest.get('seed')}`")
    out.append(f"- CONTROL: `{Path(manifest['control_hex']).name}`  MAIN: `{Path(manifest['main_hex']).name}`")
    out.extend(_setup_summary(sess_events))
    sess_incidents = [i for i in incidents if int(i.get("session_id", -1)) == session_id]
    if sess_incidents:
        out.append(f"- harness rule-oracle incidents this session: {len(sess_incidents)}")
        for inc in sess_incidents:
            out.append(f"    - [{inc.get('severity')}] {inc.get('oracle')}: {inc.get('symptom')}")
    out.append("")
    out.append("## Timeline (stimulus → resulting observable state)")
    out.append("")
    out.append(
        "Legend: PBn=MAIN unit n (PB1=MAIN0, PB2=MAIN2). gate=active/awake, "
        "preset=active slot(0=A,1=B), job=preset_job_state, diag=nonzero diag counters "
        "(I,D,S,B,R,A,P), reset=nonzero reset-cause flags (O,V,W,X). tas_ack/src_wr are "
        "cumulative I2C counters shown as deltas. vol/input/disp_state are raw CONTROL "
        "cache bytes; the LCD rows are the ground-truth user-visible text."
    )
    out.append("")

    merged = _merge(sess_events, sess_obs)
    pending: list[str] = []
    prev_sv: dict[str, Any] | None = None
    block = 0
    prev_tick = 0
    for kind, payload in merged:
        if kind == "event":
            action = payload["action"]
            if action in SETUP_ACTIONS:
                continue
            pending.append(_stimulus_str(payload))
            continue
        # observation
        block += 1
        sv = _state_vector(payload)
        tick = int(payload["tick"])
        dtick = tick - prev_tick
        prev_tick = tick
        out.append(f"### obs #{block}  (tick={tick}, Δ={dtick/1e6:.1f}M)")
        if pending:
            out.append(f"- stimuli: {' ; '.join(pending)}")
        else:
            out.append("- stimuli: (none — settle/observe only)")
        out.append(f"- LCD: [{sv['lcd0']!r}, {sv['lcd1']!r}]")
        out.append(
            f"- CTL: conn={int(sv['connected'])} wait={int(sv['waiting'])} "
            f"disp={sv['disp_state']} vol=0x{sv['vol']:02X} input={sv['input']} "
            f"mute={int(sv['ctl_mute'])} presetB={int(sv['ctl_presetB'])} "
            f"diag_present={sv['diag_present']}"
        )
        if sv["fname_flags"] or sv["fname_cache"]:
            out.append(
                f"- CTL.filename: flags=0x{sv['fname_flags']:02X} len={sv['fname_len']} "
                f"explen={sv['fname_explen']} id={sv['fname_id']} cache={sv['fname_cache']!r}"
            )
        for tag in ("PB1", "PB2"):
            out.append(
                f"- {tag}: gate={sv[f'{tag}_gate']} preset={sv[f'{tag}_preset']} "
                f"job={sv[f'{tag}_job']} jobtgt={sv[f'{tag}_job_target']} "
                f"diag={sv[f'{tag}_diag']} reset={sv[f'{tag}_reset']} "
                f"fname={sv[f'{tag}_fname']!r}"
            )
            out.append(
                f"- {tag}.audio: mute_latch=0x{sv[f'{tag}_mute_latch']:02X} "
                f"event_flags=0x{sv[f'{tag}_event_flags']:02X} "
                f"dsp_fault=0x{sv[f'{tag}_dsp_fault']:02X} "
                f"logical_vol=0x{sv[f'{tag}_logical_vol']:02X} "
                f"computed_vol=0x{sv[f'{tag}_computed_vol']:02X} "
                f"input={sv[f'{tag}_input']}/mirror={sv[f'{tag}_input_mirror']} "
                f"tas30={sv[f'{tag}_tas30'] or '--'}(n={sv[f'{tag}_tas30_count']})"
                + (f" dsp_coeff={sv.get(f'{tag}_dsp_digest', '--')}" if sv.get(f'{tag}_dsp_digest') else "")
            )
        changes = _diff(prev_sv, sv)
        if changes:
            out.append(f"- Δ since prev: {', '.join(changes)}")
        prev_sv = sv
        pending = []
        out.append("")

    out.append("## Notes for the oracle")
    out.append(
        "- This is simulated externally-observable state, not source. Judge whether the "
        "firmware's response to each stimulus is correct per the oracle rubric in "
        "`docs/SIM_CHAIN_EXPLORATORY_STRESS_SPEC.md` (§Oracles and Bug Classifiers)."
    )
    out.append(
        "- Distinguish real firmware bugs from harness artifacts using that spec's "
        "§\"Bug vs Harness Artifact Checklist\". Synthetic stimuli (raw_uart_bytes, "
        "impossible chain frames, line holds) are lower priority unless they durably "
        "lock the UI/audio or corrupt persistent state."
    )
    out.append(
        "- The `PBn slots: A=.. B=..` line in the header is the PRESET FILENAME content "
        "seeded into each MAIN's preset-A/preset-B EEPROM slots before boot. These come "
        "from an arbitrary test-string pool that INCLUDES input-sounding names (e.g. "
        "'USB Audio', 'RCA SPDIF') and deliberately malformed bytes (e.g. 'bad\\x01name'). "
        "A `PBn fname=` value that matches the active preset's seeded slot is CORRECT "
        "firmware behavior — it is the firmware echoing stored preset-name bytes, NOT a "
        "preset/input conflation. Only flag a filename that does NOT match the seeded slot "
        "for the active preset (wrong slot, stale after a slot change, truncated, or "
        "corrupted beyond the injected bytes)."
    )
    return "\n".join(out) + "\n"


def _session_ids(run_dir: Path) -> list[int]:
    events = _load_jsonl(run_dir / "events.jsonl")
    return sorted({int(e["session_id"]) for e in events})


def _triage_run(run_dir: Path) -> list[dict[str, Any]]:
    """Triage every session in a run, loading the run's JSONL only once."""
    events = _load_jsonl(run_dir / "events.jsonl")
    observations = _load_jsonl(run_dir / "observations.jsonl")
    sids = sorted({int(e["session_id"]) for e in events})
    out: list[dict[str, Any]] = []
    for sid in sids:
        try:
            out.append(_triage_session(run_dir, sid, events=events, observations=observations))
        except Exception as exc:  # keep batch robust against a bad session
            out.append({"run_dir": str(run_dir), "session_id": sid, "error": repr(exc), "score": -1})
    return out


def _session_meta(
    run_dir: Path,
    session_id: int,
    events: list[dict[str, Any]] | None = None,
    observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if events is None:
        events = _load_jsonl(run_dir / "events.jsonl")
    if observations is None:
        observations = _load_jsonl(run_dir / "observations.jsonl")
    sess_events = [e for e in events if int(e["session_id"]) == session_id]
    sess_obs = [o for o in observations if int(o["session_id"]) == session_id]
    init = next((e for e in sess_events if e["action"] == "init"), None)
    ruc = next((e for e in sess_events if e["action"] == "run_until_connected"), None)
    n_stim = sum(
        1 for e in sess_events if e["action"] not in SETUP_ACTIONS and e["action"] != "step"
    )
    final_lcd = sess_obs[-1]["lcd"] if sess_obs else (ruc.get("result", {}).get("lcd") if ruc else None)
    return {
        "run_dir": str(run_dir),
        "run_id": run_dir.name,
        "session_id": session_id,
        "campaign": init["params"].get("campaign") if init else "?",
        "seed": init["params"].get("seed") if init else None,
        "n_stimuli": n_stim,
        "n_obs": len(sess_obs),
        "connected": (ruc.get("result", {}).get("connected") if ruc else None),
        "final_lcd": final_lcd,
    }


def _printable(text: str) -> bool:
    return all(ch == " " or 0x20 <= ord(ch) < 0x7F for ch in text)


def _triage_session(
    run_dir: Path,
    session_id: int,
    events: list[dict[str, Any]] | None = None,
    observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Mechanical interestingness signals for one session.

    These do NOT decide bug-vs-not (that is the agent oracle's job); they only
    order the queue so the semantic oracle looks at the most divergent state
    windows first.  Persistence-to-final-observation is weighted far above a
    one-shot transient, because a PB1!=PB2 mismatch *during* a preset apply is
    expected and only a mismatch that survives the settle window is suspicious.

    Pass preloaded `events`/`observations` to avoid re-reading the run's JSONL
    once per session (use `_triage_run` for whole-run batches).
    """
    if events is None:
        events = _load_jsonl(run_dir / "events.jsonl")
    if observations is None:
        observations = _load_jsonl(run_dir / "observations.jsonl")
    sess_obs = [o for o in observations if int(o["session_id"]) == session_id]
    svs = [_state_vector(o) for o in sess_obs]
    signals: dict[str, Any] = {
        "preset_mismatch_obs": 0,
        "gate_mismatch_obs": 0,
        "ui_main_preset_mismatch_obs": 0,
        "lcd_nonprintable_obs": 0,
        "waiting_connected_obs": 0,
        "diag_saturated": False,
        "fname_valid_len_mismatch_obs": 0,
        "final_job_stuck": False,
        "final_preset_mismatch": False,
        "final_gate_mismatch": False,
        "final_ui_main_mismatch": False,
        "final_not_connected": False,
        "lcd_idle_streak": 0,
        # ACTUAL DSP preset-coefficient oracle signals (only populated for
        # corpus generated after the 2026-06-09 coeff-digest enrichment).
        "cross_pb_coeff_desync_obs": 0,
        "final_cross_pb_coeff_desync": False,
        "preset_coeff_collision": False,   # preset A and B map to SAME coeffs
        "preset_coeff_unstable": False,    # one preset maps to >1 coeff image
    }
    # per-unit map: active preset bit -> set of settled biquad digests seen
    preset_digests: dict[int, dict[int, set[str]]] = {0: {}, 1: {}}
    last_lcd: tuple[str, str] | None = None
    idle = 0
    for sv in svs:
        if sv["PB1_gate"] and sv["PB2_gate"] and sv["PB1_preset"] != sv["PB2_preset"]:
            signals["preset_mismatch_obs"] += 1
        # cross-PB coefficient desync: both awake, SAME active preset, but the
        # actual biquad coefficient images differ -> one MAIN has wrong/stale
        # coeffs even though the preset flags agree.
        d1, d2 = sv.get("PB1_dsp_digest", ""), sv.get("PB2_dsp_digest", "")
        if (
            sv["PB1_gate"] and sv["PB2_gate"]
            and sv["PB1_preset"] == sv["PB2_preset"]
            and d1 and d2 and d1 != d2
        ):
            signals["cross_pb_coeff_desync_obs"] += 1
        # learn each unit's settled preset->coeff mapping (job idle = settled)
        for u, tag in ((0, "PB1"), (1, "PB2")):
            dg = sv.get(f"{tag}_dsp_digest", "")
            if dg and sv[f"{tag}_gate"] and sv[f"{tag}_job"] == 0:
                preset_digests[u].setdefault(sv[f"{tag}_preset"], set()).add(dg)
        if sv["PB1_gate"] != sv["PB2_gate"]:
            signals["gate_mismatch_obs"] += 1
        # CONTROL believes presetB, but PB1 active preset disagrees (UI vs MAIN)
        if int(sv["ctl_presetB"]) != int(sv["PB1_preset"]):
            signals["ui_main_preset_mismatch_obs"] += 1
        if not (_printable(sv["lcd0"]) and _printable(sv["lcd1"])):
            signals["lcd_nonprintable_obs"] += 1
        if sv["waiting"] and sv["connected"]:
            signals["waiting_connected_obs"] += 1
        for tag in ("PB1", "PB2"):
            if any(int(v) == 0x0F for v in sv[f"{tag}_diag"].values()):
                signals["diag_saturated"] = True
        if (sv["fname_flags"] & 0x01) and sv["fname_len"] != sv["fname_explen"]:
            signals["fname_valid_len_mismatch_obs"] += 1
        cur_lcd = (sv["lcd0"], sv["lcd1"])
        if cur_lcd == last_lcd:
            idle += 1
            signals["lcd_idle_streak"] = max(signals["lcd_idle_streak"], idle)
        else:
            idle = 0
        last_lcd = cur_lcd
    if svs:
        last = svs[-1]
        signals["final_job_stuck"] = bool(last["PB1_job"] or last["PB2_job"])
        signals["final_preset_mismatch"] = bool(
            last["PB1_gate"] and last["PB2_gate"] and last["PB1_preset"] != last["PB2_preset"]
        )
        signals["final_gate_mismatch"] = bool(last["PB1_gate"] != last["PB2_gate"])
        signals["final_ui_main_mismatch"] = bool(int(last["ctl_presetB"]) != int(last["PB1_preset"]))
        signals["final_not_connected"] = not bool(last["connected"])
        ld1, ld2 = last.get("PB1_dsp_digest", ""), last.get("PB2_dsp_digest", "")
        signals["final_cross_pb_coeff_desync"] = bool(
            last["PB1_gate"] and last["PB2_gate"]
            and last["PB1_preset"] == last["PB2_preset"]
            and ld1 and ld2 and ld1 != ld2
        )
    for u in (0, 1):
        per_preset = preset_digests[u]
        if any(len(digs) > 1 for digs in per_preset.values()):
            signals["preset_coeff_unstable"] = True
        if 0 in per_preset and 1 in per_preset and (per_preset[0] & per_preset[1]):
            signals["preset_coeff_collision"] = True
    score = (
        20 * int(signals["final_preset_mismatch"])
        + 18 * int(signals["final_gate_mismatch"])
        + 15 * int(signals["final_ui_main_mismatch"])
        + 14 * int(signals["final_job_stuck"])
        + 25 * int(signals["final_not_connected"])
        + 12 * min(signals["lcd_nonprintable_obs"], 5)
        + 10 * min(signals["waiting_connected_obs"], 5)
        + 8 * int(signals["diag_saturated"])
        + 6 * min(signals["fname_valid_len_mismatch_obs"], 5)
        + 2 * min(signals["preset_mismatch_obs"], 8)
        + 2 * min(signals["gate_mismatch_obs"], 8)
        + 1 * min(signals["ui_main_preset_mismatch_obs"], 8)
        + (5 if signals["lcd_idle_streak"] >= 8 else 0)
        + 24 * int(signals["final_cross_pb_coeff_desync"])
        + 18 * int(signals["preset_coeff_collision"])
        + 14 * int(signals["preset_coeff_unstable"])
        + 3 * min(signals["cross_pb_coeff_desync_obs"], 8)
    )
    # synthetic-fault load: count deliberately-corrupting stimuli in the session.
    # Divergence accompanied by these is usually the injected fault surfacing
    # correctly; divergence with ZERO synthetic load is the real prize.
    synthetic_actions = {
        "src_nack", "tas_nack", "mssp_stop", "line_hold", "raw_main_bytes", "link_drop",
    }
    sess_events = [e for e in events if int(e["session_id"]) == session_id]
    synthetic_fault_load = sum(1 for e in sess_events if e.get("action") in synthetic_actions)
    # realistic divergence score: same divergence signals, but EXCLUDING the
    # fault-driven ones (diag_saturated) since those need injected NACKs to reach.
    realistic_score = (
        20 * int(signals["final_preset_mismatch"])
        + 18 * int(signals["final_ui_main_mismatch"])
        + 16 * int(signals["final_job_stuck"])
        + 12 * int(signals["final_gate_mismatch"])
        + 10 * int(signals["final_not_connected"])
        + 3 * min(signals["waiting_connected_obs"], 5)
        + 4 * min(signals["lcd_nonprintable_obs"], 3)
        + 2 * min(signals["preset_mismatch_obs"], 6)
        + 1 * min(signals["ui_main_preset_mismatch_obs"], 6)
        + (4 if signals["lcd_idle_streak"] >= 8 else 0)
        + 24 * int(signals["final_cross_pb_coeff_desync"])
        + 18 * int(signals["preset_coeff_collision"])
        + 14 * int(signals["preset_coeff_unstable"])
        + 3 * min(signals["cross_pb_coeff_desync_obs"], 6)
    )
    signals["synthetic_fault_load"] = synthetic_fault_load
    meta = _session_meta(run_dir, session_id, events=events, observations=observations)
    meta["signals"] = signals
    meta["score"] = score
    meta["realistic_score"] = realistic_score
    meta["synthetic_fault_load"] = synthetic_fault_load
    return meta


def cmd_triage(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    rows: list[dict[str, Any]] = []
    for run_dir in _iter_run_dirs(root):
        rows.extend(_triage_run(run_dir))
    rows.sort(key=lambda r: r.get("score", -1), reverse=True)
    json.dump(rows, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    rows: list[dict[str, Any]] = []
    for run_dir in _iter_run_dirs(root):
        for sid in _session_ids(run_dir):
            rows.append(_session_meta(run_dir, sid))
    json.dump(rows, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_card(args: argparse.Namespace) -> int:
    sys.stdout.write(render_card(Path(args.run_dir).resolve(), args.session_id))
    return 0


def cmd_render_all(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, Any]] = []
    for run_dir in _iter_run_dirs(root):
        for sid in _session_ids(run_dir):
            meta = _session_meta(run_dir, sid)
            if args.min_stimuli and meta["n_stimuli"] < args.min_stimuli:
                continue
            card_name = f"{run_dir.name}__s{sid:04d}.md"
            card_path = out_dir / card_name
            try:
                card_path.write_text(render_card(run_dir, sid), encoding="utf-8")
            except SystemExit:
                continue
            meta["card"] = str(card_path)
            meta["card_name"] = card_name
            index.append(meta)
    (out_dir / "index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    print(f"rendered {len(index)} cards into {out_dir}", file=sys.stderr)
    print(str(out_dir / "index.json"))
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_index = sub.add_parser("index", help="list sessions as JSON")
    p_index.add_argument("path")
    p_index.set_defaults(func=cmd_index)

    p_triage = sub.add_parser("triage", help="rank sessions by mechanical interestingness")
    p_triage.add_argument("path")
    p_triage.set_defaults(func=cmd_triage)

    p_card = sub.add_parser("card", help="render one session card")
    p_card.add_argument("run_dir")
    p_card.add_argument("--session-id", type=int, required=True)
    p_card.set_defaults(func=cmd_card)

    p_all = sub.add_parser("render-all", help="render all session cards to files")
    p_all.add_argument("path")
    p_all.add_argument("--out", required=True)
    p_all.add_argument("--min-stimuli", type=int, default=3)
    p_all.set_defaults(func=cmd_render_all)

    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
