from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import PATCHED_CONTROL_HEX_V163B, PATCHED_MAIN_HEX_V28, V32_MAIN_HEX
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness

pytestmark = [pytest.mark.wire]

_STATUS_5E = 0x05E
_RX_RING_RD = 0x0C6
_RX_RING_WR = 0x0C7
_PRESET_B_BIT = 0x04
_ACTIVE_BIT = 0x08
_MUTE_BIT = 0x10
_PRESET_JOB_STATE = 0x2DE

_DELAYED_SWITCH_XFAIL = pytest.mark.xfail(
    reason=(
        "V2.8 known repro: delayed preset switch can desync CONTROL from a two-MAIN "
        "wire chain or leave follow-up 0x03 commands ineffective"
    ),
    strict=True,
)


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _skip_missing(*paths: Path) -> None:
    for path in paths:
        if not path.exists():
            pytest.skip(f"missing: {path.name}")


def _new_v28_two_main_wire_chain(*, fast_boot: bool) -> WireMultiMainChainHarness:
    return WireMultiMainChainHarness(
        PATCHED_CONTROL_HEX_V163B,
        PATCHED_MAIN_HEX_V28,
        main_units=2,
        fast_boot=fast_boot,
        disable_standby_check=False,
    )


def _set_profile_hypex(chain: WireMultiMainChainHarness) -> None:
    control = chain.control
    control._issue("reg(0x020)=0x10", 5.0)
    control._issue("reg(0x021)=0x32", 5.0)
    control._issue("reg(0x022)=0x33", 5.0)
    control._issue("reg(0x023)=0x34", 5.0)
    control._issue("reg(0x024)=0x36", 5.0)
    control._issue("reg(0x025)=0x37", 5.0)
    control._issue("reg(0x026)=0x35", 5.0)


def _main_status(chain: WireMultiMainChainHarness, index: int) -> int:
    return _read_reg(chain.mains[index]._issue, _STATUS_5E)


def _main_preset(chain: WireMultiMainChainHarness, index: int) -> int:
    return 1 if (_main_status(chain, index) & _PRESET_B_BIT) else 0


def _main_active(chain: WireMultiMainChainHarness, index: int) -> bool:
    return bool(_main_status(chain, index) & _ACTIVE_BIT)


def _main_muted(chain: WireMultiMainChainHarness, index: int) -> bool:
    return bool(_main_status(chain, index) & _MUTE_BIT)


def _main_debug_state(chain: WireMultiMainChainHarness, index: int) -> str:
    status = _main_status(chain, index)
    rx_rd = _read_reg(chain.mains[index]._issue, _RX_RING_RD)
    rx_wr = _read_reg(chain.mains[index]._issue, _RX_RING_WR)
    return (
        f"main{index}(status_5e=0x{status:02X}, preset={1 if (status & _PRESET_B_BIT) else 0}, "
        f"active={int(bool(status & _ACTIVE_BIT))}, muted={int(bool(status & _MUTE_BIT))}, "
        f"rx_rd=0x{rx_rd:02X}, rx_wr=0x{rx_wr:02X})"
    )


def _assert_all_mains_preset(chain: WireMultiMainChainHarness, expected: int) -> None:
    actual = [_main_preset(chain, idx) for idx in range(len(chain.mains))]
    assert actual == [expected] * len(chain.mains), (
        f"MAIN preset mismatch: expected {[expected] * len(chain.mains)}, got {actual}; "
        f"lcd={chain.lcd_lines()!r}; "
        f"states={[ _main_debug_state(chain, idx) for idx in range(len(chain.mains)) ]}"
    )


def _assert_all_mains_active(chain: WireMultiMainChainHarness, expected: bool) -> None:
    actual = [_main_active(chain, idx) for idx in range(len(chain.mains))]
    assert actual == [expected] * len(chain.mains), (
        f"MAIN active mismatch: expected {[expected] * len(chain.mains)}, got {actual}; "
        f"lcd={chain.lcd_lines()!r}; "
        f"states={[ _main_debug_state(chain, idx) for idx in range(len(chain.mains)) ]}"
    )


