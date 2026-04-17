"""V1.7 shifted CONTROL — full behavioral parity against stock V1.6b.

Exercises every behavioral surface reachable through
``GpsimControlHarness``: boot-time TX burst, button presses (volume /
standby / mute / menu navigation), UART RX parser responses to
simulated MAIN replies, IR decode dispatch, and LCD rendering.

For each scenario, the test drives **stock V1.6b** and **V1.7 shifted**
with identical inputs and asserts that their observable outputs (TX
frame sequence, LCD rows, flag-register bytes) match exactly.  Any
divergence is a relocation bug: the shifted image must be behavioral
idem to stock within every flow, which proves the V1.7 shifted baseline
is safe to build V1.71 on top of.

All tests are ``@pytest.mark.gpsim`` + ``@pytest.mark.slow`` because
each scenario spins up two gpsim instances and runs them to quiescence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

import pytest

from dlcp_fw.paths import (
    STOCK_CONTROL_HEX_V16B,
    V17_CONTROL_ASM_COMMENTS,
    V17_CONTROL_RAM_INC,
)
from dlcp_fw.sim.gpsim import gpsim_available

try:
    from dlcp_fw.sim.control_gpsim import GpsimControlHarness, RxTriplet
    from dlcp_fw.sim.v17_symbols import assemble_v17, build_shifted_asm
    _IMPORT_OK = True
except Exception:  # pragma: no cover
    _IMPORT_OK = False


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    if not _IMPORT_OK:
        pytest.skip("control_gpsim harness not importable")


# ---------------------------------------------------------------------------
# Image assembly — shared session fixture (shifted hex built once).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def v17_shifted_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Assemble V1.7 shifted hex once per module."""
    tmp = tmp_path_factory.mktemp("v17_shift_parity")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    src_stage = tmp / V17_CONTROL_ASM_COMMENTS.name
    src_stage.write_bytes(V17_CONTROL_ASM_COMMENTS.read_bytes())
    shifted_src = tmp / "v17_shifted.asm"
    build_shifted_asm(src_stage, shifted_src)
    hex_out = tmp / "v17_shifted.hex"
    assemble_v17(shifted_src, hex_out)
    return hex_out


# ---------------------------------------------------------------------------
# Harness helpers
# ---------------------------------------------------------------------------

# Standalone harness settings (no MAIN attached): use heartbeat "full" so
# CONTROL sees constant BF replies and stays in DISPLAY mode.  Warmup past
# the initial boot-handshake phase before running test scenarios.
_WARMUP_CYCLES = 25_000_000
_STEPS_PER_PRESS = 12
_RX_STEPS_PER_FRAME = 6


def _new_harness(control_hex: Path) -> GpsimControlHarness:
    """Boot a CONTROL-only harness with safe defaults for parity tests.

    ``fast_boot=False`` because the V1.7 shifted image has NOP padding
    at stock 0x0052 (inside the former defensive stub), making the
    ``control_disable_boot_wait`` overlay's byte preconditions
    unmatchable.  The longer warmup uses ``warmup(25M)`` to cover the
    same startup interval.
    """
    return GpsimControlHarness(
        control_hex,
        fast_boot=False,
        chunk_cycles=600_000,
        hold_cycles=300_000,
        heartbeat_rx_mode="full",
    )


@dataclass(frozen=True)
class ScenarioOutcome:
    """Captured observable state after a scenario run."""

    lcd_lines: Tuple[str, str]
    tx_frames: Tuple[Tuple[int, int, int], ...]
    flags: int  # 0x01F
    display_state: int  # 0x0BF
    input_select_cache: int  # 0x0B8
    volume_cache: int  # 0x0B9

    def as_summary(self) -> dict:
        return {
            "lcd": self.lcd_lines,
            "tx": self.tx_frames,
            "flags": hex(self.flags),
            "display_state": self.display_state,
            "input_select_cache": hex(self.input_select_cache),
            "volume_cache": hex(self.volume_cache),
        }


def _capture(h: GpsimControlHarness) -> ScenarioOutcome:
    return ScenarioOutcome(
        lcd_lines=tuple(h.lcd_lines()),
        tx_frames=tuple((f.route, f.cmd, f.data) for f in h.tx_frames()),
        flags=h.read_reg(0x01F),
        display_state=h.read_reg(0x0BF),
        input_select_cache=h.read_reg(0x0B8),
        volume_cache=h.read_reg(0x0B9),
    )


def _run_scenario(
    control_hex: Path,
    scenario: Callable[[GpsimControlHarness], None],
) -> ScenarioOutcome:
    """Boot a harness, warmup, run the scenario, capture outcome."""
    h = _new_harness(control_hex)
    try:
        h.warmup(_WARMUP_CYCLES)
        scenario(h)
        # Let the firmware drain any pending TX before we sample state.
        for _ in range(6):
            h.step()
        return _capture(h)
    finally:
        h.close()


