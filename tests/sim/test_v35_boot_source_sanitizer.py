"""V3.5 boot source sanitizer must clamp each channel independently."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V35_MAIN_ASM, V35_MAIN_HEX
from dlcp_fw.sim.v30_symbols import assemble_v30

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


ACTIVE_FLAGS = 0x05E
ACTIVE_GATE_MASK = 0x08

CHANNEL_EEPROM_BASE = 0x07
CHANNEL_PRIMARY_BASE = 0x060
CHANNEL_SHADOW_BASE = 0x0A5

BOOT_TCY = 16_000_000
RESTORE_SETTLE_TICKS = 40_000_000


@pytest.fixture(scope="module")
def v35_source_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v35_boot_source_sanitizer")
    hex_out = tmp / "DLCP_Firmware_V3.5.hex"
    assemble_v30(V35_MAIN_ASM, hex_out)
    return hex_out


@pytest.fixture(scope="module", params=["source", "canonical"])
def v35_main_hex(request: pytest.FixtureRequest, v35_source_hex: Path) -> Path:
    return v35_source_hex if request.param == "source" else V35_MAIN_HEX


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _boot_with_source_seed(hex_path: Path, sources: list[int]):  # type: ignore[no-untyped-def]
    _require_rust()
    assert len(sources) == 6
    chain = RustChain.from_v3x_main_only(str(hex_path))
    for offset, value in enumerate(sources):
        chain.write_main_eeprom_byte(0, CHANNEL_EEPROM_BASE + offset, value)
    chain.step_tcy(BOOT_TCY)
    chain.step_ticks(RESTORE_SETTLE_TICKS)
    assert chain.read_reg(ACTIVE_FLAGS) & ACTIVE_GATE_MASK
    return chain


def _channel_sources(chain, base: int) -> list[int]:  # type: ignore[no-untyped-def]
    return [chain.read_reg(base + offset) & 0xFF for offset in range(6)]


def test_v35_boot_clamps_corrupt_channel6_without_mutating_channel5_or_shadows(
    v35_main_hex: Path,
) -> None:
    chain = _boot_with_source_seed(v35_main_hex, [0x00, 0x01, 0x02, 0x03, 0x03, 0x09])

    assert _channel_sources(chain, CHANNEL_PRIMARY_BASE) == [0x00, 0x01, 0x02, 0x03, 0x03, 0x01]
    assert _channel_sources(chain, CHANNEL_SHADOW_BASE) == [0x00, 0x01, 0x02, 0x03, 0x03, 0x01]


@pytest.mark.parametrize("corrupt_index", [4, 5])
def test_v35_boot_source_sanitizer_clamps_channel5_and_channel6_independently(
    v35_main_hex: Path,
    corrupt_index: int,
) -> None:
    valid = [0x00, 0x01, 0x02, 0x03, 0x02, 0x03]
    sources = valid.copy()
    sources[corrupt_index] = 0x09

    chain = _boot_with_source_seed(v35_main_hex, sources)
    expected = valid.copy()
    expected[corrupt_index] = 0x01

    assert _channel_sources(chain, CHANNEL_PRIMARY_BASE) == expected
    assert _channel_sources(chain, CHANNEL_SHADOW_BASE) == expected


def test_v35_source_channel6_sanitizer_writes_channel6_not_channel5() -> None:
    text = V35_MAIN_ASM.read_text(encoding="utf-8")
    start = text.index("restore_eeprom_settings_on_boot__validate_channel6_source:")
    end = text.index("restore_eeprom_settings_on_boot__validate_src_route_status:", start)
    body = text[start:end]

    assert "movwf       channel_6_source_config_b0, BANKED" in body
    assert "movwf       channel_5_source_config_b0, BANKED" not in body
