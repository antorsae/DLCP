"""Sim-backed HID backend tests.

Exercises the ``SimHidBackend`` + ``SimUsbHub`` adapters at
``src/dlcp_fw/flash/sim_backend.py`` against a rust ``Chain.from_v171_v32``
chain.  These tests cover the cmd 0x06 / 0x03 / 0x40 / 0x41 / 0x43 HID
feature-report surface that the V3.2 release flasher uses; the EP0 path
is exercised by the sibling ``test_v32_flasher_sim_backend_ep0.py``.

The full flasher-via-sim integration test lives in
``test_v32_release_flash_sim.py``; this module gates the building blocks.
"""

from __future__ import annotations

import re

import pytest

from dlcp_fw.paths import PROJECT_ROOT, V171_CONTROL_HEX, V32_MAIN_ASM, V32_MAIN_HEX

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_OK = True
    _RUST_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_OK = False
    _RUST_ERROR = exc

from dlcp_fw.flash.sim_backend import (
    SimHidBackend,
    SimUsbDevice,
    SimUsbHub,
    install_sim_hub,
    make_sim_hub,
)
from dlcp_fw.flash import dlcp_control_flash, dlcp_main_flash, read_coeffs


pytestmark = pytest.mark.dual_supported


# RAM constants (cross-checked vs dlcp_main_flash.py).
_FILENAME_RAM_BASE = 0x2C0
_FILENAME_RAM_LEN = 0x1E
_FILENAME_DIRTY_FLAGS_ADDR = 0x0BD
_FILENAME_DIRTY_BIT = 0x20
_USB_XACT_PENDING_BIT = 0x40
_LOGICAL_VOLUME_RAM_BASE = 0x066
_COMPUTED_VOLUME_RAM_BASE = 0x06E
_INPUT_SELECT_RAM = 0x099
_INPUT_SELECT_MIRROR_RAM = 0x0B3
_SETUP_PROFILE_RAM = 0x0B8
_USER_VOLUME_MINUS_30 = (0xFF, 0xFF, 0xFF, 0xE2)
_USER_INPUT_COAX_2 = 0x03
_USER_SETUP_PROFILE_SENTINEL = 0x03

_HID_REPORT_LEN = 64
_CMD_DIAG_MEMREAD = 0x43
_DIAG_MEMREAD_REGION_EEPROM = 0x01


def test_v32_firmware_hid_entrypoint_matches_listing() -> None:
    """The rust firmware-HID facade must jump to the current V3.2 USB service."""
    lst_text = V32_MAIN_ASM.with_suffix(".lst").read_text(encoding="utf-8")
    match = re.search(
        r"^main_usb_service_3a26\s+ADDRESS\s+([0-9A-Fa-f]{8})\b",
        lst_text,
        re.MULTILINE,
    )
    assert match, "V3.2 listing has no main_usb_service_3a26 symbol"
    service_pc = int(match.group(1), 16)

    facade_src = (PROJECT_ROOT / "crates/dlcp-sim-py/src/lib.rs").read_text(
        encoding="utf-8"
    )
    assert f"MAIN_USB_SERVICE_3A26_PC: u32 = 0x{service_pc:04X}" in facade_src


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


def _read_v32_eeprom_identity_from_hex() -> tuple[int, int, int]:
    info = dlcp_main_flash.detect_static_hex_eeprom_version(
        dlcp_main_flash.parse_intel_hex(str(V32_MAIN_HEX))
    )
    assert info is not None, f"missing V3.2 EEPROM identity in {V32_MAIN_HEX}"
    return (info.major & 0xFF, info.minor & 0xFF, info.revision & 0xFF)


def _exchange(dev: SimHidBackend, payload: bytes) -> bytes:
    """Helper: write a 64-byte payload (with the 0x00 report id prefix) and
    read the next 64-byte response."""
    if len(payload) != _HID_REPORT_LEN:
        raise ValueError("payload must be 64 bytes")
    n = dev.write(b"\x00" + payload)
    assert n == _HID_REPORT_LEN + 1
    raw = dev.read(_HID_REPORT_LEN, 1000)
    if not raw:
        return b""
    assert len(raw) == _HID_REPORT_LEN
    return bytes(raw)


