"""V1.71 Phase B.5 → superseded by Layer 2: preset is now value-bearing.

Originally guarded the V1.61b 3-retry preset-frame counter at the
head of ``full_sync_burst``.  V1.71 Layer 2 (BUG C7 fix) removes the
retry counter machinery entirely and makes preset value-bearing in
the periodic broadcast — emitted on step 6 of the new one-frame-per-
call dispatch alongside volume / input / mute / cmd1d / standby.

The structural retry-counter assertions that used to live here are
gone (Layer 2 explicitly removes the V1.61b 0x70/0x71 retry block).
Their inverse — "the retry block is GONE" and "Layer 2 emits preset
without the V1.61b primed handshake" — lives in
``test_v171_layer2_full_sync_step.py``.

Only one behavioral assertion remains here: the TX stream contains
at least one preset frame after a few full-sync periods.  This is
intentionally a duplicate of the Layer 2 file's stronger assertion,
kept here as a smoke-level guard so a Phase-A-style regression catches
any future rebase that breaks the periodic preset emission.
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
PRESET_BIT = 6
PRESET_FRAME_A = (0xB0, 0x20, 0x00)
PRESET_FRAME_B = (0xB0, 0x20, 0x01)


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_fs_retry")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


# ---------------------------------------------------------------------------
# Behavioral: preset frame appears in TX during the periodic full-sync cycle
# ---------------------------------------------------------------------------

def _run_full_sync_preset_check(h) -> None:  # type: ignore[no-untyped-def]
    h.warmup(80_000_000)
    for _ in range(160):
        h.step()
    tx: set[tuple[int, int, int]] = set()
    for f in h.tx_frames():
        if isinstance(f, tuple):
            tx.add(f)
        else:
            tx.add((f.route, f.cmd, f.data))
    assert PRESET_FRAME_A in tx or PRESET_FRAME_B in tx, (
        f"no preset-select frame in TX after warmup; got {sorted(tx)}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_full_sync_emits_preset_frame_after_connect(
    v171_hex: Path,
) -> None:
    """After warmup the TX stream contains at least one preset frame.

    Under Layer 2, preset is value-bearing in the periodic full-sync:
    every 6th trigger of ``full_sync_burst`` lands on step 6 and
    emits ``[B0, 0x20, preset_byte]`` via
    ``v171_send_preset_frame_txonly``.  The initial preset bit is
    determined by EEPROM 0x74 (defaults to 0 = preset A for erased
    EEPROM); either frame value is acceptable here.

    Warmup is generous (≥80M cycles) to make sure step 6 has cycled
    around at least once even if the trigger period varies.
    """
    _require_rust()
    chain = RustChain.from_v17_chain(str(v171_hex))
    _run_full_sync_preset_check(chain)
