"""One-main gpsim co-simulation harness for CONTROL<->MAIN link tests."""

from __future__ import annotations

import re
import tempfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, List

from .control_gpsim import (
    CONTROL_FOSC_HZ,
    GpsimControlHarness,
    TxTriplet,
    _CliSession,
    _LogDecoder,
    _parse_cycle,
    _read_reg,
)
from .gpsim import require_gpsim_binary
from .ground_truth import record_event, snapshot_after_event
from .hexio import parse_intel_hex
from .main_gpsim import (
    MAIN_FAULT_FLAGS_ADDR,
    MAIN_FAULT_MSSP_WAIT_STALL,
    MAIN_NATIVE_TIMEOUT_MSSP_SEED_ADDR,
    MAIN_NATIVE_TIMEOUT_SEED_OK,
    MAIN_NATIVE_TIMEOUT_SEED_TIMEOUT,
    MAIN_NATIVE_TIMEOUT_UART_SEED_ADDR,
    MAIN_FAULT_UART_TX_STALL,
    MAIN_GPSIM_PROCESSOR,
    MAIN_MAILBOX_TX_BASE,
    MAIN_UART_TRMT_BUSY_COUNT_ATTR,
    MAIN_UART_TRMT_BUSY_CYCLES_ATTR,
    MAIN_MSSP_STOP_BUSY_COUNT_ATTR,
    MAIN_MSSP_STOP_BUSY_CYCLES_ATTR,
    build_seeded_main_sim_hex,
    default_main_i2c_regfile_devices,
    probe_main_an0_boot_exit_cycle,
    resolve_main_an0_boot_exit_addr,
    write_main_an0_bootstrap_stc,
    write_main_i2c_regfile_stc,
)
from .manifests import (
    main_adc_boot_wait_hook,
    main_external_i2c_bypass_for_main_hex,
    main_reset_to_appstart,
    main_serial_mailbox_hooks_for_main_hex,
    main_v24_stall_test_hooks,
    main_v25_timeout_test_hooks,
)
from .overlay import apply_overlays

# Stock MAIN clock decode from PIC18F2455 config words:
# 12 MHz external clock input -> PLLDIV /3 -> 96 MHz PLL -> CPUDIV /6
# => 16 MHz Fosc, 4 MHz instruction clock, 1280 Tcy/byte at 31,250 baud.
MAIN_FOSC_HZ = 16_000_000
BAUD_RATE = 31_250
BITS_PER_BYTE = 10
EUSART_FIFO_DEPTH = 2
MAIN_NATIVE_RX_BASE = 0x0200
MAIN_NATIVE_RX_SIZE = 0xC0
_EXEC_BREAK_RE = re.compile(r"Execution at .*?\(0x([0-9A-Fa-f]+)\)")
_BP_EXEC_RE = re.compile(r"^\s*(\d+):\s+p18f[0-9A-Za-z]+\s+Execution at .*?\(0x([0-9A-Fa-f]+)\)", re.MULTILINE)
_REGFILE_RE = re.compile(
    r"(?:[A-Za-z0-9_]+\.)?reg([0-9A-Fa-f]{2})\s*=\s*(?:\$|0x)([0-9A-Fa-f]+)",
    re.IGNORECASE,
)
_MODULE_INT_RE = re.compile(
    r"(?:[A-Za-z0-9_]+\.)?([A-Za-z0-9_]+)\s*=\s*((?:\$|0x)?[0-9A-Fa-f]+)",
    re.IGNORECASE,
)
_SCALAR_HEX_RE = re.compile(r"^\s*(\$[0-9A-Fa-f]+|0x[0-9A-Fa-f]+|\d+)\s*$", re.MULTILINE)


def _byte_cycles(fosc_hz: int, baud: int = BAUD_RATE) -> int:
    tcy_hz = fosc_hz // 4
    return int(BITS_PER_BYTE * tcy_hz / baud)


def _sim_step_timeout(delta_cycles: int) -> float:
    delta = max(1, int(delta_cycles))
    # Native-ring runs can spend noticeable wall time inside gpsim's internal
    # serial callbacks before the CLI prompt returns, especially with the V2.5
    # timeout-hook overlay enabled. A short sub-second timeout is too brittle.
    return max(15.0, delta / 100_000.0)


def _is_v25_timeout_hook_image(main_hex: Path) -> bool:
    mem = parse_intel_hex(main_hex)
    return (
        mem.get(0x5500) == 0x00
        and mem.get(0x5501) == 0x0E
        and mem.get(0x5502) == 0x0B
        and mem.get(0x5503) == 0x6E
        and mem.get(0x556E) == 0x00
        and mem.get(0x556F) == 0x0E
        and mem.get(0x5570) == 0x0B
        and mem.get(0x5571) == 0x6E
    )


def _is_waiting_lcd(lcd: tuple[str, str]) -> bool:
    return "WAITING FOR DLCP" in lcd[0].upper() or "WAITING FOR DLCP" in lcd[1].upper()


def _parse_breakpoints(output: str) -> dict[int, int]:
    out: dict[int, int] = {}
    for m in _BP_EXEC_RE.finditer(output):
        out[int(m.group(1))] = int(m.group(2), 16)
    return out


def _contains_exec_break(output: str, addr: int) -> bool:
    wanted = addr & 0xFFFF
    for m in _EXEC_BREAK_RE.finditer(output):
        if int(m.group(1), 16) & 0xFFFF == wanted:
            return True
    return False


def _add_break_exec(issue, addr: int) -> int:
    before = set(_parse_breakpoints(issue("break", 5.0)).keys())
    issue(f"break e 0x{addr:04X}", 5.0)
    after = set(_parse_breakpoints(issue("break", 5.0)).keys())
    new_ids = sorted(after - before)
    if len(new_ids) != 1:
        raise RuntimeError(f"failed to allocate execution breakpoint for 0x{addr:04X}")
    return new_ids[0]


