"""V1.7 CONTROL ↔ MAIN chain behavioral-parity tests (spec §A5).

Drives stock V2.3 MAIN paired with three CONTROL variants:

* stock V1.6b (behavioral baseline — sanity-check the chain harness),
* V1.7 byte-identical rebuild (must match stock by construction),
* V1.7 shifted (+0x222 bytes — must behave identically, proving that
  the relocation does not break chain-level invariants).

The two parity gates are:

1. ``run_until_connected`` reaches Volume screen (``"Volume:"`` in LCD
   row 0) — spec §A5 "Chain reaches display".
2. Blackout + STBY press leaves the chain in the WAITING state after
   wake — spec §A5 "Chain blackout/wake WAITING".

Each test is marked ``gpsim`` + ``slow``; the shifted variant is a
session-scoped fixture so the V1.7 sources are assembled only once.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    STOCK_CONTROL_HEX_V16B,
    V17_CONTROL_ASM_COMMENTS,
    V17_CONTROL_RAM_INC,
)
from dlcp_fw.sim.gpsim import gpsim_available

try:
    from dlcp_fw.sim.chain_gpsim import SingleMainChainHarness
    from dlcp_fw.sim.v17_symbols import assemble_v17, build_shifted_asm
    _CHAIN_IMPORT_OK = True
except Exception:  # pragma: no cover
    _CHAIN_IMPORT_OK = False


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    if not _CHAIN_IMPORT_OK:
        pytest.skip("chain_gpsim harness not importable in this env")


@pytest.fixture(scope="module")
def v17_chain_images(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Assemble V1.7 + V1.7 shifted hex once per test module."""
    tmp = tmp_path_factory.mktemp("v17_chain")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    src_stage = tmp / V17_CONTROL_ASM_COMMENTS.name
    src_stage.write_bytes(V17_CONTROL_ASM_COMMENTS.read_bytes())

    hex_v17 = tmp / "v17.hex"
    assemble_v17(src_stage, hex_v17)

    shifted_src = tmp / "v17_shifted.asm"
    build_shifted_asm(src_stage, shifted_src)
    hex_shifted = tmp / "v17_shifted.hex"
    assemble_v17(shifted_src, hex_shifted)

    return {"v17": hex_v17, "shifted": hex_shifted}


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


# ---------------------------------------------------------------------------
# Spec §A5 gate #1: chain reaches Volume screen.
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_v17_stock_v16b_chain_reaches_display(stock_main_hex: Path) -> None:
    """Sanity baseline: stock V1.6b CONTROL + stock MAIN V2.3 reach Volume."""
    _require_gpsim()
    pair = _new_pair(STOCK_CONTROL_HEX_V16B, stock_main_hex)
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None
        assert pair.is_connected(), (
            f"V1.6b+V2.3 never connected; lcd={last.lcd!r} "
            f"flags=0x{last.control_flags:02X}"
        )
        assert not pair.is_waiting(), (
            f"V1.6b+V2.3 stayed in WAITING; lcd={last.lcd!r}"
        )
        assert "Volume:" in last.lcd[0], (
            f"V1.6b+V2.3 did not reach Volume: {last.lcd!r}"
        )
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v17_rebuilt_chain_reaches_display(
    v17_chain_images, stock_main_hex: Path
) -> None:
    """V1.7 byte-identical rebuild behaves exactly like stock V1.6b."""
    _require_gpsim()
    pair = _new_pair(v17_chain_images["v17"], stock_main_hex)
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None
        assert pair.is_connected(), (
            f"V1.7+V2.3 never connected; lcd={last.lcd!r} "
            f"flags=0x{last.control_flags:02X}"
        )
        assert not pair.is_waiting(), (
            f"V1.7+V2.3 stayed in WAITING; lcd={last.lcd!r}"
        )
        assert "Volume:" in last.lcd[0], (
            f"V1.7+V2.3 did not reach Volume: {last.lcd!r}"
        )
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v17_shifted_chain_reaches_display(
    v17_chain_images, stock_main_hex: Path
) -> None:
    """V1.7 shifted (+0x222) must still converge to Volume screen.

    The dynamic standby-check overlay resolves the patch site via the
    ``post_connect_init`` symbol from the sibling ``.lst``.  If
    relocation broke anything behaviorally — a missed TBLPTR load, a
    hardcoded branch, a stale address in the overlay stack — the
    chain would either fail to connect or land in WAITING.
    """
    _require_gpsim()
    pair = _new_pair(v17_chain_images["shifted"], stock_main_hex)
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None
        assert pair.is_connected(), (
            f"V1.7-shifted+V2.3 never connected; lcd={last.lcd!r} "
            f"flags=0x{last.control_flags:02X}"
        )
        assert not pair.is_waiting(), (
            f"V1.7-shifted+V2.3 stayed in WAITING; lcd={last.lcd!r}"
        )
        assert "Volume:" in last.lcd[0], (
            f"V1.7-shifted+V2.3 did not reach Volume: {last.lcd!r}"
        )
    finally:
        pair.close()


# ---------------------------------------------------------------------------
# Spec §A5 gate #2: blackout/wake leaves chain in WAITING state.
# ---------------------------------------------------------------------------

def _run_blackout_wake(pair: SingleMainChainHarness) -> None:
    last = pair.run_until_connected(limit=140)
    assert last is not None
    assert pair.is_connected(), (
        f"chain never connected; lcd={last.lcd!r} "
        f"flags=0x{last.control_flags:02X}"
    )
    pair.set_blackout(True)
    pair.press("STBY")
    pair.step_many(80)
    assert "ZZZ" in pair.lcd_lines()[0].upper(), (
        f"chain did not enter standby before wake: {pair.lcd_lines()!r}"
    )
    pair.press("STBY")
    waiting = pair.run_until_waiting(limit=20)
    assert waiting is not None
    assert pair.is_waiting(), (
        f"chain did not fall back to WAITING after wake blackout: {waiting.lcd!r}"
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_v17_stock_v16b_blackout_wake_shows_waiting(stock_main_hex: Path) -> None:
    _require_gpsim()
    pair = _new_pair(STOCK_CONTROL_HEX_V16B, stock_main_hex)
    try:
        _run_blackout_wake(pair)
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v17_rebuilt_blackout_wake_shows_waiting(
    v17_chain_images, stock_main_hex: Path
) -> None:
    _require_gpsim()
    pair = _new_pair(v17_chain_images["v17"], stock_main_hex)
    try:
        _run_blackout_wake(pair)
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v17_shifted_blackout_wake_shows_waiting(
    v17_chain_images, stock_main_hex: Path
) -> None:
    _require_gpsim()
    pair = _new_pair(v17_chain_images["shifted"], stock_main_hex)
    try:
        _run_blackout_wake(pair)
    finally:
        pair.close()
