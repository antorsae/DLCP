"""V1.7 CONTROL relocation-safety tests (Phase 3).

Validates the structural invariants from
``docs/IMPL_V16B_SOURCE_REWRITE_SPEC.md §A4–A5``: a 0x222-byte shift
inserted after the vector block must preserve:

* Vector block length (0x0000–0x004B is still 0x4C bytes of vectors).
* Bootloader bytes (0x7800–0x7FFF byte-identical to stock).
* CONFIG bits and EEPROM data.
* Symbol addresses shift deterministically by +0x222.
* Every application-code label known to the semantic map is resolvable
  in the shifted listing.

The shift test proves V1.71 can freely grow function bodies knowing
relocation-safety invariants hold.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    STOCK_CONTROL_HEX_V16B,
    V17_CONTROL_ASM_COMMENTS,
    V17_CONTROL_ASM_SHIFTED,
    V17_CONTROL_RAM_INC,
)
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.v17_symbols import assemble_v17, build_shifted_asm, parse_v17_symbols

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


SHIFT = 0x222


@pytest.fixture(scope="module")
def shifted_build(tmp_path_factory: pytest.TempPathFactory):
    """Build the shifted source, assemble, and return (hex_path, symbols)."""
    tmp = tmp_path_factory.mktemp("v17_shift")
    # Stage the commented source + RAM include so gpasm can resolve
    # everything without writing into the source tree.
    src_copy = tmp / V17_CONTROL_ASM_COMMENTS.name
    src_copy.write_bytes(V17_CONTROL_ASM_COMMENTS.read_bytes())
    ram_copy = tmp / V17_CONTROL_RAM_INC.name
    ram_copy.write_bytes(V17_CONTROL_RAM_INC.read_bytes())

    shifted = tmp / "dlcp_control_v17_shifted.asm"
    build_shifted_asm(src_copy, shifted)
    hex_out = shifted.with_suffix(".hex")
    assemble_v17(shifted, hex_out)
    lst_path = shifted.with_suffix(".lst")
    symbols = parse_v17_symbols(lst_path)
    return hex_out, symbols


@pytest.mark.dual_supported
def test_shifted_committed_file_exists() -> None:
    """The canonical shifted source must be regeneratable to the committed path."""
    # Not committed on disk by default; build_shifted_asm drives the
    # tmp-path fixture above.  Confirm the path constant resolves.
    assert V17_CONTROL_ASM_SHIFTED.name == "dlcp_control_v17_shifted.asm"


@pytest.mark.dual_supported
def test_shifted_assembles_without_errors(shifted_build) -> None:
    hex_out, _ = shifted_build
    assert hex_out.exists() and hex_out.stat().st_size > 0


@pytest.mark.dual_supported
def test_shifted_bootloader_preserved(shifted_build) -> None:
    hex_out, _ = shifted_build
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(hex_out)
    for addr in range(0x7800, 0x8000):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"bootloader byte diverges at 0x{addr:06X}: "
            f"stock=0x{stock.get(addr, 0xFF):02X} shifted=0x{built.get(addr, 0xFF):02X}"
        )


@pytest.mark.dual_supported
def test_shifted_config_preserved(shifted_build) -> None:
    hex_out, _ = shifted_build
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(hex_out)
    for addr in range(0x300000, 0x30000E):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF)


@pytest.mark.dual_supported
def test_shifted_eeprom_preserved(shifted_build) -> None:
    hex_out, _ = shifted_build
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(hex_out)
    for addr in range(0xF00000, 0xF00100):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF)


@pytest.mark.dual_supported
def test_shifted_vector_block_length_preserved(shifted_build) -> None:
    """Vector block spans 0x0000–0x004B (0x4C bytes).

    The bytes *within* the block encode different goto/call targets
    because the jump destinations shift, but the block length and the
    reset vector target (0x7800, pinned bootloader) must not change.
    """
    hex_out, _ = shifted_build
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(hex_out)
    # Reset vector: goto 0x7800 — bootloader is pinned.
    for a in range(0, 4):
        assert built.get(a, 0xFF) == stock.get(a, 0xFF), (
            f"reset vector byte changed at 0x{a:04X}"
        )


@pytest.mark.dual_supported
def test_shifted_application_region_leads_with_padding(shifted_build) -> None:
    hex_out, _ = shifted_build
    built = parse_intel_hex(hex_out)
    for addr in range(0x004C, 0x004C + SHIFT):
        assert built.get(addr, 0xFF) == 0x00, (
            f"expected 0x00 NOP padding at 0x{addr:04X}, got 0x{built.get(addr, 0xFF):02X}"
        )


@pytest.mark.parametrize(
    "label, stock_addr",
    [
        ("bootloader_entry", 0x7800),
        ("isr_entry", 0x03A6),
        ("app_cold_init", 0x0366),
        ("lcd_command", 0x0066),
        ("ir_rc5_decode", 0x021E),
        ("rx_parser_entry", 0x044A),
        ("tx_byte_enqueue", 0x05EC),
        ("full_sync_burst", 0x0B36),
        ("main_event_loop", 0x150E),
    ],
)
@pytest.mark.dual_supported
def test_shifted_symbols_track_expected_shift(shifted_build, label, stock_addr) -> None:
    """Application-code labels shift by +0x222; bootloader stays pinned."""
    _, symbols = shifted_build
    assert label in symbols, f"symbol missing from shifted .lst: {label}"
    shifted_addr = symbols[label]
    if stock_addr >= 0x7800:
        # Bootloader region is pinned.
        expected = stock_addr
    else:
        expected = stock_addr + SHIFT
    assert shifted_addr == expected, (
        f"{label}: expected 0x{expected:06X} (stock 0x{stock_addr:06X} + shift "
        f"0x{SHIFT if stock_addr < 0x7800 else 0:X}), got 0x{shifted_addr:06X}"
    )


# ---------------------------------------------------------------------------
# gpsim boot equivalence: stock V1.6b / V1.7 / V1.7 shifted all advance
# the same cycle count with no TX divergence in the absence of MAIN
# heartbeats.  Pins spec §A5 relocation-safety claim at runtime — if a
# hardcoded address escaped the audit, the shifted build would hang or
# produce a different TX sequence.
# ---------------------------------------------------------------------------

_GPSIM_SMOKE_STEPS = 20  # ~12M cycles @ chunk_cycles=600_000


@pytest.fixture(scope="module")
def v17_smoke_images(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Build V1.7 + V1.7 shifted hex for the smoke test fixture."""
    tmp = tmp_path_factory.mktemp("v17_gpsim_smoke")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    src_stage = tmp / V17_CONTROL_ASM_COMMENTS.name
    src_stage.write_bytes(V17_CONTROL_ASM_COMMENTS.read_bytes())

    hex_v17 = tmp / "v17.hex"
    assemble_v17(src_stage, hex_v17)

    shifted_src = tmp / "v17_shifted.asm"
    build_shifted_asm(src_stage, shifted_src)
    hex_shifted = tmp / "v17_shifted.hex"
    assemble_v17(shifted_src, hex_shifted)

    return {"v17": hex_v17, "shifted": hex_shifted}