def _clear_break(issue, bp_id: int) -> None:
    issue(f"clear {bp_id}", 5.0)


def _parse_regfile_value(output: str, addr: int) -> int:
    wanted = addr & 0xFF
    for m in _REGFILE_RE.finditer(output):
        if int(m.group(1), 16) == wanted:
            return int(m.group(2), 16) & 0xFF
    raise RuntimeError(f"missing regfile readback for reg{wanted:02x}")


def _parse_module_int_value(output: str, attr_name: str) -> int:
    wanted = attr_name.strip().lower()
    for match in _MODULE_INT_RE.finditer(output):
        if match.group(1).strip().lower() != wanted:
            continue
        value_text = match.group(2)
        base = 16 if value_text.lower().startswith("0x") or value_text.startswith("$") else 10
        return int(value_text.replace("$", "0x"), base) & 0xFFFFFFFF
    scalar_matches = list(_SCALAR_HEX_RE.finditer(output))
    if scalar_matches:
        value_text = scalar_matches[-1].group(1)
        base = 16 if value_text.lower().startswith("0x") or value_text.startswith("$") else 10
        return int(value_text.replace("$", "0x"), base) & 0xFFFFFFFF
    raise RuntimeError(f"missing module attribute readback for {attr_name}")


@dataclass(frozen=True)
class MainChainSnapshot:
    cycle: int
    status_5e: int
    flags_7e: int
    mailbox_rd: int
    mailbox_wr: int
    mailbox_tx_wr: int
    fault_flags: int
    transport_mode: str


@dataclass(frozen=True)
class ChainStepResult:
    lcd: tuple[str, str]
    control_flags: int
    control_tx: List[TxTriplet]
    main_tx: List[TxTriplet]
    cycle: int
    main: MainChainSnapshot


class _MainStandbyPinModel:
    """Harness-level AN0/ADC model for MAIN standby sensing."""

    def __init__(self, mode: str, *, manual_adc: int | None = None) -> None:
        self.mode = mode
        self._bus_high = 0
        self._manual_adc = self._clamp_adc(manual_adc) if manual_adc is not None else None

    @staticmethod
    def _clamp_adc(v: int) -> int:
        if v < 0:
            return 0
        if v > 0x0FFF:
            return 0x0FFF
        return v

    def set_bus_level(self, high: int) -> None:
        self._bus_high = 1 if high else 0

    def target_adc(self) -> int:
        if self._manual_adc is not None:
            return self._manual_adc
        if self.mode == "hold":
            return 0x0230
        if self.mode == "release":
            return 0x0220
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
        if adcon0 & 0x02:
            issue(f"reg(0xFC2)=0x{adcon0 & 0xFD:02X}", 5.0)
        porta = _read_reg(issue, 0xF80)
        desired_ra0 = 1 if adc >= 0x0228 else 0
        if (porta & 0x01) != desired_ra0:
            issue(f"porta=0x{(porta & 0xFE) | desired_ra0:02X}", 5.0)


class _MainCurrentLoopPinModel:
    """Harness-level current-loop pin model (RC0 link idle + RC2 strap)."""

    def __init__(self, idle_high: bool = True, rc2_mode: str = "keep") -> None:
        self.idle_high = idle_high
        self.rc2_mode = rc2_mode

    def apply(self, issue) -> None:
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


