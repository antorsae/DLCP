"""V1.4 stock CONTROL + V2.3 stock MAIN chain WAITING-fallback tests.

Two rust-facade tests:

* ``test_stock_single_main_chain_reaches_display`` — stock pair
  reaches Volume display after run_until_connected.
* ``test_stock_single_main_blackout_on_wake_shows_waiting`` —
  blackout + STBY + wake leaves CONTROL in WAITING because MAIN
  doesn't reply during the blackout cycle.

Two earlier gpsim-only tests
(``test_chain_attaches_default_external_i2c_bus``,
``test_blackout_drops_link_but_main_keeps_running``) were deleted in
PF.4 phase 2 batch 6: the first probed gpsim's
``uses_external_i2c_regfile_bus`` attribute (gpsim-internal — rust
has its own SRC4382 / TAS3108 slave models with different read
APIs); the second compared per-step ``main.cycle`` counters that
the rust chain's universal-tick scheduler does not expose at
single-step granularity.  Neither covered firmware behaviour beyond
what the two remaining tests already exercise.
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


@pytest.mark.dual_supported
@pytest.mark.slow
def test_stock_single_main_chain_reaches_display(
    stock_control_hex_v14: Path,
) -> None:
    """V1.4 stock CONTROL + V2.3 stock MAIN chain reaches Volume display."""
    _require_rust()
    c = RustChain.from_v17_chain(str(stock_control_hex_v14))
    c.run_until_connected(limit=140)
    lines = c.lcd_lines()
    assert c.is_connected(), (
        f"pair never connected; lcd={lines!r} "
        f"flags=0x{c.read_reg(0x01F):02X}"
    )
    assert not c.is_waiting(), (
        f"pair stayed in WAITING after connect; lcd={lines!r}"
    )
    assert "Volume:" in lines[0], (
        f"unexpected post-connect lcd: {lines!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_stock_single_main_blackout_on_wake_shows_waiting(
    stock_control_hex_v14: Path,
) -> None:
    """After standby + UART blackout, wake leaves CONTROL in WAITING.

    Phases:
      1. Boot + connect -> Volume display
      2. set_blackout(True) + press STBY -> chain enters Zzz with no
         further UART traffic
      3. Press STBY again to wake -> CONTROL transitions to WAITING (no
         MAIN reply during blackout-cycle)
    """
    _require_rust()
    c = RustChain.from_v17_chain(str(stock_control_hex_v14))
    c.run_until_connected(limit=140)
    assert c.is_connected(), (
        f"pair never connected; lcd={c.lcd_lines()!r}"
    )

    c.set_blackout(True)
    c.press("STBY")
    c.step_many(80)
    assert "ZZZ" in c.lcd_lines()[0].upper(), (
        f"pair did not enter standby before wake: {c.lcd_lines()!r}"
    )

    c.press("STBY")
    c.run_until_waiting(limit=20)
    assert c.is_waiting(), (
        f"pair did not fall back to WAITING after wake blackout: "
        f"{c.lcd_lines()!r}"
    )
