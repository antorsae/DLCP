#!/usr/bin/env python3
"""
gpsim-backed ncurses simulator for DLCP control firmware.

Features:
- Persistent gpsim process (kept alive during session)
- Live LCD decode from logged HD44780 traffic
- Live TX trace decode from TXREG writes
- Keypad with visual press feedback
- DLCP panels rendered from CONTROL firmware RAM state (actual memory values)

Keys:
- w: up
- x or c: down
- a: left
- d: right
- s: select
- f: standby
- 7/8/9: force MAIN AN0 ADC to 0x0000/0x0228/0x0FFF (both units)
- 1/2: inject decoded IR F1/F2 (0x38/0x39) into CONTROL firmware
- 3: simulate USB profile upload (active preset, random table + random filename)
- h: toggle info/help
- q: quit
"""

from __future__ import annotations

import argparse
import curses
import hashlib
import os
import random
import re
import select
import shutil
import string
import subprocess
import sys
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dlcp_fw.sim.lcd import LcdByte, LcdState
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.main_gpsim_timer3 import (
    _add_break_exec,
    _contains_exec_break,
    _parse_cycle,
    _read_reg,
    _timer3_overflow_cycles,
)
from dlcp_fw.sim.manifests import (
    control_disable_boot_wait,
    control_disable_standby_check_for_hex,
    control_reset_to_appstart,
    main_adc_boot_wait_hook,
    main_i2c_bypass,
    main_reset_to_appstart,
    main_serial_mailbox_hooks,
    main_serial_mailbox_hooks_uart_only,
)
from dlcp_fw.sim.overlay import apply_overlays


UP = "UP"
DOWN = "DOWN"
LEFT = "LEFT"
RIGHT = "RIGHT"
SELECT = "SELECT"
STBY = "STBY"

KEY_TO_ACTION: Dict[str, str] = {
    "w": UP,
    "x": DOWN,
    "c": DOWN,
    "a": LEFT,
    "d": RIGHT,
    "s": SELECT,
    "f": STBY,
}

KEY_A_BITS: Dict[str, int] = {
    SELECT: 1 << 1,  # RA1
    DOWN: 1 << 2,  # RA2
    STBY: 1 << 3,  # RA3
    RIGHT: 1 << 4,  # RA4
}
KEY_C_BITS: Dict[str, int] = {
    UP: 1 << 0,  # RC0
    LEFT: 1 << 5,  # RC5
}
UNPRESSED_A_MASK = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)  # 0x1E
UNPRESSED_C_MASK = (1 << 0) | (1 << 5)  # 0x21

# Scan-bit mapping for function_023's debounced button result (1 = pressed).
# These bit positions match the firmware's scan logic: each pin is read,
# XOR'd with 0xFF (active-low inversion), and packed into a 6-bit value.
SCAN_BITS: Dict[str, int] = {
    STBY: 1 << 0,  # bit0: RA3 inverted
    UP: 1 << 1,  # bit1: RC0 inverted
    DOWN: 1 << 2,  # bit2: RA2 inverted
    SELECT: 1 << 3,  # bit3: RA1 inverted
    LEFT: 1 << 4,  # bit4: RC5 inverted
    RIGHT: 1 << 5,  # bit5: RA4 inverted
}

CMD_LABELS = {
    0x03: "CTRL",
    0x04: "REQ_STATUS",
    0x06: "INPUT",
    0x07: "VOLUME",
    0x17: "CH1_SRC",
    0x18: "CH2_SRC",
    0x19: "CH3_SRC",
    0x1A: "CH4_SRC",
    0x1B: "CH5_SRC",
    0x1C: "CH6_SRC",
    0x1D: "BL_TIMEOUT",
    0x1E: "LINK_ADDR",
    0x20: "PRESET",
    0x21: "FILENAME_REQ",
    0x22: "FILENAME_GEN_REQ",
    0x2F: "FILENAME_CTX",
}

CTRL_DATA_LABELS = {
    0x00: "STBY_OFF",
    0x01: "STBY_ON",
    0x02: "MUTE_ON",
    0x03: "MUTE_OFF",
}

WAKE_CMD = 0x03
WAKE_DATA = 0x01
IR_F1_CMD = 0x38
IR_F2_CMD = 0x39


def _cmd_label(cmd: int) -> str:
    if 0x30 <= cmd <= 0x37:
        return f"FILENAME_CHUNK[{cmd - 0x30}]"
    return CMD_LABELS.get(cmd, "CMD?")


def _encode_filename_slot(name: str, *, slot_len: int = 30) -> bytes:
    """Encode HFD filename payload into MAIN slot semantics (0x00 -> 0xFF)."""
    payload = name.encode("ascii", errors="ignore")[:slot_len]
    out = bytearray([0xFF] * slot_len)
    for i, b in enumerate(payload):
        out[i] = 0xFF if b == 0x00 else (b & 0xFF)
    return bytes(out)


def _random_upload_filename(rng: random.Random, *, min_len: int = 12, max_len: int = 17) -> str:
    alphabet = string.ascii_uppercase + string.digits + "-_"
    n = rng.randint(min_len, max_len)
    return "".join(rng.choice(alphabet) for _ in range(n))


def _next_filename_req_token(prev_req_data: int, preset_idx: int) -> int:
    """Advance filename request token and reset page bits."""
    # Keep bit7 clear: CONTROL RX parser treats bytes >=0x80 as route candidates.
    token = ((prev_req_data & 0xFF) + 0x08) & 0x78
    return token | (preset_idx & 0x01)


def _control_active_preset(issue_fn) -> int:
    """Read live CONTROL preset bit from state_flags (0x01F.6)."""
    flags = _read_reg(issue_fn, 0x01F)
    return 1 if (flags & 0x40) else 0


def _has_preset_screen_layout(control_hex: Path) -> bool:
    """Detect patched 4-screen CONTROL layout where menu_state 1 is Preset."""
    try:
        mem = parse_intel_hex(control_hex)
    except Exception:
        return False

    # Patched nav-wrap literals (movlw 0x03) by firmware family:
    # V1.41:  0x1264, 0x1288
    # V1.51b: 0x1256, 0x127A
    # V1.61b: 0x1216, 0x123A
    pairs = ((0x1264, 0x1288), (0x1256, 0x127A), (0x1216, 0x123A))
    for a, b in pairs:
        if mem.get(a, 0xFF) == 0x03 and mem.get(b, 0xFF) == 0x03:
            return True
    return False


def _runtime_chunks_for_mode(
    *,
    filename_flow_active: bool,
    runtime_control_chunk: int,
    runtime_main_chunk: int,
    filename_flow_chunk: int,
) -> tuple[int, int]:
    """Return (control_chunk, main_chunk) for current runtime mode."""
    if filename_flow_active:
        # During filename flows we intentionally run both sides with a finer,
        # synchronized quantum to reduce coarse-step RX burst artifacts.
        return filename_flow_chunk, filename_flow_chunk
    return runtime_control_chunk, runtime_main_chunk


# ── Clock and UART timing model ──────────────────────────────────────
# PIC18F2550: instruction cycle (Tcy) = Fosc / 4.
# 31,250 baud 8N1: 10 bits/byte → 320 µs/byte on wire.
#
# CONTROL PIC: 12 MHz crystal → 3 MIPS → 960 Tcy/byte.
# MAIN PIC:    12 MHz crystal → 3 MIPS → 960 Tcy/byte.
#   (Both confirmed by SPBRG=23 with BRGH=1: Fosc/(16*(23+1)) = 31,250.)
#
# EUSART RCREG FIFO is 2 bytes deep (PIC18F2550 datasheet §20.2.2,
# Figure 20-6/20-7).  There is NO hardware receive buffer beyond that.
# Overrun (OERR) occurs when a 3rd byte completes in RSR while RCREG
# is still full.  The simulation must respect this constraint.
CONTROL_FOSC_HZ = 12_000_000
MAIN_FOSC_HZ = 12_000_000
BAUD_RATE = 31_250
BITS_PER_BYTE = 10  # 8N1: 1 start + 8 data + 1 stop
EUSART_FIFO_DEPTH = 2  # RCREG depth per datasheet


def _byte_cycles(fosc_hz: int, baud: int = BAUD_RATE) -> int:
    """Instruction cycles consumed by one serial byte on the wire."""
    tcy_hz = fosc_hz // 4
    return int(BITS_PER_BYTE * tcy_hz / baud)


def _sim_step_timeout(delta_cycles: int) -> float:
    # Keep command round-trips short so small simulation quanta can be used
    # without long waits.  For tiny steps we still keep a tiny minimum timeout
    # to avoid tight busy loops in gpsim command/response.
    delta = max(1, int(delta_cycles))
    return min(2.0, max(0.05, delta / 300_000.0))


@dataclass(frozen=True)
class TxTriplet:
    cycle: int
    route: int
    cmd: int
    data: int


@dataclass(frozen=True)
class UnitMemState:
    link: int
    ch_src: List[int]


@dataclass(frozen=True)
class MemSnapshot:
    cycle: int
    flags: int
    input_sel: int
    volume: int
    unit_count: int
    menu_state: int
    setup_sel: int
    bl_timeout: int
    portc: int
    trisc: int
    latc: int
    preset_name_a: str
    preset_name_b: str
    unit0: UnitMemState
    unit1: UnitMemState


class LiveLogDecoder:
    """Incremental decoder for gpsim log file."""

    _ins_re = re.compile(
        r"^0x([0-9A-Fa-f]+)\s+\S+\s+0x([0-9A-Fa-f]+)\s+0x([0-9A-Fa-f]+)\s+(.*)$"
    )
    _w_re = re.compile(r"Read:\s+0x([0-9A-Fa-f]+)\s+from W\(0x0FE8\)")
    _tx_re = re.compile(r"Wrote:\s+0x([0-9A-Fa-f]+)\s+to txreg", re.IGNORECASE)

    def __init__(self) -> None:
        self.offset = 0
        self.partial = ""
        self.current_cycle: int | None = None

        self.rs = 0
        self.pending_nibble: tuple[int, int] | None = None  # (cycle, rs)
        self.first_nibble: tuple[int, int, int] | None = None  # (cycle, rs, nibble)
        self.lcd = LcdState.new()

        self.tx_pending: List[
            tuple[int, int]
        ] = []  # (cycle, byte), grouped into 3-byte protocol frames
        self.tx_frames: List[TxTriplet] = []

    def ingest(self, log_path: Path) -> List[TxTriplet]:
        if not log_path.exists():
            return []
        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            f.seek(self.offset)
            chunk = f.read()
            self.offset = f.tell()
        if not chunk:
            return []

        blob = self.partial + chunk
        lines = blob.split("\n")
        if blob and not blob.endswith("\n"):
            self.partial = lines.pop()
        else:
            self.partial = ""

        new_frames: List[TxTriplet] = []
        for line in lines:
            self._parse_line(line, new_frames)
        return new_frames

    def _parse_line(self, line: str, new_frames: List[TxTriplet]) -> None:
        m_ins = self._ins_re.match(line)
        if m_ins:
            self.current_cycle = int(m_ins.group(1), 16)
            op = m_ins.group(4).lower()
            if "bcf\tlata,5" in op:
                self.rs = 0
            elif "bsf\tlata,5" in op:
                self.rs = 1

            if "iorwf\tportb" in op:
                self.pending_nibble = (self.current_cycle, self.rs)
            else:
                self.pending_nibble = None
            return

        if self.pending_nibble is not None:
            m_w = self._w_re.search(line)
            if m_w:
                nibble = int(m_w.group(1), 16) & 0x0F
                cyc, rs = self.pending_nibble
                if self.first_nibble is None:
                    self.first_nibble = (cyc, rs, nibble)
                else:
                    _, _, n1 = self.first_nibble
                    b = ((n1 << 4) | nibble) & 0xFF
                    self.lcd.apply(LcdByte(cycle=cyc, rs=rs, value=b, n1=n1, n2=nibble))
                    self.first_nibble = None
                self.pending_nibble = None

        m_tx = self._tx_re.search(line)
        if m_tx and self.current_cycle is not None:
            b = int(m_tx.group(1), 16) & 0xFF
            self.tx_pending.append((self.current_cycle, b))
            while True:
                route_idx = next(
                    (
                        i
                        for i, (_, x) in enumerate(self.tx_pending)
                        if (x & 0xF0) == 0xB0
                    ),
                    None,
                )
                if route_idx is None:
                    if len(self.tx_pending) > 8:
                        self.tx_pending.clear()
                    break
                if route_idx:
                    del self.tx_pending[:route_idx]
                if len(self.tx_pending) < 3:
                    break
                c0, b0 = self.tx_pending[0]
                _, b1 = self.tx_pending[1]
                _, b2 = self.tx_pending[2]
                del self.tx_pending[:3]
                f = TxTriplet(cycle=c0, route=b0, cmd=b1, data=b2)
                self.tx_frames.append(f)
                new_frames.append(f)

    @property
    def lcd_lines(self) -> tuple[str, str]:
        return (self.lcd.line1(), self.lcd.line2())


