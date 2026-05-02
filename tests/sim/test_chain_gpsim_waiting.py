from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.chain_gpsim import SingleMainChainHarness
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


def _new_pair(control_hex: Path, main_hex: Path) -> SingleMainChainHarness:
    return SingleMainChainHarness(
        control_hex,
        main_hex,
        fast_boot=False,
        control_chunk_cycles=200_000,
        main_chunk_cycles=200_000,
        hold_cycles=240_000,
        disable_standby_check=False,
        bypass_i2c=False,
        main_transport_mode="native_ring",
    )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_single_main_chain_reaches_display(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
    dlcp_sim_backend: str,
) -> None:
    """V1.4 stock CONTROL + V2.3 stock MAIN chain reaches Volume display."""
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v17_chain(str(stock_control_hex_v14))
        c.run_until_connected(limit=140)
        lines = c.lcd_lines()
        assert c.is_connected(), (
            f"[rust] pair never connected; lcd={lines!r} "
            f"flags=0x{c.read_reg(0x01F):02X}"
        )
        assert not c.is_waiting(), (
            f"[rust] pair stayed in WAITING after connect; lcd={lines!r}"
        )
        assert "Volume:" in lines[0], (
            f"[rust] unexpected post-connect lcd: {lines!r}"
        )
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        pair = _new_pair(stock_control_hex_v14, stock_main_hex)
        try:
            assert pair.main.uses_adc_boot_wait_hook is False
            last = pair.run_until_connected(limit=140)
            assert last is not None, "[gpsim] pair never produced a step result"
            assert last.main.transport_mode == "native_ring"
            assert pair.is_connected(), (
                f"[gpsim] pair never connected; lcd={last.lcd!r} "
                f"flags=0x{last.control_flags:02X}"
            )
            assert not pair.is_waiting(), (
                f"[gpsim] pair stayed in WAITING after connect; lcd={last.lcd!r}"
            )
            assert "Volume:" in last.lcd[0], (
                f"[gpsim] unexpected post-connect lcd: {last.lcd!r}"
            )
        finally:
            pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_chain_attaches_default_external_i2c_bus(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
) -> None:
    """gpsim-only: tests gpsim's external I2C regfile bus attribute and
    reads cfg71/dsp34 subaddresses through the gpsim I2C regfile module.

    Stays gpsim-only because the rust facade has SRC4382 (cfg71) and
    TAS3108 (dsp34) slave models with different read APIs and the
    `uses_external_i2c_regfile_bus` attribute is gpsim-internal.
    """
    _require_gpsim()
    pair = _new_pair(stock_control_hex_v14, stock_main_hex)
    try:
        assert pair.main.uses_external_i2c_regfile_bus is True
        assert pair.main.read_i2c_regfile("cfg71", 0x00) == 0x00
        assert pair.main.read_i2c_regfile("dsp34", 0x00) == 0x00
    finally:
        pair.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_single_main_blackout_on_wake_shows_waiting(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
    dlcp_sim_backend: str,
) -> None:
    """After standby + UART blackout, wake leaves CONTROL in WAITING.

    Phases:
      1. Boot + connect -> Volume display
      2. set_blackout(True) + press STBY -> chain enters Zzz with no
         further UART traffic
      3. Press STBY again to wake -> CONTROL transitions to WAITING (no
         MAIN reply during blackout-cycle)
    """
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v17_chain(str(stock_control_hex_v14))
        c.run_until_connected(limit=140)
        assert c.is_connected(), (
            f"[rust] pair never connected; lcd={c.lcd_lines()!r}"
        )

        c.set_blackout(True)
        c.press("STBY")
        c.step_many(80)
        assert "ZZZ" in c.lcd_lines()[0].upper(), (
            f"[rust] pair did not enter standby before wake: {c.lcd_lines()!r}"
        )

        c.press("STBY")
        c.run_until_waiting(limit=20)
        assert c.is_waiting(), (
            f"[rust] pair did not fall back to WAITING after wake blackout: "
            f"{c.lcd_lines()!r}"
        )
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        pair = _new_pair(stock_control_hex_v14, stock_main_hex)
        try:
            last = pair.run_until_connected(limit=140)
            assert last is not None, "[gpsim] pair never produced a step result"
            assert pair.is_connected(), (
                f"[gpsim] pair never connected; lcd={last.lcd!r} "
                f"flags=0x{last.control_flags:02X}"
            )

            pair.set_blackout(True)
            pair.press("STBY")
            pair.step_many(80)
            assert "ZZZ" in pair.lcd_lines()[0].upper(), (
                f"[gpsim] pair did not enter standby before wake: "
                f"{pair.lcd_lines()!r}"
            )

            pair.press("STBY")
            waiting = pair.run_until_waiting(limit=20)
            assert waiting is not None, (
                "[gpsim] pair produced no steps while waiting for reconnect"
            )
            assert pair.is_waiting(), (
                f"[gpsim] pair did not fall back to WAITING after wake blackout: "
                f"{waiting.lcd!r}"
            )
        finally:
            pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_blackout_drops_link_but_main_keeps_running(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
) -> None:
    """gpsim-only: per-step cycle accounting under blackout.

    Stays gpsim-only because the assertion compares per-step cycle
    counters (`step.main.cycle > last.main.cycle`) which the rust
    facade doesn't expose at single-step granularity (the rust chain
    advances cores within a unified universal-tick scheduler that
    doesn't return a per-step cycle delta).  The same invariant
    (MAIN keeps running with blackout enabled) is observable on rust
    via `current_cycle` deltas, but the assertion shape is gpsim-
    specific.
    """
    _require_gpsim()
    pair = _new_pair(stock_control_hex_v14, stock_main_hex)
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None, "pair never produced a step result"
        assert pair.is_connected(), (
            f"pair never connected; lcd={last.lcd!r} "
            f"flags=0x{last.control_flags:02X}"
        )

        pair.set_blackout(True)
        step1 = pair.step()
        step2 = pair.step()

        assert step1.main.cycle > last.main.cycle
        assert step2.main.cycle > step1.main.cycle
        assert step1.main.transport_mode == step2.main.transport_mode
    finally:
        pair.close()
