"""V1.71 Phase C.3: sentinel-driven reconnect loop behavior.

Spec §Feature inventory rows on "Reconnect handshake state" and
"Full-sync retry on missing echo":

    V1.62b reconnect_wait_body polls 4 boot sentinels
    (input_select_cache 0x0B8, volume_cache 0x0B9,
    cmd1d_setting_cache 0x0A7, raw_status_cache 0x0A1) each
    initialised to 0x80 and clearing when MAIN replies with the
    corresponding BF frame.  When all four are non-0x80, exit;
    otherwise increment the per-cycle counter in bank-1 0x73,
    retry with a full UART soft-recover every 8 iterations.

Verifiable from the standalone harness:

* Source-level structure checks on the sentinel loop.
* Loop exits when harness heartbeat fills the sentinels.
* With heartbeat paused, the firmware stays in / returns to the
  loop (does not hang, does not crash) — at minimum, the parser
  cycle count keeps advancing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


CONTROL_FLAGS_ADDR = 0x01F
CONNECTED_BIT = 1
INPUT_SELECT_CACHE_ADDR = 0x0B8
VOLUME_CACHE_ADDR = 0x0B9
CMD1D_SETTING_CACHE_ADDR = 0x0A7
RAW_STATUS_CACHE_ADDR = 0x0A1


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_sentinel")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


# ---------------------------------------------------------------------------
# Source-level guards
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
def test_v171_source_replaces_reconnect_loop_with_sentinel_body() -> None:
    """reconnect_wait_loop body must contain the sentinel-check block."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("reconnect_wait_loop:")
    assert start >= 0, "reconnect_wait_loop label missing"
    end = text.find("v171_reconnect_wait_done:", start)
    assert end > start, "v171_reconnect_wait_done marker missing"
    loop_body = text[start:end]
    required = [
        "V1.71 inline (V1.62b): full sentinel-driven reconnect loop",
        "v171_reconnect_wait_body",
        "v171_reconnect_wait_done",
        "input_select_cache",
        "volume_cache",
        "cmd1d_setting_cache",
        "raw_status_cache",
        "0x73, BANKED",                      # per-cycle retry counter
        "0x08",                              # 8-iteration retry threshold
    ]
    missing = [m for m in required if m not in loop_body]
    assert not missing, f"sentinel loop markers missing: {missing}"
    for marker in (
        "subwf   input_select_cache, W, B",
        "subwf   volume_cache, W, B",
        "subwf   cmd1d_setting_cache, W, B",
        "subwf   raw_status_cache, W, B",
        "call    rx_parser_entry, 0x0",
        # `v171_service_rx_frame_gap` sits right after `rx_parser_entry`
        # and performs the parser-stall watchdog PLUS a `movlb 0x00`
        # entry (which also doubles as the post-`rx_parser_entry` BSR
        # reset the sentinel compares rely on).  Its presence here is
        # required both for liveness (V32_MAIN_HANG_HARDENING_PLAN §2)
        # and to guarantee BSR=0 for the subsequent BANKED compares.
        "call    v171_service_rx_frame_gap, 0x0",
    ):
        assert marker in loop_body, (
            f"sentinel loop must compare cached reconnect sentinels in BANKED mode: {marker!r}"
        )


