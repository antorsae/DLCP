"""V3.4 SRC/DSP forensic diag counters (N/L/C/T/M) — stage 1 (USB-only).

Five BANK 3 upper RAM counters make the SRC/route/mute/apply domain visible
after the 2026-06-12 live incident (spontaneous filter change + ~1 s
one-sided dropout under Auto Detect) left zero trace in the legacy
I/D/S/B/R/A/P set:

  N 0x3C0  non-PCM mute episodes (active_flags.4 0->1 edges via SRC monitor)
  L 0x3C1  Auto-Detect loss-debounce confirmed source losses
  C 0x3C2  SRC route changes applied (route request != shadow)
  T 0x3C3  preset table walks (cold/wake/reconnect apply + async job COMMIT)
  M 0x3C4  DSP mute writes (clrf_i2c_coeff_0123_and_write entries)

Visibility is the extended USB HID cmd 0x44 payload: length byte 0x10 with
the five cells appended AFTER the legacy reset flags so legacy offsets are
stable.  Chain burst / CONTROL LCD surfacing is deferred to the V1.74 stage.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from dlcp_fw.flash.dlcp_diag import (  # noqa: E402
    CMD44_LENGTH_BYTE_V34,
    _format_src_line,
    parse_cmd44_diag_response,
)
from dlcp_fw.paths import V173_CONTROL_HEX, V34_MAIN_HEX  # noqa: E402
from dlcp_fw.sim.dlcp_sim_native import Chain  # noqa: E402

DIAG_SRC_N = 0x3C0
DIAG_SRC_L = 0x3C1
DIAG_SRC_C = 0x3C2
DIAG_SRC_T = 0x3C3
DIAG_SRC_M = 0x3C4

SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13

IR_ADDR = 0x10
IR_PRESET_A = 0x38
IR_PRESET_B = 0x39

ONE_S = 48_000_000


@pytest.fixture(scope="module")
def settled_chain():
    """One booted V1.73 + 2x V3.4 chain with a steady detected source.

    Module-scoped: each test below stimulates and asserts COUNTER DELTAS so
    they compose on one boot (boot costs ~half the runtime of this file).
    Order-sensitive absolute assertions live in test_boot_baseline only,
    which runs first by definition order and asserts pre-stimulus state.
    """
    chain = Chain.from_v171_v32(
        control_hex_path=str(V173_CONTROL_HEX), main_hex_path=str(V34_MAIN_HEX)
    )
    chain.run_until_connected(limit=240)
    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.step_ticks(4 * ONE_S)
    return chain


def _cells(chain, unit: int = 0) -> dict[str, int]:
    return {
        "N": chain.read_main_reg(unit, DIAG_SRC_N),
        "L": chain.read_main_reg(unit, DIAG_SRC_L),
        "C": chain.read_main_reg(unit, DIAG_SRC_C),
        "T": chain.read_main_reg(unit, DIAG_SRC_T),
        "M": chain.read_main_reg(unit, DIAG_SRC_M),
    }


def test_boot_baseline_counts_cold_walk_and_first_route(settled_chain) -> None:
    """Cold init must CLEAR the bank-3 cells (wipe-protected RAM is the only
    region the broad wipes skip), then the boot itself contributes the
    deterministic baseline: exactly one full preset-table walk (T) and at
    least one applied route change once Auto Detect locks the source (C).
    No non-PCM episode and no confirmed loss may be counted on a clean boot.
    """
    cells = _cells(settled_chain)
    assert cells["N"] == 0, cells
    assert cells["L"] == 0, cells
    assert cells["T"] == 1, cells
    assert 1 <= cells["C"] <= 0x0F, cells


def test_nonpcm_blip_counts_episodes_not_passes(settled_chain) -> None:
    """N counts mute EPISODES: the SRC monitor polls reg 0x12 continuously,
    so a sustained non-PCM condition must increment N exactly once (the
    active_flags.4 0->1 edge), and a second blip after the clean-PCM
    auto-unmute must count exactly once more.  M (DSP mute writes) must
    advance with the first mute write of each episode.
    """
    chain = settled_chain
    before = _cells(chain)

    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x01)
    chain.step_ticks(ONE_S)
    mid = _cells(chain)
    assert mid["N"] == before["N"] + 1, (before, mid)
    assert mid["M"] >= before["M"] + 1, (before, mid)

    # sustained non-PCM: more polls, no new episode
    chain.step_ticks(ONE_S)
    assert _cells(chain)["N"] == before["N"] + 1

    # clean PCM -> auto-unmute, then a second blip = second episode
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.step_ticks(ONE_S)
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x01)
    chain.step_ticks(ONE_S)
    assert _cells(chain)["N"] == before["N"] + 2
    chain.poke_main_src4382_reg(0, SRC_REG_NON_PCM, 0x00)
    chain.step_ticks(ONE_S)


def test_source_loss_and_reacquire_count_l_and_c(settled_chain) -> None:
    """A sustained Auto-Detect source loss confirms (L counts) and applies
    route reconciliations; the re-detect applies a route again.  Bounds are
    >= because the scan-walk re-arms candidate routes during sustained
    absence (each confirmed after the K=6 debounce, rev 0x88).
    """
    chain = settled_chain
    before = _cells(chain)

    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x00)
    chain.step_ticks(6 * ONE_S)          # K=6 loss debounce (rev 0x88): ~3 s to confirm
    lost = _cells(chain)
    assert lost["L"] >= before["L"] + 1, (before, lost)
    assert lost["C"] >= before["C"] + 1, (before, lost)

    chain.poke_main_src4382_reg(0, SRC_REG_RX_STATUS, 0x01)
    chain.step_ticks(4 * ONE_S)
    back = _cells(chain)
    assert back["C"] >= lost["C"] + 1, (lost, back)


def test_preset_switch_counts_walk_and_mute(settled_chain) -> None:
    """Each completed async preset switch is one full table walk (T, exact:
    nothing else walks tables) and at least one forced-mute DSP write (M,
    floor: the counter is shared with detect-machinery mutes, and prior
    tests' trailing detect state may land one during these windows under
    xdist module splits).
    """
    chain = settled_chain
    chain.step_ticks(6 * ONE_S)   # drain any trailing detect-machinery state
    before = _cells(chain)

    chain.inject_decoded_ir_event(addr=IR_ADDR, cmd=IR_PRESET_B)
    chain.step_ticks(4 * ONE_S)
    after_b = _cells(chain)
    assert after_b["T"] == before["T"] + 1, (before, after_b)
    assert after_b["M"] >= before["M"] + 1, (before, after_b)

    chain.inject_decoded_ir_event(addr=IR_ADDR, cmd=IR_PRESET_A)
    chain.step_ticks(4 * ONE_S)
    after_a = _cells(chain)
    assert after_a["T"] == before["T"] + 2, (before, after_a)
    assert after_a["M"] >= before["M"] + 2, (before, after_a)


def test_cmd44_extended_payload_reflects_cells(settled_chain) -> None:
    """The extended cmd 0x44 reply: length byte 0x10, legacy 11 cells at
    their stable offsets, and the five SRC/DSP cells appended at [14..18]
    in N, L, C, T, M order, equal to the live RAM cells.
    """
    chain = settled_chain
    cells = _cells(chain)
    report = [0x44] + [0x00] * 63
    resp, dispatch_hits = chain.firmware_hid_report(0, report)
    assert dispatch_hits >= 1
    assert resp[0] == 0x44 and resp[1] == 0x00
    assert resp[2] == 0x10, f"length byte 0x{resp[2]:02X}"
    assert list(resp[14:19]) == [
        cells["N"], cells["L"], cells["C"], cells["T"], cells["M"]
    ], (list(resp[3:19]), cells)
    # legacy block sanity: reset flags [10..13] still hold exactly one 1
    assert sum(resp[10:14]) == 1, list(resp[10:14])

    snap = parse_cmd44_diag_response(bytes(resp))
    assert snap.src_counters == (
        cells["N"], cells["L"], cells["C"], cells["T"], cells["M"]
    )


def test_counter_saturates_at_0x0f(settled_chain) -> None:
    """The shared diag_inc_sat helper caps the new cells at 0x0F too."""
    chain = settled_chain
    chain.write_main_reg(0, DIAG_SRC_M, 0x0F)
    chain.inject_decoded_ir_event(addr=IR_ADDR, cmd=IR_PRESET_B)
    chain.step_ticks(4 * ONE_S)
    assert chain.read_main_reg(0, DIAG_SRC_M) == 0x0F
    chain.inject_decoded_ir_event(addr=IR_ADDR, cmd=IR_PRESET_A)
    chain.step_ticks(4 * ONE_S)
    assert chain.read_main_reg(0, DIAG_SRC_M) == 0x0F


# ---------------------------------------------------------------------------
# Host-side parser/renderer (pure Python, no sim)
# ---------------------------------------------------------------------------


def _hid_response(length_byte: int, cells: list[int]) -> bytes:
    body = [0x44, 0x00, length_byte] + cells
    return bytes(body + [0xFF] * (64 - len(body)))


def test_host_parses_legacy_11_cell_payload_without_src_counters() -> None:
    snap = parse_cmd44_diag_response(
        _hid_response(0x0B, [0] * 7 + [1, 0, 0, 0])
    )
    assert snap.src_counters is None


def test_host_parses_extended_16_cell_payload() -> None:
    cells = [0, 0, 2, 2, 0, 0, 0] + [1, 0, 0, 0] + [3, 1, 4, 2, 5]
    snap = parse_cmd44_diag_response(_hid_response(CMD44_LENGTH_BYTE_V34, cells))
    assert snap.src_counters == (3, 1, 4, 2, 5)
    assert snap.diag_src_n == 3 and snap.diag_src_m == 5


def test_host_rejects_out_of_range_src_counter() -> None:
    cells = [0] * 7 + [1, 0, 0, 0] + [0x10, 0, 0, 0, 0]
    with pytest.raises(RuntimeError, match="SRC/DSP counter 'N' out of range"):
        parse_cmd44_diag_response(_hid_response(CMD44_LENGTH_BYTE_V34, cells))


def test_host_report_renders_src_line_only_when_present() -> None:
    legacy = parse_cmd44_diag_response(
        _hid_response(0x0B, [0] * 7 + [1, 0, 0, 0])
    )
    extended = parse_cmd44_diag_response(
        _hid_response(CMD44_LENGTH_BYTE_V34,
                      [0] * 7 + [1, 0, 0, 0] + [1, 2, 3, 4, 5])
    )
    assert _format_src_line(legacy) is None
    line = _format_src_line(extended)
    assert line is not None and "N1 L2 C3 T4 M5" in line
