"""V3.5 duplicate wake frames must not cancel pending wake bring-up."""

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
EVENT_FLAGS = 0x07E
DIAG_B = 0x2E8

ACTIVE_GATE_MASK = 0x08
EVENT_WAKE_STANDBY_MASK = 0x04

BOOT_TCY = 16_000_000
WAKE_SETTLE_TCY = 20_000_000


@pytest.fixture(scope="module")
def v35_source_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v35_duplicate_wake")
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
    return chain


def _force_gate_closed_with_no_pending_wake(chain) -> None:  # type: ignore[no-untyped-def]
    chain.write_reg(ACTIVE_FLAGS, chain.read_reg(ACTIVE_FLAGS) & ~ACTIVE_GATE_MASK)
    chain.write_reg(EVENT_FLAGS, chain.read_reg(EVENT_FLAGS) & ~EVENT_WAKE_STANDBY_MASK)
    chain.write_reg(DIAG_B, 0x00)


def test_v35_duplicate_wake_frames_preserve_pending_wake_dispatch(
    v35_main_hex: Path,
) -> None:
    """Old V3.5 clears bit2 on the second wake and skips bring-up."""
    chain = _boot_main(v35_main_hex)
    _force_gate_closed_with_no_pending_wake(chain)

    delivered, overruns = chain.inject_main_frames_fifo(
        [[0xB0, 0x03, 0x01], [0xB0, 0x03, 0x01]],
        fifo_limit=47,
    )
    assert (delivered, overruns) == (6, 0)
    chain.step_tcy(WAKE_SETTLE_TCY)

    assert chain.read_reg(ACTIVE_FLAGS) & ACTIVE_GATE_MASK
    assert chain.read_reg(DIAG_B) >= 1, (
        "duplicate wake opened the logical gate but canceled the deferred "
        "wake bring-up dispatch"
    )


def test_v35_wake_handler_preserves_preexisting_pending_event_after_duplicate(
    v35_main_hex: Path,
) -> None:
    """A duplicate wake against an open gate must not clear pending work."""
    chain = _boot_main(v35_main_hex)
    chain.write_reg(ACTIVE_FLAGS, chain.read_reg(ACTIVE_FLAGS) | ACTIVE_GATE_MASK)
    chain.write_reg(EVENT_FLAGS, chain.read_reg(EVENT_FLAGS) | EVENT_WAKE_STANDBY_MASK)
    chain.write_reg(DIAG_B, 0x00)

    delivered, overruns = chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    assert (delivered, overruns) == (3, 0)
    chain.step_tcy(WAKE_SETTLE_TCY)

    assert chain.read_reg(ACTIVE_FLAGS) & ACTIVE_GATE_MASK
    assert chain.read_reg(DIAG_B) >= 1
