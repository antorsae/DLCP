"""Tests for MAIN preset-command mailbox handling.

V2.7 patched (the `patched_main_hex` fixture) MAIN echoes cmd 0x20
(preset-select) frames back as a 3-byte UART TX response.  The
patched MAIN's cmd 0x20 handler is the firmware-truthful path that
produces this echo; the rust MAIN-only chain captures the echo
directly via the native USART TX recorder.

NOT activated before injection (unlike `test_main_gpsim_command_
edges.py` / `test_main_gpsim_command_matrix.py` which use cmd
0x03/0x01 activation): the cmd 0x20 echo path doesn't require
active state on V2.7.  The post-injection step window is 20 M
MAIN-Tcy (vs 4 M for the activated tests) -- the cmd 0x20 echo
takes longer to propagate without the active-state speedup.

Bank-selection semantics (which preset is "active") is covered by
`test_main_model_banking.py` -- this file only verifies the TX-echo
behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


# Boot warmup: 4 M MAIN-Tcy.
_BOOT_TCY = 4_000_000

# Per-frame post-injection step window: 20 M MAIN-Tcy.
_FRAME_TCY = 20_000_000


def _run_frames(
    main_hex: Path, frames: list[list[int]],
) -> list[tuple[int, int, int]]:
    """Boot the rust MAIN-only chain (no activation), inject all
    `frames` in sequence with a step phase between each, return the
    captured TX-frame stream after all injections."""
    _require_rust()
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


def _check(
    main_hex: Path, frames: list[list[int]],
    expected: list[tuple[int, int, int]],
) -> None:
    if not main_hex.exists():
        pytest.skip(f"missing: {main_hex.name}")
    actual = _run_frames(main_hex, frames)
    assert actual == expected, (
        f"frames={frames!r} expected={expected!r} actual={actual!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_preset_a_mailbox_reply(patched_main_hex: Path) -> None:
    """cmd=0x20 data=0 -> MAIN echoes preset A selection."""
    _check(patched_main_hex, [[0xB0, 0x20, 0x00]], [(0xB0, 0x20, 0x00)])


@pytest.mark.dual_supported
@pytest.mark.slow
def test_preset_b_mailbox_reply(patched_main_hex: Path) -> None:
    """cmd=0x20 data=1 -> MAIN echoes preset B selection."""
    _check(patched_main_hex, [[0xB0, 0x20, 0x01]], [(0xB0, 0x20, 0x01)])


@pytest.mark.dual_supported
@pytest.mark.slow
def test_preset_switch_ab_mailbox_sequence(patched_main_hex: Path) -> None:
    """Set B then A -> MAIN echoes both frames in order."""
    _check(
        patched_main_hex,
        [[0xB0, 0x20, 0x01], [0xB0, 0x20, 0x00]],
        [(0xB0, 0x20, 0x01), (0xB0, 0x20, 0x00)],
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_broadcast_reaches_unit(patched_main_hex: Path) -> None:
    """route=0xB0 is consumed by unit (broadcast addressing)."""
    _check(patched_main_hex, [[0xB0, 0x20, 0x01]], [(0xB0, 0x20, 0x01)])
