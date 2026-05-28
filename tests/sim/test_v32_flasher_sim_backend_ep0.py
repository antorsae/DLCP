"""Sim-backed EP0 backend foundation test.

Exercises the ``SimDlcpEp0`` adapter at
``src/dlcp_fw/flash/sim_backend.py`` end-to-end against a rust
``Chain.from_v171_v32`` chain.  Demonstrates that the flasher's
existing EP0 helpers (``_ep0_read_byte``, ``_ep0_or_byte``,
``_force_active_filename_persist``) work unchanged when handed a
``SimDlcpEp0`` instead of a real ``DlcpEp0``.

This is the foundation for option A (full flasher-script + fake-USB
integration with rust sim).  Subsequent commits add HID-feature-
report support so cmd 0x03 / cmd 0x43 are also covered.
"""

from __future__ import annotations

import pytest

from dlcp_fw.paths import V171_CONTROL_HEX, V32_MAIN_HEX

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_OK = True
    _RUST_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_OK = False
    _RUST_ERROR = exc

from dlcp_fw.flash.sim_backend import SimDlcpEp0, make_sim_ep0


pytestmark = pytest.mark.dual_supported


# Hand-mirrored from src/dlcp_fw/flash/dlcp_main_flash.py constants
# (kept private there).  Cross-check on test setup: V3.2 RAM map.
_ACTIVE_FLAGS_ADDR = 0x05E
_ACTIVE_PRESET_MASK = 0x04
_ACTIVE_REAPPLY_MASK = 0x80
_EVENT_FLAGS_ADDR = 0x07E
_FILENAME_DIRTY_FLAGS_ADDR = 0x0BD
_EVENT_DIRTY_SERVICE_MASK = 0x01
_FILENAME_DIRTY_MASK = 0x20
_USB_XACT_PENDING_MASK = 0x40
_FILENAME_RAM_BASE = 0x2C0
_FILENAME_RAM_LEN = 0x1E
_PRESET_A_EEPROM_BASE = 0x60
_PRESET_B_EEPROM_BASE = 0x83


def _require_rust() -> None:
    if not _RUST_OK:
        pytest.fail(f"rust facade not importable: {_RUST_ERROR!r}")


def _open_chain():
    _require_rust()
    if not V171_CONTROL_HEX.exists() or not V32_MAIN_HEX.exists():
        pytest.skip("missing V1.71 and/or V3.2 firmware artifacts")
    chain = RustChain.from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(V32_MAIN_HEX),
    )
    chain.run_until_connected(limit=400)
    assert chain.is_connected() and not chain.is_waiting()
    chain.step_ticks(50_000_000)  # boot-side preset-load settle
    return chain


def _open_main_only_chain():
    _require_rust()
    if not V32_MAIN_HEX.exists():
        pytest.skip("missing V3.2 firmware artifact")
    chain = RustChain.from_v3x_main_only(str(V32_MAIN_HEX))
    chain.step_tcy(20 * 200_000)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(20 * 200_000)
    assert chain.read_reg(_ACTIVE_FLAGS_ADDR) & 0x08, "MAIN not active"
    return chain


def _filename_slot(label: bytes) -> bytes:
    if len(label) > _FILENAME_RAM_LEN:
        raise ValueError(label)
    return label + bytes([0xFF] * (_FILENAME_RAM_LEN - len(label)))


def _seed_main_only_filename_slot(chain, base: int, slot: bytes) -> None:  # type: ignore[no-untyped-def]
    for i, value in enumerate(slot):
        chain.write_main_eeprom_byte(0, base + i, value)


def _read_main_only_filename_ram(chain) -> bytes:  # type: ignore[no-untyped-def]
    return bytes(chain.read_reg(_FILENAME_RAM_BASE + i) for i in range(_FILENAME_RAM_LEN))


def test_sim_ep0_read_byte_matches_chain_read_main_reg() -> None:
    """``ep0.set_pointer(addr) + ep0.read_exact(1)`` must read the same
    byte ``chain.read_main_reg(unit, addr)`` does -- proving the EP0
    read path is semantically equivalent to direct facade access."""
    chain = _open_chain()
    ep0 = make_sim_ep0(chain, unit=1)  # MAIN1 / PB2 / --right

    for addr in (0x000, 0x05E, 0x07E, 0x0BD, 0x2C0, 0x2DE):
        expected = chain.read_main_reg(1, addr)
        ep0.set_pointer(addr)
        got = ep0.read_exact(1)[0]
        assert got == expected, (
            f"EP0 read at 0x{addr:04X} mismatched chain.read_main_reg: "
            f"got 0x{got:02X}, expected 0x{expected:02X}"
        )


