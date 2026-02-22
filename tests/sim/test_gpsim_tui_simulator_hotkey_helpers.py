from __future__ import annotations

import random

from scripts.gpsim_tui_simulator import (
    _control_active_preset,
    _cmd_label,
    _encode_filename_slot,
    _has_preset_screen_layout,
    _next_filename_req_token,
    _random_upload_filename,
    _runtime_chunks_for_mode,
)
from dlcp_fw.paths import (
    PATCHED_CONTROL_HEX,
    PATCHED_CONTROL_HEX_V151B,
    PATCHED_CONTROL_HEX_V161B,
    STOCK_CONTROL_HEX_V14,
    STOCK_CONTROL_HEX_V15B,
    STOCK_CONTROL_HEX_V16B,
)


def test_cmd_label_includes_filename_request_and_chunks() -> None:
    assert _cmd_label(0x21) == "FILENAME_REQ"
    assert _cmd_label(0x22) == "FILENAME_GEN_REQ"
    assert _cmd_label(0x2F) == "FILENAME_CTX"
    assert _cmd_label(0x30) == "FILENAME_CHUNK[0]"
    assert _cmd_label(0x37) == "FILENAME_CHUNK[7]"
    assert _cmd_label(0x38) == "CMD?"


def test_encode_filename_slot_maps_null_to_ff_and_pads() -> None:
    slot = _encode_filename_slot("AB\x00CD")
    assert len(slot) == 30
    assert slot[:5] == b"AB\xffCD"
    assert slot[5:] == bytes([0xFF] * 25)


def test_random_upload_filename_len_and_charset() -> None:
    rng = random.Random(1234)
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    for _ in range(64):
        name = _random_upload_filename(rng)
        assert 12 <= len(name) <= 17
        assert set(name).issubset(allowed)


def test_next_filename_req_token_advances_txn_and_sets_preset() -> None:
    assert _next_filename_req_token(0x00, 0) == 0x08  # txn 1, page0, preset A
    assert _next_filename_req_token(0x08, 1) == 0x11  # txn 2, page0, preset B
    assert _next_filename_req_token(0x79, 0) == 0x00  # 4-bit txn wrap, bit7 stays clear


def test_control_active_preset_reads_live_flag_bit() -> None:
    calls: list[int] = []

    def issue(cmd: str, _: float) -> str:
        calls.append(1)
        if cmd == "reg(0x01f)":
            return "[0x01f] = 0x40"
        raise AssertionError(cmd)

    assert _control_active_preset(issue) == 1
    assert calls


def test_runtime_chunks_for_mode_preserves_main_chunk_outside_filename_flow() -> None:
    assert _runtime_chunks_for_mode(
        filename_flow_active=False,
        runtime_control_chunk=300_000,
        runtime_main_chunk=120_000,
        filename_flow_chunk=30_000,
    ) == (300_000, 120_000)

    assert _runtime_chunks_for_mode(
        filename_flow_active=True,
        runtime_control_chunk=300_000,
        runtime_main_chunk=120_000,
        filename_flow_chunk=30_000,
    ) == (30_000, 30_000)


def test_has_preset_screen_layout_detects_patched_and_stock_control_hex() -> None:
    assert _has_preset_screen_layout(PATCHED_CONTROL_HEX)
    assert _has_preset_screen_layout(PATCHED_CONTROL_HEX_V151B)
    assert _has_preset_screen_layout(PATCHED_CONTROL_HEX_V161B)
    assert not _has_preset_screen_layout(STOCK_CONTROL_HEX_V14)
    assert not _has_preset_screen_layout(STOCK_CONTROL_HEX_V15B)
    assert not _has_preset_screen_layout(STOCK_CONTROL_HEX_V16B)