@pytest.mark.dual_supported
def test_v171_source_embeds_uart_soft_recover_in_sentinel_loop() -> None:
    """Every 8 iterations, the sentinel loop runs a UART soft-recover."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("reconnect_wait_loop:")
    end = text.find("v171_reconnect_wait_done:", start)
    assert start >= 0 and end > start
    loop_body = text[start:end]
    # The 8-retry path does the same soft-recover as the parser head
    # (RCSTA CREN toggle + RCREG double-drain + ring / state reset).
    for marker in (
        "bcf     RCSTA, CREN, A",
        "bsf     RCSTA, CREN, A",
        "movf    RCREG, W, A",
        "clrf    tx_ring_rd, BANKED",
        "clrf    rx_ring_rd, BANKED",
        "clrf    rx_frame_position, BANKED",
    ):
        assert marker in loop_body, (
            f"sentinel loop missing UART soft-recover step: {marker!r}"
        )


@pytest.mark.dual_supported
def test_v171_cold_wait_restores_bsr_before_sentinel_compares() -> None:
    """The cold WAITING loop must read the real sentinel cache bank after parser.

    BSR must be 0 for the BANKED sentinel compares that follow
    `rx_parser_entry`.  Require the `v171_service_rx_frame_gap`
    helper call — it's the post-hardening BSR-reset-cum-watchdog for
    this loop, and its first instruction is `movlb 0x00`.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("flow_ccs_0FA0_118C:")
    end = text.find("post_connect_init", start)
    assert start >= 0 and end > start
    wait_body = text[start:end]
    assert "call    rx_parser_entry, 0x0" in wait_body
    assert "call    v171_service_rx_frame_gap, 0x0" in wait_body, (
        "cold WAITING loop must call v171_service_rx_frame_gap after "
        "rx_parser_entry (parser-stall watchdog + BSR reset for "
        "BANKED sentinel compares)"
    )


# NOTE: not @pytest.mark.dual_supported -- this test is a
# pre-existing failure on main (the V1.71 source's
# `v171_reconnect_wait_done` block doesn't yet have a marker
# substring `RECONNECT_WAIT_DONE`).  Once the source rewrite
# adds the marker, this test goes dual_supported.
def test_v171_source_emits_wake_and_reseeds_idle_timer_on_loop_exit() -> None:
    """Exit path: wake frame + reload idle timer to 0xEA61 + zero full-sync."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("v171_reconnect_wait_done:")
    end = text.find("post_connect_init", start)
    assert start >= 0 and end > start
    exit_body = text[start:end]
    for marker in (
        "standby_wake_broadcast",
        "idle_timeout_lo",
        "idle_timeout_hi",
        "full_sync_lo",
        "full_sync_hi",
        "0x61",                              # idle timer low init
        "0xEA",                              # idle timer high init
        "RECONNECT_WAIT_DONE",
    ):
        assert marker in exit_body, (
            f"reconnect exit path missing marker: {marker!r}"
        )


# ---------------------------------------------------------------------------
# Behavioral: boot proceeds past reconnect loop when heartbeat is on
# ---------------------------------------------------------------------------

def _run_sentinel_loop_exit_check(h) -> None:  # type: ignore[no-untyped-def]
    h.warmup(25_000_000)
    flags = h.read_reg(CONTROL_FLAGS_ADDR)
    assert flags & (1 << CONNECTED_BIT), (
        f"CONTROL did not reach CONNECTED; sentinel loop may be stuck "
        f"(flags=0x{flags:02X})"
    )
    for name, addr in (
        ("input_select_cache", INPUT_SELECT_CACHE_ADDR),
        ("volume_cache", VOLUME_CACHE_ADDR),
        ("cmd1d_setting_cache", CMD1D_SETTING_CACHE_ADDR),
        ("raw_status_cache", RAW_STATUS_CACHE_ADDR),
    ):
        value = h.read_reg(addr)
        assert value != 0x80, (
            f"sentinel {name} still 0x80 after warmup; got 0x{value:02X}"
        )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_sentinel_loop_exits_when_heartbeat_fills_sentinels(
    v171_hex: Path
) -> None:
    """After warmup, all 4 sentinels are non-0x80 and CONNECTED is set.

    The rust 3-core ring's V2.3-combined MAIN injects
    BF/06, BF/07, BF/1D, BF/03 periodically.  Each frame's parser
    dispatch writes its respective sentinel slot (non-0x80 values
    from the stored volume / input / cmd1d / raw status).  Once
    all four clear, the V1.71 sentinel loop exits, emits the wake
    frame, and sets CONNECTED.  Warmup of 25M cycles is 8+
    heartbeat rounds — plenty.
    """
    _require_rust()
    chain = RustChain.from_v17_chain(str(v171_hex))
    _run_sentinel_loop_exit_check(chain)
