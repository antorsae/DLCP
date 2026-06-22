"""V1.73 atomic sender checks for multi-PB input frames."""

from __future__ import annotations

import re

from dlcp_fw.paths import V173_CONTROL_ASM


def _body(text: str, start_label: str, end_label: str) -> str:
    start = text.index(f"{start_label}:")
    end = text.index(f"{end_label}:", start)
    return text[start:end]


def test_split_input_senders_reserve_three_bytes_before_enqueue() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8")
    body = _body(text, "input_frame_send_targeted", "input_frame_send_targeted_aborted")
    assert re.search(r"call\s+tx_ring_reserve_3", body)
    assert body.index("tx_ring_reserve_3") < body.index("tx_byte_enqueue")
    assert len(re.findall(r"call\s+tx_byte_enqueue", body)) == 3
    assert "movlw   0xB1" in body
    assert "movlw   0xB2" in body
    assert "movlw   0x06" in body


def test_split_full_sync_does_not_advance_target_on_saturation() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8")
    body = _body(text, "input_frame_send_split_sync", "input_frame_send_split_sync_legacy")
    assert "btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED" in body
    assert "bra     input_frame_send_split_sync_legacy" in body
    assert re.search(
        r"rcall\s+input_frame_send_targeted\s*\n\s*"
        r"bc\s+input_frame_send_split_sync_done",
        body,
    )
    assert "btg     input_split_flags_b1, INPUT_SPLIT_FLAG_SYNC_TARGET, BANKED" in body


def test_legacy_broadcast_input_sender_atomic_expectations_are_unchanged() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8")
    legacy = _body(text, "input_frame_send", "input_frame_send_aborted")
    assert "INPUT_SPLIT_FLAG_PB2_LINKED" in legacy
    assert re.search(r"rcall\s+tx_ring_reserve_3", legacy)
    assert legacy.index("tx_ring_reserve_3") < legacy.index("tx_byte_enqueue")
    assert len(re.findall(r"call\s+tx_byte_enqueue", legacy)) == 3


def test_current_input_page_linked_pb2_uses_broadcast_not_addressed() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8")
    body = _body(text, "input_frame_send_current_input_page", "input_frame_send_targeted")
    assert "movlw   0x03" in body
    assert "INPUT_SPLIT_FLAG_PB2_LINKED" in body
    assert re.search(
        r"btfsc\s+input_split_flags_b1,\s+INPUT_SPLIT_FLAG_PB2_LINKED,\s+BANKED\s*\n\s*"
        r"goto\s+input_frame_send",
        body,
    )
    assert "goto    input_frame_send_pb2_targeted" in body