def _assert_parity(
    scenario_name: str,
    stock: ScenarioOutcome,
    shifted: ScenarioOutcome,
    *,
    tx_only: bool = False,
) -> None:
    """Assert stock == shifted outcomes with a readable diff message."""
    assert stock.tx_frames == shifted.tx_frames, (
        f"[{scenario_name}] TX frame divergence\n"
        f"  stock:   {stock.tx_frames!r}\n"
        f"  shifted: {shifted.tx_frames!r}"
    )
    if tx_only:
        return
    assert stock.lcd_lines == shifted.lcd_lines, (
        f"[{scenario_name}] LCD divergence\n"
        f"  stock:   {stock.lcd_lines!r}\n"
        f"  shifted: {shifted.lcd_lines!r}"
    )
    assert stock.flags == shifted.flags, (
        f"[{scenario_name}] control_flags divergence "
        f"stock=0x{stock.flags:02X} shifted=0x{shifted.flags:02X}"
    )
    assert stock.display_state == shifted.display_state, (
        f"[{scenario_name}] display_state_index divergence "
        f"stock=0x{stock.display_state:02X} shifted=0x{shifted.display_state:02X}"
    )
    assert stock.input_select_cache == shifted.input_select_cache, (
        f"[{scenario_name}] input_select_cache divergence "
        f"stock=0x{stock.input_select_cache:02X} shifted=0x{shifted.input_select_cache:02X}"
    )
    assert stock.volume_cache == shifted.volume_cache, (
        f"[{scenario_name}] volume_cache divergence "
        f"stock=0x{stock.volume_cache:02X} shifted=0x{shifted.volume_cache:02X}"
    )


def _run_and_compare(
    scenario_name: str,
    v17_shifted_hex: Path,
    scenario: Callable[[GpsimControlHarness], None],
    *,
    tx_only: bool = False,
) -> None:
    _require_gpsim()
    stock = _run_scenario(STOCK_CONTROL_HEX_V16B, scenario)
    shifted = _run_scenario(v17_shifted_hex, scenario)
    _assert_parity(scenario_name, stock, shifted, tx_only=tx_only)


# ---------------------------------------------------------------------------
# Scenario A: idle warmup — no input.  Smoke test for boot convergence.
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_idle_warmup(v17_shifted_hex: Path) -> None:
    """After warmup with no button presses, stock and shifted agree."""
    _run_and_compare("idle_warmup", v17_shifted_hex, lambda h: None)


# ---------------------------------------------------------------------------
# Scenario B: volume up/down button presses.  Exercises the volume-frame
# encoder, TX ring enqueue, LCD redraw (the garbled "???P b?" bug that
# surfaced the TBLPTR literal issue was in this flow).
# ---------------------------------------------------------------------------

def _press_sequence(keys: Sequence[str]) -> Callable[[GpsimControlHarness], None]:
    def _do(h: GpsimControlHarness) -> None:
        for key in keys:
            h.press(key)
            for _ in range(_STEPS_PER_PRESS):
                h.step()
    return _do


