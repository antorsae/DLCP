"""V1.4 stock CONTROL robustness checks.

A single rust-facade test verifies V1.4 stock CONTROL without a MAIN
peer reaches and stays on the "WAITING FOR DLCP" LCD message.

A second test (`test_stock_control_v14_runtime_response_blackout_falls_back_to_waiting`)
was gpsim-only by design: it depended on gpsim's synthetic-heartbeat
pause to clear the CONNECTED bit after warmup.  The rust facade has
no `disable_force_connected` primitive, and `Chain.from_v17_chain` +
`set_blackout(True)` does not clear CONNECTED on V1.4 stock within
the test budget.  Migrating it requires either a new rust facade
primitive or a deeper probe of why V1.4 stock's no-heartbeat timeout
doesn't fire on rust under chain blackout — tracked for a future
session.
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


def _lcd_text_lower(lines) -> str:
    return (lines[0] + " " + lines[1]).lower()


def _wait_for_waiting(c, *, limit: int, chunk_tcy: int) -> bool:
    for _ in range(limit):
        c.step_tcy(chunk_tcy)
        if "waiting for dlcp" in _lcd_text_lower(c.lcd_lines()):
            return True
    return False


@pytest.mark.dual_supported
@pytest.mark.slow
def test_stock_control_v14_without_main_shows_waiting_on_lcd(
    stock_control_hex_v14: Path,
) -> None:
    """V1.4 stock CONTROL without MAIN: LCD reaches and stays on WAITING."""
    _require_rust()
    c = RustChain.from_v17_control_only(str(stock_control_hex_v14))
    if not _wait_for_waiting(c, limit=120, chunk_tcy=300_000):
        pytest.fail(f"lcd never stuck on WAITING without MAIN: {c.lcd_lines()!r}")
    # Hold for ~24 chunks worth of cycles to confirm it stays.
    c.step_tcy(24 * 300_000)
    text = _lcd_text_lower(c.lcd_lines())
    assert "waiting for dlcp" in text, (
        f"lcd left WAITING after holding without MAIN: {c.lcd_lines()!r}"
    )
