"""V3.5 repeated fixed-input cmd06 frames should be idempotent when unmuted."""

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
ACTIVE_USER_MUTE_MASK = 0x10
ACTIVE_MUTE_SHADOW_MASK = 0x20
SRC_ROUTE_STATUS = 0x05F
EVENT_FLAGS = 0x07E
INPUT_SELECT = 0x099
SRC_ROUTE_REQUEST = 0x093
ROUTE_SHADOW = 0x0AB
INPUT_SELECT_MIRROR = 0x0B3
I2C_SLOW_COUNTER = 0x0BB
DIAG_SRC_C = 0x3C2

SRC_REG_RX_CONTROL = 0x0D
SRC_REG_TX_CONTROL_2 = 0x08
SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
TAS_REG_VOLUME_COEFF = 0x30

ROUTE_SPDIF = 0x01
SRC_PAIR_SPDIF = (0x09, 0x70)

BOOT_TCY = 16_000_000
COMMAND_SETTLE_TCY = 4_000_000


@pytest.fixture(scope="module")
def v35_source_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v35_cmd06_idempotence")
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


def _boot_main(hex_path: Path):  # type: ignore[no-untyped-def]
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(hex_path))
    chain.step_tcy(BOOT_TCY)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.write_reg(SRC_ROUTE_STATUS, 0x03)
    chain.write_reg(SRC_ROUTE_REQUEST, 0x00)
    chain.write_reg(ROUTE_SHADOW, 0x00)
    chain.write_reg(I2C_SLOW_COUNTER, 0x65)
    return chain


def _inject_cmd06(chain, value: int) -> None:  # type: ignore[no-untyped-def]
    delivered, overruns = chain.inject_main_frames_fifo([[0xB0, 0x06, value]], fifo_limit=47)
    assert (delivered, overruns) == (3, 0)
    chain.step_tcy(COMMAND_SETTLE_TCY)


def _converge_spdif(chain) -> None:  # type: ignore[no-untyped-def]
    _inject_cmd06(chain, 0x05)
    assert chain.read_reg(INPUT_SELECT) == 0x05
    assert chain.read_reg(INPUT_SELECT_MIRROR) == 0x05
    assert chain.read_reg(SRC_ROUTE_REQUEST) == ROUTE_SPDIF
    assert chain.read_reg(ROUTE_SHADOW) == ROUTE_SPDIF
    assert SRC_PAIR_SPDIF[0] in chain.read_main_src4382_write_values(0, SRC_REG_RX_CONTROL)
    assert SRC_PAIR_SPDIF[1] in chain.read_main_src4382_write_values(0, SRC_REG_TX_CONTROL_2)


def test_v35_repeated_fixed_input_cmd06_does_not_rewrite_route_or_increment_c(
    v35_main_hex: Path,
) -> None:
    chain = _boot_main(v35_main_hex)
    _converge_spdif(chain)

    chain.reset_main_src4382_stats(0)
    chain.write_reg(DIAG_SRC_C, 0x00)
    before = (
        chain.read_reg(INPUT_SELECT),
        chain.read_reg(INPUT_SELECT_MIRROR),
        chain.read_reg(SRC_ROUTE_REQUEST),
        chain.read_reg(ROUTE_SHADOW),
    )

    for _ in range(3):
        _inject_cmd06(chain, 0x05)

    assert (
        chain.read_reg(INPUT_SELECT),
        chain.read_reg(INPUT_SELECT_MIRROR),
        chain.read_reg(SRC_ROUTE_REQUEST),
        chain.read_reg(ROUTE_SHADOW),
    ) == before
    assert chain.read_reg(DIAG_SRC_C) == 0x00
    assert chain.read_main_src4382_write_values(0, SRC_REG_RX_CONTROL) == []
    assert chain.read_main_src4382_write_values(0, SRC_REG_TX_CONTROL_2) == []


def test_v35_repeated_fixed_input_cmd06_repairs_stale_mirror_without_route_churn(
    v35_main_hex: Path,
) -> None:
    chain = _boot_main(v35_main_hex)
    _converge_spdif(chain)
    chain.write_reg(INPUT_SELECT_MIRROR, 0x00)
    chain.reset_main_src4382_stats(0)
    chain.write_reg(DIAG_SRC_C, 0x00)

    _inject_cmd06(chain, 0x05)

    assert chain.read_reg(INPUT_SELECT) == 0x05
    assert chain.read_reg(INPUT_SELECT_MIRROR) == 0x05
    assert chain.read_reg(ROUTE_SHADOW) == ROUTE_SPDIF
    assert chain.read_reg(DIAG_SRC_C) == 0x00
    assert chain.read_main_src4382_write_values(0, SRC_REG_RX_CONTROL) == []
    assert chain.read_main_src4382_write_values(0, SRC_REG_TX_CONTROL_2) == []


def test_v35_repeated_fixed_input_cmd06_while_muted_preserves_mute_refresh_path(
    v35_main_hex: Path,
) -> None:
    chain = _boot_main(v35_main_hex)
    _converge_spdif(chain)
    chain.write_reg(ACTIVE_FLAGS, chain.read_reg(ACTIVE_FLAGS) | ACTIVE_USER_MUTE_MASK | ACTIVE_MUTE_SHADOW_MASK)
    chain.write_reg(EVENT_FLAGS, 0x00)
    chain.reset_main_dsp_write_log(0)

    _inject_cmd06(chain, 0x05)

    active = chain.read_reg(ACTIVE_FLAGS)
    assert active & ACTIVE_USER_MUTE_MASK
    assert active & ACTIVE_MUTE_SHADOW_MASK
    payloads = chain.read_main_dsp_write_payloads(0, TAS_REG_VOLUME_COEFF)
    assert payloads, "muted repeated cmd06 should still refresh zero-volume TAS payload"
    assert all(payload == b"\x00\x00\x00\x00" for payload in payloads)
