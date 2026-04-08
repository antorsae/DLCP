"""Stateful main-unit simulation model for preset banking tests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .hexio import parse_intel_hex
from .protocol import SerialFrame


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class FlashWriteEvent:
    logical_addr: int
    physical_addr: int
    value: int


@dataclass(frozen=True)
class DspIngestEvent:
    preset_idx: int
    table_base: int
    table_sha256: str


@dataclass(frozen=True)
class UsbCmd03Event:
    subcmd: int
    payload: bytes
    response: bytes


@dataclass(frozen=True)
class PresetSwitchEvent:
    kind: str
    value: int | None = None


@dataclass
class MainUnitModel:
    name: str
    link_addr: int
    flash: bytearray
    eeprom: bytearray = field(default_factory=lambda: bytearray([0xFF] * 0x100))
    ram: bytearray = field(default_factory=lambda: bytearray([0x00] * 0x300))
    preset_idx: int = 0
    apply_count: int = 0
    rx_count: int = 0
    handled_count: int = 0
    filename_dirty: bool = False
    muted: bool = False
    flash_writes: List[FlashWriteEvent] = field(default_factory=list)
    dsp_ingest: List[DspIngestEvent] = field(default_factory=list)
    usb_cmd03_log: List[UsbCmd03Event] = field(default_factory=list)
    preset_switch_log: List[PresetSwitchEvent] = field(default_factory=list)
    tx_frames: List[SerialFrame] = field(default_factory=list)
    # Preset B address layout (V2.4-V2.8: 0x4A00/0x0C00, V3.1+: 0x4C00/0x0A00)
    _preset_b_base: int = 0x4A00
    _preset_b_remap_delta: int = 0x0C00
    _delayed_preset_switch: bool = False

    _FILENAME_LEN = 0x1E
    _FILENAME_RAM_BASE = 0x2C0
    _FILENAME_EEPROM_BASE_A = 0x60
    _FILENAME_EEPROM_BASE_B = 0x83

    @staticmethod
    def from_hex(name: str, link_addr: int, hex_path: Path) -> "MainUnitModel":
        mem: Dict[int, int] = parse_intel_hex(hex_path)
        flash = bytearray([0xFF] * 0x6000)
        eeprom = bytearray([0xFF] * 0x100)
        for addr, b in mem.items():
            if 0 <= addr < len(flash):
                flash[addr] = b
            if 0xF00000 <= addr <= 0xF000FF:
                eeprom[addr - 0xF00000] = b
        # Auto-detect preset B base: V3.1+ uses 0x4C00, earlier builds use 0x4A00.
        # V2.8 keeps the legacy bank map but enables delayed preset switching via
        # USB version 2.8. V3.1+ is detected from the 0x4C00 cloned preset window.
        preset_b_base = 0x4A00
        preset_b_delta = 0x0C00
        delayed_preset_switch = flash[0x2416] == 0x08
        if flash[0x4C00:0x4C10] == flash[0x5600:0x5610] and flash[0x4C00:0x4C04] != b"\xFF\xFF\xFF\xFF":
            preset_b_base = 0x4C00
            preset_b_delta = 0x0A00
            delayed_preset_switch = True
        model = MainUnitModel(
            name=name, link_addr=link_addr, flash=flash, eeprom=eeprom,
            _preset_b_base=preset_b_base, _preset_b_remap_delta=preset_b_delta,
            _delayed_preset_switch=delayed_preset_switch,
        )
        model.boot_load_filename_from_eeprom()
        return model

    def _accepts_route(self, route: int) -> bool:
        if (route & 0xF0) != 0xB0:
            return False
        rid = route & 0x0F
        return rid == 0 or rid == self.link_addr

    def _map_addr_for_table(self, logical_addr: int) -> int:
        if self.preset_idx != 1:
            return logical_addr
        upper = (logical_addr >> 16) & 0xFF
        high = (logical_addr >> 8) & 0xFF
        if upper != 0:
            return logical_addr
        if 0x56 <= high <= 0x5F:
            return logical_addr - self._preset_b_remap_delta
        return logical_addr

    def process_frame(self, frame: SerialFrame) -> bool:
        frame = frame.normalized()
        self.rx_count += 1
        if not self._accepts_route(frame.route):
            return False
        if frame.cmd == 0x03:
            subcmd = frame.data & 0xFF
            if subcmd == 0x02:
                self.muted = True
                self.handled_count += 1
                return True
            if subcmd == 0x03:
                self.muted = False
                self.handled_count += 1
                return True
        if frame.cmd != 0x20:
            return False
        self.set_preset(frame.data & 0x01)
        self.handled_count += 1
        return True

    def uses_delayed_preset_switch(self) -> bool:
        return self._delayed_preset_switch

    def set_preset(self, idx: int) -> None:
        normalized = 1 if idx else 0
        if normalized == self.preset_idx:
            return
        if self.filename_dirty:
            self.persist_dirty_filename_to_eeprom()
        if self.uses_delayed_preset_switch():
            was_muted = self.muted
            if not was_muted:
                self.muted = True
                self.preset_switch_log.append(PresetSwitchEvent("mute_on"))
            self.preset_switch_log.append(PresetSwitchEvent("delay_ms", 150))
            self.preset_idx = normalized
            self.preset_switch_log.append(PresetSwitchEvent("switch", normalized))
            self.boot_load_filename_from_eeprom()
            self.apply_table()
            if not was_muted:
                self.muted = False
                self.preset_switch_log.append(PresetSwitchEvent("mute_off"))
            return
        self.preset_idx = normalized
        self.boot_load_filename_from_eeprom()
        self.apply_table()

    def table_bytes(self, base: int = 0x5600) -> bytes:
        return bytes(self.flash[base : base + 0xA00])

    def table_digest(self, base: int = 0x5600) -> str:
        return sha256_hex(self.table_bytes(base))

    def apply_table(self) -> None:
        self.apply_count += 1
        base = self._preset_b_base if self.preset_idx else 0x5600
        self.dsp_ingest.append(
            DspIngestEvent(
                preset_idx=self.preset_idx,
                table_base=base,
                table_sha256=self.table_digest(base),
            )
        )

    def upload_hfd_table(self, payload_0xA00: bytes) -> None:
        if len(payload_0xA00) != 0xA00:
            raise ValueError("payload must be exactly 0xA00 bytes")
        for i, b in enumerate(payload_0xA00):
            logical = 0x5600 + i
            physical = self._map_addr_for_table(logical)
            if not (0 <= physical < len(self.flash)):
                raise RuntimeError(f"{self.name}: mapped address out of range 0x{physical:04X}")
            self.flash[physical] = b
            self.flash_writes.append(
                FlashWriteEvent(logical_addr=logical, physical_addr=physical, value=b)
            )

    def upload_hfd_profile(
        self,
        *,
        table_payload_0xA00: bytes,
        filename: str | None = None,
        persist_filename: bool = True,
    ) -> None:
        self.upload_hfd_table(table_payload_0xA00)
        if filename is None:
            return
        payload = filename.encode("ascii", errors="ignore")[: self._FILENAME_LEN]
        payload = payload + (b"\x00" * (self._FILENAME_LEN - len(payload)))
        self.usb_cmd03(0x09, payload)
        if persist_filename:
            self.persist_dirty_filename_to_eeprom()

    @staticmethod
    def _sanitize_filename_char(b: int) -> int:
        bb = b & 0xFF
        if bb in (0x00, 0xFF):
            return 0x20
        return bb

    def _set_filename_ram_bytes(self, slot: bytes) -> None:
        if len(slot) != self._FILENAME_LEN:
            raise ValueError("filename slot must be exactly 30 bytes")
        base = self._FILENAME_RAM_BASE
        self.ram[base : base + self._FILENAME_LEN] = slot

    def filename_ram_bytes(self) -> bytes:
        base = self._FILENAME_RAM_BASE
        return bytes(self.ram[base : base + self._FILENAME_LEN])

    def _filename_eeprom_base(self, preset_idx: int | None = None) -> int:
        idx = self.preset_idx if preset_idx is None else (1 if preset_idx else 0)
        return self._FILENAME_EEPROM_BASE_B if idx else self._FILENAME_EEPROM_BASE_A

    def filename_eeprom_bytes(self, preset_idx: int | None = None) -> bytes:
        base = self._filename_eeprom_base(preset_idx)
        return bytes(self.eeprom[base : base + self._FILENAME_LEN])

    def cmd03_set_filename(self, payload: bytes) -> bytes:
        slot = bytearray([0xFF] * self._FILENAME_LEN)
        for i, b in enumerate(payload[: self._FILENAME_LEN]):
            slot[i] = (b & 0xFF) or 0xFF
        self._set_filename_ram_bytes(bytes(slot))
        self.filename_dirty = True
        return b""

    def cmd03_erase_filename(self) -> bytes:
        self._set_filename_ram_bytes(bytes([0xFF] * self._FILENAME_LEN))
        self.filename_dirty = True
        return b""

    def cmd03_get_filename(self) -> bytes:
        return self.filename_ram_bytes()

    def persist_dirty_filename_to_eeprom(self) -> bool:
        if not self.filename_dirty:
            return False
        base = self._filename_eeprom_base()
        self.eeprom[base : base + self._FILENAME_LEN] = self.filename_ram_bytes()
        self.filename_dirty = False
        return True

    def boot_load_filename_from_eeprom(self, preset_idx: int | None = None) -> None:
        base = self._filename_eeprom_base(preset_idx)
        self._set_filename_ram_bytes(bytes(self.eeprom[base : base + self._FILENAME_LEN]))
        self.filename_dirty = False

    def drain_tx_frames(self) -> List[SerialFrame]:
        out = list(self.tx_frames)
        self.tx_frames.clear()
        return out

    def usb_cmd03(self, subcmd: int, payload: bytes = b"") -> bytes:
        sub = subcmd & 0xFF
        data = bytes(payload)
        if sub == 0x08:
            resp = self.cmd03_get_filename()
        elif sub == 0x09:
            resp = self.cmd03_set_filename(data)
        elif sub == 0x0A:
            resp = self.cmd03_erase_filename()
        else:
            resp = b""
        self.usb_cmd03_log.append(UsbCmd03Event(subcmd=sub, payload=data, response=resp))
        return resp
