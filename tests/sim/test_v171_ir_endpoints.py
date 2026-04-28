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

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


PRESET_ADDR = 0x10
STANDBY_FRAME = (0xB0, 0x03, 0x00)
WAKE_FRAME = (0xB0, 0x03, 0x01)


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    if not _IMPORT_OK:
        pytest.skip("control_gpsim harness not importable")


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _frame_tuple(f) -> tuple[int, int, int]:  # type: ignore[no-untyped-def]
    """Normalise a TX frame into a (route, cmd, data) tuple.
    gpsim's `tx_frames()` returns TxTriplet dataclass instances
    (with .route/.cmd/.data attrs); rust returns plain tuples.
    """
    if isinstance(f, tuple):
        return f
    return (f.route, f.cmd, f.data)


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


def _run_in_backends(
    backend: str,
    hex_path: Path,
    body,  # Callable[[harness], None]
) -> None:
    """Dispatch a duck-typed scenario body to gpsim, rust, or both
    per the `dlcp_sim_backend` fixture.  Rust runs first in dual
    mode so a missing native binding fails fast.
    """
    if backend in {"rust", "dual"}:
        _require_rust()
        chain = RustChain.from_v17_chain(str(hex_path))
        body(chain)
    if backend in {"gpsim", "dual"}:
        _require_gpsim()
        h = _boot(hex_path)
        try:
            body(h)
        finally:
            h.close()


def _run_ir_emits_frame(cmd: int, expected: tuple[int, int, int], label: str):
    """Build a duck-typed body asserting that injecting `cmd` yields
    `expected` somewhere in the TX stream after a 24-step settle.
    """
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        _warmup_and_quiesce(h)
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=cmd)
        for _ in range(24):
            h.step()
        tx = [_frame_tuple(f) for f in h.tx_frames()[before:]]
        assert expected in tx, (
            f"{label}: expected {expected} after IR {cmd:#x}; got {tx}"
        )
    return _do


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x3a_emits_standby_frame(
    v171_hex: Path, dlcp_sim_backend: str
) -> None:
    """RC5 0x3A on menu address → [B0, 03, 00]."""
    _run_in_backends(
        dlcp_sim_backend, v171_hex,
        _run_ir_emits_frame(0x3A, STANDBY_FRAME, "IR 0x3A"),
    )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x3b_emits_wake_frame(
    v171_hex: Path, dlcp_sim_backend: str
) -> None:
    """RC5 0x3B on menu address → [B0, 03, 01]."""
    _run_in_backends(
        dlcp_sim_backend, v171_hex,
        _run_ir_emits_frame(0x3B, WAKE_FRAME, "IR 0x3B"),
    )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_endpoints_emit_expected_order(
    v171_hex: Path, dlcp_sim_backend: str
) -> None:
    """The IR-triggered frame appears as the FIRST new frame after injection.

    Distinguishing an IR-triggered emission from a coincident stock
    full-sync burst is hard at the simple ``frame in list`` level:
    the stock firmware periodically emits the same ``[B0, 03, 0X]``
    standby/wake broadcast as part of its status poll.  But an IR
    event emits its frame immediately (inside the IR dispatch), before
    any stock periodic code gets cycles.  So the first new frame
    captured after the IR event should be the IR-triggered one.
    """
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        _warmup_and_quiesce(h)

        # Take TX snapshot immediately before the IR event.
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x3A)
        # Very tight window: one step is enough for the ~80 instruction
        # cycles needed to emit the 3-byte frame via tx_byte_enqueue.
        for _ in range(2):
            h.step()
        new_frames_a = [_frame_tuple(f) for f in h.tx_frames()[before:]]
        assert new_frames_a, "0x3A did not emit any TX frame"
        assert new_frames_a[0] == STANDBY_FRAME, (
            f"0x3A first new frame != standby; got {new_frames_a[0]}"
        )

        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x3B)
        for _ in range(2):
            h.step()
        new_frames_b = [_frame_tuple(f) for f in h.tx_frames()[before:]]
        assert new_frames_b, "0x3B did not emit any TX frame"
        assert new_frames_b[0] == WAKE_FRAME, (
            f"0x3B first new frame != wake; got {new_frames_b[0]}"
        )
    _run_in_backends(dlcp_sim_backend, v171_hex, _do)


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_unknown_code_does_not_prepend_v171_frame(
    v171_hex: Path, dlcp_sim_backend: str
) -> None:
    """Unmapped RC5 code: the first new frame (if any) must not be V1.71's.

    Deliberately loose: the stock periodic full-sync burst can land in
    the same 2-step window and prepend its own ``[B0, 07, vol]`` etc.
    We only care that NO V1.71 standby/wake endpoint frame appears
    before any natural stock frame — if it does, my inline dispatch
    is leaking into non-endpoint codes.
    """
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        _warmup_and_quiesce(h)
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x40)
        for _ in range(2):
            h.step()
        new_frames = [_frame_tuple(f) for f in h.tx_frames()[before:]]
        if not new_frames:
            return  # no TX activity at all — also acceptable
        first = new_frames[0]
        assert first != STANDBY_FRAME, (
            f"unmapped IR 0x40 emitted standby frame first; got {new_frames}"
        )
        assert first != WAKE_FRAME, (
            f"unmapped IR 0x40 emitted wake frame first; got {new_frames}"
        )
    _run_in_backends(dlcp_sim_backend, v171_hex, _do)
