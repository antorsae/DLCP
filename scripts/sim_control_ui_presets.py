#!/usr/bin/env python3
"""
Console LCD simulator for patched DLCP Control v1.4 presets UI.

This is a protocol/UI state simulator (not a full PIC emulator). It models:
- Top-level screens: Volume(0), Preset(1), Input(2), Setup(3)
- Setup list: DLCP 1..6, BL Timeout
- Setup item editor for DLCP 1..6: Source CH1..CH6 + USBaudio
- Preset screen: UP=A, DOWN=B with >X< bracket selection

Keys:
  L = Left
  R = Right
  U = Up
  D = Down
  S = Select
  B = Back (leave setup item editor)
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Dict, List

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dlcp_fw.paths import PATCHED_CONTROL_HEX


def parse_intel_hex(path: pathlib.Path) -> Dict[int, int]:
    mem: Dict[int, int] = {}
    upper = 0
    for lineno, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise RuntimeError(f"{path}:{lineno}: invalid HEX record")
        ll = int(line[1:3], 16)
        addr16 = int(line[3:7], 16)
        rtype = int(line[7:9], 16)
        data = bytes.fromhex(line[9 : 9 + ll * 2])
        if rtype == 0x00:
            base = (upper << 16) | addr16
            for i, b in enumerate(data):
                mem[base + i] = b
        elif rtype == 0x01:
            break
        elif rtype == 0x04:
            if ll != 2:
                raise RuntimeError(f"{path}:{lineno}: bad type 04 length")
            upper = (data[0] << 8) | data[1]
    return mem


def read_str16(mem: Dict[int, int], addr: int) -> str:
    raw = bytes(mem.get(addr + i, 0x20) for i in range(16))
    # In firmware these are 16-byte fixed labels; strip only trailing NUL.
    raw = raw.replace(b"\x00", b" ")
    return raw.decode("ascii", "replace")[:16].ljust(16)


def clamp16(s: str) -> str:
    return s[:16].ljust(16)


@dataclass
class ControlStrings:
    menu_hdr: List[str]
    setup_items: List[str]
    src_items: List[str]
    input_opts: List[str]
    mute_text: str

    @staticmethod
    def from_hex(mem: Dict[int, int]) -> "ControlStrings":
        menu_hdr = [read_str16(mem, 0x1062 + i * 0x10) for i in range(3)]
        setup_items = [read_str16(mem, 0x1422 + i * 0x10) for i in range(7)]
        src_items = [read_str16(mem, 0x1660 + i * 0x10) for i in range(7)]
        input_opts = [read_str16(mem, 0x1970 + i * 0x10) for i in range(9)]
        mute_text = read_str16(mem, 0x0354)
        return ControlStrings(
            menu_hdr=menu_hdr,
            setup_items=setup_items,
            src_items=src_items,
            input_opts=input_opts,
            mute_text=mute_text,
        )


@dataclass
class ControlUISim:
    st: ControlStrings
    menu_state: int = 0  # 0=Volume, 1=Preset, 2=Input, 3=Setup
    setup_sub: int = 0  # 0..6
    in_setup_item: bool = False
    param_idx: int = 0  # 0..6
    input_sel: int = 0  # 0..8
    volume_steps: int = 102  # maps to -45.0dB at startup
    mute: bool = False
    preset: int = 0  # 0=A, 1=B
    # param tables per DLCP index 0..5
    src_params: List[List[int]] = field(default_factory=lambda: [[0] * 6 for _ in range(6)])

    def _render_volume_line1(self) -> str:
        line = list(self.st.menu_hdr[0])
        line[15] = "B" if self.preset else "A"
        return clamp16("".join(line))

    def _render_volume_line2(self) -> str:
        if self.mute:
            return clamp16(self.st.mute_text)
        db = (self.volume_steps - 192) * 0.5
        return clamp16(f"{db:+5.1f}dB")

    def _render_preset_line(self, line_preset: int) -> str:
        letter = "A" if line_preset == 0 else "B"
        active = (self.preset == line_preset)
        lb = ">" if active else " "
        rb = "<" if active else " "
        if line_preset == 0:
            return clamp16(f"Preset       {lb}{letter}{rb}")
        return clamp16(f"             {lb}{letter}{rb}")

    def render(self) -> tuple[str, str]:
        if self.in_setup_item:
            line1 = self.st.src_items[self.param_idx]
            if self.param_idx < 6:
                v = self.src_params[self.param_idx][self.setup_sub]
                line2 = self.st.input_opts[v % len(self.st.input_opts)]
            else:
                line2 = clamp16("(USBaudio opt)")
            return clamp16(line1), clamp16(line2)

        if self.menu_state == 0:
            return self._render_volume_line1(), self._render_volume_line2()
        if self.menu_state == 1:
            return self._render_preset_line(0), self._render_preset_line(1)
        if self.menu_state == 2:
            return clamp16(self.st.menu_hdr[1]), clamp16(self.st.input_opts[self.input_sel % len(self.st.input_opts)])
        return clamp16(self.st.menu_hdr[2]), clamp16(self.st.setup_items[self.setup_sub])

    def state_brief(self) -> str:
        pchar = "B" if self.preset else "A"
        return (
            f"menu={self.menu_state} setup_sub={self.setup_sub} "
            f"in_item={int(self.in_setup_item)} param={self.param_idx} "
            f"preset={pchar}"
        )

    def press(self, key: str) -> None:
        k = key.upper()
        if k not in {"L", "R", "U", "D", "S", "B"}:
            raise ValueError(f"unknown key: {key}")

        # In setup item editor
        if self.in_setup_item:
            if k in {"B", "S"}:
                self.in_setup_item = False
                return
            if k == "R":
                self.param_idx = (self.param_idx + 1) % 7
                return
            if k == "L":
                self.param_idx = (self.param_idx - 1) % 7
                return
            if self.param_idx < 6:
                cur = self.src_params[self.param_idx][self.setup_sub]
                if k == "U":
                    self.src_params[self.param_idx][self.setup_sub] = (cur + 1) % len(self.st.input_opts)
                elif k == "D":
                    self.src_params[self.param_idx][self.setup_sub] = (cur - 1) % len(self.st.input_opts)
            return

        # Volume (state 0)
        if self.menu_state == 0:
            if k == "R":
                self.menu_state = 1
            elif k == "L":
                self.menu_state = 3
            elif k == "U":
                self.volume_steps = min(self.volume_steps + 1, 228)
            elif k == "D":
                self.volume_steps = max(self.volume_steps - 1, 0)
            elif k == "S":
                self.mute = not self.mute
            return

        # Preset (state 1)
        if self.menu_state == 1:
            if k == "R":
                self.menu_state = 2
            elif k == "L":
                self.menu_state = 0
            elif k == "U":
                self.preset = 0  # A
            elif k == "D":
                self.preset = 1  # B
            return

        # Input (state 2)
        if self.menu_state == 2:
            if k == "R":
                self.menu_state = 3
            elif k == "L":
                self.menu_state = 1
            elif k == "U":
                self.input_sel = (self.input_sel + 1) % len(self.st.input_opts)
            elif k == "D":
                self.input_sel = (self.input_sel - 1) % len(self.st.input_opts)
            return

        # Setup (state 3)
        if k == "R":
            self.menu_state = 0
        elif k == "L":
            self.menu_state = 2
        elif k == "U":
            self.setup_sub = (self.setup_sub + 1) % 7
        elif k == "D":
            self.setup_sub = (self.setup_sub - 1) % 7
        elif k == "S":
            if self.setup_sub < 6:
                self.in_setup_item = True


def print_lcd(step: int, action: str, sim: ControlUISim) -> None:
    l1, l2 = sim.render()
    print(f"[{step:02d}] {action}")
    print(f"|{l1}|")
    print(f"|{l2}|")
    print(f"  {sim.state_brief()}")


def parse_script(s: str) -> List[str]:
    out: List[str] = []
    for tok in s.replace(" ", "").split(","):
        if not tok:
            continue
        out.append(tok.upper())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hex",
        type=pathlib.Path,
        default=PATCHED_CONTROL_HEX,
        help="control firmware hex (default: patched control presets A/B)",
    )
    ap.add_argument(
        "--script",
        default="R,D,R,R,R",
        help="comma-separated key presses",
    )
    args = ap.parse_args()

    mem = parse_intel_hex(args.hex.resolve())
    st = ControlStrings.from_hex(mem)
    sim = ControlUISim(st=st)

    print_lcd(0, "START", sim)
    for i, k in enumerate(parse_script(args.script), 1):
        sim.press(k)
        print_lcd(i, k, sim)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
