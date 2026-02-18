"""HD44780 decode from gpsim log writes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class LcdByte:
    cycle: int
    rs: int
    value: int
    n1: int
    n2: int


def decode_lcd_bytes(log_path: Path) -> List[LcdByte]:
    ins_re = re.compile(r"^0x([0-9A-Fa-f]+)\s+\S+\s+0x([0-9A-Fa-f]+)\s+0x([0-9A-Fa-f]+)\s+(.*)$")
    w_re = re.compile(r"Read:\s+0x([0-9A-Fa-f]+)\s+from W\(0x0FE8\)")
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()

    rs = 0
    pending: tuple[int, int] | None = None
    nibbles: list[tuple[int, int, int]] = []

    for line in lines:
        m = ins_re.match(line)
        if m:
            cycle = int(m.group(1), 16)
            op = m.group(4).lower()
            if "bcf\tlata,5" in op:
                rs = 0
            elif "bsf\tlata,5" in op:
                rs = 1

            if "iorwf\tportb" in op:
                pending = (cycle, rs)
            else:
                pending = None
            continue

        if pending is None:
            continue
        mw = w_re.search(line)
        if not mw:
            continue
        w = int(mw.group(1), 16)
        nibbles.append((pending[0], pending[1], w & 0x0F))

    out: List[LcdByte] = []
    for i in range(0, len(nibbles) - 1, 2):
        _, _, n1 = nibbles[i]
        c2, rs2, n2 = nibbles[i + 1]
        b = ((n1 << 4) | n2) & 0xFF
        out.append(LcdByte(cycle=c2, rs=rs2, value=b, n1=n1, n2=n2))
    return out


@dataclass
class LcdState:
    ddram: List[str]
    cursor: int = 0

    @staticmethod
    def new() -> "LcdState":
        return LcdState(ddram=[" "] * 0x80, cursor=0)

    def line1(self) -> str:
        return "".join(self.ddram[0x00:0x10])

    def line2(self) -> str:
        return "".join(self.ddram[0x40:0x50])

    def apply(self, b: LcdByte) -> str:
        if b.rs == 0:
            v = b.value
            if v == 0x01:
                self.ddram = [" "] * 0x80
                self.cursor = 0
                return "CMD CLR"
            if v == 0x02:
                self.cursor = 0
                return "CMD HOME"
            if v & 0x80:
                self.cursor = v & 0x7F
                return f"CMD SET_DDRAM 0x{self.cursor:02X}"
            return f"CMD 0x{v:02X}"

        ch = chr(b.value) if 32 <= b.value < 127 else "?"
        if 0 <= self.cursor < len(self.ddram):
            self.ddram[self.cursor] = ch
        self.cursor = (self.cursor + 1) & 0x7F
        return f"DATA '{ch}' (0x{b.value:02X})"

