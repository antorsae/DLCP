from __future__ import annotations

import tempfile
from pathlib import Path

from dlcp_fw.sim.control_ui import ControlPersistentState, ControlStrings, ControlUISim
from dlcp_fw.sim.protocol import SerialFrame


def _req_txn(data: int) -> int:
    return (data >> 3) & 0x1F


def _req_page(data: int) -> int:
    return (data >> 1) & 0x03


def _req_preset(data: int) -> int:
    return data & 0x01


def _assert_req(frame: SerialFrame, *, page: int, preset: int) -> None:
    assert frame.route == 0xB1
    assert frame.cmd == 0x21
    assert _req_page(frame.data) == page
    assert _req_preset(frame.data) == preset


def _assert_gen_req(frame: SerialFrame, *, preset: int) -> None:
    assert frame.route == 0xB1
    assert frame.cmd == 0x22
    assert _req_page(frame.data) == 0
    assert _req_preset(frame.data) == preset


def _ingest_generation_reply(sim: ControlUISim, gen: int) -> int:
    req = sim.filename_expected_req & 0xFF
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req))
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x22, data=gen & 0x7F))
    return req


def _ingest_full_filename_for_active_request(sim: ControlUISim, text: str, *, gen: int = 1) -> None:
    _ingest_generation_reply(sim, gen)
    payload = text[:30].ljust(30).encode("ascii")
    spans = [(0, 8), (8, 16), (16, 24), (24, 30)]
    for start, end in spans:
        req = sim.filename_expected_req & 0xFF
        sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req))
        for local_idx, abs_idx in enumerate(range(start, end)):
            sim.ingest_rx_frame(
                SerialFrame(route=0xBF, cmd=0x30 + local_idx, data=payload[abs_idx])
            )


def test_preset_screen_navigation(patched_control_hex) -> None:
    """Volume -> Preset -> switch to B -> back to Volume shows B."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()

    # Initial state: Volume with A
    l1, l2 = sim.render()
    assert l1 == "Volume:        A"

    # RIGHT -> Preset screen (A active by default)
    sim.press("R")
    l1, l2 = sim.render()
    assert l1 == (" " * 15) + "A"
    assert l2 == "                "

    # DOWN -> select B
    sim.press("D")
    l1, l2 = sim.render()
    assert l1 == (" " * 15) + "B"
    assert l2 == "                "
    assert sim.preset == 1

    # LEFT -> back to Volume, shows B
    sim.press("L")
    l1, _ = sim.render()
    assert l1 == "Volume:        B"


def test_keypress_script_emits_preset_frames(patched_control_hex) -> None:
    """Preset screen emits preset and filename-request command frames."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()

    # Navigate to Preset, switch B then A
    script = ["R", "D", "U"]
    sim.run_script(script)

    assert len(sim.tx_frames) == 5
    _assert_gen_req(sim.tx_frames[0], preset=0)  # enter preset screen
    assert sim.tx_frames[1] == SerialFrame(route=0xB0, cmd=0x20, data=0x01)  # select B
    _assert_gen_req(sim.tx_frames[2], preset=1)  # request B generation
    assert sim.tx_frames[3] == SerialFrame(route=0xB0, cmd=0x20, data=0x00)  # select A
    _assert_gen_req(sim.tx_frames[4], preset=0)  # request A generation
    assert _req_txn(sim.tx_frames[2].data) == ((_req_txn(sim.tx_frames[0].data) + 1) & 0x1F)
    assert _req_txn(sim.tx_frames[4].data) == ((_req_txn(sim.tx_frames[2].data) + 1) & 0x1F)


def test_four_screen_wraparound(patched_control_hex) -> None:
    """Navigation wraps: Volume -> Preset -> Input -> Setup -> Volume."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()

    assert sim.menu_state == 0  # Volume
    sim.press("R")
    assert sim.menu_state == 1  # Preset
    sim.press("R")
    assert sim.menu_state == 2  # Input
    sim.press("R")
    assert sim.menu_state == 3  # Setup
    sim.press("R")
    assert sim.menu_state == 0  # Volume (wrap)

    # And LEFT wraps the other way
    sim.press("L")
    assert sim.menu_state == 3  # Setup
    sim.press("L")
    assert sim.menu_state == 2  # Input
    sim.press("L")
    assert sim.menu_state == 1  # Preset
    sim.press("L")
    assert sim.menu_state == 0  # Volume


def test_power_cycle_persists_last_preset(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    # Navigate to Preset and switch to B
    sim.run_script(["R", "D"])
    assert sim.preset == 1
    assert sim.persist.load_preset() == 1
    # Verify EEPROM address matches patched firmware (0x74)
    assert sim.persist.eeprom[0x74] == 1

    sim2 = sim.power_cycle()
    assert sim2.preset == 1
    line1, _ = sim2.render()
    assert line1 == "Volume:        B"


def test_eeprom_file_roundtrip(patched_control_hex) -> None:
    """Save EEPROM to file, load in new sim, verify preset survives."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R", "D"])  # switch to preset B
    assert sim.preset == 1

    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "eeprom.bin"
        sim.persist.save_to_file(eeprom_path)
        assert eeprom_path.exists()
        assert len(eeprom_path.read_bytes()) == 256

        # Create a fresh sim with a new persistent state loaded from file
        persist2 = ControlPersistentState()
        persist2.load_from_file(eeprom_path)
        sim2 = ControlUISim(st=st, persist=persist2)
        sim2.boot()
        assert sim2.preset == 1
        line1, _ = sim2.render()
        assert line1 == "Volume:        B"


