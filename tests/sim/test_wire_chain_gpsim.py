from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import PATCHED_MAIN_HEX_V24, PATCHED_MAIN_HEX_V25, V31_MAIN_HEX
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc

pytestmark = [pytest.mark.wire]


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _scan_for_frame(
    raw: list[int], route: int, cmd: int, data: int,
) -> int:
    """Return index of first 3-byte (route, cmd, data) match in `raw`,
    or -1 if not present.  Mirror of the gpsim-side
    ``main_tx_frames(0)`` scan, but operating on a flat byte list."""
    for i in range(len(raw) - 2):
        if raw[i] == route and raw[i + 1] == cmd and raw[i + 2] == data:
            return i
    return -1


def _new_stock_wire_chain(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
) -> WireMultiMainChainHarness:
    return WireMultiMainChainHarness(
        stock_control_hex_v14,
        stock_main_hex,
        main_units=1,
        fast_boot=False,
        disable_standby_check=False,
    )


def _new_patched_wire_chain(
    control_hex: Path,
    main_hex: Path,
) -> WireMultiMainChainHarness:
    return WireMultiMainChainHarness(
        control_hex,
        main_hex,
        main_units=1,
        fast_boot=False,
        disable_standby_check=False,
    )


def _enter_standby(chain: WireMultiMainChainHarness) -> None:
    chain.press("STBY")
    chain.step_many(20)
    assert "ZZZ" in chain.lcd_lines()[0].upper(), f"pair did not enter standby before wake: {chain.lcd_lines()!r}"


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_wire_single_main_chain_exchanges_real_uart_frames(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
    dlcp_sim_backend: str,
) -> None:
    """Stock V1.4 CONTROL + V2.3 MAIN: real UART frames flow over the wire chain.

    The proof-of-life invariant: MAIN0 must emit BF/03/01 (the version
    announce frame) once it boots and CONTROL must consume those bytes
    over the chain.

    Migrated to dual_supported in P4.7.  Both backends boot a CONTROL+MAIN
    wire chain; the rust path uses ``Chain.from_v17_chain`` (which couples
    UART rings between K20 CONTROL and a full-silicon V2.3 MAIN core) and
    captures MAIN's TX via ``tx_record_since_last_capture()`` after
    ``run_until_connected`` reaches the Volume screen.  CONTROL reaching
    the Volume screen on rust requires having consumed MAIN's UART
    replies, so ``is_connected and not is_waiting`` is the
    backend-uniform proxy for both ``main_rx_activity`` and
    ``control_rx_activity`` from the gpsim API.
    """
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v17_chain(str(stock_control_hex_v14))
        c.mark_tx_capture_point()
        used = c.run_until_connected(limit=140)
        assert c.is_connected() and not c.is_waiting(), (
            f"[rust] chain never reached DISPLAY: lcd={c.lcd_lines()!r} "
            f"used_chunks={used}"
        )
        raw = c.tx_record_since_last_capture()
        assert _scan_for_frame(raw, 0xBF, 0x03, 0x01) >= 0, (
            f"[rust] MAIN0 never emitted BF/03/01; last 30 bytes: "
            f"{[hex(b) for b in raw[-30:]]}"
        )
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        chain = _new_stock_wire_chain(stock_control_hex_v14, stock_main_hex)
        try:
            assert not chain.mains[0].uses_adc_boot_wait_hook

            last = chain.run_until_main_reply(limit=45, main_index=0)
            assert last is not None, "[gpsim] wire chain never produced a step result"
            assert chain.main_rx_activity(0), "[gpsim] MAIN0 never showed native RX activity from CONTROL"
            assert chain.control_rx_activity(), "[gpsim] CONTROL never consumed UART data from MAIN0"

            frames = chain.main_tx_frames(0)
            assert frames, "[gpsim] MAIN0 never emitted a UART reply over the wire bridge"
            assert any((f.route, f.cmd, f.data) == (0xBF, 0x03, 0x01) for f in frames), frames[-10:]
        finally:
            chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("control_fixture", "main_hex", "case_id"),
    [
        pytest.param("patched_control_hex_v161b", PATCHED_MAIN_HEX_V24, "v161b_v24", id="v161b_v24"),
        pytest.param("patched_control_hex_v162b", PATCHED_MAIN_HEX_V25, "v162b_v25", id="v162b_v25"),
        pytest.param("patched_control_hex_v162b", V31_MAIN_HEX, "v162b_v31", id="v162b_v31"),
    ],
)
def test_wire_supported_patched_pairs_reach_display(
    request: pytest.FixtureRequest,
    control_fixture: str,
    main_hex: Path,
    case_id: str,
) -> None:
    _require_gpsim()
    control_hex = request.getfixturevalue(control_fixture)
    chain = _new_patched_wire_chain(control_hex, main_hex)
    try:
        last = chain.run_until_connected(limit=60)
        assert last is not None, f"{case_id} never reached DISPLAY in wire mode"
        assert last.lcd[0].startswith("Volume:"), last.lcd
        assert "Auto Detect" in last.lcd[1], last.lcd
        assert last.control_flags & 0x02, hex(last.control_flags)
        assert chain.control_rx_activity(), f"{case_id} CONTROL never consumed wire UART data"
        assert chain.main_rx_activity(0), f"{case_id} MAIN never consumed wire UART data"
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "main_hex",
    [
        pytest.param(PATCHED_MAIN_HEX_V24, id="v161b_v24"),
        pytest.param(PATCHED_MAIN_HEX_V25, id="v161b_v25"),
    ],
)
def test_wire_v161b_bounded_wake_main_reply_drop_strands_both_versions(
    patched_control_hex_v161b: Path,
    main_hex: Path,
) -> None:
    _require_gpsim()
    chain = _new_patched_wire_chain(patched_control_hex_v161b, main_hex)
    try:
        first = chain.run_until_connected(limit=60)
        assert first is not None, "pair never reached DISPLAY before wake drop fault"

        _enter_standby(chain)

        chain.set_link_fault("m0_to_ctl", drop=True)
        chain.press("STBY")
        saw_wait = False
        for _ in range(3):
            step = chain.step()
            saw_wait = saw_wait or chain.is_waiting()
            assert step is not None

        chain.clear_link_faults()
        recovered = chain.run_until_connected(limit=120)
        assert saw_wait, "pair never entered WAITING during bounded reply drop"
        assert recovered is not None, "pair produced no steps after reply drop fault clear"
        assert not chain.is_connected(), f"pair unexpectedly reconnected after bounded reply drop: {recovered.lcd!r}"
        assert chain.is_waiting(), f"pair left WAITING after bounded reply drop: {recovered.lcd!r}"
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "main_hex",
    [
        pytest.param(PATCHED_MAIN_HEX_V24, id="v161b_v24"),
        pytest.param(PATCHED_MAIN_HEX_V25, id="v161b_v25"),
    ],
)
def test_wire_v161b_bounded_wake_main_reply_delay_strands_both_versions(
    patched_control_hex_v161b: Path,
    main_hex: Path,
) -> None:
    _require_gpsim()
    chain = _new_patched_wire_chain(patched_control_hex_v161b, main_hex)
    try:
        first = chain.run_until_connected(limit=60)
        assert first is not None, "pair never reached DISPLAY before wake delay fault"

        _enter_standby(chain)

        chain.set_link_fault("m0_to_ctl", extra_cycles=10_000_000)
        chain.press("STBY")
        saw_wait = False
        for _ in range(2):
            step = chain.step()
            saw_wait = saw_wait or chain.is_waiting()
            assert step is not None

        chain.clear_link_faults()
        recovered = chain.run_until_connected(limit=120)
        assert saw_wait, "pair never entered WAITING during bounded reply delay"
        assert recovered is not None, "pair produced no steps after reply delay clear"
        assert not chain.is_connected(), f"pair unexpectedly reconnected after bounded reply delay: {recovered.lcd!r}"
        assert chain.is_waiting(), f"pair left WAITING after bounded reply delay: {recovered.lcd!r}"
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "main_hex",
    [
        pytest.param(PATCHED_MAIN_HEX_V24, id="v162b_v24"),
        pytest.param(PATCHED_MAIN_HEX_V25, id="v162b_v25"),
    ],
)
def test_wire_v162b_bounded_wake_delay_release_recovers_both_versions(
    patched_control_hex_v162b: Path,
    main_hex: Path,
) -> None:
    _require_gpsim()
    chain = _new_patched_wire_chain(patched_control_hex_v162b, main_hex)
    try:
        first = chain.run_until_connected(limit=60)
        assert first is not None, "pair never reached DISPLAY before wake burst-pressure fault"

        _enter_standby(chain)

        chain.set_link_fault("m0_to_ctl", extra_cycles=10_000_000)
        chain.press("STBY")
        held = chain.step_many(2)
        assert held is not None, "pair produced no steps during bounded reply delay"
        assert chain.is_waiting(), f"pair never entered WAITING during bounded reply delay: {held.lcd!r}"

        chain.clear_link_faults()
        recovered = chain.run_until_connected(limit=120)
        assert recovered is not None, "pair produced no steps after delayed-reply release"
        assert chain.is_connected(), f"pair never reconnected after delayed-reply release: {recovered.lcd!r}"
        assert not chain.is_waiting(), f"pair stayed in WAITING after delayed-reply release: {recovered.lcd!r}"
        assert "Volume:" in recovered.lcd[0], f"unexpected recovered LCD after delayed-reply release: {recovered.lcd!r}"
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_wire_main_to_control_blackout_is_unidirectional(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
) -> None:
    _require_gpsim()
    chain = _new_stock_wire_chain(stock_control_hex_v14, stock_main_hex)
    try:
        first = chain.run_until_main_reply(limit=45, main_index=0)
        assert first is not None, "wire chain never produced a baseline UART reply"
        assert chain.control_rx_activity(), "CONTROL never consumed any baseline UART data"
        assert chain.main_rx_activity(0), "MAIN0 never consumed any baseline UART data"

        chain.set_link_fault("m0_to_ctl", drop=True)
        drained = chain.step_many(8)
        assert drained is not None, "wire chain produced no steps during blackout drain"

        control_rx_hold = (drained.control_rx_rd, drained.control_rx_wr)
        main_tx_count = len(chain.main_tx_frames(0))
        held = chain.step_many(8)
        assert held is not None, "wire chain produced no steps during one-way blackout"

        assert (held.control_rx_rd, held.control_rx_wr) == control_rx_hold
        assert len(chain.main_tx_frames(0)) > main_tx_count, "MAIN0 stopped emitting replies under one-way blackout"
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_wire_main_to_control_delay_holds_future_replies_after_backlog_drain(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
) -> None:
    _require_gpsim()
    chain = _new_stock_wire_chain(stock_control_hex_v14, stock_main_hex)
    try:
        first = chain.run_until_main_reply(limit=45, main_index=0)
        assert first is not None, "wire chain never produced a baseline UART reply"

        chain.set_link_fault("m0_to_ctl", extra_cycles=30_000_000)
        # One already-queued status burst may still arrive after the fault is
        # armed. Drain that backlog, then confirm later replies stay delayed.
        settled = chain.step()
        control_rx_hold = (settled.control_rx_rd, settled.control_rx_wr)
        main_tx_count = len(chain.main_tx_frames(0))
        delayed = chain.step_many(5)
        assert delayed is not None, "wire chain produced no steps while delaying replies"

        assert (delayed.control_rx_rd, delayed.control_rx_wr) == control_rx_hold
        assert len(chain.main_tx_frames(0)) > main_tx_count, "MAIN0 stopped emitting replies while delay was active"
    finally:
        chain.close()