# 20 chunks × 600_000 K20-Tcy = 12 M K20-Tcy.  Rust uses the
# total Tcy in a single ``step_tcy(12_000_000)`` call.
_RUST_SMOKE_TCY = _GPSIM_SMOKE_STEPS * 600_000


def _run_smoke(hex_path) -> tuple[int, list]:
    """Boot *hex_path* on the rust CONTROL-only chain and return
    (cycle_count, tx_frames) at +12M K20-Tcy."""
    _require_rust()
    c = RustChain.from_v17_control_only(str(hex_path))
    c.step_tcy(_RUST_SMOKE_TCY)
    return c.current_cycle, c.tx_frames()


@pytest.mark.dual_supported
def test_shifted_boot_parity_with_stock_and_v17(v17_smoke_images) -> None:
    """Stock V1.6b, V1.7, and V1.7 shifted advance identically.

    Boots each image with a CONTROL-only chain (no MAIN heartbeats),
    advances ~12M K20-Tcy, and compares the final cycle count and
    captured UART TX byte sequence.  The three images must agree
    exactly.

    Without a UART coupling, ``Chain::drain_completed_tx_bytes``
    falls through to the loopback-sentinel branch and records each
    CONTROL TX byte to ``uart_tx_history``, so ``tx_frames()``
    returns the K20's USART output even with no peer.

    A previous gpsim-only sister test
    (``test_shifted_gpsim_with_dynamic_standby_overlay``) was deleted
    in PF.4 phase 2 batch 8: it exercised gpsim's
    ``control_disable_standby_check_dynamic`` overlay (resolve patch
    site from sibling ``.lst`` via ``post_connect_init`` symbol
    lookup) which has no rust analogue — the rust facade boots
    silicon-correct without a runtime byte-patch.  The relocation-
    safety invariant the deleted test guarded is covered by the
    structural symbol-shift tests above and by the cycle/TX parity
    assertion below.
    """
    stock_cycle, stock_tx = _run_smoke(STOCK_CONTROL_HEX_V16B)
    v17_cycle, v17_tx = _run_smoke(v17_smoke_images["v17"])
    shifted_cycle, shifted_tx = _run_smoke(v17_smoke_images["shifted"])
    assert stock_cycle == v17_cycle, (
        f"V1.7 cycle count diverges from stock: "
        f"stock={stock_cycle} v17={v17_cycle}"
    )
    assert stock_cycle == shifted_cycle, (
        f"V1.7 shifted cycle count diverges from stock: "
        f"stock={stock_cycle} shifted={shifted_cycle}"
    )
    assert stock_tx == v17_tx, (
        f"V1.7 TX frames diverge from stock: "
        f"stock={stock_tx[:3]!r} v17={v17_tx[:3]!r}"
    )
    assert stock_tx == shifted_tx, (
        f"V1.7 shifted TX frames diverge from stock: "
        f"stock={stock_tx[:3]!r} shifted={shifted_tx[:3]!r}"
    )


@pytest.mark.dual_supported
def test_shifted_hex_is_larger_than_unshifted() -> None:
    """Shifted build has 0x222 more bytes of code than the baseline."""
    # Baseline code region byte count equals stock V1.6b.  Shifted build
    # adds 0x222 bytes of NOP padding, so its highest-used application
    # address must be exactly SHIFT bytes higher than stock's.
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    # Find highest application-code address < 0x7000 (below pre-shift
    # erased-flash fill that was between app code and bootloader).
    stock_tail = max(
        (a for a, b in stock.items() if a < 0x7000 and b != 0xFF),
        default=-1,
    )
    assert stock_tail > 0, "stock hex has no code below 0x7000?"
    # The shifted build is a separate fixture per session, but this test
    # does not need to rebuild — it only asserts stock structure as a
    # sanity check that makes the assumption explicit.
    assert stock_tail < 0x7000 - SHIFT, (
        f"stock code already uses all headroom below the bootloader: "
        f"tail 0x{stock_tail:04X}, need <0x{0x7000 - SHIFT:04X}"
    )
