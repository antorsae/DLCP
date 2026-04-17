"""V1.71 Phase E: V1.64b explicit IR standby / wake endpoints.

Verifies that RC5 0x3A and 0x3B on the menu-configured IR address
emit the canonical ``[0xB0, 0x03, 0x00]`` / ``[0xB0, 0x03, 0x01]``
standby/wake frames over the stock TX pipeline — the V1.64b
explicit-endpoint feature, inlined into the same IR-dispatch body
that Phase B's preset shortcuts live in.
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


PRESET_ADDR = 0x10
STANDBY_FRAME = (0xB0, 0x03, 0x00)
WAKE_FRAME = (0xB0, 0x03, 0x01)


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    if not _IMPORT_OK:
        pytest.skip("control_gpsim harness not importable")


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_ir_endpoints")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _boot(hex_path: Path) -> GpsimControlHarness:
    """Boot with heartbeat disabled post-warmup so TX capture is deterministic.

    The stock full-sync / poll burst emits ``[B0, 03, 01]`` as part of
    its wake status broadcast; if the heartbeat keeps firing those,
    the IR-endpoint parity assertions can't distinguish "IR endpoint
    emitted the frame" from "heartbeat emitted the frame".  Warmup
    happens with heartbeat on (to complete the boot-handshake), then
    we pause the heartbeat immediately before injecting IR.
    """
    return GpsimControlHarness(
        hex_path,
        fast_boot=False,
        chunk_cycles=600_000,
        heartbeat_rx_mode="full",
    )


def _warmup_and_quiesce(h: GpsimControlHarness) -> None:
    """Bring CONTROL through boot, then pause heartbeat + drain pending TX."""
    h.warmup(25_000_000)
    h.pause_heartbeat()
    # Let any full-sync burst already in flight finish before measuring.
    for _ in range(40):
        h.step()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x3a_emits_standby_frame(v171_hex: Path) -> None:
    """RC5 0x3A on menu address → [B0, 03, 00]."""
    _require_gpsim()
    h = _boot(v171_hex)
    try:
        _warmup_and_quiesce(h)
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x3A)
        for _ in range(24):
            h.step()
        tx = [(f.route, f.cmd, f.data) for f in h.tx_frames()[before:]]
        assert STANDBY_FRAME in tx, (
            f"expected {STANDBY_FRAME} after IR 0x3A; got {tx}"
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x3b_emits_wake_frame(v171_hex: Path) -> None:
    """RC5 0x3B on menu address → [B0, 03, 01]."""
    _require_gpsim()
    h = _boot(v171_hex)
    try:
        _warmup_and_quiesce(h)
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x3B)
        for _ in range(24):
            h.step()
        tx = [(f.route, f.cmd, f.data) for f in h.tx_frames()[before:]]
        assert WAKE_FRAME in tx, (
            f"expected {WAKE_FRAME} after IR 0x3B; got {tx}"
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_endpoints_emit_expected_order(v171_hex: Path) -> None:
    """The IR-triggered frame appears as the FIRST new frame after injection.

    Distinguishing an IR-triggered emission from a coincident stock
    full-sync burst is hard at the simple ``frame in list`` level:
    the stock firmware periodically emits the same ``[B0, 03, 0X]``
    standby/wake broadcast as part of its status poll.  But an IR
    event emits its frame immediately (inside the IR dispatch), before
    any stock periodic code gets cycles.  So the first new frame
    captured after the IR event should be the IR-triggered one.
    """
    _require_gpsim()
    h = _boot(v171_hex)
    try:
        _warmup_and_quiesce(h)

        # Take TX snapshot immediately before the IR event.
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x3A)
        # Very tight window: one step is enough for the ~80 instruction
        # cycles needed to emit the 3-byte frame via tx_byte_enqueue.
        for _ in range(2):
            h.step()
        new_frames_a = [(f.route, f.cmd, f.data) for f in h.tx_frames()[before:]]
        assert new_frames_a, "0x3A did not emit any TX frame"
        assert new_frames_a[0] == STANDBY_FRAME, (
            f"0x3A first new frame != standby; got {new_frames_a[0]}"
        )

        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x3B)
        for _ in range(2):
            h.step()
        new_frames_b = [(f.route, f.cmd, f.data) for f in h.tx_frames()[before:]]
        assert new_frames_b, "0x3B did not emit any TX frame"
        assert new_frames_b[0] == WAKE_FRAME, (
            f"0x3B first new frame != wake; got {new_frames_b[0]}"
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_unknown_code_does_not_prepend_v171_frame(v171_hex: Path) -> None:
    """Unmapped RC5 code: the first new frame (if any) must not be V1.71's.

    Deliberately loose: the stock periodic full-sync burst can land in
    the same 2-step window and prepend its own ``[B0, 07, vol]`` etc.
    We only care that NO V1.71 standby/wake endpoint frame appears
    before any natural stock frame — if it does, my inline dispatch
    is leaking into non-endpoint codes.
    """
    _require_gpsim()
    h = _boot(v171_hex)
    try:
        _warmup_and_quiesce(h)
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x40)
        for _ in range(2):
            h.step()
        new_frames = [(f.route, f.cmd, f.data) for f in h.tx_frames()[before:]]
        if not new_frames:
            return  # no TX activity at all — also acceptable
        first = new_frames[0]
        assert first != STANDBY_FRAME, (
            f"unmapped IR 0x40 emitted standby frame first; got {new_frames}"
        )
        assert first != WAKE_FRAME, (
            f"unmapped IR 0x40 emitted wake frame first; got {new_frames}"
        )
    finally:
        h.close()
