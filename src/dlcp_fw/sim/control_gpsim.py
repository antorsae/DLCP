"""Non-interactive gpsim harness for CONTROL firmware testing.

Provides a simplified, test-oriented API for booting the patched CONTROL
firmware under gpsim, pressing buttons, stepping the simulation, and
reading LCD / TX frame state.  Supports EEPROM file persistence via
gpsim's ``dump e`` / ``load e`` commands (Intel HEX format).

The harness includes a heartbeat model that keeps the firmware in DISPLAY
mode (bit1=1 in flags at 0x01F) and prevents function_042 from blocking
(bit3 injection).  Without actual MAIN units, the harness injects fake
BF/03/01 serial responses and forces the WAITING-phase sentinel vars to
transition, matching the TUI simulator's approach.

Adapted from ``GpsimControlSession`` in ``scripts/gpsim_tui_simulator.py``.
"""

from __future__ import annotations

import os
import pty
import re
import select
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .gpsim import require_gpsim_binary
from .ground_truth import record_event, snapshot_after_event
from .lcd import LcdByte, LcdState
from .manifests import (
    control_disable_boot_wait,
    control_disable_standby_check_for_hex,
    control_reset_to_appstart,
)
from .overlay import apply_overlays
from .paths import CONTROL_HEX_PATCHED


# ---------------------------------------------------------------------------
# Inline GpsimCliSession (matching scripts/gpsim_tui_simulator.py line 308)
# to avoid importing the full TUI module and its curses dependency.
# ---------------------------------------------------------------------------

_PROMPT = b"**gpsim>"
_CYCLE_RE = re.compile(r"^\s*0x([0-9A-Fa-f]+)\s+p18f[0-9A-Za-z]+", re.MULTILINE)
_REG_RE = re.compile(r"\[0x([0-9A-Fa-f]+)\]\s*=\s*0x([0-9A-Fa-f]+)")
_TX_RE = re.compile(r"Wr(?:ite|ote):\s+0x([0-9A-Fa-f]+)\s+to txreg", re.IGNORECASE)

CONTROL_FOSC_HZ = 12_000_000
CONTROL_GPSIM_PROCESSOR = "p18f25k20"

# Scan-bit mapping for function_023's debounced button result (1 = pressed).
SCAN_BITS: Dict[str, int] = {
    "STBY": 1 << 0,
    "UP": 1 << 1,
    "DOWN": 1 << 2,
    "SELECT": 1 << 3,
    "LEFT": 1 << 4,
    "RIGHT": 1 << 5,
}

# Short aliases for convenience
_KEY_ALIASES: Dict[str, str] = {
    "U": "UP",
    "D": "DOWN",
    "L": "LEFT",
    "R": "RIGHT",
    "S": "SELECT",
    "B": "STBY",
}

# Heartbeat model constants
_HEARTBEAT_BF_INTERVAL = 5  # inject BF/03/01 every N steps


