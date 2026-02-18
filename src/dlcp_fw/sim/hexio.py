"""Intel HEX helpers for deterministic simulation overlays."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping


class HexError(RuntimeError):
    """Raised on malformed HEX data."""


def parse_intel_hex(path: Path) -> Dict[int, int]:
    mem: Dict[int, int] = {}
    upper = 0
    for lineno, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise HexError(f"{path}:{lineno}: missing ':'")
        try:
            ll = int(line[1:3], 16)
            addr16 = int(line[3:7], 16)
            rtype = int(line[7:9], 16)
        except ValueError as exc:
            raise HexError(f"{path}:{lineno}: invalid record header") from exc
        data_hex = line[9 : 9 + ll * 2]
        try:
            data = bytes.fromhex(data_hex)
            cc = int(line[9 + ll * 2 : 11 + ll * 2], 16)
        except ValueError as exc:
            raise HexError(f"{path}:{lineno}: invalid data/checksum") from exc

        total = ll + ((addr16 >> 8) & 0xFF) + (addr16 & 0xFF) + rtype + sum(data)
        total &= 0xFF
        calc = (~total + 1) & 0xFF
        if calc != cc:
            raise HexError(
                f"{path}:{lineno}: checksum mismatch got=0x{cc:02X} want=0x{calc:02X}"
            )

        if rtype == 0x00:
            base = (upper << 16) | addr16
            for i, b in enumerate(data):
                mem[base + i] = b
        elif rtype == 0x01:
            break
        elif rtype == 0x04:
            if ll != 2:
                raise HexError(f"{path}:{lineno}: type 04 must contain 2 bytes")
            upper = (data[0] << 8) | data[1]
    return mem


def _rec(addr16: int, rtype: int, payload: bytes) -> str:
    ll = len(payload)
    total = ll + ((addr16 >> 8) & 0xFF) + (addr16 & 0xFF) + rtype + sum(payload)
    cc = ((~total + 1) & 0xFF)
    return f":{ll:02X}{addr16:04X}{rtype:02X}{payload.hex().upper()}{cc:02X}"


def write_intel_hex(path: Path, mem: Mapping[int, int], chunk: int = 16) -> None:
    addrs = sorted(mem.keys())
    out = []
    cur_upper: int | None = None
    i = 0
    while i < len(addrs):
        start = addrs[i]
        upper = (start >> 16) & 0xFFFF
        if upper != cur_upper:
            cur_upper = upper
            out.append(_rec(0x0000, 0x04, bytes([(upper >> 8) & 0xFF, upper & 0xFF])))
        a16 = start & 0xFFFF
        data = bytearray([mem[start] & 0xFF])
        i += 1
        while i < len(addrs):
            nxt = addrs[i]
            if ((nxt >> 16) & 0xFFFF) != upper:
                break
            if (nxt & 0xFFFF) != ((a16 + len(data)) & 0xFFFF):
                break
            if len(data) >= chunk:
                break
            data.append(mem[nxt] & 0xFF)
            i += 1
        out.append(_rec(a16, 0x00, bytes(data)))
    out.append(":00000001FF")
    path.write_text("\n".join(out) + "\n", encoding="ascii")


def bytes_at(mem: Mapping[int, int], addr: int, size: int, default: int = 0xFF) -> bytes:
    return bytes(mem.get(addr + i, default) for i in range(size))


def patch_bytes(mem: Dict[int, int], patches: Mapping[int, int]) -> int:
    changed = 0
    for addr, value in patches.items():
        cur = mem.get(addr, 0xFF)
        mem[addr] = value & 0xFF
        if cur != (value & 0xFF):
            changed += 1
    return changed


def assert_bytes(mem: Mapping[int, int], expected: Mapping[int, int], *, label: str = "HEX") -> None:
    for addr, want in expected.items():
        got = mem.get(addr, 0xFF)
        if got != (want & 0xFF):
            raise HexError(
                f"{label}: byte mismatch at 0x{addr:04X}: got 0x{got:02X}, want 0x{want:02X}"
            )


@dataclass(frozen=True)
class ByteRangeDigest:
    base: int
    size: int
    sha256: str


def iter_byte_ranges(base: int, size: int, step: int) -> Iterable[tuple[int, int]]:
    end = base + size
    cur = base
    while cur < end:
        span = min(step, end - cur)
        yield cur, span
        cur += span
