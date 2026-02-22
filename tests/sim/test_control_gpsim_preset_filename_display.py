"""gpsim regression tests for CONTROL preset-screen DSP filename display path."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness


WARMUP_CYCLES = 25_000_000
STEP_COUNT = 10


def _require_gpsim() -> None:
    if shutil.which("gpsim") is None:
        pytest.skip("gpsim not installed")


def _boot_harness(patched_control_hex: Path) -> GpsimControlHarness:
    h = GpsimControlHarness(
        patched_control_hex,
        fast_boot=True,
        chunk_cycles=200_000,
        hold_cycles=120_000,
        heartbeat_rx_mode="none",
        heartbeat_force_connected=True,
    )
    h.warmup(WARMUP_CYCLES)
    return h


def _press_and_step(h: GpsimControlHarness, key: str, steps: int = STEP_COUNT) -> None:
    h.press(key)
    for _ in range(steps):
        h.step()


def _req_txn(data: int) -> int:
    return (data >> 3) & 0x1F


def _req_page(data: int) -> int:
    return (data >> 1) & 0x03


def _req_preset(data: int) -> int:
    return data & 0x01


def _last_req_data(h: GpsimControlHarness, *, cmd: int = 0x21) -> int:
    for f in reversed(h.tx_frames()):
        if f.route == 0xB1 and f.cmd == cmd:
            return f.data & 0xFF
    raise AssertionError(f"missing request frame cmd=0x{cmd:02X}")


def _inject_generation_reply(h: GpsimControlHarness, *, gen: int) -> int:
    req = _last_req_data(h, cmd=0x22)
    h.inject_host_command(cmd=0x2F, data=req, steps=0)
    h.inject_host_command(cmd=0x22, data=gen & 0x7F, steps=0)
    for _ in range(6):
        h.step()
    return req


def _inject_filename_full(h: GpsimControlHarness, text30: str, *, gen: int = 1) -> list[int]:
    s = text30[:30].ljust(30).encode("ascii")
    _inject_generation_reply(h, gen=gen)
    reqs: list[int] = []
    spans = [(0, 8), (8, 16), (16, 24), (24, 30)]
    for start, end in spans:
        req = _last_req_data(h, cmd=0x21)
        reqs.append(req)
        h.inject_host_command(cmd=0x2F, data=req, steps=1)
        for local_idx, abs_idx in enumerate(range(start, end)):
            h.inject_host_command(cmd=0x30 + local_idx, data=s[abs_idx], steps=1)
        for _ in range(6):
            h.step()
    return reqs


def _inject_filename_line(h: GpsimControlHarness, text16: str) -> None:
    s = text16[:16].ljust(16) + (" " * 14)
    _inject_filename_full(h, s)
    for _ in range(8):
        h.step()


def _displayed_preset_and_name(h: GpsimControlHarness) -> tuple[int, str]:
    l1, l2 = h.lcd_lines()
    if len(l1) != 16 or len(l2) != 16:
        raise AssertionError(f"unexpected LCD dimensions: {l1!r} / {l2!r}")
    if l1.startswith("Volume:") or l1.startswith("Input:") or l1.startswith("Setup"):
        raise AssertionError(f"not in preset filename screen: {l1!r} / {l2!r}")

    # Legacy format: "<name[0..13]> <A|B>"
    if l1[14] == " " and l1[15] in ("A", "B"):
        preset_idx = 1 if l1[15] == "B" else 0
        return preset_idx, (l1[:14] + l2)

    # Prefix format: "<A|B>:<name[0..13]>"
    if l1[0] in ("A", "B") and l1[1] == ":":
        preset_idx = 1 if l1[0] == "B" else 0
        return preset_idx, (l1[2:] + l2)

    raise AssertionError(f"not in preset filename screen: {l1!r} / {l2!r}")


def _ensure_preset_screen(h: GpsimControlHarness, *, max_tries: int = 10) -> None:
    for _ in range(max_tries):
        l1, l2 = h.lcd_lines()
        if len(l1) == 16 and len(l2) == 16:
            suffix_fmt = l1[14] == " " and l1[15] in ("A", "B")
            prefix_fmt = l1[0] in ("A", "B") and l1[1] == ":"
            if (suffix_fmt or prefix_fmt) and not l1.startswith("Volume:"):
                return
        if l1.startswith("Volume:"):
            _press_and_step(h, "R")
            continue
        if l1.startswith("Input:"):
            _press_and_step(h, "L")
            continue
        if l1.startswith("Setup"):
            _press_and_step(h, "L")
            continue
        _press_and_step(h, "L")
    l1, l2 = h.lcd_lines()
    raise AssertionError(f"failed to re-enter preset screen: {l1!r} / {l2!r}")


def _assert_displayed_name(h: GpsimControlHarness, preset_idx: int, expected_name: str) -> None:
    _ensure_preset_screen(h)
    got_preset, got_name = _displayed_preset_and_name(h)
    expected = expected_name[:30].ljust(30)
    assert got_preset == preset_idx
    assert got_name == expected


def _refresh_same_preset_request(h: GpsimControlHarness) -> None:
    # Preset -> Volume -> Preset (same active preset, fresh cmd=0x22 generation request).
    _press_and_step(h, "L")
    _press_and_step(h, "R")
    _ensure_preset_screen(h)


def _upload_for_active_preset(h: GpsimControlHarness, filename: str) -> None:
    gen = sum(filename.encode("ascii", "ignore")) & 0x7F
    if gen == 0:
        gen = 1
    _inject_filename_full(h, filename, gen=gen)
    for _ in range(8):
        h.step()


def _select_preset(h: GpsimControlHarness, preset_idx: int, *, max_tries: int = 6) -> None:
    _ensure_preset_screen(h)
    for _ in range(max_tries):
        cur, _ = _displayed_preset_and_name(h)
        if cur == preset_idx:
            return
        _press_and_step(h, "D" if preset_idx else "U")
    cur, _ = _displayed_preset_and_name(h)
    raise AssertionError(f"failed to select preset {preset_idx}, still at {cur}")


@pytest.mark.gpsim
@pytest.mark.slow
def test_enter_preset_screen_emits_filename_request_cmd21(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        before = len(h.tx_frames())
        _press_and_step(h, "R")  # Volume -> Preset
        frames = h.tx_frames()[before:]
        req = [(f.route, f.cmd, f.data) for f in frames if f.route == 0xB1 and f.cmd == 0x22]
        assert req, f"expected cmd=0x22 filename generation request frame, got {frames}"
        route, cmd, data = req[-1]
        assert (route, cmd) == (0xB1, 0x22)
        assert _req_page(data) == 0
        assert _req_preset(data) == 0
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_filename_fetch_advances_cmd21_pages(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _press_and_step(h, "R")  # enter Preset (A), initial generation request
        base = len(h.tx_frames())
        _inject_generation_reply(h, gen=0x11)
        req0 = _last_req_data(h, cmd=0x21)

        # Feed page0 context + local chunks 0..7. CONTROL should request page1.
        h.inject_host_command(cmd=0x2F, data=req0, steps=1)
        for i in range(8):
            h.inject_host_command(cmd=0x30 + i, data=ord("A"), steps=1)
        for _ in range(8):
            h.step()
        req = [(f.route, f.cmd, f.data) for f in h.tx_frames()[base:] if f.route == 0xB1 and f.cmd == 0x21]
        assert req, f"missing page1 request after page0 chunks: {req}"
        last1 = req[-1][2]
        assert _req_page(last1) == 1
        assert _req_preset(last1) == 0
        assert _req_txn(last1) == _req_txn(req0)

        # Feed page1 context + local chunks 0..7. CONTROL should request page2.
        base2 = len(h.tx_frames())
        h.inject_host_command(cmd=0x2F, data=last1, steps=1)
        for i in range(8):
            h.inject_host_command(cmd=0x30 + i, data=ord("B"), steps=1)
        for _ in range(8):
            h.step()
        req2 = [(f.route, f.cmd, f.data) for f in h.tx_frames()[base2:] if f.route == 0xB1 and f.cmd == 0x21]
        assert req2, f"missing page2 request after page1 chunks: {req2}"
        last2 = req2[-1][2]
        assert _req_page(last2) == 2
        assert _req_preset(last2) == 0
        assert _req_txn(last2) == _req_txn(req0)
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_filename_chunk_parser_updates_a_b_caches_and_renders(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _press_and_step(h, "R")  # Volume -> Preset (A selected)

        text_a = "DSP Filename A  ".ljust(30)
        _inject_filename_full(h, text_a)
        l1, l2 = h.lcd_lines()
        assert l1 == f"{text_a[:14]} A"
        assert l2 == text_a[14:30]

        _press_and_step(h, "D")  # select B
        text_b = "DSP Filename B  ".ljust(30)
        _inject_filename_full(h, text_b)
        l1, l2 = h.lcd_lines()
        assert l1 == f"{text_b[:14]} B"
        assert l2 == text_b[14:30]

        _press_and_step(h, "U")  # back to A
        l1, l2 = h.lcd_lines()
        assert l1 == f"{text_a[:14]} A"
        assert l2 == text_a[14:30]
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_non_filename_host_command_does_not_clobber_filename_render(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _press_and_step(h, "R")  # Volume -> Preset
        full = "Stable Filename  ".ljust(30)
        _inject_filename_full(h, full)
        before = h.lcd_lines()

        # Adjacent command outside v2 context/chunk range.
        h.inject_host_command(cmd=0x38, data=ord("X"), steps=1)
        for _ in range(6):
            h.step()
        after = h.lcd_lines()

        assert after == before
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_full_30_byte_filename_ingest_spans_two_lines(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _press_and_step(h, "R")  # Volume -> Preset (A)
        full = "123456789012345678901234567890"
        reqs = _inject_filename_full(h, full)
        l1, l2 = h.lcd_lines()
        assert l1 == "12345678901234 A"
        assert l2 == "5678901234567890"

        # Update idx29 using page3 context + local idx5 (cmd=0x35).
        req3 = reqs[-1]
        h.inject_host_command(cmd=0x2F, data=req3, steps=1)
        h.inject_host_command(cmd=0x35, data=ord("Z"), steps=1)
        for _ in range(8):
            h.step()
        l1b, l2b = h.lcd_lines()
        assert l1b == "12345678901234 A"
        assert l2b == "5678901234567890"
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_filename_fetch_does_not_poll_forever_after_full_slot(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        before = len(h.tx_frames())
        _press_and_step(h, "R")  # enter Preset (initial generation request)
        _inject_filename_full(h, "123456789012345678901234567890", gen=0x21)
        for _ in range(40):
            h.step()

        gen_reqs = [
            (f.route, f.cmd, f.data)
            for f in h.tx_frames()[before:]
            if f.route == 0xB1 and f.cmd == 0x22
        ]
        assert len(gen_reqs) == 1, f"expected one generation request, got {len(gen_reqs)}"

        reqs = [
            (f.route, f.cmd, f.data)
            for f in h.tx_frames()[before:]
            if f.route == 0xB1 and f.cmd == 0x21
        ]
        assert len(reqs) == 4, f"expected 4 page requests total, got {len(reqs)}: {reqs}"
        datas = [d for _, _, d in reqs]
        assert [_req_page(d) for d in datas] == [0, 1, 2, 3]
        assert [_req_preset(d) for d in datas] == [0, 0, 0, 0]
        assert len({_req_txn(d) for d in datas}) == 1
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_stale_context_after_toggle_does_not_advance_pages(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _press_and_step(h, "R")  # req A generation
        req_a = _last_req_data(h, cmd=0x22)
        _press_and_step(h, "D")  # req B generation (new txn)
        req_b = _last_req_data(h, cmd=0x22)
        assert _req_preset(req_a) == 0
        assert _req_preset(req_b) == 1
        assert _req_txn(req_a) != _req_txn(req_b)

        before = len([f for f in h.tx_frames() if f.route == 0xB1 and f.cmd == 0x21])
        h.inject_host_command(cmd=0x2F, data=req_a, steps=1)
        h.inject_host_command(cmd=0x22, data=0x44, steps=1)
        h.inject_host_command(cmd=0x30, data=ord("X"), steps=1)
        for _ in range(12):
            h.step()
        after = len([f for f in h.tx_frames() if f.route == 0xB1 and f.cmd == 0x21])
        assert after == before, "stale context/chunk unexpectedly advanced filename paging"
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_generation_match_skips_cmd21_fetch_in_gpsim(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _press_and_step(h, "R")
        _inject_filename_full(h, "GEN_CACHED_A", gen=0x66)

        before = len(h.tx_frames())
        _refresh_same_preset_request(h)
        _inject_generation_reply(h, gen=0x66)
        for _ in range(10):
            h.step()

        new_frames = h.tx_frames()[before:]
        assert any(f.route == 0xB1 and f.cmd == 0x22 for f in new_frames)
        assert not any(f.route == 0xB1 and f.cmd == 0x21 for f in new_frames)
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_generation_mismatch_triggers_cmd21_fetch_in_gpsim(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _press_and_step(h, "R")
        _inject_filename_full(h, "GEN_OLD_A", gen=0x31)

        before = len(h.tx_frames())
        _refresh_same_preset_request(h)
        _inject_generation_reply(h, gen=0x32)
        for _ in range(10):
            h.step()

        new_frames = h.tx_frames()[before:]
        assert any(f.route == 0xB1 and f.cmd == 0x22 for f in new_frames)
        assert any(f.route == 0xB1 and f.cmd == 0x21 for f in new_frames)
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_generation_cache_not_marked_valid_until_full_commit_in_gpsim(
    patched_control_hex: Path,
) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _press_and_step(h, "R")
        _inject_filename_full(h, "OLD_FILENAME_A", gen=0x20)

        # Trigger generation miss to 0x21, but inject only first chunk.
        _refresh_same_preset_request(h)
        _inject_generation_reply(h, gen=0x21)
        req = _last_req_data(h, cmd=0x21)
        h.inject_host_command(cmd=0x2F, data=req, steps=1)
        h.inject_host_command(cmd=0x30, data=ord("N"), steps=1)
        for _ in range(8):
            h.step()

        # Same generation must still trigger cmd21 fetch again (no false hit).
        base = len(h.tx_frames())
        _refresh_same_preset_request(h)
        _inject_generation_reply(h, gen=0x21)
        for _ in range(10):
            h.step()
        new_frames = h.tx_frames()[base:]
        assert any(f.route == 0xB1 and f.cmd == 0x22 for f in new_frames)
        assert any(f.route == 0xB1 and f.cmd == 0x21 for f in new_frames)
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "control_hex_fixture",
    ["patched_control_hex", "patched_control_hex_v151b", "patched_control_hex_v161b"],
)
def test_usb_upload_sequence_ab_b_update_then_a_update(
    request: pytest.FixtureRequest,
    control_hex_fixture: str,
) -> None:
    """
    End-to-end A/B filename flow:
    A=fA1, B=fB1, B=fB2, A=fA2 with preset toggles between each check.
    """
    _require_gpsim()
    h = _boot_harness(request.getfixturevalue(control_hex_fixture))
    try:
        _press_and_step(h, "R")  # Volume -> Preset (A)

        _upload_for_active_preset(h, "fA1")
        _assert_displayed_name(h, 0, "fA1")

        _select_preset(h, 1)  # A -> B
        _upload_for_active_preset(h, "fB1")
        _assert_displayed_name(h, 1, "fB1")

        _select_preset(h, 0)  # B -> A
        _assert_displayed_name(h, 0, "fA1")

        _select_preset(h, 1)  # A -> B
        _assert_displayed_name(h, 1, "fB1")

        _refresh_same_preset_request(h)  # stay on B, refresh request token/page
        _upload_for_active_preset(h, "fB2")
        _assert_displayed_name(h, 1, "fB2")

        _select_preset(h, 0)  # B -> A
        _assert_displayed_name(h, 0, "fA1")

        _select_preset(h, 1)  # A -> B
        _assert_displayed_name(h, 1, "fB2")

        _select_preset(h, 0)  # B -> A
        _refresh_same_preset_request(h)
        _upload_for_active_preset(h, "fA2")
        _assert_displayed_name(h, 0, "fA2")

        _select_preset(h, 1)  # A -> B
        _assert_displayed_name(h, 1, "fB2")

        _select_preset(h, 0)  # B -> A
        _assert_displayed_name(h, 0, "fA2")
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "control_hex_fixture",
    ["patched_control_hex", "patched_control_hex_v151b", "patched_control_hex_v161b"],
)
def test_usb_upload_sequence_blank_start_then_b_then_a_updates(
    request: pytest.FixtureRequest,
    control_hex_fixture: str,
) -> None:
    """
    Fresh start flow:
    A blank, B blank, B=fB1, B=fB2, A blank, then A=fA2 while B remains fB2.
    """
    _require_gpsim()
    h = _boot_harness(request.getfixturevalue(control_hex_fixture))
    try:
        _press_and_step(h, "R")  # Volume -> Preset (A)
        _assert_displayed_name(h, 0, "")

        _select_preset(h, 1)  # A -> B
        _assert_displayed_name(h, 1, "")

        _upload_for_active_preset(h, "fB1")
        _assert_displayed_name(h, 1, "fB1")

        _refresh_same_preset_request(h)  # stay on B
        _upload_for_active_preset(h, "fB2")
        _assert_displayed_name(h, 1, "fB2")

        _select_preset(h, 0)  # B -> A
        _assert_displayed_name(h, 0, "")

        _select_preset(h, 1)  # A -> B
        _assert_displayed_name(h, 1, "fB2")

        _select_preset(h, 0)  # B -> A
        _refresh_same_preset_request(h)
        _upload_for_active_preset(h, "fA2")
        _assert_displayed_name(h, 0, "fA2")

        _select_preset(h, 1)  # A -> B
        _assert_displayed_name(h, 1, "fB2")

        _select_preset(h, 0)  # B -> A
        _assert_displayed_name(h, 0, "fA2")
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "control_hex_fixture",
    ["patched_control_hex", "patched_control_hex_v151b", "patched_control_hex_v161b"],
)
def test_incomplete_reply_does_not_clobber_displayed_name(
    request: pytest.FixtureRequest,
    control_hex_fixture: str,
) -> None:
    """
    Regression guard: partial filename reply must not overwrite committed cache.
    """
    _require_gpsim()
    h = _boot_harness(request.getfixturevalue(control_hex_fixture))
    try:
        _press_and_step(h, "R")  # Volume -> Preset (A)
        full = "Z12345678901234567890123456789"
        _upload_for_active_preset(h, full)
        _assert_displayed_name(h, 0, full)

        _refresh_same_preset_request(h)  # same preset A, fresh request
        _inject_generation_reply(h, gen=0x2B)
        req = _last_req_data(h, cmd=0x21)
        h.inject_host_command(cmd=0x2F, data=req, steps=1)
        h.inject_host_command(cmd=0x30, data=ord("_"), steps=1)
        for _ in range(24):
            h.step()

        # Incomplete transfer must not corrupt committed cache.
        _assert_displayed_name(h, 0, full)
    finally:
        h.close()
