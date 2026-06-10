"""Focused tests for the exploratory card formatter's timeline merge.

The merge must preserve causal write order per stream and keep the
stimulus->observation pairing sane on BOTH kinds of corpora:

- monotonic corpora (post clock-fix): identical to a plain tick sort;
- pre-clock-fix corpora whose universal clock rewound at mid-session resets:
  epoch-aware sorting must keep post-rewind stimuli AFTER pre-rewind
  observations even when the raw ticks tie or invert.
"""

from __future__ import annotations

import importlib.util
import sys

from dlcp_fw.paths import SCRIPTS_DIR

_spec = importlib.util.spec_from_file_location(
    "sim_exploratory_oracle_format", SCRIPTS_DIR / "sim_exploratory_oracle_format.py"
)
_fmt = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules.setdefault("sim_exploratory_oracle_format", _fmt)
_spec.loader.exec_module(_fmt)


def _event(event_id: int, tick: int) -> dict:
    return {
        "session_id": 1,
        "event_id": event_id,
        "action": f"act{event_id}",
        "params": {},
        "result": {"tick": tick},
    }


def _obs(tick: int) -> dict:
    return {"session_id": 1, "tick": tick}


def _shape(merged) -> list[tuple[str, int]]:
    out = []
    for kind, payload in merged:
        ident = payload["event_id"] if kind == "event" else payload["tick"]
        out.append((kind, int(ident)))
    return out


def test_merge_monotonic_corpus_matches_plain_tick_sort() -> None:
    events = [_event(1, 10), _event(2, 30), _event(3, 50)]
    obs = [_obs(20), _obs(40), _obs(60)]
    assert _shape(_fmt._merge(events, obs)) == [
        ("event", 1),
        ("obs", 20),
        ("event", 2),
        ("obs", 40),
        ("event", 3),
        ("obs", 60),
    ]


def test_merge_event_before_observation_at_equal_tick() -> None:
    events = [_event(1, 20)]
    obs = [_obs(20)]
    assert _shape(_fmt._merge(events, obs)) == [("event", 1), ("obs", 20)]


def test_merge_rewound_corpus_keeps_post_rewind_stimuli_after_pre_rewind_obs() -> None:
    # The reset rewinds both streams: event@100/obs@100 are epoch 0; the
    # post-reset event@20/obs@20 are epoch 1.  A monotonized-tick-only merge
    # collapsed all four onto tick 100 and (events-first at equal ticks) put
    # the post-rewind stimulus on the PRE-rewind observation block.
    events = [_event(1, 100), _event(2, 20)]
    obs = [_obs(100), _obs(20)]
    assert _shape(_fmt._merge(events, obs)) == [
        ("event", 1),
        ("obs", 100),
        ("event", 2),
        ("obs", 20),
    ]


def test_merge_preserves_causal_order_within_each_stream_across_rewinds() -> None:
    events = [_event(1, 90), _event(2, 110), _event(3, 15), _event(4, 35)]
    obs = [_obs(95), _obs(120), _obs(25), _obs(40)]
    merged = _shape(_fmt._merge(events, obs))
    assert [i for kind, i in merged if kind == "event"] == [1, 2, 3, 4]
    assert [i for kind, i in merged if kind == "obs"] == [95, 120, 25, 40]
    # Epoch boundary honored: everything from epoch 1 sorts after epoch 0.
    assert merged.index(("event", 3)) > merged.index(("obs", 120))


def test_session_timeline_reports_rewind_count() -> None:
    events = [_event(1, 100)]
    obs = [_obs(100), _obs(20), _obs(30), _obs(10)]
    _ev, _ob, rewinds = _fmt._session_timeline(events, obs, 1)
    assert rewinds == 2
