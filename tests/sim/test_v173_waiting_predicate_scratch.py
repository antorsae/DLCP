"""V1.73 WAITING-loop predicate scratch safety regressions."""

from __future__ import annotations

import re
import pytest

from dlcp_fw.paths import V173_CONTROL_ASM


pytestmark = pytest.mark.dual_supported


def test_v173_waiting_four_sentinel_reduce_uses_non_isr_scratch() -> None:
    text = V173_CONTROL_ASM.read_text(encoding="utf-8")
    match = re.search(
        r"v171_waiting_cold_past_grace_done:\n(?P<body>.*?)\npost_connect_init:",
        text,
        re.DOTALL,
    )
    assert match is not None, "cold WAITING post-grace block not found"
    body = match.group("body")
    reduce = body[
        body.index("movlw   0x80"):
        body.index("movlw   0x61")
    ]

    assert "(Common_RAM + 24)" not in reduce
    assert "v171_tx_enq_retry_acc" in reduce
    assert reduce.count("andwf   v171_tx_enq_retry_acc, F, A") == 3
    assert "call    " not in reduce