def test_sim_ep0_read_exact_auto_increments_pointer() -> None:
    """The real EP0 protocol auto-increments TBLPTR on every read via
    ``_poke(0xE7, n, in_dir=True, ...)``.  ``SimDlcpEp0.read_exact``
    mirrors that: a multi-byte read starting at ``addr`` returns
    consecutive RAM bytes."""
    chain = _open_chain()
    ep0 = make_sim_ep0(chain, unit=1)

    # Read the full filename-RAM window.
    ep0.set_pointer(_FILENAME_RAM_BASE)
    sim_window = ep0.read_exact(_FILENAME_RAM_LEN)
    assert len(sim_window) == _FILENAME_RAM_LEN

    direct = bytes(
        chain.read_main_reg(1, _FILENAME_RAM_BASE + i)
        for i in range(_FILENAME_RAM_LEN)
    )
    assert sim_window == direct, (
        f"EP0 read_exact window did not match chain.read_main_reg "
        f"sweep:\n  ep0={sim_window.hex()}\n  raw={direct.hex()}"
    )


def test_sim_ep0_poke_writes_via_chain() -> None:
    """``ep0._poke(addr, value, in_dir=False)`` must write ``value``
    to MAIN[unit] RAM at ``addr`` so a subsequent read returns it.
    Used by the real ``_ep0_write_byte`` and ``_ep0_or_byte``
    helpers in the flasher."""
    chain = _open_chain()
    ep0 = make_sim_ep0(chain, unit=1)

    # Pick a benign scratch address; this is the V3.2 ram_0x00B/00C
    # area which firmware uses for transient EEPROM helper state but
    # is undefined between calls -- safe to clobber for the test.
    SCRATCH_ADDR = 0x00B
    ep0._poke(SCRATCH_ADDR, 0x5A, in_dir=False)
    assert chain.read_main_reg(1, SCRATCH_ADDR) == 0x5A
    ep0._poke(SCRATCH_ADDR, 0xA5, in_dir=False)
    assert chain.read_main_reg(1, SCRATCH_ADDR) == 0xA5


def test_sim_ep0_unit_routing_targets_correct_main() -> None:
    """``unit=0`` writes hit MAIN0; ``unit=1`` writes hit MAIN1.
    Cross-check via per-MAIN reads -- writes to one MAIN must not
    leak into the other."""
    chain = _open_chain()
    SCRATCH_ADDR = 0x00C
    chain.write_main_reg(0, SCRATCH_ADDR, 0x00)
    chain.write_main_reg(1, SCRATCH_ADDR, 0x00)
    ep0_main0 = make_sim_ep0(chain, unit=0)
    ep0_main1 = make_sim_ep0(chain, unit=1)

    ep0_main0._poke(SCRATCH_ADDR, 0x11, in_dir=False)
    ep0_main1._poke(SCRATCH_ADDR, 0x22, in_dir=False)

    assert chain.read_main_reg(0, SCRATCH_ADDR) == 0x11, (
        "write via unit=0 EP0 must hit MAIN0"
    )
    assert chain.read_main_reg(1, SCRATCH_ADDR) == 0x22, (
        "write via unit=1 EP0 must hit MAIN1"
    )


