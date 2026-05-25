"""V1.71 stale Setup-index migration guard.

Field units upgraded from older CONTROL releases may retain a nonzero
``EEPROM[0x01]`` setup-submenu byte.  Stock V1.6b and the V1.71 source
rewrite load that byte into RAM ``0x0BA``; the Setup page then uses it as
the row-2 string-table index.  Since V1.6b/V1.71 only has one visible
Setup row, any nonzero value renders program bytes as LCD garbage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM, V32_MAIN_HEX
from dlcp_fw.sim.v17_symbols import assemble_v17

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


SETUP_INDEX_RAM = 0x0BA
SETUP_INDEX_EEPROM = 0x01
CONTROL_TAP_TICKS = 5_000_000
CONTROL_BUTTON_PINS = {
    "RIGHT": ("A", 4),
}


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_setup_index_clamp")
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


def _tap_control_key(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = CONTROL_BUTTON_PINS[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(CONTROL_TAP_TICKS)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(CONTROL_TAP_TICKS)


def _navigate_to_setup(chain) -> None:  # type: ignore[no-untyped-def]
    for _ in range(3):
        _tap_control_key(chain, "RIGHT")
    assert chain.lcd_lines()[0] == "Setup           ", chain.lcd_lines()


@pytest.mark.slow
@pytest.mark.parametrize("stale_setup_index", [0x01, 0x06, 0xFF])
def test_v171_clamps_stale_setup_index_before_setup_render(
    v171_hex: Path,
    stale_setup_index: int,
) -> None:
    """A stale setup-submenu EEPROM byte must not render code bytes on LCD."""
    _require_rust()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(V32_MAIN_HEX),
    )
    chain.write_control_eeprom_byte(SETUP_INDEX_EEPROM, stale_setup_index)

    chunks = chain.run_until_connected(limit=300)
    assert chunks < 300, f"chain did not connect; lcd={chain.lcd_lines()!r}"
    assert chain.read_reg(SETUP_INDEX_RAM) == 0x00

    _navigate_to_setup(chain)
    assert chain.lcd_lines() == ("Setup           ", "BL Timeout      ")


def test_v171_source_keeps_setup_index_clamp_after_settings_load() -> None:
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    settings_load = text.index("call    settings_load_eeprom")
    preset_boot = text.index("V1.71 inline (V1.61b): preset boot init", settings_load)
    body = text[settings_load:preset_boot]

    assert "movlb   0x00" in body
    assert "movf    0xba, W, B" in body
    assert "bz      v171_setup_index_clamp_done" in body
    assert "clrf    0xba, B" in body
    assert "movwf   EEADR, A" in body
    assert "clrf    WREG, A" in body
    assert "call    eeprom_write_byte" in body
