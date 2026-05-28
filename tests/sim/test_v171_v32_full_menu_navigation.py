"""V1.71/V3.2 full visible menu navigation coverage.

These tests exercise the front-panel menu paths that a user can reach with
physical keys.  The stock V1.6b baseline is kept in the same file so current
V1.71 expectations are anchored to a known-good menu shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM, V32_MAIN_HEX
from dlcp_fw.sim.v17_symbols import assemble_v17


pytestmark = pytest.mark.dual_supported


try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


CONTROL_TAP_TICKS = 5_000_000
DISPLAY_STATE_INDEX = 0x0BF
HEALTH_AGE_PB1 = 0x1B0
HEALTH_AGE_PB2 = 0x1B1
HEALTH_SEEN_MASK = 0x1B2
HEALTH_FLAGS = 0x1B3
HEALTH_DISPLAY_DIRTY = 2
HEALTH_STALE_AGE = 0x03
PINS = {
    "STBY": ("A", 3),
    "UP": ("C", 0),
    "DOWN": ("A", 2),
    "SELECT": ("A", 1),
    "RIGHT": ("A", 4),
    "LEFT": ("C", 5),
}

STOCK_INPUT_OPTIONS = (
    "Auto Detect",
    "S/PDIF",
    "USB Audio",
    "AES",
    "Optical",
    "Analogue 1",
    "Analogue 2",
    "Analogue 3",
    "Analogue 4",
)
TIMEOUT_OPTIONS = ("30 sec", "2 min", "5 min", "Off (no timeout)")


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_full_menu_navigation")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _tap(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = PINS[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(CONTROL_TAP_TICKS)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(CONTROL_TAP_TICKS)


def _settle(chain, steps: int = 8) -> None:  # type: ignore[no-untyped-def]
    for _ in range(steps):
        chain.step()


def _settle_tcy(chain, chunks: int = 50) -> None:  # type: ignore[no-untyped-def]
    for _ in range(chunks):
        chain.step_tcy(1_000)


def _press(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    _tap(chain, key)
    _settle(chain)


def _line_text(chain) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    line0, line1 = chain.lcd_lines()
    return line0.rstrip(), line1.rstrip()


def _stock_chain():  # type: ignore[no-untyped-def]
    _require_rust()
    chain = RustChain.from_v16b_v23()
    assert chain.run_until_connected(limit=300) < 300
    return chain


def _v171_chain(v171_hex: Path):  # type: ignore[no-untyped-def]
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(V32_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=300) < 300
    return chain


def _navigate_right_to(chain, title: str, *, limit: int = 8) -> None:  # type: ignore[no-untyped-def]
    for _ in range(limit):
        if _line_text(chain)[0] == title:
            return
        _press(chain, "RIGHT")
    pytest.fail(f"did not reach {title!r}; lcd={chain.lcd_lines()!r}")


def test_stock_v16b_v23_menu_structure_is_known_good() -> None:
    chain = _stock_chain()

    assert _line_text(chain)[0].startswith("Volume:")
    right_titles = []
    for _ in range(3):
        _press(chain, "RIGHT")
        right_titles.append(_line_text(chain)[0])
    assert right_titles == ["Input:", "Setup", "Volume:-17.0dB"]

    _navigate_right_to(chain, "Input:")
    input_options = []
    for _ in range(len(STOCK_INPUT_OPTIONS)):
        input_options.append(_line_text(chain)[1])
        _press(chain, "UP")
    assert tuple(input_options) == STOCK_INPUT_OPTIONS
    assert _line_text(chain)[1] == STOCK_INPUT_OPTIONS[0]

    _navigate_right_to(chain, "Setup")
    assert _line_text(chain) == ("Setup", "BL Timeout")
    _press(chain, "SELECT")
    timeout_options = []
    for _ in range(len(TIMEOUT_OPTIONS)):
        timeout_options.append(_line_text(chain)[1])
        _press(chain, "UP")
    assert tuple(timeout_options) == TIMEOUT_OPTIONS
    assert _line_text(chain)[1] == TIMEOUT_OPTIONS[0]
    _press(chain, "SELECT")
    assert _line_text(chain) == ("Setup", "BL Timeout")


def test_v171_v32_top_level_ring_reaches_every_menu(v171_hex: Path) -> None:
    chain = _v171_chain(v171_hex)

    assert _line_text(chain)[0].startswith("Volume:")
    right_titles = []
    right_states = []
    for _ in range(6):
        _press(chain, "RIGHT")
        line0, _ = _line_text(chain)
        right_titles.append(line0)
        right_states.append(chain.read_reg(DISPLAY_STATE_INDEX))

    assert right_titles[0:3] == ["Preset", "Input:", "Setup"]
    assert right_titles[3].startswith("PB1")
    assert right_titles[4].startswith("PB2")
    assert right_titles[5].startswith("Volume:")
    assert right_states == [1, 2, 3, 4, 5, 0]

    left_titles = []
    left_states = []
    for _ in range(6):
        _press(chain, "LEFT")
        line0, _ = _line_text(chain)
        left_titles.append(line0)
        left_states.append(chain.read_reg(DISPLAY_STATE_INDEX))

    assert left_titles[0].startswith("PB2")
    assert left_titles[1].startswith("PB1")
    assert left_titles[2] == "Setup"
    assert left_titles[3:5] == ["Input:", "Preset"]
    assert left_titles[5].startswith("Volume:")
    assert left_states == [5, 4, 3, 2, 1, 0]


def test_v171_v32_preset_and_input_menus_are_navigable(v171_hex: Path) -> None:
    chain = _v171_chain(v171_hex)

    _navigate_right_to(chain, "Preset")
    assert _line_text(chain) == ("Preset", "Active: A")
    _press(chain, "DOWN")
    assert _line_text(chain) == ("Preset", "Active: B")
    _press(chain, "UP")
    assert _line_text(chain) == ("Preset", "Active: A")

    _navigate_right_to(chain, "Input:")
    input_options = []
    for _ in range(len(STOCK_INPUT_OPTIONS)):
        input_options.append(_line_text(chain)[1])
        _press(chain, "UP")
    assert tuple(input_options) == STOCK_INPUT_OPTIONS
    assert _line_text(chain)[1] == STOCK_INPUT_OPTIONS[0]

    down_options = []
    for _ in range(len(STOCK_INPUT_OPTIONS)):
        down_options.append(_line_text(chain)[1])
        _press(chain, "DOWN")
    assert tuple(down_options) == (
        "Auto Detect",
        "Analogue 4",
        "Analogue 3",
        "Analogue 2",
        "Analogue 1",
        "Optical",
        "AES",
        "USB Audio",
        "S/PDIF",
    )
    assert _line_text(chain)[1] == STOCK_INPUT_OPTIONS[0]


def test_v171_v32_setup_timeout_editor_is_navigable(v171_hex: Path) -> None:
    chain = _v171_chain(v171_hex)

    _navigate_right_to(chain, "Setup")
    assert _line_text(chain) == ("Setup", "BL Timeout")
    _press(chain, "SELECT")
    assert _line_text(chain) == ("BL Timeout", "30 sec")

    timeout_options = []
    for _ in range(len(TIMEOUT_OPTIONS)):
        timeout_options.append(_line_text(chain)[1])
        _press(chain, "UP")
    assert tuple(timeout_options) == TIMEOUT_OPTIONS
    assert _line_text(chain)[1] == TIMEOUT_OPTIONS[0]

    down_options = []
    for _ in range(len(TIMEOUT_OPTIONS)):
        down_options.append(_line_text(chain)[1])
        _press(chain, "DOWN")
    assert tuple(down_options) == ("30 sec", "Off (no timeout)", "5 min", "2 min")
    assert _line_text(chain)[1] == TIMEOUT_OPTIONS[0]

    _press(chain, "SELECT")
    assert _line_text(chain) == ("Setup", "BL Timeout")


def test_v171_v32_setup_editor_defers_health_suffix_until_exit(v171_hex: Path) -> None:
    chain = _v171_chain(v171_hex)

    _navigate_right_to(chain, "Setup")
    _press(chain, "SELECT")
    for _ in range(3):
        _press(chain, "UP")
    assert _line_text(chain) == ("BL Timeout", "Off (no timeout)")

    chain.set_blackout(True)
    chain.write_reg(HEALTH_AGE_PB1, HEALTH_STALE_AGE)
    chain.write_reg(HEALTH_AGE_PB2, 0)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _settle_tcy(chain)

    assert _line_text(chain) == ("BL Timeout", "Off (no timeout)")

    _press(chain, "SELECT")
    _settle_tcy(chain)

    assert chain.lcd_lines()[0] == "Setup           "
    assert chain.lcd_lines()[1] == "BL Timeout    !1"


def test_v171_source_uses_symbolic_bl_timeout_option_table_pointer() -> None:
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    assert "menu_bl_timeout_options_table:" in text
    assert "HIGH(menu_bl_timeout_options_table)" in text
    assert "LOW(menu_bl_timeout_options_table)" in text

    pointer_load = text[
        text.index("menu_bl_timeout_options_table:") :
        text.index("flow_main_event_loop_1532:")
    ]
    assert "movlw   0x14" not in pointer_load
    assert "movlw   0xce" not in pointer_load