class _CliSession:
    """Interactive gpsim subprocess wrapper (matching TUI's GpsimCliSession)."""

    def __init__(self, gpsim_bin: str) -> None:
        master_fd, slave_fd = pty.openpty()
        self.proc = subprocess.Popen(
            [gpsim_bin, "-i"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)
        self.fd = master_fd
        self.buf = b""
        self._read_until_prompt(timeout_s=8.0, require=None)

    def _read_available(self, timeout_s: float) -> bytes:
        ready, _, _ = select.select([self.fd], [], [], timeout_s)
        if not ready:
            return b""
        return os.read(self.fd, 4096)

    def _sync(self) -> None:
        settle = time.monotonic() + 0.02
        while True:
            timeout_s = max(0.0, settle - time.monotonic())
            data = self._read_available(timeout_s)
            if not data:
                break
            self.buf += data
            settle = time.monotonic() + 0.02
        idx = self.buf.rfind(_PROMPT)
        if idx >= 0:
            self.buf = self.buf[idx + len(_PROMPT):]

    def _read_until_prompt(
        self, *, timeout_s: float, require: bytes | None
    ) -> str:
        end = time.monotonic() + timeout_s
        saw_required = require is None
        while time.monotonic() < end:
            if not saw_required and require is not None and require in self.buf:
                saw_required = True
            idx = self.buf.find(_PROMPT)
            if saw_required and idx >= 0:
                settle = time.monotonic() + 0.02
                while time.monotonic() < settle:
                    data = self._read_available(0.0)
                    if not data:
                        break
                    self.buf += data
                    if not saw_required and require is not None and require in self.buf:
                        saw_required = True
                last = self.buf.rfind(_PROMPT)
                cut = last + len(_PROMPT)
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
        os.write(self.fd, (command + "\n").encode("ascii"))
        return self._read_until_prompt(timeout_s=timeout_s, require=None)

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
        try:
            os.close(self.fd)
        except OSError:
            pass


def _read_reg(issue, addr: int) -> int:
    for _ in range(3):
        out = issue(f"reg(0x{addr:03x})", 5.0)
        for m in _REG_RE.finditer(out):
            if int(m.group(1), 16) == addr:
                return int(m.group(2), 16) & 0xFF
        fallback = re.findall(r"=\s*0x([0-9A-Fa-f]+)", out)
        if fallback:
            return int(fallback[-1], 16) & 0xFF
        time.sleep(0.01)
    raise RuntimeError(f"unable to parse register 0x{addr:03X} value")


def _parse_cycle(output: str) -> int:
    m = _CYCLE_RE.search(output)
    if not m:
        raise RuntimeError("unable to parse cycle counter from gpsim output")
    return int(m.group(1), 16)


# ---------------------------------------------------------------------------
# Lightweight LCD + TX decoder (subset of LiveLogDecoder from TUI)
# ---------------------------------------------------------------------------


class _LogDecoder:
    """Incremental decoder for gpsim log file — LCD and TX frames."""

    _ins_re = re.compile(
        r"^0x([0-9A-Fa-f]+)\s+\S+\s+0x([0-9A-Fa-f]+)\s+0x([0-9A-Fa-f]+)\s+(.*)$"
    )
    _w_re = re.compile(r"Read:\s+0x([0-9A-Fa-f]+)\s+from W\(0x0FE8\)")

    def __init__(self) -> None:
        self.offset = 0
        self.partial = ""
        self.current_cycle: int | None = None
        self.rs = 0
        self.pending_nibble: tuple[int, int] | None = None
        self.first_nibble: tuple[int, int, int] | None = None
        self.lcd = LcdState.new()
        self.tx_pending: List[tuple[int, int]] = []
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

        m_tx = _TX_RE.search(line)
        if m_tx and self.current_cycle is not None:
            b = int(m_tx.group(1), 16) & 0xFF
            self.tx_pending.append((self.current_cycle, b))
            while True:
                route_idx = next(
                    (i for i, (_, x) in enumerate(self.tx_pending) if (x & 0xF0) == 0xB0),
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


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TxTriplet:
    cycle: int
    route: int
    cmd: int
    data: int


@dataclass(frozen=True)
class RxTriplet:
    route: int
    cmd: int
    data: int

    def normalized(self) -> "RxTriplet":
        return RxTriplet(
            route=self.route & 0xFF,
            cmd=self.cmd & 0xFF,
            data=self.data & 0xFF,
        )


@dataclass
class StepResult:
    lcd: tuple[str, str]
    new_tx: List[TxTriplet]
    cycle: int


# ---------------------------------------------------------------------------
# GpsimControlHarness
# ---------------------------------------------------------------------------

class GpsimControlHarness:
    """Non-interactive gpsim harness for CONTROL firmware.

    Includes a heartbeat model that:
    1. Injects BF/03/01 serial responses to simulate MAIN connection.
    2. Sets bit3 of 0x01F before each step so function_042 can exit.
    3. Uses two-phase WAITING detection (same as TUI simulator).

    Parameters
    ----------
    control_hex
        Path to the patched control HEX file.
    fast_boot
        If True, apply the boot-wait bypass overlay for faster startup.
    eeprom_file
        If given, load this Intel HEX EEPROM image before boot.
    chunk_cycles
        Instruction cycles per simulation step.
    hold_cycles
        How long a button press is held (in cycles).
    heartbeat_rx_mode
        RX injection policy after warmup: "full", "connected_only", or "none".
    heartbeat_force_connected
        If True, force CONNECTED bit (0x01F.1) high before each step.
    heartbeat_reset_idle
        If True, reset 0x09D:0x09E before each step (default behavior).
    disable_standby_check
        If True, apply the simulation-only overlay that bypasses the normal
        DISPLAY -> WAITING standby jump. Set False for robustness tests that
        must observe the real WAITING / reconnect path.
    """

    # gpsim pin names and stimulus names for the 6 button inputs.
    _BTN_STIMULI = [
        (f"{CONTROL_GPSIM_PROCESSOR}.porta1", "stim_ra1"),  # SELECT (RA1)
        (f"{CONTROL_GPSIM_PROCESSOR}.porta2", "stim_ra2"),  # DOWN   (RA2)
        (f"{CONTROL_GPSIM_PROCESSOR}.porta3", "stim_ra3"),  # STBY   (RA3)
        (f"{CONTROL_GPSIM_PROCESSOR}.porta4", "stim_ra4"),  # RIGHT  (RA4)
        (f"{CONTROL_GPSIM_PROCESSOR}.portc0", "stim_rc0"),  # UP     (RC0)
        (f"{CONTROL_GPSIM_PROCESSOR}.portc5", "stim_rc5"),  # LEFT   (RC5)
    ]

    def __init__(
        self,
        control_hex: Path | None = None,
        *,
        fast_boot: bool = True,
        eeprom_file: Path | None = None,
        chunk_cycles: int = 600_000,
        hold_cycles: int = 300_000,
        heartbeat_rx_mode: str = "full",
        heartbeat_force_connected: bool = False,
        heartbeat_reset_idle: bool = True,
        disable_standby_check: bool = True,
    ) -> None:
        if control_hex is None:
            control_hex = CONTROL_HEX_PATCHED

        self._gpsim_bin = require_gpsim_binary()
        self.chunk_cycles = chunk_cycles
        self.hold_cycles = hold_cycles
        self._eeprom_file = eeprom_file
        self._heartbeat_rx_mode = heartbeat_rx_mode
        self._heartbeat_force_connected = heartbeat_force_connected
        self._heartbeat_reset_idle = heartbeat_reset_idle
        self._disable_standby_check = disable_standby_check
        if self._heartbeat_rx_mode not in {"full", "connected_only", "none"}:
            raise ValueError(
                "heartbeat_rx_mode must be one of: 'full', 'connected_only', 'none'"
            )
        self._tmp = tempfile.TemporaryDirectory(prefix="gpsim_control_harness_")
        self.tmp_path = Path(self._tmp.name)
        self.sim_hex = self.tmp_path / "sim.hex"
        self.log_path = self.tmp_path / "gpsim.log"
        self.current_cycle = 0

        manifests = [control_reset_to_appstart()]
        if fast_boot:
            manifests.append(control_disable_boot_wait())
        if self._disable_standby_check:
            manifests.append(control_disable_standby_check_for_hex(control_hex))
        apply_overlays(control_hex, self.sim_hex, manifests=manifests)

        self._gpsim = _CliSession(self._gpsim_bin)
        self._issue = lambda c, t=10.0: self._gpsim.cmd(c, timeout_s=t)

        self._decoder = _LogDecoder()
        self._key_release: Dict[str, int] = dict.fromkeys(SCAN_BITS, 0)
        self._prev_active: set[str] = set()

        # Heartbeat model state
        self._heartbeat_enabled = True
        self._waiting_entered = False
        self._heartbeat_active = False
        self._heartbeat_step = 0

        self._boot()

    def _boot(self) -> None:
        self._issue(f"processor {CONTROL_GPSIM_PROCESSOR}", 5.0)
        self._issue(f"load {self.sim_hex}", 10.0)
        self._issue(f"frequency {CONTROL_FOSC_HZ}", 5.0)

        # Load EEPROM before execution starts.  gpsim defaults EEPROM to
        # 0x00, but real PIC18 hardware defaults to 0xFF.  When no custom
        # EEPROM file is provided, write 0xFF to key locations so the
        # firmware's range-check / clamp behaves identically to real
        # hardware on first boot.
        if self._eeprom_file is not None and self._eeprom_file.exists():
            self._load_eeprom_file(self._eeprom_file)
        else:
            self._load_default_eeprom()

        self._issue(f"log on {self.log_path}", 5.0)
        for reg in ("txreg", "portb", "lata"):
            self._issue(f"log w {reg}", 5.0)
        self._setup_button_stimuli()
        self._apply_key_levels(active=set())

    def _load_eeprom_file(self, path: Path) -> None:
        """Load EEPROM contents from an Intel HEX file."""
        from .hexio import parse_intel_hex

        mem = parse_intel_hex(path)
        # Prefer gpsim's native EEPROM loader for fidelity and speed.
        out = self._issue(f"load e {CONTROL_GPSIM_PROCESSOR} {path}", 10.0)
        lowered = out.lower()
        if "index" not in lowered and "error" not in lowered and "failed" not in lowered:
            return

        # Fallback path: direct SFR writes.
        for addr in range(256):
            val = mem.get(addr, 0xFF)
            if val != 0x00:  # skip gpsim-default zeros for speed
                self._eeprom_write(addr, val)

    def _load_default_eeprom(self) -> None:
        """Write 0xFF to key EEPROM locations (matching real hardware).

        gpsim initialises data EEPROM to 0x00, but real PIC18 hardware
        ships with EEPROM erased to 0xFF.  Rather than writing all
        256 bytes, only write bytes that directly affect preset boot
        behaviour in patched firmware:
        - EEPROM[0x74]: preset persistence byte (patched)
        - EEPROM[0x73]: stock BL-timeout byte (kept for fidelity)
        """
        self._eeprom_write(0x74, 0xFF)
        self._eeprom_write(0x73, 0xFF)

    def _eeprom_write(self, addr: int, value: int) -> None:
        """Write a single byte to data EEPROM via the PIC18 SFR sequence."""
        self._issue(f"reg(0xFA9)=0x{addr & 0xFF:02X}", 5.0)   # EEADR
        self._issue(f"reg(0xFA8)=0x{value & 0xFF:02X}", 5.0)   # EEDATA
        self._issue("reg(0xFA6)=0x04", 5.0)                     # EECON1: WREN
        self._issue("reg(0xFA7)=0x55", 5.0)                     # EECON2: unlock seq
        self._issue("reg(0xFA7)=0xAA", 5.0)                     # EECON2: unlock seq
        self._issue("reg(0xFA6)=0x06", 5.0)                     # EECON1: WREN+WR

    def _setup_button_stimuli(self) -> None:
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

    def _inject_rx_bytes(self, data: List[int]) -> bool:
        """Inject bytes into the CONTROL RX ring buffer (0x066..0x095)."""
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

    def _heartbeat_pre_step(self) -> None:
        """Set bit3 of 0x01F and reset idle timeout before each step.

        bit3 lets function_042 exit immediately.  Resetting the idle
        timeout counter (0x09D:0x09E) prevents the firmware's local
        reconnect logic from clearing CONNECTED (bit1) during the step.
        Without this, the firmware times out and re-enters the RECONNECT
        loop within a single chunk, showing 'Waiting for DLCP'.
        """
        if not self._heartbeat_enabled:
            return
        if self._heartbeat_active:
            self._heartbeat_step += 1
            cur = _read_reg(self._issue, 0x01F)
            mask = 0x08  # event-exit flag used by function_042
            if self._heartbeat_force_connected:
                mask |= 0x02  # force CONNECTED bit high for test determinism
            self._issue(f"reg(0x01F)=0x{cur | mask:02X}", 5.0)
            if self._heartbeat_reset_idle:
                # Reset idle timeout so the firmware stays in DISPLAY mode
                self._issue("reg(0x09D)=0xFF", 5.0)
                self._issue("reg(0x09E)=0xFF", 5.0)

    def _heartbeat_post_step(self) -> None:
        """Inject simulated MAIN responses after each step.

        Modes:
        - full: inject complete status set (volume/input/mute/source/timeout)
        - connected_only: inject only BF/03/01 (set CONNECTED)
        - none: no serial RX injection
        """
        if not self._heartbeat_enabled:
            return
        if self._heartbeat_active and (self._heartbeat_step % _HEARTBEAT_BF_INTERVAL == 0):
            if self._heartbeat_rx_mode == "full":
                # Full MAIN status response: function_050 sends 5 frames.
                self._inject_rx_bytes([
                    0xBF, 0x05, 0x33,  # volume = 0x33 (-45 dB)
                    0xBF, 0x07, 0x60,  # input  = 0x60 (Auto)
                    0xBF, 0x03, 0x01,  # mute   = off, sets CONNECTED
                    0xBF, 0x06, 0x00,  # source config
                    0xBF, 0x1D, 0x00,  # display/timeout
                ])
            elif self._heartbeat_rx_mode == "connected_only":
                self._inject_rx_bytes([0xBF, 0x03, 0x01])

    def _update_waiting_detection(self) -> None:
        """Detect DISPLAY mode entry to activate the heartbeat model.

        The TUI uses a two-phase sentinel-based detection (sentinels go
        0x00 → 0x80 → actual values), but that requires real MAIN
        responses.  Since the harness only injects BF/03/01, the
        sentinels stay at 0x80 forever.  Instead, detect DISPLAY mode
        directly via bit1 of flags register 0x01F, which the BF/03/01
        response sets.

        Before DISPLAY mode: also check for WAITING entered (sentinels
        = 0x80) so we know the firmware has passed the boot screen and
        is actively processing serial data.
        """
        if not self._heartbeat_enabled:
            return
        if self._heartbeat_active:
            return
        if not self._waiting_entered:
            w = (
                _read_reg(self._issue, 0x0B8),
                _read_reg(self._issue, 0x0B9),
                _read_reg(self._issue, 0x0A7),
                _read_reg(self._issue, 0x0A1),
            )
            if all(v == 0x80 for v in w):
                self._waiting_entered = True
        if self._waiting_entered:
            flags = _read_reg(self._issue, 0x01F)
            if flags & 0x02:  # bit1 = DISPLAY mode
                self._heartbeat_active = True
                # Force-set sentinel vars to plausible non-0x80 values so
                # the firmware's WAITING check succeeds.  Without a real
                # MAIN simulator these would stay at 0x80 forever.
                self._issue("reg(0x0B8)=0x00", 5.0)  # input_sel = Auto
                self._issue("reg(0x0B9)=0x33", 5.0)  # volume = default
                self._issue("reg(0x0A7)=0x01", 5.0)  # cmd1d_setting
                self._issue("reg(0x0A1)=0x01", 5.0)  # unit_count = 1

    def warmup(self, cycles: int) -> None:
        """Run simulation with heartbeat injection until past WAITING phase.

        Steps the simulation in large chunks, injecting BF/03/01 responses
        to transition through boot → WAITING → DISPLAY mode.  Uses larger
        chunks than normal stepping (2M vs chunk_cycles) for efficiency.

        The firmware boot sequence takes ~7M cycles to reach WAITING and
        ~19M cycles to enter DISPLAY mode.  Warmup stops early once
        DISPLAY mode is detected (bit1 of flags at 0x01F).
        """
        # Use larger chunks during warmup for efficiency (fewer gpsim
        # round-trips).  Normal step() uses self.chunk_cycles.
        warmup_chunk = max(self.chunk_cycles, 2_000_000)
        target = self.current_cycle + cycles
        while self.current_cycle < target:
            self._heartbeat_pre_step()
            self._run_to(min(self.current_cycle + warmup_chunk, target))
            self._decoder.ingest(self.log_path)
            self._heartbeat_post_step()
            self._update_waiting_detection()

            # Inject full MAIN status response during warmup to help the
            # firmware discover a MAIN unit and update sentinel vars.
            if not self._heartbeat_active:
                self._inject_rx_bytes([
                    0xBF, 0x05, 0x33,  # volume
                    0xBF, 0x07, 0x60,  # input
                    0xBF, 0x03, 0x01,  # connected
                    0xBF, 0x06, 0x00,  # source
                    0xBF, 0x1D, 0x00,  # timeout
                ])

            # Stop early once DISPLAY mode is reached (bit1 of 0x01F).
            if self._heartbeat_active:
                # Run extra chunks with full heartbeat support so the
                # LCD updates from "Waiting for DLCP" to the Volume screen.
                for _ in range(12):
                    self._heartbeat_pre_step()
                    self._run_to(min(self.current_cycle + self.chunk_cycles, target))
                    self._decoder.ingest(self.log_path)
                    self._heartbeat_post_step()
                break

    def pause_heartbeat(self) -> None:
        """Disable synthetic MAIN assistance while keeping current sim state."""
        self._heartbeat_enabled = False

    def resume_heartbeat(self) -> None:
        """Re-enable synthetic MAIN assistance after a deliberate blackout."""
        self._heartbeat_enabled = True

    def press(self, key: str) -> None:
        """Schedule a button press.

        Accepts full names (UP, DOWN, LEFT, RIGHT, SELECT, STBY) or
        single-letter aliases (U, D, L, R, S, B).
        """
        action = _KEY_ALIASES.get(key.upper(), key.upper())
        if action not in SCAN_BITS:
            raise ValueError(f"unknown key {key!r}")
        record_event(
            kind="press",
            harness="gpsim_control",
            payload={"key": key, "action": action},
        )
        self._key_release[action] = max(
            self._key_release[action], self.current_cycle + self.hold_cycles
        )
        snapshot_after_event("press", [self])

    def step(self) -> StepResult:
        """Advance simulation by one chunk with heartbeat injection."""
        self._heartbeat_pre_step()
        active = {k for k, rel in self._key_release.items() if rel > self.current_cycle}
        self._apply_key_levels(active=active)
        self._run_to(self.current_cycle + self.chunk_cycles)
        new_tx = self._decoder.ingest(self.log_path)
        self._heartbeat_post_step()
        self._update_waiting_detection()
        return StepResult(
            lcd=self._decoder.lcd_lines,
            new_tx=new_tx,
            cycle=self.current_cycle,
        )

    def lcd_lines(self) -> tuple[str, str]:
        """Return current LCD content (line1, line2)."""
        return self._decoder.lcd_lines

    def tx_frames(self) -> List[TxTriplet]:
        """Return all TX frames decoded so far."""
        return list(self._decoder.tx_frames)

    def read_reg(self, addr: int) -> int:
        """Read a single RAM/SFR register."""
        return _read_reg(self._issue, addr)

    @property
    def harness_id(self) -> str:
        """Stable identifier used by the ground-truth snapshotter."""
        return "control"

    def dump_state(self) -> tuple[bytes, dict[int, int]]:
        """Return (RAM bank 0, SFR map for top-of-bank-15) for snapshotting.

        Reads 0x000-0x0FF as RAM bank 0 (256 bytes; firmware-defined
        variables, RX/TX rings, IR debounce state, control flags, etc.)
        and 0xF60-0xFFF as the SFR area (160 entries; PORT/LAT/TRIS,
        ADC, MSSP/I²C, EUSART, timers, oscillator, IRQ, stack pointer
        and ALU state on the 2455/K20 layout).  Each register is read
        through the same `reg(0xXXX)` CLI path tests already use so
        the dump is consistent with what tests observe.
        """
        ram = bytes(_read_reg(self._issue, addr) for addr in range(0x000, 0x100))
        sfr = {addr: _read_reg(self._issue, addr) for addr in range(0xF60, 0x1000)}
        return ram, sfr

    def inject_bytes(self, data: List[int]) -> bool:
        """Inject raw bytes into the CONTROL RX ring buffer."""
        record_event(
            kind="inject_bytes",
            harness="gpsim_control",
            payload={"data": [b & 0xFF for b in data]},
        )
        ok = self._inject_rx_bytes(list(data))
        snapshot_after_event("inject_bytes", [self])
        return ok

    def inject_triplet(self, frame: TxTriplet) -> bool:
        """Inject one route/cmd/data triplet into the CONTROL RX ring buffer."""
        record_event(
            kind="inject_triplet",
            harness="gpsim_control",
            payload={"route": frame.route & 0xFF, "cmd": frame.cmd & 0xFF, "data": frame.data & 0xFF},
        )
        ok = self._inject_rx_bytes([frame.route, frame.cmd, frame.data])
        snapshot_after_event("inject_triplet", [self])
        return ok

    def inject_frames_fifo(
        self, frames: List[List[int]], fifo_limit: int
    ) -> tuple[int, int]:
        """Inject complete frames with frame-aligned overrun semantics.

        Each frame is a list of bytes (typically 3: route, cmd, data).
        A frame is either fully delivered or fully dropped.

        Returns (delivered_bytes, overrun_bytes).
        """
        record_event(
            kind="inject_frames_fifo",
            harness="gpsim_control",
            payload={
                "frames": [[b & 0xFF for b in f] for f in frames],
                "fifo_limit": fifo_limit,
            },
        )
        rd = _read_reg(self._issue, 0x098)
        wr = _read_reg(self._issue, 0x099)
        delivered = 0
        overruns = 0
        limit = min(max(1, fifo_limit), 47)
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
        snapshot_after_event("inject_frames_fifo", [self])
        return delivered, overruns

    def inject_host_commands(
        self,
        commands: List[RxTriplet],
        *,
        steps_per_command: int = 1,
    ) -> List[TxTriplet]:
        """Inject route/cmd/data triplets into CONTROL RX buffer.

        This is the public host-command injection harness used by gpsim
        tests to drive parser behavior without touching private internals.
        """
        record_event(
            kind="inject_host_commands",
            harness="gpsim_control",
            payload={
                "commands": [
                    {"route": c.route & 0xFF, "cmd": c.cmd & 0xFF, "data": c.data & 0xFF}
                    for c in commands
                ],
                "steps_per_command": steps_per_command,
            },
        )
        before = len(self._decoder.tx_frames)
        for raw in commands:
            frame = raw.normalized()
            ok = self._inject_rx_bytes([frame.route, frame.cmd, frame.data])
            if not ok:
                raise RuntimeError(
                    f"RX ring full while injecting frame "
                    f"route=0x{frame.route:02X} cmd=0x{frame.cmd:02X} data=0x{frame.data:02X}"
                )
            for _ in range(max(0, steps_per_command)):
                self.step()
        snapshot_after_event("inject_host_commands", [self])
        return self.tx_frames()[before:]

    def inject_host_command(
        self,
        *,
        cmd: int,
        data: int,
        route: int = 0xBF,
        steps: int = 1,
    ) -> List[TxTriplet]:
        """Inject one route/cmd/data triplet into CONTROL RX buffer."""
        return self.inject_host_commands(
            [RxTriplet(route=route, cmd=cmd, data=data)],
            steps_per_command=steps,
        )

    def inject_decoded_ir_event(
        self,
        *,
        cmd: int,
        addr: int,
        steps: int = 4,
        clear_debounce: bool = True,
    ) -> List[TxTriplet]:
        """Inject a decoded IR event through the ISR handoff registers.

        This bypasses RB5 waveform generation and directly writes:
        - 0x01D: decoded IR command
        - 0x01E: decoded IR address

        Then it clears 0x01F bit0 (IR_ARMED) so the foreground dispatch
        path (label_166) runs on the next step(s).
        """
        record_event(
            kind="inject_decoded_ir_event",
            harness="gpsim_control",
            payload={
                "cmd": cmd & 0xFF,
                "addr": addr & 0xFF,
                "steps": steps,
                "clear_debounce": bool(clear_debounce),
            },
        )
        if clear_debounce:
            self._issue("reg(0x01B)=0x00", 5.0)
            self._issue("reg(0x01C)=0x00", 5.0)
        self._issue(f"reg(0x01D)=0x{cmd & 0xFF:02X}", 5.0)
        self._issue(f"reg(0x01E)=0x{addr & 0xFF:02X}", 5.0)

        flags = self.read_reg(0x01F)
        self._issue(f"reg(0x01F)=0x{flags & 0xFE:02X}", 5.0)

        before = len(self._decoder.tx_frames)
        for _ in range(max(1, steps)):
            self.step()
        snapshot_after_event("inject_decoded_ir_event", [self])
        return self.tx_frames()[before:]

    def dump_eeprom(self, path: Path) -> None:
        """Save EEPROM contents to an Intel HEX file.

        gpsim's ``dump e`` command is not supported, so we read all 256
        EEPROM bytes via the PIC18 SFR interface and write a standard
        Intel HEX file.
        """
        data = bytearray(256)
        for addr in range(256):
            self._issue(f"reg(0xFA9)=0x{addr:02X}", 5.0)   # EEADR
            self._issue("reg(0xFA6)=0x01", 5.0)              # EECON1: RD
            data[addr] = _read_reg(self._issue, 0xFA8)        # EEDATA
        lines = [":020000040000FA"]
        for offset in range(0, 256, 16):
            chunk = data[offset : offset + 16]
            ll = len(chunk)
            total = ll + ((offset >> 8) & 0xFF) + (offset & 0xFF) + sum(chunk)
            cc = (~total + 1) & 0xFF
            lines.append(
                f":{ll:02X}{offset:04X}00{chunk.hex().upper()}{cc:02X}"
            )
        lines.append(":00000001FF")
        path.write_text("\n".join(lines) + "\n")

    def close(self) -> None:
        """Shut down the gpsim process and clean up temp files."""
        try:
            self._issue("log off", 5.0)
        except Exception:
            pass
        self._gpsim.close()
        self._tmp.cleanup()

    def _run_to(self, target_cycle: int) -> None:
        # gpsim's `break c N` can report cycle N-1 due to multi-cycle PIC18
        # instructions, but internally considers N reached.  A subsequent
        # `break c N` + `run` would hang forever.  Skip if within 1 cycle.
        if target_cycle <= self.current_cycle + 1:
            self.current_cycle = target_cycle
            return
        delta = target_cycle - self.current_cycle
        # Use generous timeout: gpsim with logging enabled can be quite slow.
        # The log-w for portb/lata/txreg adds significant overhead per cycle.
        timeout_s = max(15.0, delta / 100_000.0)
        self._issue(f"break c {target_cycle}", 5.0)
        out = self._issue("run", timeout_s)
        try:
            self.current_cycle = _parse_cycle(out)
        except Exception as exc:
            raise RuntimeError(
                f"unable to parse cycle after run (target={target_cycle}): {out[:200]!r}"
            ) from exc

    def _apply_key_levels(self, *, active: set[str]) -> None:
        """Inject button events via RAM writes to debounce state."""
        newly_pressed = active - self._prev_active
        self._prev_active = set(active)
        if not newly_pressed:
            return
        scan = 0
        for key in newly_pressed:
            scan |= SCAN_BITS.get(key, 0)
        if scan == 0:
            return
        self._issue(f"reg(0x0BE)=0x{scan:02X}", 5.0)
        self._issue("reg(0x0BB)=0x00", 5.0)