def test_sim_ep0_force_persist_clears_filename_dirty() -> None:
    """Integration: drive the flasher's ``_force_active_filename_persist``
    semantic via SimDlcpEp0.  Prior ``cmd 0x03`` is simulated by
    direct RAM pokes (the existing pattern from
    ``test_v32_usb_filename_xact_gate.py``); the EP0 backend then
    triggers ``event_flags.0`` to drive the firmware's persist
    handler.  Final ``filename_dirty_flags.bit5`` must clear."""
    chain = _open_chain()
    ep0 = make_sim_ep0(chain, unit=1)

    # Simulate cmd 0x03 WRITE side effect: filename RAM dirty + xact
    # gate set + a recognizable filename in RAM.  (Future commit
    # replaces this with a SimHidBackend that drives the firmware's
    # actual cmd 0x03 dispatch end-to-end.)
    sentinel = b"sim-flasher-ep0-test           "[:_FILENAME_RAM_LEN]
    for i, value in enumerate(sentinel):
        chain.write_main_reg(1, _FILENAME_RAM_BASE + i, value)
    flags = chain.read_main_reg(1, _FILENAME_DIRTY_FLAGS_ADDR)
    chain.write_main_reg(
        1,
        _FILENAME_DIRTY_FLAGS_ADDR,
        flags | _FILENAME_DIRTY_MASK | _USB_XACT_PENDING_MASK,
    )

    # EP0 op: read event_flags via the EP0 read path (proves the
    # backend can survey the state the flasher polls).
    ep0.set_pointer(_EVENT_FLAGS_ADDR)
    pre_event = ep0.read_exact(1)[0]
    # EP0 op: poke event_flags to set the dirty-service bit.
    ep0._poke(
        _EVENT_FLAGS_ADDR,
        pre_event | _EVENT_DIRTY_SERVICE_MASK,
        in_dir=False,
    )

    # Step the chain so the firmware's main_core_service_265c
    # dispatcher runs and persists the filename + clears bit5/bit6.
    chain.step_ticks(200_000_000)

    # EP0 op: read filename_dirty_flags via the EP0 read path.
    # Validate both bits cleared (bit5: persist done; bit6: xact
    # gate cleared per the V3.2 USB-xact-gate fix).
    ep0.set_pointer(_FILENAME_DIRTY_FLAGS_ADDR)
    flags_after = ep0.read_exact(1)[0]
    assert (flags_after & _FILENAME_DIRTY_MASK) == 0, (
        f"filename dirty bit should clear after force_persist; "
        f"got 0x{flags_after:02X}"
    )
    assert (flags_after & _USB_XACT_PENDING_MASK) == 0, (
        f"USB xact gate (bit6) should clear after force_persist; "
        f"got 0x{flags_after:02X}"
    )


def test_v32_ep0_reapply_reload_filename_ram_for_restored_preset() -> None:
    """BUG-PRESET-01: active_flags.bit7 reapply must reload the live
    filename RAM for the restored preset.

    Release flashing writes preset A's filename, then preset B's filename,
    then restores the originally active preset through the EP0 reapply path.
    With no CONTROL broadcast involved, that reapply path must update
    RAM 0x2C0..0x2DD from the active preset's EEPROM slot.
    """
    chain = _open_main_only_chain()
    slot_a = _filename_slot(b"LX521.4 22MG10F-v5")
    slot_b = _filename_slot(b"LX521.4 22MG10F-v7")
    _seed_main_only_filename_slot(chain, _PRESET_A_EEPROM_BASE, slot_a)
    _seed_main_only_filename_slot(chain, _PRESET_B_EEPROM_BASE, slot_b)

    # Precondition: device is currently on B and live RAM still shows B.
    flags = chain.read_reg(_ACTIVE_FLAGS_ADDR)
    flags = (flags | _ACTIVE_PRESET_MASK) & (~_ACTIVE_REAPPLY_MASK & 0xFF)
    chain.write_reg(_ACTIVE_FLAGS_ADDR, flags)
    for i, value in enumerate(slot_b):
        chain.write_reg(_FILENAME_RAM_BASE + i, value)
    assert _read_main_only_filename_ram(chain) == slot_b

    # EP0 restore request: switch to A and set reapply pending.
    chain.write_reg(
        _ACTIVE_FLAGS_ADDR,
        (flags & (~_ACTIVE_PRESET_MASK & 0xFF)) | _ACTIVE_REAPPLY_MASK,
    )
    for _ in range(80):
        if not (chain.read_reg(_ACTIVE_FLAGS_ADDR) & _ACTIVE_REAPPLY_MASK):
            break
        chain.step_ticks(2_000_000)

    active_flags = chain.read_reg(_ACTIVE_FLAGS_ADDR)
    assert (active_flags & _ACTIVE_REAPPLY_MASK) == 0, (
        f"reapply bit did not clear: active_flags=0x{active_flags:02X}"
    )
    assert (active_flags & _ACTIVE_PRESET_MASK) == 0, (
        f"preset A was not restored: active_flags=0x{active_flags:02X}"
    )
    assert _read_main_only_filename_ram(chain) == slot_a, (
        "EP0 reapply restored preset A but left live filename RAM on preset B"
    )


