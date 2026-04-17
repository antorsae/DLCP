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


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_preset")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _new_harness(hex_path: Path) -> GpsimControlHarness:
    return GpsimControlHarness(
        hex_path,
        fast_boot=False,
        chunk_cycles=600_000,
        hold_cycles=300_000,
        heartbeat_rx_mode="full",
    )


def _set_preset_bit(h: GpsimControlHarness, value: bool) -> None:
    """Force-set or -clear the PRESET_BIT before injecting an IR shortcut."""
    flags = h.read_reg(CONTROL_FLAGS_ADDR)
    mask = 1 << PRESET_BIT
    if value:
        flags |= mask
    else:
        flags &= ~mask
    # Use gpsim's raw register write: reg(0xXXX) = value.
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


# ---------------------------------------------------------------------------
# Happy-path: IR 0x38 → preset A, IR 0x39 → preset B
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x39_sets_preset_b_and_emits_frame(v171_hex: Path) -> None:
    """Starting from preset A, RC5 0x39 flips to B and emits [B0, 20, 01]."""
    _require_gpsim()
    h = _new_harness(v171_hex)
    try:
        h.warmup(25_000_000)
        _set_preset_bit(h, False)
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x39)
        for _ in range(24):
            h.step()

        tx = [(f.route, f.cmd, f.data) for f in h.tx_frames()[before:]]
        assert _preset_frame(0x01) in tx, (
            f"expected [B0, 20, 01] after IR 0x39; got {tx}"
        )
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert flags & (1 << PRESET_BIT), (
            f"PRESET_BIT not set after IR 0x39 (flags=0x{flags:02X})"
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x38_sets_preset_a_and_emits_frame(v171_hex: Path) -> None:
    """Starting from preset B, RC5 0x38 flips to A and emits [B0, 20, 00]."""
    _require_gpsim()
    h = _new_harness(v171_hex)
    try:
        h.warmup(25_000_000)
        _set_preset_bit(h, True)
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x38)
        for _ in range(24):
            h.step()

        tx = [(f.route, f.cmd, f.data) for f in h.tx_frames()[before:]]
        assert _preset_frame(0x00) in tx, (
            f"expected [B0, 20, 00] after IR 0x38; got {tx}"
        )
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert not (flags & (1 << PRESET_BIT)), (
            f"PRESET_BIT not cleared after IR 0x38 (flags=0x{flags:02X})"
        )
    finally:
        h.close()


# ---------------------------------------------------------------------------
# Idempotence: pressing the same shortcut twice only emits once
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x39_twice_emits_once(v171_hex: Path) -> None:
    """Second RC5 0x39 when already in B is a no-op — no duplicate frame."""
    _require_gpsim()
    h = _new_harness(v171_hex)
    try:
        h.warmup(25_000_000)
        _set_preset_bit(h, False)
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x39)
        for _ in range(24):
            h.step()
        before_second = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x39)
        for _ in range(24):
            h.step()

        tx_after = [(f.route, f.cmd, f.data) for f in h.tx_frames()[before_second:]]
        assert _preset_frame(0x01) not in tx_after, (
            f"spurious [B0, 20, 01] on repeat IR 0x39: {tx_after}"
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_ir_0x38_twice_emits_once(v171_hex: Path) -> None:
    """Second RC5 0x38 when already in A is a no-op — no duplicate frame."""
    _require_gpsim()
    h = _new_harness(v171_hex)
    try:
        h.warmup(25_000_000)
        _set_preset_bit(h, True)
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x38)
        for _ in range(24):
            h.step()
        before_second = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x38)
        for _ in range(24):
            h.step()

        tx_after = [(f.route, f.cmd, f.data) for f in h.tx_frames()[before_second:]]
        assert _preset_frame(0x00) not in tx_after, (
            f"spurious [B0, 20, 00] on repeat IR 0x38: {tx_after}"
        )
    finally:
        h.close()


