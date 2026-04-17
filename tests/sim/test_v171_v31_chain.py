"""V1.71 CONTROL × V3.1 MAIN chain parity tests — final gate.

Spec §Test strategy: ``test_v171_v31_robustness.py`` (this file)
replicates the 2 wire-chain robustness behaviors from the existing
V3.1/V1.63b pair using the source-inlined V1.71 CONTROL instead of
the V1.63b binary overlay.

Because V1.71 inlines all of V1.61b/V1.62b/V1.63b/V1.64b, the chain
behavior should match or strictly improve V1.63b parity:

* **Boot to Volume**: V1.71 + V3.1 MAIN reach the Volume display
  screen (V1.62b+ reconnect handshake traversal, V1.63b BF/08
  absence, V1.71 preset boot init all coexist).
* **Blackout/wake → WAITING**: blackout drops the link and wake
  returns CONTROL to the WAITING screen — with V1.71 Phase C's
  wake-frame-on-reconnect inline, the path is exercised.

Both tests mirror ``test_v17_chain.py`` but target V3.1 MAIN (the
spec's declared V1.71 pairing) rather than stock V2.3 MAIN.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    V17_CONTROL_RAM_INC,
    V171_CONTROL_ASM,
    V31_MAIN_HEX,
)
from dlcp_fw.sim.gpsim import gpsim_available

try:
    from dlcp_fw.sim.chain_gpsim import SingleMainChainHarness
    from dlcp_fw.sim.v17_symbols import assemble_v17
    _CHAIN_IMPORT_OK = True
except Exception:  # pragma: no cover
    _CHAIN_IMPORT_OK = False


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    if not _CHAIN_IMPORT_OK:
        pytest.skip("chain_gpsim harness not importable in this env")
    if not V31_MAIN_HEX.exists():
        pytest.skip(f"missing V3.1 MAIN hex: {V31_MAIN_HEX}")


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_v31_chain")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _new_pair(control_hex: Path) -> SingleMainChainHarness:
    return SingleMainChainHarness(
        control_hex,
        V31_MAIN_HEX,
        fast_boot=False,
        control_chunk_cycles=200_000,
        main_chunk_cycles=200_000,
        hold_cycles=240_000,
        disable_standby_check=False,
        bypass_i2c=False,
        main_transport_mode="native_ring",
    )


# ---------------------------------------------------------------------------
# Gate A: V1.71 + V3.1 reach the Volume screen
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_v31_chain_reaches_display(v171_hex: Path) -> None:
    """V1.71 CONTROL + V3.1 MAIN converge to Volume screen post-connect."""
    _require_gpsim()
    pair = _new_pair(v171_hex)
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None
        assert pair.is_connected(), (
            f"V1.71+V3.1 never connected; lcd={last.lcd!r} "
            f"flags=0x{last.control_flags:02X}"
        )
        assert not pair.is_waiting(), (
            f"V1.71+V3.1 stayed in WAITING; lcd={last.lcd!r}"
        )
        assert "Volume:" in last.lcd[0], (
            f"V1.71+V3.1 did not reach Volume: {last.lcd!r}"
        )
    finally:
        pair.close()


# ---------------------------------------------------------------------------
# Gate B: Blackout/wake → WAITING (exercises V1.62b wake-frame-on-reconnect)
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_v31_blackout_wake_shows_waiting(v171_hex: Path) -> None:
    """After blackout + STBY toggle, V1.71 CONTROL falls back to WAITING."""
    _require_gpsim()
    pair = _new_pair(v171_hex)
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None
        assert pair.is_connected(), (
            f"V1.71+V3.1 never connected; lcd={last.lcd!r} "
            f"flags=0x{last.control_flags:02X}"
        )

        pair.set_blackout(True)
        pair.press("STBY")
        pair.step_many(80)
        assert "ZZZ" in pair.lcd_lines()[0].upper(), (
            f"V1.71+V3.1 did not enter standby before wake: "
            f"{pair.lcd_lines()!r}"
        )

        pair.press("STBY")
        waiting = pair.run_until_waiting(limit=20)
        assert waiting is not None, (
            "V1.71+V3.1 produced no steps while waiting for reconnect"
        )
        assert pair.is_waiting(), (
            f"V1.71+V3.1 did not fall back to WAITING after wake blackout: "
            f"{waiting.lcd!r}"
        )
    finally:
        pair.close()
