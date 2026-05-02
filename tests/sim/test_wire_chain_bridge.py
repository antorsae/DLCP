"""Unit tests for the pure-Python _StreamingUartBridge.

These tests don't need gpsim — the bridge is a file-based mapper that
translates sender-cycle/edge pairs into receiver-cycle/edge pairs. They
cover the batch-shift accounting, warning threshold, drop/extra-cycles
fault knobs, and the monotonic-cycle guarantee on the receiver side.

Marked dual_supported in P4.7: the bridge is a pure-Python component
with no simulator interaction; the tests pass identically under any
DLCP_SIM_BACKEND mode.  When P4.9 deletes the gpsim wire-chain
infrastructure, the bridge and these tests get removed together.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from dlcp_fw.sim.wire_chain_gpsim import _StreamingUartBridge


pytestmark = pytest.mark.dual_supported


def _make_bridge(
    tmp_path: Path,
    *,
    scale_num: int = 1,
    scale_den: int = 1,
    shift_warn_threshold: int | None = None,
) -> _StreamingUartBridge:
    record = tmp_path / "sender.txt"
    fifo = tmp_path / "receiver.stim"
    bridge = _StreamingUartBridge(
        name="test",
        sender_record_path=record,
        receiver_fifo_path=fifo,
        scale_num=scale_num,
        scale_den=scale_den,
        shift_warn_threshold=shift_warn_threshold,
    )
    bridge.start()
    return bridge


def _append_edges(record_path: Path, edges: list[tuple[int, int]]) -> None:
    with record_path.open("a", encoding="ascii") as f:
        for cycle, level in edges:
            f.write(f"{cycle} {level}\n")


def _read_fifo(fifo_path: Path) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for line in fifo_path.read_text(encoding="ascii").splitlines():
        parts = line.strip().split()
        if len(parts) != 2:
            continue
        out.append((int(parts[0]), int(parts[1])))
    return out


def test_bridge_preserves_edge_spacing_when_receiver_is_behind(tmp_path: Path) -> None:
    bridge = _make_bridge(tmp_path, scale_num=4, scale_den=3)
    _append_edges(bridge.sender_record_path, [(300, 0), (600, 5), (900, 0)])

    assert bridge.flush(receiver_min_cycle=0) == 3

    # Idle seed + three edges.
    fifo = _read_fifo(bridge.receiver_fifo_path)
    assert fifo[0] == (0, 5)
    # With scale 4/3: 300 -> 400, 600 -> 800, 900 -> 1200.
    assert fifo[1:] == [(400, 0), (800, 5), (1200, 0)]

    stats = bridge  # accessor-free struct
    assert stats.shift_events == 0
    assert stats.total_shift_cycles == 0
    assert stats.max_shift_cycles == 0
    assert stats.total_edges == 3


def test_bridge_shifts_batch_when_receiver_already_past_mapped_cycle(tmp_path: Path) -> None:
    bridge = _make_bridge(tmp_path, scale_num=1, scale_den=1)
    _append_edges(bridge.sender_record_path, [(100, 0), (200, 5)])

    # Receiver clock is already at 1000 — shift batch forward.
    bridge.flush(receiver_min_cycle=1000)

    fifo = _read_fifo(bridge.receiver_fifo_path)
    assert fifo[-2:] == [(1001, 0), (1101, 5)]  # original spacing 100 preserved
    assert bridge.shift_events == 1
    assert bridge.total_shift_cycles == 901
    assert bridge.max_shift_cycles == 901


def test_bridge_emits_warning_above_threshold(tmp_path: Path) -> None:
    bridge = _make_bridge(tmp_path, shift_warn_threshold=50)
    _append_edges(bridge.sender_record_path, [(10, 0)])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bridge.flush(receiver_min_cycle=1000)
    assert any("shifted batch by" in str(w.message) for w in caught)


def test_bridge_suppresses_warning_below_threshold(tmp_path: Path) -> None:
    bridge = _make_bridge(tmp_path, shift_warn_threshold=10_000)
    _append_edges(bridge.sender_record_path, [(0, 0)])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bridge.flush(receiver_min_cycle=500)
    assert not any("shifted batch" in str(w.message) for w in caught)
    assert bridge.shift_events == 1  # shift happened, just silent


def test_bridge_drop_fault_discards_edges(tmp_path: Path) -> None:
    bridge = _make_bridge(tmp_path)
    _append_edges(bridge.sender_record_path, [(10, 0), (20, 5)])
    bridge.configure(drop=True)
    assert bridge.flush() == 2

    # Only the start seed line should be present.
    fifo = _read_fifo(bridge.receiver_fifo_path)
    assert fifo == [(0, 5)]
    # Dropped edges don't count toward delivered totals.
    assert bridge.total_edges == 0


def test_bridge_extra_cycles_delays_delivery(tmp_path: Path) -> None:
    bridge = _make_bridge(tmp_path)
    bridge.configure(extra_cycles=42)
    _append_edges(bridge.sender_record_path, [(100, 0)])
    bridge.flush(receiver_min_cycle=0)

    fifo = _read_fifo(bridge.receiver_fifo_path)
    assert fifo[-1] == (142, 0)


def test_bridge_enforces_monotonic_receiver_cycle(tmp_path: Path) -> None:
    bridge = _make_bridge(tmp_path)
    # Same mapped cycle for both edges — bridge must still advance.
    _append_edges(bridge.sender_record_path, [(50, 0), (50, 5)])
    bridge.flush(receiver_min_cycle=0)

    fifo = _read_fifo(bridge.receiver_fifo_path)[1:]  # skip idle seed
    cycles = [c for c, _ in fifo]
    assert cycles == sorted(set(cycles))
    assert len(cycles) == 2


def test_bridge_handles_partial_final_line_across_flushes(tmp_path: Path) -> None:
    bridge = _make_bridge(tmp_path)
    # Write a line without trailing newline; the bridge should buffer it.
    bridge.sender_record_path.write_text("10 0", encoding="ascii")
    assert bridge.flush() == 0

    # Complete the line on the next flush.
    with bridge.sender_record_path.open("a", encoding="ascii") as f:
        f.write("\n20 5\n")
    assert bridge.flush() == 2


def test_bridge_missing_record_is_noop(tmp_path: Path) -> None:
    record = tmp_path / "never_written.txt"
    fifo = tmp_path / "receiver.stim"
    bridge = _StreamingUartBridge(
        name="ghost",
        sender_record_path=record,
        receiver_fifo_path=fifo,
        scale_num=1,
        scale_den=1,
    )
    # start() was not called; record doesn't exist; flush must return 0.
    assert bridge.flush() == 0


def test_bridge_clear_fault_resets_configured_state(tmp_path: Path) -> None:
    bridge = _make_bridge(tmp_path)
    bridge.configure(drop=True, extra_cycles=99)
    bridge.clear_fault()
    _append_edges(bridge.sender_record_path, [(5, 0)])
    assert bridge.flush(receiver_min_cycle=0) == 1

    fifo = _read_fifo(bridge.receiver_fifo_path)
    # extra_cycles reset to 0, drop reset to False.
    assert fifo[-1] == (5, 0)