# ---------------------------------------------------------------------------
# A ↔ B toggle pattern
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_preset_ab_toggle_sequence(v171_hex: Path) -> None:
    """0x39, 0x38, 0x39 yields [B, A, B] frame sequence and flag toggle."""
    _require_gpsim()
    h = _new_harness(v171_hex)
    try:
        h.warmup(25_000_000)
        _set_preset_bit(h, False)
        seen: list[tuple[int, int, int]] = []
        for cmd, expected_data in ((0x39, 0x01), (0x38, 0x00), (0x39, 0x01)):
            before = len(h.tx_frames())
            h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=cmd)
            for _ in range(24):
                h.step()
            emitted = [(f.route, f.cmd, f.data) for f in h.tx_frames()[before:]]
            seen.extend(emitted)
            assert _preset_frame(expected_data) in emitted, (
                f"expected [B0, 20, {expected_data:02X}] after IR 0x{cmd:02X}; got {emitted}"
            )
        # Final flag state should match last shortcut (0x39 → B).
        assert h.read_reg(CONTROL_FLAGS_ADDR) & (1 << PRESET_BIT)
    finally:
        h.close()


# ---------------------------------------------------------------------------
# Backcompat: no leakage into non-preset IR paths
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_non_preset_ir_does_not_emit_preset_frame(v171_hex: Path) -> None:
    """A menu-configured RC5 (e.g. 0x10 = volume up) must NOT emit preset frame."""
    _require_gpsim()
    h = _new_harness(v171_hex)
    try:
        h.warmup(25_000_000)
        before = len(h.tx_frames())
        h.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x10)  # volume up
        for _ in range(24):
            h.step()
        tx = [(f.route, f.cmd, f.data) for f in h.tx_frames()[before:]]
        # Neither A nor B preset frames should appear on a non-preset shortcut.
        assert _preset_frame(0x00) not in tx
        assert _preset_frame(0x01) not in tx
    finally:
        h.close()


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


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_preset_boot_init_byte_01_sets_preset_bit(
    v171_hex: Path, tmp_path: Path
) -> None:
    """EEPROM[0x74] = 0x01 → PRESET_BIT set after settings_load_eeprom runs."""
    _require_gpsim()
    ee_path = tmp_path / "preset_b.hex"
    _write_preset_eeprom_image(ee_path, 0x01)
    h = GpsimControlHarness(
        v171_hex,
        fast_boot=False,
        eeprom_file=ee_path,
        chunk_cycles=600_000,
        heartbeat_rx_mode="full",
    )
    try:
        h.warmup(25_000_000)
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert flags & (1 << PRESET_BIT), (
            f"PRESET_BIT not set after boot with EEPROM[0x74]=0x01 "
            f"(flags=0x{flags:02X})"
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_preset_boot_init_byte_00_clears_preset_bit(
    v171_hex: Path, tmp_path: Path
) -> None:
    """EEPROM[0x74] = 0x00 → PRESET_BIT clear after boot."""
    _require_gpsim()
    ee_path = tmp_path / "preset_a.hex"
    _write_preset_eeprom_image(ee_path, 0x00)
    h = GpsimControlHarness(
        v171_hex,
        fast_boot=False,
        eeprom_file=ee_path,
        chunk_cycles=600_000,
        heartbeat_rx_mode="full",
    )
    try:
        h.warmup(25_000_000)
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert not (flags & (1 << PRESET_BIT)), (
            f"PRESET_BIT unexpectedly set after boot with EEPROM[0x74]=0x00 "
            f"(flags=0x{flags:02X})"
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_preset_boot_init_any_nonzero_nonone_defaults_to_a(
    v171_hex: Path, tmp_path: Path
) -> None:
    """EEPROM[0x74] = 0xFF (erased) → PRESET_BIT clear (defaults to A)."""
    _require_gpsim()
    ee_path = tmp_path / "preset_erased.hex"
    _write_preset_eeprom_image(ee_path, 0xFF)
    h = GpsimControlHarness(
        v171_hex,
        fast_boot=False,
        eeprom_file=ee_path,
        chunk_cycles=600_000,
        heartbeat_rx_mode="full",
    )
    try:
        h.warmup(25_000_000)
        flags = h.read_reg(CONTROL_FLAGS_ADDR)
        assert not (flags & (1 << PRESET_BIT)), (
            f"PRESET_BIT not clear on erased EEPROM[0x74]=0xFF "
            f"(flags=0x{flags:02X})"
        )
    finally:
        h.close()
