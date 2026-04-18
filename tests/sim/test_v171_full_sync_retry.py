"""V1.71 Phase B.5: full-sync preset retry counter behavior.

Spec §Feature inventory row on "Full-sync burst":

    Preset change enqueues 3 retries of the preset-switch frame
    [B0, 0x20, preset_byte] sent to MAIN on each full-sync cycle.

Verifiable observables from the standalone CONTROL harness:

* After boot with PRESET_BIT = 1, the initial full-sync rounds emit
  the preset frame at least twice (counter arms at 3 on connect
  edge, decrements once per full-sync until it reaches zero).
* Source check: the retry-counter block + bank-1 0x70/0x71 RAM
  references live at the head of ``full_sync_burst`` — guards
  against a rebase accidentally dropping the retry feature.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM
from dlcp_fw.sim.gpsim import gpsim_available

try:
    from dlcp_fw.sim.control_gpsim import GpsimControlHarness
    from dlcp_fw.sim.v17_symbols import assemble_v17
    _IMPORT_OK = True
except Exception:  # pragma: no cover
    _IMPORT_OK = False


CONTROL_FLAGS_ADDR = 0x01F
PRESET_BIT = 6
PRESET_FRAME_A = (0xB0, 0x20, 0x00)
PRESET_FRAME_B = (0xB0, 0x20, 0x01)


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    if not _IMPORT_OK:
        pytest.skip("control_gpsim harness not importable")


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_fs_retry")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _boot(hex_path: Path) -> GpsimControlHarness:
    return GpsimControlHarness(
        hex_path,
        fast_boot=False,
        chunk_cycles=600_000,
        heartbeat_rx_mode="full",
    )


# ---------------------------------------------------------------------------
# Source-level guards (stable regardless of gpsim timing)
# ---------------------------------------------------------------------------

def test_v171_source_hosts_preset_retry_counter_at_full_sync_entry() -> None:
    """Retry counter block must live at the head of full_sync_burst."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("full_sync_burst:")
    assert start >= 0, "full_sync_burst label missing"
    # The inline retry block anchors a stable comment.
    retry_block = text[start:start + 4000]
    for marker in (
        "V1.71 inline (V1.61b): preset-frame retry counter",
        "v171_fs_connected",
        "v171_fs_send_check",
        "v171_fs_continue",
        "0x71, BANKED",  # primed flag
        "0x70, BANKED",  # retry counter
    ):
        assert marker in retry_block, (
            f"retry-counter marker missing from full_sync_burst: {marker!r}"
        )


def test_v171_source_uses_v171_send_preset_helper_from_full_sync() -> None:
    """The retry block must reuse the shared v171_send_preset_frame_and_persist."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    start = text.find("full_sync_burst:")
    retry_block = text[start:start + 4000]
    assert "v171_send_preset_frame_and_persist" in retry_block, (
        "full-sync retry must reuse v171_send_preset_frame_and_persist"
    )


# ---------------------------------------------------------------------------
# Behavioral: preset frame appears in TX during the first full-sync cycles
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_full_sync_emits_preset_frame_after_connect(v171_hex: Path) -> None:
    """After warmup (CONNECTED + primed), the TX stream contains at least
    one [B0, 0x20, preset_byte] frame from the full-sync retry path.

    The initial value of PRESET_BIT is determined by EEPROM 0x74
    (defaults to 0 = preset A for erased EEPROM).  We accept either
    preset frame — the retry counter fires regardless.
    """
    _require_gpsim()
    h = _boot(v171_hex)
    try:
        h.warmup(25_000_000)
        # Allow a couple of full-sync periods to elapse.
        for _ in range(80):
            h.step()
        tx = {(f.route, f.cmd, f.data) for f in h.tx_frames()}
        assert PRESET_FRAME_A in tx or PRESET_FRAME_B in tx, (
            f"no preset-select frame in TX after warmup; got {sorted(tx)}"
        )
    finally:
        h.close()