def _assert_all_mains_muted(chain: WireMultiMainChainHarness, expected: bool) -> None:
    actual = [_main_muted(chain, idx) for idx in range(len(chain.mains))]
    assert actual == [expected] * len(chain.mains), (
        f"MAIN mute mismatch: expected {[expected] * len(chain.mains)}, got {actual}; "
        f"lcd={chain.lcd_lines()!r}; "
        f"states={[ _main_debug_state(chain, idx) for idx in range(len(chain.mains)) ]}"
    )


def _step_without_waiting(
    chain: WireMultiMainChainHarness,
    *,
    steps: int,
    context: str,
):
    last = None
    for _ in range(steps):
        last = chain.step()
        assert not chain.is_waiting(), (
            f"CONTROL entered WAITING during {context}: lcd={last.lcd!r}"
        )
    return last


def _toggle_mute_and_assert(
    chain: WireMultiMainChainHarness,
    *,
    expected_muted: bool,
    limit: int = 20,
) -> None:
    if not chain.lcd_lines()[0].startswith("Volume:"):
        _return_to_volume_screen(chain)
    chain.press("S")
    for _ in range(limit):
        _step_without_waiting(chain, steps=1, context="mute toggle")
        actual = [_main_muted(chain, idx) for idx in range(len(chain.mains))]
        if actual == [expected_muted] * len(chain.mains):
            return
    pytest.fail(
        f"mute toggle did not settle to {expected_muted} within {limit} steps; "
        f"actual={[ _main_muted(chain, idx) for idx in range(len(chain.mains)) ]} "
        f"lcd={chain.lcd_lines()!r}"
    )


def _enter_standby(chain: WireMultiMainChainHarness, *, limit: int = 30) -> None:
    chain.press("STBY")
    for _ in range(limit):
        chain.step()
        if "ZZZ" in chain.lcd_lines()[0].upper():
            return
    pytest.fail(f"chain did not enter standby within {limit} steps; lcd={chain.lcd_lines()!r}")


def _wake_and_reconnect(chain: WireMultiMainChainHarness, *, limit: int = 120):
    chain.press("STBY")
    last = chain.run_until_connected(limit=limit)
    assert last is not None, "chain produced no steps while waiting to reconnect"
    assert chain.is_connected(), f"chain never reconnected: lcd={last.lcd!r}"
    assert not chain.is_waiting(), f"chain stayed in WAITING after wake: lcd={last.lcd!r}"
    _assert_all_mains_active(chain, True)
    return last


def _enter_standby_via_ir(chain: WireMultiMainChainHarness, *, limit: int = 30) -> None:
    chain.control.inject_decoded_ir_event(cmd=0x32, addr=0x10, steps=1)
    for _ in range(limit):
        chain.step()
        if "ZZZ" in chain.lcd_lines()[0].upper():
            return
    pytest.fail(f"chain did not enter standby via IR within {limit} steps; lcd={chain.lcd_lines()!r}")


def _wake_and_reconnect_via_ir(chain: WireMultiMainChainHarness, *, limit: int = 120):
    chain.control.inject_decoded_ir_event(cmd=0x32, addr=0x10, steps=1)
    last = chain.run_until_connected(limit=limit)
    assert last is not None, "chain produced no steps while waiting to reconnect after IR wake"
    assert chain.is_connected(), f"chain never reconnected after IR wake: lcd={last.lcd!r}"
    assert not chain.is_waiting(), f"chain stayed in WAITING after IR wake: lcd={last.lcd!r}"
    _assert_all_mains_active(chain, True)
    return last


