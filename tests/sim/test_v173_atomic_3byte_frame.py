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
    body = _body(text, "input_frame_send_split_sync", "input_frame_send_current_input_page")
    assert "btfss   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_SEEN, BANKED" in body
    assert "bra     input_frame_send_pb1_targeted" in body
    assert "btfsc   input_split_flags_b1, INPUT_SPLIT_FLAG_PB2_LINKED, BANKED" in body
    assert "bra     input_frame_send_split_sync_linked" in body
    assert re.search(
        r"rcall\s+input_frame_send_targeted\s*\n\s*"
        r"bc\s+input_frame_send_split_sync_done",
        body,
    )
    assert body.index("bc      input_frame_send_split_sync_done") < body.index(
        "btg     input_split_flags_b1, INPUT_SPLIT_FLAG_SYNC_TARGET, BANKED"
    )


def test_input_sender_dispatches_only_to_addressed_helpers() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8")
    dispatch = _body(text, "input_frame_send", "input_frame_send_current_input_page")
    assert "INPUT_SPLIT_FLAG_PB2_LINKED" in dispatch
    assert "input_frame_send_pb1_targeted" in dispatch
    assert "input_frame_send_pb2_targeted" in dispatch
    assert "input_frame_send_linked_pair" in dispatch
    assert "tx_byte_enqueue" not in dispatch
    assert "movlw   0xB0" not in dispatch


def test_current_input_page_linked_pb2_uses_addressed_pair_not_broadcast() -> None:
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
    assert "movlw   0xB0" not in body
