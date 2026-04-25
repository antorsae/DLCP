"""Ground-truth capture for the dlcp-sim Rust rewrite (Phase 0).

A per-test `GroundTruthContext` bundles two artefact streams:

  * `StimulusRecorder` — JSONL of every external event the test
    pushes into the simulated chain (presses, blackout toggles,
    fault injections, host-command frames), one event per line.
  * `SnapshotTaker` — binary RAM dump + JSON SFR map written to
    `snapshots/<seq>.<phase>.<harness_id>.{ram.bin,sfr.json}`
    at the start of the test, after each recorded mutator event,
    and at the end of the test.

A future Rust engine can replay the stimulus from JSONL and be
diffed against the snapshots at the same boundaries.

The context is bound to the test in scope via a `ContextVar`.  The
chain-harness mutator methods call `record_event(...)` (and
optionally `snapshot_after_event(...)`) which look up the active
context and no-op when capture is off.  Tests themselves require
zero rewrites — the conftest plugin sets the context at test entry
and tears it down at teardown.

Event schema (one JSON object per line, schema_version=1):

    {
        "seq": <int>,                # 0-based sequence within run
        "wall_time": <float>,        # time.time() at injection
        "kind": <str>,               # eg "press", "set_blackout"
        "harness": <str>,            # "single_main_chain", ...
        "payload": <dict>,           # kind-specific arguments
    }

Snapshot file naming (one snapshot = pair of files; split on
``.`` always yields exactly four components ``[seq, label,
harness, ext]``):

    snapshots/0000000000.init.<harness_id>.ram.bin     # 256 B RAM bank 0
    snapshots/0000000000.init.<harness_id>.sfr.json    # top-of-bank-15 SFR map
    snapshots/0000000001.event_<kind>.<harness_id>.ram.bin
    snapshots/0000000001.event_<kind>.<harness_id>.sfr.json
    snapshots/<final_seq>.final.<harness_id>.ram.bin
    snapshots/<final_seq>.final.<harness_id>.sfr.json

Where `harness_id` is "control" / "main_0" / "main_1" depending
on the chain topology.  For event snapshots the `kind` is the
same `kind` argument that was passed to the immediately-preceding
`record_event(...)` call so a downstream reader can correlate
snapshots back to stimulus.jsonl entries.

P0.3 lands the *event* phase only; `snapshot_phase("init", ...)`
and `snapshot_phase("final", ...)` exist in the API but no
caller currently invokes them — the autouse fixture cannot take
init/final snapshots itself because chain harness instances
don't exist at fixture-enter time.  A later sub-task (e.g. P0.5)
may wire init/final snapshots if needed.

The `tick` field listed in spec §4 is intentionally omitted; the
existing harnesses don't expose a uniform universal-clock counter
(CONTROL and MAIN have separate per-core PIC cycle counters and
the 48 MHz universal tick is a Phase-3 concept).  A forward-
compatible "tick" field is reserved for P0.5/Phase-3 to fill in
once the multi-core clock domain is wired.
"""

from __future__ import annotations

import contextvars
import json
import re
import time
from pathlib import Path
from types import TracebackType
from typing import Any, Iterable, Protocol


_HARNESS_ID_RE = re.compile(r"[A-Za-z0-9_-]+")

__all__ = [
    "GroundTruthContext",
    "Snapshotable",
    "StimulusRecorder",
    "SnapshotTaker",
    "get_active_context",
    "get_active_recorder",
    "record_event",
    "snapshot_after_event",
    "snapshot_phase",
]


