"""Exhaustive stock-vs-patched compatibility checks for original MAIN commands.

Each parametrized case picks a (cmd, data) frame at route 0xB0 and asserts
that patched MAIN (V2.7 by default via the `patched_main_hex` fixture)
produces the same firmware-internal RAM as stock V2.3 for the registers
that the command is supposed to touch.

Both firmwares boot a MAIN-only rust chain via the native RX ring, inject
the activation frame, then the test frame, and snapshot the watch_regs
subset.  The stock-vs-patched equality is a firmware invariant.

The test also captures MAIN's TX byte stream after the test command and
asserts patched-vs-stock equality there too -- this covers cmd04 / cmd10
which have no register side-effects, only TX-burst output (cmd04 calls
`send_status_burst`, cmd10/0x29 calls `report_cmd29_status`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import STOCK_MAIN_HEX

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


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing: {p.name}")


_PHASE_TCY = 4_000_000


def _run_command(
    main_hex: Path, *, cmd: int, data: int, watch_regs: tuple[int, ...],
) -> tuple[dict[int, int], list[tuple[int, int, int]]]:
    """Boot the rust MAIN-only chain, send activation + test frame,
    snapshot watch_regs AND TX frames emitted by MAIN after the test
    command.

    Captures MAIN0's TX byte stream via `mark_tx_capture_point()` +
    `tx_record_since_last_capture()`, then chunks into 3-byte
    `(route, cmd, data)` tuples.  Trailing partial frames are
    truncated -- a partial frame at the wire boundary wouldn't yet
    be visible to a parser anyway."""
    _require_rust()
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


@pytest.mark.dual_supported
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
) -> None:
    """Every original MAIN command must preserve stock V2.3 behavior
    after patching."""
    del label
    _skip_missing(STOCK_MAIN_HEX, patched_main_hex)
    stock_regs, stock_tx = _run_command(
        STOCK_MAIN_HEX, cmd=cmd, data=data, watch_regs=check_regs,
    )
    patched_regs, patched_tx = _run_command(
        patched_main_hex, cmd=cmd, data=data, watch_regs=check_regs,
    )
    for reg in check_regs:
        assert patched_regs[reg] == stock_regs[reg], (
            f"cmd=0x{cmd:02X} data=0x{data:02X}: "
            f"reg 0x{reg:03X} patched=0x{patched_regs[reg]:02X} "
            f"stock=0x{stock_regs[reg]:02X}"
        )
    assert patched_tx == stock_tx, (
        f"cmd=0x{cmd:02X} data=0x{data:02X}: TX-frame divergence; "
        f"patched={patched_tx!r} stock={stock_tx!r}"
    )