def test_fresh_eeprom_defaults_to_preset_a(patched_control_hex) -> None:
    """Fresh 0xFF EEPROM defaults to preset A."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    persist = ControlPersistentState()
    # All 0xFF — simulates blank EEPROM
    assert persist.eeprom[0x74] == 0xFF
    sim = ControlUISim(st=st, persist=persist)
    sim.boot()
    assert sim.preset == 0
    line1, _ = sim.render()
    assert line1 == "Volume:        A"


def test_volume_resets_on_power_cycle(patched_control_hex) -> None:
    """Volume is volatile — it resets to default (0x33) on power cycle."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    # Change volume
    sim.press("U")
    sim.press("U")
    sim.press("U")
    assert sim.volume_steps == 0x36

    sim2 = sim.power_cycle()
    assert sim2.volume_steps == 0x33


def test_preset_selection_is_idempotent(patched_control_hex) -> None:
    """Selecting already-active preset should not emit duplicate frames."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R"])  # Volume -> Preset

    # Entering Preset emits one generation request for active preset A.
    assert len(sim.tx_frames) == 1
    _assert_gen_req(sim.tx_frames[0], preset=0)

    # Already in A; UP should be no-op.
    sim.press("U")
    assert sim.preset == 0
    assert len(sim.tx_frames) == 1
    _assert_gen_req(sim.tx_frames[0], preset=0)

    # Switch to B once, then press DOWN again (no-op).
    sim.press("D")
    sim.press("D")
    assert sim.preset == 1
    assert len(sim.tx_frames) == 3
    _assert_gen_req(sim.tx_frames[0], preset=0)
    assert sim.tx_frames[1] == SerialFrame(route=0xB0, cmd=0x20, data=0x01)
    _assert_gen_req(sim.tx_frames[2], preset=1)


def test_preset_line2_uses_selected_cache(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R"])  # into Preset (A)

    text_a = "DSP Filename A  ".ljust(30)
    _ingest_full_filename_for_active_request(sim, text_a)
    l1, l2 = sim.render()
    assert l1 == f"{text_a[:14]} A"
    assert l2 == text_a[14:30]

    sim.press("D")  # select B
    text_b = "DSP Filename B  ".ljust(30)
    _ingest_full_filename_for_active_request(sim, text_b)
    l1, l2 = sim.render()
    assert l1 == f"{text_b[:14]} B"
    assert l2 == text_b[14:30]

    sim.press("U")  # back to A; old A cache should still render
    l1, l2 = sim.render()
    assert l1 == f"{text_a[:14]} A"
    assert l2 == text_a[14:30]


def test_preset_screen_renders_full_30_byte_name_across_two_lines(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R"])  # into Preset (A)

    full = "123456789012345678901234567890"
    _ingest_full_filename_for_active_request(sim, full)
    l1, l2 = sim.render()
    assert l1 == "12345678901234 A"
    assert l2 == "5678901234567890"

    # Feed a stale/invalid chunk command outside 0x30..0x37; must be ignored.
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x4D, data=ord("Z")))
    l1b, l2b = sim.render()
    assert l1b == "12345678901234 A"
    assert l2b == "5678901234567890"


def test_filename_fetch_uses_paged_cmd21_requests(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R"])  # into Preset (A) -> generation request

    assert len(sim.tx_frames) == 1
    gen_req = sim.tx_frames[-1]
    _assert_gen_req(gen_req, preset=0)
    txn = _req_txn(gen_req.data)

    # Generation reply (unknown on first request) should trigger page0 cmd=0x21 fetch.
    _ingest_generation_reply(sim, gen=0x11)
    req0 = sim.tx_frames[-1]
    _assert_req(req0, page=0, preset=0)
    assert _req_txn(req0.data) == txn

    # Feed page 0 context+chunks: simulator should request page 1.
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req0.data))
    for i in range(8):
        sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x30 + i, data=ord("A")))
    req1 = sim.tx_frames[-1]
    _assert_req(req1, page=1, preset=0)
    assert _req_txn(req1.data) == txn

    # Feed page 1 context+chunks: next request page 2.
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req1.data))
    for i in range(8):
        sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x30 + i, data=ord("B")))
    req2 = sim.tx_frames[-1]
    _assert_req(req2, page=2, preset=0)
    assert _req_txn(req2.data) == txn

    # Feed page 2 context+chunks: next request page 3.
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req2.data))
    for i in range(8):
        sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x30 + i, data=ord("C")))
    req3 = sim.tx_frames[-1]
    _assert_req(req3, page=3, preset=0)
    assert _req_txn(req3.data) == txn


def test_stale_filename_context_is_ignored_after_preset_toggle(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R"])  # Preset A -> generation req A
    req_a = sim.tx_frames[-1].data

    sim.press("D")  # switch to B -> generation req B with newer txn
    req_b = sim.tx_frames[-1].data
    assert _req_preset(req_a) == 0
    assert _req_preset(req_b) == 1
    assert _req_txn(req_b) != _req_txn(req_a)

    # Delayed/stale transfer for A must not be accepted.
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req_a))
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x22, data=0x55))
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x30, data=ord("X")))
    assert sim.filename_cache[0][0] == 0x20
    assert sim.filename_cache[1][0] == 0x20

    # Matching generation reply for current B request triggers paged fetch.
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req_b))
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x22, data=0x56))
    req_b0 = sim.tx_frames[-1].data
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req_b0))
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x30, data=ord("Y")))
    assert sim.filename_cache[0][0] == 0x20
    assert sim.filename_cache[1][0] == 0x20
    assert sim.filename_stage[0] == ord("Y")

    # Cache updates only after completed page boundaries, not on partial chunks.
    for i in range(1, 8):
        sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x30 + i, data=ord("Y")))
    req_b1 = sim.tx_frames[-1].data
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req_b1))
    for i in range(8):
        sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x30 + i, data=ord("Y")))
    req_b2 = sim.tx_frames[-1].data
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req_b2))
    for i in range(8):
        sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x30 + i, data=ord("Y")))
    req_b3 = sim.tx_frames[-1].data
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req_b3))
    for i in range(6):
        sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x30 + i, data=ord("Y")))
    assert sim.filename_cache[1][0] == ord("Y")


def test_generation_match_skips_cmd21_data_fetch(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R"])  # initial generation request

    # First load: generation unknown -> cmd21 fetch + cache commit.
    _ingest_full_filename_for_active_request(sim, "GEN-CACHED-A", gen=0x41)
    base = len(sim.tx_frames)

    # Re-enter preset and reply with same generation: no cmd21 should follow.
    sim.press("L")
    sim.press("R")
    _assert_gen_req(sim.tx_frames[-1], preset=0)
    _ingest_generation_reply(sim, gen=0x41)

    new_frames = sim.tx_frames[base:]
    assert any(f.cmd == 0x22 for f in new_frames)
    assert not any(f.cmd == 0x21 for f in new_frames)


def test_generation_mismatch_triggers_cmd21_data_fetch(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R"])  # initial generation request

    _ingest_full_filename_for_active_request(sim, "GEN-OLD-A", gen=0x10)
    base = len(sim.tx_frames)

    sim.press("L")
    sim.press("R")
    _assert_gen_req(sim.tx_frames[-1], preset=0)
    _ingest_generation_reply(sim, gen=0x11)

    new_frames = sim.tx_frames[base:]
    assert any(f.cmd == 0x22 for f in new_frames)
    assert any(f.cmd == 0x21 for f in new_frames)


def test_generation_cache_updates_only_after_full_transfer_commit(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R"])  # initial generation request

    # Build initial committed cache at gen=0x20.
    _ingest_full_filename_for_active_request(sim, "OLD_FILENAME_A", gen=0x20)
    assert sim.filename_generation_cache[0] == 0x20
    assert (sim.filename_generation_valid_mask & 0x01) == 0x01
    baseline_char = sim.filename_cache[0][0]

    # New generation arrives, but transfer is interrupted after first chunk.
    sim.press("L")
    sim.press("R")
    _assert_gen_req(sim.tx_frames[-1], preset=0)
    _ingest_generation_reply(sim, gen=0x21)
    req = sim.filename_expected_req & 0xFF
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x2F, data=req))
    sim.ingest_rx_frame(SerialFrame(route=0xBF, cmd=0x30, data=ord("N")))

    # No full commit yet: generation cache and displayed cache stay old.
    assert sim.filename_generation_cache[0] == 0x20
    assert (sim.filename_generation_valid_mask & 0x01) == 0x01
    assert sim.filename_cache[0][0] == baseline_char

    # Re-request same generation: must retry cmd21 (not cache-hit skip).
    base = len(sim.tx_frames)
    sim.press("L")
    sim.press("R")
    _assert_gen_req(sim.tx_frames[-1], preset=0)
    _ingest_generation_reply(sim, gen=0x21)
    new_frames = sim.tx_frames[base:]
    assert any(f.cmd == 0x22 for f in new_frames)
    assert any(f.cmd == 0x21 for f in new_frames)
