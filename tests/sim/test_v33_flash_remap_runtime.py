"""V3.3 assembly-side preset-B flash remap regressions.

These tests reopen the old size-ledger blocker around the duplicated
flash_read / flash_write / flash_erase preset-B remap prologues.  The
critical coverage is firmware-driven: an HFD-style HID upload to the
logical 0x5600 preset table must land in physical 0x4C00 when
``active_flags.bit2`` selects preset B.
"""

from __future__ import annotations

import pytest

from dlcp_fw.flash.dlcp_hfd_upload import (
    SLOT_PAYLOAD_SIZE,
    SLOT_SIZE,
    TABLE_SIZE,
    _build_upload_reports,
    _looks_like_upload_ack,
)
from dlcp_fw.paths import V172_CONTROL_HEX, V33_MAIN_ASM, V33_MAIN_HEX
from dlcp_fw.sim.v30_symbols import load_gpasm_symbols_for_hex

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_OK = True
    _RUST_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_OK = False
    _RUST_ERROR = exc


pytestmark = pytest.mark.dual_supported


_ACTIVE_FLAGS = 0x05E
_ACTIVE_PRESET_B = 0x04
_PRESET_A_BASE = 0x5600
_PRESET_B_BASE = 0x4C00
_FIRST_FLUSH_SIZE = 0xC0
_HID_REPORT_LEN = 64


def _require_rust() -> None:
    if not _RUST_OK:
        pytest.fail(f"rust facade not importable: {_RUST_ERROR!r}")


def _v33_hid_symbols() -> tuple[int, int]:
    symbols = load_gpasm_symbols_for_hex(V33_MAIN_HEX)
    if not symbols:
        pytest.skip("missing V3.3 gpasm listing for HID entry symbols")
    try:
        return int(symbols["main_usb_service_3a26"]), int(symbols["hid_command_dispatch"])
    except KeyError as exc:
        pytest.fail(f"missing V3.3 HID symbol in gpasm listing: {exc}")  # pragma: no cover


def _firmware_hid_report_v33(chain, unit: int, report: bytes) -> bytes:  # type: ignore[no-untyped-def]
    if len(report) != _HID_REPORT_LEN:
        raise ValueError(f"expected {_HID_REPORT_LEN}-byte report")
    service_pc, dispatch_pc = _v33_hid_symbols()
    response, dispatch_hits = chain._inner.firmware_hid_report(  # noqa: SLF001
        int(unit),
        [int(b) & 0xFF for b in report],
        20_000,
        service_pc,
        dispatch_pc,
    )
    assert dispatch_hits > 0
    return bytes(response)


def _first_flush_table() -> bytes:
    table = bytearray([0xFF] * TABLE_SIZE)
    for slot in range(_FIRST_FLUSH_SIZE // SLOT_SIZE):
        base = slot * SLOT_SIZE
        table[base : base + 4] = bytes(
            [0xA0 | slot, 0xB0 | slot, 0xC0 | slot, 0xD0 | slot]
        )
        for offset in range(SLOT_PAYLOAD_SIZE):
            table[base + 4 + offset] = (0x31 + (slot * 0x17) + offset) & 0xFF
    return bytes(table)


def test_v33_flash_remap_start_address_uses_shared_helper() -> None:
    text = V33_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    assert "preset_b_remap_start_addr:" in text
    assert "preset_b_remap_start_addr_if_b:" in text

    flash_write_body = text[text.index("flash_write:") : text.index("flash_write_stock:")]
    flash_erase_body = text[text.index("flash_erase:") : text.index("flash_erase_stock:")]
    flash_read_body = text[text.index("flash_read:") : text.index("flash_read_stock:")]

    assert "call        preset_b_remap_start_addr, 0x0" in flash_write_body
    assert "call        preset_b_remap_start_addr_if_b, 0x0" in flash_erase_body
    assert "call        preset_b_remap_start_addr, 0x0" in flash_read_body
    assert "subwf       ram_0x004" not in flash_write_body
    assert "subwf       ram_0x004" not in flash_erase_body
    assert "subwf       ram_0x004" not in flash_read_body


def test_v33_hid_flash_access_to_active_preset_b_remaps_physical_flash() -> None:
    """HID flash helpers use logical 0x5600 but physically target 0x4C00 for B.

    Cmd 0x43 proves the flash_read remap directly.  Eight HFD-style upload
    reports then fill the first 0xC0-byte staging block, forcing the firmware
    path through flash_erase / flash_write.  Distinct A/B sentinels prove the
    remap is assembly-side, not a Python model shortcut.
    """
    _require_rust()
    if not V172_CONTROL_HEX.is_file() or not V33_MAIN_HEX.is_file():
        pytest.skip("missing V1.72 / V3.3 firmware artifacts")

    chain = RustChain.from_v171_v32(
        control_hex_path=str(V172_CONTROL_HEX),
        main_hex_path=str(V33_MAIN_HEX),
    )
    chain.run_until_connected(limit=400)
    assert chain.is_connected() and not chain.is_waiting()
    chain.step_ticks(50_000_000)

    unit = 1
    core_idx = 2
    original_a = bytes((0x40 + i) & 0xFF for i in range(_FIRST_FLUSH_SIZE))
    original_b = bytes((0x80 + i) & 0xFF for i in range(_FIRST_FLUSH_SIZE))
    chain.patch_core_flash(core_idx, _PRESET_A_BASE, original_a)
    chain.patch_core_flash(core_idx, _PRESET_B_BASE, original_b)

    memread = bytearray(_HID_REPORT_LEN)
    memread[0] = 0x43
    memread[1] = 0x00
    memread[2] = _PRESET_A_BASE & 0xFF
    memread[3] = (_PRESET_A_BASE >> 8) & 0xFF
    memread[4] = 0x10

    chain.write_main_reg(
        unit,
        _ACTIVE_FLAGS,
        chain.read_main_reg(unit, _ACTIVE_FLAGS) & ~_ACTIVE_PRESET_B,
    )
    response = _firmware_hid_report_v33(chain, unit, bytes(memread))
    assert response[0] == 0x43 and response[1] == 0x00 and response[2] == 0x10
    assert response[3:19] == original_a[:0x10]

    chain.write_main_reg(
        unit,
        _ACTIVE_FLAGS,
        chain.read_main_reg(unit, _ACTIVE_FLAGS) | _ACTIVE_PRESET_B,
    )
    response = _firmware_hid_report_v33(chain, unit, bytes(memread))
    assert response[0] == 0x43 and response[1] == 0x00 and response[2] == 0x10
    assert response[3:19] == original_b[:0x10]

    table = _first_flush_table()
    for cmd, report in _build_upload_reports(table)[: _FIRST_FLUSH_SIZE // SLOT_SIZE]:
        response = _firmware_hid_report_v33(chain, unit, report)
        assert _looks_like_upload_ack(response, expected_cmd=cmd), response[:4].hex()

    after_a = chain.read_core_flash(core_idx, _PRESET_A_BASE, _FIRST_FLUSH_SIZE)
    after_b = chain.read_core_flash(core_idx, _PRESET_B_BASE, _FIRST_FLUSH_SIZE)
    assert after_a == original_a
    assert after_b == bytes([0xFF] * _FIRST_FLUSH_SIZE)