class Snapshotable(Protocol):
    """Anything the snapshot taker can dump.

    `harness_id` is a short identifier used in snapshot filenames;
    must be unique within a single capture context (so two MAIN
    harnesses in a wire chain have distinct ids like ``main_0`` and
    ``main_1``) and must match ``[A-Za-z0-9_-]+`` in full
    (re.fullmatch — no embedded ``.``, no trailing newline) so the
    4-component snapshot filename contract
    (``seq.<label>.<harness_id>.<ext>``) survives ``Path.split('.')``
    parsing.

    `dump_state()` returns ``(ram_bank0, sfr_map)`` where:
      * ``ram_bank0`` is exactly 256 bytes covering 0x000-0x0FF.
      * ``sfr_map`` is a dict ``{addr: value}`` over the top-of-
        bank-15 SFR area (typically 0xF60-0xFFF).

    Both reads use the harness's existing register-access path so
    the dump captures the same view tests already see.
    """

    @property
    def harness_id(self) -> str: ...

    def dump_state(self) -> tuple[bytes, dict[int, int]]: ...


_active_context: contextvars.ContextVar["GroundTruthContext | None"] = (
    contextvars.ContextVar("dlcp_sim_active_context", default=None)
)


SCHEMA_VERSION = 1


class StimulusRecorder:
    """Append-only JSONL writer for ground-truth stimulus events.

    Owned by `GroundTruthContext`; not used standalone in normal
    operation.  Re-entrancy is enforced at the context level, not
    here, since the recorder no longer manages the active-context
    ContextVar itself.
    """

    def __init__(self, out_path: Path) -> None:
        self.out_path = Path(out_path)
        self._fp = None
        self._seq = 0
        self._closed = False

    def open(self) -> None:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.out_path.open("w", encoding="utf-8")

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

    @property
    def next_seq(self) -> int:
        return self._seq

    def record(self, *, kind: str, harness: str, payload: dict[str, Any] | None = None) -> int:
        """Append one event to the JSONL stream and return its seq.

        Flushing on every event is deliberate: a test that crashes
        mid-run leaves a usable partial stream, which is what we
        want for post-mortem replay.
        """
        if self._closed or self._fp is None:
            return -1
        seq = self._seq
        event: dict[str, Any] = {
            "seq": seq,
            "wall_time": time.time(),
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "harness": harness,
            "payload": payload or {},
        }
        self._fp.write(json.dumps(event, sort_keys=True) + "\n")
        self._fp.flush()
        self._seq += 1
        return seq


