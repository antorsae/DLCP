"""Behavioral simulation of DLCP Control UI key/menu flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List

from .hexio import parse_intel_hex
from .protocol import SerialFrame


def read_str16(mem: Dict[int, int], addr: int) -> str:
    raw = bytes(mem.get(addr + i, 0x20) for i in range(16))
    raw = raw.replace(b"\x00", b" ")
    return raw.decode("ascii", "replace")[:16].ljust(16)


def _clamp16(s: str) -> str:
    return s[:16].ljust(16)


@dataclass
class ControlStrings:
    menu_hdr: List[str]
    setup_items: List[str]
    src_items: List[str]
    aux_opts: List[str]
    src_route_opts: List[str]
    timeout_opts: List[str]
    input_opts: List[str]
    mute_text: str

    @staticmethod
    def from_hex(mem: Dict[int, int]) -> "ControlStrings":
        menu_hdr = [read_str16(mem, 0x1062 + i * 0x10) for i in range(3)]
        setup_items = [read_str16(mem, 0x1422 + i * 0x10) for i in range(7)]
        src_items = [read_str16(mem, 0x1660 + i * 0x10) for i in range(7)]
        aux_opts = [read_str16(mem, 0x1710), read_str16(mem, 0x1720)]
        src_route_opts = [read_str16(mem, 0x16D0 + i * 0x10) for i in range(4)]
        timeout_opts = [read_str16(mem, 0x15BC + i * 0x10) for i in range(4)]
        input_opts = [read_str16(mem, 0x1970 + i * 0x10) for i in range(9)]
        mute_text = read_str16(mem, 0x0354)
        return ControlStrings(
            menu_hdr=menu_hdr,
            setup_items=setup_items,
            src_items=src_items,
            aux_opts=aux_opts,
            src_route_opts=src_route_opts,
            timeout_opts=timeout_opts,
            input_opts=input_opts,
            mute_text=mute_text,
        )

    @staticmethod
    def from_hex_path(path: Path) -> "ControlStrings":
        return ControlStrings.from_hex(parse_intel_hex(path))


@dataclass
class ControlPersistentState:
    eeprom: bytearray = field(default_factory=lambda: bytearray([0xFF] * 256))
    preset_addr: int = 0x74

    def save_preset(self, preset_idx: int) -> None:
        self.eeprom[self.preset_addr] = preset_idx & 0x01

    def load_preset(self) -> int:
        v = self.eeprom[self.preset_addr]
        if v not in (0, 1):
            return 0
        return v

    def save_to_file(self, path: Path) -> None:
        path.write_bytes(bytes(self.eeprom))

    def load_from_file(self, path: Path) -> None:
        if not path.exists():
            return
        data = path.read_bytes()
        for i, b in enumerate(data[:256]):
            self.eeprom[i] = b


@dataclass
class ControlUISim:
    st: ControlStrings
    persist: ControlPersistentState = field(default_factory=ControlPersistentState)
    menu_state: int = 0  # 0=Volume, 1=Preset, 2=Input, 3=Setup
    setup_sub: int = 0  # 0..6
    in_setup_item: bool = False
    param_idx: int = 0  # 0..6 (Source CH1..CH6, USBaudio)
    input_sel: int = 0  # 0..8
    volume_steps: int = 0x33
    mute: bool = False
    preset: int = 0
    src_params: List[List[int]] = field(default_factory=lambda: [[0] * 6 for _ in range(6)])
    aux_vals: List[int] = field(default_factory=lambda: [0] * 6)
    timeout_sel: int = 0
    tx_frames: List[SerialFrame] = field(default_factory=list)
    retry_budget: int = 0
    prev_connected: int = 0

    def boot(self) -> None:
        self.menu_state = 0
        self.in_setup_item = False
        self.preset = self.persist.load_preset()
        self.retry_budget = 3
        self.prev_connected = 0

    def power_cycle(self) -> "ControlUISim":
        nxt = ControlUISim(st=self.st, persist=self.persist)
        nxt.boot()
        return nxt

    def _emit_frame(self, route: int, cmd: int, data: int) -> None:
        self.tx_frames.append(SerialFrame(route=route, cmd=cmd, data=data).normalized())

    def _emit_volume(self) -> None:
        self._emit_frame(0xB0, 0x07, self.volume_steps)

    def _emit_input(self) -> None:
        self._emit_frame(0xB0, 0x06, self.input_sel)

    def _emit_mute(self) -> None:
        self._emit_frame(0xB0, 0x03, 0x02 if self.mute else 0x03)

    def _emit_preset_frame(self) -> None:
        self._emit_frame(0xB0, 0x20, self.preset & 0x01)

    def service_full_sync(self, *, connected: bool = True) -> None:
        current = 1 if connected else 0
        if current != self.prev_connected:
            self.prev_connected = current
            if current == 1 and self.retry_budget == 0:
                self.retry_budget = 3
        if self.retry_budget > 0:
            self._emit_preset_frame()
            self.retry_budget -= 1

    def _set_preset(self, idx: int) -> None:
        normalized = idx & 0x01
        if normalized == self.preset:
            return
        self.preset = normalized
        self.persist.save_preset(self.preset)
        self._emit_preset_frame()
        self.retry_budget = 2

    def _render_volume_line1(self) -> str:
        line = list(self.st.menu_hdr[0])
        line[15] = "B" if self.preset else "A"
        return _clamp16("".join(line))

    def _render_volume_line2(self) -> str:
        if self.mute:
            return _clamp16(self.st.mute_text)
        delta = self.volume_steps - 0x60
        if delta > 0:
            return _clamp16(f"+{delta}.0 dB")
        if delta < 0:
            return _clamp16(f"-{abs(delta)}.0 dB")
        return _clamp16("0.0 dB")

    def _render_preset_line1(self) -> str:
        return _clamp16("Preset")

    def _render_preset_line2(self) -> str:
        return _clamp16(f"Active: {'B' if self.preset else 'A'}")

    def ingest_rx_frame(self, frame: SerialFrame) -> bool:
        _ = frame
        return False

    def render(self) -> tuple[str, str]:
        if self.in_setup_item:
            if self.setup_sub < 6:
                line1 = self.st.src_items[self.param_idx]
                if self.param_idx < 6:
                    v = self.src_params[self.param_idx][self.setup_sub]
                    line2 = self.st.src_route_opts[v % len(self.st.src_route_opts)]
                else:
                    v = self.aux_vals[self.setup_sub] & 1
                    line2 = self.st.aux_opts[v]
                return _clamp16(line1), _clamp16(line2)
            return _clamp16(self.st.setup_items[6]), _clamp16(
                self.st.timeout_opts[self.timeout_sel % len(self.st.timeout_opts)]
            )

        if self.menu_state == 0:
            return self._render_volume_line1(), self._render_volume_line2()
        if self.menu_state == 1:
            return self._render_preset_line1(), self._render_preset_line2()
        if self.menu_state == 2:
            return _clamp16(self.st.menu_hdr[1]), _clamp16(
                self.st.input_opts[self.input_sel % len(self.st.input_opts)]
            )
        return _clamp16(self.st.menu_hdr[2]), _clamp16(self.st.setup_items[self.setup_sub])

    def press(self, key: str) -> None:
        k = key.upper()
        if k not in {"L", "R", "U", "D", "S", "B"}:
            raise ValueError(f"unknown key {key!r}")

        if self.in_setup_item:
            if k in {"B", "S"}:
                self.in_setup_item = False
                return
            if self.setup_sub < 6:
                if k == "R":
                    self.param_idx = (self.param_idx + 1) % 7
                    return
                if k == "L":
                    self.param_idx = (self.param_idx - 1) % 7
                    return
                if self.param_idx < 6:
                    cur = self.src_params[self.param_idx][self.setup_sub]
                    if k == "U":
                        self.src_params[self.param_idx][self.setup_sub] = (cur + 1) % len(
                            self.st.src_route_opts
                        )
                    elif k == "D":
                        self.src_params[self.param_idx][self.setup_sub] = (cur - 1) % len(
                            self.st.src_route_opts
                        )
                else:
                    cur = self.aux_vals[self.setup_sub] & 1
                    nxt = (cur + 1) & 1 if k == "U" else (cur - 1) & 1
                    self.aux_vals[self.setup_sub] = nxt
            else:
                if k == "U":
                    self.timeout_sel = (self.timeout_sel + 1) % len(self.st.timeout_opts)
                elif k == "D":
                    self.timeout_sel = (self.timeout_sel - 1) % len(self.st.timeout_opts)
            return

        if self.menu_state == 0:
            if k == "R":
                self.menu_state = 1
            elif k == "L":
                self.menu_state = 3
            elif k == "U":
                self.volume_steps = min(self.volume_steps + 1, 0x72)
                self.mute = False
                self._emit_volume()
            elif k == "D":
                self.volume_steps = max(self.volume_steps - 1, 0)
                self.mute = False
                self._emit_volume()
            elif k == "S":
                self.mute = not self.mute
                self._emit_mute()
            return

        if self.menu_state == 1:
            if k == "R":
                self.menu_state = 2
            elif k == "L":
                self.menu_state = 0
            elif k == "U":
                self._set_preset(0)
            elif k == "D":
                self._set_preset(1)
            return

        if self.menu_state == 2:
            if k == "R":
                self.menu_state = 3
            elif k == "L":
                self.menu_state = 1
            elif k == "U":
                self.input_sel = (self.input_sel + 1) % len(self.st.input_opts)
                self._emit_input()
            elif k == "D":
                self.input_sel = (self.input_sel - 1) % len(self.st.input_opts)
                self._emit_input()
            return

        if k == "R":
            self.menu_state = 0
        elif k == "L":
            self.menu_state = 2
        elif k == "U":
            self.setup_sub = (self.setup_sub + 1) % 7
        elif k == "D":
            self.setup_sub = (self.setup_sub - 1) % 7
        elif k == "S":
            self.in_setup_item = True

    def run_script(self, keys: Iterable[str]) -> None:
        for k in keys:
            self.press(k)