class MainChainHarness:
    """Persistent gpsim harness for one MAIN unit on the serial chain."""

    def __init__(
        self,
        main_hex: Path,
        *,
        gpasm: str = "gpasm",
        chunk_cycles: int = 200_000,
        tag: str = "0",
        standby_mode: str = "hold",
        main_ra0_adc: int | None = None,
        rc2_mode: str = "high",
        rx_fifo_limit: int = 47,
        bypass_i2c: bool = False,
        transport_mode: str = "mailbox",
        enable_timeout_test_hooks: bool = False,
    ) -> None:
        if transport_mode not in {"mailbox", "native_ring"}:
            raise ValueError("transport_mode must be 'mailbox' or 'native_ring'")

        self.main_hex = Path(main_hex)
        self._gpsim_bin = require_gpsim_binary()
        self.chunk_cycles = chunk_cycles
        self._rx_fifo_limit = min(max(1, rx_fifo_limit), 63)
        self.transport_mode = transport_mode
        self._fault_flags_addr = MAIN_FAULT_FLAGS_ADDR
        self._native_timeout_seed_addrs: tuple[int, int] | None = None
        self._fault_flags_value = 0
        self.tag = tag
        self._tmp = tempfile.TemporaryDirectory(prefix=f"gpsim_chain_main_{tag}_")
        self.tmp_path = Path(self._tmp.name)
        self.seeded_hex = self.tmp_path / "main_seeded.hex"
        self.sim_hex = self.tmp_path / "sim.hex"
        self.log_path = self.tmp_path / "gpsim.log"
        self.current_cycle = 0
        self.decoder = _LogDecoder()
        self._mailbox_tx_partial: List[int] = []
        self.standby_model = _MainStandbyPinModel(standby_mode, manual_adc=main_ra0_adc)
        # Native-ring chain tests now use a real AN0 bootstrap only for the
        # default active/high standby model. Forcing AN0 low here makes MAIN's
        # first BF/03 status report "standby" and breaks CONTROL reconnect.
        self._use_native_an0_bootstrap = (
            self.transport_mode == "native_ring"
            and standby_mode == "hold"
            and main_ra0_adc is None
        )
        self._native_an0_boot_pending = self._use_native_an0_bootstrap
        self._main_boot_exit_addr = (
            resolve_main_an0_boot_exit_addr(self.main_hex)
            if self._use_native_an0_bootstrap
            else None
        )
        self._boot_bp_id: int | None = None
        self._boot_handoff_cycle = 0
        self._uses_adc_boot_wait_hook = False
        self._i2c_regfile_devices = [] if bypass_i2c else default_main_i2c_regfile_devices()
        self._uses_external_i2c_regfile_bus = bool(self._i2c_regfile_devices)
        self.current_loop_model = _MainCurrentLoopPinModel(idle_high=True, rc2_mode=rc2_mode)

        manifests = [main_reset_to_appstart()]
        if self.transport_mode == "mailbox":
            if bypass_i2c:
                manifests.append(main_external_i2c_bypass_for_main_hex(self.main_hex))
            manifests.append(main_serial_mailbox_hooks_for_main_hex(self.main_hex, gpasm=gpasm))
        else:
            if not self._use_native_an0_bootstrap:
                manifests.append(main_adc_boot_wait_hook(gpasm=gpasm))
                self._uses_adc_boot_wait_hook = True
            if enable_timeout_test_hooks:
                if _is_v25_timeout_hook_image(self.main_hex):
                    manifests.append(main_v25_timeout_test_hooks(gpasm=gpasm))
                else:
                    manifests.append(main_v24_stall_test_hooks(gpasm=gpasm))
                self._native_timeout_seed_addrs = (
                    MAIN_NATIVE_TIMEOUT_UART_SEED_ADDR,
                    MAIN_NATIVE_TIMEOUT_MSSP_SEED_ADDR,
                )
            if bypass_i2c:
                manifests.append(main_external_i2c_bypass_for_main_hex(self.main_hex))
        build_seeded_main_sim_hex(main_hex, self.seeded_hex)
        apply_overlays(self.seeded_hex, self.sim_hex, manifests=manifests)

        self._gpsim = _CliSession(self._gpsim_bin)
        self._issue = lambda c, t=10.0: self._gpsim.cmd(c, timeout_s=t)
        self._boot()

    def _boot(self) -> None:
        self._issue(f"processor {MAIN_GPSIM_PROCESSOR}", 5.0)
        self._issue(f"load {self.sim_hex}", 10.0)
        self._issue(f"frequency {MAIN_FOSC_HZ}", 5.0)
        if self._use_native_an0_bootstrap:
            assert self._main_boot_exit_addr is not None
            boot_exit_cycle = probe_main_an0_boot_exit_cycle(
                self.main_hex,
                boot_exit_addr=self._main_boot_exit_addr,
            )
            self._boot_handoff_cycle = (
                ((boot_exit_cycle + self.chunk_cycles - 1) // self.chunk_cycles) * self.chunk_cycles + 1
            )
            an0_stc = self.tmp_path / "main_an0_bootstrap.stc"
            write_main_an0_bootstrap_stc(
                an0_stc,
                post_boot_adc=self.standby_model.target_adc(),
                post_boot_cycle=self._boot_handoff_cycle,
                processor=MAIN_GPSIM_PROCESSOR,
            )
            self._issue(f"load {an0_stc}", 10.0)
            self._boot_bp_id = _add_break_exec(self._issue, self._main_boot_exit_addr)
        if self._i2c_regfile_devices:
            i2c_stc = self.tmp_path / "main_i2c_bus.stc"
            write_main_i2c_regfile_stc(
                i2c_stc,
                devices=self._i2c_regfile_devices,
                processor=MAIN_GPSIM_PROCESSOR,
            )
            self._issue(f"load {i2c_stc}", 10.0)
        self._issue(f"log on {self.log_path}", 5.0)
        self._issue("log w txreg", 5.0)
        if self.transport_mode == "mailbox":
            self._issue("reg(0x7C0)=0x00", 5.0)
            self._issue("reg(0x7C1)=0x00", 5.0)
            self._issue("reg(0x7C2)=0x00", 5.0)
            self._issue("reg(0x7C3)=0x00", 5.0)
        self._fault_flags_value = 0
        self._apply_fault_injection_state()
        self._apply_pin_models()

    def _apply_fault_injection_state(self) -> None:
        if self._native_timeout_seed_addrs is not None:
            uart_addr, mssp_addr = self._native_timeout_seed_addrs
            uart_seed = (
                MAIN_NATIVE_TIMEOUT_SEED_TIMEOUT
                if self._fault_flags_value & MAIN_FAULT_UART_TX_STALL
                else MAIN_NATIVE_TIMEOUT_SEED_OK
            )
            mssp_seed = (
                MAIN_NATIVE_TIMEOUT_SEED_TIMEOUT
                if self._fault_flags_value & MAIN_FAULT_MSSP_WAIT_STALL
                else MAIN_NATIVE_TIMEOUT_SEED_OK
            )
            self._issue(f"reg(0x{uart_addr:03X})=0x{uart_seed:02X}", 5.0)
            self._issue(f"reg(0x{mssp_addr:03X})=0x{mssp_seed:02X}", 5.0)
            return
        self._issue(f"reg(0x{self._fault_flags_addr:03X})=0x{self._fault_flags_value:02X}", 5.0)

    @property
    def uses_adc_boot_wait_hook(self) -> bool:
        return self._uses_adc_boot_wait_hook

    @property
    def uses_external_i2c_regfile_bus(self) -> bool:
        return self._uses_external_i2c_regfile_bus

    def read_i2c_regfile(self, device_name: str, addr: int) -> int:
        if not self._uses_external_i2c_regfile_bus:
            raise RuntimeError("external I2C regfile bus is not attached")
        output = self._issue(f"{device_name}.reg{addr & 0xFF:02x}", 5.0)
        return _parse_regfile_value(output, addr)

    def read_i2c_attribute(self, device_name: str, attr_name: str) -> int:
        if not self._uses_external_i2c_regfile_bus:
            raise RuntimeError("external I2C regfile bus is not attached")
        output = self._issue(f"{device_name}.{attr_name}", 5.0)
        return _parse_module_int_value(output, attr_name)

    def read_uart_attribute(self, attr_name: str) -> int:
        output = self._issue(attr_name, 5.0)
        return _parse_module_int_value(output, attr_name)

    def set_uart_fault(
        self,
        *,
        trmt_busy_cycles: int | None = None,
        trmt_busy_count: int | None = None,
    ) -> None:
        if trmt_busy_cycles is not None:
            self._issue(
                f"{MAIN_UART_TRMT_BUSY_CYCLES_ATTR} = {max(0, int(trmt_busy_cycles))}",
                5.0,
            )
        if trmt_busy_count is not None:
            self._issue(
                f"{MAIN_UART_TRMT_BUSY_COUNT_ATTR} = {max(-1, int(trmt_busy_count))}",
                5.0,
            )

    def clear_uart_faults(self) -> None:
        self.set_uart_fault(trmt_busy_cycles=0, trmt_busy_count=0)

    def set_mssp_stop_fault(
        self,
        *,
        stop_busy_cycles: int | None = None,
        stop_busy_count: int | None = None,
    ) -> None:
        if stop_busy_cycles is not None:
            self._issue(
                f"{MAIN_MSSP_STOP_BUSY_CYCLES_ATTR} = {max(0, int(stop_busy_cycles))}",
                5.0,
            )
        if stop_busy_count is not None:
            self._issue(
                f"{MAIN_MSSP_STOP_BUSY_COUNT_ATTR} = {max(-1, int(stop_busy_count))}",
                5.0,
            )

    def clear_mssp_stop_faults(self) -> None:
        self.set_mssp_stop_fault(stop_busy_cycles=0, stop_busy_count=0)

    def set_i2c_fault(
        self,
        device_name: str,
        *,
        address_nack_count: int | None = None,
        address_stretch_scl_cycles: int | None = None,
        address_stretch_count: int | None = None,
        data_nack_count: int | None = None,
        data_stuck_sda_cycles: int | None = None,
        data_stuck_sda_count: int | None = None,
        hold_scl_low: bool | None = None,
        stretch_scl_cycles: int | None = None,
    ) -> None:
        if not self._uses_external_i2c_regfile_bus:
            raise RuntimeError("external I2C regfile bus is not attached")
        if address_nack_count is not None:
            self._issue(
                f"{device_name}.Address_Nack_Count = {max(0, int(address_nack_count))}",
                5.0,
            )
        if address_stretch_scl_cycles is not None:
            self._issue(
                f"{device_name}.Address_Stretch_SCL_Cycles = {max(0, int(address_stretch_scl_cycles))}",
                5.0,
            )
        if address_stretch_count is not None:
            self._issue(
                f"{device_name}.Address_Stretch_Count = {max(-1, int(address_stretch_count))}",
                5.0,
            )
        if data_nack_count is not None:
            self._issue(
                f"{device_name}.Data_Nack_Count = {max(0, int(data_nack_count))}",
                5.0,
            )
        if data_stuck_sda_cycles is not None:
            self._issue(
                f"{device_name}.Data_Stuck_SDA_Cycles = {max(0, int(data_stuck_sda_cycles))}",
                5.0,
            )
        if data_stuck_sda_count is not None:
            self._issue(
                f"{device_name}.Data_Stuck_SDA_Count = {max(-1, int(data_stuck_sda_count))}",
                5.0,
            )
        if hold_scl_low is not None:
            raise RuntimeError(
                "runtime Hold_SCL_Low toggling is not supported by the current gpsim build"
            )
        if stretch_scl_cycles is not None:
            self._issue(
                f"{device_name}.Stretch_SCL_Cycles = {max(0, int(stretch_scl_cycles))}",
                5.0,
            )

    def clear_i2c_faults(self, device_name: str) -> None:
        self.set_i2c_fault(
            device_name,
            address_nack_count=0,
            address_stretch_scl_cycles=0,
            address_stretch_count=-1,
            data_nack_count=0,
            data_stuck_sda_cycles=0,
            data_stuck_sda_count=-1,
            stretch_scl_cycles=0,
        )

    def close(self) -> None:
        try:
            self._issue("log off", 5.0)
        except Exception:
            pass
        self._gpsim.close()
        self._tmp.cleanup()

    @property
    def harness_id(self) -> str:
        """Stable identifier for the ground-truth snapshotter.  Two
        MAINs in a wire chain get distinct ids ``main_0`` / ``main_1``
        from the constructor's `tag` argument."""
        return f"main_{self.tag}"

    def dump_state(self) -> tuple[bytes, dict[int, int]]:
        """Return (RAM bank 0, SFR map) for snapshotting.  Same shape
        as `GpsimControlHarness.dump_state` (256 B RAM at 0x000-0x0FF
        plus 0xF60-0xFFF SFR area on the 2455 layout)."""
        ram = bytes(_read_reg(self._issue, addr) for addr in range(0x000, 0x100))
        sfr = {addr: _read_reg(self._issue, addr) for addr in range(0xF60, 0x1000)}
        return ram, sfr

    def _apply_pin_models(self) -> None:
        self.current_loop_model.apply(self._issue)
        if not self._native_an0_boot_pending:
            self.standby_model.apply(self._issue)

    def set_standby_bus(self, high: int) -> None:
        self.standby_model.set_bus_level(high)

    def read_snapshot(self) -> MainChainSnapshot:
        if self.transport_mode == "mailbox":
            rx_rd = _read_reg(self._issue, 0x7C0)
            rx_wr = _read_reg(self._issue, 0x7C1)
            tx_wr = _read_reg(self._issue, 0x7C3)
        else:
            rx_rd = _read_reg(self._issue, 0x0C6)
            rx_wr = _read_reg(self._issue, 0x0C7)
            tx_wr = 0
        return MainChainSnapshot(
            cycle=self.current_cycle,
            status_5e=_read_reg(self._issue, 0x05E),
            flags_7e=_read_reg(self._issue, 0x07E),
            mailbox_rd=rx_rd,
            mailbox_wr=rx_wr,
            mailbox_tx_wr=tx_wr,
            fault_flags=self.fault_flags(),
            transport_mode=self.transport_mode,
        )

    def fault_flags(self) -> int:
        if self._native_timeout_seed_addrs is not None:
            return self._fault_flags_value
        return self._fault_flags_value

    def set_fault_flags(
        self,
        *,
        uart_tx_stall: bool | None = None,
        mssp_wait_stall: bool | None = None,
    ) -> int:
        flags = self.fault_flags()
        if uart_tx_stall is not None:
            if uart_tx_stall:
                flags |= MAIN_FAULT_UART_TX_STALL
            else:
                flags &= ~MAIN_FAULT_UART_TX_STALL
        if mssp_wait_stall is not None:
            if mssp_wait_stall:
                flags |= MAIN_FAULT_MSSP_WAIT_STALL
            else:
                flags &= ~MAIN_FAULT_MSSP_WAIT_STALL
        self._fault_flags_value = flags
        if self._native_timeout_seed_addrs is not None:
            self._apply_fault_injection_state()
        else:
            self._apply_fault_injection_state()
        return flags

    def clear_fault_flags(self) -> None:
        self._fault_flags_value = 0
        if self._native_timeout_seed_addrs is not None:
            self._apply_fault_injection_state()
        else:
            self._apply_fault_injection_state()

    def inject_frames_fifo(
        self, frames: List[List[int]], fifo_limit: int
    ) -> tuple[int, int]:
        # Record before injection.  Snapshot is taken after the
        # delivery completes so the captured state reflects post-write
        # RX-ring values.
        record_event(
            kind="inject_frames_fifo",
            harness="main_chain",
            payload={
                "frames": [[b & 0xFF for b in f] for f in frames],
                "fifo_limit": fifo_limit,
                "transport_mode": self.transport_mode,
            },
        )
        result = self._inject_frames_fifo_impl(frames, fifo_limit)
        snapshot_after_event("inject_frames_fifo", [self])
        return result

    def _inject_frames_fifo_impl(
        self, frames: List[List[int]], fifo_limit: int
    ) -> tuple[int, int]:
        if self.transport_mode == "native_ring":
            rd = _read_reg(self._issue, 0x0C6)
            wr = _read_reg(self._issue, 0x0C7)
            delivered = 0
            overruns = 0
            limit = min(max(1, fifo_limit), MAIN_NATIVE_RX_SIZE - 1)
            for frame in frames:
                used = (wr - rd) % MAIN_NATIVE_RX_SIZE
                free = limit - used
                if free < len(frame):
                    overruns += len(frame)
                    continue
                for b in frame:
                    addr = MAIN_NATIVE_RX_BASE + wr
                    self._issue(f"reg(0x{addr:03X})=0x{b & 0xFF:02X}", 5.0)
                    wr = (wr + 1) % MAIN_NATIVE_RX_SIZE
                    delivered += 1
            if delivered > 0:
                self._issue(f"reg(0x0C7)=0x{wr:02X}", 5.0)
            return delivered, overruns

        rd = _read_reg(self._issue, 0x7C0)
        wr = _read_reg(self._issue, 0x7C1)
        delivered = 0
        overruns = 0
        limit = min(max(1, fifo_limit), self._rx_fifo_limit)
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

    def _drain_mailbox_tx_frames(self) -> List[TxTriplet]:
        rd = _read_reg(self._issue, 0x7C2)
        wr = _read_reg(self._issue, 0x7C3)
        if rd == wr:
            return []

        new_frames: List[TxTriplet] = []
        cur = rd
        while cur != wr:
            addr = MAIN_MAILBOX_TX_BASE + (cur & 0x3F)
            self._mailbox_tx_partial.append(_read_reg(self._issue, addr))
            cur = (cur + 1) & 0xFF
            if len(self._mailbox_tx_partial) >= 3:
                route, cmd, data = self._mailbox_tx_partial[:3]
                new_frames.append(
                    TxTriplet(
                        cycle=self.current_cycle,
                        route=route & 0xFF,
                        cmd=cmd & 0xFF,
                        data=data & 0xFF,
                    )
                )
                del self._mailbox_tx_partial[:3]

        self._issue(f"reg(0x7C2)=0x{cur:02X}", 5.0)
        return new_frames

    # --- USB peripheral helpers (requires gpsim USB SIE model) ---

    def usb_host_cmd(self, cmd: int, *, ep: int = 0, length: int = 0) -> int:
        """Issue a USB host command and return the result."""
        self._issue(f"usb_host_ep = {ep}", 5.0)
        self._issue(f"usb_host_len = {length}", 5.0)
        self._issue(f"usb_host_cmd = {cmd}", 5.0)
        out = self._issue("usb_host_result", 5.0)
        return _parse_module_int_value(out, "usb_host_result")

    def usb_read_ram(self, addr: int, count: int) -> bytes:
        """Read bytes from USB Bank 4 RAM (0x400-0x7FF)."""
        return bytes(_read_reg(self._issue, addr + i) for i in range(count))

    def usb_write_ram(self, addr: int, data: bytes) -> None:
        """Write bytes to USB Bank 4 RAM."""
        for i, b in enumerate(data):
            self._issue(f"reg(0x{(addr + i):03X})=0x{b:02X}", 5.0)

    def usb_read_bd(self, bd_index: int) -> tuple[int, int, int, int]:
        """Read a Buffer Descriptor (stat, cnt, adrl, adrh)."""
        base = 0x400 + bd_index * 4
        return tuple(_read_reg(self._issue, base + i) for i in range(4))

    def usb_bd_addr(self, bd_index: int) -> int:
        """Get the buffer address from a BD."""
        _, _, adrl, adrh = self.usb_read_bd(bd_index)
        return adrl | (adrh << 8)

    def usb_bd_uown(self, bd_index: int) -> bool:
        """Check if SIE owns the BD (UOWN bit)."""
        stat, _, _, _ = self.usb_read_bd(bd_index)
        return bool(stat & 0x80)

    def usb_bus_reset(self) -> int:
        """Issue USB bus reset."""
        return self.usb_host_cmd(1)  # USB_BUS_RESET

    def usb_ep0_setup(self, setup_packet: bytes) -> int:
        """Send 8-byte SETUP packet to EP0 OUT."""
        if len(setup_packet) != 8:
            raise ValueError("SETUP packet must be 8 bytes")
        # Write setup data into the EP0 OUT BD's buffer
        bd_addr = self.usb_bd_addr(0)  # EP0 OUT even
        self.usb_write_ram(bd_addr, setup_packet)
        return self.usb_host_cmd(2)  # USB_EP0_SETUP

    def usb_ep0_in(self) -> tuple[int, bytes]:
        """Read EP0 IN response. Returns (result, data)."""
        result = self.usb_host_cmd(3)  # USB_EP0_IN
        _, cnt, adrl, adrh = self.usb_read_bd(2)  # EP0 IN BD
        buf_addr = adrl | (adrh << 8)
        data = self.usb_read_ram(buf_addr, cnt)
        return result, data

    def usb_ep0_out_status(self) -> int:
        """Send zero-length OUT status stage."""
        return self.usb_host_cmd(4)  # USB_EP0_OUT_STATUS

    def usb_ep_out(self, ep: int, data: bytes) -> int:
        """Send data to EPn OUT (e.g., HID report to EP1)."""
        bd_idx = 3 + (ep - 1) * 2  # EPn OUT BD index (mode 01)
        bd_addr = self.usb_bd_addr(bd_idx)
        self.usb_write_ram(bd_addr, data)
        return self.usb_host_cmd(5, ep=ep, length=len(data))

    def usb_ep_in(self, ep: int) -> tuple[int, bytes]:
        """Read data from EPn IN. Returns (result, data)."""
        bd_idx = 3 + (ep - 1) * 2 + 1  # EPn IN BD index
        result = self.usb_host_cmd(6, ep=ep)
        _, cnt, adrl, adrh = self.usb_read_bd(bd_idx)
        buf_addr = adrl | (adrh << 8)
        data = self.usb_read_ram(buf_addr, cnt)
        return result, data

    def usb_enumerate(self, *, timeout_steps: int = 80) -> None:
        """Prepare firmware for USB HID exchange.

        Forces USB configured state and sets up EP1 BDs so that
        usb_hid_exchange() can deliver HID reports via the SIE
        token engine (triggering real TRNIF interrupts).
        """
        # Set PORTC.0 high (VBUS detect)
        try:
            self._issue("portc0 = 1", 5.0)
        except Exception:
            pass

        # Wait for USB module to be enabled
        for _ in range(timeout_steps):
            self.step()
            ucon = _read_reg(self._issue, 0xF6D)
            if ucon & 0x08:
                break

        # Bus reset → triggers firmware USB init
        self.usb_bus_reset()
        for _ in range(20):
            self.step()

        # Force configured state + EP1 setup (bypasses EP0 enumeration)
        self._issue("reg(0x0CD)=0x06", 5.0)  # USB configured state
        self._issue("reg(0xF71)=0x1E", 5.0)  # UEP1 = interrupt EP enabled

        # Arm EP1 OUT BD (BD3 at 0x40C): buffer at 0x042C, 64 bytes
        self._issue("reg(0x40C)=0x88", 5.0)  # UOWN=1, DTSEN=1
        self._issue("reg(0x40D)=0x40", 5.0)  # cnt=64
        self._issue("reg(0x40E)=0x2C", 5.0)  # adrl
        self._issue("reg(0x40F)=0x04", 5.0)  # adrh

        # EP1 IN BD (BD4 at 0x410): firmware arms this after processing
        self._issue("reg(0x410)=0x00", 5.0)  # UOWN=0 (CPU owns)
        self._issue("reg(0x411)=0x40", 5.0)  # cnt=64
        self._issue("reg(0x412)=0x6C", 5.0)  # adrl
        self._issue("reg(0x413)=0x04", 5.0)  # adrh

        # Enable USB interrupt (UIE.TRNIE + UIE.URSTIE)
        self._issue("reg(0xF69)=0x7B", 5.0)  # UIE

        for _ in range(5):
            self.step()

    def usb_hid_exchange(self, report: bytes, *, timeout_steps: int = 40) -> bytes:
        """Send a 64-byte HID OUT report via SIE and read response.

        Writes the report to the EP1 OUT buffer (0x042C), triggers
        the EP_OUT token via the SIE engine (fires TRNIF), then waits
        for the firmware to process and arm EP1 IN with the response.
        """
        padded = (report + b"\x00" * 64)[:64]

        # Ensure EP1 OUT BD is armed
        self._issue("reg(0x40C)=0x88", 5.0)  # UOWN=1, DTSEN=1
        self._issue("reg(0x40D)=0x40", 5.0)  # cnt=64

        # Write report to EP1 OUT buffer at 0x042C
        self.usb_write_ram(0x042C, padded)

        # Force USB configured state and clear any pending UIR flags
        # (stale URSTIF from bus reset would cause firmware to reset 0xCD)
        self._issue("reg(0x0CD)=0x06", 5.0)
        # Clear all pending UIR flags (write 0xFF → W1C clears all bits)
        self._issue("reg(0xF68)=0xFF", 5.0)

        # Trigger EP1 OUT token via SIE (fires TRNIF → firmware processes)
        self.usb_host_cmd(5, ep=1, length=64)  # USB_EP_OUT

        # Let firmware process the HID command
        for _ in range(timeout_steps):
            self.step()

        # Read response from firmware's response buffer (0x15A-0x199)
        response = bytes(
            _read_reg(self._issue, 0x15A + i) for i in range(64)
        )
        return response

    def step(self) -> tuple[MainChainSnapshot, List[TxTriplet]]:
        self._apply_pin_models()
        self._apply_fault_injection_state()
        target_cycle = self.current_cycle + self.chunk_cycles
        timeout_s = _sim_step_timeout(self.chunk_cycles)
        self._issue(f"break c {target_cycle}", 5.0)
        out = self._issue("run", timeout_s)
        self.current_cycle = _parse_cycle(out)
        if self._native_an0_boot_pending and _contains_exec_break(out, self._main_boot_exit_addr):
            assert self._main_boot_exit_addr is not None
            if self._boot_bp_id is not None:
                _clear_break(self._issue, self._boot_bp_id)
                self._boot_bp_id = None
            self._native_an0_boot_pending = False
            self._apply_pin_models()
            if self.current_cycle < target_cycle:
                out = self._issue("run", timeout_s)
                self.current_cycle = _parse_cycle(out)
        self._apply_pin_models()
        if self.transport_mode == "mailbox":
            new_tx = self._drain_mailbox_tx_frames()
        else:
            new_tx = self.decoder.ingest(self.log_path)
        return self.read_snapshot(), new_tx


class LinkPipe:
    """Byte-paced current-loop transport for frame-aligned injection."""

    def __init__(
        self, name: str, *, byte_cycles: int, fifo_depth: int = EUSART_FIFO_DEPTH
    ) -> None:
        self.name = name
        self.byte_cycles = max(1, byte_cycles)
        self.fifo_depth = max(1, fifo_depth)
        self.queue: Deque[tuple[int, List[int]]] = deque()
        self._next_tx_cycle = 0
        self.delivered_last = 0
        self.overrun_last = 0

    def __len__(self) -> int:
        return len(self.queue)

    def clear(self) -> None:
        self.queue.clear()
        self._next_tx_cycle = 0
        self.delivered_last = 0
        self.overrun_last = 0

    def enqueue(self, frame: TxTriplet) -> None:
        start = max(int(frame.cycle), self._next_tx_cycle)
        last_byte_done = start + 3 * self.byte_cycles
        self._next_tx_cycle = last_byte_done
        self.queue.append((last_byte_done, [frame.route, frame.cmd, frame.data]))

    def pump(self, now_cycle: int, sink: object, *, max_inject: int = 256) -> int:
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
            return 0

        delivered, overruns = sink.inject_frames_fifo(ready, self.fifo_depth)
        self.delivered_last = delivered
        self.overrun_last = overruns
        return delivered


class SingleMainChainHarness:
    """One-main CONTROL<->MAIN gpsim link harness for robustness tests."""

    def __init__(
        self,
        control_hex: Path,
        main_hex: Path,
        *,
        gpasm: str = "gpasm",
        fast_boot: bool = True,
        control_chunk_cycles: int = 200_000,
        main_chunk_cycles: int = 200_000,
        hold_cycles: int = 240_000,
        rx_fifo_limit: int = 47,
        disable_standby_check: bool = False,
        bypass_i2c: bool = False,
        main_transport_mode: str = "mailbox",
        enable_main_timeout_test_hooks: bool = False,
    ) -> None:
        self.control = GpsimControlHarness(
            control_hex,
            fast_boot=fast_boot,
            chunk_cycles=control_chunk_cycles,
            hold_cycles=hold_cycles,
            heartbeat_rx_mode="none",
            heartbeat_force_connected=False,
            heartbeat_reset_idle=False,
            disable_standby_check=disable_standby_check,
        )
        self.control.pause_heartbeat()
        self.main = MainChainHarness(
            main_hex,
            gpasm=gpasm,
            chunk_cycles=main_chunk_cycles,
            tag="0",
            standby_mode="hold",
            main_ra0_adc=None,
            rc2_mode="high",
            rx_fifo_limit=rx_fifo_limit,
            bypass_i2c=bypass_i2c,
            transport_mode=main_transport_mode,
            enable_timeout_test_hooks=enable_main_timeout_test_hooks,
        )
        self.link_ctl_m0 = LinkPipe(
            "CTL->M0",
            byte_cycles=_byte_cycles(CONTROL_FOSC_HZ),
            fifo_depth=rx_fifo_limit,
        )
        self.link_m0_ctl = LinkPipe(
            "M0->CTL",
            byte_cycles=_byte_cycles(MAIN_FOSC_HZ),
            fifo_depth=rx_fifo_limit,
        )
        self._blackout = False

    def close(self) -> None:
        try:
            self.main.close()
        finally:
            self.control.close()

    def lcd_lines(self) -> tuple[str, str]:
        return self.control.lcd_lines()

    def is_connected(self) -> bool:
        return bool(self.control.read_reg(0x01F) & 0x02)

    def is_waiting(self) -> bool:
        return _is_waiting_lcd(self.control.lcd_lines())

    def press(self, key: str) -> None:
        # Recording happens inside `GpsimControlHarness.press` so direct
        # `chain.control.press(...)` test calls are captured.  Recording
        # again here would emit two events per `pair.press(...)` call.
        self.control.press(key)

    def set_blackout(self, enabled: bool) -> None:
        record_event(
            kind="set_blackout",
            harness="single_main_chain",
            payload={"enabled": bool(enabled)},
        )
        self._blackout = enabled
        if enabled:
            self.link_ctl_m0.clear()
            self.link_m0_ctl.clear()
        snapshot_after_event("set_blackout", [self.control, self.main])

    def set_main_fault_flags(
        self,
        *,
        uart_tx_stall: bool | None = None,
        mssp_wait_stall: bool | None = None,
    ) -> int:
        record_event(
            kind="set_main_fault_flags",
            harness="single_main_chain",
            payload={
                "uart_tx_stall": uart_tx_stall,
                "mssp_wait_stall": mssp_wait_stall,
            },
        )
        flags = self.main.set_fault_flags(
            uart_tx_stall=uart_tx_stall,
            mssp_wait_stall=mssp_wait_stall,
        )
        snapshot_after_event("set_main_fault_flags", [self.main])
        return flags

    def clear_main_fault_flags(self) -> None:
        record_event(kind="clear_main_fault_flags", harness="single_main_chain")
        self.main.clear_fault_flags()
        snapshot_after_event("clear_main_fault_flags", [self.main])

    def set_main_uart_fault(
        self,
        *,
        trmt_busy_cycles: int | None = None,
        trmt_busy_count: int | None = None,
    ) -> None:
        record_event(
            kind="set_main_uart_fault",
            harness="single_main_chain",
            payload={
                "trmt_busy_cycles": trmt_busy_cycles,
                "trmt_busy_count": trmt_busy_count,
            },
        )
        self.main.set_uart_fault(
            trmt_busy_cycles=trmt_busy_cycles,
            trmt_busy_count=trmt_busy_count,
        )
        snapshot_after_event("set_main_uart_fault", [self.main])

    def clear_main_uart_faults(self) -> None:
        record_event(kind="clear_main_uart_faults", harness="single_main_chain")
        self.main.clear_uart_faults()
        snapshot_after_event("clear_main_uart_faults", [self.main])

    def set_main_mssp_stop_fault(
        self,
        *,
        stop_busy_cycles: int | None = None,
        stop_busy_count: int | None = None,
    ) -> None:
        record_event(
            kind="set_main_mssp_stop_fault",
            harness="single_main_chain",
            payload={
                "stop_busy_cycles": stop_busy_cycles,
                "stop_busy_count": stop_busy_count,
            },
        )
        self.main.set_mssp_stop_fault(
            stop_busy_cycles=stop_busy_cycles,
            stop_busy_count=stop_busy_count,
        )
        snapshot_after_event("set_main_mssp_stop_fault", [self.main])

    def clear_main_mssp_stop_faults(self) -> None:
        record_event(kind="clear_main_mssp_stop_faults", harness="single_main_chain")
        self.main.clear_mssp_stop_faults()
        snapshot_after_event("clear_main_mssp_stop_faults", [self.main])

    def set_main_i2c_fault(
        self,
        device_name: str = "cfg71",
        *,
        address_nack_count: int | None = None,
        address_stretch_scl_cycles: int | None = None,
        address_stretch_count: int | None = None,
        data_nack_count: int | None = None,
        data_stuck_sda_cycles: int | None = None,
        data_stuck_sda_count: int | None = None,
        hold_scl_low: bool | None = None,
        stretch_scl_cycles: int | None = None,
    ) -> None:
        record_event(
            kind="set_main_i2c_fault",
            harness="single_main_chain",
            payload={
                "device_name": device_name,
                "address_nack_count": address_nack_count,
                "address_stretch_scl_cycles": address_stretch_scl_cycles,
                "address_stretch_count": address_stretch_count,
                "data_nack_count": data_nack_count,
                "data_stuck_sda_cycles": data_stuck_sda_cycles,
                "data_stuck_sda_count": data_stuck_sda_count,
                "hold_scl_low": hold_scl_low,
                "stretch_scl_cycles": stretch_scl_cycles,
            },
        )
        self.main.set_i2c_fault(
            device_name,
            address_nack_count=address_nack_count,
            address_stretch_scl_cycles=address_stretch_scl_cycles,
            address_stretch_count=address_stretch_count,
            data_nack_count=data_nack_count,
            data_stuck_sda_cycles=data_stuck_sda_cycles,
            data_stuck_sda_count=data_stuck_sda_count,
            hold_scl_low=hold_scl_low,
            stretch_scl_cycles=stretch_scl_cycles,
        )
        snapshot_after_event("set_main_i2c_fault", [self.main])

    def clear_main_i2c_faults(self, device_name: str = "cfg71") -> None:
        record_event(
            kind="clear_main_i2c_faults",
            harness="single_main_chain",
            payload={"device_name": device_name},
        )
        self.main.clear_i2c_faults(device_name)
        snapshot_after_event("clear_main_i2c_faults", [self.main])

    def step(self) -> ChainStepResult:
        if not self._blackout:
            self.link_m0_ctl.pump(self.control.current_cycle, self.control)

        control_step = self.control.step()
        standby_bus = 1 if (self.control.read_reg(0x01F) & 0x04) else 0
        self.main.set_standby_bus(standby_bus)

        if not self._blackout:
            for frame in control_step.new_tx:
                if (frame.route & 0xF0) == 0xB0:
                    self.link_ctl_m0.enqueue(frame)
            self.link_ctl_m0.pump(control_step.cycle, self.main)
        main_snapshot, main_tx = self.main.step()
        if not self._blackout:
            for frame in main_tx:
                if frame.route == 0xBF:
                    self.link_m0_ctl.enqueue(frame)
        else:
            main_tx = []

        return ChainStepResult(
            lcd=control_step.lcd,
            control_flags=self.control.read_reg(0x01F),
            control_tx=control_step.new_tx,
            main_tx=main_tx,
            cycle=control_step.cycle,
            main=main_snapshot,
        )

    def step_many(self, steps: int) -> ChainStepResult | None:
        last: ChainStepResult | None = None
        for _ in range(max(0, steps)):
            last = self.step()
        return last

    def run_until_connected(self, *, limit: int) -> ChainStepResult | None:
        last: ChainStepResult | None = None
        for _ in range(limit):
            last = self.step()
            if self.is_connected() and not _is_waiting_lcd(last.lcd):
                return last
        return last

    def run_until_waiting(self, *, limit: int) -> ChainStepResult | None:
        last: ChainStepResult | None = None
        for _ in range(limit):
            last = self.step()
            if _is_waiting_lcd(last.lcd):
                return last
        return last