@pytest.mark.gpsim
@pytest.mark.slow
@_DELAYED_SWITCH_XFAIL
def test_v28_wire_two_main_rapid_ir_f1_f2_preserves_followup_mute() -> None:
    _require_gpsim()
    _skip_missing(PATCHED_CONTROL_HEX_V163B, PATCHED_MAIN_HEX_V28)

    chain = _new_v28_two_main_wire_chain(fast_boot=True)
    try:
        last = chain.run_until_connected(limit=100)
        assert last is not None, "two-main wire chain never reached DISPLAY"
        _set_profile_hypex(chain)

        rapid_ir = [0x39, 0x38] * 4 + [0x39]
        for cmd in rapid_ir:
            chain.control.inject_decoded_ir_event(cmd=cmd, addr=0x10, steps=1)
            _step_without_waiting(chain, steps=2, context="rapid preset toggle")

        _step_without_waiting(chain, steps=80, context="rapid preset drain")
        _assert_all_mains_preset(chain, 1)

        _toggle_mute_and_assert(chain, expected_muted=True)
        _toggle_mute_and_assert(chain, expected_muted=False)
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
@_DELAYED_SWITCH_XFAIL
def test_v28_wire_two_main_interleaved_mute_during_delayed_switch_preserves_state() -> None:
    _require_gpsim()
    _skip_missing(PATCHED_CONTROL_HEX_V163B, PATCHED_MAIN_HEX_V28)

    chain = _new_v28_two_main_wire_chain(fast_boot=True)
    try:
        last = chain.run_until_connected(limit=100)
        assert last is not None, "two-main wire chain never reached DISPLAY"
        _set_profile_hypex(chain)

        chain.control.inject_decoded_ir_event(cmd=0x39, addr=0x10, steps=1)
        chain.press("S")

        _step_without_waiting(chain, steps=30, context="preset switch + mute on")
        _assert_all_mains_preset(chain, 1)
        _assert_all_mains_muted(chain, True)

        _toggle_mute_and_assert(chain, expected_muted=False)
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
@_DELAYED_SWITCH_XFAIL
def test_v28_wire_two_main_interleaved_standby_during_delayed_switch_reconnects_cleanly() -> None:
    _require_gpsim()
    _skip_missing(PATCHED_CONTROL_HEX_V163B, PATCHED_MAIN_HEX_V28)

    chain = _new_v28_two_main_wire_chain(fast_boot=False)
    try:
        last = chain.run_until_connected(limit=100)
        assert last is not None, "two-main wire chain never reached DISPLAY"
        _set_profile_hypex(chain)

        chain.control.inject_decoded_ir_event(cmd=0x39, addr=0x10, steps=1)
        _enter_standby(chain)

        _wake_and_reconnect(chain)
        _assert_all_mains_preset(chain, 1)

        _toggle_mute_and_assert(chain, expected_muted=True)
        _toggle_mute_and_assert(chain, expected_muted=False)
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
@_DELAYED_SWITCH_XFAIL
def test_v28_wire_two_main_stop_fault_during_delayed_switch_recovers() -> None:
    _require_gpsim()
    _skip_missing(PATCHED_CONTROL_HEX_V163B, PATCHED_MAIN_HEX_V28)

    chain = _new_v28_two_main_wire_chain(fast_boot=False)
    try:
        last = chain.run_until_connected(limit=100)
        assert last is not None, "two-main wire chain never reached DISPLAY"
        _set_profile_hypex(chain)

        ring_before = (
            _read_reg(chain.mains[0]._issue, _RX_RING_RD),
            _read_reg(chain.mains[0]._issue, _RX_RING_WR),
        )

        chain.control.inject_decoded_ir_event(cmd=0x39, addr=0x10, steps=1)
        chain.set_main_mssp_stop_fault(main_index=0, stop_busy_cycles=5_000_000, stop_busy_count=-1)
        chain.step_many(30)

        ring_after_fault = (
            _read_reg(chain.mains[0]._issue, _RX_RING_RD),
            _read_reg(chain.mains[0]._issue, _RX_RING_WR),
        )

        chain.clear_main_mssp_stop_faults(main_index=0)
        try:
            chain.mains[0]._issue("p18f2455.sspcon2 = 0", 5.0)
        except Exception:
            pass

        recovered = chain.run_until_connected(limit=120)
        assert recovered is not None, (
            "chain produced no steps after delayed-switch STOP fault clear; "
            f"ring_before={ring_before} ring_after_fault={ring_after_fault}"
        )
        assert chain.is_connected(), (
            "chain never recovered after delayed-switch STOP fault; "
            f"lcd={recovered.lcd!r} ring_before={ring_before} "
            f"ring_after_fault={ring_after_fault}"
        )
        assert not chain.is_waiting(), (
            "chain stayed in WAITING after delayed-switch STOP fault clear; "
            f"lcd={recovered.lcd!r} ring_before={ring_before} "
            f"ring_after_fault={ring_after_fault}"
        )
        _assert_all_mains_preset(chain, 1)

        _toggle_mute_and_assert(chain, expected_muted=True)
        _toggle_mute_and_assert(chain, expected_muted=False)
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
@_DELAYED_SWITCH_XFAIL
def test_v28_wire_two_main_preset_soak_under_reconnect_and_full_sync_keeps_both_mains_responsive() -> None:
    _require_gpsim()
    _skip_missing(PATCHED_CONTROL_HEX_V163B, PATCHED_MAIN_HEX_V28)

    chain = _new_v28_two_main_wire_chain(fast_boot=False)
    try:
        last = chain.run_until_connected(limit=100)
        assert last is not None, "two-main wire chain never reached DISPLAY"
        _set_profile_hypex(chain)

        for cycle, cmd in enumerate((0x39, 0x38, 0x39), start=1):
            target_preset = 1 if cmd == 0x39 else 0
            chain.control.inject_decoded_ir_event(cmd=cmd, addr=0x10, steps=1)
            _step_without_waiting(
                chain,
                steps=40,
                context=f"preset soak cycle {cycle} switch",
            )
            _assert_all_mains_preset(chain, target_preset)
            _toggle_mute_and_assert(chain, expected_muted=True)
            _toggle_mute_and_assert(chain, expected_muted=False)

            _enter_standby(chain)
            _wake_and_reconnect(chain)
            _assert_all_mains_preset(chain, target_preset)

            _step_without_waiting(
                chain,
                steps=40,
                context=f"preset soak cycle {cycle} post-reconnect full-sync drain",
            )
            _toggle_mute_and_assert(chain, expected_muted=True)
            _toggle_mute_and_assert(chain, expected_muted=False)
    finally:
        chain.close()