def test_v32_runtime_eeprom_identity_matches_release_hex_without_seed() -> None:
    """BUG-REV-01: a canonical V3.2 boot must migrate runtime EEPROM
    identity to the release tuple without test-side seeding.

    The release flasher streams app program memory only; EEPROM bytes in
    the HEX are not flashed directly.  Therefore V3.2 itself must write
    the runtime identity tuple during boot, including the release revision
    at EEPROM[0x82].
    """
    chain = _open_chain()
    expected = _read_v32_eeprom_identity_from_hex()
    for unit in (0, 1):
        actual = tuple(chain.read_main_eeprom_byte(unit, 0x80 + i) for i in range(3))
        assert actual == expected, (
            f"MAIN{unit} runtime EEPROM identity mismatch: got {actual!r}, "
            f"expected release tuple {expected!r}"
        )


def test_v32_firmware_hid_report_enters_dispatch_and_reads_eeprom() -> None:
    """Firmware-path USB HID gate: a simulated host EP1 report must be
    consumed by V3.2 ``main_usb_service_3a26`` and enter the real
    ``hid_command_dispatch`` path.

    This specifically guards against the old ``SimHidBackend`` shape,
    which answered cmd 0x43 by calling ``chain.read_main_eeprom_byte``
    directly and therefore did not exercise firmware-side USB staging,
    command dispatch, or EP1 IN response arming.
    """
    chain = _open_chain()
    expected = _read_v32_eeprom_identity_from_hex()

    payload = bytearray(_HID_REPORT_LEN)
    payload[0] = _CMD_DIAG_MEMREAD
    payload[1] = _DIAG_MEMREAD_REGION_EEPROM
    payload[2] = 0x80
    payload[3] = 0x00
    payload[4] = 0x03

    resp, dispatch_hits = chain.firmware_hid_report(1, bytes(payload))
    assert dispatch_hits > 0
    assert len(resp) == _HID_REPORT_LEN
    assert resp[0] == _CMD_DIAG_MEMREAD
    assert resp[1] == 0x00
    assert resp[2] == 0x03
    assert tuple(resp[3:6]) == expected

    # Prove the firmware EP1 buffers, not only the returned Python bytes,
    # reflect the transaction.
    assert chain.read_main_reg(1, 0x042C) == _CMD_DIAG_MEMREAD
    assert chain.read_main_reg(1, 0x040C) & 0x80
    assert chain.read_main_reg(1, 0x0410) & 0x80
    in_buf = bytes(chain.read_main_reg(1, 0x046C + i) for i in range(6))
    assert in_buf == bytes(resp[:6])


# ---------------------------------------------------------------------------
# Hub / device wiring tests
# ---------------------------------------------------------------------------


