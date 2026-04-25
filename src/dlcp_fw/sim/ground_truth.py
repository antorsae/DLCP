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
    "OutputCapturable",
    "OutputCapture",
    "Snapshotable",
    "StimulusRecorder",
    "SnapshotTaker",
    "get_active_context",
    "get_active_recorder",
    "record_event",
    "snapshot_after_event",
    "snapshot_phase",
    "dump_harness_outputs",
]


class OutputCapturable(Protocol):
    """Anything the OutputCapture can drain at harness close().

    Each method returns ``None`` when the harness has nothing to
    contribute for that stream — control harnesses populate LCD,
    main harnesses do not; both populate EUSART tx and EEPROM.
    `harness_id` shares the same constraint as `Snapshotable`.

    The capture writes files only for non-None return values, so
    an empty test that produces no LCD/EEPROM still writes
    `uart_tx_<id>.jsonl` with zero events without spurious sidecars.
    """

    @property
    def harness_id(self) -> str: ...

    def tx_frames_snapshot(self) -> list[tuple[int, int, int]] | None:
        """Return ``[(route, cmd, data), ...]`` for every TX frame
        decoded so far, or None if this harness has no UART TX
        to report."""
        ...

    def lcd_snapshot(self) -> tuple[str, str] | None:
        """Return current ``(line0, line1)`` LCD content, or None
        if this harness has no LCD attached."""
        ...

    def eeprom_snapshot(self) -> bytes | None:
        """Return all 256 bytes of internal EEPROM, or None if
        this harness type has no EEPROM (or capture would be too
        expensive at close-time)."""
        ...


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

    `cycle_count()` returns the gpsim instruction-cycle counter at
    snapshot time, or ``None`` if the harness can't expose it.
    Captured into a per-snapshot ``.meta.json`` sidecar so the
    Rust ISA parity test (P1.8d / Task #18) can run its executor
    for the same number of cycles before bit-comparing.  Default
    impl returns ``None`` for harnesses that don't track cycles.

    Both reads use the harness's existing register-access path so
    the dump captures the same view tests already see.
    """

    @property
    def harness_id(self) -> str: ...

    def dump_state(self) -> tuple[bytes, dict[int, int]]: ...

    def cycle_count(self) -> int | None:
        return None


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
            meta_path = self.out_dir / f"{stem}.meta.json"
            ram_path.write_bytes(ram)
            sfr_dump = {f"0x{addr:03X}": v & 0xFF for addr, v in sorted(sfr.items())}
            try:
                sfr_path.write_text(
                    json.dumps(sfr_dump, indent=2) + "\n",
                    encoding="utf-8",
                )
                # Optional metadata sidecar: cycle count at
                # snapshot time, if the harness exposes it.
                # Consumed by the Rust ISA-parity test (P1.8d /
                # Task #18) which runs its executor for the
                # same number of cycles before bit-comparing.
                cycle = None
                cycle_fn = getattr(target, "cycle_count", None)
                if callable(cycle_fn):
                    try:
                        cycle = cycle_fn()
                    except Exception:
                        cycle = None
                if cycle is not None:
                    meta_path.write_text(
                        json.dumps({"cycle": int(cycle)}, indent=2) + "\n",
                        encoding="utf-8",
                    )
            except Exception:
                # Avoid leaving orphan files; the validator
                # requires snapshot files to come in pairs.
                for p in (ram_path, sfr_path, meta_path):
                    if p.exists():
                        try:
                            p.unlink()
                        except OSError:
                            pass
                raise
        self._seq += 1
        return seq


class OutputCapture:
    """Writes per-harness UART/LCD/EEPROM artefacts at close-time.

    Files are written directly into the test's output directory:

        uart_tx_<harness_id>.jsonl  (one JSONL line per TX frame)
        lcd_<harness_id>.txt        (two text lines, exact LCD raster)
        eeprom_<harness_id>.bin     (256 raw bytes of EEPROM)

    `dump(harness)` is called from each harness's `close()` *before*
    it tears down its gpsim subprocess so any read still works.  A
    harness whose `*_snapshot()` accessor returns None contributes
    no file for that stream — e.g. MainChainHarness has no LCD and
    therefore writes no `lcd_main_0.txt`.
    """

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)
        self._opened = False
        # Track which harnesses have been dumped so a redundant
        # close() doesn't double-write.
        self._dumped: set[str] = set()

    def open(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._opened = True

    def close(self) -> None:
        # Filesystem-only; nothing to flush.
        pass

    def dump(self, harness: OutputCapturable) -> None:
        """Drain the harness's UART/LCD/EEPROM into the output dir.

        The harness is marked dumped only AFTER all writes complete.
        If a write raises (e.g. EEPROM read against a dead gpsim
        subprocess), the partial files written so far are removed
        and the dumped flag stays unset so a subsequent close() can
        retry.  EEPROM is the most fragile read; it runs after the
        cheap in-memory UART/LCD writes so a transient EEPROM failure
        doesn't prevent capture of the other streams.
        """
        if not self._opened:
            return
        hid = harness.harness_id
        if hid in self._dumped:
            return

        tx_path = self.out_dir / f"uart_tx_{hid}.jsonl"
        lcd_path = self.out_dir / f"lcd_{hid}.txt"
        eeprom_path = self.out_dir / f"eeprom_{hid}.bin"
        # Register each path BEFORE the write so a mid-write failure
        # (disk full, encoding error, etc.) still has the partial
        # file unlinked by the rollback loop.  Earlier code only
        # appended on successful completion, which left in-progress
        # write failures uncleaned.
        written: list[Path] = []
        try:
            tx = harness.tx_frames_snapshot()
            if tx is not None:
                written.append(tx_path)
                with tx_path.open("w", encoding="utf-8") as fp:
                    for seq, frame in enumerate(tx):
                        route, cmd, data = frame
                        fp.write(json.dumps({
                            "seq": seq,
                            "route": route & 0xFF,
                            "cmd": cmd & 0xFF,
                            "data": data & 0xFF,
                        }, sort_keys=True) + "\n")

            lcd = harness.lcd_snapshot()
            if lcd is not None:
                line0, line1 = lcd
                written.append(lcd_path)
                lcd_path.write_text(
                    f"{line0}\n{line1}\n", encoding="utf-8"
                )

            eeprom = harness.eeprom_snapshot()
            if eeprom is not None:
                if len(eeprom) != 256:
                    raise RuntimeError(
                        f"{hid}.eeprom_snapshot() returned {len(eeprom)} "
                        "bytes (expected 256)"
                    )
                written.append(eeprom_path)
                eeprom_path.write_bytes(eeprom)
        except Exception:
            # Roll back partial state so a downstream validator can't
            # be fooled by a half-captured artifact set.  `written`
            # may contain paths whose corresponding write was only
            # partially completed; unlink them too.
            for p in written:
                try:
                    p.unlink()
                except OSError:
                    pass
            raise
        # Successful complete dump — only now mark this harness as
        # done so a future close() retry is rejected.
        self._dumped.add(hid)


class GroundTruthContext:
    """Per-test container that bundles a stimulus recorder, a
    snapshot taker, and an output capture, and owns the active-
    context ContextVar slot.

    Use as a context manager — entering binds the context to the
    current task, exiting unbinds and closes the underlying writers.
    Re-entrancy is rejected (single active context per call stack).
    """

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)
        self.stimulus = StimulusRecorder(self.out_dir / "stimulus.jsonl")
        self.snapshots = SnapshotTaker(self.out_dir / "snapshots")
        self.outputs = OutputCapture(self.out_dir)
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
        self.outputs.open()
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
                self.outputs.close()
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


def dump_harness_outputs(harness: OutputCapturable) -> None:
    """Drain a harness's UART/LCD/EEPROM into the active context.

    No-op when capture is off.  Called from each harness's
    ``close()`` *before* the gpsim subprocess is torn down so any
    final reg() reads still work.  Idempotent — a harness whose
    close() runs twice (e.g. via ``__del__``) only writes the
    output files once.
    """
    ctx = _active_context.get()
    if ctx is None:
        return
    ctx.outputs.dump(harness)