# ---------------------------------------------------------------------------
# V3.2 async preset job tests — expected to PASS
# ---------------------------------------------------------------------------


def _new_v32_two_main_wire_chain(*, fast_boot: bool) -> WireMultiMainChainHarness:
    return WireMultiMainChainHarness(
        PATCHED_CONTROL_HEX_V163B,
        V32_MAIN_HEX,
        main_units=2,
        fast_boot=fast_boot,
        disable_standby_check=False,
    )


def _wait_preset_job_idle(
    chain: WireMultiMainChainHarness,
    *,
    limit: int = 120,
    context: str = "preset job drain",
) -> None:
    for _ in range(limit):
        _step_without_waiting(chain, steps=1, context=context)
        states = [
            _read_reg(chain.mains[idx]._issue, _PRESET_JOB_STATE)
            for idx in range(len(chain.mains))
        ]
        if all(s == 0 for s in states):
            return
    pytest.fail(
        f"preset job did not reach IDLE within {limit} steps; "
        f"states={[_read_reg(chain.mains[idx]._issue, _PRESET_JOB_STATE) for idx in range(len(chain.mains))]}; "
        f"debug={[_main_debug_state(chain, idx) for idx in range(len(chain.mains))]}"
    )


def _wait_preset_job_idle_allow_reconnect(
    chain: WireMultiMainChainHarness,
    *,
    limit: int = 180,
    context: str = "preset job drain with reconnect",
) -> None:
    for _ in range(limit):
        if chain.is_waiting():
            last = chain.run_until_connected(limit=120)
            assert last is not None, f"{context}: chain produced no steps while reconnecting from WAITING"
            assert chain.is_connected(), f"{context}: chain failed to reconnect from WAITING"
        chain.step()
        states = [
            _read_reg(chain.mains[idx]._issue, _PRESET_JOB_STATE)
            for idx in range(len(chain.mains))
        ]
        if all(s == 0 for s in states):
            return
    pytest.fail(
        f"{context}: preset job did not reach IDLE within {limit} steps; "
        f"states={[_read_reg(chain.mains[idx]._issue, _PRESET_JOB_STATE) for idx in range(len(chain.mains))]}; "
        f"debug={[_main_debug_state(chain, idx) for idx in range(len(chain.mains))]}"
    )


def _wait_main_preset_job_state(
    chain: WireMultiMainChainHarness,
    *,
    main_index: int,
    expected_state: int,
    limit: int = 120,
    context: str,
) -> None:
    for _ in range(limit):
        _step_without_waiting(chain, steps=1, context=context)
        if _read_reg(chain.mains[main_index]._issue, _PRESET_JOB_STATE) == expected_state:
            return
    pytest.fail(
        f"main{main_index} preset job did not reach state {expected_state} within {limit} steps; "
        f"state=0x{_read_reg(chain.mains[main_index]._issue, _PRESET_JOB_STATE):02X} "
        f"lcd={chain.lcd_lines()!r} "
        f"debug={[_main_debug_state(chain, idx) for idx in range(len(chain.mains))]}"
    )