def test_sim_usb_hub_enumerates_two_devices_by_default() -> None:
    """``SimUsbHub(chain)`` exposes one HID device per simulated MAIN
    (units 0 and 1 by default), matching the typical 2x V3.2 chain."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    devs = hub.enumerate_devices(SimUsbHub.DEFAULT_VID, SimUsbHub.DEFAULT_PID)
    assert len(devs) == 2
    units_seen = {dev.serial_number for dev in devs}
    assert units_seen == {"SIM-MAIN0", "SIM-MAIN1"}
    # Default product strings show app mode for both.
    assert all("V3.2" in dev.product_string for dev in devs)


def test_sim_usb_hub_install_redirects_enumerate_devices() -> None:
    """``install_sim_hub`` overrides
    ``dlcp_control_flash.enumerate_devices`` so the flasher's existing
    helpers see the simulated devices."""
    chain = _open_chain()
    hub = make_sim_hub(chain)

    # Without install: real-hidapi path (returns whatever is plugged in,
    # potentially 0 devices on a CI box).  Just confirm the hook is None.
    assert dlcp_control_flash._ENUMERATE_DEVICES_OVERRIDE is None

    with install_sim_hub(hub):
        assert dlcp_control_flash._ENUMERATE_DEVICES_OVERRIDE is not None
        sim_devs = dlcp_control_flash.enumerate_devices(
            SimUsbHub.DEFAULT_VID, SimUsbHub.DEFAULT_PID
        )
        assert len(sim_devs) == 2

    # After exit: hook is restored.
    assert dlcp_control_flash._ENUMERATE_DEVICES_OVERRIDE is None


def test_sim_usb_hub_install_redirects_open_hid_and_make_dlcp_ep0() -> None:
    """``install_sim_hub`` also overrides ``_open_hid`` (raw HID open)
    and ``_make_dlcp_ep0`` (EP0 transport).  The flasher's helpers
    therefore consume sim-backed objects when the hub is installed."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    with install_sim_hub(hub):
        # Pick a sim device path and open HID.
        info = hub.enumerate_devices(SimUsbHub.DEFAULT_VID, SimUsbHub.DEFAULT_PID)[1]
        dev = dlcp_main_flash._open_hid(info.path)
        assert isinstance(dev, SimHidBackend)
        # Construct a sim EP0 backend.
        ep0 = dlcp_main_flash._make_dlcp_ep0(
            vid=SimUsbHub.DEFAULT_VID, pid=SimUsbHub.DEFAULT_PID, path=info.path,
        )
        # SimDlcpEp0 has unit attribute.
        assert ep0.unit == 1


# ---------------------------------------------------------------------------
# Cmd 0x06 (version probe)
# ---------------------------------------------------------------------------


def test_sim_hid_cmd06_version_matches_target_hex_version() -> None:
    """Cmd 0x06 (version probe) returns the same flag/major/minor that
    ``detect_static_hex_hid_version`` extracts from the parsed V3.2 hex."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    dev = hub.open_hid_path(hub.device_for_unit(1).path)

    # Issue cmd 0x06 with subcmd=0x01 (version).
    payload = bytearray(_HID_REPORT_LEN)
    payload[0] = 0x06
    payload[1] = 0x01
    resp = _exchange(dev, bytes(payload))
    assert dev.last_firmware_hid_dispatch_hits > 0
    assert resp[0] == 0x06
    flag, major, minor = resp[1], resp[2], resp[3]
    # V3.2 firmware: version major/minor are 3/2.  Flag is whatever the
    # firmware reports for the post-stub layer-1 version.
    assert (major, minor) == (3, 2), (
        f"V3.2 cmd 0x06 version mismatch: got major={major} minor={minor}, "
        f"expected (3, 2)"
    )
    # Sanity-check the flag matches the parsed hex's flag (couldn't
    # hardcode without coupling to the static literal).
    from dlcp_fw.flash.dlcp_main_flash import (
        detect_static_hex_hid_version, parse_intel_hex,
    )
    expected = detect_static_hex_hid_version(parse_intel_hex(str(V32_MAIN_HEX)))
    assert expected is not None
    assert flag == expected.flag
    assert major == expected.major
    assert minor == expected.minor


# ---------------------------------------------------------------------------
# Cmd 0x03 (filename WRITE / READ / ERASE)
# ---------------------------------------------------------------------------


def test_sim_hid_cmd03_write_then_read_round_trips_filename() -> None:
    """Cmd 0x03 WRITE pokes RAM 0x2C0..0x2DD, sets dirty bits 5+6.  A
    follow-up cmd 0x03 READ returns the same bytes."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    dev = hub.open_hid_path(hub.device_for_unit(1).path)

    name_bytes = b"PRESET-A-SIM-NEW"
    payload = bytearray(_HID_REPORT_LEN)
    payload[0] = 0x03
    payload[1] = 0x09  # WRITE subcmd
    # Pad to 0x1E with 0x00 (ASCII end-of-name padding for the WRITE
    # subcmd, per ``_name_slot_to_cmd03_payload``).
    payload[2 : 2 + len(name_bytes)] = name_bytes
    resp = _exchange(dev, bytes(payload))
    assert dev.last_firmware_hid_dispatch_hits > 0
    assert resp[0] == 0x03 and resp[1] == 0x09

    # Verify RAM matches what we wrote.
    for i, b in enumerate(name_bytes):
        ram = chain.read_main_reg(1, _FILENAME_RAM_BASE + i)
        assert ram == b, (
            f"RAM[{_FILENAME_RAM_BASE + i:04X}]=0x{ram:02X}, expected 0x{b:02X}"
        )
    # Dirty bits 5 + 6 should be set.
    flags = chain.read_main_reg(1, _FILENAME_DIRTY_FLAGS_ADDR)
    assert flags & _FILENAME_DIRTY_BIT, "filename_dirty_flags.5 not set"
    assert flags & _USB_XACT_PENDING_BIT, "filename_dirty_flags.6 not set"

    # READ subcmd returns the slot.
    payload[1] = 0x08  # READ
    payload[2:] = bytes(_HID_REPORT_LEN - 2)
    resp = _exchange(dev, bytes(payload))
    assert resp[0] == 0x03 and resp[1] == 0x08
    # The first len(name_bytes) bytes of the RAM slot match what we wrote.
    for i, b in enumerate(name_bytes):
        assert resp[2 + i] == b


