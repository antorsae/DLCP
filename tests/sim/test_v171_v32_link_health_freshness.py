"""V1.71/V3.2 link-health freshness MVP tests.

Pins the small cmd 0x23 / BF/2C protocol and the CONTROL-side parser/UI
contracts from docs/V171_V32_LINK_HEALTH_FRESHNESS_SPEC.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM, V32_MAIN_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


pytestmark = pytest.mark.dual_supported

HEALTH_AGE_PB1 = 0x1B0
HEALTH_AGE_PB2 = 0x1B1
HEALTH_SEEN_MASK = 0x1B2
HEALTH_FLAGS = 0x1B3
HEALTH_PENDING = 0
HEALTH_TARGET = 1
HEALTH_DISPLAY_DIRTY = 2
HEALTH_STALE_AGE = 0x03
HEALTH_LOST_AGE = 0x0A

DISPLAY_STATE_INDEX = 0x0BF
STATE_PB1_DIAG = 4
STATE_PB2_DIAG = 5
V171_DIAG_PB1_BASE = 0x180
V171_DIAG_PB2_BASE = 0x18B
V171_DIAG_PRESENT = 0x197

_CONTROL_BUTTON_PINS = {
    "RIGHT": ("A", 4),
    "LEFT": ("C", 5),
}


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_link_health")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _label_body(text: str, start_label: str, end_label: str) -> str:
    start = text.find(f"{start_label}:")
    assert start >= 0, f"{start_label} missing"
    end = text.find(f"{end_label}:", start)
    assert end > start, f"{end_label} missing after {start_label}"
    return text[start:end]


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _step_parser(chain, chunks: int = 50) -> None:  # type: ignore[no-untyped-def]
    for _ in range(chunks):
        chain.step_tcy(1_000)


def _tap_key(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = _CONTROL_BUTTON_PINS[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(5_000_000)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(5_000_000)


def _navigate_to_diag_page(chain, pb_idx: int) -> None:  # type: ignore[no-untyped-def]
    for _ in range(4):
        _tap_key(chain, "RIGHT")
        for _ in range(8):
            chain.step()
    if pb_idx == 1:
        _tap_key(chain, "RIGHT")
        for _ in range(8):
            chain.step()


def _settle_short(chain, chunks: int = 50) -> None:  # type: ignore[no-untyped-def]
    for _ in range(chunks):
        chain.step_tcy(1_000)


def test_v32_cmd23_health_dispatch_and_reply_shape() -> None:
    text = V32_MAIN_ASM.read_text(encoding="utf-8")
    cmd22 = re.search(r"goto\s+cmd22_reset_flags_query_handler\s*\n", text)
    assert cmd22, "cmd 0x22 dispatch missing"
    after = text[cmd22.end():cmd22.end() + 300]
    assert re.search(
        r"xorlw\s+0x01[^\n]*\n\s*"
        r"btfsc\s+STATUS,\s*2,\s*ACCESS[^\n]*\n\s*"
        r"goto\s+cmd23_health_query_handler",
        after,
    ), "cmd 0x23 dispatch must immediately follow cmd 0x22 with xorlw 0x01"

    body = _label_body(text, "cmd23_health_query_handler", "diag_send_burst_xx")
    assert re.search(r"movlw\s+0xBF\b", body)
    assert re.search(r"movlw\s+0x2C\b", body)
    assert re.search(r"movlw\s+0x00\b", body)
    assert len(re.findall(r"rcall\s+uart_tx_byte_blocking", body)) == 3
    assert re.search(r"bcf\s+active_flags,\s*6,\s*ACCESS", body)
    assert "goto        flow_main_uart_service_1be6_1e6c" in body


def test_v171_bf2c_is_exact_parser_case_not_diag_range_extension() -> None:
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    body = _label_body(text, "v171_bf2x_case_check", "flow_rx_parser_entry_05EA")
    assert "v171_health_bf2c_reply" in body
    assert re.search(
        r"movlw\s+0x2C\s*\n\s*cpfseq\s+rx_parsed_cmd,\s*A\s*\n\s*"
        r"bra\s+v171_bf2x_diag_range_check\s*\n\s*"
        r"bra\s+v171_health_bf2c_reply",
        body,
    ), "BF/2C must be exact-special-cased before the diagnostics range gate"
    assert re.search(r"movlw\s+0x2C\s*\n\s*cpfslt\s+rx_parsed_cmd", body), (
        "diagnostics upper-bound gate must remain cmd < 0x2C"
    )


def test_v171_health_sender_is_dedicated_cmd23_sender() -> None:
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    body = _label_body(text, "v171_health_send_query", "v171_health_patch_suffix")
    assert "v171_diag_send_query_w" not in body
    assert re.search(r"call\s+tx_ring_reserve_3", body)
    assert re.search(r"movlw\s+0xB1", body)
    assert re.search(r"movlw\s+0xB2", body)
    assert re.search(r"movlw\s+0x23", body)
    assert len(re.findall(r"call\s+tx_byte_enqueue", body)) == 3


def test_v171_suffix_and_diag_stale_literals_are_present() -> None:
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    suffix = _label_body(text, "v171_health_patch_suffix", "v171_health_diag_check_stale")
    for literal in ("'!'", "'1'", "'2'"):
        assert literal in suffix
    assert "display_state_index" in suffix
    assert re.search(r"movlw\s+0xCC", suffix), "suffix must patch row-2 tail"

    diag = _label_body(text, "v171_diag_render_stale_or_lost", "v171_diag_render_absent")
    for literal in ("'o'", "'l'", "'d'", "'s'", "'t'"):
        assert literal in diag
    assert "v171_diag_lcd_pad_count" in diag


@pytest.mark.slow
def test_bf2c_expected_reply_resets_pending_target_age(v171_hex: Path) -> None:
    _require_rust()
    chain = RustChain.from_v171_v32(control_hex_path=str(v171_hex))
    chain.warmup(25_000_000)
    chain.set_blackout(True)
    chain.write_reg(HEALTH_AGE_PB1, 5)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_PENDING)  # pending PB1
    chain.inject_triplet(0xBF, 0x2C, 0x00)
    _step_parser(chain)
    assert chain.read_reg(HEALTH_AGE_PB1) == 0
    assert chain.read_reg(HEALTH_SEEN_MASK) & 0x01
    # The parser clears the original pending bit; the foreground service may
    # immediately queue the next low-priority health ping in the same settle
    # window, so the stable contract is the accepted fresh proof.


@pytest.mark.slow
def test_bf2c_unsolicited_reply_does_not_mark_fresh(v171_hex: Path) -> None:
    _require_rust()
    chain = RustChain.from_v171_v32(control_hex_path=str(v171_hex))
    chain.warmup(25_000_000)
    chain.set_blackout(True)
    chain.write_reg(HEALTH_AGE_PB2, 7)
    chain.write_reg(HEALTH_SEEN_MASK, 0)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_TARGET)  # target PB2, but not pending
    chain.inject_triplet(0xBF, 0x2C, 0x00)
    _step_parser(chain)
    assert chain.read_reg(HEALTH_AGE_PB2) == 7
    assert not (chain.read_reg(HEALTH_SEEN_MASK) & 0x02)


@pytest.mark.slow
@pytest.mark.parametrize(
    "age_pb1,age_pb2,expected_row2",
    [
        (0, 0, "Auto Detect     "),
        (HEALTH_STALE_AGE, 0, "Auto Detect   !1"),
        (0, HEALTH_STALE_AGE, "Auto Detect   !2"),
        (HEALTH_STALE_AGE, HEALTH_STALE_AGE, "Auto Detect !1 2"),
    ],
)
def test_main_screen_health_suffix_exact_16_char_rendering(
    v171_hex: Path, age_pb1: int, age_pb2: int, expected_row2: str
) -> None:
    _require_rust()
    chain = RustChain.from_v171_v32(control_hex_path=str(v171_hex))
    chain.run_until_connected(limit=200)
    assert chain.lcd_lines()[0].startswith("Volume:"), chain.lcd_lines()
    chain.set_blackout(True)

    chain.write_reg(HEALTH_AGE_PB1, age_pb1)
    chain.write_reg(HEALTH_AGE_PB2, age_pb2)
    chain.write_reg(HEALTH_SEEN_MASK, 0x03)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _settle_short(chain)

    assert chain.lcd_lines()[1] == expected_row2


@pytest.mark.slow
def test_main_screen_link_failure_suffix_surfaces_and_recovers(v171_hex: Path) -> None:
    _require_rust()
    chain = RustChain.from_v171_v32(control_hex_path=str(v171_hex))
    chain.run_until_connected(limit=200)
    chain.step_ticks(50_000_000)
    assert chain.lcd_lines()[1] == "Auto Detect     "

    chain.set_link_fault("m0_to_m1", drop=True)
    for _ in range(3):
        chain.step_ticks(48_000_000)

    assert chain.is_connected() and not chain.is_waiting()
    assert chain.lcd_lines()[1] == "Auto Detect !1 2"

    chain.set_link_fault("m0_to_m1", drop=False)
    for _ in range(2):
        chain.step_ticks(48_000_000)

    assert chain.is_connected() and not chain.is_waiting()
    assert chain.lcd_lines()[1] == "Auto Detect     "


@pytest.mark.slow
@pytest.mark.parametrize(
    "pb_idx,state,age_addr,diag_base,present_bit,pb_label",
    [
        (0, STATE_PB1_DIAG, HEALTH_AGE_PB1, V171_DIAG_PB1_BASE, 0x01, "PB1"),
        (1, STATE_PB2_DIAG, HEALTH_AGE_PB2, V171_DIAG_PB2_BASE, 0x02, "PB2"),
    ],
)
def test_diag_stale_lost_and_recovery_do_not_render_stale_ok(
    v171_hex: Path,
    pb_idx: int,
    state: int,
    age_addr: int,
    diag_base: int,
    present_bit: int,
    pb_label: str,
) -> None:
    _require_rust()
    chain = RustChain.from_v171_v32(control_hex_path=str(v171_hex))
    chain.run_until_connected(limit=200)
    _navigate_to_diag_page(chain, pb_idx)
    assert chain.read_reg(DISPLAY_STATE_INDEX) == state
    assert chain.lcd_lines()[0].startswith(pb_label), chain.lcd_lines()

    chain.set_blackout(True)
    for i in range(11):
        chain.write_reg(diag_base + i, 0)
    chain.write_reg(V171_DIAG_PRESENT, present_bit)
    chain.write_reg(HEALTH_SEEN_MASK, present_bit)

    chain.write_reg(age_addr, HEALTH_STALE_AGE)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _settle_short(chain, chunks=10)
    assert chain.lcd_lines()[0].startswith(f"{pb_label} old"), chain.lcd_lines()
    assert "OK" not in chain.lcd_lines()[1]

    chain.write_reg(age_addr, HEALTH_LOST_AGE)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _settle_short(chain, chunks=50)
    assert chain.lcd_lines()[0].startswith(f"{pb_label} lost"), chain.lcd_lines()
    assert "OK" not in chain.lcd_lines()[1]

    chain.write_reg(age_addr, 0)
    chain.write_reg(HEALTH_FLAGS, 1 << HEALTH_DISPLAY_DIRTY)
    _settle_short(chain, chunks=50)
    assert chain.lcd_lines()[0] == f"{pb_label}             "
    assert chain.lcd_lines()[1] == "OK              "