class SnapshotTaker:
    """Writes binary RAM + JSON SFR snapshots to `snapshots/`.

    Owned by `GroundTruthContext`.  Each snapshot is a pair of files:

        <seq:010d>.<phase>.<harness_id>.ram.bin   (256 bytes)
        <seq:010d>.<phase>.<harness_id>.sfr.json  (hex-keyed dict)

    The seq is monotonic across init/event/final; `phase` is one of
    {"init", "event", "final"}; for "event" the filename also
    embeds the event kind so a reader can match snapshots back to
    the stimulus.jsonl entries.
    """

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)
        self._seq = 0
        self._opened = False

    def open(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._opened = True

    def close(self) -> None:
        # Filesystem-only; nothing to flush.
        pass

    def take(
        self,
        targets: Iterable[Snapshotable],
        *,
        phase: str,
        kind: str | None = None,
    ) -> int:
        """Dump RAM + SFR for each target.  Returns the seq used.

        Per-target writes are best-effort atomic in pairs: if the
        SFR write fails after the RAM write succeeded the orphan
        RAM file is cleaned up so a downstream validator does not
        see an unpaired snapshot.  Duplicate `harness_id`s within
        a single target set raise immediately, before any disk I/O,
        so a wire-chain bug that builds two MAINs with the same
        tag surfaces as a clear error rather than silent
        overwriting.
        """
        if not self._opened:
            return -1
        materialised = list(targets)
        seen: set[str] = set()
        for target in materialised:
            hid = target.harness_id
            # `fullmatch` rejects trailing newlines and partial
            # matches; `match` with `$` would silently accept
            # "control\n" because Python's `$` is multiline-friendly.
            if not _HARNESS_ID_RE.fullmatch(hid):
                raise RuntimeError(
                    f"invalid harness_id {hid!r}: must match "
                    "[A-Za-z0-9_-]+ in full so the snapshot filename's "
                    "4-component layout (seq.label.harness_id.ext) "
                    "remains parseable"
                )
            if hid in seen:
                raise RuntimeError(
                    f"duplicate harness_id {hid!r} in snapshot target set; "
                    "harness ids must be unique within one capture"
                )
            seen.add(hid)
        seq = self._seq
        for target in materialised:
            ram, sfr = target.dump_state()
            if len(ram) != 256:
                raise RuntimeError(
                    f"{target.harness_id}.dump_state() returned RAM of "
                    f"length {len(ram)} (expected 256)"
                )
            label = f"{phase}_{kind}" if (phase == "event" and kind) else phase
            stem = f"{seq:010d}.{label}.{target.harness_id}"
            ram_path = self.out_dir / f"{stem}.ram.bin"
            sfr_path = self.out_dir / f"{stem}.sfr.json"
            ram_path.write_bytes(ram)
            sfr_dump = {f"0x{addr:03X}": v & 0xFF for addr, v in sorted(sfr.items())}
            try:
                sfr_path.write_text(
                    json.dumps(sfr_dump, indent=2) + "\n",
                    encoding="utf-8",
                )
            except Exception:
                # Avoid leaving an orphan ram.bin without its sfr.json
                # sidecar; the validator requires snapshots to come in
                # pairs.
                if ram_path.exists():
                    try:
                        ram_path.unlink()
                    except OSError:
                        pass
                raise
        self._seq += 1
        return seq


class GroundTruthContext:
    """Per-test container that bundles a stimulus recorder and a
    snapshot taker, and owns the active-context ContextVar slot.

    Use as a context manager — entering binds the context to the
    current task, exiting unbinds and closes the underlying writers.
    Re-entrancy is rejected (single active context per call stack).
    """

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)
        self.stimulus = StimulusRecorder(self.out_dir / "stimulus.jsonl")
        self.snapshots = SnapshotTaker(self.out_dir / "snapshots")
        self._token: contextvars.Token | None = None

    def __enter__(self) -> "GroundTruthContext":
        if _active_context.get() is not None:
            raise RuntimeError(
                "another GroundTruthContext is already active; "
                "nested capture is not supported"
            )
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.stimulus.open()
        self.snapshots.open()
        self._token = _active_context.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if self._token is not None:
                _active_context.reset(self._token)
                self._token = None
        finally:
            try:
                self.snapshots.close()
            finally:
                self.stimulus.close()


def get_active_context() -> "GroundTruthContext | None":
    """Return the active capture context for the current test, or None."""
    return _active_context.get()


def get_active_recorder() -> "StimulusRecorder | None":
    """Compatibility shim: return the active context's recorder."""
    ctx = _active_context.get()
    return ctx.stimulus if ctx is not None else None


def record_event(*, kind: str, harness: str, payload: dict[str, Any] | None = None) -> int:
    """Record `kind` to the active recorder.  No-op when capture is off.

    Returns the assigned seq (or -1 when capture is off).  This is
    the shim chain-harness mutators call; the cost when capture is
    off is one ContextVar read and a None comparison.
    """
    ctx = _active_context.get()
    if ctx is None:
        return -1
    return ctx.stimulus.record(kind=kind, harness=harness, payload=payload)


def snapshot_after_event(kind: str, targets: Iterable[Snapshotable]) -> None:
    """Take a per-event snapshot of the given harnesses.  No-op when
    capture is off.  `kind` should match the `kind` passed to the
    immediately-preceding `record_event(...)` call so the snapshot
    file's `event_<kind>` label correlates with the stimulus.jsonl
    entry."""
    ctx = _active_context.get()
    if ctx is None:
        return
    ctx.snapshots.take(targets, phase="event", kind=kind)


def snapshot_phase(phase: str, targets: Iterable[Snapshotable]) -> None:
    """Take an init or final snapshot.  `phase` is "init" or "final"."""
    if phase not in ("init", "final"):
        raise ValueError(f"snapshot_phase phase must be init|final, got {phase!r}")
    ctx = _active_context.get()
    if ctx is None:
        return
    ctx.snapshots.take(targets, phase=phase)