def test_sim_hid_cmd03_erase_fills_slot_with_0xff() -> None:
    """Cmd 0x03 ERASE writes 0xFF across the whole filename slot."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    dev = hub.open_hid_path(hub.device_for_unit(1).path)

    # Pre-poke a known string so erase has something to overwrite.
    for i, b in enumerate(b"OLDNAME"):
        chain.write_main_reg(1, _FILENAME_RAM_BASE + i, b)

    payload = bytearray(_HID_REPORT_LEN)
    payload[0] = 0x03
    payload[1] = 0x0A  # ERASE subcmd
    resp = _exchange(dev, bytes(payload))
    assert dev.last_firmware_hid_dispatch_hits > 0
    assert resp[0] == 0x03 and resp[1] == 0x0A

    for i in range(_FILENAME_RAM_LEN):
        ram = chain.read_main_reg(1, _FILENAME_RAM_BASE + i)
        assert ram == 0xFF, f"RAM[{_FILENAME_RAM_BASE + i:04X}]=0x{ram:02X} after erase"


def test_sim_hid_cmd03_write_padding_maps_zero_to_0xff_matching_firmware() -> None:
    """V3.2 firmware's cmd 0x03 WRITE handler maps payload byte 0x00 to
    RAM byte 0xFF (the host's ``_name_slot_to_cmd03_payload`` converts
    0x00/0xFF padding in the source name slot to 0x00 in the payload,
    expecting the firmware to convert back).  ``SimHidBackend`` must
    mirror that conversion -- otherwise sim RAM ends up with 0x00 padding
    while real hardware would have 0xFF, and post-flash EEPROM persist
    + ``_verify_capture_overlay`` parity break.  Codex MEDIUM vs 7d16ff9.
    """
    chain = _open_chain()
    hub = make_sim_hub(chain)
    dev = hub.open_hid_path(hub.device_for_unit(1).path)

    name_bytes = b"PB-A"  # 4 chars, 26 bytes of trailing padding
    # Build payload mirroring ``_name_slot_to_cmd03_payload``: name
    # bytes verbatim, padding bytes (originally 0xFF in name_slot)
    # become 0x00.
    payload = bytearray(_HID_REPORT_LEN)
    payload[0] = 0x03
    payload[1] = 0x09  # WRITE
    payload[2 : 2 + len(name_bytes)] = name_bytes
    # payload[2 + len(name_bytes) : 2 + 0x1E] is already 0x00 from
    # bytearray init -> firmware should convert these to 0xFF in RAM.
    resp = _exchange(dev, bytes(payload))
    assert dev.last_firmware_hid_dispatch_hits > 0
    assert resp[0] == 0x03 and resp[1] == 0x09

    # Verify RAM: name bytes verbatim, padding bytes are 0xFF (NOT 0x00).
    for i, b in enumerate(name_bytes):
        ram = chain.read_main_reg(1, _FILENAME_RAM_BASE + i)
        assert ram == b, (
            f"name byte mismatch at {i}: RAM=0x{ram:02X} expected 0x{b:02X}"
        )
    for i in range(len(name_bytes), _FILENAME_RAM_LEN):
        ram = chain.read_main_reg(1, _FILENAME_RAM_BASE + i)
        assert ram == 0xFF, (
            f"padding byte at {i}: RAM=0x{ram:02X} expected 0xFF "
            f"(0x00->0xFF firmware-side conversion)"
        )


def test_sim_usb_hub_make_dlcp_ep0_default_steps_chain_for_polling_loops() -> None:
    """The hub's ``make_dlcp_ep0`` defaults ``step_ticks_per_op`` to
    100k ticks (~ 2 ms sim time) so the unmodified flasher's polling
    loops (e.g. ``_force_active_filename_persist`` with 1.5 s timeout +
    20 ms poll) actually see firmware-side state changes.  Codex HIGH
    vs 7d16ff9 (atomic ops would never let firmware run between EP0
    pokes/reads, leaving dirty bits stuck and the persist trigger
    timing out)."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    ep0 = hub.make_dlcp_ep0(
        vid=SimUsbHub.DEFAULT_VID,
        pid=SimUsbHub.DEFAULT_PID,
        path=hub.device_for_unit(1).path,
    )
    # Default step_ticks_per_op should be > 0.
    assert ep0._step_ticks_per_op == SimUsbHub.DEFAULT_STEP_TICKS_PER_EP0_OP
    assert ep0._step_ticks_per_op >= 100_000

    # Explicit step_ticks_per_op=0 still works (atomic-op test path).
    ep0_atomic = hub.make_dlcp_ep0(
        vid=SimUsbHub.DEFAULT_VID,
        pid=SimUsbHub.DEFAULT_PID,
        path=hub.device_for_unit(1).path,
        step_ticks_per_op=0,
    )
    assert ep0_atomic._step_ticks_per_op == 0


