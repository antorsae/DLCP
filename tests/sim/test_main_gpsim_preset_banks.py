"""gpsim-level tests for MAIN preset-command mailbox handling.

V2.7 patched (the `patched_main_hex` fixture) MAIN echoes cmd 0x20
(preset-select) frames back as a 3-byte UART TX response.  The
patched MAIN's cmd 0x20 handler is the firmware-truthful path
that produces this echo; the legacy gpsim mailbox-overlay was
just CAPTURING the echo via instrumentation hooks at MAIN's TXREG
write paths.  With native_ring transport on either backend, the
same firmware-driven TX is observable directly.

Migrated to dual_supported in P4.7: both backends use the native
USART path; rust uses `Chain.from_v3x_main_only` +
`mark_tx_capture_point()` + `tx_record_since_last_capture()`;
gpsim uses `MainChainHarness(transport_mode="native_ring")` +
`tx_frames_snapshot()` baseline-and-diff.

NOT activated before injection (unlike `test_main_gpsim_command_
edges.py` / `test_main_gpsim_command_matrix.py` which use cmd
0x03/0x01 activation): the original test ran without activation
and the cmd 0x20 echo path doesn't require active state on V2.7.
The post-injection step window is 20 M MAIN-Tcy (vs 4 M for the
activated tests) -- the cmd 0x20 echo takes longer to propagate
without the active-state speedup; 20 M is empirically sufficient
on rust.

Bank-selection semantics (which preset is "active") is covered
by `test_main_model_banking.py` -- this file only verifies the
TX-echo behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.gpsim import gpsim_available

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


# Boot warmup: 4 M MAIN-Tcy (20 gpsim chunks × 200_000).
_BOOT_TCY = 4_000_000

# Per-frame post-injection step window: 20 M MAIN-Tcy.  Unlike the
# activated tests (which use 4 M Tcy), cmd 0x20's echo takes
# longer without active-state speedup; 20 M is empirically
# sufficient.  The original gpsim test used `cycles=120_000_000`
# total which is even more conservative.
_FRAME_TCY = 20_000_000


def _run_frames_gpsim(
    main_hex: Path, frames: list[list[int]],
) -> list[tuple[int, int, int]]:
    """Boot MAIN via gpsim native ring (no activation), inject all
    `frames` in sequence with a step phase between each, return the
    captured TX-frame stream after all injections."""
    h = MainChainHarness(
        main_hex, chunk_cycles=200_000, standby_mode="hold",
        rc2_mode="low", bypass_i2c=False, transport_mode="native_ring",
    )
    try:
        for _ in range(_BOOT_TCY // 200_000):
            h.step()
        before_tx = list(h.tx_frames_snapshot() or [])
        for frame in frames:
            h.inject_frames_fifo([frame], fifo_limit=47)
            for _ in range(_FRAME_TCY // 200_000):
                h.step()
        all_tx = list(h.tx_frames_snapshot() or [])
        return all_tx[len(before_tx):]
    finally:
        h.close()


def _run_frames_rust(
    main_hex: Path, frames: list[list[int]],
) -> list[tuple[int, int, int]]:
    """Same as `_run_frames_gpsim` on the rust MAIN-only chain."""
    chain = RustChain.from_v3x_main_only(str(main_hex))
    chain.step_tcy(_BOOT_TCY)
    chain.mark_tx_capture_point()
    for frame in frames:
        chain.inject_main_frames_fifo([frame], fifo_limit=47)
        chain.step_tcy(_FRAME_TCY)
    raw = chain.tx_record_since_last_capture()
    return [
        (raw[i], raw[i + 1], raw[i + 2])
        for i in range(0, len(raw) - len(raw) % 3, 3)
    ]


def _run_frames(
    main_hex: Path, frames: list[list[int]], backend: str,
) -> list[tuple[int, int, int]]:
    if backend == "rust":
        return _run_frames_rust(main_hex, frames)
    return _run_frames_gpsim(main_hex, frames)


def _check(
    main_hex: Path, frames: list[list[int]],
    expected: list[tuple[int, int, int]], backend: str,
) -> None:
    if not main_hex.exists():
        pytest.skip(f"missing: {main_hex.name}")
    actual = _run_frames(main_hex, frames, backend)
    assert actual == expected, (
        f"[{backend}] frames={frames!r} expected={expected!r} "
        f"actual={actual!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_a_mailbox_reply(
    patched_main_hex: Path, dlcp_sim_backend: str,
) -> None:
    """cmd=0x20 data=0 -> MAIN echoes preset A selection."""
    frames = [[0xB0, 0x20, 0x00]]
    expected = [(0xB0, 0x20, 0x00)]
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        _check(patched_main_hex, frames, expected, "rust")
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _check(patched_main_hex, frames, expected, "gpsim")


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_b_mailbox_reply(
    patched_main_hex: Path, dlcp_sim_backend: str,
) -> None:
    """cmd=0x20 data=1 -> MAIN echoes preset B selection."""
    frames = [[0xB0, 0x20, 0x01]]
    expected = [(0xB0, 0x20, 0x01)]
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        _check(patched_main_hex, frames, expected, "rust")
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _check(patched_main_hex, frames, expected, "gpsim")


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_switch_ab_mailbox_sequence(
    patched_main_hex: Path, dlcp_sim_backend: str,
) -> None:
    """Set B then A -> MAIN echoes both frames in order."""
    frames = [[0xB0, 0x20, 0x01], [0xB0, 0x20, 0x00]]
    expected = [(0xB0, 0x20, 0x01), (0xB0, 0x20, 0x00)]
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        _check(patched_main_hex, frames, expected, "rust")
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _check(patched_main_hex, frames, expected, "gpsim")


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_broadcast_reaches_unit(
    patched_main_hex: Path, dlcp_sim_backend: str,
) -> None:
    """route=0xB0 is consumed by unit (broadcast addressing)."""
    frames = [[0xB0, 0x20, 0x01]]
    expected = [(0xB0, 0x20, 0x01)]
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        _check(patched_main_hex, frames, expected, "rust")
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _check(patched_main_hex, frames, expected, "gpsim")
