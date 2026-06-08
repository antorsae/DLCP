"""V3.4 MAIN mute must survive later route/input volume refreshes."""

from __future__ import annotations

import pytest

from dlcp_fw.paths import V34_MAIN_HEX


ACTIVE_FLAGS = 0x05E
EVENT_FLAGS = 0x07E
ACTIVE_USER_MUTE_MASK = 0x10
ACTIVE_MUTE_SHADOW_MASK = 0x20
TAS_REG_VOLUME_COEFF = 0x30

BOOT_TCY = 16_000_000
MUTE_SETTLE_TICKS = 8_000_000
INPUT_REFRESH_SETTLE_TICKS = 20_000_000


try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    RustChain = None  # type: ignore[assignment]
    _RUST_CHAIN_IMPORT_ERROR = exc


def _require_rust() -> None:
    if RustChain is None:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _inject_frame(chain, cmd: int, data: int) -> None:  # type: ignore[no-untyped-def]
    delivered, overruns = chain.inject_main_frames_fifo([[0xB0, cmd, data]], fifo_limit=47)
    assert delivered == 3 and overruns == 0


def _boot_v34_main():  # type: ignore[no-untyped-def]
    _require_rust()
    assert V34_MAIN_HEX.exists(), V34_MAIN_HEX
    chain = RustChain.from_v3x_main_only(str(V34_MAIN_HEX))
    chain.step_tcy(BOOT_TCY)
    assert chain.read_main_reg(0, ACTIVE_FLAGS) & 0x08, "MAIN did not reach active app state"
    return chain


def _mute_main(chain) -> None:  # type: ignore[no-untyped-def]
    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x03, 0x02)
    chain.step_ticks(MUTE_SETTLE_TICKS)
    _assert_user_muted_with_zero_volume_coeff(chain)


def _assert_user_muted_with_zero_volume_coeff(chain) -> None:  # type: ignore[no-untyped-def]
    active = chain.read_main_reg(0, ACTIVE_FLAGS) & 0xFF
    events = chain.read_main_reg(0, EVENT_FLAGS) & 0xFF
    payload = chain.read_main_dsp_write_payload(0, TAS_REG_VOLUME_COEFF)
    assert active & ACTIVE_USER_MUTE_MASK, (
        f"user mute bit cleared unexpectedly: active=0x{active:02X}, events=0x{events:02X}, "
        f"dsp30={None if payload is None else payload.hex()}"
    )
    assert active & ACTIVE_MUTE_SHADOW_MASK, (
        f"mute shadow bit cleared unexpectedly: active=0x{active:02X}, events=0x{events:02X}, "
        f"dsp30={None if payload is None else payload.hex()}"
    )
    assert payload == b"\x00\x00\x00\x00", (
        f"TAS3108 volume coefficient should stay muted: active=0x{active:02X}, "
        f"events=0x{events:02X}, dsp30={None if payload is None else payload.hex()}"
    )


def test_v34_mute_on_writes_zero_volume_coeff() -> None:
    """Baseline green check: the explicit mute command itself still works."""
    chain = _boot_v34_main()
    _mute_main(chain)


@pytest.mark.xfail(
    strict=True,
    reason="BUG-MUTE-REFRESH-01: V3.4 route/input refresh clears user mute and rewrites TAS volume",
)
def test_v34_user_mute_survives_input_route_refresh() -> None:
    """Expected-red reproducer for live mute drop-outs.

    The live symptom is periodic audio returning for roughly one second while
    muted.  The deterministic core reproducer is MAIN-local:
    ``B0/03/02`` writes the zero TAS3108 volume coefficient, then
    ``B0/06/00`` forces route/input reconciliation and currently rewrites a
    non-zero coefficient while also clearing the user-mute bit.
    """
    chain = _boot_v34_main()
    _mute_main(chain)

    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x06, 0x00)
    chain.step_ticks(INPUT_REFRESH_SETTLE_TICKS)

    _assert_user_muted_with_zero_volume_coeff(chain)
