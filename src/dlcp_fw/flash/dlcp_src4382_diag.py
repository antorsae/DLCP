#!/usr/bin/env python3
"""Read SRC4382 operator diagnostics through USB HID cmd 0x45.

This is the host side of PROPOSAL_1_SRC4382_USB_DIAGNOSTICS_IMPL.md V1a.
Firmware cmd 0x45 is intentionally tiny: each request reads one SRC4382 page-0
register.  This host tool assembles those raw reads into the human snapshot.
It sends only cmd 0x45 by default: no version probe, no cmd 0x43 memread, no
EP0 RAM reads, no current-loop traffic, and no write commands.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
import time
from typing import Iterable, Optional

from dlcp_fw.flash.dlcp_control_flash import (
    DEFAULT_PID,
    DEFAULT_VID,
    HidDeviceInfo,
    enumerate_devices,
)
from dlcp_fw.flash.dlcp_main_flash import (
    _exchange_report,
    _mk_report,
    _open_hid,
    _pick_device,
)


CMD45 = 0x45
CMD45_PAYLOAD_LEN = 0x23
CMD45_SCHEMA_V1 = 0x01
CMD45_FLAG_PC_PD_REQUEST = 0x02
CMD45_FLAG_RATIO_REQUEST = 0x04
CMD45_REQ_FLAGS_ALLOWED = CMD45_FLAG_PC_PD_REQUEST | CMD45_FLAG_RATIO_REQUEST
DLCP_RED_CLOCK_HZ = 24_000_000.0
DLCP_ASSUMED_OUTPUT_DIVIDER = 256
DLCP_ASSUMED_OUTPUT_RATE_HZ = DLCP_RED_CLOCK_HZ / DLCP_ASSUMED_OUTPUT_DIVIDER
DLCP_ASSUMED_OUTPUT_RATE_BASIS = "24.000 MHz / 256"

STATUS_NAMES = {
    0x00: "ok",
    0x01: "i2c_fail",
    0x02: "unsupported",
    0x03: "bad_request",
    0x04: "partial",
}

CMD45_RAW_READ_REGS = (
    0x03,
    0x04,
    0x05,
    0x06,
    0x07,
    0x08,
    0x09,
    0x0A,
    0x0D,
    0x0E,
    0x12,
    0x13,
    0x14,
    0x15,
    0x2D,
    0x2E,
    0x2F,
)
CMD45_RAW_RATIO_REGS = (0x32, 0x33)
CMD45_RAW_PC_PD_REGS = (0x29, 0x2A, 0x2B, 0x2C)

SNAPSHOT_FLAG_USEFUL = 0x01
SNAPSHOT_FLAG_PARTIAL = 0x02
SNAPSHOT_FLAG_PC_PD_PRESENT = 0x04
SNAPSHOT_FLAG_RATIO_PRESENT = 0x08
SNAPSHOT_FLAG_STALE = 0x10
SNAPSHOT_FLAG_PENDING = 0x20
SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT = 0x40

LOCK_NAMES = {
    0x00: "locked",
    0x01: "unlocked",
    0x02: "estimator_hole",
    0xFF: "unknown",
}

PAYLOAD_NAMES = {
    0x00: "pcm",
    0x01: "non_pcm",
    0x02: "dts",
    0xFF: "unknown",
}

RXCKR_NAMES = {
    0x00: "not_determined",
    0x01: "128fs",
    0x02: "256fs",
    0x03: "512fs",
    0xFF: "unknown",
}

PC_TYPE_NAMES = {
    0x01: "dolby_ac3",
    0x0B: "dts_type_i",
    0x0C: "dts_type_ii",
    0x0D: "dts_type_iii",
    0xFF: "unknown",
}

PC_TYPE_LABELS = {
    0x00: "Null",
    0x01: "Dolby AC-3",
    0x03: "Pause",
    0x04: "MPEG-1 Layer 1",
    0x05: "MPEG-1 Layer 2/3 or MPEG-2 no ext",
    0x06: "MPEG-2 data with extension",
    0x07: "MPEG-2 AAC ADTS",
    0x08: "MPEG-2 Layer 1 low rate",
    0x09: "MPEG-2 Layer 2/3 low rate",
    0x0B: "DTS Type 1",
    0x0C: "DTS Type 2",
    0x0D: "DTS Type 3",
    0x0E: "ATRAC",
    0x0F: "ATRAC2/3",
}

ERROR_BIT_NAMES = (
    "unlock",
    "bipolarity",
    "parity",
    "validity",
    "channel_status_crc",
    "q_channel_crc",
    "oslip",
    "q_channel_change",
)

RX_LABELS = ("RX1", "RX2", "RX3", "RX4")
ROUTE_PROFILES = {
    1: ("S/PDIF", 0x09, 0x70),
    2: ("USB Audio", 0x0A, 0xB0),
    3: ("AES", 0x08, 0x30),
    4: ("Optical", 0x0B, 0xF0),
}
PORT_DATA_FORMAT_LABELS = {
    0x00: "24-bit left-justified",
    0x01: "24-bit I2S",
    0x02: "unused",
    0x03: "unused",
    0x04: "16-bit right-justified",
    0x05: "18-bit right-justified",
    0x06: "20-bit right-justified",
    0x07: "24-bit right-justified",
}
PORT_OUTPUT_LABELS = {
    0x00: "self",
    0x01: "other port",
    0x02: "DIR",
    0x03: "SRC",
}
PORT_CLOCK_LABELS = {
    0x00: "MCLK 24MHz",
    0x01: "RXCKI",
    0x02: "RXCKO",
    0x03: "reserved",
}
PORT_DIVIDERS = {
    0x00: 128,
    0x01: 256,
    0x02: 384,
    0x03: 512,
}
DIT_INPUT_LABELS = {
    0x00: "Port A",
    0x01: "Port B",
    0x02: "DIR",
    0x03: "SRC",
}
DIT_CLOCK_LABELS = {
    0x00: "MCLK 24MHz",
    0x01: "RXCKO",
}
TXCUS_LABELS = {
    0x00: "disabled",
    0x01: "host",
    0x02: "DIR RA",
    0x03: "host+DIR RA",
}
RXCKO_DIVIDERS = {
    0x00: "passthrough",
    0x01: "/2",
    0x02: "/4",
    0x03: "/8",
}
SRC_INPUT_LABELS = {
    0x00: "Port A",
    0x01: "Port B",
    0x02: "DIR",
    0x03: "reserved",
}
SRC_REF_CLOCK_LABELS = {
    0x00: "MCLK 24MHz",
    0x01: "RXCKI",
    0x02: "RXCKO",
    0x03: "reserved",
}
DEEMPH_LABELS = {
    0x00: "off",
    0x01: "48k",
    0x02: "44.1k",
    0x03: "32k",
}
PREBUFFER_LABELS = {
    0x00: "64 samples",
    0x01: "32 samples",
    0x02: "16 samples",
    0x03: "8 samples",
}
WORD_LENGTH_LABELS = {
    0x00: "24-bit",
    0x01: "20-bit",
    0x02: "18-bit",
    0x03: "16-bit",
}
KNOWN_SAMPLE_RATES_HZ = (
    (32_000.0, "32 kHz"),
    (44_100.0, "44.1 kHz"),
    (48_000.0, "48 kHz"),
    (88_200.0, "88.2 kHz"),
    (93_750.0, "93.75 kHz DLCP native"),
    (96_000.0, "96 kHz"),
    (176_400.0, "176.4 kHz"),
    (192_000.0, "192 kHz"),
)


@dataclasses.dataclass(frozen=True)
class Src4382Snapshot:
    """Parsed schema-1 cmd 0x45 response."""

    status: int
    payload_len: int
    schema: int
    snapshot_flags: int
    selected_rx: int
    source_route: int
    reg0d: int
    reg08: int
    reg12: int
    reg13: int
    reg14: int
    reg15: int
    reg32: int
    reg33: int
    reg2d: int
    reg2e: int
    reg2f: int
    decoded_lock: int
    decoded_payload: int
    decoded_pc_type: int
    error_bits: int
    reg03: int
    reg04: int
    reg05: int
    reg06: int
    reg07: int
    reg09: int
    reg0a: int
    reg0e: int
    extension_reserved: bytes
    pc_high: int
    pc_low: int
    pd_high: int
    pd_low: int
    raw_response: bytes

    @property
    def status_name(self) -> str:
        return STATUS_NAMES[self.status]

    @property
    def useful(self) -> bool:
        return bool(self.snapshot_flags & SNAPSHOT_FLAG_USEFUL)

    @property
    def partial(self) -> bool:
        return bool(self.snapshot_flags & SNAPSHOT_FLAG_PARTIAL)

    @property
    def stale(self) -> bool:
        return bool(self.snapshot_flags & SNAPSHOT_FLAG_STALE)

    @property
    def job_pending(self) -> bool:
        return bool(self.snapshot_flags & SNAPSHOT_FLAG_PENDING)

    @property
    def pc_pd_present(self) -> bool:
        return bool(self.snapshot_flags & SNAPSHOT_FLAG_PC_PD_PRESENT)

    @property
    def ratio_present(self) -> bool:
        return bool(self.snapshot_flags & SNAPSHOT_FLAG_RATIO_PRESENT)

    @property
    def clock_status_present(self) -> bool:
        return bool(self.snapshot_flags & SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT)

    @property
    def lock_name(self) -> str:
        return LOCK_NAMES[self.decoded_lock]

    @property
    def payload_name(self) -> str:
        return PAYLOAD_NAMES[self.decoded_payload]

    @property
    def rxckr_name(self) -> str:
        return RXCKR_NAMES.get(self.reg13 & 0xFF, f"0x{self.reg13:02X}")

    @property
    def pc_type_name(self) -> str:
        if self.decoded_pc_type == 0xFF:
            return "unknown"
        return PC_TYPE_NAMES.get(
            self.decoded_pc_type & 0x1F,
            f"0x{self.decoded_pc_type & 0x1F:02X}",
        )

    @property
    def ratio(self) -> Optional[float]:
        if not self.ratio_present or 0xFF in (self.reg32, self.reg33):
            return None
        integer = (self.reg32 >> 3) & 0x1F
        frac = ((self.reg32 & 0x07) << 8) | self.reg33
        return integer + (frac / 2048.0)

    @property
    def error_names(self) -> tuple[str, ...]:
        if self.error_bits == 0xFF:
            return ("unknown",)
        return tuple(
            name for bit, name in enumerate(ERROR_BIT_NAMES)
            if self.error_bits & (1 << bit)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status_name,
            "status_raw": self.status,
            "payload_len": self.payload_len,
            "schema": self.schema,
            "snapshot_flags": self.snapshot_flags,
            "flags": {
                "useful": self.useful,
                "partial": self.partial,
                "pc_pd_present": self.pc_pd_present,
                "ratio_present": self.ratio_present,
                "stale": self.stale,
                "job_pending": self.job_pending,
                "clock_status_present": self.clock_status_present,
            },
            "selected_rx": None if self.selected_rx == 0xFF else self.selected_rx,
            "source_route": None if self.source_route == 0xFF else self.source_route,
            "registers": {
                "03": self.reg03,
                "04": self.reg04,
                "05": self.reg05,
                "06": self.reg06,
                "07": self.reg07,
                "0d": self.reg0d,
                "08": self.reg08,
                "09": self.reg09,
                "0a": self.reg0a,
                "0e": self.reg0e,
                "12": self.reg12,
                "13": self.reg13,
                "14": self.reg14,
                "15": self.reg15,
                "32": self.reg32,
                "33": self.reg33,
                "2d": self.reg2d,
                "2e": self.reg2e,
                "2f": self.reg2f,
            },
            "decoded": {
                "lock": self.lock_name,
                "payload": self.payload_name,
                "rxckr": self.rxckr_name,
                "pc_type": self.pc_type_name,
                "ratio": self.ratio,
                "errors": list(self.error_names),
                "clock_status": _clock_status_dict(self),
            },
            "pc_pd": (
                {
                    "pc_high": self.pc_high,
                    "pc_low": self.pc_low,
                    "pd_high": self.pd_high,
                    "pd_low": self.pd_low,
                }
                if self.pc_pd_present
                else None
            ),
            "raw_response_hex": self.raw_response.hex(),
        }


@dataclasses.dataclass(frozen=True)
class Src4382DeviceReport:
    info: HidDeviceInfo
    snapshot: Src4382Snapshot
    label: Optional[str] = None

    def to_dict(self, *, show_path: bool = False) -> dict[str, object]:
        path = _format_path(self.info.path, show_path=show_path)
        return {
            "label": self.label,
            "hid_path": path,
            "vendor_id": self.info.vendor_id,
            "product_id": self.info.product_id,
            "manufacturer_string": self.info.manufacturer_string,
            "product_string": self.info.product_string,
            "serial_number": self.info.serial_number,
            "snapshot": self.snapshot.to_dict(),
        }


@dataclasses.dataclass(frozen=True)
class Cmd45RawRead:
    status: int
    register: int
    value: int
    raw_response: bytes


def _format_path(path: Optional[bytes], *, show_path: bool = False) -> Optional[str]:
    if path is None:
        return None
    if show_path:
        return path.decode("utf-8", errors="replace")
    digest = hashlib.sha256(path).hexdigest()[:10]
    return f"<hid:{digest}>"


def _response_base(resp: bytes) -> int:
    if len(resp) >= 65 and resp[0] == 0x00 and resp[1] == CMD45:
        return 1
    if len(resp) >= 2 and resp[0] == 0x00 and resp[1] == CMD45:
        return 1
    if len(resp) >= 1 and resp[0] == CMD45:
        return 0
    got = resp[1] if len(resp) >= 2 and resp[0] == 0x00 else (resp[0] if resp else 0)
    raise RuntimeError(f"unexpected cmd 0x45 echo: 0x{got:02X}")


def parse_cmd45_raw_read_response(resp: bytes, *, expected_reg: Optional[int] = None) -> Cmd45RawRead:
    """Parse the compact raw-register cmd 0x45 response."""

    base = _response_base(resp)
    if len(resp) < base + 4:
        raise RuntimeError(
            f"short cmd 0x45 raw-read response: {len(resp)} bytes "
            f"(need at least {base + 4})"
        )
    status = resp[base + 1]
    if status not in STATUS_NAMES:
        raise RuntimeError(f"cmd 0x45 raw-read unknown status byte: 0x{status:02X}")
    reg = resp[base + 2]
    if expected_reg is not None and reg != (expected_reg & 0xFF):
        raise RuntimeError(
            f"cmd 0x45 raw-read register echo mismatch: got 0x{reg:02X}, "
            f"expected 0x{expected_reg & 0xFF:02X}"
        )
    return Cmd45RawRead(
        status=status,
        register=reg,
        value=resp[base + 3],
        raw_response=bytes(resp[base : base + 64]) if len(resp) >= base + 64 else bytes(resp[base:]),
    )


def _derive_selected_rx(selected_rx: int, reg0d: int) -> int:
    if selected_rx != 0xFF or reg0d == 0xFF:
        return selected_rx
    return reg0d & 0x03


def _derive_lock(decoded_lock: int, reg14: int, reg13: int) -> int:
    if decoded_lock != 0xFF:
        return decoded_lock
    if reg14 == 0xFF:
        return 0xFF
    if reg14 & 0x04:
        return 0x01
    if reg13 == 0xFF:
        return 0xFF
    if reg13 == 0x00:
        return 0x02
    return 0x00


def _derive_payload(decoded_payload: int, reg12: int) -> int:
    if decoded_payload != 0xFF or reg12 == 0xFF:
        return decoded_payload
    if reg12 & 0x02:
        return 0x02
    if reg12 & 0x01:
        return 0x01
    return 0x00


def _derive_pc_type(decoded_pc_type: int, pc_low: int) -> int:
    if decoded_pc_type != 0xFF or pc_low == 0xFF:
        return decoded_pc_type
    return pc_low & 0x1F


def _derive_error_bits(error_bits: int, reg14: int, reg15: int) -> int:
    if error_bits != 0xFF:
        return error_bits
    if 0xFF in (reg14, reg15):
        return 0xFF
    out = 0x00
    for source_bit, dest_bit in (
        (2, 0),
        (4, 1),
        (6, 2),
        (5, 3),
        (7, 4),
        (1, 5),
        (3, 7),
    ):
        if reg14 & (1 << source_bit):
            out |= 1 << dest_bit
    if reg15 & 0x01:
        out |= 1 << 6
    return out


def _derive_source_route(reg0d: int, reg08: int) -> int:
    for route, (_label, expected_0d, expected_08) in ROUTE_PROFILES.items():
        if reg0d == expected_0d and reg08 == expected_08:
            return route
    return 0xFF


def _raw_read_values_to_snapshot(
    reads: dict[int, Cmd45RawRead],
    *,
    include_pc_pd: bool,
    include_ratio: bool,
) -> Src4382Snapshot:
    def value(reg: int) -> int:
        read = reads.get(reg)
        if read is None or read.status != 0:
            return 0xFF
        return read.value & 0xFF

    failures = [read for read in reads.values() if read.status != 0]
    flags = SNAPSHOT_FLAG_USEFUL
    status = 0x00
    if failures:
        status = 0x01
        flags |= SNAPSHOT_FLAG_PARTIAL

    extension_regs = tuple(value(reg) for reg in (0x03, 0x04, 0x05, 0x06, 0x07, 0x09, 0x0A, 0x0E))
    if all(v != 0xFF for v in extension_regs):
        flags |= SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT
    else:
        extension_regs = (0xFF,) * 8

    reg32, reg33 = value(0x32), value(0x33)
    if include_ratio and 0xFF not in (reg32, reg33):
        flags |= SNAPSHOT_FLAG_RATIO_PRESENT
    else:
        reg32, reg33 = 0xFF, 0xFF

    pc_pd = tuple(value(reg) for reg in CMD45_RAW_PC_PD_REGS)
    if include_pc_pd and all(v != 0xFF for v in pc_pd):
        flags |= SNAPSHOT_FLAG_PC_PD_PRESENT
    else:
        pc_pd = (0xFF, 0xFF, 0xFF, 0xFF)

    reg0d = value(0x0D)
    reg08 = value(0x08)
    reg12 = value(0x12)
    reg13 = value(0x13)
    reg14 = value(0x14)
    reg15 = value(0x15)
    selected_rx = _derive_selected_rx(0xFF, reg0d)
    decoded_lock = _derive_lock(0xFF, reg14, reg13)
    decoded_payload = _derive_payload(0xFF, reg12)
    decoded_pc_type = _derive_pc_type(0xFF, pc_pd[1])
    error_bits = _derive_error_bits(0xFF, reg14, reg15)
    source_route = _derive_source_route(reg0d, reg08)

    body = bytearray(64)
    body[0] = CMD45
    body[1] = status
    body[2] = CMD45_PAYLOAD_LEN
    body[3] = CMD45_SCHEMA_V1
    body[4] = flags
    body[5] = 0xFF
    body[6] = source_route
    body[7] = reg0d
    body[8] = reg08
    body[9] = reg12
    body[10] = reg13
    body[11] = reg14
    body[12] = reg15
    body[13] = reg32
    body[14] = reg33
    body[15] = value(0x2D)
    body[16] = value(0x2E)
    body[17] = value(0x2F)
    body[18] = 0xFF
    body[19] = 0xFF
    body[20] = 0xFF
    body[21] = 0xFF
    if flags & SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT:
        body[22:30] = bytes(extension_regs)
        body[30:34] = b"\xFF" * 4
    else:
        body[22:34] = b"\xFF" * 12
    body[34:38] = bytes(pc_pd)

    return Src4382Snapshot(
        status=status,
        payload_len=CMD45_PAYLOAD_LEN,
        schema=CMD45_SCHEMA_V1,
        snapshot_flags=flags,
        selected_rx=selected_rx,
        source_route=source_route,
        reg0d=reg0d,
        reg08=reg08,
        reg12=reg12,
        reg13=reg13,
        reg14=reg14,
        reg15=reg15,
        reg32=reg32,
        reg33=reg33,
        reg2d=body[15],
        reg2e=body[16],
        reg2f=body[17],
        decoded_lock=decoded_lock,
        decoded_payload=decoded_payload,
        decoded_pc_type=decoded_pc_type,
        error_bits=error_bits,
        reg03=extension_regs[0],
        reg04=extension_regs[1],
        reg05=extension_regs[2],
        reg06=extension_regs[3],
        reg07=extension_regs[4],
        reg09=extension_regs[5],
        reg0a=extension_regs[6],
        reg0e=extension_regs[7],
        extension_reserved=b"\xFF" * 4,
        pc_high=pc_pd[0],
        pc_low=pc_pd[1],
        pd_high=pc_pd[2],
        pd_low=pc_pd[3],
        raw_response=bytes(body),
    )


def parse_cmd45_src4382_response(resp: bytes) -> Src4382Snapshot:
    """Parse and validate a cmd 0x45 schema-1 response."""

    base = _response_base(resp)
    need = base + 64
    if len(resp) < base + 38:
        raise RuntimeError(
            f"short cmd 0x45 response: {len(resp)} bytes "
            f"(need at least {base + 38})"
        )
    status = resp[base + 1]
    if status not in STATUS_NAMES:
        raise RuntimeError(f"cmd 0x45 unknown status byte: 0x{status:02X}")
    payload_len = resp[base + 2]
    if payload_len != CMD45_PAYLOAD_LEN:
        raise RuntimeError(
            f"cmd 0x45 payload_len mismatch: got 0x{payload_len:02X}, "
            f"expected 0x{CMD45_PAYLOAD_LEN:02X}"
        )
    schema = resp[base + 3]
    if schema != CMD45_SCHEMA_V1:
        raise RuntimeError(
            f"cmd 0x45 schema mismatch: got 0x{schema:02X}, "
            f"expected 0x{CMD45_SCHEMA_V1:02X}"
        )
    flags = resp[base + 4]
    if flags & 0x80:
        raise RuntimeError(f"cmd 0x45 reserved snapshot flag set: 0x{flags:02X}")

    extension_regs = tuple(resp[base + 22 : base + 30])
    extension_reserved = bytes(resp[base + 30 : base + 34])
    if flags & SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT:
        if any(v == 0xFF for v in extension_regs):
            raise RuntimeError(
                "cmd 0x45 clock/status extension flag set with 0xFF register byte"
            )
        if extension_reserved != (b"\xFF" * 4):
            raise RuntimeError("cmd 0x45 extension reserved bytes must be 0xFF")
    elif bytes(resp[base + 22 : base + 34]) != (b"\xFF" * 12):
        raise RuntimeError("cmd 0x45 extension bytes present without clock/status flag")
    tail = bytes(resp[base + 38 : need]) if len(resp) >= need else b""
    if tail and any(tail):
        raise RuntimeError("cmd 0x45 reserved tail bytes must be zero")

    selected_rx_raw = resp[base + 5]
    if selected_rx_raw not in (0x00, 0x01, 0x02, 0x03, 0xFF):
        raise RuntimeError(
            f"cmd 0x45 selected_rx out of range: 0x{selected_rx_raw:02X}"
        )
    decoded_lock_raw = resp[base + 18]
    if decoded_lock_raw not in LOCK_NAMES:
        raise RuntimeError(
            f"cmd 0x45 decoded_lock out of range: 0x{decoded_lock_raw:02X}"
        )
    decoded_payload_raw = resp[base + 19]
    if decoded_payload_raw not in PAYLOAD_NAMES:
        raise RuntimeError(
            f"cmd 0x45 decoded_payload out of range: 0x{decoded_payload_raw:02X}"
        )
    decoded_pc_type_raw = resp[base + 20]
    if decoded_pc_type_raw != 0xFF and decoded_pc_type_raw > 0x1F:
        raise RuntimeError(
            f"cmd 0x45 decoded_pc_type out of range: 0x{decoded_pc_type_raw:02X}"
        )

    pc_pd = tuple(resp[base + 34 : base + 38])
    if flags & SNAPSHOT_FLAG_PC_PD_PRESENT:
        if any(v == 0xFF for v in pc_pd):
            raise RuntimeError("cmd 0x45 PC/PD-present flag set with 0xFF PC/PD byte")
    elif pc_pd != (0xFF, 0xFF, 0xFF, 0xFF):
        raise RuntimeError("cmd 0x45 PC/PD bytes present without PC/PD flag")
    if flags & SNAPSHOT_FLAG_RATIO_PRESENT and 0xFF in (resp[base + 13], resp[base + 14]):
        raise RuntimeError("cmd 0x45 ratio-present flag set with 0xFF ratio byte")
    if status == 0 and flags & (SNAPSHOT_FLAG_PARTIAL | SNAPSHOT_FLAG_STALE | SNAPSHOT_FLAG_PENDING):
        raise RuntimeError("cmd 0x45 status OK cannot be partial/stale/pending")

    reg0d = resp[base + 7]
    reg12 = resp[base + 9]
    reg13 = resp[base + 10]
    reg14 = resp[base + 11]
    reg15 = resp[base + 12]
    selected_rx = _derive_selected_rx(selected_rx_raw, reg0d)
    decoded_lock = _derive_lock(decoded_lock_raw, reg14, reg13)
    decoded_payload = _derive_payload(decoded_payload_raw, reg12)
    decoded_pc_type = _derive_pc_type(decoded_pc_type_raw, pc_pd[1])
    error_bits = _derive_error_bits(resp[base + 21], reg14, reg15)

    return Src4382Snapshot(
        status=status,
        payload_len=payload_len,
        schema=schema,
        snapshot_flags=flags,
        selected_rx=selected_rx,
        source_route=resp[base + 6],
        reg0d=reg0d,
        reg08=resp[base + 8],
        reg12=reg12,
        reg13=reg13,
        reg14=reg14,
        reg15=reg15,
        reg32=resp[base + 13],
        reg33=resp[base + 14],
        reg2d=resp[base + 15],
        reg2e=resp[base + 16],
        reg2f=resp[base + 17],
        decoded_lock=decoded_lock,
        decoded_payload=decoded_payload,
        decoded_pc_type=decoded_pc_type,
        error_bits=error_bits,
        reg03=extension_regs[0] if flags & SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT else 0xFF,
        reg04=extension_regs[1] if flags & SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT else 0xFF,
        reg05=extension_regs[2] if flags & SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT else 0xFF,
        reg06=extension_regs[3] if flags & SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT else 0xFF,
        reg07=extension_regs[4] if flags & SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT else 0xFF,
        reg09=extension_regs[5] if flags & SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT else 0xFF,
        reg0a=extension_regs[6] if flags & SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT else 0xFF,
        reg0e=extension_regs[7] if flags & SNAPSHOT_FLAG_CLOCK_STATUS_PRESENT else 0xFF,
        extension_reserved=extension_reserved,
        pc_high=pc_pd[0],
        pc_low=pc_pd[1],
        pd_high=pc_pd[2],
        pd_low=pc_pd[3],
        raw_response=bytes(resp[base : base + 64]) if len(resp) >= base + 64 else bytes(resp[base:]),
    )


def make_cmd45_request(reg: int) -> bytes:
    """Build a compact cmd 0x45 raw page-0 register-read report."""

    report = _mk_report(CMD45)
    report[1] = reg & 0xFF
    return bytes(report)


def _probe_cmd45_reg(
    dev,
    reg: int,
    *,
    timeout_ms: int = 1000,
) -> Cmd45RawRead:
    report = make_cmd45_request(reg)
    resp = _exchange_report(dev, report, timeout_ms=timeout_ms)
    return parse_cmd45_raw_read_response(resp, expected_reg=reg)


def query_src4382_snapshot(
    dev,
    *,
    timeout_ms: int = 1000,
    include_pc_pd: bool = True,
    include_ratio: bool = True,
    wait: bool = True,
) -> Src4382Snapshot:
    """Query raw cmd 0x45 register reads and assemble a host-side snapshot."""

    _ = wait  # Kept for CLI/API compatibility; raw reads are synchronous.
    regs = list(CMD45_RAW_READ_REGS)
    if include_ratio:
        regs.extend(CMD45_RAW_RATIO_REGS)
    if include_pc_pd:
        regs.extend(CMD45_RAW_PC_PD_REGS)
    reads: dict[int, Cmd45RawRead] = {}
    for reg in regs:
        reads[reg] = _probe_cmd45_reg(dev, reg, timeout_ms=timeout_ms)
    return _raw_read_values_to_snapshot(
        reads,
        include_pc_pd=include_pc_pd,
        include_ratio=include_ratio,
    )


def query_device(
    info: HidDeviceInfo,
    *,
    timeout_ms: int = 1000,
    include_pc_pd: bool = True,
    include_ratio: bool = True,
    wait: bool = True,
    label: Optional[str] = None,
) -> Src4382DeviceReport:
    if info.path is None:
        raise RuntimeError("HID device has no path")
    dev = _open_hid(info.path)
    try:
        snapshot = query_src4382_snapshot(
            dev,
            timeout_ms=timeout_ms,
            include_pc_pd=include_pc_pd,
            include_ratio=include_ratio,
            wait=wait,
        )
    finally:
        try:
            dev.close()
        except Exception:
            pass
    return Src4382DeviceReport(info=info, snapshot=snapshot, label=label)


def query_one(
    *,
    vid: int = DEFAULT_VID,
    pid: int = DEFAULT_PID,
    path: Optional[bytes],
    timeout_ms: int = 1000,
    include_pc_pd: bool = True,
    include_ratio: bool = True,
    wait: bool = True,
    label: Optional[str] = None,
) -> Src4382DeviceReport:
    info = _pick_device(vid, pid, path)
    return query_device(
        info,
        timeout_ms=timeout_ms,
        include_pc_pd=include_pc_pd,
        include_ratio=include_ratio,
        wait=wait,
        label=label,
    )


def query_all(
    *,
    vid: int = DEFAULT_VID,
    pid: int = DEFAULT_PID,
    timeout_ms: int = 1000,
    include_pc_pd: bool = True,
    include_ratio: bool = True,
    wait: bool = True,
    label: Optional[str] = None,
) -> list[Src4382DeviceReport]:
    reports: list[Src4382DeviceReport] = []
    for idx, info in enumerate(enumerate_devices(vid, pid), 1):
        reports.append(
            query_device(
                info,
                timeout_ms=timeout_ms,
                include_pc_pd=include_pc_pd,
                include_ratio=include_ratio,
                wait=wait,
                label=label or f"main{idx}",
            )
        )
    if not reports:
        raise RuntimeError("no matching DLCP HID devices found")
    return reports


def _format_reg(value: int) -> str:
    return "n/a" if value == 0xFF else f"0x{value:02X}"


def _format_word(high: int, low: int) -> str:
    if 0xFF in (high, low):
        return "n/a"
    return f"0x{high:02X}{low:02X}"


def _rx_label(value: int) -> str:
    if 0 <= value < len(RX_LABELS):
        return RX_LABELS[value]
    return "unknown"


def _on_off(value: bool) -> str:
    return "on" if value else "off"


def _format_rate_hz(rate_hz: float) -> str:
    return f"{rate_hz / 1000.0:.3f} kHz"


def _nearest_sample_rate_label(rate_hz: float) -> Optional[str]:
    for nominal_hz, label in KNOWN_SAMPLE_RATES_HZ:
        if abs(rate_hz - nominal_hz) <= max(150.0, nominal_hz * 0.002):
            return label
    return None


def _decode_reg0d(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    rx = _rx_label(value & 0x03)
    ref = "MCLK 24MHz" if value & 0x08 else "RXCKI"
    transfer = "held" if value & 0x10 else "live"
    return f"RXMUX={rx}; DIR ref={ref}; C/U transfer={transfer}"


def _decode_reg08(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    byp = _rx_label((value >> 6) & 0x03)
    aes = "bypass" if value & 0x20 else "DIT"
    line = "bypass" if value & 0x10 else "DIT"
    return (
        f"bypass={byp}; AESOUT={aes}; line={line}; "
        f"txmute={_on_off(bool(value & 0x02))}; "
        f"txoff={_on_off(bool(value & 0x01))}"
    )


def _format_divider(div_code: int) -> str:
    divider = PORT_DIVIDERS[div_code & 0x03]
    return f"/{divider}"


def _decode_port_control1(value: int, *, port: str) -> str:
    if value == 0xFF:
        return "n/a"
    output = PORT_OUTPUT_LABELS[(value >> 4) & 0x03]
    if output == "self":
        output = f"Port {port} input"
    elif output == "other port":
        output = "Port B input" if port == "A" else "Port A input"
    mode = "master" if value & 0x08 else "slave"
    fmt = PORT_DATA_FORMAT_LABELS[value & 0x07]
    mute = _on_off(bool(value & 0x40))
    return f"mode={mode}; out={output}; fmt={fmt}; mute={mute}"


def _decode_port_control2(value: int, *, port: str) -> str:
    if value == 0xFF:
        return "n/a"
    clock = PORT_CLOCK_LABELS[(value >> 2) & 0x03]
    divider = _format_divider(value & 0x03)
    return f"clock={clock}; LRCK{port}={divider}"


def _decode_reg07(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    clock = DIT_CLOCK_LABELS[(value >> 7) & 0x01]
    divider = _format_divider((value >> 5) & 0x03)
    source = DIT_INPUT_LABELS[(value >> 3) & 0x03]
    return (
        f"clock={clock}; frame={divider}; input={source}; "
        f"BLS={'out' if value & 0x04 else 'in'}; "
        f"valid={_on_off(bool(value & 0x02))}; "
        f"slip-src={'block-start' if value & 0x01 else 'data-slip'}"
    )


def _decode_reg09(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    validity = "DIR V-bit" if value & 0x04 else "VALID bit"
    txcus = TXCUS_LABELS[value & 0x03]
    return f"validity={validity}; C/U source={txcus}"


def _decode_reg0a(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    labels = [
        f"READY irq={_on_off(bool(value & 0x10))}",
        f"RATIO irq input>output={_on_off(bool(value & 0x20))}",
        f"TSLIP={_on_off(bool(value & 0x02))}",
        f"TBTI={_on_off(bool(value & 0x01))}",
    ]
    return "; ".join(labels)


def _decode_reg0e(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    divider = RXCKO_DIVIDERS[(value >> 1) & 0x03]
    return (
        f"RXCKO={_on_off(bool(value & 0x01))}; div={divider}; "
        f"RXAMLL={_on_off(bool(value & 0x08))}; "
        f"LOL={'free-run' if value & 0x10 else 'stop'}"
    )


def _decode_reg12(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    labels = []
    if value & 0x01:
        labels.append("IEC61937")
    if value & 0x02:
        labels.append("DTS CD/LD")
    return ", ".join(labels) if labels else "PCM"


def _decode_reg13(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    return RXCKR_NAMES.get(value & 0x03, f"0x{value & 0x03:02X}")


def _decode_reg14(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    labels = []
    for mask, name in (
        (0x80, "CSCRC"),
        (0x40, "PARITY"),
        (0x20, "VBIT"),
        (0x10, "BPERR"),
        (0x08, "QCHG"),
        (0x04, "UNLOCK"),
        (0x02, "QCRC"),
        (0x01, "RBTI"),
    ):
        if value & mask:
            labels.append(name)
    lock = "UNLOCK=1" if value & 0x04 else "UNLOCK=0"
    return f"{lock}; " + (", ".join(labels) if labels else "clean")


def _decode_reg15(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    return "OSLIP" if value & 0x01 else "clean"


def _decode_reg2d(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    src_input = SRC_INPUT_LABELS[value & 0x03]
    ref = SRC_REF_CLOCK_LABELS[(value >> 2) & 0x03]
    return (
        f"input={src_input}; ref={ref}; mute={_on_off(bool(value & 0x10))}; "
        f"track={_on_off(bool(value & 0x40))}"
    )


def _decode_reg2e(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    deemph = "auto" if value & 0x20 else DEEMPH_LABELS[(value >> 3) & 0x03]
    decimation = "direct-downsample" if value & 0x04 else "decimation-filter"
    prebuffer = PREBUFFER_LABELS[value & 0x03]
    return f"prebuffer={prebuffer}; {decimation}; de-emphasis={deemph}"


def _decode_reg2f(value: int) -> str:
    if value == 0xFF:
        return "n/a"
    return f"output word={WORD_LENGTH_LABELS[(value >> 6) & 0x03]}"


def _pc_type_label(pc_low: int) -> str:
    if pc_low == 0xFF:
        return "n/a"
    type_code = pc_low & 0x1F
    return PC_TYPE_LABELS.get(type_code, f"reserved 0x{type_code:02X}")


def _route_summary(snap: Src4382Snapshot) -> str:
    if snap.source_route == 0xFF:
        return f"route=unknown; selected={_rx_label(snap.selected_rx)}"
    parts = [f"route={snap.source_route}"]
    profile = ROUTE_PROFILES.get(snap.source_route)
    if profile is not None:
        label, expected_0d, expected_08 = profile
        parts.append(label)
        if snap.reg0d == expected_0d and snap.reg08 == expected_08:
            parts.append("check=OK")
        else:
            parts.append(
                "check=MISMATCH "
                f"expected 0D=0x{expected_0d:02X} 08=0x{expected_08:02X}"
            )
    else:
        parts.append("legacy/auto route")
    parts.append(f"selected={_rx_label(snap.selected_rx)}")
    return "; ".join(parts)


def _clock_status_dict(snap: Src4382Snapshot) -> Optional[dict[str, object]]:
    if not snap.clock_status_present:
        return None
    return {
        "port_a": {
            "mode": "master" if snap.reg03 & 0x08 else "slave",
            "output": PORT_OUTPUT_LABELS[(snap.reg03 >> 4) & 0x03],
            "clock": PORT_CLOCK_LABELS[(snap.reg04 >> 2) & 0x03],
            "divider": PORT_DIVIDERS[snap.reg04 & 0x03],
        },
        "port_b": {
            "mode": "master" if snap.reg05 & 0x08 else "slave",
            "output": PORT_OUTPUT_LABELS[(snap.reg05 >> 4) & 0x03],
            "clock": PORT_CLOCK_LABELS[(snap.reg06 >> 2) & 0x03],
            "divider": PORT_DIVIDERS[snap.reg06 & 0x03],
        },
        "dit": {
            "input": DIT_INPUT_LABELS[(snap.reg07 >> 3) & 0x03],
            "clock": DIT_CLOCK_LABELS[(snap.reg07 >> 7) & 0x01],
            "divider": PORT_DIVIDERS[(snap.reg07 >> 5) & 0x03],
        },
        "src_dit_status": {
            "ready_interrupt": bool(snap.reg0a & 0x10),
            "ratio_interrupt_input_gt_output": bool(snap.reg0a & 0x20),
            "tslip": bool(snap.reg0a & 0x02),
            "tbti": bool(snap.reg0a & 0x01),
        },
        "rxcko": {
            "enabled": bool(snap.reg0e & 0x01),
            "divider": RXCKO_DIVIDERS[(snap.reg0e >> 1) & 0x03],
            "rxamll": bool(snap.reg0e & 0x08),
            "lol_free_run": bool(snap.reg0e & 0x10),
        },
    }


def _clock_rate_candidates(
    snap: Src4382Snapshot,
    *,
    output_clock_hz: Optional[float],
) -> list[tuple[str, float, bool]]:
    if not snap.clock_status_present or output_clock_hz is None or output_clock_hz <= 0:
        return []
    candidates: list[tuple[str, float, bool]] = []
    if snap.reg03 & 0x08 and ((snap.reg04 >> 2) & 0x03) == 0x00:
        divider = PORT_DIVIDERS[snap.reg04 & 0x03]
        source = PORT_OUTPUT_LABELS[(snap.reg03 >> 4) & 0x03]
        candidates.append((f"Port A {source} MCLK/{divider}", output_clock_hz / divider, source == "SRC"))
    if snap.reg05 & 0x08 and ((snap.reg06 >> 2) & 0x03) == 0x00:
        divider = PORT_DIVIDERS[snap.reg06 & 0x03]
        source = PORT_OUTPUT_LABELS[(snap.reg05 >> 4) & 0x03]
        candidates.append((f"Port B {source} MCLK/{divider}", output_clock_hz / divider, source == "SRC"))
    if ((snap.reg07 >> 7) & 0x01) == 0x00:
        divider = PORT_DIVIDERS[(snap.reg07 >> 5) & 0x03]
        source = DIT_INPUT_LABELS[(snap.reg07 >> 3) & 0x03]
        candidates.append((f"DIT {source} MCLK/{divider}", output_clock_hz / divider, source == "SRC"))
    return sorted(candidates, key=lambda item: (not item[2], item[0]))


def _clock_summary(
    snap: Src4382Snapshot,
    *,
    output_clock_hz: Optional[float],
) -> str:
    if not snap.clock_status_present:
        return "extension absent; exact SRC4382-owned rate not proven"
    candidates = _clock_rate_candidates(snap, output_clock_hz=output_clock_hz)
    if not candidates:
        return "no MCLK master-divider candidate on exposed Port A/B/DIT path"
    parts = [
        f"{label}={_format_rate_hz(rate)}{' path' if preferred else ' evidence'}"
        for label, rate, preferred in candidates
    ]
    return "; ".join(parts)


def _preferred_output_rate(
    snap: Src4382Snapshot,
    *,
    output_clock_hz: Optional[float],
) -> tuple[Optional[float], Optional[str]]:
    candidates = _clock_rate_candidates(snap, output_clock_hz=output_clock_hz)
    if not candidates:
        return None, None
    label, rate, _preferred = candidates[0]
    return rate, label


def _lock_summary(snap: Src4382Snapshot) -> str:
    if snap.lock_name == "estimator_hole":
        return "CLK? estimator-hole; formal UNLOCK=0"
    return snap.lock_name.replace("_", "-")


def _payload_summary(snap: Src4382Snapshot) -> str:
    if snap.payload_name == "pcm":
        return "PCM"
    if snap.payload_name == "non_pcm":
        return "IEC61937/non-PCM"
    if snap.payload_name == "dts":
        return "DTS CD/LD"
    return "unknown"


def _rate_summary(
    snap: Src4382Snapshot,
    *,
    output_clock_hz: Optional[float],
    override_output_rate_hz: Optional[float],
    override_output_rate_basis: Optional[str],
) -> str:
    if snap.ratio is None:
        return "input=n/a; ratio=n/a"
    if not snap.clock_status_present:
        return f"input=unknown; ratio={snap.ratio:.6f}; clock/status extension absent"
    if override_output_rate_hz is not None:
        output_rate_hz = override_output_rate_hz
        basis = (
            f"{override_output_rate_basis or 'override output rate'} "
            f"{_format_rate_hz(output_rate_hz)}"
        )
    else:
        output_rate_hz, basis = _preferred_output_rate(
            snap,
            output_clock_hz=output_clock_hz,
        )
    if output_rate_hz is None or output_rate_hz <= 0:
        return f"input=unknown; ratio={snap.ratio:.6f}; no proven MCLK output-rate basis"
    input_rate_hz = snap.ratio * output_rate_hz
    nearest = _nearest_sample_rate_label(input_rate_hz)
    nearest_text = f"; nearest={nearest}" if nearest is not None else ""
    basis_text = f"; basis={basis}" if basis else ""
    ready_text = "; READY irq=off/masked" if not (snap.reg0a & 0x10) else ""
    return (
        f"input={_format_rate_hz(input_rate_hz)} est{nearest_text}; "
        f"ratio={snap.ratio:.6f}{basis_text}{ready_text}"
    )


def _error_summary(snap: Src4382Snapshot) -> str:
    if snap.error_bits == 0xFF:
        return "unknown"
    return ", ".join(snap.error_names) if snap.error_names else "none"


def _health_summary(snap: Src4382Snapshot) -> str:
    flags = [
        f"useful={_on_off(snap.useful)}",
        f"partial={_on_off(snap.partial)}",
        f"stale={_on_off(snap.stale)}",
        f"pending={_on_off(snap.job_pending)}",
    ]
    return f"{snap.status_name.upper()}; " + "; ".join(flags)


def _ascii_table(headers: tuple[str, ...], rows: Iterable[tuple[str, ...]]) -> str:
    table_rows = [tuple(str(cell) for cell in headers)]
    table_rows.extend(tuple(str(cell) for cell in row) for row in rows)
    widths = [
        max(len(row[idx]) for row in table_rows)
        for idx in range(len(headers))
    ]
    sep = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def format_row(row: tuple[str, ...]) -> str:
        cells = [
            row[idx].ljust(widths[idx])
            for idx in range(len(headers))
        ]
        return "| " + " | ".join(cells) + " |"

    lines = [sep, format_row(table_rows[0]), sep]
    lines.extend(format_row(row) for row in table_rows[1:])
    lines.append(sep)
    return "\n".join(lines)


def format_human_report(
    reports: Iterable[Src4382DeviceReport],
    *,
    show_path: bool = False,
    output_clock_hz: Optional[float] = DLCP_RED_CLOCK_HZ,
    output_rate_hz: Optional[float] = None,
    output_rate_basis: Optional[str] = None,
) -> str:
    if output_rate_basis is None and output_rate_hz is not None:
        output_rate_basis = "caller-supplied output rate"
    lines: list[str] = []
    for report_idx, report in enumerate(reports):
        snap = report.snapshot
        if report_idx:
            lines.append("")
        label = f"{report.label} " if report.label else ""
        path = _format_path(report.info.path, show_path=show_path)
        lines.append(
            "SRC4382 selected-source snapshot  "
            f"{label}{path}  status={snap.status_name.upper()} "
            f"flags=0x{snap.snapshot_flags:02X}"
        )
        lines.append("")
        lines.append(_ascii_table(
            ("Field", "Value"),
            (
                ("Status", _health_summary(snap)),
                ("Route", _route_summary(snap)),
                ("Lock", _lock_summary(snap)),
                ("Payload", _payload_summary(snap)),
                ("Rate", _rate_summary(
                    snap,
                    output_clock_hz=output_clock_hz,
                    override_output_rate_hz=output_rate_hz,
                    override_output_rate_basis=output_rate_basis,
                )),
                ("Clock", _clock_summary(snap, output_clock_hz=output_clock_hz)),
                ("RXCKR", f"{snap.rxckr_name} (coarse recovered-clock class)"),
                ("SRC config", f"{_decode_reg2d(snap.reg2d)}; {_decode_reg2f(snap.reg2f)}"),
                ("Errors", _error_summary(snap)),
            ),
        ))
        lines.append("")
        lines.append(_ascii_table(
            ("Reg", "Hex", "Decode", "Notes"),
            (
                ("03", _format_reg(snap.reg03), _decode_port_control1(snap.reg03, port="A"), "Port A control 1"),
                ("04", _format_reg(snap.reg04), _decode_port_control2(snap.reg04, port="A"), "Port A clock/divider"),
                ("05", _format_reg(snap.reg05), _decode_port_control1(snap.reg05, port="B"), "Port B control 1"),
                ("06", _format_reg(snap.reg06), _decode_port_control2(snap.reg06, port="B"), "Port B clock/divider"),
                ("07", _format_reg(snap.reg07), _decode_reg07(snap.reg07), "DIT control 1"),
                ("0D", _format_reg(snap.reg0d), _decode_reg0d(snap.reg0d), "receiver control"),
                ("08", _format_reg(snap.reg08), _decode_reg08(snap.reg08), "transmitter/bypass"),
                ("09", _format_reg(snap.reg09), _decode_reg09(snap.reg09), "DIT control 3"),
                ("0A", _format_reg(snap.reg0a), _decode_reg0a(snap.reg0a), "SRC/DIT status"),
                ("0E", _format_reg(snap.reg0e), _decode_reg0e(snap.reg0e), "RXCKO control"),
                ("12", _format_reg(snap.reg12), _decode_reg12(snap.reg12), "non-PCM detect"),
                ("13", _format_reg(snap.reg13), _decode_reg13(snap.reg13), "RXCKR class only"),
                ("14", _format_reg(snap.reg14), _decode_reg14(snap.reg14), "receiver errors"),
                ("15", _format_reg(snap.reg15), _decode_reg15(snap.reg15), "output slip"),
                ("2D", _format_reg(snap.reg2d), _decode_reg2d(snap.reg2d), "SRC control 1"),
                ("2E", _format_reg(snap.reg2e), _decode_reg2e(snap.reg2e), "SRC control 2"),
                ("2F", _format_reg(snap.reg2f), _decode_reg2f(snap.reg2f), "SRC word length"),
                ("32", _format_reg(snap.reg32), "ratio SRI/SRF[10:8]", "read before 0x33"),
                ("33", _format_reg(snap.reg33), "ratio SRF[7:0]", "input:output ratio"),
            ),
        ))
        lines.append("")
        pc_value = _format_word(snap.pc_high, snap.pc_low)
        pd_value = _format_word(snap.pd_high, snap.pd_low)
        pc_decode = "not requested"
        pd_decode = "not requested"
        if snap.pc_pd_present:
            pc_word = (snap.pc_high << 8) | snap.pc_low
            pd_word = (snap.pd_high << 8) | snap.pd_low
            pc_decode = (
                f"type={_pc_type_label(snap.pc_low)}; "
                f"error={_on_off(bool(pc_word & 0x0080))}; stream={(pc_word >> 13) & 0x07}"
            )
            pd_decode = f"burst length={pd_word} bits"
        lines.append(_ascii_table(
            ("PC/PD", "Value", "Decode"),
            (
                ("PC", pc_value, pc_decode),
                ("PD", pd_value, pd_decode),
            ),
        ))
    return "\n".join(lines) + ("\n" if lines else "")


def _reports_to_json(
    reports: list[Src4382DeviceReport],
    *,
    show_path: bool = False,
) -> dict[str, object]:
    return {
        "spec": "SRC4382_USB_DIAGNOSTICS_V1a",
        "cmd": "0x45",
        "devices": [report.to_dict(show_path=show_path) for report in reports],
    }


def _parse_int_auto(value: str) -> int:
    return int(value, 0)


def _query_from_args(args: argparse.Namespace) -> list[Src4382DeviceReport]:
    path = args.path.encode("utf-8") if args.path is not None else None
    if args.all:
        return query_all(
            vid=args.vid,
            pid=args.pid,
            timeout_ms=args.timeout_ms,
            include_pc_pd=args.include_pc_pd,
            include_ratio=args.include_ratio,
            wait=not args.no_wait,
            label=args.label,
        )
    return [
        query_one(
            vid=args.vid,
            pid=args.pid,
            path=path,
            timeout_ms=args.timeout_ms,
            include_pc_pd=args.include_pc_pd,
            include_ratio=args.include_ratio,
            wait=not args.no_wait,
            label=args.label,
        )
    ]


def _emit_reports(args: argparse.Namespace, reports: list[Src4382DeviceReport]) -> None:
    if args.json:
        print(json.dumps(_reports_to_json(reports, show_path=args.show_path), sort_keys=True))
    else:
        print(
            format_human_report(
                reports,
                show_path=args.show_path,
                output_rate_hz=args.output_rate_hz,
                output_rate_basis=args.output_rate_basis,
                output_clock_hz=args.output_clock_hz,
            ),
            end="",
        )


def _should_fail_status(args: argparse.Namespace, reports: list[Src4382DeviceReport]) -> bool:
    return args.fail_on_diag_status and any(report.snapshot.status != 0 for report in reports)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vid", type=_parse_int_auto, default=DEFAULT_VID)
    ap.add_argument("--pid", type=_parse_int_auto, default=DEFAULT_PID)
    ap.add_argument("--path", help="explicit HID device path; default queries every matching DLCP HID device")
    ap.add_argument("--all", action="store_true", help="query every matching DLCP HID device")
    ap.add_argument("--label", help="operator label to include in output")
    ap.add_argument("--json", action="store_true", help="emit JSON; with --watch this is NDJSON")
    ap.add_argument("--watch", action="store_true", help="repeat until interrupted")
    ap.add_argument("--interval", type=float, default=1.0, help="watch interval seconds")
    ap.add_argument("--timeout-ms", type=int, default=1000, help="HID exchange/job wait timeout")
    ap.add_argument(
        "--include-pc-pd",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="request PC/PD bytes (default: enabled)",
    )
    ap.add_argument(
        "--include-ratio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="request ratio bytes 0x32/0x33 (default: enabled)",
    )
    ap.add_argument(
        "--output-clock-hz",
        type=float,
        default=DLCP_RED_CLOCK_HZ,
        help=(
            "output-rate basis clock for estimated input-rate display "
            f"(default: {DLCP_RED_CLOCK_HZ:.0f}; used with --output-divider)"
        ),
    )
    ap.add_argument(
        "--output-divider",
        type=float,
        default=DLCP_ASSUMED_OUTPUT_DIVIDER,
        help=(
            "legacy option retained for compatibility; exact default output "
            "rates are now derived from cmd45 clock/divider registers"
        ),
    )
    ap.add_argument(
        "--output-rate-hz",
        type=float,
        default=None,
        help=(
            "override output rate for estimated input-rate display; "
            "by default this is derived from cmd45 clock/divider register evidence; "
            "0 disables the estimate"
        ),
    )
    ap.add_argument("--no-wait", action="store_true", help="accepted for compatibility; raw reads are synchronous")
    ap.add_argument("--show-path", action="store_true", help="show raw HID paths instead of redacted hashes")
    ap.add_argument("--force-fast", action="store_true", help="allow --watch intervals below 0.5 s")
    ap.add_argument(
        "--fail-on-diag-status",
        action="store_true",
        help="exit nonzero when a represented diagnostic status is not OK",
    )
    args = ap.parse_args(argv)

    if args.path is None:
        args.all = True
    if args.interval < 0.5 and not args.force_fast:
        ap.error("--interval below 0.5 requires --force-fast")
    if args.timeout_ms <= 0:
        ap.error("--timeout-ms must be positive")
    if args.output_clock_hz <= 0:
        ap.error("--output-clock-hz must be positive")
    if args.output_divider <= 0:
        ap.error("--output-divider must be positive")
    if args.output_rate_hz is not None and args.output_rate_hz < 0:
        ap.error("--output-rate-hz must be nonnegative")
    args.output_rate_basis = None
    if args.output_rate_hz == 0:
        args.output_rate_hz = None
        args.output_clock_hz = None
        args.output_rate_basis = "disabled by --output-rate-hz 0"
    elif args.output_rate_hz is not None:
        args.output_rate_basis = "override --output-rate-hz"

    if args.watch:
        exit_code = 0
        try:
            while True:
                reports = _query_from_args(args)
                if args.json:
                    print(json.dumps(_reports_to_json(reports, show_path=args.show_path), sort_keys=True))
                    sys.stdout.flush()
                else:
                    _emit_reports(args, reports)
                if _should_fail_status(args, reports):
                    exit_code = 2
                time.sleep(args.interval)
        except KeyboardInterrupt:
            return exit_code
    reports = _query_from_args(args)
    _emit_reports(args, reports)
    return 2 if _should_fail_status(args, reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