def _switch_to_preset_via_public_keys(
    chain: WireMultiMainChainHarness,
    *,
    target_preset: int,
) -> None:
    chain.press("R")
    _step_without_waiting(chain, steps=1, context="enter preset screen")
    if target_preset:
        chain.press("D")
    else:
        chain.press("U")
    _step_without_waiting(
        chain,
        steps=2,
        context=f"front-panel preset {'B' if target_preset else 'A'} select",
    )


def _wait_main_preset_job_active(
    chain: WireMultiMainChainHarness,
    *,
    main_index: int,
    limit: int = 120,
    context: str,
) -> int:
    for _ in range(limit):
        _step_without_waiting(chain, steps=1, context=context)
        state = _read_reg(chain.mains[main_index]._issue, _PRESET_JOB_STATE)
        if state != 0:
            return state
    pytest.fail(
        f"main{main_index} preset job never became active within {limit} steps; "
        f"state=0x{_read_reg(chain.mains[main_index]._issue, _PRESET_JOB_STATE):02X} "
        f"lcd={chain.lcd_lines()!r} "
        f"debug={[_main_debug_state(chain, idx) for idx in range(len(chain.mains))]}"
    )


def _return_to_volume_screen(chain: WireMultiMainChainHarness, *, limit: int = 12) -> None:
    if chain.lcd_lines()[0].startswith("Volume:"):
        return
    chain.press("L")
    for _ in range(limit):
        _step_without_waiting(chain, steps=1, context="return to volume screen")
        if chain.lcd_lines()[0].startswith("Volume:"):
            return
    pytest.fail(f"control did not return to volume screen within {limit} steps; lcd={chain.lcd_lines()!r}")


def _press_mute_and_assert_delivery(
    chain: WireMultiMainChainHarness,
    *,
    limit: int = 12,
) -> None:
    on_volume_screen = chain.lcd_lines()[0].startswith("Volume:")
    before_control = len(chain.control.tx_frames())
    before_rx = [
        (
            _read_reg(chain.mains[idx]._issue, _RX_RING_RD),
            _read_reg(chain.mains[idx]._issue, _RX_RING_WR),
        )
        for idx in range(len(chain.mains))
    ]
    if on_volume_screen:
        chain.press("S")
    else:
        chain.control.inject_decoded_ir_event(cmd=0x35, addr=0x10, steps=1)
    for _ in range(limit):
        _step_without_waiting(chain, steps=1, context="mute traffic delivery")
        new_frames = chain.control.tx_frames()[before_control:]
        saw_mute_cmd = any(
            f.route == 0xB0 and f.cmd == 0x03 and f.data in {0x01, 0x02, 0x03}
            for f in new_frames
        )
        after_rx = [
            (
                _read_reg(chain.mains[idx]._issue, _RX_RING_RD),
                _read_reg(chain.mains[idx]._issue, _RX_RING_WR),
            )
            for idx in range(len(chain.mains))
        ]
        delivered = all(after_rx[idx] != before_rx[idx] for idx in range(len(chain.mains)))
        if saw_mute_cmd and delivered:
            return
    pytest.fail(
        "mute traffic did not reach both MAINs within "
        f"{limit} steps; lcd={chain.lcd_lines()!r} "
        f"control={[ (f.route, f.cmd, f.data) for f in chain.control.tx_frames()[before_control:] ]} "
        f"rx_before={before_rx} "
        f"rx_after={[(_read_reg(chain.mains[idx]._issue, _RX_RING_RD), _read_reg(chain.mains[idx]._issue, _RX_RING_WR)) for idx in range(len(chain.mains))]}"
    )


