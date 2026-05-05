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

The V1.7 hex images are built once per test module by the
``v17_chain_images`` fixture (scope=module) so the V1.7 source is
assembled at most twice (canonical + shifted) per pytest invocation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    STOCK_CONTROL_HEX_V16B,
    V17_CONTROL_ASM_COMMENTS,
    V17_CONTROL_RAM_INC,
)
from dlcp_fw.sim.v17_symbols import assemble_v17, build_shifted_asm

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
            "run `cargo build --release -p dlcp-sim-py && "
            "bash crates/dlcp-sim-py/build.sh` and retry. "
            f"Underlying error: {_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _assert_v17_chain_reaches_display(control_hex: Path) -> None:
    """Build the rust V1.7-family single-MAIN chain via
    :meth:`Chain.from_v17_chain` (V2.3-combined MAIN by default), run
    the steady-state convergence predicate up to 140 chunks, then
    assert the V1.6b chain parity gates -- ``is_connected``,
    ``not is_waiting``, and ``"Volume:" in lcd[0]``.
    """
    _require_rust()
    chain = RustChain.from_v17_chain(str(control_hex))
    # limit=140 chunks; predicate firing on the 140th iteration counts
    # as success.  We don't gate on the chunk count -- the explicit
    # is_connected / is_waiting / lcd-content assertions below catch
    # non-convergence (run_until_connected returns the limit both when
    # the predicate fires on the last chunk and when it never fires;
    # the post-loop assertions disambiguate).
    chain.run_until_connected(limit=140)
    assert chain.is_connected(), (
        f"chain not connected after run_until_connected; "
        f"tick={chain.current_tick()}, lcd={chain.lcd_lines()!r}"
    )
    assert not chain.is_waiting(), (
        f"chain still in WAITING state; "
        f"tick={chain.current_tick()}, lcd={chain.lcd_lines()!r}"
    )
    assert "Volume:" in chain.lcd_lines()[0], (
        f"chain LCD did not reach Volume screen; "
        f"tick={chain.current_tick()}, lcd={chain.lcd_lines()!r}"
    )


def _run_blackout_wake(control_hex: Path) -> None:
    """Build the rust V1.7-family single-MAIN chain, run to connected
    Volume display, set blackout, press STBY (CONTROL enters Zzz
    standby), step until standby is rendered, press STBY again (wake),
    and confirm CONTROL falls back to WAITING because the chain link
    is blacked out."""
    _require_rust()
    chain = RustChain.from_v17_chain(str(control_hex))
    chain.run_until_connected(limit=140)
    assert chain.is_connected(), (
        f"chain not connected; lcd={chain.lcd_lines()!r}"
    )
    chain.set_blackout(True)
    chain.press("STBY")
    chain.step_many(80)
    assert "ZZZ" in chain.lcd_lines()[0].upper(), (
        f"chain did not enter standby before wake; "
        f"lcd={chain.lcd_lines()!r}"
    )
    chain.press("STBY")
    chain.run_until_waiting(limit=20)
    assert chain.is_waiting(), (
        f"chain did not fall back to WAITING after wake "
        f"blackout; lcd={chain.lcd_lines()!r}"
    )


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


# ---------------------------------------------------------------------------
# Spec §A5 gate #1: chain reaches Volume screen.
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
@pytest.mark.slow
def test_v17_stock_v16b_chain_reaches_display() -> None:
    """Sanity baseline: stock V1.6b CONTROL + stock MAIN V2.3 reach Volume."""
    _assert_v17_chain_reaches_display(STOCK_CONTROL_HEX_V16B)


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v17_rebuilt_chain_reaches_display(v17_chain_images) -> None:
    """V1.7 byte-identical rebuild behaves exactly like stock V1.6b.

    The rebuilt hex is, by construction, byte-identical to
    ``STOCK_CONTROL_HEX_V16B``.  Running it anyway acts as a regression
    gate against an accidental ``assemble_v17`` divergence.
    """
    _assert_v17_chain_reaches_display(v17_chain_images["v17"])


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v17_shifted_chain_reaches_display(v17_chain_images) -> None:
    """V1.7 shifted (+0x222) must still converge to Volume screen.

    If relocation broke anything behaviorally — a missed TBLPTR load,
    a hardcoded branch, a stale address in the overlay stack — the
    chain would either fail to connect or land in WAITING.  The
    PIC18 dispatch is relocation-agnostic, so the same parity gate
    holds.
    """
    _assert_v17_chain_reaches_display(v17_chain_images["shifted"])


# ---------------------------------------------------------------------------
# Spec §A5 gate #2: blackout/wake leaves chain in WAITING state.
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
@pytest.mark.slow
def test_v17_stock_v16b_blackout_wake_shows_waiting() -> None:
    _run_blackout_wake(STOCK_CONTROL_HEX_V16B)


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v17_rebuilt_blackout_wake_shows_waiting(v17_chain_images) -> None:
    _run_blackout_wake(v17_chain_images["v17"])


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v17_shifted_blackout_wake_shows_waiting(v17_chain_images) -> None:
    _run_blackout_wake(v17_chain_images["shifted"])