@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_volume_up_sequence(v17_shifted_hex: Path) -> None:
    _run_and_compare(
        "volume_up_x5",
        v17_shifted_hex,
        _press_sequence(["UP"] * 5),
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_volume_down_sequence(v17_shifted_hex: Path) -> None:
    _run_and_compare(
        "volume_down_x5",
        v17_shifted_hex,
        _press_sequence(["DOWN"] * 5),
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_volume_up_then_down(v17_shifted_hex: Path) -> None:
    _run_and_compare(
        "volume_mixed",
        v17_shifted_hex,
        _press_sequence(["UP"] * 3 + ["DOWN"] * 3 + ["UP"] * 2),
    )


# ---------------------------------------------------------------------------
# Scenario C: menu navigation.  SELECT/LEFT/RIGHT cycle through the
# volume/preset/input/setup screens, exercising LCD string fetches for
# EVERY screen header (this flow is what the TBLPTR-pattern-B fix
# unblocked).
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_menu_select_cycle(v17_shifted_hex: Path) -> None:
    _run_and_compare(
        "menu_select_cycle",
        v17_shifted_hex,
        _press_sequence(["SELECT"] * 4),
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_menu_mixed_navigation(v17_shifted_hex: Path) -> None:
    _run_and_compare(
        "menu_mixed",
        v17_shifted_hex,
        _press_sequence(["SELECT", "UP", "SELECT", "DOWN", "SELECT", "LEFT", "RIGHT"]),
    )


# ---------------------------------------------------------------------------
# Scenario D: STBY toggle.  Enters/exits standby mode, issues the
# standby/wake MAIN frame over TX.
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_stby_enter_then_wake(v17_shifted_hex: Path) -> None:
    _run_and_compare(
        "stby_toggle",
        v17_shifted_hex,
        _press_sequence(["STBY", "STBY"]),
    )


# ---------------------------------------------------------------------------
# Scenario E: UART RX parser responses.  Inject a sequence of BF/XX
# frames (MAIN replies) and observe that the parser updates caches and
# TX/flag state identically.
# ---------------------------------------------------------------------------

def _rx_sequence(frames: Sequence[Tuple[int, int, int]]) -> Callable[[GpsimControlHarness], None]:
    def _do(h: GpsimControlHarness) -> None:
        for route, cmd, data in frames:
            h.inject_triplet(RxTriplet(route=route, cmd=cmd, data=data))
            for _ in range(_RX_STEPS_PER_FRAME):
                h.step()
    return _do


@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_rx_bf_status_frames(v17_shifted_hex: Path) -> None:
    """Inject the full BF/* status-echo set MAIN sends during sync."""
    _run_and_compare(
        "rx_bf_status",
        v17_shifted_hex,
        _rx_sequence([
            (0xBF, 0x03, 0x01),  # standby status: awake
            (0xBF, 0x05, 0x00),  # raw status clear
            (0xBF, 0x06, 0x01),  # input_select = 1
            (0xBF, 0x07, 0x45),  # volume = 0x45
            (0xBF, 0x1D, 0x7F),  # cmd1d setting
        ]),
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_rx_volume_sweep(v17_shifted_hex: Path) -> None:
    """Sweep volume BF/07 across the range, checking cache tracking."""
    _run_and_compare(
        "rx_volume_sweep",
        v17_shifted_hex,
        _rx_sequence([(0xBF, 0x07, v) for v in (0x20, 0x40, 0x60, 0x7F)]),
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_rx_input_cycle(v17_shifted_hex: Path) -> None:
    """Cycle input_select through the BF/06 echo path."""
    _run_and_compare(
        "rx_input_cycle",
        v17_shifted_hex,
        _rx_sequence([(0xBF, 0x06, i) for i in range(4)]),
    )


# ---------------------------------------------------------------------------
# Scenario F: combined button press + RX response.  Models a real MAIN
# replying to a button-initiated command and verifying that both the
# request TX frame and the RX-reply parser state agree.
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_press_then_rx_echo(v17_shifted_hex: Path) -> None:
    def _do(h: GpsimControlHarness) -> None:
        h.press("UP")
        for _ in range(_STEPS_PER_PRESS):
            h.step()
        h.inject_triplet(RxTriplet(route=0xBF, cmd=0x07, data=0x46))
        for _ in range(_RX_STEPS_PER_FRAME):
            h.step()
        h.press("UP")
        for _ in range(_STEPS_PER_PRESS):
            h.step()

    _run_and_compare("press_then_rx", v17_shifted_hex, _do)


# ---------------------------------------------------------------------------
# Scenario G: decoded IR event.  Drives the ir_rc5_decode dispatch by
# seeding the RC5 decoded cmd/addr registers directly.  Exercises the
# IR→TX mapping for the canonical Hypex RC5 profile.
# ---------------------------------------------------------------------------

def _ir_event(addr: int, cmd: int) -> Callable[[GpsimControlHarness], None]:
    def _do(h: GpsimControlHarness) -> None:
        h.inject_decoded_ir_event(addr=addr, cmd=cmd)
        for _ in range(_STEPS_PER_PRESS):
            h.step()
    return _do


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "addr,cmd,label",
    [
        (0x10, 0x10, "ir_volume_up"),
        (0x10, 0x11, "ir_volume_down"),
        (0x10, 0x20, "ir_preset_next"),
        (0x10, 0x0C, "ir_standby"),
    ],
)
def test_parity_ir_decoded_event(
    v17_shifted_hex: Path, addr: int, cmd: int, label: str
) -> None:
    _run_and_compare(
        f"ir_{label}",
        v17_shifted_hex,
        _ir_event(addr, cmd),
    )


# ---------------------------------------------------------------------------
# Scenario H: TX frames immediately after boot warmup.  Covers the
# full-sync burst (function_028), the preset echo sequence, and the
# periodic poll.  This is the same behavioral surface that
# test_control_gpsim_command_emission_legacy.py guards for V1.41.
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_boot_full_sync_burst(v17_shifted_hex: Path) -> None:
    def _do(h: GpsimControlHarness) -> None:
        # Give the periodic full-sync emitter a chance to run after warmup.
        for _ in range(40):
            h.step()
    _run_and_compare(
        "boot_full_sync",
        v17_shifted_hex,
        _do,
    )


# ---------------------------------------------------------------------------
# Scenario I: host-command injection (HFD over BF).  Simulates a PC
# sending HFD route commands into CONTROL — exercises the parser's
# preset-select (0x20) and setting (0x1D) code paths.
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_host_preset_select(v17_shifted_hex: Path) -> None:
    def _do(h: GpsimControlHarness) -> None:
        h.inject_host_command(cmd=0x20, data=0x00)
        for _ in range(12):
            h.step()
        h.inject_host_command(cmd=0x20, data=0x01)
        for _ in range(12):
            h.step()
    _run_and_compare("host_preset_toggle", v17_shifted_hex, _do)


@pytest.mark.gpsim
@pytest.mark.slow
def test_parity_host_cmd1d_setting(v17_shifted_hex: Path) -> None:
    def _do(h: GpsimControlHarness) -> None:
        for value in (0x10, 0x20, 0x40, 0x7F):
            h.inject_host_command(cmd=0x1D, data=value)
            for _ in range(8):
                h.step()
    _run_and_compare("host_cmd1d_sweep", v17_shifted_hex, _do)