def _inject_ir_until_mute_on_delivered(
    chain: WireMultiMainChainHarness,
    *,
    attempts: int = 3,
    limit_per_attempt: int = 16,
) -> None:
    for _ in range(attempts):
        before_control = len(chain.control.tx_frames())
        before_rx = [
            (
                _read_reg(chain.mains[idx]._issue, _RX_RING_RD),
                _read_reg(chain.mains[idx]._issue, _RX_RING_WR),
            )
            for idx in range(len(chain.mains))
        ]
        chain.control.inject_decoded_ir_event(cmd=0x35, addr=0x10, steps=1)
        for _ in range(limit_per_attempt):
            _step_without_waiting(chain, steps=1, context="interleaved IR mute-on delivery")
            new_frames = chain.control.tx_frames()[before_control:]
            saw_mute_on = any(
                f.route == 0xB0 and f.cmd == 0x03 and f.data == 0x03
                for f in new_frames
            )
            after_rx = [
                (
                    _read_reg(chain.mains[idx]._issue, _RX_RING_RD),
                    _read_reg(chain.mains[idx]._issue, _RX_RING_WR),
                )
                for idx in range(len(chain.mains))
            ]
            delivered = all(after_rx[idx] != before_rx[idx] for idx in range(len(chain.mains)))
            if saw_mute_on and delivered:
                return
    pytest.fail(
        "could not deliver explicit mute-on (B0/03/03) to both MAINs via interleaved IR; "
        f"lcd={chain.lcd_lines()!r}"
    )