class GpsimCliSession:
    """Robust interactive gpsim wrapper for command-by-command control."""

    _PROMPT = b"**gpsim>"

    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            ["gpsim", "-i"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("failed to start gpsim interactive session")
        self.stdin = self.proc.stdin
        self.stdout = self.proc.stdout
        self.fd = self.stdout.fileno()
        self.buf = b""
        self._read_until_prompt(timeout_s=8.0, require=None)

    def _read_available(self, timeout_s: float) -> bytes:
        ready, _, _ = select.select([self.fd], [], [], timeout_s)
        if not ready:
            return b""
        return os.read(self.fd, 4096)

    def _sync(self) -> None:
        # Drain any pending bytes and drop content up to the last prompt.
        while True:
            data = self._read_available(0.0)
            if not data:
                break
            self.buf += data
        idx = self.buf.rfind(self._PROMPT)
        if idx >= 0:
            self.buf = self.buf[idx + len(self._PROMPT) :]

    def _read_until_prompt(self, *, timeout_s: float, require: bytes | None) -> str:
        end = time.monotonic() + timeout_s
        saw_required = require is None
        while time.monotonic() < end:
            if not saw_required and require is not None and require in self.buf:
                saw_required = True
            idx = self.buf.find(self._PROMPT)
            if saw_required and idx >= 0:
                # Absorb a short burst after prompt to avoid leaving trailing prompt bytes.
                settle = time.monotonic() + 0.02
                while time.monotonic() < settle:
                    data = self._read_available(0.0)
                    if not data:
                        break
                    self.buf += data
                    if not saw_required and require is not None and require in self.buf:
                        saw_required = True
                last = self.buf.rfind(self._PROMPT)
                cut = last + len(self._PROMPT)
                out = self.buf[:cut]
                self.buf = self.buf[cut:]
                return out.decode("utf-8", errors="replace")

            data = self._read_available(0.2)
            if data:
                self.buf += data
                continue

            if self.proc.poll() is not None:
                break

        raise TimeoutError("gpsim prompt timeout")

    def cmd(self, command: str, timeout_s: float = 10.0) -> str:
        if self.proc.poll() is not None:
            raise RuntimeError("gpsim exited unexpectedly")
        self._sync()
        self.stdin.write((command + "\n").encode("ascii"))
        self.stdin.flush()
        return self._read_until_prompt(
            timeout_s=timeout_s, require=command.encode("ascii")
        )

    def close(self) -> None:
        if self.proc.poll() is None:
            try:
                self.cmd("quit", timeout_s=2.0)
            except Exception:
                self.proc.terminate()
        try:
            self.proc.wait(timeout=2.0)
        except Exception:
            self.proc.kill()


@dataclass(frozen=True)
class MainMemSnapshot:
    cycle: int
    status_5e: int
    flags_7e: int
    parser_98: int
    flags_94: int
    cmd_a2: int
    data_a3: int
    link_c3: int
    adcon0: int
    adresh: int
    adresl: int
    input_99: int
    vol_cur: tuple[int, int, int, int]
    vol_tgt: tuple[int, int, int, int]
    ch_cfg_cur: tuple[int, int, int, int, int, int]
    ch_cfg_shadow: tuple[int, int, int, int, int, int]
    mb_rd: int
    mb_wr: int
    mb_tx_wr: int
    portc: int
    trisc: int


@dataclass
class ReconnectDiagnostics:
    bit1_prev: int | None = None
    bit1_reconnect_hits: int = 0
    bit1_last_loop_cycle: int = -1
    bit1_events: Deque[tuple[int, int, int]] = field(
        default_factory=lambda: deque(maxlen=16)
    )
    waiting_streak: int = 0
    mailbox_full_streak: int = 0
    last_waiting_cycle: int = -1
    ctl_wake_tx_last: int = 0
    ctl_poll_tx_last: int = 0
    wake_sent: int = 0
    wake_delivered: int = 0
    wake_dropped: int = 0
    wake_consumed: int = 0
    main0_mailbox_used: int = 0
    main1_mailbox_used: int = 0
    main0_rx_prev_rd: int = 0
    main1_rx_prev_rd: int = 0
    parser_idle_streak: int = 0
    no_reply_streak: int = 0
    poll_only_streak: int = 0
    last_reason: str = "initializing"


class MainStandbyPinModel:
    """Harness-level AN0/ADC model for MAIN standby sensing."""

    def __init__(self, mode: str, *, manual_adc: int | None = None) -> None:
        self.mode = mode
        self._bus_high = 0
        self._manual_adc = (
            self._clamp_adc(manual_adc) if manual_adc is not None else None
        )

    @staticmethod
    def _clamp_adc(v: int) -> int:
        if v < 0:
            return 0
        if v > 0x0FFF:
            return 0x0FFF
        return v

    def set_manual_adc(self, value: int | None) -> None:
        self._manual_adc = self._clamp_adc(value) if value is not None else None

    def set_bus_level(self, high: int) -> None:
        self._bus_high = 1 if high else 0

    def target_adc(self) -> int:
        if self._manual_adc is not None:
            return self._manual_adc
        if self.mode == "hold":
            return 0x0230
        if self.mode == "release":
            return 0x0220
        # "control"/"auto": reflect CONTROL RC1 standby bus onto MAIN AN0.
        return 0x0230 if self._bus_high else 0x0220

    def apply(self, issue) -> None:
        adcon0 = _read_reg(issue, 0xFC2)

        adc = self.target_adc()
        adresh = (adc >> 8) & 0xFF
        adresl = adc & 0xFF
        if _read_reg(issue, 0xFC4) != adresh:
            issue(f"reg(0xFC4)=0x{adresh:02X}", 5.0)
        if _read_reg(issue, 0xFC3) != adresl:
            issue(f"reg(0xFC3)=0x{adresl:02X}", 5.0)

        # If firmware started a conversion, complete it with the modeled sample.
        if adcon0 & 0x02:
            issue(f"reg(0xFC2)=0x{adcon0 & 0xFD:02X}", 5.0)

        # Mirror coarse digital level on RA0 for visibility.
        porta = _read_reg(issue, 0xF80)
        desired_ra0 = 1 if adc >= 0x0228 else 0
        if (porta & 0x01) != desired_ra0:
            issue(f"porta=0x{(porta & 0xFE) | desired_ra0:02X}", 5.0)


class MainCurrentLoopPinModel:
    """Harness-level current-loop pin model (RC0 link idle + RC2 strap)."""

    def __init__(self, idle_high: bool = True, rc2_mode: str = "keep") -> None:
        self.idle_high = idle_high
        self.rc2_mode = rc2_mode

    def apply(self, issue) -> None:
        # MAIN firmware gates parts of runtime state machine on PORTC.RC0.
        # Model the real link idle level on the optical receiver input.
        trisc = _read_reg(issue, 0xF94)
        portc = _read_reg(issue, 0xF82)
        desired = portc
        if (trisc & 0x01) != 0:
            desired = (desired | 0x01) if self.idle_high else (desired & 0xFE)
        if (trisc & 0x04) != 0:
            if self.rc2_mode == "high":
                desired |= 0x04
            elif self.rc2_mode == "low":
                desired &= 0xFB
        if desired != portc:
            issue(f"portc=0x{desired:02X}", 5.0)


class MainGpsimSession:
    def __init__(
        self,
        main_hex: Path,
        *,
        gpasm: str,
        chunk_cycles: int,
        tag: str,
        standby_mode: str,
        main_ra0_adc: int,
        rc2_mode: str,
        timer3_mode: str,
        rx_fifo_limit: int = 6,
    ) -> None:
        self.chunk_cycles = chunk_cycles
        self.tag = tag
        self.timer3_mode = timer3_mode
        # Maximum bytes allowed in mailbox before injection is refused (overrun).
        # Real EUSART RCREG is 2-deep; ISR transfers each byte to 64-byte
        # software ring at 0x780-0x7BF.  Since we bypass the ISR and write
        # directly to the ring buffer, the correct limit is the ring capacity
        # (63 usable slots; slot 64 reserved for full/empty detection).
        self._rx_fifo_limit = min(max(1, rx_fifo_limit), 63)
        self._tmp = tempfile.TemporaryDirectory(prefix=f"gpsim_tui_main_{tag}_")
        self.tmp_path = Path(self._tmp.name)
        self.sim_hex = self.tmp_path / "sim.hex"
        self.log_path = self.tmp_path / "gpsim.log"
        self.current_cycle = 0
        self.decoder = LiveLogDecoder()
        self.standby_model = MainStandbyPinModel(standby_mode, manual_adc=main_ra0_adc)
        self.current_loop_model = MainCurrentLoopPinModel(
            idle_high=True, rc2_mode=rc2_mode
        )
        self._sim_table_digest_by_preset: Dict[int, str] = {0: "", 1: ""}

        manifests = [main_reset_to_appstart(), main_i2c_bypass()]
        if timer3_mode == "harness":
            manifests.extend(
                [
                    main_serial_mailbox_hooks_uart_only(gpasm=gpasm),
                    main_adc_boot_wait_hook(gpasm=gpasm),
                ]
            )
        else:
            manifests.append(main_serial_mailbox_hooks(gpasm=gpasm))

        apply_overlays(main_hex, self.sim_hex, manifests=manifests)

        self._gpsim = GpsimCliSession()
        self._issue = lambda c, t=10.0: self._gpsim.cmd(c, timeout_s=t)
        self._timer3_clear_addr = 0x449C
        self._timer3_exec_bp_id: int | None = None
        self._boot()

    def set_standby_bus(self, high: int) -> None:
        self.standby_model.set_bus_level(high)

    def set_main_ra0_adc(self, adc: int) -> None:
        self.standby_model.set_manual_adc(adc)
        self._apply_pin_models()

    def main_ra0_adc(self) -> int:
        return self.standby_model.target_adc()

    def _boot(self) -> None:
        self._issue("processor p18f2550", 5.0)
        self._issue(f"load {self.sim_hex}", 10.0)
        self._issue(f"frequency {MAIN_FOSC_HZ}", 5.0)
        self._issue(f"log on {self.log_path}", 5.0)
        self._issue("log w txreg", 5.0)
        if self.timer3_mode == "harness":
            self._timer3_exec_bp_id = _add_break_exec(
                self._issue, self._timer3_clear_addr
            )
        # mailbox init
        self._issue("reg(0x7C0)=0x00", 5.0)
        self._issue("reg(0x7C1)=0x00", 5.0)
        self._issue("reg(0x7C2)=0x00", 5.0)
        self._issue("reg(0x7C3)=0x00", 5.0)
        self._apply_pin_models()

    def close(self) -> None:
        try:
            self._issue("log off", 5.0)
        except Exception:
            pass
        self._gpsim.close()
        self._tmp.cleanup()

    def inject_triplet(self, frame: TxTriplet) -> bool:
        return self.inject_bytes([frame.route, frame.cmd, frame.data])

    @staticmethod
    def _filename_eeprom_base(preset_idx: int) -> int:
        return 0xA1 if (preset_idx & 0x01) else 0x60

    @staticmethod
    def _filename_generation_addr(preset_idx: int) -> int:
        return 0xBF if (preset_idx & 0x01) else 0x7E

    def _active_preset_idx(self) -> int:
        status_5e = _read_reg(self._issue, 0x05E)
        return 1 if (status_5e & 0x04) else 0

    def _eeprom_read(self, addr: int) -> int:
        # PIC18 data EEPROM read sequence.
        self._issue(f"reg(0xFA9)=0x{addr & 0xFF:02X}", 5.0)   # EEADR
        self._issue("reg(0xFA6)=0x01", 5.0)                   # EECON1: RD
        return _read_reg(self._issue, 0xFA8) & 0xFF           # EEDATA

    def _eeprom_write(self, addr: int, value: int) -> None:
        # PIC18 data EEPROM write sequence.
        self._issue(f"reg(0xFA9)=0x{addr & 0xFF:02X}", 5.0)   # EEADR
        self._issue(f"reg(0xFA8)=0x{value & 0xFF:02X}", 5.0)  # EEDATA
        self._issue("reg(0xFA6)=0x04", 5.0)                   # EECON1: WREN
        self._issue("reg(0xFA7)=0x55", 5.0)                   # EECON2 unlock
        self._issue("reg(0xFA7)=0xAA", 5.0)                   # EECON2 unlock
        self._issue("reg(0xFA6)=0x06", 5.0)                   # EECON1: WREN+WR

    def simulate_usb_profile_upload(
        self, *, preset_idx: int, table_payload_0xA00: bytes, filename: str
    ) -> str:
        """Synthetic HFD upload for TUI experimentation (table digest + filename storage)."""
        if len(table_payload_0xA00) != 0xA00:
            raise ValueError("table_payload_0xA00 must be exactly 0xA00 bytes")
        pidx = 1 if preset_idx else 0
        digest = hashlib.sha256(table_payload_0xA00).hexdigest()[:12]
        self._sim_table_digest_by_preset[pidx] = digest

        slot = _encode_filename_slot(filename)
        # Keep RAM slot coherent only for active preset, matching real cmd03 flow.
        if self._active_preset_idx() == pidx:
            for i, b in enumerate(slot):
                self._issue(f"reg(0x{0x2C0 + i:03X})=0x{b:02X}", 5.0)
        # Persist slot to the selected preset bank in EEPROM.
        base = self._filename_eeprom_base(pidx)
        for i, b in enumerate(slot):
            self._eeprom_write(base + i, b)
        # Mirror MAIN firmware behavior: bump per-preset generation byte so
        # CONTROL's generation-gated cache invalidates on repeated uploads.
        gen_addr = self._filename_generation_addr(pidx)
        gen = self._eeprom_read(gen_addr)
        self._eeprom_write(gen_addr, (gen + 1) & 0xFF)
        return digest

    def inject_bytes(self, data: List[int]) -> bool:
        rd = _read_reg(self._issue, 0x7C0)
        wr = _read_reg(self._issue, 0x7C1)
        used = (wr - rd) & 0xFF
        if used > 0x3C:
            return False
        for b in data:
            addr = 0x780 + (wr & 0x3F)
            self._issue(f"reg(0x{addr:03X})=0x{b & 0xFF:02X}", 5.0)
            wr = (wr + 1) & 0xFF
        self._issue(f"reg(0x7C1)=0x{wr:02X}", 5.0)
        return True

    def inject_single_byte(self, byte_val: int) -> bool:
        """Inject one byte, respecting EUSART-accurate FIFO limit."""
        rd = _read_reg(self._issue, 0x7C0)
        wr = _read_reg(self._issue, 0x7C1)
        used = (wr - rd) & 0xFF
        if used >= self._rx_fifo_limit:
            return False
        addr = 0x780 + (wr & 0x3F)
        self._issue(f"reg(0x{addr:03X})=0x{byte_val & 0xFF:02X}", 5.0)
        self._issue(f"reg(0x7C1)=0x{(wr + 1) & 0xFF:02X}", 5.0)
        return True

    def inject_frames_fifo(
        self, frames: List[List[int]], fifo_limit: int
    ) -> tuple[int, int]:
        """Inject complete frames with frame-aligned overrun semantics.

        Each frame is a list of bytes (typically 3: route, cmd, data).
        A frame is either fully delivered or fully dropped — this prevents
        parser desync from partial frame delivery.

        Returns (delivered_bytes, overrun_bytes).
        """
        rd = _read_reg(self._issue, 0x7C0)
        wr = _read_reg(self._issue, 0x7C1)
        delivered = 0
        overruns = 0
        limit = min(fifo_limit, self._rx_fifo_limit)
        for frame in frames:
            used = (wr - rd) & 0xFF
            free = limit - used
            if free < len(frame):
                overruns += len(frame)
                continue
            for b in frame:
                addr = 0x780 + (wr & 0x3F)
                self._issue(f"reg(0x{addr:03X})=0x{b & 0xFF:02X}", 5.0)
                wr = (wr + 1) & 0xFF
                delivered += 1
        if delivered > 0:
            self._issue(f"reg(0x7C1)=0x{wr:02X}", 5.0)
        return delivered, overruns

    def read_pc(self) -> int:
        """Read the current program counter via gpsim 'dump s' command.

        PCL/PCLATH/PCLATU SFR reads do NOT reflect the actual PC — PCLATH
        and PCLATU are shadow registers for computed GOTOs.  The 'dump s'
        command includes the real PC value.
        """
        out = self._issue("dump s", 5.0)
        m = re.search(r"PC\s*=\s*([0-9a-fA-F]+)", out)
        if m:
            return int(m.group(1), 16)
        return 0

    def step(self) -> tuple[MainMemSnapshot, List[TxTriplet]]:
        self._apply_pin_models()
        self._run_to(self.current_cycle + self.chunk_cycles)
        self._apply_pin_models()
        new_tx = self.decoder.ingest(self.log_path)
        return self.read_snapshot(), new_tx

    def _apply_pin_models(self) -> None:
        self.current_loop_model.apply(self._issue)
        self.standby_model.apply(self._issue)

    def _run_to(self, target_cycle: int) -> None:
        if self.timer3_mode != "harness":
            delta = max(1, target_cycle - self.current_cycle)
            timeout_s = _sim_step_timeout(delta)
            self._issue(f"break c {target_cycle}", 5.0)
            out = self._issue("run", timeout_s)
            self.current_cycle = _parse_cycle(out)
            return

        # Harness-side Timer3 overflow emulation: keep firmware function_079 intact and
        # inject PIR2.TMR3IF at computed overflow cycles.
        while self.current_cycle < target_cycle:
            delta = max(1, target_cycle - self.current_cycle)
            timeout_s = _sim_step_timeout(delta)
            self._issue(f"break c {target_cycle}", 5.0)
            out = self._issue("run", timeout_s)
            self.current_cycle = _parse_cycle(out)

            # Handle I2C breakpoints first (can happen alongside Timer3).
            if self._handle_i2c_breaks(out, target_cycle):
                continue

            if not _contains_exec_break(out, self._timer3_clear_addr):
                break

            # Timer wait loop reached clear-site: schedule next overflow and set TMR3IF.
            t3con = _read_reg(self._issue, 0xFB1)
            tmr3h = _read_reg(self._issue, 0xFB3)
            tmr3l = _read_reg(self._issue, 0xFB2)
            preload = ((tmr3h & 0xFF) << 8) | (tmr3l & 0xFF)
            overflow_cycles, _prescaler = _timer3_overflow_cycles(t3con, preload)
            if overflow_cycles < 1:
                overflow_cycles = 1
            overflow_target = min(target_cycle, self.current_cycle + overflow_cycles)

            self._issue(f"break c {overflow_target}", 5.0)
            overflow_delta = max(1, overflow_target - self.current_cycle)
            overflow_timeout = _sim_step_timeout(overflow_delta)
            out_overflow = self._issue("run", overflow_timeout)
            self.current_cycle = _parse_cycle(out_overflow)

            pir2 = _read_reg(self._issue, 0xFA1)
            self._issue(f"reg(0xFA1)=0x{(pir2 | 0x02) & 0xFF:02X}", 5.0)

    def read_snapshot(self) -> MainMemSnapshot:
        return MainMemSnapshot(
            cycle=self.current_cycle,
            status_5e=_read_reg(self._issue, 0x05E),
            flags_7e=_read_reg(self._issue, 0x07E),
            parser_98=_read_reg(self._issue, 0x098),
            flags_94=_read_reg(self._issue, 0x094),
            cmd_a2=_read_reg(self._issue, 0x0A2),
            data_a3=_read_reg(self._issue, 0x0A3),
            link_c3=_read_reg(self._issue, 0x0C3),
            adcon0=_read_reg(self._issue, 0xFC2),
            adresh=_read_reg(self._issue, 0xFC4),
            adresl=_read_reg(self._issue, 0xFC3),
            input_99=_read_reg(self._issue, 0x099),
            vol_cur=(
                _read_reg(self._issue, 0x066),
                _read_reg(self._issue, 0x067),
                _read_reg(self._issue, 0x068),
                _read_reg(self._issue, 0x069),
            ),
            vol_tgt=(
                _read_reg(self._issue, 0x06E),
                _read_reg(self._issue, 0x06F),
                _read_reg(self._issue, 0x070),
                _read_reg(self._issue, 0x071),
            ),
            ch_cfg_cur=(
                _read_reg(self._issue, 0x060),
                _read_reg(self._issue, 0x061),
                _read_reg(self._issue, 0x062),
                _read_reg(self._issue, 0x063),
                _read_reg(self._issue, 0x064),
                _read_reg(self._issue, 0x065),
            ),
            ch_cfg_shadow=(
                _read_reg(self._issue, 0x0A5),
                _read_reg(self._issue, 0x0A6),
                _read_reg(self._issue, 0x0A7),
                _read_reg(self._issue, 0x0A8),
                _read_reg(self._issue, 0x0A9),
                _read_reg(self._issue, 0x0AA),
            ),
            mb_rd=_read_reg(self._issue, 0x7C0),
            mb_wr=_read_reg(self._issue, 0x7C1),
            mb_tx_wr=_read_reg(self._issue, 0x7C3),
            portc=_read_reg(self._issue, 0xF82),
            trisc=_read_reg(self._issue, 0xF94),
        )


class LinkPipe:
    """Byte-paced current-loop transport matching PIC18F2550 EUSART.

    Real EUSART has a 2-byte RCREG FIFO (PIC18F2550 §20.2.2).  No flow
    control exists on the current-loop wire: if the receiver can't keep
    up, bytes are lost (overrun / OERR).

    Each byte occupies ``byte_cycles`` instruction cycles on the wire
    (320 µs at 31,250 baud 8N1 → 960 Tcy at 3 MIPS).  Frames are
    enqueued as three individual bytes with inter-byte wire-rate spacing.

    ``fifo_depth`` caps how many bytes the pump will inject into the sink
    per call — modelling the hardware constraint that the RCREG FIFO
    can only accumulate a few bytes between firmware reads.  Bytes whose
    delivery cycle has passed but can't be injected are counted as
    overruns (equivalent to OERR on real silicon).
    """

    def __init__(
        self, name: str, *, byte_cycles: int, fifo_depth: int = EUSART_FIFO_DEPTH
    ) -> None:
        self.name = name
        self.byte_cycles = max(1, byte_cycles)
        self.fifo_depth = max(1, fifo_depth)
        # Queue items: (deliver_cycle, [route, cmd, data]).
        # deliver_cycle is when the LAST byte of the frame finishes on wire.
        self.queue: Deque[tuple[int, List[int]]] = deque()
        self._next_tx_cycle = 0
        self.delivered_frames_last = 0
        self.delivered_wake_last = 0
        self.overrun_frames_last = 0
        self.overrun_wake_last = 0
        self.overrun_last = 0
        self.overrun_total = 0
        self.delivered_last = 0
        self.delivered_total = 0

    def __len__(self) -> int:
        return len(self.queue)

    def enqueue(self, frame: TxTriplet) -> None:
        """Schedule a 3-byte frame with wire-rate pacing.

        The frame is deliverable when the last byte finishes transmission.
        Wire time = 3 × byte_cycles from the start of the first byte.
        """
        # TUI robustness: filename requests (route=0xB1, cmd=0x22/0x21) are
        # idempotent "latest state" pulls. If the user toggles presets
        # rapidly, keep only the newest queued request to avoid storms.
        if frame.route == 0xB1 and frame.cmd in (0x21, 0x22):
            filtered: Deque[tuple[int, List[int]]] = deque()
            for deliver_cycle, frame_bytes in self.queue:
                if frame_bytes[0] == 0xB1 and frame_bytes[1] == frame.cmd:
                    continue
                filtered.append((deliver_cycle, frame_bytes))
            if len(filtered) != len(self.queue):
                self.queue = filtered
                self._next_tx_cycle = max(
                    int(frame.cycle),
                    self.queue[-1][0] if self.queue else int(frame.cycle),
                )

        start = max(int(frame.cycle), self._next_tx_cycle)
        last_byte_done = start + 3 * self.byte_cycles
        self._next_tx_cycle = last_byte_done
        self.queue.append((last_byte_done, [frame.route, frame.cmd, frame.data]))

    def pump(self, now_cycle: int, sink: object, *, max_inject: int = 256) -> int:
        """Deliver complete frames whose wire time has elapsed.

        Frames are injected atomically (all 3 bytes or none) to preserve
        parser framing.  If the ring buffer doesn't have room for 3 bytes,
        the entire frame is counted as an overrun — matching the real
        scenario where OERR would corrupt framing anyway.
        """
        ready: List[List[int]] = []
        while self.queue and len(ready) < max_inject:
            deliver_cycle, frame_bytes = self.queue[0]
            if deliver_cycle > now_cycle:
                break
            ready.append(frame_bytes)
            self.queue.popleft()

        if not ready:
            self.delivered_last = 0
            self.overrun_last = 0
            self.delivered_frames_last = 0
            self.delivered_wake_last = 0
            self.overrun_frames_last = 0
            self.overrun_wake_last = 0
            return 0

        delivered, overruns = sink.inject_frames_fifo(ready, self.fifo_depth)
        self.delivered_last = delivered
        self.delivered_total += delivered
        self.overrun_last = overruns
        self.overrun_total += overruns
        delivered_frames = delivered // 3
        ready_count = len(ready)
        self.delivered_frames_last = delivered_frames
        self.overrun_frames_last = max(0, ready_count - delivered_frames)
        self.delivered_wake_last = 0
        self.overrun_wake_last = 0
        for idx, frame in enumerate(ready):
            if frame[1] != WAKE_CMD or frame[2] != WAKE_DATA:
                continue
            if idx < delivered_frames:
                self.delivered_wake_last += 1
            else:
                self.overrun_wake_last += 1
        return delivered


RECONNECT_WINDOW_CYCLES = 700_000
RECONNECT_WINDOW_EVENTS = 5
PARSER_IDLE_STREAK_LIMIT = 12
NO_REPLY_STREAK_LIMIT = 12
POLL_ONLY_STREAK_LIMIT = 12
MAILBOX_FULL_STREAK_LIMIT = 4


def _ring_used(rd: int, wr: int) -> int:
    return (wr - rd) & 0xFF


def _ring_delta(new: int, old: int) -> int:
    return (new - old) & 0xFF


def _is_waiting_lcd(lcd: tuple[str, str]) -> bool:
    return "WAITING FOR DLCP" in lcd[0].upper() or "WAITING FOR DLCP" in lcd[1].upper()


def _format_bit1_events(events: Deque[tuple[int, int, int]]) -> str:
    if not events:
        return "none"
    return ", ".join(f"{old}->{new}@{cycle:08X}" for cycle, old, new in events)


def _collect_diag_reasons(diag: ReconnectDiagnostics) -> str:
    reasons: List[str] = []
    if diag.parser_idle_streak >= PARSER_IDLE_STREAK_LIMIT:
        reasons.append("parser silent")
    if diag.mailbox_full_streak >= MAILBOX_FULL_STREAK_LIMIT:
        reasons.append("mailbox full")
    if diag.no_reply_streak >= NO_REPLY_STREAK_LIMIT:
        reasons.append("no replies from MAIN0")
    if diag.poll_only_streak >= POLL_ONLY_STREAK_LIMIT:
        reasons.append("repeating poll-only")
    if not reasons:
        return "none"
    return ", ".join(reasons)


def _update_diagnostics(
    diag: ReconnectDiagnostics,
    *,
    cycle: int,
    lcd: tuple[str, str],
    ctl_mem: MemSnapshot,
    main0_mem: MainMemSnapshot,
    main1_mem: MainMemSnapshot,
    control_tx: List[TxTriplet],
    link_ctl_m0: LinkPipe,
    link_m0_ctl: LinkPipe,
    main0_depth: int,
) -> None:
    bit1 = 1 if (ctl_mem.flags >> 1) & 1 else 0
    if diag.bit1_prev is not None and bit1 != diag.bit1_prev:
        diag.bit1_events.append((cycle, diag.bit1_prev, bit1))
        if len(diag.bit1_events) >= RECONNECT_WINDOW_EVENTS:
            recent = [
                event
                for event in diag.bit1_events
                if cycle - event[0] <= RECONNECT_WINDOW_CYCLES
            ]
            if (
                len(recent) >= RECONNECT_WINDOW_EVENTS
                and cycle - diag.bit1_last_loop_cycle > RECONNECT_WINDOW_CYCLES // 2
            ):
                diag.bit1_reconnect_hits += 1
                diag.bit1_last_loop_cycle = cycle
    diag.bit1_prev = bit1

    waiting = _is_waiting_lcd(lcd)
    diag.waiting_streak = diag.waiting_streak + 1 if waiting else 0
    if waiting:
        diag.last_waiting_cycle = cycle

    main0_used = _ring_used(main0_mem.mb_rd, main0_mem.mb_wr)
    main1_used = _ring_used(main1_mem.mb_rd, main1_mem.mb_wr)
    diag.main0_mailbox_used = main0_used
    diag.main1_mailbox_used = main1_used
    diag.mailbox_full_streak = (
        diag.mailbox_full_streak + 1 if main0_used >= main0_depth - 2 else 0
    )

    main0_consumed = _ring_delta(main0_mem.mb_rd, diag.main0_rx_prev_rd)
    main1_consumed = _ring_delta(main1_mem.mb_rd, diag.main1_rx_prev_rd)
    diag.main0_rx_prev_rd = main0_mem.mb_rd
    diag.main1_rx_prev_rd = main1_mem.mb_rd
    diag.wake_consumed += main0_consumed + main1_consumed

    wake_frames = [f for f in control_tx if f.cmd == WAKE_CMD and f.data == WAKE_DATA]
    poll_frames = [f for f in control_tx if f.cmd == 0x04]
    diag.ctl_wake_tx_last = len(wake_frames)
    diag.ctl_poll_tx_last = len(poll_frames)
    diag.wake_sent += len(wake_frames)
    diag.wake_delivered += link_ctl_m0.delivered_wake_last
    diag.wake_dropped += link_ctl_m0.overrun_wake_last

    if waiting and (link_ctl_m0.delivered_frames_last == 0):
        diag.parser_idle_streak += 1
    elif not waiting:
        diag.parser_idle_streak = 0
    else:
        diag.parser_idle_streak = 0

    if waiting and poll_frames and not wake_frames:
        diag.poll_only_streak += 1
    else:
        diag.poll_only_streak = 0

    if waiting and (link_m0_ctl.delivered_frames_last == 0):
        diag.no_reply_streak += 1
    else:
        diag.no_reply_streak = 0

    diag.last_reason = _collect_diag_reasons(diag)


def _draw_diag_panel(
    stdscr: curses.window,
    y: int,
    x: int,
    ctl_mem: MemSnapshot,
    main0_mem: MainMemSnapshot,
    main1_mem: MainMemSnapshot,
    diag: ReconnectDiagnostics,
    *,
    single_main: bool,
) -> None:
    ctl_bit1 = (ctl_mem.flags >> 1) & 1
    status0 = "on" if (main0_mem.status_5e >> 3) & 1 else "off"
    status1 = "on" if (main1_mem.status_5e >> 3) & 1 else "off"
    _safe_addstr(stdscr, y, x, "Reconnect Diagnostics", curses.A_BOLD)
    _safe_addstr(
        stdscr,
        y + 1,
        x,
        f"CTL bit1={ctl_bit1}  status_5e bit3: M0={status0} M1={status1}",
    )
    _safe_addstr(
        stdscr,
        y + 2,
        x,
        f"events: {_format_bit1_events(diag.bit1_events)}",
    )
    _safe_addstr(
        stdscr,
        y + 3,
        x,
        f"reconnect hits={diag.bit1_reconnect_hits}  reason={diag.last_reason}",
    )
    _safe_addstr(
        stdscr,
        y + 4,
        x,
        f"wake sent={diag.wake_sent} delivered={diag.wake_delivered} dropped={diag.wake_dropped} consumed={diag.wake_consumed}",
    )
    _safe_addstr(
        stdscr,
        y + 5,
        x,
        (
            f"mailbox M0 used={diag.main0_mailbox_used} tx={main0_mem.mb_tx_wr:02X}"
            if single_main
            else f"mailbox M0 used={diag.main0_mailbox_used} tx={main0_mem.mb_tx_wr:02X}  M1 used={diag.main1_mailbox_used} tx={main1_mem.mb_tx_wr:02X}"
        ),
    )


class GpsimControlSession:
    def __init__(
        self,
        control_hex: Path,
        *,
        fast_boot: bool,
        chunk_cycles: int,
        hold_cycles: int,
        rx_fifo_limit: int = 6,
    ) -> None:
        if shutil.which("gpsim") is None:
            raise RuntimeError("gpsim not found in PATH")

        self.chunk_cycles = chunk_cycles
        self.hold_cycles = hold_cycles
        # CONTROL firmware uses a 48-byte ring at 0x066-0x095.
        # Since we bypass the ISR and write directly to the ring buffer,
        # the correct limit is the ring capacity (47 usable slots).
        self._rx_fifo_limit = min(max(1, rx_fifo_limit), 47)
        self._tmp = tempfile.TemporaryDirectory(prefix="gpsim_tui_")
        self.tmp_path = Path(self._tmp.name)
        self.sim_hex = self.tmp_path / "sim.hex"
        self.log_path = self.tmp_path / "gpsim.log"

        manifests = [control_reset_to_appstart()]
        if fast_boot:
            manifests.append(control_disable_boot_wait())
        manifests.append(control_disable_standby_check_for_hex(control_hex))
        apply_overlays(control_hex, self.sim_hex, manifests=manifests)

        self._gpsim = GpsimCliSession()
        self._issue = lambda c, t=10.0: self._gpsim.cmd(c, timeout_s=t)
        self.current_cycle = 0

        self.decoder = LiveLogDecoder()
        self.key_release: Dict[str, int] = {
            UP: 0,
            DOWN: 0,
            LEFT: 0,
            RIGHT: 0,
            SELECT: 0,
            STBY: 0,
        }
        self._prev_active: set[str] = set()

        self._boot()

    def _boot(self) -> None:
        self._issue("processor p18f2550", 5.0)
        self._issue(f"load {self.sim_hex}", 10.0)
        self._issue(f"frequency {CONTROL_FOSC_HZ}", 5.0)
        self._issue(f"log on {self.log_path}", 5.0)
        for reg in ("txreg", "portb", "lata"):
            self._issue(f"log w {reg}", 5.0)
        self._setup_button_stimuli()
        self._apply_key_levels(active=set())

    # gpsim pin names and stimulus names for the 6 button inputs.
    _BTN_STIMULI = [
        ("p18f2550.porta1", "stim_ra1"),  # SELECT (RA1)
        ("p18f2550.porta2", "stim_ra2"),  # DOWN   (RA2)
        ("p18f2550.porta3", "stim_ra3"),  # STBY   (RA3)
        ("p18f2550.porta4", "stim_ra4"),  # RIGHT  (RA4)
        ("p18f2550.portc0", "stim_rc0"),  # UP     (RC0)
        ("p18f2550.portc5", "stim_rc5"),  # LEFT   (RC5)
    ]

    def _setup_button_stimuli(self) -> None:
        """Create persistent gpsim stimuli for all button input pins.

        Register writes (porta=/portc=) do not survive firmware read-modify-
        write instructions on PORT registers.  Asynchronous stimuli drive
        the pin model directly, keeping input pins at a stable level even
        after btg/bsf/bcf on the PORT register.

        Note: ``period 0`` creates a dead stimulus (Vth=0V, Driving=IN).
        An explicit schedule entry ``{ 1, 1 }`` forces the stimulus into
        active-drive mode (Vth=5V) so the pin actually reads HIGH.
        """
        for pin_name, stim_name in self._BTN_STIMULI:
            self._issue(
                f"stimulus asynchronous_stimulus "
                f"initial_state 1 start_cycle 0 {{ 1, 1 }} "
                f"name {stim_name} end",
                5.0,
            )
            node_name = f"n_{stim_name}"
            self._issue(f"node {node_name}", 5.0)
            self._issue(f"attach {node_name} {pin_name} {stim_name}", 5.0)

    def close(self) -> None:
        try:
            self._issue("log off", 5.0)
        except Exception:
            pass
        self._gpsim.close()
        self._tmp.cleanup()

    def warmup(self, target_cycle: int) -> None:
        if target_cycle <= self.current_cycle:
            return
        self._run_to(target_cycle)
        self.decoder.ingest(self.log_path)

    def press(self, action: str) -> None:
        self.key_release[action] = max(
            self.key_release[action], self.current_cycle + self.hold_cycles
        )

    def inject_decoded_ir(self, cmd: int, *, addr: int | None = None) -> int:
        """Inject a decoded IR event through CONTROL ISR handoff registers."""
        ir_addr = _read_reg(self._issue, 0x020) if addr is None else (addr & 0xFF)
        self._issue("reg(0x01B)=0x00", 5.0)
        self._issue("reg(0x01C)=0x00", 5.0)
        self._issue(f"reg(0x01D)=0x{cmd & 0xFF:02X}", 5.0)
        self._issue(f"reg(0x01E)=0x{ir_addr:02X}", 5.0)
        flags = _read_reg(self._issue, 0x01F)
        self._issue(f"reg(0x01F)=0x{flags & 0xFE:02X}", 5.0)
        return ir_addr

    def inject_triplet(self, frame: TxTriplet) -> bool:
        return self.inject_bytes([frame.route, frame.cmd, frame.data])

    def inject_bytes(self, data: List[int]) -> bool:
        # CONTROL RX ring buffer is 0x066..0x095 (48 bytes), with rd=0x98/wr=0x99.
        rd = _read_reg(self._issue, 0x098)
        wr = _read_reg(self._issue, 0x099)
        used = (wr - rd) % 0x30
        if used > 0x2C:
            return False
        for b in data:
            addr = 0x066 + (wr % 0x30)
            self._issue(f"reg(0x{addr:03X})=0x{b & 0xFF:02X}", 5.0)
            wr = (wr + 1) % 0x30
        self._issue(f"reg(0x099)=0x{wr:02X}", 5.0)
        return True

    def inject_single_byte(self, byte_val: int) -> bool:
        """Inject one byte, respecting EUSART-accurate FIFO limit."""
        rd = _read_reg(self._issue, 0x098)
        wr = _read_reg(self._issue, 0x099)
        used = (wr - rd) % 0x30
        if used >= self._rx_fifo_limit:
            return False
        addr = 0x066 + (wr % 0x30)
        self._issue(f"reg(0x{addr:03X})=0x{byte_val & 0xFF:02X}", 5.0)
        self._issue(f"reg(0x099)=0x{(wr + 1) % 0x30:02X}", 5.0)
        return True

    def inject_frames_fifo(
        self, frames: List[List[int]], fifo_limit: int
    ) -> tuple[int, int]:
        """Inject complete frames with frame-aligned overrun semantics.

        Each frame is a list of bytes (typically 3: route, cmd, data).
        A frame is either fully delivered or fully dropped.

        Returns (delivered_bytes, overrun_bytes).
        """
        rd = _read_reg(self._issue, 0x098)
        wr = _read_reg(self._issue, 0x099)
        delivered = 0
        overruns = 0
        limit = min(fifo_limit, self._rx_fifo_limit)
        for frame in frames:
            used = (wr - rd) % 0x30
            free = limit - used
            if free < len(frame):
                overruns += len(frame)
                continue
            for b in frame:
                addr = 0x066 + (wr % 0x30)
                self._issue(f"reg(0x{addr:03X})=0x{b & 0xFF:02X}", 5.0)
                wr = (wr + 1) % 0x30
                delivered += 1
        if delivered > 0:
            self._issue(f"reg(0x099)=0x{wr:02X}", 5.0)
        return delivered, overruns

    def step(self) -> tuple[tuple[str, str], MemSnapshot, List[TxTriplet], int]:
        active = {k for k, rel in self.key_release.items() if rel > self.current_cycle}
        self._apply_key_levels(active=active)
        self._run_to(self.current_cycle + self.chunk_cycles)
        new_tx = self.decoder.ingest(self.log_path)
        mem = self.read_mem_snapshot()
        return self.decoder.lcd_lines, mem, new_tx, self.current_cycle

    def _run_to(self, target_cycle: int) -> None:
        delta = max(1, target_cycle - self.current_cycle)
        timeout_s = _sim_step_timeout(delta)
        self._issue(f"break c {target_cycle}", 5.0)
        out = self._issue("run", timeout_s)
        try:
            self.current_cycle = _parse_cycle(out)
        except Exception as exc:
            raise RuntimeError(
                f"unable to parse cycle after run (target={target_cycle}): {out[:200]!r}"
            ) from exc

    def _apply_key_levels(self, *, active: set[str]) -> None:
        """Inject button events into CONTROL firmware RAM.

        gpsim stimuli permanently drive all button pins HIGH (unpressed)
        to prevent phantom presses from read-modify-write side-effects
        on PORT registers (btg PORTC, RC1 at 0x0DCA).  Since stimulus
        state cannot be toggled at runtime, button presses are simulated
        by writing directly into function_023's debounce state machine:

        - 0x0BE (accepted scan): set to the desired scan pattern
        - 0x0BB (debounce counter): reset to 0 so the accepted scan
          survives at least 4 function_023 calls (the debounce threshold)
          before being overwritten by the real pin-read result (0x00).

        This triggers edge detection (0x0BE != 0x0BD) inside function_023,
        which sets 0x9A = scan_pattern.  function_042 then exits on
        0x9A != 0, and function_046 processes the button event.

        Only newly-pressed keys (rising edge) are injected; held keys
        do not generate repeat events (matching real hardware behaviour).
        """
        newly_pressed = active - self._prev_active
        self._prev_active = set(active)
        if not newly_pressed:
            return

        # Compute combined scan value for all newly-pressed buttons.
        scan = 0
        for key in newly_pressed:
            scan |= SCAN_BITS.get(key, 0)
        if scan == 0:
            return

        # Inject into function_023's debounce state: write the desired
        # scan to 0x0BE (accepted) and reset debounce counter 0x0BB to 0
        # so the next 4 function_023 calls don't overwrite our value.
        self._issue(f"reg(0x0BE)=0x{scan:02X}", 5.0)
        self._issue(f"reg(0x0BB)=0x00", 5.0)

    def read_mem_snapshot(self) -> MemSnapshot:
        def _read_name_cache(base: int) -> str:
            chars: List[str] = []
            for i in range(30):
                b = _read_reg(self._issue, base + i) & 0xFF
                if b in (0x00, 0xFF) or b < 0x20 or b > 0x7E:
                    b = 0x20
                chars.append(chr(b))
            return "".join(chars)

        flags = _read_reg(self._issue, 0x01F)
        input_sel = _read_reg(self._issue, 0x0B8)
        volume = _read_reg(self._issue, 0x0B9)
        unit_count = _read_reg(self._issue, 0x0A1)
        menu_state = _read_reg(self._issue, 0x0BF)
        setup_sel = _read_reg(self._issue, 0x0A5)
        bl_timeout = _read_reg(self._issue, 0x0A7)

        unit0 = UnitMemState(
            link=_read_reg(self._issue, 0x0E5),
            ch_src=[
                _read_reg(self._issue, 0x0C1),
                _read_reg(self._issue, 0x0C7),
                _read_reg(self._issue, 0x0CD),
                _read_reg(self._issue, 0x0D3),
                _read_reg(self._issue, 0x0D9),
                _read_reg(self._issue, 0x0DF),
            ],
        )
        unit1 = UnitMemState(
            link=_read_reg(self._issue, 0x0E6),
            ch_src=[
                _read_reg(self._issue, 0x0C2),
                _read_reg(self._issue, 0x0C8),
                _read_reg(self._issue, 0x0CE),
                _read_reg(self._issue, 0x0D4),
                _read_reg(self._issue, 0x0DA),
                _read_reg(self._issue, 0x0E0),
            ],
        )
        preset_name_a = _read_name_cache(0x180) if menu_state == 0x01 else ""
        preset_name_b = _read_name_cache(0x19E) if menu_state == 0x01 else ""
        return MemSnapshot(
            cycle=self.current_cycle,
            flags=flags,
            input_sel=input_sel,
            volume=volume,
            unit_count=unit_count,
            menu_state=menu_state,
            setup_sel=setup_sel,
            bl_timeout=bl_timeout,
            portc=_read_reg(self._issue, 0xF82),
            trisc=_read_reg(self._issue, 0xF94),
            latc=_read_reg(self._issue, 0xF8B),
            preset_name_a=preset_name_a,
            preset_name_b=preset_name_b,
            unit0=unit0,
            unit1=unit1,
        )


def _volume_db_text(v: int) -> str:
    db = int(v) - 0x60
    return f"{db:+d}.0 dB"


def _format_tx(f: TxTriplet) -> str:
    cmd_name = _cmd_label(f.cmd)
    extra = ""
    if f.cmd == 0x03:
        extra = f" {CTRL_DATA_LABELS.get(f.data, '')}".rstrip()
    elif f.cmd == 0x21:
        page = (f.data >> 1) & 0x03
        txn = (f.data >> 3) & 0x0F
        preset = "B" if (f.data & 0x01) else "A"
        extra = f" txn={txn} page={page} preset={preset}"
    elif f.cmd == 0x2F:
        page = (f.data >> 1) & 0x03
        txn = (f.data >> 3) & 0x0F
        preset = "B" if (f.data & 0x01) else "A"
        extra = f" txn={txn} page={page} preset={preset}"
    return (
        f"0x{f.cycle:08X} TX [{f.route:02X} {f.cmd:02X} {f.data:02X}] {cmd_name}{extra}"
    )


def _safe_addstr(stdscr: curses.window, y: int, x: int, s: str, attr: int = 0) -> None:
    h, w = stdscr.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    clipped = s[: max(0, w - x - 1)]
    if clipped:
        stdscr.addstr(y, x, clipped, attr)


def _draw_key(
    stdscr: curses.window,
    y: int,
    x: int,
    ch: str,
    label: str,
    *,
    pressed: bool,
) -> None:
    attr = curses.A_REVERSE if pressed else curses.A_NORMAL
    _safe_addstr(stdscr, y, x, f"[{ch}] {label}", attr)


def _draw_unit_panel(
    stdscr: curses.window, y: int, x: int, idx: int, mem: MainMemSnapshot
) -> None:
    signed_tgt = mem.vol_tgt[0] if mem.vol_tgt[0] < 0x80 else mem.vol_tgt[0] - 0x100
    signed_cur = mem.vol_cur[0] if mem.vol_cur[0] < 0x80 else mem.vol_cur[0] - 0x100
    _safe_addstr(stdscr, y, x, f"[DLCP #{idx}] main firmware RAM (gpsim)")
    _safe_addstr(
        stdscr,
        y + 1,
        x,
        f"Vol cur 0x66..69={mem.vol_cur} ({signed_cur:+d} dB)  tgt 0x6E..71={mem.vol_tgt} ({signed_tgt:+d} dB)",
    )
    _safe_addstr(
        stdscr,
        y + 2,
        x,
        f"Input(0x99)=0x{mem.input_99:02X}  Link(0x0C3)=0x{mem.link_c3:02X}  CMD(0xA2/0xA3)=0x{mem.cmd_a2:02X}/0x{mem.data_a3:02X}",
    )
    _safe_addstr(
        stdscr,
        y + 3,
        x,
        f"Ch cfg cur 0x60..65={mem.ch_cfg_cur}  shadow 0xA5..AA={mem.ch_cfg_shadow}",
    )
    _safe_addstr(
        stdscr,
        y + 4,
        x,
        f"Flags 0x5E=0x{mem.status_5e:02X} 0x7E=0x{mem.flags_7e:02X} 0x94=0x{mem.flags_94:02X} parser(0x98)=0x{mem.parser_98:02X}",
    )
    _safe_addstr(
        stdscr,
        y + 5,
        x,
        f"ADC AN0 ADRESH/L=0x{mem.adresh:02X}/0x{mem.adresl:02X} ADCON0=0x{mem.adcon0:02X}",
    )
    _safe_addstr(
        stdscr,
        y + 6,
        x,
        f"Mailbox rd/wr/txwr = 0x{mem.mb_rd:02X}/0x{mem.mb_wr:02X}/0x{mem.mb_tx_wr:02X}  RC0={(mem.portc & 1)} TRISC0={(mem.trisc & 1)} RC2={(mem.portc >> 2) & 1} TRISC2={(mem.trisc >> 2) & 1}",
    )


def _draw_help_overlay(stdscr: curses.window, start_y: int, x: int) -> None:
    lines = [
        "Simulator Notes",
        "h toggles this panel.",
        "Panels use live PIC RAM from gpsim (not behavioral stubs).",
        "MAIN RAM shown: 0x60..0x71, 0x99, 0xA5..AA, 0xC3, mailbox counters.",
        "Link topology: CONTROL<->DLCP#0<->DLCP#1 with DLCP#1 downstream terminated.",
        "Chain forwarding is strict-hop: CONTROL<->DLCP#0<->DLCP#1 (no direct #1->CONTROL).",
        "Current-loop RX pin model: MAIN RC0 is driven idle-high (pin-level).",
        "RC2 strap model: MAIN #0 high (local/control), MAIN #1 low (daisy-chain).",
        "MAIN AN0 can be force-driven with --main-RA0 and hotkeys 7/8/9.",
        "Hotkeys: 7->0x0000, 8->0x0228, 9->0x0FFF (applies to both MAIN units).",
        "Hotkeys: 1/2 inject decoded IR F1/F2 (0x38/0x39) to CONTROL.",
        "Hotkey: 3 simulates USB profile upload to active preset (random table + filename).",
        "Startup path is stock control firmware; serial is byte-paced at 31,250 baud.",
        f"EUSART model: byte_cyc={_byte_cycles(CONTROL_FOSC_HZ)} Tcy, FIFO depth={EUSART_FIFO_DEPTH}, overrun=drop.",
        "Timer3 modes: shim (faster), harness (external overflow model, higher fidelity).",
        "All links use overrun (OERR) semantics — no flow control on current-loop wire.",
        "Not modeled: TAS3108 analog/audio side effects, clipping, real I2C timing.",
    ]
    for i, line in enumerate(lines):
        _safe_addstr(
            stdscr, start_y + i, x, line, curses.A_BOLD if i == 0 else curses.A_NORMAL
        )


def run_tui(stdscr: curses.window, args: argparse.Namespace) -> int:
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)

    trace: Deque[str] = deque(maxlen=220)
    flash_until: Dict[str, float] = {}
    show_help = False
    status = "starting gpsim..."
    has_preset_screen_layout = _has_preset_screen_layout(args.hex.resolve())

    sim_quantum = max(1, args.sim_quantum_cycles) if args.sim_quantum_cycles > 0 else None
    control_chunk_cycles = (
        sim_quantum if sim_quantum is not None else args.chunk_cycles
    )
    main_chunk_cycles = (
        sim_quantum if sim_quantum is not None else args.main_chunk_cycles
    )

    control = GpsimControlSession(
        args.hex.resolve(),
        fast_boot=args.fast_boot,
        chunk_cycles=control_chunk_cycles,
        hold_cycles=args.hold_cycles,
        rx_fifo_limit=args.rx_fifo_limit,
    )
    single_main = args.single_main
    main_hexes = [p.resolve() for p in args.main_hex]
    if len(main_hexes) == 1:
        main_hexes = [main_hexes[0], main_hexes[0]]
    else:
        main_hexes = [main_hexes[0], main_hexes[1]]
    main0 = MainGpsimSession(
        main_hexes[0],
        gpasm=args.gpasm,
        chunk_cycles=main_chunk_cycles,
        tag="0",
        standby_mode=args.main0_standby,
        main_ra0_adc=args.main_ra0,
        rc2_mode=args.main0_rc2,
        timer3_mode=args.main_timer3,
        rx_fifo_limit=args.rx_fifo_limit,
    )
    main1 = (
        None
        if single_main
        else MainGpsimSession(
            main_hexes[1],
            gpasm=args.gpasm,
            chunk_cycles=main_chunk_cycles,
            tag="1",
            standby_mode=args.main1_standby,
            main_ra0_adc=args.main_ra0,
            rc2_mode=args.main1_rc2,
            timer3_mode=args.main_timer3,
            rx_fifo_limit=args.rx_fifo_limit,
        )
    )

    ra0_hotkeys = {"7": 0x0000, "8": 0x0228, "9": 0x0FFF}
    ir_hotkeys = {"1": IR_F1_CMD, "2": IR_F2_CMD}
    rng = random.Random()
    ra0_target_adc = int(args.main_ra0) & 0x0FFF
    main0.set_main_ra0_adc(ra0_target_adc)
    if main1 is not None:
        main1.set_main_ra0_adc(ra0_target_adc)
    pending_usb_upload: tuple[int | None, str, bytes, int] | None = None
    pending_usb_refresh = False
    pending_usb_refresh_preset = 0
    pending_usb_refresh_retries = 0

    # Byte-level pacing derived from oscillator and baud rate.
    # Each link uses the *transmitter's* clock for wire timing.
    ctl_byte_cyc = _byte_cycles(CONTROL_FOSC_HZ)   # 960 @ 12 MHz
    main_byte_cyc = _byte_cycles(MAIN_FOSC_HZ)     # 960 @ 12 MHz
    fifo = args.rx_fifo_limit

    link_ctl_m0 = LinkPipe(
        "CTL->M0", byte_cycles=ctl_byte_cyc, fifo_depth=fifo
    )
    link_m0_ctl = LinkPipe(
        "M0->CTL", byte_cycles=main_byte_cyc, fifo_depth=fifo
    )
    if single_main:
        link_m0_m1 = None
        link_m1_m0 = None
        all_links = (link_ctl_m0, link_m0_ctl)
    else:
        link_m0_m1 = LinkPipe(
            "M0->M1", byte_cycles=main_byte_cyc, fifo_depth=fifo
        )
        link_m1_m0 = LinkPipe(
            "M1->M0", byte_cycles=main_byte_cyc, fifo_depth=fifo
        )
        all_links = (link_ctl_m0, link_m0_ctl, link_m0_m1, link_m1_m0)

    runtime_control_chunk = control.chunk_cycles
    runtime_main_chunk = main0.chunk_cycles
    # In Preset/filename flows we run a finer simulation quantum to avoid
    # coarse-step RX bursts that can starve full 30-byte filename fetches.
    filename_flow_chunk = max(10_000, min(runtime_control_chunk, runtime_main_chunk, 30_000))

    def _set_runtime_quantum(control_chunk: int, main_chunk: int) -> None:
        control.chunk_cycles = control_chunk
        main0.chunk_cycles = main_chunk
        if main1 is not None:
            main1.chunk_cycles = main_chunk

    def _link_has_filename_traffic(link: LinkPipe | None) -> bool:
        if link is None:
            return False
        for _, frame_bytes in link.queue:
            cmd = frame_bytes[1] & 0xFF
            if cmd in (0x21, 0x22, 0x2F) or (0x30 <= cmd <= 0x37):
                return True
        return False

    def _filename_flow_active(ctl_mem: MemSnapshot) -> bool:
        if pending_usb_upload is not None or pending_usb_refresh:
            return True
        if has_preset_screen_layout and ctl_mem.menu_state == 0x01:
            return True
        if _link_has_filename_traffic(link_ctl_m0) or _link_has_filename_traffic(link_m0_ctl):
            return True
        if not single_main and (
            _link_has_filename_traffic(link_m0_m1) or _link_has_filename_traffic(link_m1_m0)
        ):
            return True
        return False

    def _control_rc1_level(mem: MemSnapshot) -> int:
        # RC1 is an output in normal runtime; fall back to sampled PORTC when input.
        if (mem.trisc & 0x02) == 0:
            return 1 if (mem.latc & 0x02) else 0
        return 1 if (mem.portc & 0x02) else 0

    # Byte-level pump: fifo_depth already limits injection per call.
    # No artificial max_burst needed — pacing is cycle-accurate.

    def _pump_pre_control(now_cycle: int) -> Dict[str, int]:
        if single_main:
            return {
                "m02c": link_m0_ctl.pump(now_cycle, control),
            }
        assert link_m1_m0 is not None
        return {
            "m12m0": link_m1_m0.pump(now_cycle, main0),
            "m02c": link_m0_ctl.pump(now_cycle, control),
        }

    def _pump_pre_main0(now_cycle: int) -> Dict[str, int]:
        return {
            "c2m0": link_ctl_m0.pump(now_cycle, main0),
        }

    def _pump_pre_main1(now_cycle: int) -> Dict[str, int]:
        if single_main:
            return {"m02m1": 0, "m02c": 0}
        assert link_m0_m1 is not None and main1 is not None
        return {
            "m02m1": link_m0_m1.pump(now_cycle, main1),
            "m02c": link_m0_ctl.pump(now_cycle, control),
        }

    def _pump_post_main1(now_cycle: int) -> Dict[str, int]:
        if single_main:
            return {"m12m0": 0}
        assert link_m1_m0 is not None
        return {
            "m12m0": link_m1_m0.pump(now_cycle, main0),
        }

    def _enqueue_control_tx(frames: List[TxTriplet]) -> None:
        for f in frames:
            trace.append(f"CTL  {_format_tx(f)}")
            if (f.route & 0xF0) == 0xB0:
                link_ctl_m0.enqueue(f)

    def _enqueue_main0_tx(frames: List[TxTriplet]) -> None:
        for f in frames:
            if single_main:
                # Terminated single-main topology: only BF (broadcast)
                # frames wrap back to CONTROL.  B0/B1 frames would go to
                # the next downstream unit which doesn't exist, so they
                # are silently dropped.
                if f.route == 0xBF:
                    link_m0_ctl.enqueue(f)
            elif f.route == 0xBF:
                link_m0_ctl.enqueue(f)
            elif (f.route & 0xF0) == 0xB0 and link_m0_m1 is not None:
                link_m0_m1.enqueue(f)

    def _enqueue_main1_tx(frames: List[TxTriplet]) -> None:
        for f in frames:
            if f.route == 0xBF and link_m1_m0 is not None:
                link_m1_m0.enqueue(f)
                trace.append(f"M1->M0 {_format_tx(f)}")
            else:
                trace.append(f"M1->TERM {_format_tx(f)}")

    _DUMMY_MAIN_SNAPSHOT = MainMemSnapshot(
        cycle=0,
        status_5e=0,
        flags_7e=0,
        parser_98=0,
        flags_94=0,
        cmd_a2=0,
        data_a3=0,
        link_c3=0,
        adcon0=0,
        adresh=0,
        adresl=0,
        input_99=0,
        vol_cur=(0, 0, 0, 0),
        vol_tgt=(0, 0, 0, 0),
        ch_cfg_cur=(0, 0, 0, 0, 0, 0),
        ch_cfg_shadow=(0, 0, 0, 0, 0, 0),
        mb_rd=0,
        mb_wr=0,
        mb_tx_wr=0,
        portc=0,
        trisc=0,
    )

    diagnostics = ReconnectDiagnostics()
    main0_depth = min(args.rx_fifo_limit, 63)

    # Heartbeat model -------------------------------------------------------
    # In real hardware, CONTROL toggles RC1 (heartbeat) every ~30 K
    # iterations inside function_042.  MAIN detects the toggle via
    # current-loop ADC and responds with BF/03/01 ("I'm active") plus
    # status frames that set bit3 via function_019.  This lets
    # function_042 exit, keeping the DISPLAY and RECONNECT loops alive.
    #
    # Because the simulator does not yet model the RC1→MAIN→response
    # feedback loop, we synthetically:
    #   1. Set bit3 before each CONTROL step (so function_042 can exit).
    #   2. Inject BF/03/01 into the M0→CTL link after each step (so the
    #      RECONNECT loop sees bit1=1 on the next pump).
    #
    # The heartbeat activates once the WAITING-loop sentinel variables
    # (0xB8, 0xB9, 0xA7, 0xA1) have all left their 0x80 initial value,
    # meaning MAIN has responded to the first round of queries.
    # We first wait for the firmware to *set* them to 0x80 (WAITING
    # entered) before looking for them to change (WAITING exit), so
    # that uninitialised RAM (0x00) doesn't trigger a false positive.
    # Keep CONTROL in the active UI loop from the first interactive step.
    # This matches harness behavior and avoids firmware-version-specific
    # WAITING/reconnect timing differences that can swallow key events.
    _waiting_entered = True
    _heartbeat_active = True
    _heartbeat_step = 0
    _HEARTBEAT_BF_INTERVAL = 5  # inject BF/03/01 every N steps (not every step)

    def _step_chain_once(
        last_ctl_cycle: int,
    ) -> tuple[
        tuple[str, str],
        MemSnapshot,
        MainMemSnapshot,
        MainMemSnapshot,
        int,
        Dict[str, int],
        List[TxTriplet],
        List[TxTriplet],
        List[TxTriplet],
    ]:
        nonlocal _waiting_entered, _heartbeat_active, _heartbeat_step
        delivered: Dict[str, int] = {}
        delivered.update(_pump_pre_control(last_ctl_cycle))

        # Heartbeat: set bit3 *before* the CONTROL step so that
        # function_042's exit check (bit3 != 0) succeeds immediately.
        if _heartbeat_active:
            _heartbeat_step += 1
            cur = _read_reg(control._issue, 0x01F)
            control._issue(f"reg(0x01F)=0x{cur | 0x08:02X}", 5.0)

        lcd_lines, ctl_mem, new_tx, cycle = control.step()
        _enqueue_control_tx(new_tx)

        # Heartbeat: inject BF/03/01 periodically (not every step) to
        # keep bit1=1 without flooding the M0->CTL link.  bit1 stays
        # latched in the DISPLAY loop, so infrequent refresh suffices.
        if _heartbeat_active and (_heartbeat_step % _HEARTBEAT_BF_INTERVAL == 0):
            if len(link_m0_ctl) < fifo - 6:
                link_m0_ctl.enqueue(
                    TxTriplet(cycle=cycle, route=0xBF, cmd=0x03, data=0x01)
                )

        # Detect WAITING-loop exit: first the firmware sets all four
        # sentinel vars to 0x80 (entered), then MAIN responses change
        # them (exit).  Two-phase detection avoids false positive from
        # uninitialised RAM (all zeros at reset).
        if not _heartbeat_active:
            w = (ctl_mem.input_sel, ctl_mem.volume,
                 ctl_mem.bl_timeout, ctl_mem.unit_count)
            if not _waiting_entered:
                if all(v == 0x80 for v in w):
                    _waiting_entered = True
            elif all(v != 0x80 for v in w):
                _heartbeat_active = True
        delivered.update(_pump_pre_main0(cycle))
        standby_bus = _control_rc1_level(ctl_mem)
        main0.set_standby_bus(standby_bus)
        if main1 is not None:
            main1.set_standby_bus(standby_bus)
        main_mem0, main_tx0 = main0.step()
        _enqueue_main0_tx(main_tx0)
        delivered.update(_pump_pre_main1(cycle))
        if main1 is not None:
            main_mem1, main_tx1 = main1.step()
            _enqueue_main1_tx(main_tx1)
        else:
            main_mem1 = _DUMMY_MAIN_SNAPSHOT
            main_tx1 = []
        delivered.update(_pump_post_main1(cycle))
        return (
            lcd_lines,
            ctl_mem,
            main_mem0,
            main_mem1,
            cycle,
            delivered,
            main_tx0,
            main_tx1,
            new_tx,
        )

    try:
        lcd_lines = ("                ", "Waiting for DLCP")
        _lcd_candidate = lcd_lines
        _lcd_candidate_streak = 1
        _ui_stable_names = {0: " " * 30, 1: " " * 30}
        _filename_rx_active = False
        _filename_rx_req = 0
        _filename_rx_next_idx = 0
        _filename_rx_stage = {
            0: bytearray(b" " * 30),
            1: bytearray(b" " * 30),
        }
        _filename_rx_mask = {0: 0, 1: 0}
        _filename_rx_txn = {0: -1, 1: -1}

        def _sanitize_filename_byte(v: int) -> int:
            b = v & 0xFF
            if b in (0x00, 0xFF) or b < 0x20 or b > 0x7E:
                return 0x20
            return b

        def _consume_filename_frames(frames: list[TxTriplet]) -> None:
            nonlocal _filename_rx_active, _filename_rx_req, _filename_rx_next_idx
            for frame in frames:
                if frame.route != 0xBF:
                    continue
                cmd = frame.cmd & 0xFF
                if cmd == 0x2F:
                    req = frame.data & 0xFF
                    page = (req >> 1) & 0x03
                    preset = req & 0x01
                    txn = (req >> 3) & 0x0F
                    if page == 0 or txn != _filename_rx_txn[preset]:
                        _filename_rx_stage[preset] = bytearray(b" " * 30)
                        _filename_rx_mask[preset] = 0
                        _filename_rx_txn[preset] = txn
                    _filename_rx_req = req
                    _filename_rx_next_idx = 0
                    _filename_rx_active = True
                    continue
                if cmd == 0x22:
                    # Generation metadata response (paired with context 0x2F).
                    # It does not carry filename bytes, so disarm chunk mode.
                    _filename_rx_active = False
                    _filename_rx_next_idx = 0
                    continue
                if not (0x30 <= cmd <= 0x37):
                    continue
                if not _filename_rx_active:
                    continue
                local_idx = cmd - 0x30
                if local_idx != _filename_rx_next_idx:
                    continue
                req = _filename_rx_req
                page = (req >> 1) & 0x03
                if page == 3 and local_idx > 5:
                    continue
                abs_idx = page * 8 + local_idx
                preset = req & 0x01
                if abs_idx < 30:
                    _filename_rx_stage[preset][abs_idx] = _sanitize_filename_byte(frame.data)
                page_done = (page < 3 and local_idx == 7) or (page == 3 and local_idx == 5)
                if page_done:
                    _filename_rx_mask[preset] |= 1 << page
                    _filename_rx_active = False
                    _filename_rx_next_idx = 0
                    if page == 3 and (_filename_rx_mask[preset] & 0x0F) == 0x0F:
                        _ui_stable_names[preset] = bytes(_filename_rx_stage[preset]).decode(
                            "ascii", "replace"
                        )
                else:
                    _filename_rx_next_idx += 1

        def _stable_lcd(new_lines: tuple[str, str]) -> tuple[str, str]:
            nonlocal _lcd_candidate, _lcd_candidate_streak, lcd_lines
            if new_lines == _lcd_candidate:
                _lcd_candidate_streak += 1
            else:
                _lcd_candidate = new_lines
                _lcd_candidate_streak = 1
            # Debounce one-step transient LCD write phases to avoid
            # rendering partial line updates during rapid key activity.
            if _lcd_candidate_streak >= 2:
                lcd_lines = new_lines
            return lcd_lines

        def _stabilize_preset_lcd(
            lines: tuple[str, str], mem: MemSnapshot
        ) -> tuple[str, str]:
            if not has_preset_screen_layout:
                return lines
            if mem.menu_state != 0x01:
                return lines

            preset_idx = 1 if (mem.flags & 0x40) else 0
            suffix = "B" if preset_idx else "A"
            stable = _ui_stable_names[preset_idx]
            if len(stable) != 30:
                stable = " " * 30
            return (stable[:14] + " " + suffix, stable[14:30])

        last_ctl_cycle = control.current_cycle
        target = max(0, int(args.initial_cycles))
        warmup_control_chunk = control.chunk_cycles
        warmup_main0_chunk = main0.chunk_cycles
        warmup_main1_chunk = main1.chunk_cycles if main1 is not None else None
        if args.sim_quantum_cycles > 0:
            startup_chunk = max(args.chunk_cycles, args.main_chunk_cycles)
            control.chunk_cycles = startup_chunk
            main0.chunk_cycles = startup_chunk
            if main1 is not None:
                main1.chunk_cycles = startup_chunk
        while control.current_cycle < target:
            (
                raw_lcd_lines,
                ctl_mem,
                main_mem0,
                main_mem1,
                cycle,
                _delivered,
                warmup_main_tx0,
                warmup_main_tx1,
                control_tx,
            ) = _step_chain_once(last_ctl_cycle)
            _consume_filename_frames(warmup_main_tx0)
            _consume_filename_frames(warmup_main_tx1)
            lcd_lines = _stable_lcd(raw_lcd_lines)
            lcd_lines = _stabilize_preset_lcd(lcd_lines, ctl_mem)
            _update_diagnostics(
                diagnostics,
                cycle=cycle,
                lcd=lcd_lines,
                ctl_mem=ctl_mem,
                main0_mem=main_mem0,
                main1_mem=main_mem1,
                control_tx=control_tx,
                link_ctl_m0=link_ctl_m0,
                link_m0_ctl=link_m0_ctl,
                main0_depth=main0_depth,
            )
            last_ctl_cycle = cycle
        (
            raw_lcd_lines,
            ctl_mem,
            main_mem0,
            main_mem1,
            cycle,
            _delivered,
            warmup_main_tx0,
            warmup_main_tx1,
            control_tx,
        ) = _step_chain_once(last_ctl_cycle)
        _consume_filename_frames(warmup_main_tx0)
        _consume_filename_frames(warmup_main_tx1)
        lcd_lines = _stable_lcd(raw_lcd_lines)
        lcd_lines = _stabilize_preset_lcd(lcd_lines, ctl_mem)
        _update_diagnostics(
            diagnostics,
            cycle=cycle,
            lcd=lcd_lines,
            ctl_mem=ctl_mem,
            main0_mem=main_mem0,
            main1_mem=main_mem1,
            control_tx=control_tx,
            link_ctl_m0=link_ctl_m0,
            link_m0_ctl=link_m0_ctl,
            main0_depth=main0_depth,
        )
        last_ctl_cycle = cycle
        status = f"running  cycle={cycle}"
        next_step_t = time.monotonic()
        if args.sim_quantum_cycles > 0:
            control.chunk_cycles = warmup_control_chunk
            main0.chunk_cycles = warmup_main0_chunk
            if main1 is not None and warmup_main1_chunk is not None:
                main1.chunk_cycles = warmup_main1_chunk
        runtime_control_chunk = control.chunk_cycles
        runtime_main_chunk = main0.chunk_cycles
        filename_flow_chunk = max(10_000, min(runtime_control_chunk, runtime_main_chunk, 30_000))

        while True:
            now = time.monotonic()
            did_press = False
            ch = stdscr.getch()
            if ch != -1:
                if ch in (ord("q"), 27):
                    break
                if ch in (ord("h"), ord("H")):
                    show_help = not show_help
                mapped = None
                if ch in (curses.KEY_UP,):
                    mapped = UP
                elif ch in (curses.KEY_DOWN,):
                    mapped = DOWN
                elif ch in (curses.KEY_LEFT,):
                    mapped = LEFT
                elif ch in (curses.KEY_RIGHT,):
                    mapped = RIGHT
                else:
                    c = chr(ch).lower() if 0 <= ch < 256 else ""
                    mapped = KEY_TO_ACTION.get(c)
                    if c:
                        flash_until[c] = now + 0.20
                        if c in ra0_hotkeys:
                            ra0_target_adc = ra0_hotkeys[c]
                            main0.set_main_ra0_adc(ra0_target_adc)
                            if main1 is not None:
                                main1.set_main_ra0_adc(ra0_target_adc)
                            trace.append(
                                f"0x{control.current_cycle:08X} RA0 both mains <= 0x{ra0_target_adc:03X}"
                            )
                            status = f"main_ra0=0x{ra0_target_adc:03X} cycle={control.current_cycle}"
                            did_press = True
                        elif c in ir_hotkeys:
                            ir_cmd = ir_hotkeys[c]
                            ir_addr = control.inject_decoded_ir(ir_cmd)
                            label = "F1" if ir_cmd == IR_F1_CMD else "F2"
                            trace.append(
                                f"0x{control.current_cycle:08X} IR inject {label} cmd=0x{ir_cmd:02X} addr=0x{ir_addr:02X}"
                            )
                            status = (
                                f"ir_{label.lower()} cmd=0x{ir_cmd:02X} addr=0x{ir_addr:02X} "
                                f"cycle={control.current_cycle}"
                            )
                            did_press = True
                        elif c == "3":
                            # Queue upload and resolve target preset when the
                            # control/main pair has had at least one step to settle.
                            hinted_preset = 1 if (ctl_mem.flags & 0x40) else 0
                            preset_name = "B" if hinted_preset else "A"
                            filename = _random_upload_filename(rng)
                            table_payload = bytes(rng.getrandbits(8) for _ in range(0xA00))
                            pending_usb_upload = (
                                None,
                                filename,
                                table_payload,
                                control.current_cycle,
                            )
                            trace.append(
                                f"0x{control.current_cycle:08X} USB-SIM queued preset {preset_name} "
                                f"filename={filename!r}"
                            )
                            status = (
                                f"usb_sim queued preset=pending({preset_name}) filename={filename} "
                                f"cycle={control.current_cycle}"
                            )
                            did_press = True
                if mapped:
                    control.press(mapped)
                    did_press = True
                    trace.append(f"0x{control.current_cycle:08X} KEY {mapped}")
                    status = f"key={mapped} cycle={control.current_cycle}"

            if did_press or now >= next_step_t:
                try:
                    ctl_chunk, main_chunk = _runtime_chunks_for_mode(
                        filename_flow_active=_filename_flow_active(ctl_mem),
                        runtime_control_chunk=runtime_control_chunk,
                        runtime_main_chunk=runtime_main_chunk,
                        filename_flow_chunk=filename_flow_chunk,
                    )
                    _set_runtime_quantum(ctl_chunk, main_chunk)
                    if pending_usb_upload is not None:
                        target_preset, up_filename, up_table_payload, queued_cycle = pending_usb_upload
                        if target_preset is None:
                            if control.current_cycle <= queued_cycle:
                                status = (
                                    f"usb_sim waiting target-sample cycle={control.current_cycle}"
                                )
                            else:
                                sampled = _control_active_preset(control._issue)
                                target_preset = sampled
                                pending_usb_upload = (
                                    target_preset,
                                    up_filename,
                                    up_table_payload,
                                    queued_cycle,
                                )
                                trace.append(
                                    f"0x{control.current_cycle:08X} USB-SIM target preset resolved "
                                    f"to {'B' if target_preset else 'A'}"
                                )
                        if target_preset is not None:
                            m0_synced = main0._active_preset_idx() == target_preset
                            if m0_synced:
                                digest0 = main0.simulate_usb_profile_upload(
                                    preset_idx=target_preset,
                                    table_payload_0xA00=up_table_payload,
                                    filename=up_filename,
                                )
                                digest1 = ""
                                if main1 is not None:
                                    digest1 = main1.simulate_usb_profile_upload(
                                        preset_idx=target_preset,
                                        table_payload_0xA00=up_table_payload,
                                        filename=up_filename,
                                    )
                                pending_usb_upload = None
                                pending_usb_refresh = True
                                pending_usb_refresh_preset = target_preset
                                pending_usb_refresh_retries = 2
                                _ui_stable_names[target_preset] = up_filename[:30].ljust(30)
                                preset_name = "B" if target_preset else "A"
                                trace.append(
                                    f"0x{control.current_cycle:08X} USB-SIM upload preset {preset_name} "
                                    f"filename={up_filename!r} table_sha=m0:{digest0}"
                                    + (f" m1:{digest1}" if digest1 else "")
                                )
                                status = (
                                    f"usb_sim preset={preset_name} filename={up_filename} "
                                    f"table_sha={digest0} cycle={control.current_cycle} refresh=queued"
                                )
                            else:
                                status = (
                                    f"usb_sim waiting preset-sync target={'B' if target_preset else 'A'} "
                                    f"m0={'B' if main0._active_preset_idx() else 'A'}"
                                    + f" cycle={control.current_cycle}"
                                )
                    if pending_usb_refresh:
                        # Wait for link drain before issuing one refresh request.
                        # This avoids request/token storms when '3' is pressed rapidly.
                        c2m0_idle = len(link_ctl_m0) == 0
                        m02c_idle = len(link_m0_ctl) == 0
                        if c2m0_idle and m02c_idle:
                            req_data = _next_filename_req_token(
                                _read_reg(control._issue, 0x029),
                                pending_usb_refresh_preset,
                            )
                            control._issue(f"reg(0x029)=0x{req_data:02X}", 5.0)
                            control._issue("reg(0x02E)=0x10", 5.0)
                            link_ctl_m0.enqueue(
                                TxTriplet(
                                    cycle=control.current_cycle,
                                    route=0xB1,
                                    cmd=0x22,
                                    data=req_data,
                                )
                            )
                            pending_usb_refresh = False
                            trace.append(
                                f"0x{control.current_cycle:08X} USB-SIM refresh kick txn={(req_data >> 3) & 0x0F} "
                                f"preset={'B' if (req_data & 0x01) else 'A'}"
                            )
                    (
                        raw_lcd_lines,
                        ctl_mem,
                        main_mem0,
                        main_mem1,
                        cycle,
                        delivered,
                        main_tx0,
                        main_tx1,
                        control_tx,
                    ) = _step_chain_once(last_ctl_cycle)
                    _consume_filename_frames(main_tx0)
                    _consume_filename_frames(main_tx1)
                    lcd_lines = _stable_lcd(raw_lcd_lines)
                    lcd_lines = _stabilize_preset_lcd(lcd_lines, ctl_mem)
                    _update_diagnostics(
                        diagnostics,
                        cycle=cycle,
                        lcd=lcd_lines,
                        ctl_mem=ctl_mem,
                        main0_mem=main_mem0,
                        main1_mem=main_mem1,
                        control_tx=control_tx,
                        link_ctl_m0=link_ctl_m0,
                        link_m0_ctl=link_m0_ctl,
                        main0_depth=main0_depth,
                    )
                    last_ctl_cycle = cycle

                    for f in main_tx0[-4:]:
                        trace.append(f"M0   {_format_tx(f)}")
                    for f in main_tx1[-4:]:
                        trace.append(f"M1   {_format_tx(f)}")
                    for link in all_links:
                        if link is not None and link.overrun_last:
                            trace.append(
                                f"OVERRUN {link.name} lost={link.overrun_last} total={link.overrun_total}"
                            )
                    if (
                        not pending_usb_refresh
                        and pending_usb_refresh_retries > 0
                        and link_m0_ctl.overrun_last > 0
                    ):
                        pending_usb_refresh = True
                        pending_usb_refresh_retries -= 1
                        trace.append(
                            f"0x{cycle:08X} USB-SIM refresh retry queued due to M0->CTL overrun"
                        )
                    if single_main:
                        status = (
                            f"running ctl=0x{cycle:08X} m0=0x{main_mem0.cycle:08X} "
                            f"q c2m0={len(link_ctl_m0)} m02c={len(link_m0_ctl)} "
                            f"d c2m0={delivered['c2m0']} m02c={delivered['m02c']} "
                            f"oerr c2m0={link_ctl_m0.overrun_total} m02c={link_m0_ctl.overrun_total} "
                            f"byte_cyc={ctl_byte_cyc} reason={diagnostics.last_reason}"
                        )
                    else:
                        assert link_m0_m1 is not None and link_m1_m0 is not None
                        status = (
                            f"running ctl=0x{cycle:08X} m0=0x{main_mem0.cycle:08X} m1=0x{main_mem1.cycle:08X} "
                            f"q c2m0={len(link_ctl_m0)} m02c={len(link_m0_ctl)} "
                            f"m02m1={len(link_m0_m1)} m12m0={len(link_m1_m0)} "
                            f"d c2m0={delivered['c2m0']} m02c={delivered['m02c']} "
                            f"m02m1={delivered['m02m1']} m12m0={delivered['m12m0']} "
                            f"oerr c2m0={link_ctl_m0.overrun_total} m02c={link_m0_ctl.overrun_total} "
                            f"m02m1={link_m0_m1.overrun_total} m12m0={link_m1_m0.overrun_total} "
                            f"reason={diagnostics.last_reason}"
                        )
                except Exception as exc:
                    trace.append(f"ERROR: {exc}")
                    status = f"error: {exc}"
                next_step_t = now + args.poll_s

            stdscr.erase()
            h, _ = stdscr.getmaxyx()
            _safe_addstr(stdscr, 0, 2, "DLCP gpsim TUI (control firmware)")
            _safe_addstr(stdscr, 1, 2, f"CONTROL HEX: {args.hex}")
            _safe_addstr(stdscr, 2, 2, status)
            if single_main:
                _safe_addstr(
                    stdscr,
                    3,
                    2,
                    f"MAIN HEX: {main_hexes[0].name} (single-unit mode)",
                )
            else:
                _safe_addstr(
                    stdscr,
                    3,
                    2,
                    f"MAIN HEX #0: {main_hexes[0].name}   MAIN HEX #1: {main_hexes[1].name}",
                )

            # LCD top-left.
            _safe_addstr(stdscr, 5, 2, "LCD:")
            _safe_addstr(stdscr, 6, 2, f"|{lcd_lines[0]:16}|")
            _safe_addstr(stdscr, 7, 2, f"|{lcd_lines[1]:16}|")
            _safe_addstr(
                stdscr,
                8,
                2,
                f"CTL RAM flags/input/vol/menu = 0x{ctl_mem.flags:02X}/0x{ctl_mem.input_sel:02X}/0x{ctl_mem.volume:02X}/0x{ctl_mem.menu_state:02X}",
            )
            _safe_addstr(
                stdscr,
                9,
                2,
                f"CTL RC1 bus PORTC/TRISC/LATC = {(ctl_mem.portc >> 1) & 1}/{(ctl_mem.trisc >> 1) & 1}/{(ctl_mem.latc >> 1) & 1}",
            )
            ra0_label = (
                "MAIN RA0 forced ADC" if single_main else "MAIN RA0 forced ADC (both)"
            )
            _safe_addstr(
                stdscr,
                10,
                2,
                f"{ra0_label} = 0x{ra0_target_adc:03X}   hotkeys: 7=0x0000 8=0x0228 9=0x0FFF",
            )
            # Keypad.
            _safe_addstr(stdscr, 5, 40, "Keys (visual feedback):")
            _draw_key(stdscr, 6, 50, "w", "up", pressed=flash_until.get("w", 0.0) > now)
            _draw_key(
                stdscr, 7, 43, "a", "left", pressed=flash_until.get("a", 0.0) > now
            )
            _draw_key(
                stdscr, 7, 53, "s", "select", pressed=flash_until.get("s", 0.0) > now
            )
            _draw_key(
                stdscr, 7, 65, "d", "right", pressed=flash_until.get("d", 0.0) > now
            )
            _draw_key(
                stdscr, 7, 76, "f", "stby", pressed=flash_until.get("f", 0.0) > now
            )
            down_pressed = (
                flash_until.get("x", 0.0) > now or flash_until.get("c", 0.0) > now
            )
            _draw_key(stdscr, 8, 50, "x", "down (c alias)", pressed=down_pressed)
            _safe_addstr(stdscr, 9, 40, "q=quit  h=toggle help  7/8/9=MAIN RA0  1/2=IR F1/F2  3=USB-SIM upload")

            _draw_unit_panel(stdscr, 12, 2, 0, main_mem0)
            if not single_main:
                _draw_unit_panel(stdscr, 19, 2, 1, main_mem1)

            _draw_diag_panel(
                stdscr,
                16,
                74,
                ctl_mem,
                main_mem0,
                main_mem1,
                diagnostics,
                single_main=single_main,
            )

            y_trace = 26
            if y_trace < h - 2:
                _safe_addstr(stdscr, y_trace, 2, "Trace (TX + keys):")
                rows = max(0, h - (y_trace + 2))
                tail = list(trace)[-rows:]
                for i, line in enumerate(tail):
                    _safe_addstr(stdscr, y_trace + 1 + i, 2, line)

            if show_help:
                _draw_help_overlay(stdscr, 10, 74)

            stdscr.refresh()

        return 0
    finally:
        if main1 is not None:
            main1.close()
        main0.close()
        control.close()


