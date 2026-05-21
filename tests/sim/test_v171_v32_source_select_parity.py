"""V1.6b/V2.3 vs V1.71/V3.2 source-selection parity tests.

These tests pin the source-selection behavior that matters for a two-MAIN
chain: CONTROL's emitted manual-source frames, each MAIN's cmd 0x06 route
decision, and V3.2's current SRC4382 route priming on both PB roles.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    STOCK_CONTROL_HEX_V16B,
    STOCK_MAIN_COMBINED_HEX,
    V171_CONTROL_HEX,
    V32_MAIN_ASM,
)
from dlcp_fw.sim.v30_symbols import assemble_v30


SRC_ROUTE_STATUS = 0x05F
EVENT_FLAGS = 0x07E
INPUT_SELECT = 0x099
SRC_ROUTE_REQUEST = 0x093
ROUTE_SHADOW = 0x0AB
INPUT_SELECT_MIRROR = 0x0B3
I2C_SLOW_COUNTER = 0x0BB
RX_RING_RD = 0x0C6
RX_RING_WR = 0x0C7
RX_RING_BASE = 0x0200
RX_RING_SIZE = 0xC0

SRC_REG_RX_CONTROL = 0x0D
SRC_REG_TX_CONTROL_2 = 0x08
TAS_REG_VOLUME_COEFF = 0x30

CONTROL_INPUT_INDEX = 0x0B7
CONTROL_INPUT_SELECT_CACHE = 0x0B8
CONTROL_DISPLAY_STATE = 0x0BF

COMMAND_SETTLE_TICKS = 4_000_000
FRONT_PANEL_SETTLE_TICKS = 10_000_000
CONTROL_TAP_TICKS = 5_000_000

CONTROL_BUTTON_PINS = {
    "RIGHT": ("A", 4),
    "UP": ("C", 0),
}

MENU_SOURCE_SEQUENCE = [0x05, 0x06, 0x07, 0x08, 0x01, 0x02, 0x03, 0x04]
MENU_SOURCE_LABELS = [
    "S/PDIF          ",
    "USB Audio       ",
    "AES             ",
    "Optical         ",
    "Analogue 1      ",
    "Analogue 2      ",
    "Analogue 3      ",
    "Analogue 4      ",
]

ROUTE_BY_STATUS_AND_INPUT = {
    0x00: {0x01: 0, 0x02: 1, 0x03: 3, 0x04: 3, 0x05: 4, 0x06: 0, 0x07: 0, 0x08: 0},
    0x01: {0x01: 0, 0x02: 5, 0x03: 1, 0x04: 3, 0x05: 3, 0x06: 4, 0x07: 0, 0x08: 0},
    0x02: {0x01: 0, 0x02: 5, 0x03: 6, 0x04: 1, 0x05: 3, 0x06: 3, 0x07: 4, 0x08: 0},
    0x03: {0x01: 0, 0x02: 5, 0x03: 6, 0x04: 7, 0x05: 1, 0x06: 3, 0x07: 3, 0x08: 4},
}

SRC_PAIR_BY_ROUTE = {
    0: (0x08, 0x30),
    1: (0x09, 0x70),
    2: (0x0A, 0xB0),
    3: (0x08, 0x30),
    4: (0x0B, 0xF0),
    5: (0x08, 0x30),
    6: (0x08, 0x30),
    7: (0x08, 0x30),
}


@dataclass(frozen=True)
class RouteSnapshot:
    input_select: int
    input_select_mirror: int
    route_request: int
    route_shadow: int


@dataclass(frozen=True)
class FrontPanelResult:
    emitted_sources: list[int]
    source_labels: list[str]
    final_lcd: tuple[str, str]
    route_snapshot: tuple[RouteSnapshot, RouteSnapshot]


@pytest.fixture(scope="module")
def v32_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_v32_source_select_parity")
    hex_out = tmp / "DLCP_Firmware_V3.2.hex"
    assemble_v30(V32_MAIN_ASM, hex_out)
    return hex_out


def _rust_chain():
    try:
        from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"rust dlcp_sim_native facade not importable -- {exc!r}")
    return RustChain


def _boot_stock_chain():  # type: ignore[no-untyped-def]
    chain = _rust_chain().from_v171_v32(
        control_hex_path=str(STOCK_CONTROL_HEX_V16B),
        main_hex_path=str(STOCK_MAIN_COMBINED_HEX),
    )
    chunks = chain.run_until_connected(limit=300)
    assert chunks < 300, f"stock chain did not connect; lcd={chain.lcd_lines()!r}"
    return chain


def _boot_current_chain(v32_hex: Path):  # type: ignore[no-untyped-def]
    chain = _rust_chain().from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(v32_hex),
    )
    chunks = chain.run_until_connected(limit=300)
    assert chunks < 300, f"current chain did not connect; lcd={chain.lcd_lines()!r}"
    return chain


def _tap_control_key(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = CONTROL_BUTTON_PINS[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(CONTROL_TAP_TICKS)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(CONTROL_TAP_TICKS)


def _navigate_to_input_menu(chain, *, right_taps: int) -> None:  # type: ignore[no-untyped-def]
    for _ in range(right_taps):
        _tap_control_key(chain, "RIGHT")
    assert chain.lcd_lines()[0] == "Input:          "


def _prepare_mains_for_manual_case(chain, source_status: int) -> None:  # type: ignore[no-untyped-def]
    for unit in (0, 1):
        chain.write_main_reg(unit, SRC_ROUTE_STATUS, source_status)
        chain.write_main_reg(unit, SRC_ROUTE_REQUEST, 0x00)
        chain.write_main_reg(unit, ROUTE_SHADOW, 0x7F)
        chain.write_main_reg(unit, INPUT_SELECT, 0x00)
        chain.write_main_reg(unit, INPUT_SELECT_MIRROR, 0x00)
        chain.write_main_reg(unit, I2C_SLOW_COUNTER, 0x65)
        chain.write_main_reg(unit, EVENT_FLAGS, 0x00)
        chain.write_main_reg(unit, RX_RING_RD, chain.read_main_reg(unit, RX_RING_WR))
        chain.poke_main_src4382_reg(unit, SRC_REG_RX_CONTROL, 0xEE)
        chain.poke_main_src4382_reg(unit, SRC_REG_TX_CONTROL_2, 0xDD)
        chain.reset_main_src4382_stats(unit)
        chain.reset_main_dsp_write_log(unit)


def _inject_main_chain_frame(chain, unit: int, frame: tuple[int, int, int]) -> None:  # type: ignore[no-untyped-def]
    rd = chain.read_main_reg(unit, RX_RING_RD) % RX_RING_SIZE
    wr = chain.read_main_reg(unit, RX_RING_WR) % RX_RING_SIZE
    used = (wr + RX_RING_SIZE - rd) % RX_RING_SIZE
    free = RX_RING_SIZE - 1 - used
    assert free >= len(frame), f"MAIN{unit} RX ring full: free={free}, frame={frame!r}"
    for byte in frame:
        chain.write_main_reg(unit, RX_RING_BASE + wr, byte & 0xFF)
        wr = (wr + 1) % RX_RING_SIZE
    chain.write_main_reg(unit, RX_RING_WR, wr)


def _inject_manual_source_both_units(chain, input_select: int) -> None:  # type: ignore[no-untyped-def]
    frame = (0xB0, 0x06, input_select)
    _inject_main_chain_frame(chain, 0, frame)
    _inject_main_chain_frame(chain, 1, frame)
    chain.step_ticks(COMMAND_SETTLE_TICKS)


def _route_snapshot(chain) -> tuple[RouteSnapshot, RouteSnapshot]:  # type: ignore[no-untyped-def]
    return tuple(
        RouteSnapshot(
            input_select=chain.read_main_reg(unit, INPUT_SELECT),
            input_select_mirror=chain.read_main_reg(unit, INPUT_SELECT_MIRROR),
            route_request=chain.read_main_reg(unit, SRC_ROUTE_REQUEST),
            route_shadow=chain.read_main_reg(unit, ROUTE_SHADOW),
        )
        for unit in (0, 1)
    )


def _expected_route_snapshot(input_select: int, route: int) -> tuple[RouteSnapshot, RouteSnapshot]:
    expected = RouteSnapshot(
        input_select=input_select,
        input_select_mirror=input_select,
        route_request=route,
        route_shadow=route,
    )
    return (expected, expected)


def _wait_for_route_snapshot(
    chain,  # type: ignore[no-untyped-def]
    expected: tuple[RouteSnapshot, RouteSnapshot],
    context: str,
) -> tuple[RouteSnapshot, RouteSnapshot]:
    for _ in range(40):
        snapshot = _route_snapshot(chain)
        if snapshot == expected:
            return snapshot
        chain.step_ticks(500_000)
    pytest.fail(f"{context} did not converge to {expected!r}; got {_route_snapshot(chain)!r}")


def _assert_main_rx_drained(chain) -> None:  # type: ignore[no-untyped-def]
    for unit in (0, 1):
        assert chain.read_main_reg(unit, RX_RING_RD) == chain.read_main_reg(unit, RX_RING_WR)


def _menu_source_result(chain, *, right_taps: int) -> FrontPanelResult:  # type: ignore[no-untyped-def]
    _navigate_to_input_menu(chain, right_taps=right_taps)

    emitted_sources: list[int] = []
    source_labels: list[str] = []
    for _ in range(len(MENU_SOURCE_SEQUENCE)):
        before = len(chain.tx_frames())
        _tap_control_key(chain, "UP")
        chain.step_ticks(2_000_000)
        new_sources = [
            frame[2]
            for frame in chain.tx_frames()[before:]
            if frame[0] == 0xB0 and frame[1] == 0x06
        ]
        assert len(new_sources) == 1, chain.tx_frames()[before:]
        emitted_sources.extend(new_sources)
        source_labels.append(chain.lcd_lines()[1])

    return FrontPanelResult(
        emitted_sources=emitted_sources,
        source_labels=source_labels,
        final_lcd=chain.lcd_lines(),
        route_snapshot=_route_snapshot(chain),
    )


def test_front_panel_input_menu_emits_same_manual_source_sequence_as_stock(
    v32_hex: Path,
) -> None:
    stock = _menu_source_result(_boot_stock_chain(), right_taps=1)
    current = _menu_source_result(_boot_current_chain(v32_hex), right_taps=2)

    assert stock.emitted_sources == MENU_SOURCE_SEQUENCE
    assert current.emitted_sources == stock.emitted_sources
    assert stock.source_labels == MENU_SOURCE_LABELS
    assert current.source_labels == stock.source_labels
    assert stock.final_lcd == current.final_lcd == ("Input:          ", "Analogue 4      ")


def test_manual_source_route_matrix_matches_stock_for_both_pb_roles(
    v32_hex: Path,
) -> None:
    stock = _boot_stock_chain()
    current = _boot_current_chain(v32_hex)
    stock.set_blackout(True)
    current.set_blackout(True)

    for source_status, routes_by_input in ROUTE_BY_STATUS_AND_INPUT.items():
        for input_select, expected_route in routes_by_input.items():
            context = f"status=0x{source_status:02X} input=0x{input_select:02X}"
            expected = _expected_route_snapshot(input_select, expected_route)

            _prepare_mains_for_manual_case(stock, source_status)
            _inject_manual_source_both_units(stock, input_select)
            stock_snapshot = _wait_for_route_snapshot(stock, expected, f"stock {context}")

            _prepare_mains_for_manual_case(current, source_status)
            _inject_manual_source_both_units(current, input_select)
            current_snapshot = _wait_for_route_snapshot(current, expected, f"current {context}")

            assert stock_snapshot == expected, f"stock mismatch for {context}: {stock_snapshot!r}"
            assert current_snapshot == expected, f"current mismatch for {context}: {current_snapshot!r}"
            assert current_snapshot == stock_snapshot, f"parity mismatch for {context}"


def test_displayed_spdif_front_panel_path_matches_stock_for_both_pb_roles(
    v32_hex: Path,
) -> None:
    cases = [
        ("stock", _boot_stock_chain(), 1),
        ("current", _boot_current_chain(v32_hex), 2),
    ]

    for label, chain, right_taps in cases:
        _navigate_to_input_menu(chain, right_taps=right_taps)
        _prepare_mains_for_manual_case(chain, source_status=0x03)

        before = len(chain.tx_frames())
        _tap_control_key(chain, "UP")
        chain.step_ticks(FRONT_PANEL_SETTLE_TICKS)

        new_frames = chain.tx_frames()[before:]
        assert (0xB0, 0x06, 0x05) in new_frames, f"{label} frames={new_frames!r}"
        assert chain.lcd_lines() == ("Input:          ", "S/PDIF          ")
        assert chain.read_reg(CONTROL_INPUT_INDEX) == 0x01
        assert chain.read_reg(CONTROL_INPUT_SELECT_CACHE) == 0x05
        assert chain.read_reg(CONTROL_DISPLAY_STATE) in (0x01, 0x02)
        assert _route_snapshot(chain) == _expected_route_snapshot(input_select=0x05, route=1)

        for unit in (0, 1):
            assert chain.read_main_src4382_reg(unit, SRC_REG_RX_CONTROL) == 0x09
            assert chain.read_main_src4382_reg(unit, SRC_REG_TX_CONTROL_2) == 0x70
            assert 0x09 in chain.read_main_src4382_write_values(unit, SRC_REG_RX_CONTROL)
            assert 0x70 in chain.read_main_src4382_write_values(unit, SRC_REG_TX_CONTROL_2)
            assert chain.read_main_dsp_write_payload(unit, TAS_REG_VOLUME_COEFF) is not None
        _assert_main_rx_drained(chain)


def test_current_source_present_routes_program_src4382_on_both_pb_roles(
    v32_hex: Path,
) -> None:
    chain = _boot_current_chain(v32_hex)
    chain.set_blackout(True)
    source_status = 0x03

    for input_select, expected_route in ROUTE_BY_STATUS_AND_INPUT[source_status].items():
        _prepare_mains_for_manual_case(chain, source_status)
        _inject_manual_source_both_units(chain, input_select)

        expected = _expected_route_snapshot(input_select, expected_route)
        assert _wait_for_route_snapshot(chain, expected, f"current input=0x{input_select:02X}") == expected
        expected_rx, expected_tx = SRC_PAIR_BY_ROUTE[expected_route]

        for unit in (0, 1):
            assert chain.read_main_src4382_reg(unit, SRC_REG_RX_CONTROL) == expected_rx
            assert chain.read_main_src4382_reg(unit, SRC_REG_TX_CONTROL_2) == expected_tx
            assert expected_rx in chain.read_main_src4382_write_values(unit, SRC_REG_RX_CONTROL)
            assert expected_tx in chain.read_main_src4382_write_values(unit, SRC_REG_TX_CONTROL_2)
            assert chain.read_main_dsp_write_payload(unit, TAS_REG_VOLUME_COEFF) is not None


def test_autodetect_startup_selected_state_matches_stock_for_both_pb_roles(
    v32_hex: Path,
) -> None:
    expected = _expected_route_snapshot(input_select=0x00, route=0)

    stock = _boot_stock_chain()
    current = _boot_current_chain(v32_hex)

    assert _route_snapshot(stock) == expected
    assert _route_snapshot(current) == expected
