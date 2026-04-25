"""Ground-truth capture for the dlcp-sim Rust rewrite (Phase 0).

A `StimulusRecorder` writes a JSONL stream of every external event
the test pushes into the simulated chain — button presses, blackout
toggles, fault injections, host-command frames — so a future Rust
engine can replay the same stimulus and be diffed against the
captured outputs (UART byte streams, LCD raster, EEPROM, RAM).

The recorder is bound to the test in scope via a `ContextVar`.  The
chain-harness mutator methods call `get_active_recorder()` and, if
non-None, append an event tuple to the recorder's stream.  Tests
themselves require zero rewrites — the conftest plugin sets the
recorder at test entry and tears it down at teardown.

Event schema (one JSON object per line, schema_version=1):

    {
        "seq": <int>,                # 0-based sequence within run
        "wall_time": <float>,        # time.time() at injection
        "kind": <str>,               # eg "press", "set_blackout"
        "harness": <str>,            # "single_main_chain", ...
        "payload": <dict>,           # kind-specific arguments
    }

The `tick` field listed in spec §4 is intentionally omitted in
P0.2; the existing harnesses don't expose a uniform universal-clock
counter (CONTROL and MAIN have separate per-core PIC cycle counters
and the 48 MHz universal tick is a Phase-3 concept).  A
forward-compatible "tick" field is reserved for P0.5/Phase-3 to fill
in once the multi-core clock domain is wired.
"""

from __future__ import annotations

import contextvars
import json
import time
from pathlib import Path
from types import TracebackType
from typing import Any

__all__ = ["StimulusRecorder", "get_active_recorder", "record_event"]


_active_recorder: contextvars.ContextVar["StimulusRecorder | None"] = (
    contextvars.ContextVar("dlcp_sim_active_recorder", default=None)
)


SCHEMA_VERSION = 1


class StimulusRecorder:
    """Append-only JSONL writer for ground-truth stimulus events.

    Use as a context manager:

        with StimulusRecorder(out_dir / "stimulus.jsonl") as rec:
            ... # tests run, harness mutators write through rec

    Re-entrancy / nested recorders are NOT supported: the active
    recorder is a single `ContextVar` slot and entering a second
    recorder while the first is live raises.
    """

    def __init__(self, out_path: Path) -> None:
        # File creation is deferred to __enter__ so that a re-entrancy
        # check that fails (another recorder already active) doesn't
        # leave a truncated file behind on disk for the user to wonder
        # about.
        self.out_path = Path(out_path)
        self._fp = None
        self._seq = 0
        self._token: contextvars.Token | None = None
        self._closed = False

    def __enter__(self) -> "StimulusRecorder":
        if _active_recorder.get() is not None:
            raise RuntimeError(
                "another StimulusRecorder is already active; "
                "nested capture is not supported"
            )
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.out_path.open("w", encoding="utf-8")
        self._token = _active_recorder.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if self._token is not None:
                _active_recorder.reset(self._token)
                self._token = None
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._fp is None:
            return
        try:
            self._fp.flush()
        finally:
            self._fp.close()

    def record(self, *, kind: str, harness: str, payload: dict[str, Any] | None = None) -> None:
        """Append one event to the JSONL stream and flush.

        Flushing on every event is deliberate: a test that crashes
        mid-run leaves a usable partial stream, which is what we
        want for post-mortem replay.
        """
        if self._closed or self._fp is None:
            return
        event: dict[str, Any] = {
            "seq": self._seq,
            "wall_time": time.time(),
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "harness": harness,
            "payload": payload or {},
        }
        self._fp.write(json.dumps(event, sort_keys=True) + "\n")
        self._fp.flush()
        self._seq += 1


def get_active_recorder() -> StimulusRecorder | None:
    """Return the recorder bound to the current test, or None."""
    return _active_recorder.get()


def record_event(*, kind: str, harness: str, payload: dict[str, Any] | None = None) -> None:
    """Record `kind` to the active recorder, if any.  No-op otherwise.

    This is the shim chain-harness mutators call; the cost when
    capture is off is one ContextVar read + one None comparison.
    """
    rec = _active_recorder.get()
    if rec is not None:
        rec.record(kind=kind, harness=harness, payload=payload)