@pytest.mark.parametrize(
    ("dirty_mask", "case"),
    [
        (_FILENAME_DIRTY_MASK, "filename-dirty"),
        (_USB_XACT_PENDING_MASK, "usb-xact-pending"),
        (_FILENAME_DIRTY_MASK | _USB_XACT_PENDING_MASK, "dirty-and-xact"),
    ],
)
def test_v32_ep0_reapply_stays_pending_until_filename_dirty_clears(
    dirty_mask: int,
    case: str,
) -> None:
    """BUG-PRESET-01: EP0 reapply must not report completion while
    filename dirty/xact bits make ``preset_load_filename`` unsafe.

    A real post-flash or HFD-adjacent interleaving can have live filename
    RAM from preset B while EP0 requests a restore to preset A.  If bit5
    or bit6 is set, V3.2 must defer readiness by keeping
    active_flags.bit7 set; clearing bit7 with B's live filename still in
    RAM makes the flasher report a complete preset A restore with stale
    visible metadata.
    """
    chain = _open_main_only_chain()
    slot_a = _filename_slot(b"EP0-REAPPLY-A")
    slot_b = _filename_slot(b"EP0-REAPPLY-B")
    _seed_main_only_filename_slot(chain, _PRESET_A_EEPROM_BASE, slot_a)
    _seed_main_only_filename_slot(chain, _PRESET_B_EEPROM_BASE, slot_b)

    # Precondition: active preset bit says B and live filename RAM is B.
    flags = chain.read_reg(_ACTIVE_FLAGS_ADDR)
    flags = (flags | _ACTIVE_PRESET_MASK) & (~_ACTIVE_REAPPLY_MASK & 0xFF)
    chain.write_reg(_ACTIVE_FLAGS_ADDR, flags)
    for i, value in enumerate(slot_b):
        chain.write_reg(_FILENAME_RAM_BASE + i, value)
    assert _read_main_only_filename_ram(chain) == slot_b

    # EP0 restore request: switch active_flags.bit2 to A and set the
    # firmware reapply bit while filename metadata is still dirty/gated.
    chain.write_reg(
        _FILENAME_DIRTY_FLAGS_ADDR,
        chain.read_reg(_FILENAME_DIRTY_FLAGS_ADDR) | dirty_mask,
    )
    chain.write_reg(
        _ACTIVE_FLAGS_ADDR,
        (flags & (~_ACTIVE_PRESET_MASK & 0xFF)) | _ACTIVE_REAPPLY_MASK,
    )

    # Give the main loop more than enough time to process the reapply
    # branch.  The old bug clears bit7 here even though it skipped
    # preset_load_filename; the fixed behavior keeps bit7 pending.
    for _ in range(80):
        chain.step_ticks(2_000_000)
        if not (chain.read_reg(_ACTIVE_FLAGS_ADDR) & _ACTIVE_REAPPLY_MASK):
            break

    active_flags = chain.read_reg(_ACTIVE_FLAGS_ADDR)
    assert active_flags & _ACTIVE_REAPPLY_MASK, (
        f"{case}: reapply must stay pending while filename dirty/xact bits "
        f"are set; active_flags=0x{active_flags:02X}, "
        f"dirty=0x{chain.read_reg(_FILENAME_DIRTY_FLAGS_ADDR):02X}"
    )
    assert (active_flags & _ACTIVE_PRESET_MASK) == 0, (
        f"{case}: EP0 preset bit should already reflect requested A; "
        f"active_flags=0x{active_flags:02X}"
    )
    assert _read_main_only_filename_ram(chain) == slot_b, (
        f"{case}: dirty/gated reapply should not clobber live host RAM yet"
    )

    # Once the filename transaction is actually clean, the same pending
    # reapply must complete and load A's EEPROM slot into live RAM.
    chain.write_reg(
        _FILENAME_DIRTY_FLAGS_ADDR,
        chain.read_reg(_FILENAME_DIRTY_FLAGS_ADDR)
        & (~(_FILENAME_DIRTY_MASK | _USB_XACT_PENDING_MASK) & 0xFF),
    )
    for _ in range(80):
        if not (chain.read_reg(_ACTIVE_FLAGS_ADDR) & _ACTIVE_REAPPLY_MASK):
            break
        chain.step_ticks(2_000_000)

    active_flags = chain.read_reg(_ACTIVE_FLAGS_ADDR)
    assert (active_flags & _ACTIVE_REAPPLY_MASK) == 0, (
        f"{case}: reapply did not complete after dirty/xact bits cleared; "
        f"active_flags=0x{active_flags:02X}"
    )
    assert _read_main_only_filename_ram(chain) == slot_a, (
        f"{case}: clean reapply did not load preset A filename RAM"
    )


