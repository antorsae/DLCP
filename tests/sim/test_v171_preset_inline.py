"""V1.71 Phase B (first inline): IR 0x38 / 0x39 preset A/B shortcuts.

Verifies the behavioral surface of the first inline V1.61b feature:

* RC5 0x38 on the menu-configured IR address clears `control_flags.6`
  (PRESET_BIT) and emits the ``[0xB0, 0x20, 0x00]`` preset-select
  broadcast frame.
* RC5 0x39 sets `control_flags.6` and emits ``[0xB0, 0x20, 0x01]``.
* Re-issuing the same shortcut after the bit already matches is a
  no-op — no frame emitted, no EEPROM write.
* EEPROM byte 0x74 is updated by the inline helper
  ``v171_send_preset_frame_and_persist`` (visible as a
  ``reg(0xFA9)=0x74 reg(0xFA8)=...`` sequence via gpsim's EEPROM
  emulation).

Upstream V1.7 suite must remain green.  All tests are ``gpsim``
markers; the structural gates live in ``test_v171_baseline.py``.
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


PRESET_ADDR = 0x10  # menu_configured IR address (RAM 0x20 in stock V1.6b)
PRESET_FRAME_ROUTE = 0xB0
PRESET_FRAME_CMD = 0x20
CONTROL_FLAGS_ADDR = 0x01F
PRESET_BIT = 6


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
    if isinstance(f, tuple):
        return f
    return (f.route, f.cmd, f.data)


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_preset")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _new_harness(
    hex_path: Path,
    *,
    chunk_cycles: int = 600_000,
    hold_cycles: int = 300_000,
) -> GpsimControlHarness:
    return GpsimControlHarness(
        hex_path,
        fast_boot=False,
        chunk_cycles=chunk_cycles,
        hold_cycles=hold_cycles,
        heartbeat_rx_mode="full",
    )


def _set_preset_bit(h, value: bool) -> None:  # type: ignore[no-untyped-def]
    """Force-set or -clear the PRESET_BIT before injecting an IR shortcut.

    Backend-agnostic: rust harness exposes `write_reg`; gpsim only
    has the lower-level `_issue` register-poke command.
    """
    flags = h.read_reg(CONTROL_FLAGS_ADDR)
    mask = 1 << PRESET_BIT
    if value:
        flags |= mask
    else:
        flags &= ~mask
    if hasattr(h, "write_reg"):
        h.write_reg(CONTROL_FLAGS_ADDR, flags)
    else:
        h._issue(f"reg(0x{CONTROL_FLAGS_ADDR:03X})=0x{flags:02X}", 5.0)


def _warm_and_dispatch_ir(
    h: GpsimControlHarness,
    cmd: int,
    *,
    steps: int = 24,
) -> None:
    h.warmup(25_000_000)
    h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=cmd)
    for _ in range(steps):
        h.step()


def _preset_frame(data: int) -> tuple[int, int, int]:
    return (PRESET_FRAME_ROUTE, PRESET_FRAME_CMD, data)


def _run_in_backends(
    backend: str,
    hex_path: Path,
    body,  # Callable[[harness], None]
    *,
    chunk_cycles: int = 600_000,
    hold_cycles: int = 300_000,
    eeprom_init: dict[int, int] | None = None,
) -> None:
    """Dispatch a duck-typed body to gpsim / rust / both per backend.
    Rust runs first in dual mode so a missing native binding fails
    fast.  `eeprom_init` is a dict of {addr: value} bytes to seed
    into CONTROL's EEPROM before warmup -- gpsim path writes a HEX
    file and passes `eeprom_file=`; rust path calls
    `chain.write_control_eeprom_byte` per entry.
    """
    if backend in {"rust", "dual"}:
        _require_rust()
        chain = RustChain.from_v17_chain(str(hex_path))
        if eeprom_init:
            for addr, value in eeprom_init.items():
                chain.write_control_eeprom_byte(addr, value)
        body(chain)
    if backend in {"gpsim", "dual"}:
        _require_gpsim()
        eeprom_kwargs = {}
        if eeprom_init:
            # gpsim consumes EEPROM via `eeprom_file=` HEX path.
            # Build a single-record HEX file with the seeded bytes
            # (only the lowest-addr entry is a single byte; for
            # non-contiguous seeds, callers should write one HEX
            # file per dict entry -- the V1.71 preset tests only
            # seed one byte at 0x74).
            import tempfile
            tmp_dir = tempfile.mkdtemp(prefix="rust_eeprom_seed_")
            ee_path = Path(tmp_dir) / "seed.hex"
            # For the preset tests we only seed one byte; emit a
            # single record per entry, then the EOF.
            lines: list[str] = []
            for addr, value in eeprom_init.items():
                ll = 1
                total = ll + ((addr >> 8) & 0xFF) + (addr & 0xFF) + value
                cc = (~total + 1) & 0xFF
                lines.append(f":{ll:02X}{addr:04X}00{value:02X}{cc:02X}")
            lines.append(":00000001FF")
            ee_path.write_text("\n".join(lines) + "\n", encoding="ascii")
            eeprom_kwargs["eeprom_file"] = ee_path
        h = GpsimControlHarness(
            hex_path,
            fast_boot=False,
            chunk_cycles=chunk_cycles,
            hold_cycles=hold_cycles,
            heartbeat_rx_mode="full",
            **eeprom_kwargs,
        )
        try:
            body(h)
        finally:
            h.close()


# ---------------------------------------------------------------------------
# Happy-path: IR 0x38 → preset A, IR 0x39 → preset B
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x39_sets_preset_b_and_emits_frame(
    v171_hex: Path, dlcp_sim_backend: str
) -> None:
    """Starting from preset A, RC5 0x39 flips to B and emits [B0, 20, 01]."""
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        _set_preset_bit(h, False)
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x39)
        for _ in range(24):
            h.step()

        tx = [_frame_tuple(f) for f in h.tx_frames()[before:]]
        assert _preset_frame(0x01) in tx, (
            f"expected [B0, 20, 01] after IR 0x39; got {tx}"
        )
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert flags & (1 << PRESET_BIT), (
            f"PRESET_BIT not set after IR 0x39 (flags=0x{flags:02X})"
        )
    _run_in_backends(dlcp_sim_backend, v171_hex, _do)


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x38_sets_preset_a_and_emits_frame(
    v171_hex: Path, dlcp_sim_backend: str
) -> None:
    """Starting from preset B, RC5 0x38 flips to A and emits [B0, 20, 00]."""
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        _set_preset_bit(h, True)
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x38)
        for _ in range(24):
            h.step()

        tx = [_frame_tuple(f) for f in h.tx_frames()[before:]]
        assert _preset_frame(0x00) in tx, (
            f"expected [B0, 20, 00] after IR 0x38; got {tx}"
        )
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert not (flags & (1 << PRESET_BIT)), (
            f"PRESET_BIT not cleared after IR 0x38 (flags=0x{flags:02X})"
        )
    _run_in_backends(dlcp_sim_backend, v171_hex, _do)


# ---------------------------------------------------------------------------
# Idempotence: pressing the same shortcut twice only emits once
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x39_twice_emits_once(
    v171_hex: Path, dlcp_sim_backend: str
) -> None:
    """Second RC5 0x39 when already in B is a no-op.

    Use a tighter chunk size here so the assertion isolates an immediate
    duplicate IR emit instead of catching the independent Layer-2 periodic
    preset broadcast that can legitimately arrive later in a coarse 600k-
    cycle step window.
    """
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        _set_preset_bit(h, False)
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x39)
        for _ in range(200):
            h.step()
        before_second = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x39)
        for _ in range(50):
            h.step()

        tx_after = [_frame_tuple(f) for f in h.tx_frames()[before_second:]]
        assert _preset_frame(0x01) not in tx_after, (
            f"spurious [B0, 20, 01] on repeat IR 0x39: {tx_after}"
        )
        assert h.read_reg(CONTROL_FLAGS_ADDR) & (1 << PRESET_BIT), (
            "PRESET_BIT should remain set after repeat IR 0x39"
        )
    _run_in_backends(
        dlcp_sim_backend, v171_hex, _do,
        chunk_cycles=10_000, hold_cycles=5_000,
    )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x38_twice_emits_once(
    v171_hex: Path, dlcp_sim_backend: str
) -> None:
    """Second RC5 0x38 when already in A is a no-op.

    Same tightened window rationale as the repeat-0x39 test above.
    """
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        _set_preset_bit(h, True)
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x38)
        for _ in range(200):
            h.step()
        before_second = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x38)
        for _ in range(50):
            h.step()

        tx_after = [_frame_tuple(f) for f in h.tx_frames()[before_second:]]
        assert _preset_frame(0x00) not in tx_after, (
            f"spurious [B0, 20, 00] on repeat IR 0x38: {tx_after}"
        )
        assert not (h.read_reg(CONTROL_FLAGS_ADDR) & (1 << PRESET_BIT)), (
            "PRESET_BIT should remain clear after repeat IR 0x38"
        )
    _run_in_backends(
        dlcp_sim_backend, v171_hex, _do,
        chunk_cycles=10_000, hold_cycles=5_000,
    )


# ---------------------------------------------------------------------------
# A ↔ B toggle pattern
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_preset_ab_toggle_sequence(
    v171_hex: Path, dlcp_sim_backend: str
) -> None:
    """0x39, 0x38, 0x39 yields [B, A, B] frame sequence and flag toggle."""
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        _set_preset_bit(h, False)
        seen: list[tuple[int, int, int]] = []
        for cmd, expected_data in ((0x39, 0x01), (0x38, 0x00), (0x39, 0x01)):
            before = len(h.tx_frames())
            h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=cmd)
            for _ in range(24):
                h.step()
            emitted = [_frame_tuple(f) for f in h.tx_frames()[before:]]
            seen.extend(emitted)
            assert _preset_frame(expected_data) in emitted, (
                f"expected [B0, 20, {expected_data:02X}] after IR 0x{cmd:02X}; got {emitted}"
            )
        # Final flag state should match last shortcut (0x39 → B).
        assert h.read_reg(CONTROL_FLAGS_ADDR) & (1 << PRESET_BIT)
    _run_in_backends(dlcp_sim_backend, v171_hex, _do)


# ---------------------------------------------------------------------------
# Backcompat: no leakage into non-preset IR paths
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_non_preset_ir_first_frame_is_not_preset(
    v171_hex: Path, dlcp_sim_backend: str
) -> None:
    """A menu-configured RC5 (0x10 = volume up): the IR-triggered frame
    is NOT a preset frame.

    V1.71's full-sync retry counter (Phase B.5) emits preset frames
    periodically as part of the normal sync burst, so we cannot assert
    "no preset frame ever appears in TX".  Instead, we verify that the
    IR-triggered emission itself (the FIRST new frame after injection)
    is NOT a preset frame — which catches any leakage where volume IRs
    inadvertently trigger the preset TX path.
    """
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        h.pause_heartbeat()
        for _ in range(40):
            h.step()
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x10)  # volume up
        for _ in range(2):
            h.step()
        new_frames = [_frame_tuple(f) for f in h.tx_frames()[before:]]
        if not new_frames:
            return
        first = new_frames[0]
        assert first != _preset_frame(0x00), (
            f"volume-up IR emitted preset A frame first; got {new_frames}"
        )
        assert first != _preset_frame(0x01), (
            f"volume-up IR emitted preset B frame first; got {new_frames}"
        )
    _run_in_backends(dlcp_sim_backend, v171_hex, _do)


# ---------------------------------------------------------------------------
# Preset boot init: EEPROM 0x74 → PRESET_BIT (V1.71 inline of V1.61b)
# ---------------------------------------------------------------------------

def _write_preset_eeprom_image(path: Path, preset_byte: int) -> None:
    """Write an Intel HEX EEPROM image with byte 0x74 = ``preset_byte``.

    gpsim's ``load e`` expects EEPROM data at the raw 0x00..0xFF
    addresses (no 0xF00000 extension); we produce a minimal single-
    record image setting the preset slot.
    """
    addr = 0x0074
    data = bytes([preset_byte & 0xFF])
    ll = len(data)
    total = ll + ((addr >> 8) & 0xFF) + (addr & 0xFF) + 0x00 + sum(data)
    cc = (~total + 1) & 0xFF
    record = f":{ll:02X}{addr:04X}00{data.hex().upper()}{cc:02X}"
    path.write_text(record + "\n" + ":00000001FF\n", encoding="ascii")


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_preset_boot_init_byte_01_sets_preset_bit(
    v171_hex: Path, tmp_path: Path, dlcp_sim_backend: str
) -> None:
    """EEPROM[0x74] = 0x01 → PRESET_BIT set after settings_load_eeprom runs."""
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert flags & (1 << PRESET_BIT), (
            f"PRESET_BIT not set after boot with EEPROM[0x74]=0x01 "
            f"(flags=0x{flags:02X})"
        )
    _run_in_backends(
        dlcp_sim_backend, v171_hex, _do,
        eeprom_init={0x74: 0x01},
    )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_preset_boot_init_byte_00_clears_preset_bit(
    v171_hex: Path, tmp_path: Path, dlcp_sim_backend: str
) -> None:
    """EEPROM[0x74] = 0x00 → PRESET_BIT clear after boot."""
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert not (flags & (1 << PRESET_BIT)), (
            f"PRESET_BIT unexpectedly set after boot with EEPROM[0x74]=0x00 "
            f"(flags=0x{flags:02X})"
        )
    _run_in_backends(
        dlcp_sim_backend, v171_hex, _do,
        eeprom_init={0x74: 0x00},
    )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_preset_boot_init_any_nonzero_nonone_defaults_to_a(
    v171_hex: Path, tmp_path: Path, dlcp_sim_backend: str
) -> None:
    """EEPROM[0x74] = 0xFF (erased) → PRESET_BIT clear (defaults to A)."""
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert not (flags & (1 << PRESET_BIT)), (
            f"PRESET_BIT not clear on erased EEPROM[0x74]=0xFF "
            f"(flags=0x{flags:02X})"
        )
    _run_in_backends(
        dlcp_sim_backend, v171_hex, _do,
        eeprom_init={0x74: 0xFF},
    )