def test_sim_usb_hub_force_persist_clears_dirty_via_flasher_helpers() -> None:
    """End-to-end: the flasher's ``_force_active_filename_persist``,
    handed a sim-backed EP0 from ``hub.make_dlcp_ep0``, sees the
    firmware-side persist drive ``filename_dirty_flags`` bits 5+6 to
    zero within the default 1.5 s timeout.  Confirms the codex HIGH fix
    (default step_ticks_per_op) actually unblocks the polling path."""
    from dlcp_fw.flash.dlcp_main_flash import _force_active_filename_persist

    chain = _open_chain()
    hub = make_sim_hub(chain)

    # Set bits 5+6 (filename dirty + USB xact pending) so persist has
    # work to do.
    chain.write_main_reg(
        1, _FILENAME_DIRTY_FLAGS_ADDR,
        chain.read_main_reg(1, _FILENAME_DIRTY_FLAGS_ADDR)
        | _FILENAME_DIRTY_BIT | _USB_XACT_PENDING_BIT,
    )
    assert chain.read_main_reg(1, _FILENAME_DIRTY_FLAGS_ADDR) & (
        _FILENAME_DIRTY_BIT | _USB_XACT_PENDING_BIT
    )

    # The flasher's helper opens an EP0 internally via ``_make_dlcp_ep0``;
    # install_sim_hub redirects that to the hub which provides the step-
    # ticks default.
    with install_sim_hub(hub):
        forced = _force_active_filename_persist(
            vid=SimUsbHub.DEFAULT_VID,
            pid=SimUsbHub.DEFAULT_PID,
            path=hub.device_for_unit(1).path,
            timeout_s=2.0,
            poll_s=0.005,
        )
    assert forced is True
    flags = chain.read_main_reg(1, _FILENAME_DIRTY_FLAGS_ADDR) & 0xFF
    assert (flags & _FILENAME_DIRTY_BIT) == 0, (
        f"filename_dirty_flags.5 still set after force_persist: 0x{flags:02X}"
    )
    assert (flags & _USB_XACT_PENDING_BIT) == 0, (
        f"filename_dirty_flags.6 still set after force_persist: 0x{flags:02X}"
    )


