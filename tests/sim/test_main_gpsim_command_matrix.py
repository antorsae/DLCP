"""Exhaustive stock-vs-patched compatibility checks for original MAIN commands.

Each parametrized case picks a (cmd, data) frame at route 0xB0 and asserts
that patched MAIN (V2.7 by default via the `patched_main_hex` fixture)
produces the same firmware-internal RAM as stock V2.3 for the registers
that the command is supposed to touch.

Migrated to dual_supported in P4.7: both backends boot a MAIN-only chain
via the native RX ring, inject the activation frame, then the test frame,
and snapshot the watch_regs subset.  The stock-vs-patched equality is a
firmware invariant (not a backend property), so each backend independently
runs both hexes and asserts their equivalence.

Pre-migration this test used `run_main_mailbox_gpsim` with the legacy
gpsim mailbox-overlay injection at 0x780+/0x7C0..0x7C3 (a gpsim-only RAM-
poke shim); rust uses the production native RX ring at
0x0200..0x02BF / 0x0C6/0x0C7.  The gpsim adapter is rewritten to use the
native ring (via `MainChainHarness(transport_mode="native_ring")`) so the
two backends exercise the same firmware path.  This drops the legacy
`parser_break_hit`, `0x7C0..0x7C3` ring-state, and `tx_bytes` mailbox-
overlay assertions -- those tested gpsim's overlay state, not firmware
behavior, and have no rust equivalent.  Same migration shape as
`test_main_gpsim_command_edges.py` (commit 77e74f2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import STOCK_MAIN_HEX
from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.control_gpsim import _read_reg
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


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing: {p.name}")


# Per-phase MAIN-Tcy advancement.  20 gpsim chunks × 200_000 MAIN-Tcy/chunk
# = 4 M MAIN-Tcy per phase.  Matches `test_v31_command_matrix.py` and
# `test_main_gpsim_command_edges.py`.
_PHASE_TCY = 4_000_000


def _run_command_gpsim(
    main_hex: Path, *, cmd: int, data: int, watch_regs: tuple[int, ...],
) -> tuple[dict[int, int], list[tuple[int, int, int]]]:
    """Boot MAIN via gpsim, send activation + test frame on the native
    RX ring, snapshot watch_regs AND TX frames emitted by MAIN after
    the test command.

    The TX-frames return value covers the firmware-truthful invariant
    for cmd04 / cmd10 (no register side-effects, only TX-burst
    output -- e.g. cmd04 calls `send_status_burst` and cmd10/0x29
    calls `report_cmd29_status`); without this, those parametrize
    cases would assert nothing post-migration."""
    h = MainChainHarness(
        main_hex, chunk_cycles=200_000, standby_mode="hold",
        rc2_mode="low", bypass_i2c=False, transport_mode="native_ring",
    )
    try:
        for _ in range(20):
            h.step()
        h.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
        for _ in range(20):
            h.step()

        # Mark the TX baseline AFTER activation: the activation cmd
        # itself emits some BF replies; we only want to assert on the
        # response to the TEST command.
        before_tx = list(h.tx_frames_snapshot() or [])

        h.inject_frames_fifo([[0xB0, cmd, data]], fifo_limit=47)
        for _ in range(20):
            h.step()

        all_tx = list(h.tx_frames_snapshot() or [])
        new_tx = all_tx[len(before_tx):]
        regs = {r: _read_reg(h._issue, r) for r in watch_regs}
        return regs, new_tx
    finally:
        h.close()


def _run_command_rust(
    main_hex: Path, *, cmd: int, data: int, watch_regs: tuple[int, ...],
) -> tuple[dict[int, int], list[tuple[int, int, int]]]:
    """Same as `_run_command_gpsim` on the rust MAIN-only chain.

    Captures MAIN0's TX byte stream via `mark_tx_capture_point()` +
    `tx_record_since_last_capture()`, then chunks into 3-byte
    `(route, cmd, data)` tuples (matching gpsim's
    `tx_frames_snapshot()` shape).  Trailing partial frames are
    truncated -- a partial frame at the wire boundary wouldn't yet
    be visible to a parser anyway."""
    chain = RustChain.from_v3x_main_only(str(main_hex))
    chain.step_tcy(_PHASE_TCY)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(_PHASE_TCY)

    chain.mark_tx_capture_point()

    chain.inject_main_frames_fifo([[0xB0, cmd, data]], fifo_limit=47)
    chain.step_tcy(_PHASE_TCY)

    raw_bytes = chain.tx_record_since_last_capture()
    new_tx = [
        (raw_bytes[i], raw_bytes[i + 1], raw_bytes[i + 2])
        for i in range(0, len(raw_bytes) - len(raw_bytes) % 3, 3)
    ]
    regs = {r: chain.read_reg(r) for r in watch_regs}
    return regs, new_tx


def _run_command(
    main_hex: Path, *, cmd: int, data: int,
    watch_regs: tuple[int, ...], backend: str,
) -> tuple[dict[int, int], list[tuple[int, int, int]]]:
    if backend == "rust":
        return _run_command_rust(
            main_hex, cmd=cmd, data=data, watch_regs=watch_regs,
        )
    return _run_command_gpsim(
        main_hex, cmd=cmd, data=data, watch_regs=watch_regs,
    )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("cmd", "data", "label", "check_regs"),
    [
        (0x03, 0x00, "cmd03_standby_off", (0x05E,)),
        (0x03, 0x01, "cmd03_standby_on", (0x05E,)),
        (0x03, 0x02, "cmd03_mute_on", (0x05E,)),
        (0x03, 0x03, "cmd03_mute_off", (0x05E,)),
        (0x04, 0x00, "cmd04_status_request", ()),
        (0x06, 0x02, "cmd06_set_source", (0x099, 0x0B3)),
        (0x07, 0x45, "cmd07_set_volume",
         (0x066, 0x067, 0x068, 0x069, 0x06E, 0x06F, 0x070, 0x071)),
        (0x10, 0x29, "cmd10_query_standby", ()),
        (0x17, 0x01, "cmd17_ch1_source", (0x0A5,)),
        (0x18, 0x02, "cmd18_ch2_source", (0x0A6,)),
        (0x19, 0x03, "cmd19_ch3_source", (0x0A7,)),
        (0x1A, 0x01, "cmd1a_ch4_source", (0x0A8,)),
        (0x1B, 0x02, "cmd1b_ch5_source", (0x0A9,)),
        (0x1C, 0x03, "cmd1c_ch6_source", (0x0AA,)),
        (0x1D, 0x07, "cmd1d_backlight_timeout", (0x0B8,)),
        (0x1E, 0x07, "cmd1e_link_address", (0x0B2, 0x0C3)),
    ],
    ids=lambda p: p if isinstance(p, str) else None,
)
def test_original_main_command_matrix_matches_stock(
    patched_main_hex: Path,
    cmd: int,
    data: int,
    label: str,
    check_regs: tuple[int, ...],
    dlcp_sim_backend: str,
) -> None:
    """Every original MAIN command must preserve stock V2.3 behavior
    after patching.

    Dual-mode (P4.7): each backend independently runs both stock and
    patched hexes and asserts the per-cmd register subset matches.
    Cross-backend behaviors aren't asserted (gpsim and rust may have
    minor cadence differences in side-effect register convergence;
    the firmware-truthful invariant is per-backend stock-vs-patched,
    not cross-backend).
    """
    del label
    _skip_missing(STOCK_MAIN_HEX, patched_main_hex)
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        stock_regs, stock_tx = _run_command(
            STOCK_MAIN_HEX, cmd=cmd, data=data,
            watch_regs=check_regs, backend="rust",
        )
        patched_regs, patched_tx = _run_command(
            patched_main_hex, cmd=cmd, data=data,
            watch_regs=check_regs, backend="rust",
        )
        for reg in check_regs:
            assert patched_regs[reg] == stock_regs[reg], (
                f"[rust] cmd=0x{cmd:02X} data=0x{data:02X}: "
                f"reg 0x{reg:03X} patched=0x{patched_regs[reg]:02X} "
                f"stock=0x{stock_regs[reg]:02X}"
            )
        assert patched_tx == stock_tx, (
            f"[rust] cmd=0x{cmd:02X} data=0x{data:02X}: TX-frame "
            f"divergence; patched={patched_tx!r} stock={stock_tx!r}"
        )
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        stock_regs, stock_tx = _run_command(
            STOCK_MAIN_HEX, cmd=cmd, data=data,
            watch_regs=check_regs, backend="gpsim",
        )
        patched_regs, patched_tx = _run_command(
            patched_main_hex, cmd=cmd, data=data,
            watch_regs=check_regs, backend="gpsim",
        )
        for reg in check_regs:
            assert patched_regs[reg] == stock_regs[reg], (
                f"[gpsim] cmd=0x{cmd:02X} data=0x{data:02X}: "
                f"reg 0x{reg:03X} patched=0x{patched_regs[reg]:02X} "
                f"stock=0x{stock_regs[reg]:02X}"
            )
        assert patched_tx == stock_tx, (
            f"[gpsim] cmd=0x{cmd:02X} data=0x{data:02X}: TX-frame "
            f"divergence; patched={patched_tx!r} stock={stock_tx!r}"
        )
