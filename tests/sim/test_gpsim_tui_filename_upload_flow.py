"""gpsim TUI regression tests for preset-screen filename upload flow (hotkey 3)."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pytest

from scripts import gpsim_tui_simulator as tui


def _require_gpsim_toolchain() -> None:
    if shutil.which("gpsim") is None:
        pytest.skip("gpsim not installed")
    if shutil.which("gpasm") is None:
        pytest.skip("gpasm not installed")


class _FakeScreen:
    def __init__(self, keys: list[int]) -> None:
        self.keys = list(keys)
        self._line1 = " " * 16
        self._line2 = " " * 16
        self.history: list[tuple[str, str]] = []

    def nodelay(self, _flag: bool) -> None:
        return None

    def timeout(self, _ms: int) -> None:
        return None

    def getch(self) -> int:
        if self.keys:
            return self.keys.pop(0)
        return -1

    def getmaxyx(self) -> tuple[int, int]:
        return (80, 200)

    def addstr(self, y: int, _x: int, s: str, _attr: int = 0) -> None:
        if y == 6 and s.startswith("|") and s.endswith("|"):
            self._line1 = s[1:-1]
        elif y == 7 and s.startswith("|") and s.endswith("|"):
            self._line2 = s[1:-1]

    def erase(self) -> None:
        return None

    def refresh(self) -> None:
        self.history.append((self._line1, self._line2))


def _args(control_hex: Path, main_hex: Path) -> argparse.Namespace:
    return argparse.Namespace(
        hex=control_hex,
        main_hex=[main_hex],
        gpasm="gpasm",
        chunk_cycles=300_000,
        sim_quantum_cycles=0,
        main_chunk_cycles=300_000,
        main0_standby="hold",
        main1_standby="hold",
        main_ra0=0x0000,
        main0_rc2="high",
        main1_rc2="low",
        main_timer3="shim",
        hold_cycles=240_000,
        initial_cycles=20_000_000,
        poll_s=0.0,
        fast_boot=True,
        single_main=False,
        rx_fifo_limit=47,
    )


def _run_tui_scripted(
    control_hex: Path, main_hex: Path, keys: list[int], names: list[str]
) -> list[tuple[str, str]]:
    fs = _FakeScreen(keys)
    orig_curs_set = tui.curses.curs_set
    orig_sleep = tui.time.sleep
    orig_name_gen = tui._random_upload_filename
    name_iter = iter(names)
    try:
        tui.curses.curs_set = lambda _x: None
        tui.time.sleep = lambda _x: None
        tui._random_upload_filename = lambda _rng: next(name_iter)
        rc = tui.run_tui(fs, _args(control_hex, main_hex))
    finally:
        tui.curses.curs_set = orig_curs_set
        tui.time.sleep = orig_sleep
        tui._random_upload_filename = orig_name_gen
    assert rc == 0
    return fs.history


def _preset_snapshots(history: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for l1, l2 in history:
        if len(l1) != 16 or len(l2) != 16:
            continue
        if l1.startswith("Volume:") or l1.startswith("Input:") or l1.startswith("Setup"):
            continue
        if l1[14:15] == " " and l1[15:16] in ("A", "B"):
            out.append((l1[15], l1[:14] + l2))
            continue
        if l1[0:1] in ("A", "B") and l1[1:2] == ":":
            out.append((l1[0], l1[2:] + l2))
    return out


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "control_hex_fixture",
    ["patched_control_hex", "patched_control_hex_v151b", "patched_control_hex_v161b"],
)
def test_tui_hotkey3_updates_a_b_filenames(
    request: pytest.FixtureRequest,
    control_hex_fixture: str,
    patched_main_hex: Path,
) -> None:
    _require_gpsim_toolchain()
    control_hex = request.getfixturevalue(control_hex_fixture)

    wait = [-1] * 140
    # Enter preset (d), upload A, toggle to B (x), upload B, toggle to A (w), upload A again.
    keys = (
        [ord("d")]
        + wait
        + [ord("3")]
        + wait
        + [ord("x")]
        + wait
        + [ord("3")]
        + wait
        + [ord("w")]
        + wait
        + [ord("3")]
        + wait
        + [ord("q")]
    )
    history = _run_tui_scripted(
        control_hex,
        patched_main_hex,
        keys,
        names=["A_UPLOAD_01", "B_UPLOAD_01", "A_UPLOAD_02"],
    )
    seen = _preset_snapshots(history)

    assert ("A", "A_UPLOAD_01".ljust(30)) in seen
    assert ("B", "B_UPLOAD_01".ljust(30)) in seen
    assert ("A", "A_UPLOAD_02".ljust(30)) in seen
    assert seen[-1] == ("A", "A_UPLOAD_02".ljust(30))


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "control_hex_fixture",
    ["patched_control_hex", "patched_control_hex_v151b", "patched_control_hex_v161b"],
)
def test_tui_quick_toggle_then_upload_b_still_refreshes(
    request: pytest.FixtureRequest,
    control_hex_fixture: str,
    patched_main_hex: Path,
) -> None:
    _require_gpsim_toolchain()
    control_hex = request.getfixturevalue(control_hex_fixture)

    settle = [-1] * 80
    quick = [-1] * 12
    wait = [-1] * 180
    # Enter preset (d), quick A/B toggles, settle on B, then upload.
    keys = (
        [ord("d")]
        + settle
        + [ord("x")]
        + quick
        + [ord("w")]
        + quick
        + [ord("x")]
        + settle
        + [ord("3")]
        + wait
        + [ord("q")]
    )
    history = _run_tui_scripted(
        control_hex,
        patched_main_hex,
        keys,
        names=["B_STRESS_02"],
    )
    seen = _preset_snapshots(history)

    assert ("B", "B_STRESS_02".ljust(30)) in seen
    assert seen[-1] == ("B", "B_STRESS_02".ljust(30))


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "control_hex_fixture",
    ["patched_control_hex", "patched_control_hex_v151b", "patched_control_hex_v161b"],
)
def test_tui_repeated_same_preset_upload_refreshes_filename(
    request: pytest.FixtureRequest,
    control_hex_fixture: str,
    patched_main_hex: Path,
) -> None:
    _require_gpsim_toolchain()
    control_hex = request.getfixturevalue(control_hex_fixture)

    wait = [-1] * 160
    # Enter preset (A), upload A#1, then upload A#2 without switching preset.
    keys = (
        [ord("d")]
        + wait
        + [ord("3")]
        + wait
        + [ord("3")]
        + wait
        + [ord("q")]
    )
    history = _run_tui_scripted(
        control_hex,
        patched_main_hex,
        keys,
        names=["A_SAME_01", "A_SAME_02"],
    )
    seen = _preset_snapshots(history)

    assert ("A", "A_SAME_01".ljust(30)) in seen
    assert ("A", "A_SAME_02".ljust(30)) in seen
    assert seen[-1] == ("A", "A_SAME_02".ljust(30))


@pytest.mark.gpsim
@pytest.mark.slow
def test_tui_rapid_toggle_does_not_mix_a_b_filename_caches(
    patched_control_hex_v151b: Path, patched_main_hex: Path
) -> None:
    _require_gpsim_toolchain()

    wait = [-1] * 120
    quick = [-1] * 2
    # Enter preset (d), upload A, switch to B (x), upload B,
    # then rapidly toggle A/B without further uploads.
    toggles: list[int] = []
    for _ in range(20):
        toggles.extend([ord("w")] + quick + [ord("x")] + quick)
    keys = (
        [ord("d")]
        + wait
        + [ord("3")]
        + wait
        + [ord("x")]
        + wait
        + [ord("3")]
        + wait
        + toggles
        + ([-1] * 160)
        + [ord("q")]
    )
    a_name = "A_STABLE_01".ljust(30)
    b_name = "B_STABLE_01".ljust(30)
    history = _run_tui_scripted(
        patched_control_hex_v151b,
        patched_main_hex,
        keys,
        names=["A_STABLE_01", "B_STABLE_01"],
    )
    seen = _preset_snapshots(history)

    assert ("A", a_name) in seen
    assert ("B", b_name) in seen

    # After B is first known-good, every displayed snapshot must match
    # the selected preset's own cached name (no cross-preset mixing).
    start = seen.index(("B", b_name))
    for preset, rendered in seen[start:]:
        if preset == "A":
            assert rendered == a_name
        else:
            assert rendered == b_name


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "control_hex_fixture",
    ["patched_control_hex", "patched_control_hex_v151b", "patched_control_hex_v161b"],
)
def test_tui_enter_preset_without_upload_still_shows_preset_layout(
    request: pytest.FixtureRequest,
    control_hex_fixture: str,
    patched_main_hex: Path,
) -> None:
    _require_gpsim_toolchain()
    control_hex = request.getfixturevalue(control_hex_fixture)

    keys = [ord("d")] + ([-1] * 220) + [ord("q")]
    history = _run_tui_scripted(control_hex, patched_main_hex, keys, names=[])
    seen = _preset_snapshots(history)

    assert seen, "RIGHT should enter Preset even without upload"
    # Before any upload, layout must still be deterministic (blank filename region).
    assert any(name == (" " * 30) for _, name in seen)


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "control_hex_fixture",
    ["patched_control_hex", "patched_control_hex_v151b", "patched_control_hex_v161b"],
)
def test_tui_rapid_toggle_without_upload_keeps_blank_filename(
    request: pytest.FixtureRequest,
    control_hex_fixture: str,
    patched_main_hex: Path,
) -> None:
    _require_gpsim_toolchain()
    control_hex = request.getfixturevalue(control_hex_fixture)

    quick = [-1] * 4
    toggles: list[int] = []
    for _ in range(24):
        toggles.extend([ord("x")] + quick + [ord("w")] + quick)
    keys = [ord("d")] + ([-1] * 80) + toggles + ([-1] * 160) + [ord("q")]

    history = _run_tui_scripted(control_hex, patched_main_hex, keys, names=[])
    seen = _preset_snapshots(history)

    assert seen, "Preset snapshots should exist during rapid A/B toggling"
    assert any(preset == "A" for preset, _ in seen)
    assert any(preset == "B" for preset, _ in seen)
    assert all(name == (" " * 30) for _, name in seen)