# ---------------------------------------------------------------------------
# Cmd 0x43 (DIAG_MEMREAD)
# ---------------------------------------------------------------------------


def test_sim_hid_cmd43_flash_region_matches_chain_read_core_flash() -> None:
    """Cmd 0x43 region=0 returns the same bytes ``chain.read_core_flash``
    does for the same window."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    dev = hub.open_hid_path(hub.device_for_unit(1).path)

    addr = 0x5600  # PRESET_A_FLASH_BASE
    length = 0x10
    payload = bytearray(_HID_REPORT_LEN)
    payload[0] = 0x43
    payload[1] = 0x00  # region FLASH
    payload[2] = addr & 0xFF
    payload[3] = (addr >> 8) & 0xFF
    payload[4] = length
    resp = _exchange(dev, bytes(payload))
    assert dev.last_firmware_hid_dispatch_hits > 0
    assert resp[0] == 0x43
    assert resp[1] == 0x00, f"DIAG_MEMREAD bad status: 0x{resp[1]:02X}"
    assert resp[2] == length

    # MAIN1 -> core_idx 2.
    expected = chain.read_core_flash(2, addr, length)
    assert bytes(resp[3 : 3 + length]) == bytes(expected)


def test_sim_hid_cmd43_eeprom_region_matches_chain_read_main_eeprom() -> None:
    """Cmd 0x43 region=1 returns the same bytes ``chain.read_main_eeprom_byte``
    does for the same window.  Used by the V3.2 flasher to verify
    post-flash EEPROM filename slots."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    dev = hub.open_hid_path(hub.device_for_unit(1).path)

    addr = 0x80  # version tuple base (major/minor/revision)
    length = 0x03
    payload = bytearray(_HID_REPORT_LEN)
    payload[0] = 0x43
    payload[1] = 0x01  # region EEPROM
    payload[2] = addr & 0xFF
    payload[3] = (addr >> 8) & 0xFF
    payload[4] = length
    resp = _exchange(dev, bytes(payload))
    assert dev.last_firmware_hid_dispatch_hits > 0
    assert resp[0] == 0x43
    assert resp[1] == 0x00, f"DIAG_MEMREAD bad status: 0x{resp[1]:02X}"

    expected = bytes(chain.read_main_eeprom_byte(1, addr + i) for i in range(length))
    assert bytes(resp[3 : 3 + length]) == expected
    # We do NOT assert V3.2 identity here.  ``Chain.from_v171_v32`` seeds
    # MAIN EEPROM from the V2.3-combined fixture (per
    # ``build_seeded_main_core`` in the rust crate), so EEPROM[0x80..0x82]
    # at runtime reflects V2.3 + firmware boot-time writes -- NOT the
    # V3.2 hex's EEPROM identity.  Tests that need V3.2 identity must
    # pre-seed via ``chain.write_main_eeprom_byte`` BEFORE
    # ``run_until_connected``.


# ---------------------------------------------------------------------------
# Cmd 0x40 / 0x41 (bootloader switch + stream + verify)
# ---------------------------------------------------------------------------