def _wait_all_mains_muted(
    chain: WireMultiMainChainHarness,
    *,
    expected: bool,
    limit: int = 60,
    context: str,
) -> None:
    for _ in range(limit):
        _step_without_waiting(chain, steps=1, context=context)
        actual = [_main_muted(chain, idx) for idx in range(len(chain.mains))]
        if actual == [expected] * len(chain.mains):
            return
    pytest.fail(
        f"MAIN mute state did not converge to {expected} within {limit} steps; "
        f"actual={[ _main_muted(chain, idx) for idx in range(len(chain.mains)) ]}; "
        f"debug={[_main_debug_state(chain, idx) for idx in range(len(chain.mains))]}"
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_wire_two_main_rapid_ir_f1_f2_preserves_followup_mute() -> None:
    _require_gpsim()
    _skip_missing(PATCHED_CONTROL_HEX_V163B, V32_MAIN_HEX)

    chain = _new_v32_two_main_wire_chain(fast_boot=True)
    try:
        last = chain.run_until_connected(limit=100)
        assert last is not None, "two-main wire chain never reached DISPLAY"
        _set_profile_hypex(chain)

        rapid_ir = [0x39, 0x38] * 4 + [0x39]
        for cmd in rapid_ir:
            chain.control.inject_decoded_ir_event(cmd=cmd, addr=0x10, steps=1)
            _step_without_waiting(chain, steps=2, context="rapid preset toggle")

        _wait_preset_job_idle(chain, limit=120, context="rapid preset drain")
        _assert_all_mains_preset(chain, 1)

        _toggle_mute_and_assert(chain, expected_muted=True)
        _toggle_mute_and_assert(chain, expected_muted=False)
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_wire_two_main_interleaved_mute_during_delayed_switch_preserves_state() -> None:
    _require_gpsim()
    _skip_missing(PATCHED_CONTROL_HEX_V163B, V32_MAIN_HEX)

    chain = _new_v32_two_main_wire_chain(fast_boot=True)
    try:
        last = chain.run_until_connected(limit=100)
        assert last is not None, "two-main wire chain never reached DISPLAY"
        _set_profile_hypex(chain)

        _switch_to_preset_via_public_keys(chain, target_preset=1)
        _wait_main_preset_job_active(
            chain,
            main_index=0,
            limit=60,
            context="wait for main0 async preset job active",
        )
        _inject_ir_until_mute_on_delivered(chain)

        _wait_preset_job_idle(chain, limit=120, context="preset switch drain")

        _assert_all_mains_preset(chain, 1)
        _wait_all_mains_muted(
            chain,
            expected=True,
            limit=80,
            context="wait for final interleaved mute convergence",
        )
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_wire_two_main_interleaved_standby_during_delayed_switch_reconnects_cleanly() -> None:
    _require_gpsim()
    _skip_missing(PATCHED_CONTROL_HEX_V163B, V32_MAIN_HEX)

    chain = _new_v32_two_main_wire_chain(fast_boot=False)
    try:
        last = chain.run_until_connected(limit=100)
        assert last is not None, "two-main wire chain never reached DISPLAY"
        _set_profile_hypex(chain)

        _switch_to_preset_via_public_keys(chain, target_preset=1)
        _wait_main_preset_job_active(
            chain,
            main_index=0,
            limit=60,
            context="wait for main0 async preset job active",
        )
        _return_to_volume_screen(chain)
        _enter_standby(chain)

        _wake_and_reconnect(chain)
        _wait_preset_job_idle(chain, limit=180, context="post-wake preset settle")

        _assert_all_mains_preset(chain, 1)
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_wire_two_main_stop_fault_during_delayed_switch_recovers() -> None:
    _require_gpsim()
    _skip_missing(PATCHED_CONTROL_HEX_V163B, V32_MAIN_HEX)

    chain = _new_v32_two_main_wire_chain(fast_boot=False)
    try:
        last = chain.run_until_connected(limit=100)
        assert last is not None, "two-main wire chain never reached DISPLAY"
        _set_profile_hypex(chain)

        _switch_to_preset_via_public_keys(chain, target_preset=1)
        _wait_main_preset_job_state(
            chain,
            main_index=0,
            expected_state=0x03,
            limit=120,
            context="wait for main0 async apply",
        )
        apply_index_before_fault = _read_reg(chain.mains[0]._issue, 0x2E0)

        ring_before = (
            _read_reg(chain.mains[0]._issue, _RX_RING_RD),
            _read_reg(chain.mains[0]._issue, _RX_RING_WR),
        )

        chain.set_main_mssp_stop_fault(main_index=0, stop_busy_cycles=5_000_000, stop_busy_count=-1)
        chain.step_many(3)

        ring_after_fault = (
            _read_reg(chain.mains[0]._issue, _RX_RING_RD),
            _read_reg(chain.mains[0]._issue, _RX_RING_WR),
        )
        assert _read_reg(chain.mains[0]._issue, _PRESET_JOB_STATE) == 0x03, (
            "main0 left APPLY during persistent STOP fault instead of keeping the job retryable"
        )
        assert _read_reg(chain.mains[0]._issue, 0x2E0) == apply_index_before_fault, (
            "main0 advanced the async preset-table index during the early STOP-timeout window"
        )

        chain.clear_main_mssp_stop_faults(main_index=0)

        recovered = chain.run_until_connected(limit=120)
        assert recovered is not None, (
            "chain produced no steps after delayed-switch STOP fault clear; "
            f"ring_before={ring_before} ring_after_fault={ring_after_fault}"
        )
        assert chain.is_connected(), (
            "chain never recovered after delayed-switch STOP fault; "
            f"lcd={recovered.lcd!r} ring_before={ring_before} "
            f"ring_after_fault={ring_after_fault}"
        )
        assert not chain.is_waiting(), (
            "chain stayed in WAITING after delayed-switch STOP fault clear; "
            f"lcd={recovered.lcd!r} ring_before={ring_before} "
            f"ring_after_fault={ring_after_fault}"
        )
        _wait_preset_job_idle(chain, limit=180, context="post-fault preset recovery")
        _assert_all_mains_preset(chain, 1)
        _return_to_volume_screen(chain)

        _press_mute_and_assert_delivery(chain)
        _enter_standby(chain)
        _wake_and_reconnect(chain)
        _assert_all_mains_preset(chain, 1)
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_wire_two_main_preset_soak_under_reconnect_and_full_sync_keeps_both_mains_responsive() -> None:
    _require_gpsim()
    _skip_missing(PATCHED_CONTROL_HEX_V163B, V32_MAIN_HEX)

    chain = _new_v32_two_main_wire_chain(fast_boot=False)
    try:
        last = chain.run_until_connected(limit=100)
        assert last is not None, "two-main wire chain never reached DISPLAY"
        _set_profile_hypex(chain)

        # Include real A<->B alternation under reconnect/full-sync churn.
        for cycle, target_preset in enumerate((1, 0, 1), start=1):
            chain.control.inject_decoded_ir_event(
                cmd=0x39 if target_preset else 0x38,
                addr=0x10,
                steps=1,
            )
            chain.step_many(2)
            _wait_preset_job_idle_allow_reconnect(
                chain,
                limit=180,
                context=f"preset soak cycle {cycle} switch",
            )

            _assert_all_mains_preset(chain, target_preset)

            _enter_standby_via_ir(chain)
            _wake_and_reconnect_via_ir(chain)
            _assert_all_mains_preset(chain, target_preset)
    finally:
        chain.close()
