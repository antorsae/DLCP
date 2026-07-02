"""V3.5 UART RX ring dequeue must be safe against ISR OERR resync."""

from __future__ import annotations

import re

from dlcp_fw.paths import V35_MAIN_ASM


def _label_body(text: str, label: str, end_labels: list[str]) -> str:
    start = text.index(f"{label}:")
    end = min(text.index(f"{end}:", start) for end in end_labels if f"{end}:" in text[start:])
    return text[start:end]


def test_v35_rx_ring_read_masks_and_restores_prior_gie_around_dequeue() -> None:
    text = V35_MAIN_ASM.read_text(encoding="utf-8")
    body = _label_body(text, "rx_ring_read", ["usb_ep1_configure_hid_buffers"])

    assert "btfss       INTCON, 7, ACCESS" in body
    assert "bcf         INTCON, 7, ACCESS" in body
    assert "bsf         INTCON, 7, ACCESS" in body
    assert re.search(
        r"btfss\s+INTCON,\s*7,\s*ACCESS.*?bcf\s+INTCON,\s*7,\s*ACCESS.*?"
        r"rcall\s+rx_ring_has_data.*?movf\s+rx_ring_rd_b0,\s*W,\s*BANKED.*?"
        r"movf\s+INDF2,\s*W,\s*ACCESS.*?incf\s+rx_ring_rd_b0,\s*F,\s*BANKED",
        body,
        re.S,
    ), body
    assert "bsf         INTCON, 7, ACCESS" not in body[: body.index("bcf         INTCON, 7, ACCESS")]


def test_v35_rx_ring_read_masked_span_is_bounded() -> None:
    text = V35_MAIN_ASM.read_text(encoding="utf-8")
    body = _label_body(text, "rx_ring_read", ["usb_ep1_configure_hid_buffers"])
    start = body.index("bcf         INTCON, 7, ACCESS")
    end = body.index("rx_ring_read__restore_gie", start)
    masked = body[start:end]

    forbidden = [
        "cmd_dispatch",
        "i2c_",
        "uart_tx_byte_blocking",
        "standby_event_dispatch",
        "src4382",
        "tas3108",
    ]
    for token in forbidden:
        assert token not in masked
    instructions = [
        line for line in masked.splitlines()
        if line.strip() and not line.lstrip().startswith(";") and not line.rstrip().endswith(":")
    ]
    assert len(instructions) <= 32, masked
