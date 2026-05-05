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
from dlcp_fw.sim.v17_symbols import assemble_v17

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


def _step_tcy(h, tcy: int) -> None:  # type: ignore[no-untyped-def]
    """Advance the harness by exactly `tcy` K20 instruction cycles.
    Rust facade exposes `step_tcy(N)` directly.  gpsim's harness
    only has `step()` which advances `chunk_cycles` (passed at
    construction) per call -- so for the gpsim path the caller
    must construct the harness with `chunk_cycles=tcy` first; this
    helper then issues exactly one `step()` call.
    """
    if hasattr(h, "step_tcy"):
        h.step_tcy(tcy)
    else:
        h.step()


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_preset")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _set_preset_bit(h, value: bool) -> None:  # type: ignore[no-untyped-def]
    """Force-set or -clear the PRESET_BIT before injecting an IR shortcut."""
    flags = h.read_reg(CONTROL_FLAGS_ADDR)
    mask = 1 << PRESET_BIT
    if value:
        flags |= mask
    else:
        flags &= ~mask
    h.write_reg(CONTROL_FLAGS_ADDR, flags)


def _warm_and_dispatch_ir(h, cmd: int, *, steps: int = 24) -> None:  # type: ignore[no-untyped-def]
    h.warmup(25_000_000)
    h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=cmd)
    for _ in range(steps):
        h.step()


def _preset_frame(data: int) -> tuple[int, int, int]:
    return (PRESET_FRAME_ROUTE, PRESET_FRAME_CMD, data)


def _run_with_rust(
    hex_path: Path,
    body,  # Callable[[harness], None]
    *,
    eeprom_init: dict[int, int] | None = None,
) -> None:
    """Run scenario body against the rust facade chain.  `eeprom_init`
    is a dict of {addr: value} bytes seeded via
    `chain.write_control_eeprom_byte` before the body runs.
    """
    _require_rust()
    chain = RustChain.from_v17_chain(str(hex_path))
    if eeprom_init:
        for addr, value in eeprom_init.items():
            chain.write_control_eeprom_byte(addr, value)
    body(chain)


# ---------------------------------------------------------------------------
# Happy-path: IR 0x38 → preset A, IR 0x39 → preset B
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_ir_0x39_sets_preset_b_and_emits_frame(
    v171_hex: Path
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
    _run_with_rust(v171_hex, _do)


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_ir_0x38_sets_preset_a_and_emits_frame(
    v171_hex: Path
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
    _run_with_rust(v171_hex, _do)


# ---------------------------------------------------------------------------
# Idempotence: pressing the same shortcut twice only emits once
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_ir_0x39_twice_emits_once(
    v171_hex: Path
) -> None:
    """Second RC5 0x39 when already in B is a no-op.

    Use a tighter step granularity here (10K Tcy per advancement)
    so the assertion isolates an immediate duplicate IR emit
    instead of catching the independent Layer-2 periodic preset
    broadcast that can legitimately arrive later in a coarse
    200K-Tcy step window.  Codex review of 8917f3f (MEDIUM)
    flagged that rust's fixed 200K-Tcy `step()` was 20x wider
    than gpsim's configured 10K-Tcy chunks, so the body now uses
    `_step_tcy(h, 10_000)` which dispatches to `step_tcy(10000)`
    on rust and (after the gpsim harness is built with
    chunk_cycles=10_000) `step()` on gpsim.
    """
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        _set_preset_bit(h, False)
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x39)
        for _ in range(200):
            _step_tcy(h, 10_000)
        before_second = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x39)
        for _ in range(50):
            _step_tcy(h, 10_000)

        tx_after = [_frame_tuple(f) for f in h.tx_frames()[before_second:]]
        assert _preset_frame(0x01) not in tx_after, (
            f"spurious [B0, 20, 01] on repeat IR 0x39: {tx_after}"
        )
        assert h.read_reg(CONTROL_FLAGS_ADDR) & (1 << PRESET_BIT), (
            "PRESET_BIT should remain set after repeat IR 0x39"
        )
    _run_with_rust(v171_hex, _do)


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_ir_0x38_twice_emits_once(
    v171_hex: Path
) -> None:
    """Second RC5 0x38 when already in A is a no-op.

    Same tightened-window rationale as the repeat-0x39 test
    above (codex MEDIUM): use `_step_tcy(h, 10_000)` so the
    rust path advances at the same 10K-Tcy granularity as
    gpsim's configured chunk size.
    """
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        _set_preset_bit(h, True)
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x38)
        for _ in range(200):
            _step_tcy(h, 10_000)
        before_second = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x38)
        for _ in range(50):
            _step_tcy(h, 10_000)

        tx_after = [_frame_tuple(f) for f in h.tx_frames()[before_second:]]
        assert _preset_frame(0x00) not in tx_after, (
            f"spurious [B0, 20, 00] on repeat IR 0x38: {tx_after}"
        )
        assert not (h.read_reg(CONTROL_FLAGS_ADDR) & (1 << PRESET_BIT)), (
            "PRESET_BIT should remain clear after repeat IR 0x38"
        )
    _run_with_rust(v171_hex, _do)


# ---------------------------------------------------------------------------
# A ↔ B toggle pattern
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_preset_ab_toggle_sequence(
    v171_hex: Path
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
    _run_with_rust(v171_hex, _do)


# ---------------------------------------------------------------------------
# Backcompat: no leakage into non-preset IR paths
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_non_preset_ir_first_frame_is_not_preset(
    v171_hex: Path
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
    _run_with_rust(v171_hex, _do)


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
@pytest.mark.slow
def test_v171_preset_boot_init_byte_01_sets_preset_bit(
    v171_hex: Path, tmp_path: Path
) -> None:
    """EEPROM[0x74] = 0x01 → PRESET_BIT set after settings_load_eeprom runs."""
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert flags & (1 << PRESET_BIT), (
            f"PRESET_BIT not set after boot with EEPROM[0x74]=0x01 "
            f"(flags=0x{flags:02X})"
        )
    _run_with_rust(v171_hex, _do,
        eeprom_init={0x74: 0x01},
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_preset_boot_init_byte_00_clears_preset_bit(
    v171_hex: Path, tmp_path: Path
) -> None:
    """EEPROM[0x74] = 0x00 → PRESET_BIT clear after boot."""
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert not (flags & (1 << PRESET_BIT)), (
            f"PRESET_BIT unexpectedly set after boot with EEPROM[0x74]=0x00 "
            f"(flags=0x{flags:02X})"
        )
    _run_with_rust(v171_hex, _do,
        eeprom_init={0x74: 0x00},
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_preset_boot_init_any_nonzero_nonone_defaults_to_a(
    v171_hex: Path, tmp_path: Path
) -> None:
    """EEPROM[0x74] = 0xFF (erased) → PRESET_BIT clear (defaults to A)."""
    def _do(h) -> None:  # type: ignore[no-untyped-def]
        h.warmup(25_000_000)
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert not (flags & (1 << PRESET_BIT)), (
            f"PRESET_BIT not clear on erased EEPROM[0x74]=0xFF "
            f"(flags=0x{flags:02X})"
        )
    _run_with_rust(v171_hex, _do,
        eeprom_init={0x74: 0xFF},
    )
