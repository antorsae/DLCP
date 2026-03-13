"""Live wire-mode gpsim chain harness using real RC6/RC7 UART pins.

This harness keeps each PIC in its own gpsim process and bridges the UART
pins with gpsim's FileRecorder/FileStimulus modules. That preserves the
simulated EUSART timing and receive buffering inside each MCU instead of
injecting bytes directly into firmware RAM rings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict

from .chain_gpsim import MainChainHarness, _is_waiting_lcd
from .control_gpsim import CONTROL_FOSC_HZ, GpsimControlHarness, TxTriplet, _read_reg

CONTROL_TCY_HZ = CONTROL_FOSC_HZ // 4
MAIN_TCY_HZ = 16_000_000 // 4


def _scaled_cycles(cycles: int, *, from_hz: int, to_hz: int) -> int:
    return max(1, int((cycles * to_hz + (from_hz // 2)) // from_hz))


def _attach_tx_recorder(issue, *, processor: str, tx_pin: str, recorder_name: str, out_path: Path) -> None:
    issue("module library libgpsim_modules", 5.0)
    issue(f"module load FileRecorder {recorder_name}", 5.0)
    issue(f"node n_{recorder_name}", 5.0)
    issue(f"attach n_{recorder_name} {processor}.{tx_pin} {recorder_name}.pin", 5.0)
    issue(f"{recorder_name}.digital = true", 5.0)
    issue(f'{recorder_name}.file = "{out_path}"', 5.0)


def _attach_rx_stimulus(
    issue,
    *,
    processor: str,
    rx_pin: str,
    stimulus_name: str,
    fifo_path: Path,
    poll_cycles: int = 8,
) -> None:
    issue("module library libgpsim_modules", 5.0)
    issue(f"module load FileStimulus {stimulus_name}", 5.0)
    issue(f"node n_{stimulus_name}", 5.0)
    issue(f"attach n_{stimulus_name} {stimulus_name}.pin {processor}.{rx_pin}", 5.0)
    issue(f"{stimulus_name}.initial = 5", 5.0)
    issue(f"{stimulus_name}.poll = {max(1, poll_cycles)}", 5.0)
    issue(f'{stimulus_name}.file = "{fifo_path}"', 30.0)


class _StreamingUartBridge:
    """Convert one sender's recorded pin transitions into another pin stream."""

    def __init__(
        self,
        *,
        name: str,
        sender_record_path: Path,
        receiver_fifo_path: Path,
        scale_num: int,
        scale_den: int,
        idle_voltage: int = 5,
    ) -> None:
        self.name = name
        self.sender_record_path = sender_record_path
        self.receiver_fifo_path = receiver_fifo_path
        self.scale_num = scale_num
        self.scale_den = scale_den
        self.idle_voltage = idle_voltage
        self._drop = False
        self._extra_cycles = 0
        self._sender_offset = 0
        self._sender_partial = ""
        self._last_receiver_cycle = 0

    def start(self) -> None:
        self.receiver_fifo_path.write_text(f"0 {self.idle_voltage}\n", encoding="ascii")

    def close(self) -> None:
        return

    def configure(self, *, drop: bool | None = None, extra_cycles: int | None = None) -> None:
        if drop is not None:
            self._drop = bool(drop)
        if extra_cycles is not None:
            self._extra_cycles = max(0, int(extra_cycles))

    def clear_fault(self) -> None:
        self.configure(drop=False, extra_cycles=0)

    def flush(self, *, receiver_min_cycle: int | None = None) -> int:
        """Forward newly-recorded sender transitions into the receiver stimulus file.

        The sender and receiver live in separate gpsim processes, so a batch may
        only become available after the receiver has already advanced past the
        sender's natural mapped cycle. In that case, shift the whole batch into
        the receiver's future while preserving intra-batch spacing.
        """
        if not self.sender_record_path.exists():
            return 0
        with self.sender_record_path.open("r", encoding="ascii", errors="replace") as record:
            record.seek(self._sender_offset)
            chunk = record.read()
            self._sender_offset = record.tell()
        if not chunk:
            return 0

        blob = self._sender_partial + chunk
        lines = blob.split("\n")
        if blob and not blob.endswith("\n"):
            self._sender_partial = lines.pop()
        else:
            self._sender_partial = ""

        edges: list[tuple[int, int]] = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) != 2:
                continue
            try:
                sender_cycle = int(parts[0], 10)
                sender_level = int(float(parts[1]))
            except ValueError:
                continue
            edges.append((sender_cycle, sender_level))

        if not edges:
            return 0
        if self._drop:
            return len(edges)

        mapped_cycles = [
            ((sender_cycle * self.scale_num + (self.scale_den // 2)) // self.scale_den) + self._extra_cycles
            for sender_cycle, _ in edges
        ]
        batch_shift = 0
        first_cycle = mapped_cycles[0]
        min_target = self._last_receiver_cycle + 1
        if receiver_min_cycle is not None:
            min_target = max(min_target, receiver_min_cycle + 1)
        if first_cycle < min_target:
            batch_shift = min_target - first_cycle

        with self.receiver_fifo_path.open("a", buffering=1, encoding="ascii") as fifo:
            for mapped_cycle, (_, sender_level) in zip(mapped_cycles, edges):
                receiver_cycle = mapped_cycle + batch_shift
                if receiver_cycle <= self._last_receiver_cycle:
                    receiver_cycle = self._last_receiver_cycle + 1
                self._last_receiver_cycle = receiver_cycle
                receiver_voltage = self.idle_voltage if sender_level else 0
                fifo.write(f"{receiver_cycle} {receiver_voltage}\n")
        return len(edges)


@dataclass(frozen=True)
class WireMainSnapshot:
    index: int
    cycle: int
    status_5e: int
    flags_7e: int
    rx_rd: int
    rx_wr: int
    tx_frame_count: int


@dataclass(frozen=True)
class WireChainStepResult:
    lcd: tuple[str, str]
    control_flags: int
    cycle: int
    control_tx: tuple[TxTriplet, ...]
    control_rx_rd: int
    control_rx_wr: int
    mains: tuple[WireMainSnapshot, ...]
    main_new_tx: tuple[tuple[TxTriplet, ...], ...]


class WireMultiMainChainHarness:
    """High-fidelity UART chain harness for CONTROL + one or more MAIN units."""

    def __init__(
        self,
        control_hex: Path,
        main_hex: Path,
        *,
        main_units: int = 1,
        gpasm: str = "gpasm",
        fast_boot: bool = False,
        control_chunk_cycles: int = 1_000_000,
        hold_cycles: int = 240_000,
        disable_standby_check: bool = False,
    ) -> None:
        if main_units < 1:
            raise ValueError("main_units must be >= 1")

        self._tmp = TemporaryDirectory(prefix="gpsim_wire_chain_")
        self.tmp_path = Path(self._tmp.name)
        self.control_chunk_cycles = control_chunk_cycles
        self._main_chunk_cycles = _scaled_cycles(
            control_chunk_cycles,
            from_hz=CONTROL_TCY_HZ,
            to_hz=MAIN_TCY_HZ,
        )

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

        self.mains = [
            MainChainHarness(
                main_hex,
                gpasm=gpasm,
                chunk_cycles=self._main_chunk_cycles,
                tag=str(index),
                standby_mode="hold",
                main_ra0_adc=None,
                rc2_mode="high",
                transport_mode="native_ring",
            )
            for index in range(main_units)
        ]

        self._bridges: list[_StreamingUartBridge] = []
        self._bridge_map: Dict[str, _StreamingUartBridge] = {}
        self._control_rx_activity = False
        self._control_rx_prev = (0, 0)
        self._main_rx_activity = [False] * main_units
        self._main_rx_prev = [(0, 0)] * main_units

        self._attach_uart_transport()

    def _attach_uart_transport(self) -> None:
        control_tx = self.tmp_path / "control_tx.txt"
        _attach_tx_recorder(
            self.control._issue,
            processor="p18f25k20",
            tx_pin="portc6",
            recorder_name="CTLTXREC",
            out_path=control_tx,
        )

        main_tx_paths: list[Path] = []
        for index, main in enumerate(self.mains):
            main_tx = self.tmp_path / f"main{index}_tx.txt"
            main_tx_paths.append(main_tx)
            _attach_tx_recorder(
                main._issue,
                processor="p18f2455",
                tx_pin="portc6",
                recorder_name=f"M{index}TXREC",
                out_path=main_tx,
            )

        def add_link(
            *,
            link_name: str,
            sender_record_path: Path,
            sender_tcy_hz: int,
            receiver_issue,
            receiver_processor: str,
            receiver_rx_pin: str,
            receiver_tcy_hz: int,
            stimulus_name: str,
        ) -> None:
            fifo_path = self.tmp_path / f"{stimulus_name}.stim"
            bridge = _StreamingUartBridge(
                name=link_name,
                sender_record_path=sender_record_path,
                receiver_fifo_path=fifo_path,
                scale_num=receiver_tcy_hz,
                scale_den=sender_tcy_hz,
            )
            bridge.start()
            _attach_rx_stimulus(
                receiver_issue,
                processor=receiver_processor,
                rx_pin=receiver_rx_pin,
                stimulus_name=stimulus_name,
                fifo_path=fifo_path,
            )
            self._bridges.append(bridge)
            self._bridge_map[link_name] = bridge

        add_link(
            link_name="ctl_to_m0",
            sender_record_path=control_tx,
            sender_tcy_hz=CONTROL_TCY_HZ,
            receiver_issue=self.mains[0]._issue,
            receiver_processor="p18f2455",
            receiver_rx_pin="portc7",
            receiver_tcy_hz=MAIN_TCY_HZ,
            stimulus_name="CTL2M0",
        )
        add_link(
            link_name="m0_to_ctl",
            sender_record_path=main_tx_paths[0],
            sender_tcy_hz=MAIN_TCY_HZ,
            receiver_issue=self.control._issue,
            receiver_processor="p18f25k20",
            receiver_rx_pin="portc7",
            receiver_tcy_hz=CONTROL_TCY_HZ,
            stimulus_name="M02CTL",
        )

        for index in range(len(self.mains) - 1):
            add_link(
                link_name=f"m{index}_to_m{index + 1}",
                sender_record_path=main_tx_paths[index],
                sender_tcy_hz=MAIN_TCY_HZ,
                receiver_issue=self.mains[index + 1]._issue,
                receiver_processor="p18f2455",
                receiver_rx_pin="portc7",
                receiver_tcy_hz=MAIN_TCY_HZ,
                stimulus_name=f"M{index}2M{index + 1}",
            )
            add_link(
                link_name=f"m{index + 1}_to_m{index}",
                sender_record_path=main_tx_paths[index + 1],
                sender_tcy_hz=MAIN_TCY_HZ,
                receiver_issue=self.mains[index]._issue,
                receiver_processor="p18f2455",
                receiver_rx_pin="portc7",
                receiver_tcy_hz=MAIN_TCY_HZ,
                stimulus_name=f"M{index + 1}2M{index}",
            )

    def close(self) -> None:
        for bridge in self._bridges:
            bridge.close()
        try:
            for main in self.mains:
                main.close()
        finally:
            self.control.close()
            self._tmp.cleanup()

    def press(self, key: str) -> None:
        self.control.press(key)

    def lcd_lines(self) -> tuple[str, str]:
        return self.control.lcd_lines()

    def is_waiting(self) -> bool:
        return _is_waiting_lcd(self.lcd_lines())

    def is_connected(self) -> bool:
        return bool(self.control.read_reg(0x01F) & 0x02)

    def set_link_fault(
        self,
        link_name: str,
        *,
        drop: bool | None = None,
        extra_cycles: int | None = None,
    ) -> None:
        try:
            bridge = self._bridge_map[link_name]
        except KeyError as exc:
            names = ", ".join(sorted(self._bridge_map))
            raise KeyError(f"unknown wire link {link_name!r}; known links: {names}") from exc
        bridge.configure(drop=drop, extra_cycles=extra_cycles)

    def clear_link_faults(self) -> None:
        for bridge in self._bridge_map.values():
            bridge.clear_fault()

    def set_main_i2c_fault(
        self,
        device_name: str = "cfg71",
        *,
        main_index: int = 0,
        address_nack_count: int | None = None,
        address_stretch_scl_cycles: int | None = None,
        address_stretch_count: int | None = None,
        data_nack_count: int | None = None,
        data_stuck_sda_cycles: int | None = None,
        data_stuck_sda_count: int | None = None,
        hold_scl_low: bool | None = None,
        stretch_scl_cycles: int | None = None,
    ) -> None:
        self.mains[main_index].set_i2c_fault(
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

    def clear_main_i2c_faults(self, device_name: str = "cfg71", *, main_index: int = 0) -> None:
        self.mains[main_index].clear_i2c_faults(device_name)

    def control_rx_activity(self) -> bool:
        return self._control_rx_activity

    def main_rx_activity(self, index: int) -> bool:
        return self._main_rx_activity[index]

    def main_tx_activity(self, index: int) -> bool:
        return bool(self.mains[index].decoder.tx_frames)

    def main_tx_frames(self, index: int) -> list[TxTriplet]:
        return list(self.mains[index].decoder.tx_frames)

    def _read_control_rx_state(self) -> tuple[int, int]:
        return (_read_reg(self.control._issue, 0x098), _read_reg(self.control._issue, 0x099))

    def _update_rx_activity(self) -> tuple[int, int]:
        control_rx_rd, control_rx_wr = self._read_control_rx_state()
        current_control = (control_rx_rd, control_rx_wr)
        if current_control != self._control_rx_prev or current_control != (0, 0):
            self._control_rx_activity = True
        self._control_rx_prev = current_control

        for index, main in enumerate(self.mains):
            current_main = (_read_reg(main._issue, 0x0C6), _read_reg(main._issue, 0x0C7))
            if current_main != self._main_rx_prev[index] or current_main != (0, 0):
                self._main_rx_activity[index] = True
            self._main_rx_prev[index] = current_main

        return current_control

    def _flush_bridges(
        self,
        *,
        names: tuple[str, ...] | None = None,
        receiver_min_cycle: int | None = None,
    ) -> None:
        if names is None:
            bridges = tuple(self._bridges)
        else:
            bridges = tuple(self._bridge_map[name] for name in names)
        for bridge in bridges:
            bridge.flush(receiver_min_cycle=receiver_min_cycle)

    def step(self) -> WireChainStepResult:
        control_step = self.control.step()
        control_tx = tuple(control_step.new_tx)

        # Mirror native-ring standby propagation: CONTROL bit2 drives MAIN RC2.
        standby_bus = 1 if (self.control.read_reg(0x01F) & 0x04) else 0
        for main in self.mains:
            main.set_standby_bus(standby_bus)

        # Forward CONTROL TX edges into MAIN input files before MAIN advances.
        self._flush_bridges(
            names=("ctl_to_m0",),
            receiver_min_cycle=min(main.current_cycle for main in self.mains),
        )
        main_new_tx: list[tuple[TxTriplet, ...]] = []
        main_snaps: list[WireMainSnapshot] = []
        for index, main in enumerate(self.mains):
            snap, new_tx_list = main.step()
            new_tx = tuple(new_tx_list)
            main_new_tx.append(new_tx)
            outgoing: list[str] = []
            if index == 0:
                outgoing.append("m0_to_ctl")
            if index > 0:
                outgoing.append(f"m{index}_to_m{index - 1}")
            if index + 1 < len(self.mains):
                outgoing.append(f"m{index}_to_m{index + 1}")
            for name in outgoing:
                if name.endswith("_to_ctl"):
                    receiver_cycle = self.control.current_cycle
                else:
                    dst_index = int(name.rsplit("_to_m", 1)[1])
                    receiver_cycle = self.mains[dst_index].current_cycle
                self._bridge_map[name].flush(receiver_min_cycle=receiver_cycle)
            main_snaps.append(
                WireMainSnapshot(
                    index=index,
                    cycle=main.current_cycle,
                    status_5e=snap.status_5e,
                    flags_7e=snap.flags_7e,
                    rx_rd=snap.mailbox_rd,
                    rx_wr=snap.mailbox_wr,
                    tx_frame_count=len(main.decoder.tx_frames),
                )
            )
        control_rx_rd, control_rx_wr = self._update_rx_activity()

        return WireChainStepResult(
            lcd=control_step.lcd,
            control_flags=self.control.read_reg(0x01F),
            cycle=control_step.cycle,
            control_tx=control_tx,
            control_rx_rd=control_rx_rd,
            control_rx_wr=control_rx_wr,
            mains=tuple(main_snaps),
            main_new_tx=tuple(main_new_tx),
        )

    def step_many(self, steps: int) -> WireChainStepResult | None:
        last: WireChainStepResult | None = None
        for _ in range(max(0, steps)):
            last = self.step()
        return last

    def run_until_connected(self, *, limit: int) -> WireChainStepResult | None:
        last: WireChainStepResult | None = None
        for _ in range(limit):
            last = self.step()
            if self.is_connected() and not _is_waiting_lcd(last.lcd):
                return last
        return last

    def run_until_waiting(self, *, limit: int) -> WireChainStepResult | None:
        last: WireChainStepResult | None = None
        for _ in range(limit):
            last = self.step()
            if _is_waiting_lcd(last.lcd):
                return last
        return last

    def run_until_main_reply(self, *, limit: int, main_index: int = 0) -> WireChainStepResult | None:
        last: WireChainStepResult | None = None
        before = len(self.mains[main_index].decoder.tx_frames)
        for _ in range(limit):
            last = self.step()
            if len(self.mains[main_index].decoder.tx_frames) > before:
                return last
        return last