def test_sim_ep0_read_past_0x10000_raises() -> None:
    """``set_pointer(0xFFFF) + read_exact(2)`` would wrap past the
    12-bit data-memory window.  The real firmware's TBLPTRH-driven
    EP0 path switches read regions there; the sim doesn't model
    that, so we raise loudly instead of silently returning the
    wrap-to-0 byte (codex LOW vs 83fb65c)."""
    chain = _open_chain()
    ep0 = make_sim_ep0(chain, unit=1)

    # Single-byte read AT 0xFFFF is fine (no wrap needed; the
    # auto-increment afterwards lands on 0x10000 but isn't read).
    ep0.set_pointer(0xFFFF)
    _ = ep0.read_exact(1)

    # Two-byte read crossing 0x10000 must raise.
    ep0.set_pointer(0xFFFF)
    with pytest.raises(ValueError, match="wrap past 0x10000"):
        ep0.read_exact(2)


def test_sim_ep0_chunked_read_past_0x10000_raises() -> None:
    """Chunked crossing: ``set_pointer(0xFFFF); read_exact(1)`` leaves
    the pointer at 0x10000; the NEXT ``read_exact(1)`` must raise
    instead of silently reading from address 0 after a mask wrap
    (codex LOW vs 805afd2)."""
    chain = _open_chain()
    ep0 = make_sim_ep0(chain, unit=1)

    ep0.set_pointer(0xFFFF)
    _ = ep0.read_exact(1)  # OK: pointer now at 0x10000

    # Without the fix, the pointer would be masked to 0x0000 and
    # this would silently read MAIN1's address-0 RAM.  With the fix
    # the wrap check fires.
    with pytest.raises(ValueError, match="wrap past 0x10000"):
        ep0.read_exact(1)


def test_sim_ep0_zero_length_read_returns_empty_bytes() -> None:
    """``_poke(addr, value, in_dir=True, read_len=0)`` matches the
    real ``DlcpEp0._poke`` behaviour of returning an empty
    ``bytes()`` rather than a single byte (codex LOW vs 83fb65c)."""
    chain = _open_chain()
    ep0 = make_sim_ep0(chain, unit=1)

    # Direct-read path with read_len=0 -> empty bytes.
    result = ep0._poke(0x05E, 0x00, in_dir=True, read_len=0)
    assert result == b"", f"expected empty bytes; got {result!r}"

    # Sanity: read_len=1 still returns one byte.
    result = ep0._poke(0x05E, 0x00, in_dir=True, read_len=1)
    assert len(result) == 1


def test_sim_ep0_can_be_used_with_existing_flasher_helpers() -> None:
    """``SimDlcpEp0`` implements the same surface (``set_pointer``,
    ``read_exact``, ``_poke``) as ``DlcpEp0``.  This lets the
    flasher's private EP0 helpers (``_ep0_read_byte``,
    ``_ep0_write_byte``, ``_ep0_or_byte``, ``_read_ep0_window``)
    work UNCHANGED when handed a ``SimDlcpEp0`` -- demonstrating
    the duck-type compatibility the integration plan needs.

    We invoke the helpers directly here.  A future commit refactors
    the flasher CLI to take an ``ep0_factory`` callable so the
    script itself can be driven by tests."""
    from dlcp_fw.flash import dlcp_main_flash as flasher

    chain = _open_chain()
    ep0 = make_sim_ep0(chain, unit=1)

    # _ep0_read_byte → set_pointer + read_exact(1)
    flags = flasher._ep0_read_byte(ep0, addr=_ACTIVE_FLAGS_ADDR)  # type: ignore[arg-type]
    assert flags == chain.read_main_reg(1, _ACTIVE_FLAGS_ADDR)

    # _ep0_or_byte → read + (maybe) write back
    SCRATCH_ADDR = 0x00D
    chain.write_main_reg(1, SCRATCH_ADDR, 0x10)
    flasher._ep0_or_byte(ep0, addr=SCRATCH_ADDR, mask=0x21)  # type: ignore[arg-type]
    assert chain.read_main_reg(1, SCRATCH_ADDR) == 0x31

    # _ep0_write_byte → _poke
    flasher._ep0_write_byte(ep0, addr=SCRATCH_ADDR, value=0x99)  # type: ignore[arg-type]
    assert chain.read_main_reg(1, SCRATCH_ADDR) == 0x99