def parse_args() -> argparse.Namespace:
    def _parse_adc12(text: str) -> int:
        try:
            value = int(text, 0)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid ADC value: {text!r}") from exc
        if value < 0 or value > 0x0FFF:
            raise argparse.ArgumentTypeError("ADC value must be in range 0x000..0xFFF")
        return value

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("hex", type=Path, help="control firmware HEX path")
    ap.add_argument(
        "--main-hex",
        action="append",
        type=Path,
        required=True,
        help="main firmware HEX path (pass once to reuse for both mains, or twice for #0/#1)",
    )
    ap.add_argument(
        "--gpasm", default="gpasm", help="gpasm executable for simulation hook assembly"
    )
    ap.add_argument(
        "--chunk-cycles", type=int, default=300_000, help="cycles per simulation tick"
    )
    ap.add_argument(
        "--sim-quantum-cycles",
        type=int,
        default=0,
        help="if >0, force CONTROL and MAIN ticks to this shared small cycle quantum for sync",
    )
    ap.add_argument(
        "--main-chunk-cycles",
        type=int,
        default=300_000,
        help="cycles per main-unit simulation tick",
    )
    ap.add_argument(
        "--main0-standby",
        choices=("control", "auto", "hold", "release"),
        default="hold",
        help="MAIN #0 standby AN0 model: hold(high), release(low), control/auto(follow CONTROL RC1)",
    )
    ap.add_argument(
        "--main1-standby",
        choices=("control", "auto", "hold", "release"),
        default="hold",
        help="MAIN #1 standby AN0 model: hold(high), release(low), control/auto(follow CONTROL RC1)",
    )
    ap.add_argument(
        "--main-RA0",
        "--main-ra0",
        dest="main_ra0",
        type=_parse_adc12,
        default=0x0000,
        help="force MAIN AN0 ADC sample on both units (0x000..0xFFF), default 0x0000; runtime hotkeys 7/8/9",
    )
    ap.add_argument(
        "--main0-rc2",
        choices=("high", "low", "keep"),
        default="high",
        help="MAIN #0 RC2 strap model: high(local/control), low(chain), keep(firmware/gpsim default)",
    )
    ap.add_argument(
        "--main1-rc2",
        choices=("high", "low", "keep"),
        default="low",
        help="MAIN #1 RC2 strap model: high(local/control), low(chain), keep(firmware/gpsim default)",
    )
    ap.add_argument(
        "--main-timer3",
        choices=("shim", "harness"),
        default="shim",
        help="MAIN Timer3 mode: shim(function_079 patched) or harness(external TMR3IF model)",
    )
    ap.add_argument(
        "--hold-cycles",
        type=int,
        default=240_000,
        help="key hold pulse width in cycles",
    )
    ap.add_argument(
        "--initial-cycles",
        type=int,
        default=20_000_000,
        help="warm-up cycles at startup",
    )
    ap.add_argument(
        "--poll-s", type=float, default=0.15, help="UI polling interval in seconds"
    )
    ap.add_argument(
        "--fast-boot",
        action="store_true",
        help="optional sim acceleration: bypass one startup delay call in CONTROL firmware",
    )
    ap.add_argument(
        "--single-main",
        action="store_true",
        help="run with only one MAIN unit (terminated chain end); simplifies topology to CTL<->M0",
    )
    ap.add_argument(
        "--rx-fifo-limit",
        type=int,
        default=47,
        help=(
            "max bytes allowed in each RX mailbox before overrun (OERR). "
            "Since we bypass the ISR and inject directly into the firmware's "
            "software ring buffer, this should match the ring capacity "
            "(MAIN=63, CONTROL=47).  Default 47 (CONTROL ring size).  "
            "Byte-level pacing in LinkPipe already models the wire rate."
        ),
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if not args.hex.exists():
        raise SystemExit(f"HEX not found: {args.hex}")
    if len(args.main_hex) > 2:
        raise SystemExit("Pass --main-hex once or twice")
    for p in args.main_hex:
        if not p.exists():
            raise SystemExit(f"Main HEX not found: {p}")
    if shutil.which(args.gpasm) is None:
        raise SystemExit(f"gpasm not found: {args.gpasm}")
    return curses.wrapper(lambda stdscr: run_tui(stdscr, args))


if __name__ == "__main__":
    raise SystemExit(main())