def test_sim_hid_cmd40_app_to_bootloader_flips_mode() -> None:
    """App cmd 0x40 (mode-switch trigger) flips the device's mode to
    ``bootloader``; the next ``enumerate_devices`` call sees the
    bootloader product string."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    sim_dev = hub.device_for_unit(1)
    assert sim_dev.mode == "app"
    assert "V3.2" in sim_dev.product_string

    dev = hub.open_hid_path(sim_dev.path)
    # Send app cmd 0x40 with no payload.
    payload = bytearray(_HID_REPORT_LEN)
    payload[0] = 0x40
    n = dev.write(b"\x00" + bytes(payload))
    assert n == _HID_REPORT_LEN + 1
    # No response expected from the app cmd 0x40 (we mirror the real
    # device's silent reset).
    assert dev.read(_HID_REPORT_LEN, 100) == []

    # Mode flipped, product string flipped.
    assert sim_dev.mode == "bootloader"
    assert "bootl" in hub.enumerate_devices(
        SimUsbHub.DEFAULT_VID, SimUsbHub.DEFAULT_PID
    )[1].product_string


def test_sim_hid_cmd40_preserves_user_volume_and_input_settings() -> None:
    """BUG-SETTINGS-01: app cmd 0x40 writes only the bootloader marker
    and must preserve EEPROM-backed user settings."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    sim_dev = hub.device_for_unit(1)

    # Seed both persistent EEPROM bytes and live RAM mirrors to a
    # non-default state.  The hardware bug reset these to EEPROM[0..4]
    # = FF FF FF A0 01 (-96 dB, analog 1).
    for offset, value in enumerate(_USER_VOLUME_MINUS_30):
        chain.write_main_eeprom_byte(1, offset, value)
        chain.write_main_reg(1, _COMPUTED_VOLUME_RAM_BASE + 3 - offset, value)
        chain.write_main_reg(1, _LOGICAL_VOLUME_RAM_BASE + 3 - offset, value)
    chain.write_main_eeprom_byte(1, 0x04, _USER_INPUT_COAX_2)
    chain.write_main_reg(1, _INPUT_SELECT_RAM, _USER_INPUT_COAX_2)
    chain.write_main_reg(1, _INPUT_SELECT_MIRROR_RAM, _USER_INPUT_COAX_2)
    chain.write_main_eeprom_byte(1, 0x0E, _USER_SETUP_PROFILE_SENTINEL)
    chain.write_main_reg(1, _SETUP_PROFILE_RAM, _USER_SETUP_PROFILE_SENTINEL)

    dev = hub.open_hid_path(sim_dev.path)
    payload = bytearray(_HID_REPORT_LEN)
    payload[0] = 0x40
    n = dev.write(b"\x00" + bytes(payload))
    assert n == _HID_REPORT_LEN + 1
    assert dev.read(_HID_REPORT_LEN, 100) == []

    assert sim_dev.mode == "bootloader"
    assert sim_dev.last_app_to_bootloader_settings == {
        "eeprom_volume": _USER_VOLUME_MINUS_30,
        "eeprom_input": _USER_INPUT_COAX_2,
        "eeprom_setup_profile": _USER_SETUP_PROFILE_SENTINEL,
        "computed_volume": bytes(reversed(_USER_VOLUME_MINUS_30)),
        "logical_volume": bytes(reversed(_USER_VOLUME_MINUS_30)),
        "input_select": _USER_INPUT_COAX_2,
        "input_mirror": _USER_INPUT_COAX_2,
        "setup_profile": _USER_SETUP_PROFILE_SENTINEL,
    }
    assert chain.read_main_eeprom_byte(1, 0xFF) == 0x00
    assert tuple(
        chain.read_main_eeprom_byte(1, offset) for offset in range(4)
    ) == _USER_VOLUME_MINUS_30
    assert chain.read_main_eeprom_byte(1, 0x04) == _USER_INPUT_COAX_2
    assert bytes(
        chain.read_main_reg(1, _COMPUTED_VOLUME_RAM_BASE + i) for i in range(4)
    ) == bytes(reversed(_USER_VOLUME_MINUS_30))
    assert bytes(
        chain.read_main_reg(1, _LOGICAL_VOLUME_RAM_BASE + i) for i in range(4)
    ) == bytes(reversed(_USER_VOLUME_MINUS_30))
    assert chain.read_main_reg(1, _INPUT_SELECT_RAM) == _USER_INPUT_COAX_2
    assert chain.read_main_reg(1, _INPUT_SELECT_MIRROR_RAM) == _USER_INPUT_COAX_2
    assert chain.read_main_eeprom_byte(1, 0x0E) == _USER_SETUP_PROFILE_SENTINEL
    assert chain.read_main_reg(1, _SETUP_PROFILE_RAM) == _USER_SETUP_PROFILE_SENTINEL


def test_sim_hid_cmd40_stream_then_cmd41_verify_round_trips_via_flasher_crc() -> None:
    """Stream the V3.2 firmware app window (0x1000..0x5FFF) via cmd 0x40
    packets; cmd 0x41 verify with the CRC computed by
    ``dlcp_control_flash.crc_stream`` on the same bytes succeeds (resp[2]=0xAA)
    and flips mode back to app.  Confirms the sim's CRC parity with the
    real flasher's CRC."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    sim_dev = hub.device_for_unit(1)
    sim_dev.mode = "bootloader"  # skip the app switch for this unit test
    sim_dev.bootloader_stream = bytearray()
    dev = hub.open_hid_path(sim_dev.path)

    # Synthetic 0x5000-byte stream of all 0xFF -- exercises the CRC path
    # without needing the live V3.2 hex.
    stream = bytes([0xFF]) * (0x6000 - 0x1000)
    pos = 0
    while pos < len(stream):
        chunk = stream[pos : pos + 30]
        if len(chunk) < 30:
            chunk = chunk + bytes([0xFF]) * (30 - len(chunk))
        payload = bytearray(_HID_REPORT_LEN)
        payload[0] = 0x40
        payload[2 : 2 + 30] = chunk
        resp = _exchange(dev, bytes(payload))
        assert resp[0] == 0x40
        pos += 30

    # Compute expected CRC via the flasher's own crc_stream.
    from dlcp_fw.flash.dlcp_control_flash import crc_stream
    expected_crc = crc_stream(stream)
    payload = bytearray(_HID_REPORT_LEN)
    payload[0] = 0x41
    payload[4] = (expected_crc >> 8) & 0xFF
    payload[5] = expected_crc & 0xFF
    resp = _exchange(dev, bytes(payload))
    assert resp[0] == 0x41
    assert resp[2] == 0xAA, (
        f"cmd 0x41 verify failed: got resp[2]=0x{resp[2]:02X}, expected 0xAA. "
        f"(host CRC=0x{expected_crc:04X})"
    )
    # Mode flipped back to app.
    assert sim_dev.mode == "app"


def test_sim_hid_cmd41_verify_with_wrong_crc_returns_failure() -> None:
    """A cmd 0x41 verify with a deliberately-wrong CRC returns resp[2]
    != 0xAA and leaves the device in bootloader mode."""
    chain = _open_chain()
    hub = make_sim_hub(chain)
    sim_dev = hub.device_for_unit(1)
    sim_dev.mode = "bootloader"
    sim_dev.bootloader_stream = bytearray()
    dev = hub.open_hid_path(sim_dev.path)

    # No stream at all -> all zeros stream.  CRC of all-0xFF expected.
    payload = bytearray(_HID_REPORT_LEN)
    payload[0] = 0x41
    payload[4] = 0xDE  # wrong CRC hi
    payload[5] = 0xAD  # wrong CRC lo
    resp = _exchange(dev, bytes(payload))
    assert resp[0] == 0x41
    assert resp[2] != 0xAA
    # Still in bootloader mode after a failed verify.
    assert sim_dev.mode == "bootloader"
